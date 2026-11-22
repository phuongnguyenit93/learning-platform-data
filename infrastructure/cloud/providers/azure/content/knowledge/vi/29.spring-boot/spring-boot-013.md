# Đóng gói, health probe và graceful shutdown trên Azure

Một ứng dụng **Spring Boot** chạy ổn định trên máy phát triển chưa chắc hoạt động an toàn khi Azure khởi động thêm replica, triển khai phiên bản mới, chuyển traffic, thay node hoặc gửi tín hiệu dừng tiến trình. Nếu gói triển khai sai, ứng dụng có thể thiếu thư viện hoặc không lắng nghe đúng cổng. Nếu health probe sai, hệ thống có thể chuyển request vào một instance chưa sẵn sàng hoặc restart liên tục một instance lành mạnh. Nếu không có **graceful shutdown**, một lần rolling deployment có thể làm rớt request đang xử lý, cắt kết nối tới cơ sở dữ liệu hoặc xử lý trùng một đơn hàng.

Bài thuộc chương **Spring Boot trên Azure** của module **CLOUD_PROVIDERS_AZURE**. Trong hành trình học Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ, dữ liệu, bảo mật, giám sát và kiểm soát chi phí, bài này tập trung vào ba hợp đồng vận hành gắn bó chặt chẽ: **artifact có thể khởi chạy**, **tín hiệu sức khỏe trung thực** và **kết thúc ứng dụng có kiểm soát**. Chúng ta xem xét Azure App Service, Azure Container Apps (ACA), Azure Kubernetes Service (AKS), Azure Virtual Machines và lưu ý khác biệt với Azure Functions.

**Phạm vi:** các ví dụ hướng tới Java 17/21, Spring Boot 3.x và môi trường Linux/container; phải xác minh phiên bản JDK, Spring Boot, image, runtime/SKU và khả năng nền tảng đang được hỗ trợ ở thời điểm triển khai. Những số giây, CPU, RAM, số replicas và cổng bên dưới là **giả định để học**, không phải cấu hình mặc định tốt nhất cho mọi hệ thống. Không triển khai thử nghiệm phá hoại trên production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Đóng gói Spring Boot thành **executable JAR**, phân biệt JAR, WAR và **OCI container image**.
- Xây Dockerfile an toàn cho JDK/JRE, non-root user, cổng HTTP và JVM memory.
- Giải thích **liveness, readiness, startup** và khác biệt giữa kiểm tra process với kiểm tra nghiệp vụ.
- Cấu hình Spring Boot Actuator health probes, kiểm tra qua cổng ứng dụng, tránh lộ chi tiết nhạy cảm.
- Đặt **startup, readiness và liveness probes** thích hợp cho AKS và Container Apps.
- Hiểu App Service Health Check, startup warm-up và health path của Java hosting.
- Giải thích **SIGTERM**, lifecycle shutdown của Spring, connection draining và thời hạn kết thúc.
- Phối hợp **terminationGracePeriodSeconds**, preStop, readiness và rolling deployment trong Kubernetes.
- Thiết kế shutdown cho REST API, HTTP streaming và các Service Bus/Kafka/background workers.
- Xử lý race conditions: request đến khi pod đang thoát, connection pool, task đang chạy, duplicate messages.
- Thiết kế CI/CD kiểm chứng artifact, probe behavior, image security, rolling rollout và rollback.
- Đo downtime, startup duration, lỗi 5xx, request interruption và cost của cấu hình high availability.

## 2. Ba hợp đồng vận hành

~~~mermaid
flowchart LR
    A[Git + build] --> B[Executable JAR hoặc OCI image]
    B --> C[Azure host khởi động JVM]
    C --> D[Startup probe / warm-up]
    D --> E[Readiness cho nhận traffic]
    E --> F[HTTP requests + background work]
    F --> G[SIGTERM / scale-in / deployment]
    G --> H[Ngừng nhận việc mới]
    H --> I[Drain + commit/checkpoint]
    I --> J[Exit trong deadline]
~~~

Ba hợp đồng:

1. **Artifact contract:** bản build chứa đúng bytecode/dependencies, chạy đúng Java version và cấu hình, reproducible và có provenance.
2. **Health contract:** nền tảng nhận đúng tín hiệu liệu tiến trình còn sống, đã khởi động hay đủ điều kiện nhận traffic.
3. **Shutdown contract:** khi nền tảng yêu cầu dừng, tiến trình ngừng nhận việc mới, hoàn tất hoặc bàn giao việc đang làm trong deadline, rồi thoát theo cách có thể dự đoán.

Chúng liên quan nhau. Dockerfile khai báo sai port có thể khiến readiness probe thất bại dù ứng dụng vẫn chạy. Liveness probe phụ thuộc database có thể restart tất cả pods khi Azure SQL chậm. Graceful shutdown có hiệu lực nhưng thời hạn termination chỉ 5 giây vẫn có thể làm transaction bị cắt.

## 3. So sánh đường triển khai lên Azure

| Nền tảng | Artifact điển hình | Cách kiểm tra sức khỏe | Cơ chế dừng cần quan tâm |
|---|---|---|---|
| **Azure App Service (Java SE)** | Executable JAR | App Service Health Check, app logs, Actuator | App restart/slot swap/scale-in, runtime termination và warm-up |
| **App Service custom container** | OCI image | Health Check với HTTP path; container startup | Container signal/lifecycle theo hosting |
| **Azure Container Apps** | OCI image | HTTP/TCP startup/readiness/liveness probes theo cấu hình | Revision/replica termination, draining/scale-in |
| **AKS** | OCI image qua Kubernetes Deployment | startupProbe, readinessProbe, livenessProbe | Pod termination, SIGTERM, preStop, grace period |
| **Azure Virtual Machines / VMSS** | JAR hoặc OCI image | Process/systemd, Load Balancer/Application Gateway probe | systemd stop signal, timeouts, rolling VM updates |
| **Azure Functions Java** | Function package hoặc hình thức được hỗ trợ | Function host/runtime health và trigger behavior | Host lifecycle và trigger checkpoint/retry, không giống nguyên một Spring MVC server |

**Không dùng chung một tệp probe YAML cho tất cả nền tảng.** Spring Boot có thể giữ các HTTP endpoints nhất quán, nhưng các control-plane settings, termination deadline và health semantics khác nhau.

## 4. Mẫu ứng dụng dùng xuyên suốt

Giả sử **orders-api** là REST API:

- **GET /api/orders/{id}** đọc đơn hàng qua Azure Database for PostgreSQL.
- **POST /api/orders** ghi đơn và tạo outbox event.
- **/actuator/health/liveness** dùng cho liveness.
- **/actuator/health/readiness** dùng cho readiness.
- Database credentials được cấp qua managed identity/secret store phù hợp.
- Có thể triển khai hai replicas trở lên; session và trạng thái đơn **không giữ duy nhất trong RAM**.

~~~text
Client -> Azure ingress -> orders-api instances
                           |
                           +-- PostgreSQL
                           +-- Service Bus (qua outbox worker)
                           +-- Azure Monitor / Application Insights
~~~

Mục tiêu: khi deploy phiên bản mới, **instance cũ ngừng nhận việc mới**, những requests đang xử lý hoàn thành trong giới hạn, instance mới chỉ nhận traffic khi readiness thực sự đạt. Điều này không tự bảo đảm **exactly-once** ở database/queue; các thao tác nghiệp vụ vẫn cần transaction/idempotency.

## 5. Chọn JAR, WAR hay container image

| Định dạng | Cơ chế chạy | Khi phù hợp | Rủi ro |
|---|---|---|---|
| **Executable JAR** | JVM chạy Spring Boot embedded server | App Service Java SE, VM hoặc base cho image | JDK/host runtime và artifact version phải phù hợp |
| **WAR** | Servlet container hỗ trợ định dạng WAR | App cũ hoặc hosting servlet riêng | Container/version compatibility, context path |
| **OCI image** | Container runtime khởi chạy Java process | Container Apps, AKS, App Service containers | Base image patches, user permissions, signal/PID 1 |
| **Native executable** nếu đã chọn công nghệ tương ứng | Native image/runtime tương thích | Trường hợp startup/footprint có lợi | Build, library compatibility, debugging, observability khác |

Một **Spring Boot executable JAR** có thể chạy với **java -jar**, thường đã chứa dependency runtime. Một **plain JAR** thiếu dependency hoặc Main-Class phù hợp sẽ không vận hành như Spring Boot executable JAR.

### Checklist trước khi build

- Pin JDK version qua Maven/Gradle toolchain và CI image.
- Pin Spring Boot parent/BOM và kiểm tra dependencies.
- Có unit/integration tests, kiểm tra schema compatibility.
- Tách config và secrets khỏi artifact.
- Bật Actuator phù hợp nhưng không xuất toàn bộ endpoints ra Internet.
- Xác định **artifact name/entrypoint** trước khi viết Dockerfile.
- Thiết kế shutdown thời gian hợp lý ngay từ code, không để lúc production mới xử lý.

## 6. Maven tạo executable Spring Boot JAR

Một cấu hình Maven minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>SPRING_BOOT_SUPPORTED_VERSION</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>orders-api</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
  </dependencies>
  <build>
    <finalName>orders-api</finalName>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**SPRING_BOOT_SUPPORTED_VERSION** là placeholder: thay bằng Spring Boot stable được hỗ trợ với Java 21, không chạy Maven khi còn placeholder. Bản POM là bộ khung, chưa có PostgreSQL/Security/test dependencies, migration plugin hoặc đầy đủ profile production.

Build:

~~~bash
./mvnw -B clean verify
java -jar target/orders-api.jar
~~~

Lệnh cần Maven wrapper sẵn có. Có thể dùng **mvn** nếu môi trường CI đã quản lý phiên bản Maven. Để chắc chắn artifact chạy, kiểm tra khởi động thực sự và endpoint HTTP, không chỉ dựa vào build exit code.

## 7. Gradle bootJar và artifact consistency

Với Gradle và Spring Boot Gradle plugin:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/orders-api-1.0.0.jar
~~~

Tên JAR phụ thuộc project version, Gradle configuration và plugin. Khi dùng **bootJar**, phân biệt với plain **jar** nếu cùng sinh hai artifact; pipeline phải trỏ đúng file.

### Reproducibility

~~~text
Commit SHA  -> Maven/Gradle lock/BOM -> Built artifact
                                        |
                                        +-- Artifact checksum
                                        +-- SBOM/dependency scan
                                        +-- Image digest (nếu container)
~~~

Một release đáng tin ghi lại commit, artifact checksum, build tool/JDK version và hình thức deploy. Tránh build lại từ nhánh **main mới nhất** ở mỗi môi trường vì kết quả có thể khác dù cùng tên version.

## 8. Dockerfile an toàn cho Spring Boot

Nếu dùng ACA hoặc AKS, đóng executable JAR vào OCI image. Giả sử CI đã tạo **target/orders-api.jar**.

~~~dockerfile
# Ví dụ runtime JRE 21; thay tag/digest theo chính sách cập nhật.
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --chown=10001:10001 target/orders-api.jar /app/orders-api.jar

USER 10001:10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

### Giải thích các quyết định

- **JRE thay JDK** khi chỉ cần runtime; vẫn cần kiểm tra ứng dụng có dùng công cụ JDK/native runtime đặc biệt không.
- **COPY --chown** để non-root user đọc được artifact; hỗ trợ của Docker/build runtime phải được xác minh.
- **USER 10001** giảm bề mặt tấn công; ứng dụng cần quyền phù hợp để tạo temp files.
- **EXPOSE 8080** ghi metadata container, **không tự mở public port** trên Azure.
- **ENTRYPOINT dạng JSON array** giúp Java thường trở thành PID 1 và nhận termination signals trực tiếp; tránh wrapping shell không dùng **exec**.
- **MaxRAMPercentage=65** là ví dụ, phải đo heap/non-heap/RSS và resource limit thực.

