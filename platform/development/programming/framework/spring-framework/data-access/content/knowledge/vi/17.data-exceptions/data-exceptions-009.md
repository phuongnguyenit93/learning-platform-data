# Không đồng nhất mọi DataAccessException với một lỗi nghiệp vụ

## 1. Vấn đề: lỗi truy cập dữ liệu không tự động là lỗi nghiệp vụ

Trong Spring Framework, `org.springframework.dao.DataAccessException` là gốc của hệ thống exception dùng để mô tả **thất bại khi truy cập dữ liệu**. `JdbcTemplate`, các công cụ Spring JDBC và một số tích hợp JPA/Hibernate có thể chuyển lỗi của công nghệ lưu trữ thành những exception trong hệ phân cấp này.

Tuy nhiên, **một lỗi ở tầng dữ liệu không mặc nhiên có cùng ý nghĩa với một lỗi nghiệp vụ**. Ví dụ:

- Người dùng đăng ký một email đã tồn tại: nếu thao tác đang tạo tài khoản và vi phạm đúng ràng buộc unique của email, ứng dụng có thể trả một lỗi nghiệp vụ như `EMAIL_ALREADY_USED`.
- SQL gọi đến cột không tồn tại: đó thường là lỗi code hoặc schema/migration, không phải người dùng nhập sai.
- Database mất kết nối: đó là sự cố hạ tầng, không phải quy tắc nghiệp vụ.
- Câu truy vấn một hàng không trả bản ghi: đôi khi hợp lệ và phải trả `Optional.empty()`; trong luồng khác, đó là một tài nguyên không tồn tại hoặc một bất biến bị phá vỡ.
- Deadlock hoặc timeout: có thể là vấn đề tạm thời cần thử lại có kiểm soát, nhưng chưa đủ chứng minh rằng yêu cầu nghiệp vụ đã thất bại vĩnh viễn.

**Sai lầm cần tránh** là bắt mọi `DataAccessException` rồi luôn trả cùng một thông báo “Dữ liệu không hợp lệ”, “Đã tồn tại” hoặc HTTP 400:

```java
// Phản ví dụ: che giấu mọi nguyên nhân kỹ thuật dưới một nhãn nghiệp vụ.
try {
    accountRepository.insert(email);
} catch (DataAccessException ex) {
    throw new BusinessException("Thông tin không hợp lệ");
}
```

Đây chỉ là **đoạn phản ví dụ**, không phải chương trình độc lập; `BusinessException` là kiểu giả định. Nếu DB không kết nối được hoặc code viết sai SQL, đoạn này sẽ đánh lừa người dùng, làm sai thống kê lỗi và gây khó khăn khi điều tra.

Một thiết kế đúng cần **xét loại exception + ngữ cảnh thao tác + ràng buộc dữ liệu cụ thể + khả năng phục hồi** trước khi quyết định có chuyển sang lỗi nghiệp vụ hay không.

## 2. Tách ba lớp ý nghĩa: persistence, domain và API

Xét một ứng dụng đăng ký tài khoản:

```text
HTTP request / message
        │
        ▼
Application service
  ├── Kiểm tra quy tắc nghiệp vụ
  ├── Quyết định thao tác và transaction
  └── Chuyển lỗi DB có ý nghĩa xác định sang lỗi domain
        │
        ▼
Repository / JdbcTemplate
        │  SQL + prepared parameters
        ▼
Database / JDBC driver
        │  SQLException (SQLState, vendor error code, cause)
        ▼
Spring SQLExceptionTranslator
        │  DataAccessException và các subclass
        ▼
Application service xử lý có chọn lọc
        │
        ▼
API layer chuyển kết quả/domain error thành response phù hợp
```

Vai trò cụ thể:

1. **Persistence exception** (ví dụ `DuplicateKeyException`, `BadSqlGrammarException`): mô tả sự cố của truy cập dữ liệu, có thông tin kỹ thuật giúp khắc phục.
2. **Domain/application exception** (ví dụ `EmailAlreadyUsedException`, `OrderStateConflictException`): thể hiện **quy tắc và hợp đồng của một use case cụ thể**, có ý nghĩa ngay cả nếu sau này chuyển từ JDBC sang công nghệ khác.
3. **API error** (ví dụ mã lỗi `EMAIL_ALREADY_USED` với HTTP 409): là cách trình bày lỗi cho caller theo hợp đồng giao tiếp. Mã HTTP không phải là property vốn có của `DataAccessException`.

Không nên tạo bảng ánh xạ toàn cục kiểu “mọi `DataIntegrityViolationException` đều là HTTP 409” hoặc “mọi `DataAccessException` đều là HTTP 400”. Cùng một exception có thể mang ý nghĩa khác nhau tùy nơi phát sinh.

### Ví dụ một lỗi DB, ba cách diễn giải

Một vi phạm unique constraint có thể là:

- **Email trùng khi đăng ký:** business conflict `EMAIL_ALREADY_USED`.
- **Mã giao dịch nội bộ được sinh trùng vì bug:** lỗi hệ thống phải điều tra, không đổ lỗi cho người dùng.
- **Idempotency key lặp lại:** có thể là yêu cầu retry hợp lệ; cần đọc lại kết quả cũ và xác nhận payload theo hợp đồng idempotency, thay vì trả “email đã tồn tại”.

Chỉ nhìn tên `DuplicateKeyException` là **chưa đủ** để quyết định câu trả lời của API.

## 3. Hệ phân cấp exception của Spring và ý nghĩa của nó

`DataAccessException` là **unchecked exception** (kế thừa `NestedRuntimeException`), vì vậy tầng repository không bắt buộc phải khai báo `throws`. Nó được thiết kế để làm cho code ít phụ thuộc công nghệ dữ liệu.

Các nhánh đáng chú ý:

| Nhóm/kiểu | Thông tin kỹ thuật | Ngụ ý xử lý |
| --- | --- | --- |
| `NonTransientDataAccessException` | Lặp lại cùng thao tác, cùng điều kiện thường vẫn lỗi cho đến khi nguyên nhân được sửa | Không retry mù quáng |
| `TransientDataAccessException` | Thao tác **có thể** thành công nếu thử lại mà không cần sửa yêu cầu | Chỉ retry sau khi xét an toàn và transaction |
| `RecoverableDataAccessException` | Có thể hồi phục sau thao tác phục hồi phù hợp, như lấy connection mới | Phục hồi và thử lại **toàn transaction**, không coi là business error |
| `UncategorizedDataAccessException` | Không phân loại được chính xác lỗi bên dưới | Giữ nguyên nguyên nhân; điều tra, không tự đoán ý nghĩa nghiệp vụ |
| `DataIntegrityViolationException` | Vi phạm ràng buộc dữ liệu hoặc lỗi toàn vẹn được translator nhận diện | Xác định **ràng buộc nào**, **use case nào** trước khi chuyển sang domain |
| `DuplicateKeyException` | Vi phạm primary/unique key; là subclass của `DataIntegrityViolationException` | Có thể trở thành domain conflict nếu đúng unique key nghiệp vụ |
| `EmptyResultDataAccessException` | Code yêu cầu ít nhất một kết quả nhưng truy vấn không trả kết quả | Có thể là absence hợp lệ, 404 hoặc lỗi bất biến tùy API |
| `IncorrectResultSizeDataAccessException` | Số dòng trả về không như code chờ đợi | Nhiều dòng khi đòi một dòng thường là lỗi thiết kế/dữ liệu |
| `BadSqlGrammarException` | SQL không hợp lệ (cũng có thể do cột/bảng không tồn tại) | Thường là bug/migration, cần sửa hệ thống |
| `InvalidDataAccessApiUsageException` | Dùng API dữ liệu sai hợp đồng | Thường là bug của ứng dụng |
| `PessimisticLockingFailureException` | Thất bại liên quan pessimistic locking | Xem xét retry/backoff hoặc conflict theo use case |
| `OptimisticLockingFailureException` | Xung đột optimistic version khi framework nhận diện | Có thể là conflict nghiệp vụ nếu API có version/ETag |
| `QueryTimeoutException` | Truy vấn vượt thời gian cho phép | Sự cố thực thi; không tự diễn giải là “không tìm thấy” |
| `DataAccessResourceFailureException` | Resource dữ liệu thất bại, ví dụ không kết nối được DB | Sự cố hạ tầng, xử lý theo khả dụng của hệ thống |

**Chú ý về tên lớp:** `BadSqlGrammarException` ở package `org.springframework.jdbc`; phần lớn kiểu khác trong bảng ở `org.springframework.dao`. Những class như `DeadlockLoserDataAccessException` đã bị deprecated ở các bản Spring 6.x; nên ưu tiên nhánh `PessimisticLockingFailureException`/`CannotAcquireLockException` khi cần xử lý cơ chế lock.

Tên exception là một **phân loại kỹ thuật có ích**, nhưng không phải bằng chứng tuyệt đối rằng một nghiệp vụ đã sai. Không phải mọi driver, database hoặc translator đều cung cấp một subclass chi tiết như nhau.

### Ví dụ phân nhánh đúng hơn

```java
try {
    repository.save(request);
} catch (DuplicateKeyException ex) {
    // Chỉ chuyển thành domain error nếu biết chắc ràng buộc unique
    // mà thao tác này có thể vi phạm mang đúng ý nghĩa nghiệp vụ.
    throw new EmailAlreadyUsedException(ex);
}
// Không catch-all DataAccessException để đổi mọi lỗi thành EmailAlreadyUsed.
```

