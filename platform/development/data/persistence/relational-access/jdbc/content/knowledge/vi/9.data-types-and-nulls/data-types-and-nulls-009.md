# Sử dụng getObject với lớp đích và kiểm tra hỗ trợ trong JDBC

Trong chương **Kiểu dữ liệu và NULL**, khi đọc một cột bằng `ResultSet`, ứng dụng thường muốn nhận ngay giá trị theo kiểu Java cần sử dụng: `Integer` cho số nguyên có thể `NULL`, `BigDecimal` cho tiền, `LocalDate` cho ngày hoặc `OffsetDateTime` cho thời điểm có thông tin múi giờ. JDBC cung cấp `getObject(column, Class<T>)` để **yêu cầu driver chuyển giá trị SQL sang lớp đích cụ thể**, giúp mã ánh xạ dữ liệu rõ ràng hơn.

Tuy nhiên, **không phải mọi driver JDBC đều hỗ trợ mọi lớp đích trên mọi kiểu cột SQL**. Việc driver báo hỗ trợ một phiên bản API JDBC cũng không bảo đảm từng phép chuyển đổi đều hoạt động. Bài này hướng dẫn sử dụng API đúng cách, kiểm tra `NULL`, kiểm chứng hỗ trợ trên driver và cơ sở dữ liệu thật, đồng thời chuẩn bị phương án thay thế khi cần.

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Các ví dụ dưới đây sử dụng Java, `java.sql.ResultSet`, `java.sql.DatabaseMetaData` và `java.sql.ResultSetMetaData`; mức độ hỗ trợ thực tế phụ thuộc vào phiên bản Java, driver, SQL type và DBMS.

## 1. getObject với lớp đích dùng để làm gì?

`ResultSet` cung cấp hai overload quan trọng:

```java
<T> T getObject(int columnIndex, Class<T> type) throws SQLException;
<T> T getObject(String columnLabel, Class<T> type) throws SQLException;
```

Khi gọi, bạn chỉ định:

1. **Cột cần đọc**: số thứ tự `columnIndex` bắt đầu từ **1**, hoặc `columnLabel` là nhãn cột của kết quả SQL, gồm cả alias từ `AS`.
2. **Lớp Java đích**: `Integer.class`, `BigDecimal.class`, `LocalDate.class`, v.v.
3. **Kết quả**: đối tượng kiểu `T` khi phép chuyển đổi được hỗ trợ; **Java `null` nếu giá trị SQL là `NULL`**.

Ví dụ:

```java
Integer points = resultSet.getObject("points", Integer.class);
BigDecimal creditLimit = resultSet.getObject("credit_limit", BigDecimal.class);
LocalDate joinDate = resultSet.getObject("join_date", LocalDate.class);
```

Khi phù hợp với kiểu SQL và driver, cách đọc này giúp tránh ép kiểu thủ công từ `Object`, đồng thời giữ được trạng thái `NULL` của cột.

### So sánh ba cách đọc

Giả sử cột `points` là SQL `INTEGER` và cho phép `NULL`:

| Lời gọi | Kiểu trả về | Khi cột SQL là `NULL` | Điều cần lưu ý |
|---|---|---|---|
| `getInt("points")` | `int` | `0` | Phải gọi `wasNull()` ngay sau getter |
| `getObject("points")` | `Object` | `null` | Kiểu Java cụ thể do ánh xạ mặc định của driver quyết định |
| `getObject("points", Integer.class)` | `Integer` | `null` | Cần driver hỗ trợ chuyển đổi SQL type sang `Integer` |

Hai trường hợp khác nhau rõ rệt:

```java
// Khi SQL points = NULL và driver hỗ trợ typed getObject:
Integer unknown = resultSet.getObject("points", Integer.class); // null

// Khi SQL points = 0:
Integer knownZero = resultSet.getObject("points", Integer.class); // 0
```

Đây là điểm mạnh của lớp wrapper: `Integer` có thể biểu diễn cả giá trị số và tình trạng thiếu giá trị, còn `int` thì không.

## 2. Hiểu đúng Class<T> và kết quả nullable

### 2.1. Lớp đích phải phù hợp với ngữ nghĩa của dữ liệu

Lớp đích chỉ định **kiểu Java ứng dụng muốn nhận**. Nó không thay đổi kiểu cột trong cơ sở dữ liệu, không tự nâng cấp driver và không cam kết driver có thể chuyển đổi tùy ý.

