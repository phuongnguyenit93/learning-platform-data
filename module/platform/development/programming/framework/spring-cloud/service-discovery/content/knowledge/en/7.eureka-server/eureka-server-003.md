# Setting Up Standalone Eureka with a Dedicated Profile

Eureka Server is the central registry where services register their instances and look up one another. When developing locally or running a demo environment, you can start a standalone Eureka Server on port `8761`. Spring Cloud Netflix configures Eureka Server itself as a Eureka Client by default; without adjustment, the server attempts to register with a peer and fetch the registry from a peer even when running a single node.

The right way to set up a standalone environment is to create a dedicated Spring profile, for example `eureka-server`, and place the standalone properties in `application-eureka-server.yml`. When this profile is active, the server neither registers itself into its own registry nor fetches the registry from another node. This configuration is suitable for local/development environments; production deployments require multiple peers for high availability.

## 1. Application Structure

A minimal Eureka Server application can be organized as follows:

```text
eureka-server/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/eurekaserver/
        │       └── EurekaServerApplication.java
        └── resources/
            ├── application.yml
            └── application-eureka-server.yml
```

`application.yml` contains shared application configuration. `application-eureka-server.yml` contains configuration that takes effect only when the `eureka-server` profile is active. This separation makes the standalone server configuration easy to identify and keeps it from mixing with configurations for other environments or roles.

## 2. Declaring the Eureka Server Dependency

Add the `spring-cloud-starter-netflix-eureka-server` starter to the project. Do not declare an explicit version for the starter when the Spring Cloud BOM is already imported.

Example dependency section in `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
```

