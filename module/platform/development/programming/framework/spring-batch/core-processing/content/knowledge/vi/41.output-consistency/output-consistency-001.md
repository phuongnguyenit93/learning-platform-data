# Output được tạo một lần hay nhiều lần

Trong Spring Batch, một job có thể đọc item, xử lý rồi ghi kết quả ra database, file, message broker hoặc API bên ngoài. Một câu hỏi quan trọng khi vận hành batch là: **một kết quả nghiệp vụ được tạo đúng một lần hay có thể được tạo nhiều lần?**

Không thể trả lời câu hỏi này chỉ bằng cách nhìn vào số lần `ItemWriter.write()` được gọi. Chunk có thể rollback, step có thể retry, job có thể restart sau khi process chết, hoặc writer có thể gửi output thành công nhưng lỗi xảy ra trước khi checkpoint được lưu. Khi đó cùng một item có thể đi qua một phần pipeline nhiều lần.

Spring Batch cung cấp checkpoint, transaction và retry để kiểm soát tiến độ xử lý. Những cơ chế này giúp job phục hồi sau lỗi, nhưng không tự bảo đảm mọi side effect bên ngoài chỉ xảy ra đúng một lần. Muốn output có hiệu ứng nghiệp vụ một lần, cần thiết kế transaction boundary, identity của output, idempotency và cơ chế recovery phù hợp với từng loại đích ghi.

## “Một lần” có thể mang nhiều ý nghĩa

Trước khi thiết kế, cần phân biệt số lần thực thi kỹ thuật với kết quả nghiệp vụ cuối cùng.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Một lần gọi | Một method như `write()` hoặc API publish được gọi một lần |
| Một lần thử (attempt) | Một lần thực hiện thao tác; retry tạo attempt tiếp theo |
| Một lần commit | Một transaction được commit thành công |
| Một output vật lý | Một row, file, message hoặc request thực sự được tạo/gửi |
| Một hiệu ứng nghiệp vụ | Trạng thái nghiệp vụ cuối cùng chỉ phản ánh một lần xử lý logic |

Một writer có thể được gọi nhiều lần nhưng database vẫn chỉ có một row nếu dùng unique key và thao tác idempotent. Ngược lại, writer chỉ được gọi một lần trong log ứng dụng nhưng message có thể đã được broker nhận, rồi client timeout khiến trạng thái kết quả không xác định.

Vì vậy, mục tiêu thực tế thường là **một hiệu ứng nghiệp vụ**, kể cả khi hệ thống phải thực hiện nhiều attempt kỹ thuật. Đây là cách tiếp cận quan trọng với batch có retry và restart.

## Vì sao output có thể được tạo nhiều lần?

Một chunk-oriented step thường đọc và xử lý một nhóm item, sau đó gọi writer trong transaction. Khi có lỗi, Spring Batch có thể rollback và thực hiện lại một phần công việc theo cấu hình. Một số side effect đã xảy ra trước lỗi có thể không rollback được.

Các nguyên nhân phổ biến:

- Writer đã ghi/gửi output nhưng chunk transaction rollback.
- Writer gửi bất đồng bộ rồi trả về trước khi biết kết quả; lỗi chỉ xuất hiện sau đó.
- Broker đã nhận message nhưng acknowledgement bị mất hoặc timeout.
- Process chết sau khi đích ghi nhận output nhưng trước khi checkpoint được commit.
- Job restart đọc lại item chưa được checkpoint.
- Người vận hành launch một `JobInstance` mới với cùng tập input và tạo lại output.
- Processor, listener hoặc service thực hiện side effect và bị gọi lại khi retry.
- Hai job execution cùng xử lý một tập input vì không có cơ chế claim/lock.

Ví dụ một step xử lý 100 đơn hàng:

```text
Chunk 1: đọc 100 item
    |
    v
Processor xử lý các item
    |
    v
Writer gửi 100 message
    |
    +--> broker nhận message
    |
    v
Lỗi xảy ra trước khi tiến độ chunk được xác nhận
    |
    v
Rollback / retry / restart
    |
    v
Cùng các item được gửi lại
```

Nếu broker không tham gia cùng transaction có thể rollback, các message lần đầu vẫn tồn tại. Lần gửi lại tạo duplicate. Đây không nhất thiết là bug của Spring Batch; đó là hệ quả của việc side effect nằm ngoài transaction được quản lý.

## Chunk transaction và checkpoint

Trong chunk processing, Spring Batch đọc item, gọi processor nếu có, rồi truyền các output hợp lệ tới writer. Sau khi chunk được xử lý, framework cập nhật tiến độ và hoàn tất transaction theo cấu hình step.

Mô hình khái quát:

