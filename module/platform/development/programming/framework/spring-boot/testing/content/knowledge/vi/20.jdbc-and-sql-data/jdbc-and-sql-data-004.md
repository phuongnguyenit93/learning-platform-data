# `@DataR2dbcTest` và kiểm thử truy cập dữ liệu Reactive trong Spring Boot

Trong ứng dụng Spring Boot dùng **Spring Data R2DBC**, repository không trả đối tượng hoặc `List<T>` ngay khi gọi method. Thay vào đó, các thao tác thường trả **`Mono<T>`** hoặc **`Flux<T>`** và chỉ thực sự truy cập cơ sở dữ liệu khi có **subscription**. Vì thế, một bài test chỉ gọi `repository.save(book)` rồi kết thúc **chưa chứng minh có INSERT**; một bài test dùng `StepVerifier.expectNextCount(2)` cũng chưa chắc đã kiểm đúng dữ liệu hoặc thứ tự kết quả.

**`@DataR2dbcTest`** là test slice của Spring Boot dành cho Spring Data R2DBC: chỉ nạp hạ tầng truy cập dữ liệu reactive cần thiết, repository và `R2dbcEntityTemplate` thay vì khởi động toàn bộ ứng dụng. Theo tài liệu **Spring Boot 3.5**, slice có thể dùng embedded database trong bộ nhớ và **mặc định không bọc từng test bằng transaction rollback**. Đây là khác biệt trọng yếu so với `@DataJpaTest` hoặc nhiều `@JdbcTest`: dữ liệu đã ghi có thể còn lại qua các test nếu không được dọn đúng cách.

Bài này giải thích: ranh giới `@DataR2dbcTest`, cách kết nối R2DBC/khởi tạo schema, kiểm `Mono`/`Flux` bằng `StepVerifier`, test CRUD/query/unique constraints, cô lập fixture, **reactive transaction** và `TransactionalOperator`, khi nào chọn H2 hoặc PostgreSQL Testcontainers, cùng ví dụ **Java 17 + Spring Boot 3.5 + H2 R2DBC** có thể chạy bằng Maven.

## 1. Bản chất R2DBC và phạm vi cần chứng minh

**R2DBC** (*Reactive Relational Database Connectivity*) là SPI/API cho các database drivers có khả năng làm việc theo mô hình Reactive Streams. Nó khác **JDBC** thường dùng kiểu chặn luồng với `Connection`/`PreparedStatement` và khác JPA/Hibernate ở cơ chế persistence context.

```text
Spring WebFlux / reactive service
            |
            +--> ReactiveCrudRepository<Book, Long>
            |            |
            |            v
            |      Spring Data R2DBC mapping
            |
            +--> R2dbcEntityTemplate
            |            |
            |            v
            +--> DatabaseClient
                         |
                         v
                R2DBC ConnectionFactory
                         |
                         v
                R2DBC driver / database
                         |
                         v
                   Publisher
                  Mono / Flux
                         |
                         v
            subscribe -> onNext/onError/onComplete
```

- **`ConnectionFactory`** (R2DBC SPI) là cơ chế lấy connection reactive, vai trò tương tự `DataSource` của JDBC nhưng API khác.
- **`DatabaseClient`** (Spring Framework R2DBC) chạy SQL có bind parameters và trả `Mono`/`Flux`.
- **`R2dbcEntityTemplate`** là API cao hơn cho CRUD/query theo entity metadata.
- **`ReactiveCrudRepository`** là abstraction Spring Data sinh implementation, hỗ trợ `save`, `findById`, `deleteAll`, `count` và query methods.
- **`StepVerifier`** của `reactor-test` subscribe publisher, kiểm `onNext`, `onError`, `onComplete` và thứ tự.

### R2DBC không phải JPA chạy trong Mono

R2DBC entity thường dùng annotations của **Spring Data Relational**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.relational.core.mapping.Column;

@Table("BOOKS")
class Book {
    @Id
    @Column("ID")
    Long id;
}
```

Đây là **snippet mapping**, không phải file hoàn chỉnh. Nó không dùng `jakarta.persistence.Entity`, `@ManyToOne`, `EntityManager` hay Hibernate dirty checking. Với R2DBC, `save` là thao tác repository; đừng cho rằng mọi lần thay field Java sẽ tự được phát hiện như JPA managed entity tại flush.

| Câu hỏi | JDBC/JPA truyền thống | R2DBC reactive |
|---|---|---|
| API thường trả | Entity/collection hoặc `Optional` | `Mono<T>` hoặc `Flux<T>` |
| Công cụ kết nối | `DataSource` | `ConnectionFactory` |
| Query mức thấp | `JdbcTemplate`/`EntityManager` | `DatabaseClient` |
| Mapping repository | `JpaRepository`, `CrudRepository` | `ReactiveCrudRepository` |
| Khi nào database thao tác? | Khi method blocking thực thi hoặc JPA flush/commit | Khi Publisher được **subscribe** và demand/transaction vận hành |
| Transaction context | Thường dựa vào thread-bound transaction của `PlatformTransactionManager` | Qua **Reactor Context** với `ReactiveTransactionManager` |
| Test hỗ trợ | `@DataJpaTest`, `@DataJdbcTest`, `@JdbcTest` | **`@DataR2dbcTest`** và `StepVerifier` |

Nói **non-blocking** không có nghĩa test không có I/O hoặc không cần một database thật. Nó chỉ mô tả mô hình API và driver; H2 in-memory có đặc tính triển khai riêng, không tự chứng minh độ trễ hoặc tính tương đương với PostgreSQL production.

## 2. `@DataR2dbcTest` nạp những bean nào?

Trong **Spring Boot 3.5**, annotation:

```java
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;

