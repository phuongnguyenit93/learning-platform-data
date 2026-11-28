# Giới hạn luồng servlet, số kết nối và số yêu cầu đang xử lý

## 1. Vì sao phải giới hạn concurrency của SOAP service?

Một Spring Web Services endpoint có thể xử lý SOAP request trong vài mili giây khi hệ thống khỏe, nhưng một request khác có thể giữ tài nguyên vài giây vì truy vấn database, gọi SOAP partner, đọc attachment hoặc chờ network. Nếu server nhận request nhanh hơn khả năng hoàn tất, số request đang xử lý tăng dần. Thread servlet, connection database, socket HTTP outbound, heap và buffer đều có thể bị sử dụng hết.

Khi không có giới hạn, hệ thống dễ rơi vào chuỗi sự cố: latency tăng, thread chờ lâu, connection pool cạn, request timeout, client retry, tải tiếp tục tăng và service càng khó phục hồi. Giới hạn concurrency là một phần của **capacity management và overload protection**, không chỉ là tinh chỉnh một con số trong Tomcat.

Module **SPRING_WEB_SERVICES** học phát triển SOAP theo hướng contract-first, thiết kế XSD/WSDL, JAXB/OXM, endpoint và SOAP client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Trong chương **Hiệu năng và vận hành**, bài này tập trung vào giới hạn luồng servlet, số kết nối và số yêu cầu đang xử lý của SOAP service.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt connection, request, servlet thread, worker thread và in-flight request.
2. Mô tả đường đi của SOAP request qua servlet container, Spring-WS và downstream.
3. Dùng Little’s Law để ước lượng concurrency theo throughput và latency.
4. Phân biệt thread pool, HTTP connection pool và database connection pool.
5. Cấu hình bounded executor, max threads, accept queue và connection limits.
6. Thiết kế admission control, backpressure, timeout và load shedding.
7. Giới hạn tải theo partner/operation để một tích hợp không chiếm hết năng lực.
8. Nhận biết rủi ro async servlet/async task khi chuyển việc sang executor khác.
9. Theo dõi queue depth, active threads, in-flight requests, pool exhaustion và latency.
10. Xây load test, capacity test và overload test cho Spring-WS service.

## 2. Phân biệt connection, request và thread

Các khái niệm này liên quan nhưng không thể thay thế nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| TCP connection | Kênh truyền giữa client và server | Một keep-alive socket |
| HTTP request | Một lần trao đổi HTTP trên connection | POST SOAP Envelope |
| Servlet request | Request được container dispatch vào servlet pipeline | /soap/shipment |
| Servlet thread | Thread container dùng để xử lý request đồng bộ | http-nio-8080-exec-17 |
| In-flight request | Request đã nhận nhưng chưa hoàn tất | Chờ DB hoặc SOAP partner |
| Outbound connection | Kết nối app dùng gọi dependency | HTTP connection tới partner |
| DB connection | Session từ application tới database | Một connection HikariCP |
| Async worker | Thread executor khác tiếp tục xử lý tác vụ | soap-async-4 |

Một HTTP keep-alive connection có thể phục vụ nhiều requests tuần tự. HTTP/2 có thể multiplex nhiều streams trên một connection. Vì vậy số socket không nhất thiết bằng số request đang xử lý.

Tương tự, một request đồng bộ thường chiếm một servlet thread trong thời gian xử lý. Nếu request gọi executor bất đồng bộ rồi trả response, worker thread có thể tiếp tục làm việc sau khi servlet thread đã được trả. Cần đếm concurrency ở từng tầng, không chỉ nhìn một pool.

## 3. Đường đi của một SOAP request trong Spring-WS

Một ứng dụng Spring-WS chạy trên servlet stack thường có luồng khái quát:

~~~mermaid
flowchart TD
    A[Client TCP connection] --> B[Servlet connector]
    B --> C[Servlet thread admission]
    C --> D[Filters / Spring Security]
    D --> E[MessageDispatcherServlet]
    E --> F[SOAP message factory / parsing]
    F --> G[Endpoint interceptors]
    G --> H[Endpoint method]
    H --> I[Application service]
    I --> J[DB connection pool]
    I --> K[Outbound HTTP connection pool]
    J --> L[Business result]
    K --> L
    L --> M[SOAP marshalling / response]
    M --> N[Write HTTP response]
~~~

Không phải mọi request dùng tất cả các tầng. Nhưng khi phân tích tải cần ghi rõ request giữ tài nguyên nào ở từng thời điểm:

- Connector có thể giữ socket và request buffers.
- Servlet thread có thể bị giữ trong suốt synchronous processing.
- XML parser/marshaller dùng CPU và heap.
- WSS4J có thể dùng CPU cho signature, decryption và certificate validation.
- Service có thể giữ DB connection trong transaction.
- Outbound SOAP call giữ HTTP connection và thường giữ thread đang chờ response.
- Response serialization và network write tiếp tục sử dụng CPU/buffer.

Một request chậm có thể chiếm nhiều tài nguyên cùng lúc, dù chỉ là một request logic.

## 4. Mô hình đồng bộ: vì sao servlet thread bị chiếm?

