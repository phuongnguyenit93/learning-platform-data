# Chọn reader database hay file trong Spring Batch

## 1. Bài toán thiết kế

Một dự án Spring Batch thường bắt đầu bằng câu hỏi: “Dữ liệu cần xử lý nằm ở đâu?”. Nếu dữ liệu đang ở bảng SQL, nhiều nhóm chọn `JdbcCursorItemReader` hoặc `JdbcPagingItemReader`. Nếu đối tác giao một file CSV qua SFTP, nhóm khác chọn `FlatFileItemReader`. Nhưng quyết định **chọn reader database hay file** không chỉ phụ thuộc nơi dữ liệu xuất hiện ban đầu.

Giả sử job đối soát phải xử lý 8 triệu giao dịch mỗi đêm. Dữ liệu hiện nằm ở PostgreSQL; một hệ thống khác cũng có thể xuất CSV theo ngày. Cả hai cách đều có thể đưa vào `ItemProcessor` và `ItemWriter`, nhưng chúng khác nhau về tính nhất quán, tải database, khả năng kiểm toán, restart, quyền truy cập, độ trễ và cách vận hành khi dữ liệu thay đổi trong lúc job chạy.

Đây là bài thuộc *Spring Batch Core Processing → Quyết định thiết kế*. Mục tiêu là giúp bạn chọn nguồn đọc có thể **đáp ứng yêu cầu nghiệp vụ và vận hành một cách có chứng cứ**, thay vì mặc định “file nhanh hơn” hoặc “database hiện đại hơn”.

Sau bài này, bạn có thể:

- Phân biệt `JdbcCursorItemReader`, `JdbcPagingItemReader`, `JpaPagingItemReader`, `FlatFileItemReader` và `MultiResourceItemReader`.
- Đánh giá **tính ổn định của snapshot**, khả năng restart, checkpoint và tránh đọc thiếu/trùng.
- So sánh tải database, bộ nhớ JVM, I/O, độ trễ, chi phí vận hành và tính độc lập giữa các hệ thống.
- Cấu hình reader database/file với Spring Batch 5.x, `JobParameters` và `@StepScope`.
- Chọn chunk size, page size, fetch size và partition strategy phù hợp.
- Thiết kế kiểm thử cho dữ liệu thay đổi, file bị sửa, crash, restart và lỗi schema/encoding.
- Viết một **Architecture Decision Record (ADR)** cho lựa chọn reader.

Mã ví dụ dùng **Java 17+, Spring Boot 3.x và Spring Batch 5.2.x**. Các khái niệm vẫn hữu ích ở Spring Batch 6.x, nhưng một số package/API có thể khác; hãy xem tài liệu đúng phiên bản trước khi copy code.

---

## 2. Quyết định đầu tiên: dữ liệu gốc là gì và ai sở hữu nó?

Trước khi nhìn tên class reader, xác định tính chất nguồn dữ liệu.

| Câu hỏi | Nếu câu trả lời là database | Nếu câu trả lời là file |
|---|---|---|
| Ai sở hữu dữ liệu? | Service/database đang phục vụ giao dịch | Đối tác hoặc quy trình xuất snapshot |
| Nguồn có thay đổi khi batch chạy không? | Có thể có insert/update/delete đồng thời | Có thể bất biến sau lúc publish nếu hợp đồng tốt |
| Dữ liệu được chọn theo điều kiện nào? | SQL filter, join, cutoff, partition | Tên file, manifest, header, kỳ dữ liệu |
| Cần tái chạy cùng một snapshot? | Cần snapshot/version/điều kiện cố định | Dễ hơn nếu giữ nguyên file + checksum |
| Nguồn chịu thêm tải được không? | Phải hỏi DBA/SRE và đo | Phải bảo đảm storage/network/định dạng |
| Truy cập bị giới hạn thế nào? | SQL account, row-level policy, schema quyền | SFTP/bucket ACL, encryption, expiry |
| Dữ liệu phải có ngay? | Gần real-time nếu đã commit | Phụ thuộc thời gian tạo và chuyển file |
| Cần audit nguồn chính xác? | Query + snapshot/version + parameters | Immutable file ID, checksum, manifest |
| Cần phân phối cùng dữ liệu cho nhiều bên? | Mỗi bên query riêng, có thể gây tải | Một snapshot có thể được chia sẻ có kiểm soát |
| Lỗi xảy ra giữa chừng? | Cursor/page checkpoint và consistency | File path/position checkpoint, yêu cầu file bất biến |

**Điều quan trọng nhất là hợp đồng dữ liệu.** Một reader “đọc tốt” không thể sửa được vấn đề nguồn liên tục thay đổi khiến tập bản ghi mất tính nhất quán. Ngược lại, file chỉ thật sự có lợi thế snapshot khi bên gửi bảo đảm file đã hoàn chỉnh, không bị sửa trong lúc và sau khi consumer bắt đầu xử lý.

### 2.1. Bốn kiểu nguồn dữ liệu phổ biến

1. **Database giao dịch đang hoạt động (OLTP):** dữ liệu thay đổi liên tục; query batch có thể ảnh hưởng latency của ứng dụng.
2. **Database replica/warehouse hoặc bảng staging:** phù hợp với những truy vấn đọc lớn nếu có cơ chế snapshot/cutoff rõ ràng.
3. **File snapshot bất biến:** dữ liệu được chốt theo kỳ rồi xuất thành một hoặc nhiều file, có manifest/checksum.
4. **File đang được ghi hoặc API xuất file tạm thời:** chỉ có thể dùng an toàn sau khi được “đóng” và xác nhận hoàn tất.

Mô hình thứ ba thường dễ tái chạy, nhưng có chi phí tạo snapshot, storage và thời gian truyền file. Mô hình thứ hai thường linh hoạt cho filter và có thể tránh copy, nhưng phải kiểm soát isolation, lock và độ ổn định khóa sắp xếp.

---

## 3. Kiến trúc reader trong Spring Batch

Spring Batch dùng giao diện `ItemReader<T>`:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Mỗi lần `read()` trả về một item hoặc `null` nếu đã hết dữ liệu. Đối với reader hỗ trợ restart, giao diện `ItemStream` bổ sung `open`, `update` và `close`.

```text
Job
 │
 ▼
Step (chunk-oriented)
 │
 ├── ItemReader.read()
 │      ├── JDBC cursor/paging/JPA
 │      └── flat file/multi-file
 │
 ├── ItemProcessor.process()
 │
 └── ItemWriter.write(Chunk)
          │
          ▼
     Transaction commit
     + ItemStream checkpoint
          │
          ▼
       JobRepository
```

Nhờ abstraction này, nhiều pipeline có thể **giữ nguyên processor và writer**, chỉ thay reader. Tuy nhiên, hai reader không tự tương đương về thứ tự, dữ liệu đầu vào hay khả năng restart.

### 3.1. Reader không phải transaction coordinator

`FlatFileItemReader` có thể ghi lại vị trí dòng để restart, nhưng đọc file không được rollback cùng database. `JdbcCursorItemReader` đọc qua JDBC connection/cursor với cấu hình transaction riêng; không nên giả định mọi query/reader đều chạy trong cùng transaction với writer. Một batch commit thành công chỉ ghi nhận chunk và metadata theo cấu hình, không tạo snapshot mới của nguồn.

Ví dụ một job đọc database nguồn A, xử lý rồi ghi database B:

```text
Source DB A               Spring Batch              Target DB B
    │                          │                         │
    ├──── SELECT rows ────────►│                         │
    │                          ├──── write/commit ──────►│
    │                          │                         │
    └── source vẫn có thể bị update/delete đồng thời      │
```

Nếu A và B không chia sẻ transaction có ý nghĩa, việc commit ở B không khóa trạng thái nguồn tại A. Tương tự, đọc file đã thay đổi vị trí dữ liệu có thể khiến checkpoint theo dòng không còn đúng.

---

## 4. Bảng so sánh nhanh

| Tiêu chí | Database reader | File reader |
|---|---|---|
| Độ mới dữ liệu | Có thể gần dữ liệu commit mới nhất | Phụ thuộc chu kỳ snapshot/export |
| Chọn lọc dữ liệu | SQL WHERE/JOIN/partition thuận lợi | Thường phải quét hoặc dùng manifest/index riêng |
| Tải lên hệ giao dịch | Có nguy cơ query nặng, cursor/connection dài | Giảm tải đọc trực tiếp DB sau khi snapshot xong |
| Tái chạy đúng tập dữ liệu | Phải kiểm soát snapshot/version/biến động | Dễ hơn nếu file bất biến và được giữ lại |
| Restart | Cursor/page/checkpoint; phụ thuộc ổn định query/sort | Position/resource; phụ thuộc byte/line/file order không đổi |
| Tính nhất quán | Isolation, snapshot, high-water mark, CDC | File hoàn tất/manifest, checksum, schema version |
| Bộ nhớ | Phụ thuộc fetch/page size, driver, JPA graph | Phụ thuộc line/parser, không cần load toàn bộ file |
| I/O | DB connection, network SQL, paging | File system/object store/SFTP, disk/network |
| Chạy song song | Partition theo ID/range, query theo khóa | Partition theo file, byte range với định dạng hỗ trợ |
| Audit | Cần ghi query, filter, snapshot ID | File ID/checksum/manifest là bằng chứng thuận tiện |
| Dữ liệu cực lớn | Cần đánh giá khả năng chịu tải của DB | Có thể dễ chia file, nhưng chi phí export/storage |
| Security | DB roles, row/column permission | ACL, encryption at rest/in transit, key lifecycle |
| Schema thay đổi | DB schema migrations, query mapping | Header/layout/versioning, backward compatibility |
| Lỗi nguồn | Timeout, deadlock, replica lag, cursor lost | File missing, corrupt, truncated, wrong encoding |
| Nhiều consumer | Nhiều query DB có thể lặp tải | Dùng cùng snapshot file có kiểm soát |
| Xóa/retention | Chính sách bảng/snapshot | Chính sách object version, file archive và cleanup |

