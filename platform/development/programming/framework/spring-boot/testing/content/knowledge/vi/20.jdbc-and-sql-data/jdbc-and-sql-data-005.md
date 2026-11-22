# Kiểm tra row mapping, giá trị null và chuyển đổi kiểu trong Spring JDBC

## 1. Mục tiêu và vấn đề thường gặp

Trong một ứng dụng dùng JDBC, câu SELECT có thể đúng, số lượng hàng trả về có thể đúng, nhưng đối tượng Java vẫn mang dữ liệu sai. Chẳng hạn, cột INTEGER là **SQL NULL** lại xuất hiện dưới dạng **0**, cột BOOLEAN chưa xác định lại thành **false**, số tiền DECIMAL bị làm tròn qua double, hoặc mã trạng thái VARCHAR bị gán nhầm enum. Những lỗi này nguy hiểm vì code thường vẫn chạy mà không ném exception.

Trong Spring JDBC, **RowMapper<T>** đảm nhiệm việc chuyển **một hàng ResultSet đang được trỏ tới** thành object Java. **JdbcTemplate** thực hiện PreparedStatement, gọi JDBC driver, di chuyển ResultSet tới từng row và quản lý resource lifecycle. Vì vậy test của lớp row mapping cần chứng minh những điều **từ dữ liệu SQL đến Java domain**, không chỉ chứng minh rằng có một object khác null.

Sau bài học bạn sẽ:

- Hiểu hợp đồng **RowMapper.mapRow(ResultSet, rowNum)**, column label và phạm vi trách nhiệm của JdbcTemplate.
- Phân biệt **không có row** với **row có SQL NULL**.
- Hiểu **ResultSet.getInt/getBoolean trả 0/false khi SQL NULL**, và lý do phải gọi **wasNull() ngay sau getter tương ứng**.
- Ánh xạ BIGINT, nullable INTEGER/BOOLEAN, DECIMAL(12,2), DATE và VARCHAR status code sang Java 17.
- Dùng **Integer/Boolean** khi cần giữ ba trạng thái NULL, 0/FALSE và giá trị thông thường.
- Giữ độ chính xác bằng **BigDecimal**, kiểm null trước khi chuyển **java.sql.Date → LocalDate**, và dùng **Locale.ROOT** khi chuẩn hóa enum.
- Kiểm tra SQL aliases, row count, `query` so với `queryForObject` và lỗi dữ liệu invalid.
- Viết project Java 17/Spring Boot **3.3.5**, Gradle, embedded H2 với **@JdbcTest, schema.sql/data.sql, JdbcTemplate và 12 JUnit Jupiter tests**.
- Phân biệt lỗi xảy ra từ JDBC/SQLException với **IllegalArgumentException** do converter tự ném.
- Biết khi nào test H2 là đủ và khi nào cần JDBC driver production với Testcontainers.

**Ngữ cảnh:** Bài thuộc JDBC và dữ liệu SQL, không phải Spring Data JPA/Hibernate hay R2DBC reactive. Bài không cần HTTP server, Spring MVC hoặc Spring Security để xác minh bản chất RowMapper. Các API tương ứng với Spring Framework 6.1.x do Spring Boot 3.3 quản lý.

## 2. RowMapper vận hành ở đâu?

Một lần gọi repository tới JdbcTemplate có thể được hình dung như sau:

~~~text
Repository
  |
  | jdbcTemplate.query(sql, rowMapper, args...)
  v
JdbcTemplate
  +-- Mở hoặc lấy JDBC Connection
  +-- Tạo PreparedStatement, bind tham số
  +-- Driver thực hiện SELECT -> ResultSet
  +-- while (resultSet.next()):
  |      rowMapper.mapRow(rs, rowNum)
  |      -> CustomerView
  +-- Gom danh sách các kết quả
  +-- Đóng ResultSet/Statement theo vòng đời JDBC
  v
List<CustomerView>
~~~

Chữ ký nền tảng:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Đây là **chữ ký rút gọn để giải thích**, không phải tệp Java độc lập. Những quy tắc quan trọng:

1. Khi `mapRow` được gọi, `ResultSet` **đã đứng tại row cần đọc**. Không gọi `rs.next()` trong mapper, vì JdbcTemplate đã di chuyển con trỏ.
2. `ResultSet` getter dùng column index **1-based** nếu gọi `getString(1)`, nhưng `rowNum` của Spring **0-based** trong result set. Không dùng rowNum làm khóa ID.
3. Các getter nhận String như `rs.getString("full_name")` truy cập **column label**. Nếu SELECT dùng `AS display_name`, label là `display_name`.
4. RowMapper xử lý **một row**, không phải toàn bộ List, cũng không nên tự query thêm một lần cho mỗi row (tránh N+1).
5. JDBC resource closing, query exception translation và transaction boundaries do JdbcTemplate và Spring quản lý. Mapper không đóng connection/result set.
6. JDBC getter có thể ném `SQLException`; khi thực thi trong JdbcTemplate, lỗi thường được chuyển thành một Spring `DataAccessException`. Nhưng lỗi conversion do bạn chủ động ném như `IllegalArgumentException` không tự có cùng exception type.

**Lỗi rất thực tế với JOIN:** SELECT * từ hai bảng đều có cột id có thể làm mapper đọc sai id. Nên SELECT rõ từng column và đặt alias như `customer_id`, `order_id`; sau đó test đúng labels.

## 3. SQL NULL, Java null, 0, FALSE và chuỗi rỗng

SQL NULL không đồng nghĩa với 0, FALSE, String rỗng hoặc ngày mặc định. Đó là các trạng thái khác nhau, và mapping phải phản ánh nullability cũng như ý nghĩa domain.

