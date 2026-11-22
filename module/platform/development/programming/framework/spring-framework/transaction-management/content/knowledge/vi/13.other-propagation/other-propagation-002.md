# MANDATORY và yêu cầu bên gọi đã mở giao dịch

> **Chủ đề:** Spring Framework — Transaction Management. **Nhóm kiến thức:** Propagation khác. Bài này giải thích chính xác `Propagation.MANDATORY`: phương thức **bắt buộc** phải được gọi trong một transaction đang tồn tại, **không** tự tạo transaction mới khi thiếu transaction; khi đã có transaction thì **tham gia cùng transaction vật lý** và chịu chung kết quả commit/rollback. Bài có ví dụ Java 17, Spring Boot 3.5.7, Spring JDBC và H2 để kiểm chứng trực tiếp.

## 1. MANDATORY là gì?

Trong Spring, `@Transactional` cho phép điều chỉnh propagation — cách một method tham gia, khởi tạo hoặc từ chối transaction hiện có. `Propagation.MANDATORY` thể hiện một **điều kiện bắt buộc đối với caller**: caller phải đặt lời gọi trong transaction phù hợp **trước khi** đến method này.

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.MANDATORY)
public void reserveStock(long productId, int quantity) {
    // Code này yêu cầu có transaction đang tồn tại.
}
```

Khi lời gọi **thực sự đi qua Spring transaction interceptor**:

- **Đã có transaction phù hợp:** Spring cho method tham gia transaction đó. Method không tự tạo một physical transaction mới; commit/rollback cuối cùng do transaction bao ngoài quyết định.
- **Không có transaction:** Spring từ chối lời gọi và thường ném `org.springframework.transaction.IllegalTransactionStateException` **trước khi chạy thân method**.
- **Có annotation nhưng không đi qua proxy** (trong Spring AOP proxy mode): kiểm tra MANDATORY có thể **không hề diễn ra**, vì interceptor không được gọi.

Tài liệu API Spring mô tả ý nghĩa của `MANDATORY` là: hỗ trợ transaction hiện tại, báo lỗi nếu không có. Đây là **hợp đồng bắt buộc**, khác `REQUIRED` — vốn tự mở transaction khi thiếu.

### Tư duy đúng

Nếu lớp repository/service A có một thao tác chỉ được chạy trong quá trình nghiệp vụ lớn hơn, ta muốn **caller chịu trách nhiệm mở transaction**. `MANDATORY` biến kỳ vọng đó thành một kiểm tra có thể phát hiện lỗi cấu trúc ở runtime, thay vì vô tình chạy SQL auto-commit và chỉ phát hiện dữ liệu sai sau này.

**Tuy nhiên:** `MANDATORY` không xác minh “transaction phải được tạo bởi method cụ thể X” hay “transaction phải bảo vệ đúng tất cả database”. Nó chỉ kiểm tra có **transaction hiện có theo transaction manager đang được chọn**. Muốn bảo đảm danh tính caller, database hoặc business invariants phải kiểm soát bằng thiết kế, phân quyền, transaction manager/resource wiring và test.

## 2. Phân biệt MANDATORY với REQUIRED và REQUIRES_NEW

| Propagation của method được gọi | Khi chưa có transaction | Khi đã có transaction `T1` | Có thể commit độc lập trước outer? |
| --- | --- | --- | --- |
| `REQUIRED` — mặc định | Tạo transaction mới | Tham gia `T1` | Không nếu đang tham gia T1 |
| **`MANDATORY`** | **Ném lỗi, không chạy thân method** | **Tham gia `T1`** | **Không** |
| `REQUIRES_NEW` | Tạo transaction mới | Tạm ngưng T1 và tạo `T2` riêng | Có, vì T2 độc lập |
| `SUPPORTS` | Chạy không có transaction | Tham gia T1 | Không tự tạo |
| `NEVER` | Chạy không có transaction | Ném lỗi nếu tồn tại T1 | Không |
| `NOT_SUPPORTED` | Chạy không có transaction | Tạm ngưng T1, chạy ngoài transaction | Không |

Một nhầm lẫn phổ biến: thấy chữ **MANDATORY** và nghĩ nó “buộc Spring phải tạo giao dịch”. Không đúng. MANDATORY **buộc caller phải mang transaction vào**; nếu không có, nó **từ chối** chứ không tạo.

Ví dụ hai service:

```java
@Service
class CheckoutService {
    private final InventoryService inventory;

    CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional // REQUIRED, khi chưa có tx sẽ bắt đầu T1.
    public void checkout() {
        inventory.reserve(); // Gọi bean khác qua Spring proxy.
    }
}

@Service
class InventoryService {
    @Transactional(propagation = Propagation.MANDATORY)
    public void reserve() {
        // Tham gia T1 do checkout() mở.
    }
}
```

Đây là **trích đoạn minh họa**, cần import `org.springframework.stereotype.Service` và các annotation transaction; chưa phải chương trình độc lập. Khi `checkout` được gọi **qua proxy** từ một caller không có transaction, `checkout` mở T1, `reserve` tham gia chính T1. **Không có T2.**

Ngược lại, nếu một controller hoặc job gọi **trực tiếp** `InventoryService.reserve()` qua proxy nhưng chưa có transaction, MANDATORY sẽ từ chối trước khi thao tác database diễn ra.

## 3. Logical transaction scope và physical transaction

Để hiểu commit/rollback của MANDATORY, cần phân biệt:

- **Physical transaction:** giao dịch thật của tài nguyên như JDBC connection/DB transaction, có begin, commit và rollback.
- **Logical transaction scope:** phạm vi transaction do Spring interceptor xử lý cho một phương thức transactional; nó mang metadata, quy tắc rollback và có thể tham gia physical transaction đã mở.

Một method outer `@Transactional(REQUIRED)` và inner `@Transactional(MANDATORY)` được intercept tạo **hai phạm vi logic** nhưng thông thường chỉ có **một physical transaction T1**.

```text
Controller / Runner
    |
    v
