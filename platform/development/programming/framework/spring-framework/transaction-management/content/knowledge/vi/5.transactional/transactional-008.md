# Tạo annotation ghép cho chính sách dùng chung của `@Transactional` trong Spring

## Mục tiêu

Khi hoàn thành bài này, bạn có thể:

1. Giải thích **composed annotation (annotation ghép)** là gì và tại sao dùng nó để đặt một chính sách transaction nhất quán.
2. Khai báo annotation Java có **meta-annotation `@Transactional`** với `@Target`, `@Retention(RUNTIME)` và `@Documented`.
3. Tạo các annotation dùng chung cho nghiệp vụ **ghi** và **đọc**, gồm propagation, isolation, rollback rule, timeout và transaction manager khi thực sự cần.
4. Phân biệt **chính sách cố định** với một thuộc tính được mở có kiểm soát qua `@AliasFor`.
5. Dùng annotation ghép trên Spring service, kiểm tra metadata mà Spring nhận ra và chứng minh rollback bằng một ví dụ Java 17+.
6. Tránh các lỗi thường gặp: sai import `@Transactional`, method không qua proxy, self-invocation, nuốt exception, hiểu sai `readOnly`, hoặc nghĩ annotation tự cung cấp ACID.

Phạm vi của bài là **tạo annotation ghép cho chính sách giao dịch dùng chung**. Cơ chế database/ACID, propagation và isolation được nhắc đến ở những điểm cần thiết để hiểu chính sách.

## 1. Bài toán: cùng một transaction policy được lặp lại ở nhiều nơi

Giả sử nhiều service cùng phải tuân theo quy tắc ghi dữ liệu: tham gia transaction hiện có hoặc mở mới (`REQUIRED`), dùng isolation `READ_COMMITTED`, rollback cả khi có checked exception, và giới hạn timeout của transaction mới.

Khi không có quy ước chung, mã dễ lặp lại:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = Exception.class,
    timeout = 15
)
public void transfer(...) { ... }
```

Hãy hình dung cấu hình đó xuất hiện ở 30 phương thức. Một người mới có thể bỏ quên `rollbackFor`, gõ nhầm `REQUIRES_NEW`, hoặc thay timeout mà không biết chính sách. Dù dùng IDE để sao chép, các khai báo vẫn có thể lệch nhau theo thời gian.

**Composed annotation** giúp đưa policy vào một chỗ:

```java
@WriteTx
public void transfer(...) { ... }
```

Lúc đó tên `@WriteTx` là một **từ vựng nghiệp vụ**: người đọc hiểu phương thức ghi theo chính sách đã được định nghĩa. Chỉ cần chỉnh một định nghĩa khi chính sách chung đổi, đồng thời có thể kiểm thử chính sách đó ở mức metadata và giao dịch thật.

Nó **không** tạo ra một transaction manager mới, không thay thế database constraint và không bảo đảm mọi thao tác ngoài DB được rollback. Đây là cách tái sử dụng **transaction metadata**, được Spring transaction infrastructure đọc khi một bean được gọi qua cơ chế phù hợp.

## 2. Cơ chế: annotation nằm trên một annotation khác

Trong Java, một annotation có thể được gắn lên khai báo của một annotation khác. Annotation được gắn phía trên gọi là **meta-annotation**.

```text
@Transactional(...)
       |
       v
public @interface WriteTx { ... }
       |
       v
@WriteTx
public void transfer(...) { ... }
       |
       v
Spring tìm merged transaction metadata
       |
       v
