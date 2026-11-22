# Batch từ danh sách `Object[]` hoặc `SqlParameterSource` trong Spring JDBC

## 1. Bài toán và ý tưởng cốt lõi

Khi cần thêm, sửa hoặc xóa nhiều bản ghi bằng **cùng một câu SQL** nhưng với các bộ tham số khác nhau, gọi `update(...)` từng dòng thường tạo nhiều lần gửi lệnh tới JDBC driver. Spring JDBC cung cấp `batchUpdate(...)` để truyền cả tập tham số, giảm chi phí lặp ở tầng ứng dụng và có thể giảm round-trip tới cơ sở dữ liệu, tùy driver và cách driver triển khai batching.

Ví dụ, tăng lương cho ba nhân viên không phải ba mẫu SQL khác nhau: câu lệnh vẫn là `UPDATE employee SET salary = ? WHERE id = ?`, chỉ các giá trị `salary` và `id` thay đổi. Một phần tử của batch tương ứng với **một lần thực thi SQL cho một bộ tham số**.

Quy trình khái niệm: tạo một `PreparedStatement` cho SQL → gắn tham số của từng dòng → thêm dòng vào batch → JDBC thực thi batch → trả số bản ghi ảnh hưởng cho từng phần tử. Spring quản lý statement, tài nguyên, chuyển đổi `SQLException` thành `DataAccessException`. Việc driver có dùng JDBC batch thực sự hay thực hiện nhiều cập nhật riêng là phụ thuộc khả năng của driver.

**Hai cách biểu diễn tham số cần nắm:**
- **Theo vị trí:** `JdbcTemplate.batchUpdate(sql, List<Object[]>)`. Một `Object[]` là các giá trị ứng với dấu `?` theo thứ tự từ trái sang phải.
- **Theo tên:** `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])`. Mỗi `SqlParameterSource` cung cấp các giá trị theo tên `:id`, `:salary`…; thứ tự đặt giá trị trong đối tượng không quyết định vị trí trong SQL.

Cả hai đều là **DML batch** (`INSERT`, `UPDATE`, `DELETE`), không đồng nghĩa với một câu `INSERT ... VALUES (...), (...)` duy nhất, không tự tạo transaction và không tự đảm bảo toàn bộ batch thành công hoặc rollback.

## 2. API và cách chọn

| Tình huống | API | Hình dạng tham số | Kết quả |
|---|---|---|---|
| SQL dùng `?`, dữ liệu dạng mảng theo cột | `JdbcTemplate.batchUpdate(String, List<Object[]>)` | `List<Object[]>`: mỗi mảng là một dòng | `int[]` |
| Cần khai báo loại SQL rõ ràng, đặc biệt với `null` | `JdbcTemplate.batchUpdate(String, List<Object[]>, int[] argTypes)` | Thêm mảng `java.sql.Types` cùng thứ tự với dấu `?` | `int[]` |
| SQL dùng tham số tên, dữ liệu là map/bean | `NamedParameterJdbcTemplate.batchUpdate(String, SqlParameterSource[])` | Một `SqlParameterSource` cho mỗi dòng | `int[]` |
| Có danh sách bean hoặc map cần chuyển nhanh | `SqlParameterSourceUtils.createBatch(Collection<?>)` | Trả `SqlParameterSource[]` cho lời gọi phía trên | `SqlParameterSource[]` |

Chọn `Object[]` khi thứ tự cột ngắn và rõ, dữ liệu đầu vào đã là tuple. Chọn `SqlParameterSource` khi có nhiều trường, muốn giảm rủi ro đổi nhầm vị trí, hoặc muốn dùng trực tiếp JavaBean/map. Cả hai đều dùng tham số ràng buộc (bind variables), tránh nối giá trị người dùng trực tiếp vào chuỗi SQL.

**Quy tắc bắt buộc:** mọi phần tử trong cùng một batch dùng cùng cấu trúc SQL; các `Object[]` phải có đúng số giá trị bằng số dấu `?`, còn mọi `SqlParameterSource` phải cung cấp đủ tên mà câu SQL sử dụng.

