# Checked exception và nhu cầu khai báo rollback rõ ràng trong Spring Transaction Management

## 1. Vì sao một exception vẫn có thể khiến transaction commit?

Trong Java, **checked exception** là exception mà trình biên dịch buộc mã gọi phải xử lý bằng `catch` hoặc khai báo `throws`, ví dụ `IOException`, `SQLException` hay một exception nghiệp vụ `extends Exception`. **Unchecked exception** thường là `RuntimeException` và các lớp kế thừa; `Error` cũng không chịu kiểm tra checked-exception của trình biên dịch.

Trong **cấu hình rollback mặc định truyền thống của Spring**, một phương thức `@Transactional` ném exception thoát ra ngoài có kết quả:

- `RuntimeException` hoặc `Error`: Spring **chọn rollback**.
- Một checked `Exception` không phải `RuntimeException`: Spring **không mặc định chọn rollback**. Nếu transaction do phương thức đó sở hữu và vẫn có thể commit, Spring sẽ **commit dù vẫn truyền checked exception cho caller**.

Đây là **quy tắc của Spring transaction interceptor**, không phải quy tắc Java rằng checked exception “không nghiêm trọng” hoặc database tự động quyết định dựa trên kiểu exception. Checked/unchecked chỉ nói về cơ chế compile và phân loại Throwable; **điều cần làm khi lỗi xuất hiện là quyết định nghiệp vụ**.

Ví dụ một giao dịch tạo đơn hàng, trừ tồn kho rồi phát hiện địa chỉ giao hàng không hợp lệ:

```java
@Transactional
public void placeOrder(...) throws InvalidDeliveryAddressException {
    orderRepository.save(...);
    stockRepository.reserve(...);

    throw new InvalidDeliveryAddressException("Cannot ship to address");
}
```

Nếu `InvalidDeliveryAddressException extends Exception`, không có rollback rule khác và transaction thực sự mở, **các thao tác DB trước đó có thể được commit** khi exception thoát khỏi phương thức. Điều này thường trái với mong muốn “đơn hàng hoặc thành công toàn bộ hoặc không thay đổi gì”. Cách rõ ràng:

```java
@Transactional(rollbackFor = InvalidDeliveryAddressException.class)
public void placeOrder(...) throws InvalidDeliveryAddressException {
    // Cùng nghiệp vụ, nhưng exception này báo Spring rollback transaction.
}
```

Các đoạn vừa rồi là **mã minh họa**: repository, exception và tham số cần định nghĩa trong ứng dụng thật. Một project JDBC Spring Boot chạy được và output xác định sẽ có ở phần 5.

> **Quy tắc quan trọng:** “Có `throws`”, “đã ném exception”, “đã gọi `save`” và “đã cập nhật SQL” đều **không đủ** để suy ra transaction sẽ rollback. Phải xác định **loại exception, rollback rules, ranh giới transaction, đường gọi qua proxy và trạng thái DB**.

## 2. Tách bạch ba lớp quyết định

Một tình huống thường gặp:

```text
Caller
    |
    v
Spring transaction proxy / interceptor
    |-- bắt đầu hoặc tham gia transaction
    v
Service method
    |-- JDBC/JPA ghi dữ liệu trong transaction
    |-- throw BusinessCheckedException
    v
Proxy nhận exception
    |-- kiểm tra rollback rule
    |-- rollback hoặc cố gắng commit
    v
Caller vẫn nhận exception (nếu transaction hoàn tất như dự kiến)
```

Ba lớp quyết định khác nhau:

1. **Java:** yêu cầu `throws BusinessCheckedException` hoặc `catch` vì exception là checked; không quyết định database commit/rollback.
2. **Spring:** xem transaction attribute và rollback/no-rollback rules của method; có thể rollback hoặc cho transaction tiếp tục commit.
3. **Database:** thực thi `COMMIT`/`ROLLBACK` trên connection/transaction đang quản lý. Database có thể báo lỗi khi commit dù Spring đã chọn commit.

Nếu caller bắt exception sau khi proxy đã commit, **catch ở caller không thể tự rollback một transaction đã kết thúc**. Nếu exception bị bắt **ngay bên trong** transactional method rồi method trả về bình thường, interceptor không nhận exception đó; nếu không có tác nhân khác đánh dấu rollback-only, transaction thường đi đến commit.

### So sánh nhanh các kết quả

Giả định method `@Transactional` được gọi qua Spring proxy, dùng một DB có transaction, bắt đầu transaction mới, hoạt động DB thành công tới trước khi ném exception và không có quy tắc nào khác:

