# Vai trò của Types, JDBCType và SQLType

Trong **JDBC (Java Database Connectivity)**, Java trao đổi dữ liệu với cơ sở dữ liệu quan hệ bằng các giá trị có kiểu: số nguyên, chuỗi, số thập phân, ngày, giờ, dữ liệu nhị phân và nhiều kiểu khác. Khi sử dụng `PreparedStatement` hoặc đọc `ResultSet`, driver cần biết **kiểu SQL đích** để chuyển đổi giá trị Java cho đúng.

JDBC cung cấp ba tên dễ bị nhầm lẫn:

- **`java.sql.Types`**: lớp tập hợp các **hằng số `int`** đại diện cho mã kiểu SQL/JDBC.
- **`java.sql.JDBCType`**: một **`enum`** đại diện cho các kiểu JDBC chuẩn, có tên dễ đọc và có thể chuyển về mã kiểu `int`.
- **`java.sql.SQLType`**: một **interface** biểu diễn một kiểu SQL; `JDBCType` triển khai interface này, và nhà cung cấp driver cũng có thể cung cấp những kiểu riêng.

Bài học thuộc chương **Kiểu dữ liệu và NULL**. Mục tiêu là hiểu lúc nào dùng `Types.INTEGER`, `JDBCType.INTEGER` hay biến kiểu `SQLType`; dùng đúng overload của `PreparedStatement`; xử lý SQL `NULL`; và kiểm tra kiểu cột qua metadata mà không giả định mọi driver đều giống nhau.

## 1. Mô hình ba thành phần

~~~text
                   JDBC API
                       │
          ┌────────────┴──────────────┐
          │                           │
   java.sql.Types             java.sql.SQLType
   lớp chứa hằng số int        interface mô tả kiểu SQL
          │                           ▲
          │                           │ implements
          │                    java.sql.JDBCType
          │                    enum kiểu JDBC chuẩn
          │                           │
          └───────────┬───────────────┘
                      ▼
            Driver JDBC hiểu kiểu
                      │
                      ▼
                Giá trị trong DB
~~~

Ví dụ ba cách biểu diễn kiểu số thập phân:

~~~java
// Cách 1: int theo API JDBC truyền thống
int legacyCode = java.sql.Types.DECIMAL;

// Cách 2: enum có tên theo JDBC 4.2
java.sql.JDBCType standardType = java.sql.JDBCType.DECIMAL;

// Cách 3: tham chiếu qua interface chung
java.sql.SQLType sqlType = java.sql.JDBCType.DECIMAL;

// Chuyển enum tiêu chuẩn về mã kiểu int
Integer vendorCode = standardType.getVendorTypeNumber();
System.out.println(legacyCode == vendorCode); // true
~~~

Ở đoạn code này, `vendorCode` thực tế là mã kiểu chuẩn của `JDBCType.DECIMAL`; tên phương thức là `getVendorTypeNumber()` vì interface `SQLType` còn phục vụ kiểu do nhà cung cấp định nghĩa. **Giá trị mà biến lưu trữ thuộc kiểu Java nào** và **kiểu SQL mà câu lệnh kỳ vọng** là hai thứ cần phân biệt.

## 2. `java.sql.Types`: mã kiểu SQL dạng số nguyên

`Types` là lớp chứa các hằng số tĩnh như `Types.INTEGER`, `Types.VARCHAR` và `Types.TIMESTAMP`. Mỗi hằng số có giá trị `int` theo JDBC:

~~~java
import java.sql.Types;

int integerCode = Types.INTEGER;
int varcharCode = Types.VARCHAR;
int decimalCode = Types.DECIMAL;
int dateCode = Types.DATE;
~~~

Các phương thức có từ các phiên bản JDBC cũ thường nhận mã kiểu `int`:

~~~java
// Kiểu SQL cho giá trị NULL
statement.setNull(1, Types.VARCHAR);

// Kiểu SQL được yêu cầu khi chuyển đổi giá trị
statement.setObject(2, new java.math.BigDecimal("19.95"),
                    Types.DECIMAL);
~~~

*Trong ví dụ, `statement` là một `PreparedStatement` đã được tạo và các chỉ số `1`, `2` tương ứng với vị trí dấu `?` trong SQL.*

`Types` hữu ích khi làm việc với:

- `PreparedStatement.setNull(int parameterIndex, int sqlType)`;
- `PreparedStatement.setObject(int parameterIndex, Object value, int targetSqlType)`;
- `ResultSetMetaData.getColumnType(int column)` và `ParameterMetaData.getParameterType(int parameter)`;
- các API driver, thư viện và code cũ vốn sử dụng mã kiểu số nguyên.

