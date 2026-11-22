# Xử lý giá trị boolean và các biểu diễn do JDBC driver hỗ trợ

## 1. Vì sao boolean trong SQL không đơn giản như `boolean` của Java?

**JDBC (Java Database Connectivity)** là API chuẩn giúp Java truy cập cơ sở dữ liệu quan hệ. Khi đọc hoặc ghi một trường biểu thị trạng thái bật/tắt, ứng dụng thường muốn dùng `boolean` hoặc `Boolean`. Nhưng ở phía database, giá trị đó có thể được lưu bằng kiểu `BOOLEAN`, `BIT`, số `0/1`, hoặc chuỗi `Y/N`, tùy hệ quản trị, phiên bản, schema và JDBC driver.

Vấn đề quan trọng hơn sự khác biệt tên kiểu là **SQL có thể biểu diễn giá trị `NULL`**, trong khi kiểu nguyên thủy `boolean` của Java chỉ có `true` hoặc `false`. Nếu bỏ qua `NULL` khi đọc `ResultSet`, ứng dụng có thể hiểu nhầm “chưa xác định” thành “không”.

Ví dụ, bảng theo dõi việc đồng ý nhận thông báo có ba trạng thái:

| Giá trị database | Ý nghĩa nghiệp vụ | Giá trị Java phù hợp |
|---|---|---|
| `TRUE` | Người dùng đã đồng ý | `Boolean.TRUE` |
| `FALSE` | Người dùng đã từ chối | `Boolean.FALSE` |
| `NULL` | Chưa có lựa chọn hoặc chưa được xác nhận | `null` |

Nếu một trường chỉ được phép có hai trạng thái, schema có thể dùng `NOT NULL` và quy định giá trị mặc định hợp lệ. Nếu nghiệp vụ thực sự có ba trạng thái, dùng `Boolean` nullable hoặc một enum ba trạng thái sẽ truyền đạt ý nghĩa tốt hơn.

Bài thuộc chương **Kiểu dữ liệu và NULL**, tập trung vào bốn câu hỏi: database lưu boolean theo kiểu gì; JDBC driver trả về kiểu nào; đọc/ghi mà không làm mất trạng thái `NULL` ra sao; và cách thiết kế mã đủ rõ ràng khi chuyển giữa các driver.

## 2. Hai trạng thái ở Java, ba trạng thái trong SQL

### 2.1. `boolean` và `Boolean`

~~~java
boolean enabled = false; // Chỉ true hoặc false.

Boolean accepted = Boolean.TRUE;
Boolean rejected = Boolean.FALSE;
Boolean unanswered = null;
~~~

`boolean` là primitive: không thể nhận `null`. `Boolean` là kiểu tham chiếu: có thể nhận `true`, `false` hoặc `null`.

Điều này dẫn đến quy tắc lựa chọn kiểu:

- Cột bảo đảm `NOT NULL` và có ý nghĩa hai trạng thái: có thể ánh xạ thành `boolean`.
- Cột cho phép SQL `NULL`: dùng `Boolean`, enum hoặc một kiểu biểu diễn trạng thái rõ nghĩa.
- Nếu `NULL` không hợp lệ với nghiệp vụ dù database đang cho phép, phải kiểm tra và báo lỗi dữ liệu, thay vì âm thầm thay `NULL` thành `false`.

Ví dụ không an toàn:

~~~java
Boolean consent = null;
if (consent) { // Ném NullPointerException do auto-unboxing.
    sendNotification();
}
~~~

Khi muốn chỉ xử lý giá trị `true`:

~~~java
if (Boolean.TRUE.equals(consent)) {
    sendNotification();
}
~~~

Biểu thức trên không ném `NullPointerException`, nhưng vẫn phải quyết định hành vi riêng cho `NULL` nếu nghiệp vụ cần phân biệt “chưa trả lời” với “từ chối”.

### 2.2. Logic ba giá trị của SQL

Trong SQL, biểu thức boolean có thể là `TRUE`, `FALSE` hoặc `UNKNOWN`; điều kiện liên quan đến `NULL` thường cho kết quả `UNKNOWN`.

| `active` | `active = TRUE` | `NOT (active = TRUE)` |
|---|---|---|
| `TRUE` | TRUE | FALSE |
| `FALSE` | FALSE | TRUE |
| `NULL` | UNKNOWN | UNKNOWN |

Trong mệnh đề `WHERE`, chỉ hàng có điều kiện đánh giá là **TRUE** được giữ lại; cả `FALSE` và `UNKNOWN` đều không được chọn.