OrderService.placeOrder()            @Transactional(REQUIRED)
    |                                      |
    |                          logical scope OUTER
    |                          BEGIN physical transaction T1
    |
    +--> InventoryService.reserve()   @Transactional(MANDATORY)
    |         |                            |
    |         |                 logical scope INNER
    |         |                 REQUIRE existing transaction
    |         |                 JOIN physical transaction T1
    |         +---- SQL trên cùng T1 -----> |
    |
    +--------- SQL trên T1 --------------> |
    |
    v
Outer kết thúc: COMMIT hoặc ROLLBACK physical transaction T1
```

**MANDATORY không commit T1 khi inner method trả về.** Kết thúc inner thành công chỉ có nghĩa phần công việc của inner đã trở về outer scope. Nếu outer về sau ném `RuntimeException` và rollback T1, các thay đổi do inner đã thực hiện trong T1 cũng rollback.

Điều này hợp với các bước nghiệp vụ phải **atomic cùng nhau** như ghi đơn hàng và trừ tồn kho trên cùng datasource; nhưng nếu inner thực sự cần commit độc lập để giữ dữ liệu khi outer rollback, `MANDATORY` không đáp ứng, và một boundary `REQUIRES_NEW` có chủ ý có thể phù hợp hơn.

## 4. Không có transaction thì chuyện gì xảy ra?

Xét method:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void writeAuditRow() {
    jdbc.update("INSERT INTO audit_log(id) VALUES (1)");
}
```

Đây là **trích đoạn**: `jdbc` là `JdbcTemplate` đã được inject vào bean có transaction advice. Nếu được gọi trực tiếp **qua Spring proxy** khi không có transaction:

1. Caller đi vào transaction interceptor.
2. Spring xác định transaction manager/transaction attribute tương ứng.
3. Manager thấy propagation `MANDATORY` nhưng không có transaction hiện hữu phù hợp.
4. Nó ném `IllegalTransactionStateException`. **Thân method không được chạy**, vì vậy câu `INSERT` không thực hiện.
5. Không có commit hay rollback của method này, bởi **không có transaction mới nào được bắt đầu**.

Lỗi này thường là **tín hiệu thiết kế sai ranh giới transaction**, không phải lý do để tự động đổi `MANDATORY` thành `REQUIRED` ở mọi nơi.

### Có thể dùng try/catch không?

```java
try {
    inventoryService.reserve();
} catch (IllegalTransactionStateException ex) {
    // Báo lỗi cấu trúc giao dịch; không coi là reserve thành công.
}
```

Đây là trích đoạn chẩn đoán; cần import `org.springframework.transaction.IllegalTransactionStateException`. Bắt exception có thể giúp chuyển lỗi thành phản hồi/diagnostic có nghĩa, nhưng **không thể biến thao tác đã bị từ chối thành thao tác hoàn tất**. Đừng nuốt lỗi rồi trả về success.

Nếu đúng nghiệp vụ cho phép lời gọi độc lập, có thể thiết kế một method outer `@Transactional(REQUIRED)` để mở transaction, rồi gọi inner `MANDATORY`. Không nên bắt buộc mọi caller tự nhớ mở transaction thủ công bằng JDBC connection.

## 5. Hợp đồng caller: ai chịu trách nhiệm mở transaction?

Một thiết kế dễ duy trì chia hai tầng:

1. **Orchestration/application service:** chịu trách nhiệm điều phối nghiệp vụ và mở transaction cho toàn quy trình; thường dùng `@Transactional` mặc định `REQUIRED`.
2. **Participant service:** có những operation **chỉ hợp lệ bên trong transaction đã mở**; dùng `MANDATORY` để phát hiện lời gọi sai hợp đồng.

Ví dụ:

```java
@Service
class OrderApplicationService {
    private final OrderWriter orderWriter;
    private final StockWriter stockWriter;

    OrderApplicationService(OrderWriter orderWriter,
                            StockWriter stockWriter) {
        this.orderWriter = orderWriter;
        this.stockWriter = stockWriter;
    }

    @Transactional
    public void placeOrder(long orderId) {
        orderWriter.save(orderId);
        stockWriter.reserve(orderId);
    }
}

@Service
class StockWriter {
    @Transactional(propagation = Propagation.MANDATORY)
    public void reserve(long orderId) {
        // SQL trừ tồn kho.
    }
}
```

**Chỉ là trích đoạn thiết kế:** `OrderWriter` là component do ứng dụng định nghĩa; các class không phải một file Java độc lập. Nếu mọi write đều dùng **cùng JDBC DataSource** và đúng transaction manager, khi `placeOrder` rollback, `reserve` rollback cùng. Nếu controller gọi `stockWriter.reserve` trực tiếp mà không có T1, đó là một **lỗi hợp đồng** và được phát hiện sớm.

### MANDATORY không biến hệ thống thành bảo đảm giao dịch xuyên mạng

Transaction T1 là transaction của tài nguyên mà manager điều khiển. Nếu `reserve()` gọi HTTP sang service khác, MANDATORY **không tự gia nhập transaction vật lý của service B**. Nếu `OrderWriter` và `StockWriter` dùng các transaction managers/datasources khác nhau, “cùng call stack” không đồng nghĩa “cùng physical transaction”. Thiết kế XA/2PC, saga/outbox/idempotency là chủ đề khác; ở đây cần giữ rõ ranh giới cục bộ.

