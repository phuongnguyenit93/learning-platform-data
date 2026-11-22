# rollbackFor và noRollbackFor theo kiểu ngoại lệ

## 1. Hai thuộc tính quyết định rollback theo loại lỗi

Trong Spring Framework, `@Transactional` có thể quản lý một giao dịch bao gồm nhiều thao tác database. Khi phương thức kết thúc bình thường, transaction manager thường cố **commit**; khi một ngoại lệ thoát khỏi lời gọi được Spring quản lý, transaction interceptor cần quyết định **rollback hay commit**. Hai thuộc tính quan trọng là:

- **`rollbackFor`:** liệt kê **kiểu ngoại lệ** (`Class<? extends Throwable>`) khiến Spring yêu cầu rollback.
- **`noRollbackFor`:** liệt kê **kiểu ngoại lệ** mà Spring **không yêu cầu rollback**, kể cả khi đó là một unchecked exception vốn thường gây rollback theo mặc định.

Ví dụ:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    // Nếu IOException thoát khỏi method, yêu cầu rollback.
}

@Transactional(noRollbackFor = BusinessNoticeException.class)
public void processNotice() {
    // Nếu BusinessNoticeException thoát khỏi method,
    // Spring không đánh dấu rollback chỉ vì exception này.
}
~~~

Đây chỉ là **đoạn minh họa về annotation**; method body và `BusinessNoticeException` chưa được định nghĩa nên không phải chương trình chạy độc lập. Ví dụ hoàn chỉnh có thể biên dịch và kiểm thử nằm ở phần sau.

**Phân biệt cốt lõi:** “method ném exception” không đồng nghĩa “database chắc chắn rollback”. Spring đọc **rollback rule** trước khi quyết định. Ngược lại, cấu hình `noRollbackFor` **không bảo đảm** transaction sẽ commit trong mọi tình huống: transaction có thể đã bị đánh dấu rollback-only, database có thể từ chối commit, hoặc có lỗi hạ tầng riêng.

### Bối cảnh nghiệp vụ

Giả sử bạn ghi thay đổi trạng thái đơn hàng trong database rồi phát hiện một điều kiện:

- **Lỗi kỹ thuật/nghiệp vụ nghiêm trọng:** thay đổi không được lưu → rollback.
- **Thông báo nghiệp vụ không làm mất hiệu lực kết quả đã ghi:** đôi khi vẫn muốn commit, dù method phải báo tình huống đặc biệt cho caller.

Điều này phải được quyết định bằng **bất biến nghiệp vụ** chứ không phải vì exception có tên nghe “nặng” hay “nhẹ”. `noRollbackFor` đặc biệt dễ gây lỗi dữ liệu dở dang nếu dùng sai.

## 2. Mặc định: unchecked rollback, checked thường không rollback

Trước khi thiết lập rule riêng, cần phân biệt hai họ exception Java:

~~~text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.lang.RuntimeException       (unchecked)
    │   ├── IllegalArgumentException
    │   └── IllegalStateException
    └── IOException / SQLException / ...  (checked)
~~~

- **Unchecked exception:** các lớp kế thừa `RuntimeException`; ví dụ `IllegalStateException`, `NullPointerException`. `Error` cũng là loại unchecked theo quy tắc Java nhưng không kế thừa `RuntimeException`.
- **Checked exception:** các lớp kế thừa `Exception` nhưng không kế thừa `RuntimeException`, ví dụ `IOException`. Compiler yêu cầu khai báo hoặc bắt loại ngoại lệ này.
- **Quy tắc Spring mặc định thông thường:** rollback với `RuntimeException` và `Error`, **không tự rollback chỉ vì checked exception**.

Ví dụ, một method ghi thành công vào DB rồi ném `IOException`. Nếu transaction mới do Spring mở và không có rule khác, Spring có thể **commit phần ghi** rồi truyền `IOException` ra caller. Điều này thường gây bất ngờ.

| Tình huống | Mặc định của `@Transactional` | Sau khi thêm rule |
| --- | --- | --- |
| `IllegalStateException` thoát ra | Rollback | `noRollbackFor = IllegalStateException.class` yêu cầu không rollback do loại lỗi ấy. |
| `IOException` thoát ra | Không rollback theo mặc định | `rollbackFor = IOException.class` yêu cầu rollback. |
| `Error` thoát ra | Rollback | Chỉ thay đổi khi có rule cấu hình phù hợp, dùng cực kỳ thận trọng. |
| Method trả về bình thường | Commit nếu Spring sở hữu transaction và không có lý do rollback khác | Rule theo exception không có gì để khớp. |

Các kết quả trên giả định **transaction thực sự hoạt động**, lời gọi đi qua Spring proxy và không có trạng thái rollback-only hoặc lỗi từ database trước đó.

