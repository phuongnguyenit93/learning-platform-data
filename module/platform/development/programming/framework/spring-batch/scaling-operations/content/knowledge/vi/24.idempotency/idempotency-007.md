# Replay chunk an toàn trong Spring Batch

> **Chương:** Idempotency
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài học tập trung vào **phát lại (replay) một chunk mà không mất, không nhân đôi tác dụng nghiệp vụ**, kể cả khi rollback, retry, restart hoặc broker gửi lại yêu cầu sau sự cố.

Một chunk đã được *đọc* không đồng nghĩa đã được *commit*. Một worker đã ghi thành công dữ liệu đích cũng chưa chắc manager đã nhận được phản hồi. Do đó, kiến trúc batch có khả năng phục hồi phải chấp nhận rằng cùng item hoặc cùng chunk **có thể được thực thi nhiều lần**, trong khi kết quả nghiệp vụ cần giữ đúng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khi nào Spring Batch xử lý lại một chunk và phân biệt **retry trong lượt chạy**, **restart cùng JobInstance** và **redelivery của remote chunk request**.
2. Xác định các mốc **read, process, write, update checkpoint, commit, reply/ACK** cùng những khoảng hở gây mất hoặc lặp dữ liệu.
3. Thiết kế writer idempotent dựa trên **business operation key**, unique constraint và transaction, thay vì chỉ dựa vào `chunkId` hoặc `StepExecutionId`.
4. Phân biệt replay an toàn đối với database cùng transaction, API bên ngoài, message broker và file/object storage.
5. Thiết lập kiểm thử fault injection, concurrency, retry/restart và đối soát để chứng minh kết quả chính xác khi scale workload.

## 1. Replay chunk là gì?

Trong Spring Batch, một **chunk** là nhóm item được đọc, xử lý, ghi dưới một ranh giới transaction do step cấu hình. Ví dụ `chunk(100, transactionManager)` thường gom tối đa 100 item vào một lần ghi/commit, trừ các trường hợp cuối input hoặc fault-tolerant processing có hành vi đặc thù.

**Chunk replay** là việc **cùng một tập item hoặc một phần item tương đương được xử lý/ghi lại** sau lỗi hoặc yêu cầu phát lại. Nó không nhất thiết là một API có tên `replayChunk()`; đó là hiện tượng hệ thống phải xử lý an toàn ở nhiều tầng.

Ví dụ:

~~~text
Chunk C-17: [ORDER-101, ORDER-102, ORDER-103]

Lần thử #1:
  read -> process -> write -> COMMIT?
  mạng lỗi / worker crash / manager không nhận reply

Lần thử #2:
  một hoặc cả ba order lại được đưa tới writer

Kỳ vọng:
  mỗi business operation chỉ có một kết quả hợp lệ cuối cùng,
  hoặc trạng thái xung đột có thể điều tra;
  không cộng tiền hai lần hay tạo hai invoice.
~~~

### Ba hình thức replay thường gặp

| Hình thức | Điều gì kích hoạt? | Phạm vi có thể bị xử lý lại |
| --- | --- | --- |
| **Rollback/retry tại chunk** | Exception ở reader/processor/writer, fault-tolerant step thử lại | Item/chunk chưa commit, đôi khi writer được gọi lại khi cô lập item lỗi |
| **Restart job** | `JobExecution` `FAILED`/`STOPPED`, operator restart cùng `JobInstance` | Item kể từ checkpoint bền vững; những chunk chưa ghi nhận hoàn tất |
| **Remote redelivery** | Broker chưa nhận ACK hoặc manager chưa nhận reply | Cùng chunk request có thể đến worker lần nữa, kể cả sau business commit |

Ba hình thức có nguyên nhân khác nhau nhưng đều đặt ra một câu hỏi: **Nếu item này đã gây ra tác dụng nghiệp vụ, lần thực thi lại có làm tác dụng ấy xảy ra thêm lần nữa không?**

## 2. Mốc transaction và những khoảng hở nguy hiểm

Trong một chunk step đơn giản, các giai đoạn logic gồm:

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant J as JobRepository
    participant D as Business database
    R->>R: read(items)
    R->>P: process(items)
    P->>W: write(chunk)
    W->>D: SQL mutations
    R->>J: ItemStream.update(context)
    J->>J: Store checkpoint/counters
    Note over D,J: Commit atomic chỉ nếu cấu hình transaction hỗ trợ
~~~

Sơ đồ mô tả các **mốc khái niệm**, không khẳng định mọi implementation đều có thứ tự gọi SQL giống hệt. `ItemStream.update(...)` và metadata persistence được Spring Batch điều phối theo vòng đời chunk; thời điểm commit thật sự phụ thuộc transaction manager, datasource và step implementation.

### Crash window cần kiểm tra

| Điểm xảy ra lỗi | Business effect | Checkpoint/metadata | Rủi ro sau restart |
| --- | --- | --- | --- |
| Trước khi writer ghi | Chưa có | Chưa advance hợp lệ | Item được xử lý lại; thường an toàn nếu reader state đúng |
| Writer đã ghi SQL nhưng **chưa commit** | Có thay đổi chưa commit | Có thể chưa commit | Nếu cùng transaction: rollback rồi replay |
| Business DB **commit**, metadata DB chưa commit/được ghi | Dữ liệu đích đã tồn tại | Có thể vẫn ở checkpoint cũ | **Replay item đã ghi**; writer phải idempotent |
| Metadata checkpoint được coi là hoàn tất nhưng business effect chưa bền vững | Business effect thiếu | Đã advance | Nguy cơ **mất item**; thiết kế transaction sai |
| Remote worker đã commit, reply/ACK thất lạc | Effect đã xảy ra | Manager có thể chưa biết | Broker/manager có thể phát lại work unit |