## 6. Khi inner MANDATORY thất bại: rollback-only và UnexpectedRollbackException

`MANDATORY` tham gia T1, vì vậy cần đặc biệt chú ý **rollback-only**.

Giả sử outer mở T1 và gọi inner qua **proxy của bean khác**:

```java
@Transactional
public void outer() {
    orders.insert(10); // SQL minh họa trong T1.
    try {
        inventory.reserveAndFail(); // @Transactional(MANDATORY)
    } catch (IllegalStateException ex) {
        // Outer bắt lỗi và muốn tiếp tục.
    }
    orders.insert(11); // Vẫn chạy được trong một số trường hợp.
}
```

Nếu `reserveAndFail()` ném `IllegalStateException` (unchecked) **thoát qua interceptor của inner**:

- Inner logical scope theo rollback rule mặc định quyết định rollback.
- Vì MANDATORY **không tạo T2** mà đang tham gia T1, với transaction manager cục bộ mặc định, nó thường đánh dấu physical transaction T1 là **rollback-only**.
- Outer bắt exception chỉ xử lý **dòng điều khiển Java**. Việc bắt lỗi **không tự xóa** rollback-only.
- Khi outer trả về bình thường và interceptor cố commit T1, Spring rollback thay vì commit. Caller của outer thường nhận `UnexpectedRollbackException`: thông báo rằng commit dự kiến không thực sự diễn ra.

Không phải mọi exception được bắt đều bảo đảm nhận `UnexpectedRollbackException`: điều này phụ thuộc rollback rules, inner có đi qua proxy hay không, cấu hình manager (chẳng hạn `globalRollbackOnParticipationFailure`), lỗi tài nguyên và trạng thái rollback-only. Bài demo ở dưới dùng `JdbcTransactionManager` mặc định để thể hiện kết quả.

### Exception thoát khỏi outer

Nếu outer **không bắt** unchecked exception của inner, exception tiếp tục thoát khỏi outer. Outer interceptor cũng thấy lỗi và rollback T1. Trong trường hợp này caller có thể thấy **exception gốc** thay vì `UnexpectedRollbackException` (vì outer không hề cố commit sau khi nuốt lỗi).

### Checked exceptions và rollback rules

Theo mặc định thường dùng của Spring, unchecked `RuntimeException` và `Error` gây rollback, còn checked exception như `IOException` **không** mặc định gây rollback. Có thể cấu hình:

```java
@Transactional(
    propagation = Propagation.MANDATORY,
    rollbackFor = IOException.class
)
public void importDetails() throws IOException {
    // Khi IOException thoát qua interceptor, Spring áp dụng rollback rule.
}
```

Đây là **trích đoạn**, cần import `java.io.IOException`, `Propagation` và `Transactional`. Vì method tham gia T1, rollback rule này có thể ảnh hưởng **physical transaction chung**, không chỉ riêng các câu SQL của inner. Không dùng `noRollbackFor` như một giải pháp chung để “ngăn rollback toàn bộ” khi data đã mất tính nhất quán.

### Inner method gọi mà không qua proxy

Nếu outer gọi `this.innerMandatory()` trong **cùng bean**, transaction interceptor **không thấy** annotation của inner trong Spring AOP proxy mode. Inner có thể vẫn làm việc trong transaction outer nếu outer đang có T1, nhưng các rollback rules / propagation attribute **riêng của inner** không được áp dụng qua lời gọi nội bộ đó.

Vì thế cần kiểm tra cả **physical transaction** lẫn **đường gọi qua proxy** trước khi quy lỗi cho MANDATORY.

## 7. MANDATORY không tạo transaction riêng cho isolation, timeout và readOnly

Ví dụ một method participant khai báo:

```java
@Transactional(
    propagation = Propagation.MANDATORY,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void readConsistentReport() {
    // Chạy trong transaction đang có, không mở T2.
}
```

Đây là **trích đoạn**; cần import `org.springframework.transaction.annotation.Isolation`, `Propagation` và `Transactional`.

Vì MANDATORY **chỉ tham gia transaction đã mở**:

- `isolation = SERIALIZABLE` ở inner **không tự nâng** isolation của physical transaction ngoài lên SERIALIZABLE.
- `timeout = 5` ở inner **không reset** hạn chót của transaction ngoài. Timeout của transaction đã mở vẫn chi phối.
- `readOnly = true` ở inner **không tự biến** transaction ngoài đang read-write thành một physical read-only transaction.
- Những attribute riêng liên quan tới bắt đầu transaction mới thường **chỉ có ý nghĩa ở boundary thực sự tạo transaction**.
- **Rollback rules của inner** vẫn có ý nghĩa tại logical scope: khi exception phù hợp thoát ra, interceptor có thể đánh dấu physical transaction chung rollback-only.

Spring có chế độ validate existing transaction, ví dụ `setValidateExistingTransaction(true)` trên transaction manager thích hợp. Khi bật, mức isolation không tương thích hoặc một inner read-write cố tham gia outer read-only có thể bị **từ chối** thay vì bị bỏ qua. Điều đó là **validation**, không phải hành động tạo transaction mới hay đổi transaction đã mở.

### MANDATORY tham gia transaction nào nếu có nhiều tầng?

