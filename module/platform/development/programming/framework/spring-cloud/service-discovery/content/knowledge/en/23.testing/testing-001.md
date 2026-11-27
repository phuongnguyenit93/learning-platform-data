# Unit Testing with a Mock DiscoveryClient

## 1. Why mock DiscoveryClient?

A Spring Cloud service often uses DiscoveryClient to look up instances by service ID. When testing the calling service's logic, we need to verify that the application handles outcomes properly, such as when instances exist, when no instances exist, or when the discovery provider throws an error.

If every unit test had to start Eureka, Consul, or Kubernetes, the tests would be slow, environment-dependent, and hard to reproduce failures in. We can replace the real DiscoveryClient with a Mockito-controlled mock. The test focuses solely on the behavior of the class under test:

- Which service ID is queried?
- How does the application process the list of instances?
- What happens when the registry has no instances?
- What happens when DiscoveryClient throws an exception?
- Does the application preserve the boundary between “no instances found” and “unable to query discovery”?

In the Spring Cloud Service Discovery module, DiscoveryClient is the shared abstraction for Eureka, Consul, Kubernetes, and other providers. Unit tests built on this abstraction do not need to know which specific provider is running.

## 2. Scope of a unit test

A good unit test checks a single unit of logic with controlled dependencies. In this lesson, the class under test receives DiscoveryClient via its constructor. Mockito creates a mock for that interface and returns the results configured in each test.

| Component | In a unit test |
|---|---|
| Service under test | Real object |
| DiscoveryClient | Mockito mock |
| ServiceInstance | Can be a separate mock |
| Eureka/Consul/Kubernetes | Not started |
| Spring ApplicationContext | No need to create |
| Network, DNS, registry | Not used |

A unit test verifies the application logic when DiscoveryClient returns predefined data. It does not verify network configuration, Kubernetes API permissions, Eureka Server connectivity, or how a provider synchronizes the registry. Those parts require separate integration tests.

## 3. Preparing test dependencies

The examples use JUnit 5, Mockito, and AssertJ. In a Spring Boot project, the test starter dependency usually provides these libraries already:

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

Versions should be managed by the Spring Boot parent/BOM and a compatible Spring Cloud release train. Do not pick a Spring Cloud Commons version independently of the project's dependency management.

If the project uses Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-commons")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Spring Boot Starter Test provides JUnit Jupiter, Mockito, and AssertJ in common setups. If the project does not use this starter, declare JUnit Jupiter, mockito-junit-jupiter, and AssertJ individually with compatible versions.

## 4. Creating a business class that uses DiscoveryClient

Suppose payment-service needs to find another service's URI before sending a request. We extract the discovery lookup into a small class:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.Optional;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class ServiceEndpointResolver {

    private final DiscoveryClient discoveryClient;

    public ServiceEndpointResolver(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Optional<URI> resolveFirstInstance(String serviceId) {
        try {
            return discoveryClient.getInstances(serviceId)
                    .stream()
                    .findFirst()
                    .map(ServiceInstance::getUri);
        } catch (RuntimeException exception) {
            throw new DiscoveryLookupException(serviceId, exception);
        }
    }
}
~~~

Application exception class:

~~~java
package com.example.payment.discovery;

public class DiscoveryLookupException extends RuntimeException {

    public DiscoveryLookupException(String serviceId, Throwable cause) {
        super("Cannot discover instances for service: " + serviceId, cause);
    }
}
~~~

The resolver class does not instantiate a EurekaClient or Kubernetes API client. It only depends on DiscoveryClient, so the provider can be swapped without changing the URI lookup logic.

In this example, an empty list is represented by Optional.empty(). An exception during the discovery query is wrapped into DiscoveryLookupException so the caller can distinguish two situations:

- The registry responded successfully, but no instances currently exist.
- The discovery query operation failed.

Do not silently turn an exception into an empty list. Doing so causes network errors, permission errors, or provider failures to be mistaken for an unregistered service.

## 5. Writing unit tests with Mockito

Create the test in the same package as the class under test, for example:

~~~text
src/test/java/com/example/payment/discovery/ServiceEndpointResolverTest.java
~~~

Test contents:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@ExtendWith(MockitoExtension.class)
class ServiceEndpointResolverTest {

    private static final String SERVICE_ID = "inventory-service";

    @Mock
    private DiscoveryClient discoveryClient;

    private ServiceEndpointResolver resolver;

    @BeforeEach
    void setUp() {
        resolver = new ServiceEndpointResolver(discoveryClient);
    }

