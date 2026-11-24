# Distinguishing Startup Reading from File Changes After the Application Is Running

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Configuration Deployment

## 1. The Problem: Edited Configuration on Disk, Why Does the Application Still Use the Old Value?

Suppose a Spring Boot application runs with `./config/application.yml` outside the JAR:

~~~yaml
catalog:
  client:
    timeout: 3s
    enabled: true
~~~

An operator wants to increase the timeout because the Catalog service is responding slowly. They edit the file:

~~~yaml
catalog:
  client:
    timeout: 10s
    enabled: true
~~~

The file saves successfully; reopening it in an editor shows `10s`. Yet new requests to the Spring Boot service still time out after about 3 seconds. This is **not necessarily a bug** in Spring Boot or the filesystem.

Many applications read Config Data at **startup**, construct `Environment`, bind values into `@ConfigurationProperties`, and use them to build HTTP clients, connection pools, or beans. Editing an external file afterward **does not automatically make Spring Boot reload the file, rebind beans, and reconfigure already-created resources**.

This lesson focuses on distinguishing three events that are often conflated:

1. **The file on the filesystem changes.**
2. **Effective property sources in the process are re-read/reloaded.**
3. **Active components actually use the new value.**

Completing step 1 does not prove step 2 or step 3 has happened.

### Learning objectives

After this lesson, you will:

- List the steps from loading Config Data to active beans at startup.
- Distinguish current file contents, values in Spring `Environment`, values in `@ConfigurationProperties`, and the state of already-constructed clients.
- Understand why `application.yml`, `spring.config.import`, config trees, and `@PropertySource` files do not provide hot reload by default.
- Distinguish changing a file on the classpath/JAR from changing a file outside the JAR.
- Identify the effects of updating ConfigMap/Secret mounts, environment variables, and `subPath` files in Kubernetes.
- Choose between restart/rolling rollout and dynamic refresh when deployment needs truly demand it.
- Design verification, runbooks, readiness, and rollback for a configuration change.
- Avoid treating "the file was edited" as proof that the application applied the configuration.

## 2. Spring Boot's Basic Configuration Lifecycle

In a typical startup, the process can be pictured as follows:

~~~text
T0 — Before running the JVM
  - application.yml/application.properties exist
  - environment variables and CLI arguments are configured
  - ConfigMap/Secret or externalized files are provisioned
                   |
                   v
T1 — SpringApplication prepares Environment
  - reads config data from effective locations
  - evaluates profiles, imports, documents, precedence
                   |
                   v
T2 — Initialize ApplicationContext
  - creates beans
  - binds @ConfigurationProperties
  - resolves @Value
  - type conversion/validation
                   |
                   v
T3 — Initialize runtime resources
  - HTTP clients, DataSource, pools, schedulers
  - cache structures or business policies
                   |
                   v
T4 — Application serves traffic
                   |
                   v
T5 — Someone edits application.yml outside the JAR
  - bytes of the file on disk change
  - DOES NOT automatically return to T1, T2, T3
~~~

This is a high-level diagram: hooks in Spring have detailed ordering by framework and bean. However, the operational issue sits at the boundary where **T5 does not automatically re-trigger the configuration loading and reconstruction cycle**.

### 2.1. Externalized configuration does not mean hot reload

"Externalized" means configuration values are separated from application code and can be supplied from sources outside the artifact. It enables running the exact same JAR in dev, staging, and production with different values.

It **does not mean** that editing any external source causes every running process to see the change immediately. How configuration is supplied and how configuration is updated are **two independent architectural decisions**.

### 2.2. A Spring bean can be a snapshot of configuration

With Spring Boot 3 and Java 17+:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        boolean enabled
) {}
~~~

Once the `CatalogClientProperties` bean is bound, the record is an object whose components are already set. Editing the YAML file does not change the record's fields from `3s` to `10s`.

