# Chọn cursor hay paging trong Spring Batch

## 1. Bài toán và mục tiêu quyết định

Một job Spring Batch có thể đọc một bảng chứa vài triệu đơn hàng rồi xử lý từng bản ghi qua `ItemProcessor` và `ItemWriter`. Khi thiết kế `ItemReader` cho nguồn JDBC, hai lựa chọn phổ biến là **cursor** và **paging**. Cả hai đều tránh việc nạp toàn bộ dữ liệu vào danh sách Java ngay từ đầu, nhưng chúng khác nhau về cách tương tác với database, tài nguyên sử dụng, độ ổn định khi dữ liệu thay đổi, hiệu năng và khả năng restart.

Nếu chọn không phù hợp, job có thể gặp những biểu hiện như:

- Cursor bị đóng vì timeout hoặc do kết nối JDBC bị ngắt sau một thời gian dài.
- Truy vấn paging chậm dần, database phải xử lý nhiều lần hoặc bỏ sót/trùng bản ghi khi dữ liệu nguồn thay đổi.
- Heap tăng vì cấu hình fetch size/page size quá lớn, hoặc vì writer giữ mọi item.
- Restart từ checkpoint đọc lại không đúng dữ liệu do thứ tự query đã đổi.
- Tăng số worker nhưng throughput không tăng vì nguồn dữ liệu bị tranh chấp hoặc reader không thread-safe.

Bài học thuộc nhóm **Quyết định thiết kế** của **Spring Batch Core Processing**. Mục tiêu không phải khẳng định cursor hay paging luôn nhanh hơn mà là **biết căn cứ chọn** theo tính chất nguồn dữ liệu, transaction, khối lượng dữ liệu, yêu cầu restart và hạ tầng.

Sau bài học, bạn có thể:

1. Giải thích cơ chế của `JdbcCursorItemReader` và `JdbcPagingItemReader`.
2. Phân biệt JDBC cursor với phân trang SQL kiểu `OFFSET/LIMIT`, phân trang theo khóa và cursor token của API.
3. Đánh giá bộ nhớ, kết nối, số truy vấn, transaction và sự thay đổi dữ liệu nguồn.
4. Cấu hình mỗi reader bằng Spring Batch 5.x, với tham số ngày nghiệp vụ và thứ tự đọc ổn định.
5. Bảo vệ restart khỏi dữ liệu thay đổi, xác định cách chia partition và thiết kế idempotency.
6. Đo hiệu năng bằng metadata Batch, database metrics và phép thử có kiểm soát.
7. Dùng một ma trận quyết định để chọn reader phù hợp cho từng trường hợp.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC và PostgreSQL. SQL, cơ chế cursor và transaction có thể khác theo driver/database; cần xác minh với hệ thống thực tế trước khi đưa vào production.

## 2. Cursor và paging thực sự đọc dữ liệu như thế nào?

### 2.1. Cursor: một câu truy vấn, đọc dần qua ResultSet

Reader dùng cursor mở một truy vấn, nhận `ResultSet` rồi gọi `next()` để lấy từng bản ghi. Driver có thể tải dữ liệu từ server theo đợt, tùy cấu hình fetch size, connection và cơ chế hỗ trợ cursor của database.

```text
                   Database
                      |
      SELECT ... WHERE ... ORDER BY ...
                      |
                      v
               JDBC ResultSet
               cursor còn mở
                      |
           fetch theo nhóm từ DB
                      |
                      v
              JdbcCursorItemReader
                   read()
                      |
                      v
             Processor -> Writer
                   chunk N
                      |
                 COMMIT chunk
                      |
                      v
          Tiếp tục đọc ResultSet cũ
```

Điểm nhận diện: thường **một truy vấn chính** phục vụ cả lượt quét, với cursor/result set còn hoạt động xuyên nhiều chunk. Phần dữ liệu JDBC đã nhận về vẫn có thể được buffer tùy driver.

**Không phải cứ dùng tên CursorItemReader là database sẽ stream từng dòng.** Driver có thể buffer phần lớn hoặc toàn bộ ResultSet nếu fetch size, auto-commit hoặc chế độ cursor chưa được thiết lập phù hợp. Phải đo heap, network và behavior của driver thực tế.

### 2.2. Paging: nhiều truy vấn, mỗi lần lấy một trang

Reader paging thực hiện các truy vấn lấy một nhóm bản ghi rồi ánh xạ chúng thành item; khi trang hiện tại đã được tiêu thụ, nó thực hiện truy vấn tiếp theo.

```text
Database: sales_order
         |
         +-- Page 1: 500 rows ----+
         |                        |
         +-- Page 2: 500 rows ----+--> JdbcPagingItemReader
         |                        |            |
         +-- Page 3: 500 rows ----+            v
         |                               read() từng item
         +-- ...                               |
                                            Chunk -> Writer
```

Điểm nhận diện: cursor database lâu dài không phải cơ chế chính; thay vào đó có **nhiều query theo trang**. Spring Batch sử dụng `PagingQueryProvider` để tạo SQL theo database và yêu cầu **sort key ổn định, duy nhất**.

Paging không tự đảm bảo nhất quán khi dữ liệu đang đổi. Nếu bảng thay đổi giữa các truy vấn trang, kết quả của mỗi query có thể nhìn thấy dữ liệu khác nhau tùy isolation, khóa sort và điều kiện lọc.

### 2.3. So sánh ngắn

| Khía cạnh | Cursor | Paging |
| --- | --- | --- |
| Kiểu truy cập | Một result set đọc tuần tự | Nhiều truy vấn lấy từng trang |
| Kết nối DB | Thường giữ kết nối/result set đến cuối step | Kết nối được dùng theo từng lần fetch trang; có thể trả về pool giữa các truy vấn |
| Lượt query | Thường ít hơn | Nhiều hơn, xấp xỉ số trang |
| Cơ chế buffer | JDBC fetch/driver buffer | Page buffer cộng item trong chunk |
| Sắp xếp | `ORDER BY` giúp restart/order ổn định | Sort key là phần thiết yếu để paging chính xác |
| Khả năng chịu connection timeout | Bị ảnh hưởng khi cursor dài và connection mất | Mỗi page query tương đối độc lập, nhưng tổng quá trình vẫn có thể lỗi |
| Dữ liệu thay đổi giữa các lần đọc | Phụ thuộc transaction/isolation/cursor semantics | Các trang có thể quan sát snapshot khác nhau |
| Restart | Thường mở lại query, khôi phục vị trí theo trạng thái đã lưu | Khôi phục vị trí/trang dựa trên state và sort key |
| Parallelism | Một cursor đơn thường thiên về tuần tự | Có thể kết hợp partition theo khoảng key; một reader cũng không mặc nhiên thread-safe |

**Không nên chọn theo một câu “cursor luôn nhanh hơn” hoặc “paging luôn an toàn hơn”.** Các thuộc tính cụ thể phụ thuộc driver, query, index, transaction và sự thay đổi của dữ liệu.