```text
Chunk transaction
    |
    +--> read items
    +--> process items
    +--> writer.write(chunk)
    +--> update checkpoint / execution state
    |
    v
Commit
```

Chi tiết callback và thời điểm cập nhật metadata phụ thuộc loại step, transaction manager và cấu hình repository. Điều quan trọng là business output và checkpoint chỉ được atomic nếu chúng thực sự tham gia cùng một transaction có thể commit/rollback chung.

### Khi business output và checkpoint cùng transaction

Nếu writer ghi vào database và `JobRepository` dùng cùng transactional resource cùng transaction manager được cấu hình đúng, business write và cập nhật metadata có thể commit trong cùng transaction. Khi transaction rollback, cả hai phần được rollback; khi commit, cả hai cùng được xác nhận.

Đây là tình huống thuận lợi để tránh cửa sổ lỗi giữa business output và checkpoint. Tuy nhiên, phải kiểm tra cấu hình thực tế: dùng cùng một `DataSource` object hay cùng database chưa đủ để chứng minh hai thao tác tham gia cùng transaction. Transaction manager, connection binding và repository configuration phải phối hợp đúng.

### Khi business output và checkpoint dùng resource khác nhau

Nếu writer ghi database A còn `JobRepository` ghi database B, hoặc writer gửi file/message/HTTP, một local transaction thường không thể commit atomic cả hai resource.

Ví dụ:

```text
Business database                 JobRepository
       |                                |
       +--> ghi output                  +--> ghi checkpoint
                \                      /
                 \                    /
                  Hai resource độc lập
```

Một resource có thể commit trong khi resource kia thất bại. Nếu output đã commit nhưng checkpoint chưa được lưu, restart có thể thực hiện output lần nữa. Nếu checkpoint được xác nhận nhưng output thất bại và writer không báo lỗi đúng cách, item có thể bị bỏ qua.

Không suy ra tính atomic chỉ từ việc cả hai thao tác được gọi trong cùng một method `write()` hoặc cùng một step.

## Restart có thể tạo output lần nữa

`JobRepository` lưu `JobExecution`, `StepExecution` và `ExecutionContext` để Spring Batch biết job đã đi tới đâu. Khi job thất bại, restart đúng `JobInstance` có thể tiếp tục từ checkpoint đã commit.

Tuy nhiên, checkpoint chỉ đại diện cho tiến độ mà framework đã lưu. Nếu output đã được đích bên ngoài chấp nhận nhưng checkpoint chưa được xác nhận, item có thể được xử lý lại sau restart.

Ví dụ:

1. Reader lấy item `O-100`.
2. Writer gửi message `OrderProcessed(O-100)`.
3. Broker nhận message.
4. Process bị dừng trước khi step lưu checkpoint tương ứng.
5. Job được restart và đọc lại `O-100`.
6. Writer gửi cùng message lần nữa.

Broker có thể chứa hai message cho cùng một event nghiệp vụ. Consumer cần deduplicate hoặc producer phải dùng một cơ chế transaction phù hợp.

### Restart cùng JobInstance và launch JobInstance mới

Hai tình huống này khác nhau:

- **Restart:** tiếp tục một `JobInstance` đã thất bại, với cùng identifying `JobParameters` và state tương ứng.
- **Launch mới:** tạo `JobInstance` mới, thường do identifying parameters thay đổi hoặc có run identifier mới.

Một job chạy thành công rồi được launch lại như một instance mới có thể xử lý toàn bộ input từ đầu. Spring Batch không thể tự biết đó là lần chạy lại không mong muốn nếu business identity của batch không được mô hình hóa.

Nếu một tập input chỉ được xử lý một lần về mặt nghiệp vụ, hãy có `batchId`, source file ID, event ID hoặc business key để nhận diện lần xử lý. Không dựa riêng vào `JobExecutionId`, vì mỗi lần execution có ID mới.

## Retry trong cùng một step

Khi step được cấu hình fault tolerance, exception có thể khiến processor hoặc writer được gọi lại theo retry policy. Retry có thể diễn ra trước khi step fail hoàn toàn.

Ví dụ:

```java
return new StepBuilder("publishStep", jobRepository)
        .<OrderEvent, OrderEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(eventProcessor)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .build();
```

Nếu writer đã gửi một phần chunk rồi ném exception, Spring Batch có thể thử lại theo retry semantics của step. Message đã gửi trước lỗi có thể vẫn còn ở broker. Nếu writer gửi một số record thành công rồi một record thất bại, retry toàn bộ thao tác có thể phát lại các record thành công trước đó.

Với database writer tham gia transaction chunk, các row write trong transaction bị rollback có thể được thực hiện lại mà không để lại row trùng. Với file, message broker hoặc HTTP API, side effect thường không tự rollback cùng transaction database.

### Processor cũng có thể chạy lại

