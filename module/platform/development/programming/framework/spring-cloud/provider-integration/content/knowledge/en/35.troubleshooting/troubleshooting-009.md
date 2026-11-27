# SDK, classpath, Netty, or blocking/reactive model compatibility errors

A Spring Boot application integrating multiple cloud providers may compile successfully yet fail at startup, or fail only when calling a specific service. Common symptoms include `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, `AbstractMethodError`, `ALPN is not configured properly`, Netty channel creation failures, `UnsatisfiedLinkError`, sudden timeout spikes, or WebFlux event-loop blocking.

These errors typically fall into one of four categories:

1. **Platform version incompatibility:** Spring Boot, Spring Framework, the Spring Cloud release train, and provider starters come from mutually unsupported lines.
2. **Dependency/classpath conflicts:** multiple versions of Netty, Reactor, gRPC, protobuf, Guava, AWS SDK, or Jakarta/Java EE APIs appear together.
3. **Mismatched HTTP transport:** sync/async clients use the wrong transport, lack an implementation, or use incompatible connection pools or native libraries.
4. **Wrong I/O model:** calling blocking libraries on the WebFlux event loop, using reactive publishers without returning/composing them properly, or spawning excessive threads and connections.

Do not fix errors by upgrading every dependency to the latest version or adding an arbitrary Netty version. Identify which dependency wins at runtime, which library pulled that version in, and which thread model requests run on. Only then adjust BOMs, remove dependency overrides, or switch to the appropriate client.

This article shows how to read compatibility matrices, analyze dependency trees with Maven/Gradle, resolve conflicts among AWS SDK, Azure SDK, Google Cloud libraries, and Netty, distinguish blocking vs. reactive APIs, and verify via builds and integration tests.

## 1. Classifying symptoms by failure layer

| Symptom | Likely failing layer | Clues to look for |
| --- | --- | --- |
| App fails to start, missing class | Classpath or starter | `ClassNotFoundException`, `NoClassDefFoundError`, unmatched auto-configuration conditions |
| Runs, but fails when invoking a method | Binary incompatibility | `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` |
| `ClassCastException` even though two objects share the same class name | Classloader or duplicate classes | Class loaded from two different JARs/classloaders |
| `ALPN is not configured properly` | gRPC/Netty/TLS runtime | Netty version conflict, missing ALPN/native support, or incompatible platform |
| `UnsatisfiedLinkError` when initializing transport | Native Netty/CRT | Wrong OS/CPU classifier, native library failed to load |
| WebFlux responds slowly, all requests hang | Blocking on event loop | Thread dump shows `block()`, JDBC, or sync SDK calls on `reactor-http-nio` |
| `PoolAcquireTimeoutException` or growing pending acquires | Connection pool | Insufficient connections, requests holding connections too long, unconsumed/unclosed bodies |
| AWS async client lacks HTTP implementation | HTTP client dependency | `netty-nio-client`/CRT excluded or missing async transport |
| Azure SDK fails to build `HttpClient` | Azure HTTP transport | Excluded `azure-core-http-netty` without adding OkHttp/JDK `HttpClient` |
| Google Cloud client throws linkage errors at runtime | gRPC/Guava/protobuf/Netty | Version differs from Google Cloud Libraries BOM or runtime adds external JARs |

**First rule:** inspect the deepest exception (`Caused by`) and the missing class/method name. The outermost exception usually describes only where the failure surfaced, whereas the root exception points to the dependency or transport to investigate.

## 2. Lock down the compatibility matrix before editing dependencies

### 2.1. Spring Boot and Spring Cloud release trains

Each Spring Cloud release train is published for compatibility with a specific Spring Boot generation. Never pick two versions simply because both are newest on Maven Central.

The table below lists the primary pairs published in Spring's compatibility mapping at the time of writing:

| Spring Boot | Corresponding Spring Cloud release train |
| --- | --- |
| 4.0.x / 4.1.x | 2025.1.x (Oakwood; Boot 4.1 support starting from the patch release noted in the mapping) |
| 3.5.x | 2025.0.x (Northfields) |
| 3.4.x | 2024.0.x (Moorgate) |
| 3.2.x / 3.3.x | 2023.0.x (Leyton) |
| 3.0.x / 3.1.x | 2022.0.x (Kilburn) |
| 2.6.x / 2.7.x | 2021.0.x (Jubilee) |

This table reflects compatibility, not a guarantee that every line still receives security support or patches. Check support status and patch versions on the Spring Cloud Supported Versions page before upgrading production.

### 2.2. Cloud provider library mappings

Provider libraries have their own BOMs and release schedules. Examples of published mappings:

| Library | Corresponding Spring Boot / Spring Cloud | Notes |
| --- | --- | --- |
| Spring Cloud AWS 4.x | Boot 4.0.x / Spring Cloud 2025.1.x | Uses AWS SDK for Java 2.x |
| Spring Cloud AWS 3.4.x | Boot 3.5.x / Spring Cloud 2025.0.x | Uses AWS SDK for Java 2.x |
| Spring Cloud AWS 3.3.x | Boot 3.4.x / Spring Cloud 2024.0.x | Uses AWS SDK for Java 2.x |
| Spring Cloud AWS 3.1.x–3.2.x | Boot 3.2.x–3.3.x / Spring Cloud 2023.0.x | Verify exact compatible patch |
| Spring Cloud AWS 2.4.x | Boot 2.6.x–2.7.x / Spring Cloud 2021.0.x | Maintenance line, uses AWS SDK for Java 1.x |
| Spring Cloud Azure 7.x | Boot 4.0.x / Spring Cloud 2025.1.x | Check JDK range of the patch |
| Spring Cloud Azure 6.x | Boot 3.5.x / Spring Cloud 2025.0.x | Current line for Boot 3.5 |
| Spring Cloud Azure 5.x | Boot 3.2.x–3.5.x depending on patch and Spring Cloud train | Do not generalize one patch across the entire line |
| Spring Framework on Google Cloud 8.x | Boot 4.0.x / 4.1.x, Spring Cloud 2025.1.x | Check module-specific exceptions |
| Spring Framework on Google Cloud 7.x | Boot 3.5.x / Spring Cloud 2025.0.x | Spring Framework 6.2.8+ per mapping |
| Spring Framework on Google Cloud 6.x | Boot 3.4.x / Spring Cloud 2024.0.x | Spring Framework 6.2.x |
| Spring Framework on Google Cloud 5.x | Boot 3.2.x / 3.3.x, Spring Cloud 2023.0.x | Trace module has compatibility exceptions |

These tables change across patch releases. Before picking versions, cross-check at least three sources: the Spring Boot/Cloud support mapping, the provider's BOM, and release notes for the specific service starter. Never infer one provider's mapping from another provider's mapping.

### 2.3. Signs of mixing major versions

- Spring Cloud AWS 2.x belongs to the AWS SDK v1 generation; Spring Cloud AWS 3.x/4.x uses SDK v2.
- Spring Boot 3.x moved to Spring Framework 6 and Jakarta EE; many `javax.*` APIs became `jakarta.*`.
- Spring Cloud Azure 4.x and later use the unified `spring-cloud-azure-dependencies` BOM; older `azure-spring-*` starters may belong to an earlier structure.
- Spring Framework on Google Cloud has its own BOM; trace/observability modules may have different constraints than storage, Pub/Sub, or Secret Manager.
- An application can contain both AWS SDKs or multiple HTTP clients, yet coexisting on the classpath does not mean their auto-configurations, adapters, or model objects are compatible.

If a stack trace shows `javax.servlet.*` in a Boot 3/4 application, find the legacy dependency instead of adding `javax.servlet-api` to silence compile errors. Mixing `javax` and `jakarta` APIs usually causes deployment errors or framework interface cast failures.

## 3. Using BOMs to keep dependency groups consistent

### 3.1. Role of each BOM

| BOM | Management scope |
| --- | --- |
| `spring-boot-dependencies` | Spring Boot, Spring Framework, and the core dependency set tested by Boot |
| `spring-cloud-dependencies` | Spring Cloud release train |
| `spring-cloud-aws-dependencies` | Spring Cloud AWS starters and related dependencies |
| `spring-cloud-azure-dependencies` | Spring Cloud Azure starters and Azure SDK dependency set |
| `spring-cloud-gcp-dependencies` | Spring Framework on Google Cloud starters and related dependencies |
| `libraries-bom` | Google Cloud Java client libraries and foundations such as gRPC, protobuf, Guava |

A BOM is a set of version rules, not a dependency packaged directly. When declaring starters managed by a BOM, omit individual versions on those starters.

### 3.2. Maven: importing BOMs for your platform

The `dependencyManagement` snippet below illustrates the structure. Replace version properties with versions verified against your project's compatibility matrix:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>SPRING_BOOT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>SPRING_CLOUD_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Only import BOMs for providers actually in use. -->
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

If an application uses Google Cloud Java clients directly without Spring Framework on Google Cloud starters, you may need `com.google.cloud:libraries-bom` instead of the Spring GCP BOM. Avoid importing multiple BOMs managing the same artifact without understanding Maven precedence rules and which version actually wins.

Example declaring starters once BOMs are in place:

```xml
<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>

    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
