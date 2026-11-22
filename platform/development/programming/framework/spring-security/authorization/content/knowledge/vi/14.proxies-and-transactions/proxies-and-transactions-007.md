# @PostAuthorize, rollback và tác động không nằm trong giao dịch

## 1. Mục tiêu: từ chối trả kết quả có đồng nghĩa với hoàn tác?

Giả sử một phương thức Spring service tạo bản ghi, gửi thông báo, rồi trả về một đối tượng chứa `owner`. Ứng dụng gắn:

```java
@Transactional
@PostAuthorize("returnObject.owner == authentication.name")
public RecordResult createFor(String owner) {
    // Ghi database, gửi thông báo, trả RecordResult.
}
```

Đây chỉ là **mẫu chữ ký phương thức**, không phải chương trình Java độc lập. Nếu người gọi là `bob` nhưng đối tượng trả về thuộc `alice`, `@PostAuthorize` sẽ từ chối kết quả (thường bằng một ngoại lệ thuộc họ `AccessDeniedException`). Tuy nhiên, câu hỏi quan trọng hơn là: **bản ghi có bị rollback và thông báo đã gửi có được thu hồi không?**

Không thể kết luận chỉ từ annotation. Có ít nhất ba ranh giới cần xem xét:

1. **Ranh giới ủy quyền**: `@PostAuthorize` xét điều kiện **sau khi phương thức đích đã chạy và trả giá trị**.
2. **Ranh giới transaction**: commit/rollback phụ thuộc vào việc transaction interceptor còn bao quanh thời điểm phát sinh ngoại lệ hay transaction đã kết thúc.
3. **Ranh giới hệ thống**: email, HTTP request, Kafka publish trực tiếp, file, Redis không tham gia cùng transaction database và không tự hoàn tác khi SQL rollback.

**Quy tắc quan trọng nhất:** `@PostAuthorize` hữu ích để bảo vệ **việc trả kết quả đọc dữ liệu**; không nên dùng nó làm lớp kiểm tra quyền duy nhất cho thao tác ghi/xóa/chuyển tiền hoặc thực hiện tác động không thể thu hồi. Tài liệu chính thức Spring Security cảnh báo rõ trường hợp dùng `@Transactional` cùng `@PostAuthorize` cho method ghi database.

## 2. @PostAuthorize đánh giá khi nào?

Với Method Security đã bật:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Spring Security sử dụng AOP interceptor để đánh giá annotation. Mẫu phổ biến:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document findOne(long id) {
    return repository.findById(id).orElseThrow();
}
```

Trong đoạn mẫu này, `repository` và `Document` là thành phần của ứng dụng. Ý nghĩa:

- `returnObject` là **toàn bộ đối tượng đã được method trả về**; biểu thức đọc `owner` của nó.
- `authentication.name` là định danh hiện tại theo `Authentication#getName()`.
- Phương thức đích được gọi trước, sau đó Spring Security mới kiểm tra biểu thức.
- Nếu điều kiện đúng, caller nhận đối tượng; nếu sai, mặc định ném `AccessDeniedException` hoặc subclass tương ứng. Trong HTTP servlet request được cấu hình phù hợp, hành vi này thường được dịch thành HTTP 403.
- Nếu không đi qua Spring AOP proxy (ví dụ tự `new` service hoặc `this.findOne(...)` bên trong cùng bean), interceptor có thể không chạy.
- Nếu method đã có tác dụng phụ trước khi return thì annotation **không làm thời gian chạy quay ngược**.

Ví dụ thời gian:

```text
T0   caller gọi Spring-managed service qua proxy
T1   các interceptor "before" (ví dụ @PreAuthorize) có thể kiểm tra
T2   target method bắt đầu chạy
T3   target INSERT / UPDATE / gọi API / phát message
T4   target return RecordResult(owner="alice")
T5   @PostAuthorize đọc returnObject.owner và Authentication của bob
T6   điều kiện sai → AuthorizationDeniedException / AccessDeniedException
T7   caller nhận lỗi; transaction có rollback hay không còn tùy vị trí transaction advice
```

**Phân biệt với `@PreAuthorize`:** tiền kiểm có thể chặn lời gọi **trước khi target chạy**, nếu biểu thức đủ thông tin từ Authentication và method arguments. Với hành động có tác dụng phụ, đây thường là cách bảo vệ phù hợp hơn.

## 3. Thứ tự AOP quyết định transaction có nhìn thấy ngoại lệ không

`@Transactional` và `@PostAuthorize` đều có thể được áp dụng bằng Spring AOP. Hai interceptor bao quanh method theo **thứ tự advisor**; interceptor có order nhỏ hơn thường nằm **ngoài** interceptor có order lớn hơn. Trong Spring Security 6.x:

- `@PreAuthorize` có order 200.
- `@PostAuthorize` có order 500.
- Advisor transaction của `@EnableTransactionManagement` có order mặc định `Ordered.LOWEST_PRECEDENCE` (rất lớn) nếu không cấu hình lại.

Thứ tự thực tế có thể khác khi bạn đặt `order`, thay đổi `@EnableMethodSecurity(offset=...)`, đăng ký advisor tùy biến, dùng outer transaction, propagation khác, hoặc gọi qua các proxy khác nhau. Vì vậy cần **quan sát advisor chain/test tích hợp** để kết luận, không suy luận tuyệt đối chỉ từ vị trí annotation trong source code.

### 3.1. Transaction nằm trong hậu kiểm: đã commit rồi mới bị từ chối

Trong trường hợp phổ biến của cấu hình mặc định không có transaction ngoài và advisor transaction ở order thấp nhất:

```text
Caller
  → PostAuthorize advice (outer)
      → Transaction advice (inner)
          BEGIN
          → Target method: ghi database
          COMMIT
      ← Target result (transaction đã kết thúc)
      → PostAuthorize kiểm tra returnObject
          DENY → AccessDeniedException
Caller nhận 403 / exception
```

Ở đây **SQL đã commit trước khi ngoại lệ từ hậu kiểm xuất hiện**. Transaction advice không còn hoạt động nên không thể thấy ngoại lệ để rollback. Kể cả thêm:

```java
@Transactional(rollbackFor = AccessDeniedException.class)
```

cũng **không giúp** nếu ngoại lệ phát sinh **sau khi transaction đã commit**. `rollbackFor` chỉ chi phối quyết định của transaction interceptor khi ngoại lệ đi xuyên qua phạm vi mà interceptor quản lý.

Một HTTP 403, do đó, **không chứng minh database không đổi**. Kiểm tra kết quả bằng truy vấn DB ở test hoặc quan sát transaction log.

### 3.2. Transaction bao cả hậu kiểm: có thể rollback thay đổi DB

Nếu transaction advice nằm **ngoài** `@PostAuthorize` (order nhỏ hơn 500), nó còn đang mở khi hậu kiểm từ chối:

```text
Caller
  → Transaction advice (outer)
      BEGIN
      → PostAuthorize advice (inner)
          → Target method: ghi database
          ← Target result
          → kiểm tra returnObject: DENY
          → ném AccessDeniedException
      ← ngoại lệ đi xuyên transaction advice
      ROLLBACK (mặc định vì runtime exception)
Caller nhận 403 / exception
```

Ví dụ cấu hình thứ tự minh họa cho Spring Security 6.x:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement(order = 300)
public class SecurityAndTransactionConfig {
}
```

Với `@PreAuthorize` order 200, transaction order 300 và `@PostAuthorize` order 500:

```text
@PreAuthorize (200) → @Transactional (300) → @PostAuthorize (500)
    → target method → post-check → commit hoặc rollback
