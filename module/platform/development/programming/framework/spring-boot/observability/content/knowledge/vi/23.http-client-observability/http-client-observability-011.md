# Client timeout

Order Service gọi Inventory Service để kiểm tra tồn kho. Khi Inventory chậm, request của Order có thể giữ thread và connection lâu hơn dự kiến. Nếu nhiều request cùng chờ, thread pool hoặc connection pool có thể cạn, làm latency lan sang các API khác. Timeout giới hạn thời gian chờ ở từng giai đoạn của HTTP client; HTTP client Observation giúp thấy request outbound kết thúc vì response, HTTP error hay timeout.

Bài **Client timeout** thuộc chương **HTTP client observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Không có một timeout duy nhất tự động giới hạn toàn bộ thời gian của HTTP call. Connect timeout, read/response timeout, connection-pool acquisition timeout và deadline nghiệp vụ bảo vệ các khoảng chờ khác nhau. Cấu hình phải phù hợp request factory/HTTP client thực tế, ngân sách latency của caller và retry policy. Khi timeout xảy ra trước khi nhận response, Observation thường không có HTTP status thật; hãy quan sát exception, duration và status fallback riêng biệt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vì sao HTTP client cần timeout trong hệ thống Spring Boot.
2. Phân biệt connect, read/response, pool acquisition timeout và end-to-end deadline.
3. Hiểu timeout được áp dụng bởi ClientHttpRequestFactory và HTTP client implementation.
4. Cấu hình timeout toàn cục bằng Spring Boot properties và timeout riêng qua RestTemplateBuilder.
5. Nhận biết khác biệt API timeout giữa các phiên bản Spring Boot.
6. Phân biệt timeout exception với HTTP response 5xx.
7. Đọc client Observation, metrics và traces khi request timeout.
8. Thiết kế retry/backoff phù hợp timeout budget và idempotency.
9. Tránh để request thread, connection pool hoặc downstream quá tải dây chuyền.
10. Kiểm thử timeout bằng server giả lập chậm và các tình huống connection failure.
11. Điều tra timeout theo từng giai đoạn: DNS, pool, connect, TLS, response và body read.

## 2. Vì sao phải cấu hình client timeout?

Một HTTP call có thể chờ ở nhiều giai đoạn:
- Phân giải hostname/DNS.
- Chờ connection khả dụng trong pool.
- Thiết lập TCP connection.
- Thực hiện TLS handshake.
- Gửi request.
- Chờ response headers.
- Đọc response body.
- Retry một hoặc nhiều attempts.

Nếu không có giới hạn phù hợp, request có thể chiếm thread và connection lâu. Khi traffic tăng, số request đang chờ tăng theo; service có thể hết thread, pool bị chiếm, queue dài và latency lan sang request khác.

~~~mermaid
flowchart TD
    A["HTTP client call"] --> B["Acquire connection"]
    B --> C["DNS / TCP connect"]
    C --> D["TLS handshake"]
    D --> E["Send request"]
    E --> F["Wait for response"]
    F --> G["Read response body"]
    G --> H["Complete"]
    B -. "pool acquisition timeout" .-> X["Fail"]
    C -. "connect timeout" .-> X
    D -. "TLS/handshake timeout" .-> X
    F -. "response/read timeout" .-> X
    G -. "read timeout" .-> X
~~~

Sơ đồ thể hiện các giai đoạn logic; HTTP client cụ thể có thể gộp hoặc triển khai một số giai đoạn khác nhau. Không phải request factory nào cũng cung cấp timeout riêng cho từng giai đoạn.

## 3. Các loại timeout cần phân biệt

| Loại timeout | Giới hạn khoảng chờ nào? | Ví dụ lỗi/triệu chứng |
|---|---|---|
| Connection-pool acquisition | Chờ lấy connection từ pool | Pool exhausted, lease timeout |
| DNS timeout | Phân giải hostname | Unknown host hoặc resolver timeout |
| Connect timeout | Thiết lập TCP connection | Connection timed out/refused |
| TLS handshake timeout | Thương lượng TLS | Handshake timeout/SSL exception |
| Response/read timeout | Chờ response hoặc dữ liệu tiếp theo | Read timed out, response timeout |
| Write timeout | Gửi request/body tới peer | Write timeout, broken pipe |
| End-to-end deadline | Tổng thời gian nghiệp vụ cho phép | Caller deadline exceeded |

