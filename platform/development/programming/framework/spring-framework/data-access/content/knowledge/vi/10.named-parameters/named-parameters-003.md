# MapSqlParameterSource và khai báo kiểu SQL

## 1. Tại sao tham số có tên vẫn cần khai báo kiểu SQL?

Trong Spring JDBC, `NamedParameterJdbcTemplate` cho phép viết `:customerCode`, `:amount` hoặc `:remark` thay cho các dấu `?` theo thứ tự. Cách này làm câu SQL dài dễ đọc, giảm nhầm lẫn khi nhiều tham số cùng kiểu và có thể tái sử dụng cùng một tên.

Ví dụ:

~~~sql
INSERT INTO invoices (customer_code, amount, remark)
VALUES (:customerCode, :amount, :remark)
~~~

Để cung cấp các giá trị theo tên, ta có thể truyền một `Map<String, ?>` hoặc một `SqlParameterSource`. **`MapSqlParameterSource`** là implementation thông dụng của `SqlParameterSource`: chứa cặp tên → giá trị, đồng thời có thể cung cấp **kiểu JDBC SQL** và **type name** cho từng tham số.

Điểm cần phân biệt:

- **Tên tham số** xác định giá trị Java nào gắn với vị trí bind trong câu SQL.
- **Giá trị Java** là dữ liệu gửi tới database, ví dụ `"C001"`, `new BigDecimal("125.50")`, `LocalDate` hoặc `null`.
- **Kiểu SQL** cho biết cách JDBC nên xử lý một tham số, ví dụ `Types.VARCHAR`, `Types.DECIMAL`, `Types.DATE` hoặc `Types.BIGINT`.
- **Type name** có thể cần với kiểu đặc biệt/vendor-specific; không phải mọi truy vấn đều cần khai báo.
- **Định nghĩa cột** vẫn nằm ở DDL của database: chỉ định `Types.DECIMAL` lúc bind **không** tạo cột DECIMAL hay tự áp đặt quy tắc nghiệp vụ.
- **Validation** là việc khác: bind đúng kiểu không bảo đảm giá dương, mã hợp lệ hay người dùng có quyền truy cập dữ liệu.

Khai báo kiểu SQL đặc biệt hữu ích khi giá trị Java **`null` không mang thông tin lớp Java**, với kiểu JDBC không hiển nhiên, hoặc khi driver/database đòi hỏi kiểu rõ ràng. Khi giá trị không null và driver hiểu tốt, Spring thường có thể suy luận hoặc lựa chọn setter phù hợp; không cần ép khai báo kiểu cho mọi tham số một cách máy móc.

## 2. Vị trí của MapSqlParameterSource trong Spring JDBC

`NamedParameterJdbcTemplate` là lớp hỗ trợ named parameters và ủy quyền phần lớn công việc JDBC cho `JdbcTemplate` bên dưới. `MapSqlParameterSource` không thực thi SQL và không giữ Connection: nó chỉ là **nguồn metadata tham số** truyền vào các phương thức `query`, `queryForObject`, `update`, `batchUpdate`.

~~~text
Repository/Service
    |
    | SQL:  UPDATE invoices
    |       SET remark = :remark
    |       WHERE id = :id
    |
    | MapSqlParameterSource:
    |   remark -> null, Types.VARCHAR
    |   id     -> 5L, Types.BIGINT
    v
NamedParameterJdbcTemplate
    |
    | phân tích tên tham số và bind values/types
    | SQL JDBC tương ứng: UPDATE invoices
    |                    SET remark = ?
    |                    WHERE id = ?
    v
JdbcTemplate -> PreparedStatement -> JDBC driver -> Database
    |
    v
Số dòng bị ảnh hưởng / List DTO / kết quả truy vấn
~~~

Tên tham số giúp đọc code; chúng không được gửi nguyên dạng vào JDBC PreparedStatement. Spring phân tích và thay những tên phù hợp bằng placeholder JDBC, sau đó bind các giá trị đúng thứ tự. Một tên có thể xuất hiện nhiều lần trong cùng SQL: Spring lấy giá trị đã cung cấp để bind cho từng chỗ tương ứng.

Không nhầm `:id` với tên cột `id`. `:id` là placeholder giá trị; tên bảng, tên cột và đoạn cú pháp SQL không thể thay bằng placeholder dữ liệu. Với dynamic identifier, chỉ sử dụng một tập tên cho phép được xác thực trước khi tạo SQL.

## 3. API thiết yếu của MapSqlParameterSource

Lớp thuộc package `org.springframework.jdbc.core.namedparam` và kế thừa `AbstractSqlParameterSource`. Các dạng dùng phổ biến:

~~~java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

// Không khai báo SQL type:
MapSqlParameterSource simple = new MapSqlParameterSource()
        .addValue("id", 10L)
        .addValue("status", "NEW");

// Khai báo SQL type với hằng số java.sql.Types:
MapSqlParameterSource explicit = new MapSqlParameterSource()
        .addValue("id", 10L, Types.BIGINT)
        .addValue("amount", new BigDecimal("125.50"), Types.DECIMAL)
        .addValue("remark", null, Types.VARCHAR);

// Khởi tạo từ Map có sẵn:
MapSqlParameterSource fromMap = new MapSqlParameterSource(
        Map.of("id", 10L, "status", "NEW"));

