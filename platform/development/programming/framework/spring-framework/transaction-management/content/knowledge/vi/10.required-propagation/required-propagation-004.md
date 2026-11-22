# Ảnh hưởng của `rollback-only` trong phạm vi con với `PROPAGATION_REQUIRED`

## Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

1. Phân biệt **transaction logic** (logical transaction scope) với **transaction vật lý** (physical transaction) khi hai phương thức đều dùng `@Transactional(propagation = REQUIRED)`.
2. Giải thích vì sao phạm vi con đánh dấu **rollback-only** thì phạm vi ngoài không thể commit transaction vật lý chung, dù code bên ngoài đã bắt exception.
3. Nhận biết khi nào caller nhận `UnexpectedRollbackException`, khi nào nhận exception nghiệp vụ ban đầu, và khi nào một method trả về bình thường nhưng dữ liệu vẫn rollback.
4. Phân biệt `setRollbackOnly()` của scope hiện tại, dấu global rollback-only của transaction chung và exception đã đi qua `TransactionInterceptor`.
5. Thực hành với **Java 17+, Spring Boot, JDBC và H2**, kiểm chứng bằng dữ liệu thực tế sau khi từng case kết thúc.
6. Biết khi nào không nên chọn `REQUIRES_NEW`, khi nào `NESTED`/savepoint phù hợp, và cách tránh bất ngờ trong thiết kế service nhiều tầng.

**Chủ đề chính:** hệ quả của **rollback-only trong phạm vi con** khi propagation là `REQUIRED`. Các cách propagation khác chỉ được dùng để so sánh, không thay thế việc hiểu rõ transaction chung.

## 1. `REQUIRED`: nhiều phạm vi logic nhưng chỉ một transaction vật lý

Giả sử `OrderService.placeOrder()` gọi `InventoryService.reserveStock()`. Cả hai method đều có `@Transactional(propagation = Propagation.REQUIRED)`. Trong cấu hình transaction manager chuẩn của Spring:

- Nếu caller chưa có transaction, `placeOrder()` tạo **transaction vật lý T**.
- Khi lời gọi đi qua **proxy** của `InventoryService.reserveStock()`, `REQUIRED` nhận ra T đang tồn tại và **tham gia T**, không tạo transaction vật lý thứ hai.
- Spring vẫn tạo một **phạm vi transaction logic riêng** cho `reserveStock()`. Phạm vi này có thể tự quyết định rollback-only theo lỗi/rollback rule của nó.
- Hai phạm vi logic cùng chia sẻ transaction vật lý T, cùng một connection và cùng số phận commit cuối cùng. Không có một “commit con” thực sự độc lập.

```text
Caller
  |
  v
OrderService proxy
  |  Logical scope OUTER: REQUIRED
  |  Begin physical transaction T
  |
  v
OrderService.placeOrder()
  |  SQL A trong T
  |
  v
InventoryService proxy
  |  Logical scope INNER: REQUIRED
  |  Join physical transaction T
  |
  v
InventoryService.reserveStock()
  |  SQL B trong T
  |  ERROR hoặc setRollbackOnly()
  |
  v
INNER đánh dấu T rollback-only
  |
  v
OUTER vẫn tiếp tục, có thể cố COMMIT
  |
  v
T chỉ có thể ROLLBACK
```

Chính sự tồn tại đồng thời của **hai scope logic** và **một physical transaction** tạo ra hành vi tưởng như nghịch lý: method ngoài “không thấy lỗi” hoặc đã `catch` lỗi nhưng vẫn không thể commit.

### Mặc định `REQUIRED` là gì?

`@Transactional` của Spring dùng `Propagation.REQUIRED` mặc định. Hai cách khai báo dưới đây tương đương về propagation:

```java
@Transactional
public void outer() {
    // ...
}
```

```java
@Transactional(propagation = Propagation.REQUIRED)
public void inner() {
    // ...
}
```

Đây là hai snippet độc lập. Chúng chỉ trở thành hai **transactional scopes thực sự** nếu các method được **Spring transaction advice** xử lý, thường qua lời gọi vào hai bean khác nhau. Việc chỉ dán annotation lên method rồi gọi bằng `this.inner()` không tự tạo scope logic được advice.

## 2. Ai sở hữu transaction và ai có quyền commit?

Phân biệt ba ý:

1. **Owner / transaction originator:** scope đã bắt đầu physical transaction T mới, thường là outermost `REQUIRED` khi trước đó chưa có transaction.
2. **Participant:** scope `REQUIRED` bên trong chỉ tham gia T hiện có. Khi nó kết thúc bình thường, manager xử lý kết thúc **phạm vi logic**, nhưng không thực sự commit connection của T.
3. **Rollback-only:** trạng thái cho biết T không còn được phép commit. Participant có thể khiến T bị đánh dấu rollback-only; owner không thể “xóa” dấu đó rồi commit như không có gì xảy ra.

| Scope | Khi bắt đầu | Khi kết thúc thành công | Nếu đánh dấu rollback-only |
| --- | --- | --- | --- |
| Outer `REQUIRED`, tạo T mới | Bắt đầu physical transaction T | Thử commit T | Phải rollback T |
| Inner `REQUIRED`, tham gia T | Không mở physical transaction mới | Trả quyền điều khiển cho outer; **không commit T** | Có thể đánh dấu T thành global rollback-only |
| Outer sau khi inner rollback-only | Vẫn trong T | Nỗ lực commit sẽ phát hiện T không committable | Thực hiện rollback, thường báo `UnexpectedRollbackException` nếu outer không tự yêu cầu rollback |

**Một transaction vật lý không thể vừa commit phần outer vừa rollback riêng phần inner** khi các thay đổi nằm trong cùng T mà không có savepoint/transaction độc lập. Với `REQUIRED`, nếu inner khiến T thành rollback-only, các câu SQL của outer trước/sau inner đều phải bị rollback cùng T.

### Local và global rollback-only

Trong API của Spring, một `TransactionStatus` có thể phản ánh **local rollback-only** do scope hiện tại đặt, hoặc trạng thái **global rollback-only** của transaction vật lý bên dưới.