Method tham gia **transaction hiện đang hoạt động** theo manager/resource của nó. Ví dụ outer T1 gọi một method `REQUIRES_NEW` mở T2, rồi method trong T2 gọi participant `MANDATORY` qua proxy: participant sẽ tham gia **T2**, không phải T1 đã bị suspend. MANDATORY **không biết và không kiểm tra “người mở transaction đúng là OrderService”**.

Vì vậy nếu nghiệp vụ yêu cầu participant chỉ được gọi ở một workflow xác định, phải có lớp API/authorization/business validation và test tương ứng; `MANDATORY` chỉ kiểm tra hiện diện transaction.

## 8. Dự án Java 17 chạy được: MANDATORY chặn caller không có transaction

Mục tiêu thực hành: dùng Spring Boot 3.5.7 (Spring Framework 6.2), Java 17, Maven, H2 và `JdbcTransactionManager`. Kiểm chứng bốn tình huống:

1. **Không có T1:** gọi inner `MANDATORY` trực tiếp qua proxy → `IllegalTransactionStateException`; method body không chạy.
2. **Có T1, cả hai thành công:** outer `REQUIRED` gọi inner `MANDATORY` → hai INSERT commit cùng nhau.
3. **Outer thất bại sau inner thành công:** outer throw unchecked exception → cả hai INSERT rollback.
4. **Inner thất bại, outer bắt exception:** inner tham gia T1, đánh dấu rollback-only → outer không commit được và caller nhận `UnexpectedRollbackException`.

Không dùng sleep hay query timeout để đánh giá MANDATORY; tiêu chí đáng tin là **dữ liệu DB còn lại và exception đúng ranh giới**.

### 8.1. Cấu trúc dự án

```text
mandatory-transaction-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/mandatory/
        │       ├── MandatoryApplication.java
        │       ├── OuterService.java
        │       └── MandatoryService.java
        └── resources/
            └── application.properties
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>vn.example</groupId>
    <artifactId>mandatory-transaction-demo</artifactId>
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

`spring-boot-starter-jdbc` mang thư viện Spring JDBC và transaction infrastructure. `h2` là database in-memory, không cần cài riêng. Spring Boot tự cấu hình `DataSource`, `JdbcTemplate` từ properties; ở đây ta khai báo transaction manager JDBC tường minh để biết rõ manager nào kiểm soát transaction.

### 8.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:mandatory_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` làm database in-memory còn tồn tại giữa các connection trong cùng JVM. Demo tạo bảng bằng `JdbcTemplate` trước khi chạy service; transaction manager JDBC và `JdbcTemplate` dùng cùng nguồn dữ liệu.

### 8.4. `src/main/java/vn/example/mandatory/MandatoryService.java`

```java
package vn.example.mandatory;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MandatoryService {

    private final JdbcTemplate jdbc;

    public MandatoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void insertThenFail(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
        throw new IllegalStateException("Inner operation failed");
    }
}
```

Cả hai method đều là **public** trên bean `@Service` để Spring transaction proxy có thể intercept. `insert` chỉ hợp lệ khi transaction hiện có; `insertThenFail` cố ý ném unchecked exception **sau** câu SQL nhằm kiểm chứng rollback-only.

`MandatoryService` không sở hữu quyết định commit cuối cùng. Nó là participant tham gia transaction do caller tạo.

### 8.5. `src/main/java/vn/example/mandatory/OuterService.java`

```java
package vn.example.mandatory;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {

    private final JdbcTemplate jdbc;
    private final MandatoryService participant;

    public OuterService(JdbcTemplate jdbc, MandatoryService participant) {
        this.jdbc = jdbc;
        this.participant = participant;
    }

    @Transactional
    public void commitBoth() {
        insertOuter(10, "outer-commit");
        participant.insert(11, "inner-commit");
    }

    @Transactional
    public void rollbackBoth() {
        insertOuter(20, "outer-rollback");
        participant.insert(21, "inner-rollback");
        throw new IllegalStateException("Outer operation failed");
    }

    @Transactional
    public void catchInnerFailure() {
        insertOuter(30, "outer-before-inner-error");
        try {
            participant.insertThenFail(31, "inner-error");
        } catch (IllegalStateException expected) {
            // Exception Java đã được bắt, nhưng rollback-only còn đó.
        }
        insertOuter(32, "outer-after-inner-error");
        // Method trả về bình thường; commit T1 vẫn không thành công.
    }

    private void insertOuter(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
    }
}
```

Vì `OuterService` inject **Spring-managed MandatoryService** qua constructor, các lời gọi `participant.insert(...)` và `participant.insertThenFail(...)` đi qua **proxy bean khác**, không phải `this.innerMethod()`.

Các method outer không nêu propagation nên mặc định là `REQUIRED`. Khi runner gọi từ bên ngoài transaction, mỗi outer method tạo một T1. Inner `MANDATORY` tham gia cùng T1; không có thêm T2 nào.

### 8.6. `src/main/java/vn/example/mandatory/MandatoryApplication.java`