Đây là **khuynh hướng**, không phải kết luận tuyệt đối. File nằm trên network storage kém có thể chậm hơn database. Một DB replica được tối ưu cho analytics có thể cung cấp snapshot ổn định và throughput tốt hơn pipeline xuất file tạm. Cần đo hệ thống thật.

---

## 5. Nhánh database: cursor, paging và JPA

### 5.1. JdbcCursorItemReader

`JdbcCursorItemReader` dùng JDBC `ResultSet` như một con trỏ đọc tuần tự. Khi `read()` được gọi, reader lấy hàng tiếp theo và ánh xạ qua `RowMapper`.

```text
Database:
  SELECT id, amount FROM orders WHERE ...
         │
         ▼
     JDBC ResultSet / cursor
         │
         ├── row #1 → read()
         ├── row #2 → read()
         ├── row #3 → read()
         └── ... đến hết
```

**Khi đáng cân nhắc:**

- Query có tập kết quả lớn, cần đọc tuần tự.
- Database/driver hỗ trợ cursor/streaming hợp lý.
- Không cần phân trang theo từng request.
- Có thể giữ connection và cursor theo thời gian xử lý.
- Cần mapping dữ liệu đơn giản, ít ORM overhead.

**Rủi ro:**

- Cursor/connection sống lâu; nếu processor/writer chậm, tài nguyên có thể bị giữ nhiều giờ.
- Driver có thể buffer toàn bộ `ResultSet` nếu không cấu hình streaming đúng.
- Query lớn có thể tranh chấp CPU/IO với OLTP.
- Khi connection bị mất, phải restart reader/job theo cơ chế hỗ trợ, không luôn resume được cursor vật lý.
- Tập dữ liệu thay đổi trong lúc query có thể ảnh hưởng theo isolation/snapshot của DB.

Ví dụ cấu hình Spring Batch 5.x:

```java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> cursorOrderReader(
        DataSource dataSource,
        @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

    if (cutoffId == null) {
        throw new IllegalArgumentException("cutoffId required");
    }

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("cursorOrderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, customer_id, amount
                FROM source_orders
                WHERE id <= ?
                ORDER BY id
                """)
            .preparedStatementSetter(ps -> ps.setLong(1, cutoffId))
            .rowMapper((rs, rowNum) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .build();
}
```

Các import chính:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
```

`OrderRow` là model sẽ được khai báo ở phần ví dụ hoàn chỉnh bên dưới.

**Lưu ý:** `fetchSize(500)` là hint cho JDBC driver, **không phải giới hạn memory cứng**. Với một số driver cần tắt autocommit hoặc bật chế độ stream/cursor cụ thể. Hãy xem behavior thực của PostgreSQL/MySQL/Oracle/JDBC driver trong môi trường đang dùng; không suy từ mỗi dòng config.

### 5.2. JdbcPagingItemReader

`JdbcPagingItemReader` thay vì giữ một cursor truy vấn lâu dài sẽ thực hiện nhiều query lấy từng trang. Mỗi trang chứa số dòng xấp xỉ `pageSize`, sau đó reader trả từng item khi `read()` được gọi.

```text
Query page #1 → [row 1 ... row 500]
                         │
                     read() từng row
                         │
Query page #2 → [row 501 ... row 1000]
                         │
                     read() từng row
                         ▼
                     hết dữ liệu
```

**Điều kiện quan trọng:** khóa sắp xếp phải **duy nhất và ổn định**. Tài liệu Spring Batch lưu ý cần unique sort key để không mất dữ liệu khi restart. Reader dùng giá trị sort key đã lưu để định vị lại khi tiếp tục, nhưng điều này **không tự tạo snapshot nhất quán** nếu nguồn thay đổi.

Ví dụ tạo `PagingQueryProvider` cho bảng có khóa chính `id`:

```java
@Bean
PagingQueryProvider orderPagingQueryProvider(DataSource dataSource)
        throws Exception {

    SqlPagingQueryProviderFactoryBean factory =
            new SqlPagingQueryProviderFactoryBean();

    factory.setDataSource(dataSource);
    factory.setSelectClause("SELECT id, customer_id, amount");
    factory.setFromClause("FROM source_orders");
    factory.setWhereClause("WHERE id <= :cutoffId");
    factory.setSortKey("id");
    factory.afterPropertiesSet();

    return factory.getObject();
}
```

Reader:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> pagedOrderReader(
        DataSource dataSource,
        PagingQueryProvider orderPagingQueryProvider,
        @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

    if (cutoffId == null) {
        throw new IllegalArgumentException("cutoffId required");
    }

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("pagedOrderReader")
            .dataSource(dataSource)
            .queryProvider(orderPagingQueryProvider)
            .parameterValues(Map.of("cutoffId", cutoffId))
            .rowMapper((rs, n) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Import tương ứng:

```java
import java.util.Map;

import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.PagingQueryProvider;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.batch.item.database.support.SqlPagingQueryProviderFactoryBean;
```

`SqlPagingQueryProviderFactoryBean` tạo SQL phân trang theo dialect database. Việc có `ORDER BY id` ổn định là thiết yếu. Index phù hợp với predicate/sort giúp hạn chế full scan khi dữ liệu lớn.

**Khi nên cân nhắc paging:** chạy lâu, muốn đọc theo query ngắn, cần dễ chia partition theo ID, có sort key duy nhất, database hỗ trợ paging hiệu quả.

**Rủi ro paging:**

- Mỗi page query là một lần truy vấn mới, có thể thấy dữ liệu thay đổi giữa các trang.
- Nếu predicate dựa vào trạng thái `status='NEW'` mà writer chuyển status thành `PROCESSED`, tập kết quả bị biến đổi. Spring Batch JDBC paging với sort-key checkpoint có thể tránh một số lệch offset, nhưng **không bảo đảm** mọi chiến lược cập nhật/lọc đều không mất dữ liệu.
- Sort key không duy nhất hoặc bị chỉnh sửa gây rủi ro đọc thiếu/trùng.
- Page size quá lớn làm tăng memory; page size quá nhỏ tăng DB round trip.
- Khi dùng multi-threaded reader, khả năng dùng `saveState` và thread safety cần được thiết kế tường minh; không giả định dùng cùng một instance reader trên nhiều thread là restart-safe.

### 5.3. Cursor hay paging?

| Câu hỏi | Cursor | Paging |
|---|---|---|
| Số query chính | Một query/ResultSet kéo dài | Nhiều query theo trang |
| Giữ connection/cursor | Thường có, kéo dài | Mỗi lần fetch page, tùy datasource |
| Phụ thuộc driver streaming | Cao | Thường rõ hơn theo page |
| Đọc tuần tự tập kết quả lớn | Thuận tiện | Thuận tiện nếu khóa/page ổn định |
| Snapshot query thống nhất | Tùy isolation và DB | Khó hơn vì nhiều query khác thời điểm |
| Khả năng phân vùng theo ID | Có thể thiết kế, nhưng mỗi cursor riêng | Thường thuận tiện |
| Restart | Khôi phục vị trí theo state/count | Dùng sort key/state theo reader |
| DB round-trip | Ít query nhưng connection lâu | Nhiều query |
| Workload và query planner | Một truy vấn dài | Nhiều truy vấn nhỏ, index quan trọng |

Đừng mặc định paging “luôn tốt hơn cursor”. Với database đã hỗ trợ cursor server-side, một truy vấn đọc tuần tự trên replica có thể rất hiệu quả. Với nhiều giờ xử lý và giao tiếp qua network không ổn định, paging có thể quản lý tài nguyên dễ hơn. Benchmark và requirement về consistency quyết định.

### 5.4. JpaPagingItemReader

`JpaPagingItemReader` phù hợp khi dự án dùng JPA và muốn ánh xạ entity theo JPQL. Ví dụ:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderEntity> jpaOrderReader(
        EntityManagerFactory emf) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("jpaOrderReader")
            .entityManagerFactory(emf)
            .queryString("""
                select o
                from OrderEntity o
                order by o.id
                """)
            .pageSize(500)
            .build();
}
```

Các reader JPA có hành vi quản lý persistence context theo page; trong Spring Batch 5.x, `JpaPagingItemReader` clear persistence context/detach các entity sau mỗi page. Dù vậy, các quan hệ lazy/eager vẫn có thể tạo object graph lớn hoặc N+1 query nếu processor truy cập sâu.

**Khi dùng JDBC thay vì JPA?**

- Nếu chỉ cần vài cột để tạo DTO/report, JDBC thường đơn giản và giảm overhead entity tracking.
- Nếu xử lý entity domain thực sự cần mapping/relationship và hệ thống đã có JPQL phù hợp, JPA tiện hơn.
- Nếu query có hàng triệu row và không cần thay đổi entity, một DTO projection/JDBC reader đáng cân nhắc để hạn chế memory và N+1.
- Nếu định dùng native complex SQL hoặc window function, JDBC thường dễ kiểm soát hơn.