TransactionInterceptor + TransactionManager
```

Có hai tầng trách nhiệm:

- **Java:** lưu annotation theo retention, giới hạn nơi annotation được sử dụng, kiểm tra cú pháp/type.
- **Spring:** tìm `@Transactional` trực tiếp hoặc qua một/multiple meta-annotation, tổng hợp thuộc tính rồi áp dụng transactional advice.

Dấu `@WriteTx` trên method không làm bytecode của phương thức tự sinh `begin/commit`. Trong proxy mode thông dụng, Spring tạo **AOP proxy** cho bean, và lời gọi đi qua proxy mới được `TransactionInterceptor` bao quanh bằng begin/commit/rollback. Transaction manager thật (ví dụ JDBC/JPA/R2DBC) điều phối tài nguyên tham gia giao dịch.

### Các annotation Java cần có

| Annotation | Mục đích | Quyết định trong bài |
| --- | --- | --- |
| `@Target` | Nơi được phép gắn annotation | `METHOD`, `TYPE` cho method hoặc class service |
| `@Retention` | Thời gian tồn tại metadata | `RUNTIME` để Spring tìm được khi chạy |
| `@Documented` | Hiển thị trong Javadoc | Nên có để công khai chính sách |
| `@Transactional` | Định nghĩa semantic giao dịch của Spring | Là **meta-annotation quan trọng nhất** |
| `@AliasFor` | Cho một attribute của annotation mới override attribute của meta-annotation | Chỉ dùng khi thật sự muốn cho phép điều chỉnh |

`@Inherited` là tùy chọn nếu muốn annotation áp dụng với quan hệ **kế thừa class** theo quy tắc Java/Spring; nó không khiến method annotation tự “di truyền” tới mọi method được override. Nên ưu tiên đặt policy trên các concrete service class/method rõ ràng.

**Import đúng:** `org.springframework.transaction.annotation.Transactional`. `jakarta.transaction.Transactional` là một annotation khác, có các semantics/attribute khác; đừng dùng nó để sao chép nguyên ví dụ `propagation`, `isolation`, `rollbackFor` của Spring.

## 3. Tạo policy cố định cho phương thức đọc: `@ReadOnlyTx`

Một chính sách đọc có thể được thiết kế gọn, rõ nghĩa và không cung cấp tham số cần tùy biến.

**File `src/main/java/example/txpolicy/ReadOnlyTx.java`:**

```java
package example.txpolicy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true
)
public @interface ReadOnlyTx {
}
```

Giải thích:

- `@Transactional(...)` được gắn **trên khai báo `@interface`**. Đây là điểm khiến `ReadOnlyTx` trở thành composed annotation của Spring transaction.
- `REQUIRED` là mặc định của Spring: khi không có transaction thì bắt đầu một transaction; khi đã có một transaction phù hợp, join nó.
- `readOnly = true` là **hint/thông tin cho manager và database**, đôi khi được tối ưu hóa hay cưỡng chế tùy driver/DB. Không nên coi nó là một hàng rào bảo mật luôn cấm ghi.
- Khi một method `REQUIRED` tham gia transaction có sẵn, `readOnly` trên method con không mặc nhiên thay đổi tính chất của transaction ngoài đã bắt đầu.
- Không có attribute trên `@ReadOnlyTx`, nghĩa là mỗi chỗ sử dụng đều theo cùng một metadata. Nếu nhiều trường hợp đọc có nhu cầu khác nhau, hãy xét có cần nhiều policy tên rõ nghĩa hay không.

Ví dụ:

```java
@Service
public class CustomerQueryService {

    @ReadOnlyTx
    public Customer findCustomer(long id) {
        // Truy cập database qua repository/JdbcTemplate phù hợp.
        // Đoạn này minh họa vị trí annotation, chưa là class chạy độc lập.
        return customerRepository.findById(id).orElseThrow();
    }
}
```

Snippet chỉ minh họa cách áp dụng; phần ví dụ chạy hoàn chỉnh ở mục 5 sử dụng `JdbcTemplate` với H2.

## 4. Tạo policy ghi với rollback checked exception: `@WriteTx`

Nhiều hệ thống có checked exception thể hiện lỗi nghiệp vụ. Nếu nghiệp vụ đòi **không commit bất kỳ phần ghi nào khi checked exception thoát ra ngoài**, ta có thể dùng policy:

**File `src/main/java/example/txpolicy/WriteTx.java`:**

```java
package example.txpolicy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = Exception.class
)
public @interface WriteTx {

