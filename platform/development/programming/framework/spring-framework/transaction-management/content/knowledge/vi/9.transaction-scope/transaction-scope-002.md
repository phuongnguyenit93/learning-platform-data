# Lời gọi dịch vụ lồng nhau không luôn tạo giao dịch mới

> **Ngữ cảnh:** Spring Framework — Transaction Management, phần **Phạm vi giao dịch**. Bài này giải thích vì sao một phương thức service gọi phương thức service khác, dù cả hai có `@Transactional`, vẫn có thể chỉ dùng **một giao dịch vật lý**; khi nào Spring tạo giao dịch độc lập; vì sao lời gọi nội bộ cùng bean có thể bỏ qua transaction advice; và hậu quả của rollback-only. Ví dụ dùng Java 17, Spring Boot 3.5.x, Spring JDBC và H2.

## 1. Ý chính: số phương thức không bằng số giao dịch

Xét hai service trong cùng một ứng dụng:

```java
@Service
class OrderService {
    private final InventoryService inventory;

    OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder() {
        // Ghi đơn hàng vào database.
        inventory.reserve(); // Gọi bean dịch vụ khác.
    }
}

@Service
class InventoryService {
    @Transactional
    public void reserve() {
        // Ghi thông tin giữ hàng vào database.
    }
}
```

Đây là **trích đoạn minh họa**, giả định code sử dụng `@Service`, `@Transactional` của Spring, có transaction manager và repository/JdbcTemplate đúng nguồn dữ liệu. Hai phương thức đều có `@Transactional` nhưng mặc định `propagation = REQUIRED`.

Nếu `placeOrder()` được gọi qua Spring proxy **khi chưa có transaction**:

1. Interceptor của `OrderService` bắt đầu **một giao dịch vật lý**.
2. `OrderService` gọi `InventoryService` qua **proxy của một Spring bean khác**.
3. Interceptor của `InventoryService` nhận thấy transaction phù hợp đã tồn tại; với `REQUIRED`, nó **tham gia giao dịch đó**, không mở transaction vật lý thứ hai.
4. Các cập nhật có cùng transaction manager/resource được commit hoặc rollback **cùng nhau** khi outer boundary kết thúc.

Vì vậy, “nested service calls” không đồng nghĩa “nested independent transactions”. Từ *lồng nhau* mô tả **call stack**, còn số transaction vật lý phụ thuộc **propagation, transaction manager, tài nguyên và đường đi qua proxy**.

## 2. Phân biệt logical transaction scope và physical transaction

Spring dùng hai lớp khái niệm cần phân biệt:

- **Logical transaction scope:** ranh giới do transaction interceptor thiết lập khi một phương thức được áp dụng transaction advice. Mỗi lời gọi `@Transactional(propagation = REQUIRED)` được intercept có thể có một scope logic riêng, mang metadata và trạng thái rollback-only riêng.
- **Physical transaction:** giao dịch thật của tài nguyên, ví dụ một JDBC connection hoặc JPA transaction đang hoạt động. Một hoặc nhiều scope logic có thể cùng trỏ tới **một** physical transaction.

Sơ đồ với `REQUIRED`:

```text
Caller
  |
  v
OrderService.placeOrder()  @Transactional(REQUIRED)
  |   [logical scope A]
  |   [physical transaction T1 bắt đầu]
  |
  +--> InventoryService.reserve()  @Transactional(REQUIRED)
  |      [logical scope B]
  |      [tham gia cùng physical transaction T1]
  |
  +--> tiếp tục cập nhật
  |
  v
Commit hoặc rollback T1 tại outer boundary
```

Số method annotated được intercept ở ví dụ này là **2**, số physical transaction là **1**.

Nếu một inner scope đặt trạng thái **rollback-only** trên T1, outer scope vẫn đang tham gia cùng T1 nên không thể commit thành công giao dịch đó chỉ vì nó bắt được exception và tiếp tục chạy. Spring có thể ném `UnexpectedRollbackException` ở lúc outer cố commit để tránh báo thành công giả.

Sơ đồ với `REQUIRES_NEW`:

```text
OuterService.outer()  @Transactional(REQUIRED)
    [physical transaction T1 đang mở]
       |
       | gọi qua proxy
       v
InnerService.inner()  @Transactional(REQUIRES_NEW)
    [T1 được tạm ngưng]
    [physical transaction T2 độc lập bắt đầu]
    [T2 commit hoặc rollback riêng]
       |
       v
    [T1 được khôi phục]
       |
       v
Outer tiếp tục T1 và commit/rollback T1
```

Ở đây, nếu transaction manager và datasource cho phép suspend/resume đúng, số physical transaction có thể là **2**, mỗi transaction có kết quả riêng. Nhưng đây là hệ quả của **`REQUIRES_NEW` được intercept thực sự**, không phải vì tên method là `inner`.

## 3. Mặc định `REQUIRED`: tham gia transaction nếu đã tồn tại

`@Transactional` của Spring có propagation mặc định là `Propagation.REQUIRED`:

```java
@Transactional
public void updateProfile() {
    // Tương đương @Transactional(propagation = Propagation.REQUIRED)
}
```

Hành vi:

| Trạng thái lúc vào method | `REQUIRED` làm gì? | Số physical transaction mới |
| --- | --- | --- |
| Chưa có transaction phù hợp | Bắt đầu transaction mới | 1 |
| Đã có transaction phù hợp với cùng manager/resource | Tham gia transaction đang có | 0 |
| Method không được proxy intercept | Annotation không tạo scope logic tại lời gọi đó | 0 do riêng annotation này |
| Đang dùng manager/resource khác | Không thể tự suy ra cùng transaction; phải xét cấu hình cụ thể | Tùy manager và tài nguyên |

