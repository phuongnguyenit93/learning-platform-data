# IO_ERROR trong HTTP client observability

> **Chương:** HTTP client observability  
> **Bài:** IO_ERROR  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. IO_ERROR là gì trong một HTTP client?

Một HTTP client gửi request qua mạng tới dependency. Trước khi nhận được HTTP response, quá trình này có thể thất bại vì DNS không phân giải được host, không mở được TCP connection, TLS handshake lỗi, socket bị reset, kết nối bị đóng giữa chừng hoặc request timeout.

**IO_ERROR** trong ngữ cảnh HTTP client observability là cách phân loại một thất bại ở tầng I/O/transport khi client không hoàn tất được trao đổi HTTP như mong đợi. Đây là nhãn phân loại hữu ích trong bài học và dashboard; không phải một HTTP status code chuẩn và cũng không phải một exception class duy nhất trong Java.

Điểm cần phân biệt:

- HTTP response 503 nghĩa là client đã nhận được response có status 503.
- Connection refused nghĩa là client không thiết lập được kết nối tới server; không có HTTP response.
- Read timeout nghĩa là client đã chờ dữ liệu quá thời hạn; có thể đã kết nối và gửi request nhưng không nhận được response hoàn chỉnh.
- TLS handshake failure nghĩa là kết nối bảo mật không thiết lập được đúng cách.
- HTTP 404 là response hợp lệ ở tầng giao thức, dù có thể là lỗi theo contract của API.

~~~mermaid
flowchart TD
  A["WebClient gửi request"] --> B["DNS resolution"]
  B --> C["TCP connect"]
  C --> D["TLS handshake nếu HTTPS"]
  D --> E["Gửi request / nhận response"]
  E --> F{"Kết quả"}
  F -->|"HTTP response"| G["Phân loại status code"]
  F -->|"I/O / transport exception"| H["IO_ERROR"]
  G --> I["Client observation kết thúc"]
  H --> I
  I --> J["Metrics + trace + logs"]
~~~

Không có response status khi request thất bại trước khi nhận response. Vì vậy đừng gán giả HTTP 500 cho mọi IO_ERROR. Ghi nhận exception type và outcome riêng để phân biệt lỗi transport với server response.

## 2. Các giai đoạn mạng có thể tạo IO_ERROR

Một HTTP exchange đi qua nhiều giai đoạn. Biết giai đoạn nào thất bại giúp khoanh vùng nguyên nhân nhanh hơn.

| Giai đoạn | Triệu chứng thường gặp | Ví dụ nguyên nhân |
| --- | --- | --- |
| DNS lookup | Không phân giải được hostname | DNS record sai, resolver lỗi, service discovery chậm |
| TCP connect | Connection refused / connect timeout | Service không listen, firewall, network policy |
| TLS handshake | SSLHandshakeException | Certificate hết hạn, truststore sai, protocol/cipher mismatch |
| Request write | Broken pipe / connection reset | Peer đóng socket, proxy reset, connection stale |
| Response read | Read timeout / premature close | Server chậm, packet loss, response bị cắt |
| Connection pool acquire | Không lấy được connection trong thời hạn | Pool cạn, request giữ connection quá lâu |
| Response decode | Codec/decoder exception | Payload không hợp lệ hoặc schema không khớp |

Một số lỗi xảy ra sau khi HTTP response headers đã về, ví dụ body stream bị đóng giữa chừng. Khi đó client có thể đã biết status code nhưng vẫn thất bại khi đọc body. Không phải mọi lỗi I/O đều đồng nghĩa “chưa nhận được response”; hãy ghi nhận cả status đã biết và exception xảy ra trong giai đoạn body consumption nếu instrumentation cung cấp.

## 3. IO_ERROR khác HTTP status và application error