**Không nhúng DB password, Azure connection string, SAS token hoặc private key** qua Dockerfile ENV/ARG. Chúng có thể lộ trong image layers, build logs hoặc metadata.

### Vì sao không dùng shell entrypoint tùy tiện?

~~~dockerfile
# Không khuyến khích khi shell không forward signals phù hợp:
ENTRYPOINT java -jar /app/orders-api.jar
~~~

Một shell có thể chạy ở PID 1, không chuyển SIGTERM đúng cách hoặc xử lý exit status không như dự kiến. Nếu cần script khởi tạo:

~~~sh
#!/bin/sh
set -eu
# Kiểm tra environment không chứa secret trong logs.
exec java -jar /app/orders-api.jar
~~~

**exec** thay thế shell bằng JVM, giúp tín hiệu đến đúng process. Script cần quyền execute, line endings Linux và user permissions đúng; với distroless image có thể không có **/bin/sh**.

## 9. Build image và chạy local

~~~bash
./mvnw -B clean verify
docker build -t orders-api:lab .
docker run --rm --name orders-api \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local \
  orders-api:lab
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
~~~

Các đường dẫn health này cần **Actuator + Spring Boot probes configuration**. Nếu ứng dụng chưa có main class/controllers hoặc database configuration bắt buộc, ví dụ không chạy hoàn chỉnh chỉ từ POM ở mục 6.

### Những gì cần quan sát

- Container process có chạy bằng UID non-root?
- Java có nhận biến môi trường/cổng đúng?
- Readiness có chuyển từ chưa sẵn sàng sang sẵn sàng khi startup hoàn tất?
- Liveness trả 200 khi process hoạt động bình thường?
- Container có bị **OOMKilled** do memory limit không?
- Khi gửi SIGTERM, app có hoàn thành request đang chạy rồi thoát đúng deadline?

## 10. JVM trong container: memory, CPU và exit code

Trong container, Spring Boot dùng **heap, metaspace, direct buffers, thread stacks, native memory, JIT code cache và các thư viện**. Java hiện đại thường hiểu container limits nhưng vẫn cần đo và cấu hình thích hợp.

~~~text
Container memory limit: 1024 MiB (giả định)
  |
  +-- JVM maximum heap: ~650 MiB
  +-- Metaspace / native / threads
  +-- Direct memory / TLS / network buffers
  +-- OS/container overhead
  +-- Safety headroom
~~~

**Không đặt -Xmx bằng toàn bộ container memory limit** rồi mặc định còn đủ RAM cho non-heap. Với resource limits nhỏ, GC thrashing hoặc OOM có thể khiến liveness probe timeout và gây restart loop.

### Exit codes và nguyên nhân

| Dấu hiệu | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Exit code 0 | Hoàn tất/dừng bình thường | Lịch scale-in, logs và lifecycle |
| Exit code 137 | Process bị SIGKILL (có thể OOM hoặc force-kill) | OOMKilled, memory metrics, termination deadline |
| Exit code 143 | Thường tương ứng SIGTERM ở shell/runtime; không bắt buộc luôn xuất hiện | Lịch deploy/scale-in và signal handling |
| Liveness failure/restart | Probe không trả lời hoặc process treo | HTTP path/port, startup time, CPU/GC |
| JVM exception | Startup/config/dependency lỗi | Stack trace đã redaction, secrets/DB connectivity |

Exit code **không đủ để kết luận nguyên nhân một mình**; luôn đối chiếu pod events, platform logs, OOM flags và thời điểm deployment.

## 11. Liveness, readiness và startup khác nhau thế nào?

**Health probe** là cơ chế nền tảng kiểm tra ứng dụng theo lịch để quyết định có nên gửi traffic hoặc restart instance.

| Probe | Câu hỏi | Khi thất bại | Không nên phụ thuộc |
|---|---|---|---|
| **Startup** | Ứng dụng đã khởi động đủ để bắt đầu giám sát bình thường chưa? | Nền tảng có thể restart sau ngưỡng thất bại | Khởi động JVM bình thường chưa xong |
| **Liveness** | Process còn sống và có thể phục hồi bình thường không? | Restart instance/container sau threshold | SQL/Redis bên ngoài có đang online |
| **Readiness** | Instance hiện sẵn sàng nhận **traffic mới** không? | Rút khỏi danh sách endpoints/traffic pool | Một chức năng không trọng yếu đang lỗi |

**Liveness thất bại nên chỉ ra lỗi mà restart process có khả năng sửa được.** Ví dụ process deadlock không phục hồi. Ngược lại, database đang bảo trì là sự kiện ngoài process; restart 50 pods cùng lúc sẽ làm tình hình xấu hơn.

**Readiness thất bại không bắt buộc restart**. Nó giúp loại instance chưa sẵn sàng khỏi tuyến traffic để tránh HTTP 5xx; hệ thống cần có ít nhất một số instance khác sẵn sàng nếu muốn tiếp tục phục vụ.

## 12. Sơ đồ trạng thái của một Spring Boot instance

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> AliveNotReady: JVM, context, startup complete
    AliveNotReady --> Ready: readiness checks pass
    Ready --> NotReady: drain / local dependency unavailable
    NotReady --> Ready: recovered, not terminating
    Ready --> Terminating: SIGTERM / scale-in
    NotReady --> Terminating: SIGTERM
    Terminating --> Stopped: outstanding work completed or deadline
    Stopped --> [*]
~~~

Trong Spring Boot, **ApplicationAvailability** có **LivenessState** và **ReadinessState**. Khi khởi động thành công, framework phát các availability state events theo lifecycle. Trong shutdown, readiness có thể chuyển sang **REFUSING_TRAFFIC** trước khi các bean/servers bị đóng, tùy Spring Boot/runtime.

**Trạng thái framework không thay thế kiểm thử thực tế của platform**: endpoint routing/caches và propagation giữa control plane–data plane có thể có độ trễ. Vì vậy vẫn cần graceful drain và retry an toàn ở client.

## 13. Spring Boot Actuator: phụ thuộc và cấu hình

Thêm Actuator vào project Spring Boot:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Ví dụ **application.yml** cho Spring Boot 3.x:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Đường dẫn Actuator thường là:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Với **management.endpoint.health.probes.add-additional-paths=true**, các phiên bản Spring Boot hỗ trợ cũng có thể bổ sung:

~~~text
GET /livez
GET /readyz
~~~

trên **main application port**. Kiểm tra đúng Spring Boot version và actuator exposure trong project; không mặc định các additional paths tồn tại ở mọi bản hoặc đều được phép truy cập khi Spring Security đã cấu hình.

### Vì sao đặt show-details=never?

Một health response chứa hostname, DB error, storage connection hoặc stacktrace có thể tiết lộ thông tin vận hành. Health check public chỉ nên nói **UP/DOWN hoặc trạng thái tối thiểu**, còn chi tiết chẩn đoán cần được bảo vệ bằng security/monitoring chuyên dụng.

### Health output và status code

Một response minh họa:

~~~json
{"status":"UP"}
~~~

Khi readiness **REFUSING_TRAFFIC**, actuator readiness group thường trả trạng thái không sẵn sàng với HTTP status không thành công theo status mapping tương ứng, ví dụ **503**. Nếu ứng dụng tùy biến mapping, phải đảm bảo Azure probe hiểu status đó đúng.

## 14. Health endpoint nằm trên cổng nào?

Actuator có thể chạy trên **cùng cổng ứng dụng** hoặc tách riêng qua **management.server.port**. Điều này ảnh hưởng chất lượng probe.

~~~text
Client traffic -> port 8080 -> Spring MVC/Tomcat
Health probe   -> port 8080 -> cùng connector/process
~~~

Nếu health probes chạy trên **một cổng quản trị riêng**:

~~~text
Client traffic -> port 8080 -> main server connector
Health probe   -> port 9090 -> management connector
~~~

Một health probe trả 200 trên **management port 9090** chưa chứng minh main connector **8080** đang tiếp nhận request tốt. Ví dụ main thread pool bị nghẽn hoặc cấu hình ingress sai thì management port vẫn có thể hoạt động.

### Khuyến nghị

- Với Kubernetes/ACA, ưu tiên **main-port readiness/liveness paths** khi có thể và hợp lệ với security policy.
- Nếu dùng management port riêng để bảo vệ, bổ sung synthetic checks trên đường phục vụ thật.
- Không cung cấp toàn bộ Actuator endpoints qua Internet.
- Health path cần nhất quán với container targetPort/Service/ingress và các rewrite rules.

**Không thay authentication bằng port isolation**: management port cũng cần network policy và quyền phù hợp.

## 15. Spring Security và health probes

Khi dự án dùng **Spring Security**, health endpoints có thể bị authentication filter trả 401/403 hoặc redirect tới login. Platform probe thường không đăng nhập như end user.

Một cấu hình skeleton Spring Boot 3/Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/actuator/health",
                "/actuator/health/liveness",
                "/actuator/health/readiness",
                "/livez",
                "/readyz")
            .permitAll()
            .anyRequest().authenticated());
        // Đây chỉ là authorization skeleton, không đầy đủ JWT/CSRF.
        return http.build();
    }
}
~~~

**Không dùng skeleton như security config production hoàn chỉnh.** Với REST API, cần JWT/OIDC resource server config, issuer/audience validation, CSRF policy thích hợp theo cookie/token auth, exception handling và method-level authorization. Chỉ mở health paths cần thiết, với response không tiết lộ data. Trên App Service/AKS, bổ sung access restrictions để health endpoint không rộng hơn mục đích.

### Kiểm tra

~~~bash
curl --silent --show-error -i \
  http://localhost:8080/actuator/health/liveness
curl --silent --show-error -i \
  http://localhost:8080/actuator/health/readiness
~~~

Nếu nhận **302 login redirect**, **401** hoặc **403**, phải xem lại đường network/security; không đặt Azure probe kỳ vọng 200 trên endpoint đang bị bảo vệ bắt buộc bằng JWT của người dùng.

## 16. Readiness: có nên đưa database vào không?

Một lựa chọn thường gặp là đưa **db** health indicator vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

**Đây là ví dụ tùy biến có điều kiện**, không phải khuyến nghị mặc định. Với ứng dụng chỉ phục vụ request khi database bắt buộc hoạt động, kiểm tra DB có thể giúp tránh gửi traffic vào instance không có kết nối. Tuy nhiên, nếu **toàn bộ replicas cùng mất DB**, chúng đều trở thành not ready; proxy/load balancer có thể trả 503 cho mọi request, dù ứng dụng có thể phục vụ những endpoint không cần DB.

### Hai cách thiết kế

| Cách | Lợi ích | Rủi ro |
|---|---|---|
| **Readiness chỉ theo readinessState** | Không loại toàn bộ pods khi shared DB lỗi | Request cần DB vẫn thất bại, phải xử lý lỗi/timeout tốt |
| **Readiness gồm db** | Loại pod không thể dùng DB (ví dụ lỗi kết nối cục bộ) | Shared outage làm mọi pod unready, có thể giấu nguyên nhân |

### Quy tắc thực hành

1. **Không thêm DB vào liveness** để tránh restart storm.
2. Đánh giá dependency nào thực sự là điều kiện nhận mọi request.
3. Dùng circuit breaker/timeouts và degraded responses cho dependency tạm lỗi.
4. Với nhiều loại endpoint, cân nhắc phân tách service hoặc synthetic checks theo nghiệp vụ.
5. Nếu có check DB, đặt timeout/connection pool phù hợp; probe không nên tạo heavy query.
6. Test toàn bộ database outage, không chỉ một pod bị network lỗi.

