# Lưu request body khi thử lại và chi phí bộ nhớ

## 1. Vì sao retry một request có body khó hơn retry GET?

Trong kiến trúc **SPRING_CLOUD_GATEWAY**, client gọi một endpoint công khai; Spring Cloud Gateway Server WebFlux chọn route bằng predicate, chạy filter chain, có thể biến đổi path/header, tìm instance bằng service discovery và gửi HTTP request tới microservice. Khi backend trả lỗi tạm thời hoặc kết nối gặp sự cố, **Retry GatewayFilter Factory** có thể thử lại lời gọi.

Với `GET /api/products/42` không có body, thử lại thường đơn giản: Gateway có thể tạo một request mới với cùng method, path và headers. Nhưng với:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: order-7b23

{"sku":"A-42","quantity":2}
~~~

request body đi vào **reactive stream** và thường chỉ được tiêu thụ một lần. Nếu Gateway gửi hết dữ liệu của stream cho lần thử thứ nhất, lần thử thứ hai sẽ đọc dữ liệu từ đâu? Để phát lại, Gateway cần **giữ bản sao có thể đọc lại của body**, hoặc có một nguồn dữ liệu có thể phát lại một cách an toàn.

Theo tài liệu **Retry GatewayFilter Factory** của Spring Cloud Gateway Server WebFlux, khi bật retry cho HTTP method có body, Gateway **cache body**, và việc này có thể gây áp lực bộ nhớ. Body được giữ trong exchange attribute `ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR`, dưới dạng `org.springframework.core.io.buffer.DataBuffer` trong các phiên bản được tài liệu mô tả.

Đây là trọng tâm của bài **“Lưu request body khi thử lại và chi phí bộ nhớ”**, thuộc chương **Thử lại yêu cầu**. Bài liên hệ tới routing, filter chain, biến đổi request/header, khám phá dịch vụ, xác thực, rate limiting, circuit breaker, TLS và observability, nhưng tập trung vào hai câu hỏi:

1. Làm thế nào để một body đã được đọc vẫn tới backend đầy đủ trong **từng retry attempt**?
2. Chi phí bộ nhớ, độ trễ và độ an toàn nghiệp vụ của cách làm đó là gì?

> **Phạm vi:** Bài sử dụng **Spring Cloud Gateway Server WebFlux** trên Spring Boot/Spring Cloud tương thích. Gateway Server MVC có cơ chế `cacheBody` và `AdaptCachedBody` riêng; **không sao chép** cấu hình của Server MVC sang WebFlux.

## 2. Hiểu chính xác “retry” trong Gateway

Giả sử Gateway định tuyến tới `orders-service` và cấu hình:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      statuses:
        - BAD_GATEWAY
      methods:
        - GET
~~~

`retries: 2` nghĩa là tối đa **hai lần thử thêm** sau lần đầu, tức có thể có **ba attempts** cho một request client. Nó **không** có nghĩa chỉ thực hiện tổng cộng hai attempts.

~~~text
Client gửi 1 request
       |
       +--> Attempt 1 --> backend trả 502
       |
       +--> Attempt 2 --> backend trả 502
       |
       +--> Attempt 3 --> backend trả 200
       |
       +--> Client nhận response cuối 200
~~~

Chỉ những lỗi được chính sách retry cho phép (status, status series, exception, method và các giới hạn khác của version) mới kích hoạt attempt tiếp theo. Nếu backend trả 400 và policy chỉ retry 502, Gateway không nên lặp lại chỉ vì có cấu hình Retry.

### 2.1. Những tham số quan trọng

| Tham số | Vai trò | Cẩn trọng |
| --- | --- | --- |
| `retries` | Số lần thử **bổ sung** | Tổng attempts tối đa thông thường = `1 + retries` |
| `statuses` | Các HTTP status cụ thể để cân nhắc retry | Chẳng hạn `BAD_GATEWAY`, `SERVICE_UNAVAILABLE` |
| `series` | Nhóm status, ví dụ toàn bộ 5xx | Quá rộng có thể retry lỗi logic không thể tự hồi phục |
| `methods` | HTTP method được phép thử lại | Mặc định chỉ `GET` theo tài liệu; POST phải cân nhắc rất kỹ |
| `exceptions` | Các exception có thể được retry | Phân biệt lỗi kết nối trước/sau khi backend đã xử lý |
| `backoff` | Độ trễ và tăng dần giữa attempts | Phải giới hạn tổng latency; nên dùng jitter nếu phiên bản hỗ trợ |
| `jitter`, `timeout` | Tùy chọn theo các bản Gateway mới | Kiểm tra semantics theo version, không giả định chúng giới hạn toàn bộ request |

Tài liệu Gateway WebFlux 5.x nêu mặc định của Retry khi được bật: `retries=3`, `series=5XX`, `methods=GET`, exceptions gồm `IOException` và `TimeoutException`; backoff/jitter tắt, timeout riêng của filter không giới hạn nếu không cấu hình. **Không nên đưa cấu hình mặc định này lên mọi API production** mà chưa xét khả năng chịu tải.

### 2.2. Retry không bảo đảm backend chưa xử lý

Hai tình huống sau có thể tạo cùng một triệu chứng “Gateway không nhận được response”:

~~~text
A. Gateway chưa kết nối được backend
   → backend có thể chưa nhận request

B. Backend đã tạo đơn hàng nhưng kết nối đứt khi trả response
   → Gateway không biết tác dụng phụ đã hoàn thành hay chưa
~~~