| Tình huống thoát khỏi method | Rollback mặc định truyền thống? | Hệ quả quan sát sau khi proxy xử lý |
| --- | --- | --- |
| Method trả về bình thường | Không | Commit nếu không có lỗi/rollback-only |
| `throw new IllegalStateException(...)` | **Có** | Các thay đổi DB trong transaction bị rollback |
| `throw new IOException(...)` | **Không** | Transaction có thể commit trước khi IOException được chuyển lên caller |
| `throw new CustomException(...)` với `CustomException extends Exception` | **Không** | Có thể commit dù caller nhận checked exception |
| Checked exception + `rollbackFor = CustomException.class` | **Có** | Spring yêu cầu rollback |
| Unchecked exception + `noRollbackFor = SpecificRuntimeException.class` | **Không đối với loại đã chỉ định** | Có thể commit rồi exception vẫn được ném cho caller |
| Exception được bắt và nuốt bên trong method | Proxy không thấy exception thoát ra | Thường commit, trừ khi trạng thái transaction đã bị đánh dấu rollback-only hay DB lỗi |

Tất cả kết luận về commit là **có điều kiện**: commit có thể thất bại bởi constraint, lỗi database, deadlock, transaction đã bị đánh dấu rollback-only, hoặc transaction do một scope bên ngoài sở hữu. “Spring chọn commit” **không có nghĩa chắc chắn commit đã thành công**.

## 3. Checked exception: `throws` không mang ý nghĩa rollback

Ví dụ định nghĩa exception nghiệp vụ:

```java
package demo.rollback;

public class BusinessCheckedException extends Exception {
    public BusinessCheckedException(String message) {
        super(message);
    }
}
```

Đây là checked exception vì kế thừa `Exception` trực tiếp, **không** kế thừa `RuntimeException`. Compiler buộc caller xử lý hoặc khai báo `throws BusinessCheckedException`. Cả hai API sau đều hợp lệ về mặt Java:

```java
@Transactional
public void processWithoutRule() throws BusinessCheckedException {
    updateDatabase();
    throw new BusinessCheckedException("Rejected");
}

@Transactional(rollbackFor = BusinessCheckedException.class)
public void processWithRule() throws BusinessCheckedException {
    updateDatabase();
    throw new BusinessCheckedException("Rejected");
}
```

Hai method có **cùng khai báo `throws`** nhưng chính sách rollback khác nhau. `rollbackFor` quyết định rollback vì một exception type xuất hiện; không ảnh hưởng việc compiler yêu cầu xử lý checked exception.

Tương tự, nếu JDBC thuần tự ném `SQLException`, đây là checked exception. Tuy nhiên, **`JdbcTemplate` và Spring JDBC thường chuyển `SQLException` thành `DataAccessException`**, là một `RuntimeException`, nên nhiều lỗi SQL được rollback theo mặc định. Không suy từ danh sách exception gốc của JDBC rằng `JdbcTemplate` sẽ đưa nguyên checked `SQLException` lên service.

Với Spring Data JPA, các lỗi persistence thường xuất hiện dưới dạng unchecked exception. Bởi vậy, một bài kiểm tra chỉ ném exception database có thể **không kiểm chứng đúng** quy tắc checked exception; cần tự ném một checked business exception sau thao tác DB thành công.

## 4. Khai báo rollback và no-rollback bằng `@Transactional`

### 4.1. Ưu tiên loại exception cụ thể

Cách rõ ràng nhất:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void registerCustomer(...) throws BusinessCheckedException {
    // Nếu exception này thoát khỏi method qua proxy, rollback.
}
```

Có thể chỉ định nhiều loại:

```java
@Transactional(rollbackFor = {
    BusinessCheckedException.class,
    java.io.IOException.class
})
public void completeOrder(...) throws BusinessCheckedException, java.io.IOException {
    // Chỉ cần một trong các exception này thoát ra là rule áp dụng.
}
```

`rollbackFor` nhận `Class<? extends Throwable>`. Khai một supertype như `Exception.class` sẽ áp dụng cho các subclass, bao gồm checked và unchecked `Exception`; các `Error` không kế thừa `Exception`, nhưng vẫn theo default rollback. Chính sách rộng đôi khi hữu ích, song nếu một checked exception biểu thị “không có dữ liệu” và quy trình cần commit có chủ đích, việc bắt rollback toàn bộ có thể không phù hợp.

Một rule cụ thể thường dễ hiểu và bảo trì hơn:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
```

so với:

```java
@Transactional(rollbackFor = Exception.class)
```

Quyết định nên căn cứ vào **giao ước nghiệp vụ**: exception nào biểu thị transaction phải bị hủy, exception nào chỉ là trạng thái vẫn có thể commit.

### 4.2. `noRollbackFor`: ngoại lệ vẫn được ném nhưng transaction có thể commit

Một số exception biểu thị trạng thái được chấp nhận sau khi đã ghi một thay đổi, chẳng hạn một exception runtime được dùng để báo caller “cần hành động tiếp theo”, trong khi audit record **phải được giữ**. Khi đó có thể cấu hình:

```java
@Transactional(noRollbackFor = ExpectedStatusException.class)
public void recordStatusAndReport() {
    // Ghi audit/đánh dấu trạng thái đã xác nhận.
    throw new ExpectedStatusException("Follow-up is required");
}
```

