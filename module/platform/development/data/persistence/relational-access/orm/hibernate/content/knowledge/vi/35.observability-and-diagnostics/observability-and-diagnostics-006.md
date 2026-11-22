# Dấu vết qua ranh giới dịch vụ, giao dịch và JDBC

Một request API có thể mất 800 ms dù câu SQL chậm nhất chỉ 12 ms. Một phương thức service có thể return thành công nhưng transaction vẫn thất bại ở lúc commit. Một thông điệp đã được consumer nhận có thể tạo một trace mới, dù bắt nguồn từ cùng nghiệp vụ. Khi điều tra Hibernate, **chỉ nhìn log SQL hoặc thời gian chạy của một method sẽ không cho biết toàn bộ câu chuyện**.

Bài này trình bày cách nối dấu vết từ **API/service → Spring transaction interceptor → Hibernate Session/persistence context → connection pool → JDBC driver → database**, đồng thời mở rộng qua HTTP, message broker và các công việc bất đồng bộ.

**Nguyên tắc cốt lõi:** Trace cho biết *một yêu cầu đi qua đâu và mất thời gian ở đâu*; log cho biết *sự kiện chi tiết nào xảy ra*; metrics cho biết *tần suất và xu hướng*; database diagnostics giúp xác nhận *SQL, lock và execution plan thực tế*. Bốn nguồn dữ liệu bổ sung cho nhau, không nên thay thế lẫn nhau.

~~~text
HTTP request / traceId
    |
    +-- Controller span
          |
          +-- Service use-case span
                |
                +-- Spring transaction scope
                |     |
                |     +-- Hibernate Session / first-level cache
                |     +-- Flush / dirty checking
                |     +-- Connection pool acquire / JDBC
                |     |      |
                |     |      +-- SQL SELECT/INSERT/UPDATE
                |     |      +-- Database lock / wait / execution
                |     |
                |     +-- COMMIT / ROLLBACK
                |
                +-- Response or event publication
~~~

> **Phạm vi:** Java 17+, Spring Boot/Spring Framework, Spring Data JPA, Hibernate ORM 6.x, JDBC, Micrometer Observation/Tracing và OpenTelemetry là bối cảnh minh họa. Tên các spans, metrics, semantic-convention attributes và auto-instrumentation có thể đổi giữa phiên bản. **Không phải mọi tầng đều tự tạo span.** Những ví dụ được đánh dấu minh họa cần cấu hình/kiểm chứng trên stack thực tế.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **trace, span, log, metric, transaction và JDBC connection**.
2. Theo dấu một business request xuyên qua các service và các transaction boundaries.
3. Hiểu tại sao **method return**, **Hibernate flush** và **database commit** là ba mốc khác nhau.
4. Biết cách liên kết trace IDs với application logs, repository calls, SQL statements và database waits.
5. Sử dụng Micrometer/OpenTelemetry ở mức service, không giả định auto-instrumentation bao phủ mọi nghiệp vụ.
6. Chẩn đoán N+1, connection-pool starvation, lock contention, transaction quá dài, rollback và JDBC batching.
7. Propagate trace context qua HTTP, async executor và message broker theo hợp đồng rõ ràng.
8. Bảo vệ dữ liệu nhạy cảm khi bật tracing/SQL logging.
9. Thiết kế benchmark/integration tests chứng minh trace thể hiện đúng những ranh giới quan trọng.
10. Có runbook xử lý một request chậm hoặc thất bại trong hệ thống Hibernate.

## 2. Một tình huống xuyên suốt

Giả sử hệ thống bán hàng có API:

~~~http
POST /api/orders/42/confirm
~~~

