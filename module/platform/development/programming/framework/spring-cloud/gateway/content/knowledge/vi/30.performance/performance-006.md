# Tác động của logging, tracing và biến đổi body

## 1. Bối cảnh: hiệu năng Gateway không chỉ là thời gian gọi upstream

Trong kiến trúc microservices, **Spring Cloud Gateway** đứng trên đường đi của nhiều HTTP requests. Gateway chọn route qua predicate, chạy filter chain, viết lại đường dẫn/header, tìm service instance và gọi backend; các chính sách xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request cùng hoạt động trên đường đi đó.

Một request thông thường:

~~~text
Client ──HTTP──> Gateway ──HTTP──> order-service
                  │
                  ├─ route predicates
                  ├─ authentication/authorization
                  ├─ path/header filters
                  ├─ rate limiting / resilience
                  ├─ HTTP client / TLS
                  └─ metrics / logs / tracing
~~~

Vì Gateway xử lý lưu lượng tập trung, một thay đổi tưởng nhỏ — bật `DEBUG`, ghi toàn bộ body vào log, sample 100% traces hoặc thêm JSON rewrite — có thể gây tăng CPU, phân bổ bộ nhớ, disk/network I/O và latency của **tất cả requests đi qua route**.

Ví dụ:

- Với lưu lượng thấp, một dòng log bổ sung gần như không nhìn thấy trong p50.
- Khi lượng request tăng, ghi log đồng bộ hoặc export spans gặp nghẽn có thể làm **p99** tăng mạnh dù upstream không thay đổi.
- Body transform từ streaming sang giải mã/encode toàn bộ JSON có thể tăng **heap/pooled buffers** theo kích thước body và số requests đang xử lý.
- Wiretap hoặc logging nhầm header/body có thể gây **rò rỉ token/PII**, ngoài vấn đề hiệu năng.

Bài **“Tác động của logging, tracing và biến đổi body”** thuộc chương **Hiệu năng** của module **SPRING_CLOUD_GATEWAY**. Chúng ta phân tích tác động thực tế của từng cơ chế, cách đo bằng benchmark có đối chứng và cách chọn cấu hình phù hợp môi trường production.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt **access log**, **application log**, **Reactor Netty wiretap**, **trace** và **metrics**.
2. Giải thích chi phí CPU, I/O, allocation, queue và backpressure của từng loại quan sát.
3. Cấu hình logging và tracing phù hợp cho Gateway Server WebFlux, nhận biết khác biệt 4.x/5.x.
4. Hiểu tại sao `ModifyRequestBody`/`ModifyResponseBody`, body caching và logging body có thể phá ưu điểm streaming.
5. Đọc p50/p95/p99 latency, throughput, error rate, event-loop lag, heap/GC, direct memory và exporter drops.
6. Thiết kế benchmark **baseline → bật từng cơ chế → kết hợp → kiểm tra dưới tải cao**.
7. Viết test HTTP qua mock upstream để xác nhận tính đúng đắn của body/header/status song song với đo hiệu năng.
8. Đề xuất chính sách logging, sampling, kích thước payload, rate limiting và alert trước production.

> **Phạm vi:** trọng tâm là **Spring Cloud Gateway Server WebFlux** dùng Reactor Netty. Server Web MVC chạy Servlet, dùng các executor/filters khác; những kết luận về CPU, I/O và buffering vẫn có giá trị nhưng **không copy nguyên `GlobalFilter`, `DataBuffer` hoặc cấu hình Netty** sang Server Web MVC. Những property phụ thuộc Spring Cloud Gateway/Spring Boot release train được ghi rõ; đối chiếu đúng phiên bản thực tế.

## 2. Đặt mô hình đo: latency, throughput và tài nguyên

### 2.1. Latency end-to-end gồm nhiều thành phần

Một request có thể tiêu tốn thời gian ở:

~~~text
Client -> Gateway:
  network_in
  + accept / decode / security / route match
  + request filters
  + acquire outbound connection / DNS / TLS
  + upstream processing / network
  + response filters
  + write response / network_out

Cộng thêm (nếu bật):
  log formatting + log sink I/O
  trace observation / span creation + exporter pressure
  body decoding + transformation + encoding
  GC/allocator pressure + scheduler/queue contention
~~~

Không cộng các thành phần này một cách máy móc như thể chúng **luôn tuần tự**: HTTP streaming, asynchronous queues và concurrency khiến một số hoạt động chồng lấp. Công thức có giá trị để **lập giả thuyết** và xác định điểm đo, không phải một bộ cộng chính xác cho mọi request.

### 2.2. Chỉ số phải thu thập

| Chỉ số | Phản ánh | Khi tăng cần nghĩ đến |
| --- | --- | --- |
| **RPS / throughput** | Số request hoàn thành mỗi giây | Sức tải và saturation |
| **p50 latency** | Trải nghiệm request điển hình | Chi phí trung bình/hop |
| **p95/p99 latency** | Đuôi latency, request chậm | Queue, I/O blocking, GC, slow backend |
| **Error rate** | 4xx/5xx/timeout theo route | Overload, upstream fail, policy |
| **CPU usage / throttling** | Mức xử lý và cgroup quota | Serialization, logs, GC, TLS |
| **Heap used / allocation rate** | Đối tượng Java và pressure lên GC | JSON/log objects, body copies |
| **Direct/pooled memory** | Bộ nhớ buffer ngoài heap của Netty | Payload/buffer retention, leak |
| **GC pause và frequency** | Dừng do garbage collector | Allocation pressure, memory sizing |
| **Active outbound connections** | HTTP client pool | Concurrency, connect bottleneck |
| **Event-loop lag / blocked threads** | Reactor Netty event loop có bị giữ quá lâu | Sync logging, parse JSON, file I/O |
| **Log queue/dropped logs** | Logging pipeline chịu tải | Async appender capacity, slow sink |
| **Span export queue/drops** | Trace pipeline chịu tải | Sampling, backend lỗi, OTLP timeout |
| **Bytes in/out** | Network volume | Body logging, payload expansion, retry |
| **Backend p95/p99** | Latency tại upstream | Phân biệt lỗi Gateway với dịch vụ |

**Mục tiêu tối ưu là giữ đúng HTTP contract và security trong ngân sách tài nguyên**, không đơn thuần đạt RPS lớn nhất bằng cách tắt hết logging/tracing.

### 2.3. Xem tail latency thay vì chỉ trung bình

Ví dụ **số liệu giả định để minh họa**, không phải benchmark đã chạy:

| Scenario | RPS | p50 | p95 | p99 | CPU Gateway |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline route đơn giản | 1.200 | 14 ms | 29 ms | 46 ms | 38% |
| Thêm log metadata từng request | 1.180 | 15 ms | 32 ms | 53 ms | 44% |
| Bật wiretap dưới tải lớn | 890 | 20 ms | 71 ms | 160 ms | 79% |
| Rewrite JSON body lớn | 760 | 23 ms | 95 ms | 210 ms | 86% |

Các con số chỉ diễn giải hướng **có thể xảy ra**. Không được dùng như kết luận “wiretap luôn chậm 31%” hoặc “body rewrite luôn tăng 5 ms”: kết quả phụ thuộc phần cứng, payload, log backend, tracer, sampling, TLS, upstream và lượng đồng thời.

## 3. Chi phí của logging: năm tầng cần phân biệt

### 3.1. Access log

**Access log** thường là một dòng trên mỗi HTTP request, chứa method, path, status, duration hoặc bytes, tùy formatter/server. Nó hữu ích để phát hiện traffic/error ở ranh giới Gateway.

Đặc điểm:

- Có thể ghi một bản ghi cho **mỗi request**.
- Chi phí chủ yếu ở **format, queue, write và vận chuyển logs**.
- Ít tốn hơn body logging nếu chỉ chứa metadata có giới hạn.
- Vẫn có thể gây cardinality/lộ PII nếu log raw URL/query chứa token/email.
- Nếu sink bị nghẽn, appender hoặc stdout/container logging có thể gây backpressure lên request threads.

Access log không phải trace: nó không tự hiển thị cây Gateway → order → inventory.

### 3.2. Application log trong filters và business code

Ví dụ:

~~~java
log.info("route={} method={} status={}",
        routeId, method, status);
~~~

Một dòng có thể rẻ; nhưng nếu **mỗi filter** ghi 2–3 dòng cho mỗi request, tổng log events tăng theo số filter và RPS.

Giả sử 2.000 RPS × 6 bản ghi/request:

~~~text
2,000 requests/s × 6 log events/request
  = 12,000 log events/s

Nếu 1 event ≈ 400 bytes (chỉ là giả định):
  ≈ 4.8 MB/s raw log content, chưa tính framing/metadata/compression
~~~

Tính toán này chỉ là **ước lượng năng lực log pipeline**, không phải số liệu benchmark của Spring Cloud Gateway. Trong thực tế log format, JSON encoding, stdout driver, collector và index làm thay đổi byte count đáng kể.

### 3.3. Reactor Netty wiretap

**Wiretap** là cơ chế debug mức HTTP client/server connection của Reactor Netty. Khi dùng cấu hình/level phù hợp, nó có thể ghi dữ liệu network và thậm chí **nội dung bytes/headers/payload** tùy wiretap format.

Wiretap **không nên bật thường trực** trên Gateway production chịu tải vì:

- Rất nhiều log events ở tầng I/O.
- Chuyển đổi bytes → chuỗi/hex/log object tạo CPU và allocations.
- Logging có thể chạy gần event loop hoặc liên quan asynchronous queues, tăng nguy cơ latency.
- Có thể ghi HTTP Authorization, cookies, request/response body, PII.
- Mức tác động phụ thuộc logging levels/format; bật property thôi mà logger không ở level phù hợp có thể không tạo output mong đợi.

### 3.4. Full body logging

Body logging là mức rủi ro cao hơn access log:

- Phải quan sát/đọc nội dung payload, thường cần **cache hoặc copy** nếu pipeline vẫn phải chuyển tiếp body.
- Body lớn có thể chiếm bộ nhớ đáng kể ở số lượng requests đồng thời cao.
- Formatting bytes thành UTF-8/JSON có thể decode thêm lần nữa.
- Log sink nhận dữ liệu gần bằng kích thước request/response nhân theo lưu lượng.
- Chứa credential và PII; redaction **sau khi đã dump ra log** là quá muộn.

Trong Gateway, body logging không nên được xây bằng cách tự `subscribe()` vào request body rồi đọc bytes: reactive body thường là stream tiêu thụ có giới hạn, có thể bị cạn hoặc leak nếu code quản lý `DataBuffer` sai.

### 3.5. Structured logs

JSON logs hỗ trợ phân tích tốt nhưng cũng tiêu tốn CPU/bytes:

~~~json
{
  "service": "edge-gateway",
  "routeId": "orders-api",
  "method": "POST",
  "status": 201,
  "durationMs": 28,
  "traceId": "example-trace-id"
}
~~~

Đây là **schema minh họa**, không phải output Gateway tự phát. Với high-cardinality fields (raw path, trace ID, user ID), nên đặt chúng ở **log event đã bảo vệ**, không làm **metric labels**. Không cho rằng structured JSON luôn nhanh hoặc chậm hơn text log: phải đo formatter, async appender, collector và storage cụ thể.

## 4. Cấu hình logging Gateway WebFlux theo phiên bản

### 4.1. Gateway Server WebFlux 4.x: wiretap chỉ bật tạm thời

Trong một môi trường **local/staging cô lập**, những nhánh 4.x thường dùng:

~~~yaml
spring:
  cloud:
    gateway:
      httpserver:
        wiretap: true
      httpclient:
        wiretap: true

logging:
  level:
    reactor.netty: DEBUG
~~~

Các tên property và logger cần kiểm chứng theo Spring Cloud Gateway/Reactor Netty release chính xác. `reactor.netty: DEBUG` đặt rộng có thể ghi nhiều thông tin hơn dự kiến; có thể thu hẹp logger theo package/class mà version thực dùng.

**Chỉ dùng để điều tra trong thời gian ngắn**, với traffic test/synthetic. Không bật wiretap trên public production để tìm lỗi bằng cách đọc raw Authorization/body.

### 4.2. Gateway Server WebFlux 5.x: namespace mới

Tài liệu cấu hình Gateway 5.x liệt kê:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: true
          httpclient:
            wiretap: true

logging:
  level:
    reactor.netty: DEBUG
~~~

Dòng property mới được kiểm chứng trong tài liệu `spring.cloud.gateway.server.webflux.httpserver.wiretap` và `spring.cloud.gateway.server.webflux.httpclient.wiretap`.

**Không đặt cả namespace 4.x và 5.x** để hy vọng một trong hai hoạt động. Một prefix không được bind có thể làm benchmark “tắt wiretap” mà bạn tưởng đã bật, dẫn đến kết luận sai.

### 4.3. Reactor Netty access log là cấu hình khác wiretap

Với Reactor Netty HTTP server, thuộc tính system property đặc trưng là:

~~~text
-Dreactor.netty.http.server.accessLogEnabled=true
~~~

Ví dụ khi chạy JAR trong lab:

~~~bash
java -Dreactor.netty.http.server.accessLogEnabled=true -jar gateway.jar
~~~

System property nên được đặt **trước khi Reactor Netty HTTP server được tạo**. Đây **không phải** thuộc tính của `spring.cloud.gateway.httpclient.wiretap`. Access log và wiretap có phạm vi/mức chi tiết khác nhau.

Dùng Java process options phù hợp deployment; đừng chép một tùy chọn debug vào toàn bộ replicas production mà không có change approval, retention và bảo vệ dữ liệu.

### 4.4. Cấu hình bình thường nên như thế nào?

Một baseline an toàn hơn:

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: false
          httpclient:
            wiretap: false
          observability:
            enabled: true

logging:
  level:
    root: INFO
    reactor.netty: WARN
~~~

Đoạn này minh họa nhánh **Gateway Server WebFlux 5.x**, không phải mọi project phải đặt chính xác `root: INFO`. Quan trọng là **không bật debug network/body thường trực**, vẫn giữ metrics/observability được cấu hình có trách nhiệm.

Với production, có thể có **access logs metadata đã làm sạch** và **logs lỗi có sampling**; không nên tắt sạch log đến mức không thể điều tra sự cố.

## 5. Thiết kế log theo chi phí và nhu cầu vận hành

### 5.1. Log có cấu trúc tối thiểu

Thông tin thường đủ để điều tra route:

| Trường | Ví dụ | Ghi chú |
| --- | --- | --- |
| timestamp | UTC | Hỗ trợ đối chiếu |
| service/environment | edge-gateway / production | Không ghi secret |
| routeId | orders-api | ID ổn định |
| method | GET | Low-cardinality |
| route pattern | `/api/orders/**` | Tốt hơn raw user ID path |
| status/outcome | 201 / success | Nhóm status |
| duration | 28 ms | Có thể dùng metrics thay mỗi-log |
| traceId/spanId | Chuỗi identifier | Chỉ khi tracing scope hợp lệ |
| error category | timeout/connect/tls | Không log raw exception chứa secret |
| upstream group | ORDER-SERVICE | Không cần IP cá nhân hoặc URL nhạy cảm |

Không dump tất cả headers hay bodies khi mục tiêu chỉ là biết route nào bị chậm.

### 5.2. Log có điều kiện, không tạo string trước khi check level

Tránh:

~~~java
// PHẢN VÍ DỤ: chi phí serialize xảy ra trước lời gọi log.
log.debug("body=" + expensiveJsonSerialization(payload));
~~~

Dù DEBUG đang tắt, `expensiveJsonSerialization(payload)` **vẫn chạy** vì Java tính toán argument trước khi gọi logger.

Tốt hơn:

~~~java
if (log.isDebugEnabled()) {
    log.debug("route={} payloadSizeBytes={}",
            routeId, safeBodyLength);
}
~~~

Hãy ưu tiên **payload size** thay vì nội dung. Với dữ liệu phải ẩn, không truyền object nhạy cảm vào logger kể cả ở DEBUG; một chính sách debug bị bật nhầm có thể làm lộ.

Với SLF4J 2 fluent/lazy supplier, vẫn cần kiểm xem supplier có thực sự lazy theo logger implementation; đừng tạo full JSON `String` trước supplier rồi gọi nó là “lazy”.

### 5.3. Async logging: giảm blocking nhưng không miễn phí

Async appender có thể đưa việc format/write nặng khỏi request path. Tuy nhiên:

~~~text
Request/event loop
  -> enqueue log event
  -> bounded/unbounded queue
  -> async worker
  -> stdout/file/network collector
~~~

Có trade-offs:

- **Queue bounded:** có thể drop log khi đầy, làm thiếu audit/debug data.
- **Queue unbounded:** có thể tích lũy bộ nhớ và gây OOM.
- **Blocking enqueue:** vẫn có thể block event-loop khi queue đầy.
- **Exception/logging context capture:** có chi phí copy MDC/arguments.
- **On shutdown:** phải flush hợp lý nhưng không khóa request path vô hạn.

Async appender không làm chi phí tạo event/serialize fields tự biến mất. Nếu logs dùng cho **audit bắt buộc**, chính sách drop khác logs debug thông thường.

### 5.4. Sampling log

Một chiến lược thường tốt hơn full logging:

- Log **lỗi/timeout** có context đã redact với mức độ cần thiết.
- Log **metadata của một tỷ lệ requests thành công** được chọn ổn định.
- Duy trì metrics cho **toàn bộ traffic** nếu chi phí phù hợp.
- Cho phép tăng mức debug tạm thời trên **một replica/route**, có thời hạn.
- Không dùng user identity làm seed sampling không kiểm soát; xem xét fairness và privacy.

Sampling access logs **không giống tracing sampling**. Không suy rằng “1% log” sẽ cho 1% cùng những requests được sample spans nếu không có correlation strategy.

## 6. Ví dụ GlobalFilter đo duration: minh họa giới hạn của custom logging

Trong Gateway Server WebFlux, `GlobalFilter` tham gia **Gateway filter chain của route đã khớp**. Một ví dụ log metadata sau khi chain hoàn tất:

~~~java
package example.gateway.performance;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class MinimalRouteTimingFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(MinimalRouteTimingFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, GatewayFilterChain chain) {

        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long millis =
                                (System.nanoTime() - startedAt) / 1_000_000L;

                        Route route = exchange.getAttribute(
                                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
                        String id = route != null
                                ? route.getId() : "unknown";

                        if (log.isInfoEnabled()) {
                            log.info(
                                "route={} method={} status={} durationMs={} signal={}",
                                id,
                                exchange.getRequest().getMethod(),
                                exchange.getResponse().getStatusCode(),
                                millis,
                                signal);
                        }
                    });
        });
    }

    @Override
    public int getOrder() {
        return -10;
    }
}
~~~

**Điểm cần hiểu:**

