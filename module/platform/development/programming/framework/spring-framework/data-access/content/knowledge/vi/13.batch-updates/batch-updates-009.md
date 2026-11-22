# Khai báo kiểu SQL cho `NULL` để tránh lỗi và chi phí metadata khi cập nhật theo lô

## 1. Vấn đề nằm ở đâu?

Trong Spring JDBC, `JdbcTemplate.batchUpdate(...)` và `NamedParameterJdbcTemplate.batchUpdate(...)` gửi nhiều bộ tham số cho cùng một câu SQL, thường qua `PreparedStatement`. Với giá trị khác `null`, Spring/driver thường suy ra được kiểu JDBC từ đối tượng Java. Với `null`, không có lớp Java của giá trị để suy ra kiểu SQL tương ứng.

Ví dụ, bảng có hai cột cho phép `NULL`:

```sql
CREATE TABLE customer_record (
    id         BIGINT PRIMARY KEY,
    note       VARCHAR(200) NULL,
    expires_at TIMESTAMP NULL
);
```

Một lô chạy lặp lại câu:

```sql
UPDATE customer_record
SET note = ?, expires_at = ?
WHERE id = ?;
```

Nếu một hàng có `note = null` và `expires_at = null`, việc chỉ đưa `new Object[] {null, null, 101L}` có thể khiến lớp gán tham số không biết tham số 1 là `VARCHAR`, tham số 2 là `TIMESTAMP`. Trong một số đường đi, Spring tìm kiểu qua `PreparedStatement.getParameterMetaData().getParameterType(index)`. Tùy driver, thao tác đó có thể tốn thêm lượt trao đổi với DBMS, không được hỗ trợ đầy đủ, hoặc trả kiểu không phù hợp. Lặp lại trong batch lớn có thể làm thời gian thực thi tăng rõ rệt.

**Cách xử lý ưu tiên:** khai báo chính xác kiểu JDBC của từng tham số từ schema SQL bằng các hằng `java.sql.Types`, để khi gặp `null`, Spring/driver có thể gán `NULL` có kiểu. Không nên coi việc chỉnh một cờ toàn cục để bỏ qua metadata là giải pháp đầu tiên.

## 2. Ghép kiểu đúng với cột đích

| Kiểu cột SQL thông dụng | Kiểu JDBC thường dùng | Khi gán `NULL` |
| --- | --- | --- |
| `VARCHAR`, chuỗi | `Types.VARCHAR` | `ps.setNull(i, Types.VARCHAR)` |
| `INTEGER` | `Types.INTEGER` | `ps.setNull(i, Types.INTEGER)` |
| `BIGINT` | `Types.BIGINT` | `ps.setNull(i, Types.BIGINT)` |
| `DECIMAL(p,s)`, `NUMERIC` | `Types.DECIMAL` hoặc `Types.NUMERIC` | Theo schema; có thể cần scale cho số khác null |
| `DATE` | `Types.DATE` | `ps.setNull(i, Types.DATE)` |
| `TIMESTAMP` không kèm múi giờ | `Types.TIMESTAMP` | `ps.setNull(i, Types.TIMESTAMP)` |
| `BOOLEAN` | `Types.BOOLEAN` | `ps.setNull(i, Types.BOOLEAN)` |
| Dữ liệu nhị phân `VARBINARY` | `Types.VARBINARY` | `ps.setNull(i, Types.VARBINARY)` |

Đây là bảng định hướng, không phải ánh xạ đúng cho mọi cơ sở dữ liệu. Các kiểu như `UUID`, `JSON/JSONB`, `ARRAY`, `TIMESTAMP WITH TIME ZONE` và kiểu do người dùng định nghĩa cần đối chiếu tài liệu driver/DBMS; `Types.OTHER` hoặc tên kiểu SQL riêng đôi khi phải được cấu hình thêm. **`Types.NULL` không thay cho kiểu thực của cột.**

Với SQL trong ví dụ, thứ tự ba placeholder là `VARCHAR, TIMESTAMP, BIGINT`. Chỉ số trong `int[] argTypes` bắt đầu từ 0 theo mảng Java; chỉ số tham số trong `PreparedStatement` bắt đầu từ **1**.

