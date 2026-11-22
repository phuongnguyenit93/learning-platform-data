# Chia dữ liệu thành các lô nhỏ để giới hạn bộ nhớ khi cập nhật theo lô

> **Ngữ cảnh:** Spring Framework – Data Access, chủ đề **Cập nhật theo lô**. Mục tiêu là cập nhật nhiều bản ghi bằng JDBC batch, đồng thời chỉ giữ một lượng dữ liệu đầu vào có giới hạn trong bộ nhớ ứng dụng.

## 1. Vì sao cần chia lô?

Giả sử phải cập nhật tên của 2 triệu khách hàng. Nếu đọc toàn bộ 2 triệu đối tượng vào một `List` rồi mới gọi `JdbcTemplate.batchUpdate(...)`, bộ nhớ heap có thể tăng theo tổng số bản ghi. Mỗi đối tượng còn kéo theo chuỗi, mảng và chi phí quản lý đối tượng; trình điều khiển JDBC cũng có thể đệm tham số. Khi dữ liệu lớn, cách này có nguy cơ gây GC kéo dài hoặc `OutOfMemoryError`.

**Chia lô (chunking)** là xử lý tối đa `batchSize` phần tử mỗi lần: lấy một nhóm nhỏ từ nguồn → gửi cùng một câu SQL dạng tham số tới JDBC batch → giải phóng tham chiếu tới nhóm đó → lấy nhóm tiếp theo. Ví dụ `N = 2.001` bản ghi, `batchSize = 500` sẽ thành 5 lô: `500 + 500 + 500 + 500 + 1`.

Điều cần phân biệt:

- **JDBC batch** gom nhiều lần thực thi *cùng một* `PreparedStatement` nhằm giảm các chuyến đi qua mạng và chi phí gọi SQL. Nó chủ yếu là một kỹ thuật tăng hiệu năng.
- **Chunking đầu vào** giới hạn số đối tượng được giữ cùng lúc trong ứng dụng. Đây mới là điều trực tiếp giúp khống chế heap khi nguồn dữ liệu được đọc tuần tự.
- **Transaction** quyết định phạm vi commit/rollback; kết thúc một JDBC batch **không đồng nghĩa** với commit một transaction.
- **`fetchSize`** là gợi ý số hàng đọc về khi truy vấn (phụ thuộc driver), còn **`batchSize`** ở đây là số thao tác ghi gom trong một đợt. Không được nhầm hai tham số.

Với một nguồn dữ liệu thực sự đọc dần, bộ đệm ứng dụng cần khoảng `O(B × S)` bộ nhớ, trong đó `B` là số phần tử mỗi lô và `S` là kích thước trung bình của một phần tử. Nếu nạp toàn bộ nguồn thành `List` trước, bộ nhớ vẫn cỡ `O(N × S)` cho dù gọi JDBC batch với `B` nhỏ. Công thức chỉ mô tả bộ đệm dữ liệu ở tầng ứng dụng, chưa tính bộ nhớ JVM khác, đệm của driver, kết quả trả về hay tài nguyên của cơ sở dữ liệu.

## 2. Chọn đúng API của Spring JDBC

Spring Framework cung cấp một số cách:

