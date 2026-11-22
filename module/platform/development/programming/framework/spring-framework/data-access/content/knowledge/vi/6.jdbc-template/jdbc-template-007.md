# ConnectionCallback cho tình huống cần truy cập JDBC mức thấp

## 1. Khi nào cần ConnectionCallback?

Với Spring JDBC, phần lớn thao tác dữ liệu nên dùng các phương thức có sẵn của **JdbcTemplate** như query, queryForObject, update và batchUpdate. Những phương thức này lo việc lấy kết nối, đóng JDBC resource, bind tham số, duyệt ResultSet và dịch lỗi SQL, nên service và repository ít phải quản lý tài nguyên thủ công.

Tuy nhiên, có những tình huống cần trực tiếp sử dụng **java.sql.Connection**: lấy DatabaseMetaData; tạo SQL Array/Struct; dùng API vendor-specific; hoặc chạy một chuỗi thao tác JDBC đặc thù trên cùng Connection mà các phương thức tiện dụng chưa biểu đạt rõ. **ConnectionCallback<T>** là điểm mở rộng của JdbcTemplate cho việc đó. Callback được Spring cấp một Connection và có thể trả một kết quả T đã xử lý xong.

Sau bài này, bạn phải trả lời được:

1. ConnectionCallback được gọi như thế nào, và ai chịu trách nhiệm lấy/release Connection?
2. Vì sao có thể dùng PreparedStatement, ResultSet, DatabaseMetaData trong callback mà vẫn tham gia Spring transaction?
3. Những tài nguyên nào phải đóng bằng try-with-resources, những thao tác nào tuyệt đối không nên làm trên Connection do Spring quản lý?
4. SQLException được chuyển thành DataAccessException ra sao?
5. Khi nào chọn ConnectionCallback thay vì RowMapper, ResultSetExtractor, PreparedStatementCallback hay JdbcTemplate.update?
6. Vì sao nhiều câu SQL chạy trong một callback chưa tự bảo đảm atomic khi service không có ranh giới transaction?

Bài dùng **Java 21, Spring Boot 3.3.5 và H2** cho ví dụ runnable. Phạm vi là Spring JDBC đồng bộ; reactive/R2DBC dùng cách quản lý transaction context khác.

## 2. Hợp đồng của ConnectionCallback<T>

Trong package org.springframework.jdbc.core, ConnectionCallback là một functional interface. Về mặt khái niệm, giao diện này có dạng:

~~~java
@FunctionalInterface
interface ConnectionCallback<T> {
    T doInConnection(Connection connection) throws SQLException;
}
~~~

Đây là **chữ ký minh họa rút gọn**, không phải interface cần tự định nghĩa trong dự án. Bản thật thuộc thư viện Spring và có thể khai báo thêm DataAccessException; SQLException được phép ném vì callback là điểm truy cập JDBC mức thấp.

JdbcTemplate có overload execute(ConnectionCallback<T>). Ví dụ, đọc tên hệ quản trị database thông qua Connection:

~~~java
String productName = jdbcTemplate.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
~~~

Đoạn này giả định đã có JdbcTemplate jdbcTemplate và import org.springframework.jdbc.core.ConnectionCallback. Ép kiểu tường minh **ConnectionCallback<String>** giúp Java phân giải đúng overload execute vì JdbcTemplate còn có các overload khác với callback nhận Statement.

Phương thức execute được Spring thiết kế để:

- Lấy Connection qua cơ chế Spring JDBC, có thể dùng lại Connection gắn với transaction hiện tại nếu DataSource/transaction manager khớp.
- Gọi callback với Connection đó; JdbcTemplate thường bọc Connection bằng proxy có hành vi chặn close trực tiếp và chuẩn bị các Statement theo cấu hình template.
- Cho phép callback đọc metadata, tạo PreparedStatement, xử lý ResultSet, trả về object hoặc collection đã được materialize.
- Catch SQLException thoát khỏi callback và dịch sang hệ **org.springframework.dao.DataAccessException** (unchecked).
- Release Connection khi callback kết thúc, nhưng không commit/rollback sớm transaction do service đang quản lý.

Bởi vậy, API này cung cấp quyền thao tác mức Connection mà vẫn giữ hợp đồng quản lý tài nguyên của Spring.

