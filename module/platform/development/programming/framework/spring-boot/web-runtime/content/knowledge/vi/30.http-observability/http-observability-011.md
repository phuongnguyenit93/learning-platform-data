# Giới hạn log chẩn đoán chi tiết trong môi trường production

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Quan sát HTTP

## 1. Bối cảnh: chẩn đoán HTTP mà không làm hệ thống tệ hơn

Một Spring Boot API phục vụ 1.000 requests/giây. Khi một số requests trả **401**, **403**, **500** hoặc có p99 latency tăng, nhóm vận hành thử chuyển **logging.level.root=TRACE** để xem chuyện gì đang xảy ra. Kết quả có thể trái kỳ vọng: log bị tràn, collector nghẽn, CPU và I/O tăng, các lỗi thật bị chìm giữa hàng nghìn dòng. Nghiêm trọng hơn, HTTP headers, Cookie, JWT, raw query string, JSON body hoặc SQL bind parameters có thể xuất hiện ở hệ thống logging vốn có retention và quyền truy cập khác database.

**Quy tắc:** production cần *quan sát liên tục*, nhưng không cần *ghi toàn bộ nội dung HTTP*. Hãy ghi **tín hiệu tối thiểu, có cấu trúc, có correlation**, đặt **privacy/security boundary**, dùng metrics/traces cho thống kê và chỉ tăng DEBUG một cách hẹp, có phê duyệt và thời hạn.

Bài này dành cho **Spring Boot 3.x Servlet Spring MVC**, thuộc nhóm **Quan sát HTTP**. Nó bao gồm:

1. Sự khác biệt giữa **application logs**, **access logs**, **Spring MVC/Security diagnostics**, **audit logs**, **metrics**, **tracing** và Actuator.
2. Cấu hình log levels đúng với **logging.level.\***, profiles và **spring.mvc.log-request-details=false**.
3. Vì sao không ghi Authorization, Cookie, query, payload hoặc raw exceptions, kể cả khi DEBUG.
4. Pattern Tomcat access log, vấn đề path variables và timestamp units.
5. Tác động và bảo vệ **/actuator/loggers** và **/actuator/httpexchanges**.
6. Một ví dụ **Java 17+ chạy được**: request ID, MDC, HTTP summary không log secrets.
7. JUnit test với **OutputCaptureExtension** và secret canary.
8. Sampling, log volume, performance, OpenTelemetry/Micrometer, proxy, Kubernetes và multi-replica.
9. Runbook production bật DEBUG trong cửa sổ ngắn và rollback.

## 2. Logs, metrics, traces và audit có vai trò khác nhau

| Tín hiệu | Mục đích | Ví dụ cần giữ | Nguy cơ khi quá chi tiết |
| --- | --- | --- | --- |
| **Application log** | Diễn giải event và lỗi ứng dụng | errorCode, operation, duration, correlation ID | Dump DTO/password/body, repeated stack traces. |
| **HTTP access log** | Biết method/route/status/time của request | GET /api/items/{id} 200 16ms | Raw path, query string và IP có PII. |
| **Spring MVC DEBUG/TRACE** | Handler mapping và framework behavior | Mapping/exception handling | Headers, parameters, form data nếu logging details được bật. |
| **Spring Security DEBUG/TRACE** | Auth, authorization, CSRF, filter chain | Security decision, status 401/403 | Volume lớn, có thể ghi context nhạy cảm. |
| **Audit** | Giao dịch bảo mật/nghiệp vụ bắt buộc lưu | Authenticated subject ID, action, outcome | Không được phụ thuộc vào sampled DEBUG logs. |
| **Metrics** | Request rate, error rate, p95/p99 | http.server.requests, status, templated route | Raw URL/userId trong tags gây high cardinality. |
| **Distributed tracing** | Tìm chặng chậm khi gọi nhiều services | traceId/spanId, dependency operation, timing | Span attributes chứa token/PII. |
| **Actuator httpexchanges** | Xem vài trao đổi gần đây khi bật | Method, status, timing | Expose request history và metadata nhạy cảm. |
| **Proxy/CDN logs** | Định tuyến/edge/WAF/tls problems | Routing outcome, status, edge latency | Bản sao token/query ngay trước Spring. |

**Tín hiệu thường trực** nên rẻ và an toàn. Metrics với low-cardinality labels cho thấy trends; tracing được sampling hợp lý cho thấy các chặng; log structured event giải thích lỗi; audit pipeline bảo đảm theo yêu cầu tuân thủ. Không nhồi cả bốn nhu cầu vào một logger DEBUG.

**Log volume là một resource budget**, không phải tài nguyên miễn phí. Có thể tăng request latency, bão hòa stdout/file disk, collector, network egress và indexing costs. Cần quản trị log bytes/s và retention như một SLO hỗ trợ.

## 3. Phân loại dữ liệu nào được ghi

Quy tắc mạnh nhất là **allowlist fields**, không phải dump mọi thứ rồi hy vọng regex redaction xóa đủ.