Đây là **đoạn minh họa**, phụ thuộc một repository/domain exception trong ứng dụng thật. Ở bảng có nhiều unique constraints, phải xác định chính xác constraint có ý nghĩa, hoặc dùng thao tác truy cập dành riêng để giảm khả năng diễn giải nhầm.

## 4. Cách Spring dịch SQLException, và vì sao không nên dựa vào tên exception một cách tuyệt đối

Khi JDBC driver báo `SQLException`, nó thường chứa:

- `SQLState`: mã chuẩn hoặc mã nhà cung cấp, ví dụ `23505` thường biểu diễn lỗi unique trong H2/PostgreSQL.
- `getErrorCode()`: mã số lỗi vendor.
- `getMessage()` và `getNextException()`: mô tả, thông tin nối tiếp từ driver.
- Loại `SQLException`: ví dụ `SQLIntegrityConstraintViolationException` hoặc `SQLTransientException`.

`SQLExceptionTranslator` của Spring đưa những thông tin đó vào cây `DataAccessException`. Từ Spring Framework 6.x, translator mặc định cho `JdbcTemplate` là `SQLExceptionSubclassTranslator`, có fallback xem SQLState. Có thể sử dụng `SQLErrorCodeSQLExceptionTranslator` để áp dụng mã lỗi đặc thù vendor hoặc mapping tùy chỉnh khi cần. Điều này giải thích vì sao **cùng một vi phạm constraint có thể được phân loại ở mức chi tiết khác nhau** giữa driver/cấu hình.

Không viết logic nghiệp vụ chỉ dựa trên chuỗi tiếng Anh trong `SQLException.getMessage()`. Chuỗi có thể thay đổi theo phiên bản, localization, driver và DB. Nếu cần phân biệt nhiều unique constraints ở cùng thao tác, hãy thiết kế named constraints, lập mapping có kiểm thử trên đúng DB và giữ xử lý fallback an toàn.

Các phương thức từ `NestedRuntimeException` như `getRootCause()` và `getMostSpecificCause()` giúp truy vết nguyên nhân. Ví dụ **đoạn mã tiện ích Java minh họa**:

```java
import java.sql.SQLException;

static void diagnose(DataAccessException failure) {
    Throwable mostSpecific = failure.getMostSpecificCause();
    if (mostSpecific instanceof SQLException sql) {
        System.out.println("SQLState=" + sql.getSQLState());
        System.out.println("VendorCode=" + sql.getErrorCode());
    }
}
```

Đoạn này **không độc lập** vì cần import `org.springframework.dao.DataAccessException` và đặt phương thức trong class. Hơn nữa, `getMostSpecificCause()` không được bảo đảm luôn là `SQLException`; nó có thể là cause khác. Trong ứng dụng thực tế, ghi log các thông tin kỹ thuật có kiểm soát, không xuất câu SQL và dữ liệu nhạy cảm ra API response.

## 5. Khi nào một DataAccessException thật sự dẫn tới lỗi nghiệp vụ?

Có thể chuyển exception kỹ thuật sang lỗi domain khi đáp ứng được cả ba điều kiện:

1. **Use case có quy tắc đã định nghĩa**: ví dụ mỗi email chỉ thuộc tối đa một tài khoản.
2. **Có bằng chứng rằng exception tương ứng đúng quy tắc đó**: ví dụ `INSERT` vào bảng chỉ có một unique constraint dành cho email, hoặc có cơ chế xác định đúng constraint.
3. **Domain/API công bố hành vi tương ứng**: ví dụ thông báo “Email đã được sử dụng”, cho phép khách đổi email và thử lại.

Cũng cần nhìn vào thao tác:

| Tình huống | Xử lý phù hợp | Vì sao |
| --- | --- | --- |
| Đăng ký email đã tồn tại, đúng unique email | Chuyển thành `EmailAlreadyUsedException` | Quy tắc nghiệp vụ xác định |
| Lấy bản ghi tùy chọn không tồn tại | Trả `Optional.empty()` | “Không có kết quả” là kết quả hợp lệ |
| Lấy tài nguyên bắt buộc theo ID không tồn tại | Có thể thành `AccountNotFoundException` | Use case đòi phải tồn tại |
| Truy vấn đòi duy nhất nhưng trả 2 dòng | Điều tra invariant/schema, không trả `NotFound` | Có dữ liệu nhưng sai số lượng |
| Unique key của một bảng nội bộ bị trùng do bug | Lỗi hệ thống | Không phải xung đột do người dùng |
| Foreign key / CHECK / NOT NULL vi phạm | Xét ràng buộc cụ thể và lời gọi | Có thể là bug mapper, stale data hoặc yêu cầu sai |
| Hết thời gian query | Thông báo lỗi kỹ thuật phù hợp, quan sát và khắc phục | Không đủ bằng chứng dữ liệu sai |
| DB không kết nối được | Xử lý outage/availability, không trả “dữ liệu sai” | Hạ tầng, có thể cần circuit breaker |
| SQL sai hoặc không khớp migration | Ứng dụng cần sửa code/schema | Không thể yêu cầu người dùng đổi email để chữa |