## 3. Ví dụ chạy độc lập với Java 17 + Maven + H2

Ví dụ sau chủ động minh họa **cả ba đường đi**: `List<Object[]>` để thêm nhân viên; `MapSqlParameterSource[]` để cập nhật hai người; và `SqlParameterSourceUtils.createBatch(List<JavaBean>)` để cập nhật người còn lại. Đây là chương trình Java chạy đầy đủ, không cần khởi động Spring Boot.

Tạo cấu trúc tệp:

~~~text
spring-jdbc-batch-demo/
├── pom.xml
└── src/main/java/demo/BatchDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-jdbc-batch-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/BatchDemo.java`**

~~~java
package demo;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;

public class BatchDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE employee (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    salary INTEGER NOT NULL,
                    note VARCHAR(100)
                )
                """);

        // 1) Một Object[] ứng với các dấu ? theo đúng thứ tự SQL.
        List<Object[]> inserts = List.of(
                new Object[] {1L, "An", 100, null},
                new Object[] {2L, "Binh", 200, "thu viec"},
                new Object[] {3L, "Chi", 300, null}
        );

        int[] inserted = jdbc.batchUpdate(
                "INSERT INTO employee (id, name, salary, note) " +
                "VALUES (?, ?, ?, ?)",
                inserts,
                new int[] {
                        Types.BIGINT, Types.VARCHAR,
                        Types.INTEGER, Types.VARCHAR
                }
        );
        System.out.println("INSERT=" + Arrays.toString(inserted));

        // 2) Mỗi MapSqlParameterSource có tên trùng :id và :salary.
        SqlParameterSource[] changes = {
                new MapSqlParameterSource()
                        .addValue("id", 1L, Types.BIGINT)
                        .addValue("salary", 120, Types.INTEGER),
                new MapSqlParameterSource()
                        .addValue("id", 3L, Types.BIGINT)
                        .addValue("salary", 330, Types.INTEGER)
        };

        int[] updatedByMap = named.batchUpdate(
                "UPDATE employee SET salary = :salary WHERE id = :id",
                changes
        );
        System.out.println("UPDATE_MAP=" + Arrays.toString(updatedByMap));

        // 3) Chuyển collection JavaBean thành SqlParameterSource[].
        List<SalaryChange> beanChanges = List.of(
                new SalaryChange(2L, 220)
        );
        int[] updatedByBean = named.batchUpdate(
                "UPDATE employee SET salary = :salary WHERE id = :id",
                SqlParameterSourceUtils.createBatch(beanChanges)
        );
        System.out.println("UPDATE_BEAN=" +
                Arrays.toString(updatedByBean));

        List<Integer> finalSalaries = jdbc.queryForList(
                "SELECT salary FROM employee ORDER BY id",
                Integer.class
        );
        System.out.println("FINAL=" + finalSalaries);
    }

    public static final class SalaryChange {
        private final long id;
        private final int salary;

        public SalaryChange(long id, int salary) {
            this.id = id;
            this.salary = salary;
        }

        public long getId() {
            return id;
        }

        public int getSalary() {
            return salary;
        }
    }
}
~~~

Trong thư mục chứa `pom.xml`, cần có JDK 17+ và Maven; chạy:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.BatchDemo"
~~~

**Đầu ra phần chương trình trên H2:**

~~~text
INSERT=[1, 1, 1]
UPDATE_MAP=[1, 1]
UPDATE_BEAN=[1]
FINAL=[120, 220, 330]
~~~

Lần `INSERT` tạo ba dòng, lần cập nhật theo map đổi lương cho id 1 và 3, lần cập nhật theo JavaBean đổi lương cho id 2. Các giá trị 1 là số hàng mà từng câu lệnh DML tác động trong ví dụ H2 này; trên driver/DB khác, mã đếm có thể là giá trị JDBC đặc biệt (phần 6).

## 4. Hiểu chính xác `List<Object[]>`

Với SQL:

~~~sql
INSERT INTO employee (id, name, salary, note) VALUES (?, ?, ?, ?)
~~~

Ánh xạ tham số của phần tử `new Object[] {1L, "An", 100, null}` là:

| Vị trí dấu `?` | Cột | Giá trị | SQL type trong ví dụ |
|---|---|---|---|
| 1 | `id` | `1L` | `Types.BIGINT` |
| 2 | `name` | `"An"` | `Types.VARCHAR` |
| 3 | `salary` | `100` | `Types.INTEGER` |
| 4 | `note` | `null` | `Types.VARCHAR` |

- **Đúng số lượng và thứ tự:** nếu đảo `id` và `salary`, dữ liệu có thể sai hoặc bị DB từ chối; tên biến Java không giúp JDBC tự xác định vị trí.
- **`argTypes` là mảng kiểu của *các vị trí tham số*, dùng chung cho mọi dòng**, không phải một mảng kiểu cho từng bản ghi. Dùng hằng của `java.sql.Types` thay vì mã số tự chế.
- Nếu mọi giá trị/driver đều suy luận kiểu tốt, có thể dùng overload hai tham số: `jdbc.batchUpdate(sql, inserts)`. Với cột có giá trị `null` hoặc driver suy luận không ổn, overload ba tham số làm kiểu SQL rõ ràng hơn.
- Với mỗi câu SQL, giữ thứ tự biểu thức và danh sách mảng đồng bộ. Thay cấu trúc cột mà quên sửa các mảng là lỗi khó nhìn thấy khi nhiều cột cùng kiểu.

Ví dụ trên sử dụng `List.of(...)` chứa các **mảng không null**; một phần tử *bên trong* mảng có thể là `null`. Đừng nhầm với `List.of(null)`, vốn không chấp nhận phần tử null.

## 5. Hiểu `SqlParameterSource[]` và cách tạo nhanh

`NamedParameterJdbcTemplate` xử lý SQL dùng tên, chẳng hạn:

~~~sql
UPDATE employee SET salary = :salary WHERE id = :id
~~~

Ở mỗi phần tử của `SqlParameterSource[]`, hai tham số `salary` và `id` được tra theo **tên**. Việc gọi `addValue("id", ...)` trước `addValue("salary", ...)` vẫn đúng, dù `:salary` đứng trước `:id` trong SQL.

**`MapSqlParameterSource`:** phù hợp khi dữ liệu được lắp ghép động, cần khai báo rõ SQL type, hoặc phải truyền null có kiểu:

~~~java
SqlParameterSource row = new MapSqlParameterSource()
        .addValue("id", 10L, Types.BIGINT)
        .addValue("note", null, Types.VARCHAR);

// Dùng row bên trong một SqlParameterSource[] tương ứng với SQL
// UPDATE employee SET note = :note WHERE id = :id
~~~

Đoạn trên chỉ minh họa cách gắn tham số, không phải chương trình chạy độc lập; id 10 chưa được tạo ở ví dụ H2.

**`BeanPropertySqlParameterSource`:** lấy tham số từ thuộc tính đối tượng, thông thường qua getter `getId()`, `getSalary()`. `SqlParameterSourceUtils.createBatch(beanChanges)` sẽ tạo một nguồn tham số cho mỗi bean. Tên thuộc tính phải khớp tên tham số trong SQL; đặt `getEmployeeId()` mà SQL dùng `:id` sẽ không tự ghép đúng.

**Từ map hoặc bean có sẵn:** helper `SqlParameterSourceUtils.createBatch(...)` nhận collection/mảng chứa map với khóa kiểu String hoặc bean. Ví dụ minh họa một batch tham số cho SQL cập nhật lương:

~~~java
List<java.util.Map<String, Object>> rows = List.of(
        java.util.Map.of("id", 1L, "salary", 130),
        java.util.Map.of("id", 3L, "salary", 340)
);
SqlParameterSource[] batch =
        SqlParameterSourceUtils.createBatch(rows);
int[] counts = named.batchUpdate(
        "UPDATE employee SET salary = :salary WHERE id = :id",
        batch
);
~~~

Đoạn này giả định đã có biến `named` và các dòng id 1, 3; không nằm trong chương trình `BatchDemo` chính. `Map.of(...)` không hỗ trợ key hoặc value null; khi cần null, dùng `MapSqlParameterSource.addValue(..., Types.XXX)` hoặc một map hỗ trợ null.

**Các lựa chọn gần nhau:** `NamedParameterJdbcTemplate` cũng có overload nhận `Map<String, ?>[]`. Tuy vậy, dùng `SqlParameterSource[]` đặc biệt tiện khi cần mang theo metadata của kiểu SQL hoặc chuyển từ danh sách bean. Hai mảng này **không** phải `Object[][]`: `Object[]` ánh xạ theo *vị trí*, còn `SqlParameterSource` ánh xạ theo *tên*.

## 6. Diễn giải `int[]`, lỗi và transaction

`batchUpdate(...)` trả `int[]`: vị trí thứ i tương ứng phần tử thứ i đã gửi. Các giá trị có thể là:

| Kết quả một phần tử | Ý nghĩa |
|---|---|
| `0` | Câu lệnh không làm ảnh hưởng hàng nào (ví dụ `WHERE id` không khớp), không nhất thiết là exception |
| `1`, `2`, ... | Driver báo số hàng đã bị tác động bởi câu lệnh tương ứng |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Driver báo thực thi thành công nhưng không cung cấp số hàng |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver báo phần tử thất bại nếu driver trả trạng thái này; nhiều trường hợp lỗi làm cả lời gọi ném exception |

Vì có mã âm, **không mặc định dùng `Arrays.stream(counts).sum()` để kết luận tổng số hàng thực tế**, và không mặc định mọi phần tử phải trả 1: lệnh UPDATE có thể khớp 0 dòng. Nếu API ném `DataAccessException`, thường không nhận được mảng kết quả theo đường chạy thành công; thông tin lỗi chi tiết phụ thuộc `SQLException`/`BatchUpdateException` và driver.

**Batch không đồng nghĩa transaction.** Nếu một phần tử vi phạm khóa duy nhất hoặc ràng buộc khác, các phần tử trước đó có thể đã được driver thực thi. Với một nghiệp vụ cần tính toàn vẹn, gọi DAO trong transaction Spring (ví dụ method service gắn `@Transactional` với transaction manager đúng `DataSource`). Theo mặc định, exception không kiểm tra (như `DataAccessException`) thoát khỏi method transaction sẽ đánh dấu rollback; nếu tự bắt và nuốt exception, cần tự quyết định rollback. Ngoài transaction, chế độ autocommit và cách driver xử lý lỗi sẽ quyết định phần nào được lưu. Không coi `batchUpdate` là cơ chế đảm bảo all-or-nothing.

**Khi cần generated keys:** đừng suy luận id tự tăng từ `int[]`. Spring có một số overload batch sử dụng `KeyHolder`, nhưng khả năng nhận đủ key và thứ tự phụ thuộc API/driver/DB; chọn và thử riêng trên hệ DB triển khai.

## 7. Hiệu năng và vận hành thực tế

- **Chia batch vừa phải:** với hàng chục nghìn bản ghi, không nhất thiết gom tất cả vào một danh sách lớn; thử các kích thước như vài trăm đến khoảng một nghìn dòng, đo trên DB/driver thật và chỉnh theo kích thước record, giới hạn bộ nhớ, log và thời gian khóa. Đây là điểm xuất phát để benchmark, không phải quy luật cố định.
- **Bảo toàn transaction khi chia lô:** chia nhiều lời gọi `batchUpdate` để tiết kiệm bộ nhớ không tự tạo ranh giới commit. Nếu một nghiệp vụ bắt buộc nguyên tử, đặt transaction bao quanh các lô cần cùng rollback; nếu chủ ý commit từng lô, định nghĩa rõ cách retry và nhận diện phần đã xử lý.
- **Lưu ý overload khác:** `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` hỗ trợ chia theo kích thước và trả `int[][]`. Đây là lựa chọn nâng cao khi dữ liệu lớn hoặc cần tự bind từng trường; khác với overload `List<Object[]>` trong trọng tâm bài này.
- **Driver/DB quyết định lợi ích:** một số driver tối ưu/viết lại batch, số khác giảm ít round-trip hơn mong đợi. Hãy đo throughput, latency, thời gian giữ transaction, lock, và query plan; đừng mặc định một batch luôn nhanh hơn trong mọi hoàn cảnh.
- **Dữ liệu và bảo mật:** ràng buộc tham số cho *giá trị*, không tự động bảo vệ tên bảng/cột ghép động. Giới hạn và kiểm tra identifier theo allowlist, xác thực dữ liệu trước khi đẩy vào DB; tránh log toàn bộ dữ liệu nhạy cảm khi batch lỗi.
- **Retry an toàn:** batch `INSERT` không có thiết kế idempotent có thể sinh trùng khóa hoặc dữ liệu lặp khi retry sau timeout. Thiết kế khóa duy nhất, upsert phù hợp từng DB, hoặc cơ chế đánh dấu yêu cầu đã xử lý trước khi bật retry.

## 8. Lỗi phổ biến và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| SQL báo thiếu/sai tham số | `Object[]` thiếu phần tử, đảo vị trí hoặc map/bean thiếu tên `:param` | Đếm `?`; kiểm tra thứ tự array; đối chiếu tên parameter với key/getter |
| Insert null lỗi kiểu dữ liệu | Không suy luận được SQL type hoặc cột không cho null | Dùng `argTypes`, `addValue(name, null, Types.XXX)` và kiểm tra schema |
| Kết quả có nhiều `0` | `UPDATE/DELETE WHERE` không khớp khóa | Kiểm tra dữ liệu id, điều kiện WHERE, nghiệp vụ cho phép 0 dòng hay không |
| Duplicate key giữa batch | Lặp khóa chính/unique, dữ liệu retry hoặc không idempotent | Xử lý trùng, transaction và chiến lược retry/upsert rõ ràng |
| Batch chậm hoặc tốn RAM | Tập dữ liệu quá lớn, driver không tối ưu, DB bị lock/index contention | Chia lô, benchmark theo driver, xem index và thời gian transaction |
| Hàng trước đã thay đổi dù hàng sau lỗi | Chưa có transaction bao phủ hoặc exception bị bắt mà không rollback | Chuyển thao tác vào Spring transaction và kiểm chứng rollback trên DB thật |
| JavaBean không bind được tên | Getter/field không tương ứng tên `:param` | Kiểm tra JavaBean getter, dùng `MapSqlParameterSource` để tường minh |

**Checklist trước khi triển khai:**
1. SQL chỉ có một mẫu lệnh; thứ tự/các tên tham số hợp lệ cho mọi phần tử.
2. Dữ liệu null, kiểu SQL và các constraint đã được kiểm tra.
3. Xác định nghiệp vụ chấp nhận bao nhiêu hàng bị ảnh hưởng, kể cả mã `SUCCESS_NO_INFO`.
4. Chọn phạm vi transaction, cách xử lý lỗi từng phần và quy tắc retry.
5. Đo kích thước batch trên DB/driver thật và kiểm thử với dữ liệu có lỗi giữa batch.

## 9. Tự luyện tập

1. Đổi một nhân viên trong ví dụ thành id không tồn tại khi cập nhật; dự đoán phần tử `int[]` sẽ là 0 và đối chiếu kết quả.
2. Thêm một `Object[]` có `id` trùng khóa chính để quan sát exception; so sánh trạng thái dữ liệu khi có và không có transaction.
3. Chuyển phần `INSERT` từ `Object[]` sang `SqlParameterSource[]` với tên `:id`, `:name`, `:salary`, `:note`. Bảo đảm null ở `note` có SQL type đúng.
4. Tạo vài nghìn nhân viên thử nghiệm, đo thời gian ở nhiều kích thước batch và so sánh với các lời gọi `update(...)` riêng lẻ trong cùng điều kiện.

## Tài liệu tham khảo

- Spring Framework Reference — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework Javadoc — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework Javadoc — `NamedParameterJdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework Javadoc — `SqlParameterSourceUtils`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSourceUtils.html
