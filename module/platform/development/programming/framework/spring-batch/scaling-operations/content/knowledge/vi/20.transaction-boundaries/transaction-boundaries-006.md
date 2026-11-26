# Không giữ transaction qua network call trong Spring Batch

Một Spring Batch job đọc đơn hàng từ PostgreSQL, gọi HTTP để lấy giá vận chuyển, rồi ghi kết quả. Ở bản thử nghiệm, mỗi HTTP call mất khoảng 150 ms và job vẫn chạy. Khi triển khai tám worker threads, dịch vụ đối tác bắt đầu trả lời chậm ở p99, connection pool liên tục có yêu cầu chờ, các chunk rollback và thời gian chạy batch tăng mạnh. Điều đáng chú ý: database không dùng nhiều CPU, nhưng các JDBC connection và row lock vẫn có thể bị giữ trong lúc ứng dụng **đang chờ một hệ thống trên mạng**.

Bài học **“Không giữ transaction qua network call”** thuộc chương **Transaction boundary** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo giới hạn tài nguyên thực tế.

Nguyên tắc cần ghi nhớ: **đặt transaction database ngắn, xác định, chỉ bao quanh thao tác dữ liệu cần tính nguyên tử; không giữ transaction đang mở trong lúc chờ HTTP/gRPC, broker hoặc API bên ngoài**. Tuy nhiên, việc tách một network call khỏi transaction cũng tạo ra **khoảng lỗi giữa hai hệ thống**. Vì thế phải thiết kế idempotency, trạng thái trung gian, retry và reconciliation cùng lúc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định ranh giới transaction mặc định của chunk-oriented step và vì sao network call trong `ItemProcessor` có thể kéo dài transaction.
2. Phân biệt **transaction logic**, JDBC connection thực sự được mượn, DB locks, broker acknowledgement và side effect bên ngoài.
3. Giải thích tác động của HTTP timeout, p95/p99 latency và retry lên thời gian giữ connection, throughput và Hikari pool.
4. Nhận diện anti-pattern gọi API bên trong `@Transactional`, `ItemWriter`, tasklet hoặc chunk worker.
5. Thiết kế quy trình **claim ngắn → gọi mạng ngoài transaction → ghi kết quả trong transaction ngắn**.
6. Dùng lease, fencing token và business idempotency để phục hồi worker bị crash hoặc request bị lặp.
7. Áp dụng transactional outbox/inbox khi cần gửi message hay kích hoạt tác dụng phụ sau DB commit.
8. Hiểu khác biệt giữa remote chunking/remote partitioning và việc gọi API nghiệp vụ ở từng worker.
9. Tính giới hạn concurrency theo HTTP latency, DB connection budget, CPU và SLA.
10. Kiểm thử lỗi ở cả hai phía commit/network, đo đúng duration và đối soát dữ liệu trước khi publish.

## 2. Một transaction “qua network call” nguy hiểm như thế nào?

**Transaction boundary** là đoạn công việc được transaction manager điều phối commit hoặc rollback trên một hay nhiều tài nguyên phù hợp. Với Spring JDBC/JPA thông thường, `@Transactional` hoặc `TransactionTemplate` bắt đầu một transaction database; database có thể cấp connection, giữ row locks, snapshot/undo/WAL resources cho đến lúc transaction kết thúc.

Nếu đoạn code bên trong transaction còn gọi một HTTP endpoint, transaction logic vẫn chưa kết thúc trong lúc chờ phản hồi.

~~~java
@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final ShippingClient shippingClient;

    // ANTI-PATTERN: network call nằm giữa các DB operations
    @Transactional
    public void enrichOrder(long orderId) {
        jdbc.update("""
            UPDATE orders
            SET status = 'PROCESSING'
            WHERE order_id = ?
            """, orderId);

        ShippingQuote quote = shippingClient.fetchQuote(orderId);
        // Endpoint có thể timeout sau 5-30 giây.

        jdbc.update("""
            UPDATE orders
            SET shipping_fee = ?, status = 'READY'
            WHERE order_id = ?
            """, quote.fee(), orderId);
    }
}
~~~

Trong ví dụ này, transaction DB đã sửa hàng `orders` trước khi gửi request. Tùy isolation/driver, row lock và connection của transaction có thể bị giữ cho đến khi method trả về hoặc ném exception.

~~~mermaid
sequenceDiagram
    participant W as Worker JVM
    participant D as Database
    participant A as HTTP API
    W->>D: BEGIN + UPDATE status
    Note over D: Transaction/lock còn mở
    W->>A: GET/POST request
    Note over W,A: Chờ network p99 / retry / timeout
    A-->>W: Response hoặc lỗi
    W->>D: UPDATE result
    W->>D: COMMIT / ROLLBACK
    Note over D: Chỉ sau đó transaction kết thúc
~~~

Hệ quả có thể thấy:

- **Connection hold time dài:** connection không quay lại pool để phục vụ transaction khác.
- **Row/table lock contention:** worker khác đợi lock, gây p95/p99 transaction latency tăng.
- **Deadlock/lock timeout:** nhiều worker giữ các khóa khác nhau trong lúc gọi mạng rồi cần thêm khóa.
- **Transaction log/snapshot pressure:** DB phải giữ tài nguyên transaction đang mở; còn phụ thuộc engine/isolation.
- **Rollback scope lớn:** API đã trả kết quả nhưng DB rollback do lỗi ở cuối chunk.
- **Retry khuếch đại tải:** một HTTP timeout dẫn tới rollback và xử lý lại cả chunk, có thể gọi API lại nhiều lần.
- **Throughput và SLA thiếu ổn định:** batch bị chi phối bởi tail latency và rate limit của dịch vụ mạng.

### 2.1. Có phải vừa gọi @Transactional là connection lập tức bị giữ?

Không thể khẳng định tuyệt đối. Với Spring transaction management, thời điểm lấy JDBC connection thực phụ thuộc `PlatformTransactionManager`, `DataSource`, `LazyConnectionDataSourceProxy`, JPA và các lần truy cập DB. Một transaction logic có thể được mở trước khi một connection vật lý được mượn; nhưng **nếu DB work hoặc lock đã xảy ra trước network call**, transaction vẫn chưa commit và các resource có thể còn bị giữ.

Điều cần tránh không chỉ là “giữ connection”, mà là **tạo một ranh giới tính nguyên tử dài, phụ thuộc độ trễ và trạng thái của hệ thống khác**. Không dựa vào lazy acquisition để biện hộ cho một thiết kế transaction kéo dài không kiểm soát.

### 2.2. HTTP timeout và database transaction timeout khác nhau

| Timeout | Bảo vệ gì? | Không bảo đảm gì? |
| --- | --- | --- |
| HTTP connect timeout | Giới hạn thời gian thiết lập kết nối | Không giới hạn toàn bộ vòng đời yêu cầu |
| HTTP read/response timeout | Giới hạn giai đoạn đợi dữ liệu theo cấu hình client | Không nhất thiết là timeout tổng của nhiều retries |
| Overall request deadline | Ngân sách thời gian toàn call, kể cả retry nếu client hỗ trợ | Không rollback side effect đã thực hiện ở service ngoài |
| Spring transaction timeout | Giới hạn thời gian transaction theo manager/driver | Không bắt buộc ngắt ngay blocking HTTP call |
| JDBC statement/query timeout | Giới hạn thời gian chạy câu SQL | Không giám sát HTTP call ngoài DB |
| Hikari connectionTimeout | Giới hạn thời gian **chờ mượn** connection từ pool | Không phải thời hạn một transaction được giữ connection |

Đặt `@Transactional(timeout = 5)` không tự bảo đảm network call bị hủy sau năm giây. Mỗi tầng phải có timeout/deadline và hành vi cancellation được kiểm thử.

## 3. Spring Batch chunk transaction đặt ở đâu?

Với chunk-oriented step điển hình:

~~~java
return new StepBuilder("importStep", jobRepository)
        .<OrderRow, OrderResult>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Framework thực hiện chunk-oriented processing với **ranh giới transaction cho mỗi chunk**. Trong cấu hình mặc định phổ biến, đọc, xử lý, ghi và cập nhật checkpoint tương ứng diễn ra trong chu kỳ chunk transaction do `TaskletStep` điều phối. Vì vậy, một lệnh HTTP bên trong `ItemProcessor.process(...)` hoặc `ItemWriter.write(...)` thường đang nằm **trên đường thực thi của transaction chunk**.

~~~mermaid
flowchart TD
    B["BEGIN chunk transaction"] --> R["read() cho tối đa K item"]
    R --> P["process(item)"]
    P --> H{"Processor gọi HTTP?"}
    H -->|Có| N["Network call có thể block/timeout"]
    N --> W["write(Chunk)"]
    H -->|Không| W
    W --> C["Checkpoint / COMMIT"]
    C --> E["Tiếp tục chunk sau"]
    N -.-> X["Nếu lỗi: rollback, retry/skip theo policy"]