| Tình huống | Có HTTP response? | Ví dụ | Phân loại quan sát |
| --- | --- | --- | --- |
| DNS failure | Không | UnknownHostException | IO_ERROR |
| TCP refused | Không | ConnectException | IO_ERROR |
| Connect timeout | Thường không | ConnectTimeoutException | IO_ERROR |
| TLS handshake failure | Không có response HTTP hợp lệ | SSLHandshakeException | Transport/security setup error |
| Read timeout | Thường không có response hoàn chỉnh | ReadTimeoutException | IO_ERROR / timeout |
| HTTP 404 | Có | Not Found | HTTP response outcome |
| HTTP 503 | Có | Service Unavailable | HTTP response outcome, thường là dependency failure |
| JSON decode failure | Đã có response | DecodingException | Client processing/codec error |
| Business validation rejection | Có response hoặc domain result | Inventory rejected | Business outcome |

Một HTTP client observation có thể ghi status code và exception theo convention của instrumentation. Các hệ thống có thể gom nhiều exception transport thành một nhóm IO_ERROR cho dashboard, nhưng vẫn cần giữ exception type cụ thể trong trace/log để điều tra.

Không phân loại lỗi chỉ bằng message string. Exception hierarchy và cause chain thường cung cấp thông tin đáng tin cậy hơn; tuy nhiên loại exception cụ thể phụ thuộc HTTP connector và phiên bản.

## 4. Những exception I/O thường gặp trong Java

Một số loại exception có thể xuất hiện:

| Exception | Ý nghĩa thường gặp | Cần kiểm tra |
| --- | --- | --- |
| UnknownHostException | Không phân giải được hostname | DNS, service discovery, hostname |
| ConnectException | Kết nối TCP thất bại, thường bị từ chối | Service listener, port, firewall |
| SocketTimeoutException | Socket read/connect timeout tùy cấu hình | Timeout settings, server latency, network |
| SSLHandshakeException | TLS handshake thất bại | Certificate chain, truststore, TLS config |
| SSLPeerUnverifiedException | Không xác minh được peer identity | Hostname verification, certificate |
| ClosedChannelException | Channel đã đóng khi thao tác | Lifecycle connection, peer close |
| IOException | Lỗi I/O tổng quát | Cause chain và connector logs |
| PrematureCloseException | Connection/response đóng sớm trong một số Reactor Netty versions | Server/proxy reset, body stream |

Không phải WebClient luôn ném đúng các class trên. Reactor Netty, JDK HttpClient và connector khác có exception types/wrappers riêng. Ví dụ một IOException có thể được bọc trong WebClientRequestException, Reactor exception hoặc CompletionException.

Khi phân loại, giữ cả wrapper và root cause nếu hữu ích. Đừng dựa vào tên class duy nhất để kết luận DNS, TLS hay socket đã hỏng.

## 5. WebClient biểu diễn I/O failure như thế nào?

WebClient là reactive client. Request thường chỉ thực sự được gửi khi publisher được subscribe. Lỗi có thể được phát ra dưới dạng reactive onError signal, không phải luôn ném đồng bộ tại dòng gọi phương thức.

Ví dụ:

~~~java
public Mono<Product> findProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
~~~

Nếu DNS, connect hoặc read gặp lỗi, publisher có thể phát error signal. Nếu response có status 4xx/5xx, retrieve() mặc định thường chuyển status đó thành WebClientResponseException, trừ khi code cấu hình onStatus hoặc xử lý response khác.

~~~java
return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 503,
                response -> response.createException()
                        .flatMap(Mono::error))
        .bodyToMono(Product.class)
        .onErrorMap(
                WebClientRequestException.class,
                ex -> new InventoryIoException(
                        "Inventory transport failed", ex));
~~~

Ví dụ minh họa việc translate lỗi request-level thành exception domain. Cần nhớ:
- WebClientRequestException thường bao bọc lỗi khi gửi request/transport.
- WebClientResponseException thường đại diện HTTP response được xử lý như lỗi bởi retrieve().
- Decode/codec errors có thể phát sinh khi đọc body.
- Timeout operator hoặc connector timeout có thể tạo exception khác nhau.
- onErrorMap không nên chuyển mọi exception thành IO_ERROR; chỉ map nhóm lỗi phù hợp và giữ cause.

## 6. Tạo taxonomy cho HTTP client outcome