Ví dụ với database hỗ trợ SQL `BOOLEAN`:

~~~sql
SELECT id FROM accounts WHERE active = TRUE;
SELECT id FROM accounts WHERE active = FALSE;
SELECT id FROM accounts WHERE active IS NULL;
~~~

Để tìm các hàng có giá trị `NULL`, phải dùng `IS NULL`, không dùng `active = NULL`. Cú pháp boolean literal/predicate và hỗ trợ `BOOLEAN` khác nhau giữa các hệ quản trị; riêng phần minh họa này giả định database hỗ trợ kiểu boolean SQL.

**Hệ quả nghiệp vụ:** “không bật” có thể được định nghĩa là chỉ `FALSE` hoặc gồm cả `FALSE` và `NULL`. Hai cách hiểu này không giống nhau; phải làm rõ yêu cầu trước khi viết câu SQL hoặc mã Java.

## 3. Các cách lưu cờ boolean trong cơ sở dữ liệu

Không có một cách biểu diễn duy nhất được mọi database và JDBC driver dùng giống hệt nhau:

| Hệ thống / loại schema | Biểu diễn thường gặp | Điều cần kiểm tra khi dùng JDBC |
|---|---|---|
| PostgreSQL | `BOOLEAN` với `TRUE`/`FALSE`/`NULL` | Driver hỗ trợ đọc `getBoolean` và bind boolean cho cột tương ứng |
| MySQL | `BOOLEAN`/`BOOL` là alias của `TINYINT(1)` | Kiểm tra cả giá trị dữ liệu lẫn metadata và thiết lập chuyển đổi của Connector/J |
| Microsoft SQL Server | `BIT` nhận 0, 1 hoặc `NULL` | Phân biệt kiểu database `BIT` với bitstring của hệ quản trị khác |
| Oracle Database trước dòng hỗ trợ SQL `BOOLEAN` (trước 23c) | Thường dùng `NUMBER(1)`, `CHAR(1)` hoặc quy ước tương đương | Cần mapping 0/1 hoặc Y/N theo schema; không giả định mọi driver chấp nhận `setBoolean` |
| Oracle Database phiên bản mới có SQL `BOOLEAN` | Có kiểu boolean SQL, tùy phiên bản và driver | Kiểm tra tính năng SQL, phiên bản JDBC driver và khả năng chuyển đổi |
| SQLite | Thường quy ước số 0/1; không có lớp lưu trữ BOOLEAN độc lập như PostgreSQL | Kiểm tra cột, dữ liệu thực tế và driver; giá trị khác 0/1 có thể cần bị từ chối |
| Hệ thống cũ hoặc schema tùy biến | `CHAR(1)` lưu `Y/N`, `T/F`, `1/0`; số `SMALLINT/INTEGER` | Dùng quy tắc giải mã tường minh và kiểm tra dữ liệu không hợp lệ |

Bảng mô tả **các trường hợp phổ biến**, không phải danh sách chuyển đổi mà mọi driver bắt buộc triển khai. Cả phiên bản database lẫn cấu hình driver có thể ảnh hưởng đến kiểu JDBC được báo qua metadata hoặc kiểu đối tượng trả về bởi `getObject`.

Lưu ý thêm: `BIT` có thể mang ý nghĩa khác giữa các hệ quản trị. Ví dụ, `BIT` trong SQL Server thường được dùng làm cờ logic, còn PostgreSQL có kiểu `bit string` khác với `boolean`. Vì vậy, **không suy luận nghĩa chỉ từ tên kiểu** khi chuyển schema sang database khác.

### 3.1. Chọn schema theo ý nghĩa nghiệp vụ

Với cơ sở dữ liệu hỗ trợ `BOOLEAN` SQL, ví dụ:

~~~sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    active  BOOLEAN
);
~~~

Ở đây, `active` có thể `NULL`. Nếu mọi tài khoản bắt buộc phải xác định trạng thái:

~~~sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    active  BOOLEAN NOT NULL
);
~~~

Nếu dùng MySQL và cần bảo đảm cờ chỉ nhận 0/1, cần biết `BOOLEAN` ở đó là alias của `TINYINT(1)` và có thể lưu những số khác theo quy tắc kiểu số; nên đặt **ràng buộc kiểm tra phù hợp và kiểm soát đầu vào** theo phiên bản database. Tương tự, một cột `INTEGER` lưu cờ nên có ràng buộc miền giá trị và xử lý dữ liệu cũ không hợp lệ.

## 4. Đọc cột boolean đúng cách bằng `getBoolean` và `wasNull`