### Những mã kiểu hay gặp

| Hằng số `Types` | Ý nghĩa SQL thường gặp | Kiểu Java thường dùng |
| --- | --- | --- |
| `INTEGER` | Số nguyên 32-bit | `Integer` / `int` |
| `BIGINT` | Số nguyên có miền lớn | `Long` / `long` |
| `DECIMAL`, `NUMERIC` | Số thập phân chính xác | `BigDecimal` |
| `VARCHAR`, `CHAR` | Ký tự, chuỗi | `String` |
| `BOOLEAN`, `BIT` | Giá trị logic/bit | `Boolean` / `boolean` |
| `DATE` | Ngày | `LocalDate` hoặc `java.sql.Date` |
| `TIME` | Giờ | `LocalTime` hoặc `java.sql.Time` |
| `TIMESTAMP` | Ngày giờ, không tự biểu diễn múi giờ | `LocalDateTime` hoặc `java.sql.Timestamp` |
| `TIMESTAMP_WITH_TIMEZONE` | Ngày giờ có thông tin múi giờ/offset theo kiểu SQL tương ứng | `OffsetDateTime` khi driver hỗ trợ |
| `VARBINARY`, `BINARY` | Dữ liệu nhị phân | `byte[]` |
| `BLOB`, `CLOB` | Đối tượng nhị phân/ký tự lớn | `Blob`, `Clob` hoặc stream theo API phù hợp |
| `ARRAY` | Mảng SQL | `java.sql.Array` |
| `OTHER` | Kiểu ngoài các nhóm chuẩn, thường phụ thuộc DB | Phụ thuộc driver |

Bảng trên là hướng dẫn ánh xạ thường gặp, **không phải cam kết mọi driver chấp nhận mọi cặp Java/SQL**. Chẳng hạn DB có thể không hỗ trợ kiểu `BOOLEAN` độc lập hoặc ánh xạ `TIMESTAMP_WITH_TIMEZONE` theo quy tắc riêng. Khi cần độ chính xác, tra tài liệu driver và schema thật.

Các mã kiểu `Types` là **mã nhận diện**, không phải độ dài tính bằng byte, số chữ số, số bit hay thứ tự ưu tiên. Không so sánh chúng theo `>` hoặc `<` để kết luận một kiểu “rộng hơn” kiểu khác.

## 3. `java.sql.JDBCType`: enum cho các kiểu JDBC chuẩn

`JDBCType` là enum được bổ sung cùng các API dùng `SQLType` trong JDBC 4.2 (Java 8). Enum này tạo ra cách diễn đạt có tên, thuận tiện khi cần truyền kiểu SQL:

~~~java
import java.sql.JDBCType;
import java.sql.SQLType;

SQLType type = JDBCType.VARCHAR;

System.out.println(type.getName());             // VARCHAR
System.out.println(type.getVendorTypeNumber()); // Mã int chuẩn tương ứng
~~~

`JDBCType` **triển khai `SQLType`**, nên bạn có thể truyền `JDBCType.DECIMAL` cho phương thức nhận `SQLType`:

~~~java
statement.setObject(
        1,
        new java.math.BigDecimal("125.40"),
        JDBCType.DECIMAL
);
~~~

Đây là overload nhận `SQLType`; nếu driver hỗ trợ, nó giúp thể hiện rõ yêu cầu chuyển đổi sang kiểu SQL `DECIMAL`.

Bạn cũng có thể chuyển mã số nguyên của kiểu chuẩn sang enum:

~~~java
import java.sql.JDBCType;
import java.sql.Types;

JDBCType type = JDBCType.valueOf(Types.INTEGER);
System.out.println(type); // INTEGER
~~~

`JDBCType.valueOf(int)` chỉ tìm các giá trị có trong enum chuẩn. Nếu truyền mã không tương ứng với `JDBCType`, phương thức ném `IllegalArgumentException`; không nên dùng để ép **mọi mã riêng của DB** thành kiểu JDBC chuẩn.

### Không phải API nào cũng nhận JDBCType trực tiếp

Hai lời gọi sau minh họa sự khác biệt về chữ ký phương thức:

~~~java
// setNull truyền mã int:
statement.setNull(1, Types.INTEGER);

// setObject có overload nhận SQLType:
statement.setObject(2, Integer.valueOf(10), JDBCType.INTEGER);
~~~