Processor nên tập trung vào transformation và validation. Nếu processor gửi email, tạo payment, gọi API thay đổi trạng thái hoặc ghi database ngoài transaction, retry có thể lặp side effect đó.

Không đặt side effect không idempotent trong processor chỉ vì method `process()` trông như được gọi một lần cho mỗi item. Trong fault-tolerant step, item có thể được xử lý lại. Hãy chuyển side effect sang writer hoặc một workflow có idempotency/outbox rõ ràng.

### Listener cũng có thể tạo side effect lặp

Các listener như `ItemWriteListener`, `ChunkListener` và `StepExecutionListener` hữu ích cho logging, metrics và audit. Tuy nhiên, callback có thể được gọi trong những đường retry, rollback hoặc restart khác nhau. Không dùng listener để gửi notification quan trọng nếu chưa có idempotency hoặc durable event record.

Logging cùng một event nhiều lần thường chấp nhận được; tạo invoice, gửi email hoặc cập nhật hệ thống ngoài nhiều lần có thể không chấp nhận được.

## Exactly-once, at-least-once và at-most-once

Khi nói về output một lần hay nhiều lần, cần xác định delivery semantics.

| Semantics | Đặc điểm | Hệ quả |
| --- | --- | --- |
| At-most-once | Một output có thể được thử tối đa một lần theo policy | Có thể mất output nếu lỗi xảy ra trước khi đích nhận |
| At-least-once | Hệ thống retry cho tới khi có xác nhận phù hợp | Có thể tạo duplicate; cần idempotency |
| Exactly-once effect | Dù có nhiều attempt, business effect chỉ được áp dụng một lần | Cần identity/deduplication hoặc transaction phối hợp |
| Exactly-once delivery | Một message chỉ được giao đúng một lần tới consumer | Rất khó bảo đảm end-to-end khi có crash/retry; phải xác định rõ phạm vi broker |

Trong hệ thống phân tán, “exactly once” thường chỉ có ý nghĩa trong một phạm vi transaction hoặc broker cụ thể. Kafka transactional producer có thể cung cấp exactly-once semantics cho các thao tác Kafka trong phạm vi được cấu hình, nhưng không tự làm một database update và một HTTP call trở thành một transaction duy nhất.

Một mục tiêu thực tế là at-least-once delivery kết hợp idempotent consumer/writer, từ đó đạt exactly-once business effect trong phạm vi dữ liệu được kiểm soát.

## Idempotency: nhiều attempt nhưng một kết quả

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một input mà trạng thái cuối không thay đổi sau lần đầu.

Ví dụ cập nhật trạng thái:

```sql
UPDATE orders
SET status = 'PUBLISHED'
WHERE order_id = :orderId
  AND status <> 'PUBLISHED';
```

Chạy lại câu lệnh không tạo thêm một row mới. Tuy nhiên, cần kiểm tra business semantics: nếu mỗi lần update tạo trigger/audit record hoặc phát event khác, side effect phụ vẫn có thể lặp.

### Idempotency key

Mỗi output nghiệp vụ nên có một identity ổn định, ví dụ:

- `eventId` cho message.
- `paymentRequestId` cho lệnh thanh toán.
- `invoiceId` cho hóa đơn.
- `sourceRecordId + operationType` cho kết quả batch.
- `batchId + businessKey` cho output của một batch.

Idempotency key phải được tạo trước hoặc xác định từ dữ liệu bền vững, rồi giữ nguyên qua retry/restart. Không tạo UUID mới mỗi lần writer được gọi cho cùng một logical output.

### Unique constraint chống insert trùng

Một unique constraint ở database là hàng rào mạnh để ngăn hai execution tạo cùng một output:

```sql
CREATE TABLE processed_order (
    order_id VARCHAR(50) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL,
    result_code VARCHAR(30) NOT NULL
);
```

Writer có thể dùng insert với conflict handling theo dialect database. Ví dụ PostgreSQL:

```sql
INSERT INTO processed_order(order_id, processed_at, result_code)
VALUES (:orderId, :processedAt, :resultCode)
ON CONFLICT (order_id) DO NOTHING;
```

`ON CONFLICT` là cú pháp riêng của PostgreSQL. Với Oracle, SQL Server, MySQL hoặc database khác, dùng cú pháp/chiến lược tương ứng. Unique constraint mới là bảo vệ cuối cùng trước race condition; chỉ kiểm tra `SELECT` trước khi `INSERT` không đủ an toàn khi hai job chạy đồng thời.

Nếu duplicate cần được phân biệt với output đã tồn tại nhưng có nội dung khác, hãy đọc và so sánh checksum/version hoặc dùng upsert có điều kiện. Không bỏ qua mọi duplicate một cách im lặng nếu chúng có thể chỉ ra dữ liệu nguồn xung đột.