**Kết luận:** Cần kiểm tra **tài nguyên nào thật sự tham gia cùng transaction**. Không được mặc định `JobRepository`, business DB, broker và HTTP API luôn commit cùng nhau.

### Khi business data và metadata cùng transaction

Nếu writer và phần metadata cập nhật trong chunk thực sự được enlist trong **cùng transaction atomic** với cùng database/transaction manager phù hợp, rollback giúp tránh trạng thái “data commit nhưng checkpoint chưa commit” đối với phần được bao phủ. Đây là cấu hình thuận lợi để restart theo checkpoint.

Tuy nhiên, vẫn phải giữ writer an toàn khi **retry của framework** hoặc khi có tác dụng phụ khác ngoài transaction. Một khi ứng dụng ghi sang datasource khác hoặc gọi API, mô hình atomic này không còn được suy ra chỉ từ `@Transactional` hay tên `PlatformTransactionManager`.

## 3. Chọn đúng mức định danh khi replay

Spring Batch và hạ tầng message có nhiều loại ID, nhưng không ID nào thay thế được mọi loại khác.

| Định danh | Ví dụ | Dùng để làm gì? | Có đủ để chống ghi nghiệp vụ trùng? |
| --- | --- | --- | --- |
| `JobInstance` identity | job name + identifying parameters | Nhận diện công việc logic cần restart | Không: một job chứa rất nhiều item |
| `JobExecutionId` | `501` | Một lần chạy/restart | Không: thay đổi khi restart |
| `StepExecutionId` | `7001` | Một worker/step attempt | Không: thay đổi khi worker được chạy lại |
| Partition key | `range-0003` | Xác định phần việc trong kế hoạch | Không: chứa nhiều item |
| Chunk request/correlation ID | `C-17` | Nhận diện một yêu cầu remote chunk | Chỉ là tối ưu dedupe chunk; chưa đủ cho side effect từng item |
| Source record ID | `sourceA:ORD-1001` | Truy vết bản ghi nguồn | Cần gắn đúng phiên bản và nghiệp vụ |
| **Business operation ID** | `capture:PAY-1001` | Nhận diện tác dụng **phải xảy ra tối đa một lần** | **Thường là khóa quan trọng nhất** |

Một key nghiệp vụ điển hình:

~~~text
(tenantId, operationId)
~~~

Hoặc với pipeline snapshot, nơi cùng một source item ở hai phiên bản khác nhau **được phép** tạo hai kết quả độc lập:

~~~text
(tenantId, sourceVersion, sourceItemId, operationType)
~~~

**Phải chốt semantics trước khi chốt unique key.** Nếu cùng một lệnh thanh toán được replay trong snapshot mới mà unique key lại chứa snapshot mới, có thể vô tình thu tiền lần nữa. Ngược lại, một nghiệp vụ hợp lệ phải cập nhật sang phiên bản mới có thể bị chặn sai nếu key quá rộng.

### Cùng key nhưng payload thay đổi

Replay đúng phải mang **cùng ý nghĩa nghiệp vụ**. Nếu nhận:

~~~text
operationId=PAY-1001, amount=100.00
operationId=PAY-1001, amount=900.00
~~~

thì đây không phải duplicate bình thường. Writer cần **phát hiện conflict** bằng payload hash/các trường bất biến, báo lỗi hoặc chuyển sang reconciliation. `ON CONFLICT DO NOTHING` không kiểm tra payload có thể che dữ liệu bị sửa bất ngờ.

## 4. Định nghĩa bất biến nghiệp vụ trước khi viết mã

Một job idempotent phải có tiêu chí kiểm chứng rõ, thay vì chỉ yêu cầu `BatchStatus.COMPLETED`.

Ví dụ job ghi ledger từ file giao dịch:

1. Với mỗi `(tenantId, operationId)` hợp lệ, ledger có **tối đa một** bản ghi.
2. Nếu cùng operation được replay với cùng payload, kết quả không đổi.
3. Nếu cùng operation ID nhưng payload khác, job **không tự chọn** bản cuối và không im lặng bỏ qua; phải báo conflict.
4. Sau khi khôi phục, mọi source record thuộc snapshot đều có trạng thái: `APPLIED`, `FILTERED` đúng nghiệp vụ, `QUARANTINED` hoặc `PENDING`; không có item mất dấu.
5. Nếu có bước publish/gọi API, trạng thái phải phản ánh **xác nhận thật của đích**, không chỉ kết quả trả về của processor.

~~~mermaid
flowchart LR
    S["Input item + stable business key"] --> C{"Key đã tồn tại?"}
    C -- "Chưa" --> N["Ghi dữ liệu / ledger trong transaction"]
    C -- "Rồi" --> H{"Payload tương đương?"}
    H -- "Có" --> D["Duplicate hợp lệ:<br/>không tạo effect mới"]
    H -- "Không" --> E["Conflict:<br/>fail/quarantine"]
    N --> OK["Commit thành công"]
    D --> OK
~~~

**Bất biến được thực thi tại hệ thống đích**, ví dụ unique constraint/transaction trong database hoặc idempotency key có hiệu lực tại API nhận. Chỉ kiểm tra bằng một `HashSet` trong JVM không đủ khi job có nhiều thread, nhiều node hoặc restart.

## 5. Replay-safe writer với PostgreSQL

