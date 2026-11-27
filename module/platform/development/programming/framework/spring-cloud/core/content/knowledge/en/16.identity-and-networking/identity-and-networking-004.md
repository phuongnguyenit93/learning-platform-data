# Selecting a network address on multi-interface hosts

A server can simultaneously have multiple network interfaces: Ethernet cards, Wi-Fi, VPN, loopback, Docker bridges, Kubernetes interfaces, or NICs dedicated to a management network. Each interface can carry one or more IPv4/IPv6 addresses. When a Spring Cloud application registers with a service registry, it must advertise the right address so other services can connect.

If the application picks the wrong address, the registry may still accept the registration, yet clients end up calling an unroutable address. A `127.0.0.1` address, a Docker bridge IP, or an IP reachable only from the management network can all cause discovery to return an unusable instance.

Spring Cloud Commons provides `InetUtils` and the `spring.cloud.inetutils` configuration group to select suitable host information. However, you must distinguish **the address the web server binds to for listening** from **the address the application advertises to the registry**. These two addresses serve different purposes and do not necessarily match.

This lesson belongs to the **Identity and Networking** chapter of **SPRING_CLOUD_CORE**. The content focuses on selecting an address when multiple interfaces exist, configuring `preferred-networks` and `ignored-interfaces`, overriding addresses per provider, and verifying registration in real environments.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish network interface, IP address, hostname, bind address, and advertised address.
- Explain why OS interface ordering can cause an application to pick the wrong IP.
- Describe the role of `InetUtils` and `InetUtilsProperties` in Spring Cloud Commons.
- Configure `spring.cloud.inetutils.preferred-networks` to prefer desired IP ranges.
- Configure `spring.cloud.inetutils.ignored-interfaces` to exclude unsuitable interfaces.
- Understand the limitations of `use-only-site-local-interfaces` and fallback values.
- Distinguish common host discovery configuration from provider-specific configuration such as Eureka or others.
- Distinguish `server.address` from the service registration address.
- Choose appropriate addresses in Docker, Kubernetes, VPN, and dual-stack IPv4/IPv6 setups.
- Test the selected address and verify that other clients can actually connect.

## 2. Distinguishing networking concepts

Before configuring Spring Cloud, determine precisely which type of address the application requires.

| Concept | Meaning | Example |
| --- | --- | --- |
| Network interface | Network device/interface exposed by the OS to the process | `eth0`, `ens160`, `wlan0`, `tun0`, `docker0` |
| IP address | Address assigned to an interface | `10.20.5.18`, `192.168.1.30`, `2001:db8::18` |
| Hostname | Machine name resolved via DNS or another name resolution mechanism | `checkout-01.internal` |
| Bind address | Local address on which the server opens a listening socket | `0.0.0.0`, `127.0.0.1`, `10.20.5.18` |
| Advertised address | Address the application publishes to the registry or other clients | `10.20.5.18:8080`, `checkout.internal:8080` |
| Outbound route/source address | Interface and source IP chosen by OS routing/sockets for outgoing connections | VPN, LAN NIC, or policy-based route |
| Service ID | Logical name used by clients to find the service | `checkout-service` |

`InetUtils` primarily helps Spring Cloud determine host/IP information for the machine running the application. It does not replace DNS, routing tables, firewalls, service meshes, or web server bind configuration.

### 2.1. Bind address differs from advertised address

Example:

```yaml
server:
  address: 0.0.0.0
  port: 8080
```

`0.0.0.0` instructs the server to listen on all suitable local IPv4 addresses. This is not an address to register for other services to call. Clients cannot use `0.0.0.0` as a concrete connection target.

Meanwhile, the registry needs an address routable from consumers' networks, for example:

```text
checkout-service -> 10.20.5.18:8080
```

An application can bind on `0.0.0.0` while advertising `10.20.5.18`. This is a common setup when a host has multiple interfaces.

### 2.2. Advertised address does not determine the outbound NIC