Even a mutable JavaBean:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public class MutableClientProperties {
    private Duration timeout;

    public Duration getTimeout() { return timeout; }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

does not automatically rerun setters just because a file changed. A mutable object **has the capability** to be updated; that does not mean the framework installed a file watcher/rebind pipeline.

### 2.3. Values already copied into a client are even harder to update

Example of configuring an HTTP client once:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfig {

    @Bean
    HttpClient catalogHttpClient(CatalogClientProperties props) {
        return HttpClient.newBuilder()
                .connectTimeout(props.timeout())
                .build();
    }
}
~~~

Assuming the required Java imports are declared, when `HttpClient` is built, the timeout is passed to the builder. Later, even if some mechanism updates `CatalogClientProperties`, you cannot assume an already-built `HttpClient` instance changes automatically. You must check the client's contract and how beans/resources are recreated.

Therefore, there are **at least four places** to inspect: the filesystem, `Environment`, properties beans, and client resources.

## 3. Quick Comparison Table of Four States

| Component | What does it hold? | Auto-updates when `application.yml` is edited? |
| --- | --- | --- |
| External file outside JAR | Bytes/contents stored on disk | **Yes**, if the edit actually succeeded |
| Spring `Environment` with loaded Config Data | `PropertySource`s created during loading | **Not by default** |
| Singleton `@ConfigurationProperties` | Bound values | **Not by default** |
| `@Value` on a singleton bean field | Value injected at bean creation | **Not by default** |
| Already-created client or connection pool | Internal config parameters, connections, caches | **Not by default** |
| Reading file directly per call with `Files.readString` | Bytes at the moment of that read | Can see changes when re-opening/reading the file |
| Client using a secret/config supplier with real refresh | Values governed by supplier/cache | Depends on implementation and refresh policy |
| Bean under a dedicated refresh mechanism | Bean instance after refresh | Only when refresh is triggered and properly applied |

"Not by default" is the phrasing to keep. An application may integrate Spring Cloud, a file watcher, or a custom reload library; those mechanisms change the behavior. However, **core Spring Boot externalized configuration does not guarantee hot reload for all files and beans**.

## 4. Case 1: application.yml on the Classpath or Inside the JAR

A project:

~~~text
catalog-service/
├── src/main/resources/application.yml
└── src/main/java/...
~~~

When packaged as a Spring Boot executable JAR, this resource normally lives inside the artifact. On a normal run, Boot reads it from the classpath during Config Data loading.

If a developer edits `src/main/resources/application.yml` locally after the JAR has already been built and launched:

- The new source file does not update the contents inside the old JAR.
- The running process does not automatically pick up the edited source file.
- Restarting the **same old JAR** still uses the contents packaged inside that JAR, not the edited source file.
- To change embedded config contents, you typically rebuild/redeploy a new artifact or supply an externalized source.

### 4.1. Do not directly modify an archive in use by a running process

Editing files inside a running JAR is not a reliable configuration update strategy. The archive may be open by the classloader; modifying it can corrupt the artifact or cause unpredictable behavior.

Good practice is treating the artifact as **immutable** and separating per-environment values into external Config Data, environment variables, or a secret manager. This avoids rebuilding the same code just to change a timeout.

### 4.2. DevTools is not a production runtime rule

Spring Boot DevTools has a restart mechanism in development when the classpath changes. However, this is a **development convenience**, not a production hot-reload guarantee.

A DevTools restart makes the application re-read configuration because **the context is recreated**, not as proof that beans mutate in place inside a non-restarting process. Never design production operations around IDE/DevTools behavior.

## 5. Case 2: application.yml Outside the JAR

Suppose:

~~~text
/deploy/catalog/
├── catalog.jar
└── config/
    └── application.yml
~~~

File:

~~~yaml
catalog:
  client:
    timeout: 3s
~~~

Run from working directory `/deploy/catalog`:

~~~bash
java -jar catalog.jar
~~~

Spring Boot has default config locations outside the classpath, including relative locations like `file:./` and `file:./config/`. When the working directory and config data rules match, `./config/application.yml` is loaded at startup.

### 5.1. An externalized file is easier to edit, yet does not live-reload automatically

Letting operators edit `./config/application.yml` without rebuilding the JAR is a major benefit. However, singleton beans created before the edit still keep their old values.

Example timeline:

~~~text
09:00:00  JVM starts, Config Data reads timeout=3s
09:00:01  Binder creates CatalogClientProperties(timeout=3s)
09:00:02  HTTP client is built with corresponding timeout
10:15:00  Operator edits file to timeout=10s
10:15:01  File on disk is 10s
10:15:02  Bean in JVM is still 3s
10:15:03  Client can still be using 3s
10:20:00  JVM is restarted with current configuration
10:20:01  New bean receives 10s unless a higher-precedence source overrides it
~~~

Do not assume every file update triggers a restart. Treat **restart/reload** as a separate deployment step with verification.

### 5.2. File paths depend on the working directory

`file:./config/application.yml` is normally resolved relative to the process's working directory, not automatically relative to the directory containing the JAR.

A service launched via systemd, Docker, or an IDE can have a different working directory. If you edit `/deploy/catalog/config/application.yml` while the JVM is looking in `/app/config/application.yml`, even a restart will not help if the active location did not change.

Document absolute paths or clarify the working directory in runbooks. Do not randomly edit multiple files with the same name to guess "which file takes effect."

### 5.3. Precedence issues

An external file outside the JAR may be loaded yet fail to win if a higher-precedence source provides the same key.

Example:

~~~yaml
# ./config/application.yml
catalog:
  client:
    timeout: 10s
~~~

Yet runtime passes:

~~~bash
java -jar catalog.jar --catalog.client.timeout=2s
~~~

In standard setups, command-line properties beat Config Data. Even after a restart, the final value can still be `2s`.

Therefore, when seeing "edited file yet value did not change," distinguish two causes:

1. **Not reloaded** after editing.
2. **Reloaded, yet overridden by another source**.

## 6. Case 3: Adding Files via spring.config.import

Example `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/catalog-extra.yml"

catalog:
  client:
    timeout: 3s
~~~

Imported file:

~~~yaml
catalog:
  client:
    timeout: 10s
~~~

Spring Boot Config Data processes `spring.config.import` **during configuration preparation**, so the imported file can contribute properties and override according to Boot's ordering rules.

However, when `catalog-extra.yml` changes while the application is running, merely being imported does not make Boot automatically re-read it and rebind all beans.

### 6.1. optional: does not mean auto-refresh

The `optional:` prefix means that when a location does not exist, Config Data can skip the missing-location error. It does **not** mean:

- Wait for the file to appear and auto-load it later.
- Auto-reload when the file is modified.
- Ignore malformed YAML syntax errors.
- Make a missing required property valid.
- Update already-created beans.

If the file contains required data, use appropriate validation or startup contracts.

### 6.2. Importing multiple sources requires understanding ordering

When multiple imported files or location groups exist, precedence determines the final property. After a restart, still confirm which source is taking effect. A file being re-read yet overridden by a higher-precedence file can create the illusion of "restarted yet nothing changed."

Never infer from a file's modification timestamp that it has higher precedence. Config Data follows its own rules for locations, imports, profiles, and document order.

## 7. Case 4: configtree and Mounted Files

Spring Boot supports config tree imports, commonly used when each property lives in its own file.

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Example tree:

~~~text
/run/config/
├── catalog.client.timeout
├── catalog.client.enabled
└── partner.api.token
~~~

Each **filename** represents a property name; **file content** is the property value. If `catalog.client.timeout` contains `3s`, the Binder receives `catalog.client.timeout=3s`.

### 7.1. Updating the file does not auto-update the record

An orchestrator may update `catalog.client.timeout` to `10s`. If the `CatalogClientProperties` record was already created at startup, it does not update automatically.

Relationship:

~~~text
File /run/config/catalog.client.timeout
            |
            | read when Config Data loads
            v
Environment / Config Data PropertySource
            |
            | bound into object
            v
CatalogClientProperties(timeout=3s)
            |
            | supplies value to client
            v
HttpClient(timeout=3s)
~~~

Editing the file clearly affects only **the first node**. Subsequent stages require a designed update mechanism or a restart.

### 7.2. File contents and re-reading

If you want to read a file directly on each request, you can use `Files.readString`; if you want periodic reads, you can use a scheduler or file watcher. However, that is **custom application logic**, not an automatic feature of config tree imports.

For files containing secrets, check encoding, trailing newlines, access permissions, and atomic replacement mechanics. Do not blindly apply `trim()` to every secret value if whitespace could be part of a valid credential.

## 8. @PropertySource Also Has Its Own Load Timing

A Spring Framework configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-settings.properties")
class LegacySettingsConfiguration {}
~~~

adds `.properties` resources to `Environment` when the configuration class is processed during `ApplicationContext` refresh.

When the file is edited afterward, the annotation is not reprocessed automatically, and beans using `@Value` do not re-resolve values.

### 8.1. @PropertySource does not replace Config Data

- `@PropertySource` suits `.properties` resources by default.
- YAML is not supported by it in the same way Boot loads `application.yml` without a custom factory.
- Multi-document files and profile activation require Config Data.
- `@PropertySource` is added relatively late compared to settings like `logging.*` or `spring.main.*`.

Choosing a custom YAML `PropertySourceFactory` does not solve dynamic reload either. The factory changes how the resource is parsed when invoked; it does not turn the annotation into a file watcher.

### 8.2. Config Data locations and startup timing

Properties such as `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are used very early to decide where to load files from. If you put them in a resource added later via `@PropertySource`, do not expect Boot to redo file discovery.

This is another example showing that **when configuration is read** matters just as much as the values themselves.

## 9. Is Spring Environment Always Immutable?

No. Spring's `ConfigurableEnvironment` and `MutablePropertySources` allow code to modify the `PropertySource` list or add values at runtime.

For example, a program can add:

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.ConfigurableEnvironment;

public void addOverride(ConfigurableEnvironment env) {
    env.getPropertySources().addFirst(
            new MapPropertySource(
                    "runtime-override",
                    Map.of("catalog.client.timeout", "10s")
            )
    );
}
~~~

After this operation, a new `environment.getProperty("catalog.client.timeout")` call can see `10s` due to the higher-precedence source.

However:

- The previously bound singleton `CatalogClientProperties` can still hold `3s`.
- Fields injected with `@Value` during bean creation do not auto-update.
- An `HttpClient` already built with `3s` is not rebuilt automatically.
- Mutating `Environment` arbitrarily at runtime can cause **different components to read two different versions of configuration**.

**Changing `Environment` does not mean changing the whole system.** If you do so, you must design rebind/recreation workflows and consistency guarantees.

### 9.1. Avoid manual "hot patching" of Environment in production

If an operator invokes a custom endpoint to add a `MapPropertySource` into one JVM, it only affects that instance and not other replicas. Restarting the process loses the in-memory override.

If you need to change configuration across multiple instances, use a properly distributed, verified, and secured management mechanism instead of expecting individual instances to sync manual patches.

## 10. @ConfigurationProperties Is a Bound Object, Not a File Watcher

Comparison table:

| Usage pattern | Value at initialization | When file changes | To apply new values |
| --- | --- | --- | --- |
| Constructor-bound record | Final components | Does not auto-change | Create/bind a new bean |
| JavaBean `@ConfigurationProperties` | Setters/field values | Does not auto-call setters | Rebind or reinitialize |
| `@Value` on singleton | Injected value | Does not auto-reinject | Recreate bean or refresh mechanism |
| `HttpClient` builder | Client config copied | Does not auto-rebuild | Build a new client |
| HikariCP pool | Connection settings and pool state | Does not auto-update everything | Restart/recreate or tested management API |
| Scheduler created with initial cron | Scheduled trigger | Does not auto-reschedule | Re-register trigger/scheduler |
| Code calling `Files.readString` per request | File content at each open | Can see new file | Handle reads and consistency safely |

### 10.1. Immutable records clarify the contract

Record:

~~~java
@ConfigurationProperties(prefix = "reports.export")
public record ExportProperties(
        String directory,
        Duration interval
) {}
~~~

is clearly a snapshot. On a restart, a new record receives values from current sources. This fits the **immutable deployment** model: stable artifact, configuration applied at each startup.

### 10.2. Mutable JavaBeans do not make the system auto-refresh

A class with setters:

~~~java
@ConfigurationProperties(prefix = "reports.export")
public class ExportProperties {
    private Duration interval = Duration.ofMinutes(5);

    public Duration getInterval() { return interval; }
    public void setInterval(Duration interval) {
        this.interval = interval;
    }
}
~~~

still keeps `5m` or the bound value until code or a framework invokes the setter again or creates a new object. Mutable objects do not watch the filesystem on their own.

### 10.3. The configuration object is one layer; the consuming object is another

Even if a properties bean is updated to 10s by a refresh mechanism, an executor or scheduler already built with 3s may still need to be stopped and recreated. Therefore, refresh designs must trace the **value propagation path** from source to every consuming component.

## 11. Why Does Environment Still Have Old Values After Editing a File?

Several causes are possible:

1. The file was not reloaded after editing.
2. The file the operator edited is not at the active config location.
3. The file reloaded, yet the property was overridden by a higher-precedence source.
4. The active profile differs from the edited file.
5. The YAML document has `spring.config.activate.on-profile` that is not active.
6. The file imported via `optional:` did not exist at load time.
7. The new file has the right value, yet the bean still holds an old snapshot.
8. The bean updated, yet a client/cache still uses the old value.
9. Another replica is serving requests and has not been updated.
10. A custom refresh mechanism failed or was never triggered.

### 11.1. Distinguishing using a non-sensitive key

Using test property `catalog.client.timeout`, you can observe:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final Environment environment;
    private final CatalogClientProperties properties;

    public ConfigProbe(
            Environment environment,
            CatalogClientProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Environment timeout = "
                + environment.getProperty("catalog.client.timeout")
        );
        System.out.println(
                "Bound bean timeout = " + properties.timeout()
        );
    }
}
~~~