// Có thể truyền qua interface:
SqlParameterSource source = explicit;
~~~

Đây là **đoạn minh họa sử dụng API trong một phương thức hoặc JShell có đủ import**, không phải một file Java độc lập. Lưu ý `Map.of` **không cho phép value null**; khi cần typed NULL, dùng `MapSqlParameterSource.addValue(..., null, sqlType)`.

Bảng phương thức:

| API | Ý nghĩa |
| --- | --- |
| `new MapSqlParameterSource()` | Tạo nguồn tham số rỗng. |
| `new MapSqlParameterSource(name, value)` | Tạo nguồn với một tham số. |
| `new MapSqlParameterSource(map)` | Sao chép/cung cấp các cặp tham số từ Map (không kèm SQL type do Map không mô tả type). |
| `addValue(name, value)` | Thêm giá trị, chưa khai báo SQL type rõ ràng. |
| `addValue(name, value, sqlType)` | Thêm giá trị cùng mã JDBC SQL type. |
| `addValue(name, value, sqlType, typeName)` | Thêm giá trị, mã SQL type và tên kiểu SQL cụ thể. |
| `addValues(map)` | Thêm nhiều cặp tên/giá trị. |
| `registerSqlType(name, sqlType)` | Đăng ký SQL type cho tên đã hoặc sẽ dùng. |
| `registerTypeName(name, typeName)` | Đăng ký tên kiểu SQL cho tham số khi cần. |
| `hasValue(name)` / `getValue(name)` | Kiểm tra tồn tại tên và lấy giá trị. |
| `getSqlType(name)` / `getTypeName(name)` | Lấy metadata SQL type/type name đã đăng ký. |
| `getValues()` | Lấy view Map read-only của tập giá trị. |

Các overload `addValue` trả về chính `MapSqlParameterSource` để gọi nối chuỗi. `getValues()` không phải lời hứa rằng đối tượng MapSqlParameterSource bên trong đã bất biến; thông thường nên tạo một nguồn tham số mới cho từng request/câu SQL thay vì chia sẻ và sửa một instance mutable giữa các luồng.

### 3.1. Hai cách khai báo SQL type tương đương về ý định

~~~java
MapSqlParameterSource a = new MapSqlParameterSource()
        .addValue("remark", null, Types.VARCHAR);

MapSqlParameterSource b = new MapSqlParameterSource()
        .addValue("remark", null);
b.registerSqlType("remark", Types.VARCHAR);
~~~

Khi đưa vào NamedParameterJdbcTemplate, hai nguồn này cùng có một giá trị `remark=null` với metadata `Types.VARCHAR`. Cách đầu thường ngắn và đọc dễ hơn; cách thứ hai hữu ích nếu logic đăng ký type và logic nạp giá trị tách biệt.

### 3.2. Kiểu chưa khai báo không có nghĩa Types.NULL

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("remark", null);

boolean present = p.hasValue("remark");       // true
Object value = p.getValue("remark");          // null
int sqlType = p.getSqlType("remark");
// sqlType == SqlParameterSource.TYPE_UNKNOWN
~~~

Đây là mẫu code minh họa. `hasValue` phân biệt **đã khai báo tên nhưng giá trị null** với **chưa khai báo tên**. `SqlParameterSource.TYPE_UNKNOWN` có nghĩa Spring chưa được cấp SQL type rõ ràng; nó **không tương đương** `java.sql.Types.NULL`. Khi driver không suy luận được kiểu của null, khai báo chính xác `Types.VARCHAR`/`Types.INTEGER`/… có thể xử lý vấn đề; lựa chọn phải dựa trên kiểu cột và quy ước driver.

## 4. Hiểu đúng java.sql.Types và typeName

`addValue(name, value, sqlType)` nhận một **số nguyên JDBC SQL type**, thường viết bằng hằng `java.sql.Types`. Không truyền `String.class`, `Integer.class` hoặc tên SQL kiểu chuỗi vào vị trí tham số `sqlType`.

| Java value / mục đích | SQL type thường phù hợp | Lưu ý |
| --- | --- | --- |
| `String` cho VARCHAR | `Types.VARCHAR` | CHAR/NVARCHAR có thể có ngữ nghĩa khác theo schema/driver. |
| `Long` cho BIGINT | `Types.BIGINT` | Kiểm tra giới hạn số, đừng ép sai kiểu cột. |
| `Integer` cho INTEGER | `Types.INTEGER` | Phân biệt NULL và số 0. |
| `BigDecimal` cho DECIMAL | `Types.DECIMAL` hoặc `Types.NUMERIC` | Kiểu cột phải đủ precision/scale; không thay validation tiền tệ. |
| `java.sql.Date` cho DATE | `Types.DATE` | Dùng `Date.valueOf(LocalDate)` nếu cần JDBC DATE rõ ràng. |
| `java.sql.Timestamp` cho TIMESTAMP | `Types.TIMESTAMP` | Xác định timezone/driver và ý nghĩa thời điểm. |
| `Boolean` cho BOOLEAN | `Types.BOOLEAN` | Hỗ trợ và mapping có thể khác giữa các database. |
| `byte[]` cho BINARY/VARBINARY | `Types.VARBINARY` (tùy cột) | BLOB/stream có vòng đời tài nguyên riêng. |
| SQL NULL của cột VARCHAR | `null` kèm `Types.VARCHAR` | Metadata type hướng dẫn bind null. |
| JSONB, UUID, ARRAY, custom type | Có thể là `Types.OTHER`, `Types.ARRAY` và typeName | Phụ thuộc vendor/driver, không suy diễn từ một database sang database khác. |