Controller gọi `OrderApplicationService.confirm(42)`. Service tải đơn hàng qua repository, kiểm tra tồn kho, chuyển trạng thái rồi ghi lịch sử. Hibernate sử dụng một Session và transaction do Spring quản lý.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderApplicationService orders;

    public OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping("/{id}/confirm")
    public ResponseEntity<Void> confirm(@PathVariable Long id) {
        orders.confirm(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OrderHistoryRepository histories;

    public OrderApplicationService(
            OrderRepository orders,
            OrderHistoryRepository histories) {
        this.orders = orders;
        this.histories = histories;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        order.confirm();

        histories.save(
            OrderHistory.confirmed(order.getId())
        );
    }
}
~~~

Nếu `order` là managed entity, Hibernate có thể phát `UPDATE orders` lúc flush/commit, không nhất thiết ngay tại `order.confirm()`. Một `INSERT order_history` có thể được sắp xếp cùng các pending actions theo mapping.

**Dấu vết mong muốn phải đủ sức giải thích cả thời gian trước flush, khi phát SQL và khi commit.**

## 3. Trace là gì?

Một **distributed trace** biểu diễn đường đi của một operation qua các thành phần. Mỗi trace có một **trace ID**; nó gồm nhiều spans biểu diễn những công việc có thời gian bắt đầu/kết thúc.

Ví dụ giả định:

~~~text
traceId: 4bf92f3577b34da6a3ce929d0e0e4736

POST /api/orders/{id}/confirm       240 ms
└── order.confirm use-case          221 ms
    ├── inventory.reserve HTTP      70 ms
    ├── SQL SELECT orders            8 ms
    ├── SQL INSERT order_history     7 ms
    ├── SQL UPDATE orders           11 ms
    └── transaction commit          65 ms
~~~

Đây là **minh họa về điều muốn quan sát**, không phải cấu trúc tự động chắc chắn xuất hiện trong một sản phẩm tracing nào đó.

Một trace ID liên kết các spans; nhưng bản thân trace ID không phải:

- Database transaction ID.
- JPA entity ID.
- Hibernate Session ID.
- JDBC connection ID.
- Business order ID.

Có thể lưu quan hệ giữa những loại ID này bằng **attributes an toàn** hoặc log correlation, nhưng không đồng nhất chúng.

## 4. Span là gì?

Span thường có:

- `traceId` chung của toàn trace.
- `spanId` riêng của span.
- Parent span hoặc liên kết span links.
- Tên operation.
- Start/end timestamps và duration.
- Status/error information.
- Attributes/annotations/events có chọn lọc.
- Resource metadata như service name/version/environment.

Một span service:

~~~text
name: order.confirm
kind: INTERNAL
status: ERROR hoặc OK/UNSET tùy instrumentation
attributes:
  operation: confirm
  aggregate.type: order
  outcome: committed
~~~

Các attributes trên là **minh họa đặt tên**, không nhất thiết là OpenTelemetry semantic conventions chính thức.

Không đưa `order.id=42` vào **low-cardinality metric labels** cho mọi order: sẽ tạo cardinality rất lớn. Với spans/logs, business ID có thể hữu ích để tìm lỗi nhưng phải tuân thủ bảo mật, sampling và retention; ưu tiên ID giả danh/hạn chế dữ liệu nhạy cảm.

## 5. Trace, log và metrics giải quyết câu hỏi khác nhau

| Công cụ | Trả lời tốt | Không tự chứng minh |
|---|---|---|
| Distributed trace | Request qua những spans nào, duration/parent-child | Transaction DB đã commit hay chưa nếu không có instrumentation |
| Structured logs | Sự kiện và context chi tiết, exception, SQL parameters đã redact | Phân bố latency toàn hệ nếu chỉ đọc một request |
| Metrics | Throughput, lỗi, p95/p99, pool saturation, trend | Một request cụ thể mắc ở đâu |
| Hibernate Statistics | Entity loads, flushes, prepared statements, cache metrics | Timeline phân tán của riêng request |
| JDBC/SQL proxy logs | SQL statement và thời gian ở JDBC boundary | Thời gian CPU DB so với network/lock nếu thiếu DB diagnostics |
| DB monitoring | Wait events, locks, execution plans, connection state | Toàn bộ application/service call path |

Một hệ quan sát trưởng thành kết hợp nhiều lớp. Nếu chỉ có SQL log, bạn có thể biết câu SQL chạy nhưng không biết nó thuộc request nào hoặc nằm trong transaction nào.

## 6. Ranh giới service khác ranh giới transaction

Một request HTTP có thể gọi nhiều service methods. Một service method có thể:

- Không có transaction.
- Tạo một transaction mới.
- Tham gia transaction đã có.
- Tạm suspend transaction để gọi `REQUIRES_NEW`.
- Chạy một phần logic sau commit.
- Gọi remote service ở một process khác.

~~~mermaid
flowchart TD
    A["HTTP Controller"] --> B["OrderService.confirm()"]
    B --> C["InventoryService.check()"]
    B --> D["OrderRepository.findById()"]
    B --> E["HistoryRepository.save()"]
    B --> F["Spring Transaction Interceptor"]
    F --> G["Hibernate Session"]
    G --> H["JDBC + DB"]
~~~

**Đồ thị call methods không tự nói được transaction boundary.** Ví dụ nếu `confirm()` có `@Transactional`, transaction interceptor thường bắt đầu transaction *trước khi gọi body method*, và commit *sau khi method body return*.

Cần phân biệt thời gian method body với thời gian toàn transaction interceptor.

## 7. Ranh giới transaction xảy ra quanh phương thức

Với Spring AOP proxy:

~~~text
Caller
  |
  | gọi service qua proxy
  v
TransactionInterceptor
  |
  +-- get/create transaction
  |
  +-- gọi @Transactional method body
  |      |
  |      +-- repository calls
  |      +-- thay đổi managed entities
  |
  +-- flush (khi cần)
  +-- commit / rollback
  |
  v
return/exception tới Caller
~~~

Nếu bạn đặt stopwatch **bên trong** body method:

~~~java
@Transactional
public void confirm(Long orderId) {
    long started = System.nanoTime();
    try {
        // Business logic...
    } finally {
        log.info("business body elapsed={} ns",
            System.nanoTime() - started);
    }
}
~~~

thời gian log ở `finally` có thể **không bao gồm** giai đoạn commit sau khi body trả về. Không dùng số này thay cho latency end-to-end của command.

## 8. Flush không phải commit

Hibernate stateful Session có persistence context và dirty checking.

~~~java
@Transactional
public void confirm(Long id) {
    Order order = orders.findById(id).orElseThrow();
    order.confirm();

    entityManager.flush();

    // SQL UPDATE có thể đã gửi.
    // Transaction vẫn chưa commit.
}
~~~

`flush()` đồng bộ pending changes sang database trong transaction. Nhưng transaction vẫn có thể rollback sau đó. JDBC `executeUpdate()` thành công không phải bằng chứng dữ liệu durable bên ngoài transaction.

Một trace có thể chứa SQL UPDATE span **thành công** rồi transaction commit **thất bại**. Khi ghi nhật ký nghiệp vụ, không gọi request là `COMMITTED` chỉ vì thấy SQL update.

## 9. Khi nào SQL được phát?

Hibernate có thể phát SQL tại:

- `find()`/HQL SELECT.
- `persist()` trong vài ID generation strategies, nhất là khi cần DB-generated key.
- `flush()` tường minh.
- Auto-flush trước một query liên quan.
- Commit transaction.
- Collection initialization hoặc LAZY association loads.
- Bulk HQL/native mutation.
- JDBC code ngoài Hibernate.

Ví dụ:

~~~java
Order order = repo.findById(id).orElseThrow();
order.confirm();
// Chưa chắc có UPDATE ngay.

long count = entityManager.createQuery(
    "select count(o) from Order o",
    Long.class
).getSingleResult();
// Có thể auto-flush tùy flush mode/query overlap.
~~~

Vì vậy **thứ tự SQL spans không nhất thiết trùng thứ tự các setter calls**. Đó không phải bug của trace; nó phản ánh ORM write-behind.

## 10. Cùng request không có nghĩa cùng một database transaction

Giả sử:

~~~java
@Transactional
public void placeOrder() {
    createOrder();
    auditService.recordInNewTransaction();
}
~~~

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordInNewTransaction() {
    // Ghi audit trong transaction độc lập.
}
~~~

Một HTTP trace có thể chứa cả hai methods, nhưng `REQUIRES_NEW` thường:

- Suspend outer transaction.
- Mượn thêm connection/resource tùy manager.
- Begin/commit transaction riêng.
- Resume outer transaction.

Audit commit có thể thành công trong khi outer order transaction rollback. **Một trace có nhiều transaction outcomes**; không đặt một `tx.committed=true` global cho cả trace nếu thực tế không đúng.

## 11. REQUIRED không tạo một commit mới

Với `@Transactional(propagation = REQUIRED)` (mặc định), method con tham gia transaction đã có nếu tồn tại.

~~~java
@Transactional
public void confirm(Long id) {
    ledgerService.writeEntry(id);
    // Cùng transaction nếu ledgerService dùng REQUIRED
    // và được gọi qua Spring transaction proxy thích hợp.
}
~~~

Thời điểm `ledgerService.writeEntry()` trả về **không phải** lúc transaction commit. Một nested service span có thể thành công, sau đó outer transaction lỗi.

Để trace chính xác:

- Đánh dấu method outcome riêng.
- Đánh dấu transaction outcome ở boundary thật.
- Không tự tạo “transaction commit” event khi method con kết thúc.
- Kiểm tra call path/proxy để biết method có tham gia Spring transaction không.

## 12. NESTED, savepoint và rollback cục bộ

`Propagation.NESTED` có thể sử dụng database savepoints nếu transaction manager/resource hỗ trợ. Hibernate/JPA integration không nhất thiết hỗ trợ nested semantics ở mọi cấu hình.

Một span con có thể kết thúc với rollback tới savepoint nhưng outer transaction tiếp tục commit.

Nếu tracing chỉ có một span `order.confirm` với status OK, bạn có thể bỏ sót một nhánh rollback cục bộ đã được phục hồi. Hãy ghi log/metric cho savepoint rollback khi workflow dùng NESTED.

**Đừng tự suy luận từ chữ “nested span” rằng nó là “nested transaction”.** Span parent-child là quan hệ quan sát; transaction nesting là semantics của transaction manager/database.

## 13. Self-invocation làm sai giả định về transaction

Spring proxy-based `@Transactional` thường không intercept lời gọi nội bộ:

~~~java
@Service
public class OrderService {

    public void start(Long id) {
        this.confirm(id); // Không đi qua AOP proxy.
    }

    @Transactional
    public void confirm(Long id) {
        // ...
    }
}
~~~

Có thể xuất hiện service span hoặc log `confirm()`, nhưng transaction dự kiến không được mở bởi annotation của phương thức đó.

Khi trace cho thấy SQL auto-commit lẻ tẻ hoặc no active transaction:

- Kiểm tra bean có do Spring quản lý?
- Lời gọi có đi qua proxy?
- `@Transactional` import đúng package?
- Transaction manager được chọn đúng?
- Async/thread boundary có làm mất context?

**Trace thấy method chạy không chứng minh transaction advice đã chạy.**

## 14. Tách connection acquisition khỏi SQL execution

Một request chậm có thể do phải **chờ JDBC connection** từ pool, trong khi bản thân SQL nhanh.

~~~text
Service          850 ms
  |
  +-- Pool acquire wait: 700 ms
  |
  +-- JDBC execute:      15 ms
  |
  +-- Application:      135 ms
~~~

Nếu instrumentation chỉ tạo JDBC span quanh `executeQuery()`, bạn thấy “SQL 15 ms” và không có nguyên nhân của 700 ms còn lại.

Các khả năng:

- HikariCP pool quá nhỏ so với concurrency.
- Một transaction giữ connection lâu do remote HTTP call.
- N+1 queries làm connection utilization tăng.
- Slow queries khác giữ pool.
- Connection leak hoặc stream/resultset chưa đóng.
- Database không tiếp nhận đủ connections.

Cần metrics riêng cho **pool acquisition time**, active/idle/pending connections, timeouts và usage duration.

## 15. JDBC execute duration không đồng nghĩa DB CPU duration

Một JDBC `PreparedStatement.executeQuery()` span có thể gồm:

- Thời gian client/driver chuẩn bị và gửi request.
- Network round-trip.
- Database lock waiting.
- SQL parsing/planning/execution ở DB.
- Driver receive/initial result handling.

Nó **không tự tách** DB CPU khỏi network, lock wait hoặc query plan. Nhiều driver còn truyền dữ liệu theo batch/cursor, nên thời gian duyệt `ResultSet.next()` có thể lớn hơn execute span.

Do đó, với SQL “chậm”, hãy kiểm tra:

- DB slow query logs.
- Execution plan và index.
- Lock/wait events.
- Network latency.
- Row count/fetch size.
- ResultSet iteration/hydration time.
- Connection pool pressure.

## 16. Hibernate hydration có thể là phần latency đáng kể

Hibernate không chỉ gửi SQL; nó còn:

1. Nhận rows từ JDBC.
2. Hydrate entity attributes.
3. Dùng persistence context identity map.
4. Tạo hoặc resolve association references.
5. Quản lý entity state/snapshots.
6. Khởi tạo collections theo fetch plan.
7. Chạy phần logic liên quan lifecycle khi cần.

Một SQL trả 100.000 rows có thể thực thi nhanh trong DB nhưng ứng dụng vẫn mất nhiều thời gian phân bổ objects và GC.

Tracing cần quan sát cả **query operation duration** và **application heap/CPU metrics**. Một span `db.query` không nhất thiết bao phủ toàn bộ hydration trong Hibernate.

## 17. Một trace waterfall giả định

~~~text
POST /orders/{id}/confirm                   620 ms
├─ HTTP authentication                       12 ms
└─ usecase.order.confirm                    588 ms
   ├─ inventory.check HTTP                   70 ms
   ├─ repository.findById                    90 ms
   │  ├─ Hikari acquire                      65 ms
   │  └─ JDBC SELECT                         10 ms
   ├─ business validate                      30 ms
   ├─ Hibernate flush                       120 ms
   │  ├─ JDBC INSERT order_history           35 ms
   │  └─ JDBC UPDATE orders                  75 ms
   └─ database COMMIT                        65 ms
~~~

Các số này chỉ minh họa và không bắt buộc cộng chính xác do spans có thể chồng lấp hoặc có overhead/idle gaps. Khi đọc waterfall:

- Service duration bao gồm nhiều khoảng không có child span.
- Child spans có thể chạy song song.
- Tổng durations của children không nhất thiết bằng parent duration.
- Span không được instrument không đồng nghĩa thời gian đó bằng 0.
- Commit có thể hiện hoặc không hiện dưới dạng span tùy tracing setup.

**Đừng cộng duration của mọi child để tính thời gian request nếu chúng overlap.**

## 18. Distributed trace qua HTTP: trace context

W3C Trace Context chuẩn hóa các HTTP headers như:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

`traceparent` chứa version, trace ID, parent span ID và trace flags. Tracing instrumentation ở client/service có thể tự inject/extract headers để nối các spans giữa processes.

Không tự viết parser bằng tách chuỗi nếu framework đã hỗ trợ chuẩn. Dùng OpenTelemetry/Micrometer instrumentation tương thích các HTTP clients thực tế.

Không đặt order ID, email hoặc JWT trong `tracestate`/baggage tùy tiện; context có thể đi qua nhiều hệ thống và bị ghi log.

## 19. Dấu vết service A → service B không có transaction dùng chung

~~~mermaid
sequenceDiagram
    participant API as API Gateway
    participant S1 as Order Service
    participant S2 as Inventory Service
    participant D1 as Order DB
    participant D2 as Inventory DB
    API->>S1: HTTP (traceparent)
    S1->>S2: HTTP (traceparent)
    S2->>D2: JDBC transaction T2
    D2-->>S2: commit T2
    S2-->>S1: reservation result
    S1->>D1: JDBC transaction T1
    D1-->>S1: commit T1
    S1-->>API: HTTP result
~~~

Cùng một trace ID **không tạo distributed database transaction**. Order DB transaction T1 và Inventory DB transaction T2 vẫn độc lập trừ khi có một giao thức distributed transaction thật sự.

Nếu T2 commit rồi T1 rollback, trace có thể bao gồm cả hai outcomes. Khi nghiệp vụ cần consistency xuyên services, phải thiết kế saga, compensations, outbox hoặc cơ chế khác — không trông chờ tracing giải quyết atomicity.

## 20. Correlation ID khác trace ID

Một hệ thống có thể có:

- `traceId`: kỹ thuật tracing theo request/operation.
- `requestId`: ID do gateway tạo, có thể hữu ích cả khi trace không được sample.
- `orderId`: business aggregate ID.
- `transactionId`: DB transaction ID hoặc application-generated unit-of-work ID.
- `eventId`: message/outbox event ID.
- `sessionId`: Hibernate Session identity (thường không cần expose).

Không dùng một ID thay mọi ID. Ví dụ một order trải qua hàng trăm requests, nên có nhiều trace IDs. Một request lại có thể tác động nhiều orders.

Nếu cần nhóm logs theo business ID, dùng field riêng nhưng kiểm soát retention, access và privacy.

## 21. Structured logging liên kết với trace

Một log record hữu ích:

~~~json
{
  "timestamp": "2026-11-15T08:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "operation": "order.confirm",
  "outcome": "completed"
}
~~~

Trong Spring/Micrometer Tracing, trace/span IDs có thể được đưa vào MDC/logging context khi tích hợp được bật đúng cách.

Ví dụ Logback pattern (minh họa):

~~~properties
logging.pattern.level=%5p [traceId=%X{traceId},spanId=%X{spanId}]
~~~

Không nên tự gắn trace ID bằng `ThreadLocal` tùy ý khi hệ thống đã có instrumentation. Tracing context phải được quản lý đúng scope; với async executor, propagation có thể khác.

## 22. Đặt service span bao quanh cả transaction commit

Một sai sót dễ gặp là đặt timing **bên trong** method `@Transactional` rồi gọi đó là “toàn transaction”.

Nếu một controller hoặc outer caller instrument scope quanh lời gọi qua Spring transaction proxy:

~~~java
@PostMapping("/{id}/confirm")
public ResponseEntity<Void> confirm(@PathVariable Long id) {
    Observation.createNotStarted(
        "usecase.order.confirm",
        observationRegistry
    )
    .lowCardinalityKeyValue("operation", "confirm")
    .observe(() -> orderService.confirm(id));

    return ResponseEntity.noContent().build();
}
~~~

`Observation` là Micrometer Observation API, ví dụ khái niệm. Scope quanh lời gọi **qua proxy** có thể bao gồm transaction begin/body/commit/rollback phát sinh trong chính lời gọi.

Nếu `orderService.confirm()` lại chỉ tham gia outer transaction đã được mở ở nơi khác, span này không nhất thiết bao toàn bộ commit. **Đặt observation ở đúng boundary thực tế**, không chỉ gắn tên method.

Không đưa `id` của mỗi order vào `lowCardinalityKeyValue`. Nếu cần correlation business ID, dùng high-cardinality context có chính sách privacy/cardinality phù hợp.

## 23. Spring AOP và @Observed

Micrometer có annotation `@Observed` cho một số method-level observations khi aspect/instrumentation phù hợp được cấu hình.

~~~java
@Observed(
    name = "order.confirm",
    contextualName = "order confirmation"
)
public void confirm(Long id) {
    // ...
}
~~~

**Chỉ viết `@Observed` không bảo đảm span xuất hiện**. Phải xác nhận ObservedAspect/AOP hoặc auto-instrumentation của stack thật sự intercept method. Self-invocation và proxy ordering cũng có thể khiến boundaries khác dự kiến.

Nếu mục tiêu là đo **commit sau method body**, cần xem thứ tự observation aspect và transaction advice. Instrument ở outer boundary hoặc viết chuyên biệt interceptor quanh transaction manager khi yêu cầu thực sự quan trọng.

## 24. Micrometer Observation và Tracing khác nhau

**Micrometer Observation** cung cấp abstraction ghi observation và liên kết handlers, có thể sinh metrics/tracing tùy registry và dependencies.

**Micrometer Tracing** là bridge tới tracer như OpenTelemetry/Brave, giúp quản lý trace/span context.

**OpenTelemetry** định nghĩa API/SDK/semantic conventions và exporter/collector ecosystem. Có thể dùng OTel Java agent để auto-instrument HTTP/JDBC mà không phải sửa nhiều business code.

Các tầng liên quan:

~~~text
Spring application
   |
Micrometer Observation / custom business observations
   |
Micrometer Tracing bridge hoặc OpenTelemetry instrumentation
   |
OTLP exporter / Collector
   |
Jaeger / Tempo / Zipkin / tracing backend
~~~

Không bật đồng thời nhiều instrumentation agents/bridges thiếu kiểm soát: có thể tạo **duplicate HTTP/JDBC spans**, nesting sai hoặc tăng overhead.

## 25. Spring Boot tracing setup là version-sensitive

Với một Spring Boot 3.x stack dùng Micrometer/OTel, ví dụ dependencies có thể gồm:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-actuator")
implementation("io.micrometer:micrometer-tracing-bridge-otel")
runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
~~~

Configuration minh họa:

~~~properties
management.tracing.sampling.probability=0.1
management.otlp.tracing.endpoint=http://otel-collector:4318/v1/traces
~~~

Đường properties/exporter dependency **có thể khác giữa các Spring Boot minor/major versions**. Hãy dùng hướng dẫn Actuator/Observability đúng version và xác nhận exporter thực sự tạo spans ở backend.

Production sampling phải xét volume/cost; `1.0` chỉ nên dùng trong môi trường test hoặc khi lưu lượng phù hợp.

## 26. Lựa chọn Java agent cho instrumentation

Một hướng khác là OpenTelemetry Java agent:

~~~text
java
  -javaagent:/opt/otel/opentelemetry-javaagent.jar
  -jar order-service.jar
~~~

Các environment variables minh họa:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
~~~

Exact exporter protocol/endpoint phụ thuộc configuration của agent và collector. Java agent có thể tự instrument HTTP, JDBC và nhiều libraries theo version.

**Không mặc định Java agent tự tạo một database transaction span chính xác cho mỗi Spring `@Transactional`.** Các auto-generated client spans cần được bổ sung business/transaction observations có chủ đích.

Nếu đã dùng Micrometer Tracing với exporter, kiểm tra double instrumentation trước khi bật thêm agent.

## 27. JDBC instrumentation và SQL visibility

Có một số chiến lược:

1. **OpenTelemetry JDBC instrumentation** qua Java agent hoặc library wrapper.
2. **Datasource proxy/P6Spy** để log SQL timing (phụ thuộc thư viện/config).
3. **Hibernate SQL logging** để xem generated SQL.
4. **Hibernate Statistics** để tổng hợp entity/query/flush metrics.
5. **Database logs/monitoring** để xem SQL runtime và waits.

Mỗi lớp thấy một phần:

~~~text
Hibernate ORM
   |
   | generated SQL + bind values
   v
Connection pool / JDBC wrapper
   |
   | connection acquisition and statement timing
   v
JDBC Driver
   |
   | network protocol
   v
DB server
   |
   | execution plan, locks, WAL, commit
~~~

Đừng lắp nhiều SQL loggers vô kiểm soát: có thể tạo duplicate logs, performance overhead hoặc expose bind values ở nhiều nơi.

## 28. Hibernate SQL logging

Với Hibernate ORM 6.x trong Spring Boot, cấu hình thường gặp:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tùy version, bind logger names có thể khác. SQL logging hữu ích để thấy:

- SQL SELECT/INSERT/UPDATE/DELETE thực tế.
- N+1 statements.
- `flush()` phát DML vào lúc nào.
- Batching hoặc ordering có làm SQL shape đổi không.
- SQL comments/tags nếu được bật.

**Cẩn trọng:** Bind logging có thể chứa email, token, số điện thoại, dữ liệu tài chính hoặc nội dung riêng tư. Chỉ bật trên dữ liệu test/sanitized khi có thể; production cần retention/access controls và không dùng TRACE bừa bãi.

Log SQL **không có nghĩa** có một trace span kết nối tới HTTP request nếu logger chưa có MDC/correlation.

## 29. Hibernate Statistics

Bật thống kê trong môi trường kiểm soát:

~~~properties
hibernate.generate_statistics=true
~~~

Với Hibernate SessionFactory:

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();

long loaded = statistics.getEntityLoadCount();
long updates = statistics.getEntityUpdateCount();
long flushes = statistics.getFlushCount();
long prepared = statistics.getPrepareStatementCount();
~~~

Cần import `org.hibernate.stat.Statistics`.

**Statistics của SessionFactory là tổng hợp**, không đại diện độc quyền cho một request nếu nhiều threads đang chạy. Để đo một scenario, nên cô lập workload hoặc có phương án metric per request, chẳng hạn custom observation hoặc query counter trong test.

Không tự clear global statistics giữa production requests: điều đó làm sai dữ liệu của các threads khác.

## 30. Mối quan hệ giữa Hibernate event và trace

Hibernate có lifecycle/internal events như:

- Pre/PostLoad hoặc JPA `@PostLoad`.
- PreInsert/PostInsert.
- PreUpdate/PostUpdate.
- Flush events.
- Collection actions.

Có thể instrument một số event để xem persistence lifecycle, nhưng:

- `PostUpdate` không đồng nghĩa transaction commit.
- Hibernate event SPI gắn provider/internal operations.
- Bulk SQL không có per-entity lifecycle như ORM update thông thường.
- Listener có thể chạy nhiều lần hoặc theo những timings khác người viết business code kỳ vọng.

Nếu muốn biết “Order đã được xác nhận và committed?”, cần theo dấu business command và transaction outcome, **không chỉ quan sát một `PostUpdateEvent`**.

## 31. JDBC batching và số spans

Một vòng `persist()` 1.000 entities không đồng nghĩa 1.000 network round trips. Hibernate có thể batch prepared statements theo cấu hình, mapping, ID generator và dialect.

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Nếu batching thực sự hoạt động, mỗi JDBC batch có thể chứa nhiều statement executions. Instrumentation có thể tạo span quanh `executeBatch()` hoặc từng statement tùy implementation.

Do đó, không suy ra:

- Số JDBC spans = số rows.
- Số prepared statements = số network packets.
- Một trace có 1.000 Hibernate entity actions thì nhất thiết có 1.000 JDBC execute spans.
- Bật `batch_size=50` là bảo đảm driver đã batch đúng 50 rows.

Đo actual JDBC batches, driver metrics và throughput trên DB thật.

## 32. Flush time và lock waiting

Nếu `flush()` lâu, nguyên nhân có thể nằm ở:

- Hibernate dirty checking và action queue.
- Số lượng entities/collections.
- JDBC statement preparation/batching.
- Database row/table locks.
- Foreign key/unique constraint checks.
- DB IO/WAL.
- Network latency.
- Driver result handling.

Một span `hibernate.flush` dài không đủ phân biệt tất cả. Nếu có JDBC spans con, phần chênh lệch có thể gợi ý ORM overhead; nhưng không chính xác tuyệt đối nếu instrumentation không cover toàn bộ operation.

Cần đối chiếu với DB monitoring/lock waits và heap/CPU profiles.

## 33. Theo dấu connection pool HikariCP

Các chỉ số thường hữu ích của HikariCP khi tích hợp Micrometer:

- `hikaricp.connections.active`
- `hikaricp.connections.idle`
- `hikaricp.connections.pending`
- `hikaricp.connections.acquire`
- `hikaricp.connections.usage`
- `hikaricp.connections.timeout`

Tên metrics và tags có thể khác theo phiên bản/registry. Cần kiểm tra endpoint actuator/metrics thực tế.

Ví dụ:

~~~text
p95 HTTP latency tăng
  +-- Hikari pending connections tăng
  +-- acquire time tăng
  +-- JDBC execute time ổn định
~~~

Khả năng cao bottleneck là pool/connection lifetime chứ không phải bản thân SQL.

**Đừng tăng maxPoolSize lập tức** nếu DB đã bão hòa: nhiều connections hơn có thể khiến lock contention và DB load tệ hơn.

## 34. Transaction kéo dài vì gọi HTTP khi giữ connection

Anti-pattern:

~~~java
@Transactional
public void confirm(Long id) {
    Order order = orders.findById(id).orElseThrow();

    inventoryClient.reserve(order.getItems()); // Remote call lâu.

    order.confirm();
}
~~~

Tùy Spring/Hibernate connection acquisition mode, connection có thể đã được lấy trước remote call. Nếu inventory service chậm, transaction/connection/resources có thể bị giữ lâu.

Trace có thể thấy:

~~~text
transaction scope: 900 ms
    |
    +-- DB SELECT: 20 ms
    +-- inventory HTTP: 700 ms
    +-- DB UPDATE: 20 ms
~~~

Tối ưu cần cân nhắc tính đúng đắn:

- Tách remote calls khỏi DB transaction nếu domain cho phép.
- Dùng saga/outbox khi cần phối hợp distributed workflows.
- Thiết kế reservation token/idempotency.
- Giới hạn remote timeout.
- Không đơn giản di chuyển HTTP call ra ngoài transaction nếu làm mất invariants mà chưa có compensation.

## 35. Database PostgreSQL: đang chờ gì?

Nếu dùng PostgreSQL, một truy vấn chẩn đoán có thể đọc `pg_stat_activity`:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE application_name = 'order-service';
~~~

Tùy quyền database, dữ liệu có thể bị giới hạn. `wait_event_type='Lock'` gợi ý lock contention; `Client`, `IO` hoặc các wait types khác cần diễn giải theo PostgreSQL version.

Có thể dùng `pg_blocking_pids(pid)` để tìm blockers:

~~~sql
SELECT pid, pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
~~~

Không lấy PID làm trace ID. PID là server process/backend identifier và có vòng đời khác.

## 36. SQL query plan và EXPLAIN

Một SQL chậm có thể do:

- Thiếu index.
- Bad cardinality estimates.
- Join algorithm không phù hợp.
- Sort/hash lớn.
- Filter trên nhiều rows.
- N+1 ở application.
- Lock/IO contention.

PostgreSQL minh họa:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

**`ANALYZE` thực sự chạy câu SQL.** Với mutation queries còn có side effects nếu không dùng transaction/rollback kiểm soát; chỉ chạy trên DB test hoặc trong điều kiện được cho phép.

`EXPLAIN` cho biết execution plan, không tự cung cấp request correlation. Gắn SQL shape/normalized query identity từ traces để chọn đúng query đưa vào EXPLAIN.

## 37. pg_stat_statements và normalized SQL

PostgreSQL extension `pg_stat_statements` (khi được cài/cho phép) có thể tổng hợp execution statistics theo normalized statements. Nó giúp tìm câu SQL nặng **trên toàn hệ**, không phải trace đơn lẻ.

Hướng kết hợp:

1. Trace tìm operation có latency cao.
2. JDBC span/log xác định SQL shape.
3. DB monitoring/pg_stat_statements xem aggregate cost.
4. EXPLAIN xem query plan trên dataset đại diện.
5. Trở lại application đo heap, ORM hydration và pool acquisition.

Không giả định DB log query text có traceId. Nếu phải gắn correlation trong SQL comments, cần kiểm soát PII, log volume và effects lên query normalization/plan cache.

## 38. SQL comments để gắn nhãn query

Hibernate Query có thể hỗ trợ comments, tùy setting và query API:

~~~java
Query<Order> query = session.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
);

