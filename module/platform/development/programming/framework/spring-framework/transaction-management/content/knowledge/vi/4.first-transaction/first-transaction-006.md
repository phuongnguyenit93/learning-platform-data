# Tạo lỗi giữa luồng và quan sát rollback

## 1. Mục tiêu của bài thực hành

Một transaction chỉ thực sự có ý nghĩa khi bạn **chứng minh được nó hoàn tác các thao tác đã chạy trước lúc lỗi**. Bài này tạo lỗi chủ động ở giữa một nghiệp vụ Spring Framework, rồi đọc lại dữ liệu để kiểm tra kết quả.

Sau bài học, bạn có thể:

- Phân biệt **thay đổi đã thực thi trong transaction** với **thay đổi đã commit**.
- Xác định đúng điểm bắt đầu, điểm phát sinh lỗi và điểm rollback của một phương thức có `@Transactional`.
- Viết phép thử tích hợp cho hai tình huống: lỗi **sau câu SQL đầu tiên** và lỗi **sau cả hai câu SQL nhưng trước commit**.
- Giải thích tại sao exception phải đi qua transaction interceptor, và vì sao bắt/nuốt lỗi có thể khiến database commit dữ liệu dở dang.
- Tự đối chứng bằng cách bỏ transaction trong **môi trường học thử** và quan sát các assertion thất bại.

Chúng ta dùng **Java 17+, Spring Boot 3.5.0, Spring JDBC, H2 in-memory và JUnit 5**. Chạy test bằng Maven; không cần API HTTP, không cần cơ sở dữ liệu chạy riêng. Tất cả thay đổi chỉ nằm trong database thử nghiệm H2.

## 2. Tình huống: chuyển tiền không được cập nhật dở dang

Có hai tài khoản trong cùng database:

| Tài khoản | Số dư ban đầu | Sau chuyển 200 thành công | Sau lỗi và rollback |
| --- | ---: | ---: | ---: |
| A (id = 1) | 1.000 | 800 | 1.000 |
| B (id = 2) | 500 | 700 | 500 |
| **Tổng** | **1.500** | **1.500** | **1.500** |

Nghiệp vụ phải thực hiện theo thứ tự:

1. Trừ 200 từ tài khoản A bằng `UPDATE`.
2. Cộng 200 cho tài khoản B bằng `UPDATE`.
3. Chỉ **commit** khi hoàn thành toàn bộ nghiệp vụ.

Để kiểm tra rollback, ta **cố tình phát sinh exception** sau bước 1, trước bước 2. Thời điểm đó, câu SQL trừ tiền đã ảnh hưởng một hàng; một truy vấn thực hiện **trong cùng transaction** có thể thấy A = 800. Nhưng giao dịch chưa commit. Khi exception thoát ra và Spring rollback, kết quả bền vững phải là A = 1.000, B = 500.

Thêm một phép thử khó hơn: để cả hai `UPDATE` chạy xong, **rồi mới phát sinh exception trước khi phương thức trả về**. Cả phần trừ A và cộng B đều phải bị rollback. Nó chứng minh rằng “SQL đã chạy xong” không đồng nghĩa với “transaction đã commit”.

~~~text
Caller
  |
  v
Spring transaction proxy
  |
  +-- BEGIN
  |     |
  |     +-- UPDATE account A: 1000 -> 800
  |     |
  |     +-- [ĐIỂM LỖI 1] Exception? -- Có --> ROLLBACK
  |     |
  |     +-- UPDATE account B: 500 -> 700
  |     |
  |     +-- [ĐIỂM LỖI 2] Exception? -- Có --> ROLLBACK
  |     |
  |     +-- Không có lỗi ----------------> COMMIT
  |
  v
Caller nhận kết quả hoặc exception
~~~

Một **lỗi sau khi transaction đã commit** là tình huống khác: rollback không thể tự quay ngược một commit đã hoàn tất. Bài này chủ động tạo lỗi **trước ranh giới commit** để quan sát tính nguyên tử.

## 3. Chuẩn bị dự án Spring Boot có thể chạy

Tạo thư mục `rollback-lab` với cấu trúc:

~~~text
rollback-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/rollback/
    │   │   ├── RollbackLabApplication.java
    │   │   └── MoneyTransferService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/rollback/
            └── MoneyTransferServiceTest.java