- Gọi `status.setRollbackOnly()` trên status của một logical scope đặt **local rollback-only** đối với scope đó.
- Khi scope con `REQUIRED` tham gia một transaction đã có và kết thúc với yêu cầu rollback (ví dụ sau unchecked exception), transaction manager theo mặc định sẽ **đánh dấu shared physical transaction là rollback-only**. Outer có thể chưa hề gọi `setRollbackOnly()`.
- Khi owner cố commit, manager kiểm tra trạng thái transaction và phải rollback nếu T đã được đánh dấu không thể commit.

Thuật ngữ “global” ở đây nghĩa là **trạng thái của transaction vật lý chung**, không đồng nghĩa với “global distributed transaction”/XA/JTA. `DataSourceTransactionManager` dùng một connection JDBC và local transaction vẫn có thể mang global rollback-only trong cách gọi của framework.

## 3. Vì sao có `UnexpectedRollbackException`?

Xét luồng tiêu biểu:

```java
// Outer service:
@Transactional
public void process() {
    saveHeader();
    try {
        innerService.saveDetailAndFail();
    } catch (IllegalStateException ex) {
        // Bắt lỗi nhưng muốn tiếp tục.
    }
    saveAuditRow();
}
```

```java
// Inner service là bean Spring KHÁC:
@Transactional
public void saveDetailAndFail() {
    saveDetail();
    throw new IllegalStateException("Detail failed");
}
```

Hai code block là đoạn minh họa, chưa khai báo hết các bean/helper. Luồng thực khi gọi từ bên ngoài qua outer proxy:

1. Outer proxy mở physical transaction T.
2. Outer viết `header` trong T.
3. Inner proxy tạo scope logic `REQUIRED` và tham gia **chính T**.
4. Inner viết `detail`, sau đó ném `IllegalStateException`.
5. Exception **đi qua inner `TransactionInterceptor`**; mặc định unchecked exception yêu cầu rollback. Inner transaction manager không thể rollback độc lập một phần T mà không rollback phần outer, nên đánh dấu T **rollback-only** rồi ném exception tiếp.
6. Outer method bắt `IllegalStateException` và tiếp tục viết `audit` trong cùng T. Method outer trở về bình thường.
7. Outer proxy định commit vì method hoàn tất bình thường, nhưng T đã rollback-only. Spring rollback toàn bộ header/detail/audit.
8. Vì outer **không chủ đích yêu cầu rollback** mà cũng không được phép tưởng commit đã thành công, caller nhận **`UnexpectedRollbackException`**.

```text
Outer @Transactional REQUIRED (owner T)
   saveHeader()
   |
   +--> Inner @Transactional REQUIRED (participant T)
   |       saveDetail()
   |       throw IllegalStateException
   |       Inner interceptor: mark T rollback-only
   |       throw IllegalStateException
   |
   catch IllegalStateException      <- exception bị bắt
   saveAuditRow()
   return                            <- outer method trông như thành công
   |
   Outer interceptor: commit(T)?
            |
            +-- T is rollback-only
                    |
                    v
               ROLLBACK T
                    |
                    v
           UnexpectedRollbackException
```

`UnexpectedRollbackException` là hành vi **có chủ đích để bảo toàn tính đúng đắn của API**: caller không được nhận tín hiệu commit thành công khi transaction thực tế đã rollback do một scope khác. Đây không phải “Spring tự gây lỗi”; đây là tín hiệu về một transaction chung đã bị phạm vi con bác bỏ.

### Không phải mọi rollback đều tạo `UnexpectedRollbackException`

| Tình huống | Tín hiệu ra ngoài thường gặp | Vì sao |
| --- | --- | --- |
| Inner ném runtime exception, outer **không bắt** | Exception nghiệp vụ ban đầu | Outer interceptor thấy lỗi và chủ động rollback |
| Inner ném runtime exception, outer **bắt và return bình thường** | `UnexpectedRollbackException` khi outer commit | Inner đã mark T rollback-only, outer vẫn thử commit |
| Inner tự `setRollbackOnly()`, trả về bình thường; outer vẫn thử commit | `UnexpectedRollbackException` khi outer commit | Không cần exception để dấu rollback-only lan tới T |
| Outer tự `setRollbackOnly()` trên transaction nó sở hữu | Có thể return bình thường; T rollback theo yêu cầu outer | Rollback đã được outer yêu cầu rõ, không nhất thiết “unexpected” |
| Lỗi bị catch **trước khi qua bất kỳ inner interceptor nào**, T chưa rollback-only | Outer có thể commit | Transaction advice chưa nhận tín hiệu thất bại và không có rollback-only |
| Inner ném checked exception **không khớp rollback rule**, outer bắt | Outer có thể commit | Spring mặc định trên 6.1 không đánh dấu rollback-only cho checked exception |
| Inner dùng `REQUIRES_NEW`, rollback inner, outer bắt và tiếp tục | Outer có thể commit transaction riêng | Hai physical transactions độc lập; semantics nghiệp vụ đã khác |

Những kết quả trên giả định Spring transaction manager mặc định và database/driver vẫn hoạt động theo trạng thái được mô tả. Lỗi SQL nghiêm trọng có thể làm DB không committable **ngay cả khi** exception bị catch.

## 4. Cơ chế đánh dấu rollback-only trong Spring

Trong mô hình imperative JDBC/JPA, transaction status có thể được truy cập bằng `TransactionAspectSupport.currentTransactionStatus()` **bên trong lời gọi được Spring transaction advice xử lý**.

