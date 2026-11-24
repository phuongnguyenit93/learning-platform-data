# Đóng gói ứng dụng và phân biệt yêu cầu runtime của từng biến thể Spring Cloud Gateway

Đóng gói một ứng dụng **Spring Cloud Gateway** không đơn giản là tạo JAR và đặt nó vào Docker. Một Gateway có thể build thành công nhưng không tìm thấy route, chạy nhầm Servlet runtime thay vì Reactor Netty, không kết nối được Redis hoặc service registry, hay bị Kubernetes liên tục khởi động lại do health probe không đúng. Những lỗi này thường chỉ xuất hiện sau khi đưa ứng dụng vào môi trường có ingress, TLS, nhiều replicas và chính sách bảo mật thực tế.

Bài thuộc chương **Triển khai** của module **SPRING_CLOUD_GATEWAY**, tập trung vào **đóng gói ứng dụng và phân biệt yêu cầu runtime của từng biến thể**. Ta sẽ chọn đúng giữa **Gateway Server WebFlux**, **Gateway Server Web MVC**, **ProxyExchange WebFlux** và **ProxyExchange MVC**, sau đó xây executable JAR/OCI image, cấu hình Java runtime, tài nguyên container, secrets, service discovery, các route predicates/filters, authentication, rate limiting, circuit breaker, retry, TLS và observability.

Sau khi học, bạn có thể:

1. Phân biệt **web stack/runtime** với **kiểu artifact phân phối**.
2. Chọn đúng dependencies, Spring Boot–Spring Cloud BOM và Java runtime theo variant.
3. Đóng gói executable JAR, container image và kiểm tra ứng dụng chạy đúng HTTP server.
4. Cấu hình routes, profiles, service discovery, Redis, TLS/JWT và secrets không phụ thuộc đường dẫn máy developer.
5. Thiết kế startup/readiness/liveness, shutdown, rolling update và phục hồi kết nối dài trong Kubernetes.
6. Đặt smoke/integration tests trước khi coi một image đã sẵn sàng production.

> **Giới hạn phiên bản:** Spring Cloud Gateway đã đổi tên một số starter và prefix cấu hình giữa các release train. Ví dụ dưới đây dùng tên phổ biến ở các dòng Gateway hiện đại; hãy kiểm tra **tài liệu và BOM của phiên bản đang triển khai**. Java 21 trong Dockerfile là **lựa chọn minh họa** và phải khớp baseline Spring Boot/Gateway; nó không phải yêu cầu bắt buộc cho mọi bản. Bài không khẳng định một cấu hình Kubernetes hoặc image mẫu đã đạt tiêu chuẩn bảo mật production khi chưa kiểm thử.

## 1. Hai quyết định: biến thể ứng dụng và định dạng artifact

Cần tách hai trục:

- **Variant:** Gateway Server WebFlux, Gateway Server Web MVC, ProxyExchange WebFlux hoặc ProxyExchange MVC.
- **Artifact:** executable **JAR**, **OCI container image**, hoặc trong phạm vi hỗ trợ của phiên bản, **native executable/AOT**.

Một executable JAR có thể khởi động Reactor Netty **hoặc** một Servlet container tùy classpath/config. Docker image chỉ chứa file, runtime và lệnh chạy; **Docker không tự biến Servlet app thành reactive app**.

| Biến thể | Stack/runtime chủ đạo | Điểm mở rộng | Phù hợp nhất |
|---|---|---|---|
| **Gateway Server WebFlux** | Spring WebFlux + Project Reactor, thường **Reactor Netty** | Reactive route predicates, `GatewayFilter`, `GlobalFilter` | API Gateway tập trung, nhiều routes/filters và traffic I/O concurrent |
| **Gateway Server Web MVC** | Spring MVC / **Servlet container** | WebMvc.fn `RouterFunction`, handler filter functions | Gateway tích hợp Servlet/MVC ecosystem |
| **ProxyExchange WebFlux** | WebFlux runtime | Controller nhận `ProxyExchange<T>`, trả `Mono<ResponseEntity<?>>` | BFF/proxy vài endpoint theo reactive controller |
| **ProxyExchange MVC** | Spring MVC / Servlet | Controller nhận `ProxyExchange<T>`, trả `ResponseEntity<?>` | BFF/proxy đơn giản trên MVC |

**Gateway Server** có route engine, predicates, filter factories và các tính năng như RequestRateLimiter/Retry theo variant. **ProxyExchange** là công cụ proxy trong controller; việc thêm dependency của nó **không tự kích hoạt** Gateway Server route/filter chain.

### Sơ đồ chọn biến thể

~~~mermaid
flowchart TD
    A["Ứng dụng cần gọi/proxy microservices"] --> B{"Cần route engine & filter policies tập trung?"}
    B -->|Có| C{"Web stack dự định?"}
    C -->|"Reactive WebFlux"| W["Gateway Server WebFlux"]
    C -->|"Servlet / Spring MVC"| M["Gateway Server Web MVC"]
    B -->|"Không, vài controller endpoints"| D{"Controller stack?"}
    D -->|WebFlux| PW["ProxyExchange WebFlux"]
    D -->|MVC| PM["ProxyExchange MVC"]
    W --> J["Chọn JAR / OCI image + Java runtime"]
    M --> J
    PW --> J
    PM --> J
~~~

**Không lựa chọn chỉ dựa trên benchmark RPS của một request GET nhỏ.** Hiệu năng thật phụ thuộc blocking operations, security filters, payload, concurrency, backend latency, retries, connection pool, TLS và memory.

## 2. Gateway Server WebFlux: Netty và reactive pipeline

Ở Gateway Server WebFlux, Spring WebFlux và Project Reactor điều phối chuỗi xử lý request/response bất đồng bộ. Mô hình Gateway Server WebFlux thường dùng **Reactor Netty HTTP server và HTTP client**.

### Những yêu cầu runtime quan trọng

- Starter **Server WebFlux** đúng dòng Spring Cloud Gateway.
- WebFlux/reactive application context cùng Reactor Netty server/client tương thích.
- Custom `GatewayFilter`/`GlobalFilter` dùng `Mono`/`Flux` và **không chặn event loop** bằng `Thread.sleep`, JDBC blocking hoặc `block()`.
- HTTP client connection pool, DNS, connect/response timeouts và Netty direct memory được quan sát.
- Body filters như `CacheRequestBody` hoặc `ModifyRequestBody` có thể gom toàn body, làm memory tăng mạnh với upload lớn.
- Nếu dùng `lb://`, cần Spring Cloud LoadBalancer và service discovery/resolver phù hợp.
- Nếu dùng `RequestRateLimiter` dựa trên Redis, cần Redis client/config và chính sách fail-open/fail-closed được kiểm thử.
- WebSocket/SSE/streaming phải được kiểm cả qua ingress, TLS termination và rollout.

### Không deploy như WAR Servlet truyền thống

