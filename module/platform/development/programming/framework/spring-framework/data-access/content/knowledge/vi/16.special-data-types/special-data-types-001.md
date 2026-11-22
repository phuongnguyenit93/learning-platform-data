# Chuyển đổi giữa kiểu SQL và kiểu Java trong Spring JDBC

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Framework truy cập cơ sở dữ liệu qua JDBC, một giá trị đi qua ba lớp kiểu dữ liệu:

1. **Kiểu của cột trong database**: `VARCHAR`, `DECIMAL`, `DATE`, `TIMESTAMP`, `BLOB`, `ARRAY`, `JSON`, `UUID`…
2. **Kiểu JDBC và driver**: `java.sql.Types` / `JDBCType` mô tả loại dữ liệu SQL; `PreparedStatement` gắn giá trị đầu vào; `ResultSet` đọc giá trị đầu ra. Driver quyết định hỗ trợ chuyển đổi và biểu diễn đặc thù.
3. **Kiểu ứng dụng Java**: `String`, `BigDecimal`, `Long`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `UUID`, `byte[]`, Java record/bean và các đối tượng nghiệp vụ.

Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcInsert`, `SimpleJdbcCall`) quản lý vòng đời tài nguyên, bind tham số, ánh xạ dòng kết quả và chuyển lỗi SQL thành `DataAccessException`. **Spring không xóa bỏ khác biệt kiểu giữa các database**. Với loại đặc biệt, bạn vẫn cần quyết định kiểu Java, cách bind, cách đọc, xử lý `NULL` và đôi khi viết converter cụ thể cho driver.

Bài này tập trung vào việc chọn và kiểm soát chuyển đổi giữa SQL ↔ Java trong Spring JDBC, bao gồm cả kiểu thông thường làm nền tảng và **kiểu dữ liệu đặc biệt**. Không đánh đồng cơ chế của Spring JDBC với JPA/Hibernate: `@Column`, `AttributeConverter` và dialect của JPA không tự động được `JdbcTemplate` áp dụng.

### Đường đi của một giá trị

~~~text
Java value
  -> Spring JDBC parameter binding
  -> PreparedStatement.setXxx/setObject/setNull
  -> JDBC driver -> SQL column
  -> ResultSet.getXxx/getObject/getArray/getBlob...
  -> RowMapper/ResultSetExtractor
  -> Java value / domain model
~~~

Điều phải xác nhận là **hai chiều**. Việc driver ghi được một `UUID` hoặc một chuỗi JSON chưa bảo đảm đọc lại sẽ ra đúng kiểu `UUID` hay POJO mong muốn. Cũng không có một ánh xạ duy nhất cho mọi hệ DB, mọi phiên bản driver, mọi kiểu mở rộng.

## 2. Ba khái niệm khác nhau: SQL type, JDBC type và Java type

- **SQL type**: cách database lưu và diễn giải dữ liệu, ví dụ `NUMERIC(12,2)` có precision 12 và scale 2; `TIMESTAMP WITH TIME ZONE` có ngữ nghĩa khác `TIMESTAMP` thường.
- **JDBC type code**: hằng số như `Types.DECIMAL`, `Types.VARCHAR`, `Types.TIMESTAMP`, `Types.ARRAY`, `Types.OTHER`; dùng khi bind hoặc khai báo tham số. `JDBCType` là enum hiện đại triển khai `SQLType`, ví dụ `JDBCType.DECIMAL`. Nhiều API Spring JDBC nhận `int` từ `Types`.
- **Java type**: giá trị trong chương trình; lựa chọn cần dựa trên nullability, phạm vi số, precision, timezone, tính bất biến và nhu cầu nghiệp vụ.

Hai cột có cùng tên `id` nhưng một cột `INTEGER`, một cột `BIGINT` có thể cần `Integer` và `Long` khác nhau; hai cột `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE` cũng không nên tự coi là cùng một `Instant` nếu chưa thống nhất cách lưu múi giờ.

### Bảng ánh xạ thực hành

Đây là **kiểu Java thường nên chọn**, không phải cam kết `ResultSet.getObject(column)` luôn trả đúng lớp đó.

| Kiểu SQL/JDBC | Kiểu Java thường dùng | Lưu ý chuyển đổi |
|---|---|---|
| `CHAR`, `VARCHAR`, `LONGVARCHAR`, `NCHAR`, `NVARCHAR` | `String` | `CHAR` có thể được pad dấu cách; collation và Unicode tùy DB |
| `TINYINT`, `SMALLINT` | `Byte`, `Short` hoặc `Integer` tùy phạm vi | Đừng giả định mọi driver trả đúng wrapper khi dùng `getObject()` không khai báo kiểu |
| `INTEGER` | `Integer` / `int` | `int` không biểu diễn SQL `NULL` |
| `BIGINT` | `Long` / `long` | Kiểm tra cột số không dấu hay số vượt `long` ở DB cụ thể |
| `DECIMAL(p,s)`, `NUMERIC(p,s)` | `BigDecimal` | Đúng khi cần giá trị thập phân chính xác, nhất là tiền |
| `REAL`, `FLOAT`, `DOUBLE PRECISION` | `Float` hoặc `Double` theo loại thực tế | Số dấu phẩy động nhị phân có sai số biểu diễn |
| `BOOLEAN`, `BIT` | `Boolean` / `boolean` hoặc driver-specific | `BIT(n)` không nhất thiết là một boolean, có thể là chuỗi bit |
| `DATE` | `LocalDate` | Chỉ có ngày lịch, không mang thời điểm/múi giờ |
| `TIME [WITHOUT TIME ZONE]` | `LocalTime` | Chỉ có giờ trong ngày |
| `TIMESTAMP [WITHOUT TIME ZONE]` | `LocalDateTime` | Không chứa offset/zone; tránh diễn giải là UTC theo mặc định |
| `TIME WITH TIME ZONE` | `OffsetTime` | Phụ thuộc DB/driver |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` | Hành vi lưu offset gốc, chuẩn hóa UTC và đọc lại tùy DB |
| `BINARY`, `VARBINARY`, `LONGVARBINARY` | `byte[]` | Dữ liệu nhị phân nhỏ; không tự chuyển thành chuỗi UTF-8 |
| `BLOB` | `Blob` hoặc stream/`byte[]` | Quan tâm bộ nhớ, kích thước và vòng đời connection |
| `CLOB`, `NCLOB` | `Clob`/`NClob`, `Reader` hoặc `String` | Text lớn; kiểm tra mã hóa và streaming |
| `ARRAY` | `java.sql.Array` và phần tử Java được driver trả | Khác Java array/List và khác mở rộng `IN (:ids)` của Spring |
| `STRUCT`, kiểu composite | `java.sql.Struct`, `SQLData` hoặc object do converter tạo | Phụ thuộc tên kiểu và cấu trúc DB |
| `SQLXML` | `java.sql.SQLXML`, XML text/DOM/StAX sau khi parse | Phải xử lý nội dung XML và tài nguyên |
| `UUID`, `JSON/JSONB`, `ENUM`, kiểu không chuẩn | `UUID`, `String`/POJO, enum Java | **Không có ánh xạ xuyên DB thống nhất**; driver có thể dùng `Types.OTHER` |

