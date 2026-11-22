# Đánh dấu rollback-only khi không ném lại ngoại lệ trong Spring Framework

## 1. Mục tiêu và bài toán

Trong Spring, `@Transactional` thường làm rollback khi `RuntimeException` hoặc `Error` thoát ra khỏi phương thức được transaction interceptor quản lý. Nhưng nhiều luồng nghiệp vụ cần **bắt ngoại lệ, xử lý và không ném lại**: chẳng hạn muốn trả kết quả `REJECTED` thay vì trả HTTP 500, hoặc ghi nhận một lỗi kiểm tra dữ liệu theo hợp đồng nghiệp vụ. Khi exception bị bắt bên trong phương thức, transaction interceptor có thể chỉ thấy **return bình thường** và sẽ commit những câu SQL đã thực hiện.

**Rollback-only** giải quyết vấn đề đó: code có thể chủ động nói với transaction manager rằng **transaction scope phải rollback dù không còn exception đi ra ngoài**.

Sau bài học, bạn sẽ biết:

- Vì sao catch exception bên trong `@Transactional` khiến rollback tự động theo exception không còn được kích hoạt.
- Cách sử dụng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` khi đang được Spring transaction proxy quản lý.
- Cách dùng `TransactionTemplate` và `TransactionStatus.setRollbackOnly()` trong lập trình transaction trực tiếp.
- Vì sao đánh dấu rollback-only **khác** với chạy `ROLLBACK` ngay lập tức.
- Khác biệt giữa đánh dấu ở outer transaction và ở inner `Propagation.REQUIRED`; khi nào phát sinh `UnexpectedRollbackException`.
- Ảnh hưởng của `NESTED` và `REQUIRES_NEW` đối với phạm vi bị rollback.
- Cách kiểm tra dữ liệu sau khi transaction kết thúc, cùng các lỗi thường gặp và bài thực hành Java 17+.

**Tình huống:** Service ghi một thay đổi, sau đó phát hiện dữ liệu không đạt quy tắc nghiệp vụ. API cần trả `REJECTED` thay vì ném exception, nhưng database phải giữ trạng thái như trước lời gọi. Nếu chỉ catch rồi return, transaction có thể commit. Cần chủ động đánh dấu rollback-only trước khi kết thúc.

## 2. Exception, transaction interceptor và quyết định commit

Với transaction AOP thông thường của Spring:

```text
Caller
  |
  v
Spring transaction proxy
  |  bắt đầu / tham gia transaction
  v
@Transactional service
  |  INSERT/UPDATE...
  |  exception có thể xảy ra
  |  try/catch bên trong?
  v
TransactionInterceptor xử lý kết thúc
  |  exception thoát ra -> xét rollback rules
  |  return bình thường -> xét rollback-only và commit/rollback
  v
Caller nhận return hoặc exception
```

Xem một đoạn code **minh họa, chưa phải chương trình độc lập**:

```java
@Transactional
public void save() {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        1L, "candidate");

    try {
        validateInput(); // Ném IllegalArgumentException
    } catch (IllegalArgumentException ex) {
        log.warn("Rejected input", ex);
        // Không ném lại và cũng không đánh dấu rollback.
    }
}
```

`IllegalArgumentException` là unchecked exception. Nếu nó **thoát ra khỏi** method qua transactional interceptor, Spring mặc định rollback. Nhưng ở ví dụ này, method bắt exception rồi return bình thường. Nếu không có cờ rollback-only/lỗi khác, Spring sẽ **commit** INSERT. Interceptor không tự biết tất cả exception từng xuất hiện và đã được xử lý trong method.

| Tình huống tại boundary | Mặc định khi method sở hữu transaction vật lý |
| --- | --- |
| Return bình thường, không rollback-only | Commit |
| `RuntimeException` hoặc `Error` thoát ra | Rollback |
| Checked `Exception` thoát ra, không có `rollbackFor` | Thường commit rồi ném lại exception |
| Exception bị catch và method return bình thường | Thường commit |
| Exception bị catch, gọi `setRollbackOnly()` rồi return | Rollback khi scope hoàn tất |
| Bên trong transaction khác đã đánh dấu rollback-only | Có thể rollback và báo `UnexpectedRollbackException` tại commit ngoài |

Bảng mô tả cấu hình mặc định. `rollbackFor`, `noRollbackFor`, propagation, DB errors và tình trạng `rollback-only` có thể thay đổi kết quả cụ thể. Đặc biệt, rollback-only có thể được đặt bởi một scope **khác** cùng tham gia physical transaction.

## 3. rollback-only có nghĩa gì?

`TransactionStatus.setRollbackOnly()` đánh dấu transaction scope hiện tại là **chỉ được phép kết thúc bằng rollback**. Đây là quyết định của transaction manager tại **lúc hoàn tất scope**, không phải thao tác `Connection.rollback()` tức thì ngay tại dòng gọi.

```text
BEGIN
  |
  +-- INSERT A
  +-- validate() ném lỗi
  +-- catch lỗi
  +-- status.setRollbackOnly()  <-- đặt cờ, chưa chạy ROLLBACK ngay
  +-- return hoặc tiếp tục một số câu lệnh
  |
  v
