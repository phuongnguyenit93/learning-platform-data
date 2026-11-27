# Role of InetUtils and HostInfo

> **Chapter:** Identity and Networking  
> **Module:** SPRING_CLOUD_CORE

In an application running on a machine with multiple network interfaces, obtaining an IP address via a simple call like `InetAddress.getLocalHost()` does not always yield an address usable by other services. A host may simultaneously have loopback, LAN NICs, VPNs, Docker/Kubernetes interfaces, and virtual interfaces. If the application advertises the wrong address, the service registry may store an unreachable endpoint, causing service discovery to find the instance while requests to that instance fail.

Spring Cloud Commons provides **`InetUtils`** to locate suitable host information from network interfaces and **`InetUtils.HostInfo`** to represent the selected hostname and IP address. These two components support integrations that need to know the application's address. They help standardize host detection, but they do not register services themselves, create addresses routable across NAT, or replace the deployment platform's network configuration.

## 1. Why is InetUtils needed?

A server or container can see many network addresses:

- `127.0.0.1` or `::1`: loopback, used only within the host/network namespace.
- Ethernet or Wi-Fi card addresses.
- VPN addresses.
- Docker bridge or Kubernetes CNI interface addresses.
- Virtual interface addresses created by a hypervisor or networking software.
- IPv4 or IPv6 addresses assigned to the same interface.

If the application picks the first address returned by the OS, the result may not suit service advertisement. For instance, an instance inside a container might pick a loopback address or a bridge IP reachable only from a specific network.

`InetUtils` provides a way to find a non-loopback address according to configurable policies such as ignoring interfaces, preferring network ranges, and accepting only site-local addresses. As a result, applications can select host information more consistently across environments.

### 1.1. Not every IP address can serve as a service endpoint

A valid IP address on a machine is not necessarily reachable by clients elsewhere.

| Address type | Example | Implications when advertised |
| --- | --- | --- |
| Loopback | `127.0.0.1`, `::1` | Points only to the instance's own network namespace; usually not used for instance discovery |
| Private IPv4 | `10.20.1.15`, `192.168.10.8` | Usable in private networks if clients have routes to that range |
| Link-local | `169.254.x.x` | Link-local scope; generally unsuitable for standard service communication |
| Public IPv4 | A public IP address | Reachable if firewall, routing, and NAT allow it |
| IPv6 global | Globally routable IPv6 address | Requires client, registry, and network infrastructure IPv6 support |
| Container bridge IP | E.g., `172.18.0.4` | May only be reachable within that bridge or overlay network |

Address selection must align with the deployment topology. In Kubernetes, an application typically needs to advertise the Pod address or a platform-provided address, depending on how service registration is configured. A private IP does not automatically mean an IP reachable from every network.

## 2. What are InetUtils and HostInfo?

`InetUtils` belongs to the `org.springframework.cloud.commons.util` package. It provides operations to find non-loopback addresses and convert address details into a host object.

Commonly used API:

~~~java
InetUtils.HostInfo hostInfo =
        inetUtils.findFirstNonLoopbackHostInfo();
~~~

`InetUtils.HostInfo` is a data type holding the selected host info, typically consisting of:

- `hostname`: the hostname resolved from the address.
- `ipAddress`: the IP address represented as a string.

Both values can be read via getters:

~~~java
String hostname = hostInfo.getHostname();
String ipAddress = hostInfo.getIpAddress();
~~~

Common APIs of `InetUtils`:

| API | Role |
| --- | --- |
| `findFirstNonLoopbackAddress()` | Finds a suitable non-loopback network address |
| `findFirstNonLoopbackHostInfo()` | Finds the address and returns the corresponding host information |
| `close()` | Releases internal resources of InetUtils when the bean is closed |

Exact API names and details may vary across Spring Cloud Commons versions. When writing code for a specific release train, check the Javadoc/source of the exact dependency version in use.

### 2.1. Distinguishing InetUtils from InetAddress

`java.net.InetAddress` is Java's standard API for representing IP addresses and resolving hostnames. It does not automatically apply network interface selection policies tailored for Spring Cloud applications.

