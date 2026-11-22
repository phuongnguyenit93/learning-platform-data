# Nhãn URI theo mẫu đường dẫn và tránh số lượng giá trị nhãn quá lớn

> **Module:** Spring Boot - web-runtime · **Nhóm:** Quan sát HTTP. Chủ đề bài học là cách gắn nhãn `uri` của HTTP metrics/observations theo **mẫu đường dẫn (route/URI template)** thay vì giá trị URL cụ thể, từ đó kiểm soát **cardinality** và chi phí metrics. Các ví dụ dùng **Spring Boot 4.1.2**, **Java 17+**, Spring MVC, Micrometer, Actuator và Prometheus; có đối chiếu WebFlux, RestClient/WebClient, trace và các điểm dễ nhầm khi Spring Security từ chối request trước khi controller được chọn.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **URI thực tế**, **URI template**, query string, route pattern, HTTP method, HTTP status và một **label/tag** của meter.
2. Giải thích vì sao `/api/users/123` và `/api/users/456` nên có cùng giá trị nhãn metrics `uri="/api/users/{userId}"`, không phải hai nhãn khác nhau.
3. Tính tác động của cardinality lên số time series khi kết hợp `uri` với method, status, outcome, instance và histogram buckets.
4. Sử dụng instrumentation mặc định Spring MVC/WebFlux với `http.server.requests`, hiểu low-cardinality key `uri` và high-cardinality key `http.url` trong **Observation**.
5. Cấu hình Spring Boot Actuator `/actuator/metrics/http.server.requests`, xuất `/actuator/prometheus` và kiểm bằng cURL.
6. Tạo dự án Maven Spring Boot 4.1.2 có các đường dẫn chứa ID, chứng minh nhiều requests vẫn gộp vào một URI template trong metrics.
7. Viết outbound `RestClient`/`WebClient` với URI template, tránh dùng raw URL hoặc ID làm tag tùy tiện; hiểu `uri=none`/`UNKNOWN`/`NOT_FOUND` và ranh giới trước handler mapping.
8. Áp dụng `management.metrics.web.server.max-uri-tags`, `management.metrics.web.client.max-uri-tags` và `MeterFilter` như **hàng rào cuối**, không coi đó là cách thay cho sửa nhãn sai.
9. Thiết kế chính sách label allowlist, bảo vệ PII/token, quy trình phát hiện cardinality explosion và dashboard/alert vận hành.

## 2. Bản chất của URI template và raw URI

Một Spring MVC route:

~~~java
@GetMapping("/api/users/{userId}")
public String user(@PathVariable String userId) {
    return "user=" + userId;
}
~~~

Có thể xử lý nhiều yêu cầu HTTP:

~~~text
GET /api/users/1
GET /api/users/2
GET /api/users/3
GET /api/users/customer-abcdef
GET /api/users/550e8400-e29b-41d4-a716-446655440000
~~~

Đây là **năm raw paths khác nhau**, nhưng chỉ **một route pattern**:

~~~text
/api/users/{userId}
~~~

Đối với metric đo thời gian phản hồi và tỷ lệ lỗi theo endpoint nghiệp vụ, câu hỏi hữu ích là: “GET /api/users/{userId} mất bao lâu?” chứ không phải tạo một meter riêng cho mỗi khách hàng/UUID.

| Thành phần | Ví dụ | Có nên đưa nguyên vẹn vào metrics label? |
| --- | --- | --- |
| URI template | `/api/users/{userId}` | **Có**, tập giá trị được kiểm soát |
| Raw URI path | `/api/users/123456` | **Không**, số lượng ID có thể tăng mãi |
| Query string | `?email=a@example.test&page=123` | **Không**, có thể chứa PII/vô hạn biến thể |
| URL gồm host | `https://api.example.test/api/users/123456` | Không dùng làm nhãn low-cardinality của server |
| Method | `GET`, `POST` | Có, tập hữu hạn |
| HTTP status | `200`, `404`, `500` | Có, tập hữu hạn tương đối |
| Error class | `IOException`, `none` | Có thể, nhưng kiểm số kiểu lỗi và cấu hình |
| User ID / session ID | `u-39284923`, `sess-a1...` | **Không**, vừa high-cardinality vừa nhạy cảm |
| Tenant ID tự do | `tenant-839201` | Thường **không**; cân nhắc tier/nhóm được whitelist |
| HTTP route group | `billing`, `catalog`, `auth` | Có thể, nếu số nhóm ổn định |

**Route template là mô tả cấu trúc endpoint**, không phải thao tác replace tùy tiện các chữ số trong URL. Ví dụ `/api/v2/users/123`: `v2` là phần version cố định cần giữ, còn `123` có thể là path variable. Một regex thay mọi dãy số bằng `{id}` sẽ mất version, làm các routes không liên quan bị gộp sai.

### 2.1. Mẫu ổn định không đồng nghĩa mọi thứ đều cùng một mẫu

Các endpoints:

~~~text
/api/users/{userId}
/api/users/{userId}/orders/{orderId}
/api/orders/{orderId}
/api/search
/api/health
~~~

là **năm nhóm route khác nhau** nếu ứng dụng khai báo và quan sát như vậy. Không nên gộp toàn bộ thành `/api/**` vì metrics sẽ mất khả năng so sánh endpoint. Mục tiêu là **độ chi tiết vừa đủ để ra quyết định vận hành**, không phải giảm toàn bộ labels về một giá trị.

### 2.2. Query parameters không phải route template

Các yêu cầu:

~~~text
GET /api/search?q=java&page=1
GET /api/search?q=spring&page=999
GET /api/search?q=private-email@example.test&page=3
~~~

thường cùng route pattern `/api/search`. Query values có thể có cardinality rất cao và chứa dữ liệu nhạy cảm. Nếu cần đo loại truy vấn, tạo **nhóm định sẵn** như `search_type=prefix|exact|fuzzy|other` với allowlist, không gắn nguyên query hoặc email vào meter.

## 3. Cardinality là gì và tại sao nó gây sự cố?

Một metric time series thường được xác định bởi **metric name + tập labels/tags đầy đủ**. Khi thay bất kỳ label value, hệ thống có thể tạo một series mới.

Ví dụ:

~~~text
http_server_requests_seconds_count{
  method="GET",
  uri="/api/users/{userId}",
  status="200",
  outcome="SUCCESS",
  instance="app-1"
}
~~~

Nếu thay `uri="/api/users/{userId}"` bằng `uri="/api/users/943573"`, mỗi ID mới có thể sinh thêm chuỗi đo riêng cho endpoint **không hề khác nhau về behavior**.

Cardinality explosion dẫn tới:

- Nhiều `Meter.Id` và timer/histogram được tạo trong JVM.
- Nhiều label sets trong Prometheus hoặc backend tương tự.
- RAM, CPU, allocation, GC và bộ nhớ lưu trữ/chi phí observability tăng.
- Scrape payload lớn hơn; scrape timeout và remote write backlog.
- PromQL queries/recording rules nặng hơn; dashboard chậm.
- Nhãn có token/user ID làm lộ thông tin trong monitoring.
- Khi hệ thống có cap, series mới có thể bị **từ chối**, mất khả năng quan sát các endpoints xuất hiện sau đó.

### 3.1. Đếm tổ hợp nhãn

Giả sử, theo giả định lý thuyết:

- 200 URI patterns.
- 4 HTTP methods mỗi route.
- 5 status codes có thể xảy ra.
- 10 service instances.