~~~

Sơ đồ chỉ mô tả hành vi chuẩn ở mức khái niệm; thứ tự callback và transaction participation có thể thay đổi với reader từ transactional queue, async processor, custom tasklet, nested transaction hay cách cấu hình tài nguyên. **Không lấy sơ đồ làm hợp đồng cho mọi extension của Spring Batch.**

### 3.1. Processor trông như một hàm thuần nhưng lại gọi mạng

~~~java
@Bean
public ItemProcessor<OrderRow, OrderResult> orderProcessor(
        PricingClient pricingClient) {

    // Không nên đưa trực tiếp HTTP vào chunk transaction
    // khi latency/retry không thể kiểm soát.
    return order -> {
        PriceInfo price = pricingClient.lookup(order.sku());
        return new OrderResult(order.id(), price.amount());
    };
}
~~~

Khi một chunk 200 items gọi HTTP 200 lần, nếu tuần tự và mỗi call trung bình 100 ms thì riêng thời gian chờ mạng đã khoảng **20 giây/chunk**, chưa kể đọc/ghi, retry và tail latency. Nếu transaction đang giữ DB resources, đây là transaction dài bất hợp lý cho workload batch có nhiều worker.

Ngay cả khi sử dụng HTTP client nonblocking, nếu pipeline **đợi kết quả trước commit chunk**, transaction vẫn có thể phải mở tới lúc hoàn tất network operation. Không suy luận “async API” đồng nghĩa transaction kết thúc sớm.

### 3.2. Tasklet không mặc nhiên nằm ngoài transaction

Một anti-pattern khác:

~~~java
return new StepBuilder("callApiStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            remoteClient.callExternalSystem();
            return RepeatStatus.FINISHED;
        }, transactionManager)
        .build();
~~~

Trong `TaskletStep` thông thường, `Tasklet.execute(...)` được gọi trong transaction do step quản lý. Đổi từ `ItemProcessor` sang tasklet **không tự tách HTTP call khỏi transaction**. Muốn network call hoàn toàn ngoài DB transaction, phải thiết kế **một ranh giới thực thi khác** hoặc cấu hình transaction có kiểm chứng; không chỉ chuyển class/method.

## 4. Không phải mọi resource có chung một transaction

Một JDBC transaction thường chỉ bảo đảm atomicity cho công việc trên datasource/transaction manager đó. HTTP server, Kafka broker, RabbitMQ, đối tác thanh toán và một database khác **không tự động** tham gia transaction này.

| Tác vụ | Trong cùng local JDBC transaction? | Cần thêm gì nếu phải chống lặp? |
| --- | --- | --- |
| `JdbcTemplate.update` cùng datasource/manager | Thông thường có, nếu tham gia đúng transaction | Unique key, SQL/lock đúng nghiệp vụ |
| JDBC ở datasource khác | Không mặc định | Phối hợp transaction hoặc eventual consistency |
| HTTP GET | Không | Snapshot/version, timeout và cache khi hợp lệ |
| HTTP POST tạo charge | Không | Idempotency key ở đích, reconciliation |
| Publish message tới broker | Không mặc định atomic với DB | Transactional outbox hoặc cơ chế phối hợp được kiểm chứng |
| Ghi file/object storage | Không tự rollback theo DB | Temporary/versioned object, commit marker, cleanup |
| Gửi email/SMS | Không | Dedupe key, outbox, audit trail |

**Đừng gọi một workflow nhiều hệ thống là “exactly once” chỉ vì phương thức Java có `@Transactional`.** Ngay cả khi dùng JTA/XA cho một số loại resource, API HTTP bên ngoài thường không hỗ trợ tham gia cùng global transaction; XA còn tăng độ phức tạp vận hành và không thay thế idempotency ở hệ thống đích.

## 5. Định lượng chi phí giữ transaction trong lúc chờ HTTP

Giả sử một worker xử lý một yêu cầu cần:

- 25 ms thao tác DB.
- 400 ms chờ HTTP.
- 16 yêu cầu đang xử lý đồng thời.
- Các yêu cầu đủ độc lập và downstream chưa nghẽn.

Nếu connection đã được giữ trước HTTP, thời gian chiếm dụng có thể khoảng:

\[
T_{\mathrm{hold}} \approx 25 + 400 = 425\ \text{ms}.
\]

Với 16 workers luôn bận, số connection đang bị giữ có thể xấp xỉ **16**. Throughput trần lý tưởng mỗi worker vào khoảng `1 / 0,425≈2,35` request/s, cả hệ thống khoảng **37,6 request/s** trước overhead.