**Nguyên tắc:** chỉ xử lý như nghiệp vụ khi có thể giải thích được **quy tắc nào bị vi phạm** và **người gọi có thể làm gì tiếp theo**.

### Vì sao kiểm tra “đã tồn tại chưa” không thay thế unique constraint?

Đoạn nghiệp vụ:

```text
Request A: SELECT email -> chưa tồn tại
Request B: SELECT email -> chưa tồn tại
Request A: INSERT email -> thành công
Request B: INSERT email -> DB báo unique violation
```

Hai request chạy đồng thời nên tiền kiểm tra không đủ chống race condition. Database constraint là nơi chốt tính duy nhất; application xử lý conflict **đúng nghĩa** khi constraint bị vi phạm. Có thể kiểm tra trước để cải thiện thông báo, nhưng không được dựa vào đó để bảo đảm tính đúng đắn.

## 6. Ví dụ hoàn chỉnh: chỉ chuyển lỗi duplicate email, giữ nguyên lỗi SQL kỹ thuật

Ví dụ Spring Boot 3.5.7, Java 17+, Spring JDBC và H2 minh họa ba trường hợp:
- Duplicate email → domain exception `EmailAlreadyUsedException`.
- Không có bản ghi ở API tìm kiếm tùy chọn → `Optional.empty()`.
- Cột SQL không tồn tại → `BadSqlGrammarException` kỹ thuật, **không trở thành** `EmailAlreadyUsedException`.

Dự án:

```text
data-access-exception-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/daoerror/
    │   └── DataAccessExceptionDemoApplication.java
    └── resources/
        ├── schema.sql
        └── application.properties
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>data-access-exception-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

**`src/main/resources/application.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:dao_exception_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.banner-mode=off
logging.level.root=ERROR
```

**`src/main/java/com/example/daoerror/DataAccessExceptionDemoApplication.java`**:

```java
package com.example.daoerror;

import java.util.Optional;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class DataAccessExceptionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataAccessExceptionDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(AccountService service, JdbcTemplate jdbc) {
        return args -> {
            service.register("an@example.test");

            System.out.println("Existing found: " +
                    service.findId("an@example.test").isPresent());
            System.out.println("Missing returned empty: " +
                    service.findId("missing@example.test").isEmpty());

            try {
                service.register("an@example.test");
            } catch (EmailAlreadyUsedException ex) {
                System.out.println("Business exception: " +
                        ex.getClass().getSimpleName());
            }

            try {
                jdbc.queryForObject(
                        "SELECT missing_column FROM accounts",
                        String.class);
            } catch (BadSqlGrammarException ex) {
                System.out.println("Technical SQL exception: " +
                        ex.getClass().getSimpleName());
            }
        };
    }
}

@Repository
class AccountRepository {
    private final JdbcTemplate jdbc;

    AccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void insert(String email) {
        jdbc.update("INSERT INTO accounts (email) VALUES (?)", email);
    }

    Long findId(String email) {
        return jdbc.queryForObject(
                "SELECT id FROM accounts WHERE email = ?",
                Long.class,
                email);
    }
}

@Service
class AccountService {
    private final AccountRepository repository;

    AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    public void register(String email) {
        try {
            repository.insert(email);
        } catch (DuplicateKeyException ex) {
            // Trong schema mẫu, email là unique key mà client cung cấp.
            throw new EmailAlreadyUsedException(ex);
        }
    }

    public Optional<Long> findId(String email) {
        try {
            // Truy vấn id theo unique email nên có tối đa một hàng.
            return Optional.ofNullable(repository.findId(email));
        } catch (EmptyResultDataAccessException ex) {
            // Với API tìm kiếm tùy chọn, không có bản ghi là bình thường.
            return Optional.empty();
        }
    }
}

