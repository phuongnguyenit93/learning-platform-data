# Writer tạo duplicate output trong Spring Batch

Trong Spring Batch, một lỗi khó phát hiện là **writer tạo duplicate output**: cùng một bản ghi nghiệp vụ xuất hiện hai lần trong bảng đích, file CSV có những dòng lặp lại hoặc một API bên ngoài nhận cùng một yêu cầu nhiều lần. Đôi khi `JobExecution` vẫn có `BatchStatus.COMPLETED`, bởi Spring Batch chỉ biết writer đã thực hiện những lời gọi được cấu hình; framework không thể tự suy đoán khóa duy nhất hay quy tắc “mỗi giao dịch chỉ được ghi một lần” của nghiệp vụ.

Lỗi này đặc biệt phổ biến khi batch có **chunk transaction, retry, restart, writer ghi nối file, job chạy chồng lấp hoặc side effect ngoài transaction**. Trong chương **Lỗi thường gặp** của **Spring Batch Core Processing**, mục tiêu là phân biệt các nguyên nhân, thu thập bằng chứng rồi thiết kế writer có tính **idempotent** (xử lý lại cùng yêu cầu mà không nhân đôi tác động nghiệp vụ).

```text
          Dữ liệu nguồn
               |
               v
          ItemReader
               |
               v
          ItemProcessor
               |
               v
           ItemWriter
         /      |      \
        v       v       v
      JDBC     File    API / Message
        |       |       |
        +-------+-------+
                |
          Duplicate output?
                |
      +---------+----------+
      |         |          |
    Input     Retry /    Trùng job/
    trùng     restart    output path
```

**Nguyên tắc:** đừng sửa lỗi bằng cách xóa những dòng trùng sau khi job chạy xong nếu chưa xác định tại sao chúng được tạo. Cách “dọn hậu quả” có thể che lỗi transaction, làm mất các dòng thực sự hợp lệ hoặc xóa một tác động đã được hệ thống ngoài xác nhận.

## 1. Thế nào là duplicate output?

Hai record có cùng toàn bộ cột chưa chắc luôn là duplicate nghiệp vụ. Cần định nghĩa **đơn vị kết quả duy nhất** (*business identity*).

Ví dụ job nhập thanh toán:

```text
Input:
  paymentId=P001, amount=100.00
  paymentId=P002, amount=200.00

Output mong đợi:
  P001,100.00
  P002,200.00

Output thực tế:
  P001,100.00
  P002,200.00
  P001,100.00   <-- duplicate nếu mỗi paymentId chỉ được ghi một lần
```

Trong một số nghiệp vụ khác, `paymentId=P001` có thể xuất hiện ở nhiều **phiên bản** hoặc nhiều **kỳ dữ liệu**. Khi ấy khóa duy nhất không chỉ là `paymentId`, mà có thể là `(tenantId, sourceVersion, paymentId)` hoặc `(businessDate, paymentId)`. Nếu xác định khóa quá hẹp, ta có thể vô tình bỏ những record cần giữ; nếu khóa quá rộng (nhất là thêm UUID của mỗi execution), ta có thể không phát hiện dữ liệu bị ghi trùng.

Phân biệt các dạng duplicate:

| Dạng | Dấu hiệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Duplicate có sẵn ở **input** | Cùng khóa nguồn xuất hiện nhiều lần | Reader đọc đúng nguồn nhưng bản thân dữ liệu nguồn bị lặp? |
| Duplicate do **processor** | Một item được biến đổi thành nhiều output, hoặc mapping mất khóa | Logic xử lý có chủ đích tạo nhiều dòng không? |
| Duplicate do **writer** | Một item làm writer ghi nhiều lần | Writer có vòng lặp/lời gọi ngoài ý muốn hoặc lưu buffer sai không? |
| Duplicate khi **retry** | Một thao tác được thực hiện lại trong cùng `StepExecution` | Lần trước đã có side effect trước khi báo lỗi? |
| Duplicate khi **restart** | Lỗi ở execution đầu, execution sau ghi lại dữ liệu đã có | `ExecutionContext` và transaction/writer state có khớp? |
| Duplicate do **rerun/new JobInstance** | Cùng kỳ xử lý được chạy lại từ đầu | `JobParameters` có tạo instance mới không? |
| Duplicate do **concurrency** | Hai thread/partition/node ghi cùng record | Phân vùng hoặc khóa/constraint có ngăn chồng lấp? |
| Duplicate do **append/ghi đè file** | File có nhiều block dữ liệu lặp, thường sau lần chạy thứ hai | Writer mở output cũ theo chế độ nào? |

Trước khi chọn giải pháp, phải thống nhất duplicate đang nói đến **hai dòng vật lý giống nhau**, **hai giao dịch cùng khóa nghiệp vụ**, hay **hai sự kiện xử lý lại có chủ đích**. Audit có thể cần giữ các lần thử, nhưng hệ thống đích không nhất thiết phải áp dụng tác động nghiệp vụ nhiều lần.

## 2. Vì sao chunk transaction có thể dẫn đến ghi lặp?

Spring Batch thường thực hiện chunk-oriented processing:

```text
BEGIN TRANSACTION
  read item 1..N
  process item 1..N
  writer.write(chunk)
  update ExecutionContext/checkpoint
COMMIT
```

Nếu reader, writer, `JobRepository` và dữ liệu đích sử dụng transaction manager phù hợp, một lỗi **trước commit** thường khiến các thay đổi của database trong transaction được rollback. Khi restart, những item chưa commit có thể được xử lý lại; đó là hành vi đúng. Vấn đề phát sinh khi **một tác động của writer đã thành công nhưng không được rollback cùng transaction**.

```text
Chunk 1: P001, P002
  writer gửi P001 tới API ngoài ---> API trả 200, đã tạo giao dịch
  writer gửi P002 tới API ngoài ---> timeout
  chunk transaction SQL rollback

Lần thử lại:
  writer gửi lại P001 ------------> API tạo giao dịch lần thứ hai!
  writer gửi lại P002 ------------> API trả 200
```

`rollback` của database **không thu hồi** giao dịch đã tạo bởi API bên ngoài. Tương tự, ghi file, gửi email hoặc publish message không tự tham gia cùng transaction JDBC của chunk. Chính vì vậy writer cần hợp đồng idempotency ở ranh giới tác động bên ngoài.

### 2.1. Retry khác restart, và cả hai khác rerun

- **Retry**: thao tác lỗi được thử lại trong cùng quá trình xử lý, thường bên trong một `StepExecution`, theo fault-tolerant policy. Nếu writer có side effect trước khi báo lỗi, retry có thể nhân đôi tác động.
- **Restart**: một `JobInstance` bị `FAILED`/`STOPPED` được chạy tiếp bằng một `JobExecution` mới, dựa trên metadata và checkpoint đã lưu. Phần chưa commit có thể bị đọc/ghi lại.
- **Rerun từ đầu**: khởi chạy một `JobInstance` mới, thường do thay identifying `JobParameters` hoặc tạo kỳ/version mới. Nếu cả hai instance ghi chung một đích mà không có idempotency, có thể tạo duplicate.

Mỗi trường hợp đòi hỏi cách xác định **điều gì đã được commit**, **vị trí đọc cần khôi phục** và **khóa nghiệp vụ để chống áp dụng tác động hai lần**.

## 3. Vai trò của `JobInstance`, `JobParameters` và `ExecutionContext`

Trong Spring Batch:

```text
Tên Job + identifying JobParameters
                 |
                 v
            JobInstance
                 |
        +--------+---------+
        |                  |
  JobExecution #1     JobExecution #2
       FAILED             COMPLETED (restart)
```

Ví dụ mỗi kỳ có một instance:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "feed-v3")
    .toJobParameters();
```

Mặc định các tham số trên là identifying. Khi thất bại, việc restart cùng instance cho phép Spring Batch sử dụng `ExecutionContext` đã lưu. Nếu mỗi lần gọi thêm một UUID identifying:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "feed-v3")
    .addString("attemptId", UUID.randomUUID().toString())
    .toJobParameters();
```

thì mỗi lần launch là **JobInstance khác nhau**, không phải một restart. Cơ chế restart của reader không thể tự biết rằng hai instance này cần dùng chung checkpoint. Đây là nguồn duplicate phổ biến khi ứng dụng dùng `RunIdIncrementer` hoặc timestamp để “né” `JobInstanceAlreadyCompleteException`.

### 3.1. `ExecutionContext` là checkpoint, không phải khóa chống trùng

`ItemStream` có các method `open(ExecutionContext)`, `update(ExecutionContext)` và `close()`. Một reader restartable như `FlatFileItemReader` có thể lưu vị trí đã đọc; writer restartable như `FlatFileItemWriter` có thể lưu trạng thái file. Khi chunk commit thành công, framework lưu context để phục hồi.

Checkpoint giúp **giảm lượng dữ liệu phải xử lý lại**, nhưng không thay thế unique key ở đích. Nếu process bị kill đúng lúc hệ thống ngoài đã nhận thao tác nhưng trạng thái Batch chưa commit, không thể dựa vào `ExecutionContext` để biết tác động đó đã được hệ thống ngoài chấp nhận hay chưa.

### 3.2. Cấu hình vô tình phá checkpoint

Những thay đổi cần kiểm soát:

- `.saveState(false)` trên reader/writer vốn cần restart có thể làm mất khả năng tiếp tục đúng vị trí.
- Thay đổi `.name(...)` của `ItemStream` giữa hai lần thực thi có thể đổi key trạng thái trong context.
- Bọc `ItemStream` bên trong một delegate nhưng không ủy quyền/đăng ký `open/update/close` khiến framework không lưu state như kỳ vọng.
- Đổi đường dẫn file đầu ra hoặc file nguồn qua từng `JobExecution` thay vì giữ identity ổn định theo instance.
- Đổi thứ tự truy vấn hoặc nguồn dữ liệu giữa restart có thể làm offset/sort key trỏ tới record khác.
- Chia partition không ổn định khiến một khoảng input được xử lý bởi nhiều worker ở các lần chạy.

**Không trực tiếp sửa các bảng `BATCH_*` để ép vị trí restart.** Metadata thuộc quyền quản lý của Spring Batch; sửa thủ công dễ làm bộ đếm/context và thực tế output không khớp nhau.

## 4. Nguyên nhân 1: `FlatFileItemWriter` ghi nối vào file cũ

Một dấu hiệu thường gặp là báo cáo CSV sau lần chạy thứ hai chứa cùng header và toàn bộ dòng dữ liệu của lần đầu:

```text
orders.csv sau lần 1:
  id,status
  A001,PAID
  A002,NEW

orders.csv sau lần 2:
  id,status
  A001,PAID
  A002,NEW
  id,status
  A001,PAID
  A002,NEW
```

Nguyên nhân có thể là writer đã được cấu hình **append**, đường dẫn output dùng chung giữa các lần chạy, hoặc writer tự mở file ở chế độ append ngoài cơ chế `ItemStream`. Không nên chỉ xóa header bị trùng: phần dữ liệu bên dưới cũng đã được lặp.

### 4.1. Phân biệt lần chạy mới với restart

Với `FlatFileItemWriter`, các tùy chọn như `appendAllowed`, `shouldDeleteIfExists` và `saveState` ảnh hưởng cách writer mở file. Spring Batch có logic riêng khi writer **được restart bằng execution context hợp lệ**; không nên đánh đồng hành vi mở file ở restart với hành vi của một instance hoàn toàn mới.

| Tình huống | Kỳ vọng | Nguy cơ duplicate |
| --- | --- | --- |
| Instance mới, output mới | Tạo file kết quả cho kỳ/version mới | Thấp nếu tên file riêng và không ghép output cũ |
| Instance mới, trùng output path | Có chính sách từ chối/replace/version rõ ràng | Append hoặc replace sai tạo lặp/mất output |
| Restart instance lỗi với file dở dang | Mở lại đúng output, khôi phục vị trí reader và writer | Nếu xóa/append sai, có thể mất dữ liệu hoặc lặp chunk |
| Hai execution cùng ghi chung output | Có cơ chế loại trừ hoặc output tách riêng | Hai writer có thể xen dòng, lặp hoặc làm hỏng file |

### 4.2. Writer file với đường dẫn xác định theo kỳ dữ liệu

Ví dụ Spring Batch 5.x:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemWriter<String> ordersWriter(
        @Value("#{jobParameters['outputPath']}") String outputPath) {

    return new FlatFileItemWriterBuilder<String>()
        .name("ordersWriter")
        .resource(new FileSystemResource(outputPath))
        .encoding(StandardCharsets.UTF_8.name())
        .lineAggregator(line -> line)
        .saveState(true)
        .build();
}
```

Mẫu này giữ tên writer ổn định và dùng state phục vụ restart. **Nó chưa tự bảo đảm idempotency**: nếu `outputPath` được truyền bừa bãi, hai instance khác nhau vẫn có thể trỏ vào cùng một file. Trong ứng dụng thực, tạo path từ `businessDate` và output version đã được xác thực dưới một output root do service quản lý. Không lấy đường dẫn từ input không tin cậy rồi cho phép writer ghi tùy ý trên filesystem.

### 4.3. Chiến lược file an toàn hơn: staging → verify → publish

```text
Output của JobInstance:
  staging/2026-11-16/orders-v3.part
             |
        writer ghi, checkpoint/restart
             |
     job COMPLETED + xác minh nội dung
             |
             v
  published/2026-11-16/orders-v3.csv
```

Tệp `.part` chỉ được sử dụng bởi job đang thực thi; consumer không đọc nó như kết quả cuối. Sau khi job thành công, kiểm tra số dòng/checksum rồi publish có kiểm soát. Nếu có lần xuất lại có chủ đích, cấp **output version** mới hoặc chính sách replace có phê duyệt thay vì nối dữ liệu vào bản chính thức.

`Files.move(..., ATOMIC_MOVE)` có thể giúp publish nguyên vẹn trên filesystem hỗ trợ, nhưng không được bảo đảm khi di chuyển giữa volume hoặc đối với object storage. Nếu đích là S3/MinIO, cần dùng object version/manifest và quy trình xác nhận riêng.

### 4.4. Tệp đã có trước khi job bắt đầu

Nếu phát hiện output cuối đã tồn tại, cần xác định nó thuộc:

1. **Kết quả đã được công nhận**: không tự ý ghi nối hoặc ghi đè.
2. **File tạm của cùng instance cần restart**: giữ file và trạng thái writer; không xóa nó chỉ vì file tồn tại.
3. **File rác hoặc output khác identity**: điều tra/cleanup đúng phạm vi, tránh xóa file của instance khác.

Cấu hình `shouldDeleteIfExists(true)` có thể phù hợp với **instance mới** nhưng có nguy cơ nghiêm trọng nếu được dùng như một thao tác xóa file tùy tiện ngoài vòng đời restart. Hãy hiểu contract của `FlatFileItemWriter` và kiểm thử cả start mới lẫn restart thực tế.

## 5. Nguyên nhân 2: writer JDBC `INSERT` lặp cùng khóa nghiệp vụ

Ví dụ writer ghi vào bảng không có unique constraint:

```sql
CREATE TABLE order_result (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_order_id VARCHAR(50) NOT NULL,
    amount NUMERIC(18,2) NOT NULL
);
```

Nếu mỗi lần ghi luôn tạo một `id` mới, cùng `source_order_id=A001` có thể xuất hiện hai lần mà database vẫn coi cả hai là hợp lệ. `commitCount` và `writeCount` của Spring Batch không thể tự phát hiện quy tắc duy nhất đã bị vi phạm.

### 5.1. Xây dựng khóa duy nhất theo nghiệp vụ

Nếu một đơn hàng nguồn chỉ được lưu một lần cho mỗi `sourceVersion`:

```sql
CREATE TABLE order_result (
    source_version VARCHAR(80) NOT NULL,
    source_order_id VARCHAR(50) NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (source_version, source_order_id)
);
```

Khóa này giúp database chặn duplicate kể cả khi scheduler bất ngờ chạy hai job hoặc writer bị gọi lại. Tuy nhiên, chọn khóa là quyết định nghiệp vụ: nếu mỗi bản cập nhật của cùng order phải được giữ làm lịch sử, dùng thêm `eventVersion` hoặc một event ID ổn định, không áp dụng một unique constraint quá hẹp rồi đánh mất dữ liệu hợp lệ.

### 5.2. Dùng upsert idempotent khi hợp đồng cho phép

Ví dụ **PostgreSQL**:

```sql
INSERT INTO order_result(source_version, source_order_id, amount)
VALUES (:sourceVersion, :sourceOrderId, :amount)
ON CONFLICT (source_version, source_order_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

Đây là cú pháp PostgreSQL, không dùng nguyên văn cho Oracle, SQL Server hoặc MySQL. `DO UPDATE` có nghĩa cùng một khóa được tính lại sẽ **ghi đè giá trị amount hiện có**. Chỉ dùng khi ứng dụng bảo đảm cùng nguồn/version tạo kết quả xác định hoặc có quy tắc cập nhật rõ ràng. Nếu không được phép thay kết quả đã công nhận, có thể chọn `DO NOTHING` kết hợp kiểm tra payload/checksum để tránh che một bản ghi cùng khóa nhưng khác nội dung.

### 5.3. Ví dụ `JdbcBatchItemWriter` dùng khóa nghiệp vụ

Spring Batch 5.x:

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

record OrderOutput(String sourceVersion, String sourceOrderId,
                   java.math.BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<OrderOutput> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderOutput>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO order_result
                (source_version, source_order_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT (source_version, source_order_id)
            DO UPDATE SET amount = EXCLUDED.amount
            """)
        .itemPreparedStatementSetter((item, ps) -> {
            ps.setString(1, item.sourceVersion());
            ps.setString(2, item.sourceOrderId());
            ps.setBigDecimal(3, item.amount());
        })
        .build();
}
```

`JdbcBatchItemWriter` gửi các câu lệnh qua JDBC batch trong phạm vi transaction được step cấu hình. **Writer JDBC không mặc định có tính idempotent** chỉ vì tên class có chữ “Batch”. Chính ràng buộc database và SQL `INSERT`/`UPSERT` xác định hành vi khi nhận lại cùng item.

### 5.4. Vì sao không nên dùng `SELECT` rồi `INSERT` như cách chống trùng duy nhất?

```text
Job A: SELECT WHERE source_order_id='A001' → chưa có
Job B: SELECT WHERE source_order_id='A001' → chưa có
Job A: INSERT A001
Job B: INSERT A001  --> duplicate nếu không có UNIQUE constraint
```

Đây là race condition kiểu *check-then-act*. Một bước kiểm tra ở ứng dụng có thể hữu ích, nhưng phải có unique constraint/upsert có tính atomic ở database hoặc cơ chế đồng bộ tương ứng. Khóa nghiệp vụ cũng phải bao gồm tenant/kỳ/version khi cần; đừng dùng một khóa toàn cục không phản ánh dữ liệu.

## 6. Nguyên nhân 3: writer gọi API hoặc publish message nhiều lần

Gửi yêu cầu HTTP, phát message, gửi email hoặc ghi object storage thường nằm **ngoài transaction JDBC** của Spring Batch. Một timeout **không chứng minh thao tác chưa thực hiện**: server có thể đã nhận, xử lý và commit, còn client chỉ mất response.

```text
Client Batch                    Hệ thống đích
     |                              |
     | POST create(P001)            |
     |----------------------------->|
     |                              | tạo P001 thành công
     |          (response lost)     |
     |<---------- X                 |
     |
     | Retry POST create(P001)      |
     |----------------------------->| tạo P001 lần nữa?
```

### 6.1. Idempotency key ổn định qua retry và restart

Thay vì tạo request ID mới ở mỗi attempt, ứng dụng nên tính khóa từ **yêu cầu nghiệp vụ**:

```java
String idempotencyKey = "payment:"
    + sourceVersion + ":" + paymentId;
```

Nếu API hỗ trợ idempotency key, gửi cùng khóa ở header theo hợp đồng của API (ví dụ `Idempotency-Key`) cho các lần thử cùng một tác động. Hệ thống đích cần lưu khóa và trả lại kết quả trước đó hoặc từ chối duplicate theo quy tắc rõ ràng.

**Không dùng** `jobExecutionId`, `UUID.randomUUID()` hoặc timestamp hiện tại làm idempotency key của **mỗi lần thử** nếu các attempt đó đều đại diện cho cùng một payment. Những giá trị thay đổi qua retry/restart sẽ làm mất tác dụng chống trùng.

Trong một số giao thức, key chỉ được giữ trong khoảng thời gian giới hạn; phải hiểu retention của hệ thống đích. Với tác động tiền tệ hoặc yêu cầu có giá trị cao, thêm đối soát trạng thái ở server, audit event và quy trình xử lý khi response không rõ kết quả.

### 6.2. Transactional outbox

Nếu batch ghi database rồi phát sự kiện ra message broker, có thể dùng *transactional outbox*:

```text
BEGIN TRANSACTION
  UPSERT order_result(A001)
  INSERT outbox_event(eventId=order-result:feed-v3:A001, payload=...)
COMMIT

Publisher đọc outbox:
  gửi event tới broker
  đánh dấu đã gửi / retry nếu lỗi

Consumer:
  ghi nhận eventId đã xử lý
  bỏ qua redelivery của cùng event
```

Outbox giảm nguy cơ database đã commit nhưng sự kiện bị mất; tuy vậy, publisher vẫn có thể gửi **lặp** sau timeout. Vì vậy event ID phải ổn định và consumer vẫn cần deduplication/inbox hoặc cập nhật idempotent. Đây là thiết kế bảo đảm kết quả cuối có thể đúng ngay cả khi hạ tầng gửi theo *at-least-once delivery*; không nên tuyên bố “exactly-once end-to-end” chỉ dựa vào một framework.

## 7. Nguyên nhân 4: cùng job bị kích hoạt nhiều lần

Lịch `@Scheduled`, Quartz, Kubernetes CronJob, CLI hoặc API vận hành có thể cùng gọi một job trong một khoảng ngắn. Nếu mỗi nguồn kích hoạt tạo identifying parameters khác nhau, Spring Batch có thể coi chúng là **những `JobInstance` hợp lệ khác nhau**, dù cùng xử lý một kỳ dữ liệu.

```text
02:00 Scheduler trên Node A -> JobInstance (businessDate=16/11, runId=1)
02:00 Scheduler trên Node B -> JobInstance (businessDate=16/11, runId=2)

Cả hai đọc input ngày 16/11
Cả hai ghi vào orders-2026-11-16.csv hoặc cùng bảng đích
```

Khi ứng dụng có nhiều instance, `@Scheduled` thường được đăng ký ở **mỗi instance** nếu không có cơ chế điều phối riêng. `JobRepository` giúp nhận diện executions của cùng instance nhưng **không loại trừ mọi lần chạy của các instance khác nhau**.

### Chiến lược kiểm soát

- Định danh `JobInstance` bằng **kỳ dữ liệu/bộ input ổn định**, không ngẫu nhiên hóa identifying parameters chỉ để lần nào cũng launch được.
- Dùng scheduler cluster-aware/distributed lock hoặc một nguồn trigger điều phối khi cần mỗi kỳ chỉ có một launcher.
- Đặt unique constraint hoặc idempotency ở **output** làm lớp bảo vệ cuối, bởi bất kỳ cơ chế lock nào cũng có trường hợp tiến trình chết/timeout.
- Tách output theo kỳ và version; không cho hai instance cùng mở một file đích để ghi đồng thời.
- Nếu công việc được chia partition, mỗi partition cần phạm vi không chồng lấp và tên/identity có thể tái dựng khi restart.

Một bước `JobExplorer.findRunningJobExecutions(jobName)` hỗ trợ giám sát, nhưng **kiểm tra “không có job đang chạy” rồi launch** gồm hai thao tác, vẫn có race giữa nhiều node. Đừng coi việc kiểm tra trạng thái đơn thuần là khóa phân tán.

## 8. Nguyên nhân 5: reader phát cùng item nhiều lần

Vết duplicate ở writer có thể bắt nguồn từ **reader**, không phải writer:

- SQL query `JOIN` với quan hệ một-nhiều vô tình nhân dòng.
- Paging không có thứ tự ổn định hoặc sort key không duy nhất.
- Dataset bị cập nhật trong lúc phân trang theo `OFFSET`.
- Hai partition quét cùng khoảng ID hoặc cùng file.
- Multi-threaded step chia sẻ reader stateful không thread-safe.
- File nguồn đã chứa dòng trùng, hoặc file được lấy nhiều lần từ một thư mục đầu vào.
- Retry/restart đọc lại một chunk chưa commit, nhưng writer không idempotent.

Ví dụ query có thể nhân dữ liệu:

```sql
SELECT o.order_id, o.total
FROM orders o
JOIN order_tags t ON t.order_id = o.order_id;
```

Nếu một order có ba tag, kết quả query có thể có ba dòng của cùng `order_id`. Nếu writer chỉ quan tâm tới order, output sẽ chứa duplicate dù mỗi lần gọi writer hoàn toàn đúng với input đã nhận.

Thay vì dùng `DISTINCT` theo phản xạ, cần làm rõ mỗi order có cần tổng hợp tag hay không. Có thể chọn `EXISTS`, `GROUP BY`, truy vấn nguồn đã loại trùng có chủ đích hoặc sửa data model. **Không dùng dedup ở writer để che lỗi logic JOIN** nếu số lượng kết quả mang ý nghĩa nghiệp vụ.

### 8.1. Reader paging và sort key

Với `JdbcPagingItemReader`, sort key nên ổn định và phân biệt item; dùng cột `id` duy nhất hoặc một tổ hợp khóa xác định. Truy vấn chỉ `ORDER BY created_at` khi nhiều dòng có cùng timestamp có thể khiến các trang không ổn định.

`pageSize` và `fetchSize` giúp hiệu năng đọc, còn `chunk size` xác định commit interval; chúng **không phải cơ chế chống duplicate**. Với dữ liệu thay đổi trong lúc job chạy, cần snapshot hoặc watermark/khóa đầu vào, không dựa hoàn toàn vào việc thay page size.

### 8.2. Chạy song song và partition

```text
partition A: order_id 1..1000
partition B: order_id 1001..2000

Đúng: hai tập không giao nhau.

Sai:
partition A: order_id 1..1500
partition B: order_id 1000..2000
                 ^^^^^^^^^
                 dữ liệu chồng lấp 1000..1500
```

Một hệ thống tốt giữ kế hoạch partition **ổn định theo job instance**, có checkpoint riêng cho từng worker step và unique key ở output. Chỉ thêm `TaskExecutor` cho một step dùng reader stateful không có nghĩa reader đã thread-safe hoặc restart vẫn an toàn; trong một số tình huống, `SynchronizedItemStreamReader` đồng bộ thao tác đọc nhưng **không bảo đảm** checkpoint đúng nếu các chunk commit ngoài thứ tự.

## 9. Quy trình điều tra duplicate theo bằng chứng

Khi phát hiện dòng bị lặp, hãy điều tra theo một thứ tự giúp khoanh vùng lỗi thay vì thử đổi cờ writer ngẫu nhiên.

### Bước 1: xác nhận định nghĩa duplicate

Xác định business key và kỳ nguồn:

```sql
-- Ví dụ bảng đích có source_version và source_order_id.
SELECT source_version, source_order_id, COUNT(*) AS total
FROM order_result
GROUP BY source_version, source_order_id
HAVING COUNT(*) > 1
ORDER BY total DESC, source_version, source_order_id;
```

Nếu bảng đã có unique key trên đúng hai cột, truy vấn này sẽ không thể tìm thấy duplicate theo định nghĩa đó. Khi người dùng vẫn báo trùng, cần kiểm tra liệu họ đang nhìn dữ liệu ở một bảng downstream khác, file xuất, view có JOIN nhân dòng, hay định nghĩa business key thực sự khác.

### Bước 2: tra các `JobExecution` cùng kỳ

Với schema Spring Batch 5.x, một truy vấn read-only thường hữu ích:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.START_TIME,
    je.END_TIME,
    je.STATUS,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Đối chiếu identifying parameters trong `BATCH_JOB_EXECUTION_PARAMS` để xác định những execution thuộc cùng `businessDate`/`sourceVersion`. Nếu có hai `JobInstance` khác nhau nhưng cùng business key, kiểm tra `runId`, UUID hoặc lịch chạy trùng. Schema metadata có thể khác theo major version Spring Batch; luôn đối chiếu DDL version của ứng dụng trước khi chạy SQL tùy chỉnh.

### Bước 3: xem counters và thời điểm lỗi ở step

```sql
SELECT
    JOB_EXECUTION_ID,
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :job_execution_id
ORDER BY STEP_EXECUTION_ID;
```

Các counters là bằng chứng về hoạt động framework nhưng **không đồng nghĩa số record nghiệp vụ duy nhất ở output**. `WRITE_COUNT=1000` không chứng minh database có 1000 hàng mới: `UPSERT` có thể cập nhật hàng cũ, writer file có thể bị ghi nối và API có thể đã nhận cùng event hai lần. Khi có retry, các lần gọi processor/writer cũng không nhất thiết ánh xạ 1:1 với số item đã commit.

### Bước 4: xem checkpoint và nguồn dữ liệu

- Reader có triển khai `ItemStream`/`saveState(true)` và tên ổn định không?
- Có sử dụng đúng `ExecutionContext` của **same JobInstance** khi restart không?
- Input file có cùng checksum/object version giữa hai lần chạy không?
- SQL reader có sort key/partition range ổn định và không nhân bản row do JOIN không?
- Có chunk đã rollback nhưng writer vẫn tạo side effect bên ngoài không?

Nếu file xuất bị lặp cả một khối bản ghi, hãy kiểm tra ngày tạo file, thao tác append, số execution cùng output path và header duplicate. Nếu database chỉ lặp các record gần một checkpoint, kiểm tra retry/restart và transaction. Nếu lặp rải rác trên toàn bộ input, kiểm tra nguồn dữ liệu, JOIN và partition.

### Bước 5: đối chiếu tác động ở đích

Đối với JDBC, tra transaction/unique key và thời điểm insert. Đối với API, tra `idempotencyKey`/request ID và phản hồi thực tế ở server. Đối với message, tra event ID và lịch sử consumer. Đối với file, so checksum hoặc nhận diện block byte/line bị lặp. **Không kết luận API chưa thực hiện yêu cầu chỉ vì client nhận timeout**.

## 10. Ví dụ kiểm thử restart không tạo duplicate với H2

Phần này minh họa một **integration test Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter**. Step đọc bốn payment từ file, ghi vào H2 theo chunk size 2. Lần chạy đầu cố ý ném exception ở chunk chứa `P003`, sau khi chunk đầu đã commit. Lần chạy thứ hai dùng **cùng identifying JobParameters** để restart. Kết quả cuối phải có đúng bốn khóa, không có duplicate.

### 10.1. Dependency Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

### 10.2. Test hoàn chỉnh

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = DuplicateOutputRestartTest.TestBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class DuplicateOutputRestartTest {

    record Payment(String id, int amount) {}

    @Autowired JobLauncherTestUtils jobLauncherTestUtils;
    @Autowired JdbcTemplate jdbcTemplate;
    @Autowired AtomicBoolean failOnce;

    @BeforeEach
    void prepareDatabase() {
        jdbcTemplate.execute("""
            CREATE TABLE IF NOT EXISTS payment_result (
                id VARCHAR(30) PRIMARY KEY,
                amount INTEGER NOT NULL
            )
            """);
        jdbcTemplate.update("DELETE FROM payment_result");
        failOnce.set(true);
    }

    @Test
    void restartReusesCheckpointAndProducesNoDuplicate(@TempDir Path dir)
            throws Exception {
        Path input = dir.resolve("payments.csv");
        Files.writeString(input, """
            id,amount
            P001,100
            P002,200
            P003,300
            P004,400
            """, StandardCharsets.UTF_8);

        String sourceVersion = "fixture-" + UUID.randomUUID();
        JobParameters parameters = new JobParametersBuilder()
            .addString("sourceVersion", sourceVersion) // identifying
            .addString("inputPath", input.toAbsolutePath().toString(), false)
            .toJobParameters();

        // Chunk #1 (P001, P002) commit, chunk #2 thất bại có chủ đích.
        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(jdbcTemplate.queryForList(
            "SELECT id FROM payment_result ORDER BY id", String.class))
            .containsExactly("P001", "P002");

        // Cùng identifying parameters: đây là restart JobInstance cũ.
        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(restarted.getJobInstance().getId())
            .isEqualTo(first.getJobInstance().getId());
        assertThat(restarted.getId()).isNotEqualTo(first.getId());

        List<String> ids = jdbcTemplate.queryForList(
            "SELECT id FROM payment_result ORDER BY id", String.class);
        assertThat(ids).containsExactly("P001", "P002", "P003", "P004");

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM payment_result", Integer.class);
        assertThat(count).isEqualTo(4);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApplication {

        @Bean
        AtomicBoolean failOnce() {
            // Chỉ dùng để tạo failure có kiểm soát trong test.
            return new AtomicBoolean(true);
        }

        @Bean
        Job importPaymentsJob(JobRepository repository,
                              @Qualifier("importPaymentsStep") Step step) {
            return new JobBuilder("importPaymentsJob", repository)
                .start(step)
                .build();
        }

        @Bean
        @StepScope
        FlatFileItemReader<Payment> paymentReader(
                @Value("#{jobParameters['inputPath']}") String inputPath) {

            return new FlatFileItemReaderBuilder<Payment>()
                .name("paymentReader")
                .resource(new FileSystemResource(inputPath))
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fields -> new Payment(
                    fields.readString("id"), fields.readInt("amount")))
                .saveState(true)
                .build();
        }

        @Bean
        ItemWriter<Payment> paymentWriter(JdbcTemplate jdbc,
                                          AtomicBoolean failOnce) {
            return chunk -> {
                // Chunk thứ hai thất bại TRƯỚC khi ghi dữ liệu.
                boolean containsP003 = chunk.getItems().stream()
                    .anyMatch(payment -> payment.id().equals("P003"));
                if (containsP003 && failOnce.compareAndSet(true, false)) {
                    throw new IllegalStateException("Injected writer failure");
                }

                for (Payment payment : chunk) {
                    // H2 MERGE dùng riêng trong integration test.
                    jdbc.update("""
                        MERGE INTO payment_result (id, amount)
                        KEY (id) VALUES (?, ?)
                        """, payment.id(), payment.amount());
                }
            };
        }

        @Bean
        Step importPaymentsStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("paymentReader") FlatFileItemReader<Payment> reader,
                @Qualifier("paymentWriter") ItemWriter<Payment> writer) {

            return new StepBuilder("importPaymentsStep", repository)
                .<Payment, Payment>chunk(2, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
        }
    }
}
```

Trong ví dụ:

1. Reader là `FlatFileItemReader` có tên ổn định và `.saveState(true)`, vì vậy framework có thể lưu trạng thái sau chunk đầu đã commit.
2. Writer cố tình ném lỗi **trước khi ghi `P003`**, để chắc chắn phần đầu đã commit và phần sau chưa commit theo datasource test. `AtomicBoolean` chỉ là công cụ failure injection trong một test; không dùng state toàn cục như vậy trong production.
3. H2 dùng `MERGE INTO ... KEY(id)` để cập nhật theo khóa duy nhất. PostgreSQL production cần SQL khác, ví dụ `INSERT ... ON CONFLICT`, như phần trước.
4. Lần restart dùng đúng identifying parameters. `inputPath` non-identifying vẫn được giữ nguyên trong cả hai lần chạy; `sourceVersion` được sinh ngẫu nhiên **một lần cho toàn bộ kịch bản test**, không đổi ở lần restart.
5. Assertions kiểm tra cả metadata (`FAILED` rồi `COMPLETED`, cùng `JobInstance`) và dữ liệu đã commit ở đích. Nếu chỉ kiểm tra `COMPLETED`, test không chứng minh được writer chống duplicate.

Test này minh họa lỗi writer trong **cùng database transaction**. Nó không chứng minh hành vi của API ngoài transaction hoặc file writer; những trường hợp đó cần test riêng, bao gồm timeout sau khi side effect đã được đích chấp nhận.

### 10.3. Phép thử bổ sung khi job chạy trùng

Sau khi có một lần chạy thành công, hãy thử chạy **một JobInstance mới** nhưng cùng `sourceVersion` và input trong môi trường kiểm thử có chủ đích. Nếu output có unique key và upsert hợp lệ, số lượng kết quả cuối vẫn là bốn. Tuy vậy, phép thử phải kiểm tra cả payload, hành vi công nhận bản ghi và số lần gọi hệ thống ngoài, bởi cùng một hàng sau upsert không chứng minh mọi side effect đều không bị lặp.

Với file writer, nên test:

- Lần chạy mới vào đường dẫn chưa tồn tại.
- Lần chạy mới khi file đã có dữ liệu, theo policy từ chối/replace/version.
- Lỗi sau một số chunk, restart cùng instance và cùng file.
- File chứa header đúng một lần; mỗi business key xuất hiện đúng theo quy tắc.
- Hai lịch chạy cạnh tranh cùng output path có bị ngăn hoặc cô lập không.

## 11. Các cách sửa lỗi theo từng loại output

| Loại writer | Giải pháp ưu tiên | Điều không nên giả định |
| --- | --- | --- |
| JDBC `INSERT` | Unique constraint theo business key; SQL idempotent/upsert; transaction đúng | `JdbcBatchItemWriter` tự loại duplicate |
| JPA writer | Entity ID/unique key đúng, flush/transaction rõ ràng, merge theo nghiệp vụ | ORM tự bảo đảm không tạo record trùng nếu ID sinh mới |
| Flat file | Đường dẫn ổn định theo instance, `ItemStream` state, staging/versioned publish | `appendAllowed(true)` luôn an toàn cho restart và rerun |
| S3/object storage | Key/version ổn định, publish manifest, conditional write/kiểm tra object khi phù hợp | Timeout upload nghĩa là object chưa được tạo |
| HTTP API | Idempotency key ổn định, query trạng thái khi kết quả không rõ, retry có giới hạn | Retry POST luôn vô hại |
| Message broker | Event ID cố định, transactional outbox, inbox/dedup ở consumer | Một message chỉ được giao đúng một lần trong mọi failure |
| Multi-thread/partition | Phạm vi input không chồng lấp, state riêng, output constraint | Đồng bộ `read()` một mình đủ bảo đảm restart chính xác |

Trong tất cả trường hợp, nên phân biệt hai trách nhiệm: **ngăn duplicate mới** bằng thiết kế kỹ thuật, và **xử lý dữ liệu trùng đã tồn tại** bằng quy trình đối soát/khôi phục có kiểm soát. Không tự thực hiện lệnh xóa hàng loạt theo một điều kiện chưa được xác nhận với owner dữ liệu.

## 12. Những sai lầm sửa duplicate thường gặp

### 12.1. “Thêm `DISTINCT` vào mọi query là xong”

`DISTINCT` có thể loại các dòng vật lý giống nhau trong một query, nhưng không ngăn hai API call hay hai insert vào database ở những thời điểm khác nhau. Nó cũng có thể vô tình gộp hai transaction hợp lệ có cùng số tiền và thời gian. Chỉ dùng khi logic input thực sự yêu cầu tập duy nhất và khóa lựa chọn đã được xác nhận.

### 12.2. “Tắt retry để không còn duplicate”

Tắt retry có thể giảm số attempt nhưng làm batch thất bại nhiều hơn và không giải quyết rerun/restart. Một hệ thống thực tế vẫn phải chịu được trường hợp process crash hoặc scheduler gửi lại yêu cầu. **Idempotency tại điểm tác động** mới là lớp bảo vệ cần thiết.

### 12.3. “`JobRepository` sẽ chống mọi job chạy trùng”

Repository quản lý trạng thái theo `JobInstance`. Nếu job name hoặc identifying parameters khác nhau, có thể tồn tại hai instance cùng ghi vào output. Hơn nữa, lịch chạy trên nhiều node cần điều phối riêng. Không xem `JobRepository` là một distributed lock tổng quát cho tất cả output resource.

### 12.4. “Chỉ cần `writeCount` bằng số input”

`writeCount` đo số item được framework chuyển đến writer/ghi thành công theo step execution. Nếu dùng upsert, số hàng **mới** trong đích có thể nhỏ hơn. Nếu writer gửi request tới external API, writer có thể báo hoàn tất nhưng hệ thống đích thực tế có trạng thái khác. Phải đối soát theo khóa nghiệp vụ ở output thực.

### 12.5. “Sau khi restart, xóa file cũ rồi ghi lại từ đầu”

Xóa file dở dang của writer có checkpoint nhưng giữ offset reader khiến file **mất phần đã commit**. Ngược lại, giữ file cũ và đọc lại từ đầu dễ tạo duplicate. Nếu muốn rerun từ đầu, cần thiết kế một workflow riêng với input/output version, không gọi đó là restart thông thường.

### 12.6. “Dùng `INSERT IGNORE` để bỏ qua mọi lỗi”

Một số dialect có cú pháp bỏ qua conflict, nhưng điều đó có thể che **khác biệt payload** hoặc lỗi dữ liệu cần review. Idempotent không đồng nghĩa “im lặng bỏ qua”. Khi cùng business key xuất hiện với nội dung khác, nên có chính sách: từ chối, đánh dấu conflict, audit hoặc cập nhật version, tùy hợp đồng nghiệp vụ.

## 13. Monitoring và cảnh báo duplicate

Để phát hiện lỗi sớm, nên quan sát cả **lần chạy**, **business key** và **output được công nhận**:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Hai `JobInstance` khác nhau cùng `businessDate/sourceVersion` | Có thể scheduler/rerun tạo công việc trùng |
| Hai execution đồng thời ghi một output path | Rủi ro file xen dòng/ghi trùng |
| Unique constraint violations tăng | Writer nhận lại khóa đã tồn tại hoặc input/partition bị trùng |
| Nhiều `ON CONFLICT`/upsert so với số item mới | Nguồn hoặc retry/rerun cần điều tra, không nhất thiết là lỗi |
| Retry/rollback count tăng mạnh | Lỗi hạ tầng có thể gây replay và side effect ngoài transaction |
| Cùng idempotency key được gửi nhiều lần | Có retry/redelivery; phải kiểm tra kết quả thực tế ở đích |
| Input count và số business key đầu ra không khớp | Có thể thiếu, lọc, skip hoặc trùng; cần đối soát theo pipeline |
| File header/block dữ liệu xuất hiện lặp lại | Append hoặc publish cùng file nhiều lần |

Một mẫu log có cấu trúc:

```text
event=batch.output.write
jobName=importOrdersJob
jobInstanceId=221
jobExecutionId=845
stepExecutionId=1082
businessDate=2026-11-16
sourceVersion=feed-v3
outputAlias=orders-result
writeMode=UPSERT
```

Không đưa toàn bộ payload nhạy cảm, mật khẩu, token hay presigned URL vào log. Với observability backend như Micrometer/Prometheus, tránh dùng `orderId`, `paymentId` và `jobExecutionId` làm metric labels vì cardinality rất lớn. Các ID chi tiết nên nằm trong audit/log có phân quyền; metric chỉ cần nhóm tên job, loại kết quả hoặc error category.

### Đối soát theo kỳ dữ liệu

Trong pipeline một input tạo một output (không có filter, skip hoặc gộp item), có thể kỳ vọng:

```text
Số business key đầu vào duy nhất
        =
Số business key đầu ra duy nhất
```

Nhưng trong pipeline thực, processor có thể lọc, một item có thể sinh nhiều output hoặc writer có logic tổng hợp. Do đó định nghĩa đối soát phải theo **hợp đồng nghiệp vụ**, không áp đặt công thức 1:1 cho mọi job. Đặc biệt, cộng `readCount` của nhiều executions trong chuỗi restart có thể đếm lại những item đã đọc ở chunk rollback; đây không phải số bản ghi nguồn duy nhất.

## 14. Quy trình xử lý khi đã có duplicate trong production

Khi phát hiện duplicate trong kết quả đang được người dùng sử dụng, cách xử lý cần vừa giữ tính đúng của dữ liệu vừa bảo toàn bằng chứng điều tra.

1. **Ngăn phát sinh thêm:** tạm dừng trigger liên quan hoặc khóa đường publish kết quả nếu được phép, không tự xóa dữ liệu đang được dùng.
2. **Xác định business identity:** cùng `paymentId` có thực sự là duplicate hay là các phiên bản/sự kiện khác nhau?
3. **Lưu bằng chứng:** `JobParameters`, `JobExecution`/`StepExecution`, log, source manifest/checksum, SQL keys, output file version và API request ID.
4. **Phân tích ranh giới lỗi:** trùng từ input, writer, retry/restart, schedule/concurrency hay downstream consumer.
5. **Thiết kế bản sửa:** unique constraint, output version, idempotency key, checkpoint ổn định, scheduler lock hoặc sửa reader/partition.
6. **Thử lại với failure injection:** tạo lỗi giữa chunk, timeout sau side effect, restart cùng instance và rerun theo kỳ để chứng minh không tái diễn.
7. **Làm sạch dữ liệu cũ có kiểm soát:** xuất danh sách đề xuất xử lý, kiểm tra tác động và chỉ sửa/xóa theo quy trình được owner dữ liệu duyệt, có audit và khả năng rollback.

Với dữ liệu tiền tệ, việc xóa một “dòng trùng” trong database không hoàn tác một khoản thanh toán đã được đối tác ghi nhận. Cần quy trình nghiệp vụ bù trừ/đối soát theo quy định hệ thống đích; không dùng SQL DELETE để coi như đã hoàn tác side effect bên ngoài.

## 15. Cách chọn biện pháp ngăn duplicate

```text
Phát hiện output duplicate
           |
           v
Input source đã có cùng business key?
    |                     |
   Có                   Không
    |                     |
    v                     v
Định nghĩa rule         Có nhiều JobInstance /
dedup/validation        trigger cùng kỳ?
                          |             |
                         Có            Không
                          |             |
                          v             v
                    Sửa params/      Duplicate xảy ra
                    scheduler/lock   quanh rollback/retry?
                                         |            |
                                        Có           Không
                                         |            |
                                         v            v
                                  Kiểm tra txn,   Kiểm tra JOIN,
                                  idempotency,    file append,
                                  checkpoint      partition, writer
                                         \            /
                                          v          v
                                    Thêm ràng buộc output
                                    + test fail/restart
```

**Kết luận:** writer tạo duplicate output không phải lúc nào cũng là lỗi một dòng code trong `write()`. Nó có thể bắt nguồn từ dữ liệu nguồn, ranh giới transaction, `JobParameters`, `ExecutionContext`, cách mở file, cơ chế retry hoặc nhiều execution cùng tác động đến một resource. Cách sửa bền vững là **xác định business key, bảo vệ idempotency tại đích, giữ checkpoint đúng và kiểm thử với lỗi thật giữa các chunk**. Khi đó cả chạy bình thường, restart và rerun có chủ đích đều cho kết quả có thể giải trình.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): cơ chế chunk, transaction và commit.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): hợp đồng `open`, `update`, `close` và `ExecutionContext` cho restart.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): `FlatFileItemWriter`, file state và cấu hình writer.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter`, paging/cursor và JDBC.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong fault-tolerant step.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobParameters`, `JobExecution` và restart.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): hỗ trợ kiểm thử job, step và failure/restart.
