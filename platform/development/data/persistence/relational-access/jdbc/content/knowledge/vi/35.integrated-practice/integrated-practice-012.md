# Đưa DAO vào ứng dụng Spring với ranh giới giao dịch đúng

Khi một ứng dụng Java bắt đầu bằng JDBC thuần, từng DAO (*Data Access Object*) thường tự gọi `DataSource.getConnection()`, tạo `PreparedStatement`, chạy SQL rồi đóng tài nguyên. Cách viết này có thể phù hợp với một thao tác đọc độc lập. Nhưng khi phát triển thành một ứng dụng Spring có nhiều DAO phối hợp để hoàn thành **một nghiệp vụ nguyên tử**, mỗi DAO tự mở và commit một kết nối riêng sẽ trở thành rủi ro: một bước thành công có thể được lưu vĩnh viễn dù bước tiếp theo thất bại.

Trong bài thực hành tổng hợp này, ta **chuyển một luồng đăng ký khóa học sang Spring JDBC**, bảo đảm ba thao tác sau cùng thuộc **một transaction**:

1. Giữ một chỗ trống trong khóa học.
2. Tạo bản ghi đăng ký cho học viên.
3. Ghi sự kiện vào bảng outbox để một worker có thể xử lý sau commit.

Ta sử dụng `JdbcTemplate` cho hai DAO đầu, cố ý giữ một DAO dùng **JDBC thuần** để luyện cách tham gia transaction bằng `DataSourceUtils`, rồi đặt ranh giới `@Transactional` tại Service. Cuối cùng, integration test xác minh **commit khi thành công**, **rollback khi thất bại**, không rò rỉ dữ liệu giữa các lần chạy và không mắc bẫy rollback tự động của test framework.

Bài thuộc module **JDBC**: vẫn thực hành driver, `DataSource`, `PreparedStatement`, `ResultSet`, SQL tham số hóa, CRUD, transaction, số hàng cập nhật, ràng buộc quan hệ và xử lý lỗi. **Spring là lớp điều phối trên JDBC**, không thay thế việc hiểu cách kết nối và SQL hoạt động.

## 1. Mục tiêu, phạm vi và kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Xác định **DAO chỉ quản lý SQL** và **Service quản lý transaction của use case**.
- Đọc một ví dụ DAO JDBC cũ và chỉ ra vì sao `autoCommit = true` có thể gây ghi dữ liệu một phần.
- Đưa DAO vào các Spring bean qua constructor injection, dùng cùng `DataSource` và transaction manager.
- Kết hợp `JdbcTemplate` với `PreparedStatement` thuần mà vẫn dùng **cùng connection do Spring quản lý**.
- Biết khi nào dùng `@Transactional(rollbackFor = SQLException.class)` với checked exception.
- Phân biệt lỗi `DataAccessException` của Spring JDBC với `SQLException` của JDBC thuần.
- Xử lý an toàn việc giữ chỗ đồng thời bằng `UPDATE` có điều kiện, kiểm tra update count và unique constraint.
- Viết integration test quan sát dữ liệu đã commit sau lời gọi Service, test rollback khi trùng đăng ký hoặc hết chỗ.
- Nhận diện các giới hạn của proxy `@Transactional`, self-invocation, `REQUIRES_NEW`, `@Async` và commit không rõ kết quả.

**Phạm vi:** Một cơ sở dữ liệu quan hệ có hỗ trợ transaction. Không dùng JPA/Hibernate, không tự dựng XA/distributed transaction, không giả định tất cả DBMS có cùng cú pháp tự sinh khóa. Ví dụ hướng tới **Java 17+ và Spring Boot 3.x/Spring JDBC**; khi dùng phiên bản khác, kiểm tra tài liệu API tương ứng.

### Tiêu chí hoàn thành bài lab

| Tiêu chí | Kiểm chứng |
| --- | --- |
| Đăng ký hợp lệ | Số ghế giảm đúng một, có một đăng ký và một outbox event |
| Đăng ký trùng cùng học viên/khóa học | Unique constraint báo lỗi; số ghế **không** bị trừ thêm |
| Khóa học hết chỗ | Không tạo đăng ký hoặc outbox event |
| DAO JDBC thuần tham gia Spring transaction | Nếu DAO cuối lỗi, hai DAO trước cũng rollback |
| Lời gọi đi qua Spring proxy | `@Transactional` thực sự được áp dụng |
| Test độc lập | Fixture có định danh riêng và cleanup; không dùng DB sản xuất |
| Không tự quản lý transaction trong DAO | Không có `commit()`, `rollback()` hoặc `setAutoCommit(false)` trong ba DAO |

## 2. Bắt đầu từ vấn đề của thiết kế DAO cũ

Một phiên bản đơn giản hóa của hệ thống trước khi đưa vào Spring:

```java
// Ví dụ KHÔNG phù hợp khi nghiệp vụ phải nguyên tử qua nhiều DAO.
public void reserveSeatLegacy(DataSource dataSource, long courseId)
        throws SQLException {

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "UPDATE classroom_course "
                 + "SET available_seats = available_seats - 1 "
                 + "WHERE course_id = ? AND available_seats > 0")) {

        ps.setLong(1, courseId);
        ps.executeUpdate(); // Thậm chí chưa kiểm tra update count.
        // Connection có thể vẫn ở autoCommit=true.
    }
}
```

Nếu sau khi trừ ghế, một DAO khác tự lấy connection và chèn đăng ký gặp lỗi unique constraint, bước giảm ghế **có thể đã được commit**. Việc các DAO cùng nhận một đối tượng `DataSource` không bảo đảm chúng cùng dùng một physical connection hoặc một transaction.

```text
THIẾT KẾ CŨ
RegistrationService
    +-- CourseDao.getConnection()       -> UPDATE -> auto-commit
    +-- EnrollmentDao.getConnection()   -> INSERT -> lỗi
    +-- OutboxDao.getConnection()       -> chưa chạy

Hậu quả: số ghế có thể đã giảm dù học viên không được đăng ký.

THIẾT KẾ MỚI
Spring proxy -> @Transactional RegistrationService
    +-- CourseSeatDao (JdbcTemplate)       \
    +-- EnrollmentDao (JdbcTemplate)        > cùng Spring transaction
    +-- RegistrationOutboxDao (raw JDBC)   /
           |
       Thành công -> Spring commit
       Thất bại   -> Spring rollback
```

Điểm thay đổi quan trọng nhất là **quyền sở hữu transaction được chuyển khỏi từng DAO**. Trong Spring imperative transaction management, Service được gọi qua proxy, Spring mở hoặc tham gia transaction và liên kết connection phù hợp với thread xử lý lời gọi.

## 3. Chuẩn bị ứng dụng Spring JDBC

Với một dự án Spring Boot Maven có quản lý phiên bản qua Spring Boot parent/BOM, các phụ thuộc liên quan:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <!-- Thêm JDBC driver tương ứng DBMS test/prod của bạn.
         Version lấy từ BOM hoặc khai báo theo dự án. -->