Trong flow đồng bộ, servlet thread tiếp tục thực thi cho đến khi response được hoàn tất. Ví dụ:

~~~java
@Endpoint
public class ShipmentEndpoint {
    private final ShipmentApplicationService service;

    public ShipmentEndpoint(ShipmentApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = "urn:example:shipment:v1",
        localPart = "GetShipmentStatusRequest")
    @ResponsePayload
    public GetShipmentStatusResponse getStatus(
            @RequestPayload GetShipmentStatusRequest request) {
        ShipmentStatus status =
            service.getStatus(request.getShipmentId());
        return toResponse(status);
    }
}
~~~

Nếu `service.getStatus()` gọi database rồi gọi thêm partner SOAP service đồng bộ, servlet thread thường nằm chờ trong toàn bộ thời gian đó. Network I/O có thể không tiêu thụ nhiều CPU, nhưng thread vẫn bị chiếm và không thể xử lý request khác.

### 4.1. Chậm không đồng nghĩa CPU cao

Có thể thấy CPU chỉ 25% nhưng servlet thread pool đã hết vì threads đang chờ DB connection, lock/transaction, partner SOAP endpoint, DNS/TLS handshake hoặc response body của attachment. Do đó CPU utilization một mình không đủ kết luận hệ thống còn capacity.

## 5. Little’s Law: throughput, latency và concurrency

Little’s Law:

\[
L = \lambda W
\]

Trong đó L là số phần tử trung bình đang ở trong boundary được đo, λ là throughput trung bình (requests/second), W là thời gian trung bình một request ở trong boundary (seconds).

Ví dụ service xử lý 120 requests/second và latency trung bình 0,25 giây:

\[
L = 120 \times 0.25 = 30
\]

Trung bình có khoảng 30 requests đang được xử lý hoặc chờ trong boundary đã đo.

Nếu latency tăng lên 2 giây trong khi throughput vẫn 120 requests/second:

\[
L = 120 \times 2 = 240
\]

Hệ thống cần giữ 240 requests in flight để duy trì throughput đó. Nếu servlet executor chỉ cho 100 request đồng thời, queue hoặc client-visible latency sẽ tăng; cuối cùng có thể timeout hoặc reject.

### 5.1. Little’s Law không tự cho biết thread pool tối ưu

Cần phân biệt L của request boundary, active servlet threads, requests đang chờ queue, async tasks, DB connections và outbound HTTP connections. Little’s Law áp dụng cho một boundary ổn định với throughput/latency đo nhất quán. Không lấy throughput endpoint rồi nhân latency downstream để kết luận số servlet threads trực tiếp.

### 5.2. Ví dụ tính nhanh

| Throughput | Average latency | Average in-flight |
| ---: | ---: | ---: |
| 50 req/s | 100 ms | 5 |
| 100 req/s | 250 ms | 25 |
| 200 req/s | 500 ms | 100 |
| 300 req/s | 1 s | 300 |
| 100 req/s | 2 s | 200 |

Đây là số trung bình. Capacity planning phải xét peak, latency distribution (p95/p99), burstiness, CPU, downstream limits và headroom.

## 6. Vì sao tăng max threads có thể làm hệ thống tệ hơn?

Tăng servlet threads có thể giúp khi thiếu worker và downstream còn capacity. Nhưng nếu bottleneck là database hoặc partner SOAP endpoint, thêm threads có thể tạo nhiều requests chờ DB, nhiều outbound calls hơn partner chịu được, tăng heap pressure, context switching, timeout và retry đồng thời. Không dùng số threads lớn để che dependency chậm. Xác định bottleneck bằng metrics và profiling trước.

## 7. Servlet connector và worker thread pool

Servlet container quản lý network connector, accept queue và worker threads. Tên cấu hình phụ thuộc container:

- Tomcat có connector maxThreads, minSpareThreads, acceptCount, maxConnections.
- Jetty có thread pool và connector accept queue riêng.
- Undertow có I/O threads và worker task threads với mô hình khác.
- Spring Boot properties thay đổi theo version/container.

Không copy property Tomcat vào Jetty/Undertow rồi kỳ vọng cùng semantics.

### 7.1. Ví dụ cấu hình Tomcat trong Spring Boot

~~~yaml
server:
  tomcat:
    threads:
      max: 120
      min-spare: 16
    max-connections: 500
    accept-count: 80
    connection-timeout: 5s
~~~

Đây là cấu hình minh họa, không phải sizing production. Kiểm version Spring Boot/Tomcat và property thực tế. max-connections không phải số SOAP requests đồng thời; accept-count là backlog behavior khi workers bận theo semantics connector, không phải queue nghiệp vụ bền vững.

### 7.2. maxConnections và maxThreads khác nhau

- maxConnections: số connections connector quản lý.
- maxThreads: giới hạn worker threads xử lý request.
- acceptCount: backlog/queue behavior khi worker capacity bận, tùy connector.

Server có thể giữ nhiều keep-alive connections hơn worker threads. HTTP/2 streams và connector implementation cũng làm quan hệ phức tạp hơn. Quan sát active connections, request rate, active threads và queue.

## 8. Accept queue không phải backpressure đầy đủ

Accept queue/backlog là nơi kết nối chờ theo hành vi OS/container. Nó không thay admission control ở application:

- Client có thể chờ lâu rồi timeout.
- Queue dài làm latency tăng dù throughput không tăng.
- Queue đầy có thể khiến connection bị từ chối/reset.
- Queue quá lớn che overload cho tới khi nhiều clients cùng timeout.

Nên fail sớm và có kiểm soát khi capacity hết thay vì giữ request lâu không giới hạn.

### 8.1. Bounded queues

Nếu có application executor riêng, dùng bounded queue với capacity rõ. Queue vô hạn khiến backlog và memory có thể tăng không giới hạn.

Queue ngắn có thể hấp thụ burst nhỏ; queue dài cần rationale từ SLA và deadline. Với synchronous servlet requests, quyết định connector behavior và application admission policy thay vì thêm queue không cần thiết.

## 9. Connection pool tới database

SOAP service thường dùng connection pool. Với HikariCP, các thông số thường gặp gồm maximumPoolSize, minimumIdle, connectionTimeout, idleTimeout và maxLifetime.

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 24
      minimum-idle: 8
      connection-timeout: 1500
      idle-timeout: 600000
      max-lifetime: 1740000
~~~

Giá trị milliseconds chỉ minh họa. Không đặt maximumPoolSize bằng maxThreads máy móc. Database có giới hạn connections, CPU, IOPS và lock contention; pool quá lớn có thể làm DB chậm hơn.

### 9.1. Sizing DB pool theo tổng ứng dụng

Nếu có 5 replicas, mỗi replica pool tối đa 24 connections, tổng potential DB connections là:

\[
5 \times 24 = 120
\]

Cộng services khác, migration jobs, reporting, admin tools và monitoring. Tổng phải nằm trong budget DB có headroom. Xem connections thực tế, không chỉ cấu hình một pod.

### 9.2. Hạn chế giữ DB connection quá lâu

Không gọi SOAP partner chậm trong khi giữ transaction/DB connection nếu không cần. Anti-pattern:

~~~java
@Transactional
public ShipmentResult process(String id) {
    Shipment shipment = repository.findById(id).orElseThrow();
    PartnerResponse response = partnerSoapClient.call(shipment);
    shipment.apply(response);
    return mapper.toResult(shipment);
}
~~~

Transaction có thể giữ connection/lock trong suốt outbound network call. Thiết kế lại để rút ngắn transaction, dùng state machine/outbox/saga khi workflow phức tạp và bảo vệ race conditions.

## 10. Outbound HTTP connection pool cho SOAP client

SOAP service có thể đồng thời gọi nhiều partner. HTTP client/connection manager có giới hạn total connections, per-route limits, connection acquisition timeout, connect/TLS timeout, response/read timeout và keep-alive behavior.

Theo dõi tổng connections, per-partner connections, pending lease requests, lease wait, connect latency, response latency, idle eviction và stale connection failures.

### 10.1. Per-route limits

Giới hạn tổng pool không đảm bảo một partner không chiếm hết. Dùng per-route limit hoặc tách HTTP clients theo partner profile. Partner chậm không nên giữ tất cả outbound connections cho đối tác khác.

### 10.2. Không tạo HTTP client cho mỗi request

Tạo HTTP client/pool dùng chung theo partner profile và lifecycle hợp lý. Client mới cho từng SOAP request làm mất pooling, tăng handshake/DNS/socket churn và khó giới hạn resource.

## 11. Ba pool phải được sizing cùng nhau

Một SOAP request synchronous có thể cần servlet worker, DB connection trong transaction và outbound HTTP connection khi gọi partner. Các pool không nhất thiết cùng size.

~~~text
Servlet worker threads:          120
Database pool per instance:       24
Partner-A HTTP connections:       16
Partner-B HTTP connections:       12
Async worker threads:              8
~~~

Đây là ví dụ capacity profile, không phải khuyến nghị. Nếu mọi request path cần DB và Partner A, throughput bị ràng buộc bởi bottleneck nhỏ nhất cùng service time. Request chỉ đọc DB hoặc không gọi partner có demand khác.

### 11.1. Kiểm dependency graph

| SOAP operation | DB demand | Partner HTTP demand | CPU demand |
| --- | --- | --- | --- |
| GetShipmentStatus | 1 short query | 0 | Thấp |
| CreateShipment | 1 transaction | 1 Partner A call | Trung bình |
| CancelShipment | 1 transaction | 1 Partner B call | Trung bình |
| VerifySignedDocument | 0 hoặc 1 | 0 | CPU cao do crypto |
| UploadDocument | 1 metadata write | 1 storage call | I/O/memory cao |

Không capacity plan chỉ dựa average request nếu workload có resource demands khác nhau.

## 12. Giới hạn số request đang xử lý ở application layer

maxThreads giới hạn worker concurrency nhưng không tạo policy theo operation/partner. Có thể dùng admission control/semaphore ở application boundary:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class RequestAdmission {
    private final Semaphore permits;

    public RequestAdmission(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    public Permit acquire(long timeout, TimeUnit unit)
            throws InterruptedException {
        if (!permits.tryAcquire(timeout, unit)) {
            return null;
        }
        return new Permit(permits);
    }

    public static final class Permit implements AutoCloseable {
        private final Semaphore semaphore;
        private boolean closed;

        private Permit(Semaphore semaphore) {
            this.semaphore = semaphore;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                semaphore.release();
            }
        }
    }
}
~~~