Điểm “**cùng manager/resource**” quan trọng: hai service gọi hai datasource khác nhau không mặc nhiên có ACID chung. Spring transaction manager thường quản lý transaction cục bộ của tài nguyên nó được cấu hình; tên annotation giống nhau không đảm bảo transaction được phân phối qua nhiều database hoặc remote service.

### Vì sao reuse transaction là hành vi hữu ích?

Một workflow phổ biến: `CheckoutService` gọi `OrderRepository`, `InventoryRepository` và `AuditRepository`, tất cả ghi vào **cùng một database**. Transaction tại service boundary bảo đảm những thay đổi được commit cùng nhau hoặc rollback cùng nhau. Nếu cứ mỗi method mở một transaction độc lập, dễ có trạng thái “đã tạo order nhưng chưa giữ hàng” khi một bước sau thất bại.

Vì vậy `REQUIRED` là mặc định tốt cho nhiều call stack, vì những bước cùng thuộc một nghiệp vụ thường cần cùng transaction vật lý.

## 4. “Gọi dịch vụ lồng nhau” gồm hai trường hợp rất khác

### 4.1. Gọi từ bean A sang bean B

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        inner.inner(); // Spring-injected bean, qua proxy của InnerService.
    }
}

@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Có thể mở T2 độc lập nếu lời gọi được intercept.
    }
}
```

Đây là **trích đoạn**, cần import `org.springframework.transaction.annotation.Propagation`, `@Transactional` và `@Service`. Khi `InnerService` được inject là Spring bean proxy và cả hai method phù hợp với cơ chế proxy, inner có thể áp dụng propagation riêng.

### 4.2. Gọi method khác trong **cùng bean** (self-invocation)

```java
@Service
class SameBeanService {

    @Transactional
    public void outer() {
        inner(); // Tương đương this.inner(); không đi qua Spring proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Annotation của inner KHÔNG được intercept trong lời gọi trên.
    }
}
```

Trong **Spring AOP proxy mode**, interceptor chỉ bao lời gọi **đến proxy từ bên ngoài**. Một method trên target gọi method khác bằng `this.inner()` không đi lại qua proxy, nên metadata `REQUIRES_NEW` ở `inner` **không được áp dụng riêng**.

Nếu `outer()` đã bắt đầu T1, code trong `inner()` vẫn có thể sử dụng T1 thông qua JdbcTemplate/JPA vì transaction đã gắn vào thread/context. Nhưng nó **không tạo T2**. Nếu outer rollback, những thao tác DB trong inner cũng có thể rollback theo T1.

Nếu `outer()` không annotated và không có transaction nào khác, self-invocation vào `inner()` có thể khiến toàn bộ code đó chạy **không có transaction** dù source có `@Transactional`.

> Thấy `TransactionSynchronizationManager.isActualTransactionActive() == true` **không chứng minh** annotation trên inner method đã được interceptor xử lý: transaction có thể được mở từ caller phía ngoài.

### 4.3. Visibility, final và proxy type

Một số method không được proxy intercept vì Java hoặc loại proxy:

- Với JDK interface proxy, caller cần gọi qua **public method của interface** mà proxy phơi bày.
- Với class-based proxy, Spring Framework 6.0+ có thể intercept các method public/protected/package-visible đủ điều kiện khi gọi qua proxy; phiên bản cũ có chính sách mặc định khác.
- Method `private` không thể bị class proxy override; method `final` cũng không thể override bằng subclass proxy.
- Bean tự tạo bằng `new` và method gọi từ constructor hoặc `@PostConstruct` không nên được xem là lời gọi transaction proxy thông thường.

Đây là những nguyên nhân **khác** với propagation. Trước khi phân tích vì sao `REQUIRES_NEW` không tạo giao dịch mới, phải xác nhận inner method **đã đi qua interceptor hay chưa**.

## 5. So sánh các propagation hay gặp khi service gọi nhau

| Propagation của inner | Khi outer đã có transaction T1 | Khi chưa có transaction | Lưu ý |
| --- | --- | --- | --- |
| `REQUIRED` | Tham gia **T1** | Tạo transaction mới | Mặc định; inner không tự commit độc lập. |
| `REQUIRES_NEW` | Tạm ngưng T1, tạo transaction **T2** | Tạo transaction mới | T2 commit/rollback độc lập; có thể cần thêm connection. |
| `NESTED` | Thường tạo **savepoint trong T1** với JDBC hỗ trợ | Có thể tạo transaction mới như REQUIRED | Rollback về savepoint; **không phải T2 độc lập**. |
| `SUPPORTS` | Chạy trong T1 | Chạy không có transaction | Không chủ động tạo transaction. |
| `MANDATORY` | Tham gia T1 | Ném lỗi vì bắt buộc phải có transaction | Hữu ích khi method yêu cầu caller đã mở transaction. |
| `NOT_SUPPORTED` | Tạm ngưng transaction rồi chạy **không có transaction** | Chạy không có transaction | Không mặc nhiên biến mọi JDBC/HTTP thao tác thành side effect an toàn. |
| `NEVER` | Ném lỗi vì cấm transaction | Chạy không có transaction | Kiểm soát hợp đồng caller. |

Bảng giả định inner method được **Spring transaction interceptor** xử lý và transaction manager hỗ trợ hành vi tương ứng. Nếu gọi `this.inner()`, bảng propagation **không tự được áp dụng** cho inner annotation.

### Chọn theo yêu cầu nghiệp vụ

- Cần tất cả bước ghi database commit/rollback cùng nhau: thông thường dùng **`REQUIRED`**.
- Cần một transaction phụ có thể commit **dù outer về sau rollback** (ví dụ nhật ký kỹ thuật bắt buộc lưu độc lập), cân nhắc **`REQUIRES_NEW`** và chấp nhận tính độc lập, khả năng cạn pool/lock.
- Cần thử một bước, có thể rollback **riêng bước đó** rồi outer tiếp tục trên cùng physical transaction: cân nhắc **`NESTED`** khi datasource/driver hỗ trợ savepoint.
- Cần method chỉ được gọi **trong** một transaction: `MANDATORY` thể hiện hợp đồng rõ ràng.

Không chọn `REQUIRES_NEW` như một “bản vá chung” cho lỗi transaction. Nó **thay đổi tính nguyên tử nghiệp vụ**, có thể khiến inner commit trong lúc outer thất bại.

## 6. Rollback-only và `UnexpectedRollbackException`

Đây là tình huống gây nhầm lẫn nhiều nhất khi hai service cùng dùng `REQUIRED`.

Giả sử:

```java
@Transactional
public void outer() {
    orders.insert(...); // Viết minh họa, giả định orders là repository.
    try {
        inventory.reserve(); // @Transactional(REQUIRED), ném RuntimeException.
    } catch (IllegalStateException ex) {
        // Cố bỏ qua lỗi để outer tiếp tục.
    }
    orders.markPrepared(...);
}
```

Đây là **trích đoạn**, `orders`/`inventory` là thành phần do ứng dụng định nghĩa.

Diễn biến với giao dịch cục bộ thông thường:

1. `outer()` mở T1.
2. `inventory.reserve()` qua proxy tham gia **cùng T1** và tạo logical scope riêng.
3. `reserve()` ném `IllegalStateException` (unchecked).
4. Interceptor của inner, theo rollback rule mặc định, xử lý thất bại của scope và đánh dấu T1 **rollback-only**; inner exception truyền ra outer.
5. Outer **bắt exception**, tiếp tục code và **trả về bình thường**.
6. Outer interceptor cố commit T1. Nhưng T1 đã rollback-only, nên transaction bị rollback.
7. Spring có thể ném **`UnexpectedRollbackException`** cho caller outer: caller phải biết rằng commit đã không xảy ra dù outer code trả về bình thường.

Ý nghĩa của exception này: một scope bên trong âm thầm đánh dấu giao dịch vật lý không thể commit, còn outer scope lại tưởng mình sẽ commit. Spring báo rõ thay vì giả vờ commit thành công.

**Không phải mọi exception được bắt đều dẫn đến `UnexpectedRollbackException`.** Ví dụ inner tự ném lỗi **không qua transaction proxy**, hoặc lỗi không thuộc rollback rule, hoặc code xử lý bằng savepoint thích hợp, có thể có kết quả khác. Khi phân tích phải nhìn đường gọi, rollback rule, cấu hình transaction manager và cách exception được xử lý.

### Checked exception và rollback rule

Spring `@Transactional` mặc định rollback khi `RuntimeException` hoặc `Error` thoát ra qua interceptor; checked `Exception` thường **không** mặc định gây rollback. Có thể cấu hình:

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // Giao dịch rollback khi IOException thoát ra qua interceptor.
}
```