@DataR2dbcTest
class BookRepositorySliceTest {
    // @Autowired repository, R2dbcEntityTemplate, DatabaseClient...
}
```

Đây là cấu hình test dạng khung, chưa có `@Test`.

`@DataR2dbcTest` thực hiện **test slicing**: bật các auto-configurations cần cho `R2dbcAutoConfiguration`, `R2dbcDataAutoConfiguration`, R2DBC repositories, transaction manager và SQL initialization tương ứng với classpath. Khi embedded R2DBC driver phù hợp có sẵn, slice có thể tạo connection tới **in-memory database**, đồng thời cung cấp `R2dbcEntityTemplate` và các bean repository Spring Data R2DBC. Có thể inject `DatabaseClient` hoặc `ConnectionFactory` để kiểm SQL trực tiếp.

Các `@Component` và `@ConfigurationProperties` thông thường **không được tự scan đầy đủ** như full application context; có thể dùng `@EnableConfigurationProperties` hoặc `@Import` có chủ đích nếu test cần bean cấu hình nhỏ. Một `@Service` bình thường có thể **không xuất hiện**; đây là scope đúng, không nhất thiết là lỗi của Spring.

**Mặc định Data R2DBC tests không transactional.** Điều này đã được Spring Boot ghi rõ. Không áp đặt kinh nghiệm từ `@DataJpaTest` rằng “mỗi test tự rollback”; với R2DBC, các thay đổi sau khi publisher hoàn tất có thể **đã được commit qua autocommit** và hiển thị ở test tiếp theo.

### Ma trận: bằng chứng nào được thu trong slice?

| Cần chứng minh | `@DataR2dbcTest` kiểm được? | Điều kiện / giới hạn |
|---|---|---|
| Repository bean được tạo và inject | **Có** | Repository nằm trong scan và classpath có R2DBC |
| SQL qua `ReactiveCrudRepository` thực sự lưu/đọc | **Có** | Database/schema tồn tại, Publisher được subscribe |
| Mapping table/column, generated ID, converter | **Có** | Dùng đúng DDL/dialect/test fixtures |
| Query method `findByIsbn` trả đúng entity | **Có** | Assert nội dung `onNext`, không chỉ `expectNextCount` |
| Unique constraint, FK, SQL lỗi | **Có** | Constraint thật tồn tại trong test DB; assert `onError` |
| `R2dbcEntityTemplate` và `DatabaseClient` | **Có** | Bean/config phù hợp; SQL chạy trên test DB |
| Reactive transaction commit/rollback | **Có thể** | Cần đặt **transaction boundary thực** bằng `TransactionalOperator` hoặc reactive `@Transactional` đúng cách |
| Full service/controller/web route/security | **Không mặc định** | Cần unit/service integration, `@WebFluxTest` hoặc `@SpringBootTest` |
| PostgreSQL-specific SQL/locking/collations | **Không chỉ với H2** | Dùng PostgreSQL Testcontainers/DB test đúng engine |
| Socket HTTP/WebFlux và JSON response | **Không** | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |

**Khi nào dùng unit test thay slice?** Nếu logic chỉ tính giá hoặc chọn một `Publisher` giả mà không cần schema/query, JUnit/Reactor Test thuần với fake repository có thể nhanh hơn. Nếu mục tiêu là JDBC `JdbcTemplate`, chọn `@JdbcTest`; nếu là ORM/JPA, chọn `@DataJpaTest`. Đừng dùng `@DataR2dbcTest` chỉ vì module có chữ “reactive” trong tên trong khi implementation là JPA blocking.

## 3. Cơ chế Publisher: không subscribe thì không có I/O

Hai dòng này **không tương đương**:

```java
Mono<Book> pending = repository.save(new Book("ISBN-A", "A", 5));
// Chỉ tạo Publisher. Không có bằng chứng rằng INSERT đã chạy.

StepVerifier.create(pending)
        .assertNext(saved -> assertNotNull(saved.getId()))
        .verifyComplete();
// StepVerifier subscribe và kiểm INSERT thực sự cho kết quả.
```

Đây là snippet bên trong test đã inject `repository`, có `Book` và static import JUnit; file đầy đủ ở phần 6.

Publisher của Reactor có tính **cold/lazy** theo cách tạo ra nó: khi subscribe, pipeline mới thực hiện SQL. Không được nhầm “Java code đã gọi `save`” với “database đã thấy row”. Thường dùng `StepVerifier` để chủ động điều khiển và xác minh tín hiệu:

```java
StepVerifier.create(repository.findByIsbn("978-1"))
        .assertNext(book -> {
            assertEquals("978-1", book.getIsbn());
            assertEquals(7, book.getStock());
        })
        .verifyComplete();
