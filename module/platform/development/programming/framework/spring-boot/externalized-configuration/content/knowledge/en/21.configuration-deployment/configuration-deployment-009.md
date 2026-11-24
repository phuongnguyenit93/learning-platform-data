# Self-Refresh Limits of Plain Spring Boot and the Spring Cloud Boundary

## 1. Core Question: Configuration Was Edited, Why Does the Application Keep Old Values?

Spring Boot provides a flexible **Externalized Configuration** system: an application can read `application.yaml`, `application.properties`, external files outside the JAR, environment variables, system properties, command-line arguments, and `configtree:`. These sources let you change configuration **without modifying Java source code**.

However, there is a wide gap between "configuration lives outside the application" and "changing a value makes the running application update immediately."

Suppose you have:

```yaml
demo:
  banner: "version-one"
  request-timeout: 2s
```

and a service:

```java
@Component
public class BannerService {

    private final String banner;

    public BannerService(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

If you edit the file to:

```yaml
demo:
  banner: "version-two"
  request-timeout: 500ms
```

while the Spring Boot process is running, `banner()` **does not change automatically**. Core Spring Boot does not by default watch files to reload Config Data, does not rerun bean constructors, and does not automatically refresh connection pools or HTTP clients.

Many technologies labeled "refresh" actually address **different layers**:

1. The true configuration source is edited.
2. The process detects and reloads the new values.
3. `Environment`/`PropertySource` inside the process reflects the new values.
4. Beans depending on configuration are rebound or recreated.
5. Live business resources actually apply the change.
6. Multiple instances transition safely to the new state together.

**Plain Spring Boot focuses on loading and binding configuration during the startup lifecycle; Spring Cloud adds remote config, refresh, scope, and event mechanisms to support certain runtime update layers.** Yet even with Spring Cloud, not all six steps are automatically instantaneous or consistent.

This lesson belongs to the **Configuration Deployment** group under **Spring Boot Externalized Configuration**.

### Learning objectives

After this lesson, you will be able to:

- Distinguish **externalized** from **hot-reload** and **dynamic refresh**.
- Describe how Config Data loads into `Environment` when Spring Boot starts.
- Compare `Environment.getProperty()` lookups, values injected via `@Value`, `@ConfigurationProperties` beans, and resources already constructed from configuration.
- Explain why editing mounted files, ConfigMaps, Secrets, or YAML outside the JAR does not make the application auto-update.
- Run a Boot-only experiment proving that editing a file at runtime does not auto-reload it.
- Run an experiment **mutating a `PropertySource` in memory** to prove a new value in `Environment` does not mean existing beans updated.
- Understand the roles of `EnvironmentChangeEvent`, `@RefreshScope`, `/actuator/refresh`, Spring Cloud Config, Consul Watch, and Spring Cloud Bus.
- Know when a rolling restart is safer and simpler than in-place refresh.
- Understand limitations with records, constructor binding, static fields, connection pools, and secret rotation.
- Design testing, rollout, rollback, and security for runtime configuration changes.

**Illustrative scope:** Java 21, Spring Boot 3.3.x; examples pin Spring Boot `3.3.13`. The Spring Cloud section describes the `2023.0.x` release train compatible with Boot 3.3 (examples use `2023.0.6`). These versions are for learning, not a claim that they are always the latest releases. For projects running another release train, consult documentation for that exact version.

---

## 2. Two Concepts Often Conflated: Externalized Configuration and Live Refresh

**Externalized configuration** means configuration sources can live outside Java code or outside the artifact, allowing each environment to supply its own data. It solves:

```text
Same binary JAR
       |
       +--> development: application-dev.yaml
       |
       +--> staging:     environment variables / mounted file
       |
       +--> production:  configtree / remote config provider
```

The goal is **decoupling code from deployment values**. There is no default contract that a running process continuously polls every file.

**Live refresh** is a deliberate chain of actions:

```text
Value at source changes
           |
           v
Detection mechanism / refresh trigger exists?
           |
           v
Property sources reloaded?
           |
           v
Environment sees new value?
           |
           v
Beans updated or recreated?
           |
           v
Running services and resources apply new value?
```

If any link is missing, the practical outcome is "the source changed, yet business logic still uses the old value."

Example: a secret in Vault is rotated successfully. That only confirms **the record or lease in Vault** changed. If a `DataSource` already holds connections using the old credential, the pool and connections may still need recreation or a dedicated handling policy.

### 2.1. Four diagnostic questions to ask in order

1. **Did the source actually change?** Check the file, revision, KV path, secret version, or current source.
2. **Did the process see the new source?** Did `Environment` or the provider reload?
3. **Which beans still hold an old snapshot?** `@Value`, constructor-injected fields, records, config beans, or a singleton that copied data.
4. **Which runtime infrastructure needs recreation?** HTTP clients, `DataSource`, thread pools, schedulers, caches, TLS contexts, or subscribers.

Do not rush to add `@RefreshScope` before knowing which step is missing.

## 3. What Does Core Spring Boot Do with Config Data?

In Spring Boot, the Config Data API processes data such as:

```text
application.yaml
application.properties
application-{profile}.yaml
spring.config.import
spring.config.location
spring.config.additional-location
file:
classpath:
configtree:
```

Properties are loaded into `Environment` as `PropertySource`s. When needed, the `@ConfigurationProperties` Binder performs name relaxation, type conversion, constructor/setter binding, and validation to create beans.

Simplified timeline:

```text
SpringApplication.run(...)
           |
           v
Create and prepare Environment
           |
           v
Load Config Data, profiles, import locations
           |
           v
ApplicationContext / bean definitions
           |
           v
Create and bind @ConfigurationProperties beans
           |
           v
Inject @Value, create business beans
           |
           v
Initialize and open required resources
           |
           v
Application ready to serve
```

This diagram is conceptual: not every bean follows a strict linear order; lazy initialization and dependency graphs can shift exact timing. What is essential to remember is that **configuration is normally loaded and consumed during application context initialization**.

### 3.1. `spring.config.import` is not a file watcher

Example:

```yaml
spring:
  config:
    import: "optional:file:./runtime-overrides.yaml"
```

At startup, Config Data processes this location and adds its data. If `runtime-overrides.yaml` is edited later, core Spring Boot **does not by default watch the file to re-read and rebind**.

Similarly:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

specifies a config tree source loaded during the Config Data lifecycle. Do not assume files under `/run/config/` become live variables continuously synchronized with beans.

`optional:` only handles the case where the location may be absent per that location type's semantics. It does **not** mean "when the location appears or changes, the process auto-refreshes."

### 3.2. `spring.config.location` and location precedence

`spring.config.location` changes the location set searched for Config Data, while `spring.config.additional-location` adds locations to the default set. `spring.config.import` brings imported documents into Config Data processing with precedence rules.

These properties affect **which values are chosen when loading configuration**. They do not implement a runtime watch or rebind mechanism.

### 3.3. A custom dynamic source still differs from Boot core auto-refresh

Spring Framework supports `MutablePropertySources`, and libraries can provide a `PropertySource` that reads data dynamically. Thus, new calls to `Environment.getProperty()` **can see new values** if the underlying property source changed or was replaced.

This does not contradict the fact that **Boot Config Data does not watch files by default**. Those are two separate questions:

```text
Can a PropertySource be queried dynamically?
    Yes, if the PropertySource/application itself does so.

Does Boot automatically watch every YAML/volume and rebind every bean?
    No, not by default.
```

## 4. `Environment`, `@Value`, and `@ConfigurationProperties` Differ on Snapshots

Suppose a bean was created with:

```properties
demo.banner=alpha
```

Later, a special mechanism puts `demo.banner=beta` into `Environment`.

### 4.1. `Environment.getProperty()` at query time

```java
String current = environment.getProperty("demo.banner");
```

If `Environment` now holds the new source with appropriate precedence, a **new** call can return `beta`.

However, if you just edited a YAML file on disk and Boot has not reloaded the `PropertySource`, this call still returns `alpha`.

### 4.2. `@Value` is resolved at injection time

```java
@Component
public class BannerSnapshot {

    private final String banner;