~~~

Nếu tạo từ **Spring Initializr**, chọn Java 17, Maven, Spring Boot 3.5.0 và dependency **JDBC API**, **H2 Database**, **Spring Boot Starter Test**. Bạn cũng có thể tạo trực tiếp các tệp dưới đây, sau đó chạy với Maven đã cài sẵn.

### 3.1. Tệp `pom.xml`

~~~xml
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
    <artifactId>rollback-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter-jdbc` cung cấp Spring JDBC/`JdbcTemplate` và cơ chế transaction JDBC; `h2` là database quan sát; `spring-boot-starter-test` cung cấp JUnit 5 và hỗ trợ kiểm thử Spring.

### 3.2. Tệp `src/main/resources/application.properties`

~~~properties
spring.datasource.url=jdbc:h2:mem:rollback_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

H2 tồn tại trong bộ nhớ tiến trình Java. Khi tiến trình kết thúc, dữ liệu thử nghiệm không được dùng làm dữ liệu lâu dài. Tham số `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại trong suốt vòng đời tiến trình, kể cả khi connection cuối đã đóng. Spring Boot chạy `schema.sql` lúc khởi tạo, và test sẽ tự chèn lại dữ liệu gốc trước mỗi trường hợp.

### 3.3. Tệp `src/main/resources/schema.sql`

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
~~~

`balance` dùng số nguyên chỉ để đơn giản hóa bài học và tránh sai số của `double`. Với ứng dụng tài chính thực tế phải thiết kế đơn vị tiền, miền giá trị, kiểm tra tràn số, lịch sử giao dịch, quyền truy cập và idempotency phù hợp. Ràng buộc `CHECK` chỉ ngăn số dư âm; nó không tự động đảm bảo đủ cả hai bước chuyển tiền.

### 3.4. Tệp `src/main/java/com/example/rollback/RollbackLabApplication.java`

~~~java
package com.example.rollback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RollbackLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackLabApplication.class, args);
    }
}
~~~

Class này là điểm khởi động Spring Boot và cho phép `@SpringBootTest` tìm cấu hình ứng dụng. Các class service và test phải thuộc cùng package `com.example.rollback` như cấu trúc nêu trên.

## 4. Viết service có hai điểm tạo lỗi rõ ràng

**Tệp `src/main/java/com/example/rollback/MoneyTransferService.java`:**

~~~java
package com.example.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {
    public enum FailurePoint {
        NONE,
        AFTER_DEBIT,
        AFTER_CREDIT
    }

    private final JdbcTemplate jdbc;

    public MoneyTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(
            long sourceId,
            long destinationId,
            long amount,
            FailurePoint failurePoint) {

        if (amount <= 0 || sourceId == destinationId || failurePoint == null) {
            throw new IllegalArgumentException("Invalid transfer input");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );

        if (debited != 1) {
            throw new IllegalStateException(
                "Source missing or insufficient balance"
            );
        }

        // Lỗi chủ động giữa hai lệnh UPDATE.
        if (failurePoint == FailurePoint.AFTER_DEBIT) {
            long balanceInsideTransaction = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                Long.class,
                sourceId
            );
            throw new IllegalStateException(
                "FAIL_AFTER_DEBIT: source balance inside transaction=" +
                balanceInsideTransaction
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, destinationId
        );

        if (credited != 1) {
            throw new IllegalStateException("Destination account missing");
        }

        // Cả hai UPDATE đã thực thi; transaction vẫn chưa commit.
        if (failurePoint == FailurePoint.AFTER_CREDIT) {
            throw new IllegalStateException("FAIL_AFTER_CREDIT");
        }
    }
}
~~~

### Giải thích chính xác từng thời điểm

**Trước dòng `@Transactional`:** Spring quản lý bean `MoneyTransferService`. Khi một bean khác gọi `transfer(...)` **qua proxy** của Spring, transaction interceptor yêu cầu transaction manager bắt đầu transaction hoặc tham gia transaction có sẵn. Trong bài lab, test không có transaction bao ngoài, nên mỗi lời gọi service tạo một transaction mới.