Không phải request factory nào cũng cho cấu hình tất cả loại timeout. Ví dụ một client có thể chỉ expose connect và read timeout, còn pool acquisition timeout thuộc connection manager riêng. DNS/TLS timeout có thể do HTTP implementation quản lý hoặc dùng timeout khác.

### 3.1 Connect timeout

Connect timeout giới hạn thời gian client chờ thiết lập kết nối tới host/port. Nó không phải thời gian tối đa để server xử lý request. Khi kết nối đã thiết lập thành công, connect timeout không giới hạn thời gian chờ response.

### 3.2 Read/response timeout

Read timeout thường giới hạn thời gian chờ dữ liệu đọc từ socket hoặc response; semantics chi tiết phụ thuộc client implementation. Một số HTTP clients định nghĩa response timeout theo thời gian chờ response, số khác áp dụng socket read timeout cho từng lần đọc. Với streaming, timeout giữa các lần nhận dữ liệu có thể khác deadline tổng.

Không giả định read timeout luôn là tổng thời gian từ lúc gửi đến lúc nhận hết body. Kiểm tra tài liệu của request factory được sử dụng.

### 3.3 Pool acquisition timeout

Khi dùng connection pool, request có thể chờ connection rảnh trước khi connect tới server. Pool acquisition timeout bảo vệ thời gian chờ này. Nếu chỉ cấu hình connect/read timeout mà pool không có acquisition timeout, request vẫn có thể chờ lâu ngay cả khi connect timeout thấp.

### 3.4 End-to-end deadline

Deadline là ngân sách tổng cho toàn bộ thao tác nghiệp vụ, ví dụ kiểm tra tồn kho phải hoàn tất trong 800 ms. Deadline có thể bao gồm pool wait, connect, TLS, response, retry, serialization và code nghiệp vụ khác.

Một request có connect timeout 200 ms và read timeout 500 ms vẫn có thể vượt 800 ms nếu còn pool wait, retry hoặc nhiều dependency calls. Vì thế cần deadline ở tầng caller/use case, kết hợp timeout phù hợp ở transport.

## 4. Cấu hình timeout toàn cục trong Spring Boot

Spring Boot hiện hành hỗ trợ HTTP client defaults qua nhóm properties spring.http.client. Ví dụ:

~~~yaml
spring:
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
~~~

Các defaults này áp dụng cho client builders/request factories do Spring Boot auto-configuration quản lý, tùy client type và phiên bản. Client tự tạo request factory hoặc tự thay builder có thể không nhận defaults.

Timeout toàn cục giúp đặt baseline nhất quán, nhưng không nhất thiết phù hợp mọi downstream. Service quan trọng có thể cần timeout ngắn hơn; API xử lý báo cáo có thể có budget khác. Tạo cấu hình riêng khi SLA/use case khác nhau.

Tài liệu: [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html).

## 5. Cấu hình timeout qua RestTemplateBuilder

Với các phiên bản Spring Boot có RestTemplateBuilder API tương ứng, có thể đặt connect và read timeout:

~~~java
import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class InventoryClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://inventory.internal")
                .connectTimeout(Duration.ofMillis(200))
                .readTimeout(Duration.ofMillis(600))
                .build();
    }
}
~~~

API builder thay đổi theo versions. Spring Boot 3.4 trở lên có các method connectTimeout/readTimeout; API setConnectTimeout/setReadTimeout cũ đã deprecated trong các phiên bản mới hơn. Không copy method name giữa các version mà không kiểm tra API đang dùng.

Nếu ứng dụng tạo RestTemplateBuilder bean riêng, cần giữ cấu hình của Boot bằng RestTemplateBuilderConfigurer; tự thay builder mà không dùng configurer có thể làm mất RestTemplateCustomizers và defaults auto-configured.

### 5.1 Timeout toàn cục và timeout theo client

Dùng timeout toàn cục cho baseline và builder riêng cho downstream có budget khác.

| Client | Connect timeout | Read timeout | Lý do |
|---|---:|---:|---|
| Inventory | 200 ms | 600 ms | API nội bộ cần phản hồi nhanh |
| Payment | 500 ms | 2 s | External gateway có latency cao hơn |
| Catalog | 300 ms | 1 s | Read-heavy nhưng không nên giữ request lâu |

Đây chỉ là số minh họa, không phải giá trị khuyến nghị chung. Chọn theo latency distribution, SLO, network và khả năng xử lý dependency.