Spring transaction manager hoàn tất scope
  |
  +-- ROLLBACK (nếu scope sở hữu toàn transaction)
  +-- hoặc xử lý rollback tại savepoint / đánh dấu shared transaction
```

Những hệ quả:

- `setRollbackOnly()` **không phát lại exception** đã bị catch. Nếu caller cần biết nghiệp vụ bị từ chối, phải trả trạng thái lỗi rõ ràng (`REJECTED`) hoặc có cơ chế báo lỗi tương ứng.
- Có thể tiếp tục chạy code sau marker, nhưng các ghi thuộc transaction vật lý sẽ không được commit nếu toàn transaction rollback. Đừng thực hiện các side effect không thể rollback sau khi đã biết phải hủy.
- `status.isRollbackOnly()` cho biết cờ trên status, **không chứng minh** câu SQL ROLLBACK đã chạy. Dữ liệu có thể vẫn nhìn thấy từ connection hiện tại cho đến khi transaction thực sự kết thúc.
- Không có API `setCommitOnly()` để xóa rollback-only. Khi transaction chung đã bị đánh dấu rollback-only, thêm `noRollbackFor` cũng không ép nó commit.
- Nếu DB đã đưa transaction vào trạng thái lỗi/aborted, marker không làm connection trở lại hợp lệ; hãy kết thúc scope, rollback và xử lý lỗi như phù hợp.

## 4. Cách A: TransactionAspectSupport.currentTransactionStatus()

Trong method được `@Transactional` xử lý **qua Spring proxy**, dùng:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result process(long id) {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        id, "candidate");

    try {
        checkBusinessRule(id);
    } catch (BusinessValidationException ex) {
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return Result.REJECTED;
    }

    return Result.ACCEPTED;
}
```

Đây là **fragment minh họa**: `Result`, `BusinessValidationException`, `checkBusinessRule` và các field cần được khai báo nếu muốn chạy. Ý nghĩa:

1. Caller gọi proxy Spring; interceptor bắt đầu hoặc tham gia transaction.
2. Câu INSERT tham gia JDBC connection do manager quản lý.
3. Exception bị catch bên trong method; không có exception đi ra.
4. Code lấy status hiện tại qua `TransactionAspectSupport` và đánh dấu rollback-only.
5. Method trả kết quả `REJECTED`; transaction manager xử lý rollback khi scope kết thúc đúng với propagation.
6. Caller không nên hiểu `return` bình thường là bằng chứng database đã commit.

### Điều kiện và giới hạn của currentTransactionStatus()

`TransactionAspectSupport.currentTransactionStatus()` tra cứu **status do transaction aspect gắn với thread hiện tại**. Nếu không có status do advice tạo ra, API có thể ném `NoTransactionException`. Vì vậy:

- Phải gọi từ code đang ở trong **transaction interceptor context**. Chỉ viết annotation trên một method bị self-invocation (`this.method()`) không tự bảo đảm interceptor được thực thi.
- Không gọi từ thread khác hoặc `@Async` rồi giả định nó thấy status của thread gốc. Spring transaction đồng bộ không tự truyền theo thread mới.
- Nếu `TransactionTemplate` đã cung cấp `TransactionStatus` trong callback, hãy dùng chính đối tượng callback.
- Nếu dùng `Propagation.SUPPORTS` mà không có actual transaction, cần phân biệt trạng thái logic với tài nguyên vật lý. Để chẩn đoán transaction JDBC thật, có thể kiểm tra `TransactionSynchronizationManager.isActualTransactionActive()`.
- Code nghiệp vụ nay phụ thuộc API Spring transaction. Nếu hợp đồng cho phép ném exception qua boundary, `@Transactional(rollbackFor = ...)` thường là thiết kế dễ kiểm thử và ít coupling hơn.

## 5. Cách B: TransactionTemplate và callback TransactionStatus

Với programmatic transaction, Spring trao status trực tiếp cho callback:

```java
transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        20L, "candidate");

    try {
        validateInput();
    } catch (IllegalArgumentException ex) {
        status.setRollbackOnly();
    }
});
```

Đây là **fragment**, cần khai báo `transactionTemplate`/`jdbcTemplate` và helper validation. Khi callback trả về bình thường nhưng status rollback-only, `TransactionTemplate` xử lý rollback theo propagation.

Có thể trả kết quả nghiệp vụ:

```java
Decision result = transactionTemplate.execute(status -> {
    try {
        saveInDatabase();
        validateBusinessRule();
        return Decision.ACCEPTED;
    } catch (BusinessValidationException ex) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
});
```

`Decision` và các helper cần được tự định nghĩa; đoạn code có mục đích giải thích luồng. Nếu `TransactionTemplate` tạo transaction riêng, `REJECTED` được trả sau rollback. Nếu callback chỉ tham gia outer transaction đã có, kết quả cuối của physical transaction vẫn do outer scope quyết định.

**Chú ý:** `TransactionTemplate` mặc định dùng propagation `REQUIRED`. Nó không tự tạo transaction độc lập trong mọi hoàn cảnh. Inner callback trong outer transaction có thể làm **outer rollback-only** giống một inner `@Transactional(REQUIRED)`.

## 6. Vị trí đánh dấu và propagation: hệ quả rất khác nhau

### 6.1. Đánh dấu tại outermost transaction

```text
caller không có transaction
  |
  -> @Transactional REQUIRED process()
        INSERT A
        catch validation error
        setRollbackOnly()
        return REJECTED
  |
  -> proxy ROLLBACK transaction vật lý
  |
  -> caller nhận REJECTED; không nhất thiết nhận exception
```

Đây là rollback **có chủ đích** do outermost scope sở hữu. `UnexpectedRollbackException` **không phải bắt buộc** phát sinh trong tình huống này: khi outer scope tự yêu cầu rollback, Spring thường rollback bình thường. Nếu caller cần biết kết quả, hãy thiết kế return value thể hiện thất bại.

### 6.2. Inner REQUIRED đánh dấu rollback-only

```text
caller
  |
  -> @Transactional REQUIRED outer()
        INSERT A
        |
        -> @Transactional REQUIRED inner()
             INSERT B
             catch lỗi
             currentTransactionStatus().setRollbackOnly()
             return bình thường
        |
        INSERT C
        return bình thường
  |
  -> outer proxy cố commit shared physical transaction
       => ROLLBACK A, B, C
       => UnexpectedRollbackException
```

Với `REQUIRED`, các scope có thể khác nhau về mặt logic nhưng **cùng một physical transaction**. Khi inner status yêu cầu rollback, Spring đánh dấu transaction vật lý chung rollback-only. Outer không tự đánh dấu cờ và vẫn định commit; do đó nó cần nhận `UnexpectedRollbackException` để không đánh lừa caller rằng commit đã thành công.

**Thời điểm ném:** `UnexpectedRollbackException` có thể phát sinh trong lúc **outer interceptor xử lý commit**, nghĩa là **sau khi thân method `outer()` đã return**. Khối `try/catch` bao quanh `inner()` *trong thân outer* không nhất thiết bắt được lỗi commit này; caller gọi **outer proxy** mới là nơi xử lý.