Đây là **trích đoạn**, import `java.io.IOException`. Rule riêng có thể thay đổi kết quả cả ở scope inner tham gia T1. Nếu bạn **bắt exception ngay trong cùng method** rồi không ném tiếp hoặc đánh dấu rollback-only, interceptor có thể chỉ thấy method thành công, trừ khi tài nguyên đã lỗi/rollback-only vì nguyên nhân khác.

### Tại sao sửa bằng catch hoặc `noRollbackFor` chưa chắc đúng?

Nếu một inner step thất bại nhưng nghiệp vụ outer vẫn muốn thành công, phải thiết kế rõ nội dung được phép bỏ qua và trạng thái dữ liệu hợp lệ. Chỉ bắt exception có thể để transaction bị rollback-only. Ngược lại, thêm `noRollbackFor` bừa bãi có thể giữ lại thay đổi chưa hoàn chỉnh.

Nếu inner step có thể bị hủy còn outer tiếp tục, `NESTED` với savepoint (khi hỗ trợ) hoặc tách thành transaction độc lập có chủ đích sẽ rõ ràng hơn. Hãy xác định **hậu quả commit/rollback mong muốn** trước khi chọn propagation.

## 7. Ví dụ hoàn chỉnh Java 17: đếm bản ghi để thấy ranh giới giao dịch

Phần này cung cấp project Spring Boot tối giản, **chạy được** với Maven, Java 17 và H2. Kết quả được đo bằng dữ liệu sau khi các method kết thúc, thay vì chỉ xem annotation trong code.

Ta thử 5 trường hợp trong **cùng một database**:

1. Outer và inner đều `REQUIRED`; outer lỗi ⇒ cả hai insert rollback.
2. Inner `REQUIRED` lỗi, outer bắt exception ⇒ T1 rollback-only và outer commit không thành công.
3. Inner `REQUIRES_NEW` thành công, outer lỗi ⇒ T2 vẫn commit, T1 rollback.
4. Outer gọi method `REQUIRES_NEW` qua `this` trong chính bean ⇒ annotation inner không được intercept; cả hai insert thuộc T1.
5. Inner `NESTED` thất bại, outer bắt lỗi ⇒ rollback tới savepoint của inner; hai insert hợp lệ ở outer commit.