```java
package vn.example.mandatory;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class MandatoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MandatoryApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc,
                           MandatoryService participant,
                           OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE journal_entries (" +
                "id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)"
            );

            try {
                participant.insert(1, "direct-without-transaction");
                throw new AssertionError("MANDATORY should reject no tx");
            } catch (IllegalTransactionStateException expected) {
                System.out.println(
                    "direct=IllegalTransactionStateException"
                );
            }
            System.out.println("directRows=" + count(jdbc, 1));

            outer.commitBoth();
            System.out.printf("committed=%d,%d%n",
                count(jdbc, 10), count(jdbc, 11));

            try {
                outer.rollbackBoth();
                throw new AssertionError("Expected outer failure");
            } catch (IllegalStateException expected) {
                // Outer T1 đã rollback.
            }
            System.out.printf("outerRollback=%d,%d%n",
                count(jdbc, 20), count(jdbc, 21));

            try {
                outer.catchInnerFailure();
                throw new AssertionError("Expected rollback-only");
            } catch (UnexpectedRollbackException expected) {
                System.out.println(
                    "innerCaught=UnexpectedRollbackException"
                );
            }
            System.out.printf("innerCaughtRows=%d,%d,%d%n",
                count(jdbc, 30), count(jdbc, 31), count(jdbc, 32));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM journal_entries WHERE id = ?",
            Integer.class, id
        );
    }
}
```

**Vì sao kết quả đáng tin trong cấu hình demo?**

- `@EnableTransactionManagement(proxyTargetClass = true)` bật transaction advice bằng class-based proxy.
- `JdbcTransactionManager` quản lý transaction JDBC cho một bean `DataSource` mà `JdbcTemplate` cũng dùng.
- `CommandLineRunner` là caller khác bean, không được gắn `@Transactional`; chính nó gọi `MandatoryService` trực tiếp khi không có T1, và gọi `OuterService` qua proxy cho các ca còn lại.
- `IllegalTransactionStateException` được Spring ném **trước khi vào `participant.insert`** ở lần gọi trực tiếp.
- Trong `catchInnerFailure`, manager `JdbcTransactionManager` mặc định đánh dấu physical transaction rollback-only sau lỗi unchecked ở scope inner tham gia.
- Dữ liệu được đọc lại **sau khi các lời gọi outer kết thúc**, không dùng chính transaction thất bại để phán đoán kết quả.

### 8.7. Lệnh chạy

Từ thư mục `mandatory-transaction-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/mandatory-transaction-demo-1.0.0.jar
```

Các dòng **do chương trình demo chủ động in** khi chạy với Spring Boot 3.5.7/H2/JDBC manager như trên là:

```text
direct=IllegalTransactionStateException
directRows=0
committed=1,1
outerRollback=0,0
innerCaught=UnexpectedRollbackException
innerCaughtRows=0,0,0
```

Spring Boot có thể in thêm log startup, HikariCP và shutdown; bảng trên chỉ mô tả **stdout nghiệp vụ chủ động** từ code.

### 8.8. Đọc từng dòng kết quả

| Output | Ý nghĩa |
| --- | --- |
| `direct=IllegalTransactionStateException` | MANDATORY từ chối caller không có transaction. |
| `directRows=0` | Thân `MandatoryService.insert(1, ...)` không chạy. |
| `committed=1,1` | Outer và inner cùng commit thành công trong T1. |
| `outerRollback=0,0` | Outer rollback T1 kéo theo các SQL đã chạy trong inner MANDATORY. |
| `innerCaught=UnexpectedRollbackException` | Inner MANDATORY đã đặt T1 rollback-only; outer bắt lỗi rồi cố commit nhưng không thể. |
| `innerCaughtRows=0,0,0` | Cả thao tác outer trước lỗi, inner lúc lỗi và outer sau catch đều rollback. |

Đây là lý do thực tế để dùng MANDATORY: caller buộc phải chủ động chọn transaction boundary, inner không tự mở giao dịch riêng hay tự commit. Đồng thời, nó giúp phát hiện caller vô tình gọi participant ở sai tầng.

## 9. Lưu ý về self-invocation, proxy và vòng đời bean

### 9.1. Self-invocation có thể vô hiệu hóa MANDATORY

```java
@Service
class BadBoundary {
    public void startWithoutTransaction() {
        mandatoryStep(); // Gọi nội bộ this.mandatoryStep().
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void mandatoryStep() {
        // Trong proxy mode, annotation không được áp dụng qua self-call.
    }
}
```

Đây là **trích đoạn**, không phải chương trình đầy đủ. Nếu `startWithoutTransaction()` được gọi bên ngoài mà không có transaction, `mandatoryStep()` có thể vẫn chạy **mà không ném `IllegalTransactionStateException`**, vì lời gọi không qua interceptor. Đó không phải Spring “cho phép MANDATORY chạy sai”; đó là **bạn đã bỏ qua proxy**.

**Cách sửa thường đơn giản:** tách method participant sang một bean Spring khác hoặc đặt transaction boundary ở public method được caller ngoài bean gọi qua proxy. Hạn chế dùng self-proxy hack nếu thiết kế có thể tách trách nhiệm rõ hơn.

### 9.2. Annotation trên private/final method

Class-based proxy không override được `private`/`final` method; JDK proxy chỉ cung cấp các public interface methods. Với Spring Framework 6.x, class-based proxy có thể xét non-public method phù hợp khi gọi qua proxy, nhưng không khiến private/final được intercept. Với MANDATORY, hậu quả có thể nghiêm trọng: **mất bước kiểm tra có transaction**.

Vì vậy, đối với nghiệp vụ phải bảo đảm gọi trong transaction, một **public method trên Spring-managed bean riêng** là boundary dễ lý giải và dễ kiểm thử nhất.

### 9.3. Constructor, @PostConstruct và đối tượng tạo bằng new

Đừng gọi method transaction MANDATORY trong constructor, `@PostConstruct` hoặc trên object tự `new` rồi mong Spring proxy mặc nhiên chạy. Vào thời điểm construction/initialization, proxy có thể chưa sẵn; object tạo thủ công không phải bean proxy. Hãy gọi sau khi context khởi tạo qua bean được Spring inject, hoặc sử dụng transaction API chương trình khi cần.