Retry lần thứ hai ở tình huống B có thể **tạo hai đơn hàng**. Việc cache body giải quyết khả năng **phát lại bytes**, **không giải quyết tính idempotent của nghiệp vụ**. Đối với POST thanh toán, tạo đơn, gửi email, phát OTP hay ghi dữ liệu, cần thiết kế idempotency key, unique constraint và chính sách retry đúng với downstream.

## 3. Vì sao request body trong WebFlux không tự đọc lại được?

Spring WebFlux biểu diễn request body là `Flux<DataBuffer>` hoặc luồng reactive tương ứng. Với cơ chế streaming, dữ liệu có thể được đọc từ socket theo từng phần (chunk) thay vì được tạo sẵn thành một byte array bất biến.

~~~mermaid
flowchart LR
    C["Client<br/>POST + request body"] --> R["Reactor Netty<br/>incoming byte stream"]
    R --> B["Flux<DataBuffer><br/>đọc theo chunk"]
    B --> F["Gateway filter chain"]
    F --> N["NettyRoutingFilter"]
    N --> U["Downstream service"]
~~~

Một nguồn body đọc từ HTTP socket thường **không thể được đăng ký lại để phát nguyên dữ liệu đầu vào** sau khi đã tiêu thụ, vì socket không tự quay ngược. Spring WebFlux cũng sử dụng `DataBuffer` có thể là bộ nhớ được pool, quản lý reference count. Nếu custom filter đọc body mà không tái tạo request đúng cách, downstream có thể thấy body rỗng; nếu giữ buffer nhưng không giải phóng đúng vòng đời, có thể rò rỉ direct memory.

Khi Retry WebFlux hỗ trợ method có body, framework có thể **cache body để những lượt thử sau sử dụng lại**. Thông tin này gắn với cùng `ServerWebExchange` qua attribute:

~~~java
ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR
~~~

Theo tài liệu Retry WebFlux, đối tượng ở attribute là `DataBuffer`. Tuy nhiên, **đừng tự đọc/giữ/release attribute này trong custom code mà không hiểu chi tiết version và quản lý reference count**. API và thời điểm giải phóng buffer là trách nhiệm nhạy cảm của framework; cần kiểm thử leak nếu viết GlobalFilter xử lý body ở mức thấp.

### 3.1. Retry body cache khác gì CacheRequestBody?

| Cơ chế | Mục đích | Chú ý |
| --- | --- | --- |
| **Retry** với method có body | Bảo đảm body có thể được phát lại ở attempts phù hợp | Có thể giữ `DataBuffer` trong exchange và gây áp lực memory |
| **`CacheRequestBody` GatewayFilter Factory** | Đọc và cache body để filter khác dùng, có thể chuyển body thành một Java class | Cũng có chi phí buffer/deserialize; không phải giải pháp miễn phí |
| **`ModifyRequestBody`** | Đọc, giải mã, biến đổi và tạo body mới | Có thể tạo thêm bản sao hoặc đối tượng trung gian |
| **`ReadBody` route predicate** | Đọc body để đánh giá điều kiện route | Cần cache để xử lý downstream; không thể coi như streaming thuần |
| **`RequestSize` GatewayFilter** | Từ chối payload vượt kích thước được phép | Bảo vệ giới hạn body, không thay thế chính sách retry/idempotency |

Các cơ chế có thể tương tác trong cùng một request; **không mặc định có đúng một bản sao body trong toàn bộ pipeline**. Khi đặt `CacheRequestBody`, `ModifyRequestBody` và Retry chung một route, hãy benchmark và xác minh thứ tự filter, kích thước bộ đệm và behavior theo version. Không tự thêm `CacheRequestBody` chỉ vì Retry đã cache body; đó có thể là chi phí không cần thiết.

### 3.2. Server MVC không dùng cùng cấu hình

Tài liệu **Gateway Server MVC** nói về `cacheBody: true` cùng filter `AdaptCachedBody`. Trong Gateway **Server WebFlux**, hướng dẫn Retry mô tả cache body khi dùng retry cho method có body; mẫu WebFlux không cần sao chép `AdaptCachedBody` từ MVC. Trộn các hướng dẫn này có thể gây nhầm cấu hình hoặc không tìm thấy filter.

## 4. Chi phí bộ nhớ: số bytes giữ lại mới là vấn đề

Giả sử mỗi request POST mang body kích thước `B` bytes; tại một thời điểm có `N` request đang được Gateway xử lý và mỗi request phải giữ body để retry.

Mức bộ nhớ giữ cho **payload** có thể ước lượng sơ bộ:

\[
M_{\text{payload}} \approx \sum_{i=1}^{N} B_i
\]

Với body đồng đều:

\[
M_{\text{payload}} \approx N \times B
\]

Ví dụ giả định:

| Kích thước body | Request đồng thời đang giữ body | Payload cần giữ tối thiểu theo mô hình đơn giản |
| --- | ---: | ---: |
| 16 KiB | 100 | Khoảng 1,6 MiB |
| 512 KiB | 400 | Khoảng 200 MiB |
| 2 MiB | 400 | Khoảng 800 MiB |
| 8 MiB | 150 | Khoảng 1.200 MiB ≈ 1,17 GiB |

**Đây là ước lượng dung lượng payload, không phải đo RAM thực tế của JVM.** Bộ nhớ thực có thể lớn hơn do overhead của pooled buffers, allocator, copy, các đối tượng JSON, TLS buffers, response aggregation, các request khác, filter chain và pressure từ garbage collector.