## 6. Khác biệt giữa các Spring Boot versions

API timeout và request factory configuration thay đổi theo version:

| Spring Boot version | Cách cấu hình thường gặp |
|---|---|
| 3.0–3.3 | RestTemplateBuilder với setConnectTimeout/setReadTimeout |
| 3.4–3.5 | connectTimeout/readTimeout; method set* deprecated; requestFactorySettings có từ 3.4 |
| 4.x | RestTemplateBuilder API trong package mới và client settings/request factory builders; kiểm tra version reference |

Từ Spring Boot 3.4, request factory settings cho phép cấu hình tập trung hơn; Spring Boot 4.x tiếp tục phát triển client settings và builder API. Package của RestTemplateBuilder cũng thay đổi giữa major versions. Đừng trộn import của Boot 3 với Boot 4 trong cùng ví dụ.

Tham khảo:
- [Spring Boot 3.4 RestTemplateBuilder](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html)
- [Spring Boot 4.0 RestTemplateBuilder](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html)
- [Spring Boot 4.2 RestTemplateBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html)

## 7. Request factory quyết định timeout thực tế

RestTemplate ủy quyền HTTP exchange cho ClientHttpRequestFactory. Request factory có thể dựa trên JDK client, Apache HttpComponents, Jetty hoặc implementation khác do ứng dụng cấu hình.

Các factory không nhất thiết có cùng semantics hoặc cùng tập timeout options. Một số hỗ trợ connection pooling và pool acquisition timeout; một số không. Một số dùng read timeout ở mức socket; một số expose response timeout riêng.

~~~mermaid
flowchart TD
    A["RestTemplate"] --> B["ClientHttpRequestFactory"]
    B --> C["JDK-based client"]
    B --> D["Apache HttpComponents"]
    B --> E["Jetty client"]
    C --> F["Implementation-specific timeout semantics"]
    D --> F
    E --> F
~~~

Khi đổi request factory hoặc dependency classpath, timeout có thể thay đổi dù YAML không đổi. Kiểm tra factory thực tế, connection manager/pool, TLS settings và tài liệu version.

### 7.1 Khi tự cấu hình request factory

Nếu cung cấp ClientHttpRequestFactory hoặc builder riêng, phải đặt timeout ở đúng layer của implementation. Việc tạo factory thủ công có thể khiến một số Boot defaults không được áp dụng. Test timeout thực tế bằng request chậm, không chỉ assert property đã bind.

## 8. Timeout và HTTP client Observation

RestTemplate Observation ghi nhận outbound exchange. Khi request hoàn tất:
- Có response: status và outcome có thể được ghi.
- Response 5xx: status 5xx; DefaultResponseErrorHandler có thể ném HttpServerErrorException.
- Connect/read timeout trước response: không có HTTP status từ server; instrumentation có thể ghi fallback UNKNOWN và exception type.
- Pool acquisition failure: có thể xảy ra trước khi gửi request; error context phản ánh exception từ pool/client implementation.

Ví dụ:

~~~text
method = GET
uri = /api/items/{sku}
clientName = inventory.internal
status = UNKNOWN
error = ResourceAccessException
duration = 612 ms
~~~

Đây là dữ liệu minh họa. Exception type thực tế phụ thuộc request factory; timeout có thể được wrap thành ResourceAccessException, IOException, SocketTimeoutException hoặc exception của HTTP client.

**Không đổi timeout thành status=504 trong client Observation nếu client không nhận HTTP 504 từ server.** 504 chỉ hợp lệ khi thực sự có HTTP response 504. Nếu gateway/caller tự tạo response 504 sau khi dependency timeout, server Observation ở phía caller có thể có status 504 trong khi outbound client Observation có status UNKNOWN.

## 9. Đọc timeout trong trace

Khi một request inbound gọi nhiều dependencies, client spans cho thấy mỗi outbound call tốn bao lâu và thất bại ở đâu.

~~~mermaid
flowchart LR
    A["Order server span<br/>920 ms"] --> B["Inventory client span<br/>600 ms"]
    A --> C["Payment client span<br/>200 ms"]
    A --> D["Validation/response<br/>120 ms"]
~~~

Ví dụ minh họa request tổng khoảng 920 ms; Inventory call chiếm 600 ms. Nếu Inventory span kết thúc với timeout sau 600 ms, trace giúp nhận diện dependency là phần chờ lớn nhất.