### 6.3. NESTED và REQUIRES_NEW

| Propagation inner khi outer tồn tại | Transaction vật lý | Marker rollback-only của inner |
| --- | --- | --- |
| `REQUIRED` | Dùng chung physical transaction | Có thể khiến toàn outer rollback-only, dẫn đến `UnexpectedRollbackException` |
| `NESTED` | Cùng transaction, tạo savepoint nếu manager/driver hỗ trợ | Có thể rollback đến savepoint ở cuối nested scope; outer có thể tiếp tục |
| `REQUIRES_NEW` | Transaction độc lập; outer tạm suspend | Rollback inner độc lập; outer có thể commit phần riêng |

`NESTED` không commit độc lập: nếu outer rollback, mọi thay đổi của transaction vật lý đều bị hủy. `REQUIRES_NEW` độc lập nhưng có thể cần thêm connection và tạo vấn đề nhất quán nếu inner commit mà outer rollback sau đó.

Trong bài thực hành bên dưới, ví dụ inner dùng **REQUIRED** để cho thấy rõ `UnexpectedRollbackException`; không giả định mọi transaction manager đều hỗ trợ savepoint `NESTED`.

## 7. Dự án Spring Boot Java 17+: bốn tình huống rollback-only

Dự án sử dụng **Spring Boot 3.3.5**, **Spring JDBC**, **H2** và **Maven**. Nó in ra kết quả kiểm chứng **sau khi các proxy invocation kết thúc**:

1. Catch lỗi nhưng không đặt rollback-only → bản ghi được commit.
2. Catch lỗi và gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` → rollback mà không ném lại.
3. Catch lỗi trong `TransactionTemplate` và dùng callback status → rollback.
4. Inner `REQUIRED` đánh dấu rollback-only → outer rollback, caller nhận `UnexpectedRollbackException`.

### 7.1. Cấu trúc project

```text
rollback-only-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RollbackOnlyApplication.java
    │   │   ├── LocalRollbackService.java
    │   │   ├── InnerService.java
    │   │   └── OuterService.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── RollbackOnlyIntegrationTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>rollback-only-demo</artifactId>
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
```

`spring-boot-starter-jdbc` chứa `JdbcTemplate` và transaction support; H2 chạy trong JVM. `spring-boot-starter-test` cung cấp Spring TestContext và JUnit 5.

### 7.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:rollback_only_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

H2 database có tên `rollback_only_demo` cho phép các connection trong cùng JVM dùng cùng database. `DB_CLOSE_DELAY=-1` giữ database khi connection cuối đóng, phù hợp ví dụ.

### 7.4. LocalRollbackService: ba cách xử lý lỗi

**`src/main/java/demo/LocalRollbackService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class LocalRollbackService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public LocalRollbackService(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    @Transactional
    public void swallowedWithoutMarker(long id) {
        insert(id, "no-marker");

        try {
            rejectForDemo();
        } catch (IllegalArgumentException ex) {
            // Phản ví dụ: nuốt lỗi, không yêu cầu rollback.
        }
    }

    @Transactional
    public void swallowedAndMarked(long id) {
        insert(id, "marked");

        try {
            rejectForDemo();
        } catch (IllegalArgumentException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
        }
    }

    public void templateAndMarked(long id) {
        template.executeWithoutResult(status -> {
            insert(id, "template-marked");

            try {
                rejectForDemo();
            } catch (IllegalArgumentException ex) {
                status.setRollbackOnly();
            }
        });
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                id, description);
    }

    private void rejectForDemo() {
        throw new IllegalArgumentException("business rejected");
    }
}
```

**Phân tích:**

- `swallowedWithoutMarker` là **phản ví dụ**: exception đã được xử lý, interceptor thấy method thành công, nên transaction mới commit.
- `swallowedAndMarked` vẫn bắt exception nhưng gọi explicit rollback-only. Vì nó được gọi từ caller không có outer transaction, proxy rollback transaction của method.
- `templateAndMarked` không cần annotation ở wrapper: `TransactionTemplate` quản lý transaction bên trong callback và dùng `status` được truyền vào.

Code cố tình có cùng helper phát lỗi để loại trừ khác biệt từ việc validate. Trong nghiệp vụ thật, nên bắt **kiểu lỗi có thể xử lý dự kiến**, trả outcome phù hợp, không nuốt tất cả `Exception`.

### 7.5. InnerService: rollback-only trong inner REQUIRED

**`src/main/java/demo/InnerService.java`**

```java
package demo;

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

    @Transactional(propagation = Propagation.REQUIRED)
    public void markInsideInner(long id) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                id, "inner");

        try {
            throw new IllegalArgumentException("inner rejected");
        } catch (IllegalArgumentException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
        }
    }
}
```

**`src/main/java/demo/OuterService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
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
    public void callInner(long beforeId, long innerId, long afterId) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                beforeId, "outer-before");

        inner.markInsideInner(innerId); // Spring bean khác, qua proxy.

        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                afterId, "outer-after");
    }
}
```

`OuterService` và `InnerService` là hai bean Spring riêng, tránh self-invocation. Inner `REQUIRED` tham gia transaction ngoài. Khi inner đánh dấu local rollback-only và return, Spring làm transaction vật lý chung rollback-only. Outer tiếp tục thực hiện INSERT cuối nhưng khi kết thúc, commit bị từ chối bằng `UnexpectedRollbackException` và toàn bộ ba bản ghi bị rollback.

### 7.6. RollbackOnlyApplication: đọc sau transaction boundary

**`src/main/java/demo/RollbackOnlyApplication.java`**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootApplication
public class RollbackOnlyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackOnlyApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            LocalRollbackService local,
            OuterService outer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE tx_event (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            local.swallowedWithoutMarker(1L);
            System.out.println("no marker: " + ids(jdbc, 1L, 1L));

            local.swallowedAndMarked(2L);
            System.out.println("marker: " + ids(jdbc, 2L, 2L));

            local.templateAndMarked(3L);
            System.out.println("template marker: " + ids(jdbc, 3L, 3L));

            try {
                outer.callInner(10L, 11L, 12L);
            } catch (UnexpectedRollbackException ex) {
                System.out.println("outer: UnexpectedRollbackException");
            }
            System.out.println("outer rows: " + ids(jdbc, 10L, 12L));
        };
    }

    private static List<Long> ids(JdbcTemplate jdbc, long from, long to) {
        return jdbc.queryForList(
                "SELECT id FROM tx_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class,
                from, to);
    }
}
```

