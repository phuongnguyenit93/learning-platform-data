# Transactional writer trong Spring Batch: bảo đảm tính nhất quán của dữ liệu đầu ra

Trong một batch job, việc ghi được dữ liệu chưa đồng nghĩa với việc dữ liệu đó đã được **commit**. Nếu một phần của chunk được ghi thành công rồi phần tiếp theo gặp lỗi, Spring Batch cần biết phải hoàn tác những thay đổi nào, khi nào được thử lại và từ đâu được tiếp tục sau khi khởi động lại job. Đây là lý do **transactional writer** là một thành phần quan trọng của *output consistency* (tính nhất quán của đầu ra).

Bài này tập trung vào **chunk-oriented processing**: một `ItemWriter` ghi dữ liệu vào tài nguyên hỗ trợ giao dịch (điển hình là cơ sở dữ liệu) dưới sự điều phối của transaction manager do `Step` cấu hình. Ví dụ sử dụng API Spring Batch 5.x trở lên với `ItemWriter.write(Chunk<? extends T>)`; ở Spring Batch 4.x, phương thức tương ứng nhận `List<? extends T>`.

## 1. Transactional writer giải quyết vấn đề gì?

Giả sử một step đọc 300 giao dịch thanh toán, xử lý chúng rồi ghi vào bảng `ledger_entry` với `chunkSize = 100`:

- Chunk 1 (bản ghi 1–100) ghi thành công và commit.
- Chunk 2 (101–200) đang ghi thì bản ghi 157 vi phạm ràng buộc dữ liệu.
- Chunk 3 (201–300) chưa được xử lý.

Nếu writer tham gia **cùng transaction của chunk**, toàn bộ thay đổi cơ sở dữ liệu do chunk 2 thực hiện sẽ bị rollback; không có trạng thái nửa chunk đã lưu, nửa chunk chưa lưu. Chunk 1 vẫn tồn tại vì nó đã được commit trong một transaction trước đó. Tùy cấu hình xử lý lỗi, step có thể retry, skip bản ghi lỗi hoặc thất bại và được restart.

Nếu writer gọi HTTP API, gửi email hoặc ghi vào tài nguyên không được phối hợp với transaction, một số tác động có thể đã xảy ra trước khi Spring Batch rollback. Vì vậy, cụm từ *transactional writer* phải được hiểu chính xác:

> **Writer có tính giao dịch khi các tác động ghi của nó thực sự tham gia vào transaction do step quản lý, và hệ thống lưu trữ có khả năng commit/rollback các tác động đó.** Chỉ đặt tên lớp là `TransactionalWriter` hay thêm `@Transactional` không tự tạo ra bảo đảm này.

Ba thuộc tính thường bị nhầm lẫn:

| Thuộc tính | Ý nghĩa | Phạm vi |
|---|---|---|
| **Atomicity** (tính nguyên tử) | Các thay đổi cùng transaction được commit toàn bộ hoặc rollback toàn bộ. | Thông thường là **mỗi chunk**, không phải cả job. |
| **Idempotency** (tính lặp an toàn) | Ghi lại cùng một sự kiện không tạo thêm tác dụng ngoài ý muốn. | Quy tắc nghiệp vụ và thiết kế khóa/ràng buộc. |
| **Exactly-once effect** | Một sự kiện chỉ gây ra đúng một tác động nghiệp vụ cuối cùng, dù có retry/crash. | Cần phối hợp transaction, checkpoint, khóa idempotency và đôi khi cả phía tiêu thụ. |

Transaction là nền tảng, nhưng **transaction riêng lẻ không chứng minh được exactly-once xuyên qua mọi hệ thống**.

## 2. Transaction của chunk bao quanh writer như thế nào?

Với một chunk-oriented step thông thường, `PlatformTransactionManager` quản lý transaction cho chu kỳ đọc, xử lý và ghi dữ liệu của mỗi chunk:

~~~mermaid
flowchart TD
    A["Bắt đầu transaction của chunk"] --> B["Đọc và xử lý tối đa N item"]
    B --> C["ItemWriter.write(chunk)"]
    C -->|Không có lỗi| D["Cập nhật trạng thái checkpoint"]
    D --> E["Commit transaction"]
    C -->|Exception| F["Rollback transaction"]
    D -->|Không commit được| F
    F --> G["Retry / skip / kết thúc step thất bại"]
    E --> H{"Còn dữ liệu?"}
    H -->|Có| A
    H -->|Không| I["Step hoàn tất"]
~~~

Trình tự trên là mô hình khái niệm. Việc đọc từ một tài nguyên cụ thể có thể chịu các quy tắc buffering và restart riêng; ghi trạng thái `ExecutionContext`/checkpoint cũng phụ thuộc vào cấu hình `JobRepository`. Tuy nhiên, **ranh giới commit của writer cơ sở dữ liệu là ranh giới transaction của chunk**.

Trong Spring Batch 5+, hợp đồng writer có dạng:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

`write` được gọi với một nhóm item, và có thể ném exception. Interface này **không** tự định nghĩa cơ chế commit/rollback. Cơ chế đó đến từ tài nguyên ghi dữ liệu và transaction manager:

- `JdbcBatchItemWriter` dùng JDBC để ghi dữ liệu; các câu lệnh của nó tham gia JDBC transaction hiện hành khi `DataSource` và transaction manager được cấu hình đúng.
- Writer dùng JPA cần một `EntityManager` được quản lý trong transaction tương ứng; SQL có thể chỉ được gửi/kiểm tra đầy đủ khi flush hoặc commit.
- Writer gọi REST API, gửi email hay đẩy dữ liệu ra hệ thống khác thường **không** được rollback chỉ vì transaction của cơ sở dữ liệu rollback.
- Writer ghép nhiều delegate bằng `CompositeItemWriter` chỉ có tính nguyên tử trên những delegate **cùng tham gia một transaction tương thích**. Một delegate ghi database và một delegate gọi HTTP API không tự động trở thành giao dịch phân tán.

Một điểm quan trọng nữa: nếu job gồm 20 chunk và chunk thứ 20 thất bại, 19 chunk đã commit **không tự rollback**. Nếu nghiệp vụ đòi hỏi toàn bộ job phải xuất hiện cùng lúc, cần thiết kế thêm như ghi vào staging table rồi công bố theo batch ID, hoặc một bước publish/swap được kiểm soát.

## 3. Triển khai JDBC writer tham gia transaction của step

Xét yêu cầu ghi các sự kiện tài chính đã chuẩn hóa vào PostgreSQL. Mỗi sự kiện có `eventId` duy nhất và số tiền `amount`. Thiết kế một khóa nghiệp vụ ổn định giúp ghi lại cùng sự kiện an toàn hơn khi job restart hoặc được chạy lại.

### 3.1. Lược đồ đầu ra

~~~sql
CREATE TABLE ledger_entry (
    event_id BIGINT PRIMARY KEY,
    amount   NUMERIC(18, 2) NOT NULL
);
~~~

Khóa chính `event_id` bảo vệ sự duy nhất ở **tầng cơ sở dữ liệu**. Kiểm tra kiểu “SELECT xem có tồn tại rồi mới INSERT” là chưa đủ trong môi trường đồng thời vì hai worker có thể cùng nhìn thấy bản ghi chưa tồn tại.

### 3.2. Writer và step

