# Savepoint và rollback một phần trong Spring Framework

## 1. Mục tiêu và bài toán

Sau bài này, bạn có thể:

- Giải thích savepoint và cách rollback một phần trong một transaction còn hoạt động.
- Phân biệt rollback đến savepoint, rollback toàn transaction, release savepoint và commit.
- Dùng `@Transactional(propagation = Propagation.NESTED)` trong Spring JDBC.
- Tạo và điều khiển savepoint bằng `TransactionStatus`/`TransactionTemplate`.
- So sánh `REQUIRED`, `NESTED`, `REQUIRES_NEW` và nhận diện giới hạn khi dùng JPA, JTA hoặc tác vụ ngoài database.
- Kiểm tra dữ liệu thực tế còn lại sau khi inner scope thất bại.

**Bài toán:** Trong nghiệp vụ ghi đơn hàng, bước chính phải thành công; bước ghi dữ liệu bổ sung có thể bỏ qua nếu dữ liệu tùy chọn không hợp lệ. Nếu bước bổ sung thất bại, ta muốn hủy chỉ các lệnh SQL của bước đó rồi tiếp tục. Nhưng nếu bước chính cuối cùng thất bại, toàn bộ thay đổi vẫn phải rollback.

Savepoint cho phép làm điều này **trong cùng một database transaction**. Spring ánh xạ cơ chế savepoint JDBC vào propagation `NESTED`.

## 2. Savepoint là gì?

Một transaction thông thường có ranh giới `BEGIN → COMMIT/ROLLBACK`. `COMMIT` xác nhận mọi thay đổi; `ROLLBACK` hủy những thay đổi chưa commit của transaction.

**Savepoint** là mốc được đặt *bên trong transaction*. `ROLLBACK TO SAVEPOINT` hủy những thay đổi được thực hiện **sau mốc**, còn các thay đổi trước mốc vẫn thuộc transaction hiện hành và chưa được commit.

Ví dụ SQL (cú pháp cụ thể tùy database):

```sql
BEGIN;

INSERT INTO audit_event(id, description) VALUES (1, 'main-before');

SAVEPOINT optional_part;
INSERT INTO audit_event(id, description) VALUES (2, 'optional');

ROLLBACK TO SAVEPOINT optional_part;

INSERT INTO audit_event(id, description) VALUES (3, 'main-after');
COMMIT;
```

Sau `COMMIT`, bảng còn hàng `id = 1` và `id = 3`; `id = 2` bị rollback về savepoint.

| Mốc | Thao tác | Thay đổi chưa commit còn hiệu lực |
| --- | --- | --- |
| T0 | Bắt đầu transaction | Không có |
| T1 | INSERT id=1 | 1 |
| T2 | Tạo savepoint S | 1 |
| T3 | INSERT id=2 | 1, 2 |
| T4 | Rollback đến S | 1 |
| T5 | INSERT id=3 | 1, 3 |
| T6 | COMMIT ngoài | 1 và 3 được xác nhận |

Điểm cốt lõi:

1. `ROLLBACK TO SAVEPOINT` **không commit** phần dữ liệu phía trước mốc. Nếu outer transaction rollback sau T5, cả id=1 lẫn id=3 cũng bị hủy.
2. `RELEASE SAVEPOINT` chỉ giải phóng mốc, không commit dữ liệu.
3. Database có thể hỗ trợ nhiều savepoint, nhưng rollback về mốc trước có thể làm mất hiệu lực các mốc tạo sau. Cần kiểm tra quy tắc của database/driver.
4. Savepoint chỉ quản lý những thay đổi thuộc cùng database transaction; nó không hoàn tác email, file, HTTP request, message đã publish hoặc transaction ở connection khác.
5. DDL/loại storage engine và mức hỗ trợ savepoint của database có thể tạo ra khác biệt. Không suy ra hành vi production chỉ từ một DB thử nghiệm.

## 3. Cơ chế NESTED của Spring

Spring sử dụng `PlatformTransactionManager` để quản lý transaction. Với JDBC và một `DataSource`, `DataSourceTransactionManager` hỗ trợ JDBC savepoint; `JdbcTransactionManager` là biến thể mở rộng có dịch ngoại lệ commit/rollback.

Khi một outer transaction đã hoạt động gọi một phương thức được đánh dấu `@Transactional(propagation = Propagation.NESTED)` **qua Spring proxy**:

1. Transaction manager phát hiện transaction vật lý hiện có.
2. Spring tạo savepoint trên **cùng JDBC Connection**.
3. Các lệnh JDBC trong nested method chạy trên cùng transaction vật lý.
4. Nếu nested method trả về bình thường, nested scope kết thúc; chưa có commit vật lý.
5. Nếu method ném ngoại lệ thỏa rollback rule, Spring rollback đến savepoint rồi truyền ngoại lệ lại caller.
6. Outer caller có thể bắt ngoại lệ, tiếp tục và commit. Nếu sau đó outer rollback, mọi dữ liệu chưa commit của cả outer và inner đều bị hủy.

```text
Outer transaction: một connection, một COMMIT cuối cùng
|-- INSERT A
|-- [SAVEPOINT S] ---------+
|      INSERT B           |
|      lỗi → ROLLBACK S --+
|-- INSERT C
+-- COMMIT  => A, C còn; B mất
```

`NESTED` tạo **nhiều ranh giới rollback logic trong một transaction vật lý**; nó không tạo commit độc lập cho phần con.

### Điều kiện cần

- Có outer transaction đang hoạt động nếu mục tiêu là rollback một phần và vẫn tiếp tục outer. Không có outer transaction thì `NESTED` bắt đầu transaction mới, tương tự `REQUIRED`.
- Transaction manager cho phép nested transaction và JDBC driver/database hỗ trợ savepoints. `DataSourceTransactionManager` mặc định bật `nestedTransactionAllowed`; vẫn cần kiểm chứng driver thật.
- Công việc phải dùng cùng `DataSource` và connection được Spring gắn với transaction hiện tại. `JdbcTemplate` tham gia connection này tự động.
- Lời gọi annotated method phải đi qua Spring AOP proxy. Gọi `this.someNestedMethod()` trong cùng bean thường bỏ qua interceptor ở proxy mode.
- Spring transaction đồng bộ dựa trên thread; không mặc nhiên lan qua `@Async` hoặc thread mới.

## 4. Ví dụ chạy được: inner rollback, outer vẫn commit

Ví dụ dùng **Java 17+, Spring Boot 3.5.16, Spring JDBC, H2** và Maven. Spring Boot cấu hình `DataSource` và JDBC transaction manager từ dependency. Nested method đặt trong bean riêng để Spring proxy thực sự xử lý propagation.

Cấu trúc dự án:

```text
savepoint-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── SavepointApplication.java
    │   ├── OuterService.java
    │   └── OptionalService.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>savepoint-demo</artifactId>
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

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:savepoints;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

**`src/main/java/demo/SavepointApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class SavepointApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavepointApplication.class, args);
    }

    @Bean
    CommandLineRunner example(JdbcTemplate jdbc, OuterService outerService) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE audit_event (
                    id BIGINT PRIMARY KEY,
                    description VARCHAR(100) NOT NULL
                )
                """);

            outerService.execute();

            System.out.println("Committed IDs: "
                    + jdbc.queryForList(
                            "SELECT id FROM audit_event ORDER BY id",
                            Long.class));
        };
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
    private final OptionalService optionalService;

    public OuterService(JdbcTemplate jdbc, OptionalService optionalService) {
        this.jdbc = jdbc;
        this.optionalService = optionalService;
    }

    @Transactional
    public void execute() {
        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                1L, "before-savepoint");

        try {
            optionalService.writeOptionalPart();
        } catch (IllegalStateException ex) {
            System.out.println("Optional part rolled back; outer continues");
        }

        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                3L, "after-savepoint");
    }
}
```

**`src/main/java/demo/OptionalService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OptionalService {
    private final JdbcTemplate jdbc;

    public OptionalService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeOptionalPart() {
        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                2L, "optional-data");

        throw new IllegalStateException("Invalid optional data");
    }
}
```

Yêu cầu JDK 17+, Maven 3.6.3+; tại thư mục chứa `pom.xml` chạy:

```bash
mvn spring-boot:run
```

Các dòng **do chương trình in** (bỏ qua banner/log Spring):

```text
Optional part rolled back; outer continues
Committed IDs: [1, 3]
```

### Phân tích kết quả

- Bean runner gọi `outerService.execute()` **qua proxy**, mở outer JDBC transaction rồi insert id=1.
- `OptionalService` là bean khác, được gọi qua proxy. `NESTED` tạo savepoint trước khi insert id=2.
- `IllegalStateException` thuộc unchecked exception, kích hoạt rollback mặc định của `@Transactional`: Spring rollback về savepoint, sau đó ném lại ngoại lệ.
- `OuterService` bắt lỗi sau khi inner interceptor đã rollback, insert id=3 và trả về bình thường.
- Outer interceptor commit; SELECT chạy **sau** khi `execute()` trả về qua proxy, vì vậy chỉ thấy id 1 và 3.

Nếu bỏ dòng `throw` ở `OptionalService`, kết quả là `[1, 2, 3]`. Nếu outer ném `RuntimeException` sau insert id=3 và để ngoại lệ thoát khỏi proxy, outer transaction rollback: ngay cả các bản ghi được giữ sau rollback tới savepoint cũng không được commit.

> Ví dụ sử dụng JDBC transaction manager. Không suy luận rằng `NESTED` tự chạy với mọi `PlatformTransactionManager` hoặc rằng persistence context của JPA tự được phục hồi.

## 5. Savepoint thủ công qua TransactionStatus

Khi phải đặt nhiều checkpoint theo điều kiện trong cùng một phương thức, `TransactionStatus` (mở rộng `SavepointManager`) có các API:

- `createSavepoint()` tạo mốc và trả về đối tượng đại diện.
- `rollbackToSavepoint(savepoint)` rollback những thay đổi sau mốc đó.
- `releaseSavepoint(savepoint)` giải phóng mốc.
- `setRollbackOnly()` yêu cầu rollback khi transaction scope kết thúc; **không giống** rollback tới một savepoint cụ thể.

Ví dụ là **service thay thế** dùng lại bảng `audit_event`, không phải đoạn code chạy cùng lúc với ví dụ trước:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ManualSavepointService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public ManualSavepointService(
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(transactionManager);
    }

    public void runWithSavepoint() {
        template.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                    10L, "required-before");

            Object savepoint = status.createSavepoint();
            try {
                jdbc.update(
                        "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                        11L, "optional");

                boolean optionalValid = false;
                if (!optionalValid) {
                    throw new IllegalArgumentException("Optional data invalid");
                }
            } catch (IllegalArgumentException ex) {
                status.rollbackToSavepoint(savepoint);
            }
            status.releaseSavepoint(savepoint);

            jdbc.update(
                    "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                    12L, "required-after");
        });
    }
}
```

Để chạy thử **thay thế** `outerService.execute();` trong runner bằng `manualSavepointService.runWithSavepoint();` và inject `ManualSavepointService` vào tham số bean `example`. Với database mới, SELECT cuối trả `[10, 12]`.

Đoạn trên chỉ bắt lỗi nghiệp vụ dự kiến; lỗi JDBC không rõ nguyên nhân nên được phép thoát ra làm rollback toàn transaction. Nếu không rollback được về savepoint thì không nên cố commit outer. Ở ví dụ đơn giản có ranh giới service rõ ràng, `NESTED` thường dễ đọc hơn; `TransactionStatus` hữu ích khi số lượng và thời điểm savepoint biến thiên theo logic nghiệp vụ.

**Không lấy tùy ý một `Connection` mới rồi tự gọi `setAutoCommit(false)`/`commit()`/`rollback()` trong Spring-managed transaction.** `JdbcTemplate` và `DataSourceUtils` tham gia connection gắn với thread; một connection khác có thể không thuộc cùng transaction, khiến savepoint không bảo vệ phần ghi đó.

## 6. So sánh REQUIRED, NESTED, REQUIRES_NEW

| Tiêu chí | `REQUIRED` | `NESTED` | `REQUIRES_NEW` |
| --- | --- | --- | --- |
| Khi outer đã có transaction | Tham gia transaction vật lý hiện có | Cùng transaction vật lý, thêm savepoint | Tạm treo outer, mở transaction vật lý độc lập |
| JDBC connection | Connection hiện tại | **Cùng connection** | Thường là connection khác |
| Inner commit độc lập? | Không | **Không** | **Có** |
| Inner ném lỗi thỏa rollback rule | Thường đánh dấu transaction chung rollback-only | Rollback về savepoint; outer có thể tiếp tục | Rollback inner độc lập; outer vẫn có thể tiếp tục |
| Outer rollback sau khi inner thành công | Inner cũng mất | Inner cũng mất | Inner đã commit riêng vẫn tồn tại |
| Dùng khi | Toàn tác vụ cần cùng thành/bại | Một bước JDBC optional có thể hủy cục bộ | Phần inner bắt buộc commit độc lập |

**REQUIRED và `UnexpectedRollbackException`:** Inner method tham gia bằng `REQUIRED`, ném unchecked exception qua interceptor. Outer bắt lỗi rồi cố commit. Inner participant có thể đã đánh dấu transaction chung `rollback-only`. Bắt exception không xóa cờ này; tại commit ngoài thường xuất hiện `UnexpectedRollbackException`. Với `NESTED`, Spring rollback riêng về savepoint khi đủ điều kiện, nên lỗi nội bộ dự kiến không nhất thiết làm outer rollback-only.

**REQUIRES_NEW:** Transaction inner có commit riêng. Nếu nó commit rồi outer rollback, kết quả inner vẫn còn. Một connection mới có thể cần thiết trong khi outer giữ connection cũ; với connection pool thiếu dung lượng, nhiều thread có thể chờ nhau/cạn connection. Chỉ chọn phương án này khi semantics commit độc lập thật sự cần thiết.

## 7. Ngoại lệ và rollback rule

Mặc định `@Transactional` rollback khi `RuntimeException` hoặc `Error` thoát qua interceptor; checked exception thường không kích hoạt rollback nếu chưa cấu hình `rollbackFor`. Ví dụ cấu hình rollback cho checked exception:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void importOptionalFile() throws java.io.IOException {
    // Thực hiện thao tác JDBC; IOException có thể xuất hiện.
}
```

Đây là chữ ký **minh họa**, chưa phải chương trình độc lập. Các lưu ý quan trọng:

1. **Ngoại lệ phải đi qua interceptor** để rollback tự động theo annotation. Nếu inner tự `try/catch` và nuốt lỗi rồi return bình thường, Spring thường coi nested scope thành công. Hãy ném lại lỗi hoặc chủ động yêu cầu rollback phù hợp.
2. **Bắt lỗi ở outer là quyết định nghiệp vụ.** Chỉ tiếp tục khi lỗi optional có thể bỏ qua; không nuốt lỗi hạ tầng hoặc vi phạm bất biến.
3. **Savepoint không xóa cờ rollback-only của toàn transaction** nếu một thành phần khác đã đặt cờ đó. Khi transaction chung không còn hợp lệ, rollback toàn bộ thường là lựa chọn an toàn.
4. **Tạo savepoint trước phần rủi ro.** Mốc tạo sau lỗi không thể đưa transaction về trạng thái trước lỗi.
5. **Nested scope kết thúc thành công chưa có nghĩa dữ liệu bền vững.** Commit cuối luôn do transaction vật lý ở ngoài quyết định.

## 8. Giới hạn đặc biệt

### JPA và Hibernate

`JpaTransactionManager` mặc định không cho phép nested transactions. Một số cấu hình hỗ trợ JDBC savepoint đối với các JDBC operation tham gia transaction JPA, nhưng **`EntityManager`/persistence context/cache cấp một không tự quay về trạng thái trước savepoint**. Một entity đã sửa trong bộ nhớ có thể vẫn mang giá trị mới dù database đã rollback cục bộ.

Do đó không thể bê nguyên ví dụ `JdbcTemplate` sang `JpaRepository.save()` và kỳ vọng toàn bộ entity graph rollback từng phần. Khi phối hợp JDBC với JPA, phải kiểm chứng flush, refresh/clear, trạng thái entity và transaction manager/driver bằng integration test thực tế. Chỉ đặt `nestedTransactionAllowed=true` không bảo đảm JPA nested semantics đúng. Với nghiệp vụ JPA phức tạp, cân nhắc ranh giới transaction khác hoặc chiến lược bù trừ phù hợp.

### JTA/XA, R2DBC và nhiều database

`JtaTransactionManager` không mặc nhiên hỗ trợ JDBC savepoint như `DataSourceTransactionManager`. Đừng giả định `NESTED` hoạt động với JTA/XA/distributed transactions. Ứng dụng reactive/R2DBC phải kiểm tra riêng `ReactiveTransactionManager` và driver: ví dụ đồng bộ `JdbcTemplate` ở trên không dùng nguyên xi cho reactive pipeline. Một savepoint trên connection A không thể rollback transaction/connection B.

### Side effect ngoài transaction

HTTP request, email, file, message lên broker hay cache ngoài database có thể thành công dù SQL rollback đến savepoint. Các lựa chọn tương ứng gồm transactional outbox, xử lý idempotent và compensation; savepoint không tự thay thế các cơ chế đó.

### DDL và năng lực driver

Một số database có implicit commit với DDL; một số driver hạn chế thao tác release savepoint. Nếu cần, kiểm tra `Connection.getMetaData().supportsSavepoints()` và chạy integration test trên đúng DB/version production. Không lấy kết quả trên H2 làm bằng chứng thay cho DB khác.

## 9. Kiểm thử hành vi

Thử từng kịch bản trên database mới (hoặc reset dữ liệu giữa các lần chạy):

| Kịch bản | Thay đổi thử | Kết quả mong đợi |
| --- | --- | --- |
| Inner lỗi, outer xử lý được | Giữ code ví dụ | Commit id 1, 3 |
| Inner thành công | Bỏ `throw` của `OptionalService` | Commit id 1, 2, 3 |
| Outer lỗi sau khi bắt inner | Thêm unchecked exception cuối `OuterService.execute()` | Outer rollback, không còn các id chưa commit |
| Inner đổi thành REQUIRED | Đổi propagation từ NESTED sang REQUIRED, vẫn ném unchecked exception | Outer thường gặp rollback-only/`UnexpectedRollbackException` |
| Gọi NESTED không có outer | Gọi inner từ bean ngoài transaction | NESTED tạo transaction vật lý mới |
| Self-invocation | Gọi `this.someNestedMethod()` trong cùng bean | Annotation có thể bị bỏ qua do không đi qua proxy |

Có thể bật log khi thử nghiệm:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Chỉ bật log chi tiết khi cần, kiểm soát lượng thông tin. Hãy xác minh **dữ liệu sau khi transaction kết thúc**, thay vì chỉ kiểm tra exception. Một test tự chạy trong transaction được rollback cuối test có thể che khuất kết quả commit thật; tổ chức test để quan sát đúng boundary.

Nếu thấy `NestedTransactionNotSupportedException`, kiểm tra transaction manager thực tế, `nestedTransactionAllowed`, hỗ trợ savepoint của driver/database, outer transaction có tồn tại, và việc phối hợp JDBC/JPA/JTA. Nếu không có rollback cục bộ, kiểm tra proxy invocation và loại exception/rollback rule.

## 10. Các lỗi thường gặp

1. **Nhầm NESTED với REQUIRES_NEW:** NESTED không commit riêng; outer rollback vẫn làm mất thay đổi inner.
2. **Outer đã rollback-only mà cố cứu bằng savepoint:** rollback cục bộ không buộc transaction đang rollback-only phải commit.
3. **Gọi nested method qua `this`:** không đi qua AOP proxy; chuyển nested method sang bean Spring riêng.
4. **Nuốt lỗi trong inner:** proxy nhìn thấy trả về bình thường, không rollback tự động. Cần ném lỗi phù hợp hoặc gọi API rollback.
5. **Dùng savepoint JDBC cho JPA entity state:** bộ nhớ persistence context không tự đồng bộ với rollback cục bộ.
6. **Mở connection riêng và commit thủ công:** câu SQL ở connection đó nằm ngoài transaction/savepoint đang quản lý.
7. **Tưởng SQL rollback hoàn tác mọi side effect:** email, event hay API request cần phương án nhất quán khác.
8. **Bắt mọi lỗi rồi tiếp tục:** lỗi DB, lỗi rollback hoặc lỗi không xác định có thể khiến transaction không an toàn để commit.
9. **Chỉ thử trên H2:** phải xác nhận tính tương thích với driver/database thật.
10. **Giữ transaction ngoài quá lâu:** savepoint không loại bỏ rủi ro lock lâu, timeout và tranh chấp tài nguyên trong cùng một transaction.

## 11. Chọn cơ chế phù hợp

- **Tất cả cùng thành/bại:** Dùng một transaction `REQUIRED`; lỗi nghiêm trọng rollback toàn bộ.
- **Một bước JDBC tùy chọn có thể lỗi, outer vẫn tiếp tục:** `@Transactional(NESTED)` với JDBC transaction manager và driver hỗ trợ.
- **Nhiều checkpoint động trong một method:** `TransactionTemplate` + `TransactionStatus.createSavepoint()/rollbackToSavepoint()`.
- **Inner phải commit độc lập dù outer rollback:** `REQUIRES_NEW`, đánh giá connection pool và hậu quả nhất quán dữ liệu.
- **Có JPA entity state, nhiều database hoặc side effect ngoài DB:** thiết kế lại ranh giới transaction hoặc kết hợp outbox/compensation; không xem JDBC savepoint là cơ chế rollback tổng quát.

## 12. Tự kiểm tra

**1.** `INSERT A → SAVEPOINT S → INSERT B → ROLLBACK TO S → INSERT C → COMMIT` còn bản ghi nào? **A và C**; B đã rollback.

**2.** Inner `NESTED` thành công nhưng outer rollback sau đó, dữ liệu inner còn không? **Không**; chúng thuộc cùng transaction vật lý.

**3.** Outer bắt ngoại lệ từ inner `REQUIRED` rồi trả về bình thường, có chắc commit thành công? **Không**; inner có thể đã đánh dấu transaction chung rollback-only, gây `UnexpectedRollbackException`.

**4.** Tại sao gọi annotated nested method qua `this` có thể mất tác dụng? **Vì Spring transaction proxy không chặn self-invocation** ở proxy mode.

**5.** Savepoint có hủy HTTP request đã gửi không? **Không**; nó quản lý thay đổi thuộc database transaction tương ứng.

**6.** `RELEASE SAVEPOINT` có làm dữ liệu bền vững không? **Không**; phải đợi `COMMIT` của transaction vật lý.

## 13. Tài liệu tham khảo chính thức

- Spring Framework — Transaction propagation/`PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — DataSource/JDBC connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `TransactionStatus` và các phương thức SavepointManager: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `JpaTransactionManager` và giới hạn JPA savepoint: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html

**Ghi nhớ:** Savepoint là điểm rollback có chọn lọc **bên trong một transaction vật lý**; `NESTED` là cách Spring JDBC tổ chức điều đó. Quyền commit cuối cùng vẫn thuộc outer transaction.