1. `Mono.defer` đo khi publisher được subscribe, giảm nguy cơ tính thời gian trước execution thực.
2. `doFinally` chạy khi chain hoàn tất, lỗi hoặc bị cancel; `signal` giúp phân biệt termination.
3. `GatewayRoute`/route ID lấy từ exchange attribute, không dùng raw URL làm log label.
4. Không đọc body, không log token/cookie/query/PII.
5. `status` có thể `null` khi chưa có response status được đặt hoặc lỗi xảy ra sớm; không xem đó là 200.
6. `doFinally` là callback đồng bộ; **log sink chậm có thể làm tăng thời gian event-loop bận**.
7. Filter này chạy trong **route filter chain**, nên một request không match route hoặc bị Spring Security chặn trước Gateway có thể **không đi qua filter**.
8. Đây là **mẫu minh họa**, không thay thế Gateway/Micrometer built-in observation. Nếu đã có metrics/tracing tự động, thêm log từng request có thể đo cùng thông tin với chi phí cao hơn.

Trên production, thay vì thêm hàng loạt custom `GlobalFilter` chỉ để đo duration, ưu tiên các observation/metrics của framework, rồi chỉ thêm sự kiện cần thiết không được built-in cung cấp.

## 7. Chi phí của distributed tracing

### 7.1. Tracing thêm công việc gì?

Một trace qua Gateway và nhiều services có thể chứa:

~~~mermaid
flowchart TD
    C["Client"] --> G["Gateway SERVER span"]
    G --> GC["Gateway HTTP CLIENT span"]
    GC --> O["order-service SERVER span"]
    O --> IC["inventory HTTP CLIENT span"]
    IC --> I["inventory-service SERVER span"]
    G --> E["Exporter / Collector"]
    O --> E
    I --> E
~~~

Mỗi span có thể cần:

- Tạo identifiers hoặc tiếp nhận parent context.
- Ghi nhận timestamps, attributes, status, exception/event.
- Duy trì context qua reactive async boundaries.
- Inject `traceparent` vào outbound HTTP headers.
- Quyết định sampling.
- Serialize và gửi spans qua exporter (có thể batch).
- Queue và buffer chờ Collector/backend.

**Propagation và export là hai việc khác nhau.** Gateway có thể truyền W3C `traceparent` để downstream nối trace ngay cả khi một số spans không được export do sampler. Một trace có header hợp lệ cũng có thể không xuất hiện trong UI vì Collector bị lỗi hoặc queue bị drop.

### 7.2. Tracing overhead không phải con số hằng

Mức overhead phụ thuộc:

- Số spans/request và số hops.
- Sampling probability/parent-based sampling.
- Số attributes/events/links và kích thước string.
- Baggage/tracestate; số headers và payload bytes.
- Có exception stack trace đầy đủ trên spans hay không.
- SDK bridge: Micrometer Tracing/Brave/OpenTelemetry/Java agent.
- Exporter batch/queue/timeout, network tới Collector.
- Tracer context propagation qua Reactor.
- Thời điểm Collector chậm, mất mạng hoặc bị throttling.

Cấu hình `management.tracing.sampling.probability: 0.1` **không bảo đảm giảm 90% mọi overhead tracing**: propagation, context và một phần observation vẫn có thể xảy ra. Nó chủ yếu giảm **số sampled spans/export work** theo chính sách.

### 7.3. Có thể bật metrics nhưng không bật 100% traces

Một thiết kế hợp lý thường là:

| Tín hiệu | Mức bao phủ | Mục đích |
| --- | --- | --- |
| Metrics HTTP/route tổng hợp | Phần lớn/tất cả requests khi chi phí cho phép | SLO/RPS/status/latency |
| Error logs metadata | Theo error policy | Điều tra sự cố |
| Access logs | Chọn lọc/sampling | Correlation/audit hợp lý |
| Distributed traces | Sample có kiểm soát | Điều tra request/hop chậm |
| Wiretap | Chỉ debug ngắn hạn | Chẩn đoán network/protocol |
| Full body dump | Tránh, chỉ synthetic/redacted khi thật cần | Điều tra một contract lỗi |

Khi sampling, **không tính SLO p99 từ tập spans bị lấy mẫu tùy ý** mà không hiểu bias. Timers/metrics được thu thập theo chính sách riêng phù hợp hơn cho đánh giá toàn bộ traffic.

## 8. Cấu hình tracing theo Spring Boot 3.5 và 4.x

### 8.1. Spring Boot 3.5 với Micrometer Tracing và OTLP

Trong dự án Spring Boot 3.5 có Spring Cloud Gateway 4.x tương thích, một tổ hợp Maven thông dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Cấu hình minh họa trong **lab**:

~~~yaml
spring:
  application:
    name: edge-gateway

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

`probability: 1.0` chỉ phục vụ **lab có lưu lượng nhỏ**. Trên production cần thử các tỷ lệ thấp hơn, cân nhắc capacity/retention, kiểm tra parent-based sampling và đường export OTLP.

`localhost:4318` trong container chỉ phù hợp khi Collector nằm tại loopback của đúng network namespace. Trong Kubernetes thường cần Service DNS/Collector agent/sidecar theo kiến trúc.

### 8.2. Spring Boot 4.x với OpenTelemetry starter

Với Spring Boot 4.x, tài liệu chính thức giới thiệu:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Cấu hình minh họa theo nhóm property mới:

~~~yaml
spring:
  application:
    name: edge-gateway

management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    otlp:
      endpoint: http://otel-collector:4318
~~~

Hoặc dùng trace-specific OTLP exporter properties `management.opentelemetry.tracing.export.otlp.*` khi version hỗ trợ và cần cấu hình riêng. **Không hoán đổi tùy ý** với `management.otlp.tracing.endpoint` của Boot 3.x.

Đặt sampling `0.1` ở đây là **ví dụ ngân sách tracing**, không phải đề xuất bắt buộc cho mọi traffic. Với upstream nhiều hops, tail sampling hoặc chính sách error trace có thể phù hợp nhưng cần cấu hình Collector đúng.

### 8.3. Cấu hình tracing không tự là bật Gateway routing metrics

Ở Gateway WebFlux 5.x, tài liệu cấu hình có các nhóm:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          observability:
            enabled: true
          metrics:
            enabled: true
            path-tags:
              enabled: false
~~~

`observability.enabled` điều khiển phần tích hợp Micrometer của Gateway; `metrics.enabled` điều khiển Gateway route metrics khi infrastructure phù hợp. **Không cần bật raw path tag** để đo hiệu năng: path có ID động gây cardinality cao.

Với Gateway 4.x, các property có thể nằm dưới `spring.cloud.gateway.observability.*` và `spring.cloud.gateway.metrics.*`. Luôn đọc `configprops` tương ứng release; một property đặt sai vị trí dễ khiến so sánh “tracing on/off” không thực sự thay đổi state.

## 9. Sampling, exporter và nguy cơ queue contention

### 9.1. Mối liên hệ giữa sampling và span volume

Giả sử một request có trung bình 5 sampled spans trên toàn hệ thống, lưu lượng 1.000 RPS:

~~~text
Nếu sample 100% và mỗi request thực sự tạo 5 spans:
  1,000 requests/s × 5 spans/request = 5,000 spans/s

Nếu sample khoảng 10% theo policy đơn giản:
  ~500 sampled spans/s
~~~

Đây là **ước lượng minh họa**, không phải throughput đã đo. Span count sẽ khác nếu circuit breaker chặn, retry tạo thêm attempts, một số service chưa instrument, hoặc parent sampler/tail sampler có chính sách khác.

### 9.2. Exporter không được biến Gateway thành điểm nghẽn

Một exporter thường có hàng đợi/batching và worker riêng, nhưng vẫn có giới hạn. Khi Collector chậm:

- Queue có thể tích lũy sampled spans.
- Export timeout và retry ở telemetry pipeline tiêu thụ network/CPU.
- Queue đầy có thể **drop spans**, tạo khoảng trống trace UI.
- Nếu exporter/custom instrumentation có hành vi blocking, request latency có thể bị ảnh hưởng.
- Mức ảnh hưởng phụ thuộc SDK/exporter; không tuyên bố tất cả exporter đều block Gateway event loop.

Cần giám sát dropped spans/export failures, queue utilization, CPU/memory và **mức gián đoạn request** khi thử tắt Collector.

### 9.3. Tail-based sampling

Tail sampling ở Collector có thể giữ traces có lỗi hoặc latency cao sau khi đã xem spans. Nó hữu ích khi cần tra cứu rare errors, nhưng:

- Collector phải có đủ dữ liệu để ra quyết định.
- Buffering/timers/HA/sharding theo trace ID có chi phí.
- Nếu ingress/tracer đã drop spans ở đầu nguồn, Collector **không thể phục hồi những spans chưa từng được xuất**.
- Traces quá lớn và burst traffic có thể gây memory pressure ở Collector.

**Không mặc định bật tail sampling sẽ giảm overhead tạo spans ở Gateway**: chi phí instrumentation/export tới Collector vẫn có thể phát sinh trước quyết định cuối.

## 10. Reactor Context: ranh giới giữa tracing đúng và overhead không cần thiết

Gateway WebFlux dùng **reactive, non-blocking execution**. Một request có thể chuyển threads; nếu tracing/logging code tự dựa vào `ThreadLocal` hoặc `MDC` mà không có context propagation hợp lệ, log correlation có thể sai.

Ví dụ phản tác dụng:

~~~java
MDC.put("traceId", requestTraceId);
// Tiếp tục reactive chain nhưng quên cleanup hoặc đổi thread.
return chain.filter(exchange);
~~~

Vấn đề:

- `MDC` thường gắn với thread; Reactor pipeline có thể chạy trên thread khác.
- `ThreadLocal` không tự thể hiện logical subscriber context.
- Nếu không cleanup, một event loop thread dùng lại có thể mang metadata từ request khác.
- Gắn thêm logic manual scope/copy context ở mọi filter có chi phí và dễ lỗi.

Cách đúng là **dùng Micrometer Tracing/Reactor Context Propagation** theo framework/version, để instrumented server/client scopes và logging correlation được quản lý thống nhất.

### 10.1. Đừng `subscribe()` rời chỉ để log trace

~~~java
// PHẢN VÍ DỤ: subscription rời, không gắn với lifecycle chính.
someWebClient.get()
    .uri("/debug")
    .retrieve()
    .bodyToMono(String.class)
    .subscribe();
~~~

Lỗi có thể gồm mất parent trace, request phụ ngoài ý muốn, cancellation/error không được quản lý. Với side work thật sự cần làm, compose `Mono` vào chain và có timeout/authorization/observability riêng.

### 10.2. Đừng blocking event loop để gửi log/trace

Không gọi:

~~~java
// PHẢN VÍ DỤ: không làm thế trên Reactor Netty event-loop.
String data = blockingHttpClient.call();
Files.writeString(logPath, data);
~~~

trong `GlobalFilter` rồi nghĩ rằng vì Gateway hỗ trợ Reactor, code tự trở thành non-blocking. Blocking I/O, đồng bộ JSON serialization nặng hoặc cryptographic work quá lớn có thể chặn request khác dùng cùng event-loop thread.

Nếu bắt buộc làm blocking work nhỏ và có giới hạn, tách nó sang scheduler/executor thích hợp, kèm queue concurrency bounds và đo overhead. **`boundedElastic` không phải phép màu** để che mọi CPU-bound JSON transform hoặc output unbounded.

## 11. Biến đổi body: chức năng nhỏ, chi phí lớn

### 11.1. Stream thuần và body rewrite khác nhau

Một route chỉ sửa path/header có thể chuyển body theo streaming:

~~~text
Inbound DataBuffer stream
      │
      ├─ chọn route
      ├─ sửa path/header
      └─ gửi DataBuffer đến upstream
~~~

Khi thêm `ModifyRequestBody` hay `ModifyResponseBody`:

~~~text
Inbound byte stream
      │
      ├─ read/aggregate/decode theo body readers và target type
      ├─ tạo String/DTO/JsonNode
      ├─ transformation
      ├─ encode trở lại bytes
      └─ gửi stream/buffer mới đến upstream/client
~~~

Cơ chế rewrite thường cần có **đủ body để chuyển kiểu và biến đổi**. Chi phí có thể bao gồm:

- Read/aggregate buffers và tăng peak live bytes.
- Decode charset và parse JSON.
- Tạo object graph và thực thi business mapping.
- Serialize và encode.
- Recompute/loại bỏ `Content-Length` khi body đổi.
- Pressure lên heap, direct memory, GC và Netty allocator.
- Delay của request/response cho đến khi có dữ liệu để rewrite.

**Không giả định mọi filter đều luôn giữ toàn bộ body**: exact implementation phụ thuộc filter, codec và streaming strategy. Nhưng body rewrite qua kiểu `String`/DTO là một dấu hiệu cần lập ngân sách buffering và concurrency rõ ràng.

### 11.2. Bài toán bộ nhớ theo requests đồng thời

Giả sử **ước lượng lý thuyết**, không phải số đo JVM thật:

~~~text
Requests đồng thời:        500
Kích thước body mỗi request: 1 MiB
Số bản sao/body-equivalent còn sống đồng thời: 2

Ước lượng live payload:
  500 × 1 MiB × 2 = 1,000 MiB (~0.98 GiB)

Chưa tính:
  + object graph / char[] / JsonNode / serialization buffers
  + Netty direct pooled buffers
  + request/response metadata
  + app heap còn lại và GC overhead
~~~

Một Gateway có heap 1 GiB không thể tự coi cấu hình trên là an toàn. Trong môi trường thật, số copies không cố định, payload size có đuôi phân phối và requests có thể được xử lý với nhiều dạng byte/char buffers. **Hãy đo peak heap + direct memory + GC**, không lấy phép nhân làm giới hạn chính xác.

### 11.3. Vì sao p99 chịu ảnh hưởng nặng?

Ở tải thấp, parse một JSON 100 KiB có thể nhanh. Ở tải cao, nhiều body cùng chờ xử lý sẽ:

- Tăng allocation rate.
- Tăng thời gian GC và pressure bộ nhớ.
- Tạo hàng đợi ở HTTP client pool hoặc scheduler.
- Làm Netty event loops bận nếu transform CPU-heavy đặt sai chỗ.
- Đẩy requests khác vốn có payload nhỏ vào tail latency cao.

Do đó, benchmark phải phối hợp **payload size × concurrency × RPS**, không chỉ gọi một lần với JSON nhỏ.

## 12. Java DSL ví dụ cho ModifyRequestBody và ModifyResponseBody

Với Gateway **Server WebFlux**, hai filter này được tài liệu chính thức mô tả là **chỉ cấu hình qua Java DSL**, không phải shortcut YAML chung như `StripPrefix=1`.

Ví dụ học tập cố ý biến đổi **text/plain** để dễ nhìn chi phí decode/encode:

~~~java
package example.gateway.performance;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.http.MediaType;
import reactor.core.publisher.Mono;

@Configuration
public class BodyTransformationRoutes {

    @Bean
    RouteLocator transformDemo(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("text-transform-demo", r -> r
                    .path("/lab/transform/**")
                    .filters(f -> f
                        .stripPrefix(1)
                        .modifyRequestBody(
                            String.class,
                            String.class,
                            MediaType.TEXT_PLAIN_VALUE,
                            (exchange, body) -> body == null
                                ? Mono.empty()
                                : Mono.just(body.toUpperCase(Locale.ROOT)))
                        .modifyResponseBody(
                            String.class,
                            String.class,
                            (exchange, body) -> body == null
                                ? Mono.empty()
                                : Mono.just("gateway:" + body)))
                    .uri("http://localhost:8081"))
                .build();
    }
}
~~~

**Chỉ dùng trên endpoint lab**, không áp dụng upper-case arbitrary payload trên production:

- Request có body text `hello` sẽ được biến thành `HELLO` trước upstream.
- Response text `ok` từ upstream được đổi thành `gateway:ok` trước client.
- Codec/Content-Type phải được kiểm tra bằng test thật; ví dụ giả định `text/plain` hợp lệ.
- Trường hợp body **không tồn tại**, rewrite callback có thể nhận `null`; trả `Mono.empty()` để giữ trạng thái không có body.
- `modifyRequestBody` có `newContentType`, giúp khai báo representation đầu ra; `modifyResponseBody` dùng các writer/cấu hình media type tương ứng.
- Endpoint có response 204/HEAD hoặc compression cần test riêng; không mặc định rewrite tạo body ở mọi status.
- Dù chỉ transform String, Gateway có thể cần decode/encode và tạo object mới; hiệu năng phải đo ở body sizes khác nhau.

Ví dụ này **không ghi request/response body vào log**. Nếu vừa biến đổi body vừa log nó, bạn có thể tạo thêm một hoặc nhiều lần decode/copy và tăng rủi ro lộ dữ liệu.

### 12.1. JSON transformation có nhiều chi phí hơn

Một filter `modifyRequestBody(String.class, DomainDto.class, APPLICATION_JSON_VALUE, rewriteFn)` có thể:

1. Decode input `String`.
2. Parse/map thành object `DomainDto`.
3. Transform fields.
4. Serialize thành JSON.
5. Encode bytes.

**Không chọn `String.class` rồi parse JSON thủ công trong mỗi filter chỉ vì dễ viết**. Nếu codec và loại body đã được thiết kế tốt, chọn type hợp lý để hạn chế bước dư. Tuy nhiên, codec JSON vẫn có allocation và validation cost; cần đo.

Nếu chỉ muốn **xóa/thêm một request header** hoặc rewrite path, dùng header/path filter thay vì parse toàn bộ body. Tách routing concern khỏi nghiệp vụ nếu có thể.

### 12.2. Quy tắc nội dung rỗng

Khi body vắng mặt, `null`, `Mono.empty()` và JSON literal `null` **không nhất thiết tương đương**. Đừng dùng `Mono.just(null)` (Reactor không cho phép giá trị null). Với contract REST, hãy test:

- Không có body.
- Body length 0.
- Body chứa chuỗi JSON `null`.
- JSON object `{}`.
- Content-Type không phù hợp.
- Body vượt size limit.

Không tự rewrite body của request bị chặn trước routing, chẳng hạn 401 do Spring Security, như thể route filter luôn được chạy.

## 13. DataBuffer, pooling, backpressure và giới hạn bộ nhớ

### 13.1. DataBuffer không phải byte[] không quản lý

Spring WebFlux đại diện body streaming bằng `DataBuffer`, có implementation dựa trên buffer pooling của Reactor Netty. Một custom filter đọc body phải tuân thủ **sở hữu và giải phóng bộ nhớ**, nếu không có thể:

- Đọc một body stream rồi upstream nhận body rỗng.
- Retain buffer quá lâu, tăng direct memory.
- Double release hoặc dùng buffer sau khi đã giải phóng.
- Thiếu backpressure gây queue vô hạn.
- Cache payload lớn rồi bị OOM.