    public BannerSnapshot(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

For a normal singleton, the constructor runs when the bean is created and `banner` is a snapshot `alpha`. `Environment` later gaining `beta` does not re-invoke the constructor.

The same applies to `@Value` on instance fields: injection normally occurs during the bean lifecycle, not as a continuous property subscription.

### 4.3. `@ConfigurationProperties` is a bound object

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String banner,
        Duration requestTimeout
) {}
```

A record is built by the Binder as an object with `final` components. Once bound to `alpha`, that instance does not change to `beta` when the source changes.

Mutable JavaBeans also do not have setter-binding rerun automatically just because a file on disk changed. Mutability makes rebinding possible when **a separate mechanism** triggers it, but does not create a refresh mechanism on its own.

### 4.4. Services may retain a second copy

```java
@Service
public class TimeoutPolicy {

    private final Duration timeout;

    public TimeoutPolicy(DemoProperties props) {
        this.timeout = props.requestTimeout();
    }

    public Duration getTimeout() {
        return timeout;
    }
}
```

Even if a config bean is updated by a custom mechanism, `TimeoutPolicy` still holds the `timeout` copied at construction. That is why "refreshing a property source" and "applying it across all business logic" are two different commitments.

### 4.5. Comparison table

| Access point | When process freshly starts | When `Environment` is manually updated | When only an external YAML file is edited |
| --- | --- | --- | --- |
| New `environment.getProperty()` | Selected value | Can see new value | Does not see new value by default |
| `@Value` injected into singleton | Startup snapshot | Does not auto-reinject | Does not auto-reinject |
| `@ConfigurationProperties` record | Bound instance | Does not auto-create new instance | Does not auto-create new instance |
| Mutable `@ConfigurationProperties` POJO | Bound instance | Does not auto-rebind without a trigger | Does not auto-rebind |
| HTTP client/pool built from config | Resource running with initial config | Does not auto-recreate | Does not auto-recreate |

Cases using Spring Cloud scopes/rebinders/custom lifecycles behave differently, but you must explicitly account for the **specific additional mechanism** in play.

## 5. Lab A: Runnable Plain Spring Boot Application

Lab goals are to demonstrate:

1. Boot reads an external file outside the JAR at startup.
2. `Environment`, `@Value`, and a config record initially agree on the same value.
3. Editing the file while the process runs does **not** auto-reload it.
4. Restarting the process makes configuration process again.
5. No Spring Cloud is added, avoiding confusion about core Boot behavior.

The project uses the Spring Boot web starter solely to keep the process alive and expose an endpoint returning non-sensitive values. **The web starter does not provide refresh.**

### 5.1. Directory structure

```text
boot-refresh-boundary/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── runtime-overrides.yaml             # local file created during testing
└── src/
    ├── main/
    │   ├── java/dev/example/refresh/
    │   │   ├── RefreshBoundaryApplication.java
    │   │   ├── DemoProperties.java
    │   │   ├── BannerSnapshot.java
    │   │   └── StateController.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/refresh/
            ├── BindingTest.java
            └── EnvironmentMutationTest.java
```

Generate a skeleton from Spring Initializr with Java 21, Gradle, and Spring Boot 3.3.x, adding Web, Actuator, and Test. `gradlew`/`gradlew.bat` come from the project's Gradle Wrapper.

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'boot-refresh-boundary'
```

### 5.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

There is no Spring Cloud dependency at all. `spring-boot-starter-actuator` only provides standard supported endpoints/observability when configured. **It does not add Spring Cloud Context's `/actuator/refresh`.**

### 5.4. `DemoProperties.java`

```java
package dev.example.refresh;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String banner,
        Duration requestTimeout
) {}
```

The record has no setters. This is a clear example of a config snapshot created via constructor binding.

### 5.5. `BannerSnapshot.java`

```java
package dev.example.refresh;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class BannerSnapshot {

    private final String banner;

    public BannerSnapshot(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

The `banner` value is resolved when the bean instance is constructed. There is no listener or scheduler here.

### 5.6. `RefreshBoundaryApplication.java`

```java
package dev.example.refresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RefreshBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RefreshBoundaryApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` lets Boot register and bind `DemoProperties` via the configuration properties mechanism. Do not annotate a constructor-bound record with `@Component`.

### 5.7. `StateController.java`

```java
package dev.example.refresh;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StateController {

    private final Environment environment;
    private final DemoProperties properties;
    private final BannerSnapshot snapshot;

    public StateController(
            Environment environment,
            DemoProperties properties,
            BannerSnapshot snapshot) {
        this.environment = environment;
        this.properties = properties;
        this.snapshot = snapshot;
    }

    @GetMapping("/state")
    public Map<String, Object> state() {
        return Map.of(
                "environment", environment.getProperty(
                        "demo.banner", "<missing>"),
                "configRecord", properties.banner(),
                "valueInjected", snapshot.banner(),
                "timeout", properties.requestTimeout().toString());
    }
}
```

The endpoint returns four **non-sensitive** values. It allows no writes, does not expose the full `Environment`, and uses no real secrets. Both `DemoProperties` and `BannerSnapshot` were constructed before the endpoint responds.

**Note:** `Map.of` requires non-`null` values in this example. The configuration below always supplies `demo.banner` and `demo.request-timeout`; in production applications, add validation/fallbacks for required fields.

### 5.8. `application.yaml`

```yaml
server:
  address: 127.0.0.1
  port: 8089

spring:
  config:
    import: "optional:file:./runtime-overrides.yaml"

demo:
  banner: "from-base-file"
  request-timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

We bind the web server to loopback `127.0.0.1` so the lab is not exposed to the whole network. `runtime-overrides.yaml` is an **external Config Data file outside the classpath**, imported at startup. While it does not yet exist, `optional:` lets the app start using the base file when missing locations are permitted.

### 5.9. Running the baseline configuration

From the project root, **before creating** `runtime-overrides.yaml`:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

In another terminal:

```bash
curl http://127.0.0.1:8089/state
```

PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8089/state'
```

Expected JSON output equivalent to:

```json
{
  "environment": "from-base-file",
  "configRecord": "from-base-file",
  "valueInjected": "from-base-file",
  "timeout": "PT2S"
}
```

JSON key ordering does not matter. What matters is confirming that **all three ways of reading configuration** report the same banner from initialization.

## 6. Lab B: File Is Imported, Yet Editing the File Does Not Auto-Refresh

Stop the application first, then create:

`runtime-overrides.yaml`:

```yaml
demo:
  banner: "external-v1"
  request-timeout: 500ms
```

Start the application again. Expect `/state` to return:

```json
{
  "environment": "external-v1",
  "configRecord": "external-v1",
  "valueInjected": "external-v1",
  "timeout": "PT0.5S"
}
```

Now **without stopping the application**, edit that external file to:

```yaml
demo:
  banner: "external-v2"
  request-timeout: 100ms
```

Call again:

```bash
curl http://127.0.0.1:8089/state
```

In a Boot-only setup with no separate reload tool, the output normally remains:

```json
{
  "environment": "external-v1",
  "configRecord": "external-v1",
  "valueInjected": "external-v1",
  "timeout": "PT0.5S"
}
```

Why?

- `application.yaml` and `runtime-overrides.yaml` were read when the process started.
- The corresponding `PropertySource` holds the loaded data.
- There is no default file watcher auto-reloading YAML.
- No rebinding or bean reconstruction was triggered.
- `Duration` inside the record is an object from the initial bind.

Once you stop and **restart** the process, Boot loads the external file again; then expect:

```json
{
  "environment": "external-v2",
  "configRecord": "external-v2",
  "valueInjected": "external-v2",
  "timeout": "PT0.1S"
}
```

This is the crucial distinction between **being able to change configuration between two runs** and **automatic updates within a single run**.

### 6.1. Why does the imported file beat the base file?

In the example, the imported document from `runtime-overrides.yaml` has precedence allowing it to provide `demo.*` keys and replace values in the importing document. Yet precedence only answers **which value is chosen at import time**.

Even with higher precedence, an imported file does not automatically become a watched data stream.

### 6.2. What if editing a file makes the IDE restart automatically?

Your development setup may be using Spring Boot DevTools or IDE automation. If the process actually **restarts**, it reads the new file. That is different from an in-process refresh without a restart.

When doing this lab, disable DevTools or omit it from dependencies; `build.gradle` above intentionally omits DevTools. Check process logs to verify whether a restart occurred instead of mistakenly concluding Boot core hot-reloads.

## 7. Lab C: Mutating `Environment` in Memory While Beans Keep Old Snapshots

A subtler case: suppose **`Environment` itself changed**, without triggering a rebinding mechanism.

Spring Framework provides `ConfigurableEnvironment` and `MutablePropertySources`. We can write a test adding a `MapPropertySource` with higher priority than existing sources. This is an **intentional in-memory operation**, not Boot watching files.

Create `src/test/java/dev/example/refresh/EnvironmentMutationTest.java`:

```java
package dev.example.refresh;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

@SpringBootTest(properties = {
        "demo.banner=test-original",
        "demo.request-timeout=2s"
})
class EnvironmentMutationTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    DemoProperties properties;