## Ghi database: transaction và unique business key

Database là nơi dễ đạt output một lần nhất khi business writer và checkpoint cùng tham gia một transaction phù hợp. Nếu cùng transaction rollback, row chưa commit sẽ không tồn tại; khi retry, insert được thực hiện lại.

Tuy nhiên, cần xử lý các tình huống:

- Writer và `JobRepository` dùng cùng transactional resource hay khác nhau?
- Có nhiều job instance cùng xử lý một business key không?
- Writer có ghi vào database khác với repository không?
- Có trigger hoặc stored procedure tạo side effect ngoài transaction không?
- Unique key đại diện đúng một logical output hay chỉ một input record?

Ví dụ `JdbcBatchItemWriter`:

```java
@Bean
JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO processed_order(
                        order_id, processed_at, result_code)
                    VALUES (:orderId, :processedAt, :resultCode)
                    """)
            .beanMapped()
            .assertUpdates(false)
            .build();
}
```

Đoạn code minh họa mapping; nếu cần idempotency, SQL phải có unique constraint và chính sách duplicate phù hợp. `assertUpdates(false)` chỉ thay đổi cách writer phản ứng với số row update; nó không tự biến insert thành idempotent. Hãy dùng SQL upsert/ignore conflict đúng dialect và kiểm tra kết quả theo yêu cầu nghiệp vụ.

### Upsert có thể ghi đè kết quả mới hơn

Một câu upsert đơn giản có thể khiến lần retry cũ ghi đè dữ liệu được tạo bởi lần xử lý mới. Nếu output có version hoặc timestamp, chỉ cập nhật khi incoming version phù hợp. Idempotency phải bảo toàn semantics, không chỉ tránh exception duplicate key.

## Gửi message: acknowledgement không đồng nghĩa exactly-once

Khi gửi message tới Kafka, JMS hoặc RabbitMQ, producer thường nhận một acknowledgement/confirm theo semantics broker. Nếu acknowledgement không đến do network timeout, producer không biết chắc broker đã nhận hay chưa.

```text
Producer gửi event
       |
       v
Broker nhận và lưu event
       |
       +--> acknowledgement bị mất trên network
       |
       v
Producer timeout
       |
       v
Batch retry gửi lại event
```

Broker có thể chứa hai bản sao. Vì vậy:

- Dùng event ID ổn định qua mọi attempt.
- Cấu hình producer retry/idempotence theo khả năng broker.
- Chờ acknowledgement theo policy trước khi writer trả về.
- Consumer deduplicate event ID trong transaction với business update.
- Không coi producer acknowledgement là bằng chứng consumer đã xử lý.

Kafka producer idempotence giảm duplicate do retry nội bộ của một producer session theo semantics Kafka. Nó không tự chống duplicate do Spring Batch restart và tạo một lần publish mới với cùng event.

## Transactional Outbox

Transactional outbox là pattern phổ biến khi một transaction database vừa cập nhật dữ liệu nghiệp vụ vừa cần phát message. Thay vì publish trực tiếp trong transaction đó, ứng dụng ghi một outbox row cùng transaction với business update.

```text
Business chunk transaction
    |
    +--> UPDATE orders
    +--> INSERT outbox_event (event_id, payload, PENDING)
    +--> COMMIT
             |
             v
       Outbox publisher step
             |
             +--> read/claim pending event
             +--> publish to broker
             +--> wait for acknowledgement
             +--> mark published
```

Nếu transaction business rollback, outbox row cũng rollback. Nếu commit, ý định phát event được lưu bền vững. Broker tạm unavailable không làm mất event; publisher có thể thử lại ở execution sau.

### Outbox vẫn có thể publish nhiều lần

Giả sử broker đã nhận message nhưng publisher chết trước khi cập nhật `published_at`. Lần chạy tiếp theo thấy row vẫn pending và gửi lại. Đây là at-least-once publish có chủ đích.

Để business effect chỉ xảy ra một lần:

1. Giữ `event_id` ổn định trong outbox row.
2. Consumer lưu event ID đã xử lý trong inbox/processed-message table.
3. Consumer ghi inbox và business update trong cùng transaction.
4. Khi nhận event trùng, consumer bỏ qua business effect đã hoàn tất và acknowledge theo policy.

Outbox giải quyết tính nhất quán giữa business update và việc lưu ý định phát event; inbox/idempotency giải quyết duplicate ở consumer.

## Inbox và deduplication ở consumer

Một consumer có thể nhận cùng message nhiều lần do broker redelivery hoặc producer retry. Inbox pattern lưu ID message đã xử lý để ngăn business update lặp.

Ví dụ schema:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer xử lý theo transaction:

```text
Begin transaction
    |
    +--> Insert eventId vào processed_message
    |       |
    |       +--> unique key mới: tiếp tục
    |       +--> đã tồn tại: bỏ qua business effect
    |
    +--> cập nhật dữ liệu nghiệp vụ
    |
Commit transaction
    |
Broker acknowledgement
```

Nếu business update thất bại, transaction rollback cả inbox insert. Message được redeliver và có thể xử lý lại. Nếu inbox insert commit trước business update trong transaction khác, hệ thống có thể đánh dấu event đã xử lý dù business effect chưa hoàn thành; tránh thiết kế đó.

Deduplication table cần retention đủ dài để bao phủ cửa sổ replay. Nếu xóa inbox record quá sớm, một message cũ được replay có thể tạo business effect lần nữa.

## File output và khả năng tạo file nhiều lần

File writer có side effect khác database. Filesystem thường không tham gia transaction database của chunk. Một file có thể đã được ghi bytes nhưng checkpoint chưa commit; restart có thể ghi lại dữ liệu hoặc file bị nối thêm/truncate tùy cấu hình.

Khi dùng `FlatFileItemWriter`, cần xác định rõ:

- File output được tạo mới hay append?
- Nếu file đã tồn tại khi launch mới, có ghi đè không?
- Khi restart cùng execution, writer có khôi phục vị trí/checkpoint không?
- File có được publish cho consumer trước khi job hoàn tất không?
- Có thể để consumer đọc file dở dang không?

### Ghi vào file tạm rồi publish

Một pattern an toàn là ghi vào file staging riêng cho execution, sau đó chỉ công bố file khi job hoàn tất:

```text
Job bắt đầu
    |
    v
orders-batch-20261115.tmp
    |
    +--> ghi theo chunk và checkpoint
    |
    v
Job hoàn tất và xác nhận file đầy đủ
    |
    v
rename / publish thành orders-batch-20261115.csv
```

Consumer chỉ đọc file có tên final hoặc manifest đánh dấu hoàn tất. Nếu job restart, tiếp tục file tạm của cùng logical batch. Nếu launch mới, dùng output identity mới hoặc kiểm tra manifest để không ghi đè nhầm file đã publish.

Rename có thể atomic trong cùng filesystem nhưng không phải mọi filesystem/object storage đều bảo đảm. Với object storage, thường cần upload object bất biến rồi ghi manifest/marker cuối cùng. Không coi rename/marker là atomic nếu storage không hỗ trợ.

### File name phải có identity ổn định

Không dùng timestamp hiện tại hoặc random suffix mới ở mỗi retry nếu cùng logical output cần được tiếp tục. Tạo output key từ `batchId`, source version hoặc business date theo contract. Tách identity của logical batch khỏi `JobExecutionId`, vì restart có execution ID mới.

## HTTP API và dịch vụ bên ngoài

Gọi HTTP API trong writer cũng có thể tạo duplicate. Ví dụ API tạo invoice nhận request thành công, nhưng response bị mất. Batch không biết invoice đã được tạo và retry request.

Nếu API hỗ trợ idempotency key:

```http
POST /invoices
Idempotency-Key: invoice:ORDER-100:2026-11
Content-Type: application/json
```

Server lưu kết quả theo key và trả lại kết quả cũ khi nhận request trùng trong thời gian retention. Key phải đại diện cho một logical operation; không dùng key mới cho mỗi attempt.

Nếu API không hỗ trợ idempotency:

- Tìm API tra cứu theo business key trước khi tạo lại, nếu quy trình cho phép.
- Dùng một bảng request/outbox bền vững để theo dõi trạng thái và reconcile.
- Thiết kế operation theo kiểu PUT/upsert nếu semantics phù hợp.
- Ghi lại response/reference khi thành công.
- Có quy trình điều tra outcome unknown sau timeout.

Không tự retry một `POST` tạo resource nếu chưa hiểu API có idempotent hay không. HTTP timeout không chứng minh server chưa thực hiện request.

## Output consistency với nhiều job chạy đồng thời

Ngay cả khi một job không retry, hai execution cùng đọc một input có thể tạo output trùng. Đây là vấn đề concurrency và ownership.

Các cơ chế thường dùng:

- Unique constraint trên business key/output ID.
- Claim input bằng trạng thái hoặc lease trong database.
- Partition input thành tập không giao nhau.
- Lock theo batch/business key nếu cần.
- Idempotent writer và consumer.
- Kiểm tra `JobInstance` identity và ngăn launch trùng theo business batch.

Không chỉ kiểm tra “job đang chạy hay không” ở tầng scheduler nếu có thể có nhiều node hoặc nhiều scheduler. Quyết định claim phải được lưu ở resource chia sẻ có atomicity phù hợp.