Với writer ghi vào một database, cách trực quan là dùng **unique business key** và kiểm tra nội dung của bản ghi đã tồn tại. Mục tiêu: ghi mới một lần; replay hợp lệ thành no-op; replay khác payload thành lỗi có thể điều tra.

### 5.1. Schema minh họa

~~~sql
CREATE TABLE ledger_output (
    tenant_id       VARCHAR(80)  NOT NULL,
    operation_id    VARCHAR(160) NOT NULL,
    source_version  VARCHAR(120) NOT NULL,
    source_id       VARCHAR(160) NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    amount          NUMERIC(18, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Chỉ mục khóa chính `(tenant_id, operation_id)` chống tạo hai ledger row cho cùng operation kể cả khi hai worker khác JVM chạy đồng thời. `source_version` và `source_id` dùng cho truy vết; chúng **không** làm thay đổi định danh operation trong ví dụ này.

Không lưu `payload_hash` mà không xác định cách canonical hóa: các biểu diễn khác nhau của cùng giá trị số/JSON có thể sinh hash khác. Phải thống nhất thuật toán, thứ tự trường, version schema và biểu diễn số tiền. Nếu giá trị có ràng buộc chính xác, đối chiếu cả trường bất biến quan trọng chứ không chỉ dựa vào hash.

### 5.2. Java ItemWriter có kiểm tra conflict

Ví dụ Spring Batch 5.x, PostgreSQL và Spring JDBC:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

record LedgerOutput(
        String tenantId,
        String operationId,
        String sourceVersion,
        String sourceId,
        String payloadHash,
        BigDecimal amount) {}

record StoredLedger(
        String sourceVersion,
        String sourceId,
        String payloadHash,
        BigDecimal amount) {}

public final class IdempotentLedgerWriter
        implements ItemWriter<LedgerOutput> {

    private final JdbcTemplate jdbc;

    public IdempotentLedgerWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends LedgerOutput> chunk) {
        for (LedgerOutput item : chunk) {
            int inserted = jdbc.update(
                    """
                    INSERT INTO ledger_output (
                        tenant_id, operation_id, source_version,
                        source_id, payload_hash, amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (tenant_id, operation_id)
                    DO NOTHING
                    """,
                    item.tenantId(),
                    item.operationId(),
                    item.sourceVersion(),
                    item.sourceId(),
                    item.payloadHash(),
                    item.amount());

            if (inserted == 1) {
                continue; // Lần đầu tiên ghi operation này.
            }

            StoredLedger prior = jdbc.queryForObject(
                    """
                    SELECT source_version, source_id,
                           payload_hash, amount
                    FROM ledger_output
                    WHERE tenant_id = ? AND operation_id = ?
                    """,
                    (rs, rowNum) -> new StoredLedger(
                            rs.getString("source_version"),
                            rs.getString("source_id"),
                            rs.getString("payload_hash"),
                            rs.getBigDecimal("amount")),
                    item.tenantId(),
                    item.operationId());

            boolean samePayload = prior != null
                    && Objects.equals(
                            prior.sourceVersion(), item.sourceVersion())
                    && Objects.equals(
                            prior.sourceId(), item.sourceId())
                    && Objects.equals(
                            prior.payloadHash(), item.payloadHash())
                    && prior.amount().compareTo(item.amount()) == 0;

            if (!samePayload) {
                throw new IllegalStateException(
                        "Trùng operationId nhưng dữ liệu khác nhau: "
                        + item.operationId());
            }
            // Duplicate hợp lệ: không ghi ledger thêm lần nữa.
        }
    }
}
~~~

**Giả định để ví dụ đúng:**

- `JdbcTemplate` dùng **business DataSource** được quản lý bởi transaction manager của chunk step. Mỗi lần `write(...)` được gọi dưới transaction phù hợp.
- Câu `ON CONFLICT DO NOTHING` là cú pháp **PostgreSQL**; với hệ database khác cần thay bằng cơ chế atomic tương đương.
- Hai transaction cạnh tranh cùng unique key sẽ được database phân xử; trong PostgreSQL, transaction có thể phải chờ transaction kia kết thúc trước khi quyết định conflict.
- Đối chiếu row cũ xảy ra sau khi database đã xác nhận không insert mới; với isolation mặc định `READ COMMITTED`, truy vấn sau có thể nhìn thấy row đã commit. Hãy kiểm thử nếu ứng dụng thay isolation hoặc có cơ chế transaction bất thường.
- Ví dụ **cố ý** xem source version là bất biến cho một operation. Nếu nghiệp vụ cho phép tái phát hành cùng operation trong snapshot mới, phải định nghĩa lại logic đối chiếu có kiểm soát.
- Các record/types minh họa có thể tách thành file riêng theo quy tắc tổ chức Java. Không đặt call tới HTTP/email không idempotent bên trong vòng lặp này.

Đây là mẫu dễ hiểu, **không phải writer batch-optimized**: mỗi duplicate thực hiện thêm `SELECT` nên có thể chậm ở quy mô lớn. Sau khi kiểm chứng logic, có thể tối ưu batch SQL/staging/merge, nhưng phải giữ nguyên khả năng phát hiện conflict, unique key và semantics transaction.

### 5.3. Gắn writer vào chunk step

~~~java
@Bean
Step ledgerImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, LedgerOutput> processor,
        ItemWriter<LedgerOutput> idempotentLedgerWriter) {

    return new StepBuilder("ledgerImportStep", jobRepository)
            .<OrderInput, LedgerOutput>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(idempotentLedgerWriter)
            .build();
}
~~~