```

Starter names can change across release lines. Verify the exact BOM's catalog before copying artifact IDs into your project.

### 3.3. Gradle: using platform/BOM

Kotlin DSL example:

```kotlin
dependencies {
    implementation(platform(
        "org.springframework.cloud:spring-cloud-dependencies:SPRING_CLOUD_VERSION"
    ))
    implementation(platform(
        "io.awspring.cloud:spring-cloud-aws-dependencies:SPRING_CLOUD_AWS_VERSION"
    ))
    implementation(platform(
        "com.azure.spring:spring-cloud-azure-dependencies:SPRING_CLOUD_AZURE_VERSION"
    ))
    implementation(platform(
        "com.google.cloud:spring-cloud-gcp-dependencies:SPRING_CLOUD_GCP_VERSION"
    ))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
}
```

When using the Spring Boot plugin, the Boot BOM is applied per plugin configuration or native Gradle platform support. When using multiple BOMs, run `dependencyInsight` to see which final version is selected. Never pin an explicit version on a single dependency just to silence an error temporarily.

### 3.4. Avoid overriding foundational dependencies arbitrarily

Properties such as `netty.version`, `reactor-bom.version`, `grpc.version`, `protobuf.version`, `guava.version`, or `slf4j.version` may be managed by BOMs. Overriding a single property can affect many modules simultaneously.

Only override when:

1. A confirmed advisory or bug requires a patch.
2. Framework/provider release notes confirm the version is compatible.
3. The dependency tree shows all related modules updating consistently together.
4. Builds, linkage checks, and integration tests all pass.

Do not force all of Netty onto a newer patch just because one library requests a newer patch. First verify minimum versions of transports, `netty-common`, `netty-buffer`, `netty-codec`, `netty-transport`, `netty-handler`, resolver, and native artifacts.

## 4. Inspecting the dependency tree and actual classpath

### 4.1. Maven

Print the dependency tree:

```bash
mvn dependency:tree -Dverbose
```

Filter for groups commonly involved in incidents:

```bash
mvn dependency:tree -Dverbose "-Dincludes=io.netty:*,io.projectreactor.netty:*,io.projectreactor:*,io.grpc:*,com.google.protobuf:*,com.google.guava:*,software.amazon.awssdk:*,com.amazonaws:*,com.azure:*,org.springframework:*"
```

Inspect the effective POM to see which BOM/property won:

```bash
mvn help:effective-pom
```

Locate version mediation, transitive paths, and omitted dependencies:

```bash
mvn dependency:tree -Dverbose -Dincludes=io.netty:netty-common
mvn dependency:tree -Dverbose -Dincludes=io.grpc:grpc-netty-shaded
mvn dependency:tree -Dverbose -Dincludes=software.amazon.awssdk:netty-nio-client
```

`omitted for conflict` indicates Maven picked a different version through mediation. It does not prove the chosen version is compatible; compare that version against each library's BOM.

### 4.2. Gradle

View the full runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Investigate a specific artifact:

```bash
./gradlew dependencyInsight --dependency netty-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-netty-shaded --configuration runtimeClasspath
```

`dependencyInsight` shows which dependency requested the version, which rule picked the final version, and any constraints involved.

On Windows PowerShell, you can run `gradlew.bat` instead of `./gradlew`.

### 4.3. Comparing compile classpath and runtime classpath

A dependency can exist on `compileClasspath` without existing on `runtimeClasspath`, or vice versa due to scopes/exclusions. An application may compile yet lack a transport at runtime.

Inspect all of:

- Compile classpath.
- Runtime classpath.
- Test runtime classpath.
- Actual JARs inside the image or `BOOT-INF/lib`.
- Classpath entries added externally by an application server, Spark/Hadoop, or launcher.

If an error happens only in the production container, compare the JAR list inside the image against the build's runtime tree. A developer machine's dependency tree does not reflect JARs injected by the production platform.

## 5. Common classpath conflicts

### 5.1. AWS SDK for Java 1.x vs. 2.x

The two major versions use distinct packages:

| SDK generation | Root package |
| --- | --- |
| AWS SDK v1 | `com.amazonaws.*` |
| AWS SDK v2 | `software.amazon.awssdk.*` |

Spring Cloud AWS 2.x uses SDK v1; Spring Cloud AWS 3.x/4.x uses SDK v2. During an incomplete migration, both SDKs can coexist because packages differ, yet:

- `AmazonS3` and `S3Client` are different APIs.
- Credentials, request models, exceptions, and HTTP clients are not shared.
- Legacy starters/auto-configuration can create different bean types or expect different properties.
- The SDK v1 BOM does not manage SDK v2 and vice versa.

Never cast SDK v1 objects to SDK v2 or pass one major version's request model into the other's client. Pick one major version for new code; if running side by side during migration, define clear adapters and bean names.

### 5.2. javax.* vs. jakarta.*

Spring Boot 3 and later use Jakarta EE namespaces for the corresponding APIs. Examples:

- `javax.servlet.*` → `jakarta.servlet.*`
- `javax.persistence.*` → `jakarta.persistence.*`
- `javax.validation.*` → `jakarta.validation.*`

An older dependency may compile standalone yet fail with Boot 3/4 Servlet/JPA versions. Locate the legacy JAR in the dependency tree, upgrade the library to its Jakarta line, or replace the adapter. Never add both APIs simultaneously just to force compilation when the runtime implementation only supports one namespace.

### 5.3. Spring Framework 5/6/7 and Spring Cloud

Starters pull in Spring modules transitively. If a project uses Boot 3 while an old starter pulls in Spring Framework 5, the classpath can contain incompatible APIs.

Check these artifacts:

- `org.springframework:spring-core`
- `org.springframework:spring-context`
- `org.springframework:spring-web`
- `org.springframework:spring-webflux`
- `org.springframework:spring-beans`
- `org.springframework:spring-aop`

All Spring Framework modules inside an application context must share the same release line. Use the matching Spring Boot BOM and Spring Cloud BOM instead of pinning individual `spring-*` JARs.

### 5.4. SLF4J and logging implementations

Common symptoms:

- `NoSuchMethodError` in `org.slf4j`.
- `NoClassDefFoundError: org/slf4j/impl/StaticLoggerBinder` with legacy bindings.
- Warnings about multiple SLF4J providers/bindings.
- Missing or duplicated logs due to multiple active logging implementations.

Spring Boot manages a compatible logging stack. Do not arbitrarily add `slf4j-simple`, `log4j-slf4j-impl`, `logback-classic`, or bridges when Boot already supplies the logging implementation. Choose one backend and bridges matching your SLF4J version.

### 5.5. Guava, protobuf, and gRPC

Google Cloud Java libraries rely on foundational dependencies such as:

- Guava.
- `protobuf-java`.
- gRPC API/stub/core.
- GAX.
- Google Auth Library.
- HTTP transport.

If another library pulls in an outdated Guava/protobuf version, runtime errors can occur when a Google client calls a method absent from the resolved version.

Prefer `spring-cloud-gcp-dependencies` when using Spring Framework on Google Cloud starters, or `libraries-bom` when using Google Cloud Java clients directly. Do not pin individual protobuf/gRPC artifacts if a BOM already manages them, unless you have verified compatibility across the entire group.

## 6. Netty in multi-cloud applications

### 6.1. Why do multiple libraries pull in Netty?

Netty can enter through several dependency paths:

| Component | Role of Netty |
| --- | --- |
| Spring WebFlux / Reactor Netty | Non-blocking HTTP server and HTTP client |
| AWS SDK v2 async | `NettyNioAsyncHttpClient` is the default async HTTP client |
| Azure SDK for Java | `azure-core-http-netty` is the default Azure SDK HTTP transport |
| Google Cloud gRPC clients | May use `grpc-netty-shaded` or the corresponding gRPC transport |
| Other SDKs/connectors | May pull in Netty modules or dedicated native transports |

These components do not necessarily share the same BOM. When they share unshaded `io.netty.*` on the same classloader, incorrect version mediation can produce linkage errors.

### 6.2. Recognizing Netty version skew

Symptoms:

- `NoSuchMethodError` in `io.netty.*`.
- `NoSuchFieldError` in `ByteBuf`, `ChannelOption`, `SslContext`, or other Netty classes.
- `AbstractMethodError` in handlers/codecs.
- Channel/event-loop creation failures after upgrading an SDK.
- Only one transport fails while other HTTP clients keep working.
- `ClassNotFoundException` for a Netty module required by a transport.

Inspect the entire `io.netty` group in the runtime tree. Modules from the same Netty line must be managed in lockstep; do not check only `netty-all`, because many SDKs declare individual Netty modules.

### 6.3. How grpc-netty-shaded differs from netty-*

`grpc-netty-shaded` packages Netty under relocated package names. It is not the same as adding a standard `io.netty:netty-transport` artifact to the classpath.

Do not exclude `grpc-netty-shaded` just because you see "Netty" in the artifact name. Identify the actual gRPC transport used by your Google client. When an application includes Reactor Netty, Azure Netty, and gRPC shaded transport together, verify each group's versions independently against its corresponding BOM.

### 6.4. Never upgrade Netty via a single standalone dependency

A common mistake is adding a newer `netty-handler` while leaving `netty-common`, `netty-buffer`, `netty-codec`, or `netty-transport` on an older version selected by another BOM. The result can be worse because classes exist while method signatures mismatch.

How to fix:

1. Find the first dependency introducing Netty into the tree.
2. List all Netty modules and their resolved versions.
3. Identify which BOM manages each version.
4. Upgrade BOMs/starters to compatible patches where available.
5. Apply controlled dependency constraints/overrides only if confirmed by the vendor.
6. Run linkage checks and integration tests on the runtime image.

### 6.5. AWS SDK v2: sync and async use different HTTP clients

AWS SDK for Java 2.x distinguishes clearly:

| Service client | Model | Typical default HTTP client |
| --- | --- | --- |
| `S3Client`, `SqsClient`, `DynamoDbClient` | Synchronous | Apache-based sync HTTP client |
| `S3AsyncClient`, `SqsAsyncClient`, `DynamoDbAsyncClient` | Asynchronous | Netty-based async HTTP client |
| Async using CRT | Asynchronous | AWS Common Runtime HTTP client |

If you exclude `netty-nio-client` from the classpath to trim dependencies yet still instantiate `S3AsyncClient`, the SDK lacks a suitable async HTTP implementation. Conversely, adding Netty to the application does not automatically turn synchronous `S3Client` into non-blocking I/O.

You can select an HTTP client explicitly in the builder:

```java
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3AsyncClient = S3AsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(64))
        .build();