query.setParameter("status", OrderStatus.PENDING);
query.setComment("usecase=order-pending-list");
~~~

Hibernate có tùy chọn dùng SQL comments, ví dụ `hibernate.use_sql_comments`, để thêm comment vào generated SQL trong những trường hợp được hỗ trợ.

**Chỉ dùng nhãn tĩnh/đã kiểm soát**, không chèn trực tiếp traceId, tenant name, email hay user input vào SQL comments trên mọi request nếu chưa đánh giá privacy, log volume và plan-cache behavior.

Một SQL comment có thể giúp chẩn đoán query source, nhưng nó không thay W3C distributed trace context.

## 39. N+1 queries trong trace

Ví dụ:

~~~java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu `customer` là LAZY, Hibernate có thể phát:

~~~text
SELECT orders ...                  1 lần
SELECT customer WHERE id = ?     N lần
~~~

Trace có thể cho thấy nhiều SQL spans lặp cùng shape. Hibernate Statistics cũng có thể cho thấy prepared statement count tăng.

Giải pháp:

- DTO projection có join cần thiết.
- `join fetch` hoặc EntityGraph khi phù hợp.
- Batch fetching.
- Phân trang và giới hạn row count.
- Không dùng `EAGER` bừa bãi vì có thể tăng graph và queries ngoài dự đoán.