    @Autowired
    BannerSnapshot snapshot;

    @Test
    void changingEnvironmentDoesNotRecreateExistingBeans() {
        assertEquals("test-original", properties.banner());
        assertEquals("test-original", snapshot.banner());

        MutablePropertySources sources =
                environment.getPropertySources();

        MapPropertySource manual = new MapPropertySource(
                "lab-manual-override",
                Map.of("demo.banner", "changed-in-memory"));

        sources.addFirst(manual);

        try {
            // New Environment calls see the new property source.
            assertEquals(
                    "changed-in-memory",
                    environment.getProperty("demo.banner"));

            // Both existing beans are not automatically rebound/reinjected.
            assertEquals("test-original", properties.banner());
            assertEquals("test-original", snapshot.banner());
        } finally {
            sources.remove("lab-manual-override");
        }
    }
}
```

Run:

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

The test is expected to pass, showing:

```text
Environment.getProperty("demo.banner") = changed-in-memory

DemoProperties.banner()                = test-original
BannerSnapshot.banner()                = test-original
```

This is **direct proof** that changing the value visible in `Environment` does not automatically update every existing bean.

### 7.1. Why does the test clean up in `finally`?

Spring Boot Test caches and reuses compatible `ApplicationContext` instances across tests. If a test leaves a high-precedence `PropertySource` behind, subsequent tests can read the wrong values.

That is why the sample runs:

```java
sources.remove("lab-manual-override");
```

in `finally`. In a multi-threaded system, mutating `MutablePropertySources` while serving requests requires concurrency and lifecycle controls. **Do not turn this debugging technique into a production config-write endpoint.**

### 7.2. Does modifying a `PropertySource` emit an event?

In Boot-only, adding a `MapPropertySource` **does not automatically emit an event to rebind all beans**. You can build your own event/listener system or deliberately recreate beans, but that is a custom application-managed mechanism, not a default Boot guarantee.

Spring Cloud has dedicated events and rebinders. Do not take this test example, fire an arbitrary event, and assume every resource updates safely.

### 7.3. Verifying baseline values with a separate test

Create `src/test/java/dev/example/refresh/BindingTest.java`:

```java
package dev.example.refresh;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.banner=from-test",
        "demo.request-timeout=750ms"
})
class BindingTest {

    @Autowired
    DemoProperties settings;

    @Autowired
    BannerSnapshot snapshot;

    @Test
    void bindsAtContextCreation() {
        assertEquals("from-test", settings.banner());
        assertEquals(Duration.ofMillis(750),
                settings.requestTimeout());
        assertEquals("from-test", snapshot.banner());
    }
}
```

This test verifies *startup binding*, while `EnvironmentMutationTest` verifies *snapshots do not auto-update after in-memory changes*. Both tests complement each other.

## 8. Docker and Kubernetes: An Updated Source Does Not Mean Updated Beans

In modern deployments, ConfigMaps, Secrets, and mounted files often create the impression that configuration is "live" because it sits outside the container image. However, distinguish **how containers receive values**.

### 8.1. Container environment variables

Docker Compose example:

```yaml
services:
  demo:
    image: example/demo:1.0
    environment:
      DEMO_BANNER: "from-container-env"
```

Environment values are passed **when the process/container is created**. Editing `compose.yaml` or a Kubernetes Deployment manifest does not automatically change environment variables in a running JVM process. Typically the container/pod must be recreated via your deployment workflow.

Spring Boot receives `DEMO_BANNER` as a property source at startup. There is no built-in mechanism to know that an external YAML outside Kubernetes was edited while the pod/process remained unchanged.

### 8.2. ConfigMap volumes

Kubernetes can update some ConfigMap volume contents inside a running pod via kubelet propagation. However:

```text
ConfigMap object updated
     |
     v
File in pod may update after a delay
     |
     v
Boot Config Data already loaded file earlier
     |
     v
Old bean still holds snapshot
```

The new file arriving on disk is **one step**, not the final outcome. When mounting via `subPath`, certain volume updates are **not even reflected automatically** as they are with directory mounts.

### 8.3. Kubernetes Secret volumes

Similarly, updated/remounted secrets do not force `@Value`, `@ConfigurationProperties`, or connection pools inside the JVM to change automatically.

For secrets:

- If rotating passwords, ensure clients receive and apply the new credential.
- If rotating secrets, handle existing connections, sessions, and tokens.
- If secrets are delivered via env vars instead of files, processes normally require a restart.
- If using an operator, CSI driver, or agent, understand **the exact update mechanics and cadence of that integration**.

### 8.4. Spring Boot config tree

Suppose a file:

```text
/run/config/demo.banner
```

has content:

```text
hello
```

`application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

Boot reads the file as property `demo.banner` at startup. If kubelet or a sidecar changes the file content to `goodbye` while the process runs, Boot core **does not automatically rescan the config tree and rebind all beans**.

Replacing `configtree:` with a remote import also does not guarantee live refresh; you must check what the remote integration does and how updates are triggered.

## 9. Spring Boot DevTools Is Not a Production Refresh Mechanism

Spring Boot DevTools is for **development**. Under supported conditions, classpath file changes trigger an **automatic restart** of the application. DevTools can also support LiveReload for web UIs.

Key differences:

| Criterion | DevTools restart | Spring Cloud refresh | Rolling restart |
| --- | --- | --- | --- |
| Goal | Local development | Refresh a subset of config/beans at runtime | Deploy new version or configuration |
| Process/ApplicationContext | Recreated per DevTools restart mechanism | Usually keeps process and partially refreshes | Creates new process/pod |
| Monitors production mounted files? | No guarantee | Depends on provider/watch | Coordinated by CD/Kubernetes |
| Applies to all beans/resources? | Reinitializes app within DevTools scope | No | Recreates entire process state |
| Suitable as production strategy? | No | Possible when designed and secured | Usually suitable for critical changes |

When learning about refresh, **do not take DevTools restarting on file edits as evidence that Boot core supports hot rebinding**.

## 10. The Spring Cloud Boundary: What Components Does It Add?

Spring Cloud is not a single "flag" that enables automatic updates. Depending on dependencies, it provides:

- **Spring Cloud Config Client**: reads configuration from Config Server.
- **Spring Cloud Context**: refresh primitives such as `@RefreshScope`, `ContextRefresher`, Environment change events, and rebinding for eligible beans.
- **Spring Cloud Actuator refresh endpoint**: an administrative trigger when installed and appropriately exposed.
- **Spring Cloud Bus**: broadcasts refresh messages across multiple instances over a message broker.
- **Spring Cloud Consul Config**: reads KV from Consul; offers Config Watch to detect changes per configuration.
- **Spring Cloud Vault**: reads secrets from Vault with lease/lifecycle mechanics; secret renewal does not mean every bean refreshes safely.

These modules **are not a single product** and are not necessarily added together.

Diagram:

```text
Config Server / Consul KV / Vault / Other
                     |
             provider integration
                     |
                  Config Data
                     |
                 Environment
                     |
              change detection?
                     |
             refresh trigger/event
                     |
         +-----------+------------+
         |                        |
   rebind some              @RefreshScope targets
@ConfigurationProperties         |
         |                        |
         +-----------+------------+
                     |
               Application beans
                     |
         resource lifecycle still needs handling
```