`InetUtils` adds host selection policies across the system's interfaces. You can think of them as:

- `InetAddress` represents network addresses and supports name resolution.
- `InetUtils` finds a suitable address according to configured policies.
- `HostInfo` packages the selected hostname and IP for other components to use.

Therefore, do not replace `InetUtils` with `InetAddress.getLocalHost()` when the requirement is to select a non-loopback address according to Spring Cloud policies.

## 3. Using InetUtils in an application

When Spring Cloud Commons is on the classpath and the corresponding auto-configuration is active, the application can inject the `InetUtils` bean.

Example component logging host info after the application starts:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.commons.util.InetUtils;
import org.springframework.stereotype.Component;

@Component
public class HostInfoReporter implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(HostInfoReporter.class);

    private final InetUtils inetUtils;

    public HostInfoReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    @Override
    public void run(ApplicationArguments args) {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        log.info("Selected host information: hostname={}, ipAddress={}",
                hostInfo.getHostname(), hostInfo.getIpAddress());
    }
}
~~~

This example is only for observing host info. It does not replace configuring the advertised address for service registration. If an application needs to register a specific address, inspect the registration mechanism used by the discovery client and identify where it obtains hostname/IP from.

Avoid re-scanning interfaces on every request. Host info is normally determined during startup or when network configuration changes through a controlled deployment process.

### 3.1. Do not manually close container-managed InetUtils

If `InetUtils` is created and managed by Spring as a bean, the ApplicationContext is responsible for invoking the corresponding destruction callback. Do not manually call `inetUtils.close()` after every read of `HostInfo`. Closing the bean prematurely can prevent other components from using its internal resources.

If you instantiate `InetUtils` manually outside the Spring container, the code creating the instance is responsible for closing it when no longer needed.

## 4. Configuring interface and address selection

`InetUtils` has configuration properties under the `spring.cloud.inetutils` prefix. These properties help exclude unsuitable interfaces, prefer desired IP ranges, and define fallback values.

Example:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
        - br-.*
      preferred-networks:
        - '10\.20\..*'
        - '192\.168\.50\..*'
      use-only-site-local-interfaces: true
      timeout-seconds: 2
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

The regex values in the example are wrapped in YAML single quotes to preserve backslashes. Adjust interface names and network ranges to match real infrastructure.

### 4.1. ignored-interfaces

`ignored-interfaces` is a list of patterns used to skip interfaces by name. Example:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
        - tun.*
~~~

This can be used to ignore a bridge or VPN interface that must not serve as the advertised address. Patterns match interface names; they are not a list of IP addresses.

Do not ignore all virtual interfaces mechanically. On some platforms, a virtual or CNI interface is the valid network path for Pods to communicate. Before adding a pattern, identify what traffic that interface carries.

### 4.2. preferred-networks

`preferred-networks` lets you prioritize addresses matching network patterns. Example:

~~~yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
        - '192\.168\.50\..*'
~~~

If a host has multiple interfaces, this configuration helps pick an address in the desired range. Patterns are regular expressions, not CIDR notation. For example, `10.20.0.0/16` should not be entered as if InetUtils understood CIDR natively; write an appropriate regex or use the platform's dedicated network configuration mechanism if exact CIDR control is needed.

If no address matches a preferred pattern, the outcome also depends on other filters and the fallback logic of the InetUtils version in use. Do not assume a preferred range always exists in every environment; verify the outcome at startup.

### 4.3. use-only-site-local-interfaces

`use-only-site-local-interfaces` restricts selection to addresses classified by Java as site-local. For IPv4, this group typically includes private ranges such as `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`.

This property can be useful when applications communicate only within a private network. However, site-local does not mean "reachable by every other service." A private address can still be isolated by subnets, network policies, firewalls, or routing.

If the application needs to advertise a public IP, a NAT address, or a platform-assigned address, do not enable this filter without verifying behavior. For complex networking requirements, configuring the advertised hostname/IP directly on the discovery client or platform may be necessary.