```

Đây là **ví dụ chủ động sắp advisor để minh họa**, không phải khuyến nghị đổi order trên mọi ứng dụng. Thay đổi advisor order có thể tác động đến toàn bộ phương thức có `@Transactional`, thay đổi thời điểm mở/đóng transaction và tương tác với advice khác. Với dự án thực, ưu tiên kiểm tra quyền **trước khi ghi** rồi mới transaction; nếu cần hậu kiểm để rollback, xác minh chain bằng test trên đúng version và cấu hình đã deploy.

Theo Spring Security, một cách điều phối khác trong một số trường hợp là bảo đảm việc khai báo `@EnableTransactionManagement` được xử lý trước `@EnableMethodSecurity`; nhưng **thứ tự khai báo hoặc tên annotation không đủ để chứng minh an toàn** khi đã có cấu hình advisor khác. Ví dụ dùng `order=300` ở đây nhằm làm quan hệ bao ngoài/bao trong tường minh và có thể kiểm thử.

### 3.3. Ma trận các tình huống quan trọng

| Tình huống | Khi hậu kiểm từ chối | Dữ liệu trong transaction DB | Tác động ngoài transaction |
|---|---|---|---|
| `@PostAuthorize` bao ngoài một transaction đã commit | Sau commit | **Không rollback được** phần đã commit | Không bị hoàn tác |
| Transaction bao ngoài cả `@PostAuthorize`; ngoại lệ thoát ra | Trước commit | Thường **rollback** trên `AccessDeniedException` | Không bị hoàn tác |
| Có caller với transaction còn mở, method `REQUIRED` tham gia | Trước commit của outer caller nếu ngoại lệ truyền ra | Có thể rollback outer transaction theo rollback rules | Không bị hoàn tác |
| Method dùng `REQUIRES_NEW` và commit riêng trước post-check | Sau commit của transaction độc lập | Transaction độc lập không bị hoàn tác | Không bị hoàn tác |
| Phát hiện sai quyền trong `@PreAuthorize` trước khi target chạy | Trước tác dụng phụ của target | Không có thay đổi từ target cần hoàn tác | Không có tác động từ target |
| Ngoại lệ bị bắt/nuốt trước transaction boundary hoặc cấu hình `noRollbackFor` | Có thể không làm transaction rollback | Phụ thuộc rollback-only và transaction rules | Không bị hoàn tác |

Trong các dòng này, “rollback được” chỉ áp dụng cho tài nguyên thực sự tham gia **cùng transaction** và chịu quản lý của transaction manager. Nó không phải cơ chế đảo ngược mọi thao tác trong một JVM.

## 4. Vì sao @Transactional không tự bảo đảm rollback?

### 4.1. Rollback rules và thời điểm ngoại lệ

Mặc định của Spring Framework 6.x, khi transaction interceptor **nhìn thấy** ngoại lệ:
- `RuntimeException` hoặc `Error` → đánh dấu rollback.
- Checked exception → thông thường **không** rollback, trừ khi khai báo `rollbackFor` hoặc thiết lập quy tắc phù hợp.
- `AccessDeniedException` thuộc nhóm runtime exception nên thường kích hoạt rollback **nếu** ngoại lệ đi ra qua transaction advice.
- `@Transactional(noRollbackFor = AccessDeniedException.class)` có thể khiến transaction vẫn commit khi nhận ngoại lệ ấy, nếu không có điều kiện rollback-only khác.
- Catch ngoại lệ rồi trả kết quả bình thường bên trong transaction có thể làm advice không thấy lỗi; cần xử lý rõ trạng thái rollback nếu nghiệp vụ yêu cầu.

Ví dụ:

```java
@Transactional(rollbackFor = Exception.class)
public void performBusinessOperation() throws Exception {
    // Đánh dấu rollback cho cả checked Exception chưa xử lý
    // nếu exception đi xuyên qua transaction interceptor.
}
```

Ví dụ trên là chữ ký minh họa; không liên quan trực tiếp đến `@PostAuthorize` nếu hậu kiểm xảy ra ngoài transaction.

### 4.2. Rollback là cơ chế cho các tài nguyên tham gia transaction

Nếu `DataSourceTransactionManager` quản lý JDBC connection, các câu SQL trên cùng connection/transaction có thể rollback khi chưa commit. Nếu method ghi bằng một datasource khác không tham gia cùng transaction manager, Spring không mặc nhiên rollback ở datasource thứ hai.

Cũng cần phân biệt các trạng thái:
- **SQL được execute / JPA được flush**: dữ liệu có thể đã gửi đến database nhưng chưa commit; rollback còn có ý nghĩa.
- **SQL đã commit**: transaction khác không thể “undo” commit ấy bằng một ngoại lệ phát sinh sau đó.
- **Dữ liệu đã được bên thứ ba nhận**: dù database rollback, hệ thống khác có thể đã gửi email, lưu event hoặc thay đổi trạng thái.

Với `PROPAGATION_REQUIRES_NEW`, transaction bên trong có thể commit độc lập với transaction bên ngoài. Rollback của outer transaction không đảo được commit của inner transaction. Nếu có nhiều transaction manager hoặc luồng bất đồng bộ, phải phân tích từng ranh giới.

### 4.3. Transaction là advice, không phải phép màu của annotation

Với proxy-mode mặc định của `@Transactional` và `@EnableMethodSecurity`, self-invocation thường đi thẳng đến target mà không qua lời khuyên AOP:

```java
@Service
class ExampleService {
    public void outer() {
        inner(); // Gọi trong cùng đối tượng; có thể bypass proxy
    }

    @Transactional
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document inner() {
        // ...
    }
}
```

Đoạn này là **mẫu cảnh báo**, chưa runnable vì còn thiếu `Document` và imports. Khi caller gọi `outer()` qua proxy, lời gọi `inner()` qua `this` có thể không được cả transaction lẫn post-authorization kiểm tra. Tách thành service bean khác hoặc thiết kế method entry point đi qua Spring-managed proxy; kiểm thử integration thay vì dựa trên annotation xuất hiện trong code.

## 5. Ví dụ chạy được: database rollback nhưng “email giả lập” vẫn tồn tại

Ví dụ sau dùng Java 17+, Spring Boot **3.5.6**, Spring Security 6.5.x do Boot quản lý, Maven, H2 in-memory database và `JdbcTemplate`. Chủ đích cho thấy ba kết quả khác nhau:

1. **Transaction bọc hậu kiểm**: quyền bị từ chối → INSERT rollback, nhưng tác động ngoài transaction vẫn xảy ra.
2. **Transaction commit bên trong method**: quyền bị từ chối sau đó → INSERT đã commit vẫn tồn tại.
3. **`@PreAuthorize` chặn trước**: method không chạy, không có INSERT hay lời gọi bên ngoài.

Không sử dụng dịch vụ email thực. Một component giữ danh sách thông báo trong bộ nhớ đại diện cho **hành động không tham gia JDBC transaction**; danh sách đó không bị SQL rollback.

### 5.1. Cấu trúc dự án

```text
postauthorize-transaction-demo/
├── pom.xml
├── src/main/java/com/example/authztx/
│   ├── PostAuthorizeTransactionApplication.java
│   ├── SecurityAndTransactionConfig.java
│   ├── RecordResult.java
│   ├── FakeExternalGateway.java
│   └── WriteService.java
├── src/main/resources/schema.sql
└── src/test/java/com/example/authztx/WriteServiceTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>postauthorize-transaction-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