    @AliasFor(annotation = Transactional.class, attribute = "timeout")
    int timeout() default 15;
}
```

Tại sao có hai kiểu cấu hình trong một annotation?

- **Cố định:** `REQUIRED`, `READ_COMMITTED`, `rollbackFor = Exception.class` luôn là policy mặc định cho mọi method có `@WriteTx`.
- **Mở có kiểm soát:** chỉ `timeout` được lộ ra. `@WriteTx` có timeout mặc định 15 giây, còn `@WriteTx(timeout = 12)` cho phép method dùng 12 giây.
- `@AliasFor(annotation = Transactional.class, attribute = "timeout")` khai báo rằng attribute của `@WriteTx` **override** thuộc tính `timeout` của meta-annotation `@Transactional` khi Spring tổng hợp metadata. Hai attribute đều là kiểu `int`.
- Nếu không cần cho phép override timeout, đơn giản hơn là đặt `timeout = 15` trực tiếp trong `@Transactional(...)` và để thân annotation trống.

Quy tắc alias không đến từ Java reflection thuần. Spring sử dụng cơ chế **merged annotations** để tìm meta-annotation và tính giá trị override. Một lệnh `method.getAnnotation(Transactional.class)` có thể trả `null` khi method chỉ gắn `@WriteTx`; điều đó không đồng nghĩa Spring không thấy transaction metadata.

**Không dùng `@AliasFor` như một cách “tự động chuyển mọi thuộc tính có tên giống nhau”.** Với attribute cần override, khai báo chính xác meta-annotation và `attribute` mục tiêu, bảo đảm kiểu dữ liệu tương ứng, rồi kiểm thử bằng API merged annotation của Spring.

## 5. Ví dụ chạy được: Spring Boot + JDBC/H2

Ta xây dựng một ứng dụng nhỏ chuyển điểm giữa hai ví. Nghiệp vụ kiểm chứng riêng một điểm đặc biệt của policy: **checked exception** xuất hiện sau thao tác trừ tiền sẽ khiến thay đổi trừ tiền **rollback**, nhờ `rollbackFor = Exception.class` trong `@WriteTx`.

Ví dụ dùng **Java 17+, Spring Boot 3.3.5 và Gradle**. Nếu dùng Java 21 theo toolchain dự án của bạn, đổi `JavaLanguageVersion.of(17)` thành `of(21)` hoặc giữ 17 nếu runtime hỗ trợ.

### 5.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo project Gradle Spring Boot với wrapper bằng Spring Initializr hoặc Gradle đã cài, rồi đặt các file theo đúng package `example.txpolicy`. Không cần web server vì ví dụ dùng `ApplicationRunner`.

### 5.2. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:policy_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Spring Boot tự cấu hình `DataSource`, `JdbcTemplate`, JDBC transaction manager khi dependencies phù hợp. `mode: always` chạy `schema.sql` khi khởi động. H2 in-memory là môi trường minh họa; khi triển khai hệ thống thực, cân nhắc schema migration, cách quản lý connection, durable storage và test trên đúng DBMS sản xuất.

### 5.3. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

Hai ví có tổng điểm 1.500. Với chuyển 200, số dư đúng phải là 800 và 700. Khi lỗi ở bước cộng điểm, số dư phải giữ nguyên như trước giao dịch đó.

### 5.4. `src/main/java/example/txpolicy/MissingWalletException.java`

```java
package example.txpolicy;