### 7.1. Cấu trúc dự án

```text
nested-transaction-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/
        │       └── example/
        │           └── nested/
        │               ├── NestedTransactionApplication.java
        │               ├── OuterService.java
        │               └── InnerService.java
        └── resources/
            └── application.properties
```

### 7.2. `pom.xml`

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
    <artifactId>nested-transaction-demo</artifactId>
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

- `spring-boot-starter-jdbc` cung cấp Spring JDBC và transaction infrastructure.
- `h2` là JDBC database in-memory.
- `spring-boot-maven-plugin` tạo executable jar từ dự án Boot.
- Không cần chạy database server riêng.

### 7.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:nested_scope_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
```

Pool có thể cấp nhiều connection; ví dụ `REQUIRES_NEW` giữ connection của T1 trong lúc T2 cần connection khác. Đây chỉ là demo tuần tự, không phải công thức sizing cho production.

### 7.4. `src/main/java/vn/example/nested/InnerService.java`

```java
package vn.example.nested;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void joinRequired(int id) {
        insert(id, "required-inner");
    }

    @Transactional
    public void requiredAndFail(int id) {
        insert(id, "required-inner-error");
        throw new IllegalStateException("inner REQUIRED failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independent(int id) {
        insert(id, "requires-new-inner");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedAndFail(int id) {
        insert(id, "nested-inner-error");
        throw new IllegalStateException("inner NESTED failed");
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)",
            id, description
        );
    }
}
```

Các method có `@Transactional` đều là `public`, chạy trên một Spring bean riêng; caller nhận bean này bằng constructor injection, nên lời gọi từ outer được transaction proxy intercept.

Chú ý: `NESTED` hoạt động theo **JDBC savepoints** khi transaction manager/driver hỗ trợ. Không tự suy ra `NESTED` được JPA, NoSQL hoặc mọi driver hỗ trợ giống nhau.

### 7.5. `src/main/java/vn/example/nested/OuterService.java`

```java
package vn.example.nested;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void requiredOuterFails() {
        insert(11, "outer-required");
        inner.joinRequired(12);
        throw new IllegalStateException("outer REQUIRED failed");
    }

    @Transactional
    public void requiredFailureIsCaught() {
        insert(21, "outer-before-inner-error");
        try {
            inner.requiredAndFail(22);
        } catch (IllegalStateException expected) {
            // Inner đã đánh dấu physical transaction rollback-only.
        }
        insert(23, "outer-after-inner-error");
        // Trả về bình thường nhưng commit vẫn có thể bị từ chối.
    }

    @Transactional
    public void requiresNewOuterFails() {
        insert(31, "outer-requires-new");
        inner.independent(32);
        throw new IllegalStateException("outer failed after inner commit");
    }

    @Transactional
    public void selfInvocationOuterFails() {
        insert(41, "outer-self-invocation");
        requiresNewOnSameBean(42); // this.method(): bỏ qua proxy.
        throw new IllegalStateException("outer self-call failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewOnSameBean(int id) {
        insert(id, "self-inner");
    }

    @Transactional
    public void nestedRecovery() {
        insert(51, "outer-before-savepoint");
        try {
            inner.nestedAndFail(52);
        } catch (IllegalStateException expected) {
            // Inner rollback tới JDBC savepoint.
        }
        insert(53, "outer-after-savepoint");
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)",
            id, description
        );
    }
}
```

Không có `@Transactional` trên `insert()` private helper: nó chạy bên trong connection/transaction của caller khi caller có transaction. Trong `selfInvocationOuterFails()`, `requiresNewOnSameBean(42)` là lời gọi cùng bean. Vì không qua proxy, annotation `REQUIRES_NEW` của inner method không mở T2. Row 41 và 42 vẫn thuộc T1 do outer mở; outer rollback thì cả hai cùng biến mất.

Trường hợp `requiredFailureIsCaught()` là điểm dễ gây bất ngờ: outer catch exception không có nghĩa đã xóa rollback-only. Inner `REQUIRED` được intercept, ném unchecked exception, nên transaction manager đánh dấu physical transaction không thể commit. Outer tiếp tục insert row 23, nhưng cả 21/22/23 đều rollback khi outer kết thúc.

### 7.6. `src/main/java/vn/example/nested/NestedTransactionApplication.java`

```java
package vn.example.nested;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class NestedTransactionApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedTransactionApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc,
                                  OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_log (" +
                "id INT PRIMARY KEY, " +
                "description VARCHAR(60) NOT NULL)"
            );

            expectFailure(outer::requiredOuterFails);
            System.out.printf("required=%d,%d%n",
                count(jdbc, 11), count(jdbc, 12));

            try {
                outer.requiredFailureIsCaught();
            } catch (UnexpectedRollbackException expected) {
                System.out.println(
                    "requiredCaught=UnexpectedRollbackException"
                );
            }
            System.out.printf("requiredCaughtRows=%d,%d,%d%n",
                count(jdbc, 21), count(jdbc, 22), count(jdbc, 23));

            expectFailure(outer::requiresNewOuterFails);
            System.out.printf("requiresNew=%d,%d%n",
                count(jdbc, 31), count(jdbc, 32));

            expectFailure(outer::selfInvocationOuterFails);
            System.out.printf("selfInvocation=%d,%d%n",
                count(jdbc, 41), count(jdbc, 42));

            outer.nestedRecovery();
            System.out.printf("nested=%d,%d,%d%n",
                count(jdbc, 51), count(jdbc, 52), count(jdbc, 53));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectFailure(Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected simulated failure");
        } catch (IllegalStateException expected) {
            // Lỗi giả lập được ném ra từ outer.
        }
    }
}
```

Các lựa chọn có chủ ý:

- `@EnableTransactionManagement(proxyTargetClass = true)` cho phép transaction advice chạy qua class-based proxy.
- `JdbcTransactionManager` quản lý **một** H2 `DataSource` được Boot auto-configure; `JdbcTemplate` dùng cùng datasource.
- `CommandLineRunner` được Spring gọi sau khi context khởi tạo, và gọi `OuterService` đã inject qua proxy. Không có transaction sẵn trên runner.
- `JdbcTransactionManager` kế thừa nền tảng của `DataSourceTransactionManager`, cho phép transaction lồng qua JDBC savepoint khi driver/database hỗ trợ. H2 đáp ứng yêu cầu trong demo.
- `count(...)` chạy sau mỗi method ở bên ngoài transaction của outer nên nhìn thấy kết quả commit/rollback thực tế.

### 7.7. Lệnh chạy và stdout cần quan sát

Từ thư mục `nested-transaction-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/nested-transaction-demo-1.0.0.jar
```

Với Java 17, Spring Boot 3.5.7 và cấu hình ở trên, những dòng **do chính demo in ra** là:

```text
required=0,0
requiredCaught=UnexpectedRollbackException
requiredCaughtRows=0,0,0
requiresNew=0,1
selfInvocation=0,0
nested=1,0,1
```

Spring Boot có thể in các dòng log khởi động riêng. Các dòng trên là kết quả nghiệp vụ dự kiến khi test chạy trên stack đã nêu.

### 7.8. Đọc từng kết quả

| Case | Bản ghi còn tồn tại | Lý do |
| --- | --- | --- |
| `required=0,0` | Không có 11/12 | Outer và inner `REQUIRED` cùng T1; outer ném unchecked exception ⇒ rollback T1. |
| `requiredCaughtRows=0,0,0` | Không có 21/22/23 | Inner `REQUIRED` đã đánh dấu T1 rollback-only; catch không tạo lại quyền commit. |
| `requiresNew=0,1` | Chỉ có 32 | Inner T2 commit độc lập; outer T1 rollback. |
| `selfInvocation=0,0` | Không có 41/42 | Annotation `REQUIRES_NEW` ở method cùng bean không được intercept qua `this`; cả hai insert thuộc T1. |
| `nested=1,0,1` | Có 51 và 53, không có 52 | Inner rollback về savepoint trong T1, outer tiếp tục rồi commit T1. |

Số bản ghi ở đây được xác định bởi **ràng buộc transaction thực tế** của ví dụ, không dựa trên một phép đo giả định kiểu “mỗi method có annotation đều tạo connection mới”.

## 8. `REQUIRES_NEW`: độc lập nhưng có chi phí và rủi ro

`@Transactional(propagation = Propagation.REQUIRES_NEW)` yêu cầu một transaction vật lý **mới** cho scope được intercept:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentEvent() {
    // Transaction này có thể commit dù outer sau đó rollback.
}
```

