# Không kill process giữa critical write trong Spring Batch

## 1. Bài toán: dừng một batch job mà không làm hỏng dữ liệu

Trong **Spring Batch Core Processing**, một job có thể đang ghi dữ liệu thanh toán, cập nhật hàng triệu bản ghi, tạo file báo cáo hoặc gửi thông điệp sang hệ thống khác. Khi cần triển khai phiên bản mới, bảo trì máy chủ, thu hồi pod hoặc hủy một lần chạy sai, thao tác **kill process ngay lập tức** có thể xảy ra đúng lúc một đoạn ghi dữ liệu quan trọng (*critical write*) đang thực hiện.

Một số hậu quả điển hình:

- Database đã commit dữ liệu nghiệp vụ nhưng tiến độ batch chưa được ghi nhận đầy đủ.
- Một API bên ngoài đã xử lý giao dịch, nhưng JVM bị dừng trước khi nhận và lưu phản hồi.
- File xuất dữ liệu mới ghi được một nửa đã bị hệ thống khác đọc như một file hoàn chỉnh.
- Một chunk chưa commit bị rollback; sau restart nó được xử lý lại, dẫn đến side effect trùng nếu writer không idempotent.
- Metadata trong `JobRepository` còn hiển thị `STARTED` vì tiến trình biến mất mà không cập nhật trạng thái cuối.

Nguyên tắc vận hành là: **yêu cầu job dừng có kiểm soát, đợi ranh giới ghi an toàn, xác nhận trạng thái bền vững, rồi mới dừng tiến trình**. Đồng thời, hệ thống phải có khả năng phục hồi nếu JVM vẫn bị buộc dừng do lỗi máy, mất điện, `SIGKILL` hoặc hết thời gian grace period. Không có cơ chế ứng dụng nào bảo đảm hệ điều hành sẽ không bao giờ kết thúc process trong một critical write.

Trong chương **Execution control**, mục tiêu không chỉ là biết lệnh nào dừng job, mà còn phải thiết kế ranh giới transaction, tín hiệu stop, thời gian chờ và cách restart để giữ đúng kết quả nghiệp vụ.

## 2. Critical write là gì?

**Critical write** là một vùng xử lý mà nếu bị ngắt ở thời điểm không phù hợp, trạng thái được ghi vào một hoặc nhiều nơi có thể không còn thể hiện đúng kết quả công việc.

Ví dụ trong một job quyết toán:

```text
ItemReader
   |
   v
ItemProcessor
   |
   v
ItemWriter
   |
   +-- INSERT payment_ledger vào DB ---------+
   |                                          |
   +-- UPDATE transaction_status ------------+-- critical write
   |                                          |
   +-- Gửi request sang payment service ------+
   |
   v
Cập nhật Batch metadata / checkpoint
```

Độ nguy hiểm phụ thuộc vào **hệ thống chịu trách nhiệm commit**, không chỉ vào số dòng code. Hai lệnh SQL trên cùng connection và cùng transaction có thể được commit/rollback như một đơn vị. Nhưng một HTTP request không tự rollback cùng transaction JDBC.

| Loại write | Ranh giới an toàn có thể dựa vào | Rủi ro khi process chết giữa chừng |
| --- | --- | --- |
| Ghi database trong một transaction | Transaction đã commit hoặc rollback; outcome có thể cần xác minh | Client không biết commit thành công chưa; bước sau có thể chạy lại |
| Ghi nhiều database độc lập | Không mặc định có một commit chung | DB A đã commit, DB B chưa |
| Gọi HTTP/API thanh toán | Kết quả phía nhận và idempotency key của API | API xử lý thành công nhưng caller không kịp lưu trạng thái |
| Publish Kafka/RabbitMQ | Acknowledgment và transaction của broker nếu có | Đã gửi nhưng chưa nhận ack; retry phát lại |
| Ghi file xuất báo cáo | File tạm hoàn chỉnh, đóng file, công bố bằng rename/manifest | Consumer đọc file dở dang hoặc file đã công bố nhưng checkpoint chưa cập nhật |
| Ghi object storage | Upload hoàn tất và object/manifest được công bố | Upload chưa hoàn tất hoặc lần retry tạo object trùng |

Vì thế, “không kill giữa critical write” có hai tầng:

1. **Execution control:** chủ động trì hoãn việc dừng cho đến khi batch đi qua điểm an toàn.
2. **Data correctness:** thiết kế write có transaction, idempotency và cơ chế đối soát để vẫn phục hồi được khi dừng đột ngột.

Không thể thay tầng thứ hai bằng một lời hứa “vận hành sẽ không bao giờ kill giữa chừng”.

## 3. Phân biệt stop, graceful shutdown và kill

| Thao tác | Cách hoạt động | Điều nó bảo đảm |
| --- | --- | --- |
| Yêu cầu dừng qua `JobOperator.stop(executionId)` | Đánh dấu yêu cầu stop; Spring Batch và step hợp tác dừng ở điểm có thể kiểm tra tín hiệu | Cho job **cơ hội** hoàn tất công việc đang chạy và chuyển trạng thái |
| Graceful shutdown của ứng dụng/JVM | Process nhận tín hiệu kết thúc, chạy shutdown lifecycle/hooks trong giới hạn cho phép | Có thể dọn tài nguyên nếu thời gian và lifecycle được cấu hình phù hợp |
| `SIGTERM` trên Linux | Yêu cầu process kết thúc; JVM thường bắt đầu shutdown thông thường | Không tự động tương đương `JobOperator.stop`; không bảo đảm job/chunk đã hoàn tất |
| `SIGKILL` / kill cưỡng bức | OS chấm dứt process không cho chạy cleanup của JVM | Không chạy `finally`, shutdown hook hoặc cleanup application |
| Pod bị force delete, node mất nguồn | Process biến mất ngoài dự kiến | Chỉ các dữ liệu đã được hệ thống lưu trữ bền vững xác nhận mới có thể tin cậy |