### Claim input bằng trạng thái

Một pattern là chuyển record từ `READY` sang `IN_PROGRESS` trong transaction claim, gắn `batch_id`/owner và lease. Worker chỉ xử lý record đã claim cho batch đó. Sau khi output hoàn tất, cập nhật `DONE`; khi worker chết, lease hết hạn cho phép recovery.

Lease không loại bỏ duplicate hoàn toàn: worker cũ có thể vẫn hoạt động sau khi lease hết hạn và worker mới claim lại. Dùng fencing token/version hoặc idempotent output để ngăn worker cũ ghi kết quả không hợp lệ.

## Processor, writer và listener: đặt side effect ở đâu?

Mỗi thành phần có vai trò khác nhau:

| Thành phần | Vai trò phù hợp | Lưu ý về output lặp |
| --- | --- | --- |
| `ItemReader` | Đọc item và khôi phục vị trí | Reader có thể đọc lại item sau restart tùy checkpoint |
| `ItemProcessor` | Validation và transformation | Có thể được gọi lại; tránh side effect không idempotent |
| `ItemWriter` | Ghi output của chunk | Có thể retry; thiết kế transaction/idempotency |
| `ItemWriteListener` | Quan sát sự kiện write | Không giả định callback là nơi publish đúng một lần |
| `ChunkListener` | Quan sát ranh giới chunk | Side effect có thể lặp qua rollback/retry |
| `StepExecutionListener` | Quan sát lifecycle step | `afterStep` không phải distributed commit hook |

Đặt business output ở writer hoặc một bước publish có trạng thái bền vững. Processor nên tạo dữ liệu đầu ra, không nên trực tiếp thực hiện các hành động không thể rollback.

Listener phù hợp cho metrics, logging và audit có thể deduplicate. Nếu cần gửi notification sau khi business transaction commit, hãy dùng outbox hoặc cơ chế after-commit có lưu trữ bền vững; chỉ gọi trong `afterStep` không bảo đảm không lặp khi job được launch lại.

## Asynchronous writer và output chưa xác nhận

Một writer có thể gửi message/API bất đồng bộ. Nếu `write()` trả về ngay sau khi enqueue future mà không chờ kết quả, Spring Batch có thể coi chunk đã hoàn tất trong khi send vẫn đang pending.

Điều này tạo hai vấn đề:

- Send thất bại sau khi checkpoint đã tiến lên: output bị mất khỏi góc nhìn batch.
- Process chết khi future chưa hoàn tất: outcome không xác định; không biết broker đã nhận hay chưa.

Nếu output là điều kiện bắt buộc của chunk, writer phải chờ acknowledgement/confirm theo policy trước khi trả về hoặc sử dụng transaction/resource integration được hỗ trợ. Khi gửi song song nhiều message, giới hạn số future in-flight và chờ toàn bộ kết quả; nếu một số thành công trước khi một số khác thất bại, vẫn phải xử lý duplicate khi retry.

Không nuốt exception trong callback và không ghi log rồi tiếp tục như thành công. Spring Batch chỉ có thể retry/fail nếu writer truyền lỗi ra ngoài.

## Skip có thể làm output không được tạo

Retry tập trung vào thử lại; skip cho phép bỏ qua item sau khi vượt policy. Nếu một item bị skip ở writer, output tương ứng có thể không được tạo. Điều đó có thể đúng nếu dữ liệu lỗi được reject theo nghiệp vụ, nhưng nguy hiểm nếu exception thực chất là broker outage.

Nếu dùng skip:

- Chỉ skip lỗi có thể chấp nhận bỏ qua.
- Ghi reject record bền vững với business key và nguyên nhân.
- Theo dõi skip count và cảnh báo khi vượt ngưỡng.
- Không skip lỗi tạm thời của broker chỉ để job thành công.
- Có quy trình sửa dữ liệu và replay item bị reject.

`SkipListener` có thể ghi nhận item bị skip, nhưng side effect của listener cũng cần idempotency và transaction boundary rõ ràng.

## Exactly-once effect với database writer

Để đạt một business effect cho mỗi logical output, có thể kết hợp:

1. Một output ID ổn định.
2. Unique constraint hoặc upsert có điều kiện.
3. Business write và checkpoint trong cùng transaction nếu kiến trúc hỗ trợ.
4. Claim input để ngăn nhiều execution xử lý trùng.
5. Reconciliation để phát hiện input chưa có output hoặc output không có input tương ứng.

Ví dụ, bảng output có `source_record_id` duy nhất. Khi writer được gọi lại, insert duplicate không tạo row thứ hai. Nếu output cần được cập nhật, dùng version hoặc compare-and-set để không ghi đè trạng thái mới hơn.