**Readiness cần mô tả khả năng phục vụ traffic của chính instance**, không phải cứ có dịch vụ bên ngoài lỗi là tự restart cả hệ thống.

## 17. Startup probe: giải quyết ứng dụng khởi động chậm

Spring Boot có thể khởi động chậm do classpath, database migration, JIT/warm-up, remote configuration hoặc cache.

Kubernetes **startupProbe** trì hoãn việc chạy liveness/readiness probes cho tới khi startup check thành công theo cơ chế Kubernetes. Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
  timeoutSeconds: 2
~~~

**Budget lý thuyết khoảng 5 × 24 = 120 giây** trước khi bị coi là startup thất bại, không bao gồm mọi timing/overhead chi tiết. Không chọn số 120 chỉ vì tiện: đo startup p95/p99 với tải, database và environment thật.

### Startup probe nên kiểm tra gì?

- Endpoint chỉ có thể trả thành công khi JVM/Spring process đã ở trạng thái đủ khởi động.
- Không phụ thuộc truy vấn SQL dài/không ổn định.
- Không kết thúc thành công quá sớm khi main HTTP connector chưa mở, nếu platform cần HTTP readiness.

**Không dùng readiness failureThreshold dài để che startup chậm** rồi quên startupProbe. Trong Kubernetes, startupProbe tách startup budget khỏi liveness policy bình thường.

## 18. Liveness probe: chẩn đoán tình trạng process

Một liveness probe HTTP minh họa:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Tức là nền tảng kiểm tra định kỳ, và sau đủ lần thất bại liên tiếp sẽ restart theo policy. Kết quả thực tế phụ thuộc thời điểm/scheduling; đây không phải cam kết "restart chính xác sau 30 giây".

### Những lỗi cần tránh

- Liveness gọi **/actuator/health** mặc định mà nhóm này bao gồm indicator DB/Redis, dẫn đến restart vì external outage.
- Endpoint liveness chạy qua public gateway khác đường nội bộ, chịu ảnh hưởng WAF/rate limit.
- timeoutSeconds quá thấp so với GC pauses/CPU throttling, khiến false positives.
- failureThreshold=1 cho process có lúc pause ngắn.
- Liveness URL trả 302/401 nhưng operator tưởng JVM chết.

Đặt liveness để phát hiện **process không còn phục hồi được**, không biến nó thành một bài integration test mọi downstream.

## 19. Readiness probe: bảo vệ traffic trong rollout

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 1
~~~

Khi readiness chưa đạt, Kubernetes Service thường không đưa pod vào danh sách endpoints sẵn sàng cho traffic mới, với điều kiện các controller và network components tuân theo readiness. **Có độ trễ propagation**, nên liveness/readiness không thay thế graceful shutdown hoặc retry.

### Readiness có nên kiểm tra Java thread pool?

Nếu thread pool quá tải dài hạn, ứng dụng có thể tạm ngừng nhận request. Nhưng nếu readiness dao động theo từng đợt tải ngắn, traffic sẽ dồn sang replicas còn lại và gây hiệu ứng dây chuyền. Cần đánh giá **backpressure/load shedding** và autoscale thay vì gắn readiness trực tiếp với mỗi đỉnh CPU ngắn.

### Chỉ bật readiness trong lần build mới?

Không. Readiness phải hoạt động cả khi deploy, scale-in, temporary local failure và recovery. Test **lifecycle complete**, không chỉ một lần curl 200 sau startup.

## 20. Tại sao health probe có thể gây outage?

Một ví dụ anti-pattern:

~~~text
10 Spring Boot replicas
  -> liveness calls /actuator/health
  -> indicator 'db' queries shared PostgreSQL

PostgreSQL có sự cố 2 phút
  -> tất cả liveness fail
  -> tất cả replicas bị restart liên tục
  -> JVM warm-up + reconnect storm
  -> database phục hồi càng chậm
~~~

**Lỗi nguồn** là external database outage, nhưng **hành vi gây khuếch đại** là liveness gắn sai dependency. Cải tiến:

- Liveness chỉ phản ánh tình trạng JVM/process.
- Database timeout/circuit breaker không làm app treo vô hạn.
- Readiness policy được lựa chọn có chủ đích.
- HPA/autoscaler không tạo vô hạn retries vào database.
- Observability tách **DB_DOWN** khỏi **JVM_DEADLOCK**.

Mục tiêu không phải để health luôn xanh, mà để mỗi tín hiệu **diễn đạt đúng loại sự cố và dẫn tới hành động đúng**.

## 21. AKS: Deployment có đầy đủ probes và graceful deadline

Ví dụ cho Spring Boot chạy trong AKS:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 50
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: orders-api
          image: myregistry.azurecr.io/orders-api:1.0.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "768Mi"
            limits:
              cpu: "1500m"
              memory: "1536Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
            timeoutSeconds: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
            timeoutSeconds: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Đây là **manifest học tập**, không phải gói production hoàn chỉnh. Cần registry credential/AKS pull permission, workload identity, application config, NetworkPolicy, ingress, HPA, PDB, security policies, observability và bảo mật image theo yêu cầu.

### Giải thích thời hạn

~~~text
terminationGracePeriodSeconds = 50 s
preStop delay                  = 5 s
Spring Boot shutdown phase    = 30 s
Headroom minh họa             = 15 s
~~~

Giá trị **50 s** bao gồm thời gian chạy preStop hook, thời gian JVM xử lý SIGTERM và một khoản dự phòng, không phải **50 s + preStop**. Nếu hook kéo dài 40 giây, JVM có thể chỉ còn thời gian rất ngắn trước khi Kubernetes cưỡng bức kết thúc.

### Lưu ý preStop command

Lệnh **/bin/sh -c sleep 5** cần shell/sleep tồn tại trong image. Với **distroless image**, hook kiểu này có thể thất bại; dùng cơ chế lifecycle được nền tảng hỗ trợ hoặc sidecar/entrypoint phù hợp và kiểm thử. Không dùng sleep dài như giải pháp thay thế cho readiness/draining logic.

### maxUnavailable=0 không hứa zero-downtime tuyệt đối

Thông số này chủ yếu giúp Deployment controller duy trì số replicas sẵn sàng khi **rolling update có kiểm soát**. Nó không ngăn node outage, AZ failure, database outage, HPA race, network propagation delay, hay schema migration làm phiên bản cũ lỗi.

## 22. AKS: kiểm chứng rollout và tình trạng pod

Khi đã được phép chạy trong **cluster lab**:

~~~bash
NAMESPACE="spring-lab"

kubectl get deployment orders-api -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l app=orders-api -o wide
kubectl describe deployment orders-api -n "$NAMESPACE"
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp
kubectl rollout status deployment/orders-api -n "$NAMESPACE"
~~~

Kiểm tra từng pod:

~~~bash
kubectl describe pod <POD_NAME> -n "$NAMESPACE"
kubectl logs <POD_NAME> -n "$NAMESPACE" --tail=100
kubectl get endpointslice -n "$NAMESPACE" \
  -l kubernetes.io/service-name=orders-api
~~~

### Những thông tin cần tìm

- Pod **Ready** sau startup bao lâu?
- Đã từng xảy ra **Startup probe failed**, **Readiness probe failed** hay **Liveness probe failed** chưa?
- Restart count tăng không? Có **OOMKilled** không?
- Service EndpointSlices có những endpoints được phép nhận traffic?
- Khi rollout, phiên bản cũ và mới có cùng tồn tại và phục vụ hợp lệ không?
- Có lỗi 503/502/connection reset từ phía ingress trong lúc đổi pod không?

Đừng chỉ nhìn **kubectl get pods** với trạng thái Running. **Running không tương đương Ready**, và Ready cũng không chứng minh toàn bộ transaction business thành công.

## 23. AKS: rollout, PodDisruptionBudget và drain

Ở Kubernetes:

- **Deployment RollingUpdate** điều khiển thay thế pods khi nâng phiên bản.
- **readinessProbe** quyết định pod có đủ điều kiện nhận traffic.
- **PodDisruptionBudget (PDB)** hỗ trợ giới hạn những gián đoạn **tự nguyện** theo cách Kubernetes eviction API áp dụng.
- **terminationGracePeriodSeconds** cho process thời gian tắt theo lifecycle.
- **Ingress/gateway** có thể còn kết nối keep-alive hoặc độ trễ cập nhật upstream.

Ví dụ PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

**PDB không bảo vệ mọi trường hợp pod mất đột ngột** (node crash, OOM, forced deletion), và không thay thế số replicas thực/zone spread. Nếu có 2 replicas và PDB yêu cầu minAvailable=2, node drain bảo trì có thể bị trì hoãn; thiết kế cần cân bằng availability và khả năng bảo trì.

### Terminating pod và endpoint propagation

Kubernetes báo pod đang terminating; EndpointSlice và ingress controllers cần thời gian cập nhật. Trong thời gian này, request đã mở hoặc một số request mới vẫn có thể chạm instance cũ. **preStop delay ngắn** đôi khi giúp gateway cập nhật trước khi process dừng, nhưng phải đo trong thực tế và không biến 5 giây thành quy luật cố định.

## 24. Container Apps: probe ở cấp container app

Với **Azure Container Apps**, ứng dụng đóng OCI image và cung cấp HTTP ingress theo targetPort. ACA hỗ trợ các cấu hình health probes cho container theo khả năng phiên bản/hosting.

Một cấu hình minh họa **khái niệm**, không phải file deployable nguyên vẹn:

~~~yaml
containerApp:
  image: myregistry.azurecr.io/orders-api:1.0.0
  ingress:
    external: true
    targetPort: 8080
  scale:
    minReplicas: 2
    maxReplicas: 10
  probes:
    startup:
      httpGet: /actuator/health/liveness
      port: 8080
    readiness:
      httpGet: /actuator/health/readiness
      port: 8080
    liveness:
      httpGet: /actuator/health/liveness
      port: 8080
~~~

**Không paste YAML này vào az containerapp create/update**. Schema thực của ACA template chứa cấu trúc **properties.template.containers[].probes** và các fields cụ thể theo API version, phân biệt HTTP/TCP, threshold/timing; cần tạo cấu hình thật bằng Portal/Bicep/ARM/CLI schema được hỗ trợ.

### Cần kiểm tra điều gì?

1. **Container ingress targetPort** khớp server.port của Spring.
2. App khởi động với JVM args và env vars đúng.
3. Các probe dùng HTTP endpoint tồn tại, trả HTTP status phù hợp.
4. Revision mới chỉ nhận traffic khi sẵn sàng theo platform behavior.
5. Khi **scale-to-zero**, lần phục vụ đầu có cold start; probe thresholds phải phù hợp.
6. Khi ACA scale-in/stop revision, ứng dụng có xử lý termination signal và shutdown deadline không?
7. Dòng log scale/restart phân biệt startup failure với liveness failure.

**Không giả định cách ACA gửi termination signal và termination grace giống từng chi tiết Kubernetes Deployment của AKS.** ACA dùng nền tảng được quản lý; chỉnh shutdown cần dựa trên cấu hình và tài liệu ACA cụ thể.

## 25. Container Apps: revisions, traffic và graceful scale-in

ACA có **revisions** và có thể hỗ trợ chia traffic giữa các revision theo chế độ phù hợp.

~~~text
External client
       |
       v
ACA ingress / traffic weights
       |
       +-- Revision v1: 90%, ready replicas
       |
       +-- Revision v2: 10%, ready replicas
                 |
                 v
             Spring Boot API
~~~

### Trước khi đưa traffic sang v2