Một taxonomy nhỏ, rõ nghĩa giúp metrics và dashboard nhất quán. Ví dụ:

| Outcome | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| SUCCESS | Exchange hoàn tất theo policy | HTTP 2xx hoặc response được chấp nhận |
| HTTP_CLIENT_ERROR | Nhận HTTP 4xx | 400, 404, 429 |
| HTTP_SERVER_ERROR | Nhận HTTP 5xx | 500, 502, 503 |
| IO_ERROR | Transport/I/O không hoàn tất | DNS, connect, socket reset |
| TIMEOUT | Hết thời hạn ở một giai đoạn | Connect/read/overall timeout |
| DECODE_ERROR | Không đọc/giải mã được response | Invalid JSON |
| CANCELLED | Reactive operation bị cancel | Caller hủy subscription |

Taxonomy trên là ví dụ thiết kế cho ứng dụng, không phải tập giá trị mặc định bắt buộc của Spring Boot/Micrometer. Có thể gộp TIMEOUT vào IO_ERROR nếu dashboard chỉ cần một nhóm transport; hoặc giữ riêng nếu cần phân tích latency/timeout.

Điều quan trọng là định nghĩa nhất quán:
- Có status code thì giữ status code.
- Không có response status thì không giả lập mã HTTP.
- Giữ exception type đã chuẩn hóa.
- Phân biệt timeout, cancellation và decode failure khi cần.
- Không dùng exception message tự do làm metric tag.

## 7. WebClient observation ghi nhận lỗi ra sao?

Spring Boot có thể cấu hình WebClient instrumentation qua WebClient.Builder được Spring quản lý. Khi Observation handlers và tracing integration hoạt động, client exchange có thể tạo observation/span và ghi nhận response status, exception và duration.