public class MissingWalletException extends Exception {
    public MissingWalletException(String message) {
        super(message);
    }
}
```

Đây là **checked exception** vì lớp trực tiếp mở rộng `Exception` mà không mở rộng `RuntimeException`. Theo mặc định thường gặp của Spring Framework 6.1, checked exception không tự động buộc rollback; `@WriteTx` đã cung cấp rule rõ ràng. Hành vi default có thể được cấu hình khác trong những phiên bản Spring mới, nhưng rule ghi cụ thể vẫn thể hiện chính sách nghiệp vụ.

### 5.5. `src/main/java/example/txpolicy/WalletService.java`

```java
package example.txpolicy;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class WalletService {
    private final JdbcTemplate jdbc;

    public WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @WriteTx(timeout = 12)
    public void transfer(long sourceId, long targetId, long amount)
            throws MissingWalletException {
        if (amount <= 0 || sourceId == targetId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE wallets SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );

        if (debited != 1) {
            throw new MissingWalletException(
                "Source missing or insufficient funds"
            );
        }

        int credited = jdbc.update(
            "UPDATE wallets SET balance = balance + ? WHERE id = ?",
            amount, targetId
        );

        if (credited != 1) {
            throw new MissingWalletException("Destination missing");
        }
    }

    @ReadOnlyTx
    public String balances() {
        List<String> pairs = jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        );
        return String.join(", ", pairs);
    }
}
```

Phân tích transaction:

1. Caller gọi `transfer()` **qua Spring bean proxy**. Spring tìm merged metadata từ `@WriteTx(timeout=12)`.
2. Interceptor dùng manager JDBC bắt đầu transaction mới trong trường hợp caller chưa có transaction; policy gồm `REQUIRED`, `READ_COMMITTED`, timeout 12 giây, rollback khi gặp `Exception`.
3. `UPDATE` nguồn trừ điểm và có điều kiện `balance >= ?` trong cùng statement. Nếu không đủ điểm, affected rows = 0 và service ném checked exception.
4. `UPDATE` đích chỉ chạy sau khi trừ nguồn thành công. Nếu id đích không tồn tại, affected rows = 0; checked exception thoát khỏi phương thức và **Spring rollback** cả thao tác nguồn.
5. Nếu cả hai cập nhật thành công, method kết thúc và interceptor commit.
6. `balances()` dùng policy đọc riêng. Bản thân `readOnly=true` chỉ là hint; SQL đọc vẫn phải phù hợp isolation và rule nghiệp vụ.

Đặt transaction trên toàn method `transfer()` là quan trọng: nếu chỉ đặt trên các helper cập nhật riêng biệt, có thể tạo hai giao dịch độc lập và phá atomicity của chuyển điểm.

### 5.6. `src/main/java/example/txpolicy/TxPolicyApplication.java`

```java
package example.txpolicy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxPolicyApplication.class, args);
    }

    @Bean
    ApplicationRunner example(WalletService wallets) {
        return args -> {
            wallets.transfer(1L, 2L, 200L);
            System.out.println("Sau commit: " + wallets.balances());

            try {
                wallets.transfer(1L, 999L, 50L);
            } catch (MissingWalletException ex) {
                System.out.println("Loi du kien: " + ex.getMessage());
            }

            System.out.println("Sau rollback: " + wallets.balances());
        };
    }
}
```

`@EnableTransactionManagement` thể hiện rõ cấu hình declarative transaction; nhiều ứng dụng Spring Boot có auto-configuration đủ điều kiện cũng bật transaction management. Method được gọi từ `ApplicationRunner` thông qua bean Spring inject vào, nên tránh được lỗi self-invocation.

Chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các dòng ứng dụng in ra, bỏ qua log khởi động, có nội dung dự kiến:

```text
Sau commit: 1=800, 2=700
Loi du kien: Destination missing
Sau rollback: 1=800, 2=700
```

Giải thích dòng cuối: sau giao dịch đầu, ví 1 đang có 800 và ví 2 có 700. Giao dịch thứ hai tạm trừ thêm 50 ở ví 1, nhưng vì ví 999 không tồn tại nên ném **checked exception**. Policy `rollbackFor=Exception.class` khiến DB rollback phần trừ tạm thời; số dư vẫn 800 và 700.

Bốn file Java của ví dụ chạy gồm `ReadOnlyTx.java`, `WriteTx.java`, `MissingWalletException.java`, `WalletService.java`, cộng `TxPolicyApplication.java`. Các class phải nằm đúng package `example.txpolicy`; từng code block Java tương ứng một file, không ghép tất cả vào một file.

## 6. Kiểm tra Spring thật sự nhận ra composed annotation

Nên kiểm tra ở **hai lớp**:

- **Metadata test:** Spring tổng hợp thành `@Transactional` với đúng propagation, isolation, rollback rule và timeout.
- **Behavior test:** method được proxy xử lý, transaction thật rollback khi checked exception phát ra sau một câu SQL đã thành công.

### 6.1. Metadata: đọc bằng API merged annotation

Java reflection thuần không tự biến `@WriteTx` thành một `@Transactional` trực tiếp. Spring có `AnnotatedElementUtils.findMergedAnnotation(...)` để lấy merged view.

Đoạn sau đặt trong một lớp test JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

class TxMetadataTest {

    @Test
    void mergedWritePolicyHasExpectedValues() throws Exception {
        Method method = WalletService.class.getMethod(
            "transfer", long.class, long.class, long.class
        );

        Transactional tx = AnnotatedElementUtils.findMergedAnnotation(
            method, Transactional.class
        );

        assertNotNull(tx);
        assertEquals(Propagation.REQUIRED, tx.propagation());
        assertEquals(Isolation.READ_COMMITTED, tx.isolation());
        assertEquals(12, tx.timeout());
        assertTrue(Arrays.asList(tx.rollbackFor()).contains(Exception.class));
    }
}
```

