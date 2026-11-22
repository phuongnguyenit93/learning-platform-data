# Batch update size trong Spring Batch: chọn kích thước batch để ghi dữ liệu hiệu quả

## 1. Batch update size là gì?

Trong hệ thống Spring Batch, việc cập nhật hàng chục nghìn hoặc hàng triệu bản ghi thường tốn nhiều thời gian hơn khi ứng dụng gửi **một câu lệnh SQL cho mỗi item**. JDBC batching cho phép gom nhiều bộ tham số của **cùng một câu SQL có cấu trúc giống nhau** để driver thực thi theo lô, giảm chi phí lặp lại của thao tác chuẩn bị câu lệnh và giao tiếp với cơ sở dữ liệu.

**Batch update size** thường chỉ số lượng câu lệnh cập nhật/ghi được gom vào **một lần gọi JDBC `executeBatch()`** hoặc một nhóm mà framework/driver xử lý cùng nhau.

Giả sử cần chuyển trạng thái của 100.000 đơn hàng từ `NEW` thành `READY`. Khi ghi tuần tự:

```text
UPDATE orders SET status = 'READY' WHERE id = 1;
UPDATE orders SET status = 'READY' WHERE id = 2;
UPDATE orders SET status = 'READY' WHERE id = 3;
...
UPDATE orders SET status = 'READY' WHERE id = 100000;
```

Ứng dụng có thể tạo 100.000 lần thực thi độc lập. Với JDBC batching, ứng dụng chuẩn bị một câu SQL có placeholder và truyền nhiều bộ tham số:

```sql
UPDATE orders
SET status = ?
WHERE id = ?
```

```text
JDBC PreparedStatement
  addBatch("READY", 1)
  addBatch("READY", 2)
  addBatch("READY", 3)
  ...
  addBatch("READY", 200)
  executeBatch()

Lặp lại cho những nhóm tiếp theo.
```

Nếu mỗi nhóm chứa 200 item, 100.000 item tạo khoảng **500 nhóm batch** ở tầng ứng dụng. Điều này không đồng nghĩa chính xác 500 network round-trip: cách driver và database đóng gói, gửi và thực thi batch phụ thuộc phiên bản, protocol và cấu hình. Muốn biết tốc độ thực cần benchmark.

Trong Spring Batch, chủ đề này nằm tại giao điểm của **chunk processing**, **JDBC/JPA writer** và **transaction management**. Không nên chỉ tăng một tham số và giả định hiệu năng sẽ luôn tốt hơn.

## 2. Phân biệt ba kích thước rất dễ bị nhầm

Trong tài liệu hoặc cấu hình dự án, “batch size” có thể chỉ ba khái niệm khác nhau:

| Khái niệm | Cấu hình/ví dụ | Quyết định điều gì? |
|---|---|---|
| **Chunk size / commit interval** | `.chunk(500, transactionManager)` | Số item Spring Batch xử lý trong một chunk trước ranh giới commit thông thường |
| **JDBC batch update size** | `JdbcTemplate.batchUpdate(..., batchSize=100, ...)` | Số bộ tham số JDBC tối đa trong một nhóm batch do API này tạo |
| **Hibernate JDBC batch size** | `hibernate.jdbc.batch_size=50` | Số thao tác SQL tương thích Hibernate có thể gom khi flush persistence context |

Hai kích thước đầu **không phải cùng một tham số**. Ví dụ:

```text
Một chunk Spring Batch: 500 item
       |
       v
ItemWriter nhận Chunk(500)
       |
       +--> JDBC executeBatch: 100 item
       +--> JDBC executeBatch: 100 item
       +--> JDBC executeBatch: 100 item
       +--> JDBC executeBatch: 100 item
       +--> JDBC executeBatch: 100 item
       |
       v
Commit transaction của chunk
```

Trong cấu hình minh họa này, **5 nhóm JDBC batch** có thể nằm trong **cùng một transaction của một chunk**. Việc driver thực thi năm nhóm không tự tạo năm transaction khác nhau.

Nếu dùng `JdbcBatchItemWriter` chuẩn và writer nhận trực tiếp một chunk 500 item, writer sẽ gọi cơ chế batch update của Spring JDBC cho dữ liệu của chunk. API builder của `JdbcBatchItemWriter` không có một tùy chọn `batchSize` riêng tương tự overload chia nhóm của `JdbcTemplate`. Muốn giới hạn nhóm JDBC nhỏ hơn chunk, có thể dùng writer tùy biến hoặc chọn commit interval phù hợp.

### Ví dụ quan hệ giữa các size

| Chunk size | JDBC update size | Nhóm JDBC cho chunk đầy đủ | Transaction của chunk* |
|---:|---:|---:|---:|
| 100 | 100 | 1 | 1 |
| 500 | 100 | 5 | 1 |
| 1.000 | 200 | 5 | 1 |
| 1.000 | 1.000 | 1 | 1 |
| 10 | 100 | 1 nhóm tối đa 10 item | 1 |

\* Giả định step là chunk-oriented, dùng transaction manager đúng và writer tham gia transaction của step. Retry, rollback, filtering, skip hoặc số item còn lại có thể làm hành vi thực tế phức tạp hơn.

Từ đây, một câu hỏi quan trọng là: bạn muốn giảm **số transaction**, giảm **chi phí gửi SQL**, hay giảm **memory/lock**? Mỗi mục tiêu có thể dẫn tới một cấu hình size khác nhau.

## 3. Batch update trong luồng xử lý Spring Batch

Một step chunk-oriented điển hình:

```text
ItemReader
    |
    v
ItemProcessor       (có thể filter item bằng cách trả null)
    |
    v
[Chunk item được giữ lại]
    |
    v
ItemWriter          (batch UPDATE / INSERT / UPSERT)
    |
    v
Transaction commit
    |
    v
Checkpoint lưu tiến độ trong JobRepository
```