## 10. Khi nào MANDATORY hợp lý, khi nào không?

### Phù hợp

- Thao tác ghi **không được phép commit độc lập** khỏi quy trình ngoài.
- Module service được thiết kế rõ là **participant**, outer service chịu trách nhiệm orchestration và transaction boundary.
- Cần phát hiện sớm lời gọi sai từ controller, scheduler hoặc batch job chưa mở transaction.
- Có cùng transaction manager/resource và mong muốn rollback **tất cả** dữ liệu nghiệp vụ nếu một bước thất bại.

Ví dụ mô hình:

```text
CheckoutService.checkout()       REQUIRED: mở T1
  ├── OrderWriter.save()         MANDATORY: join T1
  ├── StockWriter.reserve()      MANDATORY: join T1
  └── LedgerWriter.record()      MANDATORY: join T1
                                 |
                                 v
                    T1 commit hoặc rollback cùng nhau
```

Lưu ý: dù ba method cùng đặt MANDATORY, chúng chỉ thật sự có chung physical transaction khi cùng transaction manager và kết nối/tài nguyên được cấu hình phù hợp.

### Không phù hợp

- Method vừa cần được caller trong transaction dùng, **vừa** cần tự hoạt động độc lập từ job/CLI không có transaction. `REQUIRED` có thể hợp lý hơn, hoặc cung cấp API outer riêng để mở transaction.
- Inner cần **commit ngay** dù outer rollback. `REQUIRES_NEW` mới cung cấp transaction độc lập; MANDATORY không làm vậy.
- Inner cần rollback riêng một phần bằng savepoint; xem xét `NESTED` khi JDBC driver/manager hỗ trợ, nhưng đó là cơ chế khác.
- Code chủ yếu là HTTP/gRPC, message broker hoặc thao tác ngoài database mà transaction manager không quản lý. MANDATORY không biến remote side effects thành ACID.
- Dùng nhiều transaction managers/datasources nhưng không xác định rõ manager phù hợp; chỉ kiểm tra “có transaction” ở một manager không chứng minh mọi tài nguyên đang tham gia.

## 11. Khi có nhiều transaction managers

Một annotation có thể chọn manager tường minh:

```java
@Transactional(
    transactionManager = "ordersTransactionManager",
    propagation = Propagation.MANDATORY
)
public void updateOrderLine() {
    // Cần đúng Orders DataSource/repository.
}
```

Đây là **trích đoạn**, giả định bean `ordersTransactionManager` tồn tại. MANDATORY xét transaction hiện có **tương thích với manager đó**. Một transaction cho `paymentsTransactionManager` **không tự động** trở thành transaction của `ordersTransactionManager`, ngay cả khi cùng calling thread.

Nếu một service được gọi với T1 của manager A nhưng trong method tham gia manager B, phải hiểu chính xác transaction đang được kiểm tra, data source nào được lấy connection và cách chọn manager. Không cố “sửa” lỗi bằng cách đổi mọi method thành `REQUIRED` nếu điều đó khiến dữ liệu chạy trên hai physical transactions độc lập mà bạn lại tưởng là atomic.

Một số kiến trúc sử dụng `JtaTransactionManager`, JPA transaction manager hoặc reactive transaction manager. Semantics chung của MANDATORY vẫn là **yêu cầu transaction hiện có**, nhưng cách manager phát hiện transaction, tài nguyên tham gia và khả năng suspend/rollback phụ thuộc integration cụ thể.

## 12. Trường hợp caller suspend transaction trước khi gọi MANDATORY

Có outer T1 không có nghĩa **mọi call stack con** đều còn T1. Nếu đi vào một scope `NOT_SUPPORTED`, transaction manager có thể **tạm ngưng** T1 rồi chạy code bên trong ngoài transaction.

```java
@Service
class NonTransactionalStep {
    private final MandatoryService mandatory;

    NonTransactionalStep(MandatoryService mandatory) {
        this.mandatory = mandatory;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void callMandatoryOutsideTx() {
        mandatory.insert(77, "invalid");
    }
}
```

Đây là **trích đoạn**, giả định có class `MandatoryService` như demo. Khi `callMandatoryOutsideTx()` được gọi **qua proxy** lúc T1 đã hoạt động, nó yêu cầu suspend T1. Lời gọi `mandatory.insert(...)` qua proxy trong scope bị suspend sẽ không có transaction phù hợp và MANDATORY ném `IllegalTransactionStateException`. Spring sẽ khôi phục transaction đã suspend khi xử lý kết thúc scope theo cơ chế manager.

**Điểm quan trọng:** “caller ban đầu từng mở transaction” là chưa đủ. MANDATORY cần transaction **đang hoạt động tại thời điểm interceptor của method tham gia**. T1 bị suspend không đáp ứng điều kiện đó.

Nếu một method `REQUIRES_NEW` đã mở T2 và gọi MANDATORY, MANDATORY sẽ tham gia T2 mới. Nó không biết đến T1 đang bị suspend phía ngoài.

## 13. MANDATORY trong các mô hình không cùng thread hoặc reactive

### Imperative / JDBC

Với `JdbcTransactionManager` hay `DataSourceTransactionManager`, transaction context imperative thường được giữ trong **ThreadLocal** của Spring. T1 từ thread request không tự động truyền sang một `new Thread(...)`, thread pool hay `@Async`.

Ví dụ **trích đoạn cảnh báo**:

```java
@Transactional
public void submitAsync() {
    executor.execute(() -> {
        mandatoryService.insert(99, "async");
    });
}
```