### 5.3. Application và thứ tự advisor

**`src/main/java/com/example/authztx/PostAuthorizeTransactionApplication.java`**

```java
package com.example.authztx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PostAuthorizeTransactionApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeTransactionApplication.class, args);
    }
}
```

**`src/main/java/com/example/authztx/SecurityAndTransactionConfig.java`**

```java
package com.example.authztx;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement(order = 300)
public class SecurityAndTransactionConfig {
}
```

Trong ví dụ cố định này, transaction order 300 được đặt giữa `@PreAuthorize` (200) và `@PostAuthorize` (500). Vì vậy ngoại lệ của hậu kiểm đi qua transaction interceptor và có thể làm rollback. Với ứng dụng thật, hãy xác minh advisor chain trên phiên bản cụ thể trước khi áp dụng cách sắp thứ tự toàn cục.

### 5.4. schema.sql và lớp kết quả

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS audit_write (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner VARCHAR(100) NOT NULL
);
```

H2 là embedded database trong ví dụ; Spring Boot có thể khởi tạo `schema.sql` khi ứng dụng dùng datasource H2. Để kiểm thử hệ thống thật, cần cấu hình datasource và chiến lược migration schema phù hợp.

**`src/main/java/com/example/authztx/RecordResult.java`**

```java
package com.example.authztx;