```java
Integer quantity = rs.getObject("quantity", Integer.class);
Long orderId = rs.getObject("order_id", Long.class);
BigDecimal amount = rs.getObject("amount", BigDecimal.class);
String description = rs.getObject("description", String.class);
```

Nên chọn lớp có khả năng biểu diễn đầy đủ dữ liệu. Ví dụ, nếu SQL `BIGINT` có thể lớn hơn phạm vi `Integer`, hãy dùng `Long.class`. Nếu SQL `DECIMAL(18, 2)` chứa giá trị tiền, `BigDecimal.class` an toàn hơn `Double.class` vì tránh mất độ chính xác do số thực nhị phân.

**Không dùng `int.class` hay `boolean.class` như lựa chọn mặc định** khi dữ liệu có thể `NULL`. Tham số kiểu nguyên thủy không có khả năng biểu diễn Java `null`; cách dùng tương thích, rõ nghĩa là `Integer.class`, `Boolean.class` và các lớp wrapper khác.

### 2.2. SQL NULL được giữ thành Java null

Khi driver hỗ trợ `getObject(column, Class<T>)` và chuyển đổi tương ứng, nếu giá trị của cột là SQL `NULL`, kết quả trả về là Java `null`:

```java
Integer retries = rs.getObject("retry_count", Integer.class);

if (retries == null) {
    System.out.println("Chưa có số lần thử lại");
} else if (retries == 0) {
    System.out.println("Đã xác định: 0 lần");
} else {
    System.out.println("Đã thử lại: " + retries + " lần");
}
```

Đối với getter trả về đối tượng, so sánh trực tiếp với `null` thường là đủ; không cần gọi thêm `wasNull()` để phân biệt với `0` hay `false`. `wasNull()` đặc biệt hữu ích cho những getter trả về kiểu nguyên thủy, chẳng hạn `getInt()`, `getLong()` và `getBoolean()`.

Một giá trị `null` của trường trong đối tượng Java **khác** với trường hợp truy vấn không có dòng. `ResultSet.next() == false` nghĩa là **không có bản ghi để đọc**; còn một hàng tồn tại với cột SQL `NULL` có thể cho `getObject(...) == null`.

### 2.3. Đừng tự động unbox một giá trị có thể null

`Integer` và `Boolean` là kiểu tham chiếu; Java có thể tự chuyển chúng thành `int` hoặc `boolean` khi gán hoặc so sánh. Nếu giá trị đang là `null`, thao tác unboxing sẽ gây `NullPointerException`:

```java
Integer points = rs.getObject("points", Integer.class);

// Nguy hiểm khi points == null:
// int count = points;
// if (points > 0) { ... }

if (points != null && points > 0) {
    System.out.println("Điểm đang dương");
}
```

Với Boolean nullable, `Boolean.TRUE.equals(value)` chỉ kiểm tra trạng thái đúng; nếu nghiệp vụ cần phân biệt cả `null`, `true` và `false`, hãy dùng ba nhánh rõ ràng.

## 3. Bảng ánh xạ kiểu SQL sang Class<T>

Bảng dưới là những lớp Java đích **thường phù hợp** với SQL type tương ứng. Khả năng thực thi của `getObject(column, Class<T>)` vẫn phải được xác minh trên driver và DBMS cụ thể.

| SQL type điển hình | Lớp Java đích nên cân nhắc | Lưu ý |
|---|---|---|
| `SMALLINT` | `Short.class` | Giữ đúng phạm vi số nhỏ |
| `INTEGER` | `Integer.class` | Có thể `null` nếu cột nullable |
| `BIGINT` | `Long.class` | Tránh ép xuống `Integer` gây tràn hoặc lỗi chuyển đổi |
| `DECIMAL` / `NUMERIC` | `BigDecimal.class` | Giữ độ chính xác thập phân |
| `REAL` / `FLOAT` / `DOUBLE` | `Float.class` / `Double.class` theo SQL type | Có sai số biểu diễn số thực nhị phân |
| `CHAR` / `VARCHAR` | `String.class` | Hỗ trợ chuỗi; xử lý khác biệt `NULL`/chuỗi rỗng theo DBMS |
| `BOOLEAN` / `BIT` | `Boolean.class` nếu DBMS có mapping phù hợp | DBMS có thể mô phỏng boolean qua kiểu số |
| `DATE` | `LocalDate.class` | Mapping thời gian của JDBC 4.2; cần kiểm tra driver |
| `TIME` | `LocalTime.class` | Thời gian trong ngày không có ngày/múi giờ |
| `TIMESTAMP` | `LocalDateTime.class` | Ngày giờ không mang offset trong đối tượng |
| `TIME_WITH_TIMEZONE` | `OffsetTime.class` | Chỉ khi DBMS/driver hỗ trợ SQL type và chuyển đổi này |
| `TIMESTAMP_WITH_TIMEZONE` | `OffsetDateTime.class` | Lưu và hiểu offset theo DBMS/driver |
| `BINARY` / `VARBINARY` | `byte[].class` trong trường hợp được driver hỗ trợ | Với dữ liệu lớn thường có API stream phù hợp |