```

This is an illustrative configuration; choose concurrency based on load, service limits, and pool sizing. Do not create a new client per request. Reuse clients across the application lifecycle and close them on shutdown.

If using only sync clients and wanting fewer dependencies, the AWS SDK offers `URLConnection` or Apache-based clients depending on version. When excluding the default HTTP client, you must add a compatible replacement implementation and verify required HTTP method/timeout capabilities.

### 6.6. Azure SDK for Java: Netty is the default HTTP client

The Azure SDK uses an `HttpClient` abstraction; `azure-core-http-netty` is the standard default implementation. OkHttp or the JDK `HttpClient` can be used if your dependency set and JDK version meet requirements.

If you exclude `azure-core-http-netty`, you must supply another implementation. Dropping Netty without adding a replacement HTTP client causes the Azure SDK to fail when creating clients or sending requests.

Example creating the default Azure HTTP client:

```java
import com.azure.core.http.HttpClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

HttpClient httpClient = HttpClient.createDefault();

BlobServiceClient blobClient =
        new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .httpClient(httpClient)
                .buildClient();
```

Only call `HttpClient.createDefault()` when a default implementation is on the classpath. When using a different transport, add the matching artifact and configure the builder per Azure SDK documentation. Ensure the `azure-core-http-netty` version meets the minimum version published by Microsoft for your release.

### 6.7. Google Cloud: gRPC transport and ALPN

Several Google Cloud Java clients use gRPC. An `ALPN is not configured properly` error usually requires checking:

- Java runtime and platform supported by gRPC.
- gRPC Java version.
- Netty/transport version.
- TLS provider and ALPN support.
- Whether multiple versions of Netty, Guava, or protobuf exist on the classpath.
- Whether the runtime container/server adds JARs outside the build artifact.

Use Google Cloud Java's compatibility checker and troubleshooting guide. Do not blindly add `netty-tcnative` or swap JDKs before inspecting the gRPC error and runtime compatibility.

## 7. Choosing blocking vs. reactive properly

### 7.1. Spring MVC and Spring WebFlux use different thread models

| Model | How requests are handled | Blocking I/O |
| --- | --- | --- |
| Spring MVC / Servlet | Requests run on a servlet thread pool | Sync SDKs can be used with appropriate thread, timeout, and connection pool limits |
| Spring WebFlux | Event loop handles many requests with few threads | Never call blocking APIs directly on event-loop threads |
| Worker/background job | Depends on executor and workload | Blocking APIs can run on a dedicated thread pool |
| End-to-end reactive pipeline | Passes `Mono`/`Flux` up to callers | Prefer async/reactive SDKs and avoid calling `block()` inside pipelines |

WebFlux does not make every Java library non-blocking. A controller returning `Mono` that internally calls JDBC, sync `S3Client`, or `Storage.get()` can still block the event loop unless offloaded to a scheduler meant for blocking work.

### 7.2. AWS SDK v2: S3Client vs. S3AsyncClient

Sync API:

```java
HeadObjectResponse response = s3Client.headObject(request);
```

This call blocks the invoking thread until a response arrives. In Spring MVC, that can be appropriate if thread pools and timeouts are tuned properly.

In WebFlux, a blocking call can be wrapped on `boundedElastic`:

Assuming `s3Client` and `HeadObjectRequest request` were already created/injected:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<HeadObjectResponse> result =
        Mono.fromCallable(() -> s3Client.headObject(request))
                .subscribeOn(Schedulers.boundedElastic());
```

