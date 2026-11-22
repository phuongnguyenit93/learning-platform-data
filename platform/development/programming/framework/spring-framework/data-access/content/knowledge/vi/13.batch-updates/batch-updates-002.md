# BatchPreparedStatementSetter và kích thước lô trong Spring JDBC

## 1. Mục tiêu và bối cảnh

Khi cần chèn hoặc cập nhật hàng trăm, hàng nghìn bản ghi bằng **cùng một câu SQL nhưng khác tham số**, gọi `JdbcTemplate.update(...)` từng dòng có thể tạo nhiều lượt giao tiếp với cơ sở dữ liệu. JDBC batching gom các bộ tham số thành một nhóm, để driver có cơ hội tối ưu việc thực thi và giảm chi phí qua lại giữa ứng dụng và database.

`BatchPreparedStatementSetter` là callback của Spring JDBC dùng với:

```java
int[] counts = jdbcTemplate.batchUpdate(sql, batchPreparedStatementSetter);
```

Nó quyết định **giá trị tham số cho từng phần tử** và **số phần tử của một lần gọi batch**. Bài này tập trung vào cách hiện thực hai phương thức đó, cách kiểm soát kích thước lô, đọc kết quả và lựa chọn cấu hình phù hợp. Đây là JDBC batch, khác với sản phẩm Spring Batch chuyên điều phối job.

Sau bài học, bạn có thể:
- Viết `BatchPreparedStatementSetter` đúng chỉ số và kiểu dữ liệu.
- Phân biệt tổng số bản ghi với kích thước của một lô thực thi.
- Chia dữ liệu lớn thành nhiều lô, kể cả lô cuối có ít phần tử.
- Hiểu ý nghĩa `int[]` mà `batchUpdate` trả về và xử lý lỗi/transaction hợp lý.
- Đo và điều chỉnh batch size dựa trên số liệu thực tế.

## 2. Hợp đồng của BatchPreparedStatementSetter

Interface nằm tại `org.springframework.jdbc.core.BatchPreparedStatementSetter`, gồm đúng hai phương thức:

```java
public interface BatchPreparedStatementSetter {
    void setValues(PreparedStatement ps, int i) throws SQLException;
    int getBatchSize();
}
```

- `getBatchSize()` trả về **số lần gắn tham số trong batch hiện tại**. Với danh sách 75 phần tử truyền vào một lần, thường trả về 75. Giá trị này **không phải cấu hình tự động cắt danh sách lớn thành từng nhóm**.
- `setValues(ps, i)` được gọi để gắn tham số cho phần tử thứ `i`; `i` bắt đầu từ **0**. Ngược lại, vị trí `?` trong JDBC `PreparedStatement` bắt đầu từ **1**: `ps.setLong(1, ...)` là tham số đầu tiên.
- Một lần gọi `batchUpdate(sql, pss)` tái sử dụng **cùng một SQL có dấu `?`**. Mỗi lần `setValues` phải điền đầy đủ các tham số tương ứng với SQL đó; không ghép dữ liệu người dùng trực tiếp vào chuỗi SQL.
- `SQLException` trong callback được `JdbcTemplate` xử lý và chuyển thành hệ ngoại lệ `DataAccessException` thích hợp. Không cần tự nuốt ngoại lệ trong `setValues`.

Luồng khái niệm:

```text
Danh sách dữ liệu → getBatchSize()
                   → setValues(ps, 0), setValues(ps, 1), ...
                   → JDBC addBatch / executeBatch
                   → int[] updateCounts
```

Driver JDBC quyết định mức tối ưu thực tế. Theo hợp đồng API, nếu driver không hỗ trợ batch, `JdbcTemplate` có thể thực hiện các update riêng lẻ trên cùng `PreparedStatement`; vì thế batching không bảo đảm luôn nhanh hơn.

## 3. Ví dụ Java 17+ có thể chạy: chia 5 bản ghi thành lô 2

Ví dụ độc lập sử dụng Spring JDBC và H2 trong bộ nhớ, không yêu cầu Spring Boot hay máy chủ database. Cấu trúc:

```text
spring-jdbc-batch-demo/
├── pom.xml
└── src/main/java/demo/BatchDemo.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jdbc-batch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.21</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BatchDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/BatchDemo.java`**:

```java
package demo;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

public class BatchDemo {

    record Item(long id, String sku, int stock) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
            CREATE TABLE inventory (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(32) NOT NULL,
                stock INT NOT NULL
            )
            """);

        List<Item> items = List.of(
            new Item(1L, "A-01", 10),
            new Item(2L, "A-02", 20),
            new Item(3L, "B-01", 30),
            new Item(4L, "B-02", 40),
            new Item(5L, "C-01", 50)
        );

        int batchSize = 2;
        int batchNumber = 0;
        String sql = "INSERT INTO inventory (id, sku, stock) VALUES (?, ?, ?)";

        for (int from = 0; from < items.size(); from += batchSize) {
            List<Item> chunk = items.subList(
                from, Math.min(from + batchSize, items.size())
            );

            int[] counts = jdbc.batchUpdate(sql, new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int i)
                        throws SQLException {
                    Item item = chunk.get(i);
                    ps.setLong(1, item.id());
                    ps.setString(2, item.sku());
                    ps.setInt(3, item.stock());
                }

                @Override
                public int getBatchSize() {
                    return chunk.size();
                }
            });

            System.out.println("Batch " + (++batchNumber)
                + ": " + Arrays.toString(counts));
        }

        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM inventory", Integer.class
        );
        System.out.println("Total rows: " + total);
    }
}
```

Chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Đầu ra với H2 đã khai báo:

```text
Batch 1: [1, 1]
Batch 2: [1, 1]
Batch 3: [1]
Total rows: 5
```

Giải thích từng bước:

1. SQL có ba placeholder `?`, nên `setValues` đặt `id` vào vị trí 1, `sku` vào vị trí 2, `stock` vào vị trí 3.
2. Vòng ngoài tạo ba nhóm kích thước lần lượt là 2, 2, 1. `getBatchSize()` trả về độ dài **thực tế của `chunk`**, nên lô cuối không truy cập ngoài danh sách.
3. `i` trong mỗi lô lại bắt đầu từ 0; `chunk.get(i)` ánh xạ chính xác sang bản ghi của lô đó.
4. Mỗi lệnh `INSERT` của ví dụ H2 tác động một hàng, do đó mảng đếm là `[1, 1]` hoặc `[1]`. Các driver/database khác có thể trả mã đặc biệt thay vì số hàng cụ thể.

Mẫu này minh họa giới hạn **số phần tử được gửi trong mỗi lần gọi JDBC batch**. Vì `items` đã được nạp toàn bộ vào bộ nhớ, nó chưa giải quyết bài toán đọc đầu vào hàng triệu dòng; trường hợp đó cần đọc theo trang, cursor hoặc luồng có giới hạn bộ đệm.

## 4. Phân biệt kích thước lô và tổng số bản ghi

Gọi `jdbc.batchUpdate(sql, pss)` một lần với `getBatchSize() = 50_000` nghĩa là một batch có 50.000 bộ tham số; **không tự động tách thành 100 lô 500 bản ghi**. Muốn giới hạn mỗi batch ở 500, phải chia tập đầu vào, hoặc dùng API batch có tham số kích thước lô.

Với `N` phần tử và kích thước mục tiêu `B > 0`:

- Số batch = `ceil(N / B)`.
- Các batch trước thường có `B` phần tử.
- Batch cuối có `N % B` phần tử nếu phần dư khác 0.
- Ví dụ `N = 1.205`, `B = 500` → ba batch: `500 + 500 + 205`.
- `N = 0` → không có phần tử nào để ghi; có thể trả kết quả rỗng ngay.

Trong code, tránh viết `getBatchSize() { return 500; }` khi danh sách thực tế chỉ có 205 phần tử. Giá trị trả về phải phù hợp phạm vi chỉ số mà `setValues` có thể truy cập.

Nếu có danh sách `List<Item>`, Spring JDBC còn cung cấp overload quản lý việc chia lô:

```java
int batchSize = 500;
int[][] countsByBatch = jdbc.batchUpdate(
    "INSERT INTO inventory (id, sku, stock) VALUES (?, ?, ?)",
    items,
    batchSize,
    (PreparedStatement ps, Item item) -> {
        ps.setLong(1, item.id());
        ps.setString(2, item.sku());
        ps.setInt(3, item.stock());
    }
);
```

Đây là `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)`; khác với overload nhận `BatchPreparedStatementSetter` trong ví dụ chính. Với overload này, framework chia danh sách theo `batchSize` và trả `int[][]`: mảng ngoài theo từng batch, mảng trong theo từng phần tử. Chỉ sử dụng đoạn mã trên **bên trong phương thức đã có `jdbc` và `items`** tương ứng; nó là ví dụ API bổ sung, không phải một chương trình Java độc lập.

## 5. Đọc kết quả update counts chính xác

Với `batchUpdate(String, BatchPreparedStatementSetter)`, kiểu trả về là `int[]`. Mỗi phần tử tương ứng với một thao tác trong batch, nhưng **không phải lúc nào cũng là số dương**.

| Giá trị | Ý nghĩa |
|---|---|
| `n >= 0` | Số hàng bị tác động mà driver báo; `0` có thể xảy ra với `UPDATE` không tìm thấy bản ghi. |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Thao tác thành công, nhưng driver không cung cấp số hàng cụ thể. |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver báo thao tác thất bại trong kết quả batch; nhiều trường hợp sẽ ném `BatchUpdateException` thay vì trả về kết quả bình thường. |

Không cộng vô điều kiện mọi phần tử của `counts` để kết luận “tổng số hàng đã ghi”: giá trị `-2` không phải âm hai hàng và `-3` không phải âm ba hàng. Nếu nghiệp vụ cần biết bản ghi nào thành công, hãy phối hợp counts với lỗi JDBC, khóa nghiệp vụ và truy vấn đối soát; không tự suy luận rằng toàn batch là nguyên tử chỉ từ `int[]`.

Ví dụ kiểm tra kết quả khi không có ngoại lệ:

```java
for (int count : counts) {
    if (count == java.sql.Statement.SUCCESS_NO_INFO) {
        // Đã thành công nhưng số hàng không rõ.
    } else if (count == java.sql.Statement.EXECUTE_FAILED) {
        // Cần điều tra lỗi theo driver và trạng thái transaction.
    } else if (count == 0) {
        // Có thể là UPDATE không khớp hàng nào.
    } else {
        // count > 0: số hàng bị tác động mà driver cung cấp.
    }
}
```

Thông thường `JdbcTemplate` chuyển lỗi SQL thành `DataAccessException`. Khi một phần batch lỗi, database/driver có thể đã thực thi một số phần tử trước đó; việc các thay đổi đó có bị rollback hay không phụ thuộc **transaction đang bao quanh công việc**.

## 6. Batch size bao nhiêu là hợp lý?

Không có con số cố định đúng với mọi hệ thống. Số 100, 500 hoặc 1.000 chỉ là **điểm khởi đầu để đo**, không phải mặc định bắt buộc của `BatchPreparedStatementSetter`.

| Batch size | Lợi ích có thể có | Đánh đổi có thể gặp |
|---|---|---|
| Quá nhỏ, ví dụ 1–10 | Ít dữ liệu chờ trong mỗi batch, lỗi dễ khoanh vùng | Nhiều lần gọi driver và round trip; thông lượng có thể thấp |
| Vừa phải, ví dụ 100–1.000 | Thường cân bằng chi phí gọi và lượng dữ liệu trong lô | Cần đo với loại SQL, driver, database thực tế |
| Rất lớn, ví dụ 10.000+ | Ít lần gọi `executeBatch` hơn | Tốn bộ nhớ/bộ đệm, giữ tài nguyên lâu, khó xử lý batch lỗi, có thể chạm giới hạn driver/database |

Các yếu tố quyết định thực tế:

1. **Độ lớn của mỗi bản ghi:** 500 dòng với vài cột số khác hẳn 500 dòng chứa chuỗi dài hoặc dữ liệu nhị phân.
2. **Driver và database:** hỗ trợ JDBC batch, cách rewrite SQL, giới hạn tham số/thông điệp, độ trễ mạng và phiên bản driver tạo khác biệt đáng kể.
3. **Câu SQL:** `INSERT` đơn giản khác `UPDATE` có điều kiện, trigger, kiểm tra khóa ngoại, index và unique constraint.
4. **Transaction và cạnh tranh:** batch lớn có thể tăng thời gian giữ lock hoặc thời gian xử lý một transaction, ảnh hưởng các request khác.
5. **Tài nguyên:** heap, pool kết nối, timeout, log giao dịch, I/O, CPU và kích thước packet đều có thể trở thành nút thắt.
6. **Yêu cầu nghiệp vụ:** mức cho phép ghi một phần, khả năng retry, yêu cầu đối soát và idempotency.

Cách đo nên làm:

- Tạo dataset giống dữ liệu sản xuất, cùng index và tỷ lệ insert/update; có thể thử các mức `100 → 500 → 1.000` sau khi đo baseline.
- Đo **throughput** (bản ghi/giây), tổng thời gian, độ trễ từng batch và p95, số lần gọi database, CPU/heap, lock wait, timeout và tỷ lệ lỗi.
- Chạy lặp lại sau warm-up hợp lý; kiểm tra kết quả đã ghi, không chỉ thời gian của vòng lặp Java.
- Chọn mức nhỏ nhất đạt thông lượng mục tiêu mà vẫn đáp ứng giới hạn bộ nhớ, độ trễ, thời gian giữ lock và yêu cầu khôi phục lỗi. Không mặc định “batch càng lớn càng nhanh”.

Đôi khi driver có tùy chọn tăng tốc batch (chẳng hạn cơ chế viết lại nhiều lệnh insert thành nhiều hàng). Cần kiểm tra tài liệu của **đúng phiên bản driver** và benchmark lại vì hiệu quả và counts có thể thay đổi.

## 7. Transaction, lỗi giữa batch và retry

**Batch không đồng nghĩa transaction.** Batch mô tả cách nhóm thao tác SQL; transaction quyết định phạm vi commit/rollback.

- Nếu các batch chạy trong **một transaction** Spring (ví dụ phương thức service được gọi qua proxy `@Transactional` cùng transaction manager thích hợp), lỗi unchecked như `DataAccessException` thường dẫn đến rollback cả transaction theo mặc định.
- Nếu **không có transaction bao quanh** hoặc chủ động commit mỗi chunk, những batch đã thực thi/commit có thể tồn tại khi batch sau thất bại. Mức độ commit còn tùy cấu hình auto-commit và driver.
- Chia 10.000 bản ghi thành 20 lần gọi `batchUpdate` **không tự tạo 20 transaction**. Muốn transaction theo chunk, phải xác định ranh giới riêng, ví dụ dùng `TransactionTemplate` cho từng chunk.
- Transaction rất dài giúp rollback nguyên khối nhưng có thể tăng thời gian giữ lock, log và rủi ro timeout; transaction theo chunk giảm phạm vi lỗi nhưng đòi hỏi xử lý trạng thái hoàn tất một phần.

Một chính sách retry an toàn phải trả lời: “Nếu lô trước đã commit nhưng ứng dụng không nhận được phản hồi, ghi lại cùng dữ liệu có tạo bản ghi trùng không?”. Cân nhắc khóa duy nhất theo nghiệp vụ, thao tác idempotent, `UPSERT`/`ON CONFLICT` theo hệ quản trị phù hợp, checkpoint và đối soát trước khi retry. Không tự động retry toàn bộ dữ liệu khi chưa biết trạng thái commit.

Nếu cần chẩn đoán lỗi từng hàng, có thể lần theo nguyên nhân JDBC `BatchUpdateException` và `getUpdateCounts()`, nhưng mã số/khả năng xác định hàng lỗi tùy driver; không dùng chúng làm bằng chứng giao dịch đã commit.

## 8. Các lỗi thường gặp

**Sai chỉ số:** `i` của danh sách bắt đầu 0, nhưng `PreparedStatement` bắt đầu 1. `ps.setString(0, ...)` là sai.