### 4.1. Có phải retries=3 sẽ nhân body lên bốn lần?

**Không nhất thiết.** Nếu Gateway giữ **một body cache** và tái sử dụng nó cho nhiều attempts, `retries=3` **không mặc định** nghĩa là lưu bốn bản sao độc lập của cùng body.

Tuy nhiên, tăng số attempts thường **kéo dài thời gian request còn sống** và giữ buffer lâu hơn. Khi backend chậm hoặc outage, số request đồng thời tăng, làm tổng memory tăng dù từng request chỉ giữ một cache. Nếu thêm filter tự copy/deserialize body, số bản sao thực tế còn có thể tăng.

~~~text
Payload bytes mỗi request:       B
Thời gian giữ request:           T
Tốc độ request vào trung bình:   λ

Concurrent requests xấp xỉ λ × T trong trạng thái ổn định.
Body memory xấp xỉ λ × T × B (+ overhead).
~~~

Đây là ứng dụng sơ bộ của quan hệ concurrency/latency, **không phải công thức dự báo chính xác** khi có burst, backpressure, timeout không đều hoặc streaming.

### 4.2. Heap và direct memory là hai phần cần theo dõi

Với WebFlux/Reactor Netty, nhiều buffer có thể là **direct/off-heap** được pool. Do đó chỉ nhìn `-Xmx` hoặc biểu đồ heap có thể bỏ sót áp lực bộ nhớ. Các triệu chứng có thể gồm:

- `OutOfMemoryError: Direct buffer memory`, lỗi cấp phát native buffer;
- tăng RSS/container memory và bị Kubernetes OOMKilled;
- GC pressure nếu body được chuyển thành `String`, `byte[]` hoặc đối tượng JSON trên heap;
- tăng độ trễ p95/p99, request đang chờ và số connection đang mở;
- memory leak do custom filter không giải phóng `DataBuffer` đúng cách.

Theo dõi **JVM heap, Netty direct memory, process RSS, container memory, số request in-flight và kích thước payload** cùng lúc; không chỉ tăng heap để xử lý mọi sự cố.

### 4.3. Buffer tồn tại đến khi nào?

Thời gian buffer được giữ phụ thuộc cách Retry/CacheRequestBody trong version xử lý exchange, completion/cancellation, timeout và các filter khác. Không nên tự giả định buffer được giải phóng ngay sau một attempt thất bại. Cần test cả:

- Retry thành công sau attempt thứ hai;
- hết lượt retry, trả lỗi cuối;
- client hủy request giữa lúc backoff;
- timeout/kết nối tới backend bị hủy;
- backend trả response ngay khi chưa nhận hết body;
- Gateway bị overload hoặc shutdown.

Với custom `DataBuffer` processing, hãy dùng API Spring DataBufferUtils đúng contract; không `retain()` hoặc `release()` ngẫu nhiên chỉ để “giảm memory” trong một đoạn filter.

## 5. Bảo vệ trước body quá lớn: RequestSize

Spring Cloud Gateway WebFlux cung cấp **`RequestSize` GatewayFilter Factory**. Nó giới hạn request size theo tham số `maxSize` và theo tài liệu có thể trả **413 Payload Too Large** khi request bị từ chối:

~~~yaml
filters:
  - name: RequestSize
    args:
      maxSize: 128KB
~~~

`maxSize` chấp nhận kiểu `DataSize`, có đơn vị như `KB`/`MB`. Nếu bật RequestSize nhưng không khai báo giới hạn, tài liệu Gateway mô tả mức mặc định **5 MB**; **đó không phải một body limit toàn cục cho mọi route không dùng RequestSize**.

### 5.1. Thứ tự filter nên có chủ đích

Một route chỉ nên bật retry body sau khi đã có cơ chế kiểm soát payload:

~~~text
Client request
    ↓
Route predicates
    ↓
StripPrefix              (biến đổi path một lần)
    ↓
RequestSize max 128KB    (bảo vệ payload trước Retry)
    ↓
Retry methods POST       (cache/replay body; có thể lặp lại các filter phía sau)
    ↓
NettyRoutingFilter       (gửi request đến backend)
~~~

**RequestSize đặt trước Retry** theo thứ tự khai báo filter giúp kiểm soát trước khi chấp nhận retry; cần xác nhận thứ tự thực thi thực tế nếu dùng custom GlobalFilter/order. Chỉ dựa vào `Content-Length` cũng chưa đủ trong mọi trường hợp: client có thể gửi chunked/streaming hoặc header không chính xác. Cần phối hợp giới hạn ở ingress, HTTP server, filter và downstream, đồng thời kiểm thử **chunked request**.

### 5.2. Spring codec max-in-memory-size không phải lời giải toàn diện

Spring WebFlux cho phép cấu hình giới hạn buffer của một số **decoder/HttpMessageReader**, ví dụ `spring.codec.max-in-memory-size` trong các dòng Spring Boot có hỗ trợ. Nhưng không được coi nó là **giới hạn duy nhất và chắc chắn áp dụng cho tất cả body cache ở Gateway Retry**:

- Retry có đường cache `DataBuffer` riêng; tùy phiên bản có thể không sử dụng cùng decoder limit.
- Một `ModifyRequestBody` hoặc controller JSON có thể gặp `DataBufferLimitException` trong khi request raw proxy có đường xử lý khác.
- Multipart file upload có cơ chế threshold/disk usage khác phần form fields.
- Tăng `max-in-memory-size` lên hàng chục MiB để né exception có thể khiến nguy cơ OOM tệ hơn.