Nếu tổ chức lại thành **DB transaction ngắn 25 ms** và **HTTP call 400 ms nằm ngoài transaction**, cùng throughput 37,6 request/s, số connection bận trung bình cho phần DB (ước tính theo Little's law) khoảng:

\[
L_{\mathrm{DB}}
\approx37,6\times0,025
\approx0,94\ \text{connection}.
\]

Đây là **ví dụ giả định** để thấy sự khác biệt giữa *worker in-flight* và *connection hold time*. Nó chưa tính nhiều transaction DB, queue waits, lock, peak bursts, connection pool implementation hoặc chi phí polling/claim. Kết quả thực có thể khác, nhưng nguyên lý vẫn rõ: **giảm thời gian giữ connection làm tăng khả năng tái sử dụng pool**.

### 5.1. Vì sao thread count không chữa được transaction dài?

Nếu tám workers đang giữ cả tám connection chờ HTTP, thêm 16 worker threads không tạo thêm DB capacity. Chúng có thể chờ `DataSource.getConnection()`, làm `Hikari pending` tăng và gây timeout. Tăng Hikari pool lên 32 đôi khi giảm wait tức thì nhưng có thể làm DB lock contention và tải online xấu hơn.

Tối ưu đúng là hỏi: **“Một transaction thực sự phải giữ lock/connection bao lâu để thực hiện phần DB của nó?”** trước khi tăng threads.

## 6. Các anti-pattern cần loại bỏ

### 6.1. @Transactional bao trùm I/O bên ngoài

~~~java
@Transactional
public void settlePayment(Order order) {
    markOrderProcessing(order.id());       // DB write
    paymentGateway.charge(order);          // HTTP side effect
    markOrderPaid(order.id());             // DB write
}
~~~

Nếu HTTP đã charge thành công nhưng `markOrderPaid` thất bại, database rollback **không hoàn tiền ở cổng thanh toán**. Sau khi retry, cùng order có thể bị charge hai lần. Đây vừa là **transaction dài**, vừa là **dual-write consistency problem**.

### 6.2. REQUIRES_NEW không tự chữa transaction dài

~~~java
@Transactional
public void process() {
    updateA();
    isolatedService.writeBInNewTransaction(); // REQUIRES_NEW
    remoteApi.call();                         // Outer transaction vẫn mở
}
~~~

`Propagation.REQUIRES_NEW` tạo transaction khác cho method được gọi, nhưng **outer transaction vẫn đang tồn tại**, có thể giữ resource/lock trong lúc chờ inner transaction và HTTP. Trong một số trường hợp, nó còn làm nhu cầu connection tăng vì inner transaction mượn connection khác.

Không dùng `REQUIRES_NEW` như một “nút tắt giữ transaction” khi outer method vẫn gọi mạng. Nó chỉ phù hợp với một mục tiêu transaction độc lập có phân tích hậu quả commit/rollback rõ ràng.

### 6.3. NOT_SUPPORTED chỉ suspend chứ không nhất thiết giải phóng

~~~java
@Transactional
public void outer() {
    writeBeforeNetwork();
    nonTransactionalHelper.callApi(); // @Transactional(NOT_SUPPORTED)
    writeAfterNetwork();
}
~~~

`NOT_SUPPORTED` có thể **suspend transaction hiện tại** trong lúc method helper chạy nếu được Spring proxy áp dụng đúng. Nhưng transaction outer chưa commit và các connection/lock đã cấp phát trước đó **không nhất thiết được nhả**; chúng có thể vẫn bị giữ trong thời gian suspend.

Đặc biệt, **self-invocation** (method trong cùng bean gọi nhau trực tiếp) có thể bỏ qua Spring AOP proxy, khiến annotation không có tác dụng mong đợi. Muốn bỏ HTTP khỏi transaction, thiết kế **transaction trước đã commit xong**, không chỉ suspend mà chưa kết thúc.

### 6.4. Retry không giới hạn ngay trong transaction

~~~java
// Anti-pattern khái niệm
while (true) {
    try {
        remoteClient.call();
        break;
    } catch (Exception e) {
        Thread.sleep(10_000L); // Có thể đang giữ transaction/connection
    }
}
~~~

Nếu mỗi retry đợi 10 giây trong khi transaction vẫn mở, connection hold time tăng theo số lần lỗi. Trong Spring Batch fault tolerance, retry/skip còn có rollback/replay semantics riêng; cần xác định retry ở **đúng lớp**, với budget hữu hạn và không giữ DB locks khi backoff.

### 6.5. Async không có nghĩa đã thoát transaction

~~~java
@Transactional
public void updateAndDispatch() {
    jdbc.update("UPDATE ...");
    CompletableFuture<?> future = client.callAsync();
    future.join(); // Vẫn đợi trước khi commit
}
~~~

`future.join()` nằm trong method transactional vẫn giữ đường thực thi chưa commit. Ngược lại, “fire-and-forget” rồi commit có thể dẫn tới **mất event** nếu process chết trước khi request được gửi bền vững. Giải pháp đúng cho tác vụ cần tin cậy thường là **outbox**, không phải chỉ bỏ `join()`.

## 7. Quy tắc thiết kế: tách transaction ngắn và network I/O

Một mô hình hữu ích cho xử lý dữ liệu phân tán là:

1. **Claim/reserve** một work item bằng transaction DB ngắn; commit và nhả lock.
2. **Gọi network** ở ngoài mọi DB transaction đã mở; có deadline và idempotency key khi cần.
3. **Persist response/status** bằng một transaction DB ngắn, kiểm tra worker còn sở hữu item.
4. Chạy bước xử lý/ghi chunk tiếp theo từ dữ liệu đã stage, hoặc publish event bằng outbox.
5. Retry/recover theo trạng thái bền vững, không dựa vào biến `boolean` trong heap JVM.

~~~mermaid
flowchart TD
    A[("Work table: PENDING")] --> B["BEGIN TX 1<br/>Claim + lease token"]
    B --> C["COMMIT TX 1"]
    C --> D["HTTP/gRPC call<br/>KHÔNG có DB transaction"]
    D --> E{"Response?"}
    E -->|Success| F["BEGIN TX 2<br/>Persist + check lease token"]
    F --> G["COMMIT TX 2<br/>READY"]
    E -->|Transient failure| H["BEGIN TX 3<br/>Schedule retry/backoff"]
    H --> I["COMMIT TX 3<br/>PENDING/RETRY"]
    E -->|Permanent failure| J["BEGIN TX 4<br/>Mark FAILED / review"]
    J --> K["COMMIT TX 4"]
    G --> L["Spring Batch đọc snapshot READY<br/>xử lý DB chunk ngắn"]
~~~

**Lưu ý:** một network call **nằm giữa hai transaction đã commit** không cho phép rollback đồng thời mọi tác dụng phụ của ba bước. Vì vậy thiết kế này có tính **eventual consistency** và phải có state machine, timeout/lease, idempotency, reconciliation cùng runbook.

### 7.1. Đặt API call ở đâu trong ứng dụng?

Có nhiều phương án, nhưng cần nói rõ ranh giới thực thi:

| Phương án | Transaction DB khi gọi HTTP | Khi nào phù hợp |
| --- | --- | --- |
| External enrichment worker/service độc lập | **Không**, nếu worker không mở @Transactional bao ngoài | Cần scale HTTP riêng và retry độc lập |
| Scheduled poller dùng claim transaction ngắn | **Không**, nếu poller không transactional và repository methods commit trước call | Queue công việc trong DB, volume vừa/đủ lớn |
| Hai job/phase: fetch/stage rồi batch transform | **Không** ở fetch service; batch sau chỉ đọc staged snapshot | Muốn snapshot, restart và audit rõ |
| Transactional outbox dispatcher | **Không** khi dispatcher publish/gọi bên ngoài sau khi commit outbox | Gửi message hoặc tạo external side effect đáng tin cậy |
| HTTP ngay trong ItemProcessor của chunk step mặc định | **Thường có** transaction chunk đang active | Dễ viết nhưng rủi ro khi call chậm |
| HTTP ngay trong TaskletStep thường gặp | **Thường có** transaction của tasklet | Không phải cách thoát transaction chỉ bằng đổi API |

Nếu muốn sử dụng Spring Batch cho orchestration tổng thể, có thể để một **job hoặc phase riêng** chuẩn bị dữ liệu mạng ở bên ngoài chunk transaction rồi phát tín hiệu dữ liệu sẵn sàng; **đừng mặc định mỗi tasklet của job đó không transactional**. Hợp đồng của adapter/worker phải được kiểm chứng bằng integration test.

## 8. Mô hình trạng thái durable cho một network-enrichment task

Ví dụ quy trình làm giàu dữ liệu khách hàng. DB table chứa input ID, trạng thái xử lý và kết quả từ API.

~~~sql
-- PostgreSQL, schema minh họa
CREATE TABLE enrichment_work (
    work_id        BIGINT PRIMARY KEY,
    customer_id    BIGINT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    lease_token    UUID,
    leased_until   TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    response_json  JSONB,
    source_version BIGINT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('PENDING','IN_PROGRESS','READY','FAILED'))
);

CREATE INDEX ix_enrichment_work_ready_to_claim
    ON enrichment_work(status, next_attempt_at, work_id);
~~~

Bảng này mô tả **công việc cần làm**, không phải output cuối của job Spring Batch. Với workload lớn cần cân nhắc index cho `leased_until`, partition table/retention và chi phí các update liên tục; schema chỉ để minh họa.

### 8.1. Bất biến trạng thái

~~~text
PENDING --[claim]--> IN_PROGRESS
IN_PROGRESS --[HTTP success + persisted]--> READY
IN_PROGRESS --[transient failure]--> PENDING (next_attempt_at tương lai)
IN_PROGRESS --[permanent failure]--> FAILED
IN_PROGRESS --[lease expires]--> eligible for re-claim
READY --> materialized immutable snapshot --> Spring Batch downstream
~~~

Các điều kiện cần giữ:

- Một work item chỉ có **một lease hợp lệ** tại một thời điểm theo database.
- Worker ghi kết quả chỉ khi `lease_token` còn khớp và lease chưa hết hạn.
- Sau crash, lease hết hạn cho phép worker khác re-claim.
- Không chấp nhận response của worker cũ ghi đè response mới.
- Retry budget hữu hạn; nếu lỗi cố định, đánh dấu FAILED và báo vận hành.
- Một khi tạo snapshot đầu vào cho bước Batch downstream, snapshot phải bất biến.

**Lease token không thay thế idempotency của external API.** Worker có lease cũ bị chậm vẫn có thể tạo một HTTP side effect trước khi kết quả DB bị fencing; external service phải tự nhận diện request lặp hoặc hỗ trợ idempotency key.

## 9. Java: claim ngắn, HTTP ngoài transaction, persist ngắn

Ví dụ minh họa dùng Spring Framework/Spring Boot 3.x, Java 17+, PostgreSQL và Spring Batch 5.2.x cho bước xử lý về sau. Đoạn này cố ý đặt network worker **ngoài một chunk/tasklet transaction của Spring Batch**. Nó là một service/poller độc lập có thể được scheduler chạy, sau đó Spring Batch xử lý snapshot READY.

### 9.1. Record đại diện và repository

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

public record ClaimedWork(
        long workId, long customerId, UUID leaseToken) {}

@Repository
public class EnrichmentClaimRepository {

    private final JdbcTemplate jdbc;

    public EnrichmentClaimRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<ClaimedWork> claimOne() {
        UUID token = UUID.randomUUID();

        List<ClaimedWork> rows = jdbc.query("""
            WITH candidate AS (
                SELECT work_id
                FROM enrichment_work
                WHERE (status = 'PENDING' AND next_attempt_at <= now())
                   OR (status = 'IN_PROGRESS' AND leased_until < now())
                ORDER BY work_id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE enrichment_work AS w
            SET status = 'IN_PROGRESS',
                lease_token = ?,
                leased_until = now() + INTERVAL '90 seconds',
                attempt_count = attempt_count + 1,
                updated_at = now()
            FROM candidate
            WHERE w.work_id = candidate.work_id
            RETURNING w.work_id, w.customer_id, w.lease_token
            """,
            (rs, rowNum) -> new ClaimedWork(
                    rs.getLong("work_id"),
                    rs.getLong("customer_id"),
                    rs.getObject("lease_token", UUID.class)),
            token);

        return rows.stream().findFirst();
    }

    @Transactional
    public boolean markReady(
            ClaimedWork work, String json, long sourceVersion) {

        int updated = jdbc.update("""
            UPDATE enrichment_work
            SET status = 'READY',
                response_json = CAST(? AS jsonb),
                source_version = ?,
                lease_token = NULL,
                leased_until = NULL,
                updated_at = now()
            WHERE work_id = ?
              AND status = 'IN_PROGRESS'
              AND lease_token = ?
              AND leased_until > now()
            """,
            json, sourceVersion, work.workId(), work.leaseToken());

        return updated == 1;
    }