### 4.4. timeout-seconds

`timeout-seconds` caps the wait time for certain host info resolution operations, especially when resolving a hostname from an address. Slow reverse DNS lookups can prolong host discovery.

Set a bounded timeout so host resolution does not stall startup for too long. A smaller value reduces wait time, though it may leave the hostname unresolved; the IP remains distinct network info that can still identify the endpoint.

Do not treat this timeout as a global timeout for all application requests or for service discovery as a whole.

### 4.5. default-hostname and default-ip-address

When no suitable address is found or host info cannot be resolved as expected, fallback values may be used:

~~~yaml
spring:
  cloud:
    inetutils:
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

Fallback values give the application a deterministic result instead of empty info in certain cases. However, `localhost` and `127.0.0.1` are rarely suitable endpoints to register in a multi-instance environment. If the registry receives a loopback address, other services may mistakenly call their own local machine.

In production, configure things so that failing to find a suitable advertised address becomes an actionable signal rather than silently registering an unreachable default.

## 5. Hostname and IP address have different meanings

Hostname is a name resolved from an address or supplied by the environment; IP address is a network address. The two values may be related, but they are not interchangeable in all situations.

Example:

| HostInfo field | Example | Meaning |
| --- | --- | --- |
| `hostname` | `order-7f8c9d.internal` | Hostname resolvable by DNS or internal infrastructure |
| `ipAddress` | `10.20.1.15` | IP address of the selected interface |

Hostname may depend on DNS, search domains, and reverse lookup. An address might lack a proper PTR record; the returned hostname might also be unresolvable by other clients.

IPs can change when containers or instances are recreated. Do not rely solely on an IP as the durable identity of an instance if the platform allocates IPs dynamically.

### 5.1. Service identity vs. instance identity

In Spring Cloud, distinguish:

| Information | Example | Role |
| --- | --- | --- |
| Application/service name | `order-service` | Logical name for clients to find the service |
| Hostname | `order-7f8c9d.internal` | Hostname of the instance |
| IP address | `10.20.1.15` | Network address of the instance |
| Port | `8080` | Port on which the instance receives traffic |
| Instance ID | `order-service:pod-7f9c` | Identifier of a specific running copy in the registry |

`InetUtils` and `HostInfo` provide hostname/IP information. Service name, port, instance ID, metadata, and health status are normally supplied by the application, discovery client, or deployment platform.

Do not use hostname or IP as a substitute for `spring.application.name`. A single service can have multiple instances with different hostnames/IPs yet share the same logical name.

## 6. Relationship with service discovery and service registration

Spring Cloud Commons defines common abstractions for service discovery and registration. Implementations such as Eureka, Consul, or another registry may need hostname/IP when registering an instance.

`InetUtils` can serve as a source of host info for some integrations or be used by the application to set advertised values. However:

- `InetUtils` does not register the instance into the registry on its own.
- `HostInfo` does not contain all registration metadata.
- Selecting an IP does not open firewalls or create routes.
- Having the registry store an endpoint does not guarantee the endpoint is reachable by every client.
- How a discovery client chooses hostname/IP depends on its implementation and configuration.

Before changing `spring.cloud.inetutils`, determine which hostname/IP source the discovery client actually uses. Some implementations let you configure a dedicated advertised hostname or IP; specific properties vary between Eureka, Consul, and other registries.

### 6.1. Example configuring host and service name

An application can declare its own service name:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
~~~

Here `spring.application.name` sets the application's logical name, while InetUtils finds a host per the network policy. The discovery client must be configured compatibly to register the right address. Setting preferred networks alone does not guarantee every discovery client will advertise the selected IP in the exact same way.

If the environment provides a platform-supplied advertised address, use the discovery client's official integration properties or platform-injected environment variables. Do not force InetUtils to pick an unreachable interface merely because that address looks valid locally on the host.

## 7. Multi-network-interface scenarios

Suppose a VM has the following interfaces:

| Interface | Address | Purpose |
| --- | --- | --- |
| `lo` | `127.0.0.1` | Loopback |
| `eth0` | `10.20.1.15` | Internal service network |
| `tun0` | `10.8.0.2` | Admin VPN |
| `docker0` | `172.18.0.1` | Docker bridge |

If services in the cluster communicate over the `10.20.0.0/16` network, the application can prefer this range and ignore the VPN or Docker bridge interfaces:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - tun.*
        - docker0
      preferred-networks:
        - '10\.20\..*'
      use-only-site-local-interfaces: true
~~~

This configuration is only an example. Actual interface names and addresses vary by OS, container runtime, and network plugin. Inspect from inside the exact network namespace in which the JVM runs.

If the service runs inside a container, interface discovery only sees what is visible inside the container. It does not automatically know the node's public IP or an external load balancer address. When advertising an address different from the local interface address, obtain that value from the platform or discovery client configuration.

## 8. IPv4, IPv6, DNS, and practical limits

### 8.1. IPv4 and IPv6

A single interface can hold multiple addresses, including IPv4 and IPv6. Clients, registry, DNS, and network policies must agree on the address family they support.

Do not assume every IPv6 address can be placed directly into a URL without bracket handling. For instance, an IPv6 literal in a URL typically takes the form `http://[2001:db8::10]:8080`.

If the application supports IPv4 only, verify the selected address and configure the discovery client accordingly. Do not manually slice or transform address strings to force an IPv6 address into IPv4.

### 8.2. DNS and reverse lookup

Hostnames can be resolved from IPs via DNS or the OS name service mechanism. In container environments, reverse DNS may not be configured; the resulting hostname may be a short name, an internal name, or a default value.

Verify both forward lookup (hostname to IP) and reverse lookup (IP to hostname) if hostnames are used in registration. A hostname that only reverse-resolves inside an internal subnet may not help clients in other networks.

### 8.3. NAT and advertised addresses

If an instance sits behind NAT, the private address on the interface can differ from the address external clients see. InetUtils only inspects interfaces in the process's environment; it does not query routers to infer a public/NAT address.

In that scenario, establish a clear source of truth for the advertised address: platform configuration, DNS, service mesh, load balancer, or a discovery provider-specific property.

### 8.4. Dynamic addresses and instance lifecycle

In container orchestration, a Pod's IP can change after rescheduling. The registry must update registrations when an instance stops and a new instance starts. HostInfo is not a mechanism for continuously tracking network address changes.

If an interface address changes while the JVM is still running, do not assume a HostInfo value read at startup updates automatically. A refresh/re-registration mechanism supported by the discovery integration, or a restart/rolling replacement per platform procedures, is required.

## 9. Inspecting host info in the runtime environment

When an instance registers the wrong address, inspect from the exact environment where the JVM runs:

1. List actual interfaces and addresses.
2. Identify which interface carries inter-service traffic.
3. Check ignored and preferred patterns.
4. Check the site-local filter.
5. Confirm whether the hostname resolves in the required DNS.
6. Compare HostInfo with the address the discovery client actually registers.
7. Test routes, firewalls, and network policies from a client in the target network.

On Linux, common commands to inspect interfaces:

~~~bash
ip address
ip route
hostname
getent hosts "$(hostname)"
~~~

These commands are only for diagnostics in Linux environments; minimal containers may not include all of them. Never invoke these commands from Java code or on every request.

### 9.1. Controlled logging of HostInfo

You can log the selected hostname and IP at startup:

~~~java
InetUtils.HostInfo hostInfo =
        inetUtils.findFirstNonLoopbackHostInfo();

log.info("Host selected for diagnostics: hostname={}, ipAddress={}",
        hostInfo.getHostname(), hostInfo.getIpAddress());
~~~

This information helps cross-check against registration metadata. If internal IPs or hostnames expose sensitive topology details, restrict log access and avoid leaking them into public logs.

## 10. Testing InetUtils configuration

Do not write tests that depend on a developer laptop's or CI runner's interfaces expecting a fixed IP. Network addresses change by runner, VPN, container, and OS.