Một request stop **không phải** lời xác nhận rằng job đã dừng. Ví dụ, `JobOperator.stop(123L)` có thể trả về sau khi yêu cầu được gửi đi, trong khi `JobExecution` vẫn ở trạng thái `STOPPING` hoặc `STARTED` và writer vẫn đang chạy.

Phân biệt các trạng thái thông dụng:

- `STARTED`: batch đang thực thi theo metadata được ghi nhận.
- `STOPPING`: đã có yêu cầu dừng, nhưng chưa hoàn tất quá trình dừng.
- `STOPPED`: job đã dừng theo cơ chế có kiểm soát, có thể là ứng viên để restart nếu cấu hình cho phép.
- `COMPLETED`: job hoàn thành bình thường; không phải một “stop” cần restart.
- `FAILED`: thực thi kết thúc do lỗi; có thể restart nếu job/step được thiết kế restartable.
- `UNKNOWN` hoặc metadata kẹt ở `STARTED` sau crash: cần điều tra trạng thái thực tế trước khi quyết định chạy tiếp.

**Lưu ý:** trạng thái trong `JobRepository` là dữ liệu quan sát, không phải một khóa bảo vệ tuyệt đối trước kill từ bên ngoài. Nếu node chết, tiến trình không còn khả năng ghi trạng thái `FAILED` hay `STOPPED`.

## 4. Chunk transaction là ranh giới dừng tự nhiên

Với Spring Batch chunk-oriented step, reader/processor tạo một nhóm item; writer ghi chúng trong một transaction của chunk. Khi transaction thành công, dữ liệu và trạng thái checkpoint thích hợp được commit theo cấu hình repository và transaction manager.

```text
Chunk #1
  READ -> PROCESS -> WRITE -> COMMIT   [điểm an toàn]

Chunk #2
  READ -> PROCESS -> WRITE -> COMMIT   [điểm an toàn]

Chunk #3
  READ -> PROCESS -> WRITE -> COMMIT   [điểm an toàn]

                     ^ stop request đến trong WRITE của Chunk #2
                     |
                     +-- job cần cơ hội kết thúc chunk hiện tại,
                         ghi trạng thái rồi mới dừng
```

Với các step chunk chuẩn, Spring Batch kiểm tra tín hiệu dừng ở những điểm điều phối thích hợp. Một yêu cầu stop thường không ép cắt ngang câu lệnh SQL đang chạy. Tuy nhiên, **đừng dựa vào điều này để cho rằng mọi thao tác đang ghi chắc chắn được commit**: timeout của connection, rollback, exception, shutdown JVM và tài nguyên ngoài transaction vẫn có thể tác động.

