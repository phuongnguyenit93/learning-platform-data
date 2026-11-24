# Distinguishing localhost, Specific Addresses, and All Network Interfaces When Configuring Spring Boot

## Lesson Objectives

After this lesson, you will be able to:

1. Explain the meaning of **localhost/loopback**, a **specific IP address**, and a **wildcard** address when an HTTP server opens a listening port.
2. Configure server.address and server.port in a Spring Boot 3.3.x application.
3. Predict which requests can reach the server from the same machine, another machine on the LAN, a container, or an external network.
4. Distinguish the address the server **binds** to from the hostname a client uses to **connect**, the public destination address, DNS, the HTTP Host header, and CORS.
5. Inspect listening sockets using curl, ss, netstat, or PowerShell; identify wrong IP bind errors, firewalls, NAT, and IPv4/IPv6 issues.
6. Apply sensible configurations for local machine development, backends running behind a reverse proxy, Docker, and Kubernetes.

The content focuses on the embedded HTTP server of **Spring Boot 3.3.x with Java 17+**. The TCP/IP principles apply more broadly to Tomcat, Jetty, Undertow, and Reactor Netty. Examples use port 8080; the addresses 192.168.1.50 and 192.168.1.100 are only illustrative private-network addresses and must be replaced with real IPs belonging to your environment.

## 1. What Does It Actually Mean for a Server to "Listen on an Address"?

An HTTP server using TCP typically asks the operating system to create a listening socket bound to a **local IP address and port**, for example:

~~~text
127.0.0.1:8080
192.168.1.50:8080
0.0.0.0:8080
[::1]:8080
[::]:8080
~~~

When a client wants to connect, it sends packets to a **destination IP and destination port**. The operating system receives packets on the appropriate network interface, checks whether a matching listening socket exists, and hands the accepted connection to the server.

Two concepts to separate:

- **Bind address:** the local address that the server registers to accept connections, determined by the server and the operating system.
- **Destination address:** the IP address that the client actually sends the request to after resolving the hostname and selecting a route.

For example, the machine running Spring Boot has multiple interfaces:

~~~text
Machine A running Spring Boot
  |
  +-- lo       127.0.0.1       (loopback, calling itself)
  |
  +-- Wi-Fi    192.168.1.50    (LAN network)
  |
  +-- VPN      10.8.0.7        (VPN network)
~~~

Binding 127.0.0.1:8080 means accepting connections directed to loopback; binding 192.168.1.50:8080 means accepting connections directed to that LAN address; binding 0.0.0.0:8080 means accepting connections on the corresponding local IPv4 addresses, including loopback, Wi-Fi, and VPN, if there are no other network barriers.

**A successful bind does not guarantee remote reachability.** Clients still need a route to the IP, a port opened by firewalls/security groups, an appropriate NAT or proxy path, and the server actually running.

## 2. localhost and Loopback: Returning Only to the Calling Machine Itself

**localhost** is a special machine name resolved by the system to a loopback address, typically including:

- **127.0.0.1:** IPv4 loopback, an address in the 127.0.0.0/8 block.
- **::1:** IPv6 loopback.

Connection attempt flow:

~~~text
Browser on Machine A -> http://localhost:8080
      |
      v
localhost -> 127.0.0.1 or ::1 on MACHINE A
      |
      v
Server listening on loopback on Machine A
~~~

Another machine B accessing http://localhost:8080 will look for a server on **Machine B**, not Machine A.

This is critically important when working with:

- A real phone and a laptop: localhost on the phone is the phone.
- A Docker container: localhost inside a container is that container itself.
- A Kubernetes Pod: localhost is the loopback belonging to the Pod's network namespace.
- A virtual machine: localhost inside a VM is the VM.
- A reverse proxy on a different host: localhost from the proxy points back to the proxy's host.

### Explicit IPv4 Loopback Configuration

In src/main/resources/application.yml:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Or application.properties:

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

When the application binds successfully, requests from the **same machine/network namespace** to http://127.0.0.1:8080 can reach the server. Clients on another machine cannot reach Machine A's loopback by typing localhost on Machine B.

Advantage: restricts the network acceptance scope at the operating system level, suitable for local exercises or applications accessed only by a reverse proxy on the same host.

Limitation: loopback does not replace authentication, authorization, or data security. Other processes on the **same host/network namespace** can still connect if there are no additional barriers.

### Why Shouldn't You Rely Ambiguously on the Name localhost?

When setting:

~~~yaml
server:
  address: localhost
~~~

Spring Boot converts this address into an InetAddress, and the result depends on name resolution, IPv4/IPv6, and the environment. If localhost resolves preferring ::1 while the client tries to access 127.0.0.1, you may observe different connection behavior for the same word localhost.

For predictable hands-on testing, use **127.0.0.1** for pure IPv4 tests or **::1** for pure IPv6 tests. You can also test explicitly with curl --ipv4 or curl --ipv6.

## 3. Specific IP Address: Binding to an Existing Local IP

Machine A has LAN address 192.168.1.50. Configuration:

~~~yaml
server:
  address: 192.168.1.50
  port: 8080
~~~

Meaning: the socket accepts connections targeting **192.168.1.50:8080**, and does not automatically accept connections targeting 127.0.0.1:8080 or another IP on the machine.

~~~text
Machine A has IP 192.168.1.50, server binds 192.168.1.50:8080

From Machine A -> http://192.168.1.50:8080    Can reach
From Machine A -> http://127.0.0.1:8080       Does not reach this listener
From Machine B -> http://192.168.1.50:8080    Can reach, if route/firewall allow
From Machine B -> http://localhost:8080       Points to Machine B, not A
~~~

**Prerequisite:** the bound IP must be a valid address existing on the corresponding host or network namespace. If you mistakenly set 192.168.1.50 when the host only has 192.168.1.51, the server may fail to start and report an error equivalent to "Cannot assign requested address" or "BindException".

When to use a specific address:

- A server has multiple network interfaces and you only want to listen on one interface.
- The application only accepts connections over an internal NIC, separated from a public NIC.
- The device has a stable IP that rarely changes.

Points to consider: Wi-Fi/VPN IPs can change when switching networks, when DHCP renews leases, when an interface goes down, or when moving machines. Hardcoding a LAN address is often inflexible in Docker, Kubernetes, and cloud deployments with dynamic IPs. If the server runs in a container, the **container's local IP** differs from the host's IP; you cannot assume the host's LAN IP exists inside the container.

## 4. All Network Interfaces: 0.0.0.0 and IPv6 Notation ::

For IPv4, **0.0.0.0 is the unspecified/wildcard bind address**. When a server listens on 0.0.0.0:8080, the operating system can accept connections sent to the **local IPv4 addresses** on that port.

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Example:

~~~text
Server listening on 0.0.0.0:8080
     |
     +-- 127.0.0.1:8080      (IPv4 loopback)
     +-- 192.168.1.50:8080   (IPv4 LAN)
     +-- 10.8.0.7:8080       (IPv4 VPN)
~~~

This does not mean the Internet can automatically connect to the server: routers, firewalls, cloud security groups, private/public addressing, inbound NAT, and reverse proxies still determine the path.

### Do Not Use 0.0.0.0 as a Destination URL for Users

0.0.0.0 has a special meaning **when binding**. When you want to send an HTTP request, use an actual destination address:

~~~text
On the same machine:    http://127.0.0.1:8080
From another LAN host:  http://192.168.1.50:8080
Via valid DNS:          https://api.example.com
~~~

Do not instruct users to access http://0.0.0.0:8080 as a general service address. Some tools may handle that URL in a special way, but it is not a meaningful, portable server address on a network.

### IPv6: :: Is Wildcard, ::1 Is Loopback

IPv6 notations equivalent in **role**:

| Purpose | IPv4 | IPv6 |
|---|---|---|
| Loopback only | 127.0.0.1 | ::1 |
| All addresses on the same address family stack | 0.0.0.0 | :: |
| Address of one specific interface | 192.168.1.50 | Example fd00::50 |

To bind to IPv6 loopback, try:

~~~yaml
server:
  address: "::1"
  port: 8080
~~~

To bind to the IPv6 wildcard:

~~~yaml
server:
  address: "::"
  port: 8080
~~~

Quoting IPv6 addresses in YAML improves readability and avoids syntax ambiguity. When a URL contains a literal IPv6 address, enclose the address part in square brackets:

~~~text
http://[::1]:8080
http://[fd00::50]:8080
~~~

**Do not deduce that binding :: definitely accepts IPv4 as well.** Dual-stack mode and IPv4-mapped IPv6 depend on the JVM, operating system, and socket/server configuration. For a system requiring both IPv4 and IPv6, inspect the listener and test requests on **both address families**. Similarly, 0.0.0.0 only describes the IPv4 wildcard; it does not guarantee IPv6 reachability.

