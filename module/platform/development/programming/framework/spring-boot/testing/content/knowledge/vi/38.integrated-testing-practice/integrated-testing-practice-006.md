# Chứng minh ranh giới rollback và dọn dữ liệu sau HTTP test

## 1. Bài toán: @Transactional trên test nhưng database vẫn còn bản ghi

Bạn có một Spring Boot API `POST /orders` lưu đơn hàng vào database. Test gửi HTTP thật bằng `TestRestTemplate`, được đánh dấu `@Transactional` và mặc định rollback sau khi chạy. Thế nhưng sau test, bảng `orders` vẫn chứa dữ liệu.

Đây **không nhất thiết là lỗi của Spring Transaction Manager**. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT` trên ứng dụng servlet, JUnit test method chạy trên thread **HTTP client**, còn request được embedded server xử lý ở **server worker thread**. Spring transaction do `TransactionalTestExecutionListener` mở cho test method gắn với thread của test; nó không tự truyền qua TCP/HTTP sang server. Một `@Transactional` ở Spring service phía server sẽ mở/commit hoặc rollback một **transaction khác**. Nếu server xử lý POST thành công rồi commit, rollback ở thread test sẽ **không xóa** hàng đã commit đó.

Tài liệu chính thức **Spring Boot 3.5.16** nêu rõ: khi real server được start bằng `RANDOM_PORT`/`DEFINED_PORT`, HTTP client và server hoạt động trong các threads và transactions riêng; transaction bắt đầu ở server sẽ không bị test-managed rollback tự động hoàn tác. Ngược lại, `MockMvc` **đồng bộ**, không qua TCP, thường thực thi handler trên thread gọi test; service `@Transactional(propagation=REQUIRED)` có thể tham gia transaction đang mở của test và bị rollback theo test. Vì vậy cùng một API có thể để lại database state khác nhau khi test qua `MockMvc` và HTTP thật.

### Kết quả cần đạt

Sau bài bạn sẽ:

1. Vẽ chính xác các ranh giới `JUnit test transaction`, `Spring MVC request transaction`, database connection và commit.
2. Giải thích vì sao `@Rollback`/`@Transactional` trên test không rollback server-side writes sau HTTP request.
3. Dùng `@SpringBootTest(RANDOM_PORT)`, `TestRestTemplate`, `@LocalServerPort` đúng phạm vi.
4. Phân biệt `MOCK + @AutoConfigureMockMvc` với `RANDOM_PORT + real HTTP`; hiểu giới hạn của MockMvc khi có async dispatch.
5. Dùng `@BeforeTransaction`/`@AfterTransaction` để kiểm data **sau khi test-managed transaction thật sự rollback**.
6. Tạo hai records: **client marker** chỉ tồn tại trong transaction test và **server order** được commit qua HTTP. Sau rollback: marker = 0, server order = 1.
7. Thực hiện **targeted cleanup** sau HTTP test bằng mã định danh riêng và transaction/connection đã commit.
8. Không dùng `@AfterEach` trong cùng test-managed transaction để cleanup server data rồi tưởng delete sẽ commit.
9. Kiểm rollback bên **service server** khi business exception phát sinh **trước commit**.
10. So sánh lỗi input validation (400), duplicate key (409), server failure (500) và DB state.
11. Dùng `@Sql`/`@SqlConfig(transactionMode=ISOLATED)` đúng khi cần committed fixtures/cleanup; hiểu khi nào script cleanup có thể rollback theo outer test transaction.
12. Thiết kế fixture ID/namespace giúp các test classes chia sẻ database mà không xóa dữ liệu lẫn nhau.
13. Tránh false positive do Hibernate first-level cache, chưa `flush()`/`clear()` hoặc assert trước commit/async completion.
14. Viết integration tests Java 17/Spring Boot 3.5.16 chạy được bằng Maven với H2/Spring JDBC và mở rộng sang PostgreSQL Testcontainers.

## 2. Hai transactions không nằm trong cùng HTTP request

### 2.1. Real HTTP: ranh giới không thể tự vượt qua

~~~text
JUnit thread (HTTP client)                     Servlet container worker
---------------------------------             --------------------------------
@Transactional test begins [TX-T]            (chưa có server TX)

insert client_marker
  -> row chưa commit trong TX-T
  -> chỉ thread/connection test biết

HTTP POST /orders  --------------------------> Controller
                                               -> OrderService.create()
                                               -> @Transactional begins [TX-S]
                                               -> repository INSERT server_order
                                               -> TX-S COMMIT
                  <-------------------------- HTTP 201 Created

JUnit test assertions
Spring TestContext rolls back [TX-T]
   |
   +-- client_marker ROLLED BACK
   +-- server_order still COMMITTED
~~~

**Không có một transaction JDBC chạy xuyên qua HTTP request chỉ vì cả hai threads thuộc cùng JVM hay một Spring ApplicationContext.** Transaction state của Spring imperative transaction management thường được bind với current thread qua `TransactionSynchronizationManager`. Một remote HTTP request còn có thể vào **một process khác**; không nên thiết kế test dựa vào giả định transaction xuyên mạng.

### 2.2. MockMvc đồng bộ: thường là cùng thread

~~~text
JUnit thread, @Transactional test [TX-T]
    |
    +-- MockMvc.perform(POST /orders)
    |      -> DispatcherServlet mock request
    |      -> Controller
    |      -> Service @Transactional(REQUIRED)
    |      -> joins TX-T (same thread)
    |      -> INSERT order, not yet committed
    |
    +-- repository query on same test transaction sees the row
    |
    +-- test method ends
           -> TX-T ROLLBACK
           -> order disappears
~~~

Với synchronous `MockMvc` và `REQUIRED` propagation, request processing thường cùng thread và có thể dùng test-managed transaction. Đây là **sự thuận tiện cho slice/integration tests không chạy server**, nhưng không đại diện nguyên vẹn cho commit behavior của production HTTP request. Nếu controller gọi `@Async`, async servlet dispatch, `REQUIRES_NEW`, gửi message hoặc ra service khác, transaction boundary sẽ khác.

### 2.3. Spring test transaction có những gì?

Khi JUnit/Spring TestContext chạy một transactional test method:
- `TransactionalTestExecutionListener` tạo **test-managed transaction** trước `@BeforeEach`/`@Test`.
- `@BeforeTransaction` chạy **ngoài và trước** test transaction.
- `@BeforeEach` và `@AfterEach` chạy **bên trong** test-managed transaction khi test method dùng `@Transactional`.
- Mặc định test transaction **rollback**, trừ khi cấu hình `@Commit`/`@Rollback(false)` hoặc `TestTransaction.flagForCommit()`.
- `@AfterTransaction` chạy **sau khi** transaction test kết thúc; đây là nơi phù hợp để verify committed state hoặc cleanup đã phải thoát outer transaction.

Không suy rằng `@AfterEach` luôn nằm ngoài transaction. Đây là lỗi cleanup phổ biến.

### 2.4. Một bảng so sánh dễ nhớ

| Hình thức test | Test thread transaction | Server transaction | Server write có rollback theo test? |
| --- | --- | --- | --- |
| Unit test không Spring | Không trừ khi tự tạo | Không có HTTP server | Không áp dụng |
| `@JdbcTest`, mặc định transactional | Có | Không có HTTP request | Writes cùng TX test rollback |
| `@SpringBootTest(MOCK)` + synchronous MockMvc + `@Transactional` | Có | Service `REQUIRED` có thể join TX test | Thường có |
| `@SpringBootTest(RANDOM_PORT)` + `@Transactional` | Có ở client/test thread | TX độc lập trong server thread | **Không** |
| `@SpringBootTest(RANDOM_PORT)` không `@Transactional` | Không | Service TX phía server | Không; phải cleanup |
| Async worker / message consumer | Không tự propagate | TX độc lập theo worker | Không tự rollback với TX test |
| Service `REQUIRES_NEW` khi gọi từ MockMvc cùng thread | Outer TX test tạm suspend | New service TX commit riêng | Không nếu inner TX commit |

“Thường có” ở MockMvc phụ thuộc synchronous execution, propagation và DB/client path. Đừng biến bảng thành cam kết rằng mọi MockMvc call đều chạy trên một transaction.

## 3. Tại sao cách viết test tưởng đúng có thể để lại dữ liệu?

### 3.1. Anti-pattern phổ biến

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrdersHttpTest {

    @Autowired TestRestTemplate http;

    @Test
    void createsOrder() {
        http.postForEntity(
                "/orders",
                new CreateOrderRequest("fixed-123", "alice", 2),
                OrderRecord.class);
    }

    // Không có cleanup.
}
~~~

Đây là snippet phản ví dụ, không phải một file trong dự án lab. `@Transactional` chỉ làm rollback các operations của **test thread**. POST đã qua real network boundary, server có thể commit. Test chạy lần sau với `fixed-123` có thể gặp duplicate key, khiến suite bị phụ thuộc thứ tự và data residue.

### 3.2. @AfterEach vẫn có thể rollback DELETE

Một biến thể nguy hiểm:

~~~java
@AfterEach
void cleanup() {
    repository.deleteById("fixed-123");
}
~~~

Nếu class/test method có `@Transactional`, callback `@AfterEach` vẫn chạy **trong test-managed transaction**. Nó có thể nhìn thấy server-committed row, delete nó tạm thời, nhưng khi test transaction rollback, **DELETE cũng rollback**; hàng gốc vẫn còn. Bạn thấy một log `DELETE FROM orders` không có nghĩa cleanup đã commit.

Hãy dùng một trong hai mô hình:
- **Khuyến nghị cho real HTTP tests:** bỏ `@Transactional` trên test, tạo IDs riêng, cleanup bằng repository trong `@AfterEach` với autocommit/transaction phù hợp.
- **Nếu cố ý phải chứng minh TX boundary:** dùng `@AfterTransaction` hoặc một `TransactionTemplate` transaction độc lập đã commit; test chỉ dùng local marker để so sánh.

### 3.3. @DirtiesContext không xóa database

`@DirtiesContext` đóng/loại cached Spring ApplicationContext. Nó **không có nghĩa** tất cả rows trong external PostgreSQL, Redis keys, Kafka offsets hoặc persisted files sẽ bị xóa. Nếu DB là một H2 in-memory instance gắn với context và không giữ sống bên ngoài, context close đôi khi khiến state biến mất — nhưng đó là side effect do DB lifecycle, **không phải data cleanup contract**. Với database server thật, context mới có thể thấy mọi rows cũ.

### 3.4. Chạy riêng PASS, chạy suite FAIL

Các nguyên nhân điển hình:
- Cùng fixed ID ở nhiều methods/classes.
- Một test POST thành công nhưng không cleanup sau commit.
- `@Sql` delete script chạy trong transaction bị rollback.
- Parallel tests dùng `DELETE FROM orders` toàn bảng.
- Test A tạo async worker chưa xong, `@AfterEach` cleanup quá sớm.
- JPA entity được giữ trong persistence context, nên assertion đọc cache thay vì DB fresh.
- Testcontainers backend reused, schema/data cũ còn.
- Method ordering che hidden dependency.

Điều tra **thứ gì còn trong DB sau khi client TX kết thúc**, không chỉ nhìn HTTP status hoặc green check của JUnit.

## 4. Kế hoạch chứng minh bằng phép đo hai phía

Ta không cần giả định các thread transaction ID giống hay khác chỉ dựa vào tên thread. Ta chứng minh bằng **database state**:

1. `@BeforeTransaction` tạo hai IDs duy nhất: `clientMarkerId` và `httpOrderId`.
2. Trong test-managed TX, gọi JDBC trực tiếp insert **client marker**.
3. Từ cùng test method, gửi `POST /orders` thật qua `TestRestTemplate` để server tạo **HTTP order**.
4. HTTP server service có `@Transactional` và trả 201 sau khi service hoàn tất.
5. Test-managed transaction kết thúc với rollback.
6. Trong `@AfterTransaction`, query database bằng connection/transaction mới.
7. Assert **client marker không tồn tại** vì rollback.
8. Assert **HTTP order vẫn tồn tại** vì đã commit ở server thread.
9. Dùng `finally` xóa đúng hai IDs ngoài test transaction.
10. Query lại để xác nhận cleanup đã thành công.

~~~text
Đo ở thời điểm sau test-managed rollback:

    client_marker_id -> COUNT(*) = 0
    http_order_id    -> COUNT(*) = 1

Đo sau committed cleanup:

    client_marker_id -> COUNT(*) = 0
    http_order_id    -> COUNT(*) = 0
~~~

Đây là phép đo trực tiếp của invariant, tránh kết luận dựa trên stack trace hoặc lời kể “Spring sẽ rollback hết”.

## 5. Dự án Maven: Spring Boot 3.5.16 + Java 17 + H2 + JDBC

### 5.1. Chức năng lab

API mẫu quản lý bản ghi đơn hàng:
- `POST /orders` tạo đơn và trả 201.
- `GET /orders/{id}` đọc theo ID, trả 200/404.
- `POST /orders/rollback` insert trong service transaction rồi cố tình throw RuntimeException, handler trả 500; database phải rollback server-side insert.
- Duplicate primary key trả 409, row gốc không thay đổi.
- Input validation `quantity < 1` trả 400 và không insert.

Ba lớp test cùng làm rõ các bối cảnh:
1. `RealHttpCleanupIntegrationTest`: real HTTP, **không** test-level transaction; `@AfterEach` targeted cleanup (4 tests).
2. `RealHttpRollbackBoundaryTest`: real HTTP, **có** test-level transaction; `@BeforeTransaction`/`@AfterTransaction` chứng minh client marker rollback nhưng server order còn; cleanup sau TX (1 test).
3. `MockMvcRollbackContrastTest`: synchronous MockMvc, **có** test-level transaction; assert row tồn tại trong TX nhưng biến mất sau rollback (1 test).

Tổng **6 JUnit test methods dự kiến**. H2 cho môi trường học nhỏ, không cần Docker; với các invariant phụ thuộc lock/isolation/sequence/dialect, phải chạy thêm test tương đương với PostgreSQL Testcontainers.

### 5.2. Cây thư mục

~~~text
http-rollback-cleanup-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/httpcleanup/
│   │   ├── HttpCleanupApplication.java
│   │   ├── CreateOrderRequest.java
│   │   ├── OrderRecord.java
│   │   ├── OrderRepository.java
│   │   ├── OrderService.java
│   │   └── OrderController.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/java/com/example/httpcleanup/
    ├── RealHttpCleanupIntegrationTest.java
    ├── RealHttpRollbackBoundaryTest.java
    └── MockMvcRollbackContrastTest.java
~~~

Các file Java đều nằm dưới package `com.example.httpcleanup`. Main class ở package root của module, Spring Boot component scan repository/service/controller. Không có mock hoặc external HTTP dependencies ngoài server được khởi tạo trong test.

### 5.3. pom.xml

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>http-rollback-cleanup-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

Dependency notes:
- `spring-boot-starter-web` cung cấp Servlet Spring MVC, JSON/Jackson.
- `spring-boot-starter-jdbc` cung cấp `JdbcTemplate`, `DataSourceTransactionManager`/JDBC transaction manager, Hikari.
- `spring-boot-starter-validation` kích hoạt validation annotations của request DTO.
- `h2` runtime là test DB dễ chạy, **không tương đương production PostgreSQL về isolation/locking**.
- `spring-boot-starter-test` có JUnit 5, AssertJ, Spring Test, MockMvc và `TestRestTemplate` trong **Spring Boot 3.5.x**.
- Spring Boot parent/BOM đồng bộ Spring Framework/Jackson/JUnit versions.
- Java 17 là minimum sample; không cần Docker cho lab chính.

### 5.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=http-rollback-cleanup-lab
spring.main.banner-mode=off

spring.datasource.url=jdbc:h2:mem:http_cleanup_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.connection-timeout=10000

spring.sql.init.mode=always
server.address=127.0.0.1

logging.level.org.springframework.transaction=INFO
logging.level.org.springframework.jdbc.core=INFO
~~~

**Vì sao `DB_CLOSE_DELAY=-1`?** H2 in-memory database tiếp tục tồn tại trong cùng JVM ngay khi last JDBC connection đóng. Nó giúp các Spring contexts của lab vẫn có thể cùng nhìn database; đồng thời nhấn mạnh **context close hoặc test rollback không tự clean DB**. Test không dựa vào thứ tự lớp hay database tên “mới”.

Không set `server.port=8080`. `@SpringBootTest(RANDOM_PORT)` chọn port động; `MOCK` không mở server thật. `server.address=127.0.0.1` hạn chế test server trên loopback.

Cấu hình trên dành cho lab; production thường dùng DB migration/versioning thay vì H2 `schema.sql` và mật khẩu rỗng.

### 5.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS demo_orders (
    order_id VARCHAR(100) PRIMARY KEY,
    owner_tag VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 1)
);
~~~

Schema nhỏ để phân biệt:
- **Primary key** chống duplicate order ID.
- **Non-null owner tag** tạo namespace khi cleanup.
- **CHECK constraint** bảo vệ quantity ở database, ngoài validation ở HTTP boundary.
- `IF NOT EXISTS` giúp schema init idempotent trong H2 dùng chung ở lab. Trong production, dùng Flyway/Liquibase đã quản lý version, không dùng câu lệnh này thay migration strategy.

Mỗi test tạo ID unique; cleanup bằng `WHERE order_id = ?`. Không có `DELETE FROM demo_orders` toàn bảng trong bất kỳ test runnable nào.

### 5.6. HttpCleanupApplication.java

`src/main/java/com/example/httpcleanup/HttpCleanupApplication.java`:

~~~java
package com.example.httpcleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCleanupApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                HttpCleanupApplication.class, args);
    }
}
~~~

Không bật scheduler/async listeners mặc định trong lab; điều này giúp persistence contract sau HTTP response đồng bộ và deterministic.

### 5.7. CreateOrderRequest.java

`src/main/java/com/example/httpcleanup/CreateOrderRequest.java`:

~~~java
package com.example.httpcleanup;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
        @NotBlank String id,
        @NotBlank String owner,
        @Min(1) int quantity) {
}
~~~

Record Java 17 được Jackson bind từ JSON. `@Valid` ở controller kích hoạt Bean Validation cho request:
- `id` và `owner` không được blank.
- `quantity >= 1`.
- Nếu input invalid, Spring MVC mặc định trả 400 cho `MethodArgumentNotValidException`, service không được gọi.
- Validation chỉ bảo vệ request boundary; database CHECK constraint vẫn cần thiết nếu có code path insert ngoài HTTP.

Không dùng một fixed ID trong nhiều test runs.

### 5.8. OrderRecord.java

`src/main/java/com/example/httpcleanup/OrderRecord.java`:

~~~java
package com.example.httpcleanup;

public record OrderRecord(
        String id,
        String owner,
        int quantity) {
}
~~~

Đây là DTO/row projection đơn giản. Trong ứng dụng thật, có thể tách domain entity/DTO/persistence model và tránh trả PII hoặc internal fields.

### 5.9. OrderRepository.java

`src/main/java/com/example/httpcleanup/OrderRepository.java`:

~~~java
package com.example.httpcleanup;

import java.util.Objects;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(OrderRecord order) {
        return jdbc.update(
                "INSERT INTO demo_orders "
                        + "(order_id, owner_tag, quantity) "
                        + "VALUES (?, ?, ?)",
                order.id(),
                order.owner(),
                order.quantity());
    }

    public Optional<OrderRecord> findById(String id) {
        return jdbc.query(
                "SELECT order_id, owner_tag, quantity "
                        + "FROM demo_orders WHERE order_id = ?",
                (rs, rowNum) -> new OrderRecord(
                        rs.getString("order_id"),
                        rs.getString("owner_tag"),
                        rs.getInt("quantity")),
                id)
                .stream()
                .findFirst();
    }

    public long countById(String id) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders "
                        + "WHERE order_id = ?",
                Long.class,
                id);

        return Objects.requireNonNull(count);
    }

    public int deleteById(String id) {
        return jdbc.update(
                "DELETE FROM demo_orders WHERE order_id = ?",
                id);
    }
}
~~~

`JdbcTemplate` tham gia Spring transaction **gắn với thread đang gọi**:
- Khi gọi `insert` từ JUnit thread đang có test-managed TX, JDBC operation nằm trong TX test.
- Khi gọi từ service trong servlet server thread có `@Transactional` riêng, operation nằm trong server transaction.
- Khi gọi `deleteById` ngoài transaction trong test không `@Transactional`, Hikari/JDBC auto-commit thường đảm bảo statement đã commit.
- Khi gọi trong `@AfterTransaction` (ngoài TX test), cleanup statement không bị rollback cùng test transaction đã kết thúc.
- Nếu ứng dụng sử dụng explicit transaction manager/connection custom, cần xác nhận behavior thay vì chỉ mặc định.

Repository không lưu cached Java Map; mọi assertion đọc DB thực qua JDBC.

### 5.10. OrderService.java

`src/main/java/com/example/httpcleanup/OrderService.java`:

~~~java
package com.example.httpcleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderRecord create(CreateOrderRequest request) {
        OrderRecord created = new OrderRecord(
                request.id(),
                request.owner(),
                request.quantity());

        repository.insert(created);
        return created;
    }

    @Transactional
    public void createThenFail(
            CreateOrderRequest request) {

        repository.insert(new OrderRecord(
                request.id(),
                request.owner(),
                request.quantity()));

        throw new IllegalStateException(
                "forced rollback before commit");
    }
}
~~~

**Transaction semantics:**
- Controller gọi `OrderService` qua Spring proxy, nên `@Transactional` được áp dụng.
- `create` thành công và Spring transaction manager commit **trước khi method quay về controller**.
- `createThenFail` throw unchecked `IllegalStateException`; Spring mặc định rollback transaction của service, không commit insert.
- Error handler trả 500 **sau khi** exception đã đi qua transaction interceptor, vì vậy handler không “đổi” một rollback thành commit.
- Nếu exception được catch **bên trong** transactional service rồi return bình thường mà không set rollback-only, transaction có thể commit; test phải chứng minh contract thực, không chỉ HTTP 500.

Trong production code, có thể dùng domain-specific exception và phân loại status 4xx/5xx phù hợp; ở lab 500 cố ý mô tả lỗi nội bộ trước commit.

### 5.11. OrderController.java

`src/main/java/com/example/httpcleanup/OrderController.java`:

~~~java
package com.example.httpcleanup;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderRepository repository;

    public OrderController(
            OrderService service,
            OrderRepository repository) {
        this.service = service;
        this.repository = repository;
    }

    @PostMapping
    public ResponseEntity<OrderRecord> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderRecord created = service.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderRecord> get(
            @PathVariable String id) {

        return repository.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() ->
                        ResponseEntity.notFound().build());
    }

    @PostMapping("/rollback")
    public ResponseEntity<Void> rollback(
            @Valid @RequestBody CreateOrderRequest request) {

        service.createThenFail(request);
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, String>> conflict(
            DataIntegrityViolationException ignored) {

        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(Map.of("code", "ORDER_CONFLICT"));
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> failed(
            IllegalStateException ignored) {

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "ORDER_ROLLED_BACK"));
    }
}
~~~

Code dùng API của Spring MVC:
- `POST /orders` trả 201.
- `GET /orders/{id}` trả 200 khi có row, 404 khi không.
- `POST /orders/rollback` chạy service rồi exception bị map 500.
- Duplicate PK từ JDBC `DataIntegrityViolationException` được map 409.
- Invalid input bị `@Valid`/Spring MVC reject 400 trước service.
- Error responses không đưa exception stack/password/internal SQL ra cho client.

Đây là demo HTTP layer. Các assertion quan trọng trong test bên dưới vẫn kiểm trạng thái **database**, không suy rollback chỉ từ HTTP status.

## 6. Test 1: Real HTTP, không @Transactional, cleanup sau request

### 6.1. RealHttpCleanupIntegrationTest.java

`src/test/java/com/example/httpcleanup/RealHttpCleanupIntegrationTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpCleanupIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository repository;

    private String orderId;

    @BeforeEach
    void uniqueDataPerMethod() {
        orderId = "http_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void deleteOnlyThisTestsRow() {
        if (orderId != null) {
            repository.deleteById(orderId);

            assertThat(repository.countById(orderId))
                    .as("targeted cleanup committed")
                    .isZero();
        }
    }

    @Test
    void post201PersistsAndGetReadsCommittedRow() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 3);

        ResponseEntity<OrderRecord> created =
                http.postForEntity(
                        "/orders",
                        request,
                        OrderRecord.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(created.getBody())
                .isEqualTo(new OrderRecord(
                        orderId, "http-test", 3));

        // Query qua repository khác code path controller:
        assertThat(repository.countById(orderId))
                .isEqualTo(1L);

        ResponseEntity<OrderRecord> loaded =
                http.getForEntity(
                        "/orders/{id}",
                        OrderRecord.class,
                        orderId);

        assertThat(loaded.getStatusCode())
                .isEqualTo(HttpStatus.OK);

        assertThat(loaded.getBody())
                .isEqualTo(created.getBody());
    }

    @Test
    void serverExceptionRollsBackItsOwnInsert() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 5);

        ResponseEntity<String> failed =
                http.postForEntity(
                        "/orders/rollback",
                        request,
                        String.class);

        assertThat(failed.getStatusCode())
                .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);

        // HTTP 500 tự nó KHÔNG chứng minh rollback.
        assertThat(repository.countById(orderId))
                .isZero();

        ResponseEntity<String> notFound =
                http.getForEntity(
                        "/orders/{id}",
                        String.class,
                        orderId);

        assertThat(notFound.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void invalidPayloadCannotInsert() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 0);

        ResponseEntity<String> invalid =
                http.postForEntity(
                        "/orders",
                        request,
                        String.class);

        assertThat(invalid.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(repository.countById(orderId))
                .isZero();
    }

    @Test
    void duplicateKeyReturns409WithoutReplacingOriginal() {

        CreateOrderRequest first =
                new CreateOrderRequest(
                        orderId, "http-test", 2);

        ResponseEntity<OrderRecord> created =
                http.postForEntity(
                        "/orders",
                        first,
                        OrderRecord.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        CreateOrderRequest duplicate =
                new CreateOrderRequest(
                        orderId, "http-test", 99);

        ResponseEntity<String> conflict =
                http.postForEntity(
                        "/orders",
                        duplicate,
                        String.class);

        assertThat(conflict.getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);

        assertThat(repository.findById(orderId))
                .contains(new OrderRecord(
                        orderId, "http-test", 2));

        assertThat(repository.countById(orderId))
                .isEqualTo(1L);
    }
}
~~~