| API | Cách xử lý | Điều cần lưu ý về bộ nhớ |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(sql, BatchPreparedStatementSetter)` | `getBatchSize()` cho biết số lần gán tham số trong lời gọi hiện tại; `setValues(...)` điền từng bộ tham số. | Nếu truyền danh sách rất lớn, vẫn giữ danh sách đó; nên gọi cho từng lô nhỏ. |
| `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` | Spring tự chia **collection đã truyền** thành các JDBC batch, trả `int[][]`. | `batchSize` không biến một collection đã nạp hết thành nguồn streaming. Muốn chặn heap, chỉ truyền collection nhỏ lấy dần từ nguồn. |
| `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` | Dùng tham số đặt tên, một phần tử mảng cho mỗi bộ giá trị. | Tạo `SqlParameterSource[]` cho **từng lô**, tránh tạo mảng cho toàn bộ tập dữ liệu. |

Phần dưới dùng `JdbcTemplate` với `Collection<T>` và `ParameterizedPreparedStatementSetter<T>`. SQL được tham số hóa bằng dấu `?`, không nối chuỗi SQL theo dữ liệu. Trình điều khiển hỗ trợ batch tốt thường giảm số round trip, nhưng mức tăng tốc phụ thuộc driver, cấu hình và database; một số driver có thể thực thi lần lượt thay vì tối ưu thành batch thực sự.

## 3. Ví dụ chạy được: đọc dần, giữ tối đa 3 phần tử

Ví dụ dùng **Java 17, Spring JDBC 6.2 và H2** để dễ chạy độc lập. Dữ liệu nguồn là `Iterator` tạo bản ghi khi được yêu cầu; ứng dụng không tạo danh sách tất cả bản ghi trước khi cập nhật.

Tạo cấu trúc:

```text
spring-jdbc-chunks/
├── pom.xml
└── src/main/java/ChunkedBatchDemo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-jdbc-chunks</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.5.252</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ChunkedBatchDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/ChunkedBatchDemo.java`**

```java
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class ChunkedBatchDemo {
    private static final String SQL =
            "UPDATE customer SET full_name = ? WHERE id = ?";

    record NameChange(long id, String newName) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:chunks;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE customer (" +
                "id BIGINT PRIMARY KEY, full_name VARCHAR(100) NOT NULL)");

        for (long id = 1; id <= 7; id++) {
            jdbc.update(
                    "INSERT INTO customer (id, full_name) VALUES (?, ?)",
                    id, "old-" + id);
        }

        // Nguồn tạo từng phần tử khi đọc; không giữ List 7 phần tử.
        Iterator<NameChange> source = new Iterator<>() {
            private long nextId = 1;

            @Override
            public boolean hasNext() {
                return nextId <= 7;
            }

            @Override
            public NameChange next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                long id = nextId++;
                return new NameChange(id, "new-" + id);
            }
        };

        int successfulStatements = updateInChunks(jdbc, source, 3);
        Integer renamedRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer " +
                "WHERE full_name LIKE 'new-%'",
                Integer.class);

        System.out.println("Successful statements: " + successfulStatements);
        System.out.println("Rows now renamed: " + renamedRows);
    }

    static int updateInChunks(JdbcTemplate jdbc,
                              Iterator<NameChange> source,
                              int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be > 0");
        }

        List<NameChange> buffer = new ArrayList<>(batchSize);
        int successfulStatements = 0;

        while (source.hasNext()) {
            buffer.add(source.next());

            if (buffer.size() == batchSize) {
                successfulStatements += executeChunk(jdbc, buffer);
                buffer.clear();
            }
        }

        // Không bỏ quên lô cuối khi số bản ghi không chia hết.
        if (!buffer.isEmpty()) {
            successfulStatements += executeChunk(jdbc, buffer);
            buffer.clear();
        }

        return successfulStatements;
    }

    static int executeChunk(JdbcTemplate jdbc, List<NameChange> chunk) {
        int[][] counts = jdbc.batchUpdate(
                SQL,
                chunk,
                chunk.size(),
                (ps, change) -> {
                    ps.setString(1, change.newName());
                    ps.setLong(2, change.id());
                });

        int accepted = 0;
        for (int[] oneBatch : counts) {
            for (int count : oneBatch) {
                if (count == Statement.EXECUTE_FAILED) {
                    throw new IllegalStateException("Batch entry failed");
                }
                if (count >= 0 || count == Statement.SUCCESS_NO_INFO) {
                    accepted++;
                } else {
                    throw new IllegalStateException(
                            "Unexpected JDBC update count: " + count);
                }
            }
        }

        System.out.println("Chunk size: " + chunk.size());
        return accepted;
    }
}
```

Chạy ở thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn -q compile exec:java
```

Đầu ra dự kiến với H2:

```text
Chunk size: 3
Chunk size: 3
Chunk size: 1
Successful statements: 7
Rows now renamed: 7
```

**Giải thích dòng chảy:**

1. `source.next()` sinh một `NameChange` mỗi lần gọi; trong ví dụ không tồn tại một `List` khổng lồ đầu vào.
2. `buffer` tăng từ 0 đến tối đa 3 phần tử. Đủ 3 thì `executeChunk` chạy SQL cập nhật từng hàng bằng một JDBC batch.
3. Sau khi lệnh thành công, `buffer.clear()` bỏ các tham chiếu đến đối tượng của lô đã xử lý. JVM có thể thu hồi bộ nhớ khi GC; không cần và không nên ép gọi `System.gc()`.
4. Hai lô đầu có 3 phần tử, lô cuối có 1 phần tử. Kiểm tra `!buffer.isEmpty()` giúp không bỏ sót lô cuối.
5. `int[][]` lưu kết quả của các batch trong **lời gọi hiện tại**, thay vì tích lũy tất cả kết quả của hàng triệu lệnh. Trong ví dụ, mỗi lời gọi chỉ chứa một lô nhỏ.