| Trường | Khuyến nghị | Lý do |
| --- | --- | --- |
| Method, HTTP status, sanitized errorCode | Ghi khi cần | Hữu ích để phân nhóm lỗi. |
| Route template, operation ID | Ưu tiên | Ví dụ **/api/users/{id}**, không raw user ID. |
| Duration, service, instance | Ghi có kiểm soát | Đo performance và khoanh vùng pod. |
| Request ID/traceId/spanId | Có thể ghi | Dùng correlation, không thay auth. |
| Authorization, Proxy-Authorization | **Không ghi giá trị** | Token, API key, Basic credentials. |
| Cookie, Set-Cookie | **Không ghi giá trị** | Session/refresh/CSRF cookies. |
| Request/response body | **Không ghi mặc định** | Password, OTP, PII, financial data, binary. |
| Raw query string | **Không ghi** | Email, token, free-text searches. |
| Raw URI path | Hạn chế | Có thể chứa token, email, order/customer ID. |
| Headers đầy đủ | Không dump | User-Agent/Referer có PII; custom headers có secrets. |
| SQL bind parameter values | Không ghi production | Lộ dữ liệu trực tiếp từ database. |
| Uploaded file name/content | Không ghi raw | Filename có PII hoặc ký tự điều khiển. |
| Exception message/stack trace | Có điều kiện | Thông báo có thể echo URL/query/SQL/PII. |
| Remote IP / Geo / User-Agent | Chỉ nếu có mục đích rõ | Có thể là thông tin riêng tư. |

Một đoạn code không an toàn:

~~~java
// Minh hoa ANTI-PATTERN trong mot component co Logger log.
log.debug("request headers={} body={}", requestHeaders, body);
log.error("remote call failed: {}", remoteResponseBody);
~~~

Đoạn code an toàn hơn:

~~~java
// Minh hoa event co field da duoc kiem soat.
log.info("http.request route={} method={} status={} elapsedMs={}",
        "/api/orders/{id}", "GET", 200, 18);
log.warn("upstream.timeout dependency={} reasonCode={}",
        "inventory", "CONNECT_TIMEOUT");
~~~

Đây là hai snippets minh họa, không phải một Java program độc lập. Hệ thống thật phải lấy method/status/duration từ HTTP lifecycle. Nếu dùng một mã định danh user để audit, hãy xác minh identity và tuân thủ schema/access/retention của **audit log** riêng.

### Vì sao redact sau khi ghi chưa đủ?

Giả sử server log body rồi collector mới dùng regex che **password**. Raw body có thể đã nằm ở:

- stdout/stderr container;
- file của JVM/appender;
- sidecar agent buffer;
- staging log shipping queue;
- backup/snapshot;
- crash report hoặc support ticket.

Regex còn có thể bỏ sót tên field mới, nested JSON, URL-encoded values, exception messages hoặc token không có key chuẩn. Giải pháp là **không tạo log event chứa secret ngay từ đầu**; sanitizer ở collector chỉ là lớp bảo vệ thêm.

### Log injection/forging

Một client có thể cố gửi CR/LF và các ký tự điều khiển trong path/header. Nếu ứng dụng ghép raw input vào text log, một request có thể trông như nhiều dòng log giả. Dùng **structured encoder với escaping**, length limits và allowlist values thay vì tin mọi Origin, User-Agent, X-Request-Id hoặc query do client gửi.

**JSON log không đồng nghĩa an toàn**: encoder có thể escape control chars nhưng vẫn lưu nguyên Bearer token nếu lập trình viên đưa nó vào một field.

## 4. Spring Boot 3.3: log levels và những property quan trọng

Spring Boot dùng Logback theo mặc định khi có starters phù hợp. Những level thường gặp:

| Level | Mục tiêu | Khuyến nghị |
| --- | --- | --- |
| **ERROR** | Lỗi bất thường của server | Ghi code/correlation, hạn chế stacktrace lặp. |
| **WARN** | Degraded state, condition cần chú ý | Thêm counter/rate limiting. |
| **INFO** | Lifecycle và event vận hành quan trọng | Baseline production. |
| **DEBUG** | Thêm chi tiết code path | Chỉ bật class/package hẹp trong thời gian ngắn. |
| **TRACE** | Chi tiết sâu, nhiều events | Tránh bật rộng trên traffic production. |
| **OFF** | Tắt logger | Không tắt audit bắt buộc. |

Cấu hình:

~~~properties
spring.application.name=http-logging-demo
logging.level.root=INFO
logging.level.com.example.httplog=INFO
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Khong cho MVC log headers/parameters day du o DEBUG/TRACE
spring.mvc.log-request-details=false

# Pham vi reactive HTTP codecs, khi co WebClient/WebFlux
spring.codec.log-request-details=false

# Tranh dua exception/stacktrace vao default HTTP error response
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

**spring.mvc.log-request-details=false** là property của **Spring MVC Servlet**. Spring Framework che request headers/parameters trong framework DEBUG/TRACE mặc định vì dữ liệu có thể nhạy cảm. **spring.codec.log-request-details=false** dành cho codec logging, không thay thế property MVC.

Cả hai **không chặn custom Servlet Filters, outbound HTTP logging, Tomcat access logs hoặc app code tự ghi body**. Đừng coi một property là chứng chỉ dữ liệu được bảo vệ ở mọi layer.

### Không bật debug=true/trace=true trên toàn production

Spring Boot **--debug**, **debug=true**, **--trace**, **trace=true** tăng logging cho một tập core loggers. Chúng không đặt tất cả logger thành DEBUG/TRACE đồng loạt, nhưng vẫn có thể mở rộng ngoài phạm vi điều tra.

Không dùng:

~~~properties
# Anti-pattern tren production
logging.level.root=TRACE
logging.level.org.springframework=TRACE
logging.level.org.springframework.security=TRACE
~~~