Tài liệu Spring WebFlux có `DataBufferUtils`, `DataBufferLimitException` và các cơ chế decoding/aggregation hỗ trợ khi cần. **Không tự gọi `DataBufferUtils.join()` rồi giữ reference vô hạn** chỉ để log request.

### 13.2. Phản ví dụ: “đọc body để debug”

~~~java
// PHẢN VÍ DỤ — KHÔNG dùng trong Gateway production.
exchange.getRequest().getBody()
    .subscribe(buffer -> {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        log.info("body=" + new String(bytes));
    });

return chain.filter(exchange);
~~~

Vấn đề:

- `subscribe()` tách riêng khỏi lifecycle chính của request.
- Có thể cạnh tranh/tiêu thụ stream body mà downstream cần.
- Thiếu charset, size limit và redaction.
- Có thể không release pooled buffer đúng.
- Logging large bytes đồng bộ.
- Không propagate cancellation/errors theo chain.

Cách tốt hơn thường là **không log body**. Nếu phải kiểm tra payload, dùng mock upstream trong integration test hoặc một component debug **được thiết kế có giới hạn/redaction/test** với scope và thời hạn rõ ràng.

### 13.3. Giới hạn kích thước đúng tầng

Có nhiều giới hạn khác nhau:

| Cơ chế | Bảo vệ |
| --- | --- |
| Gateway `RequestSize` filter | Từ chối request vượt ngưỡng cấu hình ở route |
| Spring WebFlux codec `maxInMemorySize` | Giới hạn aggregation/decoding cho một số operations |
| Ingress/API load balancer limit | Chặn tải quá lớn trước Gateway |
| Backend size limit | Bảo vệ service đích |
| Netty connection/pool/timeouts | Giới hạn tài nguyên transport và thời gian |
| Rate limiting / concurrency limit | Giảm áp lực tổng requests |

Một giới hạn **không thay tất cả giới hạn còn lại**. Đặt `maxInMemorySize` cao để “sửa lỗi 413” có thể làm tăng OOM risk khi body transformations xảy ra đồng thời.

### 13.4. Backpressure không bảo đảm an toàn khi buffer không giới hạn

Reactor hỗ trợ backpressure, nhưng nếu filter:

- Dùng `collectList()` trên stream không giới hạn.
- Dùng queue unbounded.
- Cache mọi response body trong map.
- Gọi `flatMap` với concurrency quá lớn.
- Dùng `publishOn` không kiểm soát backlog.

thì vẫn có thể làm memory tăng mạnh. “Reactive” không đồng nghĩa “không thể OOM”; phải thiết kế **giới hạn hữu hạn** ở kích thước, số requests đồng thời và thời gian chờ.

## 14. Kết hợp body rewrite với Retry, compression và security

### 14.1. Retry có thể tăng số lần xử lý payload

Một `POST` có body được retry có thể yêu cầu **cache/replay** nội dung body. Chi phí có thể gồm:

- Bộ đệm body để replay.
- Re-execution của filters nằm trong phần được retry.
- Outbound bytes tăng theo attempts.
- Backend side effects tăng nếu không có idempotency.

Kể cả khi Retry chỉ áp dụng cho `GET`, response body buffering/filtering có thể làm tăng latency ở mỗi attempt. Với POST orders/payment, **không bật retry một cách máy móc**; cần `Idempotency-Key`, backend dedup và kiểm thử timeout-after-commit.

### 14.2. Compression thay đổi cách so sánh body

Nếu upstream trả `gzip`, wire bytes có thể nhỏ hơn body đã giải nén. Khi `ModifyResponseBody` đọc text/JSON:

- Codec có thể giải nén hoặc không theo HTTP client configuration.
- Body rewrite có thể cần re-encode và điều chỉnh Content-Encoding/Content-Length.
- Việc decode rồi re-encode tạo thêm CPU/memory.
- Chunk boundaries không được đảm bảo giữ nguyên qua proxy.

Test cần phân biệt **wire bytes** và **semantic JSON/body**. Không so gzip ciphertext với UTF-8 plaintext rồi kết luận filter làm hỏng body.

### 14.3. Body transformation khác streaming proxy

Với file upload/download lớn, một route **chỉ chuyển tiếp** thường hợp lý hơn route transform body thành `String` hoặc DTO.

Với webhook đã ký chữ ký, thay một byte/whitespace có thể khiến signature verification ở backend thất bại. Không rewrite JSON đã ký nếu contract cần bảo toàn bytes chính xác.

### 14.4. PII và nội dung nhạy cảm

**Đừng bật request/response body logging để đo hiệu năng body transforms.** Trong benchmark có thể dùng payload giả và kiểm checksum/counters; không cần log nội dung thật.

Một trường `Authorization`, cookie, password, refresh token, số thẻ hoặc raw PII đi vào log/trace sẽ tạo rủi ro dữ liệu nghiêm trọng. “Chỉ DEBUG” không tự biến dữ liệu thành an toàn nếu log aggregator, CI artifacts và retention vẫn ghi lại.

## 15. Tác động kết hợp: logging + tracing + body transform

Ba cơ chế có thể **nhân tác động** chứ không chỉ cộng:

~~~mermaid
flowchart TD
    R["Request vào Gateway"] --> L["Log metadata / wiretap"]
    R --> T["Tracing context & sampled spans"]
    R --> B["Body decode / rewrite / encode"]
    L --> Q["Log queue / stdout / collector"]
    T --> X["Span exporter / OTLP collector"]
    B --> M["Heap + direct buffers / GC"]
    Q --> S["CPU / network / I/O pressure"]
    X --> S
    M --> S
    S --> P["Queueing / p95 p99 latency"]
~~~

Ví dụ:

1. Body transform tạo String/DTO mới.
2. Một debug logger serialize DTO để log toàn payload.
3. Tracing instrumentation ghi một số attributes quá lớn.
4. Log collector và OTLP exporter cùng sử dụng network/CPU.
5. GC và cgroup CPU throttling tăng.
6. Request từ các routes **không dùng body transform** cũng có thể chậm vì tài nguyên Gateway dùng chung.

Do đó một benchmark “bật cả ba và so với baseline” chỉ xác nhận **tác động kết hợp**, chưa giúp biết phần nào gây hại. Cần **ablation study**: bật/tắt từng yếu tố.

### 15.1. Ma trận thử nghiệm có đối chứng

| Nhóm | Logging | Tracing | Body transform | Mục đích |
| --- | --- | --- | --- | --- |
| A | Metadata tối thiểu | Tắt export spans hoặc sampling tối thiểu | Không | Baseline |
| B | Access log metadata | Như A | Không | Chi phí access log |
| C | Application log 1 event/request | Như A | Không | Chi phí per-request log |
| D | Wiretap trong lab | Như A | Không | Chi phí protocol debug |
| E | Như A | Sampling 10% | Không | Chi phí tracing mức thấp |
| F | Như A | Sampling 100% | Không | Chi phí tracing lab cường độ cao |
| G | Như A | Như A | Rewrite body nhỏ | Chi phí transformation |
| H | Như A | Như A | Rewrite body lớn | Ảnh hưởng kích thước payload |
| I | Log metadata | Sampling 10% | Rewrite body | Tác động kết hợp production-like |
| J | Wiretap | Sampling 100% | Rewrite body lớn | **Stress/debug lab**, không phải profile production |

Trong các nhóm A–J, cần ghi rõ baseline thật sự có những observations nào. “Tắt export spans” và “tắt toàn bộ Micrometer Observation” **không giống nhau**; nếu thay nhiều biến ở một nhóm, kết quả khó diễn giải.

## 16. Quy trình benchmark đúng: từ baseline đến kết luận

### 16.1. Giữ nguyên các biến bên ngoài

Cố định hoặc ghi nhận:

- Spring Boot/Cloud Gateway version, JDK, GC, container image.
- Số CPU cores, cgroup quota, heap/direct memory, pod limits.
- Số Gateway replicas và CPU affinity khi có.
- Upstream mock/service latency, body size, HTTP keep-alive, TLS mode.
- Concurrency, arrival rate, request mix (GET/POST, size distribution).
- Log sink (stdout/file/async queue), collector/backend topology.
- Sampling probability và số spans/request.
- HTTP client pool, max connections, pending acquire timeout.
- Security, rate limiting, Retry, circuit breaker behavior.
- Warm-up duration và thời lượng steady-state.
- Nếu có Kubernetes, node contention, HPA, throttling, autoscaling policy.

Không so sánh A trên laptop và B trên pod production rồi kết luận B chậm vì tracing.

### 16.2. Test theo lưu lượng đến, không chỉ số users

Với closed-loop benchmark, khi Gateway chậm, người dùng ảo có thể chờ lâu hơn và **vô tình gửi ít request hơn**, khiến kết quả che đi quá tải.

Với open-loop/constant-arrival-rate, load generator cố giữ một arrival rate đã xác định. Nó thường hữu ích để quan sát queueing/p99 dưới tải tăng. Tuy nhiên cần xác minh generator có đủ VUs/connections/CPU để thực sự đạt target RPS.

### 16.3. Một k6 script minh họa

Trong project lab có thể dùng k6, với `BASE_URL` từ environment:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: 200,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 100,
      maxVUs: 400
    }
  }
};

