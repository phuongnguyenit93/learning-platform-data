# Quan sát bảo mật bằng log, metric và trace theo phiên bản hỗ trợ — Spring Security Servlet

> **Phạm vi:** Vận hành ứng dụng Spring Security chạy trên **Servlet/Spring MVC**, đặc biệt Spring Boot 3.x + Spring Security 6.x + Micrometer/Actuator (Java 17+). Nội dung nêu cách thu thập và liên kết **security logs, metrics và distributed traces**, cách theo dõi xác thực/phân quyền, nguyên tắc không làm lộ credential hoặc dữ liệu định danh, cùng yêu cầu kiểm tra **khả năng hỗ trợ theo đúng phiên bản**. Phần mã đầy đủ tập trung vào **những API công khai ổn định**; những tên metric/observation do framework tự sinh có thể thay đổi giữa version và phải được xác nhận từ ứng dụng thực chạy.

## 1. Vì sao cần security observability?

Một lỗi bảo mật trong vận hành thường không thể được trả lời chỉ bằng câu hỏi “HTTP trả 401 hay 403?”. Cần biết:

- Có bao nhiêu lần **authentication thất bại** trong một khoảng thời gian? Có tăng đột biến không?
- Thất bại xuất phát từ **bad credentials**, token hết hạn, khóa JWT không hợp lệ, CSRF hay **thiếu authority**?
- Một request đã được xác thực nhưng vì sao bị **403**?
- Một thay đổi cấu hình SecurityFilterChain có làm các endpoint quan trọng bỗng trả **200/302/401/403** khác trước không?
- Một người dùng gửi request qua gateway, backend và database; request nào tương ứng với log và trace nào?
- Bộ lọc xác thực hoặc việc gọi IdP/introspection có tăng latency sau khi triển khai bản phát hành mới?
- Có hành vi giả mạo header, retry đăng nhập liên tục hoặc truy cập trái quyền tăng đột biến không?
- Dữ liệu trong log/metric/trace có đang vô tình chứa password, Authorization header, session cookie hoặc access token không?

**Security observability** là khả năng dùng tín hiệu từ một hệ thống đang hoạt động để hiểu diễn biến và quyết định bảo mật của nó. Nó bổ trợ cho kiểm thử và audit, **không** tự thay thế authentication, authorization, SIEM, WAF hay các biện pháp ngăn chặn tấn công.

Ba loại tín hiệu có thế mạnh khác nhau:

| Tín hiệu | Câu hỏi trả lời tốt | Thí dụ | Hạn chế |
| --- | --- | --- | --- |
| **Log** | “Sự kiện gì đã xảy ra?” | `authentication_failed`, `authorization_denied`, thời điểm, reason code, request ID | Chi phí lưu trữ, nguy cơ rò PII/token, phải chuẩn hóa schema |
| **Metric** | “Tần suất, độ trễ và xu thế thay đổi ra sao?” | Số lần auth thất bại, tỷ lệ 401/403, latency, timeout của IdP | Bị bùng nổ cardinality nếu đặt user ID/token/URL động thành tag |
| **Trace** | “Yêu cầu này đi qua những thành phần nào và mất thời gian ở đâu?” | Ingress → filter chain → controller → service → IdP | Sampling có thể bỏ sót; trace không phải audit log toàn vẹn |

**Không có một hệ duy nhất giải quyết mọi thứ:** metric cho cảnh báo, log cho điều tra sự kiện, trace cho quan hệ nhân quả và latency. Một sự kiện đăng nhập thất bại nghiêm trọng nên có **security event có cấu trúc**, metric counter để phát hiện tăng bất thường và correlation ID để nối với trace khi tồn tại.

## 2. Kiến trúc tín hiệu trên Spring Security Servlet

~~~text
[Client / browser]
       |
       v
[Gateway / reverse proxy / IdP integration]
       |
       | request ID / trace context đã được xác minh
       v
[Servlet container]
       |
       +--> Micrometer HTTP server observation
       |      http.server.requests (tùy cấu hình/phiên bản)
       |
       v
[FilterChainProxy / SecurityFilterChain]
       |
       +--> Authentication filters / providers
       |      - form login, HTTP Basic, Bearer JWT, OAuth2/OIDC ...
       |      - authentication success/failure events
       |
       +--> AuthorizationFilter / access decisions
       |      - permit / deny, 401 / 403
       |
       +--> CSRF / session / exception handling
       |
       v
[Spring MVC controller]
       |
       v
[Business service / database / outbound HTTP / IdP]
       |
       +--> application observations / network spans
       |
       v
[HTTP response]

LOGS  -> central log pipeline / audit store
METRIC -> MeterRegistry -> Prometheus / monitoring
TRACE  -> ObservationRegistry -> tracer/exporter -> trace backend
~~~

Các tên như `http.server.requests` thường là **HTTP server instrumentation từ Spring Boot/Micrometer**, **không phải mặc định mọi hoạt động Spring Security đều tạo metric riêng**. Một số phiên bản Spring Security có tích hợp Micrometer Observation bên trong filter chain; mức độ và tên instrumentation thay đổi theo dependencies và bản phát hành.

Vì vậy một quy trình tốt bắt đầu từ **xác minh thực tế**, chứ không đoán tên metric theo trí nhớ:

1. Xác định Spring Boot/Spring Security/Micrometer versions đang chạy.
2. Xác nhận Actuator và registry/exporter đã được cài.
3. Xác nhận security instrumentation có hỗ trợ trên tổ hợp phiên bản đó.
4. Tạo request mẫu hợp lệ và bị từ chối.
5. Kiểm **tín hiệu thực tế xuất hiện** trong log/`/actuator/metrics`/trace backend.
6. Xây dashboard/alert theo **metric names và tags đã quan sát và được hỗ trợ**, không hardcode những names tưởng tượng.

## 3. Theo phiên bản hỗ trợ: đừng trộn ba thế hệ công cụ

### 3.1. Tư duy version matrix

| Nền tảng | Hướng tích hợp | Điều cần kiểm trước khi sử dụng |
| --- | --- | --- |
| **Spring Boot 2.x / Spring Security 5.x** | Actuator/Micrometer metrics; một số hệ dùng Spring Cloud Sleuth để tracing. | Không copy nguyên cấu hình Micrometer Tracing hoặc Observation integration của Boot 3.x; API, dependency và tên observation không đồng nhất. |
| **Spring Boot 3.x / Spring Security 6.x** | Micrometer Observation và Micrometer Tracing là hướng tích hợp phổ biến; Spring Security có các điểm tích hợp observability tùy bản 6.x. | Kiểm chính xác Boot minor version, Spring Security minor, Actuator, registry, tracing bridge và auto-configuration. |
| **Phiên bản Spring Boot/Security mới hơn hoặc custom stack** | Phải dựa vào release notes, reference documentation và tính năng được công bố của **đúng tổ hợp đang triển khai**. | Không mặc định mọi metric/filter observation từ bản cũ vẫn giữ nguyên name/tag/semantics. |