## 5. Comparing the Three Common Choices

Suppose the host has loopback 127.0.0.1 and LAN 192.168.1.50, port 8080 is free, the firewall allows LAN, and the server binds successfully:

| server.address | Access from 127.0.0.1 same machine | Access from 192.168.1.50 same machine | Access over LAN from another machine |
|---|---|---|---|
| 127.0.0.1 | Yes | Not via that listener | No |
| 192.168.1.50 | Not via that listener | Yes | Possible, if firewall/route allow |
| 0.0.0.0 | Yes | Yes | Possible, if firewall/route allow |

This table applies to **IPv4 and a single listening server**. If the machine has another server on the port or a forwarding proxy, system-wide connection results may differ. Binding describes where a listener accepts connections, not absolute exclusivity over every transmission path to the application.

Practical selection rules:

- **Local machine development only:** 127.0.0.1 is usually the clearest network-restricting default.
- **Only via an internal NIC of a fixed host:** the specific address on that NIC.
- **Containers, Pods, or hosts needing traffic across multiple NICs:** 0.0.0.0 can make sense, but you must use firewalls, proxies, Services, or network policies to control access scope.
- **Services accessed only via a reverse proxy on the same host:** you can bind the backend to 127.0.0.1 so the proxy connects locally.
- **Reverse proxy on a different host/container:** the backend usually needs to bind to an address reachable on the network between the proxy and the app.

Each environment has a different network path; there is no single server.address value that is "safest and works everywhere".

## 6. Spring Boot Configuration: server.address Differs from server.port

In Spring Boot 3.3.x, the relevant properties are:

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

- **server.address** determines the address the server binds to (converted to a network address object).
- **server.port** determines the HTTP TCP port of the embedded server; the default is usually 8080 if unchanged.
- **server.port=0** requests the operating system to allocate an available dynamic port; it **does not mean** bind all interfaces.
- **server.address=0.0.0.0** means IPv4 wildcard; it **does not mean** port 0.
- When **server.address is not declared**, the embedded server usually listens on the network addresses allowed by the implementation and JVM configuration. Do not rely on vague defaults: inspect the real listener, especially in IPv4-only/IPv6-only environments.

Equivalent YAML:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

### Spring MVC and Spring WebFlux

server.address and server.port are Spring Boot-level properties. They apply to the corresponding embedded server in both types of applications:

~~~text
Spring MVC / Servlet:
  server.address -> Tomcat/Jetty/Undertow servlet factory -> TCP listener

Spring WebFlux / Reactive:
  server.address -> Reactor Netty (or another reactive server) -> TCP listener
~~~

Internal server creation differs, but the meaning of IP and port binding at the network layer is the same. Do not manually call factory.getWebServer() to change the address; configure via properties or an appropriate server customizer.

### Multiple Configuration Sources Can Override

Values from the command line, environment variables, profiles, application.yml, and other configuration sources follow a precedence order. For example, you can run:

~~~bash
./gradlew bootRun --args='--server.address=127.0.0.1 --server.port=8082'
~~~

This command assumes the project has the bootRun task configured. On Windows PowerShell you can use:

~~~powershell
.\gradlew.bat bootRun --args="--server.address=127.0.0.1 --server.port=8082"
~~~

When you see the server binding differently from application.yml, check active profiles and runtime arguments before concluding that Boot ignored the property. Environment variables typically use SERVER_ADDRESS and SERVER_PORT according to relaxed binding rules.

## 7. Bind Address, DNS, Host Header, CORS, and Reverse Proxy Are Different Layers

Suppose a client calls:

~~~text
https://api.example.com/products
~~~

A connection may flow as follows:

~~~text
Client
   |
   +-- DNS: api.example.com -> public address of proxy/load balancer
   |
   +-- TCP/TLS to public IP:443
   |
   v
Reverse proxy / load balancer
   |
   +-- Forwards to backend 10.1.0.20:8080
   |
   v
Spring Boot bound to 10.1.0.20:8080 or 0.0.0.0:8080
   |
   v
Spring MVC / WebFlux processes request
~~~

Distinguish clearly:

1. **DNS:** translates a hostname into an IP (or multiple IPs) for the client. Pointing DNS to an IP does not make the application bind to that IP.
2. **Listening/bind IP:** determines which local socket accepts network connections.
3. **HTTP Host header / HTTP/2 :authority:** identifies the authority the client intends to access at the HTTP layer; it is not synonymous with the address the socket binds to.
4. **Reverse proxy:** can accept traffic on a public IP and connect to the backend on another private IP; from Spring Boot's perspective, the direct peer is usually the proxy.
5. **CORS:** is a browser mechanism restricting JavaScript access to cross-origin responses; it does not open or close a listening socket and is not a firewall.
6. **Authentication/authorization:** determines who is allowed to use an endpoint, even when the network has already permitted the connection.

For example, a server binding 0.0.0.0:8080 can still be reachable only via HTTPS at a reverse proxy because a firewall blocks direct traffic. Conversely, setting strict CORS does not prevent curl, mobile apps, or non-browser clients from connecting directly to the API if the port is open.

### server.address Is Not "the Public Address of the Website"

If public DNS points to load balancer 203.0.113.10 while the application runs on private host 10.1.0.20, do **not** set server.address=203.0.113.10 unless that IP is actually assigned inside the application's network namespace. The backend typically binds to 10.1.0.20 or a wildcard, and the load balancer forwards traffic to that private IP.

The public address the client calls and the internal address the backend binds to can be completely different.

## 8. Spring Boot 3.3.x, Java 17+ Hands-On Exercise

Create a new Spring Boot MVC application or add this example to an existing Boot 3.3.x project. Dependency section in build.gradle of the Spring Boot project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This is only the dependencies block, not the complete build.gradle file with plugins and repositories. Use JDK 17 or higher.

Create src/main/java/com/example/bind/BindAddressApplication.java:

~~~java
package com.example.bind;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BindAddressApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindAddressApplication.class, args);
    }

    @RestController
    static class NetworkController {

        @GetMapping("/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/network")
        String network(HttpServletRequest request) {
            return "local=" + request.getLocalAddr()
                    + ":" + request.getLocalPort()
                    + "; remote=" + request.getRemoteAddr()
                    + ":" + request.getRemotePort();
        }
    }
}
~~~

This is a **complete Java class within a Spring Boot project**. It cannot be compiled with bare javac without Spring Boot, Spring Web, and Jakarta Servlet libraries on the classpath; use the project's Gradle/Maven to run it.

Explanation:

- @SpringBootApplication tells Spring Boot to initialize the context and embedded Tomcat from starter-web.
- /ping has a stable response body of pong, convenient for testing whether the server is accepting requests.
- /network reports the local address/port that ServletRequest sees for the **accepted connection**, and the remote address/port of the direct peer.
- If bound to 0.0.0.0 but accessed from 127.0.0.1, the local address reported by the request is typically 127.0.0.1, not necessarily the wildcard string 0.0.0.0. This is not a configuration error: the wildcard describes the listener, while the local address describes a specific connection.
- If routed through a proxy, the remote address is usually the proxy and the local address is the backend's internal address; it is not the public address or the end user's origin IP.

Initial configuration in src/main/resources/application.yml:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Run at the project root:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Test:

~~~bash
curl -4 -s http://127.0.0.1:8080/ping
~~~

Expected response body, **exact**:

~~~text
pong
~~~

Check connection info:

~~~bash
curl -4 -s http://127.0.0.1:8080/network
~~~

The output looks like local=127.0.0.1:8080; remote=127.0.0.1:<source-port>, where the source port changes on each connection. Do not assert a fixed stdout because ephemeral ports are dynamically allocated by the OS.

### Experiment A: localhost Only

Keep:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

From the same host, /ping via 127.0.0.1 works. From Machine B on the LAN, trying http://192.168.1.50:8080/ping typically fails to connect **via this listener** because the server only binds to loopback. Note that 192.168.1.50 must be the real IP of Host A; if Host A uses another address, substitute accordingly.

### Experiment B: Bind to a LAN Address

Set Host A's actual IP, for example:

~~~yaml
server:
  address: 192.168.1.50
  port: 8080
~~~

Restart. Once bound successfully, test directly to http://192.168.1.50:8080/ping from Machine A; then try from Machine B. Whether Machine B can connect still depends on subnet/route and firewalls. Testing http://127.0.0.1:8080/ping may fail because the listener is attached to the LAN IP rather than loopback.

### Experiment C: Bind All IPv4 Interfaces

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Restart. Test on Host A:

~~~bash
curl -4 -s http://127.0.0.1:8080/ping
curl -4 -s http://192.168.1.50:8080/ping
~~~