Với JPA reader, phải phân biệt **query semantics**, persistence context, transaction và cách reader checkpoint. Đừng coi việc dùng ORM là tự có snapshot consistency hoặc restart an toàn.

---

## 6. Nhánh file: FlatFileItemReader

### 6.1. File là một Resource, không phải một bảng SQL

`FlatFileItemReader` đọc file văn bản theo dòng/record và dùng `LineMapper` ánh xạ thành item. Những thành phần chính:

- `Resource`: vị trí file (ví dụ `FileSystemResource`, `ClassPathResource`).
- `LineMapper`: chuyển dòng thành domain object.
- `LineTokenizer`: tách CSV/fixed-width.
- `FieldSetMapper`: chuyển trường sang kiểu Java.
- `encoding`: charset của input.
- `linesToSkip`: số dòng header/comment cần bỏ.
- `strict`: policy khi resource không tồn tại.

Ví dụ CSV:

```csv
id,customer_id,amount
1001,71,120.50
1002,72,0.00
1003,73,99.99
```

Reader:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> fileOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile required");
    }

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("fileOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("id", "customer_id", "amount")
            .fieldSetMapper(fs -> new OrderRow(
                    fs.readLong("id"),
                    fs.readLong("customer_id"),
                    fs.readBigDecimal("amount")))
            .build();
}
```

Imports cơ bản:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
```

**Vì sao `strict(true)`?** Với một file bắt buộc, lỗi thiếu input phải làm job fail rõ ràng. `strict(false)` có thể chấp nhận resource không tồn tại và reader coi như rỗng; điều đó chỉ phù hợp nếu nghiệp vụ định nghĩa input vắng mặt là hợp lệ và có giám sát riêng.

### 6.2. CSV không luôn đơn giản như split(",")

Một dòng CSV có thể có dấu phẩy trong quoted field, ký tự xuống dòng nằm trong quoted text, dấu nháy escape, BOM hoặc encoding khác UTF-8. Với format phức tạp, cấu hình `DelimitedLineTokenizer`/`RecordSeparatorPolicy` cần theo đúng hợp đồng; nếu dữ liệu có RFC 4180-like quoting, cần kiểm thử các trường hợp đặc biệt thay vì tự dùng `line.split(",")`.

Mỗi file nên có **schema version/hợp đồng** quy định:

- Encoding (UTF-8 hoặc encoding khác).
- Header có bắt buộc hay không, tên/cột và thứ tự.
- Dấu phân tách, quote/escape, newline.
- Kiểu date/time, múi giờ và decimal separator.
- Null/empty value, độ dài tối đa mỗi field.
- Chính sách reject/skip malformed record.
- Trailer row, record count và checksum nếu có.

Một file có tên đúng nhưng schema sai vẫn phải được phát hiện trước hoặc trong quá trình đọc.

### 6.3. File phải hoàn tất và bất biến

Giả sử đối tác ghi `orders.csv` vào thư mục; batch thấy file tồn tại và bắt đầu đọc trong lúc đối tác mới ghi được 60%. Reader có thể gặp EOF sớm và job hoàn tất với chỉ 60% dữ liệu.

Cần **giao thức “ready”**:

```text
Producer:
    write orders-2026-11-15.csv.tmp
              │
              ▼
        flush + close
              │
              ▼
        checksum/manifest
              │
              ▼
    atomic rename / ready marker
              │
              ▼
Consumer:
    chỉ lấy file đã READY
              │
              ▼
    xác minh fileId, size, checksum
              │
              ▼
    FlatFileItemReader
```

Trên object storage, rename có thể không phải atomic operation như local filesystem. Có thể upload object với key bất biến rồi phát hành **manifest/ready object** sau khi upload thành công. Consumer chỉ đọc những object được manifest ký/ghi nhận là hoàn tất.

### 6.4. Checksum và version

Tối thiểu nên lưu:

```text
fileId=orders-VN-2026-11-15
objectKey=incoming/orders-VN-2026-11-15-v3.csv
sizeBytes=...
sha256=...
schemaVersion=3
businessDate=2026-11-15
recordCount=...
publishedAt=...
```

`SHA-256` giúp phát hiện thay đổi byte do lỗi/tráo file **nếu giá trị checksum kỳ vọng đến từ nguồn đáng tin**. Một attacker thay cả file lẫn checksum không bị ngăn chỉ bởi hash không có chữ ký/quyền bảo vệ manifest. Với dữ liệu nhạy cảm, dùng TLS, access control, encryption và signed/authenticated manifest theo threat model.

Trên restart, cần **đọc lại cùng phiên bản file**, cùng byte, cùng cấu hình parser và thứ tự file. Không chỉ dùng wildcard hay tên `latest.csv` có thể trỏ sang object khác.

---

## 7. Nhiều file: MultiResourceItemReader

Nếu một kỳ dữ liệu gồm hàng trăm file cùng schema, `MultiResourceItemReader` có thể đọc tuần tự nhiều `Resource` thông qua delegate như `FlatFileItemReader`.

```java
@Bean
@StepScope
MultiResourceItemReader<OrderRow> multiFileReader(
        @Value("#{jobParameters['inputDirectory']}") String directory) {

    Path root = Path.of(directory).toAbsolutePath().normalize();

    Resource[] resources = resolveFrozenManifest(root);
    // resolveFrozenManifest là hàm nghiệp vụ do ứng dụng cài đặt:
    // lấy danh sách file đã READY từ manifest bất biến.

    FlatFileItemReader<OrderRow> delegate =
            new FlatFileItemReaderBuilder<OrderRow>()
                    .name("fileDelegate")
                    .encoding(StandardCharsets.UTF_8.name())
                    .strict(true)
                    .linesToSkip(1)
                    .delimited()
                    .names("id", "customer_id", "amount")
                    .fieldSetMapper(fs -> new OrderRow(
                            fs.readLong("id"),
                            fs.readLong("customer_id"),
                            fs.readBigDecimal("amount")))
                    .build();

    return new MultiResourceItemReaderBuilder<OrderRow>()
            .name("multiFileReader")
            .resources(resources)
            .delegate(delegate)
            .build();
}
```

Đây là ví dụ định hướng: `resolveFrozenManifest(root)` phải được cài đặt theo định dạng manifest và quy tắc bảo mật của dự án, trả về những `Resource` thực sự tồn tại, được phép và không đổi.

**Điểm restart rất quan trọng:** Spring Batch có cơ chế đảm bảo thứ tự resource bằng comparator; nhưng nếu trong lúc job chạy/restart bạn thêm, bớt hoặc thay file trong tập input, vị trí checkpoint có thể không còn trỏ cùng record. Vì vậy nên **đóng băng danh sách file** từ một manifest có file IDs/versions ổn định, xử lý trong thư mục riêng cho một job instance và chỉ cleanup sau khi hoàn tất.

### 7.1. Partition theo file

Khi có nhiều file độc lập, một chiến lược phổ biến là mỗi partition xử lý một file hoặc một nhóm file:

```text
Manifest: 200 files
          │
          ▼
Partitioner
  ├─ partition-1 → files 001–025
  ├─ partition-2 → files 026–050
  ├─ partition-3 → files 051–075
  └─ ...
          │
          ▼
Workers (mỗi partition có reader riêng)
          │
          ▼
Writer/output theo partition
          │
          ▼
Merge/publish khi tất cả thành công
```

Phải bảo đảm output không ghi chung không đồng bộ, partition IDs ổn định khi restart và mỗi file chỉ được xử lý một lần theo nghiệp vụ. Nếu file quá lớn nhưng chỉ có một file, có thể cân nhắc partition theo byte range **khi định dạng cho phép**; với CSV có quoted newline, chia byte tùy ý có thể cắt ngang record và gây mất dữ liệu.

---

## 8. Nhất quán dữ liệu: điểm khác biệt thường quyết định lựa chọn

### 8.1. Cùng query không chắc cùng dữ liệu qua hai lần chạy

Với database live:

```sql
SELECT id, customer_id, amount
FROM source_orders
WHERE business_date = DATE '2026-11-15'
ORDER BY id;
```

Nếu một record bị sửa sau khi page đầu đã được đọc nhưng trước khi page sau chạy, batch có thể xử lý tập kết quả pha trộn theo hai thời điểm. `ORDER BY id` chỉ bảo đảm thứ tự trong mỗi truy vấn theo DB, **không giữ nguyên nội dung của record**.

Các tùy chọn tùy mức nhất quán:

1. **High-water mark:** chốt `maxId` hoặc `updatedAt cutoff` trước job, lọc chỉ những record nằm trong phạm vi đã công bố.
2. **Snapshot/version column:** chọn version dữ liệu đã freeze.
3. **Database snapshot transaction/isolation:** dùng khả năng MVCC/snapshot của DB, nhưng cân nhắc transaction kéo dài và tải tài nguyên.
4. **Staging table:** copy khóa/dữ liệu cần xử lý vào bảng batch snapshot, sau đó đọc bảng đó.
5. **CDC/event log:** xử lý thay đổi qua stream với offset/checkpoint; phù hợp nếu yêu cầu đồng bộ liên tục hơn là snapshot nightly.
6. **Immutable exported file:** chốt dữ liệu thành file và manifest, rồi batch chỉ đọc snapshot đó.