**Nguyên tắc:** đừng chỉ nhìn tên kiểu Java để suy ra SQL type. Khi nghi ngờ, kiểm tra DDL, `ResultSetMetaData.getColumnType()`, `getColumnTypeName()` và lớp giá trị do driver trả. `java.sql.Types.OTHER` thường là tín hiệu kiểu mở rộng, không phải một converter JSON/UUID tổng quát.

## 3. Chuyển từ Java sang SQL: bind tham số

### JDBC thuần làm gì?

JDBC liên kết tham số theo vị trí **1-based**:

~~~java
// Đoạn minh họa bên trong phạm vi đã có PreparedStatement ps.
ps.setLong(1, 42L);
ps.setBigDecimal(2, new java.math.BigDecimal("19.90"));
ps.setObject(3, java.time.LocalDate.of(2026, 10, 30));
ps.setNull(4, java.sql.Types.VARCHAR);
~~~

`setLong`, `setBigDecimal`… rõ kiểu đầu vào. `setObject` yêu cầu driver chuyển từ object Java sang SQL; JDBC 4.2 hỗ trợ nhiều kiểu `java.time` qua `setObject`/`getObject`. Khi driver không hỗ trợ hoặc cần tính tương thích, chuyển sang `java.sql.Date.valueOf(localDate)`, `Time.valueOf(localTime)` hoặc `Timestamp.valueOf(localDateTime)` cho cột không mang timezone. Cách này không tự giải quyết múi giờ của một thời điểm tuyệt đối.

`ps.setObject(index, value, targetSqlType)` hoặc `ps.setNull(index, sqlType)` đặt SQL type đích rõ ràng. Không dùng `setString` cho mọi loại dữ liệu rồi để DB tự CAST một cách ngẫu nhiên.

### `JdbcTemplate`: tham số theo vị trí và `Types`

~~~java
// Minh họa với JdbcTemplate jdbc đã cấu hình, bảng account tồn tại.
int changed = jdbc.update(
        "UPDATE account SET balance = ?, closed_at = ? WHERE id = ?",
        new Object[] {new java.math.BigDecimal("125.50"), null, 10L},
        new int[] {
                java.sql.Types.DECIMAL,
                java.sql.Types.TIMESTAMP,
                java.sql.Types.BIGINT
        }
);
~~~

Mảng kiểu SQL có **một phần tử cho mỗi dấu `?`**, cùng thứ tự SQL. Đây là cách an toàn khi truyền `null` có kiểu, nhất là với driver cần metadata cụ thể. Truyền mảng kiểu không thay đổi tính nullable của cột: schema `NOT NULL` vẫn có quyền từ chối.

Một cách khác là `SqlParameterValue`:

~~~java
// Minh họa với JdbcTemplate jdbc đã cấu hình.
jdbc.update(
        "UPDATE account SET balance = ? WHERE id = ?",
        new org.springframework.jdbc.core.SqlParameterValue(
                java.sql.Types.DECIMAL,
                new java.math.BigDecimal("125.50")),
        10L
);
~~~

`SqlParameterValue` mang SQL type đi cùng một giá trị, có thể bao gồm scale cho kiểu số. Khi driver không suy luận được kiểu từ Java value (đặc biệt `NULL` và kiểu lạ), cách này rõ nghĩa hơn đưa một `Object` trần.

### `NamedParameterJdbcTemplate`: tham số theo tên và SQL type

~~~java
// Minh họa: đã có NamedParameterJdbcTemplate named.
var params = new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("id", 10L, java.sql.Types.BIGINT)
        .addValue("balance", new java.math.BigDecimal("125.50"),
                java.sql.Types.DECIMAL)
        .addValue("closedAt", null, java.sql.Types.TIMESTAMP);

int changed = named.update("""
        UPDATE account
        SET balance = :balance, closed_at = :closedAt
        WHERE id = :id
        """, params);
~~~

`MapSqlParameterSource.addValue(name, value, sqlType)` và `registerSqlType(name, sqlType)` giúp chỉ rõ kiểu theo **tên**. `BeanPropertySqlParameterSource` đọc giá trị từ getter của bean và cũng có thể đăng ký type; dùng khi các thuộc tính Java khớp tên tham số. Với `null`, `Map.of(...)` không phải lựa chọn vì không chấp nhận null value.