- Probe paths có tồn tại trong image mới?
- v2 có cần migration schema không? v1 còn chạy song song được không?
- Startup time và memory footprint có thay đổi?
- JWT issuer/audience, database DNS và Key Vault references hoạt động?
- Nếu v2 lỗi, rollback **traffic route** có an toàn với data đã ghi không?

### Scale-in là một rollout thu nhỏ

Khi minReplicas hoặc scale rules làm giảm số replicas, ứng dụng vẫn cần:

- Ngừng tiếp nhận việc mới khi bắt đầu termination.
- Không để HTTP request hoặc queue job bị cắt không có retry.
- Đóng JDBC pools/HTTP clients sạch trong giới hạn.
- Ghi signal/termination metrics để điều tra.

**Chỉ quan sát một lần deploy êm không chứng minh autoscale-in hoạt động an toàn**. Test cả giai đoạn scale-down khi có requests đang chạy.

## 26. App Service: Health Check cho Spring Boot

**Azure App Service Health Check** có thể gọi HTTP path định kỳ trên instances khi tính năng và plan hỗ trợ, rồi đánh giá những instances không khỏe theo chính sách dịch vụ.

### Thiết lập

1. Mở **App Service** trong Azure Portal, chọn ứng dụng và đúng environment/slot.
2. Vào phần **Health check** theo giao diện hiện hành.
3. Cấu hình đường dẫn có thể trả status thích hợp, ví dụ **/actuator/health/readiness**.
4. Xác nhận path trả mã thành công từ **chính ứng dụng đã deploy**, không bị authentication redirect.
5. Kiểm tra platform logs/metrics về trạng thái instances.
6. Test thay đổi cấu hình trên staging trước production.

### Chọn path nào?

| Path | Ưu điểm | Hạn chế |
|---|---|---|
| **/actuator/health/liveness** | Phản ánh process còn hoạt động | Có thể trả UP khi instance chưa sẵn sàng xử lý |
| **/actuator/health/readiness** | Đo instance có sẵn sàng nhận traffic | Nếu cấu hình phụ thuộc DB chung, toàn bộ instances có thể bị đánh dấu unhealthy |
| **/healthz** tự xây tối giản | Dễ map theo chính sách platform | Cần đồng bộ với Spring availability và không che lỗi |

**Không trả 200 cố định** để làm Health Check xanh nếu Spring Boot web server chưa khởi động xong hoặc instance không thể nhận yêu cầu. Ngược lại, không cho một health path thực hiện SQL query phức tạp gây tăng tải hoặc false positives.

### Những lưu ý App Service

- Health Check không thay thế **readiness/liveness/startup Kubernetes probes**; cách platform xử lý trạng thái unhealthy khác nhau.
- Tính năng, số instances cần cho route-away behavior và thresholds phụ thuộc plan/điều kiện dịch vụ.
- Nếu chạy **custom container**, cần đảm bảo startup command và port mapping/hosting configuration chính xác.
- **Always On** khi plan hỗ trợ có thể hữu ích tránh app idle unload, nhưng không thay health path hoặc tự bảo đảm không có cold start khi deploy.
- Nếu chỉ có một instance, không có instance khác để chuyển traffic; cần thiết kế scale/HA thích hợp.

## 27. App Service: warm-up, startup command và slots

**App Service Java SE** có thể khởi chạy executable Spring Boot JAR theo runtime và cơ chế deploy được hỗ trợ. **App Service custom container** dùng image/entrypoint với các biến port/hosting tương ứng.

### Những kiểm tra cần có

- Java runtime/JDK tương thích với compiled bytecode.
- JAR đúng tên và có Main-Class/Boot loader.
- Spring Boot lắng nghe cổng và địa chỉ mà runtime host yêu cầu.
- App Settings/Key Vault references đã được resolve.
- /actuator/health/readiness trả trạng thái đúng sau startup.
- Cold start/warm-up không làm request đầu tiên bị timeout.

### Deployment slots

~~~text
Slot staging: candidate JAR/image
     |
     +-- Warm-up + test health + test DB/network
     |
     v
Swap/traffic promotion theo tính năng
     |
     v
Slot production: candidate version
~~~

**Slot swap có chính sách sticky settings/identities riêng**. Trước khi swap, xác minh database endpoint, secrets, resource identity, event publishers và downstream services. Không để staging credential vô tình có quyền ghi production DB.

### Health Check không phải login-protected application page

Nếu health path trả 302 tới /login hoặc một HTML error page 200 trong khi ứng dụng thực lỗi, bạn cần điều chỉnh security/routing và nội dung response. Health endpoint tối thiểu nên dùng HTTP status có ý nghĩa và không công bố stacktraces.

## 28. Virtual Machines và VM Scale Sets: systemd lifecycle

Với VM Linux, Spring Boot có thể được quản lý bằng **systemd**:

~~~ini
[Unit]
Description=Spring Boot orders API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=orders
WorkingDirectory=/opt/orders
Environment=SPRING_PROFILES_ACTIVE=prod
ExecStart=/usr/bin/java -jar /opt/orders/orders-api.jar
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=45
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
~~~

Đây là **mẫu**: phải tạo service user, cấp quyền file, xác nhận đường dẫn Java/JAR và secret injection. **Không đưa DB password trong unit file**, vốn có thể bị đọc theo quyền file/systemd environment. Thực thi systemd cần root/sudo được phân quyền; không tự chạy trên VM production trong lab.

### Khi systemd stop

1. systemd gửi **SIGTERM** cho process theo unit configuration.
2. Spring Boot bắt đầu shutdown lifecycle.
3. HTTP server ngừng nhận request mới và cố hoàn tất việc đang xử lý theo chính sách.
4. Beans/pools/worker resources được giải phóng.
5. Nếu quá **TimeoutStopSec**, systemd có thể cưỡng bức terminate.

**TimeoutStopSec phải tương thích Spring timeout-per-shutdown-phase**, thời gian pre-drain ở load balancer và overhead. Với VMSS, backend pool/health probe/rolling upgrade còn cần điều phối việc rút traffic.

## 29. Azure Functions không dùng nguyên quy tắc probe của web server

**Azure Functions Java** có **function host**, triggers, scaling và lifecycle theo hosting plan. Một function đọc Service Bus hoặc chạy theo lịch không nhất thiết có **embedded Tomcat** hay Actuator endpoints như một Spring Boot MVC app.

| Thành phần | Spring Boot web app | Azure Functions Java |
|---|---|---|
| Process điều phối | JVM/embedded server | Azure Functions host + Java worker |
| Health của ứng dụng | Actuator liveness/readiness | Host/trigger health và telemetry theo plan |
| Work intake | HTTP/gateway hoặc application consumer | Trigger/binding |
| Shutdown | Spring application context/server lifecycle | Host/trigger lifecycle, in-flight handling theo binding |
| Retry/checkpoint | Ứng dụng/queue consumer | Binding/host config và business idempotency |

Không khẳng định thêm **server.shutdown=graceful** vào một Function project sẽ tự điều phối Service Bus trigger và checkpoint của Functions host. Nếu workload cần shutdown-aware behavior, dùng cơ chế Functions host/SDK phù hợp và business idempotency.

## 30. SIGTERM là điểm bắt đầu, không phải mục tiêu cuối

Khi container hoặc host cần dừng, tín hiệu **SIGTERM** thông thường yêu cầu JVM bắt đầu tắt có kiểm soát. Nếu JVM không xử lý hoặc timeout của host hết, hệ thống có thể gửi **SIGKILL** hoặc cơ chế cưỡng bức tương đương.

~~~mermaid
sequenceDiagram
    participant P as Platform / Orchestrator
    participant A as Spring Boot
    participant I as Ingress / Service
    participant D as Database / downstream
    P->>I: Đánh dấu endpoint terminating (propagation)
    P->>A: preStop hook nếu có
    P->>A: SIGTERM (sau hook)
    A->>A: Readiness REFUSING_TRAFFIC / shutdown
    A->>I: Ngừng nhận kết nối mới theo server behavior
    A->>D: Hoàn thành hoặc rollback transaction
    A->>A: Close pools, listeners, background tasks
    A-->>P: Process exit
    Note over P,A: Hết grace deadline: có thể force-kill
~~~

Thứ tự cụ thể của ingress deregistration, SIGTERM và availability event phụ thuộc Kubernetes/ACA/App Service/runtime. **Sequence diagram chỉ minh họa các thành phần tham gia**, không cam kết chính xác mọi thời điểm trên mỗi nền tảng.

### Shutdown không thể ngăn tất cả failure modes

- VM/node có thể mất điện không kịp SIGTERM.
- Pod có thể bị OOMKilled/SIGKILL.
- Request có thể bị client disconnect giữa chừng.
- Database transaction có thể commit ngay trước khi JVM chết.
- Queue event có thể được redeliver sau failover.

Vì vậy, graceful shutdown **giảm rủi ro gián đoạn có kiểm soát**, không thay thế idempotency, durability, retry hoặc DR.

## 31. Cấu hình graceful shutdown trong Spring Boot

Ví dụ **application.yml**:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

### Ý nghĩa

- **server.shutdown=graceful**: yêu cầu embedded web server dùng cơ chế dừng có kiểm soát theo khả năng server/runtime.
- **spring.lifecycle.timeout-per-shutdown-phase=30s**: giới hạn thời gian cho **mỗi shutdown phase** trong lifecycle mà Spring quản lý; **không phải bảo đảm toàn bộ process luôn dừng trong đúng 30 giây**.
- Health probes phản ánh trạng thái sẵn sàng để nền tảng route traffic.

### Tại sao cần phân biệt total deadline và phase timeout?

Nếu ứng dụng có nhiều lifecycle phases hoặc các resources không tuân theo thời gian, tổng thời gian shutdown có thể dài hơn một con số đã cấu hình. Orchestrator deadline là giới hạn cuối:

~~~text
Host termination grace:        50 s
  - preStop:                    5 s
  - Spring lifecycle phases:   cần đo thực tế
  - network/cleanup overhead:  còn lại

Nếu chưa thoát sau host deadline:
  -> process có thể bị force-kill
~~~

**Không áp dụng máy móc:** "Spring timeout=30s nên Kubernetes grace=31s đủ". Cần quan sát termination p95, số lượng bean listeners, I/O, worker drain và overhead; đặt số liệu có dự phòng.

### Server khác nhau có shutdown semantics khác nhau

Tomcat, Jetty, Undertow và Reactor Netty có cơ chế tạm dừng nhận kết nối mới và xử lý request đang mở khác nhau. Các connection keep-alive, HTTP/2 streams, WebSocket, streaming responses và client retries có thể đòi logic ứng dụng bổ sung. **Server graceful shutdown không tự đợi vô hạn mọi business job hoàn thành**.

## 32. Không tự dùng System.exit để "tắt nhanh"

Một anti-pattern:

~~~java
@PreDestroy
public void stop() {
    System.exit(0); // Không nên: phá vỡ lifecycle/cleanup của context
}
~~~

Gọi System.exit từ một lifecycle callback có thể làm khó đoán thứ tự dừng bean và resource cleanup. Trong Spring Boot thường để **SpringApplication/ApplicationContext + embedded server** xử lý termination do SIGTERM; nếu có nhu cầu shutdown chủ động bằng API quản trị, phải thiết kế đường điều khiển được bảo vệ và đúng lifecycle, không dùng endpoint public gọi System.exit.

### Shutdown hooks và tín hiệu

JVM có thể chạy shutdown hooks khi tiến trình kết thúc bình thường theo cơ chế được hỗ trợ. Spring Boot đăng ký hook để đóng ApplicationContext. Tuy nhiên, **SIGKILL, lỗi kernel, mất điện hoặc OOM ở mức host** không đảm bảo callback/hook được chạy. Cần thiết kế external state và checkpoint để phục hồi sau cái chết đột ngột.

