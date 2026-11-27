# Ignoring interfaces with ignoredInterfaces

A host running a Spring Cloud application may have many network interfaces: LAN cards, Wi-Fi, loopback, VPNs, Docker bridges, Hyper-V virtual adapters, or interfaces created by a container platform. When the application auto-determines its hostname and IP to register with a service registry, the selected interface might not be one reachable by other services.

Spring Cloud Commons provides `spring.cloud.inetutils.ignored-interfaces` to skip interfaces whose names match a list of Java regular expressions. For example, you can ignore `docker0` and interfaces starting with `veth`. This property helps `InetUtils` select a more appropriate address when building host info for the application.

This lesson belongs to the **Identity and Networking** chapter of the **SPRING_CLOUD_CORE** module. We will examine how `ignoredInterfaces` works in `InetUtils`, how to write accurate regexes, how to distinguish it from `preferredNetworks`, how to inspect real interfaces on a machine, and how to verify the IP the application advertises.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain why a multi-interface machine can cause an application to register the wrong IP.
- Identify the roles of `InetUtils` and `InetUtilsProperties` in Spring Cloud Commons.
- Configure the `spring.cloud.inetutils.ignored-interfaces` list in YAML or properties.
- Write Java regular expressions to match interface names exactly or by prefix.
- Distinguish interface names from IP addresses and hostnames.
- Distinguish `ignored-interfaces` from `preferred-networks` and `use-only-site-local-interfaces`.
- Inspect interfaces, display names, UP state, and the addresses seen by the JVM.
- Understand the impact of network namespaces in Docker/Kubernetes and VPN/virtual adapters.
- Recognize scenarios where fallbacks may still return an unwanted address.
- Verify `spring.cloud.client.hostname` and `spring.cloud.client.ip-address` before registering a service.

## 2. The problem when a machine has multiple network interfaces

A server can have several active adapters simultaneously. Examples:

| Interface | Common purpose | Example address |
| --- | --- | --- |
| `lo` | Internal loopback | `127.0.0.1` |
| `eth0` or `ens192` | Primary host network | `10.20.1.15` |
| `docker0` | Docker bridge on the host | `172.17.0.1` |
| `veth8a1b2c` | Virtual Ethernet pair for a container | `172.18.0.1` |
| `tun0` | VPN tunnel | `10.8.0.12` |
| `tailscale0` | Overlay network | `100.64.0.8` |
| `vEthernet (Default Switch)` | Virtual adapter on Windows/Hyper-V | Depends on configuration |

If the application selects the IP of an interface used only for a local bridge, the service registry may store an address unreachable by services on other networks. Clients looking up the service receive the wrong endpoint and connections fail.

For instance, an application runs on a host with:

- `eth0` with IP `10.20.1.15`, reachable by services in the VPC.
- `docker0` with IP `172.17.0.1`, serving only the local Docker bridge.
- `tun0` with IP `10.8.0.12`, dedicated to an admin VPN.

If `InetUtils` picks `172.17.0.1`, Eureka/Consul or another registration component may advertise the wrong address to service consumers.

### 2.1. Why can't we just use the machine's hostname by default?

A hostname can resolve to different addresses depending on DNS, hosts files, network namespaces, or multi-NIC configurations. A machine can also have multiple IPv4 and IPv6 addresses.

Spring Cloud Commons provides the `InetUtils` abstraction to find suitable host information. Integrations that rely on `InetUtils` or host properties published by Spring Cloud can use this result when registering the service.

## 3. What is ignoredInterfaces?

`ignoredInterfaces` is a list of Java regular expressions used to skip network interfaces with matching names. The full property is:

~~~text
spring.cloud.inetutils.ignored-interfaces
~~~

Spring Cloud Commons binds this property to `InetUtilsProperties.ignoredInterfaces`. By default the list is empty, meaning no interface is excluded by this filter.

Official example:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
~~~

In the example:

- `docker0` matches an interface whose display name is exactly `docker0`.
- `veth.*` matches names starting with `veth` optionally followed by more characters, such as `veth0` or `veth8a1b2c`.