This is a bridge for blocking libraries, not a conversion of a sync SDK into non-blocking I/O. Limit concurrency and monitor the `boundedElastic` queue; do not use this pattern to mask an unbounded blocking workload.

Async API:

With the same request and a reused `S3AsyncClient`:

```java
Mono<HeadObjectResponse> result =
        Mono.fromFuture(s3AsyncClient.headObject(request));
```

`S3AsyncClient` returns `CompletableFuture`; convert it to Reactor with `Mono.fromFuture`. Return `Mono` to the caller instead of calling `join()` or `get()` on the WebFlux event loop.

### 7.3. Azure SDK: sync and async clients are separate types

The Azure SDK typically provides separate sync and async clients:

- `BlobClient` is synchronous.
- `BlobAsyncClient` returns reactive types.
- `ServiceBusClient` and `ServiceBusAsyncClient` follow the corresponding model.
- `SecretClient` and `SecretAsyncClient` follow the corresponding model.

Async Blob example:

```java
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobClientBuilder;
import com.azure.storage.blob.models.BlobProperties;
import reactor.core.publisher.Mono;

BlobAsyncClient blobAsyncClient =
        new BlobClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .buildAsyncClient();

Mono<BlobProperties> properties =
        blobAsyncClient.getProperties();
```

`Mono` is a cold publisher: the request executes only upon subscription. In a WebFlux controller, return the publisher so the framework subscribes; never call `subscribe()` manually and return an empty response.