`spring.cloud.inetutils.preferred-networks` helps Spring Cloud prioritize a host/IP when building host info for compatible integrations. This property does not modify routing tables, alter policy routing, or force all HTTP, JDBC, Kafka, or messaging connections to exit via the selected interface.

When outbound traffic must be forced over a VPN or a specific NIC, configure routes in the OS/container/network platform or configure the corresponding socket/client. Never treat `InetUtils` as a packet-routing control mechanism. After choosing an advertised address, always verify bidirectional routes, firewalls, NAT, and reachability from the consumer's exact network namespace.
### 2.3. Loopback addresses are unsuitable for cross-host service discovery

Addresses such as `127.0.0.1` or `::1` point only to the process's own network namespace. If the registry advertises `127.0.0.1:8080`, another service calling that address connects to its own loopback rather than the host running `checkout-service`.

Loopback is useful for local communication on the same host, but should not be the advertised address for services on other hosts/containers.

## 3. Why do multi-interface hosts easily pick the wrong address?

A VM or server may have interfaces like:

```text
lo       127.0.0.1
ens160   10.20.5.18
ens192   172.20.0.12
docker0  172.17.0.1
tailscale0 100.80.10.4
```

Those addresses can serve different purposes:

- `ens160`: application network reachable by internal services.
- `ens192`: backup or management network.
- `docker0`: bridge between host and containers.
- `tailscale0`: VPN overlay accessible only by nodes on the VPN.
- `lo`: loopback.

If the application picks the first non-loopback IP in OS-returned order, it might choose `172.20.0.12` or `100.80.10.4` instead of `10.20.5.18`.

Interface enumeration order is not a stable contract across machines or across deployments. Do not rely on the assumption that an interface named `eth0` always precedes others, or that the first address is always one consumers can use.

### 3.1. Common sources of confusion

- Multiple physical NICs active at once.
- VPN enabled after the application starts.
- Docker or container runtimes creating bridge interfaces.
- Host having both IPv4 and IPv6 simultaneously.
- Management interface having a private address with no route to the service network.
- Host having multiple subnets or multiple default gateways.
- DNS returning multiple addresses with different clients resolving via different network paths.

The problem to solve is not merely picking a "nice-looking" IP. The advertised address must **be routable and reachable by actual consumers**.

## 4. InetUtils in Spring Cloud Commons

Spring Cloud Commons includes the `InetUtils` utility in package:

```java
org.springframework.cloud.commons.util.InetUtils
```

This utility helps resolve host info for the machine running the application, including hostname and IP address. Related settings bind from:

```text
spring.cloud.inetutils
```

Common properties:

| Property | Effect |
| --- | --- |
| `spring.cloud.inetutils.preferred-networks` | List of regexes to prioritize addresses belonging to desired networks |
| `spring.cloud.inetutils.ignored-interfaces` | List of regexes to skip interfaces with matching names |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | Only consider addresses classified by Java as site-local |
| `spring.cloud.inetutils.default-ip-address` | Fallback address if no suitable address is found |
| `spring.cloud.inetutils.default-hostname` | Fallback hostname when host cannot be determined |
| `spring.cloud.inetutils.timeout-seconds` | Time limit for host determination operations depending on implementation |

Exact names and behavior should be checked against the Spring Cloud Commons version the application uses. This property group governs common host discovery; discovery providers may still have their own override settings.

### 4.1. How does InetUtils find an address?

Conceptually, address selection typically follows these steps:

1. Retrieve the list of interfaces visible to the JVM's network namespace.
2. Skip inactive interfaces or interfaces excluded by filtering rules.
3. Skip loopback and interfaces matching `ignored-interfaces`.
4. Inspect addresses bound to the remaining interfaces.
5. Apply the site-local rule if enabled.
6. Prioritize addresses matching `preferred-networks`.
7. If no suitable address is found, fall back to the configured default address.

Exact interface traversal and address selection details belong to the active release's implementation. Do not rely on OS enumeration order when multiple addresses match.