```java
@Transactional(propagation = Propagation.REQUIRED)
public void innerWork() {
    // Thực hiện một phần dữ liệu đã tham gia transaction hiện tại.
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

Sau lời gọi này:

- Inner method có thể trả về **không ném exception**.
- Inner transaction scope được kết thúc với yêu cầu rollback.
- Với `REQUIRED` đang tham gia T có sẵn, manager báo trạng thái rollback-only lên T chung.
- Outer tiếp tục chạy Java code được, nhưng không thể commit T như một transaction hợp lệ.

Đừng dùng `setRollbackOnly()` chỉ để “không ghi một hàng phụ”: đó là một quyết định ảnh hưởng tới **toàn bộ physical transaction T** khi dùng shared `REQUIRED`.

### `@Transactional` và rollback rules

Mặc định Spring Framework 6.1, thường đi cùng Spring Boot 3.3.x:

- `RuntimeException` và `Error` đi ra khỏi transactional method thường kích hoạt rollback.
- Checked exception không kích hoạt rollback nếu không có `rollbackFor` phù hợp.
- Có thể khai báo `@Transactional(rollbackFor = IOException.class)` hoặc `rollbackFor = Exception.class` để đổi rule.
- Có thể dùng `noRollbackFor` cho trường hợp được phép commit dù exception thoát ra.

Đây là **quy tắc áp dụng tại từng logical scope được advice**. Nếu inner đã mark T rollback-only, outer không thể sửa bằng cách khai báo `noRollbackFor` ở outer. `noRollbackFor` của outer điều chỉnh cách **outer interceptor phản ứng với exception đi qua nó**, không có quyền làm T trở lại committable.

Một cấu hình Spring Framework mới hơn có thể thay default rollback rules (ví dụ tùy chọn rollback tất cả exceptions); luôn kiểm tra version và cấu hình của hệ thống thật. Phần demo phía dưới cố định Spring Boot 3.3.5 để kỳ vọng rõ ràng.

## 5. Demo Java 17+ có thể chạy: sáu kịch bản trên cùng một H2 database

Ta tạo hai Spring beans độc lập: **`InnerService`** và **`OuterService`**. Cả hai sử dụng `@Transactional(propagation = REQUIRED)` và cùng `JdbcTemplate`/`DataSourceTransactionManager`. Mỗi kịch bản reset dữ liệu trước khi chạy, nên có thể so sánh trực tiếp kết quả.

**Nghiệp vụ minh họa:** hai ví `wallets(1)=1000`, `wallets(2)=500`. Inner trừ 100 ở ví 1. Outer cộng 10 rồi cộng 20 vào ví 2. Nếu transaction commit, số dư sau toàn chuỗi có thể là `1=900, 2=530`. Nếu T rollback, cả hai ví quay về `1=1000, 2=500`.

Các trường hợp:

| Kịch bản | Điều xảy ra ở inner | Outer | Kết quả transaction T |
| --- | --- | --- | --- |
| 1. Inner ném runtime, outer catch | Inner interceptor mark rollback-only | Return bình thường, cố commit | Rollback T, `UnexpectedRollbackException` |
| 2. Inner gọi `setRollbackOnly()` | Inner return bình thường nhưng mark rollback-only | Return bình thường, cố commit | Rollback T, `UnexpectedRollbackException` |
| 3. Outer không catch inner exception | Inner mark rollback-only và ném runtime | Exception đi qua outer interceptor | Rollback T, caller thấy `IllegalStateException` |
| 4. Outer tự catch lỗi cục bộ | Không gọi inner proxy; lỗi bị nuốt trong outer | Return bình thường | Commit phần ghi trong outer |
| 5. Inner ném checked `IOException` | Không match rollback rule mặc định | Outer catch và return | Commit phần ghi của cả inner + outer |
| 6. Không có lỗi | Inner không tham gia hoặc không báo lỗi | Outer return bình thường | Commit thành công |

### 5.1. Tạo dự án

Dùng Spring Initializr để tạo project Java 17+, Gradle, Spring Boot 3.3.5 với dependency JDBC và H2. Trong project đó đặt các file đúng đường dẫn.

Cấu trúc:

```text
required-rollback-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/required/
    │   │   ├── InnerService.java
    │   │   ├── OuterService.java
    │   │   └── RequiredRollbackApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/required/
        └── RequiredRollbackTest.java
```

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'required-rollback-demo'
```

### 5.3. `build.gradle`

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

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và hạ tầng transaction JDBC; H2 là database in-memory. Khi Spring Boot cấu hình `DataSource` và transaction manager, cả hai service dùng một `DataSource` nên tham gia cùng physical transaction khi method con có `REQUIRED`.

### 5.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:required_scope_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Ứng dụng chạy trong CLI, không cần web server. `spring.sql.init.mode=always` chạy `schema.sql` lúc khởi động. H2 phục vụ demo; trong production phải dùng DBMS và schema migration phù hợp.

### 5.5. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

Cột `balance` và ràng buộc `CHECK` là dữ liệu thật, cho phép test hậu quả commit/rollback. Tất cả ví trong demo nằm trong một database H2 và hai service nhận cùng `JdbcTemplate` do Spring cấu hình.

### 5.6. `src/main/java/example/required/InnerService.java`

```java
package example.required;

import java.io.IOException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void debit() {
        int updated = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (updated != 1) {
            throw new IllegalStateException("Insufficient balance");
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void throwRuntimeAfterDebit() {
        debit();
        throw new IllegalStateException("Inner runtime failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void markRollbackOnlyWithoutThrowing() {
        debit();
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void throwCheckedAfterDebit() throws IOException {
        debit();
        throw new IOException("Inner checked failure");
    }
}
```

**Điểm cần kiểm chứng:**

- Ba public method đều dùng **`REQUIRED`**, và `InnerService` là Spring bean **khác** `OuterService`.
- `throwRuntimeAfterDebit()` cập nhật một hàng thành công, rồi ném unchecked exception. Inner interceptor nhìn thấy lỗi khi method kết thúc bất thường và quyết định rollback.
- `markRollbackOnlyWithoutThrowing()` cập nhật thành công, sau đó đánh dấu rollback-only bằng `TransactionAspectSupport.currentTransactionStatus()`. Method có thể return bình thường; dấu rollback-only vẫn có hiệu lực.
- `throwCheckedAfterDebit()` cập nhật thành công rồi ném checked `IOException`. Với default rollback rules của Spring Boot 3.3.5, inner interceptor **không** yêu cầu rollback chỉ vì `IOException`; do đó transaction ngoài vẫn có thể commit nếu không có lỗi khác.
- `debit()` là helper private, không có transactional annotation riêng. Nó thực hiện SQL **trong connection đã tham gia T** vì được gọi từ method public đã được advice.

Đây là ví dụ cố ý tạo **exception ứng dụng sau một câu SQL hợp lệ**, không phải lỗi SQL/constraint violation. Vì thế ta có thể cô lập hành vi của Spring rollback rules khỏi khả năng DB tự đánh dấu transaction aborted.

### 5.7. `src/main/java/example/required/OuterService.java`