Spring Boot có logging groups **web** và **sql** cho một số packages, nhưng **logging.level.web=DEBUG** có thể mở nhiều logger hơn cần thiết. Khi điều tra một class, đặt mức cho logger cụ thể; khi điều tra security 403, ưu tiên staging/canary và logs đã review.

### Không log mọi 4xx thành ERROR

HTTP 400/401/403/404/429 có thể là kết quả hợp lệ của security/validation/rate limiting. Dùng metrics đếm status và sanitized reason code. Nếu log full stacktrace mỗi lần 404/401, attacker có thể gây log storm bằng traffic không hợp lệ.

## 5. Tomcat access log và nguy cơ path/query

**Tomcat access log** khác application log SLF4J; pattern/rotation/files do Tomcat container quản lý. Spring Boot hỗ trợ **server.tomcat.accesslog.\***. Ví dụ chỉ nên dùng cho local/staging có routes an toàn:

~~~properties
server.tomcat.basedir=./tomcat-work
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=3
~~~

Giải thích Tomcat pattern:

- **%t**: timestamp.
- **%m**: HTTP method.
- **%U**: request path, không bao gồm query string.
- **%s**: status.
- **%D**: thời gian xử lý, **microseconds** trong Tomcat.
- **%r**: HTTP request line có thể chứa query string.
- **%q**: query string.
- **%{Authorization}i**: request Authorization header, không nên đưa vào log.
- **%{Cookie}i** hoặc **%{Set-Cookie}o**: cookies nhạy cảm, không ghi.

**%U vẫn chưa an toàn tuyệt đối!** Nếu app có path **/password/reset/superSecretToken** hoặc **/users/alice@example.test**, Tomcat ghi raw path, không tự thay thành route template. Đối với production nhiều dynamic IDs, có thể tắt Tomcat path logging và dùng HTTP summary với **normalized route/operation key** ở Spring, hoặc triển khai access logs đã redacted tại edge.

Với basedir phía trên, logs thường ở **./tomcat-work/logs/**. Nếu để Tomcat default base directory tạm, logs có thể không được giữ như kỳ vọng. Cấu hình retention, volume, file permissions và log shipping; trong Kubernetes local files có thể mất sau pod restart.

**Không ghi cùng một request năm lần** ở CDN, ingress, Tomcat, Servlet Filter và WebClient nếu không có mục đích rõ. Dùng correlation ID để liên kết những records cần giữ, rồi đặt ngân sách dữ liệu.

## 6. Actuator loggers và khả năng thay đổi mức log runtime

**/actuator/loggers** là endpoint quản trị của Spring Boot Actuator, có thể đọc và đổi configured level của một logger khi endpoint được bật, được expose và caller có quyền. Nó rất hữu ích khi cần DEBUG tạm thời không restart, nhưng là một **control plane nhạy cảm**.

Theo tài liệu Boot 3.3, mặc định **chỉ health được expose qua HTTP/JMX**. Việc có actuator dependency không có nghĩa loggers, env, heapdump hay httpexchanges tự công khai.

Ví dụ dành **chỉ cho local lab hoặc một management plane đã có authentication/TLS/network isolation**:

~~~properties
management.endpoints.web.exposure.include=health,metrics,loggers
~~~

**Tuyệt đối không đặt cấu hình này lên public API không có bảo vệ.** Nếu app có Spring Security và bạn viết custom SecurityFilterChain, hãy kiểm rules cho Actuator; Boot có thể back off default security rules. HTTP POST tới loggers có thể nhận **403** do CSRF/security mặc định; không vô hiệu hóa CSRF toàn ứng dụng để sửa.

Các lệnh sau **chỉ minh họa trên localhost không chứa dữ liệu thật**:

~~~bash
curl -sS \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

~~~bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":"DEBUG"}' \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

Sau khi điều tra, có thể xóa override:

~~~bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":null}' \
  http://localhost:8080/actuator/loggers/com.example.httplog
~~~

**Rollback đúng:** null xóa configured level để thừa hưởng effective level, không tự khôi phục một configured level cũ. Trước thay đổi, lưu chính xác configuredLevel/effectiveLevel và khôi phục đúng cái đã có; runtime change thường chỉ áp dụng **một instance/pod**, có thể mất khi restart.

Không để operator quên DEBUG: dùng incident ticket, approval, owner, time window, TTL, log volume monitoring, explicit rollback và kiểm xác nhận nhiều instances.

## 7. Actuator httpexchanges: không tự động ghi mọi request

**/actuator/httpexchanges** hiển thị HTTP exchanges gần đây khi có **HttpExchangeRepository** và endpoint được enable/expose phù hợp. Spring Boot có implementation **InMemoryHttpExchangeRepository**, thường lưu tối đa 100 exchanges theo mặc định; có thể cấu hình capacity.

Snippet minh họa API Boot 3.3, **không đưa vào demo chính nếu chưa có yêu cầu**:

~~~java
@Bean
HttpExchangeRepository httpExchangeRepository() {
    InMemoryHttpExchangeRepository repository =
            new InMemoryHttpExchangeRepository();
    repository.setCapacity(50);
    return repository;
}
~~~

Imports thuộc **org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository**, **InMemoryHttpExchangeRepository**, **org.springframework.context.annotation.Bean**. Đoạn này cần nằm trong Spring @Configuration đã được scan.

