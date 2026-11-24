# Configuring server.port, server.address, and Listening Network Addresses in Spring Boot

## 1. Three Different Questions When Running an HTTP Server

A Spring Boot application includes an embedded web server (Tomcat, Jetty, Undertow, or Reactor Netty, depending on the web stack and dependencies). When the server starts, it needs to open a socket to accept connections from clients. Two important properties are **server.port** and **server.address**:

- **server.port**: which TCP port does the server listen on?
- **server.address**: which IP address/interface of the machine running the application does the server bind to?
- **The address clients use to access it**: which URL can a client use to connect from its own network location?

These are three related but not identical questions. For example, a server binding to 0.0.0.0:8080 means it accepts IPv4 connections on suitable local IPv4 addresses. Clients do not use the URL http://0.0.0.0:8080 to access it from another machine; clients must use an IP or hostname that is routable to the host, such as http://192.168.1.20:8080.

Illustration:

~~~text
Client A (same machine) -- http://127.0.0.1:8080 --> Spring Boot
Client B (another machine) -- http://192.168.1.20:8080 --> Spring Boot

Spring Boot binds:
  127.0.0.1:8080  -> only via the loopback of the machine running the process
  192.168.1.20:8080 -> via a specific IPv4 address, if this IP belongs to the machine
  0.0.0.0:8080    -> all suitable local IPv4 addresses

Whether a client can connect also depends on routes, firewalls, NAT,
container/network namespaces, and proxy configuration.
~~~

**Bind address** is the local address that the operating system assigns to the listener. **Destination address** in the client's URL is the address that the client can route to. Meanwhile, public hostnames, DNS, reverse proxies, and TLS may reside at other layers.

## 2. Configuring server.port

In a typical embedded web Spring Boot application, server.port defaults to **8080** unless overridden by configuration or the environment.

Configuration in src/main/resources/application.yaml:

~~~yaml
server:
  port: 8085
~~~

Equivalent in application.properties:

~~~properties
server.port=8085
~~~

With this configuration, the HTTP server is expected to listen on TCP port 8085, provided there are no startup errors such as the port already being in use or an invalid bind address.

### Common Port Values

| Value | Meaning |
|---|---|
| Not declared | Usually uses 8080 |
| 8085 | Requests the server to listen on TCP port 8085 |
| 0 | Lets the operating system allocate an available port; useful for integration testing |
| -1 | Disables opening a listening HTTP endpoint in an embedded web application, while still allowing WebApplicationContext creation |
| Out-of-range number | Invalid configuration or cannot bind; do not use |

**server.port=0** does not mean the server actually listens on port 0. Zero is a request for dynamic port allocation; after the server starts, the actual port is typically a positive number chosen by the operating system. Therefore, do not construct a URL pointing to localhost:0.

**server.port=-1** is not the same as spring.main.web-application-type=none. Setting -1 still allows creating the web application context while disabling the HTTP listener; whereas web-application-type=none selects a non-web application type and does not start an embedded web server under the normal model.

A port may already be occupied by another process or not permitted for use. On some operating systems, binding to privileged ports such as 80 or 443 requires appropriate permissions or capability grants. Setting server.port does not automatically open firewalls, NAT, or routers.

## 3. Configuring server.address

The **server.address** property controls the IP address that the web server binds to; the configuration data type is resolved by Spring Boot into a network address.

Example accepting requests only on IPv4 loopback:

~~~yaml
server:
  port: 8080
  address: 127.0.0.1
~~~

With this setup, a client on the same machine or in the same network namespace can call http://127.0.0.1:8080. Another machine on the LAN typically cannot access this listener using the host's LAN IP, even if it knows the port, because the listener is not bound to the LAN interface.

Example accepting connections on all local IPv4 addresses:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
~~~

Here, 0.0.0.0 is the **IPv4 wildcard bind address**. It is not a hostname or the application's public destination address. Even when the server binds to the wildcard, firewalls and routing still need to permit clients from other networks to connect.

Example binding only to a specific LAN IP of the machine:

~~~yaml
server:
  port: 8080
  address: 192.168.1.20
~~~

This configuration is only valid if the address 192.168.1.20 is actually assigned to an interface in the environment running the process. If the machine does not have that address, the server typically fails with an error such as Cannot assign requested address, BindException, or an equivalent bind error.