~~~java
@Configuration
class InventoryClientConfig {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Dùng injected builder giúp nhận customizers/observation instrumentation do Boot cấu hình. Một WebClient tự tạo độc lập có thể không có cùng behavior.

Observation có thể:
- Bắt đầu khi reactive exchange thực thi.
- Đo thời gian request.
- Ghi method và URI template.
- Ghi response status nếu nhận được.
- Báo lỗi nếu exchange kết thúc bằng exception.
- Tạo client span và propagate trace context khi tracing bridge phù hợp.

Không giả định mọi lỗi đều tạo tag outcome tên IO_ERROR. Giá trị mặc định tùy convention/version; nếu cần taxonomy riêng, hãy chuẩn hóa ở lớp metric/observation phù hợp và giữ nguyên exception details ở trace/log.

## 8. Metrics để đo IO_ERROR

Một metric client request timer có thể tổng hợp thời gian và số lần gọi. Tên meter/tag phụ thuộc version; trong hệ sinh thái Spring thường gặp meter http.client.requests.

Các chiều hữu ích có cardinality kiểm soát:
- dependency: inventory, payment, identity.
- method: GET, POST, PUT.
- uri: route template.
- outcome: success, io_error, timeout, http_error.
- exception: loại exception chuẩn hóa.
- status: HTTP status nếu response tồn tại.

Ví dụ custom Counter:

~~~java
Counter.builder("http.client.failures")
        .tag("dependency", "inventory")
        .tag("failure.type", "io_error")
        .register(meterRegistry)
        .increment();
~~~

Đây là metric tùy chỉnh minh họa. Không tạo meter mới cho từng request. Đăng ký Counter một lần theo tổ hợp tag hữu hạn hoặc dùng builder/registry pattern có cache phù hợp.

### 8.1. Tính tỷ lệ I/O failure

Ví dụ PromQL nếu hệ thống có custom counters:

~~~text
sum(rate(http_client_failures_total{failure_type="io_error"}[5m]))
/
sum(rate(http_client_requests_total[5m]))
~~~

Metric names thực tế có thể khác. Đảm bảo numerator và denominator dùng cùng phạm vi dependency/operation, và mẫu số bao gồm đúng các lần exchange cần đo.

Nếu retries tạo nhiều exchanges, tỷ lệ per-attempt khác tỷ lệ logical operation thất bại cuối cùng. Cần đặt tên dashboard rõ ràng, ví dụ client attempt IO error rate và business request final failure rate.

### 8.2. Timeout riêng hay gộp vào IO_ERROR?

Timeout thường là một loại I/O/transport failure, nhưng nhiều đội vận hành muốn dashboard riêng vì timeout gắn với latency, pool saturation và SLA. Chọn một trong hai cách:

- Gộp timeout vào IO_ERROR và thêm exception/phase metadata ở trace.
- Tách outcome TIMEOUT nhưng vẫn nhóm nó dưới transport failure trong dashboard tổng.

Không đếm cùng một event hai lần trong tổng failure rate. Nếu có metric riêng cho timeout, xác định quan hệ giữa các counters.

## 9. Cardinality và URI template

HTTP client có thể gọi nhiều URI khác nhau. Nếu metric tag chứa raw URL hoặc path ID, số series tăng theo lượng tài nguyên.

Không tốt:

~~~java
webClient.get()
        .uri("/products/" + productId)
        .retrieve();
~~~

Nên dùng URI template:

~~~java
webClient.get()
        .uri("/products/{id}", productId)
        .retrieve();
~~~

Với base URL động, chuẩn hóa dependency thành tên hữu hạn thay vì host string tùy ý từ input. Không đưa:
- productId/orderId/customerId.
- query string.
- raw exception message.
- IP/port động nếu không cần.
- traceId/requestId.
- token hoặc URL có credentials.

Dùng low-cardinality tags cho metrics. Trace/log có thể giữ thêm thông tin chẩn đoán được allowlist và bảo vệ, nhưng không nên export PII/secrets.

## 10. Trace cho IO_ERROR và context propagation

Khi WebClient được instrument, client span có thể kết thúc với exception event hoặc error status tùy tracing implementation. Trace context được inject vào outbound headers để downstream nối server span nếu request đến được service.

Với W3C Trace Context, header traceparent mang trace ID, parent span ID và flags. Nếu DNS/connect thất bại trước khi HTTP request được gửi, header có thể chưa bao giờ tới dependency; client span vẫn ghi nhận lần thử thất bại.

Nếu lỗi xảy ra ở DNS/connect trước khi server nhận request:
- Client span vẫn có thể tồn tại.
- Có thể không có downstream server span.
- Trace cho thấy lỗi ở phía caller.
- Exception type/cause giúp xác định giai đoạn thất bại.

Ví dụ trace minh họa:

~~~text
order-service: POST /orders                 [SERVER]
  order-service: inventory GET /stock/{sku} [CLIENT, ERROR]
    exception.type = java.net.ConnectException
    error.type = io_error
~~~

Nếu downstream không có span, không kết luận ngay instrumentation bị hỏng. Request có thể chưa đến được server. Kiểm tra client span, network logs, service health và Collector/exporter.

Sampling có thể loại trace trước khi export. Logs/metrics vẫn có thể tồn tại theo policy riêng; đừng phụ thuộc trace để đo đầy đủ số lần I/O failure.

## 11. Timeout là một nhóm cần phân biệt

Timeout có thể xảy ra ở nhiều giai đoạn:

| Timeout | Giai đoạn | Điều cần kiểm tra |
| --- | --- | --- |
| DNS timeout | Phân giải hostname | Resolver, DNS latency |
| Connect timeout | Mở TCP connection | Network route, listener, firewall |
| TLS handshake timeout | Thiết lập TLS | Certificate validation, peer response |
| Response/read timeout | Chờ response bytes | Server latency, downstream saturation |
| Pool acquire timeout | Chờ connection trong pool | Pool size, connection leak, concurrency |
| Overall request timeout | Tổng thời gian operation | Budget end-to-end và từng timeout thành phần |

Không phải mọi timeout đều là SocketTimeoutException. Reactor Netty có thể phát exception riêng; pool acquire có thể phát lỗi acquire timeout; Reactor timeout operator có thể phát TimeoutException.

Thiết kế timeout theo budget end-to-end. Tổng thời gian retry, backoff, connection acquire và request attempts phải nằm trong deadline của caller. Nếu mỗi lần retry có timeout dài hơn budget còn lại, request có thể kéo dài quá SLA.

## 12. Retry và circuit breaker khi gặp IO_ERROR

Retry có thể hữu ích với lỗi tạm thời như connection reset hoặc timeout, nhưng không phải mọi I/O failure đều retry an toàn.

Có thể cân nhắc retry khi:
- Lỗi có khả năng tạm thời.
- Operation idempotent hoặc có idempotency key.
- Retry budget còn đủ.
- Backoff có jitter và giới hạn số lần.
- Không retry các lỗi cấu hình cố định như hostname sai hoặc certificate không hợp lệ một cách vô hạn.

Không retry vô điều kiện POST tạo giao dịch nếu chưa bảo đảm idempotency. Retry có thể khuếch đại tải khi dependency đang quá tải.

Với Reactor, có thể cấu hình retryWhen với Retry.backoff để giới hạn số lần thử và khoảng backoff. Mỗi lần retry có thể tạo một HTTP exchange mới; kiểm tra số client spans thực tế thay vì giả định mọi integration tạo cùng một cấu trúc.

Circuit breaker ngăn tiếp tục gọi dependency khi tỷ lệ lỗi vượt ngưỡng. Nó giúp bảo vệ caller và downstream, nhưng cần phân biệt failure type nào được tính là failure. HTTP 404 expected có thể không nên mở circuit; timeout/connect failure thường cần được xem xét.

~~~mermaid
flowchart TD
  A["HTTP client call"] --> B["Attempt"]
  B --> C{"Result"}
  C -->|"Success"| D["Return response"]
  C -->|"Retryable IO_ERROR"| E{"Retry budget còn?"}
  E -->|"Có"| F["Backoff + jitter"]
  F --> B
  E -->|"Không"| G["Record final failure"]
  C -->|"Non-retryable"| G
  G --> H["Circuit breaker records failure"]
  H --> I["Fallback / error response"]
~~~

## 13. Phân biệt IO_ERROR với decode và business failures

Một response có thể tới thành công ở tầng mạng nhưng ứng dụng vẫn không sử dụng được:

- Server trả 200 nhưng body không phải JSON hợp lệ: decode error.
- Server trả 404 cho SKU không tồn tại: HTTP response và có thể là business result.
- Server trả 503: HTTP server response failure.
- TCP connection reset trước response: IO_ERROR.
- Caller cancel khi không còn cần kết quả: cancellation, không nhất thiết là IO_ERROR.

Việc phân loại đúng giúp không đổ lỗi cho network khi thực chất schema response đã đổi, hoặc đổ lỗi cho server khi caller chủ động hủy.

Với body stream, lỗi đọc có thể xảy ra sau khi response status đã biết. Ghi nhận cả status và body-read exception nếu framework cung cấp; đừng xóa status chỉ vì body decode thất bại.

## 14. Logging cho IO_ERROR

Log record cần giúp trả lời dependency nào, operation nào, giai đoạn nào và exception type gì. Dùng exception object để giữ stack trace ở boundary chịu trách nhiệm log.

~~~java
try {
    return inventoryClient.findStock(sku);
} catch (WebClientRequestException ex) {
    log.error(
            "Inventory HTTP transport failed dependency={} operation={}",
            "inventory",
            "find-stock",
            ex);
    throw ex;
}
~~~

Ví dụ chỉ phù hợp với code đồng bộ hoặc đoạn code đã chuyển reactive error thành exception trong đúng boundary. Với reactive WebClient, dùng onErrorResume/doOnError/onErrorMap theo flow thay vì try/catch quanh việc tạo Mono; try/catch đó không bắt lỗi phát sinh sau subscription.

Không log full URL có credentials, request/response body, authorization headers, cookies hoặc raw customer identifiers. Gắn traceId/spanId qua logging correlation integration thay vì tự tạo ID.

Tránh log cùng exception tại client adapter, service, controller và global handler. Chọn một boundary ghi stack trace đầy đủ; các tầng khác có thể translate/rethrow và giữ cause.

## 15. Troubleshooting IO_ERROR

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| UnknownHostException | DNS/service discovery | Kiểm tra hostname, DNS resolver, namespace |
| Connection refused | Không có listener hoặc port sai | Kiểm tra service endpoints, port, readiness |
| Connect timeout | Network policy, firewall, route hoặc service quá tải | Kiểm tra network path và connect latency |
| SSLHandshakeException | Certificate/truststore/protocol mismatch | Kiểm tra chain, SAN, truststore, TLS versions |
| Read timeout | Dependency chậm, queue hoặc response stream treo | So sánh server latency, pool và timeout budget |
| Connection reset | Peer/proxy đóng socket | Kiểm tra proxy, load balancer, keep-alive |
| Pool acquire timeout | Connection pool cạn | Kiểm tra concurrency, pool metrics, response body release |
| Premature close | Server/proxy cắt response | Kiểm tra server logs, proxy limits, body stream |
| Có metrics nhưng không trace | Tracing bridge/sampling/export pipeline | Kiểm tra span creation, sampling, exporter |
| Không có status tag | Không nhận response hoặc convention khác | Phân biệt transport failure và HTTP response |
| Error rate tăng sau deploy | DNS, endpoint, TLS, timeout hoặc dependency regression | So sánh version/resource và rollout |
| Retry làm tải tăng | Retry storm hoặc policy rộng | Giới hạn attempts, jitter, circuit breaker |

### Quy trình điều tra

1. Xác định có nhận được HTTP status hay không.
2. Đọc exception class và cause chain.
3. Xác định giai đoạn DNS, connect, TLS, write, read, pool hay decode.
4. Kiểm tra WebClient connector, timeout và pool metrics.
5. So sánh dependency latency/error với caller latency.
6. Kiểm tra client span; downstream span có thể vắng nếu request chưa tới server.
7. Đối chiếu logs, deployment version và service instance.
8. Kiểm tra retry/circuit breaker có khuếch đại lỗi không.
9. Tạo test tái hiện trong môi trường cô lập trước khi đổi timeout hoặc retry policy.

## 16. Tình huống thực tế: order-service không kết nối được inventory

**Bối cảnh:** order-service gọi inventory-service qua WebClient. Sau một lần deploy, tỷ lệ IO_ERROR tăng. Client metrics cho thấy nhiều request thất bại nhưng không có HTTP status.

### Bước 1 — phân loại exception

Logs cho thấy WebClientRequestException có cause là ConnectException. Điều này chỉ ra TCP connection bị từ chối, không phải inventory trả 503.

### Bước 2 — kiểm tra service discovery và endpoint

Kiểm tra hostname, Kubernetes Service selector, EndpointSlices, port mapping và readiness của inventory pods. Một deployment sai selector có thể khiến Service không có endpoint sẵn sàng.

### Bước 3 — xem trace

Client span kết thúc với error nhưng không có server span tương ứng. Điều này phù hợp với giả thuyết request không đến được inventory process. Nếu có server span, tiếp tục kiểm tra request đã tới server nhưng lỗi ở giai đoạn response.

### Bước 4 — xem retry policy

Nếu mỗi request thử lại nhiều lần, tổng connect attempts tăng. Đếm attempt riêng, giới hạn retry và dùng backoff; không tạo retry storm khi endpoint không có listener.

### Bước 5 — xác minh sau sửa

Sau khi khôi phục endpoint, theo dõi:
- IO_ERROR rate và connect exception count giảm.
- Client success rate tăng.
- Client latency trở về baseline.
- Trace client/server spans nối lại.
- Retry attempts không tăng bất thường.

**Bài học:** IO_ERROR không phải HTTP 5xx. Khi không có response status, điều tra network/transport trước; dùng exception cause, client span và hạ tầng để tìm giai đoạn thất bại.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — tạo các lỗi transport

Dùng mock server hoặc môi trường test để tạo:
- Hostname không phân giải được.
- Port không có listener.
- Connect timeout.
- Read timeout.
- TLS certificate không tin cậy.
- Response body bị đóng sớm.

Ghi lại exception class, cause chain, có HTTP status hay không và client observation được export thế nào.

### Bài tập B — phân biệt HTTP response với I/O failure

Mock response 404, 503 và một lần connection reset. Xác minh 404/503 có status code; connection reset không có HTTP response status. Không map tất cả thành status 500.

### Bài tập C — timeout budget

Thiết kế connect timeout, response timeout, overall timeout và retry budget cho một dependency có SLA. Tính tổng thời gian tối đa gồm attempts và backoff, bảo đảm không vượt deadline caller.

### Bài tập D — metrics và cardinality

Tạo custom counter cho io_error theo dependency và exception category. Gửi request với nhiều SKU khác nhau; xác minh SKU không tạo metric series mới. So sánh attempt failure rate với final operation failure rate.

### Bài tập E — tracing

Bật WebClient observation và tracing. Gây lỗi DNS/connect để xác minh client span có error nhưng có thể không có downstream server span. Sau đó cho mock server trả 503 để so sánh response status và exception semantics.

### Bài tập F — retry/circuit breaker

Mô phỏng dependency chập chờn. Cấu hình retry có giới hạn, backoff và circuit breaker. Xác minh retry không áp dụng cho certificate/hostname misconfiguration và không khuếch đại tải.

### Câu hỏi tự kiểm tra

1. IO_ERROR khác HTTP 5xx như thế nào?
2. Vì sao ConnectException thường không có HTTP response status?
3. UnknownHostException chỉ ra giai đoạn nào?
4. TLS handshake failure cần kiểm tra những gì?
5. WebClientRequestException và WebClientResponseException khác nhau ra sao?
6. Vì sao try/catch quanh việc tạo Mono không bắt được lỗi xảy ra khi subscribe?
7. Timeout có thể phát sinh ở những giai đoạn nào?
8. Response body có thể lỗi sau khi status đã được nhận không?
9. Khi nào retry IO_ERROR là an toàn?
10. Vì sao không retry vô hạn khi DNS hoặc certificate sai?
11. Circuit breaker nên phân loại HTTP 404 expected thế nào?
12. Vì sao client span có thể không có downstream server span?
13. Làm sao giữ cardinality thấp cho IO_ERROR metrics?
14. Log IO_ERROR cần giữ context và cause nào?
15. Làm thế nào phân biệt transport failure, decode error, cancellation và business rejection?

**Tiêu chí hoàn thành:** phân biệt IO_ERROR với HTTP status; nhận diện các giai đoạn DNS/TCP/TLS/I/O; hiểu exception mapping của WebClient/Reactor; cấu hình timeout/retry có budget; quan sát metrics/traces/logs; kiểm soát cardinality; điều tra client failure mà không giả lập HTTP status.

## 18. Ghi nhớ

- IO_ERROR là nhóm lỗi I/O/transport, không phải HTTP status code và không phải một exception class duy nhất.
- DNS, TCP connect, TLS handshake, socket write/read, pool acquire và response stream có thể thất bại ở các giai đoạn khác nhau.
- HTTP 503 là response nhận được; connection refused hoặc DNS failure thường không có response status.
- WebClient phát lỗi qua reactive signal khi exchange thực thi; try/catch quanh việc tạo publisher không bắt được mọi lỗi bất đồng bộ.
- WebClientRequestException thường đại diện lỗi request/transport; WebClientResponseException thường đại diện response status được xử lý như lỗi. Giữ cause chain và kiểm tra connector.
- Timeout có thể ở DNS, connect, pool, TLS, read hoặc overall deadline; không gom mọi timeout thành cùng một nguyên nhân.
- Retry chỉ nên áp dụng cho lỗi tạm thời và operation an toàn; giới hạn attempts, backoff, jitter và deadline.
- Dùng metrics outcome/exception category có cardinality thấp; không đưa raw URL, ID hoặc exception message thành tag.
- Client span có thể có error dù downstream không có server span nếu request chưa đến được service.
- Phân biệt IO_ERROR, HTTP response error, decode failure và cancellation để dashboard và alert có semantics đúng.

## Tài liệu tham khảo

- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