### Không bật actuator shutdown public

Một số phiên bản Spring Boot Actuator có endpoint shutdown có thể được cấu hình riêng. Không expose endpoint này cho Internet để "test graceful shutdown", vì nó là thao tác điều khiển vòng đời rất nhạy cảm. Để test SIGTERM, dùng container/orchestrator stop trong sandbox.

## 33. @PreDestroy: đóng resource nhưng không làm nghiệp vụ dài

Với resource tự quản như scheduler hoặc custom network client, có thể dùng **@PreDestroy**:

~~~java
package com.example.orders;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import java.time.Instant;

@Component
public class LocalResourceOwner {
    private volatile boolean closing;

    public boolean isClosing() {
        return closing;
    }

    @PreDestroy
    public void closeResources() {
        closing = true;
        // Đóng custom client/file handle có deadline hợp lý.
        // Không thực hiện migration hay gọi API bên ngoài vô thời hạn.
        System.out.println("Cleanup invoked at " + Instant.now());
    }
}
~~~

**Đây là skeleton**; flag closing trong bean không tự làm traffic routing dừng và không thay thế readinessState của Spring Boot. Những resources do Spring quản lý, như DataSource/JMS/Kafka clients, thường có lifecycle riêng; đừng đóng cùng resource hai lần hoặc sai thứ tự.

### Trình tự quan trọng

- Dừng intake **trước** khi dọn resources mà việc đang chạy còn cần.
- Chờ tasks trong giới hạn, xử lý cancellation/interruption.
- Đảm bảo commit/rollback/checkpoint theo contract.
- Sau đó giải phóng thread pools, connections và file handles.

**Không đặt sleep(60000) trong @PreDestroy** để "đợi mọi thứ"; timeout cố định có thể phí grace budget và vẫn không đảm bảo job hoàn tất.

## 34. ThreadPoolTaskExecutor và các tác vụ @Async

Spring Boot apps thường có xử lý bất đồng bộ bằng **@Async** hoặc executor tự quản. Khi nhận shutdown, nếu executor dừng đột ngột, task đang chạy có thể bị cắt.