**Gateway Server WebFlux không phải một Gateway viết cho external Servlet container.** Hãy ưu tiên **Boot executable JAR hoặc OCI image chạy với runtime Netty được hỗ trợ**. Đừng dựa vào việc Spring WebFlux nói chung có một số khả năng tích hợp Servlet rồi suy rằng **mọi Gateway Server WebFlux có thể được thả vào Tomcat dưới dạng WAR**.

### Những lỗi dễ gặp

| Sai lầm | Hậu quả |
|---|---|
| Thêm `spring-boot-starter-web` chỉ để dùng một tiện ích MVC | Classpath application type xung đột |
| Gọi blocking SDK trên event loop | P95/P99 tăng, requests bị tồn đọng |
| Buffer toàn file trong GatewayFilter | Direct/heap pressure, OOMKill |
| Dùng WebFlux `SecurityWebFilterChain` nhưng thực tế app thành Servlet | Security config không hoạt động như dự kiến |
| Giả định mọi route filters có sẵn | Startup lỗi do thiếu Redis/CircuitBreaker hoặc config sai |

## 3. Gateway Server Web MVC: Servlet, WebMvc.fn và thread model

**Gateway Server Web MVC** dựa trên **Spring MVC/Servlet**. Các điểm mở rộng của nó là **WebMvc.fn `RouterFunction` và handler filter functions**, không phải `ServerWebExchange` và reactive `GatewayFilter` như WebFlux.

### Điều kiện để triển khai

- Starter **Gateway Server Web MVC** tương thích Boot/Cloud.
- Có **Servlet runtime** được hỗ trợ, thường là embedded Tomcat; có thể cấu hình Servlet container khác nếu phiên bản và dependencies cho phép.
- Dùng `SecurityFilterChain` của Spring Security Servlet.
- Nếu cần custom predicates/filter logic, dùng API **GatewayRequestPredicates** và **HandlerFilterFunctions** của MVC.
- Giám sát Servlet threads, HTTP client connection pools, blocking calls và request queues.
- Kiểm tra WebSocket/SSE và timeout theo **Servlet stack/proxy chain thật**, không tự áp giả định Netty.

| Yếu tố | WebFlux Server | Web MVC Server |
|---|---|---|
| HTTP server phổ biến | Reactor Netty | Embedded Servlet container |
| API request trong extension | `ServerWebExchange` | WebMvc.fn `ServerRequest`/Servlet request |
| Filter extension | Reactive `GatewayFilter`/`GlobalFilter` | MVC handler filters |
| Security | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Blocking behavior | Có thể gây kẹt event loop | Giữ worker threads, có thể gây thread exhaustion |
| Streaming/long connections | Reactive publisher lifecycle | Servlet/web server lifecycle tùy ứng dụng |

**MVC không mặc định “chậm”; WebFlux không mặc định “nhanh”.** Chọn theo code và yêu cầu vận hành, rồi đo đúng workload, concurrency, TLS và downstream behavior.

## 4. ProxyExchange WebFlux và MVC: runtime theo controller

**ProxyExchange** sử dụng Spring handler methods thay vì yêu cầu khai báo một full Gateway Server route engine. Ví dụ ở MVC:

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogBff {

    @GetMapping("/bff/catalog")
    ResponseEntity<?> get(ProxyExchange<byte[]> proxy)
            throws Exception {
        // URI do server sở hữu, không lấy raw url từ client.
        return proxy.uri("https://catalog.internal.example.test/items")
            .get();
    }
}
~~~

Với WebFlux, import thường gặp là `org.springframework.cloud.gateway.webflux.ProxyExchange`, và controller trả `Mono<ResponseEntity<?>>`. Package và API cụ thể vẫn phải được kiểm với version đang dùng.

### Điều cần nhớ khi đóng gói ProxyExchange

- ProxyExchange WebFlux cần **WebFlux** web runtime; ProxyExchange MVC cần **Servlet/MVC** web runtime.
- ProxyExchange không tự có Gateway Server `RequestRateLimiter`, `Retry`, `CircuitBreaker` hay dynamic route locator.
- Authentication/authorization, rate limiting, retry, breaker và observability phải được tích hợp **đúng tầng controller/HTTP client**.
- `ProxyExchange<byte[]>` có thể materialize body/response trong RAM; không tự phù hợp streaming file nhiều GiB.
- Khi dùng backend URI, chỉ cho phép đích **server-side allowlist** để chặn open proxy/SSRF.

### Chọn ProxyExchange khi nào?

Khi ứng dụng chỉ có vài endpoint BFF được xử lý riêng, không cần hàng trăm routes và chính sách filter thống nhất. Nếu muốn quản lý predicates, rewrite path/header, circuit breakers và rate limits qua một control plane Gateway, **Gateway Server** thường phù hợp hơn.

## 5. Chọn dependency và Boot–Cloud BOM theo một web stack

Các artifact thường gặp ở các dòng hiện đại:

| Chọn một biến thể | Artifact minh họa |
|---|---|
| Gateway Server WebFlux | `spring-cloud-starter-gateway-server-webflux` |
| Gateway Server Web MVC | `spring-cloud-starter-gateway-server-webmvc` |
| ProxyExchange WebFlux | `spring-cloud-gateway-proxyexchange-webflux` |
| ProxyExchange MVC | `spring-cloud-gateway-proxyexchange-webmvc` |

Các dòng cũ có thể dùng `spring-cloud-starter-gateway`, `spring-cloud-starter-gateway-mvc`, `spring-cloud-gateway-webflux` hoặc `spring-cloud-gateway-mvc`. **Không trộn tên dependency thuộc nhiều release train** rồi hy vọng Maven/Gradle tự chọn đúng.

**Spring Boot BOM** quản lý các thành phần Spring Framework, Reactor, Netty, Jackson, Micrometer... và **Spring Cloud BOM** quản lý Gateway, LoadBalancer, CircuitBreaker, DiscoveryClient... Chúng phải được chọn **theo ma trận tương thích**, không chọn version mới nhất của từng artifact riêng lẻ.

### Kiểm tra classpath

1. Xác định app dùng **reactive** hay **servlet** application type.
2. Kiểm các starters kéo transitive Spring MVC và WebFlux.
3. Kiểm Java bytecode target và JRE trong image.
4. Kiểm dependency Redis, Security, LoadBalancer, CircuitBreaker có hiện diện khi route cần.
5. Kiểm trùng/khác version Reactor Netty hoặc Boot autoconfiguration.
6. Thực thi startup và HTTP smoke test; **compile thành công không chứng minh runtime đúng**.

Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có trên classpath, Boot trong những cấu hình phổ biến ưu tiên **Servlet/MVC application type**. Đặc biệt nguy hiểm nếu bạn định chạy **Gateway Server WebFlux**.

## 6. Gradle: mẫu dependency cho bốn ứng dụng khác nhau

