# Gọi remote service trong transaction dài: lỗi thường gặp trong Spring Batch

Một Spring Batch Job thường kết hợp xử lý dữ liệu nội bộ với dịch vụ bên ngoài: tra cứu tỷ giá, xác thực khách hàng, gọi API tính phí, phát hành hóa đơn, đẩy thông báo hoặc đồng bộ đơn hàng sang hệ thống đối tác. Lỗi kiến trúc dễ gặp là **thực hiện HTTP/gRPC call ngay trong transaction database kéo dài của một chunk**.

Khi dịch vụ remote phản hồi chậm, transaction và kết nối database có thể bị giữ trong suốt thời gian chờ mạng. Nếu remote service đã thực hiện thao tác nhưng database transaction của Spring Batch lại rollback, hai hệ thống có thể rơi vào trạng thái không đồng nhất. Retry ngây thơ có thể khiến dịch vụ ngoài nhận lệnh nhiều lần.

Trong nhóm **Lỗi thường gặp** của **Spring Batch Core Processing**, bài này giải thích vì sao tình huống đó xuất hiện, tác động lên hiệu năng và độ tin cậy, cách nhận diện, các phương án tách giao dịch và cách kiểm thử khi remote service thất bại.

**Thông điệp chính:** Transaction của Spring Batch quản lý những tài nguyên tham gia transaction đó; nó **không tự biến một HTTP request thành thao tác có thể rollback**. Đừng đặt lệnh gọi remote có side effect trong transaction dài rồi kỳ vọng rollback sẽ hoàn tác cả hai hệ thống.

## 1. Tình huống thực tế

Giả sử `invoiceSettlementJob` có nhiệm vụ:

1. Đọc danh sách hóa đơn chờ thanh toán từ database.
2. Tính số tiền.
3. Gọi `POST /payments` tại một dịch vụ thanh toán bên ngoài.
4. Ghi trạng thái hóa đơn đã thanh toán vào database.
5. Commit mỗi 100 hóa đơn.

Cấu hình tưởng như hợp lý:

```text
invoiceSettlementJob
  |
  v
settleInvoicesStep (chunk size = 100)
  |
  +-- ItemReader: đọc hóa đơn
  |
  +-- ItemProcessor: gọi remote payment service
  |
  +-- ItemWriter: cập nhật bảng invoices
  |
  +-- commit chunk
```

Nếu mỗi remote call mất 300 ms, chỉ riêng 100 lệnh gọi tuần tự đã tốn khoảng **30 giây**, chưa tính I/O database, retry hoặc timeout. Trong nhiều cấu hình chunk-oriented processing, transaction của chunk đã được mở trong giai đoạn này.

Nếu remote service có một request mất 45 giây do timeout mạng, transaction có thể tồn tại lâu hơn nữa. Các vấn đề phát sinh có thể gồm:

- Connection database bị giữ lâu, làm giảm số connection khả dụng cho Job và các ứng dụng khác.
- Những hàng hoặc khóa database đã được cập nhật trong transaction có thể bị giữ tới commit/rollback.
- Transaction log/WAL và tài nguyên MVCC/locking tăng áp lực.
- Khi timeout, một chunk lớn có thể rollback và cần xử lý lại.
- Remote service có thể đã nhận và thực hiện yêu cầu dù client không nhận được response.
- Khi framework retry, cùng hóa đơn có thể bị gửi nhiều lần sang remote.
- Job bị chậm, vượt cửa sổ xử lý, xung đột với lần chạy kế tiếp.

Điểm khó nhất không chỉ là **transaction dài**, mà là **tính không nguyên tử giữa database và hệ thống remote**.

## 2. Spring Batch đặt transaction ở đâu?

Với một Step kiểu chunk-oriented, Spring Batch thường thực hiện đọc, xử lý và ghi một chunk bên trong một ranh giới transaction được quản lý bởi `PlatformTransactionManager`.

Sơ đồ khái niệm:

```text
Chunk transaction START
    |
    +-- read item 1
    +-- process item 1
    +-- read item 2
    +-- process item 2
    |       ...
    +-- read/process item N
    |
    +-- write chunk
    |
Chunk transaction COMMIT
```

Ví dụ Spring Batch 5.x:

```java
@Bean
Step settlementStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Invoice> reader,
        ItemProcessor<Invoice, Invoice> processor,
        ItemWriter<Invoice> writer) {

    return new StepBuilder("settlementStep", jobRepository)
            .<Invoice, Invoice>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Đây là cấu hình khái niệm; `Invoice` và các reader/processor/writer phải được ứng dụng cung cấp. Ở Spring Batch 6.x, package và một số API Step builder thay đổi theo phiên bản; cần dùng đúng dependency.

**Điểm quan trọng:** Chuyển lệnh HTTP từ `ItemWriter` sang `ItemProcessor` hoặc `ItemReader` **không tự bảo đảm lời gọi nằm ngoài transaction**. Trong chunk-oriented Step, các thành phần này thường được gọi trong phạm vi xử lý chunk có transaction.

`@Transactional` trên một service được gọi từ processor cũng không tự làm transaction ngắn đi. Theo propagation mặc định `REQUIRED`, service tham gia transaction hiện có. Dùng `REQUIRES_NEW` lại có thể tạo một transaction database mới trong khi transaction bên ngoài vẫn tồn tại và chờ; nó không biến HTTP thành thao tác transactional với database.

### Transaction trong `TaskletStep`

Không chỉ chunk: một `Tasklet` thực thi trong `TaskletStep` cũng thường được Spring Batch bao bọc bằng transaction theo cấu hình Step. Đưa lệnh gọi remote vào một Tasklet duy nhất không mặc nhiên khắc phục vấn đề. Cần **chủ động thiết kế ranh giới giao dịch**, không suy luận từ tên loại Step.

### Transaction có thể giữ những gì?

Không phải mọi transaction đều khóa toàn bộ bảng trong suốt thời gian tồn tại. Mức độ ảnh hưởng phụ thuộc:

- DBMS và isolation level.
- Các câu SQL đã chạy trước remote call.
- Row-level locks, index locks, optimistic/pessimistic locking.
- Cách reader mở cursor và kết nối.
- Driver/pool, flush và thời điểm DB connection được mượn.
- Mức concurrent load và thời gian transaction sống.

Một transaction chỉ đọc có thể không giữ write lock, nhưng vẫn có thể giữ snapshot hoặc connection và gây tác động tới MVCC/cleanup, tùy database. Vì vậy phải quan sát hệ thống thực tế thay vì khẳng định mọi transaction dài đều khóa toàn bộ dữ liệu.

## 3. Vì sao remote call nguy hiểm trong transaction?

### 3.1. Độ trễ mạng không có giới hạn chắc chắn

Một lời gọi HTTP có thể tốn:

```text
DNS lookup
  + TCP connect
  + TLS handshake
  + network latency
  + remote queue
  + remote business processing
  + response transfer
  + proxy/load-balancer retries
```

Thời gian trung bình 100 ms không có nghĩa P99 cũng là 100 ms. Một vài request ở đuôi chậm có thể kéo dài toàn chunk. Nếu gọi N request tuần tự trong một transaction, thời gian chờ có thể cộng dồn.

### 3.2. Chiếm connection và gây lock contention

Giả sử pool có 10 connection và 8 worker Batch đang giữ transaction trong lúc chờ API. Phần còn lại của ứng dụng chỉ có rất ít kết nối khả dụng. Các request khác chờ `getConnection()` và có thể timeout.

Nếu worker đã `UPDATE invoices SET status = 'PROCESSING'` trước khi gọi remote, khóa trên những hàng đó có thể tồn tại trong suốt thời gian chờ. Transaction khác muốn sửa cùng hóa đơn phải chờ.

Hệ quả có thể lan rộng: một remote service chậm khiến **database bị nghẽn** dù database không phải nguồn lỗi ban đầu.

### 3.3. Không có distributed rollback cho HTTP thông thường

Database transaction và HTTP request là hai hệ thống có cơ chế commit riêng:

```text
Spring Batch / DB                     Remote payment service
-----------------                     ----------------------
BEGIN TX
UPDATE invoice...
POST /payments --------------------->  charge succeeds
                                <----- HTTP 200