| Kiểu SQL | JDBC getter | Khi SQL NULL | Kiểu Java đề xuất |
|---|---|---|---|
| INTEGER nullable | getInt | Trả **0**; `wasNull()` phân biệt | **Integer** |
| BOOLEAN nullable | getBoolean | Trả **false**; `wasNull()` phân biệt | **Boolean** |
| BIGINT NOT NULL | getLong | Schema không cho NULL | **long** |
| VARCHAR nullable | getString | Trả Java null | String |
| DECIMAL nullable | getBigDecimal | Trả Java null | BigDecimal |
| DATE nullable | getDate | Trả Java null | LocalDate sau khi kiểm null |
| TIMESTAMP nullable | getTimestamp | Trả Java null | Kiểu thời gian theo contract |
| Một cột bất kỳ | getObject | SQL NULL thường → Java null | Kiểu phụ thuộc driver |

### 3.1. Getter primitive tự mất thông tin nếu không kiểm wasNull

**Sai cho INTEGER nullable:**

~~~java
Integer points = rs.getInt("reward_points");
~~~

Vì `getInt` trả primitive int, SQL NULL đã biến thành 0 trước bước autoboxing thành Integer. Việc đổi tên biến sang Integer không khôi phục thông tin đã mất.

**Đúng:**

~~~java
int rawPoints = rs.getInt("reward_points");
Integer points = rs.wasNull() ? null : rawPoints;
~~~

**Tương tự với BOOLEAN nullable:**

~~~java
boolean rawVerified = rs.getBoolean("verified");
Boolean verified = rs.wasNull() ? null : rawVerified;
~~~

Khi verified là SQL NULL, Java Boolean được gán null. Khi SQL FALSE, `rs.wasNull()` là false và Java Boolean là Boolean.FALSE. Khi TRUE thì Java Boolean.TRUE.

### 3.2. wasNull chỉ theo dõi getter gần nhất

Một lỗi tinh vi là đọc một cột khác trước khi gọi `wasNull()`:

~~~java
// Sai: getter id đã thay đổi trạng thái lần đọc gần nhất.
int raw = rs.getInt("reward_points");  // SQL NULL -> 0
long id = rs.getLong("id");            // BIGINT NOT NULL
Integer points = rs.wasNull() ? null : raw;

// Đúng:
int rawCorrect = rs.getInt("reward_points");
Integer pointsCorrect = rs.wasNull() ? null : rawCorrect;
long idCorrect = rs.getLong("id");
~~~

Các snippets trên thuộc phương thức có ResultSet rs, không phải file Java riêng. **Không đặt một câu `rs.wasNull()` duy nhất ở cuối mapRow**: khi đó nó mô tả cột cuối cùng được đọc, không mô tả tất cả các cột nullable trước đó.

### 3.3. Có nên dùng ResultSet.getObject(..., Integer.class)?

JDBC có getter `getObject(String, Class<T>)` và `getObject(String)`. SQL NULL được biểu diễn Java null; với driver hỗ trợ, typed getObject có thể giúp mapping wrapper ngắn hơn. Nhưng **khả năng chuyển kiểu phụ thuộc driver và SQL type**. H2, PostgreSQL, MySQL, Oracle và SQL Server không nhất thiết hỗ trợ y hệt cho BOOLEAN, UUID, JSON, ARRAY hoặc timezone.

Trong ví dụ chính, dùng **getInt/wasNull và getBoolean/wasNull** để minh họa quy tắc được đặc tả bởi `java.sql.ResultSet` và test trực tiếp bằng H2.

### 3.4. Row vắng mặt khác row có cột null

Câu SELECT theo ID có thể:
- Không trả row: `List` rỗng, hoặc repository trả `Optional.empty()`.
- Trả một row, trong đó reward_points/verified/credit_limit là SQL NULL: repository trả **Optional chứa object**, nhưng các trường đó là Java null.
- Trả một row có reward_points=0 và verified=FALSE: object chứa Integer 0 và Boolean.FALSE, khác null.

Đừng trả Optional.empty chỉ vì vài columns null. Đó là phép gộp sai giữa hai khái niệm **cardinality** và **nullability**.

## 4. Chuyển kiểu cần chính xác, rõ ràng

### 4.1. BIGINT, INTEGER và narrowing

SQL BIGINT thường nên dùng Java long; INTEGER thường dùng int/Integer tùy nullability. Nếu phải thu hẹp long sang int, Java cast thông thường có thể overflow âm thầm:

~~~java
long largeId = 3_000_000_000L;
int lost = (int) largeId; // Không còn giá trị gốc.

// Math.toIntExact(largeId) ném ArithmeticException,
// phù hợp nếu contract yêu cầu conversion phải chính xác.
~~~

Với BigDecimal sang long/int, các method `longValue()` và `intValue()` có thể cắt phần thập phân. Nếu nghiệp vụ không chấp nhận việc đó, dùng **longValueExact/intValueExact** để báo lỗi khi dữ liệu không biểu diễn chính xác được.

### 4.2. DECIMAL, NUMERIC và BigDecimal

Với SQL `DECIMAL(12,2)` dùng cho tiền hoặc hạn mức, ưu tiên **BigDecimal**:

~~~java
BigDecimal creditLimit = rs.getBigDecimal("credit_limit");
~~~

- SQL NULL → Java null.
- SQL 0.00 → BigDecimal có giá trị 0.00, **không phải null**.
- SQL 1234.50 → giá trị thập phân được giữ chính xác theo cột.
- Không đọc bằng getDouble rồi `new BigDecimal(double)`: nhị phân dấu phẩy động có thể không biểu diễn chính xác 0.1 và các số thập phân khác.

**BigDecimal.equals so cả value và scale.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false. Trong ví dụ H2 DECIMAL(12,2), assertion bằng BigDecimal("1234.50") kiểm cả scale. Nếu business chỉ đòi numeric equality, dùng `compareTo(...) == 0` hoặc AssertJ `isEqualByComparingTo`; nếu scale là contract, kiểm scale cố định.

### 4.3. DATE, TIMESTAMP và timezone

SQL DATE có nghĩa ngày lịch không kèm giờ. Mapping phổ biến:

~~~java
java.sql.Date sqlDate = rs.getDate("last_contact_date");
LocalDate lastContact =
        sqlDate == null ? null : sqlDate.toLocalDate();
~~~

Phải kiểm SQL NULL trước khi gọi toLocalDate. Nếu không, test nullable date sẽ ném NullPointerException. Một số JDBC 4.2 drivers hỗ trợ `getObject("last_contact_date", LocalDate.class)`; vẫn nên test trên driver thật.

**Không dùng quy tắc này tùy tiện cho TIMESTAMP WITH TIME ZONE.** DATE, TIMESTAMP WITHOUT TIME ZONE và TIMESTAMP WITH TIME ZONE có semantics khác nhau. Khi cần Instant hoặc OffsetDateTime, xác định UTC/timezone policy và test daylight-saving/timezone boundary; đừng vô thức dùng system default timezone của máy CI.

### 4.4. VARCHAR trạng thái → enum cần normalization policy

Schema trong bài lưu state_code là VARCHAR NOT NULL, nhưng fixture có cả "active" và "ACTIVE". Java Enum.valueOf phân biệt chữ hoa/chữ thường, nên bài dùng:

~~~java
String rawCode = rs.getString("state_code");
CustomerStatus status = CustomerStatus.valueOf(
        rawCode.trim().toUpperCase(Locale.ROOT));
~~~

**Locale.ROOT** giữ quy tắc chuyển chữ cho mã kỹ thuật không phụ thuộc locale máy chạy. Trường hợp:
- "active" → ACTIVE.
- "PAUSED" → PAUSED.
- "not-a-status" → IllegalArgumentException.

Không âm thầm biến mọi enum code lạ thành ACTIVE hoặc PAUSED để tránh lỗi. Nếu domain có trạng thái UNKNOWN, định nghĩa nó và test theo contract; nếu mã lạ là dữ liệu hỏng, fail rõ và ghi nhận để sửa data tốt hơn.

## 5. Thiết kế cấp độ test phù hợp

| Cấp độ | Driver/SQL thật? | Điều chứng minh |
|---|---|---|
| Unit test custom RowMapper với mocked ResultSet | Không | Thứ tự getter/wasNull và nhánh logic Java |
| **@JdbcTest + H2** | **Có** | SQL, ResultSet, column labels, null/type conversion, JDBC behavior |
| @JdbcTest + production DB Testcontainers | Có, gần production | SQL vendor/type/driver-specific conversion |
| @SpringBootTest + DataSource | Có | Full app context, service/repository wiring |
| HTTP integration phía trên repository | Có nếu được cấu hình | Thêm HTTP/security/JSON, không thay test JDBC |

Spring Boot 3.3 **@JdbcTest** tự cấu hình embedded database và JdbcTemplate nếu có H2 trên test classpath. Nó mặc định transactional và rollback test-managed changes sau mỗi test. Nó **không tự component-scan mọi @Repository hay @Service**, nên test chỉ import repository thực sự cần.

Một unit test chỉ stub ResultSet có thể khiến getter trả những thứ được lập trình sẵn mà không chứng minh JDBC SQL/type behavior. Vì vậy khi đề bài là row mapping/NULL/type conversion, **@JdbcTest với database thật** là lớp test quan trọng.

## 6. Ví dụ hoàn chỉnh Spring Boot 3.3.5 / Java 17 / H2

Dữ liệu bảng customer_profiles có các kiểu:

| Cột | SQL | Java |
|---|---|---|
| id | BIGINT PRIMARY KEY | long |
| full_name | VARCHAR(80) NOT NULL | String |
| reward_points | INTEGER NULL | Integer |
| verified | BOOLEAN NULL | Boolean |
| credit_limit | DECIMAL(12,2) NULL | BigDecimal |
| last_contact_date | DATE NULL | LocalDate |
| state_code | VARCHAR(20) NOT NULL | CustomerStatus |

Fixture sẽ có hàng với 0/FALSE, hàng toàn nullable columns NULL, hàng TRUE/0.00, hàng enum code không hợp lệ. Điều đó buộc mapper chứng minh phân biệt đúng chứ không chỉ trả happy-path object.

### 6.1. Cấu trúc dự án

~~~text
settings.gradle
build.gradle
src/main/java/demo/jdbc/JdbcMappingApplication.java
src/main/java/demo/jdbc/CustomerStatus.java
src/main/java/demo/jdbc/CustomerView.java
src/main/java/demo/jdbc/CustomerRowMapper.java
src/main/java/demo/jdbc/CustomerRepository.java
src/test/resources/schema.sql
src/test/resources/data.sql
src/test/java/demo/jdbc/CustomerJdbcMappingTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jdbc-row-mapping-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích dependency:** starter-jdbc cung cấp Spring JDBC/JdbcTemplate, H2 là embedded JDBC database nằm trên runtime/test classpath, starter-test cung cấp Spring Test, JUnit Jupiter và assertions. Không có Hibernate/JPA hay R2DBC vì trọng tâm là JDBC ResultSet. Spring Boot BOM quản lý phiên bản tương thích; không tự pin H2/JDBC driver khác mà không có nhu cầu.

### 6.2. Application và kiểu dữ liệu Java

**src/main/java/demo/jdbc/JdbcMappingApplication.java**

~~~java
package demo.jdbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcMappingApplication.class, args);
    }
}
~~~

**src/main/java/demo/jdbc/CustomerStatus.java**

~~~java
package demo.jdbc;

public enum CustomerStatus {
    ACTIVE,
    PAUSED
}
~~~

**src/main/java/demo/jdbc/CustomerView.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.time.LocalDate;

public record CustomerView(
        long id,
        String name,
        Integer rewardPoints,
        Boolean verified,
        BigDecimal creditLimit,
        LocalDate lastContactDate,
        CustomerStatus status) {
}
~~~

