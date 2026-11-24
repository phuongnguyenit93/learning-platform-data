# Registering or Removing Contributors with HealthContributorRegistry

## 1. The Registry Manages Which Checks Participate in Health

An application may connect to resources that change at runtime: adding a tenant, enabling a search integration, or removing a connection that is no longer in use. If the list of health checks were determined only at startup, the health endpoint could miss new resources or continue checking retired ones.

`HealthContributorRegistry` is the registry of components providing health information (`HealthContributor`), keyed by identifier name. Through the registry, an application can add or remove a contributor at runtime without restarting.

Distinguish two questions:

- **Is the contributor still within the monitoring scope?** The registry determines its presence or absence.
- **Is the resource functioning properly?** `HealthIndicator` performs the check and returns `Health` with a status such as `UP` or `DOWN`.

A search service that is still in use yet temporarily disconnected must remain present and report `DOWN`. Only remove a contributor when the resource genuinely leaves the monitoring scope. Removing a `DOWN` check can make the aggregate report look healthier even though the failure has not been resolved.

This lesson uses the synchronous API in the `org.springframework.boot.actuate.health` package of **Spring Boot 3.3.x**, suitable for Servlet applications. The example pins the dependency at 3.3.0 for reproducibility; projects on another 3.3.x patch version should keep version management consistent with the project's BOM.

## 2. Relationship Between Contributors, Spring Beans, and the Health Endpoint

`HealthContributor` is the common type. Two common forms are:

| Type | Role |
| --- | --- |
| `HealthIndicator` | A check with a `health()` method returning `Health` |
| `CompositeHealthContributor` | A group of child contributors forming a branch in the health tree |
| `HealthContributorRegistry` | Manages root-level contributors by ID, supporting add, lookup, iteration, and removal |

Under standard auto-configuration, Spring Boot builds the registry from contributor beans in the `ApplicationContext`. `HealthEndpoint` uses that registry to find which contributors to check. Therefore, in a Spring Boot application, **inject the registry used by the application** into the lifecycle management class.

Instantiating `new DefaultHealthContributorRegistry()` yourself creates only a separate registry. Unless the health endpoint is configured to use that registry, adding contributors to it does not change `/actuator/health`. A standalone registry is great for the isolated example in section 4, yet does not replace the injected registry in an application.

Registry operations are also independent of bean lifecycle:

- `registerContributor` does not register a new bean into `ApplicationContext`. An object created with `new` and placed into the registry does not automatically receive Spring dependency injection or bean lifecycle callbacks.
- `unregisterContributor` does not delete a Spring bean and does not automatically close connection pools, HTTP clients, or stop background tasks.
- Removing a contributor does not automatically stop the underlying resource from serving business traffic.