Đây là component do ứng dụng xây. Dùng try-with-resources để release permit trên mọi đường đi:

~~~java
try (RequestAdmission.Permit permit =
         admission.acquire(50, TimeUnit.MILLISECONDS)) {
    if (permit == null) {
        throw new ServiceOverloadedException();
    }
    return applicationService.execute(command);
}
~~~

Trong production, xử lý InterruptedException, mapping overload thành SOAP Fault/HTTP response và permit scope đúng. Semaphore trong từng pod chỉ giới hạn per-instance concurrency; muốn giới hạn global theo partner cần distributed policy hoặc capacity allocation, thường ưu tiên local bulkhead cộng downstream limits.

## 13. Đặt admission control ở đâu?

Admission control nên ở boundary biết operation/partner và trước khi tiêu thụ tài nguyên đắt:

- API gateway/load balancer: global/per-client rate limit.
- Servlet filter: giới hạn tổng request/route trước SOAP parsing.
- Spring-WS interceptor/endpoint boundary: policy theo SOAP operation/partner sau khi có metadata.
- Application service: giới hạn tác vụ nặng/dependency cụ thể.
- Outbound client: giới hạn concurrent calls theo partner/route.

Không đợi DB pool cạn mới reject. Admission sớm giảm chi phí parse XML, validate signature và giữ thread cho requests biết chắc không xử lý được.

### 13.1. Authentication và fairness

Nếu quota theo partner, identity phải được xác minh trước khi dùng làm quota key. Không tin partnerId trong Body. Với WS-Security-only, có thể cần coarse limit trước WSS4J theo IP/route và quota partner sau khi xác thực.

Không để client gửi invalid XML/signature không giới hạn để chiếm CPU parser/crypto; giới hạn request size, rate, connections và quan sát security failures.

## 14. Backpressure và load shedding

**Backpressure** làm producer giảm tốc khi consumer không thể xử lý thêm. Với SOAP qua HTTP, cơ chế có thể là admission rejection, HTTP 429/503, timeout/deadline propagation, bounded queues và retry policy có giới hạn.

**Load shedding** chủ động từ chối một phần tải để giữ phần còn lại hoạt động. Khi overload, từ chối sớm request không ưu tiên thường tốt hơn làm mọi request chậm đến timeout.

### 14.1. Chọn response theo contract

SOAP service có thể trả SOAP Fault với detail SERVICE_OVERLOADED hoặc dùng HTTP 503 theo integration contract. Không tự phát minh Fault QName trái WSDL. Nếu gateway trả 429/503 trước SOAP stack, caller có thể không nhận SOAP Envelope.

### 14.2. Retry không được phá backpressure

Nếu server trả 503 và clients retry ngay, overload nặng hơn. Dùng Retry-After khi thích hợp, exponential backoff, jitter, max attempts, retry budget và idempotency cho commands.

## 15. Timeout hierarchy và deadline propagation

~~~text
Client total deadline
  └── Gateway timeout
       └── Servlet request budget
            ├── SOAP parsing / WS-Security budget
            ├── DB acquire + query/transaction budget
            └── Outbound SOAP call budget
                 ├── connection lease
                 ├── connect/TLS
                 └── response/read
~~~

Ví dụ client total deadline 5 giây không thể cùng lúc có outbound partner timeout 10 giây nếu synchronous request phải chờ kết quả. Downstream timeout nên nhỏ hơn budget còn lại và chừa thời gian serialize/trả response.

### 15.1. Timeout khác cancellation

Client hết thời gian chờ không có nghĩa server tự dừng công việc. Request có thể tiếp tục query DB/gọi partner. Cần cancellation propagation nếu API hỗ trợ, query timeout, statement cancellation, bounded workers và idempotency.

Timeout ngắn tùy tiện cũng nguy hiểm: transaction hoặc external call có thể đã commit, tạo unknown outcome.

## 16. Giới hạn queue và thời gian chờ

Nếu request chờ queue 4 giây nhưng deadline còn 3 giây, xử lý khi dequeue gần như chắc chắn gây timeout client. Admission policy có thể từ chối request quá hạn trước công việc nặng.

Một queue tốt có capacity hữu hạn, queue wait timeout, request deadline/age check, rejection policy, metrics depth/oldest age và cleanup khi client cancel nếu hỗ trợ.

Queue không sửa được service có throughput nhỏ hơn arrival rate kéo dài. Nếu λin > λout lâu dài, backlog tăng cho đến khi đầy.

## 17. Bulkhead theo partner và operation

Một partner SOAP endpoint chậm có thể làm cạn shared thread/connection pools. **Bulkhead** cô lập capacity theo dependency hoặc workload:

~~~mermaid
flowchart TD
    A[SOAP requests] --> B{Operation / partner routing}
    B --> C[Partner A bulkhead]
    B --> D[Partner B bulkhead]
    B --> E[Local read-only pool]
    C --> F[Partner A HTTP pool]
    D --> G[Partner B HTTP pool]
    E --> H[Database]