```java
package example.required;

import java.io.IOException;
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

    private void addToSecondWallet(long amount) {
        jdbc.update(
            "UPDATE wallets SET balance = balance + ? WHERE id = 2",
            amount
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchRuntimeFromInner() {
        addToSecondWallet(10);
        try {
            inner.throwRuntimeAfterDebit();
        } catch (IllegalStateException ignored) {
            // Inner interceptor đã thấy lỗi và mark T rollback-only.
        }
        addToSecondWallet(20);
        // Return bình thường nhưng outer commit phải thất bại.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void innerMarksRollbackOnly() {
        addToSecondWallet(10);
        inner.markRollbackOnlyWithoutThrowing();
        addToSecondWallet(20);
        // Không có exception Java trong inner nhưng T đã rollback-only.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void letRuntimeEscape() {
        addToSecondWallet(10);
        inner.throwRuntimeAfterDebit();
        // Không bắt: exception tiếp tục tới outer interceptor.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchLocallyBeforeAnyInnerAdvice() {
        addToSecondWallet(10);
        jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1"
        );

        try {
            throw new IllegalStateException("Locally handled failure");
        } catch (IllegalStateException ignored) {
            // Không có inner @Transactional boundary nào thấy exception.
        }
        addToSecondWallet(20);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchCheckedFromInner() {
        addToSecondWallet(10);
        try {
            inner.throwCheckedAfterDebit();
        } catch (IOException ignored) {
            // Checked exception không match rollback rule mặc định.
        }
        addToSecondWallet(20);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void completeSuccessfully() {
        addToSecondWallet(10);
        addToSecondWallet(20);
    }
}
```

**Cơ chế ở các case đầu tiên:**

- Trong `catchRuntimeFromInner()`, `inner.throwRuntimeAfterDebit()` gọi qua **Spring proxy của bean khác**. Inner interceptor nhận `IllegalStateException`, gắn global rollback-only cho T, rồi ném lại. Catch ở outer chỉ nuốt exception Java, **không xóa rollback-only** của T.
- Trong `innerMarksRollbackOnly()`, inner không ném lỗi. Dù vậy, tại lúc logical scope con kết thúc, transaction manager nhận `status.setRollbackOnly()` và đánh dấu transaction vật lý chung. Outer không có cách commit T.
- Trong `letRuntimeEscape()`, lỗi đi qua cả inner lẫn outer interceptor. Outer cũng nhận thất bại, nên nó rollback T theo yêu cầu đã biết; caller nhận exception nghiệp vụ `IllegalStateException` thay vì thông thường nhận `UnexpectedRollbackException`.
- Trong `catchLocallyBeforeAnyInnerAdvice()`, outer tự bắt exception chưa đi qua **một inner transactional interceptor** nào. Với T còn committable và không có lỗi database khác, outer hoàn tất bình thường nên commit mọi cập nhật. Đây là ví dụ phản chứng giúp phân biệt “đã ném exception” với “scope con đã mark rollback-only”.
- Trong `catchCheckedFromInner()`, `IOException` có đi qua inner proxy nhưng default rule **không yêu cầu rollback**. Outer bắt ngoại lệ rồi kết thúc bình thường, nên commit cả cập nhật ở inner và outer.

Cách viết `catchLocallyBeforeAnyInnerAdvice()` là **tình huống cần hiểu, không phải mẫu nghiệp vụ an toàn để làm theo**. Nếu thao tác trừ tiền không được phép thất bại độc lập, phải thiết kế rollback rule hoặc exception propagation đúng.

### 5.8. `src/main/java/example/required/RequiredRollbackApplication.java`

```java
package example.required;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RequiredRollbackApplication {

    @FunctionalInterface
    interface Job {
        void run() throws Exception;
    }

    public static void main(String[] args) {
        SpringApplication.run(RequiredRollbackApplication.class, args);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update(
            "UPDATE wallets SET balance = 1000 WHERE id = 1"
        );
        jdbc.update(
            "UPDATE wallets SET balance = 500 WHERE id = 2"
        );
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, row) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void runCase(
            String name, JdbcTemplate jdbc, Job job) {
        reset(jdbc);
        String signal = "completed";

        try {
            job.run();
        } catch (Exception error) {
            signal = error.getClass().getSimpleName();
        }

        System.out.println(
            name + " | " + signal + " | " + balances(jdbc)
        );
    }

    @Bean
    ApplicationRunner demo(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            runCase("Inner exception caught", jdbc,
                outer::catchRuntimeFromInner);
            runCase("Inner rollback-only", jdbc,
                outer::innerMarksRollbackOnly);
            runCase("Exception escapes outer", jdbc,
                outer::letRuntimeEscape);
            runCase("Caught before inner advice", jdbc,
                outer::catchLocallyBeforeAnyInnerAdvice);
            runCase("Checked inner exception", jdbc,
                outer::catchCheckedFromInner);
            runCase("Success", jdbc,
                outer::completeSuccessfully);
        };
    }
}
```

`ApplicationRunner` là điểm vào CLI. Bean `OuterService` được **Spring inject**, do đó các lời gọi `outer::...` đi qua outer proxy. `OuterService` cũng được inject `InnerService` bean, nên các lời gọi inner cũng qua proxy riêng — một điều kiện bắt buộc để demo thật sự tạo nhiều **logical transaction scopes**.

Phương thức `runCase()` reset dữ liệu **ngoài** transaction của service cho từng tình huống. Sau khi method kết thúc (hoặc transaction proxy ném exception), nó đọc DB bằng `JdbcTemplate` để xác định điều gì đã commit/rollback.

### 5.9. Chạy và stdout dự kiến

Dùng Gradle wrapper của project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Bỏ qua các dòng log Spring và Gradle, sáu dòng do demo tự in là:

```text
Inner exception caught | UnexpectedRollbackException | 1=1000, 2=500
Inner rollback-only | UnexpectedRollbackException | 1=1000, 2=500
Exception escapes outer | IllegalStateException | 1=1000, 2=500
Caught before inner advice | completed | 1=900, 2=530
Checked inner exception | completed | 1=900, 2=530
Success | completed | 1=1000, 2=530
```

Đây là stdout **dự kiến theo code và cấu hình được nêu**; không phải lời khẳng định đã chạy Gradle trong môi trường của bạn. H2, Spring transaction manager và database schema cần được cấu hình đầy đủ như các file trên để kết quả tương ứng.