Không viết `statement.setNull(1, JDBCType.INTEGER)`: `setNull` trong `PreparedStatement` nhận `int` ở vị trí kiểu SQL, không có overload chuẩn `setNull(int, SQLType)`. Nếu code đang giữ biến `SQLType`, phải xét việc lấy mã `getVendorTypeNumber()` và mức hỗ trợ của driver trước khi chuyển về API `int`.

## 4. `java.sql.SQLType`: interface chung cho kiểu SQL

`SQLType` định nghĩa ba phương thức mô tả một kiểu:

~~~java
public interface SQLType {
    String getName();
    String getVendor();
    Integer getVendorTypeNumber();
}
~~~

Ý nghĩa:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getName()` | Tên của kiểu SQL do đối tượng mô tả |
| `getVendor()` | Tên nhà cung cấp hoặc hệ thống định nghĩa kiểu |
| `getVendorTypeNumber()` | Mã số nhận diện kiểu trong phạm vi vendor; về mặt interface có thể là `null` |

Đối với kiểu chuẩn, `JDBCType` cung cấp triển khai tương ứng. Đối với một kiểu đặc thù của DB — chẳng hạn một enum do ứng dụng tạo trong database, kiểu không gian hoặc một kiểu JSON riêng — driver **có thể** cung cấp đối tượng `SQLType` riêng. Cách xử lý kiểu đó phụ thuộc driver.

Ví dụ về lập trình với interface:

~~~java
import java.sql.JDBCType;
import java.sql.SQLType;

public static void printSqlType(SQLType type) {
    System.out.println("Name: " + type.getName());
    System.out.println("Vendor: " + type.getVendor());
    System.out.println("Code: " + type.getVendorTypeNumber());
}

printSqlType(JDBCType.VARCHAR);
~~~

Phương thức này có thể nhận bất kỳ implementation `SQLType` nào, nhưng **việc truyền một đối tượng `SQLType` tới driver không bảo đảm driver sẽ hiểu kiểu đó**. Interface chỉ cung cấp hợp đồng mô tả kiểu. Với kiểu riêng, cần dùng các hướng dẫn về binding và chuyển đổi của driver hiện tại.

### Mối quan hệ giữa ba API

| Tiêu chí | `Types` | `JDBCType` | `SQLType` |
| --- | --- | --- | --- |
| Loại Java | Lớp chứa hằng số | Enum | Interface |
| Biểu diễn | `int` | `JDBCType` | Đối tượng triển khai interface |
| Kiểu chuẩn JDBC | Có | Có | Có, thông qua `JDBCType` |
| Kiểu riêng của driver | Có thể có mã do driver công bố | Enum không tự thêm hằng số mới | Có thể được driver triển khai |
| Được dùng trực tiếp bởi | API `setNull`, `setObject(..., int)` và metadata | API nhận `SQLType` | API nhận `SQLType` |
| Mục đích chính | Khả năng tương thích với API mã số | Kiểu chuẩn có tên và rõ nghĩa | Mở rộng cách mô tả kiểu |

**Điểm mấu chốt:** `Types.DECIMAL` và `JDBCType.DECIMAL` mô tả cùng một kiểu JDBC chuẩn, nhưng chúng **không cùng kiểu Java**. `SQLType` không phải enum thứ ba; đó là interface mà `JDBCType` triển khai.

## 5. Tại sao cần chỉ rõ kiểu khi bind tham số?

`PreparedStatement` cho phép truyền giá trị theo nhiều cách:

~~~java
// Driver thường suy ra kiểu từ setter:
statement.setInt(1, 42);
statement.setString(2, "Keyboard");

// Chỉ rõ mã kiểu SQL kiểu cũ:
statement.setObject(3, new java.math.BigDecimal("49.95"),
                    java.sql.Types.DECIMAL);

// Chỉ rõ SQLType kiểu mới:
statement.setObject(4, java.time.LocalDate.of(2026, 1, 15),
                    java.sql.JDBCType.DATE);
~~~

Các dạng này không phải lúc nào cũng thay thế cho nhau:

- `setInt`, `setString`, `setBigDecimal` nêu rõ kiểu giá trị Java; driver thường ánh xạ sang kiểu SQL phù hợp với cột.
- `setObject(index, value)` yêu cầu driver suy luận ánh xạ từ đối tượng Java; sự suy luận có thể không rõ khi kiểu Java khớp nhiều kiểu SQL.
- `setObject(index, value, targetSqlType)` yêu cầu driver thực hiện chuyển đổi hướng đến kiểu SQL đích. Tham số `targetSqlType` có thể là mã `int` hoặc `SQLType` tùy overload.
- `setObject(index, value, targetSqlType, scaleOrLength)` còn nhận độ chính xác/thang số hoặc độ dài theo contract của loại dữ liệu. Đây là API cần kiểm tra kỹ theo driver.

Đặt kiểu SQL đích không có nghĩa mọi phép chuyển đổi đều hợp lệ. Ví dụ chuỗi `"abc"` không thể mặc nhiên chuyển thành `INTEGER`. Driver hoặc DB có thể ném `SQLException`/`SQLDataException` khi dữ liệu không hợp lệ, tràn số hoặc không hỗ trợ chuyển đổi.

## 6. SQL NULL khác Java null và khác kiểu cột

Trong SQL, `NULL` biểu diễn **không có giá trị** hoặc **không xác định** theo ngữ nghĩa SQL. Nó **không phải** số `0`, chuỗi rỗng `""` hay giá trị Boolean `false`. Một cột kiểu `DECIMAL` có thể chứa giá trị số hoặc `NULL` tùy ràng buộc schema, nhưng cột đó vẫn có **kiểu dữ liệu DECIMAL**.

Ví dụ:

~~~sql
CREATE TABLE products (
    id           BIGINT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    price        DECIMAL(12, 2) NOT NULL,
    available_on DATE,
    description  VARCHAR(500)
);
~~~

`description` có thể `NULL`; kiểu cột vẫn là `VARCHAR(500)`. Khi dùng JDBC, giá trị Java `null` cần được bind một cách rõ nghĩa cho kiểu cột tương ứng:

~~~java
String description = null;

if (description == null) {
    statement.setNull(5, java.sql.Types.VARCHAR);
} else {
    statement.setString(5, description);
}
~~~

`Types.VARCHAR` cho driver biết kiểu SQL dự kiến của marker tại vị trí `5`. Với các kiểu phức tạp như user-defined type, một số driver yêu cầu overload có `typeName`:

~~~java
// Chỉ dùng khi driver/DB yêu cầu tên kiểu SQL cụ thể:
statement.setNull(parameterIndex,
                  java.sql.Types.STRUCT,
                  sqlTypeName);
~~~

Trong ví dụ này `parameterIndex` và `sqlTypeName` là các giá trị được xác định từ schema/driver. Cú pháp tên kiểu và việc hỗ trợ `STRUCT` thay đổi theo hệ quản trị.

### Có nên dùng `Types.NULL` cho mọi giá trị null?

`Types.NULL` là **một mã kiểu JDBC đặc biệt**, nhưng không phải lựa chọn thay thế cho kiểu SQL thực tế của cột khi bạn đã biết schema. Cách ổn định hơn là gọi `setNull(index, Types.VARCHAR)` cho cột `VARCHAR`, `setNull(index, Types.INTEGER)` cho cột `INTEGER`, `setNull(index, Types.DATE)` cho cột `DATE`, v.v.

Nhiều driver có thể tự suy luận kiểu của marker trong `setObject(index, null)`, nhưng **không nên phụ thuộc vào khả năng đó trên mọi DB/driver**, đặc biệt khi câu SQL có biểu thức chưa cho phép suy ra kiểu như `? IS NULL`. Nếu biết kiểu đích, hãy truyền nó tường minh.

### So sánh SQL NULL bằng cú pháp nào?

~~~sql
-- Đúng: tìm sản phẩm chưa có mô tả
SELECT id FROM products WHERE description IS NULL;

-- Sai về mặt ngữ nghĩa: kết quả của "= NULL" không phải TRUE
SELECT id FROM products WHERE description = NULL;
~~~

Khi muốn cho phép người dùng chọn giữa “không lọc theo mô tả”, “chỉ tìm mô tả NULL” và “tìm mô tả bằng một chuỗi”, chương trình phải có ba chế độ rõ ràng. Một giá trị Java `null` đơn lẻ không đủ để mô tả cả ba ý định.

## 7. Ví dụ hoàn chỉnh: chèn dữ liệu có NULL và kiểu ngày

Đoạn mã sau minh họa việc kết hợp `Types`, `JDBCType` và các setter thường gặp. Ví dụ dùng Java 17 trở lên; giả sử `DataSource`, bảng `products` và driver JDBC đã được cấu hình.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.JDBCType;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDate;
import javax.sql.DataSource;

public final class ProductWriter {

    private final DataSource dataSource;

    public ProductWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int addProduct(
            long id,
            String name,
            BigDecimal price,
            LocalDate availableOn,
            String description) throws SQLException {

        String sql = """
                INSERT INTO products
                    (id, name, price, available_on, description)
                VALUES (?, ?, ?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            statement.setString(2, name);

            // JDBC 4.2: SQLType thông qua enum JDBCType
            statement.setObject(3, price, JDBCType.DECIMAL);

            if (availableOn == null) {
                statement.setNull(4, Types.DATE);
            } else {
                // Mapping java.time được hỗ trợ bởi JDBC 4.2;
                // kiểm tra phiên bản driver trong thực tế.
                statement.setObject(4, availableOn, JDBCType.DATE);
            }

            if (description == null) {
                statement.setNull(5, Types.VARCHAR);
            } else {
                statement.setString(5, description);
            }

            return statement.executeUpdate();
        }
    }
}
~~~

Giải thích theo từng tham số:

| Marker | Cột SQL | Dữ liệu Java | Cách bind |
| --- | --- | --- | --- |
| `1` | `id BIGINT` | `long` | `setLong(1, id)` |
| `2` | `name VARCHAR` | `String` | `setString(2, name)` |
| `3` | `price DECIMAL` | `BigDecimal` | `setObject(3, price, JDBCType.DECIMAL)` |
| `4` | `available_on DATE` | `LocalDate` hoặc `null` | `setObject(..., JDBCType.DATE)` hoặc `setNull(..., Types.DATE)` |
| `5` | `description VARCHAR` | `String` hoặc `null` | `setString(...)` hoặc `setNull(..., Types.VARCHAR)` |

Ở mức JDBC 4.2, `LocalDate` tương ứng kiểu SQL `DATE`; tuy nhiên, môi trường chỉ hỗ trợ driver cũ có thể cần chuyển bằng `java.sql.Date.valueOf(availableOn)` và gọi `setDate(...)`. Với `BigDecimal`, `setBigDecimal(3, price)` cũng là lựa chọn rõ ràng và thường di động.

`executeUpdate()` trả số dòng được driver báo là chèn/tác động; nó không trả `ResultSet`. Giá trị trả về không thay thế cho việc quản lý `commit()/rollback()` khi các thao tác nằm trong giao dịch tường minh.

**Giá trị `price` là bắt buộc theo schema ví dụ**. Trong code production, hãy kiểm tra các tham số bắt buộc từ tầng ứng dụng, ví dụ không cho phép `price == null` và không cho phép tên rỗng, thay vì chỉ chờ DB từ chối.

## 8. Đọc NULL từ ResultSet: tránh biến NULL thành 0 hoặc false

Khi gọi getter trả kiểu nguyên thủy, JDBC không thể trả Java `null`. Ví dụ:

~~~java
int stock = rows.getInt("stock");
boolean active = rows.getBoolean("active");
~~~

Nếu giá trị SQL ở cột là `NULL`, `getInt(...)` trả `0` và `getBoolean(...)` trả `false`. Muốn phân biệt chúng với giá trị thật, dùng `ResultSet.wasNull()` **ngay sau getter tương ứng**:

~~~java
int stockValue = rows.getInt("stock");
Integer stock = rows.wasNull() ? null : stockValue;

boolean activeValue = rows.getBoolean("active");
Boolean active = rows.wasNull() ? null : activeValue;
~~~

`wasNull()` kiểm tra **giá trị cột vừa đọc**. Vì vậy phải gọi ngay sau getter mà bạn muốn kiểm tra, không chen getter khác vào giữa.

Một cách khác là gọi getter trả object:

~~~java
String description = rows.getString("description");
BigDecimal price = rows.getBigDecimal("price");

// Với những getter này, SQL NULL thông thường trở thành Java null.
~~~

Với Java time và JDBC 4.2, nhiều driver hỗ trợ:

~~~java
java.time.LocalDate availableOn =
        rows.getObject("available_on", java.time.LocalDate.class);
~~~

Nếu cột là SQL `NULL`, getter đối tượng có thể trả Java `null`. Mức hỗ trợ `getObject(column, Class<T>)` và mapping `java.time` cần kiểm tra trên phiên bản driver thực tế. Với driver không hỗ trợ, dùng `getDate(...)` rồi chuyển thành `LocalDate` sau khi kiểm tra null.

## 9. Đọc kiểu SQL thực tế qua metadata

Khi không chắc kiểu cột được DB/driver báo cáo là gì, `ResultSetMetaData` cung cấp các thông tin hữu ích:

~~~java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.JDBCType;
import java.sql.SQLException;

public static void describeColumns(ResultSet rows)
        throws SQLException {

    ResultSetMetaData meta = rows.getMetaData();

    for (int column = 1; column <= meta.getColumnCount(); column++) {
        int typeCode = meta.getColumnType(column);
        String typeName = meta.getColumnTypeName(column);
        String label = meta.getColumnLabel(column);

        System.out.println(
                label + " -> code=" + typeCode + ", name=" + typeName
        );

        try {
            // Chỉ chuyển đổi nếu đây là mã có trong enum chuẩn.
            JDBCType type = JDBCType.valueOf(typeCode);
            System.out.println("JDBC standard type: " + type);
        } catch (IllegalArgumentException unknown) {
            System.out.println("Driver-specific/unknown JDBC code");
        }
    }
}
~~~

Phân biệt:

- `getColumnType(int)` trả **mã `int`** theo hệ mã `java.sql.Types`, hoặc mã khác được driver công bố khi phù hợp.
- `getColumnTypeName(int)` trả **tên kiểu do DB/driver báo cáo**, ví dụ tên SQL đặc trưng của nhà cung cấp.
- `getColumnLabel(int)` là nhãn cột trong kết quả, có thể là alias từ `SELECT ... AS ...`.
- `getColumnClassName(int)`, nếu cần, cho biết tên lớp Java mà driver dự kiến dùng cho `getObject()`.

**Không nhầm kiểu cột trong metadata với kiểu của giá trị hiện tại.** Cột `DECIMAL` có thể chứa `NULL`; `getColumnType` vẫn mô tả `DECIMAL`. Đồng thời, metadata của biểu thức SQL như `CAST(...)`, `COUNT(*)` hoặc phép tính có thể phản ánh kiểu **biểu thức trả về**, khác với kiểu của cột gốc.

### Metadata tham số có giới hạn gì?

`ParameterMetaData` có `getParameterType(int)` trả mã `int`, nhưng không phải driver nào cũng suy ra được đầy đủ kiểu của mọi marker `?` trước khi thực thi. Trong câu lệnh phức tạp, một marker chưa có ngữ cảnh rõ ràng có thể bị driver báo loại chung hoặc không hỗ trợ metadata.

Vì thế, **không dùng metadata làm cách duy nhất để suy ra kiểu của tham số** nếu đã biết schema và ràng buộc nghiệp vụ. Setter có kiểu rõ ràng vẫn là cách truyền dữ liệu dễ kiểm chứng hơn.

## 10. Kiểu dữ liệu của vendor và mã Types.OTHER

Các DB cung cấp kiểu mở rộng như JSON/JSONB, UUID, enum, kiểu không gian hoặc kiểu người dùng tự định nghĩa. JDBC cung cấp `Types.OTHER` cho trường hợp kiểu không ánh xạ trực tiếp vào một kiểu chuẩn thích hợp; driver có thể ánh xạ các kiểu mở rộng khác nhau theo cách riêng.

Ví dụ một driver có thể báo:

~~~text
getColumnType(...)     -> Types.OTHER
getColumnTypeName(...) -> tên kiểu riêng của database
~~~

Cách bind giá trị cho kiểu đó phụ thuộc driver, ví dụ có thể cần:

- Một đối tượng Java do driver cung cấp;
- `setObject(..., Types.OTHER)` hoặc một đối tượng `SQLType` riêng;
- Một cú pháp `CAST(? AS ...)` với tên kiểu từ code cấu hình tin cậy;
- Một API vendor-specific hoặc type handler của framework.

**Không giả định `setObject(index, value, JDBCType.OTHER)` là cách chung để ghi mọi kiểu JSON/UUID/enum trên mọi DB.** `OTHER` chỉ là nhãn chung, còn định dạng dữ liệu, kiểu SQL đích và phép chuyển đổi do driver/DB quyết định. Nếu sử dụng `SQLType` do driver cung cấp, phải bảo đảm driver đó thực sự nhận biết và hỗ trợ đối tượng ấy.

Với cột SQL có tên kiểu do người dùng định nghĩa, không chèn tên kiểu từ input không tin cậy vào SQL qua phép nối chuỗi. Tên kiểu là **cấu trúc SQL**, không phải một giá trị có thể thay bằng marker `?`; hãy chọn từ danh sách hợp lệ do ứng dụng định nghĩa.

## 11. Lưu ý về độ chính xác, ngày giờ và chuyển kiểu

Chọn đúng mã kiểu là điều kiện cần nhưng chưa đủ để bảo vệ dữ liệu.

| Trường hợp | Rủi ro | Cách làm |
| --- | --- | --- |
| Lưu tiền tệ bằng `double` rồi bind vào `DECIMAL` | Sai số nhị phân có thể xuất hiện trước khi ghi DB | Dùng `BigDecimal` và xác định scale/rounding rõ ràng |
| Lưu số Java vượt miền kiểu SQL | Overflow hoặc ngoại lệ chuyển đổi | Kiểm tra giới hạn của cột và kiểu setter |
| Lưu `LocalDateTime` vào `TIMESTAMP` | Không tự chứa thông tin múi giờ | Xác định rõ timezone/offset theo thiết kế nghiệp vụ |
| Lưu `OffsetDateTime` | Hỗ trợ/mapping phụ thuộc driver và kiểu DB | Chọn kiểu SQL phù hợp, kiểm tra JDBC 4.2 và hành vi driver |
| Bind `null` bằng kiểu SQL không tương thích | DB không suy ra hoặc từ chối kiểu | Dùng `setNull` với mã kiểu phù hợp schema |
| Dùng `getInt` đọc cột nullable | SQL NULL dễ bị hiểu thành 0 | Dùng `wasNull()` hoặc API object phù hợp |
| Dùng `getString` cho mọi kiểu | Có thể mất ngữ nghĩa kiểu, phụ thuộc format của driver | Chọn getter có kiểu tương ứng |
| Dùng `Types.OTHER` cho mọi kiểu không rõ | Driver có thể không chuyển đổi đúng | Xác định schema, kiểm tra metadata và tài liệu driver |

Đặc biệt với `DECIMAL(p,s)`, `p` là độ chính xác tổng số chữ số và `s` là số chữ số thập phân theo quy tắc kiểu SQL. `JDBCType.DECIMAL` **không tự cung cấp** giá trị `p` và `s` của cột; thông tin đó thuộc schema/metadata hoặc yêu cầu nghiệp vụ.

## 12. Khi nào chọn Types, JDBCType hay SQLType?

Có thể chọn dựa trên chữ ký API và tính tương thích:

1. **API yêu cầu `int`**: dùng `Types.X`. Ví dụ `setNull(index, Types.VARCHAR)`, hoặc khi so sánh với `ResultSetMetaData.getColumnType(...)`.
2. **API nhận `SQLType` và dùng kiểu chuẩn**: dùng `JDBCType.X`. Ví dụ `setObject(index, amount, JDBCType.DECIMAL)`.
3. **Muốn viết hàm nhận nhiều kiểu từ driver**: nhận tham số `SQLType`, nhưng cần kiểm tra driver có hỗ trợ kiểu và mã vendor đó hay không.
4. **Chỉ cần bind Java value thông thường**: ưu tiên các setter có kiểu rõ ràng như `setLong`, `setString`, `setBigDecimal` hoặc `setDate`; không phải lúc nào cũng cần gọi `setObject`.
5. **Đang có SQL NULL**: dùng `setNull` với mã kiểu thật của cột; đừng coi `Types.NULL` hoặc Java `null` là câu trả lời duy nhất cho mọi kiểu dữ liệu.

Ví dụ chọn một cách nhất quán:

~~~java
// Code cũ và setNull:
statement.setNull(1, java.sql.Types.DATE);

// API JDBC 4.2 nhận SQLType:
statement.setObject(2, java.time.LocalDate.of(2026, 11, 16),
                    java.sql.JDBCType.DATE);

// Setter kiểu rõ ràng, không cần SQLType:
statement.setBigDecimal(3, new java.math.BigDecimal("15.75"));
~~~

Nếu một driver không hỗ trợ overload `setObject(..., SQLType)`, có thể cần dùng overload `int` hoặc setter chuyên biệt tương ứng. Việc chọn API phải dựa trên **phiên bản driver và cơ sở dữ liệu đang triển khai**, không chỉ dựa trên phiên bản JDK.

## 13. Các lỗi thường gặp

| Nhầm lẫn | Điều chỉnh |
| --- | --- |
| “`Types` là enum.” | `Types` là lớp chứa hằng `int`; `JDBCType` mới là enum. |
| “`SQLType` là một hằng số số nguyên.” | `SQLType` là interface, một object có `getName()`, `getVendor()` và `getVendorTypeNumber()`. |
| “`JDBCType` và `SQLType` là hai enum khác nhau.” | `JDBCType implements SQLType`. |
| “`setNull(1, JDBCType.INTEGER)` là overload chuẩn.” | Dùng `setNull(1, Types.INTEGER)`; API `setNull` nhận mã `int`. |
| “Có JDBCType là driver hỗ trợ mọi kiểu.” | Enum mô tả kiểu, còn hỗ trợ thực tế do driver và DB quyết định. |
| “SQL NULL có nghĩa cột không còn kiểu dữ liệu.” | Cột vẫn có kiểu SQL; NULL chỉ là trạng thái giá trị. |
| “SQL NULL luôn đọc được bằng `getInt` như Java null.” | Getter nguyên thủy trả giá trị mặc định; gọi `wasNull()` để kiểm tra. |
| “`Types.OTHER` giúp tự hiểu mọi kiểu riêng.” | Ánh xạ vendor-specific cần tài liệu, metadata và cách bind thích hợp. |
| “`getColumnTypeName()` là tên lớp Java của cột.” | Đây là tên kiểu SQL; tên lớp Java xem `getColumnClassName()`. |
| “`DECIMAL` và `double` luôn giữ nguyên dữ liệu tiền.” | Dùng `BigDecimal` để tránh sai số nhị phân ngoài ý muốn. |

## 14. Bài tập tự kiểm tra

**Câu 1.** `Types.INTEGER`, `JDBCType.INTEGER` và `SQLType` khác nhau thế nào?

`Types.INTEGER` là giá trị `int`; `JDBCType.INTEGER` là một phần tử enum; `SQLType` là interface mà phần tử enum đó triển khai. Cả ba liên quan đến **kiểu SQL INTEGER**, nhưng có dạng biểu diễn Java khác nhau.

**Câu 2.** Cột `description VARCHAR(500)` được phép NULL. Khi giá trị Java là `null`, nên gọi gì?

`statement.setNull(index, Types.VARCHAR)`, dùng đúng chỉ số marker và kiểu SQL của cột. Không cần biến SQL thành chuỗi `'NULL'`; đây là một chuỗi ký tự, không phải giá trị NULL.

**Câu 3.** `rows.getInt("stock")` trả `0`. Có đủ cơ sở để nói cột chứa 0 không?

Không. SQL NULL cũng khiến getter nguyên thủy trả 0; cần gọi `rows.wasNull()` ngay sau `getInt(...)`.

**Câu 4.** Có thể gọi `statement.setObject(1, amount, JDBCType.DECIMAL)` ở đâu?

Ở overload `PreparedStatement.setObject(int, Object, SQLType)` của JDBC 4.2, nếu driver hỗ trợ. `amount` nên là giá trị Java phù hợp như `BigDecimal`.

**Câu 5.** `ResultSetMetaData.getColumnType(...)` trả `Types.OTHER`. Có thể kết luận giá trị cột phải đọc thành `String` không?

Không. `OTHER` không nói một lớp Java duy nhất. Cần xem `getColumnTypeName(...)`, metadata khác và hướng dẫn của driver cho kiểu riêng đó.

**Câu 6.** Khi cần nhận một kiểu SQL do driver định nghĩa, chữ ký hàm nên dùng `SQLType` hay `JDBCType`?

`SQLType` linh hoạt hơn vì có thể nhận cả `JDBCType` và implementation vendor-specific. Nhưng driver phải thực sự hỗ trợ kiểu đó khi binding; chỉ thỏa interface chưa đủ.

## 15. Ghi nhớ

Trong JDBC, **`Types` cung cấp mã số kiểu SQL, `JDBCType` cung cấp các tên kiểu chuẩn dưới dạng enum, còn `SQLType` là interface chung để biểu diễn kiểu SQL**. Khi API yêu cầu `int`, dùng `Types.X`; khi API nhận `SQLType` và cần kiểu chuẩn, dùng `JDBCType.X`. Với kiểu riêng của DB, kiểm tra tài liệu driver và đừng coi `OTHER` là phép chuyển đổi tự động.

Khi gặp giá trị **SQL NULL**, hãy phân biệt kiểu của cột với trạng thái không có giá trị, bind bằng `setNull(index, Types.X)` khi biết kiểu đích, và kiểm tra `wasNull()` ngay sau getter nguyên thủy. Kết hợp đúng các API kiểu dữ liệu, metadata và quản lý `PreparedStatement`/`ResultSet` sẽ giúp ứng dụng JDBC trao đổi dữ liệu chính xác và dễ bảo trì.