`ResultSet.getBoolean(...)` trả về primitive `boolean`. Theo hợp đồng JDBC, khi cột SQL là `NULL`, getter này trả về `false`. Vì thế **chỉ gọi `getBoolean` là chưa đủ** khi bạn cần bảo toàn ba trạng thái.

### 4.1. Ví dụ tối thiểu

~~~java
boolean raw = rs.getBoolean("active");
boolean sqlNull = rs.wasNull(); // Phải kiểm tra ngay sau getter tương ứng.
Boolean active = sqlNull ? null : raw;
~~~

Kết quả:

| SQL `active` | `getBoolean("active")` | `wasNull()` | `active` |
|---|---|---|---|
| TRUE | true | false | `Boolean.TRUE` |
| FALSE | false | false | `Boolean.FALSE` |
| NULL | false | true | `null` |

`wasNull()` phản ánh **giá trị cột được đọc gần nhất**. Không đọc một cột khác trước khi kiểm tra:

~~~java
boolean active = rs.getBoolean("active");
String label = rs.getString("label");
boolean wasActiveNull = rs.wasNull(); // SAI ý định: kiểm tra "label".
~~~

Đúng phải là:

~~~java
boolean active = rs.getBoolean("active");
boolean wasActiveNull = rs.wasNull();
String label = rs.getString("label");
~~~

Nếu schema bảo đảm `active NOT NULL`, bạn có thể dùng primitive và có thể kiểm tra dữ liệu không đúng kỳ vọng:

~~~java
boolean active = rs.getBoolean("active");
if (rs.wasNull()) {
    throw new java.sql.SQLException("Dữ liệu active bất ngờ là NULL");
}
~~~

### 4.2. Ví dụ repository đầy đủ

Ví dụ dùng bảng `accounts(id, active)` có cột `active` kiểu boolean SQL, `javax.sql.DataSource` đã cấu hình và JDBC driver phù hợp:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

record AccountStatus(long id, Boolean active) {}

public final class AccountStatusRepository {
    private final DataSource dataSource;

    public AccountStatusRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<AccountStatus> findById(long accountId)
            throws SQLException {
        String sql = "SELECT id, active FROM accounts WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, accountId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không tồn tại bản ghi.
                }

                long id = rs.getLong("id");
                boolean raw = rs.getBoolean("active");
                boolean activeIsNull = rs.wasNull();
                return Optional.of(
                        new AccountStatus(id, activeIsNull ? null : raw));
            }
        }
    }
}
~~~

Ví dụ dùng Java 17+ để có `record`. Phải phân biệt **không có hàng** (phương thức trả `Optional.empty()`) với **hàng có `active = NULL`** (trả một `AccountStatus` mà thành phần `active` bằng `null`). Đây là hai trạng thái nghiệp vụ khác nhau.

Tất cả lần đọc `ResultSet` diễn ra trước khi đóng `ResultSet`, `PreparedStatement` và `Connection`. Khi đã ánh xạ thành `AccountStatus`, đối tượng Java có thể được dùng sau khi connection được trả về pool.

## 5. Có nên dùng `getObject(..., Boolean.class)`?

JDBC hỗ trợ một overload typed getter:

~~~java
Boolean active = rs.getObject("active", Boolean.class);
~~~

Đây có thể là cách đọc gọn cho cột kiểu boolean được driver hỗ trợ: nếu SQL `NULL`, phương thức trả `null` theo hợp đồng của typed `getObject`; nếu giá trị không `NULL` và chuyển đổi được, nó trả một `Boolean`.

Tuy nhiên, **khả năng chuyển đổi và hỗ trợ kiểu đích phụ thuộc driver và kiểu SQL thực tế**. Không giả định `getObject(..., Boolean.class)` sẽ luôn chuyển được `CHAR('Y')` hoặc `NUMBER(1)` sang `Boolean`. Driver có thể ném `SQLException` nếu không hỗ trợ chuyển đổi.

Một hướng đánh giá thực tế:

1. Với cột kiểu boolean/bit mà driver đã xác nhận hỗ trợ, dùng `getBoolean` + `wasNull` là cách tường minh và phổ biến.
2. Dùng typed `getObject(..., Boolean.class)` nếu đã kiểm tra hợp đồng driver và muốn nhận một `Boolean` nullable trực tiếp.
3. Với cột legacy `0/1`, `Y/N`, hãy ánh xạ theo **quy ước dữ liệu đã định**, kiểm tra giá trị không hợp lệ thay vì dựa vào chuyển đổi ngầm.

