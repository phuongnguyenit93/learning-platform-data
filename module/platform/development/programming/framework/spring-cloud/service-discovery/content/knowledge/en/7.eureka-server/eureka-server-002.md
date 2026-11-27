# Initializing a Server with Starter and `@EnableEurekaServer`

## Objectives

After this lesson, you will be able to:

- Create a Spring Boot application acting as a Eureka Server.
- Add the right starter and enable the server using `@EnableEurekaServer`.
- Configure a standalone registry for Eureka Clients to register and look up services.
- Distinguish standalone server configuration from a multi-node Eureka cluster configuration.
- Start, verify, and secure Eureka Server in a deployment environment.

## What Role Does Eureka Server Play?

In Spring Cloud Service Discovery, applications need a place to store information about instances currently providing services. Eureka Server provides that registry. Eureka Client in each application registers its instance, sends heartbeats, and fetches the instance list from the server.

Spring Cloud Commons defines abstractions such as `DiscoveryClient` for looking up instances and `ServiceRegistry` for registering or deregistering. Eureka is a specific implementation of this mechanism. Eureka Server is the process that stores and serves the registry; Eureka Client is the component added to applications that need to participate in the registry. These two roles normally run in separate applications.

The `spring-cloud-starter-netflix-eureka-server` starter provides the server integration. The `@EnableEurekaServer` annotation activates the Eureka Server configuration in a Spring Boot application. Adding the dependency alone is not enough to turn an application into a server.

## 1. Preparing Dependencies

Spring Boot and Spring Cloud must use compatible versions. Choose a Spring Cloud release train compatible with your project's Spring Boot version and use the Spring Cloud BOM to manage versions consistently. The Eureka Server starter below does not declare its own version because the BOM manages it.

### Maven

Add the BOM to `dependencyManagement` and the starter to `dependencies`:

~~~~xml
<properties>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
~~~~

Replace `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` with the release train compatible with the Spring Boot version in use. If the project already imports the Spring Cloud BOM in a parent POM or shared dependency configuration, keep the existing BOM and only add the starter.

### Gradle Kotlin DSL

With Gradle Kotlin DSL, you can import the BOM using `platform`:

~~~~kotlin
val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-server")
}
~~~~

After syncing dependencies, inspect the dependency tree if the build reports conflicts. Do not mix different Spring Cloud release trains in the same application.

## 2. Creating the Eureka Server Startup Class

Create a standard Spring Boot application and place `@EnableEurekaServer` on the main configuration class. For example:

~~~~java
package com.example.discoveryserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
~~~~

`@SpringBootApplication` enables Spring Boot's auto-configuration and component scanning. `@EnableEurekaServer` activates the components required for the application to provide the Eureka registry and dashboard. Place this class in the root package so other application components are scanned following the standard structure.

Do not place `@EnableEurekaServer` in every microservice. Business applications that only need to register and discover services normally add the Eureka Client starter. Only the application acting as the registry uses the Eureka Server starter and this annotation.

## 3. Configuring a Standalone Server

For learning or local development environments, start with a single Eureka Server. Create `src/main/resources/application.yml`:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
~~~~

Meaning of the properties:

| Property | Meaning |
| --- | --- |
| `spring.application.name` | Spring Boot application name; helps identify the server process in logs and configuration. |
| `server.port` | HTTP port that Eureka Server listens on. `8761` is the port commonly used in Eureka examples. |
| `eureka.client.register-with-eureka` | Disables the server registering itself as a client with the registry. |
| `eureka.client.fetch-registry` | Disables the server fetching the registry from another peer when running standalone. |

The last two options clarify standalone mode: the server does not need to register itself or fetch the registry from another Eureka Server. Eureka Clients can still register with this server and fetch the registry from it.

Do not confuse `spring.application.name` with the service IDs managed by the server. For example, `discovery-server` is the registry application name; `inventory-service` and `order-service` are service names registered by clients.

## 4. Starting and Verifying

After configuring the dependencies, startup class, and YAML, run the application with Maven or Gradle:

~~~~bash
./mvnw spring-boot:run
~~~~

Or:

~~~~bash
./gradlew bootRun
~~~~

On Windows, you can use `mvnw.cmd` or `gradlew.bat` respectively. Once the application starts successfully:

1. Check the logs showing Spring Boot started on port `8761`.
2. Open `http://localhost:8761` to view the Eureka dashboard.
3. Verify the dashboard displays the server and the list of registered instances.
4. Start an application with Eureka Client pointing to `http://localhost:8761/eureka/`.
5. Confirm the client's service ID appears on the dashboard after registration.

The dashboard may display an empty registry when no clients have registered yet. That does not mean the server is not working. Conversely, being able to open the dashboard page only confirms that the HTTP interface is reachable; verify a successful client registration to confirm the discovery flow works end-to-end.