Giá trị JDBC update count cần hiểu đúng: số không âm là số hàng ảnh hưởng được driver báo cáo; `Statement.SUCCESS_NO_INFO` (`-2`) cho biết lệnh thành công nhưng **không biết số hàng**, và `Statement.EXECUTE_FAILED` (`-3`) biểu thị thất bại. Vì vậy ví dụ đếm **số câu lệnh được chấp nhận** thay vì suy ra rằng mỗi câu lệnh chắc chắn cập nhật một hàng. Kết quả `Rows now renamed: 7` là phép kiểm tra trực tiếp trên bảng H2.

> **Giới hạn ví dụ:** `DriverManagerDataSource` và H2 in-memory phù hợp để minh họa. Ứng dụng thật thường dùng `DataSource` có connection pool và nguồn `Iterator` lấy từ file, hàng đợi hoặc bộ đọc dữ liệu được quản lý vòng đời rõ ràng. `Iterator` ở đây là nguồn giả lập; bản thân việc chuyển `hugeList.iterator()` thành `Iterator` sẽ **không** làm `hugeList` biến mất khỏi bộ nhớ.

## 4. Đọc nguồn đúng cách mới thực sự giới hạn heap

**Mẫu chưa đạt mục tiêu:**

```java
// Minh họa anti-pattern, không phải chương trình độc lập.
List<NameChange> all = loadMillionsOfRowsIntoList();
jdbc.batchUpdate(SQL, all, 500, (ps, row) -> {
    ps.setString(1, row.newName());
    ps.setLong(2, row.id());
});
```

Spring có thể chia hoạt động JDBC thành nhiều batch 500 lệnh, nhưng `all` vẫn chứa toàn bộ dữ liệu. Đổi sang vòng lặp dùng `all.subList(from, to)` cũng không giải phóng được danh sách gốc: `subList` chỉ là một view dựa trên danh sách ban đầu.

**Mẫu phù hợp:** nguồn phải cấp dữ liệu dần, ví dụ đọc từng dòng file hoặc truy vấn các trang nhỏ; chỉ đưa tối đa `B` phần tử vào `buffer`; xử lý rồi xóa tham chiếu trước khi đọc tiếp. Các nguồn thực tế:

- **File lớn:** đọc tuần tự bằng `BufferedReader`/`Files.lines(...)` và đóng tài nguyên bằng `try-with-resources`; chỉ parse đủ dữ liệu cho một lô.
- **Database nguồn:** phân trang theo khóa ổn định (chẳng hạn `WHERE id > :lastId ORDER BY id LIMIT :pageSize` nếu database hỗ trợ cú pháp này) hoặc dùng cursor/streaming `ResultSet` khi đã hiểu cách driver xử lý `fetchSize`, transaction và connection. Không gọi `queryForList` để lấy hàng triệu hàng cùng lúc.
- **Message/queue:** chỉ lấy một lượng thông điệp hợp lý, gửi batch, ghi nhận trạng thái xử lý rồi mới nhận tiếp. Phải quyết định cách xử lý thông điệp đã nhận khi batch lỗi.

Nếu cùng một thao tác vừa stream `ResultSet` từ database vừa cập nhật database đó, cần xem xét connection, isolation, cursor và tính nhất quán; không mặc nhiên cho rằng có thể mở một cursor dài rồi thực thi mọi câu UPDATE trên chính connection ấy mà không ảnh hưởng nguồn đọc. Với dữ liệu nhiều và cần restart, phân trang khóa ổn định kèm checkpoint thường dễ kiểm soát hơn.

## 5. Chunk không tự tạo ranh giới giao dịch

Có hai yêu cầu nghiệp vụ khác nhau:

| Kiểu giao dịch | Ý nghĩa | Đổi lại |
| --- | --- | --- |
| **Một transaction bao toàn bộ các chunk** | Nếu có lỗi và rollback, toàn bộ đợt cập nhật cùng quay lui (tùy giao dịch/database). | Transaction có thể kéo dài, giữ lock/connection, tăng áp lực undo/redo log. Heap của bộ đệm nhỏ chưa đủ giải quyết các tài nguyên này. |
| **Một transaction cho mỗi chunk** | Một lô thành công có thể commit rồi mới xử lý lô tiếp. Lock và phạm vi rollback thường nhỏ hơn. | Nếu lô thứ 5 lỗi, bốn lô trước có thể đã commit. Phải có checkpoint, retry và logic tránh ghi lặp. |