Kiểm tra số statements per request/operation, không chỉ latency của từng SQL riêng lẻ.

## 40. N+1 do OSIV hoặc serialization

Nếu REST controller trả JPA entities trực tiếp:

~~~java
return orderRepository.findAll();
~~~

Serializer có thể truy cập lazy fields **sau khi service method đã kết thúc**, nhất là khi Open Session in View được bật. Traces có thể cho thấy SQL queries xảy ra trong giai đoạn HTTP response serialization thay vì trong service span.

Triệu chứng:

- Repository span nhanh.
- Response latency vẫn cao.
- SQL statements xuất hiện sau service return.
- N+1 gắn với JSON serialization.

Khắc phục bằng DTO/projection/fetch plan ở service và kiểm soát OSIV, không chỉ tối ưu repository method.

## 41. Rollback và UnexpectedRollbackException

Một method con có thể bắt exception nhưng đã đánh dấu transaction rollback-only.

~~~java
@Transactional
public void confirm(Long id) {
    try {
        pricingService.applyDiscount(id);
    } catch (RuntimeException ex) {
        log.warn("Discount failed", ex);
    }

    // Outer method có thể return bình thường.
}
~~~

Nếu inner REQUIRED đã đánh dấu shared transaction rollback-only, khi outer scope cố commit có thể phát `UnexpectedRollbackException`.