### 4.2. HostInfo

`InetUtils` can return host information via `HostInfo`, containing hostname and IP address. Spring Cloud uses this info in components that need to identify the local host.

Illustrative example:

```java
@Component
public class LocalHostReporter {

    private final InetUtils inetUtils;

    public LocalHostReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    public void report() {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        String hostname = hostInfo.getHostname();
        String ipAddress = hostInfo.getIpAddress();
        // Report only non-sensitive host metadata.
    }
}
```

This snippet helps inspect the output of the host selection algorithm. It does not prove the IP is reachable from every consumer; routes, firewalls, and provider registration must still be verified.

## 5. Prioritizing network ranges with preferred-networks

When a host has multiple addresses, `preferred-networks` lets you specify which address ranges should be preferred. Values are regular expressions matched against network addresses according to `InetUtils` rules.

For example, a machine has application subnet `10.20.0.0/16`, while bridge and VPN use other ranges:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.].*'
```

The application will prefer an address matching `10.20.*` if a suitable address exists.

### 5.1. Preferring multiple ranges

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.].*'
        - '^192[.]168[.]50[.].*'
```

This example allows addresses in the application subnet `10.20.*` or subnet `192.168.50.*` to be treated as preferred candidates.

If multiple interfaces have matching addresses, do not assume YAML line order is the final selection order. Outcome also depends on the interface/address traversal algorithm of the running version. Configure things so only one range matches if selecting one exact NIC is mandatory.

### 5.2. More specific regexes are safer

An overly broad regex:

```yaml
preferred-networks:
  - '^10.*'
```

can match many `10.0.0.0/8` subnets, including unintended management or overlay networks.

Narrow it down by subnet:

```yaml
preferred-networks:
  - '^10[.]20[.]5[.].*'
```

If addresses can change within a subnet while the subnet itself stays fixed, a subnet-scoped regex balances stability and flexibility.

### 5.3. Regexes and IPv6

IPv6 addresses have a different string format from IPv4, for example:

```text
2001:db8:20::18
fd20:5::18
fe80::1234
```

If IPv6 must be prioritized, regexes must match how addresses are formatted when `InetUtils` evaluates them. Avoid writing IPv4 regexes and assuming they filter IPv6 as well. Verify on the exact JVM, OS, and Spring Cloud release.

## 6. Excluding interfaces with ignored-interfaces

`ignored-interfaces` excludes interfaces by name. Values are a list of regexes, useful when a host has bridges, VPNs, or management interfaces that the service must not advertise.

Example:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^br-.*'
        - '^veth.*'
        - '^tun[0-9]+$'
```

Meaning:

- Ignore the default `docker0` bridge.
- Ignore bridge interfaces whose names start with `br-`.
- Ignore virtual Ethernet pairs starting with `veth`.
- Ignore tunnel interfaces named `tun0`, `tun1`, ...

Interface names differ across Linux, Windows, macOS, and cloud environments. On Windows, display names may be `Ethernet`, `Wi-Fi`, or adapter names set by a hypervisor/VPN. Obtain the exact real names before writing regexes.

### 6.1. Combining preferred-networks and ignored-interfaces

In the example:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^tailscale[0-9]*$'
      preferred-networks:
        - '^10[.]20[.]5[.].*'
```

The two settings solve two distinct tasks:

- `ignored-interfaces` excludes unwanted interfaces.
- `preferred-networks` prioritizes addresses in the desired subnet among the remaining addresses.

Do not treat these two lists as routing tables. They do not create routes, change gateways, or configure firewalls.

### 6.2. Do not exclude interfaces by name if names are unstable

In cloud or container setups, interface names can vary by platform. If names are unstable, filtering by network range via `preferred-networks` is usually easier to manage. If both names and subnets can change, consider configuring an explicit advertised IP/hostname at the provider or platform layer.

## 7. Using only site-local interfaces

You can enable:

```yaml
spring:
  cloud:
    inetutils:
      use-only-site-local-interfaces: true
```

