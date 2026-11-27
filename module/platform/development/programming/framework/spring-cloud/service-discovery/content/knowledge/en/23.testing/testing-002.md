# ServiceInstance Contract and Metadata Testing

In Spring Cloud, a consumer typically receives a list of instances through DiscoveryClient. Each element is represented by ServiceInstance, a Spring Cloud Commons abstraction that hides how the registry stores data. Eureka, Consul, ZooKeeper, or a custom discovery client may use different registration structures, yet the consumer needs consistent information about the service, host, port, URI, security status, and metadata.

If an adapter maps a field incorrectly, service discovery may still return an instance, but the consumer could route to the wrong host/port, pick the wrong zone, or misread the application version. Therefore, we need contract tests at the boundary between the registry and the application, while validating metadata as a data schema with explicit rules.

This article explains how to define a ServiceInstance contract, write a shared test suite across multiple discovery clients, verify metadata through a real registry, and test consumer policies driven by metadata.

## 1. ServiceInstance as the contract between registry and consumer

ServiceInstance describes a concrete instance of a logical service. The consumer does not need to know whether the registry stores the instance as an application record, a service entry, or a znode. The consumer only needs meaningful and consistent fields.

Common attributes:

| Attribute | Meaning | Example |
|---|---|---|
| serviceId | Logical name of the service | inventory-service |
| instanceId | Identifier of a specific instance | inventory-node-a |
| host | Hostname or IP reachable by the consumer | 10.20.1.11 |
| port | Application port called by the consumer | 8081 |
| isSecure | Indicates whether the endpoint uses a secure connection | true |
| getUri | URI combining scheme, host, and port | https://inventory-node-a:8443 |
| metadata | Additional instance data | app.version=2.4.0 |

In Spring Cloud Commons, ServiceInstance provides methods such as getServiceId(), getHost(), getPort(), isSecure(), getUri(), and getMetadata(). Some versions also include getInstanceId() with a default implementation that may return null. Consequently, if the application needs a stable instance ID for observability, deduplication, or routing, make that an explicit system contract requirement and test each adapter.

ServiceInstance is not a verbatim copy of the registry record. The adapter is responsible for converting registry data into this abstraction. Contract tests should verify what the consumer actually receives, independent of the internal structure of Eureka, Consul, or ZooKeeper.

## 2. Defining the contract before writing tests

Before writing tests, clearly specify which fields are required, which are optional, and how missing or malformed data should be handled.

Example contract for inventory-service:

| Field | Application rule | Verification |
|---|---|---|
| serviceId | Non-empty, matches agreed logical name | Compare with fixture serviceId |
| instanceId | Non-empty and unique within the same service | Non-null, no duplicates |
| host | Non-empty, reachable from consumer network | Format check and integration connectivity |
| port | Within range 1–65535 | Boundary check |
| isSecure | Matches the advertised endpoint | Compare against scheme |
| URI | Consistent scheme, host, and port | Validate URI after conversion |
| metadata | Non-null map; keys and values follow schema | Validate required keys and value types |

Some rules above are application-level contracts; not all of them are enforced by the ServiceInstance interface itself. For example, instanceId may be absent in an implementation using the default method. If the consumer does not need an instance ID, do not enforce it just because one particular adapter happens to provide it.

The contract also needs to define how serviceId is normalized. A registry might expose application names in uppercase, lowercase, or with its own normalization rules. Do not assume every registry returns the same casing. Choose an application rule and test that the adapter converts accordingly.

## 3. Metadata as a data schema, not an arbitrary bucket

Metadata typically holds information for observability or routing policies. For example:

~~~yaml
app.version: "2.4.0"
app.build: "2026.11.24"
routing.zone: "zone-a"
routing.weight: "10"
routing.canary: "false"
contract.metadata-schema-version: "1"
~~~

When converted into ServiceInstance, metadata is usually a Map<String, String>. As a result, numbers and booleans are also represented as strings. Consumers need to parse them according to agreed rules; for example, weight can be parsed as an integer and canary compared against the string "true".

Use namespaced keys such as app.version, routing.zone, or contract.metadata-schema-version to avoid collisions between groups of information. Agree on exact casing; the metadata Map does not automatically treat routing.Zone and routing.zone as the same key.

Metadata should be categorized into groups:

- **Required:** needed by the consumer for routing or API compatibility.
- **Optional:** used only for observability or secondary features.
- **Extensible:** new keys may appear that older consumers should safely ignore.
- **Disallowed:** passwords, tokens, private keys, credentials, or sensitive data.