Ví dụ cấu hình **ThreadPoolTaskExecutor**:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {

    @Bean(name = "orderExecutor")
    public ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

### Giới hạn cần biết

- **Wait-for-tasks** có thể giúp hoàn tất jobs đang chạy, nhưng sẽ dùng shutdown budget.
- Queue 100 là **bộ nhớ trong process**, có thể mất khi JVM chết.
- Task không tôn trọng interruption hoặc gọi downstream không có timeout vẫn có thể vượt deadline.
- Tùy phiên bản Spring Framework, lifecycle và hành vi từ chối nhiệm vụ mới khi context đóng có thể khác; hãy kiểm thử thay vì suy luận chỉ từ tên setter.

**Đừng dùng in-memory @Async queue cho business event bắt buộc không mất**. Nếu quan trọng, ghi durable job/outbox vào database hoặc Service Bus rồi mới trả HTTP response.

## 35. @Scheduled và nhiều replicas

Một Spring Boot application có thể dùng:

~~~java
@Scheduled(fixedDelay = 60000)
public void refreshCache() {
    // Chạy mỗi phút khi application instance còn sống.
}
~~~

Khi scale thành 5 replicas, **cả 5 instances có thể chạy @Scheduled**. Khi Azure triển khai phiên bản mới, có thể cùng tồn tại 5 pods cũ và 5 pods mới trong thời gian ngắn; việc này càng làm tăng nguy cơ chạy song song.

### Những cách xử lý

| Nhu cầu | Lựa chọn |
|---|---|
| Cache refresh trên mỗi instance | @Scheduled local có thể phù hợp |
| Gửi một báo cáo toàn hệ thống | Durable scheduler/queue, distributed lock hoặc single elected leader |
| Batch chạy 1 lần/ngày | Container Apps Job/AKS CronJob/Functions Timer theo điều kiện |
| Tác vụ cần retry bền vững | Service Bus/outbox và idempotent worker |

**Graceful shutdown không làm cho @Scheduled thành exactly-once scheduler.** Ngay cả distributed lock cũng cần expiry/ownership fencing và idempotency; node có thể chết khi giữ lock.

### Spring scheduler shutdown

Kiểm tra shutdown policy của **TaskScheduler**, thread pools, cron jobs và long-lived threads. Nếu dùng custom Executors, có thể cần lifecycle shutdown riêng; không chỉ bật server.shutdown rồi tưởng tất cả jobs dừng.

## 36. Queue consumers: at-least-once và shutdown

Một Java worker nhận **Service Bus** message:

~~~text
Queue message M42
    |
    v
Java consumer nhận message / lock
    |
    +-- Validate payload
    +-- Execute DB transaction
    +-- Commit business effect
    +-- Complete/acknowledge message
~~~

Khi worker bị scale-in:

1. Ngừng nhận message mới.
2. Cho in-flight message handler có thời gian hoàn thành.
3. Commit DB transaction trước khi hoàn tất broker message.
4. Nếu không xong trong deadline, để broker redeliver theo semantics.
5. Lần xử lý lại cần nhận diện eventId/idempotency key để tránh side effects trùng.

### Race điển hình

~~~text
T1: Worker ghi đơn hàng thành công.
T2: Database commit hoàn tất.
T3: Host SIGTERM, process chết trước complete message.
T4: Broker redeliver message.
T5: Worker mới phải thấy đơn đã ghi và không tạo trùng.
~~~

**Không thể chữa race này chỉ bằng timeout shutdown dài hơn** vì node có thể chết đột ngột. Thiết kế **unique constraint, idempotency key, transactional outbox/inbox** nếu nghiệp vụ đòi độ tin cậy.

### Không lẫn liveness của API và worker

Một worker chỉ đọc queue có thể không có HTTP server/port 8080. Nếu đặt Kubernetes HTTP probe cho một container không mở HTTP endpoint, nó sẽ bị restart liên tục dù consumer đang xử lý bình thường. Dùng probe phù hợp cho worker hoặc tách API và worker thành deployments khác.

## 37. HTTP request đang chạy khi shutdown

Giả sử một **POST /orders** mất 8 giây:

~~~text
00s Client gửi POST /orders
02s Azure scale-in / rollout bắt đầu
03s Spring bắt đầu drain
08s DB transaction commit
09s Server trả 201 Created
12s JVM kết thúc
~~~

Đây là **kịch bản lý tưởng** nếu route cập nhật và shutdown deadlines đủ dài. Nhưng có thể xảy ra:

~~~text
00s POST /orders bắt đầu
02s SIGTERM
05s Container force-killed
06s Client retry do không nhận response
~~~

Với tình huống thứ hai, database có thể đã commit hoặc chưa. Client retry có thể tạo đơn trùng. **Đáp án sản phẩm là idempotency**, không chỉ grace period.

### API idempotency

Client gửi header:

~~~http
POST /api/orders HTTP/1.1
Idempotency-Key: order-client-req-7c0e...
Content-Type: application/json

{"cartId":"cart-123"}
~~~

Backend cần gắn key với user/tenant, endpoint, request hash và record transaction một cách bền vững. Nếu cùng key được gửi lại sau network timeout, trả lại kết quả hợp lệ đã xác nhận hoặc trạng thái phù hợp thay vì tạo order mới. **Không dùng idempotency key như authentication token**.

## 38. HTTP streaming, SSE và WebSocket

HTTP request/response ngắn tương đối dễ drain. **Server-Sent Events**, WebSocket và streaming responses có thể kéo dài vài phút hoặc hàng giờ.

### Vấn đề

- Một streaming response có thể chưa kết thúc khi grace budget hết.
- Kết nối WebSocket có thể bị đóng trong rolling deployment.
- Client cũ có token/session state chỉ nằm trong instance cũ.
- Nếu dùng in-memory subscription maps, client phải đăng ký lại.

### Thiết kế ổn định

1. Client có **reconnect với exponential backoff/jitter**.
2. Protocol có **cursor/event sequence** để lấy lại trạng thái sau reconnect nếu cần.
3. Dùng durable backend/broker hoặc external session state khi có yêu cầu.
4. Gửi tín hiệu drain/close theo protocol khi có thể, không chỉ TCP reset.
5. Thử rolling deployments khi có connections active.
6. Không đặt grace period vô hạn để giữ một WebSocket bất tử.

**Graceful shutdown không bảo đảm mọi WebSocket tiếp tục sống qua pod replacement.** Để người dùng không mất nghiệp vụ, client cần resubscribe/resync khi reconnect.

## 39. DB transactions, connection pools và cleanup

Khi Spring ApplicationContext shutdown, **DataSource/HikariCP** được đóng theo lifecycle. Nếu pool đóng trước khi một task đang chạy ghi xong, task có thể thất bại hoặc transaction bị rollback.

### Nguyên tắc

- Đừng đóng DataSource thủ công từ signal handler khi service layer còn in-flight.
- Không thực hiện database migration trong @PreDestroy.
- Với request/business job, đặt **transaction timeout** phù hợp.
- Thực hiện checkpoint/outbox commit trước khi broker complete.
- Cho shutdown lifecycle thời gian để tasks đang chạy hoàn tất.
- Tính cả thời gian DNS, connection retry và lock waits khi đo shutdown.

### Một anti-pattern

~~~java
@PreDestroy
void shutdown() throws InterruptedException {
    // Anti-pattern: chờ vô hạn rồi hy vọng database luôn phản hồi.
    while (hasPendingOrders()) {
        Thread.sleep(1000);
    }
}
~~~

Trong trường hợp database outage, loop này không thể kết thúc đúng hạn, process bị force-kill và có thể gây rollback/retry storm. Thay bằng **bounded drain + durable recovery**.

## 40. Tính shutdown deadline có dự phòng

Một ngân sách giả định:

| Thành phần | Thời gian tối đa mục tiêu |
|---|---:|
| Ingress/EndpointSlice propagation + preStop | 5 giây |
| In-flight HTTP requests bình thường | 15 giây |
| Worker/bean cleanup | 10 giây |
| Logging/metrics flush và headroom | 10 giây |
| **Tổng grace đề xuất thử nghiệm** | **40 giây** |

Nếu chốt **terminationGracePeriodSeconds=45**, cần thử load thật; giá trị tổng chỉ là ước lượng. Với một request tối đa 120 giây, deadline 45 giây không thể hứa sẽ hoàn tất request đó.

### Nên thay đổi gì nếu tác vụ dài?

- Tách thành **202 Accepted + durable jobId** rồi xử lý async.
- Rút ngắn transaction/remote call timeouts.
- Cho client retry dựa trên idempotency.
- Dùng checkpoint cho long-running task.
- Với báo cáo lớn, lưu kết quả vào Blob Storage và trả URL/ID khi hoàn thành.

### Deadline không cộng một cách ngây thơ

Spring có nhiều shutdown phases; những việc có thể chạy song song hoặc nối tiếp. Network routing, preStop và lifecycle cleanup có thể overlap theo nền tảng. Do đó **đo elapsed time từ SIGTERM/scale-in đến process exit**, không chỉ cộng các hằng số trong YAML.

## 41. Bài thử local: request chậm và Docker stop

Để kiểm chứng draining, thêm một controller **chỉ dùng trong profile lab**:

~~~java
package com.example.orders.lab;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@Profile("local-lab")
@RestController
public class SlowLabController {

    @GetMapping("/lab/slow")
    public ResponseEntity<Map<String, String>> slow(
            @RequestParam(defaultValue = "8") int seconds)
            throws InterruptedException {
        int boundedSeconds = Math.min(Math.max(seconds, 0), 20);
        Thread.sleep(boundedSeconds * 1000L);
        return ResponseEntity.ok(Map.of(
            "result", "completed",
            "finishedAt", Instant.now().toString()
        ));
    }
}
~~~

**Lab endpoint giả lập chờ, không xử lý business transaction**. Không expose route này trên môi trường public/prod. Dùng @Profile để tách; phải xác minh cấu hình profiles của bản deploy không bật local-lab.

### Thử nghiệm bằng Docker

Terminal 1:

~~~bash
./mvnw -B clean verify
docker build -t orders-api:lab .
docker run -d --name orders-api \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local-lab \
  orders-api:lab
~~~

Terminal 2, sau khi readiness UP:

~~~bash
curl --silent --show-error -i \
  "http://localhost:8080/lab/slow?seconds=12"
~~~

Terminal 3, khi request đang chạy:

~~~bash
docker stop --time 45 orders-api
~~~

Sau khi stop:

~~~bash
docker logs orders-api
docker inspect orders-api --format '{{.State.ExitCode}}'
docker rm orders-api
~~~

**Giới hạn thử nghiệm:** Docker stop gửi tín hiệu và chờ process kết thúc theo Docker runtime, nhưng không mô phỏng chính xác Kubernetes endpoint deregistration/Ingress routing. Để đo zero-downtime với replicas, cần lab AKS/ACA hoặc routing layer tương đương. Một kết quả 200 từ request chậm là bằng chứng tốt cho case đó, **không chứng minh mọi race condition đã bị loại**.

## 42. Thử forced termination để chứng minh tính bền vững

Không nên chỉ thử shutdown "êm":

~~~text
Test A: SIGTERM và grace 45s
  -> Request chậm có thể hoàn tất nếu thời gian đủ.

Test B: SIGKILL/kill -9 trên container lab
  -> Không có @PreDestroy guarantee.
  -> Database/queue phải tự phục hồi bằng transaction/retry.
~~~

Trong **sandbox do bạn sở hữu**, có thể dùng:

~~~bash
docker kill --signal=SIGKILL orders-api
~~~

Chỉ chạy nếu container lab đã được tạo cho thử nghiệm và có dữ liệu giả, không chạy trên service production. Khi không có termination hook:

- DB transaction chưa commit phải rollback theo DB semantics.
- DB commit đã thành công nhưng HTTP response chưa tới client cần idempotency.
- Queue message chưa complete có thể được giao lại; worker phải dedup.
- File đang ghi vào local disk có thể bị dang dở, không dùng làm source of truth.

**Nếu test forced-kill làm mất đơn hàng hoặc gửi email trùng, không thể sửa chỉ bằng tăng graceful timeout.** Cần sửa business transaction, persistence, message settlement và replay design.

## 43. Quản lý signals trong Java và container entrypoint

Một cách kiểm tra đơn giản khi container khởi động:

~~~text
PID 1: java -jar /app/orders-api.jar  -> thường nhận SIGTERM trực tiếp

PID 1: /bin/sh start.sh
 PID 7: java -jar /app/orders-api.jar
  -> shell có thể không forward signal phù hợp
~~~

Khi dùng script, luôn xem xét **exec** để JVM thay thế shell:

~~~sh
#!/bin/sh
set -eu
exec java $JAVA_TOOL_OPTIONS -jar /app/orders-api.jar
~~~

**Cảnh báo:** ví dụ script trên có khả năng mở rộng biến theo shell, dễ sai escaping/word splitting khi JAVA_TOOL_OPTIONS chứa tham số phức tạp; Java runtime tự nhận JAVA_TOOL_OPTIONS từ môi trường, nên phương án an toàn hơn thường là:

~~~sh
#!/bin/sh
set -eu
exec java -jar /app/orders-api.jar
~~~

JAVA_TOOL_OPTIONS vẫn được JVM đọc theo cơ chế của Java. Dùng Dockerfile JSON-array ENTRYPOINT khi không cần script và luôn test signal behavior của base image thực.

### Có nên viết JVM shutdown hook riêng?

Chỉ khi có tài nguyên không được Spring quản lý và không tích hợp được qua bean lifecycle. Tránh trùng logic với @PreDestroy/DisposableBean/SmartLifecycle khiến race. Mọi bước cleanup phải có **timeout, idempotency và logging tối thiểu**.

## 44. Observability cho probes và shutdown

Để đánh giá hiệu quả, cần biết:

| Nhóm | Tín hiệu quan sát | Ý nghĩa |
|---|---|---|
| **Startup** | JVM start → liveness UP → readiness UP | Thời gian warm-up và cold start |
| **Readiness** | Probe success/failure, pod ready count | Traffic routing và rollback trigger |
| **Liveness** | Restart count, failure reasons | Crash, deadlock hoặc cấu hình sai |
| **HTTP** | 5xx, 429, connection resets, p95/p99 | Chất lượng trải nghiệm trong rollout |
| **Shutdown** | SIGTERM received, shutdown duration, force-kill | Thực tế grace budget |
| **Async** | In-flight jobs, queue depth, retry, dead-letter | Business completion khi scale-in |
| **DB** | Active/pending pool, transaction rollback | Downstream saturation và cleanup |
| **JVM** | Heap, RSS, GC pauses, native memory | OOM/false positive probe |
| **Cost** | Warm replicas, plan capacity, log ingestion | Chi phí của HA/probe thresholds |

**Azure Monitor, Application Insights, Container Insights, Log Analytics và Micrometer/OpenTelemetry** có thể phối hợp thu thập dữ liệu, nhưng không phải tất cả metrics trên đều là built-in counters của mọi nền tảng. Một số là **custom application events** cần instrumentation.

### Structured event log nên có

~~~json
{
  "event": "application_shutdown_started",
  "appVersion": "orders-api-1.0.0",
  "replicaRef": "pod-hash-opaque",
  "reason": "SIGTERM",
  "inFlightRequests": 7,
  "inFlightJobs": 2,
  "timestamp": "2026-11-20T10:00:00Z"
}
~~~

Đây là **event minh họa**; không giả định Spring Boot tự phát một JSON log như vậy hoặc luôn biết nguyên nhân chính xác của SIGTERM. Khi cần, thêm observation qua lifecycle hooks/metrics nhưng không ghi secrets, user payloads hoặc PII.

### Phân biệt deployment failures và app failures

Một **readiness failure** do DNS database có thể xuất hiện cạnh lỗi **image pull** hoặc **startup command**, nhưng cách khắc phục khác nhau. Liên kết appVersion/image digest, time window, pod events, ingress errors, health statuses và resource config để phân loại.

## 45. Chi phí và khả năng sẵn sàng

Tăng số replicas và kéo dài grace period có thể cải thiện khả năng chống gián đoạn, nhưng phát sinh trade-off:

- **minReplicas=2** thay vì 0/1 có chi phí compute nền tảng, giảm cold start/single replica risk.
- **maxSurge=1** cho rollout tạm cần thêm capacity node/container.
- StartupProbe có budget dài giúp tránh restart nhầm, nhưng rollout lỗi thật có thể phát hiện chậm hơn.
- Health Check với ít instances không thể tạo thêm dự phòng nếu không có compute khác.
- Log probe từng 5 giây với full JSON có thể làm tăng log ingestion đáng kể.
- Chờ drain quá lâu làm scale-in chậm và giữ nhiều replicas cùng lúc.

### Ví dụ ngân sách capacity

~~~text
Đơn vị giả định: mỗi replica cần 1 CPU + 1.5 GiB RAM
  Production steady state: 3 replicas
  RollingUpdate maxSurge:  1 replica
  Peak trong rollout:      4 replicas
~~~

Nền tảng/node phải có chỗ cho **4 replicas** khi rollout; nếu không, pod mới có thể Pending và rollback/deployment stall. Với AKS, thêm capacity nodes có thể phát sinh chi phí. Với Container Apps, scale, consumption/workload profile pricing tùy plan. **Đây là sizing lý thuyết, không phải bảng giá**.

## 46. Tình huống A: deployment mắc CrashLoopBackOff

**Bối cảnh:** AKS deployment mới vừa lên, pods hiện **CrashLoopBackOff** sau khi liveness fail.

### Các nguyên nhân khả dĩ

1. Spring Boot startup cần 80 giây nhưng liveness bắt đầu quá sớm.
2. Probe gọi port 80 trong khi Java lắng nghe 8080.
3. Endpoint /actuator/health/liveness bị trả 401/302.
4. Container bị OOMKilled vì memory limit nhỏ.
5. Runtime JDK không tương thích compiled bytecode.
6. Spring Boot startup thất bại vì missing env/DB credential.

### Runbook

~~~bash
kubectl describe pod <POD_NAME> -n <LAB_NAMESPACE>
kubectl logs <POD_NAME> -n <LAB_NAMESPACE> --previous
kubectl get deployment orders-api -n <LAB_NAMESPACE> -o yaml
~~~

Sau đó phân loại:

- **Startup lâu nhưng sẽ thành công:** thêm startupProbe, chỉnh budget dựa đo đạc.
- **Port/path sai:** sửa probe, targetPort và cấu hình Spring.
- **401/302:** sửa security/mgmt routing và hạn chế exposure.
- **OOMKilled:** đo heap/non-heap/RSS, tăng memory hoặc tối ưu app.
- **NoClassDefFoundError/UnsupportedClassVersionError:** sửa build/runtime JDK.
- **Missing secret:** sửa managed identity/config, không embed password vào image.

**Đừng tăng failureThreshold tới một con số rất lớn để che JVM crash lặp**; startupProbe chỉ có ích nếu app thực sự đang khởi động và cuối cùng sẵn sàng.

## 47. Tình huống B: App Service Health Check trả 401

**Bối cảnh:** Spring Boot dùng Spring Security. App vẫn trả response bình thường khi đăng nhập, nhưng Health Check liên tục đánh dấu instance unhealthy.

### Điều tra

1. Kiểm tra **Health Check path** đã cấu hình trong App Service.
2. Gọi endpoint từ network phù hợp, quan sát HTTP status, redirect chain.
3. Xem Spring SecurityFilterChain matchers và thứ tự xử lý path.
4. Kiểm tra Actuator base path nếu ứng dụng đổi **management.endpoints.web.base-path**.
5. Xác nhận URL/probe dùng port/hostname thực của app.
6. Nếu health URL là HTTP proxy path, kiểm tra rewrite và authentication tại gateway.

### Sửa

Cho phép đúng health path trả trạng thái tối thiểu (không yêu cầu user login), kiểm soát truy cập bằng network/access restrictions khi cần. Không mở **/actuator/** cho mọi endpoint như heapdump, env, loggers hoặc shutdown chỉ vì health cần truy cập.

**Không dùng 302 tới /login hoặc HTML "service unavailable" với HTTP 200** để báo healthy; platform có thể hiểu sai tình trạng thực.

## 48. Tình huống C: rolling update có 5xx dù tất cả pods Ready

**Bối cảnh:** Trong lúc deploy orders-api v2, có một số request nhận HTTP 502/503 hoặc connection reset. Kubernetes cho thấy old pods và new pods phần lớn Ready.

### Có thể do

- EndpointSlice/ingress upstream removal propagation trễ.
- JVM nhận SIGTERM và dừng connector trước khi gateway ngừng gửi request mới.
- Liveness/readiness xanh nhưng thread pool quá tải.
- Keep-alive/HTTP/2 connection vẫn chạm pod cũ.
- New version dùng DB schema không tương thích với old version.
- Rollout maxSurge thiếu node capacity, new pod còn Pending.

### Runbook theo thứ tự

1. Chụp mốc thời gian: rollout begin, pod terminating, SIGTERM, failed requests.
2. So ingress 5xx với Java logs/traces và network resets.
3. Xem readiness transitions, EndpointSlice conditions, ingress logs.
4. Đo shutdown elapsed time; tìm force-kill hoặc timeout.
5. Thử **preStop drain delay ngắn** trong sandbox, đo lại, không tăng vô hạn.
6. Xem **maxUnavailable, maxSurge, minReadySeconds, terminationGracePeriodSeconds**.
7. Kiểm tra DB schema compatibility hai versions.
8. Thử client retry/idempotency cho requests bị cắt.

**Không mặc định maxUnavailable=0 đảm bảo không có 5xx.** Zero-downtime là một kết quả đo thực ở nhiều tầng, không là một cờ Kubernetes đơn lẻ.

## 49. Tình huống D: worker tạo hóa đơn trùng khi scale-in

**Bối cảnh:** Spring Boot worker nghe Service Bus queue, tạo invoice trong database và gửi email. Azure Container Apps giảm từ 4 replicas xuống 1; một message được broker giao lại.

### Vấn đề

Worker hoàn thành **DB commit** nhưng container dừng trước broker settle; worker mới xử lý lại message và tạo invoice thứ hai.

### Thiết kế đúng

~~~text
Message eventId + tenantId
     |
     v
Database unique constraint (tenantId,eventId)
     |
     +-- Already processed -> safe replay / no duplicate
     |
     +-- New -> create invoice + outbox email event
                     |
                     v
                 Commit transaction
                     |
                     v
                Complete queue message
~~~

Nếu email là side effect bên ngoài DB, dùng **outbox + sender idempotency/dedup policy** thay vì giả định "gửi thành công" và "queue complete" nằm trong một transaction chung.

### Kiểm tra

- Scale down trong lúc worker xử lý.
- Force-kill sau commit trước complete trong **mock/sandbox**.
- Gửi lại cùng eventId.
- Xem database unique constraint và số email thực.
- Đảm bảo không biến duplicate thành endless retries.

**Graceful shutdown làm giảm cơ hội đứt đoạn, nhưng không thay business idempotency.**

## 50. Tình huống E: health endpoint UP nhưng ứng dụng không phục vụ được

**Bối cảnh:** /actuator/health/liveness trả 200, nhưng API trả 503 vì HikariCP pool exhausted hoặc database chậm.

### Vì sao

Liveness chỉ trả lời "process còn sống"; app vẫn có thể không đáp ứng nghiệp vụ. Nếu readiness group chỉ có readinessState và không biết local pool saturation, nó cũng có thể trả UP.

### Cách giải quyết

1. Thu metrics **Hikari active/idle/pending/timeout**, p95 query latency.
2. Đặt connection/transaction timeouts, circuit breaker khi cần.
3. Xác định có phải shared DB outage hay instance cục bộ lỗi.
4. Cân nhắc custom readiness indicator **rất nhẹ** nếu sự cố chỉ ảnh hưởng một instance và tác động mọi request.
5. Không thêm database vào liveness.
6. Dùng synthetic business transaction test có tần suất/chi phí an toàn.
7. Đặt alerts cho business error rate/latency độc lập health status.

**Health check không phải phép thử đầy đủ tính đúng đắn của nghiệp vụ.** Một API có thể healthy về kỹ thuật nhưng sai authorization, schema hoặc domain logic.

## 51. Tình huống F: JVM thoát sớm dù đã bật graceful shutdown

**Bối cảnh:** Có cấu hình server.shutdown=graceful và timeout 30s, nhưng Spring Boot container dừng gần như ngay khi Azure scale-in, request 10s bị cắt.

### Nguyên nhân cần kiểm tra

- Entrypoint dạng shell không forward SIGTERM hoặc tín hiệu đến process khác.
- Host termination grace nhỏ hơn request duration.
- Spring Boot không dùng runtime/web server version như dự kiến.
- Process bị OOMKilled/SIGKILL, không có cơ hội graceful.
- Server đã dừng nhưng @Async/business job không nằm trong lifecycle được quản lý.
- Ứng dụng tự gọi System.exit trong handler.
- Một health-check restart đã xảy ra, không phải rollout bình thường.

### Chẩn đoán

~~~text
Container start command / PID 1
        |
        v
Signal nhận được? SIGTERM hay SIGKILL?
        |
        v
Spring Boot shutdown logs/lifecycle events có chạy?
        |
        v
Elapsed time vs platform grace
        |
        v
In-flight request / worker state / DB commit outcome
~~~

**Không thể khắc phục SIGKILL hoặc mất node bằng cấu hình Spring Boot**. Nếu host cưỡng bức chết, thiết kế phải có durable recovery và idempotency.

## 52. Kiểm thử tự động và release gates trong CI/CD

Một pipeline nên xác minh **cả artifact và lifecycle**, không chỉ compile:

~~~mermaid
flowchart TD
    A[Commit Java + config] --> B[Maven verify + security scan]
    B --> C[Build OCI image nếu cần]
    C --> D[Run container local + health probes]
    D --> E[Simulate SIGTERM during slow request]
    E --> F[Simulate forced kill + idempotency]
    F --> G[Deploy staging Azure]
    G --> H[Verify ingress/readiness/startup]
    H --> I[Rolling rollout / revision test under load]
    I --> J{SLO + errors + secrets checks pass?}
    J -- No --> K[Stop and investigate]
    J -- Yes --> L[Promote approved artifact]
    L --> M[Monitor + rollback plan]
~~~

### Các test có thể tự động hóa

| Test | Điều kiện đạt |
|---|---|
| **Artifact build** | Build sạch, tests pass, executable JAR chạy |
| **Image execution** | Non-root, đúng JDK/port, không lộ secrets |
| **Startup** | Liveness/readiness chuyển trạng thái theo lifecycle trong budget |
| **Readiness** | Instance chưa ready không nhận traffic qua route đã kiểm thử |
| **Liveness** | External DB outage không gây restart toàn bộ instances |
| **Graceful SIGTERM** | Request ngắn còn đang xử lý hoàn tất nếu nằm trong budget |
| **Forced termination** | Idempotent retry, durable state đúng |
| **Rolling update** | Không tăng lỗi 5xx vượt ngưỡng canary |
| **Security** | Health công bố tối thiểu, business API yêu cầu auth |
| **Regression** | Old/new app versions cùng chạy tương thích DB/event schema |
| **Observability** | Có startup/shutdown, trace, errors và resource metrics |
| **Cost** | Replicas, surge/warm capacity trong ngân sách |

### Release gates cần rõ

- Có **commit SHA + immutable artifact/image digest**.
- p95 latency, 5xx, restart rate và process shutdown duration trong ngưỡng được chấp nhận.
- Không có secret leakage/critical unaddressed CVEs theo policy.
- Database/queue compatibility tests pass.
- Cấu hình health/port/grace được review như một phần deployment.
- Có rollback đã thử, không chỉ viết trên giấy.

**Không chạy fault injection trên production** nếu chưa có change approval và phương án hạn chế tác động; ưu tiên staging/sandbox với dữ liệu giả lập.

## 53. Bài thực hành end-to-end: deploy Spring Boot không làm đứt request

### Bối cảnh

Bạn là developer của **Orders API**. Ứng dụng phải:

- Chạy Java 21, Spring Boot 3.x trên **OCI image**.
- Có **/actuator/health/liveness** và **/actuator/health/readiness**.
- Dùng **server.shutdown=graceful** và timeout-per-shutdown-phase đã đo.
- Chạy ít nhất **hai replicas** ở lab AKS hoặc Container Apps với cấu hình nền tảng được hỗ trợ.
- Deploy ứng dụng mới mà không khiến các requests ngắn thất bại ngoài ngưỡng lab.
- Khi bị cưỡng bức kill, retry POST không tạo bản ghi business trùng.

Nếu không có quyền/budget Azure, có thể thực hiện **build/container/SIGTERM tests local** và viết deployment manifest/ADR để giải thích việc kiểm thử trên Azure. Không tạo AKS cluster chỉ vì bài lab yêu cầu so sánh; dùng sandbox được cấp hoặc mô phỏng.

### Phần A — Chuẩn bị project

Tạo một Spring Boot web app tối thiểu với:

- Spring Web.
- Spring Boot Actuator.
- Spring Security nếu muốn kiểm tra auth rules.
- Một endpoint GET /api/ping.
- Một endpoint **/lab/slow** chỉ bật trong profile local-lab.
- Một POST endpoint giả có hỗ trợ **Idempotency-Key** nếu làm phần nâng cao.

Ví dụ controller đơn giản:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok", "time", Instant.now().toString());
    }
}
~~~

