# Failure khi commit trong Spring Batch: nguyên nhân, tác động và phục hồi

## 1. Tại sao lỗi commit nguy hiểm hơn một lỗi xử lý item thông thường?

Trong Spring Batch, một Step xử lý dữ liệu theo từng **chunk** thường đọc nhiều item, biến đổi chúng, ghi output rồi yêu cầu transaction **commit**. Khi một processor ném exception trước khi ghi, ứng dụng thường biết item nào gặp lỗi. Nhưng khi lỗi xảy ra **ngay lúc commit**, câu hỏi quan trọng hơn là:

> Dữ liệu đã được database xác nhận bền vững hay chưa, và checkpoint của Spring Batch có phản ánh đúng trạng thái đó không?

Ví dụ, job nhập 10.000 đơn hàng với \`chunk(100)\`:

~~~text
Read O001 ... O100
       |
       v
Process, validate
       |
       v
Writer INSERT vào database
       |
       v
COMMIT transaction
       |
       +--- Thành công ----------> Checkpoint được xác nhận
       |
       +--- Lỗi trước commit ----> Rollback nếu transaction còn khả dụng
       |
       +--- Mất kết nối tại COMMIT
                |
                +--> DB chưa commit?
                |
                +--> DB đã commit nhưng ACK thất lạc?
~~~

Ở nhánh cuối, ứng dụng có thể chỉ nhận một exception giao tiếp và **không biết chắc commit thực tế đã thành công hay thất bại**. Nếu tự chạy lại bằng \`INSERT\`, output có nguy cơ trùng hoặc vướng unique constraint. Nếu bỏ qua lỗi, dữ liệu có thể thiếu.

**Failure khi commit** thuộc nhóm **Failure recovery** vì nó đặt ra đồng thời ba yêu cầu:

1. **Nhận biết trạng thái transaction:** rollback xác định, commit xác định hay kết quả chưa rõ.
2. **Đánh giá trạng thái bền vững:** output thực tế, dữ liệu metadata và checkpoint.
3. **Phục hồi an toàn:** có thể restart/reprocess mà không mất bản ghi, ghi trùng hoặc tạo side effect lặp.

Không nên đồng nhất một exception được phát ra trong \`commit()\` với kết luận chắc chắn rằng transaction đã rollback.

## 2. Ranh giới transaction của một chunk

Trong mô hình chunk-oriented processing, Spring Batch tổ chức việc đọc, xử lý và ghi theo các đơn vị giao dịch:

~~~text
StepExecution
   |
   +-- Chunk #1
   |     Begin transaction
   |     Reader:    item 1..100
   |     Processor: biến đổi / lọc
   |     Writer:    ghi dữ liệu
   |     ItemStream.update(ExecutionContext)
   |     Cập nhật StepExecution / checkpoint metadata
   |     Commit transaction
   |
   +-- Chunk #2
   |     Begin transaction
   |     Reader:    item 101..200
   |     ...
   |
   +-- Chunk #N
         ...
~~~

Đây là hình dung tổng quát: thứ tự chi tiết và cách đồng bộ metadata phụ thuộc Step implementation và transaction infrastructure. Với cấu hình chuẩn, framework cập nhật trạng thái Step và \`ExecutionContext\` ở ranh giới checkpoint. Nhưng **tính nguyên tử giữa dữ liệu nghiệp vụ và Batch metadata chỉ có thể kỳ vọng khi các thao tác thực sự tham gia cùng transaction/resource**.

Các thành phần liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| \`PlatformTransactionManager\` | Bắt đầu, commit và rollback transaction của Step |
| \`ItemReader\` | Đọc input; có thể duy trì vị trí/state giữa các chunk |
| \`ItemProcessor\` | Biến đổi, filter hoặc phát sinh lỗi nghiệp vụ |
| \`ItemWriter\` | Ghi output vào DB, file hoặc hệ thống khác |
| \`ItemStream\` | \`open\`, \`update\`, \`close\` cho trạng thái có thể restart |
| \`ExecutionContext\` | Lưu checkpoint và các giá trị cần khôi phục |
| \`StepExecution\` | Bộ đếm read/write/skip, trạng thái và metadata của một lần chạy Step |
| \`JobRepository\` | Lưu JobInstance, JobExecution, StepExecution và ExecutionContext |

Khi writer sử dụng **JDBC datasource cùng transaction manager** với Step, thao tác INSERT/UPDATE của writer có thể rollback cùng transaction chunk. Ngược lại, một request HTTP, email đã gửi, message đã publish hoặc file đã ghi thường **không tự rollback** khi Spring Batch rollback transaction database.

### Phân biệt write thành công và commit thành công

Một câu lệnh \`jdbcTemplate.update(...)\` trả về số dòng đã tác động nghĩa là database đã thực hiện lệnh trong transaction hiện tại; **chưa chắc thay đổi đã commit**. Writer có thể ghi xong 100 item rồi bước commit bị lỗi.

Tương tự, \`writeCount\` phản ánh cơ chế ghi nhận của Step, không phải một bằng chứng độc lập rằng 100 bản ghi đã có mặt bền vững trong mọi hệ thống bên ngoài. Khi điều tra lỗi commit, cần kiểm tra dữ liệu thật ở đích cùng với metadata và trạng thái transaction.

## 3. Những kiểu failure tại thời điểm commit

| Tình huống | Điều ứng dụng thường thấy | Trạng thái dữ liệu | Hướng xử lý |
|---|---|---|---|
| Validation hoặc constraint bị phát hiện trước commit | Exception từ writer/flush | Transaction thường rollback được | Sửa dữ liệu hoặc policy skip/retry phù hợp |
| Transaction bị đánh dấu rollback-only | \`UnexpectedRollbackException\` hoặc exception liên quan | Không được commit thành công theo kỳ vọng | Tìm nguyên nhân rollback-only trước đó |
| Deadlock/serialization conflict được database từ chối | Exception transaction/concurrency | Giao dịch bị hủy hoặc phải rollback theo DB | Retry **cả đơn vị transaction** khi an toàn |
| Database connection mất trước khi gửi COMMIT | Lỗi kết nối/transaction | Có thể rollback khi connection đóng; cần xác minh theo hệ DB | Kiểm tra trạng thái thực tế và khả năng replay |
| COMMIT đã xử lý nhưng phản hồi thất lạc | Timeout/I/O exception ở lời gọi commit | **Không xác định chỉ từ exception** | Reconcile DB + checkpoint; replay idempotent |
| Lỗi callback sau commit | Exception từ \`afterCommit\` hoặc tác vụ hậu commit | DB có thể **đã commit** | Không giả định rollback, tách logic hậu commit |
| Database output và Batch metadata dùng hai transaction | Một nơi commit, nơi khác lỗi | Có thể lệch output và checkpoint | Dùng kiến trúc đồng bộ hoặc cơ chế reconcile |
| Writer gọi API/file ngoài transaction | Job/Step FAILED hoặc rollback DB | Side effect ngoài có thể vẫn tồn tại | Idempotency, outbox, staging và audit |

Lỗi từ tầng Spring như \`TransactionSystemException\`, \`CannotCreateTransactionException\`, \`UnexpectedRollbackException\`, từ JDBC driver hoặc database có tên khác nhau theo ngữ cảnh. **Tên exception không phải lúc nào cũng cho biết database đã commit hay chưa**. Cần xem nguyên nhân gốc, SQLState/vendor code, transaction manager, log phía database và trạng thái persisted.

### 3.1. Failure trước commit

Ví dụ writer ghi dữ liệu không hợp lệ dẫn đến unique constraint violation, hoặc một thành phần gọi \`setRollbackOnly()\`. Khi transaction bị hủy một cách xác định, những ghi nhận **trong cùng transaction** không được coi là đã commit. Spring Batch có thể đánh dấu Step FAILED và khi restart sẽ xử lý lại từ checkpoint đã lưu.

Đừng suy ra toàn bộ chunk đã rollback nếu writer còn dùng API, storage hoặc connection quản lý transaction độc lập.

### 3.2. Failure do kết quả commit không rõ

Giả sử database nhận lệnh \`COMMIT\`, ghi log giao dịch bền vững, nhưng TCP connection đứt trước khi xác nhận về ứng dụng:

~~~text
Application                         Database
    |                                 |
    |----------- COMMIT ------------->|
    |                                 | transaction committed
    |<---- ACK bị mất do network -----X
    |
    +---- Nhận SQLException / timeout
          nhưng không biết kết quả commit
~~~

Đây là tình huống **ambiguous commit outcome**. Một cơ chế phục hồi chỉ dựa vào việc “có exception thì dữ liệu chưa ghi” có thể gây duplicate. Ngược lại, cứ coi là đã ghi sẽ làm mất dữ liệu nếu COMMIT thực sự chưa thành công.

### 3.3. Failure sau commit

Một callback \`afterCommit\` có thể ném exception sau khi tài nguyên DB đã hoàn tất commit. Khi đó exception vẫn lan về ứng dụng nhưng **không thể rollback giao dịch đã commit**. Tác vụ sau commit như publish event cần xử lý lại theo cơ chế tin cậy riêng, chẳng hạn outbox, thay vì yêu cầu database “undo” commit đã hoàn thành.

## 4. Điều gì xảy ra với JobExecution, StepExecution và checkpoint?

Spring Batch không dùng một trạng thái duy nhất để mô tả mọi thứ đã xảy ra:

- **\`BatchStatus\`** cho biết trạng thái thực thi được framework ghi nhận (\`STARTED\`, \`FAILED\`, \`STOPPED\`, \`COMPLETED\`, ...).
- **\`ExitStatus\`** cung cấp exit code của Step/Job, có thể được cấu hình/điều chỉnh theo flow.
- **\`StepExecution\`** lưu counter và trạng thái của Step.
- **\`ExecutionContext\`** lưu checkpoint/state cần thiết cho restart.
- **Database đích** lưu dữ liệu nghiệp vụ thực tế.

Trong trường hợp commit failure, những nguồn này **có thể không cùng phản ánh một ranh giới tiến độ** nếu transaction không đồng nhất hoặc xảy ra sự cố ngay lúc cập nhật metadata.

Ví dụ chunk size 100:

~~~text
Chunk #1: O001..O100
  Business DB: COMMITTED
  ExecutionContext: checkpoint=100

Chunk #2: O101..O200
  Writer gửi dữ liệu thành công
  COMMIT trả lỗi không rõ kết quả

Quan sát sau sự cố:
  StepExecution: có thể FAILED hoặc metadata còn STARTED
  Business DB: có thể có hoặc chưa có O101..O200
  ExecutionContext: có thể ở 100 hoặc trạng thái mới hơn
~~~

Không nên lấy \`readCount\` hoặc \`writeCount\` cuối cùng rồi tự khẳng định “đã commit đến record X”. Trong fault-tolerant step, rollback, retry, filter, skip và prefetch làm counter/reader position khác với số record output cuối.

### Khi JobRepository và dữ liệu nghiệp vụ cùng database

Nếu hai loại ghi dùng **cùng datasource và cùng transaction vật lý**, commit của chunk có thể làm dữ liệu nghiệp vụ và cập nhật metadata trở thành một đơn vị nguyên tử: cả hai commit hoặc cả hai rollback theo bảo đảm của database. Điều này làm restart dễ dự đoán hơn.

Tuy nhiên, các bản ghi trạng thái tổng thể của JobExecution (như final FAILED/COMPLETED), log, metrics và những lời gọi ngoài transaction vẫn có vòng đời riêng. **Đừng suy rộng tính nguyên tử của chunk thành một distributed transaction xuyên mọi thành phần của hệ thống**.

### Khi dùng hai datasource

Nếu writer ghi dữ liệu nghiệp vụ vào DB A, còn JobRepository dùng DB B với transaction manager riêng:

~~~text
              Chunk processing
                /          \
               v            v
          Business DB A   Batch metadata DB B
               |            |
            COMMIT A      COMMIT B
               |            |
          Thành công       Thất bại
~~~

Kết quả có thể là bản ghi output tồn tại nhưng checkpoint chưa tăng. Khi restart, reader đọc lại item đã ghi, dẫn đến duplicate nếu writer không idempotent. Chỉ dùng \`@Transactional\` không tự tạo atomic commit cho hai database độc lập.

Nếu bắt buộc cần đảm bảo nguyên tử trên nhiều resource, phải thiết kế cơ chế phân tán phù hợp với yêu cầu và hạ tầng; với nhiều job thực tế, **idempotent writer + reconciliation + staging/outbox** thường dễ vận hành và phục hồi hơn việc giả định commit đồng thời.

## 5. Quy trình phản ứng đầu tiên khi nghi ngờ commit failure

Đừng lập tức chạy lại job nhiều lần. Cần xác minh phạm vi và hậu quả trước:

1. **Xác định execution:** jobName, jobExecutionId, jobInstanceId, StepExecutionId, batchId và thời điểm exception.
2. **Xác định tài nguyên:** writer ghi vào DB/file/API nào, có bao nhiêu transaction manager, JobRepository dùng cùng database không.
3. **Đọc exception chain:** lỗi xảy ra ở writer, flush, commit, callback sau commit hay khi lưu metadata.
4. **Giữ nguyên bằng chứng:** log có correlation ID, metadata Step, checkpoint, transaction ID nếu database hỗ trợ; tránh xóa output.
5. **Kiểm tra dữ liệu bền vững:** truy vấn theo batchId và business key, so với input snapshot hoặc expected set.
6. **Đánh giá side effect ngoài transaction:** event/API/file đã được phát hành hay chưa, có idempotency key không.
7. **Chọn chiến lược phục hồi:** restart theo checkpoint khi nhất quán; reconcile và replay idempotent khi không chắc chắn; cách ly output nếu cần.
8. **Đối soát lại sau phục hồi:** chỉ đánh dấu READY hoặc cấp dữ liệu cho downstream sau khi kiểm tra đạt.

Sơ đồ quyết định:

~~~text
Commit exception
       |
       v
Đã xác định chắc transaction rollback?
       | Có
       v
  Restart từ checkpoint hợp lệ
       |
       +--> Kiểm tra writer idempotent / external effects

       Không rõ
       |
       v
Tra DB output + JobRepository + external receipts
       |
       +--> Output thiếu: replay có kiểm soát
       |
       +--> Output đủ: tránh ghi lại; sửa tiến độ theo runbook
       |
       +--> Output có một phần/khác biệt: quarantine,
            reconcile từng key rồi replay idempotent
~~~

Mọi bước liên quan đến sửa trạng thái metadata phải được quản lý theo runbook. Không tự chuyển \`BATCH_JOB_EXECUTION.STATUS\` sang COMPLETED hoặc sửa vị trí reader bằng SQL chỉ vì output “trông có vẻ đủ”: điều đó có thể khiến JobRepository và flow restart mâu thuẫn.

## 6. Thiết kế dữ liệu đích để phục hồi được

Giả sử một job nhập đơn hàng từ nguồn đã cố định; mỗi input hợp lệ tạo đúng một hàng output. Ta định nghĩa:

- \`batchId\`: định danh lô nghiệp vụ và phạm vi đối soát.
- \`orderId\`: business key duy nhất trong một batch.
- \`amount\`: số tiền đã chuẩn hóa theo quy tắc nghiệp vụ.
- \`sourceHash\`: fingerprint ổn định của dữ liệu đầu vào quan trọng (nếu cần xác định cùng một item hay một phiên bản mới).

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE imported_order (
    batch_id     VARCHAR(64) NOT NULL,
    order_id     VARCHAR(64) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL,
    source_hash  VARCHAR(64) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

Unique key trên \`(batch_id, order_id)\` ngăn duplicate vật lý trong bảng. Nhưng **unique constraint không đồng nghĩa writer có thể replay an toàn**: \`INSERT\` lần hai vẫn có thể ném lỗi và làm Step FAILED.

Một chiến lược idempotency cụ thể cần quy định:

| Tình huống khi replay | Hành vi mong muốn |
|---|---|
| Key chưa tồn tại | INSERT bản ghi mới |
| Key đã tồn tại và nội dung khớp | Xem như đã xử lý; không tạo duplicate |
| Key đã tồn tại nhưng amount/hash khác | Báo conflict để reconcile, không âm thầm ghi đè |
| Bản ghi đã được downstream tiêu thụ | Không sửa đột ngột; dùng version/correction workflow |

Một số job dùng \`INSERT ... ON CONFLICT DO NOTHING\` (PostgreSQL) để bỏ qua bản ghi lặp. Cách này chỉ an toàn khi **đã có cơ chế phát hiện key trùng nhưng payload khác**. Nếu không, job có thể báo thành công dù dữ liệu đích chứa bản ghi của input cũ.

### Ví dụ writer có kiểm soát xung đột

Trong mô hình đơn giản dưới đây, writer thử INSERT, sau đó nếu phát hiện duplicate key thì đọc lại bản ghi đã lưu để xác nhận tính tương đương. Đây là ví dụ về **ý tưởng nghiệp vụ**, không nên đặt một câu lệnh JDBC bị lỗi rồi tiếp tục truy vấn trong cùng transaction PostgreSQL: sau một lỗi SQL, transaction PostgreSQL có thể đã ở trạng thái aborted.

Thay vì bắt exception SQL trong transaction đã lỗi, có thể dùng atomic UPSERT với điều kiện rõ ràng và kiểm tra row count:

~~~sql
INSERT INTO imported_order (batch_id, order_id, amount, source_hash)
VALUES (:batchId, :orderId, :amount, :sourceHash)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET
    amount = imported_order.amount
WHERE imported_order.amount = EXCLUDED.amount
  AND imported_order.source_hash = EXCLUDED.source_hash;
~~~

Với PostgreSQL, nếu key trùng nhưng dữ liệu khác, điều kiện \`WHERE\` không đạt nên \`RETURNING\` không có dòng; ứng dụng có thể kiểm tra số dòng nhận được và báo **conflict**. Ví dụ dùng \`RETURNING order_id\` để rõ kết quả:

~~~sql
INSERT INTO imported_order (batch_id, order_id, amount, source_hash)
VALUES (:batchId, :orderId, :amount, :sourceHash)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET amount = imported_order.amount
WHERE imported_order.amount = EXCLUDED.amount
  AND imported_order.source_hash = EXCLUDED.source_hash
RETURNING order_id;
~~~

Điều này minh họa chính sách **“insert mới hoặc chấp nhận bản ghi cũ giống hệt”**. Việc tạo UPDATE no-op vẫn có thể kích hoạt trigger/audit hoặc tạo row version tùy database, nên trong production cần xem xét chi phí và side effect. Một lựa chọn khác là dùng staging và truy vấn đối soát set-based trước khi merge.

Tất cả SQL ở ví dụ này là cú pháp PostgreSQL; nếu dùng Oracle, SQL Server hoặc MySQL phải xây phương án tương đương theo semantics và isolation level của database đó.

## 7. Ví dụ chunk Step có transaction và checkpoint

Ví dụ dùng Spring Batch 5+, đọc một file CSV đã đóng băng theo \`inputFile\`, ghi đơn hàng vào DB. Phần minh họa nhằm làm rõ **điểm commit và khả năng restart**, không giả định rằng bản thân cấu hình này xử lý được mọi lỗi commit không rõ kết quả.

Input file:

~~~csv
orderId,amount,sourceHash
O001,100.00,hash-o001-v1
O002,45.50,hash-o002-v1
O003,80.00,hash-o003-v1
O004,25.00,hash-o004-v1
~~~

Kiểu dữ liệu:

~~~java
import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        BigDecimal amount,
        String sourceHash) {
}
~~~

Reader có khả năng lưu trạng thái:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("importOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount", "sourceHash")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount"),
                    fields.readString("sourceHash")))
            .saveState(true)
            .build();
}
~~~

Writer minh họa với \`JdbcTemplate\` và câu \`INSERT\` thông thường để các tình huống commit có thể được quan sát:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
public ItemWriter<OrderRow> orderWriter(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return chunk -> {
        for (OrderRow order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO imported_order
                        (batch_id, order_id, amount, source_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    batchId,
                    order.orderId(),
                    order.amount(),
                    order.sourceHash());
        }
    };
}
~~~

Step và Job:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(2, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

Trong chương trình thật, hai \`@Bean\` method cần nằm trong \`@Configuration\`, các bean infrastructure phải được tạo và \`JobRepository\`/transaction manager phải dùng datasource phù hợp. Với \`chunk(2)\`, file bốn record tạo hai đơn vị commit nếu tất cả hợp lệ.

Ví dụ writer \`INSERT\` **chưa idempotent**. Nếu DB đã commit nhưng checkpoint chưa cập nhật, restart có thể vướng duplicate key. Trước khi chạy trong production, cần thay bằng chính sách replay an toàn hoặc đảm bảo nguồn metadata và dữ liệu nghiệp vụ đồng nhất.

## 8. Lỗi commit có tự động retry hoặc skip được không?

Trong Spring Batch, \`faultTolerant()\`, \`retry(...)\`, \`skip(...)\` và \`skipLimit(...)\` chủ yếu hỗ trợ lỗi trong các hoạt động **read/process/write** theo cơ chế fault-tolerant chunk. Lỗi xảy ra **khi transaction manager commit ở ranh giới chunk** có vị trí khác với exception của một item.

Vì vậy:

- Không giả định \`.retry(SomeSQLException.class)\` sẽ luôn retry một lỗi phát sinh tại chính \`PlatformTransactionManager.commit()\`.
- Không coi \`.skip(Exception.class)\` là giải pháp cho commit failure; không có một item duy nhất chắc chắn là thủ phạm.
- Không đặt retry bao quanh toàn bộ JobLauncher với tham số ngẫu nhiên: dễ tạo JobInstance mới và ghi output trùng.
- Không retry transaction khi outcome còn mơ hồ và writer không idempotent.
- Nếu database trả lỗi concurrency mang nghĩa transaction bị rollback rõ ràng, retry toàn chunk có thể phù hợp, nhưng phải dựa vào bảo đảm của database/transaction manager và chính sách retry đã thiết kế.

Đặc biệt, **\`noRollback(...)\` không biến một commit thất bại thành commit thành công**. Tùy chọn này điều chỉnh chính sách rollback với một số exception ở quá trình chunk; nó không đảm bảo tiếp tục an toàn sau sự cố tại commit.

### Khi nào retry hữu ích?

| Lỗi | Ví dụ | Hướng thường cân nhắc |
|---|---|---|
| Transient read/process | API timeout, deadlock đọc có thể thử lại | Retry có giới hạn và backoff |
| Transient write trước commit | DB lock timeout khi ghi | Retry chunk nếu state và side effect cho phép |
| Commit rejected rõ ràng | Serialization conflict làm transaction abort | Thử lại toàn transaction khi idempotent |
| Commit outcome không rõ | Mất ACK sau COMMIT | Reconcile trước; retry an toàn theo business key |
| Permanent constraint violation | Khóa trùng nhưng payload khác | Dừng/quarantine để xử lý data conflict |
| Metadata commit lệch output | DB business và DB batch không đồng bộ | Repair/reconciliation theo runbook, không retry mù |

Khả năng retry an toàn phụ thuộc **idempotency** và **tính độc lập của các side effect**, chứ không đơn thuần phụ thuộc một exception được đánh dấu \`retryable\`.

## 9. Fault injection để phân biệt trước và sau commit

Với Failure recovery, kiểm thử chỉ tạo lỗi trong \`ItemWriter.write()\` là chưa đủ: lỗi này thường xuất hiện **trước khi framework gọi commit**. Để kiểm thử ranh giới transaction, có thể dùng một môi trường tích hợp và công cụ tiêm lỗi có kiểm soát.

### 9.1. Mô phỏng lỗi trước commit

Trong Spring transaction, có thể đăng ký **TransactionSynchronization** tại thời điểm một transaction đang hoạt động. Callback \`beforeCommit\` chạy trước commit của transaction. Nếu callback ném exception, transaction thông thường bị rollback theo quy trình transaction manager.

Ví dụ một thành phần chỉ dùng trong test:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class BeforeCommitFailureInjector {

    private final AtomicBoolean failNext = new AtomicBoolean(true);

    public void registerForCurrentTransaction() {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException("No active synchronization");
        }

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        if (failNext.compareAndSet(true, false)) {
                            throw new IllegalStateException(
                                    "TEST_FAIL_BEFORE_COMMIT");
                        }
                    }
                });
    }
}
~~~

Thành phần test phải được gọi **trong transaction chunk mục tiêu**, ví dụ từ writer đã được test cấu hình. Không đặt ngẫu nhiên ở thời điểm khởi động context vì khi đó chưa chắc có transaction.

Điểm cần quan sát trong test: lỗi được phát trước commit, transaction bị rollback theo manager đang sử dụng, output tương ứng chunk chưa được công bố, job có trạng thái phù hợp và dữ liệu sau restart chính xác.

### 9.2. Mô phỏng lỗi sau khi commit đã hoàn tất

Trong môi trường test, một callback \`afterCommit\` có thể cố tình ném exception:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                throw new IllegalStateException(
                        "TEST_FAIL_AFTER_COMMIT");
            }
        });
~~~

Đây là mô hình **lỗi callback hậu commit**: thay đổi DB đã có thể commit thành công trước khi ứng dụng nhận exception. Nó **không tương đương** với việc mô phỏng đứt kết nối JDBC đúng lúc COMMIT hoặc giả lập chính xác mọi loại lỗi transaction manager.

Khi kiểm tra tình huống này, đừng assert cứng rằng \`BatchStatus\` chắc chắn là FAILED hay dữ liệu chắc chắn rollback trong mọi cấu hình. Hãy quan sát và ghi lại:

- Exception được phát ở thời điểm nào.
- DB output đã commit hay chưa.
- Checkpoint của Spring Batch có trạng thái gì.
- JobExecution/StepExecution cuối cùng ghi nhận status nào.
- Restart có lặp bản ghi hay không.

Việc ném exception trong callback hậu commit có thể ảnh hưởng luồng xử lý và logging, nên chỉ sử dụng injector trong test cô lập; không giữ code tiêm lỗi trong production.

### 9.3. Mô phỏng lỗi COMMIT thật ở tầng kết nối

Để kiểm tra **ambiguous commit outcome**, cần môi trường tích hợp gần thực tế hơn:

- Database test chuyên dụng với transaction semantics giống production.
- Proxy mạng hoặc test harness có thể cắt kết nối **sau khi phía DB nhận COMMIT nhưng trước khi client nhận xác nhận**, nếu công cụ/driver cho phép.
- Log phía database hoặc audit có transaction marker để xác minh commit thực tế.
- Worker/JobRepository thật trong test, không chỉ mock \`PlatformTransactionManager\`.

Loại test này khó điều khiển tuyệt đối vì thời điểm COMMIT/ACK là race. Hãy bảo đảm test có thể ghi nhận cả trường hợp transaction commit và trường hợp rollback, rồi đánh giá thuật toán phục hồi có xử lý **cả hai** mà vẫn cho output cuối đúng hay không.

Không nên gọi một mock \`commit()\` “ném exception” là bằng chứng rằng mạng thực đã mất ACK sau commit. Mock phương thức chỉ mô phỏng cách ứng dụng phản ứng với exception, chưa mô phỏng trạng thái bền vững của DB.

## 10. Kịch bản kiểm thử phục hồi sau commit failure

Giả sử input gồm sáu đơn hợp lệ, \`chunk(2)\`, mỗi đơn phải có đúng một bản ghi output:

~~~text
O001, O002  -> Chunk 1
O003, O004  -> Chunk 2
O005, O006  -> Chunk 3
~~~

Các kịch bản chính:

| Trường hợp | Điểm tiêm lỗi | Điều cần kiểm tra |
|---|---|---|
| Baseline | Không lỗi | Job COMPLETED; đủ sáu đơn, không trùng |
| Trước commit của chunk 2 | \`beforeCommit\` hoặc database reject có kiểm soát | Chunk chưa commit được rollback; checkpoint/đích nhất quán |
| Sau commit của chunk 2 | \`afterCommit\` của transaction kiểm thử | Đích có thể đã có O003/O004 dù ứng dụng thấy exception |
| COMMIT phản hồi không rõ | Proxy/database chaos | Phục hồi an toàn dù commit thực tế có/không xảy ra |
| Metadata DB lỗi | Tách nguồn metadata có chủ đích | Phát hiện output/checkpoint lệch |
| Writer có side effect ngoài | API nhận request rồi lỗi DB | Không tạo duplicate side effect khi restart |
| File writer đang flush | Lỗi storage/file | Output tạm được cách ly và không phát hành sớm |
| Restart lần thứ hai | Lần đầu failure, lần hai thành công | Cùng JobInstance; output cuối chính xác |
| Retry nhiều lần cùng record | Replay cùng batchId/orderId | Idempotent; payload xung đột phải bị phát hiện |

### Ví dụ assertion trên dữ liệu cuối

Với bảng \`imported_order\`, sau khi phục hồi thành công:

~~~sql
-- Đủ record thuộc đúng batch.
SELECT COUNT(*)
FROM imported_order
WHERE batch_id = :batchId;

-- Không trùng business key.
SELECT batch_id, order_id, COUNT(*) AS occurrences
FROM imported_order
WHERE batch_id = :batchId
GROUP BY batch_id, order_id
HAVING COUNT(*) > 1;

-- Không thiếu record so với snapshot nguồn.
SELECT s.order_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM imported_order t
      WHERE t.batch_id = s.batch_id
        AND t.order_id = s.order_id
  );
~~~

Nếu bảng nguồn \`staging_order\` không tồn tại trong ứng dụng, test có thể so sánh với danh sách ID kỳ vọng từ file fixture. **COUNT(*) đơn lẻ chưa đủ**: một record thiếu và một record trùng có thể giữ nguyên số lượng. Với payload quan trọng, kiểm tra cả amount/hash theo đúng quy tắc transform.

### Không khẳng định thời điểm failure bằng sleep

Test commit failure nên có cách chọn **chunk/transaction mục tiêu** rõ ràng, ví dụ injector có bộ đếm số lần đăng ký, callback của writer sau một bộ record cố định, hoặc transaction manager proxy điều khiển từ test. Tránh \`Thread.sleep(100)\` rồi ngắt DB: trên CI, timing khác nhau có thể khiến lỗi rơi vào chunk không mong muốn.

Với mô phỏng network failure thật, ghi log transaction marker để phân biệt failure xảy ra trước hay sau commit; bài test chấp nhận outcome không xác định nhưng phải bảo đảm thuật toán reconcile an toàn cho cả hai.

## 11. Restart JobInstance sau lỗi commit

Spring Batch lưu checkpoint để hỗ trợ restart Step chưa hoàn thành. Tính đúng đắn của restart phụ thuộc input bất biến, \`ItemStream\` lưu state và side effect của writer.

Ví dụ:

~~~text
JobInstance #410: importOrdersJob(batchId=B42)
    |
    +-- JobExecution #900: FAILED
    |     Chunk 1 committed
    |     Chunk 2 commit outcome ambiguous
    |
    +-- JobExecution #904: restart
          Tiếp tục từ checkpoint framework tìm được
          Writer phải chịu được việc replay O003/O004 nếu có
~~~

**Restart** nghĩa là tiếp tục cùng JobInstance theo metadata của Spring Batch, thường tạo một JobExecution mới. **Không thêm identifying parameter ngẫu nhiên** vào lần chạy thứ hai rồi gọi đó là restart: thao tác này tạo một JobInstance khác và có thể xử lý lại toàn bộ nguồn.

Ví dụ với JobOperator:

~~~java
long failedExecutionId = 900L;

// Chỉ gọi sau khi đã đánh giá trạng thái và quyền restart.
Long restartedExecutionId = jobOperator.restart(failedExecutionId);
~~~

Đoạn code giả định \`jobOperator\` đã được inject và execution đủ điều kiện restart. Lời gọi restart có thể bị từ chối khi job không restartable, execution chưa kết thúc, Step vượt \`startLimit\`, input thay đổi hoặc metadata không nhất quán.

### Điều gì nếu checkpoint tiến sau output?

Nếu JobRepository ghi checkpoint mới nhưng output nghiệp vụ chưa commit (hai resource không cùng transaction), restart có thể **bỏ qua** những item chưa có ở đích. Unique key không giải quyết được lỗi mất dữ liệu này. Cần đối soát expected input với actual output, rồi khôi phục những key thiếu.

### Điều gì nếu output đi trước checkpoint?

Nếu output đã commit nhưng checkpoint vẫn cũ, restart đọc lại item đã có trong DB. Khi đó idempotent writer có thể bỏ qua replay an toàn; writer INSERT thuần có thể gặp duplicate constraint.

Vì cả hai chiều lệch đều có thể xảy ra trong kiến trúc nhiều resource, **exact-set reconciliation** phải là một phần của phục hồi khi không có bảo đảm atomicity.

## 12. File output và commit failure

Không phải mọi writer đều ghi database. Với \`FlatFileItemWriter\`, checkpoint có thể giúp restart một file, nhưng file system không có semantics giống một transaction JDBC. Một lỗi flush/close, mất điện, thay đổi file hoặc consumer đọc file đang ghi có thể khiến output bị thiếu, trùng hoặc chỉ hoàn thành một phần.

Một chiến lược phổ biến:

~~~text
job execution
    |
    v
Ghi batch-B42-v1.csv.part
    |
    v
Đóng file, xác minh schema/record/checksum
    |
    v
Tạo batch-B42-v1.csv (nếu thao tác publish an toàn)
    |
    v
Ghi manifest/READY marker
    |
    v
Consumer mới bắt đầu đọc
~~~

Lưu ý:

- **Không xem file tồn tại là dấu hiệu đã commit thành công**.
- Khi restart, giữ nguyên version input và hiểu rõ chế độ append/truncate/state của writer.
- Không phát hành file tạm khi JobExecution mới ở trạng thái FAILED hoặc STOPPED.
- Rename có thể nguyên tử trên cùng filesystem phù hợp, nhưng không mặc định nguyên tử khi chuyển giữa hai storage hoặc trên object storage.
- Với cloud object storage, nên dùng object key/version bất biến và manifest/READY marker phát hành sau khi xác minh.
- Nếu đã công bố một version cho consumer, không ghi đè trực tiếp khi repair; dùng version/correction theo contract.

Các cấu hình \`saveState\`, \`transactional\`, \`shouldDeleteIfExists\`, \`appendAllowed\` của file writer cần được hiểu theo phiên bản Spring Batch và chiến lược restart cụ thể. Không áp một bộ option chung cho mọi job.

## 13. Side effect tới API, message broker và hệ thống khác

Đây là nguồn sai lệch phổ biến nhất sau commit failure:

~~~text
Step transaction (DB)
        |
        +-- INSERT order vào DB (chưa commit)
        |
        +-- Gọi HTTP API gửi thông báo
        |      API đã gửi thành công
        |
        +-- COMMIT database thất bại
               |
               v
        DB rollback
        Thông báo không tự thu hồi
~~~

Khi restart, job có thể gửi thông báo lần thứ hai. Kể cả JobRepository và DB nghiệp vụ dùng chung transaction, lời gọi HTTP **không nằm trong transaction đó**.

### Transactional outbox

Nếu cần phát sự kiện sau khi ghi DB, một lựa chọn là ghi **event outbox trong cùng transaction** với bản ghi nghiệp vụ:

~~~text
Business transaction:
    INSERT/UPDATE imported_order
    INSERT outbox_event(event_id, batch_id, order_id, payload)
    COMMIT

Publisher độc lập:
    Đọc outbox chưa phát
    Gửi message
    Ghi nhận trạng thái phát hành
~~~

Khi commit DB thất bại, cả output và outbox record cùng rollback nếu chúng thật sự dùng chung transaction. Khi commit DB thành công nhưng publisher mất ACK từ broker, publisher có thể gửi lại. Vì thế consumer vẫn cần **idempotency key/event ID** và xử lý duplicate.

### API có side effect

Với request thanh toán, đặt chỗ hoặc tạo đơn ở hệ thống ngoài, cần một idempotency key ổn định, thường dựa trên **batchId + business key + loại tác vụ**.

~~~http
POST /reservations
Idempotency-Key: B42-O003-RESERVE
Content-Type: application/json

{"orderId":"O003","quantity":2}
~~~

Khi response bị timeout, retry với **cùng idempotency key** để dịch vụ đích nhận diện đó là cùng một hành động. Nhưng phải xác minh contract của dịch vụ đích thật sự hỗ trợ idempotency trong phạm vi thời gian yêu cầu; chỉ gửi header không bảo đảm bên nhận thực hiện chống trùng.

Trong các trường hợp commit không rõ kết quả, đôi khi phải truy vấn **receipt/status API** bằng idempotency key trước khi thực hiện lại.

## 14. Giám sát và audit lỗi commit

Một sự cố commit cần đủ thông tin để điều tra, nhưng không nên ghi secrets hoặc payload nhạy cảm.

Ví dụ event log:

~~~text
event=chunk.commit.failed
jobName=importOrdersJob
jobInstanceId=410
jobExecutionId=900
stepExecutionId=1901
batchId=B42
chunkSequence=2
transactionResource=orders-datasource
exceptionClass=TransactionSystemException
rootSqlState=08006
commitOutcome=UNKNOWN
observedAt=2026-11-16T03:25:00+07:00
~~~

Đây là cấu trúc minh họa. Không suy ra \`commitOutcome=ROLLED_BACK\` chỉ từ \`SQLState=08006\`: lỗi kết nối không chứng minh transaction đã rollback ở phía database. Nếu root cause hoặc mã lỗi cung cấp bảo đảm rõ ràng theo database, audit có thể phân loại cụ thể sau khi xác minh.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| \`batch_chunk_commit_failures_total\` | Số lần lỗi ở pha commit theo job/Step/resource |
| \`batch_job_failures_total\` | Số lần job kết thúc FAILED |
| \`batch_recovery_attempts_total\` | Số lần thực hiện quy trình recovery |
| \`batch_output_reconciliation_mismatch_total\` | Số lô có thiếu/thừa/khác dữ liệu |
| \`batch_replay_conflicts_total\` | Số business key trùng nhưng payload khác |
| \`batch_last_success_timestamp\` | Thời điểm output sẵn sàng thành công gần nhất |
| \`batch_recovery_duration_seconds\` | Thời gian từ phát hiện failure tới khi kết thúc recovery |

Tên metric ở đây là **đề xuất quy ước ứng dụng**, không phải danh sách meter mặc định của Spring Batch.

Trong metrics nên dùng label ít biến thiên như \`job\`, \`step\`, \`resource\`, \`failureClass\`. Các giá trị \`jobExecutionId\`, \`batchId\`, \`orderId\` phù hợp hơn trong log/traces/audit, tránh tăng số lượng time series vô hạn.

### Không nên tự nuốt exception commit

Nếu một application-level listener hoặc wrapper nhận exception ở pha commit, **không đổi exception thành một WARN rồi báo Job COMPLETED** khi chưa xác định tình trạng dữ liệu. Việc làm đó có thể khiến downstream tiêu thụ output dở dang.

Với failure chưa chắc chắn, có thể đưa business batch sang trạng thái **RECOVERY_REQUIRED** hoặc **QUARANTINED** trong một control store được thiết kế riêng. Nhưng việc cập nhật control store cũng có thể lỗi; cần đồng bộ trạng thái này với JobRepository và có quy trình đối soát độc lập.

## 15. Runbook thực tế cho vận hành

Một quy trình phục hồi có thể dùng cho job production:

### Giai đoạn A — Cô lập và thu thập bằng chứng

1. Dừng scheduler tự động lặp lại lô có vấn đề hoặc giữ lock theo batchId.
2. Xác nhận không còn một execution khác đang ghi cùng business keys.
3. Ghi lại JobExecutionId, StepExecutionId, batchId, input version, commit log và error chain.
4. Kiểm tra downstream đã đọc/nhận output hay chưa.

### Giai đoạn B — Đối soát trạng thái

1. Đọc \`BATCH_JOB_EXECUTION\`, \`BATCH_STEP_EXECUTION\`, ExecutionContext qua API hoặc query được phép.
2. Kiểm tra tập output theo batchId từ database/storage thật.
3. So với snapshot input và quy tắc transform; phát hiện **missing, unexpected, duplicate, mismatch**.
4. Kiểm tra receipts ở external API, outbox hoặc broker khi có side effect.
5. Xác định trạng thái: **rollback confirmed**, **commit confirmed** hay **outcome still unknown**.

### Giai đoạn C — Phục hồi

1. Nếu transaction rollback xác định và checkpoint hợp lệ: restart theo cơ chế Spring Batch, với writer đã an toàn khi replay.
2. Nếu commit đã xác định nhưng metadata chậm/thiếu: xử lý sự lệch theo runbook, không vội tạo JobInstance mới.
3. Nếu kết quả không rõ: replay theo business key/idempotency hoặc đối soát và xử lý các record thiếu với một execution sửa lỗi riêng được kiểm soát.
4. Nếu side effect đã công bố sai: dùng correction/compensation nghiệp vụ, không xóa DB tùy tiện rồi giả định hệ thống ngoài cũng đã quay lui.

### Giai đoạn D — Đóng sự cố

1. Chạy kiểm tra final output theo hợp đồng.
2. Xác minh không có execution song song cùng sở hữu lô.
3. Ghi audit recovery và mapping giữa JobExecution gốc với execution phục hồi.
4. Chỉ cập nhật business status READY khi các điều kiện bắt buộc đều đạt.
5. Lưu nguyên nhân, biện pháp sửa lỗi và kịch bản kiểm thử để ngăn tái diễn.

Nếu metadata JobRepository bị giữ ở trạng thái STARTED sau process crash, **không trực tiếp UPDATE STATUS** trong database production chỉ để mở đường restart. Cần kiểm tra process còn sống, transaction còn mở, scheduler lock và tài liệu recovery của phiên bản Spring Batch đang dùng. Việc sửa metadata thủ công phải là thao tác cuối cùng có kiểm soát.

## 16. Các sai lầm thường gặp

**“Có exception trong commit nghĩa là rollback.”** Sai khi COMMIT đã thành công ở DB nhưng ACK bị mất hoặc callback hậu commit ném exception. Cần xác minh dữ liệu bền vững.

**“Writer không ném lỗi nghĩa là output đã commit.”** Writer thường chạy trước commit; database có thể từ chối commit hoặc transaction bị rollback-only.

**“readCount/writeCount cho biết chính xác record đã commit.”** Các counter không thay thế việc đối soát output và checkpoint, đặc biệt khi có retry/rollback.

**“Spring Batch tự xử lý distributed transaction giữa mọi datasource.”** Cùng annotation hoặc cùng Job không có nghĩa hai database/API đã có atomic commit.

**“Cứ retry cùng Job với tham số mới.”** Tham số identifying mới tạo JobInstance mới; có thể đọc lại từ đầu và gây duplicate.

**“Unique constraint đã đủ cho idempotency.”** Constraint ngăn trùng vật lý nhưng có thể khiến replay FAILED. Cần định nghĩa chính sách xử lý key đã tồn tại và kiểm tra payload khác.

**“ON CONFLICT DO NOTHING luôn an toàn.”** Có thể che giấu input mới khác giá trị so với bản ghi cũ. Kiểm tra hash/amount và báo conflict khi không tương đương.

**“Skip lỗi commit như skip item hỏng.”** Commit failure là vấn đề transaction/chunk; không xác định được một item lỗi để bỏ qua an toàn.

**“Tất cả lỗi DB đều retry được.”** Có lỗi vĩnh viễn, lỗi serialization có transaction abort xác định và lỗi kết nối với outcome không chắc chắn; phải phân loại đúng.

**“Dùng Thread.sleep rồi kill DB là test chính xác.”** Timing không ổn định giữa máy local và CI; cần fault injection theo ranh giới transaction và xác nhận outcome thực tế.

**“Transaction DB sẽ rollback request HTTP đã gửi.”** Side effect ngoài transaction cần idempotency, outbox hoặc compensation.

**“Chỉ cần job COMPLETED là output đúng.”** Job status là tín hiệu thực thi; sau recovery vẫn cần kiểm tra tập record, giá trị, không trùng và điều kiện publish.

**“Có thể sửa bảng metadata Spring Batch tùy ý.”** Một thao tác sửa sai có thể khiến checkpoint, execution status và output lệch thêm; cần runbook và bằng chứng.

**“File đã xuất hiện là có thể tiêu thụ.”** File có thể đang dở dang hoặc chưa được verify; publish bằng manifest/version/READY marker sau khi hoàn tất.

## 17. Nguyên tắc thiết kế khả năng phục hồi

Để xử lý **failure khi commit** an toàn trong Spring Batch Core Processing, nên thiết kế ngay từ đầu theo các nguyên tắc sau:

1. **Xác định transaction boundary thật** cho business data, Batch metadata và từng external side effect.
2. **Cho phép outcome không chắc chắn**: exception ở commit có thể xuất hiện sau khi DB đã hoàn tất giao dịch.
3. **Lưu checkpoint có thể khôi phục** với \`ItemStream\`/ExecutionContext và input ổn định theo JobInstance.
4. **Thiết kế replay idempotent** bằng business key, payload/version kiểm soát và chiến lược merge hoặc xử lý conflict rõ ràng.
5. **Đối soát kết quả bền vững** theo expected set, không chỉ dựa vào status hoặc các counter.
6. **Tách publish khỏi ghi tạm** để consumer chỉ nhận output đã hoàn tất và xác minh.
7. **Kiểm thử cả trước commit, sau commit và commit outcome không rõ** bằng fault injection phù hợp với tầng lỗi muốn mô phỏng.
8. **Vận hành bằng ID và runbook**: jobExecutionId, stepExecutionId, batchId, transaction resource, input version và audit recovery.

Điểm khó nhất của commit failure không phải luôn là làm job chạy tiếp, mà là **biết được công việc nào đã thực sự hoàn tất và có thể lặp lại phần chưa chắc chắn mà không phá tính đúng đắn của dữ liệu**. Khi transaction boundary, checkpoint, idempotency và reconciliation được thiết kế cùng nhau, Spring Batch có thể phục hồi từ lỗi commit mà vẫn bảo vệ tính đầy đủ, tính duy nhất và khả năng truy vết của output.