## 3. Mã Java 17+ trong dự án Spring JDBC

Đoạn dưới là **một lớp Java hoàn chỉnh** để đưa vào ứng dụng có dependency `spring-jdbc` và một `DataSource` đã cấu hình. Nó không có `main` vì cần kết nối đến bảng `customer_record`. Lưu trong tệp `CustomerRepository.java`; từng phương thức minh họa một cách gán kiểu, không cần chạy cả bốn cách cho cùng bộ dữ liệu.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

public final class CustomerRepository {
    private static final String POSITIONAL_SQL =
            "UPDATE customer_record SET note = ?, expires_at = ? WHERE id = ?";
    private static final String NAMED_SQL =
            "UPDATE customer_record SET note = :note, expires_at = :expiresAt WHERE id = :id";

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerRepository(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.namedJdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    public record Change(long id, String note, LocalDateTime expiresAt) {}

    private static Timestamp timestampOrNull(LocalDateTime value) {
        return value == null ? null : Timestamp.valueOf(value);
    }

    // Cách 1: một mảng kiểu chung cho mọi hàng (phù hợp SQL cố định).
    public int[] updateWithArgTypes(List<Change> changes) {
        List<Object[]> rows = changes.stream()
                .map(c -> new Object[] {
                        c.note(), timestampOrNull(c.expiresAt()), c.id()
                })
                .toList();

        int[] sqlTypes = {Types.VARCHAR, Types.TIMESTAMP, Types.BIGINT};
        return jdbc.batchUpdate(POSITIONAL_SQL, rows, sqlTypes);
    }

    // Cách 2: chủ động gọi setNull(index, sqlType) cho từng cột nullable.
    public int[] updateWithSetter(List<Change> changes) {
        return jdbc.batchUpdate(POSITIONAL_SQL, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int row) throws SQLException {
                Change c = changes.get(row);

                if (c.note() == null) {
                    ps.setNull(1, Types.VARCHAR);
                } else {
                    ps.setString(1, c.note());
                }

                if (c.expiresAt() == null) {
                    ps.setNull(2, Types.TIMESTAMP);
                } else {
                    ps.setTimestamp(2, Timestamp.valueOf(c.expiresAt()));
                }

                ps.setLong(3, c.id());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        });
    }

    // Cách 3: tham số có tên, khai báo kiểu trực tiếp cho từng tên.
    public int[] updateWithNamedParameters(List<Change> changes) {
        SqlParameterSource[] batch = changes.stream()
                .map(c -> new MapSqlParameterSource()
                        .addValue("note", c.note(), Types.VARCHAR)
                        .addValue("expiresAt", timestampOrNull(c.expiresAt()),
                                Types.TIMESTAMP)
                        .addValue("id", c.id(), Types.BIGINT))
                .toArray(SqlParameterSource[]::new);

        return namedJdbc.batchUpdate(NAMED_SQL, batch);
    }

    // Cách 4: chỉ bọc một số giá trị cần kiểu riêng.
    public int[] clearNullableFieldsWithSqlParameterValue(long id) {
        List<Object[]> rows = List.<Object[]>of(new Object[] {
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(Types.TIMESTAMP, null),
                id
        });
        return jdbc.batchUpdate(POSITIONAL_SQL, rows);
    }
}
```

**Cách gọi minh họa trong một service có `CustomerRepository repository`:**

```java
List<CustomerRepository.Change> changes = List.of(
        new CustomerRepository.Change(101L, null, null),
        new CustomerRepository.Change(
                102L, "Đang xử lý", LocalDateTime.of(2027, 1, 15, 9, 30))
);
int[] affected = repository.updateWithArgTypes(changes);
```

Đoạn gọi này là **fragment đặt trong phương thức**, không phải chương trình độc lập; giả định hàng có `id=101` và `id=102` đã tồn tại. Kết quả `affected` phụ thuộc dữ liệu và driver; không có một stdout cố định. Với hàng 101, hai cột nullable được gán thành SQL `NULL`; với hàng 102, chúng nhận giá trị có kiểu tương ứng. `LocalDateTime` trong ví dụ đi với cột `TIMESTAMP` **không kèm múi giờ**; nếu schema dùng loại có múi giờ, chọn kiểu Java/JDBC phù hợp thay vì sao chép máy móc.

### Khi nào chọn cách nào?

| API | Cách cung cấp kiểu `NULL` | Phù hợp |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(sql, List<Object[]>, int[])` | `argTypes` ánh xạ theo vị trí SQL, dùng chung cho cả lô | SQL cố định, nhiều hàng, muốn mã ngắn |
| `JdbcTemplate.batchUpdate(sql, BatchPreparedStatementSetter)` | `ps.setNull(index, Types.X)` | Cần kiểm soát cách chuyển đổi mỗi tham số |
| `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` | `MapSqlParameterSource.addValue(name, value, sqlType)` hoặc `registerSqlType` | SQL dài, tham số có tên, dễ tránh lệch thứ tự |
| Mảng đối tượng có `SqlParameterValue` | `new SqlParameterValue(Types.X, null)` | Chỉ vài giá trị cần chỉ định kiểu |
| `BeanPropertySqlParameterSource` | Có thể suy ra kiểu SQL từ kiểu thuộc tính Java đã khai báo dù giá trị null | DTO/bean có property được định kiểu rõ ràng |