### Comparison Table of Common Addresses

| server.address | Listener | Key Points to Remember |
|---|---|---|
| Not declared | Usually binds to a wildcard according to the embedded server and OS defaults | Check the actual listener; defaults may be affected by IPv4/IPv6 |
| 127.0.0.1 | IPv4 loopback only | Suitable when HTTP only needs local machine access |
| 0.0.0.0 | All suitable local IPv4 addresses | Clients on other machines must use a real IP/hostname, not 0.0.0.0 |
| 192.168.1.20 | Specific IPv4 IP | The IP must belong to a local interface in the runtime environment |
| ::1 | IPv6 loopback | Not synonymous with IPv4 loopback |
| :: | IPv6 wildcard | Whether IPv4 connections are also supported depends on dual-stack, OS, and server |

When server.address is not declared, the exact binding behavior is determined by the embedded server, JVM, and operating system. Some environments prefer the IPv6 wildcard; whether IPv4 is accepted alongside it depends on dual-stack configuration. Therefore, inspect the actual socket if you have strict requirements for IPv4 or IPv6.

**Not every string that looks like a machine name is a suitable bind address.** If you use a hostname, it must resolve to an IP address that the machine actually owns. Using an IP literal is usually easier to verify, especially when deploying to containers or multi-interface environments.

## 4. Understanding Loopback, Wildcard, and Specific Interfaces Accurately

### Loopback: 127.0.0.1 and ::1

Loopback is the path from a process to the network stack of that same machine or namespace. 127.0.0.1 is IPv4 loopback, while ::1 is IPv6 loopback.

For example, Spring Boot binds to 127.0.0.1:8080. From the host machine:

~~~bash
curl -v http://127.0.0.1:8080/health
~~~

The request can reach the application if the /health endpoint exists. From another machine, using 127.0.0.1 points back to the **client machine**, not the machine running Spring Boot.

In a container, 127.0.0.1 is the loopback inside the container or the process's network namespace. It is not the host's loopback in the standard container networking model. This is a common cause of the issue where the host has published a port yet connections still cannot reach the service inside the container.

### Wildcard: 0.0.0.0 and ::

Binding to 0.0.0.0:8080 typically allows the socket to accept connections sent to any suitable local IPv4 address of the process. If the machine has loopback, a LAN IP, and a VPN IP, a wildcard listener can receive requests through those paths, provided firewalls/routing allow it.

0.0.0.0 is an IPv4 wildcard bind notation, not an address intended for end users. Some local tools may accept http://0.0.0.0 as an address to connect to, but this is neither an accurate nor a portable way to describe a public endpoint.

The IPv6 wildcard :: has its own behavior. Some operating systems configure IPv6 sockets to accept IPv4 as IPv4-mapped addresses, while others enable IPv6-only. Do not assume :: is always equivalent to 0.0.0.0.

### Specific Interface IP

Binding to 192.168.1.20:8080 only accepts connections matching that address. This is useful when a server has multiple interfaces and you want to listen only on a specific network.

However, a private address can change when DHCP reassigns an IP, when a pod is redeployed, or when a container runs on a new host. Therefore, hardcoding a local IP into server.address is generally unsuitable for orchestrated container environments.

## 5. Connecting to the Listener from a Client

For a client to reach the server, all of the following must be satisfied simultaneously:

1. The application actually starts up and creates a listening socket.
2. The server binds to an address that receives incoming traffic.
3. The port the client uses matches the listener's port, or there is a proxy/port mapping forwarding to it.
4. The IP or hostname the client uses resolves and routes to the right machine/network namespace.
5. Firewalls, security groups, network policies, and proxies allow the connection.
6. If HTTPS is used, TLS must be properly configured on the server or at the reverse proxy.

**server.address does not register DNS** and **server.port does not automatically configure NAT**. A hostname can be published in public DNS and a reverse proxy can listen on port 443, while Spring Boot only opens 127.0.0.1:8080 or 0.0.0.0:8080 on the internal network.

Example topology:

~~~text
Browser
https://shop.example.org:443
        |
        v
Load balancer / reverse proxy :443
        |
        v
Spring Boot :8080 (private network)
~~~