UPDATE invoice status...
DB COMMIT -> FAILS

Kết quả:
  Database: invoice chưa được đánh dấu đã trả
  Remote:   payment đã thực hiện thành công
```

Rollback database **không gọi “undo payment”** tự động. Một request HTTP thông thường không tham gia XA/2-phase commit của transaction manager. Ngay cả khi dùng JTA cho nhiều tài nguyên XA, một REST API bên ngoài không tự trở thành resource XA.

### 3.4. Timeout không có nghĩa request chưa được thực hiện

Một tình huống phổ biến:

```text
Client sends request
       |
       v
Remote commits payment
       |
       X response lost / read timeout
       |
Client sees timeout
       |
Batch retries request
       |
Remote receives duplicate
```

Client chỉ biết **không nhận được xác nhận**, không biết remote đã xử lý hay chưa. Vì thế, **không retry một lệnh có side effect chỉ vì gặp timeout** nếu remote endpoint không hỗ trợ idempotency hoặc cơ chế truy vấn lại kết quả theo khóa.

### 3.5. Rollback và retry có thể xử lý lại một item

Với chunk-oriented processing, transaction rollback có thể khiến các item trong chunk được xử lý lại, tùy reader, retry policy và khả năng restart. Các callback processor/writer có thể chạy hơn một lần cho cùng business entity.

Nếu processor gọi `POST` gây side effect, một invoice có thể bị gửi lại trong lần xử lý lại chunk. Đếm số lần gọi processor **không bằng** số business transaction duy nhất.

## 4. Dấu hiệu nhận diện qua log và metrics

Một Job có thể gặp các triệu chứng:

| Triệu chứng | Cơ chế có thể liên quan |
| --- | --- |
| `jobDuration` tăng đột biến khi remote chậm | Chunk transaction chờ network. |
| Connection pool `active` cao, `pending` tăng | Worker giữ connection lâu. |
| Database lock wait / deadlock tăng | Transaction giữ khóa trong lúc chờ remote. |
| `rollbackCount`, retry count tăng | Timeout/HTTP exception làm chunk rollback hoặc retry. |
| Job bị lỗi `CannotAcquireLockException` / transaction timeout | Tranh chấp DB và transaction duration. |
| Remote nhận request trùng | Retry sau timeout hoặc rollback nhưng remote đã commit. |
| Job restart và gửi lại request cũ | Không có idempotency key / outbox status bền vững. |
| Bảng nghiệp vụ báo chưa xử lý nhưng remote đã xử lý | Thiếu atomicity giữa DB và HTTP. |
| Throughput giảm khi tăng worker | Pool/DB/API bị bão hòa hoặc contention. |

Nên gắn các trường quan sát vào log và tracing:

```text
jobName
jobInstanceId
jobExecutionId
stepExecutionId
businessKey (đã được phép log)
outboxEventId / idempotencyKey
remoteOperation
remoteDurationMs
remoteStatusClass (2xx/4xx/5xx/timeout)
attemptNumber
retryDecision
transactionPhase
```

**Không đưa token, thông tin thẻ thanh toán, secret, payload chứa PII hoặc URL kèm credentials vào log.** Với metrics, không dùng `jobExecutionId` hoặc business key làm tag có cardinality không giới hạn; chúng phù hợp để truy vấn log chi tiết hơn.

## 5. Những cách sửa “nhanh” nhưng chưa giải quyết được vấn đề

### Chỉ tăng `transaction timeout`

Tăng transaction timeout có thể khiến Job bớt fail do timeout, nhưng **kéo dài thời gian giữ tài nguyên và cửa sổ không nhất quán**. Nó không khiến remote side effect rollback cùng DB.

### Chỉ tăng `connection pool size`

Pool lớn hơn có thể trì hoãn cạn kết nối, nhưng cũng cho phép thêm nhiều transaction đồng thời tới database và có thể làm tăng lock contention. Cần sửa thiết kế giao dịch dài trước khi mở rộng tài nguyên.

### Chuyển HTTP từ writer sang processor

Trong chunk Step, processor vẫn thường chạy trong transaction của chunk. Nếu processor gọi remote nhiều lần, transaction có thể vẫn dài tương tự.

### Thêm `@Transactional(REQUIRES_NEW)` cho remote service

`REQUIRES_NEW` tác động tới transaction Spring hỗ trợ, không biến HTTP thành XA resource. Ngoài ra, transaction ngoài có thể vẫn bị tạm treo/giữ tài nguyên trong lúc transaction mới chạy. Không nên dùng nó để che một ranh giới giao dịch chưa đúng.

### Chỉ dùng `@Transactional(timeout = 5)`

Transaction timeout giới hạn thời gian transaction ở phía ứng dụng/database theo cơ chế tương ứng, nhưng **không bảo đảm HTTP client ngắt đúng lúc**, không trả lại tiền đã charge và không tạo idempotency. Cần cả timeout mạng và chính sách lỗi.

### Chỉ bật `retry(...)` trong Spring Batch

Retry có ích với lỗi tạm thời **khi thao tác có thể retry an toàn**. Với `POST` không idempotent, retry có thể nhân đôi side effect. Skip cũng không phải giải pháp: bỏ qua invoice đã charge nhưng không được ghi trạng thái sẽ khiến dữ liệu mâu thuẫn.

### Dùng async thread ngay trong processor

Đẩy HTTP sang `CompletableFuture.runAsync(...)` rồi return trước khi có kết quả có thể làm Job commit khi tác vụ remote chưa hoàn tất. Không có bảo đảm worker async kế thừa transaction và `SecurityContext` của thread gọi. Cần một luồng điều phối bền vững, không chỉ thêm thread.

## 6. Chọn kiến trúc theo bản chất remote operation

Không phải remote call nào cũng giống nhau. Trước hết phân loại:

| Loại remote call | Ví dụ | Rủi ro chính | Thiết kế gợi ý |
| --- | --- | --- | --- |
| **Read-only lookup** | Lấy tỷ giá, thông tin tham chiếu | Latency, timeout, rate limit, dữ liệu thay đổi theo thời gian | Prefetch/cache, staging data trước chunk hoặc tách thành phase riêng. |
| **Idempotent PUT/UPSERT** | Đặt trạng thái của entity theo khóa xác định | Timeout không rõ kết quả, ordering và conflict | Idempotency key/version, retry có giới hạn, tách transaction khi có thể. |
| **Non-idempotent command** | Trừ tiền, phát hành coupon, gửi SMS | Side effect trùng sau retry/rollback | Transactional outbox, remote idempotency, trạng thái điều phối. |
| **Bulk remote API** | Gửi 1.000 item trong một request | Batch size, partial failure, timeout lớn | Chia batch ở tầng remote worker, mapping từng item và cơ chế replay. |
| **Long-running remote workflow** | Tạo báo cáo, xác nhận đối soát liên hệ thống | Không thể chờ kết thúc trong một DB transaction | Async command + callback/poll, state machine, timeout/reconciliation. |

Hai hướng chủ đạo:

1. Với **tra cứu dữ liệu**, giảm hoặc loại bỏ việc chờ mạng **trong transaction** bằng staging/cache và thiết kế điểm snapshot dữ liệu.
2. Với **lệnh làm thay đổi hệ thống ngoài**, ưu tiên **ghi ý định bền vững trong transaction ngắn**, rồi thực thi remote ngoài transaction bằng worker riêng.

## 7. Kiến trúc khuyến nghị: transactional outbox

**Transactional outbox** là một mô hình phổ biến để tách việc ghi nhận ý định nghiệp vụ và việc gọi remote.

Thay vì trực tiếp gọi `POST /payments` trong `ItemProcessor` hoặc `ItemWriter`:

1. Spring Batch xử lý invoice và ghi một **outbox command** vào database trong cùng transaction với thay đổi nội bộ cần thiết.
2. Chunk commit kết thúc nhanh mà không phải chờ HTTP.
3. Một worker/dispatcher đọc outbox đã commit, claim công việc, rồi gọi remote **ngoài DB transaction**.
4. Khi có kết quả, worker cập nhật trạng thái trong một transaction database ngắn khác.
5. Nếu lỗi, trạng thái outbox cho phép retry có giới hạn và đối soát. Remote endpoint cần idempotency key để tránh side effect trùng.

```text
Spring Batch Job                             Outbox dispatcher
----------------                             -----------------
BEGIN chunk TX
  read invoice
  validate/transform
  write invoice status=PENDING_REMOTE
  INSERT outbox(commandId, payload, status=NEW)