`CommandLineRunner` không có `@Transactional`, nên bản thân runner không tạo outer transaction bao quanh toàn bộ demo. Mỗi lời gọi service đã qua proxy sẽ hoàn tất transaction của nó (hoặc ném exception ở commit) **trước khi** đoạn đọc `ids(...)` chạy.

### 7.7. Chạy và giải thích stdout

Yêu cầu JDK 17+ và Maven 3.6.3+; chạy ở thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng do **chương trình** in, ngoài banner/log khởi động của Spring và Maven:

```text
no marker: [1]
marker: []
template marker: []
outer: UnexpectedRollbackException
outer rows: []
```

| Case | Điều xảy ra trong phương thức | Kết quả |
| --- | --- | --- |
| ID 1 | Catch `IllegalArgumentException`, không marker | Commit id=1 |
| ID 2 | Catch lỗi, `currentTransactionStatus().setRollbackOnly()` | Rollback id=2, không cần ném lại |
| ID 3 | Catch lỗi trong template, `status.setRollbackOnly()` | Rollback id=3 |
| ID 10–12 | Inner `REQUIRED` đánh dấu rollback-only; outer return | Rollback toàn bộ, outer proxy ném `UnexpectedRollbackException` |

**Đặc biệt:** Không có exception ở caller của `local.swallowedAndMarked(2L)`, nhưng SELECT độc lập sau transaction trả `[]`. Điều đó chứng minh **return bình thường không đồng nghĩa đã commit**.

## 8. Integration test để tránh kết luận sai

