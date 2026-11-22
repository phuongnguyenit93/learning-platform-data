# Ngoại lệ phải đi qua ranh giới giao dịch để interceptor quan sát

## 1. Vì sao ném lỗi chưa chắc khiến transaction rollback?

Trong Spring Framework, `@Transactional` thường hoạt động theo cơ chế **AOP proxy**. Caller gọi một Spring bean qua proxy; `TransactionInterceptor` bắt đầu hoặc tham gia transaction, thực thi phương thức đích rồi quan sát **kết quả đi ra từ lời gọi**. Khi phương thức hoàn tất bình thường, interceptor thường yêu cầu commit. Khi một lỗi phù hợp với **rollback rules** thoát khỏi phương thức, interceptor yêu cầu rollback hoặc đánh dấu transaction rollback-only.

Vì thế, hai đoạn code gần giống nhau có thể tạo kết quả khác nhau:

```java
@Transactional
public void silentlyContinue() {
    debit(100);
    try {
        creditMissingAccount(100);
    } catch (IllegalStateException ex) {
        log.warn("Credit failed", ex);
    }
    // Method trả về bình thường: interceptor không thấy lỗi này thoát ra.
}
```

```java
@Transactional
public void failAndRollback() {
    debit(100);
    creditMissingAccount(100);
    // Nếu creditMissingAccount ném RuntimeException, lỗi đi ra proxy.
}
```

Cả hai chỉ là snippet minh họa; ứng dụng đầy đủ ở mục 5 sẽ định nghĩa các method thực. Với giả định hai câu SQL đều tham gia cùng transaction và lỗi do **logic ứng dụng** ném sau khi kiểm tra affected rows, phiên bản đầu có thể **commit khoản đã trừ**; phiên bản sau có thể **rollback toàn bộ**.

Đây là nội dung trọng tâm:

> Một ngoại lệ được tạo ra **bên trong** method không tự động trở thành tín hiệu rollback cho `TransactionInterceptor`. Interceptor thông thường chỉ áp dụng rollback rules cho ngoại lệ đi ra **qua ranh giới transactional advice** (hoặc nhận tín hiệu đặc biệt được framework hỗ trợ). Nếu exception đã bị bắt và method trả về bình thường, advice không thể suy ra rằng nghiệp vụ đã thất bại.

Tuy nhiên, “lỗi thoát ra” là **điều kiện quan trọng, chưa phải điều kiện đủ**: kiểu exception còn phải khớp rollback rules; và transaction có thể đã bị đánh dấu rollback-only hoặc DB đã từ chối transaction theo cơ chế riêng. Bài này lần lượt phân biệt các trường hợp.

## 2. Nhìn đúng vị trí của ranh giới giao dịch

Giả sử `OrderController` gọi `PaymentService.pay()` trên một bean Spring:

```text
Controller
  |
  | service.pay()
  v
Spring proxy / TransactionInterceptor
  |
  | begin hoặc join transaction
  v
PaymentService.pay()  [thân method @Transactional]
  |
  +-- debit() thành công
  +-- credit() thất bại -> throw IllegalStateException
  |
  +-- Lựa chọn A: catch ngay tại đây và return
  |       |
  |       v
  |   Interceptor nhận "return bình thường" -> commit nếu có thể
  |
  +-- Lựa chọn B: exception tiếp tục đi ra method
          |
          v
      Interceptor nhận exception -> xem rollback rules
          |
          +-- Rule yêu cầu rollback -> rollback/rollback-only
          +-- Rule không yêu cầu rollback -> có thể commit
          |
          v
      Ngoại lệ được ném tiếp ra Controller
```

**Vị trí catch quan trọng hơn việc có catch hay không.** Nếu Controller bắt exception **sau khi lời gọi `service.pay()` đã đi qua Spring proxy**, interceptor đã có cơ hội xử lý rollback trước khi Controller biến lỗi thành HTTP response phù hợp. Ngược lại, bắt và nuốt exception **trong thân phương thức transactional** có thể khiến interceptor chỉ nhìn thấy completion.

```java
// Tại tầng caller (chỉ là snippet minh họa):
try {
    paymentService.pay(request);
    return successResponse();
} catch (InsufficientBalanceException ex) {
    return rejectedResponse(ex.getMessage());
}
```

Nếu `paymentService` là bean proxied, lỗi đã đi qua interceptor trước khi tới `catch` của caller. Caller hoàn toàn có thể dịch exception thành phản hồi API; **không cần để lỗi tiếp tục đi tới người dùng cuối** để transaction rollback. Điều cần là lỗi được truyền đến đúng transactional boundary trước khi xử lý ở tầng cao hơn.

### “Ranh giới” không nhất thiết là kết thúc HTTP request

Một request có thể gọi nhiều service. Transaction không tự bao trùm toàn bộ request nếu annotation chỉ đặt trên một method. Nếu service đã commit thành công rồi controller làm việc khác và ném lỗi, exception đó xảy ra **sau transaction**, không làm đảo ngược commit đã hoàn tất. Cần xác định đâu là **đơn vị nghiệp vụ cần commit/rollback cùng nhau**, đặt transaction boundary bao trùm chính xác phần việc đó và tránh cho tác vụ thất bại quan trọng nằm ngoài ranh giới.

## 3. Quy tắc mặc định: interceptor nhìn loại exception nào?

Theo cấu hình mặc định thông dụng của `@Transactional` trong Spring Framework 6.1/6.2:

| Tình huống đi ra từ method | Kết quả mặc định khi transaction mới thuộc method |
| --- | --- |
| Method trả về bình thường | Yêu cầu commit, trừ khi transaction đã rollback-only hoặc commit thất bại |
| `RuntimeException` hoặc subclass thoát ra | Yêu cầu rollback |
| `Error` thoát ra | Yêu cầu rollback theo default rules |
| Checked exception (`IOException`, `Exception` không phải `RuntimeException`) thoát ra | **Mặc định không yêu cầu rollback**; transaction có thể commit rồi exception vẫn được ném tiếp |
| Exception được bắt và nuốt bên trong method | Interceptor thường chỉ thấy return bình thường; có thể commit |
| Transaction đã bị đánh dấu rollback-only | Không commit dù method trả về bình thường; đường báo lỗi phụ thuộc transaction scope |
| Exception xảy ra ngoài boundary sau commit | Không thể tự động rollback một transaction đã commit |