This setting restricts selection to addresses classified by Java as site-local. It can help when services communicate only on internal networks and should never pick a public address.

However, do not enable it mechanically:

- A service may need a public address or an overlay address not classified as expected.
- Java's site-local classification is not synonymous with every "private network" definition in infrastructure.
- For IPv6, Java API's site-local should not be conflated with all Unique Local addresses (`fc00::/7`).
- A site-local address can still lack a route or be blocked by a firewall from consumers.

Use `preferred-networks` to target a specific subnet when you know which network should be advertised. `use-only-site-local-interfaces` is a broader filter, not a substitute for subnet design.

## 8. Fallback values do not replace network configuration

You can configure:

```yaml
spring:
  cloud:
    inetutils:
      default-hostname: checkout-fallback
      default-ip-address: 10.20.5.18
```

Fallbacks are helpful when no suitable host address can be determined, but understand their limits:

- They do not assign an IP to an OS interface.
- They do not create routes or open firewalls.
- They do not prove the address still exists or belongs to the current instance.
- If a fallback IP becomes stale, the registry may advertise an unreachable address.

Only configure fallbacks when that address is stably managed by deployment infrastructure. Otherwise, let the application fail or use explicit provider configuration to avoid registering a wrong address.

## 9. Common host discovery configuration vs. provider overrides

`spring.cloud.inetutils.*` affects general host info determination. However, each discovery provider may allow declaring a dedicated hostname or IP.

### 9.1. Example with Eureka

Eureka has its own instance properties:

```yaml
eureka:
  instance:
    prefer-ip-address: true
    ip-address: 10.20.5.18
```

Commonly used properties:

| Property | Meaning |
| --- | --- |
| `eureka.instance.hostname` | Hostname used by the Eureka instance |
| `eureka.instance.ip-address` | IP address assigned to the instance |
| `eureka.instance.prefer-ip-address` | Prefer publishing URL based on IP instead of hostname |

If `ip-address` is set explicitly, make sure that IP belongs to an interface reachable by consumers. `prefer-ip-address=true` does not fix routes or verify reachability.

### 9.2. When to use InetUtils, when to override per provider?

| Need | Approach |
| --- | --- |
| Multiple services share host discovery and the same preferred subnet | Configure `spring.cloud.inetutils.preferred-networks` |
| Exclude unsuitable bridge/VPN interfaces for general host selection | Configure `spring.cloud.inetutils.ignored-interfaces` |
| Only one provider needs a different advertised address | Use the provider's own hostname/IP properties |
| Infrastructure assigns static IPs per instance | Override IP/hostname via deployment configuration |
| Use stable DNS instead of changing IPs | Advertise a hostname resolvable by consumers |

Do not assume every provider obtains its host from `InetUtils` via the same path. Check the starter/provider documentation and verify the actual registration.

## 10. Docker and containers

Containers typically have their own network namespace. The JVM sees the interfaces of that namespace, not necessarily all interfaces on the host.

Example:

```text
Host:
  eth0       10.20.5.18
  docker0    172.17.0.1

Container:
  lo         127.0.0.1
  eth0       172.18.0.4
```

On a bridge network, `172.18.0.4` may be reachable from another container on the same network, yet unreachable from services outside the host.

### 10.1. Common options

- **Containers on the same Docker network:** advertise the IP or DNS service name reachable within that network.
- **Consumers outside the Docker network:** publish ports and advertise a host address/DNS reachable by consumers.
- **Host network mode:** the container shares the host's network namespace; pick the right host interface and check for port conflicts.
- **Multiple Docker networks:** a container can have multiple interfaces; use preferred networks or provider-specific configuration.

### 10.2. Do not advertise the host's bridge address to external consumers

If the registry returns `172.17.0.1:8080` while the consumer sits on a network with no route to the host's Docker bridge, connections will fail. An address that looks valid on the server side does not mean it is valid from the consumer's perspective.