Both can return pong when the host's network and firewall allow it. From Machine B on the LAN, also try http://192.168.1.50:8080/ping. The difference between testing on Machine A and Machine B helps separate **bind** issues from **route/firewall** issues.

### Experiment D: localhost Hostname and IPv6

If the OS/JVM supports IPv6, set:

~~~yaml
server:
  address: "::1"
  port: 8080
~~~

Run:

~~~bash
curl -6 -s "http://[::1]:8080/ping"
~~~

Expected result is pong. An IPv4 connection to 127.0.0.1:8080 is not considered equivalent. If the command fails, check IPv6 support and the actual listener before concluding the server is misconfigured.

**Experiment note:** Whenever you change address/port, you must restart the application so a new socket is bound. Editing the YAML file without restarting the running server does not automatically change the listening socket address.

## 9. Identifying the Real IP and Listening Socket

A common mistake is reading only the log line "Tomcat started on port 8080" and assuming the server is definitely listening on all interfaces. Check the **local address** of the listening socket.

### Linux

View addresses on the machine:

~~~bash
ip -br address
~~~

View listening TCP sockets on port 8080:

~~~bash
ss -ltnp 'sport = :8080'
~~~

If an environment lacks permission to view process names, ss can still list listeners without showing PID/process. Common output patterns:

~~~text
127.0.0.1:8080     IPv4 localhost only
192.168.1.50:8080  IPv4 LAN address only
0.0.0.0:8080       IPv4 wildcard
[::1]:8080         IPv6 loopback
[::]:8080          IPv6 wildcard
~~~

These are **sample values**, not an actual transcript of a run. Notation may appear as *:8080 or an IPv6 form depending on the tool.

### Windows PowerShell

View IPs and interfaces:

~~~powershell
Get-NetIPAddress -AddressFamily IPv4
~~~

View listeners on port 8080:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Check from another machine:

~~~powershell
Test-NetConnection -ComputerName 192.168.1.50 -Port 8080
~~~

If multiple processes are open, use OwningProcess to cross-reference the JVM's PID. A wildcard address in the output only shows that the server **can** accept connections on the corresponding interfaces; it does not prove that the firewall allows other machines to call it.

### Checking Both the Request and the Route

~~~bash
curl -4 -v http://127.0.0.1:8080/ping
curl -4 -v http://192.168.1.50:8080/ping
~~~

Run the second command from **another machine** to verify genuine LAN connectivity. If run from the server itself, the OS may route packets to an IP owned by the machine itself without traversing the external network path, so it is not proof that LAN clients can reach it.

In environments using an HTTP proxy configured by environment variables, curl may go through another proxy. When you need to test a direct connection, use the --noproxy '*' option for curl commands and pay attention to shell escaping rules.

## 10. Docker: Two Different Binding Layers

When running Spring Boot inside a container, there are two separate steps:

1. **Bind inside the container:** the address the JVM listens on inside the container's network namespace, set by server.address.
2. **Publish on the Docker host:** the host port mapped to the container port by Docker, set by -p or ports.

Example:

~~~text
Laptop (Docker host)              Container
192.168.1.50                      172.18.0.2 (example)
     |                                 |
Host port 8080 --Docker NAT--------> container port 8080
                                        |
                                   Spring Boot listener
~~~

### Mistake: server.address=127.0.0.1 Inside the Container

If the application binds 127.0.0.1:8080 **inside the container**, it listens on the container's loopback. Docker publishes to the container's network IP, so the host may be unable to reach the service even when using -p 8080:8080.

To receive connections forwarded by Docker, commonly use:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

This configuration does not make Docker open a host port; it only allows the app to accept traffic on IPv4 interfaces **inside the container**.

### Publishing on All Host Addresses vs. localhost Only

Run a pre-built image:

~~~bash
docker run --rm -p 8080:8080 my-spring-boot-app:latest
~~~

In a typical default bridge configuration, Docker publishes host port 8080 on all host addresses, allowing clients with a network path to the host to access it if the firewall permits.

Publish only to the Docker host loopback:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 my-spring-boot-app:latest
~~~

This is completely different from setting server.address=127.0.0.1 **inside the container**. The commonly desired setup: Spring Boot binds 0.0.0.0 inside the container, and the Docker host publishes only 127.0.0.1 if the service is for local development.

