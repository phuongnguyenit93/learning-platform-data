# ParameterizedPreparedStatementSetter và xử lý lô cuối trong Spring JDBC

Khi ứng dụng cần thực thi nhiều câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` có **cùng cấu trúc SQL** nhưng tham số khác nhau, `JdbcTemplate` hỗ trợ gom các thao tác thành nhiều lô (batch). `ParameterizedPreparedStatementSetter<T>` giúp ánh xạ từng đối tượng Java vào các dấu `?` của `PreparedStatement`; Spring chịu trách nhiệm chia lô và thực thi, kể cả **lô cuối có ít phần tử hơn `batchSize`**.

Bài này tập trung vào overload:

```java
<T> int[][] batchUpdate(
    String sql,
    Collection<T> batchArgs,
    int batchSize,
    ParameterizedPreparedStatementSetter<T> pss
)
```

Đây là API của `org.springframework.jdbc.core.JdbcTemplate` (được khai báo qua `JdbcOperations`).

## 1. Khi nào dùng overload này?

Giả sử có 1.005 bản ghi cần ghi vào bảng `inventory`, cùng sử dụng câu SQL:

```sql
INSERT INTO inventory (id, sku, quantity) VALUES (?, ?, ?)
```

Gọi `jdbcTemplate.update(...)` 1.005 lần có thể phát sinh nhiều lần trao đổi với cơ sở dữ liệu. Với batch, driver JDBC có cơ hội nhóm các lệnh để giảm chi phí giao tiếp. Nếu chọn `batchSize = 200`, Spring sẽ chia dữ liệu thành sáu lô: năm lô đủ 200 bản ghi và một lô cuối gồm 5 bản ghi.

Overload này phù hợp khi:

- Đã có `Collection<T>` chứa các đối tượng cần xử lý, ví dụ `List<Product>`, `List<OrderLine>`.
- Tất cả phần tử dùng chung một câu SQL với vị trí dấu `?` cố định.
- Muốn giới hạn số phần tử trong từng lô mà không phải tự viết vòng lặp `addBatch()`/`executeBatch()`.
- Muốn giữ mã ánh xạ tham số rõ ràng, có thể dùng `setLong`, `setString`, `setNull`, `setTimestamp` và các setter JDBC phù hợp.

**Phân biệt:** `batchSize` là **số thao tác tối đa của một lô JDBC**, không phải số hàng chắc chắn được cập nhật, không phải số transaction và cũng không phải số luồng song song.

## 2. Vai trò của từng tham số và callback

| Thành phần | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `sql` | Câu SQL dùng lại cho mọi phần tử | Số/vị trí `?` phải khớp các lần `ps.setXxx(...)`. |
| `batchArgs` | Tập dữ liệu đầu vào kiểu `Collection<T>` | Mỗi đối tượng tương ứng một lần gọi callback. |
| `batchSize` | Giới hạn số phần tử gom trong một lô | Phải chọn số nguyên dương; nên kiểm tra `batchSize > 0` ở đầu vào ứng dụng. |
| `pss` | Callback `ParameterizedPreparedStatementSetter<T>` | Nhận `PreparedStatement` và **chính đối tượng `T` hiện tại** để bind tham số. |
| Kết quả `int[][]` | Các update count theo từng lô | Mảng ngoài ứng với lô; mảng trong chứa kết quả theo từng thao tác của lô. |

Giao diện hàm (functional interface):

```java
@FunctionalInterface
public interface ParameterizedPreparedStatementSetter<T> {
    void setValues(PreparedStatement ps, T argument) throws SQLException;
}
```

Ví dụ ánh xạ ba trường:

```java
(ps, item) -> {
    ps.setLong(1, item.id());
    ps.setString(2, item.sku());
    ps.setInt(3, item.quantity());
}
```

Vị trí tham số JDBC bắt đầu từ **1**. Callback được gọi cho từng `item`; khác với `BatchPreparedStatementSetter.setValues(PreparedStatement ps, int i)` nhận **chỉ số phần tử**. Không gọi `ps.addBatch()`, `ps.executeBatch()`, `ps.clearBatch()`, `ps.close()` hay `commit()` trong callback này: `JdbcTemplate` quản lý các thao tác đó. Callback chỉ chịu trách nhiệm **gán đủ các tham số cho một phần tử**; đừng dựa vào giá trị bind còn lại của phần tử trước.

## 3. Cơ chế chia lô và lô cuối

Giả sử `batchArgs` có `n = 5` phần tử và `batchSize = 2`:

```text
Đầu vào:       A  B  C  D  E
Lô 1:         [A  B]          -> executeBatch()
Lô 2:               [C  D]    -> executeBatch()
Lô cuối:                   [E] -> executeBatch()
Kích thước:     2      2        1
```

Theo logic chia lô khi driver hỗ trợ JDBC batch:

1. Spring duyệt từng đối tượng trong `batchArgs` theo thứ tự duyệt của collection.
2. Với từng đối tượng, Spring gọi `pss.setValues(ps, object)` và thêm thao tác vào batch.
3. Khi đạt `batchSize`, Spring thực thi batch và giữ một nhóm update count.
4. Khi **hết dữ liệu đầu vào**, nếu còn phần tử chưa đủ một lô thì Spring **vẫn thực thi lô cuối** và đưa nhóm kết quả này vào `int[][]`.
5. Phương thức trả về sau khi xử lý xong toàn bộ collection hoặc ném ngoại lệ nếu gặp lỗi.

Không cần bổ sung phần tử giả để lấp đầy lô cuối, cũng không cần gọi `flush` thủ công.

Với driver hỗ trợ JDBC batching và không có lỗi, số lô là `ceil(n / batchSize)` khi `n > 0`. Lô cuối có kích thước `n % batchSize` nếu phép chia có dư; nếu chia hết thì lô cuối cũng đủ `batchSize`, **không có lô rỗng bổ sung**.

| Số phần tử `n` | `batchSize` | Số lô | Kích thước các lô |
| ---: | ---: | ---: | --- |
| 0 | 2 | 0 | `[]` |
| 1 | 2 | 1 | `[1]` |
| 5 | 2 | 3 | `[2, 2, 1]` |
| 6 | 3 | 2 | `[3, 3]` |
| 7 | 3 | 3 | `[3, 3, 1]` |

**Điều kiện quan trọng:** Hình dạng này mô tả đường thực thi batch thông thường. Nếu JDBC driver thông báo không hỗ trợ batch, `JdbcTemplate` có thể thực thi các update riêng lẻ; đừng giả định hình dạng nhóm kết quả trên mọi driver. Luôn thử với driver và cơ sở dữ liệu thực tế.

## 4. Ví dụ chạy được với Java 17+, Spring JDBC và H2

Ví dụ sau chèn 5 sản phẩm với `batchSize = 2`, đọc kết quả và xác minh đủ 5 hàng. `TransactionTemplate` được sử dụng để các lần chèn nằm trong **một transaction**.

Tạo cấu trúc:

```text
batch-demo/
├── build.gradle
└── src/main/java/BatchUpdateDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.19'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'BatchUpdateDemo'
}
```

Nội dung `src/main/java/BatchUpdateDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class BatchUpdateDemo {

    record Stock(long id, String sku, int quantity) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
            CREATE TABLE stock (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(30) NOT NULL,
                quantity INT NOT NULL
            )
            """);

        List<Stock> items = List.of(
            new Stock(1L, "A", 10),
            new Stock(2L, "B", 20),
            new Stock(3L, "C", 30),
            new Stock(4L, "D", 40),
            new Stock(5L, "E", 50)
        );

        int batchSize = 2;
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        int[][] counts = transaction.execute(status ->
            jdbc.batchUpdate(
                "INSERT INTO stock (id, sku, quantity) VALUES (?, ?, ?)",
                items,
                batchSize,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.sku());
                    ps.setInt(3, item.quantity());
                }
            )
        );

        int[] sizes = Arrays.stream(counts).mapToInt(batch -> batch.length).toArray();
        System.out.println("Batch sizes: " + Arrays.toString(sizes));
        System.out.println("Update counts: " + Arrays.deepToString(counts));

        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM stock", Integer.class
        );
        System.out.println("Rows in table: " + total);
    }
}
```

Trong thư mục `batch-demo`, chạy bằng Gradle (có thể dùng `./gradlew run` nếu dự án đã có wrapper):

```bash
gradle run
```

Với H2 và các dữ liệu trong ví dụ, **các dòng do chương trình in ra** là:

```text
Batch sizes: [2, 2, 1]
Update counts: [[1, 1], [1, 1], [1]]
Rows in table: 5
```

Gradle có thể in thêm log build riêng. Bản ghi thứ năm nằm trong lô cuối **một phần tử** và vẫn được chèn; `SELECT COUNT(*)` trả về 5. H2 báo một hàng bị ảnh hưởng cho mỗi `INSERT` thành công, nên các update count trong ví dụ đều là `1`.

### Đọc từng dòng quan trọng

- `List<Stock> items` là `Collection<Stock>` đầu vào; không cần chuyển sang `List<Object[]>`.
- `jdbc.batchUpdate(..., items, 2, (ps, item) -> ...)` duyệt từng `Stock` và bind ba dấu `?`.
- `Arrays.stream(counts).mapToInt(batch -> batch.length)` cho thấy **số phần tử mỗi lô**.
- `Arrays.deepToString(counts)` hiển thị cả hai chiều của `int[][]`; `Arrays.toString(counts)` không hiển thị giá trị mảng lồng nhau theo ý muốn.
- `TransactionTemplate` dùng chung `DataSource` với `JdbcTemplate`; Spring quản lý connection trong transaction. Ranh giới lô `[2, 2, 1]` **không tự động tạo ba transaction**.

Đây là ứng dụng console tối thiểu để quan sát cơ chế. Trong Spring Boot, thường inject `JdbcTemplate` và dùng `@Transactional` trên phương thức service được gọi qua Spring proxy, thay cho việc tự tạo `DriverManagerDataSource`/`TransactionTemplate` trong `main`.

## 5. Hiểu đúng `int[][]` và update count

Giả sử một batch gồm các câu `UPDATE inventory SET quantity = ? WHERE id = ?`:

- `1`: câu lệnh ảnh hưởng một hàng.
- `0`: không có hàng nào khớp điều kiện, hoặc một tình huống được driver báo là không có hàng bị ảnh hưởng; không mặc định xem đó là lỗi kỹ thuật.
- Giá trị dương lớn hơn 1: câu lệnh tác động nhiều hàng.
- `Statement.SUCCESS_NO_INFO` (`-2`): câu lệnh thành công nhưng driver không cung cấp số hàng cụ thể.
- `Statement.EXECUTE_FAILED` (`-3`): dấu hiệu thất bại theo quy ước JDBC; khi batch thất bại, driver thường ném `BatchUpdateException` và Spring dịch thành `DataAccessException`. Không giả định phương thức luôn trả về đầy đủ mảng có `-3`.

Ví dụ `[[1, 1], [1, 0], [1]]` cho thấy ba lô với tổng năm thao tác; thao tác thứ tư không cập nhật hàng nào. **Không được dùng `counts.length` làm số hàng bị ảnh hưởng**, vì đó là số nhóm batch theo đường xử lý batch.

Khi tổng hợp, chỉ cộng các update count **không âm**. Nếu gặp `SUCCESS_NO_INFO`, không thể tính tổng hàng chính xác bằng phép cộng update count; cần đối chiếu dữ liệu sau ghi nếu nghiệp vụ yêu cầu số đếm tuyệt đối. Đừng lặng lẽ cộng `-2` vào tổng hoặc coi mọi kết quả `-2` là thất bại.

## 6. Transaction, lỗi giữa chừng và lô cuối

**Chia batch không đồng nghĩa với chia transaction.** Có ba tình huống cần phân biệt:

1. **Có transaction bao quanh toàn bộ lời gọi:** nếu một phần tử hoặc lô cuối gây lỗi và ngoại lệ truyền ra khỏi `TransactionTemplate` hoặc phương thức `@Transactional` phù hợp, transaction sẽ được rollback theo quy tắc Spring. Với database/engine hỗ trợ transaction, những thay đổi trước đó trong cùng transaction cũng được hoàn tác.
2. **Không có transaction bao quanh:** connection có thể ở chế độ auto-commit; lô đầu thành công có thể đã được commit trước khi lô sau lỗi. Không được tự nhận rằng toàn bộ thao tác luôn "all-or-nothing".
3. **Driver ném lỗi trong `executeBatch()`:** mức độ thực thi trước lúc lỗi, update count và khả năng tiếp tục của batch phụ thuộc driver. Cần kiểm tra cause, `BatchUpdateException`, log có ngữ cảnh và trạng thái DB, không phỏng đoán phần tử nào đã commit chỉ từ độ dài mảng.

Ví dụ sửa dữ liệu đầu vào thành hai phần tử trùng khóa chính (`id = 3`). Lần chèn thứ hai vào cùng khóa sẽ vi phạm ràng buộc `PRIMARY KEY`; nếu lỗi xảy ra bên trong transaction của ví dụ và không bị nuốt, Spring rollback các insert đã làm trước đó. Khi ứng dụng bắt ngoại lệ để thông báo, hãy bắt **bên ngoài** `TransactionTemplate`. Nếu bắt và bỏ qua lỗi **bên trong** transaction callback rồi trả về bình thường, bạn có thể vô tình làm transaction commit khi chưa xử lý trạng thái rollback.

Khi cần retry sau lỗi, hãy thiết kế thao tác **idempotent** (ví dụ khóa nghiệp vụ duy nhất và chính sách upsert thích hợp với DB), xác định ranh giới transaction, và xác minh trạng thái thực tế. Retry mù toàn bộ dữ liệu có thể gây trùng, sai số đếm hoặc phát sinh tác dụng phụ.

## 7. Các trường hợp biên và lỗi phổ biến

### Đầu vào rỗng hoặc nhỏ hơn `batchSize`

Nếu `items.isEmpty()`, không có thao tác SQL nào cần chạy; kết quả thông thường là mảng ngoài rỗng. Nếu có 1 phần tử với `batchSize=100`, phần tử duy nhất chính là lô cuối và vẫn được xử lý. Nếu `n` chia hết cho `batchSize`, không tạo lô rỗng sau cùng.

### `batchSize` không hợp lệ

Dùng `batchSize > 0`. Với `0` hoặc số âm, phép chia lô không có nghĩa; nên chặn đầu vào trước khi gọi API thay vì dựa vào ngoại lệ từ triển khai. Giá trị quá lớn cũng không mặc nhiên nhanh hơn: có thể làm tăng bộ nhớ driver dùng để giữ tham số hoặc vượt giới hạn của DB/driver.

### Bind `null` và kiểu SQL

Đừng gọi `ps.setString(2, null)` một cách tùy tiện nếu driver hoặc schema cần kiểu SQL rõ ràng. Ví dụ nếu `sku` được phép `NULL`:

```java
if (item.sku() == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, item.sku());
}
```

Điều chỉnh theo cột thực tế. Không gán tham số từ đối tượng trước khi gặp giá trị `null` ở đối tượng hiện tại; luôn bind đủ vị trí. Dùng placeholder `?` cho **giá trị dữ liệu**, không nối chuỗi SQL từ input để dựng giá trị. Tên bảng/cột không thể được thay bằng `?`; cần kiểm soát riêng nếu chúng có tính động.

### Khả năng hỗ trợ của driver

Batch thực sự và update count chi tiết do driver quyết định; hiệu quả và cả dạng nhóm trả về có thể khác khi JDBC batching không được hỗ trợ. Cần chạy kiểm thử tích hợp với **driver/DB sản xuất**, nhất là khi phụ thuộc vào `SUCCESS_NO_INFO`, timeout, lỗi giữa lô hoặc thứ tự cập nhật.

### Không để `Collection` lớn tràn bộ nhớ

`batchSize=500` chỉ chia **thao tác gửi đến JDBC**; nó không tự tải dữ liệu theo trang từ nguồn. Nếu `batchArgs` chứa hàng triệu đối tượng đã có sẵn trong `List`, dữ liệu vẫn chiếm bộ nhớ ứng dụng. Với dữ liệu cực lớn, nên đọc theo trang/chunk ở tầng nghiệp vụ, gọi `batchUpdate` cho mỗi chunk và chủ động quyết định phạm vi transaction. Việc ghép nhiều chunk có thể thay đổi tính nguyên tử, vì vậy thiết kế rõ commit/retry/checkpoint.

### Không lẫn các API batch

| API | Đầu vào/callback | Kết quả | Điểm khác biệt |
| --- | --- | --- | --- |
| `batchUpdate(sql, BatchPreparedStatementSetter)` | `setValues(ps, i)` + `getBatchSize()` | `int[]` | Thường dành cho một batch, callback tự lấy phần tử theo chỉ số. |
| `batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` | `setValues(ps, item)` | `int[][]` | Spring chia collection thành nhiều lô và **tự xử lý lô cuối thiếu phần tử**. |
| `InterruptibleBatchPreparedStatementSetter` | Callback theo chỉ số có thể báo hết dữ liệu | `int[]` với overload setter tương ứng | Dùng khi cần báo kết thúc sớm trong cơ chế `BatchPreparedStatementSetter`. |
| `NamedParameterJdbcTemplate.batchUpdate(...)` | Tham số có tên, chẳng hạn `:sku`, nguồn `SqlParameterSource[]` | `int[]` | Cách bind khác; không sử dụng callback `ParameterizedPreparedStatementSetter<T>` của overload đang học. |

Không nên tự thêm `executeBatch()` cho lô cuối theo cách dùng JDBC thuần; với overload được học, Spring đã làm điều đó.

## 8. Cách kiểm thử đúng hành vi lô cuối

Để xác minh code và tránh bỏ sót dữ liệu, kiểm thử tối thiểu các trường hợp:

1. `n = 0` và `batchSize = 2`: không ghi dữ liệu.
2. `n = 1` và `batchSize = 2`: ghi 1 dòng, lô cuối có 1 phần tử.
3. `n = 5` và `batchSize = 2`: có 3 lô cỡ `[2, 2, 1]`, DB lưu đủ 5 dòng.
4. `n = 6` và `batchSize = 3`: có 2 lô đủ `[3, 3]`, không thêm lô rỗng.
5. Một phần tử sai kiểu/vi phạm khóa: quan sát ngoại lệ và rollback khi có transaction, kiểm tra lại DB.
6. Với câu `UPDATE`, có một ID không tồn tại: quan sát update count `0` mà không nhầm với lỗi SQL.

Khi test độc lập H2, có thể assert hình dạng `int[][]` cụ thể như ví dụ. Khi test đa driver hoặc production DB, **kết quả trong DB và bảo đảm transaction** mới là tiêu chí nghiệp vụ chính; update count có thể chứa `SUCCESS_NO_INFO` và không đủ để chứng minh số dòng chính xác.

**Câu hỏi tự kiểm tra:** Với 1.001 phần tử, `batchSize=250`, driver hỗ trợ batching, tất cả lệnh thành công: sẽ có bao nhiêu lô và lô cuối có bao nhiêu phần tử?

**Đáp án:** Có `ceil(1001/250)=5` lô; bốn lô đầu mỗi lô 250 phần tử, lô cuối có **1 phần tử**. Nếu trước đây bạn xử lý bằng vòng lặp chỉ gọi `executeBatch()` mỗi khi đủ 250, bạn sẽ đánh rơi phần tử cuối; overload của Spring xử lý phần dư tự động.

## 9. Ghi nhớ

- `ParameterizedPreparedStatementSetter<T>` bind **từng đối tượng `T`** vào một `PreparedStatement` dùng chung SQL.
- `JdbcTemplate.batchUpdate(sql, collection, batchSize, pss)` chia dữ liệu thành nhiều lô, trả về `int[][]`; **lô cuối không đủ `batchSize` vẫn được thực thi**.
- `batchSize` là ranh giới batch, **không phải** ranh giới transaction; cần `TransactionTemplate` hoặc `@Transactional` phù hợp để kiểm soát atomicity.
- Hiểu `0`, `SUCCESS_NO_INFO` và lỗi batch trước khi tổng hợp kết quả; xác minh dữ liệu thật sau ghi khi tính đúng đắn quan trọng.
- Tự bind đủ tham số, xử lý `null`/SQL types, kiểm tra `batchSize > 0` và test trường hợp lô cuối còn dư.

### Nguồn tham khảo

- Spring Framework Reference — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework `JdbcOperations` Javadoc, overload `batchUpdate` nhận `Collection<T>`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- Java 17 API — `java.sql.Statement` (các hằng update count): https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