COMMIT chunk TX
       |
       v
BATCH OUTBOX TABLE  <---- claim in short transaction
                         COMMIT claim transaction
                             |
                             v
                         HTTP POST remote
                         (NO DB transaction held)
                             |
                     +-------+-------+
                     |               |
                  Success          Timeout/error
                     |               |
               short DB TX      short DB TX
               mark SENT        schedule retry /
               + reconcile      UNKNOWN/FAILED
                     |               |
                   COMMIT           COMMIT
```

### Tại sao mẫu này giảm rủi ro?

- Không giữ chunk transaction khi chờ response mạng.
- Ý định gửi được commit cùng những thay đổi local cần thiết.
- Dispatcher có thể chạy lại sau restart mà không phụ thuộc process Spring Batch ban đầu.
- Có trạng thái để theo dõi backlog và phân tích lỗi.
- Có thể giới hạn concurrency, rate limit, exponential backoff và circuit breaker ở tầng remote worker.

**Giới hạn quan trọng:** Transactional outbox **không tạo bảo đảm exactly-once cho HTTP**. Worker có thể gọi remote thành công rồi chết trước khi cập nhật outbox `SENT`. Lần chạy lại sẽ gửi cùng command. Vì vậy remote phải hỗ trợ idempotency hoặc có cách kiểm tra trạng thái theo command ID đáng tin cậy.

## 8. Thiết kế schema outbox

Ví dụ PostgreSQL:

```sql
CREATE TABLE payment_outbox (
    command_id       UUID PRIMARY KEY,
    invoice_id       BIGINT NOT NULL,
    operation        VARCHAR(40) NOT NULL,
    payload_json     JSONB NOT NULL,
    status           VARCHAR(32) NOT NULL,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_until      TIMESTAMPTZ NULL,
    worker_id        VARCHAR(100) NULL,
    remote_reference VARCHAR(255) NULL,
    last_error_code  VARCHAR(100) NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payment_outbox_dispatch
ON payment_outbox (status, next_attempt_at);
```

Các cột minh họa:

| Trường | Ý nghĩa |
| --- | --- |
| `command_id` | ID ổn định của một ý định remote; dùng làm idempotency key. |
| `invoice_id` | Khóa nghiệp vụ, có thể nối với bảng invoice. |
| `operation` | Loại thao tác remote, ví dụ `CAPTURE_PAYMENT`. |
| `payload_json` | Dữ liệu cần gửi; phải quản lý bảo mật và giới hạn PII. |
| `status` | `NEW`, `SENDING`, `SENT`, `RETRY`, `UNKNOWN`, `DEAD`. |
| `attempt_count` | Số lần worker đã thử gửi theo cơ chế điều phối. |
| `next_attempt_at` | Thời điểm được phép retry lần tiếp theo. |
| `lease_until` | Thời hạn claim để tránh nhiều worker xử lý cùng lúc. |
| `worker_id` | Worker đang giữ claim, phục vụ vận hành/fencing. |
| `remote_reference` | ID kết quả remote nếu có, giúp đối soát. |
| `last_error_code` | Mã lỗi chuẩn hóa, không lưu raw token/response nhạy cảm. |

Nếu mỗi invoice chỉ được charge một lần cho một nghĩa vụ thanh toán, nên có **unique business constraint** bổ sung như `(invoice_id, operation, business_version)`. `command_id` duy nhất chưa đủ: một lỗi mapping có thể sinh hai UUID khác nhau cho cùng hành động nghiệp vụ.

### Command ID phải ổn định qua retry/restart

Một cách định danh phổ biến:

```text
commandId = stable identifier of invoice + operation + business version
```

Có thể tạo UUID deterministically theo business key, hoặc sinh UUID một lần khi ghi outbox và **tái sử dụng chính ID đã lưu** ở mọi lần retry. Không sinh UUID mới mỗi lần worker gọi lại remote, vì điều đó làm idempotency key thay đổi.

Nếu remote yêu cầu header:

```http
POST /payments
Idempotency-Key: <stable-command-id>
Content-Type: application/json
```

Hợp đồng idempotency thực tế phụ thuộc remote service: thời gian giữ key, phạm vi uniqueness, cách xử lý request cùng key nhưng payload khác, mã phản hồi và khả năng tra cứu kết quả. Không giả định mọi API đều hỗ trợ header như ví dụ.

## 9. Bước Batch chỉ ghi ý định vào outbox

Ví dụ Spring Batch 5.x dùng `ItemProcessor` chỉ biến đổi dữ liệu tại chỗ, không gọi remote. Bản ghi invoice được ánh xạ sang command cần gửi.

```java
import java.util.UUID;

public record Invoice(
        long id,
        String businessKey,
        long amountCents,
        long version) {
}

public record PaymentCommand(
        UUID commandId,
        long invoiceId,
        long amountCents,
        String operation) {
}
```

Processor:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.batch.item.ItemProcessor;

public final class PaymentCommandProcessor
        implements ItemProcessor<Invoice, PaymentCommand> {

    @Override
    public PaymentCommand process(Invoice invoice) {
        if (invoice.amountCents() <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }

        // Một khóa logic ổn định cho cùng invoice/version/operation.
        String logicalKey = invoice.businessKey()
                + ":CAPTURE_PAYMENT:" + invoice.version();

        UUID commandId = UUID.nameUUIDFromBytes(
                logicalKey.getBytes(StandardCharsets.UTF_8));

        return new PaymentCommand(
                commandId,
                invoice.id(),
                invoice.amountCents(),
                "CAPTURE_PAYMENT");
    }
}
```

Lưu ý `UUID.nameUUIDFromBytes` trong Java tạo ID từ bytes theo thuật toán của JDK. Đây là minh họa **deterministic ID**, không phải cơ chế ẩn thông tin: nếu input business key có thể đoán, ID cũng có thể dự đoán. Chỉ dùng với key/namespace thích hợp; khi cần bảo mật hoặc chống lộ khóa, sinh ID ngẫu nhiên một lần rồi lưu bền vững thay vì chuyển dữ liệu nhạy cảm vào UUID.

Writer PostgreSQL minh họa:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<PaymentCommand> outboxWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<PaymentCommand>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO payment_outbox
                    (command_id, invoice_id, operation,
                     payload_json, status)
                VALUES
                    (:commandId, :invoiceId, :operation,
                     CAST(:payloadJson AS jsonb), 'NEW')
                ON CONFLICT (command_id) DO NOTHING
                """)
            .itemSqlParameterSourceProvider(cmd ->
                    new MapSqlParameterSource()
                            .addValue("commandId", cmd.commandId())
                            .addValue("invoiceId", cmd.invoiceId())
                            .addValue("operation", cmd.operation())
                            .addValue("payloadJson",
                                    "{\"amountCents\":"
                                        + cmd.amountCents() + "}")
            )
            .build();
}
```

Đoạn SQL dùng cú pháp **PostgreSQL**. Với DBMS khác, thay thế bằng cú pháp upsert/dedup tương ứng. `ON CONFLICT DO NOTHING` chỉ thể hiện một lựa chọn idempotent đơn giản; nếu cùng `command_id` xuất hiện với payload khác, hệ thống thực tế cần phát hiện **conflict nghiệp vụ** chứ không im lặng bỏ qua.

Step:

```java
@Bean
Step preparePaymentCommandsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Invoice> invoiceReader,
        PaymentCommandProcessor processor,
        JdbcBatchItemWriter<PaymentCommand> outboxWriter) {

    return new StepBuilder(
            "preparePaymentCommandsStep", jobRepository)
            .<Invoice, PaymentCommand>chunk(200, transactionManager)
            .reader(invoiceReader)
            .processor(processor)
            .writer(outboxWriter)
            .build();
}
```

**Tại sao tốt hơn gọi API trong processor?** Phần trong chunk giờ chỉ thực hiện xử lý local và SQL outbox. Không có HTTP call nào được thực thi trong transaction của chunk. Nếu transaction rollback, lệnh outbox chưa commit cũng rollback theo — với điều kiện sử dụng **cùng database và transaction manager phù hợp**.

Trong ứng dụng thật, nếu cần đồng thời cập nhật `invoices` sang `PENDING_REMOTE` và insert outbox, thực hiện cả hai trong cùng transaction, ví dụ bằng writer tổng hợp sử dụng cùng datasource. Không thay đổi trạng thái invoice rồi commit trước khi insert outbox vì khi process chết giữa hai thao tác có thể mất lệnh remote.

### Những điều cần chú ý khi áp dụng

- `InvoiceReader` chỉ chọn những invoice hợp lệ và thuộc phạm vi Job, không tự tạo command lặp cho invoice đã hoàn tất.
- Dùng unique key nghiệp vụ để chống duplicate khi Job retry/restart.
- Nếu dùng hai datasource/transaction manager, phải thiết kế nhất quán riêng; transaction Spring Batch không mặc định bao trùm cả hai DB.
- Metadata JobRepository, outbox và dữ liệu nghiệp vụ là những nhóm dữ liệu khác nhau; không dùng cleanup metadata để xóa outbox production.
- Dữ liệu payload phải đáp ứng yêu cầu bảo mật và retention; outbox có thể chứa lệnh thanh toán nhạy cảm.

## 10. Dispatcher: chỉ giữ transaction khi claim và cập nhật trạng thái

Dispatcher nên có ba pha **tách biệt**:

1. **Claim:** lấy một lệnh `NEW`/`RETRY` bằng transaction database ngắn, đánh dấu ai đang xử lý và lease.
2. **Call remote:** kết nối mạng ngoài transaction database.
3. **Acknowledge/reschedule:** ghi kết quả hoặc lịch retry trong transaction ngắn khác.

Mã minh họa dùng `TransactionTemplate` để hiện ranh giới:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public final class PaymentOutboxDispatcher {

    private final TransactionTemplate transactionTemplate;
    private final PaymentOutboxRepository outbox;
    private final RemotePaymentGateway gateway;

    public PaymentOutboxDispatcher(
            TransactionTemplate transactionTemplate,
            PaymentOutboxRepository outbox,
            RemotePaymentGateway gateway) {

        this.transactionTemplate = transactionTemplate;
        this.outbox = outbox;
        this.gateway = gateway;
    }

    public void dispatchOne() {
        Optional<PendingPayment> claimed =
                transactionTemplate.execute(status ->
                        outbox.claimNextReady());

        if (claimed == null || claimed.isEmpty()) {
            return;
        }

        PendingPayment payment = claimed.get();

        try {
            // Không có DB transaction từ claim đang mở ở đây.
            RemoteReceipt receipt = gateway.capture(
                    payment.commandId(),
                    payment.invoiceId(),
                    payment.amountCents());

            transactionTemplate.executeWithoutResult(status ->
                    outbox.markSent(
                            payment.commandId(),
                            payment.claimToken(),
                            receipt.remoteReference()));

        } catch (RemoteOutcomeUnknownException ex) {
            transactionTemplate.executeWithoutResult(status ->
                    outbox.markUnknownForReconciliation(
                            payment.commandId(),
                            payment.claimToken(),
                            "TIMEOUT_OR_UNCERTAIN_RESULT"));

        } catch (RetryableRemoteException ex) {
            transactionTemplate.executeWithoutResult(status ->
                    outbox.scheduleRetry(
                            payment.commandId(),
                            payment.claimToken(),
                            "REMOTE_RETRYABLE_ERROR"));

        }
    }

    public record PendingPayment(
            UUID commandId,
            long invoiceId,
            long amountCents,
            String claimToken) {
    }

    public record RemoteReceipt(String remoteReference) {
    }

    public interface RemotePaymentGateway {
        RemoteReceipt capture(
                UUID commandId,
                long invoiceId,
                long amountCents);
    }

    public interface PaymentOutboxRepository {
        Optional<PendingPayment> claimNextReady();
        void markSent(
                UUID commandId,
                String claimToken,
                String remoteReference);
        void markUnknownForReconciliation(
                UUID commandId,
                String claimToken,
                String errorCode);
        void scheduleRetry(
                UUID commandId,
                String claimToken,
                String errorCode);
    }

    public static class RetryableRemoteException
            extends RuntimeException {
    }

    public static class RemoteOutcomeUnknownException
            extends RuntimeException {
    }
}
```

Đây là **khung triển khai**: `PaymentOutboxRepository` và `RemotePaymentGateway` là interface do ứng dụng cung cấp, chưa có SQL claim, retry clock hay HTTP transport trong ví dụ. `TransactionTemplate` ở đây sử dụng transaction manager của database outbox, và `dispatchOne()` phải được gọi từ một scope **không có outer transaction đang mở**. Nếu gọi bên trong một method `@Transactional`, `TransactionTemplate` mặc định `REQUIRED` có thể tham gia outer transaction; thiết kế cần bảo đảm method dispatcher được kích hoạt từ scheduler/service không giữ DB transaction từ trước.

### Một claim cần tính nguyên tử

Không viết:

```java
if (outbox.findFirstNew() != null) {
    outbox.markSending(...);
}
```

mà không có kiểm soát concurrency. Hai worker có thể chọn cùng command trước khi bất kỳ worker nào cập nhật trạng thái.

Với PostgreSQL, có thể dùng transaction ngắn với `SELECT ... FOR UPDATE SKIP LOCKED` và `UPDATE`, hoặc một câu `UPDATE ... RETURNING` chọn công việc đủ điều kiện theo cơ chế nguyên tử. Cần có:

- `lease_until` để phục hồi command nếu worker chết.
- `claimToken` hoặc generation/fencing number để worker cũ không cập nhật nhầm sau khi lease bị worker khác chiếm.
- `next_attempt_at` để retry không tạo vòng lặp nóng.
- `attempt_count` và giới hạn nỗ lực.
- Unique business key/idempotency ở remote để tránh side effect trùng.

### Vấn đề lease hết hạn khi HTTP còn chạy

`lease_until` không phải mutex tuyệt đối. Nếu remote call kéo dài hơn lease, worker B có thể claim lại trong khi worker A chưa kết thúc. Do đó:

1. Đặt HTTP timeout ngắn hơn hoặc phù hợp với lease policy.
2. Gia hạn lease với cơ chế điều phối phù hợp cho tác vụ dài.
3. Dùng fencing/claim token để tránh stale update trong DB.
4. Dựa vào idempotency key để bảo vệ remote side effect ngay cả khi có duplicate request.

Một distributed lock không thay thế tính idempotent của hệ thống đích.

## 11. Khi không biết remote đã thành công hay chưa

Không phải mọi lỗi remote đều như nhau:

| Tình huống | Có biết side effect remote đã xảy ra không? | Hành động gợi ý |
| --- | --- | --- |
| HTTP 2xx kèm reference xác thực | Thông thường có kết quả thành công theo contract | Lưu `SENT`/`CONFIRMED` trong transaction ngắn. |
| HTTP 400 do validation trước xử lý | Tùy contract, có thể kết luận request bị từ chối | Lưu `REJECTED` và lý do đã chuẩn hóa; không retry vô hạn. |
| HTTP 429 / 503 | Có thể là lỗi tạm thời, tùy contract | Retry sau backoff, tôn trọng `Retry-After` nếu có. |
| Connection refused trước khi gửi request | Thường chưa có side effect, nhưng cần xét transport | Retry có giới hạn. |
| Read timeout sau khi gửi request | **Không chắc** remote đã commit hay chưa | Trạng thái `UNKNOWN`, tra cứu theo idempotency/command ID trước khi retry tùy API. |
| Client nhận HTTP 500 | Không mặc định biết remote đã rollback | Kiểm tra contract; có thể là outcome unknown. |
| Worker chết sau HTTP 200, trước DB ack | Remote đã thực hiện nhưng outbox vẫn chưa `SENT` | Idempotent retry hoặc reconciliation bằng command ID. |

Một số API chỉ cung cấp retry-idempotency trong một thời hạn nhất định (ví dụ key được lưu trong vài giờ). Nếu Job có thể replay sau nhiều ngày, chính sách xử lý cần tính đến **thời hạn dedup** và khả năng tra cứu kết quả bền vững từ remote.

Không có remote idempotency và không có API reconciliation, bài toán “thực hiện side effect đúng một lần tuyệt đối khi timeout và crash” thường không thể được bảo đảm chỉ bằng Spring Batch. Khi đó cần thay đổi hợp đồng tích hợp hoặc dùng một quy trình đối soát nghiệp vụ thay vì hứa hẹn exactly-once.

## 12. Timeout và retry khi gọi remote

Ngay cả khi đã tách transaction, HTTP client vẫn cần timeout. Tránh lời gọi remote chờ vô hạn rồi giữ một worker/outbox claim mãi.

Phân biệt các giới hạn:

- **Connect timeout:** thời gian chờ thiết lập kết nối.
- **Read/response timeout:** thời gian chờ dữ liệu phản hồi.
- **Overall deadline:** hạn chót cho cả một lệnh, có thể gồm nhiều retry.
- **Retry backoff:** khoảng chờ giữa các lần thử.
- **Rate limit:** số request/s hoặc số request đồng thời được remote chấp nhận.

Ví dụ cấu hình `RestClient` trên Spring Framework 6.1+:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Bean
RestClient paymentRestClient() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

    factory.setConnectTimeout(Duration.ofSeconds(2));
    factory.setReadTimeout(Duration.ofSeconds(5));

    return RestClient.builder()
            .baseUrl("https://payments.example.internal")
            .requestFactory(factory)
            .build();
}
```

Địa chỉ trong ví dụ chỉ là placeholder kỹ thuật, không phải API có thật. Nên cấu hình URL qua môi trường/secret management và validate destination; không lấy URL tùy ý từ JobParameters không đáng tin cậy.

Ví dụ request với idempotency key:

```java
public RemoteReceipt capture(PendingPayment payment) {
    var response = paymentRestClient.post()
            .uri("/payments")
            .header(
                    "Idempotency-Key",
                    payment.commandId().toString())
            .body(new PaymentRequest(
                    payment.invoiceId(),
                    payment.amountCents()))
            .retrieve()
            .body(PaymentResponse.class);

    if (response == null) {
        throw new RemoteOutcomeUnknownException();
    }

    return new RemoteReceipt(response.paymentReference());
}
```

Các kiểu `PendingPayment`, `PaymentRequest`, `PaymentResponse`, `RemoteReceipt` ở ví dụ là DTO/record do dự án định nghĩa. Logic phân loại HTTP status, transport exception và thời gian timeout cần hoàn thiện theo contract remote. `retrieve()` có thể ném exception tùy status; **không được coi mọi exception là lỗi chưa có side effect**.

### Chính sách retry gợi ý

```text
Attempt 1
  |
  +-- 2xx ------------> SENT
  |
  +-- permanent 4xx --> REJECTED / manual review
  |
  +-- 429/503 --------> RETRY after backoff + jitter
  |
  +-- timeout --------> UNKNOWN -> query remote by key
                             |
                             +-- found success -> SENT
                             +-- known rejected -> REJECTED
                             +-- no answer     -> review / safe retry
```

Cần giới hạn retry theo nỗ lực và tổng thời gian, tránh retry storm khi remote outage. Backoff nên có jitter nếu nhiều worker cùng thử. Có thể thiết lập circuit breaker để giảm tải cho remote trong thời gian sự cố, nhưng circuit breaker **không giải quyết tính đúng đắn của side effect**.

## 13. Nếu remote operation là read-only: staging và cache

Không phải mọi remote lookup đều cần outbox. Giả sử một Job kiểm tra tỷ giá theo ngày trước khi tính toán:

```text
ItemReader -> ItemProcessor -> GET /exchange-rate -> ItemWriter
```

Nếu mỗi item gọi cùng một tỷ giá, đó vừa là overhead network vừa làm chunk transaction dài. Các hướng tốt hơn:

### 13.1. Prefetch một lần cho toàn Job hoặc cửa sổ dữ liệu

```text
Prepare phase (remote lookup, no long DB transaction)
    |
    v
Persist approved reference snapshot / cache
    |
    v
Chunk Step: read -> calculate using local snapshot -> write
```

Định danh snapshot bằng ngày tỷ giá, phiên bản nguồn và timestamp, để có thể restart nhất quán. Nếu chỉ cache trong memory mà Job restart ở node khác, kết quả có thể thay đổi; cần xem yêu cầu tái lập nghiệp vụ.

**Cẩn thận:** đưa remote call vào một Tasklet Step riêng **không mặc nhiên khiến nó chạy ngoài transaction**, vì TaskletStep cũng có transaction boundary. Cần thiết kế lời gọi network ở orchestrator ngoài transaction chunk/Tasklet hoặc cấu hình service/transaction boundary cụ thể và kiểm chứng đường gọi thực tế.

### 13.2. Batch remote reads thay vì N calls trên N items

Nếu remote có API hỗ trợ bulk GET, gom danh sách khóa cần lookup và nạp một lần theo batch, rồi lưu kết quả vào bảng staging hoặc cache dùng trong Step. Việc tăng batch size giảm số round trip nhưng cần tính đến giới hạn request payload, timeout và rate limit.

### 13.3. Cache có tính nhất quán rõ ràng

Cache phù hợp khi dữ liệu tham chiếu ít thay đổi, nhưng phải có:

- TTL hoặc version cố định theo JobInstance.
- Chính sách cache miss.
- Cách invalidation khi nghiệp vụ yêu cầu.
- Giới hạn bộ nhớ và key cardinality.
- Khả năng tái tạo cùng kết quả khi restart.

Đừng dùng cache mà không xác định dữ liệu theo thời điểm nào nếu Job cần kết quả có thể audit.

## 14. Tách Job thành nhiều giai đoạn

Khi việc gọi remote không thể hoàn thành nhanh và cần xử lý hàng triệu item, một Job đồng bộ duy nhất có thể không còn là mô hình phù hợp.

Ví dụ xử lý theo ba giai đoạn:

```text
Job A: Prepare commands
  └── Read invoices -> validate -> write durable outbox
                         |
                         v
                  Dispatcher service
                  (remote HTTP, retries, reconciliation)
                         |
                         v
Job B: Finalize / reconcile
  └── Read confirmed remote outcomes -> update business status
```

Job A có thể kết thúc `COMPLETED` ngay sau khi các command được ghi bền vững, nhưng điều đó **không đồng nghĩa tất cả hóa đơn đã thanh toán ở remote**. Phải định nghĩa rõ:

- `PREPARATION_COMPLETED`: lệnh đã được tạo và commit.
- `REMOTE_PENDING`: còn outbox cần gửi.
- `REMOTE_CONFIRMED`: kết quả đã được xác nhận.
- `RECONCILIATION_FAILED`: có trường hợp không rõ/khác biệt cần xử lý.
- `BUSINESS_COMPLETED`: quy trình nghiệp vụ thực sự đã hoàn tất.

Các trạng thái này có thể nằm ở bảng nghiệp vụ/state machine, không nhất thiết là các `BatchStatus` mặc định. Nếu dashboard hiển thị Job A `COMPLETED`, cần bổ sung metric backlog/outcome để không khiến người vận hành hiểu lầm toàn bộ thanh toán đã thành công.

### Chọn orchestration

| Phương án | Phù hợp khi | Điều cần chú ý |
| --- | --- | --- |
| Một Job tạo outbox + worker nền | Remote call lâu, nhiều lệnh độc lập | Dữ liệu đích và SLA hoàn tất ở tầng worker. |
| Hai Job Batch có checkpoint | Có bước staging và finalize theo đợt | Điều phối phụ thuộc giữa hai Job, retry và restart. |
| Message queue + consumer | Cần mở rộng remote throughput linh hoạt | Delivery có thể trùng, consumer idempotent. |
| Async remote workflow + callback | Remote trả job/token rồi xử lý lâu | Callback authentication, correlation ID, timeout và reconciliation. |
| Remote service cung cấp bulk API | Có thể gửi lô lớn một cách đáng tin cậy | Partial failure và idempotency cho từng item. |

Không có một kiến trúc duy nhất phù hợp mọi quy trình. Điểm bất biến là **không giữ transaction database của chunk mở suốt thời gian chờ remote dài**.

## 15. Chọn chunk size và số worker sau khi tách remote call

Tách network khỏi chunk transaction thường giảm latency của commit path, nhưng vẫn cần đo.

Trong Job ghi outbox:

- Chunk size lớn hơn có thể giảm overhead commit, nhưng tăng bộ nhớ và phạm vi rollback.
- Writer nên dùng JDBC batching khi phù hợp.
- Unique/index trên outbox phải đáp ứng throughput.
- Các update cùng hot rows có thể vẫn gây contention; cần chọn khóa nghiệp vụ và partition phù hợp.

Trong dispatcher:

- **Max in-flight requests** là giới hạn số HTTP call đồng thời.
- **Remote rate limit** giới hạn request trên giây.
- **Connection pool HTTP** cần đủ cho worker nhưng không quá lớn.
- **Outbox claim batch size** cân bằng chi phí DB và lease.
- **Backpressure** tránh khiến queue tăng mãi hoặc gây quá tải remote.

Ví dụ một remote service chỉ cho 100 request/s mà mỗi Job tạo 10.000 command/s. Tăng thread ở dispatcher không giải quyết được giới hạn remote. Cần cơ chế backlog, SLA xử lý và rate control, hoặc thay đổi hợp đồng bulk API.

Theo dõi ít nhất:

```text
outbox_pending_count
outbox_oldest_age_seconds
outbox_sent_total
outbox_retry_total
outbox_unknown_total
remote_request_duration_seconds
remote_request_error_total
db_transaction_duration_seconds
db_connection_pool_pending
batch_step_rollback_count
```

Đối với metric labels, dùng những giá trị có cardinality giới hạn như `operation`, `status`, `remote_service`; không dùng `invoiceId` hoặc `commandId` làm label.

## 16. Tương tác với skip/retry trong Spring Batch

Spring Batch hỗ trợ `faultTolerant()`, `retry(...)`, `skip(...)` và các listener tương ứng. Chúng rất hữu ích khi được dùng đúng loại lỗi, nhưng không thay thế kiến trúc remote-safe.

### 16.1. Lỗi dữ liệu nội bộ

Nếu invoice sai định dạng hoặc thiếu trường bắt buộc, có thể cấu hình skip/quality report cho đúng exception. Đó là lỗi dữ liệu riêng lẻ, không liên quan remote latency.

### 16.2. Lỗi remote tạm thời

Nếu remote không phản hồi, chiến lược phù hợp thường là lưu command bền vững và retry ở dispatcher. Không nên để hàng triệu HTTP retry diễn ra ngay trong chunk transaction của Job và giữ lock/connection.

### 16.3. Remote trả kết quả mơ hồ

Một timeout có thể xuất hiện sau khi remote đã commit. Không được phân loại chắc chắn thành “không xử lý” rồi retry không idempotent. Cần trạng thái `UNKNOWN` và reconciliation bằng idempotency key.

### 16.4. Trường hợp cần dùng remote trong chunk?

Có những tình huống không thể thay đổi kiến trúc ngay, ví dụ hệ thống legacy yêu cầu kiểm tra từ xa cho mỗi record và không hỗ trợ cache. Nếu bắt buộc giữ remote lookup trong chunk:

1. Chỉ dùng cho remote operation đọc/idempotent.
2. Đặt connect/read/overall timeout và retry có giới hạn.
3. Giảm chunk size cho phù hợp thời gian remote P95/P99.
4. Giám sát DB connection hold time, lock wait, rollback và throughput.
5. Không cập nhật/giữ khóa nghiệp vụ trước khi chờ remote nếu có thể tránh.
6. Kiểm tra semantics khi rollback/restart và không giả định remote side effect có thể undo.
7. Lập kế hoạch tách network khỏi transaction khi đủ điều kiện.

Đây là **biện pháp giảm thiểu tạm thời**, không phải lời khuyên mặc định cho kiến trúc mới.

## 17. Điểm khác nhau giữa transaction timeout và HTTP timeout

| Timeout | Được kiểm soát ở đâu | Tác động chính | Không bảo đảm điều gì |
| --- | --- | --- | --- |
| DB transaction timeout | Transaction manager/DB | Hạn chế giao dịch kéo dài và khả năng commit | Không undo remote side effect. |
| Connection timeout | HTTP client | Không chờ thiết lập kết nối quá lâu | Không giới hạn toàn bộ response time. |
| Read/response timeout | HTTP client | Không chờ dữ liệu vô hạn | Không chứng minh remote chưa xử lý. |
| Overall request deadline | Client/orchestrator | Giới hạn thời gian một attempt | Không tự động hủy side effect đã commit ở remote. |
| Retry budget | Dispatcher | Giới hạn số attempt/tổng thời gian | Không thay thế idempotency. |
| Outbox lease timeout | Database claim layer | Phục hồi command khi worker chết | Không chắc chắn worker cũ đã ngừng HTTP. |

Cần thiết kế các timeout **ăn khớp**: một HTTP attempt không nên vượt lease một cách không kiểm soát; tổng retry và timeout phải phù hợp SLA; transaction ngắn phải có đủ thời gian cho SQL cần thiết nhưng không bao trùm network.

Không nên đặt mọi timeout cùng một số chỉ vì dễ cấu hình. Mỗi timeout bảo vệ một tầng khác nhau.

## 18. Thiết kế test chứng minh lỗi transaction dài

Một bài test chỉ kiểm tra Job `COMPLETED` không chứng minh transaction đã được rút ngắn. Muốn phát hiện việc gọi HTTP trong transaction, cần kiểm tra ranh giới cụ thể.

### 18.1. Unit test vị trí remote call

Nếu thiết kế mới có `PaymentCommandProcessor` thuần dữ liệu, test nên chứng minh processor **không gọi remote gateway**. Có thể dùng mock trong các component khác, nhưng với processor thuần thì chỉ cần assert output command và deterministic command ID.

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentCommandProcessorTest {

    @Test
    void createsStableCommandWithoutHttpCall() throws Exception {
        PaymentCommandProcessor processor =
                new PaymentCommandProcessor();

        Invoice invoice =
                new Invoice(10L, "INV-2026-001", 15_000L, 1L);

        PaymentCommand first = processor.process(invoice);
        PaymentCommand second = processor.process(invoice);

        assertThat(first.commandId())
                .isEqualTo(second.commandId());
        assertThat(first.invoiceId()).isEqualTo(10L);
        assertThat(first.amountCents()).isEqualTo(15_000L);
    }
}
```

Test này không chứng minh toàn hệ thống không gọi HTTP từ một listener khác. Nó chỉ xác nhận processor cụ thể là một phép biến đổi local.

### 18.2. Test dispatcher không giữ transaction khi gọi HTTP

Có thể tạo `RemotePaymentGateway` giả lập để kiểm tra transaction activity lúc `capture` được gọi.

Với `TransactionSynchronizationManager`:

```java
import org.springframework.transaction.support
        .TransactionSynchronizationManager;

public final class TransactionInspectingGateway
        implements RemotePaymentGateway {

    @Override
    public RemoteReceipt capture(
            UUID commandId,
            long invoiceId,
            long amountCents) {

        if (TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new AssertionError(
                    "Remote HTTP call must not run inside DB transaction");
        }

        return new RemoteReceipt("remote-test-reference");
    }
}
```

Đây là một test helper minh họa: cần cung cấp các interface/record của dự án và cấu hình Spring transaction manager để phép kiểm tra có nghĩa. Trong test tích hợp, hãy cấu hình dispatcher sử dụng `TransactionTemplate` để claim và ack, gọi method từ **ngoài outer transaction**.

Nếu test method được đánh dấu `@Transactional` và trực tiếp gọi dispatcher, transaction test bên ngoài có thể làm phép kiểm tra thất bại dù dispatcher tự mở các scope ngắn. Nên tắt transaction bao quanh test hoặc dùng test cụ thể có ranh giới transaction được kiểm soát.

### 18.3. Test remote chậm không giữ DB transaction

Dùng HTTP test server hoặc fake gateway có `CountDownLatch`:

```text
Test starts dispatcher
   |
   v
Dispatcher claims command -> short DB COMMIT
   |
   v
Remote gateway blocked at latch
   |
   +-- Test probes DB / transaction resources
   |      Expected: claim transaction already committed
   |
Test releases latch
   |
   v
Dispatcher receives response -> short DB COMMIT
```

Nên kiểm tra bằng một transaction **khác** rằng command đã ở trạng thái `SENDING` trong lúc remote bị chặn. Điều này là bằng chứng phạm vi claim đã commit. Không chỉ dùng kiểm tra `TransactionSynchronizationManager` vì nó cho biết trạng thái thread hiện hành, chưa thể hiện toàn bộ lock/connection lifecycle từ những thread khác.

### 18.4. Test remote thành công nhưng DB ack lỗi

Kịch bản then chốt cho độ tin cậy:

1. Outbox có command `C` ở trạng thái `NEW`.
2. Dispatcher claim và gọi remote với idempotency key `C`.
3. Remote xử lý thành công, trả reference.
4. Cố ý làm DB ack thất bại hoặc kill worker trước khi cập nhật `SENT`.
5. Worker khác claim lại sau lease/recovery.
6. Remote nhận lại **cùng key `C`** và trả cùng kết quả theo contract idempotency.
7. Outbox chuyển `SENT`, không tạo thêm một khoản charge.

Nếu test chỉ kiểm tra remote trả 200 một lần, không phát hiện được lỗi nghiêm trọng nhất của outbox/retry.

### 18.5. Test timeout không rõ kết quả

1. Fake remote thực hiện side effect nhưng cố ý không trả response.
2. Client thấy read timeout.
3. Outbox ghi `UNKNOWN` hoặc trạng thái cần reconciliation.
4. Dispatcher/query remote theo idempotency key để xác nhận kết quả.
5. Không blindly gửi charge mới với key khác.
6. Kiểm tra log và trạng thái cuối phản ánh đúng sự không chắc chắn.

### 18.6. Test rollback chunk không làm mất/nhân đôi command

Tạo Job ghi outbox, gây rollback sau khi writer bắt đầu xử lý. Với unique constraint và deterministic command ID, chạy lại chunk hoặc restart Job:

- Không có command đã commit nếu toàn chunk bị rollback.
- Sau retry thành công, có đúng một outbox command cho business operation.
- Không có remote side effect trước khi transaction outbox commit.
- Nếu JobInstance restart, command key vẫn tương ứng với cùng nghiệp vụ.

## 19. Ví dụ test tích hợp với `spring-batch-test`

Giả sử Job `preparePaymentsJob` chỉ đọc invoice và ghi outbox, không gửi HTTP trong chunk.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class PaymentOutboxBatchIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    @Qualifier("preparePaymentsJob")
    private Job job;

    @Test
    void jobShouldCreateCommittedCommands() throws Exception {
        jobLauncherTestUtils.setJob(job);

        // Test fixture: database đã có 3 invoice hợp lệ.
        // Các invoice test phải được tạo/reset bởi fixture riêng.

        var parameters = new JobParametersBuilder()
                .addString(
                        "benchmarkRunId",
                        UUID.randomUUID().toString(),
                        true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        Integer pending = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM payment_outbox
                WHERE status = 'NEW'
                """,
                Integer.class);

        assertThat(pending).isEqualTo(3);
    }
}
```

Ví dụ dùng **Spring Batch 5.x**, `JobLauncherTestUtils`, JUnit Jupiter và AssertJ. Đây là khung test: phải cung cấp bean Job, reader, writer, schema outbox và fixture ba invoice. Nếu test chạy song song hoặc dùng database chung, cần cô lập dữ liệu để tránh `COUNT(*)` đọc nhầm command từ test khác.

Trong thực tế nên assert thêm:

- Ba `command_id` tương ứng đúng ba invoice.
- Mỗi business operation chỉ có một command.
- Dữ liệu payload đúng và không chứa trường nhạy cảm không cần thiết.
- Không có request HTTP nào phát ra trong giai đoạn Job chuẩn bị outbox.
- Trạng thái invoice và command được commit nhất quán.

## 20. Một phương án khác: cập nhật business state sau remote

Không phải quy trình nào cũng muốn đặt invoice thành `PAID` ngay trong chunk. Với thanh toán, thường nên dùng state machine:

```text
Invoice CREATED
     |
     v
