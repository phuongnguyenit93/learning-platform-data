# Testing HealthIndicator and InfoContributor in Isolation

When the inventory service responds normally, the health indicator must return `UP`. If the inventory service is unreachable, the indicator must return `DOWN` with an appropriate reason. The info contributor has a different responsibility. It adds the release version to the data that Actuator will aggregate. Both behaviors can be tested by instantiating the class with `new`, calling the method, and asserting on the returned object or the added data.

| Component | Direct Call | What to Verify |
| --- | --- | --- |
| `HealthIndicator` | `health()` | The `Status` value and `Health.getDetails()` contents corresponding to each outcome of the dependency check. |
| `InfoContributor` | `contribute(builder)` | The key, data type, and value added to `Info.Builder`, and that existing entries under other keys remain intact. |

When running inside an application, Actuator discovers components registered as beans. In unit tests, the test itself creates the components and supplies the inputs. This approach lets you reproduce each branch without starting Spring, opening an HTTP port, or calling the inventory service. [HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) · [Actuator Extension Components](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## Preparing the Sample Project

The example uses Java 17 or later, Gradle, Spring Boot Actuator 3.3.0, and JUnit Jupiter. Create `build.gradle` in a separate test directory. The Spring Boot Bill of Materials (BOM) provides the corresponding dependency versions. The `test` task runs the tests via the JUnit Platform.

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

## Testing HealthIndicator

Extract the inventory service connection into `InventoryProbe` and inject it via the constructor. The indicator class only translates the check result into a `Health`. The example's policy is to return `UP` when reachable, `DOWN` with reason `unreachable` when the check returns `false`, and `DOWN` with reason `probe_failed` when an I/O error occurs.

**`src/main/java/demo/actuator/InventoryHealthIndicator.java`**

```java
package demo.actuator;

import java.io.IOException;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class InventoryHealthIndicator implements HealthIndicator {

    @FunctionalInterface
    public interface InventoryProbe {
        boolean isReachable() throws IOException;
    }

    private final InventoryProbe probe;

    public InventoryHealthIndicator(InventoryProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            if (probe.isReachable()) {
                return Health.up().build();
            }
            return Health.down().withDetail("reason", "unreachable").build();
        } catch (IOException failure) {
            return Health.down().withDetail("reason", "probe_failed").build();
        }
    }
}
```

Each test case uses a predetermined stub probe. The first two lambdas immediately return `true` or `false`. The third lambda throws `SocketTimeoutException` to simulate a timeout without sleeping or waiting on the network. Comparing the entire details map catches both returning the wrong reason and accidentally leaking an exception message containing an internal address into the result.

**`src/test/java/demo/actuator/InventoryHealthIndicatorTest.java`**

```java
package demo.actuator;

import java.net.SocketTimeoutException;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InventoryHealthIndicatorTest {

    @Test
    void returnsUpWhenTheProbeSucceeds() {
        var indicator = new InventoryHealthIndicator(() -> true);

        Health result = indicator.health();

        assertEquals(Status.UP, result.getStatus());
        assertEquals(Map.of(), result.getDetails());
    }

    @Test
    void returnsDownWhenTheProbeReportsUnreachable() {
        var indicator = new InventoryHealthIndicator(() -> false);

        Health result = indicator.health();

        assertEquals(Status.DOWN, result.getStatus());
        assertEquals(Map.of("reason", "unreachable"), result.getDetails());
    }

    @Test
    void returnsDownWithASafeReasonWhenTheProbeTimesOut() {
        var indicator = new InventoryHealthIndicator(() -> {
            throw new SocketTimeoutException("private endpoint: inventory.internal");
        });

        Health result = indicator.health();

        assertEquals(Status.DOWN, result.getStatus());
        assertEquals(Map.of("reason", "probe_failed"), result.getDetails());
    }
}
```

Use `Status.UP` and `Status.DOWN` to assert results at the Java layer. Aggregating indicators, deciding detail visibility, and mapping statuses to HTTP codes belong to the endpoint layer. Those rules should be tested with application configuration when they are part of the requirements. [Health Endpoint Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health)

## Testing InfoContributor

`contribute` adds data to the builder passed in by the caller. The example uses the top-level key `inventory`, with a nested map containing `release`. The class receives the release version through its constructor, so the test controls the value without having to read configuration from the environment.

**`src/main/java/demo/actuator/InventoryInfoContributor.java`**

```java
package demo.actuator;

import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;

public final class InventoryInfoContributor implements InfoContributor {

    private final String release;

    public InventoryInfoContributor(String release) {
        this.release = release;
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("inventory", Map.of("release", release));
    }
}
```

Instantiate a real `Info.Builder` and pre-populate an entry simulating data supplied by another component. Call `contribute`, then call `build().getDetails()` to inspect the final data. Comparing maps verifies nested structure, values, and existing entries without depending on key order. Assign a distinct top-level key to each component to avoid two components writing to the same entry. [How to Contribute Data to the Info Endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info.writing-custom-info-contributors)

**`src/test/java/demo/actuator/InventoryInfoContributorTest.java`**

```java
package demo.actuator;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InventoryInfoContributorTest {

    @Test
    void addsInventoryMetadataWithoutOverwritingOtherEntries() {
        var contributor = new InventoryInfoContributor("2026.11");
        Info.Builder builder = new Info.Builder()
            .withDetail("application", Map.of("name", "store"));

        contributor.contribute(builder);

        assertEquals(
            Map.of(
                "application", Map.of("name", "store"),
                "inventory", Map.of("release", "2026.11")
            ),
            builder.build().getDetails()
        );
    }
}
```

## Running and Reading Results

From the directory containing `build.gradle`, run the following command.

```bash
gradle test
```

Expect all three cases in `InventoryHealthIndicatorTest` and the single case in `InventoryInfoContributorTest` to pass. The third indicator test demonstrates how the class **handles** a timeout exception. To verify that the real client applies the configured timeout properly, test the client at the integration layer.

When connecting the two components to a real application, additional tests can confirm that the beans are discovered, that the indicator appears under the right name or health group, and that the data is published according to configuration at `/actuator/health` or `/actuator/info`. If the isolated tests fail, start from the conversion logic inside the component. If only the endpoint tests fail, check bean registration and endpoint configuration before changing rules already verified at the Java layer.