Inspect addresses from the client's actual network namespace, not only from the host running the application.

## 11. Kubernetes and service DNS

In Kubernetes, each Pod has its own network namespace and Pod IP. However, clients should normally call services via Kubernetes Service DNS rather than storing a fixed Pod IP in application config.

Example:

```text
inventory.default.svc.cluster.local
```

Some principles:

- Pod IPs can change when a Pod is recreated.
- Service DNS is more stable and points to eligible endpoints via Service/EndpointSlice.
- `InetUtils` sees interfaces inside the Pod network namespace, not every NIC on the node.
- `server.address=0.0.0.0` can be used so the server listens on interfaces inside the Pod; the advertised address remains the Pod IP or DNS matching the discovery mechanism.
- When using Kubernetes-native discovery, there is no need to register Pod IPs via Eureka/Consul for the exact same purpose.

If a Spring Cloud discovery provider is still used inside Kubernetes, determine whether consumers are inside the same cluster or external, then select Pod IP, node/LoadBalancer address, or DNS matching the actual topology.

## 12. Hostname or IP address?

Advertising a hostname instead of an IP can work well when DNS is reliably managed:

```yaml
eureka:
  instance:
    hostname: checkout-01.internal
    prefer-ip-address: false
```

Advantages of hostnames:

- No need to update registrations merely because an IP changes if DNS is updated properly.
- Can support multiple addresses or failover at the DNS layer.
- Can provide a more observable identifier name.

However, hostnames also carry prerequisites:

- Consumers must be able to resolve the hostname.
- DNS records must point to addresses with valid routes from consumers.
- DNS caches and TTLs can slow down propagation of changes.
- TLS certificates must match the hostname if HTTPS is used.
- Split-horizon DNS may return different addresses depending on the client's network.

Explicit IPs suit stable addresses and simple topologies. Hostnames suit well-operated DNS setups where identity should be decoupled from physical IPs.

## 13. IPv4, IPv6, and multiple addresses on the same interface

A single interface can hold multiple addresses, such as private IPv4, global IPv6, and link-local IPv6. Not every address is suitable for service registration.

| Address type | Example | Notes |
| --- | --- | --- |
| IPv4 loopback | `127.0.0.1` | Only usable within the same network namespace |
| IPv4 private | `10.20.5.18` | Usable in internal networks if routable |
| IPv4 public | `203.0.113.18` | Requires firewall/NAT and publishing policy checks |
| IPv6 loopback | `::1` | Local only |
| IPv6 link-local | `fe80::1234` | Meaningful only on-link; typically needs zone/interface scope |
| IPv6 global | `2001:db8::18` | Routable if network supports it |
| IPv6 unique-local | `fd20:5::18` | Used within private networks per IPv6 design |

### 13.1. IPv6 link-local is not a general advertised address

An `fe80::/10` address is only meaningful on a single link. A client on another link cannot use it as a global service address. If IPv6 is required, choose a global or unique-local address matching the topology and ensure all consumers have routes.

### 13.2. URIs with IPv6 require square brackets

When embedding an IPv6 literal in a URL, syntax normally requires square brackets:

```text
http://[2001:db8::18]:8080
```

Never naively concatenate `host + ":" + port` if the host could be IPv6. Use `URI`, `InetAddress`, and standard APIs to handle addresses.

## 14. Practical address selection workflow

Before configuring, answer the following questions:

1. Where are the consumers located: same host, same Docker network, same Kubernetes cluster, same VPC, or external networks?
2. Which addresses are routable from consumers to the server?
3. Are any interfaces dedicated strictly to management, backup, or VPN?
4. Does the application need to advertise an IP or a hostname?
5. Does the provider rely on `InetUtils` or have its own override properties?
6. Is a single address required or are multiple addresses valid?
7. Can the address change after the process starts?
8. Do the registry/consumers support the IPv6 and DNS policies in use?

Then:

- List interfaces and addresses on the host/container.
- Identify the application subnet.
- Use `ignored-interfaces` to exclude unsuitable NICs if names are stable.
- Use `preferred-networks` to prioritize a specific subnet.
- If infrastructure supplies static addresses or stable DNS, consider provider-level overrides.
- Verify the actual registered address.
- Test connecting from at least one representative consumer.

## 15. Complete configuration example

Suppose the host running `checkout-service` has:

```text
ens160     10.20.5.18       service network
ens192     192.168.50.12   backup network
docker0    172.17.0.1      Docker bridge
tun0       100.80.10.4     VPN
```

Consumers in the system only access subnet `10.20.5.0/24`. Spring Cloud configuration:

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^tun[0-9]+$'
      preferred-networks:
        - '^10[.]20[.]5[.].*'

server:
  address: 0.0.0.0
  port: 8080
```

If using Eureka and wanting to advertise the IP:

```yaml
eureka:
  instance:
    prefer-ip-address: true
```

In this case:

- Server binds to all suitable local IPv4 addresses.
- `InetUtils` prioritizes subnet `10.20.5.*` and ignores Docker bridge/VPN.
- The discovery provider uses host information per its integration mechanism.
- Consumers see the service address belonging to the service network.

If you must strictly guarantee IP `10.20.5.18`, you can set `eureka.instance.ip-address` explicitly, though it must be updated when the IP changes. Do not combine a fixed override while assuming `preferred-networks` will replace that override.

## 16. Diagnosing wrong addresses published by the registry

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Registry displays `127.0.0.1` | No non-loopback address found or provider overridden | Check interfaces, fallbacks, and provider config |
| Registry displays Docker bridge IP | `InetUtils` selected the bridge interface | Check `ignored-interfaces` and `preferred-networks` |
| Registry displays VPN IP | VPN interface was treated as a valid candidate | Exclude interface or prioritize service subnet |
| Registered IP is right but consumers cannot call it | Mismatched route/firewall/NAT | Test connecting from consumer's exact network namespace |
| Registered hostname is right but fails to resolve | Wrong DNS record or split-horizon DNS | Check resolution from consumer host |
| Only some consumers can connect | Clients reside in different network segments | Check routes, ACLs, and DNS per segment |
| After changing NIC, registry retains old IP | Host info/registration does not auto-update on NIC changes | Verify re-registration lifecycle or restart |
| IPv6 registered but clients cannot call it | Client/provider lacks support or address is link-local | Check IPv6 type, URI, and network policies |
| Updated preferred-networks yet IP unchanged | Provider has explicit IP/hostname override or config not loaded | Inspect Environment and final registration object |

### 16.1. OS tools

On Linux:

```bash
ip addr
ip route
ip route get 10.20.5.25
```

On Windows:

```powershell
Get-NetIPConfiguration
Get-NetIPAddress
Get-NetRoute
```

On macOS:

```bash
ifconfig
netstat -rn
```

These commands help determine which addresses belong to which interfaces and the routes toward consumer networks. Having an IP present on a machine does not mean bidirectional routing is established.

### 16.2. Checking from the consumer side

Once the registry returns an address:

1. Extract the exact host and port received by the discovery client.
2. Test DNS resolution if host is a hostname.
3. Verify the route to that address.
4. Test TCP connectivity to the port.
5. Check TLS/SNI/certificate if HTTPS is used.
6. Call the health endpoint or a properly authenticated test API.

Do not declare success merely because `register()` returns without throwing an exception. Successful registration and actual reachability are two distinct outcomes.

## 17. Testing address selection

Tests should verify bound configuration and the final address published by the provider.

### 17.1. Testing property binding

With a Spring Boot test, verify the properties:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.]5[.].*'
      ignored-interfaces:
        - '^docker0$'
```

Check that the corresponding configuration bean contains the expected regex lists. This is a binding test, not a test of the OS IP-selection algorithm.

### 17.2. Testing InetUtils in a test environment