Ví dụ checked exception thường gây bất ngờ:

```java
@Transactional
public void saveAndCheck() throws java.io.IOException {
    writeToDatabase();                   // UPDATE đã thành công
    throw new java.io.IOException("External validation unavailable");
}
```

Method có ném lỗi đi qua interceptor nhưng **`IOException` không thuộc rollback rules mặc định**. Trên database không còn lỗi nào khác và transaction đủ điều kiện commit, Spring vẫn có thể commit UPDATE rồi ném `IOException` lên caller.

Nếu nghiệp vụ bắt buộc rollback trong trường hợp này, khai báo rõ:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void saveAndCheck() throws java.io.IOException {
    writeToDatabase();
    throw new java.io.IOException("External validation unavailable");
}
```

Có thể dùng `rollbackFor = Exception.class` khi **mọi checked exception** đều cần rollback, nhưng quy tắc càng rộng thì càng phải hiểu chính xác. `@Transactional(noRollbackFor = SomeBusinessException.class)` có thể chủ ý cho phép commit dù `SomeBusinessException` thoát ra. Khi nhiều rule trùng khớp, Spring ưu tiên rule phù hợp mạnh nhất.

**Lưu ý phiên bản:** Trong Spring Framework 6.2 có tùy chọn cấu hình mặc định rollback cho **mọi exception** ở cấp `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`. Vì vậy, đừng lấy bảng mặc định trên để suy diễn cho một ứng dụng đã thay cấu hình. Demo của bài dùng Spring Boot 3.3.x (thường đi với Spring Framework 6.1.x) và chỉ dùng rule minh thị, nên phân biệt rõ checked exception mặc định.

## 4. Ba kiểu bắt lỗi và hậu quả

### 4.1. Catch bên trong, log rồi trả về bình thường

```java
@Transactional
public void wrongTransfer() {
    decreaseSourceBalance();
    try {
        increaseDestinationBalance();
    } catch (IllegalStateException ex) {
        log.warn("Could not credit destination", ex);
    }
}
```

Luồng gọi:

1. Interceptor mở transaction.
2. `decreaseSourceBalance` cập nhật một hoặc nhiều hàng trong DB.
3. `increaseDestinationBalance` phát lỗi ứng dụng.
4. `catch` nuốt lỗi; method vẫn return bình thường.
5. Interceptor không thấy exception tương ứng với lỗi nghiệp vụ.
6. Nếu transaction chưa bị đánh dấu rollback-only, Spring có thể commit phần thay đổi nguồn.

Log lỗi không thay đổi rollback state. `@Transactional` không có cơ chế đọc log rồi hiểu nghiệp vụ thất bại. Cần chọn cách xử lý nhất quán với hợp đồng của method.

### 4.2. Catch để thêm ngữ cảnh rồi ném tiếp

```java
@Transactional
public void transfer() {
    decreaseSourceBalance();
    try {
        increaseDestinationBalance();
    } catch (IllegalStateException ex) {
        throw new TransferFailedException(
            "Failed while crediting destination", ex
        );
    }
}
```

Với `TransferFailedException extends RuntimeException` và `@Transactional` mặc định, exception mới **thoát khỏi** method, nên interceptor thấy lỗi và xử lý rollback. Nếu phải wrap exception, ưu tiên giữ **cause** để hỗ trợ chẩn đoán. Không wrap thành checked exception mà quên `rollbackFor`, vì có thể vô tình đổi hành vi rollback.

**Điểm về checked/wrapped exception:** Interceptor xem **exception thực tế mà nó nhận được** và rollback rules trên method. `new RuntimeException(cause)` và `new IOException(cause)` có thể cho kết quả rollback khác nhau nếu không có rule bổ sung.

### 4.3. Catch ở caller sau proxy boundary

```java
// Controller hoặc service orchestration không ở trong transaction riêng:
public String submit() {
    try {
        transferService.transfer();
        return "OK";
    } catch (TransferFailedException ex) {
        return "REJECTED";
    }
}
```

Nếu `transferService.transfer()` được gọi qua Spring proxy, rollback đã được quyết định/xử lý khi exception đi ra phương thức đó; caller có thể trả `"REJECTED"` mà không làm mất rollback. Nếu caller **cũng đang ở một transaction bao ngoài**, cần xem thêm propagation và rollback-only ở mục 7.

## 5. Demo chạy được với Java 17+, Spring Boot và H2

Demo cố ý dùng một ví có id 1 với 1.000 điểm và ví id 2 với 500 điểm. Một thao tác ghi nợ trừ 100 điểm khỏi ví 1, rồi thử ghi có vào id 999 (không tồn tại). Phần **ghi có thất bại được nhận diện bằng số hàng cập nhật bằng 0 và ném `IllegalStateException`**, không phải bởi lỗi SQL từ DB. Điều này quan trọng: ta muốn kiểm chứng **exception có đi qua interceptor hay không**, tránh phụ thuộc vào cách DBMS đánh dấu transaction sau một SQL error.

Chạy demo theo các trường hợp độc lập, **reset số dư trước từng trường hợp**, rồi quan sát:

| Case | Tín hiệu caller nhìn thấy | Số dư sau khi transaction kết thúc |
| --- | --- | --- |
| Lỗi bị nuốt bên trong | Return bình thường | 1=900, 2=500 (**commit dở nghiệp vụ**) |
| `RuntimeException` thoát qua interceptor | `IllegalStateException` | 1=1000, 2=500 (**rollback**) |
| Checked `IOException` thoát, mặc định | `IOException` | 1=900, 2=500 (**vẫn commit**) |
| Checked `IOException` và `rollbackFor` | `IOException` | 1=1000, 2=500 (**rollback**) |
| Bắt lỗi và `setRollbackOnly()` | Method trả `false` | 1=1000, 2=500 (**rollback có chủ đích**) |
| Service con `REQUIRED` ném lỗi, service cha bắt | `UnexpectedRollbackException` ở commit cha | 1=1000, 2=500 (**rollback**) |

Chương trình gồm năm file Java trong package `example.rollback`, bên cạnh ba file Gradle/config/schema.

### 5.1. `settings.gradle`

```groovy
rootProject.name = 'transaction-exception-boundary'
```

### 5.2. `build.gradle`

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

Dùng Gradle wrapper do Spring Initializr tạo cho dự án Java 17/Spring Boot 3.3.5, hoặc dùng bản Gradle tương thích. Có thể chạy qua terminal với `./gradlew bootRun` trên Unix/macOS hoặc `.\gradlew.bat bootRun` trên PowerShell. Demo không cần web server.

### 5.3. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:rollback_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Ứng dụng dùng `spring-boot-starter-jdbc` nên Spring Boot auto-configure `DataSource`, `JdbcTemplate` và JDBC transaction manager khi điều kiện thỏa mãn. `spring.sql.init.mode=always` chạy schema lúc khởi động. Database H2 in-memory này phục vụ kiểm thử, không thay thế một cấu hình DB bền vững trong sản xuất.

### 5.4. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

### 5.5. `src/main/java/example/rollback/WalletService.java`

```java
package example.rollback;