**Lưu ý:** bind parameter chỉ áp dụng **giá trị**. Tên bảng, tên cột, thứ tự sắp xếp hoặc kiểu SQL không được bảo vệ nếu lắp chuỗi trực tiếp từ dữ liệu không tin cậy. Với identifier động, kiểm tra allowlist và ghép SQL có kiểm soát.

## 4. Chuyển từ SQL sang Java: đọc `ResultSet` có chủ đích

Ba cách thường gặp:

~~~java
String label = rs.getString("label");
java.math.BigDecimal amount = rs.getBigDecimal("amount");
java.time.LocalDate when = rs.getObject("booked_on",
        java.time.LocalDate.class);
~~~

`rs.getObject("booked_on", LocalDate.class)` yêu cầu chuyển giá trị sang lớp Java cụ thể, nếu driver hỗ trợ. Khác với `rs.getObject("booked_on")`: cách không truyền lớp dùng kiểu mặc định của driver và có thể trả `java.sql.Date` thay vì `LocalDate`.

Trong Spring JDBC, dùng `RowMapper<T>` để quyết định cách tạo đối tượng:

~~~java
// Minh họa trong biến RowMapper<Item> mapper của DAO.
(rs, rowNum) -> new Item(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getBigDecimal("amount"),
        rs.getObject("created_on", java.time.LocalDate.class)
)
~~~

Đoạn này chỉ minh họa logic mapper và giả định đã khai báo record/class `Item` tương ứng. `JdbcTemplate` đóng statement/result set đúng vòng đời, còn `RowMapper` quyết định field nào có ý nghĩa và cách kiểm tra null/kiểu. Khi SQL chỉ trả một cột, có thể dùng `queryForObject(sql, BigDecimal.class, args...)`; không áp dụng kiểu ánh xạ một cột cho truy vấn nhiều cột.

**Cần phân biệt:**

- `ResultSet#getInt/getLong/getBoolean` trả primitive; SQL `NULL` bị biểu diễn bằng 0/false nên phải dùng `wasNull()` nếu cột cho phép null.
- `getString/getBigDecimal/getBytes/getObject` trả reference có thể là `null`.
- `getObject(column, Integer.class)` giúp lấy nullable wrapper khi driver hỗ trợ kiểu yêu cầu.
- `ResultSet.getObject(...)` không tự biến JSON thành record ứng dụng, enum thành enum Java hoặc binary thành tài liệu đúng định dạng.

### `NULL` và primitive: một lỗi dữ liệu âm thầm

~~~java
int raw = rs.getInt("rating");
Integer rating = rs.wasNull() ? null : raw;

// Trên driver hỗ trợ chuyển đổi có định kiểu:
Integer rating2 = rs.getObject("rating", Integer.class);
~~~

Nếu cột rating có SQL `NULL` mà code chỉ đọc `int raw = rs.getInt("rating")`, bạn sẽ thấy `0` và dễ nhầm “chưa đánh giá” với “đánh giá bằng 0”. `wasNull()` phải gọi **ngay sau** getter cần kiểm tra, trước khi đọc cột khác.

Khi thiết kế model, dùng `Integer`/`Long`/`Boolean` nếu nghiệp vụ cần phân biệt null; dùng primitive chỉ khi cột chắc chắn `NOT NULL` và logic không cần trạng thái chưa xác định. `Optional<T>` có thể là kiểu trả về của DAO/service, nhưng đừng giả định driver JDBC tự trả `Optional<T>` từ `getObject`.

## 5. Ví dụ hoàn chỉnh Java 17 + Spring JDBC + H2

Ví dụ chạy độc lập bằng Maven, **không cần Spring Boot**. Dữ liệu gồm số chính xác, boolean, ngày, timestamp và cột số cho phép `NULL`. Bước ghi dùng `NamedParameterJdbcTemplate` cùng SQL type tường minh; bước đọc dùng `JdbcTemplate` cùng `RowMapper` và `getObject(column, Class)`.

Cấu trúc file:

~~~text
sql-java-conversion-demo/
├── pom.xml
└── src/main/java/demo/SqlJavaTypeDemo.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sql-java-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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

**`src/main/java/demo/SqlJavaTypeDemo.java`:**

~~~java
package demo;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public class SqlJavaTypeDemo {

    record Item(long id, String label, BigDecimal amount,
                boolean active, LocalDate bookedOn,
                LocalDateTime recordedAt, Integer rating) {}

    public static void main(String[] args) {
        JdbcDataSource ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:sql_types_demo;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(ds);

        jdbc.execute("""
                CREATE TABLE item (
                    id BIGINT PRIMARY KEY,
                    label VARCHAR(80) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    active BOOLEAN NOT NULL,
                    booked_on DATE NOT NULL,
                    recorded_at TIMESTAMP NOT NULL,
                    rating INTEGER NULL
                )
                """);

        LocalDate day = LocalDate.of(2026, 10, 30);
        LocalDateTime localTime =
                LocalDateTime.of(2026, 10, 30, 9, 15, 30);

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", 7L, Types.BIGINT)
                .addValue("label", "Book", Types.VARCHAR)
                .addValue("amount", new BigDecimal("259.90"), Types.DECIMAL)
                .addValue("active", true, Types.BOOLEAN)
                .addValue("bookedOn", Date.valueOf(day), Types.DATE)
                .addValue("recordedAt",
                        Timestamp.valueOf(localTime), Types.TIMESTAMP)
                .addValue("rating", null, Types.INTEGER);

        int inserted = named.update("""
                INSERT INTO item
                    (id, label, amount, active, booked_on, recorded_at, rating)
                VALUES
                    (:id, :label, :amount, :active, :bookedOn,
                     :recordedAt, :rating)
                """, params);

        Item row = jdbc.queryForObject("""
                SELECT id, label, amount, active,
                       booked_on, recorded_at, rating
                FROM item WHERE id = ?
                """, (rs, rowNum) -> new Item(
                rs.getLong("id"),
                rs.getString("label"),
                rs.getBigDecimal("amount"),
                rs.getBoolean("active"),
                rs.getObject("booked_on", LocalDate.class),
                rs.getObject("recorded_at", LocalDateTime.class),
                rs.getObject("rating", Integer.class)
        ), 7L);

        System.out.println("inserted=" + inserted);
        System.out.println("id=" + row.id());
        System.out.println("label=" + row.label());
        System.out.println("amount=" + row.amount().toPlainString());
        System.out.println("active=" + row.active());
        System.out.println("bookedOn=" + row.bookedOn());
        System.out.println("recordedAt=" + row.recordedAt());
        System.out.println("rating=" + row.rating());

        int updated = jdbc.update(
                "UPDATE item SET rating = ? WHERE id = ?",
                new Object[] {5, 7L},
                new int[] {Types.INTEGER, Types.BIGINT}
        );
        Integer newRating = jdbc.queryForObject(
                "SELECT rating FROM item WHERE id = ?",
                Integer.class, 7L
        );
        System.out.println("updated=" + updated);
        System.out.println("newRating=" + newRating);
    }
}
~~~