    @Transactional
    public void scheduleRetry(ClaimedWork work) {
        jdbc.update("""
            UPDATE enrichment_work
            SET status = CASE
                    WHEN attempt_count >= 5 THEN 'FAILED'
                    ELSE 'PENDING'
                END,
                next_attempt_at = now() + INTERVAL '30 seconds',
                lease_token = NULL,
                leased_until = NULL,
                updated_at = now()
            WHERE work_id = ?
              AND status = 'IN_PROGRESS'
              AND lease_token = ?
            """,
            work.workId(), work.leaseToken());
    }
}
~~~

**Ý nghĩa chính của code:**

- `claimOne()` dùng transaction ngắn với PostgreSQL `FOR UPDATE SKIP LOCKED` để tránh nhiều poller claim cùng row đang bị khóa.
- Transaction commit khi repository method kết thúc **nếu được gọi qua Spring proxy và không có outer transaction**.
- `lease_token` là một UUID mới cho lần claim; kết quả cũ chỉ có thể ghi khi token còn hợp lệ.
- `markReady` đòi token khớp và `leased_until > now()`; worker cũ trễ bị từ chối ghi.
- `scheduleRetry` giới hạn attempt count theo minh họa; với production, lưu error category, retry-after của API, exponential backoff và jitter thay vì luôn 30 giây.
- Dùng thời gian database `now()` tránh phụ thuộc đồng hồ JVM khác nhau.
- Nếu crash sau claim, `leased_until` cho phép re-claim item.
- Index/độ công bằng của `ORDER BY work_id` cần được đo; nếu item đầu hàng đợi thường lỗi, cân nhắc retry scheduling/priority có giới hạn.

Đây là **khung triển khai**, không phải thư viện đầy đủ: cần xử lý HTTP error cụ thể, telemetry, transaction manager đúng datasource, validation JSON và chính sách stale lease. Với workload hàng triệu row, query claim phải được benchmark ở mức concurrent pollers thực tế.

### 9.2. Poller không transactional

~~~java
import java.util.Optional;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public class EnrichmentPoller {

    private final EnrichmentClaimRepository claims;
    private final CustomerApiClient client;

    public EnrichmentPoller(
            EnrichmentClaimRepository claims,
            CustomerApiClient client) {
        this.claims = claims;
        this.client = client;
    }

    // KHÔNG @Transactional ở class/method này.
    // Không gọi từ một TaskletStep đang giữ outer transaction.
    @Scheduled(fixedDelayString = "${enrichment.poll.delay-ms:500}")
    public void processOne() {
        Optional<ClaimedWork> candidate = claims.claimOne();
        if (candidate.isEmpty()) {
            return;
        }

        ClaimedWork work = candidate.get();
        try {
            // Claim transaction đã COMMIT trước khi vào đây.
            // Client phải có connect/read/overall deadline hữu hạn.
            CustomerResponse response = client.fetch(
                    work.customerId(), "enrichment-" + work.workId());

            boolean persisted = claims.markReady(
                    work, response.json(), response.sourceVersion());

            if (!persisted) {
                // Lease hết hạn hoặc worker khác đã re-claim.
                // Không ghi đè response mới; ghi metric và đối soát.
                reportLostOwnership(work.workId());
            }
        } catch (TransientCustomerApiException e) {
            claims.scheduleRetry(work);
        } catch (PermanentCustomerApiException e) {
            // Production: có markFailed(work, error) với fencing.
            recordPermanentFailure(work, e);
        }
    }

    private void reportLostOwnership(long workId) {
        // Metrics/logger theo workId (không log PII).
    }

    private void recordPermanentFailure(
            ClaimedWork work, Exception exception) {
        // Code minh họa: triển khai trạng thái FAILED có lease fencing.
        // Không để item sống mãi trong IN_PROGRESS vì bắt lỗi bị nuốt.
        claims.scheduleRetry(work);
    }
}
~~~

`CustomerApiClient`, `CustomerResponse` và các exception là giao diện/kiểu do ứng dụng cung cấp; cần thêm `@EnableScheduling` hoặc scheduler tương ứng. Đoạn ví dụ là **mẫu luồng transaction**, không phải ứng dụng có thể copy chạy ngay.

**Điểm quan trọng nhất:** call `client.fetch(...)` nằm **giữa hai lời gọi repository method đã commit**, và `EnrichmentPoller` không bị một outer `@Transactional` bao quanh. Nếu bạn nhúng poller này vào `TaskletStep.execute(...)` của một step có transaction đang active, lời gọi `claims.claimOne()` có thể tham gia outer transaction, khiến thiết kế bị phá hỏng. Cần thử bằng transaction instrumentation thực, không chỉ xem annotation trên poller.

### 9.3. Giới hạn của lease và fencing

Lease 90 giây chỉ phù hợp khi tổng network deadline và retry budget **ngắn hơn khoảng đó** với headroom; nếu call có thể mất vài phút, cần lease dài hơn hoặc heartbeat được thực hiện bằng transaction ngắn, có kiểm soát.

Fencing trong `markReady` ngăn worker cũ ghi vào **enrichment_work**; nhưng nếu client đang thực hiện **HTTP POST tạo side effect**, token DB không thể ngăn một yêu cầu cũ đã tới đối tác. Khi đó cần gửi **business idempotency key ổn định** được đối tác hỗ trợ, ví dụ `enrichment:<work_id>:<operation_version>`, và kiểm chứng contract phía đối tác.

Nếu API chỉ là read-only GET, retry thường an toàn hơn nhưng vẫn phải chú ý **phiên bản dữ liệu**: hai lần GET có thể trả dữ liệu khác nhau. Hãy ghi `sourceVersion`/ETag hoặc snapshot/cutoff và định nghĩa cách dùng response khi dữ liệu thay đổi.

### 9.4. Vì sao @Transactional trên repository vẫn hợp lý?

Không phải bài học yêu cầu **không dùng transaction**. Mục tiêu là **dùng transaction rất ngắn ở thao tác cần nguyên tử**:

~~~text
TX claim:
  SELECT/UPDATE claim dưới lock -> COMMIT

No DB TX:
  gọi API + backoff/retry (có deadline)

TX persist:
  UPDATE kết quả nếu đúng ownership -> COMMIT
~~~

Cần chọn concurrency sao cho DB transactions của claim/persist vẫn đủ throughput, và tách giới hạn API calls khỏi số connection DB. Đây là cách giảm chi phí lock/connection mà vẫn giữ được state bền vững.

## 10. Đưa kết quả network vào Spring Batch chunk step an toàn

Sau khi dữ liệu đã được fetch, có thể đưa vào một **immutable ready snapshot** mà Spring Batch đọc và xử lý bằng những transaction ngắn, không gọi HTTP trong chunk.

Một cách minh họa:

~~~sql
CREATE TABLE ready_enrichment_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    work_id BIGINT NOT NULL,
    response_json JSONB NOT NULL,
    source_version BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, work_id)
);

CREATE TABLE normalized_enrichment (
    work_id BIGINT PRIMARY KEY,
    response_json JSONB NOT NULL,
    source_version BIGINT NOT NULL
);
~~~

Trước khi bắt đầu job, một phase điều phối phải:

1. Xác nhận **mọi work item thuộc cutoff** đã `READY`, hoặc có chính sách loại trừ lỗi rõ.
2. Đóng băng `snapshotId` cùng danh sách work IDs/source versions.
3. Materialize dữ liệu vào `ready_enrichment_snapshot` và bảo đảm không bị sửa trong lúc job đọc/restart.
4. Chỉ sau khi bước trên hoàn tất mới khởi chạy `JobInstance` với identifying `snapshotId`.

Không nên dùng paging reader query trên một bảng vừa được job cập nhật trạng thái làm thay đổi điều kiện lọc mà không có kế hoạch: khi offset paging trên tập `WHERE status='READY'` đang co lại, có thể **bỏ qua item**. Tách snapshot immutable làm checkpoint và reader deterministic dễ hơn.

### 10.1. Ví dụ StepBuilder với reader dữ liệu đã stage

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

public record ReadyEnrichment(
        long workId, String responseJson, long sourceVersion) {}

@Bean
@StepScope
public JdbcCursorItemReader<ReadyEnrichment> readyReader(
        DataSource dataSource,
        @Value("#{jobParameters['snapshotId']}") String snapshotId) {

    return new JdbcCursorItemReaderBuilder<ReadyEnrichment>()
            .name("readyReader")
            .dataSource(dataSource)
            .sql("""
                SELECT work_id, response_json, source_version
                FROM ready_enrichment_snapshot
                WHERE snapshot_id = ?
                ORDER BY work_id
                """)
            .preparedStatementSetter(ps -> ps.setString(1, snapshotId))
            .rowMapper((rs, rowNum) -> new ReadyEnrichment(
                    rs.getLong("work_id"),
                    rs.getString("response_json"),
                    rs.getLong("source_version")))
            .fetchSize(500)
            .saveState(true)
            .build();
}