High-water mark theo `id <= cutoffId` **chỉ chặn insert ID lớn hơn**; nó không ngăn update/delete các dòng cũ. Nếu nghiệp vụ yêu cầu đúng dữ liệu tại một instant, phải có snapshot/version thực sự hoặc một hợp đồng source “dữ liệu cũ không được sửa sau khi chốt”.

### 8.2. Paging và các điều kiện lọc thay đổi

Ví dụ query:

```sql
SELECT id, status, amount
FROM orders
WHERE status = 'NEW'
ORDER BY id;
```

Nếu chính step update `status='PROCESSED'` sau khi ghi, việc phân trang theo OFFSET trên tập `NEW` có thể bỏ qua những dòng còn lại vì tập kết quả bị thu hẹp.

`JdbcPagingItemReader` hỗ trợ checkpoint theo sort key, có thể tránh một số vấn đề của offset thuần. Tuy nhiên thiết kế vẫn cần:

- Unique, stable sort key.
- Biến đổi trạng thái không làm mất bản ghi mà reader chưa đọc.
- Đảm bảo không có process khác tạo/đổi record trong cửa sổ xử lý theo cách phá hợp đồng.
- Test với insert/update/delete đồng thời và restart.

Một hướng chắc chắn là **materialize danh sách ID cần xử lý** cho từng batch run trong bảng staging:

```sql
CREATE TABLE batch_run_items (
    run_id         VARCHAR(100) NOT NULL,
    order_id       BIGINT NOT NULL,
    PRIMARY KEY (run_id, order_id)
);
```

Khi bắt đầu, chụp danh sách ID đủ điều kiện vào bảng `batch_run_items`; reader lấy theo `run_id` và `order_id` ổn định. Nếu cần nội dung tại thời điểm chốt, phải snapshot cả những cột có thể thay đổi hoặc ghi version và truy vấn version tương ứng, không chỉ ID.

### 8.3. File snapshot không tự an toàn nếu bị thay

Với file:

```text
JobExecution A:
   read file version v1 đến dòng 1.500.000
   crash

Trong lúc downtime:
   producer thay file cùng tên bằng v2
   thêm/xóa một dòng ở đầu

Restart:
   reader tiếp tục theo vị trí dòng 1.500.001
   nhưng dòng đó thuộc dữ liệu khác
```

Thứ tự/position checkpoint không còn có nghĩa. Do đó file snapshot phải giữ nguyên version, checksum và nội dung cho đến khi job hoàn thành hoặc retention window kết thúc. Cần có manifest/immutable object key, chứ không chỉ “đường dẫn giống lần trước”.

### 8.4. Đồng nhất giữa DB, file và nghiệp vụ

Khi chuyển từ DB reader sang file reader, hãy tự hỏi:

- File chứa đúng những record SQL query từng lấy không?
- Filter theo `businessDate`, `tenant`, `status` được áp ở cùng thời điểm và cùng timezone không?
- Join từ các bảng có snapshot nhất quán không?
- Dữ liệu bị null, chuẩn hóa decimal/date có đổi không?
- Nếu file export thất bại giữa chừng, consumer có phát hiện?
- Bản ghi mới tới muộn được xử lý theo kỳ nào?

Một file CSV không tự tương đương với “SELECT ...” nếu export không có hợp đồng rõ ràng.

---

## 9. Restartability: reader lưu gì và phải bảo vệ điều gì?

### 9.1. ItemStream và ExecutionContext

Reader có state thường dùng vòng đời:

```java
open(ExecutionContext context)
read()
read()
...
update(ExecutionContext context)
close()
```

Spring Batch quản lý checkpoint tại các ranh giới phù hợp của step/transaction và lưu metadata vào `JobRepository`.

**Database cursor:** reader có thể lưu vị trí đọc; khi restart cần query có dữ liệu/thứ tự tương thích. Reader không “khôi phục lại chính connection/cursor vật lý” của lần chạy đã chết.

**Database paging:** reader lưu state và sort-key checkpoint; khi restart cần unique sort key và dataset ổn định.

**Flat file:** reader lưu vị trí dòng/record và state stream; khi restart cần cùng resource bytes, encoding và parser semantics.

**Multi-file:** cần thêm resource ordering ổn định và cùng tập input.

### 9.2. saveState(false) không phải nút tăng tốc miễn phí

`saveState(false)` có thể phù hợp khi reader được điều phối theo cách khác, nhưng tắt state của reader thường làm **mất khả năng restart tự động từ checkpoint**. Trong multi-threaded step, một số reader có lưu ý riêng về state/thread safety; không nên bật/tắt `saveState` mà chưa hiểu yêu cầu recovery.

Đừng cố giải quyết race condition bằng cách tắt checkpoint rồi chấp nhận job có thể đọc lại tất cả dữ liệu nếu ứng dụng có side effect không idempotent.

### 9.3. Identifying JobParameters

Một mô hình ổn định:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "snapshot-20261115-v1", true)
        .addString("requestedAtUtc", "2026-11-15T19:00:00Z", false)
        .toJobParameters();
```

`businessDate` và `sourceSnapshotId` tham gia định danh `JobInstance`; `requestedAtUtc` là metadata quan sát không làm mỗi retry tạo một instance mới.

Nếu một instance thất bại, khi restart phải truy cập lại **chính cùng snapshot**. Nếu snapshot đã bị xóa, không được tự lặng lẽ đọc “latest” rồi coi là restart an toàn.

### 9.4. File path không nên trỏ “latest”

Không dùng:

```text
inputFile=/data/latest.csv
```

Nếu `latest.csv` có thể bị thay, restart không chắc đọc cùng dữ liệu. Nên dùng:

```text
inputFile=/data/snapshots/orders-2026-11-15-v1.csv
inputVersionId=...
inputSha256=...
```

Nếu object storage có version ID thì lưu version ID an toàn cho mỗi job; khi restart đọc theo version đó.

### 9.5. Idempotency ở output luôn cần được xét

Reader có checkpoint tốt vẫn không giải quyết hoàn toàn duplicate side effect:

- Chunk đọc DB nhưng writer gửi API ngoài đã commit trước khi job rollback.
- Flat file reader ở giữa chunk bị fail và writer đã tạo một phần file output.
- Job restart sau khi output đã publish nhưng chưa kịp cập nhật metadata.

Do đó, bên cạnh reader, thiết kế writer có khóa nghiệp vụ, unique constraint/upsert, outbox hoặc conditional publish phù hợp. **Exactly-once end-to-end không tự phát sinh chỉ bằng chọn reader DB hay file.**

---

## 10. Mức sử dụng bộ nhớ và hiệu năng

### 10.1. DB cursor: fetchSize không phải hard cap

Một JDBC driver có thể prefetch/buffer dữ liệu theo lựa chọn của driver. `fetchSize(500)` chỉ là đề nghị. Để biết có streaming thật:

- Đọc tài liệu JDBC driver/version đang deploy.
- Kiểm tra transaction/autocommit mode và cursor support.
- Đo live heap khi dataset tăng gấp 10.
- Đo connection lifetime và DB waits.
- Kiểm tra query plan/index và throughput.

### 10.2. Database paging: pageSize và chunk size độc lập

Giả sử `pageSize=2000` và `chunkSize=100`: reader có thể giữ nhiều item của page trong bộ nhớ qua các commit; giảm chunk không nhất thiết giảm toàn bộ working set. Ngược lại `pageSize=100` và `chunkSize=1000` có thể khiến một chunk thực hiện nhiều query.

| pageSize | chunkSize | Điểm cần đo |
|---:|---:|---|
| 100 | 100 | Số truy vấn, latency và GC |
| 500 | 500 | Cân bằng query round trip/heap |
| 2.000 | 100 | Buffer page tồn tại qua nhiều chunk |
| 100 | 2.000 | Nhiều page trong một transaction |
| 2.000 | 2.000 | Peak heap, transaction/DB load |

Không chọn thông số chỉ vì các con số tròn. Đo với record size p95/p99, không chỉ kích thước trung bình.

### 10.3. File reader: memory theo kích thước record

`FlatFileItemReader` thường đọc tuần tự, nhưng:

- Một dòng cực lớn có thể tạo `String`/char array lớn.
- CSV quoted multiline và parser có thể giữ nhiều dòng.
- Mapping sang object graph lớn làm item nặng hơn byte CSV.
- Reader tự viết dùng `Files.readAllLines()` phá hỏng streaming.
- Decompression/JSON array parser có thể tăng bộ nhớ mạnh.

Với file nhiều GiB, tránh load toàn bộ vào list hoặc `byte[]` chỉ để map record. Với binary/JSON/XML phức tạp, chọn streaming parser phù hợp chứ không áp ép `FlatFileItemReader` cho mọi định dạng.

### 10.4. Chọn hướng theo bottleneck

| Bottleneck | Database reader | File reader |
|---|---|---|
| DB CPU/IO/lock cao | Có thể chuyển sang replica/staging/export file | File đọc riêng giảm tải query runtime |
| Network từ DB tới worker chậm | Cursor/paging chịu nhiều DB round-trip hoặc stream | File có thể được đặt gần worker |
| Storage throughput thấp | DB có thể tối ưu scan/index | File trên disk/object store có thể là nút thắt |
| File export tốn thời gian | Đọc trực tiếp DB tránh chờ export | Cần đầu tư pipeline snapshot nhanh hơn |
| Job cần chạy song song | ID/range partition và SQL index | File partition thường rõ ràng nếu file độc lập |
| Memory JVM cao | Giảm page/fetch, projection, JPA graph | Giới hạn record, parser, tránh preloading |
| Restart tốn thời gian | Stable keyset/snapshot, checkpoint | Immutable file, file offset/line, manifest |

Nếu workload là “báo cáo 100.000 record mỗi đêm”, cả hai cách có thể đủ nhanh; chọn phương án đơn giản hơn với hợp đồng rõ. Nếu workload là 5 tỷ record, thiết kế snapshot, export và partition có thể quyết định nhiều hơn chọn class reader.

---

## 11. Mức độ phụ thuộc và kiến trúc liên hệ giữa hệ thống

### 11.1. Reader DB liên kết trực tiếp hệ thống

Đọc database source trực tiếp khiến batch phụ thuộc:

- Tình trạng và cấu hình database.
- Schema/table/column và quyền truy cập.
- Index/query plan.
- Transaction isolation và tải OLTP.
- Kết nối mạng, pool, credential rotation.
- Lịch bảo trì database.
- Chính sách tương thích schema giữa hai nhóm.

Mặt tốt: không cần pipeline xuất/truyền file, có thể truy vấn linh hoạt, tránh trùng bản dữ liệu tạm. Mặt khó: thay đổi ở source DB có thể tác động batch trực tiếp. Một hệ thống sở hữu dữ liệu có thể không muốn cấp quyền SELECT bảng nghiệp vụ cho nhóm khác.

### 11.2. File là một hợp đồng trao đổi tách rời

Đối tác tạo file theo phiên bản schema, publish manifest và chuyển quyền cho consumer. Batch không cần biết schema vật lý của DB source.

Ưu điểm:

- Giảm coupling trực tiếp tới database nguồn.
- Dễ kiểm toán một phiên bản snapshot.
- Có thể chuyển cùng snapshot cho nhiều bên.
- Không cần giữ connection tới OLTP khi xử lý.

Nhược điểm:

- Có chi phí export, chuyển file, storage và cleanup.
- Dữ liệu có độ trễ so với source live.
- Cần versioning/schema validation/manifest.
- Cần xử lý file đến muộn, thiếu, hỏng, nửa chừng hoặc trùng.

### 11.3. Kết hợp hai hướng

Không phải lúc nào cũng phải chọn hoàn toàn một phía. Một kiến trúc phổ biến:

```text
OLTP Database
     │
     ├── snapshot / SQL export / CDC
     ▼