Những kiểu **vendor-specific** như PostgreSQL `UUID`, JSON/JSONB, các kiểu mảng hoặc cấu trúc đặc biệt thường có quy tắc riêng; chẳng hạn `getObject("id", UUID.class)` có thể dùng được với một driver phù hợp nhưng **không phải bảo đảm chuẩn chung cho mọi SQL type hoặc mọi DBMS**. Đọc tài liệu driver trước khi yêu cầu lớp như `UUID.class` hoặc lớp JSON riêng.

### JDBC 4.2 và java.time

JDBC 4.2 mở rộng hỗ trợ các kiểu Java 8 Date and Time API. Ví dụ:

```java
LocalDate businessDate = rs.getObject("business_date", LocalDate.class);
LocalTime openingTime = rs.getObject("opening_time", LocalTime.class);
LocalDateTime createdAt = rs.getObject("created_at", LocalDateTime.class);
OffsetDateTime createdWithOffset =
        rs.getObject("created_with_offset", OffsetDateTime.class);
```

Những lớp trên biểu diễn các ý nghĩa khác nhau:

- `LocalDate` chỉ có ngày.
- `LocalTime` chỉ có giờ trong ngày.
- `LocalDateTime` có ngày và giờ, **không mang offset hoặc múi giờ**.
- `OffsetDateTime` có ngày, giờ và offset UTC; điều này không đồng nghĩa giữ nguyên tên vùng giờ như `Asia/Ho_Chi_Minh`.

Đặc biệt không nên mặc định có thể lấy `OffsetDateTime` trực tiếp từ bất kỳ cột `TIMESTAMP` nào. Cần kiểm tra schema, loại timestamp của DBMS, cách driver đọc offset và yêu cầu nghiệp vụ. Một số DBMS lưu giá trị theo múi giờ của session hoặc chuẩn hóa timestamp thay vì giữ nguyên offset đầu vào.

## 4. Ví dụ đầy đủ: đọc DTO bằng typed getObject

Giả sử ứng dụng quản lý hồ sơ khách hàng sử dụng bảng:

```sql
CREATE TABLE customer_profiles (
    profile_id      BIGINT PRIMARY KEY,
    loyalty_points  INTEGER NULL,
    credit_limit    DECIMAL(12, 2) NULL,
    joined_on       DATE NULL,
    last_seen_at    TIMESTAMP NULL,
    nickname        VARCHAR(100) NULL
);
```

Để minh họa các trạng thái dữ liệu, hai dòng mẫu có thể có giá trị như sau:

| `profile_id` | `loyalty_points` | `credit_limit` | `joined_on` | `last_seen_at` |
|---|---|---|---|---|
| `1` | `NULL` | `NULL` | `NULL` | `NULL` |
| `2` | `0` | `0.00` | Ngày hợp lệ | Thời điểm hợp lệ |

Ví dụ Java dưới đây dùng `DataSource` đã cấu hình sẵn, `PreparedStatement` để tránh nối giá trị vào SQL và `record` để biểu diễn DTO. `record` yêu cầu Java 16 trở lên; API `java.time` có từ Java 8. Driver JDBC cần hỗ trợ các chuyển đổi lớp đích được yêu cầu.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Optional;

public final class CustomerProfileReader {

    public record Profile(
            long id,
            Integer loyaltyPoints,
            BigDecimal creditLimit,
            LocalDate joinedOn,
            LocalDateTime lastSeenAt,
            String nickname) {}

    public static Optional<Profile> findById(
            DataSource dataSource, long profileId) throws SQLException {

        String sql = "SELECT profile_id, loyalty_points, credit_limit, "
                + "joined_on, last_seen_at, nickname "
                + "FROM customer_profiles WHERE profile_id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, profileId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    // Không có dòng khớp với profileId.
                    return Optional.empty();
                }