@Bean
public JdbcBatchItemWriter<ReadyEnrichment> readyWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ReadyEnrichment>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO normalized_enrichment(
                    work_id, response_json, source_version)
                VALUES (:workId, CAST(:responseJson AS jsonb), :sourceVersion)
                ON CONFLICT (work_id)
                DO UPDATE SET
                    response_json = EXCLUDED.response_json,
                    source_version = EXCLUDED.source_version
                WHERE normalized_enrichment.source_version
                        < EXCLUDED.source_version
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("workId", item.workId())
                            .addValue("responseJson", item.responseJson())
                            .addValue("sourceVersion", item.sourceVersion()))
            .assertUpdates(false)
            .build();
}

@Bean
public Step normalizeReadyStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<ReadyEnrichment> readyReader,
        JdbcBatchItemWriter<ReadyEnrichment> readyWriter) {

    return new StepBuilder("normalizeReadyStep", jobRepository)
            .<ReadyEnrichment, ReadyEnrichment>chunk(500, transactionManager)
            .reader(readyReader)
            .writer(readyWriter)
            .build();
}
~~~

**Lưu ý kỹ thuật:**

- Reader chỉ đọc `ready_enrichment_snapshot`, không gọi HTTP trong `read()`/`process()`/`write()`.
- `chunk(500, transactionManager)` tạo ranh giới transaction ngắn cho JDBC operations của worker step.
- `@StepScope` late-bind `snapshotId` của JobInstance; snapshot phải immutable khi restart.
- Writer dùng PostgreSQL upsert theo version; `assertUpdates(false)` quan trọng vì lệnh upsert có điều kiện có thể ảnh hưởng **0 rows** khi replay cùng/phiên bản cũ. Nếu giữ mặc định assert update count, một item đã đúng có thể bị báo writer error.
- Các bean `JobRepository`, `DataSource`, transaction manager và cấu hình Boot/Spring Batch infrastructure không nằm trong snippet; cần kiểm tra datasource dùng trong writer và transaction manager tương thích.
- Ví dụ dùng JSON string; production cần schema validation và quy tắc source-version conflict, đặc biệt khi cùng version có payload khác nhau.
- Đây là ví dụ **một phase sau external enrichment**, không phải cách để gọi API ngay trong chunk mà giữ transaction ngắn.

### 10.2. Nếu không thể materialize toàn bộ snapshot?

Có thể tổ chức các batch window nhỏ theo `snapshotId`/time partition, hoặc stage từng shard bất biến rồi launch worker step cho shard hoàn tất. Khi nhiều StepExecutions chạy đồng thời, cần:

- Manifest/ID range không chồng lấn và ổn định.
- Checkpoint riêng theo partition.
- Không đưa item `IN_PROGRESS` vào reader khi external response chưa bền vững.
- Writer idempotent, DB/API quota tính trên toàn worker cluster.
- Có cơ chế đối soát cuối cùng trước khi công bố “đợt xử lý hoàn tất”.

Nếu cần streaming liên tục thay vì snapshot batch, event-driven pipeline có outbox/inbox hoặc message transport phù hợp có thể hợp lý hơn một chunk step chờ HTTP ở trong transaction.

## 11. Transactional outbox: publish sau commit nhưng không mất event

Một biến thể thường gặp là sau khi xử lý chunk DB, job cần **gửi message** để dịch vụ khác làm việc. Mẫu sai:

~~~java
@Transactional
public void writeAndPublish(Order order) {
    jdbc.update("UPDATE orders ...");
    kafkaTemplate.send("orders-ready", order); // gửi khi DB chưa commit
}
~~~

Nếu message đã tới consumer mà DB transaction sau đó rollback, downstream thấy một sự kiện của trạng thái chưa tồn tại. Nếu commit DB thành công nhưng process chết trước khi gửi message, downstream có thể **không bao giờ được thông báo**.

**Transactional outbox** giải bài toán dual write bằng cách ghi **business state + outbox event trong một DB transaction**:

~~~sql
-- Cùng transaction database với thay đổi nghiệp vụ:
BEGIN;

UPDATE orders
SET status = 'READY'
WHERE order_id = :orderId;

INSERT INTO outbox_event(
    event_id, aggregate_id, event_type, payload, status)
VALUES (
    :eventId, :orderId, 'ORDER_READY',
    CAST(:payload AS jsonb), 'NEW'
);

COMMIT;
~~~

Sau commit, một **dispatcher độc lập** lấy outbox rows và publish tới broker/API ở **ngoài transaction DB đã commit**. Dispatcher cập nhật trạng thái đã gửi bằng transaction ngắn, có retry. Nếu publish thành công nhưng dispatcher crash trước khi đánh dấu sent, event có thể được phát lại.

~~~mermaid
sequenceDiagram
    participant B as Spring Batch Writer
    participant D as Database
    participant X as Outbox Dispatcher
    participant Q as Broker / External API
    B->>D: BEGIN
    B->>D: UPDATE business state
    B->>D: INSERT outbox event
    B->>D: COMMIT
    X->>D: Claim outbox event, COMMIT
    X->>Q: Publish / network call (no DB TX)
    Q-->>X: Confirm / response
    X->>D: Mark SENT in short TX
    Note over X,Q: Publish có thể lặp khi crash sau gửi trước khi mark SENT
~~~

**Outbox không tự bảo đảm exactly-once delivery.** Nó giúp tránh **mất sự kiện do khoảng lỗi giữa DB commit và publish**, khi được triển khai đúng; consumer cần **inbox/deduplication bằng event ID** hoặc idempotency theo business key. Với HTTP đối tác có side effect, phải có idempotency key do đối tác chấp nhận.

### 11.1. Inbox/dedup ở phía nhận

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(consumer_name, message_id)
);
~~~

Khi nhận message, consumer cố gắng insert khóa dedupe và thực hiện business DB writes **trong cùng transaction**. Nếu khóa đã tồn tại, có thể ACK response thành công mà không nhân đôi effect. Nếu handler gọi API khác, phải phối hợp thêm idempotency/outbox ở tầng tiếp theo.

Đừng đặt bản ghi `processed_message` **trong một transaction khác** với DB effect cần bảo vệ, vì crash ở giữa sẽ tạo trạng thái “đã xử lý” nhưng thực tế chưa ghi, hoặc ngược lại.

## 12. Remote chunking và remote partitioning có tự giải quyết vấn đề này không?

Không. Chuyển processor/writer sang JVM khác có thể tăng tổng throughput và phân phối workload, nhưng **worker vẫn có transaction của chunk/step**.

### 12.1. Remote chunking

Manager đọc items và gửi `ChunkRequest` qua middleware. Worker nhận chunk, xử lý/ghi và trả `ChunkResponse`. Nếu worker `ItemProcessor` gọi API trong transaction/handler scope đang quản lý DB work, vấn đề transaction dài vẫn tồn tại ở worker.

Ngoài ra còn có lỗi phân tán:

- Worker commit DB nhưng reply mất.
- Broker redeliver một request.
- Manager timeout trong khi worker vẫn chạy.
- DB writer xử lý lại một chunk sau worker crash.

Chống lặp bằng business idempotency và correlation, không mặc định coi broker ACK là “exactly once”. Tách việc làm giàu qua API ra khỏi transaction DB vẫn có ích, nhưng phải có staging, durable work state hoặc outbox phù hợp.

### 12.2. Remote partitioning

Manager phân vùng input thành các worker `StepExecution`; mỗi remote worker **tự đọc** shard, xử lý và ghi. Partition có `ExecutionContext` riêng giúp restart theo shard, nhưng một HTTP call trong worker chunk vẫn có thể kéo dài transaction của shard.

Nếu tách enrichment phase, worker có thể đọc một manifest đã được làm giàu sẵn hoặc chỉ xử lý các record `READY`, thay vì giữ một JDBC transaction mở khi gọi mạng. Cần kiểm soát snapshot và worker generations khi restart, không để hai worker xử lý cùng partition nếu manager mất liên lạc.

### 12.3. Parallel steps cũng cần ranh giới

Có thể có một flow riêng làm remote enrichment và một flow ghi DB. **Chạy song song** không tự cung cấp thứ tự phụ thuộc: step ghi DB phải nhận dữ liệu **đã commit/stage** từ enrichment step và có cơ chế bảo đảm khi nào nó được phép chạy. Nếu dependent steps phải chạy sau nhau, định nghĩa đúng luồng job và điều kiện hoàn tất.