**Type name** dùng khi driver hoặc kiểu đặc thù cần biết tên SQL chính xác, ví dụ `jsonb` hay tên kiểu ARRAY trong một database cụ thể:

~~~java
MapSqlParameterSource vendorSpecific =
        new MapSqlParameterSource()
                .addValue("payload", "{\"enabled\":true}",
                        Types.OTHER, "jsonb");
~~~

Đây chỉ là **minh họa cú pháp đăng ký metadata**, **không phải ví dụ chạy được trên mọi database**. PostgreSQL JSONB có thể cần `PGobject`, cast SQL hoặc driver-specific binding; chỉ thêm `Types.OTHER` và `"jsonb"` **không bảo đảm** một String sẽ luôn được driver chấp nhận. Cần kiểm thử trực tiếp với database/driver đích. Với các kiểu vendor-specific, phải hiểu cách driver gọi `setObject`/`setNull` và metadata `typeName`.

Khác biệt cần nhớ: typeName ở đây là **tên kiểu SQL của tham số**, không phải tên tham số, tên cột hay tên Java class. Không khai báo typeName “cho đẹp” nếu driver không cần.

## 5. Typed NULL: tình huống quan trọng nhất

Khi truyền giá trị null, Java không có runtime class của giá trị để gợi ý loại SQL. Một số driver/JDBC path xử lý untyped null được, nhưng ở những câu SQL/driver khác việc xác định kiểu có thể mơ hồ hoặc gây lỗi. Đưa SQL type vào `MapSqlParameterSource` giúp biểu đạt rõ ý định:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", 5L, Types.BIGINT)
        .addValue("remark", null, Types.VARCHAR);

int updated = namedJdbc.update(
        "UPDATE invoices SET remark = :remark WHERE id = :id",
        params);
~~~

Đoạn đặt trong repository có trường `NamedParameterJdbcTemplate namedJdbc`. Hai tham số được bind theo loại JDBC phù hợp. Nếu `remark` là cột VARCHAR nullable, cập nhật `remark` thành SQL NULL là điều hợp lệ. Nếu cột NOT NULL, database vẫn từ chối. SQL type metadata **không vượt qua** NOT NULL/CHECK/FK constraints.

**NULL không giống chuỗi rỗng và không giống giá trị mặc định.** Trong SQL, phép so sánh bằng với NULL không theo quy tắc số học thường:

~~~sql
-- Không dùng biểu thức này để tìm các hàng remark IS NULL:
SELECT id FROM invoices WHERE remark = :remark;

-- Đúng khi cần tìm remark đang NULL:
SELECT id FROM invoices WHERE remark IS NULL;
~~~

Nếu `:remark` được bind là NULL, biểu thức `remark = NULL` cho UNKNOWN theo SQL three-valued logic, không match hàng như mong đợi. Đây là vấn đề **ngữ nghĩa SQL**, không được giải quyết bằng việc chỉ khai báo `Types.VARCHAR`.

### 5.1. Khi nào nên khai báo kiểu?

- Giá trị null và driver không thể xác định hoặc bắt buộc phải biết type.
- Driver cần setNull với đúng kiểu cột/kiểu tùy biến.
- Dữ liệu được chuyển qua Java type quá rộng (ví dụ `Object`) và không muốn để driver chọn không nhất quán.
- Batch chứa các hàng mà cùng tham số có lúc null, lúc không null.
- Kiểu đặc thù như SQL ARRAY, STRUCT, JSONB, UUID cần contract driver rõ ràng.

Không buộc phải thêm SQL type cho mọi tham số String/Long/BigDecimal đã biết. Chỉ khai báo chính xác khi giúp rõ contract hoặc khi cần. Khai báo **sai** type có thể làm hỏng conversion, mất precision hoặc tạo lỗi khó hiểu hơn so với để Spring tự suy luận.

## 6. Ví dụ chạy được: NamedParameterJdbcTemplate + MapSqlParameterSource + H2

Ta tạo ứng dụng console Spring Boot lưu hóa đơn vào H2. Repository dùng typed SQL parameters cho `BIGINT`, `VARCHAR`, `DECIMAL`, `DATE`, bao gồm giá trị `remark = null`. App cũng chạy truy vấn `IN (:statuses)` để thấy named parameter collection được xử lý ra sao.

Các điều kiện của demo:

- Java 21, Gradle tương thích Java 21 (ví dụ Gradle 8.5).
- Spring Boot 3.3.5 và Spring JDBC starter, H2 trong bộ nhớ.
- Không cần database server hoặc HTTP.
- Bảng được tạo mới mỗi lần chạy trong tiến trình độc lập.
- Dữ liệu đầu vào là cố định để output ổn định.

### 6.1. Cấu trúc dự án