**Sau lệnh trừ tiền:** `JdbcTemplate.update(...)` trả về số hàng đã cập nhật. Nếu tài khoản nguồn tồn tại, đủ tiền và SQL hợp lệ, nó trả về `1`; số dư của A trở thành **800 bên trong transaction**. Điều này chưa có nghĩa dữ liệu đã commit. Khi cùng connection/query trong transaction đọc lại, nó có thể nhìn thấy chính thay đổi chưa commit đó.

**Tại `AFTER_DEBIT`:** code chủ động `throw new IllegalStateException(...)`. Đây là `RuntimeException`, phù hợp quy tắc rollback mặc định của Spring. Lệnh cập nhật B chưa được gọi. Exception rời khỏi service, transaction interceptor bắt lỗi rồi yêu cầu rollback. Trên H2, giá trị A = 800 được hoàn tác về 1.000.

**Tại `AFTER_CREDIT`:** A đã được trừ và B đã được cộng, nhưng phương thức chưa hoàn thành bình thường nên transaction chưa commit. `IllegalStateException` vẫn làm rollback cả hai lệnh, đưa A/B trở về 1.000/500.

**Tại `NONE`:** cả hai lệnh thành công, method trả về bình thường; transaction interceptor commit. Trạng thái được xác nhận là A = 800, B = 700.

**Khi tài khoản đích không tồn tại:** `jdbc.update(...)` trả về `0`, service phát sinh exception *sau khi đã trừ tiền nguồn*. Đây là một tình huống lỗi nghiệp vụ thực tế, khác với lỗi cố tình chèn, nhưng kết quả rollback mong đợi giống nhau.

Sử dụng `@Transactional` trên **public service method** giúp đặt ranh giới transaction ở nơi bao trùm toàn bộ nghiệp vụ. Đặt các transaction riêng trên từng câu cập nhật repository mà không có transaction bao ngoài có thể khiến lệnh đầu tiên commit trước khi lệnh tiếp theo thất bại.

## 5. Viết integration test đo chính dữ liệu đã lưu

**Tệp `src/test/java/com/example/rollback/MoneyTransferServiceTest.java`:**

~~~java
package com.example.rollback;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static com.example.rollback.MoneyTransferService.FailurePoint.AFTER_CREDIT;
import static com.example.rollback.MoneyTransferService.FailurePoint.AFTER_DEBIT;
import static com.example.rollback.MoneyTransferService.FailurePoint.NONE;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MoneyTransferServiceTest {
    @Autowired
    private MoneyTransferService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void resetAccounts() {
        jdbc.update("DELETE FROM account");
        jdbc.update(
            "INSERT INTO account (id, balance) VALUES (?, ?)",
            1L, 1000L
        );
        jdbc.update(
            "INSERT INTO account (id, balance) VALUES (?, ?)",
            2L, 500L
        );
    }

    @Test
    void noFailureCommitsBothUpdates() {
        service.transfer(1L, 2L, 200L, NONE);

        assertEquals(800L, balanceOf(1L));
        assertEquals(700L, balanceOf(2L));
    }

    @Test
    void failureBetweenUpdatesRollsBackFirstUpdate() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 2L, 200L, AFTER_DEBIT)
        );

        assertEquals(
            "FAIL_AFTER_DEBIT: source balance inside transaction=800",
            error.getMessage()
        );

        // Đọc lại sau khi lời gọi qua Spring proxy kết thúc bằng rollback.
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void failureAfterBothUpdatesRollsBackEverything() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 2L, 200L, AFTER_CREDIT)
        );

        assertEquals("FAIL_AFTER_CREDIT", error.getMessage());
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void invalidDestinationAlsoRollsBackDebit() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 99L, 200L, NONE)
        );

        assertEquals("Destination account missing", error.getMessage());
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    private long balanceOf(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class,
            id
        );
    }
}
~~~

### Tại sao cách viết test này mới chứng minh được rollback?