**Chạy** (cài JDK 17+ và Maven, đứng tại thư mục chứa `pom.xml`):

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.SqlJavaTypeDemo"
~~~

**Đầu ra logic trên H2 in-memory mới:**

~~~text
inserted=1
id=7
label=Book
amount=259.90
active=true
bookedOn=2026-10-30
recordedAt=2026-10-30T09:15:30
rating=null
updated=1
newRating=5
~~~

Tại sao kết quả đúng?

1. `BigDecimal("259.90")` giữ giá trị thập phân chính xác, H2 lưu với scale 2. `toPlainString()` hiển thị `259.90`.
2. Input ngày dùng `java.sql.Date.valueOf(LocalDate)` và input timestamp dùng `Timestamp.valueOf(LocalDateTime)` để rõ SQL type; khi đọc, JDBC 4.2/H2 hỗ trợ `LocalDate`, `LocalDateTime` trực tiếp.
3. Cột `rating` ở lần INSERT là SQL `NULL`, nên Java `Integer rating` nhận `null` chứ không bị biến thành số 0.
4. Lời gọi `JdbcTemplate.update(...)` dùng mảng `Types` với thứ tự chính xác cho hai dấu `?`, rồi `queryForObject(..., Integer.class)` đọc một scalar.
5. Giá trị `TIMESTAMP` trong ví dụ là thời gian lịch *không có offset*; chữ `2026-10-30T09:15:30` không thể tự suy ra UTC hay múi giờ Việt Nam từ nó.

Đây là chương trình chạy độc lập. Các đoạn ngắn phía sau là minh họa cho các hệ DB hoặc bảng khác; **không ghép chúng nguyên xi vào chương trình trên**.

## 6. SQL `DECIMAL`, `NUMERIC` và độ chính xác số

### Tiền, số thập phân chính xác: chọn `BigDecimal`

`DECIMAL(12,2)` có tối đa 12 chữ số tổng cộng và 2 chữ số sau dấu thập phân (theo cách DB thực thi precision/scale). Java `double` lưu nhị phân nên không biểu diễn chính xác hầu hết giá trị thập phân như 0.1:

~~~java
var safe = new java.math.BigDecimal("0.10");
var unsafe = new java.math.BigDecimal(0.1);

System.out.println(safe.toPlainString());
System.out.println(unsafe.toPlainString());
~~~

Kết quả dòng đầu là `0.10`. Dòng thứ hai là một biểu diễn thập phân dài của giá trị `double` 0.1, nên không dùng constructor từ `double` cho tiền. Đoạn trên có thể chạy khi đặt trong một method Java; nó không liên quan đến H2 demo.

Chọn `BigDecimal` cho giá/tiền, số đo cần precision; chọn `Float`/`Double` cho dữ liệu dấu phẩy động phù hợp nghiệp vụ. `BigDecimal.equals(...)` tính cả scale: `1.0` và `1.00` khác nhau theo `equals` nhưng bằng nhau theo `compareTo(...) == 0`. Khi làm tròn, định nghĩa rõ `RoundingMode` tại điểm nghiệp vụ, đừng để việc chuyển kiểu ngầm định quyết định.

### Phạm vi số nguyên và overflow

`BIGINT` thông thường tương ứng `long` có dấu của Java. Nếu DB sử dụng unsigned BIGINT, NUMBER lớn hoặc `NUMERIC(38,0)`, một `long` có thể không đủ. `Number.longValue()` có thể mất phần vượt phạm vi; `BigDecimal.longValueExact()` hoặc `BigInteger.longValueExact()` giúp phát hiện không biểu diễn chính xác:

~~~java
java.math.BigDecimal n =
        new java.math.BigDecimal("9223372036854775808");

try {
    System.out.println(n.longValueExact());
} catch (ArithmeticException ex) {
    System.out.println("BIGINT vuot pham vi long");
}
~~~

Đầu ra của ví dụ số riêng này: `BIGINT vuot pham vi long`.

Khi ánh xạ schema, kiểm tra cả **giới hạn**, **scale**, **signed/unsigned**, và DB driver có chuyển kiểu tự động hay không. Không ép kiểu `(Long) rs.getObject("id")` khi driver có thể trả `BigDecimal` hoặc `BigInteger`.

## 7. Ngày, giờ và vấn đề timezone

Đây là một trong những vùng dễ sinh lỗi nhất khi chuyển SQL ↔ Java.

