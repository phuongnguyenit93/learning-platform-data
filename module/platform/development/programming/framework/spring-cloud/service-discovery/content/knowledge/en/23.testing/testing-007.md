# Testing Multiple Instances, Status Changes, and Deregistration

## 1. Goals of instance lifecycle testing

A service can have multiple instances registered under the same service ID. Discovery clients must receive the appropriate instance list; meanwhile, each instance has its own lifecycle: registering, transitioning to a non-serving state, and deregistering on shutdown.

When testing Spring Cloud Service Discovery, two groups of behaviors need verification:

- **Lookup:** DiscoveryClient returns a list of multiple ServiceInstances, an empty list, or a query failure; business logic selects and handles instances properly.
- **Registration lifecycle:** ServiceRegistry receives the expected register, status update, and deregister calls in the order required by the application.

DiscoveryClient is the abstraction for reading services and instances. ServiceRegistry is the abstraction for writing the local instance's registration lifecycle. Because the two interfaces serve opposite directions, tests need to control them separately.

## 2. Distinguishing DiscoveryClient and ServiceRegistry

| API | Responsibility | Example operations |
|---|---|---|
| DiscoveryClient | Look up services and instances | getServices(), getInstances(serviceId) |
| ServiceRegistry | Manage the current instance's registration | register(), setStatus(), deregister() |
| ServiceInstance | Describe a discovered endpoint | service ID, host, port, URI, metadata |
| Registration | Instance that can be registered with the registry | ServiceInstance information used for register/deregister |

DiscoveryClient typically returns multiple ServiceInstances because a service can run multiple replicas. ServiceRegistry operates on a specific registration managed by the application. Never call setStatus on DiscoveryClient: that API belongs to ServiceRegistry or the corresponding provider client.

## 3. Preparing test dependencies

The examples use JUnit 5, Mockito, and AssertJ. In a Spring Boot project, spring-boot-starter-test usually provides these libraries:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The Spring Cloud Commons version should be managed by a Spring Cloud BOM compatible with your Spring Boot version. Do not mix a Commons version from a different release train.

If using Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-commons")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

## 4. Creating a class that reads multiple instances