The list has OR semantics: if an interface matches any pattern, `InetUtils` skips that interface.

### 3.1. What value is the regex matched against?

In the current implementation, `InetUtils` calls `NetworkInterface.getDisplayName()` and then matches that display name against each pattern using `String.matches(regex)`.

This has three consequences:

1. The input is the **interface's display name**, not an IP address.
2. `String.matches` requires the entire string to match the regex; patterns are not automatically treated as substring searches.
3. Name and display name may differ depending on the OS or driver. Inspect the exact value the JVM sees before writing patterns.

Examples:

| Display name | Pattern | Result |
| --- | --- | --- |
| `docker0` | `docker0` | Match |
| `veth1234` | `veth.*` | Match |
| `veth1234` | `veth` | No match |
| `my-docker0` | `docker0` | No match |
| `my-docker0` | `.*docker.*` | Match |
| `eth0` | `veth.*` | No match |

If you want an exact match, you can write `^docker0$`. With `String.matches`, both ends of the string must already match in full, yet anchors make the intent easier to read.

### 3.2. Commonly used pattern examples

| Goal | Pattern | Explanation |
| --- | --- | --- |
| Ignore only `docker0` | `^docker0$` | Exact name |
| Ignore all `veth` interfaces | `^veth.*$` | `veth` prefix |
| Ignore bridges named `br-...` | `^br-[0-9a-f]+$` | Hex string after `br-` |
| Ignore numbered `virbr` adapters | `^virbr\\d+$` | One or more digits |
| Ignore names containing `docker` | `.*docker.*` | Substring match |

Include only interfaces that truly should not be used. Accidentally ignoring the primary network interface can prevent the application from finding the desired IP.

## 4. How InetUtils selects an address

`ignoredInterfaces` is one step in the address-selection process. It does not by itself determine the entire final address.

General flow in `InetUtils.findFirstNonLoopbackAddress()`:

1. The JVM enumerates the `NetworkInterface` entries on the machine.
2. `InetUtils` evaluates interfaces that are UP.
3. Before iterating an interface's addresses, `InetUtils` checks the display name against the ignored pattern list.
4. If the name matches, the interface is skipped; none of its addresses are evaluated as candidates.
5. For non-ignored interfaces, `InetUtils` iterates addresses and checks IPv4, non-loopback, and network filter conditions.
6. If a suitable address is found, `InetUtils` converts it into a `HostInfo` containing hostname and IP.
7. If no candidate is found, the current implementation tries `InetAddress.getLocalHost()` as a fallback.

~~~mermaid
flowchart TD
    A[Enumerate network interfaces] --> B{Interface is UP?}
    B -->|No| A
    B -->|Yes| C[Read display name]
    C --> D{Matches ignoredInterfaces?}
    D -->|Yes| A
    D -->|No| E[Enumerate interface addresses]
    E --> F{IPv4 and non-loopback?}
    F -->|No| E
    F -->|Yes| G{Pass preferredNetworks or site-local filter?}
    G -->|No| E
    G -->|Yes| H[Candidate host address]
    H --> I[Build HostInfo]
    E --> J{More addresses?}
    J -->|Yes| E
    J -->|No| A
    A --> K{Any candidate found?}
    K -->|Yes| I
    K -->|No| L[Fallback InetAddress.getLocalHost()]
~~~

The diagram shows that the ignored filter runs on the interface before its addresses are evaluated. If an interface is ignored, none of the addresses bound to it participate in candidate selection.

### 4.1. ignoredInterfaces is not an IP address filter

Patterns like `^10\\.20\\..*` should not be placed in `ignored-interfaces` if the goal is IP filtering. That pattern is checked against the interface name, such as `eth0`, not against an address like `10.20.1.15`.

To prioritize or restrict IP ranges, use `preferred-networks` or `use-only-site-local-interfaces`.

### 4.2. Understanding the fallback properly

If all interfaces are ignored or no address satisfies the criteria, the current `InetUtils` tries `InetAddress.getLocalHost()`. The returned fallback address has not necessarily passed through the same ignored/preferred filters as regular candidates.

