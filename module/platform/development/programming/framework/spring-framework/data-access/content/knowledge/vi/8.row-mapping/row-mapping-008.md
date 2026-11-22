# Chọn kiểu Java nullable và xử lý wasNull() khi đọc nguyên thủy

> **Nguyên tắc:** SQL `NULL` biểu thị giá trị chưa biết/không có giá trị, trong khi kiểu nguyên thủy Java như `int`, `long`, `boolean`, `double` **không thể mang `null`**. Trong JDBC, các getter kiểu nguyên thủy như `ResultSet.getInt(...)` trả **`0`** nếu cột là SQL `NULL` và `getBoolean(...)` trả **`false`** nếu là SQL `NULL`. Vì thế, nếu một cột có thể `NULL`, phải đọc đúng bằng kiểu nullable hoặc gọi **`ResultSet.wasNull()` ngay sau getter nguyên thủy** để không đánh mất thông tin.

Bài này thuộc phần **ánh xạ kết quả** của Spring Framework Data Access. Trọng tâm là cách biến một hàng SQL thành Java object bằng `RowMapper`, cách giữ nguyên ý nghĩa của SQL `NULL` và cách chọn kiểu Java theo ràng buộc dữ liệu.

## 1. Vì sao SQL NULL gây lỗi âm thầm khi ánh xạ?

Xét bảng sau:

```sql
CREATE TABLE measurements (
    id BIGINT PRIMARY KEY,
    score INTEGER NULL,
    active BOOLEAN NULL,
    attempts BIGINT NULL,
    note VARCHAR(80) NULL
);

INSERT INTO measurements (id, score, active, attempts, note) VALUES
    (1, NULL, NULL, NULL, NULL),
    (2, 0, FALSE, 0, ''),
    (3, 42, TRUE, 123, 'ready');
```

Ba hàng mang các ý nghĩa khác nhau:

- `id=1`: điểm, trạng thái, số lần và ghi chú **chưa có giá trị**.
- `id=2`: điểm **bằng 0**, trạng thái **`false`**, số lần **bằng 0**, ghi chú **chuỗi rỗng**. Tất cả đều là giá trị thực, không phải SQL `NULL`.
- `id=3`: điểm 42, trạng thái true, số lần 123 và ghi chú "ready".

Nếu ánh xạ bằng:

```java
int score = rs.getInt("score");
boolean active = rs.getBoolean("active");
long attempts = rs.getLong("attempts");
```

thì hàng `id=1` và `id=2` đều nhìn giống nhau ở các biến trên: `score=0`, `active=false`, `attempts=0`. Chính điều này gây lỗi nghiệp vụ âm thầm: ứng dụng có thể hiểu "chưa chấm điểm" thành "được 0 điểm", "chưa xác định hoạt động" thành "không hoạt động" hoặc "chưa thống kê" thành "đã thống kê 0 lần".

Khi SQL cho phép `NULL` và sự khác biệt đó có ý nghĩa, **domain model phải giữ được trạng thái vắng mặt** bằng kiểu như `Integer`, `Boolean`, `Long` hoặc một value object rõ nghĩa.

## 2. Hợp đồng chính xác của các getter trong ResultSet

`java.sql.ResultSet` có các getter theo kiểu. Chúng nhận **chỉ số cột bắt đầu từ 1** hoặc **nhãn cột** (column label, gồm alias nếu SQL dùng `AS`).

| SQL / JDBC getter | Kiểu trả về Java | Nếu SQL là `NULL` |
| --- | --- | --- |
| `getInt(...)` | `int` | `0` |
| `getLong(...)` | `long` | `0L` |
| `getShort(...)`, `getByte(...)` | `short`, `byte` | `0` |
| `getDouble(...)`, `getFloat(...)` | `double`, `float` | `0.0` |
| `getBoolean(...)` | `boolean` | `false` |
| `getString(...)` | `String` | Java `null` |
| `getBigDecimal(...)` | `BigDecimal` | Java `null` |
| `getDate(...)`, `getTimestamp(...)` | `java.sql.Date`, `Timestamp` | Java `null` |
| `getObject(...)` | `Object` | Java `null` |
| `getObject(label, Integer.class)` | `Integer` nếu conversion được hỗ trợ | Java `null` |

**Cảnh báo:** Không phải getter nguyên thủy ném exception khi gặp SQL `NULL`. Nó thường trả giá trị mặc định của kiểu Java và cập nhật trạng thái để `wasNull()` có thể kiểm tra. Vì vậy việc không có exception **không chứng minh cột đã có giá trị**.

### wasNull() làm gì?

```java
boolean wasNull = rs.wasNull();
```

`ResultSet.wasNull()` trả `true` khi **giá trị của cột vừa được đọc bởi getter gần nhất** là SQL `NULL`. Nó không phải kiểm tra "có hàng nào null trong ResultSet" và cũng không phải thuộc tính null của toàn bộ hàng.

Trình tự đúng:

```java
int rawScore = rs.getInt("score");
boolean scoreWasNull = rs.wasNull(); // Kiểm tra ngay sau getInt

Integer score = scoreWasNull ? null : rawScore;
```

Kết quả:

| Giá trị SQL của `score` | `rawScore` | `scoreWasNull` | `score` |
| --- | ---: | --- | --- |
| `NULL` | `0` | `true` | `null` |
| `0` | `0` | `false` | `Integer.valueOf(0)` |
| `42` | `42` | `false` | `Integer.valueOf(42)` |

Điểm then chốt là **cả hai trường hợp SQL `NULL` và SQL số 0 cùng tạo ra `rawScore=0`**, nhưng `wasNull()` giúp phân biệt.

## 3. Phải gọi wasNull() ngay sau getter cần kiểm tra

### Mẫu đúng