```

Nếu row không tồn tại, `Mono<Book>` thường **complete rỗng**; nó **không phát null** và không ném lỗi chỉ vì không có hàng, trừ khi chính repository method dùng operator ép nonempty. Test không có dữ liệu nên dùng `StepVerifier.create(repository.findByIsbn("UNKNOWN")).verifyComplete()` — trường hợp này không kỳ vọng `onNext`.

### Assertion và mức độ bằng chứng

| API StepVerifier | Bằng chứng |
|---|---|
| `expectNext(book)` | `equals` trên object ở vị trí tiếp theo; phải hiểu equality của entity |
| `assertNext(book -> ...)` | Có thể kiểm `id`, `isbn`, `stock` cụ thể |
| `expectNextMatches(predicate)` | Chỉ kiểm predicate; tránh predicate quá lỏng |
| `expectNextCount(3)` | Có đúng 3 `onNext`, **không** kiểm giá trị hay thứ tự |
| `expectNextSequence(...)` | Thứ tự và equality theo danh sách mong đợi |
| `verifyComplete()` | Chạy test, kiểm không còn event và kết thúc thành công |
| `expectErrorSatisfies(...).verify()` | Chạy query/save và kiểm loại/cause lỗi |
| `thenCancel().verify(...)` | Kiểm Publisher chưa kết thúc hoặc muốn hủy sớm |
| `verify(Duration.ofSeconds(...))` | Có timeout rõ cho pipeline có nguy cơ không kết thúc |

**Không chỉ** tạo `StepVerifier.create(...)` và bỏ quên `verify`: thiếu lệnh verify có nghĩa chưa subscribe và chưa kiểm gì. `Mono.block()` trong JUnit thread đôi khi dùng được để dựng fixture nhưng dễ che ranh giới reactive và không dùng được an toàn trên event-loop WebFlux; trong bài này ưu tiên giữ toàn bộ thao tác trong pipeline và dùng StepVerifier.

## 4. Database khởi tạo schema trong test bằng cách nào?

**R2DBC không phải JPA/Hibernate auto-DDL.** Annotation `@Table("BOOKS")` giúp mapping object tới table, **không tự tạo table**. Test phải có schema theo một trong những cách có kiểm soát:

- **Spring Boot SQL initialization:** đặt `schema.sql` trong classpath và bật `spring.sql.init.mode=always` khi cần, thường đủ cho H2 trong bài học.
- **Migration thực:** Flyway/Liquibase dùng SQL/JDBC migration cho database production-like; trong ứng dụng chỉ có R2DBC, có thể cần dependency JDBC/DataSource riêng để migration tool kết nối. Đừng mặc định tool migration tự chuyển sang R2DBC.
- **Reactive DatabaseClient setup:** có thể execute DDL reactive trước mỗi test hoặc trước suite; với DDL dùng chung phải cẩn trọng parallel tests.
- **Testcontainers:** dùng PostgreSQL/MariaDB/MySQL phù hợp driver và migrations để kiểm dialect, constraint, schema thật.

**H2 identifier quoting:** Spring Data R2DBC có thể quote các tên từ `@Table`/`@Column`; H2 mặc định chuyển **tên không quote thành chữ hoa**. Nếu entity có `@Table("books")` nhưng DDL tạo `CREATE TABLE books` không quote, H2 lưu `BOOKS`, trong khi SQL từ mapper có thể dùng tên quoted `"books"` → **table not found**. Ví dụ runnable bên dưới dùng **tên UPPERCASE nhất quán** ở annotation và SQL: `BOOKS`, `ID`, `ISBN`, `TITLE`, `STOCK`.

### H2 in-memory connection lifecycle

R2DBC mở/đóng connection qua `ConnectionFactory`; H2 in-memory có thể **xóa database khi connection cuối cùng đóng** nếu không cấu hình giữ database sống. Với URL của R2DBC H2:

```properties
spring.r2dbc.url=r2dbc:h2:mem:///booksdb?options=DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

`DB_CLOSE_DELAY=-1` giữ database in-memory trong vòng đời JVM để các connection ngắn hạn vẫn thấy schema. Đây là cấu hình **dành cho test**, không phải production. Ví dụ dùng annotation `@DataR2dbcTest(properties={...})` tương đương để tự chứa code. Nếu suite tạo nhiều context trên cùng JVM và cùng H2 database name, cần tránh va chạm schema; dùng database name riêng hoặc test isolation phù hợp.

## 5. Test fixture phải dọn dữ liệu vì Data R2DBC không tự rollback

Dùng `@BeforeEach` dọn table thông qua reactive repository, **và phải subscribe**:

```java
@BeforeEach
void clearBooks() {
    StepVerifier.create(repository.deleteAll())
            .verifyComplete();
}
```

Với H2 test database và **một test class chạy tuần tự**, đây là cách đơn giản để tránh một test để lại dữ liệu rồi làm test khác fail. Nếu chỉ gọi `repository.deleteAll()` mà không subscribe thì cleanup **không thực thi**.

**Không tự dùng `@Transactional` trên JUnit test method rồi mong được rollback** như cách thường làm trong `@DataJpaTest`:

- Reactive transaction thường dựa trên **Reactor Context**, không phải ThreadLocal.
- JUnit `void @Test` không tự mang Reactor Context vào mỗi `StepVerifier`.
- Test `@DataR2dbcTest` không tự được bọc trong transaction test-managed theo mặc định.
- Nếu cần kiểm rollback, hãy dựng **một reactive pipeline** và bọc nó bằng `TransactionalOperator`, hoặc gọi một **bean proxy** có reactive `@Transactional` trả Publisher.
- Rollback không đảo được tác dụng ngoài DB như đã gửi message tới broker hoặc gọi API khác.

Tránh chia sẻ cùng một H2 in-memory database khi nhiều test class chạy song song mà đều `deleteAll`: một class có thể dọn fixture của class khác. Với CI parallel, dùng database/schema riêng cho mỗi class/job hoặc test containers cách ly, rồi cleanup bằng key/transaction có chủ đích.

## 6. Ví dụ đầy đủ: Java 17, Spring Boot 3.5, H2 R2DBC và 9 test