Số tổ hợp tối đa theo các trục này khoảng:

~~~text
200 × 4 × 5 × 10 = 40,000 label combinations
~~~

Nếu publisher thêm **20 histogram buckets** cho một số metric trên mỗi label combination, tổng các chuỗi bucket có thể nhân lên đáng kể, chưa kể count/sum hoặc các nhãn khác. **Đây là upper-bound minh họa**, không khẳng định mọi route có đủ mọi status/method hay mọi instance xuất hiện trong cùng một scrape; `outcome` còn liên quan trực tiếp tới `status` nên không nên nhân nó như một chiều độc lập vô điều kiện.

Nếu thay 200 templates thành 200.000 raw IDs, cùng một hệ số nhân sẽ lớn hơn theo bậc hàng nghìn. Không có ngân sách CPU/RAM nào đáng dùng chỉ để giữ từng giá trị ID của cùng một endpoint ở metrics.

### 3.2. Một Java demo độc lập để thấy cardinality

Tạo file `CardinalityExample.java`:

~~~java
import java.util.HashSet;
import java.util.Set;

public class CardinalityExample {
    public static void main(String[] args) {
        Set<String> rawUris = new HashSet<>();
        Set<String> routeTemplates = new HashSet<>();

        for (int id = 1; id <= 10_000; id++) {
            rawUris.add("/api/users/" + id);
            routeTemplates.add("/api/users/{userId}");
        }

        System.out.println("Unique raw URI values: " + rawUris.size());
        System.out.println("Unique route templates: " + routeTemplates.size());
    }
}
~~~

Chạy với JDK 17:

~~~bash
javac --release 17 CardinalityExample.java
java CardinalityExample
~~~

Stdout chính xác:

~~~text
Unique raw URI values: 10000
Unique route templates: 1
~~~

Đây là demo của `Set` trong Java, **không** đo số meter Spring Boot thực. Nó chỉ chứng minh vì sao tag theo route template có cardinality thấp hơn. Trong production, luôn đo metric series thực sau khi scrape thay vì suy ra từ code duy nhất.

## 4. Spring Boot, Micrometer và Observation

Spring Boot Actuator tích hợp Micrometer metrics và Observation API để quan sát HTTP server và HTTP clients. Với Spring MVC/WebFlux, instrumentation mặc định tạo observations gắn với `http.server.requests`; với outbound clients, `http.client.requests`.

~~~text
HTTP request
   |
   v
Spring MVC / WebFlux instrumentation
   |
   v
ObservationRegistry
   +-- low-cardinality KeyValues  -> Micrometer metrics
   +-- high-cardinality KeyValues -> tracing (nếu được cấu hình)
   |
   v
MeterRegistry / Prometheus registry
   |
   v
/actuator/metrics (chẩn đoán) /actuator/prometheus (scrape)
   |
   v
Prometheus, Grafana hoặc monitoring backend khác
~~~

**Quan trọng:** Không có nghĩa mọi trace field tự động trở thành metrics labels. Trong Spring Observation, **low-cardinality key values** phục vụ metrics; **high-cardinality key values** có thể được ghi vào traces tùy tracing integration. Không tự promote `http.url`, `user.id` hay query vào meter tags.

### 4.1. Low-cardinality labels mặc định của HTTP server

Theo Spring Framework Observation conventions, các trường thường có:

| Key | Ý nghĩa |
| --- | --- |
| `method` | HTTP method hoặc `none` khi không hợp lệ |
| `status` | Status code hoặc `UNKNOWN` nếu chưa có response |
| `outcome` | Nhóm kết quả HTTP, ví dụ SUCCESS, CLIENT_ERROR |
| `uri` | **Mẫu route** nếu mapping đã được xác định; fallback khi chưa có |
| `error` | Class lỗi hoặc `none` tùy exception handling/convention |
| `exception` | Trường tương thích cũ, có thể deprecated/loại bỏ trong phiên bản tương lai |

Chính `uri` là đối tượng của bài học. Nếu controller khai báo `@GetMapping("/api/users/{userId}")` và request mapping thành công, label thường là `/api/users/{userId}`, **không** phải số ID đã thay vào path.

### 4.2. High-cardinality URL và quyền riêng tư

Spring Framework cũng ghi nhận high-cardinality key như `http.url` trong context/tracing. URL thực có thể chứa IDs, query string hoặc giá trị nhạy cảm. Cho nên:

- **Không** copy `http.url` vào low-cardinality metric tag.
- Không đẩy credentials, tokens, PII vào URL ngay cả khi không tạo metrics tags: URL còn xuất hiện trong access logs, proxies, traces và browser history.
- Với tracing, đặt sampling, access controls, retention và redaction/sanitization đúng nghiệp vụ.
- Không mặc định các thành phần tracing sẽ lọc sạch PII chỉ vì Micrometer metrics không thu nó.

### 4.3. MVC và WebFlux giống mục tiêu, khác các extension points

Spring Boot tự động instrument requests từ Spring MVC controllers/functional handlers và WebFlux controllers/functional handlers khi đúng dependencies. Hai stack dùng conventions tương ứng:

| | MVC / Servlet | WebFlux / Reactive |
| --- | --- | --- |
| HTTP handler pipeline | `DispatcherServlet` | `DispatcherHandler` |
| Observation server filter | `ServerHttpObservationFilter` kiểu Servlet | `ServerHttpObservationFilter` kiểu WebFilter reactive |
| Default convention class | `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` | `org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention` |
| Observation context | Servlet `ServerRequestObservationContext` | Reactive `ServerRequestObservationContext` |
| URI label | Matched route pattern nếu được biết | Matched route pattern nếu được biết |
| High-cardinality URL | Có thể thuộc tracing | Có thể thuộc tracing |

Đừng copy một custom `ServerRequestObservationConvention` của Servlet rồi đưa sang WebFlux: type packages/context khác nhau. Hãy ưu tiên convention mặc định nếu không có nhu cầu chính đáng để thay nhãn.

## 5. Giá trị đặc biệt của nhãn uri: UNKNOWN, NOT_FOUND, REDIRECTION

Không phải mọi HTTP request đều đến được handler mapping. Spring Framework có các fallback values để giữ cardinality thấp:

- `uri="/api/users/{userId}"` khi route pattern đã được xác định.
- `uri="NOT_FOUND"` với request 404 mà không có matching handler phù hợp.
- `uri="REDIRECTION"` trong trường hợp chuyển hướng 3xx không có matching pattern.
- `uri="root"` khi không có path info theo convention.
- `uri="UNKNOWN"` khi không thể suy ra pattern và không rơi vào các trường hợp trên.

**Fallback không có nghĩa URL thực là UNKNOWN.** Chỉ là instrumentation không biết một **route template có cardinality thấp** cho request đó.

### 5.1. Một matched route có thể trả HTTP 404

Hai tình huống khác nhau:

~~~text
GET /api/users/404      -> handler @GetMapping("/api/users/{userId}") khớp,
                           controller trả 404 vì không tìm thấy dữ liệu.

GET /not-a-real-route   -> không có handler ứng dụng khớp đường dẫn.
~~~

Trường hợp thứ nhất vẫn có route template và metric có thể gắn `uri="/api/users/{userId}"`, `status="404"`. Trường hợp thứ hai thường gắn `uri="NOT_FOUND"`. Không suy ra cứ status 404 là nhãn URI sẽ bằng NOT_FOUND.

### 5.2. Spring Security 401 trước MVC mapping