In this model, the client uses port 443 and the public hostname. Spring Boot listens on port 8080. Having two different ports is not an error; that is how a reverse proxy forwards requests. Spring Boot's bind address must match the internal connection from the proxy.

If you want to terminate HTTPS directly in Spring Boot, you need to configure TLS (server.ssl.* or an SSL bundle configuration appropriate for your Boot version) along with the desired port. Changing server.port from 8080 to 443 **does not automatically turn HTTP into HTTPS**.

## 6. Runnable Spring Boot Example to Observe Binding

Use a Spring Boot 3.x application with Java 17+, the spring-boot-starter-web dependency, and App.java:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class App {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }

    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
~~~

Place the file at src/main/java/example/App.java and application.yaml at src/main/resources/application.yaml:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
~~~

Run inside a Spring Boot Maven project that declares starter-web:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell, use:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

From the same machine running the application:

~~~bash
curl -s http://127.0.0.1:8085/hello
~~~

The expected **HTTP response body** is:

~~~text
hello
~~~

This is the response body, not the entire stdout when Spring Boot starts up. Startup logs may vary depending on the server version, log configuration, and environment.

If you change address to 0.0.0.0 and restart the application, the same endpoint can be accessed via the machine's actual LAN IP, such as http://192.168.1.20:8085/hello, **if that IP belongs to the host and the network path permits it**. Do not treat the example 192.168.1.20 as the real IP of every machine.

This example requires Spring Boot dependencies and a Maven project; it cannot be compiled with a bare javac command using only the Java Standard Library, because it imports Spring classes.

## 7. Environment-Specific Configuration and Precedence

The server.* properties are externalized configuration and can be placed in application.properties, application.yaml, profile-specific files, environment variables, or command-line arguments.

Example application.yaml for shared values:

~~~yaml
server:
  port: 8080
~~~

Example application-dev.yaml for development:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
~~~

Example application-prod.yaml for deployment on a private network:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
~~~

When the dev profile is activated, Spring Boot uses the corresponding values according to PropertySource precedence. Understand that an active profile does not mean every value comes from that file: environment variables, command-line options, or configuration sources with higher precedence can override them.

Example overriding the port at runtime:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

Or running a JAR file:

~~~bash
java -jar app.jar --server.port=9090 --server.address=127.0.0.1
~~~

Common environment variables using relaxed binding:

~~~bash
export SERVER_PORT=9090
export SERVER_ADDRESS=0.0.0.0
java -jar app.jar
~~~

Depending on the shell environment, the syntax for setting environment variables may differ. PowerShell example:

~~~powershell
$env:SERVER_PORT = "9090"
$env:SERVER_ADDRESS = "127.0.0.1"
java -jar app.jar
~~~

In a project with configuration from multiple sources, verify the effective value at runtime. Do not read a single application.yaml file and conclude for certain that the server is using that port if profiles, environment variables, or command-line overrides are present.

## 8. Server in Docker and Kubernetes

### Docker: Listening Inside the Container and Port Publication on the Host

Example running an application image:

~~~bash
docker run --rm -p 8085:8080 -e SERVER_PORT=8080 -e SERVER_ADDRESS=0.0.0.0 my-spring-app
~~~

Here:

- The container process listens on port 8080 and binds 0.0.0.0 inside the container's network namespace.
- Docker publishes port 8085 on the host and forwards it to port 8080 of the container.
- Clients on the host typically use http://localhost:8085.
- Clients from other machines wanting to reach the host must use the host's network address and be permitted by firewalls/routing.

If the application inside the container only binds 127.0.0.1, the published port may be unreachable from the host via bridge networking because port forwarding goes to the container's network address, not its internal loopback.

Avoid confusing the two syntaxes:

- **server.port**: the port the server binds **inside the container**, for example 8080.
- **docker -p 8085:8080**: maps **host port 8085** to **container port 8080**.

Dockerfile EXPOSE 8080 only documents the intended port; by itself it does not publish any port on the host. Some environments have networking different from the default bridge, so check the actual topology.

### Kubernetes: containerPort Does Not Automatically Expose a Public Endpoint

A container in a Pod may specify:

~~~yaml
ports:
  - containerPort: 8080
    name: http
~~~