Bài thực hành có một bảng **BOOKS**: `ID` được database sinh; `ISBN` unique; `TITLE` và `STOCK` bắt buộc. API reactive repository và template chạy trên H2 qua R2DBC. Không có Spring MVC/WebFlux controller hoặc web server, vì mục tiêu là **truy cập dữ liệu Reactive**.

Ba lớp hạ tầng được kiểm:

1. **Repository abstraction** `BookRepository extends ReactiveCrudRepository<Book, Long>`.
2. **R2dbcEntityTemplate** với `Criteria`/ `Query` trên entity.
3. **DatabaseClient** với SQL update/bind parameters; cùng `ReactiveTransactionManager` để rollback.

### 6.1. Cây thư mục

```text
r2dbc-book-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/r2dbc/
    │   ├── R2dbcBooksApplication.java
    │   ├── Book.java
    │   └── BookRepository.java
    └── test/
        ├── java/com/example/r2dbc/
        │   └── BookRepositoryR2dbcTest.java
        └── resources/
            └── schema.sql
```

### 6.2. `pom.xml` hoàn chỉnh

File **`pom.xml`** dùng **Spring Boot 3.5.0**, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>r2dbc-book-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

`spring-boot-starter-data-r2dbc` có Spring Data R2DBC, Reactor và transaction infrastructure. `r2dbc-h2` là **reactive H2 driver**, khác JDBC `com.h2database:h2` dùng qua `DataSource`; chỉ thêm `h2` JDBC mà thiếu `r2dbc-h2` không tạo R2DBC connection factory thích hợp. `reactor-test` cung cấp StepVerifier. Parent quản lý version tương thích của Spring, Reactor và driver; tránh pin riêng phiên bản ngẫu nhiên.

### 6.3. Lớp cấu hình Spring Boot gốc

File **`src/main/java/com/example/r2dbc/R2dbcBooksApplication.java`**:

```java
package com.example.r2dbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class R2dbcBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(R2dbcBooksApplication.class, args);
    }
}
```

`@DataR2dbcTest` chạy trong package con/cùng package với `R2dbcBooksApplication` nên có thể phát hiện cấu hình gốc, nhưng vẫn chỉ nạp R2DBC slice. App thực không khai báo web starter, vì vậy không khởi động HTTP server.

### 6.4. SQL schema cho H2 test

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE BOOKS (
    ID BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ISBN VARCHAR(40) NOT NULL UNIQUE,
    TITLE VARCHAR(160) NOT NULL,
    STOCK INTEGER NOT NULL
);
```

Bảng `BOOKS` có unique trên ISBN và NOT NULL cho các cột; các test sẽ kiểm INSERT/UPDATE/SELECT và lỗi duplicate key. Đây là DDL **cho H2**, không phải migration PostgreSQL. `schema.sql` chỉ tạo bảng; không thêm `data.sql`, nên `@BeforeEach` kiểm soát dữ liệu đầu vào rõ ràng.

R2DBC không có Hibernate auto-schema từ entity; `spring.sql.init.mode=always` cùng `schema.sql` giúp khởi tạo bảng khi context test bắt đầu. Trong ứng dụng thật dùng Flyway/Liquibase, phải đảm bảo migration chạy bằng một kết nối/driver mà công cụ migrations hỗ trợ, thường JDBC, và test schema đúng production.

### 6.5. Entity Book với mapping uppercase nhất quán

File **`src/main/java/com/example/r2dbc/Book.java`**:

```java
package com.example.r2dbc;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("BOOKS")
public class Book {
    @Id
    @Column("ID")
    private Long id;

    @Column("ISBN")
    private String isbn;

    @Column("TITLE")
    private String title;

    @Column("STOCK")
    private int stock;

    protected Book() {
        // Spring Data mapping.
    }