```java
int rawScore = rs.getInt("score");
Integer score = rs.wasNull() ? null : rawScore;

boolean rawActive = rs.getBoolean("active");
Boolean active = rs.wasNull() ? null : rawActive;

long rawAttempts = rs.getLong("attempts");
Long attempts = rs.wasNull() ? null : rawAttempts;
```

Mỗi phép gọi `wasNull()` theo sát đúng getter của cột. Không có lệnh đọc cột khác chen giữa.

### Mẫu sai: đọc cột thứ hai rồi mới hỏi cột thứ nhất

```java
int rawScore = rs.getInt("score");
String note = rs.getString("note");
boolean scoreWasNull = rs.wasNull(); // SAI: kiểm tra NOTE, không còn SCORE
```

Ở đây trạng thái `wasNull()` phản ánh **lần đọc `getString("note")` gần nhất**, nên tên biến `scoreWasNull` gây hiểu nhầm. Nếu `score` là SQL `NULL` nhưng `note` có giá trị, biến trở thành `false` và ứng dụng tưởng score bằng 0 thật.

Sửa:

```java
int rawScore = rs.getInt("score");
boolean scoreWasNull = rs.wasNull();

String note = rs.getString("note");
```

Giữa một getter và `wasNull()` có thể có các phép tính Java không đọc cột, nhưng **quy tắc an toàn và dễ review nhất là gọi ngay**, nhất là trong `RowMapper` có nhiều cột hoặc các hàm trợ giúp.

### Mẫu sai: dùng giá trị mặc định để tự đoán

```java
int rawScore = rs.getInt("score");
Integer score = (rawScore == 0) ? null : rawScore; // SAI
```

Số `0` là giá trị hợp lệ của SQL `INTEGER`; đoạn trên làm mất trường hợp score thật sự bằng 0.

```java
boolean rawActive = rs.getBoolean("active");
Boolean active = rawActive ? true : null; // SAI
```

Cách này làm mất trường hợp SQL `FALSE` (giá trị có thật). Đặc biệt với cờ nghiệp vụ ba trạng thái (*true / false / unknown*), kiểu Java `Boolean` và kiểm tra `wasNull()` là cần thiết.

## 4. Chọn kiểu Java theo khả năng NULL của dữ liệu

Quy tắc thiết kế kiểu:

- Nếu cột **`NOT NULL` và hợp đồng thực sự luôn có giá trị**, có thể dùng primitive phù hợp: `int`, `long`, `boolean`. Ví dụ khóa chính `id BIGINT PRIMARY KEY` thường ánh xạ sang `long`.
- Nếu cột **`NULL` được phép và mang nghĩa nghiệp vụ**, dùng wrapper: `Integer`, `Long`, `Boolean`, `Double`, `Float`, v.v.
- Với số tiền hoặc thập phân chính xác, ưu tiên `BigDecimal` thay vì `double` bất kể tính nullable. `BigDecimal` là object, vốn có thể mang Java `null`.
- Với chuỗi, ngày/giờ, object, các getter thích hợp thường đã trả Java `null` khi SQL là `NULL`, nhưng vẫn cần chính sách nghiệp vụ về việc cho phép null.
- Nếu business yêu cầu phân biệt cả *vắng mặt* và *giá trị được mặc định*, mô hình domain nên thể hiện rõ, thay vì thay toàn bộ `NULL` thành một sentinel ngầm như 0 hoặc chuỗi rỗng.

Ví dụ record:

```java
public record Measurement(
    long id,           // id NOT NULL, có thể dùng primitive
    Integer score,     // NULL khác với 0
    Boolean active,    // NULL khác với false
    Long attempts,     // NULL khác với 0L
    String note        // NULL khác với ""
) {}
```

Đây là định nghĩa record Java 17+ không phụ thuộc Spring; nếu đặt thành file public top-level, tên file là `Measurement.java`.

| Cột SQL | Giả định schema | Kiểu Java đề xuất | Lý do |
| --- | --- | --- | --- |
| `id BIGINT PRIMARY KEY` | Không NULL | `long` / `Long` | `long` phù hợp khi chắc chắn đã có ID |
| `score INTEGER NULL` | Có thể NULL | `Integer` | Không đồng nhất "chưa chấm" với 0 |
| `active BOOLEAN NULL` | Có thể NULL | `Boolean` | Diễn đạt true / false / unknown |
| `attempts BIGINT NULL` | Có thể NULL | `Long` | Không đồng nhất "chưa thống kê" với 0 |
| `price DECIMAL(12,2) NULL` | Có thể NULL | `BigDecimal` | Giữ độ chính xác tiền tệ và vắng mặt |
| `note VARCHAR NULL` | Có thể NULL | `String` | Phân biệt Java `null` với chuỗi rỗng |
| `created_at TIMESTAMP NULL` | Có thể NULL | `LocalDateTime` hoặc kiểu thời gian phù hợp | Giữ khả năng vắng mặt; xét múi giờ/dialect |

Chọn wrapper không đồng nghĩa một property **nên luôn được phép null**. Sau khi lấy dữ liệu, service có thể áp ràng buộc và ném lỗi nếu một giá trị thực tế thiếu trái hợp đồng. Nhưng không để JDBC âm thầm chuyển null thành 0/false rồi mới kiểm tra: thông tin đã mất.

## 5. Hai chiến lược lấy kiểu nullable từ ResultSet

### 5.1. Primitive getter + wasNull(): rõ ràng, kiểm soát tốt

```java
static Integer nullableInt(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    int value = rs.getInt(label);
    return rs.wasNull() ? null : value;
}

static Boolean nullableBoolean(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    boolean value = rs.getBoolean(label);
    return rs.wasNull() ? null : value;
}

static Long nullableLong(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    long value = rs.getLong(label);
    return rs.wasNull() ? null : value;
}
```