Trong trace backend, kiểm tra:
- Client span start/end và duration.
- Error event/exception type.
- Status code nếu response thực sự được nhận.
- Parent server span và các client spans khác.
- Retry attempts nếu mỗi attempt có span riêng.
- Trace context có nối tới downstream hay không.

Sampling có thể khiến một số trace không được export; metrics timeout/error rate vẫn hữu ích để phát hiện xu hướng tổng thể.

## 10. Timeout budget và retry

Retry không làm biến mất timeout; nó sử dụng thêm ngân sách. Một logical operation có deadline 1 giây, retry 3 lần với read timeout 600 ms mỗi lần có thể kéo dài vượt deadline đáng kể nếu không giới hạn attempts và backoff.

Một retry budget nên xem xét:
- Deadline tổng của caller.
- Timeout mỗi attempt.
- Số lần retry tối đa.
- Backoff và jitter.
- Thời gian pool acquisition/connect cho từng attempt.
- Thời gian còn lại trước deadline.
- Tính idempotent của operation.
- Retry-after từ server nếu có.

~~~text
Caller deadline: 1000 ms
Attempt 1 budget: 300 ms
Backoff: 50 ms
Attempt 2 budget: 300 ms
Backoff: 100 ms
Attempt 3 budget: remaining 250 ms
Reserve for response/cleanup: remaining budget
~~~

Ví dụ chỉ minh họa cách chia ngân sách. Không đặt tổng attempt budgets và backoffs vượt deadline. Khi không còn đủ thời gian cho một attempt hữu ích, fail sớm thay vì khởi động request chắc chắn không thể hoàn tất trong ngân sách.

### 10.1 Không retry mọi timeout một cách mù quáng

- GET/idempotent operations thường có thể retry theo policy.
- POST tạo payment/order có thể đã được server xử lý dù client timeout; retry có thể tạo giao dịch trùng nếu không có idempotency key.
- 4xx như 400/401/403 thường không nên retry như lỗi tạm thời.
- 429/503 có thể retry nếu policy và Retry-After cho phép.
- TLS certificate/configuration errors không được giải quyết bằng retry liên tục.
- DNS/connect failures có thể tạm thời nhưng cần backoff/jitter và giới hạn.

Timeout phía client không chứng minh server chưa xử lý request. Trước khi retry mutation, phải thiết kế idempotency hoặc reconciliation.

## 11. Timeout, connection pool và bulkhead

Với HTTP client dùng pool, connection có thể bị giữ trong lúc request chờ response. Nếu downstream chậm, pool nhanh chóng hết connection. Request mới chờ acquire connection, rồi có thể timeout trước cả khi connect.

Cần quan sát riêng:
- Pool leased/available/pending connections.
- Pool acquisition duration/timeouts.
- Connect failures và connect latency.
- Active requests và request queue.
- Response latency và timeout counts.

Bulkhead giới hạn số calls đồng thời tới một dependency để service chậm không chiếm toàn bộ resources của ứng dụng. Có thể dùng semaphore/thread pool isolation hoặc giới hạn connection pool tùy kiến trúc. Timeout và bulkhead bổ trợ nhau: timeout giới hạn thời gian; bulkhead giới hạn mức tiêu thụ tài nguyên đồng thời.

## 12. DNS, TLS và các pha timeout khác

Không phải mọi lỗi kết nối đều là connect timeout:

| Giai đoạn | Triệu chứng | Hướng điều tra |
|---|---|---|
| DNS | UnknownHostException, resolver delay | DNS server, search domains, TTL, resolver timeout |
| Pool acquire | Lease timeout, pending tăng | Pool max, leak, response body chưa đóng, concurrency |
| TCP connect | Connect timed out/refused | Routing, firewall, endpoint health |
| TLS handshake | SSLHandshakeException, handshake timeout | CA chain, certificate, protocol, peer |
| Write | Broken pipe, write timeout | Peer close, request body size, network |
| Read/response | SocketTimeoutException, response timeout | Downstream latency, network, server saturation |
| Body decode | Conversion exception sau response | Content-Type, payload, message converter |

Khi TLS handshake thất bại, client có thể chưa gửi HTTP request; do đó không có HTTP status. Không tắt certificate verification để xử lý timeout/handshake error. Sửa CA, hostname, certificate validity và truststore đúng cách.