                Profile profile = new Profile(
                        rs.getLong("profile_id"),
                        rs.getObject("loyalty_points", Integer.class),
                        rs.getObject("credit_limit", BigDecimal.class),
                        rs.getObject("joined_on", LocalDate.class),
                        rs.getObject("last_seen_at", LocalDateTime.class),
                        rs.getString("nickname"));

                return Optional.of(profile);
            }
        }
    }
}
```

Ở đây, `profile_id` là khóa chính không cho phép `NULL`, nên `getLong(...)` phù hợp; các cột còn lại có thể `NULL`. Khi cột `loyalty_points` là `NULL`, thuộc tính `Integer loyaltyPoints` của record cũng là `null`; nếu cột bằng 0 thật, thuộc tính là `0`. Với `credit_limit`, `BigDecimal` giúp giữ phần thập phân chính xác.

Sự khác biệt giữa **không tìm thấy dòng** và **dòng có cột NULL** thể hiện rõ:

```java
Optional<CustomerProfileReader.Profile> found =
        CustomerProfileReader.findById(dataSource, 1L);

if (found.isEmpty()) {
    System.out.println("Không tìm thấy hồ sơ");
} else {
    Integer points = found.get().loyaltyPoints();

    if (points == null) {
        System.out.println("Hồ sơ có tồn tại nhưng chưa có điểm");
    } else {
        System.out.println("Điểm hiện tại: " + points);
    }
}
```

`Optional.empty()` ở ví dụ này biểu thị **không tồn tại bản ghi**. Nó không nên được dùng thay thế trực tiếp cho mỗi giá trị nullable của từng cột khi ánh xạ entity/DTO.

### Dùng tên cột hay chỉ số cột?

Có thể viết:

```java
Integer pointsByName = rs.getObject("loyalty_points", Integer.class);
Integer pointsByIndex = rs.getObject(2, Integer.class);
```

Chỉ số là **1-based** và phụ thuộc thứ tự cột trong `SELECT`. Với tên cột, nếu SQL dùng alias:

```sql
SELECT loyalty_points AS points FROM customer_profiles;
```

thì `rs.getObject("points", Integer.class)` dùng **column label** `points`. Không mặc định driver nhận mọi biến thể tên cột gốc/alias giống nhau; nên chọn alias rõ ràng và dùng nhất quán.

## 5. Điều gì xảy ra nếu driver không hỗ trợ chuyển đổi?

Khi một phép chuyển đổi được yêu cầu, ứng dụng có thể gặp:

- **`SQLFeatureNotSupportedException`**: driver không hỗ trợ phương thức/tính năng được yêu cầu. Đây là lớp con của `SQLException`.
- **`SQLException` khác**: driver không thể chuyển SQL type sang lớp Java mong muốn, lỗi truy cập cột, lỗi dữ liệu, lỗi kết nối hoặc lỗi máy chủ.
- **`ClassCastException`** khi lập trình viên ép kiểu không phù hợp từ kết quả `getObject(column)` không typed. `getObject(column, Class<T>)` giúp khai báo loại mong đợi nhưng không làm mọi phép chuyển đổi đều hợp lệ.

Ví dụ có thể thất bại trên driver/DBMS không cung cấp chuyển đổi sang `LocalDate`:

```java
LocalDate joined = rs.getObject("joined_on", LocalDate.class);
```

Đây là **lỗi khả năng tương thích**, không phải dấu hiệu cột đang `NULL`. Một giá trị SQL `NULL` bình thường phải được biểu diễn bằng Java `null` khi phương thức hỗ trợ chuyển đổi đúng.

### 5.1. Fallback cho cột số nullable

Khi driver báo rõ không hỗ trợ typed `getObject`, có thể quay về getter nguyên thủy và `wasNull()`:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

public static Integer readNullableInt(ResultSet rs, String columnLabel)
        throws SQLException {
    try {
        return rs.getObject(columnLabel, Integer.class);
    } catch (SQLFeatureNotSupportedException unsupported) {
        int value = rs.getInt(columnLabel);
        return rs.wasNull() ? null : value;
    }
}
```

`wasNull()` phải được gọi **ngay sau** `getInt(...)`; nếu đọc thêm cột khác trước đó, cờ `NULL` có thể phản ánh sai cột.

Không viết:

```java
int value = rs.getInt("loyalty_points");
Integer points = value == 0 ? null : value; // Sai: 0 thật bị coi là NULL.
```

### 5.2. Fallback cho java.time