import java.io.IOException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class WalletService {
    private final JdbcTemplate jdbc;

    public WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void debit() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (rows != 1) {
            throw new IllegalStateException("Insufficient source balance");
        }
    }

    private void creditMissingWallet() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance + 100 WHERE id = 999"
        );
        if (rows != 1) {
            throw new IllegalStateException("Destination missing");
        }
    }

    @Transactional
    public void swallowedInside() {
        debit();
        try {
            creditMissingWallet();
        } catch (IllegalStateException ignored) {
            // Lỗi đã bị nuốt trong method; interceptor thấy return bình thường.
        }
    }

    @Transactional
    public void escapedOutside() {
        debit();
        creditMissingWallet();
        // RuntimeException đi ra khỏi method và được interceptor quan sát.
    }

    @Transactional
    public void checkedDefault() throws IOException {
        debit();
        throw new IOException("External validation failed");
    }

    @Transactional(rollbackFor = IOException.class)
    public void checkedWithRollbackRule() throws IOException {
        debit();
        throw new IOException("External validation failed");
    }

    @Transactional
    public boolean markRollbackOnlyAfterCatch() {
        debit();
        try {
            creditMissingWallet();
            return true;
        } catch (IllegalStateException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            return false;
        }
    }
}
```

**Đọc code đúng cách:**

- `debit()` và `creditMissingWallet()` là **helper private** chạy trong cùng lời gọi `WalletService` đang được bọc transaction. Chúng không tự mở transaction, không cần một annotation mới.
- `swallowedInside()` có thể commit thay đổi của `debit()`, vì exception từ `creditMissingWallet()` **không thoát ra ngoài**.
- `escapedOutside()` để unchecked exception tiếp tục đến interceptor: mặc định Spring rollback.
- `checkedDefault()` ném **checked `IOException`**. Nó thoát ra tới caller nhưng theo default của Spring Boot 3.3.x vẫn không trigger rollback, nên debit có thể commit.
- `checkedWithRollbackRule()` chỉ khác ở metadata `rollbackFor = IOException.class`, cho phép interceptor rollback.
- `markRollbackOnlyAfterCatch()` mô tả một lựa chọn khi bắt buộc giữ xử lý nội bộ: chủ động đặt transaction rollback-only. Nó trả `false` để caller biết nghiệp vụ **không thành công**, dù không ném lại lỗi. Đây là giải pháp có sự phụ thuộc trực tiếp vào API transaction của Spring; ưu tiên ném lỗi cho interceptor khi thiết kế cho phép.

Lưu ý: không sử dụng `@Transactional` trực tiếp trên `debit()` private rồi mong proxy nhìn thấy `this.debit()`. Ở đây transaction bắt đầu từ **public method entrypoint** được gọi qua bean Spring, và helper chạy trong transaction đã mở.

### 5.6. `src/main/java/example/rollback/InnerService.java`

```java
package example.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void debitThenFail() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (rows != 1) {
            throw new IllegalStateException("Insufficient source balance");
        }
        throw new IllegalStateException("Inner failure");
    }
}
```

### 5.7. `src/main/java/example/rollback/OuterService.java`

```java
package example.rollback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void catchesInner() {
        try {
            inner.debitThenFail();
        } catch (IllegalStateException ignored) {
            // Chỉ nuốt exception; không thể xóa rollback-only của transaction.
        }
    }
}
```

Hai service khác bean để lời gọi `outer -> inner` **đi qua proxy của `InnerService`**. Cả hai dùng mặc định `Propagation.REQUIRED`, vì vậy chúng tham gia **cùng transaction vật lý** khi lời gọi bắt đầu từ ngoài.

Khác với `WalletService.swallowedInside()`, exception từ `InnerService.debitThenFail()` **đã đi qua transaction interceptor của service con**. Interceptor con đánh dấu shared transaction là rollback-only. Bắt exception bên ngoài inner proxy không đảo ngược quyết định này.

Khi `OuterService.catchesInner()` kết thúc bình thường và proxy cha cố commit, transaction thực tế đã rollback-only. Vì caller không chủ ý yêu cầu rollback ở scope ngoài, Spring báo `UnexpectedRollbackException` để không khiến caller tin rằng commit đã thành công. Tình huống này có giải thích chi tiết ở mục 7.

### 5.8. `src/main/java/example/rollback/RollbackDemoApplication.java`

```java
package example.rollback;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackDemoApplication {

    @FunctionalInterface
    interface ThrowingJob {
        void run() throws Exception;
    }

    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void scenario(
            String label, JdbcTemplate jdbc, ThrowingJob job) {
        reset(jdbc);
        String signal = "completed";

        try {
            job.run();
        } catch (Exception ex) {
            signal = ex.getClass().getSimpleName();
        }

        System.out.println(
            label + " | signal=" + signal + " | " + balances(jdbc)
        );
    }

    @Bean
    ApplicationRunner demo(
            WalletService wallets,
            OuterService outer,
            JdbcTemplate jdbc) {
        return args -> {
            scenario("Caught inside", jdbc, wallets::swallowedInside);
            scenario("Escaped", jdbc, wallets::escapedOutside);
            scenario("Checked default", jdbc, wallets::checkedDefault);
            scenario("Checked rule", jdbc, wallets::checkedWithRollbackRule);

            reset(jdbc);
            boolean result = wallets.markRollbackOnlyAfterCatch();
            System.out.println(
                "Manual rollback | result=" + result +
                " | " + balances(jdbc)
            );

            scenario(
                "Inner REQUIRED caught by outer",
                jdbc,
                outer::catchesInner
            );
        };
    }
}
```

Đây là một ứng dụng **khởi chạy hoàn chỉnh trong project Gradle/Spring Boot có các file trên**. `ApplicationRunner` gọi `WalletService`/`OuterService` được Spring inject qua container, tức lời gọi đi qua proxy. Các `JdbcTemplate` update trong `reset()` chạy **ngoài** transaction của service và trả fixture về trạng thái ban đầu.

### 5.9. Chạy và kết quả dự kiến

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Những dòng do chính ứng dụng in ra, bỏ qua log khởi động Spring/Gradle, dự kiến:

```text
Caught inside | signal=completed | 1=900, 2=500
Escaped | signal=IllegalStateException | 1=1000, 2=500
Checked default | signal=IOException | 1=900, 2=500
Checked rule | signal=IOException | 1=1000, 2=500
Manual rollback | result=false | 1=1000, 2=500
Inner REQUIRED caught by outer | signal=UnexpectedRollbackException | 1=1000, 2=500
```

Mỗi trường hợp được reset độc lập, nên không phải cộng dồn các lần trừ tiền. Đây là **kết quả suy ra từ luồng code và cấu hình được trình bày**, không phải lời khẳng định đã chạy chính project này. Khi chuyển sang DBMS khác, hãy giữ cùng business invariants và kiểm thử theo database/transaction manager đang dùng.

### 5.10. Ý nghĩa của từng trường hợp

**Caught inside:** `debit()` thay ví nguồn 1.000 thành 900. `creditMissingWallet()` không tìm thấy ví 999, method tự bắt lỗi và return bình thường. Interceptor thấy không có unchecked exception thoát ra nên commit. Đây là lỗi nghiệp vụ thường cần sửa.

**Escaped:** Các câu SQL diễn ra như trên nhưng `IllegalStateException` không bị nuốt. Interceptor thấy unchecked exception, rollback. Sau đó `ApplicationRunner` mới bắt lỗi để in `IllegalStateException`. Đây là ví dụ rõ nhất của quy tắc “exception phải đi qua boundary”.

**Checked default:** `IOException` thoát ra, nhưng rollback rules mặc định không đánh dấu rollback cho checked exception. Spring có thể commit debit rồi caller vẫn nhận `IOException`.

**Checked rule:** Cùng `IOException`, thêm `rollbackFor` nên interceptor rollback như yêu cầu.

**Manual rollback:** Method đã bắt exception nhưng tự gọi `setRollbackOnly()`, trả `false` cho biết business operation không thành công. Trong tình huống method **sở hữu transaction mới** của demo, Spring thực hiện rollback ngay khi method kết thúc, không phải commit.

**Inner REQUIRED:** Inner interceptor nhìn thấy unchecked exception và đánh dấu transaction đang chia sẻ là rollback-only. Outer bắt lỗi nhưng không thể biến shared transaction trở lại “committable”. `UnexpectedRollbackException` được ném ở boundary ngoài khi cố commit.

## 6. Thiết kế lại try/catch để interceptor biết thất bại

Trong thực tế, việc bắt lỗi có giá trị: thêm context, tạo mã lỗi nghiệp vụ, cleanup tài nguyên ngoài DB hoặc phát log. Vấn đề là **bắt ở đâu và có giữ nguyên tín hiệu thất bại không**.

### 6.1. Ném lại cùng exception

```java
@Transactional
public Receipt finalizePayment(long paymentId) {
    try {
        return savePaymentAndLedger(paymentId);
    } catch (RuntimeException ex) {
        log.error("Payment {} failed", paymentId, ex);
        throw ex;
    }
}
```

`throw ex` giữ nguyên loại exception và stack trace, nên rule mặc định cho unchecked exception vẫn áp dụng. Ví dụ minh họa cần các dependency `Receipt`, repository và logger của ứng dụng; không phải file độc lập.

### 6.2. Ném một domain exception mới

```java
public final class PaymentRejectedException extends RuntimeException {
    public PaymentRejectedException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Transactional
public void settlePayment(long paymentId) {
    try {
        performSettlement(paymentId);
    } catch (IllegalStateException ex) {
        throw new PaymentRejectedException("Settlement failed", ex);
    }
}
```

Đây là thiết kế hợp lệ nếu caller cần một domain error cụ thể, và `PaymentRejectedException` là **unchecked**. Nên giữ cause, tránh tạo `new RuntimeException("failed")` rồi mất hết thông tin gốc. Lớp và method là hai snippet minh họa; trong project thật cần đặt class vào file tương ứng.

### 6.3. Nếu muốn phục hồi rồi tiếp tục thì sao?

Không phải mọi exception bắt được đều bắt buộc hủy transaction. Có những nghiệp vụ được phép fallback, ví dụ một truy vấn **không quan trọng** không thành công nhưng các invariant vẫn giữ nguyên. Khi đó bắt lỗi và tiếp tục có thể là lựa chọn đúng, **miễn bạn chủ động chấp nhận commit phần đã thành công** và hiểu trạng thái DB còn dùng được.

Tuy nhiên, với công việc nhiều bước phải **all-or-nothing**, bắt lỗi sau bước giữa rồi return success là nguy hiểm. Các trường hợp đó nên:

- để exception phù hợp thoát qua interceptor;
- dùng `rollbackFor` cho checked exception quan trọng;
- chủ động `setRollbackOnly()` và trả `Result` thất bại rõ nghĩa nếu cần xử lý tại chỗ;
- hoặc thiết kế một transaction nhỏ riêng, savepoint hay workflow bù trừ nếu yêu cầu có thể phục hồi một phần.

Không thể vừa yêu cầu “mọi bước cùng thành công” vừa im lặng commit sau một bước bắt buộc thất bại.

## 7. Ngoại lệ qua boundary của inner service: tại sao catch ở outer vẫn rollback?

Một lỗi phổ biến là cho rằng:

> “Tôi đã catch exception trong outer service nên Spring phải commit outer transaction.”

Suy luận đó thiếu một bước: **exception đã đi qua interceptor của inner service chưa?**

Với `Propagation.REQUIRED`:

```text
Caller
  |
  v
Outer proxy: tạo transaction vật lý T
  |
  v
OuterService.catchesInner()
  |
  v
Inner proxy: tham gia T, tạo scope transaction logic bên trong
  |
  v
InnerService.debitThenFail()
  |
  +-- UPDATE ví nguồn
  +-- throw IllegalStateException
  |
  v
Inner interceptor thấy lỗi
  |
  +-- đánh dấu T rollback-only
  +-- ném lại exception
  |
  v
OuterService catch exception và return bình thường
  |
  v
Outer interceptor cố commit T
  |
  +-- T đã rollback-only -> rollback
  +-- báo UnexpectedRollbackException
```

Hai scope `@Transactional` logic có thể dùng **cùng một transaction vật lý**. `REQUIRED` tham gia transaction của caller nếu đã có. Vì vậy, không có “commit riêng” cho inner method. Dấu rollback-only do inner advice gây ra ảnh hưởng tới kết quả cuối ở outer.

`UnexpectedRollbackException` có ý nghĩa an toàn: một caller đã được hứa rằng method hoàn tất không thể lặng lẽ tin là **commit** nếu thực tế transaction được rollback bởi scope con.

### Khác với `REQUIRES_NEW` và `NESTED`

| Propagation của inner method | Điều có thể xảy ra khi inner thất bại | Cần lưu ý |
| --- | --- | --- |
| `REQUIRED` | Inner và outer dùng cùng transaction vật lý, inner rollback-only có thể khiến outer commit thất bại với `UnexpectedRollbackException` | Đây là demo mục 5 |
| `REQUIRES_NEW` | Inner chạy một transaction vật lý độc lập; rollback inner không nhất thiết làm outer rollback | Có thể cần connection riêng, không bảo đảm atomicity chung |
| `NESTED` | Với manager/driver hỗ trợ savepoint, inner có thể rollback về savepoint rồi outer tiếp tục | Không tự suy ra hỗ trợ trên mọi DB/JPA/manager |

Không đổi `REQUIRES_NEW` chỉ để tránh `UnexpectedRollbackException` nếu dữ liệu của hai nghiệp vụ **phải** commit/rollback cùng nhau. Phương án đúng thường là để failure đi ra khỏi **outer transactional boundary**, hoặc thiết kế rõ cơ chế phục hồi phù hợp với invariant.

### Catch exception ở controller khác catch trong outer transaction

Trong demo, `ApplicationRunner` gọi `outer.catchesInner()` rồi bắt `UnexpectedRollbackException` **sau khi outer proxy đã hoàn tất quyết định rollback**. Bắt ở đây không làm transaction commit trở lại. Tương tự, HTTP controller có thể map lỗi thành status 409/422/500 sau khi giao dịch đã kết thúc.

## 8. `rollbackOnly` dùng đúng và hiểu đúng

Một method transactional có thể chủ động yêu cầu rollback mà không ném exception:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public OperationResult tryProcess() {
    try {
        performOperation();
        return OperationResult.success();
    } catch (KnownBusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return OperationResult.failure(ex.getMessage());
    }
}
```

Snippets này giả định `OperationResult`, `KnownBusinessException` và `performOperation()` thuộc ứng dụng; method không độc lập để chạy bằng `javac`.

Nếu method sở hữu transaction mới và đánh dấu **local rollback-only**, interceptor sẽ rollback khi kết thúc. Khi một participating transaction hoặc scope con đã đánh dấu **global rollback-only** đối với transaction vật lý được chia sẻ, scope ngoài có thể nhận `UnexpectedRollbackException` khi cố commit. Đừng kỳ vọng có thể gọi một API “clearRollbackOnly()” để khôi phục giao dịch. Nếu DB đã coi transaction là hỏng, cũng không nên tiếp tục dùng nó như chưa xảy ra gì.

`TransactionAspectSupport.currentTransactionStatus()` chỉ có nghĩa trong lời gọi đang được transaction advice của Spring quản lý; gọi từ code chạy ngoài scope transactional có thể không có status. Nó làm service phụ thuộc trực tiếp vào Spring transaction API, nên ưu tiên cơ chế declarative khi có thể.

Một lựa chọn programmatic khác là `TransactionTemplate`:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

OperationResult result = template.execute(status -> {
    try {
        performOperation();
        return OperationResult.success();
    } catch (KnownBusinessException ex) {
        status.setRollbackOnly();
        return OperationResult.failure(ex.getMessage());
    }
});
```

Đoạn này chỉ minh họa API bên trong class đã có `transactionManager` và các kiểu nghiệp vụ; không phải chương trình độc lập. Cả hai cách đều cần **trả trạng thái thất bại minh bạch** cho caller. Không dùng rollback-only rồi trả một object “success” đánh lừa các tầng phía trên.

## 9. Lỗi database có thể khiến transaction không còn commit được ngay cả khi exception bị bắt

Đừng hiểu quy tắc ở đầu bài là:

> “Cứ catch exception trong transaction thì chắc chắn DB sẽ commit.”

Đây là kết luận sai. Ngoại lệ được bắt có thể đến từ **DBMS**, chứ không chỉ từ kiểm tra nghiệp vụ.

Ví dụ, với PostgreSQL, nhiều lỗi câu SQL (constraint violation, syntax error trong transaction...) đưa transaction hiện tại về trạng thái **aborted**; các statement sau đó thường bị từ chối cho đến khi `ROLLBACK` hoặc xử lý theo savepoint phù hợp. Spring hoặc transaction manager cũng có thể đánh dấu transaction rollback-only. Nếu application chỉ nuốt exception, nó không làm transaction tự hồi phục.

Cần phân biệt:

1. **Application-level exception sau câu SQL hợp lệ:** ví dụ `UPDATE ... WHERE id = 999` cập nhật **0 hàng**, JDBC không báo lỗi. Service tự ném `IllegalStateException`; nếu nuốt và chưa có rollback-only, DB vẫn có thể commit phần trước. Demo được thiết kế theo loại này.
2. **Database-level SQL error:** ví dụ khóa trùng làm DBMS từ chối statement. Trạng thái transaction sau lỗi phụ thuộc DBMS, driver, savepoint và manager. Catch trong Java **không** là bằng chứng đã có khả năng commit.
3. **Một inner transactional interceptor đã thấy exception:** nó có thể đã đánh dấu transaction rollback-only dù outer service catch lỗi sau đó.
4. **Transaction timeout/rollback-only từ trước:** method có thể return bình thường nhưng commit vẫn thất bại hoặc bị chuyển thành rollback.

Vì thế, khi gỡ lỗi phải kiểm tra **lỗi xuất phát ở đâu**, **đã đi qua interceptor nào**, **trạng thái transaction** và **hành vi DBMS**; không chỉ tìm số lượng `catch` trong source code.

## 10. Những tình huống ngoài luồng method đồng bộ

### 10.1. Self-invocation: exception có thể không bao giờ đi qua proxy cần thiết

```java
@Service
public class OrderService {
    public void createOrder() {
        saveOrder();
    }