    @Test
    void shouldReturnUriWhenInstanceExists() {
        URI expectedUri = URI.create("http://10.0.0.12:8081");
        ServiceInstance instance = mock(ServiceInstance.class);

        when(instance.getUri()).thenReturn(expectedUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.singletonList(instance));

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).contains(expectedUri);
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldReturnEmptyWhenNoInstanceIsRegistered() {
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.emptyList());

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).isEmpty();
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldUseFirstInstanceFromReturnedList() {
        URI firstUri = URI.create("http://10.0.0.12:8081");
        URI secondUri = URI.create("http://10.0.0.13:8081");
        ServiceInstance first = mock(ServiceInstance.class);
        ServiceInstance second = mock(ServiceInstance.class);

        when(first.getUri()).thenReturn(firstUri);
        when(second.getUri()).thenReturn(secondUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Arrays.asList(first, second));

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).contains(firstUri);
    }

    @Test
    void shouldWrapDiscoveryFailureAndKeepOriginalCause() {
        RuntimeException providerFailure =
                new RuntimeException("registry connection failed");
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenThrow(providerFailure);

        Throwable thrown = catchThrowable(
                () -> resolver.resolveFirstInstance(SERVICE_ID));

        assertThat(thrown).isInstanceOf(DiscoveryLookupException.class);
        assertThat(thrown.getCause()).isSameAs(providerFailure);
    }
}
~~~

These tests do not create a Spring ApplicationContext. MockitoExtension initializes the mocks before each test, and setUp creates a real ServiceEndpointResolver instance with the mock passed through the constructor.

## 6. Understanding each test scenario

### 6.1. Instance exists

The test configures DiscoveryClient to return one ServiceInstance. The ServiceInstance is also mocked to return the expected URI. After calling the resolver, the test asserts that the Optional contains the expected URI and that DiscoveryClient was invoked with the correct service ID.

This test verifies the data flow from the discovery result to the result exposed by the business class.

### 6.2. No instance exists

When DiscoveryClient returns an empty list, the resolver returns Optional.empty(). This is a valid outcome if the registry query succeeds but the service has no instances yet.

This scenario must be tested separately from exceptions. An empty list is not a provider failure.

### 6.3. Multiple instances exist

In the example, the resolver picks the first element in the list. The test sets up two instances and verifies that the URI of the first element is used.

The list order returned by a provider is not necessarily a business priority order. In a real application, if instances must be selected by zone, metadata, weight, or load balancing, test the corresponding selection policy instead of assuming the first element is always best.

### 6.4. DiscoveryClient throws an exception

When the provider throws a RuntimeException, the resolver converts it into DiscoveryLookupException and keeps the original exception as the cause. That way, the caller can handle errors at the business boundary while logs and tracing still preserve the root cause.

Avoid asserting the full provider exception message in unit tests if the message depends on version or implementation. Checking the application exception type and its cause is usually more stable.

## 7. Mocking getServices() and other APIs

If a class needs to inspect the service catalog rather than instances, you can mock getServices():

~~~java
when(discoveryClient.getServices())
        .thenReturn(Arrays.asList("payment-service", "inventory-service"));

List<String> services = discoveryClient.getServices();

assertThat(services)
        .contains("payment-service", "inventory-service");
~~~

The snippet above illustrates how to define mock behavior. In an actual test, call the business class that uses DiscoveryClient and assert the outcome of that class. Calling the mock directly and asserting the configured value only verifies that Mockito works, not application logic.

Other methods are mocked following the same principle:

- getInstances(serviceId): returns the defined list of ServiceInstance objects.
- getServices(): returns the list of service IDs.
- description(): returns a description if application logic uses it.
- probe(): can be mocked in DiscoveryClient versions that support this method.

Only stub the methods that the code under test actually calls. Unnecessary stubs make tests harder to read and can cause Mockito strict stubbing errors.

## 8. When should ServiceInstance be mocked?

ServiceInstance is the abstraction describing an endpoint found by discovery. When business logic only needs the URI, you can mock ServiceInstance and stub getUri() as shown above.

If the logic uses multiple attributes, stub each attribute explicitly:

~~~java
import java.util.Collections;
import java.util.Map;

ServiceInstance instance = mock(ServiceInstance.class);

when(instance.getServiceId()).thenReturn("inventory-service");
when(instance.getHost()).thenReturn("10.0.0.12");
when(instance.getPort()).thenReturn(8081);
when(instance.isSecure()).thenReturn(false);
when(instance.getMetadata()).thenReturn(
        Collections.singletonMap("zone", "zone-a"));
~~~

Another option is to construct a real ServiceInstance implementation such as DefaultServiceInstance if the API and constructor of your Spring Cloud Commons version fit. A real object can make tests more readable when many fields are needed; a mock is convenient when only one or two behaviors are needed.

Avoid deep multi-layer mocking when a simple value object will do. The goal is to control external dependencies, not turn the test into a mirror of the implementation.

## 9. Verifying interactions with DiscoveryClient

Mockito lets you verify that the class under test calls the right API:

~~~java
verify(discoveryClient).getInstances("inventory-service");
~~~

You can verify that discovery is not called on invalid input if the business class has validation rules:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;

verifyNoInteractions(discoveryClient);
~~~

Only use verify when the interaction is part of the guaranteed behavior, such as passing the exact service ID or avoiding unnecessary registry calls. Avoid verifying every internal call that has no bearing on the class contract; otherwise tests become brittle during refactoring.

If calling a method a specific number of times is part of the requirement, you can use:

~~~java
import static org.mockito.Mockito.times;