It is a change to the observation list. Provisioning, draining requests, awaiting in-flight work, and releasing resources require their own lifecycle mechanisms. Default configuration of the endpoint and registry is described in [Spring Boot 3.3.13 HealthEndpointConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

## 3. Operations and Contracts to Remember

The signatures below apply to `HealthContributorRegistry`; mutation operations are inherited from `ContributorRegistry<HealthContributor>`:

```java
void registerContributor(String name, HealthContributor contributor);
HealthContributor getContributor(String name);
HealthContributor unregisterContributor(String name);
```

| Operation | Outcome to understand |
| --- | --- |
| `registerContributor(id, contributor)` | Adds contributor by ID; returns nothing and does not invoke `health()` automatically |
| `getContributor(id)` | Returns the registered object, or `null` if absent |
| `unregisterContributor(id)` | Returns the removed contributor itself, or `null` if the ID does not exist |
| Iterating the registry | Yields each `NamedContributor<HealthContributor>` with name and object; iteration does not run checks automatically |

In the default 3.3 implementation, registering a duplicate ID throws `IllegalStateException`, even when passing the exact same old object again. This is not an overwrite update. Neither the name nor the contributor passed to registration may be `null`.

Do not cast every contributor to `HealthIndicator`: the returned value may also be a `CompositeHealthContributor`. Cast only when certain which type the ID points to, or check with `instanceof`.

### Choose Clear and Consistent IDs

The ID is the name appearing in the health tree, not a Java class name or an arbitrary URL. Default configuration has bean-name shortening rules, such as a `searchHealthIndicator` bean typically appearing under the name `search`. When registering dynamically, pick a clean ID upfront such as `externalSearch` or `tenantAlpha`, and use that exact ID for lookup and removal.

Do not rely on all methods shortening names in the same way automatically. In particular, look up using the actual name in the registry. Do not use `/` to simulate a child path; names should be stable, recognizable, and avoid colliding with auto-configured contributor names or health group names.

You can inspect the list of names without making network calls:

```java
registry.forEach(named -> System.out.println(named.getName()));
```

This is a snippet placed where a `registry` variable already exists, not a standalone program. See the official contracts at [ContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ContributorRegistry.html) and [NamedContributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

## 4. Runnable Java Program: Add, Change Status, Remove

This example uses a standalone registry to observe API behavior directly. It **does not start Spring Boot, does not open an HTTP port, and does not call external services**. `AtomicBoolean` simulates resource status; `AtomicInteger` counts actual check invocations.

Create a separate directory containing two files, `pom.xml` and `RegistryDemo.java`. JDK 17 or newer and Maven are required; the first dependency download requires access to Maven Central.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>health-registry-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

`RegistryDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.health.DefaultHealthContributorRegistry;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;

public class RegistryDemo {
    public static void main(String[] args) {
        HealthContributorRegistry registry = new DefaultHealthContributorRegistry();
        AtomicBoolean available = new AtomicBoolean(false);
        AtomicInteger checks = new AtomicInteger();

        HealthIndicator tenantAlpha = () -> {
            checks.incrementAndGet();
            return available.get()
                    ? Health.up().build()
                    : Health.down().withDetail("reason", "simulated-unavailable").build();
        };

        String id = "tenantAlpha";
        System.out.println("present-before=" + (registry.getContributor(id) != null));
        registry.registerContributor(id, tenantAlpha);
        System.out.println("present-after=" + (registry.getContributor(id) != null));
        System.out.println("checks-after-register=" + checks.get());
        System.out.println("first-status=" + tenantAlpha.health().getStatus());

        try {
            registry.registerContributor(id, tenantAlpha);
        }
        catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        available.set(true);
        HealthIndicator registered = (HealthIndicator) registry.getContributor(id);
        System.out.println("second-status=" + registered.health().getStatus());

        HealthContributor removed = registry.unregisterContributor(id);
        System.out.println("removed-same-instance=" + (removed == tenantAlpha));
        System.out.println("present-after-remove=" + (registry.getContributor(id) != null));
        System.out.println("remove-again=" + registry.unregisterContributor(id));
        System.out.println("detached-status=" + tenantAlpha.health().getStatus());
    }
}
```

In PowerShell on Windows, run in the directory containing the two files:

```powershell
mvn -q dependency:copy-dependencies "-DoutputDirectory=lib"
javac --release 17 -cp "lib/*" RegistryDemo.java
java -cp ".;lib/*" RegistryDemo
```

On Linux/macOS, the first two commands are similar; the run command uses `:` as the classpath separator:

```bash
java -cp ".:lib/*" RegistryDemo
```

Stdout of the program, excluding messages from Maven or the compiler:

```text
present-before=false
present-after=true
checks-after-register=0
first-status=DOWN
duplicate=IllegalStateException
second-status=UP
removed-same-instance=true
present-after-remove=false
remove-again=null
detached-status=UP
```

Each output line proves a distinct point:

1. After registration, the contributor can be found, yet the check count remains `0`. Registration only changes membership.
2. The first `health()` call returns `DOWN` because the `available` flag is `false`.
3. Re-registering the same ID fails. The existing contributor is not replaced.
4. Flipping the flag to `true` makes the next check return `UP`; there is no need to remove and re-register.
5. Removal returns the exact original object; subsequent lookup no longer finds the ID.
6. Removing again returns `null`. This is not a "resource is DOWN" error.
7. The `tenantAlpha` reference can still be called after removal. The registry does not destroy the object.

The cast in the example is valid because this program itself just registered a `HealthIndicator` under that ID. Do not apply this cast mechanically to contributors fetched from an arbitrary application's registry.

## 5. Integrating into a Spring Boot Application: One Owner per ID

Suppose a search feature can be activated or retired while the application is running. One management class holds sole responsibility for the `externalSearch` ID.

Place the class below in a package scanned by the application, such as `src/main/java/example/health/DynamicSearchHealth.java`. The application needs `spring-boot-starter-web` and `spring-boot-starter-actuator`, with versions managed by the same Spring Boot BOM. This is a class integrated into an existing application, not a standalone application with `main`.

```java
package example.health;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Service;

@Service
public final class DynamicSearchHealth {
    private static final String ID = "externalSearch";

    private final HealthContributorRegistry registry;
    private final AtomicBoolean available = new AtomicBoolean(false);
    private final HealthIndicator indicator = () -> available.get()
            ? Health.up().build()
            : Health.down().build();
    private boolean registered;

    public DynamicSearchHealth(HealthContributorRegistry registry) {
        this.registry = registry;
    }

    public synchronized void activate() {
        if (registered) {
            return;
        }
        registry.registerContributor(ID, indicator);
        registered = true;
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }

    public synchronized void deactivate() {
        if (!registered) {
            return;
        }
        if (registry.getContributor(ID) != indicator) {
            throw new IllegalStateException("Contributor ownership changed: " + ID);
        }
        registry.unregisterContributor(ID);
        registered = false;
    }
}
```

Usage from the application's feature or resource lifecycle manager:

```java
searchHealth.activate();          // Start monitoring; initial status is DOWN.
searchHealth.setAvailable(true);  // Resource is ready; the next check returns UP.
searchHealth.setAvailable(false); // Resource encountered an error; keep the contributor and report DOWN.
searchHealth.deactivate();        // Only call when the resource leaves the monitoring scope.
```

This is an illustrative call sequence, with `searchHealth` being the injected `DynamicSearchHealth` bean. The four statements run back-to-back, so they create no pauses for a user to make HTTP calls between steps. To observe each stage, apply one change at a time via the application's feature management flow before sending health requests.

In the example, `AtomicBoolean` only simulates status. For a real resource, the contributor must check appropriate conditions, enforce timeouts on I/O operations, and return results accurately reflecting the resource. Do not replace a real check with a flag that is always `true`.

### Why Have the `registered` Flag and `synchronized`?

`registered` records the registration that this class has successfully performed. It switches to `true` only after `registerContributor` completes; if an ID conflict occurs, the exception is preserved to surface the configuration error. Repeated calls to `activate()` or `deactivate()` through the same bean do not create duplicate registrations.

`synchronized` serializes the two lifecycle management methods **on this same object**. `AtomicBoolean` ensures checking threads see updates to the status flag. The two mechanisms solve two different problems.

A mandatory prerequisite is that every change for the `externalSearch` ID must go through that owning class. This class's lock does not prevent other code from writing directly to the registry. The reference check in `deactivate()` catches some unintended changes, yet does not create an atomic "check-then-remove" against external callers.

If multiple places manage the same ID, unify ownership or design shared coordination. Do not resolve contention by catching every `IllegalStateException` and ignoring it.

## 6. Observing the Effect Through the Health Endpoint

In a local practice environment, you can enable component visibility:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: always
      show-details: never
```

This configuration lets you view contributor names while not requesting check details to be exposed. It does not replace HTTP access authorization configuration. In real systems, choose an appropriate visibility policy such as `when-authorized`, and do not put sensitive data into check results.

Send requests after applying each change:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/externalSearch
```

In PowerShell you can use `curl.exe` to invoke the real curl program. The URLs above assume port `8080`, default management path, no extra context path, and an authorized caller.

Assuming all other contributors are `UP`, no custom HTTP mappings exist, and `externalSearch` is included in the inspected report:

| Stage | Contributor `externalSearch` | Aggregate health |
| --- | --- | --- |
| Not activated yet | Not in registry yet | Determined by remaining contributors |
| After `activate()`, flag still `false` | `DOWN` | `DOWN`, HTTP 503 |
| After `setAvailable(true)` | `UP` | `UP`, HTTP 200 |
| After `setAvailable(false)` | Still present and returns `DOWN` | `DOWN`, HTTP 503 |
| After `deactivate()` | No longer in registry | Determined by remaining contributors |

While the component exists and is permitted to be shown, the component URL can return:

```json
{"status":"DOWN"}
```

After removal, that component path normally returns HTTP 404 because the contributor is not found. This differs from HTTP 503 for a contributor that is still present yet reports `DOWN`. Security configuration may cause callers to receive 401/403 before reaching health lookup.

Do not conclude "once removed, aggregate health is always UP." Another contributor may still be `DOWN`; if the aggregated status set is empty, the result may be `UNKNOWN`. Aggregate status is decided by `StatusAggregator`, while HTTP status code is decided by `HttpCodeStatusMapper`.

Presence in the registry also does not guarantee the component name always appears in JSON: component visibility policy, access permissions, and health group filters can all affect what is observed. See [Spring Boot 3.3 Health Information documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

## 7. When Composites, Health Groups, or Reactive Applications Are Involved

### Composite: Register a Branch, Not a Fake Path

If a tenant has multiple child resources, you can build a `CompositeHealthContributor` and register it under a single root ID:

```java
HealthIndicator database = () -> Health.up().build();
HealthIndicator cache = () -> Health.down().build();

CompositeHealthContributor tenant = CompositeHealthContributor.fromMap(
        Map.<String, HealthContributor>of(
                "database", database,
                "cache", cache));

registry.registerContributor("tenantAlpha", tenant);
```

This snippet requires the corresponding imports from `java.util.Map` and `org.springframework.boot.actuate.health`, along with an existing `registry` variable. The health tree has branch `tenantAlpha` and children `database`, `cache`. A corresponding component path could be `/actuator/health/tenantAlpha/cache`.

`registry.unregisterContributor("tenantAlpha")` removes the entire branch from the root registry. Passing `"tenantAlpha/cache"` to the root registry does not mean it will traverse into the composite to delete a child. Dynamic addition or removal of children must be managed by the composite implementation and that branch's ownership mechanism; `fromMap` does not provide a mutable child registry API.

### Health Group: Selected Members Still Depend on Configuration

A group configured with `include: db` will not automatically track every new contributor with a different ID. Inspect the exact group being observed.

If a group explicitly names a contributor that is only registered after startup, startup membership validation may fail because the ID does not exist yet. You may consider changing registration timing, group design, or `management.endpoint.health.validate-group-membership` after evaluating requirements.

Disabling membership validation does not create missing contributors and does not ensure a group always has all critical checks. For mandatory resources, keeping a stable contributor and changing its status usually reports more clearly than having the member appear and disappear.

You can cross-check selection and membership validation rules at [Spring Boot 3.3 Health Groups](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

### Reactive: Use the Exact Registry Read by the Endpoint

In a WebFlux application, use `ReactiveHealthContributorRegistry` for dynamic changes. When a synchronous contributor must be added to the reactive registry, the API provides `ReactiveHealthContributor.adapt(...)`. Do not assume modifying the synchronous registry automatically mirrors changes into the reactive registry serving the endpoint.

This section only defines the API boundary; the lesson's examples use the synchronous registry. You can additionally cross-check [HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html), [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html), and [ReactiveHealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthContributorRegistry.html).

## 8. Concurrency, Replacement, and Resource Cleanup

The default registry implementation protects structural mutations of the contributor list. That does not turn every business sequence into an atomic transaction, nor does it make `health()` code thread-safe under concurrent calls.

Scenarios requiring explicit design:

- **Check-then-register:** between `getContributor(id) == null` and `registerContributor(id, value)`, another thread may register first. Ownership/coordination and conflict handling are required.
- **Remove-then-add to replace:** those are two separate operations. A health request in between may see a missing contributor; if the add step fails, the old contributor has already been removed. This API has no atomic `replaceContributor` operation.
- **In-flight health requests:** a check run may already hold a reference to a contributor before it is removed. Removing from the registry does not cancel that check run and does not guarantee all concurrent requests see the exact same list snapshot.
- **Closing resources too early:** do not close an HTTP client or pool merely because `unregisterContributor` just returned, if business work or checks are still using it. Stopping new work, awaiting in-flight processing, and closing resources belong to lifecycle management.
- **Multiple application instances:** the registry lives in the current process, not a distributed state store. Changes on one instance do not automatically update other instances or survive restarts. The desired list must be reconstructed from an authoritative configuration/business source.

If a resource still exists and only its condition changes, keep the ID and contributor stable while updating check data in a thread-safe way. This avoids observation gaps caused by removing and re-registering.

## 9. Common Mistakes and How to Distinguish Them

| Symptom | Cause to check | Appropriate fix |
| --- | --- | --- |
| Registered yet HTTP does not change | Mutated a self-created registry, wrong registry type, or hitting another instance | Inject the application's registry, verify application type and instance |
| ID exists yet component missing in JSON | Component hidden or group does not include that ID | Check visibility policy, permissions, and group configuration |
| Second registration throws exception | ID already exists or collides with a name reserved for a group | Use proper IDs and single ownership; do not treat register as overwrite |
| Lookup returns `null` | Used class/bean name instead of real ID, wrong casing, or already removed | Iterate names in registry and use consistent IDs |
| Health still `DOWN` after removal | Another contributor is still failing or a concurrent check had started | Read the specific component and distinguish in-flight checks |
| Health "turns healthy" right after removal | Failing check was excluded from the aggregate set | Only remove when changing monitoring scope is business-appropriate |
| Pool remains after removing contributor | Registry does not manage closing resources | Use dedicated resource lifecycle management |
| Removing root with `/` name fails to delete child | Confused root registry with composite structure | Manage child branch inside composite or remove exact root ID |

## 10. Self-Practice and Understanding Check

1. Run `RegistryDemo` and explain why `checks-after-register=0` even though `present-after=true`.
2. Change `available` from `false` to `true` while keeping the same registration. State the difference between changing status and changing membership.
3. Remove the `try/catch` block around the duplicate registration and rerun. Identify why the program stops before the removal step.
4. Add a second contributor, remove `tenantAlpha`, then iterate names. Verify removal applies only to the specified ID.
5. In the test application, observe root health and component health before/after removal. Explain why a non-existent component differs from a component that is `DOWN`.
6. Given the requirement "the search service is still mandatory yet temporarily unreachable," choose between keeping the contributor reporting `DOWN` versus removing it. Explain the impact on operators and monitoring systems.

After this lesson, learners should be able to identify **who owns the ID**, **which registry the endpoint uses**, **when to change status**, and **when a resource genuinely leaves the monitoring list**.