**`src/test/java/demo/RollbackOnlyIntegrationTest.java`**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class RollbackOnlyIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private LocalRollbackService local;

    @Autowired
    private OuterService outer;

    @Test
    void caughtWithoutMarkerCommits() {
        local.swallowedWithoutMarker(101L);
        assertEquals(1, count(101L));
    }

    @Test
    void caughtWithMarkerRollsBack() {
        local.swallowedAndMarked(102L);
        assertEquals(0, count(102L));
    }

    @Test
    void templateMarkerRollsBack() {
        local.templateAndMarked(103L);
        assertEquals(0, count(103L));
    }

    @Test
    void innerRequiredMarkerPreventsOuterCommit() {
        assertThrows(
                UnexpectedRollbackException.class,
                () -> outer.callInner(110L, 111L, 112L));

        assertEquals(0, count(110L));
        assertEquals(0, count(111L));
        assertEquals(0, count(112L));
    }

    private int count(long id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_event WHERE id = ?",
                Integer.class, id);
        return result == null ? 0 : result;
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** cả bốn test pass khi dự án đã được tạo và dependency tải thành công. Spring Boot khởi động context và `CommandLineRunner` tạo bảng bằng các ID nhỏ (1,2,3,10,11,12); các test dùng ID khác (101–112), tránh trùng.

Không đặt `@Transactional` trên test class/method trong ví dụ này. Nếu test tự có transaction do `Spring TestContext` mở, service `REQUIRED` sẽ **tham gia transaction của test**, làm thay đổi thời điểm commit và nơi có thể xuất hiện `UnexpectedRollbackException`. Mặc định test-managed transaction được rollback sau test, nên một phép kiểm tra ở sai boundary có thể gây hiểu nhầm.

Hãy luôn kiểm tra **trạng thái cuối của dữ liệu sau khi outermost transaction kết thúc**, không chỉ assert method có ném exception hay không.

## 9. Trả kết quả nghiệp vụ khi không ném exception

Một API cần thống nhất giữa outcome Java và transaction outcome. Nếu caller chỉ thấy method return bình thường nhưng dữ liệu đã rollback, việc trả thông báo "success" sẽ gây sai lệch.

Ví dụ **fragment**, giả sử có `enum Outcome { ACCEPTED, REJECTED }` và đã khai báo `jdbcTemplate`:

```java
@Transactional
public Outcome process(long id) {
    jdbcTemplate.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, "candidate");

    if (!isBusinessValid(id)) {
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return Outcome.REJECTED;
    }

    return Outcome.ACCEPTED;
}
```

`isBusinessValid()` cần triển khai theo quy tắc nghiệp vụ; code ở mục này chỉ để minh họa contract. Với một transaction do method sở hữu, `REJECTED` là trạng thái có thể trả sau rollback. Khi có outer transaction, inner trả `REJECTED` chưa có nghĩa physical transaction đã hoàn tất; caller phải xử lý cả boundary ngoài.

Nếu có thể ném exception thay vì trả status, cách declarative thường rõ hơn:

```java
@Transactional(rollbackFor = BusinessValidationException.class)
public void processOrThrow(long id) throws BusinessValidationException {
    jdbcTemplate.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, "candidate");

    validateOrThrow(id);
}
```

Đây là fragment minh họa, không phải class độc lập. `rollbackFor` kích hoạt rollback khi checked `BusinessValidationException` **thoát qua interceptor**. Nếu method catch exception rồi return bình thường, `rollbackFor` không thể phát hiện exception bị nuốt; phải ném lại hoặc chủ động đánh dấu rollback-only.

## 10. Khi nào nên chọn cơ chế nào?

| Yêu cầu | Cơ chế gợi ý |
| --- | --- |
| Lỗi nghiệp vụ có thể ném ra caller | `@Transactional` với rollback rule (`rollbackFor` nếu checked) |
| Bắt lỗi bên trong method, trả kết quả `REJECTED`, phải hủy toàn bộ transaction đang sở hữu | `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` |
| Điều khiển transaction bằng callback không cần transaction AOP | `TransactionTemplate` và callback `TransactionStatus.setRollbackOnly()` |
| Một bước JDBC tùy chọn cần rollback mà outer vẫn phải tiếp tục | `NESTED`/savepoint nếu manager và DB hỗ trợ |
| Inner phải commit hoặc rollback độc lập với outer | `REQUIRES_NEW` với đánh giá connection pool/consistency |
| Nghiệp vụ cần commit nhất quán trên nhiều resource hoặc side effects | Thiết kế riêng (outbox, compensation, distributed transaction khi phù hợp) |