1. **`@SpringBootTest` khởi tạo Spring context thật** và tiêm `MoneyTransferService` do Spring quản lý, vì thế lời gọi đi qua transaction proxy. Nếu tự `new MoneyTransferService(jdbc)` rồi gọi, annotation không được kích hoạt qua proxy mặc định.
2. **`@BeforeEach` làm sạch và khởi tạo dữ liệu độc lập cho mỗi test.** Test nào chạy trước cũng không ảnh hưởng kết quả test sau.
3. **Không có `@Transactional` trên class test hoặc test method.** Nếu test tự mở transaction bên ngoài, phép thử có thể “trông như rollback đúng” vì transaction của chính test được framework rollback cuối test, dù service chưa quản lý transaction như dự định. Với cách viết ở đây, `jdbc.update` trong phần chuẩn bị được commit ngoài transaction của service, và đọc sau exception quan sát trạng thái đã hoàn tất của transaction service.
4. **`assertThrows` chỉ kiểm tra lỗi đã được phát ra; assertions đọc DB mới kiểm tra tính nguyên tử.** Một test chỉ xác nhận exception mà không đọc trạng thái sau đó chưa chứng minh rollback.
5. **Kiểm tra cả hai tài khoản** quan trọng hơn chỉ kiểm tra exception hoặc một số dư. Test `AFTER_CREDIT` đặc biệt cho thấy cả hai thay đổi đã chạy rồi vẫn bị hoàn tác.
6. **Kiểm tra thông điệp 800 bên trong transaction:** lúc lỗi `AFTER_DEBIT` được tạo ra, truy vấn cùng transaction thực sự nhìn thấy số dư trung gian 800; nhưng sau rollback, test đọc thấy 1.000. Đó là khác biệt giữa **thay đổi tạm thời** và **dữ liệu đã commit**.

Các test sử dụng H2 cùng `DataSource` cho Spring transaction manager và `JdbcTemplate`. Nếu thực tế ứng dụng có nhiều `DataSource`/transaction manager, bạn phải chọn đúng transaction manager và bảo đảm các thao tác cần nguyên tử thuộc phạm vi quản lý của nó.

## 6. Chạy test và diễn giải kết quả

Mở terminal tại thư mục `rollback-lab`. Kiểm tra môi trường:

~~~bash
java -version
mvn -version
~~~

Yêu cầu JDK từ Java 17; hãy bảo đảm Maven đang sử dụng đúng JDK đó. Chạy:

~~~bash
mvn test
~~~

Nếu tạo dự án bằng Spring Initializr và có Maven Wrapper, có thể dùng `./mvnw test` trên Linux/macOS hoặc `.\mvnw.cmd test` trên Windows PowerShell.

JUnit chạy bốn test trong một context Spring Boot; thứ tự không cần cố định. Khi dependency/biên dịch/khởi tạo H2 thành công, báo cáo Maven Surefire phải cho thấy **4 test passed, 0 failure, 0 error**. Các dòng log Spring, phiên bản thư viện và thời gian chạy không cố định.

| Test | Thời điểm tạo lỗi | Giá trị quan sát sau lời gọi | Điều được chứng minh |
| --- | --- | --- | --- |
| `noFailureCommitsBothUpdates` | Không tạo lỗi | A = 800, B = 700 | Đường thành công commit cả hai UPDATE. |
| `failureBetweenUpdatesRollsBackFirstUpdate` | Sau trừ A, trước cộng B | A = 1.000, B = 500 | Lệnh trừ đã chạy nhưng bị rollback. |
| `failureAfterBothUpdatesRollsBackEverything` | Sau trừ A và cộng B, trước commit | A = 1.000, B = 500 | Cả hai SQL đã chạy vẫn được rollback. |
| `invalidDestinationAlsoRollsBackDebit` | Sau trừ A, khi cập nhật B ảnh hưởng 0 hàng | A = 1.000, B = 500 | Lỗi nghiệp vụ không làm mất phần đã trừ. |

### Quan sát chi tiết test lỗi giữa luồng

Theo `failureBetweenUpdatesRollsBackFirstUpdate`:

~~~text
Trước test:
    SELECT A -> 1000
    SELECT B -> 500

Bên trong @Transactional:
    UPDATE A -200 -> A=800 trong transaction
    SELECT A cùng transaction -> 800
    throw IllegalStateException("FAIL_AFTER_DEBIT: ...=800")

Spring transaction interceptor:
    RuntimeException thoát khỏi method
    -> rollback transaction

Sau khi lời gọi service kết thúc:
    SELECT A -> 1000
    SELECT B -> 500
~~~

**Tại sao không cần gọi `rollback()` trong service?** Bởi Spring quản lý ranh giới transaction. Khi runtime exception phù hợp quy tắc rollback thoát khỏi method được proxy quản lý, transaction manager hoàn tác transaction. Code nghiệp vụ tập trung vào cập nhật, kiểm tra điều kiện và phát sinh lỗi có ý nghĩa.

