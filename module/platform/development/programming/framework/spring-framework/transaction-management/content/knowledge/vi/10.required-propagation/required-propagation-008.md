# Kiểm chứng luồng thành công, lỗi lan ra và lỗi bị bắt với Spring REQUIRED

## 1. Mục tiêu

`Propagation.REQUIRED` là chế độ propagation mặc định của `@Transactional` trong Spring Framework. Khi chưa có transaction, phương thức `REQUIRED` tạo một transaction vật lý mới; khi đã có transaction tương thích, nó **tham gia cùng transaction vật lý** của caller. Điều này ảnh hưởng trực tiếp đến kết quả khi có lỗi, nhất là trường hợp outer method **bắt exception** từ inner service rồi tiếp tục.

Bài học này giúp bạn tự kiểm chứng các luồng:

1. **Luồng thành công:** outer và inner `REQUIRED` đều hoàn thành, toàn bộ thay đổi được commit cùng nhau.
2. **Lỗi lan ra:** inner ném unchecked exception, outer không bắt, exception thoát qua cả hai interceptor; toàn transaction rollback.
3. **Lỗi bị outer bắt:** inner `REQUIRED` đã bị transaction interceptor đánh dấu rollback-only trước khi exception tới outer; outer catch và return bình thường nhưng commit vẫn thất bại, thường xuất hiện `UnexpectedRollbackException`.
4. **Lỗi bị bắt ngay trong inner:** lỗi không thoát qua inner transaction interceptor, không ai đánh dấu rollback-only; transaction có thể commit bình thường nếu không còn vấn đề nào khác.

Sau bài học, bạn cũng sẽ biết cách viết integration test xác nhận **dữ liệu đã commit/rollback**, phân biệt exception xảy ra trong method và exception xuất hiện lúc commit, hiểu ảnh hưởng của Spring AOP proxy, và chọn cách xử lý lỗi thích hợp.

**Bối cảnh:** Dịch vụ đặt đơn hàng ghi dữ liệu bắt buộc trước và sau khi gọi bước con. Với `REQUIRED`, bước con không có transaction độc lập, dù đó là một method được đánh dấu `@Transactional` riêng. Vì vậy, một lỗi đã được xử lý ở tầng gọi chưa chắc khiến transaction chung đủ điều kiện commit.

## 2. Cơ chế REQUIRED: logical scope và physical transaction

Giả sử một outer service gọi một inner service, cả hai có `@Transactional(propagation = Propagation.REQUIRED)`:

```text
Caller
  |
  v
OuterService proxy
  |  Tạo physical transaction T
  |  +-- logical scope OUTER
  |       |
  |       +-- INSERT A
  |       |
  |       +-- InnerService proxy
  |       |     +-- logical scope INNER
  |       |          dùng cùng physical transaction T
  |       |          INSERT B
  |       |
  |       +-- INSERT C
  |
  +-- khi OUTER kết thúc: COMMIT hoặc ROLLBACK T
  v
Caller
```

Hai khái niệm quan trọng:

- **Physical transaction:** transaction thực sự trên database connection, có một quyết định commit hoặc rollback cuối cùng.
- **Logical transaction scope:** phạm vi được tạo khi lời gọi đi qua một transactional interceptor. Outer và inner có thể có các metadata/rollback-only status logic riêng, nhưng `REQUIRED` ánh xạ chúng vào **cùng physical transaction** nếu đã có transaction.

Do đó:

- Inner `REQUIRED` không commit độc lập khi method inner trả về bình thường. Commit vật lý vẫn chờ outermost transaction boundary.
- Nếu outer rollback, mọi thay đổi của inner tham gia transaction đó cũng bị hủy.
- Nếu inner transaction scope đánh dấu transaction chung **rollback-only**, outer không thể hủy cờ đó chỉ bằng `try/catch` hay `return` bình thường.
- Trong cấu hình Spring mặc định, khi inner participant làm transaction chung rollback-only mà outer vẫn cố commit, Spring ném `UnexpectedRollbackException` để caller không bị hiểu nhầm là commit đã thành công.

### Khi nào REQUIRED mở transaction mới?

| Context khi gọi method REQUIRED | Hành vi | Ai quyết định commit cuối? |
| --- | --- | --- |
| Chưa có transaction | Mở physical transaction mới | Transaction interceptor của method đó |
| Đã có transaction tương thích | Tham gia physical transaction đang mở | Scope ngoài cùng sở hữu physical transaction |
| Method chỉ gọi `this.inner()` trong cùng bean | Có thể bỏ qua proxy của inner method | Chỉ những interceptor thực sự được đi qua mới áp dụng metadata |
| Dùng `@Async`/thread mới | Transaction thread-bound không tự truyền qua thread khác | Phụ thuộc transaction mới thực sự được mở ở thread đó |