Immutable staging data
     │
     ├── snapshot table / read replica
     │
     └── immutable files + manifest
              │
              ▼
         Spring Batch
              │
              ▼
        Target database / files
```

Nếu yêu cầu SLA cao nhưng không muốn query OLTP khi batch chạy, có thể export/snapshot trước giờ xử lý, rồi đọc file hoặc bảng staging. Nếu chỉ cần vài nghìn record và nguồn đã đủ ổn định, tạo pipeline snapshot riêng có thể gây phức tạp không cần thiết.

---

## 12. Ví dụ thiết kế thống nhất: thay reader, giữ processor/writer

Bài toán: tạo bảng invoice từ các order đã chốt trong kỳ nghiệp vụ. Có hai nguồn được phép:

- `DB`: bảng `source_orders` chứa `id`, `customer_id`, `amount`. Batch đọc những ID không vượt quá một `cutoffId` được xác định trước.
- `FILE`: một CSV immutable chứa đúng ba cột `id,customer_id,amount`.

Hai phương án phải trả cùng model `OrderRow`.

### 12.1. Model

```java
package com.example.batch.design;

import java.math.BigDecimal;

public record OrderRow(
        long id, long customerId, BigDecimal amount) {}

public record InvoiceRow(
        long orderId, BigDecimal amountWithFee) {}
```

Processor stateless:

```java
@Bean
ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor() {
    return order -> new InvoiceRow(
            order.id(),
            order.amount().multiply(new BigDecimal("1.05")));
}
```

Với hợp đồng tiền có scale 2, nên xác định rõ rounding:

```java
return new InvoiceRow(
        order.id(),
        order.amount()
                .multiply(new BigDecimal("1.05"))
                .setScale(2, RoundingMode.HALF_UP));
```

Phải dùng chính sách rounding do nghiệp vụ quy định; `HALF_UP` chỉ là lựa chọn minh họa.

### 12.2. Hai implementation reader cùng tên bean

Dùng Spring Boot `@ConditionalOnProperty` để chọn đúng một bean `orderReader` khi khởi tạo context. Đối với nguồn file, path được resolve theo `JobParameters`.

```java
package com.example.batch.design;

import java.nio.charset.StandardCharsets;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration(proxyBeanMethods = false)
class OrderReaderConfiguration {