`OrderInput`, processor và reader là thành phần nghiệp vụ do ứng dụng định nghĩa. Với Spring Batch 5.x, các kiểu `Step`, `StepBuilder`, `JobRepository`, `ItemReader`, `ItemProcessor`, `ItemWriter`, `PlatformTransactionManager` và annotation `@Bean` cần import tương ứng.

**Đặc biệt quan trọng:** `transactionManager` phải bảo vệ transaction của **writer này**. Nếu manager đang dùng transaction manager khác, đừng giả định chunk commit có thể rollback bản ghi ledger. Cần kiểm tra cả cách `JobRepository` lưu checkpoint để xử lý đúng các crash windows.

## 6. Tại sao checkpoint đúng vẫn chưa bảo đảm effect đúng một lần?

Với reader restartable, `ItemStream` thường hỗ trợ `open/update/close` và lưu trạng thái đọc vào `ExecutionContext`. Ví dụ:

~~~text
Chunk 1: ID 1..200      COMMIT → checkpoint 201
Chunk 2: ID 201..400    COMMIT → checkpoint 401
Chunk 3: ID 401..600    crash giữa write/checkpoint

Sau restart có thể đọc lại ID 401..600.
Writer phải chấp nhận replay của các operation đã ghi.
~~~

Nếu business write và checkpoint thật sự commit atomic trong cùng transaction, phần chưa commit sẽ rollback và restart có thể tiếp tục chính xác. Nhưng nếu có hai datasource hoặc side effect ngoài transaction, những item đã tạo effect ở đích có thể bị đọc lại.

### Một số lỗi checkpoint nguy hiểm

| Sai lầm | Hậu quả |
| --- | --- |
| Reader lưu “đã đọc tới ID 600” trước khi writer commit | Nếu worker crash, có thể bỏ qua item chưa được ghi |
| Dùng query không có sort key ổn định | Paging restart có thể thiếu/trùng khi dữ liệu thay đổi |
| Thay range partition khi restart cùng `JobInstance` | Checkpoint cũ không còn ứng với phần việc cũ |
| Reader không hỗ trợ `saveState` nhưng giả định resume | Có thể replay toàn bộ range hoặc sai vị trí |
| Multi-threaded chunk tự cập nhật một key `lastId` | Commit out-of-order có thể làm bỏ sót item |
| Đặt `chunkId` sinh từ timestamp làm business key | Khi replay key đổi, writer không chặn duplicate |

**Phân biệt rõ:** Cấu hình checkpoint giải quyết “bắt đầu lại từ đâu”; idempotency giải quyết “nếu bắt đầu lại trùng phần đã làm, hậu quả là gì”. Một hệ thống đáng tin cậy thường cần **cả hai**.

## 7. Retry và skip có thể khiến writer được gọi lại

Trong Spring Batch fault-tolerant step, một lỗi ghi chunk có thể làm transaction rollback; framework có thể retry hoặc cô lập item lỗi để quyết định skip theo policy.

~~~text
Chunk [A, B, C, D]
    |
    +-- Writer lần đầu: exception vì C
    |
    +-- Rollback transaction
    |
    +-- Retry / tách đường xử lý để nhận diện item lỗi
    |
    +-- Writer có thể gặp lại A, B, C hoặc D
    |
    +-- C được skip nếu exception skippable và còn skipLimit
~~~

**Không lấy số lần gọi `ItemWriter.write(...)` làm số chunk commit.** Một writer có thể được gọi nhiều lần, nhưng chỉ commit thành công mới là mốc bền vững với database.

### Các quy tắc quan trọng

- **Processor nên thuần dữ liệu** khi có thể. Nếu processor gửi email/gọi thanh toán trước writer, rollback ở writer không hoàn tác được tác dụng đó.
- **Writer có side effect** phải chịu được retry/replay. Với database, dùng transaction và unique business key; với API, dùng idempotency key tại API đích.
- **Skip không sửa dữ liệu đã ghi trước đó** vào hệ thống ngoài transaction. Nếu C bị skip sau khi các request khác đã phát thành công, phải có reconciliation riêng.
- **`skipLimit` là theo `StepExecution`**, không phải tổng ngân sách lỗi của mọi partition hoặc mọi lần restart.

## 8. Remote chunking: replay xảy ra ở tầng message

Trong **remote chunking**, manager đọc item và gửi **chunk request** qua middleware; worker nhận chunk, xử lý/ghi và gửi **reply** về manager. Khác với remote partitioning, request không nhất thiết tương đương một worker `StepExecution` độc lập theo từng range.

~~~mermaid
sequenceDiagram
    participant M as Manager: reader/chunking
    participant Q as Broker
    participant W as Worker: processor/writer
    participant D as Business DB
    M->>Q: Chunk request C-17
    Q->>W: Deliver C-17
    W->>D: Write business operations
    D-->>W: COMMIT
    W--xQ: Reply/ACK thất lạc
    Q->>W: Redeliver C-17
    W->>D: Replay các item cùng operation key
    D-->>W: Dedupe: no extra business effect
    W->>Q: Reply/ACK sau xử lý hợp lệ
    Q-->>M: Correlated reply
~~~

Sơ đồ là minh họa tình huống phát lại; giao thức ACK/reply thực tế phụ thuộc Spring Batch Integration, Spring Integration và transport đang dùng. Không giả định một reply tự động đồng nghĩa broker đã ACK hoặc manager đã cập nhật checkpoint.

### Ba mức chống lặp trong remote chunking