**Có bắt buộc thấy exception trên console không?** Không. `assertThrows` đón exception như một kết quả mong đợi, nên test vẫn **PASS**. Bằng chứng chính là thông điệp được assert và số dư đọc lại. Nếu muốn quan sát thêm bằng debugger, đặt breakpoint ở lệnh `throw` và ở `balanceOf` của test; không cần ghi log hoặc sửa dữ liệu bên ngoài.

## 7. Phản chứng: bỏ ranh giới transaction thì điều gì thay đổi?

Chỉ thực hiện trong **bản sao dự án lab và H2 test**:

1. Tạm comment annotation `@Transactional` trên `MoneyTransferService.transfer(...)`.
2. Chạy lại `mvn test` với nguyên trạng các assertion.
3. Quan sát những test rollback thất bại; sau đó khôi phục `@Transactional` và chạy lại để xác nhận PASS.

Với `JdbcTemplate` và H2 ở chế độ auto-commit mặc định khi **không có transaction bao ngoài**, mỗi `UPDATE` thành công được commit độc lập. Vì thế:

| Kịch bản khi bỏ `@Transactional` | Kết quả có thể quan sát với cấu hình lab |
| --- | --- |
| Lỗi `AFTER_DEBIT` | A = 800, B = 500: dữ liệu bị cập nhật dở dang. |
| Lỗi `AFTER_CREDIT` | A = 800, B = 700: hai lần cập nhật đã commit riêng dù lời gọi trả về exception. |
| Tài khoản đích không tồn tại | A = 800, B = 500: mất 200 ở nguồn. |
| Không có lỗi | A = 800, B = 700: nhìn bề ngoài vẫn đúng, nhưng không bảo đảm nguyên tử nếu lỗi ở giữa. |

Ở test lỗi giữa luồng, assertion kỳ vọng `1000` nhưng thực tế đọc thấy `800`, nên test thất bại. Đây là **phản chứng có kiểm soát** cho vai trò của transaction; không dùng thao tác “bỏ transaction để thử” trên hệ thống có dữ liệu thật.

Lưu ý: nếu có một transaction khác bên ngoài bao trùm lời gọi, hoặc cấu hình datasource/auto-commit khác, phép phản chứng sẽ không còn tương đương. Do đó lab cố ý dùng test không annotate `@Transactional` và kết nối H2 mặc định.

## 8. Những lỗi thường gặp khiến rollback không xảy ra như mong đợi

### 8.1. Lỗi bị bắt rồi nuốt trong service

Xem đoạn mã **minh họa sai**:

~~~java
@Transactional
public void doWork() {
    try {
        performFirstUpdate();
        performSecondUpdate();
    } catch (RuntimeException ex) {
        // Chỉ ghi log rồi kết thúc method bình thường.
    }
}
~~~

Đây không phải một class có thể biên dịch độc lập vì các phương thức cập nhật được lược bớt để minh họa. Nếu exception đã bị bắt và không còn dấu hiệu yêu cầu rollback, Spring có thể thấy method kết thúc bình thường và **commit thay đổi đã thực hiện**.

Cách sửa thường tốt hơn là **ném lại exception** sau khi bổ sung ngữ cảnh hoặc dùng một unchecked exception nghiệp vụ. Trường hợp buộc phải bắt lỗi nhưng vẫn rollback, cần chủ động đánh dấu transaction rollback-only qua API Spring thích hợp; lưu ý nếu đang tham gia transaction bên ngoài, caller có thể gặp `UnexpectedRollbackException` khi cố commit transaction đã bị đánh dấu rollback-only.

### 8.2. Dùng checked exception mà chưa cấu hình quy tắc rollback

Mặc định Spring rollback khi `RuntimeException` hoặc `Error` thoát khỏi transactional method. Một checked exception như `IOException` **không mặc định kích hoạt rollback**. Khi cần rollback cả checked exception, cấu hình phù hợp:

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public void operation() throws java.io.IOException {
    // Ví dụ cấu hình annotation; không phải chương trình độc lập.
}
~~~

Trong lab, ta chọn `IllegalStateException` có chủ ý để kiểm tra quy tắc rollback mặc định. Đừng suy diễn “cứ throw bất cứ Exception nào là rollback”.