Therefore, `ignored-interfaces` is a filter during address selection, **not an absolute guarantee that the returned address can never belong to an ignored interface**. After changing configuration, always inspect the actual `HostInfo`.

## 5. Configuration in application.yml

### 5.1. Ignoring Docker bridges and veth on the host

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
~~~

This configuration is suitable when the JVM runs on a Docker host and bridge/veth interfaces appear in the host namespace. Actual interface names may vary, so verify using OS tools and the JVM.

### 5.2. Ignoring a specific group of virtual adapters

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
        - '^virbr[0-9]+$'
        - '^br-[0-9a-f]+$'
      preferred-networks:
        - '10.20.'
        - '192.168.50.'
~~~

In the example, the ignored list skips interfaces whose names match the patterns. `preferred-networks` further filters by IP address so only addresses belonging to the two desired prefixes are accepted.

In the current implementation, `preferredNetworks` checks addresses using `address.matches(regex)` or `address.startsWith(regex)`. Thus values like `10.20.` used as a string prefix can also work. This behavior differs from `ignoredInterfaces`, which uses `interfaceName.matches(regex)`.

### 5.3. Ignoring loopback by name

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^lo$'
~~~

Loopback addresses are already excluded by the `isLoopbackAddress()` check when picking IPv4 candidates. Adding `lo` to the ignored list can make the policy explicit or skip the entire loopback interface before iterating addresses. Usually this setting is unnecessary if your only goal is to exclude loopback addresses.

### 5.4. Using application.properties

Lists can be declared with indexed properties:

~~~properties
spring.cloud.inetutils.ignored-interfaces[0]=^docker0$
spring.cloud.inetutils.ignored-interfaces[1]=^veth.*$
spring.cloud.inetutils.ignored-interfaces[2]=^virbr[0-9]+$
~~~

Spring Boot relaxed binding supports kebab-case in both properties and YAML. Use one consistent format across the project to keep configuration easy to follow.

## 6. Distinguishing the three interface and address selection properties

The three properties are often used together but solve different problems:

| Property | Input evaluated | Effect |
| --- | --- | --- |
| `spring.cloud.inetutils.ignored-interfaces` | Display name of the network interface | Skips the entire interface if its name matches a regex |
| `spring.cloud.inetutils.preferred-networks` | IP address of the interface | Accepts only addresses matching a configured regex or prefix |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | IP address | Accepts only addresses for which `InetAddress.isSiteLocalAddress()` returns true |

Combined example:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
      preferred-networks:
        - '10.20.'
        - '192.168.50.'
      use-only-site-local-interfaces: false
~~~

Do not enable `use-only-site-local-interfaces` expecting every private address to be selected under the same concept as CIDR. This property uses the JDK's `InetAddress.isSiteLocalAddress()` rule; it is not a CIDR parser and is not equivalent to a cloud provider's network policy.

### 6.1. Default hostname and IP when no host is found

`InetUtilsProperties` also provides:

~~~yaml
spring:
  cloud:
    inetutils:
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

These two values are used when `InetUtils.findFirstNonLoopbackHostInfo()` fails to obtain a host address. They are not a substitute for proper interface configuration. If the service registry publishes `127.0.0.1` to services on other hosts, clients will connect to their own loopback and fail to reach the registered service.

## 7. Inspecting interfaces actually seen by the JVM

Before writing regexes, list the interfaces on the exact machine/container running the application. Commands like `ip addr` or `ip link` are helpful on Linux, yet output from the JVM itself is the ground truth for matching `NetworkInterface.getDisplayName()`.

### 7.1. Java diagnostic

Create a small program:

~~~java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Enumeration;

public class NetworkInterfaceReport {

    public static void main(String[] args) throws SocketException {
        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();

        while (interfaces.hasMoreElements()) {
            NetworkInterface networkInterface = interfaces.nextElement();

            System.out.printf(
                    "name=%s, displayName=%s, up=%s, index=%d%n",
                    networkInterface.getName(),
                    networkInterface.getDisplayName(),
                    networkInterface.isUp(),
                    networkInterface.getIndex());

            Enumeration<InetAddress> addresses =
                    networkInterface.getInetAddresses();

            while (addresses.hasMoreElements()) {
                InetAddress address = addresses.nextElement();
                System.out.printf(
                        "  address=%s, type=%s, loopback=%s, siteLocal=%s%n",
                        address.getHostAddress(),
                        address.getClass().getSimpleName(),
                        address.isLoopbackAddress(),
                        address.isSiteLocalAddress());
            }
        }
    }
}
~~~