~~~

Giới hạn per-partner có thể gồm semaphore max concurrent calls, outbound connection pool, timeout, retry budget và circuit breaker. Một partner hết capacity không được block tất cả các partner khác.

Tách quá nhiều pools làm capacity phân mảnh. Chọn bulkhead theo dependency có failure/performance profile khác, đo utilization và giữ tổng resource budget.

## 18. Async servlet và async processing không tạo capacity miễn phí

Async servlet có thể giải phóng container thread khi request chuyển sang xử lý bất đồng bộ, nhưng công việc vẫn chạy ở executor khác. Nếu executor không bounded, queue vô hạn hoặc downstream pool không giới hạn, overload chỉ chuyển vị trí.

~~~text
Servlet thread:
  parse/admit -> submit task -> release servlet thread

Bounded worker:
  call service / DB / partner -> complete async response
~~~

Với Spring-WS SOAP endpoint, không giả định chỉ đổi return type thành CompletableFuture là message processing tự chuyển async. Xác minh support theo Spring-WS version, servlet async mode, message context lifecycle, response completion, Fault mapping và WSS4J context propagation.

### 18.1. Security context và transaction context

Thread khác không tự động có cùng ThreadLocal SecurityContext, transaction hoặc MDC. Nếu async:

- Propagate verified principal theo Spring Security mechanism phù hợp.
- Không giữ transaction/EntityManager trên thread khác.
- Propagate correlation/trace context theo instrumentation.
- Re-authorize trước side effects nếu policy yêu cầu.
- Clear context khi task hoàn tất.

Không truyền raw security headers sang worker rồi coi đó là Authentication đã được verify.

## 19. Attachment và XML processing có resource profile riêng

SOAP message không chỉ là payload nhỏ. MTOM attachment, XML lớn hoặc WS-Security encryption/signature làm tăng CPU, heap, disk I/O và temporary storage.

Giới hạn ở HTTP request body/content length, SOAP message size, XML depth/element count nếu parser hỗ trợ, attachment count/size và MIME parts, decompression ratio, JAXB object graph, crypto algorithms và total deadline.

Streaming có thể giảm memory so với buffering, nhưng phải kiểm implementation. Upload 100 MB không nên tiêu thụ cùng concurrency budget như GetShipmentStatus 2 KB.

### 19.1. Separate workload classes

| Workload | Resource policy |
| --- | --- |
| Small status reads | Higher concurrency, short timeout |
| Create/cancel commands | Moderate concurrency, DB capacity |
| Large MTOM uploads | Low concurrency, streaming/temp storage quota |
| XML signature-heavy operations | CPU-aware limit |
| Partner fan-out operations | Bulkhead per downstream |

Không dùng một semaphore global nếu workload demands khác nhau; đồng thời tránh tạo quá nhiều limits độc lập không quản lý.

## 20. Capacity planning nhiều replicas

Giả sử triển khai 4 replicas:

- Mỗi replica có 120 max servlet threads.
- DB pool 24 connections.
- Partner A pool 16 connections.
- Partner B pool 12 connections.

| Resource | Mỗi replica | 4 replicas |
| --- | ---: | ---: |
| Servlet max threads | 120 | 480 |
| DB max pool | 24 | 96 |
| Partner A connections | 16 | 64 |
| Partner B connections | 12 | 48 |

Đây là giới hạn cấu hình, không phải throughput. DB có thể chỉ chịu 60 app connections; Partner A chỉ hỗ trợ 30 concurrent requests. Cần phân bổ global cluster budget:

\[
perInstanceLimit \leq \frac{globalBudget - reserve}{replicaCount}
\]

Autoscaling thêm pods có thể làm tổng DB/outbound connections vượt budget dù từng pod cấu hình đúng. CPU-based HPA cũng có thể bỏ sót I/O thread starvation khi CPU thấp nhưng pending queues tăng.

## 21. Tính capacity thực nghiệm

Capacity phụ thuộc CPU time/request, p95/p99, DB query/lock time, downstream latency, payload/attachment size, workload mix, heap/GC, network, retries và replica count.

Quy trình:

1. Xác định workload mix thực.
2. Bắt đầu với concurrency thấp.
3. Tăng tải theo step và giữ đủ lâu cho steady state.
4. Đo throughput, p50/p95/p99, error và saturation.
5. Tìm điểm latency/error tăng nhanh trong khi throughput gần như không tăng.
6. Giữ headroom bên dưới knee point.
7. Lặp với downstream slowdown/failure và payload lớn.
8. Kiểm recovery sau khi tải giảm.

Không chỉ load test GetStatus nếu CreateShipment có transaction và partner call. Tạo workload mix gần production và test từng nhóm để tìm bottleneck.

## 22. Metrics cho servlet threads

Theo dõi current/active/busy worker threads, max/available threads, request throughput, request duration p50/p95/p99, queue/backlog nếu container expose, active connections và rejected requests.

Spring Boot Actuator/Micrometer có thể expose một số server/HTTP metrics tùy servlet container/version. Không hardcode tên metrics khi chưa kiểm registry thật; khám phá endpoint và dashboard đang triển khai.

### 22.1. Busy threads tiến sát max