**Lưu ý phiên bản:** kể từ Spring Framework 6.2, cấu hình quản lý transaction bằng annotation có thể chủ động thay mặc định toàn cục, ví dụ `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. Bài lab dưới đây **không bật tùy chọn đó**, vì vậy các test quan sát mặc định quen thuộc RuntimeException/Error rollback, checked exception không rollback. Nếu ứng dụng của bạn đã tùy biến global default rules, đừng áp bảng mặc định một cách máy móc; rule cụ thể vẫn cần được đối chiếu với chính sách toàn cục đã chọn.

## 3. rollbackFor và noRollbackFor khớp theo *kiểu*, kể cả lớp con

Hai thuộc tính kiểu class:

~~~java
@Transactional(
    rollbackFor = {IOException.class, BusinessCheckedException.class},
    noRollbackFor = {NonCriticalBusinessException.class}
)
public void performOperation() {
    // ...
}
~~~

Có các nguyên tắc:

1. Một rule `rollbackFor = IOException.class` áp dụng cho `IOException` **và các lớp con**. Tương tự cho `noRollbackFor`.
2. Khi nhiều rule cùng khớp một exception, Spring sử dụng **rule khớp mạnh nhất**. Với rule khai báo bằng class, có thể hiểu thực hành là **loại cụ thể hơn trên chuỗi kế thừa** thường thắng loại cha rộng hơn.
3. Nếu không có custom rule nào khớp, Spring trở về chính sách mặc định (trừ khi ứng dụng đã thay chính sách toàn cục).
4. Không nên viết hai rule đối nghịch cho **cùng đúng một lớp** rồi dựa vào thứ tự xuất hiện để đoán kết quả. Hãy làm chính sách không mơ hồ.

Ví dụ đơn giản về thứ tự ưu tiên:

~~~java
class BusinessRuntimeException extends RuntimeException { }

class CriticalBusinessException extends BusinessRuntimeException { }

@Transactional(
    noRollbackFor = BusinessRuntimeException.class,
    rollbackFor = CriticalBusinessException.class
)
public void operation() {
    // ...
}
~~~

- Ném `BusinessRuntimeException`: khớp `noRollbackFor` → không rollback theo rule đó.
- Ném `CriticalBusinessException`: khớp cả rule của lớp cha và lớp con. `rollbackFor` của **lớp con cụ thể hơn** thắng → rollback.
- Nếu ném một `IllegalArgumentException` không liên quan: không khớp hai custom rules; đây vẫn là RuntimeException nên rollback theo mặc định.

Đây là ví dụ **lược bớt method body**, chưa phải class chạy độc lập. Trong phần lab, chính các class exception và những nhánh hành vi này sẽ được khai báo/kiểm thử đầy đủ.

### Khớp class khác khớp tên chuỗi

Có bốn thuộc tính annotation:

| Dạng có type safety | Dạng chuỗi pattern |
| --- | --- |
| `rollbackFor = IOException.class` | `rollbackForClassName = "java.io.IOException"` |
| `noRollbackFor = BusinessRuntimeException.class` | `noRollbackForClassName = "com.example.BusinessRuntimeException"` |

Dạng **Class** được compiler kiểm tra và khớp theo quan hệ kiểu Java. Dạng **ClassName** là **pattern chứa trong tên lớp đủ định danh**, không phải regular expression hay glob; pattern quá rộng như `"Exception"` có thể khớp ngoài ý muốn. Chẳng hạn tên `CustomException` có nguy cơ khớp cả `CustomExceptionV2` nếu dùng pattern. Khi biết class lúc compile, nên ưu tiên `rollbackFor`/`noRollbackFor` thay vì chuỗi.

## 4. Sơ đồ quyết định khi exception thoát khỏi @Transactional

~~~text
Caller gọi public method QUA Spring proxy
                   |
          transaction bắt đầu/tham gia
                   |
          target method thực thi
                   |
       +-----------+-------------+
       |                         |
       v                         v
  Trả về bình thường       Exception/Error thoát ra
       |                         |
       |                  Xem custom rules
       |                         |
       |              +----------+----------+
       |              |                     |
       |         Rule khớp              Không có rule
       |              |                     |
       |       Chọn mạnh nhất        Mặc định theo loại:
       |              |              RuntimeException/Error -> rollback
       |       rollback / no        checked -> không rollback
       |              |                     |
       +--------------+---------------------+
                      |
            Spring hoàn tất transaction
           (commit hoặc rollback theo điều kiện)
                      |
                Caller nhận kết quả/lỗi
~~~

“Không rollback” trong hình nghĩa là **không yêu cầu rollback chỉ do exception ấy**; interceptor có thể tiến hành commit nếu là transaction mới do mình mở và mọi điều kiện khác đều hợp lệ. Nó **không** có nghĩa nuốt exception: caller vẫn nhận exception sau khi advice xử lý.

**Quan trọng:** Nếu method chỉ **tham gia** transaction `REQUIRED` do caller tạo, thì service method không nắm quyền commit cuối. Một method khác có thể đã đặt rollback-only hoặc transaction ngoài có thể rollback về sau.

## 5. Bài lab hoàn chỉnh: đo trạng thái DB sau từng exception

Ta sẽ tạo dự án **Java 17+**, **Spring Boot 3.5.0**, **Spring JDBC**, **H2 in-memory**, **JUnit 5** bằng Maven. Không cần chạy PostgreSQL riêng. Ví dụ dùng một hàng `tx_counter(id=1, value=100)`; mỗi method tăng `value` thêm 10 **trước khi ném exception**. Sau lời gọi:

- **Rollback** → giá trị phải trở về **100**.
- **Commit dù có exception** → giá trị là **110**.

Điểm hay của thiết kế này: mọi test đều có một thay đổi database thật để phân biệt hai chính sách. Test cũng không được annotate `@Transactional`, vì transaction riêng của Spring Test có thể che khuất việc service thật sự commit hay rollback.

Cấu trúc tệp:

~~~text
rollback-rules-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/rollbackrules/
    │   │   ├── RollbackRulesApplication.java
    │   │   └── RollbackRuleService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/rollbackrules/
            └── RollbackRuleServiceTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rollback-rules-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

`spring-boot-starter-jdbc` đưa `JdbcTemplate` và transaction infrastructure vào ứng dụng; `h2` cấp database thử nghiệm; `spring-boot-starter-test` cấp JUnit 5 và `@SpringBootTest`. Với một `DataSource` JDBC tương thích và `PlatformTransactionManager` do Boot cấu hình tự động, `@Transactional` sẽ áp vào service bean.

### 5.2. application.properties và schema.sql

Tệp `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:rollback_rules_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_counter (
    id BIGINT PRIMARY KEY,
    value BIGINT NOT NULL
);
~~~