## 3. Luồng tài nguyên khi thực thi

~~~text
Application / Controller
    |
    v
Service @Transactional
    |
    v
Repository
    |
    v
JdbcTemplate.execute(ConnectionCallback<T>)
    |
    +-- DataSourceUtils / Spring JDBC lấy Connection phù hợp
    |     +-- Transaction active cùng DataSource: Connection đã gắn
    |     +-- Không có transaction: mượn kết nối cho lần thực thi
    |
    +-- callback chạy với Connection
    |     +-- getMetaData()
    |     +-- prepareStatement(...), bind tham số
    |     +-- executeQuery() / executeUpdate()
    |     +-- đọc ResultSet / generated keys
    |     +-- đóng ResultSet, PreparedStatement
    |     +-- trả DTO / scalar T
    |
    +-- JdbcTemplate chuyển SQLException thành DataAccessException
    +-- Spring release Connection
    |
    v
Service nhận T
    |
    +-- transaction kết thúc -> commit hoặc rollback
    |
    v
Caller đọc T mà không cần Connection mở
~~~

**Ai sở hữu cái gì?** Spring chịu trách nhiệm mượn, gắn transaction và release **Connection**. Callback chịu trách nhiệm đóng các **Statement, PreparedStatement, ResultSet** và tài nguyên đặc thù mà nó chủ động tạo. Không trả Connection, ResultSet hoặc Stream đang gắn với ResultSet ra ngoài callback; hãy trả dữ liệu Java đã đọc đầy đủ.

**Một lưu ý về transaction:** JDBC Connection được Spring quản lý trong callback chưa có nghĩa callback tự mở transaction nghiệp vụ. Nếu không có @Transactional và pool ở autoCommit=true, mỗi lệnh SQL có thể commit riêng. Để nhiều thao tác là một đơn vị commit/rollback, đặt transaction tại ranh giới service.

## 4. Bài mẫu chạy được: ghi audit event, lấy id và metadata

Bài toán: bảng audit_events lưu id, category, message. Một phương thức repository phải INSERT sự kiện, đọc generated key, truy vấn COUNT(*) cho category đó và lấy tên database, tất cả bên trong một ConnectionCallback. Sau đó service được gọi hai lần: một lần thành công, một lần cố tình ném exception để kiểm chứng rollback.

### 4.1. Cấu trúc và cấu hình Gradle

~~~text
connection-callback-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/callback/
    │   ├── CallbackApplication.java
    │   ├── SaveInfo.java
    │   ├── AuditRepository.java
    │   └── AuditService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'connection-callback-demo'
~~~

Tệp build.gradle:

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

Tệp src/main/resources/application.properties:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:callbackdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp src/main/resources/schema.sql:

~~~sql
CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    category VARCHAR(32) NOT NULL,
    message VARCHAR(200) NOT NULL
);
~~~

Spring Boot tự cấu hình Hikari DataSource, JdbcTemplate và JDBC transaction manager khi có JDBC starter. H2 dùng bộ nhớ, được khởi tạo lại với mỗi lần chạy tiến trình mới.

### 4.2. Record kết quả

Tệp src/main/java/example/callback/SaveInfo.java:

~~~java
package example.callback;

public record SaveInfo(long id, int countByCategory, String database) {
}
~~~

SaveInfo chứa kết quả đã materialize: long, int và String. Nó không giữ JDBC handle hoặc lazy object nên caller có thể đọc sau khi callback kết thúc.

### 4.3. Repository sử dụng ConnectionCallback

Tệp src/main/java/example/callback/AuditRepository.java:

~~~java
package example.callback;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public SaveInfo insertAndInspect(String category, String message) {
        return jdbc.execute((ConnectionCallback<SaveInfo>) connection -> {
            String database = connection.getMetaData()
                    .getDatabaseProductName();

            long id;
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO audit_events(category, message) VALUES (?, ?)",
                    Statement.RETURN_GENERATED_KEYS)) {

                insert.setString(1, category);
                insert.setString(2, message);

                if (insert.executeUpdate() != 1) {
                    throw new SQLException("Không insert được một sự kiện");
                }

                try (ResultSet keys = insert.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Database không trả generated key");
                    }
                    id = keys.getLong(1);
                }
            }

            int count;
            try (PreparedStatement query = connection.prepareStatement(
                    "SELECT COUNT(*) FROM audit_events WHERE category = ?")) {

                query.setString(1, category);

                try (ResultSet rows = query.executeQuery()) {
                    if (!rows.next()) {
                        throw new SQLException("COUNT không trả kết quả");
                    }
                    count = rows.getInt(1);
                }
            }

            return new SaveInfo(id, count, database);
        });
    }

    public int countCategory(String category) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE category = ?",
                Integer.class,
                category);
        return count;
    }
}
~~~