## 13. HTTP timeout, retry và rate limit: phải đặt ngoài transaction

Một chiến lược network call lành mạnh có các thành phần:

- **Connect timeout** phù hợp với mạng/deployment.
- **Response deadline** hữu hạn, tính cả retry/redirect theo client.
- **Retry chỉ cho lỗi được phân loại transient** (timeout, 429, 503, một số 5xx).
- **Exponential backoff với jitter**, không retry liên tục đồng bộ theo giờ.
- **Retry budget** theo item/job, tránh retry storm kéo dài quá SLA.
- **Rate limiting/bulkhead** để không vượt quota đối tác.
- **Circuit breaker** khi upstream/downstream có sự cố, nếu phù hợp.
- **Business idempotency key** nếu request tạo hiệu ứng bên ngoài.
- **Distributed tracing** để tìm callback mất hoặc response chậm.
- **Durable state** để retry tiếp sau khi JVM/pod restart.

### 13.1. Không phải HTTP method nào cũng retry như nhau

| Loại request | Ví dụ | Hướng xử lý retry |
| --- | --- | --- |
| GET tra cứu versioned snapshot | Đọc tỷ giá từ snapshot xác định | Có thể retry nếu thời điểm/version rõ và không tạo side effect |
| GET dữ liệu sống | Lấy mức giá “hiện tại” | Retry có thể trả version khác; cần quy tắc cutoff/ETag |
| POST tạo charge | Trừ tiền khách hàng | Chỉ retry an toàn khi đối tác hỗ trợ idempotency key hoặc có cơ chế đối soát |
| POST gửi email | Tạo email gửi đi | Dedupe key ở email system/outbox |
| PUT idempotent theo tài nguyên | Ghi lại trạng thái xác định theo version | Cần kiểm tra idempotency contract và optimistic locking |
| API trả 429 | Rate limit | Dùng Retry-After nếu có, rate limit và backoff |
| API trả 400/schema error | Lỗi dữ liệu cố định | Không retry vô hạn; chuyển FAILED/manual review |

Không suy luận “GET luôn an toàn về business semantics” khi dữ liệu nguồn không versioned hoặc server có side effects ngoài chuẩn HTTP. Tương tự, tên phương thức `POST` không tự chứng minh hệ thống đích có hoặc không có idempotency; phải đọc contract thực.

### 13.2. Timeout không chứng minh bên kia chưa xử lý

Một request có thể timeout sau khi remote server đã nhận và xử lý thành công nhưng phản hồi bị mất. Retry cùng request **không được tạo thêm charge/order/email**. Với API có idempotency, dùng khóa ổn định cho cùng operation qua mọi lần thử. Không tạo UUID mới cho mỗi retry rồi gọi đó là cùng một operation.

Nếu đối tác không hỗ trợ idempotency, cần xây cơ chế **query transaction status** hoặc reconciliation trước khi quyết định retry một side effect không thể đảo ngược.

## 14. Quản lý concurrency và network latency mà không làm nghẽn JDBC pool

Giả sử job cần xử lý một triệu item trong một giờ. Mục tiêu throughput trong thời gian xử lý:

\[
R=\frac{1.000.000}{3600}
\approx278\ \text{item/s}.
\]

Nếu mỗi item cần một HTTP request trung bình 0,4 giây, Little's law cho mức in-flight trung bình tại API:

\[
L_{\mathrm{API}}\approx278\times0,4\approx111,2.
\]

Nếu đối tác chỉ cho phép tối đa **20 in-flight requests**, mục tiêu 278 item/s **không khả thi** khi một request/item mất 0,4 giây theo giả định và quota giữ nguyên. Thêm JVM hay JDBC connections không sửa giới hạn API này.

Những lựa chọn có thể xem xét:

1. API batch request nhiều item/lần nếu đối tác hỗ trợ.
2. Caching/version reuse khi cùng key và nghiệp vụ cho phép.
3. Giảm latency bằng data locality, connection reuse hoặc tối ưu endpoint.
4. Xin quota cao hơn có giới hạn rõ.
5. Tách nhiệm vụ thành nhiều cửa sổ xử lý hoặc điều chỉnh SLA.
6. Giảm số item phải gọi API bằng lọc/dedupe hợp lệ.

Đừng dùng nhiều thread trong transaction để che API latency khi Hikari pool đang cạn. Tách transaction giúp giải phóng DB capacity, nhưng throughput vẫn bị **min của reader, API, broker, workers và writer**.

### 14.1. Tách pool và budget

| Pool/giới hạn | Theo dõi | Thiết kế |
| --- | --- | --- |
| HTTP client in-flight | Active requests, p95/p99 latency, 429 | Semaphore/rate limiter và deadline |
| JDBC/HikariCP | Active/idle/pending, connection acquire time | Transaction ngắn, connection budget |
| Worker executor | ActiveCount, queue depth, rejected tasks | Bounded concurrency và backpressure |
| Broker consumers | Ready/unacked, redelivery, DLQ | ACK/commit/replay policy |
| Database | Locks, deadlocks, WAL/redo, IOPS | SQL/index/transaction tối ưu |
| Spring Batch | Chunk duration, read/write/commit/rollback counts | Checkpoint/restart đúng |
| JVM | CPU, heap, thread stack, GC | Không tạo quá nhiều runnable/blocking threads |

Tổng cấu hình JDBC pool trên **mọi worker pods và manager** phải nằm trong ngân sách database sau khi tính online workload, không chỉ xem một pod.

### 14.2. Không giữ một JDBC transaction để “chờ có chỗ ở queue”

Một cách dễ gây áp lực là mở transaction, update status rồi block trên việc enqueue message khi broker chậm. Nếu có thể, lưu outbox event trong DB transaction ngắn, commit, rồi dispatcher xử lý broker retries ngoài transaction. Khi cần update trạng thái queue, dùng transaction ngắn kèm lease.

## 15. Đo chỉ số nào để biết transaction đã thực sự ngắn?

Đừng chỉ nhìn latency của HTTP. Cần tách các khoảng thời gian:

~~~text
T_claim_TX        = thời gian transaction claim DB
T_http            = thời gian network call + retry/backoff
T_persist_TX      = thời gian transaction ghi response
T_chunk_TX        = thời gian chunk transaction DB của Spring Batch
T_connection_hold = thời gian connection thực sự bị mượn/giữ
T_lock_wait       = thời gian chờ lock
T_pool_wait       = thời gian chờ mượn JDBC connection
T_end_to_end      = tổng thời gian từ PENDING tới output hợp lệ
~~~

**Mục tiêu:** `T_http` có thể dài do network, nhưng `T_claim_TX` và `T_persist_TX` không phải kéo dài theo `T_http`. Nếu Hikari connection hold p99 vẫn gần HTTP p99, rất có thể transaction hoặc resource lifetime chưa được tách như dự kiến.

### 15.1. Bộ metric tối thiểu

| Nhóm | Metric | Dùng để phát hiện |
| --- | --- | --- |
| Transaction | p50/p95/p99 duration, rollback rate, lock wait | Transaction dài và contention |
| HikariCP | active, pending, acquire latency, timeout count | Pool exhaustion |
| HTTP | success/timeout/429/5xx, deadline, retries, in-flight | Upstream bottleneck/retry storm |
| Work state | PENDING age, IN_PROGRESS lease age, READY rate, FAILED count | Stuck work/recovery lag |
| Spring Batch | StepExecution, read/write/commit/rollback/skip counts | Tiến độ đã commit và restart |
| Worker | concurrent calls, claim rate, stale lease rejections | Oversubscription/ownership |
| Outbox | NEW/SENT age, publish failures, duplicate rate | Message dispatch lag |
| Data correctness | unique business IDs, source version, aggregate totals | Mất/nhân đôi dữ liệu |
| SLA | estimated completion, recovery headroom | Nguy cơ trễ deadline |

Metrics tên cụ thể phụ thuộc Spring Boot, Micrometer, JDBC driver, HikariCP và instrumentation đã bật; không giả định mọi metric có sẵn. Trace có thể gắn `jobExecutionId`, `stepExecutionId`, `workId`, lease ID (cẩn trọng cardinality) và partner request ID; **không log PII hoặc payload nhạy cảm**.

### 15.2. Quan sát connection hold khác transaction duration

Một transaction logic dài có thể không mượn connection ngay lập tức nhờ lazy acquisition; ngược lại một JDBC cursor connection có thể được mở trong thời gian dài theo hợp đồng reader. Vì vậy cần đo:

- Transaction begin/commit trong instrumentation của Spring.
- JDBC connection acquire/release bằng datasource metrics/proxy khi hợp lệ.
- SQL/lock duration từ database.
- HTTP timing từ client và distributed trace.