Đây là **minh họa**: `ExpectedStatusException` cần được định nghĩa (ví dụ kế thừa `RuntimeException`). `noRollbackFor` không bắt hoặc nuốt exception; caller vẫn thấy exception sau khi proxy xử lý. Nếu database đã báo lỗi khiến transaction không thể commit, rule này **không thể ép database commit thành công**.

Đừng lạm dụng `noRollbackFor` để “chữa” một luồng xử lý sai. Nếu nghiệp vụ không coi trạng thái là lỗi, việc trả về một result type như `Result`/status thay vì ném exception thường làm hợp đồng API dễ hiểu hơn.

### 4.3. Rule theo type so với rule theo tên class

Spring có bốn thuộc tính liên quan:

| Thuộc tính | Dạng khai báo | Ý nghĩa |
| --- | --- | --- |
| `rollbackFor` | `BusinessCheckedException.class` | Rollback cho type và các subclass |
| `rollbackForClassName` | `"demo.rollback.BusinessCheckedException"` | Rollback theo mẫu chuỗi tên exception |
| `noRollbackFor` | `SpecificRuntimeException.class` | Không yêu cầu rollback cho type và subclass |
| `noRollbackForClassName` | `"demo.rollback.SpecificRuntimeException"` | Không yêu cầu rollback theo mẫu chuỗi tên |

**Nên ưu tiên type-safe `.class`** khi exception class có trên classpath. Một string rule kiểu `rollbackForClassName = "Exception"` **không** có nghĩa “chỉ exception tên chính xác là Exception”; pattern so khớp **chuỗi con** của tên đầy đủ, có thể vô tình khớp nhiều loại khác. Dấu `*` **không phải** glob trong exception-name pattern. Ngay cả `"demo.rollback.BusinessCheckedException"` còn có khả năng khớp class tên `BusinessCheckedExceptionV2` hoặc nested class tương ứng do chuỗi tên chứa cùng đoạn.

Ví dụ minh họa riêng cho pattern khi type chưa thể tham chiếu trực tiếp:

```java
@Transactional(
    rollbackForClassName = "vendor.partner.CheckedIntegrationException"
)
public void integrate() throws Exception {
    // Rule khớp theo tên exception, không phải kiểu Java tại compile time.
}
```

Chỉ dùng trường hợp thật sự cần pattern; class-based rule ít rủi ro hơn.

### 4.4. Nếu rollback và no-rollback cùng khớp thì sao?

Spring chọn **rule khớp mạnh nhất**, dựa trên mức độ gần trong cây kế thừa type hoặc độ mạnh khớp pattern. Ví dụ:

```java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = SpecificBusinessException.class
)
public void updateAndMaybeReport() throws SpecificBusinessException {
    // SpecificBusinessException extends Exception
}
```

Khi `SpecificBusinessException` được ném, rule cụ thể `noRollbackFor` thắng rule rộng `rollbackFor = Exception.class`. Khi một checked exception khác kế thừa `Exception` được ném, rule `rollbackFor = Exception.class` có thể áp dụng. Không xây dựng một hệ rule chồng chéo không cần thiết hoặc có hai rule mạnh ngang nhau; hãy chọn chủ đích nghiệp vụ rõ ràng và kiểm thử.

**Phân biệt:** quy tắc “strongest matching rule wins” ở đây là **ưu tiên exception rule của một transaction attribute**. Nó không phải ưu tiên mẫu tên method `get*`/`save*` trong XML, cũng không phải thứ tự các AOP advisor.

## 5. Ví dụ chạy được: cùng checked exception, một method commit và một method rollback

Ta dùng **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2** để kiểm chứng hành vi mặc định. Dự án độc lập, không cần REST controller hay JPA. Bản Spring Framework do Spring Boot 3.3.x quản lý sử dụng quy tắc rollback truyền thống; đừng bật một chính sách rollback toàn cục khác khi chạy ví dụ này.

Cấu trúc file:

```text
checked-rollback-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/rollback/
    │   ├── RollbackDemoApplication.java
    │   ├── AuditService.java
    │   └── BusinessCheckedException.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

### 5.1. Gradle và cơ sở dữ liệu

**`settings.gradle`**

```groovy
rootProject.name = 'checked-rollback-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

Spring Boot starter JDBC cung cấp `JdbcTemplate` và transaction infrastructure; driver H2 được nạp lúc chạy. Không cần khai `spring-tx` riêng hoặc dùng Spring Data JPA cho bài kiểm chứng SQL trực tiếp này. Nếu dự án đang dùng BOM/version catalog khác, giữ Spring modules và driver tương thích với dự án đó.

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:rollbacklab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE audit_events (
    id BIGINT PRIMARY KEY,
    message VARCHAR(80) NOT NULL
);
```

H2 là database in-memory tồn tại trong JVM; mỗi lần chạy app mới bắt đầu từ một database rỗng. Spring Boot chạy `schema.sql` lúc khởi động. Không cần tạo bảng thủ công.

### 5.2. Exception nghiệp vụ

**`src/main/java/demo/rollback/BusinessCheckedException.java`**

```java
package demo.rollback;