The word "some" is crucial: never expect a refresh trigger to safely swap every resource regardless of structure or Java types.

## 11. What Is `EnvironmentChangeEvent`?

In Spring Cloud Context, `EnvironmentChangeEvent` is an event signaling that certain `Environment` keys changed or need processing in the integration flow. Spring Cloud mechanisms can listen to this event to drive rebinding and update supported configuration components.

However, there are three common misconceptions:

1. **The event is not itself a data source.** Property sources must be reloaded or replaced before expecting new values.
2. **The event does not replace every bean.** Some bean/config styles do not support standard rebinding.
3. **The event does not recreate business resources.** JDBC pools, schedulers, WebSocket connections, or caching client libraries require dedicated policies.

In the Boot-only lab, replacing a `MapPropertySource` does not fire a Spring Cloud event (because Spring Cloud is not present). Even when a provider emits the event, verify which listeners handle it and which beans actually update.

### 11.1. Detecting changed keys differs from successful rebinding

An event may list changed keys:

```text
demo.banner
demo.request-timeout
```

Yet a bean may not be recreated, a field may keep its old value, or a resource holder that copied the timeout may continue using `2s`.

When debugging, log **the value at the source**, **the value in `Environment`**, **the bean value**, and **the actual downstream resource value** at each step. Seeing "refresh completed" in logs does not confirm business logic switched over.

## 12. `@RefreshScope`: Refreshing Target Beans, Not Mutating Every Field

Spring Cloud Context provides:

```java
import org.springframework.cloud.context.config.annotation.RefreshScope;
```

A bean annotated with `@RefreshScope` is typically accessed through a proxy. When the refresh scope cache is invalidated, the target can be recreated on the next access.

Example in an app with Spring Cloud Context:

```java
package dev.example.refresh;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RefreshableBanner {

    private final String banner;

    public RefreshableBanner(
            @Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String currentBanner() {
        return banner;
    }
}
```

If `Environment` has loaded the new value **and** refresh is triggered through a supported mechanism, a new target of the bean is created, rerunning the constructor and picking up the new banner.

Accurate mental model:

```text
Before refresh:
  proxy -> target#1("alpha")

After updating Environment + invalidating scope:
  proxy -> target#2("beta") when recreated on demand
```

This is not writing into a `final` field on the old target. It is **swapping the target behind the scope/proxy**.

### 12.1. Why not put `@RefreshScope` on every bean?

A bean may:

- Hold I/O resources that must be closed and recreated.
- Have many dependencies holding direct references.
- Have methods executing long-running requests.
- Hold locks, mutable state, or queues.
- Use external sessions, tokens, or connection pools.
- Have side effects in constructors/`@PostConstruct`.
- Have its lifecycle managed by another framework.

Refreshing a bean mid-request requires analyzing concurrency, lifecycle, and rollback. A simple bean holding a banner refreshes easily; a pool serving active transactions is far more complex.

### 12.2. `@RefreshScope` does not fetch new values itself

If the source has not changed or property sources have not reloaded, recreating the target still picks up **the old value**. `@RefreshScope` handles target recreation, not every provider/watch/precedence step.

### 12.3. Do not treat constructor-bound records like JavaBeans with setters

A `@ConfigurationProperties` record is an immutable snapshot. Spring Cloud Context has limitations with `@ConfigurationProperties` records and certain constructor-bound objects in refresh/rebinding flows. Do not assume you can put `@RefreshScope` on a record and have every dependent swap values safely.

When dynamic values are needed, you can:

- Use a `@RefreshScope` service bean supporting target recreation from `@Value`.
- Build a holder/reference with explicit atomic swapping and validation.
- Use a dynamic source read at request time for data that allows it.
- Use a rolling restart when many resources must change together.

Pick a verifiable mechanism rather than treating immutable Java types like magic.

## 13. `/actuator/refresh`: Administrative Trigger, Not Plain Boot Actuator

A Boot-only application adding:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

gets Boot's Actuator endpoints per dependencies and config. That **does not create Spring Cloud's refresh endpoint**.

With Spring Cloud Context and the refresh endpoint present, an application can expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

Then an authorized caller can trigger:

```bash
curl -X POST http://127.0.0.1:8089/actuator/refresh
```

**Never expose this endpoint publicly in production.** It can alter runtime behavior and must be protected like a sensitive operational action: authentication, authorization, mTLS or private networking, auditing, rate limiting, and approval workflows.

### 13.1. The endpoint existing does not prove required data refreshed

`POST /actuator/refresh` is a **trigger**. For it to take real effect:

- A provider or mechanism must update `PropertySource`s.
- New data must be read successfully.
- Beans needing updates must participate in a supported refresh mechanism.
- Business beans/resources must not keep using stale snapshots.
- Final values and service behavior must be tested.

If a refresh request returns a response, do not infer that all HTTP clients were reconfigured or all replicas changed values simultaneously.

### 13.2. Do not confuse with `/actuator/env`

Actuator `env` is for observing the environment as permitted by configuration, and may allow administrative property updates when specific settings are enabled. It is not the same as reloading Config Data imports or recreating immutable beans.

Because `env`/`configprops` can involve secrets and system structure, **never open them to the Internet** just for debugging. Prefer allowlist logging, health checks, and properly authorized tooling.

## 14. Lab D: Adding Spring Cloud Config to the Application

After confirming Boot-only limits, create **a separate practice branch** from the initial lab. Keep `DemoProperties`, `BannerSnapshot`, and `StateController` to observe differences when a remote provider is introduced.

### 14.1. Dependencies and versions

In Gradle, use the Spring Cloud BOM matching Boot 3.3.x. Lab example:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

Add to existing `dependencies`:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-config'
```

Do not pin a separate starter version if the BOM already manages it. If your project uses a different Boot/Cloud version, check the official compatibility matrix before copying this BOM.

### 14.2. Importing from Config Server

Use:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "configserver:http://localhost:8888"
```

Config Client looks up configuration for the application/profile/label on Config Server. Prerequisites:

- Spring Cloud Config Client dependency present.
- Config Server running at the configured endpoint.
- Matching configuration in the server's backend.
- Client has access permissions and appropriate TLS/auth for the environment.
- App defines a fail-fast/optional strategy matching config criticality.

For local testing when the server might not be running, you can use:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

`optional:` lets the app handle an absent server per Config Client semantics; it is not a promise that authentication failures, invalid syntax, or binding errors are ignored.

### 14.3. Config Server and Config Client are two separate processes

Topology:

```text
Git/native config repository
           |
           v
    Config Server :8888
           |
      HTTP(S) Config
           |
      demo-client app
           |
    Environment + Beans
```

Config Server distributes configuration, while the Client loads values into `Environment`. When a Git file changes, the change must be seen by Config Server and then picked up by clients via an appropriate mechanism.

A new Git commit **is not automatically equivalent** to running client instances applying the new value.

### 14.4. A local Config Server using the native backend

A separate project with:

```groovy
implementation 'org.springframework.cloud:spring-cloud-config-server'
```

and main class:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Server `application.yaml`:

```yaml
server:
  port: 8888

spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations: "file:./config-repo"
```

Create:

```text
config-repo/
  demo-client.yaml
```

with:

```yaml
demo:
  banner: "remote-alpha"
  request-timeout: 800ms
```

Run Config Server from the working directory containing `config-repo`. Verify:

```bash
curl http://localhost:8888/demo-client/default
```

This setup is for a local lab. Production requires authentication, TLS, high availability, and a managed backend.

### 14.5. Observing the Client from startup

When the client starts and reads remote properties, `/state` can reflect:

```json
{
  "environment": "remote-alpha",
  "configRecord": "remote-alpha",
  "valueInjected": "remote-alpha",
  "timeout": "PT0.8S"
}
```

Exact values depend on competing sources like CLI, env, and local files. To keep tests clear, **avoid setting the same key in multiple sources** until the import is verified.

### 14.6. Editing remote config while the client is running

Update the server config:

```yaml
demo:
  banner: "remote-beta"
  request-timeout: 100ms
```

Config Server serving the new content does not prove the client reloaded it. Check:

1. Which revision/value does GET on the Config Server endpoint return?
2. Did the client `Environment` reload from the server?
3. Was the `@RefreshScope` target invalidated/recreated?
4. Does the `DemoProperties` record still hold the old snapshot?
5. Are business resources using the new timeout?

This is the right checklist to separate **remote distribution** from **runtime refresh**.

## 15. Lab E: Using `@RefreshScope` to Observe the Difference

In the branch with Spring Cloud, add `RefreshableBanner` from Section 12.

Add a dedicated endpoint in the controller:

```java
@GetMapping("/refreshable-banner")
public Map<String, String> refreshableBanner(
        RefreshableBanner current) {
    return Map.of("banner", current.currentBanner());
}
```

In this example, `RefreshableBanner` is supplied by Spring via its appropriate scope/proxy. Alternatively, you can simply inject `RefreshableBanner` into the controller constructor and call its method inside the handler.

After modifying the remote source, invoke the configured and secured refresh trigger:

```bash
curl -X POST http://127.0.0.1:8089/actuator/refresh
```

If the provider updated `Environment` and `@RefreshScope` invalidated the target, a new request to `/refreshable-banner` can return `remote-beta`. Meanwhile:

- Singleton `BannerSnapshot` (not in refresh scope) may still return `remote-alpha`.
- The old constructor-bound `DemoProperties` record is not automatically replaced by default.
- `StateController` may still hold a reference to the old config record bean.
- A pool/client already created with timeout `800ms` may still hold the old configuration.

The lesson is that **refresh is scoped**, not "all fields across the JVM change at once."

### 15.1. `@RefreshScope` requires a supporting dependency

Do not add:

```java
import org.springframework.cloud.context.config.annotation.RefreshScope;
```

to a Boot-only build without Spring Cloud Context. It is not a core Spring Boot annotation.

Likewise, do not expect `/actuator/refresh` to work if you only added `spring-boot-starter-actuator` without the relevant Spring Cloud pieces.

### 15.2. Mutable `@ConfigurationProperties` and rebinding

Spring Cloud Context includes mechanisms that can rebind certain `@ConfigurationProperties` beans when `Environment` changes. Exact behavior depends on bean type, registration, property sources, and version. A JavaBean with setters may update under the right setup, though you must test it rather than generalizing to all beans.

With records, constructor binding, or beans that already used config values to construct resources, **rebinding does not equal recreating the resource**. Maintain clear lifecycle boundaries.

## 16. Spring Cloud Bus: One Trigger to Many Instances

In a system with multiple replicas:

```text
Config Server
      |
   service-1 (3 instances)
   service-2 (5 instances)
```

Calling `/actuator/refresh` on **one** instance does not automatically refresh the remaining instances.

Spring Cloud Bus can use a message broker to broadcast events to multiple instances per configuration, such as RabbitMQ or Kafka via the corresponding starter/transport.

Diagram:

```text
Config changed
      |
      v
Bus event / broker
      |
      +--> instance A -> refresh
      +--> instance B -> refresh
      +--> instance C -> refresh
      +--> instance D -> refresh
```

This is a **fan-out**, not a distributed transaction:

- An instance may be offline.
- A subscriber may process the event late.
- A refresh may fail if the new data is invalid.
- Concurrent requests may hit instances running different versions.
- Broker availability does not prove beans/resources finished updating.

For strong consistency guarantees, use rollout policies, version gates, readiness checks, and further testing; some requirements are better served by a rolling restart than bulk live refresh.

## 17. Consul Config Watch: Watching KV Changes Does Not Update Every Bean

Spring Cloud Consul Config can load KV entries into `Environment` via an import such as:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "consul:localhost:8500"
```

With the Spring Cloud Consul Config dependency and Consul configured, deployments can enable **Config Watch** to poll KV prefix changes and emit refresh events to the application context.

Typical flow:

```text
Consul KV changes key
      |
      v
Consul Watch detects
      |
      v
Spring Cloud refresh event
      |
      v
Property sources / beans processed per supported mechanism
      |
      v
App uses new value? -> must verify
```

Distinguish Consul Config from Consul Discovery. Discovery registers and locates services; it does not refresh a timeout setting loaded from KV.

### 17.1. When watch emits an event yet nothing changes

Check:

- Is the key under the exact prefix/path/profile and format Consul Config reads?
- Is Watch running and permitted to access Consul KV?
- Are there network or ACL issues?
- Does `Environment` hold the new value?
- Was the bean rebound or recreated by scope?
- Does a service hold a `final` field or copy of the old value?

Do not rush to add a second polling loop inside the application to "fix" watch before identifying which link failed.

### 17.2. Watch can create operational pressure

If many keys change rapidly, uncontrolled refresh events can trigger frequent resource recreation or request spikes. Add debouncing/backoff, rollout coordination, and rate limits when needed. Just because a config store supports watch does not mean every parameter should be live-updated.

## 18. Vault and Secret Rotation: A New Value Is Not Enough

HashiCorp Vault offers secret engines, authentication, policies, token/lease lifecycles, auditing, and dynamic credentials. Spring Cloud Vault helps applications read secrets as property sources.

Example import:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "vault://"
```

Separate four concepts:

1. **Secret source changes:** Vault stores a new secret version or issues a new credential.
2. **Client fetches new secret:** the integration/agent/CSI mechanism actually reads the new value.
3. **Beans using secret update:** `Environment`, injected beans, or config holders change.
4. **Resources apply new secret:** database pools, TLS contexts, HTTP clients, and open connections handle lifecycle transitions.

For example, a `DataSource` built at startup with the old password does not replace all open connections in the pool merely because a property source changed when Vault issued a new credential.

### 18.1. Static KV secrets vs. dynamic credentials

- For static KV secrets, editing a key in Vault does not mean services reload automatically.
- For leased dynamic secrets, renewal and revocation follow Vault's and the integration's lifecycle.
- For database credentials, handle pool recreation, active transactions, credential expiration, and readiness.

A sound rotation plan often requires provisioning new resources first, draining/shifting traffic, closing old resources, and revoking the old secret only after transition completes per policy.

### 18.2. Do not use refresh to mask security failures

If Vault returns 403 or a required secret is missing, never silently fall back to a dummy password in production so the app keeps serving requests. Using `optional:` or local fallbacks must be decided by data criticality.

Never log raw secrets, expose full `Environment` for debugging, or leave `/actuator/refresh` publicly accessible.

## 19. Restart and Rolling Deployment: Why Is It Often Easier to Control?

When configuration governs:

- database URLs or pool credentials,
- TLS certificates/keys,
- thread pool sizing,
- HTTP client connection timeouts,
- topic/queue subscriptions,
- feature flags with major schema impact,
- major discovery endpoints or routes,
- security policies,

**recreating the application or pod** in a controlled rollout is often simpler and safer than trying to mutate every resource in place.

A rolling deployment typically follows:

```text
Config revision N+1 approved
        |
        v
CI/CD applies new image/config/pod template
        |
        v
New pod starts and binds config N+1
        |
        v
Readiness check + smoke tests
        |
        v
Shift traffic to new pod
        |
        v
Terminate pod N via graceful shutdown
```

Details such as `maxSurge`, `maxUnavailable`, `PodDisruptionBudget`, and readiness probes depend on infrastructure; core Spring Boot does not impose a Kubernetes rollout strategy.

**Advantages:** a fresh process runs through the complete lifecycle of Config Data, Binder, validation, and resource initialization. You do not have to guarantee every old object can safely mutate in place.

**Trade-offs:** startup cost, sufficient spare capacity, and handling failed rollouts. Not every tiny tweak demands a restart, yet restarts remain the easiest baseline to prove correct for critical configuration.

### 19.1. ConfigMap changes do not guarantee a rollout

Kubernetes does not deploy new pods for every ConfigMap data change; behavior depends on your deployment controller/automation. Many teams include a checksum annotation in the pod template or use a dedicated operator/reloader to trigger rollouts on approved config changes.

Verify **whether the pod template changed**, **whether new pods were created**, and **whether the new app reads the intended revision**.

### 19.2. Rollback is not just rolling back configuration