If using a sync client in WebFlux, wrap the call in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and manage concurrency. Never call `block()` on the event loop.

### 7.4. Google Cloud Java clients have no single async model

Google Cloud Java libraries expose APIs per service:

- Many service clients offer synchronous methods.
- Some long-running APIs return `OperationFuture` or `OperationCallable`.
- Pub/Sub `Publisher` returns `ApiFuture` when publishing.
- Some services expose async stubs or dedicated callbacks via gRPC.
- Cloud Storage's `Storage` interface has many synchronous methods.

Do not assume every class named `Client` is non-blocking. Read the API of the exact service and method you are calling.

Synchronous Cloud Storage in WebFlux example:

```java
Mono<Blob> blobMono =
        Mono.fromCallable(() -> storage.get(bucketName, objectName))
                .subscribeOn(Schedulers.boundedElastic());
```

If a service provides a future/callback API, convert the future to a reactive type with an appropriate adapter. Avoid calling `future.get()` or waiting on a latch on the event loop.

### 7.5. Never call subscribe() and discard the result

Error-prone pattern:

```java
@GetMapping("/orders/{id}")
Mono<Order> getOrder(@PathVariable String id) {
    paymentClient.lookup(id)
            .subscribe(result -> log.info("Lookup completed"));
    return Mono.just(new Order(id));
}
```

The request returns before lookup finishes; exceptions, cancellation, and context from the lookup are detached from the response pipeline.

Compose the publisher instead:

```java
@GetMapping("/orders/{id}")
Mono<Order> getOrder(@PathVariable String id) {
    return paymentClient.lookup(id)
            .map(result -> new Order(id, result.status()));
}
```

Use fire-and-forget only when explicitly required by business rules and backed by dedicated queues/retries/observability—never call `subscribe()` to dodge designing an async flow.

## 8. Signs of event-loop starvation and pool exhaustion

### 8.1. Blocked event loop

Signs:

- Many requests slow down simultaneously even while CPU remains low.
- `reactor-http-nio-*` threads sit inside socket reads, JDBC calls, `Future.get()`, `Thread.sleep()`, or `block()`.
- Reactor emits warnings about blocking calls on non-blocking threads.
- Timeouts spike simultaneously across multiple endpoints.
- Requests unrelated to cloud SDKs also slow down.

Inspect thread dumps and locate the first stack frame belonging to application code or sync SDKs. Move blocking calls onto `boundedElastic` or switch to async clients.

### 8.2. Exhausted connection pools

A pool can run out of connections because:

- Max connections are lower than actual concurrency.
- Requests hold connections while waiting on downstreams.
- Response bodies/streams are not consumed or closed.
- Acquire timeouts are too short for legitimate queues.
- Retries inflate concurrent in-flight requests.
- Too many service clients are created, each owning a separate pool.
- Clients are not reused.

Distinguish pending-acquire timeouts from downstream timeouts. Raising pool size without controlling concurrency can overload the service provider further.

### 8.3. Backpressure and concurrency

Reactive does not mean infinite throughput. When calling cloud services, cap concurrency based on:

- Provider quotas/rate limits.
- SDK HTTP client max concurrency.
- Available connections.
- Thread pool/executor capacity.
- Payload sizes and response times.
- Number of replicas targeting the same resource.

Use `flatMap` with a concurrency cap when fanning out to many objects/messages. Avoid unbounded `flatMap` firing thousands of simultaneous requests.

## 9. HTTP client configuration and lifecycle

### 9.1. Reusing clients

Service clients are generally thread-safe and designed for reuse. Creating a client per request causes:

- Spawning multiple connection pools and event loops.
- Repeated DNS/TLS handshakes.
- Rising threads, sockets, and file descriptors.
- Higher startup overhead/latency.
- Difficulty closing resources on application shutdown.

Instantiate clients as Spring singleton beans or via a lifecycle-managed factory. Close clients/transports per SDK guidance when the `ApplicationContext` stops.

### 9.2. Timeouts must be configured per layer