~~~text
named-sql-types-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/namedsql/
    │   ├── NamedSqlApplication.java
    │   ├── InvoiceView.java
    │   ├── InvoiceRepository.java
    │   └── InvoiceService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'named-sql-types-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:namedsqldemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    issue_date DATE NOT NULL,
    remark VARCHAR(200),
    status VARCHAR(16) NOT NULL
);
~~~

Ở đây kiểu SQL của **cột** được quyết định bởi schema. MapSqlParameterSource sẽ khai báo **kiểu của các giá trị bind** tương ứng. Cột remark cho phép SQL NULL; amount thì không.

### 6.2. Model kết quả

Tệp `src/main/java/example/namedsql/InvoiceView.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.time.LocalDate;

public record InvoiceView(
        long id,
        String customerCode,
        BigDecimal amount,
        LocalDate issueDate,
        String remark,
        String status) {
}
~~~

Record chứa giá trị Java đã được đọc: Long primitive, String, BigDecimal và LocalDate. Caller có thể sử dụng nó sau khi truy vấn kết thúc, không cần giữ ResultSet/Connection.

### 6.3. Repository: typed parameters và generated keys

Tệp `src/main/java/example/namedsql/InvoiceRepository.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Types;
import java.time.LocalDate;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class InvoiceRepository {
    private static final String INSERT_SQL = """
            INSERT INTO invoices
                (customer_code, amount, issue_date, remark, status)
            VALUES
                (:customerCode, :amount, :issueDate, :remark, :status)
            """;

    private final NamedParameterJdbcTemplate namedJdbc;

    public InvoiceRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }

    public long insert(
            String customerCode,
            BigDecimal amount,
            LocalDate issueDate,
            String remark,
            String status) {

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("customerCode", customerCode, Types.VARCHAR)
                .addValue("amount", amount, Types.DECIMAL)
                .addValue("issueDate", Date.valueOf(issueDate), Types.DATE)
                .addValue("remark", remark, Types.VARCHAR)
                .addValue("status", status, Types.VARCHAR);

        KeyHolder keys = new GeneratedKeyHolder();
        int updated = namedJdbc.update(
                INSERT_SQL, params, keys, new String[] {"id"});

        if (updated != 1 || keys.getKey() == null) {
            throw new IllegalStateException(
                    "Không insert được một invoice có generated key");
        }
        return keys.getKey().longValue();
    }

    public int clearRemark(long invoiceId) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", invoiceId, Types.BIGINT)
                .addValue("remark", null, Types.VARCHAR);

        return namedJdbc.update(
                "UPDATE invoices SET remark = :remark WHERE id = :id",
                params);
    }

    public List<InvoiceView> findByStatuses(List<String> statuses) {
        if (statuses.isEmpty()) {
            return List.of();
        }

        MapSqlParameterSource params =
                new MapSqlParameterSource()
                        .addValue("statuses", statuses);

        return namedJdbc.query("""
                SELECT id, customer_code, amount, issue_date, remark, status
                FROM invoices
                WHERE status IN (:statuses)
                ORDER BY id
                """,
                params,
                (rs, rowNum) -> new InvoiceView(
                        rs.getLong("id"),
                        rs.getString("customer_code"),
                        rs.getBigDecimal("amount"),
                        rs.getDate("issue_date").toLocalDate(),
                        rs.getString("remark"),
                        rs.getString("status")));
    }
}
~~~

**Điểm cần hiểu trong code:**

1. `new MapSqlParameterSource()` được tạo riêng cho từng thao tác, nên không chia sẻ trạng thái mutable của tham số giữa request/thread.
2. `addValue("amount", amount, Types.DECIMAL)` mô tả cách bind BigDecimal với cột DECIMAL. Nó **không** thay việc validate amount phải dương/không vượt ngưỡng; đó là nhiệm vụ của domain và database constraints.
3. `Date.valueOf(issueDate)` tạo JDBC DATE tương ứng với LocalDate để demo không phụ thuộc việc driver tự convert LocalDate sang DATE. Trong ứng dụng thật, nhiều driver hiện đại có thể xử lý LocalDate trực tiếp; hãy kiểm tra compatibility.
4. `addValue("remark", remark, Types.VARCHAR)` hoạt động cả khi remark là String hoặc null. Trường hợp null là ví dụ điển hình có ích khi khai báo type.
5. `KeyHolder` nhận generated key từ JDBC driver. Overload `update(sql, params, keyHolder, new String[]{"id"})` có hỗ trợ Spring JDBC; tên cột generated key có thể khác theo database/cách quote identifier. H2 ở demo này hỗ trợ.
6. `clearRemark` đưa cùng tên/giá trị vào UPDATE nhưng bind null có SQL type cụ thể. Trả int là số dòng cập nhật; caller phải kiểm tra 0 dòng nếu nghiệp vụ yêu cầu invoice phải tồn tại.
7. `findByStatuses` truyền collection cho tham số `:statuses`. NamedParameterJdbcTemplate mở rộng danh sách thành đúng số placeholder cho SQL IN, không biến nó thành một tham số JDBC ARRAY. Vì vậy không khai báo `Types.ARRAY` cho List này.
8. Kiểm tra danh sách rỗng trước khi dùng `IN (:statuses)`. Không dựa vào SQL `IN ()` vì cú pháp/hành vi không portable. Repository định nghĩa danh sách rỗng trả kết quả rỗng.
9. RowMapper đọc cột và tạo InvoiceView; ResultSet đã được template đóng khi query kết thúc. `issue_date` có NOT NULL trong schema nên `getDate(...).toLocalDate()` được dùng an toàn trong demo này.