### 6.2. Những điều test này chứng minh

**Test post201:**
- Request đi qua **embedded HTTP server thật**.
- Service transaction commit trước khi controller trả response thành công.
- Repository query độc lập thấy row.
- GET endpoint cũng đọc được row.
- `@AfterEach` delete row theo ID riêng.

**Test rollback:**
- Server service insert rồi throw exception trong transaction.
- HTTP handler trả 500, nhưng assertion không dừng ở status.
- Query trực tiếp DB thấy không có row.
- GET trả 404.
- Không có test-managed transaction để vô tình che việc server rollback.

**Test validation:**
- Input quantity=0 bị reject tại MVC boundary.
- Không có row mới.
- Không dùng database CHECK constraint như bằng chứng duy nhất cho 400.

**Test duplicate:**
- Insert đầu thành công.
- Insert thứ hai cùng PK bị JDBC reject, HTTP 409.
- Row gốc vẫn đúng quantity=2, không bị overwrite.
- Cleanup xóa đúng row hiện có.

### 6.3. Vì sao @AfterEach cleanup ở đây an toàn?

Lớp **không** gắn `@Transactional` ở test/class. Khi `repository.deleteById(orderId)` chạy sau response:
- Không có test-managed TX bao bọc `@AfterEach`.
- JDBC statement lấy connection, thực hiện delete và hoàn tất theo auto-commit mặc định trong lab.
- Test đọc lại `COUNT(*)=0` để kiểm delete đã có hiệu lực.
- ID riêng tránh ảnh hưởng methods/classes khác.