**Không ép ứng dụng nâng cấp** chỉ để lấy một metric có thể thu thập bằng application events; nhưng cũng đừng viết hàng loạt custom filters chỉ vì quên kiểm khả năng instrument sẵn của framework.

Trong hệ thống có dependency management do Spring Boot BOM quản lý, ưu tiên dùng **phiên bản Micrometer và Spring Security do Boot quản lý** thay vì khai báo ngẫu nhiên các versions độc lập. Khi override versions, cần test compatibility rõ ràng.

### 3.2. Cách kiểm tra một version thực tế

Với Maven project, các lệnh thường dùng:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Trong output, tìm:
- `spring-boot-actuator` và `spring-boot-actuator-autoconfigure`;
- `spring-security-web`, `spring-security-config`, `spring-security-core`;
- `micrometer-core`, `micrometer-observation`;
- exporter như `micrometer-registry-prometheus`;
- tracing bridge (ví dụ `micrometer-tracing-bridge-otel` hoặc Brave bridge);
- OpenTelemetry/Zipkin/OTLP exporter tương ứng.

Với Gradle có thể dùng `./gradlew dependencies --configuration runtimeClasspath`. Không suy từ một dependency “đã nằm trên classpath” rằng mọi security filter tự được instrument; cần kiểm **bean/auto-configuration**, actual runtime và báo cáo tín hiệu.

### 3.3. Tên metric/observation nào ổn định?

Từ hệ sinh thái Spring Boot Actuator/Micrometer, `http.server.requests` là một tên HTTP server metric/observation thường gặp trong Boot 3.x. Các **Spring Security observation names** có thể xuất hiện với tiền tố `spring.security.*`, chẳng hạn những thành phần liên quan filter chains và authorization, nhưng **không cam kết cùng tên và tags trên mọi 6.x minor**.

Không xây alert production như “`spring.security.http.requests` chắc chắn tồn tại ở mọi bản” khi chưa quan sát runtime. Thay vào đó:
- đọc tài liệu **đúng version** của Spring Security cho mục *Observability*;
- xác nhận có Micrometer `ObservationRegistry` được auto-wire vào security infrastructure;
- xem tên từ `/actuator/metrics` hoặc monitoring backend;
- viết một smoke test sau nâng cấp để bắt metric/observation biến mất;
- quản lý dashboard như code, gắn với version release.

Nếu không có metric built-in cần thiết, có thể bổ sung **custom low-cardinality counter** dựa trên authentication events hoặc policy events. Cách này dùng tên do ứng dụng tự quy định nên dễ quản lý hơn.

## 4. Security log: ghi một sự kiện đủ dùng, không ghi bí mật

### 4.1. Mô hình log có cấu trúc

Một sự kiện audit cần thông tin có thể tra cứu, ví dụ:

~~~json
{
  "event_type": "authentication",
  "outcome": "failure",
  "reason": "bad_credentials",
  "service": "checkout-api",
  "environment": "prod",
  "request_id": "req-6f9a",
  "trace_id": "trace-example",
  "timestamp": "2026-11-06T11:25:30Z"
}
~~~

Đây là **schema minh họa**, không phải log đã thu từ hệ thống thật. `request_id` và `trace_id` chỉ nên được gắn khi có nguồn đáng tin/có kiểm tra; “tự do nhận nguyên header từ client” có thể tạo log injection hoặc correlation giả.

Các trường thường hữu ích:

- `event_type`: nhóm cố định, như `authentication`, `authorization`, `session`, `logout`, `csrf`, `token_validation`.
- `outcome`: `success`, `failure`, `denied`, `error` theo schema rõ ràng.
- `reason`: reason code **ổn định và đã chuẩn hóa** như `bad_credentials`, `token_expired`, `missing_authority`, `csrf_invalid`.
- `timestamp`, `service`, `deployment`, `request_id`/`trace_id` khi có.
- `route_template`: ví dụ `/api/orders/{orderId}` thay vì path có ID thật.
- `actor_reference`: chỉ khi cần và được chính sách privacy/audit cho phép; có thể dùng ID nội bộ đã bảo vệ, HMAC hoặc lưu tại kho audit riêng.

**Không đưa vào log thông thường:** username/password, full Basic header, Bearer token, refresh token, session ID, raw cookie, secret key, OTP, authorization code, private certificate material, nguyên request body đăng nhập, raw JWT claims nhạy cảm. Khi cần điều tra theo account, dùng cơ chế tra cứu bảo vệ truy cập và retention riêng.

### 4.2. Điều gì nên log ở từng tầng?

| Tầng | Sự kiện có giá trị | Tránh |
| --- | --- | --- |
| Gateway | Request bị chặn bởi policy, TLS/mTLS peer được chấp nhận hay từ chối, rate limiting | Token/cookie hoặc request body có credential |
| Authentication | Thành công/thất bại theo reason code, provider hoặc mechanism đã chuẩn hóa | Password, bearer token, email hay full principal dump |
| Authorization | Quyết định deny, action/resource type, policy ID nội bộ phù hợp | Full object chứa dữ liệu nghiệp vụ |
| CSRF | Thiếu/không khớp token theo route/method đã chuẩn hóa | Token CSRF nguyên văn |
| Session/logout | Tạo/đóng session ở mức event và outcome; liên kết audit được phép | Session identifier thô trong application logs |
| Business service | Hành động bị từ chối ở cấp tenant/object, policy rule | Giá trị bí mật trong entity hoặc request JSON |
| Infrastructure | Certificate expiry, JWKS/IdP unavailability, exporter backlog | Private keys, client secrets, handshake raw payload |

Đảm bảo **không ghi trùng audit** chỉ vì một HTTP request có `REQUEST` và `ASYNC` servlet dispatch, hoặc vì cùng event được xử lý bởi nhiều listeners. Đếm “authentication attempts” không đồng nghĩa “unique users”: một client HTTP Basic có thể thực hiện authentication nhiều lần trên nhiều request.

### 4.3. Log level TRACE/DEBUG không phải chế độ quan sát production dài hạn

Trong môi trường local, có thể tạm bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

`TRACE` có thể tạo rất nhiều log từ filter chain. Không bật vô hạn trên production: tăng chi phí, giảm hiệu năng, có nguy cơ ghi dữ liệu có tính nhạy cảm tùy request/component/config. Nếu cần debug sự cố production, chọn phạm vi package, thời hạn, sampling và quyền truy cập log; sau đó tắt và xác nhận không còn thông tin nhạy cảm.