Giả định `executor` và `mandatoryService` là các dependency ứng dụng, còn lời gọi worker thread đi qua proxy. MANDATORY ở thread worker có thể ném `IllegalTransactionStateException` vì nó **không thấy** T1 của thread gọi, dù `submitAsync()` đang trong transaction.

Nếu thread worker thật sự cần transaction, hãy tạo transaction boundary riêng **tại nơi worker chạy**, có propagation phù hợp; không cố chia sẻ một JDBC connection/transaction thread-bound tùy tiện giữa threads.

### Reactive

Với `ReactiveTransactionManager`, context giao dịch thường ở **Reactor Context**, không phải ThreadLocal imperative. MANDATORY trong reactive pipeline vẫn yêu cầu transaction hiện có theo manager/reactive context; đổi scheduler hoặc tách publisher khỏi pipeline không đúng có thể khiến context bị mất. Không lấy ví dụ JDBC imperative làm bằng chứng rằng transaction tự đi qua mọi reactive publisher.

### Remote services

Một HTTP/gRPC request gửi sang service B không mang physical database transaction JDBC của service A. Nếu B có endpoint gọi method MANDATORY, B phải có transaction context **ở phía B** hoặc lời gọi bị từ chối; `@Transactional` ở service A không tự lan sang B. Không coi MANDATORY là bảo đảm atomic xuyên microservices.

## 14. Cách kiểm tra một MANDATORY boundary thật sự hoạt động

### 14.1. Dùng `TransactionSynchronizationManager` để chẩn đoán

Trong method participant:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