H2 ở đây nằm trong bộ nhớ; `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại trong suốt vòng đời JVM dù connection được đóng. `schema.sql` được Spring Boot chạy để tạo bảng lúc context khởi động. Các test sẽ reset dữ liệu về `100` trước mỗi tình huống nên không phụ thuộc thứ tự test.

### 5.3. RollbackRulesApplication.java

Tệp `src/main/java/com/example/rollbackrules/RollbackRulesApplication.java`:

~~~java
package com.example.rollbackrules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RollbackRulesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackRulesApplication.class, args);
    }
}
~~~

Đây là class ứng dụng nằm cùng package với service/test; `@SpringBootTest` có thể tìm bootstrap configuration thông qua class này. Bài lab không cần `@EnableTransactionManagement` thủ công khi Spring Boot auto-configuration đã cung cấp transaction management cho JDBC. Không có cấu hình `rollbackOn = ALL_EXCEPTIONS` trong ví dụ.

### 5.4. RollbackRuleService.java

Tệp `src/main/java/com/example/rollbackrules/RollbackRuleService.java`:

~~~java
package com.example.rollbackrules;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RollbackRuleService {
    private final JdbcTemplate jdbc;

    public RollbackRuleService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Checked exception: không phải RuntimeException.
    public static class CheckedBusinessException extends Exception {
        public CheckedBusinessException(String message) {
            super(message);
        }
    }

    public static final class IgnorableCheckedException
            extends CheckedBusinessException {
        public IgnorableCheckedException(String message) {
            super(message);
        }
    }

    // Unchecked exception: kế thừa RuntimeException.
    public static class BusinessRuntimeException extends RuntimeException {
        public BusinessRuntimeException(String message) {
            super(message);
        }
    }

    public static final class CriticalRuntimeException
            extends BusinessRuntimeException {
        public CriticalRuntimeException(String message) {
            super(message);
        }
    }

    // 1. Mặc định: RuntimeException -> rollback.
    @Transactional
    public void defaultRuntime() {
        increase();
        throw new BusinessRuntimeException("default runtime");
    }

    // 2. Mặc định: checked exception -> không rollback.
    @Transactional
    public void defaultChecked() throws CheckedBusinessException {
        increase();
        throw new CheckedBusinessException("default checked");
    }

    // 3. rollbackFor buộc rollback cho checked exception.
    @Transactional(rollbackFor = CheckedBusinessException.class)
    public void rollbackOnChecked() throws CheckedBusinessException {
        increase();
        throw new CheckedBusinessException("checked with rollbackFor");
    }

    // 4. noRollbackFor bỏ yêu cầu rollback đối với RuntimeException này.
    @Transactional(noRollbackFor = BusinessRuntimeException.class)
    public void noRollbackOnRuntime() {
        increase();
        throw new BusinessRuntimeException("runtime with noRollbackFor");
    }

    // 5. Rule lớp con IgnorableCheckedException cụ thể hơn Exception.
    @Transactional(
        rollbackFor = Exception.class,
        noRollbackFor = IgnorableCheckedException.class
    )
    public void checkedRules(boolean ignorable)
            throws CheckedBusinessException {
        increase();
        if (ignorable) {
            throw new IgnorableCheckedException("ignorable checked");
        }
        throw new CheckedBusinessException("other checked");
    }

    // 6. Rule lớp con CriticalRuntimeException cụ thể hơn lớp cha.
    @Transactional(
        noRollbackFor = BusinessRuntimeException.class,
        rollbackFor = CriticalRuntimeException.class
    )
    public void runtimeRules(boolean critical) {
        increase();
        if (critical) {
            throw new CriticalRuntimeException("critical");
        }
        throw new BusinessRuntimeException("noncritical");
    }

    private void increase() {
        int updated = jdbc.update(
            "UPDATE tx_counter SET value = value + 10 WHERE id = ?",
            1L
        );
        if (updated != 1) {
            throw new IllegalStateException("Missing test counter");
        }
    }
}
~~~

**Không tự ý thêm `@Transactional` vào `increase()`.** Đây là helper private được gọi **bên trong** public method đã có transaction. Transaction thực sự bắt đầu ở lời gọi proxy tới `defaultRuntime()`, `checkedRules(...)`, v.v. Private method không được proxy độc lập, nhưng các JDBC calls của nó vẫn sử dụng transaction đã mở của public method.

Giải thích từng nhóm:

- **`defaultRuntime()`**: lệnh tăng 10 chạy, ném `BusinessRuntimeException`; Spring mặc định rollback nên DB còn 100.
- **`defaultChecked()`**: lệnh tăng 10 chạy, ném checked `CheckedBusinessException`; Spring mặc định không đánh dấu rollback vì loại exception ấy, nên DB thành 110 và exception vẫn đi ra caller.
- **`rollbackOnChecked()`**: cùng một checked exception, nhưng `rollbackFor` đã yêu cầu rollback → DB trở lại 100.
- **`noRollbackOnRuntime()`**: cùng loại unchecked vốn rollback mặc định, nhưng `noRollbackFor` đổi lựa chọn → DB thành 110.
- **`checkedRules(true)`**: `IgnorableCheckedException` khớp cả `Exception.class` của rollback và rule `IgnorableCheckedException.class` của no-rollback. Lớp con cụ thể hơn thắng → DB 110.
- **`checkedRules(false)`**: `CheckedBusinessException` khớp `Exception.class` nhưng không khớp `IgnorableCheckedException.class` → rollback → DB 100.
- **`runtimeRules(true)`**: `CriticalRuntimeException` khớp cả no-rollback của cha lẫn rollback của lớp con → rule con thắng → DB 100.
- **`runtimeRules(false)`**: chỉ ném `BusinessRuntimeException`, no-rollback rule áp dụng → DB 110.

Lưu ý các exception được ném **sau một lệnh UPDATE thành công**, tức đây không phải sự khác biệt giả tạo do code chưa thay đổi dữ liệu.

### 5.5. Integration tests: chứng minh bằng giá trị sau transaction

Tệp `src/test/java/com/example/rollbackrules/RollbackRuleServiceTest.java`:

~~~java
package com.example.rollbackrules;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import static com.example.rollbackrules.RollbackRuleService.BusinessRuntimeException;
import static com.example.rollbackrules.RollbackRuleService.CheckedBusinessException;
import static com.example.rollbackrules.RollbackRuleService.CriticalRuntimeException;
import static com.example.rollbackrules.RollbackRuleService.IgnorableCheckedException;

@SpringBootTest
class RollbackRuleServiceTest {
    @Autowired
    private RollbackRuleService service;

    @Autowired
    private JdbcTemplate jdbc;

    // KHÔNG gắn @Transactional lên test.
    // Dữ liệu khởi tạo phải commit trước khi gọi service.
    @BeforeEach
    void resetCounter() {
        jdbc.update("DELETE FROM tx_counter");
        jdbc.update(
            "INSERT INTO tx_counter (id, value) VALUES (?, ?)",
            1L, 100L
        );
    }

    private long readValue() {
        Long value = jdbc.queryForObject(
            "SELECT value FROM tx_counter WHERE id = ?",
            Long.class, 1L
        );
        if (value == null) {
            throw new AssertionError("Missing counter");
        }
        return value;
    }

    @Test
    void runtimeExceptionRollsBackByDefault() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.defaultRuntime()
        );
        assertEquals(100L, readValue());
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.defaultChecked()
        );
        assertEquals(110L, readValue());
    }

    @Test
    void rollbackForMakesCheckedExceptionRollBack() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.rollbackOnChecked()
        );
        assertEquals(100L, readValue());
    }

    @Test
    void noRollbackForAllowsRuntimeExceptionToCommit() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.noRollbackOnRuntime()
        );
        assertEquals(110L, readValue());
    }

    @Test
    void moreSpecificNoRollbackForWinsForCheckedChild() {
        assertThrows(
            IgnorableCheckedException.class,
            () -> service.checkedRules(true)
        );
        assertEquals(110L, readValue());
    }

    @Test
    void broadRollbackForStillAppliesToOtherCheckedException() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.checkedRules(false)
        );
        assertEquals(100L, readValue());
    }

    @Test
    void moreSpecificRollbackForWinsForCriticalRuntimeChild() {
        assertThrows(
            CriticalRuntimeException.class,
            () -> service.runtimeRules(true)
        );
        assertEquals(100L, readValue());
    }

    @Test
    void noRollbackForParentAppliesToNoncriticalRuntime() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.runtimeRules(false)
        );
        assertEquals(110L, readValue());
    }
}
~~~

Tại sao **không** gắn `@Transactional` lên test class hoặc test method? Spring Test có cơ chế mở một transaction bao ngoài rồi tự rollback sau test. Nếu test chạy trong transaction đó, service `REQUIRED` có thể chỉ tham gia transaction của test; việc khẳng định dữ liệu ngay giữa test hoặc để framework rollback cuối test có thể che giấu điểm commit thực của service. Ở đây reset bằng JDBC ngoài transaction của test, tiếp theo gọi service proxy, rồi **đọc lại sau khi proxy đã xử lý commit/rollback**.

`assertThrows` chỉ xác nhận **loại exception**. `assertEquals(100L/110L, readValue())` mới chứng minh Spring đã xử lý transaction theo chính sách. Nếu chỉ test loại exception mà bỏ truy vấn DB, ta chưa biết dữ liệu có commit dở dang hay không.

Lời gọi phải đi qua bean `@Autowired RollbackRuleService` của Spring; tự `new RollbackRuleService(jdbc)` sẽ không kích hoạt transaction interceptor trong proxy mode.

## 6. Chạy lab và đối chiếu ma trận kết quả

Trong thư mục `rollback-rules-lab`, kiểm tra Java/Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

Yêu cầu JDK từ Java 17 và Maven cài đặt, có thể tải dependencies. Nếu dự án có Maven Wrapper, thay lệnh cuối bằng `./mvnw test` trên Linux/macOS hoặc `.\mvnw.cmd test` trên Windows PowerShell.

Với bộ source và cấu hình trên, **8 test** phải thành công. Maven Surefire báo số test chạy là 8, số failure/error là 0 (thứ tự, thời gian và log môi trường có thể khác nhau). Các giá trị kiểm tra là:

| Test / lời gọi | Exception thoát ra | Rule có hiệu lực | Giá trị đọc lại |
| --- | --- | --- | ---: |
| `defaultRuntime()` | `BusinessRuntimeException` | Mặc định rollback unchecked | **100** |
| `defaultChecked()` | `CheckedBusinessException` | Mặc định không rollback checked | **110** |
| `rollbackOnChecked()` | `CheckedBusinessException` | `rollbackFor` checked | **100** |
| `noRollbackOnRuntime()` | `BusinessRuntimeException` | `noRollbackFor` unchecked | **110** |
| `checkedRules(true)` | `IgnorableCheckedException` | No-rollback lớp con thắng rollback lớp cha | **110** |
| `checkedRules(false)` | `CheckedBusinessException` | Rollback theo `Exception.class` | **100** |
| `runtimeRules(true)` | `CriticalRuntimeException` | Rollback lớp con thắng no-rollback lớp cha | **100** |
| `runtimeRules(false)` | `BusinessRuntimeException` | No-rollback lớp cha áp dụng | **110** |

Mỗi test bắt đầu từ `value=100`. Điều khác biệt duy nhất là **loại exception** hoặc **rule** được khai báo. Không có phép ghi ở database nào ngoài update cộng 10 trong service và reset của test.

### Quan sát một lỗi checked gây commit

~~~text
Test đặt value=100 (đã commit).
  |
  v
proxy.defaultChecked()
  |
  +-- Spring mở JDBC transaction
  +-- UPDATE value = value + 10   (trong transaction: 110)
  +-- throw CheckedBusinessException
  |
  v
Transaction interceptor thấy không có rollback rule khớp.
Checked exception mặc định không yêu cầu rollback.
  |
  v
Spring commit transaction, rồi exception đi đến assertThrows.
  |
  v
Test SELECT -> value=110.
~~~

### Cùng checked exception nhưng rollbackFor đổi kết quả

~~~text
Test đặt value=100 (đã commit).
  |
  v
proxy.rollbackOnChecked()
  |
  +-- UPDATE value = value + 10   (trong transaction: 110)
  +-- throw CheckedBusinessException
  |
  v
rollbackFor=CheckedBusinessException.class khớp
  |
  v
Spring yêu cầu rollback.
  |
  v
Test SELECT -> value=100.
~~~

Điểm quan trọng: **ngoại lệ xuất hiện trong cả hai trường hợp**. Sự khác biệt nằm ở **kết quả hoàn tất transaction**, không phải method có ném lỗi hay không.

## 7. Chọn rule khi có kế thừa: cách dự đoán có hệ thống

Giả sử định nghĩa:

~~~text
Exception
└── CheckedBusinessException
    └── IgnorableCheckedException

RuntimeException
└── BusinessRuntimeException
    └── CriticalRuntimeException
~~~

**Trường hợp A:**

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = IgnorableCheckedException.class
)
~~~

Khi method ném `IgnorableCheckedException`, cả `Exception.class` lẫn `IgnorableCheckedException.class` đều khớp. Rule no-rollback của chính kiểu ngoại lệ cụ thể hơn nên được chọn. Khi method ném `CheckedBusinessException`, rule no-rollback cho lớp con **không** khớp: lớp cha không tự kế thừa ngược các chính sách dành riêng cho lớp con. Rule rollback của `Exception.class` có hiệu lực.

**Trường hợp B:**

~~~java
@Transactional(
    noRollbackFor = BusinessRuntimeException.class,
    rollbackFor = CriticalRuntimeException.class
)
~~~

Khi ném `CriticalRuntimeException`, rollback của lớp con thắng. Khi ném đúng `BusinessRuntimeException`, no-rollback thắng. Đừng diễn giải thành “noRollbackFor luôn thắng” hay “rollbackFor luôn thắng”; **độ cụ thể của rule khớp** mới quyết định trong ví dụ này.

**Trường hợp C: không có rule liên quan.** Ném `NullPointerException` với cấu hình ở trường hợp B: nó không kế thừa `BusinessRuntimeException` nên không khớp cả hai rule khai báo; Spring tiếp tục dùng mặc định rollback với unchecked exception.

**Trường hợp D: hai rule xung đột cùng cấp.** Không thiết kế cùng một class vừa nằm trong `rollbackFor` vừa nằm trong `noRollbackFor`. Tài liệu khuyến khích lựa chọn rule rõ ràng; việc dựa vào thứ tự khai báo hoặc các chi tiết nội bộ khi độ cụ thể bằng nhau làm chính sách khó hiểu và dễ thay đổi ngoài ý muốn.

### Phân biệt "kiểu ngoại lệ được ném" với "nguyên nhân bọc bên trong"

Nếu method bắt `IOException` rồi ném `new IllegalStateException("failed", ioException)`, exception **thoát ra ngoài** là `IllegalStateException`. Một `rollbackFor = IOException.class` **không mặc nhiên khớp** lớp nguyên nhân trong `getCause()`; Spring kiểm tra exception mà interceptor nhận được để áp rollback rules.

Ngược lại, nếu method ném trực tiếp `IOException` đã khai báo và nó thoát qua proxy, `rollbackFor = IOException.class` có thể áp đúng. Khi chọn rule, xác định exception class **thực tế qua ranh giới service**, không chỉ class ở tầng thấp hoặc mã lỗi trong message.

## 8. Khi nào dùng rollbackFor, khi nào dùng noRollbackFor?

### Trường hợp phù hợp với rollbackFor

Dùng khi một **checked exception** biểu thị rằng các cập nhật đã thực hiện trong transaction **không được phép commit**.

Ví dụ service xử lý file đã ghi trước một phần dữ liệu, sau đó gặp `IOException` hoặc ngoại lệ nghiệp vụ checked báo quá trình chưa hoàn chỉnh. Nếu toàn bộ lô phải nguyên tử:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // Các JDBC updates và xử lý input thuộc cùng nghiệp vụ.
}
~~~

Đây là ví dụ rút gọn để minh họa annotation. Nếu hệ thống phát hành theo cấu hình rollback mặc định cho mọi exception, cần kiểm tra quy tắc hiện hành; vẫn có thể khai báo rõ khi muốn contract hiển nhiên ở method.

### Trường hợp cân nhắc noRollbackFor

Chỉ dùng khi exception **không làm mất hiệu lực các thay đổi đã ghi**.

Ví dụ sau khi database lưu một trạng thái hợp lệ, phương thức cần thông báo một ngoại lệ nghiệp vụ để caller quyết định chuyển sang luồng tiếp theo. Nếu các thay đổi vẫn phải được giữ lại, có thể cấu hình `noRollbackFor = SomeBusinessException.class`.

Nhưng nếu thao tác có hai bước “trừ tiền” và “cộng tiền”, rồi ném exception sau bước trừ tiền, cấu hình no-rollback cho exception ấy sẽ **commit một giao dịch dở dang**. Không được dùng noRollbackFor chỉ để “tránh mất dữ liệu đã ghi” khi thực chất phải bảo đảm atomicity.

**Đề xuất thiết kế:** nếu “không tìm thấy/không còn hàng” là kết quả nghiệp vụ bình thường, nhiều trường hợp nên trả về một **result type** thay vì lạm dụng exception có no-rollback. Như vậy semantics thành công/thất bại và hậu quả database được diễn đạt rõ hơn.

## 9. Các giới hạn và bẫy thường gặp

### 9.1. Bắt/nuốt exception trước khi nó ra khỏi phương thức

~~~java
@Transactional(rollbackFor = IOException.class)
public void operation() {
    try {
        writeToDatabase();
        readExternalFile();
    } catch (IOException ex) {
        // Nuốt exception: method trả về bình thường.
    }
}
~~~

Đoạn trên là **mã minh họa không độc lập**; `writeToDatabase()` và `readExternalFile()` chưa được khai báo, dùng để trình bày lỗi. Khi `IOException` bị bắt rồi nuốt, transaction interceptor **không thấy** ngoại lệ ấy lúc method kết thúc. `rollbackFor` không tự hoạt động chỉ vì exception đã xuất hiện ở giữa code. Cần ném lại exception theo contract hoặc trong trường hợp thật sự cần, đánh dấu rollback-only qua API Spring. Ưu tiên thiết kế luồng lỗi rõ ràng hơn là dựa vào marker thủ công.

### 9.2. Self-invocation hoặc tạo bean bằng new

~~~java
public void outer() {
    this.inner(); // Không đi qua Spring proxy trong proxy mode mặc định.
}

@Transactional(rollbackFor = IOException.class)
public void inner() {
    // ...
}
~~~

Đây là **một đoạn minh họa**, chưa đủ để biên dịch độc lập. Khi target gọi `this.inner()`, interceptor của Spring AOP thường không được áp cho lời gọi nội bộ đó. Tương tự, `new RollbackRuleService(jdbc)` tự tạo instance bên ngoài Spring container sẽ không có proxy transaction.

Annotation không thể giúp nếu **không có transaction được kích hoạt**. Trong lab, tất cả public method được gọi qua service `@Autowired` để tránh sai lệch này.

### 9.3. noRollbackFor không hủy trạng thái rollback-only sẵn có

Giả sử operation A nằm trong một transaction lớn. Một operation B bên trong đã đánh dấu transaction `rollback-only`, hoặc database đã đưa giao dịch vào trạng thái không thể commit do lỗi SQL. Sau đó operation A ném một ngoại lệ cấu hình `noRollbackFor`.

Rule “không rollback vì loại exception này” **không xóa** dấu rollback-only và **không** buộc database tiếp tục commit một giao dịch đã mất hiệu lực. Khi transaction ngoài cố commit, Spring có thể phát hiện/ báo `UnexpectedRollbackException` hoặc database trả lỗi tùy hoàn cảnh.

Điều này đặc biệt quan trọng với các lỗi `DataAccessException` do JDBC/database phát ra: chính lệnh SQL và engine có thể làm transaction không thể commit. Đừng dùng noRollbackFor như công tắc “bất chấp lỗi database”.

### 9.4. Exception phát sinh sau commit

Nếu method transactional kết thúc và transaction manager **đã commit**, sau đó controller hoặc HTTP response serialization mới ném exception, rollback rules trên method trước đó **không thể hoàn tác commit đã xong**. Ranh giới transaction phải bao trọn các thay đổi dữ liệu cần atomicity, nhưng không nên kéo dài qua network call chỉ để tránh vấn đề này.

Nếu client mất phản hồi ngay sau commit, client không chắc kết quả đã được ghi; cơ chế `rollbackFor`/`noRollbackFor` không giải quyết idempotency hoặc duplicate retry. Cần request ID, trạng thái nghiệp vụ và chiến lược retry phù hợp.

### 9.5. Exception bị dịch hoặc bọc ở lớp khác

Một JDBC exception có thể được Spring dịch thành `DataAccessException` (unchecked) thay vì loại checked ở driver. Một service có thể wrap checked exception thành một unchecked business exception. Do đó rule nên được viết theo **loại lỗi thực sự thoát ra từ method giao dịch**, không chỉ theo declaration của repository.

Nếu bạn muốn rollback mọi bất biến nghiệp vụ bị vi phạm nhưng “không rollback” cho một ngoại lệ cho phép giữ dữ liệu, hãy xây dựng phân cấp exception tương ứng, chọn rule theo **kiểu**, rồi test riêng các subtype.

### 9.6. Propagation và nhiều transaction manager

`@Transactional` mặc định dùng `Propagation.REQUIRED`: nếu có transaction ngoài, method tham gia transaction đó; điểm commit do transaction owner quyết định. Nếu method sử dụng `REQUIRES_NEW`, nó có transaction độc lập với phạm vi ngoài khi manager hỗ trợ. Vì vậy kết quả của rule tại một method phụ thuộc transaction nào đang được xử lý.

Với nhiều `DataSource`, service phải dùng `PlatformTransactionManager` thích hợp. `rollbackFor` không thể rollback một nguồn dữ liệu mà manager hiện tại không quản lý. Transaction database cũng không tự hoàn tác email, message broker, HTTP call hoặc thay đổi trong hệ thống thứ ba.

### 9.7. Test có @Transactional che khuất kết quả

Spring Test có thể rollback transaction của test **sau khi test kết thúc**, kể cả khi service không tự quản lý transaction theo kỳ vọng. Nếu muốn chứng minh service commit hay rollback, tránh bọc test bằng `@Transactional` hoặc dùng chiến lược test kiểm soát ranh giới rõ ràng. Trong lab, `@BeforeEach` reset dữ liệu ngoài transaction của test và assertions đọc DB sau mỗi method.

### 9.8. Hiểu sai noRollbackFor là bắt hoặc bỏ qua exception

`noRollbackFor` **không catch** và **không suppress** exception. Java method vẫn ném lỗi, caller vẫn phải handle theo kiểu Java. Nó chỉ ảnh hưởng đến **quyết định rollback của transaction advice**. Nếu code cần báo thành công có cảnh báo, sử dụng kiểu kết quả trả về thường tốt hơn việc ném exception nhưng vẫn commit.

### 9.9. Thay đổi mặc định toàn cục mà quên kiểm tra lại

Trong Spring Framework 6.2+, các ứng dụng có thể cấu hình default rollback cho mọi exception khi dùng annotation transaction management. Nếu ứng dụng bật `rollbackOn = ALL_EXCEPTIONS`, ví dụ `defaultChecked()` của lab sẽ không còn cho kết quả 110 nếu không có rule ghi đè. Khi QA môi trường thật, xác minh luôn transaction configuration toàn cục và Spring version.

## 10. So sánh cấu hình annotation với XML

Phạm vi bài này tập trung `rollbackFor`/`noRollbackFor` **theo kiểu ngoại lệ** ở Java annotation. Có thể bắt gặp cấu hình tương đương ở dự án dùng Spring XML:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="process*"
                   rollback-for="com.example.BusinessCheckedException"
                   no-rollback-for="com.example.NonCriticalException"/>
    </tx:attributes>
</tx:advice>
~~~

Đây là **mảnh XML minh họa**, cần XML namespace `tx`, transaction manager và advisor/pointcut tương ứng để thành cấu hình hoạt động. Với XML, `rollback-for`/`no-rollback-for` thường là **chuỗi tên/pattern** của exception; không nên suy ra nó có cùng kiểu type-safe `Class` như `@Transactional(rollbackFor = Foo.class)`. Cần đặc biệt tránh tên pattern quá rộng.

Đối với code Java mới, khi import được class, ưu tiên khai báo `rollbackFor = FooException.class` và `noRollbackFor = BarException.class` để compiler hỗ trợ kiểm tra và tránh match nhầm tên.

## 11. Quy trình thiết kế rule đúng nghiệp vụ

Trước khi thêm một ngoại lệ vào `rollbackFor` hoặc `noRollbackFor`, hãy xác định:

1. **Bất biến sau lỗi là gì?** Nếu method đã thực hiện một hoặc nhiều câu ghi, có được phép giữ lại chúng không?
2. **Exception nào thực sự thoát qua Spring proxy?** Là checked hay unchecked, type chính xác là gì, có bị wrap không?
3. **Transaction đã được mở đúng chỗ chưa?** Caller có đi qua proxy, dùng đúng manager và cùng database resource không?
4. **Có rule khác hoặc global policy nào khớp không?** Xét inheritance, tính cụ thể và khả năng ghi đè.
5. **Có transaction bên ngoài hoặc rollback-only sẵn có không?** Không hứa sẽ commit chỉ vì method cấu hình noRollbackFor.
6. **Test có đọc lại database sau khi method kết thúc không?** Thay đổi một chút trong code mà không đo trạng thái persisted là chưa đủ.

Một hệ thống thường có những nhóm lỗi:

| Loại lỗi | Chính sách khuyến nghị để cân nhắc |
| --- | --- |
| Exception kỹ thuật báo thao tác không hoàn thành, đã cập nhật dở dang | Rollback toàn bộ nghiệp vụ. |
| Checked business exception báo nghiệp vụ không hợp lệ sau một phần thay đổi | Dùng `rollbackFor` hoặc chính sách toàn cục phù hợp. |
| RuntimeException từ lỗi lập trình hoặc invariant bị vi phạm | Giữ rollback mặc định; đừng no-rollback tùy tiện. |
| Ngoại lệ thuần báo trạng thái đã được ghi hợp lệ và cần caller xử lý | Có thể cân nhắc `noRollbackFor`, nhưng nên đánh giá việc dùng result type. |
| Constraint violation/SQL failure đã làm DB transaction lỗi | Không dùng noRollbackFor để ép commit; xử lý lỗi, rollback/retry an toàn. |

Không phải mọi checked exception đều “nhẹ” và mọi unchecked exception đều “nặng”. Đó chỉ là cơ chế kiểm tra của Java compiler; Spring cung cấp custom rules để điều chỉnh theo nghiệp vụ.

## 12. Bài tập mở rộng

**Bài tập A — Dự đoán kết quả trước khi chạy:** giữ `@Transactional(rollbackFor = CheckedBusinessException.class)` và ném `IgnorableCheckedException` (lớp con). Kết quả kỳ vọng: **rollback**, vì lớp con thuộc họ checked exception đã khai báo. Viết test xác nhận giá trị 100.

**Bài tập B — Cấu hình exception cụ thể:** thêm `noRollbackFor = IgnorableCheckedException.class` vào cùng method của bài tập A. Kết quả với exception cụ thể: **commit**, vì no-rollback của lớp con cụ thể hơn rollback của lớp cha. Với `CheckedBusinessException` gốc, vẫn rollback.

**Bài tập C — So sánh wrap và rethrow:** một method ném trực tiếp `CheckedBusinessException`; method khác bắt nó rồi ném `IllegalStateException`. Nếu không có rule riêng, dự đoán checked sẽ commit, unchecked sẽ rollback. Viết integration test đọc lại database để kiểm tra.

**Bài tập D — Thử nuốt exception:** tại bản sao lab, catch và không rethrow ngoại lệ ở cuối service method. Chú ý phương thức trả về bình thường; liệu transaction interceptor có biết đó là một lỗi cần rollback? Chỉ thực hành trên H2 thử nghiệm.

**Bài tập E — Đọc rule như một bảng quyết định:** vẽ phân cấp `Exception -> ParentChecked -> ChildChecked`; cấu hình rollback cho cha và no-rollback cho con; xác định kết quả của mỗi kiểu trước khi chạy test.

**Bài tập F — Kiểm tra kết hợp với transaction ngoài:** nếu một method khác mở transaction bao ngoài, bắt exception của method trong rồi vẫn cố commit, có thể xảy ra điều gì khi transaction đã bị đánh dấu rollback-only? Tìm hiểu `UnexpectedRollbackException` và điều kiện ném của transaction manager; không giả định bắt exception là đủ để phục hồi transaction.

## 13. Câu hỏi tự đánh giá

1. **`rollbackFor = IOException.class` có áp dụng cho lớp con của IOException không?** — Có, type-based rule áp dụng cho kiểu được khai báo và subtype.
2. **`noRollbackFor = IllegalArgumentException.class` có tự bắt và bỏ exception không?** — Không. Exception vẫn được truyền lên; nó chỉ thay đổi lựa chọn rollback do exception ấy.
3. **Checked exception không có custom rule làm gì theo mặc định?** — Với cấu hình thông thường, Spring không yêu cầu rollback chỉ vì checked exception, nên transaction mới có thể commit.
4. **Nếu `rollbackFor = Exception.class` và `noRollbackFor = IgnorableCheckedException.class`, ném IgnorableCheckedException thì sao?** — No-rollback của kiểu cụ thể hơn thắng, giả sử transaction còn có thể commit.
5. **Nếu `noRollbackFor = BusinessRuntimeException.class` và `rollbackFor = CriticalRuntimeException.class`, ném CriticalRuntimeException thì sao?** — Rollback của lớp con cụ thể hơn thắng.
6. **Vì sao phải gọi method qua Spring-managed bean?** — Spring proxy cần intercept để áp `@Transactional` và các rollback rules.
7. **Vì sao chỉ kiểm tra `assertThrows` chưa đủ?** — Nó không chứng minh commit hay rollback; cần đọc dữ liệu sau lời gọi.
8. **Nếu SQL đã đánh dấu transaction rollback-only, noRollbackFor có cứu commit được không?** — Không. Rule không xóa rollback-only.
9. **`rollbackForClassName` có chính xác giống `rollbackFor` không?** — Không: một bên dựa trên pattern tên ngoại lệ; một bên dựa trên kiểu Java.
10. **Một lỗi HTTP xảy ra sau database commit có được rollback bằng rollbackFor của service không?** — Không. Transaction đã kết thúc; cần thiết kế idempotency/compensation nếu nghiệp vụ đòi hỏi.

## 14. Tổng kết

- `rollbackFor` cho Spring biết **nên rollback khi exception thuộc kiểu nào thoát ra**.
- `noRollbackFor` cho Spring biết **không yêu cầu rollback vì exception thuộc kiểu nào**, kể cả đó là RuntimeException.
- Mặc định thường là rollback cho `RuntimeException`/`Error` và không rollback cho checked exception, trừ khi đã thay default policy toàn cục.
- Với nhiều custom rules cùng khớp, **rule cụ thể nhất** thắng; ưu tiên class-based rules thay vì string pattern để tránh khớp nhầm.
- **Lỗi phải qua transaction interceptor**, transaction phải được quản lý đúng và database còn khả năng commit. Catch/nuốt exception hoặc đánh dấu rollback-only ở nơi khác có thể thay đổi kết quả.
- **Kết quả database sau test** mới là bằng chứng về rollback/commit; không suy từ exception name hay việc annotation xuất hiện trong source.

> **Nguyên tắc thực hành:** trước khi cho một exception vào `noRollbackFor`, hãy xác nhận rằng **mọi thay đổi đã thực hiện trước lúc exception xảy ra đều được phép giữ lại**. Nếu câu trả lời là không, transaction phải rollback.

### Tài liệu chính thức

- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Using @Transactional / Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — @Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Spring Test Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)