Trong Spring Boot 4/Spring Security 7, một request có thể bị Security filter từ chối **trước khi DispatcherServlet xác định route pattern**. Khi đó observation của request 401 có thể dùng `uri="UNKNOWN"`. Đây là hành vi có chủ đích để **không thực hiện matching sớm chỉ cho metrics** và tránh tăng chi phí/hệ quả bảo mật.

Do đó, khi phân tích 401:

- Không vội kết luận controller mapping thiếu hoặc Spring instrumentation bị hỏng.
- Không sửa bằng cách đưa `request.getRequestURI()` vào low-cardinality `uri`; thao tác đó tạo nổ label theo ID.
- Có thể quan sát 401 theo status/outcome/method, security-specific metrics hoặc logs/traces đã bảo vệ.
- Nếu cần chi tiết theo route, đánh giá kiến trúc instrumentation và cách xác định route an toàn **trước** bảo mật, không suy diễn pattern từ raw path tùy tiện.

Trong các triển khai khác, proxy/filters, exceptions và status có thể thay đổi fallback behavior. Hãy kiểm dữ liệu thực của version/dependencies đang dùng.

### 5.3. Tránh gán “lỗi 404” theo path raw

Một attacker có thể gửi hàng triệu paths ngẫu nhiên như:

~~~text
/.env-0001
/.env-0002
/login/any-random-token
/api/users/never-existing-uuid
~~~

Nếu server metrics đặt `uri` bằng raw path trên 404, kẻ tấn công có thể khiến monitoring backend tạo vô số series dù **route chẳng tồn tại**. Spring default dùng `NOT_FOUND`/`UNKNOWN` theo trường hợp để tránh điều đó. Với security alert, lưu thông tin request ở access log/traces phù hợp, nhưng có rate limits, redaction và controls.

## 6. Dự án thực hành Spring Boot 4.1.2 + Actuator + Prometheus

Mục tiêu: chạy một app MVC ở localhost, tạo nhiều HTTP requests với các ID khác nhau, sau đó nhìn `http.server.requests` và exporter Prometheus để xác minh **một nhãn uri template**. Có thêm một endpoint gọi outbound `RestClient` bằng URI template để kiểm client instrumentation.

**Yêu cầu:** JDK 17+, Maven và cURL. Trên Windows PowerShell có thể dùng `curl.exe` thay vì alias `curl`. Không cần database hoặc dịch vụ ngoài.

### 6.1. Cấu trúc

~~~text
uri-cardinality-demo/
  pom.xml
  src/main/java/com/example/urimetrics/
    UriCardinalityApplication.java
    UserController.java
    LocalClientController.java
  src/main/resources/
    application.properties
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>uri-cardinality-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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

Các artifact được Spring Boot quản lý version; không cần tự pin version của Micrometer registry. `spring-boot-starter-webmvc` là starter MVC ở Boot 4.x; `spring-boot-starter-restclient` cung cấp tích hợp outbound blocking HTTP client; `spring-boot-starter-actuator` tạo metrics endpoints; `micrometer-registry-prometheus` hỗ trợ định dạng scrape Prometheus.

### 6.3. UriCardinalityApplication.java

~~~java
package com.example.urimetrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UriCardinalityApplication {
    public static void main(String[] args) {
        SpringApplication.run(UriCardinalityApplication.class, args);
    }
}
~~~

### 6.4. UserController.java