containerPort describes the port the process is expected to listen on; Kubernetes does not automatically turn this line into a listener. Spring Boot must still bind to the right address and port.

A Kubernetes Service can route to a Pod port via targetPort. Example:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-api
spec:
  selector:
    app: web-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

This Service routes cluster-internal port 80 to port 8080 on the selected Pods. It does not start the server by itself, does not change the application's server.port, and does not mean the Service is accessible from the Internet.

A Kubernetes Pod IP belongs to a network environment that can change. For containerized applications, binding 0.0.0.0 with a deployment-configured port is usually more stable than hardcoding a Pod IP into server.address. Connectivity to a Pod also depends on Services, Ingress/Gateway, CNI, and NetworkPolicy.

## 9. server.port=0 and How to Retrieve the Actual Port

Setting the port to 0 is useful when multiple integration tests run in parallel because each test server can be assigned its own port by the OS.

~~~yaml
server:
  port: 0
~~~

In a Spring Boot test using a random port:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AppHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void respondsOnAssignedPort() {
        String body = restTemplate.getForObject(
                "http://localhost:" + port + "/hello",
                String.class
        );
        assertThat(body).isEqualTo("hello");
    }
}
~~~

This is test code in the same Spring Boot 3.x project with spring-boot-starter-test and the /hello controller from the previous example. It is not a standalone Java snippet; it requires a test context started by Spring Boot.

Note: RANDOM_PORT can override server.port settings from ordinary configuration sources based on how Spring Boot test sets up the environment. @LocalServerPort only has a reliable value after the embedded server has started in an appropriate test environment.

Another way to obtain the bound port is to listen for WebServerInitializedEvent when the web server is ready:

~~~java
package example;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class BoundPortReporter {

    @EventListener
    void afterServerStarted(WebServerInitializedEvent event) {
        int port = event.getWebServer().getPort();
        System.out.println("Actual server port: " + port);
    }
}
~~~

This example is for Spring Boot 3.x. The printed port value is the actual runtime port, so do not assert a fixed stdout when server.port=0 because it may differ on each run.

## 10. Checking the Actually Listening Address and Port

### Checking from the Application

Read the startup logs and check whether the application started up successfully. If the server fails to bind, startup may fail before any endpoint exists.

### Checking the Listener in the Operating System

Linux, for example:

~~~bash
ss -ltnp
~~~

You can filter by port:

~~~bash
ss -ltnp 'sport = :8085'
~~~

On Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8085
~~~

The LocalAddress column or equivalent shows whether the listener is bound to 127.0.0.1, 0.0.0.0, ::1, ::, or a specific IP. What is displayed also depends on the OS and permissions to inspect processes.

### Testing the Connection Path from Multiple Locations

On the machine running Spring Boot:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:8085/hello
~~~

On another machine on the same LAN, replace with the server's actual LAN IP:

~~~bash
curl -v --connect-timeout 3 http://192.168.1.20:8085/hello
~~~

If localhost succeeds but LAN fails, things to check include whether the listener is bound to loopback, firewalls, whether the IP/port is right, and whether there is a route to the server. If both fail, check whether the server started, the endpoint path, and startup errors.

For the localhost hostname having both an A record and an AAAA record, a client may try 127.0.0.1 or ::1. When you want to test a specific address family:

~~~bash
curl -4 -v http://localhost:8085/hello
curl -6 -v http://localhost:8085/hello
~~~

The IPv6 command may fail if the server only binds IPv4, and that does not prove the server is not running.