public class BusinessCheckedException extends Exception {
    public BusinessCheckedException(String message) {
        super(message);
    }
}
```

Vì extends `Exception` và không extends `RuntimeException`, đây là checked exception.

### 5.3. Service với ba chính sách

**`src/main/java/demo/rollback/AuditService.java`**

```java
package demo.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void defaultChecked(long id) throws BusinessCheckedException {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "default"
        );
        throw new BusinessCheckedException("business rejected");
    }

    @Transactional(rollbackFor = BusinessCheckedException.class)
    public void explicitChecked(long id) throws BusinessCheckedException {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "explicit"
        );
        throw new BusinessCheckedException("business rejected");
    }

    @Transactional
    public void defaultUnchecked(long id) {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "runtime"
        );
        throw new IllegalStateException("runtime rejected");
    }
}
```

Mỗi method thử ghi một hàng vào database, rồi ném exception. Khác biệt nằm ở chính sách:

- `defaultChecked`: không khai `rollbackFor`. Checked exception không kích hoạt rollback theo mặc định truyền thống.
- `explicitChecked`: khai rõ `rollbackFor = BusinessCheckedException.class`.
- `defaultUnchecked`: dùng unchecked `IllegalStateException` để đối chiếu default rollback.

### 5.4. Runner gọi qua Spring proxy và quan sát sau khi transaction hoàn tất

**`src/main/java/demo/rollback/RollbackDemoApplication.java`**

```java
package demo.rollback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner verify(AuditService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + count(jdbc));

            try {
                service.defaultChecked(1L);
            } catch (BusinessCheckedException ex) {
                System.out.println("Default checked: " + ex.getMessage());
            }
            System.out.println("After default checked: " + count(jdbc));

            try {
                service.explicitChecked(2L);
            } catch (BusinessCheckedException ex) {
                System.out.println("Explicit checked: " + ex.getMessage());
            }
            System.out.println("After explicit rollback: " + count(jdbc));

            try {
                service.defaultUnchecked(3L);
            } catch (IllegalStateException ex) {
                System.out.println("Runtime: " + ex.getMessage());
            }
            System.out.println("After runtime rollback: " + count(jdbc));

            System.out.println(
                "Remaining ids: " +
                jdbc.queryForList("SELECT id FROM audit_events ORDER BY id",
                                  Long.class)
            );
        };
    }

    private static Integer count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_events", Integer.class);
    }
}
```

**Chạy ở thư mục project với Gradle Wrapper**:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giữa các log thông thường của Gradle/Spring Boot, những dòng chương trình in ra phải theo thứ tự:

```text
Before: 0
Default checked: business rejected
After default checked: 1
Explicit checked: business rejected
After explicit rollback: 1
Runtime: runtime rejected
After runtime rollback: 1
Remaining ids: [1]
```

Vì sao các con số chính xác?

1. Bảng ban đầu rỗng nên `COUNT(*) = 0`.
2. `defaultChecked(1)` chèn ID 1, ném checked exception; proxy chọn commit theo default. Caller bắt exception nhưng `COUNT(*)` lúc này là **1**.
3. `explicitChecked(2)` chèn ID 2 rồi ném **cùng loại checked exception**; rollback rule yêu cầu rollback. ID 2 không tồn tại sau khi method kết thúc, nên count vẫn **1**.
4. `defaultUnchecked(3)` chèn ID 3 rồi ném `IllegalStateException`; mặc định rollback, count vẫn **1**.
5. Chỉ ID 1 đã commit, nên `Remaining ids: [1]`.

Các đoạn Java là một ví dụ **Spring Boot project đầy đủ khi ghép đúng files và dependencies**; chạy bằng `bootRun`, không phải một file độc lập chạy chỉ bằng `javac`. Mỗi lần chạy từ một JVM mới, H2 in-memory khởi tạo lại; nếu tái sử dụng DB lâu dài, hãy quản lý reset dữ liệu trước khi thử lại.

**Lưu ý ranh giới:** `AuditService` là bean được inject từ Spring container; runner gọi vào service **qua proxy**. Runner không được đánh dấu `@Transactional` nên việc đếm diễn ra **sau khi proxy service đã quyết định commit/rollback**. Nếu đặt runner/test trong một transaction bao ngoài, tính độc lập và số đếm có thể khác.

## 6. Vì sao nên chọn rollback rule theo ý nghĩa nghiệp vụ?

Một checked exception thường mô tả **kết quả nghiệp vụ có thể dự đoán** chứ không phải lỗi hạ tầng. Ví dụ:

| Exception | Ý nghĩa có thể có | Chọn rollback? |
| --- | --- | --- |
| `InvalidOrderException` | Đơn không thể được chấp nhận; đã tạm giữ tồn kho | **Thường có**, để không để lại phần ghi chưa hoàn tất |
| `InsufficientFundsException` | Không thể trừ tiền; không muốn tạo giao dịch chuyển tiền dở dang | **Có** nếu transaction đã ghi thay đổi phải hủy |
| `EmailDeliveryException` | DB đã xác nhận đơn hàng nhưng gửi email thất bại | **Phụ thuộc**: thường không nên giữ transaction DB mở khi gọi email; xử lý qua outbox/after-commit |
| `ValidationWarningException` | Lưu một cảnh báo/biên bản audit có chủ đích rồi trả lời người gọi | **Có thể không**, nếu policy yêu cầu lưu trạng thái đã xử lý |
| `IOException` khi đọc file nhập | File bị hỏng giữa quá trình cập nhật nhiều bảng | **Có** nếu muốn nhập dữ liệu nguyên tử |
| `SQLException` nguyên bản từ JDBC | Lỗi DB | **Phụ thuộc** vào transaction/DB, nhưng thường cần rollback; Spring JDBC thường chuyển thành unchecked `DataAccessException` |

Không thể suy luận “mọi checked exception đều phải commit” hoặc “mọi checked exception đều phải rollback” mà không hiểu tài nguyên đã thay đổi và trạng thái được coi là thành công. Hãy mô tả **giao ước lỗi** ngay tại service boundary: exception nào bảo rằng nghiệp vụ thất bại và mọi ghi trong transaction phải hủy.

Một exception “thường là checked” vẫn có thể xuất hiện **sau khi external side effect** như HTTP/email đã hoàn tất. DB rollback không thu hồi được email hoặc cuộc gọi API đã gửi. Khi cần đồng bộ DB với thông báo, cân nhắc transactional outbox và xử lý sau commit; `rollbackFor` chỉ điều khiển tài nguyên do transaction manager phụ trách.

## 7. Những tình huống khiến khai `rollbackFor` vẫn chưa đạt mục tiêu

### 7.1. Exception bị bắt ngay trong transactional method

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() {
    try {
        callBusinessOperation();
    } catch (BusinessCheckedException ex) {
        logWarning(ex);
        // Method trả về bình thường: proxy không nhận exception.
    }
}
```