### 5.10. Diễn giải đầu ra theo bảng trạng thái

| Case | Inner logical scope | Trạng thái T khi outer cố kết thúc | Outer return / caller nhận |
| --- | --- | --- | --- |
| Inner exception caught | Lỗi unchecked, mark T rollback-only | Không thể commit | `UnexpectedRollbackException` |
| Inner rollback-only | Chủ động `setRollbackOnly`, mark T rollback-only | Không thể commit | `UnexpectedRollbackException` |
| Exception escapes outer | Lỗi unchecked qua cả inner lẫn outer | Outer biết phải rollback | `IllegalStateException` |
| Caught before inner advice | Không có lỗi qua inner interceptor; T vẫn hợp lệ | Có thể commit | Return bình thường |
| Checked inner exception | Checked exception không match default rollback rule | Có thể commit | Outer catch, return bình thường |
| Success | Không có thất bại | Có thể commit | Return bình thường |

**Chú ý:** Có thể vẫn thấy các câu SQL của outer/inner chạy được sau lúc T bị đánh dấu rollback-only (như cập nhật `+20` ở case đầu), tùy trạng thái DB/connection. Nhưng chúng **không thể được commit** khi T cuối cùng rollback. Đừng kiểm tra “sau câu SQL thứ ba có nhìn thấy dữ liệu tạm?” rồi kết luận transaction thành công.

## 6. Kiểm thử bằng JUnit 5 và dữ liệu thực

Test kiểm tra **exception tại boundary** và **trạng thái database sau transaction**, chứ không chỉ kiểm tra `@Transactional` có tồn tại trên source code.

File `src/test/java/example/required/RequiredRollbackTest.java`:

```java
package example.required;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class RequiredRollbackTest {
    @Autowired OuterService outer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private long balance(long id) {
        Long value = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?",
            Long.class,
            id
        );
        return value.longValue();
    }

    @Test
    void catchingInnerExceptionCannotMakeSharedTransactionCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::catchRuntimeFromInner
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void innerRollbackOnlyWithoutExceptionStillAbortsOuter() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::innerMarksRollbackOnly
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void escapingInnerRuntimeExceptionRollsBackNormally() {
        assertThrows(
            IllegalStateException.class,
            outer::letRuntimeEscape
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void catchingLocalFailureBeforeInnerAdviceDoesNotMarkRollback() {
        outer.catchLocallyBeforeAnyInnerAdvice();
        assertEquals(900L, balance(1));
        assertEquals(530L, balance(2));
    }

    @Test
    void catchingCheckedExceptionCanLeaveTransactionCommittable() {
        outer.catchCheckedFromInner();
        assertEquals(900L, balance(1));
        assertEquals(530L, balance(2));
    }

    @Test
    void successfulMethodCommits() {
        outer.completeSuccessfully();
        assertEquals(1000L, balance(1));
        assertEquals(530L, balance(2));
    }
}
```

Chạy:

```bash
./gradlew test
```

`@SpringBootTest` dựng application context và có thể thực thi `ApplicationRunner`, nhưng `@BeforeEach` đặt lại fixture trước từng test. Các test **không được đánh dấu `@Transactional`** để transaction do test framework quản lý không che giấu commit/rollback của service. Nếu chạy tests song song cùng database H2, cần tách schema/fixture hoặc tuần tự hóa để tránh race condition.

### Vì sao không chỉ dùng Mockito?

Mockito có thể kiểm tra `inner.throwRuntimeAfterDebit()` được gọi, hoặc outer bắt exception, nhưng không có **physical transaction** để đánh dấu rollback-only/commit. Cần test tích hợp với `DataSourceTransactionManager` và database thật hoặc in-memory có hỗ trợ transaction để xác minh hệ quả quan trọng nhất.

## 7. Bắt ngoại lệ ở outer không thể xóa dấu rollback-only

Cùng xem hai tình huống giống nhau ở bề mặt:

**A. Lỗi chỉ được tạo và bắt bên trong outer method**

```java
@Transactional
public void methodA() {
    performFirstUpdate();
    try {
        throw new IllegalStateException("Business warning");
    } catch (IllegalStateException ignored) {
    }
    performSecondUpdate();
}
```

Nếu DB không tự báo lỗi/rollback-only, method return thành công và **có thể commit** cả hai update. Lỗi chưa đi qua một **inner transaction interceptor**.

**B. Lỗi đi qua inner proxy trước khi outer catch**

```java
@Transactional
public void methodB() {
    performFirstUpdate();
    try {
        otherBean.innerTransactionalMethod();
    } catch (IllegalStateException ignored) {
    }
    performSecondUpdate();
}
```

Nếu `otherBean.innerTransactionalMethod()` dùng `REQUIRED` và ném unchecked exception, inner interceptor thường mark T rollback-only. Outer có catch cũng không “hủy lệnh rollback”.

Hai snippet này chỉ minh họa, không phải source Java độc lập; project chạy được nằm ở mục 5. Điểm khác biệt không phải từ khóa `catch` mà là **exception đã đi qua transactional advice nào trước khi bị catch**.

### Nếu outer cũng đã cố tình rollback thì sao?

Outer có thể chủ động đánh dấu scope của mình:

```java
@Transactional
public boolean processOrReject() {
    try {
        otherBean.innerTransactionalMethod();
        return true;
    } catch (IllegalStateException failure) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
}
```

Nếu outer sở hữu T mới, local rollback-only của outer khiến transaction rollback theo **quyết định rõ của outer**, không nhất thiết tạo `UnexpectedRollbackException` khi kết thúc. Tuy nhiên, `false` là **kết quả thất bại**; caller không được biến nó thành “commit thành công”. Nếu outer chỉ là participant của một transaction rộng hơn, transaction chung có thể khiến scope ngoài nữa gặp unexpected rollback khi nó cố commit.

Ở code thực tế, **ném lại exception nghiệp vụ phù hợp** thường đơn giản hơn việc phụ thuộc vào `TransactionAspectSupport`. Chỉ dùng `setRollbackOnly()` khi hợp đồng API cần xử lý lỗi nội bộ mà vẫn báo thất bại qua kiểu trả về, và đã hiểu hậu quả đối với outer scopes.

## 8. Tại sao manager đôi khi báo lỗi sớm hoặc báo muộn?