**Kích thước cố định sai:** Trả `100` ở `getBatchSize()` dù lô cuối chỉ còn 17 phần tử dẫn đến lỗi truy cập phần tử hoặc gắn tham số sai. Luôn dùng `chunk.size()` khi xử lý từng chunk.

**Thiếu/thừa tham số:** SQL có `?, ?, ?` thì mỗi `setValues` phải gắn đúng ba vị trí và đúng kiểu. Khi giá trị nullable, nên dùng `ps.setNull(index, java.sql.Types.VARCHAR)` hoặc setter phù hợp; không nối chuỗi thủ công để biểu diễn `NULL`.

**Nhầm hiệu quả của batching:** Một danh sách lớn với `getBatchSize() = items.size()` không có giới hạn bộ nhớ. Muốn xử lý dữ liệu khổng lồ, đọc đầu vào theo đợt và gọi `batchUpdate` nhiều lần.

**Bỏ qua kết quả âm:** `SUCCESS_NO_INFO` là thành công mà không biết row count, không phải thất bại. Không sum mảng đếm mà thiếu xử lý mã đặc biệt.

**Giả định tự rollback:** Spring JDBC chỉ thực thi câu lệnh và dịch ngoại lệ; rollback phụ thuộc transaction đã thiết lập. Kiểm tra transaction thực tế trước khi thiết kế retry.

**Tối ưu theo số “magic”:** Chọn 1.000 vì nghe nhanh hơn 100 mà không đo kích thước dữ liệu, driver, SQL, lock và thời gian hoàn thành; dễ làm thông lượng hoặc độ ổn định kém đi.

## 9. Checklist áp dụng trong dự án

1. Xác nhận các bản ghi dùng chung một mẫu SQL có `?` và cơ chế bind tham số đủ loại dữ liệu.
2. Định nghĩa giới hạn batch size dương; xử lý danh sách trống và lô cuối đúng số phần tử.
3. Chọn `BatchPreparedStatementSetter` khi cần điều khiển cách bind từng index; chọn overload với `ParameterizedPreparedStatementSetter` khi muốn Spring chia `Collection` theo `batchSize`.
4. Rà soát constraints, index, hành vi khi trùng khóa và quy tắc cập nhật.
5. Thiết kế phạm vi transaction, rollback và retry trước khi chạy dữ liệu quan trọng.
6. Kiểm tra `counts`, ngoại lệ, số bản ghi trong database và metrics với dữ liệu thử.
7. Benchmark nhiều batch size trên driver/database thực tế rồi cố định cấu hình đã chứng minh hiệu quả.

## 10. Câu hỏi tự kiểm tra

1. Với 1.205 bản ghi và batch size 500, có bao nhiêu lô và lô cuối có bao nhiêu phần tử? **Đáp án:** ba lô, lần lượt 500, 500, 205.
2. `getBatchSize() = 500` có khiến `JdbcTemplate` tự chia danh sách 20.000 bản ghi thành 40 lần gọi không? **Không.** Overload `BatchPreparedStatementSetter` chỉ xử lý số phần tử được callback cung cấp trong một lần gọi. Cần tự chia hoặc chọn overload có tham số batch size.
3. Tại sao `setValues(ps, 0)` vẫn phải gọi `ps.setLong(1, id)`? Vì chỉ số phần tử `i` và chỉ số tham số `PreparedStatement` dùng hai quy ước khác nhau: 0-based và 1-based.
4. `counts = [1, -2, 0]` có nghĩa gì? Một thao tác ảnh hưởng một hàng, một thao tác thành công nhưng row count không rõ, và một thao tác có count bằng 0; không thể cộng thành số hàng ghi đáng tin cậy.
5. Chia thành 20 batch có bảo đảm mỗi batch tự commit không? **Không.** Phạm vi commit do transaction/auto-commit quyết định.

## Tài liệu tham khảo

- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Javadoc — `BatchPreparedStatementSetter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/BatchPreparedStatementSetter.html
- Javadoc — `JdbcOperations.batchUpdate`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