Do not use metadata as a substitute for authentication and authorization mechanisms. A canary=true field does not prove an instance is authorized to receive canary traffic; it is only input data for an already configured policy.

## 4. Distinguishing registration data from the read ServiceInstance

The data flow typically proceeds as follows:

~~~mermaid
flowchart LR
    Provider["Provider registers instance"]
    Registry["Eureka / Consul / ZooKeeper"]
    Adapter["DiscoveryClient adapter"]
    Instance["ServiceInstance"]
    Consumer["Consumer / LoadBalancer"]
    Provider -->|"serviceId, host, port, metadata"| Registry
    Registry -->|"Registry record"| Adapter
    Adapter -->|"Normalize fields"| Instance
    Instance -->|"Instance list"| Consumer
~~~

Contract tests should verify at least two boundaries:

1. The provider writes the registration data accurately.
2. DiscoveryClient returns a ServiceInstance matching the registered data.

If you only test the DefaultServiceInstance constructor, you are only testing an in-memory object. That does not prove the Eureka or Consul adapter maps metadata from the registry accurately.

Similarly, if you only mock DiscoveryClient to return a valid ServiceInstance, you have not verified how real registration data passes through the registry and comes back to the consumer.

## 5. Checking core fields of ServiceInstance

You can create a shared helper to verify invariants that every adapter must satisfy.

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public final class ServiceInstanceContractAssertions {

    private ServiceInstanceContractAssertions() {
    }

    public static void assertBaseContract(ServiceInstance instance) {
        assertThat(instance).isNotNull();
        assertThat(instance.getServiceId()).isNotBlank();
        assertThat(instance.getHost()).isNotBlank();
        assertThat(instance.getPort()).isBetween(1, 65535);
        assertThat(instance.getMetadata()).isNotNull();

        URI uri = instance.getUri();

        assertThat(uri).isNotNull();
        assertThat(uri.getScheme())
                .isEqualTo(instance.isSecure() ? "https" : "http");
        assertThat(uri.getHost()).isEqualTo(instance.getHost());
        assertThat(uri.getPort()).isEqualTo(instance.getPort());
        assertThat(uri.getUserInfo()).isNull();
    }
}
~~~

This helper encodes the application's concrete contract: the URI must reflect host, port, and secure; metadata must be a non-null map; and the URI must not embed user info or credentials.

If your system uses a scheme other than HTTP/HTTPS, has a base path in the URI, omits default ports, or terminates TLS at a proxy, adjust the contract to match the endpoint the consumer actually calls. Do not apply these assertions mechanically to an architecture with custom URIs.

Also test IPv6 if the system supports it. IPv6 hosts must be properly encoded in the URI, typically with square brackets in the authority part. Create tests with IPv6 addresses instead of manually concatenating host and port strings.

## 6. Checking instanceId and uniqueness

ServiceInstance may provide getInstanceId(), though the interface may have a default implementation returning null. If the system needs to distinguish instances for logging, tracing, deduplication, or endpoint selection, include instanceId in the application contract.

Example additional assertion:

~~~java
public static void assertIdentifiedInstance(ServiceInstance instance) {
    assertBaseContract(instance);

    assertThat(instance.getInstanceId())
            .as("instanceId must be stable and non-empty")
            .isNotBlank();
}
~~~

When a service has multiple replicas, verify that IDs do not collide:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public class InstanceIdAssertions {

    public static void assertUniqueIds(List<ServiceInstance> instances) {
        List<String> ids = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toList());

        assertThat(ids).doesNotContainNull();
        assertThat(ids).doesNotHaveDuplicates();
    }
}
~~~

Do not use host alone as the instanceId if multiple processes run on the same host with different ports. An identifier typically combines service name, hostname or pod name, and port, or uses an ID assigned by the deployment platform.

## 7. Checking required and optional metadata

A metadata verification helper should assert the keys needed by the consumer while allowing extension keys to appear.

~~~java
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public final class MetadataContractAssertions {

    private MetadataContractAssertions() {
    }

    public static void assertInventoryMetadata(ServiceInstance instance) {
        Map<String, String> metadata = instance.getMetadata();

        assertThat(metadata)
                .containsEntry("app.version", "2.4.0")
                .containsEntry("routing.zone", "zone-a")
                .containsEntry("contract.metadata-schema-version", "1");
    }
}
~~~

