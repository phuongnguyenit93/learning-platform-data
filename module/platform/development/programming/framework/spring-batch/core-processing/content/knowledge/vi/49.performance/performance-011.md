# Tối ưu mà không phá restart trong Spring Batch

Một batch job chạy đúng với 10.000 bản ghi chưa chắc xử lý hiệu quả khi dữ liệu tăng lên hàng triệu bản ghi. Các biện pháp tăng tốc thường gặp là tăng chunk size, đọc theo trang lớn hơn, ghi theo lô, thêm thread hoặc chia partition. Nhưng nếu tối ưu chỉ dựa vào số bản ghi/giây, ta có thể vô tình làm mất **khả năng restart**: sau khi job lỗi, dữ liệu bị bỏ sót, ghi trùng hoặc toàn bộ input bị đọc lại từ đầu.

Trong **Spring Batch Core Processing**, chủ đề **Performance – Tối ưu mà không phá restart** yêu cầu giải quyết đồng thời hai mục tiêu:

1. **Tăng hiệu năng:** giảm tổng thời gian chạy, số lần gọi database, thời gian chờ I/O, lượng bộ nhớ và chi phí transaction.
2. **Giữ khả năng khôi phục:** khi job thất bại hoặc bị dừng, chạy lại đúng `JobInstance` phải tiếp tục từ trạng thái đã lưu, không làm hỏng dữ liệu đã commit và không bỏ qua phần chưa xử lý.

Định hướng quan trọng: *tối ưu một bước chỉ được coi là thành công nếu đường chạy bình thường **và** đường chạy sau lỗi đều cho kết quả nghiệp vụ đúng*. Việc job hoàn tất nhanh hơn không đủ để chứng minh bản tối ưu an toàn.

## 1. Hiểu đúng cơ chế restart trước khi tối ưu

Spring Batch quản lý trạng thái qua `JobRepository`. Những thực thể cần phân biệt:

| Thành phần | Chức năng | Quan hệ với restart |
| --- | --- | --- |
| `JobInstance` | Một công việc logic được định danh bởi tên job + identifying `JobParameters` | Restart phải thuộc cùng instance, không tạo instance khác ngoài ý muốn |
| `JobExecution` | Một lần thử chạy của instance | Lần đầu thất bại và lần restart có execution khác nhau |
| `StepExecution` | Một lần thực thi step, chứa status, counters và context | Step thất bại có thể có execution mới khi job restart |
| `ExecutionContext` | Map trạng thái được framework persist vào repository | Reader/writer có thể lưu vị trí để khôi phục |
| `ItemStream` | Hợp đồng `open`, `update`, `close` | `open` khôi phục, `update` chuẩn bị checkpoint, `close` giải phóng tài nguyên |
| Transaction của chunk | Giới hạn commit/rollback của một nhóm item | Quyết định phần công việc nào đã commit trước lỗi |

Ví dụ chunk size là 200:

```text
Đọc/ghi 1..200       → commit #1; checkpoint sau item 200
Đọc/ghi 201..400     → commit #2; checkpoint sau item 400
Đọc/ghi 401..600     → lỗi trước commit #3
                                      |
                                      v
                         rollback phần chưa commit
                                      |
                                      v
Restart: mở reader bằng checkpoint bền vững sau item 400
         (trong trường hợp reader hỗ trợ lưu/khôi phục đúng)
```

Phần 401..600 có thể đã được đọc và processor đã chạy, nhưng nếu transaction chưa commit thì không thể coi là hoàn tất. Tại lần restart, các item này có thể được đọc lại. Điều đó bình thường đối với xử lý có checkpoint; những side effect ngoài transaction phải có idempotency hoặc cơ chế đối soát riêng.

**Không lấy `readCount`, `writeCount` hoặc dòng log cuối làm vị trí restart mặc định.** Giá trị khôi phục do implementation của reader/writer lưu qua `ExecutionContext` quyết định. Một số reader không có state, hoặc dùng key/last sort key khác với chỉ số item.

### JobParameters là một phần của hợp đồng phục hồi

Với batch xử lý theo ngày nghiệp vụ:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "file-v12")
    .toJobParameters();
```

Hai giá trị trên mặc định là *identifying*. Nếu cùng tên job và tham số identifying, Spring Batch xác định cùng `JobInstance`. Khi execution trước `FAILED`/`STOPPED` và cấu hình cho phép, Spring Batch có thể restart instance đó bằng metadata đã lưu.

Ngược lại:

```java
JobParameters differentInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "file-v12")
    .addString("attemptId", UUID.randomUUID().toString())
    .toJobParameters();