Java 17 record giữ các field bất biến theo giá trị của chúng. Đặc biệt, `Integer rewardPoints` và `Boolean verified` có thể là null, khác với int/boolean. Nếu domain yêu cầu không có null, policy chuẩn hóa dữ liệu nên được định nghĩa rõ ở một layer phù hợp, không để JDBC primitive getters làm việc đó ngầm.

### 6.3. Schema/data SQL cho test

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(80) NOT NULL,
    reward_points INTEGER NULL,
    verified BOOLEAN NULL,
    credit_limit DECIMAL(12,2) NULL,
    last_contact_date DATE NULL,
    state_code VARCHAR(20) NOT NULL
);
~~~

**src/test/resources/data.sql**

~~~sql
INSERT INTO customer_profiles (
    id, full_name, reward_points, verified,
    credit_limit, last_contact_date, state_code
) VALUES
    (1, 'Lan', 0, FALSE, 1234.50, DATE '2024-04-12', 'active'),
    (2, 'Minh', NULL, NULL, NULL, NULL, 'PAUSED'),
    (3, 'Hòa', 42, TRUE, 0.00, DATE '2024-05-01', 'ACTIVE'),
    (4, 'Invalid', 7, FALSE, 5.00, DATE '2024-06-01',
     'not-a-status');
~~~

**Tại sao ở src/test/resources?** Với embedded H2 trong @JdbcTest, Spring Boot 3.3 có **SqlInitializationAutoConfiguration**, mặc định chạy schema.sql rồi data.sql từ test classpath khi khởi tạo DataSource. Các file test này **không tự được đem vào bootRun bình thường**, vì bootRun không mặc định đưa test resources lên runtime classpath. Với production hãy dùng Flyway/Liquibase hoặc cơ chế schema initialization độc lập đúng môi trường.

Các test bên dưới chỉ SELECT, không thay đổi các rows đã seed, vì vậy không phụ thuộc thứ tự chạy. Nếu thêm DML, cần hiểu transaction/rollback của @JdbcTest; không nên dùng DDL create/drop trong mỗi test tùy tiện vì database có commit semantics riêng.

### 6.4. RowMapper đầy đủ

**src/main/java/demo/jdbc/CustomerRowMapper.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.jdbc.core.RowMapper;

public final class CustomerRowMapper implements RowMapper<CustomerView> {

    @Override
    public CustomerView mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        long id = rs.getLong("id");
        String name = rs.getString("full_name");

        int rawPoints = rs.getInt("reward_points");
        Integer points = rs.wasNull() ? null : rawPoints;

        boolean rawVerified = rs.getBoolean("verified");
        Boolean verified = rs.wasNull() ? null : rawVerified;

        BigDecimal creditLimit = rs.getBigDecimal("credit_limit");

        Date sqlDate = rs.getDate("last_contact_date");
        LocalDate lastContact =
                sqlDate == null ? null : sqlDate.toLocalDate();

        String rawStatus = rs.getString("state_code");
        CustomerStatus status;
        try {
            status = CustomerStatus.valueOf(
                    rawStatus.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Unsupported state_code: " + rawStatus, ex);
        }

        return new CustomerView(
                id, name, points, verified,
                creditLimit, lastContact, status);
    }
}
~~~

**Phân tích các điểm quan trọng:**
1. id là BIGINT PRIMARY KEY NOT NULL; Java long không đánh mất NULL hợp lệ vì schema không cho phép null.
2. name là VARCHAR NOT NULL, dùng getString. Nếu schema nullable, getString sẽ trả Java null thay vì empty String.
3. reward_points dùng getInt rồi **wasNull ngay sau đó**, tạo Integer nullable đúng.
4. verified dùng getBoolean rồi **wasNull ngay sau đó**, giữ TRUE/FALSE/NULL.
5. credit_limit dùng getBigDecimal; không đi qua double và không thay null bằng BigDecimal.ZERO.
6. last_contact_date dùng getDate rồi kiểm null trước toLocalDate, tránh NPE.
7. state_code NOT NULL, do đó `rawStatus.trim()` hợp lệ với schema hiện tại. Nếu cột ngoài đời cho NULL, phải thiết kế một nhánh null rõ.
8. Enum conversion có Locale.ROOT và exception có tên cột + raw code; không im lặng coi mã lạ là ACTIVE.
9. Mapper không gọi rs.next(), không đóng ResultSet và không tự gửi SQL thêm trong callback.
10. rowNum không được dùng làm primary key. Khi cần logging row number, lưu ý thứ tự row phụ thuộc ORDER BY.

### 6.5. Repository sử dụng JdbcTemplate và parameterized SQL

**src/main/java/demo/jdbc/CustomerRepository.java**

~~~java
package demo.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRepository {

    private static final String SELECT_COLUMNS = """
            SELECT id, full_name, reward_points, verified,
                   credit_limit, last_contact_date, state_code
            FROM customer_profiles
            """;

    private final JdbcTemplate jdbc;
    private final CustomerRowMapper mapper = new CustomerRowMapper();

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerView> findById(long id) {
        List<CustomerView> rows = jdbc.query(
                SELECT_COLUMNS + " WHERE id = ?",
                mapper, id);

        return rows.stream().findFirst();
    }

    public List<CustomerView> findByStatus(CustomerStatus status) {
        return jdbc.query(
                SELECT_COLUMNS
                        + " WHERE UPPER(state_code) = ? ORDER BY id",
                mapper, status.name());
    }
}
~~~

`findById` truy vấn theo primary key nên tối đa một row; `jdbc.query` trả List rỗng khi không tìm thấy, sau đó Optional.empty. Khi tìm thấy row có nhiều SQL NULL thì Optional vẫn chứa CustomerView. `findByStatus` dùng cùng RowMapper cho nhiều rows; ORDER BY làm expected order trong test rõ.