Các đoạn dưới đây giả định project đã cấu hình Spring Boot plugin và **Boot/Cloud BOM tương thích**. **Chọn đúng một** nhóm cho một ứng dụng; các khối mã là ví dụ thay thế nhau, không phải cộng hết vào cùng `build.gradle`.

### Gateway Server WebFlux

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

### Gateway Server Web MVC

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### ProxyExchange WebFlux

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

### ProxyExchange MVC

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **dependency skeleton**, không phải production-ready build. Security resource server/JWT, Redis, CircuitBreaker, DiscoveryClient và tracing chỉ nên bổ sung khi tính năng cần và đã có cấu hình/test tương ứng.

## 7. Maven cũng cần Boot parent/Cloud BOM và executable packaging

Với Maven, cấu hình Spring Boot parent hoặc Boot dependency management, cùng Spring Cloud dependency BOM tương thích. Ví dụ **một phần `pom.xml`**, không đủ để build riêng:

~~~xml
<properties>
  <java.version>21</java.version>
  <spring-cloud.version>RELEASE_TRAIN_MATCHING_BOOT</spring-cloud.version>
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
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
  </dependency>
</dependencies>
~~~

Giá trị `RELEASE_TRAIN_MATCHING_BOOT` chỉ là placeholder: hãy thay bằng một Spring Cloud release train tương thích với Spring Boot baseline. Trong XML, `${spring-cloud.version}` tham chiếu property đã khai báo; không dùng nguyên placeholder khi build. Phải cấu hình **spring-boot-maven-plugin**/**repackage** đúng nếu muốn executable Boot JAR. `mvn package` tạo JAR thường chưa đủ khi plugin thiếu.

## 8. Chọn Java runtime cho executable JAR

Những thông tin cần chốt trước khi build:

| Tham số | Câu hỏi |
|---|---|
| JDK compile | Phiên bản nào chạy Gradle/Maven? |
| Java target bytecode | JAR được compile cho Java mấy? |
| Runtime JRE trong image | Có hỗ trợ class version và BOM đang dùng không? |
| Base image | Có cập nhật security patches, đúng architecture không? |
| JVM flags | Có phù hợp memory/cgroup và GC policy không? |
| Truststore | Java runtime có tin CA của backend/JWK/Redis TLS không? |
| Native libraries | Image architecture và các runtime libraries có đủ không? |

Lỗi kinh điển: JAR build Java 21 nhưng chạy với JRE 17 dẫn tới `UnsupportedClassVersionError`. Ngược lại, **JRE mới hơn không tự bảo đảm một Spring Boot cũ hơn đã được nhà phát hành hỗ trợ**.

### Kiểm tra tại CI

~~~bash
java -version
./gradlew clean test bootJar
ls -lh build/libs/
~~~

Các lệnh minh họa để người học thực hành; bài viết không thực thi build. **Không dùng `-x test` hoặc `-DskipTests` làm đường chính của production pipeline**.

## 9. Tạo executable JAR: `bootJar` khác `jar`

Với Spring Boot Gradle plugin:

~~~groovy
// Tên artifact cố định để Dockerfile dễ COPY.
tasks.named('bootJar') {
    archiveFileName = 'gateway-app.jar'
}
~~~

Build và thử khởi động:

~~~bash
./gradlew clean test bootJar

java -jar build/libs/gateway-app.jar \
  --spring.profiles.active=lab
~~~

Boot executable JAR được đóng gói với launcher và runtime dependencies phù hợp Boot plugin. Một plain `jar` chỉ chứa classes của ứng dụng có thể **không chứa dependencies**, dẫn tới lỗi thiếu class khi `java -jar`.

Với Maven có Boot plugin/repackage tương ứng:

~~~bash
./mvnw verify

# Chọn đúng tên JAR thực tế từ target/.
java -jar target/gateway-app.jar
~~~

`target/gateway-app.jar` là tên ví dụ, không tồn tại nếu `artifactId`/`finalName` khác. Dù dùng Maven hay Gradle, cần chứng minh **application context đã khởi động và route backend chạy đúng**.

## 10. OCI image: Buildpacks và Dockerfile

Một Gateway đã được đóng gói có thể tạo OCI image bằng:

1. **Spring Boot Cloud Native Buildpacks** qua `bootBuildImage`/`spring-boot:build-image`.
2. **Dockerfile** dựa trên JRE runtime tương thích.

Hai cách này không quyết định app dùng Netty hay Tomcat; web stack nằm trong dependencies/config.

### Buildpacks

~~~bash
# Gradle (khi Spring Boot plugin hỗ trợ):
./gradlew bootBuildImage \
  --imageName=registry.example.test/team/gateway-app:lab

# Maven:
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.test/team/gateway-app:lab
~~~

Buildpacks có thể tận dụng caching/layering, hỗ trợ reproducible deployment tốt hơn nếu được quản trị đúng. Tuy vậy, image builder/runtime compatibility, registry credentials và SBOM scanning vẫn cần được kiểm trong CI.

### Tại sao tránh `latest`?

Một tag mutable như `latest` có thể trỏ đến image khác giữa hai lần rollout. Để rollback và audit, ưu tiên **immutable tag theo commit SHA** hoặc **image digest**, đồng thời ghi lại Boot/Cloud BOM, route config revision và kết quả kiểm thử.

## 11. Dockerfile chạy không phải root

Giả sử `bootJar` tạo `build/libs/gateway-app.jar`:

~~~dockerfile
# Java 21 chỉ là ví dụ, phải tương thích runtime baseline dự án.
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/libs/gateway-app.jar /app/app.jar

# Numeric UID/GID, không chạy root.
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Một số điểm cần đánh giá:

- Base image phải được cập nhật/pin digest, quét CVEs và đối chiếu CPU architecture.
- `USER 10001:10001` có thể cần quyền ghi vào `/tmp`, logs/temp và vị trí certificate do app dùng.
- `EXPOSE 8080` chỉ là metadata, không tự publish cổng ra Internet.
- Không copy credentials, keystore password hay private keys vào JAR/image.
- JRE trong image phải đúng bytecode/compiler, không thay bằng runtime “nhẹ hơn” nhưng cũ hơn.
- Nếu chạy **read-only root filesystem**, phải mount writable volume đúng vị trí; không thể coi container filesystem luôn có thể ghi.

Build và run lab:

~~~bash
./gradlew clean test bootJar
docker build -t gateway-app:lab .
docker run --rm -p 8080:8080 gateway-app:lab
~~~

**Bẫy localhost:** `localhost` bên trong container là **chính container đó**, không phải máy host hay một backend container khác. Route `http://localhost:9090` có thể chạy trên IDE nhưng lỗi 502 khi deploy Docker/Kubernetes.

## 12. Container memory: không cấp Xmx bằng memory limit

Một Gateway WebFlux dùng heap **và** Netty **direct memory**; MVC dùng heap, thread stacks, buffer pools, metaspace và nhiều native allocations.

~~~text
Memory limit container: 1024 MiB (ví dụ)
Heap khoảng 55-60%: 560-615 MiB (điểm xuất phát)
Phần còn lại: direct memory, metaspace, thread stacks, TLS, native/JVM
~~~

Đây là **ước lượng minh họa**, không phải tỷ lệ chuẩn cho mọi workload. Trong Netty, streaming và nhiều kết nối có thể làm direct memory tăng; với MVC, worker threads và blocking I/O tạo áp lực khác.

Một JVM flag thường gặp:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
java -jar /app/app.jar
~~~

**Đừng cấu hình `-Xmx=1024m` khi container chỉ có 1 GiB** rồi bỏ qua các vùng khác. Theo dõi RSS/container memory, heap, GC, direct memory, metaspace, file descriptors, threads và connection pool khi tải tăng.

### Đo theo variant

| Variant | Điểm nghẽn hay gặp |
|---|---|
| WebFlux Server | Event-loop blocking, Netty pending acquire, direct memory |
| Web MVC Server | Servlet threads waiting, HTTP client pool/DB pool saturation |
| ProxyExchange WebFlux | Controller blocking, body aggregation, reactive context |
| ProxyExchange MVC | Threads giữ bởi outbound slow calls và body buffering |

**Virtual threads** là một lựa chọn có điều kiện trên các Spring Boot/Servlet versions hỗ trợ, nhưng không làm ProxyExchange MVC trở thành reactive và không xóa giới hạn của HTTP client/DB pool.

## 13. Cấu hình môi trường tách khỏi image

Một image tốt nên triển khai được ở staging/production mà **không build lại để sửa backend host hoặc JWT issuer**. Nguồn cấu hình có thể gồm:

- Spring Boot profiles/property sources;
- Kubernetes **ConfigMap** cho cấu hình không bí mật;
- Kubernetes **Secret**/secret manager cho credentials;
- Externalized route definitions/config repository có kiểm soát quyền;
- Files/mount cho CA truststore, TLS certificates và client keys.