Đây là các method helper đặt **trong một class Java** có import JDBC tương ứng hoặc dùng tên đầy đủ như trên. Lợi thế: cơ chế rõ ràng, hoạt động theo hợp đồng `getInt`/`getBoolean`/`getLong`/`wasNull` chuẩn, và không phụ thuộc hỗ trợ chuyển đổi `getObject(..., Class)` đặc thù của driver.

Với cột cần nhiều conversion đặc biệt, vẫn phải chọn getter phù hợp với SQL type. `wasNull()` chỉ giải quyết vấn đề vắng mặt, **không sửa được lỗi lấy sai kiểu hoặc tràn số khi ép kiểu**.

### 5.2. Typed getObject(): ngắn hơn khi JDBC driver hỗ trợ conversion

Với JDBC 4.1+, API có overload:

```java
Integer score = rs.getObject("score", Integer.class);
Boolean active = rs.getObject("active", Boolean.class);
Long attempts = rs.getObject("attempts", Long.class);
```

Theo hợp đồng JDBC, khi cột là SQL `NULL`, giá trị object trả về là Java `null`. Không cần `wasNull()` để phân biệt null ở các giá trị kiểu reference này.

**Điều kiện quan trọng:** driver cần hỗ trợ chuyển đổi từ SQL type sang Java type yêu cầu. Một driver có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException` nếu conversion không được hỗ trợ. Kiểm thử trên driver/DBMS thực sự, nhất là với `BOOLEAN`, `UUID`, kiểu ngày/giờ, số không chuẩn hoặc driver cũ. Tránh khẳng định mọi SQL type đều có một chuyển đổi Java cố định.

Nếu muốn tối đa tính tương thích, mẫu `getInt() + wasNull()` vẫn rất rõ ràng. Nếu đội dự án chuẩn hóa một driver hiện đại đã kiểm thử typed `getObject`, cách thứ hai thường gọn hơn.

### 5.3. Các getter trả object vốn xử lý NULL

```java
String note = rs.getString("note");
java.math.BigDecimal amount = rs.getBigDecimal("amount");
java.sql.Timestamp created = rs.getTimestamp("created_at");
```

Với các cột tương ứng, nếu SQL là `NULL`, getter thường trả Java `null` theo JDBC contract. Không cần `wasNull()` chỉ để biết `String` đang null hay không. Tuy nhiên, với SQL number/datetime không khớp kiểu, có thể phải kiểm tra conversion, timezone, độ chính xác hoặc ánh xạ `java.time` phù hợp.

## 6. Một ví dụ Java thuần để hiểu logic wasNull

Giả sử `rs` là một `ResultSet` **đã được di chuyển đến hàng hiện tại** (ví dụ trong vòng `while (rs.next())` của JDBC thuần, hoặc trong callback `RowMapper` do Spring gọi). Đoạn sau thực hiện ánh xạ thủ công:

```java
long id = rs.getLong("id"); // ID NOT NULL
int rawScore = rs.getInt("score");
Integer score = rs.wasNull() ? null : rawScore;

boolean rawActive = rs.getBoolean("active");
Boolean active = rs.wasNull() ? null : rawActive;

long rawAttempts = rs.getLong("attempts");
Long attempts = rs.wasNull() ? null : rawAttempts;

String note = rs.getString("note");

Measurement row = new Measurement(id, score, active, attempts, note);
```

Đây là **mảnh mã bên trong method có biến `ResultSet rs`** và record `Measurement` nêu ở trên; không có `main` độc lập. Hãy chú ý thứ tự từng cặp getter/`wasNull()`.

Nếu dữ liệu SQL của `id=1` như ví dụ, record phải là:

```text
Measurement[id=1, score=null, active=null, attempts=null, note=null]
```

Với `id=2`:

```text
Measurement[id=2, score=0, active=false, attempts=0, note=]
```

`note=` ở cuối phản ánh chuỗi Java rỗng, **không phải** `note=null`. Cả hai chuỗi in ra không tự phân biệt được mọi whitespace đặc biệt, nên trong kiểm thử cần so sánh thực tế bằng `assertEquals("")` và `assertNull(...)`.

### Nếu chỉ cần đánh dấu tính thiếu dữ liệu

Đôi khi ứng dụng không cần giữ số nguyên, mà chỉ cần biết cột có giá trị hay không:

```java
rs.getInt("score");
boolean missingScore = rs.wasNull();
```

Mẫu này hợp lệ nhưng nếu cần sử dụng điểm sau đó, phải lưu giá trị cùng trạng thái null. Không gọi `getInt` lại sau khi đã chuyển qua getter của cột khác rồi cố dựa vào trạng thái `wasNull()` cũ.

## 7. Spring JDBC RowMapper: nơi xử lý nullable cho từng hàng

Trong Spring, `JdbcTemplate.query(sql, rowMapper)` duyệt `ResultSet` và gọi `RowMapper.mapRow(rs, rowNum)` với mỗi hàng. Spring **đã di chuyển con trỏ đến hàng hiện tại trước khi gọi mapper**; bên trong `mapRow` **không gọi `rs.next()`**. `RowMapper` nên là logic ánh xạ thuần, không đóng `ResultSet` hay `Connection`.

Hợp đồng:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
```

Đây là chữ ký **mô tả tối giản** của interface Spring; trong dự án phải import `org.springframework.jdbc.core.RowMapper`, không khai báo lại như trên.