</dependencies>
```

Đây là phần **dependencies minh họa**, chưa phải toàn bộ `pom.xml` chạy độc lập; dự án cần cấu hình Java 17+, phiên bản Spring Boot phù hợp, JDBC driver và thông số kết nối. Spring Boot thường tự tạo `JdbcTemplate` và transaction manager khi chỉ có một `DataSource` phù hợp và điều kiện auto-configuration được đáp ứng; **không tự đăng ký manager thứ hai** nếu ứng dụng đã có manager được Boot cấu hình.

Nếu dùng Spring Framework không qua Boot, có thể khai báo transaction manager JDBC rõ ràng:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JdbcTransactionConfig {

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

`DataSource` ở đây phải được tạo bởi cấu hình của ứng dụng hoặc connection pool. Spring Boot đã auto-configure các bean tương ứng thì **không copy thêm `JdbcTransactionConfig` một cách máy móc**.

Với một database và JDBC local transaction, `JdbcTransactionManager` hoặc `DataSourceTransactionManager` đều là những lựa chọn phù hợp. Một transaction manager chỉ quản lý những thao tác **tham gia đúng `DataSource` của nó**; cùng JDBC URL nhưng hai DataSource/pool độc lập không phải tự nhiên cùng một transaction.

### Cách bố trí mã tham khảo

```text
application
├── RegistrationApplication.java
├── dao
│   ├── CourseSeatDao.java
│   ├── EnrollmentDao.java
│   └── RegistrationOutboxDao.java
├── service
│   ├── RegistrationService.java
│   └── NoSeatAvailableException.java
└── test
    └── RegistrationServiceIT.java
```

Đây là **sơ đồ tổ chức**, không phải yêu cầu phải tạo thêm các file trong bài học. Các snippet bên dưới giả định cùng package hoặc import đầy đủ lớp tương ứng; Java source thực tế phải có `package` và vị trí thư mục theo dự án.

## 4. DDL và ràng buộc dữ liệu của bài thực hành

Thiết kế ba bảng:

```sql
-- DDL minh họa gần SQL chuẩn.
-- GENERATED ALWAYS AS IDENTITY / CHECK cần điều chỉnh theo DBMS.
CREATE TABLE classroom_course (
    course_id       BIGINT PRIMARY KEY,
    title           VARCHAR(120) NOT NULL,
    available_seats INTEGER NOT NULL
        CHECK (available_seats >= 0)
);

CREATE TABLE classroom_enrollment (
    enrollment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id     BIGINT NOT NULL,
    student_id    VARCHAR(64) NOT NULL,

    FOREIGN KEY (course_id)
        REFERENCES classroom_course(course_id),
    UNIQUE (course_id, student_id)
);

CREATE TABLE registration_outbox (
    event_id      VARCHAR(36) PRIMARY KEY,
    enrollment_id BIGINT NOT NULL,
    event_type    VARCHAR(32) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (enrollment_id)
        REFERENCES classroom_enrollment(enrollment_id)
);
```

Mục đích của từng ràng buộc:

| Ràng buộc | Bảo vệ điều gì? |
| --- | --- |
| `classroom_course.course_id` là khóa chính | Một khóa học chỉ có một bản ghi số ghế |
| `CHECK (available_seats >= 0)` | Không cho phép ghi số ghế âm khi engine hỗ trợ constraint |
| `UNIQUE (course_id, student_id)` | Một học viên không thể có hai đăng ký cùng khóa học |
| FK enrollment → course | Không đăng ký vào khóa học không tồn tại |
| FK outbox → enrollment | Event nội bộ liên quan tới một đăng ký có thật |
| `event_id` là khóa duy nhất | Có thể nhận diện event khi worker xử lý lại |

Một số DBMS yêu cầu cú pháp tự sinh ID khác (ví dụ `IDENTITY`/`AUTO_INCREMENT` hoặc sequence). Driver cũng có khác biệt khi lấy generated keys. **Hãy chạy migration bằng dialect đúng với DBMS**, không cố dùng nguyên DDL minh họa trên mọi hệ.

### Giao ước nghiệp vụ

Một yêu cầu `register(courseId, studentId)`:

1. Chỉ nhận `courseId > 0` và `studentId` khác rỗng, độ dài hợp lệ.
2. Chỉ đăng ký được khi `available_seats > 0`.
3. Một cặp `(courseId, studentId)` chỉ tồn tại một lần.
4. Đăng ký thành công phải tạo một event `ENROLLED` trong **cùng DB transaction**.
5. Nếu bất kỳ bước nào thất bại, không được giữ số ghế đã giảm hoặc một nửa bản ghi đăng ký.

Để giữ lab tập trung, một học viên chưa có bảng riêng; `student_id` là chuỗi định danh được ứng dụng cung cấp. Bài production có thể thêm bảng học viên, điều kiện thời gian, phân quyền, trạng thái học phí và các unique constraints bổ sung.

## 5. DAO thứ nhất: giữ chỗ bằng `JdbcTemplate.update`

Không viết `SELECT available_seats` rồi lấy kết quả Java để tính và ghi lại số ghế mới; hai transaction có thể cùng đọc giá trị cũ và cùng ghi đè. Thay vào đó, thực hiện một câu **`UPDATE` có điều kiện**:

```sql
UPDATE classroom_course
SET available_seats = available_seats - 1
WHERE course_id = ? AND available_seats > 0;
```

**Tệp `NoSeatAvailableException.java`:**

```java
public class NoSeatAvailableException extends RuntimeException {
    public NoSeatAvailableException(long courseId) {
        super("Unknown course or no available seat: " + courseId);
    }
}
```

**Tệp `CourseSeatDao.java`:**

```java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CourseSeatDao {
    private static final String RESERVE_SQL = """
            UPDATE classroom_course
            SET available_seats = available_seats - 1
            WHERE course_id = ? AND available_seats > 0
            """;

    private final JdbcTemplate jdbc;

    public CourseSeatDao(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    public void reserveOne(long courseId) {
        int updated = jdbc.update(RESERVE_SQL, courseId);
        if (updated == 0) {
            throw new NoSeatAvailableException(courseId);
        }
        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one course row, got " + updated);
        }
    }
}
```

**Vì sao `JdbcTemplate` tham gia transaction?** Khi được cấu hình với `DataSource` phù hợp, `JdbcTemplate` sử dụng cơ chế lấy connection của Spring, có khả năng dùng connection đã được transaction manager liên kết với thread. DAO không tự gọi `commit()` hay `rollback()`; `jdbc.update(...)` trả update count và Spring quản lý statement/connection theo phạm vi thao tác.

### Kiểm tra update count trước khi đi bước tiếp

| `jdbc.update` trả về | Diễn giải |
| ---: | --- |
| `1` | Đã giảm đúng một hàng **trong transaction hiện tại** |
| `0` | Không có khóa học hoặc không còn ghế |
| Khác `0`/`1` | Bất thường với điều kiện theo khóa chính; cần báo lỗi |

**Giảm ghế thành công không đồng nghĩa đã commit**. Nếu DAO đăng ký học viên hoặc outbox thất bại về sau, transaction phải rollback cả lần giảm ghế này. Với nhiều đăng ký đồng thời, DB cần dùng cơ chế locking/MVCC thích hợp và kiểm tra điều kiện tại thời điểm cập nhật; cần integration test trên đúng DBMS/isolation level.

## 6. DAO thứ hai: chèn đăng ký và lấy khóa sinh

DAO sử dụng `JdbcTemplate` với `GeneratedKeyHolder` để nhận `enrollment_id`, sau đó Service sẽ truyền khóa cho outbox DAO.

**Tệp `EnrollmentDao.java`:**

```java
import java.sql.PreparedStatement;
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class EnrollmentDao {
    private static final String INSERT_SQL = """
            INSERT INTO classroom_enrollment(course_id, student_id)
            VALUES (?, ?)
            """;

    private final JdbcTemplate jdbc;

    public EnrollmentDao(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    public long insert(long courseId, String studentId) {
        KeyHolder keys = new GeneratedKeyHolder();

        int updated = jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    INSERT_SQL, new String[] { "enrollment_id" });
            ps.setLong(1, courseId);
            ps.setString(2, studentId);
            return ps;
        }, keys);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one enrollment row, got " + updated);
        }
        Number value = keys.getKey();
        if (value == null || value.longValue() <= 0) {
            throw new IllegalStateException(
                    "Driver returned no valid enrollment_id");
        }
        return value.longValue();
    }
}
```

`JdbcTemplate` đóng statement và quản lý connection của callback. **Không đóng `connection` trong `PreparedStatementCreator`**, vì connection thuộc về cơ chế giao dịch Spring.

Lưu ý các giới hạn:

- `prepareStatement(sql, columnNames)` và `GeneratedKeyHolder` phụ thuộc khả năng generated keys của JDBC driver. Với một số driver/DB, cần overload `Statement.RETURN_GENERATED_KEYS` hoặc cú pháp trả khóa chuyên biệt.
- `keys.getKey()` kỳ vọng **một khóa số duy nhất**. Nếu DB trả nhiều khóa hoặc kiểu khác, hãy dùng contract thích hợp và kiểm tra chính xác.
- Unique constraint `(course_id, student_id)` là bảo vệ cuối cùng chống đăng ký trùng; một câu `SELECT` kiểm tra trước đó **không đủ** dưới concurrency.
- Nếu unique constraint bị vi phạm, `JdbcTemplate` thường dịch `SQLException` thành `DataAccessException` unchecked như `DataIntegrityViolationException` (phân loại chính xác tùy DB/translator).

**Không dùng `SELECT MAX(enrollment_id)`** để tìm ID vừa tạo: đó có thể là ID của transaction khác. Sequence/identity cũng có thể tạo khoảng trống sau rollback; test không được giả định ID phải liên tiếp.

## 7. DAO thứ ba: JDBC thuần nhưng vẫn trong Spring transaction

Đây là phần luyện tập quan trọng: giữ cách viết JDBC nguyên bản với `Connection`/`PreparedStatement`, nhưng **không** tự `getConnection()` từ `DataSource` một cách tùy ý khi đang có Spring transaction.

Spring cung cấp `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(connection, dataSource)`. Khi có transaction JDBC imperative đang hoạt động trên cùng thread và cùng DataSource, `DataSourceUtils` tìm connection được **Spring liên kết với transaction**. Nó không đóng physical connection của transaction khi DAO hoàn thành.

**Tệp `RegistrationOutboxDao.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;