Trong bài này, mọi lời gọi được thực hiện từ một `CommandLineRunner` **không có transaction ngoài**. Outer service nằm trong bean Spring riêng; inner service cũng là bean Spring riêng để cả hai interceptor đều hoạt động. Điều đó giúp quan sát rõ logic `REQUIRED` mà không vô tình dùng self-invocation.

## 3. Luồng 1 — thành công: outer và inner cùng commit

```text
T0: caller -> outer proxy -> BEGIN T
T1: outer INSERT id=101
T2: inner proxy -> tham gia T, INSERT id=102
T3: inner return bình thường -> không commit vật lý
T4: outer INSERT id=103, return bình thường
T5: outer proxy -> COMMIT T thành công
T6: caller SELECT -> [101, 102, 103]
```

Mọi câu SQL ở bước T1, T2, T4 dùng cùng transaction. Điều quan trọng là **T3 chưa commit**, dù inner method đã kết thúc. Khi outer trả về và commit thành công tại T5, connection đọc mới sẽ thấy tất cả ba bản ghi.

Nếu outer ném exception thỏa rollback rule sau khi inner đã return thành công, inner cũng bị rollback. Vì vậy một inner `REQUIRED` "đã thành công" mới chỉ là thành công ở **logical scope**, chưa phải dữ liệu được commit bền vững.

## 4. Luồng 2 — lỗi lan ra: rollback toàn transaction

Inner ghi một bản ghi rồi ném `IllegalStateException`, outer **không catch**:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=201
T2: inner proxy -> tham gia T
T3: inner INSERT id=202
T4: inner throw IllegalStateException
T5: inner interceptor nhận unchecked exception
    -> đánh dấu shared transaction rollback-only
    -> ném tiếp exception ra outer
T6: outer method không catch -> outer interceptor nhận exception
    -> ROLLBACK T
T7: caller bắt IllegalStateException
T8: caller SELECT -> [] (không có id=201,202)
```

Với cấu hình mặc định:

- `RuntimeException` và `Error` kích hoạt rollback khi thoát qua transaction interceptor.
- Checked exception thường **không** kích hoạt rollback mặc định, trừ khi khai báo `rollbackFor` hoặc có rule mặc định khác được cấu hình. Nếu thay `IllegalStateException` bằng checked exception rồi để exception thoát ra mà **không** cấu hình rollback, có thể xảy ra **commit rồi ném exception**.
- Nếu exception được ném **sau khi có SQL**, dữ liệu chưa commit không tự "còn lại" chỉ vì JDBC đã báo UPDATE thành công; transaction manager mới quyết định kết quả cuối cùng.

Ví dụ annotation đổi rollback policy cho checked exception:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = java.io.IOException.class
)
public void importData() throws java.io.IOException {
    // Thực hiện JDBC và có thể ném IOException.
}
```

Đoạn này chỉ minh họa rule, chưa phải class chạy độc lập. Muốn kiểm chứng đúng hãy thử với service và exception cụ thể, sau đó đọc database **sau khi proxy invocation kết thúc**.

## 5. Luồng 3 — outer bắt lỗi từ inner REQUIRED: vẫn rollback