You can test the configuration bound into `InetUtilsProperties` inside a Spring context with explicit values:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.commons.util.InetUtilsProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.inetutils.ignored-interfaces[0]=docker0",
        "spring.cloud.inetutils.preferred-networks[0]=10\\.20\\..*",
        "spring.cloud.inetutils.use-only-site-local-interfaces=true",
        "spring.cloud.inetutils.timeout-seconds=2"
})
class InetUtilsPropertiesTest {

    @Autowired
    InetUtilsProperties properties;

    @Test
    void bindsNetworkSelectionPolicy() {
        assertThat(properties.getIgnoredInterfaces())
                .contains("docker0");
        assertThat(properties.getPreferredNetworks())
                .contains("10\\.20\\..*");
        assertThat(properties.isUseOnlySiteLocalInterfaces()).isTrue();
        assertThat(properties.getTimeoutSeconds()).isEqualTo(2);
    }
}
~~~

This example tests policy binding rather than asserting a fixed IP. Getter names and injecting `InetUtilsProperties` depend on the Spring Cloud Commons version; if your version alters the API or binds properties differently, adjust the test to match your exact dependency.

### 10.1. Integration testing in a representative environment

Beyond binding tests, include smoke tests on containers or staging to confirm:

- HostInfo does not return loopback unexpectedly.
- The selected IP belongs to an allowed network range.
- Hostname resolves from the clients that need access.
- The registry receives the expected advertised address and port.
- A client from an actual subnet connects successfully.
- When no suitable interface exists, fallback values do not cause the instance to register silently with invalid info without warning.

Network integration tests should verify actual connectivity from the client side, not merely assert that an IP string looks well-formed.

## 11. Common mistakes and how to avoid them

1. **Selecting loopback:** inspect interfaces and policies; never advertise `127.0.0.1` or `::1` to clients on other instances.
2. **Selecting Docker bridge/VPN by mistake:** use ignored interfaces or preferred networks after identifying the exact interface for service traffic.
3. **Treating CIDR as regex:** preferred networks use regex patterns; convert to a proper regex or use another network configuration mechanism.
4. **Enabling site-local when a public address is needed:** site-local filters by address type and does not replace platform-provided advertised addresses.
5. **Assuming private IPs are always reachable:** check routes, firewalls, subnets, and network policies.
6. **Relying on unstable reverse DNS:** verify forward/reverse lookups and configure an explicit hostname if discovery requires a stable name.
7. **Confusing HostInfo with service identity:** service name, port, and instance ID must be supplied separately.
8. **Assuming InetUtils registers the service itself:** the discovery client or registration integration is responsible for sending metadata to the registry.
9. **Using localhost fallback in production:** validate the advertised address before allowing the instance to register.
10. **Assuming HostInfo updates automatically when the network changes:** re-resolve the host and perform re-registration or replace the instance per deployment lifecycle.

## 12. Address selection checklist for a Spring Cloud service

When deploying a service in the `SPRING_CLOUD_CORE` module, follow these steps:

1. Identify which clients need to access the instance and which subnets/networks they reside in.
2. Inspect network interfaces from inside the actual VM or container.
3. Decide whether to restrict to site-local addresses only.
4. Ignore interfaces that do not carry service traffic.
5. Prefer network ranges routable by clients.
6. Set intentional timeout and fallback values.
7. Read HostInfo and cross-check with the hostname/IP registered by the discovery client.
8. Verify real connectivity from a client in the target network.
9. Define how IP changes or instance recreations are handled.
10. Emit enough logs/metrics for diagnostics without exposing sensitive topology details.

**Key takeaway:** `InetUtils` helps locate a suitable host address from network interfaces according to configuration policies; `InetUtils.HostInfo` packages the chosen hostname and IP. They support host detection in the Spring Cloud Commons ecosystem, while service name, instance ID, port, registration, and routability belong to other parts of the system. For service discovery to work reliably, choose an address actually reachable by clients within the **SPRING_CLOUD_CORE** network topology.