Đây là class riêng trong Spring Boot project, cần main application class và Maven/Gradle dependencies. Nếu dùng Spring Security, cấu hình /api/ping theo auth policy; không tự mở public API endpoint khi production yêu cầu JWT.

### Phần B — Đóng gói JAR và image

~~~bash
./mvnw -B clean verify
test -f target/orders-api.jar
docker build -t orders-api:lab .
~~~

Lệnh **test -f** dành cho shell Bash/Linux và giả định Maven finalName=orders-api. Trên PowerShell tương đương có thể dùng **Test-Path target/orders-api.jar**. Để đảm bảo image sẵn sàng:

~~~bash
docker run -d --name orders-api-lab \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local-lab \
  orders-api:lab

curl --fail --silent --show-error \
  http://localhost:8080/actuator/health/liveness

curl --fail --silent --show-error \
  http://localhost:8080/actuator/health/readiness
~~~

Nếu nhận 404, kiểm tra Actuator dependency, health probes configuration và profile. Nếu nhận 401/403, kiểm tra SecurityFilterChain. Nếu kết nối không thành công, kiểm tra port/entrypoint/JDK/container logs.

### Phần C — Kiểm tra startup timing

Ghi **bốn thời điểm**:

~~~text
T0 = Container/pod start time
T1 = JVM start / first application log
T2 = Liveness first UP
T3 = Readiness first UP

startupDuration = T3 - T0
~~~

Tất cả là mốc đo từ cùng hệ thống đồng hồ/telemetry đáng tin; nếu lấy dữ liệu nhiều hệ thống khác nhau, cần xem clock skew và sampling interval. So sánh ít nhất 5 lần trong sandbox, hoặc ghi rõ sample count nhỏ nếu môi trường hạn chế.

### Phần D — Test SIGTERM có request đang xử lý

1. Dùng **/lab/slow?seconds=12** và bắt đầu một request.
2. Trong lúc request chờ, gửi **docker stop --time 45**.
3. Ghi HTTP status và response time.
4. Kiểm tra container exit code và log shutdown.
5. Nếu request thất bại, phân loại: request đã hoàn tất trước stop? client timeout? app shutdown ngay? host force-kill?
6. Lặp lại với request dài hơn deadline và ghi kỳ vọng/giới hạn.

**Đừng cố chứng minh zero-downtime bằng request bị cắt quá deadline.** Mục tiêu là hiểu hành vi và thiết kế async/idempotency cho requests không thể hoàn tất trong thời gian dừng.

### Phần E — Thử AKS hoặc ACA trong sandbox

Với **AKS**:

- Dùng Deployment/Service ở mục 21, thay đúng image, namespace và các quyền.
- Bật 2–3 replicas, startup/readiness/liveness probes.
- Đặt maxUnavailable=0 và một mức maxSurge hợp lý cho cluster capacity.
- Kiểm tra EndpointSlices, pod events, rollout status.
- Triển khai revision/image mới trong khi chạy request test có giới hạn.
- Ghi 5xx/connection resets và shutdown duration.

Với **Container Apps**:

- Deploy image lên lab Container App/environment với ingress/targetPort đúng.
- Khai báo probes theo schema ACA được hỗ trợ.
- Dùng revisions và kiểm tra traffic routing khi version mới ready.
- Đặt minReplicas phù hợp nếu muốn loại tác động scale-to-zero khỏi thử nghiệm rollout.
- Thử scale-in khi có request trong chừng mực sandbox cho phép.

**Không tự ý xoá pods/nodes hoặc thay ingress/network trên cluster dùng chung/production** để tạo lỗi. Nếu không có quyền, mô tả kế hoạch thử và lập kết quả expected vs measured.

### Phần F — Thử degraded dependency

Giả lập **database unavailable** trong test configuration hoặc mock service:

1. Liveness **không** nên fail chỉ vì external DB không sẵn sàng.
2. Readiness có thể fail **nếu chính sách của app coi DB là bắt buộc**; ghi rõ vì sao.
3. Business HTTP endpoints trả lỗi/timeout được kiểm soát, không treo mãi.
4. Worker có backoff, retry/quarantine theo broker.
5. Khi DB phục hồi, ứng dụng không tạo reconnect storm.

Mục đích là xác nhận probe policy, không phải làm hỏng database thật.

### Phần G — Test forced-kill và retry

Trong local mock/durable test DB:

1. Gửi POST /orders với idempotency key.
2. Cưỡng bức kill trong một mốc tiến trình mô phỏng.
3. Gửi lại cùng request/key.
4. Kiểm tra số lượng orders, outbox entries và response contract.
5. Test nếu client gửi cùng key nhưng payload khác: phải từ chối/conflict theo policy.

**Không được tạo giao dịch tiền/đơn hàng thật khi thử nghiệm**. Sử dụng sample data và sandbox database.

### Phần H — Báo cáo bằng chứng

| Bằng chứng | Giá trị cần ghi |
|---|---|
| Commit SHA/artifact checksum/image digest | Giá trị đã kiểm chứng |
| JDK/Spring Boot versions | Phiên bản thực tế |
| Azure platform + SKU/region | App Service/ACA/AKS/VM theo lab |
| Replica count/resource limits | Values đã deploy |
| Startup probe thresholds | Period, failureThreshold, timeout |
| Readiness/liveness paths | HTTP codes + timing |
| Graceful config | server.shutdown, Spring phase timeout |
| Host termination deadline | Values thực cấu hình |
| Slow request outcome | HTTP status + latency + logs |
| Forced kill outcome | DB/queue idempotency evidence |
| Rolling release outcome | 5xx count, restarts, time to ready |
| Security | Secret exposure NONE, health limited |
| Cost | Compute/replica, logs/ingress, cleanup |

### Phần I — Cleanup an toàn

- Chỉ xóa **container lab** và resources được phép sở hữu.
- Xóa/đóng test instances, staging revisions hoặc nodes theo chính sách.
- Giữ logs/correlation sample đã redaction cho learning evidence nếu được phép.
- Kiểm tra Azure Cost Management vì App Service plan, Container Apps environment, AKS nodes, ACR, logging có thể còn tính phí.
- Không xóa cluster/registry/namespace dùng chung của nhóm khác.

## 54. Checklist production-ready

- [ ] Artifact **executable JAR** hoặc OCI image đã được build/test từ commit xác định.
- [ ] JDK/Spring Boot versions còn được hỗ trợ, nhất quán CI và runtime Azure.
- [ ] Image base đã scan, không có secrets và chạy non-root khi khả thi.
- [ ] Docker entrypoint truyền SIGTERM trực tiếp tới JVM, không bỏ signal trong shell.
- [ ] Port, ingress targetPort, Service/Health Check path đã được kiểm chứng.
- [ ] Actuator health probes bật và trả response tối thiểu, không tiết lộ stacktrace/secret.
- [ ] SecurityFilterChain cho đúng health path, các business endpoints vẫn được bảo vệ.
- [ ] Liveness phản ánh process health, không phụ thuộc DB/external API chung.
- [ ] Readiness phản ánh khả năng nhận traffic, có policy được review cho dependencies.
- [ ] Startup probe thresholds dựa trên startup p95/p99 trong environment tương đương.
- [ ] Health trên main application port hoặc có synthetic check kiểm chứng traffic path.
- [ ] Có **server.shutdown=graceful**, phase timeouts và host termination deadline phù hợp.
- [ ] Shutdown deadline tính preStop, in-flight work và headroom; được đo thực tế.
- [ ] Không dùng @PreDestroy sleep vô hạn, System.exit hoặc actuator shutdown public.
- [ ] Custom threads/schedulers/clients có lifecycle đóng sạch và timeout.
- [ ] Long-running business jobs đã có durable queue/checkpoint thay vì chỉ RAM.
- [ ] Service Bus/Kafka consumers ngừng intake, commit/checkpoint/settle đúng thứ tự.
- [ ] Có idempotency cho POST và broker redelivery sau forced kill.
- [ ] HTTP streaming/WebSocket clients có reconnect/resync strategy.
- [ ] Database pooling không vượt connection capacity khi autoscale/rollout surge.
- [ ] AKS Deployment có strategy, probes, grace, resource requests/limits đúng.
- [ ] AKS PDB/zone-spread/ingress được kiểm chứng nếu yêu cầu HA.
- [ ] ACA probes/revisions/ingress và scale-in behavior đã được thử.
- [ ] App Service Health Check, slot settings và warm-up được smoke test.
- [ ] VM/systemd stop timeout và Load Balancer probes tương thích lifecycle.
- [ ] Azure Functions triggers được xử lý theo host lifecycle, không giả định Actuator.
- [ ] CI/CD có SIGTERM, forced-kill và rolling release tests ở sandbox.
- [ ] Metrics/alerts đo 5xx, restart, readiness, startup time, in-flight jobs và shutdown time.
- [ ] Đã có rollback/runbook và schema compatibility giữa versions cũ–mới.
- [ ] Sizing compute/replicas có tính maxSurge, warm capacity và chi phí logs.
- [ ] Không dùng tài nguyên production hoặc dữ liệu thật để fault-inject khi chưa được duyệt.

## 55. Câu hỏi tự kiểm tra

1. Executable Spring Boot JAR khác plain JAR và WAR ở những điểm nào?
2. Tại sao một OCI image có EXPOSE 8080 không tự mở public port?
3. Dùng ENTRYPOINT JSON-array có ích gì cho tín hiệu SIGTERM?
4. Vì sao non-root container cần kiểm tra file permissions và thư mục tạm?
5. JDK mismatch có thể thể hiện qua lỗi nào?
6. JVM heap chiếm toàn bộ memory limit có nguy cơ gì?
7. Readiness, liveness và startup probes có ba mục tiêu gì?
8. Một ứng dụng Running nhưng không Ready có nên nhận request qua Service không?
9. Vì sao liveness không nên gọi shared PostgreSQL?
10. Khi nào DB check có thể phù hợp trong readiness?
11. management.server.port riêng có thể che lỗi gì ở main app port?
12. Health endpoint có nên public hóa full Actuator env/heapdump không?
13. Vì sao HTTP 302 tới login là vấn đề đối với App Service Health Check?
14. Startup probe failureThreshold × periodSeconds giúp điều gì?
15. Vì sao phải đo thời gian khởi động Spring Boot thay vì chọn thresholds tùy ý?
16. readinessProbe false có restart pod không, khác liveness thế nào?
17. maxUnavailable=0 có đảm bảo tuyệt đối zero downtime không?
18. preStop hook dùng thời gian của termination grace hay được cộng thêm?
19. Một image distroless cần chú ý gì nếu preStop dùng /bin/sh?
20. Readiness thay đổi có đến ngay mọi ingress/gateway không?
21. Spring Boot cấu hình graceful shutdown bằng những properties nào?
22. timeout-per-shutdown-phase có bằng tổng shutdown deadline không?
23. Vì sao không gọi System.exit trong @PreDestroy?
24. SIGKILL/oom/node outage có đảm bảo chạy shutdown hook không?
25. Khi nào ThreadPoolTaskExecutor wait-for-tasks có ích và khi nào nguy hiểm?
26. @Scheduled chạy trên nhiều replicas tạo vấn đề gì?
27. Worker commit DB nhưng chưa complete message thì điều gì có thể xảy ra?
28. Vì sao Idempotency-Key cần ràng buộc user, tenant và request payload?
29. WebSocket có tiếp tục sống mãi khi pod bị thay thế không?
30. Khi nào nên tách HTTP request dài thành durable asynchronous job?
31. API có liveness UP nhưng 503 business có mâu thuẫn không?
32. App Service Health Check khác readiness của Kubernetes ở điểm nào?
33. Container Apps revisions giúp canary và rollback ra sao?
34. AKS PDB có chống được forced OOM kill không?
35. Vì sao App Service slot swap cần kiểm tra effective settings và DB credentials?
36. VM systemd TimeoutStopSec cần phối hợp với Spring phase timeout thế nào?
37. Azure Functions Service Bus trigger có cần một Tomcat actuator endpoint không?
38. Những metrics nào dùng để đánh giá graceful shutdown trong rollout?
39. Nếu image version mới cần database schema thay đổi, rollback code có đủ không?
40. Một bài kiểm thử local Docker stop chứng minh gì và chưa chứng minh gì?

## 56. Tài liệu tham khảo

- [Spring Boot production-ready features](https://docs.spring.io/spring-boot/reference/actuator/index.html) — Actuator, health, metrics và probes.
- [Spring Boot Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) — ApplicationAvailability, liveness/readiness.
- [Spring Boot graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — server shutdown, lifecycle timeout.
- [Spring Framework TaskExecutor and scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — async tasks, scheduling, executor lifecycle.
- [Azure App Service for Java](https://learn.microsoft.com/azure/app-service/configure-language-java) — hosting Java, startup và application configuration.
- [Azure App Service Health Check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check) — health probe integration.
- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — warm-up/swap và settings.
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview) — environments, replicas và revisions.
- [Azure Container Apps health probes](https://learn.microsoft.com/azure/container-apps/health-probes) — container-level readiness/liveness/startup.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — staged releases, traffic splits.
- [AKS introduction](https://learn.microsoft.com/azure/aks/intro-kubernetes) — managed Kubernetes.
- [Kubernetes liveness, readiness and startup probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — probe semantics.
- [Kubernetes Pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) — SIGTERM, hooks, grace period và forced termination.
- [Kubernetes Deployment rolling updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — rollout strategy/availability.
- [Kubernetes PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/) — voluntary disruptions.
- [Azure Functions Java developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java Functions hosting/lifecycle.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs và alerts.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — chi phí plan/nodes/replicas.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, security, operations, performance, cost.

**Kết luận:** Đóng gói Spring Boot thành JAR hoặc OCI image mới là bước đầu. Một phiên bản sẵn sàng cho Azure cần **health probes có ý nghĩa, application readiness chính xác, JVM nhận SIGTERM, graceful shutdown có deadline thực tế, workers có checkpoint/idempotency và rollout được kiểm thử dưới tải**. App Service, Container Apps, AKS, VM và Functions có lifecycle khác nhau, vì vậy không sao chép nguyên cấu hình nền tảng này sang nền tảng kia. Hãy kiểm thử **startup bình thường, readiness không đạt, shared dependency outage, SIGTERM có request đang chạy và forced termination** trên sandbox; đo metrics, review bảo mật và chi phí rồi mới quyết định production. Mục tiêu không phải một dashboard luôn xanh, mà là ứng dụng **nhận đúng traffic khi sẵn sàng, dừng có trật tự khi được yêu cầu, và phục hồi đúng nghiệp vụ khi không kịp dừng**.