Khi busy threads gần max liên tục, kiểm request latency, thread states WAITING/BLOCKED/RUNNABLE, downstream acquisition/response wait, synchronized bottleneck, retry storm và queue growth. Thread dump đúng lúc overload thường hữu ích hơn một utilization number đơn lẻ.

## 23. Metrics cho database và outbound pools

Database pool: active/idle/total connections, pending borrowers, acquisition wait/timeouts, query/transaction duration, DB sessions/locks/CPU/slow queries.

Outbound HTTP pool: leased/available/pending connections, lease wait, per-route utilization, connect/TLS/response latency, timeout/reset/reuse failures.

Nếu servlet busy cao đồng thời DB active=max và pending tăng, requests có thể đang chờ DB. Nếu DB nhàn nhưng outbound pending tăng, bottleneck có thể là HTTP dependency.

## 24. In-flight requests và queue age

Đếm request đang xử lý giúp phân biệt throughput và concurrency. Instrument ở servlet filter hoặc Spring-WS/application boundary:

- Increment khi request vào scope đo.
- Decrement trong finally khi scope kết thúc.
- Ghi active count/high-water mark.
- Gắn operation class sau khi xác định QName.
- Theo dõi duration và outcome.
- Với async, giữ measurement đến async completion, không decrement khi servlet thread vừa release.

Instrumentation phải cleanup cả khi exception/Fault. Queue age cũng hữu ích: queue 50 tasks có thể tốt nếu chờ 1 ms nhưng nguy hiểm nếu task đầu đã chờ 30 giây. Theo dõi oldest age và deadline remaining.

## 25. Logging và tracing khi điều tra saturation

Trace/log có thể gắn correlation/trace ID, operation/QName, partner class đã xác thực, request size class, duration theo boundary (parse, auth, service, DB, partner, marshal), timeout/reject reason, retry attempt và pool wait duration.

Không log raw SOAP Body, UsernameToken, private data hoặc attachment để chẩn đoán latency. Dùng span events/metrics và sampled traces; tránh shipment ID làm metric labels vì cardinality cao.

## 26. Load testing và overload testing

Gatling, JMeter hoặc k6 có thể tạo SOAP HTTP POST traffic. Test gửi Envelope đúng contract và đo client latency cùng server saturation.

| Kịch bản | Mục tiêu |
| --- | --- |
| Constant arrival rate | Sustained throughput |
| Ramp-up concurrency | Tìm saturation knee |
| Burst traffic | Queue/admission |
| Slow DB | DB pool waits và timeout |
| Slow partner SOAP | Outbound pool/bulkhead |
| Partner unavailable | Circuit breaker/load shedding |
| Large MTOM | Memory/attachment limits |
| WS-Security signature load | CPU/crypto capacity |
| Multi-partner mix | Fairness/isolation |
| Recovery after overload | Backlog draining/recovery |

### 26.1. Open model và closed model

Closed model có số virtual users cố định, user gửi tiếp sau response; khi server chậm arrival rate tự giảm. Open model điều khiển arrival rate độc lập; khi server chậm in-flight/queue tăng nếu không admission control. Closed model có thể che overload vì tải gửi tự giảm. Chọn model theo workload production.

## 27. SLO và headroom

SLO minh họa: 99% status requests dưới 300 ms; 99% create dưới 1,5 giây; overload rejection trong ngưỡng đã thỏa thuận khi traffic bình thường; không vượt DB/global partner budgets; partner chậm không làm status reads ngừng phục vụ.

Đây không phải chuẩn mặc định. SLO theo business contract, client timeout, partner SLA và dữ liệu thực. Headroom phải đủ cho burst, rolling deployment và một replica lỗi. Test nominal, peak forecast và N-1/partner degradation.

## 28. Graceful shutdown và rolling deployment

Khi instance dừng:

1. Đánh dấu readiness fail để ngừng nhận traffic mới.
2. Load balancer ngừng route request theo propagation behavior.
3. Cho in-flight requests hoàn tất trong graceful shutdown window.
4. Cancel/terminate công việc quá deadline theo policy.
5. Đóng outbound HTTP và DB pools.
6. Flush telemetry cần thiết.
7. Không giữ shutdown vô hạn vì downstream hung call.

Grace period phù hợp request deadline và orchestrator termination grace period. Nếu pod bị kill trước khi response về, client có thể unknown outcome; idempotency vẫn cần cho commands.

## 29. Overload response và SOAP Fault policy

Từ chối ở gateway/connector có thể trả HTTP 429/503. Nếu request vào Spring-WS và policy tạo Fault, dùng contract rõ:

- SOAP Sender/Client cho request caller phải sửa.
- SOAP Receiver/Server hoặc application-defined detail cho temporary overload tùy policy.
- Fault detail có code SERVICE_OVERLOADED, DEPENDENCY_BUSY hoặc RETRY_LATER nếu contract công bố.
- Correlation ID và hướng dẫn retry/backoff phù hợp.
- Không trả stack trace, thread names, pool size hoặc topology.

Test cả HTTP-level rejection và SOAP-level overload response. Tránh retry vô hạn hoặc biến overload thành business success.

## 30. Quy trình chọn giới hạn ban đầu