Dấu **?** truyền tham số vào PreparedStatement, tránh ghép untrusted input trực tiếp vào SQL. SELECT_COLUMNS được nối với các SQL fragments **cố định từ source code**, không chứa dữ liệu bên ngoài. SQL UPPER đơn giản cho case normalization nhưng có thể ảnh hưởng việc dùng index ở production; nên quyết định normalization policy khi thiết kế bảng.

**Vì sao RowMapper tạo bằng new?** Mapper không có state/constructor dependency, có thể dùng lại an toàn trong repository. Nếu cần converter hoặc cấu hình, dùng bean injection có chủ đích, không bắt buộc RowMapper phải mang @Component.

## 7. Bộ test JUnit Jupiter: 12 phương thức thực thi JDBC

**src/test/java/demo/jdbc/CustomerJdbcMappingTest.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(CustomerRepository.class)
class CustomerJdbcMappingTest {

    @Autowired
    CustomerRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsZeroFalseDecimalDateAndLowercaseStatus() {
        CustomerView row = repository.findById(1L).orElseThrow();

        assertEquals(1L, row.id());
        assertEquals("Lan", row.name());
        assertEquals(Integer.valueOf(0), row.rewardPoints());
        assertEquals(Boolean.FALSE, row.verified());
        assertEquals(new BigDecimal("1234.50"), row.creditLimit());
        assertEquals(
                LocalDate.of(2024, 4, 12), row.lastContactDate());
        assertEquals(CustomerStatus.ACTIVE, row.status());
    }

    @Test
    void preservesAllSqlNullColumns() {
        CustomerView row = repository.findById(2L).orElseThrow();

        assertEquals("Minh", row.name());
        assertNull(row.rewardPoints());
        assertNull(row.verified());
        assertNull(row.creditLimit());
        assertNull(row.lastContactDate());
        assertEquals(CustomerStatus.PAUSED, row.status());
    }

    @Test
    void mapsTrueZeroMoneyAndUnicode() {
        CustomerView row = repository.findById(3L).orElseThrow();

        assertEquals("Hòa", row.name());
        assertEquals(Integer.valueOf(42), row.rewardPoints());
        assertEquals(Boolean.TRUE, row.verified());
        assertEquals(new BigDecimal("0.00"), row.creditLimit());
        assertEquals(
                LocalDate.of(2024, 5, 1), row.lastContactDate());
        assertEquals(CustomerStatus.ACTIVE, row.status());
    }

    @Test
    void missingRowProducesOptionalEmpty() {
        assertTrue(repository.findById(999L).isEmpty());
    }

    @Test
    void mapsSeveralRowsInExplicitOrder() {
        List<CustomerView> rows =
                repository.findByStatus(CustomerStatus.ACTIVE);

        assertEquals(2, rows.size());
        assertEquals(
                List.of(1L, 3L),
                rows.stream().map(CustomerView::id).toList());
        assertEquals(
                List.of("Lan", "Hòa"),
                rows.stream().map(CustomerView::name).toList());
    }

    @Test
    void rejectsInvalidEnumCodeClearly() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> repository.findById(4L));

        assertTrue(error.getMessage().contains(
                "Unsupported state_code: not-a-status"));
    }

    @Test
    void bareGetIntCollapsesNullAndZero() {
        Integer zero = jdbc.queryForObject(
                "SELECT reward_points FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getInt("reward_points"), 1L);

        Integer sqlNull = jdbc.queryForObject(
                "SELECT reward_points FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getInt("reward_points"), 2L);

        assertEquals(Integer.valueOf(0), zero);
        assertEquals(Integer.valueOf(0), sqlNull);
    }

    @Test
    void wasNullObservesOnlyTheLastColumnRead() {
        Boolean tooLate = jdbc.queryForObject(
                """
                SELECT reward_points, id
                FROM customer_profiles WHERE id = 2
                """,
                (rs, n) -> {
                    rs.getInt("reward_points");
                    rs.getLong("id");
                    return rs.wasNull();
                });

        Boolean immediately = jdbc.queryForObject(
                """
                SELECT reward_points
                FROM customer_profiles WHERE id = 2
                """,
                (rs, n) -> {
                    rs.getInt("reward_points");
                    return rs.wasNull();
                });

        assertEquals(Boolean.FALSE, tooLate);
        assertEquals(Boolean.TRUE, immediately);
    }

    @Test
    void bareGetBooleanCollapsesNullAndFalse() {
        Boolean falseValue = jdbc.queryForObject(
                "SELECT verified FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getBoolean("verified"), 1L);

        Boolean sqlNull = jdbc.queryForObject(
                "SELECT verified FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getBoolean("verified"), 2L);

        assertEquals(Boolean.FALSE, falseValue);
        assertEquals(Boolean.FALSE, sqlNull);
    }

    @Test
    void readsSqlColumnAliasByColumnLabel() {
        String name = jdbc.queryForObject(
                """
                SELECT full_name AS screen_name
                FROM customer_profiles WHERE id = ?
                """,
                (rs, n) -> rs.getString("screen_name"), 1L);

        assertEquals("Lan", name);
    }

    @Test
    void queryForObjectRequiresExactlyOneRow() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> jdbc.queryForObject(
                        """
                        SELECT full_name
                        FROM customer_profiles WHERE id = ?
                        """,
                        String.class, 999L));

        assertThrows(
                IncorrectResultSizeDataAccessException.class,
                () -> jdbc.queryForObject(
                        """
                        SELECT full_name
                        FROM customer_profiles WHERE id IN (1, 3)
                        """,
                        String.class));
    }

    @Test
    void exactNarrowingRejectsFractionsAndOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> new BigDecimal("12.50").intValueExact());

        assertThrows(
                ArithmeticException.class,
                () -> Math.toIntExact(3_000_000_000L));
    }
}
~~~

**Tổng cộng 12 phương thức @Test**. Bộ fixture chỉ được đọc nên không cần @TestMethodOrder, static mutable state hoặc reset test database giữa methods. Test 7–9 **cố ý assert hành vi sai của primitive getter nếu quên wasNull** để người học thấy lỗi: đó không phải mapper production. Mapper thực đã gọi wasNull đúng thứ tự và test 1–3 bảo vệ dữ liệu.