System.out.println("active=" + active);
```

Đây là **trích đoạn**, import `org.springframework.transaction.support.TransactionSynchronizationManager`. Nếu call được intercept, có transaction T1 phù hợp và method đang chạy, `active=true` thường đúng. Nhưng **active=true không chứng minh MANDATORY đã được advice**: method không được intercept vẫn có thể thấy transaction do outer mở.

Vì vậy cần **hai phép thử tách biệt**:

- Gọi MANDATORY qua proxy **không có transaction** → phải có lỗi `IllegalTransactionStateException` trước khi SQL chạy.
- Gọi MANDATORY qua proxy **có transaction** và sau đó làm outer rollback → SQL inner phải rollback cùng outer.

Hai phép thử này xác minh cả **ràng buộc đầu vào** và **việc tham gia physical transaction**.

### 14.2. Bật log để quan sát transaction interceptor

Trong môi trường dev/test có thể dùng:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Các log có thể giúp thấy method nào đi qua transaction advice và manager bắt đầu/tham gia/kết thúc transaction. Không dựa chỉ vào log nếu dữ liệu DB cho thấy kết quả khác, và tránh log chi tiết dữ liệu nhạy cảm ở production.

### 14.3. Cẩn thận với Spring TestContext

Một test method có `@Transactional` có thể được Spring TestContext mở một **test-managed transaction** trước khi gọi service. Lúc đó, direct invocation `MANDATORY` trong test **có transaction**, nên không ném exception. Nếu muốn kiểm thử lỗi “không có transaction”, test method phải **không bị bao bởi transaction test**, hoặc điều khiển transaction của test rõ bằng API phù hợp.

Tương tự, test tự rollback cuối cùng có thể che khuất việc outer service boundary có thực sự commit/rollback như bạn tưởng. Hãy thiết kế test vừa kiểm tra trạng thái transaction vừa đọc dữ liệu từ ranh giới phù hợp **sau lời gọi**.

## 15. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận hoặc lỗi | Điều đúng cần nhớ | Cách xử lý |
| --- | --- | --- |
| “MANDATORY luôn tạo transaction.” | Nó **yêu cầu transaction đã có**; thiếu thì ném lỗi. | Đặt `@Transactional(REQUIRED)` ở outer boundary hoặc đổi hợp đồng nếu cần standalone. |
| “Inner có MANDATORY sẽ commit trước outer.” | MANDATORY **tham gia T1**, không có T2. | Để outer quyết định commit/rollback; dùng `REQUIRES_NEW` chỉ nếu thực sự cần độc lập. |
| “Controller gọi MANDATORY trực tiếp vẫn chạy.” | Nếu không có T1 và call qua proxy, Spring từ chối. | Controller gọi orchestration service mở transaction. |
| “Bắt inner exception xong outer chắc chắn commit.” | Inner có thể đã đánh dấu T1 rollback-only. | Xác định rollback rules; xử lý contract lỗi; test `UnexpectedRollbackException`. |
| “isActualTransactionActive=true chứng minh annotation MANDATORY chạy.” | Không chứng minh advice của chính method. | Test call ngoài transaction và rollback thực tế. |
| “`this.innerMandatory()` cũng kiểm tra MANDATORY.” | Self-invocation bypass proxy mode. | Tách bean, gọi Spring-injected proxy. |
| “Timeout/isolation ở MANDATORY tự thay đổi T1.” | MANDATORY không tạo transaction mới. | Đặt thuộc tính ở boundary tạo T1; validate mismatch khi cần. |
| “Nếu từng mở T1 thì mọi method con luôn thấy T1.” | `NOT_SUPPORTED` có thể suspend T1, thread/async khác không tự kế thừa. | Kiểm tra active transaction đúng tại call site. |
| “Có một transaction ở manager khác là đủ.” | Transaction phải tương thích với manager của method. | Chọn manager/datasource rõ, test bằng DB thực. |
| “MANDATORY bảo vệ luôn HTTP/email.” | Không tự rollback side effect ngoài transaction resource. | Thiết kế outbox/idempotency/saga khi cần. |
| “Private/final method cũng được áp dụng annotation.” | Spring AOP proxy có giới hạn intercept. | Dùng public service boundary qua bean proxy. |
| “Lỗi `IllegalTransactionStateException` là lỗi SQL.” | Đây là lỗi **trạng thái transaction trước method**. | Kiểm tra caller, proxy, manager trước khi xem SQL. |

## 16. Checklist sử dụng MANDATORY

- [ ] Method chỉ được phép chạy **khi transaction đã tồn tại**; đây là yêu cầu nghiệp vụ, không phải lựa chọn theo thói quen.
- [ ] Caller orchestration có `@Transactional(REQUIRED)` hoặc transaction boundary khác **thật sự đang hoạt động** khi gọi participant.
- [ ] Method MANDATORY ở Spring-managed bean và được gọi **qua proxy**, không bằng `new` hay `this`.
- [ ] Đã xác nhận đúng `PlatformTransactionManager` và các repository/JdbcTemplate dùng đúng tài nguyên.
- [ ] Không kỳ vọng MANDATORY mở transaction mới hoặc commit độc lập.
- [ ] Đã xác định rollback rules của inner và hậu quả rollback-only đối với outer.
- [ ] Đã kiểm tra trường hợp outer bắt inner exception rồi vẫn không thể commit.
- [ ] Không dựa vào isolation, timeout hoặc read-only của participant để đổi physical transaction đã mở.
- [ ] Nếu có `NOT_SUPPORTED`, `REQUIRES_NEW` hoặc async/thread, đã xác định transaction **đang hiện diện thực tế** tại lời gọi.
- [ ] Integration test gọi **không có transaction** phải ném `IllegalTransactionStateException`.
- [ ] Integration test caller có transaction commit thành công phải lưu cả outer/inner dữ liệu.
- [ ] Integration test caller rollback phải hoàn tác cả outer/inner dữ liệu.
- [ ] Test không có transaction tự mở bởi Spring TestContext ngoài ý muốn.
- [ ] Không giả định MANDATORY tự tạo transaction toàn cục cho nhiều datasource hoặc microservices.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Một method public `@Transactional(propagation = MANDATORY)` được gọi qua proxy, nhưng không có transaction. Nó có tự tạo transaction không?

**Trả lời:** **Không.** Nó ném `IllegalTransactionStateException` trước khi chạy thân method.

**Câu 2.** Outer `REQUIRED` mở T1, inner `MANDATORY` được gọi qua bean khác. Có bao nhiêu physical transactions?

**Trả lời:** Thông thường **một** T1, nếu cùng manager/resource phù hợp. Inner tham gia T1.

**Câu 3.** Inner `MANDATORY` trả về thành công, sau đó outer ném unchecked exception. SQL inner có còn không?

**Trả lời:** Không nếu cả hai cùng physical transaction T1 và outer rollback thành công; inner chưa commit độc lập.

**Câu 4.** Inner `MANDATORY` ném unchecked exception, outer bắt lỗi rồi trả về bình thường. Có chắc outer commit không?

**Trả lời:** **Không.** Inner có thể đã đánh dấu T1 rollback-only. Với manager mặc định như demo, outer nhận `UnexpectedRollbackException` khi cố commit.

**Câu 5.** Outer T1 gọi một bean `NOT_SUPPORTED` rồi bean này gọi MANDATORY. MANDATORY nhìn thấy T1 không?

**Trả lời:** Không nếu `NOT_SUPPORTED` đã **suspend T1** theo đúng manager và lời gọi đi qua proxy. MANDATORY yêu cầu transaction hiện có tại thời điểm nó được intercept.

**Câu 6.** Outer T1 gọi `REQUIRES_NEW` mở T2; trong T2 gọi MANDATORY. Inner MANDATORY thuộc transaction nào?

**Trả lời:** Nó tham gia **T2** đang hiện hành, không phải T1 đang bị suspend. MANDATORY chỉ kiểm tra có transaction phù hợp, không kiểm tra ai mở transaction ban đầu.

**Câu 7.** `this.participant()` trong cùng bean có `@Transactional(MANDATORY)`, không có transaction. Có đảm bảo lỗi không?

**Trả lời:** Không trong Spring proxy mode, vì self-invocation có thể bỏ qua interceptor. Thiết kế tách bean/call qua proxy và test để bảo đảm ràng buộc.

## Tài liệu tham khảo chính thức

- Spring Framework — [`Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Propagation.html): `MANDATORY` yêu cầu transaction hiện tại, khác `REQUIRED` và `REQUIRES_NEW`.
- Spring Framework — [`TransactionDefinition` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html): `PROPAGATION_MANDATORY` và hợp đồng transaction hiện hành.
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): annotation, propagation, rollback rules, isolation/timeout/readOnly.
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical transaction, participation và `UnexpectedRollbackException`.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy và self-invocation.
- Spring Framework — [`IllegalTransactionStateException` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/IllegalTransactionStateException.html): lỗi khi trạng thái transaction không phù hợp với propagation.
- Spring Framework — [TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): nguy cơ test vô tình cung cấp transaction cho method MANDATORY.

**Ghi nhớ cốt lõi:** `MANDATORY` là **yêu cầu caller phải mở transaction trước**, không phải lời yêu cầu Spring tự mở transaction. Khi đã có transaction phù hợp, inner tham gia **cùng physical transaction**, cùng commit/rollback với outer; khi không có, method bị từ chối **trước khi thực thi**. Bảo đảm này chỉ hiệu lực khi lời gọi **đi qua Spring transaction proxy** và đúng transaction manager/resource.