## 13. Kiểm thử timeout có kiểm soát

Một test timeout đáng tin cậy cần mô phỏng đúng giai đoạn chờ. Có thể dùng mock server hoặc local test server với endpoint delay.

Các kịch bản:
1. Server accept connection nhưng trì hoãn response headers quá read/response timeout.
2. Server gửi headers sớm nhưng trì hoãn body chunks để kiểm tra read inactivity timeout.
3. Port không mở để kiểm tra connect refused (không nhất thiết chờ hết connect timeout).
4. Host không phân giải được để kiểm tra DNS failure.
5. Pool có giới hạn nhỏ và giữ connection để kiểm tra acquisition timeout nếu client hỗ trợ.
6. TLS server có certificate không trusted để kiểm tra handshake failure.
7. Retry nhiều attempts để kiểm tra tổng deadline.

### 13.1 Ví dụ test server trả chậm

~~~java
@RestController
class SlowController {

    @GetMapping("/slow")
    String slow() throws InterruptedException {
        Thread.sleep(1500);
        return "done";
    }
}
~~~

Nếu client read timeout nhỏ hơn 1.5 giây, request có thể thất bại trước khi server trả response. Đây là test minh họa; dùng delay có kiểm soát, tránh sleep dài trong test suite chính nếu có thể thay bằng latch hoặc mock server.

### 13.2 Assert Observation

Dùng test ObservationRegistry hoặc MeterRegistry để xác nhận:
- Observation được start và stop dù request ném exception.
- Duration được ghi nhận.
- Error chứa exception phù hợp.
- Status là UNKNOWN khi không có response.
- Status là 503 nếu mock server thực sự trả 503.
- Retry attempts có số Observation mong đợi.
- Không có metric tags chứa raw URL/SKU/request ID.

Đừng chỉ assert client ném exception; kiểm tra signal và context mà hệ thống sẽ dùng khi vận hành.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request chờ rất lâu dù connect timeout ngắn | Đang chờ pool hoặc response; connect timeout không áp dụng | Cấu hình acquisition/read/deadline phù hợp |
| Read timeout không có hiệu lực | Request factory không hỗ trợ hoặc custom factory bỏ qua settings | Kiểm tra factory/implementation và test thực tế |
| Request timeout trước khi connect | Pool acquisition hoặc DNS timeout | Quan sát pool pending và DNS |
| Client span status UNKNOWN | Không nhận HTTP response trước lỗi | Kiểm tra exception type và giai đoạn timeout |
| Client span status 504 | Có HTTP 504 response từ proxy/server | Điều tra gateway/downstream; phân biệt với local timeout |
| Timeout xuất hiện sau đổi dependency | Request factory/client implementation đã đổi | Kiểm tra classpath và factory được chọn |
| Pool pending tăng và latency lan rộng | Connection bị giữ lâu hoặc pool quá nhỏ | Kiểm tra response body lifecycle, pool sizing và bulkhead |
| Retry làm dependency quá tải | Attempts/backoff không giới hạn hoặc retry mọi lỗi | Đặt retry budget, jitter và retryable classification |
| POST bị thực hiện hai lần sau timeout | Caller không biết server đã xử lý hay chưa | Idempotency key và reconciliation |
| Trace thiếu downstream server span | Request chưa tới server hoặc propagation bị strip | Kiểm tra client duration, network và trace headers |
| Timeout test không ổn định | Dựa vào sleep/timing quá sát | Dùng latch, mock server và margin rõ ràng |
| TLS error bị retry liên tục | Coi lỗi cấu hình như lỗi tạm thời | Fail fast, sửa CA/certificate/truststore |

## 15. Playbook: Inventory call vượt latency budget

**Tình huống:** p95 của Order API vượt SLO; trace cho thấy call Inventory chờ lâu và đôi khi timeout.

1. Lọc traces theo route và time window bị ảnh hưởng.
2. Mở client span Inventory, so duration với deadline của Order API.
3. Kiểm tra status và error: response 503 khác local timeout UNKNOWN.
4. Nếu timeout xảy ra trước connect, kiểm tra pool pending/acquisition và DNS.
5. Nếu connect thành công nhưng response chậm, xem server span/log của Inventory và network latency.
6. So sánh p50/p95/p99, timeout count và pool metrics.
7. Kiểm tra retry attempts, backoff, idempotency và tổng thời gian.
8. Chọn timeout mỗi attempt nhỏ hơn deadline tổng, dành ngân sách cho phần xử lý còn lại.
9. Giới hạn concurrency/bulkhead nếu dependency có thể bão hòa.
10. Test lại với response delay và xác nhận client Observation ghi đúng duration/error/status.