| Timeout | Limit |
| --- | --- |
| Connection timeout | Time to open a TCP/TLS connection |
| TLS handshake timeout | Time to complete handshake |
| Read/response timeout | Time waiting for a response or data |
| API call timeout | Total duration for one SDK call, potentially including retries |
| Pool acquire timeout | Time waiting to obtain a connection from the pool |
| Reactor timeout | Deadline of a publisher in the pipeline |
| Business deadline | Maximum duration accepted by business logic |

Setting a Reactor timeout shorter than the SDK API timeout can cause callers to cancel subscriptions while the underlying SDK request keeps running if cancellation does not propagate all the way to the transport. Check the cancellation semantics of your specific client.

### 9.3. Closing streams and response bodies

Streaming APIs can hold sockets/connections open until the body is consumed or closed. Examples such as AWS `ResponseInputStream`, Azure download streams, and Google `ReadChannel` must be handled per SDK contract.

Use try-with-resources for synchronous streams. For reactive streams, propagate cancellation and never drop a subscriber mid-stream without releasing resources.

### 9.4. Do not share an HTTP client of the wrong type

An async HTTP client cannot necessarily serve a synchronous service client. Likewise, Reactor Netty `HttpClient`, AWS `SdkHttpClient`, Azure `HttpClient`, and gRPC `ManagedChannel` are distinct abstractions even though several rely on Netty underneath.

Share connection pools only when explicitly supported by the SDK and when transport types match. Never pass a Reactor Netty client directly into the AWS SDK merely because both are built on Netty.

## 10. Handling by cloud provider

### 10.1. AWS SDK for Java 2.x

Check:

- All AWS SDK v2 service modules match the AWS SDK BOM version.
- Never mix different `software.amazon.awssdk:*` versions.
- `S3Client` uses a sync HTTP client; `S3AsyncClient` requires an async HTTP client.
- If excluding Apache/Netty to trim dependencies, add a replacement HTTP implementation for the matching client type.
- AWS CRT carries native dependencies and requires compatible OS/runtime support.
- Share one client per region/endpoint/credential configuration; close clients on shutdown.
- Never block with `join()` on Netty/Reactor event loops.

Maven example importing the AWS SDK v2 BOM for direct SDK clients:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>AWS_SDK_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

When using Spring Cloud AWS, prefer the Spring Cloud AWS BOM and only override the AWS SDK BOM for a clear compatibility reason. Check whether legacy AWS SDK v1 is pulled in by an older integration.

### 10.2. Azure SDK for Java

Check:

- Spring Cloud Azure BOM aligns with Spring Boot/Spring Cloud.
- Azure SDK libraries are managed by the matching BOM.
- `azure-core-http-netty` has a compatible version; if excluded, replace it with supported OkHttp or JDK `HttpClient`.
- Sync clients are never called directly on WebFlux event loops.
- Async clients return `Mono`/`Flux`; return/compose publishers instead of subscribing manually.
- Netty transport is shared with Reactor Netty, so check for version skew.
- Service Bus, Event Hubs, and AMQP clients use dedicated transports; do not equate them with the HTTP Netty client.
- Close `HttpClient`/client resources if constructed manually and required by SDK lifecycle rules.

### 10.3. Google Cloud Java libraries

Check:

- Use `spring-cloud-gcp-dependencies` for Spring Framework on Google Cloud starters.
- Use `libraries-bom` when declaring Google Cloud Java clients directly per library instructions.
- Never pin Guava, protobuf, or gRPC independently without checking the entire dependency graph.
- Run the gRPC compatibility checker if encountering ALPN errors.
- Distinguish sync APIs, `ApiFuture`, `OperationFuture`, callbacks, and async stubs per service.
- Check whether the runtime container adds Netty/Guava/protobuf JARs outside the build artifact.
- Reuse `Publisher`, `Storage`, `SecretManagerServiceClient`, and corresponding clients across the lifecycle; never recreate clients per request.

## 11. Tools to catch linkage errors early

### 11.1. Maven Enforcer dependency convergence

You can enable a rule to detect multiple versions of the same artifact in the dependency tree:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>MAVEN_ENFORCER_VERSION</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

This rule can flag benign conflicts in `test` scope or dependencies where BOMs intentionally select a version. Inspect each path before adding exclusions. Never apply broad exclusion lists just to force a green build.

### 11.2. Google Linkage Checker

The Google Cloud Java troubleshooting guide recommends the Linkage Checker Enforcer Rule to detect certain linkage errors before runtime. This is a helpful extra check when using multiple Google Cloud libraries or encountering `NoSuchMethodError`/`NoClassDefFoundError`.

Linkage checker does not replace integration tests on the runtime image. An app server or container can introduce JARs outside Maven/Gradle's dependency graph.

### 11.3. Inspecting the packaged artifact

For a Spring Boot executable JAR:

```bash
jar tf target/orders-api.jar
```

Check runtime libraries under `BOOT-INF/lib`. For Docker images, inspect the exact deployed image digest and the actual JAR list inside the image. When using layered JARs/buildpacks, compare dependency layers against the released image.

### 11.4. Enabling controlled diagnostics

When needed, log:

- Spring Boot/Spring Framework/Spring Cloud versions.
- SDK/provider starter versions.
- Netty, Reactor Netty, gRPC, protobuf, and Guava versions.
- Actual HTTP transport name.
- Active/pending connection counts and timeouts.
- Thread names and relevant stack traces.

Never log access tokens, credentials, SAS tokens, signed URLs, or business payloads. Turn off debug logs once isolated to avoid cost increases and data exposure.

## 12. Troubleshooting matrix by specific error