This check runs once when `ApplicationRunner` executes after startup; it is not a file watcher. Reading these later can yield different results if a separate mechanism updated `Environment` without rebinding the bean.

Use only to observe **non-secret** keys. Never print all properties or entire objects containing tokens/passwords to logs.

### 11.2. Reading the source directly after file changes

A shell command like:

~~~bash
cat ./config/application.yml
~~~

only proves the file's contents at the path the shell reads. It does not prove the Java process uses the same working directory, re-read the file, or lacks a higher-precedence override.

When suspecting paths, check working directory, systemd `WorkingDirectory`, Docker `WORKDIR`, volume mount paths, and `spring.config.location` or `spring.config.additional-location` arguments.

## 12. Kubernetes ConfigMap via Environment Variables

In Kubernetes, an application can receive a ConfigMap as environment variables:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: example/catalog-service:1.0
          env:
            - name: CATALOG_CLIENT_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: catalog-runtime
                  key: timeout
~~~

When Kubernetes creates the container, environment variables are populated from the ConfigMap at creation time. If ConfigMap `catalog-runtime` is updated afterward, **the running container's environment is not updated automatically**.

This does not even depend directly on `@ConfigurationProperties` mutability: even if code tried to re-read env on every request, the process environment still holds the initial value.

### 12.1. New Pods can receive new values