Không chỉ tăng timeout để làm giảm số exception. Timeout quá dài có thể giữ tài nguyên lâu hơn và làm sự cố lan rộng.

## 16. Bài tập tự kiểm tra

**Bài 1 — Phân biệt timeout.** Một request chờ connection pool 400 ms, connect 50 ms và read 200 ms. Timeout nào giới hạn thời gian chờ pool? Vì sao connect timeout không giải quyết được nó?

**Bài 2 — Không có HTTP response.** DNS lookup thất bại. Client Observation nên ghi status gì? Vì sao không nên gán 500 hoặc 504 giả cho outbound call?

**Bài 3 — Deadline.** Caller có deadline 900 ms, mỗi attempt read timeout 700 ms, retry tối đa hai lần. Vì sao cấu hình này có thể vượt deadline? Hãy chia ngân sách hợp lý hơn.

**Bài 4 — Spring Boot version.** Vì sao ví dụ setReadTimeout có thể deprecated ở Spring Boot 3.4+, và cần kiểm tra gì trước khi copy code?

**Bài 5 — Request factory.** Ứng dụng đổi từ JDK request factory sang Apache HttpComponents và timeout thay đổi. Những semantics nào cần kiểm tra?

**Bài 6 — POST retry.** Payment request timeout sau khi gửi body. Vì sao retry có thể tạo charge trùng? Vai trò của idempotency key?

**Bài 7 — Pool saturation.** Pool pending tăng, connect timeout không xuất hiện. Điều này gợi ý gì và cần đo metric nào?

**Bài 8 — Trace.** Client span có duration 600 ms, status UNKNOWN, error là SocketTimeoutException. Hãy nêu các khả năng và thứ tự điều tra.

### Gợi ý trả lời

1. Pool acquisition timeout giới hạn thời gian chờ connection. Connect timeout chỉ bắt đầu khi client thực hiện thiết lập kết nối.
2. UNKNOWN/fallback theo convention vì chưa có HTTP response. 500/504 chỉ hợp lệ khi server/proxy thực sự trả status đó.
3. Hai attempts 700 ms cộng backoff và pool/connect có thể vượt 900 ms. Chia deadline thành budgets mỗi attempt, backoff và reserve cho response/cleanup.
4. API builder mới dùng connectTimeout/readTimeout; method set* cũ bị deprecated. Kiểm tra Spring Boot version và request factory API.
5. Connect/read/response timeout semantics, pool acquisition, TLS, redirect, cancellation và default values.
6. Server có thể đã xử lý charge trước khi response bị mất; idempotency key cho phép server nhận diện lần retry cùng logical operation.
7. Request chờ connection pool, không phải đang connect. Đo leased/available/pending, acquisition duration và acquisition timeout.
8. Kiểm tra read/response timeout, server latency, network, body streaming, pool và retries; status UNKNOWN nghĩa không nhận response HTTP.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestTemplateBuilder, global HTTP client settings, request factory và timeout configuration.
- [Spring Boot 3.4 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html): connectTimeout/readTimeout và requestFactorySettings.
- [Spring Boot 4.0 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html): builder/client settings trong Boot 4.
- [Spring Boot 4.2 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html): API hiện hành và các method deprecated.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate và ClientHttpRequestFactory.
- [Apache HttpComponents Client](https://hc.apache.org/httpcomponents-client-5.5.x/current/user-manual/html/): connection manager, connection request timeout và socket/response timeout.
- [JDK HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): connect timeout và request timeout của JDK client.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle và handlers.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): client spans, error recording và context propagation.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP client duration, status và error attributes.

**Ghi nhớ:** Timeout bảo vệ tài nguyên và latency budget của caller. Connect timeout không giới hạn pool wait hay response read; read timeout không nhất thiết là deadline tổng. Request factory quyết định semantics thực tế, nên test sau khi đổi client implementation hoặc Spring Boot version. Quan sát duration, exception, status, pool metrics và retry attempts cùng nhau; timeout trước response thường không có HTTP status. Chọn retry theo deadline và idempotency, đồng thời giới hạn concurrency để dependency chậm không làm sụp caller.