**Không có cleanup toàn bảng.** Nếu test fail sau HTTP POST nhưng trước assert, `@AfterEach` vẫn có cơ hội delete đúng ID. Nếu JVM bị kill hoặc server shutdown giữa chừng, callback có thể không chạy; cần cleanup môi trường CI/TTL/schema isolation cho những lần abort thô.

### 6.4. Rủi ro nếu repository auto-commit không giống giả định

Nếu bạn thêm một transaction ngoài, custom `PlatformTransactionManager` hoặc datasource có auto-commit false, targeted delete chưa chắc đã commit. Khi đó:
- Chỉ ra rõ transaction boundary của cleanup.
- Dùng `TransactionTemplate.executeWithoutResult(...)` nếu muốn explicit commit.
- Hoặc thực hiện `@Sql(..., transactionMode=ISOLATED)` với script được isolate đúng scope.
- Verify bằng **query sau commit** với một connection mới.

Không chèn `@Transactional` lên cả class test chỉ vì nó “trông chuẩn integration test”; chính annotation này sẽ thay lifecycle của cleanup.

## 7. Test 2: Chứng minh hai số phận khác nhau sau rollback

### 7.1. RealHttpRollbackBoundaryTest.java

`src/test/java/com/example/httpcleanup/RealHttpRollbackBoundaryTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class RealHttpRollbackBoundaryTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository repository;

    private String clientMarkerId;
    private String httpOrderId;
    private boolean httpCreated;

    @BeforeTransaction
    void createIdsOutsideTheTestTransaction() {
        clientMarkerId = "client_" + UUID.randomUUID()
                .toString().replace("-", "");
        httpOrderId = "server_" + UUID.randomUUID()
                .toString().replace("-", "");
        httpCreated = false;
    }

    @Test
    void testThreadRollbackCannotUndoCommittedHttpWrite() {

        // Bên trong test-managed transaction [TX-T]:
        repository.insert(new OrderRecord(
                clientMarkerId, "client-marker", 1));

        assertThat(repository.countById(clientMarkerId))
                .isEqualTo(1L);

        // Real HTTP sử dụng server thread và transaction [TX-S].
        ResponseEntity<OrderRecord> response =
                http.postForEntity(
                        "/orders",
                        new CreateOrderRequest(
                                httpOrderId, "server-request", 7),
                        OrderRecord.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(response.getBody())
                .isEqualTo(new OrderRecord(
                        httpOrderId, "server-request", 7));

        httpCreated = true;

        // Không tự gọi repository.delete() ở đây.
        // Test thread [TX-T] sẽ tự rollback sau method.
    }

    @AfterTransaction
    void compareCommittedStatesAndCleanupAfterRollback() {
        if (clientMarkerId == null || httpOrderId == null) {
            return;
        }

        try {
            // Marker do test thread tạo phải biến mất
            // sau rollback của test-managed transaction.
            assertThat(repository.countById(clientMarkerId))
                    .as("test-thread marker was rolled back")
                    .isZero();

            if (httpCreated) {
                // Row được server-side transaction commit,
                // không bị rollback cùng TX-T.
                assertThat(repository.countById(httpOrderId))
                        .as("HTTP server write remained committed")
                        .isEqualTo(1L);
            }
        }
        finally {
            // @AfterTransaction chạy NGOÀI TX-T.
            // Cleanup targeted ngay cả khi assertion fail.
            repository.deleteById(httpOrderId);
            repository.deleteById(clientMarkerId);
        }

        assertThat(repository.countById(clientMarkerId))
                .isZero();

        assertThat(repository.countById(httpOrderId))
                .isZero();
    }
}
~~~

### 7.2. Những checkpoints có ý nghĩa

| Checkpoint | clientMarkerId | httpOrderId |
| --- | --- | --- |
| Trước test | Không có | Không có |
| Trong test, sau insert marker | Có trong TX-T, chưa commit | Chưa có |
| Sau real HTTP POST 201 | Có trong TX-T | Đã commit qua TX-S |
| `@AfterTransaction` sau default rollback | **0** | **1** |
| Sau cleanup ngoài TX-T | **0** | **0** |

Test này **cố tình** có `@Transactional` để cho thấy rollback chỉ áp dụng cho marker của JUnit thread; HTTP order vẫn committed. Trong integration suite thông thường, bỏ `@Transactional` và dùng mô hình cleanup ở lớp trước sẽ đơn giản hơn.

### 7.3. Vì sao cần @BeforeTransaction?

`@BeforeTransaction` chạy **trước** test-managed TX. Trong lab nó tạo IDs, không ghi DB. Cũng có thể dùng để:
- Kiểm database baseline từ một connection ngoài test TX.
- Seed fixtures cần committed state trước khi HTTP request chạy.
- Đo current count trước test.
- Bảo đảm row cũ từ run khác không tồn tại, nếu ID đã có lifecycle riêng.

**Cẩn thận:** Nếu cố insert fixture trong `@BeforeEach` của transactional test, fixture thường vẫn thuộc TX-T và **server thread không thể đọc dữ liệu chưa commit**. Đó là một nguyên nhân gây 404 hoặc foreign-key failure trong real HTTP test.

### 7.4. Vì sao cần @AfterTransaction?

Callback này chạy sau test transaction kết thúc. Vì vậy:
- Query không nằm trong TX-T cũ.
- Nhìn đúng trạng thái persisted sau rollback.
- Cleanup có thể commit độc lập qua JdbcTemplate/autocommit lab.
- `finally` bảo vệ cleanup khi assertion fail.

Nếu dùng `@AfterEach` trong cùng class, callback được chạy **trong TX-T**, nên DELETE của HTTP row có thể rollback và để lại row. Vì thế **không** đưa cleanup server row vào `@AfterEach` của class này.

### 7.5. Tại sao có biến httpCreated?

HTTP request có thể fail trước khi server nhận đủ dữ liệu. Nếu test body chưa nhận HTTP 201, ta không thể assert chắc chắn server order đã commit. Biến `httpCreated` chỉ true sau response 201. Nhưng cleanup trong `finally` vẫn xóa order ID ngay cả khi request/response có lỗi giữa chừng, để giảm nguy cơ sót dữ liệu nếu server đã commit mà client bị mất response.

Trường hợp network timeout với server operation còn chạy **sau** cleanup là bài toán phức tạp hơn: cần operation ID, idempotency và completion/settling protocol, không chỉ `@AfterTransaction` hoặc sleep. Lab cố ý dùng synchronous service action để giữ contract rõ.

### 7.6. Một chi tiết quan trọng về test method failure

Nếu assert HTTP response fail, `@AfterTransaction` vẫn có thể được gọi trong normal test lifecycle để cleanup. Nhưng nếu JVM bị kill/timeout quá mức, callback không được bảo đảm. Cleanup không phải durable compensation mechanism cho production, chỉ là cơ chế kiểm thử. Với test server không stable, isolate DB/container cho each run.

## 8. Test 3: MockMvc đồng bộ có thể rollback chung với JUnit test

### 8.1. MockMvcRollbackContrastTest.java

`src/test/java/com/example/httpcleanup/MockMvcRollbackContrastTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class MockMvcRollbackContrastTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    OrderRepository repository;

    private String orderId;

    @Test
    void synchronousMockMvcRequestJoinsTestTransaction()
            throws Exception {

        orderId = "mock_" + UUID.randomUUID()
                .toString().replace("-", "");

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "mock-test", 4);

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                objectMapper.writeValueAsString(
                                        request)))
                .andExpect(status().isCreated());

        // MockMvc đồng bộ xử lý request trong test thread.
        // @Transactional(REQUIRED) service join TX test.
        assertThat(repository.countById(orderId))
                .isEqualTo(1L);
    }

    @AfterTransaction
    void verifyNoCommittedRowAfterTestRollback() {
        if (orderId == null) {
            return;
        }

        try {
            assertThat(repository.countById(orderId))
                    .as("synchronous MockMvc write rolled back")
                    .isZero();
        }
        finally {
            // Chỉ là safety cleanup nếu implementation đổi.
            repository.deleteById(orderId);
        }
    }
}
~~~