## 3. JDBC cursor khác API cursor và SQL OFFSET

Từ “cursor” có thể chỉ nhiều khái niệm:

- **JDBC cursor:** một `ResultSet` còn mở, dữ liệu được đọc dần qua kết nối tới database.
- **API cursor token:** server trả một token cho request tiếp theo, ví dụ `nextCursor=abc123`. Đây là kiểu phân trang API và không nhất thiết giữ JDBC ResultSet lâu dài.
- **Keyset pagination:** truy vấn trang tiếp theo dựa trên giá trị khóa cuối của trang trước, ví dụ `WHERE order_id > :lastId`.
- **Offset pagination:** truy vấn bỏ qua N dòng rồi lấy trang kế tiếp, ví dụ `OFFSET 500000 LIMIT 500`.

Hai cách SQL paging có đặc điểm khác nhau:

```sql
-- OFFSET: những dòng trước vị trí offset vẫn có thể
-- tạo chi phí quét/sắp xếp/bỏ qua rất lớn.
SELECT order_id, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
ORDER BY order_id
LIMIT 500 OFFSET 100000;
```

```sql
-- Keyset: tiếp tục sau khóa cuối đã xử lý.
SELECT order_id, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
  AND order_id > 100500
ORDER BY order_id
LIMIT 500;
```

Khi có index phù hợp, keyset thường tránh được chi phí bỏ qua hàng trăm nghìn bản ghi của offset. Nhưng keyset vẫn không bảo đảm snapshot bất biến nếu có bản ghi mới được thêm, xóa hoặc cập nhật điều kiện lọc trong lúc đọc.

**Với `JdbcPagingItemReader`**, để framework tạo câu query và quản lý state theo database dialect, bạn cấu hình sort key qua `sortKeys`. Các query được tạo và cách đọc trang phụ thuộc `PagingQueryProvider`/dialect; không nên quy giản mọi implementation thành đúng một mẫu `LIMIT OFFSET` viết tay. Spring Batch dùng sort key để xác định vị trí tiếp tục trong cơ chế paging/restart.

## 4. Các tiêu chí chính để chọn

Trước khi viết code, hãy trả lời các câu hỏi sau:

| Câu hỏi | Nếu câu trả lời là... | Hướng cân nhắc |
| --- | --- | --- |
| Dữ liệu có thể đọc tuần tự qua một query ổn định? | Có, ít biến động | Cursor phù hợp để xem xét |
| Một connection có thể giữ lâu trong nhiều phút/giờ? | Không; proxy/pool có timeout | Ưu tiên cân nhắc paging |
| Bảng có khóa duy nhất dùng làm sort key? | Có index phù hợp | Paging có nền tảng tốt |
| Query phức tạp, sort/join tốn kém mỗi trang? | Có | Cursor có thể giảm lặp query |
| Cần partition độc lập theo vùng dữ liệu? | Có | Paging theo key range thường tiện triển khai |
| Dữ liệu đang được INSERT/UPDATE/DELETE liên tục? | Có | Snapshot/watermark là quyết định quan trọng hơn chọn reader |
| Restart bắt buộc chính xác, không mất/trùng item? | Có | Cần nguồn ổn định, checkpoint và writer idempotent ở cả hai loại |
| Driver thực sự stream ResultSet? | Không rõ | Test trước khi chọn cursor |
| Số lượng kết quả nhỏ? | Vài nghìn dòng | Cả hai có thể tốt; ưu tiên đơn giản và bảo trì |
| Bộ nhớ container rất hạn chế? | Có | Giới hạn fetch/page/chunk và đo retained heap cho cả hai |

Một câu trả lời thực tế thường gồm **reader + cấu hình + chính sách nhất quán dữ liệu + phương án restart**, chứ không chỉ tên class.

## 5. Ví dụ dữ liệu dùng chung

Giả sử cần xử lý đơn hàng theo `businessDate`:

```sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sales_order_date_id
    ON sales_order (business_date, order_id);
```

Cần đọc các bản ghi của ngày 15/11/2026, theo `order_id` tăng dần, rồi ghi tổng hợp vào hệ thống đích.