`AbstractPlatformTransactionManager` có các thiết lập nâng cao ảnh hưởng tới việc xử lý một participating transaction.

### 8.1. `globalRollbackOnParticipationFailure`

Mặc định là **`true`**: nếu một participant `REQUIRED` thất bại theo rollback rules, manager đánh dấu transaction đang được chia sẻ là global rollback-only. Đây là hành vi giải thích case `catchRuntimeFromInner()`.

Một số manager cho phép `setGlobalRollbackOnParticipationFailure(false)` để transaction owner quyết định có tiếp tục sau lỗi của participant hay không. **Không coi đây là cách sửa chung** cho `UnexpectedRollbackException`: tài nguyên có thể đã bị đánh dấu lỗi/rollback-only ở tầng database hoặc ORM; việc tiếp tục transaction sau data-access failure có thể không hợp lệ. Thiết lập này cũng **không xóa** một rollback-only được đặt rõ qua `TransactionStatus.setRollbackOnly()`.

### 8.2. `failEarlyOnGlobalRollbackOnly`

Mặc định của Spring transaction manager thường là **`false`**: nếu T đã bị đánh dấu global rollback-only, `UnexpectedRollbackException` thường được báo ở **outermost boundary** khi outer cố commit.

Nếu đổi thành `true`, framework có thể báo `UnexpectedRollbackException` **sớm hơn** tại một boundary transaction bên trong khi phát hiện global rollback-only. Việc bật hay tắt không thay đổi sự thật: T đã rollback-only thì không thể commit.

### 8.3. `validateExistingTransaction`

Một participant `REQUIRED` mặc định thường **tham gia đặc tính của outer transaction**, không tự thay isolation, timeout hay read-only flag của physical transaction đang tồn tại. Cấu hình `validateExistingTransaction=true` có thể yêu cầu manager phát hiện mismatch về isolation hoặc read-only khi join. Đây là cách kiểm soát chính sách transaction, **không phải công cụ giải phóng rollback-only**.

| Cấu hình | Mặc định thường gặp | Tác dụng |
| --- | --- | --- |
| `globalRollbackOnParticipationFailure` | `true` | Participant thất bại -> shared T rollback-only |
| `failEarlyOnGlobalRollbackOnly` | `false` | Báo unexpected rollback ở boundary ngoài cùng |
| `validateExistingTransaction` | `false` | Có thể cho phép join dù policy cục bộ khác outer |

Ba cờ này thuộc hạ tầng transaction manager và cần đánh giá theo DB/ORM thực. Không tùy tiện sửa các default để che một lỗi thiết kế service.

## 9. Đối chiếu `REQUIRES_NEW` và `NESTED` nhưng không đánh tráo semantics

Khi nghiệp vụ **thật sự muốn một phần công việc có thể thất bại độc lập**, có thể cân nhắc propagation khác. Tuy nhiên, đây là **quyết định thay đổi ý nghĩa consistency**, không phải mẹo triệt `UnexpectedRollbackException`.

| Propagation inner | Quan hệ với outer | Inner rollback ảnh hưởng outer thế nào? | Lưu ý |
| --- | --- | --- | --- |
| `REQUIRED` | Cùng physical transaction T | T có thể bị mark rollback-only; outer không commit được | Mặc định, phù hợp all-or-nothing |
| `REQUIRES_NEW` | Transaction inner mới độc lập; outer bị tạm đình chỉ | Inner rollback **không tự** mark outer transaction rollback-only | Cần connection/tài nguyên riêng, có thể làm cạn pool |
| `NESTED` | Một physical transaction, sử dụng savepoint khi hỗ trợ | Inner rollback về savepoint; outer có thể tiếp tục và commit phần còn lại | Cần manager/driver hỗ trợ savepoint; không phải commit độc lập |

### `REQUIRES_NEW`: độc lập thật sự

Ví dụ service gửi email không thuộc database transaction thì không thay đổi vấn đề này; `REQUIRES_NEW` chỉ điều phối transaction resource manager đang quản lý. Nếu dùng `REQUIRES_NEW` cho ghi audit DB độc lập:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentAudit() {
    // Ghi audit trong transaction mới.
}
```

Nó có thể commit dù outer transaction rollback, nhưng đó **chỉ đúng** khi audit được phép tồn tại độc lập. Nếu audit bắt buộc phản ánh cùng một nghiệp vụ đã commit, tách transaction kiểu này có thể làm dữ liệu mâu thuẫn.

### `NESTED`: rollback về savepoint

Với `DataSourceTransactionManager` và driver hỗ trợ JDBC savepoints, `PROPAGATION_NESTED` có thể tạo savepoint khi inner tham gia T. Nếu inner thất bại, manager rollback về savepoint; outer có thể xử lý lỗi và tiếp tục commit phần trước savepoint.

Nhưng `NESTED` vẫn là **một physical transaction**. Nó không mở transaction độc lập và không bảo đảm khả dụng trên mọi transaction manager (đặc biệt các trường hợp JPA/JTA). Nếu outer rollback, mọi thay đổi inner đã qua savepoint nhưng chưa commit cuối cùng cũng rollback.

**Lựa chọn theo invariant:**

- Tất cả phải cùng thành công hoặc cùng thất bại -> ưu tiên `REQUIRED` và để exception/rollback-only được xử lý đúng.
- Một phần độc lập phải commit/rollback riêng -> xem xét `REQUIRES_NEW` và chi phí tài nguyên.
- Muốn phục hồi một phần SQL trong cùng transaction -> cân nhắc `NESTED`/savepoint khi manager hỗ trợ.

## 10. Những nguyên nhân khiến ví dụ không tạo được hai logical scopes

Không phải việc một class có hai method `@Transactional` nghĩa là hai interceptor đã chạy.

### 10.1. Self-invocation

```java
@Service
public class CombinedService {

    @Transactional
    public void outer() {
        try {
            inner();
        } catch (IllegalStateException ignored) {
        }
    }