Pay attention to both `name` and `displayName` columns. The current `InetUtils` implementation matches patterns against `displayName`. If you only read names from `ip link` and configure based on those, verify that the JVM's display name holds the same value.

### 7.2. Observing Spring Cloud's HostInfo

Inside a Spring application, you can inject `InetUtils` to inspect the result Spring Cloud computes:

~~~java
package com.example.networking;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.commons.util.InetUtils;
import org.springframework.stereotype.Component;

@Component
public class HostInfoReporter implements ApplicationRunner {

    private final InetUtils inetUtils;

    public HostInfoReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    @Override
    public void run(ApplicationArguments args) {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        System.out.println("hostname=" + hostInfo.getHostname());
        System.out.println("ipAddress=" + hostInfo.getIpAddress());
    }
}
~~~

This snippet illustrates checking the result in an application with Spring Cloud Commons auto-configuration. Do not log internal network details into public logs if that constitutes sensitive infrastructure data.

### 7.3. Enabling TRACE logging

To see which interfaces are tried, which are skipped, and which address is chosen, enable logging in a local environment:

~~~yaml
logging:
  level:
    org.springframework.cloud.commons.util.InetUtils: TRACE
~~~

The current implementation emits trace logs when inspecting interfaces, ignoring an interface, and finding a non-loopback interface. Turn off TRACE after diagnosing because the logs can reveal network structure and generate high startup log volume.

## 8. HostInfoEnvironmentPostProcessor and service registration

Spring Cloud Commons includes `HostInfoEnvironmentPostProcessor`. In the current implementation, this processor:

1. Creates `InetUtilsProperties`.
2. Attaches configuration property sources to the Environment.
3. Uses Spring Boot's `Binder` to bind the `spring.cloud.inetutils` prefix.
4. Instantiates `InetUtils` with the newly bound properties.
5. Calls `findFirstNonLoopbackHostInfo()`.
6. Adds `spring.cloud.client.hostname` and `spring.cloud.client.ip-address` to the Environment.

The processor is ordered after `ConfigDataEnvironmentPostProcessor` in the current codebase. That allows Config Data settings, such as `application.yml`, to be bound before host info is computed.

Discovery clients or auto-registration integrations can consume this host info when constructing registration details. However, each registry may have its own override properties such as hostname, IP, prefer IP, or metadata. If you have configured provider-level overrides, verify the precedence between provider configuration and Spring Cloud defaults.

### 8.1. When is host info computed?

`HostInfoEnvironmentPostProcessor` runs during application startup to populate hostname and IP into the Environment. It does not continuously re-scan interfaces when a VPN toggles or an adapter changes state after the application is already running.

If network topology changes after startup:

- Verify whether the registry supports updating registration host/metadata at runtime.
- If no safe runtime update mechanism exists, restart/rollout the instance to recompute host info.
- Do not assume editing `application.yml` or refreshing a bean alone will automatically recompute `spring.cloud.client.ip-address`.

## 9. Docker and Kubernetes: network namespaces matter greatly

Interface names visible on the host can differ from interface names inside a container.

Example on a Docker host:

~~~text
Host network namespace:
  eth0
  docker0
  vethA1B2
  vethC3D4

Container network namespace:
  lo
  eth0
~~~

An application running inside a container normally sees only the interfaces belonging to the container's network namespace. It may not see `docker0` or the `veth` ends located in the host namespace. Therefore, configuring:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
~~~

takes effect when those names actually appear inside the JVM's namespace. If the container only sees `eth0` and `lo`, the patterns `docker0` and `veth.*` match no interfaces.

### 9.1. Do not ignore eth0 mechanically

In many containers, `eth0` is the primary interface reachable by other services across an overlay or bridge network. If you add:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^eth0$'
~~~