final class EmailAlreadyUsedException extends RuntimeException {
    EmailAlreadyUsedException(Throwable cause) {
        super("Email is already registered", cause);
    }
}
```

Các class package-private `AccountRepository`, `AccountService` và `EmailAlreadyUsedException` được đặt cùng file với class public có tên khớp file. Spring component scan từ package `com.example.daoerror` nhận `@Repository` và `@Service`. `JdbcTemplate` do `spring-boot-starter-jdbc` cấu hình với `DataSource` H2.

Chạy trong thư mục `data-access-exception-demo`:

```bash
mvn -q spring-boot:run
```

Với **database H2 mới, bảng trống**, bốn dòng do chương trình in là:

```text
Existing found: true
Missing returned empty: true
Business exception: EmailAlreadyUsedException
Technical SQL exception: BadSqlGrammarException
```

Những thông báo bổ sung từ Maven/JVM phụ thuộc môi trường. Kết quả giả định Spring JDBC 6.2.x trong Spring Boot 3.5.7 và H2 JDBC driver nhận diện SQLState unique `23505`. Với DB/driver khác, **mức độ chi tiết của exception cần được kiểm tra bằng integration test**.

Giải thích luồng:

1. Đăng ký `an@example.test` lần đầu, lệnh `INSERT` thành công.
2. Đọc đúng email bằng `queryForObject(...)` trả một ID; tìm email không tồn tại làm `queryForObject` ném `EmptyResultDataAccessException` và service chọn `Optional.empty()`.
3. Đăng ký lại cùng email: H2 vi phạm unique, Spring dịch thành `DuplicateKeyException`; **chỉ** service `register` đổi lỗi sang `EmailAlreadyUsedException`.
4. Truy vấn `missing_column` là sai schema. Spring ném `BadSqlGrammarException`; mã không bắt nó ở service như một lỗi business. Demo chỉ catch ở runner để minh họa và in đúng loại lỗi; ứng dụng thực tế phải ghi log/điều tra.
5. `EmailAlreadyUsedException` vẫn giữ `cause` gốc để hỗ trợ chẩn đoán, nhưng thông điệp domain không chứa SQL, bảng hay thông tin nội bộ.

**Giới hạn của ví dụ:** bảng chỉ có ràng buộc unique tự nhiên trên `email` bên cạnh primary key do database tự sinh, và câu lệnh chỉ truyền `email`. Với bảng nhiều unique constraints, việc bắt mọi `DuplicateKeyException` trong một thao tác phức tạp có thể diễn giải nhầm; phải xác định constraint/nguồn dữ liệu đúng trước khi thông báo `EMAIL_ALREADY_USED`.

## 7. EmptyResult: một kết quả bình thường trong API này, một lỗi ở API khác

`EmptyResultDataAccessException` thường phát sinh khi phương thức như `JdbcTemplate.queryForObject(...)` mong một dòng nhưng truy vấn trả **0 dòng**. Không nên đồng nhất nó với `NotFound` cho mọi trường hợp.

Ví dụ:

- `Optional<User> findByEmail(email)`: người dùng không có email đó có thể là kết quả hợp lệ; return `Optional.empty()`.
- `User getById(id)` trong use case bắt buộc có user: có thể chuyển sang `UserNotFoundException` (nếu điều kiện truy cập và hợp đồng API cho phép).
- `loadSystemConfiguration("required-key")`: thiếu cấu hình bắt buộc là lỗi hệ thống, không phải 404 của client.
- `findExactlyOneActiveSubscription(userId)`: nếu logic đòi luôn có đúng một hàng, không có hàng có thể vi phạm invariant nghiệp vụ, cần xử lý riêng.

Đặc biệt **đừng che** trường hợp `IncorrectResultSizeDataAccessException` do **nhiều dòng** bằng một `catch` rộng rồi trả “không tìm thấy”. Nếu truy vấn được thiết kế một bản ghi mà trả nhiều bản ghi, đó có thể là lỗi unique constraint, join hoặc dữ liệu.

Khi cần API trả nhiều hoặc không bản ghi mà không ném vì 0 dòng, có thể dùng `query(...)` nhận list:

```java
List<Long> ids = jdbcTemplate.query(
        "SELECT id FROM accounts WHERE email = ?",
        (rs, rowNum) -> rs.getLong("id"),
        email);