Diễn giải:

1. **getMetaData():** lấy DatabaseMetaData từ chính Connection được Spring cấp; trong H2 product name là H2.
2. **prepareStatement:** dùng dấu hỏi và setString để bind giá trị, không ghép dữ liệu đầu vào vào SQL.
3. **RETURN_GENERATED_KEYS:** driver trả khóa do database sinh. Đọc ResultSet khóa trước khi đóng PreparedStatement. Cách lấy khóa phụ thuộc khả năng driver/database; ví dụ này phù hợp H2.
4. **SELECT COUNT(*) trên cùng Connection:** trong một transaction đang hoạt động, truy vấn có thể thấy INSERT trước đó chưa commit của chính transaction.
5. **try-with-resources:** bảo đảm đóng ResultSet và PreparedStatement kể cả khi có SQLException. **Không** đặt Connection trong try-with-resources.
6. **SaveInfo:** là kết quả độc lập với Connection sau khi callback trả về.
7. **countCategory:** vì chỉ cần một giá trị scalar, queryForObject đơn giản hơn tự viết ConnectionCallback. Một ứng dụng thực thường dùng update(..., KeyHolder) nếu chỉ cần generated key, thay vì mở API mức thấp.

### 4.4. Service bao transaction quanh callback

Tệp src/main/java/example/callback/AuditService.java:

~~~java
package example.callback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {
    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public SaveInfo save(String category, String message) {
        return repository.insertAndInspect(category, message);
    }

    @Transactional
    public void saveThenRollback(String category, String message) {
        repository.insertAndInspect(category, message);
        throw new IllegalStateException("Yêu cầu rollback");
    }
}
~~~

Service đặt ranh giới transaction. Khi caller gọi bean service qua proxy Spring, transaction manager gắn Connection phù hợp. JdbcTemplate sẽ sử dụng Connection đó; transaction được commit khi save hoàn thành, hoặc rollback khi saveThenRollback ném IllegalStateException ra ngoài method. Đừng tự gọi connection.commit() hay connection.rollback() trong callback.

### 4.5. Chạy ứng dụng và kiểm chứng

Tệp src/main/java/example/callback/CallbackApplication.java:

~~~java
package example.callback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(CallbackApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(AuditService service, AuditRepository repo) {
        return args -> {
            SaveInfo saved = service.save("INFO", "Created successfully");

            System.out.printf(
                    "Đã lưu id=%d, số INFO=%d, DB=%s%n",
                    saved.id(),
                    saved.countByCategory(),
                    saved.database());

            try {
                service.saveThenRollback("ERROR", "Must not persist");
            } catch (IllegalStateException expected) {
                System.out.println("Đã rollback yêu cầu lỗi");
            }

            System.out.printf(
                    "Sau rollback: INFO=%d, ERROR=%d%n",
                    repo.countCategory("INFO"),
                    repo.countCategory("ERROR"));
        };
    }
}
~~~

Chạy từ thư mục dự án với **JDK 21 và Gradle tương thích Java 21** (ví dụ Gradle 8.5):

~~~bash
gradle bootRun
~~~

Ba dòng do chương trình in trong lần chạy H2 mới:

~~~text
Đã lưu id=1, số INFO=1, DB=H2
Đã rollback yêu cầu lỗi
Sau rollback: INFO=1, ERROR=0
~~~

Lần save đầu tiên commit, bản ghi INFO còn lại. Lần saveThenRollback thực hiện INSERT ERROR qua ConnectionCallback nhưng RuntimeException thoát khỏi service khiến Spring rollback transaction, vì vậy ERROR=0 sau đó. Identity sequence có thể vẫn tăng khi INSERT rollback, nên không giả định các id luôn liên tiếp hoặc được tái sử dụng.