## 5. Configuring a Multi-Node Eureka Cluster

A single Eureka Server is suitable for development or testing environments. In deployments requiring fault tolerance, you can run multiple Eureka Servers and configure them as peers. Each node exchanges its registry with declared peers so registration data is replicated across nodes.

For example, node `eureka-a` runs on `8761` and node `eureka-b` runs on `8762`. Node A's configuration points to B:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  instance:
    hostname: eureka-a
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-b:8762/eureka/
~~~~

Node B configures its own hostname and port, while pointing `defaultZone` to node A:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8762

eureka:
  instance:
    hostname: eureka-b
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-a:8761/eureka/
~~~~

The hostnames in the example must be resolvable and the nodes must be able to reach each other over the network. In real deployments, replace them with DNS names or stable internal infrastructure addresses. With more than two nodes, each node declares the remaining peers following the same principle. Avoid having a node point only to itself in peer configuration, as that creates no registry exchange between nodes.

Business clients should be configured to reach Eureka endpoints suitable for the topology, such as via a peer list or an internal load-balanced address designed for Eureka. When deploying a cluster, verify both bidirectional connectivity between peers and client reachability to the published endpoints.

## 6. Understanding Registry, Heartbeats, and Self-Preservation

Eureka Server stores the state of instances registered by clients. Clients periodically send heartbeats to renew their leases. If the server does not receive a heartbeat within the specified period, the instance may be considered expired and removed from the registry. Clients also periodically fetch the registry and can keep a local cache for lookups between sync intervals.

Under unstable network conditions, the server may receive fewer heartbeats than expected even while many applications are still running. The self-preservation mechanism limits mass instance eviction when the server suspects a widespread network issue. Therefore, the registry may temporarily hold stale information. An entry in the registry should not be treated as an instantaneous health metric or guaranteed proof that the instance is actively serving requests successfully.

In operations, monitor heartbeat logs, peer status, instance counts, and connection warnings. Only adjust lease or self-preservation settings after understanding network characteristics, heartbeat intervals, and the impact on failed-instance detection time. Disabling self-preservation just to make the dashboard clean up faster can cause the registry to mistakenly evict healthy instances during connectivity blips.

## 7. Securing Eureka Server

The registry contains internal addresses and routing information of services, so it must be protected as an infrastructure component. In production:

- Place Eureka Server on an internal network and restrict access sources using network policies, firewalls, or security groups.
- Enable authentication for the dashboard and registry APIs; issue dedicated credentials for clients authorized to register or look up services.
- Use HTTPS/TLS when traffic traverses untrusted networks and manage certificates appropriately.
- Do not expose the dashboard, registration APIs, or management endpoints directly to the public Internet.
- Store URLs, usernames, and passwords in environment variables or a secret store; never commit secrets to the repository.
- If the application uses Spring Security, configure CSRF appropriately for the Eureka APIs that clients need to call while still enforcing authentication and authorization.
- If enabling Spring Boot Actuator, expose only the strictly necessary endpoints and apply corresponding access controls.

The server configuration examples above are for local environments only. Before deploying, add authentication, TLS, and access restrictions according to infrastructure policies.

## 8. Common Errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Application starts but has no Eureka dashboard | Missing `@EnableEurekaServer` or missing server starter | Check dependencies and annotations on the main configuration class. |
| Cannot bind to port `8761` | Port is occupied by another process or `server.port` is configured differently | Check startup logs and the application's actual port. |
| Dashboard opens but registry is empty | No clients have registered yet or clients point to the wrong URL | Check `defaultZone` on the client side and registration logs. |
| Server peers do not see each other | Wrong DNS, firewall, port, or `defaultZone` | Check hostname resolution and connectivity between nodes from the actual runtime environment. |
| Stopped instance still appears | Lease expiration has not been processed yet or self-preservation is holding the registry | Check leases, server logs, and network connectivity; wait for the registry update cycle. |
| Client receives stale registry data | Registry sync or peer connectivity has an issue | Check peer status, registry fetch logs, and client connectivity. |
| Client is rejected when registering | Wrong credentials, TLS issue, or CSRF/security filter blocking requests | Check security configuration on the server and corresponding configuration on the client. |

## Key Takeaways

- Use `spring-cloud-starter-netflix-eureka-server` to add the server component.
- Place `@EnableEurekaServer` on the Spring Boot configuration class to activate Eureka Server.
- For a standalone server, set `register-with-eureka: false` and `fetch-registry: false`.
- For a multi-node cluster, configure peers via `eureka.client.service-url.defaultZone` and ensure hostnames and ports are reachable.
- An empty dashboard can still be a healthy running server if no clients have registered yet.
- Heartbeats, leases, and self-preservation affect when the registry reflects failed instances; observe behavior before tuning.
- Protect the dashboard and registry APIs with a private network, authentication, TLS, and proper secret management.