### 7.1. Tại sao test id=1 quan trọng?

Hàng 1 có reward_points=0, verified=FALSE, credit_limit=1234.50, DATE '2024-04-12', status "active". Một mapper sai có thể vẫn trả 0/FALSE cho hàng này và test đơn giản pass. Nhưng test id=1 cần đi cùng test id=2 NULL và id=3 TRUE để bảo đảm **0/FALSE không bị gộp với SQL NULL**.

BigDecimal("1234.50") được so theo scale đúng với DECIMAL(12,2) của H2. Converter enum chuẩn hóa "active" thành ACTIVE theo chính sách Locale.ROOT. DATE được chuyển thành LocalDate chính xác, không dựa vào timezone của JVM cho ý nghĩa ngày lịch.

### 7.2. Test id=2 bắt lỗi bỏ wasNull

Hàng id=2 có SQL NULL ở reward_points, verified, credit_limit và last_contact_date. `preservesAllSqlNullColumns()` kiểm tra **từng nullable field**. Nếu mapper dùng `getInt` và `getBoolean` không wasNull, nó trả Integer(0) và Boolean.FALSE, khiến assertion fail. Nếu mapper gọi date.toLocalDate mà bỏ null check, nó phát sinh NullPointerException.

Hàng này vẫn là một record hợp lệ vì id/full_name/state_code đều NOT NULL. Đừng biến object thành Optional.empty chỉ vì một field không có giá trị.

### 7.3. Test id=3 bảo vệ TRUE, zero money và Unicode

Hàng 3 có points=42, verified=TRUE, credit_limit=0.00 và full_name "Hòa". Bài test chứng minh Boolean.TRUE khác NULL/FALSE, BigDecimal(0.00) khác SQL NULL, DATE '2024-05-01' được giữ nguyên và dữ liệu tiếng Việt đi qua H2/JDBC/JVM đúng.

Với dữ liệu thật, nên thêm tests cho số âm, rất lớn, scale đặc biệt và Unicode normalization nếu domain có yêu cầu. Dữ liệu 3 hàng chỉ là **tập tối thiểu có chủ đích** để nêu lỗi phổ biến.

### 7.4. Test wasNull và nguy cơ gọi trễ

`bareGetIntCollapsesNullAndZero()` cố ý đọc hai rows có 0 và NULL bằng getInt không kiểm wasNull; cả hai cho 0. `bareGetBooleanCollapsesNullAndFalse()` tương tự: FALSE và NULL đều cho false.

`wasNullObservesOnlyTheLastColumnRead()` chứng minh thứ tự:
- getInt("reward_points") trên SQL NULL.
- getLong("id") trên BIGINT NOT NULL.
- wasNull() lúc này trả **false**, vì lần đọc gần nhất là id.

Nếu gọi wasNull ngay sau getInt, nó trả **true**. Điều cần học là **vị trí của một câu lệnh**, không phải số lượng câu lệnh: không thể đặt một wasNull ở cuối method rồi suy luận cho nhiều columns.

### 7.5. Test status, row count và alias

Hàng id=4 cố ý chứa state_code="not-a-status". Custom enum converter chủ động ném IllegalArgumentException có thông báo "Unsupported state_code". Không nên đổi nó thành Optional.empty hoặc mặc định ACTIVE vì như vậy che giấu dữ liệu sai.

`findByStatus(ACTIVE)` kiểm tra một SELECT nhiều rows trả List có id theo ORDER BY: 1,3. Câu SQL UPPER(state_code) cho phép "active" và "ACTIVE". Điều này kiểm tra mapper chạy cho nhiều rows, không phụ thuộc thứ tự ngẫu nhiên của database.

`readsSqlColumnAliasByColumnLabel()` dùng SELECT full_name AS screen_name và getter getString("screen_name"). Theo JDBC, column label là alias. Nếu code đọc full_name khi ResultSet chỉ expose screen_name, driver có thể ném SQLException; JdbcTemplate sẽ xử lý qua cơ chế exception translation.

`queryForObjectRequiresExactlyOneRow()` cố ý kiểm:
- Không có row → EmptyResultDataAccessException.
- Nhiều hơn một row → IncorrectResultSizeDataAccessException.

Đây là **cardinality errors**, không phải cột SQL NULL. `JdbcTemplate.query` trả List, phù hợp tìm danh sách hoặc chuyển theo khóa unique thành Optional.

## 8. Chạy test và kiểm chứng kết quả

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trong Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu bạn vừa tạo source mà chưa tạo Wrapper scripts/JAR, lệnh ./gradlew chưa tồn tại. Dùng phiên bản Gradle tương thích để tạo wrapper hoặc chạy **gradle test**. H2 embedded không cần container, socket HTTP, PostgreSQL hay Redis.

Chạy riêng class:

~~~bash
./gradlew test --tests demo.jdbc.CustomerJdbcMappingTest
~~~

Với đúng source, scripts và dependencies của ví dụ, JUnit Jupiter sẽ phát hiện **12 test methods**. Tất cả được thiết kế để PASS trên H2; đây là kỳ vọng từ source mẫu, **không phải tuyên bố đã thực thi tests trong môi trường của bạn**. Báo cáo Gradle thường nằm ở:

~~~text
build/reports/tests/test/index.html
~~~

**Các mutation tự luyện để thấy test có ích:**

- Xóa `rs.wasNull()` ở getInt hoặc getBoolean: test NULL phải fail.
- Đổi Integer/Boolean thành int/boolean: row SQL NULL không thể giữ nguyên.
- Gọi toLocalDate không kiểm date null: test id=2 fail do NPE.
- Chuyển BigDecimal sang double rồi dựng object: test money/scale có thể phát hiện khác biệt.
- Bỏ toUpperCase(Locale.ROOT): row code "active" fail enum conversion.
- Thay invalid enum code thành trạng thái mặc định: test invalid code fail.
- Đổi SELECT alias nhưng chưa sửa label getter: JDBC báo column not found.
- Bỏ ORDER BY ở query nhiều rows: test thứ tự không còn được SQL contract bảo đảm.

