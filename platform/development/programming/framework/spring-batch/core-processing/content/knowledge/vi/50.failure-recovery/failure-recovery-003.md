# Failure ở writer trong Spring Batch: phát hiện, rollback và phục hồi

Trong một batch job, `ItemWriter` là nơi kết quả xử lý được ghi ra cơ sở dữ liệu, file, message broker hoặc một API bên ngoài. Lỗi tại đây thường nghiêm trọng hơn việc một item không đọc được: có thể đã có dữ liệu được ghi trước thời điểm lỗi, một phần chunk chưa commit, hoặc một hệ thống bên ngoài đã nhận side effect mà Spring Batch không thể hoàn tác.

**Failure ở writer** là tình huống một thao tác ghi thất bại, tạo ra kết quả không chắc chắn hoặc không thể bảo đảm hợp đồng đầu ra. Để phục hồi đúng, cần phân biệt rõ **writer đã được gọi** với **dữ liệu đã được commit**, xác định tài nguyên nào thật sự tham gia transaction, lựa chọn giữa **retry**, **skip**, **fail-fast** và **restart**, đồng thời bảo vệ kết quả khỏi ghi trùng.

Bài này thuộc **Spring Batch Core Processing → Failure recovery**, tập trung vào chunk-oriented processing trong Spring Batch 5.x trở lên, với `ItemWriter.write(Chunk<? extends T>)`. Các ví dụ dùng Java 17+ và JDBC/PostgreSQL ở nơi cần SQL cụ thể; các nguyên tắc về ranh giới transaction và replay có thể áp dụng cho những writer khác sau khi xét tính chất từng tài nguyên.

## 1. Writer nằm ở đâu trong vòng đời một chunk?

Với step xử lý theo chunk, luồng thường gặp là:

~~~mermaid
flowchart TD
    A["Bắt đầu chunk transaction"] --> B["ItemReader đọc tối đa N item"]
    B --> C["ItemProcessor xử lý từng item"]
    C --> D["ItemWriter.write(chunk)"]
    D -->|Ghi thành công| E["Cập nhật checkpoint / metadata cần thiết"]
    E --> F["Commit transaction"]
    D -->|Writer ném exception| G["Rollback transaction"]
    E -->|Commit thất bại| G
    G --> H{"Chính sách xử lý lỗi"}
    H -->|Lỗi tạm thời| I["Retry theo giới hạn"]
    H -->|Cho phép skip| J["Cô lập và bỏ item lỗi theo chính sách"]
    H -->|Không phục hồi được| K["Step FAILED"]
    I --> D
    J --> D
    F --> L["Bắt đầu chunk tiếp theo"]
~~~

Sơ đồ mô tả **khái niệm**: các bước nội bộ của fault-tolerant step, retry, skip, việc đọc lại item và commit thực tế tùy reader, writer, transaction manager và cấu hình. Điểm không đổi là **mỗi chunk là một ranh giới transaction thường gặp**, còn toàn bộ job không mặc nhiên nằm trong một transaction lớn.

Ví dụ `chunkSize = 3`, reader đưa các item A, B, C vào writer. Writer đã gửi câu lệnh ghi cho A và B, đến C thì database trả lỗi. Nếu cả ba câu lệnh dùng **cùng transaction của step** và transaction đó rollback thành công, A và B **không được commit**, dù code writer đã chạy qua chúng.

Ngược lại, nếu writer gọi HTTP API để tạo giao dịch A và B rồi API thất bại với C, rollback transaction JDBC của step **không xóa** các giao dịch A, B đã được API bên ngoài chấp nhận. Lúc ấy cần idempotency, outbox hoặc cơ chế phục hồi liên hệ thống riêng.

### Hợp đồng ItemWriter

Spring Batch 5.x định nghĩa:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Writer có thể ném exception để báo lỗi. Bản thân interface **không tạo transaction**; ranh giới transaction được cấu hình ở `Step`, còn tài nguyên ghi dữ liệu quyết định liệu thao tác có commit/rollback cùng transaction ấy hay không.

Trong Spring Batch 4.x, `ItemWriter.write` nhận `List<? extends T>`. Khi đọc ví dụ trên internet, cần chú ý khác biệt API giữa các phiên bản.

## 2. Ba mức độ “đã ghi” không được nhầm lẫn

Trong một lần viết dữ liệu, có thể quan sát ba mức độ khác nhau:

| Trạng thái | Ví dụ | Điều có thể kết luận |
|---|---|---|
| **Writer đã được gọi** | `write(chunk)` bắt đầu thực thi. | Chưa đủ bằng chứng về bất kỳ kết quả lưu trữ nào. |
| **Câu lệnh đã chạy hoặc dữ liệu đã flush** | JDBC đã gửi `INSERT`, JPA đã flush. | Thay đổi có thể vẫn đang nằm trong transaction chưa commit. |
| **Transaction đã commit thành công** | Transaction manager xác nhận commit. | Thay đổi thuộc transaction đã được xác nhận bền vững theo bảo đảm của tài nguyên. |

Đặc biệt, callback `ItemWriteListener.afterWrite(...)` thường được gọi sau khi writer hoàn tất **nhưng trước khi transaction của chunk commit**. Vì thế, ghi một sự kiện `PAYMENT_PERSISTED` hoặc gửi email từ `afterWrite` có thể báo thành công quá sớm. Nếu commit tiếp theo thất bại, người nhận đã thấy một thông báo về dữ liệu không được commit.

Nếu cần hành động sau commit, hãy sử dụng cơ chế gắn với transaction/commit một cách phù hợp hoặc thiết kế transactional outbox. Đối với logging, có thể ghi “writer call completed”, nhưng không tự suy ra “chunk committed” từ `afterWrite`.

### Chunk đã commit trước đó không rollback khi chunk sau lỗi

Giả sử input có tám item và `chunkSize = 3`:

| Chunk | Item | Kết quả |
|---|---|---|
| 1 | 1, 2, 3 | Commit thành công. |
| 2 | 4, 5, 6 | Writer lỗi khi ghi item 6; transaction chunk 2 rollback. |
| 3 | 7, 8 | Chưa chạy nếu step thất bại ở chunk 2. |

