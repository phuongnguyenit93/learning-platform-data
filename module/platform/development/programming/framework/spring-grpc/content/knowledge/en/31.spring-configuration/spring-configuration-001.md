# Configuring the gRPC Server with Properties in Spring gRPC

In **SPRING_GRPC**, the server is initialized and configured through Spring Boot auto-configuration. Properties determine whether the server is enabled, which address/port it listens on, how TLS is used, and how capabilities such as reflection, health checks, or servlet transport are integrated.

Proper configuration helps the application run consistently across development machines, test environments, and production. This lesson focuses on the `spring.grpc.server.*` prefix, how to set values in YAML/properties, environment-specific overrides, distinguishing HTTP ports from gRPC ports, and verifying configuration with integration tests.

## 1. Which parts of the server do properties control?

Spring Boot uses externalized configuration to bind values from `application.yml`, `application.properties`, environment variables, command-line arguments, and other property sources into auto-configuration.

With Spring gRPC, server settings live under the prefix:

```text
spring.grpc.server
```

Some commonly used properties:

| Property | Meaning |
| --- | --- |
| `spring.grpc.server.enabled` | Enables/disables server auto-configuration |
| `spring.grpc.server.port` | Port of the native gRPC server; a value of `0` requests a dynamic port |
| `spring.grpc.server.address` | Network address the server binds to; when set, it may take precedence over host/port configuration |
| `spring.grpc.server.ssl.bundle` | Name of the SSL bundle used for TLS |
| `spring.grpc.server.ssl.client-auth` | Client certificate authentication policy |
| `spring.grpc.server.reflection.enabled` | Enables/disables gRPC reflection when the supporting library is present |
| `spring.grpc.server.health.enabled` | Controls auto-configuration of the gRPC Health service |
| `spring.grpc.server.servlet.enabled` | Selects the servlet-based server in a web application when the environment supports it |

The exact list and applicability conditions depend on the Spring Boot/Spring gRPC version and the transport on the classpath. Check the configuration metadata of the exact starter your project uses; do not assume every version has the same properties.

Properties configure the server factory and transport. They do not replace the `.proto` contract, nor do they implement RPC business logic automatically. The application still needs a `BindableService` bean, typically a subclass extending the generated `*ImplBase`.

## 2. Configuring the port with application.yml

Example native gRPC server configuration:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: 9090
```

The application will start the gRPC server on port `9090` if a suitable native server factory is in use. For container environments, the port can be taken from an environment variable:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: ${GRPC_PORT:9090}
```

If `GRPC_PORT` has a value, Spring Boot uses that value; if the variable is not set, the default value in the placeholder is `9090`.

The same configuration in `application.properties`:

```properties
spring.grpc.server.enabled=true
spring.grpc.server.port=9090
```

Both YAML and properties forms are equivalent in terms of binding. Choose one format consistently across the project for easier review and operation.

### 2.1. Choosing the bind address

If you need to specify the network address explicitly, you can configure `spring.grpc.server.address` in the address format supported by your starter version:

```yaml
spring:
  grpc:
    server:
      address: "0.0.0.0:9090"
```

Binding to `0.0.0.0` allows the server to accept connections across the container/host network interfaces. In environments where only local access is permitted, consider binding to loopback or a specific interface address.

When `address` is set and takes precedence in the version being used, do not also expect `port` to override the port part of `address`. Choose one clear configuration source and verify the actual address in the startup log.

## 3. Distinguishing the HTTP port from the gRPC port

A Spring Boot application can run an HTTP server for REST, Actuator, or admin interfaces while simultaneously running a native gRPC server on a different port.

Example:

```yaml
server:
  port: 8080

spring:
  grpc:
    server:
      port: 9090
```

In a native server configuration:

- `server.port` is the Spring Boot web server port.
- `spring.grpc.server.port` is the gRPC listener port.
- REST/Actuator can go through the HTTP server, while gRPC clients connect to the gRPC listener.

These are two independent listeners. Opening the HTTP port in a Kubernetes Service or firewall does not automatically open the gRPC port.

**Important exception:** if the application runs gRPC through a servlet container, the servlet container manages the network listener and HTTP/2. In this mode, some native server properties such as `spring.grpc.server.port` may not be used; the web port `server.port` and the servlet container's HTTP/2 configuration determine the endpoint instead. Identify the transport mode before troubleshooting issues like "changed the port, but the server is still listening on the old port".

## 4. Registering a service bean so the server has endpoints

Properties can enable the listener, but the server only exposes business RPCs when `BindableService` beans are registered. For example, with a `StockService` generated from `.proto`:

```java
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

@Service
public class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        StockReply reply = StockReply.newBuilder()
                .setSku(request.getSku())
                .setAvailable(17)
                .build();

        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Component scanning detects this bean, and Spring gRPC can bind the `BindableService` to the configured server factory. The method name and parameter types must match the generated base class from the actual contract.

If the server opens the port but the client receives `UNIMPLEMENTED`, check whether the service bean is in the application context and whether the method is overridden properly. Simply changing `port` or `address` will not fix an RPC registration error.

## 5. Overriding configuration by environment

Do not hardcode production ports in source code. Use profiles and environment variables so the same artifact can run across multiple environments.

Example `application.yml`:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: 9090
```

Example `application-prod.yml`:

```yaml
spring:
  grpc:
    server:
      address: "0.0.0.0:9090"
```

Run with the production profile:

```bash
java -jar stock-service.jar --spring.profiles.active=prod
```

Or override directly with an environment variable:

```bash
SPRING_GRPC_SERVER_PORT=9191
```

Command-line arguments can also override it:

```bash
java -jar stock-service.jar --spring.grpc.server.port=9191
```

Spring Boot applies a precedence order across property sources. When the effective value is not what you expect, check active profiles, container environment variables, command-line arguments, and configuration loaded from ConfigMaps/secrets. Do not just read `application.yml` and assume that is the final value.

With Kubernetes, you can set `SPRING_GRPC_SERVER_PORT` in the Deployment and declare the matching `containerPort`/Service `targetPort`. `containerPort` is only Pod metadata; the Service/NetworkPolicy still needs to point to the right port and allow traffic.

## 6. Configuring TLS with an SSL bundle

In production environments, gRPC typically requires TLS to protect data in transit. Spring Boot allows declaring an SSL bundle and referencing that bundle from the gRPC server.

Illustrative example with a PKCS12 keystore:

```yaml
spring:
  ssl:
    bundle:
      jks:
        grpc-server:
          keystore:
            location: "classpath:tls/server.p12"
            password: ${GRPC_KEYSTORE_PASSWORD}
            type: PKCS12

  grpc:
    server:
      port: 9090
      ssl:
        bundle: grpc-server
        client-auth: none
```

`grpc-server` is the application-defined bundle name; the `spring.grpc.server.ssl.bundle` property references this exact name. The password comes from a secret or environment variable—never commit real values to the repository.

If mutual TLS (mTLS) is needed, configure `client-auth` according to a supported policy, such as `require`, and declare appropriate trust material so the server can verify client certificates. Setting `client-auth` alone without an appropriate truststore/CA will cause the handshake to fail.

Points to check:

- The certificate is valid (not expired), and the SAN matches the hostname used by the client.
- The server has the correct private key and certificate chain.
- The client trusts the server's CA.
- If mTLS is enabled, the server trusts the CA that issued the client certificate.
- Plaintext test configuration is not carried over to production.

If the application runs over servlet transport, TLS is usually configured on the servlet container/web server. In that case, the native gRPC server's SSL bundle might not control the servlet listener.

## 7. Reflection and Health service

gRPC Reflection allows tools such as `grpcurl` to discover service descriptors on the server. gRPC Health provides standard RPCs to probe server/service status.

Example of disabling reflection:

```yaml
spring:
  grpc:
    server:
      reflection:
        enabled: false
```

The reflection service typically requires the `grpc-services` library on the classpath for auto-configuration to register it. Without this dependency, changing the property cannot create the implementation on its own.

The health service also depends on the starter's integration capabilities and the corresponding dependency. When using health checks for Kubernetes, distinguish between:

- **Liveness:** whether the process is still alive to keep running.
- **Readiness:** whether the service is ready to receive traffic.
- **gRPC Health:** the health status published over the gRPC protocol.

Do not configure readiness to always report `SERVING` if the application has not yet connected to the database or essential dependencies. When you need to control service status, update the health manager according to the actual lifecycle and business state.

## 8. Shutdown timeout and handling in-flight requests

When the application stops or undergoes a rolling update, the gRPC server needs time to finish in-flight RPCs. Spring gRPC has properties for graceful shutdown; the exact property names and duration structure should be confirmed against your starter version.

When configuring the grace period:

- Choose a duration long enough for normal RPCs to complete.
- Clients still need deadlines so requests do not hang indefinitely.
- The application needs to handle cancellation and stop accepting new work during shutdown.
- Readiness should transition to a state that stops receiving traffic before the process terminates.
- Do not choose an overly long duration if the deployment platform has a shorter termination grace period.

The wait times of the platform, Spring application shutdown, and the gRPC server must be compatible. If Kubernetes force-kills the process before gRPC completes graceful shutdown, in-flight requests can still be interrupted.

## 9. Testing server configuration with a dynamic port

In integration tests, use port `0` so the operating system picks an available port. This prevents conflicts when multiple tests run concurrently:

```yaml
spring:
  grpc:
    server:
      port: 0
```

In Spring Boot versions that provide `@LocalGrpcServerPort`, you can obtain the bound port in a test:

```java
@SpringBootTest(properties = "spring.grpc.server.port=0")
class StockGrpcServerTest {

    @LocalGrpcServerPort
    int grpcPort;

    @Test
    void serverBindsToAnAvailablePort() {
        assertTrue(grpcPort > 0);
    }
}
```

If using the annotation above, import it from the test support package corresponding to your project's Spring Boot/Spring gRPC version. For versions that do not yet provide this annotation, use the appropriate test server API or factory to retrieve the actual listener address.

To test RPCs over a real network connection, create a channel pointing to `localhost` and `grpcPort`, invoke the generated stub, and close the channel in `finally` or `@AfterEach`. Only use `usePlaintext()` in non-TLS server tests; for TLS tests, configure the corresponding trust certificate.

## 10. When are properties enough, and when is Java customization needed?

Use properties for deployment values that commonly vary across environments: enable/disable flags, port, address, SSL bundle, and server features exposed by the starter.

When you need to fine-tune transport or behavior without a corresponding property, Spring gRPC provides extension points such as `ServerBuilderCustomizer` for the server builder. For example, a requirement to limit inbound message size may need a customizer depending on the transport and API version.

Selection rules:

- If a documented property exists, prefer the property for clear environment-driven configuration.
- If conditional logic or advanced builder APIs are needed, use bean customization.
- Do not invent an arbitrary `spring.grpc.server.*` key and expect auto-configuration to bind it.
- If you create custom `@ConfigurationProperties` for your application, use your application's own prefix to avoid confusion with properties owned by the starter.

## 11. Diagnosing common configuration errors

| Symptom | Check |
| --- | --- |
| Client cannot connect | Actual port/address, bind interface, firewall, Kubernetes Service, and transport |
| Changing `server.port` does not change gRPC port | Native server uses `spring.grpc.server.port`; check servlet mode |
| Server opens port, but RPC returns `UNIMPLEMENTED` | `BindableService` bean, component scan, method override, and service name |
| Configured port has no effect | Active profile, env vars, command-line args, and `spring.grpc.server.address` taking precedence |
| TLS handshake fails | SSL bundle, private key, trust chain, hostname, and client-auth |
| Reflection does not work | `grpc-services` dependency and `spring.grpc.server.reflection.enabled` |
| Tests occasionally occupy the same port | Use port `0` and retrieve the actual bound port |
| Shutdown interrupts in-flight requests | Grace period, client deadline, and platform termination grace period |

During investigation, note the active property sources and startup logs. If Spring Boot Actuator is available, the `configprops` endpoint can help inspect bound configuration; only enable and secure this endpoint according to security policy because it can expose configuration details.

## 12. Practice exercises

1. Configure `spring.grpc.server.port=9090` in YAML and verify that the gRPC listener starts.
2. Run the HTTP server on `8080` and the gRPC server on `9090`; verify that both ports serve the expected protocols.
3. Override the port using `SPRING_GRPC_SERVER_PORT` and command-line arguments; verify the effective value.
4. Run with the `prod` profile and configure a bind address suitable for a container environment.
5. Register a bean extending the generated `StockServiceGrpc.StockServiceImplBase`; call an RPC to verify the service is bound.
6. Use port `0` in an integration test and obtain the actual port using your version's test support.
7. Configure an SSL bundle for the native server; verify the handshake with a trusted client.
8. Enable reflection when `grpc-services` is present, then disable it via property and verify that the behavior changes.
9. Test graceful shutdown while an RPC is running; compare the grace period against the client deadline and termination grace period.
10. Create a configuration matrix for local, test, and production, clearly noting which properties are overridden from the environment.

### Key Takeaways

**Properties configure how the gRPC server is initialized and operated in each environment.** Use `spring.grpc.server.*` for the native server, distinguish it from the web server's `server.port`, manage values via profiles/environment, and verify the effective values. TLS, reflection, health, and shutdown only work when supported by the transport, dependencies, and starter version. After configuring, verify the listener, service beans, and an actual RPC with an integration test.

## References

- [Spring Boot Reference — gRPC](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring gRPC Reference — Server](https://docs.spring.io/spring-grpc/reference/server.html)