**Cách tiếp cận đúng:** giới hạn kích thước ở điểm vào, tránh retry với upload/streaming lớn, đo bộ nhớ thực và load-test với phiên bản Gateway cụ thể.

## 6. Cấu hình Retry an toàn cho GET và cho POST lab

### 6.1. Nên bắt đầu bằng GET không body

Ví dụ **Gateway Server WebFlux 5.x**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 2
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                    methods:
                      - GET
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 400ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

Ở route này, Retry chỉ được áp dụng cho GET; không cần body POST để phát lại. Hãy kiểm tra thời gian phản hồi thực tế, số attempts và tải backend trước khi tăng số lượt retry.

### 6.2. POST có body: chỉ bật khi hiểu idempotency

Ví dụ **lab cố tình retry POST** để quan sát body cache, không phải chính sách mặc định khuyên dùng cho mọi API:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: post-body-retry-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/retry/**
                - Method=POST
              filters:
                - StripPrefix=2
                - name: RequestSize
                  args:
                    maxSize: 128KB
                - name: Retry
                  args:
                    retries: 1
                    statuses:
                      - BAD_GATEWAY
                    methods:
                      - POST
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 200ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

Client gọi `POST /api/retry/echo`, backend thấy `POST /echo` vì `StripPrefix=2` chạy ở phía trước Retry. `retries=1` cho phép nhiều nhất hai attempts. `RequestSize` hạn chế payload lab, nhưng vẫn phải kiểm chứng hành vi thực tế khi dùng chunked transfer và với các filter khác.

### 6.3. Cấu hình tương ứng cho Gateway WebFlux 4.2/4.3

Với Gateway Server WebFlux 4.2/4.3, danh sách routes dùng prefix `spring.cloud.gateway.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: post-body-retry-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/retry/**
            - Method=POST
          filters:
            - StripPrefix=2
            - name: RequestSize
              args:
                maxSize: 128KB
            - name: Retry
              args:
                retries: 1
                statuses:
                  - BAD_GATEWAY
                methods:
                  - POST
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 200ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

**Chọn một namespace routes đúng release**, không khai báo cả hai bản cho cùng một project. Các bản WebFlux mới dùng starter thường là `spring-cloud-starter-gateway-server-webflux`; các bản 4.x trước đó thường dùng `spring-cloud-starter-gateway`. Sử dụng Spring Cloud BOM phù hợp Spring Boot và không thêm Servlet MVC starter vào Gateway WebFlux.

## 7. Lab: backend trả 502 lần đầu, 200 lần thứ hai

Để thấy Retry có **thực sự gửi cùng body ở attempt sau** hay không, tạo backend echo Spring Boot WebFlux tại `localhost:9091`. Backend đọc raw bytes, tính **SHA-256**, lưu số attempt theo ID lab và cố tình trả `502` ở attempt đầu, `200` ở attempt thứ hai.

**Quan trọng:** Backend này chỉ phục vụ quan sát, không tạo đơn hàng hay giao dịch thật. Không dùng nó làm minh chứng POST nghiệp vụ có thể retry an toàn.

### 7.1. Cấu hình backend

Tạo project Boot với dependency `spring-boot-starter-webflux`. File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091

spring:
  application:
    name: retry-body-lab-backend
~~~

Lớp khởi động `src/main/java/demo/retry/RetryLabApplication.java`:

~~~java
package demo.retry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetryLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetryLabApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/retry/RetryEchoController.java`:

~~~java
package demo.retry;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class RetryEchoController {

    // Chỉ là bộ đếm lab trong RAM, không phải kho idempotency production.
    private final Map<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> echo(
            @RequestHeader("X-Lab-Request-Id") String requestId,
            @RequestBody Mono<byte[]> rawBody) {

        return rawBody.map(bytes -> {
            int attempt = attempts
                    .computeIfAbsent(requestId, ignored -> new AtomicInteger())
                    .incrementAndGet();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("requestId", requestId);
            result.put("attempt", attempt);
            result.put("bytes", bytes.length);
            result.put("sha256", sha256(bytes));

            HttpStatus status = attempt == 1
                    ? HttpStatus.BAD_GATEWAY
                    : HttpStatus.OK;

            return ResponseEntity.status(status)
                    .header("X-Backend-Attempt", Integer.toString(attempt))
                    .body(result);
        });
    }

    private String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

`Mono<byte[]>` và `Content-Type: application/octet-stream` cho phép backend nhận payload bytes để tính checksum. Đây là endpoint test giới hạn bởi memory/codecs của backend; không dùng để nhận upload lớn trong production. Trường `attempts` chỉ tồn tại trong một tiến trình và không dọn key, nên cũng chỉ phù hợp lab ngắn.

### 7.2. Khởi chạy

Trong terminal backend:

~~~bash
./mvnw spring-boot:run
~~~

Trong terminal Gateway khác, sử dụng cấu hình mục 6.2 hoặc 6.3 phù hợp version:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows, dùng `mvnw.cmd spring-boot:run` hoặc Maven đã cài. Đây là hướng dẫn tự thực hành; bài **không khẳng định đã chạy code hay build/test trong repository**.

### 7.3. Gửi POST qua Gateway

~~~bash
curl -i "http://localhost:8080/api/retry/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: body-replay-001" \
  --data-binary "retry-demo-payload"
~~~

Với backend chưa từng nhìn thấy `body-replay-001`, kết quả **kỳ vọng**:

- Attempt thứ nhất vào backend với path `/echo`; backend đọc 18 bytes và trả `502 BAD_GATEWAY`.
- Retry filter nhận status 502 được cho phép và thử thêm lần thứ hai.
- Attempt thứ hai vào backend cũng với body có **18 bytes và cùng SHA-256**, backend trả `200 OK`.
- Client nhận response cuối với JSON `attempt=2` và header `X-Backend-Attempt: 2`.

Ví dụ response **minh họa** (không dùng SHA-256 giả để tránh tạo checksum không chính xác):

~~~http
HTTP/1.1 200 OK
X-Backend-Attempt: 2
Content-Type: application/json

{"requestId":"body-replay-001","attempt":2,"bytes":18,"sha256":"<hash-do-backend-tinh>"}
~~~

Để kiểm chứng checksum raw bytes độc lập, trên máy có `sha256sum`:

~~~bash
printf '%s' 'retry-demo-payload' | sha256sum
~~~

Nếu body qua Gateway bị mất hoặc bị sửa sai, số bytes/checksum tại backend sẽ khác. Nếu response là 502 với `attempt=1`, kiểm tra route có Retry POST hay không, filter được nạp đúng namespace và status có match điều kiện retry.

### 7.4. So sánh gọi backend trực tiếp

~~~bash
curl -i "http://localhost:9091/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: direct-001" \
  --data-binary "retry-demo-payload"
~~~

Lần direct đầu tiên thường trả **502**, vì không có Gateway Retry. Gọi lại lần nữa bằng **cùng** `X-Lab-Request-Id` thì backend trả **200**; điều này cho thấy điều kiện của backend là deterministic. Với Gateway, hai attempts xảy ra bên trong **một request client**.

### 7.5. Phân biệt bộ đếm attempt với dữ liệu thật

Trong code lab, `requestId` là một khóa để đếm attempts. Nó **không phải** implementation idempotency production: không có transactional persistence, không có TTL, không kiểm tra mismatch payload cùng ID, không ngăn nhiều process đồng thời. Tránh lấy ví dụ này rồi dùng `ConcurrentHashMap` làm hệ thống dedup thanh toán/đơn hàng.

## 8. Test kích thước lớn và request đồng thời

### 8.1. Test payload vượt giới hạn

Giới hạn ở route lab là `128KB`. Với shell Unix, tạo payload test tạm **ở ngoài repo**:

~~~bash
dd if=/dev/zero of=/tmp/retry-payload-256k.bin bs=1024 count=256
curl -i "http://localhost:8080/api/retry/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: too-large-001" \
  --data-binary "@/tmp/retry-payload-256k.bin"
~~~

Kết quả theo `RequestSize` là **413 Payload Too Large**, và backend không nên nhận body bị từ chối. Nếu test môi trường khác cho kết quả không đúng, kiểm tra filter order, transport, Content-Length, request size enforcement với streaming/chunked và các cấu hình/proxy phía trước.

**Không dùng bài test để tăng giới hạn vài trăm MiB cho dễ chạy**: mục đích là xác minh chính sách bảo vệ bộ nhớ, không phải stress hệ thống thiếu giới hạn. Với Windows, có thể tạo file nhị phân bằng công cụ phù hợp rồi dùng `curl.exe --data-binary "@file.bin"`.

### 8.2. Test body nhỏ, nhiều request cùng lúc

Trên máy test, chuẩn bị một nguồn tạo tải có kiểm soát (JMeter, k6, Gatling hoặc công cụ tương đương). Ví dụ mục tiêu:

~~~text
Route:       POST /api/retry/echo
Body sizes:  1 KiB, 32 KiB, 128 KiB
Concurrency: 10 → 50 → 100
Backoff:     100 ms
Retries:     1
Duration:    tăng từng bước, không tấn công hệ thống production
~~~

Đo **process RSS**, heap/non-heap/direct memory, số requests in-flight, p95/p99 latency, số 502 từ backend, số 200 cuối, số attempts trên backend và tỷ lệ 413/5xx/OOM. So sánh ba cấu hình: **không retry POST**, **retry POST body nhỏ**, và **retry POST dưới tải với giới hạn kích thước**.

Trong tải concurrent, không dùng cùng `X-Lab-Request-Id` cho nhiều **logical client requests**; nếu dùng chung, bộ đếm backend có thể làm response từ request thứ hai trả 200 ngay ở attempt đầu và khiến kết luận sai.

### 8.3. Hệ quả nếu body quá lớn và request tồn tại lâu

Giả sử 400 request đồng thời, mỗi body 2 MiB. Theo mô hình tối thiểu, payload đã khoảng **800 MiB** trước overhead. Nếu backend tạm lỗi, retry với backoff kéo dài mỗi request, số body cache tồn tại cùng lúc còn có thể tăng. Đây là một dạng **memory amplification do retry**, kể cả khi retry chỉ tạo **một bản body cache**.

Do đó quy tắc tốt là giới hạn **cả body size, số requests in-flight, retries, per-attempt timeout và overall request deadline**, thay vì chỉ chỉnh một tham số `maxSize`.

## 9. Filter order: Retry lặp lại những filter nào?

Spring Cloud Gateway cảnh báo: khi dùng Retry, nó **thử lại tất cả các filter đứng sau nó** trong chuỗi tương ứng. Điều này quan trọng khi filter có **side effect**:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      methods:
        - POST
  - AddRequestHeader=X-Attempt-Trace, repeated
~~~

Filter `AddRequestHeader` được chạy trong phần chuỗi phía sau Retry có thể thêm header lần nữa khi attempt lặp lại. Với filter tự viết, nguy cơ còn lớn hơn: ghi log sự kiện, trừ quota, gửi message, đọc body, tạo correlation ID hoặc cập nhật state có thể bị thực hiện nhiều lần.

### 9.1. Thiết kế trước/sau Retry có chủ đích

| Filter/chức năng | Thường nên đặt | Lý do |
| --- | --- | --- |
| Xác thực JWT/session | Security WebFilter trước proxy | Không xác thực lại vì mỗi retry backend, không tin token chưa verify |
| Giới hạn payload `RequestSize` | Trước Retry | Từ chối body lớn trước khi cache/replay |
| Biến đổi path ổn định `StripPrefix` | Trước Retry trong lab | Tránh biến đổi lại path theo attempt |
| Rate limit theo request client | Trước Retry nếu muốn một quota cho mỗi client request | Tránh trừ nhiều quota do filter được chạy lại |
| Header correlation ID bất biến | Trước Retry hoặc thiết kế idempotent | Giữ cùng ID trên các attempts |
| HTTP routing | Phần downstream được Retry bao quanh | Cho phép thực hiện attempt tiếp theo |
| Retry attempt metrics | Trong phần attempt, thiết kế rõ | Cần đếm từng backend call, không nhầm với một client request |

Đây là khuyến nghị thiết kế, **không phải thứ tự tuyệt đối cho mọi GlobalFilter/custom filter**. Gateway tổng hợp các filter rồi sắp xếp theo order; cần quan sát effective order và test. Nếu filter đặt sau Retry có side effect, hãy đảm bảo idempotent hoặc cho nó biết attempt index.

### 9.2. CacheRequestBody/ModifyRequestBody và Retry

Nếu route đã có `ModifyRequestBody` trước Retry, có thể body được biến đổi một lần rồi Retry phát lại **body đã biến đổi**, tùy version/flow. Nếu nó nằm sau Retry, quá trình biến đổi có thể thực thi **nhiều lần**. Với chữ ký HMAC, mã hóa hay checksum, cần xác định chính xác body nào được ký/gửi đi, và có giữ Content-Length/Content-Type phù hợp hay không.

Không tự gộp/release `DataBuffer` để “tiết kiệm bộ nhớ” khi chưa có benchmark và hiểu cơ chế pooled buffers. Nếu cần đọc body nhiều lần, ưu tiên filter hỗ trợ chính thức và kiểm tra tài liệu version tương ứng.

## 10. Idempotency: phát lại đúng bytes vẫn có thể tạo lỗi nghiệp vụ

Một request POST có thể **không idempotent**: gửi hai lần không tương đương gửi một lần.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as orders-service
    C->>G: POST /orders + Idempotency-Key: K1
    G->>O: Attempt 1, body B
    Note over O: Đã ghi order #123
    O--xG: Kết nối mất trước response
    G->>O: Attempt 2, vẫn body B
    alt Backend có dedup đúng
        Note over O: Nhận ra K1, không tạo order khác
        O-->>G: Kết quả order #123
    else Không có dedup
        Note over O: Có thể tạo order #124
        O-->>G: Response của đơn thứ hai
    end
    G-->>C: Kết quả cuối
~~~

**Idempotency key** phải được triển khai ở backend hoặc lớp có quyền kiểm soát nghiệp vụ, không chỉ được Gateway thêm vào header. Ví dụ chính sách:

1. Client gửi `Idempotency-Key` ổn định cho **một hành động logic**, không đổi giữa attempts.
2. Backend gắn key với caller/tenant/endpoint và fingerprint request, lưu trạng thái xử lý ở kho bền vững.
3. Nếu cùng key + cùng request đã hoàn tất, backend trả kết quả đã lưu; nếu đang xử lý, trả trạng thái có chủ đích.
4. Nếu cùng key nhưng payload khác, backend từ chối để tránh trùng/mismatch.
5. Có TTL và unique constraint/transaction để xử lý các request concurrent.

**Không phải mọi POST có idempotency key đều an toàn để tự động retry**: cần xem contract API, duplicate suppression và dữ liệu đã commit. Đặc biệt tránh retry mặc định với thanh toán, phát OTP, upload nhiều phần hoặc gửi lệnh điều khiển thiết bị.

## 11. Những request không nên cache/retry body theo cách thông thường

| Loại request | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Upload tệp vài trăm MiB/GiB | Cache toàn bộ body gây OOM/native pressure | Không retry tại Gateway; dùng streaming, upload trực tiếp object storage hoặc resumable upload |
| Multipart file upload | Nhiều buffer/temporary files và metadata | Chọn cơ chế multipart có limits/cleanup; tránh cache lặp |
| Streaming vô hạn/chunked dài | Không biết trước giới hạn body; cache có thể không kết thúc | Không dùng retry body toàn bộ; thiết kế protocol reconnect/resume |
| SSE/WebSocket/gRPC streaming | Ngữ nghĩa luồng/connection khác HTTP request đơn | Dùng cơ chế retry/reconnect riêng có resume offset |
| POST thanh toán/tạo đơn | Có side effect dù response 502 | Chỉ retry khi backend hỗ trợ idempotency contract |
| Gửi dữ liệu nhạy cảm/token trong body | Bản sao body nằm trong memory lâu hơn | Hạn chế retention, bảo vệ logs/memory dumps, timeout sớm |
| GET/HEAD không có body | Không cần body cache như POST | Ưu tiên retry thận trọng với backoff và giới hạn attempts |

Khi cần xử lý tải lớn, một lựa chọn thiết kế tốt là để Gateway **stream proxy không cache toàn bộ body**, còn việc thử lại thực hiện tại client hoặc tầng lưu trữ có resume/idempotency phù hợp. Thay đổi này phải phù hợp SLA và khả năng chịu lỗi của sản phẩm.

## 12. Timeout, backoff, jitter và retry storm

**Retry làm tăng tổng thời gian chờ**, không tự giảm lỗi nếu backend đang quá tải. Với:

~~~text
Lần 1: timeout sau 2 giây
Backoff: 100 ms
Lần 2: timeout sau 2 giây
Backoff: 200 ms
Lần 3: timeout sau 2 giây
~~~

request có thể giữ body và kết nối trong **hơn sáu giây** cộng backoff/overhead, mặc dù mỗi attempt chỉ chờ hai giây. Cần xác định **deadline end-to-end** độc lập với giới hạn từng attempt.

Jitter giúp giảm việc nhiều Gateway replica retry đồng thời sau một sự cố chung. Dù Gateway 5.x có tham số `jitter.randomFactor`, hãy kiểm tra hỗ trợ và semantics ở version đang dùng; không chép một property mới vào config 4.x rồi mặc định tin là có hiệu lực.

### 12.1. Retry storm và load balancing

Khi có 1000 request/s và tất cả gặp 503:

~~~text
Không Retry: backend nhận khoảng 1000 attempts/s
retries=2: có thể lên tới khoảng 3000 attempts/s
~~~

Đây là **ước lượng worst-case đơn giản**, không phải phép đo thực tế. Khi load balancing chọn instance khác cho các attempts, retry có thể chuyển tải từ backend đang lỗi sang các backend còn khỏe, gây **cascading failure**. Cần kết hợp retry budget, circuit breaker, concurrency limit, deadline, rate limiting và health-based discovery.

**Một client request ≠ một backend attempt.** Trong logs/metrics cần ghi cả số yêu cầu từ client lẫn số attempt được gửi xuống backend để thấy hệ số khuếch đại lưu lượng.

### 12.2. Retry kết hợp circuit breaker

Thứ tự của Retry và CircuitBreaker filter ảnh hưởng điều gì được tính là một lỗi và khi nào circuit mở. Nếu circuit breaker bao quanh toàn bộ chuỗi retry, một logical request có thể được tính khác so với circuit breaker được gọi lại trên mỗi attempt. Cần thiết kế thứ tự, lỗi được retry, fallback và các chỉ số theo đúng mong muốn, rồi kiểm chứng thực tế; **không bật hai cơ chế mặc định cùng lúc** chỉ để “tăng độ bền”.

## 13. Quan sát body cache và bảo vệ thông tin nhạy cảm

Các chỉ số đáng theo dõi:

- `gateway.request.inflight`: request đang xử lý và thời gian sống;
- `gateway.retry.attempts`: attempts trên mỗi logical request, phân nhóm theo route;
- `gateway.retry.success_after_retry`: tỷ lệ thành công sau retry;
- `gateway.retry.exhausted`: lần retry cuối vẫn lỗi;
- phân phối request body size theo bucket, **không tag từng request ID**;
- JVM heap, direct memory, Netty allocator memory, process RSS/container usage;
- số kết nối backend, timeout, 502/503, cancellation và client disconnect;
- tỷ lệ trả 413 do kích thước request.

Tên metrics có thể do hệ thống bạn tự định nghĩa hoặc được thư viện tích hợp xuất ra khác nhau; **không giả định mọi tên trong danh sách là metrics mặc định của Gateway**.

### 13.1. Điều không nên ghi vào log

Không log raw `Authorization`, cookie session, request body có thông tin cá nhân, access token, thông tin thanh toán hoặc toàn bộ `CACHED_REQUEST_BODY_ATTR`. Body cache có thể tồn tại trong bộ nhớ đến khi exchange kết thúc; việc đưa body vào log sẽ tạo **thêm bản sao** và rủi ro lộ dữ liệu.

Nếu cần xác minh body integrity trong lab, dùng **SHA-256 và kích thước** thay vì log nguyên payload. Trong production, checksum cũng có thể trở thành dữ liệu có thể liên kết giữa requests, cần đánh giá yêu cầu bảo vệ thông tin.

### 13.2. Các tín hiệu gỡ lỗi

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| Attempt thứ hai nhận body rỗng | Body bị filter trước đó tiêu thụ, Retry không match method/status, request decorator sai | Filter order, cached body và số bytes backend |
| Memory tăng khi POST retry | Body cache tồn tại nhiều request đồng thời hoặc có extra body copies | RSS, direct memory, in-flight, body size và retry duration |
| `DataBufferLimitException` | Một decoder/filter phải aggregate body vượt giới hạn | Codec/filter cụ thể, không chỉ tăng maxInMemorySize |
| 413 trước backend | `RequestSize`/ingress giới hạn payload | MaxSize, header Content-Length và chunked transfer |
| Client 200 nhưng hai đơn hàng tạo ra | Retry POST không có idempotency | Backend transaction, unique key, số attempts |
| Lặp body sai checksum | Transform body bị chạy nhiều lần hoặc encoding thay đổi | Hash raw bytes tại backend, Content-Type/Length |
| Filter sau Retry chạy nhiều lần | Retry bao quanh phần chain phía sau | Tái cấu trúc filter order hoặc làm filter idempotent |
| GET hoạt động, POST timeout/OOM | Chỉ POST cần cache body | Giới hạn body và concurrency, cân nhắc bỏ retry POST |
| Client hủy nhưng memory không giảm | Buffer reference leak hoặc cancellation cleanup sai trong custom filter | DataBufferUtils release, metrics allocator, leak detection |
| Retry 5xx rồi tiếp tục 429 | Rate limiter và retry thứ tự không đúng policy | Đếm client requests so với backend attempts |

## 14. Checklist triển khai production

- [ ] Chỉ bật Retry cho **methods và status/exceptions có thể phục hồi**, ưu tiên GET/HEAD không có body khi thích hợp.
- [ ] Với POST/PUT/PATCH có body, có **idempotency contract** thực sự; không dựa vào cache body để chống duplicate.
- [ ] Hiểu `retries` là **số lượt thêm** và giới hạn tổng attempts.
- [ ] Biết body cache WebFlux gắn với `CACHED_REQUEST_BODY_ATTR` và có thể dùng pooled `DataBuffer`.
- [ ] Có `RequestSize`/ingress size limit và đã thử Content-Length, chunked request, multipart và body lớn.
- [ ] Đã kiểm tra thứ tự của Retry với StripPrefix, RequestSize, body modifiers, rate limiter và circuit breaker.
- [ ] Có per-attempt timeout, overall deadline, backoff và jitter phù hợp version.
- [ ] Đo heap **và direct memory** dưới tải concurrent; không chỉ tăng `-Xmx`.
- [ ] Test Retry thành công, hết attempts, client cancel, backend timeout, connection reset và lỗi sau khi backend đã commit.
- [ ] Không bật body retry cho upload lớn, streaming hoặc workflow không replay-safe.
- [ ] Không tự retain/release `DataBuffer` trong custom filter nếu chưa tuân thủ contract ref-count.
- [ ] Idempotency key giữ nguyên giữa attempts, được backend kiểm tra bằng kho bền vững.
- [ ] Retry không làm tăng backend load vượt ngân sách; circuit breaker/load balancer/rate limiter được cấu hình tương thích.
- [ ] Log/trace/metric phân biệt một client request với nhiều backend attempts, không ghi body/token nhạy cảm.
- [ ] Có runbook khi memory/RSS tăng, OOMKilled, 502/503 hàng loạt và giảm số retries.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao Retry cho POST cần lưu body?**

Vì body HTTP đi vào thường là một reactive stream được tiêu thụ theo luồng; lần thử tiếp theo cần một nguồn có thể phát lại dữ liệu, không thể mong socket tự gửi lại bytes đã đọc.

**2. Với `retries: 2`, tối đa có bao nhiêu attempts?**

Thông thường **ba**: một attempt đầu và hai attempts bổ sung.

**3. Bật `retries: 3` có nghĩa Gateway bắt buộc giữ bốn bản sao body trong memory không?**

Không. Gateway có thể tái sử dụng một body cache; nguy cơ lớn đến từ **số request in-flight, body size, thời gian giữ buffer và các copy do filter khác tạo**.

**4. Vì sao thêm `spring.codec.max-in-memory-size=100MB` không phải biện pháp an toàn?**

Vì đó là limit của các codec/decoder tương ứng, không phải bảo đảm giới hạn mọi body cache của Retry; tăng mạnh còn làm mỗi request có thể giữ body lớn hơn và đẩy hệ thống tới OOM.

**5. Backend đã tạo đơn nhưng trả 502 do mất kết nối, Gateway retry cùng body. Có an toàn không?**

Không tự động an toàn. Cần backend hỗ trợ **idempotency key/transaction** để nhận diện duplicate và trả kết quả nhất quán.

**6. Vì sao nên giữ `RequestSize` trước `Retry`?**

Để giới hạn payload trước khi chấp nhận khả năng cache/replay, giảm nguy cơ giữ body lớn trong bộ nhớ. Vẫn cần kiểm thử thực tế với custom filter và chunked transfer.

## 16. Tài liệu tham khảo

1. [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html): tham số Retry, cache body trong `DataBuffer` và cảnh báo memory.
2. [Spring Cloud Gateway Server WebFlux 4.2 — Retry](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/retry-factory.html): tham số và cấu hình route theo namespace 4.x.
3. [Spring Cloud Gateway Server WebFlux — RequestSize](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestsize-factory.html): `maxSize`, 413 và giới hạn kích thước request.
4. [Spring Cloud Gateway Server WebFlux — CacheRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/cacherequestbody-factory.html): đọc/cache body cho các filter khác.
5. [Spring Framework WebFlux — Reactive Core, DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): pooled/direct buffers, cleanup và memory.
6. [Spring Framework WebFlux — HTTP Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): giới hạn memory của các decoder/reader.
7. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): khái niệm method idempotent, status codes và retry considerations.

**Ghi nhớ:** Retry một HTTP request có body trong Gateway WebFlux cần **khả năng phát lại body**, và framework có thể **cache `DataBuffer` theo exchange** để phục vụ các attempts. Body cache làm tăng bộ nhớ cần giữ khi số request đồng thời cao hoặc backend chậm; **retries tăng thời gian sống của buffer**, không nhất thiết tạo một bản sao mới ở từng attempt. Giới hạn payload, concurrency, timeout và retry budget; kiểm tra filter order và **idempotency nghiệp vụ** trước khi bật retry cho POST/PUT/PATCH.