| Loại giá trị | Kiểu SQL phổ biến | Java thích hợp | Ý nghĩa |
|---|---|---|---|
| Sinh nhật hoặc ngày kế toán | `DATE` | `LocalDate` | Ngày trên lịch, không có giờ |
| Giờ mở cửa | `TIME` | `LocalTime` | Giờ trong ngày, chưa gắn ngày/zone |
| Giờ hẹn theo lịch địa phương | `TIMESTAMP WITHOUT TIME ZONE` | `LocalDateTime` | Ngày + giờ, không có offset |
| Thời điểm có thông tin offset | `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` | Có thể chuyển về một `Instant` |
| Một thời điểm toàn cục để so sánh | Chọn chiến lược lưu UTC hoặc kiểu có timezone rõ ràng | `Instant` ở domain layer | Không coi `LocalDateTime` là instant nếu chưa gắn zone |

Ví dụ dùng JDBC 4.2, giả sử DB/driver hỗ trợ `TIMESTAMP WITH TIME ZONE`:

~~~java
// Đoạn minh họa trong RowMapper, cột event_at có timezone.
java.time.OffsetDateTime dt =
        rs.getObject("event_at", java.time.OffsetDateTime.class);
java.time.Instant instant = dt == null ? null : dt.toInstant();
~~~

Với input, driver hiện đại có thể hỗ trợ `ps.setObject(index, offsetDateTime)` hoặc chỉ định `Types.TIMESTAMP_WITH_TIMEZONE`; cần integration test. `OffsetDateTime` có offset như `+07:00`, nhưng không lưu đầy đủ tên vùng `Asia/Ho_Chi_Minh`. Một số DB chuẩn hóa giá trị về UTC, một số giữ offset theo cách riêng. `TIMESTAMP WITHOUT TIME ZONE` thường không lưu bất kỳ thông tin offset nào.

**Lỗi cần tránh:**

- Tự gắn `ZoneOffset.UTC` vào một `LocalDateTime` được ghi từ giờ địa phương mà chưa xác minh nguồn. Kết quả lệch nhiều giờ.
- Giả định `java.sql.Timestamp` luôn là thời điểm UTC: nó là kiểu legacy biểu diễn timestamp, việc diễn giải khi qua DB/driver phụ thuộc cấu hình.
- Dùng `java.util.Date` hoặc `String` thay `LocalDate` cho ngày sinh làm tăng rủi ro vô tình chuyển múi giờ.
- Cho rằng database trả lại đúng offset ban đầu chỉ vì cột tên `TIMESTAMP WITH TIME ZONE`. Hãy kiểm tra hành vi chính xác của DB production.

Khi xử lý dữ liệu thời điểm, thống nhất chiến lược: (1) lưu UTC/instant hoặc kiểu time zone thích hợp, (2) chuyển zone chỉ ở biên trình bày, (3) cấu hình timezone session/driver, (4) test case qua nửa đêm và giờ tiết kiệm ánh sáng nếu hệ thống phục vụ vùng có DST.

## 8. Kiểu đặc biệt: UUID, JSON, ENUM và các type vendor

Các kiểu này không có cùng một hợp đồng Java/JDBC trên mọi database.

### UUID

Một số DB cung cấp kiểu `UUID` native, một số lưu bằng `CHAR(36)`, `BINARY(16)` hoặc tổ hợp khác. Với DB/driver hỗ trợ object `UUID`, ví dụ PostgreSQL hoặc H2:

~~~java
// Minh họa với PreparedStatement ps và ResultSet rs trên DB hỗ trợ UUID.
java.util.UUID uuid =
        java.util.UUID.fromString("11111111-2222-4333-8444-555555555555");
ps.setObject(1, uuid); // driver hỗ trợ chuyển UUID sang SQL UUID
java.util.UUID readBack =
        rs.getObject("external_id", java.util.UUID.class);
~~~

Ví dụ chỉ minh họa JDBC API trong ngữ cảnh đã có `ps` và `rs`; nó không tự chứa query/tables. Cấu hình `MapSqlParameterSource.addValue("externalId", uuid, Types.OTHER)` có thể phù hợp với driver sử dụng `OTHER` cho UUID, nhưng không nên ép `Types.OTHER` chung cho mọi DB. Nếu lưu UUID dưới `BINARY(16)` hoặc `CHAR(36)`, cần codec định nghĩa rõ thứ tự byte/chuỗi; đừng giả định JDBC tự làm việc đó.

### JSON và JSONB

SQL `JSON`/`JSONB` thường cần **serialize Java object thành JSON text** khi ghi, và **parse JSON về model** khi đọc. Spring JDBC không tự biến `Map<String,Object>` thành `JSONB` của mọi DB.

Ví dụ SQL **dành riêng cho PostgreSQL**, với `payloadJson` đã là chuỗi JSON hợp lệ (chẳng hạn do Jackson tạo), `named` là `NamedParameterJdbcTemplate` đã cấu hình:

~~~java
var p = new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("id", 100L, java.sql.Types.BIGINT)
        .addValue("payload", payloadJson, java.sql.Types.VARCHAR);

named.update("""
        INSERT INTO event_store(id, payload)
        VALUES (:id, CAST(:payload AS jsonb))
        """, p);
~~~

`CAST(... AS jsonb)` là chi tiết PostgreSQL; database khác có cú pháp khác. Khi đọc, `rs.getString("payload")` có thể cung cấp JSON text để parse bằng Jackson (ví dụ `ObjectMapper.readValue(...)`). Đây là **đoạn minh họa**, cần bảng `event_store`, biến `payloadJson` và thư viện JSON trong ứng dụng, không phải phần của demo H2. Nếu driver trả `PGobject` qua `getObject`, phải trích JSON từ đối tượng theo API driver; đừng cast mù sang `String`.

### ENUM

Với enum Java `Status.ACTIVE`, chọn một trong hai chính sách và giữ nhất quán:

- Lưu text ổn định (ví dụ `"ACTIVE"`) trong cột `VARCHAR`; đọc `Status.valueOf(raw)` **sau khi** xác thực tên và xử lý giá trị legacy/không hợp lệ.
- Sử dụng enum native của database và converter/SQL type phù hợp driver.

Tránh lưu `ordinal()` của enum Java nếu thứ tự khai báo có thể đổi; chỉ cần chèn một giá trị enum vào giữa danh sách là ý nghĩa số cũ có thể sai.

### Kiểu không có mapping chuẩn

Các kiểu GIS, network address, range, composite, XML mở rộng, JSONB và kiểu vendor thường cần `Types.OTHER`, đối tượng driver riêng hoặc SQL cast. **`Types.OTHER` chỉ khai báo mã kiểu**, không bảo đảm driver có thể tự serialize POJO. Giữ converter tại tầng repository/adapter, test theo từng version driver và schema.

## 9. SQL `ARRAY` khác Java `List` và tham số `IN`

SQL ARRAY là **một giá trị cột** chứa nhiều phần tử. JDBC biểu diễn bằng `java.sql.Array`, không phải mặc định bằng `List<T>`.

~~~java
// Đoạn minh họa trong code đã có JdbcTemplate jdbc và bảng
// sample_array(id BIGINT, tags VARCHAR ARRAY) trên DB hỗ trợ ARRAY.
jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Void>) con -> {
    java.sql.Array sqlArray =
            con.createArrayOf("VARCHAR", new String[] {"spring", "jdbc"});
    try (java.sql.PreparedStatement ps = con.prepareStatement(
            "UPDATE sample_array SET tags = ? WHERE id = ?")) {
        ps.setArray(1, sqlArray);
        ps.setLong(2, 7L);
        ps.executeUpdate();
    } finally {
        sqlArray.free();
    }
    return null;
});
~~~

Đây là **ví dụ JDBC API**, không phải chương trình chạy độc lập: tên type truyền cho `createArrayOf`, DDL, cách lưu và support SQL ARRAY cần kiểm tra theo DB. Một số driver không hỗ trợ `createArrayOf` hoặc yêu cầu tên element type cụ thể (ví dụ `text`, `integer`). Việc đóng statement và giải phóng `Array` tránh giữ tài nguyên driver quá lâu.

Khi đọc:

~~~java
// Đoạn minh họa bên trong RowMapper.
java.sql.Array sqlArray = rs.getArray("tags");
Object javaArray = null;
if (sqlArray != null) {
    try {
        javaArray = sqlArray.getArray();
    } finally {
        sqlArray.free();
    }
}
// javaArray thường là một Java array do driver chọn; kiểm tra kiểu trước cast.
~~~

Dạng của `getArray()` có thể là `String[]`, `Integer[]`, `Object[]` hoặc loại khác; đừng cast cố định khi driver/schema chưa được xác minh.

**Đừng nhầm với `IN (:ids)`:** khi truyền `List<Long> ids` cho `NamedParameterJdbcTemplate`, Spring mở rộng nó thành nhiều dấu `?` trong một điều kiện SQL `IN`; đây là **nhiều bind scalar**, không phải một SQL ARRAY ở một cột. Tập IDs rỗng và giới hạn số parameter cần được xử lý riêng theo DB.

## 10. BLOB, CLOB, binary và SQLXML

### `BINARY/VARBINARY` và `BLOB`

- Tệp/hình ảnh nhỏ có thể dùng `byte[]` với `getBytes`/`setBytes`; cần kiểm tra kích thước dữ liệu và giới hạn bộ nhớ.
- `BLOB` lớn có thể đọc qua `ResultSet.getBinaryStream(...)` hoặc `Blob.getBinaryStream()`; chỉ đọc trong thời gian `ResultSet`/connection còn hợp lệ, đóng stream đúng cách.
- Spring có `LobHandler` / `DefaultLobHandler` với các API như `getBlobAsBytes`, `getBlobAsBinaryStream`, `LobCreator.setBlobAsBytes`, `setBlobAsBinaryStream`. Tránh tải toàn bộ BLOB hàng trăm MB vào `byte[]` nếu có thể stream.

Ví dụ đơn giản cho dữ liệu nhị phân nhỏ:

~~~java
// Minh họa trong RowMapper khi cột bytes là VARBINARY/BLOB nhỏ.
byte[] content = rs.getBytes("binary_content");
if (content != null) {
    System.out.println("bytes=" + content.length);
}
~~~

`byte[]` lưu raw bytes, không phải ảnh hay text đã được decode. Nếu bản chất là text, nên lưu cột text; khi cần chuyển binary thành text, chọn charset và định dạng rõ ràng, không dùng `new String(bytes)` thiếu charset.

### `CLOB/NCLOB`

Text nhỏ/vừa thường có thể đọc bằng `getString`. Với nội dung lớn, dùng `getCharacterStream`, `Clob` hoặc `LobHandler` trong thời gian tài nguyên JDBC còn mở. Lưu dữ liệu Unicode cần chọn kiểu cột và charset/collation phù hợp. Không nhầm `CLOB` là blob bytes UTF-8 trong mọi driver.

### `SQLXML`

`SQLXML` là kiểu dữ liệu JDBC riêng, dùng `getSQLXML`/`setSQLXML` nếu DB hỗ trợ. Ví dụ đọc:

~~~java
// Minh họa trong RowMapper trên DB có SQLXML.
java.sql.SQLXML xml = rs.getSQLXML("xml_payload");
String xmlText = null;
if (xml != null) {
    try {
        xmlText = xml.getString();
    } finally {
        xml.free();
    }
}
// Phân tích XML an toàn nếu cần chuyển sang DOM hoặc object.
~~~

Với dữ liệu XML không tin cậy, cấu hình parser chống XXE và entity expansion; không tự khởi tạo parser có quyền truy cập tài nguyên ngoài nếu không cần.