Đây là **mã minh họa** với `callBusinessOperation` và `logWarning` chưa định nghĩa. Nếu exception bị nuốt, rollback rule không tự được dùng vì không có exception thoát khỏi method. Những thay đổi DB trước đó **có thể commit** nếu transaction không bị đánh dấu rollback-only.

Cách thường tốt hơn là để exception phù hợp thoát lên service boundary:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() throws BusinessCheckedException {
    callBusinessOperation();
}
```

Khi cần ghi log, có thể catch để log **rồi rethrow** exception. Không dùng catch-and-ignore chỉ để tránh khai `throws`.

### 7.2. Chuyển checked exception sang unchecked exception

```java
@Transactional
public void process() {
    try {
        callExternalOperation();
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("Cannot process request", ex);
    }
}
```

Nếu `callExternalOperation` là một method ném IOException, đây là mẫu minh họa hợp lệ về cơ chế exception; `IllegalStateException` là unchecked nên mặc định Spring rollback. Tuy nhiên **đừng bọc exception thành runtime chỉ để điều khiển rollback** khi nghiệp vụ muốn giữ checked exception trong API; `rollbackFor = IOException.class` diễn đạt rõ hơn và giữ nguyên hợp đồng type.

### 7.3. Gọi nội bộ bean: proxy không chặn self-invocation

```java
@Service
public class WorkflowService {
    public void run() throws BusinessCheckedException {
        this.saveAndFail(); // Gọi trên chính instance, không đi qua proxy.
    }