export default function () {
  const response = http.get(
    `${__ENV.BASE_URL || "http://localhost:8080"}/api/catalog/42`,
    { headers: { "X-Benchmark-Case": "baseline" } }
  );

  check(response, {
    "expected success": (r) => r.status === 200
  });
}
~~~

Mã trên là **ví dụ tạo tải**, chưa chạy trong bài. Chỉ dùng với Gateway/upstream **do bạn sở hữu** trong lab/staging; không dùng để gây tải lớn lên public services. Kết quả k6 phải được kết hợp CPU/GC/Netty/Collector metrics để phân biệt bottleneck.

Đối với body transform, tạo thêm scenario POST **payload có kích thước phân phối rõ** (ví dụ 1 KiB, 32 KiB, 256 KiB, 1 MiB) và test request body integrity. Không gắn payload production có PII vào test script.

### 16.4. Các pha đo

1. **Warm-up:** chờ JIT, pool connections, caches ổn định; không dùng dữ liệu warm-up làm kết luận.
2. **Low load:** xác nhận correctness và overhead khi chưa saturation.
3. **Steady load:** đo p50/p95/p99 ở RPS mục tiêu.
4. **High load:** tăng RPS đến khi error rate/latency vi phạm SLO.
5. **Burst load:** kiểm tra queue/log exporter/spike.
6. **Fault:** Collector offline, log collector chậm, upstream timeout.
7. **Recovery:** log queue và buffer có xả đúng, heap có trở lại baseline không.
8. **Repeat:** chạy nhiều vòng, xen kẽ A/B để giảm bias do nhiệt/JIT/node contention.

### 16.5. Ghi kết quả với cùng một mẫu

| Trường | Cần báo cáo |
| --- | --- |
| Test ID / commit / image | Build được test |
| Scenario | A/B/C… và cấu hình logging/tracing/body |
| Request mix | GET/POST, payload sizes, gzip, auth |
| Offered RPS / achieved RPS | Load generator muốn gửi vs thực sự gửi |
| p50, p95, p99 | Latency phía client |
| Error/timeout rate | Theo status/exception |
| CPU / throttling | Gateway và Collector |
| Heap, direct memory, allocation rate | Body buffering/Netty |
| GC pause/count | Memory pressure |
| Log events/s và dropped | Logging |
| Sampled spans/s và exporter drops | Tracing |
| Upstream p95/p99 | Để tách bottleneck backend |
| Notes | JIT warm-up, retries, anomalies |

Không chỉ ghi “k6 đạt 200 RPS”. Nếu load generator target 500 nhưng chỉ đạt 310 vì hết VUs, **đã thay đổi tải thực** giữa hai nhóm; so sánh độ trễ phải xử lý sai lệch đó.

## 17. Các chỉ số nên xem bằng Micrometer/Actuator

Spring Cloud Gateway Server WebFlux và Spring Boot/Micrometer cung cấp các quan sát HTTP và Gateway metrics khi phụ thuộc, cấu hình và observation infrastructure phù hợp.

Ví dụ thường gặp:

| Signal | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `http.server.requests` | Timer/status inbound HTTP server | Không chỉ riêng Gateway routing |
| `http.client.requests` | HTTP client outbound observations | Có thể gồm Gateway outbound HTTP |
| `spring.cloud.gateway.requests` | Route-level Gateway timer theo version | Cần Gateway metrics filter/integration |
| Reactor Netty metrics | Connections, data, resource status | Tên cụ thể phụ thuộc Reactor Netty/Micrometer |
| JVM GC/memory/CPU | Heap, pools, GC pauses | Nhớ direct/pooled buffer |
| Log queue metrics | Queue size/drops nếu appender hỗ trợ | Không tự có trong mọi logging backend |
| OTel exporter metrics | Export success/failure/drops | Theo SDK/Collector |
| Custom body transform timer | Thời gian decode/rewrite/encode | Tên do dự án tự instrument |
| Custom payload-size histogram | Kích thước input/output | Không log raw body |

Đối với histogram/SLO quantiles, Prometheus summaries và histograms có trade-offs. p95/p99 có thể được tổng hợp ở tầng **metrics backend** qua histogram buckets phù hợp; một giá trị p99 từ một instance không thể luôn cộng trung bình thành p99 của cả cụm.

### 17.1. Không bật metric tags có cardinality vô hạn

Không dùng các trường sau làm metric label:

- Raw `/api/orders/123456` và mọi order ID.
- `traceId`/`spanId`/`X-Request-Id`.
- Access token, session ID, email, phone.
- Full URI upstream có query động.
- Request body, JSON fields chứa dữ liệu user.

Dùng **route ID** như `orders-api`, status/outcome, HTTP method và service group có kiểm soát. Khi cần truy vết một request, dùng logs/traces bảo vệ thay vì làm nổ số lượng Prometheus time series.

## 18. Body transform và performance tests phải đi cùng correctness tests

Một tối ưu “nhanh hơn” nhưng làm mất body hoặc sửa status là **regression**, không phải cải thiện.

### 18.1. Test contract HTTP qua mock upstream

Thiết kế:

~~~mermaid
flowchart LR
    TC["WebTestClient / HTTP test"] --> GW["Gateway Server WebFlux<br/>RANDOM_PORT"]
    GW --> MOCK["MockWebServer<br/>ephemeral port"]
    MOCK -->|RecordedRequest| ASSERT["Assert method/path/headers/body"]
    GW -->|Response| TC
    TC --> CHECK["Assert status/headers/body"]
~~~

Với route body transform, test phải khẳng định:

- Path `StripPrefix`/`RewritePath` vẫn đúng.
- Request Content-Type/Content-Length không bị sai sau rewrite.
- Backend nhận transformed payload hợp lệ.
- Response body/status/header sau rewrite đúng.
- Missing body hoặc 204 được xử lý đúng.
- No-route/401/429 không vô tình chạy body filter.
- Retry không tăng attempts ngoài mong muốn.
- Streaming lớn không bị cache không kiểm soát.

### 18.2. Ví dụ phép thử payload

| Test | Input | Expectation |
| --- | --- | --- |
| B1 | POST text 1 KiB | Body transform đúng |
| B2 | POST JSON 32 KiB | Schema/charset đúng |
| B3 | POST không body | Không sinh body ngoài contract |
| B4 | JSON literal `null` | Không nhầm missing body |
| B5 | POST 1 MiB | Bộ nhớ, status và timeout theo giới hạn |
| B6 | Binary upload | Không chuyển nhầm thành String |
| B7 | 204 upstream response | Không tạo body ở status 204 |
| B8 | gzip upstream response | Không double compress, client decode đúng |
| B9 | Retry GET | Attempts đúng; no extra body copies ngoài thiết kế |
| B10 | Timeout sau upstream commit | Không replay POST tạo side effect |
| B11 | Client disconnect | Cancellation/cleanup đúng |
| B12 | Request bị 401/403/429 | Chặn đúng, không có outbound call |
| B13 | Wiretap bị bật | Test/lab không dùng secret thật và có cleanup logs |
| B14 | Collector mất kết nối | Request nghiệp vụ vẫn theo policy, theo dõi span drops |

### 18.3. Không dùng chính logging filter đang benchmark để xác minh body

Nếu benchmark ảnh hưởng của body logging, mà assertion yêu cầu raw body từ log được viết bởi chính filter đó, bạn dễ có **measurement-induced overhead** và phụ thuộc một component đang gây vấn đề.

Hãy dùng mock backend ghi request trong test correctness, còn benchmark performance tắt chi tiết mock logs hoặc dùng controlled upstream response tối thiểu. Tách **đo correctness** và **đo throughput** nhưng dùng cùng hợp đồng route/version.

## 19. Bottleneck đặc thù của từng cấu hình

### 19.1. Bật wiretap, CPU tăng và p99 xấu đi

Giả thuyết:

- Formatting wire bytes làm CPU tăng.
- Logging queue/sink không theo kịp RPS.
- Event-loop phải xử lý thêm nhiều callback.
- Container stdout bị chặn hoặc agent throttling.

Kiểm tra:

1. Xác nhận wiretap thực sự bật theo namespace/log level.
2. So logs/sec, CPU, event-loop lag, p99, dropped log events.
3. Giữ upstream latency giống hệt baseline.
4. Tắt wiretap và đo lại trong cùng môi trường.
5. Dùng network-level captures **có bảo vệ** hoặc synthetic traffic nếu cần debug tiếp, không bật toàn bộ production.

### 19.2. Bật tracing 100%, Collector đầy hoặc mất kết nối

Giả thuyết:

- Span serialization/queue/export tăng CPU/network.
- Collector/OTLP backend chậm, queue dồn.
- Exception attrs quá nhiều.
- Service tạo trùng spans do agent + bridge cùng instrument.

Kiểm tra:

1. Spans per request thực tế.
2. Sampling/exporter configuration.
3. Queue/dropped/export failure metrics.
4. SDK/collector CPU và memory.
5. Test Collector offline có deadline.
6. Kiểm rằng Gateway không block request chờ export.

Không dùng hành động “tắt mọi tracing” như giải pháp lâu dài nếu nó làm mất khả năng điều tra; có thể giảm sampling, giới hạn attributes, sửa exporter hoặc scaling Collector.

### 19.3. Thêm ModifyResponseBody, heap tăng theo payload

Giả thuyết:

- Decode/encode `String`/DTO nhiều lần.
- Buffering response phá streaming.
- GC overhead tăng.
- Một số requests bị timeout khi concurrent large responses.

Kiểm tra:

1. Histogram body sizes (không log raw data).
2. Live heap, allocation rate, direct memory.
3. GC pauses, buffer leak warnings.
4. p95/p99 theo kích thước payload.
5. Test bỏ body transformation chỉ trên lab route.
6. Với response lớn, cân nhắc transformation tại backend (nơi hiểu schema) hoặc streaming-capable design nếu chức năng yêu cầu.

### 19.4. Không thấy heap tăng nhưng pod bị OOMKilled

Gateway WebFlux dùng **Netty direct/pooled buffers** ngoài Java heap. Container memory gồm heap và **native/direct memory**, thread stacks, code/cache, metaspace, memory mapped files và các thành phần khác.

Kiểm tra:

- `jvm.memory.*` và buffer pools nếu được instrument.
- Native Memory Tracking khi khả thi.
- Process/container RSS và cgroup memory.
- Netty resource leak diagnostics theo môi trường.
- Requests in flight, body sizes, connection pool backlog.

Không chỉ tăng `-Xmx` để giải quyết OOM nếu pod memory limit không đủ cho direct memory hoặc nếu có buffer leak.

### 19.5. Tăng RPS nhưng lỗi 429/503 nhiều hơn

Một config có thể tăng số requests được nhận nhưng giảm số requests **thành công**. Nếu rate limiter hoặc LoadBalancer báo 429/503, chỉ đo throughput toàn bộ HTTP responses sẽ gây hiểu lầm.

Đo:

- Successful RPS theo business outcome.
- 4xx/5xx và upstream attempts.
- Backend p99, saturation, pool occupancy.
- Retry amplification.
- Rate-limit policy/quotas.

**Không tăng retry và rate limit vô tội vạ** để “tối ưu Gateway”; áp lực có thể chỉ chuyển từ Gateway sang upstream.

## 20. Thiết kế giới hạn theo payload và concurrency

### 20.1. Giới hạn kích thước request

Với route chỉ phục vụ JSON nhỏ, có thể dùng filter `RequestSize` và ingress limit. Ví dụ:

~~~yaml
# Minh họa route WebFlux 5.x, cần kiểm đúng release.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: small-json-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - name: RequestSize
                  args:
                    maxSize: 2MB
~~~

Chú ý:

- `RequestSize` trả từ chối theo filter contract khi request vượt giới hạn, thường là `413 Payload Too Large`.
- Không đồng nghĩa mọi body transformation sẽ chỉ dùng tối đa 2 MiB RAM: concurrency, copies, codec và response body vẫn có thể lớn.
- Codec aggregation limits và size limit ở ingress/backend phải được đặt theo loại endpoint.
- Với uploads lớn, tách route/architecture hỗ trợ streaming, object storage/direct upload nếu phù hợp.

### 20.2. Concurrency budget không chỉ là RPS

Little's Law mô tả mối quan hệ gần đúng ở hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc/requests trung bình đang có trong hệ thống.
- \(\lambda\): throughput thực tế (requests/s).
- \(W\): thời gian ở hệ thống (s).

Nếu Gateway xử lý **1.000 requests/s** và một request ở Gateway trung bình **0,2 s**, số request in-flight trung bình xấp xỉ **200**. Khi latency tăng do body/log I/O, số concurrent in-flight có thể tăng cùng tải, kéo theo buffer/memory pressure.

Đây là **mối quan hệ của hệ thống ổn định**, không phải cam kết số in-flight chính xác trong burst/overload. Khi request timeout/queue thay đổi, cần đo thực tế.

### 20.3. Các giới hạn có thể phối hợp

- Rate limit theo principal/tenant đã xác thực.
- Max concurrent request/pending queue theo dịch vụ/route.
- HTTP client pool and connect/response timeouts.
- Request body size + codec max in-memory.
- Log event/queue budget.
- Trace sampling/span attribute limits.
- Circuit breaker bulkhead/isolation nếu cần.
- HPA/autoscaling dựa trên CPU, RPS, concurrency và SLO.

**Tăng pool size không tự làm nhanh hơn** nếu upstream đã quá tải. Cần cân bằng capacity toàn đường đi.

## 21. Observability của chính observability

Khi bật logs/tracing/metrics, phải giám sát **chi phí và thất bại của chúng**:

| Thành phần | Chỉ số | Phản ứng |
| --- | --- | --- |
| App logger | Events/s, queue fill, drops | Giảm verbosity/sample, sửa sink |
| stdout/container logging | Bytes/s, blocked writes, agent errors | Thay cấu hình collector/limits |
| Tracer | Spans created/exported | Kiểm budget theo RPS |
| OTLP exporter | Queue, batch, timeout, dropped spans | Scaling/timeout/backoff phù hợp |
| Collector | CPU/memory, queue, downstream export success | Capacity, sharding/HA |
| Body transform | In/out sizes, rewrite duration, error rate | Limits, code/codec profiling |
| Netty | Event-loop lag, direct memory, connections | Điều tra blocking/pool |
| JVM | GC pauses, allocation, RSS | Tối ưu allocations/heap/direct memory |
| Gateway route | p50/p95/p99, status | So sánh với SLO |
| Backend | Latency, error, saturation | Tách nguyên nhân upstream |

Không tạo thêm logging quá chi tiết để đo logger bị chậm: như thế sẽ làm vấn đề nặng hơn. Dùng metrics tổng hợp và profiler có scope/permission phù hợp.

### 21.1. Khi nào cần profiler?

Nếu benchmark chứng minh overhead đáng kể nhưng chưa rõ nơi tiêu tốn CPU:

- JVM Flight Recorder/JFR hoặc async-profiler với sampling/overhead được kiểm soát.
- Heap/allocations profiling, GC logs đã phân tích.
- Netty event-loop thread stack samples khi nghi blocking.
- HTTP client pool metrics và log appender metrics.
- OTLP Collector self-metrics.

**Không dump heap trên production có dữ liệu nhạy cảm** nếu không có quy trình bảo mật: heap dump có thể chứa token và user data.

## 22. Quy trình ứng phó khi latency tăng sau thay đổi cấu hình

Giả sử sau một deployment p99 tăng từ 80 ms lên 400 ms và CPU Gateway tăng.

### 22.1. Phân loại

1. Xác định thời điểm change: bật wiretap, nâng sampling hay thêm body transform?
2. Xác nhận **route ID nào bị ảnh hưởng** và quy mô.
3. So p50, p95, p99; error rate; offered/achieved RPS.
4. Kiểm backend latency: upstream có chậm cùng thời điểm không?
5. Kiểm CPU throttling, heap/direct memory, GC và log/export queues.
6. Xem retries có khuếch đại outbound calls không.
7. Kiểm lượng requests đi vào từng replica, tránh load imbalance.

### 22.2. Hành động có thứ tự

~~~mermaid
flowchart TD
    A["p99 tăng sau cấu hình observability/body"] --> B{"Có lỗi bảo mật/lộ dữ liệu không?"}
    B -->|Có| C["Dừng log body/wiretap, cô lập sink và xử lý incident"]
    B -->|Không| D["So baseline và đo Gateway/Backend"]
    C --> D
    D --> E{"Logger/OTLP queue đang nghẽn?"}
    E -->|Có| F["Giảm verbosity/sampling, sửa collector"]
    E -->|Không| G{"Heap/direct memory/GC tăng?"}
    G -->|Có| H["Giới hạn body/concurrency, rollback transform"]
    G -->|Không| I["Kiểm Netty event loops, pool, upstream latency"]
    F --> J["Re-run benchmark + regression tests"]
    H --> J
    I --> J
    J --> K{"p99/error và HTTP contract đạt SLO?"}
    K -->|Có| L["Giữ cấu hình, audit change và monitor"]
    K -->|Không| M["Rollback change an toàn, tiếp tục điều tra"]
~~~

**Rollback phải đảm bảo correctness**: nếu body transform là yêu cầu bảo mật để loại trường nhạy cảm, tắt filter để tăng RPS có thể làm lộ dữ liệu. Cần thay bằng phương án bảo vệ tương đương ở upstream hoặc route policy trước khi loại transform.

### 22.3. Một incident report tối thiểu

~~~text
Change:
  Enable debug wiretap on gateway-a for 10 minutes

Observed:
  Gateway p99 up
  CPU and log volume increased
  Backend p99 nearly unchanged
  Error rate and retry attempts monitored

Action:
  Disable wiretap
  Verify privacy/log retention
  Re-run synthetic load
  Compare p99 and log queue drops

Conclusion:
  Cần benchmark với số liệu thật để xác định mức overhead
~~~

Đoạn trên là **mẫu báo cáo tình huống**, không phải sự kiện đã xảy ra hay kết quả đo thật.