### `STRUCT` và custom SQL types

`java.sql.Struct` có thể chứa nhiều thuộc tính, truy xuất bằng `getAttributes()`. Các loại như PostgreSQL composite hoặc Oracle OBJECT cần kiểm chứng với driver, tên SQL type và thứ tự thuộc tính. Khi gọi stored procedure có IN/OUT kiểu phức tạp, Spring cung cấp `SqlTypeValue`/`AbstractSqlTypeValue` để tạo object bind trên connection thực, và `SqlReturnType` cho kết quả OUT. Đây là extension point chuyên biệt; `JdbcTemplate` không tự biến mọi `STRUCT` thành Java record.

## 11. Kết hợp converter với `RowMapper`, `BeanPropertyRowMapper` và `DataClassRowMapper`

### Điều khiển rõ ràng bằng `RowMapper`

Với kiểu khó, chọn `RowMapper<T>` tự viết để biết chính xác:

1. Cột SQL nào được đọc và tên alias là gì.
2. Kiểu driver thực sự trả (`String`, `UUID`, `java.sql.Array`, `PGobject`…).
3. Cách xử lý null, range, format/timezone và lỗi chuyển đổi.
4. Cách tạo domain object và dọn tài nguyên JDBC.

Ví dụ, nếu cột `state` lưu một chuỗi enum hợp lệ, có thể viết:

~~~java
// Mảnh code minh họa bên trong RowMapper của đối tượng có State.
String rawState = rs.getString("state");
State state = rawState == null ? null : State.valueOf(rawState);
~~~

`State` phải là enum khai báo trong ứng dụng; `valueOf` ném `IllegalArgumentException` nếu DB chứa tên không hợp lệ. Có thể chủ động ánh xạ tên legacy, chuyển thành lỗi dữ liệu rõ ràng hoặc khai báo chính sách xử lý trạng thái không biết.

### Auto-mapping có giới hạn

`BeanPropertyRowMapper` gắn cột với thuộc tính JavaBean tương ứng, hỗ trợ quy tắc tên như `first_name` → `firstName` và sử dụng cơ chế conversion của Spring khi áp dụng được. `DataClassRowMapper` hữu ích cho constructor/record được hỗ trợ. Nhưng:

- Không đảm bảo map JSON/ARRAY/STRUCT/UUID vendor thành mọi class tùy ý.
- Không tự giải quyết null không hợp lệ cho primitive.
- Không tự xác định múi giờ nghiệp vụ từ `TIMESTAMP` thiếu timezone.
- SQL alias và tên property phải khớp; schema thay đổi có thể gây lỗi runtime hoặc dữ liệu thiếu.

Với kiểu đặc biệt, ưu tiên mapper/converter tường minh và kiểm thử trên DB thật. Khi dùng converter theo tầng ứng dụng, giữ một định nghĩa thống nhất cho cả chiều ghi và đọc; nếu chỉ sửa một chiều, dễ có dữ liệu không round-trip được.

### `ConversionService` của Spring có vai trò gì?

Spring Core `ConversionService` có thể chuyển giữa các kiểu Java khi đã có converter tương ứng; `BeanPropertyRowMapper` có thể tận dụng nó. Tuy nhiên **conversion Java → Java** khác **bind/extract SQL ↔ Java của JDBC driver**. Đăng ký `Converter<String, UUID>` trong Spring không mặc nhiên khiến driver hỗ trợ `setObject(UUID)` hoặc khiến PostgreSQL JSONB tự thành POJO. Đặt đúng logic ở đúng lớp.

## 12. Cách xác minh mapping trên hệ DB thật

Ví dụ SQL có cột đặc thù, việc nhìn DDL có thể chưa đủ. Có thể kiểm tra metadata trong `RowMapper`/`ResultSetExtractor`:

~~~java
// Đoạn minh họa khi đã có ResultSet rs.
java.sql.ResultSetMetaData md = rs.getMetaData();
for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(md.getColumnLabel(i)
            + " sqlType=" + md.getColumnType(i)
            + " typeName=" + md.getColumnTypeName(i)
            + " className=" + md.getColumnClassName(i));
}
~~~

Các giá trị này là **thông tin do driver báo**, không phải bảo chứng mọi phép chuyển đổi mong muốn đều thành công. Để xác minh thật, kiểm tra riêng đầu vào và đầu ra, null/non-null, giới hạn và các phiên bản driver.

Checklist thử nghiệm quan trọng:

| Nhóm | Tình huống cần thử | Điều nên khẳng định |
|---|---|---|
| Numeric | `DECIMAL(12,2)`, số âm, số gần giới hạn | Giá trị và scale hợp nghiệp vụ; không mất precision |
| Null | `NULL`, chuỗi trống, 0, false | Phân biệt đúng cả bốn trường hợp |
| Date/time | Ngày cuối tháng, offset khác, DST nếu có | Không lệch ngày/giờ, không diễn giải timestamp sai zone |
| Text | Tiếng Việt, emoji, whitespace, dấu nháy | Unicode/escape qua bind được bảo toàn |
| UUID | UUID native và kiểu CHAR/BINARY nếu dùng | Chuyển đổi hai chiều, byte order và lớp Java đúng |
| JSON/JSONB | JSON null, SQL NULL, mảng/object, khóa lạ | Phân biệt JSON literal `null` với SQL `NULL`; parse/serialize ổn |
| ARRAY | Mảng rỗng, null element, số lớn | Kiểu phần tử và shape đúng driver |
| LOB | Dữ liệu trống, lớn, stream | Không mất byte/ký tự, không rò tài nguyên |
| ENUM/STRUCT | Giá trị mới/legacy, thứ tự field | Converter có chính sách tương thích |
| Driver | H2 test và DB production | Không suy ra khả năng production chỉ từ H2 |