Exactly-once effect là thuộc tính của toàn bộ quy trình dữ liệu, không phải một annotation hay một method của Spring Batch.

## Kiểm tra output sau job

Một job `COMPLETED` không tự chứng minh output không duplicate hoặc đủ dữ liệu. Cần kiểm tra invariant nghiệp vụ.

Ví dụ:

- Mỗi source record bắt buộc có đúng một output với business key tương ứng.
- Không có hai output cùng `eventId` trong phạm vi logical batch.
- Số record `DONE` cộng số record `REJECTED` bằng số record đã claim, nếu đó là contract.
- Mọi outbox event cần publish đều ở trạng thái `PUBLISHED` hoặc trạng thái lỗi có thể điều tra.
- File final có manifest/checksum và record count mong đợi.
- Consumer inbox cho thấy mỗi event ID chỉ tạo một business effect.

Đối soát nên dựa trên key và trạng thái bền vững, không chỉ so sánh tổng số item đọc và ghi. Filter, skip, retry và reject có thể khiến các counters khác nhau theo thiết kế.

## Ví dụ thiết kế idempotent output

Giả sử job tạo một kết quả xử lý cho mỗi đơn hàng. Tạo output key từ `orderId` và loại operation:

```java
public record ProcessedOrder(
        String orderId,
        String operation,
        BigDecimal total,
        String resultCode) {

    public String outputId() {
        return operation + ":" + orderId;
    }
}
```

Database đặt unique constraint trên `output_id`:

```sql
CREATE TABLE order_output (
    output_id VARCHAR(120) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    result_code VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Writer dùng câu lệnh insert/upsert theo dialect. Khi cùng output được thử lại, database nhận diện cùng `output_id`. Nếu nội dung mới khác nội dung đã ghi, ứng dụng cần quyết định đó là retry hợp lệ, conflict hay version mới; không ghi đè vô điều kiện.

Đối với message, dùng cùng `outputId` làm event ID hoặc idempotency key. Consumer lưu key đó trong inbox trước khi áp dụng business effect.

## Kiểm thử output một lần hay nhiều lần

Test cần mô phỏng failure window, không chỉ test trường hợp thành công bình thường.

### Kiểm thử retry writer

Tạo writer test double đếm số lần gọi và thất bại có chủ đích. Xác nhận Spring Batch retry đúng số lần. Đồng thời kiểm tra output store chỉ có một logical result nếu writer được thiết kế idempotent.

### Kiểm thử rollback sau output

Tạo writer gửi message thành công rồi làm một thao tác trong chunk thất bại. Xác nhận database rollback nhưng message ngoài transaction có thể vẫn tồn tại. Sau restart/retry, xác nhận duplicate được deduplicate bằng event ID.

### Kiểm thử crash giữa output và checkpoint

Mô phỏng process/job failure sau khi đích ghi nhận output nhưng trước khi checkpoint được xác nhận. Restart cùng `JobInstance` và kiểm tra output không tạo business effect thứ hai.

### Kiểm thử launch mới cùng input

Chạy một job thành công, sau đó launch một `JobInstance` mới với cùng input/business batch. Xác nhận unique business key, batch claim hoặc idempotency policy ngăn tạo output trùng nếu nghiệp vụ yêu cầu chỉ xử lý một lần.

### Kiểm thử hai execution đồng thời

Khởi chạy hai execution cùng xử lý một tập input. Xác nhận claim/unique constraint/locking ngăn hai execution cùng tạo output. Test trên database có concurrency behavior gần production.

### Kiểm thử asynchronous acknowledgement

Cho producer future hoàn tất exceptionally sau khi `write()` đã bắt đầu. Xác nhận writer chờ kết quả và ném exception lên step. Mô phỏng trường hợp broker nhận record nhưng acknowledgement bị mất để kiểm tra duplicate handling.

### Kiểm thử file restart

Cho job ghi một phần file rồi fail. Restart cùng execution và xác nhận file được tiếp tục đúng checkpoint, không có dòng trùng/thiếu. Sau khi job hoàn tất, xác nhận chỉ file final/manifest hoàn chỉnh được consumer nhìn thấy.

### Kiểm thử outbox/inbox

Kiểm tra các trường hợp:

1. Business transaction rollback thì không có outbox event.
2. Business transaction commit thì outbox event tồn tại.
3. Broker nhận message nhưng publisher crash trước khi mark published thì event có thể được gửi lại.
4. Consumer nhận event trùng nhưng chỉ áp dụng business effect một lần.
5. Inbox insert và business update rollback cùng nhau khi consumer xử lý lỗi.

### Kiểm thử đối soát

Sau job, query theo business key để phát hiện output thiếu, duplicate, reject chưa xử lý và outbox còn pending quá hạn. Test không chỉ kiểm tra `BatchStatus.COMPLETED`.

## Những lỗi thường gặp

### Nghĩ một lần gọi write đồng nghĩa một output

Writer có thể được gọi lại khi retry hoặc restart. Thiết kế theo logical output ID và idempotency.

### Nghĩ Spring Batch bảo đảm exactly-once cho mọi destination

Checkpoint và transaction chỉ bảo vệ resource tham gia transaction tương ứng. File, broker và HTTP API thường không rollback cùng database.

### Gửi message rồi không chờ acknowledgement

Step có thể commit trước khi biết send thất bại. Chờ kết quả theo policy hoặc dùng integration transaction phù hợp.

### Tạo UUID mới trong mỗi attempt

Duplicate không thể nhận diện vì mỗi lần gửi có ID khác. Giữ ID ổn định từ source/outbox.

### Retry POST không có idempotency key

Server có thể tạo resource lần nữa sau timeout. Dùng idempotency key hoặc reconcile outcome unknown.

### Dùng kiểm tra SELECT rồi mới INSERT để chống trùng

Hai execution có thể cùng thấy chưa có row rồi cùng insert. Dùng unique constraint và xử lý conflict atomically.

### Đặt side effect trong processor/listener

Processor/listener có thể được gọi lại. Giữ transformation thuần và đưa side effect vào writer/outbox có idempotency.

### Nuốt exception để step hoàn tất

Checkpoint có thể tiến lên dù output chưa được tạo. Truyền lỗi lên hoặc lưu reject bền vững theo policy.

### Skip lỗi broker

Event có thể bị mất vĩnh viễn. Retry/fail hoặc giữ event trong outbox.

### Launch JobInstance mới để “restart”

Instance mới có thể xử lý toàn bộ input từ đầu. Dùng đúng restart semantics và business batch identity.

### Dựa vào JobExecutionId làm idempotency key

Execution ID đổi khi restart hoặc launch mới. Dùng business identity ổn định.

### Không kiểm tra output sau job

Status `COMPLETED` không chứng minh đủ/không trùng. Đối soát theo key, event ID và trạng thái.

## Nguyên tắc thiết kế

Khi cần bảo đảm output được tạo một lần về mặt nghiệp vụ, hãy xác định:

1. “Một lần” đang nói về method call, message delivery, row/file vật lý hay business effect?
2. Writer có thể được gọi lại do retry, rollback hoặc restart không?
3. Business output và checkpoint có cùng transaction/resource không?
4. Destination có hỗ trợ transaction hoặc idempotency key không?
5. Logical output có ID ổn định qua mọi attempt không?
6. Database có unique constraint hoặc upsert atomic phù hợp không?
7. Message consumer có inbox/deduplication và transaction phù hợp không?
8. File output có staging, manifest và publish sau khi hoàn tất không?
9. HTTP/API có hỗ trợ idempotency key hoặc lookup/reconciliation không?
10. Có thể có hai job execution cùng xử lý một input không?
11. Processor/listener có side effect bị lặp không?
12. Retry, timeout và asynchronous acknowledgement có được giới hạn/quan sát không?
13. Có đối soát output thiếu, duplicate, reject và pending không?
14. Test đã mô phỏng rollback, crash, restart, launch mới và concurrent execution chưa?

Không có một cờ cấu hình Spring Batch nào tự biến mọi output thành exactly-once. Hãy thiết kế theo từng destination: dùng transaction và unique key cho database, staging/manifest cho file, event ID cùng outbox/inbox cho message, idempotency key cho API. Chấp nhận rằng thao tác có thể được thử nhiều lần, nhưng làm cho business effect có thể nhận diện và áp dụng một lần. Kiểm thử các cửa sổ lỗi giữa output acknowledgement, transaction commit và checkpoint để chứng minh hành vi khi retry/restart.

## Ghi nhớ

Một lần gọi `write()` không đồng nghĩa output chỉ được tạo một lần. Retry, rollback, restart, launch `JobInstance` mới, timeout và hai execution đồng thời đều có thể khiến cùng logical item tạo side effect nhiều lần. Spring Batch checkpoint giúp khôi phục tiến độ nhưng chỉ atomic với output khi chúng thực sự tham gia cùng transaction/resource. Database có thể dùng unique constraint và upsert; file nên ghi staging rồi publish sau khi hoàn tất; message cần event ID ổn định, outbox/inbox và consumer idempotency; HTTP API cần idempotency key hoặc reconciliation. Đặt transformation thuần trong processor, side effect có kiểm soát trong writer, không nuốt exception và không gửi async rồi trả về trước khi biết kết quả theo policy. Mục tiêu thực tế là một business effect dù có nhiều attempt kỹ thuật; xác minh bằng đối soát và test rollback, crash, retry, restart, launch mới và concurrency.