Một mapper đầy đủ:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public final class MeasurementRowMapper implements RowMapper<Measurement> {
    @Override
    public Measurement mapRow(ResultSet rs, int rowNum) throws SQLException {
        long id = rs.getLong("id");

        int rawScore = rs.getInt("score");
        Integer score = rs.wasNull() ? null : rawScore;

        boolean rawActive = rs.getBoolean("active");
        Boolean active = rs.wasNull() ? null : rawActive;

        long rawAttempts = rs.getLong("attempts");
        Long attempts = rs.wasNull() ? null : rawAttempts;

        String note = rs.getString("note");
        return new Measurement(id, score, active, attempts, note);
    }
}
```

Class cần record `Measurement` trong cùng package hoặc import đúng. Nó có thể được tái sử dụng cho nhiều câu query có đủ năm cột/alias. Nếu SQL không chọn cột `attempts` hoặc alias bị đổi, JDBC có thể báo cột không tồn tại; cần kiểm tra danh sách cột ngay trong SQL.

**Vì sao đặt nullable logic ở mapper?** Vì mapper là nơi chuyển trực tiếp SQL representation sang Java representation. Khi mọi query cùng dùng mapper thống nhất, các tầng repository/service không phải đoán liệu `0` có phải SQL NULL đã bị mất.

### Lambda RowMapper và helper

Có thể dùng lambda ngắn gọn:

```java
List<Measurement> all = jdbc.query(
    "SELECT id, score, active, attempts, note FROM measurements ORDER BY id",
    (rs, rowNum) -> {
        int value = rs.getInt("score");
        Integer score = rs.wasNull() ? null : value;

        boolean flag = rs.getBoolean("active");
        Boolean active = rs.wasNull() ? null : flag;

        long attemptsValue = rs.getLong("attempts");
        Long attempts = rs.wasNull() ? null : attemptsValue;

        return new Measurement(
            rs.getLong("id"),
            score,
            active,
            attempts,
            rs.getString("note")
        );
    }
);
```

Đây là **đoạn trong method** có `jdbc` là `JdbcOperations` hoặc `JdbcTemplate` đã inject và record `Measurement` hiện hữu. Cả cách class và lambda đều hợp lệ; với mapper phức tạp, class riêng hoặc các helper `nullableInt/nullableBoolean/nullableLong` thường dễ kiểm tra hơn.

## 8. Ví dụ Spring Boot/H2 có thể chạy: giữ nguyên SQL NULL

Ví dụ thực hành dùng Java 17+, Spring Boot 3.3+, Spring JDBC và H2 in-memory. Mục đích: tạo các giá trị SQL `NULL`/0/false thật và quan sát mapper Java khác nhau. Đây là **một ứng dụng Spring Boot nhiều file**, có thể chạy khi đặt đúng vào một dự án Boot Gradle đã tạo với plugin và dependency management tương ứng.

### 8.1. Dependencies và cấu hình

Trong `build.gradle` đã cấu hình Spring Boot, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Khối trên không phải toàn bộ build script. Hãy dùng Spring Boot plugin tương thích với JDK và các dependency. Với Maven có thể dùng các dependency tương đương.

Tệp **`src/main/resources/application.yml`**:

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:nullable_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

### 8.2. Record biểu diễn nullable

Tệp **`src/main/java/example/Measurement.java`**:

```java
package example;

public record Measurement(
    long id,
    Integer score,
    Boolean active,
    Long attempts,
    String note
) {}
```

### 8.3. Repository và RowMapper

Tệp **`src/main/java/example/MeasurementRepository.java`**:

```java
package example;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class MeasurementRepository {
    private static final RowMapper<Measurement> MAPPER =
        (rs, rowNum) -> new Measurement(
            rs.getLong("id"),
            nullableInt(rs, "score"),
            nullableBoolean(rs, "active"),
            nullableLong(rs, "attempts"),
            rs.getString("note")
        );

    private final JdbcOperations jdbc;

    public MeasurementRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public List<Measurement> findAll() {
        return jdbc.query(
            "SELECT id, score, active, attempts, note " +
            "FROM measurements ORDER BY id",
            MAPPER
        );
    }

    private static Integer nullableInt(ResultSet rs, String col)
            throws SQLException {
        int value = rs.getInt(col);
        return rs.wasNull() ? null : value;
    }

    private static Boolean nullableBoolean(ResultSet rs, String col)
            throws SQLException {
        boolean value = rs.getBoolean(col);
        return rs.wasNull() ? null : value;
    }

    private static Long nullableLong(ResultSet rs, String col)
            throws SQLException {
        long value = rs.getLong(col);
        return rs.wasNull() ? null : value;
    }
}
```

`JdbcOperations` là interface được `JdbcTemplate` hiện thực; Spring Boot có thể tự cấu hình `JdbcTemplate` qua bean `DataSource`. Repository chỉ biết API query và mapper. Các helper không giữ `ResultSet` ra ngoài callback và đều gọi `wasNull()` ngay sau getter.

### 8.4. Khởi tạo dữ liệu và in kết quả

Tệp **`src/main/java/example/NullableDemoApplication.java`**:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class NullableDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(NullableDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, MeasurementRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE measurements (
                    id BIGINT PRIMARY KEY,
                    score INTEGER NULL,
                    active BOOLEAN NULL,
                    attempts BIGINT NULL,
                    note VARCHAR(80) NULL
                )
                """);

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 1L, null, null, null, null);

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 2L, 0, false, 0L, "");

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 3L, 42, true, 123L, "ready");

            repo.findAll().forEach(System.out::println);

            Integer missing = jdbc.queryForObject(
                "SELECT score FROM measurements WHERE id = ?",
                Integer.class, 1L
            );
            System.out.println("scalarNull=" + missing);
        };
    }
}
```

Chạy trong dự án Gradle Spring Boot:

```bash
./gradlew bootRun
```

Với Windows có thể chạy `gradlew.bat bootRun`. Khi H2 in-memory mới được tạo và không có schema/seed script bổ sung, ngoài log của Spring, **những dòng in bởi chương trình** là:

```text
Measurement[id=1, score=null, active=null, attempts=null, note=null]
Measurement[id=2, score=0, active=false, attempts=0, note=]
Measurement[id=3, score=42, active=true, attempts=123, note=ready]
scalarNull=null
```

Vì sao đầu ra đúng?