~~~java
package com.example.urimetrics;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class UserController {

    @GetMapping("/api/users/{userId}")
    public String user(@PathVariable String userId) {
        if (userId.startsWith("missing")) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "User not found");
        }
        return "user=" + userId;
    }

    @GetMapping("/api/orders/{orderId}")
    public String order(@PathVariable String orderId) {
        return "order=" + orderId;
    }

    @GetMapping("/api/search")
    public String search(@RequestParam(defaultValue = "") String q) {
        return "queryLength=" + q.length();
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
~~~

**Tại sao mẫu này hữu ích?**

- Gọi `/api/users/1`, `/api/users/2`, `/api/users/1000` đều match `/api/users/{userId}`.
- Gọi `/api/orders/100` và `/api/orders/200` match `/api/orders/{orderId}`.
- `/api/search?q=...` luôn thuộc route `/api/search`; query string không phải nhãn URI mặc định.
- `/api/users/missing-5` đi vào **handler đã match**, rồi trả HTTP 404; nó khác một URL hoàn toàn không có handler.
- Trả một chuỗi text đơn giản để test không phụ thuộc JSON mapping hoặc database.
- App demo không dùng user ID từ URL làm Micrometer tag mới.

### 6.5. LocalClientController.java

~~~java
package com.example.urimetrics;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class LocalClientController {

    private final RestClient client;

    public LocalClientController(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    @GetMapping("/api/demo-client/{userId}")
    public String callLocalUser(@PathVariable String userId) {
        return client.get()
                // Giữ mẫu URI ổn định và truyền ID riêng.
                .uri("/api/users/{userId}", userId)
                .retrieve()
                .body(String.class);
    }
}
~~~

Đây là **lab** gọi lại chính ứng dụng qua HTTP localhost để tạo `http.client.requests`; không nên dùng self-HTTP call tùy tiện trong business code production. `RestClient.Builder` được **Spring Boot auto-config** và inject vào constructor giúp có ObservationRegistry cho HTTP client.

Cấu hình ở đây giả định server chạy port 8080 như `application.properties`. Nếu đổi port, sửa cả baseUrl; đây không phải ví dụ service discovery.

**Đối chiếu lỗi thường gặp:**

~~~java
// KHÔNG nên xây path động bằng cách thay ID vào template string:
client.get().uri("/api/users/" + userId).retrieve().body(String.class);

// NÊN: URI template không đổi, biến truyền riêng:
client.get().uri("/api/users/{userId}", userId)
        .retrieve().body(String.class);
~~~

Mã trên là **fragment trong một method có client/userId đã khai báo**, không phải file Java độc lập. Lý do: Spring client observation có khả năng giữ URI template được truyền vào request. Khi truyền chuỗi path đã mở rộng, instrumented client có thể coi chính chuỗi ấy là template và tạo nhiều giá trị `uri` khác nhau. Với overload nhận `java.net.URI` dựng sẵn, một số clients có thể dùng `uri="none"` nếu không có template metadata, tùy implementation: **không** suy ra raw path sẽ được normalize tự động. Giữ URI template ngay khi xây request.

### 6.6. application.properties

~~~properties
# Chạy cục bộ để không mở /actuator ra mạng.
server.address=127.0.0.1
server.port=8080

# Chỉ mở các endpoint cần quan sát trong lab.
management.endpoints.web.exposure.include=health,metrics,prometheus

# Hàng rào an toàn cho số giá trị uri label của HTTP meters.
management.metrics.web.server.max-uri-tags=40
management.metrics.web.client.max-uri-tags=40

# Static tag ít giá trị, hữu ích để phân biệt dịch vụ.
management.metrics.tags.application=uri-cardinality-demo
~~~

**Lưu ý:**

- `server.address=127.0.0.1` giới hạn listener về loopback theo cấu hình lab; production phải dùng network/IAM/firewall policy phù hợp và bảo vệ management endpoints.
- Property `management.metrics.web.server.max-uri-tags` và `management.metrics.web.client.max-uri-tags` có trong các thuộc tính Boot 4.1; ví dụ 40 thấp để minh họa **guard**, không phải ngưỡng chuẩn cho mọi hệ thống.
- Guard giới hạn số **unique URI tag values** được đưa vào meters tương ứng; khi chạm trần, các giá trị mới có thể bị **từ chối**. Nó **không** sửa nhãn đã sai và không tự chọn một template chính xác. Trên hệ thống có nhiều routes hợp lệ, ngưỡng quá thấp sẽ làm mất observability cho routes mới.
- Bảo vệ `/actuator/metrics` và `/actuator/prometheus` bằng network/access control ở production. Không bật toàn bộ `/actuator/**` trên internet.
- `/actuator/metrics` là endpoint **chẩn đoán**, không phải công cụ scrape Prometheus chính; `/actuator/prometheus` xuất định dạng thích hợp để Prometheus scrape.

### 6.7. Chạy Maven

Trong thư mục `uri-cardinality-demo`:

~~~bash
mvn spring-boot:run
~~~

App sẽ mở port 8080 tại 127.0.0.1. Từ terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/users/1
curl -i http://127.0.0.1:8080/api/users/2
curl -i http://127.0.0.1:8080/api/orders/99
curl -i "http://127.0.0.1:8080/api/search?q=java"
~~~

Expected body của GET `/api/ping` là:

~~~text
pong
~~~

Expected bodies của GET `/api/users/1` và `/api/users/2` lần lượt là:

~~~text
user=1
user=2
~~~

Headers, timeouts và formatting của `curl -i` có thể khác tùy server; các chuỗi trên là **response body** do controller tạo, không phải toàn bộ stdout.

### 6.8. Tạo nhiều URL raw nhưng ít URI label values

Bash/POSIX:

~~~bash
for i in $(seq 1 100); do
  curl -fsS -o /dev/null \
    "http://127.0.0.1:8080/api/users/$i"
done
~~~

Lệnh gửi 100 requests, nhưng chúng đều match **cùng** `@GetMapping("/api/users/{userId}")`. Mục tiêu là URI label trong HTTP server metrics giữ giá trị `/api/users/{userId}` thay vì 100 IDs khác nhau. Số request count tăng; số distinct URI label values cho route này vẫn là **một**.

Trên Windows PowerShell:

~~~powershell
1..100 | ForEach-Object {
    curl.exe -fsS -o NUL "http://127.0.0.1:8080/api/users/$_"
}
~~~

PowerShell không dùng `$(seq 1 100)` như Bash; hai lệnh là lựa chọn theo hệ điều hành. `curl.exe` chỉ để gửi requests, không tạo metrics trực tiếp.

### 6.9. Đọc Actuator metrics

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Endpoint đầu trả danh sách meter names; endpoint sau trả measurements và `availableTags` của meter `http.server.requests`. Trong đó có thể thấy URI values:

~~~json
{
  "name": "http.server.requests",
  "availableTags": [
    {
      "tag": "uri",
      "values": [
        "/api/users/{userId}",
        "/api/orders/{orderId}",
        "/api/search",
        "/api/ping"
      ]
    }
  ]
}
~~~

**Đây là JSON rút gọn để minh họa**: số lượng/order của `availableTags` và các tags khác thay đổi tùy request thực tế, Actuator endpoints, framework/proxy và version. Không khẳng định toàn bộ response chính xác giống ví dụ. Hãy tìm `availableTags` có `tag="uri"` và kiểm không xuất hiện `/api/users/1` hoặc `/api/users/2`.

Drill-down một route có dấu ngoặc nhọn dùng query parameter URL-encoded:

~~~bash
curl -sG \
  --data-urlencode 'tag=uri:/api/users/{userId}' \
  http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Với tag filter này, `COUNT` (nếu có) phản ánh tổng requests matched route, không tạo một meter per ID. Nếu app chưa có request nào vào route đó, meter có thể chưa được tạo, vì đa số metrics được đăng ký khi có traffic.

### 6.10. Xuất Prometheus

~~~bash
curl -s http://127.0.0.1:8080/actuator/prometheus
~~~

Bạn có thể tìm các dòng như:

~~~text
http_server_requests_seconds_count{method="GET",status="200",uri="/api/users/{userId}",...} 102
~~~

Đây là **dòng đại diện**, dấu `...` không phải syntax output chính xác của Prometheus exposition; nhãn thực còn có `application`, `error`/`outcome`, và thứ tự nhãn tùy exporter. Số `102` chỉ minh họa tình huống đã gửi 100+ requests, không phải kết quả bắt buộc khi chạy toàn bộ các bước. Đừng dùng biểu thức wildcard trong nhãn như một output literal để kiểm thử.

Trong Prometheus, metric name thường được chuyển thành `http_server_requests_seconds_count` và có thêm `_sum` (và `_bucket` nếu bật histogram thích hợp). Kiểm tên xuất thật ở `/actuator/prometheus`: conventions và loại timer có thể khác khi bạn đổi backend hoặc measurement name.

### 6.11. HTTP client URI template trong metrics

Gọi vài ID:

~~~bash
curl -i http://127.0.0.1:8080/api/demo-client/10
curl -i http://127.0.0.1:8080/api/demo-client/20
curl -i http://127.0.0.1:8080/api/demo-client/30
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
~~~

`RestClient` gọi URL thực bằng ID, nhưng code truyền template `/api/users/{userId}`. Client observation low-cardinality `uri` nên đại diện bằng template, với `client.name` đại diện host. Đồng thời, HTTP server metrics có hai route patterns khác nhau: `/api/demo-client/{userId}` ở inbound và `/api/users/{userId}` ở internal request.

**Đừng nhầm:** có hai HTTP requests được xử lý mỗi lần gọi `/api/demo-client/{userId}` (request ban đầu và request self-call). Đây là demo để thấy cùng lúc server/client instrumentation, không phải một ứng dụng microservice production.

### 6.12. 404 với matched route và unmatched path

~~~bash
curl -i http://127.0.0.1:8080/api/users/missing-7
curl -i http://127.0.0.1:8080/not-a-real-path-12345
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Request đầu khớp controller pattern rồi throw `ResponseStatusException(HttpStatus.NOT_FOUND)`; metrics có thể ghi `uri="/api/users/{userId}"`, `status="404"`. Request thứ hai không có mapping nên thường có fallback `uri="NOT_FOUND"`. Nếu có proxy, error handler hoặc servlet filter đặc biệt, kiểm thực tế thay vì cố định kết quả.

Nếu một phiên bản app khác dùng Security filter từ chối trước khi route matched, bạn có thể thấy `UNKNOWN` như mục 5.2. **Không sửa bằng raw request path**.

## 7. Hàng rào max-uri-tags trong Spring Boot 4

### 7.1. Dùng property

Ví dụ:

~~~properties
management.metrics.web.server.max-uri-tags=100
management.metrics.web.client.max-uri-tags=100
~~~

Theo Spring Boot 4, đây là số lượng unique `uri` tag values cho meter tương ứng. Khi vượt trần, metrics mang **giá trị tag mới** sẽ bị từ chối đăng ký qua filter. Đây là khả năng bảo vệ chống nổ metric IDs; nó không biến 1.000 raw paths thành một route template và không tự reclaim mọi series đã tồn tại.

Nếu app có hơn 100 URI patterns hợp lệ, trần 100 có thể vô tình loại metrics của những endpoints mới. Chọn ngưỡng dựa trên số route thật + growth buffer + fallback values, kiểm ứng dụng/số series và có alert khi guard kích hoạt. **Không đơn giản nâng thành một triệu** để không thấy cảnh báo.

### 7.2. Dùng MeterFilter khi muốn chính sách riêng

Micrometer cho phép các `MeterFilter` beans. Spring Boot 4 cung cấp `MaximumAllowableTagsMeterFilter` để cap tag values của meter prefix và ghi cảnh báo khi vượt giới hạn.

Ví dụ class tùy chọn **thay cho** property guard ở demo chính:

~~~java
package com.example.urimetrics;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.boot.micrometer.metrics.MaximumAllowableTagsMeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CardinalityGuardConfiguration {

    @Bean
    MeterFilter serverUriCardinalityGuard() {
        return new MaximumAllowableTagsMeterFilter(
                "http.server.requests", "uri", 80,
                "Check raw URL usage in low-cardinality URI tags");
    }
}
~~~

Đây là class **có thể thêm vào project** nếu bạn bỏ guard property trùng mục tiêu hoặc chủ động phối hợp chúng. Constructor và package ở ví dụ dùng API Spring Boot 4.x, khác một số class/package trong Boot 3.x.

**Lưu ý:** Filter bảo vệ phần đăng ký meter, không phải URL router. Một khi series đã bị chặn, dashboard của endpoint mới có thể mất dữ liệu. Cần sửa producer/convention gây label explosion và có test hồi quy; bản thân filter không đảm bảo observability đầy đủ.

### 7.3. Không lạm dụng cap để sửa lỗi dữ liệu

Một anti-pattern:

~~~text
Problem: raw URI làm 100.000 label values.
Patch: max-uri-tags = 10.
Kết quả: không còn 100.000 series, nhưng metrics từ các routes tới sau
có thể bị drop khi 10 values đầu tiên đã chiếm budget.
~~~

Corrective action:

1. Tìm nguồn nhãn raw URL/ID.
2. Đổi code/convention/client construction sang URI template.
3. Đặt allowlist/normalization dựa trên **known route metadata**, không regex tùy tiện.
4. Sau đó mới đặt guard theo ngân sách hợp lệ.
5. Test 100–1.000 IDs khác nhau mà nhãn `uri` chỉ có một route.
6. Quan sát denied meters/guard warnings và series count sau deploy.

## 8. Không đưa raw URL vào custom metrics

### 8.1. Anti-pattern trong Micrometer custom Timer

~~~java
// SAI: mỗi user ID tạo một tag mới.
Timer.builder("myapp.user.lookup")
        .tag("uri", "/api/users/" + userId)
        .register(meterRegistry)
        .record(() -> lookupUser(userId));
~~~

Đây là **fragment** (có `userId`, `lookupUser` và `meterRegistry` do app cung cấp), không phải Java file độc lập. Nếu hệ thống có 1 triệu users, timer series có thể tăng theo số IDs dù cùng một loại thao tác.

Cách đúng trong trường hợp này:

~~~java
// ĐÚNG: dùng tên route cố định.
Timer.builder("myapp.user.lookup")
        .tag("uri", "/api/users/{userId}")
        .register(meterRegistry)
        .record(() -> lookupUser(userId));
~~~

Tốt hơn nữa, nếu đây là HTTP request metric thông thường thì **không cần tạo một custom Timer trùng** với `http.server.requests`. Chỉ thêm business metric khi nó đo một thao tác khác biệt và có ý nghĩa.

### 8.2. Không gắn labels nhạy cảm

Tránh:

~~~text
user_id      = "54839293"
email        = "someone@example.test"
session_id   = "abc..."
order_id     = "order-789123"
path         = "/payments/credit-card-number"
access_token = "eyJ..."
query        = "password=..."
~~~

Dù quy mô nhỏ, các giá trị này có thể lộ trong dashboard hoặc metrics exports. Nếu cần điều tra một request cụ thể, dùng **trace ID/log correlation** với kiểm soát truy cập, retention, redaction và privacy policy; không lạm dụng metrics labels để tra từng user.

### 8.3. Custom convention: dùng dữ liệu có bounds

Trong Spring MVC, muốn đổi low-cardinality KeyValues, có thể cung cấp một bean mở rộng `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` hoặc implement `ServerRequestObservationConvention`. Với WebFlux, package reactive tương ứng khác.

Một convention an toàn nên:

- Giữ `uri` từ matched route pattern nếu có.
- Với endpoint không match, sử dụng fallback bounded như `NOT_FOUND`/`UNKNOWN`, không lấy raw path.
- Nếu muốn thêm `feature`, dùng tập hữu hạn `catalog|checkout|auth|other` từ business routing đã được kiểm soát.
- Không thêm `userId`, email, request header, query, raw URL.
- Có test kiểm tag values khi request IDs tăng.
- Chú ý việc custom convention **thay** defaults có thể làm mất tags quan trọng nếu không kế thừa/áp thích hợp.

Không đề xuất “tự parse regex request.getRequestURI()” thành template nếu Spring đã có matched route pattern. Regex dễ hỏng với UUID, encoded slash, API version, nested paths, trailing slash và paths không tồn tại.

### 8.4. Route cardinality có thể tăng dù gắn đúng template

Vấn đề không chỉ là IDs. Nếu ứng dụng tự đăng ký hàng nghìn routes **động**, mỗi route có một string literal riêng, route template thật cũng có thể cardinality cao. Ví dụ:

~~~text
/tenant-one/reports
/tenant-two/reports
/tenant-three/reports
...
~~~

Nếu mỗi tenant là một handler mapping path tĩnh riêng, nhãn pattern có thể khác từng tenant. Thiết kế API dùng template `/tenants/{tenantId}/reports` hoặc route group ổn định giúp cardinality thấp hơn, miễn là authorization và routing vẫn đúng. Không thay public API chỉ vì metrics nếu chưa đánh giá compatibility.

## 9. HTTP client instrumentation: RestClient, RestTemplate, WebClient

Spring Framework ghi nhận outbound HTTP observations bằng `http.client.requests` với các low-cardinality keys như `method`, `uri`, `client.name`, `status`, `outcome`, `error`. `uri` dựa trên **URI template mà client code cung cấp**, nếu có; nếu không có template, có thể dùng `none`.

### 9.1. RestClient tốt và không tốt

~~~java
// Fragment, yêu cầu RestClient client và String userId đã có.
client.get()
        .uri("/users/{id}", userId)
        .retrieve()
        .body(String.class);             // Có URI template

client.get()
        .uri("/users/" + userId)
        .retrieve()
        .body(String.class);             // Chuỗi đã expand, dễ nổ uri tags
~~~

Dù cả hai tạo cùng HTTP path trên wire, instrumentation có thể ghi tag khác nhau. Đúng là “**template phải tồn tại ở lúc dựng request**”, không chỉ cố sửa raw path ở exporter.

### 9.2. RestTemplate

~~~java
// Fragment, RestTemplate đã được cấu hình ObservationRegistry.
restTemplate.getForObject(
        "https://service.example.test/users/{id}",
        String.class,
        userId);
~~~

Khi truyền `java.net.URI` đã build sẵn, template metadata có thể bị mất và tag `uri` có giá trị `none` theo semantics của client. `none` có cardinality thấp nhưng **mất độ phân giải endpoint**, không phải phương án tối ưu nếu bạn có thể truyền template một cách tự nhiên.

### 9.3. WebClient

~~~java
// Fragment WebClient, return Mono<String> trong reactive pipeline.
Mono<String> result = webClient.get()
        .uri("/users/{id}", userId)
        .retrieve()
        .bodyToMono(String.class);
~~~

Spring Boot tự cấu hình `WebClient.Builder` có ObservationRegistry khi starter/dependencies phù hợp. Tránh tự tạo client/connector/observation registry thiếu cấu hình khiến `http.client.requests` không xuất hiện rồi kết luận metrics instrumentation lỗi.

### 9.4. Client name có thể trở thành high cardinality

Nếu HTTP client gọi một số hostname ổn định, `client.name` là một tag hữu ích. Nhưng nếu app là HTTP fetcher theo arbitrary user-provided URLs, nó có thể tạo vô hạn hostnames:

~~~text
client.name = random1.example
client.name = random2.example
client.name = random3.example
...
~~~

Đặt guard/allowlist/egress policy, bảo vệ SSRF và metric budget. Giới hạn `uri` thôi không đủ khi các tags khác vẫn có tập giá trị không giới hạn. Không xóa client.name ngay lập tức nếu nó phục vụ troubleshooting; chọn nhóm host ổn định hoặc service-name trong danh mục có quản trị.

## 10. Prometheus: đọc metrics và đếm series

Micrometer metric `http.server.requests` thường được export thành những Prometheus time series có tên như `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`; tùy cấu hình histograms còn có `_bucket`. Tên ở Actuator metrics endpoint **giữ tên logic**, còn exporter chuẩn hóa naming convention.

### 10.1. Lưu lượng theo route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Query này giúp xem requests/second theo các route template. Nếu nhãn `uri` là raw ID, kết quả có thể là hàng chục nghìn series; nếu là template, một dòng đại diện cho một endpoint.

### 10.2. Tỷ lệ 5xx theo route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
clamp_min(
  sum by (uri) (rate(http_server_requests_seconds_count[5m])),
  1e-9
)
~~~

Kết quả là **tỷ lệ thập phân** (ví dụ 0.02 ≈ 2%) theo route trong cửa sổ 5 phút. Với route không có 5xx, vector tính từ numerator có thể không chứa route đó; dashboard cần handle missing series, không tự giả định tất cả values đều bằng zero. Không gộp route có `UNKNOWN` với một endpoint cụ thể rồi kết luận lỗi của nó.

### 10.3. P95/P99 khi có histogram

Nếu bạn bật timer histogram phù hợp:

~~~properties
# Tùy chọn production sau khi cân nhắc chi phí series.
management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

PromQL minh họa:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Không bật histogram trên mọi metric/tag combination mà chưa tính series budget. Histogram làm tăng đáng kể lượng bucket series. Nếu metric name/exporter hoặc native histogram backend khác, sửa query theo dữ liệu thực. Đo latency theo một template giúp aggregate có ý nghĩa; đo p95 riêng cho mỗi user ID thường quá đắt và ít mẫu.

### 10.4. Đếm số giá trị URI có mặt

~~~promql
count(
  count by (uri) (http_server_requests_seconds_count)
)
~~~

Đây là số **URI label values khác nhau đang hiện diện** trong series vector tại thời điểm query, không phải số URI patterns được khai trong source, không bao gồm meter đã bị filter từ chối hay series chưa phát sinh traffic. Kiểm cả total active series per job:

~~~promql
count(http_server_requests_seconds_count)
~~~

Các query cần chọn job/namespace/instance filters khi chạy trong Prometheus nhiều dịch vụ để không đếm trộn mọi ứng dụng.

### 10.5. Scrape volume và retention

Một sự bùng nổ label có thể khiến cùng một app tăng:

- Number of active time series.
- Scrape response bytes/duration và scrape timeout.
- Rate of new series/churn.
- Memory head block ở Prometheus, remote write queue/latency.
- Chunk storage và chi phí giữ dữ liệu.
- Dashboard query latency.

Giới hạn ở backend không thay đổi vấn đề tại **source** nếu JVM vẫn tạo quá nhiều meters. Giảm cardinality tại instrumentation là ưu tiên số một.

## 11. Khi nào không nên biến metric thành trace hoặc log?

Ba lớp observability phục vụ các câu hỏi khác nhau:

| Tầng | Đối tượng | Có chứa URI cụ thể không? |
| --- | --- | --- |
| **Metrics** | Tổng lượng, latency, error ratio theo route/method/status | **Không nên**; dùng route template |
| **Traces** | Hành trình một request giữa services, span attributes | Có thể chứa chi tiết cao, **phải redaction và sampling** |
| **Logs** | Sự kiện chẩn đoán/hành vi cụ thể | Có thể có path, ID, traceId nhưng cần kiểm PII/token/retention |

Nếu muốn biết “User X nhận 404 lúc mấy giờ”, tag metrics theo user X không phải cách phù hợp. Dùng correlation ID, request logs/traces được phân quyền, dữ liệu nhạy cảm được mask. Nếu cần top ten tenants có lỗi, sử dụng dữ liệu backend nghiệp vụ hoặc pre-aggregated bounded groups, không để tất cả tenant IDs tự trở thành metrics labels.

### 11.1. Observation low vs high cardinality

Không nên viết:

~~~java
// Fragment minh họa SAI: request ID là low-cardinality meter value.
observation.lowCardinalityKeyValue("user.id", userId);
~~~

Nếu cần gắn dấu nhận dạng vào trace, phải đánh giá chính sách quyền riêng tư và dùng **high-cardinality attributes** được trace processor bảo vệ; không phải tự ý ghi mọi PII vào tracing. Code đúng phụ thuộc observation lifecycle, span exporter và data privacy controls.

## 12. HTTP 404/401, static resources, redirect và gateway

### 12.1. HTTP response trước matching

CORS preflight, Spring Security, Servlet filters, gateway rejection hoặc response lỗi sớm có thể kết thúc request trước MVC/WebFlux handler mapping. Khi không biết route template, `uri` có thể là `UNKNOWN` hoặc fallback khác. Đó là lý do không được ép request URI raw vào metrics chỉ để tránh UNKNOWN.

### 12.2. Static files

Static resources có thể được phục vụ từ một route pattern rộng như `/**` hoặc resource handler mapping. Tùy framework/version, nhãn URI của các static files có thể là một template rộng hoặc fallback. Dùng kiểm chứng thực tế; không ghi đè bằng path chứa fingerprint/hash của mỗi asset.

Asset fingerprint như:

~~~text
/assets/app.abc123.js
/assets/app.def456.js
~~~

nếu đưa nguyên vẹn vào tag có thể tạo nhiều values sau mỗi deploy. Có thể đánh dấu tài nguyên theo nhóm `static` hoặc bỏ metric per-file khi không phục vụ SLO.

### 12.3. API gateway và ingress

Một request có thể qua:

~~~text
Browser -> CDN/Ingress -> API Gateway -> Spring Boot Controller
~~~

Các layer có metric labels riêng. Ingress `path` tag có thể dùng configured route pattern, không tự biết `@GetMapping` trong JVM. Nếu ingress tạo label từ raw request path, cardinality explosion vẫn xảy ra dù Spring Boot metrics đang đúng.

Kiểm riêng mỗi instrumentation layer: Prometheus scrape jobs, service mesh, Envoy/Nginx exporters, API gateway labels. Một lỗi ở layer khác không được giải quyết chỉ bằng property `management.metrics.web.server.max-uri-tags` của Boot.

### 12.4. Path encoding và request normalization

Rủi ro khi tự parse path:

- Percent-encoded slash và Unicode normalization.
- Trailing slash/letter case.
- Matrix variables và path parameters.
- Spring MVC servlet path/context path.
- Rewrites từ proxy, version prefix, internal forward.
- Spring Security 401/403 trước controller.
- Requests chưa có matching handler.

Dùng **matching metadata từ framework**, không tự khai “nguyên tắc regex thay mọi số/UUID” để tạo metrics tags. Nếu cần policy riêng cho gateway, tạo cấu hình routes/operation names có quản lý và test all edge cases.

## 13. Thiết kế nhãn có ngân sách hữu hạn

Không chỉ `uri`: tất cả labels đều có nguy cơ nhân cardinality.

### 13.1. Nhãn nên có trong HTTP server metrics

Ví dụ:

- `method` (GET, POST, ...).
- `uri` (route pattern/operation name có quản lý).
- `status` hoặc `outcome` (giới hạn giá trị).
- `application`, `region`, `environment` (tập nhỏ, có kiểm soát).
- `error` dạng class name nếu cardinality hữu hạn và không chứa thông điệp tùy ý.

Cẩn trọng với `exception` tags: class name thường ít giá trị nhưng plugin/custom errors có thể có nhiều types. Không đưa stacktrace/error message hay SQL text vào tag.

### 13.2. Nhãn cần tránh

- `userId`, orderId, sessionId, traceId, requestId.
- Dynamic hostname từ URL do user nhập.
- Query text, email, phone number, IP của mọi caller.
- Token, API key, cookies, headers tùy ý.
- Full exception message, full SQL query, raw request path.
- File name/fingerprint nếu asset names đổi sau mỗi deploy.
- Labels lấy từ mọi HTTP header hoặc MDC mà không whitelist.

Nếu cần group theo tenant tier:

~~~text
tenant_tier = "free" | "standard" | "enterprise" | "unknown"
~~~

thì nhóm này có cardinality thấp hơn hàng trăm nghìn tenant IDs. Nhưng vẫn phải xem xét tính đúng đắn, quyền truy cập, privacy và liệu dashboard cần nhãn mới không.

### 13.3. Cardinality budget và acceptance criteria

Ví dụ policy cho một service:

| Hạng mục | Quy ước test |
| --- | --- |
| Unique `uri` values | Xấp xỉ số route templates và fallback values; không tăng theo ID |
| Active series per service | Dưới trần do Prometheus/backend quy định |
| Request volume | Tăng 100.000 requests với nhiều IDs không tạo 100.000 route labels |
| Error labels | Không chứa URL raw, token, email |
| New deployment | Không nhân series vô hạn theo deploy hash/asset fingerprint |
| Route cap | Có metrics/log khi max-uri-tags filter deny |
| Client metrics | URI template ổn định; client.name có bounds |
| Scrape | Thời gian và payload size dưới SLO |

**Đừng chọn một budget cố định cho mọi hệ thống.** Microservice 10 routes khác gateway 1.000 routes, nhưng cả hai không nên tạo một metric series per customer. Budget phụ thuộc labels, histogram, number of instances, scrape interval và retention.

## 14. CI/QA: test cardinality thay vì chỉ test HTTP 200

### 14.1. Test bằng traffic và Actuator

Một integration test hữu ích có thể:

1. Start Spring Boot app với Actuator enabled.
2. Gửi nhiều IDs khác nhau tới cùng endpoint pattern.
3. Đọc `/actuator/metrics/http.server.requests` hoặc inspect Spring-managed MeterRegistry.
4. Assert có tag `uri="/api/users/{userId}"`.
5. Assert **không** có tag `uri="/api/users/1"`, `uri="/api/users/2"`...
6. Gửi path không tồn tại, assert fallback không chứa raw path.
7. Nếu có Spring Security, test pre-handler 401 không biến raw URL thành metric tag.
8. Với outbound clients, test RestClient/WebClient URI template.
9. Test property guard khi số templates tăng vượt cap và kiểm nó báo signal vận hành, không che lỗi.

### 14.2. Một đoạn JUnit/Micrometer kiểm tag từ registry

Trong project có Spring Boot test dependency và test framework, có thể kiểm trong context tích hợp:

~~~java
// Fragment test: cần MeterRegistry, MVC test setup và traffic đã được gửi.
// Không phải Java file độc lập.
Collection<Meter> meters = meterRegistry.find("http.server.requests").meters();

boolean hasTemplate = meters.stream()
        .anyMatch(m -> "/api/users/{userId}".equals(m.getId().getTag("uri")));

boolean hasRawPath = meters.stream()
        .anyMatch(m -> {
            String uri = m.getId().getTag("uri");
            return uri != null && uri.matches("/api/users/[0-9]+");
        });

assertTrue(hasTemplate);
assertFalse(hasRawPath);
~~~

Import cần có `io.micrometer.core.instrument.Meter`, `MeterRegistry`, `java.util.Collection` và JUnit assertions. Nên gửi request thật qua web instrumentation; chỉ unit test trực tiếp controller có thể bỏ qua ObservationFilter và tạo **false negative** về metrics.

### 14.3. Không coi `uri=UNKNOWN` là bug tự động

Nếu một auth filter trả 401 trước MVC routing, expected tag có thể là `UNKNOWN`. Test cần hiểu lifecycle và **không** yêu cầu route pattern chưa hề được tìm ra. Mục tiêu bảo vệ là **không tạo high-cardinality label**, không bắt mọi request phải có template chính xác.

### 14.4. Khi cap đã chặn meter mới

Nếu metric không xuất hiện sau một đợt traffic lớn, kiểm:

- Cảnh báo max-uri-tags/meter filter deny.
- Custom conventions, dynamic routing, raw URI tags.
- Thay đổi method/status labels và metric names.
- Registry và Prometheus scrape endpoint thực tế.
- Actuator exposure/security/network.
- Framework version và observation instrumentation có còn enabled không.

Không vội tăng cap nếu chưa xác minh vấn đề gốc.

## 15. Khắc phục sự cố: tìm nguồn nổ cardinality

### Triệu chứng

- Prometheus series count tăng cùng số users/requests chứ không cùng số routes.
- `availableTags.uri.values` liệt kê nhiều `/api/users/123`, `/api/users/124`.
- Scrapes quá lớn hoặc remote write lag.
- Outbound `http.client.requests` có nhiều dynamic hostnames.
- Deploy feature mới làm JVM heap và metrics memory tăng.
- Logs có cảnh báo meter tag limit.
- Dữ liệu latency của route mới biến mất vì cap đã bị chiếm.

### Trình tự xử lý

1. Xác định **metric name** và label có nhiều values nhất từ Prometheus/Actuator.
2. Phân biệt raw path đang được xuất từ Spring Boot hay một proxy/ingress exporter.
3. Kiểm custom `ObservationConvention`, `MeterFilter` và code dùng `Timer.builder(...).tag(...)`.
4. Với HTTP client, tìm nơi dùng `.uri("/path/" + id)` hoặc `URI.create(...)` thay URI templates.
5. Với HTTP server, kiểm handler mapping, dynamic routes, 404/401 trước handler và custom instrumentation có dùng raw `requestURI` không.
6. Sửa code dùng route metadata/constant template trước khi chỉnh cap.
7. Kiểm privacy: nhãn đã từng chứa PII/token có thể nằm trong TSDB/remote storage; thực hiện data retention/incident response theo chính sách.
8. Chạy lại load test với nhiều IDs và đếm URI values/series count.
9. Giữ guard hợp lý và alert khi chạm cap, đồng thời kiểm mất metrics.
10. Sau deploy, theo dõi JVM MeterRegistry, exporter series count và backend scrape performance.

### Những lỗi dễ gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `uri="/users/1"`, `uri="/users/2"` | Raw path tag hoặc client string URI dynamic | Dùng route template |
| `uri=none` ở client | Client không có URI template metadata | Truyền template có placeholders |
| `uri=UNKNOWN` khi 401 | Security chặn trước route matching | Chấp nhận fallback, dùng security metrics/logs |
| `uri=NOT_FOUND` cho random 404 | Không có matching route | Bình thường, không đổi thành raw path |
| Mất metrics sau URI cap | Meter filter từ chối new values | Sửa cardinality nguồn, sizing cap |
| Grafana latency per-user không hiển thị | Đúng vì metrics theo route, không user | Dùng traces/logs có phân quyền |
| Sau deploy tăng series | Nhiều templates thực hoặc asset hashes/client hosts | Inventory route và exporter tags |
| Custom convention thiếu status | Thay toàn bộ key set không giữ defaults | Extend default convention đúng |
| Prometheus query không tìm meter | Chưa scrape, naming đổi hoặc chưa có traffic | Kiểm `/actuator/prometheus` và registry |
| Cùng route nhưng nhiều status series | Method/status là label khác | Đây là phân tách có mục đích |
| CPU cao khi bật histograms | Mỗi tag combination sinh buckets | Giới hạn routes/tags/buckets |
| Raw URL xuất qua trace | High-cardinality attributes có thể vẫn chứa chi tiết | Scrub/sampling/access controls |

## 16. Checklist production

- [ ] `http.server.requests` dùng route template hoặc fallback bounded, không raw ID/URL.
- [ ] `http.client.requests` dùng URI template từ RestClient/WebClient/RestTemplate khi có thể.
- [ ] Không gắn userId, tenantId tự do, sessionId, email, token, query, IP, traceId vào low-cardinality meter labels.
- [ ] Không dùng `http.url` high-cardinality trace key làm metric label.
- [ ] Có chính sách xử lý 404/401 trước handler, không ép raw path vào tag để loại UNKNOWN.
- [ ] Dùng defaults Spring MVC/WebFlux hoặc custom observation convention có test.
- [ ] Có guard max-uri-tags theo số routes thật, alert khi meter bị deny.
- [ ] Có ngân sách riêng cho histogram buckets, labels khác và số instances.
- [ ] Actuator metrics/prometheus được bảo vệ, không public toàn bộ management endpoints.
- [ ] Theo dõi active series, new series churn, scrape duration/bytes và remote-write backlog.
- [ ] Có tests gửi hàng trăm ID khác nhau nhưng số URI tag values không tăng tuyến tính.
- [ ] Có checks cho dynamic routes và client.name host cardinality.
- [ ] Trace/log URL có masking/retention/authorization phù hợp.
- [ ] Dashboard dùng mẫu URI ổn định, không tạo PromQL theo từng user.
- [ ] Khi có sự cố, sửa instrumentation nguồn và không chỉ nâng URI cap vô hạn.

## 17. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Tại sao `/api/users/1` và `/api/users/2` nên có cùng nhãn `uri="/api/users/{userId}"`?

**Đáp án:** Vì đó là cùng một endpoint route pattern. Tạo tag theo ID sẽ tăng số time series theo số người dùng thay vì theo số endpoints, gây chi phí và rủi ro PII.

**Câu 2.** Có thể dùng `request.getRequestURI()` làm custom low-cardinality key `uri` để tránh UNKNOWN không?

**Đáp án:** Không nên. Raw request URI có thể tăng vô hạn với IDs, query/URL variations và 404 scanner paths; cần route pattern hoặc bounded fallback.

**Câu 3.** `http.url` có phải nhãn metrics mặc định của HTTP server không?

**Đáp án:** Spring Observation coi nó là high-cardinality key có thể dùng cho tracing; **không** tự thêm nguyên giá trị này vào metric tags.

**Câu 4.** Vì sao Boot 4 có thể có `uri=UNKNOWN` cho HTTP 401?

**Đáp án:** Security có thể trả response trước khi Spring MVC thực hiện matching để tìm route template; không suy ra pattern từ raw path để lấp thiếu.

**Câu 5.** `management.metrics.web.server.max-uri-tags=40` có tự sửa 1.000 IDs thành một template không?

**Đáp án:** Không. Nó từ chối giá trị mới khi vượt cap; phải sửa route/client instrumentation, đồng thời bảo đảm 40 đủ cho routes hợp lệ.

**Câu 6.** Query string `?email=a@example.test` có nên là metrics label không?

**Đáp án:** Không. Nó có cardinality lớn và PII. Dùng route template và nếu cần phân loại, dùng nhóm giá trị được whitelist.

**Câu 7.** Một controller trả HTTP 404 sau khi route matched có nhất thiết được gắn `uri=NOT_FOUND` không?

**Đáp án:** Không. Khi mapping đã được biết, nó vẫn có thể gắn đúng template cùng `status=404`. NOT_FOUND thường dành cho request không có matching handler.

**Câu 8.** RestClient gọi `.uri("/users/" + id)` thì vì sao metrics có thể bị nổ tags?

**Đáp án:** Vì client observation có thể coi chuỗi URL đã expand là template. Truyền `.uri("/users/{id}", id)` để giữ mẫu.

**Câu 9.** Khi Prometheus có hàng triệu series từ URI path, chỉ nâng heap JVM có đủ không?

**Đáp án:** Không. Vấn đề tồn tại cả ở exporter, Prometheus storage/scrape, remote write và dashboard. Sửa tag tại nguồn.

**Câu 10.** Một endpoint sinh histogram 20 buckets, có nên đồng thời gắn user ID không?

**Đáp án:** Không. Buckets nhân với các tag combinations, làm series explosion tồi hơn. Tối ưu label budget và histogram config theo SLO.

## 18. Tài liệu chính thức

- [Spring Boot — Metrics and Micrometer](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — `http.server.requests`, `http.client.requests`, Actuator diagnostics, MeterFilter.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — `management.metrics.web.server.max-uri-tags` và client tương ứng.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure, access và Prometheus endpoint.
- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html).
- [Spring Boot 4.1.2 API — MaximumAllowableTagsMeterFilter](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/micrometer/metrics/MaximumAllowableTagsMeterFilter.html).
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html) — low/high cardinality, MVC/WebFlux server, RestClient/WebClient.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html) — URI template và variables.
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Security/Boot discussion — 401 uri UNKNOWN in Boot 4](https://github.com/spring-projects/spring-boot/issues/49640).
- [Micrometer — Concepts: Naming Meters and Tags](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- [Prometheus — Data Model: Metric Names and Labels](https://prometheus.io/docs/concepts/data_model/).
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/).
- [Prometheus — Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/).

**Ghi nhớ:** HTTP metrics nên trả lời “endpoint nào chậm/lỗi”, không phải “ID nào được gọi”. **Nhãn `uri` phải là route template** như `/api/users/{userId}` hoặc bounded fallback, tuyệt đối tránh raw paths/query/PII. Spring MVC và WebFlux có instrumentation mặc định làm điều này khi đã xác định handler mapping; request 401/404/redirect sớm có thể dùng UNKNOWN/NOT_FOUND/REDIRECTION. Dùng URI templates khi dựng outbound RestClient/WebClient, đặt max-uri-tags guard và kiểm tra số active series/histogram buckets. Khi nhãn nổ, sửa instrumentation **tại nguồn**, không chỉ nâng memory hay cap.