When config N+1 changes protocols or external schemas, reverting to N requires checking compatibility. For revoked secrets, rolling back to an old credential is not necessarily valid. Design rollbacks to cover dependencies and external state, not just restoring YAML.

## 20. Consistency Across Multiple Replicas

A service with three instances:

```text
app-A -> timeout=1s
app-B -> timeout=2s
app-C -> timeout=2s
```

During a refresh or rollout, requests can hit instances running **different configuration versions**. That may be acceptable for a display banner, yet unsafe for a security policy or write path.

Choose a consistency model:

- **Eventual consistency:** tolerate lag and monitor until all instances converge.
- **Version-gated rollout:** new instances only receive traffic once at the target config revision.
- **Coordinated restart:** roll in groups/waves to minimize mixed versions.
- **Compatibility-contracted feature flags:** two versions are explicitly safe to coexist during a window.
- **Global disable/kill switch:** define propagation delay and fallback behavior if the source is unreachable.

Even a system "with Bus" still needs monitoring for **which instance received which revision and whether it actually applied it**.

### 20.1. Tagging configuration with a revision

In normal configuration, you can add a non-sensitive key:

```yaml
demo:
  config-revision: "r42"
```

The application reports `config-revision` in controlled health/readiness or diagnostic output. After changes, verify each instance reports the expected revision.

Do not treat this revision field as standalone proof that all secondary resources were recreated. It is only an indicator matching source/bound-bean version.

### 20.2. Refresh can fail partially

A provider may load new config while recreating a bean fails validation or networking. During that window, the system can sit in an inconsistent state. Answer:

- Do new requests continue to be accepted?
- Does the instance flip `readiness=false`?
- Can beans/resources be rolled back?
- Does it keep using an old secret after it was revoked?
- Do logs/metrics distinguish each phase?
- Is there an alert when an instance fails to converge?

A restart strategy generally turns most errors into **startup failures** before serving traffic, though rollouts still require management.

## 21. What Happens with a Dynamically Readable PropertySource?

A custom `PropertySource` can override:

```java
public Object getProperty(String name) {
    return remoteStore.get(name);
}
```

With this, `Environment.getProperty(name)` can query the remote store and get fresh values per call. However:

- I/O on the request path introduces latency and outage coupling.
- Caching and TTLs mean updates are not necessarily "instant."
- Already-injected `@Value` fields still hold snapshots.
- Already-bound `@ConfigurationProperties` still keep old state without rebinding.
- Resources built from properties are still not recreated.
- A key can change mid-operation between two reads, breaking per-operation consistency.

**Dynamic lookups do not replace coordinated refresh.** When runtime updates are truly needed, consider versioned snapshots + atomic swaps or refresh scope, and manage consistency across related keys.

### 21.1. Do not write a custom file watcher just to invoke arbitrary setters

An error-prone approach:

```text
WatchService sees YAML change
      |
      v
Parse new file
      |
      v
Call setters on each singleton
```

This can cause:

- Some beans running with new config while others use old config.
- Partial updates while other threads are reading.
- Undefined update ordering.
- No whole-snapshot validation.
- Underlying resources not recreated.
- Race conditions between the watcher and shutdown/restart.
- Hard-to-reverse partial failures partway through setter calls.

If building custom reconfiguration, design immutable snapshot objects, pre-publish validation, atomic switching, thread safety, and resource lifecycles. Do not turn a simple watch feature into a source of production instability.

## 22. When to Use `Environment.getProperty()` Directly for Dynamic Data?

Reading config per request is not always wrong, depending on the kind of data.

Relatively suitable:

- A non-sensitive display flag with acceptable latency tolerance.
- An option affecting only the current request's logic.
- A small config key queried from a holder with clear caching and versioning.

Unsuitable without dedicated design:

- Credentials used to open connections.
- Base URL endpoints tied to pooled clients.
- TLS contexts/certificates serving active connections.
- Live thread pool or connection pool sizes.
- Security constraints requiring the whole request to see one revision.
- Multiple keys that must change together transactionally.

A pragmatic rule: **if a value is used to build a resource, refresh must explain how that resource is rebuilt**. If it is only evaluated per request, dynamic reading may suffice provided consistency and failure modes are designed.

## 23. Comparing Technical Options

| Solution | Source change detection | Environment update | Bean recreation/rebinding | Business resources | Complexity |
| --- | --- | --- | --- | --- | --- |
| Boot-only file + manual restart | Operator | When new process starts | Fresh context/beans | Fresh resources | Low |
| Boot-only `configtree:` + rolling restart | Deployment workflow | When new pod starts | Fresh context/beans | Fresh resources | Medium |
| Boot DevTools | Dev file changes | On app restart | On restart | On restart | Dev-only |
| Custom dynamic `PropertySource` | Custom code | Potentially immediate on lookup | Not by default | Not by default | Depends on design |
| Spring Cloud Config Client | Remote fetch at startup/refresh | Per provider/trigger | Selected beans via Cloud Context | Must verify | Medium |
| Cloud `@RefreshScope` | Requires refresh trigger | Requires reloaded source | Target beans can recreate | Not general automatically | Medium-high |
| Spring Cloud Bus | Event fan-out | Via instance refresh logic | Via Cloud mechanics | Must verify | Higher |
| Consul Config Watch | Polls KV | Via integration/refresh | Per refresh support | Must verify | Medium-high |
| Vault secret rotation | Secret engine/lease | Depends on client/agent | Not synced across all beans by default | Strongly needs custom lifecycle | High |
| Kubernetes rolling deployment | Controller/automation | New process | New beans | New resources | Clear, with capacity cost |

Do not pick a technology solely from the "source change detection" column. Evaluate **application mechanics and post-update state** too.

## 24. Debugging at the Right Layer Instead of Guessing

Suppose an operator reports:

> "I edited the ConfigMap, yet the HTTP client timeout has not changed."

A diagnostic workflow:

**Step 1 — Verify the ConfigMap/Secret revision.** Right namespace, key, and deployment?

**Step 2 — Verify the pod received the data.** If mounted as a file, did the file inside the pod change? Is `subPath` used? If env var, was the pod recreated?

**Step 3 — Verify new vs. old process.** Uptime, PID, pod UID, deployment revision, and startup logs.

**Step 4 — Verify whether Boot re-read the file.** Was there a restart, reloader, or provider integration?

**Step 5 — Verify `Environment`.** An authorized internal tool can inspect safe keys without exposing secrets.

**Step 6 — Verify beans.** Did `@Value`, config records/POJOs receive the new value?

**Step 7 — Verify client resources.** Are HTTP clients, connection pools, or retry policies holding old objects?

**Step 8 — Verify all replicas.** One new pod does not mean the entire Deployment converged.

**Step 9 — Review rollout/restart.** If the setting cannot refresh safely in place, create fresh resources/processes per procedure.

Every earlier step can succeed individually while the final behavior still fails if one step is skipped.

### 24.1. What to log when debugging configuration?

Safe to log:

```text
configRevision=r42
configLoaded=true
activeProfiles=prod
refreshAttempted=true
refreshApplied=false
reason=validation_error
```

Do not log:

```text
datasourcePassword=<secret>
vaultToken=<token>
allEnvironmentProperties=<all values>
```

For sensitive properties, report only presence/absence, versions, or carefully designed non-leaky identifiers—never raw values.

## 25. Difference Between Config Refresh and Route/Service Discovery Refresh

A service name can be resolved dynamically via DNS or service discovery. That mechanism is not `@ConfigurationProperties` refresh.

Examples:

- Kubernetes Service DNS updates endpoints per pod.
- Consul Discovery updates service instance lists by health.
- Load balancer clients update target lists.
- Application settings like `http.connect-timeout` can still remain startup snapshots.

**Discovery** solves "which instance to call?". **Configuration refresh** solves "how to read and apply new properties?". **Secret rotation** solves "which identities/credentials remain valid?". The three paths cooperate, yet are not interchangeable.

Do not bring in a discovery system just to change a timeout, and do not assume Config Server handles live endpoint discovery.

## 26. Special Case: Refresh and GraalVM Native Image / AOT

Spring Boot supports AOT/native images, yet dynamic reconfiguration techniques relying on proxies, reflection, and runtime target swapping must be evaluated against the Spring Cloud documentation for your exact version.