## 23. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ nhìn average latency | Bỏ qua p99 và queueing | Thu p50/p95/p99 với tải thực |
| So RPS khi offered load khác nhau | Kết luận A/B sai | Kiểm offered/achieved RPS |
| Bật wiretap thường trực production | CPU/log I/O tăng, rò rỉ body/headers | Chỉ bật ngắn hạn ở lab/có giới hạn |
| Cho rằng access log = wiretap | Đánh giá sai log volume | Phân biệt HTTP metadata vs wire details |
| `log.debug("..." + serialize(body))` | Vẫn serialize dù DEBUG off | Lazy/guard, log kích thước |
| Async log queue không giới hạn | OOM khi collector chậm | Queue bounded và drop/backpressure policy |
| Log body JSON/text tùy tiện | Buffering + PII leak | Tránh; chỉ synthetic/redacted |
| Tạo header traceparent thủ công | Trace tree sai | Dùng instrumentation/propagator |
| Sampling 100% mọi request | Exporter/collector quá tải | Có tracing budget |
| Sampling 0.1 rồi coi CPU giảm 90% | Hiểu sai propagation/observation | Đo overhead thực tế |
| OTLP collector offline thì tự block Gateway | Độ trễ nghiệp vụ phụ thuộc telemetry | Export async/queue giới hạn và monitor |
| Giữ Span trong singleton/ThreadLocal | Trace leak/corruption | Reactor Context/instrumented client |
| Dùng `subscribe()` chỉ để logging | Mất lifecycle/body/context | Compose reactive pipeline |
| Body transform tất cả response lớn | Mất streaming, tăng peak memory | Chọn lọc route, limits, backend transform |
| `DataBufferUtils.join()` rồi giữ buffer | Leak/retention | Lifecycle/release đúng |
| Chỉ tăng maxInMemorySize | Tăng OOM risk | Size+concurrency limits, redesign |
| Retry POST có body không idempotent | Giao dịch trùng và buffer thêm | Idempotency và business-safe retry |
| Chỉ đo JVM heap | Bỏ qua Netty direct memory | RSS/direct/GC/pools |
| Dùng raw path/traceId metric labels | High cardinality | Route ID/templated path |
| Tắt body redaction filter để benchmark nhanh | Lộ dữ liệu khách hàng | Benchmark trên synthetic, giữ security |
| Dùng một request nhỏ để đánh giá performance | Không thấy stress/concurrency | Mix payload, steady/burst |
| Test only HTTP 200 | Không phát hiện sai body/header/status | Contract tests hai chiều |
| Nâng Boot/Cloud nhưng giữ property cũ | Bật/tắt khác mong muốn | Kiểm configprops release thực |
| So staging 1 replica với prod 8 replicas | Không comparable | Cố định topology/record khác biệt |

## 24. Bài thực hành tổng hợp

**Bối cảnh:** một Gateway Server WebFlux route `/api/orders/**` tới backend mock, có nhu cầu log route metadata, tracing để điều tra timeout và transform response JSON theo API contract.

### Yêu cầu

1. Chọn **một** phiên bản Gateway WebFlux, ghi rõ Boot/Cloud/JDK và starter phù hợp.
2. Tạo route baseline: `Path=/api/orders/**`, `StripPrefix=1`, URI trỏ mock upstream.
3. Viết contract tests xác minh path, request/response headers, body và status.
4. Chạy baseline với wiretap off, tracing sampling thấp/tắt exporter theo thiết kế nhóm A.
5. Dùng k6 tạo steady load ở 3 mức RPS, ghi offered/achieved RPS, p50/p95/p99.
6. Bật một **metadata log event/request**, đo CPU, log bytes/s, p99.
7. Bật access log, đo riêng; kiểm log không ghi token/raw query.
8. Bật wiretap **trong staging cô lập**, đo overhead ở traffic synthetic, rồi tắt.
9. Bật tracing với sampling `0.1`, kiểm W3C context ở upstream, OTLP exports.
10. Bật sampling `1.0` trong lab ngắn hạn, đo span rate/CPU/exporter drops.
11. Bật `ModifyResponseBody` cho response text/JSON nhỏ, đo allocation/GC.
12. Tăng payload từ 1 KiB đến 1 MiB; theo dõi heap, direct memory, p99.
13. Kết hợp metadata logging + tracing 10% + body transform; so kết quả ablation.
14. Mô phỏng Collector không khả dụng; xác minh Gateway vẫn xử lý nghiệp vụ theo policy.
15. Thử backend timeout và Retry GET, đo attempts; không auto-retry POST.
16. Chạy lại contract tests để bảo đảm không làm thay đổi status/body ngoài contract.
17. Tạo một báo cáo dữ liệu và kết luận: cơ chế nào đắt nhất, ngưỡng nào bắt đầu saturation, chọn cấu hình production và cách rollback.

### Ma trận nghiệm thu

| ID | Kiểm thử | Kết quả cần đạt |
| --- | --- | --- |
| P1 | Route baseline | Backend nhận đúng method/path/query |
| P2 | Body transform | Body/request/response theo contract |
| P3 | Wiretap off | Không ghi wire details ngoài chính sách |
| P4 | Wiretap on lab | Có debug có kiểm soát; tắt sau test |
| P5 | Logging metadata | Log route/status/latency, không raw token |
| P6 | Tracing 10% | Propagation hợp lệ; exporter hoạt động |
| P7 | Collector offline | Không tăng lỗi nghiệp vụ ngoài SLO đã đặt |
| P8 | Payload 1KiB/1MiB | Không buffer tràn/OOM; p99 ghi nhận |
| P9 | Retry GET | Attempt count đúng và latency được đo |
| P10 | POST important | Không side-effect trùng vì retry mù |
| P11 | High RPS | CPU, queues, error rate và p99 được theo dõi |
| P12 | A/B ablation | So sánh trên cùng điều kiện và đủ repeats |
| P13 | Body logging | Không log PII, không đọc stream bằng subscribe rời |
| P14 | Metrics | Không có raw request ID/path dynamic labels |
| P15 | Rollback | Tắt debug hoặc khôi phục transform mà không phá security |

Các dấu hiệu trên là **tiêu chí cho bài lab**, không khẳng định đã có một benchmark thật được chạy.

## 25. Checklist trước production

- [ ] Có **HTTP contract tests** bảo đảm path, header, body, status đúng sau mọi thay đổi.
- [ ] Có baseline p50/p95/p99/throughput/error với RPS và request mix rõ ràng.
- [ ] Wiretap Reactor Netty tắt bình thường; chỉ bật ngắn hạn có phê duyệt khi debug.
- [ ] Access/application logs chứa metadata đã làm sạch, không raw token/cookie/PII.
- [ ] Mức logging có guard/lazy evaluation; không serialize payload khi log level tắt.
- [ ] Log queue có giới hạn, monitor drops/blocking/collector latency.
- [ ] Tracing được sample theo ngân sách; không giữ 100% vô hạn nếu chưa đủ capacity.
- [ ] Collector/OTLP exporter có TLS/auth, retry/queue limits, dropped-span metrics.
- [ ] Inbound/outbound trace context sử dụng propagators chuẩn, không tự copy traceparent.
- [ ] Reactor Context/MDC correlation đúng khi thread switching, không subscribe rời.
- [ ] Observability không đưa blocking I/O/CPU-heavy work vào event-loop.
- [ ] Không biến đổi body khi chỉ cần sửa path/header hoặc response status.
- [ ] Mọi body transforms có test empty body, JSON null, 204/HEAD, compression, charset.
- [ ] Đã giới hạn request size, codec aggregation, concurrency và HTTP pool backlog.
- [ ] Bộ nhớ kiểm cả heap, direct buffers, RSS/cgroup và GC.
- [ ] Custom DataBuffer filters không leak/double-release/đọc body hai lần.
- [ ] Retry với body có idempotency và replay/memory budget phù hợp.
- [ ] Upload/download lớn không bị ép aggregate thành String chỉ để log hoặc transform.
- [ ] Metrics labels chỉ dùng route ID và dimensions có cardinality giới hạn.
- [ ] Benchmark có offered/achieved RPS, steady/burst, payload size distribution và repeats.
- [ ] Khi tắt logging/tracing/body transform vẫn giữ **security và business correctness**.
- [ ] Có runbook quay về cấu hình tốt, test trên từng replica và alert cho p99/CPU/OOM.
- [ ] Đã đối chiếu cấu hình theo **Spring Cloud Gateway và Spring Boot release chính xác**.

## 26. Tổng kết và tài liệu tham khảo

**Logging, tracing và biến đổi body** đều có giá trị trong Spring Cloud Gateway, nhưng mỗi cơ chế thêm chi phí lên đường đi request:

- **Logging:** chi phí format/queue/I/O và nguy cơ block event loop hoặc lộ dữ liệu nếu dump body/header.
- **Tracing:** chi phí tạo context/span/attributes, propagate headers, sampling/export; giúp chẩn đoán request qua nhiều dịch vụ nhưng cần budget và Collector có giới hạn.
- **Body transformation:** chi phí decode/aggregate/parse/rewrite/encode, có thể phá streaming và tăng memory/GC/p99 mạnh khi payload lớn hoặc concurrency cao.

Không có một tỷ lệ “bật tracing chậm X%” hay “ModifyResponseBody tốn Y MiB” áp dụng cho mọi môi trường. **Đo có đối chứng** dưới cùng offered load, tách p50/p95/p99 và resource metrics, dùng mock upstream để giữ HTTP contract, rồi mới ra quyết định.

Phương án production thường bắt đầu bằng **metrics đủ cho SLO, log metadata đã redact, tracing có sampling, wiretap off và body transform chọn lọc**. Khi sự cố xảy ra, tăng mức quan sát **có thời hạn**, không đánh đổi bảo mật hay độ ổn định của Gateway.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — Global Filters và Gateway Metrics Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — ModifyRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyrequestbody-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyResponseBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyresponsebody-factory.html).
- [Spring Cloud Gateway Server WebFlux — RequestSize](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestsize-factory.html).
- [Spring Cloud Gateway — Configuration Properties 5.x, Netty wiretap và observability](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Boot 3.5 — Tracing với Micrometer và OTLP](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Spring Boot hiện hành — Tracing/OpenTelemetry, sampling và exporters](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Framework WebFlux — Data Buffers và codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
- [Reactor Netty — HTTP Server Access Log](https://projectreactor.io/docs/netty/release/reference/http-server.html).
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