    @Transactional(rollbackFor = BusinessCheckedException.class)
    public void saveAndFail() throws BusinessCheckedException {
        // Thao tác DB và throw checked exception.
    }
}
```

Nếu `run()` được gọi trực tiếp và không có transaction khác, `this.saveAndFail()` trong Spring AOP proxy mode thông thường **không kích hoạt advice** của `saveAndFail`. Khi kiểm tra, gọi method từ một bean khác qua injected proxy hoặc bố trí transaction ở public service boundary phù hợp. Không cho rằng annotation tự áp dụng cho mọi lời gọi Java.

### 7.4. Exception xuất hiện sau khi proxy đã trả về

```java
service.saveOrder(); // Transaction của saveOrder đã commit thành công.
throw new BusinessCheckedException("Later validation failed");
```

Nếu `saveOrder` tự mở và kết thúc transaction trước khi trở về, exception được ném từ caller sau đó **không rollback được giao dịch đã commit**. Muốn hai bước nằm trong một transaction, phải đặt transaction boundary ở service bao trùm các thao tác DB, đảm bảo lời gọi qua proxy, và cấu hình rollback phù hợp.

### 7.5. Transaction đang thuộc về caller

Với `Propagation.REQUIRED` (mặc định), method có thể **tham gia transaction hiện hữu** thay vì mở mới. Nếu một method con có `rollbackFor` và ném checked exception, transaction interceptor của method con có thể **đánh dấu transaction chia sẻ là rollback-only**. Caller bắt exception rồi cố commit vẫn có thể nhận `UnexpectedRollbackException`, vì transaction thực tế đã được đánh dấu phải rollback.

Ví dụ mô hình:

```text
outer @Transactional REQUIRED
    -> inner @Transactional(rollbackFor = BusinessCheckedException.class)
       (cùng transaction, lời gọi đi qua proxy inner)
    -> inner ném BusinessCheckedException
    -> inner interceptor đánh dấu rollback-only
    -> outer catch exception và trả về bình thường
    -> outer cố commit => không thể commit toàn transaction
       (có thể nhận UnexpectedRollbackException)
```

Mô tả này giả định hai method đi qua proxy và tham gia cùng transaction manager. Không thể “cứ catch là commit được” sau khi transaction đã rollback-only. Nếu dùng `REQUIRES_NEW`, method con có transaction độc lập, cần phân tích ranh giới riêng; không dùng propagation mới chỉ để che lỗi.

### 7.6. Bản thân DB từ chối commit

Một số lỗi SQL làm transaction database mất khả năng tiếp tục hoặc khiến ràng buộc chỉ được kiểm tra lúc commit. Ngay cả khi Spring chọn **no rollback** cho exception Java, commit vẫn có thể thất bại hoặc transaction đã bị đánh dấu rollback-only. Đừng viết test chỉ kiểm tra số exception; **đọc lại dữ liệu trên connection khác sau khi transaction thật sự hoàn tất**.

### 7.7. Annotation dùng sai nơi, thiếu transaction manager

`@Transactional` là metadata. Cần Spring transaction infrastructure và transaction manager đúng với tài nguyên được sử dụng. Với một service được tạo bằng `new` ngoài Spring container, method private, hoặc bean không nhận được proxy, rollback rule có thể không được áp dụng. Một transaction JDBC không tự bao gồm một connection được mở riêng bằng `DriverManager.getConnection(...)` bên trong method và không tự thành distributed transaction trên hai database độc lập.

## 8. Cấu hình XML cho checked exception

Nếu ứng dụng đang dùng transaction declarative qua XML, cơ chế tương đương `rollbackFor` là thuộc tính **`rollback-for` của `<tx:method>`**:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="processOrder"
                   propagation="REQUIRED"
                   rollback-for="demo.rollback.BusinessCheckedException"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* demo.rollback.service.*.*(..))"/>
    <aop:advisor pointcut-ref="serviceMethods"
                 advice-ref="txAdvice"/>
</aop:config>
```

Đây là **đoạn XML minh họa**, cần đặt trong `<beans>` đầy đủ namespace/schema và khai báo `transactionManager` + service beans. Luật `processOrder` quy định checked `BusinessCheckedException` kích hoạt rollback. Nếu service không thuộc pointcut hoặc lời gọi bỏ qua proxy, advice này không có tác dụng.

Khác biệt chính:

- Java annotation: `rollbackFor = BusinessCheckedException.class` kiểm tra type an toàn khi compile.
- XML: `rollback-for="demo.rollback.BusinessCheckedException"` là **chuỗi tên exception**; nên dùng tên đầy đủ và tránh pattern quá rộng như `"Exception"`.
- `no-rollback-for` tương đương mục đích với `noRollbackFor`.
- Một `<tx:method name="...">` được chọn theo tên method rồi Spring mới áp dụng rollback rules của transaction attribute đó. **Không trộn** thuộc tính của luật `processOrder` với fallback `*` khi nhiều mẫu khớp.

Nếu XML không dùng annotation, không bắt buộc có `<tx:annotation-driven/>`, nhưng bắt buộc transaction advice và AOP advisor được cấu hình đúng cho các service cần giao dịch. Đừng cài nhiều cơ chế advisor trùng nhau nếu chưa chủ động kiểm tra thứ tự và transaction manager.

## 9. Global rollback policy từ Spring Framework 6.2 trở lên

Spring Framework **6.2+** có lựa chọn chính sách rollback mặc định cho annotation-driven transactions:

```java
import static org.springframework.transaction.annotation.RollbackOn.ALL_EXCEPTIONS;

import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)
public class TransactionDefaultsConfig {
}
```

Với `ALL_EXCEPTIONS`, cả **checked exception** cũng kích hoạt rollback theo default của các transaction annotation mà infrastructure này xử lý. Rule cụ thể ở method, như `noRollbackFor`, vẫn có thể thay đổi kết quả cho những exception đã chỉ định. Lựa chọn này hữu ích nếu toàn ứng dụng có quy tắc “mọi exception là thất bại transaction”, nhưng cần đánh giá các luồng đã **cố tình commit khi ném checked exception** trước khi bật.