Dùng mô hình item:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderRow(
        long orderId,
        LocalDate businessDate,
        BigDecimal amount) {
}
```

Cả cursor và paging sẽ ánh xạ cùng một loại item. Bảng có `order_id` là primary key, nên nó là một khóa sắp xếp duy nhất trong phạm vi ngày xử lý.

Trong thực tế, điều kiện lọc có thể bao gồm nhiều cột như `status='READY'` và `tenant_id`. Nếu các cột đó thay đổi khi job đang chạy, bạn cần quy tắc snapshot hoặc cách chuyển trạng thái để đảm bảo không bỏ sót item.

## 6. Cấu hình JdbcCursorItemReader trong Spring Batch 5.x

Một ví dụ cấu hình cursor reader bằng builder và `@StepScope`:

```java
import java.sql.Date;
import java.time.LocalDate;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CursorReaderConfiguration {

    @Bean("ordersCursorReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> ordersCursorReader(
            DataSource dataSource,
            @Value("#{jobParameters['businessDate']}")
                String businessDate) {

        LocalDate date = LocalDate.parse(businessDate);

        return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("ordersCursorReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT order_id, business_date, amount
                 FROM sales_order
                 WHERE business_date = ?
                 ORDER BY order_id
                 """)
            .preparedStatementSetter(
                ps -> ps.setDate(1, Date.valueOf(date))
            )
            .rowMapper((rs, rowNum) -> new OrderRow(
                rs.getLong("order_id"),
                rs.getDate("business_date").toLocalDate(),
                rs.getBigDecimal("amount")
            ))
            .fetchSize(500)
            .saveState(true)
            .build();
    }
}
```

Ý nghĩa các tùy chọn:

- `name("ordersCursorReader")` tạo tên ổn định để quản lý state trong `ExecutionContext`.
- `@StepScope` cho phép lấy `businessDate` khi step chạy, tránh cố định ngày xử lý lúc ứng dụng startup.
- `preparedStatementSetter` truyền tham số SQL theo kiểu JDBC, không nối chuỗi người dùng vào SQL.
- `ORDER BY order_id` giữ thứ tự kết quả có thể dự đoán trong cùng một snapshot dữ liệu.
- `fetchSize(500)` gợi ý driver lấy dữ liệu theo nhóm; **không** mặc định là toàn bộ kết quả chỉ chiếm đúng 500 object.
- `saveState(true)` cho phép reader lưu vị trí đọc phục vụ restart theo cơ chế của Spring Batch.

### Cursor và transaction

`JdbcCursorItemReader` thường sử dụng một kết nối riêng cho cursor, khác với connection mà step dùng để commit chunk. Nhờ vậy cursor có thể tiếp tục đọc qua nhiều transaction của step. Nhưng điều đó cũng có nghĩa **transaction commit ở writer không mặc định kiểm soát snapshot hoặc lifetime của cursor**.

Trong một số tình huống đặc biệt, Spring Batch có tùy chọn `useSharedExtendedConnection` với `ExtendedConnectionDataSourceProxy` và driver hỗ trợ cursor giữ qua commit. Đây là cấu hình nâng cao; không bật chỉ để “tối ưu” khi chưa hiểu driver và transaction manager.

**Điểm cần xác minh ở môi trường thực:** Driver PostgreSQL có yêu cầu về auto-commit và fetch-size để thực sự chuyển sang cách lấy dữ liệu theo đợt. Các JDBC driver khác cũng có điều kiện riêng. Đừng khẳng định reader streaming chỉ vì đã đặt `fetchSize(500)`.

## 7. Cấu hình JdbcPagingItemReader trong Spring Batch 5.x

Paging reader dùng `selectClause`, `fromClause`, `whereClause`, `sortKeys` và `parameterValues`. Spring Batch chọn cách sinh SQL phù hợp database:

```java
import java.sql.Date;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PagingReaderConfiguration {

    @Bean("ordersPagingReader")
    @StepScope
    JdbcPagingItemReader<OrderRow> ordersPagingReader(
            DataSource dataSource,
            @Value("#{jobParameters['businessDate']}")
                String businessDate) {

        LocalDate date = LocalDate.parse(businessDate);

        Map<String, Order> sortKeys = new LinkedHashMap<>();
        sortKeys.put("order_id", Order.ASCENDING);

        return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .selectClause("""
                SELECT order_id, business_date, amount
                """)
            .fromClause("FROM sales_order")
            .whereClause("WHERE business_date = :businessDate")
            .parameterValues(
                Map.of("businessDate", Date.valueOf(date))
            )
            .sortKeys(sortKeys)
            .rowMapper((rs, rowNum) -> new OrderRow(
                rs.getLong("order_id"),
                rs.getDate("business_date").toLocalDate(),
                rs.getBigDecimal("amount")
            ))
            .pageSize(500)
            .saveState(true)
            .build();
    }
}
```

Những điểm cốt lõi:

- `sortKeys` là yêu cầu quan trọng. Trong ví dụ, `order_id` unique nên có thể làm khóa sắp xếp.
- `pageSize(500)` quyết định kích thước trang query; nó **không phải chunk size** của step.
- `parameterValues` giúp truyền giá trị `businessDate` cho query theo named parameter.
- `saveState(true)` cho phép reader lưu vị trí để restart.
- Câu SQL cuối được tạo qua paging query provider theo dialect; không viết tay một `OFFSET` tăng dần trong reader ví dụ.

Để hỗ trợ index:

```sql
CREATE INDEX idx_sales_order_date_id
    ON sales_order (business_date, order_id);
```

Index `(business_date, order_id)` có thể hỗ trợ lọc theo ngày và đọc theo order ID, nhưng lợi ích thực tế phụ thuộc selectivity, khối lượng dữ liệu, kế hoạch query, bảng có partition hay không và statistics của database. Nên kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường test có dữ liệu đại diện.

## 8. Cấu hình một chunk step dùng reader đã chọn

Hai reader đều là `ItemStreamReader<OrderRow>` phù hợp với chunk-oriented step. Có thể cấu hình riêng các profile hoặc một property để chọn reader, nhưng **không inject cả hai vào cùng step mà không phân biệt tên**.

Một ví dụ step dùng cursor:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("processOrdersCursorStep")
Step processOrdersCursorStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        @Qualifier("ordersCursorReader")
            JdbcCursorItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("processOrdersCursorStep", repository)
        .<OrderRow, OrderRow>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Nếu dùng paging, thay reader bằng `JdbcPagingItemReader<OrderRow>` và đặt một tên step phù hợp. Cách tổ chức cấu hình của dự án cần bảo đảm các scoped proxy được inject đúng; code trên chỉ minh họa phần wiring, giả định processor và writer đã được khai báo.

**Chunk size 200** và **fetch/page size 500** không cần bằng nhau. Lý tưởng phụ thuộc:

- Số row/resultset fetch từ database trong một lần I/O.
- Số item được giữ trong chunk trước khi writer được gọi.
- Phạm vi rollback và chi phí commit.
- Khối lượng bộ nhớ của item và buffer phía writer.
- Độ trễ database và hiệu suất batch write.

Một phép thử có kiểm soát mới xác định tổ hợp tốt nhất; không có “pageSize luôn phải bằng chunkSize”.

## 9. Khi nào cursor thường là lựa chọn hợp lý?

Cursor phù hợp để cân nhắc khi:

1. Job là một luồng đọc tuần tự dài từ một nguồn ổn định.
2. Database/driver hỗ trợ streaming ResultSet hiệu quả và không buffer toàn bộ dữ liệu.
3. Giữ cursor/kết nối trong thời gian job chạy là chấp nhận được.
4. Query phức tạp, tính toán nhiều, và thực hiện lại query cho từng trang sẽ tốn kém.
5. Không cần nhiều worker cạnh tranh đọc trên một cursor.
6. Khả năng restart được kiểm thử với dữ liệu snapshot ổn định.

### Ví dụ: báo cáo cuối ngày trên snapshot

Bảng `daily_sales_snapshot` được tạo xong lúc 01:00, khóa dữ liệu, sau đó job đọc tuần tự vào 01:15. Snapshot có 3 triệu row, được lập index theo key duy nhất. Nếu driver hỗ trợ fetch theo đợt, cursor có thể giảm overhead do tái truy vấn và duy trì luồng xử lý đơn giản.

Tuy vậy, “snapshot” ở đây phải là một cam kết về dữ liệu, không chỉ là tên bảng. Nếu các row vẫn có thể bị chỉnh sửa trong lúc job chạy, cursor và cơ chế restart đều cần xem lại.

### Rủi ro của cursor kéo dài

- Kết nối database bị chiếm trong thời gian dài.
- Connection pool không còn slot cho workload khác.
- Proxy/LB/firewall có timeout hoặc giới hạn lifetime.
- ResultSet bị đóng khi transaction/kết nối thay đổi.
- Truy vấn giữ tài nguyên DB hoặc snapshot lâu hơn dự kiến.
- Khi connection đứt, job phải fail và restart; không thể tái sử dụng ResultSet cũ trên kết nối mới.

Nếu job chạy nhiều giờ hoặc database có chính sách timeout nghiêm, paging có thể vận hành thuận tiện hơn.

## 10. Khi nào paging thường là lựa chọn hợp lý?

Paging đáng cân nhắc khi:

1. Có unique sort key và index hỗ trợ phân trang hiệu quả.
2. Không muốn một cursor/result set tồn tại suốt thời gian job dài.
3. Cần chia vùng dữ liệu theo ID/time/tenant để partition.
4. Lấy dữ liệu qua nhiều query được hệ thống chấp nhận.
5. Có thể cố định snapshot/watermark hoặc áp dụng quy tắc nhất quán rõ ràng.
6. Muốn điều chỉnh page size và đo mức tải database theo từng nhóm.

### Ví dụ: đọc dữ liệu trên bảng vận hành

Job xử lý các đơn hàng trong một khoảng `order_id` cố định, lấy từng trang 500 row theo khóa duy nhất. Mỗi trang có thể được truy vấn bằng index và kết nối không cần giữ một cursor xuyên cả job. Cách này giúp quản lý tài nguyên tốt hơn khi workload dài và có nhiều partition độc lập.

**Không có nghĩa paging tự động an toàn khi dữ liệu thay đổi.** Nếu business key được sắp xếp nhưng trạng thái READY của row thay đổi trong lúc đọc, truy vấn trang tiếp có thể thấy tập dữ liệu khác. Cần thiết kế snapshot hoặc work claiming.

### Paging có phải luôn nhanh hơn?

Không. Một truy vấn theo trang có thể phải lặp lại JOIN, filter, sắp xếp, tra cứu index và network round-trip. Nếu page size nhỏ so với dữ liệu, số truy vấn rất lớn. Nếu query provider/driver tạo kế hoạch không thuận lợi, paging có thể chậm hơn cursor đáng kể.

Ngược lại, cursor tưởng chừng “một query” vẫn có thể bị driver buffer nhiều dữ liệu, giữ server resources lâu và gây timeout, khiến throughput thực tế kém. Hãy đo.

## 11. Dữ liệu nguồn đang thay đổi: vấn đề quan trọng hơn tốc độ

Giả sử đọc bảng theo thứ tự `order_id`, trong lúc job chạy có transaction khác thêm/xóa/sửa record.

### 11.1. Offset pagination có thể bỏ sót hoặc lặp

Ban đầu:

```text
order_id: 10 20 30 40 50 60
pageSize=3

Page 1: 10 20 30
```

Sau trang 1, một record 15 được thêm vào. Nếu trang 2 dùng `OFFSET 3`:

```text
order_id: 10 15 20 30 40 50 60
Page 2 OFFSET 3: 30 40 50
```

Record 30 bị đọc lại. Nếu có record bị xóa trước vị trí offset, có thể bỏ sót một record.

### 11.2. Keyset tránh lệch offset nhưng không bảo đảm snapshot

Nếu trang tiếp dùng:

```sql
WHERE order_id > :lastOrderId
ORDER BY order_id
```

với `lastOrderId=30`, việc thêm record 15 không khiến trang tiếp đọc lại 30. Đây là ưu điểm của keyset.

Nhưng nếu một record mới có ID 35 được thêm sau trang 1, nó có thể xuất hiện ở trang tiếp; nếu job phải xử lý đúng **snapshot lúc bắt đầu**, đó có thể là dữ liệu ngoài phạm vi mong muốn. Nếu một record chưa đọc bị xóa hoặc đổi status, nó có thể biến mất khỏi các query tiếp theo.

Do đó keyset giảm một loại sai lệch do thay đổi vị trí offset, **không thay thế snapshot isolation hoặc nguồn bất biến**.

### 11.3. Cursor cũng cần xem transaction isolation

Một cursor đang mở có thể quan sát tập row khác nhau theo database và isolation; một số cách sử dụng cho snapshot kết quả tương đối ổn định, nhưng không nên mặc định cursor trên mọi driver luôn là ảnh chụp tại thời điểm job bắt đầu.

Cũng cần phân biệt:

- **Độ nhất quán trong một execution:** query/cursor nhìn thấy những thay đổi nào?
- **Độ nhất quán khi restart:** query mới trên kết nối mới có còn nhìn thấy đúng tập row và thứ tự cũ không?

Ngay cả khi lần chạy đầu có snapshot transaction ổn định, **restart sau crash thường mở query/transaction mới**. Nếu nguồn đã đổi, checkpoint vị trí có thể không còn đại diện cho cùng dữ liệu.

## 12. Chiến lược đảm bảo tập dữ liệu ổn định

Một số thiết kế phổ biến:

### 12.1. Snapshot bảng hoặc file trước khi xử lý

Tạo bảng snapshot theo `snapshot_id` hoặc tạo file nguồn bất biến. Job dùng identifying parameters như `snapshotId` và chỉ đọc tập dữ liệu này.

```text
Operational tables
       |
       v
Create snapshot S123
       |
       +--> Snapshot sealed / immutable
       |
       v
Spring Batch job (snapshotId=S123)
       |
       +--> cursor hoặc paging
       |
       v
Output / audit
```

Ưu điểm: restart và kiểm thử dễ xác định, không bị thay đổi nguồn vận hành trong lúc xử lý. Chi phí: thêm bước tạo snapshot, bộ nhớ đĩa và thời gian chuẩn bị.

### 12.2. High-water mark

Chốt giới hạn trên trước khi job bắt đầu:

```sql
SELECT MAX(order_id)
FROM sales_order
WHERE business_date = DATE '2026-11-15';
```

Sau đó thêm điều kiện `order_id <= :highWaterMark` ở mọi truy vấn. Lưu high-water mark trong JobParameters hoặc metadata bền vững sao cho **restart sử dụng đúng giá trị ban đầu**.

Cách này có thể hạn chế nhận thêm row có order ID mới lớn hơn watermark. Tuy nhiên, nó không bảo vệ trước UPDATE/DELETE của row nằm dưới watermark, hoặc INSERT có ID nhỏ hơn watermark. Vì vậy đây chỉ là giải pháp phù hợp khi nghiệp vụ bảo đảm dữ liệu/ID có tính đơn điệu và điều kiện lọc ổn định.

### 12.3. Claiming và trạng thái xử lý

Với hàng đợi công việc trong database, đôi khi phù hợp hơn nếu dùng **claiming**: chuyển row từ `READY` sang `IN_PROGRESS` bằng transaction/lock, hoặc lấy việc theo partition. Hệ thống phải có quy tắc lease, timeout, retry và trả lại việc chưa hoàn tất.

Đây không chỉ là vấn đề chọn cursor/paging; nó là bài toán phân phối công việc. Nếu job vừa đọc vừa cập nhật chính cột dùng để filter, ví dụ `WHERE status='READY'`, hãy cẩn thận với paging. Các row đã xử lý biến mất khỏi tập kết quả và có thể làm logic theo vị trí không còn đúng.

### 12.4. Khoá nguồn bằng version

Lưu `sourceVersion`, `sourceChecksum` hoặc mã snapshot cùng `businessDate`. Trước khi restart, kiểm tra nguồn vẫn đúng version. Với file, cần đảm bảo đường dẫn chỉ đến nội dung bất biến; chỉ giữ một đường dẫn có thể bị ghi đè là chưa đủ.

## 13. Restart: cursor khôi phục vị trí như thế nào?

Với `JdbcCursorItemReader` có `saveState(true)`, Spring Batch lưu tiến độ đọc vào `ExecutionContext` khi các chunk được commit. Khi một execution thất bại và được restart, reader mở query lại rồi dịch chuyển tới vị trí đã lưu theo cơ chế của reader/driver.

Ví dụ khái niệm:

```text
Execution 1:
  read order_id 1..200   -> commit
  read order_id 201..400 -> commit
  read order_id 401..500 -> fail, rollback

Restart:
  mở query lại
  khôi phục từ checkpoint đã commit
  xử lý lại phần chưa được commit
```

Điều này **không có nghĩa cursor database cũ được giữ qua thời gian JVM chết**. Reader tạo cursor mới và dùng state để khôi phục vị trí.

### Nguy cơ nếu thứ tự/tập row đã đổi

Nếu execution đầu đã đọc 400 dòng; sau đó 5 dòng phía trước được thêm hoặc xóa, việc khôi phục vị trí theo số lượng/row position trong tập query mới có thể dẫn đến đọc sai vị trí. `ORDER BY` ổn định chỉ giải quyết **tính xác định của thứ tự khi tập row giống nhau**, không biến tập row đang thay đổi thành bất biến.

Để restart chính xác, cần snapshot nguồn hoặc bảo đảm các row và thứ tự không đổi giữa các execution.

### driverSupportsAbsolute

Một số driver hỗ trợ di chuyển con trỏ đến vị trí xác định qua API JDBC thay vì đọc tuần tự từ đầu khi restart. Các tùy chọn reader liên quan (ví dụ hỗ trợ `absolute()`) có thể ảnh hưởng chi phí di chuyển vị trí. Cần kiểm chứng driver, không mặc định mọi ResultSet hỗ trợ nhảy ngẫu nhiên hiệu quả.

## 14. Restart: paging dùng sort key và state

`JdbcPagingItemReader` lưu trạng thái tiến độ để có thể đọc tiếp từ vị trí phù hợp. Một **sort key duy nhất** rất quan trọng để reader không nhầm hai bản ghi có cùng giá trị sắp xếp.

Ví dụ không nên chỉ sắp theo `created_at` khi nhiều row có cùng timestamp:

```sql
ORDER BY created_at
```

Nếu nhiều row trùng `created_at`, ranh giới trang có thể không xác định. Nên dùng khóa kết hợp duy nhất:

```sql
ORDER BY created_at, order_id
```

Trong builder:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("order_id", Order.ASCENDING);
```

Đây là ví dụ cho dữ liệu có thứ tự theo thời gian. Nếu `created_at` có thể thay đổi, khóa sắp xếp dù duy nhất vẫn không bảo đảm an toàn khi nguồn bị sửa giữa các trang. Chọn khóa **bất biến** khi có thể.

### Rủi ro của sort key không duy nhất

Giả sử pageSize=2 và ba record cùng `created_at`:

```text
(created_at=10:00, id=A)
(created_at=10:00, id=B)
(created_at=10:00, id=C)
```

Nếu chỉ dựa trên `created_at` để tìm trang sau, không có cách xác định “sau B nhưng trước C” bằng timestamp đó. Có thể mất hoặc lặp item. Thêm `id` vào sortKeys giúp xác định vị trí theo cặp giá trị.

**Quy tắc:** sort key phải xác định thứ tự tổng thể duy nhất của các bản ghi được chọn, không chỉ “phần lớn các dòng có giá trị khác nhau”.

## 15. Cursor, paging và transaction của chunk

Một chunk step có nhiều commit trong quá trình xử lý. Điều này tạo ra ba vòng đời khác nhau:

1. **Transaction xử lý chunk:** đọc, process và write một nhóm item, commit/rollback.
2. **Kết nối/truy vấn nguồn:** cursor hoặc truy vấn trang.
3. **JobExecution/StepExecution:** trạng thái và checkpoint để restart.

Không nên suy luận rằng vì chunk commit mỗi 200 item thì database cursor cũng được đóng/mở sau mỗi 200 item. `JdbcCursorItemReader` thường duy trì một ResultSet dài hơn transaction chunk. Với paging, reader có thể lấy pageSize 500 item rồi phục vụ nhiều chunk từ buffer đó.

### 15.1. Consistency và read-only

Nếu reader dùng một connection/transaction riêng, row visibility phụ thuộc cách database quản lý MVCC/isolation và cấu hình của reader. Gắn `@Transactional(readOnly=true)` cho một method khác trong application không tự làm mọi cursor/page query dùng cùng snapshot.

Nếu muốn snapshot nhất quán xuyên cả job, hãy thiết kế ở cấp **nguồn bất biến/snapshot** hoặc transaction/database semantics phù hợp. Một transaction snapshot kéo dài hàng giờ có thể gây chi phí MVCC/vacuum/lock hoặc giới hạn tài nguyên, nên phải cân nhắc với DBA.

### 15.2. Writer thay đổi dữ liệu reader đang duyệt

Ví dụ query đọc:

```sql
SELECT order_id
FROM sales_order
WHERE status = 'READY'
ORDER BY order_id;
```

Writer đổi `status='PROCESSED'` sau mỗi chunk. Với paging, tập row `READY` đang thu hẹp. Nếu query lại theo thứ tự/offset không phù hợp, các trang sau có nguy cơ bỏ sót. Với cursor, behavior cũng phụ thuộc snapshot/cursor semantics và cách cập nhật.

Hướng giải quyết thường tốt hơn là cố định danh sách khóa nguồn cần xử lý trước, hoặc thiết kế claiming/work queue với transaction riêng, thay vì vừa biến đổi điều kiện lọc vừa kỳ vọng mọi reader paging luôn đúng.

## 16. Bộ nhớ và tài nguyên JDBC

Một hiểu lầm là “cursor không tốn memory, paging mới tốn memory”. Cả hai có buffer:

```text
Cursor:
  JDBC driver buffers / fetch window
       + mapped current item
       + chunk items
       + writer buffers

Paging:
  pageSize mapped items
       + chunk items
       + writer buffers
       + query infrastructure
```

**Working set** có thể tăng khi:

- `fetchSize` hoặc `pageSize` quá lớn.
- Item chứa nhiều trường text/JSON/blob hoặc collection.
- `chunkSize` lớn khiến nhiều item tồn tại đến khi writer xong.
- Writer gom toàn bộ output vào một list trước khi commit.
- Nhiều partition/thread có reader, chunk và connection riêng.
- Logging giữ exception/payload hoặc async queue không giới hạn.

Ví dụ minh họa:

```text
pageSize = 1.000
average retained item ≈ 4 KB

1 paging reader có thể giữ ≈ 4 MB chỉ cho page items
8 partition readers có thể giữ ≈ 32 MB cho pages

Chưa tính chunk/writer, JDBC buffers, JVM overhead,
object graph và các task/queue khác.
```

Những con số chỉ để nhìn xu hướng, không phải phép đo heap chính xác. Sử dụng JFR/heap profiling và metric JVM để biết lượng allocation/retained memory thực tế.

### Connection pool

Cursor thường giữ một kết nối trong thời gian step hoạt động. Nếu có 10 parallel partitions, phải tính số connection dành cho readers cùng writer transactions, monitoring và workload khác. Paging có thể linh hoạt hơn về thời gian giữ connection, nhưng mỗi truy vấn vẫn cần connection và có thể tạo nhiều request vào DB.

Không nên tăng số partition vượt quá giới hạn connection pool hoặc khả năng xử lý của database rồi cho rằng throughput sẽ tuyến tính theo số worker.

## 17. Query performance: một query dài hay nhiều page query?

Giả sử có 5 triệu bản ghi, mỗi trang 1.000 item:

- Cursor có thể thực thi một query và fetch theo nhiều lượt từ result set.
- Paging cần khoảng 5.000 truy vấn page (số thực tế tùy filter, restart và cách sinh SQL).
- Từng page query có thể tận dụng index để lấy một vùng dữ liệu nhanh.
- Nếu query chứa JOIN, GROUP BY hay sort đắt, paging có thể phải lặp chi phí thực thi nhiều lần.
- Nếu cursor query giữ server resources lâu hoặc kết nối thiếu ổn định, chi phí recovery có thể vượt lợi ích của việc ít query.

Cần đo:

| Chỉ số | Cursor | Paging |
| --- | --- | --- |
| Tổng thời gian job | Đo | Đo |
| Items/second | Đo | Đo |
| Số SQL executions | Đo | Đo |
| Thời gian trung bình/p95 query | Đo | Đo |
| Số connection mở và thời gian giữ | Đo | Đo |
| CPU/IO/read buffers ở DB | Đo | Đo |
| Heap peak và GC time | Đo | Đo |
| Số lần timeout/failure | Đo | Đo |
| Thời gian restart sau lỗi | Đo | Đo |

Không lấy chỉ một metric “rows per second” làm cơ sở kết luận nếu reader nhanh nhưng writer hoặc database chịu quá nhiều tải.

### EXPLAIN và index

Với paging:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, business_date, amount
FROM sales_order
WHERE business_date = DATE '2026-11-15'
  AND order_id > 100000
ORDER BY order_id
LIMIT 500;
```

Đây là truy vấn keyset minh họa, không nhất thiết là SQL chính xác do mọi `PagingQueryProvider` sinh ra. Để phân tích chính xác Spring Batch query, bật SQL logging hoặc capture query thật từ datasource/proxy, rồi dùng chính query đó để kiểm tra execution plan.

Index phù hợp cần xét:

- Điều kiện lọc equality/range.
- Thứ tự sort key.
- Cardinality và phân bố dữ liệu.
- Selectivity theo ngày/tenant.
- Số cột truy vấn và khả năng index-only scan.
- Nhu cầu cập nhật bảng, vì index nhiều cũng tăng chi phí write.

## 18. Parallel processing và partitioning

Cả `JdbcCursorItemReader` và `JdbcPagingItemReader` đều **không mặc định thread-safe** khi cùng một instance reader được gọi đồng thời từ nhiều thread.

Với yêu cầu song song, một mô hình rõ ràng là **partition dữ liệu** theo khoảng khóa, sau đó tạo một reader riêng cho mỗi StepExecution:

```text
                         Manager Step
                              |
             +----------------+----------------+
             |                |                |
          Partition A      Partition B      Partition C
          ID 1..100k       ID 100k..200k    ID 200k..300k
             |                |                |
          Reader A         Reader B         Reader C
             |                |                |
          Chunks            Chunks           Chunks
             |                |                |
             +----------------+----------------+
                              |
                       Output / Aggregation
```

Mỗi partition nhận identifying/range parameters trong step execution context và có reader state riêng. Cần tránh chồng lấn hoặc bỏ khoảng, bảo đảm logic WHERE tương ứng và writer idempotent.

### Nếu cần multi-threaded step

Có thể đồng bộ truy cập reader bằng wrapper phù hợp trong một số thiết kế, nhưng thao tác đồng bộ hóa có thể hạn chế throughput; state/restart trong một step đa luồng cần xem xét kỹ. Không đơn giản gắn nhiều thread vào một JDBC ResultSet hoặc một reader có mutable state.

Một lý do paging hay được chọn cho partition là có thể truy vấn từng vùng khóa và tạo reader độc lập mà không giữ một cursor đơn dùng chung. Cursor cũng có thể chạy riêng trong mỗi partition; phải tính số cursor/kết nối DB đồng thời.

## 19. Transaction isolation và độ nhất quán: ba lựa chọn mẫu

### Phương án A — Nguồn bất biến theo kỳ

**Dữ liệu:** bảng snapshot đã chốt vào cuối ngày.

**Lựa chọn:** cursor hoặc paging đều có thể phù hợp. Nếu query đọc tuần tự và driver stream tốt, cursor đơn giản. Nếu cần nhiều partition hoặc connection không được giữ lâu, paging hợp lý.

**Restart:** an toàn hơn vì dữ liệu và thứ tự không đổi, nhưng writer vẫn cần idempotency.

### Phương án B — Nguồn vận hành còn thay đổi

**Dữ liệu:** bảng đơn hàng liên tục có insert/update/delete.

**Lựa chọn:** không chọn thuần theo cursor/paging trước khi giải quyết consistency. Cần snapshot, watermark có điều kiện, claiming hoặc mô hình CDC/work queue phù hợp.

**Restart:** checkpoint chỉ đúng nếu tập dữ liệu tương ứng không đổi; cần kiểm tra source version.

### Phương án C — Lưu lượng lớn và thời gian job dài

**Dữ liệu:** hàng chục triệu record, process mất vài giờ, database có connection lifetime giới hạn.

**Lựa chọn:** paging/partitioning theo khóa thường thuận tiện hơn để tránh một cursor dài duy nhất. Nhưng phải kiểm tra số query, index và DB load.

**Restart:** checkpoint theo từng partition và nguồn ổn định; không để một failure lặp lại gây duplicate trên bảng đích.

## 20. Ví dụ chọn reader theo property cấu hình

Để so sánh hai reader trên cùng logic nghiệp vụ, bạn có thể dùng hai profile hoặc cấu hình điều kiện. Ví dụ Spring Boot:

```yaml
app:
  batch:
    reader: paging
    page-size: 500
    chunk-size: 200
```

Khi chạy benchmark:

```yaml
app:
  batch:
    reader: cursor
    fetch-size: 500
    chunk-size: 200
```

Trong implementation, mỗi cấu hình reader được đăng ký có điều kiện bằng `@ConditionalOnProperty` hoặc các profile riêng; step inject một reader đúng loại. Hãy bảo đảm **Job/Step/Reader name và metadata restart** được quản lý có chủ đích khi chuyển giữa hai chiến lược.

Điểm đặc biệt quan trọng: **Không đổi cursor sang paging giữa chừng trong cùng một JobInstance FAILED rồi mặc định checkpoint reader cũ còn tương thích.** Hai reader có cách lưu trạng thái khác nhau và thứ tự/truy vấn có thể khác. Khi cần chuyển chiến lược cho một kỳ đang dở, phải có quy trình migration/restart được kiểm chứng, hoặc tạo lượt reprocess có kiểm soát sau khi đối soát dữ liệu đích.

## 21. Một ma trận quyết định thực tế

Hãy chấm các đặc điểm theo nhu cầu hệ thống thay vì dùng công thức cứng:

| Đặc điểm workload | Cursor | Paging |
| --- | --- | --- |
| Một lượt đọc tuần tự trên snapshot | **Cân nhắc mạnh** | Cũng phù hợp |
| Query nặng và tốn chi phí thực thi lại | **Có lợi thế tiềm năng** | Kiểm tra chi phí mỗi page |
| Connection dài dễ timeout | Có rủi ro | **Thường thuận tiện hơn** |
| Nhiều partition độc lập | Mỗi partition cần cursor/connection | **Dễ tổ chức theo vùng khóa** |
| Bảng có unique key/index tốt | Có lợi cho thứ tự/restart | **Quan trọng cho sortKeys và performance** |
| Không có khóa sắp xếp duy nhất | Cursor có thể đọc một thứ tự, nhưng restart vẫn rủi ro | **Khó bảo đảm paging chính xác** |
| Nguồn thay đổi liên tục | Cần snapshot/isolation | Cần snapshot/keyset/work claiming |
| Cần tuning số query và chunk riêng | Fetch size và chunk size | Page size và chunk size |
| Bài toán nhỏ, ít bản ghi | Chọn theo độ đơn giản | Chọn theo độ đơn giản |
| Hạ tầng JDBC stream ResultSet kém | Có thể buffer nhiều/timeout | **Có thể thích hợp hơn** |
| Cần restart chính xác | Nguồn ổn định và state | Nguồn ổn định, sort key unique và state |

### Một quy tắc chọn nhanh

- **Chọn cursor để thử nghiệm trước** khi có nguồn snapshot bất biến, một luồng xử lý tuần tự, query tương đối nặng và JDBC streaming hoạt động tốt.
- **Chọn paging để thử nghiệm trước** khi có unique sort key/index, job dài, connection lifetime hạn chế, hoặc muốn partition độc lập.
- **Chưa chốt reader** khi nguồn liên tục thay đổi và chưa có định nghĩa về snapshot/consistency. Trước hết giải bài toán “mỗi kỳ phải xử lý chính xác những row nào?”.

Đây là gợi ý định hướng benchmark, không phải bảo đảm phương án nào luôn tốt nhất.

## 22. Kiểm thử hành vi của hai reader

Một phép so sánh có giá trị cần kiểm tra **đúng dữ liệu** trước khi đo tốc độ.

### 22.1. Dataset có kiểm soát

Chuẩn bị dữ liệu cho ngày D:

```text
order_id: 1, 2, 3, ..., 1.005
businessDate: D
```

Cấu hình:

```text
chunkSize = 200
cursorFetchSize = 500
pagingPageSize = 500
```

Yêu cầu:

- Cả hai reader đều đọc đúng 1.005 order.
- Mỗi order ID xuất hiện đúng một lần ở kết quả nghiệp vụ.
- Thứ tự tăng theo khóa hoặc theo yêu cầu nghiệp vụ.
- Batch cuối chưa đầy 200 item vẫn được xử lý.
- Số đọc/ghi và trạng thái `StepExecution` phù hợp.

### 22.2. Các tình huống kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Nguồn rỗng | Reader trả `null` khi hết, job hoàn tất theo policy |
| Một record | Đúng một item, không lỗi ranh giới trang |
| 499, 500, 501 records | Không mất/lặp ở trang size 500 |
| 999, 1.000, 1.001 records | Đúng ở ranh giới nhiều trang |
| Query có NULL/key trùng ở sort columns | Phát hiện hoặc ngăn thiết kế sort không unique |
| Commit chunk và cursor còn đang mở | Cursor tiếp tục đọc bình thường trên driver mục tiêu |
| Writer fail tại chunk thứ ba | Restart theo checkpoint, output không duplicate |
| Thêm row trước vị trí đã đọc | Chứng minh behavior và rủi ro consistency |
| Xóa/cập nhật row giữa các trang | Kiểm tra chính sách snapshot/watermark |
| Database/proxy ngắt connection giữa job | Exception và recovery được xử lý rõ |
| 4–8 partitions | Không chồng/lệch range, tổng output đúng |
| Dữ liệu chứa large text/JSON | Heap và GC trong giới hạn |
| Một ngày có 0 row, ngày khác rất nhiều | Không bị logic tính tham số hoặc sort sai |

Với test cập nhật dữ liệu đồng thời, nên dùng synchronization như `CountDownLatch` để kiểm soát chính xác thời điểm đang đọc trang/chunk; tránh chờ `Thread.sleep` và hy vọng event xảy ra đúng lúc.

### 22.3. Integration test với database thật

Đối với paging SQL, hành vi có thể phụ thuộc database dialect. Hãy test với PostgreSQL nếu production dùng PostgreSQL (ví dụ sử dụng Testcontainers hoặc môi trường test riêng), thay vì kết luận từ H2 rằng mọi SQL và isolation sẽ giống production.

Các assertion nên đo cả **số hàng thực trong bảng đích** và **danh sách business keys**, không chỉ `readCount`. Khi retry/rollback, reader có thể gọi lại một phần, nên kiểm tra dữ liệu cuối được commit.

## 23. Benchmark hiệu năng có thể tin cậy

Hãy benchmark cursor và paging trên cùng tập dữ liệu, cùng processor/writer và cùng điều kiện hạ tầng.

### Quy trình gợi ý

1. Chuẩn bị một snapshot có số row, kích thước và phân bố dữ liệu đại diện.
2. Khởi tạo database statistics/index phù hợp; cố định cấu hình kết nối.
3. Chạy warm-up và một số lần đo cho mỗi phương án.
4. Cố định `chunkSize` ban đầu, thay riêng `fetchSize` hoặc `pageSize`.
5. Đo throughput tổng thể và số query.
6. Đo CPU/IO/lock waits/connection usage tại database.
7. Đo heap peak, allocation rate, GC pauses và số threads ở JVM.
8. Lặp lại với mức concurrency mục tiêu và trong điều kiện restart sau lỗi.
9. So sánh số lượng/khóa/kết quả đầu ra để chắc rằng hai phương án xử lý cùng dữ liệu.
10. Ghi nhận cấu hình, environment, phiên bản JVM, Spring Batch, driver và database.

### Bảng kết quả minh họa

| Chỉ số | Cursor (giả lập) | Paging (giả lập) |
| --- | ---: | ---: |
| Dữ liệu | 2.000.000 item | 2.000.000 item |
| Tổng thời gian | 420 giây | 450 giây |
| Throughput | ~4.762 item/s | ~4.444 item/s |
| JDBC query executions | 1 truy vấn chính | ~4.000 truy vấn trang |
| Thời gian giữ kết nối reader | Dài | Theo từng query/page |
| Peak heap | 1,1 GB | 1,0 GB |
| Số lỗi/timeout | 0 | 0 |
| Đầu ra đúng | Có | Có |

**Toàn bộ số liệu trong bảng là giả lập để minh họa cách báo cáo**, không phải benchmark hay lời khẳng định cursor hơn paging. Trên workload khác, paging có thể nhanh hơn rõ rệt, nhất là khi có partition hoặc cursor phải restart vì connection timeout.

Cũng không nên lấy một lần chạy duy nhất làm kết luận: JIT warm-up, cache DB, network, tải nền và query plan có thể gây sai lệch lớn.

## 24. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Cursor chiếm heap rất nhiều | Driver buffer toàn bộ ResultSet, fetchSize không hiệu lực | Kiểm tra driver/autocommit/fetch behavior; profiling |
| Cursor timeout khi job dài | Kết nối/result set tồn tại quá lâu | Tuning timeout phù hợp hoặc chuyển paging |
| Cursor restart bỏ/lặp row | Query/tập dữ liệu thay đổi sau checkpoint | Snapshot nguồn, sort/order ổn định |
| Paging mất row cuối trang | Sort key không duy nhất | Dùng khóa sắp xếp kết hợp duy nhất |
| Paging chậm dần | OFFSET sâu, sort tốn kém hoặc thiếu index | Kiểm tra SQL thật, kế hoạch query và keyset/index |
| Paging đọc lại cùng record | Mutation trước trang tiếp hoặc sort key bị đổi | Snapshot/immutable sort key |
| Đọc `WHERE status='READY'` rồi writer đổi status | Tập lọc thay đổi trong khi đọc | Snapshot, claiming hoặc pipeline tách nguồn |
| Bảng nhỏ nhưng cấu hình quá phức tạp | Tối ưu trước khi đo | Chọn phương án dễ bảo trì |
| Page size lớn gây OOM | Page buffer, chunk và writer cùng giữ item | Giảm size; profile retained heap |
| Tăng concurrency mà job chậm hơn | DB/connection pool bị bão hòa | Giới hạn partition và đo DB metrics |
| Reader chạy sai khi multithread | Chia sẻ reader không thread-safe | Reader riêng theo partition |
| Restart sau khi đổi reader thất bại | ExecutionContext cũ không tương thích | Quy trình migration/reprocess có kiểm soát |
| Duplicate ở bảng đích sau restart | Writer không idempotent, checkpoint không đủ | Unique key, upsert, outbox |
| Chạy được test H2 nhưng lỗi production | Dialect, isolation hoặc cursor behavior khác | Test với database production-compatible |
| Nhầm pageSize và chunkSize | Tuning sai mục tiêu | Tách read I/O/page buffer khỏi write transaction chunk |
| Nhầm API cursor token với JDBC cursor | Thiết kế state/lifetime sai | Xác định protocol nguồn dữ liệu thật |
| Không thấy lỗi nhưng thiếu 1% dữ liệu | Chỉ kiểm `BatchStatus.COMPLETED` | Đối soát keys/counts theo snapshot |
| Query có thứ tự không xác định | Không có `ORDER BY`/unique sort | Định nghĩa deterministic total order |

## 25. Bài tập thực hành

Tạo `importOrdersJob` đọc 100.000 đơn hàng từ bảng `sales_order` theo một `businessDate` đã chốt:

1. Viết một phiên bản dùng `JdbcCursorItemReader`, cấu hình `fetchSize=500`, tên reader và `saveState(true)`.
2. Viết một phiên bản dùng `JdbcPagingItemReader` với `pageSize=500` và sort key duy nhất.
3. Cùng một processor tính một phí xử lý đơn giản; writer ghi vào bảng `order_summary` có khóa duy nhất theo business date và order ID.
4. Thử chunk size 100, 200 và 500; đo thời gian chạy, read/write counts, peak heap, GC và số truy vấn.
5. Làm writer thất bại sau khi hai chunk đã commit; restart và đối chiếu dữ liệu đích để xác minh không duplicate.
6. Thêm một record vào nguồn giữa hai trang, sau đó xóa một record phía trước vị trí đọc. So sánh hành vi của hai reader và giải thích vì sao snapshot là điều kiện cần cho chính xác.
7. Thử cách đọc dữ liệu có sort key không duy nhất rồi sửa bằng khóa kết hợp.
8. Thực hiện partition theo ID range, mỗi partition có reader riêng; kiểm tra tổng số order được xử lý và số connection đồng thời.
9. Viết báo cáo chọn cursor hoặc paging cho môi trường có connection lifetime 30 phút và job dự kiến chạy 2 giờ. Nêu các điều kiện cần kiểm chứng bằng benchmark.

Báo cáo nên có phần **tính đúng đắn**, **tài nguyên**, **throughput**, **restart**, **rủi ro nguồn thay đổi** và **quyết định cuối cùng kèm bằng chứng**. Không chọn chỉ dựa trên phương án chạy nhanh hơn vài giây trong một lần test.

## 26. Tổng kết

Chọn **cursor hay paging** trong Spring Batch là quyết định cân bằng giữa số lần truy vấn, lifetime của connection, buffer bộ nhớ, chiến lược transaction, khả năng mở rộng và độ tin cậy khi restart.

- **Cursor** phù hợp để cân nhắc cho luồng đọc tuần tự dài trên nguồn ổn định, đặc biệt khi query tốn kém và JDBC driver thực sự hỗ trợ fetch theo đợt. Đổi lại, cursor/result set có thể giữ tài nguyên trong thời gian dài.
- **Paging** phù hợp khi có unique sort key và index tốt, cần chia dữ liệu theo partition hoặc không muốn giữ cursor lâu. Đổi lại, nó có nhiều truy vấn và phải cẩn thận khi nguồn biến đổi giữa các trang.
- **Cả hai đều cần thiết kế nguồn ổn định, checkpoint đúng, writer idempotent và kiểm thử restart**. Không có reader nào tự động bảo đảm exactly-once khi dữ liệu nguồn thay đổi và hệ thống đích có side effect ngoài transaction.

Quy trình quyết định đáng tin cậy là: xác định tập bản ghi nghiệp vụ và yêu cầu consistency → kiểm tra index/driver/connection policy → triển khai cấu hình reader phù hợp → đo throughput và tài nguyên trên dữ liệu thật → kiểm chứng restart và đầu ra. Mục tiêu cuối cùng không chỉ là đọc nhanh, mà là **xử lý đúng, có thể phục hồi và vận hành ổn định**.