Cần phân biệt:
- **Framework debug logs** giúp hiểu filter chain;
- **Security audit events** cần format/schema ổn định và chính sách lưu trữ chặt;
- **Application access logs** ghi request/response ở tầng web server/gateway;
- **Metrics/traces** không được xem là bản sao tự động của mọi audit event.

## 5. Metrics: đo tỷ lệ và độ trễ mà không làm nổ cardinality

### 5.1. Các chỉ số nên theo dõi

| Nhóm | Metric mẫu | Tại sao quan trọng |
| --- | --- | --- |
| HTTP | Tổng request theo `uri template`, `method`, `status`, `outcome` | Thấy 401/403/5xx thay đổi |
| Authentication | `auth_attempts_total{outcome="success|failure"}` (tên ứng dụng tự đặt) | Nhận biết lỗi credential/rate thay đổi |
| Authorization | `authorization_denied_total{resource_type="..."}` (nếu có instrument chính xác) | Theo dõi access denial |
| IdP/JWKS | Latency, timeout, error count của outbound call | Phát hiện phụ thuộc hạ tầng lỗi |
| Token | Tỷ lệ invalid/expired token theo reason code cố định | Phát hiện lỗi cấu hình/token rotation |
| CSRF | Tỷ lệ CSRF denied theo route template/method | Phát hiện client integration sai hoặc tấn công |
| Filter chain | Latency/calls của các observation được version hỗ trợ | Tìm hot spots trong security filter pipeline |
| Infrastructure | Exporter failures, dropped spans/logs, registry cardinality | Biết observability pipeline có hoạt động |

**Chọn bộ nhãn ít giá trị khác nhau:** `method`, `status`, `outcome`, `provider` từ enum chuẩn hóa, `route` từ template. Không thêm `username`, `email`, `session_id`, `token`, `ip`, `trace_id` hoặc path chứa UUID làm metric tags.

Ví dụ cùng một metric với 5 tag, mỗi tag có số giá trị lần lượt 4 × 8 × 20 × 2 × 3 tạo ra tới **3.840 time series** trước cả chiều theo instance/region. Nếu thêm user ID hàng triệu giá trị, cardinality có thể bùng nổ. Trường định danh nên ở **log/trace có quyền truy cập bảo vệ**, không đưa vào metric label.

### 5.2. “401 tăng” không tự đồng nghĩa có tấn công

HTTP 401 có thể do token hết hạn, thiếu token, API client sai config hoặc brute force; 403 có thể do authorization deny, CSRF hoặc cross-tenant policy. Hãy kết hợp:

- baseline và rate theo thời gian;
- route template, mechanism, reason code;
- release/deployment change;
- log sự kiện ở mức aggregate;
- latency IdP và dependency;
- trace mẫu để phân tích đường xử lý khi cần.

Không phát cảnh báo trực tiếp dựa vào **một** 401 đơn lẻ. Alert nên dựa trên bất thường so với traffic, rate/tỷ lệ và mức ảnh hưởng.

### 5.3. Metric không phải toàn bộ audit

Metric thường giữ tổng số, histogram, percentile — không giữ mọi event. Tăng `authentication_failure_total` giúp cảnh báo, nhưng không cho biết đầy đủ ai, lúc nào, policy nào từ chối. Security audit có thể cần retention, tính toàn vẹn và quy trình truy xuất riêng, tuân thủ chính sách dữ liệu cá nhân.

## 6. Tracing: biết request chậm ở hop nào

Tracing thích hợp cho một request đi qua:

~~~text
ingress/gateway (server or proxy span)
    |
    +--> inventory-api HTTP server span
         |
         +--> Spring Security filter/observation (nếu version hỗ trợ)
         +--> controller / service observation (khi được instrument)
         +--> remote IdP introspection HTTP client span
         +--> database query span (nếu instrument)
         |
         +--> HTTP 200 / 401 / 403
~~~

Một **trace** chứa nhiều **spans**, span thường có trace ID/span ID, thời gian bắt đầu/kết thúc, tên operation và attributes/tags. Một trace giúp chỉ ra request mất 800ms ở introspection endpoint hay 5ms trong authorization decision.

### 6.1. Logging correlation và trace context

Khi Spring Boot 3.x được cấu hình Micrometer Tracing với bridge/exporter phù hợp, trace/span IDs có thể được đưa vào logging MDC theo cấu hình observability. Việc nhận trace context từ HTTP headers qua proxy phải theo **trusted proxy policy**; không chấp nhận vô điều kiện mọi trace header tự gửi để giả mạo liên kết với một request nhạy cảm.

Nếu không cài tracer, ứng dụng vẫn có thể xuất HTTP metrics; **không mặc định** có trace IDs trong logs chỉ vì đã có Actuator.

### 6.2. Sampling và audit completeness

Sampling 10% có nghĩa phần lớn HTTP traces không được thu; điều này phù hợp phân tích hiệu năng nhưng **không được dùng để khẳng định mọi authentication failures đã được ghi**. Những sự kiện bắt buộc audit cần một kênh log/event riêng có durability/retention phù hợp.

Nếu tăng trace sampling trong incident, cần cân bằng chi phí, dữ liệu nhạy cảm và giới hạn exporter. Không đặt thuộc tính `authorization` chứa token/PII lên span.

### 6.3. Async/thread context

Trong Servlet + Spring MVC `Callable`, Micrometer observation/tracing và `SecurityContext` có thể có **cơ chế context propagation khác nhau**. Với `@Async`, `CompletableFuture` hoặc executor tùy chỉnh, cần xác minh có propagator/TaskDecorator/ContextSnapshot hay không.

Không tự tin rằng `MDC.get("traceId")` trên thread A sẽ xuất hiện trên thread B. Đừng dùng `InheritableThreadLocal` như cách phổ quát cho thread pool. Một **trace bị đứt** không đồng nghĩa authentication thất bại; cần kiểm instrument và context propagation riêng.

## 7. Ví dụ hoàn chỉnh Java 17+: log event và metric xác thực

Mã sau là **project Spring Boot 3.3.5 tham chiếu** để học. Đây là một phiên bản cụ thể của nhánh Boot 3.x, **không tuyên bố là bản mới nhất**. Ví dụ dùng HTTP Basic trên endpoint GET, một user demo, Actuator và Prometheus registry. Mục tiêu chứng minh:
- Spring Security **thực sự xác thực** password;
- framework phát ra event xác thực qua `AuthenticationEventPublisher`;
- listener tạo **metric low-cardinality** và log sự kiện không chứa credential;
- HTTP metrics có thể được xem ở Actuator, tùy cấu hình/phiên bản;
- tests quan sát counter tăng sau Basic success/failure.

**Hạn chế quan trọng:** Không có code JWT/OIDC đầy đủ trong project này. Những filter metrics/traces **tự động** của Spring Security 6.x chỉ sử dụng nếu phiên bản đang chạy hỗ trợ và đã được cấu hình. Không coi ví dụ là mô hình audit hoàn chỉnh cho production.