```

Thêm `attemptId` identifying mới tạo một **JobInstance khác**. Đây có thể là chủ đích của nghiệp vụ chạy lại từ đầu, nhưng **không phải restart từ checkpoint**. Không dùng `RunIdIncrementer` hoặc UUID chỉ để vượt qua `JobInstanceAlreadyCompleteException` rồi nghĩ rằng Batch sẽ tiếp tục phần còn lại.

## 2. Đo hiệu năng và định nghĩa điều kiện đúng

Trước khi tối ưu, phải biết thời gian đang mất ở đâu. Một batch chậm do SQL thiếu index không được cải thiện đáng kể chỉ bằng tăng thread; một batch chậm vì commit quá thường xuyên lại có thể cải thiện khi thay chunk size.

Các số liệu nên thu thập theo **job execution, step và kỳ dữ liệu**:

| Nhóm đo | Chỉ số | Diễn giải |
| --- | --- | --- |
| Hiệu năng tổng | Duration, records/second, throughput đầu ra | Tốc độ xử lý thực tế |
| Chunk/transaction | `commitCount`, `rollbackCount`, thời gian một chunk, số item/chunk | Chi phí commit và rủi ro làm lại khi lỗi |
| Reader | Query latency, số query, DB fetch, file read time | Điểm nghẽn đọc dữ liệu |
| Processor | CPU, allocation, GC pause, thời gian xử lý mỗi item | Chi phí tính toán |
| Writer | Rows per batch, số round-trip, lock wait, flush time | Chi phí ghi và transaction |
| Hạ tầng | CPU, heap, connection pool, disk I/O, network | Giới hạn tài nguyên |
| Khôi phục | Thời gian restart, số item cần xử lý lại, dữ liệu trùng/thiếu | Giá của lỗi sau khi tối ưu |

`StepExecution.getReadCount()` và `getWriteCount()` là các bộ đếm của **từng execution**, không nhất thiết là tổng số bản ghi nghiệp vụ duy nhất qua mọi lần restart. Khi đối soát sau restart, ưu tiên khóa nghiệp vụ và output đã commit.

Ví dụ so sánh bản gốc và bản tối ưu trên **cùng một tập đầu vào**:

| Chỉ số | Bản gốc (ví dụ) | Bản tối ưu (ví dụ) |
| --- | ---: | ---: |
| Input | 1.000.000 | 1.000.000 |
| Chunk size | 50 | 500 |
| Số lần commit xấp xỉ khi xử lý hết dữ liệu | 20.000 | 2.000 |
| Thời gian chạy | 28 phút | 13 phút |
| Số output hợp lệ cuối cùng | 999.200 | 999.200 |
| Kết quả sau lỗi giữa chừng và restart | Đúng, không trùng | Phải kiểm chứng bằng thử nghiệm |

Đây là **số giả định để minh họa phép so sánh**, không phải benchmark hay bảo đảm của Spring Batch. Tổng số commit thực tế còn phụ thuộc step, transaction, kết thúc luồng, retry và skip. Mục tiêu là vừa giảm thời gian vừa giữ kết quả cuối đúng sau khi chủ động gây lỗi.

## 3. Tối ưu chunk size mà vẫn giữ checkpoint

Chunk-oriented step đọc, xử lý, ghi theo một nhóm item rồi commit transaction. Cấu hình Spring Batch 5.x:

```java
@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<OrderRow> reader,
                      ItemProcessor<OrderRow, OrderResult> processor,
                      ItemWriter<OrderResult> writer) {
    return new StepBuilder("importOrdersStep", repository)
        .<OrderRow, OrderResult>chunk(250, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

`OrderRow` và `OrderResult` là kiểu ứng dụng minh họa, không thuộc Spring Batch. `chunk(250, transactionManager)` đặt commit interval 250 item theo mô hình chunk thông dụng.

### Chunk quá nhỏ

- Nhiều transaction và commit, nhiều metadata/checkpoint update.
- Tăng round-trip đến database nếu writer không gom đủ item.
- Có thể phù hợp khi item tốn nhiều bộ nhớ, transaction dài hoặc yêu cầu rollback ngắn.

### Chunk quá lớn

- Một transaction sống lâu, dễ tăng lock wait, áp lực undo/WAL và bộ nhớ.
- Khi lỗi cuối chunk, nhiều công việc chưa commit có thể phải làm lại.
- Một số writer giữ nhiều item hoặc buffer, khiến memory tăng và GC chậm.
- Giảm khả năng quan sát điểm tiến độ đã commit nếu một chunk mất quá lâu.

### Cách điều chỉnh an toàn

1. Đo một baseline có đầu vào cố định và output được đối soát.
2. Thử các kích thước như 100, 250, 500 trên dữ liệu đại diện thay vì mặc định “càng lớn càng nhanh”.
3. So sánh throughput, transaction duration, memory, lock wait và số lần rollback.
4. Gây lỗi sau một số chunk đã commit; restart **cùng instance** và xác nhận không mất/trùng dữ liệu.
5. Chỉ chọn giá trị mới khi cả hiệu năng lẫn kết quả khôi phục đáp ứng yêu cầu.

Thay chunk size có thể làm thay đổi ranh giới commit của các lần chạy **mới**. Với một lần restart đang dở, thay đồng thời chunk size, code reader và schema context làm việc diễn giải checkpoint phức tạp hơn; cần kiểm thử upgrade/restart trên metadata giống thực tế trước khi triển khai. Hãy tránh đổi nhiều yếu tố một lúc nếu muốn tìm đúng nguyên nhân khi có sai khác.

## 4. Tối ưu reader mà không bỏ qua hoặc đọc trùng bản ghi

Reader thường là phần khó nhất của restart vì phải nối “đã đọc tới đâu” với “tập dữ liệu có còn như trước không”. Cùng một checkpoint chỉ an toàn khi cách xác định thứ tự và danh tính item được giữ ổn định.

### 4.1. Paging cần sort key ổn định

Khi dùng `JdbcPagingItemReader`, **sort key phải ổn định và đủ phân biệt các bản ghi**. Sắp xếp chỉ theo trường không duy nhất như `created_at` có thể khiến các bản ghi cùng timestamp bị dịch vị trí khi phân trang hoặc restart.

```sql
-- Không có thứ tự xác định cho các row cùng created_at:
SELECT id, created_at, amount
FROM orders_source
WHERE business_date = :businessDate
ORDER BY created_at;

-- Khóa id duy nhất tạo thứ tự xác định:
SELECT id, created_at, amount
FROM orders_source
WHERE business_date = :businessDate
ORDER BY id;
```

Với dữ liệu lớn, cần index phù hợp với bộ lọc và sort key, ví dụ `(business_date, id)` trên bảng nguồn tùy database/query plan. `JdbcPagingItemReader` có cơ chế dùng giá trị sort key cuối để hỗ trợ restart; điều đó **không cho phép nguồn dữ liệu thay đổi tùy ý**. Nếu hàng mới được chèn, hàng cũ bị xóa hoặc khóa sort thay đổi, cần có hợp đồng dữ liệu rõ ràng về việc item mới có nằm trong kỳ xử lý hay không.

### 4.2. Ví dụ cấu hình paging reader hỗ trợ restart

Ví dụ Spring Batch 5.x, database PostgreSQL, bảng đầu vào `orders_source(id BIGINT PRIMARY KEY, business_date VARCHAR(10), amount NUMERIC)`:

```java
import java.math.BigDecimal;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(long id, BigDecimal amount) {}

@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("ordersReader")
        .dataSource(dataSource)
        .selectClause("SELECT id, amount")
        .fromClause("FROM orders_source")
        .whereClause("WHERE business_date = :businessDate")
        .parameterValues(Map.of("businessDate", businessDate))
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper((rs, rowNum) -> new OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")))
        .pageSize(250)
        .fetchSize(250)
        .saveState(true)
        .build();
}
```

`@StepScope` tạo reader cho từng step execution, tránh dùng lại con trỏ của lần chạy trước ở một singleton. `name("ordersReader")` giúp quản lý key trạng thái; khi nhiều reader chia cùng execution context, chúng cần tên riêng để không ghi đè state của nhau. `saveState(true)` cho phép reader tham gia checkpoint; không tự tắt nó chỉ vì thấy nhiều lần update metadata.

`pageSize(250)` xác định kích thước page reader, còn `fetchSize(250)` chỉ là hint cho JDBC driver về số row fetch. Giá trị thực tế phụ thuộc driver và database. `pageSize` và `chunk size` không cần bằng nhau, nhưng việc chọn chúng cùng nhau nên được đo bằng dữ liệu đại diện.

Ví dụ trên giả định **input là một snapshot nghiệp vụ ổn định** trong quá trình job và restart. Một cách giữ ổn định là truyền `sourceVersion`/`snapshotId` trong `JobParameters` rồi chỉ đọc đúng phiên bản đó. Nếu source có trạng thái động, cân nhắc staging/snapshot hoặc giới hạn bằng watermark đã chốt, thay vì liên tục gọi `now()` trong reader.

### 4.3. Cursor reader và fetch size

`JdbcCursorItemReader` có thể stream result set thay vì thực hiện các truy vấn paging. Điều chỉnh `fetchSize`, index và SQL có thể giảm I/O đáng kể. Tuy nhiên, cursor có thể giữ database connection trong thời gian dài; hành vi fetch phụ thuộc driver/transaction. Sau restart, reader cần mở lại truy vấn và dùng trạng thái đã lưu để đến vị trí phù hợp; nguồn dữ liệu thay đổi giữa hai lần chạy vẫn là rủi ro.

Không coi `fetchSize` là số item được commit hay một cơ chế checkpoint. Đây là cấu hình truy xuất của JDBC, tách biệt với `chunk()` và `ExecutionContext`.

### 4.4. Tránh offset trên tập dữ liệu biến động

Ví dụ API phân trang `?page=5&size=100` hoặc SQL `OFFSET 500` rất dễ gặp vấn đề khi phần tử ở các trang đầu bị chèn/xóa trong lúc job chạy. Nếu hệ thống nguồn có API cursor/token hoặc một khóa tăng dần và snapshot ổn định, hãy dùng chúng. Khi tự xây dựng `ItemStreamReader`, lưu token/last committed key **sau các mốc checkpoint phù hợp**, chứ không chỉ ghi log khóa cuối đã nhìn thấy.

## 5. Tối ưu writer: batch write và idempotency

Ghi từng item bằng một truy vấn JDBC có thể làm tăng số round-trip. Với cùng transaction, `JdbcBatchItemWriter` gom câu lệnh theo chunk và thường giảm chi phí gọi database. Nhưng ghi nhanh hơn không đủ; writer phải có hành vi rõ ràng khi một item được thử lại.

### 5.1. Ví dụ JDBC batch writer với upsert có khóa nghiệp vụ

Giả sử bảng đích PostgreSQL:

```sql
CREATE TABLE order_result (
    order_id BIGINT PRIMARY KEY,
    amount NUMERIC NOT NULL
);
```

Writer mẫu:

```java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

record OrderResult(long orderId, BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<OrderResult> resultWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderResult>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO order_result(order_id, amount)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET amount = EXCLUDED.amount
            """)
        .itemPreparedStatementSetter((item, statement) -> {
            statement.setLong(1, item.orderId());
            statement.setBigDecimal(2, item.amount());
        })
        .build();
}
```

`ON CONFLICT` là **cú pháp PostgreSQL**, không phải SQL chuẩn tương thích mọi database. Với Oracle, MySQL hoặc SQL Server, cần áp dụng cơ chế merge/upsert phù hợp và đánh giá lock, index cùng concurrency. Unique key trên `order_id` định nghĩa bản ghi nghiệp vụ duy nhất. Khi cùng item được xử lý lại, writer không nhân đôi dòng output.

**Upsert không tự giải quyết mọi bài toán.** Nếu kết quả tính toán phụ thuộc thời gian hoặc dữ liệu nguồn đã thay đổi, ghi lại cùng khóa với một `amount` khác vẫn có thể sai. Processor nên có hành vi xác định với cùng input/version, hoặc output cần gắn `sourceVersion` và chính sách cập nhật rõ ràng. Nếu nghiệp vụ yêu cầu giữ lịch sử mỗi lần tính, hãy dùng versioned key và cơ chế công nhận phiên bản kết quả.

### 5.2. Những bẫy khi tối ưu writer

| Thay đổi | Hiệu quả kỳ vọng | Rủi ro restart cần xử lý |
| --- | --- | --- |
| Dùng JDBC batch thay insert từng item | Ít round-trip | Kiểm tra lỗi giữa batch, transaction và tính idempotent |
| Gộp nhiều item vào một file lớn | Giảm thao tác mở/đóng | Khôi phục vị trí file, tránh ghi nối sai khi restart |
| Ghi trực tiếp ra API ngoài | Có thể giảm bước trung gian | API không tự rollback cùng DB, cần idempotency key |
| Ghi async phía sau writer | Che latency mạng | Step có thể commit trước khi output thật hoàn tất nếu không đợi/điều phối |
| Bulk insert/loader riêng | Throughput cao | Cần checkpoint/correlation giữa batch và quá trình bulk load |
| Bỏ ràng buộc unique để ghi nhanh | Giảm một số chi phí kiểm tra | Dễ mất khả năng chống trùng khi retry/restart |

Với `JpaItemWriter`, batching/flush và việc giữ persistence context ảnh hưởng memory. Nếu thay đổi cấu hình flush/clear để tăng throughput, cần đảm bảo transaction đúng và entity không được giữ lại sai qua các chunk; không để buffer của ORM tăng không giới hạn cho cả job.

## 6. Tối ưu file output mà vẫn phục hồi đúng

`FlatFileItemWriter` và các writer file có thể lưu state trong `ExecutionContext` để hỗ trợ restart. Khi tối ưu buffer hoặc thay cơ chế ghi file, cần hiểu các lựa chọn như `saveState`, append, xóa file cũ và việc writer nhận biết đã restart.

```text
Lần đầu:
  input.csv → processing → result.csv (mới)
  chunk #1/#2 commit; writer lưu trạng thái hợp lệ
  chunk #3 lỗi

Restart cùng JobInstance:
  reader đọc từ checkpoint đã lưu
  writer mở lại đúng result.csv và khôi phục trạng thái

Rerun là JobInstance mới:
  phải có chính sách output mới, thay thế có kiểm soát,
  hoặc đánh dấu version để không ghi đè kết quả đã công bố
```

Không bật `appendAllowed(true)` chỉ vì muốn giảm thời gian khởi tạo file: nếu một job instance mới ghi nối vào file của lần trước, dữ liệu có thể trùng mà status vẫn `COMPLETED`. Ngược lại, xóa file đích ở đầu **mọi** lần chạy có thể phá nội dung đã commit của execution trước khi restart.

Một quy trình an toàn cho file kết quả quan trọng là ghi vào đường dẫn tạm theo **business key + execution/version**, hoàn tất kiểm tra và chỉ publish/chuyển tên đến đường dẫn chính thức sau khi có kết quả hợp lệ. Nếu cần restart trực tiếp file tạm đang ghi, tên và trạng thái tệp tạm phải được giữ ổn định cho cùng job instance. Khi đối tượng nằm trên object storage hoặc filesystem khác, chuyển tên có thể không phải thao tác atomic; cần manifest và quy tắc publish phù hợp.

Kiểm thử cả lỗi giữa chunk, file đã tồn tại, writer flush/close và restart trên cùng file. `BatchStatus.COMPLETED` không đủ chứng minh file không có dòng trùng hay phần cuối bị cắt.

## 7. Đừng tắt `saveState` để đổi lấy tốc độ

Một cách “tối ưu” nguy hiểm là sửa `.saveState(false)` cho reader/writer rồi bỏ qua việc persist `ExecutionContext`. Điều này có thể giảm chút chi phí metadata nhưng cũng có thể khiến reader đọc từ đầu khi step khởi động lại.

```java
// Nếu reader cần khôi phục vị trí:
reader.setSaveState(true);

// Chỉ chọn false khi có hợp đồng xử lý lại từ đầu hoặc phân vùng hoàn toàn
// không cần vị trí trước đó và kết quả cuối vẫn được bảo vệ.
```

Không phải mọi processor hoặc reader đều cần giữ state: processor thuần hàm thường không lưu `ExecutionContext`; một reader tạo ra một tập item nhỏ bất biến và toàn step có thể chạy lại an toàn có thể không cần checkpoint riêng. Nhưng việc quyết định stateless **phải xuất phát từ mô hình restart**, không phải cách “xóa bớt overhead” không có số đo.

### Thực thi đúng vòng đời `ItemStream`

Với một reader tự xây dựng:

```java
public final class KeysetOrderReader implements ItemStreamReader<OrderRow> {
    private static final String LAST_KEY = "orders.reader.lastCommittedId";
    private Long nextAfterId;

    @Override
    public void open(ExecutionContext context) {
        nextAfterId = context.containsKey(LAST_KEY)
            ? context.getLong(LAST_KEY)
            : null;
        // Chuẩn bị câu query: id > nextAfterId, ORDER BY id.
    }

    @Override
    public OrderRow read() {
        // Đọc row tiếp theo theo thứ tự id; trả null khi hết.
        // Trong triển khai thật, gọi JDBC/resource ở đây.
        throw new UnsupportedOperationException("Illustrative skeleton");
    }

    @Override
    public void update(ExecutionContext context) {
        if (nextAfterId != null) {
            context.putLong(LAST_KEY, nextAfterId);
        }
    }

    @Override
    public void close() {
        // Đóng ResultSet/Statement/Connection do reader sở hữu, nếu có.
    }
}
```

Đây là **khung ý tưởng**, không phải reader sẵn sàng triển khai: phương thức `read()` cố ý chưa được viết, và trong triển khai thật `nextAfterId` phải chỉ cập nhật theo các item đã được reader bàn giao theo đúng hợp đồng checkpoint của framework. Hơn nữa, lưu last key trước commit chỉ là *checkpoint candidate*; framework persist nó tại mốc transaction thích hợp. Với paging/cursor chuẩn, nên ưu tiên implementation Spring Batch đã được kiểm chứng thay vì tự xây một reader chỉ vì muốn giảm vài lời gọi SQL.

Nếu bọc một `ItemStreamReader` bên trong delegate mà Spring Batch không nhìn thấy, phải đảm bảo wrapper ủy quyền `open/update/close` hoặc đăng ký stream đúng cách với step. Nếu bỏ sót, job vẫn có thể đọc/ghi bình thường nhưng không lưu checkpoint để restart.

## 8. Parallelism: tăng throughput nhưng phải chia ranh giới restart

Tăng concurrency là thay đổi có ảnh hưởng lớn đến trật tự xử lý. Khi một chunk step chạy đa luồng, item không nhất thiết được đọc, xử lý, ghi và commit theo cùng thứ tự tuyến tính như chạy tuần tự. Một reader stateful dùng chung có thể không thread-safe; chỉ đặt `TaskExecutor` rồi giữ nguyên reader không bảo đảm dữ liệu đúng hoặc restart được.

### 8.1. Multi-threaded step

Spring Batch có thể sử dụng task executor để thực hiện chunk trên nhiều thread (API cụ thể phụ thuộc major version). Tốc độ có thể tăng khi step chờ I/O hoặc processor có thể xử lý song song. Nhưng cần xem xét:

- Reader có an toàn khi nhiều thread gọi đồng thời không?
- `ExecutionContext` thể hiện một offset đơn có còn đủ khi các chunk hoàn tất ngoài thứ tự không?
- Writer có chia sẻ buffer, file handle hoặc transaction state giữa các thread không?
- Nếu một chunk phía sau commit trước chunk phía trước rồi process chết, restart có thể đọc lại/thiếu item nào?

`SynchronizedItemStreamReader` có thể đồng bộ truy cập reader để tránh một số race khi đọc, nhưng **không tạo bảo đảm restart an toàn cho một multi-threaded step**; các chunk vẫn có thể xử lý/commit ngoài thứ tự. Đặc biệt với reader có trạng thái, việc đồng bộ hóa method `read()` không biến toàn bộ transaction của các thread thành một chuỗi tuần tự.

### 8.2. Partitioning với các phạm vi dữ liệu không giao nhau

Đối với batch lớn và cần restart có thể kiểm soát, partitioning thường dễ thiết kế hơn vì mỗi worker xử lý một phạm vi độc lập và có `StepExecution`/context riêng:

```text
masterStep
   |
   +-- partition-00: order_id 1..100000
   |      reader riêng + writer riêng + checkpoint riêng
   |
   +-- partition-01: order_id 100001..200000
   |      reader riêng + writer riêng + checkpoint riêng
   |
   +-- partition-02: order_id 200001..300000
          reader riêng + writer riêng + checkpoint riêng
```

Một `Partitioner` có thể tạo `ExecutionContext` cho từng khoảng:

```java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxId", 100_000L);
partitions.put("range-000", first);

ExecutionContext second = new ExecutionContext();
second.putLong("minId", 100_001L);
second.putLong("maxId", 200_000L);
partitions.put("range-001", second);
```

Đoạn này minh họa dữ liệu được trả từ `Partitioner.partition(int gridSize)`; `Map`, `LinkedHashMap`, `ExecutionContext` cần import tương ứng. Trong worker step, reader nhận `minId`/`maxId` qua `@StepScope`, ví dụ `@Value("#{stepExecutionContext['minId']}")`, rồi giới hạn truy vấn. Các phạm vi phải **không chồng lấp và bao phủ đủ input**. Mỗi partition có tên/identity ổn định để có thể nhận diện và restart.

Nếu partitioner tính lại ranh giới khác ở mỗi lần chạy (do dữ liệu mới thêm hoặc thay `gridSize`), partition có thể đổi tên hoặc đổi phạm vi. Trong kịch bản restart, cần giữ kế hoạch partition đã chốt, hoặc cung cấp một mô hình tái tạo phạm vi deterministic dựa trên snapshot/version của input. Không tăng số partition giữa lần chạy lỗi và lần restart khi chưa xác minh tác động lên metadata và dữ liệu đã xử lý.

### 8.3. Remote chunking và xử lý bất đồng bộ

Remote chunking phân phối công việc tới worker qua messaging. Việc retry và redelivery có thể làm một chunk được xử lý lại; cần định danh message/chunk, xử lý idempotent và xác định lúc nào manager coi kết quả đã commit. Nếu worker gọi API hoặc ghi output ngoài transaction chung, cần cơ chế đối soát. Chọn remote chunking khi chi phí vận hành được bù bằng yêu cầu mở rộng thực tế, không chỉ vì job hiện tại “có vẻ chậm”.

## 9. Tối ưu processor và bộ nhớ mà ít ảnh hưởng checkpoint

Processor thuần hàm thường là nơi tối ưu ít đụng tới metadata nhất:

- Tránh parse cùng một cấu hình hoặc regex ở mỗi item nếu có thể chuẩn bị một lần.
- Hạn chế tạo object trung gian không cần thiết, nhưng không dùng mutable shared cache thiếu thread safety.
- Cache dữ liệu tham chiếu nhỏ, có version rõ ràng trong kỳ xử lý.
- Gom lookup bằng cách chuẩn bị reference data theo batch, nếu không làm thay đổi kết quả nghiệp vụ.
- Với CPU nặng, đo profile trước khi thêm thread; tăng thread vượt số core có thể chỉ tăng contention/GC.

Tuy vậy, thay đổi logic processor có thể phá **tính xác định** của restart. Ví dụ, lần đầu processor quy đổi tỷ giá theo bảng ngày 16/11, nhưng lần restart hôm sau lại truy cập “tỷ giá mới nhất”; cùng input sẽ sinh output khác. Giải pháp là chốt `rateVersion`/`rulesetVersion` trong identifying parameters hoặc snapshot nguồn, rồi dùng nhất quán cho mọi execution của một instance.

Trong pipeline có nhiều step, state được chia sẻ qua `JobExecutionContext`/`StepExecutionContext` phải nhỏ và có ngữ nghĩa ổn định. Không dùng `ExecutionContext` làm cache hàng triệu row: kích thước serialized metadata sẽ tăng, cập nhật checkpoint chậm và restart tốn thời gian deserialization.

## 10. Bảo đảm source input ổn định khi restart

Một tối ưu có thể hợp lý về performance nhưng nguy hiểm khi source đang thay đổi. Hãy xác định **dataset contract** trước khi đọc:

| Nguồn | Điểm dễ biến động | Giải pháp thường dùng |
| --- | --- | --- |
| File CSV trên thư mục chung | File bị thay thế cùng tên | Đưa vào staging bất biến, ghi checksum/object version |
| Bảng giao dịch đang cập nhật | Insert/delete/update làm đổi tập kết quả | Đọc snapshot, chốt watermark hoặc xử lý theo trạng thái cố định |
| API phân trang | Mỗi lần gọi trả dữ liệu khác, offset trượt | Dùng cursor token ổn định/snapshot API hoặc staging |
| Dữ liệu tham chiếu | Tỷ giá/quy tắc được chỉnh trong lúc chạy | Chốt phiên bản dữ liệu/ruleset cho job instance |
| Queue/message | Redelivery sau failure, không có transaction chung | Idempotency key và ghi nhận message đã xử lý |

Trong database, `ORDER BY id` với khóa duy nhất tạo thứ tự xác định **ở một snapshot nhất định**, nhưng không tự bảo đảm tính bất biến của tập dữ liệu. Nếu nguồn còn nhận insert có id lớn hơn, reader có thể đọc thêm ngoài phạm vi kỳ gốc. Một `maxId` được chốt lúc tạo job, cùng `businessDate` và `sourceVersion`, có thể giới hạn dataset trong một số bài toán. Tuy nhiên cập nhật/xóa các bản ghi dưới `maxId` vẫn cần policy khác, ví dụ snapshot hoặc bảng staging.

## 11. Test có gây lỗi là điều kiện của tối ưu an toàn

Integration test chỉ chạy đến `COMPLETED` không phát hiện nhiều lỗi checkpoint. Sau mỗi thay đổi đáng kể về chunk, paging, writer hoặc concurrency, cần một kịch bản **fail rồi restart** với output đã commit kiểm chứng được.

### 11.1. Kịch bản minh họa

Đầu vào bất biến: `A001, A002, A003, A004, A005`. Chunk size 2.

```text
Lần #1:
  chunk 1 [A001,A002] -> COMMIT
  chunk 2 [A003,A004] -> gây lỗi writer, ROLLBACK
  JobExecution #100 = FAILED
  Output cuối lần #1 = A001,A002

Restart cùng identifying JobParameters:
  reader mở context đã lưu
  đọc/ghi phần còn lại
  JobExecution #101 = COMPLETED
  Output cuối = A001,A002,A003,A004,A005
```

Test cần xác nhận cả ba lớp:

1. **Framework:** execution đầu `FAILED`, execution sau `COMPLETED`, cả hai có cùng `JobInstance.id` nhưng `JobExecution.id` khác nhau.
2. **Checkpoint:** step được khôi phục từ state đã commit; nếu có log checkpoint, log khớp giá trị repository, không lấy log thay thế kết quả.
3. **Business output:** tập khóa đúng, không trùng, số lượng đúng và dữ liệu các bản ghi khớp input/ruleset.

### 11.2. Assertions Java sau khi chạy hai pha

Giả định `first`, `restarted`, `jdbcTemplate` đã được tạo trong một integration test Spring Batch 5.x sử dụng `JobLauncherTestUtils`/`JobLauncher` cùng metadata repository:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> codes = jdbcTemplate.queryForList(
    "SELECT order_code FROM order_result ORDER BY order_code",
    String.class
);
assertThat(codes)
    .containsExactly("A001", "A002", "A003", "A004", "A005");

Integer duplicateKeys = jdbcTemplate.queryForObject("""
    SELECT COUNT(*) FROM (
      SELECT order_code
      FROM order_result
      GROUP BY order_code
      HAVING COUNT(*) > 1
    ) t
    """, Integer.class);
assertThat(duplicateKeys).isZero();
```

Đây là **mẫu assertion**, không phải toàn bộ test runnable: bảng `order_result(order_code, ...)` và setup gây lỗi phải được dự án chuẩn bị. Nếu bảng đích đã có ràng buộc unique trên khóa, truy vấn phát hiện trùng luôn bằng 0 theo cấu trúc dữ liệu; vẫn phải kiểm tra output count, payload và các side effect bên ngoài để chứng minh kết quả thực.

### 11.3. Test với nhiều kích thước chunk

Có thể chạy cùng một fixture ở các chunk size 1, 10, 250 rồi cố ý tạo lỗi trước và sau một checkpoint. Kết quả cuối phải giống nhau về nghiệp vụ, dù số `commitCount`, read/write count của từng execution hoặc lượng công việc phải làm lại khác nhau. Test riêng trường hợp restart với metadata từ phiên bản đã triển khai trước khi đổi cấu hình/reader key.

### 11.4. Test nhiều partition

Gây lỗi chỉ ở một partition sau khi các partition khác đã `COMPLETED`. Khi restart, kiểm tra phần đã hoàn tất không bị xử lý lại ngoài chính sách mong muốn, partition lỗi tiếp tục đúng phạm vi và output toàn job không bị trùng. Trường hợp lỗi trong lúc thay số worker/grid size cũng cần quy tắc partition stable trước khi coi việc tăng parallelism là an toàn.

## 12. Quan sát restart cost và tính đúng trong production

Ngoài thời gian chạy bình thường, nên theo dõi:

- `jobName`, `businessDate`, `jobInstanceId`, `jobExecutionId`, `stepExecutionId` để nối các lần chạy liên quan.
- Read/write/filter/skip/commit/rollback counts theo từng step execution.
- Thời gian của chunk hoặc nhóm chunk, tốc độ input và output.
- Id/version nguồn đang xử lý, checkpoint đã persist tại các mốc quan trọng, số item đọc lại sau failure nếu xác định được.
- Số lần duplicate/upsert conflict, số retry, độ trễ backend và số bản ghi đã được hệ thống đích xác nhận.
- Thời gian phục hồi từ khi phát hiện `FAILED` tới lúc output của kỳ dữ liệu được công nhận hoàn tất.

Không log toàn bộ `ExecutionContext`: nó có thể chứa thông tin nhạy cảm và trạng thái lớn. Chỉ ghi những field đã chọn và không dùng log để quyết định restart; metadata bền vững trong `JobRepository` và dữ liệu nghiệp vụ đã commit mới là cơ sở điều tra.

Ví dụ log có cấu trúc:

```text
event=batch.chunk.completed
jobName=importOrdersJob
businessDate=2026-11-16
jobExecutionId=512
stepExecutionId=841
partition=orders-range-00
readCount=100000
writeCount=99900
commitCount=400
checkpoint=lastId:100000
```

Khi log checkpoint, chỉ sử dụng tên/giá trị có hợp đồng rõ ràng của reader ứng dụng. Một giá trị `lastId` quan sát được trong bộ nhớ ngay lúc đọc chưa chắc đã là giá trị persisted sau commit. Trong chunk processing, listener sau commit có thể ghi tín hiệu tiến độ đáng tin hơn; để đối chiếu cuối cùng vẫn phải đọc repository/output.

## 13. Các thay đổi dễ phá restart

| Thay đổi tưởng như tối ưu | Tại sao nguy hiểm | Hướng an toàn |
| --- | --- | --- |
| Tắt `saveState` vì metadata update tốn thời gian | Reader mất offset được lưu | Chỉ tắt nếu step được thiết kế lại từ đầu có idempotency rõ ràng |
| Tăng chunk size lên rất lớn | Transaction/lock kéo dài; lỗi phải xử lý lại nhiều item hơn | Đo với dataset đại diện và fail/restart test |
| Thay sort key `id` thành cột không unique | Paging và restart có thể lệch/thứ tự không xác định | Dùng khóa sắp xếp ổn định và duy nhất |
| Đổi `reader.name` hoặc key context giữa hai execution | Reader không tìm thấy state cũ | Giữ hợp đồng checkpoint, có migration hoặc hoàn tất instance cũ trước khi nâng cấp |
| Dùng singleton reader stateful cho nhiều step/thread | Cursor bị chia sẻ và không thread-safe | Tạo reader per step bằng `@StepScope`, cô lập theo partition |
| Gắn `TaskExecutor` vào chunk step mà không xem reader state | Commit out-of-order, checkpoint mơ hồ | Thiết kế partition độc lập hoặc chứng minh an toàn bằng test lỗi |
| Chạy lại với UUID identifying mới | Tạo JobInstance mới và đọc lại input | Dùng identifying parameters theo kỳ, restart bằng metadata khi phù hợp |
| Append file output cũ | Có thể ghi trùng dữ liệu hoặc tiếp tục sai vị trí | Dùng writer có state, file path/version rõ ràng và test restart |
| Chuyển writer sang async fire-and-forget | Chunk commit trước khi tác vụ ghi thật hoàn tất | Đợi kết quả/ack hoặc dùng outbox/idempotent worker |
| Tăng số partition nhưng đổi range mỗi lần | Restart không tìm đúng partition đã hoàn tất | Giữ tên/range/snapshot ổn định |
| Cache reference data không gắn version | Restart có thể dùng dữ liệu khác lần đầu | Snapshot/version dataset và ruleset |
| Xóa bảng `BATCH_*` khi job lỗi | Mất metadata/ExecutionContext để phục hồi | Giữ repository và dùng chính sách restart chính thức |

## 14. Quy trình tối ưu từng bước có kiểm soát

Một cách làm thực tế cho job đang vận hành:

1. **Chốt hợp đồng đầu vào/đầu ra:** business key, source version, order/snapshot, output count/checksum và điều kiện `COMPLETED` có ý nghĩa nghiệp vụ.
2. **Đo hiện trạng:** dùng một dataset đại diện, ghi throughput, DB query/flush time, lock, memory và thời gian restart sau lỗi.
3. **Tối ưu ít rủi ro trước:** index, truy vấn SQL, batch writer, giảm thao tác lặp và chọn fetch size hợp lý; giữ nguyên ranh giới xử lý.
4. **Điều chỉnh chunk/page size:** thay từng tham số, đo tốc độ và độ dài transaction, kiểm tra rollback/restart.
5. **Xem xét parallelism khi cần:** ưu tiên phân vùng dữ liệu rõ ràng, reader/step state tách biệt, thứ tự ổn định và output idempotent.
6. **Chạy thử failure path:** gây lỗi giữa chunk, kill process/đứt kết nối trong môi trường thử nghiệm, restart đúng instance và so sánh đầu ra cuối.
7. **Triển khai có khả năng quan sát:** theo dõi throughput, duration, retry/skip, duplicate conflict và kỳ dữ liệu chưa hoàn tất; có phương án revert cấu hình khi lỗi.

Không dùng một benchmark chỉ đo “khởi chạy job từ đầu tới `COMPLETED`” để kết luận tối ưu an toàn. Cần thực sự kiểm tra trường hợp bước xử lý bị gián đoạn và tiếp tục cùng metadata đã lưu. Nếu có thay đổi schema `ExecutionContext` hoặc cách xác định partition, phải kiểm tra riêng khả năng restart các instance còn dở từ phiên bản cũ.

## 15. Phiên bản Spring Batch và API

Các đoạn code về `StepBuilder(...).chunk(size, transactionManager)`, `JdbcPagingItemReaderBuilder` và `JdbcBatchItemWriterBuilder` trong bài dùng cú pháp **Spring Batch 5.x**. Spring Batch 6 có những thay đổi package/API ở các kiểu core. Khi nâng major version, hãy kiểm tra tài liệu và import đúng version, nhất là với các hệ thống còn `JobExecution` chưa hoàn tất. **Khả năng nâng cấp framework và khả năng restart dữ liệu đang dở là hai bài toán liên quan**, cần thử trên bản sao metadata/schema và dữ liệu an toàn trước khi nâng cấp production.

Các khái niệm cốt lõi vẫn giữ nguyên: `JobInstance` định danh theo parameters, `ExecutionContext` lưu trạng thái, `ItemStream` hỗ trợ checkpoint, transaction quyết định phần được commit và writer phải chịu được dữ liệu được xử lý lại trong phạm vi đã thiết kế.

## Kết luận

Tối ưu Spring Batch bền vững không chỉ là tăng chunk size hay số thread. Nó là tối ưu **trên ranh giới transaction và checkpoint có thể giải thích được**: reader nhận diện input nhất quán, writer đảm bảo tác động không bị nhân đôi, mỗi partition có trạng thái riêng và `JobRepository` còn đủ metadata để restart. Hãy đo hiệu năng trên đường chạy bình thường, rồi cố tình gây lỗi và phục hồi để chứng minh bản tối ưu vẫn bảo toàn dữ liệu.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): ranh giới chunk, commit và transaction.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext` và restart.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): cursor/paging reader và JDBC batch writer.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và remote chunking.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): định danh job instance, trạng thái và restart.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử step/job và kịch bản restart.