Chọn marker khi **có lý do rõ ràng không thể ném exception qua transaction boundary**. Nếu chỉ muốn "bắt lỗi để log rồi tránh ném cho caller" nhưng dữ liệu thực sự phải rollback, cần thiết kế kết quả báo lỗi minh bạch để caller không hiểu lầm.

## 11. Sai lầm thường gặp và cách khắc phục

### 11.1. Bắt ngoại lệ rồi quên đặt rollback-only

Exception bị nuốt nên interceptor không được thông báo. Nếu mục đích là hủy transaction, ném lại exception hoặc gọi marker; kiểm tra dữ liệu sau hoàn tất.

### 11.2. Tin rằng rollbackFor vẫn chạy khi đã catch exception

`rollbackFor` là rule cho exception **thoát ra ngoài** qua interceptor. Nó không tự quét lịch sử exception đã xảy ra trong method. `noRollbackFor` cũng không xóa rollback-only đã có.

### 11.3. Đánh dấu inner REQUIRED và coi outer đã an toàn

Marker ở inner `REQUIRED` có thể lan ra toàn physical transaction. Outer commit có thể phát `UnexpectedRollbackException`. Hãy trả kết quả đúng cho caller và kiểm thử cả outer boundary.

### 11.4. Gọi currentTransactionStatus() ngoài transaction advice

Không có context tương ứng có thể dẫn đến `NoTransactionException`. Trong `TransactionTemplate`, dùng status callback. Với `@Transactional`, bảo đảm lời gọi qua Spring proxy thay vì `this.method()` hoặc object tự `new`.

### 11.5. Nhầm setRollbackOnly với rollback ngay lập tức

Marker không gọi `Connection.rollback()` ngay lập tức. Một `SELECT` trong cùng transaction có thể vẫn thấy dữ liệu chưa commit. Chỉ đánh giá kết quả sau khi transaction vật lý hoàn tất.

### 11.6. Tiếp tục làm side effect không thể rollback

Email, Kafka message, HTTP call hay file đã ghi không tự bị hủy khi JDBC transaction rollback. Đặt các side effect đúng thời điểm hoặc dùng outbox/idempotency/compensation.

### 11.7. Bắt mọi lỗi hạ tầng rồi cố tiếp tục

Một SQL exception có thể khiến DB transaction bị invalidated/aborted. Marker không "chữa" được connection. Thường nên để lỗi hạ tầng lan ra, rollback và retry có kiểm soát.

### 11.8. Dùng TransactionTemplate nhưng quên outer transaction

Template mặc định `REQUIRED`, nên callback có thể tham gia physical transaction đã tồn tại. Nếu muốn rollback riêng, phải thiết kế propagation thật sự phù hợp, không giả định callback luôn độc lập.

### 11.9. Test có @Transactional ngoài ý muốn

Spring TestContext thường mở test transaction rồi rollback cuối test. Inner service `REQUIRED` tham gia scope đó, làm thay đổi kết quả và timing. Trong bài này, test cố ý không có `@Transactional`.

### 11.10. Không đối chiếu dữ liệu

`isRollbackOnly()` cho biết trạng thái cờ, không chứng minh database đã rollback. Dùng ID duy nhất, truy vấn sau transaction bằng một connection/transaction độc lập và so sánh giá trị mong đợi.

## 12. Cách kiểm tra khi kết quả khác dự kiến

**Marker đã đặt nhưng dữ liệu vẫn có:**

- Câu SQL có dùng cùng transaction manager và `DataSource` không, hay một connection khác đã tự commit?
- Có outer transaction chưa hoàn tất hoặc một `REQUIRES_NEW` khác đã commit độc lập?
- Bạn đang đọc một bản ghi cũ trùng ID hay dữ liệu được ghi bởi transaction khác?
- Lời gọi có đi qua Spring proxy và marker có được đặt trên status đúng scope không?
- Có kiểm tra sau physical transaction completion hay chỉ SELECT bên trong transaction chưa kết thúc?