Overload không có kiểu đích — `rs.getObject("active")` — có thể trả về đối tượng với lớp khác nhau tùy driver và cấu hình. Không cast mù quáng kết quả sang `Boolean`.

## 6. Đọc cờ dạng số `0/1`

Nhiều schema cũ dùng `SMALLINT`, `INTEGER`, `NUMBER(1)` hoặc `TINYINT` để lưu:

- `1`: đúng/bật/đồng ý.
- `0`: sai/tắt/từ chối.
- `NULL`: chưa xác định, nếu cột cho phép.

Trong trường hợp này, ứng dụng nên **kiểm tra đúng 0 và 1**, thay vì tự quy ước “mọi số khác 0 là true” nếu schema nghiệp vụ chỉ cho phép hai giá trị.

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;

public final class NumericFlagMapper {
    public static Boolean readFlag(ResultSet rs, String columnLabel)
            throws SQLException {
        int value = rs.getInt(columnLabel);
        if (rs.wasNull()) {
            return null;
        }

        return switch (value) {
            case 0 -> Boolean.FALSE;
            case 1 -> Boolean.TRUE;
            default -> throw new SQLException(
                    "Giá trị cờ không hợp lệ tại cột " + columnLabel
                            + ": " + value);
        };
    }
}
~~~

Đoạn này dành cho cột **số nguyên có miền 0/1**; ví dụ dùng cú pháp `switch` hiện đại của Java 17+. Đối với `DECIMAL` có thể chứa phần thập phân, cần dùng getter kiểu thích hợp như `getBigDecimal` để không vô tình chuyển `1.5` thành một số nguyên trước khi kiểm tra. Cũng phải phân biệt giá trị thực tế và lỗi chuyển đổi từ driver.

Ví dụ:

~~~sql
SELECT id, enabled_flag
FROM legacy_accounts
WHERE id = ?;
~~~

~~~java
Boolean enabled = NumericFlagMapper.readFlag(rs, "enabled_flag");
~~~

Nếu cột nhận `2` hoặc `-1`, phương thức ném `SQLException` để người vận hành phát hiện dữ liệu sai, thay vì giải thích ngầm thành `true`.

### Một lưu ý riêng với MySQL

MySQL dùng `BOOLEAN`/`BOOL` như alias của `TINYINT(1)`. Việc driver trình bày `TINYINT(1)` như kiểu JDBC `BIT`/`BOOLEAN` hay `TINYINT` có thể phụ thuộc các thiết lập Connector/J và phiên bản. Nếu schema thật sự dùng `TINYINT(1)` để chứa **số đếm** hoặc giá trị không phải cờ, việc ép mọi cột đó thành `Boolean` là sai ngữ nghĩa.

Vì vậy, cần xem **schema, dữ liệu và cấu hình driver** trước khi lựa chọn getter và kiểu Java. Giá trị SQL 0/1 không tự tạo ra hợp đồng nghiệp vụ nếu không có ràng buộc hoặc kiểm soát đầu vào.

## 7. Đọc cờ dạng chuỗi `Y/N` hoặc `T/F`

Một số hệ thống lưu trạng thái qua `CHAR(1)` hoặc `VARCHAR` thay vì boolean SQL:

~~~sql
-- Minh họa một cột legacy:
-- newsletter_flag CHAR(1) cho phép 'Y', 'N', NULL
SELECT id, newsletter_flag
FROM users
WHERE id = ?;
~~~

Khi đó, dùng `getString` và ánh xạ tường minh:

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Locale;

public final class YesNoFlagMapper {
    public static Boolean readFlag(ResultSet rs, String columnLabel)
            throws SQLException {
        String raw = rs.getString(columnLabel);
        if (raw == null) {
            return null;
        }

        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "Y" -> Boolean.TRUE;
            case "N" -> Boolean.FALSE;
            default -> throw new SQLException(
                    "Cờ Y/N không hợp lệ ở cột " + columnLabel);
        };
    }
}
~~~

`trim()` xử lý khoảng trắng đệm thường gặp ở `CHAR`; `Locale.ROOT` giúp phép đổi hoa/thường không phụ thuộc ngôn ngữ của máy chạy Java. Nhưng ứng dụng không nên tùy tiện chấp nhận các biểu diễn `YES`, `T`, `1` nếu schema chính thức chỉ quy định `Y` và `N`.

Nếu hệ thống dùng `T/F`, hãy định nghĩa mapper riêng hoặc tham số hóa **tập giá trị được chấp nhận**. Một hàm “đoán boolean” quá rộng có thể che dữ liệu bẩn hoặc thay đổi ngữ nghĩa nghiệp vụ.