Chạy test thuần metadata không cần DB. `@WriteTx` định nghĩa timeout mặc định 15, nhưng `transfer` chọn `@WriteTx(timeout=12)`, do đó merged `@Transactional.timeout()` phải là 12. Đây là cách phát hiện sớm lỗi alias, sai retention hoặc sai meta-annotation.

Đoạn test ở trên là file `src/test/java/example/txpolicy/TxMetadataTest.java`: thêm `package example.txpolicy;` ở dòng đầu, trước imports, để chạy trong đúng package. Nó dùng JUnit 5 và `spring-core` có sẵn trong starter.

### 6.2. Behavior: checked exception phải rollback dữ liệu đã cập nhật

**File `src/test/java/example/txpolicy/WalletServiceTest.java`:**

```java
package example.txpolicy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class WalletServiceTest {
    @Autowired WalletService wallets;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    @Test
    void checkedExceptionRollsBackDebit() {
        assertThrows(MissingWalletException.class,
            () -> wallets.transfer(1L, 999L, 200L));

        Long actual = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 1",
            Long.class
        );
        assertEquals(1000L, actual.longValue());
    }

    @Test
    void successCommitsBothChanges() throws Exception {
        wallets.transfer(1L, 2L, 200L);

        assertEquals("1=800, 2=700", wallets.balances());
    }
}
```

Chạy:

```bash
./gradlew test
```

Các assertion sau khi method kết thúc quan sát trạng thái DB thực. `@BeforeEach` đưa fixture trở lại số dư khởi đầu vì trong ví dụ khởi động, `ApplicationRunner` cũng chạy và đã thực hiện một giao dịch. Test method không gắn `@Transactional`, để tránh test framework tự rollback test và làm sai ý nghĩa kiểm tra commit của service.

**Đừng kiểm tra chỉ bằng việc tồn tại `@WriteTx` trên method.** Test metadata không chứng minh proxy đã bao quanh lời gọi, còn test behavior giúp phát hiện các lỗi wiring hoặc không có transaction manager.

## 7. Mở attribute bằng `@AliasFor`: khi nào và khi nào không

Có hai hướng thiết kế.