Đây là trường hợp dễ gây nhầm lẫn nhất:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=301
T2: inner proxy -> tham gia T, INSERT id=302
T3: inner throw IllegalStateException
T4: inner interceptor đánh dấu T rollback-only, rồi rethrow
T5: outer catch IllegalStateException -> in "đã xử lý"
T6: outer INSERT id=303, return bình thường
T7: outer interceptor cố COMMIT T nhưng T đã rollback-only
T8: Spring ROLLBACK T và ném UnexpectedRollbackException
T9: caller SELECT -> [] (301,302,303 đều không còn)
```

Outer đã bắt lỗi thật, nhưng **nó bắt sau khi inner interceptor xử lý lỗi**. Trong `REQUIRED`, transaction vật lý T đã bị đánh dấu rollback-only tại T4. Catch ở outer không xóa được cờ.

`UnexpectedRollbackException` xuất hiện tại **thời điểm outer interceptor hoàn tất transaction**. Nó có thể xảy ra **sau khi thân method outer đã return**, nên đoạn `try/catch` bên trong thân outer chỉ bao quanh lời gọi inner sẽ không bắt được exception commit của chính outer proxy. Caller của outer proxy mới là nơi quan sát được exception đó.

Đây là chủ ý của Spring: nếu inner đã khiến database transaction bị rollback nhưng outer tưởng mình sẽ commit, Spring phải báo **commit không thành công**, tránh để caller nhận tín hiệu thành công giả.

**Lưu ý điều kiện:** Mô tả này áp dụng cơ chế `REQUIRED` thông thường và transaction manager cấu hình mặc định (đặc biệt việc rollback lỗi của inner participant đánh dấu global rollback-only). Nếu chỉnh sâu các cờ như `globalRollbackOnParticipationFailure` hoặc dùng transaction manager đặc thù, cần kiểm chứng lại semantics. Không sửa các cờ này chỉ để che `UnexpectedRollbackException`.

## 6. Luồng 4 — lỗi bị bắt ngay trong inner trước khi qua interceptor: có thể commit

Cũng là `IllegalStateException`, nhưng inner tự bắt:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=401
T2: inner proxy -> tham gia T, INSERT id=402
T3: inner ném rồi tự bắt IllegalStateException trong chính thân method
T4: inner method return bình thường; inner interceptor không thấy lỗi
T5: outer INSERT id=403, return bình thường
T6: outer proxy COMMIT T
T7: caller SELECT -> [401,402,403]
```

**So sánh hai cách bắt lỗi:**

| Vị trí catch | Inner interceptor có thấy exception không? | Transaction vật lý mặc định | Kết quả thường gặp |
| --- | --- | --- | --- |
| Inner tự catch trước khi return | **Không** | Không tự rollback do exception đó | Commit nếu outer bình thường |
| Outer catch **sau** khi inner proxy rethrow | **Có** | Inner đã đánh dấu rollback-only | Rollback, có thể `UnexpectedRollbackException` |
| Caller catch sau khi outer proxy rethrow | Outer cũng thấy lỗi | Outer rollback khi exit | Rollback, caller nhận exception gốc |
| Inner catch và chủ động `setRollbackOnly()` | Không có exception đi ra, nhưng có rollback-only | Transaction không còn đủ điều kiện commit | Rollback; nếu inner `REQUIRED` tham gia outer, có thể `UnexpectedRollbackException` |

Nếu bạn cần catch ngay trong inner nhưng **vẫn yêu cầu hủy** toàn transaction, có thể chủ động đánh dấu rollback-only:

```java
catch (IllegalStateException ex) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

Fragment này chỉ dùng trong method đang được Spring transaction interceptor quản lý. Khi inner `REQUIRED` tham gia outer, marker thường làm transaction chung rollback-only. Nếu ý định nghiệp vụ chỉ là **bỏ phần thay đổi inner**, nhưng outer vẫn commit, cần thiết kế cơ chế khác như `NESTED` với JDBC savepoint khi manager/driver hỗ trợ hoặc điều chỉnh transaction boundary; `REQUIRED` không cho phép rollback cục bộ độc lập.

## 7. Ví dụ thực hành hoàn chỉnh: Spring Boot, JDBC, H2, Java 17+

Dự án chạy bốn luồng ở trên và in dữ liệu thực sự còn lại sau mỗi transaction. Dùng **Spring Boot 3.3.5**, **Java 17+**, Spring JDBC và H2. Maven là công cụ build; Spring Boot tự cấu hình `DataSource` và JDBC transaction manager khi có dependencies thích hợp.

### 7.1. Cấu trúc thư mục

```text
required-flows-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RequiredFlowsApplication.java
    │   │   ├── OuterFlowService.java
    │   │   └── RequiredInnerService.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── RequiredFlowsIntegrationTest.java
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
    <artifactId>required-flows-demo</artifactId>
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

`spring-boot-starter-jdbc` mang `JdbcTemplate` và transaction support; H2 là database trong JVM. `spring-boot-starter-test` cho phép viết integration test bằng JUnit 5.

### 7.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:required_flows;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

`required_flows` là tên database in-memory. Nhiều connection trong cùng JVM với URL đó trỏ đến cùng database; `DB_CLOSE_DELAY=-1` giữ DB trong vòng đời JVM demo. Mỗi lần chạy bằng một JVM mới, bảng được tạo lại từ đầu.

### 7.4. RequiredInnerService.java — ba hành vi inner, đều REQUIRED