Một trace nên phân biệt:

- Business method body kết thúc bình thường.
- Transaction outcome là ROLLBACK.
- Exception xuất hiện ở transaction interceptor/outer boundary.
- JDBC statements trước đó có thể thành công nhưng không durable.

**Không gán span OK cho toàn use case trước khi transaction outcome được biết.**

## 42. Constraint violation có thể xuất hiện ở flush/commit

~~~java
@Transactional
public void createOrder(Order order) {
    entityManager.persist(order);
    // Chưa chắc INSERT xảy ra ngay.
}
~~~

Nếu unique/FK constraint bị vi phạm, exception có thể xuất hiện lúc flush hoặc transaction commit, sau khi body method đã return.

Khi điều tra:

- Ghi stack trace đầy đủ ở outer boundary.
- Correlate SQL statement/constraint name (redacted).
- Không nuốt Hibernate exception rồi tiếp tục dùng Session.
- Phân biệt application validation với DB constraint enforcement.
- Đừng kết luận `persist()` “thành công” đồng nghĩa commit sẽ thành công.

Trace around transaction proxy có thể bao gồm failure mà method-body-only span không thấy.

## 43. Transaction timeout và JDBC query timeout

Các timeout khác nhau:

- HTTP server/client timeout.
- Spring transaction timeout.
- Hibernate/JPA query timeout.
- JDBC statement timeout.
- Database statement/lock timeout.
- Connection pool acquisition timeout.