### 8.3. Không gọi qua Spring proxy

Với proxy transaction mặc định:

- Tự khởi tạo service bằng `new` thường bỏ qua transaction interceptor.
- Gọi `this.transfer(...)` từ method khác **trong cùng bean** (self-invocation) thường không đi qua proxy.
- Dùng annotation chỉ trên private method và mong nó được AOP proxy bao transaction là cách hiểu sai.
- Test phải lấy bean từ Spring context, ví dụ `@Autowired` như ở trên.

Điều cần kiểm tra là **transaction thực sự được mở tại lời gọi nghiệp vụ**, không chỉ là annotation có mặt trong source.

### 8.4. Chỉ đặt transaction cho từng lệnh riêng

Nếu mỗi repository method có transaction riêng rồi commit khi method trả về, transaction đầu có thể commit trước khi method thứ hai thất bại. Bài toán yêu cầu nguyên tử **toàn bộ chuyển tiền**, nên transaction bao ngoài phải nằm tại service method đại diện cho cả nghiệp vụ.

### 8.5. Test tự mở transaction che khuất lỗi

Spring Test có thể rollback transaction của test sau khi test kết thúc nếu test được annotate `@Transactional`. Điều đó hữu ích khi viết những test khác, nhưng có thể khiến ví dụ này **không đo được việc service tự commit/rollback**.

Vì vậy bài này để `@SpringBootTest` **không kèm `@Transactional` trên test** và reset dữ liệu bằng `@BeforeEach`. Các assertions được thực hiện sau khi service proxy đã xử lý commit hoặc rollback.

### 8.6. Nhiều datasource hoặc hiệu ứng bên ngoài

Local transaction của JDBC không tự động hoàn tác email, HTTP, message đã gửi hay thay đổi ở một database hoàn toàn khác. Cần thiết kế phối hợp riêng (ví dụ transactional outbox, idempotency, saga tùy nghiệp vụ). Không gọi một test thành công trên H2 là bằng chứng rằng toàn bộ hệ thống phân tán an toàn.

## 9. Quan sát khác nhau giữa rollback, commit và lỗi sau commit

Một tình huống đặc biệt quan trọng trong ứng dụng thực tế: service đã commit nhưng kết nối HTTP tới client bị ngắt trước khi client nhận phản hồi.

| Tình huống | Trạng thái database | Điều client có thể biết |
| --- | --- | --- |
| Exception sau SQL thứ nhất, trước commit | Transaction rollback; A/B như cũ | Client thường nhận lỗi. |
| Exception sau SQL thứ hai, trước commit | Transaction rollback cả hai; A/B như cũ | Client thường nhận lỗi. |
| Method chạy hết và commit thành công | A/B thay đổi đúng nghiệp vụ | Client thường nhận thành công. |
| Commit thành công nhưng phản hồi bị mất | A/B **có thể đã thay đổi** | Client không chắc yêu cầu đã được xử lý. |

Tình huống cuối không được giải quyết bằng “thử lại vô điều kiện”: chuyển tiền có thể bị thực hiện lần thứ hai. Thiết kế production cần **request ID/idempotency key**, tra cứu trạng thái thao tác và quy tắc retry. Transaction bảo đảm tính nguyên tử **bên trong phạm vi quản lý**, không bảo đảm client luôn biết kết quả trong mọi lỗi mạng.

## 10. Luyện tập mở rộng trên chính project

Sau khi bốn test pass, có thể thử các trường hợp khác trong database thử nghiệm:

**Bài tập A — Số dư không đủ:** gọi `service.transfer(1L, 2L, 2000L, NONE)`. SQL trừ tiền có điều kiện `balance >= 2000` nên ảnh hưởng 0 hàng; exception xảy ra **trước khi có dữ liệu thay đổi**. Assert A/B giữ nguyên. Đây là test validation, nhưng **không thay thế** test rollback giữa luồng, vì không có cập nhật nào để hoàn tác.

**Bài tập B — Lỗi sau cả hai bước:** breakpoint trước `throw new IllegalStateException("FAIL_AFTER_CREDIT")`. Dùng debugger để quan sát hai số dư tạm thời bên trong transaction nếu muốn; sau khi tiếp tục, test khẳng định chúng quay về 1.000/500. Phần quan trọng là đọc **sau rollback** chứ không suy luận từ một log trung gian.

