# Giới hạn tải, áp lực tài nguyên và bảo vệ dịch vụ phụ thuộc

## 1. Vì sao SOAP service cần giới hạn tải?

Một dịch vụ SOAP trong module **SPRING_WEB_SERVICES** có thể nhận XML lớn, giải mã MIME attachment, kiểm tra WS-Security, chuyển đổi JAXB object, truy vấn database và gọi nhiều hệ thống phía sau. Mỗi request tiêu thụ CPU, heap, thread, connection và thời gian xử lý. Khi tốc độ request đến vượt khả năng xử lý, request tích tụ trong hàng đợi, thread bị giữ lâu, heap tăng, connection pool cạn và độ trễ lan sang các operation khác.

Một SOAP endpoint vẫn có thể đúng WSDL/XSD nhưng vận hành không ổn định khi tải tăng. Thiết kế production cần kiểm soát:

- **Admission:** request nào được phép vào hệ thống, request nào cần từ chối sớm.
- **Concurrency:** số request được xử lý đồng thời.
- **Queueing:** số request được phép chờ và thời gian chờ tối đa.
- **Resource budgets:** giới hạn body, header, attachment, XML depth, CPU, heap, thread và connection.
- **Dependency protection:** timeout, bulkhead, circuit breaker, retry và rate limit cho downstream services.
- **Overload behavior:** trả lỗi có thể hiểu được, giữ hệ thống sống và phục hồi có kiểm soát.

Mục tiêu không phải tối đa hóa số request nhận vào. Mục tiêu là giữ **throughput hữu ích và latency trong SLO**, đồng thời ngăn một dependency hoặc một loại request làm sập toàn bộ SOAP service.

### Mục tiêu học tập

Sau bài thuộc chương **Hiệu năng và vận hành**, bạn có thể:

1. Ước lượng concurrency và queue capacity theo latency, throughput và ngân sách tài nguyên.
2. Đặt giới hạn request ở reverse proxy, Servlet container, SOAP parser, ứng dụng và dependency client.
3. Thiết kế bounded executor, semaphore, connection pool và timeout hữu hạn.
4. Phân biệt backpressure, admission control, rate limiting, bulkhead và circuit breaker.
5. Bảo vệ database, HTTP/SOAP downstream, broker và dịch vụ xác thực khỏi request storm.
6. Thiết kế retry có giới hạn, exponential backoff, jitter và idempotency.
7. Định nghĩa overload response/Fault an toàn và graceful degradation.
8. Đo queue depth, active requests, saturation, rejection, timeout và dependency health.
9. Xây dựng load/stress/soak tests và runbook xử lý quá tải.

## 2. Luồng request và các điểm có thể bị nghẽn

Một request SOAP qua HTTP thường đi qua nhiều lớp. Giới hạn tải phải được đặt ở nơi có thể chặn request trước khi tài nguyên phía sau bị tiêu thụ.

~~~mermaid
flowchart TD
    A["Client / partner"] --> B["Load balancer / reverse proxy"]
    B --> C["HTTP connection and request limits"]
    C --> D["Servlet container threads"]
    D --> E["MessageDispatcherServlet"]
    E --> F["SOAP parsing / MIME / XML security"]
    F --> G["Endpoint mapping and interceptors"]
    G --> H["JAXB / endpoint"]
    H --> I["Application service"]
    I --> J["Bounded dependency bulkheads"]
    J --> K["Database / HTTP APIs / broker / identity"]
    K --> L["SOAP response or Fault"]
~~~

| Lớp | Tài nguyên dễ cạn | Biện pháp kiểm soát |
| --- | --- | --- |
| Load balancer/reverse proxy | Socket, connection, ingress bandwidth | Connection limit, request rate, body limit, upstream timeout |
| Servlet container | Request threads, accept queue, connections | Max threads, accept count, connection timeout |
| SOAP parser/message factory | Heap, CPU, XML parser objects | Body/attachment limits, parser hardening, parser limits |
| WS-Security | CPU, crypto provider, trust/key lookup | Concurrency cap, algorithm policy, timeout/cache hợp lý |
| JAXB/endpoint | Heap, CPU, object graph size | Payload/schema constraints, request limits, bounded concurrency |
| Application service | DB connections, locks, CPU | Admission control, transaction timeout, bounded pools |
| Downstream client | Socket/connection pool, waiting threads | Connect/read timeout, bulkhead, circuit breaker |
| Async work/broker | Queue storage, consumers | Bounded queue, retention, consumer concurrency and DLQ |

**Nguyên tắc:** không nhận thêm việc nếu không có đủ ngân sách để xử lý hoặc từ chối nó. Queue không giới hạn chỉ chuyển overload thành latency và memory exhaustion.

## 3. Hiểu throughput, latency và concurrency

### 3.1. Little's Law

Trong hệ thống ổn định, định luật Little cho biết:

\[
L = \lambda W
\]

Trong đó L là số request trung bình đang ở trong hệ thống; λ là throughput trung bình (request/giây); W là thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ: service xử lý trung bình 80 request/giây, latency trung bình 0,25 giây:

\[
L = 80 \times 0.25 = 20
\]

Trung bình có khoảng 20 request đang ở trong hệ thống. Đây là số trung bình, không phải concurrency tối đa hay queue capacity cần đặt.

Nếu latency tăng lên 2 giây mà throughput đến vẫn 80 request/giây, số request trong hệ thống có thể tăng lên:

\[
L = 80 \times 2 = 160
\]

Đây là cách queue và in-flight work phình ra khi dependency chậm.

### 3.2. Concurrency budget không phải một con số tùy ý

Concurrency bị giới hạn bởi HTTP worker threads; CPU cores và thời gian crypto/XML parsing; heap dành cho request/response object graph; database connection pool; HTTP connection pools tới dependency; broker consumer capacity; lock contention và transaction duration.

Giả sử application service dùng tối đa 24 database connections và một request thường giữ một connection trong 100 ms. Không nên cho hàng trăm request đồng thời cùng tiến tới đoạn truy cập DB rồi để phần lớn chờ pool. Bounded concurrency gần với ngân sách downstream giúp queue nằm ở một vị trí có thể quan sát và giới hạn.

### 3.3. Dùng latency percentile và SLO

Không dùng riêng average latency để đặt giới hạn. Theo dõi p50, p95, p99, timeout/rejection rate và throughput success, không chỉ request được nhận. Nếu downstream p99 đã gần bằng timeout toàn request, retry hoặc các bước xử lý tiếp theo có thể khiến SLO bị phá vỡ. Timeout cần được phân bổ thành ngân sách theo từng dependency.

## 4. Admission control và giới hạn request đầu vào

### 4.1. Giới hạn sớm ở edge

Reverse proxy/API gateway là vị trí thích hợp để chặn request quá lớn hoặc vượt rate limit trước khi đi vào JVM:

- Max request body bytes;
- Max concurrent connections/upstream requests;
- Requests per second theo IP, partner hoặc API key đã xác thực;
- Header size/count;
- Idle/read timeout;
- Upload/attachment size;
- Connection rate và burst limit.

Các directive cụ thể phụ thuộc proxy (Nginx, Envoy, ingress controller hoặc API gateway). Đừng giả định Spring-WS tự giới hạn body trước khi container đã nhận hoặc đệm một phần request.

Rate limit theo IP đơn lẻ có thể không phù hợp khi nhiều partner dùng chung NAT. Với dịch vụ B2B, quota theo partner identity/API credential thường có ý nghĩa hơn, nhưng cần xác thực identity trước khi tin quota key.

### 4.2. Giới hạn kích thước SOAP message

SOAP Envelope là XML và có thể lớn do payload, Header hoặc MIME attachments. Cần định nghĩa:

- Max HTTP request body;
- Max SOAP envelope bytes;
- Max attachment bytes và tổng MIME message bytes;
- Max số lượng MIME parts;
- Max XML element depth và attribute count nếu parser hỗ trợ;
- Max số item trong collection theo XSD/business contract;
- Max response size.

Nếu chỉ giới hạn payload XML sau khi parse, JVM có thể đã tốn bộ nhớ để nhận/parse một message quá lớn. Đặt byte limit ở gateway/container trước, sau đó thêm giới hạn chuyên biệt ở tầng SOAP.

### 4.3. XML parser và entity expansion

SOAP parser cần xử lý XML untrusted. Bên cạnh XXE protection, kiểm soát các giới hạn parser và tắt external entity/DTD theo security policy. Billion Laughs/entity expansion có thể làm CPU/heap tăng mạnh nếu parser không được bảo vệ.

Không bật DTD hoặc external entities để giải quyết lỗi contract một cách tùy tiện. Với schema validation, dùng XSD đã quản trị, resolver an toàn và tránh cho request import schema URL từ internet/file system.

### 4.4. Reject sớm và phản hồi phù hợp

Request bị từ chối ở gateway có thể nhận HTTP 413/429/503. Nếu đã vào SOAP processing, ứng dụng có thể trả SOAP Fault theo contract. Đừng cố bọc mọi overload thành một SOAP Fault nếu gateway/container đã từ chối trước khi SOAP parser tạo message.

Response overload nên có error category ổn định, correlation ID, retry hint khi xác định an toàn, và không tiết lộ host, thread, queue, pool hoặc stack trace nội bộ. Nếu dùng HTTP 429, Retry-After có thể giúp client biết thời gian thử lại; client vẫn phải tuân retry budget và idempotency.

## 5. Bounded concurrency và queue

### 5.1. Vì sao queue phải bounded?

Khi tốc độ request đến vượt tốc độ xử lý, queue length tăng. Queue vô hạn khiến memory hoặc request age tăng không giới hạn; cuối cùng request timeout hàng loạt hoặc JVM bị OOM.

Queue bounded đặt ra một điểm quyết định: nếu còn chỗ, request được chờ trong giới hạn; nếu queue đầy, request bị từ chối ngay hoặc caller nhận trạng thái overload; queue age được giám sát để loại bỏ công việc đã hết deadline.

Không cấu hình queue rất lớn để che giấu dependency chậm. Queue lớn chỉ kéo dài thời gian trước khi fail và có thể khiến client nhận response sau khi đã bỏ cuộc.

### 5.2. Bounded executor cho background work

Với công việc bất đồng bộ như xử lý attachment, enrichment hoặc phát event, có thể dùng executor có queue hữu hạn:

~~~java
@Bean
ThreadPoolTaskExecutor invoiceExecutor() {
    ThreadPoolTaskExecutor executor =
        new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("invoice-work-");
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();
    return executor;
}
~~~