| Layer | Example Option | Meaning |
|---|---|---|
| Spring Boot inside container | server.address=0.0.0.0 | Listens on the container's IPv4 interfaces |
| Docker publish on host | -p 127.0.0.1:8080:8080 | Maps host port only on loopback |
| Docker publish on host | -p 8080:8080 | Usually maps port on all host interfaces |
| Host firewall | Allow/block TCP 8080 | Controls packets from external networks into the host |

**Docker version note:** Docker documentation notes that some older versions before 28.0.0 had cases where hosts on the same L2 could reach localhost-published ports. Therefore, do not treat host port binding as a complete substitute for firewalls and network isolation.

### Compose

Sample configuration:

~~~yaml
services:
  api:
    image: my-spring-boot-app:latest
    environment:
      SERVER_ADDRESS: "0.0.0.0"
      SERVER_PORT: "8080"
    ports:
      - "127.0.0.1:8080:8080"
~~~

The environment variables SERVER_ADDRESS and SERVER_PORT are mapped by Spring Boot to the corresponding properties. With this Compose file, the backend listens inside the container, while the host's public port is restricted to loopback. When LAN devices need access for a demo, deliberately change the host publish binding and manage the firewall at the same time.

Do not set server.address to the **Docker host's LAN IP** inside the container, because normally that IP does not belong to the container's network namespace.

## 11. Kubernetes and Cloud: Socket Binding Differs from Service Exposure

In Kubernetes, Pods normally have their own IPs. Kubelet, Services, or Ingress communicate with Pods over the Pod network; therefore, web applications in containers typically must listen on the Pod IP or 0.0.0.0.

Example container configuration:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

A Service can forward traffic from ClusterIP/port to Pod IP:8080. **A Pod listening on 0.0.0.0 does not mean the Internet can call the Pod directly**; reachability depends on the Kubernetes Service type, Ingress/Gateway, routing, and NetworkPolicy.

If the app only binds 127.0.0.1 inside the Pod, a normal Service accessing via Pod IP may fail to connect. Except for certain sidecar mechanisms or intentional loopback sharing within the same network namespace, avoid binding loopback for applications that need to receive traffic from outside the Pod.

### Cloud VMs and Load Balancers

A VM with private IP 10.1.0.20 and public IP 203.0.113.10 may use NAT in the cloud platform. 203.0.113.10 might not be assigned directly to a NIC inside the VM. If you set server.address=203.0.113.10 when that address does not exist on the VM, socket binding will fail.

Common approach: the server binds 0.0.0.0 or the private NIC IP; security groups/firewalls and load balancers control inbound traffic.

### Ensuring the Right Path for Health/Readiness Probes

An HTTP health check targeting a Pod IP or private VM IP will not pass through the probing process's own localhost if the probe runs on another node. When investigating failed readiness, examine:

- Does the app listen on the IP the probe uses?
- Does the probe use the right port and scheme (HTTP/HTTPS)?
- Has the container/Pod finished startup?
- Is a firewall/NetworkPolicy blocking the connection?
- Does the endpoint return an appropriate status code?

Do not fix this by disabling readiness or blindly opening all ports; pinpoint the exact network path the probe is taking.

## 12. Reverse Proxy and Actuator: Separating Public and Internal Surfaces

A common deployment:

~~~text
Internet -> HTTPS 443 on Nginx
                     |
                     v
              Spring Boot :8080
~~~

If Nginx and Spring Boot run on the **same host**, the backend can bind 127.0.0.1:8080 so Nginx uses proxy_pass to 127.0.0.1:8080. This reduces the publicly exposed network surface.

If Nginx runs in a **different container or different server**, 127.0.0.1 on Nginx's side points to Nginx, not the app. In that case, use an internal hostname/IP routable to Spring Boot and bind the backend to the appropriate interface.

### Management Endpoints Can Have a Separate Listener

When using Spring Boot Actuator and wanting management endpoints to listen only on localhost with a separate port, Spring Boot 3.3 supports for example:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Meaning: the main app listens on port 8080, while the management web server on port 8081 binds loopback. According to Spring Boot documentation, **management.server.address requires a custom management.server.port** in order to use a different bind address from the main server.

This configuration does not replace Actuator authorization. Endpoint access still depends on exposure, Spring Security, proxies, firewalls, and deployment topology. In containers, binding management to loopback can prevent kubelet or external monitoring outside the Pod from calling it; design probes and management networking accordingly.

## 13. Security and Operational Points to Understand Correctly

### Wildcard Binding Can Widen the Connection Surface