To receive an updated ConfigMap via environment variables, new Pods/containers must be created through the deployment mechanism. In a Deployment, a rolling restart or Pod template change creates new Pods, which receive the current env.

Updating a ConfigMap object **does not always trigger a rollout automatically**. If the manifest references the same ConfigMap name and the Pod template is unchanged, a standard Deployment may keep the old Pods running.

### 12.2. Approved operational command example

In an environment with appropriate permissions and a change plan:

~~~bash
kubectl rollout restart deployment/catalog-service \
  --namespace production

kubectl rollout status deployment/catalog-service \
  --namespace production
~~~

These are operational command examples, not suggestions to run directly in production for experimentation. Check namespace, deployment, and impact before executing.

## 13. Kubernetes ConfigMap/Secret via Volume Mounts

Kubernetes can also mount a ConfigMap or Secret as files:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: example/catalog-service:1.0
          volumeMounts:
            - name: catalog-settings
              mountPath: /app/config
              readOnly: true
      volumes:
        - name: catalog-settings
          configMap:
            name: catalog-config-files
~~~

Suppose the ConfigMap has data key `application.yml`; kubelet makes `/app/config/application.yml` appear inside the Pod.

### 13.1. Volume files can change before the process applies them

With standard ConfigMap/Secret volume mounts, Kubernetes updates volume contents when the object changes via **eventual consistency**, not instant synchronization.

Timeline:

~~~text
10:00  ConfigMap is updated
10:00+ Kubelet observes change after a delay
10:01  File /app/config/application.yml inside Pod may already be updated
10:01  Spring Environment still holds Config Data from startup
10:01  @ConfigurationProperties bean and HTTP client may still use old values
10:05  New Pod is created; Boot reads current file at startup
10:05  New bean uses new value unless overridden by another source
~~~

A file watcher detecting an updated file is **a necessary condition** for file-based hot reload, yet **insufficient** without parsing, validation, rebinding, and client-updating logic.

### 13.2. subPath limitation

When mounting a file with Kubernetes `subPath`, automatic updates of the ConfigMap/Secret volume do not work the same way as standard directory mounts.

Therefore, never design hot reload assuming a `subPath`-mounted file will update when the ConfigMap/Secret object changes. Recreate the Pod/mount or use another tested distribution mechanism.

### 13.3. Secrets differ from ConfigMaps in security, not bean snapshot semantics

Secrets hold sensitive data; ConfigMaps are for non-secret configuration. Yet when both are provided via files at startup, Spring Boot binding into beans still behaves as a snapshot in the same way.

Do not print secrets to logs or run `kubectl get secret -o yaml` carelessly for comparison. Base64 in Kubernetes Secrets is not encryption. Use RBAC, encryption at rest, and a proper secret management system.

## 14. One Config Edit Can Affect Multiple Replicas Differently

Suppose there are four Spring Boot Pods:

~~~text
pod-a: timeout=3s
pod-b: timeout=3s
pod-c: timeout=3s
pod-d: timeout=3s
~~~

If an operator edits a file on only one machine/Pod or refreshes only one process:

~~~text
pod-a: timeout=10s
pod-b: timeout=3s
pod-c: timeout=3s
pod-d: timeout=3s
~~~

The load balancer distributes traffic across multiple configuration versions, creating intermittent errors that are hard to diagnose.

A configuration change plan must answer:

- What is the shared config source?
- Which instances have received the new source?
- Is there rollout or refresh orchestration across all instances?
- Is there a way to confirm every instance runs the same version?
- Is a window where two config versions coexist acceptable?
- If not, what maintenance, drain, or synchronization strategy is needed?

### 14.1. Non-sensitive version ID

You can attach a non-sensitive `config.version` or checksum annotation to deployments to track progress:

~~~yaml
app:
  config-version: "catalog-2026-11-rotation-01"
~~~

Do not treat a version ID as absolute proof that every field bound properly. It is only a marker for tracking rollout, and must be paired with real behavior and source verification.

### 14.2. Do not log secret fingerprints carelessly

If a version ID is tied to a secret, use a non-sensitive identifier provided by the secret manager. Avoid logging hashes of raw tokens/passwords directly: for low-entropy or guessable credentials, fingerprints can increase exposure risk.

## 15. Restart and Rolling Rollout: The Most Predictable Approach

For many Spring Boot applications, a simple and reliable model is **each process instance runs with one deterministic configuration set**. When configuration changes, create new instances to replace old ones.

Process:

~~~text
Prepare new file/env/ConfigMap/Secret
                  |
                  v
Verify format and exact source
                  |
                  v
Start new instance
                  |
                  v
Spring Boot reads new config data
                  |
                  v
Bind/validate beans, initialize clients
                  |
                  v
Readiness check on new instance
                  |
                  v
Shift traffic, drain old instance
                  |
                  v
Stop old instance
                  |
                  v
Verify metrics and complete rollout
~~~

### 15.1. Advantages of restarting