    public Book(String isbn, String title, int stock) {
        this.isbn = isbn;
        this.title = title;
        this.stock = stock;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
```

**Không dùng `jakarta.persistence.Entity`**, `@GeneratedValue` hay `EntityManager`. Với Spring Data R2DBC, `@Id` null báo entity mới; khi `save` tạo INSERT và database sinh ID, Spring Data đọc generated key rồi trả entity với ID. Entity là mutable Java object; khi cập nhật, phải **gọi `save` lại** hoặc một explicit update query, vì không có Hibernate dirty-checking/flush giống JPA.

Dùng `@Table("BOOKS")` và `@Column("ID")` dạng UPPERCASE phù hợp H2 DDL đã khai báo. Khi chuyển sang PostgreSQL, naming và quoting cần được rà lại theo dialect/migration.

### 6.6. Reactive repository và query method

File **`src/main/java/com/example/r2dbc/BookRepository.java`**:

```java
package com.example.r2dbc;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface BookRepository extends ReactiveCrudRepository<Book, Long> {
    Mono<Book> findByIsbn(String isbn);

    Flux<Book> findAllByOrderByIsbnAsc();
}
```

`findByIsbn` là **derived query** dựa trên property Java, Spring Data R2DBC tạo SQL phù hợp với mapping. `findAllByOrderByIsbnAsc` yêu cầu **ORDER BY ISBN** rõ ràng. Không dựa vào thứ tự `findAll()` mặc định: SQL không hứa thứ tự ổn định nếu không có `ORDER BY`.

`ReactiveCrudRepository` trả publisher; chỉ khi có subscription thì JDBC-like I/O sẽ diễn ra qua R2DBC driver. Repository có thể trả `Mono.empty()` cho query không có row, **không trả null**.

### 6.7. JUnit test class: repository, DatabaseClient, template và transaction

File **`src/test/java/com/example/r2dbc/BookRepositoryR2dbcTest.java`**:

```java
package com.example.r2dbc;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataR2dbcTest(properties = {
        "spring.r2dbc.url=r2dbc:h2:mem:///booksdb?options=DB_CLOSE_DELAY=-1",
        "spring.sql.init.mode=always"
})
class BookRepositoryR2dbcTest {
    @Autowired
    private BookRepository repository;

    @Autowired
    private R2dbcEntityTemplate template;

    @Autowired
    private DatabaseClient databaseClient;

    @Autowired
    private ReactiveTransactionManager transactionManager;

    @BeforeEach
    void clearDataForEachTest() {
        StepVerifier.create(repository.deleteAll())
                .verifyComplete();
    }

    @Test
    void savedBookCanBeLoadedByDerivedQuery() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-001", "Spring R2DBC", 7))
                .flatMap(saved -> {
                    assertNotNull(saved.getId());
                    return repository.findByIsbn("ISBN-001");
                });

        StepVerifier.create(flow)
                .assertNext(book -> {
                    assertEquals("ISBN-001", book.getIsbn());
                    assertEquals("Spring R2DBC", book.getTitle());
                    assertEquals(7, book.getStock());
                })
                .verifyComplete();
    }

    @Test
    void absentRecordIsMonoEmptyNotNull() {
        StepVerifier.create(repository.findByIsbn("ABSENT"))
                .verifyComplete();
    }

    @Test
    void derivedQueryReturnsRowsInExplicitIsbnOrder() {
        Mono<Void> seed = repository
                .save(new Book("ISBN-B", "Second", 2))
                .then(repository.save(new Book("ISBN-A", "First", 1)))
                .then();

        StepVerifier.create(seed.thenMany(
                    repository.findAllByOrderByIsbnAsc()))
                .assertNext(book ->
                        assertEquals("ISBN-A", book.getIsbn()))
                .assertNext(book ->
                        assertEquals("ISBN-B", book.getIsbn()))
                .verifyComplete();
    }

    @Test
    void changingEntityFieldNeedsAnotherSave() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-UP", "Updated", 3))
                .flatMap(saved -> {
                    saved.setStock(11);
                    return repository.save(saved);
                })
                .flatMap(saved ->
                        repository.findByIsbn("ISBN-UP"));

        StepVerifier.create(flow)
                .assertNext(book ->
                        assertEquals(11, book.getStock()))
                .verifyComplete();
    }

    @Test
    void duplicateIsbnEmitsIntegrityViolation() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-DUP", "Original", 1))
                .flatMap(saved ->
                        repository.save(
                                new Book("ISBN-DUP", "Duplicate", 2)));