@Repository
public class RegistrationOutboxDao {
    private static final String INSERT_SQL = """
            INSERT INTO registration_outbox
                (event_id, enrollment_id, event_type)
            VALUES (?, ?, ?)
            """;

    private final DataSource dataSource;

    public RegistrationOutboxDao(DataSource dataSource) {
        this.dataSource =
                Objects.requireNonNull(dataSource, "dataSource");
    }

    // Đây là checked SQLException từ JDBC thuần.
    public void insert(
            String eventId, long enrollmentId,
            String eventType) throws SQLException {

        Connection connection =
                DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement ps =
                         connection.prepareStatement(INSERT_SQL)) {
                ps.setString(1, eventId);
                ps.setLong(2, enrollmentId);
                ps.setString(3, eventType);

                int updated = ps.executeUpdate();
                if (updated != 1) {
                    throw new SQLException(
                            "Expected exactly one outbox row");
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

### Vì sao không dùng `try (Connection connection = dataSource.getConnection())`?

Đoạn sau là **anti-pattern** trong DAO phải tham gia transaction của Service:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(SQL)) {
    // Có thể đang dùng connection mới ngoài transaction của Service.
}
```

Nếu đó là connection khác với connection mà Spring đã bind, outbox có thể commit riêng, không thấy `classroom_enrollment` chưa commit hoặc gây lỗi FK. `try-with-resources` vẫn được dùng để **đóng `PreparedStatement`**, nhưng connection lấy từ `DataSourceUtils` phải được **release qua `DataSourceUtils.releaseConnection`**, không tùy ý đóng trong DAO.

**Ngoại lệ:** Có những lớp proxy như `TransactionAwareDataSourceProxy` được Spring cung cấp để code JDBC bên thứ ba gọi `DataSource.getConnection()/close()` vẫn có thể tham gia transaction. Nhưng không được giả định một `DataSource` bất kỳ là proxy đó. Khi tự viết DAO, dùng `JdbcTemplate` hoặc `DataSourceUtils` là cách rõ ràng hơn.

### Outbox không có nghĩa event đã được gửi

`RegistrationOutboxDao.insert` chỉ ghi một **bản ghi DB** trong cùng transaction; nó **không gửi** message ra broker hoặc email. Worker bên ngoài chỉ nên đọc outbox **đã commit**, gửi event rồi cập nhật trạng thái theo thiết kế riêng. Worker cũng cần xử lý gửi lặp/idempotency; DB transaction không biến broker và database thành một giao dịch phân tán.

## 8. Service là nơi đặt ranh giới `@Transactional`

Đến đây, cả ba DAO **không** tự mở transaction và không gọi `commit()`. Service điều phối nghiệp vụ, kiểm tra đầu vào, giữ chỗ, tạo đăng ký rồi ghi outbox. Spring transaction interceptor xác nhận hoặc rollback toàn bộ theo kết quả method.

**Tệp `RegistrationService.java`:**

```java
import java.sql.SQLException;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final CourseSeatDao courseSeatDao;
    private final EnrollmentDao enrollmentDao;
    private final RegistrationOutboxDao outboxDao;

    public RegistrationService(
            CourseSeatDao courseSeatDao,
            EnrollmentDao enrollmentDao,
            RegistrationOutboxDao outboxDao) {
        this.courseSeatDao =
                Objects.requireNonNull(courseSeatDao, "courseSeatDao");
        this.enrollmentDao =
                Objects.requireNonNull(enrollmentDao, "enrollmentDao");
        this.outboxDao =
                Objects.requireNonNull(outboxDao, "outboxDao");
    }

    // Checked SQLException từ JDBC thuần cũng phải rollback.
    @Transactional(rollbackFor = SQLException.class)
    public long register(long courseId, String studentId)
            throws SQLException {

        if (courseId <= 0) {
            throw new IllegalArgumentException(
                    "courseId must be positive");
        }
        if (studentId == null || studentId.isBlank()
                || studentId.length() > 64) {
            throw new IllegalArgumentException(
                    "studentId must contain 1..64 characters");
        }

        // Bước 1: giảm số ghế trong transaction hiện tại.
        courseSeatDao.reserveOne(courseId);

        // Bước 2: tạo đăng ký; unique constraint chống đăng ký trùng.
        long enrollmentId = enrollmentDao.insert(
                courseId, studentId);

        // Bước 3: ghi outbox trong cùng transaction JDBC.
        outboxDao.insert(
                UUID.randomUUID().toString(),
                enrollmentId,
                "ENROLLED");

        // Không gọi connection.commit() ở đây.
        // Spring proxy chỉ trả kết quả cho caller sau khi
        // transaction interceptor đã xử lý commit/rollback.
        return enrollmentId;
    }
}
```

Ví dụ caller lấy Service từ Spring container, không dùng `new RegistrationService(...)` ngoài container:

```java
long enrollmentId = registrationService.register(
        42L, "student-123");
System.out.println("Enrollment: " + enrollmentId);
```

Trong một Spring MVC controller, có thể inject Service qua constructor, gọi `register(...)` và chuyển kết quả thành HTTP response. **Không tự bắt mọi exception bên trong Service rồi trả `-1`** nếu nghiệp vụ phải rollback. Hãy để lỗi đi ra ngoài transaction method, sau đó xử lý thành mã phản hồi HTTP ở tầng ngoài hoặc exception handler.

### Vòng đời một lời gọi `register`

```text
Controller -> RegistrationService Spring proxy
                  |
              Bắt đầu transaction
                  |
          CourseSeatDao.reserveOne
                  |
          EnrollmentDao.insert
                  |
          RegistrationOutboxDao.insert
                  |
           +------+-------+
           |              |
      Thành công        Exception
           |              |
        commit          rollback
           |              |
      Trả enrollmentId  Ném lỗi ra caller
```

| Giai đoạn | Trạng thái DB trước commit |
| --- | --- |
| Sau `reserveOne` | Một ghế đã giảm nhưng **chưa commit** |
| Sau `EnrollmentDao.insert` | Đăng ký tồn tại trong transaction của Service; kết nối khác có thể chưa thấy |
| Sau `RegistrationOutboxDao.insert` | Event tồn tại trong cùng transaction; worker khác chưa nên thấy trước commit |
| Sau commit thành công | Cả ba thay đổi được xác nhận cùng nhau |
| Một bước ném lỗi thỏa rollback rule | Spring yêu cầu rollback toàn bộ transaction chưa commit |

Nếu DAO outbox dùng connection ngoài transaction, bài toán nguyên tử sẽ hỏng. Vì vậy, việc viết đúng `DataSourceUtils` ở phần trước **không phải một chi tiết tùy chọn**.

## 9. Vì sao `rollbackFor = SQLException.class` quan trọng?

Spring có quy tắc rollback mặc định truyền thống:

- **`RuntimeException` và `Error`:** yêu cầu rollback.
- **Checked exception** như `SQLException`: không tự yêu cầu rollback theo mặc định nếu chưa cấu hình khác.

Trong lab:

| Nguồn lỗi | Kiểu lỗi thường gặp | Có rollback không? |
| --- | --- | --- |
| `CourseSeatDao` không còn ghế | `NoSeatAvailableException` unchecked | Có, theo quy tắc mặc định |
| `EnrollmentDao` vi phạm unique constraint | `DataIntegrityViolationException`/`DataAccessException` unchecked | Có, theo quy tắc mặc định |
| `RegistrationOutboxDao` JDBC thuần báo lỗi | `SQLException` checked, hoặc được tầng Spring dịch lỗi | Có theo `rollbackFor = SQLException.class` hoặc unchecked rule tương ứng |
| Đầu vào `studentId` không hợp lệ | `IllegalArgumentException` unchecked | Có rollback rule, nhưng chưa có DML nên không có thay đổi |

Nếu bỏ `rollbackFor` mà DAO cuối ném `SQLException` sau khi hai DAO trước đã thay đổi DB, Spring có thể **cố commit** nếu lỗi checked được truyền lên và transaction chưa bị đánh dấu rollback-only. Một DB có thể tự đánh dấu transaction lỗi trong một số trường hợp, nhưng đó **không phải chiến lược rollback ứng dụng đáng tin cậy**.

Một lựa chọn thiết kế khác là để DAO JDBC thuần chuyển `SQLException` sang `DataAccessException` của Spring bằng bộ dịch ngoại lệ tương ứng. Khi đó, Service có thể dựa trên quy tắc unchecked; tuy nhiên, cần giữ thông tin nguyên nhân và phân loại lỗi chính xác, không tùy tiện biến tất cả lỗi thành một `RuntimeException` chung.

### Không bắt rồi nuốt exception trong method có transaction

```java
// Anti-pattern minh họa:
@Transactional
public boolean registerQuietly(...) {
    try {
        // seatDao.reserveOne(...);
        // enrollmentDao.insert(...);
        return true;
    } catch (RuntimeException failure) {
        return false; // Proxy có thể thấy một return thành công.
    }
}
```

Đoạn này không biên dịch nguyên trạng vì `...` là ký hiệu lược bỏ. Nguy cơ thật là một method `@Transactional` bắt hết lỗi rồi trả về bình thường: Spring có thể coi đó là thành công để commit **nếu transaction chưa được đánh dấu rollback-only**. Trong những trường hợp một nhánh bên trong đã đánh dấu rollback-only, caller còn có thể nhận `UnexpectedRollbackException` khi interceptor cố commit ngoài.

Phương án rõ ràng là **để exception phù hợp đi ra khỏi transaction method**, hoặc khi thiết kế yêu cầu bắt lỗi và vẫn rollback, dùng cơ chế đánh dấu rollback-only một cách có chủ đích và kiểm thử. Không dựa vào `return false` để thay thế rollback.

## 10. Khi nào `@Transactional` bị bỏ qua?

Annotation chỉ có hiệu lực nếu Spring thực sự áp dụng transaction advice. Với proxy mode phổ biến, lời gọi phải đi qua **Spring-managed proxy**.

### Self-invocation

```java
@Service
public class RegistrationFacade {
    public void handle() throws SQLException {
        // Gọi trực tiếp trên this, không qua proxy của registerInternal.
        registerInternal();
    }