### 8.2. So sánh với real HTTP

Synchronous MockMvc `perform` gọi Servlet/MVC chain trong test process và thường trên cùng test thread. Service `@Transactional` dùng propagation default `REQUIRED`, nên JDBC write có thể tham gia TX-T. Test method đọc thấy row trong transaction, nhưng `@AfterTransaction` xác nhận row đã biến mất.

Real HTTP:
- Request gửi qua socket.
- Server worker thread có TX-S.
- TX-S commit độc lập.
- TX-T rollback không tác động server order.

**Không nhầm MockMvc PASS với bằng chứng rằng production HTTP request tự rollback theo JUnit test.** MockMvc là phép thử rất có giá trị cho controller/filter/JSON/security, nhưng **khác boundary** và có thể không phát hiện data residue sau actual HTTP request.

### 8.3. Khi MockMvc không còn cùng transaction

Những điều có thể thay đổi kết quả:
- Async servlet controller/`Callable`/`DeferredResult` xử lý trên worker khác.
- `@Async` dispatch từ service.
- Service `REQUIRES_NEW`, explicit `TransactionTemplate` hoặc khác transaction manager.
- DB calls qua message broker/remote service.
- Reactive R2DBC context propagation thay vì imperative ThreadLocal.
- Test dùng `@Transactional(propagation=NOT_SUPPORTED)`/`TestTransaction.end()`.

Với các đường này, phải kiểm cụ thể transaction context và committed state. Không khẳng định mọi MockMvc execution “luôn rollback được”.

## 9. Chạy lab và đọc báo cáo đúng

### 9.1. Điều kiện

- JDK 17+.
- Apache Maven.
- Dependencies có thể tải từ Maven Central/cache.
- Không cần Docker (H2 in-memory).
- Port HTTP được OS cấp động, không cần hard-code 8080.

### 9.2. Lệnh chạy

~~~bash
mvn -q clean test

mvn -q -Dtest=RealHttpCleanupIntegrationTest test

mvn -q -Dtest=RealHttpRollbackBoundaryTest test

mvn -q -Dtest=MockMvcRollbackContrastTest test
~~~

**Số test methods được thiết kế:**
- `RealHttpCleanupIntegrationTest`: 4.
- `RealHttpRollbackBoundaryTest`: 1.
- `MockMvcRollbackContrastTest`: 1.
- Tổng **6** JUnit methods nếu được Surefire discover và execute đầy đủ.

Các assertions quan trọng:
- Real HTTP 201 → row tồn tại sau response → target cleanup = 0.
- Real HTTP 500 từ service exception → database row = 0.
- Real HTTP 400 invalid request → database row = 0.
- Real HTTP 409 duplicate → row ban đầu giữ nguyên.
- Real HTTP + test-managed @Transactional → test marker rollback = 0, server row = 1 **sau TX rollback**, cleanup = 0.
- MockMvc synchronous + test-managed @Transactional → row bên trong TX = 1, sau rollback = 0.

### 9.3. Không khẳng định kết quả chưa chạy

Các đoạn mã được trình bày theo API Java 17/Spring Boot 3.5.16 và được rà soát về cấu trúc/imports/flow. Tuy nhiên, **Maven/JUnit chưa được thực thi trong quá trình soạn bài**; các giá trị trên là **kỳ vọng cần xác minh khi chạy**, không phải report “Tests run: 6, Failures: 0” đã được quan sát.

Khi chạy thực tế:
- Xem Maven exit code.
- Xem `target/surefire-reports`.
- Đối chiếu số executed, failed, errors và skipped.
- Kiểm không có lingering row theo test IDs.
- Không chỉ đọc dòng “BUILD SUCCESS” nếu tests bị skip hoặc rerun failures.

### 9.4. Quan sát transactions bằng logs

Khi cần điều tra, bật test-only logging:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.jdbc.support.JdbcTransactionManager=DEBUG
logging.level.org.springframework.test.context.transaction=DEBUG
~~~

Logger cụ thể tùy Spring version/transaction manager, không nhất thiết mọi category đều phát log. Mục tiêu:
- Gắn transaction begin/commit/rollback với thread name và service method.
- Xem test-managed rollback thuộc JUnit thread.
- Xem service transaction commit thuộc HTTP worker.
- Không in credentials/PII.
- Không assert exact framework log text như business contract; dùng database state mới là chứng cứ chính.

### 9.5. Assertion theo HTTP response chỉ là bước đầu

HTTP 201 không tự chứng minh **dữ liệu durable** nếu application:
- Trả response trước khi async write complete.
- Ghi vào in-memory cache nhưng chưa commit DB.
- Publish event vào broker mà consumer chưa xử lý.
- Swallow exception rồi trả 201.
- Dùng fire-and-forget `@Async`.

Lab sử dụng synchronous `@Transactional` service và JDBC insert. Nếu ứng dụng thật có async, phải chờ completion/idempotency/commit signal đúng contract rồi kiểm DB bằng connection độc lập.

## 10. Tại sao @Transactional không lan qua threads?

### 10.1. TransactionSynchronizationManager

Spring imperative transaction management lưu context tài nguyên và transaction metadata theo thread. Trong thực tế:
- `DataSourceTransactionManager`/`JdbcTransactionManager` bind `ConnectionHolder` với thread.
- `JdbcTemplate` lấy current connection qua Spring datasource utilities.
- `@Transactional` proxy begin/join/suspend transaction trong thread gọi method.
- ThreadLocal đó **không được tự động copy** sang Tomcat thread xử lý HTTP hoặc executor thread.

Một outbound HTTP request không thể mang một JDBC `Connection` đang mở trong thread test qua socket và magically enlist server JDBC connection vào cùng TX. Muốn distributed transactions cần protocol/scheme riêng; app REST bình thường không dùng cơ chế đó.

### 10.2. @Transactional trên controller có làm khác không?

Nếu controller method có `@Transactional`, transaction cũng thuộc **server thread**. Nó có thể bao cả controller/service flow, nhưng vẫn **độc lập với JUnit test transaction**. Vì vậy không dùng “thêm @Transactional controller” làm giải pháp cleanup sau HTTP test.

### 10.3. Propagation.REQUIRED

Nếu một transactional service method được gọi trong thread đã có transaction:
- Default `REQUIRED` tham gia transaction hiện tại.
- Với MockMvc đồng bộ trong test-managed TX, service có thể join.
- Với real HTTP server thread không có TX test, service mở transaction mới.

Do đó annotation **giống nhau** nhưng state bên ngoài khác; quyết định dựa trên **caller thread/active transaction** chứ không dựa vào tên annotation đơn lẻ.

### 10.4. Propagation.REQUIRES_NEW

`REQUIRES_NEW` thường suspend outer transaction và mở một transaction vật lý riêng. Trong test MockMvc cùng thread, service `REQUIRES_NEW` có thể commit dữ liệu mà test transaction rollback **không** thu hồi. Nếu muốn kiểm ranh giới này, tạo dedicated test và cleanup sau TX; đừng thêm `REQUIRES_NEW` vô tình rồi kỳ vọng rollback mặc định dọn mọi rows.

### 10.5. Propagation.NESTED

`NESTED` sử dụng savepoints khi transaction manager/database hỗ trợ, nhưng không đồng nghĩa “transaction remote/HTTP mới”. Nested rollback có thể chỉ rollback tới savepoint trong parent TX, commit thật vẫn phụ thuộc parent transaction. JDBC vs JPA managers hỗ trợ khác nhau. Không trộn nó với `REQUIRES_NEW`.

### 10.6. @Rollback và @Commit

Spring test annotations:
- `@Rollback` hoặc `@Rollback(true)`: test-managed TX rollback.
- `@Rollback(false)` / `@Commit`: test-managed TX commit.
- Chúng **không điều khiển** một transaction độc lập của HTTP server thread.
- Trên non-transactional test method, chúng không tạo TX mới thần kỳ.
- Dùng `@Commit` trên test có thể làm dữ liệu test persist, yêu cầu cleanup mạnh hơn.

Đừng đánh đổi isolation chỉ để “kiểm commit” nếu không có post-test cleanup rõ.

### 10.7. TestTransaction

Spring TestContext cung cấp `TestTransaction` để điều khiển **test-managed transaction**:
- `isActive()`.
- `flagForRollback()` / `flagForCommit()`.
- `end()`.
- `start()`.

Ví dụ minh họa (không nằm trong ba test classes runnable):

~~~java
@Test
@Transactional
void inspectCommittedStateOutsideCurrentTestTx() {
    // test transaction đang active
    assertThat(TestTransaction.isActive()).isTrue();

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertThat(TestTransaction.isActive()).isFalse();

    // Các queries ở đây chạy ngoài test transaction,
    // đọc committed DB state từ connection mới.

    TestTransaction.start();
    // New test transaction sẽ rollback khi method kết thúc.
}
~~~

Đoạn này cần imports Spring TestContext/JUnit/AssertJ và một transactional Spring test context đã cấu hình. Nó **không commit/rollback server TX-S qua HTTP**; chỉ hỗ trợ thay đổi góc nhìn của thread test. Đừng gọi `end()` mà không có active test transaction.

### 10.8. Preemptive timeout và transaction visibility

Spring Framework cảnh báo test-managed TX là thread-bound. Những API chạy body ở thread khác (ví dụ `assertTimeoutPreemptively(...)` của JUnit, một số timeout modes) có thể không thuộc test TX; writes sẽ không rollback như bạn nghĩ. Dùng bounded waits và non-preemptive timeout nếu cần kiểm transaction semantics, rồi verify committed DB state sau transaction đã kết thúc.

## 11. Dọn dữ liệu đúng phạm vi

### 11.1. Cách 1: unique ID + targeted delete

Phù hợp phần lớn HTTP integration tests:

~~~java
@BeforeEach
void setUp() {
    id = UUID.randomUUID().toString();
}

@AfterEach
void cleanup() {
    repository.deleteById(id);
}
~~~

**Điều kiện bắt buộc:** cleanup chạy ngoài test-managed transaction hoặc trong transaction riêng đã commit. Nếu class có `@Transactional` thì `@AfterEach` không đáp ứng điều kiện đó.

Ưu điểm:
- Không xóa data của test khác.
- Hợp với parallel tests.
- Test tự sở hữu fixture.
- Dễ điều tra row còn sót bằng ID.
- Không cần restart application context/container.

Hạn chế:
- Nếu entity có nhiều FK/child rows, phải cleanup theo dependency order/cascade phù hợp.
- Nếu có async operations còn chạy, delete có thể xảy ra quá sớm.
- Nếu process crash, callback không chạy.
- Với materialized view/outbox/cache, xóa row chính chưa đủ.
- Nếu DB isolation yêu cầu transaction riêng, dùng explicit boundary.

### 11.2. Cách 2: cleanup sau test transaction bằng @AfterTransaction

Phù hợp **chủ đích thử ranh giới rollback** như `RealHttpRollbackBoundaryTest`:
- JUnit rollback TX test trước.
- `@AfterTransaction` quan sát committed state.
- Cleanup ngoài TX test.
- Assert post-cleanup.

Hãy viết cleanup trong `finally` nếu test assert state có thể fail. `@AfterTransaction` không tự kích hoạt khi test không transactional. Không dùng nó trong class không có `@Transactional` rồi kỳ vọng callback chạy.

### 11.3. Cách 3: TransactionTemplate

Khi cần cleanup rõ ràng, nhất là test đang trong outer TX:
- Inject đúng `PlatformTransactionManager`.
- Xác định propagation.
- Dùng `TransactionTemplate` mở transaction commit riêng, có thể `PROPAGATION_REQUIRES_NEW` khi muốn tách outer transaction.
- Lưu ý database locks: outer TX có thể giữ lock, transaction cleanup mới chờ/timeout; tốt hơn thực hiện sau khi outer TX kết thúc.
- Kiểm cleanup bằng query ngoài cleanup transaction.

Ví dụ minh họa trong test integration đã cấu hình transaction manager:

~~~java
TransactionTemplate cleanup = new TransactionTemplate(txManager);
cleanup.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

cleanup.executeWithoutResult(status ->
        repository.deleteById(orderId));
~~~

Đoạn này **không** là magical cleanup cross-thread; nó mở transaction **trên thread đang gọi**. Phải bảo đảm không còn test-managed outer transaction giữ lock gây deadlock. Nếu cleanup đặt trong `@AfterTransaction`, transaction mới có thể commit đơn giản hơn.

### 11.4. Cách 4: @Sql AFTER_TEST_METHOD

Spring TestContext hỗ trợ:

~~~java
@Sql(
    scripts = "/cleanup-owned-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Test
void writesCommittedDataThroughHttp() {
    // ...
}
~~~

**Đây là snippet minh họa**, chưa có file SQL trong Maven project. Script cleanup phải phù hợp fixture namespace **độc quyền** của test; annotation SQL tĩnh khó nhận `UUID` động ở runtime. Dùng một test schema/database riêng khi script cần `TRUNCATE` hoặc fixed data IDs. Không áp global `DELETE FROM demo_orders` cho một shared DB chạy parallel.

### 11.5. TransactionMode.DEFAULT vs ISOLATED

`@SqlConfig(transactionMode=DEFAULT)` cho Spring suy ra transaction semantics dựa trên DataSource, transaction manager và current test TX:
- Script có thể chạy **bên trong** test-managed transaction.
- Nếu script delete chạy trong TX test rồi test rollback, delete có thể bị rollback.
- `ISOLATED` yêu cầu script chạy trong một transaction độc lập, commit khi thành công theo Spring SQL test infrastructure.
- `AFTER_TEST_METHOD` xác định **thời điểm tương đối với test method** của script, không tự mặc định bảo đảm độc lập/commit mọi tình huống.

Vì vậy cần nêu rõ **cả executionPhase và transactionMode** khi mục tiêu là committed cleanup cho HTTP writes. Kể cả `ISOLATED`, vẫn phải giải quyết dữ liệu owner và lock contention.

### 11.6. @Sql BEFORE_TEST_METHOD và committed fixtures

HTTP server thread cần nhìn được fixture (customer/account/order parent) trước request. Nếu bạn seed qua:
- `@BeforeEach` của một `@Transactional` test: fixture thường **chưa commit**, server không thấy.
- `@Sql(..., transactionMode=DEFAULT)` của một transactional test: script có thể nằm trong test TX, chưa commit.
- `@Sql(..., transactionMode=ISOLATED)`: có thể commit fixture độc lập trước request, phù hợp khi test yêu cầu.

Thay vì script SQL toàn cục, có thể dùng `@BeforeTransaction` hoặc `TransactionTemplate` committed seed với unique ID. Sau test, cleanup đúng ID và dependent rows.

### 11.7. @Sql AFTER_TEST_CLASS

Spring Framework 6.1+ hỗ trợ class-level SQL scripts trước/sau class. Nó hữu ích cho schema/fixture class-owned nhưng **không** giải quyết row leak nếu nhiều classes cùng DB và cleanup cuối class xóa records của class khác. Nếu suite parallel, class-level cleanup phải namespace/data owner rõ. Không dựa vào “chạy cuối class” để bảo đảm tất cả asynchronous requests đã hoàn tất.

### 11.8. @TestInstance(PER_CLASS) và data state

Nếu test class dùng `@TestInstance(PER_CLASS)`, fields có thể còn qua các test methods. Không giữ một `id` mutable dùng chung cho parallel methods mà không isolation. Tạo per-method UUID/namespace; với class-scope resource, dùng ownership rõ và không ghi nhầm row khác ở teardown.

## 12. Tại sao DELETE có thể chạy nhưng data vẫn còn?

### 12.1. DELETE nằm trong transaction sẽ rollback

~~~text
Client TX-T starts
HTTP server TX-S inserts id=server-1
HTTP server TX-S COMMIT
Client @AfterEach executes DELETE id=server-1 in TX-T
Client TX-T ROLLBACK

Final DB: server-1 STILL EXISTS
~~~

Đây là một lỗi điển hình khi thấy JDBC logs có DELETE mà kết quả cleanup không bền. Thêm logging transaction hoặc `@AfterTransaction` query sẽ giúp phân biệt.

### 12.2. DELETE lọc sai tenant/ID

SQL:

~~~sql
DELETE FROM demo_orders WHERE order_id = ?;
~~~

chỉ xóa record khi ID đúng. Hãy assert affected rows khi contract cần:
- 1 row nếu đã tạo thành công.
- 0 row nếu validation/rollback không tạo.
- Với cleanup best effort sau failure, 0 rows có thể hợp lệ.
- Không assert tất cả cleanup phải ảnh hưởng 1 row nếu test có negative cases.

Thay toàn bảng bằng targeted delete là an toàn hơn, nhưng phải dùng **ID đã gửi đi qua HTTP**, không một ID mới generate lúc teardown.

### 12.3. Async worker ghi lại row sau delete

Nếu endpoint trả 202 Accepted rồi xử lý sau:
- Test gọi DELETE trước worker commit.
- Worker sau đó INSERT.
- Sau suite row lại xuất hiện.

Cần business operation ID, completion signal/event status, bounded await, và cleanup sau terminal state. Không dùng `Thread.sleep(5000)` làm bằng chứng worker đã hoàn tất.

### 12.4. Cascade/foreign keys/outbox

Xóa đơn chính có thể bị FK constraint từ line items/outbox/payment receipts. Có các lựa chọn:
- Schema có `ON DELETE CASCADE` khi đúng business semantics.
- Cleanup child rows trước parent.
- Per-test tenant/schema/container isolate.
- TransactionTemplate cleanup cùng một atomic transaction.
- Xóa artifacts ngoài DB theo owner, không chỉ core row.

Không disable FK constraints trong test để “đỡ cleanup” nếu production dựa vào chúng.

### 12.5. Soft delete

Trong ứng dụng dùng `deleted_at` hoặc flag, `DELETE` có thể là soft delete tại repository service level (không phải SQL DELETE như lab). Khi test cần DB sạch, dùng cleanup admin/persistence layer phù hợp; nhớ không bypass security/tenant constraints ra data của test khác.

### 12.6. @AfterEach không chạy trong mọi sự cố

JUnit callbacks chạy trong lifecycle bình thường, kể cả assertion fail. Nhưng:
- JVM bị kill.
- Test timeout hung.
- CI job bị ngắt.
- Docker host crash.
- Test process dừng cưỡng bức.

Khi đó cleanup có thể không chạy. Per-run isolated schema/container và TTL/CI teardown là tuyến bảo vệ bổ sung.

## 13. Test dữ liệu sạch phải kiểm theo invariant cụ thể

### 13.1. Không dùng COUNT(*) toàn bảng trong shared suite

~~~sql
SELECT COUNT(*) FROM demo_orders;
~~~

Kết quả có thể bao gồm rows từ tests khác đang chạy. “Bảng phải trống” chỉ là invariant hợp lệ khi **test sở hữu độc quyền toàn database/schema**. Với tests chia sẻ DB:
- `WHERE order_id = ?`.
- Hoặc `WHERE owner_tag = ?` nếu owner tag unique per test.
- Hoặc schema-per-test/tenant-per-test.
- Hoặc dedicated DB/container cho global assertions.

### 13.2. UUID không bảo đảm cleanup đúng nếu request retry tạo nhiều rows

Một operation có thể sinh:
- Order row.
- Payment attempt rows.
- Outbox events.
- Audit records.
- Cache entries.

Phải xác định **tập resources do test tạo** và cleanup theo operation ID. Chỉ xóa một order ID có thể không đủ nếu event vẫn chạy hoặc outbox còn pending.

### 13.3. Dữ liệu synthetic

Dùng IDs và owner tags như `http_<uuid>`, `server_<uuid>`, `test-run-...`; không dùng customer account hoặc email thật. Log/CI artifact tránh token, JDBC password và dữ liệu nhạy cảm. Nếu test request có authentication, secrets phải quản lý theo test environment.

### 13.4. Retry và idempotency

POST có thể được client retry sau timeout dù server đã commit. Không dùng “không nhận được 201” làm bằng chứng DB không có order. Sử dụng operation idempotency key ổn định; GET theo key hoặc querying record giúp xác định final state. Cleanup nên xóa records theo key **được gửi**, không chỉ khi response status được thấy.

### 13.5. Parallel tests và transaction isolation

Hai tests khác nhau:
- Mỗi test có UUID ID → giảm key collision.
- Mỗi transaction có connection riêng → DB có thể xử lý concurrent operations.
- `DELETE ALL`/`TRUNCATE` → không an toàn trong shared environment.
- Unique owner tag cho cleanup compound resources.
- Với global fixtures, dùng per-schema/per-container hoặc JUnit `@ResourceLock` chỉ để điều phối tests trong **cùng engine**, không phải distributed DB lock.

Một transaction rollback của test A không undo commit của test B, cũng như không undo server request của chính A.

## 14. Sự khác nhau giữa kiểm MockMvc và real HTTP trong thực tế

### 14.1. MockMvc hữu ích ở đâu?

- Controller mapping/status/headers.
- JSON serialization/deserialization.
- Validation errors.
- Filter/security behavior khi cấu hình đúng.
- Handler method exceptions.
- MVC advice.
- Fast integration với synchronous Spring MVC dispatch.

MockMvc **không cần mở TCP port**, không đo handshake/network/server concurrency thực, và đôi khi cùng test transaction. Do đó một MockMvc test rollback sạch không đủ để kết luận real HTTP endpoint sẽ được cleanup tự động.

### 14.2. Real HTTP hữu ích ở đâu?

- Embedded server startup/port configuration.
- Serialization qua socket thực.
- Request/response boundaries.
- Transaction separation giữa client và server.
- Security headers/cookies/auth flows thực tế.
- Server-side commit/rollback outcomes.
- Compression/streaming/redirect behavior.
- Server thread pool/concurrency/timeout.
- Integration với external services nếu có.

Đổi lại, real HTTP cần explicit data cleanup, database readiness, port ownership, và kiểm thread/lifecycle kỹ hơn.

### 14.3. @WebMvcTest vs @SpringBootTest(MOCK)

`@WebMvcTest` là web slice; thông thường inject `@MockitoBean` cho service collaborator, vì full DB/service stack không được nạp. Nó không kiểm real transaction commit của service. `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` nạp full application context (trừ khi customizations) và test real service/database logic **trong cùng process**.

Cả hai vẫn không phải `RANDOM_PORT` HTTP thật. Chọn phạm vi test theo invariant cần chứng minh.

### 14.4. @WebFluxTest và reactive transactions

Spring WebFlux reactive pipelines không dựa hoàn toàn vào imperative ThreadLocal như MVC/JDBC; reactive transaction context được truyền qua Reactor Context trong reactive chain. Nếu test dùng WebTestClient/WebFlux/R2DBC, phải phân tích subscription, scheduler và reactive transaction operator. Không copy nguyên kết luận “MockMvc cùng thread” sang WebFlux và suy reactive transaction join một cách tự động.

### 14.5. Thread boundary trong MockMvc async

Với `Callable`, `DeferredResult` hoặc service `@Async`:
- Request có thể bắt đầu trên test thread.
- Business action chạy worker thread.
- Worker JDBC operations không mặc định thuộc test-managed TX.
- `MockMvc.perform` với async start phải theo đúng `asyncDispatch`/completion testing.
- Test có thể để lại committed rows dù không mở TCP server.

Điều quan trọng là **transaction owner/active context của actual write**, không phải chỉ tên test client library.

## 15. Server rollback: kiểm tra đúng failure path

### 15.1. Throw trước transaction commit

Lab dùng:

~~~java
@Transactional
public void createThenFail(CreateOrderRequest request) {
    repository.insert(new OrderRecord(
            request.id(),
            request.owner(),
            request.quantity()));

    throw new IllegalStateException(
            "forced rollback before commit");
}
~~~

`IllegalStateException` là unchecked exception. Với default rollback rules của Spring, transaction interceptor rollback. Test không chỉ xem 500; nó query database và GET 404.

### 15.2. Catch exception bên trong @Transactional

Cẩn thận với:

~~~java
@Transactional
public void suspicious(CreateOrderRequest request) {
    try {
        repository.insert(new OrderRecord(
                request.id(), request.owner(), request.quantity()));
        riskyOperation();
    }
    catch (RuntimeException error) {
        log.warn("operation failed", error);
    }
}
~~~

**Snippet phản ví dụ**, không thuộc runnable project. Nếu method trả bình thường và transaction không được đánh dấu rollback-only, Spring có thể commit insert mặc dù log có “operation failed”. Muốn rollback khi lỗi nghiệp vụ, propagate exception hoặc mark rollback-only theo contract, và test final DB state.

### 15.3. Checked exceptions

Mặc định Spring declarative transaction rollback trên `RuntimeException` và `Error`; checked exception thường không tự rollback trừ khi cấu hình `rollbackFor`/rollback rules. Một test HTTP path trả 500 vì checked exception **không chứng minh** data đã rollback. Kiểm transaction attributes cụ thể.

### 15.4. @Transactional self-invocation

Một method trong cùng bean gọi `this.createThenFail(...)` có thể bypass proxy advice mặc định. Khi đó code có thể chạy ngoài transaction hoặc tham gia một transaction khác. Tách transactional boundary sang Spring bean được inject/call qua proxy hoặc áp dụng AOP arrangement phù hợp. Test nên đi qua real controller/service wiring như lab.

### 15.5. Transaction commit có thể thất bại sau service body

Với JPA/Hibernate, SQL có thể chỉ flush ở commit. Một method return thành công từ body không có nghĩa transaction commit đã PASS nếu commit interceptor throw sau đó. HTTP 201 chỉ nên được trả sau service proxy return mà commit succeeded; nếu exception xảy ra ở commit, controller exception handling phải phù hợp. Test phải kiểm actual DB state, không chỉ log "save called".

### 15.6. Negative outcome nào phải được assert?

Một robust transaction test kiểm:
- HTTP status hợp đồng.
- Response body/error code ổn định.
- DB row count/by-ID.
- Không có partial outbox/line items sai.
- Retry behavior nếu API hỗ trợ.
- Idempotency key nếu payment-like.
- Dữ liệu đã cleanup sau test.

Không assert exact stack trace hoặc JDBC exception text như public API contract.

## 16. JPA/Hibernate: thêm flush và clear khi cần

Lab dùng `JdbcTemplate` nên mỗi query đọc DB trực tiếp, không có JPA first-level persistence context cache. Nếu bạn dùng Spring Data JPA:
- `repository.save(entity)` có thể trì hoãn SQL đến flush/commit.
- `EntityManager` có first-level cache và dirty checking.
- Query trong cùng persistence context có thể trả managed entity chứ chưa phản ánh transaction của thread khác theo cách bạn nghĩ.
- `entityManager.flush()` gửi pending SQL trong transaction.
- `entityManager.clear()` loại managed entities trước khi đọc lại; chỉ dùng khi phù hợp transaction/visibility.
- Với tests cần post-commit behavior, verify từ transaction/EntityManager mới hoặc `@AfterTransaction`.
- `TestEntityManager.flush()` giúp lộ constraint violations đã bị trì hoãn trong JPA slice tests.

**Nhưng flush ≠ commit.** Một row đã flush trong TX-T có thể vẫn chưa visible từ HTTP server thread và sẽ bị rollback sau test. Đừng hiểu “đã flush” là “server thấy dữ liệu”.

### 16.1. Example JPA probe (snippet)

~~~java
@PersistenceContext EntityManager em;

@Test
@Transactional
void flushIsNotCommit() {
    repository.save(new CustomerEntity(...));
    em.flush();

    // SQL đã gửi tới DB trong TX test, nhưng chưa COMMIT.
    // Server HTTP trên connection khác thường không thấy row
    // cho đến khi test transaction được commit.
}
~~~

Đây là snippet minh họa, **không** thuộc project Maven JDBC và không độc lập biên dịch nếu thiếu CustomerEntity/repository imports. Nó chỉ nhấn mạnh flush/commit boundary.

### 16.2. OSIV không làm hai requests thành một transaction

Spring Boot có thể bật Open Session in View ở Servlet/JPA applications (tùy config). OSIV giữ EntityManager gắn với request để lazy-loading, nhưng không tự biến JUnit test transaction và HTTP server transaction thành một. Cần phân biệt entity manager lifetime, transaction lifetime và HTTP request lifecycle.

### 16.3. Database isolation levels

Ở READ_COMMITTED, một transaction khác có thể thấy committed row sau commit; ở REPEATABLE_READ có snapshot behavior khác. Với test client TX-T đã bắt đầu trước server commit, một query **trong** TX-T có thể không phản ánh server state tùy DB/isolation. `@AfterTransaction` là vị trí đáng tin hơn để kiểm final committed state ngoài TX-T. PostgreSQL và H2 có implementation khác; đừng suy nguyên tắc isolation production từ H2 alone.

## 17. Testcontainers khi cần database thật

### 17.1. Tại sao H2 không đủ cho mọi bài?

H2 hữu ích cho:
- Demo ranh giới thread/transaction.
- Fast JDBC CRUD.
- Kiểm validation, basic constraints.
- Local repeatable training.

Không thay thế PostgreSQL/MySQL cho:
- Locking/MVCC isolation anomalies.
- Sequence behavior.
- JSONB/array/vendor-specific types.
- SQL syntax/collation.
- Native upsert/CTE.
- Transaction deadlock/serialization retry.
- Flyway migration dùng database dialect thật.

Nếu API contract dựa vào những behavior đó, chạy integration tests với **Testcontainers PostgreSQL**.

### 17.2. Test-only bean + @ServiceConnection

Với Spring Boot 3.5:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresIntegrationConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("http_rollback_it");
    }
}
~~~

**Snippet tùy chọn**, cần `spring-boot-testcontainers` và `org.testcontainers:postgresql` test dependencies cùng imports, không nằm trong Maven H2 lab. Import config vào `@SpringBootTest` qua `@Import`. Spring-managed bean giúp lifetime PostgreSQL khớp cached ApplicationContext, không bị JUnit extension stop trước khi context client hết dùng.

### 17.3. Container reuse không dọn dữ liệu

Dù container là Spring bean, singleton JVM hay reuse opt-in:
- Rows committed qua HTTP vẫn còn.
- `@DirtiesContext` có thể close one context nhưng DB shared ngoài context không nhất thiết reset.
- Tests cần unique IDs/schema và explicit cleanup.
- Stop container là cleanup infrastructure, không phải bằng chứng từng test đã isolate business state.

### 17.4. Dynamic JDBC URL

Testcontainers dùng mapped host/port động. Không hard-code `jdbc:postgresql://localhost:5432` nếu container map sang port khác. `@ServiceConnection` cung cấp connection details; hoặc `@DynamicPropertySource` đúng lifecycle. Một DataSource cached vẫn trỏ old port nếu container bị restart sai ownership, gây connection refused — không phải một rollback issue.

### 17.5. Dọn PostgreSQL an toàn khi parallel

Chiến lược:
- Per-test UUID order IDs.
- Per-test unique owner tag.
- Targeted child-before-parent deletion.
- Dedicated schema khi test cần `TRUNCATE`/global count.
- Dedicated container/context khi test cần database-wide migration/reset.
- Nếu teardown fail, CI post-job cleanup theo resources do job sở hữu.
- Không `DROP SCHEMA public CASCADE` trên shared DB với tests khác.
- Cần độ tin cậy cao: query committed state từ connection mới sau cleanup.

## 18. Async, message và after-commit side effects

### 18.1. HTTP response trước async completion

Một endpoint có thể:
1. Nhận POST.
2. Persist request status PENDING.
3. Enqueue job.
4. Trả HTTP 202.
5. Worker xử lý DB/Redis/Kafka sau đó.

Rollback của test client không ảnh hưởng worker transaction. `@AfterEach` cleanup ngay sau 202 có thể chạy **trước** worker, sau đó worker ghi lại row. Phương pháp:
- Dùng operation ID.
- Chờ job terminal state với bounded condition-based await.
- Query durable DB state sau completion.
- Cleanup theo operation ID khi không còn pending workers.
- Không dùng fixed sleep thay job completion.

### 18.2. @TransactionalEventListener(AFTER_COMMIT)

Nếu service phát application event và handler `@TransactionalEventListener(phase=AFTER_COMMIT)`:
- Sự kiện chỉ được xử lý theo phase khi transaction phát event commit (theo điều kiện listener/fallback).
- Trong real HTTP, server transaction commit có thể kích hoạt handler.
- Trong synchronous MockMvc dùng test transaction rollback, `AFTER_COMMIT` listener không chạy vì TX-T rollback.
- Do đó MockMvc vs real HTTP có thể khác **cả side effects**, không chỉ DB row.
- Nếu listener thực hiện DB write sau commit, cần transaction semantics rõ (đôi khi `REQUIRES_NEW`) và kiểm outbox/durable action.

### 18.3. AFTER_COMMIT không đồng nghĩa side effect atomic với DB

Handler sau commit có thể fail, trong khi DB order đã committed. Khi cần delivery guarantee, dùng transactional outbox/idempotent consumers/retry. Test rollback boundary phải xác định:
- Main row committed?
- Outbox event committed?
- Handler delivered/acknowledged?
- Duplicate operation có được chống?
- Cleanup có xóa đúng cả outbox/test-owned data?

Một HTTP 201 không chứng minh external broker publish đã thành công nếu architecture không ràng buộc.

### 18.4. @Async transaction boundary

`@Async` hoặc `CompletableFuture` chạy thread khác, không tự nhận JUnit test ThreadLocal TX. Khi test:
- Inject controlled executor.
- Đợi completion bằng `Future.get(timeout)` hoặc Awaitility.
- Kiểm committed/rolledback rows từ transaction độc lập.
- Shutdown executor theo context lifecycle.
- Cleanup sau completion.
- Không stop shared executor ở `@AfterEach` nếu context còn phục vụ classes khác.

### 18.5. Kafka/RabbitMQ consumers

HTTP endpoint có thể publish Kafka/Rabbit message; consumer xử lý với DB transaction riêng:
- Test client rollback không rollback broker offset/ack.
- Unique topic/group/queue và eventId giúp isolate.
- Nếu consumer vẫn active sau test, teardown có thể xóa fixture trước khi process xong.
- Dùng durable completion signal và bounded awaits.
- Dọn đúng topic/event/cache namespace, không reset global broker đang dùng chung.

### 18.6. Các hệ thống external khác

- Redis: key writes không tự rollback bởi JDBC transaction.
- Email/SMS: không có database rollback cho đã gửi thật; dùng fake gateway/test inbox.
- S3/blob storage: object writes cần test-owned prefix và cleanup.
- Payment gateway: idempotency key và sandbox, không dùng money thật.
- Search index: eventual indexing cần bounded await/cleanup.
- Audit logs: cần xác định chúng có phải contract và được ghi lúc nào.
- Filesystem: `Files.writeString` không tham gia JDBC rollback.

Rollback là cơ chế của **transaction manager/resource set cụ thể**, không phải “undo mọi side effect trong chương trình”.

## 19. Bẫy ở @Sql và test fixtures

### 19.1. Seed bên trong test TX nhưng gửi HTTP thật

~~~java
@BeforeEach
void seedCustomer() {
    customerRepository.save(new Customer("c1"));
}
~~~

Trong `@Transactional` HTTP test, row được save có thể chưa commit. HTTP server xử lý POST liên kết customer c1 sẽ query **connection khác**, có thể không thấy c1 → 404/FK fail. Có người “sửa” bằng `Thread.sleep` hoặc disable FK; cả hai sai. Cần seed committed trước real HTTP request, ví dụ `@BeforeTransaction`/`@Sql(ISOLATED)`/`TransactionTemplate`.

### 19.2. @Sql(... AFTER_TEST_METHOD) không tự đủ