**`src/main/java/demo/RequiredInnerService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiredInnerService {
    private final JdbcTemplate jdbc;

    public RequiredInnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(long id, String description) {
        insert(id, description);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeThenFail(long id) {
        insert(id, "inner-fails");
        throw new IllegalStateException("inner failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeAndCatchInside(long id) {
        insert(id, "inner-caught");

        try {
            throw new IllegalStateException("handled inside inner");
        } catch (IllegalStateException expected) {
            // Chỉ dành cho demo: method xử lý lỗi, không ném lại,
            // không đặt rollback-only; interceptor thấy return bình thường.
        }
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO flow_event(id, description) VALUES (?, ?)",
                id, description);
    }
}
```

`write`: inner scope kết thúc bình thường; không commit riêng khi có outer. `writeThenFail`: exception thoát qua inner interceptor và kích hoạt rollback rule mặc định; sau đó exception tiếp tục tới outer. `writeAndCatchInside`: exception bị bắt trong method nên inner interceptor không thấy, cũng không có marker. Kết quả khác nhau nằm ở **vị trí exception bị xử lý**, không phải ở loại JDBC statement.

### 7.5. OuterFlowService.java — bốn luồng có thể so sánh trực tiếp

**`src/main/java/demo/OuterFlowService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterFlowService {
    private final JdbcTemplate jdbc;
    private final RequiredInnerService inner;

    public OuterFlowService(JdbcTemplate jdbc, RequiredInnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success(long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");
        inner.write(innerId, "inner-ok");
        insert(afterId, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void propagateRuntime(long beforeId, long innerId) {
        insert(beforeId, "outer-before");
        inner.writeThenFail(innerId);
        // Exception thoát ra; code sau lời gọi inner không chạy.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchAfterInnerProxy(
            long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");

        try {
            inner.writeThenFail(innerId);
        } catch (IllegalStateException expected) {
            System.out.println("outer caught inner exception");
        }

        // Vẫn chạy nhưng transaction vật lý đã rollback-only.
        insert(afterId, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchInsideInner(
            long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");
        inner.writeAndCatchInside(innerId);
        insert(afterId, "outer-after");
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO flow_event(id, description) VALUES (?, ?)",
                id, description);
    }
}
```

`OuterFlowService` được Spring khởi tạo qua `@Service` và inject `RequiredInnerService` qua constructor. Lời gọi `inner.method()` đi qua proxy của bean **khác**. Nếu thay lời gọi bằng `this.someAnnotatedInnerMethod()` trong cùng object, transactional advice của inner method có thể bị bỏ qua (proxy mode), khiến kết quả khác dự đoán.

### 7.6. RequiredFlowsApplication.java — tạo bảng và đối chiếu sau khi service kết thúc