        StepVerifier.create(flow)
                .expectErrorSatisfies(error ->
                        assertThat(error)
                                .isInstanceOf(
                                        DataIntegrityViolationException.class))
                .verify();
    }

    @Test
    void databaseClientUpdateIsVisibleThroughRepository() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-SQL", "Direct update", 4))
                .then(databaseClient.sql(
                            "UPDATE BOOKS SET STOCK = :stock WHERE ISBN = :isbn")
                        .bind("stock", 17)
                        .bind("isbn", "ISBN-SQL")
                        .fetch()
                        .rowsUpdated())
                .flatMap(rows -> {
                    assertEquals(1L, rows);
                    return repository.findByIsbn("ISBN-SQL");
                });

        StepVerifier.create(flow)
                .assertNext(book ->
                        assertEquals(17, book.getStock()))
                .verifyComplete();
    }

    @Test
    void r2dbcEntityTemplateExecutesCriteriaQuery() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-TEMPLATE", "Template", 5))
                .then(template.select(Book.class)
                        .matching(Query.query(
                                Criteria.where("isbn").is("ISBN-TEMPLATE")))
                        .one());

        StepVerifier.create(flow)
                .assertNext(book -> {
                    assertEquals("ISBN-TEMPLATE", book.getIsbn());
                    assertEquals(5, book.getStock());
                })
                .verifyComplete();
    }

    @Test
    void reactiveTransactionRollsBackWhenPublisherErrors() {
        TransactionalOperator tx =
                TransactionalOperator.create(transactionManager);

        Mono<Void> failingFlow = tx.transactional(
                repository.save(new Book(
                            "ISBN-ROLLBACK", "Never committed", 9))
                        .then(Mono.<Void>error(
                                new IllegalStateException("rollback-test"))));

        StepVerifier.create(failingFlow)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "rollback-test".equals(error.getMessage()))
                .verify(Duration.ofSeconds(5));

        StepVerifier.create(
                    repository.findByIsbn("ISBN-ROLLBACK"))
                .verifyComplete();
    }

    @Test
    void creatingMonoDoesNotExecuteInsertUntilSubscribed() {
        Mono<Book> pending =
                repository.save(new Book("ISBN-LAZY", "Lazy", 6));

        StepVerifier.create(repository.count())
                .expectNext(0L)
                .verifyComplete();

        StepVerifier.create(pending)
                .assertNext(saved -> assertNotNull(saved.getId()))
                .verifyComplete();

        StepVerifier.create(repository.count())
                .expectNext(1L)
                .verifyComplete();
    }
}
```

**Giải thích test:**

- **Save + read**: INSERT thực sự chạy sau subscription, generated ID được trả, derived query tìm row với đúng field values.
- **Mono.empty**: query không có row **complete mà không phát `onNext`**, khác với ném `NoSuchElementException`.
- **Ordering**: tạo hai row theo một thứ tự, rồi buộc repository query sắp xếp **ISBN tăng dần**; không phụ thuộc vào kết quả `findAll()` ngẫu nhiên.
- **Update**: mutate field trên Java object chưa đồng nghĩa DB tự update; gọi `repository.save(saved)` để thực thi UPDATE theo ID.
- **Duplicate unique**: publisher phát `onError` do DB constraint, Spring data-access layer thường translate thành `DataIntegrityViolationException`. Nếu đổi vendor/version, xem root cause và translation policy thay vì so nguyên văn SQL error message.
- **DatabaseClient**: thực thi SQL có bind parameters, kiểm đúng **1 row updated**, rồi dùng repository để đọc lại.
- **R2dbcEntityTemplate**: chạy query theo `Criteria` dùng **property mapping** (`isbn`) và trả một `Mono<Book>`.
- **Transaction rollback**: gom việc `save` + lỗi cố ý vào **cùng reactive Publisher** dưới `TransactionalOperator`. Sau khi `onError`, transaction rollback, query riêng không thấy row. Nếu tách `save` thành hai subscription ngoài operator, không còn cùng transaction.
- **Lazy publisher**: gọi `save` mà chưa subscribe thì count vẫn là 0; subscribe bằng StepVerifier mới có insert, count thành 1.

Test `@BeforeEach` dọn dữ liệu bằng `deleteAll()` đã được **subscribe** nên mỗi method có fixture rỗng. Các method không dựa vào thứ tự chạy. **Đây là 9 phương thức `@Test`**, không phải 9 bước chạy chung một transaction.

### 6.8. Chạy và kết quả mong đợi

Từ thư mục có `pom.xml`, cần Java 17+ và Maven:

```bash
mvn test
```

Nếu project có Maven Wrapper:

```bash
./mvnw test
```

Chỉ chạy test class:

```bash
mvn -Dtest=BookRepositoryR2dbcTest test
```

Trên Windows dùng `mvnw.cmd` nếu có wrapper hoặc `mvn` nếu Maven đã được cài. Với H2 driver, SQL init, schema và code chính xác như trên, kỳ vọng **9 tests run, 0 failures, 0 errors**. Các test phát lỗi unique/rollback **PASS khi `StepVerifier` nhận đúng `onError`**, không phải vì DB chấp nhận dữ liệu sai. Không có stdout nghiệp vụ cố định; Surefire/JUnit có thể in log truy vấn và thông báo exception.

**Điều kiện áp dụng:** suite ở đây chạy tuần tự trong một test class, trên H2 in-memory độc lập; nếu có test class khác dùng **cùng database name** hoặc chạy song song, cần chọn database/schema/fixture isolation tương ứng. Các câu truy vấn SQL trong file dùng cú pháp H2, không phải lời đảm bảo chạy trên mọi R2DBC dialect.

## 7. Reactive transaction và rollback: điểm dễ nhầm nhất

### `@DataR2dbcTest` không tự tạo rollback quanh mỗi test

Khác với những test JDBC/JPA thường được Spring test quản lý transaction, **Data R2DBC test mặc định không transactional**. Có thể dùng `@Transactional` trên một **service bean reactive** được gọi qua Spring proxy, nhưng cần:

- `ReactiveTransactionManager` thích hợp (ví dụ `R2dbcTransactionManager`).
- Method được invoke **qua Spring proxy**, không phải self-invocation.
- Method trả `Mono`/`Flux` và các database operations diễn ra trong **cùng Reactor Context**.
- Subscription diễn ra **trong** reactive transaction boundary; không đưa một phần thao tác ra ngoài operator.

Ví dụ concept service:

```java
@Service
class InventoryService {
    private final BookRepository repository;

    InventoryService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Void> saveThenFail(Book book) {
        return repository.save(book)
                .then(Mono.error(new IllegalStateException("rollback")));
    }
}
```

Đây là **snippet ý tưởng, không phải file biên dịch độc lập**: cần imports, bean trong full context/`@Import`, transaction manager và test riêng. `@DataR2dbcTest` **không scan `@Service` mặc định**, nên muốn kiểm service thật có thể `@Import` nhỏ hoặc dùng `@SpringBootTest` phù hợp.

### TransactionalOperator cho test rõ ranh giới

Trong file runnable ở trên:

```java
TransactionalOperator tx = TransactionalOperator.create(transactionManager);

Mono<Void> work = tx.transactional(
        repository.save(new Book("ROLLBACK", "Example", 1))
                .then(Mono.<Void>error(
                        new IllegalStateException("force rollback"))));