Khi các thời điểm không khớp, tìm hiểu đúng implementation thay vì quy kết ngay “@Transactional giữ connection mọi lúc”.

## 16. Kiểm thử lỗi ở từng cửa sổ transaction/network

Chuẩn bị một snapshot có 50.000 work items, môi trường PostgreSQL thật, một fake HTTP service có thể điều khiển latency/status và nhiều worker JVM hoặc threads có giới hạn.

| Kịch bản | Cách mô phỏng | Bất biến cần đạt |
| --- | --- | --- |
| HTTP chậm p99 | Một số request chậm 10 giây | DB transaction hold không kéo dài tương ứng HTTP |
| API timeout trước side effect | Ngắt kết nối trước khi server thực hiện | Retry có giới hạn, không mất work |
| API timeout sau side effect | Server thành công nhưng làm mất response | Retry với stable idempotency key không tạo charge/email thứ hai |
| Worker crash sau claim | Kill trước khi call HTTP | Lease hết hạn, work được claim lại |
| Worker crash trong network call | Kill process đang chờ | DB không giữ lock/transaction mở qua mạng |
| Worker crash sau API success | Kill trước khi `markReady` | Claim/replay được khôi phục, remote effect không lặp |
| Worker crash sau persist | Kill sau `markReady` commit | READY không bị xử lý lại sai nghiệp vụ |
| Lease timeout | Giữ worker A chậm, worker B re-claim | A không ghi đè B qua lease fencing |
| DB pool cạn | Hạ pool size, tăng workers | Backpressure/alert, không retry storm |
| 429/503 | Fake API rate limit hoặc fail tạm | Backoff/jitter, max attempts, DLQ/FAILED |
| 400/schema error | Response không hợp lệ | Mark FAILED/manual review, không retry vô hạn |
| Snapshot drift | Đổi dữ liệu giữa hai JobExecutions | Ngăn resume sai hoặc yêu cầu reprocess |
| Batch chunk rollback | Gây lỗi writer trước commit | Idempotent DB write, checkpoint đúng |
| Duplicate broker message | Publish lại cùng outbox event | Inbox/dedupe không tạo effect trùng |
| Concurrent jobs | Chạy hai job cùng thời điểm | Tổng DB/API pool budget không vượt SLA |
| Process kill/restart | Kill manager/worker rồi restart JobInstance | Output cuối bằng clean run, không missing/duplicate |

### 16.1. Đo thời gian giữ DB connection khi HTTP bị chậm

Một integration test giá trị cao:

1. Thiết lập Hikari pool nhỏ, ví dụ max 4 trong môi trường kiểm thử.
2. Cho fake HTTP service chặn phản hồi trong 5 giây.
3. Chạy nhiều worker theo **mẫu anti-pattern** trong một test môi trường cô lập; đo active connections và lock.
4. Chạy lại cùng workload bằng mô hình **claim transaction ngắn → HTTP → persist transaction ngắn**.
5. So p99 connection hold, Hikari pending, DB lock waits và output correctness.
6. Inject crash giữa các bước và kiểm tra lease/idempotency/restart.

Không cần dùng một batch lớn để kiểm chứng nguyên lý; nhưng kiểm thử nghiệm thu production phải lặp lại trên volume, latency distribution và hạ tầng thực tế.

### 16.2. Bất biến nghiệm thu

~~~text
Every expected work item reaches READY or an explicitly handled FAILED state.
No item is silently lost because a worker crashed after claim.
Lease fencing rejects stale worker writes to the DB.
External side effect is idempotent or reconciled before replay.
No long DB transaction spans the HTTP request lifecycle.
Batch output business keys and source versions match approved snapshot.
Final output after crash/restart == output after a clean run.
End-to-end SLA includes retry, validation, publish and recovery buffer.
~~~

`BatchStatus.COMPLETED` không thay thế đối soát. Có thể có hai item thiếu và hai item trùng nhưng `writeCount` vẫn bằng kỳ vọng; so unique keys, version, totals/checksum và audit trail.

## 17. Xử lý một số tình huống thực tế

### 17.1. Không thể bỏ HTTP ra khỏi bước xử lý hiện tại ngay

Nếu hệ thống cũ có nhiều processor call HTTP bên trong chunk và không thể đổi kiến trúc ngay:

- Đo current transaction hold time và HTTP p99.
- Đặt hard timeout và retry budget, không chờ vô hạn.
- Giảm worker concurrency nếu DB locks/Hikari pending đã bão hòa.
- Chỉ retry những HTTP actions an toàn/idempotent.
- Cân nhắc tách từng API call có độ trễ lớn sang prefetch/staging phase trước.
- Đừng kết luận `@Transactional(NOT_SUPPORTED)` bên trong processor đã khắc phục toàn bộ transaction long-lived.
- Có backlog/migration plan rõ, không “sửa performance” bằng tăng JDBC pool vô hạn.

Đây là các biện pháp giảm thiểu trong giai đoạn chuyển đổi, **không phải thay thế** cho ranh giới transaction được thiết kế đúng.

### 17.2. Phải ghi DB trước khi gọi đối tác

Một số nghiệp vụ yêu cầu phải có record trạng thái `PENDING_EXTERNAL` trước khi gọi API:

~~~text
TX 1:
  INSERT business request(status=PENDING_EXTERNAL, operation_key)
  COMMIT

Network:
  gọi đối tác với operation_key làm idempotency key
  không mở DB transaction

TX 2:
  UPDATE business request(status=SUCCESS/FAILED, response_version)
  COMMIT
~~~

Đây là **state machine bền vững**, không phải transaction nguyên tử bao cả request từ đầu đến cuối. Nếu crash giữa TX1 và TX2, công việc pending được reclaimer phát hiện và khôi phục, còn operation key ngăn phía đối tác tạo tác dụng phụ lặp.

### 17.3. DB writer cần gọi một API xác nhận sau commit

Không gọi API xác nhận trong `ItemWriter.write(...)` với kỳ vọng transaction DB đã commit; trong chunk-oriented step writer thường chạy **trước commit**. Thay vào đó:

- Ghi business state + outbox event trong cùng writer transaction.
- Dispatcher gửi xác nhận sau commit.
- Consumer/đối tác dedupe theo event ID.
- Retry event chưa gửi, không rollback và chạy lại toàn bộ DB chunk vì lỗi mạng sau commit.

### 17.4. Kết quả API có thời hạn ngắn

Nếu quotation hoặc token hết hạn trong vài giây, prefetch toàn bộ dataset rồi mới ghi có thể làm response hết hạn. Có thể dùng **micro-batches/snapshot windows nhỏ**: fetch nhóm nhỏ ngoài transaction, persist version/expiry trong transaction ngắn, sau đó xử lý/commit ngay một nhóm đã sẵn sàng. Cần định nghĩa tính hợp lệ tại **thời điểm commit nghiệp vụ**, và retry khi expired, không dùng response stale.

### 17.5. API chỉ cho đúng một lần gọi

Nếu phía đối tác không hỗ trợ idempotency và hành động không thể đảo ngược, “exactly once” bằng retry là mục tiêu không thể tự chứng minh chỉ với DB transaction cục bộ. Cần giao thức tra trạng thái, callback có ID ổn định, manual reconciliation hoặc hợp đồng đối tác thay đổi. Không âm thầm retry charge chỉ vì nhận HTTP timeout.

## 18. Runbook khi Hikari pool nghẽn và job trễ SLA

Khi thấy `Hikari pending` tăng và batch chậm, thực hiện theo thứ tự:

1. Xác nhận **có bao nhiêu JobExecution, StepExecution và worker pods** đang chạy đồng thời.
2. Đo Hikari active/idle/pending, connection acquire p95/p99, lock waits và query duration.
3. So trace giữa transaction begin/commit với HTTP call begin/end; tìm nơi transaction bao trùm network.
4. Tìm @Transactional ở service/reader/processor/writer/tasklet và cả outer caller; kiểm tra AOP proxy/self-invocation.
5. Kiểm tra timeout/retry/backoff: một HTTP timeout có giữ connection rồi retry bên trong transaction không?
6. Nếu có sự cố đang diễn ra, giảm concurrency/admission theo runbook để bảo vệ DB, không tăng pool mù.
7. Xác định side effect bên ngoài có thể đã thành công trước khi retry; kiểm tra idempotency/correlation.
8. Sửa boundary theo hướng transaction ngắn + durable state/outbox hoặc tách enrichment phase.
9. Chạy failure injection sau sửa: API chậm, mất response, process crash và restart.
10. Đối soát business output trước khi khôi phục publish/downstream, rồi benchmark trên peak workload.

Không sửa trực tiếp `BATCH_STEP_EXECUTION.STATUS` thành `COMPLETED` để vượt qua rollback hoặc metadata không nhất quán; điều đó che giấu lỗi chứ không giải quyết tác dụng phụ.