Một request timeout 5 giây không tự chứng minh database query đã bị cancel sau 5 giây. Cần kiểm tra từng timeout và cancellation propagation.

Ví dụ PostgreSQL:

~~~sql
SET LOCAL statement_timeout = '3s';
~~~

Lệnh này là DB-specific và chỉ áp dụng trong transaction scope tương ứng. Không tự đặt trong mọi request nếu chưa thiết kế chính sách.

Tại tracing layer, phân biệt **client đã bỏ cuộc** với **DB statement đã dừng**. Một request canceled vẫn có thể để lại background work/resource cho tới khi driver/DB xử lý cancellation.

## 44. Async và thread-local context

Imperative Spring transactions thường được gắn với thread. Ví dụ:

~~~java
@Transactional
public void confirm(Long id) {
    executor.execute(() -> {
        // Công việc chạy thread khác.
    });
}
~~~

Async task không tự tham gia database transaction đang mở trên caller thread. Trace context cũng **không luôn tự truyền** vào custom `Executor` nếu không có context propagation/instrumentation phù hợp.

Để truyền trace context, dùng Micrometer Context Propagation/OpenTelemetry context-aware executor hoặc Spring instrumentation tương ứng với stack.

Không giữ một EntityManager/Session rồi chia sẻ sang worker thread; Hibernate Session không thread-safe.

## 45. Reactor/reactive context khác imperative thread-local

Với Reactor hoặc reactive data access, context có thể được lưu trong Reactor Context thay vì ThreadLocal theo kiểu imperative.

Một operator đổi scheduler có thể làm mất context nếu instrumentation không hỗ trợ hoặc code tự tạo luồng ngoài pipeline.

Cần phân biệt:

- Spring Data JPA/Hibernate ORM truyền thống: imperative transaction/thread model.
- R2DBC: reactive transaction integration, không dùng JDBC/Hibernate Session theo cùng cách.
- Reactive HTTP caller tới một JPA service: boundary chuyển tiếp cần thiết kế riêng.

Không dùng code copy MDC ThreadLocal làm lời giải chung cho mọi reactive flow. Kiểm tra trace/span continuity qua `publishOn`, `subscribeOn` và custom schedulers nếu ứng dụng dùng Reactor.

## 46. Trace qua message broker và outbox

Một command có thể:

1. Commit Order transaction.
2. Ghi outbox row trong cùng transaction.
3. Dispatcher gửi message.
4. Consumer ở service khác xử lý message trong transaction mới.

~~~mermaid
sequenceDiagram
    participant S as Order Service
    participant DB as Order DB
    participant P as Outbox Publisher
    participant B as Broker
    participant C as Consumer
    S->>DB: UPDATE Order + INSERT Outbox
    DB-->>S: COMMIT
    P->>DB: Read committed outbox
    P->>B: Publish event + context headers
    B->>C: Deliver event
    C->>C: New processing span / transaction
~~~

Có thể propagate W3C context qua message headers hoặc tạo trace mới với **span link** tới producer context. Chọn parent/links theo instrumentation và semantics async, không tự nối mọi consumer processing vào một request trace mãi mãi nếu event được xử lý nhiều giờ sau.

Lưu các IDs riêng: `eventId`, `aggregateId`, trace context/correlation ID. Event có thể retry/duplicate; consumer vẫn phải idempotent. **Tracing không bảo đảm delivery hoặc exactly-once processing.**

## 47. AFTER_COMMIT listener cũng là boundary riêng

Spring:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(OrderConfirmed event) {
    notificationService.send(event);
}
~~~

Listener chạy sau database commit nếu event được publish trong transaction được quản lý phù hợp. Nhưng:

- Listener có thể chạy sau khi transaction chính đã kết thúc.
- Resources có thể vẫn bound trong lúc completion callbacks chạy.
- Một DB write mới trong listener cần transaction mới nếu muốn commit rõ ràng.
- Process crash vẫn có thể làm event mất.
- Nếu listener async, trace context propagation cần được hỗ trợ.

Trace cho thấy AFTER_COMMIT span thành công không bảo đảm broker đã persisted event nếu client báo success quá sớm. Với durable integration delivery, dùng outbox/retry/ack và business idempotency.

## 48. Sampling và những lỗi hiếm

Nếu lấy 10% traces, một lỗi hiếm có thể không được sample. Metrics và structured logs vẫn rất cần.

Các chiến lược:

- Head-based sampling, ví dụ xác suất 0.1.
- Parent-based sampling để giữ continuity qua services khi phù hợp.
- Tail-based sampling tại Collector cho slow/error traces nếu backend/architecture hỗ trợ.
- Exemplars nối metrics tới traces được sample.
- Dynamic debugging có thời hạn và quyền kiểm soát.

Không hứa tail sampling luôn capture mọi lỗi nếu Collector quá tải hoặc có data loss. Cần xem chi phí ingest, storage, latency và PII exposure.

Một hệ thống tốt có error-rate/latency metrics ngay cả khi trace sampling thấp.

## 49. Cardinality và bảo mật

Không đưa dữ liệu không kiểm soát vào span names/metric labels:

**Không tốt:**

~~~text
span.name = "GET /orders/123456789"
metric label userId = "user-998877"
db.statement = "select ... password='secret'"
~~~