```

Đây là snippet lấy từ cấu trúc test đã inject `transactionManager`. Operator bọc toàn bộ Publisher: khi subscription nhận lỗi, transaction rollback. Phải kiểm **sau khi pipeline kết thúc** bằng query mới để thấy không có row.

**Đừng dùng `ThreadLocal` hoặc `TransactionTemplate` imperative để suy ra transaction của pipeline R2DBC**. Reactive transactions được mang trong **Reactor Context**, và cancellation của Publisher có thể ảnh hưởng lifecycle transaction; khi test cancel/timeout, cần xác định rõ semantics transaction và không đánh đồng cancel với commit thành công.

### Unique violation và trạng thái connection

Khi database trả lỗi UNIQUE, `StepVerifier.expectErrorSatisfies` giúp kiểm lỗi tại **subscription**. Không cần gọi `block()` để “ép” exception xuất hiện. Nếu muốn kiểm handling ở service/API, test thêm reactive service hoặc WebFlux boundary. Không bắt lỗi SQL rồi tiếp tục dùng một transaction đã lỗi như thể nó còn hợp lệ. Sau error, transaction cần rollback; trong test không transactional mặc định, từng operation có thể tự commit độc lập.

## 8. H2 in-memory hay PostgreSQL Testcontainers?

H2 rất tốt để học reactive CRUD, mapping/query cơ bản và chạy test nhanh; nhưng nó **không chứng minh** mọi ràng buộc, SQL grammar, isolation và locking của PostgreSQL/MySQL/production.

| Mục tiêu | Dùng H2 R2DBC | Dùng production-like Testcontainers |
|---|---|---|
| Repository bean được tạo, generated ID, CRUD | Phù hợp | Phù hợp nhưng nặng hơn |
| SQL query method và mapping đơn giản | Phù hợp | Phù hợp |
| PostgreSQL `jsonb`, arrays, collations, `ON CONFLICT` | **Không đủ** | **Nên dùng PostgreSQL thật** |
| FK/unique/index theo migration production | Chỉ nếu DDL test giống hệt về semantics | **Chạy migrations thật** |
| Transaction isolation, concurrency, deadlock/lock | H2 behavior có thể khác | DB engine đúng version |
| R2DBC driver/network và connection pool | H2 in-process, không đại diện remote | Có cơ hội phát hiện lỗi driver/connection tương ứng |
| CI tối ưu thời gian | Nhanh, ít phụ thuộc | Cần Docker/daemon và quản lý container |
| Regression data-critical | Bổ sung test cơ bản | **Nên có coverage bằng đúng DB engine** |

### Hướng dẫn cấu hình Testcontainers Spring Boot 3.5

Khi cần PostgreSQL R2DBC trong test, bổ sung dependency test tương ứng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Đây là **dependency snippet**, không thay cho POM runnable phần 6. Khi dùng Testcontainers, thêm `@Testcontainers`, `@Container` và `@ServiceConnection` cho `PostgreSQLContainer<?>` theo Spring Boot 3.5 để tự cung cấp **R2dbcConnectionDetails**; cần bảo đảm test không vô tình dùng H2 embedded thay vì PostgreSQL. Nếu sử dụng `@AutoConfigureTestDatabase`, cấu hình **`replace = NONE`** khi cần giữ connection factory của container. `@ServiceConnection` có thể cung cấp cả JDBC và R2DBC details, nên khi dự án dùng cả hai hãy kiểm classpath và connection được chọn.

**Chú ý:** Flyway/Liquibase thường chạy migrations qua **JDBC**; nếu chỉ có R2DBC driver, cần khai báo JDBC driver/datasource riêng cho migrations theo tool, không nên tưởng `spring-boot-starter-data-r2dbc` tự tạo schema từ entity. Spring Boot 3.5 cho phép kết nối JDBC migration đồng tồn tại với R2DBC nhưng cần cấu hình rõ, đặc biệt khi auto-config loại trừ `DataSource` do đã có `ConnectionFactory`.

Ví dụ setup container thường cần thêm Docker đang hoạt động, PostgreSQL version pin phù hợp và chiến lược tạo schema/test data độc lập. Bài H2 runnable không phụ thuộc Docker; hãy dùng Testcontainers khi **rủi ro cần chứng minh** liên quan đúng database engine.

## 9. Những lỗi thường gặp khi viết `@DataR2dbcTest`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `No qualifying bean BookRepository` | Repository không được scan hoặc thiếu Spring Data R2DBC dependency | Kiểm package dưới `@SpringBootApplication`, `spring-boot-starter-data-r2dbc` |
| `ConnectionFactory` không tạo được | Thiếu R2DBC driver/URL không đúng format | Dùng `r2dbc-h2` hoặc driver DB thật, kiểm `spring.r2dbc.url` |
| `Table BOOKS not found` | Không chạy schema.sql, sai SQL init, khác tên quoting hoặc H2 DB bị xóa khi connection đóng | `spring.sql.init.mode=always`, tên bảng nhất quán, `DB_CLOSE_DELAY=-1` |
| `save(book)` không có row ở DB | Publisher chỉ được tạo, không subscribe | `StepVerifier.create(...).verifyComplete()` |
| Test sau bị trùng ISBN với test trước | R2DBC slice không tự rollback dữ liệu | Dọn fixture bằng reactive `deleteAll()` đã subscribe |
| Test pass nhưng dữ liệu/sort sai | Chỉ dùng `expectNextCount`, không kiểm fields hoặc ORDER BY | `assertNext`, `expectNextSequence`, query có order |
| Test `findByIsbn` trả rỗng | Chưa seed/subscribe hoặc query sai property/column mapping | Kiểm fixture, mappings, schema và lifecycle |
| H2 table name sai chữ hoa | `@Table("books")` quoted khác DDL không quote `BOOKS` | Dùng UPPERCASE nhất quán hoặc quoted DDL có chủ đích |
| `@Transactional` trên `void @Test` không rollback | Không phải reactive Publisher transaction boundary | `TransactionalOperator` hoặc reactive service proxy |
| Inject `@Service` fail | Slice chỉ nạp repository/data beans | `@Import` bean tối thiểu hoặc dùng `@SpringBootTest` |
| Test H2 pass nhưng production SQL fail | Dialect/constraint/migration khác engine | Testcontainers PostgreSQL/MySQL cùng engine |
| `DuplicateKeyException` bất ngờ | Unique constraint được thực thi khi subscribe | Assert `onError`, kiểm SQL root cause; không giả định save() synchronous |
| Test treo trên CI | Publisher không hoàn tất, lỗi connection/pool, thiếu timeout | `verify(Duration)`, timeout/test diagnostics và resource cleanup |
| Đổi sang JDBC driver nhưng R2DBC vẫn lỗi | `DataSource` khác `ConnectionFactory` | Thêm driver R2DBC đúng |
| Chạy test song song làm mất fixture | Dùng chung DB name và dọn cả table | Database/schema riêng, cô lập dữ liệu theo test |
| Gọi `block()` trong WebFlux event-loop | Blocking trên scheduler không phù hợp | Chuyển pipeline reactive, dùng StepVerifier trong JUnit |
| Tưởng `@Table` tự tạo schema | R2DBC mapping không phải Hibernate DDL | SQL init/migrations rõ |

## 10. So sánh test slice với service integration và WebFlux HTTP

Một repository test `@DataR2dbcTest` có thể chứng minh `BookRepository.findByIsbn` chạy SQL và map row đúng. Nhưng nó **không tự chứng minh** service sử dụng repository đúng hoặc endpoint WebFlux có trả JSON/HTTP status đúng.

```text
@DataR2dbcTest
  repository + schema + mapping + SQL
         |
         | cần chứng minh service wiring?
         v