the application may skip the exact network interface it needs to use. Only do this once you have confirmed another suitable interface exists and the registry/consumers can genuinely route to that address.

### 9.2. Kubernetes CNI

Interface names inside a Pod depend on the CNI, runtime, and node configuration. A Pod usually has a default interface like `eth0`, while secondary interfaces may be created by Multus or other plugins. Do not guess interface names from the CNI name; run diagnostics inside the Pod or print the list from the application's JVM.

If the service registry needs the Pod address, verify the chosen address belongs to a network routable by consumers. In Kubernetes, Service/Endpoints and internal DNS are usually better abstractions for service-to-service communication; Pod IPs should not replace Services unless the application intentionally registers Pods directly.

## 10. Testing regexes independently

Because the implementation uses `String.matches`, you can test patterns before deploying:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class IgnoredInterfacePatternTest {

    @Test
    void matchesExactDockerBridgeAndVethPrefix() {
        assertThat("docker0".matches("^docker0$")).isTrue();
        assertThat("veth8a1b2c".matches("^veth.*$")).isTrue();
        assertThat("eth0".matches("^veth.*$")).isFalse();
        assertThat("my-docker0".matches("^docker0$")).isFalse();
        assertThat("my-docker0".matches(".*docker.*")).isTrue();
    }
}
~~~

This test verifies Java regex semantics. It does not prove that the production machine actually has the display names tested. For complete verification, run diagnostics in the exact OS/container and inspect `InetUtils` logs.

### 10.1. Configuration binding test

When writing an integration test for the application, verify the list binds into `InetUtilsProperties`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.commons.util.InetUtilsProperties;

@SpringBootTest(properties = {
    "spring.cloud.inetutils.ignored-interfaces[0]=^docker0$",
    "spring.cloud.inetutils.ignored-interfaces[1]=^veth.*$"
})
class InetUtilsPropertiesBindingTest {

    @Autowired
    InetUtilsProperties properties;

    @Test
    void bindsIgnoredInterfacePatterns() {
        assertThat(properties.getIgnoredInterfaces())
                .containsExactly("^docker0$", "^veth.*$");
    }
}
~~~

This test assumes the test source set includes AssertJ, JUnit Jupiter, and Spring Cloud Commons auto-configuration. If the application manually constructs `InetUtilsProperties` or disables auto-configuration, verify bean registration against the actual setup.

## 11. What ignoredInterfaces does NOT do

`ignored-interfaces` only controls `InetUtils`'s interface-selection step. It does not:

- Disable a network interface at the OS level.
- Remove interfaces from Docker, Kubernetes, Hyper-V, or a VPN.
- Modify routing tables, firewalls, NAT, or cloud network policies.
- Prevent the application from binding a socket to an address on an ignored interface.
- Block outbound connections from traversing that interface.
- Automatically configure the IP published by Eureka/Consul or another registry if the provider has its own overrides.
- Guarantee that a fallback host address cannot belong to an ignored interface.

If the goal is to secure the network or block traffic, use firewalls, network policies, security groups, or platform network configuration. Never treat `ignoredInterfaces` as a security control.

## 12. Troubleshooting

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Config includes `docker0` yet interface is still picked | JVM does not see exact display name `docker0` or regex fails full-string match | Print `getDisplayName()` and test the pattern with `String.matches()` |
| `veth` is not skipped | Pattern `veth` does not match names like `veth1234` | Use `^veth.*$` |
| Address is still the bridge IP after ignoring interface | No other candidate remains so fallback `InetAddress.getLocalHost()` returns it | Check logs and fallback; configure a suitable interface/host IP or use registry overrides |
| Container has no `docker0` | JVM runs inside its own network namespace | List interfaces inside the container; configure per actual interfaces |
| Application registers a VPN IP | VPN interface is not ignored or preferred networks permits the VPN IP | Ignore the VPN display name or adjust `preferred-networks` |
| Ignoring `eth0` leaves no valid IP | `eth0` is the container's primary interface | Remove the pattern and inspect the network namespace |
| Updated config yet `spring.cloud.client.ip-address` unchanged | Host info was computed during startup | Restart/rollout or use the registry's dedicated registration update mechanism |
| Pattern with dots or brackets fails to match | Unescaped regex metacharacters | Escape special characters or test with `String.matches()` |
| TRACE logs do not show expected interface | Interface is DOWN or invisible to the JVM | Check interface state and namespace from inside the exact process/container |