**Điểm giới hạn:**

- Không phải packet capture ghi full body.
- Metadata có thể chứa URI, remote address, headers/cookies tùy recording config; cần privacy review.
- In-memory records mất sau restart, không aggregate đa pod, không phải audit storage.
- Capacity 50 chỉ giới hạn số exchanges, không tự sanitize nội dung mỗi record.
- Expose endpoint ra internet có thể gây lộ metadata; hãy kiểm security nếu thật sự cần dùng.
- Metrics/traces/safe event logs thường phù hợp hơn với observability lâu dài.

## 8. Metrics và tracing giúp giảm nhu cầu DEBUG

Với **Spring Boot Actuator + Micrometer** và registry thích hợp, các HTTP server observations có thể tạo metric **http.server.requests**. HTTP client instrumentation có thể tạo **http.client.requests** khi các clients được dựng qua builders/observability setup phù hợp.

Những câu hỏi không cần full request dumps:

- Request rate và 5xx rate theo route/status?
- p50/p95/p99 latency của từng route khi histograms được cấu hình?
- Dependency inventory hay payment service nào đang timeout?
- Một pod có error cao hơn số còn lại?
- Threads/connection pool/GC đang bị nghẽn?
- Mất thời gian ở ingress, Spring controller hay upstream?

**Metrics tags phải low cardinality**: method, status/outcome, route template/operation name. Không thêm raw URL, customer ID, email, JWT, IP, requestId thành tag; sẽ tạo time series quá nhiều và có nguy cơ rò dữ liệu.

**Traces** dùng traceId/spanId để ghép những chặng xử lý. Nhưng tracing cũng không tự an toàn: raw SQL, baggage hoặc HTTP headers trong span attributes có thể rò PII/secret. Sử dụng allowlist và sampling đã đánh giá.

**Không suy rằng có Actuator là tracing tự hoạt động end-to-end.** Cần Micrometer Tracing bridge/exporter, instrumentation và trace context propagation phù hợp. Audit events bắt buộc được lưu riêng và không được mất chỉ vì sampling traces hoặc success logs.

## 9. Demo runnable Java 17 + Spring Boot 3.3

Ta xây API nhận POST body chứa một **secret canary giả** nhưng log chỉ có **route allowlisted, method, status, duration và request ID tự sinh**.

Dự án dùng Spring Boot **3.3.13**, Java 17+, Maven, embedded Tomcat. Trong sản phẩm mới nên chọn nhánh Spring Boot còn được bảo trì; ví dụ chỉ minh họa logging policy, không cung cấp authentication cho API demo.

~~~text
http-logging-demo/
  pom.xml
  src/main/java/com/example/httplog/
    HttpLoggingDemoApplication.java
    SafeRequestSummaryFilter.java
    DiagnosticDemoController.java
  src/main/resources/
    application.properties
    application-local.properties
    application-prod.properties
  src/test/java/com/example/httplog/
    SafeHttpLoggingIntegrationTests.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-logging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. application.properties

~~~properties
server.port=8080
spring.application.name=http-logging-demo

logging.level.root=INFO
logging.level.com.example.httplog=INFO

spring.mvc.log-request-details=false
spring.codec.log-request-details=false

server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never

# Default Actuator public surface chi health.
management.endpoints.web.exposure.include=health

# In requestId tu Logback MDC tren request thread.
logging.pattern.level=%5p [req:%X{requestId}]
~~~

**MDC** (Mapped Diagnostic Context) cung cấp context thuộc thread, không phải storage của request body. Nếu quên dọn MDC trong Servlet thread pool, request sau có thể mang nhầm ID của request trước.

### 9.3. application-local.properties

~~~properties
# Dung trong local voi du lieu synthetic.
logging.level.com.example.httplog=DEBUG

# Chi o local/staging hoac management duoc bao ve.
management.endpoints.web.exposure.include=health,metrics

server.tomcat.basedir=./tomcat-work
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%t %m %U %s %D
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=3
~~~

### 9.4. application-prod.properties

~~~properties
logging.level.root=INFO
logging.level.com.example.httplog=INFO
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO
logging.level.org.apache.catalina=INFO

spring.mvc.log-request-details=false
spring.codec.log-request-details=false
server.tomcat.accesslog.enabled=false

management.endpoints.web.exposure.include=health
~~~

Prod profile tránh access log path-level mặc định trong demo và không expose metrics/loggers trên public API. Hệ thống thật có thể phục vụ metrics qua network riêng và authentication; không phải mọi production app phải tắt metrics, mà cần bảo vệ đúng.

### 9.5. Main class

Tạo **src/main/java/com/example/httplog/HttpLoggingDemoApplication.java**:

~~~java
package com.example.httplog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpLoggingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpLoggingDemoApplication.class, args);
    }
}
~~~

### 9.6. SafeRequestSummaryFilter

Tạo **src/main/java/com/example/httplog/SafeRequestSummaryFilter.java**:

~~~java
package com.example.httplog;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SafeRequestSummaryFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRequestSummaryFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        String oldRequestId = MDC.get("requestId");
        long started = System.nanoTime();

        request.setAttribute("safeRequestId", requestId);
        response.setHeader("X-Request-Id", requestId);
        MDC.put("requestId", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            try {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                String route = switch (request.getRequestURI()) {
                    case "/api/demo" -> "/api/demo";
                    default -> "other";
                };

                String method = switch (request.getMethod()) {
                    case "GET" -> "GET";
                    case "POST" -> "POST";
                    default -> "OTHER";
                };

                log.info(
                    "http.request route={} method={} status={} elapsedMs={}",
                    route, method, response.getStatus(), elapsedMs);
            } finally {
                // Khong de MDC requestId ro sang thread duoc tai su dung.
                if (oldRequestId == null) {
                    MDC.remove("requestId");
                } else {
                    MDC.put("requestId", oldRequestId);
                }
            }
        }
    }
}
~~~

**Tại sao an toàn hơn raw request logging?**

- Server tự sinh requestId UUID, không tin một arbitrary X-Request-Id từ client như identity.
- Không đọc query string, request body, Authorization, Cookie hoặc response body.
- Route key chỉ gồm **/api/demo** và **other**; input path chứa PII không xuất hiện raw.
- Method cũng được whitelist để tránh log input kỳ lạ.
- Duration tính milliseconds, khác Tomcat %D microseconds.
- MDC luôn được restore/clear bằng nested finally, kể cả khi logger/appender gặp lỗi.
- Filter là **HTTP summary cho synchronous request**, không phải một full tracing solution.

**Giới hạn:** Servlet **async dispatch**, **SSE/DeferredResult** và error dispatch có lifecycle khác. Initial filter finally có thể chạy trước final response; response.getStatus() có thể chưa là final status khi exception được container/error handler xử lý sau đó. Dùng **Micrometer HTTP server observations**, Tomcat container metrics hoặc async-aware logging cho SLO/final latency. Đây là demo an toàn về dữ liệu, không cam kết coverage đầy đủ cho mọi loại request.

### 9.7. DiagnosticDemoController

Tạo **src/main/java/com/example/httplog/DiagnosticDemoController.java**:

~~~java
package com.example.httplog;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DiagnosticDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticDemoController.class);

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> get(HttpServletRequest request) {
        log.debug("demo GET handler selected");
        return Map.of(
                "message", "ok",
                "requestId", request.getAttribute("safeRequestId"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> post(
            @RequestBody Map<String, Object> body,
            HttpServletRequest request) {

        // KHONG ghi input.toString(), header hay body.
        log.debug("demo POST accepted fieldCount={}", body.size());

        return Map.of(
                "accepted", true,
                "fieldCount", body.size(),
                "requestId", request.getAttribute("safeRequestId"));
    }
}
~~~

**Tên file khớp public class**, package root com.example.httplog thống nhất. Controller không dùng logic lưu data; nó chỉ cho thấy POST JSON có thể được xử lý mà không dump body vào logs. FieldCount là số key top-level; trong API thật vẫn cần xem đó có phải metadata cần trả ra không.

## 10. Chạy demo bằng Maven và curl

Trong thư mục có pom.xml, với Java 17+:

~~~bash
mvn clean test
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Mở terminal thứ hai:

~~~bash
curl -si http://localhost:8080/api/demo
~~~

Response có JSON với **message=ok** và **requestId** do server sinh. Giá trị requestId khác mỗi request, nên không thể cho stdout literal cố định. Header **X-Request-Id** mang cùng UUID.

Gửi POST bằng **canaries giả, tuyệt đối không dùng secret thật**:

~~~bash
curl -si \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer DEMO_TOKEN_NOT_REAL' \
  -H 'Cookie: JSESSIONID=DEMO_SESSION_NOT_REAL' \
  --data '{"comment":"hello","secret":"CANARY_SECRET_9D2F"}' \
  http://localhost:8080/api/demo
~~~

Kỳ vọng response logic (requestId là giá trị runtime):

~~~json
{
  "accepted": true,
  "fieldCount": 2,
  "requestId": "server-generated-uuid"
}
~~~

**server-generated-uuid** chỉ là placeholder minh họa, không phải output thực. Log từ ứng dụng có thể tương tự:

~~~text
INFO ... [req:UUID] ... SafeRequestSummaryFilter : http.request route=/api/demo method=POST status=200 elapsedMs=5
DEBUG ... DiagnosticDemoController : demo POST accepted fieldCount=2
~~~

Ví dụ log trên là mẫu; timestamp, UUID, thứ tự thread log và elapsedMs thay đổi. **Không được có** CANARY_SECRET_9D2F, DEMO_TOKEN_NOT_REAL hoặc DEMO_SESSION_NOT_REAL trong application stdout/stderr của demo.

Dừng server local rồi thử prod profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Ở profile prod, dòng **DEBUG demo POST accepted** sẽ không xuất hiện, còn summary INFO vẫn được ghi. Tránh chạy hai processes cùng port. Không đưa demo chưa có authentication/TLS ra internet.

**Tomcat access log** trong local profile thường nằm tại **./tomcat-work/logs/** và có thể không in trên console. Đừng kết luận không có log chỉ vì stdout trống; cần kiểm file path và basedir đúng.

## 11. Test tự động bằng secret canary

Thêm integration test **src/test/java/com/example/httplog/SafeHttpLoggingIntegrationTests.java**:

~~~java
package com.example.httplog;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(OutputCaptureExtension.class)
class SafeHttpLoggingIntegrationTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    @Test
    void canaryNeverAppearsInApplicationOutput(
            CapturedOutput output) throws Exception {

        String bodyCanary = "CANARY_SECRET_9D2F";
        String tokenCanary = "DEMO_TOKEN_NOT_REAL";
        String cookieCanary = "DEMO_SESSION_NOT_REAL";

        String json = "{\"comment\":\"hello\","
                + "\"secret\":\"" + bodyCanary + "\"}";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/demo"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + tokenCanary)
                .header("Cookie", "JSESSIONID=" + cookieCanary)
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
                .firstValue("X-Request-Id").isPresent());

        String logs = output.getAll();
        assertFalse(logs.contains(bodyCanary));
        assertFalse(logs.contains(tokenCanary));
        assertFalse(logs.contains(cookieCanary));
        assertTrue(logs.contains(
                "http.request route=/api/demo method=POST status=200"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test khởi động Spring Boot trên **RANDOM_PORT**, dùng Java 17 **HttpClient** gửi POST thật, kiểm X-Request-Id, tìm summary và bảo đảm canaries không hiện trong output do **OutputCaptureExtension** bắt được.

**Giới hạn rõ ràng:** OutputCaptureExtension không kiểm CDN/Nginx/collector/sidecar/JVM agent hay Tomcat access file riêng. Test chỉ kiểm các đường logging thuộc process và kịch bản đã chạy. Muốn an toàn hơn, audit code paths, test canary ở các tầng có quyền truy cập và định nghĩa log governance.

**Không dùng real token/password trong test.** Kết hợp các canary synthetic với static code review, redaction checks, penetration testing và alert khi logs chứa pattern đặc trưng của secret.

## 12. MDC, structured logging và correlation

Một production event có thể được thiết kế:

~~~json
{
  "timestamp": "2026-11-08T08:30:00Z",
  "service": "catalog-api",
  "environment": "prod",
  "level": "INFO",
  "event": "http.request",
  "route": "/api/orders/{id}",
  "method": "GET",
  "status": 200,
  "duration_ms": 17,
  "request_id": "example-correlation-id"
}
~~~

Đây là **schema minh họa**, không phải JSON format mặc định của Boot 3.3. Có thể dùng Logback/Log4j2 structured encoder phù hợp; không copy properties mới của Spring Boot 4.x rồi giả định chúng có trong 3.3.

**MDC là thread-local**: nếu request xử lý qua @Async, CompletableFuture, Executor, Reactor/WebFlux, cần context propagation thích hợp. Không tự chuyển toàn bộ baggage/MDC fields giữa trust boundaries, vì có thể chứa dữ liệu nhạy cảm. Với Micrometer Tracing/Observation được cấu hình, traceId/spanId có thể được gắn vào logs; không suy rằng chỉ thêm Actuator là có distributed tracing.

**Request ID không xác thực user.** Nếu nhận X-Request-Id từ gateway, phải validate kí tự và giới hạn chiều dài (ví dụ 8–64 ký tự ASCII letter/digit/hyphen/underscore) và có trust boundary. Demo luôn sinh UUID server-side.

## 13. Servlet async/error dispatch làm thay đổi số đo

Các loại Servlet dispatch phổ biến:

- **REQUEST**: initial HTTP dispatch.
- **ASYNC**: xử lý tiếp khi DeferredResult/Callable/streaming.
- **ERROR**: dispatch vào error handler sau lỗi.
- **FORWARD/INCLUDE**: servlet routing nội bộ.

Trong demo, **OncePerRequestFilter** log ở initial synchronous dispatch. Với SSE/DeferredResult, filter có thể kết thúc trước khi response thực hoàn thành. Với exception chưa được resolver xử lý, response status khi finally có thể chưa phải status cuối cùng. Vì vậy:

1. Dùng metrics/container instrument cho final HTTP duration/status.
2. Nếu cần custom filter hoàn chỉnh, phải xử lý asyncSupported/dispatcher types, callback lúc request kết thúc, MDC propagation và cleanup đúng.
3. Không ghi trùng multiple dispatches thành nhiều request không chủ ý.
4. Test bằng async endpoints, timeout và exception path, không chỉ GET sync.
5. Không nhầm initial HTTP processing time với end-to-end SSE/WebSocket connection lifetime.

Để đo SLO, **http.server.requests** và server connector metrics thường đáng tin hơn một demo filter đơn giản.

## 14. Sampling, rate limiting và log budgets

Một phép tính minh họa:

- 1.000 requests/giây.
- 10 dòng log/request.
- 500 bytes/dòng.

Kết quả khoảng **5 MB/giây**, tức **432 GB/ngày** trước compression/indexing. Chỉ còn một dòng/request vẫn khoảng **43,2 GB/ngày**. Đây là ước lượng lý thuyết để giúp tính chi phí, không phải đo thực tế.

Các biện pháp:

- **Sampling** một phần success events, không sampling mất audit bắt buộc.
- **Rate limiting/dedup** stack traces và warnings lặp, giữ counter tổng để biết tần suất.
- **Bỏ log body hoặc payload toString**, giới hạn max bytes/event.
- **Async appenders có bounded queue** khi cần throughput; theo dõi dropped events và block behavior khi đầy.
- **Rotation/retention/storage quotas**, encryption và IAM hạn chế người xem logs.
- **Metrics-based alerts** cho ingestion bytes/s, collector lag, disk pressure, CPU và p99.
- **Cân nhắc số layers** cùng phát access logs; tránh duplication không cần thiết.
- **TTL** cho DEBUG thay vì để lâu dài trong cấu hình production.
- **Không tự bật TRACE toàn fleet** khi 5xx tăng vì có thể gây log storm đúng lúc incident.

Logging có thể làm chậm API không chỉ vì I/O. Định dạng JSON lớn, serialize stack trace, đọc body để cache và stringify object phức tạp đều tốn CPU/bộ nhớ trước khi giao cho appender.

## 15. Exceptions, Spring Security và outbound HTTP

### Spring Security

Spring Security DEBUG/TRACE có thể giúp tìm nguyên nhân **401, 403, CSRF, filter chain**. Chỉ bật logger/package cần thiết với dữ liệu đã review, trên một pod hoặc staging nếu có thể. Không đánh đồng 401/403 với ERROR: nhiều trường hợp là security policy đúng.

### Exceptions và response

**exception.getMessage() có thể không an toàn**: message có thể chứa SQL bind values, raw URL, client input hoặc upstream response text. Chọn sanitized error code, exception type được phép, correlation ID và stack trace có rate limits. Error body trả browser cần không lộ stacktrace/exception message.

### Outbound HTTP clients

**RestClient, RestTemplate, WebClient, Reactor Netty, Apache HttpClient, OkHttp** có interceptors/filters/wire logging khác inbound Servlet. Cẩn thận **wiretap** và TRACE khi outgoing requests mang Authorization, Cookie hoặc data. Property **spring.mvc.log-request-details=false** không bảo vệ outbound client logger.

Nếu dùng **http.client.requests** metrics, labels nên là dependency/templated route và status, không phải raw URL với query tokens.

### Database logging

SQL query shape có thể hữu ích nhưng bind parameter TRACE có thể tiết lộ PII và secret; tránh bật Hibernate/JDBC parameter logging toàn production chỉ để debug một HTTP request.

## 16. Proxy, container và multi-pod: mọi hop có policy riêng

Một request có thể được log tại:

~~~text
Browser
  |
  v
CDN / WAF / API Gateway
  |
  v
Nginx / Ingress / Service Mesh
  |
  v
Tomcat connector
  |
  v
Spring MVC Filter -> Controller
  |
  v
Logback -> stdout -> Collector -> SIEM
~~~

**Log masking trong Spring không tự che dữ liệu của Nginx/CDN.** Raw request line ở proxy có thể chứa query token ngay cả khi backend chỉ log status/route. Kiểm từng nơi thu thập dữ liệu, access control, retention, forwarding, redaction.

**Forwarded/X-Forwarded-For** có thể bị giả nếu edge không xóa headers không tin cậy. Không ghi hoặc dùng raw forwarded IP như identity/authorization mặc định. IP còn có thể là dữ liệu cá nhân theo chính sách.

Trong Kubernetes:

- stdout/stderr thường được runtime và collector xử lý.
- Tomcat file logs có thể nằm ở container filesystem và mất khi pod restart.
- Runtime Actuator logger change có thể chỉ ảnh hưởng một pod sau load balancer.
- Collector lag và log volume có thể ảnh hưởng request throughput.
- Correlation IDs, service/instance labels và timestamps UTC giúp điều tra nhiều pods.
- Không đặt raw logs có secrets vào public bucket, ConfigMap, image layer hoặc support ticket.

## 17. Runbook bật DEBUG trong incident

Giả sử p99 latency của **POST /api/payments** tăng. Quy trình tốt:

1. **Đặt giả thuyết** cụ thể (inventory gateway chậm, pool nghẽn hay auth filter?).
2. **Dùng metrics/traces trước** để xác định dependency/pod/route.
3. **Chọn logger nhỏ nhất** của code path cần kiểm, không root/org.springframework TRACE.
4. **Review logger message** xem có ghi body/headers/query hoặc exception text nhạy cảm không.
5. **Approval/incident ID/owner**, TTL ví dụ 5–10 phút, đúng subset pods và traffic.
6. **Lưu configuredLevel cũ**, có rollback plan và audit hành động.
7. **Bật qua secured management channel**, không public Actuator.
8. **Giám sát volume/CPU/p99**, rollback ngay nếu log storm hoặc leak.
9. **Khôi phục đúng levels** trên mọi instance, kiểm output đã về baseline.
10. **Quản trị dữ liệu đã thu**, retention/quarantine nếu cần, và bổ sung sanitized event/metric để lần sau ít cần DEBUG.

Thời hạn 5–10 phút chỉ là ví dụ operational policy, không phải mặc định do Spring đặt.

## 18. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Log đầy disk | TRACE rộng/access log duplicate | Hạ level, rate limit, rotate, quota. |
| 401 nhiều nhưng Security log khó hiểu | Thiếu context phù hợp hoặc entry point chung | Bật Security DEBUG rất hẹp trên synthetic/canary, kiểm policy. |
| Authorization xuất hiện ở logs | Custom filter/interceptor/wiretap hoặc details logging | Ngừng thu, cách ly logs, xử lý rò rỉ. |
| app log an toàn nhưng CDN leak query | Edge access log có raw URI | Review proxy fields và retention. |
| RequestId lặp ở request mới | MDC chưa clear trong thread pool | finally cleanup, test concurrent/async. |
| Filter ghi 200 nhưng actual trả 500 | Error dispatch/async lifecycle | Dùng observations/final connector status. |
| /actuator/loggers 404 | Không expose/enable hoặc bị security rules | Kiểm management config; không mở public. |
| POST loggers 403 | Authentication/authorization/CSRF | Dùng quản trị có quyền, không tắt CSRF toàn app. |
| httpexchanges trống | Không có HttpExchangeRepository | Đánh giá có cần bật không, nếu có thì bảo vệ. |
| Metrics cardinality cao | Raw URI/userId/requestId tags | Route template và low cardinality labels. |
| WebClient TRACE lộ body | Wiretap/ExchangeFilterFunction logs | Tắt, thay sanitized events. |
| Một pod khác level | Actuator change không đồng bộ replicas | Chỉnh/rollback theo instance. |
| Test canary PASS nhưng production leak | Proxy, agent, code path khác | End-to-end review và kiểm collectors. |

## 19. Checklist production

- [ ] Có data classification và allowlist fields cho logs, metrics, traces và audit.
- [ ] Root INFO/WARN phù hợp SLO, không bật TRACE rộng.
- [ ] **spring.mvc.log-request-details=false** và **spring.codec.log-request-details=false** theo stack.
- [ ] Không log Authorization, Cookie, Set-Cookie, API keys, JWT, passwords, raw body.
- [ ] Không log raw query strings, cẩn thận path variables trong Tomcat %U.
- [ ] Có requestId/traceId an toàn để liên kết request, không dùng chúng làm authentication.
- [ ] MDC cleanup trong finally, review async/reused threads.
- [ ] Sử dụng route template hoặc operation key cho HTTP summary.
- [ ] Giới hạn Actuator exposure, nhất là loggers, logfile, httpexchanges, env, heapdump.
- [ ] Mọi DEBUG prod có owner/approval/TTL/scope/rollback và log volume monitoring.
- [ ] Có chính sách quota/rotation/retention/encryption/access cho log collectors.
- [ ] Không sampling mất audit events bắt buộc.
- [ ] Có safe error codes và không trả raw stack traces ra HTTP responses.
- [ ] Review logging ở gateway, Nginx, Tomcat, HTTP clients, database và tracing agents.
- [ ] Test canary secrets trong CI, đồng thời rà soát các tầng ngoài app.
- [ ] Theo dõi logs bytes/s, dropped events, CPU, disk, p99 khi thay level.
- [ ] Với migration Boot/Framework versions, kiểm lại property names và behavior.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao root TRACE không phù hợp làm production baseline?**  
Vì gây log volume lớn, tốn CPU/I/O và dễ lộ dữ liệu nhạy cảm.

**2. Property MVC nào giữ request details bị che ở DEBUG/TRACE?**  
**spring.mvc.log-request-details=false**.

**3. Property ấy có chặn custom Servlet Filter log body không?**  
Không. Custom logging code phải tự tuân thủ allowlist.

**4. %U trong Tomcat access log có tự biến ID thành route template không?**  
Không. Nó vẫn ghi path thực và có thể chứa PII.

**5. Có nên ghi Authorization để debug 401?**  
Không. Dùng sanitized code, correlation và security diagnostics scope hẹp.

**6. Có nên mở /actuator/loggers public không?**  
Không. Đây là administrative control plane cần authentication/authorization/network protection.

**7. configuredLevel null có luôn rollback đúng không?**  
Không. Nó bỏ override, phải lưu và khôi phục level cũ nếu từng cấu hình.

**8. Httpexchanges có tự lưu request khi chỉ có Actuator dependency?**  
Không. Cần HttpExchangeRepository và endpoint phải được enable/expose.

**9. Vì sao requestId không xác minh user?**  
Vì chỉ để correlation; nếu lấy từ client, nó còn có thể bị giả mạo.

**10. Demo Filter có đo đúng final elapsed time cho SSE/DeferredResult không?**  
Không bảo đảm. Nó đo initial synchronous dispatch.

**11. Canary test PASS có chứng minh CDN không leak dữ liệu?**  
Không. Test không nhìn CDN/agent/collector.

**12. Có nên gắn raw URI vào http.server.requests tags không?**  
Không. Dùng route template để tránh high cardinality và PII.

**13. Micrometer tracing có sẵn chỉ vì import Spring Web không?**  
Không. Cần instrumentation/tracing dependencies và backend phù hợp.

**14. Có thể sampling bỏ security audit để tiết kiệm không?**  
Không nếu audit phải lưu đầy đủ theo chính sách.

**15. Khi incident chỉ xảy ra với một upstream, bật logger gì?**  
Logger class/package nhỏ nhất có message an toàn, có TTL và rollback.

## 21. Nguồn tài liệu chính thức

- **Spring Boot 3.3 – Logging:** https://docs.spring.io/spring-boot/3.3/reference/features/logging.html — logging.level.*, log groups, DEBUG/TRACE, MDC.
- **Spring Boot 3.3 – Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — spring.mvc.log-request-details, spring.codec.log-request-details, server.error.*, Tomcat access logs.
- **Spring Framework – MVC Logging:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/logging.html — masking headers/request parameters.
- **Spring Security – Servlet Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html — logging for 401/403, filter chain.
- **Spring Boot 3.3 – Actuator Endpoints:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — loggers, httpexchanges, exposure và CSRF.
- **Spring Boot 3.3 – Observability:** https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html — Micrometer Observation, metrics/traces, cardinality.
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — Tomcat accesslog config, directory và time units.
- **Spring Framework – Servlet Filters:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — filter lifecycle và forwarded header trust.
- **OWASP – Logging Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html — data exclusions, log injection, retention và security.