**`src/main/java/demo/RequiredFlowsApplication.java`**

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
public class RequiredFlowsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredFlowsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, OuterFlowService outer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE flow_event (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            outer.success(101L, 102L, 103L);
            System.out.println(
                    "success rows: " + readIds(jdbc, 101L, 103L));

            try {
                outer.propagateRuntime(201L, 202L);
            } catch (IllegalStateException ex) {
                System.out.println(
                        "propagated exception: " + ex.getMessage());
            }
            System.out.println(
                    "propagated rows: " + readIds(jdbc, 201L, 202L));

            try {
                outer.catchAfterInnerProxy(301L, 302L, 303L);
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "outer commit exception: UnexpectedRollbackException");
            }
            System.out.println(
                    "caught after inner rows: " + readIds(jdbc, 301L, 303L));

            outer.catchInsideInner(401L, 402L, 403L);
            System.out.println(
                    "caught inside inner rows: " + readIds(jdbc, 401L, 403L));
        };
    }

    private static List<Long> readIds(
            JdbcTemplate jdbc, long from, long to) {
        return jdbc.queryForList(
                "SELECT id FROM flow_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, from, to);
    }
}
```

**Vì sao phép kiểm chứng này đáng tin?**

- `CommandLineRunner` không được đánh dấu `@Transactional`, nên mỗi lời gọi outer service tự sở hữu physical transaction mới theo `REQUIRED`.
- Sau khi `outer.success(...)` trả về qua proxy, transaction đã commit. SELECT phía sau nằm ngoài transaction đó.
- Sau khi `outer.propagateRuntime(...)` ném lỗi qua proxy, transaction đã rollback trước khi caller bắt exception.
- Khi `outer.catchAfterInnerProxy(...)` trả về từ thân method nhưng commit thất bại vì rollback-only, ngoại lệ `UnexpectedRollbackException` được bắt ở **caller**. SELECT sau `catch` xác nhận không có hàng nào của luồng đó.
- Khi `outer.catchInsideInner(...)` trả về qua proxy, không có scope nào đánh dấu rollback-only; database commit cả ba hàng.

Mỗi luồng dùng một dải ID riêng. Đọc theo ID tránh sai kết luận do dữ liệu thuộc luồng khác. `JdbcTemplate` sau service không còn transaction đang bind trên thread nên sử dụng connection đọc bên ngoài transaction vừa hoàn tất.

### 7.7. Chạy và quan sát stdout

Cần JDK 17+, Maven và network/cached dependencies để tải thư viện lần đầu:

```bash
mvn spring-boot:run
```

Các dòng do chính chương trình in (không tính log Spring/Maven):

```text
success rows: [101, 102, 103]
propagated exception: inner failure
propagated rows: []
outer caught inner exception
outer commit exception: UnexpectedRollbackException
caught after inner rows: []
caught inside inner rows: [401, 402, 403]
```

Đọc kết quả theo từng trường hợp:

| Luồng | Kết thúc inner | Kết thúc outer | Dữ liệu sau giao dịch |
| --- | --- | --- | --- |
| Thành công | Return, không rollback-only | Commit | `[101, 102, 103]` |
| Lỗi lan ra | Throw unchecked, inner đánh dấu rollback-only | Outer rollback và ném lỗi gốc | `[]` |
| Outer bắt lỗi inner | Inner đã đánh dấu rollback-only trước khi outer catch | Rollback, caller nhận `UnexpectedRollbackException` | `[]` |
| Inner tự bắt lỗi | Inner return, không đánh dấu rollback-only | Commit | `[401, 402, 403]` |

**Kết luận của phép kiểm chứng:** `try/catch` không tự tạo ra một chính sách transaction mới. Hành vi phụ thuộc **exception đi qua interceptor nào**, transaction status có bị đánh dấu rollback-only hay chưa, và boundary nào thực hiện commit cuối.

## 8. Integration test: assert dữ liệu, exception và thời điểm hoàn tất

Đưa logic vào test giúp bạn phát hiện thay đổi propagation, rollback rule hoặc lời gọi proxy làm đổi kết quả. Test không mang `@Transactional` ở class/method để không tạo outer test transaction ngoài ý muốn.

**`src/test/java/demo/RequiredFlowsIntegrationTest.java`**

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class RequiredFlowsIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private OuterFlowService outer;

    @Test
    void successCommitsAllWrites() {
        outer.success(1001L, 1002L, 1003L);

        assertEquals(
                List.of(1001L, 1002L, 1003L),
                readIds(1001L, 1003L));
    }

    @Test
    void propagatedRuntimeRollsBackEntireTransaction() {
        assertThrows(
                IllegalStateException.class,
                () -> outer.propagateRuntime(2001L, 2002L));

        assertEquals(List.of(), readIds(2001L, 2002L));
    }

    @Test
    void catchingAfterInnerProxyDoesNotRestoreCommit() {
        assertThrows(
                UnexpectedRollbackException.class,
                () -> outer.catchAfterInnerProxy(
                        3001L, 3002L, 3003L));

        assertEquals(List.of(), readIds(3001L, 3003L));
    }

    @Test
    void catchingInsideInnerWithoutRollbackMarkerCanCommit() {
        outer.catchInsideInner(4001L, 4002L, 4003L);

        assertEquals(
                List.of(4001L, 4002L, 4003L),
                readIds(4001L, 4003L));
    }

    private List<Long> readIds(long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM flow_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** cả 4 test pass. Spring Boot khởi tạo `ApplicationContext`; `CommandLineRunner` chạy trước khi test method bắt đầu, tạo bảng và thực hành với ID 101–403. Test sử dụng các ID khác (1001–4003) nên không trùng dữ liệu demo. Các test không tự mở outer transaction; vì vậy phương thức outer `REQUIRED` đã hoàn tất trước khi query trong assertion.

### Vì sao không gắn `@Transactional` lên cả test?

Spring TestContext có thể tự mở **test-managed transaction** cho test mang `@Transactional` và mặc định rollback khi test kết thúc. Khi đó:

1. `outer.success()` `REQUIRED` sẽ tham gia transaction của test, nên khi outer service trả về **chưa có commit vật lý**.
2. `outer.catchAfterInnerProxy()` có thể không ném `UnexpectedRollbackException` tại thời điểm bạn kỳ vọng, vì commit thật diễn ra ở boundary ngoài do test quản lý.
3. `JdbcTemplate` trong test có thể dùng cùng connection/transaction và thấy dữ liệu chưa commit; kiểm tra như vậy không xác nhận commit thực.
4. Test framework rollback cuối test có thể khiến dữ liệu biến mất ngay cả khi service không tự rollback.

Để kiểm chứng chính xác các luồng `REQUIRED`, nên test từ caller **ngoài transaction** và query sau khi lời gọi service hoàn tất. Nếu thực sự cần test-managed transaction, có thể dùng `TestTransaction` để kết thúc transaction trước khi đối chiếu, nhưng phải chủ động chọn commit/rollback và cô lập dữ liệu kiểm thử.

### Không chỉ assert exception

Một test như `assertThrows(IllegalStateException.class, () -> outer.propagateRuntime(...))` mới xác nhận tín hiệu Java; nếu không SELECT dữ liệu sau transaction, bạn chưa chứng minh được phần SQL đã bị rollback. Ngược lại, chỉ thấy `[]` cũng chưa chứng minh đúng exception cần được truyền ra caller. Test tốt kiểm tra **cả exception và trạng thái database**.

## 9. Nếu muốn bắt lỗi mà vẫn commit một phần thì sao?

Với `REQUIRED` thông thường, inner và outer thuộc **một** physical transaction. Khi inner interceptor đã đặt rollback-only, outer catch rồi tiếp tục không thể "cứu" commit của transaction chung bằng cách xóa marker.

Có ba hướng thiết kế, tùy yêu cầu:

1. **Toàn bộ cùng thành/bại:** Giữ `REQUIRED` và để lỗi quan trọng thoát qua outer proxy, hoặc chủ động đánh dấu outer rollback-only và trả kết quả thất bại. Đây là hành vi nguyên tử mặc định.
2. **Một bước JDBC optional được phép rollback cục bộ:** Cân nhắc `Propagation.NESTED` và JDBC savepoint, nếu `PlatformTransactionManager`/driver/database hỗ trợ. Khi inner lỗi, Spring rollback về savepoint; outer có thể bắt lỗi, tiếp tục và cuối cùng commit phần còn lại. `NESTED` vẫn chia sẻ transaction vật lý và không commit độc lập.
3. **Một bước cần transaction độc lập:** `Propagation.REQUIRES_NEW` tạo physical transaction riêng, suspend outer khi cần. Inner có thể rollback mà không đánh dấu rollback-only của outer, nhưng cũng có thể commit độc lập dù outer rollback sau đó; có chi phí connection và rủi ro nhất quán cần cân nhắc.

Đừng đổi sang `REQUIRES_NEW` chỉ để làm biến mất `UnexpectedRollbackException` mà chưa xác định xem kết quả inner có được phép commit độc lập không. Tương tự, chỉnh cờ transaction manager để bỏ đánh dấu global rollback-only có thể làm database transaction tiếp tục sau lỗi không an toàn trên một số hệ quản trị.

### Một cách khác: catch trong cùng outer scope trước khi exception qua inner interceptor

Nếu inner chỉ là helper không có transaction advice riêng, exception được outer bắt **trước khi đi qua outer transaction interceptor**, outer có thể commit sau catch. Nhưng điều đó chỉ đúng khi nghiệp vụ thật sự **được phép giữ các ghi trước lỗi**, không phải mẹo dùng self-invocation để né transaction boundaries. Giải pháp tốt nên làm ranh giới transaction và chính sách lỗi rõ ràng, dễ kiểm thử.

## 10. Các lỗi thường gặp khi kiểm chứng REQUIRED

### 10.1. "Outer đã catch rồi nên chắc chắn commit"

Sai nếu exception đã đi qua một inner `@Transactional(REQUIRED)` interceptor và đánh dấu transaction chung rollback-only. Khi outer commit, `UnexpectedRollbackException` có thể xuất hiện. Luôn kiểm tra dữ liệu sau outer proxy.

### 10.2. Nhầm return của inner với COMMIT

Inner `REQUIRED` tham gia physical transaction của outer. Inner return không có commit độc lập; outer rollback hủy cả phần inner. Đừng kiểm tra kết quả bằng một query trong outer transaction rồi tuyên bố dữ liệu đã commit.

### 10.3. Bắt lỗi trong inner và nghĩ Spring tự rollback

Nếu inner tự catch, không rethrow và không `setRollbackOnly()`, interceptor thấy return bình thường. Ghi nhận ngoại lệ vào log không thay thế transaction rollback policy.

### 10.4. Bắt mọi exception và tiếp tục ghi dù database đã hỏng

Một số lỗi JDBC/constraint có thể khiến transaction DB không còn usable (tùy DB/driver). Đừng nuốt tất cả `Exception` rồi tiếp tục commit trong khi trạng thái không chắc chắn. Tổ chức rollback và retry có kiểm soát khi cần.

### 10.5. Đổi unchecked thành checked exception nhưng quên rollbackFor

Spring mặc định rollback với `RuntimeException`/`Error`; checked exception thường không rollback theo default. Nếu thay đổi exception hierarchy hoặc dùng `IOException` trong nghiệp vụ, hãy xét `@Transactional(rollbackFor = IOException.class)` và bổ sung test.

### 10.6. Self-invocation bỏ qua Spring AOP

Lời gọi `this.innerMethod()` trong cùng bean ở proxy mode thường không đi qua inner transaction interceptor. Vì vậy một test có thể commit dù thiết kế ban đầu kỳ vọng inner đánh dấu rollback-only. Dùng một Spring bean riêng và gọi qua proxy như ví dụ.

### 10.7. Tự mở JDBC connection rồi commit ngoài Spring

`DataSourceTransactionManager` chỉ điều khiển connection thuộc transaction của nó. Nếu service tự mở connection khác và `autoCommit=true`, dữ liệu có thể đã commit độc lập và không bị outer rollback. Dùng `JdbcTemplate` với đúng `DataSource`.

### 10.8. Đọc lại từ cùng transaction để "xác nhận commit"

Trong transaction, connection ghi có thể thấy dữ liệu chưa commit của chính nó. Để xác nhận, hãy đợi **outermost physical transaction** hoàn tất rồi đọc bằng connection/transaction độc lập đúng primary database. Snapshot lâu dưới `REPEATABLE_READ` hoặc read replica chậm cũng có thể khiến kết quả đọc khác.

### 10.9. Test @Transactional tạo outer boundary ngoài ý muốn

TestContext mặc định rollback các test-managed transaction. Nếu test đã mở transaction, outer service của bạn thực ra chỉ là inner participant. Tránh `@Transactional` trên test khi muốn kiểm chứng commit của service ở đúng thời điểm.

### 10.10. Chỉ nhìn log "caught" rồi cho rằng dữ liệu được giữ

Console `outer caught inner exception` chỉ chứng minh Java `catch` chạy. Ngay sau đó interceptor vẫn có thể rollback toàn bộ. Phải đặt SELECT **sau khi caller đã ra khỏi proxy** và xác minh theo ID.

## 11. Chiến lược gỡ lỗi khi kết quả khác kỳ vọng

Nếu case thành công không commit:

- Có lỗi ở transaction commit, constraint hoặc SQL trước đó không?
- Outer có bị đánh dấu rollback-only ở một participant khác?
- Bạn đang kiểm tra dữ liệu trên cùng database/schema/tenant không?
- Caller đã ra khỏi outermost proxy hay còn outer/test transaction chưa hoàn tất?

Nếu case lỗi lan ra vẫn còn dữ liệu:

- Exception thực tế là checked hay unchecked? `rollbackFor` có phù hợp không?
- Transaction annotation có hoạt động qua proxy không? Có self-invocation hay bean được tạo bằng `new`?
- JdbcTemplate có tham gia đúng DataSource của transaction manager không?
- Có một `REQUIRES_NEW` hoặc connection tự commit trước khi outer rollback không?
- ID đã tồn tại từ lần chạy trước hay transaction khác không?

Nếu outer bắt lỗi mà không nhận `UnexpectedRollbackException`:

- Inner method thực sự có `@Transactional(REQUIRED)` và được gọi qua **proxy** không?
- Lỗi có thoát qua inner interceptor hay đã bị bắt trước đó?
- Có đang dùng transaction manager cấu hình khác mặc định?
- Outer đang tham gia transaction rộng hơn, nên lỗi commit thực sự sẽ xuất hiện **sau** tại boundary ngoài cùng?
- Test có `@Transactional` làm thay đổi ranh giới không?

Trong môi trường thực hành, có thể tăng transaction log bằng cấu hình Spring Boot:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Chỉ bật log chi tiết khi cần. Log transaction hỗ trợ tìm boundary và cờ rollback-only, nhưng **đối chiếu kết quả SQL cuối cùng** mới xác nhận dữ liệu còn hay không.

## 12. Bài tập và câu hỏi kiểm tra

**Bài 1 — Thành công:** Trong ví dụ, inner `write(...)` return bình thường rồi outer ném `IllegalStateException` sau INSERT cuối. Dữ liệu [101,102,103] có được commit không?

**Đáp án:** Không. Inner `REQUIRED` không commit riêng; outer exception thỏa rollback rule, nên toàn physical transaction rollback.

**Bài 2 — Đổi vị trí catch:** Nếu chuyển catch từ `OuterFlowService.catchAfterInnerProxy` vào trong `RequiredInnerService.writeThenFail`, không rethrow và không marker, còn kết quả `UnexpectedRollbackException` không?

**Đáp án:** Không còn do exception đó, nếu các điều kiện khác giữ nguyên. Inner interceptor thấy return bình thường, outer có thể commit cả các INSERT.

**Bài 3 — Vì sao catch không cứu được?** Outer catch `IllegalStateException` từ inner `REQUIRED`, nhưng khi outer return caller nhận `UnexpectedRollbackException`. Cơ chế nào đã xảy ra?

**Đáp án:** Inner interceptor đã đánh dấu physical transaction chung rollback-only. Outer cố commit nhưng manager buộc rollback và báo kết quả bất ngờ tại outer boundary.

**Bài 4 — Thời điểm throw:** Vì sao đặt `try/catch(UnexpectedRollbackException)` bên trong thân outer method quanh lời gọi inner có thể không bắt được lỗi commit của outer?

**Đáp án:** Transaction interceptor ngoài thực hiện commit/rollback **sau khi thân outer method đã return**; caller của outer proxy mới nhận exception khi hoàn tất transaction.

**Bài 5 — Checked exception:** Một inner `REQUIRED` ném `IOException` thoát qua proxy, không có `rollbackFor`. Có chắc rollback không?

**Đáp án:** Không. Checked exception mặc định không đánh dấu rollback theo rule thông thường; Spring có thể commit nếu không có rollback-only hoặc lỗi khác.

**Bài 6 — Test transaction:** Bạn thêm `@Transactional` lên integration test rồi gọi `outer.success(...)`. Lời gọi service return có chứng minh database đã commit không?

**Đáp án:** Không. `REQUIRED` tham gia test-managed transaction đang mở; commit/rollback thật ở test boundary và TestContext mặc định rollback.

**Bài 7 — Cần rollback riêng bước con:** Có nên chỉ đổi `REQUIRED` thành `REQUIRES_NEW` nếu muốn giữ outer khi inner lỗi?

**Đáp án:** Chỉ sau khi cân nhắc tính độc lập transaction của bước con. `REQUIRES_NEW` có commit độc lập; nếu cần savepoint trong cùng transaction JDBC, xem `NESTED` khi được hỗ trợ.

**Bài 8 — Đọc dữ liệu:** Tại sao `SELECT` ngay trong `outer.success()` có thể nhìn thấy id=102 trước khi outer proxy commit?

**Đáp án:** JDBC connection trong transaction thường thấy các thay đổi chưa commit của chính nó. Phép đọc đó không phải bằng chứng commit.

## 13. Tài liệu tham khảo chính thức

- Spring Framework — **Transaction Propagation**, giải thích logical/physical scope của `PROPAGATION_REQUIRED` và `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Rolling Back a Declarative Transaction**, quy tắc mặc định với unchecked/checked exception: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — **Using @Transactional**, các thuộc tính mặc định và `rollbackFor`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **Declarative Transaction Management Explained**, vai trò proxy và transaction interceptor: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **TestContext Transaction Management**, test-managed transaction và rollback mặc định: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html

**Ghi nhớ:** Với `REQUIRED`, outer và inner dùng **cùng một physical transaction** khi outer đã mở transaction. Thành công chỉ được xác nhận tại commit ngoài cùng; lỗi unchecked lan ra thường rollback toàn bộ; một exception đã đi qua inner interceptor có thể khiến transaction chung rollback-only dù outer bắt lỗi; còn exception được bắt *trước khi* đi qua interceptor có thể cho phép commit nếu không có marker. Hãy kiểm chứng cả **tín hiệu Java** và **dữ liệu cuối cùng** sau outermost boundary.