@SpringBootTest(MOCK)
  service + repository + WebFlux context (in-process)
         |
         | cần HTTP socket thật?
         v
@SpringBootTest(RANDOM_PORT)
  WebTestClient -> embedded server -> service -> R2DBC database
```

Tùy rủi ro, có thể viết:

- **Unit test service** với fake/mock reactive repository để chứng minh business branches và `Mono.empty()`/error mapping.
- **`@DataR2dbcTest`** để chứng minh database access, SQL syntax và mapping, không cần socket.
- **`@WebFluxTest`** để chứng minh route, `@RequestParam`/body validation, JSON và HTTP error mapping với service mock.
- **`@SpringBootTest`** với real repository/service và R2DBC database test để chứng minh DI nhiều tầng.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)` + WebTestClient** khi cần HTTP server thật.

**Transaction xuyên HTTP server:** real HTTP request thường xử lý ở server thread/ Reactor Context khác test caller; đừng kỳ vọng test thread `@Transactional` rollback commit server-side. Giữ database test riêng và cleanup rõ.

### Khi nào không cần R2DBC?

Nếu ứng dụng có logic blocking thuần JDBC/JPA, chỉ bọc `Mono.fromCallable(() -> jdbcTemplate.query(...))` **không biến JDBC thành non-blocking**. Nếu cần tính reactive end-to-end, sử dụng R2DBC driver và hiểu rõ mức hỗ trợ DB/dialect; nếu nghiệp vụ có ORM relationship graph rất phức tạp, JPA có thể là công nghệ khác phù hợp hơn, không nên ép đổi chỉ vì WebFlux có trên classpath.

## 11. Checklist trước khi commit

- [ ] Test thực sự dùng **Spring Data R2DBC**, không nhầm JDBC/JPA.
- [ ] Đã đọc phạm vi `@DataR2dbcTest`, biết `@Service`/full web context không nạp mặc định.
- [ ] Có R2DBC **driver** và cấu hình `ConnectionFactory` đúng.
- [ ] Schema test được tạo rõ qua SQL init/migrations; không trông chờ `@Table` tự tạo bảng.
- [ ] Dữ liệu fixture và connection lifecycle H2 được kiểm soát.
- [ ] Tôi không coi việc gọi `repository.save(...)` là đã INSERT khi chưa subscribe.
- [ ] Mọi Publisher trong assertion/cleanup được `StepVerifier` subscribe và verify.
- [ ] Với `Mono.empty()`, test mong **onComplete không onNext**.
- [ ] Với `Flux`, tôi kiểm đúng nội dung/thứ tự khi contract yêu cầu, không chỉ đếm.
- [ ] Có test CRUD, derived query, mapping, unique/SQL error theo yêu cầu.
- [ ] Tôi biết `@DataR2dbcTest` **không tự rollback** sau mỗi method.
- [ ] Nếu cần rollback, pipeline được bọc trong `TransactionalOperator`/reactive service proxy và kiểm dữ liệu sau lỗi.
- [ ] Không trộn một reactive transaction với các subscription rời rạc ngoài Reactor Context.
- [ ] Tôi hiểu H2 không đại diện đầy đủ cho PostgreSQL production; chọn Testcontainers khi cần.
- [ ] Với schema production, migrations được chạy/kiểm bằng tool và connection phù hợp.
- [ ] Các test chạy độc lập, có cleanup và tránh xung đột khi CI parallel.
- [ ] Tôi phân biệt StepVerifier test repository với WebTestClient test HTTP.
- [ ] Nếu dùng Boot 4.x, tôi đã cập nhật dependency và import slice theo version mới.

**Kết luận:** `@DataR2dbcTest` là **test slice chuyên cho Reactive SQL repositories**. Nó cung cấp hạ tầng R2DBC để kiểm SQL và mapping nhanh hơn full context; **StepVerifier là bước subscribe bắt buộc để thấy tác dụng thật**; **schema và fixture phải chủ động quản lý**; **rollback không được tự động đảm bảo** như khi dùng `@DataJpaTest`. Khi cần chứng minh transaction, DB dialect hoặc HTTP nhiều tầng, mở rộng test có chủ đích, không suy luận từ một repository test PASS.

### Tài liệu chính thức

- [Spring Boot 3.5 — Auto-configured Data R2DBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — R2DBC and SQL databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Test slice auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Data Relational — R2DBC Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot 3.5 — Testcontainers and service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [R2DBC H2 driver options](https://github.com/r2dbc/r2dbc-h2)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