    @Transactional(rollbackFor = SQLException.class)
    public void registerInternal() throws SQLException {
        // ... nhiều DAO ...
    }
}
```

Nếu `handle()` không có transaction, annotation của `registerInternal()` **không tự được áp dụng** cho lời gọi nội bộ trong proxy mode. Cách giải quyết thường rõ ràng nhất là đưa method transaction sang **một bean riêng** rồi inject bean đó vào caller. Hoặc đặt ranh giới transaction ngay trên public entry point được gọi từ bean khác qua proxy.

Các trường hợp cần lưu ý thêm:

- Tạo Service bằng `new` bên ngoài Spring container khiến Spring không thể intercept lời gọi.
- Method `private`, `final`, một số kiểu visibility hoặc kiểu proxy có thể không được advice như kỳ vọng. Ví dụ lab dùng **public method không final**.
- Nếu project có **nhiều transaction manager**, `@Transactional` phải chọn đúng manager cho DataSource của các DAO, ví dụ `@Transactional(transactionManager = "registrationTxManager")`.
- Với Spring imperative/JDBC, transaction context thông thường gắn với thread. DAO chạy trên thread mới qua `@Async` hoặc `CompletableFuture` **không tự tham gia transaction của thread ban đầu**.
- Không chuyển một `Connection` mutable đang giữ transaction cho nhiều thread để cố “ép” chia sẻ transaction.

### Một DataSource có cấu hình sai cũng phá ranh giới

`JdbcTemplate` dùng `DataSource A`, còn `RegistrationOutboxDao` dùng `DataSource B` có cùng JDBC URL **không** chứng minh chúng cùng connection. Muốn phối hợp các DAO trong một JDBC local transaction phải đảm bảo chúng dùng **đúng DataSource gắn với transaction manager**, hoặc một lớp proxy được Spring hỗ trợ.

Không đồng nhất `@Transactional` với distributed transaction. Nếu một phần ghi sang database khác hoặc gửi message broker, cần cơ chế riêng như saga, outbox, idempotency hoặc transaction phân tán khi hạ tầng hỗ trợ và thật sự cần.

## 11. Propagation: mặc định `REQUIRED` khác `REQUIRES_NEW`

Spring `@Transactional` mặc định dùng `Propagation.REQUIRED`: nếu đã có transaction thì method tham gia, nếu chưa có thì mở transaction mới.

| Propagation | Hành vi | Ảnh hưởng đến bài lab |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại hoặc mở mới | Phù hợp với một Service phối hợp các DAO |
| `MANDATORY` | Phải có transaction hiện tại, nếu không thì lỗi | Có thể dùng ở API nội bộ bắt buộc được gọi trong transaction |
| `REQUIRES_NEW` | Tạm ngưng transaction đang có, tạo transaction độc lập | **Không phù hợp** nếu outbox hoặc enrollment phải rollback cùng Service |
| `NESTED` | Khi được hỗ trợ, dùng savepoint trong một physical transaction | Không phải commit độc lập; phụ thuộc driver/manager |
| `SUPPORTS` | Có transaction thì tham gia, không có thì chạy không transaction | Không bảo đảm use case ghi nguyên tử nếu gọi độc lập |

Nếu `RegistrationOutboxDao` chạy trong một Service khác với `REQUIRES_NEW`, event có thể commit độc lập hoặc **không thấy enrollment chưa commit** vì nó ở một transaction khác. Cả hai đều phá vỡ kỳ vọng “ghế + đăng ký + event là một đơn vị”.

`REQUIRES_NEW` còn có thể yêu cầu thêm connection trong pool: transaction ngoài vẫn giữ connection, transaction trong cần một connection khác. Khi pool nhỏ và nhiều request đồng thời, việc này gây chờ hoặc timeout. Không giải quyết lỗi bằng cách đặt `REQUIRES_NEW` ở mọi DAO.

## 12. Kiểm thử tích hợp: quan sát commit và rollback thật

Unit test với mock DAO giúp xác nhận thứ tự gọi nhưng **không chứng minh** tất cả SQL dùng một transaction. Integration test phải chạy trên **database thật hoặc database test có transaction/constraint tương đương**, kết nối bằng cùng driver/transaction manager dự kiến.

Một bẫy thường gặp: nếu method test mang `@Transactional`, Spring Test có thể tự mở transaction trước test rồi rollback cuối test. Service mặc định `REQUIRED` khi ấy **tham gia transaction của test**, nên việc test xanh không chứng minh Service đã **commit riêng như trong production**.

Để kiểm tra commit/rollback của chính Service, ví dụ sau:

- Dùng `@SpringBootTest` nhưng **không dùng `@Transactional` trên test**.
- Mỗi test tạo một khóa học với ID riêng và `studentId` riêng.
- `@AfterEach` xóa **outbox → enrollment → course** theo khóa fixture, đúng thứ tự foreign key.
- Gọi Service được **inject từ Spring**, không tự `new`.
- Đọc lại DB qua `JdbcTemplate` sau khi lời gọi Service đã hoàn thành.

**Tệp minh họa `RegistrationServiceIT.java`** (JUnit Jupiter):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.SQLException;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class RegistrationServiceIT {
    @Autowired
    private RegistrationService service;

    @Autowired
    private JdbcTemplate jdbc;

    private Long courseId;
    private String studentId;

    @BeforeEach
    void seed() {
        courseId = ThreadLocalRandom.current()
                .nextLong(1L, Long.MAX_VALUE);
        studentId = "student-" + UUID.randomUUID();

        jdbc.update("""
                INSERT INTO classroom_course
                    (course_id, title, available_seats)
                VALUES (?, ?, ?)
                """, courseId, "Spring JDBC Lab", 2);
    }

    @AfterEach
    void cleanup() {
        if (courseId == null) {
            return;
        }
        jdbc.update("""
                DELETE FROM registration_outbox
                WHERE enrollment_id IN (
                    SELECT enrollment_id FROM classroom_enrollment
                    WHERE course_id = ?
                )
                """, courseId);
        jdbc.update(
                "DELETE FROM classroom_enrollment WHERE course_id = ?",
                courseId);
        jdbc.update(
                "DELETE FROM classroom_course WHERE course_id = ?",
                courseId);
    }

    @Test
    void successfulRegistrationCommitsAllThreeSteps()
            throws SQLException {

        long id = service.register(courseId, studentId);
        assertTrue(id > 0L);

        Integer seats = jdbc.queryForObject("""
                SELECT available_seats
                FROM classroom_course WHERE course_id = ?
                """, Integer.class, courseId);
        assertEquals(1, seats.intValue());

        Long enrollmentCount = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM classroom_enrollment
                WHERE enrollment_id = ? AND course_id = ?
                      AND student_id = ?
                """, Long.class, id, courseId, studentId);
        assertEquals(1L, enrollmentCount.longValue());

        Long eventCount = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM registration_outbox
                WHERE enrollment_id = ? AND event_type = ?
                """, Long.class, id, "ENROLLED");
        assertEquals(1L, eventCount.longValue());
    }

    @Test
    void duplicateEnrollmentRollsBackReservedSeat()
            throws SQLException {

        // Lần đầu đã commit, ghế từ 2 còn 1.
        long firstId = service.register(courseId, studentId);
        assertTrue(firstId > 0L);

        // Lần hai: DAO ghế trừ 1 xuống 0 CHƯA COMMIT;
        // unique(course_id, student_id) ở DAO enrollment báo lỗi.
        assertThrows(DataIntegrityViolationException.class,
                () -> service.register(courseId, studentId));

        // Rollback phải khôi phục số ghế về 1, không giữ 0.
        Integer seats = jdbc.queryForObject(
                "SELECT available_seats FROM classroom_course "
                + "WHERE course_id = ?",
                Integer.class, courseId);
        assertEquals(1, seats.intValue());

        Long enrollments = jdbc.queryForObject(
                "SELECT COUNT(*) FROM classroom_enrollment "
                + "WHERE course_id = ? AND student_id = ?",
                Long.class, courseId, studentId);
        assertEquals(1L, enrollments.longValue());

        Long events = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM registration_outbox
                WHERE enrollment_id = ?
                """, Long.class, firstId);
        assertEquals(1L, events.longValue());
    }

    @Test
    void noAvailableSeatDoesNotCreateEnrollmentOrEvent() {
        jdbc.update("""
                UPDATE classroom_course
                SET available_seats = 0 WHERE course_id = ?
                """, courseId);

        assertThrows(NoSeatAvailableException.class,
                () -> service.register(courseId, studentId));

        Long enrollments = jdbc.queryForObject(
                "SELECT COUNT(*) FROM classroom_enrollment "
                + "WHERE course_id = ?",
                Long.class, courseId);
        assertEquals(0L, enrollments.longValue());

        Long events = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM registration_outbox o
                JOIN classroom_enrollment e
                    ON e.enrollment_id = o.enrollment_id
                WHERE e.course_id = ?
                """, Long.class, courseId);
        assertEquals(0L, events.longValue());
    }
}
```

### Điều kiện để test trên thực tế

Đây là ví dụ **Spring Boot Test + JUnit 5**, không phải chương trình Java SE độc lập. Dự án phải có application context, `DataSource`/transaction manager đúng, driver phù hợp và **migration đã tạo ba bảng**. Trong database của test, cần kiểm tra engine có hỗ trợ transaction, unique constraint, foreign key và generated keys.

`ThreadLocalRandom` giúp giảm khả năng trùng `course_id` giữa test chạy đồng thời nhưng **không chứng minh tuyệt đối** không thể trùng; database vẫn phải thực thi unique constraint. `UUID` tạo `studentId`/event ID có xác suất va chạm rất thấp, không thay thế kiểm soát dữ liệu. Đặc biệt, các bảng test không được là bảng production.

Với vài driver hoặc DB, Spring exception translator có thể phân loại lỗi unique constraint khác `DataIntegrityViolationException` cụ thể. Khi port test sang DBMS mới, cần xác minh loại ngoại lệ thực tế và SQLState, thay vì im lặng bắt một lỗi bất kỳ rồi kết luận hệ thống đã xử lý đúng unique constraint.

Cleanup có thể thất bại nếu DB ngắt kết nối hoặc tiến trình CI bị hủy trước `@AfterEach`. Vì thế, **database/schema test riêng cho job** là biện pháp bổ sung quan trọng: có thể hủy toàn bộ môi trường thử nghiệm nếu có dữ liệu sót lại.

## 13. Thử riêng rollback với checked `SQLException`

Integration test ở trên chứng minh rollback khi lỗi từ `JdbcTemplate` hoặc lỗi nghiệp vụ unchecked. Nhưng `@Transactional(rollbackFor = SQLException.class)` còn nhằm xử lý **checked exception**. Muốn kiểm chứng quy tắc này một cách có chủ đích, ta có thể tạo một bean thử nghiệm: nó giảm ghế, rồi ném `SQLException` **sau khi UPDATE đã thành công**.

Bean thử nghiệm này **không phải logic production**, và không dùng để giả lập toàn bộ DB/driver. Nó chỉ xác minh transaction advice nhận một checked exception đã đi ra khỏi phương thức qua Spring proxy.

```java
// Đặt trong một lớp top-level hoặc nested public static class
// của test, có đăng ký làm Spring bean để được proxy.
public static class CheckedRollbackProbe {
    private final CourseSeatDao seats;

    public CheckedRollbackProbe(CourseSeatDao seats) {
        this.seats = seats;
    }

    @Transactional(rollbackFor = SQLException.class)
    public void reserveThenFail(long courseId) throws SQLException {
        seats.reserveOne(courseId);
        throw new SQLException("Injected checked failure");
    }
}
```

Test có thể import một cấu hình chỉ dành cho kiểm thử:

```java
@TestConfiguration
public static class ProbeConfig {
    @Bean
    public CheckedRollbackProbe checkedRollbackProbe(
            CourseSeatDao seats) {
        return new CheckedRollbackProbe(seats);
    }
}
```

Đoạn trên giả định import từ Spring Boot Test `org.springframework.boot.test.context.TestConfiguration`, Spring `@Bean`, `@Transactional` và `java.sql.SQLException`. Khi sử dụng trong một lớp test cụ thể, dùng `@Import(ProbeConfig.class)` và `@Autowired CheckedRollbackProbe probe` để lấy **bean đã qua Spring proxy**. Một phương thức thử nghiệm:

```java
@Test
void checkedSQLExceptionRollsBackSeat() {
    long id = ThreadLocalRandom.current()
            .nextLong(1L, Long.MAX_VALUE);
    jdbc.update("""
            INSERT INTO classroom_course
                (course_id, title, available_seats)
            VALUES (?, ?, ?)
            """, id, "Checked rollback probe", 1);

    try {
        assertThrows(SQLException.class,
                () -> probe.reserveThenFail(id));

        Integer seats = jdbc.queryForObject("""
                SELECT available_seats
                FROM classroom_course WHERE course_id = ?
                """, Integer.class, id);
        assertEquals(1, seats.intValue());
    } finally {
        jdbc.update(
                "DELETE FROM classroom_course WHERE course_id = ?", id);
    }
}
```

Đây là **mảnh test bổ sung**, không phải một class JUnit hoàn chỉnh: `probe` và `jdbc` cần được inject từ Spring, test không được mang `@Transactional`, và môi trường phải có bảng `classroom_course`. Nếu bỏ `rollbackFor` ở bean probe, hành vi có thể thay đổi: Spring có thể không tự yêu cầu rollback chỉ vì `SQLException` checked. Trong một hệ thống thật, các DAO có thể chuyển lỗi thành `DataAccessException` hoặc DB có thể đánh dấu transaction lỗi; vì vậy test riêng này giúp cô lập **quy tắc rollback của Spring** khỏi các tác động khác.

**Không tạo test bằng cách làm hỏng schema production để gây lỗi.** Dùng fixture, cấu hình test và lỗi được điều khiển; không chỉnh `@Transactional` của nghiệp vụ chỉ để một ca test tình cờ xanh.

## 14. Lỗi commit chưa rõ và API đăng ký trùng

Một transaction đúng vẫn còn trường hợp khó: DB đã thực hiện commit, nhưng mạng bị ngắt trước khi ứng dụng nhận được xác nhận. Khi ấy caller có thể nhận exception trong lúc commit, nhưng **không thể kết luận đăng ký chắc chắn chưa tồn tại**.

Ví dụ:

```text
Client gửi register(course=42, student=A)
       |
       v
Spring transaction -> ghi ghế, enrollment, outbox
       |
       v
DB COMMIT hoàn tất
       |
      Mất kết nối trước khi server trả ACK
       |
       v
Client thấy lỗi, thử lại?
```

Ở ví dụ lab, unique constraint `(course_id, student_id)` ngăn tạo **hai đăng ký** cho cùng cặp. Nhưng đây **chưa phải một API idempotent hoàn chỉnh**:

- Lần gọi lặp có thể nhận lỗi “hết ghế” do `reserveOne` chạy **trước** khi DAO chèn đăng ký, dù đăng ký trước đã thành công.
- Nếu còn ghế, lần gọi lặp sẽ trừ ghế tạm thời rồi gặp unique constraint và rollback. Điều này giữ dữ liệu nhất quán nhưng trả lỗi, không tự trả lại `enrollment_id` cũ.
- Một API idempotent phải xác định rõ **request key**, kết quả đã xử lý và cách đối soát khi commit không rõ trạng thái.

Trong production, có thể thêm bảng `registration_request` hoặc cột `request_id` với unique constraint để liên kết một yêu cầu nghiệp vụ duy nhất với kết quả của nó. Các lần gọi lặp cùng key phải được xử lý theo một hợp đồng đã định nghĩa: trả kết quả cũ nếu đã hoàn tất, hoặc chờ/đối soát trạng thái nếu yêu cầu đang xử lý. Không retry mọi `DataAccessException` vô hạn.

### Đừng retry bên trong transaction đã lỗi

Khi một câu `INSERT` bị DB từ chối vì unique constraint hoặc deadlock, không nên tiếp tục chèn outbox trên **cùng transaction bị lỗi**. Với một số DB, transaction đã bị đánh dấu không thể tiếp tục. Nếu lỗi là *transient* và việc retry an toàn, phải kết thúc/rollback transaction hiện tại rồi thực hiện lại **toàn use case trong transaction mới**, với giới hạn số lần và backoff thích hợp.

Lỗi thiếu ghế hoặc đăng ký trùng là kết quả nghiệp vụ/constraint có ý nghĩa, **không phải lỗi tạm thời nên thử lại vô hạn**.

## 15. Phân biệt atomicity, concurrency và outbox

`@Transactional` giải quyết **nguyên tử** giữa các lệnh tham gia cùng một DB transaction; nó không tự bảo vệ mọi xung đột đồng thời hoặc external side effect.

### Nhiều học viên cùng đăng ký khi chỉ còn một ghế

Giả sử `available_seats = 1`. Hai transaction đồng thời chạy:

```sql
UPDATE classroom_course
SET available_seats = available_seats - 1
WHERE course_id = ? AND available_seats > 0;
```

Với database có cơ chế khóa hàng và isolation phù hợp, chỉ một transaction nên giảm ghế thành công; transaction còn lại có thể chờ rồi nhận update count `0`, hoặc gặp một lỗi concurrency cần xử lý theo chính sách DB. `CHECK available_seats >= 0` bổ sung hàng rào dữ liệu. **Không dùng một câu `SELECT` ngoài transaction rồi tin rằng kết quả số ghế không thay đổi**.

Muốn thử concurrency, có thể chạy hai tác vụ với hai student ID khác nhau trên cùng course chỉ có một ghế và kiểm tra:

1. Có nhiều nhất **một đăng ký được commit**.
2. `available_seats` không âm.
3. Số outbox event được commit đúng bằng số đăng ký thành công.
4. Các connection được trả về pool; không có deadlock chờ vô hạn.

Các phép thử cần có thời gian chờ giới hạn và đồng bộ bằng `CountDownLatch`/barrier thay vì đoán thứ tự thread qua `Thread.sleep(...)`. Một pool chỉ có một connection không tái hiện được hai transaction DB chạy đồng thời như kỳ vọng.

### Outbox được commit cùng đăng ký, việc gửi xảy ra sau

```text
RegistrationService @Transactional
  CourseSeatDao.reserveOne(...)
  EnrollmentDao.insert(...)
  RegistrationOutboxDao.insert(...)
         |
       COMMIT
         |
   Worker đọc outbox đã commit
         |
   Gửi event tới broker (có thể retry)
         |
   Consumer cần deduplication/idempotency
```

Nếu đăng ký rollback, outbox insert cũng rollback. Tuy nhiên, worker có thể gửi event thành công rồi gặp lỗi trước khi đánh dấu “đã gửi”, nên lần chạy sau có thể gửi trùng. Outbox **không bảo đảm exactly-once delivery** chỉ nhờ transaction JDBC. Thiết kế event ID, trạng thái xử lý, retry và idempotent consumer vẫn cần thiết.

### Khi nào cần một transaction khác?

Nếu nghiệp vụ phải cập nhật **hai database khác nhau**, một `JdbcTransactionManager` chỉ quản lý transaction trên **một `DataSource`**. Muốn đảm bảo tính nguyên tử trên nhiều tài nguyên có thể cần JTA/XA khi hạ tầng phù hợp, hoặc một workflow saga/outbox có bước bù và khả năng phục hồi.

Không đổi `@Transactional` thành `REQUIRES_NEW` ở từng DAO để “tăng độ an toàn”; đó là cách dễ tạo **commit một phần** và cần thêm connection từ pool.

## 16. Gỡ lỗi khi `@Transactional` không hoạt động

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng kiểm tra |
| --- | --- | --- |
| Ghế giảm dù `EnrollmentDao.insert` lỗi | DAO tự commit hoặc khác transaction | Kiểm tra `DataSource`, `DataSourceUtils`, `JdbcTemplate` và transaction manager |
| Spring không rollback một `SQLException` | Checked exception không thuộc rollback rule | `rollbackFor` hoặc exception translation |
| Test xanh nhưng production commit khác | Test `@Transactional` đã bọc bên ngoài Service | Chạy test không có transaction test, quan sát commit thật |
| `@Transactional` dường như không chạy | Service tạo bằng `new`, self-invocation, proxy không áp dụng | Lấy bean từ Spring, gọi qua proxy, kiểm tra cấu hình |
| Outbox nhìn thấy enrollment “chưa tồn tại” | DAO dùng connection/transaction độc lập | Dùng cùng DataSource và Spring-bound connection |
| `getGeneratedKeys` không trả ID | Driver/DB không hỗ trợ overload đã chọn | Kiểm tra generated-key API/cú pháp DB |
| Có hai đăng ký cùng học viên | Thiếu unique constraint ở DB | Tạo unique key `(course_id, student_id)` và test concurrency |
| Tồn kho âm hoặc số ghế âm | SQL kiểm tra rồi ghi tách rời, thiếu constraint | Atomic conditional UPDATE và ràng buộc DB |
| Transaction giữ connection quá lâu | Gọi I/O mạng hoặc xử lý nặng trong Service | Giữ transaction ngắn, chuyển side effect ra worker |
| Pool hết connection khi `REQUIRES_NEW` | Transaction lồng cần connection độc lập | Dùng `REQUIRED` cho một use case nguyên tử |
| DAO chạy ở `@Async` không rollback cùng Service | Transaction context gắn với thread | Thiết kế transaction riêng và outbox |
| Client thấy lỗi nhưng DB có bản ghi | Lỗi hoặc mất phản hồi tại commit | Request ID, đối soát, retry có kiểm soát |

### Quan sát trạng thái transaction khi chẩn đoán

Trong môi trường test hoặc diagnostic, Spring có các API như `TransactionSynchronizationManager.isActualTransactionActive()` để kiểm tra liệu một transaction Spring có đang hoạt động trên thread hay không. Có thể in giá trị này ở Service và DAO để phát hiện lời gọi bỏ qua proxy.

Nhưng **boolean “transaction active” không chứng minh mọi DAO dùng cùng physical connection**. Nếu DAO mở một DataSource khác, transaction trên thread vẫn có thể tồn tại mà câu SQL của DAO không tham gia. Bằng chứng có giá trị hơn là **integration test rollback xuyên qua tất cả DAO** và xác minh DB sau khi lời gọi kết thúc.

Không ghi toàn bộ JDBC URL, mật khẩu, token hoặc dữ liệu cá nhân vào log để chẩn đoán. Có thể ghi `SQLState`, mã lỗi nhà cung cấp, tên thao tác và correlation ID không nhạy cảm, kèm metrics của connection pool để hiểu lỗi.

## 17. Checklist khi refactor DAO JDBC cũ sang Spring

1. **Xác định nghiệp vụ nguyên tử.** Liệt kê các lệnh SQL phải thành công cùng nhau, kể cả audit/outbox.

2. **Chọn một nguồn `DataSource`.** Dùng cùng nguồn phù hợp cho transaction manager và các DAO của use case.

3. **Đặt transaction boundary tại Service.** Method public được gọi qua Spring bean/proxy, không phải gọi nội bộ `this`.

4. **Bỏ commit/rollback khỏi DAO.** DAO dùng `JdbcTemplate` hoặc nhận đúng connection đang thuộc transaction; không tự quản lý vòng đời toàn use case.

5. **Nâng cấp JDBC thuần có chủ đích.** Với DAO chưa chuyển sang `JdbcTemplate`, dùng `DataSourceUtils.getConnection/releaseConnection`; đóng statement/result set trong `try-with-resources`.

6. **Kiểm tra SQL tham số hóa.** Mọi giá trị đi qua placeholder `?`, không ghép input người dùng vào SQL.

7. **Kiểm tra update counts và constraints.** `UPDATE` trả `0` có thể là kết quả nghiệp vụ, không phải thành công.

8. **Chọn rollback rules.** Checked `SQLException` phải được xử lý theo hợp đồng; tránh nuốt lỗi và tránh `REQUIRES_NEW` không cần thiết.

9. **Viết integration tests không che commit.** Bao gồm thành công, lỗi ở DAO giữa/cuối, duplicate, thiếu ghế, generated keys, concurrency.

10. **Đối soát tài nguyên ngoài DB.** Dùng outbox/idempotency hoặc chính sách bù cho side effect; không gửi email/HTTP rồi hy vọng rollback DB có thể thu hồi.

11. **Đưa vào vận hành an toàn.** Có metrics pool, SQL exceptions, transaction latency, thời gian giữ connection và chính sách retry rõ ràng.

12. **Kiểm tra trên đúng DBMS/driver.** Khác biệt DDL, unique constraint, isolation và generated keys phải được phát hiện trước production.

## 18. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Xác định transaction owner.** Có ba DAO giữ ghế, tạo đăng ký và ghi event. DAO nào nên gọi `Connection.commit()` khi dùng `@Transactional`?

**Đáp án:** Không DAO nào. Ranh giới tại Service; Spring transaction manager commit/rollback toàn use case.

**Bài 2 — Cùng JDBC URL là đủ?** `EnrollmentDao` dùng `DataSource A`, `RegistrationOutboxDao` dùng `DataSource B` có cùng URL. Có chắc cùng transaction không?

**Đáp án:** Không. Hai DataSource có thể cấp hai connection/transaction riêng. Cần dùng đúng connection do Spring manager quản lý hoặc abstraction hỗ trợ thích hợp.

**Bài 3 — `DataSourceUtils`.** Vì sao DAO thuần nên gọi `releaseConnection(...)` trong `finally` thay vì `connection.close()` trực tiếp?

**Đáp án:** Vì connection có thể được Spring giữ cho transaction hiện tại. `releaseConnection` tôn trọng quyền sở hữu và không đóng connection transaction trước khi Service hoàn tất.

**Bài 4 — Checked exception.** `RegistrationOutboxDao` ném `SQLException` sau khi ghế đã giảm và enrollment đã chèn. Nếu chỉ dùng `@Transactional` mặc định, có thể có rủi ro gì?

**Đáp án:** Checked exception không tự kích hoạt rollback theo quy tắc truyền thống. Dùng `rollbackFor = SQLException.class` hoặc chuyển lỗi phù hợp sang unchecked `DataAccessException`.

**Bài 5 — Duplicate enrollment.** Đăng ký lần đầu thành công còn một ghế. Lần thứ hai cùng `studentId` cố đăng ký, ghế giảm tạm thời rồi unique constraint thất bại. Sau rollback còn mấy ghế?

**Đáp án:** Vẫn còn một ghế, vì lần giảm thứ hai và insert thất bại nằm trong cùng transaction và được rollback.

**Bài 6 — Self-invocation.** Một Service gọi method `@Transactional` của chính nó qua `this`. Proxy mode có chắc advice transaction riêng cho method bên trong không?

**Đáp án:** Không. Nên đặt transaction boundary ở entry point đi qua Spring proxy hoặc tách thành bean khác.

**Bài 7 — `REQUIRES_NEW`.** Nếu outbox insert chạy transaction riêng, nó có chắc rollback cùng enrollment không?

**Đáp án:** Không. Transaction riêng có thể commit độc lập hoặc không thấy enrollment chưa commit; không phù hợp với yêu cầu outbox và đăng ký nguyên tử.

**Bài 8 — Test transaction.** Vì sao test class có `@Transactional` rồi tự rollback cuối mỗi test có thể che giấu commit thực của Service?

**Đáp án:** Service `REQUIRED` có thể chỉ tham gia transaction của test. Muốn kiểm tra Service commit/rollback, hãy gọi Service ngoài test transaction và cleanup fixture riêng.

**Bài 9 — Một ghế, hai học viên.** Nếu hai transaction cùng đăng ký khóa còn một ghế, tại sao một câu `UPDATE ... WHERE available_seats > 0` tốt hơn mô hình đọc rồi ghi?

**Đáp án:** Điều kiện được kiểm tra cùng thao tác cập nhật trên DB, giúp chống mất cập nhật và bán vượt chỗ trong điều kiện transaction/isolation phù hợp. Cần kiểm thử DB thật.

**Bài 10 — Sự kiện bị gửi lặp.** Outbox đã commit nhưng worker gửi event rồi lỗi trước khi đánh dấu hoàn tất. Lần sau worker có thể gửi lại không?

**Đáp án:** Có. Worker/consumer cần idempotency hoặc deduplication theo event ID; một JDBC transaction không đảm bảo exactly-once trên broker.

**Bài 11 — Commit không rõ trạng thái.** Client nhận lỗi mạng đúng lúc Spring commit. Có thể kết luận DB chắc chắn rollback và gọi lại `register` vô điều kiện?

**Đáp án:** Không. Server có thể đã commit nhưng phản hồi bị mất. Phải thiết kế request ID và đối soát trạng thái.

**Bài 12 — Nâng cấp lab.** Hãy đổi `RegistrationOutboxDao` sang `JdbcTemplate.update(...)`. Điều gì phải giữ nguyên?

**Gợi ý:** SQL tham số hóa, kiểm tra update count, cùng `DataSource` và transaction manager với hai DAO kia, không tự commit, lỗi phải đi ra khỏi `@Transactional` và integration test vẫn chứng minh rollback/commit xuyên cả ba bước.

## Tổng kết

**Đưa DAO vào ứng dụng Spring với ranh giới giao dịch đúng** không chỉ là đặt `@Transactional` lên một phương thức. Phải xác định **Service là transaction owner**, bảo đảm mọi DAO dùng **cùng DataSource/connection do Spring quản lý**, không tự commit hoặc đóng kết nối của transaction, và xử lý ngoại lệ theo rollback rules. Bài lab đăng ký khóa học sử dụng `CourseSeatDao` với atomic conditional `UPDATE`, `EnrollmentDao` với generated keys và unique constraint, `RegistrationOutboxDao` với JDBC thuần qua `DataSourceUtils`, được điều phối bằng một `RegistrationService.register` có `@Transactional(rollbackFor = SQLException.class)`. Các integration test không có transaction test bao ngoài giúp kiểm tra commit và rollback thật. Khi triển khai, còn phải chú ý proxy/self-invocation, propagation, thread context, contention, commit không rõ trạng thái và idempotency/outbox cho tác động ngoài database. Đây là nền tảng để kết hợp **JDBC chuẩn và Spring** mà vẫn giữ đúng tính nhất quán dữ liệu trong những use case nhiều DAO.