Ví dụ:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step updateOrderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderStatusChange> reader,
        ItemProcessor<OrderStatusChange, OrderStatusChange> processor,
        ItemWriter<OrderStatusChange> writer) {

    return new StepBuilder("updateOrderStep", jobRepository)
            .<OrderStatusChange, OrderStatusChange>chunk(
                    500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Đoạn trên dùng kiểu builder của **Spring Batch 5.x**, Java 17+. `OrderStatusChange` là DTO minh họa sẽ định nghĩa ở phần kế tiếp.

Ở đây, `chunk(500, transactionManager)` điều khiển commit interval. Nó **không phải** thiết lập JDBC batch size của mọi driver hoặc Hibernate. Nếu writer không có batching, vẫn có thể xảy ra 500 lời gọi update tuần tự bên trong transaction.

Ngoài ra, nếu `ItemProcessor` lọc bớt dữ liệu hoặc step có retry/skip, số item writer nhận có thể ít hơn 500. Vì vậy đừng giả định mỗi lời gọi `write` luôn có đúng bằng commit interval item.

## 4. Sử dụng `JdbcBatchItemWriter` cho các lệnh UPDATE

`JdbcBatchItemWriter<T>` là writer có sẵn của Spring Batch để thực hiện batch SQL dựa trên các item đầu vào. Nó phù hợp khi mọi item có thể được ghi bằng cùng một câu SQL và mỗi item cung cấp bộ tham số khác nhau.

### 4.1. DTO đầu vào

```java
public record OrderStatusChange(
        long id,
        String newStatus
) {
}
```

Ví dụ dữ liệu:

```text
OrderStatusChange(101, "READY")
OrderStatusChange(102, "READY")
OrderStatusChange(103, "CANCELLED")
```

### 4.2. Cấu hình writer

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<OrderStatusChange> orderUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<OrderStatusChange>()
            .dataSource(dataSource)
            .sql("""
                UPDATE orders
                   SET status = :newStatus
                 WHERE id = :id
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("newStatus", item.newStatus())
                            .addValue("id", item.id()))
            .assertUpdates(true)
            .build();
}
```

Writer nhận một `Chunk` và sử dụng cơ chế Spring JDBC để thực thi SQL với các tham số của item. `assertUpdates(true)` yêu cầu các UPDATE được kiểm tra kết quả, giúp phát hiện item không cập nhật bản ghi nào khi driver cung cấp số dòng ảnh hưởng tương ứng.

Trong nghiệp vụ có thể bỏ qua việc không tìm thấy bản ghi, cần xác định rõ chính sách thay vì bật assert một cách máy móc. Ví dụ, “cập nhật nếu tồn tại” có thể coi 0 dòng là chấp nhận được. Trái lại, nếu mỗi item **phải** trỏ đến một đơn hàng tồn tại, 0 dòng có thể là lỗi dữ liệu cần phát hiện.

**Lưu ý:** Số dòng ảnh hưởng do JDBC trả về có thể chứa `Statement.SUCCESS_NO_INFO`, tức driver báo thành công nhưng không biết chính xác số dòng của từng phần tử. Không nên viết kiểm thử giả định mọi driver đều cung cấp một số update count dương chính xác.

### 4.3. Cần hiểu điều gì về kích thước với writer này?

Với writer trên, kích thước nhóm item mà writer nhìn thấy thường bị giới hạn bởi **chunk size**. Ví dụ step có `chunk(500)` thì một lần `write` bình thường có tối đa 500 item sau khi filter. Các câu SQL dùng PreparedStatement được gom theo item trong chunk.

Nếu yêu cầu database chỉ nhận nhóm tối đa 100 item nhưng vẫn muốn commit theo chunk 500, có thể triển khai `ItemWriter` tùy biến sử dụng overload `JdbcTemplate.batchUpdate` với tham số `batchSize`.

## 5. Giới hạn JDBC batch size riêng bằng `JdbcTemplate`

Spring JDBC có overload:

```java
int[][] batchUpdate(
    String sql,
    Collection<T> batchArgs,
    int batchSize,
    ParameterizedPreparedStatementSetter<T> pss
)
```

Nó chia một collection lớn thành các nhóm batch nhỏ hơn. Ví dụ writer xử lý 500 item mỗi chunk nhưng gom tối đa 100 item vào một lần batch update:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

public final class SizedOrderUpdateWriter
        implements ItemWriter<OrderStatusChange> {

    private static final String UPDATE_SQL = """
            UPDATE orders
               SET status = ?
             WHERE id = ?
            """;

    private final JdbcTemplate jdbcTemplate;
    private final int jdbcBatchSize;

    public SizedOrderUpdateWriter(
            JdbcTemplate jdbcTemplate,
            int jdbcBatchSize) {

        if (jdbcBatchSize <= 0) {
            throw new IllegalArgumentException(
                    "jdbcBatchSize must be positive");
        }

        this.jdbcTemplate = jdbcTemplate;
        this.jdbcBatchSize = jdbcBatchSize;
    }

    @Override
    public void write(Chunk<? extends OrderStatusChange> chunk) {
        if (chunk.isEmpty()) {
            return;
        }

        List<OrderStatusChange> items =
                new ArrayList<>(chunk.getItems());

        jdbcTemplate.batchUpdate(
                UPDATE_SQL,
                items,
                jdbcBatchSize,
                (PreparedStatement statement,
                 OrderStatusChange item) -> {
                    statement.setString(1, item.newStatus());
                    statement.setLong(2, item.id());
                }
        );
    }
}
```

Khai báo bean:

```java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
ItemWriter<OrderStatusChange> sizedOrderUpdateWriter(
        JdbcTemplate jdbcTemplate) {

    return new SizedOrderUpdateWriter(
            jdbcTemplate,
            100 // JDBC batch update size
    );
}
```

Khi step sử dụng `chunk(500)`, một lượt gọi writer có 500 item có thể tạo năm nhóm tối đa 100 item. Khi JDBC writer dùng đúng datasource và transaction manager liên kết với transaction của step, các nhóm vẫn tham gia **transaction của chunk**, không tự commit từng nhóm.

**Điểm cần lưu ý trong ví dụ này:** Writer đang thực thi SQL và để Spring JDBC ném exception nếu batch gặp lỗi. Nó chưa xử lý chính sách update count = 0, optimistic locking hoặc audit. Nếu nghiệp vụ cần chắc chắn mỗi item cập nhật đúng một bản ghi, hãy đọc `int[][]` trả về và kiểm tra kết quả theo hợp đồng của JDBC driver, bao gồm các mã `SUCCESS_NO_INFO` và `EXECUTE_FAILED`, hoặc dùng writer có cơ chế kiểm tra phù hợp.

### 5.1. Batch update không đồng nghĩa một câu SQL duy nhất

`batchUpdate` xử lý nhiều bộ tham số cho cùng một template SQL. Driver có thể gửi nhiều lệnh đã chuẩn bị hoặc tối ưu hóa payload theo cách riêng. Nó khác với một câu set-based SQL:

```sql
UPDATE orders
SET status = 'READY'
WHERE processing_date = :businessDate
  AND status = 'NEW';
```

Set-based SQL có thể cập nhật hàng nghìn dòng trong một statement, đôi khi nhanh hơn rất nhiều so với hàng nghìn UPDATE theo ID. Nhưng nó phù hợp khi các bản ghi cùng chịu một quy tắc điều kiện; nếu mỗi đơn hàng có trạng thái mới khác nhau hoặc có kiểm tra nghiệp vụ theo item, batching theo item có thể dễ kiểm soát hơn.

Cần so sánh cả hai hướng bằng workload thật, thay vì giả định batching là hình thức tối ưu cao nhất.

## 6. Lựa chọn batch update size lớn hay nhỏ

Không có con số tối ưu cho mọi hệ quản trị, driver và dữ liệu.

### 6.1. Batch nhỏ

Ví dụ `jdbcBatchSize=10`:

Ưu điểm:

- Giữ lượng tham số, dữ liệu buffer và bộ nhớ ở mức thấp.
- Dễ cô lập nhóm có vấn đề khi cần phân tích lỗi.
- Hạn chế kích thước một lần gửi đến driver.
- Phù hợp khi câu SQL nặng, row rộng hoặc hệ thống bị giới hạn tài nguyên.

Nhược điểm:

- Có thể cần nhiều lần `executeBatch()` và nhiều chi phí lặp lại.
- Với latency cao giữa ứng dụng và database, throughput có thể thấp.
- CPU/driver có thể tốn chi phí quản lý nhiều batch nhỏ.

### 6.2. Batch lớn

Ví dụ `jdbcBatchSize=1.000`:

Ưu điểm:

- Có thể giảm số lần gọi tầng JDBC.
- Tăng hiệu quả truyền tham số và tối ưu hóa ở driver/database.
- Hữu ích với thao tác lặp lại, câu SQL giống nhau và dữ liệu có kích thước vừa phải.

Nhược điểm:

- Dữ liệu/parameter buffer có thể lớn; tốn memory.
- Khi một batch lỗi, thông tin lỗi có thể khó quy về từng item.
- Database có thể phải giữ nhiều lock/tài nguyên hơn trong khi xử lý.
- Một số driver có giới hạn packet, số bind parameter hoặc kích thước batch.
- Một batch cực lớn có thể tăng độ trễ một lời gọi `executeBatch()` và ảnh hưởng khả năng dừng job có kiểm soát.

**Chunk size lớn** còn làm transaction dài và tăng chi phí rollback khi lỗi. **JDBC batch size lớn** chủ yếu ảnh hưởng nhóm lệnh ở tầng JDBC; hai yếu tố thường có tương quan khi writer nhận toàn chunk, nhưng không phải lúc nào cũng tăng/giảm cùng nhau.

### 6.3. Bảng so sánh định tính

| Kích thước | Số lần gọi batch | Bộ nhớ tham số | Khả năng phản hồi | Khi nên cân nhắc |
|---|---|---|---|---|
| 1 | Nhiều nhất | Thấp | Từng lệnh ngắn | Baseline để so sánh |
| 20–50 | Nhiều | Thấp–vừa | Thường tốt | Item lớn, SQL nặng |
| 100–200 | Trung bình | Vừa | Cân bằng | Điểm bắt đầu khảo sát phổ biến |
| 500–1.000 | Ít | Cao hơn | Batch có thể lâu hơn | SQL nhẹ, DB/driver tối ưu tốt |
| Trên 1.000 | Rất ít | Có thể rất cao | Rủi ro batch rất dài | Chỉ chọn sau benchmark |

Các khoảng số là **gợi ý thử nghiệm**, không phải giới hạn hay best practice bắt buộc. Nên thử nhiều cấu hình dưới tải đại diện để xác định ngưỡng phù hợp.

## 7. Tác động của transaction và commit interval

Đây là phần quan trọng nhất khi tăng batch size trong Spring Batch.

Giả sử:

```text
Chunk size:       500 item
JDBC batch size:  100 item
Transaction:      JDBC transaction bao trùm chunk
```

Step xử lý:

```text
BEGIN TRANSACTION

  executeBatch(items 1..100)
  executeBatch(items 101..200)
  executeBatch(items 201..300)
  executeBatch(items 301..400)
  executeBatch(items 401..500)

COMMIT
```

Nếu nhóm thứ năm thất bại và writer ném exception, **transaction của chunk có thể rollback tất cả cập nhật trong chunk**, gồm các nhóm đã gọi `executeBatch` trước đó, miễn là chúng tham gia cùng transaction và database hỗ trợ rollback đúng cách.

Ngược lại, nếu code writer tự mở connection mới và bật `autoCommit=true`, từng nhóm có thể commit trước khi lỗi được báo. Khi đó khả năng restart/rollback của Spring Batch không còn như mong đợi.

### 7.1. Chọn đúng transaction manager

Với Spring JDBC, cần bảo đảm `JdbcTemplate` sử dụng datasource tham gia transaction do `PlatformTransactionManager` của step quản lý. Trong ứng dụng JDBC thông thường, đó là `DataSourceTransactionManager` hoặc transaction manager phù hợp được Spring Boot cấu hình.

Không nên trộn datasource của writer với một transaction manager hoàn toàn không quản lý connection đó rồi kỳ vọng rollback dữ liệu JDBC.

### 7.2. Tăng chunk và tăng JDBC batch đem lại hai lợi ích khác nhau

| Thay đổi | Có thể giảm | Cái giá cần xét |
|---|---|---|
| Chunk 100 → 1.000 | Số transaction/commit/checkpoint | Transaction dài, lock, rollback lớn |
| JDBC batch 20 → 200 | Số lần chuyển/nhóm lệnh ở JDBC | Buffer lớn, batch xử lý lâu |
| Cả hai cùng tăng | Cả transaction và batch overhead | Khó phân biệt nguyên nhân tối ưu hoặc suy giảm |
| Chỉ tăng concurrency | Có thể tăng throughput tổng | Tranh chấp connection/lock, deadlock |

Khi tune, nên thay **một biến chính tại một thời điểm** và giữ workload cố định để biết thay đổi nào có tác dụng.

## 8. Retry, skip và batch thất bại

Một trong những rủi ro khi batch quá lớn là khi một câu UPDATE gặp lỗi, tất cả lệnh trong nhóm có thể báo lỗi theo cách khác nhau tùy driver.

Ví dụ một nhóm có ba item:

```text
id=101 -> cập nhật thành công
id=102 -> vi phạm ràng buộc/điều kiện nghiệp vụ
id=103 -> chưa rõ driver có tiếp tục hay không
```

JDBC có thể ném `BatchUpdateException` và cung cấp `updateCounts`. Nhưng:

- Một số driver dừng ở item lỗi đầu tiên; một số driver có thể tiếp tục xử lý các lệnh còn lại.
- Kết quả có thể là số dòng ảnh hưởng hoặc `Statement.SUCCESS_NO_INFO` / `EXECUTE_FAILED`.
- Các lệnh “đã thực thi” chưa chắc đã **commit**: transaction có thể rollback.
- Sau rollback, Spring Batch có thể retry chunk hoặc áp dụng cơ chế skip theo cấu hình fault-tolerant.
- Không thể luôn suy ra chính xác item gây lỗi từ chỉ số mảng update counts nếu driver tối ưu hóa hoặc nhóm câu lệnh.

Vì vậy, nên ưu tiên:

1. **Validate dữ liệu trước writer** cho những lỗi có thể phát hiện sớm.
2. **Ràng buộc transaction đúng** để lỗi batch không để lại dữ liệu một phần ngoài ý muốn.
3. **Idempotency** để retry/restart không tạo cập nhật sai hoặc side effect lặp.
4. **Giới hạn retry/skip hợp lý** và kiểm thử với driver/database thực tế.
5. **Log định danh nghiệp vụ của nhóm** hoặc correlation ID khi có lỗi, không log payload nhạy cảm hàng loạt.

### 8.1. Cấu hình fault tolerance minh họa

```java
@Bean
Step updateOrderStepWithRetry(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderStatusChange> reader,
        ItemWriter<OrderStatusChange> writer) {

    return new StepBuilder("updateOrderStepWithRetry", repository)
            .<OrderStatusChange, OrderStatusChange>chunk(
                    200, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(org.springframework.dao.DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

Đây chỉ là ví dụ retry cho một loại lỗi truy cập database. Tên/nhóm exception trong phiên bản Spring Framework cụ thể có thể khác, nên cần chọn các exception thực sự quan sát từ driver và chính sách ứng dụng. Không bật retry cho mọi `Exception` vì lỗi SQL cú pháp hoặc dữ liệu không hợp lệ thường không tự biến mất.

Nếu muốn skip từng item khi update thất bại, phải xem xét kỹ xem writer có thể cô lập item lỗi và liệu driver báo thông tin đủ chính xác hay không. `faultTolerant()` không biến mọi batch SQL thành thao tác skip an toàn theo item một cách kỳ diệu.

### 8.2. Vấn đề cập nhật trùng item

Một chunk có thể chứa cùng `id` nhiều lần:

```text
(id=101, status=READY)
(id=101, status=CANCELLED)
```

Với một `UPDATE ... WHERE id = ?`, thứ tự cập nhật có thể làm bản ghi cuối phụ thuộc thứ tự xử lý. Khi reader không bảo đảm thứ tự hoặc khi chạy song song, kết quả có thể không ổn định.

Giải pháp tùy nghiệp vụ:

- Đảm bảo chỉ một update cho mỗi entity ID trong một execution.
- Dùng version/optimistic locking khi cần phát hiện cập nhật cạnh tranh.
- Chuẩn hóa/sắp xếp dữ liệu trước khi ghi nếu thứ tự có ý nghĩa.
- Dùng upsert/set-based operation được thiết kế rõ semantics nếu phù hợp.

Batch size lớn **không giải quyết được tranh chấp cập nhật**; đôi khi còn khiến tác động của lock kéo dài hơn.

## 9. Hibernate/JPA batch update size

Khi step dùng JPA thay vì `JdbcTemplate`, cách gom SQL phụ thuộc ORM và persistence context.

Hibernate cung cấp cấu hình JDBC batch như:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_updates: true
```

Trong cấu hình trên:

- `hibernate.jdbc.batch_size=50` đặt ngưỡng batching mà Hibernate dùng cho những statement tương thích.
- `hibernate.order_updates=true` cho phép Hibernate sắp xếp các update theo entity type và primary key; có thể cải thiện khả năng batching và giảm một số deadlock trong tình huống nhất định, với chi phí sắp xếp.
- Số update thật được gom phụ thuộc dirty checking, thời điểm `flush`, entity mapping, SQL statement và JDBC driver.

**Chunk size của Spring Batch vẫn độc lập** với `hibernate.jdbc.batch_size`. Ví dụ `chunk(500)` và Hibernate JDBC batch 50 có thể dẫn tới nhiều nhóm SQL khi flush.

### 9.1. `JpaItemWriter` và persistence context

`JpaItemWriter` viết entity thông qua `EntityManager` của step, thường flush khi write và có tùy chọn quản lý persistence context. Cần hiểu:

- Cập nhật entity chỉ phát SQL nếu Hibernate xác định entity cần update theo mapping và trạng thái.
- Persistence context giữ entity và tracking metadata, nên chunk rất lớn có thể tốn bộ nhớ.
- Hibernate có thể cần nhóm theo loại SQL; các update hỗn tạp hoặc statement khác nhau có thể phá khả năng batching.
- Việc gọi `flush()` quá thường xuyên có thể giảm hiệu quả batch; để hàng chục nghìn entity trong persistence context cũng không tối ưu.
- Tối ưu JDBC batching không thay thế việc xem SQL log, slow query và số statement thực tế.

Nếu dùng `JpaPagingItemReader`, `JpaItemWriter` hoặc repository custom, cần xác định chính xác transaction và cơ chế flush/clear của phiên bản đang chạy. Không giả định chỉ cần đặt `hibernate.jdbc.batch_size` là mọi repository `save(...)` tự trở nên tối ưu.

### 9.2. So sánh JDBC và JPA

| Tiêu chí | `JdbcBatchItemWriter` | `JpaItemWriter` / Hibernate |
|---|---|---|
| Tạo SQL | SQL viết trực tiếp | SQL do ORM sinh |
| Batch size | Chủ yếu theo chunk; tùy biến qua JDBC nếu cần | `hibernate.jdbc.batch_size` |
| Quản lý entity | Không có persistence context JPA | Có dirty checking, flush, entity lifecycle |
| Kiểm soát UPDATE count | Gần JDBC hơn | Phụ thuộc ORM và mapping |
| Phù hợp | ETL/update lớn, SQL rõ ràng | Job cần domain entity và logic JPA |
| Điểm cần theo dõi | Driver batch/round-trip, update counts | Flush, memory, SQL grouping, N+1 |

Với bulk update đơn giản và lượng dữ liệu lớn, JDBC hoặc một câu `UPDATE` set-based có thể đáng benchmark. Với nghiệp vụ yêu cầu cascade, versioning và quan hệ entity, JPA có thể phù hợp hơn dù số SQL và memory phải được kiểm soát.

## 10. Những yếu tố khiến tăng batch size không giúp nhanh hơn

### 10.1. SQL UPDATE chậm vì thiếu index

Ví dụ:

```sql
UPDATE orders
   SET status = :status
 WHERE external_code = :externalCode;
```

Nếu cột `external_code` không được index phù hợp, mỗi UPDATE có thể quét nhiều dòng. Gom 1000 UPDATE không thay thế việc thiết kế index và query plan tốt.

Nên kiểm tra:

- Trường tìm kiếm có index đúng không?
- Predicate có chọn lọc và sargable không?
- Có trigger, cascade, foreign key hoặc audit làm update nặng không?
- Có nhiều row bị khóa/chờ commit không?
- Có truy cập không cần thiết vào cột lớn không?

### 10.2. Batch chứa nhiều SQL không giống nhau

JDBC batching hiệu quả nhất khi sử dụng cùng statement template. Nếu mỗi item tạo SQL động khác nhau, driver/ORM khó gom.

Ví dụ:

```text
UPDATE orders SET status = ? WHERE id = ?
UPDATE orders SET status = ?, note = ? WHERE id = ?
UPDATE orders SET ship_date = ? WHERE id = ?
```

Đây là ba dạng SQL khác nhau. Nếu có thể thống nhất SQL hoặc nhóm theo loại thay đổi mà vẫn giữ semantics chính xác, cơ hội batching tốt hơn.

### 10.3. Network và driver

Một số driver có tùy chọn tối ưu batching hoặc rewrite SQL, nhưng tác dụng phụ thuộc database và loại statement. Tùy chọn tối ưu `INSERT` có thể không áp dụng tương tự cho `UPDATE`.

Đừng áp dụng một tham số driver theo blog rồi kết luận hiệu năng đã tăng nếu chưa đo số câu SQL thực hiện, traffic, latency và throughput.

### 10.4. Database lock và transaction log

Nếu nhiều thread hoặc partition cập nhật vùng dữ liệu giao nhau, batch lớn có thể làm lock giữ lâu, tăng nguy cơ deadlock hoặc lock wait. Hệ thống còn phải ghi redo/WAL/transaction log; một batch cực lớn có thể làm I/O log trở thành bottleneck.

Khi này, giảm batch/chunk hoặc điều chỉnh partitioning có thể tốt hơn tăng chúng.

### 10.5. Connection pool và số worker

Ví dụ có 16 worker nhưng connection pool chỉ cho 8 kết nối hoạt động. Tăng JDBC batch size từ 100 lên 1000 không giải quyết hoàn toàn tình trạng worker chờ connection. Trái lại, transaction mỗi worker dài hơn có thể làm thời gian chờ pool tăng.

Tối ưu end-to-end cần xem cùng lúc:

```text
CPU / memory
    |
Spring Batch concurrency
    |
Connection pool
    |
JDBC driver
    |
Database connections / locks / WAL
    |
Storage I/O
```

## 11. Thiết kế benchmark để chọn batch update size

Tối ưu nên dựa trên **một workload có thể chạy lại**. Hãy tạo bộ dữ liệu mẫu gần với production về độ rộng row, phân bố khóa, số index, tỉ lệ update hợp lệ và tỉ lệ lỗi.

Giữ ổn định những yếu tố khác trong từng nhóm benchmark:

- Cùng loại database và phiên bản driver.
- Cùng dataset hoặc được reset về trạng thái tương đương trước mỗi lượt.
- Cùng chunk size khi đang thử JDBC batch size.
- Cùng concurrency, connection pool và transaction isolation.
- Cùng chiến lược index, trigger và cấu hình database.
- Chạy warm-up và nhiều lượt đo để giảm ảnh hưởng cache/JIT.
- Ghi nhận cả throughput, latency và số lỗi, không chỉ tổng thời gian.

### 11.1. Ma trận thử nghiệm minh họa

Giả sử cố định `chunkSize=500`, có thể thử:

| Lượt thử | JDBC batch size | Thời gian | Throughput | Ghi chú |
|---|---:|---:|---:|---|
| A | 1 | Cần đo | Cần đo | Baseline |
| B | 20 | Cần đo | Cần đo | Kiểm tra lợi ích batching nhỏ |
| C | 50 | Cần đo | Cần đo | Kiểm tra mức trung gian |
| D | 100 | Cần đo | Cần đo | Kiểm tra 5 nhóm/chunk |
| E | 250 | Cần đo | Cần đo | Kiểm tra 2 nhóm/chunk |
| F | 500 | Cần đo | Cần đo | Kiểm tra 1 nhóm/chunk |

Sau khi chọn vùng JDBC batch size có tiềm năng, tiếp tục thử chunk size `100`, `500`, `1.000` với batch size đã chọn. Đừng thay đồng thời hai biến ngay từ đầu vì khó xác định thay đổi nào tạo ra tác dụng.

### 11.2. Các chỉ số nên thu thập

| Metric | Ý nghĩa |
|---|---|
| `step duration` | Tổng thời gian từ khi step bắt đầu đến khi kết thúc |
| `items/sec` | Số item hoàn tất trên mỗi giây |
| `writeCount` | Số item Spring Batch ghi theo counter của step |
| `commitCount` | Số commit trong step |
| `rollbackCount` | Số lần rollback |
| Số lần `executeBatch()` | Có thực sự giảm số nhóm JDBC không |
| Tổng/update SQL latency | Bottleneck ở lệnh SQL hay tầng Java |
| Lock wait / deadlock | Tăng batch có gây tranh chấp không |
| CPU, heap, GC | Có phát sinh memory pressure không |
| DB transaction log/WAL | Có nghẽn I/O commit không |
| Connection wait/pool usage | Có bottleneck phía connection không |

**Lưu ý:** `StepExecution.getWriteCount()` phản ánh số item được Batch writer xử lý theo framework, **không nhất thiết bằng tổng số dòng database được UPDATE**. Một câu SQL có thể ảnh hưởng 0, 1 hoặc nhiều dòng; một item cũng có thể tạo nhiều statement. Nếu mục tiêu là kiểm toán số dòng thực sự thay đổi, cần thu thập affected-row counts phù hợp hoặc truy vấn xác nhận dữ liệu.

### 11.3. Ví dụ cách đọc kết quả

Giả sử benchmark của **một ứng dụng cụ thể** cho kết quả giả định:

| JDBC batch size | Thời gian 100.000 updates | Updates/giây |
|---:|---:|---:|
| 1 | 180 s | ~556 |
| 50 | 70 s | ~1.429 |
| 100 | 58 s | ~1.724 |
| 250 | 55 s | ~1.818 |
| 500 | 61 s | ~1.639 |
| 1.000 | 83 s | ~1.205 |

Các số liệu này **chỉ minh họa** cách phân tích đường cong, không phải benchmark được đo thực tế. Nếu bảng này xuất hiện trên hệ thống của bạn, `250` là ứng viên tốt hơn `1.000`. Sau ngưỡng nhất định, batch lớn hơn có thể làm memory, locking hoặc độ trễ một nhóm trở thành chi phí đáng kể.

Không nên chọn size chỉ từ throughput. Nếu size 250 nhanh hơn 100 ba giây nhưng làm `rollbackCount` hoặc P95 latency tăng mạnh, size 100 có thể an toàn hơn cho vận hành.

## 12. Đo hiệu năng trong Spring Batch

Spring Batch 5.x có tích hợp Micrometer cho metric job/step và một số giai đoạn xử lý. Có thể dùng Spring Boot Actuator + registry thích hợp, kết hợp `JobExplorer` để xem execution cụ thể.

Ví dụ cấu hình Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Dự án còn cần JDBC driver và datasource phù hợp; phiên bản phụ thuộc thường do Spring Boot BOM quản lý.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Các meter đáng quan tâm khi ứng dụng đã bật instrumentation bao gồm:

- `spring.batch.step`: Timer duration của step.
- `spring.batch.chunk.write`: thời gian writer xử lý một chunk.
- `spring.batch.item.read`: thời gian read item.
- `spring.batch.item.process`: thời gian process item.
- `spring.batch.step.active`: theo dõi step còn chạy nếu phiên bản có LongTaskTimer tương ứng.

Tên tag và meter thực tế phụ thuộc phiên bản. Kiểm tra tại `/actuator/metrics` hoặc `/actuator/prometheus` trước khi viết query cố định. **Micrometer step/chunk duration chưa tự cho biết chính xác có bao nhiêu lời gọi JDBC `executeBatch()`**; nếu cần đếm batch JDBC, thêm instrumentation ở writer hoặc theo dõi phía JDBC/driver.

### 12.1. Đo riêng từng write call

Một ví dụ tạo custom Timer chỉ cho lời gọi writer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class TimedWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final MeterRegistry registry;

    public TimedWriter(ItemWriter<T> delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        Timer.Sample sample = Timer.start(registry);

        try {
            delegate.write(chunk);
        } finally {
            sample.stop(
                    Timer.builder("custom.batch.writer.duration")
                            .tag("writer", "orderUpdate")
                            .register(registry)
            );
        }
    }
}
```

Metric trên đo **thời lượng gọi writer** gồm mã Java và JDBC, không chỉ network hoặc thời gian thực thi SQL trong database. Để đo SQL chính xác hơn, kết hợp JDBC/DB telemetry.

Đừng gắn `orderId`, `jobExecutionId` hoặc mỗi `chunkIndex` làm tag metric: chúng làm số series tăng không giới hạn. Dùng chúng trong log/tracing nếu cần truy vết một lần chạy cụ thể.

## 13. Kiểm thử writer và transaction

### 13.1. Unit test không cần cơ sở dữ liệu

Với writer tự xây, unit test có thể kiểm tra rằng nó truyền đúng `batchSize`, SQL và tham số cho `JdbcTemplate`. Nhưng test chỉ mock `JdbcTemplate` **không chứng minh database nhận batching hoặc rollback đúng**.

Giả sử cần kiểm tra constructor không nhận batch size không hợp lệ:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class SizedOrderUpdateWriterTest {

    @Test
    void rejectsZeroBatchSize() {
        JdbcTemplate template = mock(JdbcTemplate.class);

        assertThrows(
                IllegalArgumentException.class,
                () -> new SizedOrderUpdateWriter(template, 0)
        );
    }
}
```

Test này hữu ích vì nó bảo vệ một quy tắc đầu vào đơn giản; khả năng write/commit cần test tích hợp.

### 13.2. Integration test với database

Ví dụ dùng `@SpringJdbcTest` hoặc `@JdbcTest` tùy tổ chức ứng dụng; với Spring Boot, `@JdbcTest` cung cấp một context JDBC gọn để chạy SQL trên database test.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.Chunk;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class SizedOrderUpdateWriterJdbcTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jdbcTemplate.execute("DROP TABLE IF EXISTS orders");
        jdbcTemplate.execute("""
            CREATE TABLE orders (
                id BIGINT PRIMARY KEY,
                status VARCHAR(32) NOT NULL
            )
            """);
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                101L, "NEW"
        );
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                102L, "NEW"
        );
        jdbcTemplate.update(
                "INSERT INTO orders(id, status) VALUES (?, ?)",
                103L, "NEW"
        );
    }

    @Test
    void updatesItemsAcrossMultipleJdbcBatches() {
        SizedOrderUpdateWriter writer =
                new SizedOrderUpdateWriter(jdbcTemplate, 2);

        writer.write(new Chunk<>(List.of(
                new OrderStatusChange(101L, "READY"),
                new OrderStatusChange(102L, "READY"),
                new OrderStatusChange(103L, "CANCELLED")
        )));

        assertEquals("READY", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 101",
                String.class
        ));
        assertEquals("READY", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 102",
                String.class
        ));
        assertEquals("CANCELLED", jdbcTemplate.queryForObject(
                "SELECT status FROM orders WHERE id = 103",
                String.class
        ));
    }
}
```

Ví dụ trên chứng minh writer cập nhật đúng dữ liệu khi có nhiều nhóm JDBC, **không tự chứng minh số network round-trip**. Muốn khẳng định rollback khi nhóm sau thất bại, cần tạo lỗi trong một transaction test và kiểm tra dữ liệu sau khi rollback, với đúng transaction manager và DB engine mà production sử dụng.

Với cơ sở dữ liệu thật như PostgreSQL/SQL Server/MySQL, các giới hạn batching và update counts có thể khác H2. Những vấn đề về deadlock, packet size và query plan nên được kiểm thử ít nhất trên một môi trường tương tự production.

### 13.3. Test trong một Step thực

Dùng `spring-batch-test`, `JobLauncherTestUtils.launchStep("updateOrderStep")` và datasource test để xác nhận:

- Step kết thúc `COMPLETED` khi dữ liệu hợp lệ.
- Số item đọc/ghi theo `StepExecution` đúng mong đợi.
- Dữ liệu DB đạt trạng thái mong muốn.
- Khi writer ném lỗi trong một chunk, các thay đổi chưa commit không còn sau rollback.
- Restart với checkpoint phù hợp không cập nhật sai hoặc gửi side effect trùng.

Nếu chỉ quan tâm logic mapping SQL, integration test writer ngắn thường đủ. Khi cần kiểm chứng commit interval, retry, skip và restart của Spring Batch, phải chạy step thật thay vì gọi `writer.write(...)` trực tiếp.

## 14. Batch size trong môi trường chạy song song

Khi một step sử dụng nhiều thread hoặc partition, tác động của batch size được nhân lên bởi concurrency.

Giả sử:

```text
4 worker threads
mỗi worker xử lý chunk 500
mỗi chunk chia thành JDBC batch 100
```

Có thể có đồng thời nhiều transaction và nhiều nhóm batch cạnh tranh tài nguyên database. Nếu mỗi worker cùng cập nhật bảng `orders`, cần xem index, khóa, thứ tự ID và sức chứa của connection pool.

Một quy trình tune hợp lý:

1. Xác định throughput hiện tại với **1 worker**.
2. Chọn vùng chunk/JDBC batch size ổn định.
3. Tăng worker từ 1 lên 2, 4, 8 ... trong phạm vi hạ tầng.
4. Ghi lại connection wait, lock wait, deadlock, CPU và throughput.
5. Dừng tăng concurrency khi lợi ích thấp hơn chi phí tranh chấp.

Không nên coi `8 worker × batch 500` là “batch size 4.000” cho một transaction duy nhất. Đó là nhiều luồng và nhiều transaction riêng, mỗi luồng có vòng đời và lỗi riêng.

### Partitioning theo khóa

Nếu chia partition theo vùng ID hoặc business date, các worker nên xử lý tập dữ liệu **ít chồng lấp**. Điều này giúp tránh hai transaction cập nhật cùng một row. Tuy nhiên, chia partition quá lệch có thể khiến một worker xử lý 90% dữ liệu còn các worker khác rảnh.

Tối ưu batch update size cần được đặt cùng mục tiêu cân bằng partition và khóa; chỉ tăng size trong một partition quá lớn không sửa được data skew.

## 15. Quy trình tuning thực tế

Một tình huống: job cập nhật 2 triệu bản ghi đêm nay thường mất 80 phút, trong khi SLA cho phép 45 phút.

**Bước 1 — Đo baseline.** Ghi nhận `stepDuration`, `readCount`, `writeCount`, chunk size, số statement/batch thực tế, update latency và database CPU/lock.

**Bước 2 — Xác định bottleneck.** Nếu reader là chỗ chậm nhất, thay đổi JDBC batch update size của writer có thể gần như không giúp. Nếu writer chậm do network và nhiều update nhỏ, batching có tiềm năng.

**Bước 3 — Thử JDBC batch size.** Giữ chunk size, concurrency và dataset. So sánh 20, 50, 100, 200, 500; đừng nhảy thẳng lên 10.000.

**Bước 4 — Thử chunk size.** Nếu số transaction/commit quá nhiều, thử tăng commit interval nhưng quan sát lock, rollback cost và memory.

**Bước 5 — Xem SQL.** Nếu mỗi update tốn nhiều thời gian do thiếu index hoặc trigger, tối ưu SQL/schema có thể lợi hơn tăng batch size.

**Bước 6 — Kiểm thử lỗi.** Cố ý tạo một update vi phạm constraint, kiểm tra rollback, restart và idempotency ở cấu hình dự kiến triển khai.

**Bước 7 — Đo lại với concurrency thật.** Kết quả 1 worker không đảm bảo áp dụng cho 8 worker, nhất là khi cùng cập nhật một bảng lớn.

**Bước 8 — Giám sát sau triển khai.** So sánh duration, throughput, rollbackCount, DB lock wait, CPU, memory và lỗi với baseline; giữ khả năng đổi cấu hình khi workload thay đổi.

### Những anti-pattern thường gặp

| Anti-pattern | Vì sao có vấn đề? | Cách khắc phục |
|---|---|---|
| Cho rằng `chunk(1000)` tự động cấu hình mọi JDBC driver batch size bằng 1000 | Chunk chỉ xác định ranh giới xử lý/commit | Xác minh writer và batching thực tế |
| Luôn tăng size càng lớn càng tốt | Memory, lock, packet, rollback có thể tăng | Benchmark theo workload |
| Dùng `JdbcTemplate.update` trong vòng lặp và kỳ vọng batching | Mỗi `update` là lời gọi riêng | Dùng `batchUpdate` / `JdbcBatchItemWriter` |
| Tự commit ở từng nhóm JDBC trong writer | Phá ranh giới transaction của step | Để transaction manager của step quản lý |
| Test chỉ với mock rồi tuyên bố database batch tốt | Mock không chạy SQL/driver/transaction | Integration test + benchmark thật |
| Chỉ nhìn `writeCount` để biết affected rows | Counter theo item, không phải số dòng UPDATE | Kiểm tra update counts/dữ liệu thực |
| Bỏ qua trường hợp driver trả `SUCCESS_NO_INFO` | Dễ hiểu nhầm update count | Xử lý theo hợp đồng JDBC |
| Không kiểm tra rollback khi nhóm batch cuối lỗi | Có thể để dữ liệu cập nhật nửa chừng | Test transaction và restart |
| Batch chứa cùng ID nhiều lần mà không xác định thứ tự | Kết quả cập nhật không ổn định | Deduplicate hoặc versioning |
| Kết hợp đồng thời tăng chunk, batch và threads | Không biết yếu tố nào giúp hoặc gây lỗi | Từng bước, một biến chính mỗi lượt |
| Tăng batch nhưng SQL thiếu index | Bottleneck vẫn ở database | Xem query plan/index |
| Dùng một benchmark quá nhỏ | Không phản ánh GC, cache, lock và WAL | Dùng dataset đủ lớn và nhiều lượt đo |

## 16. Bài tập thực hành

Bạn có job `syncCustomerStatus` đọc 500.000 thay đổi trạng thái khách hàng từ file và cập nhật bảng `customer` trong PostgreSQL. Yêu cầu nghiệp vụ là mỗi thay đổi phải được áp dụng chính xác theo `customer_id` và job phải restart an toàn.

Hãy thực hiện các phần sau:

1. Viết `ItemReader<CustomerChange>` và một writer dùng `JdbcBatchItemWriter`. Đặt chunk size = 500.
2. Tạo writer thay thế bằng `JdbcTemplate.batchUpdate(..., batchSize=100, ...)` để chia một chunk thành các nhóm JDBC tối đa 100 phần tử.
3. Chuẩn bị dataset cố định 500.000 item gồm 99% update hợp lệ, 1% ID không tồn tại. Xác định rõ chính sách khi affected rows = 0.
4. So sánh batch size 1, 20, 50, 100, 250 và 500 trên cùng dataset; ghi duration, throughput, memory, lock wait và số lần gọi batch.
5. Giữ JDBC batch size = 100 rồi so sánh chunk size 100, 500 và 1.000. Giải thích vì sao transaction/commit count thay đổi.
6. Mô phỏng constraint violation giữa nhóm batch thứ ba; kiểm tra dữ liệu của toàn chunk sau rollback.
7. Cố ý dừng job, sau đó restart; xác nhận không xảy ra cập nhật sai hoặc hiệu ứng ngoài database trùng.
8. Thử hai worker cập nhật tập customer ID không trùng nhau, rồi thử tập ID bị chồng lấp. Quan sát lock wait/deadlock và giải thích nguyên nhân.
9. Tìm một trường hợp có thể thay hàng nghìn update theo item bằng một câu set-based `UPDATE ... WHERE ...`. So sánh semantics và hiệu năng.
10. Từ kết quả đo, đề xuất hai tham số cho môi trường của bạn: `chunkSize` và `jdbcBatchSize`, kèm bằng chứng tại sao chúng phù hợp hơn các giá trị khác.

**Câu hỏi ôn tập:** Nếu step dùng `chunk(500)` và writer chia JDBC batch size = 100, khi batch thứ năm lỗi thì bốn nhóm đầu có chắc đã commit không?

**Trả lời:** Không. Với một JDBC transaction đúng bao trùm chunk, các nhóm chỉ đã được **thực thi bên trong transaction**; khi rollback, thay đổi chưa commit của cả chunk sẽ bị hoàn tác. Kết quả phụ thuộc việc writer thực sự tham gia cùng transaction và database hỗ trợ rollback cho các thao tác đó.

## 17. Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): cách chunk, commit interval và transaction của step hoạt động.
- [Spring Batch Reference — Database Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter` và lựa chọn writer database.
- [Spring Framework JDBC — Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html#jdbc-batch): `JdbcTemplate.batchUpdate`, batching theo số lượng phần tử.
- [Spring Batch Reference — Retry and Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): chính sách xử lý lỗi ở chunk.
- [Hibernate User Guide — JDBC Batching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch): `hibernate.jdbc.batch_size` và tối ưu thứ tự update.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): theo dõi thời lượng step/chunk.
- [JDBC API — BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html): xử lý lỗi và `updateCounts` của JDBC batch.