Suppose payment-service needs all endpoints of inventory-service to pass to an instance selection policy:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class ServiceInstanceDirectory {

    private final DiscoveryClient discoveryClient;

    public ServiceInstanceDirectory(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findUris(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
~~~

This class only maps the list of ServiceInstances to a list of URIs. It does not check endpoint health itself and does not guarantee the URIs are reachable. The provider is responsible for returning instances according to its discovery semantics; the caller must still handle connection errors when sending requests.

## 5. Testing when multiple instances exist

Create the test file:

~~~text
src/test/java/com/example/payment/discovery/ServiceInstanceDirectoryTest.java
~~~

JUnit 5 and Mockito example:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@ExtendWith(MockitoExtension.class)
class ServiceInstanceDirectoryTest {

    private static final String SERVICE_ID = "inventory-service";

    @Mock
    private DiscoveryClient discoveryClient;

    private ServiceInstanceDirectory directory;

    @BeforeEach
    void setUp() {
        directory = new ServiceInstanceDirectory(discoveryClient);
    }

    @Test
    void shouldReturnEveryDiscoveredInstanceInProviderOrder() {
        URI firstUri = URI.create("http://10.0.0.12:8081");
        URI secondUri = URI.create("http://10.0.0.13:8081");
        ServiceInstance first = mock(ServiceInstance.class);
        ServiceInstance second = mock(ServiceInstance.class);

        when(first.getUri()).thenReturn(firstUri);
        when(second.getUri()).thenReturn(secondUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Arrays.asList(first, second));

        List<URI> result = directory.findUris(SERVICE_ID);

        assertThat(result).containsExactly(firstUri, secondUri);
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldReturnEmptyListWhenServiceHasNoInstances() {
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.emptyList());

        List<URI> result = directory.findUris(SERVICE_ID);

        assertThat(result).isEmpty();
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldPropagateDiscoveryFailure() {
        RuntimeException failure =
                new RuntimeException("registry query failed");
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenThrow(failure);

        org.assertj.core.api.Assertions.assertThatThrownBy(
                () -> directory.findUris(SERVICE_ID))
                .isSameAs(failure);
    }
}
~~~

The first test confirms both URIs are preserved and their order is not altered by the directory class. The second distinguishes a successful lookup where the service has no instances. The third confirms provider errors are not silently converted into an empty list.

The order in this example is simply whatever DiscoveryClient returns. Do not assume the first element always has highest priority; instance selection algorithms may live in Spring Cloud LoadBalancer or a dedicated policy.

## 6. Testing instance selection policies

If your application has a custom instance selection policy, test that policy rather than testing arbitrary provider ordering. The simple example below rotates across URIs:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class RoundRobinUriSelector {

    private final ServiceInstanceDirectory directory;
    private final AtomicInteger sequence = new AtomicInteger();

    public RoundRobinUriSelector(ServiceInstanceDirectory directory) {
        this.directory = directory;
    }

    public URI choose(String serviceId) {
        List<URI> uris = directory.findUris(serviceId);
        if (uris.isEmpty()) {
            throw new IllegalStateException(
                    "No instances found for " + serviceId);
        }
        int index = Math.floorMod(sequence.getAndIncrement(), uris.size());
        return uris.get(index);
    }
}
~~~

Tests for the selector can mock ServiceInstanceDirectory:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RoundRobinUriSelectorTest {

    @Mock
    private ServiceInstanceDirectory directory;

    private RoundRobinUriSelector selector;

    @BeforeEach
    void setUp() {
        selector = new RoundRobinUriSelector(directory);
    }

    @Test
    void shouldRotateAcrossAvailableInstances() {
        URI first = URI.create("http://10.0.0.12:8081");
        URI second = URI.create("http://10.0.0.13:8081");
        when(directory.findUris("inventory-service"))
                .thenReturn(Arrays.asList(first, second));

        assertThat(selector.choose("inventory-service")).isEqualTo(first);
        assertThat(selector.choose("inventory-service")).isEqualTo(second);
        assertThat(selector.choose("inventory-service")).isEqualTo(first);
    }

    @Test
    void shouldFailClearlyWhenNoInstanceIsAvailable() {
        when(directory.findUris("inventory-service"))
                .thenReturn(Collections.emptyList());

        assertThatThrownBy(() -> selector.choose("inventory-service"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("inventory-service");
    }
}
~~~

This algorithm illustrates application logic. When using Spring Cloud LoadBalancer, test your ServiceInstanceListSupplier, ReactorLoadBalancer, or real application policy instead of replacing them with a custom selector unused in production.

## 7. Modeling status changes and deregistration

ServiceRegistry has a generic type parameter R extends Registration. Each provider has a concrete registration type; therefore, code using the registry should preserve the provider's generic type instead of casting every registration to a raw type.

Example generic coordinator class:

~~~java
package com.example.payment.discovery;

import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public class RegistrationLifecycle<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final String unavailableStatus;

    public RegistrationLifecycle(
            ServiceRegistry<R> serviceRegistry,
            String unavailableStatus) {
        this.serviceRegistry = serviceRegistry;
        this.unavailableStatus = unavailableStatus;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void markUnavailable(R registration) {
        serviceRegistry.setStatus(registration, unavailableStatus);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

This class separates three operations so the application can orchestrate shutdown:

1. Register the instance on startup.
2. Change status to stop receiving new requests.
3. Wait for an appropriate drain period at the application or load balancer layer.
4. Deregister once draining completes or the drain deadline expires.

Status strings are provider-dependent. For example, Eureka has the OUT_OF_SERVICE status; Consul typically relies on passing/critical health checks; Kubernetes Service discovery typically relies on readiness and EndpointSlices. Do not copy Eureka status strings to another provider and expect identical semantics.

## 8. Testing registration, status change, and deregistration

Both ServiceRegistry and Registration can be mocked:

~~~java
package com.example.payment.discovery;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

@ExtendWith(MockitoExtension.class)
class RegistrationLifecycleTest {

    private static final String UNAVAILABLE = "OUT_OF_SERVICE";

    @Mock
    private ServiceRegistry<Registration> serviceRegistry;

    @Mock
    private Registration registration;

    private RegistrationLifecycle<Registration> lifecycle;

    @BeforeEach
    void setUp() {
        lifecycle = new RegistrationLifecycle<>(
                serviceRegistry, UNAVAILABLE);
    }

    @Test
    void shouldRegisterInstance() {
        lifecycle.register(registration);

        verify(serviceRegistry).register(registration);
    }

    @Test
    void shouldChangeStatusWithoutDeregisteringImmediately() {
        lifecycle.markUnavailable(registration);

        verify(serviceRegistry).setStatus(registration, UNAVAILABLE);
    }

    @Test
    void shouldDeregisterTheRequestedRegistration() {
        lifecycle.deregister(registration);

        verify(serviceRegistry).deregister(registration);
    }

    @Test
    void shouldAllowDrainSequenceBeforeDeregistration() {
        lifecycle.register(registration);
        lifecycle.markUnavailable(registration);
        // Application waits for drain here; unit test does not sleep.
        lifecycle.deregister(registration);

        InOrder order = inOrder(serviceRegistry);
        order.verify(serviceRegistry).register(registration);
        order.verify(serviceRegistry).setStatus(registration, UNAVAILABLE);
        order.verify(serviceRegistry).deregister(registration);
    }
}
~~~

The test verifies that the application sends the right operations to the registry and preserves the exact order. The drain comment marks where the application may wait for in-flight requests to finish; the unit test needs no Thread.sleep because its goal is interaction order.

In a Eureka project, the actual registration usually has a concrete type such as EurekaRegistration. When wiring real beans, use the exact generic type supplied by the provider. The example uses a mocked Registration to illustrate the general ServiceRegistry contract.

## 9. Why are status change and deregistration two separate steps?

Changing status usually signals that an instance is temporarily not accepting new traffic. Deregistering removes the registration from the registry. In a graceful shutdown sequence:

1. The application switches the instance to an out-of-service state.
2. The registry or clients observe the change via the provider's update mechanism.
3. Load balancers stop picking the instance for new requests.
4. The application finishes in-flight requests within an allowed grace period.
5. The application deregisters and releases resources.

Not every provider shares the same status model. In Eureka, OUT_OF_SERVICE has explicit registry semantics. In Consul, service health is usually driven by checks; updating a check or deregistering may be more appropriate. In Kubernetes, readiness=false and termination/EndpointSlice updates usually control endpoints. Generic unit tests only prove the application invokes the abstraction; integration tests must prove the real provider transitions state properly.

Some providers may not support setStatus in the same way or may implement it by updating a health check. If a provider lacks a suitable status setter, use the appropriate adapter/provider API and test that contract separately.

## 10. Testing multiple registrations

A single service ID can have multiple instances. If an application class manages a collection of registrations, tests should confirm each registration is handled independently:

~~~java
@Test
void shouldRegisterEachLocalRegistration() {
    Registration first = mock(Registration.class);
    Registration second = mock(Registration.class);

    lifecycle.register(first);
    lifecycle.register(second);

    verify(serviceRegistry).register(first);
    verify(serviceRegistry).register(second);
}
~~~

This test can live inside RegistrationLifecycleTest. It does not prove two instances appeared in the registry or that DiscoveryClient sees them; it only proves both registrations were sent to ServiceRegistry.

If the application only manages a single local registration, there is no need to fabricate multiple fake registrations to simulate replicas in other processes. Simulate multiple replicas on the DiscoveryClient side using a list of ServiceInstances as shown earlier.

## 11. Checking whether status changes propagate to DiscoveryClient

A unit test with a mocked ServiceRegistry and a mocked DiscoveryClient does not automatically synchronize state between them. When calling:

~~~java
serviceRegistry.setStatus(registration, "OUT_OF_SERVICE");
~~~

the mocked DiscoveryClient will not automatically drop the instance from getInstances(). They are two independent mocks, each returning only what was stubbed on it.

To verify state after a status change:

- Unit test: confirm ServiceRegistry receives the expected setStatus/deregister calls.
- Integration test: use a real Eureka, Consul, or Kubernetes provider in a test environment to confirm the status is recorded and lookups return the expected result.
- End-to-end test: send requests through a LoadBalancer/gateway and confirm the drained instance is no longer selected for new requests.

Never assert that DiscoveryClient immediately removes an instance right after setStatus. Peer replication, registry fetches, health check intervals, and client caches can introduce observable propagation lag.

## 12. Testing deregistration and shutdown

During normal application shutdown, lifecycle callbacks or provider integrations may call deregister. You can test the shutdown coordinator with a mocked ServiceRegistry and verify:

- The right Registration is passed to deregister.
- Status is updated prior to deregister if required by policy.
- Registrations belonging to other services are not deregistered.
- Failures during status change and deregistration are handled according to shutdown policy.

Do not assume every shutdown manages to send deregister. If a process receives kill -9, a host loses power, or the network partitions, deregister may never run or reach the registry. In those cases, providers rely on leases, heartbeat timeouts, health checks, or session expiration to clean up records.

Unit tests can simulate registry exceptions:

~~~java
import static org.mockito.Mockito.doThrow;

doThrow(new RuntimeException("registry unavailable"))
        .when(serviceRegistry)
        .deregister(registration);
~~~

Then verify that the shutdown class logs or propagates the error per contract. If the application must continue shutting down even when deregister fails, the handling logic should express that explicitly rather than accidentally swallowing exceptions.

## 13. Scenarios to include in the test suite

| Scenario | Expected verification |
|---|---|
| DiscoveryClient returns one instance | URI/instance is read properly |
| DiscoveryClient returns multiple instances | All instances are preserved or policy selects properly |
| Empty instance list | Returns empty or intentional business error |
| DiscoveryClient throws exception | Not mistaken for an empty list |
| Registration succeeds | Expected Registration is sent to ServiceRegistry |
| Status change | Provider-specific status is passed accurately |
| Drain begins | Instance is marked out-of-service before drain completes |
| Deregister | Expected Registration is deregistered |
| Multiple registrations | Each registration is operated on without confusion |
| Deregister fails | Shutdown handles failure according to policy |
| Network loss during shutdown | Never assumes deregister always executes |

## 14. Common testing mistakes

| Mistake | Cause | How to fix |
|---|---|---|
| Testing only one instance | Test data does not simulate multiple replicas | Stub getInstances with multiple ServiceInstances |
| Expecting status change to update mock DiscoveryClient | Two mocks do not share state | Use a shared fake or integration tests |
| Using Eureka status for every provider | Status strings have no universal semantics | Configure status per provider |
| Asserting instance vanishes immediately | Ignores replication/fetch/cache lag | Verify eventual propagation in integration tests |
| Using Thread.sleep in unit tests | Tries to wait for non-existent propagation between mocks | Verify call order; use bounded polling in integration tests |
| Using raw ServiceRegistry | Loses type safety and risks passing wrong registration | Use the provider's generic type |
| Testing only graceful shutdown | Ignores crashes or network partitions | Also test timeouts, leases, sessions, and stale entries at integration layer |
| Over-verifying internal details | Tests couple to implementation | Only verify interactions belonging to the guaranteed contract |

## 15. Unit tests vs. integration tests

| Aspect | Unit test | Integration test |
|---|---|---|
| DiscoveryClient returns multiple instances | Mockito stub | Provider returns real list |
| Instance selection logic | Tested with fixed data | Tested with LoadBalancer/integrated provider |
| Calling register/setStatus/deregister | Mock ServiceRegistry | Real registry records changes |
| Status matches provider semantics | Insufficient | Required |
| Instance removed from lookups after deregister | Insufficient | Required |
| Replication/cache latency | Not tested | Should be measured |
| Shutdown during network loss | Simulate exception | Test real timeouts and cleanup |

Unit tests are fast and focused on application logic. Integration tests verify that providers and distributed systems coordinate properly. Both are essential when implementing instance lifecycles.

## 16. Test-writing workflow

1. Identify the logic reading instance lists and the logic managing registrations.
2. Inject DiscoveryClient and ServiceRegistry via constructor or a suitable seam.
3. Mock DiscoveryClient to return one, many, or zero instances.
4. Verify results and instance selection policies.
5. Mock ServiceRegistry with the appropriate generic registration type.
6. Verify register, setStatus, and deregister receive the expected objects and statuses.
7. Use InOrder when state transition order is part of the contract.
8. Test exception handling when the provider is unreachable.
9. Never use sleep to wait for caches or replication in unit tests.
10. Write separate integration tests to verify real state propagates to lookups and LoadBalancer.

~~~mermaid
flowchart TD
    A[Prepare DiscoveryClient mock] --> B[Stub one or more ServiceInstances]
    B --> C[Assert list and selection policy]
    C --> D[Prepare ServiceRegistry mock]
    D --> E[Register registration]
    E --> F[Set unavailable status]
    F --> G[Drain in-flight requests]
    G --> H[Deregister registration]
    H --> I[Verify object, status, and order]
    I --> J[Integration test with real provider]
~~~

## 17. Summary

Testing multiple instances requires simulating DiscoveryClient returning a ServiceInstance list with multiple endpoints, then verifying that business logic preserves or selects instances per policy. Testing the registration lifecycle requires mocking ServiceRegistry and verifying that register, setStatus, and deregister are invoked with the proper registration and status.

DiscoveryClient is the lookup side; ServiceRegistry is the registration management side. Status updates and deregistration are two distinct operations, typically ordered so an instance stops receiving new requests before draining completes. Unit tests do not prove state has propagated through peer replication, health checks, client caches, or EndpointSlices; dedicated integration tests with real providers are needed to verify propagation and LoadBalancer behavior.