**Vì sao đây là kiểm chứng đúng?** Transaction chạy ở service, callback dùng Connection do template lấy từ đúng DataSource. Nếu callback sử dụng một raw Connection khác có autoCommit=true, câu INSERT có thể commit độc lập và không bị service rollback.

## 5. Quản lý Connection đúng cách

### 5.1. Không tự đóng Connection

Đoạn sau là **chống ví dụ**, giả định lớp đã có trường JdbcTemplate jdbc:

~~~java
jdbc.execute((ConnectionCallback<Integer>) connection -> {
    connection.close();  // Sai: Connection do Spring sở hữu.
    return 1;
});
~~~

Trong triển khai hiện hành, JdbcTemplate thường truyền proxy ngăn đóng Connection, nhưng đừng dựa vào chi tiết đó để cố tình close. Spring chịu trách nhiệm release Connection khi callback hoàn tất.

Ví dụ **đúng** khi tự tạo PreparedStatement và ResultSet:

~~~java
int total = jdbc.execute((ConnectionCallback<Integer>) connection -> {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM audit_events");
         ResultSet rows = statement.executeQuery()) {
        if (!rows.next()) {
            throw new SQLException("COUNT không có kết quả");
        }
        return rows.getInt(1);
    }
});
~~~

Đây là đoạn trong method của lớp có trường JdbcTemplate jdbc, với import PreparedStatement, ResultSet, SQLException và ConnectionCallback. Nếu chỉ muốn COUNT(*), queryForObject vẫn gọn hơn. Ý nghĩa ở đây là phân biệt quyền sở hữu: close ResultSet/Statement, để Spring release Connection.

### 5.2. Không commit, rollback hoặc chỉnh autoCommit

Các lệnh dưới đây là **chống ví dụ** trên Connection thuộc transaction manager, không phải phương thức chạy độc lập:

~~~java
connection.setAutoCommit(true);
connection.commit();
connection.rollback();
connection.close();
~~~

Một service @Transactional cần để transaction manager quyết định commit/rollback. Thay isolation hoặc readOnly bên trong callback cũng có thể xung đột với thuộc tính transaction; cấu hình các thuộc tính ấy tại ranh giới transaction và hiểu khả năng của driver trước khi can thiệp.

### 5.3. Tránh trả JDBC handle ra ngoài

Kết quả trả về phải là dữ liệu Java độc lập với vòng đời JDBC. Không return Connection, ResultSet, Statement, Blob locator hoặc Stream cần một ResultSet còn mở. Sau khi execute hoàn tất, Spring có thể đã release tài nguyên. Đọc và materialize DTO ngay trong callback.

Với dữ liệu lớn, materialize hàng triệu hàng vào List có thể tốn bộ nhớ; hãy dùng phân trang, batch hoặc xử lý streaming bên trong phạm vi sở hữu Connection với fetch size, timeout và cleanup được kiểm soát. Lưu ý fetch size là gợi ý cho driver, không bảo đảm mọi driver đều stream như nhau.

## 6. SQLException, DataAccessException và rollback

ConnectionCallback được phép ném SQLException mà không cần tự bọc ở mỗi thao tác; JdbcTemplate sẽ bắt và dịch nó sang một DataAccessException thích hợp. DataAccessException là unchecked exception, nên khi thoát khỏi @Transactional mặc định dẫn đến rollback.

Ngược lại, nếu callback bắt lỗi rồi **nuốt**:

~~~java
// Chống ví dụ: xử lý lỗi sai khiến phía trên tưởng thành công.
try {
    statement.executeUpdate();
} catch (SQLException ex) {
    return 0;
}
~~~

transaction interceptor có thể không biết nghiệp vụ đã thất bại và commit dữ liệu dở dang. Nếu có yêu cầu xử lý phục hồi, hãy biểu đạt chính xác bằng kết quả/exception và quyết định transaction state có chủ đích. Phân biệt “không tìm thấy dòng” (kết quả nghiệp vụ) với SQLException (truy cập database thất bại).

Lưu ý rollback mặc định của Spring thường áp dụng cho RuntimeException/Error thoát khỏi ranh giới transaction. Nếu mã khác ném checked exception chưa được dịch, cần xem rollback rules của @Transactional; không kết luận mọi checked exception đều tự động rollback.