### Ví dụ route Gateway Server WebFlux (namespace thuộc dòng mới)

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  application:
    name: gateway-edge
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: http://catalog.default.svc.cluster.local:8080
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Một số release train dùng prefix `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. MVC có namespace và route DSL khác. **Xác minh effective property binding và actual routes** của đúng bản; đừng khai báo cả hai prefix rồi giả định luôn có cùng route.

Trong ví dụ, URI dùng **Kubernetes Service DNS** trực tiếp, không phải `lb://`. Đích này phụ thuộc Service DNS/networking của Kubernetes, không tự gọi LoadBalancer discovery filter của Gateway.

### Precedence và biến môi trường

Spring Boot hỗ trợ relaxed binding, nhưng regex, map keys, SpEL và route filter args phức tạp có thể bị thay đổi khi chuyển sang tên env variables. Với route động hoặc nhiều filters, hãy ưu tiên cấu hình đã được review/versioned, và kiểm binding bằng integration test. **Đừng nhúng password vào command line hoặc log startup**.

## 14. `lb://` không phải Kubernetes Service DNS

Một route có thể chọn backend theo hai cách khác nhau:

~~~mermaid
flowchart TD
    G["Gateway route URI"] --> S{"Target scheme"}
    S -->|"http://catalog.default.svc:8080"| D["Kubernetes DNS + Service routing"]
    S -->|"lb://catalog-service"| L["Spring Cloud LoadBalancer"]
    L --> DISC["DiscoveryClient / service registry"]
    D --> P["Ready backend instances"]
    DISC --> P
    P --> OUT["Egress network/TLS policy"]
~~~

| URI | Runtime cần | Điều phải kiểm tra |
|---|---|---|
| `http://host:port` | HTTP client + DNS/route | Host, port, timeout |
| Kubernetes Service DNS | Cluster DNS, Service/Endpoints ready | Namespace, targetPort, routing |
| `lb://service-id` | LoadBalancer + DiscoveryClient/resolver tương thích | Service ID và instance list |
| `https://service` | TLS trust, hostname, SNI | CA/cert SAN và renewals |
| `ws://`/`wss://` | WebSocket routing đúng variant | Upgrade, idle timeout, close/reconnect |

**`lb://` là URI scheme do Gateway/LoadBalancer integration hiểu**, không phải scheme chuẩn mà mọi HTTP client tự hỗ trợ. Khi đưa ứng dụng từ local lên cluster, cần xác nhận service ID, discovery provider và quyền đăng ký instances.

**Network policy vẫn cần ngay cả khi service nằm trong registry**: một service được discoverable không có nghĩa bất kỳ user nào cũng được public hóa nó qua Gateway.

## 15. Runtime dependencies: Security, Redis, CircuitBreaker và Retry

Những features trong mô tả module có thể tạo yêu cầu riêng lúc chạy:

| Tính năng | Phụ thuộc và cấu hình cần xác minh | Sự cố điển hình |
|---|---|---|
| **JWT authentication** | Spring Security đúng WebFlux/MVC stack, decoder, issuer/JWK reachability, audience/scopes | 401/403 ngoài dự kiến |
| **Redis RequestRateLimiter** | Redis client/integration đúng version, Redis DNS, TLS/auth, fail policy | Redis unavailable/429/5xx |
| **CircuitBreaker** | CircuitBreaker/Resilience4j module và filter factory tương thích, fallback URI | Factory không tồn tại, fallback sai |
| **Retry** | Retry filter/client policy, attempts/backoff, body replay/idempotency | Duplicate POST, retry storm |
| **Service discovery** | LoadBalancer + provider, registry metadata, health | `lb://` không chọn được instance |
| **Local response cache** | Cache support, TTL, private/public policy | Dữ liệu stale/rò tenant |
| **TLS/mTLS outbound** | Truststore và client identity khi cần | `SSLHandshakeException` |
| **Observability** | Actuator/Micrometer/tracing exporter | Dashboard không có dữ liệu |
| **Dynamic routes** | Route source/persistence/refresh và per-node reconciliation | Các Gateway nodes route khác nhau |

Không khẳng định mọi dependency trong bảng đều phải thêm thủ công: một số starter có thể kéo transitive. **Điều quan trọng là verify classpath, bean/factory và hành vi runtime thật**.

### Không làm Redis thành liveness mặc định

Redis rate limiter có thể mất kết nối mà Gateway vẫn có những routes còn phục vụ được. Nếu liveness yêu cầu Redis healthy, Redis outage có thể làm **mọi Gateway Pod restart đồng loạt**, gây thêm outage. Chọn readiness/security failure policy theo nghiệp vụ và tách monitoring downstream khỏi liveness.

## 16. TLS: ba chặng và trust boundary

Mô hình edge phổ biến:

~~~mermaid
flowchart LR
    C["Client HTTPS"] --> I["Ingress / CDN / LB TLS"]
    I -->|"HTTP hoặc HTTPS"| G["Gateway"]
    G -->|"HTTPS/mTLS hoặc private HTTP"| B["Backend"]
~~~

Ba chặng cần quyết định riêng:

1. Client → ingress: public certificate, Host/SNI, HTTP/2/ALPN theo support.
2. Ingress → Gateway: mTLS/TLS hoặc private link với network isolation.
3. Gateway → backend: TLS verification, hostname/cert SAN, outbound truststore và client certificate khi dùng mTLS.

**Không sửa lỗi TLS bằng trust-all hoặc vô hiệu hóa hostname verification.** Truststore trong container có thể khác máy developer; dùng CA được phê duyệt và kiểm certificate rotation.

### Forwarded headers

Sau termination, Gateway có thể nhận traffic HTTP nội bộ nhưng public URL là HTTPS. `Forwarded` và `X-Forwarded-Proto`/`Host`/`For` có thể ảnh hưởng redirect, CORS hoặc client IP.

- Chỉ tin forwarded headers qua **proxy đáng tin**.
- Ingress phải strip/overwrite headers tự đặt bởi client nếu dùng chúng làm tín hiệu trusted.
- Kiểm `server.forward-headers-strategy` theo Boot/runtime variant.
- Không dùng raw `X-Forwarded-For` để cấp quyền hoặc KeyResolver IP nếu chưa xác định trust chain.
- Không forward `Authorization`/`Cookie` sang service không thuộc audience/trust boundary.

## 17. Startup, readiness và liveness: ba trạng thái khác nhau

Trong Kubernetes:

| Probe | Hỏi gì? | Kết quả khi fail |
|---|---|---|
| **startupProbe** | Ứng dụng đã hoàn thành startup chưa? | Cho phép khởi động lâu trước khi liveness kiểm tra |
| **readinessProbe** | Pod có nên được route traffic mới không? | Gỡ khỏi endpoints sẵn sàng |
| **livenessProbe** | Tiến trình có cần restart không? | Restart container |

Spring Boot Actuator có hỗ trợ Kubernetes probes. Trong các phiên bản hỗ trợ, cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

có thể giúp đưa các health groups ra **cổng chính** ở `/livez` và `/readyz`. **Phải xác minh đường dẫn trên version thực**, nhất là khi management port và HTTP application port tách nhau.

### Vì sao probe trên management port có thể gây nhầm?

Management server có thể tiếp tục trả health 200 trong khi **cổng ứng dụng chính** đã ngưng phục vụ đúng. Probe trên main port giúp kiểm kết nối sát đường traffic hơn. Tuy vậy, `/readyz` không tự chứng minh tất cả route/backend đều tốt.

**Không đưa mọi backend health vào liveness**. Liveness phải tránh phụ thuộc tạm thời bên ngoài khiến cluster rơi vào restart loop. Readiness có thể dùng các điều kiện thật sự bắt buộc để an toàn phục vụ, kèm failure policy được xác định rõ.

## 18. Kubernetes Deployment/Service minh họa

Manifest dưới đây cho một Gateway có ba replicas, rolling update và probes trên cổng HTTP ứng dụng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway-edge
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: gateway-edge
  template:
    metadata:
      labels:
        app: gateway-edge
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: gateway
          image: registry.example.test/edge/gateway:sha-EXAMPLE
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=60.0"
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: temp
              mountPath: /tmp
      volumes:
        - name: temp
          emptyDir:
            sizeLimit: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-edge
spec:
  selector:
    app: gateway-edge
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### Cần sửa trước khi dùng production

- `image` là placeholder; thay bằng image digest được ký/quản lý.
- Resource sizing và probe intervals cần đo theo startup, traffic và SLO.
- `/livez` và `/readyz` không tồn tại nếu chưa cấu hình Actuator phù hợp.
- `readOnlyRootFilesystem` yêu cầu mount mọi đường dẫn phải ghi, không chỉ `/tmp` nếu code còn dùng nơi khác.
- Chưa có NetworkPolicy, Ingress/TLS, Secret/ConfigMap, HPA, PodDisruptionBudget hoặc RBAC.
- `maxUnavailable: 0` tránh chủ động giảm số ready pods khi rollout theo strategy, nhưng **không bảo đảm zero dropped requests**.
- Nếu dùng management port riêng, phải kiểm health trên main port vẫn phản ánh trạng thái cần thiết.

## 19. Graceful shutdown, drain và rolling update

Ở Spring Boot hỗ trợ graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kubernetes khi xóa Pod có thể ngưng gửi traffic mới sau khi endpoint readiness thay đổi, nhưng việc lan truyền endpoint và load balancer state **không tức thời**.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant I as Ingress/Service
    participant G as Gateway Pod
    participant C as Client
    K->>G: SIGTERM / termination
    G->>G: Bắt đầu graceful shutdown
    K->>I: Cập nhật endpoints theo trạng thái Pod
    I-->>G: Có thể còn request trong lúc lan truyền
    G-->>C: Hoàn tất request đang chạy nếu kịp
    G->>G: Cleanup và đóng connections
    K-->>G: SIGKILL khi hết termination grace
~~~

### Điều không được giả định

- `server.shutdown=graceful` không đảm bảo mọi WebSocket kéo dài nhiều giờ sẽ hoàn tất.
- `terminationGracePeriodSeconds=45` không có nghĩa mọi upload 2 GiB sẽ kết thúc trong 45 giây.
- Rolling update thành công không bảo đảm không có retry/connection reset ở client.
- `preStop: sleep` có thể hữu ích trong một số ingress nhưng cũng tiêu tốn grace budget; không thêm máy móc.
- Backend POST đã commit có thể tạo side effect dù client nhận connection reset; cần idempotency.

### Phục hồi cho kết nối dài

| Traffic | Contract cần có |
|---|---|
| WebSocket | Reconnect/backoff, session recovery và message dedup nếu cần |
| SSE | Heartbeat, reconnect, `Last-Event-ID` khi backend hỗ trợ |
| Upload file | Resumable parts/offset/checksum, partial cleanup |
| Download file | HTTP Range/ETag/checksum khi thích hợp |
| POST nghiệp vụ | Idempotency key và deduplication do backend thực thi |

## 20. Ingress và Gateway có thể là hai lớp proxy liên tiếp

Một deployment thực tế:

~~~text
Client
  -> CDN/WAF
  -> Ingress / L7 load balancer
  -> Spring Cloud Gateway
  -> Kubernetes Service hoặc DiscoveryClient
  -> Backend
~~~

Mỗi lớp có **timeout, retries, request-size limit, hop-by-hop headers, TLS** và đôi khi body buffering.

| Loại request | Kiểm tra trước khi public |
|---|---|
| JSON GET/POST | Host/path rewrite, CORS, auth, deadlines, 401/403/429/5xx |
| Multipart upload | Ingress body-size, buffering, Content-Type boundary, cancel |
| Large download | 206/Range/ETag, length, streaming, checksum |
| SSE | Flush từng event, heartbeat, idle timeout, proxy buffering |
| WebSocket | Upgrade handshake, ws/wss, idle timeout, reconnect/drain |
| gRPC/HTTP/2 | ALPN, backend protocol, variant support end-to-end |
| Retry | Tổng attempts qua ingress + Gateway + HTTP client |
| TLS | Public/inner certs, SNI, truststore, renewal |