**Không thấy exception nhưng database rollback:**

- Outer scope đã tự `setRollbackOnly()` chưa? Đó có thể là rollback chủ động, không cần ngoại lệ.
- API đang trả `SUCCESS` dù service đã hủy transaction? Sửa contract trả `REJECTED` hoặc result có trạng thái thất bại.

**UnexpectedRollbackException xuất hiện ở outer:**

- Inner `REQUIRED` hoặc một participant khác có đánh dấu rollback-only?
- Outer có catch exception rồi tưởng việc bắt đó xóa cờ?
- Exception xuất hiện khi outer proxy commit (sau khi thân outer return) hay ở method khác?
- Có test-managed outer transaction khiến thời điểm commit thay đổi?

Khi cần, bật log trên môi trường thử nghiệm:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log giúp thấy giao dịch bắt đầu, tham gia và rollback. Tuy nhiên, chỉ đọc log không thay cho việc SELECT dữ liệu **sau transaction kết thúc**.

## 13. Câu hỏi tự kiểm tra

**1.** Một method `@Transactional` ném `IllegalArgumentException` rồi catch ngay trong method và return bình thường, không marker. Theo default có rollback không?

**Đáp án:** Không. Nếu transaction mới không bị rollback-only vì nguyên nhân khác, nó commit vì interceptor nhìn thấy return bình thường.

**2.** Viết `@Transactional(rollbackFor = IllegalArgumentException.class)` có khiến exception đã bị catch trong method kích hoạt rollback không?

**Đáp án:** Không. Rule dành cho exception đi ra khỏi interceptor. Cần ném lại hoặc chủ động đánh dấu rollback-only.

**3.** `setRollbackOnly()` có gọi SQL ROLLBACK tức thì không?

**Đáp án:** Không. Nó yêu cầu rollback khi manager hoàn tất scope; với NESTED có thể rollback về savepoint khi scope con kết thúc.

**4.** Outermost method tự đánh dấu rollback-only, return `REJECTED`. Caller có nhất thiết nhận `UnexpectedRollbackException`?

**Đáp án:** Không. Khi outer scope tự quyết định rollback, Spring có thể rollback bình thường và để caller nhận `REJECTED`.

**5.** Inner `REQUIRED` đánh dấu rollback-only, outer return bình thường. Tại sao caller có thể nhận `UnexpectedRollbackException`?

**Đáp án:** Inner và outer cùng physical transaction. Outer định commit nhưng transaction đã rollback-only, nên Spring rollback và báo commit không thành công.

**6.** Trong `TransactionTemplate`, nên lấy status từ đâu?

**Đáp án:** Dùng `TransactionStatus` do callback nhận trực tiếp và gọi `status.setRollbackOnly()`.

**7.** Nếu chỉ muốn bỏ thao tác JDBC tùy chọn và giữ outer transaction, có nên gọi outer `setRollbackOnly()`?

**Đáp án:** Không. Nếu driver/manager hỗ trợ, dùng `NESTED`/savepoint để rollback phần con; đánh dấu outer sẽ hủy toàn physical transaction.

**8.** Có thể dùng `noRollbackFor` để ép commit một transaction đã bị đánh dấu rollback-only không?

**Đáp án:** Không. `noRollbackFor` chỉ điều chỉnh phản ứng của interceptor đối với exception phù hợp, không xóa trạng thái rollback-only.

## 14. Tài liệu tham khảo chính thức

- Spring Framework — Rolling Back a Declarative Transaction; ví dụ `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation, `REQUIRED` và `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Programmatic Transaction Management, `TransactionTemplate`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `TransactionStatus` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `TransactionAspectSupport` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html
- Spring Framework — `@Transactional` settings và rollback default: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Ghi nhớ:** Khi exception đã được bắt bên trong method, Spring transaction interceptor không tự nhìn thấy exception đó để rollback. `setRollbackOnly()` cho phép chủ động yêu cầu rollback dù method return bình thường. Cần xác định đúng **transaction scope**, **propagation**, **kết quả nghiệp vụ trả về** và **dữ liệu sau khi transaction hoàn tất**.