When running a laptop with Wi-Fi, VPN, and a Docker bridge, server.address=0.0.0.0 can cause the app to receive requests over multiple unintended interfaces. If the project has experimental endpoints or unprotected admin APIs, machines on the network may try to access them when the firewall permits.

Principles:

- For development that only needs local access, use 127.0.0.1/::1 if remote access is unnecessary.
- For public services, let the gateway/reverse proxy handle TLS, authentication, and rate limiting according to architecture.
- Restrict inbound traffic using firewalls, cloud security groups, or Kubernetes NetworkPolicies; do not rely on CORS.
- Do not expose sensitive Actuator or debug endpoints just because server.address configuration was convenient.

### Bind Address Is Not an Authentication Policy

server.address=192.168.1.50 only limits the socket to accept traffic directed to that IP; any client with a network path to IP:port can connect if the firewall permits. Which users can use the API must be decided by authentication/authorization.

### TLS and Hostname Remain Independent

An HTTPS application with a certificate for api.example.com can bind on 0.0.0.0:8443. Certificates are verified against the hostname the client uses to access it, not against the wildcard on the listening socket. Changing server.address does not fix a TLS certificate mismatch error.

### Do Not Equate 0.0.0.0 with 0 or localhost

- **0.0.0.0**: IPv4 wildcard address when binding.
- **0** in server.port=0: requests dynamic port selection.
- **127.0.0.1**: IPv4 loopback.
- **localhost**: hostname resolved on the calling/running machine.
- **::**: IPv6 wildcard; dual-stack depends on the environment.
- **::1**: IPv6 loopback.

## 14. Connection Troubleshooting Procedure

When a client cannot reach the application, check in order from nearest to farthest:

1. **Did the application start successfully?** Check bind exceptions, startup logs, and the actual port. If server.port=0, find the OS-assigned port.
2. **Which address is listening?** Use ss -ltnp or Get-NetTCPConnection, distinguishing 127.0.0.1, specific IPs, and wildcards.
3. **Does that IP belong to the current machine/container?** Use ip address or Get-NetIPAddress. If it does not belong to the host, fix server.address.
4. **Can you reach it from the same network namespace?** Use curl -4 http://127.0.0.1:port or the exact IP the server is bound to.
5. **Does another client have a route to the destination IP?** Check DNS resolution, private/public IPs, VPN, subnets, and routes.
6. **Does the firewall/security group allow that TCP port?** Check host firewalls, cloud network policies, and container port publishing.
7. **Is there a proxy, NAT, or load balancer in between?** Check upstream target IP/port, service discovery, and TLS termination.
8. **Is there IPv4/IPv6 confusion?** Check curl -4/curl -6 and listeners per address family.
9. **TCP connected, but HTTP returns an error?** Then analyze routes/controllers, context paths, Host headers, HTTPS schemes, security filters, and application logs; the issue may be at the HTTP layer rather than binding.
10. **Was the application restarted after changing config?** Listening sockets do not automatically update when you only edit application.yml.

### Identifying Common Symptoms

| Symptom | Possible Cause | Resolution Direction |
|---|---|---|
| localhost works, another LAN machine cannot connect | App only binds 127.0.0.1; or firewall/route blocks | Inspect listener then open the right interface and firewall |
| LAN IP works, IPv4 localhost does not work | App binds to a specific LAN IP | Use the right IP, or wildcard if both are needed |
| Startup reports Cannot assign requested address | Binding to an IP that does not exist on the host/container | Determine real local IP and fix server.address |
| Startup reports Address already in use | IP:port is occupied by another process; IPv4/IPv6 conflict | Check listener PID, change port, or stop old process |
| curl localhost behaves inconsistently between IPv4/IPv6 | localhost resolves to ::1 or 127.0.0.1 differently from the listener | Force curl -4 / -6, set explicit bind address |
| Docker -p is declared but host cannot connect | App inside container only binds 127.0.0.1 | Bind 0.0.0.0 inside container, verify host publish |
| Container calls localhost to connect to database running on host | localhost inside container is the container | Use host-specific hostname/route or internal network |
| Kubernetes Service times out | App only binds Pod loopback or wrong NetworkPolicy/Service | Check Pod IP, targetPort, endpoints, policy |
| Curl to IP works but browser JS reports CORS | HTTP connection already reached the server; origin policy differs | Configure CORS properly; do not change bind to fix CORS |
| Nginx reports 502 | Nginx cannot reach upstream or app is not ready | Check upstream IP:port and network namespace |