### 7.1. Cấu trúc project

~~~text
security-observability-demo/
  pom.xml
  src/
    main/
      java/com/example/securityobs/
        SecurityObsApplication.java
        SecurityConfig.java
        SecurityEventMetrics.java
        DemoController.java
      resources/
        application.yml
    test/
      java/com/example/securityobs/
        SecurityEventMetricsTest.java
~~~

### 7.2. Maven dependencies

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-observability-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
    </plugins>
  </build>
</project>
~~~

**Kiểm tra cú pháp:** Phần `<build>` chỉ xuất hiện một lần trong `pom.xml`; thẻ `<plugins>` được đóng bằng `</plugins>` đúng chữ thường. Maven XML phân biệt chữ hoa/chữ thường. Luôn chạy `mvn validate` trước khi chạy test hoặc deploy.

### 7.3. Main application

**`src/main/java/com/example/securityobs/SecurityObsApplication.java`:**

~~~java
package com.example.securityobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityObsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityObsApplication.class, args);
    }
}
~~~

### 7.4. Security configuration

**`src/main/java/com/example/securityobs/SecurityConfig.java`:**

~~~java
package com.example.securityobs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        // Công bố success/failure events từ AuthenticationManager.
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/ping").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Không tắt CSRF trong ứng dụng chỉ có GET endpoints.
            .build();
    }
}
~~~

**Giải thích:**

- `InMemoryUserDetailsManager` chỉ để demo. Không sử dụng tài khoản hardcoded cho production.
- Authentication provider do Spring Security cấu hình gọi `AuthenticationEventPublisher` khi auth success/failure phù hợp. Event có thể được phát với mỗi Basic authentication attempt; **không** phải mỗi “phiên người dùng duy nhất”.
- Khi endpoint `GET /api/me` gửi Basic header sai, thường 401. Khi đúng, 200 và một success event.
- `SessionCreationPolicy.STATELESS` áp dụng cho Basic demo; tránh dựa vào session để xác thực request kế tiếp. Không xem stateless như lời chứng mọi client không gặp CSRF: browser có thể tự đính kèm Basic credential. Demo chỉ dùng GET, nên giữ CSRF mặc định.
- `/actuator/metrics` và `/actuator/prometheus` được bảo vệ bằng Basic trong demo vì `anyRequest().authenticated()`. Production phải hạn chế đường mạng/mTLS/monitoring identity và không để telemetry endpoints công khai qua Internet.
- `AbstractHttpConfigurer::disable` ở đây **chỉ tắt form login** để behavior API rõ ràng; **không** tắt CSRF, authentication hay authorization.

### 7.5. Đo authentication events với Micrometer Counter

**`src/main/java/com/example/securityobs/SecurityEventMetrics.java`:**

~~~java
package com.example.securityobs;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class SecurityEventMetrics {

    private static final Logger log =
        LoggerFactory.getLogger(SecurityEventMetrics.class);

    private final Counter success;
    private final Counter failure;

    public SecurityEventMetrics(MeterRegistry registry) {
        success = Counter.builder("app.security.authentication.attempts")
            .description("Authentication attempts recorded as success")
            .tag("outcome", "success")
            .register(registry);

        failure = Counter.builder("app.security.authentication.attempts")
            .description("Authentication attempts recorded as failure")
            .tag("outcome", "failure")
            .register(registry);
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        success.increment();

        // Không log username, password, token hay raw Authentication.
        log.info("security_event=authentication outcome=success");
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        failure.increment();

        // Reason được chuẩn hóa theo loại exception, không dump message.
        String reason = event.getException()
            .getClass().getSimpleName();

        log.warn(
            "security_event=authentication outcome=failure reason={}",
            reason);
    }
}
~~~

Đây là **một metric ứng dụng tự đặt**:
- tên `app.security.authentication.attempts`;
- tag `outcome` chỉ có hai giá trị `success`/`failure`;
- không có user ID/IP/trace ID để tránh high-cardinality;
- log sự kiện tối giản, không chứa thông tin credential.

Micrometer/Prometheus có thể **đổi định dạng tên metric** theo naming convention khi xuất. Không assert cố định “ở Prometheus chắc chắn tên có dấu chấm y hệt”. Hãy kiểm `/actuator/metrics` và `/actuator/prometheus` trong ứng dụng đang chạy.

**Sự kiện không bao phủ toàn bộ an ninh ứng dụng.** Authentication events không tự cho biết mọi authorization decision, mọi 401 do thiếu token, mọi CSRF rejection hoặc mọi JWT decoder validation error theo cùng cách. Nếu cần metric cho các loại đó, dùng **điểm instrument phù hợp** (Spring Security observations sẵn có theo version, event authorization, exception handler, gateway, application service). Đừng gắn filter “đếm deny” bằng cách chỉ dựa vào HTTP status rồi gọi nó là authentication failure.

### 7.6. API controller

**`src/main/java/com/example/securityobs/DemoController.java`:**

~~~java
package com.example.securityobs;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    public Map<String, String> currentUser(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

Trong production, không trả thêm field của `Authentication`/`UserDetails` hay raw principal để “tiện debug”; chúng có thể chứa password hash và attributes nhạy cảm.

### 7.7. Actuator và exporter (dev configuration)

**`src/main/resources/application.yml`:**

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1

logging:
  level:
    org.springframework.security: INFO
~~~

Cấu hình này **chỉ là ví dụ chạy local**. Trong production, Actuator endpoint exposure phải kết hợp authentication, network segmentation, monitoring service identity, TLS và role-based access. `health` có thể trả thông tin ở nhiều mức khác nhau; không bật `show-details=always` ra Internet.

`management.tracing.sampling.probability` sẽ có ý nghĩa khi đã cài **tracing implementation/bridge** phù hợp; một mình nó **không tạo tracer/export spans**. Đoạn `pom.xml` ở mục này chỉ cài Actuator + Prometheus metrics, chưa có bridge/exporter cho distributed tracing.

### 7.8. Chạy và kiểm chứng

Từ thư mục project:

~~~bash
mvn test
mvn spring-boot:run
~~~

Gửi một request public:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Một response body điển hình:

~~~json
{"status":"ok"}
~~~

Gửi Basic credential đúng:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Kỳ vọng HTTP 200, JSON user `alice`, một log event `outcome=success` và counter success tăng. Gửi credential sai:

~~~bash
curl -i -u alice:wrong-password http://localhost:8080/api/me
~~~

Kỳ vọng HTTP 401, một authentication failure event theo mapping exception của provider và counter failure tăng. Request Basic không gửi credential có thể nhận 401 nhưng **không nhất thiết** phát cùng loại authentication failure event vì không có attempt với username/password — đừng xem metric là phép đếm mọi status 401.

Xem actuator metrics đã được bảo vệ:

~~~bash
curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/metrics

curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/metrics/app.security.authentication.attempts

curl -i -u alice:demo-pass \
  http://localhost:8080/actuator/prometheus
~~~

Thông tin xuất hiện phụ thuộc dependency, registry, security chain và request đã thực sự tạo meter. Nếu metric chưa tồn tại, xác minh event listener được gọi và correct meter naming thay vì tự cho là Micrometer lỗi.

Các URL HTTP/Basic chỉ dùng trên localhost để học; **credential thật phải qua HTTPS và không đưa vào shell history hoặc pipeline log**.

## 8. Kiểm thử event metric mà không dùng user giả để lách xác thực

**`src/test/java/com/example/securityobs/SecurityEventMetricsTest.java`:**

~~~java
package com.example.securityobs;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityEventMetricsTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void successfulBasicIncreasesSuccessCounter() throws Exception {
        double before = count("success");

        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        assertTrue(count("success") > before);
    }

    @Test
    void badBasicPasswordIncreasesFailureCounter() throws Exception {
        double before = count("failure");

        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "bad-password")))
            .andExpect(status().isUnauthorized());

        assertTrue(count("failure") > before);
    }

    @Test
    void anonymousPublicRequestIsNotBasicLogin() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    private double count(String outcome) {
        Counter counter = registry
            .find("app.security.authentication.attempts")
            .tag("outcome", outcome)
            .counter();
        return counter == null ? 0.0 : counter.count();
    }
}
~~~