**Một `curl GET` trả 200 không chứng minh SSE/WebSocket/multipart đã đúng**, vì reverse proxy phía trước có thể buffer body hoặc bỏ Upgrade headers.

## 21. Bảo mật image, runtime và control plane

Checklist thiết yếu:

1. Container chạy non-root, drop capabilities và dùng read-only filesystem khi có thể.
2. Image scanning, dependency vulnerability audit, SBOM/provenance và immutable tags/digests.
3. Secrets ngoài image/JAR, RBAC nghiêm ngặt và rotation policy.
4. TLS/mTLS đúng trust boundaries, không vô hiệu certificate validation.
5. Network ingress/egress allowlists; chống SSRF từ dynamic route URI.
6. Bảo vệ Actuator/Prometheus; không expose Gateway route mutation endpoints công khai.
7. Spring Security đúng variant: reactive `SecurityWebFilterChain` hoặc servlet `SecurityFilterChain`.
8. Chỉ forward auth/session/tenant headers theo trust contract; không tin header user tự tạo.
9. Giới hạn request body, concurrency, retry attempts và connection timeout.
10. Audit route/security policy change, nhưng không log JWT/cookie/API key/raw payload nhạy cảm.

**Route predicate chọn tuyến, không cấp quyền truy cập.** Một route `Host=admin.example.test` hoặc `Path=/api/admin/**` không thay thế authentication/authorization.

## 22. Metrics và tracing phải được bật theo web stack thật

Sau deploy, quan sát tối thiểu:

| Câu hỏi | Số liệu |
|---|---|
| Gateway có nhận traffic không? | Inbound HTTP RPS và Gateway routed RPS |
| Route nào lỗi? | 401/403/429/5xx theo route, status |
| Người dùng bị chậm ở đâu? | Client TTFB/TTLB, Gateway P95/P99, backend tracing |
| JVM/Netty/Servlet có bão hòa? | Heap/direct memory, GC, threads/event-loop, pool |
| Retry đang nhân tải? | Outbound attempts vs routed requests |
| Breaker/limiter hoạt động đúng? | Open/fallback rate, quota decisions, Redis health |
| Pods có được scrape? | Prometheus `up` per instance, deployment revision |
| Routes có nhất quán giữa replicas? | Route config revision/health, per-node effective routes |

Không mặc định cùng tên meter cho Gateway Server WebFlux, Server Web MVC và ProxyExchange. Ở một số bản WebFlux, `spring.cloud.gateway.requests` là route-level timer; `http.server.requests` là inbound server metric. Requests bị security chặn trước route **có thể không nằm trong route-level timer**.

**Không gắn raw URL, user ID, JWT, cookie hay trace ID thành metric labels** vì cardinality và dữ liệu nhạy cảm.

## 23. Native image/AOT: định dạng chạy tùy chọn

Spring Boot có AOT/native image workflow cho những bản và dependencies hỗ trợ. **Native executable không phải Gateway variant thứ năm**.

Khi cân nhắc native:

- Phải có GraalVM/toolchain/plugin phù hợp Boot release.
- Kiểm Spring Cloud Gateway variant đang chọn có **supported native surface** hay không.
- Dynamic route loading, reflection, SpEL, SSL, DNS, Redis, CircuitBreaker và custom filters có thể cần điều chỉnh/hints hoặc không được hỗ trợ đầy đủ.
- Đo startup, RSS, latency và correctness trên **native binary thật**, không suy từ JVM JAR test.
- Có fallback/rollback về JVM image nếu ứng dụng có dynamic features chưa được chứng minh.

Đường cơ sở an toàn để học và triển khai thường là **executable JVM JAR/OCI image**; thử native khi đã có yêu cầu cụ thể và compatibility matrix rõ ràng.

## 24. Matrix smoke tests cho từng biến thể

| Kiểm tra | Server WebFlux | Server Web MVC | ProxyExchange WebFlux | ProxyExchange MVC |
|---|---|---|---|---|
| Boot khởi động với classpath đúng | Có | Có | Có | Có |
| HTTP runtime đúng | Reactor Netty | Servlet | WebFlux runtime | Servlet |
| Routes/handlers được đăng ký | Gateway route engine | MVC routing | Controller | Controller |
| Predicate/HTTP mapping | Reactive predicates | MVC predicates | `@GetMapping`... | `@GetMapping`... |
| Path/header transforms | Reactive filters | MVC handler filters | Controller/client | Controller/client |
| Security đúng API | Reactive chain | Servlet chain | Reactive chain | Servlet chain |
| CircuitBreaker/Redis | Theo Gateway support/deps | Theo MVC support/deps | Tích hợp riêng | Tích hợp riêng |
| `lb://` | Kiểm LoadBalancer/discovery | Kiểm LoadBalancer/discovery | Không tự giả định | Không tự giả định |
| Health probes/readiness | Test | Test | Test | Test |
| HTTP 401/403/429/5xx | Test | Test | Test | Test |
| TLS, WebSocket, SSE | Test end-to-end | Test end-to-end | Theo khả năng app | Theo khả năng app |
| Graceful shutdown | Test | Test | Test | Test |

**Unit test `MockMvc` của Server MVC không chứng minh Netty route của WebFlux Server đã chạy.** Dùng `WebTestClient` cho WebFlux và Servlet test tools cho MVC, thêm HTTP end-to-end qua backend test khi cần kiểm DNS/TLS/filter routing.

## 25. CI/CD và release metadata

~~~mermaid
flowchart TD
    S["Source + BOM + config revision"] --> U["Unit tests + security checks"]
    U --> I["HTTP integration tests"]
    I --> B["Build executable JAR / OCI image"]
    B --> V["SBOM/scan/signature/provenance"]
    V --> ST["Deploy staging + smoke tests"]
    ST --> CA["Canary / rolling update"]
    CA --> M["Monitor errors, latency, traffic"]
    M --> D{"SLO & security invariants PASS?"}
    D -->|Có| P["Promote image digest"]
    D -->|Không| R["Rollback + incident review"]
~~~

Nên lưu cùng release:

- Git SHA/image digest;
- Spring Boot, Spring Cloud release train và Gateway variant;
- Java build/runtime version;
- Route configuration revision;
- TLS/Redis/Discovery dependency schema (không chứa secrets);
- Deployment environment/namespace/replica count;
- Test reports, SLO before/after canary;
- Rollback image và người phê duyệt.

**Image revision và route config revision có thể đổi độc lập.** Một dynamic route dùng filter mới mà image cũ không hỗ trợ sẽ gây lỗi dù image trước đó khỏe; cần compatibility checks cho cả hai.

## 26. Lab: JAR → image → smoke tests