**Tốt hơn:**

~~~text
span.name = "GET /orders/{id}"
metric label route = "/orders/{id}"
db.operation.name = "SELECT"
query template = "select ... where id = ?"
~~~

Các nguyên tắc:

- Redact SQL bind values mặc định, đặc biệt PII/secrets.
- Không ghi token/JWT/password, raw request/response bodies tùy tiện.
- Low-cardinality tags cho metrics; high-cardinality IDs trong log/trace chỉ khi được cho phép.
- Áp dụng retention, access control và sampling policy.
- Kiểm tra exporter/collector để không gửi dữ liệu nhạy cảm ngoài phạm vi hợp đồng.
- Cân nhắc trace context headers đi xuyên trust boundaries.

## 50. Log correlation khi span không được sample

Một request có thể không được trace backend lưu nhưng application logs vẫn có requestId/traceId nếu context được tạo và logging integration hoạt động.

Hãy giữ:

- Stable requestId để user support tìm logs.
- TraceId để nối với spans được sample nếu có.
- EventId để nối async messages.
- Transaction outcome logs ở đúng boundary.
- Error code/classification thay vì chỉ raw exception string.

Không tạo hàng trăm custom identifiers nếu chúng không được dùng trong workflow chẩn đoán. Mỗi ID cần có scope/lifetime rõ.

## 51. Trace không phải nguồn sự thật về commit

Một span `SQL UPDATE status=OK` nghĩa là JDBC operation theo instrumentation đã kết thúc thành công. Nó **không** đồng nghĩa:

- Application đã commit.
- Transaction không rollback về sau.
- Replica đã nhìn thấy row mới.
- Outbox event đã được broker publish.
- Consumer đã xử lý message.
- Business invariant đã hoàn tất trên tất cả services.

Nếu cần biết commit outcome, instrument transaction manager/completion boundary hoặc ghi log sau commit với semantics rõ. Nếu cần xác nhận end-to-end business outcome, dùng các state transitions/audit/outbox records trong database.

## 52. Bảng chẩn đoán triệu chứng thường gặp

| Triệu chứng | Tín hiệu cần kiểm tra | Hướng điều tra |
|---|---|---|
| HTTP p95 tăng nhưng SQL spans ngắn | Pool acquire/pending, service gaps | Connection starvation, remote calls |
| Rất nhiều SELECT giống nhau | Statement count, N+1 pattern | Fetch plan/DTO/batch fetch |
| SQL UPDATE thành công nhưng DB không đổi | Commit/rollback outcome, transaction exceptions | Flush ≠ commit |
| Body method OK nhưng request lỗi | Transaction interceptor exception | Commit/rollback-only |
| Một query chậm bất thường | DB waits/locks/EXPLAIN | Lock, index, IO, plan |
| `flush()` dài | JDBC spans + ORM CPU/GC | Dirty checking, batching, DB writes |
| Rất ít JDBC spans nhưng request đọc lớn chậm | ResultSet/hydration time, heap | Fetch size, mapping/projection |
| Hikari pending tăng | Acquire/usage metrics | Pool sizing, transaction duration |
| SQL log không có traceId | MDC/tracing context integration | Logging correlation |
| Trace đứt ở HTTP call | Propagation headers/client instrumentation | W3C trace context |
| Trace đứt ở async task | Executor/Reactor propagation | Context-aware scheduling |
| Consumer event không cùng trace | Broker header/links, async semantics | Extract/parent/link design |
| Bulk update thiếu entity callbacks | Hibernate lifecycle bypass | Explicit business/audit logic |
| SQL bind logs lộ PII | Logging categories/exporter policy | Redaction và access controls |

## 53. End-to-end runbook điều tra request chậm

**Bước 1 — Xác định symptom.** Lấy route, service version, environment, timestamp window, p95/p99 và error rate. Không kết luận từ một request ngoại lệ.

**Bước 2 — Tìm trace hoặc requestId.** Quan sát parent/child spans và missing instrumentation. Xác định caller, downstream calls, DB operations.

**Bước 3 — Đặt transaction boundary.** Xem `@Transactional`, propagation, transaction manager, outer vs inner scope. Kiểm tra commit/rollback ở đâu.

**Bước 4 — Phân loại thời gian.** Tách business CPU, remote HTTP, pool acquire, JDBC execute, result hydration, flush và commit nếu instrumentation cho phép.

**Bước 5 — Đối chiếu metrics.** Hikari active/pending, JVM heap/GC, DB CPU/IO, lock waits, throughput.

**Bước 6 — Kiểm tra SQL shape.** Tìm N+1, high row counts, missing limits, unexpected flush, repeated queries, batching ineffective.

**Bước 7 — Phân tích DB.** Slow logs, EXPLAIN, lock/wait events, pg_stat_statements theo quyền và môi trường.

**Bước 8 — Xác minh correctness.** DB commit outcome, rollback, eventual consistency, outbox message state.

**Bước 9 — Thử fix có đối chứng.** Thay query/index/fetch/transaction boundary, đo lại trên load tương đương.

**Bước 10 — Ghi kết luận.** Nêu stack versions, bằng chứng từ traces/logs/metrics/DB, không chỉ một suy đoán.

## 54. Thiết kế một kiểm thử quan sát đúng ranh giới

Một integration test có thể tạo use case:

~~~java
@Service
public class TestOrderService {

    @Transactional
    public void updateAndRollback(Long id) {
        Order order = repository.findById(id).orElseThrow();
        order.confirm();

        entityManager.flush();

        throw new IllegalStateException("force rollback");
    }
}
~~~

Kiểm chứng:

1. SQL UPDATE có thể được phát khi flush.
2. Transaction rollback.
3. Mở transaction/EntityManager mới, Order không ở trạng thái confirmed.
4. Trace/log service có exception.
5. Không log `committed=true` trước outcome.
6. Nếu có AFTER_COMMIT listener, nó không chạy cho transaction rollback.

Với Spring tests, chú ý `@Transactional` trên test method thường rollback mặc định, có thể làm sai cách diễn giải commit của service. Khi cần commit thật, tổ chức test transaction boundary rõ ràng.

## 55. Kiểm thử propagation và commit span

Tạo hai beans:

~~~java
@Service
public class OuterService {

    @Transactional
    public void run(Long id) {
        innerService.updateWithRequiresNew(id);
        // Có thể lỗi sau khi inner commit.
        throw new IllegalStateException("outer failed");
    }
}
~~~

~~~java
@Service
public class InnerService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateWithRequiresNew(Long id) {
        // DB mutation có transaction riêng.
    }
}
~~~

Một trace tốt cho thấy business call chain, nhưng bạn phải ghi nhận **inner commit** và **outer rollback** là hai kết quả khác nhau.

Thực hiện tests qua Spring-managed beans/proxies. Nếu dùng self-invocation, `REQUIRES_NEW` có thể không được áp dụng.

## 56. Kiểm thử N+1 và pool pressure

N+1 scenario:

~~~java
List<Order> orders = orderRepository.findAll();
orders.forEach(o -> o.getCustomer().getName());
~~~

Test:

- SQL statement count theo instrumentation.
- Query shapes lặp.
- Latency theo N orders.
- Thay bằng DTO projection/fetch join và so sánh.
- Kiểm tra collection fetch join không tạo explosion hoặc pagination sai.

Pool scenario:

- Chạy load test có concurrency giới hạn.
- Quan sát Hikari acquire/pending/usage.
- Giữ DB query shape tương đương.
- Tìm connection leaks/long transactions.
- Không cố tình gây quá tải production để tạo trace.