    @Transactional
    public void inner() {
        throw new IllegalStateException("Failed");
    }
}
```

Trong Spring AOP **proxy mode**, `outer()` gọi `inner()` bằng `this`, nên **không đi qua proxy lần nữa**. Không có inner transaction advice tại lời gọi này. Nếu exception bị bắt ở outer và chưa có rollback-only từ nơi khác, outer vẫn có thể commit. Không được kết luận từ code trên rằng “inner `REQUIRED` đã đánh dấu rollback-only”.

Giải pháp: tách `inner()` sang bean Spring khác và gọi qua bean proxy, hoặc đặt đúng transaction boundary tại một public entrypoint được caller ngoài gọi, hoặc dùng `TransactionTemplate` khi cần điều khiển programmatic. Đổi từ JDK dynamic proxy sang CGLIB **không tự sửa self-invocation**.

### 10.2. Tạo bean bằng `new`

```java
InnerService inner = new InnerService(jdbcTemplate);
inner.throwRuntimeAfterDebit();
```

Đây là snippet minh họa, không phải đoạn sử dụng bean Spring. Đối tượng được tạo bằng `new` không tự có transaction proxy. Nếu được gọi trực tiếp ngoài transaction, SQL có thể auto-commit, dẫn đến kết quả khác hoàn toàn với demo.

### 10.3. Gọi sai transaction manager hoặc datasource

Nếu outer dùng datasource A, inner dùng datasource B hoặc inner được annotation với manager khác, câu “cùng physical transaction T” không còn được đảm bảo. `REQUIRED` chỉ tham gia **transaction phù hợp mà manager đang quản lý**. Cần kiểm tra tên transaction manager, datasource/EntityManager, connection binding và transaction logs.

### 10.4. Lỗi database làm T aborted

Demo dùng `UPDATE` hợp lệ rồi ném exception **ở Java** để tách bạch Spring rollback-only. Trong thực tế, DBMS có thể đánh dấu transaction thất bại ngay sau một SQL error (ví dụ PostgreSQL transaction bị aborted sau lỗi statement, trừ khi quản lý savepoint hợp lệ). Catch exception không chắc làm connection tiếp tục commit được. Trạng thái của DB có thể khiến transaction rollback hoặc commit thất bại ngoài cơ chế mark rollback-only của inner interceptor.

### 10.5. `@Async` và reactive chain

Transaction imperative dựa vào transaction context gắn thread. Giao một bước bắt buộc cho executor/`@Async` rồi return trước khi task kết thúc **không** tạo inner `REQUIRED` scope được phối hợp tự động trong cùng T. Với reactive transactions dùng `ReactiveTransactionManager`, context và lifecycle gắn subscription của `Mono`/`Flux`; không nên áp dụng máy móc kết luận dựa trên JDBC thread-local. Bài này trình bày trường hợp chuẩn **Spring imperative JDBC** để việc phân tích rollback-only rõ ràng.

## 11. Hướng debug `UnexpectedRollbackException` theo chuỗi gọi

Khi gặp lỗi dạng:

```text
org.springframework.transaction.UnexpectedRollbackException:
Transaction rolled back because it has been marked as rollback-only
```

Đừng chỉ nhìn method nơi exception xuất hiện, vì đó có thể là **outer commit boundary**, trong khi nguyên nhân mark rollback-only xuất hiện sớm hơn ở một inner scope.

Kiểm tra lần lượt:

1. **Lời gọi từ ngoài:** method nào bắt đầu T mới? Có đi qua Spring proxy không?
2. **Cấu hình propagation:** inner có `REQUIRED` mặc định hay đã dùng `REQUIRES_NEW`/`NESTED`?
3. **Cùng tài nguyên:** outer/inner có dùng cùng transaction manager và connection không?
4. **Sự kiện đầu tiên làm mark rollback-only:** inner interceptor đã thấy unchecked exception? Có `rollbackFor`/`noRollbackFor`? Có code gọi `setRollbackOnly()`?
5. **Có catch ở outer?** Catch xảy ra **sau** khi exception đi qua inner proxy hay trước đó?
6. **Transaction T còn committable không?** DBMS có trạng thái aborted hoặc ORM Session không còn dùng được?
7. **Kết quả cuối:** outer cố commit hay chủ động rollback? Exception tại caller là original exception hay `UnexpectedRollbackException`?
8. **Dữ liệu hậu transaction:** DB thực sự commit hay rollback, không chỉ nhìn việc SQL update đã trả về số hàng > 0.

Trong môi trường kiểm thử, có thể bật log có chọn lọc:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

Đây là snippet cấu hình **tùy chọn**; không cần thêm vào demo để đạt stdout đã nêu. Chỉ bật TRACE tạm thời vì log giao dịch có thể nhiều; tránh log dữ liệu nhạy cảm.

Có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` để biết thread hiện tại đang có transaction imperative hay không, nhưng nó **không cho biết** transaction sắp commit hay đã rollback-only, và không thay thế việc kiểm tra DB sau commit.

## 12. Cách thiết kế để không bị bất ngờ

### Mẫu A — toàn nghiệp vụ all-or-nothing: để lỗi đi qua outer boundary

```java
@Transactional
public Receipt createOrder(Command command) {
    reserveInventory(command);
    chargeWallet(command);
    return saveReceipt(command);
}
```

Nếu bất kỳ bước bắt buộc nào thất bại, để exception nghiệp vụ khớp rollback rule **đi ra khỏi scope ngoài**. Caller sẽ nhận lỗi đúng bản chất, transaction rollback, không có cảnh outer cố commit một transaction đã bị inner mark rollback-only.

### Mẫu B — outer cần xử lý lỗi nhưng phải biết đã rollback

```java
@Transactional
public ProcessResult process() {
    try {
        innerService.mandatoryStep();
        return ProcessResult.success();
    } catch (BusinessFailure failure) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return ProcessResult.failure(failure.getMessage());
    }
}
```

Đây là snippet minh họa, giả định `ProcessResult`, `BusinessFailure` và `innerService` thuộc code ứng dụng. Outer báo kết quả thất bại rõ ràng và **tự yêu cầu rollback**. Chỉ dùng khi contract trả object thay vì ném exception là chủ đích; không trả `success()` nếu transaction đã được mark rollback-only.

### Mẫu C — fallback thật sự tùy chọn

```java
@Transactional
public void createWithOptionalEnrichment() {
    saveRequiredData();
    try {
        optionalEnrichment();
    } catch (OptionalEnrichmentException ex) {
        recordWarning(ex);
    }
}
```