- Provides a clean phase to reload all Config Data.
- Beans are constructed in the defined lifecycle order.
- Connection pools and clients are built fresh from current configuration.
- Bound configuration can be validated before serving traffic.
- Easy to roll back via deployment/revision if the corresponding config source can be restored.
- Avoids partial-refresh states inside a long-lived process.

### 15.2. Trade-offs to manage

- A restart can cause downtime if the service has only a single instance.
- Can lose in-memory state if the application is poorly designed.
- In-flight connections and batch jobs need time to complete.
- Extra capacity is required to run old and new replicas concurrently.
- Restarting all instances simultaneously can spike load on databases or external services.

Therefore, a **safe restart** includes readiness probes, graceful shutdown, a rolling strategy, and capacity planning—not simply `kill -9` and restarting.

## 16. Readiness and Graceful Shutdown During Config Rollouts

In Spring Boot with Actuator configured, health probes can reflect serving readiness. Example YAML:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Illustrative Kubernetes readiness probe:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Only use that path and port if the application actually exposes the endpoint and infrastructure can reach it. Readiness should not blindly depend on every optional dependency such that an external outage takes the entire service out of rotation.

### 16.1. RollingUpdate

A multi-replica Deployment can use:

~~~yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
~~~

This example helps limit losing ready Pods during rollout. It **does not guarantee absolute zero downtime**, as that also depends on replica count, capacity, routing, startup duration, readiness accuracy, and how the server handles shutdown.

### 16.2. Graceful shutdown

When an old instance is asked to stop, it must stop accepting new requests and finish in-flight requests/transactions within allowed limits.

For batch jobs or queue consumers, define policies so messages are neither lost nor invalidly duplicated. Checkpoints, idempotency, retries, and broker ack semantics may be needed.

### 16.3. Readiness should confirm new config took effect on critical functions

A Pod can start up successfully even if an optional integration is not ready. If a timeout was changed to fix a Catalog service issue, merely seeing the health endpoint return 200 does not prove Catalog requests are using the new timeout.

Add safe smoke checks, metrics, and a non-sensitive config version marker when needed.

## 17. Dynamic Refresh: When Should You Consider It?

Some requirements cannot easily tolerate restarts: frequently toggled feature flags, continuously updated routing rules, certain short-lived tokens, or continuously running workers.

In those cases, consider **dynamic refresh**. However, a proper refresh solution requires many steps:

1. Detect that the configuration source changed.
2. Load new contents with the right schema and precedence order.
3. Convert types and validate thoroughly.
4. Decide whether to swap configuration or keep the old version when new values are invalid.
5. Atomically update affected components.
6. Rebuild clients/pools/schedulers if they copied values into internal structures.
7. Synchronize across threads and instances.
8. Record version, metrics, and rollback support.

Plain Spring Boot **does not automatically provide a general mechanism** to hot-reload every `application.yml` and every singleton. You need additional libraries or explicitly designed application code.

### 17.1. Spring Cloud @RefreshScope is not all of Spring Boot

In some Spring Cloud setups, there is a context/bean refresh mechanism such as `@RefreshScope`. However:

- `@RefreshScope` is not a built-in annotation of Spring Boot Core.
- Not every bean belongs to refresh scope.
- Not every client/pool rebuilds when a properties bean changes.
- Immutable configuration properties and library versions can have special behavior.
- Refresh endpoints, if exposed, must be access-controlled.
- A successful refresh on one instance does not guarantee other instances are in sync.

Therefore, do not write "add `@RefreshScope` to auto-reload `application.yml`" as a general rule. Test how sources reload, which beans are recreated, and which values end up in use.

### 17.2. Custom file watchers

A team might use Java's `WatchService` or polling to receive file-change events. That only solves the **change detection** layer.

To actually use the new configuration, you still have to:

- Read a complete file snapshot, avoiding partial reads mid-write.
- Parse in the proper YAML/properties format.
- Resolve precedence against other sources.
- Validate before publishing.
- Swap configuration atomically and notify consumers.
- Protect read permissions and logs, especially for secret files.
- Handle missed events, symlink swaps, or atomic file replacements.

For Kubernetes ConfigMap/Secret volumes, atomic writers may swap files/symlinks rather than modifying bytes at the old inode. A watcher listening only to write events on a fixed file handle can miss updates. Polling/reopening by path and testing in a real environment are usually required.

### 17.3. Do not use @Scheduled to arbitrarily rebind properties

A task reading a file every second and mutating bean properties without synchronization can let threads observe **half-old, half-new** configuration—for example, `timeout` from the new version with `endpoint` from the old version, or a new connection pool paired with an old auth header.

A better approach can be a fully validated immutable config snapshot published atomically via `AtomicReference<ConfigSnapshot>` to consumers that explicitly read the snapshot. This is custom application design, not default `@ConfigurationProperties` binding.

## 18. Example of a Controlled Dynamic Snapshot Design

Suppose only one simple policy needs frequent updates, rather than all Spring Boot application settings.

~~~java
package com.example.routing;

import java.time.Duration;

public record RoutingPolicy(
        boolean enabled,
        Duration timeout
) {
    public RoutingPolicy {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "Routing timeout must be greater than 0");
        }
    }
}
~~~

Snapshot store:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class RoutingPolicyStore {

    private final AtomicReference<RoutingPolicy> current =
            new AtomicReference<>(
                    new RoutingPolicy(true, Duration.ofSeconds(3))
            );

    public RoutingPolicy get() {
        return current.get();
    }

    public void replace(RoutingPolicy next) {
        if (next == null) {
            throw new IllegalArgumentException("Policy must not be null");
        }
        current.set(next);
    }
}
~~~

A component reading `store.get()` per decision sees either the entire old snapshot or the entire new snapshot, never a mix of fields across replacements. However:

- This is only **publishing the snapshot**, not yet the file loader.
- A file reader must parse and validate the new snapshot before calling `replace`.
- If an `HttpClient` was already built with the old timeout, it does not update with the store on its own.
- Multiple replicas must still receive the same version and report status.
- A policy is needed for malformed new files, read errors, or partial update failures.