| Mức | Mục đích | Giới hạn |
| --- | --- | --- |
| **Transport request ID/chunk correlation** | Tránh xử lý lại vô ích cùng chunk request và nhận diện reply tương ứng | Có thể thay giữa restart; không đủ cho partial business effect |
| **Item/business operation ID** | Ngăn mỗi item gây side effect lặp | Phải tồn tại bền vững ở đích; không thể là volatile cache |
| **Manager progress/checkpoint** | Biết tiến độ đọc, chunk đã được xác nhận theo framework | Cần đồng bộ với reply và recovery; không thay thế idempotent writer |

Không tự suy định dạng `ChunkRequest`, sequence number hoặc metadata của middleware qua mọi Spring Batch version. Hãy kiểm tra đúng adapter/framework đang chạy và dùng correlation stable cho **request attempt**; dedupe **nghiệp vụ** vẫn dựa vào business operation key độc lập.

### Vì sao dedupe mỗi chunk ID là chưa đủ?

Giả sử một chunk chứa 200 payments. Worker gọi external API và 120 request đầu đã thành công trước khi crash. Nếu inbox chỉ ghi `chunk C-17 COMPLETED` **sau khi xử lý đủ 200**, redelivery sẽ bắt đầu lại cả chunk và có thể thực hiện lại 120 payment.

Ngược lại, nếu đánh dấu chunk hoàn tất **trước khi ghi mọi item**, crash có thể khiến 80 payments chưa xảy ra nhưng chunk bị bỏ qua.

Khi external effect không nằm trong một transaction atomic, cần **per-operation idempotency hoặc một state machine có reconciliation**, không chỉ một cờ boolean “chunk đã xử lý”.

### Reply trễ, reply lặp và attempt

Manager có thể nhận hai reply cho cùng request, hoặc một reply của attempt cũ đến sau khi job restart. Cần correlation tới request/attempt và kiểm tra execution hiện tại trước khi cập nhật progress. Một reply cũ không được phép làm manager của lần chạy mới hiểu nhầm rằng **công việc mới** đã hoàn tất.

## 9. Remote partitioning và parallel workers

Trong **remote partitioning**, manager tạo/chọn các worker `StepExecution` theo partition key và gửi yêu cầu thực thi worker step. Cơ chế `JobRepository` hỗ trợ phân biệt worker đã `COMPLETED` và worker cần restart.

| Định danh | Dùng ở đâu? |
| --- | --- |
| `JobInstance` + manager step + partition key | Xác định phần việc logic qua restart |
| `StepExecutionId` | Nhận diện **attempt** của worker; có thể mới sau restart |
| Business operation ID | Dedupe từng item tại database/API đích |

Nếu worker A vẫn chạy nhưng manager tưởng A mất kết nối rồi gửi cùng partition cho B, cả hai có thể ghi chồng dữ liệu. Cần kiểm soát owner/lease/fencing theo hạ tầng, đồng thời **writer idempotent tại đích**. Một lock trong bộ nhớ manager hoặc một trường `@StepScope` không đủ bảo vệ side effect xuyên JVM.

### StepScope giúp gì và không giúp gì?

`@StepScope` giúp mỗi worker `StepExecution` có reader/processor có state riêng (range ID, file, tenant). Nó tránh cross-talk từ singleton mutable khi nhiều partition chạy đồng thời, **nhưng không** bảo đảm SQL ranges không overlap và không chống hai worker khác JVM cùng ghi cùng một operation.

Nếu worker step tự chạy **multi-threaded chunks** trong cùng `StepExecution`, các thread đó có thể chia sẻ cùng scoped target reader/context; phải đánh giá thread safety/checkpoint riêng.

## 10. Replay với tác dụng phụ ngoài database

### 10.1. HTTP API có idempotency key

Nếu worker gọi API thanh toán, hãy tạo `idempotencyKey` ổn định **trước khi retry lần đầu**, thường từ business operation ID; truyền **cùng key** qua mọi retry/restart và để phía nhận lưu kết quả theo key.

~~~http
POST /payments/capture HTTP/1.1
Idempotency-Key: tenant-A:CAPTURE:PAY-1001
Content-Type: application/json

{"paymentId":"PAY-1001","amount":"100.00","currency":"USD"}
~~~

Đây là mẫu giao thức minh họa, **không phải chuẩn API chung**; tên header, lifetime key và semantics trả lại response phụ thuộc từng nhà cung cấp. Khi gặp timeout, có thể API đã hoàn tất effect nhưng response bị mất. Đừng gửi lại request với key mới; hãy tra cứu trạng thái hoặc retry bằng **đúng key và payload tương đương** theo hợp đồng API.

### 10.2. Outbox khi cần phát message

Nếu chunk ghi database và phải phát một event tiếp theo, dùng **transactional outbox**:

1. Writer ghi business row và outbox event với `eventId` bền vững trong một transaction phù hợp.
2. Dispatcher/CDC phát event sau commit.
3. Dispatcher có thể gửi lại nếu publish thành công nhưng chưa cập nhật trạng thái outbox.
4. Consumer downstream dedupe theo stable event ID/business operation ID.

Outbox bảo đảm **ý định phát sự kiện không bị quên trong DB transaction**, không hứa external consumer nhận đúng một lần.

### 10.3. File và object storage

Append trực tiếp vào cùng `output.csv` khi replay một chunk có thể tạo dòng trùng. Một thiết kế an toàn hơn:

- Ghi các object/segment với tên định danh ổn định theo `JobInstance`, partition và output segment, kết hợp checksum.
- Hoàn thiện file tạm rồi publish bằng thao tác atomic/manifest phù hợp với filesystem/object store.
- Dedupe theo business key khi gộp segment, không dựa duy nhất số byte của file.
- Không ghi đè dữ liệu hợp lệ bằng phiên bản partial khi worker cũ/worker mới cạnh tranh.