1. Xác định global database connection budget và chia cho số replicas tối đa, có reserve.
2. Xác định per-partner concurrency quota và tổng outbound connection budget.
3. Đo active service time và latency distribution theo operation.
4. Ước lượng concurrency bằng Little’s Law cho target throughput.
5. So với CPU/DB/partner limits để chọn giới hạn từng boundary.
6. Chọn servlet threads đủ workload mix nhưng không cho downstream overload.
7. Đặt bounded queue ngắn, queue wait timeout và reject policy.
8. Đặt connect/lease/read/total deadlines nhất quán.
9. Load test và tăng capacity từng bước, giữ headroom.
10. Kiểm autoscaling không vượt global DB/partner budgets.

Không có công thức maxThreads = DB pool × N dùng cho mọi SOAP service. Sizing cần workload, blocking time và dependency graph đo được.

## 31. Anti-pattern thường gặp

- **Tăng maxThreads để sửa mọi latency:** đẩy overload sang DB/partner. Tìm bottleneck trước.
- **Queue vô hạn:** backlog và heap tăng không kiểm soát. Dùng bounded queue/deadline.
- **Pool mỗi nơi một con số tùy ý:** vượt global resource budget. Tổng hợp limits mọi replicas.
- **Một HTTP pool cho mọi partner:** dependency chậm làm nghẽn phần còn lại. Dùng per-route/bulkhead.
- **Giữ transaction khi gọi partner:** giữ DB connection/lock lúc chờ network. Rút ngắn transaction.
- **Timeout lớn hơn client deadline:** server làm việc sau khi client bỏ. Propagate deadline/cancel.
- **Async với executor vô hạn:** chuyển exhaustion sang tầng khác. Bounded workers.
- **Chỉ theo dõi CPU:** bỏ sót I/O thread starvation. Theo dõi pools/thread dumps.
- **Dùng maxConnections như max requests:** sai vì keep-alive/HTTP2 multiplexing. Đo request concurrency riêng.
- **Retry storm khi overload:** làm queue dài thêm. Backoff/jitter/budget/idempotency.
- **Quota theo dữ liệu caller:** giả tenant để chiếm quota. Dùng verified identity.
- **Decrement in-flight trước async completion:** metrics thấp giả. Theo dõi đúng lifecycle.

## 32. Quy trình triển khai và vận hành

1. Vẽ request path từ connector đến MessageDispatcherServlet, endpoint, service và dependencies.
2. Phân loại workload theo operation, payload size và dependency demand.
3. Đo throughput, latency, active threads, in-flight, DB/outbound pool utilization.
4. Ước lượng average concurrency bằng Little’s Law; kiểm p95/p99 và peak.
5. Xác định global DB/partner budgets qua mọi replicas.
6. Cấu hình connector threads, connections và accept/backlog theo container thật.
7. Cấu hình bounded DB pool và connection/query timeouts.
8. Cấu hình outbound HTTP pool total/per-route limits.
9. Thêm admission control/bulkheads đúng boundary.
10. Đặt queue size/age, deadline, load shedding và retry contract.
11. Giới hạn XML, MTOM và crypto workload.
12. Load test sustained, burst, slow dependency và recovery.
13. Thiết lập dashboards/alerts saturation, pending borrowers, p95/p99, rejects.
14. Kiểm autoscaling, graceful shutdown và rolling deployment.
15. Review limits khi traffic mix hoặc partner SLA thay đổi.

## 33. Bài tập thực hành

### Bài tập 1 — Tính concurrency
Service nhận 80 requests/second với average latency 400 ms. Dùng Little’s Law tính average in-flight requests. Giả định partner latency tăng lên 2 giây và phần lớn requests phải chờ partner, tính lại.

### Bài tập 2 — Đọc Tomcat metrics
Cấu hình max threads 100, max connections 400, accept count 50. Tạo tải tăng dần và quan sát busy threads, active connections, duration và rejects. Giải thích vì sao connections có thể cao hơn busy threads.

### Bài tập 3 — DB pool exhaustion
Đặt Hikari pool 10 connections và chạy 50 concurrent create requests. Đo acquisition wait/timeout. Làm query chậm và xác định servlet threads nào đang bị giữ.

### Bài tập 4 — Partner bulkhead
Tạo hai SOAP partner mock; Partner A delay 5 giây, Partner B trả 50 ms. So shared pool với per-partner limits. Chứng minh Partner A không làm Partner B hết connections.

### Bài tập 5 — Admission control
Thêm semaphore giới hạn 20 in-flight document uploads. Tạo burst 100 requests, kiểm số chạy/reject, queue wait, memory và permit release khi exception.

### Bài tập 6 — Timeout hierarchy
Đặt client deadline 4 giây, outbound connect 1 giây, response 2 giây và DB acquire 500 ms. Mô phỏng partner chậm và kiểm response trong budget.

### Bài tập 7 — Load shedding và retry
Cho service trả overload 503 khi capacity đầy. Dùng clients với jitter/bounded retry. So với immediate retry và đo recovery.

### Bài tập 8 — Large MTOM
Gửi attachment nhiều kích thước và concurrency. Đo heap, temp storage, CPU, in-flight và reject policy. Xác định limit riêng cho upload.