```

Đoạn minh họa trong một phương thức đã có `JdbcTemplate jdbcTemplate` và `String email`. Ở API này, list rỗng là kết quả thông thường. Nhưng khi hợp đồng yêu cầu một bản ghi duy nhất, hãy duy trì kiểm tra bất biến thay vì luôn lấy phần tử đầu.

## 8. DataIntegrityViolationException không phải “luôn trùng dữ liệu”

`DuplicateKeyException` là subclass của `DataIntegrityViolationException`, nhưng nhóm tổng quát còn bao trùm các lỗi như:

- Foreign key: tham chiếu bản ghi cha không tồn tại, hoặc cố xóa bản ghi đang được tham chiếu.
- `NOT NULL`: code bind `NULL` cho cột bắt buộc.
- `CHECK`: dữ liệu vi phạm constraint của schema.
- Một số tình huống mapping/type hoặc constraint khác do translator phân loại vào nhóm integrity.

Không nên viết:

```java
try {
    jdbcTemplate.update(sql, params);
} catch (DataIntegrityViolationException ex) {
    throw new EmailAlreadyUsedException(ex); // Sai: có thể là FK/NOT NULL/CHECK.
}
```

Đây là phản ví dụ. Một constraint DB có thể phản ánh quy tắc nghiệp vụ, nhưng mapping đúng cần **tên ràng buộc/kiểu vi phạm/ngữ cảnh request**. Khi chưa có đủ bằng chứng, để lỗi kỹ thuật đi qua tầng ứng dụng hoặc chuyển sang lỗi hạ tầng có giữ cause; không gán bừa thành một mã lỗi nghiệp vụ.

**Ví dụ phân biệt FK:**
- Client gửi `customerId` đã bị xóa, và hợp đồng yêu cầu khách hàng phải tồn tại: có thể trả `CUSTOMER_NOT_FOUND` hoặc conflict, tùy semantics.
- Code repository lấy sai ID vì bug: lỗi hệ thống; dùng thông báo `CUSTOMER_NOT_FOUND` cho người dùng sẽ che mất bug.

Nên có test cho từng ràng buộc cần dịch sang domain, không chỉ test rằng “có ném DataIntegrityViolationException”.

## 9. Trạng thái có thể retry không có nghĩa retry luôn an toàn

`TransientDataAccessException` gợi ý rằng lỗi có thể biến mất nếu gọi lại, nhưng ứng dụng phải trả lời bốn câu hỏi:

1. **Thao tác có idempotent không?** Đọc dữ liệu thường dễ thử lại hơn ghi dữ liệu; retry một `INSERT` không có idempotency key có thể tạo bản ghi trùng.
2. **Lần trước đã commit chưa?** Timeout hoặc mất kết nối có thể khiến caller **không biết chắc** kết quả ghi đã được commit. Retry ngay có thể thực hiện hai lần.
3. **Transaction còn dùng được không?** Sau một số lỗi SQL, transaction hoặc connection hiện tại không còn dùng được. Cần rollback và thử lại trong transaction/connection mới.
4. **Giới hạn retry là gì?** Cần số lần tối đa, backoff có jitter, deadline, log/metric, tránh khuếch đại tải khi DB đang gặp sự cố.

Ví dụ chính sách: với query đọc đơn giản gặp `CannotAcquireLockException` hoặc timeout, thử lại có giới hạn **nếu** logic và mức cô lập cho phép. Với write có tác dụng bên ngoài (gửi email, trừ tiền, phát event), cần thiết kế idempotency hoặc outbox trước khi tự động retry. Không áp dụng một interceptor retry vô hạn cho toàn bộ `DataAccessException`.

`RecoverableDataAccessException` nói đến khả năng **phục hồi bằng bước bổ sung**, tối thiểu lấy connection mới rồi thử lại transaction; nó cũng không phải domain error. `NonTransientDataAccessException` gợi ý retry cùng yêu cầu thường vô ích nếu chưa sửa nguyên nhân.

### Liên hệ @Transactional

Theo cấu hình mặc định của Spring Framework, exception **unchecked** thoát khỏi phương thức `@Transactional` sẽ khiến transaction được đánh dấu rollback. Cả `DataAccessException` và domain exception tự định nghĩa kế thừa `RuntimeException` đều thuộc nhóm này theo mặc định.

Nếu bắt một `DataAccessException` rồi **nuốt lỗi** để trả thành công, bạn có thể làm sai trạng thái transaction hoặc để logic tiếp tục với dữ liệu không nhất quán. Với JPA/Hibernate, resource có thể đã đánh dấu transaction rollback-only; ngay cả khi phương thức cố return bình thường, lúc commit vẫn có thể xảy ra `UnexpectedRollbackException`.

Nếu muốn retry thao tác trong transaction, thông thường cần đặt vòng retry **ở ngoài** ranh giới transaction để mỗi lượt có transaction mới (hoặc dùng `TransactionTemplate` tạo lại transaction). Tự gọi một phương thức `@Transactional` cùng instance có thể không đi qua Spring proxy; đừng mặc định annotation được áp dụng trong self-invocation.

## 10. Mapping ra HTTP/API: ngữ cảnh quyết định mã phản hồi

Một cách lựa chọn theo **hợp đồng use case**:

| Trường hợp | Kết quả API thường hợp lý | Lý do/giới hạn |
| --- | --- | --- |
| Email trùng khi đăng ký, constraint xác nhận đúng | `409 Conflict` + mã `EMAIL_ALREADY_USED` | Client có thể chọn email khác |
| Yêu cầu không hợp lệ trước khi truy cập DB | `400 Bad Request` hoặc `422 Unprocessable Content` tùy contract | Đây là input validation, không phải tự suy ra từ `DataAccessException` |
| Bản ghi được yêu cầu bắt buộc nhưng không tồn tại | `404 Not Found` nếu caller được phép biết | Áp dụng từ semantics của tài nguyên |
| Xung đột version/ETag trong cập nhật | `409 Conflict` hoặc `412 Precondition Failed` tùy hợp đồng HTTP | Điều kiện cạnh tranh đã có định nghĩa |
| DB outage và có chính sách tạm thời | `503 Service Unavailable` hoặc lỗi 5xx thích hợp | Không nên công bố chi tiết kết nối nội bộ |
| SQL viết sai, migration thiếu | `500 Internal Server Error` | Lỗi kỹ thuật cần sửa |
| Query timeout | 5xx thích hợp theo tầng triển khai, không mặc định 404/400 | Có thể cần timeout/retry riêng |
| Exception không phân loại | Lỗi tổng quát 5xx và correlation ID | Không đủ cơ sở gán quy tắc nghiệp vụ |

HTTP status và mã lỗi ứng dụng phải thống nhất với contract API đang triển khai. Bảng trên là **gợi ý**, không phải mapping bắt buộc của Spring. Đặc biệt, HTTP 409 dành cho xung đột có ý nghĩa trong **trạng thái tài nguyên được yêu cầu**, không phải mọi lỗi DB.

### ControllerAdvice chỉ xử lý domain exception có chủ ý

Đoạn dưới đây là **minh họa bổ sung** cho ứng dụng có `spring-boot-starter-web`, không thuộc project console ở mục 6:

```java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(EmailAlreadyUsedException.class)
    ResponseEntity<Map<String, String>> emailConflict(
            EmailAlreadyUsedException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of(
                        "code", "EMAIL_ALREADY_USED",
                        "message", "Email đã được sử dụng"));
    }
}
```

Ví dụ trên giả định `EmailAlreadyUsedException` là type trong project và được import phù hợp. Vì project demo ở mục 6 không có dependency Spring Web, **không chép file này vào project đó nếu chưa bổ sung `spring-boot-starter-web`** và điều chỉnh package/import; khi dùng thật, handler nên nằm trong package đúng quy tắc Java và có test MVC.

Không nên thêm:

```java
@ExceptionHandler(DataAccessException.class)
@ResponseStatus(HttpStatus.BAD_REQUEST)
void everythingIsBadRequest(DataAccessException ex) { /* ... */ }
```

Đây là phản ví dụ: nó sẽ che lỗi SQL/mất kết nối thành HTTP 400. Nếu ứng dụng có handler dự phòng cho lỗi kỹ thuật, hãy trả response chung không lộ thông tin nội bộ, đồng thời log exception và correlation ID. Tránh “bắt rồi quên”.

## 11. Logging và quan sát: giữ nguyên thông tin kỹ thuật ở phía server

Khi ứng dụng chuyển một exception thành lỗi nghiệp vụ, đừng mất `cause`. Ví dụ:

```java
final class EmailAlreadyUsedException extends RuntimeException {
    EmailAlreadyUsedException(Throwable cause) {
        super("Email is already registered", cause);
    }
}
```

Bên ngoài, API chỉ trả mã lỗi/ thông báo an toàn; phía server có thể dùng cause để điều tra khi cần. Tuy nhiên, cũng tránh log trùng toàn bộ stack trace ở repository, service rồi controller cho cùng một request nếu monitoring đã ghi ở ranh giới cuối.

Các thông tin hữu ích cho log/metric/trace nội bộ:

- Tên thao tác: `AccountRepository.insert`, tên bảng/constraint nếu có thể ghi an toàn.
- Tên subclass: `DuplicateKeyException`, `BadSqlGrammarException`...
- SQLState và vendor error code khi có, để phân biệt nguyên nhân từ JDBC.
- Request/correlation ID và tên use case.
- Thời gian chờ kết nối, thời gian query, số lần retry, pool metrics khi điều tra sự cố.

Không đưa mật khẩu, connection URL có secret, toàn bộ SQL chứa giá trị người dùng, thông tin cá nhân hoặc raw database exception message vào client response hay log ở mức không phù hợp.

Các chỉ số nghiệp vụ và kỹ thuật cũng nên tách: `registration.email_conflict` phản ánh use case; `db.query_timeout`, `db.connection_failure`, `db.sql_error` phản ánh độ tin cậy hệ thống. Gộp mọi lỗi vào một “validation_failed” khiến số liệu sản phẩm và cảnh báo vận hành đều sai.

## 12. Kiểm thử để không đánh đồng exception

Một tập test hữu ích cho use case đăng ký:

1. **Insert hợp lệ:** lưu email mới, assert bản ghi tồn tại.
2. **Duplicate đúng constraint:** insert cùng email hai lần; assert service phát `EmailAlreadyUsedException` và giữ `DuplicateKeyException` làm cause (trên driver H2 được dùng trong ví dụ).
3. **Không có email khi tìm kiếm tùy chọn:** `findId(...)` trả `Optional.empty()`, không ném domain exception.
4. **SQL sai:** chủ động gọi SQL không tồn tại cột trong một test riêng; assert lỗi dữ liệu vẫn là `BadSqlGrammarException`, không đổi thành `EmailAlreadyUsedException`.
5. **Constraint khác:** trong bảng thực có FK/CHECK/NOT NULL, chứng minh lỗi đó **không bị chuyển nhầm** thành duplicate email.
6. **Nhiều dòng cho truy vấn một dòng:** xác nhận hệ thống không trả “not found” khi thực chất dữ liệu/truy vấn sai bất biến.
7. **Outage/timeout:** qua test tích hợp/chaos phù hợp, kiểm tra lỗi hạ tầng được báo an toàn, retry có giới hạn và không phát lại side effect.
8. **Transaction rollback:** với một use case có nhiều lệnh, xác nhận lỗi unchecked làm rollback các thay đổi chưa commit và retry không dùng lại transaction lỗi.
9. **API contract:** kiểm thử response có mã business đúng cho xung đột đã xác nhận, còn lỗi SQL/DB không lộ message nội bộ hoặc bị đổi thành HTTP 400.

Mỗi khi đổi DB, driver hoặc phiên bản Spring, nên chạy lại ít nhất các test exception translation quan trọng. Không mặc định mapping SQLState và exception subclass luôn giống giữa H2, PostgreSQL, MySQL hay SQL Server.

### Test anti-pattern cần nhận diện

```java
// Sai: chỉ kiểm thử rằng "mọi DataAccessException được đổi thành 400".
assertThatThrownBy(() -> service.register("x@example.test"))
        .isInstanceOf(BusinessException.class);