| Error | Common cause | First remediation step |
| --- | --- | --- |
| `NoSuchMethodError` | Runtime picked an older class version than compile time | Locate artifact containing the class, run dependency tree/insight to trace version path |
| `NoClassDefFoundError` | Missing JAR, failed class initialization, or different runtime classpath | Read `Caused by` first, check runtime JARs and initializers |
| `ClassNotFoundException` | Missing dependency or classloader cannot see the JAR | Check scopes, packaging, and classloaders |
| `AbstractMethodError` | Interface/implementation binary contracts diverge | Align Spring/provider/SDK versions |
| `NoSuchFieldError` | Class version lacks the field expected by caller | Locate JAR containing the class and remove mismatched overrides |
| `ALPN is not configured properly` | Incompatible gRPC/Netty/JDK/platform | Run gRPC compatibility checker, check Netty and runtime JDK |
| `UnsatisfiedLinkError` | Mismatched native library/classifier | Check OS, CPU, libc, native artifacts, and fallback transports |
| `NoClassDefFoundError: io/netty/...` | Missing async HTTP transport or Netty excluded | Add the right Netty transport or choose another client |
| `NoSuchMethodError: io.netty...` | Netty module version skew | Align all Netty modules under a compatible BOM |
| `NoSuchMethodError: reactor...` | Reactor Core/Reactor Netty out of sync | Remove version overrides, use Spring Boot BOM |
| ALPN/gRPC fails only in container | Runtime image has different JARs or JDK from build | Compare runtime image, JDK, gRPC, and Netty |
| `NoSuchBeanDefinitionException` for provider client | Missing starter, excluded auto-config, or unmatched condition | Check starters, properties, classpath, and condition evaluation report |
| AWS async client lacks HTTP implementation | Excluded Netty/CRT while still using async client | Add `netty-nio-client`/CRT or configure another async transport |
| Azure client lacks `HttpClient` implementation | Excluded Azure Netty without adding another transport | Add `azure-core-http-okhttp` or compatible JDK `HttpClient` |
| WebFlux warns about blocking calls | Calling sync SDK/JDBC on event loop | Switch to async API or `boundedElastic` |
| WebFlux hangs without exceptions | Event-loop starvation or deadlock | Take thread dumps, locate `block()`, `Future.get()`, JDBC/socket reads |
| `PoolAcquireTimeoutException` | Pool exhausted or requests hold connections too long | Check active/pending, response body closing, concurrency, and timeouts |
| `RejectedExecutionException` | Executor shut down or overloaded | Check lifecycle, queue size, and thread pool |
| Reactive pipeline never runs | Cold publisher never returned/subscribed | Compose and return `Mono`/`Flux`; never create a publisher and discard it |
| Reactive request returns early | Called `subscribe()` then returned another response | Compose the publisher into the business chain |
| Request sent twice | Multiple subscriptions or non-idempotent retries | Check subscription count and retry policy |
| Memory grows when downloading objects | Streams/bodies left unclosed or oversized buffers | Stream data, close resources, and bound concurrency |
| Latency rises after creating clients per request | Multiple pools/event loops and TLS handshakes | Reuse singleton clients, cap pools |
| Timeouts despite low CPU | Blocked threads, pool acquire, DNS, or slow downstream | Measure connect/read/pool/API timeouts and thread states separately |

## 13. Controlled remediation workflow

Follow this order to avoid introducing new conflicts:

1. **Capture the original failure:** save full stack trace, JDK version, image digest, profile, and timestamp.
2. **Identify the layer:** Spring compatibility, classpath, transport, TLS/native, or blocking/reactive.
3. **Pull the runtime dependency tree:** filter Spring, Netty, Reactor, gRPC, protobuf, Guava, and provider SDKs.
4. **Trace version sources:** which BOM manages the artifact, which dependency pulls the version, which rule overrides it.
5. **Cross-check the compatibility matrix:** Boot, Cloud release train, provider starter, SDK, and JDK.
6. **Pick the smallest fix:** align BOM/starter lines, drop dependency pins, fix exclusions, or swap sync/async clients.
7. **Verify the code model:** never block the event loop, never fire-and-forget `subscribe()`, close streams, and reuse clients.
8. **Rebuild from clean state:** avoid stale JARs in caches or build directories.
9. **Run integration tests on a production-equivalent runtime:** exact JDK, container base image, native architecture, proxy, and transport.
10. **Monitor post-rollout:** thread pools, event loops, connection pools, timeouts, error rates, and real request counts.

If failures began after adding a provider starter, compare the dependency tree before and after the change. The new starter may pull a different Netty, Reactor, gRPC, or Spring module version onto the classpath even when business code is unchanged.

## 14. Lab: an Orders API calling all three clouds

Goal: Orders API runs Spring Boot and exposes WebFlux endpoints. The service must:

- Read objects from Amazon S3.
- Fetch blob metadata from Azure Blob Storage.
- Query object metadata from Google Cloud Storage.

One version of the code uses all three synchronous clients inside a reactive controller. As load rises, the event loop gets blocked; simultaneously, Azure Netty and AWS async Netty pull two different version lines.

### Step 1 — Record the baseline platform

Record Spring Boot, Spring Cloud train, JDK, and provider BOM versions. Confirm all versions fit each provider's compatibility matrix. Do not upgrade dependencies before recording the baseline state.

### Step 2 — Analyze the dependency tree

Run Maven:

```bash
mvn dependency:tree -Dverbose "-Dincludes=io.netty:*,io.projectreactor.netty:*,io.projectreactor:*,io.grpc:*,com.google.protobuf:*,com.google.guava:*,software.amazon.awssdk:*,com.azure:*"
```

Or Gradle:

```bash
./gradlew dependencyInsight --dependency netty-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-netty-shaded --configuration runtimeClasspath
```

Record selected versions and the dependency paths introducing each artifact.

### Step 3 — Pick the I/O model per SDK