Giả định một backend echo có `GET /catalog/items/42`; Gateway nhận `GET /api/catalog/items/42` và bỏ prefix `/api` trước khi forward.

### Bước 1 — Chọn hai project lab độc lập

- Project A: **Server WebFlux** với reactive routes.
- Project B: **Server Web MVC** với MVC routes.

Không gộp hai starters chỉ để “so sánh”. Cùng backend/HTTP contract, cùng TLS/CPU/memory limits nếu benchmark.

### Bước 2 — Build và chạy trên JVM tương thích

~~~bash
java -version
./gradlew clean test bootJar
java -jar build/libs/gateway-app.jar \
  --spring.profiles.active=lab
~~~

### Bước 3 — Xác nhận Gateway và probes

~~~bash
curl -i 'http://localhost:8080/api/catalog/items/42'
curl -i 'http://localhost:8080/livez'
curl -i 'http://localhost:8080/readyz'
~~~

Nếu `/livez`/`/readyz` trả 404, kiểm property probes/path mapping của Spring Boot version trước khi kết luận app không khỏe.

### Bước 4 — Test method/path không được phép

~~~bash
curl -i -X DELETE \
  'http://localhost:8080/api/catalog/items/42'
curl -i 'http://localhost:8080/no-route-here'
~~~

Status có thể là 404/405/401/403 tùy route, Spring Security và handler mapping. Điều phải chứng minh: requests không hợp lệ **không bị forward nhầm vào backend**.

### Bước 5 — Đóng gói image

~~~bash
docker build -t gateway-app:lab .
docker run --rm -p 8080:8080 gateway-app:lab
~~~

Kiểm DNS/network khi backend là container khác. **`localhost` ở container không tự truy cập máy host**.

### Bước 6 — Thử phụ thuộc production-like

Nếu có Redis limiter, thử vượt quota và Redis outage trong **lab**; nếu có `lb://`, kiểm instance selection; nếu có TLS, thử certificate hợp lệ và không hợp lệ; nếu có JWT, kiểm token thiếu/sai scope/audience.

### Bước 7 — Thử Kubernetes test cluster

~~~bash
kubectl apply -f gateway-deployment.yaml
kubectl rollout status deployment/gateway-edge
kubectl get pods -l app=gateway-edge
kubectl get endpointslice \
  -l kubernetes.io/service-name=gateway-edge
~~~

Manifest name, cluster RBAC và Service labels phải thực sự phù hợp. Các lệnh chỉ là bài thực hành; không chạy trên production nếu không được phép.

### Bước 8 — Kiểm rollout/drain

1. Gửi GET requests liên tục với tải thấp.
2. Rollout canary image; ghi deployment revision.
3. Quan sát readiness transitions, 5xx, dropped connections và P99.
4. Nếu có SSE/WebSocket, kiểm reconnect/resume.
5. Kiểm SIGTERM/grace budget và số requests bị mất.
6. Rollback nếu SLO hoặc security tests fail.

### Bước 9 — Báo cáo kết quả theo variant

| Kết quả | Server WebFlux | Server Web MVC |
|---|---|---|
| Java/runtime version | Đo thực | Đo thực |
| Startup + ready time | Đo thực | Đo thực |
| RSS, heap/direct, thread/event-loop | Đo thực | Đo thực |
| Successful RPS | Đo thực | Đo thực |
| P95/P99, 401/403/429/5xx | Đo thực | Đo thực |
| TLS/SSE/WebSocket/rollout | PASS/FAIL | PASS/FAIL |

**Không điền số giả định thành benchmark thật**. Một kết quả chỉ so sánh công bằng khi backend, request mix, TLS, cache, resource limits và load generator được kiểm soát.

## 27. Troubleshooting theo triệu chứng triển khai

| Triệu chứng | Nguyên nhân đáng kiểm | Hành động |
|---|---|---|
| `UnsupportedClassVersionError` | JRE thấp hơn bytecode | Khớp JDK compile/runtime |
| `NoSuchMethodError` hoặc `ClassNotFoundException` | Lệch Boot/Cloud/Reactor versions | Kiểm BOM/dependency tree |
| Server WebFlux startup lỗi sau thêm MVC starter | Web stack/classpath conflict | Chọn đúng một server variant |
| Server MVC custom filter không compile | Dùng reactive `GatewayFilter` API | Chuyển sang MVC handler filter |
| ProxyExchange không inject được | Sai module MVC/WebFlux | Kiểm dependency và controller stack |
| Health 200 nhưng routes 404 | Route config namespace sai, route chưa load | Kiểm effective routes/handler mappings |
| `lb://` 503 | Thiếu LoadBalancer/discovery/instances | Kiểm service IDs và registry |
| Container gọi backend localhost → 502 | Localhost trỏ container | Dùng Service DNS/target đúng |
| Backend HTTPS handshake fail | CA trust/SNI/hostname sai | Sửa truststore/certificate, không trust-all |
| JWT mọi request 401 | JWK/issuer/audience/security config | Kiểm auth integration/egress |
| Redis limiter không chạy | DNS/TLS/password/module sai | Kiểm Redis health/failure policy |
| CircuitBreaker filter không tồn tại | Thiếu factory/dependency | Kiểm variant/bản hỗ trợ |
| Pod OOMKilled | Heap + direct/native vượt limit | Đo RSS, giảm buffering/tăng hợp lý memory |
| P99 tăng sau load | Blocking event loop hoặc Servlet pool saturation | Profile đúng stack |
| Readiness fail nhưng app khởi động | Probe path/port hoặc startup timing sai | Kiểm endpoints/startupProbe |
| Management health xanh nhưng main port không nhận | Probe chỉ management port | Probe main port/readiness |
| WebSocket ngắt khi deploy | Không có reconnect/drain strategy | Thiết kế client resume |
| SSE bị buffer | Ingress proxy buffering/body transform | Kiểm từng hop |
| 413 upload | Ingress/Gateway/backend size limit | Đặt giới hạn theo policy |
| Image deploy sai version | Mutable tag hoặc registry cache | Pin digest/immutable tag |
| Secrets lộ qua env/config/logs | Logging hoặc RBAC sai | Redact/rotate/restrict |
| Canary routes khác nhau giữa nodes | Config revisions/refresh drift | Reconcile/rollback |
| Metrics route-level trống | Sai meter, chưa match route, variant khác | Kiểm Actuator/runtime |

### Sáu câu hỏi khoanh vùng

1. **Artifact** có đúng Java runtime, BOM, image digest không?
2. **Variant** có đúng WebFlux/Netty, MVC/Servlet hoặc ProxyExchange không?
3. **App main port** và readiness/liveness có thực sự hoạt động không?
4. **Route** có load và match đúng predicate/filter order không?
5. **Outbound** có đi được qua DNS/discovery/TLS/Redis/JWK không?
6. **Policy và kết quả** có đúng 401/403/429/5xx/retry/fallback/tracing không?