**Bài tập C — Có ngoại lệ nhưng không rollback:** tạo một bản sao service chỉ phục vụ thử nghiệm, bắt và nuốt `IllegalStateException` tại điểm lỗi. Quan sát tại sao annotation không còn đủ khi method trả về bình thường. Sau đó sửa bằng cách ném lại lỗi; không đưa bản sai vào ứng dụng thật.

**Bài tập D — Đổi quy tắc rollback:** thử checked exception trong một method lab riêng và cấu hình `rollbackFor`. Phân biệt **loại exception** với **việc transaction đã bắt đầu hay chưa**.

**Bài tập E — Hai người sửa cùng hàng:** nếu chuyển sang PostgreSQL hoặc MySQL, thử hai transaction đồng thời và quan sát lock wait/isolation. Đây là bài tập về concurrency, khác mục tiêu rollback do lỗi được tiêm có chủ đích.

## 11. Câu hỏi tự kiểm tra

1. **Tại thời điểm exception `AFTER_DEBIT`, A đã bằng 800 hay vẫn 1.000?** — Bên trong chính transaction, A đã thành 800; nhưng thay đổi chưa commit và sẽ bị rollback về 1.000.
2. **Chỉ `assertThrows` là đủ để chứng minh rollback chưa?** — Chưa. Phải đọc lại database sau khi exception đi qua transaction interceptor và khẳng định dữ liệu gốc được giữ nguyên.
3. **Nếu hai câu SQL đều chạy thành công rồi mới throw, có rollback được cả hai không?** — Có, nếu chúng nằm trong cùng transaction chưa commit và exception phù hợp quy tắc rollback thoát ra.
4. **Tại sao test không annotate `@Transactional`?** — Để không có transaction của test bao ngoài che mất lỗi ranh giới transaction của service.
5. **Nếu catch exception trong method mà không throw lại, Spring có chắc rollback?** — Không. Method có thể kết thúc bình thường và commit nếu transaction không bị đánh dấu rollback-only.
6. **Tại sao chạy với `@Autowired MoneyTransferService`?** — Để lời gọi đi qua Spring bean/proxy và transaction interceptor được kích hoạt.
7. **Tại sao `AFTER_DEBIT` là vị trí tiêm lỗi tốt hơn lỗi ngay trước câu SQL đầu tiên?** — Vì đã có một thay đổi thực tế cần hoàn tác; đó mới là bằng chứng rollback có giá trị.
8. **Mất phản hồi sau commit có thể giải quyết bằng rollback không?** — Không. Cần xác định kết quả đã xử lý và tránh retry trùng lặp.

## 12. Checklist kết quả học tập

- [ ] Chạy `mvn test` với **4 test thành công** và không có database ngoài.
- [ ] Biết A = 800 là **trạng thái trung gian bên trong transaction** trước rollback, không phải trạng thái đã commit.
- [ ] Khi tiêm lỗi sau UPDATE đầu, dữ liệu cuối **A = 1.000, B = 500**.
- [ ] Khi tiêm lỗi sau cả hai UPDATE, dữ liệu cuối **A = 1.000, B = 500**.
- [ ] Khi không tiêm lỗi, dữ liệu cuối **A = 800, B = 700**.
- [ ] Biết rollback cần cả **ranh giới transaction phù hợp** lẫn **exception/rollback rule được kích hoạt**.
- [ ] Phân biệt rollback trước commit với tình huống commit xong nhưng client chưa nhận phản hồi.

**Kết luận:** hãy đặt lỗi tại một vị trí **sau khi dữ liệu đã bị thay đổi nhưng trước commit**, sau đó đọc lại database từ ngoài lời gọi transaction. Điều quyết định không phải code có `@Transactional` hay test đã bắt được exception, mà là **mọi cập nhật chưa hoàn tất đã thực sự được hoàn tác**. Phép thử thành công và hai phép thử lỗi ở trên là bằng chứng trực tiếp cho hành vi đó.

### Tài liệu đối chiếu

- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Rolling back a declarative transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transactional test execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Boot — SQL databases and SQL initialization](https://docs.spring.io/spring-boot/reference/data/sql.html)