1. `id=1`: ba getter nguyên thủy trả giá trị mặc định nhưng `wasNull()` ngay sau mỗi getter trả true; mapper chuyển thành `null` trong `Integer`/`Boolean`/`Long`. `getString("note")` trả Java `null`.
2. `id=2`: `wasNull()` false cho `0`, `false`, `0L`; mapper giữ giá trị thật. Chuỗi rỗng được in là `note=`.
3. `id=3`: các giá trị bình thường được giữ nguyên.
4. `ORDER BY id` bảo đảm thứ tự ba hàng theo ID. Nếu bỏ `ORDER BY`, DB không cam kết trả chúng theo thứ tự INSERT.
5. `queryForObject(..., Integer.class, 1L)` gặp **đúng một hàng** có cột `score` bằng SQL `NULL`, nên trả Java `null`. Đây khác với truy vấn trả 0 hàng, khi `queryForObject` ném `EmptyResultDataAccessException`.

Những tệp trên là ứng dụng Spring Boot chạy với JDK 17+ và các Spring dependency đã cấu hình, **không thể dùng `javac` JDK thuần** vì thiếu classpath Spring/H2. Phép bind `null` trong ví dụ dùng `JdbcTemplate` và H2; với driver/SQL type đặc thù, nếu DB không suy ra kiểu từ SQL, có thể phải chỉ định `java.sql.Types` hoặc dùng `SqlParameterValue`.

## 9. Đọc kết quả một cột bằng JdbcTemplate: SQL NULL vẫn khác không có hàng

Giả sử truy vấn một cột:

```java
Integer score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

Với hàng `id=1`: có một hàng, cột `score` là SQL `NULL` nên `score == null`. Nếu truy vấn `id=99` và không có hàng, `queryForObject` **không trả `null` chỉ vì thiếu hàng**; nó ném `EmptyResultDataAccessException` theo hợp đồng đúng một hàng.

So sánh:

| Tình huống | Kết quả |
| --- | --- |
| Một hàng, `score IS NULL` | `Integer score = null` |
| Một hàng, `score = 0` | `Integer score = 0` |
| Không có hàng | `EmptyResultDataAccessException` khi dùng `queryForObject` |
| Nhiều hơn một hàng | `IncorrectResultSizeDataAccessException` |
| `SELECT COUNT(*)` không nhóm và không hàng phù hợp | Một hàng chứa `0` |

Với một property nullable, **không dùng primitive Java ở phía nhận giá trị scalar**:

```java
int score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

Ở đây Java phải *auto-unbox* `Integer` thành `int`. Nếu Spring trả `null` cho SQL `NULL`, Java ném `NullPointerException`. Đây là lỗi Java **sau khi lấy kết quả**, khác với việc `rs.getInt` tự trả 0 khi SQL NULL.

Sửa:

```java
Integer score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

Hoặc nếu API nghiệp vụ thực sự cần một số nguyên không-null, phải chọn chính sách có chủ đích: từ chối null, dùng mặc định được quy định, hoặc thay đổi schema cho `NOT NULL`.

## 10. Tự động ánh xạ: BeanPropertyRowMapper và DataClassRowMapper

Không phải mọi mapper đều được viết bằng tay. Spring JDBC có `BeanPropertyRowMapper` cho JavaBean có constructor không tham số/setter và `DataClassRowMapper` cho những kiểu dựa trên constructor, bao gồm Java record.

### BeanPropertyRowMapper + primitive property

Ví dụ một bean với field primitive:

```java
public class PrimitiveScoreBean {
    private int score;

    public PrimitiveScoreBean() {}

    public int getScore() {
        return score;
    }

    public void setScore(int score) {
        this.score = score;
    }
}
```

Nếu database trả SQL `NULL` cho `score`, Spring `BeanPropertyRowMapper` **mặc định cố gán null vào property primitive và có thể phát sinh `TypeMismatchException`**, thay vì luôn coi null là số 0 an toàn. Vì đó là điều không thể biểu diễn chính xác trong `int`.

Spring cho phép:

```java
BeanPropertyRowMapper<PrimitiveScoreBean> mapper =
    new BeanPropertyRowMapper<>(PrimitiveScoreBean.class);
mapper.setPrimitivesDefaultedForNullValue(true);
```

Đây là **đoạn code trong method** có import `org.springframework.jdbc.core.BeanPropertyRowMapper` và bean class đã định nghĩa. Thiết lập trên yêu cầu mapper bỏ qua thao tác gán `null` cho primitive, giữ nguyên giá trị hiện tại (thường mặc định là `0`). Nhưng **nó làm mất phân biệt SQL NULL và 0**; nếu bạn dùng bean đó để cập nhật database, có nguy cơ vô tình ghi `0` thay vì NULL. Vì vậy không bật cờ này chỉ để "hết lỗi" mà chưa xem hợp đồng nghiệp vụ.

Đối với cột nullable, sửa mô hình theo hướng:

```java
public class NullableScoreBean {
    private Integer score;

    public NullableScoreBean() {}

    public Integer getScore() {
        return score;
    }

    public void setScore(Integer score) {
        this.score = score;
    }
}
```

Với `Integer`, null là giá trị Java hợp lệ và ý nghĩa DB được giữ nguyên.

### DataClassRowMapper và Java record

Java record có constructor gán đủ component. Khi cột nullable, component phải có kiểu nullable nếu muốn giữ SQL `NULL`:

```java
public record ScoreView(long id, Integer score, Boolean active) {}
```

`DataClassRowMapper` có thể ánh xạ record theo constructor nếu tên cột/alias tương ứng và driver hỗ trợ conversion phù hợp. Mẫu dùng trong method với `jdbc` đã cấu hình:

```java
var mapper = new org.springframework.jdbc.core.DataClassRowMapper<>(
    ScoreView.class
);