## 7. So sánh các callback và API

| API | Quyền truy cập | Khi dùng |
| --- | --- | --- |
| JdbcTemplate.query(..., RowMapper<T>) | Một hàng ResultSet | Ánh xạ từng hàng thành DTO. |
| JdbcTemplate.query(..., ResultSetExtractor<T>) | Toàn bộ ResultSet của một truy vấn | Ghép hàng hoặc tổng hợp kết quả. |
| JdbcTemplate.execute(sql, PreparedStatementCallback<T>) | PreparedStatement | Tùy biến thao tác trên một statement đã được tạo. |
| JdbcTemplate.execute(StatementCallback<T>) | Statement | Tùy biến một Statement. |
| JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback<T>) | CallableStatement | Gọi stored procedure với IN/OUT parameter. |
| **JdbcTemplate.execute(ConnectionCallback<T>)** | **Connection** | Metadata, SQL array/struct, tính năng vendor hoặc nhiều JDBC statement đặc thù. |
| DataSourceUtils.getConnection(dataSource) | Connection phải release thủ công đúng quy tắc | Khi cần JDBC thủ công ngoài callback của template. |

Nếu chỉ chạy SELECT/UPDATE đơn giản, **không cần** ConnectionCallback; API cấp cao có ít mã cleanup và dễ kiểm thử hơn. Nếu chỉ lấy generated key, dùng JdbcTemplate.update với KeyHolder khi phù hợp. ConnectionCallback hữu ích khi thực sự cần quyền truy cập vào Connection.

## 8. Những tình huống JDBC mức thấp

**Đọc DatabaseMetaData.** Dùng connection.getMetaData() để đọc product name, driver, thông tin bảng/cột hoặc khả năng JDBC. Công cụ migration/diagnostics có thể cần. Metadata có thể chậm; không lặp lại truy vấn metadata không cần thiết trên mọi request.

**Tạo SQL Array/Struct hoặc dùng driver-specific API.** Connection.createArrayOf(typeName, elements), createStruct, unwrap có thể cần cho chức năng đặc thù. Cú pháp type name và mức hỗ trợ phụ thuộc driver/database; đối tượng java.sql.Array cần được free theo đúng vòng đời. Không tự đóng physical Connection nếu dùng unwrap.

**Nhiều statement trong một callback.** Có thể chuẩn bị, bind và chạy nhiều câu lệnh liên tiếp trên cùng Connection. Nhưng callback không tự tạo một transaction nghiệp vụ nếu không có @Transactional và driver đang autoCommit. Chọn transaction boundary theo nghiệp vụ, không theo cấu trúc mã.

**Vấn đề hiệu năng.** Callback giữ Connection khi đang chạy; thao tác chậm có thể chiếm pool, làm tăng thời gian chờ cho request khác. Tránh gọi mạng hay xử lý tệp dài trong callback. Giới hạn ResultSet, dùng timeout/fetch size hợp lý và đóng tài nguyên ngay khi xong.

**Vấn đề nhiều DataSource.** Một JdbcTemplate sử dụng DataSource B không tự tham gia transaction manager đang quản lý DataSource A, dù hai DataSource trỏ cùng URL database. Với nhiều database, cấu hình manager và chiến lược nhất quán dữ liệu phải được xác định rõ.

## 9. Vì sao không mở raw Connection trực tiếp?

Trong JDBC transaction đồng bộ, Spring thường giữ ConnectionHolder trong ngữ cảnh tài nguyên theo luồng; JdbcTemplate dùng DataSourceUtils để tìm Connection gắn với DataSource phù hợp. Ngược lại, gọi trực tiếp DataSource.getConnection() trên pool gốc (ví dụ HikariDataSource) có thể mượn Connection thứ hai và chạy ngoài transaction của service.

Phản ví dụ sau **không phải class chạy độc lập**; giả sử dataSource là raw pool gốc, các import JDBC tồn tại:

~~~java
@Transactional
public void unsafeInsert() throws SQLException {
    try (Connection raw = dataSource.getConnection();
         PreparedStatement insert = raw.prepareStatement(
                 "INSERT INTO audit_events(category, message) VALUES (?, ?)")) {
        insert.setString(1, "OUTSIDE");
        insert.setString(2, "Independent connection");
        insert.executeUpdate();
    }
    throw new IllegalStateException("Rollback service");
}
~~~