Dynamic snapshot designs fit when a policy truly changes frequently; for database settings, passwords, or HTTP connection pools, a rolling restart is usually simpler.

## 19. Configuration Changing While Running: Three Behavioral Categories

A practical classification:

### Category A — Startup-only

Examples: datasource URL, database pool password, server port, certain bootstrap logging settings, endpoints used to build clients.

Characteristics:

- Read to construct components.
- Components usually retain values for their entire lifetime.
- Restart/rebuild is the clean path to apply changes.
- Requires rollout and rollback runbooks.

### Category B — Runtime lookup

Example: a service calling `Environment.getProperty(...)` on every use.

Characteristics:

- If a `PropertySource` in `Environment` is **actually** updated, a subsequent lookup can receive the new value.
- If you only edit a YAML file without updating the `PropertySource`, it still gets the old value.
- Can suffer type conversion, consistency, and performance issues if done broadly across many properties.
- Do not treat runtime lookup as a complete dynamic configuration system.

### Category C — Explicit dynamic configuration

Examples: feature flag services, remote config clients, application-specific policy stores with refresh and versioning.

Characteristics:

- Explicit fetch/cache/reload lifecycle.
- Validation, atomic publication, and rollback.
- Can synchronize across replicas.
- Must test concurrent reads and failure modes.
- Increases operational and security cost.

Choose the category per property's needs rather than forcing one approach onto every setting in the application.

## 20. How to Edit Files Safely

Even when a **restart is mandatory**, how files are edited still matters. A malformed YAML file can cause every new instance to fail startup.

### 20.1. Avoid partial reads while a file is being written

If an operator or tool writes directly to an active file, a startup coinciding with the write may read an incomplete file. When appropriate, write to a temporary file, validate, and perform an **atomic replacement** on the same filesystem; understand the semantics of your actual mount and filesystem.

Not every filesystem or mount supports identical rename semantics. When config is managed by Kubernetes, use platform mechanisms instead of editing inside Pods.

### 20.2. Ensure valid YAML

Valid example:

~~~yaml
catalog:
  client:
    enabled: true
    timeout: 10s
~~~

Wrong indentation can produce different keys or parse errors:

~~~yaml
catalog:
  client:
  enabled: true
  timeout: 10s
~~~

Both may be syntactically valid YAML, yet the second has **a different structure than intended**, leaving `catalog.client.enabled` and `catalog.client.timeout` missing.

Therefore, YAML syntax validation alone is not enough; test binding into configuration classes and validation of required keys.

### 20.3. One source can contain multiple documents

`application.yml` supports `---` to separate documents, and `spring.config.activate.on-profile` decides which documents apply based on active profiles.

Example:

~~~yaml
catalog:
  client:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod

catalog:
  client:
    timeout: 10s
~~~

If the `prod` profile is not active, editing the `prod` document may not affect the current restart. Conversely, another active profile or CLI override can still yield a final value different from both documents.

## 21. Startup Validation Is the Guardrail Against Misconfiguration

A typed record:

~~~java
package com.example.catalog.config;

import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "catalog.client")
@Validated
public record CatalogClientProperties(
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

`@NotNull` detects missing values, though it does not guarantee a positive timeout. You can add an invariant:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        boolean enabled
) {
    public CatalogClientProperties {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "catalog.client.timeout must be greater than 0");
        }
    }
}
~~~

These two examples show **two different approaches** to validation; in a real project, pick one unified class and appropriate validator mechanism.

### 21.1. Startup validation and rollout

When deploying new configuration:

1. A new configuration source exists.
2. Start a new instance so Boot loads the source.
3. Bind and validate before serving traffic.
4. If a value is invalid, the new instance's startup fails.
5. Old instances, if still running and healthy, continue serving under the rolling strategy.

This is a major advantage of rolling restarts over mutating a live singleton: the new version passes through a **checkpoint** before receiving traffic.

### 21.2. Do not use dangerous defaults

Defaults like `spring.datasource.password=test123` or a sandbox endpoint in production can mask missing configuration errors. Only use defaults when they are genuinely safe and business-correct.

For required properties, fail fast if missing instead of silently running with unsuitable values.

## 22. Testing: Proving When Configuration Is Read

### 22.1. Testing bound properties