Khi step kết thúc `FAILED`, **chunk 1 thường vẫn tồn tại** ở database. Việc restart không phải “bắt đầu lại từ một database trống”. Spring Batch dùng metadata và `ExecutionContext` để tiếp tục khi reader/step được cấu hình restart đúng; writer cũng cần chịu được trường hợp replay.

## 3. Phân loại failure ở writer trước khi quyết định phục hồi

Không phải mọi exception đều thích hợp để retry. Cần hiểu lỗi có khả năng tự biến mất hay thuộc về dữ liệu/cấu hình.

| Loại lỗi | Ví dụ | Khả năng phục hồi thường gặp |
|---|---|---|
| **Tạm thời ở hạ tầng** | Deadlock, lock timeout, kết nối DB tạm chập chờn | Retry có giới hạn và khoảng chờ phù hợp, nếu thao tác an toàn khi thử lại. |
| **Ràng buộc dữ liệu** | Vi phạm unique key, foreign key, not-null | Thường cần xử lý dữ liệu, thiết kế idempotency hoặc skip có chính sách; retry mù quáng ít hiệu quả. |
| **Lỗi kiểu/định dạng đầu ra** | Writer chuyển đổi value không được DB/đích chấp nhận | Sửa mapper/transform hoặc loại item theo quy tắc nghiệp vụ. |
| **Lỗi lập trình/cấu hình** | SQL sai cột, schema chưa migrate, sai transaction manager | Fail-fast và sửa lỗi; retry thường làm chậm phát hiện. |
| **Hết tài nguyên** | Disk full, DB hết quota, file không ghi được | Phục hồi tài nguyên rồi restart; tránh retry dồn dập. |
| **HTTP/broker báo lỗi rõ** | HTTP 429/503, broker tạm không khả dụng | Retry có backoff nếu endpoint và yêu cầu hỗ trợ idempotency. |
| **Kết quả không chắc chắn** | Timeout sau khi gửi HTTP; mất kết nối đúng lúc commit | Không giả định side effect chưa xảy ra; dùng khóa idempotency, tra cứu trạng thái hoặc đối soát. |
| **Lỗi độc lập từng item** | Một bản ghi vi phạm quy tắc đầu ra đã công bố | Có thể skip hoặc đưa vào quarantine nếu nghiệp vụ cho phép và writer có khả năng cô lập lỗi. |

Đây là phân loại để **định hướng chính sách**, không phải luật bắt buộc cho mọi hệ thống. Ví dụ cùng một `DataIntegrityViolationException` có thể đại diện một bản ghi trùng cần bỏ qua, hoặc một lỗi nghiêm trọng cho thấy logic nghiệp vụ đã sai.

### Lỗi ở thời điểm commit khác lỗi trong write()

Ngay cả khi `write(chunk)` trả về bình thường, transaction vẫn có thể thất bại ở giai đoạn flush/commit. Với JPA, SQL có thể được trì hoãn đến lúc flush; với JDBC, một constraint hoặc lỗi commit vẫn có thể xuất hiện sau những lệnh trước đó.

Do đó:

1. Không chỉ kiểm tra exception được ném trực tiếp trong `write(...)`.
2. Xem cả `StepExecution`, `JobExecution` và rollback/commit metrics.
3. Khi commit outcome **không rõ do lỗi kết nối**, không tuyên bố chắc chắn toàn bộ dữ liệu đã rollback hay đã commit; phải có cơ chế truy vấn/đối soát dữ liệu cuối.
4. Không kích hoạt side effect không thể rollback chỉ dựa vào callback trước commit.

## 4. Transaction của writer được cấu hình ở đâu?

Đối với JDBC writer, cấu hình chunk step sẽ chỉ rõ transaction manager:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importLedgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<LedgerRow> ledgerReader,
        JdbcBatchItemWriter<LedgerRow> ledgerWriter) {

    return new StepBuilder("importLedgerStep", jobRepository)
        .<LedgerRow, LedgerRow>chunk(100, transactionManager)
        .reader(ledgerReader)
        .writer(ledgerWriter)
        .build();
}
~~~

Điều kiện quan trọng là `JdbcBatchItemWriter` và `transactionManager` phải **tham gia cùng tài nguyên transaction phù hợp**. Nếu step mở transaction trên database A nhưng writer lấy một connection độc lập với `autoCommit=true` tới database B, rollback ở A không thể hoàn tác B.

Một số lỗi thiết kế thường gặp:

- Writer dùng `DriverManager.getConnection(...)` tự mở và commit connection riêng.
- Writer gọi một service với transaction `REQUIRES_NEW` cho từng item rồi commit trước khi chunk hoàn tất.
- Writer có nhiều delegate, một delegate ghi database theo transaction còn delegate khác gọi HTTP API.
- Writer kết hợp nhiều database/queue mà không có cơ chế phối hợp giao dịch tương ứng.
- Code bắt exception rồi chỉ log, khiến step tưởng rằng writer hoàn tất thành công.

**Không nên tự bọc `write(...)` bằng một transaction mới để “an toàn hơn” nếu điều đó tách writer khỏi transaction của chunk.** Cần để bước chunk và các tài nguyên thực tế phối hợp cùng ranh giới commit được thiết kế.

## 5. Ví dụ JDBC writer và đầu ra idempotent