Điểm đáng chú ý:

1. `httpBasic("alice","demo-pass")` thực sự gửi **Authorization header** cho filter xác thực; `@WithMockUser` thường **không** đi qua password provider theo cách này.
2. Test đọc count **trước và sau** request, tránh giả định registry bắt đầu bằng 0 (các tests/context có thể đã tạo events).
3. Vì dùng listener đồng bộ thông thường, metric có thể tăng trước khi MockMvc hoàn tất. Nếu project cấu hình event processing bất đồng bộ, cần đồng bộ test hoặc dùng kiểm tra eventual consistency có thời hạn.
4. Không dùng số “mỗi request chắc chắn có đúng 1 event” như một bất biến mọi version, vì caching, filter chain và provider behavior có thể khác; mục tiêu của test là xác nhận có event mong đợi.
5. Không assert một specific Prometheus text line khi naming convention/exporter version chưa được cố định; kiểm registry trước, kiểm exporter format trong integration test riêng.

Đây là test trong ứng dụng Spring Boot, không phải chương trình standalone `javac`. Vì Maven build phụ thuộc môi trường và repository, bài không giả lập stdout của `mvn test`. Kỳ vọng là test pass khi project đúng cấu hình.

### Nếu test metric thất bại

- Kiểm bean `AuthenticationEventPublisher` có được `ProviderManager` sử dụng hay không.
- Kiểm event type `AuthenticationSuccessEvent`/`AbstractAuthenticationFailureEvent` tương ứng provider.
- Kiểm event listener `@Component` nằm trong vùng component scan.
- Kiểm HTTP Basic request có được chain xử lý và user đã thực sự authenticated không.
- Kiểm test context có cùng `MeterRegistry` và cùng application context.
- Kiểm service có custom authentication manager/provider bỏ qua event publisher hay không.
- Kiểm failure type có được mapping sang event trong `DefaultAuthenticationEventPublisher` hay cần cấu hình bổ sung.

## 9. Bật tracing khi dependencies và collector hỗ trợ

Để xuất distributed traces trong Spring Boot 3.x, thông thường cần thêm **Micrometer Tracing bridge** (ví dụ OpenTelemetry bridge) và exporter/transport tương ứng. Thêm các dependency sau vào `<dependencies>` của Maven project **chỉ khi tổ hợp version đang chạy hỗ trợ**:

~~~xml
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
  <groupId>io.opentelemetry</groupId>
  <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Đây là đoạn bổ sung, không phải một `pom.xml` độc lập. Các properties exporter/collector, OTLP protocol/endpoint, authentication và TLS phải khớp **phiên bản Boot**. Không khẳng định chỉ thêm hai dependency sẽ tự gửi trace thành công đến một backend bất kỳ: cần collector reachable, exporter config, sampling và smoke test.

Một cấu hình minh họa kiểu Boot 3.x có thể dùng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Địa chỉ collector trên là **ví dụ chỉ chạy local**; không gửi traces mang dữ liệu nghiệp vụ qua HTTP công khai ở production. Dùng transport được bảo vệ, auth/TLS và data-retention theo policy. Kiểm `management.otlp.tracing.endpoint` và đường OTLP HTTP trên chính bản Spring Boot đang sử dụng; các phiên bản hoặc exporter khác có thể yêu cầu cấu hình khác.

### Quy trình smoke-test tracing

1. Xác nhận tracer/bridge beans được tạo (không chỉ có Actuator).
2. Xác nhận collector có lắng nghe endpoint/protocol đã cấu hình.
3. Gửi request tới `/api/me` với credential demo.
4. Xem trace trong backend, kiểm HTTP server span và trace ID.
5. Kiểm log correlation trong application logs nếu MDC được cấu hình.
6. Gửi một request sai password và kiểm trace/status tương ứng, nhưng **không có Basic credential/token trong span attributes**.
7. Gửi request qua gateway/downstream để kiểm context propagation; kiểm các hop có nằm trong cùng trace hay không.
8. Kiểm sampling: nếu chỉ lấy 10%, một lần gọi không xuất trace **không đủ** để kết luận exporter hỏng; trong test môi trường cách ly có thể tạm tăng sampling.

**Đừng dùng tracing làm audit log:** khi sampling và exporter queue bỏ spans, trace có thể thiếu dù xác thực đã diễn ra. Những event pháp lý/tuân thủ cần kênh audit riêng, tách quyền truy cập và retention.

## 10. Quan sát authorization mà không “đếm 403 = thiếu quyền”

Một request 403 có thể đến từ:
- `AuthorizationFilter` chặn do thiếu authority;
- `CsrfFilter` từ chối POST thiếu/sai CSRF;
- business service từ chối quyền trên resource/tenant;
- proxy/WAF trả 403 **trước khi** request đến Spring Boot;
- custom filter hoặc API gateway đưa ra policy deny.

Vì vậy metric theo **HTTP status** là dấu hiệu tổng quan, không phải nguyên nhân. Nếu cần authorization security event, xác định điểm phát quyết định ở đúng module và version: Spring Security authorization event publishing, method security events hoặc application-level audit. **Không tự cho rằng mọi authorization denial đều phát cùng loại ApplicationEvent mặc định**.

Một ví dụ kiến trúc policy cụ thể:

~~~text
GET /api/orders/{id}
    |
    +--> HTTP authentication
    |
    +--> URL authorization
    |      -> đã authenticated?
    |
    +--> service-level ownership/tenant check
           -> allowed hoặc denied
           -> application audit event reason=object_permission_denied
    |
    +--> response 200 hoặc 403/404 theo API contract
~~~

Trong application service, nơi có đủ context để kiểm ownership, bạn có thể phát **custom audit event** với action và resource type đã chuẩn hóa. Không đưa raw `orderId`, toàn object, bearer token hoặc user ID vào metric tags. Nếu cần điều tra chi tiết, lưu audit event trong kho có ACL riêng.

### Authorization metrics theo version

Nếu bản Spring Security đang dùng cung cấp Micrometer observation cho authorization manager, dùng tích hợp được công bố và kiểm tag set thực. Nếu chưa hỗ trợ, đo custom counter theo:
- `decision=allow|deny`;
- `resource_type=order|invoice|...`, là enum hữu hạn;
- `policy_id` chỉ khi là danh sách chính sách hữu hạn.

**Không đo toàn bộ data path bằng `request.getRequestURI()`**: ví dụ `/api/orders/1234` và `/api/orders/5678` sẽ tạo cardinality vô hạn theo ID.

## 11. Session, logout, CSRF, JWT và sự kiện đặc thù

### 11.1. Session/logout

Trong ứng dụng có form login/session cookie, nên quan sát:
- tỷ lệ login success/failure;
- session lifecycle, timeout, concurrent session limit violations nếu có;
- logout intent và logout completion (nếu cần audit);
- session fixation protection hoạt động theo policy;
- cookie/configuration errors.

Không log `JSESSIONID` hoặc session identifier. Một user bị logout nhưng sau đó request được authenticated lại có thể do **SSO session** hoặc Basic credentials vẫn được client gửi; phải nhìn rõ authentication mechanism thay vì coi logout không hoạt động.

### 11.2. CSRF

Một 403 do CSRF có thể là tích hợp front-end gửi token sai, hết session hoặc cross-site request. Chỉ từ HTTP 403 không biết nguyên nhân. Dùng logger/event/exception handling phù hợp để phân biệt `MissingCsrfTokenException`, `InvalidCsrfTokenException` ở những nơi được hỗ trợ; đừng đưa raw token vào log. Kiểm chính sách CSRF trên cả chain và proxy.

### 11.3. JWT Resource Server

Các thất bại token có thể gồm:
- signature không hợp lệ;
- `issuer` không đúng;
- `audience` không cho backend hiện tại;
- `exp` hết hạn, `nbf` chưa hợp lệ;
- JWKS endpoint lỗi mạng hoặc key rotation chưa đồng bộ.

Security event lý tưởng dùng reason codes cố định như `invalid_signature`, `wrong_issuer`, `expired`, `wrong_audience`, `jwks_unavailable`. Tuy nhiên framework đôi khi gom lỗi dưới `InvalidBearerTokenException` hoặc exception khác; **không thể cam kết có sẵn từng reason code** từ đúng filter trên mọi version. Nơi instrument phải được chứng minh qua test, đồng thời tránh đưa token/claims nhạy cảm vào event.

### 11.4. Authentication federation/OIDC

Nếu proxy/IdP bên ngoài thực hiện đăng nhập, backend có thể chỉ thấy token/header/claims do proxy truyền. Một log “auth success” ở backend có thể có ý nghĩa “assertion được chấp nhận”, **không phải người dùng vừa hoàn thành MFA**. Cần phân biệt:
- login tại IdP;
- session validation tại proxy;
- token validation tại resource server;
- application authorization.

Khi correlate logs giữa các hop, dùng trusted request/trace IDs và audit fields đã normalize; không tin raw identity header do client tự gửi.

## 12. Bảo mật cho chính observability pipeline

Một hệ quan sát bảo mật có thể trở thành nguồn rò dữ liệu lớn nếu:
- log toàn bộ HTTP headers/cookies;
- xuất metric có user ID/IP/token trong tags;
- trace chứa raw JWT, password hoặc PII;
- exporter endpoint dùng HTTP không được bảo vệ;
- Prometheus/Actuator dashboards công khai ra Internet;
- nhiều kỹ sư có quyền đọc audit records nhạy cảm mà không cần thiết;
- retention vô hạn hoặc backup không có chính sách xóa;
- hệ thống logging mất dữ liệu nhưng alert vẫn báo “không có vụ việc”.

### 12.1. Checklist dữ liệu

| Đối tượng | Metric labels? | Log/trace? | Gợi ý |
| --- | --- | --- | --- |
| `outcome`, `method`, `status` | Có | Có | Danh sách nhỏ, ổn định |
| Route template `/api/orders/{id}` | Có, khi template được normalize | Có | Không dùng raw URI chứa ID |
| Username/email | Không | Chỉ trong audit store bảo vệ khi có căn cứ | Cần privacy/retention |
| Client IP | Không hoặc đã bucket hóa nếu thật sự cần | Hạn chế, tuân thủ chính sách | Tránh high cardinality và dữ liệu cá nhân |
| Trace ID | Không | Có thể log dưới correlation ID | Không phải bí mật mặc định nhưng phải tránh spoofing |
| Session ID/cookie | Không | Không | Không được log nguyên văn |
| Bearer/refresh token | Không | Không | Token là credential |
| JWT claims | Không | Chỉ field cho phép và có kiểm soát | Không dump full token |
| Exception class/reason code | Chỉ danh mục hữu hạn | Có | Không log raw message nếu chứa credential |
| Tenant ID | Thường không | Có thể lưu audit store bảo vệ | Tránh đo từng tenant thành metrics nếu nhiều tenant |

### 12.2. Retention và truy cập

- Phân tách **application operational logs** và **security audit store** theo độ nhạy/retention.
- Quy định ai được xem, tìm kiếm và xuất dữ liệu; log các hành động truy cập audit.
- Cấu hình redaction ở nhiều lớp: application, collector, pipeline, storage.
- Định kỳ chạy test “không chứa Authorization/Cookie/secret” bằng dữ liệu thử nghiệm an toàn.
- Có cảnh báo exporter queue đầy, ingestion errors và dropped data; **mất tín hiệu** cũng là sự cố vận hành.
- Không dùng log injection từ header client: sanitize ký tự xuống dòng, độ dài và định dạng correlation fields.

### 12.3. Chi phí và độ bền

Metric counter thường chi phí thấp nhưng phải giới hạn series. Trace chịu ảnh hưởng sampling/exporter; log audit cần kiểm chứng khả năng nhận và lưu sự kiện. Không đặt thao tác sync network đến log server **trong authentication filter** nếu nó có thể làm chậm hoặc cản trở login. Với event audit bắt buộc, thiết kế queue/outbox/transaction và fail-safe semantics theo yêu cầu tuân thủ.