Với cột SQL `DATE` và `TIMESTAMP` không mang offset, có thể đọc bằng các getter JDBC truyền thống rồi chuyển đổi, nếu kiểu SQL/driver phù hợp:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;

public static LocalDate readNullableDate(
        ResultSet rs, String columnLabel) throws SQLException {

    Date value = rs.getDate(columnLabel);
    return value == null ? null : value.toLocalDate();
}

public static LocalDateTime readNullableTimestamp(
        ResultSet rs, String columnLabel) throws SQLException {

    Timestamp value = rs.getTimestamp(columnLabel);
    return value == null ? null : value.toLocalDateTime();
}
```

Đây là phương án chuyển đổi cho **DATE/TIMESTAMP thông thường**. Không áp dụng máy móc cho `TIMESTAMP WITH TIME ZONE` hoặc dữ liệu yêu cầu giữ offset/instant: cách driver chuyển timestamp qua timezone của JVM/session có thể làm thay đổi ý nghĩa thời gian. Đối với dữ liệu thời điểm tuyệt đối, cần chọn loại cột, kiểu Java và chính sách múi giờ một cách nhất quán.

### 5.3. Fallback cần có điều kiện

Mẫu `catch (SQLFeatureNotSupportedException ...)` chỉ xử lý khi driver **báo rõ** tính năng không được hỗ trợ. Trong thực tế, có driver dùng một `SQLException` chung để báo lỗi chuyển đổi sang một lớp cụ thể. Khi đó, cần đọc `SQLState`, mã lỗi driver và tài liệu trước khi quyết định chuyển sang getter truyền thống.

**Không bắt tất cả `SQLException` rồi âm thầm fallback**, vì có thể che mất lỗi thật như kết nối hỏng, cột không tồn tại hoặc truy vấn thất bại:

```java
// Không nên làm:
// try {
//     return rs.getObject("loyalty_points", Integer.class);
// } catch (SQLException ignored) {
//     return 0; // Làm mất NULL và che mọi lỗi.
// }
```

Một cách tổ chức tốt là ghi nhận khả năng driver ở thời điểm kiểm thử tích hợp và chọn mã đọc phù hợp ngay từ đầu, thay vì thử lại nhiều cách sau mọi `SQLException` trong môi trường sản xuất.

## 6. Kiểm tra khả năng hỗ trợ: metadata giúp gì và không giúp gì?

Không có một phương thức JDBC metadata phổ quát kiểu `supportsGetObject(Class<T>)` cho biết **mọi** chuyển đổi SQL type → lớp Java đích đều được hỗ trợ. Vì vậy, phải kết hợp **thông tin driver**, **kiểu SQL thực tế** và **phép thử đọc giá trị**.

### 6.1. Nhận diện driver, DBMS và mức API JDBC

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("Driver: " + meta.getDriverName());
    System.out.println("Driver version: " + meta.getDriverVersion());
    System.out.println("DBMS: " + meta.getDatabaseProductName());
    System.out.println("Server version: "
            + meta.getDatabaseProductVersion());
    System.out.println("JDBC API: " + meta.getJDBCMajorVersion()
            + "." + meta.getJDBCMinorVersion());
}
```

Đoạn mã giả định đã có `DataSource dataSource`, cùng import `javax.sql.DataSource` và `java.sql.SQLException` nếu đặt trong phương thức có `throws SQLException`. Những thông tin này giúp tra tài liệu đúng phiên bản driver/DBMS.

Typed `getObject(column, Class<T>)` được bổ sung trong JDBC 4.1; hỗ trợ ánh xạ các kiểu `java.time` tiêu chuẩn được mở rộng ở JDBC 4.2. **Số phiên bản JDBC do driver công bố không phải cam kết mọi phép chuyển đổi Class<T> đều thành công.**

### 6.2. Đọc kiểu cột của ResultSet bằng ResultSetMetaData

`ResultSetMetaData` giúp biết một cột trả về từ SQL có kiểu gì:

```java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public static void describeColumns(ResultSet rs) throws SQLException {
    ResultSetMetaData columns = rs.getMetaData();

    for (int i = 1; i <= columns.getColumnCount(); i++) {
        System.out.printf(
                "column=%s, JDBCType=%d, SQLType=%s, JavaClass=%s%n",
                columns.getColumnLabel(i),
                columns.getColumnType(i),
                columns.getColumnTypeName(i),
                columns.getColumnClassName(i));
    }
}
```