public record RecordResult(String owner) {
    public String getOwner() {
        return owner;
    }
}
```

Getter `getOwner()` giúp SpEL `returnObject.owner` truy cập đúng thuộc tính.

### 5.5. Cổng tác động ngoài transaction

**`src/main/java/com/example/authztx/FakeExternalGateway.java`**

```java
package com.example.authztx;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class FakeExternalGateway {
    private final List<String> sentEvents = new CopyOnWriteArrayList<>();

    public void send(String event) {
        sentEvents.add(event);
    }

    public List<String> events() {
        return List.copyOf(sentEvents);
    }

    public void clear() {
        sentEvents.clear();
    }
}
```

Bộ nhớ này chỉ nhằm mô phỏng **ngoại ứng không tham gia JDBC transaction**. Nó không phải email server hay event broker và không minh họa các bảo đảm giao nhận mạng; nhưng đủ chứng minh rằng rollback DB không tự gọi `clear()` cho tài nguyên bên ngoài.

### 5.6. Service: ba đường chạy cần so sánh

**`src/main/java/com/example/authztx/WriteService.java`**

```java
package com.example.authztx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;
    private final FakeExternalGateway external;
    private final TransactionTemplate transactionTemplate;

    public WriteService(
            JdbcTemplate jdbc,
            FakeExternalGateway external,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.external = external;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    @Transactional
    @PostAuthorize("returnObject.owner == authentication.name")
    public RecordResult writeAndCallExternal(String owner) {
        jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner);
        external.send("sent:" + owner);
        return new RecordResult(owner);
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public RecordResult writeWithEarlyCommit(String owner) {
        transactionTemplate.executeWithoutResult(status ->
            jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner)
        );
        return new RecordResult(owner);
    }

    @Transactional
    @PreAuthorize("#owner == authentication.name")
    public RecordResult writeWithPreCheck(@P("owner") String owner) {
        jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner);
        return new RecordResult(owner);
    }
}
```

Tại `writeAndCallExternal`, transaction interceptor **bao ngoài hậu kiểm** do cấu hình order 300. Nếu user sai owner, hậu kiểm ném runtime exception khi transaction còn mở: INSERT rollback, nhưng `external.send(...)` đã tác động đến danh sách ngoài DB.

Tại `writeWithEarlyCommit`, `TransactionTemplate` chủ động mở và hoàn tất transaction **trong thân phương thức**, trước lúc `@PostAuthorize` đánh giá. Vì vậy hậu kiểm từ chối không thể hoàn tác INSERT đã commit. Đây là mô phỏng **chắc chắn** của ranh giới commit sớm, không phụ thuộc vào advisor order của `@Transactional`.

Tại `writeWithPreCheck`, điều kiện kiểm tra owner được thực hiện trước khi target chạy. User không hợp lệ không thực hiện INSERT. Đây là phương án thường hợp lý khi đủ thông tin quyền từ tham số phương thức.

### 5.7. Kiểm thử tích hợp các trạng thái commit/rollback

**`src/test/java/com/example/authztx/WriteServiceTest.java`**

```java
package com.example.authztx;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class WriteServiceTest {
    @Autowired
    private WriteService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private FakeExternalGateway external;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM audit_write");
        external.clear();
    }

    private int rows() {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_write", Integer.class
        );
        return count.intValue();
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedPostCheckRollsBackJdbcButNotExternalEffect() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeAndCallExternal("alice")
        );
        assertEquals(0, rows());
        assertEquals(List.of("sent:alice"), external.events());
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedPostCheckCannotUndoAlreadyCommittedTransaction() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeWithEarlyCommit("alice")
        );
        assertEquals(1, rows());
        assertTrue(external.events().isEmpty());
    }

    @Test
    @WithMockUser(username = "bob")
    void preAuthorizeBlocksBeforeAnyWrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeWithPreCheck("alice")
        );
        assertEquals(0, rows());
        assertTrue(external.events().isEmpty());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowedPostCheckCommitsAndKeepsExternalEffect() {
        assertEquals(
            new RecordResult("alice"),
            service.writeAndCallExternal("alice")
        );
        assertEquals(1, rows());
        assertEquals(List.of("sent:alice"), external.events());
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kỳ vọng:** Bốn test pass (`Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`). Nhật ký Maven/Spring có thể khác tùy môi trường; đây là **kết quả mong đợi theo thiết kế**, không phải tuyên bố đã chạy Maven trong bài học.

| Test | Quyền có hợp lệ? | Rows sau lời gọi | Sự kiện bên ngoài | Điều chứng minh |
|---|---|---:|---|---|
| `deniedPostCheckRollsBackJdbcButNotExternalEffect` | Không | 0 | `["sent:alice"]` | Rollback SQL không rollback side effect |
| `deniedPostCheckCannotUndoAlreadyCommittedTransaction` | Không | 1 | `[]` | Hậu kiểm không undo commit trước đó |
| `preAuthorizeBlocksBeforeAnyWrite` | Không | 0 | `[]` | Tiền kiểm chặn trước khi method chạy |
| `allowedPostCheckCommitsAndKeepsExternalEffect` | Có | 1 | `["sent:alice"]` | Hậu kiểm hợp lệ cho phép commit |

**Lưu ý kiểm thử:** Các test **không** gắn `@Transactional` lên test class. Nếu bản thân test tạo outer transaction và rollback cuối test, kết quả quan sát có thể khác vì thứ tự và thời điểm commit thay đổi. `@BeforeEach` xóa dữ liệu cho mỗi test trên embedded DB, và tất cả các method được gọi qua Spring-injected bean để AOP interceptor hoạt động.

## 6. Thiết kế nên dùng trong nghiệp vụ thật: kiểm tra quyền trước, rồi ghi

### 6.1. Xác thực quyền trên ID hoặc owner trước khi transaction ghi

Khi dữ liệu đầu vào đã đủ để biết chủ sở hữu, hãy viết:

```java
@PreAuthorize("@documentPermission.canEdit(authentication, #documentId)")
@Transactional
public void updateDocument(@P("documentId") long documentId,
                           String newTitle) {
    repository.updateTitle(documentId, newTitle);
}
```

Đây là **mẫu tích hợp**, chưa chạy riêng vì cần class entity/repository và bean `documentPermission`. Method chỉ chạy nếu chính sách `canEdit` thông qua. Đừng kiểm tra quyền chỉ bằng owner do client tự gửi: bean policy phải xác minh người gọi có quyền trên **record thật** (và tenant thật) dựa vào dữ liệu tin cậy.

Các hành động dễ bị **TOCTOU** (*time of check/time of use*): nếu quyền/chủ sở hữu bị thay giữa lần kiểm tra và lần ghi, có thể cần khóa phù hợp, kiểm tra lại bên trong transaction hoặc dùng câu `UPDATE ... WHERE owner_id = ? AND id = ?` rồi xác minh affected row count. `@PreAuthorize` không tự giải quyết race condition.

### 6.2. Khi chỉ có thể kiểm tra quyền dựa trên returnObject

Một pattern hữu ích là **đọc trước, ghi sau** qua hai service bean:

```java
@Service
public class DocumentReader {
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document findAuthorized(long id) {
        return repository.findById(id).orElseThrow();
    }
}
```

```java
@Service
public class DocumentEditor {
    private final DocumentReader reader;

    public DocumentEditor(DocumentReader reader) {
        this.reader = reader;
    }

    @Transactional
    public void edit(long id, String title) {
        Document document = reader.findAuthorized(id);
        repository.updateTitle(document.getId(), title);
    }
}
```

Đây là **mẫu cấu trúc**, cần thêm imports, repository và class `Document` để biên dịch. Điểm chủ chốt là gọi `DocumentReader` qua **Spring-injected bean**, thay vì self-invocation. `findAuthorized` thuần đọc, nên người bị từ chối chưa gây side effect ghi từ phương thức edit. Khi nghiệp vụ phức tạp, có thể thay `@PostAuthorize` ở bước đọc bằng một bean policy cung cấp kết quả/điều kiện có thể áp dụng trong transaction ghi. Đối với dữ liệu chịu cạnh tranh cập nhật, hãy bảo đảm trạng thái quyền không đổi giữa lúc đọc và ghi, hoặc recheck khi ghi.

### 6.3. Đảm bảo invariant ngay tại tầng dữ liệu

Với thao tác quản lý tài nguyên, một câu SQL bảo vệ quyền có thể làm một bước:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND owner_username = :authenticated_username
  AND tenant_id = :current_tenant_id;
```

Sau đó kiểm tra số dòng bị ảnh hưởng. Với 0 dòng, trả lỗi phù hợp (không tồn tại hoặc không đủ quyền theo chính sách che giấu thông tin). Tham số phải đến từ Authentication và tenant context tin cậy, **không dùng tenant do request tự tuyên bố**. Cách này gắn quyết định quyền và thay đổi dữ liệu vào cùng thao tác database, giảm race so với việc read-check-write tách rời.

## 7. Tác động không nằm trong transaction: HTTP, email, message, cache, file

### 7.1. Các loại tác động thường gặp

| Tác động trong method | `@Transactional` của JDBC/JPA có tự rollback? | Hướng xử lý |
|---|---|---|
| `INSERT`/`UPDATE` trên datasource tham gia transaction | Có thể, **nếu chưa commit** | Đảm bảo tx boundary và rollback rules |
| `REQUIRES_NEW` đã commit | Không bị outer rollback | Tránh commit độc lập trước quyền |
| Gửi email/SMS trực tiếp | Không | Gửi sau commit và sau khi đã được phép; outbox nếu cần bảo đảm |
| HTTP POST sang dịch vụ khác | Không | Thiết kế idempotency, saga/compensation khi cần |
| Gửi message trực tiếp sang broker | Không mặc nhiên | Outbox hoặc transaction phối hợp được xác minh riêng |
| Ghi file, upload object storage | Không | Defer, dọn file hoặc cơ chế bù có kiểm soát |
| Cập nhật Redis/cache riêng | Không mặc nhiên | Invalidate/update sau commit với quy tắc nhất quán |
| Ghi log audit sang hệ thống ngoài | Không | Phân loại log ý định/thành công; tránh công bố kết quả giả |

Ví dụ, gửi email trong method rồi `@PostAuthorize` từ chối sau return có thể khiến người dùng nhận HTTP 403 nhưng bên thứ ba **đã nhận email**. Ngay cả khi SQL transaction rollback thành công, email vẫn không được “unsend”.

Một ngoại lệ quan trọng về nội dung log: log bảo mật ghi lại **nỗ lực bị từ chối** có thể cố ý tồn tại ngoài transaction; đó là nghiệp vụ audit riêng. Nhưng event “thanh toán thành công” hoặc “đơn hàng đã tạo” không nên phát trước khi thao tác được ủy quyền và commit.

### 7.2. Transaction-bound event: gửi sau commit

Spring Framework hỗ trợ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onDocumentCommitted(DocumentChanged event) {
    notificationGateway.notify(event);
}
```

Đoạn trên là **mẫu listener**, cần bean, imports và các lớp `DocumentChanged`/`notificationGateway`. Listener được gọi sau khi transaction **commit** thành công, thay vì ngay khi sự kiện được phát trong transaction. Với mặc định `fallbackExecution = false`, nếu publish event mà **không có transaction phù hợp**, listener sẽ không chạy. Có các phase `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION` cho mục đích khác.

**Nhưng thứ tự security vẫn rất quan trọng:** nếu `@PostAuthorize` đánh giá **sau khi transaction đã commit**, listener `AFTER_COMMIT` cũng có thể đã chạy dù sau đó caller bị từ chối. Do đó `AFTER_COMMIT` chỉ tránh gửi khi chính transaction rollback; nó **không tự sửa sai** một ủy quyền bị kiểm tra quá muộn. Trước khi publish event nghiệp vụ, hãy bảo đảm quyền đã được xác minh.

Ngoài ra, publish sự kiện chỉ trong bộ nhớ có khoảng trống độ tin cậy: tiến trình có thể chết ngay sau commit nhưng trước khi listener hoàn tất. Nếu giao nhận thông báo là yêu cầu cứng, xem pattern outbox.

### 7.3. Transactional outbox cho thông báo quan trọng

Trong cùng **một** transaction database, sau khi đã được ủy quyền:

1. Ghi bản ghi nghiệp vụ và thêm một dòng `outbox_event` mô tả sự kiện cần gửi.
2. Commit cả hai thay đổi cùng nhau; nếu rollback, cả hai cùng biến mất.
3. Một worker riêng đọc outbox **đã commit** và gửi tới broker/email/API.
4. Khi gửi thành công, đánh dấu đã gửi; khi lỗi, thử lại với backoff; bên nhận nên xử lý **idempotent** vì có thể nhận trùng.

```text
Authorization hợp lệ
        ↓
Transaction SQL
   ├── UPDATE document
   └── INSERT outbox_event
        ↓
      COMMIT
        ↓
Worker đọc outbox → gửi sự kiện → đánh dấu đã gửi
```

Đây là **mô hình thiết kế**, không phải code transaction xuyên qua email server. Outbox giảm tình trạng database commit nhưng phát event thất bại do crash; đổi lại cần worker, retry, chống trùng, monitoring và chính sách xử lý event lỗi. Nó không cho phép hủy email đã gửi.

Với workflow nhiều hệ thống, có thể cần **saga và thao tác bù** (compensation). Bù trừ tạo nghiệp vụ ngược (ví dụ hoàn tiền), không phải rollback nguyên tử của transaction SQL ban đầu.

## 8. Các bẫy nâng cao cần phân biệt

### 8.1. Outer transaction của caller

Một service A gọi service B có `@PostAuthorize`. Nếu A đang có transaction `REQUIRED` và B dùng `REQUIRED` tham gia vào đó, transaction của A có thể vẫn mở sau khi B return. Khi ngoại lệ từ hậu kiểm của B lan lên và không bị nuốt, A có thể rollback toàn bộ thao tác trong transaction của mình. Nhưng kết quả này phụ thuộc vào advisor order, propagation, rollback rules, việc exception bị catch và transaction owner. **Đừng coi hiện tượng rollback trong một integration test có outer transaction là bằng chứng tất cả lối gọi đều an toàn.**

### 8.2. Exception bị catch rồi tiếp tục commit

```java
try {
    protectedService.execute();
} catch (AccessDeniedException ex) {
    logger.warn("Access denied", ex);
}
// Một outer transaction có thể tiếp tục nếu chưa bị đánh dấu rollback-only.
```

Đây là **đoạn minh họa**, chưa runnable vì cần `protectedService` và logger. Trong Spring, một transaction interceptor bên trong có thể đã đánh dấu rollback-only khi ngoại lệ đi xuyên qua nó; khi ấy outer commit có thể dẫn tới `UnexpectedRollbackException`. Ngược lại nếu exception phát sinh ngoài transaction advice, không tự có rollback-only. Không dựa trên việc “đã catch” để suy đoán trạng thái DB; kiểm tra transaction status và test thực tế.

### 8.3. Gọi background/async sau khi return

Một `@Async`, thread mới, queue nội bộ hoặc `CompletableFuture` có thể chạy trong ngữ cảnh transaction khác, hoặc không có transaction nào. `@PostAuthorize` trên lời gọi ban đầu không bảo đảm thu hồi việc đã giao cho background worker. Cũng phải xét cách truyền `SecurityContext` qua thread, có thể không tự động kế thừa. Khi cần tác vụ sau commit, hãy dùng pipeline có quan hệ nhân quả rõ ràng và sự kiện được đưa ra sau khi xác minh quyền.

### 8.4. Read-only transaction không phải cơ chế chống ghi

`@Transactional(readOnly = true)` chủ yếu là hint tối ưu cho transaction/ORM tùy driver; không mặc nhiên cấm mọi SQL write. `@PostAuthorize` trên read-only method phù hợp hơn về **ý định** vì hậu kiểm dùng để quyết định kết quả đọc. Nhưng nếu code vẫn gửi email hoặc cập nhật cache/broker, readOnly không ngăn tác động bên ngoài.

### 8.5. Bảo mật không đồng nhất với HTTP status

Trong servlet web, `AccessDeniedException` thường được xử lý thành HTTP 403 khi người dùng đã được xác thực, hoặc theo cách được cấu hình trong entry point/exception handling. Trong batch job, CLI, scheduler và service test không có HTTP response; ngoại lệ vẫn là exception trong Java. Nếu ứng dụng dùng custom denied-handler (ví dụ masking kết quả), cần xét riêng hành vi. Mã HTTP 403 và số dòng database cuối cùng là **hai phép quan sát độc lập**.

### 8.6. Idempotency và thứ tự retry

Khi đã gọi dịch vụ bên ngoài nhưng transaction DB rollback, caller có thể retry và gửi thông báo lần hai. Với API thanh toán, webhook, message hoặc email, dùng idempotency key, deduplication và trạng thái nghiệp vụ bền vững. Một transaction SQL không cung cấp exactly-once delivery cho mạng; ngay cả outbox thường có khả năng gửi ít nhất một lần, nên consumer cần idempotent.

## 9. Checklist review một method có @PostAuthorize

1. **Lý do hậu kiểm:** có thật sự cần dữ liệu `returnObject` mới biết quyền? Nếu biết quyền từ method arg hoặc record id, chuyển sang `@PreAuthorize`/bean policy trước thao tác.
2. **Tác dụng phụ:** rà toàn bộ đường chạy bên trong target, bao gồm ghi DB, gửi email, publish event, HTTP call, log nghiệp vụ, cache, file và tác vụ async.
3. **Proxy:** bảo đảm caller đi qua Spring-managed proxy, không gọi self-invocation hoặc method private/final mà advice không áp dụng.
4. **Advisor chain:** ghi nhận order `@PreAuthorize`, transaction, `@PostAuthorize` và các advisor custom. Tránh kết luận từ thứ tự khai báo annotation trong mã.
5. **Transaction boundary:** xác định ai mở transaction, khi nào commit, propagation, transaction manager, `REQUIRES_NEW` và outer caller.
6. **Rollback rules:** xác nhận `AccessDeniedException` có thật sự truyền qua transaction interceptor, không bị catch/`noRollbackFor`, và DB resource có tham gia transaction.
7. **External side effects:** chọn outbox hoặc deferred action khi nghiệp vụ yêu cầu sự kiện đúng với commit; có retry/idempotency/compensation phù hợp.
8. **Security test:** thử user được phép và không được phép, đồng thời assert **DB state và external state** sau khi exception kết thúc.
9. **Concurrency:** nếu quyền/owner có thể thay đổi giữa kiểm tra và cập nhật, bảo vệ invariant bằng condition trong query, lock hoặc revalidation trong cùng transaction.
10. **Đường truy cập khác:** API khác, scheduled job, message consumer, repository call trực tiếp cũng cần tuân chính sách; hậu kiểm tại một service không phủ mọi lối vào.

## 10. Trắc nghiệm tự kiểm tra

**Tình huống A.** Method `@Transactional @PostAuthorize` đã cập nhật 10 dòng; transaction advisor nằm bên trong post-authorization advisor; method trả về object của user khác. Database có rollback không?

**Giải thích:** Nếu transaction đã commit trước khi hậu kiểm ném `AccessDeniedException`, không. Caller có thể nhận 403 trong khi 10 dòng đã được commit.

**Tình huống B.** Transaction advisor bao ngoài `@PostAuthorize`, JDBC transaction chưa commit, `AccessDeniedException` lan ra qua transaction interceptor và không có rollback rule ngoại lệ. JDBC có rollback không?

**Giải thích:** Thông thường có. Đây là unchecked exception đi xuyên qua transaction interceptor; DB thay đổi chưa commit sẽ rollback nếu tham gia cùng transaction.

**Tình huống C.** Ở tình huống B, method đã gọi API gửi SMS trước khi return. SMS có bị hủy khi DB rollback không?

**Giải thích:** Không. HTTP/SMS nằm ngoài JDBC transaction; phải thiết kế thời điểm gửi, outbox, idempotency và xử lý bù phù hợp.

**Tình huống D.** Trước khi sửa đơn hàng, app dùng `@PreAuthorize("@policy.canEdit(authentication, #id)")`. Nếu bị từ chối, method đích có chạy không?

**Giải thích:** Không, khi AOP proxy áp dụng đúng. Đây là lý do nên ưu tiên tiền kiểm trước thao tác ghi.

## 11. Tài liệu tham khảo

- [Spring Security — Method Security / Authorization Method Results with @PostAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — trình tự hậu kiểm, ngoại lệ và cảnh báo không dùng hậu kiểm cho method ghi DB.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — propagation, transaction advisor và mặc định.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) — rollback trên unchecked exception, tùy biến quy tắc.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — `@TransactionalEventListener` và các phase AFTER_COMMIT/AFTER_ROLLBACK.
- [Spring Security — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html) — thứ tự advisor của method security.

**Ghi nhớ:** `@PostAuthorize` kiểm soát **việc trả kết quả sau khi method đã chạy**. Rollback chỉ áp dụng với **tài nguyên còn nằm trong transaction chưa commit** và khi ngoại lệ tới đúng transaction interceptor theo rollback rules. Email, HTTP, message và các commit riêng không tự hoàn tác. Muốn bảo vệ một thao tác có tác dụng phụ, hãy đặt kiểm tra quyền **trước khi thực hiện**, xác minh transaction boundary và thiết kế luồng phát sự kiện sau một commit đã được ủy quyền.