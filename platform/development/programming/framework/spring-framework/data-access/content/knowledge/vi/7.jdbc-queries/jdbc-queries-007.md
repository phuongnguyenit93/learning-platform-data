# Phân biệt một hàng chứa SQL NULL với không có hàng nào

Khi truy vấn cơ sở dữ liệu bằng JDBC hoặc Spring JDBC, hai kết quả sau **khác nhau về ý nghĩa và cách xử lý**:

1. Truy vấn **có một hàng**, nhưng một cột trong hàng đó mang giá trị **SQL `NULL`**.
2. Truy vấn **không trả về hàng nào**.

Ở trường hợp thứ nhất, thực thể/bản ghi có mặt trong tập kết quả nhưng thuộc tính đang xét không có giá trị. Ở trường hợp thứ hai, không có hàng phù hợp với điều kiện truy vấn. Phân biệt sai có thể khiến ứng dụng báo “không tìm thấy” đối với một bản ghi đang tồn tại, trả dữ liệu mặc định sai, làm mất trạng thái nghiệp vụ hoặc xử lý lỗi `JdbcTemplate` không đúng.

Bài này tập trung vào **kết quả truy vấn JDBC**: phân biệt số hàng với giá trị của cột, đọc `ResultSet.next()`, dùng `wasNull()`, ánh xạ sang Java và xử lý kết quả trong Spring JDBC.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao “một hàng có cột NULL” và “không có hàng” là hai trạng thái khác biệt.
- Nhìn vào SQL và `ResultSet` để nhận biết **sự tồn tại của hàng** trước khi đọc **giá trị của cột**.
- Dùng đúng `next()`, `getString()`, `getObject()`, `getInt()` và `wasNull()` trong Java 17+.
- Thiết kế kết quả Java bảo toàn được cả trạng thái “không có hàng” lẫn “có hàng nhưng trường nullable là null”.
- Hiểu `JdbcTemplate.queryForObject()`, `query()`, `queryForList()` khi kết quả có 0, 1 hoặc nhiều hàng.
- Tránh nhầm lẫn phát sinh từ `LEFT JOIN`, `COUNT(*)`, `COUNT(column)`, `COALESCE` và cách API xử lý kết quả.
- Kiểm chứng ba trường hợp bằng các test có ý nghĩa.

## 2. Một ví dụ SQL với ba trạng thái

Giả sử hệ thống lưu ghi chú của khách hàng. Mỗi khách hàng trong bảng ví dụ có thể có ghi chú, nhưng cột `note` được phép NULL.

~~~sql
CREATE TABLE customer_note (
    id BIGINT PRIMARY KEY,
    note VARCHAR(200) NULL
);

INSERT INTO customer_note (id, note) VALUES (1, NULL);
INSERT INTO customer_note (id, note) VALUES (2, 'Đã liên hệ');
~~~

Ta thử cùng một câu SQL với ba ID:

~~~sql
SELECT id, note
FROM customer_note
WHERE id = ?;
~~~

| Giá trị bind `id` | Số hàng trả về | Nội dung kết quả | Ý nghĩa |
| ---: | ---: | --- | --- |
| `1` | 1 | `id=1, note=NULL` | Có bản ghi, nhưng ghi chú thiếu/chưa có giá trị |
| `2` | 1 | `id=2, note='Đã liên hệ'` | Có bản ghi và ghi chú có giá trị |
| `3` | 0 | Không có hàng nào | Không tồn tại bản ghi phù hợp |

Với ID 1, hàng chứa **hai cột**: `id` có giá trị 1, `note` là SQL NULL. Với ID 3, không có hàng để đọc, vì vậy không thể hỏi “giá trị của cột `note` ở hàng đó” là gì.

Hãy hình dung kết quả:

~~~text
id = 1:  +----+------+
         | id | note |
         +----+------+
         |  1 | NULL |     <-- có một hàng
         +----+------+

id = 3:  +----+------+
         | id | note |
         +----+------+
                           <-- không có hàng
~~~

Đừng đánh đồng “hiển thị trống” với “không có hàng”. Nhiều giao diện SQL biểu diễn NULL bằng ô rỗng hoặc chữ `NULL`; cách hiển thị của công cụ không phải bằng chứng về số lượng hàng.

### Hai lớp thông tin độc lập

Có thể mô hình hóa một truy vấn tra cứu tối đa một bản ghi bằng hai câu hỏi:

1. **Hàng có tồn tại trong kết quả không?** Có/không, được kiểm tra trước.
2. **Nếu có hàng, giá trị cột có phải SQL NULL không?** Có/không, được kiểm tra sau khi đọc cột.

Về logic, trạng thái có thể là `NO_ROW`, `ROW_WITH_NULL` hoặc `ROW_WITH_VALUE`. Nếu bảng chứa nhiều cột nullable, một hàng còn có thể có nhiều tổ hợp giá trị NULL và không NULL. Việc trả duy nhất một `String` nullable từ tầng repository thường không thể tự biểu diễn hết các trạng thái này.

## 3. JDBC ResultSet: next() nói về hàng, getter nói về cột

JDBC nhận kết quả một truy vấn `SELECT` thông qua `java.sql.ResultSet`. Con trỏ của `ResultSet` thường bắt đầu ở vị trí **trước hàng đầu tiên**. Phải gọi `rs.next()` để di chuyển đến hàng tiếp theo:

- `rs.next() == true`: con trỏ đã tới một hàng hợp lệ; có thể đọc cột của **hàng hiện tại**.
- `rs.next() == false` ngay lần gọi đầu tiên: không có hàng kết quả nào.
- Một getter như `rs.getString("note")` trả Java `null` khi **cột `note` của hàng hiện tại** là SQL NULL. Nó không phải cách kiểm tra hàng có tồn tại.
- Sau khi `rs.next()` trả `false`, không có hàng hiện tại; đừng gọi getter để “thử” xem có NULL hay không.

Đoạn mã ý tưởng:

~~~java
try (ResultSet rs = statement.executeQuery()) {
    if (!rs.next()) {
        // Truy vấn trả về 0 hàng.
    } else {
        // Chắc chắn đã có ít nhất 1 hàng.
        String note = rs.getString("note");
        if (note == null) {
            // Có hàng, cột note có giá trị SQL NULL.
        } else {
            // Có hàng, cột note khác SQL NULL.
        }
    }
}
~~~

Đây là đoạn mã **minh họa đặt trong method đã có `PreparedStatement statement` và imports JDBC phù hợp**; không phải một file Java chạy độc lập. Điểm quyết định là **kiểm tra `next()` trước** rồi mới kiểm tra giá trị getter.

### Bảng hành vi cần nhớ

| Kết quả SQL | `rs.next()` lần đầu | `rs.getString("note")` sau `next()==true` | Kết luận |
| --- | --- | --- | --- |
| 0 hàng | `false` | Không được đọc | `NO_ROW` |
| 1 hàng, `note IS NULL` | `true` | Java `null` | `ROW_WITH_NULL` |
| 1 hàng, `note='Đã liên hệ'` | `true` | Chuỗi `"Đã liên hệ"` | `ROW_WITH_VALUE` |
| Nhiều hàng | `true`; các lần tiếp theo có thể `true` | Giá trị phụ thuộc từng hàng | Cần lặp hoặc phát hiện kết quả không đúng cardinality |

**Lưu ý rất thường gặp:** Nếu gọi `rs.next()` một lần trong điều kiện `if` và lại gọi lần thứ hai để “bắt đầu đọc”, bạn đã chuyển sang hàng tiếp theo hoặc qua hết kết quả. Một `ResultSet` có một hàng sẽ trả `false` ở lần thứ hai; đó là lỗi điều khiển con trỏ, không có nghĩa hàng đầu tiên là NULL.

## 4. Giá trị SQL NULL khi đọc bằng các kiểu getter

Các phương thức `ResultSet` có quy tắc khác nhau khi gặp SQL NULL. Đặc biệt, getter trả **Java primitive** không thể trả Java `null`.

| Cách đọc cột hiện tại | Nếu SQL NULL | Cách giữ thông tin “NULL” |
| --- | --- | --- |
| `rs.getString("note")` | Java `null` | Kiểm tra `note == null` |
| `rs.getObject("note")` | Java `null` | Kiểm tra `object == null` |
| `rs.getInt("score")` | Primitive `0` | Gọi `rs.wasNull()` ngay sau getter |
| `rs.getLong("id")` | Primitive `0L` | Gọi `rs.wasNull()` nếu cột nullable |
| `rs.getBoolean("enabled")` | Primitive `false` | Gọi `rs.wasNull()` nếu cột nullable |
| `rs.getBigDecimal("amount")` | Java `null` | Kiểm tra `amount == null` |

Ví dụ `score INTEGER NULL` chứa SQL NULL:

~~~java
int score = rs.getInt("score");
boolean scoreIsSqlNull = rs.wasNull();  // Phải kiểm tra sau getter vừa đọc.
Integer nullableScore = scoreIsSqlNull ? null : score;
~~~

Nếu giá trị SQL là **số 0 thật**, `getInt` cũng trả `0` nhưng `wasNull()` sẽ là `false`. Nếu là SQL NULL, `getInt` trả `0` và `wasNull()` là `true`. Vì vậy chỉ kiểm tra `score == 0` là sai khi cột có thể NULL.

`rs.wasNull()` phản ánh **cột được đọc bởi getter gần nhất**. Phải lưu lại kết quả ngay sau getter cần kiểm tra:

~~~java
int score = rs.getInt("score");
boolean isScoreNull = rs.wasNull();
String note = rs.getString("note");   // Đọc cột khác sau đó.
~~~

Không đọc `note` rồi gọi `wasNull()` và nghĩ nó vẫn phản ánh `score`. `wasNull()` cũng **không** có ý nghĩa để kiểm tra không có hàng; nó chỉ dùng sau khi một getter đã đọc cột của hàng hợp lệ.

Một số JDBC driver hỗ trợ typed `rs.getObject("score", Integer.class)` để nhận `Integer` hoặc `null`. Tính hỗ trợ chuyển đổi có thể tùy driver và kiểu SQL; với kiểu primitive, cặp `getInt`/`wasNull` là quy tắc cơ bản, rõ ràng.

### SQL NULL khác chuỗi rỗng, số 0 và false

`NULL` là trạng thái thiếu/không biết giá trị trong SQL; `''` là chuỗi có độ dài bằng 0; `0` là số nguyên có giá trị 0; `false` là boolean sai. Ba giá trị sau đều **không phải** SQL NULL trong quy tắc chung của JDBC, dù một số database có đặc thù xử lý chuỗi rỗng. Không dùng `isBlank()` hoặc `equals("")` như phép kiểm tra SQL NULL, vì getter có thể trả Java `null`.

## 5. Ví dụ Java 17+ chạy độc lập với CachedRowSet

Ví dụ sau sử dụng `javax.sql.rowset.CachedRowSet` từ JDK để dựng ba tập kết quả trong bộ nhớ; không cần JDBC driver, database hoặc Spring. `CachedRowSet` hiện thực interface `ResultSet`, giúp thực hành thật các lời gọi `next()` và `getString()`. Nó không thay cho kiểm thử truy vấn trên database cụ thể nhưng phù hợp để quan sát trực tiếp sự khác biệt.

Lưu thành **`NullVsNoRowDemo.java`**:

~~~java
import java.sql.Types;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetMetaDataImpl;
import javax.sql.rowset.RowSetProvider;

public class NullVsNoRowDemo {
    static CachedRowSet prepare(boolean hasRow, String note) throws Exception {
        CachedRowSet rows = RowSetProvider.newFactory().createCachedRowSet();
        RowSetMetaDataImpl meta = new RowSetMetaDataImpl();
        meta.setColumnCount(2);
        meta.setColumnName(1, "id");
        meta.setColumnType(1, Types.INTEGER);
        meta.setColumnName(2, "note");
        meta.setColumnType(2, Types.VARCHAR);
        rows.setMetaData(meta);

        if (hasRow) {
            rows.moveToInsertRow();
            rows.updateInt("id", 1);
            if (note == null) {
                rows.updateNull("note");
            } else {
                rows.updateString("note", note);
            }
            rows.insertRow();
            rows.moveToCurrentRow();
        }
        rows.beforeFirst();
        return rows;
    }

    static void inspect(String label, CachedRowSet rows) throws Exception {
        try (rows) {
            if (!rows.next()) {
                System.out.println(label + ": NO_ROW");
                return;
            }
            String note = rows.getString("note");
            System.out.println(label + (note == null
                    ? ": ROW_WITH_SQL_NULL"
                    : ": ROW_WITH_VALUE(" + note + ")"));
        }
    }

    public static void main(String[] args) throws Exception {
        inspect("missing", prepare(false, null));
        inspect("null", prepare(true, null));
        inspect("filled", prepare(true, "hello"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 NullVsNoRowDemo.java
java NullVsNoRowDemo
~~~

**Stdout chính xác:**

~~~text
missing: NO_ROW
null: ROW_WITH_SQL_NULL
filled: ROW_WITH_VALUE(hello)
~~~

Giải thích: phương thức `prepare(false, null)` không thêm hàng; `rows.next()` trả `false` ngay lần đầu. `prepare(true, null)` thêm **một** hàng có cột `note` được cập nhật bằng `updateNull`; `rows.next()` là `true` và `getString("note")` trả Java `null`. `prepare(true, "hello")` tạo hàng với chuỗi khác NULL. `rows.beforeFirst()` đặt con trỏ về trước hàng đầu sau khi tạo dữ liệu; `try (rows)` đóng row set sau khi kiểm tra.

**Giới hạn ví dụ:** Nó chỉ mô phỏng kết quả, chưa kiểm tra SQL `SELECT`, isolation hay tính năng của một JDBC driver ngoài đời. Mã đọc `ResultSet` ở các phần tiếp theo cần được kiểm thử trong ứng dụng với database thực tế.

## 6. Một method JDBC thật: Optional của hàng, không phải Optional của cột

Giả sử đã có bean `DataSource`, ta muốn tìm `customer_note` theo khóa chính `id`. Hợp đồng cần phân biệt:

- Không có hàng: `Optional.empty()`.
- Có hàng `id=1, note=NULL`: `Optional.of(new CustomerNote(1, null))`.
- Có hàng `id=2, note="Đã liên hệ"`: `Optional.of(new CustomerNote(2, "Đã liên hệ"))`.

Dùng một **object đại diện cho hàng**, cho phép trường nullable là Java `null`. Bởi vì `Optional` chỉ chứa object `CustomerNote` (không null), nó bảo toàn sự tồn tại của hàng ngay cả khi thuộc tính `note` là null.

Ví dụ class `CustomerNoteDao.java` dùng JDBC thuần, Java 17+:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerNoteDao {
    public record CustomerNote(long id, String note) {}

    private final DataSource dataSource;

    public CustomerNoteDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<CustomerNote> findById(long id) throws SQLException {
        String sql = "SELECT id, note FROM customer_note WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();     // Không có hàng.
                }

                CustomerNote row = new CustomerNote(
                        rs.getLong("id"),
                        rs.getString("note")     // Cho phép Java null.
                );

                if (rs.next()) {
                    throw new SQLException("Expected at most one row");
                }
                return Optional.of(row);         // Có hàng, dù note == null.
            }
        }
    }
}
~~~

Đây là **class tích hợp**: biên dịch với JDK 17+ nhưng cần một `DataSource`/JDBC driver đã cấu hình, schema và dữ liệu để chạy. Nó không có `main` và không được trình bày như chương trình độc lập. `try-with-resources` đảm bảo trả JDBC resources kể cả khi có exception. `?` là tham số prepared statement, tránh ghép trực tiếp giá trị `id` vào SQL.

Vì `id` là khóa chính, truy vấn đúng schema sẽ trả tối đa một hàng. Lệnh kiểm tra `rs.next()` lần hai giúp phát hiện lỗi nếu hợp đồng truy vấn bị sửa thành câu trả nhiều hàng. Không cần kiểm tra `wasNull()` đối với `note` khi đã dùng `getString`; riêng `id` là `PRIMARY KEY` nên không nullable.

### Tại sao Optional<String> dễ làm mất thông tin?

So sánh:

~~~java
// Sai nếu nghiệp vụ cần phân biệt "không có hàng" và "hàng có note NULL".
Optional<String> result = Optional.ofNullable(note);
~~~

`Optional.ofNullable(null)` là `Optional.empty()`, dù `note == null` có thể xuất phát từ **hàng tồn tại**. Nếu mã cũng dùng `Optional.empty()` cho truy vấn không có hàng, hai trạng thái khác nhau đã bị gộp thành một.

**Có thể dùng:** `Optional<CustomerNote>`, trong đó `CustomerNote.note()` có thể là `null`. Nếu cần hợp đồng domain chặt chẽ hơn, dùng một *sealed result type* với các trường hợp riêng như `NotFound`, `FoundNull` và `FoundValue`; điều đó hữu ích khi API/logic cần pattern matching không cho phép suy diễn từ null. Không cần tự động thêm abstraction nếu record bọc hàng đã đủ rõ.

## 7. Spring JdbcTemplate và các trường hợp 0/1/nhiều hàng

Với Spring Framework, `JdbcTemplate` quản lý việc thực thi truy vấn, ánh xạ, đóng JDBC resources và dịch lỗi qua hierarchy `DataAccessException`. Tuy nhiên **mỗi phương thức truy vấn có hợp đồng số lượng hàng khác nhau**. Phải đọc Javadoc và chọn API theo trạng thái nghiệp vụ cần giữ.

### 7.1. queryForObject: yêu cầu đúng một hàng

Một ví dụ trong ứng dụng Spring đã có bean `JdbcTemplate jdbc`:

~~~java
String note = jdbc.queryForObject(
        "SELECT note FROM customer_note WHERE id = ?",
        String.class,
        id
);
~~~

Giả sử `id` là khóa chính và có schema/dữ liệu ở phần 2:

| `id` | Tình huống | Hành vi `queryForObject(..., String.class, id)` |
| ---: | --- | --- |
| 1 | Một hàng, cột `note` là SQL NULL | Trả Java `null` |
| 2 | Một hàng, `note` có chuỗi | Trả chuỗi tương ứng |
| 3 | Không có hàng | Ném `EmptyResultDataAccessException` |
| Query lỗi và trả nhiều hàng | Hơn một hàng | Ném `IncorrectResultSizeDataAccessException` |

Vì thế, **trả `null` và ném `EmptyResultDataAccessException` có ý nghĩa khác nhau**. `EmptyResultDataAccessException` là một subtype của `IncorrectResultSizeDataAccessException`, không phải `SQLException` thuần. Nếu repository muốn trả `Optional` thay cho exception khi không tìm thấy, có thể bắt **riêng** ngoại lệ “empty result”; không nên bắt mọi `DataAccessException` rồi biến thành “not found”, vì điều đó che lỗi kết nối, cú pháp SQL hoặc quyền truy cập.

Cũng cần phân biệt trường hợp `RowMapper` trả Java `null` cho một hàng hợp lệ: `queryForObject(sql, rowMapper, args...)` có thể trả `null` khi mapper trả null. Cách dùng API vì vậy cần ghi rõ **0 hàng vs 1 hàng map thành null vs nhiều hàng**.

### 7.2. Bảo toàn ba trạng thái bằng ResultSetExtractor

Một cách rõ ràng hơn với Spring JDBC là dùng `JdbcTemplate.query(sql, ResultSetExtractor, args...)` để kiểm tra `rs.next()`, sau đó bọc **toàn bộ hàng** trong `Optional`.

~~~java
import java.sql.SQLException;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerNoteRepository {
    public record CustomerNote(long id, String note) {}

    private final JdbcTemplate jdbc;

    public CustomerNoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerNote> findById(long id) {
        return jdbc.query(
                "SELECT id, note FROM customer_note WHERE id = ?",
                rs -> {
                    if (!rs.next()) {
                        return Optional.empty();
                    }

                    CustomerNote row = new CustomerNote(
                            rs.getLong("id"),
                            rs.getString("note")
                    );

                    if (rs.next()) {
                        throw new SQLException("Expected at most one row");
                    }
                    return Optional.of(row);
                },
                id
        );
    }
}
~~~

Đây là **đoạn class để tích hợp trong một Spring application**, yêu cầu `spring-jdbc`, `spring-context`, `DataSource`/`JdbcTemplate` và schema tương ứng. Nó không phải Java CLI độc lập.

Logic phân biệt chính xác giống JDBC thuần:

- Không có hàng → `Optional.empty()`.
- Có một hàng và `note IS NULL` → `Optional.of(CustomerNote)`, trong đó `note() == null`.
- Có một hàng và note có giá trị → `Optional.of(CustomerNote)` với nội dung.
- Nhiều hàng trái hợp đồng → lỗi, thay vì âm thầm lấy hàng đầu.

`ResultSetExtractor` cho phép xử lý toàn bộ `ResultSet`, nên có thể phân biệt cardinality. Không dùng `RowMapper` trực tiếp để phát hiện “không có hàng” từ bên trong mapper: mapper thường chỉ được gọi **khi có một hàng được ánh xạ**.

### 7.3. queryForList và queryForMap

`jdbc.queryForList(sql, String.class, args...)` thường cho một `List<String>`:

- 0 hàng → danh sách rỗng `[]`.
- 1 hàng cột SQL NULL → danh sách **có một phần tử** `[null]`.
- 1 hàng cột có giá trị → ví dụ `["Đã liên hệ"]`.

Điều quan trọng là **`list.isEmpty()` khác `list.get(0) == null`**. Danh sách Java được tạo bởi mapper của Spring có thể chứa phần tử null; đừng thay nó bằng `List.of(null)` vì factory method `List.of` không cho phép phần tử null. Khi câu SQL dự kiến tối đa một hàng, ưu tiên DTO/record hoặc kiểm tra `size()` để biết cardinality.

`jdbc.queryForMap(sql, args...)` kỳ vọng một hàng và ánh xạ các cột thành `Map<String,Object>`. Nếu hàng tồn tại và `note` là SQL NULL, map có thể chứa key `note` với value Java `null`. `map.get("note") == null` **không chứng minh key vắng mặt**: cần `map.containsKey("note")` nếu thực sự muốn phân biệt key không tồn tại với key tồn tại có value null. Tuy nhiên sự tồn tại của **hàng** ở mức `queryForMap` còn được kiểm tra bằng hợp đồng đúng một hàng; truy vấn 0 hàng ném exception tương ứng.

### 7.4. Không biến mọi lỗi thành “không tìm thấy”

Chống ví dụ:

~~~java
try {
    return jdbc.queryForObject(sql, String.class, id);
} catch (Exception ex) {
    return null; // Nuốt cả lỗi DB, SQL, mạng và kết quả rỗng.
}
~~~

Ở đây `null` có thể là “hàng có SQL NULL”, “không có hàng” hoặc “database lỗi”. Code đánh mất cả **thông tin nghiệp vụ** và **tín hiệu vận hành**. Nếu cần xử lý `EmptyResultDataAccessException`, bắt đúng loại và biểu diễn riêng việc không tìm thấy; để lỗi hạ tầng tiếp tục đi qua cơ chế xử lý lỗi phù hợp.

## 8. SQL trả về một hàng như thế nào: SELECT, COUNT và aggregate

Một sai lầm phổ biến là dựa vào **giá trị** của cột để suy ra **số hàng**. Trong SQL, biểu thức tổng hợp có thể tạo một hàng ngay cả khi không có dữ liệu đầu vào.

Với bảng ví dụ:

~~~sql
-- ID 3 không tồn tại: truy vấn trực tiếp trả 0 hàng.
SELECT note FROM customer_note WHERE id = 3;

-- ID 3 không tồn tại: aggregate không GROUP BY trả một hàng, giá trị 0.
SELECT COUNT(*) AS total FROM customer_note WHERE id = 3;

-- ID 1 tồn tại nhưng note NULL: COUNT(*) = 1, COUNT(note) = 0.
SELECT COUNT(*) AS all_rows, COUNT(note) AS non_null_notes
FROM customer_note
WHERE id = 1;

-- ID 3 không tồn tại: MIN(note) trả một hàng có SQL NULL.
SELECT MIN(note) AS minimum_note
FROM customer_note
WHERE id = 3;
~~~

| Truy vấn | Số hàng kết quả | Giá trị |
| --- | ---: | --- |
| `SELECT note ... WHERE id=3` | 0 | Không có cột nào để đọc |
| `SELECT COUNT(*) ... WHERE id=3` | 1 | `0` |
| `SELECT COUNT(*) ... WHERE id=1` | 1 | `1` |
| `SELECT COUNT(note) ... WHERE id=1` | 1 | `0` |
| `SELECT MIN(note) ... WHERE id=3` | 1 | SQL `NULL` |

**Vì sao?** `COUNT(*)` đếm **hàng**; `COUNT(note)` đếm **giá trị note không NULL**. Aggregates không kèm `GROUP BY` tổng hợp toàn bộ tập đầu vào thành **một hàng** kể cả khi không có hàng đầu vào; `COUNT` cho 0, còn nhiều aggregate khác như `MIN` hoặc `SUM` thường trả NULL. Nếu có `GROUP BY`, không có group phù hợp có thể dẫn tới **0 hàng kết quả**, nên không áp dụng máy móc quy tắc “aggregate luôn một hàng” cho mọi câu SQL.

Chẳng hạn:

~~~sql
SELECT id, COUNT(*)
FROM customer_note
WHERE id = 3
GROUP BY id;
~~~

Câu này trả **0 hàng** vì không có nhóm `id=3`. Khi ứng dụng cần biết tồn tại bản ghi hay không, `COUNT(*)` hoặc `EXISTS` có thể hữu ích, nhưng hãy hiểu giá trị trả về. Nếu đã dùng một truy vấn trả về hàng đầy đủ, `rs.next()` trực tiếp thường là cách rõ nhất để phân biệt.

## 9. LEFT JOIN có thể tạo ra hàng với cột phía phải NULL

Với `LEFT JOIN`, nếu bảng bên trái có hàng nhưng không có hàng phù hợp ở bảng bên phải, SQL **vẫn trả một hàng kết quả** và các cột được chọn từ phía phải thường là NULL. Đây là nguồn nhầm lẫn khác, đặc biệt khi ứng dụng chỉ chọn một cột nullable.

Giả sử:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    nickname VARCHAR(100) NULL,
    FOREIGN KEY (customer_id) REFERENCES customer(id)
);

INSERT INTO customer (id, full_name)
VALUES (10, 'An'), (11, 'Bình');

INSERT INTO customer_profile (customer_id, nickname)
VALUES (10, NULL);
~~~

Truy vấn:

~~~sql
SELECT c.id, p.customer_id AS profile_customer_id, p.nickname
FROM customer AS c
LEFT JOIN customer_profile AS p
  ON p.customer_id = c.id
WHERE c.id IN (10, 11)
ORDER BY c.id;
~~~

Kết quả:

| `c.id` | `profile_customer_id` | `nickname` | Sự thật |
| ---: | ---: | --- | --- |
| 10 | 10 | NULL | Profile **tồn tại**, nickname NULL |
| 11 | NULL | NULL | Profile **không tồn tại**; hàng kết quả được LEFT JOIN tạo ra |

**Nếu chỉ SELECT `p.nickname`**, cả hai hàng đều cho giá trị NULL. Không thể phân biệt có profile với không có profile chỉ bằng cột nullable này. Hãy chọn thêm **khóa phía phải vốn NOT NULL khi hàng đó tồn tại**, chẳng hạn `p.customer_id`, hoặc dùng `EXISTS`/hai bước truy vấn có kiểm soát.

Để đọc chính xác khi join:

~~~java
long id = rs.getLong("id");
long profileId = rs.getLong("profile_customer_id");
boolean hasProfile = !rs.wasNull();
String nickname = rs.getString("nickname");
// hasProfile=true, nickname=null: profile có tồn tại nhưng nickname NULL.
// hasProfile=false, nickname=null: profile không tồn tại.
~~~

Với cột khóa join là primitive, gọi `wasNull()` ngay sau khi đọc `profile_customer_id`. Nếu dùng `rs.getObject("profile_customer_id")`, kiểm tra Java null cũng có thể giúp phân biệt. Trong câu SQL khác, cần chọn cột mà schema đảm bảo **NOT NULL ở hàng khớp thật**; không dùng một cột có thể NULL như thước đo “có join match”.

### WHERE trên bảng phải có thể vô tình biến LEFT JOIN thành lọc mất hàng

~~~sql
SELECT c.id, p.nickname
FROM customer c
LEFT JOIN customer_profile p ON p.customer_id = c.id
WHERE p.nickname = 'An';
~~~

Điều kiện `p.nickname = 'An'` ở `WHERE` loại bỏ hàng không có profile và hàng có nickname NULL, vì biểu thức so sánh với NULL không thành TRUE. Nếu mục tiêu là giữ mọi customer nhưng chỉ ghép profile có nickname cụ thể, có thể đưa điều kiện phù hợp vào `ON`:

~~~sql
SELECT c.id, p.nickname
FROM customer c
LEFT JOIN customer_profile p
  ON p.customer_id = c.id AND p.nickname = 'An';
~~~

Hai truy vấn có ngữ nghĩa khác nhau; không chuyển điều kiện một cách máy móc nếu nghiệp vụ muốn loại bỏ khách hàng. Luôn phân tích vị trí điều kiện và số hàng được trả.

## 10. SQL NULL và điều kiện lọc: = NULL không có nghĩa IS NULL

Trong SQL chuẩn, `NULL` đại diện giá trị chưa biết/không có, và nhiều phép so sánh sử dụng logic ba giá trị `TRUE`, `FALSE`, `UNKNOWN`:

~~~sql
-- Đúng: tìm các hàng mà cột note là SQL NULL.
SELECT id FROM customer_note WHERE note IS NULL;

-- Sai ý định: note = NULL không phải phép kiểm tra NULL.
SELECT id FROM customer_note WHERE note = NULL;

-- Đúng: tìm các hàng mà note không NULL.
SELECT id FROM customer_note WHERE note IS NOT NULL;
~~~

Nếu câu `WHERE` nhận `UNKNOWN`, hàng không được chọn. Thế nên `WHERE note = NULL` thường trả **0 hàng**, nhưng điều đó không chứng minh bảng không có hàng `note=NULL`. Hãy dùng `IS NULL`/`IS NOT NULL` hoặc toán tử so sánh NULL-safe đúng dialect khi thật sự cần.

Một lỗi khác là:

~~~sql
SELECT COALESCE(note, 'Chưa ghi chú') AS note
FROM customer_note
WHERE id = 1;
~~~

`COALESCE` thay SQL NULL thành chuỗi thay thế **trong một hàng có mặt**. Nó không tự tạo hàng khi truy vấn theo ID không có kết quả. Tuy nhiên nếu dùng `COALESCE` quanh aggregate, ngữ nghĩa sẽ khác:

~~~sql
SELECT COALESCE(MIN(note), 'Chưa ghi chú') AS note
FROM customer_note
WHERE id = 3;
~~~

Đây là **một hàng**, chứa chuỗi fallback dù không có bản ghi gốc nào thỏa `id=3`. Không dùng fallback của aggregate để suy ra hàng gốc tồn tại.

## 11. Đặt hợp đồng kết quả ở tầng repository/service

Tầng truy cập dữ liệu nên công bố rõ **hợp đồng cardinality** (0..1, đúng 1, 0..N) và **nullability** của từng trường, thay vì trả một giá trị nullable không giải thích được.

| Nhu cầu nghiệp vụ | Hợp đồng gợi ý | Tại sao |
| --- | --- | --- |
| Tìm record theo ID, có thể không tồn tại | `Optional<CustomerNote>` | Optional chứa **hàng**; field note có thể null |
| Truy vấn danh sách record | `List<CustomerNote>` | 0 hàng là list rỗng; mỗi object là một hàng |
| Lấy một scalar buộc phải có đúng một hàng | `queryForObject` và xử lý exception hợp đồng | Thể hiện “đúng một hàng” |
| Chỉ kiểm tra tồn tại | Query `EXISTS` hoặc `COUNT(*)` với điều kiện đúng | Cần boolean/count, không cần đọc field nullable |
| Cần ba trạng thái tách biệt tại API/domain | Sealed result type hoặc discriminated DTO | Phân biệt NotFound, FoundNull, FoundValue rõ ràng |
| Cột numeric có thể SQL NULL | `Integer`/`Long`/`BigDecimal` và `wasNull()` khi cần | Primitive không lưu được null |

Ví dụ Java 17 dùng một sealed result type **mô tả hợp đồng**, không bắt buộc dùng cùng ORM hay framework:

~~~java
sealed interface NoteLookup
        permits NoteLookup.NotFound, NoteLookup.Found {
    record NotFound() implements NoteLookup {}
    record Found(String note) implements NoteLookup {}
}
~~~

Trong Java 17, `record Found(String note)` cho phép `note == null`; `new NotFound()` đại diện không tìm thấy. Nếu nghiệp vụ muốn không có null ở cả field Java, có thể chia riêng `FoundWithNull` và `FoundWithValue(String)`, với validation constructor bảo đảm `FoundWithValue` không nhận null.

**Không nên chuyển trạng thái không tìm thấy thành giá trị mặc định như chuỗi rỗng hoặc số 0** nếu chúng là giá trị hợp lệ trong nghiệp vụ. Nếu quy tắc kinh doanh quy định “không có ghi chú thì dùng chuỗi rỗng”, hãy thực hiện chuyển đổi đó có chủ ý ở tầng trình bày/domain, sau khi việc tồn tại hàng đã được xác định.

### Ví dụ API có ý nghĩa khác nhau

Một API giả định `GET /customer-notes/{id}` có thể định nghĩa:

~~~text
GET /customer-notes/1  -> 200 {"id":1,"note":null}
GET /customer-notes/2  -> 200 {"id":2,"note":"Đã liên hệ"}
GET /customer-notes/3  -> 404
~~~

Đây là **quy ước thiết kế API minh họa**, không phải một chuẩn bắt buộc. Điểm cần học: SQL NULL ở cột `note` **không tự đồng nghĩa** với HTTP 404. Trên JSON, việc serializer bỏ qua field null khác với viết field có giá trị `null`; hợp đồng API cần nói rõ. Khi dùng DTO/JSON, tránh biến bản ghi tồn tại thành “not found” chỉ vì một thuộc tính nullable.

## 12. Kiểm tra cardinality thay vì lặng lẽ lấy hàng đầu tiên

Đôi khi code làm:

~~~java
if (!rs.next()) {
    return Optional.empty();
}
return Optional.of(new CustomerNote(
        rs.getLong("id"),
        rs.getString("note")
));
~~~

Cách này đúng khi **schema/query bảo đảm tối đa một hàng**, như lookup bằng primary key. Nếu query vô tình trả hai hàng, code lấy hàng đầu và bỏ qua phần còn lại. Khi hợp đồng yêu cầu đúng một hàng hoặc tối đa một hàng, có thể gọi `rs.next()` lần nữa **sau khi đọc xong hàng đầu** để phát hiện nhiều hàng. Nếu tìm nhiều hàng theo thiết kế, dùng loop:

~~~java
while (rs.next()) {
    String note = rs.getString("note");
    // Mỗi lượt tương ứng một hàng, dù note có thể là Java null.
}
~~~

Một vòng `while` chỉ chạy khi có hàng. **Danh sách rỗng** mô tả 0 hàng; **danh sách gồm một record nullable** mô tả 1 hàng. Tránh `LIMIT 1` chỉ để che một lỗi duplicate hoặc sai query khi nghiệp vụ thực ra đòi hỏi duy nhất; sửa constraint/query đúng hơn.

### Hai truy vấn riêng để kiểm tra tồn tại có thể gặp race

Ví dụ:

~~~sql
SELECT COUNT(*) FROM customer_note WHERE id = ?;
SELECT note FROM customer_note WHERE id = ?;
~~~

Giữa hai câu lệnh, một transaction khác có thể thêm/xóa/sửa hàng, tùy isolation và concurrency. Khi ứng dụng cần trạng thái **từ một lần đọc nhất quán**, ưu tiên truy vấn đơn trả về hàng, hoặc sử dụng transaction/isolation thích hợp. Đừng mặc định kiểm tra `COUNT(*)` trước là bắt buộc để phân biệt NULL và không có hàng: `ResultSet.next()` trong một truy vấn đã đáp ứng yêu cầu.

## 13. Lỗi phổ biến và cách sửa

**Lỗi 1 — Gọi getter trước `next()`.** ResultSet chưa được đặt trên hàng hợp lệ; đọc cột là sai hợp đồng JDBC và thường dẫn tới SQLException.  
**Sửa:** Chuyển con trỏ bằng `if (rs.next())` hoặc `while (rs.next())` trước.

**Lỗi 2 — Thấy `rs.getString("note") == null` rồi kết luận “không tìm thấy bản ghi”.** Getter chỉ diễn giải cột **của hàng đã tồn tại**.  
**Sửa:** Tách nhánh `!rs.next()` khỏi nhánh `note == null`.

**Lỗi 3 — Dùng `getInt() == 0` để nhận biết SQL NULL.** SQL số 0 là giá trị hợp lệ.  
**Sửa:** Dùng `rs.wasNull()` ngay sau getter và wrapper `Integer` nếu cần biểu diễn null.

**Lỗi 4 — Gọi `wasNull()` sau một getter khác.** Trạng thái của cột ban đầu đã bị thay thế.  
**Sửa:** Gọi `wasNull()` ngay sau getter cần kiểm tra, lưu kết quả boolean.

**Lỗi 5 — Gộp `Optional.empty()` từ “không có hàng” và “có hàng nhưng scalar null”.** Mất thông tin về sự tồn tại.  
**Sửa:** Bọc record/DTO đại diện **hàng**, ví dụ `Optional<CustomerNote>`, hoặc dùng result type phân biệt trạng thái.

**Lỗi 6 — Bắt tất cả `DataAccessException` rồi trả null.** Lỗi mạng, query hoặc database bị ngụy trang thành trạng thái nghiệp vụ.  
**Sửa:** Xử lý riêng trường hợp 0 hàng khi thực sự mong đợi; để lỗi hạ tầng được ghi nhận/đẩy lên thích hợp.

**Lỗi 7 — Dùng `COUNT(note) == 0` để kết luận bảng không có bản ghi.** `COUNT(note)` bỏ qua các hàng có note NULL.  
**Sửa:** Dùng `COUNT(*)` để đếm hàng nếu câu hỏi là “có bao nhiêu hàng”, hoặc query trực tiếp theo ID.

**Lỗi 8 — Dùng cột nullable của LEFT JOIN để suy ra bên phải tồn tại.** Cả “match nhưng cột NULL” và “không match” đều trả NULL.  
**Sửa:** Chọn thêm khóa phía phải không nullable; kiểm tra sự tồn tại trên khóa hoặc dùng `EXISTS`.

**Lỗi 9 — Coi `SELECT MIN(column)` trả NULL là bằng chứng có một hàng gốc chứa NULL.** Aggregate không có GROUP BY có thể trả một hàng NULL khi không có hàng đầu vào.  
**Sửa:** Đọc lại cấu trúc truy vấn, kiểm tra count/existence riêng khi cần.

**Lỗi 10 — Chuyển null thành chuỗi rỗng quá sớm.** Khi dùng `COALESCE` hoặc Java default, không phân biệt được dữ liệu gốc trống và thiếu.  
**Sửa:** Chỉ áp fallback có chủ ý ở tầng cần trình bày, giữ thông tin hiện diện của hàng khi phục vụ nghiệp vụ.

**Lỗi 11 — Kết luận “có hàng” vì `JdbcTemplate.queryForObject` trả một số `0`.** Với `COUNT(*)`, `0` là **giá trị của một hàng aggregate**, không phải hàng dữ liệu gốc.  
**Sửa:** Phân biệt tập kết quả của query aggregate và bản ghi nguồn mà nó đếm.

## 14. Checklist kiểm thử cho mã JDBC/Spring JDBC

Với repository tìm theo `id` và cột `note` nullable, nên có ít nhất các test dưới đây trên một database test phù hợp:

| Test | Dữ liệu chuẩn bị | Kết quả mong đợi |
| --- | --- | --- |
| Không có hàng | Không có `id=3` | `Optional.empty()` hoặc exception 0 hàng đúng hợp đồng |
| Một hàng, giá trị NULL | `id=1, note=NULL` | `Optional.of(row)`; `row.note()==null` |
| Một hàng, giá trị không NULL | `id=2, note='Đã liên hệ'` | `Optional.of(row)` với chuỗi |
| Giá trị số thực sự bằng 0 | `score=0` | `getInt=0`, `wasNull=false` |
| Giá trị số SQL NULL | `score=NULL` | `getInt=0`, `wasNull=true` |
| Câu query vô tình trả nhiều hàng | Bỏ điều kiện khóa hoặc dùng điều kiện không unique | Báo lỗi cardinality nếu hợp đồng tối đa một hàng |
| LEFT JOIN có hàng khớp nhưng cột nullable NULL | Profile tồn tại, nickname NULL | Phát hiện bằng PK/FK phía phải không NULL |
| LEFT JOIN không có hàng khớp | Không có profile | Không suy từ nickname; khóa phía phải NULL |
| Aggregate không có hàng nguồn | `COUNT(*)` theo ID không tồn tại | Một hàng giá trị 0 |
| Aggregate với cột NULL | `COUNT(note)` trên một hàng NULL | Một hàng giá trị 0; không suy ra không có row |

Khi test `JdbcTemplate.queryForObject`, nên assert chính xác loại exception `EmptyResultDataAccessException` cho 0 hàng, giá trị Java null cho 1 hàng một cột SQL NULL và `IncorrectResultSizeDataAccessException` cho nhiều hàng. Nếu dùng `Optional<Row>` thì assert `isEmpty()`/`isPresent()` và nội dung của row.

Nếu chỉ test trường hợp cột có giá trị, lỗi conflation giữa “không có hàng” và “hàng chứa NULL” vẫn có thể tồn tại dù mọi test đều pass.

## 15. Bài tập tự kiểm tra

**Câu 1.** Truy vấn `SELECT note FROM customer_note WHERE id=1` trả một hàng có `note=NULL`. `rs.next()` trả gì, `rs.getString("note")` trả gì?  
**Đáp án:** `rs.next() == true`; getter trả Java `null`.

**Câu 2.** Nếu `id=3` không tồn tại, có nên gọi `rs.getString("note")` để kiểm tra NULL không?  
**Đáp án:** Không. Lần `rs.next()` đầu trả `false`, không có hàng hiện tại.

**Câu 3.** Một cột `score INTEGER NULL` được đọc bằng `getInt` và trả 0. Có đủ bằng chứng SQL là 0 hay NULL chưa?  
**Đáp án:** Chưa. Phải dùng `wasNull()` ngay sau `getInt`.

**Câu 4.** `SELECT COUNT(*) FROM customer_note WHERE id=3` có bao nhiêu hàng kết quả và giá trị bao nhiêu?  
**Đáp án:** Một hàng chứa 0 (với aggregate không có GROUP BY), dù bảng gốc không có bản ghi ID 3.

**Câu 5.** `Optional.ofNullable(rs.getString("note"))` có giúp giữ sự khác biệt giữa 0 hàng và một hàng chứa NULL không?  
**Đáp án:** Không, nếu cả hai nhánh cùng dẫn tới `Optional.empty()`. Hãy dùng `next()` để nhận biết hàng và bọc DTO/record đại diện hàng trong `Optional`.

**Câu 6.** `LEFT JOIN` cho `profile_id=NULL, nickname=NULL`, còn một hàng khác cho `profile_id=10, nickname=NULL`. Ý nghĩa khác nhau thế nào?  
**Đáp án:** Trường hợp đầu không có hàng profile được join (nếu `profile_id` là khóa không NULL của profile); trường hợp sau có profile, nhưng nickname NULL.

**Câu 7.** Vì sao `queryForObject(..., String.class)` trả `null` không đồng nghĩa `EmptyResultDataAccessException`?  
**Đáp án:** Null là giá trị ánh xạ của đúng một hàng một cột SQL NULL; exception là kết quả có số hàng khác hợp đồng (đặc biệt 0 hàng).

**Câu 8.** Nếu muốn REST endpoint trả 404 khi không có hàng nhưng trả 200 khi có hàng và `note=NULL`, repository nên trả kết quả kiểu nào?  
**Đáp án:** Ví dụ `Optional<CustomerNote>`, trong đó CustomerNote luôn là object khi hàng có mặt, còn `note` được phép null.

## 16. Tóm lược quy tắc

**Hàng có mặt hay không phải được quyết định bằng cardinality, không bằng giá trị của cột nullable.** Với JDBC, `ResultSet.next()` quyết định có hàng; các getter và `wasNull()` giúp giải mã từng giá trị của hàng đó. Trong Spring JDBC, `queryForObject` yêu cầu một hàng và phân biệt 0 hàng bằng exception, trong khi `query`/`queryForList` có thể biểu diễn số hàng rõ ràng hơn theo hợp đồng. Đối với repository tra cứu theo ID, `Optional<RowDto>` thường đủ để giữ hai tầng thông tin này.

Khi gặp `JOIN`, aggregate hoặc `COALESCE`, hãy xét **tập hàng đầu ra của SQL** trước, rồi mới diễn giải NULL ở từng cột. Đó là cách tránh phần lớn lỗi “dữ liệu tồn tại nhưng bị báo không tìm thấy”.

### Tài liệu tham khảo chính thức

- [Java SE 21 — ResultSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html): vị trí con trỏ, `next()`, getters, `wasNull()` và SQL NULL.
- [Java SE 21 — CachedRowSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/CachedRowSet.html): rowset tách kết nối, sử dụng với `ResultSet`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): truy vấn bằng `JdbcTemplate`.
- [Spring Framework — JdbcOperations API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): `queryForObject`, `query`, `queryForList` và hợp đồng cardinality.
- [Spring Framework — EmptyResultDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html): ngoại lệ khi mong đợi kết quả nhưng nhận 0 hàng.