**Giới hạn phiên bản:** thuộc tính `rollbackOn` trên `@EnableTransactionManagement` và enum `RollbackOn` được bổ sung từ **Spring Framework 6.2**; **không copy đoạn code này vào ví dụ Spring Boot 3.3.x ở phần 5** (dùng Spring Framework 6.1) rồi kỳ vọng nó compile. Nếu ứng dụng dùng một phiên bản Spring khác, hãy kiểm tra API và chính sách thực tế trước khi chọn cách cấu hình toàn cục.

Một dự án bật chính sách toàn cục `ALL_EXCEPTIONS` **không còn cho kết quả** `After default checked: 1` như ví dụ phần 5; đây là thay đổi có chủ đích so với hành vi mặc định truyền thống. Không nên áp dụng lẫn cấu hình và kết luận của hai môi trường khác nhau.

## 10. Kiểm thử rollback đúng chỗ

Một test có giá trị phải kiểm tra cả **exception** lẫn **trạng thái DB sau khi transaction kết thúc**:

1. Tạo dữ liệu đầu vào đã biết, dùng một database có transaction.
2. Gọi service qua bean do Spring container quản lý, không trực tiếp `new Service`.
3. Đảm bảo test không mở một transaction bao ngoài ngoài chủ ý; `@Transactional` trên test thường làm Spring TestContext tự rollback cuối test, có thể che việc service đã commit/rollback thế nào.
4. Gây checked exception **sau một thao tác DB thành công** để phân biệt default commit và explicit rollback.
5. Bắt exception tại caller **bên ngoài service transaction**, rồi đọc lại DB.
6. Kiểm tra các trường hợp default checked, configured checked, unchecked, và nếu có chính sách đặc biệt thì `noRollbackFor`.
7. Nếu cần kiểm chứng trên PostgreSQL/MySQL, dùng đúng DB engine (ví dụ Testcontainers) vì H2 không mô phỏng hoàn toàn dialect/constraint/isolation/lock.

Bảng kỳ vọng đối với ví dụ phần 5:

| Phương thức | Exception | Rule áp dụng | ID còn lại sau lời gọi |
| --- | --- | --- | --- |
| `defaultChecked(1L)` | `BusinessCheckedException` | Default không rollback checked | `1` |
| `explicitChecked(2L)` | `BusinessCheckedException` | `rollbackFor = BusinessCheckedException.class` | Vẫn chỉ `1` |
| `defaultUnchecked(3L)` | `IllegalStateException` | Default rollback runtime | Vẫn chỉ `1` |

Nếu kết quả khác, kiểm tra **transaction proxy**, **transaction manager**, **global rollback policy**, **đường gọi**, **rollback-only**, **test transaction** và **lỗi commit** trước khi kết luận annotation không hoạt động.

### Quan sát transaction status để hỗ trợ debug

Trong code đang chạy trong thread-bound Spring transaction, có thể kiểm tra:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Đoạn trên chỉ minh họa cách kiểm tra `active`; nó không chứng minh commit đã xảy ra. `TransactionSynchronizationManager` quan sát trạng thái gắn với thread của transaction imperative. Khi dùng reactive transaction, việc truyền transaction context có cơ chế khác, không đơn giản là cùng thread-local.

### Khi cần đánh dấu rollback-only vì không thể rethrow

Trong trường hợp rất đặc biệt, code bắt checked exception rồi quyết định không ném nó nhưng vẫn bắt buộc rollback:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Trong một method đang được Spring transaction interceptor quản lý:
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

Đây là cách **programmatic** và phụ thuộc vào transaction advice đang tồn tại trên đường gọi. Không phải lời khuyên chung để thay cho `rollbackFor`; với nghiệp vụ có thể truyền exception ra ngoài, cấu hình declarative và rethrow thường dễ hiểu, dễ kiểm thử hơn.

## 11. Các sai lầm phổ biến cần tránh