Nếu outer T1 đã tồn tại, manager cần tạm ngưng transaction hiện tại, bắt đầu T2, kết thúc T2 rồi khôi phục T1. Đối với JDBC với cùng datasource, outer thường vẫn giữ connection của T1 trong khi inner lấy thêm connection cho T2.

Do vậy:

1. **Connection pool:** nhiều request đồng thời có T1 rồi cùng chờ T2 có thể cạn pool, thậm chí tạo deadlock do pool nếu tất cả connection đều bị outer giữ. Tài liệu Spring khuyến nghị pool đủ lớn, tối thiểu có dư hơn số thread đồng thời ít nhất một connection trong tình huống điển hình; thực tế phải tính nested depth và workload.
2. **Lock:** T1 có thể đang giữ row lock mà T2 muốn cập nhật. Vì T1 đang chờ T2 hoàn tất còn T2 chờ lock của T1, có thể sinh deadlock/timeout. Đừng dùng `REQUIRES_NEW` để cập nhật cùng hàng đang bị outer khóa.
3. **Commit độc lập:** T2 đã commit không bị undo chỉ vì outer rollback. Đây **là thay đổi nghiệp vụ thật**, không phải tối ưu kỹ thuật vô hại.
4. **Isolation/readOnly/timeout riêng:** T2 có thể dùng cấu hình transaction riêng vì nó là transaction mới, miễn manager/database hỗ trợ.

Một use case hợp lý là ghi một bản ghi audit kỹ thuật độc lập phải tồn tại cả khi business transaction rollback, với điều kiện audit đó không khóa dữ liệu đang được business transaction giữ. Cần quyết định rõ nếu audit thất bại thì business transaction có được tiếp tục không.

## 9. `NESTED`: savepoint, không phải transaction độc lập

`Propagation.NESTED` thường được áp dụng với JDBC transaction manager và driver hỗ trợ **savepoints**:

```text
BEGIN T1
  INSERT row A
  SAVEPOINT S1
    INSERT row B
    -- B lỗi:
  ROLLBACK TO SAVEPOINT S1
  INSERT row C
COMMIT T1

Kết quả: A và C còn; B bị hoàn tác.
```

So với `REQUIRES_NEW`:

| Điểm so sánh | `NESTED` | `REQUIRES_NEW` |
| --- | --- | --- |
| Transaction vật lý | Thường **một** T1 | T1 + T2 độc lập |
| Cơ chế phần inner | JDBC savepoint trong T1 | Transaction mới |
| Khi inner lỗi | Có thể rollback về savepoint, outer tiếp tục | T2 rollback riêng, outer tiếp tục |
| Khi outer cuối cùng rollback | Mọi thay đổi còn trong T1, kể cả phần inner đã “thành công”, đều rollback | Những thay đổi T2 đã commit vẫn tồn tại |
| Connection JDBC | Thường dùng cùng connection của T1 | Thường cần connection khác khi T1 còn bị giữ |
| Tương thích | Phụ thuộc nested support và savepoint của manager/driver | Phụ thuộc khả năng suspend/resource và pool |

Đừng nhầm “inner nested hoàn tất không lỗi” với “inner nested đã commit độc lập”. Khi chỉ dùng savepoint, **commit cuối cùng vẫn do outer T1 quyết định**.

JPA `JpaTransactionManager` không mặc nhiên hỗ trợ nested transaction cho entity persistence context tương đương JDBC savepoint. Tùy manager/driver, `NESTED` có thể bị từ chối (`NestedTransactionNotSupportedException`) hoặc bị giới hạn. Không dựa vào H2 demo để khẳng định mọi persistence stack hỗ trợ giống nhau.

## 10. Isolation, timeout và readOnly của inner `REQUIRED`

Giả sử:

```java
@Transactional(isolation = Isolation.READ_COMMITTED, timeout = 30)
public void outer() {
    inner.run();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void run() {
    // Inner được gọi qua proxy, nhưng tham gia transaction outer.
}
```

Đây là **hai trích đoạn signature của các bean khác nhau**, không phải class đầy đủ. Import `org.springframework.transaction.annotation.Isolation` và `Propagation`.

Nếu `run()` tham gia **T1** do `outer()` mở:

- Spring mặc định chọn các đặc tính của **physical transaction hiện có**. `timeout=5` không tự đặt lại đồng hồ của T1 đang có timeout 30.
- Isolation của T1 không tự nâng lên `SERIALIZABLE` chỉ vì inner annotation ghi như vậy.
- `readOnly=true` ở inner không biến một transaction đã mở kiểu read-write thành read-only vật lý.
- Một số transaction manager có thể được cấu hình `setValidateExistingTransaction(true)` để **từ chối** các trường hợp lệch isolation hoặc read-only không hợp lệ thay vì bỏ qua thầm lặng. Đây là validation của chính sách tham gia transaction, **không phải** cơ chế tự nâng isolation/đặt lại timeout.

Các thuộc tính `isolation`, `timeout` và `readOnly` có tác động rõ khi method **bắt đầu transaction mới** (ví dụ outermost `REQUIRED` hoặc `REQUIRES_NEW` được intercept). Nếu yêu cầu “inner phải có timeout ngắn riêng” là ràng buộc cứng, cần xem xét transaction boundary mới hoặc một timeout riêng cho chính query/HTTP operation; không giả định chỉ thêm annotation là đủ.

## 11. Cách thiết kế boundary dễ hiểu và dễ kiểm thử

### 11.1. Đặt transaction trên orchestration service

Khi workflow gồm nhiều thay đổi **cùng một database**, transaction ở một public service method thường là lựa chọn rõ ràng:

```java
@Service
class CheckoutService {
    private final Orders orders;
    private final Inventory inventory;

    CheckoutService(Orders orders, Inventory inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(long orderId) {
        orders.markPending(orderId);
        inventory.reserve(orderId);
        orders.markConfirmed(orderId);
    }
}
```

**Trích đoạn minh họa:** `Orders` và `Inventory` là interfaces của ứng dụng, không phải API Spring sẵn có. Khi cả hai dùng cùng transaction manager/database và không mở transaction độc lập, chúng có thể tham gia cùng physical transaction.

### 11.2. Tách bean khi thật sự cần propagation riêng

Nếu một bước cần `REQUIRES_NEW` hoặc `NESTED`, hãy đặt nó ở **Spring bean riêng** và inject bean ấy. Cấu trúc minh bạch hơn nhiều so với trông chờ self-invocation được proxy intercept.