```

Đây là đoạn pseudo-test minh họa (cần framework test, class ứng dụng tương ứng). Nó không nói được exception gốc là duplicate, SQL hỏng hay DB mất kết nối. Test có giá trị phải **điều khiển nguyên nhân** và khẳng định **đúng ánh xạ của từng use case**.

## 13. Checklist ra quyết định khi gặp DataAccessException

Trước khi viết `catch`:

1. **Đây là truy vấn/thao tác nào?** Đọc tùy chọn, đọc bắt buộc, cập nhật version, hay tạo tài nguyên duy nhất?
2. **Exception cụ thể là gì?** `DuplicateKeyException`, `EmptyResultDataAccessException`, `BadSqlGrammarException`, hay loại khác?
3. **Biết chính xác constraint hay invariant nào đã bị vi phạm không?** Nếu không, không tự gán mã lỗi nghiệp vụ.
4. **Người gọi có thể sửa request không?** Chỉ khi có quy tắc domain rõ ràng, hướng dẫn họ đổi input.
5. **Có thể thử lại an toàn không?** Cần xét idempotency, transaction và trạng thái commit, không chỉ tên `TransientDataAccessException`.
6. **Phải rollback, quan sát hoặc cảnh báo gì?** Giữ cause, log/metric đúng nhóm, tránh thông tin nhạy cảm.
7. **Hợp đồng API cần thông báo gì?** Chuyển domain error ở boundary với mã rõ ràng; giữ lỗi hạ tầng ở luồng hạ tầng.

**Quy tắc viết code:** xử lý exception **cụ thể nhất có ý nghĩa**, ngay tại lớp hiểu nghiệp vụ của thao tác. Các lỗi chưa có quy tắc xử lý nên đi tiếp tới boundary xử lý lỗi kỹ thuật, thay vì ép thành một business error chung.

## 14. Tự kiểm tra kiến thức

1. Vì sao `DuplicateKeyException` chưa đủ để kết luận “Email đã tồn tại” trong bảng có nhiều unique constraints?
2. Với phương thức `findOptionalByEmail`, khi nào `EmptyResultDataAccessException` nên biến thành `Optional.empty()`?
3. Nếu service bắt `DataAccessException` và luôn trả HTTP 400, nó che giấu những lỗi hạ tầng nào?
4. Một `QueryTimeoutException` xảy ra sau lệnh ghi: có thể khẳng định database chưa commit không? Vì sao không được retry vô hạn?
5. Tại sao `BadSqlGrammarException` thường là vấn đề vận hành/code chứ không phải lỗi nghiệp vụ của người dùng?
6. Khi dùng `@Transactional`, điều gì xảy ra theo mặc định với unchecked exception thoát ra ngoài method?
7. Tại sao test trên H2 thành công chưa đủ xác nhận translation của driver PostgreSQL/MySQL?
8. Phân biệt mã lỗi nghiệp vụ `EMAIL_ALREADY_USED` với loại exception `DataIntegrityViolationException` về trách nhiệm của từng lớp.

Bạn có thể coi bài đã nắm vững nếu luôn phân biệt được **nguyên nhân truy cập dữ liệu**, **quy tắc nghiệp vụ bị ảnh hưởng** và **cách báo lỗi cho client**.

## 15. Tài liệu chính thức

- [Spring Framework — DAO Support / Consistent Exception Hierarchy](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html)
- [Spring Framework — JDBC Core / SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html)
- [Spring Framework — DataAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessException.html)
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
- [Spring Framework — DuplicateKeyException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DuplicateKeyException.html)
- [Spring Framework — EmptyResultDataAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html)
- [Spring Framework — SQLExceptionSubclassTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html)
- [Spring Framework — Declarative transaction rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