PAYMENT_PENDING (command in outbox)
     |
     v
Remote request sent
     |
     +-- Remote confirms --> PAID
     |
     +-- Remote rejects  --> PAYMENT_REJECTED
     |
     +-- Outcome unknown --> PAYMENT_RECONCILING
```

Trạng thái `PAID` chỉ nên được gán khi có bằng chứng thanh toán đã thành công theo hợp đồng remote. Nếu một DB update trạng thái `PAID` bị lỗi, dispatcher có thể reconcile lại bằng remote reference và command ID.

Đây là một dạng **saga/orchestration** ở tầng nghiệp vụ: thay vì hứa hẹn một global transaction bao trùm tất cả hệ thống, mỗi bước có commit riêng, trạng thái rõ ràng và cơ chế compensation/reconciliation khi cần.

Đặc biệt với lệnh không thể hoàn tác như gửi email hoặc SMS, không có compensation thật sự “thu hồi email”. Vì thế điều quan trọng là tránh gửi trùng, xác định kết quả và có trạng thái theo dõi.

## 21. Nguyên tắc vận hành và giám sát

Để phát hiện vấn đề sớm, theo dõi cả Job và dispatcher:

| Nhóm | Tín hiệu nên theo dõi |
| --- | --- |
| Spring Batch | Job status, Step duration, `rollbackCount`, `readCount`, `writeCount`, retry/skip theo loại lỗi. |
| Database | Transaction duration, active connections, pool waiting time, lock wait, deadlock, long-running queries. |
| HTTP client | Connect/read timeout, latency P50/P95/P99, HTTP error classes, retry rate, in-flight requests. |
| Outbox | Số command `NEW`/`RETRY`/`UNKNOWN`, tuổi command cũ nhất, số command `DEAD`. |
| Nghiệp vụ | Số invoice `PAYMENT_PENDING`, số remote charge confirmed, số case reconciliation chưa giải quyết. |

Một log có thể có:

```text
INFO payment.outbox.sent
  jobExecutionId=9001
  commandId=<stable-id>
  invoiceBusinessKey=<safe-key>
  remoteService=payments
  remoteReference=<safe-reference>
  durationMs=281
  attempt=2