## 11. Common Errors and How to Resolve Them

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Port 8080 already in use | Another process has already bound the same address/port or there is a conflicting listener | Find the process using ss/netstat/Get-NetTCPConnection; change the port or stop the right process |
| Cannot assign requested address | server.address points to an IP that does not belong to a local interface | Use an existing address or an appropriate wildcard |
| Connects from localhost but other machines cannot connect | Bound to 127.0.0.1, firewall, or no route | Verify the listener, use an appropriate bind address, and check network policies |
| Docker has -p but host cannot access | App only binds 127.0.0.1 inside the container, wrong port mapping, or process hasn't started | Bind 0.0.0.0 inside the container, check container port and published host port |
| server.port=0 but calling localhost:0 | Confusing the port-allocation request value with the runtime port | Retrieve the actual port after startup via event/log or @LocalServerPort |
| Using URL http://0.0.0.0:8080 from another machine | Confusing wildcard bind with client access address | Use the actual IP/hostname of the host or proxy |
| Changed server.port but still running on old port | Environment variable, profile, or CLI override is present | Check configuration sources and effective values |
| HTTP connects but HTTPS fails | TLS not configured or proxy terminates TLS on a different port | Check scheme, port, and server.ssl/reverse proxy |
| Only one of IPv4/IPv6 works | Bound to 127.0.0.1 or ::1, or dual-stack configuration differs from expectations | Verify the local listener and test with curl -4/-6 |
| Kubernetes Service cannot reach Pod | App not bound properly, wrong targetPort/selector, readiness, or network policy | Verify Pod logs, listener, Service endpoints, and targetPort |

Read the actual error message before changing configuration. "Connection refused" usually indicates there is no matching listener at the endpoint or the connection was actively rejected immediately. "Connection timed out" usually requires checking the network path/firewall. HTTP 404 means you connected to the HTTP server, but the path was not handled as expected; in that case, do not jump to concluding it is a wrong bind address.

## 12. Distinguishing the Application Port from Related Ports

Easily confused properties:

- **server.port**: the HTTP port of the application's embedded server.
- **server.address**: the local bind address of that server.
- **management.server.port**: can configure management/Actuator HTTP endpoints on a separate port if the application includes Actuator and appropriate configuration.
- **server.servlet.context-path**: changes the URL path prefix of a servlet application; does not change the address or port.
- **spring.webflux.base-path**: corresponds to the base path of WebFlux when supported by the web stack configuration; not a bind address.
- **server.forward-headers-strategy**: handles forwarded headers from proxies in appropriate cases; does not determine socket binding.

When running behind a proxy, the HTTP Host or X-Forwarded-Host may differ from the address the server is bound to. Do not use the hostname in an HTTP header to infer the listener's local IP. Also do not infer the public URL from server.address because that address belongs to the host infrastructure layer.

## 13. Process for Choosing Configuration per Environment

**Development machine, only needing access from the same machine:** use 127.0.0.1 with a non-conflicting port such as 8080 or 8085. This reduces accidentally exposing the service to the LAN.

**Testing machine on a LAN:** use 0.0.0.0 or a specific LAN interface IP; access via the real LAN IP. Check the firewall and do not assume the network permits all clients.

**Docker or Kubernetes:** typically have the app bind 0.0.0.0 inside the container and expose a consistent container port. Publish the port or use Service/Ingress at the infrastructure layer. Do not hardcode a Pod IP or use 127.0.0.1 inside a container if other components must access it over the network.

**Production behind a reverse proxy:** you can bind a private interface or 0.0.0.0 on a restricted network, set firewall/network policies, and expose publicly only through the proxy. TLS, DNS, rate limiting, authentication, and public ports are typically determined by the deployment architecture.

**Integration tests:** use a random port (server.port=0 or @SpringBootTest RANDOM_PORT) and retrieve the actual port after startup. Avoid hardcoding the same port for multiple test servers running in parallel.

## 14. Pre-Deployment Verification Checklist

1. Web stack and embedded server match the dependencies being used.
2. server.port is the intended port; if using 0, tests/clients read the runtime port.
3. server.address points to an address that can actually be bound in the network namespace.
4. Do not confuse 0.0.0.0 and :: with a hostname or public URL.
5. Clients use an address/port routable to the server or proxy.
6. Firewalls, NAT, container port mappings, Service/Ingress, and TLS match the topology.
7. Verified the effective configuration after applying profiles, environment variables, and CLI arguments.
8. Tested requests from the exact place where actual clients run, not just from the server's localhost.
9. Distinguished between connection errors, HTTP status errors, and route/endpoint errors.
10. For environments with multiple interfaces or IPv4/IPv6, confirmed the actual socket listener.

Remember: **server.port chooses the port**, **server.address chooses the local IP/interface to bind**, and **the client URL depends on DNS, routing, and the infrastructure layers in front**. Understanding these three roles helps configure Spring Boot applications accurately when running locally, on multi-NIC servers, in containers, and behind reverse proxies.