Một test ứng dụng đúng hơn một lời khuyên “tăng pool size là xong”.

## 57. Checklist instrumentation cho Spring/Hibernate

**Trace context**

- [ ] HTTP incoming/outgoing có propagate W3C traceparent?
- [ ] Service name/version/environment được gắn thống nhất?
- [ ] Custom business spans không trùng auto spans?
- [ ] Async executors/Reactor tasks có context propagation?
- [ ] Message headers hoặc span links phản ánh event processing?
- [ ] Sampling/retention phù hợp volume và compliance?

**Transaction**

- [ ] Biết transaction manager và propagation cho mỗi use case?
- [ ] Observation bao gồm commit/rollback nếu claim đo cả transaction?
- [ ] Có phân biệt flush và commit?
- [ ] Có ghi nhận rollback-only/commit exception?
- [ ] REQUIRES_NEW/nested transactions có outcome riêng?
- [ ] Không chia sẻ Hibernate Session giữa threads?

**JDBC và DB**

- [ ] Biết pool acquire wait, JDBC execute và ResultSet fetch khác nhau?
- [ ] Hikari pending/active/acquire/usage được giám sát?
- [ ] Hibernate SQL logging/Statistics được bật có kiểm soát?
- [ ] DB wait events, query plans và lock analysis có công cụ?
- [ ] N+1, batching, high row counts có thể nhận diện?
- [ ] SQL/query attributes không chứa secrets/bind PII?

**Vận hành**

- [ ] Có runbook theo traceId/requestId?
- [ ] Có dashboards cho p95/p99 và DB pool saturation?
- [ ] Có integration tests flush→rollback và propagation?
- [ ] Có kiểm tra context continuity qua HTTP/async/broker?
- [ ] Có xác định trace sampling tạo lỗ hổng quan sát không?

## 58. Bài tập thực hành

1. **Trace một CRUD request:** Vẽ controller→service→repository→Hibernate→JDBC→database cho thao tác Order confirm và chỉ rõ span nào là auto, span nào cần custom.
2. **Flush vs commit:** Trong transaction, sửa managed entity, gọi `flush()`, sau đó throw exception. So sánh SQL log và DB state từ transaction mới.
3. **Timer trong body:** Đặt stopwatch trong method `@Transactional`, rồi thêm timer ở caller ngoài proxy. Giải thích khác biệt duration khi commit chậm.
4. **REQUIRED:** Outer/inner services cùng REQUIRED; chứng minh inner return không có commit riêng.
5. **REQUIRES_NEW:** Inner commit, outer rollback; thiết kế logs/trace attributes không đánh đồng outcomes.
6. **Pool acquisition:** Mô phỏng pool saturation an toàn trong test, đo Hikari pending/acquire và SQL latency.
7. **N+1:** Tạo 100 Orders với LAZY Customer, đo statement count; thay bằng DTO projection hoặc fetch join.
8. **ResultSet hydration:** Trả nhiều rows, so sánh JDBC execute duration và tổng thời gian materialize List.
9. **SQL binding privacy:** Bật Hibernate bind logging trên fake data, xác định PII fields và đề xuất redaction policy.
10. **Trace propagation HTTP:** Gửi traceparent từ service A đến B, kiểm tra trace ID continuity trên backend.
11. **Async context:** Dùng custom Executor và quan sát trace discontinuity; sửa bằng context propagation phù hợp stack.
12. **Messaging:** Ghi outbox row, dispatch event với eventId/trace context, kiểm tra consumer trace liên kết và duplicate handling.
13. **DB locks:** Trong PostgreSQL test DB, tạo hai transactions tranh chấp cùng row; quan sát pg_stat_activity lock wait và JDBC duration.
14. **Sampling:** So sánh traces với sampling rate 1.0 trong test và 0.1, giải thích vì sao error-rate metric vẫn cần thiết.
15. **Runbook:** Lấy một trace giả định có request 1 s, JDBC SQL 10 ms, pool acquire 800 ms. Viết kết luận và kế hoạch kiểm chứng.

## 59. Sơ đồ quyết định chẩn đoán

~~~mermaid
flowchart TD
    A["Request chậm hoặc lỗi"] --> B["Tìm traceId và service span"]
    B --> C{"Có JDBC spans?"}
    C -- "Không" --> D["Kiểm tra instrumentation / context / cache"]
    C -- "Có" --> E{"SQL execute dài?"}
    E -- "Không" --> F["Pool acquire / hydration / CPU / remote calls"]
    E -- "Có" --> G["DB locks / waits / EXPLAIN / IO"]
    D --> H["Xác định transaction boundary"]
    F --> H
    G --> H
    H --> I{"COMMIT hay ROLLBACK?"}
    I -- "Rollback/error" --> J["Trace exception/rollback-only/constraints"]
    I -- "Commit" --> K["Kiểm tra outcome và downstream events"]
    J --> L["Fix có đối chứng và đo lại"]
    K --> L
~~~

## 60. Nguồn tham khảo để đối chiếu theo phiên bản

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/) — distributed traces, context propagation, Java instrumentation và semantic conventions.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — header `traceparent`/`tracestate` và cấu trúc trace identifiers.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html) — observations, handlers, context và integration.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/) — bridges, tracing context và propagation.
- [Spring Boot Actuator Reference](https://docs.spring.io/spring-boot/reference/actuator/index.html) — observability, tracing, metrics và configuration tương ứng phiên bản.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — declarative transactions, propagation và proxy boundary.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — Session, flush, batching và statistics.
- [PostgreSQL Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity và wait events.

Những trang `current` có thể mô tả phiên bản mới hơn hệ thống. Đặc biệt tên metrics, semantic-convention fields, dependencies và tracing properties phải được đối chiếu với **đúng Spring Boot, Micrometer, OpenTelemetry, Hibernate và JDBC driver** đang triển khai.

## 61. Tổng kết

**Dấu vết xuyên ranh giới dịch vụ–giao dịch–JDBC chỉ đáng tin khi các ranh giới được gọi đúng tên.**

- **Service span** cho biết thời gian xử lý use case, nhưng nếu instrument bên trong method `@Transactional`, có thể bỏ sót thời gian commit ở proxy.
- **Hibernate flush** cho biết pending changes đã được đồng bộ tới database trong transaction; **flush không phải commit**.
- **JDBC span** đo ở client/driver boundary, có thể gồm network và DB waits; không tự là DB CPU time.
- **Connection pool acquire wait** có thể chiếm phần lớn latency dù SQL rất nhanh.
- **Distributed trace ID** liên kết HTTP/async/message processing; nó **không tạo transaction atomic giữa services**.
- **After-commit/event/outbox** có các mốc durability/delivery riêng; cùng trace không đồng nghĩa event đã đến consumer.
- **Logs, metrics, Hibernate Statistics, SQL logging và database diagnostics** cần bổ sung cho trace để phân biệt N+1, lock contention, GC, batching, pool starvation và rollback.
- **Bảo mật dữ liệu quan sát** quan trọng như tính đầy đủ của trace: không xuất PII/secrets trong SQL binds, baggage, metric labels hoặc span names.

Khi điều tra một lỗi thật, hãy đi từ **trace/requestId → ranh giới transaction → pool/JDBC SQL → database wait/query plan → commit outcome → side effects**, sau đó đo lại trên workload có đối chứng. Đây là cách biến dấu vết thành bằng chứng chẩn đoán, thay vì chỉ là một biểu đồ đẹp.