    @Transactional
    public void saveOrder() {
        // Thao tác dữ liệu; có thể ném exception.
    }
}
```

Đây là snippet minh họa. `createOrder()` gọi `saveOrder()` qua `this`, không qua Spring AOP proxy đối với method `saveOrder`. Vì vậy, `@Transactional` trên method được gọi nội bộ **không tự kích hoạt interceptor**. Dù `saveOrder()` ném unchecked exception, sẽ không có transaction do annotation ấy tạo nếu không có boundary khác.

Giải pháp: đặt transaction ở public entrypoint mà caller thực sự gọi qua proxy, hoặc tách method transactional sang một Spring bean khác và gọi bean đó. **Đổi từ JDK proxy sang CGLIB không giải quyết self-invocation.**

Nếu `createOrder()` đã được một transaction bên ngoài bao phủ, câu SQL bên trong `saveOrder()` vẫn có thể tham gia transaction ngoài; nhưng **cấu hình rollback riêng trên `saveOrder()`** không được áp dụng bởi interceptor của method đó.

### 10.2. `@Async`, thread khác và tương tác sau commit

Transaction imperative thường gắn với thread/context giao dịch do Spring quản lý. Nếu method transactional khởi tạo một tác vụ bất đồng bộ rồi return ngay, một exception phát sinh trong task **sau khi method đã return** thường không thể làm interceptor rollback transaction đã hoàn tất.

```java
@Transactional
public void launchTask(Executor executor) {
    saveToDatabase();
    executor.execute(() -> {
        throw new IllegalStateException("Late async failure");
    });
}
```

Ví dụ này chỉ minh họa vấn đề thời gian và không đảm bảo task trên executor dùng cùng transaction. Tránh mở tác vụ fire-and-forget làm phần bắt buộc trong nghiệp vụ ACID. Nếu cần một đơn vị transaction ở task khác, phải có boundary/manager riêng và giải pháp consistency liên tiến trình/tài nguyên khi cần.

**Ngoại lệ có điều kiện:** Spring Framework 6.1+ có xử lý đặc biệt cho một số `Future`/`CompletableFuture` **đã hoàn thành lỗi ngay tại thời điểm method trả về**, và hỗ trợ Vavr `Try.Failure` theo tài liệu. Những trường hợp này **không** có nghĩa Spring theo dõi mọi lỗi bất đồng bộ trong tương lai và rollback giao dịch đã commit. Với flow đồng bộ thông thường, quy tắc cho exception thoát khỏi method vẫn là nền tảng.

### 10.3. Reactive publisher: cần để tín hiệu `onError` qua vùng transaction

Với `ReactiveTransactionManager`, thời điểm thực thi gắn với subscription của `Mono`/`Flux`. Spring transaction interceptor/operator xem các tín hiệu kết thúc của publisher. Nếu trước ranh giới transactional bạn biến lỗi thành completion, transaction có thể commit:

```java
// Snippet minh họa: work là Mono<Void>, tx là TransactionalOperator.
Mono<Void> unsafe = work
    .onErrorResume(ex -> Mono.empty())
    .as(tx::transactional);
```

Ở đây transaction operator nhận completion; nó không còn nhận `onError` từ business failure.

Khi cần báo lỗi sau rollback:

```java
Mono<Void> safer = work
    .as(tx::transactional)
    .onErrorResume(ex -> handleAfterRollback(ex));
```

Cách này cho phép transaction operator thấy lỗi và xử lý rollback trước khi fallback downstream. `handleAfterRollback` là method của ứng dụng, phải phản ánh kết quả nghiệp vụ thất bại đúng cách. Cancellation của reactive stream cũng có semantics rollback riêng; không suy ra bằng try/catch của imperative method.

## 11. Kiểm thử rollback thật thay vì chỉ kiểm tra exception

Một test chỉ `assertThrows(IllegalStateException.class, ...)` **chưa đủ**. Nó không khẳng định DB đã rollback; trong một method checked exception không có `rollbackFor`, test vẫn nhận exception nhưng DB có thể commit thay đổi.

Nên kiểm tra cả tín hiệu caller và **trạng thái DB sau khi method kết thúc**.

### 11.1. Test JUnit 5 cho hành vi chính

File `src/test/java/example/rollback/RollbackDemoTest.java`:

```java
package example.rollback;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class RollbackDemoTest {
    @Autowired WalletService wallets;
    @Autowired OuterService outer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private long balanceOf(long id) {
        Long value = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?",
            Long.class,
            id
        );
        return value;
    }