Version management must use a Spring Cloud Release Train compatible with the project's Spring Boot version. For example, a Boot `4.2.0` environment can use Spring Cloud BOM `2026.0.0` according to the Spring Cloud compatibility matrix:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
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
```

These are illustrative version examples; when creating another project, check the compatibility matrix first and use the latest service release in the chosen train. If using Gradle, configure the Spring Boot Gradle plugin and import the same Spring Cloud BOM via dependency management so all Spring Cloud modules align consistently.

## 3. Enabling Eureka Server in the Application

For an application dedicated solely to running the registry, place `@EnableEurekaServer` on the main class:

```java
package com.example.eurekaserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
```

`@EnableEurekaServer` activates Spring Cloud Netflix's server configuration. Once the application starts successfully, Eureka provides its dashboard and HTTP APIs under the `/eureka/*` path.

If the same JAR also serves other roles and you only want to enable Eureka Server when the `eureka-server` profile is selected, do not place `@EnableEurekaServer` directly on the shared main class. Instead, place the annotation on a configuration class annotated with `@Profile`:

```java
package com.example.application;

import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("eureka-server")
@EnableEurekaServer
class EurekaServerRoleConfiguration {
}
```

This configuration class must reside within the application's component scan scope. When the profile is inactive, the configuration bearing `@EnableEurekaServer` will not be loaded. For a dedicated Eureka Server, the simpler approach remains enabling the annotation on the main class and using a dedicated profile for standalone configuration.

## 4. Common Configuration in application.yml

Set the application name in `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: eureka-server
```

Do not set `spring.profiles.active` in this file if you want the profile to be determined from the launch command or an environment variable. Activating from outside allows the same artifact to run with different configurations without repackaging.

## 5. Creating the Standalone Profile

Create `src/main/resources/application-eureka-server.yml` with the following content:

```yaml
server:
  port: 8761

eureka:
  instance:
    hostname: localhost
  client:
    register-with-eureka: false
    fetch-registry: false
    service-url:
      defaultZone: http://${eureka.instance.hostname}:${server.port}/eureka/
```

Meaning of each property:

| Property | Meaning |
|---|---|
| `server.port: 8761` | Starts the HTTP server on the default port commonly used for Eureka |
| `eureka.instance.hostname` | Hostname that Eureka Server identifies itself with and advertises |
| `eureka.client.register-with-eureka: false` | Does not register the server itself as a service instance in the registry |
| `eureka.client.fetch-registry: false` | Does not fetch the service list from a peer's registry |
| `eureka.client.service-url.defaultZone` | Default Eureka service URL address; standalone configuration points to the node itself |

The two properties `register-with-eureka` and `fetch-registry` are the key to standalone mode. Eureka Server also includes a client component; disabling these two behaviors prevents it from continuously looking for peers when running a single node.

Note: `defaultZone` is a key of a `Map<String, String>` and is therefore **case-sensitive**. Keep `defaultZone` as-is; do not write `default-zone`. Spring Cloud Netflix explicitly notes this exception in its configuration documentation.

In the local example, `localhost` works when server and clients run on the same machine. If Eureka runs in Docker, Kubernetes, or another host, `localhost` will resolve to the client's own container/host rather than Eureka Server. Replace `hostname` with a DNS name or address actually reachable by clients, such as `eureka-server` on the same Docker network.

## 6. Activating the eureka-server Profile

Spring Boot loads `application-{profile}.yml` when the corresponding profile is active. You can activate the profile via a command-line parameter:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=eureka-server
```

Or when running the built JAR:

```bash
java -jar target/eureka-server-0.0.1-SNAPSHOT.jar --spring.profiles.active=eureka-server
```

On Linux/macOS, you can use an environment variable:

```bash
SPRING_PROFILES_ACTIVE=eureka-server ./mvnw spring-boot:run
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "eureka-server"
.\mvnw.cmd spring-boot:run
```

At startup, Spring Boot logs should show that the `eureka-server` profile is active. If no profile is active, Spring Boot uses the `default` profile, and `application-eureka-server.yml` will not be applied.

Do not place `spring.profiles.active` inside `application-eureka-server.yml`. Spring Boot only allows declaring `spring.profiles.active` and `spring.profiles.default` in non-profile-specific configuration documents. A profile-specific file only provides properties for an already activated profile.

## 7. Verifying Eureka Server After Startup

Open the dashboard in a browser:

```text
http://localhost:8761/
```

Check the registry API:

```bash
curl -H "Accept: application/json" http://localhost:8761/eureka/apps
```

In a newly started standalone environment, the instance list may be empty. This is normal if no Eureka Client has registered yet. Eureka Server itself does not appear as a service instance because `register-with-eureka` is disabled.

You can also verify by inspecting the logs:

- The application started successfully and is listening on port `8761`.
- The active profile is `eureka-server`.
- There are no continuous log loops about failing to register or fetch the registry from a peer.
- The dashboard is accessible from the development machine.

## 8. Connecting a Test Eureka Client

A client application needs the `spring-cloud-starter-netflix-eureka-client` starter, a service name, and the Eureka Server address:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

The client does not use the `eureka-server` profile; the client's profile may be `local` or `dev` depending on how environments are organized. When the client starts, it sends its instance info and heartbeats to Eureka. After successful registration, the server dashboard will display `INVENTORY-SERVICE` along with its corresponding instances.

For clients running in containers or on other hosts, the URL must use a DNS name or IP routable to Eureka Server, such as `http://eureka-server:8761/eureka/`. Do not copy the `localhost` URL from a local example into a distributed deployment configuration.

## 9. Separating Standalone and Peer-Aware Configurations

Standalone mode is suitable for learning, demos, or single-machine development. A single Eureka Server does not provide high availability: the registry stores data in memory, and a server restart can lose current registration state until clients reconnect and re-register.

In production, Spring Cloud Netflix recommends running multiple Eureka Servers in a peer-aware model. Nodes register and synchronize registries with peers; they require resolvable and reachable peer addresses. A peer-aware configuration does not use the two standalone properties `register-with-eureka: false` and `fetch-registry: false`.

An example profile configuration for two peers can be organized into separate files:

`application-eureka-peer-a.yml`:

```yaml
server:
  port: 8761
eureka:
  instance:
    hostname: eureka-a.internal
  client:
    service-url:
      defaultZone: http://eureka-b.internal:8761/eureka/
```

`application-eureka-peer-b.yml`:

```yaml
server:
  port: 8761
eureka:
  instance:
    hostname: eureka-b.internal
  client:
    service-url:
      defaultZone: http://eureka-a.internal:8761/eureka/
```

This example only illustrates peer awareness. In a real deployment, each peer needs a hostname, port, TLS, firewall rules, and service URL suited to the infrastructure. Do not use `localhost` for a peer on another host; likewise, do not run two peers on the same host/port as a real HA configuration.

## 10. Security and Operational Notes

- Only expose the Eureka port to services or management networks that need access to the registry. The dashboard and `/eureka/**` APIs should not be exposed publicly.
- If adding Spring Security, configure authentication for the dashboard and clients. Eureka clients typically send registration/heartbeat requests over HTTP; when default CSRF protection is enabled, configure appropriate CSRF exemptions for `/eureka/**` so registry operations are not blocked. Never disable security entirely just to allow clients to register.
- Never write usernames/passwords directly into committed configuration files. Use environment variables or the platform's secret store.
- Monitor instance counts, heartbeat status, registry response times, eviction logs, and self-preservation status.
- Consider graceful shutdown so clients stop receiving traffic and deregister cleanly before the process exits.
- Ensure system clocks are synchronized and configure client-registered hostnames/IPs so they are reachable from consumers.

## 11. Common Errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Dashboard cannot be reached | Application is not running, wrong port, or profile is not active | Check startup logs, verify `server.port` and the `eureka-server` profile |
| Logs report inability to connect to peer | Standalone mode has not disabled client-side registration/fetch or wrong service URL | Check `register-with-eureka: false`, `fetch-registry: false`, and the loaded profile |
| Client cannot register | Client uses wrong URL, DNS, port, firewall, or Eureka Server is not ready | Check `defaultZone`, connectivity from the client's actual runtime environment, and logs on both sides |
| Client registers with localhost but other consumers cannot call it | Instance advertises a hostname/IP unreachable from consumers | Configure `eureka.instance.hostname` or `prefer-ip-address` and verify network routing |
| `defaultZone` is not recognized | Incorrect casing of the map key | Use exact camelCase `defaultZone` |
| Standalone configuration has no effect | Profile not activated or wrong filename | Filename must be `application-eureka-server.yml`; active profile must be exactly `eureka-server` |
| Eureka Server remains enabled under other profiles | `@EnableEurekaServer` is placed on a shared main class | If the server should only run per profile, move the annotation to a `@Configuration` class with `@Profile("eureka-server")` |

## 12. Completion Checklist

- [ ] Added `spring-cloud-starter-netflix-eureka-server` and used a compatible Spring Cloud BOM.
- [ ] Enabled `@EnableEurekaServer` in the appropriate application scope.
- [ ] Created `application-eureka-server.yml` with the exact profile name.
- [ ] Set the server port, hostname, and service URL appropriate for the environment.
- [ ] Disabled `register-with-eureka` and `fetch-registry` in standalone mode.
- [ ] Kept the `defaultZone` key in exact camelCase.
- [ ] Activated the profile via command line or environment variable.
- [ ] Startup logs confirm the correct profile and no peer connection retry loops.
- [ ] Dashboard and `/eureka/apps` are reachable from allowed networks.
- [ ] A test Eureka Client registered and appeared on the dashboard.
- [ ] Distinguished local standalone from peer-aware production and planned registry protection.

## References

- [Spring Cloud Netflix — Eureka Server, Standalone Mode, and Peer Awareness](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot 4.2 — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot 4.2 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Project — Release Trains and Version Compatibility](https://spring.io/projects/spring-cloud/)