## 19. Những hiểu nhầm phổ biến

| Nhận định | Điều cần chỉnh |
| --- | --- |
| “HTTP call trong `ItemProcessor` không liên quan transaction.” | Trong chunk-oriented step thông thường, processor chạy trong chu kỳ chunk transaction. |
| “Đổi processor thành tasklet là hết transaction.” | `TaskletStep.execute` thông thường cũng được transaction manager bao quanh. |
| “`@Transactional` chỉ ảnh hưởng câu SQL, HTTP không sao.” | HTTP làm method/transaction chậm commit; DB resource đã cấp có thể bị giữ. |
| “Spring transaction timeout sẽ hủy mọi HTTP call.” | Không tự bảo đảm hủy socket/blocking call. |
| “`NOT_SUPPORTED` luôn giải phóng outer locks.” | Suspend không nhất thiết commit outer transaction hoặc nhả resource. |
| “`REQUIRES_NEW` làm outer transaction kết thúc.” | Outer transaction còn tồn tại; có thể cần thêm connection. |
| “Chuyển sang remote chunking là hết transaction dài.” | Worker vẫn có chunk transaction, có thể lại gọi HTTP trong đó. |
| “HTTP 200 nghĩa local DB chắc chắn commit.” | Remote success và local DB commit là hai sự kiện khác nhau. |
| “HTTP timeout nghĩa đối tác chưa xử lý.” | Response có thể mất sau khi side effect đã xảy ra. |
| “Tạo outbox là exactly once ở broker.” | Outbox thường cần at-least-once publish và consumer dedupe. |
| “Lease token đủ chống mọi POST lặp.” | Token chỉ fence local DB updates, không ngăn external side effect đã xảy ra. |
| “Tăng Hikari pool giải quyết mọi nghẽn.” | Có thể tăng DB locks/IOPS contention; cần giảm transaction hold time. |
| “@Async luôn làm HTTP ở ngoài DB transaction.” | Nếu caller đợi kết quả trước commit hoặc async side effect không durable, vấn đề vẫn còn. |
| “Một transaction dài nhất quán hơn nhiều transaction ngắn.” | Qua nhiều hệ thống, DB transaction không bao HTTP/API; cần saga/outbox/idempotency. |
| “Job COMPLETED chứng minh không có duplicate.” | Cần reconciliation theo business key và version. |

## 20. Checklist thiết kế trước production

- [ ] Đã biết network I/O nằm trong reader/processor/writer/tasklet hay service nào.
- [ ] Không có DB transaction đã mở phải chờ HTTP/gRPC/broker latency.
- [ ] Đã đo transaction duration, JDBC connection hold time và HTTP p95/p99 **riêng biệt**.
- [ ] HTTP connect/read/overall deadlines hữu hạn, retry chỉ lỗi phù hợp và có budget.
- [ ] External side effects dùng stable idempotency key hoặc có phương án reconciliation.
- [ ] Claim/persist/outbox transactions đủ ngắn và có error handling rõ.
- [ ] Lease/fencing bảo vệ stale worker; recovery khi process crash và timeout được thử.
- [ ] Không gọi poller nontransactional từ outer chunk/tasklet transaction.
- [ ] Có nguồn READY/snapshot bất biến cho Spring Batch downstream.
- [ ] Chunk reader/writer giữ checkpoint và transaction đúng theo datasource.
- [ ] Có phân biệt PENDING/IN_PROGRESS/READY/FAILED và công cụ xử lý stuck items.
- [ ] Transactional outbox + inbox/dedupe nếu publish messages sau DB commit.
- [ ] DB/API connection pool và worker concurrency được tính trên **toàn bộ cluster**.
- [ ] Không dùng REQUIRES_NEW/NOT_SUPPORTED như bản vá cho outer transaction dài.
- [ ] Test HTTP timeout **trước và sau khi remote side effect xảy ra**.
- [ ] Test worker crash giữa claim/call/persist và lost lease, stale result.
- [ ] Test broker duplicate, restart JobInstance và output reconciliation.
- [ ] SLA có processing, retry, validation/publish và recovery headroom.

## 21. Câu hỏi tự kiểm tra

1. Vì sao gọi HTTP trong `ItemProcessor.process()` của chunk-oriented step thường là anti-pattern khi API chậm?
2. `@Transactional(timeout=10)` có tự dừng HTTP call đang block sau đúng 10 giây không?
3. Hikari `connectionTimeout` giới hạn thời gian gì, có giới hạn transaction lifetime không?
4. Nếu outer transaction đã UPDATE row rồi gọi method `NOT_SUPPORTED` để chờ HTTP, các row lock đã hết chưa?
5. Vì sao `REQUIRES_NEW` trong helper không tự kết thúc outer transaction?
6. Với 16 workers, mỗi worker giữ JDBC connection 25 ms DB + 400 ms HTTP, vì sao DB có thể có 16 connections bận dù CPU thấp?
7. Một response HTTP timeout sau khi đối tác đã charge thành công. Có nên retry POST với request ID mới không?
8. Trong mô hình claim/call/persist, network call xảy ra ở đâu so với hai transaction?
9. Vì sao cần lease token và `WHERE lease_token = ?` khi ghi response?
10. Lease token có bảo đảm không bao giờ gọi API tạo side effect hai lần không?
11. Vì sao Spring Batch `ItemWriter` thường không phải nơi phù hợp để publish message “sau commit”?
12. Transactional outbox bảo đảm điều gì và vẫn cần dedupe ở đâu?
13. Khi chuyển sang remote partitioning, HTTP call trong worker step có tự nằm ngoài transaction không?
14. Reader query `WHERE status='READY'` trên bảng liên tục đổi status có thể có vấn đề gì khi offset paging?
15. Với 1.000.000 item/giờ và latency API 0,4 giây, cần khoảng bao nhiêu requests in-flight trung bình theo Little's law?
16. Nếu API quota chỉ cho 20 in-flight, chỉ tăng thread count có đạt throughput đó không?
17. Metrics nào cho thấy transaction thực sự được tách khỏi HTTP wait?
18. Vì sao JobExecution `COMPLETED` không đủ để kết luận business effects xảy ra đúng một lần?

**Gợi ý trả lời:** (1) Processor thường nằm trong chunk transaction, API wait kéo dài transaction/lock/pool hold. (2) Không, phải cấu hình timeout/deadline của HTTP client. (3) Chờ mượn connection từ pool, không phải lifetime transaction. (4) Không nhất thiết; outer transaction chưa commit. (5) Nó chỉ tạo transaction độc lập, outer còn tồn tại. (6) Connection có thể bị giữ qua thời gian chờ mạng. (7) Không; dùng stable idempotency key hoặc tra trạng thái giao dịch. (8) Sau commit claim và trước bắt đầu persist TX. (9) Ngăn worker cũ ghi response sau khi lease đã bị worker khác lấy. (10) Không, remote side effect cần idempotency. (11) Writer thường chạy trước chunk commit. (12) Business state + outbox atomic trong DB; broker delivery có thể lặp, consumer cần inbox/idempotency. (13) Không, worker vẫn có chunk transaction. (14) Tập dữ liệu paging co/đổi, có thể bỏ sót item. (15) Khoảng 111–112. (16) Không với giả định một request/item và latency/quota giữ nguyên. (17) Transaction/pool hold p99 không đi theo HTTP p99. (18) Phải đối soát business IDs, versions, sums và side effects.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reader, processor, writer và commit interval.
- [Spring Batch Reference — Transaction Attributes](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/transaction-attributes.html): transaction attributes của step.
- [Spring Batch Reference — Retry and Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault tolerance và retry trong chunk-oriented step.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, partitioning và mô hình remote.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, checkpoint và restart.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, propagation và proxy boundaries.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW`, `NOT_SUPPORTED` và khác biệt physical/logical transaction.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` và row locking.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): lý do số JDBC connections tăng không bảo đảm throughput cao hơn.

**Điểm cốt lõi:** Không để transaction database **bị giữ mở chỉ vì một HTTP/gRPC/broker call chưa trả lời**. Trong Spring Batch, chunk/tasklet thông thường có ranh giới transaction, nên network call ở reader/processor/writer có thể kéo dài thời gian giữ DB resources và khuếch đại retry. Thiết kế an toàn là **DB transaction ngắn → network call ngoài transaction → DB transaction ngắn**, bổ sung lease/fencing, idempotency và snapshot/staging phù hợp; với việc publish sau commit, dùng **transactional outbox + inbox/dedupe**. Chỉ tăng thread pool hoặc JDBC pool sau khi đo rõ bottleneck, và luôn kiểm chứng bằng failure injection cùng reconciliation nghiệp vụ.
