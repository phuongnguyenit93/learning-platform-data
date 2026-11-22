# Failure khi cập nhật metadata trong Spring Batch: nhận diện và phục hồi

Một chunk đã xử lý xong dữ liệu nhưng không thể cập nhật metadata có thể đặt Spring Batch vào tình huống khó hơn một lỗi nghiệp vụ thông thường. Dữ liệu đầu ra có thể đã thay đổi, trong khi `JobRepository` chưa lưu được `StepExecution`, `ExecutionContext` hoặc trạng thái kết thúc. Sau đó, một lần chạy lại có thể đọc lại item đã được xử lý, gặp lỗi khóa, hoặc từ chối restart vì execution cũ vẫn có trạng thái `STARTED`.

**Failure khi cập nhật metadata** là sự cố xảy ra trong quá trình tạo, sửa hoặc commit trạng thái thực thi mà Spring Batch cần lưu bền vững để biết một job đang ở đâu và có thể restart từ điểm nào. Chủ đề thuộc nhóm **Failure recovery** vì quyết định phục hồi phải dựa trên cả **trạng thái metadata thực sự đã commit** lẫn **tác động nghiệp vụ thực sự đã hoàn tất**.

Bài viết tập trung vào Spring Batch **5.2.x**, `JobRepository` dùng JDBC và kiểu xử lý chunk-oriented. Các nguyên tắc về transaction, consistency, idempotency và checkpoint cũng hữu ích cho các phiên bản khác, nhưng một số package và API có thể khác ở Spring Batch 6.x.

## 1. Metadata của Spring Batch là gì và vì sao cần lưu?

Spring Batch có nhiều lớp thông tin cần giữ qua thời gian:

| Đối tượng / dữ liệu | Vai trò | Ví dụ |
| --- | --- | --- |
| `JobInstance` | Công việc logic xác định bởi tên job và identifying `JobParameters` | `importOrders` cho `businessDate=2026-11-15` |
| `JobExecution` | Một lần thử thực thi job | Execution `4812`, trạng thái `STARTED` hoặc `FAILED` |
| `StepExecution` | Một lần thực thi step | `loadOrders`, `readCount=600`, `writeCount=590` |
| `JobExecutionContext` | Trạng thái chia sẻ ở cấp job | ID file đầu vào, mốc tổng hợp giữa các step |
| `StepExecutionContext` | Checkpoint / trạng thái cấp step cần cho restart | Số dòng reader đã đi qua, offset file, trang API |
| `JobParameters` | Đầu vào và phần định danh `JobInstance` | `businessDate`, `tenant` |

Khi dùng **JDBC JobRepository** với table prefix mặc định, các dữ liệu này được lưu chủ yếu trong:

```text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
```

`JobRepository` là API chính để Spring Batch ghi metadata; `JobExplorer` là API đọc metadata đã lưu. Đây là thông tin cốt lõi để framework quyết định có được tạo một execution mới, tiếp tục một `JobInstance` cũ, bỏ qua step đã hoàn tất và khôi phục trạng thái reader/writer hay không.

**Không có nghĩa mọi lỗi metadata đều là “chỉ sai số liệu trên dashboard”.** Nếu `ExecutionContext` không được lưu đúng sau một chunk, lần restart sau có thể trở lại checkpoint cũ; nếu trạng thái cuối không được ghi, dashboard có thể thấy một execution vẫn `STARTED` dù process đã chết.

## 2. Trình tự xử lý chunk và thời điểm ghi metadata

Với một chunk step thông thường, vòng đời được đơn giản hóa như sau:

```text
JobLauncher khởi chạy Job
         |
         v
JobRepository tạo JobExecution / StepExecution
         |
         v
           BEGIN TRANSACTION
                  |
                  v
         ItemReader -> ItemProcessor
                  |
                  v
           ItemWriter ghi dữ liệu
                  |
                  v
        Reader/Writer cập nhật state
                  |
                  v
         StepExecution / ExecutionContext
       được cập nhật qua JobRepository
                  |
                  v
          COMMIT hoặc ROLLBACK
                  |
                  v
         Chunk tiếp theo (nếu có)
                  |
                  v
    Kết thúc Step, ghi status / exit code
                  |
                  v
    Kết thúc Job, ghi status / exit code
```

Trong Spring Batch 5.2, metadata của `StepExecution` và `ExecutionContext` thường được cập nhật **trước khi commit chunk**. `JobRepository` cần được cấu hình transaction đúng để metadata phục vụ restart không bị lưu tùy tiện, độc lập với ranh giới xử lý.

Sơ đồ là mô hình khái niệm, không phải toàn bộ thứ tự callback nội bộ cho mọi loại step. `JobExecution` còn được cập nhật ở những mốc riêng của lifecycle; một số loại step hoặc item writer có cơ chế transaction khác chunk JDBC thông thường.

### Nếu lỗi xảy ra trước commit?

Khi phần ghi dữ liệu nghiệp vụ và metadata cùng tham gia **một transaction database duy nhất**, exception khiến transaction rollback sẽ thường hoàn tác cả dữ liệu của chunk và metadata tương ứng. Điểm khôi phục trước chunk vẫn có thể dùng lại, với điều kiện không có tác dụng phụ ở tài nguyên ngoài transaction.

Nếu writer ghi ra một API HTTP, file, queue khác transaction hoặc dùng transaction manager **khác** với JobRepository, dữ liệu nghiệp vụ và metadata có thể không commit/rollback cùng nhau. Khi đó một phần tác động đã thành công nhưng checkpoint chưa lưu, và chạy lại có nguy cơ gây **trùng xử lý**.

## 3. Những dạng lỗi metadata thường gặp

| Nhóm sự cố | Biểu hiện thường gặp | Tác động có thể xảy ra |
| --- | --- | --- |
| Mất kết nối tới metadata DB | `CannotGetJdbcConnectionException`, SQL connection timeout, connection reset | Không thể tạo/cập nhật execution, context hoặc status |
| Database khóa/bị nghẽn | Lock wait timeout, deadlock, transaction timeout | Update hoặc commit thất bại; chunk có thể rollback |
| Xung đột optimistic locking | `OptimisticLockingFailureException` do cột `VERSION` không khớp | Hai luồng/tác nhân cùng sửa trạng thái execution hoặc dùng object cũ |
| Schema/permission sai | Thiếu bảng, cột, sequence, quyền `INSERT`/`UPDATE` | Không tạo hoặc cập nhật metadata theo kỳ vọng |
| `ExecutionContext` không thể serialize | Dữ liệu context không phù hợp serializer, payload quá lớn | Không thể lưu checkpoint, gây lỗi chunk hoặc lúc kết thúc |
| Ràng buộc dữ liệu | Chuỗi vượt giới hạn cột, vi phạm constraint, dữ liệu không hợp lệ | Ghi `EXIT_MESSAGE` hoặc context/status thất bại |
| Transaction boundary sai | Metadata và nghiệp vụ dùng transaction khác mà không có chiến lược consistency | Một bên commit, bên kia thất bại; restart có thể lặp side effect |
| JVM/pod bị dừng đột ngột | Process chết giữa thời điểm cập nhật và commit | Repository có thể còn `STARTED` hoặc checkpoint cũ |
| Kết quả commit không chắc chắn | Mất kết nối khi COMMIT, client không nhận acknowledgment | Không thể biết ngay DB đã commit hay rollback nếu chưa xác minh |

Tên exception cụ thể phụ thuộc JDBC driver, nền tảng database, transaction manager và cách Spring dịch exception. Không nên gắn cứng mọi sự cố vào duy nhất một exception class; log nên giữ **root cause**, SQL state/vendor code phù hợp và execution ID.

### Optimistic locking khác lỗi kết nối

Các bảng như `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION` có cột `VERSION`. Khi metadata được update, Spring Batch áp dụng chiến lược optimistic locking để tránh ghi đè thay đổi của một execution đã được cập nhật ở nơi khác.

```text
StepExecution id=9207, VERSION=12

Thread A đọc version 12
Thread B đọc version 12

Thread A update -> version 13 (thành công)
Thread B update với version 12 -> không còn khớp
                                   |
                                   v
                      OptimisticLockingFailureException
```

Đây là tín hiệu của **xung đột trạng thái**, không phải lỗi tạm thời luôn có thể retry ngay. Nếu chỉ bọc `jobRepository.update(stepExecution)` bằng retry mà không giải quyết ownership và state của execution, ta có thể ghi sai checkpoint hoặc che mất lỗi chạy đồng thời.

Hãy tìm nguyên nhân: cùng một `StepExecution` bị thao tác bởi nhiều thread, có hai launcher cùng sử dụng execution, có code tùy chỉnh tự cập nhật repository, có entity cũ bị giữ quá lâu hoặc có thao tác chỉnh metadata thủ công.

## 4. Ma trận nhất quán giữa dữ liệu nghiệp vụ và metadata

Xét một chunk cần ghi 100 item vào hệ thống đích và lưu checkpoint “đã xử lý đến item 500”.

| Dữ liệu nghiệp vụ | Metadata / checkpoint | Ý nghĩa khi restart |
| --- | --- | --- |
| Chưa commit | Chưa commit | Chunk có thể được xử lý lại theo checkpoint cũ; đây là trường hợp rollback mong muốn |
| Đã commit | Đã commit | Thông thường có thể tiếp tục từ checkpoint mới |
| **Đã commit** | **Chưa commit / không rõ** | Có nguy cơ chạy lại 100 item, gây duplicate hoặc gọi API hai lần |
| **Chưa commit** | **Đã commit** | Có nguy cơ mất item vì checkpoint chỉ đến phía sau trong khi kết quả nghiệp vụ chưa ghi |
| Không biết commit đã thành công chưa | Không biết metadata đã commit chưa | Phải điều tra bằng dấu vết bền vững, không đoán bằng exception từ client |

Hai dòng mất cân bằng ở giữa đặc biệt nguy hiểm khi hai thành phần dùng **khác transaction manager**, khi writer thực hiện side effect không transactional hoặc khi có logic tự quản lý commit không đúng quy ước Batch.

### Một database và một transaction

Khi các thao tác JDBC nghiệp vụ và JDBC `JobRepository` thực sự cùng tham gia một local transaction trên **cùng datasource/connection**, thất bại trước commit thường làm hai phần rollback cùng nhau. Tuy nhiên, phải xác nhận cách cấu hình thực tế: chỉ nhìn tên bean transaction manager hoặc thấy cùng URL database chưa đủ để chứng minh tất cả thao tác đang tham gia cùng transaction.

### Hai database hoặc tài nguyên ngoài database

```text
             Chunk transaction
                  |
          +-------+--------+
          |                |
          v                v
   Business DB        Metadata DB
   COMMIT OK           UPDATE FAILED
          |                |
          +-------+--------+
                  |
                  v
      Có nguy cơ xử lý lại item khi restart
```

Nếu dùng hai resource managers riêng mà không có giao thức commit phân tán được cấu hình đúng, Spring Batch không tự biến hai transaction thành một transaction nguyên tử. Trong thực tế, nhiều hệ thống chọn **idempotent writer** và cơ chế đối soát thay vì giao dịch phân tán.

Đối với REST API, email, object storage và message broker, cần một chiến lược riêng vì `PlatformTransactionManager` của JDBC thường không thể hoàn tác side effect đã đi ra ngoài.

## 5. Khi nào metadata có thể không phản ánh trạng thái thực tế?

Phân biệt hai câu hỏi:

1. **Điều gì đã diễn ra?** Process có từng gửi request hoặc ghi dữ liệu đích chưa?
2. **Spring Batch đã ghi nhận điều gì?** Repository còn lưu trạng thái và checkpoint nào sau những transaction đã commit?

Ví dụ một job xử lý được ba chunk, sau đó kết nối metadata DB mất khi kết thúc:

```text
JobExecution 4812
    |
    +-- Chunk 1: business + metadata COMMITTED
    +-- Chunk 2: business + metadata COMMITTED
    +-- Chunk 3: business + metadata COMMITTED
    |
    +-- Step xử lý xong
    |
    +-- UPDATE final StepExecution status -> FAILURE
    |
    +-- JobExecution có thể không được lưu thành COMPLETED
```

Trong ví dụ này, dữ liệu đã ghi không nhất thiết sai, nhưng **trạng thái kết thúc** có thể chưa được persisted. Tùy vị trí lỗi và cơ chế xử lý ngoại lệ, repository có thể hiện `STARTED`, `FAILED`, `UNKNOWN` hoặc còn trạng thái trước đó; không được giả định Spring Batch luôn lưu được một `FAILED` ngay sau khi repository DB bị lỗi.

**Một dòng status cũ là bằng chứng metadata đã lưu, không phải bằng chứng process còn sống.** Nếu pod bị kill mà không có graceful shutdown, execution có thể bị “kẹt” `STARTED`; Spring Batch không tự suy luận rằng process đã chết từ metadata.

Tương tự, `JobExecution.getStatus()` trong object ở bộ nhớ có thể đã được cập nhật nhưng transaction ghi ra DB thất bại. Khi điều tra, hãy đọc lại metadata **từ connection/transaction mới** thay vì chỉ tin object mà thread đang giữ.

## 6. `JobRepository` ghi phần nào, ở bước nào?

Các phương thức trọng tâm trong Spring Batch 5.2:

| API | Trách nhiệm |
| --- | --- |
| `createJobExecution(jobName, jobParameters)` | Tạo execution và xử lý ràng buộc job instance/việc chạy đồng thời |
| `add(stepExecution)` | Lưu một `StepExecution` mới cùng execution context ban đầu |
| `update(jobExecution)` | Cập nhật metadata của `JobExecution`; **không đồng nghĩa tự lưu execution context** |
| `update(stepExecution)` | Cập nhật metadata của `StepExecution`; **không đồng nghĩa tự lưu execution context** |
| `updateExecutionContext(jobExecution)` | Lưu `ExecutionContext` cấp job |
| `updateExecutionContext(stepExecution)` | Lưu `ExecutionContext` cấp step |

Khi dùng các builder và tasklet/chunk machinery chuẩn, **Spring Batch tự gọi repository vào các thời điểm phù hợp**. Thông thường không cần tự gọi `update(stepExecution)` mỗi lần writer thành công. Tự sửa count, version hoặc checkpoint ở ngoài luồng framework dễ gây xung đột với transaction và optimistic locking.

### `ExecutionContext` quyết định điểm restart

Một reader có state, chẳng hạn `FlatFileItemReader` khi bật lưu trạng thái, sử dụng `ExecutionContext` để lưu vị trí có thể khôi phục. Khi chunk commit thành công, checkpoint tương ứng phải được ghi bền vững. Nếu side effect đã xảy ra mà context chưa được lưu, lần restart có thể đọc lại từ vị trí cũ.

Ví dụ logic:

```text
Trước chunk: checkpoint = 400

Chunk 401..500:
  Writer gửi 100 item -> hệ thống đích chấp nhận
  Metadata update/checkpoint 500 -> FAILED

Restart từ checkpoint 400:
  401..500 được thực hiện lại -> phải xử lý duplicate an toàn
```

Với cùng một transaction database, side effect đã rollback thì việc đọc lại là phù hợp. Với hệ thống ngoài transaction, đây là lý do cần idempotency ở writer.

## 7. Cấu hình transaction cho step và repository

Ví dụ chunk step trong Spring Batch 5.2.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

Trong ví dụ, `Order` là kiểu domain của ứng dụng. `transactionManager` quyết định transaction của chunk; `jobRepository` lưu metadata. Hai dependency này có thể dùng cùng database hoặc khác datasource. **Sự xuất hiện của cả hai trong builder không tự chứng minh hai phần cùng một transaction.**

Khi cần local JDBC transaction thống nhất, hãy kiểm tra hạ tầng transaction cho repository và step, cấu hình đúng datasource và transaction manager, rồi xác nhận bằng integration test. Trong hệ thống nhiều datasource, nên dùng `@Qualifier` cho những bean như `jobRepository`, `businessTransactionManager` để tránh inject nhầm.

Ví dụ cấu hình chỉ định rõ một transaction manager cho step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
                PlatformTransactionManager businessTx,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, businessTx)
            .reader(reader)
            .writer(writer)
            .build();
}
```

Đoạn code cần import `org.springframework.beans.factory.annotation.Qualifier`. Nếu `businessTransactionManager` không điều khiển cùng datasource/transaction mà `JobRepository` dùng, phải hiểu rõ rủi ro dữ liệu đã commit nhưng metadata chưa commit. Khi cần tính nguyên tử trên hai database, hãy cân nhắc transaction management phân tán phù hợp hoặc thiết kế idempotent/outbox.

Không tăng bừa `transaction timeout` hoặc đổi isolation level để chữa mọi lỗi metadata. Deadlock, quá tải, optimistic locking và serialization error có nguyên nhân khác nhau; cần nhận diện đúng trước khi điều chỉnh.

## 8. Chiến lược idempotent writer chống trùng khi restart

Trong trường hợp không thể bảo đảm nguyên tử giữa dữ liệu và metadata, writer nên cho phép **chạy lại cùng item mà không tạo tác động trùng lặp**.

Ví dụ đơn hàng có `orderId` xác định duy nhất. Nếu database đích hỗ trợ unique constraint:

```sql
CREATE TABLE processed_order (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

Một chiến lược là dùng **upsert** theo `order_id`; nếu xử lý lại đơn hàng với cùng dữ liệu, bản ghi cuối vẫn đúng. Cú pháp upsert khác nhau theo PostgreSQL, MySQL, SQL Server, Oracle; không dùng cùng một câu SQL cho mọi database.

Ví dụ PostgreSQL, minh họa idempotency theo khóa nghiệp vụ:

```sql
INSERT INTO processed_order(order_id, amount, processed_at)
VALUES (:orderId, :amount, :processedAt)
ON CONFLICT (order_id)
DO UPDATE SET
    amount = EXCLUDED.amount;
```

Lưu ý: giữ nguyên `processed_at` trong trường hợp update là một lựa chọn nghiệp vụ ở ví dụ; nếu có timestamp audit khác, quy tắc cập nhật phải được quyết định rõ. **Upsert không tự giải quyết mọi vấn đề:** nếu writer cộng dồn số dư, phát email, chuyển tiền hoặc gọi API tính phí, gửi lại cùng item có thể tạo tác động mới. Khi đó cần một **idempotency key** được hệ thống đích công nhận, hoặc cơ chế outbox/inbox với deduplication bền vững.

Ví dụ key cho một side effect:

```text
idempotencyKey = jobName + ":" + businessDate + ":" + businessEntityId
```

Nên gắn key với **công việc logic** để restart của cùng `JobInstance` tạo cùng key, thay vì dùng `jobExecutionId`: ID này đổi mỗi lần restart và sẽ khiến hệ thống đích coi cùng nghiệp vụ là yêu cầu mới. Tất nhiên, quy tắc key phải phản ánh domain; một entity có thể hợp lệ phát sinh nhiều giao dịch khác nhau nếu nghiệp vụ yêu cầu.

## 9. Quy trình xử lý khi production báo lỗi cập nhật metadata

Khi log cho biết lỗi `JobRepository` hoặc database metadata mất kết nối, quy trình nên ưu tiên **xác minh dữ kiện trước khi restart**:

### Bước 1 — Khoanh vùng execution

Thu thập:

- `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId`.
- Identifying `JobParameters` (trong phạm vi được phép lưu/hiển thị), kỳ dữ liệu và thời điểm bắt đầu.
- Loại exception, chuỗi cause, SQLState/vendor error code, thời điểm lỗi.
- Tình trạng pod/JVM/worker và DB/connection pool tại thời điểm lỗi.
- Dấu vết side effect: bản ghi đích, request ID, message ID, file output hoặc external API response.

Không bắt đầu bằng việc sửa `STATUS` trong database. Một execution vẫn `STARTED` có thể đang xử lý thực sự trên node khác, hoặc chưa rõ bên đích đã commit hay chưa.

### Bước 2 — Đọc lại metadata từ nguồn bền vững

Dùng `JobExplorer` hoặc query chỉ đọc trong một transaction/connection mới. Kiểm tra `JobExecution`, `StepExecution`, `VERSION`, `LAST_UPDATED` và trạng thái context/checkpoint liên quan.

Tình huống cần phân biệt:

| Quan sát | Câu hỏi tiếp theo |
| --- | --- |
| `STARTED` nhưng process đã chết | Lần commit cuối là lúc nào? Có tác dụng ngoài transaction chưa được xác nhận không? |
| `FAILED` có checkpoint hợp lệ | Có thể restart theo thiết kế job không? Dữ liệu đích đã ghi ở mức nào? |
| `COMPLETED` nhưng launcher/log trả lỗi | Có khả năng commit hoàn tất nhưng client không nhận kết quả không? |
| Không có row `JobExecution` mới | Failure xảy ra trước hay trong transaction tạo execution? Có node khác đã launch cùng instance không? |
| `VERSION` conflict | Có concurrent writer đến cùng execution hay đối tượng stale không? |
| Context không deserialize được | Serializer/schema có tương thích deployment trước? Dữ liệu context nào gây lỗi? |

### Bước 3 — Đối chiếu side effect nghiệp vụ

Đếm và so sánh các khóa nghiệp vụ trong dữ liệu đích với checkpoint đã commit, ví dụ “đơn hàng đến `orderId=500` đã xử lý chưa”. Nếu có hệ thống ngoài, kiểm tra trạng thái request bằng idempotency key hoặc correlation ID; không gọi lại API chỉ vì log cuối cùng chưa thấy phản hồi.

### Bước 4 — Khôi phục hạ tầng rồi quyết định recovery

Đảm bảo database metadata đã ổn định, quyền/schema/connection pool hoạt động, không còn một execution khác đang thực thi cùng công việc. Sau đó:

- **Restart bình thường:** khi execution ở trạng thái restartable, checkpoint đáng tin cậy, writer idempotent hoặc side effect chưa commit.
- **Đối soát và replay có kiểm soát:** khi dữ liệu đã ghi nhưng checkpoint thiếu, dùng deduplication hoặc sửa sai nghiệp vụ trước khi chạy lại.
- **Khôi phục execution mồ côi:** khi process đã chết và metadata vẫn `STARTED`, cần quy trình recovery phù hợp phiên bản, kiểm tra tính hợp lệ checkpoint trước khi cho phép restart.
- **Dừng để điều tra:** khi kết quả commit chưa thể xác định hoặc dữ liệu có thể bị nhân đôi nghiêm trọng, không ép hệ thống chạy tiếp bằng cách đổi `JobParameters`.

### Bước 5 — Theo dõi lần chạy lại

Giữ nguyên identifying `JobParameters` nếu mục tiêu là **restart cùng `JobInstance`**. Quan sát `JobExecution` mới, các `StepExecution` tương ứng, checkpoint, số bản ghi được ghi thật và tín hiệu duplicate. Lưu audit trail: ai quyết định replay, dựa trên dữ kiện nào, đã đối soát những gì và trạng thái cuối.

## 10. Đọc trạng thái thực thi qua `JobExplorer`

Một service chỉ đọc giúp công cụ vận hành truy vấn lại execution từ repository. Ví dụ dành cho Spring Batch 5.2.x:

```java
import java.util.Comparator;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class MetadataIncidentInspector {
    private final JobExplorer jobExplorer;

    public MetadataIncidentInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long executionId) {
        JobExecution job = jobExplorer.getJobExecution(executionId);
        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + executionId);
        }

        System.out.printf(
                "job=%s jobExecutionId=%d status=%s exit=%s%n",
                job.getJobInstance().getJobName(),
                job.getId(),
                job.getStatus(),
                job.getExitStatus().getExitCode());

        job.getStepExecutions().stream()
                .sorted(Comparator.comparing(StepExecution::getStepName))
                .forEach(step -> System.out.printf(
                        "step=%s stepExecutionId=%d status=%s " +
                        "read=%d write=%d commit=%d rollback=%d%n",
                        step.getStepName(),
                        step.getId(),
                        step.getStatus(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount(),
                        step.getRollbackCount()));
    }
}
```

Đoạn ví dụ dùng `System.out` để thấy kết quả; trong ứng dụng thật, nên xuất structured log/DTO có quyền truy cập phù hợp. `getJobExecution(...)` trả `null` nếu ID không tồn tại. Các counter phản ánh metadata đã được lưu, không nhất thiết bao gồm side effect ngoài transaction.

**Lưu ý:** chỉ đọc `StepExecution` qua API không có nghĩa đã xác minh tất cả `ExecutionContext`. Khi quyết định restart, phải kiểm tra thêm checkpoint và dữ liệu đích qua cơ chế đã được ứng dụng thiết kế; không diễn giải `readCount`/`writeCount` như bằng chứng tuyệt đối về số bản ghi nghiệp vụ duy nhất.

## 11. SQL chẩn đoán metadata — chỉ đọc

Với JDBC `JobRepository` và table prefix mặc định `BATCH_`:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.VERSION AS JOB_VERSION,
    je.STATUS AS JOB_STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME AS JOB_CREATE_TIME,
    je.START_TIME AS JOB_START_TIME,
    je.END_TIME AS JOB_END_TIME,
    je.LAST_UPDATED AS JOB_LAST_UPDATED,
    se.STEP_EXECUTION_ID,
    se.VERSION AS STEP_VERSION,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.LAST_UPDATED AS STEP_LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :executionId
ORDER BY se.STEP_EXECUTION_ID;
```

`:executionId` là named parameter của công cụ như `NamedParameterJdbcTemplate`. Trong SQL client, sử dụng cú pháp bind tương ứng. Nếu schema có table prefix tùy chỉnh hoặc được nâng cấp khác phiên bản, điều chỉnh tên bảng/cột theo schema đang vận hành.

Thông tin cần chú ý:

- `JOB_VERSION`/`STEP_VERSION` giúp nhận diện thay đổi metadata và điều tra optimistic locking.
- `JOB_LAST_UPDATED`/`STEP_LAST_UPDATED` cho thấy lần metadata được lưu gần đây, **không phải heartbeat chắc chắn**; long-running tasklet có thể chưa commit trong một thời gian dài.
- `COMMIT_COUNT`/`ROLLBACK_COUNT` mô tả hành vi transaction được framework ghi nhận, **không xác minh** side effect đã xảy ra trong external API.
- `STARTED` hoặc `UNKNOWN` cần đi kèm xác minh process thực tế; không tự sửa bằng lệnh SQL `UPDATE`.

### Cần tránh gì?

**Không** chạy các cách “khắc phục nhanh” như:

```sql
-- KHÔNG THỰC THI: minh họa thao tác nguy hiểm.
UPDATE BATCH_JOB_EXECUTION
SET STATUS = 'FAILED'
WHERE JOB_EXECUTION_ID = :executionId;

-- KHÔNG THỰC THI: mất checkpoint và phá lịch sử restart.
DELETE FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID = :stepExecutionId;
```

Chúng bỏ qua quy tắc version, transaction, trạng thái còn lại và phụ thuộc giữa các bảng. Chỉ thực hiện recovery metadata khi có quy trình chuẩn của ứng dụng và đã xác nhận execution không còn chạy, checkpoint có thể dùng lại và dữ liệu đã được đối soát.

## 12. Job còn `STARTED` sau crash: cách hiểu đúng

Một số lỗi metadata khiến process không thể ghi trạng thái `FAILED`; một crash đột ngột cũng có thể khiến status vẫn `STARTED`. Lệnh launch/restart thông thường có thể từ chối tạo execution mới cho cùng `JobInstance` vì repository tin rằng execution trước còn chạy.

Đừng thay identifying parameter bằng timestamp/UUID để “né” lỗi; như vậy sẽ tạo **JobInstance mới** và có thể xử lý lại toàn bộ dữ liệu, làm mất ý nghĩa checkpoint.

Ở **Spring Batch 5.2.x**, tài liệu Spring Batch mô tả trường hợp process chết không graceful shutdown: trạng thái có thể còn `STARTED` và người vận hành phải xác định execution thực sự đã dừng, sau đó dùng quy trình được kiểm soát để chuyển sang trạng thái cho phép recovery nếu checkpoint hợp lệ. `ABANDONED` không đồng nghĩa `FAILED`: một execution/job bị `ABANDONED` không đi qua luồng restart thông thường như execution có `FAILED`.

Ở **Spring Batch 6.x**, API `JobOperator.recover(jobExecution)` được tài liệu hóa cho tình huống cần phục hồi execution không được kết thúc sạch trước khi restart. **Không dùng nguyên xi ví dụ 6.x cho dự án 5.2.x**; chọn cách phục hồi mà phiên bản đang chạy hỗ trợ và giữ đầy đủ audit.

Thao tác recovery phải thực hiện **sau khi** biết worker cũ không còn sống và tác động nghiệp vụ đủ an toàn để tiếp tục. Một execution “mồ côi” ở database có thể thực ra là job còn chạy nhưng bị đứt đường truyền với dashboard.

## 13. Phòng ngừa lỗi metadata và giảm tác động

### 13.1. Tách giám sát hạ tầng metadata

Theo dõi connection pool, khả năng truy cập DB, lock wait/deadlock, query latency, transaction timeout và storage capacity của `JobRepository`. Cấu hình cảnh báo riêng cho database metadata, không chỉ đo trạng thái nghiệp vụ ở bảng đích.

Mỗi log lỗi metadata nên có:

```json
{
  "eventType": "batch.metadata.update.failed",
  "jobName": "importOrders",
  "jobExecutionId": "4812",
  "stepName": "loadOrders",
  "stepExecutionId": "9207",
  "operation": "updateExecutionContext",
  "errorType": "DataAccessException",
  "sqlState": "08006",
  "message": "Could not persist batch checkpoint"
}
```

Đây là **ví dụ schema do ứng dụng quy định**, không phải một event Spring Batch tự động sinh đầy đủ. `sqlState` phụ thuộc driver/vendor. Không log raw `ExecutionContext` hoặc các tham số có chứa token, PII và dữ liệu nhạy cảm.

### 13.2. Giữ `ExecutionContext` nhỏ và tương thích

`ExecutionContext` nên lưu **checkpoint cần cho restart**, không phải toàn bộ object graph hoặc nội dung file lớn. Tránh lưu object không serialize được, object gắn với kết nối đang mở hoặc cấu trúc Java thay đổi không tương thích khi deploy. Khi thay serializer hoặc mô hình checkpoint, cần kế hoạch migration vì execution chưa hoàn tất có thể phải được restart bằng phiên bản ứng dụng mới.

### 13.3. Thiết kế cho replay an toàn

- Idempotent writer, unique business key và validation tại nơi ghi.
- Idempotency key cho API ngoài và hàng đợi, giữ key ổn định qua các lần restart của cùng nghiệp vụ.
- Outbox/inbox hoặc lưu trạng thái gửi ở nơi bền vững đối với side effect không có transaction chung.
- Giữ identifying `JobParameters` ổn định khi restart, không tự tăng `run.id` để xử lý trùng lỗi.
- Không đọc/ghi trực tiếp bảng metadata ngoài API/framework và quy trình recovery được phê duyệt.

### 13.4. Tránh update cùng một execution từ nhiều nơi

Không cho nhiều job runner cùng quản lý một `JobExecution`. Nếu dùng partitioning, cần để framework quản lý mỗi `StepExecution` của partition, không tái sử dụng object `StepExecution` có state mutable giữa các worker. Hạn chế code tự gọi `JobRepository.update` từ listener hoặc thread ngoài; nếu cần điều khiển job, dùng API quản trị phù hợp.

### 13.5. Cân nhắc độ tin cậy của metadata DB

JobRepository không nên dùng database transient nếu job phải restart sau crash. Backup và restore metadata cần đồng bộ với các quy tắc nghiệp vụ; **khôi phục metadata quá cũ** nhưng giữ dữ liệu đích mới có thể khiến chạy lại dữ liệu đã ghi. Cấu hình HA, retention và backup/restore phải được diễn tập theo tình huống recovery thực tế.

## 14. Kiểm thử lỗi cập nhật metadata

Một integration test về recovery có giá trị hơn việc chỉ mock `JobRepository.update(...)` ném exception. Mục tiêu cần kiểm chứng là **trạng thái dữ liệu đích, metadata và hành vi restart**, tức điều gì còn lại sau transaction thực sự.

Có thể thiết kế các tình huống sau trên **database test cô lập**:

| Kịch bản | Cách mô phỏng | Điều cần quan sát |
| --- | --- | --- |
| Metadata DB không khả dụng trước khi launch | Tạm ngắt datasource của repository | Không tạo được execution hợp lệ; không bắt đầu side effect |
| Mất kết nối khi update checkpoint | Inject fault ở proxy datasource/test fixture tại thời điểm phù hợp | Chunk rollback hay business commit riêng? Context persisted đến đâu? |
| `ExecutionContext` không serialize được | Dùng dữ liệu checkpoint không tương thích serializer trong test cô lập | Exception gây lỗi ở ranh giới ghi context, không được nuốt |
| Optimistic lock conflict | Tạo kịch bản cập nhật concurrent đến cùng execution dưới kiểm soát test | Có tín hiệu lỗi xung đột, không ghi đè version/stale state |
| External API đã nhận dữ liệu nhưng metadata thất bại | API stub ghi request theo idempotency key, làm lỗi repository | Restart không tạo side effect trùng |
| Process chết sau chunk commit | Kill worker test có kiểm soát sau thời điểm định trước | Repository còn gì, recovery có tiếp tục từ checkpoint hợp lệ? |
| DB báo commit lỗi/không rõ kết quả | Dùng failure injection vào commit/connection test | Recovery xác minh dữ liệu bền vững thay vì đoán outcome |

Test tích hợp nên kiểm tra bằng **một kết nối đọc mới** sau sự cố, không chỉ so object `JobExecution` còn trong JVM. Với API ngoài, stub có thể lưu danh sách idempotency key được chấp nhận và assert một nghiệp vụ không phát sinh side effect hai lần.

### Ví dụ kiểm tra invariant sau restart

Giả sử input gồm 200 order IDs và writer dùng khóa nghiệp vụ duy nhất. Sau khi cố ý gây lỗi giữa quá trình cập nhật metadata rồi thực hiện recovery có kiểm soát, test xác nhận:

```java
// Pseudocode cho integration test: dùng repository/test fixtures thực tế.
assertEquals(200, businessOrderRepository.count());
assertEquals(200, businessOrderRepository.countDistinctOrderIds());

JobExecution lastExecution = jobExplorer.getJobExecution(restartedExecutionId);
assertNotNull(lastExecution);
assertEquals(BatchStatus.COMPLETED, lastExecution.getStatus());
```

Đây là **pseudocode** vì `businessOrderRepository`, fault injection và quy trình restart là thành phần do dự án tự định nghĩa. Phép đếm 200 chỉ đúng nếu test thực sự kỳ vọng tất cả input thành công, không có filter/skip. `BatchStatus.COMPLETED` được dùng với import `org.springframework.batch.core.BatchStatus` trong Spring Batch 5.x.

Test đủ tốt còn cần đối chiếu lần chạy đầu, checkpoint, số lần gọi hệ thống ngoài và dữ liệu nghiệp vụ, tránh suy luận “không duplicate” chỉ từ tổng `writeCount`: count này là số item framework ghi nhận trên từng `StepExecution`, không phải số dòng đích duy nhất.

## 15. Những sai lầm thường gặp khi phục hồi

| Triệu chứng hoặc cách làm | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| `STARTED` lâu nên tự đổi thành `FAILED` | Worker có thể vẫn chạy, hoặc checkpoint chưa hợp lệ | Xác minh liveness, metadata và dữ liệu đích rồi dùng quy trình recovery |
| Thay `run.id` để chạy lại ngay | Tạo `JobInstance` mới, có thể xử lý lại từ đầu | Giữ identifying parameters khi cần restart đúng instance |
| Retry vô hạn mọi exception của repository | Có thể che optimistic locking, lỗi schema hoặc commit không rõ kết quả | Phân loại exception; chỉ retry khi tác vụ và transaction thực sự an toàn |
| Xóa bảng context để job “chạy tiếp” | Mất checkpoint, phá khả năng restart | Phục hồi metadata theo quy trình kiểm soát, có backup và đối soát |
| Tin log “write successful” là DB đã commit | Writer có thể ghi trong transaction chưa commit | Kiểm tra dữ liệu đã persisted và commit thực |
| Tin `COMPLETED` trong object Java | Trạng thái cuối có thể chưa commit vào repository | Đọc lại repository trên transaction/connection mới |
| Coi `LAST_UPDATED` cũ là bằng chứng process đã chết | Chunk/tasklet dài có thể không ghi metadata trong một thời gian | Kết hợp health, logs, metrics, thread/pod state |
| Dùng transaction manager khác cho data và metadata mà không xét rủi ro | Có thể phát sinh business commit / checkpoint rollback | Thiết kế transaction thống nhất, idempotency hoặc outbox |
| Tự sửa cột `VERSION` để bỏ lỗi lock | Bỏ qua optimistic locking, có nguy cơ ghi đè trạng thái đúng | Điều tra concurrent writers và stale entities |
| Không diễn tập lỗi DB trong CI/staging | Chỉ phát hiện duplicate/mất checkpoint khi production lỗi | Fault injection và xác minh invariant dữ liệu |
| Chỉ xem JobExecution status, bỏ qua StepExecution context | Khó biết điểm resume và số item đã commit | Đọc cả execution, context hợp lệ và dữ liệu đích |
| Bỏ qua metadata khi backup/restore | Restart sau restore có thể dựa trên trạng thái cũ | Đồng bộ chính sách backup, restore, retention và kiểm chứng khôi phục |

## 16. Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring a JobRepository, transaction configuration](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html)
- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch 5.2 — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — Transaction Attributes](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/transaction-attributes.html)
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html)
- [Spring Batch 5.2 — Advanced Metadata Usage và xử lý process chết](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/5.2/schema-appendix.html)
- [Spring Batch 5.2 API — `JobRepository`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/repository/JobRepository.html)
- [Spring Batch 5.2 API — `JobExplorer`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)
- [Spring Batch 6 — Advanced Metadata Usage, recovering a job](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)

Khi cập nhật metadata thất bại, cần đánh giá đồng thời **execution thực sự còn sống không**, **metadata nào đã commit**, **dữ liệu nghiệp vụ nào đã có tác động**, và **checkpoint nào có thể tin cậy để restart**. `JobRepository` lưu trạng thái để framework khôi phục, nhưng không thể tự hoàn tác những side effect nằm ngoài transaction. Vì vậy, transaction boundary rõ ràng, writer idempotent, sự kiện log có execution ID, quy trình đối soát và recovery có kiểm soát là nền tảng để một Spring Batch job có thể phục hồi an toàn sau sự cố metadata.