You can call `findFirstNonLoopbackHostInfo()` and verify the returned IP matches the preferred subnet. However, the test depends on real interfaces on the machine running the test; the same test may behave differently on a developer laptop, CI runner, and container.

For stable tests:

- Run inside a container/network namespace with controlled interfaces.
- Log the list of interfaces and addresses before evaluating results.
- Never hardcode a developer machine's IP.
- Separate regex configuration tests from OS-dependent integration tests.

### 17.3. Testing actual Registration

With a discovery provider:

1. Start the application context with the chosen network configuration.
2. Wait for auto-registration to complete.
3. Read `Registration` or query the registry.
4. Verify the advertised host/IP/port/metadata.
5. Use a test consumer to call the registered address.
6. Verify deregistration when the context closes if supported by the provider.

This is the most important test because it verifies the end result after `InetUtils`, provider configuration, and registration lifecycle work together.

## 18. Security and operations

Selecting the wrong interface not only causes connectivity failures but can also expose a service on an unintended network.

- Never advertise a management or backup interface if consumers are not permitted to access it.
- Never bind `0.0.0.0` if the application should only listen on one specific NIC.
- Use firewalls and network policies to restrict traffic; `ignored-interfaces` is not a security mechanism.
- Verify registered addresses do not leak internal topology beyond what is necessary.
- For HTTPS, ensure certificate SANs match the hostname/IP clients use.
- When changing NICs or subnets, plan registration updates and verify all consumers.
- Never use arbitrary fallback IPs to mask interface-detection failures.
- Monitor registrations that contain invalid or unreachable addresses.

## 19. Design principles

- Identify consumer networks before choosing an advertised address.
- Clearly distinguish bind address from advertised address.
- Use `preferred-networks` when a clear application subnet exists.
- Use `ignored-interfaces` when unsuitable interfaces have stable names.
- Never rely on interface order returned by the OS.
- Enable `use-only-site-local-interfaces` only when site-local semantics match the topology.
- Treat `default-ip-address` and `default-hostname` as fallbacks, not NIC configuration.
- Check whether the provider uses `InetUtils` or has its own override properties.
- In Kubernetes, prefer Service DNS when appropriate rather than pinning Pod IPs.
- Test from the consumer's network namespace, not only from the server host.
- Ensure TLS, firewalls, routing, and service registration all use consistent identity.

## 20. Summary

When a machine has multiple network interfaces, picking the first IP does not always yield the right result. Spring Cloud Commons provides `InetUtils` and `spring.cloud.inetutils` properties to prioritize subnets, exclude interfaces, and define fallbacks. `preferred-networks` helps select an address in the application network; `ignored-interfaces` excludes unsuitable NICs like bridges or VPNs; `use-only-site-local-interfaces` restricts selection according to Java's address classification.

Crucially, distinguish the server's bind address from the address advertised to the registry. `server.address=0.0.0.0` lets the server listen on multiple interfaces, yet is not an address for consumers to connect to. Providers such as Eureka may have their own hostname/IP overrides; Kubernetes may be better served by Service DNS instead of advertising a single interface IP.

An address is only valid when actual consumers can resolve and route to it. Therefore, after configuring `InetUtils`, verify the final registration, routes, firewalls, DNS, and connectivity from the consumer side. This ensures discovery returns a usable endpoint in a distributed system.

## 21. References

- [Spring Cloud Commons — Ignore Network Interfaces](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/host-info.html)
- [Spring Cloud Commons — InetUtils API](https://docs.spring.io/spring-cloud-commons/docs/current/javadoc-api/org/springframework/cloud/commons/util/InetUtils.html)
- [Spring Cloud Commons — InetUtilsProperties API](https://docs.spring.io/spring-cloud-commons/docs/current/javadoc-api/org/springframework/cloud/commons/util/InetUtilsProperties.html)
- [Spring Cloud Netflix — Eureka Instance Configuration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot Reference — Embedded Web Server Configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Java API — NetworkInterface](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/NetworkInterface.html)
- [Java API — InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