## 13. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| SQL nhận `NULL` sai type | Driver không suy luận kiểu hoặc bind null không rõ type | Dùng `Types`, `SqlParameterValue`, `MapSqlParameterSource.addValue(name, null, sqlType)` |
| Một cột `NULL` trở thành 0/false | Getter primitive `getInt/getBoolean` được dùng không kèm `wasNull` | Dùng wrapper hoặc `wasNull()` ngay sau getter |
| Số tiền bị lẻ do làm tròn | Sử dụng `double`/`float` để tính tiền | `BigDecimal(String)` và quy tắc rounding minh bạch |
| Lỗi overflow khi đọc số | Ép `NUMERIC` rộng về `int/long` không kiểm tra | Dùng `BigDecimal`/`BigInteger` và `*ValueExact()` |
| `ClassCastException` khi cast `getObject` | Driver trả lớp khác kỳ vọng | Dùng getter typed khi được hỗ trợ hoặc converter cụ thể |
| Đọc `TIMESTAMP` lệch vài giờ | Gắn zone ngầm, cấu hình session/driver khác, nhầm instant với local time | Xác định nghĩa cột và timezone, test UTC/offset |
| Spring không tự map JSONB | JSON là kiểu vendor, driver trả JSON string/PGobject | Serializer/parser rõ ràng và SQL cast phù hợp |
| Lỗi khi bind `UUID`/`ARRAY` | DB/driver không hỗ trợ kiểu bind mặc định | Xác minh type name, API riêng và integration test |
| BLOB/CLOB lỗi sau khi thoát DAO | Đọc stream/LOB khi ResultSet/connection đã đóng | Đọc trong vòng đời callback/transaction, giải phóng tài nguyên |
| `ENUM` từ DB không tồn tại trong Java | Schema và code khác phiên bản | Converter xử lý giá trị mới/legacy, chiến lược migrate |
| Bean tự map sai cột | Alias tên cột không hợp property hoặc converter thiếu | Đặt alias rõ, kiểm thử `RowMapper`/`DataClassRowMapper` |
| Dữ liệu chứa dấu nháy làm hỏng SQL | Nối giá trị vào SQL thay vì bind parameter | Dùng `?`/`:name`, không lắp giá trị trực tiếp vào SQL |

Khi driver không hỗ trợ một chuyển đổi, lỗi JDBC thường được Spring bọc thành `DataAccessException` (thường có `SQLException` gốc). Giữ log SQL được phép, loại SQL type, DB/driver version và nguyên nhân lỗi; tránh log dữ liệu nhạy cảm hoặc toàn bộ BLOB/JSON chứa thông tin cá nhân.

## 14. Quy trình chọn mapping khi xây DAO

1. **Đọc schema thực:** SQL type, precision, scale, nullable, timezone semantics và cách DB sinh giá trị.
2. **Chọn Java domain type:** ưu tiên đúng nghĩa, ví dụ `BigDecimal` cho tiền, `LocalDate` cho ngày, `OffsetDateTime/Instant` theo chính sách thời điểm, `Integer` nếu cần null.
3. **Thiết kế chiều ghi:** chọn `setXxx` hoặc `setObject` được driver hỗ trợ; khai báo `Types` cho null và kiểu đặc biệt.
4. **Thiết kế chiều đọc:** dùng `RowMapper` và getter rõ ràng; xử lý `wasNull`, overflow và converter đặc biệt.
5. **Xác nhận round-trip:** ghi → đọc trên DB thật, kiểm tra cả non-null và null, giá trị biên, Unicode, precision, thời điểm và kiểu mở rộng.
6. **Xử lý tài nguyên và lỗi:** Spring quản lý connection/statement thông thường; stream/`Array`/`SQLXML`/LOB vẫn cần đọc và giải phóng đúng vòng đời.
7. **Đưa vào integration test:** H2 giúp học cú pháp, nhưng không thể thay thế PostgreSQL, Oracle, SQL Server, MySQL… khi kiểm tra kiểu đặc trưng driver.

## 15. Tự luyện tập

1. Trong `SqlJavaTypeDemo`, thay `new BigDecimal("259.90")` bằng `new BigDecimal(259.90)`, in `toPlainString()` rồi giải thích khác biệt.
2. Thêm cột `notes VARCHAR(60) NULL`. Chèn null bằng `MapSqlParameterSource` với `Types.VARCHAR`, đọc bằng `rs.getString` và xác minh Java null.
3. Đổi cột `rating` thành bắt buộc `NOT NULL`, thử chèn null. Phân biệt lỗi SQL constraint với lỗi mapping Java.
4. Thêm kiểu `TIMESTAMP WITH TIME ZONE` nếu DB/driver hỗ trợ, ghi một `OffsetDateTime` tại `+07:00`, đọc lại và so sánh bằng `toInstant()`.
5. Trên DB thực tế, thêm cột UUID hoặc JSONB, xây hàm chuyển đổi theo cả hai chiều; kiểm tra cách xử lý SQL NULL và JSON literal null.
6. Với cột `ARRAY` hoặc `BLOB`, viết kiểm thử đọc dữ liệu, đảm bảo tài nguyên được giải phóng đúng vòng đời.
7. Dùng `ResultSetMetaData` xác định type code, type name và class name mà driver báo, so sánh với Java type ứng dụng quyết định.

## Tài liệu tham khảo

- Spring Framework 6.2 — JDBC, Common Problems with Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html
- Spring Framework — Using JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html#jdbc-NamedParameterJdbcTemplate
- Spring Framework 6.2 — `MapSqlParameterSource` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Java SE 17 — `ResultSet` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17 — `PreparedStatement` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 — `Types` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html
- pgJDBC — Java 8 Date/Time Mappings (ví dụ một driver cụ thể): https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes
