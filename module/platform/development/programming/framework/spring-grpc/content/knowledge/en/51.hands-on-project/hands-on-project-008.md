# Configuring a Spring Client Channel

In this project, you will build a gRPC client inside a Spring Boot application and manage the `ManagedChannel` through the Spring container. The client will read the target address and limits from configuration, select transport security per profile, reuse the channel across RPC calls, and attach a deadline to every call.

The goal is to create a configuration ready for real applications: the channel has a clear lifecycle, stubs are injected into services, local environments can run plaintext while deployed environments use TLS, and connection errors can be classified operationally. The examples use the `grpc-java` API integrated directly with Spring Boot; if your project has standardized on a Spring gRPC starter, you can use its channel factory mechanism instead, but never mix two lifecycle managers for the same channel.

## Expected Outcomes

Upon completion, the application should satisfy the following criteria:

- Read target, plaintext/TLS mode, and message limits from `application.yml`.
- Create a shared `ManagedChannel` scoped to the Spring application context lifecycle.
- Create generated stubs from the channel and inject them into client services.
- Set a deadline on every RPC instead of waiting indefinitely.
- Shut down the channel when the Spring context stops.
- Switch endpoints and security modes by profile without modifying business code.
- Include tests for successful calls, error statuses, and channel lifecycle.

## 1. Project Setup

The examples assume Java 17 or higher and Spring Boot 3.x. Use `grpc-java`/protobuf versions compatible with the Java, Spring Boot, and toolchain versions managed by your project; align `grpc-java` modules via a BOM rather than declaring separate versions on individual dependencies.

Core runtime dependencies:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-bom</artifactId>
            <version>${grpc.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-netty-shaded</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-protobuf</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-stub</artifactId>
    </dependency>
</dependencies>
```

`grpc.version` must be declared in your project's properties or shared dependency management according to your chosen version. If your project does not yet have a protobuf code generation step, you can configure the Maven plugin as follows; lock the version properties to the toolchain verified for compatibility in your project:

```xml
<properties>
    <grpc.version>REPLACE_WITH_COMPATIBLE_VERSION</grpc.version>
    <protobuf.version>REPLACE_WITH_COMPATIBLE_VERSION</protobuf.version>
    <os.maven.plugin.version>REPLACE_WITH_COMPATIBLE_VERSION</os.maven.plugin.version>
    <protobuf.maven.plugin.version>REPLACE_WITH_COMPATIBLE_VERSION</protobuf.maven.plugin.version>
</properties>

<build>
    <extensions>
        <extension>
            <groupId>kr.motd.maven</groupId>
            <artifactId>os-maven-plugin</artifactId>
            <version>${os.maven.plugin.version}</version>
        </extension>
    </extensions>
    <plugins>
        <plugin>
            <groupId>org.xolstice.maven.plugins</groupId>
            <artifactId>protobuf-maven-plugin</artifactId>
            <version>${protobuf.maven.plugin.version}</version>
            <configuration>
                <protocArtifact>com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}</protocArtifact>
                <pluginId>grpc-java</pluginId>
                <pluginArtifact>io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}</pluginArtifact>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>compile</goal>
                        <goal>compile-custom</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

If your project already has a code generation pipeline, keep using it and verify that generated code matches the runtime.

Create the minimal directory structure:

```text
src/main/
├── proto/
│   └── catalog.proto
├── java/com/example/catalog/
│   ├── CatalogClientApplication.java
│   ├── config/
│   │   ├── CatalogGrpcClientProperties.java
│   │   └── CatalogGrpcClientConfiguration.java
│   └── client/
│       └── CatalogClient.java
└── resources/
    ├── application.yml
    └── application-local.yml
```

The Spring Boot entry-point class simply enables component scanning for the package containing the client and configuration:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogClientApplication.class, args);
    }
}
```

## 2. Declaring the Protobuf Contract

Create `src/main/proto/catalog.proto`:

```protobuf
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "com.example.catalog.grpc";
option java_outer_classname = "CatalogProto";

service Catalog {
  rpc GetCatalog (CatalogRequest) returns (CatalogReply);
}

message CatalogRequest {
  string catalog_id = 1;
}

message CatalogReply {
  string catalog_id = 1;
  string display_name = 2;
}
```

Run the build's code generation step to create `CatalogGrpc`, `CatalogRequest`, and `CatalogReply` in package `com.example.catalog.grpc`. The client depends solely on classes generated from the contract; never hand-write message classes to substitute for protobuf types.

## 3. Binding Configuration to Spring Properties

Create `CatalogGrpcClientProperties.java`:

```java
package com.example.catalog.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.grpc.client")
public class CatalogGrpcClientProperties {

    @NotBlank
    private String target;

    private boolean usePlaintext;

    @Min(1024)
    private int maxInboundMessageSize = 4 * 1024 * 1024;

    public String getTarget() {
        return target;
    }

    public void setTarget(String target) {
        this.target = target;
    }

    public boolean isUsePlaintext() {
        return usePlaintext;
    }

    public void setUsePlaintext(boolean usePlaintext) {
        this.usePlaintext = usePlaintext;
    }

    public int getMaxInboundMessageSize() {
        return maxInboundMessageSize;
    }

    public void setMaxInboundMessageSize(int maxInboundMessageSize) {
        this.maxInboundMessageSize = maxInboundMessageSize;
    }
}
```

`@ConfigurationProperties` groups client-related settings into a typed, validatable object. `@NotBlank` ensures `target` is always provided; `@Min` prevents configuring an overly small or invalid message size limit per the example's convention. `usePlaintext` defaults to `false`, so the default configuration requires transport security.

## 4. Configuring the Channel as a Spring Bean

Create `CatalogGrpcClientConfiguration.java`:

```java
package com.example.catalog.config;

import com.example.catalog.grpc.CatalogGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogGrpcClientProperties.class)
public class CatalogGrpcClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    public ManagedChannel catalogChannel(CatalogGrpcClientProperties properties) {
        ManagedChannelBuilder<?> builder = ManagedChannelBuilder
            .forTarget(properties.getTarget())
            .maxInboundMessageSize(properties.getMaxInboundMessageSize());

        if (properties.isUsePlaintext()) {
            builder.usePlaintext();
        } else {
            builder.useTransportSecurity();
        }

        return builder.build();
    }

    @Bean
    public CatalogGrpc.CatalogBlockingStub catalogBlockingStub(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        return CatalogGrpc.newBlockingStub(channel);
    }
}
```

Spring creates the channel once and reuses it across RPCs. `destroyMethod = "shutdown"` instructs Spring to initiate channel shutdown when the application context is closed. `shutdown()` stops accepting new calls and gives in-flight RPCs a chance to finish; if your application needs a strictly bounded drain period, add an `awaitTermination` policy to your shutdown lifecycle.

`maxInboundMessageSize` caps individual inbound messages received by the client, typically server responses. It is not a cap on total stream bytes and does not replace application-layer buffer bounds.

## 5. Configuring Endpoints by Environment

In `application.yml`, declare the default target and keep TLS as the default choice:

```yaml
spring:
  application:
    name: catalog-client

catalog:
  grpc:
    client:
      target: "${CATALOG_GRPC_TARGET:dns:///catalog.internal:8443}"
      use-plaintext: false
      max-inbound-message-size: 4194304
```

In `application-local.yml`, enable plaintext only for the local server:

```yaml
catalog:
  grpc:
    client:
      target: dns:///localhost:9090
      use-plaintext: true
```

Activate the local profile during local development, e.g., via `SPRING_PROFILES_ACTIVE=local`. Staging/production environments should set `CATALOG_GRPC_TARGET` to the real endpoint and keep `use-plaintext: false`. Never enable plaintext in production or on networks carrying sensitive data.

With TLS, the server certificate must be trusted by the client and the certificate's hostname must match the connection target. If your infrastructure uses a private CA or mutual TLS, configure trust certificates and client certificates using the appropriate transport builder, such as `NettyChannelBuilder` with `GrpcSslContexts`; never disable certificate verification to bypass handshake errors.

## 6. Injecting the Stub and Calling RPCs with a Deadline

Create `CatalogClient.java`:

```java
package com.example.catalog.client;

import com.example.catalog.grpc.CatalogGrpc;
import com.example.catalog.grpc.CatalogReply;
import com.example.catalog.grpc.CatalogRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class CatalogClient {

    private final CatalogGrpc.CatalogBlockingStub stub;

    public CatalogClient(CatalogGrpc.CatalogBlockingStub stub) {
        this.stub = stub;
    }

    public CatalogReply getCatalog(String catalogId) {
        CatalogRequest request = CatalogRequest.newBuilder()
            .setCatalogId(catalogId)
            .build();

        try {
            return stub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getCatalog(request);
        } catch (StatusRuntimeException exception) {
            Status.Code code = Status.fromThrowable(exception).getCode();
            // Record status code and request/trace ID; do not log tokens or sensitive payloads.
            // Translate to a domain exception at the appropriate boundary if needed.
            throw exception;
        }
    }
}
```

`grpc-java` stubs are immutable; `withDeadlineAfter` creates a derived stub with fresh `CallOptions` for that call. Thus you can share a single injected stub while applying different deadlines per operation. The two-second deadline is illustrative: calculate deadlines from your end-to-end request latency budget and expected server processing time.

`Status.fromThrowable` classifies statuses cleanly without parsing message strings. For example, `UNAVAILABLE` may indicate a transient connection failure, `DEADLINE_EXCEEDED` signals the time budget expired, `UNAUTHENTICATED`/`PERMISSION_DENIED` relate to authentication or authorization, and `RESOURCE_EXHAUSTED` may indicate message size or quota limits. Retry only when the error is recoverable and the operation is safe to repeat; use backoff, jitter, and a bounded attempt count.

## 7. Adding an Interceptor When Shared Metadata Is Needed

If every RPC requires a correlation ID or trace metadata, register a `ClientInterceptor` on the channel builder before calling `build()`:

```java
ManagedChannelBuilder<?> builder = ManagedChannelBuilder
    .forTarget(properties.getTarget())
    .intercept(correlationIdClientInterceptor);
```

Interceptors on the shared channel should only attach metadata that is genuinely shared. Per-user auth tokens should be supplied via call credentials or request security context, avoiding baking a single user's token into a shared channel. Never log authorization values. If you manage multiple client channels, use distinct qualifiers for each channel and stub to prevent wiring the wrong target.

## 8. Testing the Configuration

Organize tests into three layers:

| Test Type | How to Run | What It Verifies |
|---|---|---|
| Binding/configuration test | Boot Spring context with specific target and transport mode | Properties bind, validation works, and the channel bean is created |
| In-process gRPC test | Use `InProcessServerBuilder` and `InProcessChannelBuilder` with a fake service | Stub invokes the right method, passes requests, and receives responses without real sockets |
| Transport integration test | Run a real server with TLS or plaintext in a test environment | DNS/target resolution, certificates, handshakes, timeouts, and network configuration work |

For in-process tests, add the `grpc-inprocess` dependency matching your chosen `grpc-java` version in test scope. Register a fake `Catalog` service implementation returning a fixed `CatalogReply`. When testing deadlines, make the fake service respond slower than the deadline and assert the client receives `DEADLINE_EXCEEDED`. When testing errors, have the service return intentional statuses and assert the client classifies the codes properly.

Recommended test checks:

1. Application context starts successfully with a valid target.
2. Blank target or invalid configuration fails startup early.
3. Multiple calls reuse the same channel bean without creating a new channel per request.
4. Successful RPC returns the expected protobuf data.
5. Slow RPC exceeding the deadline returns `DEADLINE_EXCEEDED`.
6. Unavailable server returns the appropriate status and logs include trace/request IDs for diagnosis.
7. Closing the Spring context shuts down the channel.
8. The `local` profile enables plaintext; the production profile preserves transport security.

## 9. Running and Verifying the Project

1. Confirm the protobuf generation step creates `CatalogGrpc` and Java message classes.
2. Start a gRPC server implementing `Catalog/GetCatalog` at the configured target.
3. Run Spring Boot with the `local` profile or point to a staging endpoint with a valid certificate.
4. Call `CatalogClient.getCatalog("books")` from a controller, command-line runner, or integration test.
5. Verify responses, deadlines, statuses when the server is stopped, and logs on connection failures.
6. Stop the Spring application and verify the channel shuts down.

If no server is available yet, use an in-process test server to complete client testing first. Never enable plaintext in a real deployment environment just to make connections pass.

## 10. Troubleshooting Common Errors

| Symptom | Common Cause | How to Check |
|---|---|---|
| `UNAVAILABLE` when starting an RPC | Wrong target/port, DNS fails to resolve, or server not listening | Check target, DNS, port, and server status |
| TLS handshake fails | Untrusted CA, expired certificate, or hostname mismatch | Check trust chain, SAN, certificate validity, and mTLS config |
| `DEADLINE_EXCEEDED` | Deadline too short, slow server, or blocked downstream dependency | Compare per-hop latency against deadline budget |
| `RESOURCE_EXHAUSTED` when receiving response | Response exceeds client inbound limit or quota applied | Measure message size; check receiver limit and quotas |
| Every request opens a new connection | Channel constructed inside the request-handling method | Make the channel a Spring singleton bean and inject the stub |
| Application hangs on shutdown | Active RPCs/streams or unbounded shutdown wait | Stop accepting new requests, set deadlines, and drain RPCs before exit |

## Acceptance Criteria

- [ ] Generated stubs are produced from `catalog.proto` and compiled against a compatible `grpc-java` runtime.
- [ ] `CatalogGrpcClientProperties` binds and validates configuration.
- [ ] `ManagedChannel` is created as a Spring bean, reused, and shut down with the context lifecycle.
- [ ] Blocking stub is injected into `CatalogClient`.
- [ ] Every RPC sets a deadline and statuses are classified using `Status.fromThrowable`.
- [ ] Local profile uses plaintext; default/production configuration uses TLS.
- [ ] Tests cover success, error statuses, deadlines, and channel shutdown.

Once completed, changing endpoints, message limits, or transport security only requires updating environment configuration. The client service stays focused on the RPC contract and result handling, while the Spring container owns creating, sharing, and shutting down the channel throughout the application lifecycle.