Có thể xem xét `TransactionTemplate` để mô tả một boundary cần rõ ngay trong code:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO audit_log(id, description) VALUES (?, ?)",
        999, "independent"
    );
});
```

Đây là **trích đoạn** với `manager`, `jdbc` được cung cấp sẵn. Import `org.springframework.transaction.support.TransactionTemplate` và `org.springframework.transaction.TransactionDefinition`. API chương trình tạo transaction thông qua manager ngay tại callback, phù hợp khi boundary cần điều khiển có chủ đích; vẫn phải cân nhắc connection/locks/commit độc lập.

### 11.3. Đừng dùng “bắt exception rồi tiếp tục” thay cho quyết định transaction

Nếu outer cần tiếp tục sau khi inner thất bại, xác định rõ dữ liệu nào đã ghi, được phép rollback một phần hay commit độc lập. Với `REQUIRED`, inner exception mặc định có thể đánh dấu cả transaction rollback-only. Cần thay đổi thiết kế propagation hoặc xử lý lỗi theo contract nghiệp vụ, không chỉ thêm `try/catch` cho qua.

## 12. Các trường hợp khác không tự truyền transaction

### 12.1. `@Async`, thread mới và scheduler

Imperative transaction do `PlatformTransactionManager` thường gắn với context của **thread hiện tại**. Khi method tạo `new Thread(...)`, chạy qua `@Async` hoặc thread pool, transaction không tự truyền sang thread khác.

```java
@Transactional
public void submit() {
    executor.execute(() -> {
        repository.save(...); // Chạy ở thread khác.
    });
}
```

Đây là **trích đoạn**, với `executor` và `repository` được ứng dụng định nghĩa. Code trong thread mới không mặc nhiên có T1 của `submit()`. Nếu cần transaction ở worker thread, hãy thiết kế một bean/method transaction boundary tại worker và xem xét tính nhất quán, retry cùng thứ tự thực thi.

### 12.2. Reactive transaction

Với `ReactiveTransactionManager`, transaction context thường đi theo **Reactor context**, không theo ThreadLocal như mô hình JDBC imperative. Các publisher cần nằm trong **cùng reactive pipeline/context** để tham gia transaction. Đừng lấy kết luận từ `JdbcTransactionManager` ở ví dụ rồi áp dụng máy móc cho reactive hoặc trộn reactive/imperative mà không hiểu tài nguyên liên quan.

### 12.3. Gọi REST/gRPC sang microservice khác

Một lời gọi HTTP sang service B không tự truyền physical database transaction của A, ngay cả khi hai phía đều có `@Transactional`. Mỗi service có thể mở transaction cục bộ riêng, có thời điểm commit/rollback khác nhau. Nếu cần bảo đảm nghiệp vụ xuyên hệ thống, phải thiết kế hợp đồng API, idempotency, outbox, saga hoặc distributed transaction khi tất cả participant hỗ trợ thực sự.

### 12.4. Hai transaction manager trong cùng ứng dụng

Nếu một method dùng `ordersTransactionManager` còn inner dùng `paymentsTransactionManager`, cần xét hai datasource/nguồn tài nguyên thực tế. `REQUIRED` được đánh giá trong **ngữ cảnh manager tương ứng**; không tự kết luận chúng tham gia cùng một transaction vật lý chỉ vì call stack lồng nhau. Cách chọn manager có thể khai báo tường minh:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder() {
    // Cần repository/JdbcTemplate tương ứng đúng DataSource.
}
```

Đây là **trích đoạn**, giả định bean manager đã tồn tại. Hai local managers không tự biến thành XA/2PC.

## 13. Những lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Inner `@Transactional` nhưng không mở transaction thứ hai | Mặc định `REQUIRED` **tham gia T1** | Đọc propagation, manager, kiểm tra outer transaction có tồn tại. |
| Inner `REQUIRES_NEW` nhưng vẫn rollback cùng outer | Self-invocation hoặc lời gọi không qua proxy | Kiểm tra call graph và bean proxy; tách inner sang bean khác. |
| Outer bắt lỗi inner nhưng cuối cùng ném `UnexpectedRollbackException` | Inner `REQUIRED` đã đánh dấu T1 rollback-only | Xem stack trace, rollback rule và kết quả commit thực tế. |
| Inner `REQUIRES_NEW` đã commit nhưng outer rollback | Hai transaction độc lập, hành vi thiết kế | Xác minh đây là yêu cầu nghiệp vụ, không phải lỗi framework. |
| Inner `NESTED` không chạy | Manager/driver không hỗ trợ savepoint | Kiểm tra transaction manager và JDBC savepoint capability. |
| Inner annotation có `timeout=5` nhưng sau 5 giây không fail | Inner tham gia T1, timeout của T1 chi phối | Kiểm tra transaction boundary và query timeout riêng. |
| Class có `@Transactional` nhưng không có advice | Dùng `new`, private/final method, self-call, proxy config | Kiểm tra Spring bean lifecycle, proxy type, visibility. |
| Test báo rollback thành công dù method không intercepted | Test method đã mở transaction sẵn | Chạy test ngoài test-managed transaction; đo dữ liệu sau commit/rollback. |
| `REQUIRES_NEW` khiến ứng dụng treo dưới tải | Cạn pool hoặc lock giữa T1 và T2 | Đo active/idle/pending connections, lock wait, concurrent threads. |
| Inner service nằm ở thread khác | Transaction imperative không tự truyền qua thread | Tạo boundary riêng tại thread xử lý. |

### Phân biệt “có transaction” và “transaction mới”