Không sửa expected assertions để che lỗi. Mục tiêu của mutation là thấy **lớp test đang bảo vệ hành vi nào** rồi khôi phục mapping đúng.

## 9. Các cách mapping khác: ưu và nhược điểm

| Cách ánh xạ | Cơ chế | Nên dùng khi | Cần kiểm thử |
|---|---|---|---|
| **Custom RowMapper<T>** | Tự đọc ResultSet và tạo DTO | NULL/enum/date/money có policy riêng | Mọi getter, nullability, conversions |
| **BeanPropertyRowMapper<T>** | Ánh xạ theo JavaBean setters/properties | Bean đơn giản | Null-to-primitive, naming, converters |
| **DataClassRowMapper<T>** | Constructor-based / data class / record | Java record đơn giản | Enum custom, nullable types, precision |
| **SingleColumnRowMapper<T>** | Một cột thành một value | COUNT/ID/String | Empty/multiple rows, null |
| **ColumnMapRowMapper** | Row thành Map labels/values | Query động/tooling | Trùng labels, type safety bị giảm |

BeanPropertyRowMapper thường hỗ trợ chuyển tên cột `full_name` sang property `fullName` nếu bean phù hợp, nhưng không có nghĩa nó áp đúng business enum conversion. DataClassRowMapper hỗ trợ Java records tùy phiên bản, song bạn vẫn cần test các trường hợp null, scale và trạng thái. **Thay mapper implementation không được phép thay ngầm contract dữ liệu.**

Nếu query JOIN nhiều bảng hoặc có nested DTO, một custom RowMapper rất hữu ích; nhưng không nên query thêm database trong mapRow cho từng row vì có thể tạo **N+1 queries**. Hãy cân nhắc SQL join/batch fetching hay mapper tổng hợp phù hợp.

## 10. Ma trận kiểm thử theo các loại dữ liệu

| Kiểu dữ liệu | Fixture tối thiểu | Điều phải giữ |
|---|---|---|
| INTEGER NULL | SQL NULL, 0, 42, -1, near limits | NULL khác 0, không overflow |
| BOOLEAN NULL | NULL, FALSE, TRUE | Ba trạng thái riêng |
| DECIMAL | NULL, 0.00, 0.10, 1234.50 | BigDecimal chính xác, scale theo contract |
| DATE | NULL, ngày bình thường, cuối tháng/năm | LocalDate đúng, không NPE |
| VARCHAR | null nếu nullable, empty, blank, Unicode | Không tự gộp các trạng thái |
| VARCHAR enum | ACTIVE, active, " paused ", code lạ | Chính sách normalization/failure |
| BIGINT | 1, giá trị lớn, biên overflow int | Java long/exact narrowing |
| SELECT | 0 row, 1 row, >1 rows | List/Optional/queryForObject đúng |
| SQL alias | Tên gốc, alias, JOIN trùng label | Đọc column label đúng |
| TIMESTAMP | Null, UTC, timezone transition | Temporal semantics rõ |
| UUID/JSON/ARRAY | Valid, null, invalid driver-specific | Test với production JDBC driver |

Không ép tất cả miền nghiệp vụ dùng chung null policy. Ví dụ credit_limit=NULL có thể mang nghĩa chưa khai báo, còn 0.00 nghĩa không có hạn mức; ở miền khác NULL có thể được chuẩn hóa thành một default theo policy công khai. **Điều quan trọng là quyết định có chủ đích và có test tương ứng**, không để JDBC primitive default quyết định giúp.

## 11. Giới hạn của H2 và yêu cầu production database

H2 giúp phát hiện nhiều lỗi JDBC phổ biến nhanh, nhưng không thay PostgreSQL/MySQL/Oracle/SQL Server cho mọi kiểu dữ liệu:
- Vendor SQL dialect, quoted identifiers, column label case sensitivity.
- JSONB, native ENUM, UUID, ARRAY, binary/CLOB.
- BOOLEAN mappings của các kiểu 0/1/CHAR riêng.
- DECIMAL precision/scale, overflow, rounding.
- TIMESTAMP/TIMESTAMP WITH TIME ZONE và driver-specific timezone conversion.
- Empty string vs NULL, Unicode collation/case conversion.
- Transaction locking, isolation và vendor SQLState/exception classes.

Với các cột phụ thuộc vendor, thêm integration test bằng **Testcontainers** và chính JDBC driver/schema migrations production. Trong @JdbcTest, mặc định datasource có thể bị thay bằng embedded; để dùng datasource container, cần cấu hình rõ như **@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)** cùng test datasource/service connection phù hợp.

Không nhất thiết chạy mọi unit test bằng full SpringBootTest. Phân tầng hợp lý: unit test mapper logic, @JdbcTest H2 cho JDBC basics, Testcontainers cho vendor-specific behavior, full integration cho business/HTTP boundaries.

## 12. Transaction, exception và bảo mật khi test JDBC

**Transaction:** @JdbcTest thường rollback test-managed DML sau mỗi method. Bộ ví dụ chỉ SELECT nên không cần cleanup. Nếu thêm INSERT/UPDATE, phải hiểu transaction scope; DDL có commit semantics riêng. Khi test HTTP RANDOM_PORT gọi server ở thread/transaction khác, @Transactional trên JUnit method **không tự rollback** những writes server đã commit.

**Exception:** SQLException do SQL/driver có thể được JdbcTemplate chuyển thành DataAccessException; IllegalArgumentException do custom enum conversion có thể đi thẳng ra caller. EmptyResultDataAccessException và IncorrectResultSizeDataAccessException thuộc vấn đề row count, không phải vấn đề mapping nullable columns.