~~~java
@Sql(
    statements = "DELETE FROM demo_orders",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
~~~

Snippet này **không nên copy vào shared suite**: không namespace, có nguy cơ xóa rows test khác và transaction semantics có thể không như bạn kỳ vọng. Phải xác định:
- Script thực hiện **lúc nào**?
- Nó chạy trong **transaction nào**?
- Cleanup statement có commit không?
- Nó có xóa data thuộc test khác không?

### 19.3. SQL scripts trước/sau class

`@Sql` class phase có thể giúp setup shared test fixture, nhưng:
- Class-level fixtures không tự isolate giữa parallel methods.
- Nếu tests dùng nhiều contexts cùng DB, schema init/migration có thể race.
- `@SqlMergeMode` ảnh hưởng merge/override class vs method scripts.
- Cleanup class-level có thể xảy ra sau khi một background consumer khác đã đọc fixture.
- Static scripts không thuận tiện cho dynamic per-method UUID; khi cần per-test IDs, dùng code + repository.

### 19.4. TransactionalTestExecutionListener và @AfterTransaction

Spring Framework transaction test listener đã có hooks riêng; không cần tự gọi `TransactionAspectSupport.currentTransactionStatus()` từ test để ép rollback của server TX — thread test không sở hữu server status. Dùng `@AfterTransaction` để quan sát sau TX test và explicit cleanup.

### 19.5. @Commit/@Rollback(false) cho fixture setup

Nếu bạn muốn fixture committed trước HTTP:
- Đừng đánh dấu toàn bộ test `@Commit` chỉ để server thấy data.
- Tạo fixture ở một bước transaction **độc lập có commit** rồi gọi HTTP; after test cleanup.
- Commit toàn test có thể persist cả incidental test changes và làm suite bẩn hơn.

### 19.6. SQL script cleanup lỗi bị nuốt

Nếu `DELETE` fail vì FK constraint hoặc wrong schema, test có thể vẫn báo cleanup error riêng. Đừng swallow exception để build xanh. Nếu cleanup thất bại, chạy post-test row count và fail test có thông điệp hữu ích. Với production-like schema, test cleanup code cũng cần được review như app code.

## 20. Phân tích theo dữ liệu thay vì suy từ log

### 20.1. Timeline diagnostic chuẩn

~~~text
[JUnit main] BEFORE_TRANSACTION
  prepare client_marker_id and http_order_id

[JUnit main] TX-T BEGIN
  JDBC INSERT client marker

[JUnit main] HTTP POST httpOrderId
  [Tomcat worker] TX-S BEGIN
  [Tomcat worker] INSERT httpOrderId
  [Tomcat worker] TX-S COMMIT
[JUnit main] HTTP 201

[JUnit main] test ends
[Spring TestContext] TX-T ROLLBACK

[JUnit main] AFTER_TRANSACTION
  COUNT(client_marker_id) = 0
  COUNT(http_order_id)    = 1
  DELETE http_order_id (committed)
  COUNT(http_order_id)    = 0
~~~

Đây là output **dự kiến về sự kiện**, không phải log có timestamp đo thực. Tên thread/manager/callbacks có thể khác theo version. Dùng test ID và operation ID để ghép log, nhưng tránh log secrets.

### 20.2. Không phải cứ thấy SQL INSERT là commit

SQL logger có thể in INSERT trước khi transaction commit. Nếu later exception xảy ra, DB có thể rollback. Chỉ khi transaction manager commit thành công và fresh connection query state thì mới có evidence durable row.

### 20.3. Không phải cứ thấy DELETE là cleanup xong

DELETE trong TX test có thể rollback. DELETE trong một new transaction có thể fail ở commit. Sau cleanup cần đọc lại bằng transaction/connection phù hợp, không chỉ đếm SQL statements.

### 20.4. Lỗi do DB connection/session caching

Khi JPA EntityManager giữ managed entities, `findById` có thể trả từ first-level cache. Query mới sau `em.clear()` hoặc sử dụng riêng `JdbcTemplate`/connection có thể phản ánh committed DB rõ hơn. Nhưng ngay cả query mới trong TX với REPEATABLE_READ snapshot cũng không đảm bảo thấy server commit; kiểm sau TX test kết thúc.

### 20.5. Audit server-side transaction events

Khi cần phân biệt threads/transactions:
- Log operation id.
- Log thread name.
- Log `TransactionSynchronizationManager.isActualTransactionActive()` ở service (chỉ diagnostic).
- Log transaction begin/commit/rollback category.
- Log SQL row affected counts.
- Đừng expose SQL credentials/PII.
- Không dùng check thread name như oracle duy nhất, vì scheduler/names đổi.

Business assertion cuối cùng vẫn là row count/invariant.

## 21. Bảng xử lý các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng | Cách giải |
| --- | --- | --- | --- |
| HTTP 201 nhưng row còn sau test @Transactional | Server commit trên thread khác | @AfterTransaction count=1 | Targeted committed cleanup |
| JUnit marker biến mất, HTTP order còn | TX-T rollback, TX-S commit | Hai IDs với post-TX query | Đây là boundary đúng |
| @AfterEach DELETE chạy mà row vẫn còn | DELETE nằm trong TX-T và rollback | Transaction logs + post-TX count | @AfterTransaction/independent TX |
| MockMvc test rollback sạch, real HTTP không | Same-thread vs cross-thread | So 2 loại tests | Real HTTP cleanup explicit |
| HTTP server không thấy fixture | Fixture uncommitted trong JUnit TX | Fresh connection query | Committed setup trước POST |
| HTTP 500 nhưng row còn | Exception catch/swallow hoặc commit trước error | Post-error DB count | Sửa server transaction boundary |
| HTTP 500 và row=0 | Server-side rollback đúng | Fresh DB query | Giữ regression test |
| POST invalid 400, row vẫn có | Validation/side effect ordering sai | DB count | Validate trước write, tx rollback |
| Duplicate 409 nhưng row gốc đổi | Update logic/upsert sai | Compare persisted row | Constraint + conflict handling |
| Sử dụng @DirtiesContext vẫn còn DB rows | External state không reset | Query database sau context close | Targeted cleanup/schema isolation |
| @Sql cleanup không commit | TransactionMode.DEFAULT trong TX test | @Sql config + post-TX query | ISOLATED / after-TX cleanup |
| @Sql xóa dữ liệu test khác | Global DELETE trên shared DB | Owner tags/parallel timeline | Unique namespace/targeted delete |
| @TransactionalEventListener không chạy trong MockMvc | TX test rollback, no AFTER_COMMIT | Event logs/post-TX | Test real commit path |
| Async worker ghi row sau @AfterEach | Cleanup trước completion | Future/event status timeline | Await terminal state rồi cleanup |
| H2 test xanh, PostgreSQL fail | Different SQL/locking/isolation | Testcontainers PG | Production-like DB test |
| Tests đôi lúc duplicate ID | Fixed test fixture ID | Row ID collision | UUID per method/operation |
| Rerun test sau CI fail ra 409 | Previous committed data left behind | Owner ID/from prior run | Dedicated DB/schema/cleanup |
| Test methods parallel xóa nhau | Shared cleanup SQL | IDs/owner tags | Per-test IDs or isolate |
| Query trong TX-T không thấy HTTP commit | Snapshot isolation/visibility | After-TX fresh query | Check outside TX |
| Connection refused giữa test classes | Container stop vs cached context | Testcontainers lifecycle | Managed container bean |
| DataSource pool exhausted | Connections not closed/too few | Hikari metrics | Close/concurrency budgeting |
| Test transaction không rollback @Async | Thread-bound context not propagated | Worker DB query | Worker cleanup/tx handling |
| @Commit khiến fixture sót | Explicit test TX commit | Post-test count | Cleanup with correct owner |
| @AfterTransaction không chạy | Test method không transactional | Annotation/lifecycle | Use @AfterEach if no test TX |
| HTTP GET 404 sau POST 201 | Wrong ID, read replica lag, rollback, async | Correlation ID/DB query | Fix actual consistency path |
| CI green nhưng tests skipped | Discovery/config issue | Surefire XML executed count | Enforce test execution |
| All tests pass but residual rows | No after-suite invariant check | Per-test owner count | Add post-cleanup assertion |

## 22. Thiết kế một test suite đúng cho dự án thực

### 22.1. Phân tầng test hợp lý

Một ứng dụng có thể có:
- Unit tests cho business calculations, không Spring/DB.
- Controller slice `@WebMvcTest` cho mapping/validation/JSON với mocked service.
- Repository `@JdbcTest`/`@DataJpaTest` cho SQL/mapping và rollback mặc định.
- Full `@SpringBootTest(MOCK) + MockMvc` cho synchronous filter/controller/service composition.
- Full `@SpringBootTest(RANDOM_PORT)` cho real HTTP serialization/commit/network boundary.
- Testcontainers integration cho production DB/broker dialect.
- E2E tests với external service sandbox.

Từ đó không dùng một annotation làm tất cả. Test dạng nào cần rollback sạch, loại nào cần verify committed state và cleanup phải được nói rõ.

### 22.2. Contract của một HTTP test

Mỗi test nên ghi:
- Given: persisted fixtures đã commit hoặc request độc lập không cần fixtures.
- When: HTTP operation với unique ID.
- Then: status/body và **durable state**.
- Cleanup: theo ID/owner namespace và committed transaction.
- Isolation: không sửa rows test khác.
- Completion: không có background work pending trước teardown.
- Failure: cleanup ở finally/callback ngay cả nếu assertion fail.

Đây là cấu trúc dễ review và ít flaky.

### 22.3. Nguyên tắc owner dữ liệu

Test chỉ xóa artifacts do nó sở hữu. Nếu có parent/child:
- Sinh `runId`/`testId`.
- Ghi owner tag vào tất cả rows cần cleanup hoặc liên kết qua FK.
- Xóa child before parent hoặc cascade đúng contract.
- Verifications sau cleanup với owner tag.
- Tài nguyên ngoài DB (Redis/Kafka/S3) có namespace tương ứng.

Không xóa global seed/reference data; hãy provision riêng cho test container/schema.

### 22.4. Tăng tốc mà không làm sai

- Reuse Spring context khi config giống nhau.
- Reuse container đúng lifetime nếu CI budget cần.
- Dùng unique IDs thay vì rebuild toàn context mỗi test.
- Cleanup targeted thay vì TRUNCATE toàn DB.
- Tránh `@DirtiesContext` đại trà.
- Test slice/MockMvc cho contract không cần network, real HTTP tests cho boundary.
- Dùng context cache DEBUG khi đo hiệu năng.
- Không dùng timeouts dài hay sleeps để che startup readiness/async races.

### 22.5. CI và parallel execution

Nếu chạy nhiều workers/forks:
- Mỗi JVM có Spring TestContext cache riêng.
- H2 `mem:...` thuộc JVM; mỗi process có DB memory riêng, trừ khi cấu hình external H2 server khác.
- PostgreSQL Testcontainers có thể tạo một hoặc nhiều containers, tùy ownership.
- Unique IDs ngăn trùng key giữa tests nhưng không loại nguy cơ global cleanup SQL.
- Nếu test cần COUNT(*) toàn database/schema, cấp **exclusive schema/DB**.
- JUnit `@ResourceLock` chỉ phối hợp resource keys trong cùng test engine, không thay distributed lock.
- Test classes cần không phụ thuộc thứ tự.
- Verify executed count và cleanup trong từng worker.

## 23. Bài tập mở rộng

1. Chạy ba lớp trong lab và ghi sáu test methods được thực thi (nếu môi trường phù hợp).
2. Thêm `@Transactional` vào `RealHttpCleanupIntegrationTest` nhưng giữ `@AfterEach`; dự đoán vì sao DELETE có thể rollback; **khôi phục code đúng ngay sau thí nghiệm**.
3. Trong `RealHttpRollbackBoundaryTest`, ghi log `TransactionSynchronizationManager.isActualTransactionActive()` từ test thread và server service.
4. Assert clientMarkerId=0 và httpOrderId=1 tại `@AfterTransaction`; giải thích vì sao không assert duy nhất trong test body.
5. Bỏ `@BeforeTransaction` và seed DB trong `@BeforeEach`; thử server HTTP truy vấn fixture chưa commit, giải thích invisibility.
6. Dùng `@SqlConfig(transactionMode=ISOLATED)` để commit fixture trước HTTP, bảo đảm SQL script chỉ thao tác owned data.
7. Dùng `@Sql(... AFTER_TEST_METHOD)` với script scoped theo test schema riêng; kiểm cleanup committed.
8. Thêm `@Rollback(false)` vào một test, đo post-test state rồi cleanup; giải thích vì sao không dùng nó làm default.
9. Thêm `TestTransaction.flagForRollback(); TestTransaction.end()` để query DB ngoài TX; tránh gọi sau khi TX đã kết thúc.
10. Thêm service method `@Transactional(propagation=REQUIRES_NEW)` và gọi bằng synchronous MockMvc; kiểm row có thể persist sau test rollback.
11. Thêm controller `@Async` hoặc async servlet handler; phân biệt thread/transaction boundary với MockMvc đồng bộ.
12. Thêm một endpoint trả 202 và dùng bounded completion signal trước cleanup.
13. Tạo một test `@TransactionalEventListener(AFTER_COMMIT)` và so event side effects của real HTTP vs MockMvc rollback.
14. Thêm checked exception vào transactional service, kiểm default rollback rule và `rollbackFor`.
15. Thêm Hibernate/JPA repository, dùng flush/clear và fresh transaction để tránh first-level cache false positive.
16. Tạo H2 row with foreign key child; viết targeted cleanup child-first.
17. Dùng ownerTag unique per test, query countByOwner sau cleanup.
18. Chạy class A rồi B với randomized order, xác nhận không data leak hoặc duplicate.
19. Bật JUnit parallel classes, kiểm rằng global SQL DELETE là nguy hiểm; chỉ dùng on isolated schema.
20. Đổi H2 thành PostgreSQL Testcontainers, dùng `@ServiceConnection` typed container.
21. Kiểm `JdbcTemplate` transaction boundary khi POST và test dùng hai Hikari connections.
22. Gây duplicate key trong POST, verify 409 và original row unchanged.
23. Gây validation 400, verify zero side effect ở DB và outbox giả lập.
24. Tạo fake gateway trả 500 **sau** DB commit trong service không transactional; chứng minh HTTP status không quyết định rollback.
25. Cố tình catch RuntimeException trong transactional service, verify vì sao SQL có thể commit; sửa.
26. Thêm `@DirtiesContext` vào HTTP test, chứng minh external persisted row không tự xóa.
27. Kiểm data cleanup khi test assertion throw; đảm bảo finally/callback vẫn chạy trong normal lifecycle.
28. Simulate client timeout sau server commit, truy vấn bằng operation ID và cleanup best-effort.
29. Thêm Redis key với unique test prefix; chứng minh JDBC rollback không undo Redis writes.
30. Thêm message consumer outbox, chờ after-commit processing trước cleanup.
31. Dùng Maven Surefire XML kiểm executed/skipped/errors counts, không chỉ BUILD SUCCESS.
32. Viết một checklist của module mình: transactions/owners/cleanup/timeout/parallelism/external state.
33. Đọc Spring Boot 3.5 docs về separate HTTP client/server threads và viết lại timeline theo code thật.
34. Đọc Spring Framework tx docs để phân biệt `@BeforeEach` trong TX với `@BeforeTransaction` ngoài TX.
35. Thiết kế CI schema-per-run với post-job cleanup khi test process bị killed.

## 24. Checklist kiểm thử và review

- [ ] Xác định test dùng MockMvc đồng bộ hay real HTTP?
- [ ] Với real HTTP, đã hiểu client và server khác thread/transaction?
- [ ] Không giả định `@Transactional` test rollback server writes?
- [ ] Có kiểm database state sau response, không chỉ HTTP status?
- [ ] Có phân biệt `REQUIRED` với `REQUIRES_NEW`?
- [ ] Có biết `@AfterEach` trong transactional test cũng thuộc test TX?
- [ ] Real HTTP cleanup không nằm trong transaction sắp rollback?
- [ ] Với test transactional, dùng `@AfterTransaction` hoặc independent committed cleanup?
- [ ] Có định nghĩa server-side @Transactional boundary rõ?
- [ ] Failure path throw exception trước commit đã được test?
- [ ] Không chỉ dựa HTTP 500 để tuyên bố rollback?
- [ ] Có 400/409 success/negative cases không làm bẩn DB?
- [ ] Mỗi method/HTTP operation có unique ID?
- [ ] Cleanup chỉ xóa rows/artifacts do test sở hữu?
- [ ] Không DELETE/TRUNCATE toàn bảng trong shared parallel DB?
- [ ] `@Sql AFTER_TEST_METHOD` được xét cùng transactionMode?
- [ ] `@Sql ISOLATED` được dùng khi script cần commit?
- [ ] Fixtures server cần đọc đã được commit trước HTTP?
- [ ] Không nhầm flush với commit trong JPA?
- [ ] Không dùng cached EntityManager để tự chứng minh durable DB state?
- [ ] Có query final state sau test-managed rollback?
- [ ] Có cleanup trong finally/callback khi assertions fail?
- [ ] Cleanup statement đã commit và được verify bằng query mới?
- [ ] Async worker/consumer đã hoàn thành trước cleanup?
- [ ] Không dùng Thread.sleep làm commit/completion signal?
- [ ] Testcontainers backend có đúng ownership/context lifetime?
- [ ] Database dialect production quan trọng đã kiểm bằng real DB?
- [ ] `@DirtiesContext` không bị nhầm thành database cleanup?
- [ ] Test còn đúng khi run độc lập, lặp và random order?
- [ ] JUnit forks/parallel workers không share fixed IDs/cleanup?
- [ ] Không để secrets/customer data trong test fixtures/logs?
- [ ] Chạy Maven đã đối chiếu Surefire executed count và actual failures?
- [ ] Kết quả ghi “dự kiến” nếu chưa có run chứng minh?
- [ ] Có regression test bảo vệ ranh giới HTTP commit/rollback?

## 25. Những điều không được kết luận quá mức

- **“@Transactional test luôn rollback tất cả”: sai.** Chỉ bảo đảm theo test-managed TX và resources gắn với nó, không tự qua HTTP.
- **“MockMvc luôn ở cùng transaction”: quá rộng.** Chỉ những synchronous/compatible paths mới thường chia sẻ test ThreadLocal transaction.
- **“HTTP 500 nghĩa là DB rollback”: sai.** Server có thể commit trước khi lỗi xảy ra hoặc swallow exception.
- **“SQL DELETE đã chạy nghĩa là cleanup committed”: sai.** DELETE có thể rollback.
- **“@AfterEach nằm ngoài test transaction”: sai khi test dùng @Transactional** (Spring TestContext lifecycle thông thường).
- **“@DirtiesContext reset database”: sai với external/shared DB.**
- **“@Sql AFTER_TEST_METHOD bảo đảm committed cleanup”: cần xem transactionMode/data ownership.**
- **“EntityManager.flush() đã commit”: sai.** Flush gửi SQL nhưng transaction có thể rollback.
- **“DB COUNT(*) phải bằng 0 sau mỗi test”: chỉ hợp lý khi test sở hữu toàn DB/schema.**
- **“H2 PASS chứng minh PostgreSQL production locking đúng”: sai.**
- **“Một POST trả 201 luôn đồng nghĩa tất cả async side effects hoàn tất”: sai.**
- **“Nếu API timeout thì server chắc chắn không commit”: sai.**
- **“Tăng timeout hoặc chạy @DirtiesContext sửa được data leak”: không có cơ sở.**
- **“Test/CI có exit code 0 nghĩa là đã có cleanup”: cần post-cleanup assertion và test counts.**
- **“TestTransaction.end() ở client rollback được server TX”: sai.**
- **“Tất cả DB/Redis/Kafka/S3 state cùng một transaction”: sai trong kiến trúc phổ biến.**

## 26. Kết luận

Bài học thực hành này chứng minh một ranh giới có tính quyết định: **rollback của JUnit test thread không rollback transaction do HTTP server thread đã commit**. Với `@SpringBootTest(RANDOM_PORT)`, hãy xem dữ liệu sau POST như một side effect thật cần **explicit, committed, targeted cleanup**; với test-managed transaction, dùng `@AfterTransaction` để quan sát state sau rollback và tránh đặt DELETE trong `@AfterEach` của cùng transaction. Đồng thời, cần phân biệt với synchronous MockMvc, nơi service `REQUIRED` thường tham gia test transaction và dữ liệu bị rollback cùng test.

Giá trị của phép thử nằm ở evidence trực tiếp:
- Marker do JUnit transaction insert → **biến mất sau rollback**.
- Order do HTTP server transaction insert → **còn sau rollback của test**.
- Cleanup chạy ngoài test transaction → **xóa chính xác order và verify lại DB**.
- Một server-side exception trước commit → **không có partial row**.

Khi chuyển từ lab H2 sang ứng dụng thực, giữ nguyên phương pháp nhưng dùng production-like database/Testcontainers cho concurrency/isolation, chờ async completion, cleanup theo operation ID/tenant/schema và bảo vệ mọi external side effect khỏi nhiễm chéo tests.

## 27. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — Testing Spring Boot Applications, `RANDOM_PORT`, `TestRestTemplate`, client/server separate threads and transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — Test-managed Transaction Management, `@BeforeTransaction`, `@AfterTransaction`, `TestTransaction`, preemptive timeouts: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Executing SQL scripts, `@Sql`/`@SqlConfig` transaction modes, AFTER_TEST_METHOD: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Framework 6.2 — TestContext caching and context lifecycle: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — @DirtiesContext and cache invalidation: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — Declarative Transaction Management and rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2 — Transaction Propagation and REQUIRES_NEW: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.5 — JDBC/SQL databases and initialization: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Testcontainers / ServiceConnection: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Spring MVC/MockMvc Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.with-mock-environment
- Spring Framework 6.2 — Test-managed Transactions and ORM false positives/flush: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Maven Surefire — Test selection and XML reports: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