var rows = jdbc.query(
    "SELECT id, score, active FROM measurements ORDER BY id",
    mapper
);
```

Đây là mảnh minh họa cho Spring JDBC 6.x, **không phải chương trình đầy đủ**. Dùng `Integer` và `Boolean` thay vì `int`/`boolean` giúp record nhận được trường hợp SQL NULL; constructor không thể nhận null để gán cho primitive tương ứng.

Với mapper tự động, luôn kiểm tra tên cột và alias, kiểu dữ liệu, khả năng chuyển đổi của driver và nullability trong integration test. Nếu mapping đòi hỏi logic riêng hoặc conversion phức tạp, custom `RowMapper` có thể minh bạch hơn.

## 11. SQL NULL, điều kiện lọc và phép tổng hợp

### 11.1. SQL NULL không bằng 0 hoặc FALSE

Trong SQL, so sánh `score = NULL` không đúng để tìm cột null vì biểu thức so sánh với `NULL` thường có giá trị logic `UNKNOWN`. Hãy dùng:

```sql
SELECT id FROM measurements WHERE score IS NULL;
```

Để tìm số 0 thật:

```sql
SELECT id FROM measurements WHERE score = 0;
```

Trên dữ liệu mẫu, điều kiện `score IS NULL` tìm `id=1`; điều kiện `score = 0` tìm `id=2`. Hai tập dữ liệu khác nhau về ý nghĩa. Tương tự, `active IS NULL` khác với `active = FALSE`.

### 11.2. COUNT(*) khác COUNT(cột)

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(score) AS scored_rows
FROM measurements;
```

Với ba hàng mẫu:

- `COUNT(*) = 3` vì đếm tất cả hàng.
- `COUNT(score) = 2` vì bỏ qua các giá trị score SQL NULL.

Nếu Java đã biến SQL NULL thành 0 khi mapping, rồi tính trung bình ở Java, kết quả có thể sai vì một hàng chưa chấm điểm bị tính như điểm 0. Cần xác định quy tắc: bỏ qua null, trả "không đủ dữ liệu" hay mặc định có chủ đích.

### 11.3. COALESCE là quyết định nghiệp vụ, không phải sửa lỗi mapping mặc định

```sql
SELECT id, COALESCE(score, 0) AS score
FROM measurements;
```

`COALESCE(score, 0)` cố ý thay SQL NULL bằng 0 trong **kết quả truy vấn**. Đây là một chính sách hợp lệ **nếu nghiệp vụ thực sự coi thiếu điểm là 0**, ví dụ một thống kê có quy ước rõ ràng. Nó không cho phép người đọc phân biệt 0 thật và null ban đầu; không dùng tùy tiện để né `wasNull()`.

Nếu cần cả giá trị với default và cờ gốc, có thể chọn:

```sql
SELECT id,
       score,
       (score IS NULL) AS score_missing
FROM measurements;
```

Với DBMS hỗ trợ biểu thức boolean ở SELECT (như H2/PostgreSQL), cột `score_missing` biểu diễn trạng thái để downstream xử lý. Cần cân nhắc dialect SQL nếu DBMS có representation boolean khác.

## 12. Outer join có thể tạo NULL ngay cả khi cột gốc NOT NULL

Tính nullable không chỉ đến từ định nghĩa `NULL` trong cột gốc. Ví dụ bảng `customers` và `orders`:

```sql
SELECT c.id AS customer_id,
       o.id AS order_id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Cột `orders.id` có thể được khai báo `BIGINT PRIMARY KEY NOT NULL`, nhưng với khách hàng **không có order khớp**, kết quả `LEFT JOIN` vẫn có `order_id = NULL` trong hàng đã join. Vì vậy:

```java
long rawOrderId = rs.getLong("order_id");
Long orderId = rs.wasNull() ? null : rawOrderId;
```

mới giữ được ý nghĩa "không có order". Nếu dùng `long orderId = rs.getLong("order_id")` và coi `0` là một order ID có thật, ứng dụng có thể tạo reference sai.

**Không chỉ nhìn schema của bảng bên phải để suy ra khả năng null của projection.** Quan sát cả outer join, `CASE`, biểu thức, aggregate và alias. `ResultSetMetaData.isNullable(...)` có thể giúp kiểm tra nhưng driver có thể trả kết quả "unknown"; vẫn phải thiết kế theo hợp đồng SQL và kiểm thử.

## 13. Khi nào nên dùng Optional?

`Optional<T>` diễn đạt sự tồn tại của **giá trị** ở một API Java, nhưng không nên tự động bọc mọi property trong domain record.

Có hai vấn đề khác nhau:

1. **Không có hàng** khi tìm theo ID: repository có thể trả `Optional<Measurement>`.
2. **Có hàng nhưng một cột nullable**: object `Measurement` có trường `Integer score` hoặc một value object đại diện cho trạng thái điểm.

Ví dụ contract:

```java
public Optional<Measurement> findById(long id) {
    List<Measurement> rows = jdbc.query(
        "SELECT id, score, active, attempts, note " +
        "FROM measurements WHERE id = ?",
        MAPPER,
        id
    );
    return org.springframework.dao.support.DataAccessUtils.optionalResult(rows);
}
```

Đây là method trong repository có `jdbc`, `MAPPER` và import `List`/`Optional`. `DataAccessUtils.optionalResult` có trong Spring Framework 6.1+. Kết quả `Optional.empty()` nghĩa là **không tìm thấy hàng**, còn `Optional.of(measurement)` có thể chứa `measurement.score() == null`. Điều này tránh lẫn "thiếu bản ghi" với "thiếu giá trị thuộc tính".

Nếu số liệu của một property cần ba hoặc nhiều trạng thái nghiệp vụ (ví dụ "chưa đo", "không áp dụng", "đã đo"), Java `null` đôi khi không đủ diễn đạt; cân nhắc enum hoặc kiểu kết quả có trạng thái rõ ràng thay vì thêm nhiều sentinel số.

## 14. Binding tham số nullable khi GHI dữ liệu

Bài này chủ yếu nói về **đọc `ResultSet`**, nhưng khi ghi lại dữ liệu phải giữ cùng ranh giới ý nghĩa:

- `PreparedStatement.setInt(index, 0)` ghi số 0, **không phải SQL NULL**.
- Muốn ghi SQL NULL, có thể dùng `setNull(index, java.sql.Types.INTEGER)`.
- Trong Spring JDBC, với tham số nullable và driver cần biết SQL type, dùng `SqlParameterValue` hoặc overload nhận `argTypes`, thay vì giả định mọi driver tự xác định kiểu của giá trị Java `null`.

Ví dụ JDBC thuần với statement đã tạo và cột `score INTEGER NULL`:

```java
if (score == null) {
    statement.setNull(1, java.sql.Types.INTEGER);
} else {
    statement.setInt(1, score);
}
```

Đây là **đoạn trong một method**, có `PreparedStatement statement` và `Integer score` đã được cung cấp. Mục đích là giữ được phân biệt "chưa có điểm" và "0 điểm" khi ghi, tương ứng với cách `wasNull()` giữ phân biệt đó khi đọc.

`JdbcTemplate.update` với tham số bind có thể xử lý nhiều trường hợp null tự động, nhưng nếu driver không suy luận được SQL type, hãy chỉ định kiểu thay vì đổi null thành 0 để tránh lỗi.

## 15. Kiểm thử đúng ba trạng thái NULL / 0 / giá trị thường

Kiểm thử bằng **ít nhất ba hàng** như phần mở đầu. Chỉ thử một giá trị 42 không thể phát hiện lỗi đọc SQL NULL thành 0. Một integration test dùng đúng DB driver mà ứng dụng sẽ dùng là bằng chứng mạnh nhất.

Giả sử dự án Spring Boot/H2 ở mục 8 có thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Trong một dự án Spring Boot 3.3 với `@JdbcTest` có thể tạo test cho repository. Tệp **`src/test/java/example/MeasurementRepositoryTest.java`**:

```java
package example;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(MeasurementRepository.class)
class MeasurementRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    MeasurementRepository repository;

    @BeforeEach
    void seed() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id BIGINT PRIMARY KEY,
                score INTEGER NULL,
                active BOOLEAN NULL,
                attempts BIGINT NULL,
                note VARCHAR(80) NULL
            )
            """);
        jdbc.update("DELETE FROM measurements");
        jdbc.update("""
            INSERT INTO measurements
                (id, score, active, attempts, note)
            VALUES
                (1, NULL, NULL, NULL, NULL),
                (2, 0, FALSE, 0, ''),
                (3, 42, TRUE, 123, 'ready')
            """);
    }

    @Test
    void nullAndRealZeroRemainDifferent() {
        List<Measurement> rows = repository.findAll();
        assertEquals(3, rows.size());

        Measurement unknown = rows.get(0);
        Measurement zero = rows.get(1);
        Measurement regular = rows.get(2);

        assertNull(unknown.score());
        assertNull(unknown.active());
        assertNull(unknown.attempts());
        assertNull(unknown.note());

        assertEquals(Integer.valueOf(0), zero.score());
        assertEquals(Boolean.FALSE, zero.active());
        assertEquals(Long.valueOf(0), zero.attempts());
        assertEquals("", zero.note());

        assertEquals(Integer.valueOf(42), regular.score());
        assertEquals(Boolean.TRUE, regular.active());
        assertEquals(Long.valueOf(123), regular.attempts());
        assertEquals("ready", regular.note());
    }

    @Test
    void singleColumnNullableResultIsNotMissingRow() {
        Integer score = jdbc.queryForObject(
            "SELECT score FROM measurements WHERE id = ?",
            Integer.class, 1L
        );
        assertNull(score);
    }
}
```

Chạy:

```bash
./gradlew test
```

Với Spring Boot 3.3/JUnit 5/H2 tương ứng và schema không bị xung đột, dự kiến có **2 test pass**. `@JdbcTest` thường cấu hình embedded database và transaction rollback sau mỗi test. Để kết luận mapper hoạt động trên PostgreSQL hoặc DBMS production, cần thêm integration test với đúng JDBC driver/DB thật hoặc Testcontainers; H2 không tái hiện mọi conversion và dialect.

Một kiểm tra khác rất quan trọng là **test hành vi bị lỗi**: nếu thay `nullableInt` bằng `rs.getInt` rồi gán vào `Integer` qua autoboxing, bài test `assertNull(unknown.score())` sẽ thất bại vì nhận `0`. Nhờ đó test không chỉ kiểm tra dữ liệu bình thường mà còn bảo vệ ý nghĩa null.

### Nếu dùng mock ResultSet

Ở unit test cho helper, thứ tự lời gọi phải là:

```text
getInt("score") -> wasNull()
getBoolean("active") -> wasNull()
getLong("attempts") -> wasNull()
```

Đừng stub `wasNull()` thành một giá trị cố định cho mọi cột rồi kết luận mapper đúng. Vì `wasNull()` phụ thuộc **getter ngay trước đó**, mock cần mô phỏng trạng thái tương ứng hoặc nên dùng integration test với driver thật để phát hiện việc gọi sai thứ tự.

## 16. Những lỗi thường gặp

| Sai lầm | Hệ quả và cách sửa |
| --- | --- |
| Ánh xạ `NULL` bằng `rs.getInt` rồi gán trực tiếp vào `Integer` | Autoboxing biến `0` thành `Integer.valueOf(0)`, mất NULL; dùng `wasNull` hoặc typed `getObject`. |
| Gọi `wasNull` sau khi đã đọc cột khác | Trạng thái phản ánh cột vừa đọc gần nhất; gọi ngay sau getter cần kiểm tra. |
| Cho rằng `getBoolean` trả false nghĩa là DB lưu FALSE | SQL NULL cũng trả false; kiểm tra `wasNull`. |
| Thay SQL NULL thành 0/false cho tất cả cột | Có thể làm sai phân loại trạng thái, báo cáo, update; chỉ mặc định khi nghiệp vụ xác định rõ. |
| Dùng primitive field cho cột nullable | Không giữ được null; chọn wrapper hoặc thiết kế domain có trạng thái riêng. |
| Unbox `Integer` nullable sang `int` mà không kiểm tra | Có thể `NullPointerException`; xử lý null trước khi unbox. |
| Tưởng SQL NULL tương đương không có hàng | Một hàng có cột NULL vẫn là một hàng; phân biệt với `EmptyResultDataAccessException`. |
| Bật `primitivesDefaultedForNullValue(true)` để hết lỗi mà không hiểu ý nghĩa | Giá trị null bị giữ ở default primitive, có thể ghi ngược về DB sai. |
| Dùng `score = NULL` để tìm giá trị chưa có | So sánh SQL NULL dùng `IS NULL`, không dùng `= NULL`. |
| Dùng `ResultSetMetaData.isNullable` như bảo đảm tuyệt đối cho mọi projection | Outer join và biểu thức có thể tạo NULL; driver có thể báo unknown. |
| Cho rằng typed `getObject(label, Integer.class)` được mọi driver hỗ trợ cho mọi type | Conversion phụ thuộc driver/DB; cần kiểm thử hoặc fallback getter + wasNull. |
| Đoán null bằng `score == 0` hoặc `active == false` | Đồng nhất giá trị thật với sự vắng mặt; đọc trạng thái null rõ ràng. |
| Chỉ test giá trị khác 0 | Không phát hiện bug null-to-zero; test NULL, 0/false và giá trị bình thường. |
| Dùng `SUM`/`AVG` sau khi ép null thành 0 mà không xét nghiệp vụ | Có thể làm sai mẫu số/trung bình; giữ SQL NULL hoặc nêu quy ước tính toán rõ ràng. |

## 17. Tự kiểm tra

**Câu 1.** Một hàng SQL có `score = NULL`. Sau `int score = rs.getInt("score")`, biến `score` thường bằng gì?

**Đáp án:** `0` theo hợp đồng JDBC, nhưng đó chỉ là giá trị của primitive getter. Gọi `rs.wasNull()` **ngay sau** sẽ trả `true` và cho biết SQL thực tế là NULL.

**Câu 2.** Một hàng SQL có `score = 0`. Vì sao không được dùng `score == 0` để kết luận dữ liệu bị thiếu?

**Đáp án:** Vì `0` là giá trị có thật và `getInt` cũng trả 0 cho SQL NULL. Chỉ `wasNull()` hoặc một getter trả object nullable mới phân biệt được.

**Câu 3.** Nếu đọc `getInt("score")` rồi `getString("note")` và cuối cùng `wasNull()`, `wasNull()` kiểm tra cột nào?

**Đáp án:** `note`, vì đó là getter gần nhất.

**Câu 4.** Cột `active BOOLEAN NULL` nên dùng Java `boolean` hay `Boolean` nếu trạng thái chưa xác định có nghĩa?

**Đáp án:** `Boolean`. Nó biểu diễn true, false và null. Nếu dùng `getBoolean`, phải gọi `wasNull()` để biết khi nào ánh xạ thành Java null.

**Câu 5.** `JdbcTemplate.queryForObject(sql, Integer.class)` nhận đúng một hàng nhưng cột SQL NULL. Kết quả là gì?

**Đáp án:** Có thể là Java `null`. Nếu query không có hàng thì lại là `EmptyResultDataAccessException`. Phải phân biệt số lượng hàng và giá trị của cột.

**Câu 6.** Vì sao `Integer x = rs.getInt("score")` vẫn có lỗi?

**Đáp án:** Vì Java autoboxing giá trị `int` thành `Integer` **sau khi getter đã biến SQL NULL thành 0**. Wrapper ở phía nhận không thể khôi phục thông tin đã bị mất.

**Câu 7.** `LEFT JOIN` có thể tạo `NULL` ở cột khóa chính `NOT NULL` của bảng bên phải không?

**Đáp án:** Có. Khi không có hàng khớp, kết quả join có các cột bên phải là NULL. Projection `order_id` cần được ánh xạ nullable.

**Câu 8.** Nếu dùng `BeanPropertyRowMapper` và cột SQL NULL được gán vào property `int`, nên sửa thế nào?

**Đáp án:** Ưu tiên đổi property thành `Integer` nếu null có ý nghĩa. Cờ `primitivesDefaultedForNullValue` chỉ hợp lệ khi chấp nhận đánh mất phân biệt SQL NULL và giá trị primitive mặc định.

## Tài liệu tham khảo

- [Java SE 21 — `ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html): hợp đồng `getInt`, `getBoolean`, `getObject` và `wasNull()`.
- [Spring Framework 6.2 — `RowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/RowMapper.html): nguyên tắc map từng hàng, `SQLException` và vị trí con trỏ `ResultSet`.
- [Spring Framework — `JdbcTemplate`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): cơ chế query, callback và tài nguyên JDBC.
- [Spring Framework — `BeanPropertyRowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html): kiểu primitive/nullable, `primitivesDefaultedForNullValue`.
- [Spring Framework — `DataClassRowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html): mapping constructor/Java record.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): callback `RowMapper`, dùng `JdbcTemplate` và khai báo truy vấn.

**Ghi nhớ:** SQL `NULL` khác với `0`, `false` và chuỗi rỗng. Khi cột có thể NULL, **chọn Java type giữ được null** và **gọi `wasNull()` ngay sau primitive getter** nếu sử dụng `getInt/getLong/getBoolean/...`. Hãy kiểm tra cả trường hợp thiếu hàng, giá trị NULL và giá trị 0 thật trong test để không làm sai thông tin trong tầng truy cập dữ liệu.