| Phương thức | Ý nghĩa |
|---|---|
| `getColumnType(i)` | Mã JDBC/SQL type (đối chiếu `java.sql.Types`) |
| `getColumnTypeName(i)` | Tên SQL type do driver báo cáo |
| `getColumnClassName(i)` | Tên lớp Java dự kiến trả về từ `getObject(i)` dạng không typed |
| `getColumnLabel(i)` | Tên/alias cột để truy cập bằng label |
| `isNullable(i)` | Metadata về khả năng cho phép `NULL`, nếu driver cung cấp được |

**Cảnh báo quan trọng:** `getColumnClassName(i)` nói về kiểu Java của `getObject(i)` **không truyền lớp đích**. Nó **không phải danh sách những `Class<T>` mà typed `getObject` chấp nhận**. Driver cũng có thể báo khả năng nullable ở mức metadata nhưng dữ liệu thực tế hay kết quả biểu thức `JOIN` vẫn cần được kiểm tra theo nghiệp vụ.

### 6.3. DatabaseMetaData.getTypeInfo() và supportsConvert()

`DatabaseMetaData.getTypeInfo()` liệt kê thông tin các kiểu SQL mà DBMS/driver khai báo. Một số driver còn cung cấp:

```java
boolean sqlTypeConversion = meta.supportsConvert(
        java.sql.Types.INTEGER, java.sql.Types.BIGINT);
```

Nhưng `supportsConvert(fromType, toType)` hỏi về **chuyển đổi giữa các mã SQL/JDBC type**, không phải phép kiểm tra trực tiếp `rs.getObject("points", Integer.class)` có hoạt động hay không. `getTypeInfo()` cũng không bảo đảm phép chuyển đổi SQL DATE → `LocalDate` trên driver đang sử dụng.

Thông tin metadata nên được sử dụng để **khoanh vùng khả năng và phân tích lỗi**, còn câu trả lời chắc chắn nhất cho nhu cầu ứng dụng nằm ở phép thử typed getter với dữ liệu và schema đại diện.

## 7. Thử nghiệm thực tế để xác nhận typed getObject

Một kiểm tra có ý nghĩa cần thực thi **đúng SQL**, **đúng SQL type**, **đúng Class<T>**, **đúng driver/DBMS** và **đúng dữ liệu nullable**. Một trường hợp thành công không bảo đảm mọi kiểu cột khác đều thành công.

### 7.1. Bảng dữ liệu và các trường hợp cần kiểm tra

Với bảng `customer_profiles` ở mục 4, hãy tạo các dòng có:

- `profile_id = 1`: `loyalty_points`, `credit_limit`, `joined_on` và `last_seen_at` đều SQL `NULL`.
- `profile_id = 2`: `loyalty_points = 0`, `credit_limit = 0.00` và có ngày giờ hợp lệ.
- `profile_id = 3`: `loyalty_points` là số dương, `credit_limit` có phần thập phân, ngày giờ hợp lệ.

Việc có cả `NULL` và `0` thật cho phép phát hiện lỗi biến `NULL` thành mặc định. Trường hợp ngày giờ giúp xác nhận `LocalDate.class`/`LocalDateTime.class`, còn `BigDecimal` cần bảo toàn số lẻ và scale theo yêu cầu dữ liệu.

### 7.2. Ví dụ kiểm tra nhỏ bằng JDBC