**An toàn:** dùng JdbcTemplate parameters `?` thay vì nối user input vào SQL để giảm SQL injection và giữ type binding rõ ràng. Không log nguyên PII, token, raw SQL bind values nhạy cảm hoặc full database exception ra response. Nếu converter ném lỗi vì state_code lạ, message có thể hữu ích cho log nội bộ nhưng phải qua policy an toàn khi bộc lộ cho client.

## 13. Các lỗi thường gặp và quy trình debug

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| SQL NULL thành 0 | getInt không wasNull | Getter → wasNull ngay, dùng Integer |
| SQL NULL thành false | getBoolean không wasNull | Getter → wasNull ngay, dùng Boolean |
| wasNull false dù cột cũ NULL | Có getter khác ở giữa | Đặt wasNull sát cột đang kiểm |
| NullPointerException trên Date | getDate trả null | Kiểm null trước toLocalDate |
| BigDecimal bị sai | DECIMAL đi qua double | getBigDecimal, test precision/scale |
| BigDecimal.equals fail vì scale | 1.0 khác 1.00 với equals | Chọn equals/compareTo theo contract |
| long bị sai sau cast int | Numeric overflow | Math.toIntExact khi thu hẹp |
| Enum "active" không được nhận | valueOf case-sensitive | Locale.ROOT uppercase nếu policy cho phép |
| Mã enum lạ bị nuốt | Converter dùng default sai | Fail rõ hoặc enum UNKNOWN được quy định |
| SQL column not found | Alias trong SELECT khác getter | Đọc đúng label và test query thực |
| Map nhầm ID trong JOIN | Trùng tên cột | Explicit aliases |
| queryForObject 0 row ném exception | Hiểu nhầm là Optional | Query + List/Optional khi phù hợp |
| queryForObject nhiều rows ném exception | Kết quả không unique | List hoặc unique constraint |
| @JdbcTest thiếu repository bean | Slice không scan mọi @Repository | @Import đúng class |
| schema.sql/data.sql không chạy | Sai test classpath/SQL init | src/test/resources, embedded DB config |
| H2 pass nhưng production fail | Driver-specific conversion | Testcontainers với DB thật |
| Test pass riêng, fail cả suite | Static state/DML chưa cleanup | Fixture cô lập, rollback rõ |
| Mapper đọc thiếu hàng | Tự gọi rs.next | Để JdbcTemplate điều khiển ResultSet |
| Exception type không như dự đoán | Nhầm SQL exception với conversion error | Test đúng từng exception boundary |

**Thứ tự điều tra khuyến nghị:** kiểm schema/nullability → kiểm SQL SELECT/aliases → kiểm các getter và wasNull call order → seed NULL/0/FALSE/TRUE → assert BigDecimal/DATE/enum → kiểm row count → chạy @JdbcTest → nếu chỉ lỗi ở production, chạy cùng fixtures với driver thật. Không dùng Thread.sleep hay trông chờ test order để “sửa” vấn đề dữ liệu.

## 14. Bài tập tự luyện

1. **Nullable BIGINT:** Thêm referrer_id BIGINT NULL, map bằng Long và getLong/wasNull; test null, 0 và ID lớn.
2. **Tri-state BOOLEAN:** Đổi mapper verified sang getBoolean trực tiếp và xác định test nào fail; giải thích ý nghĩa SQL NULL khác FALSE.
3. **DECIMAL:** Seed 0.00, 0.10, 100000.99, SQL NULL; dùng BigDecimal và kiểm scale theo contract.
4. **Enum:** Thêm mã " paused " và "DISABLED"; chọn normalization, failure hoặc UNKNOWN policy có tests.
5. **Alias:** SELECT full_name AS preferred_name; đổi mapper theo label hoặc tạo test phát hiện column missing.
6. **Row cardinality:** Dùng queryForObject cho 0/1/2 rows, phân biệt với row hợp lệ có nullable fields SQL NULL.
7. **Date/time:** Thêm TIMESTAMP; xác định LocalDateTime hay Instant, test timezone/DST độc lập với máy chạy.
8. **Generic mapper:** Thay custom RowMapper bằng BeanPropertyRowMapper hoặc DataClassRowMapper và chạy lại NULL/enum/money tests.
9. **Driver thật:** Chạy cùng fixture trên PostgreSQL Testcontainers và đối chiếu type conversions.
10. **Transaction:** Thêm test INSERT và kiểm rollback; so với test RANDOM_PORT có server transaction riêng.

## 15. Tài liệu chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — @JdbcTest, embedded database, JdbcTemplate và rollback.
- [Spring Boot 3.3 — Test Slices](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html) — SqlInitializationAutoConfiguration trong @JdbcTest.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html) — schema.sql, data.sql và mặc định embedded DB.
- [Spring Framework 6.1 — RowMapper API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html) — contract mapRow(ResultSet, rowNum).
- [Spring Framework 6.1 — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html) — query, queryForObject, JDBC exception translation.
- [Java SE 17 — ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — primitive getters, wasNull, getBigDecimal, getDate.
- [Java SE 17 — BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — scale, equals/compareTo, exact narrowing.
- [Spring JDBC — DataClassRowMapper](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html) — constructor-based mapping và records.

**Ghi nhớ:** RowMapper tốt phải **giữ đúng ý nghĩa dữ liệu SQL**. SQL NULL khác 0/FALSE; với primitive getters hãy gọi wasNull **ngay sau getter** rồi dùng Integer/Boolean để giữ null. DECIMAL dùng BigDecimal, DATE cần null check trước LocalDate, enum conversion phải có quy tắc rõ, và SQL aliases phải khớp getter column labels. **@JdbcTest + H2 + các test NULL/zero/false/true/invalid-code** là cách nhanh để phát hiện lỗi, còn production JDBC driver cần được kiểm chứng thêm khi type conversion phụ thuộc SQL vendor.