Avoid comparing the entire metadata map with equals if the application allows registries or adapters to add extension keys. Checking required keys makes contract tests resilient to metadata additions without breaking older consumers.

For optional keys, also test the case where the key is absent. For instance, if routing.canary is missing, the consumer should apply a defined default or reject the instance according to policy. Do not implicitly treat missing metadata as false, default zone, or latest version unless the contract states so.

For numeric values, test both valid and malformed formats:

~~~java
public static int readWeight(ServiceInstance instance) {
    String value = instance.getMetadata().get("routing.weight");

    if (value == null) {
        return 1;
    }

    try {
        int weight = Integer.parseInt(value);
        if (weight < 1) {
            throw new IllegalArgumentException("routing.weight must be greater than 0");
        }
        return weight;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Invalid routing.weight", ex);
    }
}
~~~

The default value of 1 is only a policy example. Choose how to handle missing or invalid metadata to fit business needs: use a safe default, skip the instance, or fail configuration. Do not let parse failures silently turn into unintended routing values.

## 8. Writing a shared contract test suite for DiscoveryClient

When multiple registry adapters exist, use a shared abstract test suite. Each implementation only needs to supply its DiscoveryClient and corresponding fixtures.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

abstract class DiscoveryClientContractTest {

    protected abstract DiscoveryClient discoveryClient();

    protected abstract String serviceId();

    protected abstract Map<String, String> requiredMetadata();

    @Test
    void returnsInstancesThatFollowTheContract() {
        List<ServiceInstance> instances =
                discoveryClient().getInstances(serviceId());

        assertThat(instances).isNotNull().isNotEmpty();

        instances.forEach(instance -> {
            ServiceInstanceContractAssertions.assertIdentifiedInstance(instance);
            assertThat(instance.getServiceId()).isEqualTo(serviceId());
            assertThat(instance.getMetadata())
                    .containsAllEntriesOf(requiredMetadata());
        });

        List<String> ids = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toList());

        assertThat(ids).doesNotContainNull();
        assertThat(ids).doesNotHaveDuplicates();
    }

    @Test
    void returnsAnEmptyListForUnknownService() {
        List<ServiceInstance> instances =
                discoveryClient().getInstances("service-does-not-exist");

        assertThat(instances).isNotNull().isEmpty();
    }
}
~~~

Concrete test classes extend this suite and prepare data in the registry before running. For example, a Eureka contract test starts a Eureka Server test profile; a Consul contract test uses a Consul test container; a ZooKeeper contract test creates registrations in a ZooKeeper test environment.

Do not use a single mock DiscoveryClient across all subclasses and treat that as adapter testing. The purpose of the suite is to run the same assertions against real implementations or real adapters so field-mapping differences are caught.

If a registry does not support instanceId or metadata in the same way, define a translation adapter or adjust the application-level contract. Do not skip assertions just to make every test green.

## 9. Testing metadata through a real registry

Integration tests need to verify the full round trip:

1. Start a test registry.
2. Register a provider with fixture serviceId, instanceId, host, port, and metadata.
3. Wait for the registration to appear according to the registry's mechanism.
4. Call DiscoveryClient.getInstances(serviceId) from the consumer test.
5. Locate the instance by ID instead of relying on element position.
6. Run contract assertions on the returned ServiceInstance.
7. Verify required metadata retains its values.
8. Deregister the provider or close the session and clean up data after the test.

Do not assert the order of instances in the list unless the adapter or application explicitly guarantees ordering. Registries usually do not guarantee a stable order. Look up instances by instanceId or filter by a unique attribute.

An integration test should also verify two or more instances under the same serviceId. This catches adapter bugs that return only one instance, accidentally merge metadata, or reuse the same instanceId.

With registries that use caching or eventual consistency, do not use a fixed sleep as the sole waiting mechanism. Use polling with a timeout to wait for the registration condition to appear; upon timeout, the test should clearly report the serviceId and expected state.

## 10. Metadata mapping across registries

Each registry has its own metadata model. Contract tests should validate the data after the adapter normalizes it to ServiceInstance.

| Registry | Common data location | What to test |
|---|---|---|
| Eureka | Instance metadata map | Metadata keys and values are returned accurately |
| Consul | Service metadata and tags | Whether metadata map is preserved; whether tags are mapped by application convention |
| ZooKeeper | Registration data in znode | Payload is decoded and converted into metadata properly |
| Custom registry | Adapter-specific record | Mapping does not drop data or change types |

Example metadata configuration for Eureka:

~~~yaml
eureka:
  instance:
    metadata-map:
      app.version: "2.4.0"
      routing.zone: "zone-a"
      contract.metadata-schema-version: "1"
~~~

Example metadata configuration for Consul:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          app.version: "2.4.0"
          routing.zone: "zone-a"
          contract.metadata-schema-version: "1"
~~~

Properties and mapping behavior depend on the Spring Cloud starter version. In Consul, tags and metadata are two separate concepts; do not assume a tag automatically becomes an entry in the metadata map. In ZooKeeper, verify how the starter stores and reads the payload in the version you are using.

Contract tests should assert the final data seen by the consumer, rather than requiring every registry to store the same internal structure.

## 11. Testing metadata impact on consumer policies

Metadata does not automatically make Spring Cloud LoadBalancer pick instances by zone, version, or canary. If an application wants to use metadata for filtering or ranking, it must have a dedicated policy and separate tests.

Example function filtering instances by zone:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;

public class ZoneRoutingPolicy {

    public List<ServiceInstance> filterByZone(
            List<ServiceInstance> instances,
            String requiredZone) {

        return instances.stream()
                .filter(instance -> requiredZone.equals(
                        instance.getMetadata().get("routing.zone")))
                .collect(Collectors.toList());
    }
}
~~~

Test for the policy:

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

class ZoneRoutingPolicyTest {

    @Test
    void selectsOnlyInstancesInRequestedZone() {
        ServiceInstance zoneA = new DefaultServiceInstance(
                "inventory-a",
                "inventory-service",
                "10.20.1.11",
                8081,
                false,
                Collections.singletonMap("routing.zone", "zone-a"));

        ServiceInstance zoneB = new DefaultServiceInstance(
                "inventory-b",
                "inventory-service",
                "10.20.2.12",
                8081,
                false,
                Collections.singletonMap("routing.zone", "zone-b"));

        List<ServiceInstance> selected =
                new ZoneRoutingPolicy().filterByZone(
                        Arrays.asList(zoneA, zoneB), "zone-a");

        assertThat(selected)
                .extracting(ServiceInstance::getInstanceId)
                .containsExactly("inventory-a");
    }
}
~~~

The example uses DefaultServiceInstance to test the policy in memory. It does not replace an integration test verifying that metadata is read properly from the registry. In practice, the policy may be implemented via a ServiceInstanceListSupplier or a LoadBalancer component corresponding to your Spring Cloud version.

Also test when no instances exist in the requested zone: should the application fall back to another zone, return an error, or wait? This is a business decision and should not be left to incidental list behavior.

## 12. Testing scheme, TLS, and instance address

The ServiceInstance contract must reflect the endpoint the consumer actually calls. If an instance requires HTTPS, isSecure() and the URI scheme must be consistent.

Cases to test:

- HTTP instance: isSecure=false and URI uses http.
- HTTPS instance: isSecure=true and URI uses https.
- Custom TLS port: URI preserves the registered port.
- Hostname: consumer can resolve it from its network.
- IPv4/IPv6: URI is constructed validly.
- TLS termination: clearly verify whether the consumer connects to an HTTPS proxy or an internal HTTP provider.

Do not assume every HTTPS endpoint uses port 443 or every HTTP endpoint uses port 80. The registry must return the actual port the consumer has to call.

Object-level contract tests only verify consistent host/port/scheme. Network integration tests need to attempt connections from the consumer environment to prove advertised addresses have valid routing and firewall rules.

## 13. Testing metadata compatibility across version upgrades

Metadata is a schema that can evolve over time. If consumers and providers are deployed independently, backward and forward compatibility between old and new versions must be maintained.

Useful rules:

- Adding a new optional key is usually safe if older consumers ignore unknown keys.
- Do not change the meaning of an existing key while keeping the same name.
- If the type or semantics of data change, increment metadata-schema-version.
- When removing a key, check whether any consumer still relies on it.
- For required keys, define the behavior when missing or malformed.
- Do not use metadata as a channel for large or frequently changing business payloads.

For example, consumer v1 only needs app.version and routing.zone. A newer provider adds routing.canary. Consumer v1 should ignore the new key; consumer v2 can use it once the policy is implemented. Contract tests should validate both old and extended data.

You can maintain fixtures per schema version:

| Schema | Required keys | Optional keys |
|---|---|---|
| 1 | app.version, routing.zone | routing.weight |
| 2 | app.version, routing.zone, contract.metadata-schema-version | routing.weight, routing.canary |

Do not let consumers infer the schema version from whether a particular key is present. Declaring the version explicitly makes testing and rollout more controlled.

## 14. Verifying metadata contains no secrets

Registries often have many consumers and administrative tools with read access to service metadata. Therefore, metadata is not the place to store credentials.

You can add an assertion checking for forbidden key names:

~~~java
import java.util.Locale;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public class MetadataSecurityAssertions {

    public static void assertNoSecretKeys(ServiceInstance instance) {
        Map<String, String> metadata = instance.getMetadata();

        assertThat(metadata.keySet()).allSatisfy(key -> {
            String normalized = key.toLowerCase(Locale.ROOT);

            assertThat(normalized)
                    .doesNotContain("password")
                    .doesNotContain("secret")
                    .doesNotContain("token")
                    .doesNotContain("private-key")
                    .doesNotContain("credential");
        });
    }
}
~~~

This is an extra safeguard based on key-naming conventions and cannot prove every value is benign. Restrict the metadata schema via an allowlist and review registered data. Never place authentication details in tags, hostnames, serviceIds, or URIs.

## 15. Common mistakes in contract tests

| Symptom | Possible cause | How to fix |
|---|---|---|
| ServiceInstance has correct serviceId but wrong host | Adapter picks node address or unreachable internal address | Check advertised address mapping and test from consumer |
| URI uses HTTP even though instance requires HTTPS | isSecure or scheme mapped incorrectly | Check registration and URI contract |
| Metadata lost after reading registry | Adapter does not map metadata or confuses tags | Check registry record and mapping |
| Metadata has key but wrong value type | Registry stores number/boolean as string or consumer parses wrongly | Standardize string schema and test parser |
| Two instances share the same ID | Registration generates non-unique ID | Build ID from host/pod and port or platform ID |
| Test depends on list order | Registry does not guarantee instance order | Find by instanceId and assert result set |
| Mock tests pass but production fails | Real adapter and registry were never tested | Add integration tests |
| Consumer does not filter by zone/version | Metadata does not automatically trigger routing policies | Test ServiceInstanceListSupplier or custom policy |
| Test fails intermittently | Registry cache or eventual consistency | Poll with timeout until condition holds |
| Metadata exposes credentials | Missing schema/allowlist | Forbid secrets and check security contract |

## 16. Workflow for building the test suite

Follow this sequence:

1. Define the serviceId, instanceId, and metadata schema required by the application.
2. Write assertion helpers for the core ServiceInstance fields.
3. Write dedicated assertions for required metadata, optional metadata, and forbidden data.
4. Create an abstract contract test for DiscoveryClient.
5. Write test classes for each adapter: Eureka, Consul, ZooKeeper, or custom registry.
6. Run integration tests with a test registry and register multiple instances.
7. Verify metadata flows from provider registration through the registry to the consumer.
8. Test URI, TLS, host/port, and reachability from the consumer's network.
9. Test instance filtering policies by zone, version, or canary if the application uses metadata.
10. Test missing data, malformed values, extension keys, and old/new schema versions.
11. Test deregistration and confirm the instance disappears from results after the registry updates.
12. Run the contract suite in CI for every supported adapter.

Unit contract tests can run on every pull request. Integration tests against a real registry can run under a dedicated profile or in an appropriate pipeline. Tests must clean up registrations afterward so they do not interfere with subsequent runs.

## 17. Completion checklist

Before considering the ServiceInstance contract protected, verify:

1. serviceId is a stable logical name with clear normalization rules.
2. instanceId is checked if the application requires per-replica identification.
3. host and port are addresses reachable by the consumer.
4. isSecure and the URI scheme are consistent.
5. metadata is non-null per the application contract and conforms to the schema.
6. Required keys have accurate values; optional keys have clear default rules.
7. Extension metadata does not break older consumers.
8. Metadata contains no secrets or credentials.
9. Every registry adapter runs the same contract test suite.
10. Integration tests verify data passing through a real registry.
11. Consumer policies based on metadata are tested separately.
12. Tests do not depend on instance ordering or arbitrary update timing.

The core takeaway is: **ServiceInstance is the data contract received by the consumer after the discovery adapter converts the registry record; metadata is a schema that must be governed and tested like an API.** Test core fields, metadata, and routing behavior so registry changes never silently break consumers.