Đoạn dưới kiểm tra phép chuyển đổi `INTEGER → Integer` trên một dòng đã biết, không thay đổi dữ liệu:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void verifyNullableInteger(
        DataSource dataSource, long id, Integer expected)
        throws SQLException {

    String sql = "SELECT loyalty_points FROM customer_profiles "
            + "WHERE profile_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id);
        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalStateException("Thiếu dữ liệu thử id=" + id);
            }

            Integer actual = rs.getObject("loyalty_points", Integer.class);
            if (!java.util.Objects.equals(expected, actual)) {
                throw new IllegalStateException(
                        "Sai chuyển đổi: expected=" + expected
                                + ", actual=" + actual);
            }
        }
    }
}
```

Khi dữ liệu mẫu được chuẩn bị:

```java
verifyNullableInteger(dataSource, 1L, null);
verifyNullableInteger(dataSource, 2L, 0);
verifyNullableInteger(dataSource, 3L, 12); // Nếu dòng 3 chứa đúng 12.
```

Đây là phép thử đọc thuần túy, cần đặt trong class/method Java phù hợp và cung cấp `DataSource`. Trước khi gọi dòng thứ ba, hãy tạo dữ liệu có `loyalty_points = 12`. Nếu phép chuyển đổi không được hỗ trợ, `SQLException` là kết quả cần được phân tích, **không phải tự động coi bài kiểm tra thành công**.

### 7.3. Tiêu chí đánh giá

| Kiểm tra | Kết quả mong đợi |
|---|---|
| `INTEGER NULL → Integer.class` | Java `null` |
| `INTEGER 0 → Integer.class` | Java `Integer(0)` |
| `DECIMAL 12.30 → BigDecimal.class` | Giá trị chính xác `12.30` theo ý nghĩa và scale của DBMS |
| `DATE → LocalDate.class` | Ngày không bị lệch |
| `TIMESTAMP → LocalDateTime.class` | Ngày giờ tương ứng với kiểu cột/cấu hình thời gian |
| Kiểu đích không hỗ trợ | Ngoại lệ rõ ràng, không âm thầm dùng giá trị mặc định |
| Query không có bản ghi | `rs.next() == false`, không phải một giá trị cột `null` |

Nên chạy lại bộ thử khi nâng cấp driver, Java runtime, DBMS hoặc thay đổi schema/kiểu cột. Nếu ứng dụng có nhiều `DataSource`, cần thử từng kết nối thực tế.

## 8. CallableStatement cũng có typed getObject

Ngoài `ResultSet`, `CallableStatement` có overload `getObject(index, Class<T>)` và `getObject(name, Class<T>)` cho các tham số OUT phù hợp. Trước khi đọc OUT parameter, cần đăng ký kiểu SQL và thực thi stored procedure/function theo cú pháp DBMS:

```java
import java.sql.CallableStatement;
import java.sql.Types;