Nếu raw Connection autoCommit=true, INSERT có thể commit trước khi transaction Spring rollback. **Ngoại lệ cần nhớ:** TransactionAwareDataSourceProxy được Spring thiết kế để getConnection() nhận biết transaction. Không khái quát rằng mọi implement DataSource.getConnection() đều bypass; phải biết loại proxy/pool và DataSource mà transaction manager quản lý.

Nếu bắt buộc dùng JDBC trực tiếp ngoài JdbcTemplate, cách phối hợp với Spring là DataSourceUtils.getConnection(dataSource) cùng DataSourceUtils.releaseConnection(connection, dataSource) trong finally; không tự dùng try-with-resources để close Connection đã gắn với Spring transaction.

## 10. Những lỗi phổ biến

- **Dùng ConnectionCallback cho mọi SELECT:** tự viết code thừa so với query/RowMapper.
- **Đóng Connection trong callback:** vi phạm quyền sở hữu tài nguyên của Spring.
- **Không đóng Statement/ResultSet:** gây rò rỉ tài nguyên JDBC hoặc giữ cursor quá lâu.
- **Gọi commit/rollback thủ công:** làm transaction của service không còn đáng tin.
- **Bắt rồi nuốt SQLException:** khiến service có thể commit dù thao tác thất bại.
- **Trả ResultSet ra caller:** caller có thể dùng khi tài nguyên đã đóng hoặc release.
- **Nghĩ nhiều statement trong một callback tự atomic:** không đúng khi không có transaction.
- **Mở raw DataSource.getConnection() khi service đang transactional:** có thể lấy Connection ngoài transaction.
- **Gọi @Transactional qua self-invocation:** trong Spring proxy mode, annotation có thể bị bỏ qua khi cùng đối tượng tự gọi.
- **Chuyển Connection sang @Async hoặc thread khác:** Spring transaction đồng bộ thường không tự lan truyền sang luồng mới.
- **Lạm dụng JDBC vendor API mà không kiểm tra driver:** metadata, generated keys và SQL type có thể khác nhau theo database.
- **Giữ callback quá lâu:** pool cạn, tăng latency và timeout.

## 11. Bài tập và tự kiểm tra

1. Chạy ví dụ, xác nhận INFO=1 sau commit và ERROR=0 sau lần rollback.
2. Thử một category dài quá VARCHAR(32), kiểm tra SQLException từ driver được JdbcTemplate chuyển sang DataAccessException (subtype tùy translator/driver).
3. Thay SELECT COUNT(*) trong repository bằng queryForObject và so sánh khả năng đọc mã, số lượng tài nguyên phải tự đóng.
4. Nếu service không có @Transactional, thử dự đoán điều gì xảy ra khi INSERT đầu đã auto-commit nhưng câu SQL tiếp theo lỗi.
5. Giải thích vì sao generatedKey ResultSet phải đọc trước khi PreparedStatement đóng.
6. Khi nào dùng ConnectionCallback thay vì PreparedStatementCallback?
7. Tại sao JDBC Connection trong callback không nên được trả vào một CompletableFuture hoặc giữ trong singleton field?
8. Nếu JdbcTemplate và transaction manager trỏ đến hai DataSource khác nhau, có thể mong chờ rollback chung không?
9. Vì sao TransactionAwareDataSourceProxy làm kết luận về DataSource.getConnection() thay đổi?
10. Tại sao callback vẫn cần DTO đã materialize và không nên trả Stream còn phụ thuộc ResultSet?

**Ghi nhớ:** ConnectionCallback mở ra API JDBC mức Connection bên trong hạ tầng JdbcTemplate. Nó giữ các lợi ích cốt lõi của Spring JDBC: chọn Connection tham gia transaction phù hợp, dịch SQLException và release connection. Lập trình viên phải đóng đúng Statement/ResultSet, tránh can thiệp commit/rollback, giữ phạm vi callback ngắn và trả dữ liệu Java có vòng đời độc lập.

### Tài liệu tham khảo

- Spring JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- JdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- ConnectionCallback Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ConnectionCallback.html
- DataSourceUtils Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