You can use `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void timeoutComesFromStartupProperties() {
        runner.withPropertyValues(
                "catalog.client.timeout=3s",
                "catalog.client.enabled=true"
        ).run(context -> {
            CatalogClientProperties props =
                    context.getBean(CatalogClientProperties.class);

            assertThat(props.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
        });
    }
}
~~~

Assuming `Duration` is imported and `CatalogClientProperties` matches, this test verifies the Binder with test properties; it does **not** prove an external Config Data file loads or hot-reloads.

### 22.2. Testing the real Config Data pipeline

To test `application.yml`, profile activation, or `spring.config.import`, use a test context that runs the real Config Data pipeline, such as `@SpringBootTest` with matching config files and active profiles.

Do not merely parse YAML yourself and claim the app loaded it. A parser unit test and a Boot startup integration test verify different things.

### 22.3. Testing "edit file while JVM is running"

A controlled integration test:

1. Create a config file at a temporary location with `timeout=3s`.
2. Start a Spring Boot context loading that location.
3. Read the bean and assert `3s`.
4. Edit the file to `10s` **without restarting the context**.
5. Read the bean again; it should normally remain `3s` if there is no refresh.
6. Stop the context and start a new context against that same location.
7. Read the new bean; expect `10s` if loaded and unoverridden.

This test directly separates **filesystem updates** from **lifecycle rebinding**.

### 22.4. Testing the configured client

Add a test where a client is initialized with timeout 3s, then change the source to 10s. Do not only assert properties in `Environment`; verify the client actually uses the new policy after restart or rebuild. This catches "properties changed yet the consumer remained stale."

### 22.5. Testing multiple replicas

In a Kubernetes sandbox:

- Use a test ConfigMap, with no real secrets.
- Deliver configuration via env or volume.
- Modify the ConfigMap while Pods run.
- Observe mounted files, environment, and demo endpoint behavior.
- Trigger a controlled rollout.
- Confirm all new Pods use the same value.
- Test config rollback and readiness when a new value is invalid.

Never run this experiment on user-facing production.

## 23. Sample Runbook: Changing an External Timeout Outside the JAR on a VM

**Context:** the application runs a JAR and reads `./config/application.yml` in a defined working directory.

### Preparation

- Confirm the exact file path, working directory, and service manager.
- Confirm the key to change is `catalog.client.timeout`.
- Confirm no higher-precedence CLI/env/source overrides it.
- Back up the file before editing per approved change procedures.
- Determine the restart window and impact scope.
- Prepare rollback if the new configuration is unsuitable.

### Change

1. Edit `catalog.client.timeout` from `3s` to `10s`.
2. Check syntax and formatting.
3. Use staging/validation if available to catch binding errors.
4. Restart the service via its service manager (systemd, Docker, or orchestrator).
5. Monitor startup logs, readiness, and business metrics.
6. Confirm **actual timeout behavior** or a safe measurement, not just that the file was edited.
7. If errors occur, restore the previous file and restart per procedure.

### Do not do

- Edit the file and report "applied" without restarting/refreshing.
- Accidentally edit `src/main/resources/application.yml` in source while the process runs a built JAR.
- Change multiple unrelated parameters at once.
- Log the entire `Environment` to find the winning source.
- Restart haphazardly on systems lacking draining/backup policies.

## 24. Sample Runbook: Changing Configuration on Kubernetes

**Context:** a Spring Boot Deployment has multiple replicas, configured via ConfigMap.

### Identify the delivery channel

- **Env var:** running Pods retain old values; new Pods are needed.
- **Volume mount:** files may update eventually, yet beans/clients do not update automatically.
- **subPath:** do not expect mount contents to update with the ConfigMap.
- **spring.config.import/configtree:** files enter Config Data at startup, not via an automatic watcher.

### Deployment steps

1. Review the ConfigMap/manifest diff and config schema.
2. Confirm exact source, namespace, and keys.
3. Update the ConfigMap through an approved pipeline/CI/GitOps workflow.
4. If using a sync controller from external config, wait until the controller confirms sync completed.
5. Trigger a rolling rollout via Pod template/checksum annotation change or an authorized restart.
6. Wait for new Pods to become ready; watch old/new replica counts.
7. Run a safe smoke test along the business path requiring the new configuration.
8. Confirm metrics and non-sensitive version IDs across all instances.
9. Complete the rollout and record status.
10. When rolling back, restore **both the configuration version** and the **Pod rollout**, not just the old image.

### 24.1. Why are checksum annotations commonly used?

In templating/GitOps systems, the Pod template can include an annotation that changes whenever ConfigMap contents change. Because a Deployment triggers a rollout when the Pod template changes, this links **changing a config source** to **creating new Pods**.

However, an annotation is only a rollout trigger mechanism. It does not prove the ConfigMap updated where intended or that the app bound values properly. Verify both source and runtime behavior.

### 24.2. Avoiding desynchronization when Secrets/ConfigMaps update slowly

When multiple config systems participate (secret manager, external-secrets controller, GitOps, Helm, Deployment), know the ordering of each step. Triggering a restart before the secret/config finishes syncing can make new Pods pick up stale values.

A runbook must explicitly require "source finished distributing" **before** "trigger rollout."

## 25. Dynamic Refresh and Safety Against Partial Changes

If an application must hot-reload, add failure policies:

### 25.1. Invalid new file

For example, editing from:

~~~yaml
routing:
  timeout: 3s
  enabled: true
~~~

to:

~~~yaml
routing:
  timeout: nonsense
  enabled: true
~~~

A good reload mechanism should **reject the invalid new snapshot** and keep the old policy or enter a defined error state, instead of publishing a partially updated object.

### 25.2. Two fields that must update together

If `routing.endpoint` and `routing.api-key-ref` are a matched pair, refreshing properties individually can pair the new endpoint with the old key. That can cause security or business bugs.

Treat **configuration as a versioned snapshot**, validating all cross-field relationships before publishing.

### 25.3. Clients with in-flight requests

If a request started using config version A and the system updates to B mid-request, mutating the client or credentials immediately can expose the request to inconsistent state. A professional refresh design defines lifecycle rules: keep A for active requests, construct client B for new requests, and close A after draining or timeout.

### 25.4. Rollback requires retaining previous valid versions

Storing only the current file with no revision history makes rollback difficult. Use GitOps, deployment revisions, or a versioned config store. Do not write secrets into Git for history; for secrets, use a secret manager and its version governance policies.

## 26. Common Misconceptions

| Incorrect or incomplete statement | Accurate understanding |
| --- | --- |
| "The file changed, so the app changed." | File changes only prove the source on disk changed |
| "Externalized config means hot reload." | Externalized and dynamic reload are two separate features |
| "Records are immutable, JavaBeans are mutable, so JavaBeans auto-update." | Mutable JavaBeans still require rebinding/recreation |
| "`Environment` always re-reads `application.yml`." | Config Data loads per lifecycle, with no default watcher |
| "Changing a `PropertySource` changes all beans." | Beans/clients can still hold old snapshots |
| "`@Value` looks up `Environment` on every method call." | Field/constructor injection usually resolves when the bean is created |
| "`optional` in `spring.config.import` means auto-reload." | `optional` only handles missing locations |
| "Editing a ConfigMap auto-rolls the Deployment." | Rollout requires a trigger/Pod template change when needed |
| "ConfigMap volumes update instantaneously." | Usually eventual; `subPath` has restrictions |
| "Mounted file updated, so `@ConfigurationProperties` auto-rebinds." | Not by default |
| "`@RefreshScope` handles every bean." | Depends on Spring Cloud, bean scope, and resource clients |
| "Restarting the old JAR reads the edited source YAML." | Embedded resources still come from the old artifact |
| "CLI/env does not affect files." | Precedence can override file values |
| "Health returning 200 proves the new timeout is in use." | Functional or effective-config checks are needed |
| "Rolling back the image rolls back config." | You must also restore config sources and versions |

## 27. Hands-On Exercises

### Exercise A — In-JAR vs. external file

Create two configs with the same key `lesson.timeout`:

~~~yaml
lesson:
  timeout: 3s
~~~

Package the JAR with the default, run with an external file outside the JAR containing `10s`. Observe precedence. Edit the source file in `src/main/resources` after the JAR is built, inspect the running process value, and explain why it did not auto-change.

### Exercise B — Editing a file while the application is running

Create record:

~~~java
@ConfigurationProperties(prefix = "lesson")
public record LessonProperties(Duration timeout) {}
~~~

Run with an external file `timeout=3s`. Edit to `10s` while the JVM runs. Inspect the bean before/after editing and after restart. Record three distinct values: file content, `Environment` value, and `LessonProperties`.

### Exercise C — Runtime PropertySource

Create a test context with `lesson.timeout=3s`. After the bean has bound, add a high-precedence `MapPropertySource` with `lesson.timeout=10s`. Compare:

- `environment.getProperty("lesson.timeout")`.
- `lessonProperties.timeout()`.
- A client built from the initial timeout.

Explain why the results can differ.

### Exercise D — ConfigMap env vs. volume

In a Kubernetes sandbox, supply the same test configuration key from a ConfigMap via env and via volume. Update the ConfigMap while the Pod runs. Observe:

1. Process environment.
2. Mounted file contents.
3. Bound Spring Boot bean.
4. Behavior after recreating the Pod.

Do not use production secrets in the exercise.

### Exercise E — The subPath case

Mount a ConfigMap file via `subPath`, then edit the ConfigMap. Compare with a standard volume mount and explain why you cannot rely on `subPath` for automatic hot reload.

### Exercise F — Precedence on restart

An external file outside the JAR has `lesson.timeout=10s`, yet CLI passes `--lesson.timeout=2s`. Restart the JVM. Predict the timeout and state why the app still uses `2s`.

### Exercise G — A file watcher is not enough

Build a watcher detecting changes to `application.yml`. List every remaining step required to support safe reload: parsing, conversion, validation, atomic publishing, component reconstruction, multi-replica synchronization, and rollback.

### Exercise H — Write a rollout runbook

A Deployment has four Pods using a ConfigMap for client timeout. Write the procedure: updating the ConfigMap, waiting for sync, triggering rolling restart, checking readiness, smoke testing, confirming version, and rolling back. Explain why all four Pods should not be restarted simultaneously.

### Exercise I — Invalid configuration during restart

Set `lesson.timeout=not-a-duration`. Predict the conversion error the Binder reports when the new context starts. Design how to keep the old system serving during a rolling rollout if the new Pod fails readiness.

### Exercise J — Secret changes

An application reads a token from a Secret file in `configtree`. The Secret mount receives a new version, yet the token bean still holds the old version. Describe a safe transition and when to revoke the old secret. Never log real tokens to verify.

## 28. Checklist for Deploying Configuration File Changes

### Before making changes

- [ ] Identify the file/source **actually loaded** and the working directory.
- [ ] Identify property keys, active profiles, and precedence order.
- [ ] Confirm whether the source lives inside or outside the JAR.
- [ ] Identify Env/ConfigMap/Secret/configtree/import and load timing.
- [ ] Know which components retain bound values and which clients need rebuilding.
- [ ] Explicitly choose restart, rolling rollout, or dynamic refresh.
- [ ] Have schema/binding/validation tests for the new values.
- [ ] Have a secret-protection plan and avoid logging sensitive data.
- [ ] Verify replica count, readiness, graceful shutdown, and rollback.

### When applying

- [ ] Update files/sources safely without partial writes.
- [ ] Confirm configuration has been distributed to the target environment.
- [ ] Trigger restart/rollout if that is the chosen mechanism.
- [ ] Watch startup and binding/validation errors.
- [ ] Wait for new instances to become ready before shifting traffic.
- [ ] Verify functional behavior and metrics, not only the file contents.
- [ ] Confirm all replicas run the intended version.
- [ ] Monitor effects on clients, pools, schedulers, and credentials.
- [ ] On rollback, restore both config source and deployment state.

### After changes

- [ ] Record timestamp, owner, and configuration version.
- [ ] Confirm no old Pods/instances remain beyond the transition window.
- [ ] Document any startup failures and how they were handled.
- [ ] Audit logs/Actuator to verify no secrets leaked.
- [ ] Update operational docs if refresh/restart mechanics changed.

## 29. Conclusion

**Editing a file after the application is running is not equivalent to restarting Spring Boot.** The file is only an input. Spring Boot may already have read it to build `Environment`, bind `@ConfigurationProperties`, inject `@Value`, and construct clients/pools at startup.

For applications without custom-designed refresh, **the predictable path is updating configuration and recreating the process** via restart or rolling rollout with readiness and graceful shutdown. If live updates while running are truly needed, build the entire pipeline—**detect → reload → validate → publish → rebuild/refresh consumers → observe → rollback**—not just a file watcher.

Three verification questions after every configuration change:

1. **Which source changed?** External file, env, ConfigMap/Secret, configtree, or another source?
2. **Did the process re-read it?** Was a restart/rebind/refresh verified?
3. **Did the consuming components update?** Are beans, HTTP clients, connection pools, and all replicas using the new value?

Only when you can answer all three do you have grounds to say the configuration change **took effect**, rather than merely confirming "the file was edited."

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): configuration sources, precedence, config data, external file locations, and imports.
- [Spring Boot Reference — Config Data Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): classpath/external locations and profile-specific configuration.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import` and config tree imports.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Binder, bean lifecycle, immutable and mutable property objects.
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): controlled web server shutdown.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness in Kubernetes deployments.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): querying properties in Spring `Environment`.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): delivering config via environment and volumes, updating mounted ConfigMaps.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret env/volumes, eventual updates, and `subPath` limitations.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate and rollout strategies.
- [Spring Cloud Commons — Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope): dedicated refresh mechanism when an application actually integrates Spring Cloud.