Spring Cloud Context notes limitations around `RefreshScope` support in AOT/native and documents disabling refresh in corresponding native configs, for example:

```properties
spring.cloud.refresh.enabled=false
```

Do not assume a Boot-only project compiled to a native image has hot reload merely because the runtime or Config Data can read config files.

If a project needs both native executables and runtime-changing settings, evaluate:

- Dynamic source reads per request via an appropriate API.
- A snapshot holder with an explicit update mechanism.
- Restart/rolling deployments.
- Specific AOT/native support of your chosen provider.

Do not rely on a Cloud refresh annotation seen in JVM mode without testing it in native mode.

## 27. Choosing an Architecture by Goal

### 27.1. Small applications with infrequent config changes

```text
Boot Config Data + env/file + CI/CD restart
```

Strong choice for simplicity: each process has a clear snapshot, and startup validation runs completely.

### 27.2. Microservices needing centralized, Git-versioned config

```text
Spring Cloud Config Server + Config Client
```

Add a well-governed Config Server with clients using `configserver:`. Refresh vs. restart decisions **still remain separate**. Do not assume Config Server pushes notifications to every client whenever Git changes.

### 27.3. Organizations using Consul KV needing watch

```text
Spring Cloud Consul Config + Watch + refresh policy
```

Suitable when the team understands Consul KV contexts, ACLs, formats, and events. Confirm beans and resources update after events.

### 27.4. Secrets with leases, rotation, or strict access controls

```text
Vault + Spring Cloud Vault or Vault Agent/CSI
```

Delivering secrets into Boot is only part of the problem; authentication, lease renewal, resource recreation, and auditing are the rest.

### 27.5. Kubernetes with strong deployment pipelines

```text
ConfigMap/Secret/CSI volume
          |
          v
Boot Config Data
          |
          v
Automated rolling restart by config revision
```

Often more reliable than introducing remote config infrastructure just to tweak rarely changed settings. If continuous live updates are needed, add a dedicated dynamic mechanism suited to those config types.

## 28. Testing When Deploying Refresh or Rolling Restarts

A test suite should cover multiple layers.

### 28.1. Unit tests

Instantiate config records directly and test service logic against concrete values:

```java
DemoProperties props = new DemoProperties(
        "unit", Duration.ofMillis(750));
```

No Spring Cloud or external provider is needed to verify business logic.

### 28.2. Spring Boot binding tests

Use `@SpringBootTest(properties = ...)` to confirm source overrides and type conversion produce the right target types. `BindingTest` earlier demonstrated this.

### 28.3. Confirm no auto-refresh on file edits alone

Run a Boot-only process with an imported file, edit the file, and query `/state`. The test should assert the process does not change on its own. After restart, assert the new value. This tests a **behavioral boundary**, not a defect.

### 28.4. Simulate Environment changing while beans retain snapshots

`EnvironmentMutationTest` verifies an in-memory change does not re-invoke already-executed constructors. This is a very helpful test whenever someone claims a dynamic `Environment` makes every field dynamic.

### 28.5. Cloud refresh tests

In the separate Cloud branch:

1. Start Config Server and Client.
2. Verify the client receives revision N.
3. Update the remote value to revision N+1.
4. Trigger refresh via a secured administrative path.
5. Verify `Environment` sees N+1.
6. Verify eligible `@RefreshScope` beans read N+1.
7. Verify unscoped snapshot beans keep old values unless a separate rebind mechanism exists.
8. Verify runtime resources recreate when required.
9. Test validation failure when new remote config is invalid.
10. Test rollback and multi-instance convergence.

### 28.6. Chaos/failure tests

Test:

- Config Server unavailable at client startup.
- Config Server unavailable during refresh.
- Consul watch loses connection.
- Vault returns 401/403 or missing secret path.
- Volume file updating while app has not restarted.
- One replica on the new revision while remaining replicas hold the old revision.
- New config fails conversion/validation.
- Long-lived HTTP client connections spanning a timeout change.
- New secret provisioned before old credential is revoked.
- Unauthorized calls to `/actuator/refresh`.

Passing tests must confirm **application policy** (fail-start, retry, fallback, readiness, rollout), not merely that an endpoint returned HTTP 200.

## 29. Common Misconceptions

### "Externalized Configuration means dynamic configuration"

No. Externalized describes **where and how values are supplied**, not file watching or live refreshing.

### "Editing `application.yaml` makes `Environment.getProperty()` return the new value"

No. If Config Data holds a loaded snapshot, editing the file does not update the source automatically. `Environment` only sees updates if some mechanism actually reloads or replaces that source.

### "If `Environment` has the new value, `@Value` updates too"

Not on an already-injected singleton bean. Bean recreation or an appropriate refresh mechanism is needed.

### "Records are immutable, so the record is the limitation"

Records make snapshots explicit; they are not why Boot lacks a file watcher. Mutable POJOs also do not auto-rebind without a trigger. With records, replacing the object must be designed instead of mutating fields.

### "DevTools already supports production refresh"

No. DevTools focuses on restarts and local developer experience, not production rollout policies.

### "Boot Actuator includes `/actuator/refresh` out of the box"

No. That endpoint comes from Spring Cloud Context/Actuator with matching dependencies and exposure; plain Boot Actuator does not include it.

### "`@RefreshScope` pulls new values from Git automatically"

No. The scope allows target beans to recreate after a trigger; property sources must be fetched/updated by a provider mechanism.

### "Cloud Config Server broadcasts every commit to all clients automatically"

Not by default. Webhooks, Bus, refresh triggers, restarts, or orchestration are needed.

### "Consul Watch emitted an event, so all running services updated immediately"

No. The event is only one link in the chain; beans and resources must still support updating.

### "Vault rotating a password makes connection pools switch passwords automatically"

Not by default. Pools, connections, leases, and identities require proper lifecycle management.

### "Editing a ConfigMap restarts all pods"

Not by default in every workflow. Controllers, automation, or pod-template changes are required.

### "A successful `/actuator/refresh` proves the entire cluster is consistent"

No. The endpoint normally affects one instance; fan-out and cluster convergence are separate concerns.

### "Writing a custom file watcher is enough"

No. You still need validation, atomicity, bean scoping, resource recreation, concurrency safety, rollback, and security.

### "To be safe, just add `optional:`"

No. `optional:` mainly decides whether a missing location is tolerated. Required secrets or invalid security configs may need fail-fast behavior.

## 30. Hands-On Exercises

### Exercise A — Predict snapshots

A Boot-only app has:

```properties
demo.banner=one
```

After startup, a singleton has `@Value("${demo.banner}")` injected. You edit the file to `two` without restarting.

Predict:

1. What does the file on disk contain?
2. Is `Environment` guaranteed to see `two`?
3. Does the `@Value` field change?
4. What happens after restart?

Explain each layer instead of giving a one-word "no."

### Exercise B — Mutating `MapPropertySource`

In a test, you add:

```java
new MapPropertySource(
        "override",
        Map.of("demo.banner", "beta"))
```

with high precedence. Explain why `Environment.getProperty()` returns `beta` while a previously bound record bean still returns `alpha`.

### Exercise C — Classify refresh mechanisms

Classify each action:

- DevTools auto-restarting when classpath changes.
- Config Server serving configuration from Git.
- Consul Watch emitting a `RefreshEvent`.
- Cloud `@RefreshScope` creating a new target bean.
- Spring Cloud Bus broadcasting events over a broker.
- Kubernetes performing a rolling pod restart.
- Vault issuing a new credential.

Which are *source*, *detection*, *trigger*, *bean recreation*, or *deployment*? One technology may span multiple roles without covering all of them.

### Exercise D — HTTP client timeout

A service builds an HTTP client with timeout `2s` in its constructor. Config Server later changes it to `500ms`. What conditions are needed so new requests actually use the new timeout?

Propose two solutions: one using controlled refresh/resource recreation, and one using rolling deployment.

### Exercise E — Secret rotation

Vault issues a new password, yet the connection pool keeps using the old password. Describe detecting the change, creating a new pool, shifting traffic, and closing the old pool. When can the old credential be revoked?

### Exercise F — Consul Watch