**Không phụ thuộc ngầm vào `getBoolean("newsletter_flag")`:** driver có thể không hỗ trợ chuyển `Y/N` sang boolean hoặc sử dụng quy tắc khác. Với cờ ký tự, ánh xạ minh bạch sẽ dễ chuyển database và dễ kiểm thử hơn.

## 8. Ghi boolean bằng `PreparedStatement`

### 8.1. Cột SQL kiểu boolean/bit

Khi database/driver hỗ trợ kiểu boolean phù hợp, dùng `setBoolean` để bind một giá trị primitive:

~~~java
String sql = "UPDATE accounts SET active = ? WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBoolean(1, true);
    statement.setLong(2, accountId);
    int affected = statement.executeUpdate();
}
~~~

Ví dụ ở trên đặt trong một phương thức có `dataSource`, `accountId` và xử lý `SQLException`. Các tham số JDBC được đánh số từ **1**. Driver chịu trách nhiệm chuyển giá trị Java thành cách biểu diễn phù hợp với cột đích nếu chuyển đổi được hỗ trợ.

Để ghi giá trị nullable, không gọi `setBoolean` với một biến `Boolean` đang `null`: Java sẽ phải **auto-unbox** và gây `NullPointerException`. Thay vào đó:

~~~java
import java.sql.Types;

Boolean newStatus = null; // Ví dụ chưa biết trạng thái.

if (newStatus == null) {
    statement.setNull(1, Types.BOOLEAN);
} else {
    statement.setBoolean(1, newStatus);
}
~~~

`setNull(index, sqlType)` yêu cầu SQL type của parameter. Với cột thực sự được driver báo là `BIT` thay vì `BOOLEAN`, hoặc database dùng kiểu riêng, có thể cần `Types.BIT` hay cơ chế bind tương thích với driver. Khi SQL null type không thống nhất, hãy kiểm tra schema và tài liệu driver; không giả định `Types.BOOLEAN` hoạt động với mọi cột số/ký tự.

Có thể gặp các cách viết như `setObject(index, nullableBoolean, Types.BOOLEAN)` hoặc typed overload của `setObject`. Những cách đó phải được đánh giá theo khả năng driver, đặc biệt khi giá trị `null` và kiểu SQL đích không rõ ràng. `setNull` và `setBoolean` theo từng nhánh giúp mục đích hiển thị rõ hơn.

### 8.2. Cột số và cột chuỗi legacy

Với cột số nguyên quy ước 0/1:

~~~java
if (flag == null) {
    statement.setNull(1, java.sql.Types.INTEGER);
} else {
    statement.setInt(1, flag ? 1 : 0);
}
~~~

Với cột `CHAR(1)` lưu `Y/N`:

~~~java
if (flag == null) {
    statement.setNull(1, java.sql.Types.CHAR);
} else {
    statement.setString(1, flag ? "Y" : "N");
}
~~~

Ở hai ví dụ, `flag` là `Boolean` nullable đã có trong ngữ cảnh; `statement` là `PreparedStatement` hợp lệ. Dùng `Types.SMALLINT`, `Types.TINYINT`, `Types.NUMERIC` hoặc `Types.VARCHAR` khi đó mới là kiểu cột thực tế. Không đặt `Types.INTEGER` cho mọi số cờ mà bỏ qua schema và loại tham số.

**Tại sao nên bind giá trị thay vì ghép SQL?** `PreparedStatement` tách dữ liệu khỏi cú pháp câu lệnh, giúp xử lý `NULL` và các kiểu cột đúng hơn, đồng thời hạn chế SQL injection.

### 8.3. Một ví dụ update đầy đủ với nullable boolean

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class AccountStatusWriter {
    private final DataSource dataSource;

    public AccountStatusWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean updateActive(long accountId, Boolean active)
            throws SQLException {
        String sql = "UPDATE accounts SET active = ? WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            if (active == null) {
                statement.setNull(1, Types.BOOLEAN);
            } else {
                statement.setBoolean(1, active);
            }
            statement.setLong(2, accountId);

            return statement.executeUpdate() == 1;
        }
    }
}
~~~

Ví dụ giả định cột `accounts.active` có SQL type `BOOLEAN`, cho phép `NULL`, driver hỗ trợ bind tương ứng và `id` là khóa chính. Trả về `false` từ phương thức này có nghĩa **không có đúng một hàng được cập nhật**, khác với việc lưu boolean `false` trong cột. Đây là hai loại giá trị cần phân biệt.

## 9. Metadata: xác minh driver đang nhìn cột như thế nào