- AWS: use `S3AsyncClient` to keep the pipeline reactive; convert `CompletableFuture` into `Mono`.
- Azure: use `BlobAsyncClient` and return `Mono`/`Flux` directly.
- Google Cloud Storage: if using synchronous `Storage`, wrap operations on `boundedElastic`; if a service offers a dedicated async API, use that API.

Never call `block()` on the event loop and never call `subscribe()` inside the controller.

### Step 4 — Standardize dependencies

Use compatible Spring Boot/Cloud BOMs and provider BOMs. Never pin an individual Netty module to patch a `NoSuchMethodError`. If gRPC/Netty conflicts, determine whether the shaded or unshaded transport is involved before fixing.

### Step 5 — Verify lifecycles

Ensure each SDK client is created once, pools are bounded, response streams are closed, and clients shut down cleanly when the application stops.

### Step 6 — Test

Run these checks:

- Context startup and auto-configuration.
- One request to each provider.
- Bounded concurrent requests.
- Timeouts/cancellation when downstreams are slow.
- Confirm zero blocking calls on event loops.
- Inspect active/pending pool metrics and thread counts.
- Run inside the exact production Docker image/architecture.

This lab is complete when the dependency graph aligns with BOMs, all three providers return valid results, zero linkage errors occur, event loops stay unblocked, and pools do not grow unboundedly under load.

## 15. Operational principles

- Choose Spring Boot and Spring Cloud release trains first; then pick provider starters per the compatibility matrix.
- Use Spring Boot, Spring Cloud, and provider BOMs to manage dependencies.
- Use Google `libraries-bom` when declaring Google Cloud Java libraries directly per guidance.
- Never mix Spring Cloud AWS 2.x and 3.x/4.x starters in the same configuration without a migration plan.
- Never add multiple logging backends or multiple SLF4J versions.
- Check `javax`/`jakarta` namespaces when upgrading Boot 2 to Boot 3/4.
- Inspect all Netty modules, not just `netty-all`.
- Distinguish `grpc-netty-shaded` from `io.netty`.
- AWS async clients need an async HTTP transport; Azure SDK needs an HTTP implementation; Google gRPC clients need compatible ALPN/Netty runtimes.
- Use async SDKs in WebFlux when available; if using blocking SDKs, offload to a blocking-work scheduler and cap concurrency.
- Never call `block()`, `Future.get()`, or sync JDBC on event loops.
- Never call `subscribe()` and discard the publisher in a controller.
- Reuse clients, configure bounded timeouts/pools, and close streams/resources.
- Build and test on the real runtime image, not just in an IDE or developer machine.
- When failures appear after adding a starter, diff before/after dependency trees to pinpoint which transitive dependency changed.

## 16. Key takeaways

- `NoSuchMethodError`, `NoClassDefFoundError`, and `AbstractMethodError` usually point to binary dependency mismatches.
- Spring Boot, Spring Cloud release trains, and provider starters must fall within matching compatibility matrices.
- BOMs keep versions synchronized; never override Netty/Reactor/gRPC arbitrarily.
- AWS SDK v1 (`com.amazonaws`) and v2 (`software.amazon.awssdk`) have separate APIs; Spring Cloud AWS 2.x and 3.x/4.x are not on the same major line.
- Spring Boot 3+ uses Jakarta namespaces for the corresponding APIs; legacy `javax.*` dependencies can trigger runtime errors.
- AWS SDK v2 async uses the Netty HTTP client by default; sync and async clients have distinct transport requirements.
- Azure SDK uses `azure-core-http-netty` by default and supports swapping transports when a compatible implementation is added.
- Google Cloud Java libraries may use gRPC; verify ALPN, Netty, Guava, and protobuf with the compatibility checker.
- WebFlux runs on a small event loop; never perform blocking I/O directly on event-loop threads.
- Azure async clients return Reactor types; AWS async clients return `CompletableFuture`; Google Cloud async models vary by service API.
- Reactive publishers must be composed and returned; never fire-and-forget `subscribe()` inside controllers.
- Clients and connection pools must be reused, concurrency-bounded, timeout-configured, and closed cleanly per lifecycle.
- Conclude an error is fixed only after verifying the dependency graph and testing on the real runtime image.

## Official reference documentation

1. [Spring Cloud — Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
2. [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
3. [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
4. [Spring Boot — Migration Guide 3.0 and Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
5. [Spring Cloud AWS — Compatibility matrix and supported integrations](https://github.com/awspring/spring-cloud-aws)
6. [AWS SDK for Java 2.x — Configure HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html)
7. [AWS SDK for Java 2.x — Configure the Netty async HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html)
8. [AWS SDK for Java 2.x — Asynchronous programming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
9. [Spring Cloud Azure — Spring version mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping)
10. [Spring Cloud Azure — BOM and dependency setup](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
11. [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
12. [Azure SDK for Java — Asynchronous programming](https://learn.microsoft.com/en-us/azure/developer/java/sdk/async-programming)
13. [Spring Framework on Google Cloud — Compatibility and dependency setup](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/getting-started.html)
14. [Google Cloud Java — Use the Libraries BOM](https://docs.cloud.google.com/java/docs/bom)
15. [Google Cloud Java — Troubleshooting classpath and ALPN](https://docs.cloud.google.com/java/docs/troubleshooting)
16. [Spring Framework — WebFlux concurrency model and blocking APIs](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
17. [Project Reactor — Wrapping synchronous blocking calls](https://projectreactor.io/docs/core/release/reference/faq.html)
18. [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
19. [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
20. [Maven Enforcer — Dependency convergence](https://maven.apache.org/components/enforcer/enforcer-rules/dependencyConvergence.html)

Compatibility matrices, minimum dependency versions, and transport behavior can shift between patch releases. Always verify the BOMs and release notes your application uses, and inspect the resolved runtime classpath before changing any transitive dependency.