KV has `demo.banner=beta`, watch logged a refresh event, yet the endpoint still returns `alpha`. List at least four places to check to pinpoint the cause.

### Exercise G — Kubernetes ConfigMap

A ConfigMap is updated and the mounted file changed. The Pod UID did not change, and the app uses Boot-only Config Data. Why does `/state` still return the old value? How would you design a rollout trigger?

### Exercise H — Multi-instance consistency

Out of 5 replicas, 2 received config N+1 while 3 still run N. Compare the risks for a UI banner vs. a security policy. What version observation, readiness, or rollout controls do you need?

### Exercise I — `/actuator/refresh`

Suppose a team wants to expose the refresh endpoint publicly so external pipelines can call it easily. Explain the risks, proper auth/network policies, and post-request verification checks.

### Exercise J — Native image

A Spring Boot application uses a native image and the team wants to add `@RefreshScope` from an old JVM guide. How will you verify Spring Cloud's AOT/native limitations, and what alternatives exist if unsupported?

### Exercise K — Design a configuration classification table

Classify:

```text
ui.banner
api.connect-timeout
security.allowed-origins
database.password
scheduling.pool-size
feature.discount-enabled
tls.private-key
```

For each key, decide:

1. Is eventual consistency acceptable?
2. What validation is required?
3. Which beans/resources hold snapshots?
4. Choose refresh or restart?
5. Are auditing and special secret handling needed?

### Exercise L — Write a "no auto-refresh" test

Starting from `EnvironmentMutationTest`, add a check for `DemoProperties.requestTimeout()`. Put `demo.request-timeout=100ms` into `MapPropertySource` and prove `Environment` reads the new raw value while `DemoProperties` retains the previous `Duration`.

## 31. Self-Check Questions

**1.** Does Externalized Configuration automatically mean hot-reload?

**2.** Does core Spring Boot automatically watch all `application.yaml` and `configtree:` files at runtime?

**3.** When adding a high-precedence `MapPropertySource`, can `Environment.getProperty()` return the new value while an injected `@Value` still holds the old value?

**4.** Why does a `@ConfigurationProperties` record not auto-update an already-bound component?

**5.** Does a mutable class with setters auto-rebind simply because a file outside the JAR changed?

**6.** Is Spring Boot DevTools restart the same mechanism as Cloud `@RefreshScope`?

**7.** Does plain Boot Actuator include `/actuator/refresh` out of the box?

**8.** Does `@RefreshScope` mutate `final` fields on an old target bean, or usually create a new target after invalidation?

**9.** Does Spring Cloud Config Server automatically push every Git commit to all running clients?

**10.** Does Consul Config Watch handle all resource lifecycles?

**11.** Does Vault issuing a new credential force open JDBC connections to swap credentials automatically?

**12.** Does a Kubernetes ConfigMap update automatically restart all pods?

**13.** Can a ConfigMap file mount updating while the Boot app keeps old config be completely normal behavior?

**14.** Why does a single `/actuator/refresh` response not prove cluster consistency?

**15.** When is a rolling restart usually easier to verify than dynamic refresh?

**16.** Why is a custom file watcher alone insufficient to update all singletons?

**17.** When a new secret exists yet a resource still uses the old secret, which layer is missing?

**18.** Should `/actuator/env` and `/actuator/refresh` be exposed unauthenticated for debugging?

**19.** For native images, must Spring Cloud refresh limitations be checked separately?

**20.** What test can prove modifying `Environment` does not auto-reinject beans?

### Answer key

1. No; externalized separates sources from code.
2. Not by default.
3. Yes, because lookup timing differs from injection timing.
4. Records are snapshot instances with final components, and there is no auto-recreation trigger.
5. No; a refresh/rebind mechanism is needed.
6. No; restart and refresh scope are different mechanisms.
7. No; the corresponding Spring Cloud pieces are needed.
8. Usually creates a new target via scope/proxy.
9. Not by default; dedicated triggers/distribution are needed.
10. No; watches/events do not necessarily recreate resources.
11. No.
12. Not by default across all workflows.
13. Yes, because Boot does not auto-reload Config Data from mounts.
14. Replicas and beans/resources can sit on different revisions.
15. When changing credentials, clients/pools, TLS, thread pools, or critical schemas.
16. Lacks validation, atomicity, lifecycle, consistency, and concurrency handling.
17. Resource/application-layer reconfiguration.
18. No; these are administrative endpoints and sensitive configuration data.
19. Yes, according to the Spring Cloud version in use.
20. A test adding a `MapPropertySource` and comparing `Environment` against old beans.

## 32. Production Readiness Checklist

Before shipping a "runtime config refresh" feature:

- [ ] Clearly define which properties are permitted to change dynamically.
- [ ] Know which source owns each key and what precedence applies.
- [ ] Distinguish startup Config Data snapshots from dynamic provider sources.
- [ ] Define an explicit trigger: manual API, watch, bus, operator, deployment controller.
- [ ] Handle reloading property sources and network failures.
- [ ] Know which beans sit in refresh scope or support rebinding.
- [ ] Never assume records/constructor-bound configs auto-refresh.
- [ ] Know which resources must be recreated, closed, or drained.
- [ ] Validate the entire new snapshot before applying it.
- [ ] Have rollback when a partial update fails.
- [ ] Define a consistency policy across replicas.
- [ ] Track config revisions per instance using non-sensitive data.
- [ ] Implement rate limiting/debouncing to prevent refresh storms.
- [ ] Configure retry/backoff and fail-fast rules per config type.
- [ ] Define readiness policy when new secrets or resources are invalid.
- [ ] Secure Actuator refresh/env/configprops with auth, network isolation, and auditing.
- [ ] Never log passwords, tokens, or raw secrets in logs, metrics, or responses.
- [ ] Include tests proving Boot-only does not auto-refresh files.
- [ ] Include tests showing `Environment` updated while old beans stay unchanged.
- [ ] Include integration tests covering remote providers and real beans/resources.
- [ ] Include chaos tests for config source outages or invalid data.
- [ ] Test rollout/restart with ConfigMap/Secret and `subPath` cases.
- [ ] Verify AOT/native behavior if deploying native images.
- [ ] Maintain runbooks documenting refresh, restart, rollback, and ownership rules.

## 33. Summary

One sentence to remember:

> **Plain Spring Boot reads and binds configuration very well, but does not by default detect source file changes and refresh all running beans and resources. Spring Cloud can add reloading, events, and refresh scopes, yet each application must still design update scope, lifecycle, and consistency.**

The complete path:

```text
Configuration source
(file/YAML/Consul/Config Server/Vault/Secret volume)
                    |
                    v
           Change detected?
                    |
                    v
         PropertySource reloaded?
                    |
                    v
         Environment sees new value?
                    |
                    v
    Bean rebound or recreated correctly?
                    |
                    v
    Resource/client/pool uses new value?
                    |
                    v
    All replicas converged safely?
```

When genuine dynamic updates are not required, **a rolling restart with versioned configuration, startup checks, and readiness probes** is usually simpler, easier to control, and easier to audit. When live refresh is needed, treat it as an operational feature with an explicit contract, not a side effect of putting YAML outside the JAR.

### Official References

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, `PropertySource`, profiles, Config Data, config trees, and binding.
2. [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): automatic restarts in development environments.
3. [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Bootstrap, `@RefreshScope`, `EnvironmentChangeEvent`, refresh endpoints, and limitations.
4. [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data `configserver:` import, fail-fast, and Config Client.
5. [Spring Cloud Config — Server](https://docs.spring.io/spring-cloud-config/reference/server.html): Config Server model and remote repositories.
6. [Spring Cloud Bus](https://docs.spring.io/spring-cloud-bus/reference/): broadcasting events across service instances.
7. [Spring Cloud Consul — Distributed Configuration](https://docs.spring.io/spring-cloud-consul/reference/config.html): Consul KV, watch, and `RefreshEvent`.
8. [Spring Cloud Vault — Reference](https://docs.spring.io/spring-cloud-vault/reference/): secret backends, property sources, and lease lifecycles.
9. [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): env/volumes and ConfigMap updates.
10. [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret usage patterns and security boundaries.
11. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): administrative endpoint exposure and security.