Khi kết nối với schema lạ, `ResultSetMetaData` giúp xem JDBC driver báo kiểu cột ra sao:

~~~java
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

ResultSetMetaData meta = rs.getMetaData();
int column = rs.findColumn("active");

int jdbcType = meta.getColumnType(column);
String databaseType = meta.getColumnTypeName(column);
String javaClass = meta.getColumnClassName(column);

System.out.println("JDBC type code: " + jdbcType);
System.out.println("Database type: " + databaseType);
System.out.println("Java class for getObject: " + javaClass);
~~~

Ví dụ nằm trong ngữ cảnh có `ResultSet rs` đang mở và khai báo `SQLException`. `getColumnType` trả mã trong `java.sql.Types`, `getColumnTypeName` trả tên kiểu do database/driver báo, `getColumnClassName` mô tả kiểu Java thường được tạo khi gọi `getObject` theo khả năng triển khai.

Metadata là **tín hiệu kỹ thuật về driver**, không thay thế hợp đồng dữ liệu nghiệp vụ. Nếu cột `TINYINT(1)` báo lớp `Boolean`, điều đó vẫn không chứng minh mọi giá trị của cột là cờ 0/1 hợp lệ. Ngược lại, nếu cột `BIT` báo kiểu đặc biệt, cần xác minh getter/binder phù hợp và dữ liệu thật.

Khi cần thông tin từ schema ngay cả khi không có hàng, `DatabaseMetaData.getColumns(...)` có thể cung cấp metadata cột theo khả năng JDBC driver và quyền truy cập của tài khoản. Việc tìm schema/catalog, chuẩn hóa chữ hoa/thường của tên bảng cũng tùy database.

## 10. Thiết kế mã portable qua nhiều JDBC driver

Không có lời gọi getter duy nhất bảo đảm đúng mọi quy ước lưu trữ boolean. Mã dễ kiểm soát thường đặt **quy tắc ánh xạ tại tầng repository hoặc adapter** thay vì lan truyền khác biệt driver khắp mã nghiệp vụ.

~~~mermaid
flowchart TD
    DB[("Database: BOOLEAN / BIT / 0-1 / Y-N")] --> JDBC["JDBC driver<br/>Connection + ResultSet"]
    JDBC --> M{"Kiểu SQL và quy ước schema?"}
    M -->|"BOOLEAN/BIT được hỗ trợ"| B["getBoolean + wasNull<br/>hoặc getObject(Boolean.class) đã xác minh"]
    M -->|"Số nguyên 0/1"| N["getInt + wasNull<br/>kiểm tra chỉ 0 hoặc 1"]
    M -->|"CHAR Y/N"| S["getString<br/>kiểm tra chỉ Y hoặc N"]
    B --> D["Boolean / enum của miền nghiệp vụ"]
    N --> D
    S --> D
~~~

Chọn cách tiếp cận:

| Câu hỏi | Hướng xử lý |
|---|---|
| Cột có thể SQL `NULL` không? | Dùng `Boolean` hoặc enum có trạng thái thiếu dữ liệu; bảo toàn `NULL` khi cần |
| Cột có kiểu BOOLEAN/BIT thực sự không? | Ưu tiên `getBoolean` + `wasNull` và `setBoolean`/`setNull` nếu driver hỗ trợ |
| Cột là số 0/1? | Dùng getter số, kiểm tra chính xác miền giá trị, bind số phù hợp |
| Cột là Y/N? | Dùng getter chuỗi, chỉ chấp nhận mã đã định, bind chuỗi |
| Chuyển database hoặc nâng driver? | Kiểm tra metadata, đọc tài liệu phiên bản tương ứng và chạy thử hành vi thực tế |
| Có thể thay đổi schema? | Chọn kiểu/ràng buộc phản ánh đúng miền nghiệp vụ, không chỉ dựa vào chuyển đổi của driver |
| `NULL` có nghĩa nghiệp vụ rõ không? | Nếu chưa có sự lựa chọn, giữ trạng thái thứ ba; nếu không hợp lệ, dùng `NOT NULL` và kiểm tra đầu vào |

### Những kiểm tra cần có khi tích hợp driver

Trong môi trường test với **driver và database thực tế**, cần xác minh:

1. Đọc được **true**, **false** và **NULL** theo quy tắc đã chọn.
2. Ghi cả ba trạng thái rồi đọc lại đúng ý nghĩa; kiểm tra riêng các cột có `NOT NULL`.
3. Mã hóa legacy 0/1, Y/N không chấp nhận giá trị ngoài miền một cách âm thầm.
4. `getObject(..., Boolean.class)` (nếu dùng) được driver hỗ trợ như mong đợi.
5. Metadata và hành vi chuyển đổi không thay đổi ngoài dự kiến khi nâng phiên bản driver hoặc thay cấu hình.
6. Truy vấn `WHERE` với `TRUE`, `FALSE`, `IS NULL` có đúng tập bản ghi mà nghiệp vụ cần.

Đây là những điểm nên được xác minh bằng kiểm thử tích hợp thực sự với database. Kiểm tra kiểu Java của một mock `ResultSet` không đủ chứng minh cách driver chuyển giá trị SQL trong môi trường vận hành.

## 11. Các lỗi dễ gây sai dữ liệu

### 11.1. Đọc `getBoolean` rồi quên `wasNull`

~~~java
boolean agreed = rs.getBoolean("consent"); // NULL cũng đọc ra false.
~~~

Nếu “chưa hỏi” khác “đã từ chối”, đoạn mã này đã **làm mất thông tin**. Đọc `wasNull()` ngay sau đó hoặc dùng typed getter đã được driver xác minh.

### 11.2. Auto-unboxing `Boolean` nullable

~~~java
Boolean active = null;
statement.setBoolean(1, active); // NullPointerException khi auto-unbox.
~~~

Phải dùng nhánh `setNull(...)` riêng khi giá trị là `null`.

### 11.3. Coi mọi số khác 0 là true

~~~java
boolean active = rs.getInt("flag") != 0;
~~~

Nếu schema chỉ định 0/1, giá trị 2 hoặc -1 có thể là dữ liệu lỗi. Đoạn mã trên còn làm mất SQL `NULL` vì `getInt` trả 0 cho `NULL`. Hãy kiểm tra `wasNull` và từ chối giá trị ngoài miền.

### 11.4. Gọi `getBoolean` trên cột Y/N mà không xác minh driver

Kết quả chuyển đổi ký tự không nhất thiết giống nhau giữa JDBC driver; mapper tường minh `Y → true`, `N → false`, `NULL → null` giúp hợp đồng rõ ràng và dự đoán được.

### 11.5. Mặc định SQL `BOOLEAN` giống nhau ở mọi database

Trong MySQL, `BOOLEAN` là alias của `TINYINT(1)`. SQL Server thường dùng `BIT`; một số Oracle bản cũ không hỗ trợ SQL `BOOLEAN` như các phiên bản mới. Cú pháp SQL literal, metadata, ràng buộc và cách bind phải được xác minh với đúng database.

### 11.6. Nhầm “không có bản ghi” với “giá trị boolean là NULL”

~~~java
if (!rs.next()) {
    // Không tồn tại bản ghi.
} else {
    // Có bản ghi, nhưng cột active có thể là NULL.
}
~~~

Không sử dụng một `Boolean` nullable duy nhất để biểu diễn đồng thời cả **không tìm thấy hàng**, **chưa có trạng thái** và **true/false** nếu chúng có ý nghĩa nghiệp vụ khác nhau.

### 11.7. Dùng `Boolean.TRUE.equals` rồi vô tình gộp FALSE và NULL

~~~java
if (Boolean.TRUE.equals(consent)) {
    // Chỉ khi đã đồng ý.
}
~~~

Câu lệnh là an toàn với `null`, nhưng nhánh còn lại bao gồm cả `false` và `null`. Nếu cần phân biệt “đã từ chối” với “chưa được hỏi”, hãy rẽ nhánh riêng hoặc dùng enum `AGREED / REJECTED / UNKNOWN`.

## 12. Tình huống nghiệp vụ minh họa

Một hệ thống tiếp thị có trường `newsletter_consent` với ba trạng thái:

- `TRUE`: được phép gửi newsletter theo sự đồng ý hợp lệ.
- `FALSE`: người dùng từ chối.
- `NULL`: chưa có phản hồi hoặc dữ liệu chưa được xác nhận.

Thiết kế sai là đọc `NULL` thành `false` rồi dùng chung một trạng thái cho cả “từ chối” và “chưa xin ý kiến”. Điều đó có thể che mất tình trạng dữ liệu cần xử lý và làm báo cáo sai.

Ở phía Java, có thể dùng `Boolean` nullable khi tầng dữ liệu cần giữ đúng ba giá trị. Ở tầng nghiệp vụ, enum thể hiện rõ hơn:

~~~java
enum ConsentState {
    AGREED, REJECTED, UNKNOWN
}

static ConsentState toConsentState(Boolean consent) {
    if (consent == null) {
        return ConsentState.UNKNOWN;
    }
    return consent ? ConsentState.AGREED : ConsentState.REJECTED;
}
~~~