Với `SqlParameterSourceUtils.createBatch(...)` trên các `Map` chứa giá trị `null`, đừng mặc định kiểu SQL luôn được biết: cần xem đường ánh xạ và driver, hoặc xây `MapSqlParameterSource` để đăng ký kiểu. Với `BeanPropertySqlParameterSource`, việc suy luận phụ thuộc kiểu Java của getter/property; các kiểu riêng của DBMS vẫn có thể cần khai báo tường minh.

## 4. Vì sao metadata có thể gây chậm, và điều gì đã thay đổi theo phiên bản?

Đường xử lý khái quát với `null` chưa có kiểu:

1. Spring cần gán tham số `?` cho `PreparedStatement` nhưng chỉ biết giá trị `null`.
2. Ở một số phiên bản/driver/đường đi, Spring thử `getParameterMetaData().getParameterType(position)` để xác định kiểu.
3. JDBC driver có thể hỏi DBMS về metadata, thực hiện xử lý bổ sung hoặc không cung cấp kiểu hữu ích.
4. Việc hỏi lặp lại trong batch đông hàng có thể làm mất một phần lợi ích giảm round-trip của batch.

Tuy nhiên, **không được khẳng định mọi batch có `null` đều truy vấn metadata**. Từ **Spring Framework 6.1.2**, đường xử lý mặc định đã tránh truy vấn `getParameterType` trên các driver PostgreSQL và Microsoft SQL Server mà Spring nhận diện, vì chi phí thường đáng kể. Với driver khác và các phiên bản khác, hành vi có thể khác; cần đo thực tế. Việc bỏ dò metadata cũng có thể lộ lỗi gán `NULL` cho kiểu đặc biệt (ví dụ cột `byte[]`/nhị phân) nếu không cung cấp kiểu.

Spring có cờ `spring.jdbc.getParameterType.ignore=true` để yêu cầu bỏ bước dò metadata qua `StatementCreatorUtils`. Ví dụ truyền qua JVM:

```bash
java -Dspring.jdbc.getParameterType.ignore=true -jar app.jar
```

Đây là **system property của Spring Framework**, có thể được nạp qua cơ chế `SpringProperties`; không suy diễn rằng mọi khóa trong `application.properties` của Spring Boot đều tự động điều khiển được cờ này. Chỉ cân nhắc chỉnh sau khi xác nhận nguyên nhân bằng profiling/log/đo hiệu năng trên driver đang dùng. Nếu một kiểu `NULL` đặc biệt bị bind sai, có thể cần khai báo kiểu trực tiếp hoặc kiểm tra lại cờ; ở những môi trường cần khôi phục dò metadata, đặt `spring.jdbc.getParameterType.ignore=false` và kiểm thử.

## 5. Lỗi thường gặp và cách kiểm tra