### Cases Where You Cannot Conclude from a Single Test

If a local curl to http://192.168.1.50:8080 succeeds, you have **not proved** that another LAN machine can connect. The local OS can deliver packets to an IP owned by the same machine without going out over the LAN. Run the request from a client outside the host and check firewalls/routes.

If you see 0.0.0.0:8080 in ss, you have **not proved** the service is exposed to the Internet. NAT, routes, security groups, ingress rules, and other listeners can still block or alter the path.

If the local server reports remote address=127.0.0.1, you have **not proved** the end user is accessing from localhost. A reverse proxy on the same machine may be the server's direct peer, so backend logs see the proxy.

## 15. Self-Check Questions

**Question 1.** Machine A runs Spring Boot at 127.0.0.1:8080. Machine B uses http://localhost:8080. Has B called A?

**Answer:** No. localhost on B points to B. The backend needs to listen on an IP that B has a network path to, such as A's LAN IP, and the firewall must allow it.

**Question 2.** Server binds 0.0.0.0:8080. In Machine B's browser, which URL should you type?

**Answer:** A's actual IP or hostname, for example http://192.168.1.50:8080. 0.0.0.0 is a wildcard bind, not a service address clients should use.

**Question 3.** Machine A has 192.168.1.50 and 10.8.0.7, but Spring Boot binds 192.168.1.50. Will a client on the VPN calling 10.8.0.7:8080 hit this listener?

**Answer:** Not via the socket bound to 192.168.1.50. To accept traffic on the VPN IP, bind to that IP, use an appropriate wildcard, or set up a valid forwarding proxy.

**Question 4.** A Docker image runs the app with server.address=127.0.0.1, and the Docker host maps -p 8080:8080. Why does the host machine not receive a response?

**Answer:** The app's listener exists only on container loopback; mapping from the host normally routes to the container's network address. Have the app listen on a container interface such as 0.0.0.0 and decide the host publish binding separately.

**Question 5.** Running curl http://localhost:8080 fails, but curl http://127.0.0.1:8080 succeeds. What is worth checking?

**Answer:** localhost may resolve preferring IPv6 ::1, while the server only listens on IPv4. Check DNS/hosts, curl -4/-6, and listening sockets.

**Question 6.** Does binding an application to a wildcard automatically ensure HTTP endpoints are only used by people inside the company?

**Answer:** No. Access protection depends on routing, VPN, firewalls, authentication/authorization, and other network policies.

**Question 7.** An application has public URL https://api.example.com, yet the backend only has private IP 10.1.0.20. Should you set server.address=the load balancer's public IP?

**Answer:** No, unless that public address actually exists on the NIC/backend namespace. Normally the backend binds the private IP or a wildcard and the load balancer forwards requests to the backend.

**Question 8.** If management.server.address=127.0.0.1 yet management.server.port still uses the same port as the app, does the configuration behave as intended?

**Answer:** No. For management endpoints to bind to a separate address, Spring Boot requires declaring a separate management.server.port.

## 16. Checklist When Configuring in a New Environment

- [ ] Identify the IP of the **host or network namespace running the JVM**, without confusing it with the IP of your laptop, Docker host, reverse proxy, or load balancer.
- [ ] Decide whether the service is local-only, single-NIC only, or needs to listen on multiple interfaces.
- [ ] Choose 127.0.0.1, a specific IP, or 0.0.0.0 for IPv4 needs; check IPv6 separately if applicable.
- [ ] Set server.port and check whether the port is already occupied.
- [ ] Check the listener after starting with ss/netstat/PowerShell.
- [ ] Use a real IP/hostname when calling from another client; localhost always means the client's own machine.
- [ ] For Docker, check **both** server.address inside the container **and** host publish mapping.
- [ ] For Kubernetes/cloud, check Pod/VM IP, Service, ingress, routes, security groups, and network policies.
- [ ] With a reverse proxy, verify the upstream URL is reachable from where the proxy runs.
- [ ] With Actuator, separate management binding, port, and authorization.
- [ ] Test IPv4/IPv6 independently when the environment supports dual-stack.
- [ ] Verify from a real client outside the host before declaring the service reachable.

## References

- [Spring Boot 3.3 — Common Application Properties: server.address, server.port, management.server.address](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Docker Docs — Port publishing and mapping](https://docs.docker.com/engine/network/port-publishing/)
- [Kubernetes — Services, Load Balancing and Networking](https://kubernetes.io/docs/concepts/services-networking/)