Giả sử mỗi sự kiện thanh toán hợp lệ có `eventId` duy nhất và số tiền `amount`. Một bảng kết quả PostgreSQL:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(80) PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Writer có thể dùng câu lệnh `INSERT ... ON CONFLICT` nếu chính sách là **cùng một sự kiện chỉ có một bản ghi**:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record LedgerRow(String eventId, BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<LedgerRow> ledgerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<LedgerRow>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO ledger_entry (event_id, amount)
            VALUES (:eventId, :amount)
            ON CONFLICT (event_id) DO NOTHING
            """)
        .itemSqlParameterSourceProvider(row ->
            new MapSqlParameterSource()
                .addValue("eventId", row.eventId())
                .addValue("amount", row.amount()))
        .assertUpdates(false)
        .build();
}
~~~

Chú ý:

- `event_id` là business key bền vững. Nếu một item được replay sau rollback/restart, không phát sinh hàng mới cho cùng ID.
- `ON CONFLICT ... DO NOTHING` là cú pháp PostgreSQL; database khác cần SQL tương đương.
- `assertUpdates(false)` phù hợp trong ví dụ này vì một `INSERT` gặp khóa đã tồn tại có thể tạo **0 hàng mới**. Nếu giữ `assertUpdates(true)`, writer có thể coi kết quả 0 hàng là lỗi.
- `DO NOTHING` không chứng minh hai payload trùng ID có nội dung giống nhau. Nếu cùng `event_id` với `amount` khác là sai nghiệp vụ, cần xác minh dữ liệu đã lưu hoặc dùng thiết kế UPSERT có điều kiện/kiểm tra checksum.
- Việc ghi thành công vào database không bảo đảm exactly-once cho các API, file hoặc broker ở ngoài transaction.

Nếu nghiệp vụ là cập nhật số dư bằng phép cộng, cách ghi sau **không tự idempotent**:

~~~sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

Replay cùng sự kiện sẽ cộng thêm một lần nữa. Để tránh, có thể lưu event ID đã xử lý cùng transaction với việc cập nhật số dư, dùng ràng buộc unique và chỉ cập nhật khi sự kiện mới thực sự được chấp nhận.

## 6. Retry writer failure: khi lỗi có thể tự phục hồi

Spring Batch hỗ trợ fault tolerance ở step:

~~~java
import org.springframework.dao.TransientDataAccessException;

@Bean
Step resilientLedgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<LedgerRow> reader,
        JdbcBatchItemWriter<LedgerRow> writer) {

    return new StepBuilder("resilientLedgerStep", jobRepository)
        .<LedgerRow, LedgerRow>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

Ý nghĩa:

1. `.faultTolerant()` chuyển step sang chế độ có chính sách xử lý lỗi.
2. `.retry(TransientDataAccessException.class)` cho phép thử lại các lỗi truy cập dữ liệu tạm thời thuộc kiểu được chọn.
3. `.retryLimit(3)` đặt giới hạn nỗ lực theo chính sách retry; đây **không phải ba lần chạy lại toàn bộ job**.
4. Khi writer ném exception phù hợp, Spring Batch có thể rollback chunk rồi thử lại theo cơ chế fault tolerance. Writer có thể được gọi nhiều lần với dữ liệu đã xuất hiện trong lần thử trước.
5. Khi số lần thử vượt giới hạn hoặc lỗi không thuộc loại retry, step có thể thất bại nếu không có chính sách skip thích hợp.

**Retry chỉ an toàn khi thao tác ghi có thể lặp lại theo hợp đồng nghiệp vụ.** Với JDBC cùng transaction, rollback thường loại bỏ các thay đổi chưa commit của chunk. Nhưng nếu writer gửi HTTP API hoặc commit transaction độc lập, lần thử trước có thể đã tạo side effect; retry lúc ấy cần idempotency key hoặc cơ chế xác định kết quả bên nhận.

### Có nên retry tất cả exception?

Không nên:

~~~java
// Anti-pattern: bỏ qua phân loại lỗi, thử lại cả lỗi schema và dữ liệu.
.retry(Exception.class)
~~~

Một SQL sai cột, validation sai hoặc exception do bug lập trình không tự biến mất sau nhiều lần thử. Retry bừa có thể kéo dài sự cố, tăng tải cơ sở dữ liệu và làm số lần gọi API bên ngoài tăng nhanh.

### Backoff và giới hạn thời gian

Với lỗi mạng, database bị quá tải hoặc HTTP `429`, thử lại ngay lập tức có thể làm tình hình tệ hơn. Có thể cấu hình backoff khi fault tolerance cho phép:

~~~java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(1000L); // Chờ 1 giây giữa các lần retry.

// Gắn vào fault-tolerant step builder:
// .backOffPolicy(backOff)
~~~

Khả năng sử dụng và package cụ thể của backoff policy cần khớp thư viện và phiên bản dự án; trong Spring Batch 5.x các API hỗ trợ retry/backoff của step builder thường được dùng cùng Spring Retry. Mục đích ví dụ là cho thấy cần **khoảng chờ và giới hạn**, không phải coi một giá trị 1 giây phù hợp với mọi môi trường.

Nếu phần ghi là HTTP, còn cần tổng giới hạn thời gian, timeout kết nối/đọc, giới hạn song song và cách xử lý `Retry-After` nếu API cung cấp. Không tạo vòng retry vô hạn ngay bên trong writer rồi che lỗi khỏi Spring Batch.

## 7. Skip writer failure: chỉ khi được phép loại item lỗi

**Skip** là quyết định nghiệp vụ cho phép bỏ qua một item không thể xử lý và tiếp tục các item còn lại. Nó khác **retry**, vì retry mong lỗi biến mất sau lần thử tiếp theo.

Ví dụ chính sách cho phép bỏ tối đa hai output record có lỗi đã định nghĩa rõ:

~~~java
.faultTolerant()
.skip(RejectedOutputRecordException.class)
.skipLimit(2)
~~~

`RejectedOutputRecordException` ở đây là loại exception do ứng dụng định nghĩa cho trường hợp writer có thể xác định **một record cụ thể được phép loại bỏ**. Trong code thực, phải định nghĩa class và đảm bảo writer/processor thật sự ném nó cho đúng loại lỗi.

Khi một writer xử lý nhiều item trong chunk, lỗi ở lần ghi thứ ba không tự chỉ ra item nào an toàn để skip. Spring Batch có thể phải rollback và gọi writer lại với các tập item nhỏ hơn để **cô lập item lỗi** theo thuật toán fault tolerance. Vì vậy writer có thể thấy cùng item nhiều lần ngay cả khi cuối cùng step `COMPLETED` với skip.

Trước khi cho skip tại writer, hãy xác định:

- Lỗi có thực sự thuộc về **một item riêng lẻ** hay do cả batch, schema hoặc tài nguyên ngoài?
- Có thể rollback mọi lần thử thất bại của chunk không?
- Writer có thể viết lại những item hợp lệ mà không tạo tác động trùng không?
- Skip có hợp pháp theo quy tắc nghiệp vụ không? Ví dụ báo cáo tổng số tiền có thể sai nếu tự ý bỏ giao dịch.
- Có cần lưu bản ghi bị loại trong quarantine được kiểm soát quyền truy cập và audit?
- Khi vượt `skipLimit`, step phải thất bại và quy trình vận hành làm gì tiếp?

**Không cấu hình skip chung cho tất cả `DataIntegrityViolationException` chỉ để job “chạy xanh”.** Exception đó có thể do foreign key, duplicate key, null value hoặc lỗi dữ liệu hệ thống. Một skip quá rộng có thể che mất sự cố đáng lẽ phải dừng job.

### Read skip, process skip và write skip

| Loại skip | Lỗi xuất hiện ở đâu | Ví dụ | Hệ quả |
|---|---|---|---|
| `readSkipCount` | Reader hoặc parser | CSV sai cấu trúc. | Item không được chuyển thành đối tượng hợp lệ. |
| `processSkipCount` | Processor | Không đạt quy tắc validation. | Item đã đọc nhưng không tạo output hợp lệ. |
| `writeSkipCount` | Writer | Một output record bị writer từ chối. | Các thao tác ghi cần được rollback/cô lập trước khi tiếp tục. |

Một step có thể kết thúc `COMPLETED` dù có skip nếu chính sách cho phép, nhưng đầu ra là tập con có chủ đích. Monitoring phải hiển thị số skip và nguyên nhân, không đánh đồng `COMPLETED` với “mọi input đều được ghi”.

## 8. Không nuốt exception trong writer

Một anti-pattern nguy hiểm:

~~~java
@Override
public void write(Chunk<? extends LedgerRow> items) {
    for (LedgerRow item : items) {
        try {
            save(item);
        } catch (Exception error) {
            log.warn("Save failed, continue");
        }
    }
}
~~~

Writer đã bỏ qua lỗi và trả về bình thường. Spring Batch có thể tin chunk đã hoàn tất và tiến hành commit/checkpoint dù một số item không được ghi. Điều này khiến:

- `writeCount` và trạng thái step có thể không phản ánh đầy đủ số item thật sự lưu được.
- Cơ chế retry/skip ở step không có cơ hội quyết định.
- Restart có thể bỏ qua item thiếu vì checkpoint đã tiến lên.
- Lỗi nghiệp vụ bị ẩn khỏi monitoring và audit.

Nếu cần loại item theo policy, nên thực hiện validation/filter ở tầng phù hợp hoặc cấu hình fault tolerance/skip có giới hạn. Nếu bắt lỗi để bổ sung ngữ cảnh, hãy **ném lại lỗi phù hợp** (và tránh ghép payload nhạy cảm vào exception message):

~~~java
try {
    saveChunk(items);
} catch (TransientDataAccessException error) {
    throw error; // Để step quyết định rollback/retry.
}
~~~

Đừng chuyển tất cả lỗi thành một exception chung nếu điều đó làm mất khả năng phân loại transient với non-retryable. Nếu wrapping bắt buộc, giữ cause cho chẩn đoán trong kênh phù hợp và cấu hình chính sách nhận đúng loại lỗi.

## 9. Writer ghi nhiều tài nguyên: rollback có giới hạn

Một writer có thể ghi cùng lúc:

- Bảng `orders` và `order_audit` trong một database.
- Database và file CSV.
- Database và HTTP API.
- Database và Kafka/message broker.
- Hai database độc lập.

### Nhiều bảng cùng một database transaction

Nếu hai delegate dùng cùng `DataSource`/transaction manager và không tự commit, thao tác có thể nằm trong một transaction của chunk. Ví dụ `CompositeItemWriter` chỉ gọi nhiều writer theo thứ tự:

~~~java
CompositeItemWriter<LedgerRow> composite = new CompositeItemWriter<>();
composite.setDelegates(List.of(ledgerWriter, auditWriter));
~~~

**Composite không tự tạo transaction phân tán.** Nếu `ledgerWriter` ghi JDBC theo transaction còn `auditWriter` gọi API ngoài, lỗi ở API có thể rollback dữ liệu JDBC nhưng không hoàn tác các tác động khác của API.

### HTTP API: timeout không cho biết chắc kết quả

Giả sử writer gọi API:

~~~text
Writer  --- POST /payments --->  Remote API
Writer  <--- timeout ----------  (API có thể đã commit)
~~~

Có ít nhất hai khả năng:

1. Request chưa được xử lý ở phía API.
2. API đã xử lý và commit thành công, nhưng response bị mất trên đường về.

Nếu writer retry không kèm khóa idempotency, khả năng thứ hai có thể tạo giao dịch trùng. Vì vậy khi thiết kế HTTP writer, cần:

- Gán **eventId/idempotency key ổn định** cho mỗi tác động nghiệp vụ.
- Yêu cầu phía API nhận diện và trả kết quả nhất quán cho request trùng, nếu hợp đồng hỗ trợ.
- Tra trạng thái bằng business key khi kết quả lần gọi không rõ.
- Giới hạn retry và phân biệt timeout với lỗi dữ liệu vĩnh viễn.
- Không giả định transaction database của Spring Batch rollback được HTTP.

### Transactional outbox

Khi cần ghi database và phát sự kiện, một phương án phổ biến là lưu cả dữ liệu nghiệp vụ và **ý định phát sự kiện** trong cùng transaction:

~~~sql
-- Các lệnh sau phải thực thi trong cùng transaction của chunk;
-- không BEGIN/COMMIT thủ công trong ItemWriter.

INSERT INTO ledger_entry (event_id, amount)
VALUES (:eventId, :amount)
ON CONFLICT (event_id) DO NOTHING;

INSERT INTO outbox_event (event_id, event_type, payload)
VALUES (:eventId, 'LEDGER_CREATED', :payload)
ON CONFLICT (event_id) DO NOTHING;
~~~

Sau khi transaction commit, một tiến trình riêng đọc outbox và gửi sự kiện. Nếu tiến trình gửi crash sau khi broker nhận event nhưng trước khi nó lưu tiến độ, sự kiện có thể được gửi lại. Vì vậy consumer vẫn cần xử lý trùng theo event ID. Outbox giúp phối hợp **ghi dữ liệu và ghi ý định phát** ở cùng database; nó không tự tạo exactly-once toàn bộ hệ thống.

### File writer

File system thường không hỗ trợ rollback ACID giống cơ sở dữ liệu. Một số writer của Spring Batch, như `FlatFileItemWriter`, có cơ chế buffering, đồng bộ trạng thái và hỗ trợ restart, nhưng không thể suy ra mọi file write được hoàn tác hoàn hảo sau crash hoặc mất điện.

Với file đầu ra quan trọng, có thể ghi ra file tạm, đóng và kiểm tra kết quả, rồi công bố file bằng rename/move khi filesystem bảo đảm ngữ nghĩa mong muốn. Cần xác định đường dẫn theo `JobInstance`/phiên bản, quy tắc ghi đè và việc xử lý file tạm còn sót lại sau failure.

## 10. Failure ở writer và restart Job

Spring Batch lưu metadata trong `JobRepository` và dùng `ExecutionContext` để hỗ trợ restart cho các reader/writer có quản lý trạng thái. Với cùng `JobInstance`, một `JobExecution` mới có thể tiếp tục sau execution `FAILED`/`STOPPED` theo cấu hình.

~~~text
JobInstance: importLedgerJob(businessDate=2026-11-15)
    |
    +-- JobExecution 101: FAILED
    |      chunk 1: COMMITTED
    |      chunk 2: ROLLED BACK
    |
    +-- JobExecution 102: COMPLETED
           restart cùng JobInstance
~~~

Trong ví dụ:

- Chunk 1 đã commit và thông thường vẫn tồn tại.
- Chunk 2 thất bại được retry/replay hoặc xử lý tiếp khi restart theo checkpoint phù hợp.
- Writer phải chịu được việc một item xuất hiện lại trong quá trình recovery.
- Nếu từng có side effect ngoài transaction, phải đối soát xem thao tác đã hoàn thành ở đích bên ngoài hay chưa.

**Không tạo một JobInstance mới bằng timestamp hoặc `run.id` ngẫu nhiên chỉ để vượt lỗi đã có instance**, nếu mục tiêu là phục hồi từ checkpoint. Làm vậy có thể chạy lại toàn bộ input và nhân đôi tác động đã commit. Muốn restart, cần giữ đúng identifying `JobParameters` và metadata.

### Điều gì xảy ra nếu commit không rõ thành công hay thất bại?

Một tình huống khó là ứng dụng mất kết nối đúng lúc transaction commit:

~~~text
DB nhận COMMIT
   |
   +-- Đã commit nhưng response bị mất?
   |
   +-- Chưa commit và transaction bị rollback?
~~~

Chỉ nhìn exception ở phía ứng dụng chưa chắc xác định được trường hợp nào đã xảy ra. Nếu metadata `JobRepository` và output được lưu trong hai transaction/tài nguyên khác nhau, có thể còn xuất hiện bất đồng giữa checkpoint và dữ liệu nghiệp vụ.

Vì vậy, ngoài transaction, cần thiết kế **đầu ra idempotent** và quy trình **reconciliation** theo business key. Khi restart hoặc chạy lại, hệ thống phải kiểm tra trạng thái cuối chứ không cộng dồn mù quáng.

### Metadata của step không thay thế kiểm tra kết quả nghiệp vụ

`BatchStatus.FAILED` cho biết execution không hoàn tất thành công; nó không nói rằng database đích trống. `writeCount` cho biết thống kê xử lý theo cơ chế Spring Batch; nó không thể chứng minh API ngoài đã commit bao nhiêu request khi có timeout. Với đầu ra quan trọng, cần đối chiếu số lượng/khóa/số tiền hoặc checksum tại nguồn và đích theo chính sách nghiệp vụ.

## 11. Listener giúp quan sát lỗi writer mà không làm nặng recovery

Spring Batch cho phép đăng ký `ItemWriteListener`, `SkipListener` và `StepExecutionListener` để quan sát các giai đoạn lỗi. Listener nên **ghi metadata an toàn** và không phát side effect khó rollback.

Ví dụ `ItemWriteListener`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriteListener;

public class SafeWriterListener implements ItemWriteListener<LedgerRow> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeWriterListener.class);

    @Override
    public void onWriteError(
            Exception error,
            Chunk<? extends LedgerRow> items) {
        log.warn(
            "batch.writer.failed category={} attemptedItems={}",
            classify(error),
            items.size()
        );
    }

    private String classify(Throwable error) {
        if (error instanceof
                org.springframework.dao.TransientDataAccessException) {
            return "DATABASE_TRANSIENT";
        }
        if (error instanceof
                org.springframework.dao.DataIntegrityViolationException) {
            return "DATA_CONSTRAINT";
        }
        return "WRITER_FAILURE";
    }
}
~~~

Listener không log `items` hoặc `error.getMessage()`. Dòng log chứa số item đã **thử ghi**, không phải số item đã commit. Trong một retry, callback lỗi có thể xuất hiện nhiều lần; không nên coi số dòng log lỗi bằng số item bị mất.

Ví dụ listener cho write skip:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class WriterSkipListener implements SkipListener<LedgerRow, LedgerRow> {

    private static final Logger log =
        LoggerFactory.getLogger(WriterSkipListener.class);

    @Override
    public void onSkipInWrite(LedgerRow item, Throwable error) {
        // Không in toàn bộ item hoặc raw exception.
        log.warn("batch.item.skipped stage=WRITE category=REJECTED_OUTPUT");
    }
}
~~~

Nếu nghiệp vụ yêu cầu lưu item bị reject, hãy dùng quarantine store có quyền truy cập thích hợp và ranh giới transaction rõ ràng. Không ghi dữ liệu nhạy cảm vào log hoặc gọi API không idempotent trực tiếp từ một callback có thể được kích hoạt trong luồng xử lý retry/rollback.

### Những chỉ số hữu ích

Theo `StepExecution`, nên quan sát:

| Chỉ số | Điều cho biết |
|---|---|
| `readCount` | Số item đã được đọc theo định nghĩa của step. |
| `writeCount` | Số item writer được step ghi nhận đã xử lý thành công. |
| `writeSkipCount` | Số item bị skip tại giai đoạn writer. |
| `processSkipCount` và `readSkipCount` | Item bị loại ở các giai đoạn khác. |
| `rollbackCount` | Số lần rollback được step ghi nhận. |
| `commitCount` | Số lần commit được step ghi nhận. |
| `BatchStatus` / `ExitStatus` | Trạng thái và kết quả kết thúc. |
| `jobExecutionId` / `stepExecutionId` | Điểm nối tới log/tracing và lịch sử repository. |

Không tự đồng nhất `writeCount` với “số request API ngoài đã xử lý chính xác một lần”. Chỉ số của Spring Batch không thể thay cho việc đối soát một tài nguyên có semantics riêng.

## 12. Một chiến lược phục hồi theo loại lỗi

Có thể ra quyết định theo luồng:

~~~mermaid
flowchart TD
    A["Writer failure"] --> B{"Tài nguyên ghi có tham gia\nchunk transaction không?"}
    B -->|Có| C{"Lỗi có tính tạm thời?"}
    B -->|Không / không chắc| D["Xác minh side effect ở đích\nvà khóa idempotency"]
    C -->|Có| E["Retry có giới hạn\nvà backoff"]
    C -->|Không| F{"Có thể cô lập item lỗi\nvà nghiệp vụ cho skip?"}
    F -->|Có| G["Skip có giới hạn\nvà quarantine / audit"]
    F -->|Không| H["Fail step, giữ metadata\nđể sửa và restart"]
    D --> I{"Đã có tác động ở đích?"}
    I -->|Có hoặc chưa rõ| J["Tra trạng thái / đối soát\ntránh tác động trùng"]
    I -->|Chưa có và có bảo đảm| K["Retry theo hợp đồng API"]
    E --> L["Kiểm tra kết quả cuối"]
    G --> L
    H --> L
    J --> L
    K --> L
~~~

Trong thực tế, quyết định phụ thuộc mục tiêu nghiệp vụ. Ví dụ job đối soát bắt buộc đủ 100% giao dịch có thể không được skip bất kỳ item nào; còn job nhập dữ liệu tham khảo có thể chấp nhận vài bản ghi invalid nếu đã ghi reject report và báo rõ số lượng.

### Một bảng chính sách gợi ý

| Failure | Chính sách ban đầu | Điều kiện trước khi tiếp tục |
|---|---|---|
| DB deadlock tạm thời | Retry có giới hạn. | Writer dùng transaction và thực thi an toàn khi replay. |
| SQL schema không khớp | Fail-fast. | Migration/cấu hình được sửa, sau đó restart. |
| Bản ghi vi phạm unique | Phân loại: duplicate hợp lệ hay dữ liệu sai. | Ràng buộc business key/idempotency và chính sách bỏ qua rõ. |
| File hết dung lượng | Fail; phục hồi tài nguyên. | Có thể tiếp tục/ghi lại file không trùng hoặc hỏng. |
| API 503 | Retry có backoff. | Endpoint có idempotency hoặc truy vấn trạng thái. |
| API timeout sau request | Kết quả không xác định. | Tra cứu theo idempotency key trước khi lặp tác động. |
| Một item không thể xuất | Skip nếu nghiệp vụ cho phép, nếu không fail. | Writer có thể cô lập lỗi, đếm và ghi reject đúng. |
| Process crash giữa các chunk | Restart từ metadata. | Checkpoint tin cậy, output idempotent/đối soát. |

## 13. Thiết kế kiểm thử failure ở writer

Một bài kiểm thử success path chưa đủ. Cần chủ động gây lỗi ở vị trí có thể dự đoán, kiểm tra **trạng thái output cuối** và metadata.

### 13.1. Kiểm thử rollback một chunk JDBC

Giả sử bảng `ledger_entry` trống, input gồm A, B, C trong **một chunk size 3**. Writer thực hiện JDBC insert cùng transaction của step và cố ý ném exception ở C:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

class FailingLedgerWriter implements ItemWriter<LedgerRow> {

    private final JdbcTemplate jdbc;

    FailingLedgerWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends LedgerRow> chunk) {
        for (LedgerRow row : chunk) {
            jdbc.update(
                "INSERT INTO ledger_entry(event_id, amount) VALUES (?, ?)",
                row.eventId(),
                row.amount()
            );
            if ("C".equals(row.eventId())) {
                throw new IllegalStateException("DELIBERATE_WRITER_FAILURE");
            }
        }
    }
}
~~~

Đoạn code là **writer dùng để tạo lỗi trong integration test**, không phải triển khai production. Nếu `JdbcTemplate` dùng cùng transaction đã được cấu hình cho step, khi C ném lỗi:

- A và B đã thực hiện câu `INSERT` nhưng vẫn ở transaction chưa commit.
- Transaction chunk rollback, nên không hàng nào của A, B, C được giữ sau rollback thành công.
- Step không có skip/retry phù hợp sẽ kết thúc `FAILED`.

Trong test, sau khi `JobExecution` kết thúc, truy vấn bảng và khẳng định không có các ID A/B/C; đồng thời kiểm tra `BatchStatus.FAILED`. Kiểm tra này đáng tin cậy hơn chỉ assert writer đã ném exception.

### 13.2. Kiểm thử chunk trước commit, chunk sau lỗi

Cho input A, B, C và `chunkSize = 2`. Nếu chunk đầu A/B đã commit, còn chunk thứ hai C ném lỗi, cần thấy:

- A và B **vẫn tồn tại**.
- C không có trong đầu ra nếu transaction của chunk chứa C rollback.
- Step `FAILED`.
- Restart bằng **cùng identifying JobParameters** xử lý lại phần chưa hoàn thành mà không chèn trùng A/B.

Fixture nhỏ ba item là đủ để minh họa ranh giới chunk; không cần hàng nghìn bản ghi.

### 13.3. Kiểm thử retry lỗi tạm thời

Tạo một writer test đếm số lần gọi và ném một exception **được cấu hình retry** ở lần đầu, sau đó ghi thành công. Xác minh:

1. Có ít nhất một rollback/retry theo cấu hình.
2. Job kết thúc `COMPLETED` khi lỗi đã biến mất trước giới hạn.
3. Mỗi business key chỉ có một kết quả cuối ở đích.
4. Nếu lỗi kéo dài vượt giới hạn, job `FAILED` và metadata phù hợp.

Không đặt các assertion vào đúng số lần gọi `write` nếu thuật toán fault tolerance có thể chia nhỏ chunk hoặc gọi writer khác nhau theo phiên bản. Hãy quan sát invariant về dữ liệu cuối và trạng thái step, chỉ kiểm tra số lần thử khi đó là mục tiêu cụ thể của test.

### 13.4. Kiểm thử skip writer

Tạo ba item, cố ý cho một item bị writer từ chối theo exception được đưa vào `skip(...)`. Kiểm tra hai item hợp lệ được ghi đúng một lần, item lỗi không được ghi, `writeSkipCount` phản ánh chính sách và job có trạng thái mong đợi.

Test thứ hai cho số item lỗi vượt `skipLimit` để xác nhận step thực sự thất bại, thay vì âm thầm bỏ qua tất cả.

### 13.5. Kiểm thử side effect ngoài transaction

Dùng một fake HTTP server có thể:

- Nhận request nhưng trì hoãn response đến timeout.
- Nhận cùng idempotency key hai lần.
- Trả 503 rồi 200.
- Trả lỗi validation vĩnh viễn.

Sau mỗi tình huống, kiểm tra **số tác động nghiệp vụ cuối ở server** thay vì chỉ kiểm tra số request được gửi. Một retry có thể gửi hai request hợp lệ nhưng server chỉ tạo một giao dịch nhờ idempotency.

### Ma trận kiểm thử tổng hợp

| Tình huống | Dữ liệu nhỏ | Kỳ vọng |
|---|---|---|
| Writer lỗi giữa chunk JDBC | 3 item, lỗi ở item thứ 3, chunk 3 | Rollback toàn chunk. |
| Lỗi sau một chunk đã commit | 3 item, chunk 2, lỗi item 3 | Hai item trước giữ nguyên; item 3 chưa commit. |
| Transient retry rồi thành công | 1–2 item, lỗi lần đầu | Một kết quả cuối đúng, job thành công trong giới hạn. |
| Retry hết giới hạn | Lỗi kéo dài | `FAILED`, không có output không nhất quán. |
| Skip đúng một item | 3 item, 1 rejected | Item hợp lệ đủ; counter skip và audit phù hợp. |
| Skip vượt giới hạn | 3 item, nhiều rejected | Step `FAILED`. |
| Duplicate event sau restart | Event ID lặp lại | Không có hàng nghiệp vụ trùng. |
| HTTP timeout nhưng server đã xử lý | 1 event có idempotency key | Không tạo tác động nghiệp vụ lần hai. |
| Mất kết nối khi commit | Fault injection/phỏng lập | Kết quả được xác minh bằng truy vấn/đối soát, không dựa vào giả định rollback. |
| File writer crash trước công bố | File tạm/đích | Không công bố một file đầu ra chưa hoàn tất theo chính sách. |

## 14. Logging và monitoring khi writer thất bại

Một log writer failure hữu ích cần cho phép nối lỗi tới execution và nhóm nguyên nhân, nhưng không nên dump toàn bộ chunk hoặc dữ liệu nhạy cảm:

~~~json
{
  "event": "batch.writer.failed",
  "jobName": "importLedgerJob",
  "jobExecutionId": 8102,
  "stepName": "writeLedgerStep",
  "stepExecutionId": 9205,
  "correlationId": "req-301",
  "errorCode": "DATABASE_TRANSIENT",
  "attemptedItemCount": 100
}
~~~

Đây là schema **do ứng dụng định nghĩa**, không phải JSON Spring Batch tự sinh mặc định. `attemptedItemCount` chỉ là số item trong lời gọi writer gặp lỗi, không chứng minh đã có 100 item được commit.

Không nên log:

~~~java
log.error("writer failed chunk={}", chunk);
log.error("writer failed item={}", item);
log.error("SQL failed with params={}", fullParameters);
~~~

Với item chứa thông tin cá nhân, số tài khoản, token hoặc payload đối tác, những câu log này có thể làm lộ dữ liệu qua stdout, collector và hệ thống dashboard. Exception từ parser/JDBC/HTTP cũng có thể chứa giá trị nhạy cảm trong message/cause chain; nên chuẩn hóa `errorCode` và chỉ ghi stack trace vào kênh chẩn đoán đã được kiểm soát sau khi đánh giá nội dung.

Các chỉ số giúp vận hành gồm:

- Số `JobExecution`/`StepExecution` `FAILED` theo job và step.
- `writeSkipCount`, `rollbackCount`, `commitCount`, `writeCount`.
- Thời gian xử lý từng chunk và thời gian retry/backoff.
- Mã lỗi phân loại: transient, data constraint, timeout, schema/configuration.
- Số event chưa phát trong outbox hoặc số reject đang chờ sửa, nếu hệ thống có.
- Độ lệch giữa số lượng nguồn và đầu ra sau khi đối soát.

**Không đưa `jobExecutionId`, `eventId` hay correlation ID duy nhất của từng request làm metric tag thông thường** vì có thể làm cardinality tăng mạnh. Giữ những ID đó trong log/tracing/audit để truy vết chi tiết; metric dùng nhãn có số lượng hữu hạn như `jobName`, `stepName`, `errorCode` và `status`.

## 15. Quy trình xử lý sự cố writer trong vận hành

Khi batch step thất bại ở writer, có thể đi theo quy trình sau:

1. **Xác định execution và thời điểm lỗi.** Tra `jobExecutionId`, `stepExecutionId`, `JobRepository`, trạng thái step và mã lỗi.
2. **Xác định tài nguyên writer.** JDBC cùng transaction của step, file, HTTP, broker hay nhiều đích? Có tài nguyên nào tự commit riêng không?
3. **Phân loại lỗi.** Transient, dữ liệu vĩnh viễn, schema, tài nguyên cạn, commit outcome không rõ hoặc side effect liên hệ thống.
4. **Xác minh kết quả đã commit.** Đối chiếu theo business key; phân biệt chunk trước đã commit với chunk đang lỗi. Với API ngoài, tra idempotency/event ID.
5. **Chọn recovery path.** Retry có backoff, sửa dữ liệu rồi restart, skip/quarantine theo policy hoặc phục hồi tài nguyên.
6. **Giữ đúng JobInstance khi restart.** Dùng cùng identifying parameters và checkpoint; không xóa metadata chỉ để vượt trạng thái.
7. **Theo dõi đến kết quả cuối.** Xác minh bản ghi đầu ra, số skip/retry, dữ liệu thiếu/trùng và cảnh báo, không chỉ nhìn vào `BatchStatus.COMPLETED`.

Nếu execution còn bị đánh dấu `STARTED` sau khi node thật sự đã chết, cần xác minh tiến trình và side effect trước khi thay đổi metadata. Không tùy tiện sửa trực tiếp bảng `BATCH_JOB_EXECUTION` hoặc xóa toàn bộ `BATCH_*` để “mở khóa”: có thể làm mất checkpoint và dẫn đến chạy lại dữ liệu đã commit.

### Khi nào không nên tự restart?

Không nên tự restart ngay khi:

- Không biết API bên ngoài đã tạo bao nhiêu tác động trong lần trước.
- Writer có phép cộng dồn không idempotent và checkpoint không đáng tin cậy.
- Tệp đầu ra đã bị công bố dở dang và người tiêu thụ có thể đã đọc.
- Database và metadata repository không đồng bộ, chưa đối soát.
- Lỗi thuộc schema/logic chưa được sửa, chắc chắn tái diễn.
- Lần thực thi trước có thể vẫn còn hoạt động trên node khác.

Những tình huống này cần quyết định phục hồi có dữ liệu kiểm chứng. Retry hoặc restart tự động chỉ phù hợp khi hành vi an toàn của writer đã được thiết kế và kiểm thử.

## 16. Các sai lầm thường gặp

**“Writer đã gọi INSERT, vậy hàng đã lưu.”** Không chắc; nếu transaction chưa commit và sau đó rollback, hàng không tồn tại. Cần phân biệt SQL execution/flush với transaction commit.

**“Step FAILED thì mọi output của job đã rollback.”** Sai trong chunk-oriented processing thông thường: những chunk trước đã commit thường vẫn còn. Cần kiểm tra trạng thái đầu ra trước khi restart.

**“Có retry thì cứ retry mọi exception.”** Lỗi schema, dữ liệu không hợp lệ và logic sai thường không tự hồi phục. Retry quá rộng làm chậm fail và có thể nhân đôi side effect ngoài transaction.

**“Bắt exception rồi continue để job không thất bại.”** Nếu writer nuốt lỗi, Spring Batch có thể commit/checkpoint dù thiếu dữ liệu. Hãy dùng chính sách retry/skip tường minh hoặc fail.

**“Đã dùng CompositeItemWriter thì mọi delegate cùng rollback.”** Composite chỉ gọi delegates; transaction thực sự tùy datasource, transaction manager và tài nguyên từng delegate.

**“HTTP timeout nghĩa là phía API chưa xử lý.”** Có thể API đã commit nhưng response mất. Retry an toàn cần idempotency hoặc tra cứu trạng thái.

**“Bật skip cho DataIntegrityViolationException là xử lý xong.”** Có thể bỏ mất giao dịch bắt buộc hoặc che lỗi dữ liệu hệ thống. Phải phân biệt duplicate hợp lệ, vi phạm ràng buộc và failure của cả chunk.

**“ItemWriteListener.afterWrite nghĩa là dữ liệu đã commit.”** Callback thường xảy ra trước commit của chunk, không phải sự kiện xác nhận commit cuối.

**“Restart bằng run.id mới là tiếp tục job cũ.”** Khi `run.id` là identifying và thay đổi, đó là JobInstance mới; có nguy cơ xử lý lại toàn bộ input. Restart đúng cần giữ instance cũ và dùng metadata.

**“Chỉ cần kiểm tra `writeCount` là biết API ngoài không có bản ghi trùng.”** Counter nội bộ không xác định chính xác số side effect ở hệ thống ngoài transaction, đặc biệt với timeout. Cần đối soát ở hệ thống đích.

## 17. Nguyên tắc thiết kế writer có khả năng phục hồi

Một writer đáng tin cậy trong Spring Batch thường tuân theo các nguyên tắc:

1. **Tôn trọng transaction boundary của chunk.** Ghi vào tài nguyên giao dịch phù hợp với transaction manager của step; tránh tự commit riêng nếu không có thiết kế rõ ràng.
2. **Ném exception khi không bảo đảm kết quả ghi.** Để Spring Batch quyết định rollback, retry, skip hoặc fail theo chính sách.
3. **Phân loại lỗi trước khi retry.** Chọn transient exception cụ thể, giới hạn số lần, có backoff và không retry vô hạn.
4. **Chỉ skip khi có hợp đồng nghiệp vụ.** Writer phải có khả năng cô lập item lỗi và bảo đảm item hợp lệ không bị nhân đôi.
5. **Thiết kế idempotency ở đầu ra.** Dùng business/event key, unique constraints, UPSERT có kiểm soát, hoặc cơ chế tương ứng ở API.
6. **Phối hợp tác động ngoài transaction.** Dùng outbox, idempotency key, cơ chế tra trạng thái hoặc compensation theo yêu cầu.
7. **Giữ metadata để restart.** Không xóa checkpoint/history tùy tiện; xác minh các chunk đã commit và kết quả cần replay.
8. **Quan sát metadata an toàn.** Log job/step IDs, error code, counters và trạng thái; không dump item hoặc toàn bộ chunk nhạy cảm.
9. **Kiểm thử lỗi thật.** Gây lỗi giữa chunk, lỗi sau một commit, timeout với kết quả không rõ, vượt giới hạn retry/skip và restart sau crash.

## Kết luận

**Failure ở writer** không chỉ là một exception cần bắt; nó là câu hỏi về **trạng thái dữ liệu đã ghi, ranh giới commit và khả năng chạy lại an toàn**. Với writer JDBC cùng transaction của chunk, lỗi thường dẫn tới rollback các thay đổi chưa commit của chunk, trong khi các chunk trước đó vẫn tồn tại. Spring Batch có thể retry, skip hoặc restart theo cấu hình, nhưng các cơ chế ấy có thể gọi writer lặp lại và không tự hoàn tác HTTP, file hoặc broker bên ngoài transaction.

Hãy thiết kế recovery từ đầu: phân loại lỗi, sử dụng transaction đúng, phát sinh business key ổn định, bảo vệ writer bằng idempotency, lưu checkpoint đáng tin cậy, đối soát khi commit outcome không rõ và kiểm chứng đầu ra cuối. Khi đó một lần writer thất bại trở thành tình huống có thể phát hiện, giải thích và phục hồi mà không làm mất hoặc nhân đôi dữ liệu nghiệp vụ.