    @Test
    void catchingInsideCanCommitPartialBusinessOperation() {
        wallets.swallowedInside();
        assertEquals(900L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void escapingRuntimeExceptionTriggersRollback() {
        assertThrows(IllegalStateException.class, wallets::escapedOutside);
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void checkedExceptionDefaultCanCommit() {
        assertThrows(IOException.class, wallets::checkedDefault);
        assertEquals(900L, balanceOf(1L));
    }

    @Test
    void checkedExceptionWithRuleRollsBack() {
        assertThrows(IOException.class, wallets::checkedWithRollbackRule);
        assertEquals(1000L, balanceOf(1L));
    }

    @Test
    void manualRollbackOnlyReportsFailure() {
        assertFalse(wallets.markRollbackOnlyAfterCatch());
        assertEquals(1000L, balanceOf(1L));
    }

    @Test
    void innerRollbackOnlyCannotBeClearedByOuterCatch() {
        assertThrows(UnexpectedRollbackException.class, outer::catchesInner);
        assertEquals(1000L, balanceOf(1L));
    }
}
```

Với dependency `spring-boot-starter-test` trong `build.gradle`, chạy:

```bash
./gradlew test
```

`@BeforeEach` reset fixture cho từng test. `ApplicationRunner` của demo có thể thực thi lúc `@SpringBootTest` dựng context; mỗi test lại đặt số dư về giá trị gốc trước khi assert. Test method **không được gắn `@Transactional`** trong ví dụ này, để một transaction của test framework không che giấu việc service có commit/rollback thực hay không.

Nếu chạy test song song và chia sẻ cùng một H2 database, các fixture reset có thể đè nhau. Với test tích hợp chạy song song, dùng database/schema biệt lập hoặc test resources phù hợp. Không nên chỉ dựa vào Mockito cho kết luận rollback, vì mock repository không kiểm chứng transaction vật lý.

### 11.2. Điều gì phải được chứng minh?

| Kiểm tra | Vì sao cần |
| --- | --- |
| Exception có thoát tới caller hay không | Cho biết lời gọi qua proxy có tín hiệu lỗi |
| Loại exception và rollback rules thực tế | Checked và unchecked có thể khác nhau |
| Transaction manager nào điều phối DB | Cùng tên annotation không có nghĩa cùng connection |
| Dữ liệu sau khi service kết thúc | Bằng chứng commit/rollback thật |
| Caller đang ở transaction nào | Propagation có thể làm kết quả thay đổi |
| Có DB error/rollback-only trước đó không | Catch không hứa được commit |
| Annotation có thực sự được interceptor áp dụng không | Self-invocation/bean không được proxy có thể bỏ qua metadata |

Bằng chứng mạnh là **trạng thái dữ liệu độc lập sau transaction**, cộng với kiểm tra exception và log transaction khi cần. Với các bài toán concurrent hoặc serialization failure, bổ sung test nhiều connection và xử lý retry.

## 12. Các mẫu xử lý nghiệp vụ nên dùng

### Mẫu A — lỗi buộc hủy toàn bộ thao tác

```java
@Transactional
public void placeOrder(CreateOrderCommand cmd) {
    reserveStock(cmd);
    debitWallet(cmd);
    saveOrder(cmd);
}
```

Nếu một bước bắt buộc ném `RuntimeException` đi ra method, Spring mặc định rollback các thao tác DB tham gia transaction. Các helper chỉ minh họa đơn vị nghiệp vụ, cần triển khai và kiểm tra affected rows/constraints. Đặt transaction ở tầng bao trùm đủ ba bước.

### Mẫu B — checked business exception cũng buộc hủy

```java
@Transactional(rollbackFor = InsufficientInventoryException.class)
public void placeOrder(CreateOrderCommand cmd)
        throws InsufficientInventoryException {
    reserveStock(cmd);
    debitWallet(cmd);
    saveOrder(cmd);
}
```

`InsufficientInventoryException` giả định là một checked exception của ứng dụng. `rollbackFor` diễn đạt chính xác trường hợp phải rollback; không bắt buộc mọi exception khác đều được thay đổi rule.

### Mẫu C — controller map exception thành HTTP response

```java
@PostMapping("/orders")
public ResponseEntity<?> create(@RequestBody CreateOrderCommand cmd) {
    try {
        orderService.placeOrder(cmd);
        return ResponseEntity.status(201).build();
    } catch (InsufficientInventoryException ex) {
        return ResponseEntity.unprocessableEntity().body(ex.getMessage());
    }
}
```

Controller ở ngoài transactional service; lỗi đã đi qua interceptor trước khi catch. Đây là snippet cho ứng dụng Spring MVC có đầy đủ imports/class/DTO, **không phải chương trình Java độc lập**.

### Mẫu D — lỗi không bắt buộc thì phục hồi minh thị

```java
@Transactional
public Receipt saveWithOptionalLabel(Order order) {
    Receipt receipt = persistOrder(order);
    try {
        enrichOptionalLabel(receipt);
    } catch (OptionalLabelException ex) {
        recordNonCriticalWarning(ex);
    }
    return receipt;
}
```

Chỉ dùng khi `enrichOptionalLabel` **thật sự tùy chọn**, trạng thái DB còn committable và việc lưu receipt không cần label để đáp ứng invariant. Nếu label là bước bắt buộc, đây là lỗi thiết kế. Đừng dùng mẫu này để chữa các exception do database constraint hoặc các inner transaction đã đặt rollback-only.

### Mẫu E — side effect ngoài DB cần thiết kế riêng

Nếu service đã gọi HTTP thanh toán, gửi email hoặc publish event, rollback DB không tự xóa side effect ngoài DB. Khi yêu cầu giao dịch liên hệ thống, cân nhắc transactional outbox, idempotency key hoặc saga/compensation. Ngoại lệ thoát qua interceptor chỉ điều phối những tài nguyên mà transaction manager thực sự quản lý.

## 13. Bảng lỗi phổ biến khi debug

| Triệu chứng | Điều cần điều tra | Cách sửa |
| --- | --- | --- |
| DB vẫn commit dù đã log error | Exception bị catch trong transactional method | Ném lại hoặc mark rollback-only nếu nghiệp vụ cần hủy |
| Method ném `IOException` nhưng DB commit | Checked exception không khớp rollback rules | Khai báo `rollbackFor` hoặc đổi chính sách có chủ đích |
| Có `@Transactional` nhưng không thấy rollback | Lời gọi không qua proxy, ví dụ self-invocation | Đưa transaction lên entrypoint hoặc tách bean |
| Outer method catch rồi vẫn `UnexpectedRollbackException` | Inner `REQUIRED` interceptor đã mark rollback-only | Để lỗi đi ra outer boundary hoặc thiết kế phục hồi đúng |
| Lỗi SQL đã catch nhưng transaction vẫn aborted | DBMS/driver đã đánh dấu transaction hỏng | Rollback/retry cả transaction theo database semantics |
| Test có exception nhưng vẫn mất dữ liệu | Test chỉ kiểm tra thrown type, chưa kiểm tra DB | Assert dữ liệu sau transaction kết thúc |
| Wrap exception rồi rollback behavior đổi | Đổi `RuntimeException` thành checked hoặc ngược lại | Review rollback rules trên exception thực tế |
| Đặt `noRollbackFor` nhưng mong rollback | Rule được cấu hình trái với yêu cầu | Chỉnh rule và viết regression test |
| Có lỗi từ task async sau khi caller trả về | Task nằm ngoài thời gian/ràng buộc transaction | Thiết kế transaction riêng và xử lý failure eventual |
| Log thành công nhưng DB đã rollback | Có rollback-only bị đặt trước đó | Quan sát transaction status và `UnexpectedRollbackException` |
| Dùng `try/finally` tưởng tự rollback | `finally` không thay thế exception propagation | Để interceptor nhận error hoặc mark rollback-only |

## 14. Tự kiểm tra kiến thức

1. Trong một public method `@Transactional`, code bắt `IllegalStateException`, log rồi return bình thường. Spring có tự biết lỗi đó đã xảy ra không? **Không trong đường interceptor xử lý exception đồng bộ thông thường**; trừ khi DB/manager đã đánh dấu rollback-only theo đường khác, transaction có thể commit.
2. Controller bắt exception do `service.pay()` ném. Transaction có còn được rollback không? **Có thể có**, nếu exception đã đi qua proxy của service và khớp rollback rules; catch tại controller không đảo ngược rollback.
3. `IOException` thoát qua `@Transactional` mặc định trong Spring 6.1 thường gây rollback không? **Không**; cần rule bổ sung nếu nghiệp vụ muốn rollback.
4. `@Transactional(rollbackFor=IOException.class)` thay đổi điều gì? **Nó cho interceptor biết phải rollback khi `IOException` thoát qua boundary.**
5. Nếu một inner `REQUIRED` transaction đã mark rollback-only, outer catch lỗi rồi return bình thường có chắc commit không? **Không**, outer commit có thể ném `UnexpectedRollbackException`.
6. `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` dùng để làm gì? **Yêu cầu rollback có chủ đích dù method xử lý lỗi nội bộ.**
7. Lỗi SQL bị catch rồi có chắc DB vẫn committable không? **Không**; DBMS có thể đặt transaction vào trạng thái lỗi.
8. Method `@Transactional` gọi qua `this.method()` trong cùng object có kích hoạt interceptor mới không? **Không trong proxy mode thông thường.**
9. Exception trong background task xảy ra sau khi transactional method đã commit có rollback transaction cũ không? **Không**.
10. Vì sao test chỉ `assertThrows` chưa chứng minh rollback? **Vì checked exception có thể thoát ra nhưng transaction vẫn commit; phải kiểm tra dữ liệu sau khi kết thúc.**

## 15. Checklist thiết kế rollback policy

1. Xác định **toàn bộ bước bắt buộc** phải cùng commit hoặc rollback; đặt `@Transactional` ở public service boundary đi qua Spring proxy.
2. Với mỗi kiểu exception, quyết định rõ **rollback hay được phép commit**; không dựa vào trực giác “có ném lỗi là tự hủy”.
3. Nếu lỗi buộc hủy, để exception phù hợp đi qua transaction interceptor; với checked exception, khai báo `rollbackFor`.
4. Nếu phải catch để ghi log/đổi thông báo, **ném tiếp** exception phù hợp và giữ cause. Nếu xử lý ở caller, catch sau khi qua proxy.
5. Nếu catch và không ném lại, xác nhận bước hỏng có thật sự được phép bỏ qua; nếu cần hủy, mark rollback-only và trả failure result minh bạch.
6. Kiểm tra propagation và outer/inner transactional scopes; hiểu ảnh hưởng của shared rollback-only tới `UnexpectedRollbackException`.
7. Phân biệt **application exception** với **DB SQL error**; không giả định catch sẽ khôi phục trạng thái transaction của database.
8. Không tách bước bắt buộc vào fire-and-forget task hay side effect ngoài DB mà không có chiến lược consistency riêng.
9. Kiểm thử cả **lỗi đi qua boundary**, **rule áp dụng**, **transaction manager phù hợp** và **trạng thái DB sau kết thúc**.
10. Ghi nhận phiên bản Spring và cấu hình rollback default thực tế khi nâng cấp hệ thống.

## Tài liệu tham khảo chính thức

- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional` và rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation, `REQUIRED` và `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html