- **Lẫn `null` Java với SQL `NULL`:** `"null"` (chuỗi bốn ký tự) và `""` (chuỗi rỗng) không tương đương SQL `NULL`.
- **Sai thứ tự kiểu:** `argTypes` phải có đúng một kiểu cho mỗi placeholder `?` theo thứ tự xuất hiện; `Types.TIMESTAMP` đặt vào tham số của cột `VARCHAR` có thể gây lỗi.
- **Gọi `ps.setObject(index, null)` rồi hy vọng driver tự hiểu:** với một số driver/kiểu SQL, đây là nguồn lỗi hoặc làm phải dò kiểu; ưu tiên `ps.setNull(index, Types.X)`.
- **Dùng `Types.NULL`/`Types.OTHER` cho mọi cột:** các giá trị chung chung không đảm bảo khớp kiểu cột thực; với JSON, UUID, array, binary cần đọc tài liệu driver.
- **Hiểu sai nghiệp vụ khi cập nhật:** `SET note = ?` với tham số SQL `NULL` sẽ **xóa nội dung hiện có** của cột đó. Nếu `null` trong DTO có nghĩa “không cập nhật”, cần một chính sách cập nhật/SQL khác; chỉ khai báo kiểu không giải quyết được ngữ nghĩa này.
- **Nhầm count trả về:** `int[]` lưu kết quả từng entry, nhưng JDBC có `Statement.SUCCESS_NO_INFO (-2)` và `Statement.EXECUTE_FAILED (-3)`. Một lỗi có thể làm Spring ném `DataAccessException`; không suy ra mọi phần tử luôn là 0 hoặc 1.
- **Coi batch là giao dịch nguyên tử tự động:** batch không thay thế transaction. Nếu phải all-or-nothing, gọi trong giao dịch Spring thích hợp (ví dụ `@Transactional` ở service, có transaction manager hợp lệ), kiểm thử rollback với DBMS thật.
- **Sửa cờ global trước khi sửa mapping:** giải pháp bền vững cho cột nullable thường là truyền SQL type tường minh; cấu hình toàn cục có thể ảnh hưởng các thao tác JDBC khác.

### Quy trình kiểm thử đề xuất

1. Tạo bảng đúng schema trên cơ sở dữ liệu/driver thực tế; thêm hai hàng test có khóa `101`, `102`.
2. Thực thi từng phương pháp độc lập với bộ dữ liệu gồm `null`, giá trị có dữ liệu, nhiều `null` liên tiếp và batch nhỏ/lớn.
3. Đọc lại cột bằng `SELECT`: hàng được yêu cầu xóa phải thực sự là SQL `NULL`, không phải chuỗi `"null"`; hàng có dữ liệu phải bảo toàn kiểu/giá trị.
4. Theo dõi `int[]`, lỗi từ driver, rollback; không hard-code `-2` thành thất bại.
5. Với vấn đề hiệu năng, đo **cùng số dòng, batch size, connection pool, schema, driver và cấu hình transaction** trước/sau khai báo `Types.X`; theo dõi số lượt hỏi metadata/round-trip nếu driver cho phép. Nếu driver không batch thật, kiểm tra khả năng hỗ trợ/fallback thay vì đổ mọi độ trễ cho `null`.
6. Nếu xử lý nhiều dòng cần chia lô, Spring còn có `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)`, trả về `int[][]`; trong setter vẫn áp dụng `setNull(index, Types.X)` như ví dụ trên.

## 6. Ghi nhớ khi áp dụng

**Quy tắc:** xác định kiểu từ **schema của placeholder SQL**, chọn một cách truyền kiểu phù hợp (`argTypes`, `setNull`, `MapSqlParameterSource` hoặc `SqlParameterValue`), thử nghiệm trên driver thật, rồi đo hiệu năng. Thao tác này giúp `NULL` được gán đúng kiểu và giảm sự phụ thuộc vào truy vấn `ParameterMetaData` tốn kém khi đường xử lý có dùng metadata.

### Tài liệu chính thức

- Spring Framework – [JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): các overload batch, kiểu `NULL`, metadata và lưu ý theo driver.
- Spring Framework – [Providing SQL Type Information for Parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `Types`, `SqlParameterValue`, `SqlParameterSource`.
- Spring Framework – [JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `batchUpdate` với `List<Object[]>` và `argTypes`.