Khi cần soạn truy vấn cho kết quả chưa có câu trả lời, hãy viết điều kiện `IS NULL` trên cột lưu trạng thái; đừng suy luận rằng `WHERE NOT consent` sẽ lấy cả những hàng SQL `NULL`.

Ở cấp thiết kế, cũng phải xác định `NULL` là “chưa biết” hay “không áp dụng”, vì hai ý nghĩa này có thể cần **hai trạng thái miền nghiệp vụ riêng** thay vì gộp vào một giá trị SQL.

## 13. Checklist áp dụng trong dự án

- [ ] Tôi biết **kiểu SQL thực tế** của cột: `BOOLEAN`, `BIT`, số hay ký tự.
- [ ] Tôi biết **miền giá trị được phép**: chỉ true/false, 0/1, Y/N hay có SQL `NULL`.
- [ ] Tôi phân biệt rõ `boolean` nguyên thủy và `Boolean` nullable trong Java.
- [ ] Khi dùng `getBoolean` trên cột nullable, tôi gọi `wasNull()` **ngay sau getter**.
- [ ] Với cột 0/1 hoặc Y/N, tôi ánh xạ bằng quy ước rõ ràng và từ chối dữ liệu ngoài miền.
- [ ] Khi bind giá trị nullable, tôi dùng `setNull` với loại SQL thích hợp, tránh auto-unboxing `null`.
- [ ] Tôi không dựa vào `getObject` hay metadata để suy ra nghiệp vụ mà chưa kiểm tra driver thực tế.
- [ ] Các điều kiện SQL về true/false/NULL thể hiện đúng yêu cầu của người dùng.
- [ ] Tôi đã kiểm tra hành vi khi nâng cấp driver, đổi database hoặc thay schema.

## 14. Câu hỏi tự kiểm tra

1. Nếu SQL `active = NULL`, `rs.getBoolean("active")` trả về gì? Cần gọi phương thức nào ngay sau đó để biết giá trị gốc là `NULL`?
2. Khi nào nên dùng `Boolean` thay vì `boolean` trong Java?
3. Vì sao `rs.getInt("flag") != 0` không an toàn với cột số có thể chứa `NULL` hoặc giá trị sai như 2?
4. Tại sao không thể mặc định `getBoolean("flag")` hiểu ký tự `Y/N` giống nhau ở mọi driver?
5. Với giá trị `Boolean status = null`, vì sao `statement.setBoolean(1, status)` có thể lỗi ngay ở Java?
6. MySQL diễn giải kiểu `BOOLEAN` như thế nào, và vì sao điều đó ảnh hưởng đến việc kiểm tra miền giá trị?
7. `getObject("active", Boolean.class)` có thể hữu ích thế nào và cần xác minh điều gì trước khi dùng?
8. `WHERE active = FALSE` có lấy các hàng `active IS NULL` không? Nếu nghiệp vụ cần cả hai nhóm, phải thiết kế điều kiện ra sao?
9. Vì sao việc JDBC driver báo `BIT` hoặc `BOOLEAN` qua metadata chưa đủ để quyết định trạng thái nghiệp vụ?

**Điểm cần nhớ:** một cờ trong database có thể được lưu thành **BOOLEAN, BIT, 0/1 hoặc Y/N**. Trước hết phải đọc đúng hợp đồng schema và khả năng của JDBC driver. Với `getBoolean`, **SQL `NULL` cũng tạo kết quả primitive `false`**, nên cần `wasNull()` ngay sau getter để bảo toàn trạng thái thứ ba. Khi dữ liệu là số/ký tự legacy, ánh xạ và kiểm tra miền giá trị tường minh giúp ngăn sai lệch dữ liệu giữa các hệ quản trị.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `ResultSet` (`getBoolean`, `wasNull`, `getObject`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 21 — `PreparedStatement` (`setBoolean`, `setNull`, `setObject`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)
- [Java SE 21 — `Types` (`BOOLEAN`, `BIT`, các mã SQL type)](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Types.html)
- [Java SE 21 — `ResultSetMetaData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSetMetaData.html)
- [PostgreSQL — Boolean type](https://www.postgresql.org/docs/current/datatype-boolean.html)
- [MySQL 8.4 — Numeric type syntax, BOOL/BOOLEAN](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-syntax.html)
- [Microsoft SQL Server — bit (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/data-types/bit-transact-sql)
- [SQLite — Datatypes in SQLite](https://www.sqlite.org/datatype3.html)