### 12.1. Recommended diagnostic workflow

1. List interfaces in the exact runtime environment of the application.
2. Record both `getName()` and `getDisplayName()`.
3. Record UP/DOWN state and addresses attached to each interface.
4. Enable TRACE for `InetUtils`.
5. Test each pattern with Java `String.matches()`.
6. Verify the address returned by `InetUtils.findFirstNonLoopbackHostInfo()`.
7. Inspect the actual address inside the service registry.
8. If they do not match, check provider-specific overrides and fallback behavior.

## 13. Practice exercises

### Exercise 1 — Identify interfaces

Run the `NetworkInterfaceReport` program on your development machine and record:

- Interface name.
- Display name.
- UP/DOWN state.
- List of IPv4/IPv6 addresses.
- Loopback and site-local addresses.

Identify which interface belongs to the application network and which belong to VPN/bridge/virtual adapters.

### Exercise 2 — Write ignoredInterfaces

Create a configuration that ignores:

- The Docker bridge interface with display name `docker0`.
- Every interface whose display name starts with `veth`.
- One other virtual interface identified from your diagnostic output.

Explain each regex and verify with `String.matches()`.

### Exercise 3 — Compare with preferredNetworks

Keep the ignored list and add `preferred-networks` accepting only the application network's IP prefix. Observe the differences between:

- Ignoring interfaces by display name.
- Filtering addresses by IP.
- Selecting only site-local addresses.

### Exercise 4 — Verify inside a container

Run the same application on the host and inside a container. Compare the list of interfaces seen by the JVM. Identify why a pattern may match on the host yet match nothing inside the container.

### Exercise 5 — Verify service registration

Start the application with the new configuration, read `spring.cloud.client.ip-address`, and cross-check the address registered in the registry. Try changing one pattern and restarting to confirm the result.

**Completion criteria:** you can write regexes that accurately match display names, explain why an interface is skipped, distinguish interface filtering from IP address filtering, and verify the host info used by service discovery.

## 14. Summary

`spring.cloud.inetutils.ignored-interfaces` is a list of Java regexes used to skip network interfaces while `InetUtils` searches for a host address. The current implementation matches regexes against `NetworkInterface.getDisplayName()` via `String.matches`, so patterns must match the full display name. The list uses OR semantics: matching a single pattern skips the interface.

To choose the right IP, inspect interfaces inside the JVM's network namespace, combine the ignored list with `preferred-networks` or `use-only-site-local-interfaces` as needed, and verify `HostInfo` alongside the advertised host value. `ignoredInterfaces` does not disable adapters or alter routing; if no candidates remain, the fallback may return an unexpected address. Because host info is normally computed at startup, subsequent network or configuration changes require an appropriate registration update or restart workflow.

## References

- [Spring Cloud Commons — Common Abstractions, Ignore Network Interfaces](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): examples of `docker0`, `veth.*`, `preferredNetworks`, and site-local interfaces.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): properties `spring.cloud.inetutils.ignored-interfaces`, `preferred-networks`, `default-hostname`, `default-ip-address`, and timeout.
- [InetUtils.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/commons/util/InetUtils.java): display name matching, address filtering, fallback, and HostInfo creation.
- [InetUtilsProperties.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/commons/util/InetUtilsProperties.java): `spring.cloud.inetutils` prefix and configuration properties.
- [HostInfoEnvironmentPostProcessor.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/HostInfoEnvironmentPostProcessor.java): binding configuration and publishing `spring.cloud.client.hostname` along with `spring.cloud.client.ip-address`.
- [Java NetworkInterface API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/NetworkInterface.html): name, display name, state, and addresses of a network interface.

Cross-check implementation details against the deployed Spring Cloud release train. Address selection details and configuration loading timing may vary by version, OS, and network namespace.