### Chính sách cố định

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = Exception.class
)
public @interface IndependentAuditTx {
}
```

Hướng này phù hợp khi **mọi nơi dùng annotation phải có đúng semantics đó**. Nhưng lưu ý `REQUIRES_NEW` tách transaction độc lập: audit có thể commit ngay cả khi transaction nghiệp vụ bên ngoài rollback, cần chấp nhận hệ quả dữ liệu. Không đặt `REQUIRES_NEW` chỉ để “chắc chắn hơn”.

### Chính sách có tham số được phép override

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Transactional(rollbackFor = Exception.class)
public @interface ManagedWriteTx {

    @AliasFor(annotation = Transactional.class, attribute = "timeout")
    int timeout() default 10;
}
```

Cách dùng:

```java
@ManagedWriteTx
public void saveFast() { ... }

@ManagedWriteTx(timeout = 30)
public void processLargeBatch() { ... }
```

`@AliasFor` thể hiện chủ ý: mọi phương thức chia sẻ rollback rule, nhưng timeout được phép đổi. Đây là **mã minh họa thiết kế**, không thuộc demo đầy đủ mục 5. Nếu muốn class chạy được, mỗi annotation và service phải đặt trong file/class hợp lệ và thay `...` bằng thân method thực.

Quy tắc thiết kế: chỉ lộ những thuộc tính là **điểm biến thiên có chủ đích**. Nếu mọi method có thể đổi tùy ý `propagation`, `readOnly`, `isolation`, `rollbackFor`, `timeout`, một annotation ghép trở nên chỉ là tên khác cho `@Transactional` và không còn bảo đảm policy chung.

## 8. Dùng tên transaction manager trong annotation ghép

Trong ứng dụng chỉ có một local JDBC transaction manager, thường không cần chỉ định manager trong meta-annotation. Nhưng nếu có **nhiều** transaction managers, policy có thể gắn rõ một manager:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(
    transactionManager = "ordersTransactionManager",
    rollbackFor = Exception.class
)
public @interface OrdersWriteTx {
}
```

`ordersTransactionManager` ở đây là **tên bean minh họa**. Annotation chỉ hoạt động nếu ứng dụng thật có transaction manager bean/qualifier tương ứng. Đừng sao chép tên này vào demo H2 ở mục 5 khi chưa tạo manager đó.

Spring documentation cũng minh họa custom composed annotation cho các manager khác nhau như `order` và `account`. Đây là cách tránh chọn nhầm datasource/transaction manager, **không phải** cách tự động tạo giao dịch phân tán qua hai database.

Nếu service dùng hai manager riêng, một `@OrdersWriteTx` thường chỉ bao transaction do manager orders điều phối. Muốn atomicity trên nhiều tài nguyên, phải thiết kế cơ chế phối hợp phù hợp hoặc dùng outbox/saga tùy yêu cầu hệ thống.

## 9. Phạm vi áp dụng, ưu tiên metadata và AOP proxy

### 9.1. Ở class và method

Có thể gắn annotation ghép tại class khi **mọi method nghiệp vụ** trong service có cùng policy:

```java
@ReadOnlyTx
@Service
public class ProductQueryService {
    public Product findOne(long id) { ... }
    public List<Product> findAll() { ... }
}
```

Khi một method cần policy khác, nên gắn rõ policy cụ thể ở method hoặc tách thành service riêng. Transaction attribute ở method cụ thể có thể override default ở class. Ví dụ:

```java
@ReadOnlyTx
@Service
public class ProductService {

    public Product findOne(long id) { ... }