verify(discoveryClient, times(1)).getInstances("inventory-service");
~~~

There is no need to verify invocation counts when the return value and contract already prove the behavior.

## 10. Custom fake or Mockito mock?

These two approaches serve similar purposes but differ in usage:

| Approach | Characteristics | Best suited when |
|---|---|---|
| Mockito mock | Declares behavior and verifies interactions per test | Simple logic, simulating exceptions or multiple return cases |
| Fake implementation | Creates a fake class with in-memory state and data | Multiple tests share stable fake discovery behavior |
| Real DiscoveryClient | Calls a real provider or test environment | Integration tests, verifying configuration and actual communication |

This lesson uses the term "mock" in the sense of replacing the real discovery dependency with a controllable object. For small unit tests, Mockito is usually concise. When many tests need the same updatable fake registry, a dedicated fake implementation can be easier to manage.

If you implement DiscoveryClient yourself, implement all abstract methods of the exact Spring Cloud Commons version in use. The interface can change between versions, so do not copy a fake implementation from a project on another release train without checking the API.

## 11. Why not use @SpringBootTest for this unit test?

@SpringBootTest creates an ApplicationContext and may trigger auto-configuration for discovery providers. If the goal is simply to test a class receiving DiscoveryClient through its constructor, starting the entire context adds no commensurate value.

You can use @ExtendWith(MockitoExtension.class) to create mocks and instantiate the class under test directly. This approach:

- Runs fast and requires no registry.
- Does not depend on profiles or environment configuration files.
- Makes simulating provider errors easy.
- Tests only the behavior of the target class.

If you want to verify Spring wiring, bean conditions, auto-configuration, or Eureka/Consul/Kubernetes settings, write a separate integration test or context test. Do not call a test that boots the context a unit test just because it contains one mock.

## 12. Common testing mistakes

| Mistake | Why it happens | How to fix |
|---|---|---|
| Test calls real registry | Uses real provider bean or boots Spring context | Inject mock DiscoveryClient directly |
| Result is always empty | Forgot to stub getInstances(serviceId) | Configure when(...).thenReturn(...) |
| Stub is never used | Service queries a different service ID or API | Check arguments and verify calls |
| NullPointerException in test | Mock ServiceInstance did not stub getUri() | Stub the attributes used by the code |
| Swallowing provider errors | Code turns exception into an empty list | Keep error path separate from no-instance path |
| Test depends on registry order | Assumes the first instance always has priority | Test an explicit instance selection policy |
| Slow and flaky test | Unnecessary @SpringBootTest usage | Use MockitoExtension and constructor injection |
| Strict stubbing failure | Stub declared but unused by the code | Remove unused stub or fix test input |

## 13. What unit tests do not prove

Mocking DiscoveryClient does not verify:

- Whether Eureka Client connects and fetches the registry successfully.
- Whether Consul returns passing services according to health checks.
- Whether the Kubernetes ServiceAccount has permissions to list/watch Services or EndpointSlices.
- Whether DNS, TLS, NetworkPolicies, and instance ports are configured properly.
- Whether the registry cache is fresh or stale.
- Whether the real LoadBalancer selects instances by zone or retry policy as configured.

Those aspects require integration tests with a real provider or a test Kubernetes environment. Unit tests and integration tests complement each other: unit tests check application logic, while integration tests verify coordination with the real discovery system.

## 14. Unit testing workflow

1. Identify the business class that calls DiscoveryClient.
2. Ensure DiscoveryClient is injected via constructor or a replaceable seam.
3. Create the test with JUnit 5 and enable MockitoExtension.
4. Mock DiscoveryClient and stub only methods used by the code.
5. Create a mock ServiceInstance or suitable value object.
6. Test results for a single instance, multiple instances, and an empty list.
7. Test how the application handles provider exceptions.
8. Verify the service ID or key interactions using verify.
9. Run the test standalone, ensuring no Eureka, Consul, Kubernetes, or network is needed.
10. Write separate integration tests if real providers and configuration need verification.

~~~mermaid
flowchart TD
    A[Select business class to test] --> B[Inject DiscoveryClient]
    B --> C[Mock DiscoveryClient with Mockito]
    C --> D[Stub getInstances results]
    D --> E[Execute business method]
    E --> F{Expected outcome?}
    F -->|Instance exists| G[Assert returned URI or data]
    F -->|Empty list| H[Assert Optional.empty]
    F -->|Provider exception| I[Assert app error and cause]
    G --> J[Verify required interactions]
    H --> J
    I --> J
~~~

## 15. Summary

Mocking DiscoveryClient enables testing service lookup logic without starting a real registry. With JUnit 5 and Mockito, you can control getInstances results, create ServiceInstance mocks, and verify empty lists, multiple instances, and provider exceptions.

Keep a clear boundary between having no instances and failing to query discovery. Use constructor injection to swap dependencies easily, only stub methods that are actually invoked, and avoid booting the Spring context when the goal is only to unit test a single class. Behaviors tied to networking, permissions, registry caches, and specific providers should be verified in separate integration tests.