**Không “sửa nhanh” bằng cách bật `permitAll` toàn cục, tắt TLS verification, expose mọi Actuator endpoint hoặc tăng timeout vô hạn.**

## 28. Checklist trước khi phát hành

### Variant và build

- [ ] Đã chọn rõ **Server WebFlux**, **Server Web MVC**, **ProxyExchange WebFlux** hoặc **ProxyExchange MVC**.
- [ ] Starter đúng release train; Boot và Cloud BOM tương thích.
- [ ] Không trộn Servlet/Reactive Gateway Server ngoài mô hình hỗ trợ.
- [ ] Không nhầm WebFlux `GatewayFilter` với MVC handler filter.
- [ ] Không nhầm ProxyExchange với Gateway Server filters/route locators.
- [ ] Java runtime tương thích JDK compile/Boot baseline.
- [ ] Build executable JAR thực sự, không chỉ plain JAR.
- [ ] CI chạy unit/integration/security tests trước khi publish image.
- [ ] Image digest, release metadata, scan/SBOM và rollback target sẵn sàng.

### Container, config và TLS

- [ ] Container non-root, capabilities tối thiểu, write paths đúng.
- [ ] Container CPU/memory limits dựa trên đo đạc; không đặt Xmx bằng toàn memory limit.
- [ ] Heap, direct memory, RSS, threads và connection pools được quan sát theo stack.
- [ ] Secrets ngoài image, ConfigMap/Secret/profiles đúng environment.
- [ ] Routes được bind đúng prefix của Gateway version.
- [ ] Không còn `localhost` URI dùng sai khi deploy container.
- [ ] Biết khi nào dùng Kubernetes DNS, khi nào dùng `lb://`.
- [ ] Egress/SSRF allowlist, JWT, TLS/mTLS truststore và certificate rotation được kiểm.
- [ ] Không log raw token/cookie/API key hoặc payload nhạy cảm.

### Kubernetes và vận hành

- [ ] Startup/readiness/liveness probes đúng path và đúng main/management port.
- [ ] Liveness không phụ thuộc tất cả backends/Redis.
- [ ] Có số replicas/headroom phù hợp SLO, rolling update và rollback strategy.
- [ ] Đã test SIGTERM/graceful shutdown/endpoint propagation.
- [ ] SSE/WebSocket reconnect và upload/download dài có recovery strategy.
- [ ] Ingress hỗ trợ đúng CORS, headers, HTTP/2/TLS, WebSocket/SSE, body size và timeouts.
- [ ] Authentication đúng SecurityFilterChain theo stack, backend authorization độc lập.
- [ ] Retry, breaker, Redis limiter, cache và discovery failure policies đã test.
- [ ] Actuator/Prometheus không bị expose ngoài phạm vi quản trị.
- [ ] Metrics, tracing, route IDs và deployment versions đủ để điều tra sự cố.
- [ ] Smoke tests gồm GET/POST/401/403/429/5xx, route miss, TLS và shutdown.
- [ ] Không coi build/startup/health xanh là bằng chứng hệ thống đã đủ an toàn.

## 29. Bài tập áp dụng

**Bài 1 — Chọn biến thể.** Một đội có Spring MVC BFF gồm 5 controller chỉ cần forward GET/POST tới backend, nhưng chưa cần Gateway route engine. So sánh ProxyExchange MVC với Gateway Server WebFlux theo chức năng, vận hành và dependencies.

**Bài 2 — Sửa classpath.** Một ứng dụng Server WebFlux bắt đầu boot lỗi sau khi thêm `spring-boot-starter-web`. Viết quy trình kiểm dependency graph, Boot application type và embedded HTTP server thật.

**Bài 3 — JAR/JRE.** Build Java target 21 rồi chạy trên JRE 17 trong Docker image. Dự đoán lỗi và thiết kế kiểm soát ở CI.

**Bài 4 — Readiness.** Management port trả health UP nhưng main port 8080 bị lỗi. Thiết kế probe phản ánh khả năng nhận traffic và giải thích vì sao Redis không nên nằm trong liveness mặc định.

**Bài 5 — Service discovery.** Route `lb://catalog-service` không tìm thấy instances, trong khi Kubernetes Service DNS hoạt động. So sánh hai hướng giải quyết không trộn hai loại URI.

**Bài 6 — Outage Redis.** Một route nhạy cảm yêu cầu limiter fail-closed, route public khác có chính sách khác. Test startup, readiness, 429/503 và recovery khi Redis unavailable.

**Bài 7 — WebSocket rollout.** Gateway đang giữ nhiều WebSocket sessions, rolling update làm ngắt kết nối. Thiết kế reconnect, state recovery, grace budget và test k6/WebSocket client phù hợp.

**Bài 8 — Hardening.** Image chạy root, chứa Redis password trong `application-prod.yml`, expose `/actuator/**` công khai. Liệt kê các thay đổi bắt buộc và cách kiểm chứng.

**Bài 9 — So sánh runtime.** Đo WebFlux Server và MVC Server ở cùng request mix, backend, TLS, resources. Nêu lý do không được so chỉ một chỉ số RPS hoặc chỉ startup time.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — các phần Server WebFlux, Server Web MVC, Proxy Exchange, GatewayFilter và deployment/Actuator theo version.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — variants và release train.
- [Spring Cloud Project](https://spring.io/projects/spring-cloud) — compatibility giữa Spring Boot và Spring Cloud BOM.
- [Spring Boot — Packaging](https://docs.spring.io/spring-boot/reference/packaging/index.html) — executable archives, build plugins và phân phối.
- [Spring Boot — Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html) — Buildpacks và Dockerfiles.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — graceful shutdown và requests còn xử lý.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Kubernetes probes, health groups, security và endpoint exposure.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — profiles, env và config import.
- [Spring Boot — Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html) — AOT/native constraints.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — reactive `SecurityWebFilterChain`.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — servlet `SecurityFilterChain`.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — replicas và rolling updates.
- [Kubernetes — Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — startup/readiness/liveness.
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) — SIGTERM và termination grace.
- [Kubernetes — Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) — non-root/capabilities.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — outbound URI allowlist và network controls.

**Ghi nhớ:** Trong Spring Cloud Gateway, **biến thể quyết định web stack và các route/filter APIs**, còn **JAR/OCI image chỉ là cách phân phối**. **Server WebFlux** dùng reactive Netty pipeline; **Server Web MVC** dùng Servlet/WebMvc.fn; **ProxyExchange WebFlux/MVC** là controller-style proxy, không tự có chính sách filter của Gateway Server. Để triển khai an toàn, cần khóa Boot–Cloud BOM, dùng Java runtime phù hợp, build executable JAR, chạy container non-root, tách secrets/config, xác minh DNS/`lb://`/TLS, thiết kế probes và graceful rollout, rồi **kiểm thử đúng variant với request, auth, limiter, retry, TLS và kết nối dài trong môi trường triển khai thật**. Một image build thành công **chưa chứng minh Gateway đã sẵn sàng hoặc an toàn để public**.