Các con số chỉ là ví dụ. Phải đo CPU, heap, DB connections, downstream limits và latency thực tế trước khi chọn. AbortPolicy ném RejectedExecutionException; ứng dụng cần bắt tại ranh giới submit và chuyển thành response/operation status phù hợp.

Không thay AbortPolicy bằng CallerRunsPolicy theo thói quen: khi queue đầy, HTTP request thread có thể bị buộc chạy background work, làm mất ý nghĩa tách bulkhead và tăng latency inbound. Caller-runs chỉ phù hợp khi chủ đích backpressure đồng bộ và đã tính thread budget.

### 5.3. Giới hạn concurrency đồng bộ bằng semaphore

Một operation đắt CPU hoặc gọi dependency có thể cần giới hạn số tác vụ đồng thời:

~~~java
public final class OperationAdmission {
    private final Semaphore permits = new Semaphore(24);

    public <T> T execute(Callable<T> action) throws Exception {
        if (!permits.tryAcquire()) {
            throw new ServiceOverloadedException(
                "Service capacity is temporarily exhausted");
        }
        try {
            return action.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Semaphore này là admission guard trong JVM. Nó không giới hạn tổng concurrency giữa nhiều replica. Nếu mỗi instance có 24 permits và có 5 instance, tổng có thể lên tới 120. Hãy chia budget theo instance/cluster hoặc dùng distributed coordination khi requirement thật sự cần giới hạn toàn cụm.

Không giữ permit trong lúc chờ tác vụ không liên quan sau khi resource đã được giải phóng. Phạm vi try/finally phải bao quanh chính công việc được bảo vệ.

## 6. Backpressure, rate limiting và load shedding

### 6.1. Backpressure

Backpressure là cách downstream hoặc consumer báo cho upstream giảm tốc/không gửi thêm việc. Trong HTTP SOAP request/response truyền thống, backpressure thường được triển khai gián tiếp qua bounded concurrency; bounded queue và reject; giới hạn request rate; timeout ngắn hơn deadline caller; client retry có kiểm soát; và HTTP 429/503 hoặc SOAP Fault phù hợp.

Không phải mọi API WebServiceTemplate đều có Reactive Streams backpressure. Đừng gọi bounded executor là reactive backpressure; nó là cơ chế giới hạn/điều tiết concurrency cụ thể.

### 6.2. Rate limiting và quota

Rate limit giới hạn tốc độ request trong cửa sổ thời gian; quota có thể giới hạn tổng số request hoặc bytes theo giờ/ngày/partner.

| Thuật toán | Đặc điểm |
| --- | --- |
| Fixed window | Dễ triển khai; có thể tạo burst ở ranh giới hai cửa sổ. |
| Sliding window | Phân bố chính xác hơn, chi phí state cao hơn. |
| Token bucket | Cho phép burst có giới hạn và tốc độ trung bình xác định. |
| Leaky bucket | Điều tiết đầu ra theo nhịp ổn định. |

Rate limiting nên gắn với identity đáng tin, operation cost và quota contract. Một GetStatus nhẹ không nhất thiết tiêu thụ cùng quota với SubmitLargeInvoice có attachment.

### 6.3. Load shedding

Load shedding chủ động từ chối một phần request khi hệ thống gần bão hòa để bảo vệ request quan trọng hơn: từ chối tenant vượt quota; từ chối operation batch/attachment nặng khi CPU/heap pressure cao; từ chối request có deadline đã hết; ưu tiên health/admin/control plane cần cho recovery; tạm ngưng optional enrichment khi downstream không khỏe.

Chính sách phải công bằng và có thể quan sát. Không dùng header ưu tiên do client tự khai báo nếu client chưa được xác thực hoặc chưa được cấp quota tương ứng.

## 7. Bảo vệ dịch vụ phụ thuộc bằng timeout và bulkhead

### 7.1. Timeout là ngân sách

Một SOAP operation có thể gọi nhiều dependencies:

~~~text
Total deadline:                 2.0 s
  authentication/identity lookup: 0.2 s
  order database:                 0.4 s
  inventory service:              0.6 s
  payment risk service:            0.4 s
  response serialization reserve:  0.2 s
  safety margin:                   0.2 s
~~~

Các con số chỉ minh họa. Nếu tổng timeout của dependencies vượt deadline toàn request, thread có thể bị giữ lâu hơn client chờ; client retry trong khi request cũ vẫn chạy tạo thêm tải.

Thiết kế có deadline toàn operation; timeout connect, connection acquisition, response/read riêng; propagate remaining deadline xuống dependency nếu API hỗ trợ; không cho timeout của một bước dài hơn deadline còn lại; dành thời gian serialize response và đóng resource.

### 7.2. Bulkhead

Bulkhead cô lập tài nguyên giữa các dependency hoặc nhóm operation. Ví dụ: pool riêng cho inventory và payment; semaphore riêng cho attachment scanning; thread pool riêng cho batch reports; connection pool riêng cho đối tác chậm; admission quota theo partner/operation.

Nếu payment chậm, bulkhead ngăn toàn bộ request giữ hết thread/connection đang cần cho inventory hoặc query trạng thái nhẹ.

### 7.3. Ví dụ Resilience4j

~~~java
BulkheadConfig config = BulkheadConfig.custom()
    .maxConcurrentCalls(20)
    .maxWaitDuration(Duration.ZERO)
    .build();

Bulkhead inventoryBulkhead =
    Bulkhead.of("inventory", config);

Supplier<InventoryResult> protectedCall =
    Bulkhead.decorateSupplier(
        inventoryBulkhead,
        () -> inventoryClient.checkAvailability(orderId));

InventoryResult result =
    Try.ofSupplier(protectedCall)
        .getOrElseThrow(InventoryOverloadedException::new);
~~~

Đoạn code minh họa Resilience4j Bulkhead và Vavr Try; cần dependency phù hợp hoặc thay phần error mapping bằng try/catch thông thường. maxWaitDuration(Duration.ZERO) nghĩa là không chờ permit; request không lấy được permit sẽ bị reject nhanh. Chọn concurrency theo khả năng inventory service và pool client, không chỉ dựa CPU của SOAP server.

## 8. Circuit breaker và graceful degradation

### 8.1. Circuit breaker

Circuit breaker quan sát lỗi/slow calls của dependency và chuyển trạng thái:

- **CLOSED:** cho phép call và ghi nhận kết quả;
- **OPEN:** tạm thời từ chối call tới dependency;
- **HALF_OPEN:** cho một số probe request thử dependency phục hồi.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: failure/slow-call threshold reached
    OPEN --> HALF_OPEN: wait duration elapsed
    HALF_OPEN --> CLOSED: permitted probes succeed
    HALF_OPEN --> OPEN: probe fails
~~~

Circuit breaker bảo vệ caller khỏi tiếp tục tạo tải lên dependency đang lỗi. Nó không thay timeout hoặc bulkhead: nếu call không timeout, thread có thể bị giữ trước khi breaker ghi nhận slow call; nếu không có bulkhead, nhiều call vẫn có thể chờ cùng lúc.

### 8.2. Cấu hình minh họa

~~~java
CircuitBreakerConfig config =
    CircuitBreakerConfig.custom()
        .failureRateThreshold(50)
        .slowCallRateThreshold(50)
        .slowCallDurationThreshold(Duration.ofMillis(700))
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .waitDurationInOpenState(Duration.ofSeconds(5))
        .permittedNumberOfCallsInHalfOpenState(3)
        .build();

CircuitBreaker breaker =
    CircuitBreaker.of("inventory", config);
~~~

Các ngưỡng trên là ví dụ, không phải giá trị production mặc định. Cần chọn theo traffic volume, baseline latency và SLO; với ít request, một vài failure không nên làm breaker chuyển trạng thái quá nhạy.

### 8.3. Fallback phải đúng nghiệp vụ

Fallback chỉ an toàn khi có thể cung cấp kết quả thay thế có ý nghĩa. Có thể trả trạng thái temporarily unavailable nếu inventory chưa thể xác nhận; có thể hiển thị cache stale cho truy vấn đọc nếu nghiệp vụ cho phép và đánh dấu freshness; không được tự giả định payment thành công khi payment service timeout; không được hạ thao tác ghi quan trọng thành success giả.

Nếu dependency bắt buộc để bảo đảm tính đúng đắn, trả Fault/error có thể retry thay vì fallback sai. Fault code nên phân biệt dependency unavailable với business rejection.

## 9. Retry có giới hạn và tránh retry storm

### 9.1. Khi nào retry?

Retry có thể phù hợp với lỗi tạm thời như connection reset, 503 hoặc throttling có retry hint. Không retry lỗi không thể tự hết như SOAP schema validation failure; UsernameToken/Signature invalid; authorization denied; business rule rejection; request malformed.

Retry chỉ an toàn với side-effecting operation khi có idempotency key/dedup semantics.

### 9.2. Exponential backoff và jitter

\[
t_n = \min(t_{max}, t_{base} \times 2^n) + jitter
\]

Backoff tăng khoảng cách giữa các lần thử. Jitter làm các client không retry cùng lúc. Không dùng retry tức thì trong vòng lặp vì nhiều client có thể tạo retry storm ngay khi dependency phục hồi.

Ví dụ cấu hình Resilience4j Retry:

~~~java
RetryConfig retryConfig = RetryConfig.custom()
    .maxAttempts(3)
    .waitDuration(Duration.ofMillis(200))
    .retryExceptions(TransientDependencyException.class)
    .ignoreExceptions(
        InvalidSoapRequestException.class,
        AccessDeniedException.class)
    .build();
~~~

Ví dụ trên có wait duration cố định; để có exponential backoff/jitter, cấu hình interval function phù hợp với Resilience4j version. Xác định maxAttempts bao gồm lần gọi đầu hay chỉ số retry theo API và kiểm tra tổng latency budget.

### 9.3. Retry budget

Nếu mỗi request có 3 attempts và 100 request/giây thất bại, dependency có thể nhận đến 300 attempts/giây. Vì vậy phải giới hạn attempts; giới hạn tổng thời gian retry; chỉ retry lỗi transient đã allowlist; có jitter; không retry đồng thời ở mọi layer (gateway + client + service + SDK) mà không tính tổng attempts; có circuit breaker và rate limit; giữ idempotency key xuyên các lần retry.

Không retry khi deadline caller đã hết.

## 10. Timeout và connection pool cho downstream HTTP/SOAP clients

Một WebServiceTemplate gọi service khác cần giới hạn thời gian chờ và pool:

- Connection request/acquisition timeout: chờ lấy connection từ pool;
- Connect timeout: thời gian thiết lập TCP/TLS;
- Read/response timeout: chờ dữ liệu phản hồi;
- Max total connections và per-route connections;
- Idle connection eviction/validation;
- Keep-alive policy và TLS trust configuration.

Các thuộc tính cụ thể phụ thuộc WebServiceMessageSender/HTTP client implementation (JDK, Apache HttpClient hoặc thư viện khác) và Spring-WS/Spring Framework version. Đừng giả định mọi WebServiceTemplate đều có cùng property timeout. Hãy cấu hình trên sender và test timeout qua HTTP server chậm.

Connection pool phải phù hợp concurrency budget. Nếu bulkhead cho phép 40 call đồng thời nhưng HTTP pool chỉ có 8 connection, 32 call có thể chờ acquisition; nếu pool có 200 connection nhưng downstream chỉ phục vụ 20, caller có thể gây overload downstream. Căn chỉnh bulkhead, pool và remote service quota.

## 11. Database và transaction boundaries

Database là dependency quan trọng của SOAP endpoint:

- Giới hạn connection pool và acquisition timeout;
- Đặt query/transaction timeout;
- Tránh giữ connection trong khi gọi HTTP dependency;
- Tránh transaction dài bao trùm nhiều remote calls;
- Dùng unique constraint/idempotency key để chống duplicate;
- Giới hạn batch size/page size;
- Dùng index và query plan phù hợp;
- Kiểm tra lock wait và deadlock.

Không giữ transaction mở trong lúc chờ một SOAP downstream chậm nếu có thể tách thành workflow/outbox. Transaction dài giữ connection và lock, khiến request khác cũng phải chờ rồi tăng saturation.

Với operation bất đồng bộ, ghi receipt/outbox trong transaction ngắn, sau đó worker bounded xử lý downstream. Outbox dispatcher cần bounded concurrency, retry budget, dead-letter policy và idempotent consumer.

## 12. Giới hạn XML, JAXB và attachment

### 12.1. Payload size ảnh hưởng heap nhiều hơn số byte truyền

XML text parse thành object graph; cùng một request body có thể cần nhiều lần kích thước byte trong heap do String, DOM/SAAJ nodes, JAXB objects và collection. Attachment có thể nằm trong memory hoặc temp files tùy message factory/streaming mode.

Benchmark phải đo request body bytes; parsed XML/message object count; peak heap và allocation rate; GC pause/time; số lượng/kích thước attachment; response object graph và serialized response size.

### 12.2. JAXB collection và data pagination

Không trả hàng chục nghìn record trong một SOAP response chỉ vì XSD cho phép unbounded list. Đặt maximum item count, page size và total response bytes; cung cấp pagination/cursor operation nếu contract cần.

XSD maxOccurs có thể giúp contract hạn chế số phần tử, nhưng phải được enforcement ở validation path thực tế. Nếu không bật schema validation hoặc client/server bỏ qua constraint, chỉ khai báo XSD không bảo đảm runtime limit.

### 12.3. MTOM và attachment limits

MTOM tối ưu binary data trong SOAP, nhưng không tự giới hạn file size hay bảo đảm streaming không dùng heap. Đặt max attachment count; max bytes per attachment; max aggregate message bytes; MIME part/header limits; allowed content types; malware scanning timeout/concurrency; quota storage và cleanup temporary files.

Attachment scanning là dependency đắt; nên có bulkhead riêng. Một file lớn hoặc virus scan chậm không được giữ hết SOAP worker threads.

## 13. Deadline, cancellation và client disconnect

HTTP client có thể disconnect hoặc timeout trong khi server vẫn tiếp tục chạy nghiệp vụ:

- Client timeout không có nghĩa server đã dừng;
- Thread interrupt không nhất thiết hủy được JDBC hoặc remote call;
- Connection close không tự rollback giao dịch đã commit;
- Retry từ client có thể tạo duplicate operation.

Thiết kế operation có deadline rõ, truyền remaining budget xuống dependencies, dừng bước chưa bắt đầu khi deadline đã hết và hỗ trợ idempotency/status query với operation dài. Không hủy transaction giữa chừng theo cách phá tính nhất quán.

Với công việc lâu, cân nhắc asynchronous receipt pattern:

1. SOAP request tạo operation và trả accepted cùng receipt ID;
2. worker bounded xử lý;
3. client gọi status operation hoặc nhận callback đã xác thực;
4. operation state bền vững và có retention;
5. duplicate request ID trả cùng receipt/result.

Đây là thay đổi business contract/WSDL cần thiết kế rõ, không thể chỉ bật async annotation là xong.

## 14. Graceful degradation và ưu tiên nghiệp vụ

| Thành phần | Có thể degradation? | Ví dụ |
| --- | --- | --- |
| Inventory confirmation cho create order | Thường không | Không tạo order nếu không xác nhận tồn kho. |
| Product description enrichment | Có thể | Trả dữ liệu cache có nhãn freshness. |
| Payment authorization | Không được giả success | Từ chối tạm thời hoặc pending theo contract. |
| Audit/security validation | Không | Không bỏ qua để tăng throughput. |
| Optional recommendation | Có thể | Bỏ qua recommendation khi service quá tải. |
| Notification | Thường async được | Ghi outbox và gửi sau. |

Không degradation security checks, schema validation hoặc authorization theo kiểu “bypass khi hệ thống bận”. Khi auth service tạm unavailable, fail closed hay dùng cache cần dựa theo threat model và thời hạn cache; phải được định nghĩa rõ.

## 15. Metrics và observability cho overload

### 15.1. Các metric nên có

~~~text
soap_requests_total{operation, outcome}
soap_request_duration_seconds{operation}
soap_requests_in_flight{operation}
soap_admission_rejected_total{reason, operation}
soap_request_payload_bytes{operation}
soap_executor_active_threads{name}
soap_executor_queue_depth{name}
soap_executor_rejected_total{name}
soap_dependency_duration_seconds{dependency, outcome}
soap_dependency_timeouts_total{dependency}
soap_circuit_breaker_state{dependency}
soap_bulkhead_rejected_total{dependency}
soap_db_pool_active_connections
soap_db_pool_pending_acquires
soap_attachment_bytes{type}
~~~

Đây là tên metric gợi ý, không phải metrics tự động được Spring-WS cung cấp nguyên trạng. Có thể instrument qua Micrometer, Spring Boot Actuator, HTTP client metrics, datasource pool metrics và application counters.

### 15.2. Không đưa ID cá nhân thành label

Tránh dùng email, JID, customer ID, order ID, request ID hoặc URL đầy đủ làm Prometheus label. Cardinality sẽ tăng mạnh và có thể rò dữ liệu. Dùng operation, dependency, outcome, partner tier hoặc bounded reason enum; correlation ID giữ trong log/trace thay vì metric label.

### 15.3. Logs và traces

Log có ích khi gồm correlation/request ID; SOAP operation QName; partner/tenant ID đã chuẩn hóa và policy cho phép; payload size bucket; queue wait và service duration; dependency name/outcome; timeout/retry count; rejection category và circuit state.

Không log raw SOAP Envelope, WS-Security token, signature, attachment hoặc PII mặc định. Trace spans nên phân biệt parse/security, endpoint, DB và downstream calls; đặt sampling/retention phù hợp để tracing không tự trở thành nguồn overload.

## 16. Load testing, stress testing và soak testing

| Test | Mục tiêu |
| --- | --- |
| Baseline/load | Đo throughput/latency dưới tải dự kiến. |
| Capacity | Tăng tải để xác định vùng throughput ổn định tối đa. |
| Stress | Vượt công suất để xác minh từ chối có kiểm soát và phục hồi. |
| Spike | Tăng traffic đột ngột để kiểm tra burst/queue/recovery. |
| Soak | Giữ tải lâu để phát hiện leak, queue drift, pool exhaustion và GC degradation. |
| Dependency fault | Làm downstream chậm/lỗi để xác minh timeout, bulkhead, breaker và retry. |

Kịch bản phải đo request SOAP nhỏ và lớn; WS-Security Signature; XML nhiều nested items; MTOM/attachment theo nhiều size tiers; operation đọc và ghi; downstream latency p50/p95/p99 tăng; connection pool exhausted; HTTP 429/503, socket reset, timeout; burst traffic từ một và nhiều partner; client disconnect/retry; mixed workload để kiểm tra fairness.

Đặt tiêu chí trước khi chạy: p95/p99 latency trong SLO ở target load; error/rejection rate phân biệt lỗi hệ thống với overload policy; memory/GC không tăng liên tục; queue depth/age không tăng vô hạn; DB/HTTP pools không cạn kéo dài; dependency recovery không tạo retry storm; overload response đúng; sau spike hệ thống phục hồi baseline trong thời gian xác định.

Không chọn một con số TPS chung cho mọi SOAP service. Công suất phụ thuộc payload, crypto, database, hardware, topology và downstream. Phải benchmark trên cấu hình gần production.

## 17. Ví dụ tình huống: inventory dependency chậm

Giả sử SubmitOrder gọi inventory service. Khi inventory p99 tăng từ 100 ms lên 3 giây:

1. SOAP request giữ thread lâu hơn;
2. Concurrency tăng theo Little's Law;
3. HTTP connection pool tới inventory bị chiếm;
4. Request chờ connection hoặc response;
5. Client timeout rồi retry;
6. Inventory nhận nhiều attempts hơn dù đang chậm;
7. SOAP server cạn threads và các operation nhẹ cũng bị ảnh hưởng.

Một thiết kế bảo vệ gồm timeout connect/read và deadline toàn operation; bulkhead giới hạn inventory calls đồng thời; circuit breaker mở khi failure/slow-call threshold vượt ngưỡng; retry tối đa ít lần với exponential backoff + jitter chỉ cho lỗi transient; không retry sau deadline; nếu inventory là điều kiện bắt buộc, trả temporary dependency Fault; các query status nhẹ dùng pool/concurrency độc lập; metrics theo dõi wait time, in-flight, rejection, breaker state và retry attempts.

Điều này giữ inventory overload trong phạm vi đã định và không để nó chiếm hết capacity của SOAP service.

## 18. Runbook xử lý quá tải

### 18.1. Dấu hiệu

- p95/p99 latency tăng;
- HTTP 429/503 hoặc SOAP overload Fault tăng;
- Active threads/requests sát giới hạn;
- Executor queue depth/age tăng;
- DB pending connection acquisition tăng;
- Downstream timeout/circuit breaker OPEN;
- Heap/GC pressure tăng hoặc pod restart/OOM.

### 18.2. Trình tự xử lý

1. Xác định operation, partner hoặc dependency gây tải; xem rate, payload bytes và rejection reason.
2. Kiểm tra active threads, executor queue, DB pool và HTTP client pool.
3. Xác định overload nằm ở parse/crypto, database hay dependency.
4. Bật/điều chỉnh rate limit hoặc load shedding theo policy đã phê duyệt; tránh tăng concurrency mù quáng.
5. Kiểm tra timeout, retry attempts và circuit breaker state; dừng retry storm nếu cần.
6. Tạm ngưng workload tùy chọn hoặc batch nặng; giữ security checks.
7. Khi dependency phục hồi, để circuit breaker probe/half-open theo cấu hình; theo dõi queue drain và p99.
8. Ghi lại timeline, peak metrics, request categories và điều chỉnh capacity/contract limits.

Không tăng max threads, queue capacity hoặc connection pool chỉ dựa trên triệu chứng. Nếu bottleneck ở DB, tăng worker threads thường làm DB overload nặng hơn.

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Queue càng lớn càng an toàn | Queue vô hạn hoặc quá lớn biến overload thành latency/memory growth. |
| Tăng HTTP threads luôn tăng throughput | Có thể làm cạn DB/dependency pool và tăng context switching. |
| Timeout là đủ để bảo vệ dependency | Cần bulkhead, pool limit, retry budget và circuit breaker phù hợp. |
| Circuit breaker thay timeout | Call có thể vẫn giữ thread rất lâu trước khi breaker nhận biết slow call. |
| Retry mọi SOAP Fault | Validation, security, authorization và business Fault thường không retry được. |
| Client timeout nghĩa server đã dừng | Server có thể vẫn xử lý/đã commit; cần idempotency/status. |
| XSD maxOccurs tự giới hạn runtime | Chỉ hiệu lực nếu validation thực sự kiểm tra schema; cần byte/resource limits nữa. |
| MTOM tự streaming không tốn heap | Message factory, attachment handling và client có thể buffer; phải đo thực tế. |
| Mỗi instance có 20 permits nghĩa cluster có tối đa 20 | 5 replicas có thể cho tới 100 permits; tính cluster budget. |
| Health endpoint xanh nghĩa dependency khỏe | Health check không chứng minh capacity hoặc latency của mọi operation. |
| Fallback luôn tốt hơn lỗi | Fallback sai với payment/inventory/auth có thể tạo kết quả nghiệp vụ không nhất quán. |
| Tắt WS-Security khi quá tải giúp cứu hệ thống | Bỏ security check tạo lỗ hổng; phải shed load ở ranh giới an toàn. |

## 20. Checklist thiết kế giới hạn tải

### Ingress và SOAP message

- [ ] Có body/header/attachment size limit tại gateway/container.
- [ ] Có rate limit theo partner/identity và quota theo operation cost.
- [ ] XML parser được harden, external entities/DTD bị kiểm soát.
- [ ] Có giới hạn MIME parts, XML depth, collection count và response size.
- [ ] Có timeout cho upload/idle connection và request deadline.

### Concurrency và resource pools

- [ ] HTTP workers, executors và queues có giới hạn rõ.
- [ ] Queue capacity/age có metrics và rejection policy.
- [ ] Bulkhead riêng cho dependency hoặc operation đắt.
- [ ] Semaphore/pool limit phù hợp DB và downstream capacity.
- [ ] Tổng cluster concurrency được tính từ số replica.
- [ ] Không dùng caller-runs/queue lớn ngoài chủ đích.

### Dependencies và resilience

- [ ] Connect/acquire/read/deadline timeouts hữu hạn.
- [ ] Circuit breaker có threshold phù hợp traffic/latency baseline.
- [ ] Retry chỉ transient, giới hạn attempts/time budget và có jitter.
- [ ] Side-effecting operation có idempotency/dedup.
- [ ] Fallback không giả success cho payment/inventory/security.
- [ ] Transaction DB không giữ lâu trong lúc chờ remote calls.

### Observability và verification

- [ ] Có metrics active/in-flight, queue, rejection, latency percentiles.
- [ ] Có dependency timeout/retry/bulkhead/circuit metrics.
- [ ] Logs/traces có correlation nhưng không chứa SOAP secrets/raw payload.
- [ ] Có load, stress, spike, soak và dependency fault tests.
- [ ] Acceptance criteria gồm SLO và recovery time.
- [ ] Có runbook overload và quy trình điều chỉnh quota/capacity.

## 21. Câu hỏi tự kiểm tra

1. Little's Law liên hệ queue/concurrency với throughput và latency như thế nào?
2. Vì sao average latency không đủ để thiết kế capacity?
3. Tại sao giới hạn request body cần đặt ở gateway/container trước SOAP parsing?
4. Khác biệt giữa admission control, concurrency limit, rate limiting và quota là gì?
5. Vì sao queue vô hạn có thể gây OOM hoặc latency collapse?
6. Bounded executor và semaphore bảo vệ loại tài nguyên nào?
7. Khi nào CallerRunsPolicy có thể làm tình hình tệ hơn?
8. Backpressure trong HTTP SOAP request/response khác Reactive Streams backpressure thế nào?
9. Bulkhead khác circuit breaker ra sao?
10. Vì sao circuit breaker không thay timeout?
11. Làm thế nào phân bổ timeout ngân sách cho nhiều dependencies?
12. Những lỗi nào không nên retry?
13. Exponential backoff và jitter giúp tránh retry storm ra sao?
14. Retry budget cần tính cả gateway/client/service layers như thế nào?
15. Vì sao client timeout không có nghĩa business operation chưa commit?
16. Làm sao bảo đảm idempotency khi retry operation ghi?
17. Những giới hạn nào cần đặt cho MTOM attachments?
18. Vì sao mỗi instance có cùng semaphore permits không đồng nghĩa cluster có cùng giới hạn?
19. Metrics nào giúp xác định bottleneck nằm ở DB, XML parser hay dependency?
20. Stress test khác soak test thế nào?
21. Khi nào graceful degradation không được phép?
22. Vì sao không nên tăng max threads mù quáng khi DB pool đã bão hòa?

## 22. Bài tập thực hành

**Bối cảnh:** SOAP endpoint SubmitOrder nhận XML order có thể kèm attachment, xác minh WS-Security, đọc inventory và ghi database. Inventory đôi lúc chậm hoặc trả 503. Bạn cần giữ SLO của operation đọc trạng thái đơn hàng trong lúc SubmitOrder bị tải cao.

### Phần A — Đo baseline

1. Tạo load profile cho request nhỏ, request nhiều line items và request có attachment.
2. Đo throughput, p50/p95/p99, heap, GC, active threads, DB connections và HTTP pool.
3. Tính concurrency trung bình bằng Little's Law tại target throughput/latency.
4. Xác định ngân sách DB connections, inventory concurrency và worker threads.

### Phần B — Admission và bounded resources

5. Đặt request body/attachment limits tại HTTP ingress.
6. Thêm bounded executor cho attachment processing và rejection mapping.
7. Thêm concurrency guard riêng cho inventory calls.
8. Cấu hình queue capacity, queue age và overload response.
9. Tạo burst test và xác minh service reject có kiểm soát thay vì queue vô hạn.

### Phần C — Dependency resilience

10. Cấu hình connection acquisition/connect/read timeouts cho inventory client.
11. Thêm bulkhead và circuit breaker; test OPEN/HALF_OPEN/CLOSED.
12. Thêm retry chỉ cho lỗi transient với max attempts, deadline và jitter.
13. Test 503, connection reset, response chậm và timeout.
14. Test duplicate SubmitOrder sau timeout; xác minh idempotency ngăn duplicate write.

### Phần D — Giữ operation quan trọng

15. Tạo workload đồng thời: SubmitOrder nặng và GetOrderStatus nhẹ.
16. Cô lập bulkhead/connection pool để request đọc không bị chiếm hết capacity.
17. Khi inventory unavailable, đảm bảo SubmitOrder trả temporary failure/pending đúng contract; không giả success.
18. Đảm bảo WS-Security và authorization vẫn chạy khi hệ thống quá tải.

### Phần E — Đánh giá

19. Chạy load, spike, stress và soak tests.
20. Ghi lại ngưỡng throughput ổn định, p99, rejection rate, queue age, resource utilization và recovery time.
21. Viết runbook xử lý DB pool exhaustion, dependency outage, queue saturation và retry storm.
22. Điều chỉnh limits, sau đó chạy lại đúng kịch bản để chứng minh SLO.

**Tiêu chí đạt:** tải vượt công suất bị từ chối có kiểm soát; request/attachment không thể làm heap hoặc queue tăng vô hạn; inventory outage không chiếm hết thread/connection; retry không tạo storm hoặc duplicate side effect; operation đọc quan trọng vẫn có capacity; security checks không bị bypass; metrics và runbook cho phép chẩn đoán/recovery.

## 23. Tài liệu tham khảo chính thức

- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): WebServiceTemplate, message factories, transports và server/client configuration.
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): executor/task execution và cấu hình thread pools.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, lifecycle và scheduling abstractions.
- [Resilience4j Documentation](https://resilience4j.readme.io/docs): Bulkhead, CircuitBreaker, Retry, RateLimiter và TimeLimiter.
- [Micrometer Documentation](https://docs.micrometer.io/): metrics instrumentation và observation.
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/): tracing và instrumentation cho JVM services.
- [OWASP XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): XML parser hardening và phòng chống XML external entity attacks.

Các giá trị executor/timeout/bulkhead trong bài chỉ là ví dụ để giải thích cách cấu hình. Production limits phải được benchmark trên payload, crypto, database, JVM, container và downstream topology thực tế; kiểm tra API theo version dependency của dự án.

## 24. Tổng kết

**Giới hạn tải là một hệ thống nhiều lớp:** ingress giới hạn bytes/rate; Servlet và Spring-WS giới hạn request/concurrency; parser/JAXB kiểm soát XML và object graph; bounded executor/queue giữ công việc trong ngân sách; timeout, bulkhead, circuit breaker và retry budget bảo vệ dependencies; metrics và load tests xác nhận hệ thống chịu tải và phục hồi.

Trong SOAP service doanh nghiệp, không nên nhận vô hạn request chỉ để tránh trả lỗi. Hãy đặt capacity theo SLO, từ chối sớm khi hết ngân sách, giữ pool/queue hữu hạn, không retry lỗi không thể phục hồi, bảo vệ side effects bằng idempotency và chỉ degradation ở phần nghiệp vụ cho phép. Điều đó giữ một dependency lỗi trong phạm vi của nó thay vì biến thành sự cố toàn hệ thống.

**Ghi nhớ:** throughput bền vững quan trọng hơn request rate được nhận; queue bounded quan trọng hơn queue dài; timeout phải đi cùng bulkhead và retry budget; overload response có kiểm soát tốt hơn để hệ thống cạn kiệt tài nguyên.