Ví dụ trong Spring, `TransactionTemplate` có thể bọc **mỗi lần gọi `executeChunk`** thành một transaction khi không có transaction bao ngoài:

```java
// Đoạn minh họa gắn vào một ứng dụng đã có dataSource, jdbc và chunk.
TransactionTemplate tx = new TransactionTemplate(
        new DataSourceTransactionManager(dataSource));

tx.executeWithoutResult(status -> {
    executeChunk(jdbc, chunk);
});
```

Imports tương ứng: `org.springframework.transaction.support.TransactionTemplate` và `org.springframework.jdbc.datasource.DataSourceTransactionManager`. Đoạn trên **không phải chương trình độc lập**; nó cho thấy ranh giới transaction phải được cấu hình chủ động. Mặc định `TransactionTemplate` dùng propagation `REQUIRED`: nếu đã có transaction bao ngoài, nó tham gia transaction đó và **không** commit riêng mỗi chunk. Tương tự, gắn `@Transactional` lên toàn bộ phương thức chạy vòng lặp thường tạo *một* transaction cho tất cả chunk khi gọi qua Spring proxy. Đừng nhầm một lời gọi `batchUpdate` với một lần commit.

Chọn cách nào tùy yêu cầu **atomicity**. Với tác vụ có thể chạy lại, việc cập nhật theo khóa và thiết kế thao tác idempotent (chạy lại không gây sai lệch) thường hỗ trợ phục hồi theo từng chunk. Ví dụ `SET status = 'DONE' WHERE id = ?` dễ chạy lại hơn `SET balance = balance + ?` nếu không có cơ chế chống áp dụng hai lần.

## 6. Xử lý lỗi, kiểm đếm và chạy lại

- **Không nuốt ngoại lệ:** `JdbcTemplate` chuyển lỗi JDBC thành `DataAccessException`; khi batch lỗi, driver/database có thể đã thực hiện một phần các lệnh. Đừng tự động giả định cả chunk đều chưa tác động.
- **Kiểm soát commit:** với transaction cho từng chunk, chỉ ghi checkpoint sau khi commit thành công. Lưu khóa cuối cùng đã xử lý hoặc ID job/batch ở nơi bền vững. Nếu hệ thống dừng đột ngột, tiếp tục từ checkpoint và đảm bảo thao tác có thể chạy lại.
- **Hiểu count trả về:** `0` có thể là không hàng nào khớp; `SUCCESS_NO_INFO` không thể cộng như số hàng đã cập nhật. Nếu nghiệp vụ phải biết chính xác số hàng, xác minh bằng điều kiện SQL, dữ liệu đích hoặc cơ chế audit phù hợp.
- **Đối phó lỗi tạm thời:** retry ở ranh giới chunk hoặc transaction với backoff khi lỗi phù hợp; kiểm soát unique key, thứ tự xử lý và tính idempotent. Không retry mù mọi lỗi (ví dụ sai cấu trúc SQL hoặc vi phạm dữ liệu).
- **Ngừng khi lỗi:** ví dụ chạy được ở trên ném ngoại lệ và dừng tại chunk lỗi; không `clear()`/tiếp tục vô điều kiện. Trong production, thiết kế thêm báo cáo job, lô thất bại và chiến lược phục hồi rõ ràng.

## 7. Chọn `batchSize` theo đo đạc

Không có giá trị tối ưu chung. Có thể **bắt đầu thử** từ khoảng `100–500` bản ghi/lô đối với câu UPDATE nhỏ, sau đó đo và điều chỉnh; đây chỉ là điểm khởi đầu thực nghiệm, không phải giới hạn của Spring. Một row chứa BLOB lớn có thể cần lô nhỏ hơn nhiều.

Quan sát đồng thời:

1. **Heap và GC:** peak heap, tốc độ cấp phát, thời gian GC; có giữ lại `List`, mảng tham số hoặc kết quả lâu hơn một chunk không?
2. **Throughput:** hàng/giây hoặc lệnh/giây, thời gian mỗi chunk, số lần round trip và hiệu quả của JDBC batch trong driver.
3. **Database:** thời gian giữ lock, transaction log/undo, độ dài transaction, deadlock, giới hạn packet/bind parameters hoặc statement timeout của hệ quản trị.
4. **Độ bền vận hành:** chunk quá lớn làm rollback/retry tốn nhiều hơn; chunk quá nhỏ tạo nhiều lượt gọi và có thể tăng chi phí commit.
5. **Kích thước đối tượng:** số hàng không phản ánh trực tiếp số byte; 500 đối tượng nhẹ khác xa 500 đối tượng có dữ liệu nhị phân lớn.

Một lần thử hữu ích là cố định bộ dữ liệu và SQL, chạy lần lượt với `B = 100`, `B = 500`, `B = 1000`, ghi throughput, peak heap và latency; chọn mức ổn định với database thật. Nếu đọc từ file hoặc cursor, đo riêng tốc độ đọc để tránh nhầm giới hạn nguồn dữ liệu với giới hạn cập nhật.

## 8. Lỗi triển khai thường gặp và cách kiểm tra

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nạp tất cả bản ghi trước khi chia lô | Heap tăng theo `N` | Lấy dữ liệu dần và giữ bộ đệm ≤ `B`. |
| Gọi một batch cực lớn | Driver/DB có thể đệm nhiều tham số, giao dịch lâu | Gọi batch theo nhiều chunk hữu hạn. |
| Quên lô cuối | Mất dữ liệu khi `N % B != 0` | Sau vòng lặp, xử lý nếu buffer chưa rỗng. |
| Không kiểm tra `batchSize <= 0` | Vòng lặp sai hoặc API báo lỗi khó hiểu | Validate đầu vào ngay đầu phương thức. |
| Cho rằng mỗi chunk tự commit | Nhầm atomicity, khó thiết kế rollback | Quy định ranh giới transaction tường minh. |
| Cộng `-2` vào số hàng cập nhật | Thống kê âm hoặc sai | Phân biệt câu lệnh thành công với số hàng ảnh hưởng. |
| Retry sau khi commit một phần mà không có khóa/checkpoint | Ghi trùng hoặc cộng tiền hai lần | Thiết kế idempotency và checkpoint bền vững. |
| Dùng `subList` trên `List` khổng lồ rồi xóa view | Danh sách gốc vẫn bị giữ | Đọc dần từ nguồn, không tạo danh sách gốc lớn. |

**Bộ ca kiểm thử tối thiểu:** nguồn rỗng (`N=0`); đúng một phần tử; `N=B`; `N=B+1` để bắt lỗi lô dư; dữ liệu có `id` không tồn tại (`update count=0`); `batchSize=0` và giá trị âm; lỗi SQL hoặc ràng buộc ở lô giữa; chạy lại một lô đã commit. Trong môi trường thật, theo dõi heap và kết quả dữ liệu đích, không chỉ số lần gọi `batchUpdate`.

## 9. Checklist áp dụng trong Spring Framework

- [ ] Nguồn cấp dữ liệu tuần tự hoặc theo trang nhỏ; không chứa toàn bộ tập dữ liệu trong heap.
- [ ] Chọn `batchSize > 0` và chỉ giữ tối đa `batchSize` đối tượng trong bộ đệm.
- [ ] Dùng `PreparedStatement` tham số hóa; mọi phần tử của batch sử dụng cùng mẫu SQL.
- [ ] Chạy đầy đủ lô cuối và giải phóng tham chiếu sau mỗi lô thành công.
- [ ] Xác định rõ transaction bao toàn bộ hay commit theo chunk.
- [ ] Xử lý `DataAccessException`, các giá trị update count đặc biệt và retry có kiểm soát.
- [ ] Đo heap, GC, throughput và tải database với quy mô dữ liệu thật.

**Ghi nhớ:** `batchSize` nhỏ chỉ có ý nghĩa giới hạn bộ nhớ **khi cả đường đi của dữ liệu đều theo lô**: đọc → giữ trong buffer → batch update → bỏ tham chiếu. Nếu nguồn đã nạp hết vào `List`, chia batch ở tầng JDBC giúp tổ chức các lệnh SQL nhưng không lấy lại bộ nhớ đã dùng để nạp dữ liệu.

### Tài liệu tham khảo

- Spring Framework 6.2 – JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html
- Spring Framework – Programmatic Transaction Management (`TransactionTemplate`): https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Java SE – `java.sql.Statement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