## 13. Dashboard, SLI và cảnh báo

Một dashboard hữu ích không phải càng nhiều biểu đồ càng tốt. Nó nên trả lời nhanh:

1. **Tình trạng authentication:** attempts, success/failure ratio, theo mechanism/service/route tổng hợp.
2. **Tình trạng authorization:** tổng deny và tần suất 403 (phân biệt CSRF vs permission theo log/event).
3. **Độ trễ:** p50/p95/p99 của HTTP server requests theo route template, IdP/JWKS dependency latency.
4. **Chất lượng telemetry:** exporter errors, dropped spans/logs, scrape failures, sampling config.
5. **Triển khai:** dashboard annotate release/version, filter chain config changes và key rotation events.

Ví dụ truy vấn PromQL minh họa (tên metric sau khi Prometheus normalize phải kiểm tại runtime):

~~~promql
sum(rate(app_security_authentication_attempts_total{outcome="failure"}[5m]))
/
clamp_min(
  sum(rate(app_security_authentication_attempts_total[5m])),
  1
)
~~~

**Lưu ý đơn vị:** `rate()` là số attempts/giây; chia tỷ lệ failure / total. `clamp_min(...,1)` trong ví dụ có thể làm sai tỷ lệ khi traffic tổng thấp hơn 1 attempt/giây. Trong dashboard production, thường nên dùng denominator guard thích hợp với đơn vị và threshold; không coi công thức minh họa này là alert hoàn chỉnh.

Một lựa chọn dễ hiểu hơn cho tỷ lệ trên rolling window là dùng `increase(…[10m])` trên cả tử/mẫu; sau đó xử lý không có traffic. Cần xem implementation của exporter về meter names. **Không tạo cảnh báo khi denominator=0** rồi tự kết luận lỗi tấn công.

### 13.1. Cảnh báo nên có ngữ cảnh

- **Auth failure tăng:** so với baseline có traffic; phân tích type và release, không gắn nhãn “brute force” chỉ vì 401 tăng.
- **403 tăng sau deploy:** so route/endpoint đã thay policy, CSRF, gateway.
- **JWKS/IdP latency tăng:** so dependency status và token invalid rate.
- **Tỷ lệ 200 bất thường trên endpoint nhạy cảm:** có thể là authorization regression, nhưng phải kết hợp synthetic tests/audit.
- **Không còn log/metric/trace:** có thể telemetry pipeline lỗi, không được hiểu là “không có sự cố”.

Khi xây SLO, định nghĩa rõ **mẫu số**, user journey, expected 401/403, hệ thống test traffic và yêu cầu bảo mật để không đánh đồng mọi từ chối hợp lệ là lỗi dịch vụ.

### 13.2. Dashboard phải “đúng phiên bản”

Khi nâng cấp Spring Security/Micrometer, tạo checklist regression:
- metric names/tags còn tồn tại không;
- status/route tag semantics có thay đổi không;
- default instrumentation có được bật/tắt không;
- endpoint/security policy của Actuator còn đúng không;
- trace IDs/log patterns có thay đổi không;
- tests với user demo có tạo event và counter không;
- sampling/exporter/collector có còn tương thích không.

Một dashboard không có data sau deploy chưa chắc traffic bằng 0; có thể do rename metric hoặc mất export.

## 14. Quy trình điều tra sự cố 401/403 và độ trễ xác thực

Giả sử sau deploy tỷ lệ 403 tăng:

1. **Xác định thời điểm và phạm vi:** deployment version, service, route template, method và traffic.
2. **Phân biệt tầng trả status:** gateway/WAF, Spring Security filter, controller hoặc business service.
3. **Kiểm logic CSRF:** POST thiếu token có thể trả 403 trước authorization; không suy mọi 403 là role thiếu.
4. **Kiểm Authentication:** principal thực tế, token type, issuer/audience/time nếu JWT, session/Basic nếu username/password.
5. **Kiểm authorization policy:** URL matcher, method security, tenant/object permission và policy version.
6. **Tra log audit có cấu trúc:** request ID, reason code, timestamp; tránh dump credential.
7. **Dùng trace khi có:** inspect ingress, filters/IdP outbound, business spans và latency; nhớ sampling.
8. **So với deployment trước:** filter chain order, new `SecurityFilterChain`, property mappings và dependency upgrades.
9. **Kiểm telemetry pipeline:** exporter delays/drop, scrape access, clock skew và retention.
10. **Khôi phục an toàn:** rollback hoặc sửa policy có kiểm thử; không mở `permitAll` cho endpoint nhạy cảm chỉ vì dashboard cần xanh.

Nếu 401 tăng nhưng không thấy authentication failure events, có thể request không mang credential hoặc bị entry point từ chối **trước khi provider được gọi**. Đây không phải bằng chứng listener hỏng. Tách logic: **HTTP denied outcome** và **authentication attempt failure** là hai loại metric khác nhau.

Nếu latency tăng ở JWT auth:
- kiểm JWKS network/caching/rotation và key ID mismatch;
- kiểm parser/validation overhead, allowed algorithms;
- kiểm thread pool, upstream timeout;
- kiểm trace sampling/collector;
- không bật log raw JWT hoặc bỏ issuer/audience validation để giảm latency.

## 15. Quan sát mà không làm thay đổi quyết định bảo mật

Instrumentation có thể gây lỗi nếu:
- listener ném exception và làm request thất bại;
- exporter synchronous chậm ở authentication hot path;
- log formatting serializes nguyên principal và kéo theo dữ liệu nhạy cảm;
- metrics gắn tag theo user khiến memory tăng dần;
- custom filter đo duration nhưng quên `filterChain.doFilter` hoặc tự xử lý response;
- trace context propagation làm lẫn danh tính giữa thread pool tasks;
- security endpoint exposure rộng hơn dự kiến.

**Nguyên tắc:** telemetry không được tự cấp quyền, làm yếu xác thực hay thay đổi response bảo mật. Trong listener có thể bảo đảm thao tác ghi metric/log đơn giản và không gọi IO chậm. Với audit có yêu cầu bắt buộc, thiết kế reliability theo tiêu chuẩn riêng, không chỉ “catch exception rồi bỏ qua” mọi event.

Một custom filter timing nếu thật sự cần phải:
- đặt ở vị trí được chứng minh trên chain;
- sử dụng clock/observation thích hợp và `finally` để đóng scope;
- phân biệt `REQUEST`, `ASYNC`, `ERROR` để tránh đếm sai;
- tránh double registration Spring bean filter và `addFilterBefore`;
- không log raw headers/body.

**Ưu tiên built-in instrumentation được phiên bản hỗ trợ** thay vì viết filter thủ công cho mọi đoạn.

## 16. Kiểm thử tương thích và chất lượng telemetry

### 16.1. Unit/integration tests