Với object storage, tính atomic của rename, overwrite, listing và conditional write **khác nhau theo provider**; phải kiểm chứng capability cụ thể. `@StepScope` không ngăn hai pod cùng dùng một object key.

### 10.4. Email và side effect không hỗ trợ idempotency

Nếu đích không có API idempotency hoặc không cho tra cứu delivery, **không thể đơn giản khẳng định exactly-once**. Có thể cần durable send ledger, outbox, trạng thái `PENDING_CONFIRMATION`, reconciliation hoặc chấp nhận mô hình at-least-once với quy trình bù. Bảo đảm thực tế phải được mô tả đúng biên hệ thống.

## 11. Không đánh đồng “duplicate hợp lệ” với xung đột dữ liệu

Một writer sử dụng `INSERT ... ON CONFLICT DO NOTHING` có thể ngăn thêm row, nhưng nếu record cùng key chứa amount khác, việc bỏ qua khiến job báo thành công dù input đã thay đổi.

### Bảng quyết định

| Input replay | Dữ liệu đích | Phản ứng đúng |
| --- | --- | --- |
| Cùng operation ID, cùng payload/ý nghĩa | Đã commit thành công | No-op, trả trạng thái thành công idempotent |
| Cùng operation ID, amount/tenant khác | Đã có row khác nội dung | **Conflict**, fail/quarantine để điều tra |
| Operation ID mới | Chưa có row | Thực thi lần đầu, commit |
| Row chưa thấy vì transaction khác đang xử lý | Đang cạnh tranh | Để unique constraint/transaction phân xử, retry có kiểm soát nếu cần |
| External side effect không rõ đã thành công hay chưa | Không có trạng thái đáng tin cậy | Reconcile; không dùng key mới hoặc tuyên bố thành công giả |
| Re-run theo business version mới có chủ đích | Key/payload cũ | Phải định nghĩa **new operation/version** rõ thay vì đánh lừa dedupe |

Đừng biến mọi `DataIntegrityViolationException` thành một skip hoặc no-op; unique violation có thể là xung đột nghiệp vụ, không đơn giản là delivery lặp.

## 12. Đo lường và đối soát sau replay

Spring Batch lưu `readCount`, `writeCount`, `skipCount`, `rollbackCount`, `commitCount` theo `StepExecution`. Đây là những chỉ số hữu ích, nhưng **không nhất thiết bằng số row mới trong database** khi writer sử dụng dedupe/upsert.

Ví dụ:

~~~text
Attempt #1: writeCount = 200 (chunk đã được framework ghi nhận)
Attempt #2: replay 50 item của cùng input, writer no-op 50 operation

Tổng writeCount qua attempts != số operation mới duy nhất.
Số operation unique cần đọc tại business store theo key.
~~~

Một `writeCount` cao không chứng minh chưa có duplicate side effect ở API ngoài; một `writeCount` thấp cũng không chứng minh data loss nếu writer đã idempotently xử lý và đối soát được.

### Các metric hữu ích

| Metric | Mục đích |
| --- | --- |
| `chunk_attempts_total` | Số lần worker nhận/xử lý yêu cầu chunk |
| `chunk_redelivery_total` | Tỷ lệ message được giao lại |
| `business_operation_inserted_total` | Số operation mới được commit |
| `business_operation_duplicate_total` | Số operation replay hợp lệ được chặn |
| `business_operation_conflict_total` | Cùng key nhưng payload khác |
| `chunk_rollback_total` / `StepExecution.rollbackCount` | Tần suất rollback/retry |
| `remote_reply_timeout_total` | Khả năng manager/worker mất đồng bộ |
| `outbox_pending_count` | Công việc phát sự kiện còn tồn |
| `reconciliation_mismatch_total` | Chênh lệch giữa input, ledger, audit và output |

Đếm **attempts** và **unique business operations** ở hai nơi khác nhau; không cộng raw counters của nhiều `JobExecution` rồi gọi đó là số bản ghi duy nhất.

### Tránh metric cardinality quá cao

`operationId`, `sourceId` và `StepExecutionId` hữu ích trong **log/tracing và audit database**, nhưng không nên gắn làm label cho mọi time series Prometheus. Thay vào đó, metric aggregate theo service, job type, partition group, outcome và reason code.

## 13. Performance: idempotency có chi phí nhưng không được bỏ

Khi mở rộng tới hàng triệu item, unique index và thao tác kiểm tra duplicate sẽ tạo overhead. Một số lựa chọn tối ưu:

| Kỹ thuật | Lợi ích | Điều kiện an toàn |
| --- | --- | --- |
| Batch insert với unique constraint | Giảm round trips | Phải xử lý conflict từng item và không bỏ qua payload khác |
| Staging table + merge | Tối ưu bulk load | Merge dựa vào stable business key, có reconciliation |
| Index đúng key truy vấn | Giảm latency nhận diện duplicate | Không bỏ tenant/namespace hoặc operation type quan trọng |
| Giảm chunk size khi writer dễ rollback | Giảm lượng rework trong một chunk | Đo overhead transaction và throughput thực |
| Tăng partition count | Tăng khả năng song song nếu còn tài nguyên | DB pool/lock/index/broker không được trở thành bottleneck |
| Dùng cache cho duplicate gần đây | Có thể tiết kiệm read khi workload hot | Cache chỉ là tối ưu, DB/service đích vẫn là nguồn chân lý |