// SQL gọi procedure ở đây chỉ là ví dụ; cú pháp khác nhau theo DBMS.
try (CallableStatement call =
             connection.prepareCall("{call read_customer_points(?)}")) {

    call.registerOutParameter(1, Types.INTEGER);
    call.execute();

    Integer points = call.getObject(1, Integer.class);
    // points có thể null nếu OUT parameter trả SQL NULL.
}
```

Ví dụ giả định procedure `read_customer_points` đã tồn tại và có một tham số OUT kiểu `INTEGER`; không thể chạy nguyên mẫu nếu DBMS không hỗ trợ kiểu khai báo/cú pháp đó. Với driver không hỗ trợ typed getter cho OUT parameter, có thể đọc bằng `call.getInt(1)` rồi `call.wasNull()`, nhưng phải kiểm tra cờ ngay sau getter.

Phần lớn quy tắc về **lớp đích, NULL, chuyển đổi kiểu và kiểm tra driver** cũng áp dụng cho `CallableStatement`.

## 9. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Dùng `(Integer) rs.getObject("points")` với mọi DBMS | Driver có thể trả lớp số khác; ép kiểu lỗi | Dùng typed getter nếu hỗ trợ, hoặc getter SQL cụ thể |
| Cho rằng `getObject(column, Class<T>)` chuyển được mọi SQL type | Nhận `SQLException` hoặc `SQLFeatureNotSupportedException` | Đối chiếu mapping và thử trên DBMS thật |
| Dùng `int.class` cho cột SQL nullable | Không thể biểu diễn `null` bằng primitive | Chọn `Integer.class` và xử lý `null` |
| Gán `Integer` nullable vào `int` ngay | Có thể `NullPointerException` khi unbox | Kiểm tra `null` hoặc chọn giá trị mặc định theo nghiệp vụ |
| Đọc `DECIMAL` thành `Double` cho tiền | Sai số số thực nhị phân | Dùng `BigDecimal.class` / `getBigDecimal()` |
| Đọc `BIGINT` thành `Integer` mà không xét phạm vi | Tràn số hoặc lỗi chuyển đổi | Dùng `Long.class` khi phù hợp |
| Cho rằng JDBC 4.2 bảo đảm mọi driver đều đọc được `OffsetDateTime` | Một số SQL type/driver không hỗ trợ | Xác minh loại cột và integration test |
| Dùng `getColumnClassName()` để quyết định mọi `Class<T>` có thể dùng | Metadata này mô tả getter không typed | Thử trực tiếp phép chuyển đổi cần dùng |
| Bắt mọi `SQLException` và trả `null` | Che lỗi mạng/cột/driver và làm sai dữ liệu | Chỉ fallback cho trường hợp đã phân loại rõ |
| Nhầm `rs.next() == false` với cột SQL `NULL` | Không phân biệt thiếu dòng với thiếu giá trị | Xử lý kết quả truy vấn và thuộc tính nullable ở hai lớp khác nhau |
| Gọi `wasNull()` sau getter của cột khác | Kiểm tra trạng thái NULL sai cột | Gọi ngay sau primitive getter liên quan |
| Coi `Timestamp` với `OffsetDateTime` luôn tương đương | Có thể mất offset và thay đổi thời điểm | Dùng kiểu SQL/Java phù hợp yêu cầu múi giờ |

## 10. Bài tập tự kiểm tra

**Câu 1.** Vì sao `Integer points = rs.getObject("points", Integer.class)` có thể thích hợp hơn `int points = rs.getInt("points")` khi cột SQL cho phép `NULL`?

**Đáp án:** `Integer` có thể mang Java `null` tương ứng SQL `NULL`, còn `getInt()` trả `0` cho SQL `NULL` và cần `wasNull()` để phân biệt với số 0 thật, với điều kiện driver hỗ trợ typed `getObject`.

**Câu 2.** Khi `getObject("joined_on", LocalDate.class)` thất bại với `SQLFeatureNotSupportedException`, có thể làm gì?

**Đáp án:** Kiểm tra tài liệu driver/DBMS; nếu cột là `DATE` thông thường, có thể đọc `java.sql.Date date = rs.getDate("joined_on")` rồi dùng `date == null ? null : date.toLocalDate()`.

**Câu 3.** `ResultSetMetaData.getColumnClassName(i)` có chứng minh `rs.getObject(i, LocalDate.class)` chạy được không?

**Đáp án:** Không. Metadata mô tả lớp Java cho `getObject(i)` không typed; hỗ trợ chuyển đổi sang `Class<T>` cụ thể phải được xác minh riêng.

**Câu 4.** Driver công bố JDBC 4.2, có thể kết luận mọi cột ngày giờ của mọi DBMS đều hỗ trợ `OffsetDateTime.class` không?

**Đáp án:** Không. Phải xét đúng SQL type, cách DBMS xử lý timezone, driver và phép thử thực tế.

**Câu 5.** Có nên bắt mọi `SQLException` khi đọc typed getter rồi trả về `null` để tránh gián đoạn ứng dụng không?

**Đáp án:** Không. `SQLException` có thể báo lỗi kết nối, tên cột sai hoặc dữ liệu không chuyển đổi được; trả `null` âm thầm sẽ làm mất lỗi và sai nghiệp vụ.

**Câu 6.** Một truy vấn không trả dòng nào. `getObject(...)` có trả `null` để thông báo “không tìm thấy” không?

**Đáp án:** Không. Cần gọi `rs.next()`; nếu trả `false` thì không có dòng để đọc. Chỉ gọi getter khi con trỏ đang đứng trên một hàng hợp lệ.

**Câu 7.** `rs.getObject("price", BigDecimal.class)` có thể tránh điều gì so với `rs.getDouble("price")`?

**Đáp án:** `BigDecimal` giúp bảo toàn giá trị thập phân chính xác theo dữ liệu/driver và có thể mang `null`, trong khi `double` là kiểu số thực nhị phân không chứa `null` và có sai số biểu diễn.

**Câu 8.** Khi cùng một typed getter hoạt động trên máy phát triển nhưng lỗi sau nâng driver ở máy chủ, cần thu thập thông tin gì?

**Đáp án:** Phiên bản Java runtime, tên/phiên bản driver thực đang dùng, DBMS/server, SQL type từ `ResultSetMetaData`, lớp `Class<T>` được yêu cầu, `SQLState`/mã lỗi và kết quả thử trên máy chủ mục tiêu.

## 11. Ghi nhớ

`getObject(column, Class<T>)` là cách rõ ràng để yêu cầu **đúng lớp Java đích** khi đọc dữ liệu từ JDBC, đồng thời giữ SQL `NULL` thành Java `null` với kiểu tham chiếu phù hợp. Hãy chọn lớp theo **SQL type và nghiệp vụ**, xác minh **hỗ trợ thực tế của driver** bằng metadata, tài liệu và integration test, rồi dùng getter truyền thống cùng `wasNull()` hoặc các phương án chuyển đổi ngày giờ có kiểm soát khi cần. Việc bảo toàn cả kiểu dữ liệu và ý nghĩa `NULL` giúp tầng Java tránh những lỗi âm thầm khi làm việc với cơ sở dữ liệu quan hệ.