Ví dụ cấu hình step trên Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step persistPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ItemProcessor<Payment, Payment> processor,
        ItemWriter<Payment> writer) {

    return new StepBuilder("persistPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Payment` ở đây là model ví dụ của ứng dụng. Cấu hình này tạo một chunk 100 item (ngoại trừ chunk cuối) và đặt transaction boundary quanh phần xử lý chunk. Muốn bảo vệ các SQL write của writer, writer phải sử dụng **DataSource và transaction manager được nối đúng với transaction của step**. Nếu writer gọi một database thứ hai hoặc một API bên ngoài, transaction của step không tự biến các thao tác đó thành một giao dịch nguyên tử.

**Chọn kích thước chunk là một cân bằng:**

- Chunk lớn có thể giảm chi phí commit nhưng kéo dài khoảng thời gian cần chờ để dừng an toàn.
- Chunk nhỏ làm điểm kiểm tra stop xuất hiện thường xuyên hơn, nhưng tăng overhead transaction.
- Một writer mất nhiều phút cho một lệnh I/O đơn lẻ vẫn có thể làm graceful stop chậm, dù chunk size nhỏ.

Nên đo **thời gian chunk dài nhất trong điều kiện tải thực tế**, thay vì suy ra thời gian dừng từ số lượng item.

## 5. Quy trình dừng job an toàn ở tầng ứng dụng

Một trình tự vận hành phù hợp cho batch đang xử lý nghiệp vụ quan trọng:

1. **Ngăn khởi tạo execution mới:** scheduler/launcher ngừng cấp job mới hoặc chuyển instance vào chế độ drain.
2. **Xác định execution đang chạy:** lấy `executionId` và kiểm tra `JobRepository` hoặc `JobExplorer`.
3. **Gửi yêu cầu stop qua Spring Batch:** sử dụng `JobOperator.stop(executionId)` khi JVM chứa execution vẫn hoạt động.
4. **Chờ xác nhận:** quan sát trạng thái chuyển từ `STARTED`/`STOPPING` sang `STOPPED`, hoặc `COMPLETED` nếu job kịp hoàn tất; xử lý `FAILED` theo quy trình lỗi.
5. **Xác minh critical write đã qua điểm bền vững:** transaction không còn đang mở, file chưa hoàn tất chưa được publish, outbox/operation state nhất quán.
6. **Kết thúc process theo cách graceful:** sau khi không còn execution cần xử lý, mới cho scheduler/container/service tắt.
7. **Ghi dấu vết vận hành:** lưu người/tác nhân yêu cầu, thời điểm, execution ID, kết quả dừng và quyết định restart.

Ví dụ gọi API quản trị Spring Batch (Spring Batch 5.x):

```java
import org.springframework.batch.core.launch.JobOperator;

public class BatchStopService {

    private final JobOperator jobOperator;

    public BatchStopService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public void requestStop(long executionId) throws Exception {
        // Gửi yêu cầu dừng; chưa thể kết luận job đã STOPPED.
        jobOperator.stop(executionId);
    }
}
```

Code trên giả định context cung cấp `JobOperator` đã cấu hình đúng. Trong ứng dụng thực tế, controller/CLI của admin cần xác thực, phân quyền và ghi audit. Đừng công khai thao tác stop trên một HTTP endpoint không bảo vệ.

Một vòng quan sát đơn giản dùng `JobExplorer`:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);
if (execution == null) {
    throw new IllegalArgumentException("Unknown execution: " + executionId);
}

BatchStatus status = execution.getStatus();
// STOPPED hoặc COMPLETED: job đã kết thúc theo metadata quan sát được.
// STOPPING/STARTED: tiếp tục quan sát, chưa được xem là dừng xong.
// FAILED/UNKNOWN: chuyển sang điều tra, đối soát và recovery.
```

Vòng quan sát cần có **deadline vận hành**, logging và refresh dữ liệu từ repository sau mỗi lần kiểm tra. Không nên giữ mãi một object `JobExecution` đã đọc trước đó vì trạng thái trong object cũ có thể không tự được cập nhật. Cũng không nên bận chờ bằng vòng lặp không nghỉ.

Nếu chương trình là batch CLI chạy một job rồi thoát ngay, stop từ một JVM quản trị khác chỉ hữu ích khi execution đang chạy còn có khả năng nhận và xử lý yêu cầu stop. Cần thiết kế kênh điều khiển thực tế trước khi đặt kỳ vọng vào lời gọi API.

## 6. Khi cần dừng giữa một writer rất dài

Không phải step nào cũng có các chunk ngắn. Tasklet có thể tạo file nhiều GB hoặc writer có thể chờ một request mạng rất lâu. Khi đó, chờ ranh giới chunk có thể không đáp ứng được grace period.

Các hướng thiết kế:

- **Chia công việc thành checkpoint nhỏ:** tách một critical write kéo dài thành các đơn vị có transaction và trạng thái hoàn tất rõ ràng.
- **Đặt timeout có chủ đích:** HTTP client, JDBC socket/query và các thao tác I/O phải có timeout phù hợp; timeout không được nhỏ hơn thời gian xử lý hợp lệ của một đơn vị công việc.
- **Kiểm tra tín hiệu dừng ở các điểm an toàn:** trong vòng lặp dài, chỉ ngừng sau khi đã hoàn thành hoặc rollback được một đơn vị ghi.
- **Không nuốt `InterruptedException` một cách mù quáng:** khi có tín hiệu interrupt, cần xử lý theo contract của tài nguyên và bảo toàn interrupt flag nếu không thể hoàn tất ở tầng đó.
- **Dùng trạng thái durable cho mỗi đơn vị:** xác định operation nào đã commit, operation nào còn pending, operation nào cần đối soát.

Ví dụ tasklet tạo file trong một vòng lặp không nên chỉ kiểm tra stop ở cuối một file nhiều giờ. Nó có thể ghi các block được checkpoint, xuất file tạm chưa công bố và chỉ đưa file vào danh sách tiêu thụ khi toàn bộ file hoàn tất.

Không phải mọi lời gọi `Thread.interrupt()` đều có thể ngắt an toàn SQL hoặc HTTP request. Hành vi cụ thể phụ thuộc driver, client, transaction và timeout. **Không dùng interrupt cưỡng bức như một cơ chế đảm bảo tính nguyên tử**.

## 7. Bảo vệ critical write vào database

### 7.1. Gom những thay đổi liên quan trong một transaction

Với một payment event, nghiệp vụ có thể cần ghi ledger và đánh dấu đã xử lý:

```sql
BEGIN;

INSERT INTO payment_ledger (operation_id, account_id, amount)
VALUES (:operationId, :accountId, :amount);

UPDATE payment_request
SET status = 'POSTED'
WHERE operation_id = :operationId;

COMMIT;
```

Đây là ví dụ minh họa cho hai thao tác trên **cùng database và cùng transaction**. Nếu connection bị đóng trước commit, hệ quản trị database có thể rollback transaction chưa commit. Nhưng nếu process chết ngay sau khi database commit mà trước khi client nhận xác nhận, client không biết chắc lệnh đã thành công hay chưa.

Vì vậy, **“transactional” và “idempotent” giải quyết hai vấn đề khác nhau**:

- Transaction bảo đảm các thay đổi trong cùng phạm vi commit/rollback theo quy tắc của database.
- Idempotency bảo đảm khi cùng một yêu cầu hợp lệ bị phát lại, hiệu ứng nghiệp vụ không bị tạo thêm lần nữa.

### 7.2. Dùng khóa nghiệp vụ để cho phép retry an toàn

Ví dụ PostgreSQL:

```sql
CREATE TABLE payment_ledger (
    operation_id VARCHAR(100) PRIMARY KEY,
    account_id   VARCHAR(100) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL
);
```

Writer có thể nhận một event lặp lại sau restart:

```sql
INSERT INTO payment_ledger (operation_id, account_id, amount)
VALUES (:operationId, :accountId, :amount)
ON CONFLICT (operation_id) DO NOTHING;
```

Unique constraint tạo rào chắn chống việc ghi trùng, kể cả khi hai worker cùng thử insert. Tuy nhiên `DO NOTHING` không phát hiện trường hợp một `operationId` cũ được gửi lại với `amount` khác. Nếu đó là xung đột nghiệp vụ, cần so sánh payload và báo lỗi/quarantine, thay vì âm thầm bỏ qua.

Ví dụ `ItemWriter` sử dụng `JdbcTemplate`, phù hợp cho minh họa Spring Batch 5.x:

```java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
ItemWriter<Payment> paymentWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (Payment payment : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO payment_ledger
                        (operation_id, account_id, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT (operation_id) DO NOTHING
                    """,
                    payment.operationId(),
                    payment.accountId(),
                    payment.amount()
            );
        }
    };
}
```

Ví dụ giả định `Payment` là một Java record có ba accessor tương ứng và database là PostgreSQL. Cần kết nối `JdbcTemplate` vào transaction mà step sử dụng. Nếu chỉ nhìn `StepExecution.getWriteCount()`, đừng mặc định nó bằng số dòng **mới** trong ledger: writer có thể đã nhận item nhưng database bỏ qua do trùng khóa.

### 7.3. Ranh giới commit với JobRepository

Spring Batch cập nhật metadata checkpoint và các bộ đếm thông qua `JobRepository`. Trong cấu hình chuẩn, framework phối hợp các cập nhật đó với transaction của chunk; nhưng tính nhất quán phụ thuộc cấu hình thực tế của `DataSource`, `PlatformTransactionManager` và mức độ tham gia transaction.

Nếu business write ở DB A, còn metadata batch ở DB B, không thể giả định hai nơi sẽ commit nguyên tử chỉ vì cùng chạy trong một step. Khi cần chịu lỗi giữa hai kho dữ liệu, hãy thiết kế retry/idempotency và reconcile tương ứng, hoặc chọn một cơ chế điều phối transaction được kiểm chứng.

## 8. Critical write có tác động bên ngoài: Outbox và idempotency key

Ví dụ writer vừa lưu kết quả trong database vừa gọi API chuyển tiền:

```text
BEGIN DB TRANSACTION
  INSERT payment_result
  HTTP POST /transfer
COMMIT DB TRANSACTION
```

Đây là thiết kế dễ gặp rủi ro. API có thể đã chuyển tiền nhưng database rollback. Hoặc database commit nhưng process chết trước khi lưu kết quả response. Spring Batch không có khả năng tự rollback một giao dịch HTTP đã thực hiện ở hệ thống khác.

### 8.1. Transactional outbox

Một thiết kế thường dùng:

```text
Spring Batch chunk transaction
    |
    +-- INSERT business_result --------------+
    |                                        |  COMMIT trong cùng DB
    +-- INSERT outbox_event -----------------+
                                                  |
                                                  v
                                         Outbox dispatcher
                                                  |
                                                  v
                                         External API / Broker
                                                  |
                                                  v
                                         Mark delivered / retry
```

Phần nghiệp vụ và bản ghi outbox được lưu trong **cùng transaction**. Một worker khác gửi outbox ra ngoài. Nếu worker chết sau khi gửi nhưng trước khi đánh dấu delivered, nó có thể gửi lại sau restart. Bởi vậy, consumer/API nhận cần xử lý theo **idempotency key** bền vững.

Ví dụ bảng outbox:

```sql
CREATE TABLE payment_outbox (
    event_id      VARCHAR(100) PRIMARY KEY,
    operation_id  VARCHAR(100) NOT NULL,
    payload       JSONB NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING'
);
```

`event_id` nên được sinh một cách ổn định từ operation cần gửi, hoặc được lưu lại khi transaction nghiệp vụ lần đầu được tạo. Đừng dùng một UUID ngẫu nhiên mới ở mỗi lần retry của **cùng sự kiện**, vì downstream sẽ không nhận ra bản sao.

Một consumer có thể lưu `idempotency_key` cùng với kết quả xử lý vào database của chính nó và từ chối hiệu ứng lặp. Đây là cách hướng đến **effectively-once business outcome** trên nền truyền nhận ít nhất một lần; không nên tuyên bố rằng chỉ dùng outbox sẽ làm mọi message được giao đúng một lần về mặt mạng.

### 8.2. Timeout của API không có nghĩa là thất bại

Khi HTTP client timeout, có ít nhất hai khả năng:

1. Request chưa đến server hoặc server chưa thực hiện.
2. Server đã thực hiện thành công nhưng response đến trễ hoặc bị mất.

Trong tình huống (2), một retry dùng operation ID mới có thể tạo thêm giao dịch. Cần gửi lại **cùng idempotency key**, tra cứu kết quả khi API hỗ trợ và chỉ đánh dấu thất bại cuối cùng sau khi có bằng chứng. Stop an toàn cũng phải cho phép tác vụ đang ở trạng thái “không rõ outcome” được lưu và đối soát.

## 9. Ghi file an toàn: không công bố file dở dang

Với job xuất file CSV/JSON/báo cáo, consumer có thể quan sát thư mục output trong khi writer chưa ghi xong. Nếu writer ghi trực tiếp `report.csv`, một process kill có thể để lại file đã có tên chính thức nhưng chỉ chứa một phần dữ liệu.

Một quy trình an toàn hơn:

```text
1. Tạo report-<jobKey>.csv.tmp
2. Ghi toàn bộ nội dung vào file tạm
3. Flush và đồng bộ xuống storage nếu yêu cầu độ bền nghiêm ngặt
4. Đóng handle ghi
5. Publish bằng rename/move nguyên tử khi filesystem hỗ trợ
6. Ghi nhận manifest/checkpoint bền vững
7. Chỉ cho consumer đọc file có tên final hoặc có manifest hoàn tất
```

Ví dụ Java:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public void publishReport(Path outputDirectory, String content)
        throws IOException {

    Path temp = Files.createTempFile(
            outputDirectory, "report-", ".tmp");
    Path finalFile = outputDirectory.resolve("report.csv");

    try {
        Files.writeString(temp, content, StandardCharsets.UTF_8);

        // Ví dụ yêu cầu atomic move; không âm thầm fallback sang
        // move không nguyên tử nếu contract cần atomic publication.
        Files.move(temp, finalFile, StandardCopyOption.ATOMIC_MOVE);
    } catch (AtomicMoveNotSupportedException unsupported) {
        // Chọn chiến lược publish khác phù hợp filesystem.
        throw unsupported;
    } finally {
        // Nếu move thành công, temp không còn; nếu thất bại, dọn file tạm.
        Files.deleteIfExists(temp);
    }
}
```

Đoạn code nhằm diễn tả **công bố bằng atomic move**, không phải một giải pháp đầy đủ cho durability, trùng tên hoặc nhiều process cùng ghi. `Files.writeString` đóng file sau thao tác ghi, nhưng không mặc định bảo đảm dữ liệu đã được `fsync` xuống thiết bị vật lý. Hệ thống đòi hỏi khả năng chịu mất điện cần bổ sung `FileChannel.force(...)`/đồng bộ thư mục theo khả năng OS và filesystem; với network filesystem hoặc object storage, semantics của rename có thể khác.

Cần nghĩ thêm về điểm chết **sau khi rename thành công nhưng trước checkpoint**. Lần restart có thể tạo lại file. Vì vậy nên:

- Đặt tên final dựa trên khóa nghiệp vụ/job instance ổn định.
- Không ghi đè một file đã publish nếu contract không cho phép.
- Lưu checksum, record count và manifest trạng thái để đối soát.
- Cho bước restart kiểm tra output đã hoàn tất trước khi ghi lại.

Nếu dùng `FlatFileItemWriter` của Spring Batch, hãy tìm hiểu cách writer lưu state trong `ExecutionContext` và chính sách append/restart cụ thể. Khả năng restart của writer và việc **công bố file cho consumer** là hai trách nhiệm cần thiết kế riêng.

## 10. Kubernetes và thời gian cho graceful termination

Một pod bị xóa hoặc thay thế thường nhận yêu cầu kết thúc. Kubernetes cho container một khoảng grace period; khi hết hạn, runtime có thể chấm dứt cưỡng bức các process còn tồn tại.

Ví dụ cấu hình:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: payment-batch
spec:
  terminationGracePeriodSeconds: 180
  containers:
    - name: batch
      image: your-registry/payment-batch:version
```

`180` giây chỉ là **ví dụ**, không phải khuyến nghị áp dụng cho mọi job. Grace period phải dựa vào thời gian dừng đo được, thời gian commit/rollback và timeout hợp lệ của dependency. Với một chunk có thể mất 10 phút, đặt 180 giây không bảo đảm chunk được hoàn tất.

### 10.1. Drain trước khi pod bị dừng

Một hệ thống thực tế nên có trình tự:

```text
Deployment/Operator yêu cầu drain
      |
      v
Ngăn scheduler phân công job mới
      |
      v
Gửi stop cho execution đang chạy
      |
      v
Quan sát JobRepository + trạng thái write thật
      |
      v
Đến điểm an toàn (STOPPED/COMPLETED)
      |
      v
Cho pod kết thúc theo cách graceful
```

Có thể triển khai điều khiển drain qua operator riêng, công cụ quản trị nội bộ hoặc `preStop` hook. Tuy nhiên **preStop chạy trong grace-period budget** và chỉ hữu ích nếu endpoint/hook thực sự đợi cho đến khi write an toàn. Nếu hook chỉ gọi “request stop” rồi trả về ngay, container vẫn có thể nhận tín hiệu kết thúc trước khi chunk hoàn tất.

Ví dụ ý tưởng hook:

```yaml
lifecycle:
  preStop:
    exec:
      command:
        - /bin/sh
        - -c
        - "curl --fail --silent http://127.0.0.1:8080/internal/batch/drain"
```

Ví dụ này chỉ hoạt động khi image có `/bin/sh` và `curl`, ứng dụng có endpoint nội bộ được bảo vệ, và endpoint `/internal/batch/drain` **chỉ trả thành công sau khi job đã dừng an toàn**. Cần kiểm tra timeout, authentication, khả năng gọi endpoint khi shutdown, và phương án nếu endpoint không phản hồi. `preStop` không phải lớp bảo vệ cuối cùng trước node failure hoặc force kill.

### 10.2. Spring Boot graceful shutdown không tự “drain” mọi batch job

Trong Spring Boot có thể cấu hình:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=180s
```

Cấu hình trên giúp quản lý shutdown lifecycle của các component được hỗ trợ, đặc biệt với web server. Nó **không tự động biến mọi `JobExecution` đang chạy thành một execution `STOPPED`** hoặc làm một HTTP writer trở thành transaction nguyên tử. Một batch deployment cần tích hợp riêng việc ngăn job mới, yêu cầu stop, đợi writer/step ở điểm an toàn và sau đó tắt JVM.

Đừng dùng liveness probe làm một cơ chế hủy job nghiệp vụ thông thường: probe có thể khiến container bị khởi động lại khi còn một critical write. Readiness, liveness và điều kiện dừng phải được thiết kế theo vai trò của process.

### 10.3. Các nền tảng khác

Trên VM hoặc systemd service, ý tưởng tương tự: trước khi stop service, drain scheduler, request stop và đợi kết thúc. Với Windows service, cần xử lý tín hiệu/service lifecycle của Windows thay vì giả định có POSIX `SIGTERM`. Trên nền tảng nào cũng phải có timeout và quy trình xử lý khi job không thể dừng an toàn trong giới hạn.

## 11. Nếu process vẫn bị kill: xử lý thế nào sau crash?

Không có chiến lược graceful nào loại bỏ được tất cả lỗi hạ tầng. Một kịch bản khó là:

```text
T0: Step bắt đầu chunk #8
T1: Writer gửi lệnh commit lên database
T2: Database commit thành công
T3: JVM bị SIGKILL trước khi nhận kết quả và cập nhật đầy đủ trạng thái
T4: Hệ thống restart job
```

Ở T4, không thể chỉ dựa vào việc client trước đó không nhận được phản hồi để kết luận transaction chưa commit. **Outcome có thể không chắc chắn**.

Quy trình phục hồi nên dựa vào dấu vết bền vững:

1. Xác minh process cũ thực sự không còn chạy để tránh hai worker xử lý cùng một job.
2. Kiểm tra `JobRepository`, trạng thái `JobInstance`/`JobExecution` và checkpoint đã lưu.
3. Kiểm tra dữ liệu nghiệp vụ bằng `operationId` hoặc idempotency key, đối chiếu với expected result.
4. Kiểm tra các side effect ngoài database: outbox pending, API transaction đã xử lý, file đã publish, message đã được gửi.
5. Nếu metadata kẹt ở `STARTED` sau crash, dùng **quy trình recovery được dự án kiểm chứng** để reconcile trạng thái trước khi restart; không tự sửa các bảng `BATCH_*` tùy tiện.
6. Restart **cùng job instance** khi mục tiêu là tiếp tục từ checkpoint, hoặc tạo execution mới theo quy tắc nghiệp vụ khi mục tiêu là chạy lại từ đầu.
7. Xác nhận dữ liệu cuối cùng không bị nhân đôi và lưu lại kết quả điều tra.

### Tại sao không chỉ chạy lại với run.id mới?

`JobInstance` được xác định bởi tên job cộng các **identifying JobParameters**. Thêm `run.id` mới thường tạo instance mới; nó không tương đương cơ chế restart sử dụng checkpoint của lần chạy thất bại.

Nếu job có reader lưu `ExecutionContext`, việc restart đúng instance cho phép resume theo trạng thái đã lưu. Nhưng reader vẫn có thể phát lại một phần dữ liệu, đặc biệt khi external side effect không nằm trong cùng transaction. Bởi vậy, checkpoint và idempotency **bổ sung cho nhau**.

## 12. Chống chạy trùng khi một process cũ chưa chết hẳn

Một lần drain không thành công có thể dẫn đến tình huống:

```text
Worker A: đang xử lý operation 123, mất kết nối tạm
Orchestrator: tưởng A không còn hoạt động
Worker B: bắt đầu xử lý operation 123
Worker A: kết nối hồi phục, tiếp tục ghi
```

Chỉ nhìn heartbeat hoặc timeout có thể không đủ. Với các operation không được phép chạy đồng thời, có thể kết hợp:

- **Unique constraint/idempotency key** tại nơi tạo hiệu ứng cuối cùng.
- **Distributed lease/lock** có expiry và cơ chế làm mới được kiểm soát.
- **Fencing token** tăng đơn điệu để downstream từ chối writer cũ sau khi quyền sở hữu đã chuyển sang worker mới.
- **Single active execution policy** hoặc job-level lock được lưu trong hạ tầng tin cậy.

Lease có thể hết hạn khi process tạm dừng dài vì GC hoặc mạng chậm. Nếu worker cũ sau đó tiếp tục gửi write, chỉ một “lease expired” ở controller không nhất thiết ngăn nó. Fencing token cần được **kiểm tra ở tài nguyên nhận write** nếu muốn chặn writer đã mất quyền sở hữu.

Spring Batch quản lý metadata và trạng thái job, nhưng không thể tự thay thế cơ chế đồng bộ phân tán cho mọi loại tài nguyên ngoài nó.

## 13. Thiết kế test cho việc stop đúng lúc critical write

Một integration test chỉ chạy job đến `COMPLETED` không kiểm chứng tính an toàn khi dừng. Nên mô phỏng có kiểm soát:

| Test case | Điểm dừng/lỗi | Kỳ vọng |
| --- | --- | --- |
| S01 | Stop khi job đang đọc item | Job có thể tiến tới `STOPPED` mà không làm hỏng output |
| S02 | Stop khi writer đang thực hiện một chunk | Chunk hiện tại hoàn tất hoặc rollback đúng contract; không tạo dữ liệu dở dang |
| S03 | Dừng sau DB commit nhưng trước khi application ghi ack | Retry/restart không tạo duplicate theo business key |
| S04 | HTTP service trả thành công nhưng response bị mất | Gửi lại cùng idempotency key không tạo hiệu ứng lần hai |
| S05 | Crash trước khi file final được publish | Consumer không thấy file partial có tên final |
| S06 | Crash sau khi publish file nhưng trước checkpoint | Recovery nhận ra file đã tồn tại và xác minh checksum/manifest |
| S07 | Restart cùng `JobInstance` | Chỉ xử lý phần còn lại hoặc phát lại an toàn; không nhân đôi kết quả |
| S08 | Grace period ngắn hơn thời gian writer hợp lệ | Có cảnh báo rõ và phương án reconcile; không giả định stop đã xong |
| S09 | Hai worker cùng tranh một operation | Chỉ một hiệu ứng nghiệp vụ được commit |

### Dùng latch để đặt một điểm dừng có tính xác định

Thay vì dùng `Thread.sleep(500)` và hy vọng job tình cờ đang ở writer, có thể tạo một writer test wrapper dùng `CountDownLatch`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

final class BlockingWriter<T> implements ItemWriter<T> {

    final CountDownLatch enteredWrite = new CountDownLatch(1);
    final CountDownLatch allowWriteToContinue = new CountDownLatch(1);

    private final ItemWriter<T> delegate;

    BlockingWriter(ItemWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        enteredWrite.countDown();

        if (!allowWriteToContinue.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Writer was not released");
        }

        delegate.write(chunk);
    }
}
```

Trong test, chạy job bằng launcher cấu hình **bất đồng bộ** để test thread có thể tiếp tục. Đợi `enteredWrite` được báo, gọi `jobOperator.stop(executionId)`, rồi mở `allowWriteToContinue`. Sau đó quan sát execution cho đến trạng thái terminal và assert dữ liệu nghiệp vụ.

```text
Test thread                         Job thread
-----------                         ----------
launch async ---------------------> read/process
await enteredWrite                 enter writer; signal latch
request stop                       wait allowWriteToContinue
release writer -------------------> finish writer/commit or rollback
poll status                        observe stop at safe point
assert output and checkpoint
```

Đây là **kỹ thuật phối hợp test**, không phải writer cần triển khai trong production. Đừng giữ latch chờ vô hạn; giới hạn thời gian và bảo đảm luôn release trong `finally` để tránh treo test suite. Nếu muốn mô phỏng mất process thật, chạy test trong một **process/container độc lập** và database test riêng; tiêu diệt một process không thể được mô phỏng hoàn chỉnh bằng việc throw exception trong cùng JVM.

Với trường hợp force kill, bài test phải nhận diện các trạng thái outcome có thể xảy ra (chưa commit, đã commit nhưng ack mất), rồi xác nhận rằng cơ chế reconcile/idempotency vẫn đưa về một kết quả nghiệp vụ duy nhất.

## 14. Monitoring và runbook vận hành

Để operator quyết định có thể kết thúc process chưa, cần quan sát nhiều lớp:

| Tín hiệu | Giá trị vận hành |
| --- | --- |
| `jobExecutionId`, `jobName`, `JobParameters` | Xác định chính xác lần chạy đang dừng |
| `BatchStatus` và thời gian cập nhật gần nhất | Theo dõi stop progress, phát hiện execution có thể bị kẹt |
| Step hiện tại và chunk đang xử lý | Ước lượng thời gian chờ điểm an toàn |
| Thời gian chunk p95/p99 và dài nhất | Đặt grace period dựa trên số liệu |
| Transaction đang mở và lỗi commit | Phát hiện write kéo dài hoặc bất thường |
| Số operation `PENDING`, `IN_PROGRESS`, `COMMITTED` | Xác định công việc chưa được xác nhận bền vững |
| Outbox queue và độ trễ publish | Theo dõi side effect ngoài DB còn phải hoàn thành |
| File temp/final/manifest | Phân biệt file đang ghi với file đã công bố |
| Tần suất retry và duplicate-key | Phát hiện phát lại, race hoặc recovery sai |

Một runbook có thể quy định:

**Trước bảo trì:** ngăn scheduler cấp job mới, gửi stop, đợi tất cả execution chuyển sang `STOPPED` hoặc `COMPLETED`; ghi nhận những operation còn pending.

**Nếu quá thời hạn:** kiểm tra step bị kẹt, timeout I/O và điều kiện giao dịch; đánh giá có thể đợi thêm hay phải chấp nhận crash recovery. Không tự động coi `STOPPING` là “đã an toàn để kill”.

**Sau khi process không còn:** đối soát database, outbox, file output và metadata. Chỉ restart sau khi đã xác định không còn process cũ giữ quyền thực thi cùng workload và đã xử lý trạng thái chưa rõ outcome.

Trong môi trường sản xuất, mọi nút “Force stop” nên yêu cầu quyền phù hợp và ghi audit. Người vận hành cần nhìn thấy cảnh báo cụ thể về execution còn write dang dở, chứ không chỉ một nhãn “Running”.

## 15. Những hiểu lầm thường gặp

### “Gửi SIGTERM là an toàn tuyệt đối”

`SIGTERM` cho JVM cơ hội shutdown, nhưng code có thể chưa nhận stop theo cơ chế Spring Batch, writer có thể đang chờ I/O và grace period có thể hết. Cần quy trình drain/job stop thực sự cùng khả năng phục hồi sau force kill.

### “Chỉ cần @PreDestroy để commit transaction”

`@PreDestroy` và shutdown hook không chạy khi `SIGKILL`, process crash hoặc node mất nguồn. Cũng không nên khởi tạo transaction nghiệp vụ mới chỉ để che giấu một write còn dang dở. Transaction và idempotency phải được thiết kế trong luồng xử lý bình thường.

### “Cứ bật retry là không mất dữ liệu”

Retry có thể làm **trùng side effect** nếu thao tác đã thành công nhưng caller không biết. Retry phải đi kèm idempotency key hoặc phương thức reconciliation đáng tin cậy.

### “JobRepository vẫn STARTED nghĩa là JVM còn chạy”

Một process chết đột ngột có thể để metadata ở `STARTED`. Cần xác nhận trạng thái process, lease/quyền sở hữu và điều kiện restart; không dựa vào một trường status cũ để suy đoán toàn bộ thực tế.

### “JobRepository đã checkpoint nên mọi write ngoài DB chắc chắn đúng”

Checkpoint quản lý tiến độ batch. Một HTTP call, file rename hoặc message publish có cơ chế commit/ack độc lập. Cần bảo đảm idempotency hoặc outbox tại điểm tích hợp đó.

### “Đổi run.id để restart cho nhanh”

`run.id` mới thường tạo `JobInstance` mới, có thể chạy lại toàn bộ dữ liệu. Khi cần resume từ checkpoint, phải dùng cơ chế restart thích hợp với cùng instance và tham số định danh.

### “Bỏ qua mọi duplicate key error là được”

Trùng khóa có thể là lần phát lại hợp lệ hoặc xung đột dữ liệu nghiêm trọng. Chỉ bỏ qua khi contract cho phép và payload được xác minh; những trường hợp khác phải fail/quarantine.

### “Đặt chunk size = 1 sẽ không còn critical write”

Chunk nhỏ rút ngắn thời gian transaction trung bình nhưng vẫn có thể bị kill ngay lúc commit. Một item gọi API mất 30 giây vẫn là critical write dài, và crash sau commit trước ack vẫn có thể xảy ra.

## 16. Bài thực hành

**Bài 1 – Stop có kiểm soát.** Tạo một job Spring Batch với `chunk(10)`, writer JDBC và 100 item. Khởi chạy bất đồng bộ, gọi `JobOperator.stop(executionId)` sau khi xác nhận writer đã vào một chunk. Ghi nhận thời gian từ request stop đến `STOPPED`, kiểm tra số bản ghi và trạng thái checkpoint.

**Bài 2 – Unknown commit.** Thiết kế writer dùng `operationId` làm unique key. Mô phỏng trường hợp commit thành công nhưng caller không nhận ack. Chạy lại cùng operation, assert bảng ledger vẫn chỉ có một bản ghi, đồng thời kiểm tra payload không bị thay đổi.

**Bài 3 – File partial.** Viết report vào file `.tmp` và chỉ publish bằng rename sau khi hoàn tất. Mô phỏng exception giữa quá trình ghi; xác minh consumer không thể thấy file final chứa dữ liệu dở dang. Thử crash sau publish và thiết kế chính sách nhận diện file đã hoàn tất khi restart.

**Bài 4 – Grace period.** Đo thời gian writer/chunk dài nhất trong test tải, so với `terminationGracePeriodSeconds` đang cấu hình. Thiết kế đường đi drain để process chỉ tắt sau khi không còn write cần bảo vệ; mô tả hành vi dự phòng nếu hết grace period.

**Bài 5 – External API.** Gửi một event qua outbox; mô phỏng sự cố sau khi consumer xử lý thành công nhưng trước khi dispatcher đánh dấu delivered. Phát lại event với cùng idempotency key và kiểm tra chỉ một hiệu ứng nghiệp vụ được ghi nhận.

**Bài 6 – Restart.** Để job fail sau khi một số chunk commit. Không xóa metadata trong `JobRepository`; restart đúng job instance, kiểm tra không ghi trùng và output cuối cùng khớp với lần chạy thành công từ đầu.

## 17. Ghi nhớ

**Không kill process giữa critical write** trước hết là một quy tắc điều khiển thực thi: ngừng nhận công việc mới, yêu cầu Spring Batch stop, chờ trạng thái dừng và ranh giới commit an toàn rồi mới kết thúc JVM/container. Quy tắc đó phải đi kèm một thiết kế chịu lỗi: **transaction đúng phạm vi, idempotency key, checkpoint, outbox hoặc atomic file publication, cùng quy trình đối soát và restart**. Nhờ vậy, ngay cả khi process buộc phải dừng ở thời điểm xấu nhất, hệ thống vẫn có cơ sở để xác định kết quả đã được ghi và hoàn thành công việc mà không nhân đôi hiệu ứng nghiệp vụ.

### Tài liệu tham khảo

- [Spring Batch Reference — Job](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