### 6.4. Service đặt ranh giới transaction

Tệp `src/main/java/example/namedsql/InvoiceService.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<InvoiceView> createExamples() {
        long first = repository.insert(
                "C001", new BigDecimal("125.50"),
                LocalDate.of(2026, 10, 1), null, "NEW");

        repository.insert(
                "C002", new BigDecimal("80.00"),
                LocalDate.of(2026, 10, 2), "Giao nhanh", "PAID");

        if (repository.clearRemark(first) != 1) {
            throw new IllegalStateException(
                    "Không cập nhật được remark");
        }

        return repository.findByStatuses(List.of("NEW", "PAID"));
    }
}
~~~

`@Transactional` bao các thao tác insert/update/query trong cùng transaction Spring JDBC vì NamedParameterJdbcTemplate và transaction manager dùng cùng DataSource do Spring Boot cấu hình. Nếu có exception phù hợp thoát khỏi method, Spring rollback. `MapSqlParameterSource` không tự tạo transaction, chỉ mô tả tham số; tính nguyên tử thuộc service và transaction manager.

### 6.5. Runner và stdout

Tệp `src/main/java/example/namedsql/NamedSqlApplication.java`:

~~~java
package example.namedsql;

import java.sql.JDBCType;
import java.sql.Types;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@SpringBootApplication
public class NamedSqlApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedSqlApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(InvoiceService service) {
        return args -> {
            MapSqlParameterSource typedNull =
                    new MapSqlParameterSource()
                            .addValue("remark", null, Types.VARCHAR);

            System.out.println("Kiểu JDBC remark: "
                    + JDBCType.valueOf(
                            typedNull.getSqlType("remark")));

            List<InvoiceView> invoices = service.createExamples();
            System.out.println("Số hóa đơn: " + invoices.size());

            for (InvoiceView row : invoices) {
                System.out.printf(
                        "id=%d | code=%s | amount=%s | date=%s"
                        + " | remark=%s | status=%s%n",
                        row.id(),
                        row.customerCode(),
                        row.amount().toPlainString(),
                        row.issueDate(),
                        row.remark(),
                        row.status());
            }
        };
    }
}
~~~

Chạy tại thư mục `named-sql-types-demo` với JDK 21 và Gradle hỗ trợ Java 21:

~~~bash
gradle bootRun
~~~

Các dòng **do chương trình in ra** với database H2 mới, không tính output của Gradle:

~~~text
Kiểu JDBC remark: VARCHAR
Số hóa đơn: 2
id=1 | code=C001 | amount=125.50 | date=2026-10-01 | remark=null | status=NEW
id=2 | code=C002 | amount=80.00 | date=2026-10-02 | remark=Giao nhanh | status=PAID
~~~

Diễn giải:

- `JDBCType.valueOf(typedNull.getSqlType("remark"))` trả enum `JDBCType.VARCHAR` từ mã `Types.VARCHAR` đã khai báo; dòng đầu không thực thi SQL, chỉ quan sát metadata trong MapSqlParameterSource.
- Hai INSERT dùng tham số có tên, khai báo SQL type rõ ràng; cột remark đầu tiên được gửi dưới dạng typed NULL.
- Lần UPDATE tiếp theo đặt remark đầu tiên thành NULL một lần nữa để minh họa `clearRemark`; nó vẫn là null khi SELECT.
- Hai trạng thái `NEW` và `PAID` được truyền như một collection vào SQL IN; kết quả được ORDER BY id.
- Từng giá trị DECIMAL được RowMapper đọc bằng BigDecimal, in bằng toPlainString nên không có sai số do float/double.
- Demo chỉ giả định id tự sinh của H2 bắt đầu từ 1 trong **tiến trình mới**. Với database đã có dữ liệu, identity/sequence không mặc nhiên bắt đầu từ 1.

## 7. Các cách khai báo và kiểm tra SQL type

Một `MapSqlParameterSource` lưu cả giá trị lẫn metadata type. Có thể đọc chúng để kiểm tra logic bind trước khi truy vấn:

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("id", 42L, Types.BIGINT)
        .addValue("remark", null, Types.VARCHAR)
        .addValue("amount", new BigDecimal("19.90"), Types.DECIMAL);

System.out.println(p.hasValue("remark"));
System.out.println(p.getValue("remark") == null);
System.out.println(p.getSqlType("remark") == Types.VARCHAR);
System.out.println(p.getSqlType("amount") == Types.DECIMAL);
~~~

Đây là đoạn Java **trong một method với import** cho MapSqlParameterSource, Types, BigDecimal; bốn dòng in ra đều là `true`. Lưu ý: chúng chỉ xác thực metadata bên Java, không chứng minh driver bind đúng dưới mọi schema/database. Cần integration test cho phần thực thi SQL.

### 7.1. registerSqlType và registerTypeName

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("payload", "{\"name\":\"A\"}");

p.registerSqlType("payload", Types.OTHER);
p.registerTypeName("payload", "jsonb");
~~~

Đoạn code này **chỉ cho thấy cách đăng ký metadata**, chưa thực hiện SQL và không đảm bảo driver PostgreSQL chấp nhận String như JSONB. Kiểu tên `jsonb` là đặc trưng PostgreSQL; database khác có thể dùng JSON/JSONB khác. Với JSONB thực tế, kiểm tra driver, có thể cần `PGobject`, cast SQL hoặc binding khác. Đừng lấy ví dụ typeName vendor-specific rồi áp dụng mù quáng cho H2, MySQL, SQL Server, Oracle.

### 7.2. Một nguồn tham số có thể được dùng lại tên

~~~sql
SELECT id
FROM invoices
WHERE status = :status
   OR (:status = 'ALL')
~~~

~~~java
MapSqlParameterSource args =
        new MapSqlParameterSource("status", "NEW");
~~~

Spring bind cùng giá trị `NEW` cho hai lần xuất hiện `:status` trong PreparedStatement. Đây chỉ là minh họa cú pháp. Với query có dữ liệu thật, hãy quyết định tiêu chí tìm kiếm và index cho phù hợp; tránh đặt các biểu thức OR không cần thiết nếu ảnh hưởng hiệu năng.

### 7.3. Dữ liệu null không được gửi bằng Map.of

~~~java
// Sai: Map.of không cho phép giá trị null.
Map<String, Object> broken =
        Map.of("remark", null);

// Đúng: MapSqlParameterSource chấp nhận giá trị null
// và cung cấp kiểu SQL tương ứng.
MapSqlParameterSource ok =
        new MapSqlParameterSource()
                .addValue("remark", null, Types.VARCHAR);
~~~

Phần đầu là **chống ví dụ**, chạy sẽ ném NullPointerException trước khi gửi SQL. `HashMap` có thể chứa null, nhưng một `Map<String,Object>` thông thường vẫn không mang metadata SQL type rõ ràng; khi driver có yêu cầu typed null thì `MapSqlParameterSource` hữu ích hơn.

## 8. Các kiểu tham số phức tạp và giới hạn

### 8.1. IN và collection expansion khác SQL ARRAY

Spring có thể mở rộng một Java Collection tại chỗ `IN (:ids)` thành các bind placeholder tương ứng:

~~~java
List<Long> ids = List.of(10L, 20L, 30L);
MapSqlParameterSource args =
        new MapSqlParameterSource()
                .addValue("ids", ids);

List<Long> result = namedJdbc.query(
        "SELECT id FROM invoices WHERE id IN (:ids)",
        args,
        (rs, rowNum) -> rs.getLong("id"));
~~~

Đây là **đoạn minh họa trong repository có NamedParameterJdbcTemplate namedJdbc**. Với ba id, SQL tương ứng có ba placeholder JDBC. Điều này không giống với việc tạo `java.sql.Array` hoặc bind bằng `Types.ARRAY`. Tránh collection rỗng và chú ý giới hạn số tham số SQL của database khi danh sách rất lớn; có thể cần batch, temporary table hoặc giải pháp khác.

### 8.2. Kiểu DATE/TIMESTAMP và timezone

`Types.DATE` phù hợp với ngày không có phần giờ; `LocalDate` có thể chuyển sang `java.sql.Date` cho một ví dụ portable hơn. `Types.TIMESTAMP` và `Types.TIMESTAMP_WITH_TIMEZONE` không tương đương. Nếu domain cần một **thời điểm tuyệt đối**, cân nhắc `Instant`/`OffsetDateTime`, kiểu cột, JDBC driver và quy ước UTC/offset; không tuyên bố chỉ cần chọn hằng Types thì timezone đã tự đúng.

Ví dụ typed timestamp:

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("createdAt",
                java.sql.Timestamp.from(
                        java.time.Instant.parse("2026-10-01T09:00:00Z")),
                Types.TIMESTAMP);
~~~

Đây là **ví dụ tạo tham số**, không kết nối database. Chuyển Instant sang TIMESTAMP không có timezone có thể phụ thuộc cấu hình driver/timezone; test đúng trên database thật.

### 8.3. DECIMAL, precision và scale

`Types.DECIMAL` mô tả cách bind BigDecimal, nhưng không tự tạo precision hay làm tròn đúng nghiệp vụ. Nếu bảng có `DECIMAL(12,2)`, nên bảo đảm BigDecimal theo đơn vị tiền tệ và chính sách scale trước khi ghi, đồng thời để database áp ràng buộc. `new BigDecimal("125.50")` chính xác hơn việc dùng `new BigDecimal(125.50)` khi muốn decimal theo biểu diễn chuỗi. Nếu có currency, cần kiểm tra cả đơn vị và precision, không chỉ một hằng Types.

### 8.4. JSON, UUID, ARRAY, BLOB, CLOB

Không có một SQL type duy nhất dùng được cho mọi database đối với JSON/UUID, arrays hoặc large objects. Một số driver yêu cầu object vendor-specific, type name hay cast trong SQL. Với BLOB/CLOB stream, phải kiểm soát thời điểm đọc và đóng tài nguyên; không trả InputStream đang gắn Connection ra ngoài scope. Dùng `Types.OTHER` hoặc `Types.ARRAY` phải theo tài liệu JDBC driver và database đích, không dùng chỉ vì chưa rõ type.

## 9. Batch update với typed NULL

Khi ghi nhiều hàng, `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` cho phép mỗi phần tử giữ metadata SQL type. Đây là trường hợp nên cân nhắc khai báo kiểu khi một số dòng có tham số null.

~~~java
SqlParameterSource[] batch = {
        new MapSqlParameterSource()
                .addValue("customerCode", "C010", Types.VARCHAR)
                .addValue("remark", null, Types.VARCHAR),

        new MapSqlParameterSource()
                .addValue("customerCode", "C011", Types.VARCHAR)
                .addValue("remark", "Gọi trước", Types.VARCHAR)
};

int[] affected = namedJdbc.batchUpdate("""
        UPDATE invoices
        SET remark = :remark
        WHERE customer_code = :customerCode
        """,
        batch);
~~~

Đây là đoạn **minh họa trong repository** có `NamedParameterJdbcTemplate namedJdbc`, import `SqlParameterSource`, `MapSqlParameterSource`, `Types`. Hai dòng UPDATE có thể trả số bị ảnh hưởng 0 nếu code không có trong bảng; đó là kết quả hợp lệ về mặt JDBC nhưng nghiệp vụ có thể cần từ chối nếu mong đợi đúng một invoice. Batch không tự tạo transaction cho toàn bộ nghiệp vụ; bao bằng `@Transactional` nếu cần commit/rollback cùng nhau và dùng đúng DataSource.

Một cách khác để chuẩn bị batch từ bean/Map là `SqlParameterSourceUtils.createBatch(...)`, nhưng nếu cần chỉ định SQL type tùy từng null hoặc từng vendor parameter thì tự tạo MapSqlParameterSource cho từng phần tử là cách minh bạch. Đừng giả định tất cả driver thực thi batch theo cùng cách, hoặc mọi phần tử đã commit/rollback đồng nhất nếu không có transaction.

## 10. MapSqlParameterSource, Map và BeanPropertySqlParameterSource

| Lựa chọn | Ưu điểm | Giới hạn / khi dùng |
| --- | --- | --- |
| `Map<String, ?>` | Ngắn khi giá trị đơn giản và không null, truyền thẳng cho nhiều overload. | Không cung cấp SQL type metadata trực tiếp; `Map.of` không nhận null. |
| `MapSqlParameterSource` | Named values, typed NULL, sqlType/typeName, addValue chain, addValues. | Mutable; phải tạo mới theo operation, type tự khai báo cần đúng schema/driver. |
| `BeanPropertySqlParameterSource` | Đọc tên/giá trị từ property JavaBean/record phù hợp. | Metadata type suy từ property khi có thể; không thay validation hay custom mapping driver. |
| `SqlParameterSourceUtils.createBatch` | Tạo batch SqlParameterSource từ Map/bean nhanh. | Với kiểu vendor/typed NULL đặc biệt, kiểm tra metadata thực tế hoặc dùng MapSqlParameterSource rõ ràng. |

**Lựa chọn thực tế:** một SELECT với hai giá trị String/Long rõ ràng có thể dùng Map. Một INSERT nhiều cột có nullable value, DATE/DECIMAL hoặc driver đặc thù nên cân nhắc MapSqlParameterSource để khai báo rõ. Một CRUD đơn giản từ JavaBean có thể dùng BeanPropertySqlParameterSource. Không phải lúc nào MapSqlParameterSource cũng tốt hơn Map hay BeanProperty.

## 11. Lỗi phổ biến và cách phòng tránh

| Lỗi | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| Tên SQL `:customerCode` nhưng source chứa `customer_code` | Không tìm được tham số theo tên, có thể ném exception. | Đồng nhất tên/alias SQL và key. |
| Gán null không có SQL type khi driver cần type | Driver có thể không xác định được type của null. | Dùng `addValue(name, null, Types.X)` đúng cột. |
| Dùng `Types.NULL` hoặc `Types.OTHER` cho mọi null | Có thể khác hẳn kiểu cột, driver không chấp nhận. | Chọn hằng đúng SQL type và test với driver. |
| Nhầm `SqlParameterSource.TYPE_UNKNOWN` với `Types.NULL` | Một bên là chưa khai báo, một bên là hằng JDBC type. | Hiểu ý nghĩa metadata. |
| Dùng `Types.ARRAY` cho List dùng trong IN | IN-list expansion không phải SQL ARRAY binding. | Truyền Collection thường và xử lý empty list. |
| Không xét danh sách rỗng | SQL IN () không portable, có thể sai cú pháp. | Quy định riêng kết quả empty list. |
| Truyền `new BigDecimal(0.1)` cho tiền | Có thể đưa vào sai số nhị phân. | Dùng chuỗi decimal hoặc factory được định nghĩa. |
| Tin rằng `Types.DECIMAL` kiểm tra giá dương | SQL type không kiểm tra domain. | Bean Validation/domain rule và DB constraints. |
| Dùng `Map.of("x", null)` | Ném NullPointerException trước khi gọi JDBC. | Dùng MapSqlParameterSource cho typed null. |
| Thay bảng/cột bằng `:table`, `:column` | Bind placeholder chỉ dành cho giá trị, không phải SQL identifier. | Whitelist identifier, không nối user input tùy tiện. |
| Tạo một MapSqlParameterSource shared mutable giữa request | Tham số từ request khác có thể bị ghi đè/race condition. | Tạo một instance mới trên từng operation/batch item. |
| Không kiểm tra số dòng UPDATE | 0 dòng cũng có thể coi là không thành công về nghiệp vụ. | So sánh affected rows với yêu cầu. |
| Khai báo typeName vendor nhưng không test | Driver có thể cần object/cast riêng. | Tích hợp test trực tiếp database/driver. |
| Trông chờ MapSqlParameterSource quản lý transaction | Nó chỉ giữ giá trị và metadata. | Dùng transaction manager/@Transactional phù hợp. |
| Tin typed null bảo đảm mọi truy vấn NULL đúng | SQL NULL so sánh theo three-valued logic. | Dùng IS NULL / IS NOT NULL khi muốn tìm null. |

### An toàn SQL và dữ liệu đầu vào

`MapSqlParameterSource` và PreparedStatement binding giúp tham số là **dữ liệu**, không phải cú pháp SQL. Tuy nhiên, nó không kiểm tra quyền truy cập, whitelist mã định danh, giới hạn số lượng, giá âm, điều kiện liên bảng hay SQL được xây động đúng logic. Validation và authorization phải nằm ở tầng phù hợp; database constraints là lớp bảo vệ bổ sung.

## 12. Kiểm thử và chẩn đoán

Để kiểm chứng một repository sử dụng named parameters và type metadata đúng:

1. **Kiểm tra local metadata:** `hasValue`, `getValue`, `getSqlType`, `getTypeName` với giá trị null và không null; bảo đảm `Types` tương ứng schema.
2. **Integration test với database thật hoặc tương thích:** chạy INSERT, UPDATE typed NULL, SELECT bằng RowMapper; kiểm tra dữ liệu đọc lại và affected rows.
3. **Kiểm tra NULL:** cột nullable nhận SQL NULL; cột NOT NULL từ chối, đồng thời test query tìm null bằng IS NULL thay vì `= :value`.
4. **Kiểm tra độ chính xác:** BigDecimal có scale/precision đúng khi đi qua JDBC và trở lại; không có conversion qua double không cần thiết.
5. **Kiểm tra DATE/TIMESTAMP:** ngày, thời điểm và timezone theo hợp đồng, đặc biệt khi dùng driver khác H2.
6. **Kiểm tra IN collection:** List có 1, nhiều và 0 phần tử; danh sách rỗng theo chính sách repository.
7. **Kiểm tra giá trị không hợp lệ:** tên param sai, null ngoài ý muốn, type mismatch, giá trị vượt độ lớn hoặc DECIMAL precision.
8. **Kiểm tra transaction:** nhiều thao tác update cùng service được rollback nếu xuất hiện exception, không có raw Connection ngoài transaction.
9. **Kiểm tra driver-specific:** JSON, ARRAY, UUID, generated keys và typeName với chính database production, không chỉ H2.
10. **Observability:** log SQL và lỗi bind phù hợp ở môi trường test; không đưa PII/secret vào log. Driver logging cấu hình quá chi tiết có thể làm lộ dữ liệu tham số.

### Câu hỏi tự kiểm tra

1. `MapSqlParameterSource` khác `Map<String,Object>` ở điểm nào quan trọng với typed NULL?
2. `addValue("remark", null, Types.VARCHAR)` khai báo điều gì và **không** bảo đảm điều gì?
3. Vì sao `SqlParameterSource.TYPE_UNKNOWN` không đồng nghĩa `Types.NULL`?
4. Khi nào nên dùng `registerSqlType` hoặc overload bốn tham số gồm `typeName`?
5. Với `WHERE status IN (:statuses)`, vì sao không nên ép `Types.ARRAY` cho List thông thường?
6. Thay `:tableName` vào vị trí tên bảng có hoạt động như bind dữ liệu không? Vì sao?
7. Trong demo, giá trị LocalDate được chuyển thành loại JDBC DATE bằng cách nào?
8. Nếu cột remark là NOT NULL, typed NULL có thể ghi thành công không?
9. Với batch gồm một số remark null, metadata type giúp gì, còn trách nhiệm transaction nằm ở đâu?
10. Muốn gửi JSONB sang PostgreSQL, vì sao chỉ `addValue(..., Types.OTHER, "jsonb")` chưa chắc đủ?

**Kết luận:** `MapSqlParameterSource` là nguồn named parameters có thể mô tả **giá trị Java + kiểu JDBC SQL + tên SQL type**. Nó đặc biệt hữu ích cho typed NULL và trường hợp driver cần type tường minh. Dùng nó cùng `NamedParameterJdbcTemplate`, chọn hằng `Types` theo schema/driver, validate dữ liệu độc lập với binding, và đặt transaction tại service; đừng dùng type metadata như một cách thay thế hợp đồng nghiệp vụ hay database constraints.

### Tài liệu tham khảo

- Spring JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- MapSqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- AbstractSqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/AbstractSqlParameterSource.html
- NamedParameterJdbcTemplate API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- SqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html
- JDBC Types (JDK 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Types.html