Ví dụ sau giả định ứng dụng đã cấu hình `ItemReader<LedgerItem>`, `DataSource` và `PlatformTransactionManager` trỏ tới tài nguyên nghiệp vụ thích hợp. Đây là cấu hình Java cho Spring Batch 5.x, sử dụng Java 17+:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class LedgerBatchConfig {

    @Bean
    JdbcBatchItemWriter<LedgerItem> ledgerWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<LedgerItem>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO ledger_entry (event_id, amount)
                VALUES (:eventId, :amount)
                ON CONFLICT (event_id)
                DO UPDATE SET amount = EXCLUDED.amount
                """)
            .itemSqlParameterSourceProvider(item ->
                new MapSqlParameterSource()
                    .addValue("eventId", item.eventId())
                    .addValue("amount", item.amount()))
            .assertUpdates(true)
            .build();
    }

    @Bean
    Step ledgerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<LedgerItem> reader,
            JdbcBatchItemWriter<LedgerItem> ledgerWriter) {

        return new StepBuilder("ledgerStep", jobRepository)
            .<LedgerItem, LedgerItem>chunk(100, transactionManager)
            .reader(reader)
            .writer(ledgerWriter)
            .build();
    }
}

record LedgerItem(long eventId, BigDecimal amount) {}
~~~

Những chi tiết quyết định tính nhất quán:

1. `chunk(100, transactionManager)` quy định cứ tối đa 100 item được xử lý trong một transaction của step. Chunk cuối có thể ít hơn 100 item.
2. `JdbcBatchItemWriter` lấy kết nối JDBC thông qua hạ tầng truy cập dữ liệu của Spring. Khi writer và `transactionManager` cùng dùng đúng `DataSource`, thao tác ghi tham gia transaction hiện hành; step quản lý commit/rollback.
3. SQL `ON CONFLICT ... DO UPDATE` là cú pháp **PostgreSQL**. Với hệ quản trị khác cần chọn cơ chế UPSERT/MERGE phù hợp. Việc chạy lại cùng một `event_id` cùng một `amount` tạo ra cùng trạng thái cuối.
4. `assertUpdates(true)` yêu cầu mỗi câu lệnh batch cập nhật ít nhất một hàng, giúp phát hiện một số trường hợp writer tưởng đã ghi nhưng thực tế không tác động tới hàng nào. Với câu lệnh hoặc driver cố ý trả số hàng cập nhật bằng 0, phải cân nhắc cấu hình này.
5. Đoạn mã không tự mở transaction bên trong `write`. Writer để **chunk step làm chủ transaction**.

Ví dụ trên là idempotent theo nghĩa **gán cùng giá trị tuyệt đối cho cùng khóa sự kiện**. Không được suy rộng điều đó cho mọi SQL. Chẳng hạn câu lệnh:

~~~sql
UPDATE account
SET balance = balance + :delta
WHERE account_id = :accountId;
~~~

là phép cộng dồn: chạy hai lần sẽ cộng tiền hai lần. Nếu bắt buộc cộng dồn, cần ghi nhận `event_id` đã xử lý bằng một ràng buộc unique và chỉ cập nhật số dư khi sự kiện thực sự được nhận lần đầu, trong **cùng một database transaction**.

> **Khi có nhiều DataSource/transaction manager:** chỉ định rõ bean phù hợp (ví dụ bằng `@Qualifier`). Nếu `Step` mở transaction trên database A nhưng writer ghi vào database B qua kết nối tự commit, rollback của A không thể hoàn tác dữ liệu ở B.

## 4. Điều gì xảy ra khi writer thất bại?

Giả sử chunk hiện tại chứa các item `[A, B, C]` và writer dùng JDBC transaction:

1. Writer ghi A và B trong transaction đang mở.
2. Khi ghi C, cơ sở dữ liệu trả lỗi ràng buộc.
3. Writer ném exception lên step.
4. Spring Batch rollback transaction của chunk. Kết quả: cả A, B lẫn C **đều không được commit trong chunk này**.
5. Cấu hình fault tolerance quyết định thử lại, bỏ qua item gây lỗi hoặc kết thúc step với trạng thái `FAILED`.

Những tình huống quan trọng khác nhau:

| Thời điểm lỗi | Đầu ra của writer JDBC cùng transaction | Hệ quả cần xét |
|---|---|---|
| Processor lỗi trước khi writer được gọi | Chưa ghi đầu ra của chunk hiện tại. | Step rollback hoặc xử lý theo retry/skip. |
| Writer ghi một phần rồi ném exception | Các thay đổi chưa commit của **toàn chunk** được rollback. | Retry có thể gọi writer lại với item từng xuất hiện. |
| Commit chunk thành công, chunk sau thất bại | Chunk đã commit vẫn tồn tại. | Restart cần tiếp tục đúng checkpoint. |
| Ứng dụng mất kết nối khi commit | Kết quả commit đôi khi chưa thể khẳng định chỉ từ exception phía ứng dụng. | Không nên giả định chắc chắn đã rollback; dùng khóa nghiệp vụ/idempotency để chịu được việc chạy lại. |
| Gọi HTTP thành công rồi JDBC transaction rollback | HTTP side effect không được rollback bởi JDBC transaction. | Có nguy cơ gửi hoặc ghi trùng khi retry. |
| Crash sau khi dữ liệu đã commit nhưng checkpoint chưa được ghi bền vững | Có thể phát sinh bất đồng giữa tiến độ job và đầu ra nếu hai nguồn lưu trữ không được phối hợp giao dịch. | Dùng cùng ranh giới transaction nếu khả thi và bảo vệ thao tác ghi bằng idempotency. |

### Rollback không có nghĩa là “chưa từng gọi writer”

Đặc biệt khi bật retry hoặc skip, cùng một item có thể đi qua logic writer hơn một lần. Nếu writer thay đổi biến trạng thái trong bộ nhớ, phát sinh số thứ tự ngoài transaction, ghi log làm sự kiện nghiệp vụ hoặc gọi API không idempotent, các tác dụng đó có thể bị lặp dù dữ liệu JDBC đã rollback.

Vì vậy hãy ưu tiên:

- Tách các tác động có thể rollback vào cùng một hệ thống lưu trữ có transaction.
- Dùng khóa nghiệp vụ ổn định và ràng buộc duy nhất thay cho việc sinh khóa mới ở mỗi lần thử.
- Tránh side effect không phục hồi được ngay trong processor/writer nếu có thể.
- Đảm bảo logic xử lý item có thể chịu việc replay mà không làm thay đổi kết quả ngoài mong đợi.

## 5. Retry, skip và transaction phải được thiết kế cùng nhau

Trong Spring Batch, **retry** là xử lý lỗi tạm thời bằng cách thử lại; **skip** là chấp nhận bỏ một item lỗi trong giới hạn đã cấu hình; **rollback** là hoàn tác các thay đổi của transaction hiện tại. Đây là ba khái niệm khác nhau.

Ví dụ một lỗi tranh chấp khóa DB có thể được retry:

~~~java
return new StepBuilder("ledgerStep", jobRepository)
    .<LedgerItem, LedgerItem>chunk(100, transactionManager)
    .reader(reader)
    .writer(ledgerWriter)
    .faultTolerant()
    .retry(org.springframework.dao.CannotAcquireLockException.class)
    .retryLimit(3)
    .build();
~~~

Đây là **ví dụ cấu hình** cho một lỗi có khả năng tạm thời, không phải chỉ dẫn retry mọi exception. Lỗi schema sai, dữ liệu không hợp lệ hoặc ràng buộc unique vi phạm có thể vẫn thất bại sau nhiều lần thử; retry mù quáng chỉ làm tăng tải.

Khi skip lỗi writer, Spring Batch có thể phải cô lập item lỗi khỏi một nhóm item đã ghi, dẫn đến nhiều lần gọi writer và rollback trước khi chunk có thể hoàn tất. Do đó:

- **Writer JDBC cùng transaction:** có thể rollback những lần thử thất bại, sau đó ghi lại các item hợp lệ.
- **Writer không transactional:** các lần thử thất bại có thể đã tạo side effect, ngay cả khi step sau đó quyết định skip item.
- **Writer phụ thuộc trạng thái bên ngoài:** logic “đã xử lý item nào” cần bền vững, có khóa/idempotency và tham gia transaction tương ứng khi có thể.

Không nên dùng cấu hình như `noRollback(...)` để “giữ lại những hàng đã ghi” chỉ nhằm né lỗi, vì nó có thể phá vỡ tính nguyên tử mà nghiệp vụ đang kỳ vọng. Bất kỳ ngoại lệ rollback nào cũng cần được xem xét theo tài nguyên ghi và yêu cầu nhất quán thực tế.

## 6. Writer ghi nhiều bảng hoặc nhiều đích

### 6.1. Hai bảng trong cùng một database transaction

Giả sử mỗi item cần ghi vào `ledger_entry` và `audit_entry`. Hai writer JDBC có thể được gọi tuần tự bởi `CompositeItemWriter`. Nếu cả hai dùng cùng `DataSource` và transaction manager của step, lỗi ở lần ghi bảng thứ hai làm rollback cả thay đổi ở bảng thứ nhất **trong chunk hiện tại**.

~~~java
CompositeItemWriter<LedgerItem> composite = new CompositeItemWriter<>();
composite.setDelegates(List.of(ledgerWriter, auditWriter));
~~~

Điều kiện nằm ở việc **cả hai delegate thực sự tham gia cùng transaction**, không nằm ở bản thân lớp composite. Nếu một delegate tự tạo kết nối với `autoCommit=true` hoặc bắt đầu transaction riêng rồi commit trước, sự bảo đảm sẽ không còn.

### 6.2. Database + HTTP/Kafka/email: cần thiết kế nhất quán liên hệ thống

Không nên giả định transaction JDBC tự động bảo vệ các thao tác mạng. Có ba cách ứng xử phổ biến:

| Cách làm | Ưu điểm | Giới hạn |
|---|---|---|
| Gọi API trực tiếp từ writer | Dễ triển khai. | API thành công nhưng chunk rollback có thể tạo lặp; ngược lại sự cố mạng có thể khiến kết quả API không rõ. |
| Dùng transaction phân tán/XA khi hạ tầng đều hỗ trợ | Có thể phối hợp một số tài nguyên giao dịch. | Chi phí vận hành, giới hạn hỗ trợ và nguy cơ phức tạp khi lỗi; HTTP thông thường không tham gia XA. |
| **Transactional outbox** | Cùng commit dữ liệu nghiệp vụ và ý định phát sự kiện trong một database transaction. | Bên phát sau commit thường giao hàng theo mô hình *at-least-once*; người nhận vẫn cần idempotency. |

Với hệ thống dùng database và message broker, **transactional outbox** thường là giải pháp dễ vận hành hơn việc gọi broker trực tiếp từ chunk writer:

~~~sql
BEGIN;

INSERT INTO ledger_entry (event_id, amount)
VALUES (:eventId, :amount)
ON CONFLICT (event_id)
DO UPDATE SET amount = EXCLUDED.amount;

INSERT INTO outbox_event (event_id, event_type, payload)
VALUES (:eventId, 'LedgerUpdated', :payload)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

Hai lệnh trên chỉ mang tính minh họa: chúng phải được thực thi bởi các writer/repository **trong cùng transaction do step quản lý**, không gọi `BEGIN`/`COMMIT` thủ công trong `ItemWriter`. Một tiến trình phát sự kiện riêng đọc outbox đã commit, gửi lên broker rồi đánh dấu tiến độ. Nếu tiến trình phát crash sau khi gửi nhưng trước khi đánh dấu, nó có thể gửi lại; consumer phải nhận diện `event_id` trùng.

### 6.3. File writer là một trường hợp riêng

File system thông thường không có giao dịch ACID như cơ sở dữ liệu. Một số writer của Spring Batch, chẳng hạn `FlatFileItemWriter`, có cơ chế buffering và quản lý trạng thái để hỗ trợ ghi gần với ranh giới chunk và restart; tuy nhiên **không nên đồng nhất điều đó với khả năng rollback một file vật lý như rollback một database transaction** trong mọi tình huống crash.

Với yêu cầu xuất file nhất quán cao, có thể ghi ra file tạm, đóng và xác thực đầu ra, rồi công bố bằng thao tác rename/move phù hợp với hệ thống file; lưu ý hành vi atomic rename tùy filesystem và vị trí nguồn/đích. Kết hợp tên file gắn với `JobInstance`/batch ID, quy tắc ghi đè rõ ràng và metadata công bố để tránh người tiêu thụ đọc bản chưa hoàn tất.

## 7. Restart và checkpoint: nhất quán cả dữ liệu lẫn tiến độ

Spring Batch dùng `JobRepository` để lưu trạng thái job/step và `ExecutionContext` để duy trì thông tin cần cho restart của các reader/writer có quản lý trạng thái. Khi một chunk commit thành công, tiến độ đã xác nhận cần tương ứng với đầu ra đã lưu. Nếu hai phần này thuộc hai tài nguyên giao dịch độc lập, có thể xuất hiện tình huống:

1. Dữ liệu nghiệp vụ của chunk đã commit.
2. Ứng dụng gặp sự cố trước khi trạng thái checkpoint được ghi nhận đầy đủ.
3. Lần restart chạy lại một phần input.

Đó là một lý do cần **idempotent writer**, dù writer dùng JDBC transaction. Trong một hệ thống phù hợp, cấu hình `JobRepository` và đầu ra nghiệp vụ trên cùng cơ sở dữ liệu/transaction manager có thể giúp phối hợp checkpoint và ghi dữ liệu chặt chẽ hơn; nếu dùng các tài nguyên riêng, phải đánh giá tính nhất quán và kịch bản phục hồi một cách tường minh.

Ngoài restart của **cùng JobInstance**, cần xét trường hợp người vận hành khởi chạy job mới bằng bộ `JobParameters` khác nhưng cùng dữ liệu nguồn. Spring Batch có thể xem đó là một lần chạy hợp lệ khác; chỉ dựa vào cơ chế “đã đọc đến dòng nào” không thể chống ghi trùng về mặt nghiệp vụ. Khóa sự kiện, kiểm soát batch ID và idempotency phải được thiết kế độc lập với việc job có restart hay không.

## 8. Những lỗi triển khai thường gặp

**1. Writer tự commit ngoài transaction của step.** Dùng `DriverManager.getConnection(...)` rồi bật `autoCommit=true`, gọi một SDK không hỗ trợ giao dịch, hoặc mở `REQUIRES_NEW` cho từng item có thể làm dữ liệu được commit trước khi cả chunk hoàn tất. Kết quả là rollback step không còn hoàn tác được những thay đổi đó.

**2. Nhầm lẫn annotation `@Transactional` với việc bảo đảm nhất quán.** Với chunk step, transaction manager của step phải là nguồn điều phối chính. Annotation tự nó không nối hai database, HTTP API hay queue vào cùng transaction; cách proxy Spring áp dụng transaction cũng phụ thuộc vào lời gọi thực tế.

**3. Giả định writer chỉ chạy một lần.** Retry, skip, lỗi commit không rõ kết quả và restart có thể làm lặp tác động ghi. Phép `INSERT` với ID sinh mới mỗi lần, phép cộng dồn số dư hay gửi email trực tiếp đều cần biện pháp bổ sung.

**4. Bắt lỗi rồi trả về thành công.** Nếu writer âm thầm nuốt lỗi SQL, Spring Batch có thể tiếp tục commit và đánh dấu chunk thành công dù một phần đầu ra bị thiếu. Chỉ chuyển lỗi thành kết quả hợp lệ khi nghiệp vụ có chính sách rõ ràng và đã bảo đảm tính nhất quán.

**5. Coi kích thước chunk là ranh giới của cả job.** `chunkSize=100` không làm 10.000 item trở thành một transaction. Mỗi chunk được commit độc lập; chọn kích thước chunk còn ảnh hưởng thời gian giữ khóa, dung lượng bộ nhớ, số lần round trip và khối lượng phải làm lại khi rollback.

**6. Không phân biệt sai sót dữ liệu và lỗi hạ tầng.** Vi phạm validation nghiệp vụ thường phù hợp với phân luồng/skip có kiểm soát; deadlock hoặc kết nối tạm lỗi có thể retry; mất dữ liệu hay commit không rõ cần biện pháp phục hồi khác. Không nên cấu hình retry mọi exception.

## 9. Một số tình huống thực hành để tự kiểm chứng hành vi

| Tình huống | Điều cần quan sát |
|---|---|
| Trong chunk có 3 item, item thứ ba làm writer ném exception sau khi hai item đầu đã ghi JDBC. | Không hàng nào của **chunk thất bại** được commit nếu tất cả câu lệnh dùng cùng transaction. |
| Chunk 1 đã commit; chunk 2 lỗi; sau đó restart job. | Dữ liệu chunk 1 vẫn còn; tiến độ restart và khóa nghiệp vụ ngăn kết quả trùng hoặc bỏ sót. |
| Gửi cùng một `eventId` hai lần với câu lệnh UPSERT idempotent. | Bảng đầu ra vẫn biểu diễn một trạng thái đúng cho sự kiện ấy. |
| Thay UPSERT bằng phép `balance = balance + delta` rồi phát lại item. | Thấy rõ nguy cơ cộng dồn hai lần nếu không có khóa idempotency. |
| Một delegate ghi JDBC, một delegate giả lập API đã nhận yêu cầu rồi ném exception. | Rollback JDBC không thể tự xóa side effect đã xảy ra ở API. |
| Dùng outbox rồi cố ý phát lại cùng `event_id`. | Consumer có khả năng loại sự kiện trùng theo khóa ổn định. |

Các tình huống trên kiểm tra **hành vi hệ thống dưới sự cố**, không chỉ trường hợp job chạy thành công một lần. Đặc biệt, kiểm tra cùng một kết quả nghiệp vụ sau retry/restart là cách nhìn thiết thực hơn so với chỉ đếm số lần `write` được gọi.

## 10. Nguyên tắc thiết kế cần ghi nhớ

Khi xây dựng transactional writer cho Spring Batch:

1. **Xác định đơn vị nguyên tử:** thông thường là một chunk; muốn nguyên tử trên toàn job phải có thiết kế bổ sung.
2. **Để step quản lý transaction:** writer ghi qua đúng `DataSource`/transaction manager, không tự commit riêng.
3. **Bảo vệ trước việc replay:** dùng business key, unique constraint và thao tác idempotent, đặc biệt khi retry, skip hoặc restart.
4. **Hiểu giới hạn của từng tài nguyên:** database có rollback ACID; HTTP, email, file và message broker không tự cùng rollback với database.
5. **Phối hợp tiến độ và đầu ra:** xem xét quan hệ giữa `JobRepository`, checkpoint, database nghiệp vụ và nguồn/đích bên ngoài.
6. **Dùng outbox hoặc cơ chế bù trừ khi cần:** nếu đầu ra chạy qua nhiều hệ thống, thiết kế rõ cách phát lại và xử lý trùng.

**Kết luận:** Trong Spring Batch, transactional writer là sự kết hợp giữa một `ItemWriter` ghi qua tài nguyên hỗ trợ giao dịch và **transaction boundary của chunk step**. Cơ chế này giúp tránh đầu ra JDBC bị commit dở dang trong một chunk. Để đạt *output consistency* khi có retry, restart và nhiều hệ thống tham gia, còn phải thiết kế idempotency, checkpoint và cách công bố dữ liệu một cách có chủ đích.