API sau thường dùng để quan sát:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("active=" + active);
```

Đây là **trích đoạn**, import `org.springframework.transaction.support.TransactionSynchronizationManager`. `active=true` chỉ xác nhận có transaction đang active trong thread. Nó **không chứng minh** inner đã tạo T2. Để phân biệt `REQUIRED` và `REQUIRES_NEW`, hãy kiểm tra hậu quả rollback/commit và thông tin transaction manager, hoặc dùng test có kiểm soát tương tự phần 7.

### Logging transaction trong môi trường phát triển

Có thể bật:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Các log này có thể giúp xác định transaction begin, tham gia, suspend/resume, commit/rollback, nhưng chi tiết phụ thuộc bản Spring và transaction manager. Không biến log nhạy cảm thành output công khai ở production; kiểm chứng dữ liệu thật vẫn là phép thử cuối cùng.

## 14. Kiểm thử phù hợp với từng mục tiêu

1. **Test join REQUIRED:** gọi outer qua Spring proxy, outer gọi inner `REQUIRED`; cố ý lỗi ở cuối outer và xác nhận **cả hai** insert rollback.
2. **Test rollback-only:** inner `REQUIRED` ném unchecked exception, outer bắt; xác nhận outer caller nhận `UnexpectedRollbackException` và không bản ghi nào commit.
3. **Test độc lập REQUIRES_NEW:** inner qua một bean khác commit; outer rollback; xác nhận inner vẫn còn dữ liệu trong database.
4. **Test self-invocation:** đặt method `REQUIRES_NEW` trong cùng target và gọi bằng `this`; chứng minh kết quả **không giống** gọi qua bean proxy khác.
5. **Test NESTED:** nếu transaction manager hỗ trợ savepoint, inner rollback về savepoint và outer commit phần còn lại; không giả định hỗ trợ với mọi stack.
6. **Test exception rules:** so sánh unchecked exception, checked exception với/không có `rollbackFor`. Đảm bảo test không vô tình tạo outer transaction trước.
7. **Test pool và concurrency:** thử outer+inner `REQUIRES_NEW` với nhiều concurrent requests và lock khác nhau; cấu hình timeout/pool thực tế, giám sát pending connections.
8. **Test transaction manager selection:** nếu có nhiều datasource, kiểm tra đúng manager và resource cho từng method.

**Cạm bẫy trong Spring TestContext:** test method tự có `@Transactional` thường đã mở test-managed transaction và thường rollback lúc kết thúc test. Nó có thể khiến inner `REQUIRED` tham gia một transaction **do test mở**, khác ranh giới bạn nghĩ mình đang kiểm thử. Dùng test method không annotated `@Transactional` cho bài toán kiểm chứng service boundary, hoặc hiểu và điều khiển rõ `TestTransaction` khi cần.

## 15. Checklist thiết kế transaction scope

- [ ] Xác định transaction manager và database nào đang được quản lý.
- [ ] Vẽ call graph và chỉ rõ method nào thực sự được gọi qua Spring proxy.
- [ ] Biết `@Transactional` mặc định là `REQUIRED`, không tự tạo T2 nếu T1 đã tồn tại.
- [ ] Phân biệt **logical scope** với **physical transaction**.
- [ ] Đánh giá propagation của từng inner method theo yêu cầu nghiệp vụ thật.
- [ ] Nếu dùng `REQUIRES_NEW`, chấp nhận commit/rollback độc lập và chuẩn bị đủ pool/lock strategy.
- [ ] Nếu dùng `NESTED`, đã xác minh support savepoint và semantics rollback về savepoint.
- [ ] Nếu inner `REQUIRED` có thể fail, xác định chính sách rollback-only và `UnexpectedRollbackException`.
- [ ] Không cho rằng `try/catch` tự làm transaction sạch trở lại sau khi bị mark rollback-only.
- [ ] Không dựa vào `this.inner()` để kích hoạt annotation propagation riêng ở proxy mode.
- [ ] Không áp dụng timeout/isolation/readOnly riêng của inner `REQUIRED` như thể chúng sửa được transaction vật lý đang mở.
- [ ] Kiểm thử commit/rollback bằng database state, không chỉ bằng annotation hay `active=true`.
- [ ] Tránh giữ transaction dài trong lúc chờ HTTP, thread khác hoặc thao tác ngoài database.
- [ ] Khi có nhiều manager hoặc hệ thống phân tán, xác định ranh giới thực tế của từng transaction.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `A.foo()` và `B.bar()` đều `@Transactional` mặc định, `A.foo()` mở T1 và gọi `B.bar()` qua proxy. Có mấy physical transaction?

**Đáp án:** Thông thường **một** T1, nếu cùng manager/resource phù hợp. `B.bar()` tạo scope logic tham gia T1, không có T2.

**Câu 2.** `B.bar()` khai báo `REQUIRES_NEW` và được gọi qua proxy khi T1 đang hoạt động. Điều gì xảy ra?

**Đáp án:** T1 tạm ngưng; T2 độc lập bắt đầu; T2 kết thúc rồi T1 được khôi phục. Commit T2 không bị outer T1 rollback hoàn tác.

**Câu 3.** `A.foo()` gọi `this.bar()` trong cùng bean; `bar()` khai báo `REQUIRES_NEW`. Có T2 không?

**Đáp án:** **Không** theo mặc định proxy mode, vì lời gọi không đi qua transaction interceptor của `bar()`. Nếu `foo()` đã mở T1, code `bar()` thường chạy trong T1.

**Câu 4.** Inner `REQUIRED` lỗi, outer catch exception, outer method trả về bình thường. Có chắc commit không?

**Đáp án:** **Không**. Nếu inner interceptor đánh dấu T1 rollback-only, outer commit bị rollback và có thể nhận `UnexpectedRollbackException`.

**Câu 5.** `NESTED` và `REQUIRES_NEW` đều “lồng nhau”; chúng có giống nhau không?

**Đáp án:** **Không**. `NESTED` thường rollback về **savepoint trên T1**, còn `REQUIRES_NEW` tạo **T2 vật lý độc lập**. Nếu T1 rollback sau đó, phần đã ghi trong T1 không tồn tại, nhưng T2 đã commit vẫn tồn tại.

## Tài liệu đối chiếu

- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): phân biệt physical/logical transaction scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED` và `UnexpectedRollbackException`.
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): mặc định propagation và rollback rules.
- Spring Framework — [Understanding Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor, proxy, imperative/reactive context.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/class-based proxy và self-invocation.
- Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC transaction và savepoint/nested support.
- Spring Framework — [Testing Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): ranh giới test-managed transactions.

**Kết luận trọng tâm:** Một chuỗi gọi nhiều service **không bảo đảm có nhiều transaction**. Với `REQUIRED`, nhiều logical scopes thường dùng chung một physical transaction. `REQUIRES_NEW` có thể tạo transaction độc lập nhưng cần gọi **qua proxy** và có hệ quả commit/rollback, connection/lock. `NESTED` thường là savepoint trong transaction hiện có. Hãy kiểm chứng bằng **kết quả commit/rollback thực tế** và quan sát call graph trước khi kết luận propagation hoạt động.