| Test | Mục đích | Kỳ vọng |
| --- | --- | --- |
| Basic đúng | Authentication success event/counter | Counter success tăng, 200 đúng user |
| Basic sai | Authentication failure event/counter | Counter failure tăng, 401 |
| Không gửi credential | Entry point behavior | 401 theo demo, không bắt buộc tạo failure event |
| Authorization deny | AccessDeniedHandler/policy event | 403 không bị nhầm là bad password |
| CSRF invalid (ứng dụng có POST) | Phân loại CSRF | CSRF reason, không dump token |
| HTTP server metric | Actuator/registry | Meter được tạo sau request theo đúng Boot version |
| Trace smoke test | Tracer/collector | Span xuất đúng backend khi sampling phù hợp |
| Redaction | Không rò thông tin | Log/spans/metrics không chứa demo password/token |
| Version upgrade | Tên metric/tag/trace | Regression test theo manifest version đã khóa |
| Telemetry outage | Không làm mất authentication availability ngoài policy | Exporter lỗi được báo, service xử lý phù hợp |

### 16.2. Test không rò credential

Dùng **credential demo có dấu nhận dạng** trong test environment rồi kiểm capture logs/trace sample **không chứa** chuỗi đó. Không kiểm bằng credential production. Nếu triển khai Logback TestAppender hoặc in-memory logger, luôn reset giữa tests. Kiểm cả messages và structured arguments. Test Prometheus exposition không có user-specific label values.

### 16.3. Test sampling và propagation

Trong môi trường test cách ly, tạm chọn sampling phù hợp để kiểm chain trace; test chuẩn phải giữ sampling configuration production theo policy. Với asynchronous code, kiểm trace continuity và cleanup context giữa hai request user khác nhau để tránh lẫn ID/context.

### 16.4. Đừng nhầm instrumentation test với authentication test

Một test `@WithMockUser` có thể đi qua controller và tạo HTTP metric, nhưng **không tạo password authentication attempt thật**. Muốn kiểm event do provider, gửi `httpBasic()` hoặc `formLogin()` qua FilterChainProxy. Muốn kiểm JWT signature/token claims, dùng Resource Server decoder thật hoặc test configuration đúng, không dùng mock Jwt rồi khẳng định production signature validation hoạt động.

## 17. Bài tập thực hành

**Bài 1 — Xây dashboard xác thực.** Chạy demo, gửi nhiều lần Basic đúng và sai. Dùng `/actuator/metrics/app.security.authentication.attempts` xem tags/measurements. Giải thích vì sao số lần auth events khác số user duy nhất.

**Bài 2 — Xác định 401 không qua provider.** Gửi một GET protected **không Authorization header**. So status và authentication failure counter. Giải thích lý do có thể 401 nhưng không có failure event.

**Bài 3 — So sánh 401 và 403.** Thêm endpoint yêu cầu ROLE_ADMIN, trong khi demo user chỉ ROLE_USER. Gửi Basic đúng. Xác minh authenticated nhưng status 403; không tự tăng metric “bad password”.

**Bài 4 — Metric cardinality.** Thử đề xuất tag `username` rồi tính số series khi có một triệu users. Chỉnh thiết kế chỉ còn `outcome` và route template.

**Bài 5 — Trace propagation.** Trong môi trường có OTLP collector, thêm một outbound HTTP call qua client được instrument. Kiểm chung trace ID trong gateway/backend/outbound spans khi version và propagation được cấu hình đúng. Ghi rõ sampling và bảo vệ headers.

**Bài 6 — Redaction.** Dùng credential demo khác biệt, kiểm logs, Prometheus metrics và trace exporter không chứa password/Authorization header/session cookie. Nếu có, sửa redaction ở đúng tầng.

**Bài 7 — Nâng version.** Cố định Boot/Security versions trong build; ghi lại metric names/tags hiện có. Nâng một bản minor theo hướng dẫn chính thức, chạy lại smoke tests và kiểm dashboard có cần migration không.

**Bài 8 — Alert có denominator.** Viết công thức tỷ lệ thất bại trên cửa sổ 10 phút, chỉ tính khi đủ traffic; giải thích vì sao 100% failure của một request duy nhất không nhất thiết là incident.

**Bài 9 — Mất exporter.** Trong môi trường cách ly, tắt collector/Prometheus scrape. Quan sát app availability, exporter failures/drop metrics, không biến log/trace outage thành lý do disable authentication.

**Bài 10 — Không log trùng trong async.** Với endpoint Spring MVC `Callable`, phân biệt request-start event, async dispatch completion và một business operation. Viết test kiểm audit không phát hai lần chỉ vì Servlet `ASYNC` dispatch.

## 18. Checklist triển khai theo từng phiên bản

- [ ] Ghi rõ Spring Boot, Spring Security, Micrometer, registry và tracing bridge versions.
- [ ] Dùng dependencies/versions theo BOM tương thích, test sau override/upgrade.
- [ ] Kiểm Actuator endpoint exposure và authentication/network restrictions.
- [ ] Xác nhận Spring Security built-in observations **thực sự tồn tại** trên runtime, không đoán metric names.
- [ ] Gắn HTTP metrics vào route template, method/status/outcome hữu hạn.
- [ ] Có authentication success/failure event metrics từ nguồn đáng tin; phân biệt với all-401/all-403.
- [ ] Có audit logs đủ dữ liệu điều tra, không lộ credential/PII trái chính sách.
- [ ] Không dùng username/IP/token/session/trace ID làm high-cardinality metric tags.
- [ ] Có trace sampling/exporter phù hợp; không coi tracing là audit toàn vẹn.
- [ ] Có test correlation ID/trace propagation qua gateway và async paths nếu cần.
- [ ] Có alert cho telemetry pipeline failures/dropped data.
- [ ] Có synthetic test cho auth success/failure, authorization deny và CSRF.
- [ ] Có dashboard regression test khi nâng minor/major version.
- [ ] Không để debug TRACE lâu dài trên production.
- [ ] Security monitoring endpoints chỉ cho các identity/network được phép.
- [ ] Retention, redaction, audit access và incident playbook được phê duyệt.

**Kết luận:** Quan sát bảo mật trong Spring Security Servlet hiệu quả khi **log trả lời sự kiện và lý do**, **metric trả lời tần suất/tỷ lệ/độ trễ**, và **trace trả lời quan hệ nhân quả giữa các hop**. Tín hiệu không có giá trị nếu hệ thống tự lộ token/password, làm nổ cardinality hoặc bị mất khi exporter lỗi. Vì tích hợp observability thay đổi theo **Spring Boot/Spring Security/Micrometer version**, hãy bắt đầu từ dependency/runtime thật, dùng built-in instrumentation có hỗ trợ, bổ sung custom low-cardinality security events khi cần, rồi xác minh bằng integration tests và dashboard qua mỗi lần nâng cấp.