Nếu số worker tăng nhưng unique-index lock wait tăng mạnh và throughput không cải thiện, đó là tín hiệu **bottleneck ở đích**, không phải cần tăng tiếp `gridSize`. Hãy đo CPU, DB connection pool, I/O, transaction latency, duplicate ratio và rollback rate.

### Chunk size nhỏ hay lớn hơn?

- Chunk lớn giảm số commit và overhead transaction trong điều kiện ít lỗi.
- Chunk lớn có thể tăng chi phí rollback/replay khi writer thất bại; các external effects càng khó khôi phục.
- Chunk nhỏ tăng số transaction/checkpoint và message overhead, nhưng hạn chế phạm vi công việc chưa commit.
- Không có một chunk size “tối ưu” chung; cần benchmark với **mô hình lỗi và tỷ lệ replay thực tế**.

## 14. Kiểm thử replay an toàn

Một unit test `write()` gọi hai lần chưa đủ để chứng minh an toàn sau crash: cần **transaction thật, unique constraint thật, hai connection đồng thời và fault injection**.

### 14.1. Test writer bị gọi lại sau hai transaction đã commit

Với PostgreSQL test database và `TransactionTemplate` quản lý cùng datasource:

~~~java
@Test
void ghiLaiCungOperationKhongTaoHaiLedgerRows() {
    LedgerOutput output = new LedgerOutput(
            "tenant-A", "op-1001", "snapshot-v1",
            "row-1001", "hash:payload-v1",
            new BigDecimal("125.00"));

    Chunk<LedgerOutput> chunk = new Chunk<>(List.of(output));

    transactionTemplate.executeWithoutResult(
            status -> writer.write(chunk));
    transactionTemplate.executeWithoutResult(
            status -> writer.write(chunk)); // Giả lập replay.

    Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM ledger_output "
            + "WHERE tenant_id = ? AND operation_id = ?",
            Integer.class, "tenant-A", "op-1001");

    assertEquals(1, count);
}
~~~

Ví dụ giả định `transactionTemplate`, `writer` và `jdbc` được inject trong test Spring có database/schema phù hợp; cần các import JUnit, `Chunk`, `List`, `BigDecimal`. Không đặt `@Transactional` bao quanh toàn test nếu mục tiêu là **mô phỏng hai commit độc lập**. Nên assert thêm amount, source ID, hash và không có external effect thứ hai.

### 14.2. Test rollback trước commit

~~~java
transactionTemplate.executeWithoutResult(status -> {
    writer.write(chunk);
    status.setRollbackOnly(); // Mô phỏng thất bại trước commit.
});

// Khi transaction rollback, không nên tồn tại row mới.
// Thực hiện lại trong transaction mới phải thành công.
transactionTemplate.executeWithoutResult(
        status -> writer.write(chunk));
~~~

Test này chỉ có ý nghĩa khi `writer` và `TransactionTemplate` dùng **cùng transaction manager/datasource**; phải assert row count trước và sau replay. Nếu writer có side effect HTTP, rollback database không hủy effect ấy: thêm test giả lập timeout/idempotency của API.

### 14.3. Ma trận crash-window bắt buộc

| Fault injection | Kết quả mong đợi |
| --- | --- |
| Crash trước writer | Retry xử lý bình thường, chưa có effect |
| Writer SQL thành công nhưng rollback trước commit | Database không giữ partial rows; retry tạo đúng kết quả |
| Commit DB rồi mất phản hồi với manager | Redelivery no-op theo business key; không double side effect |
| Metadata/reader checkpoint chưa advance | Item có thể được đọc lại, writer vẫn an toàn |
| Hai worker nhận cùng operation đồng thời | Unique constraint chặn bản ghi thứ hai; không có lost update |
| Cùng operation ID nhưng payload khác | Conflict được phát hiện, không im lặng bỏ qua |
| Một chunk có item hợp lệ và item sai | Transaction/retry/skip giữ đúng các item hợp lệ |
| Source snapshot thay đổi giữa restart | Phát hiện input drift; không dùng checkpoint cũ cho phạm vi mới |
| Remote chunk request redelivery | Chunk reply/correlation đúng, business effects chỉ một lần |
| Reply cũ đến sau restart | Không cập nhật sai attempt hiện tại |
| Worker remote cũ còn chạy khi worker mới bắt đầu | Fencing/transaction/idempotency không tạo effect lặp |
| Outbox dispatcher publish lại | Consumer downstream dedupe event ID |
| HTTP timeout sau khi server đã xử lý | Retry cùng key hoặc reconcile, không charge hai lần |
| TTL dedupe hết trước khi DLQ replay | Business ledger/constraint vẫn bảo vệ operation |

### 14.4. Test concurrency đúng cách

Cho hai `ExecutorService` task hoặc hai worker processes cùng gọi writer với **một `operationId`** dưới hai transaction riêng. Sử dụng latch để cho chúng đến gần cùng lúc; chỉ một row được commit. Test trên database thật cùng loại production có ý nghĩa hơn một mock `Map`.

Không test bằng một `synchronized` service singleton rồi kết luận an toàn nhiều JVM. Cần chứng minh **unique constraint ở DB** hoặc idempotency API đích là hàng rào cuối cùng.

### 14.5. Integration test với Spring Batch

Một integration test đáng tin cậy nên:

1. Chuẩn bị input snapshot bất biến với tập operation IDs dự kiến.
2. Cấu hình reader restartable, writer idempotent, `JobRepository` và transaction manager đúng.
3. Gây lỗi có chủ đích sau một số chunk commit, xác minh trạng thái `JobExecution`/`StepExecution` và checkpoint.
4. Restart **cùng JobInstance**; giữ partition key → input range, không đổi identifying parameters.
5. Đối soát ledger: **mỗi operation một row**, các amount/hash hợp lệ, không thiếu item hoặc duplicate effect.
6. Với remote setup, giả lập redelivery/reply-loss và kiểm tra broker ACK/correlation theo adapter thật.

**Không** chỉ assert `BatchStatus.COMPLETED` hoặc cộng `writeCount`: chúng không chứng minh toàn bộ side effects đúng một lần.

## 15. Runbook khi nghi ngờ chunk bị replay sai

1. **Khoanh vùng:** Xác định `JobInstance`, `JobExecution`, `StepExecutionId`, partition key, input version, chunk/request correlation và business operation IDs.
2. **Kiểm tra sự cố:** Có rollback, timeout, broker redelivery, manager reply timeout, pod crash hoặc DB failover không?
3. **Đọc metadata:** Kiểm tra `StepExecution` status, commit/rollback counts và `ExecutionContext` checkpoint; không sửa metadata thủ công.
4. **Kiểm tra business store:** Unique operation key có thực sự tồn tại? Có row trùng hoặc conflicting payload không?
5. **Kiểm tra transaction:** Business data và metadata có dùng chung transaction phù hợp? API ngoài có hỗ trợ idempotency không?
6. **Đối chiếu hệ thống message:** Request đã ACK chưa, reply có đến trễ/lặp, outbox có pending hoặc DLQ message cần xử lý không?
7. **Kiểm tra concurrent owners:** Worker cũ đã dừng chưa? Có lease/fencing hoặc multiple manager instances cùng điều phối không?
8. **Đối soát input–output:** So sánh tập operation IDs nguồn và ledger, trạng thái quarantine/filter/pending, tổng tiền/checksum khi nghiệp vụ yêu cầu.
9. **Khôi phục an toàn:** Không xóa unique key/inbox để “chạy lại từ đầu”. Với external effect không rõ, tra cứu trạng thái và quyết định replay/compensate dựa trên bằng chứng.
10. **Bổ sung phòng ngừa:** Kiểm thử crash window tương ứng, cập nhật idempotency retention, monitoring, backpressure và runbook.

### Dấu hiệu cần ưu tiên dừng/publish gate

Nếu xuất hiện cùng `operationId` nhưng khác amount, ledger và manager status mâu thuẫn, hoặc API thanh toán chưa xác định đã commit hay chưa, không nên tiếp tục publish dữ liệu như thể mọi chunk đã hoàn tất. Cần staging/reconciliation và kiểm tra thủ công theo mức độ rủi ro.

## 16. Bài tập tình huống

Một job nhập 3 triệu giao dịch chia thành 12 partition. Mỗi worker sử dụng `chunk(200)` và viết vào database A; đồng thời gọi API chuyển tiền ở database/service B. Manager dùng remote chunking để điều phối. Trong một chunk, worker đã ghi 180 giao dịch thành công ở service B, rồi mất kết nối trước khi gửi reply. Manager gửi lại chunk; writer kiểm tra `StepExecutionId` để dedupe, nhưng restart tạo `StepExecutionId` khác. Kết quả một số khách hàng bị chuyển tiền hai lần.

**Câu hỏi:**

1. Vì sao `StepExecutionId` không đủ làm idempotency key cho chuyển tiền?
2. Chỉ đánh dấu `chunk C-17 COMPLETED` có giải quyết được 180 tác dụng phụ đã xảy ra trước crash không?
3. Vì sao transaction của database A không tự rollback các khoản đã chuyển ở service B?
4. Khóa nào nên gửi đến API chuyển tiền và phải giữ ổn định qua các lượt nào?
5. Nếu API không hỗ trợ idempotency, nên xử lý trường hợp timeout chưa rõ trạng thái như thế nào?
6. Những phép đo/test nào chứng minh giải pháp đã an toàn?

**Định hướng trả lời:** `StepExecutionId` là identity của **attempt**, không phải **business operation**. Chỉ dedupe chunk có thể bỏ sót partial effects hoặc replay chúng. Hai hệ thống không tự tham gia cùng transaction atomic; cần **business operation ID bền vững** ở API nhận, giữ nguyên qua mọi retry/redelivery/restart. Khi API không hỗ trợ idempotency, phải dùng ledger trạng thái, đối soát theo reference ID và quy trình xác nhận/bù trước khi gửi lại. Test commit-before-reply-loss, partial chunk, concurrent requests, restart ID mới và tổng giao dịch thực tế tại service B.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời read/process/write và commit chunk.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, checkpoint và restart.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong fault-tolerant chunk processing.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và throughput.
- [Spring Batch Reference — Remote Chunking](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-chunking.html): manager/worker request–reply.
- [Spring Batch Reference — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): worker StepExecution ở xa.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): execution metadata và JobRepository.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và proxy.
- [PostgreSQL Documentation — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): atomic uniqueness và conflict handling.

> **Ghi nhớ:** **Replay chunk an toàn không có nghĩa chunk chỉ chạy một lần.** Nghĩa là **mọi lần chạy lại đều bảo toàn cùng kết quả nghiệp vụ**. Hãy cố định business operation ID, sử dụng unique constraint hoặc idempotency ở đích, kiểm tra payload conflict, hiểu ranh giới transaction/checkpoint, ACK/reply sau commit và kiểm thử crash window, restart và concurrency trên hạ tầng thật.