Mẫu này **chỉ an toàn khi** thất bại của `optionalEnrichment` là chấp nhận được, không vi phạm invariant, và **không có inner scope nào đã mark T rollback-only**. Nếu `optionalEnrichment()` thật ra là lời gọi đến một proxied bean `@Transactional(REQUIRED)` ném runtime exception, outer catch vẫn có thể gặp `UnexpectedRollbackException` sau đó.

Nếu optional logic cần được rollback riêng, hãy thiết kế isolation bằng transaction khác/savepoint và kiểm tra hành vi tài nguyên thật, thay vì chỉ thêm `try/catch`.

## 13. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Outer đã catch nhưng vẫn `UnexpectedRollbackException` | Inner `REQUIRED` interceptor đã mark T rollback-only | Truy nguyên inner scope; nếu toàn bộ nghiệp vụ phải hủy, để lỗi đi ra ngoài |
| Inner tự return bình thường nhưng outer không commit được | Inner gọi `setRollbackOnly()` | Xem contract của inner, không đánh dấu bừa khi chỉ muốn bỏ qua một phần |
| Outer thấy `IllegalStateException`, không có `UnexpectedRollbackException` | Lỗi đi qua outer interceptor và outer chủ động rollback | Đây có thể là kết quả đúng |
| Chạy SQL sau inner failure thấy `rowsUpdated=1` nhưng cuối cùng dữ liệu mất | SQL chỉ sửa dữ liệu tạm trong T; T rollback | Đọc database **sau khi boundary kết thúc** |
| Checked exception của inner bị catch và transaction commit | Default rollback rules không chọn rollback cho checked exception | Thêm `rollbackFor` nếu cần, kiểm thử thực |
| Không tái hiện được rollback-only | Inner gọi bằng `this`, `new` hoặc không qua proxy | Dùng Spring beans đúng và kiểm tra AOP |
| Đổi `REQUIRES_NEW` thì hết lỗi nhưng dữ liệu lệch | Inner độc lập, không còn all-or-nothing với outer | Xác định invariant trước khi đổi propagation |
| Gọi `setGlobalRollbackOnParticipationFailure(false)` nhưng vẫn rollback | DB hoặc code đã mark rollback-only trực tiếp | Không coi config là giải pháp chữa lỗi |
| Lỗi xuất hiện muộn tại outer boundary | `failEarlyOnGlobalRollbackOnly=false` | Truy dấu nguyên nhân sớm trong logs, không chỉ stack cuối |
| DB error được catch nhưng transaction không còn chạy được | DBMS transaction aborted | Rollback/retry đúng scope, không giả định có thể phục hồi |
| Test thấy exception mà không biết commit hay rollback | Chỉ assert exception type | Assert số dư/hàng dữ liệu sau transaction |
| Nhiều transaction manager | Inner không tham gia đúng T mong đợi | Kiểm tra wiring, qualifier và connection |

## 14. Câu hỏi tự kiểm tra

1. Hai method `@Transactional(REQUIRED)` lồng nhau có hai physical transactions không? **Thông thường không**; hai logical scopes chia sẻ một T.
2. Inner scope có thể đánh dấu rollback-only mà không ném exception không? **Có**, bằng `TransactionStatus.setRollbackOnly()` qua Spring API.
3. Vì sao outer catch exception mà commit vẫn thất bại? **Inner interceptor đã mark shared T rollback-only trước khi exception tới catch.**
4. `UnexpectedRollbackException` có nghĩa commit đã thành công rồi không? **Không**; Spring báo transaction đã rollback thay vì commit như caller tưởng.
5. Outer không catch unchecked exception của inner thì caller thường thấy gì? **Exception gốc**, vì outer interceptor cũng quyết định rollback theo lỗi.
6. Outer tự bắt một exception chưa đi qua inner interceptor thì có luôn rollback không? **Không**; nếu T chưa rollback-only và DB còn committable, outer có thể commit.
7. `@Transactional(noRollbackFor=IllegalStateException.class)` ở outer có xóa dấu rollback-only mà inner đã đặt không? **Không**.
8. Inner `REQUIRES_NEW` rollback có bắt buộc outer rollback không? **Không tự động** vì hai physical transactions độc lập, nhưng outer vẫn có thể rollback vì business logic hoặc lỗi thoát qua outer.
9. `NESTED` có tạo commit độc lập? **Không**; khi được hỗ trợ, nó dùng savepoint trong cùng physical T.
10. Một outer transaction có thể commit các SQL sau khi inner đã đánh dấu T rollback-only không? **Không**; mọi cập nhật trong cùng T sẽ rollback nếu T đã rollback-only.
11. Đổi từ JDK proxy sang CGLIB có làm `this.inner()` tự được advice không? **Không**.
12. Phải đặt test ở đâu để kiểm chứng? **Sau khi transaction boundary kết thúc**, trong một transaction/connection đọc độc lập, đồng thời assert exception tương ứng.

## 15. Checklist thực hành với `REQUIRED`

1. Đánh dấu đúng **outer boundary** của đơn vị nghiệp vụ cần atomicity.
2. Kiểm tra mỗi lời gọi inner có thật sự đi qua **Spring transaction proxy** và sử dụng cùng transaction manager không.
3. Phân biệt logical scopes với physical transaction chung, đừng mong inner `REQUIRED` commit/rollback một mình.
4. Khi inner thất bại, xác định default rollback rule và các rule `rollbackFor`/`noRollbackFor` thực tế.
5. Nếu inner đã mark rollback-only, outer không được giả định catch xong là transaction có thể commit.
6. Để exception quan trọng thoát qua outer boundary, hoặc chủ động mark outer rollback-only và báo thất bại minh bạch.
7. Đừng chuyển sang `REQUIRES_NEW` hoặc tắt global rollback policy chỉ để làm hết exception; quyết định dựa trên business invariant.
8. Kiểm tra lỗi SQL/ORM làm connection/session aborted và cách manager xử lý, không chỉ mã Java.
9. Test commit/rollback bằng dữ liệu sau transaction và các trường hợp exception, checked exception, `setRollbackOnly()`, self-invocation.
10. Giữ giao dịch ngắn, chỉ bao các tài nguyên thực sự được transaction manager điều phối.

## Tài liệu tham khảo chính thức

- Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`, logical vs physical scopes): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc (global/fail-early flags): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html