```

Không dùng một HTTP 200 làm chứng cứ duy nhất rằng quy trình nghiệp vụ đã kết thúc nếu còn bước cập nhật trạng thái, kiểm tra chữ ký/response hoặc đối soát.

### Công cụ điều tra lỗi production

Khi Job đột nhiên chậm:

1. So thời gian mỗi Step và số chunk/rollback.
2. Kiểm tra dashboard connection pool, DB locks và transaction tuổi cao.
3. Phân tích latency remote P95/P99, timeout và retry.
4. Tra distributed trace cho một request bị chậm, nối bằng business key/command ID an toàn.
5. Xác định điểm giữ transaction: trước, trong hay sau remote call.
6. Phân biệt slow-path do dữ liệu lớn, remote outage hay thay đổi cấu hình pool/chunk.
7. Nếu đã dùng outbox, xem backlog và tốc độ dispatcher; không tự động tăng thread mà chưa xét rate limit của remote.
8. Với `UNKNOWN` outcome, truy vấn remote theo idempotency key, tránh tự động tạo lệnh mới.

Không dọn bảng outbox hoặc metadata JobRepository để “làm job chạy nhanh hơn” khi chưa kiểm tra chức năng restart, audit và reconciliation. Outbox `SENT` có thể được archive theo chính sách retention riêng, nhưng phải bảo đảm còn dữ liệu cần cho dedup/audit.

## 22. Các sai lầm thường gặp và cách sửa

### Gọi HTTP trong `ItemProcessor` vì “processor chỉ biến đổi dữ liệu”

Processor không nhất thiết là nơi thuần computation nếu code chứa network call. Trong chunk Step, nó thường chạy trong transaction scope. **Sửa:** tách remote lookup sang staging hoặc chuyển remote command thành outbox record.

### Gọi remote trong writer rồi hy vọng DB rollback sẽ hoàn tác

`ItemWriter` có thể chạy trong DB transaction, nhưng HTTP không tự tham gia rollback. **Sửa:** commit outbox command trước, dispatcher gọi remote sau commit và dùng idempotency.

### Retry mọi `RestClientException` không phân loại

Timeout có thể xảy ra sau khi remote đã commit. **Sửa:** phân biệt known retryable vs unknown outcome, áp dụng idempotency và reconciliation.

### Tăng chunk size để giảm commit, vô tình tăng thời gian giữ transaction

Nếu mỗi item có remote latency lớn, chunk size 1.000 có thể giữ transaction rất lâu. **Sửa:** bỏ network khỏi chunk trước khi tuning chunk size; tối ưu commit sau khi thiết kế đúng.

### Chuyển sang `@Async` nhưng không theo dõi kết quả

Job có thể báo `COMPLETED` khi HTTP task vẫn đang chạy; process chết làm mất task trong bộ nhớ. **Sửa:** lưu command bền vững, dùng queue/outbox và trạng thái ack.

### Đặt `@Transactional(REQUIRES_NEW)` quanh HTTP

HTTP vẫn không transactional; transaction ngoài có thể vẫn tồn tại. **Sửa:** đặt remote call **giữa** các transaction ngắn đã commit, không chỉ đổi annotation.

### Cho rằng outbox bảo đảm exactly-once

Worker có thể crash sau khi remote commit trước khi mark `SENT`. **Sửa:** idempotency key ổn định, dedup ở remote, reconciliation khi outcome unknown.

### Dùng UUID mới mỗi lần retry

Remote nhìn thấy mỗi lần là một lệnh khác nhau. **Sửa:** lưu command ID một lần và dùng lại; ràng buộc business operation.

### Xóa command khi HTTP timeout

Không biết remote đã xử lý hay chưa; xóa command làm mất khả năng đối soát. **Sửa:** lưu `UNKNOWN` hoặc trạng thái retry/reconciliation được thiết kế rõ.

### Cho phép dispatcher chạy dưới outer `@Transactional`

`TransactionTemplate` có thể tham gia transaction ngoài theo propagation. Kết quả là remote call vẫn nằm trong transaction dài. **Sửa:** tổ chức entrypoint dispatcher không có outer transaction, kiểm tra bằng test và metrics.

### Chỉ tối ưu tốc độ, không kiểm tra side effect

Một cấu hình có thể nhanh nhưng gửi trùng payment. **Sửa:** kiểm tra số business operations unique, remote references và trạng thái sau crash/retry.

## 23. Bài tập thực hành

Giả sử `shippingOrderJob` đọc 50.000 đơn hàng đã thanh toán và gọi remote shipping service để tạo vận đơn. Remote API có P95 = 800 ms, đôi lúc mất 15 giây và có thể trả HTTP 503. Database dùng PostgreSQL, Job chạy trên 4 worker; các yêu cầu không được tạo vận đơn trùng.

### Phần A — Phân tích thiết kế lỗi

1. Vẽ transaction boundary của Step hiện tại khi `ItemProcessor` gọi `POST /shipments`.
2. Tính sơ bộ thời gian chờ mạng nếu một chunk 100 item được gọi tuần tự, chưa tính retry.
3. Liệt kê connection/lock nào có thể bị giữ và metric để kiểm tra thực tế.
4. Mô tả kịch bản remote đã tạo vận đơn nhưng HTTP response bị mất.
5. Giải thích vì sao rollback chunk không hủy được vận đơn đã tạo.

### Phần B — Đổi sang outbox

1. Thiết kế `shipment_outbox` có `command_id` ổn định, `order_id`, status, lease, attempt count và remote reference.
2. Tạo một Step chỉ ghi command/outbox và trạng thái `SHIPMENT_PENDING` trong transaction ngắn.
3. Bảo đảm unique constraint cho một yêu cầu tạo vận đơn trên một order/version.
4. Viết dispatcher claim bằng transaction ngắn, gọi shipping API ngoài transaction, rồi ack bằng transaction ngắn.
5. Gửi idempotency key đến remote; lưu reference trả về.

### Phần C — Lỗi và recovery

1. Remote trả HTTP 503 → retry sau backoff, không giữ DB transaction.
2. Remote tạo vận đơn rồi client read-timeout → đánh dấu `UNKNOWN` và query kết quả theo command ID.
3. Worker chết trước DB ack → worker khác retry cùng idempotency key, không tạo vận đơn thứ hai.
4. Lease hết hạn khi worker A vẫn chạy → xác minh fencing/dedup.
5. Job Spring Batch thất bại rồi restart → không tạo outbox command trùng cho cùng order/version.

### Phần D — Benchmark và quan sát

1. Đo Job Step duration, transaction duration và connection pool trước/sau thay đổi.
2. So sánh throughput tạo command của Batch và throughput xác nhận remote của dispatcher — đây là hai đại lượng **khác nhau**.
3. Kiểm tra tuổi command pending cũ nhất và SLA tạo vận đơn.
4. Đánh giá chi phí remote rate limit và số worker phù hợp.
5. Khẳng định dữ liệu cuối có đúng 50.000 vận đơn duy nhất nếu tất cả đơn đều được chấp nhận, không chỉ Job A có `COMPLETED`.

### Một câu hỏi quan trọng

Nếu dispatcher đã gửi yêu cầu tạo vận đơn, remote trả 200 và sau đó `markSent` trong database thất bại, **transaction nào có thể rollback?** Trạng thái thật ở remote và database khác nhau thế nào? Thiết kế idempotency/reconciliation sẽ đưa hệ thống về trạng thái đúng ra sao?

Đây chính là lý do việc **không gọi remote service trong transaction dài** phải đi cùng một chiến lược phối hợp kết quả, không chỉ là di chuyển vài dòng code.

## Tài liệu tham khảo

- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời reader/processor/writer và chunk.
- [Spring Batch Reference – Transaction Attributes](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/transaction-attributes.html): cấu hình thuộc tính transaction cho Step.
- [Spring Batch Reference – Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong fault-tolerant Step và các điều kiện cần cân nhắc.
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): sự khác biệt giữa skip và lỗi làm fail Step.
- [Spring Framework Reference – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, propagation và transaction manager.
- [Spring Framework Reference – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cấu hình HTTP client và gọi REST API.
- [Microservices.io – Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): ghi message/command bền vững cùng giao dịch local và phát ngoài transaction.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Step và các giới hạn concurrency khi tăng worker.