    @WriteTx
    public void updatePrice(long id, long amount) { ... }
}
```

Hai đoạn trên chỉ là phác thảo service, không phải lớp Java có đầy đủ imports/repository. Tránh gắn **hai policy mâu thuẫn cùng trên một method** (`@ReadOnlyTx` và `@WriteTx`) rồi trông chờ Spring “kết hợp” chúng theo ý mình; hãy để mỗi method có một nguồn policy rõ ràng.

### 9.2. Proxy và self-invocation

`@WriteTx` hoạt động như `@Transactional` về mặt AOP: trong proxy mode, **lời gọi qua Spring proxy** mới được interceptor xử lý.

```java
@Service
public class WrongService {

    public void outer() {
        inner(); // self-invocation, thường bỏ qua transaction advice
    }

    @WriteTx
    public void inner() {
        // ...
    }
}
```

Nếu `outer()` gọi `inner()` trực tiếp trong cùng instance thì không đi qua proxy; nếu chưa có transaction bên ngoài, `@WriteTx` trên `inner()` không tự tạo transaction. Nên tách `inner()` sang một Spring bean chuyên trách và gọi bean đó, hoặc thiết kế ranh giới transaction ngay tại method public được caller bên ngoài gọi.

`@Target(METHOD)` trên method private, `@Target(TYPE)` trên class do `new` tạo thủ công, hay dùng annotation trên class không thuộc Spring context cũng không tạo AOP transaction. Với interface annotations, cơ chế proxy/weaving và method visibility có khác biệt; ưu tiên gắn policy lên **concrete service class/method** có thể quan sát/test được.

### 9.3. Propagation: policy chỉ được áp dụng trong ranh giới thực tế

Khi `@WriteTx` chọn `REQUIRED` và một transaction đã tồn tại, method **tham gia** transaction đó. Isolation và timeout được khai báo cho transaction mới không có nghĩa tự động nâng isolation hoặc thay timeout của transaction đã mở.

Nếu caller đang chạy một transaction read-only, rồi gọi một method `@WriteTx` có `REQUIRED`, method có thể vẫn tham gia transaction hiện có. Đừng nghĩ `@WriteTx` tự tạo “vùng ghi” độc lập với mọi thuộc tính mới; kiểm tra policy ở cấp entrypoint và cân nhắc kiểm soát validation của existing transaction khi cần.

## 10. Những lỗi hay gặp

| Lỗi | Tại sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Quên meta `@Transactional` | `@WriteTx` chỉ còn là annotation Java bình thường | Gắn đúng `org.springframework.transaction.annotation.Transactional` |
| Quên `RUNTIME` retention | Spring không còn đủ metadata lúc chạy | Luôn khai báo `@Retention(RetentionPolicy.RUNTIME)` |
| Sai `@Target` | Không gắn được tại nơi mong muốn | Chọn `METHOD`, `TYPE` theo phạm vi thực sự dùng |
| Import `jakarta.transaction.Transactional` rồi dùng thuộc tính Spring | API khác, có thể không biên dịch hoặc policy sai | Dùng Spring annotation đúng |
| Alias trùng tên nhưng không rõ override | Khó xác minh metadata hiệu lực | Dùng `@AliasFor` và test merged attributes |
| Gọi từ `this.method()` | Spring proxy không thấy lời gọi nội bộ | Đặt ranh giới ở entrypoint hoặc tách bean |
| Bắt checked exception rồi nuốt | Interceptor thấy method return bình thường và có thể commit | Ném lại, dùng rollback-only khi phù hợp |
| Nhầm `readOnly=true` là cấm ghi tuyệt đối | Một số DB/driver không cưỡng chế | Chỉ coi là hint, vẫn bảo vệ dữ liệu/role/constraint |
| Dùng một policy cho mọi use case | Transaction dài, isolation quá mạnh hoặc propagation sai | Thiết kế số lượng policy nhỏ theo nhu cầu thật |
| Gắn nhiều policy mâu thuẫn cùng vị trí | Cách chọn merged metadata có thể không như kỳ vọng | Chỉ một chính sách rõ ràng tại từng điểm |
| Chỉ test Java reflection | Không biết Spring proxy/manager có áp dụng | Test `findMergedAnnotation` **và** DB rollback |
| Gắn manager không tồn tại | Lỗi chọn `TransactionManager` khi chạy | Xác nhận bean name/qualifier trong context |

**Đặc biệt về rollback:** `rollbackFor = Exception.class` bao gồm checked exceptions và phần lớn runtime exceptions. Nhưng Spring có thể có `noRollbackFor`, default rollback rule hoặc policy khác; thiết kế và test đúng ngoại lệ nghiệp vụ, tránh tự nghĩ mọi exception phải rollback trong mọi ngữ cảnh. Dạng `rollbackForClassName` dùng so khớp theo pattern, có thể match ngoài ý muốn; ưu tiên class literal như `rollbackFor = MyBusinessException.class` khi biết type cụ thể.

## 11. Khi nào nên dùng annotation ghép?

Annotation ghép có ích khi:

- Có **từ hai nhóm method trở lên** cần một bộ transaction settings ổn định và rõ nghĩa.
- Chính sách có ý nghĩa nghiệp vụ rõ như `@ReadOnlyTx`, `@WriteTx`, `@OrdersWriteTx`.
- Nhiều team/service cần tránh thay đổi propagation/rollback/isolation thiếu kiểm soát.
- Hệ thống có nhiều transaction managers và cần một tên policy để chọn đúng manager.
- Cần các quy tắc có thể test tập trung khi nâng cấp Spring hoặc thay transaction manager.

Không nên tạo hàng chục annotation chỉ để tiết kiệm vài ký tự. Nếu một phương thức đơn lẻ có semantics đặc thù và không có policy dùng chung, dùng `@Transactional(...)` trực tiếp có thể rõ ràng hơn. Một annotation tên đẹp nhưng che dấu `REQUIRES_NEW`, timeout quá ngắn hoặc rollback rule quá rộng sẽ khiến người đọc khó dự đoán hệ quả.

**Quy ước đặt tên:** diễn đạt **nghiệp vụ/chính sách**, ví dụ `@ReportReadTx` hoặc `@PaymentWriteTx`. Trong phần mô tả/Javadoc của policy nên ghi rõ phạm vi, transaction manager được chọn, propagation, rollback conditions, và ai chịu trách nhiệm thay đổi khi yêu cầu nghiệp vụ đổi.

## 12. Checklist triển khai và kiểm thử

1. Nhóm các method có yêu cầu transaction giống nhau; mô tả policy bằng văn bản trước khi viết annotation.
2. Khai báo `@Target` và `@Retention(RUNTIME)`, gắn Spring `@Transactional` làm meta-annotation; thêm `@Documented`.
3. Cố định những thuộc tính quan trọng; chỉ mở attribute cần tùy biến, khai báo `@AliasFor` đúng target và type.
4. Gắn annotation lên concrete Spring service class/method; xác minh transaction management đã được bật.
5. Bảo đảm caller gọi qua Spring proxy, tránh self-invocation hoặc tự `new` service.
6. Nếu có nhiều transaction managers, xác nhận bean/qualifier nào phải được chọn.
7. Test `AnnotatedElementUtils.findMergedAnnotation(...)` để chắc chắn policy đã được Spring tổng hợp đúng.
8. Test tích hợp với DB: commit đường thành công, rollback sau lỗi ở bước giữa, checked exception, concurrency/invariant quan trọng.
9. Xem xét lại behavior khi method tham gia transaction hiện hữu; timeout, isolation và `readOnly` không tự thay mọi thuộc tính của transaction ngoài.
10. Ghi lại chính sách và version Spring dùng để kiểm soát việc thay đổi semantics khi nâng cấp framework.

## Tài liệu tham khảo

- Spring Framework — Using `@Transactional`, mục **Custom Composed Annotations**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation và AOP proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rollback Rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — `@AliasFor` Javadoc (6.1.x): https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Framework — `@Transactional` Javadoc (6.2.x): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html