    @Bean("orderReader")
    @StepScope
    @ConditionalOnProperty(
            prefix = "batch.input",
            name = "type",
            havingValue = "db")
    ItemStreamReader<OrderRow> dbOrderReader(
            DataSource dataSource,
            @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

        if (cutoffId == null) {
            throw new IllegalArgumentException(
                    "cutoffId must be specified");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("dbOrderReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, customer_id, amount
                    FROM source_orders
                    WHERE id <= ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps ->
                        ps.setLong(1, cutoffId))
                .rowMapper((rs, n) -> new OrderRow(
                        rs.getLong("id"),
                        rs.getLong("customer_id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(500)
                .build();
    }

    @Bean("orderReader")
    @StepScope
    @ConditionalOnProperty(
            prefix = "batch.input",
            name = "type",
            havingValue = "file")
    ItemStreamReader<OrderRow> fileOrderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException(
                    "inputFile must be specified");
        }

        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("fileOrderReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "customer_id", "amount")
                .fieldSetMapper(fs -> new OrderRow(
                        fs.readLong("id"),
                        fs.readLong("customer_id"),
                        fs.readBigDecimal("amount")))
                .build();
    }
}
```

**Lưu ý cấu hình:**

- Hai bean cùng tên `orderReader` được điều kiện hóa; chỉ **một** nên được đăng ký theo property. Không cấu hình cùng lúc cả `db` và `file`.
- `@StepScope` cho phép lấy `JobParameters` tại thời điểm thực thi step. Không lấy path/cutoff từ một static global mutable state.
- Với `DB`, `cutoffId` chặn các ID lớn hơn theo snapshot high-water mark. Nó không bảo đảm chống update/delete bản ghi ID nhỏ hơn.
- Với `FILE`, ứng dụng phải validate/đóng băng file input trước khi step bắt đầu.
- Trong thiết kế đa nguồn production, có thể tách cấu hình theo profile/module thay vì tạo reader theo một property chung; quyết định phụ thuộc cách deploy và kiểm soát quyền.

### 12.3. Writer và step chung

Ví dụ ghi invoice vào JDBC target table có khóa unique theo `order_id`:

```java
package com.example.batch.design;

import java.math.BigDecimal;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
class InvoiceJobConfiguration {

    @Bean
    ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor() {
        return order -> new InvoiceRow(
                order.id(),
                order.amount().multiply(new BigDecimal("1.05")));
    }

    @Bean
    JdbcBatchItemWriter<InvoiceRow> invoiceWriter(
            DataSource targetDataSource) {

        return new JdbcBatchItemWriterBuilder<InvoiceRow>()
                .dataSource(targetDataSource)
                .sql("""
                    INSERT INTO invoices (order_id, amount_with_fee)
                    VALUES (?, ?)
                    """)
                .itemPreparedStatementSetter((item, ps) -> {
                    ps.setLong(1, item.orderId());
                    ps.setBigDecimal(2, item.amountWithFee());
                })
                .build();
    }

    @Bean
    Step invoiceStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("orderReader")
                    ItemStreamReader<OrderRow> orderReader,
            ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor,
            JdbcBatchItemWriter<InvoiceRow> invoiceWriter) {

        return new StepBuilder("invoiceStep", repository)
                .<OrderRow, InvoiceRow>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(invoiceProcessor)
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    Job invoiceJob(JobRepository repository, Step invoiceStep) {
        return new JobBuilder("invoiceJob", repository)
                .start(invoiceStep)
                .build();
    }
}
```

Đây là mẫu để minh họa abstraction. Dự án phải bảo đảm `source_orders` và `invoices` tồn tại, cùng cấu hình datasource/JDBC transaction phù hợp và schema target. Nếu `DataSource` source và target là hai DB khác nhau, cần xác định ranh giới transaction đúng; một local transaction manager không tự commit/rollback cả hai DB.

**Quan trọng với restart:** `INSERT` thuần sẽ thất bại nếu output đã có ID từ một lần chạy trước. Trong production, hãy thiết kế idempotency (unique key, UPSERT theo dialect, merge, staging và publish) phù hợp, không đơn giản thay mọi lỗi duplicate thành skip. Việc thiết kế writer là một phần của tính đúng đắn tổng thể.

### 12.4. Cấu hình application

Chọn DB reader:

```yaml
batch:
  input:
    type: db

spring:
  batch:
    job:
      enabled: false
```

Hoặc chọn file reader:

```yaml
batch:
  input:
    type: file

spring:
  batch:
    job:
      enabled: false
```

Với DB:

```java
JobParameters dbParams = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("cutoffId", 9000000L, true)
        .toJobParameters();
```

Với file:

```java
JobParameters fileParams = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "orders-20261115-v2", true)
        .addString("inputFile",
                "/data/ready/orders-20261115-v2.csv", false)
        .toJobParameters();
```

Một ứng dụng thường chỉ chọn một chiến lược reader theo deploy/context. Không giả định thay `batch.input.type` giữa các lần restart của cùng `JobInstance` là an toàn: điều đó có thể thay dataset, reader state key và thứ tự dữ liệu. Để hỗ trợ restart qua thay đổi deployment, cần giữ cùng **source strategy và snapshot identity** hoặc có migration state có kiểm soát.

### 12.5. Khi nào hai reader được coi là tương đương?

Định nghĩa một **source contract**:

```text
InputDatasetContract:
  businessDate         = 2026-11-15
  datasetId            = orders-20261115-v2
  expectedRecordCount  = ...
  schemaVersion        = 3
  orderingKey          = id (unique)
  amountScale          = 2
  timezone             = Asia/Ho_Chi_Minh
  allowedLateChanges   = false after cutoff
```

Nếu DB reader có query lọc thêm `status='SETTLED'` nhưng file export có cả `PENDING`, hai reader **không tương đương**, dù model Java giống nhau. Kiểm thử tổng count, business keys, sums và exceptions sẽ giúp phát hiện sai khác.

---

## 13. Hiệu năng và chi phí vận hành: đo thế nào?

### 13.1. Những metric cần đo

| Chỉ số | Database reader | File reader |
|---|---|---|
| Read throughput | Rows/s, query/page time | Lines/s, bytes/s |
| Processing throughput | Items/s sau processor/writer | Như nhau nếu pipeline tương đương |
| Latency đến dữ liệu đầu tiên | Mở cursor/fetch page | File transfer/ready + open |
| End-to-end completion time | DB query + processing | Export + transfer + processing |
| Memory/GC | Driver/page/ORM object graph | Parser/line/object graph |
| Source system impact | CPU/IO/locks/connection của DB | Export load DB, storage/network |
| Restart cost | Re-query/reposition snapshot | Reopen/skip-to-line hoặc resource checkpoint |
| Retry behavior | Connection lost, deadlock, timeout | Missing/truncated/corrupt file, remote storage error |
| Operational cost | DB capacity, read replica | Storage, retention, transfer, manifest |
| Data freshness | Thời điểm commit/query | Thời điểm snapshot ready |
| Correctness | Missing/duplicate by business key | Count/hash/schema/version |

Nếu chỉ đo `invoiceStep` sau lúc file đã sẵn sàng, file reader có thể trông nhanh hơn nhưng bỏ qua 40 phút export. Khi chọn kiến trúc, đo **từ thời điểm nghiệp vụ cần dữ liệu đến lúc kết quả cuối sẵn sàng**, không chỉ thời gian `JobExecution`.

### 13.2. Benchmark đại diện

Ví dụ lập kế hoạch đo:

1. Chọn dataset 1 triệu, 10 triệu, 50 triệu item theo khả năng môi trường.
2. Dùng cùng business contract và writer.
3. Với DB, thử cursor fetchSize 100/500/1000; paging pageSize 100/500/1000.
4. Với file, thử local SSD, object storage staging và nhiều file partition.
5. Giữ cùng heap/GC, thread count, DB workload và target schema.
6. Đo p50/p95 latency, max heap, GC pause, DB CPU/IO, network, file transfer.
7. Cho retry/restart sau khi chủ động fail ở nửa chừng.
8. Kiểm tra dữ liệu đầu ra bằng business keys/total sums, không chỉ status `COMPLETED`.

Bảng điền kết quả thực nghiệm:

| Reader | Input size | Export/prepare time | Step runtime | Peak heap | Source load | Restart time |
|---|---:|---:|---:|---:|---|---:|
| JDBC cursor | 10M | 0 | Đo | Đo | Đo | Đo |
| JDBC paging | 10M | 0 | Đo | Đo | Đo | Đo |
| Flat file SSD | 10M | Đo | Đo | Đo | Đo | Đo |
| File qua object storage | 10M | Đo | Đo | Đo | Đo | Đo |

Không điền số giả làm benchmark. Benchmark đúng phải có dữ liệu, driver, database, storage và network tương tự production.

### 13.3. Những biến gây sai lệch benchmark

- DB buffer cache nóng/lạnh.
- JIT/JVM warm-up và GC ergonomics.
- DB replica replication lag.
- File nằm trong page cache của OS.
- Băng thông/SFTP throttle.
- SQL plan/index khác giữa môi trường.
- Cùng lúc có nhiều job hay không.
- Row graph lớn/nhỏ, malformed records.
- Chunk size và writer commit frequency.

Cần chạy nhiều lần, báo kết quả cùng cấu hình. Có thể một reader nhanh ở dữ liệu nhỏ nhưng không ổn định khi dữ liệu tăng 10 lần.

---

## 14. Kiến trúc cho dữ liệu rất lớn

### 14.1. Database partition theo khóa

Một cách chia:

```text
Snapshot run S-20261115
       │
       ├─ partition A: id 1 ... 1,000,000
       ├─ partition B: id 1,000,001 ... 2,000,000
       ├─ partition C: id 2,000,001 ... 3,000,000
       └─ ...
                │
                ▼
         Reader riêng từng partition
                │
                ▼
       Process / write độc lập
```

Điều kiện:

- Các range **không chồng lấn** và phủ đủ khóa cần đọc.
- Snapshot/predicate ổn định.
- Không giả định ID liên tục nếu không có.
- Giới hạn kết nối và query concurrent để DB không quá tải.
- Reader/ExecutionContext từng partition có identity ổn định khi restart.

Nếu source có khóa phân bố không đều, chia range theo min/max có thể tạo một số partition nặng hơn phần còn lại; cân nhắc phân phối theo thống kê, hash partition hoặc danh sách key materialized.

### 14.2. File partition

Nếu dataset được xuất thành 100 file immutable có size tương đương, có thể giao mỗi partition một nhóm file:

```text
Manifest + checksums
     │
     ▼
File partitioner
  ├─ worker 1 → files 1-25
  ├─ worker 2 → files 26-50
  ├─ worker 3 → files 51-75
  └─ worker 4 → files 76-100
     │
     ▼
Output staging / merge / publish
```

Đảm bảo:

- Manifest version và file list không thay đổi khi restart.
- Một file không bị hai worker xử lý nếu không có mô hình idempotency phù hợp.
- Output partition không bị trộn/trùng; publish sau khi đủ tất cả phần.
- Tổng record count/checksum khớp manifest.
- File đến muộn không tự chèn vào tập đang chạy.

### 14.3. Trường hợp streaming/CDC tốt hơn cả hai

Nếu yêu cầu là cập nhật gần real-time mỗi vài giây, đọc lại bảng 100 triệu row mỗi phút hoặc export full CSV liên tục đều tốn tài nguyên. CDC/event-driven pipeline có thể phù hợp hơn để lấy increment, rồi Spring Batch xử lý backfill/snapshot hoặc reconciliation định kỳ.

Điều này không có nghĩa “Batch không xử lý streaming”: Spring Batch có thể làm incremental batch theo watermark hoặc chia cửa sổ. Nhưng khi nguồn thay đổi liên tục, cần một **change log/offset** đáng tin cậy để không bỏ sót update/delete.

---

## 15. Bảo mật và quyền sở hữu nguồn

### 15.1. Database reader

Quyền nên được giới hạn:

- Chỉ `SELECT` trên view/bảng cần thiết.
- Chỉ cột/trường được cho phép, tránh `SELECT *`.
- Nếu có tenant data, enforce predicate/row-level security và parameterization.
- Dùng credential/workload identity được quản lý, rotation và audit.
- Không log SQL parameter chứa PII/secret.
- Với DB replica, bảo đảm chính sách dữ liệu và lag được chấp nhận.
- Không cấp quyền update chỉ để hỗ trợ reader nếu không bắt buộc.

### 15.2. File reader

Kiểm soát:

- TLS/SFTP/mTLS khi truyền.
- Bucket/object ACL, quyền tối thiểu theo prefix/file.
- Encryption at rest và encryption application-level nếu hợp đồng yêu cầu.
- Signed manifest/checksum từ nguồn đáng tin.
- Đường dẫn allowlist, chống path traversal/symlink.
- Quyền thư mục staging, thời hạn giữ file và quarantine.
- Không đặt file PII thô trong public bucket hoặc thư mục chia sẻ rộng.
- Không log cả dòng CSV malformed khi chứa PII.

### 15.3. Không lưu secret trong JobParameters

`JobParameters` được Spring Batch lưu trong repository. Chúng phù hợp cho `businessDate`, `snapshotId`, `fileId`, cutoff ID hoặc đường dẫn đã được kiểm soát, **không phù hợp cho raw database password, API token hay AES key**.

Nếu tên object/path cũng chứa thông tin nhạy cảm, không tự hiển thị nguyên dạng trong dashboard hay log. Dùng logical file ID và service có phân quyền để resolve.

---

## 16. File ready, schema và xử lý lỗi

### 16.1. Có file nhưng không hợp đồng

Một file có thể tồn tại đầy đủ nhưng sai:

- Encoding không phải UTF-8.
- Header đổi tên/cột.
- Giá trị date theo timezone khác.
- Giá trị thập phân dùng dấu phẩy.
- Record count không khớp manifest.
- Có duplicate business key.
- File đúng tên nhưng thuộc ngày khác.
- Footer/trailer không hợp lệ.

Một bước validation trước khi đọc nên kiểm tra format/version/metadata/cutoff. Với dữ liệu nhạy cảm, xác thực chữ ký/authenticated encryption trước khi tin dữ liệu.

### 16.2. DB schema và query version

Một thay đổi DB schema làm mất cột `customer_id` có thể khiến reader fail lúc khởi chạy. Cần contract/migration:

- Dùng view ổn định theo phiên bản để tách batch khỏi bảng nội bộ.
- Dùng explicit select column và mapping.
- Test query với schema migration.
- Đồng bộ rollout producer/consumer.
- Đặt schema compatibility policy (thêm cột, đổi tên, đổi kiểu).

### 16.3. Chính sách skip/retry

| Lỗi | DB reader | File reader |
|---|---|---|
| Nguồn không sẵn sàng tạm thời | DB timeout/connection error, retry có giới hạn | SFTP/object storage timeout, retry có giới hạn |
| Dữ liệu lỗi schema | SQL mapping/type mismatch | CSV malformed/header không khớp |
| Input thiếu | Không có bảng/query/snapshot, tùy contract | Resource không tồn tại/manifest thiếu |
| Nguồn thay đổi khi restart | Query trả tập khác | File đổi byte/thứ tự |
| Bản ghi lỗi riêng lẻ | RowMapper/field conversion fail | LineMapper/FieldSet conversion fail |
| Nguồn hỏng nghiêm trọng | DB failover, snapshot lost | File truncated/checksum fail |

**Skip chỉ khi nghiệp vụ chấp nhận bỏ một record.** Không nên dùng `skipLimit` để ẩn việc file bị cắt hoặc database snapshot bị thay. Các lỗi ở cấp dataset thường cần fail toàn bộ job/quarantine và điều tra.

---

## 17. Kiểm thử thiết kế: điều gì phải chứng minh?

### 17.1. Unit test reader

Với `FlatFileItemReader`:

- Header được bỏ qua đúng.
- Mapping đúng kiểu ID/decimal/date.
- Dữ liệu UTF-8 có dấu được đọc đúng.
- Line đặc biệt, quoted delimiter và malformed data theo policy.
- EOF trả `null`.
- `strict(true)` báo lỗi khi resource thiếu.
- State lưu và khôi phục qua `ExecutionContext` với input không thay đổi.

Với `JdbcCursorItemReader`/`JdbcPagingItemReader`:

- SQL lọc đúng `businessDate`/`cutoffId`.
- Thứ tự theo khóa unique.
- Không bỏ/trùng khi paging.
- Empty result trả `null`.
- Lỗi connection được báo đúng.
- Restart khôi phục vị trí phù hợp.
- Mapping SQL NULL/decimal/timestamp chính xác.

### 17.2. Integration test tương đương hai nguồn

Cho cùng một snapshot 4 bản ghi:

```csv
id,customer_id,amount
1001,71,120.50
1002,72,0.00
1003,73,99.99
1004,74,5.25
```

Tạo bốn dòng tương ứng trong `source_orders` của H2/PostgreSQL test. Chạy hai bản cấu hình reader ở **hai context/test run riêng** với cùng processor và writer, dùng target tables riêng hoặc cleanup cô lập. Assertion:

- `readCount=4` và `writeCount=4`.
- Tập `order_id` output bằng nhau.
- Tổng `amountWithFee` bằng nhau theo rounding policy.
- Thứ tự nếu là yêu cầu contract; không dựa vào thứ tự tùy ý.
- Job status `COMPLETED`.
- Không có record duplicate.
- `businessDate`/`cutoffId`/`snapshotId` đúng theo fixture.

### 17.3. Test restart FlatFile

Quy trình:

1. Dùng `FlatFileItemReader` đọc một số item và persist checkpoint qua step thật.
2. Làm writer fail có kiểm soát.
3. Restart với cùng `JobInstance` và cùng file checksum.
4. Assert output cuối đúng, không thiếu/trùng.
5. Thay đổi một dòng ở đầu file giữa hai lần và chứng minh contract restart đã bị vi phạm — hệ thống cần chặn bằng checksum/version, không cố xử lý lặng lẽ.

### 17.4. Test restart Paging

Quy trình:

1. Chạy reader paging với sort key duy nhất.
2. Fail sau vài chunk.
3. Restart trên dataset bất biến, assert tập output đầy đủ.
4. Thử thêm dòng ID lớn hơn cutoff, chỉnh dòng cũ, xóa dòng cũ; ghi lại expected behavior theo snapshot contract.
5. Tránh giả định “có cutoffId là snapshot bất biến” khi update/delete vẫn được phép.

### 17.5. Test missing/late file

- Chưa có ready marker: không chạy hoặc fail theo chính sách, không coi file trống là success.
- Có file nhưng đang upload: consumer không mở.
- File count/checksum mismatch: fail và quarantine.
- Manifest thay đổi giữa restart: từ chối hoặc yêu cầu quyết định reprocess rõ ràng.
- Có thêm file sau khi chốt manifest: xử lý theo kỳ tiếp theo, không chèn vào instance cũ.

### 17.6. Test DB load và transaction

Không chỉ kiểm tra correctness: chạy benchmark với dữ liệu lớn để xác định SQL query plan, số connection, DB CPU, locks, rows scanned, fetch time, heap, GC, throughput và ảnh hưởng lên OLTP. Một câu query đúng nhưng làm hệ thống giao dịch chậm 5 giây không phải thiết kế chấp nhận được.

---

## 18. Tình huống lựa chọn thực tế

### Tình huống A — Báo cáo tài chính cuối ngày từ OLTP

Yêu cầu:

- 20 triệu giao dịch/ngày.
- Không được gây tải đáng kể lên DB giao dịch vào giờ cao điểm.
- Có thể kiểm toán chính xác dữ liệu của từng ngày.
- Cần chạy lại đúng kỳ trong 90 ngày.

**Thiết kế đáng cân nhắc:** tạo snapshot trong read replica/staging hoặc xuất file bất biến có manifest, sau đó chạy `FlatFileItemReader`/`MultiResourceItemReader`. Nếu dùng DB reader, phải chứng minh DB replica/snapshot isolation và chi phí query được chấp nhận.

Quyết định phụ thuộc hạ tầng snapshot đã có, tốc độ export và dữ liệu late-arrival.

### Tình huống B — Làm sạch 100.000 record trong bảng staging

Yêu cầu:

- Dữ liệu chỉ được import qua một workflow, không có update đồng thời.
- Hệ thống cùng sở hữu staging table và batch.
- Không cần chia sẻ dataset ra bên ngoài.
- Yêu cầu triển khai nhanh, ít công cụ.

**Thiết kế đáng cân nhắc:** `JdbcPagingItemReader` hoặc `JdbcCursorItemReader` với query/index ổn định; tránh tạo bước export file thừa. Dùng `cutoffId`, run ID hoặc staging snapshot ID nếu cần chạy lại.

### Tình huống C — Đối tác gửi CSV qua SFTP

Yêu cầu:

- Mỗi ngày đối tác gửi một file có chữ ký/checksum.
- Không có quyền truy cập DB đối tác.
- Phải giữ bằng chứng dữ liệu gốc.

**Chọn file reader** gần như hiển nhiên sau bước nhận/validate. Cần giao thức ready, mã hóa/quyền, header/schema version, kiểm toán file ID và checksum, quarantine file sai.

### Tình huống D — Dữ liệu thay đổi liên tục, phải đồng bộ dưới 1 phút

Yêu cầu:

- Nhiều update/delete cùng một business key.
- End-to-end latency dưới một phút.
- Full snapshot hàng giờ quá tốn kém.

**Cân nhắc CDC/incremental event pipeline** hơn là full scan DB hoặc full export file. Spring Batch vẫn hữu ích cho initial backfill và reconciliation, nhưng snapshot nightly có thể không đáp ứng độ trễ.

### Tình huống E — Dữ liệu JPA nhiều quan hệ nhưng chỉ cần ba cột

Nếu job chỉ lấy `id`, `totalAmount` và `businessDate` từ 5 triệu entity, `JdbcPagingItemReader` với projection có thể giảm memory và N+1 query hơn việc nạp toàn entity qua JPA. Nếu cần các quy tắc domain phức tạp gắn với entity, JPA có thể hợp lý — nhưng cần test lazy associations, detached entities và page size.

### Tình huống F — File lớn 100 GiB trên object storage

Đọc `InputStream` từ object store vào `FlatFileItemReader` theo kiểu phù hợp cần xem khả năng reopen/restart và durability. Một hướng thực dụng là staging các object immutable về local disk được quản lý, validate checksum, rồi phân partition theo file. Với object storage reader trực tiếp, phải thiết kế retry/seek/range và version ID, tránh đọc latest object đã đổi.

---

## 19. Khung quyết định và scoring có trọng số

Không có đáp án “reader nào tốt hơn” nếu chưa xếp ưu tiên yêu cầu. Dùng ma trận dựa trên trọng số.

Ví dụ cho job đối soát:

| Tiêu chí | Trọng số | DB reader (1–5) | File reader (1–5) |
|---|---:|---:|---:|
| Snapshot/replay chính xác | 5 | 3 | 5 |
| Không tăng tải OLTP | 5 | 2 | 5 |
| Data freshness | 3 | 5 | 3 |
| Giảm vận hành pipeline phụ | 2 | 5 | 2 |
| Audit file nguồn | 4 | 3 | 5 |
| Chạy song song | 3 | 4 | 4 |
| Chi phí storage | 2 | 4 | 2 |
| Schema linh hoạt | 2 | 4 | 3 |

**Đây là điểm giả định để minh họa**, không phải đánh giá khách quan của mọi database/file. Mỗi nhóm phải thay trọng số/điểm bằng số liệu và giới hạn thực tế. Có thể còn tiêu chí bắt buộc (*hard constraint*) loại ngay một phương án: ví dụ đối tác không cấp quyền DB, hoặc luật cấm tạo snapshot plaintext ngoài một vùng bảo vệ.

### 19.1. Quy trình ra quyết định

```text
Xác nhận business contract
         │
         ▼
Dữ liệu đã ở file bất biến?
    ├─ Có → File reader + validate manifest
    └─ Không
         │
         ▼
Batch được quyền/trách nhiệm query DB?
    ├─ Không → Snapshot/export API/file
    └─ Có
         │
         ▼
Dataset có ổn định qua toàn bộ job/restart?
    ├─ Không → Snapshot/version/staging/CDC
    └─ Có
         │
         ▼
Đánh giá volume, SLA, concurrency, DB load
         │
         ├─ DB đọc trực tiếp đáp ứng → JDBC cursor/paging/JPA
         └─ DB tải cao hoặc cần phân phối → Export file/snapshot
         │
         ▼
Benchmark + kiểm thử restart/idempotency
         │
         ▼
Chốt ADR + runbook + monitoring
```

Nếu hai phương án đều đáp ứng, ưu tiên tổng chi phí thấp hơn trong toàn bộ lifecycle (export, transfer, xử lý, audit, bảo trì, failure recovery), không chỉ độ ngắn của reader config.

---

## 20. Architecture Decision Record (ADR) mẫu

```markdown
# ADR-012: Chọn reader cho daily settlement batch

## Trạng thái
Accepted

## Bối cảnh
- Nguồn: PostgreSQL OLTP, khoảng 12 triệu transaction/ngày.
- Data cut-off: 23:59 theo business timezone.
- Thời gian chạy: dưới 90 phút.
- Không được ảnh hưởng latency OLTP.
- Cần replay cùng dataset trong 60 ngày.

## Những lựa chọn
1. JdbcCursorItemReader trực tiếp trên OLTP.
2. JdbcPagingItemReader trên read replica/snapshot.
3. Snapshot thành file bất biến và FlatFileItemReader.

## Quyết định
Chọn phương án 3 nếu pipeline xuất file kịp SLA và
hợp đồng snapshot được bảo đảm bằng ready manifest,
checksum và object version ID.

## Lý do
- Giảm tải OLTP lúc batch chạy.
- Có dữ liệu gốc bất biến để kiểm toán/restart.
- Dễ phân phối file cho các consumer đã được cấp quyền.

## Rủi ro và biện pháp
- Export trễ: alert missing input/ready marker.
- File hỏng: checksum/schema validation và quarantine.
- Storage tăng: retention policy, backup và cleanup.
- Restart: pin object version + checksum trong metadata.

## Điều kiện đánh giá lại
- Export vượt 30 phút hoặc tổng SLA không đạt.
- Dataset tăng 5 lần.
- Read replica có snapshot query rẻ hơn đáng kể.
```

ADR không cần trùng lựa chọn ở ví dụ trên. Việc ghi rõ điều kiện đánh giá lại giúp kiến trúc không biến thành một quy tắc bất biến khi hệ thống phát triển.

---

## 21. Runbook lỗi theo nguồn đọc

### 21.1. Database reader timeout hoặc DB failover

1. Xác nhận `JobExecutionId`, `StepExecution` và query/cutoff/snapshot ID.
2. Phân biệt timeout tạm thời, DB failover, deadlock, permission/schema error.
3. Kiểm tra DB primary/replica, query plan, connection pool và isolation.
4. Nếu sẽ restart, bảo đảm dataset/snapshot không đổi hoặc có recovery policy rõ.
5. Khởi chạy lại cùng identifying parameters khi hợp lệ.
6. Đối chiếu count, business keys và output idempotency.

Không đổi cutoff để “chạy tiếp” mà không biết ảnh hưởng đến tập dữ liệu.

### 21.2. File thiếu/hỏng hoặc đổi giữa chừng

1. Xác minh ready manifest và file ID/version.
2. Đối chiếu byte length, checksum, schema version, record count.
3. Kiểm tra quyền truy cập, encryption, transfer status.
4. Không âm thầm dùng `strict(false)` để biến file thiếu thành input rỗng.
5. Quarantine file hỏng, yêu cầu gửi lại hoặc dùng bản snapshot cũ đã được chấp nhận.
6. Restart chỉ khi cùng file version/checksum được khôi phục; nếu snapshot mới, lập một workflow reprocess rõ ràng.

### 21.3. Output thiếu/trùng

1. Tách nguyên nhân reader (missing input, sai cursor/page/file ordering) khỏi writer (duplicate publish, transaction).
2. Kiểm tra `readCount`, `writeCount`, `filterCount`, `skipCount`.
3. Đối chiếu business key set, không chỉ count.
4. Xác định chunk/partition nào đã commit.
5. Sửa idempotency hoặc snapshot contract trước khi restart.
6. Chạy reconciliation và lưu audit.

---

## 22. Bài tập thực hành

### Bài 1 — Chọn reader cho ba hệ thống

Đưa ra lựa chọn cho: (a) staging table 100.000 dòng ổn định, (b) đối tác gửi 100 CSV đã ký, (c) OLTP 20 triệu giao dịch/ngày có update liên tục. Viết tiêu chí, rủi ro và điều kiện quyết định.

### Bài 2 — JDBC cursor

Cài `JdbcCursorItemReader` cho bảng `orders`, đọc 1 triệu row với `fetchSize=100/500/1000`. Đo throughput, heap, DB connection lifetime. Xác nhận driver có streaming như mong đợi.

### Bài 3 — JDBC paging

Dùng `JdbcPagingItemReader` với sort key `id` unique. Thử page size 100/500/2000, crash giữa job rồi restart. Test thêm insert ID lớn hơn cutoff và update/delete dòng cũ; giải thích consistency policy.

### Bài 4 — File reader

Tạo CSV UTF-8 có header, quoted comma, malformed row, record âm/zero. Cấu hình reader, test mapping, EOF, strict mode và skip policy.

### Bài 5 — MultiResourceItemReader

Tạo ba file và manifest theo thứ tự ổn định. Chạy fail giữa file thứ hai rồi restart. Thêm file mới vào directory nhưng giữ manifest cũ; xác nhận file mới không được chèn vào instance đang xử lý.

### Bài 6 — Hai nguồn một output

Với cùng dataset, chạy một job bằng DB reader và một job bằng file reader. Assert tập business IDs, số lượng, tổng tiền và output tương đương. Đối chiếu cả dữ liệu lỗi và duplicate.

### Bài 7 — Source bị thay đổi

Cho database update status/amount của row khi paging đang chạy. Thiết kế snapshot table/version hoặc isolation phù hợp để có output đúng theo thời điểm chốt.

### Bài 8 — File chưa READY

Giả lập producer đang upload. Viết bước validation chỉ cho job mở resource sau khi nhận manifest/ready marker và checksum hợp lệ; assert không chạy trên file nửa chừng.

### Bài 9 — Partition và performance

Chia 20 triệu record theo ID range rồi theo nhiều file. Đo 1, 4, 8 worker, heap/DB I/O/storage throughput, output correctness và restart. Xác định nơi concurrency làm hệ thống chậm đi.

### Bài 10 — ADR

Viết một trang ADR cho dự án thực tế của bạn với trọng số tiêu chí, quyết định, số đo benchmark và điều kiện đánh giá lại. Chỉ chốt phương án khi có cơ chế restart và data correctness có thể kiểm chứng.

---

## 23. Tài liệu tham khảo

- [Spring Batch — Database ItemReaders and ItemWriters](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC cursor/paging, `PagingQueryProvider`, `JpaPagingItemReader` và chú ý unique sort key.
- [Spring Batch — FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): Resource, encoding, strict, line mapping.
- [Spring Batch — Multi-File Input](https://docs.spring.io/spring-batch/reference/readers-and-writers/multi-file-input.html): `MultiResourceItemReader`, resource ordering và restart.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` và execution context.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): đọc/xử lý/ghi trong transaction chunk.
- [Spring Batch — Database Reader API 5.2](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/database/JdbcPagingItemReader.html): behavior và restart của JDBC paging reader.
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning và concurrency.
- [Spring Batch — Job Repository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): checkpoint metadata, transaction và restart support.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils` và kiểm thử job/step.

**Kết luận:** lựa chọn reader database hay file phải xuất phát từ **hợp đồng tập dữ liệu, snapshot consistency, yêu cầu restart, tải hệ thống nguồn và SLA end-to-end**. Database reader đem lại SQL filtering và quyền truy cập dữ liệu cập nhật, nhưng cần kiểm soát query, sort key, isolation và thay đổi đồng thời. File reader thuận lợi khi dữ liệu được đóng băng, chia sẻ và kiểm toán, nhưng cần manifest, immutability, schema validation và chính sách khi file thiếu/hỏng. Cách chọn đúng là phương án có thể kiểm chứng đầy đủ **không đọc thiếu, không đọc trùng, có thể phục hồi và đáp ứng chi phí vận hành**, chứ không đơn giản là class reader có ít dòng code nhất.