### Bài tập 9 — Graceful shutdown
Trong lúc có request chờ partner, đánh dấu instance not-ready rồi shutdown. Kiểm request hoàn tất/cancel, client behavior và idempotency command.

### Bài tập 10 — Capacity report
Tạo report cho mỗi operation: target RPS, p95/p99, servlet threads, DB pool demand, outbound per-partner limits, peak in-flight, headroom và failure-mode results.

## 34. Checklist trước production

- [ ] Phân biệt TCP connections, HTTP requests, servlet threads, async workers và in-flight requests.
- [ ] Có sơ đồ request path và resource demands theo operation.
- [ ] Có throughput/latency measurements và Little’s Law estimates với boundary rõ.
- [ ] Servlet connector max threads/connections/accept queue đúng container/version.
- [ ] Không xem maxConnections là giới hạn request concurrency.
- [ ] Application executor queues bounded, có rejection policy.
- [ ] DB pool tổng mọi replicas nằm trong database budget có reserve.
- [ ] Transaction không giữ DB connection trong outbound call không cần thiết.
- [ ] Outbound HTTP pools có total/per-route limits và lease timeout.
- [ ] Partner failure được cô lập bằng bulkhead/circuit breaker khi cần.
- [ ] Admission control dùng verified identity nếu quota theo partner.
- [ ] In-flight requests và queue age đo đúng lifecycle.
- [ ] Read/connect/lease/DB/total deadlines nhất quán.
- [ ] Overload response/Fault và Retry-After có contract.
- [ ] Client retry có backoff/jitter/budget; commands có idempotency.
- [ ] Async workers bounded, context propagation và cleanup đã test.
- [ ] XML/MTOM/crypto có size/concurrency limits.
- [ ] Metrics theo dõi busy threads, pool active/idle/pending, latency và rejects.
- [ ] Logs/traces không tiết lộ SOAP credentials/PII.
- [ ] Load tests có sustained, burst, slow dependency, recovery và N-1 cases.
- [ ] Open/closed workload model phù hợp traffic.
- [ ] Autoscaling không vượt global DB/partner budgets.
- [ ] Graceful shutdown phù hợp request deadlines.
- [ ] Có dashboards/alerts và runbook cho thread starvation/pool exhaustion/overload.

## 35. Tài liệu tham khảo

- [Spring Boot — Web Server Configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html): embedded servlet web server và container integration.
- [Apache Tomcat — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): maxThreads, maxConnections, acceptCount và connector behavior.
- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/reference/): MessageDispatcherServlet, endpoints, transports và message processing.
- [Spring Web Services — WebServiceTemplate Javadoc](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): SOAP client invocation lifecycle.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): pool sizing, connection timeout và lifecycle.
- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html): JVM, thread và memory instrumentation.
- [Micrometer — Metrics](https://docs.micrometer.io/micrometer/reference/reference/metrics.html): instrumentation patterns; xác minh meter theo app/container.
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/): traces và metrics cho JVM applications.
- [Google SRE Book — Handling Overload](https://sre.google/sre-book/handling-overload/): load shedding, queueing và graceful degradation.
- [Google SRE Book — Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): overload amplification, retries và dependency failure.
- [Little — A Proof for the Queuing Formula L = λW](https://doi.org/10.1287/opre.9.3.383): nền tảng Little’s Law.
- [Resilience4j — Bulkhead](https://resilience4j.readme.io/docs/bulkhead): giới hạn concurrent calls và isolation.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): circuit breaker states và behavior.

Tên properties/metrics thay đổi theo Spring Boot, servlet container, Micrometer và datasource version. Đối chiếu đúng version đang triển khai; các cấu hình số trong bài là ví dụ, không phải khuyến nghị capacity cố định.

## 36. Tổng kết

**Giới hạn luồng servlet, kết nối và in-flight requests là bài toán capacity end-to-end.** maxThreads chỉ cho biết số worker request có thể chạy theo container; maxConnections không đồng nghĩa số SOAP requests; DB pool và outbound HTTP pool giới hạn các dependency khác. Một request synchronous có thể giữ servlet thread trong lúc chờ DB hoặc partner, nên CPU thấp vẫn có thể đi kèm thread starvation.

Dùng **Little’s Law** để ước lượng average concurrency từ throughput và latency, nhưng sizing cuối cùng phải dựa workload mix, p95/p99, CPU, DB/partner quotas, queue age, burst và failure modes. Bounded pools, short queues, admission control, bulkhead, timeout hierarchy và load shedding giúp hệ thống từ chối có kiểm soát trước khi cạn tài nguyên. Async không tạo capacity miễn phí; nó chuyển công việc sang executor khác và vẫn cần giới hạn.

Với **SPRING_WEB_SERVICES**, hãy load test từ MessageDispatcherServlet qua endpoint/service đến database và outbound SOAP partners. Theo dõi busy threads, in-flight requests, pool acquisition waits, queue age và latency; kiểm autoscaling, retries và graceful shutdown trên tổng cluster budget. Khi capacity được đo, giới hạn có lý do và overload được xử lý rõ theo contract, SOAP service mới duy trì hiệu năng và khả năng phục hồi dưới tải thực tế.