| Nhận định/thiết kế sai | Vì sao sai | Cách làm rõ |
| --- | --- | --- |
| “`throws Exception` thì Spring tự rollback” | `throws` là hợp đồng Java, không phải rollback rule | Dùng `rollbackFor` khi checked exception phải hủy transaction |
| “Mọi exception đều rollback mặc định” | Mặc định truyền thống chỉ `RuntimeException`/`Error`; có thể có custom/global policy | Kiểm tra config cụ thể |
| “Bắt exception ở caller sẽ rollback được” | Caller có thể nhận exception **sau commit** của service | Kiểm tra transaction owner và thời điểm bắt |
| “Cứ catch rồi return là đủ an toàn” | Interceptor không nhìn thấy exception đã bị nuốt | Rethrow, hoặc đánh dấu rollback-only khi thật sự cần |
| “`rollbackForClassName="Exception"` khớp đúng class `Exception`” | Pattern là chuỗi con, dễ khớp ngoài ý muốn | Dùng `rollbackFor = BusinessException.class` |
| “Một DB UPDATE lỗi nhưng `noRollbackFor` sẽ ép commit” | DB có thể đã đánh dấu transaction lỗi/abort | Xử lý lỗi resource, không dùng rule để qua mặt DB |
| “Test có `@Transactional` giống production” | Test transaction có thể mở sẵn và tự rollback sau test | Kiểm tra ranh giới transaction riêng của test |
| “Gọi method annotated trong cùng object sẽ có advice” | Self-invocation bỏ qua proxy mode | Gọi qua Spring-managed proxy/service boundary |
| “Spring DB rollback sẽ hoàn tác email/API ngoài” | Side effect ngoài DB không thuộc local transaction | Dùng outbox, after-commit event, idempotency |
| “Mọi checked exception đều là lỗi nghiệp vụ cần rollback” | Một số trạng thái cần commit có chủ ý | Định nghĩa exception contract và rollback policy rõ |

## 12. Câu hỏi tự đánh giá

**1. `BusinessException extends Exception` được ném khỏi `@Transactional` mặc định sau khi JDBC đã INSERT. Chắc chắn rollback không?**  
Không. Với cấu hình rollback truyền thống, Spring không chọn rollback theo checked exception đó, nên có thể commit nếu transaction mới, DB khỏe và không có rollback-only. Cần `rollbackFor = BusinessException.class` nếu muốn rollback theo type.

**2. `@Transactional(rollbackFor = IOException.class)` có cần đổi `IOException` thành `RuntimeException` không?**  
Không. Spring được cấu hình để rollback khi checked `IOException` thoát khỏi method, còn API Java vẫn có checked exception.

**3. Vì sao `JdbcTemplate` gây lỗi SQL thường rollback dù `SQLException` là checked?**  
Vì Spring JDBC thường chuyển `SQLException` thành unchecked `DataAccessException`; loại thực tế đi tới transaction interceptor mới là thứ quyết định default rollback.

**4. Nếu method bắt `BusinessCheckedException` rồi return bình thường, `rollbackFor` có tự kích hoạt không?**  
Không, vì interceptor không nhận exception thoát ra; trừ khi transaction đã rollback-only vì một nguyên nhân khác.

**5. `noRollbackFor` có làm caller không nhận exception nữa không?**  
Không. Nó chỉ thay đổi quyết định rollback/commit khi transaction manager có thể commit; exception vẫn được truyền lên caller.

**6. Vì sao cần test ngoài transaction của service?**  
Để thấy quyết định commit/rollback **sau lời gọi qua proxy**, không bị transaction bao ngoài của test/caller làm lệch kết quả.

**7. Có phải Spring Framework 6.2+ bắt buộc rollback mọi checked exception mặc định không?**  
Không. `ALL_EXCEPTIONS` là **lựa chọn cấu hình toàn cục**, không phải mặc định truyền thống; khi bật, hành vi đối với checked exception khác đi.

## 13. Ghi nhớ và quy tắc thiết kế

**Checked exception không tự kéo theo rollback trong Spring transaction mặc định truyền thống.** Khi một checked exception phải hủy thao tác nghiệp vụ, viết rule rõ ràng, thường là **`@Transactional(rollbackFor = YourCheckedException.class)`**. Khi một exception vẫn cho phép commit, hãy chứng minh chủ đích đó bằng giao ước API và test.

Cách xác nhận chính sách rollback đúng gồm bốn câu hỏi liên tiếp:

1. **Lời gọi nào mở hoặc tham gia transaction?** Có đi qua Spring proxy và đúng transaction manager không?
2. **Loại exception thực sự thoát khỏi transactional boundary là gì?** Checked, unchecked, bị wrap hay đã bị catch?
3. **Rule nào quyết định kết quả?** Mặc định, `rollbackFor`, `noRollbackFor` hay lựa chọn rollback toàn cục?
4. **Database còn dữ liệu gì sau khi transaction kết thúc?** Đọc lại DB, không suy từ việc một SQL hay `save()` đã chạy.

Khi bốn câu trả lời này rõ ràng, bạn có thể thiết kế transaction atomicity đúng với ý nghĩa nghiệp vụ thay vì dựa vào những giả định về exception.

## Tài liệu đối chiếu

- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2, *Using @Transactional* — defaults, `rollbackFor` và global `rollbackOn`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework, *Declarative Transaction Implementation and Proxy*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *<tx:advice/> Settings*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework API, *RollbackRuleAttribute*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html
- Spring Framework API, *RollbackOn enum (since 6.2)*: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/RollbackOn.html
- Spring Boot 3.3, *SQL Databases*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot 3.3, *SQL Database Initialization*: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
