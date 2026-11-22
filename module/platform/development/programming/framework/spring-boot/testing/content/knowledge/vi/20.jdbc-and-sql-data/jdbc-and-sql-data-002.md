# @DataJdbcTest cho Spring Data JDBC

Trong module **Spring Boot - testing**, nhóm **JDBC và dữ liệu SQL**, `@DataJdbcTest` là một **test slice** của Spring Boot chuyên kiểm tra **Spring Data JDBC repositories, ánh xạ aggregate root ↔ bảng SQL, query methods và ràng buộc database**. Nó tạo một `ApplicationContext` hẹp, thường dùng cơ sở dữ liệu nhúng và tự rollback transaction của mỗi test. Nhờ đó, bạn có thể kiểm tra SQL thực được thực thi mà không cần khởi động web server, controller và toàn bộ service của ứng dụng.

Điều cần nhớ: **Spring Data JDBC không phải JPA/Hibernate**. Repository dùng `CrudRepository` nhưng mapping dựa trên `org.springframework.data.relational.core.mapping.Table` và `org.springframework.data.annotation.Id`; không có persistence context với dirty checking/lazy loading giống JPA. `@DataJdbcTest` phù hợp khi bạn cần chứng minh câu SQL, insert/update/delete, ánh xạ cột hoặc constraint thực sự hoạt động.

Bài học trình bày cách chọn đúng test slice, cấu hình Spring Boot 3.4/3.5 và Java 17+, tạo một ví dụ repository có thể chạy, kiểm tra CRUD, derived query, SQL query tùy chỉnh, fixture `@Sql`, transaction rollback, dùng H2 hay PostgreSQL/Testcontainers, và nhận biết trường hợp phải dùng `@SpringBootTest` hoặc một công cụ khác.

## 1. @DataJdbcTest làm gì?

Một test điển hình:

```java
@DataJdbcTest
class BookRepositoryTest {
    @Autowired BookRepository repository;
    @Autowired JdbcTemplate jdbc;
}
```

Đoạn trên chỉ là skeleton class (cần imports, entity và repository đã định nghĩa). Khi dùng `@DataJdbcTest` với dự án đúng dependencies, Spring Boot tạo một **slice context** tập trung vào Spring Data JDBC:

- Bật auto-configuration phù hợp với `DataSource`, `JdbcTemplate`, transaction infrastructure và Spring Data JDBC repository.
- Tìm các Spring Data JDBC repositories và entity/aggregate root được đánh dấu `@Table` trong phạm vi cấu hình ứng dụng.
- Theo tài liệu, các subclass của `AbstractJdbcConfiguration` có thể được scan để cung cấp tùy chỉnh JDBC mapping.
- **Không scan các `@Component`/`@Service` thông thường** hoặc `@ConfigurationProperties` tùy ý như khi tải full app; có thể chủ động thêm bean cần test bằng cấu hình cụ thể.
- Mặc định thay datasource ứng dụng bằng **embedded in-memory database** nếu có driver nhúng phù hợp trên test classpath; điều này có thể được điều chỉnh bằng `@AutoConfigureTestDatabase`.
- Test được đánh dấu **`@Transactional`** và rollback transaction sau mỗi method theo mặc định, với các điều kiện của Spring TestContext.
- Vẫn là test **thực thi SQL** lên database, không phải mock repository.

### DataJdbcTest không tự sinh schema từ entity

Khác với việc một số người quen JPA mong đợi `spring.jpa.hibernate.ddl-auto` tạo bảng, **Spring Data JDBC không dựa vào Hibernate DDL auto-generation**. Nếu H2 chưa có bảng `books`, gọi `repository.save(...)` sẽ thất bại dù Spring tạo repository bean thành công.

Bài học sẽ cung cấp `src/test/resources/schema.sql`, cho phép SQL initializer khởi tạo bảng trong embedded H2. Dự án production có Flyway/Liquibase nên dùng migrations phù hợp với mục tiêu test, không chạy đồng thời hai cơ chế khởi tạo schema xung đột.

### Điều “slice context” không chứng minh

Một `@DataJdbcTest` xanh không tự xác nhận:

- Controller định tuyến HTTP đúng, JSON được serialize đúng hoặc authentication/authorization hoạt động.
- Toàn bộ `@Service`, `@Component`, messaging client và các bean production cùng được inject thành công.
- DB production dùng PostgreSQL/MySQL xử lý dialect, transaction isolation, locking hoặc migration giống H2.
- Dữ liệu đã **commit thật ra ngoài test transaction** nếu chính test đang ở trong transaction tự rollback.

Những rủi ro đó cần test tương ứng ở service/integration/full-context và hạ tầng phù hợp.

## 2. So sánh @JdbcTest, @DataJdbcTest, @DataJpaTest và @SpringBootTest

| Mức test | Tải nội dung chính | Phù hợp khi | Không phù hợp để kết luận |
| --- | --- | --- | --- |
| JUnit thuần | Java objects, có thể mock ports | Rule, mapping logic thuần, validation không cần DB | SQL thực/transaction/constraint |
| `@JdbcTest` | `DataSource`, `JdbcTemplate` và các JDBC components phù hợp | Test DAO tự viết SQL bằng `JdbcTemplate` mà **không dùng Spring Data JDBC repositories** | Repository derived query/mapping được auto-config như Data JDBC |
| **`@DataJdbcTest`** | `DataSource`, `JdbcTemplate`, Spring Data JDBC repositories và mapping | **CRUD/query/mapping/aggregate/constraints của Spring Data JDBC** | Full service/controller/web wiring |
| `@DataJpaTest` | JPA EntityManager, Hibernate/JPA repositories | `@Entity`, JPQL, cascade/flush/lazy behavior của JPA | Spring Data JDBC `@Table` repository |
| `@DataR2dbcTest` | R2DBC connection/repository reactive | Non-blocking `R2dbcRepository`/`DatabaseClient` | Blocking JDBC repository |
| `@SpringBootTest` | ApplicationContext rộng theo cấu hình | Nhiều tầng/service/proxy/config cần hoạt động cùng nhau | Thường quá rộng nếu chỉ muốn test repository |

**Quy tắc chọn:** nếu đang viết repository `interface BookRepository extends CrudRepository<Book, Long>` với Spring Data JDBC, hãy bắt đầu bằng `@DataJdbcTest`. Nếu chỉ dùng `JdbcTemplate.queryForObject(...)` trong một DAO tự tạo, `@JdbcTest` có thể hẹp và đủ. Nếu class được annotate `@jakarta.persistence.Entity` và repository dùng Hibernate/JPA, chọn `@DataJpaTest`. Nếu code dùng `Mono`/`Flux` trên R2DBC, chọn `@DataR2dbcTest`, đừng xem JDBC test là non-blocking.

Một điểm dễ nhầm: cả Spring Data JDBC và Spring Data JPA đều có repository interface giống `CrudRepository`. **Tên interface chưa đủ để quyết định test slice**; hãy xem mapping annotations, starter và repository factory thật đang được dùng.

## 3. Spring Data JDBC nhìn aggregate thế nào?

Spring Data JDBC xem một entity được repository quản lý như **aggregate root**:

```text
BookRepository (CrudRepository<Book, Long>)
               |
               v
Spring Data JDBC repository proxy
               |
               v
JdbcAggregateTemplate / mapping metadata
               |
               v
NamedParameterJdbcOperations / JDBC
               |
               v
DataSource + transaction manager
               |
               v
SQL table books
```

Khi gọi `repository.save(book)`, framework quyết định insert hay update dựa trên cơ chế nhận diện entity mới (thường dựa vào `@Id` chưa được gán, có các tùy chọn khác như `Persistable`). Sau khi insert với identity column, ID sinh bởi database được phản ánh vào entity hoặc bản entity trả về tùy kiểu object/mapping; **luôn dùng giá trị mà `save(...)` trả về** để tránh giả định về mutable/immutable ID strategy.

Khi query, Spring Data JDBC tạo SQL hoặc thực thi SQL từ `@Query`, sau đó ánh xạ các cột thành object. Không có session cache JPA giữ object thay đổi mà chưa lưu; nếu sửa property rồi muốn cập nhật SQL, phải **gọi `save(...)` hoặc query update được thiết kế phù hợp**.

### @Table/@Id của JDBC, không phải JPA

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {
    @Id
    private Long id;
}
```

Đây là snippet minh họa. Annotation `@Id` ở đây **khác** `jakarta.persistence.Id`; `@Table` JDBC **khác** `jakarta.persistence.Table`. Nếu copy một entity JPA vào JDBC example mà không đổi imports, repository có thể không nhận metadata như mong đợi.

### Aggregate có các object con

Nếu aggregate chứa `List<BookReview>` hoặc `Set<LineItem>` được mapping bằng `@MappedCollection`, Spring Data JDBC có thể sử dụng **bảng riêng** và cột khóa tham chiếu để lưu/đọc object con. Test cần xác minh:

- Insert aggregate root cùng children tạo đúng bản ghi và khóa liên kết.
- Update aggregate có quy tắc thay thế/ghi lại children phù hợp với Spring Data JDBC, không mặc định Hibernate dirty checking.
- Xóa aggregate dọn các children do aggregate sở hữu theo mapping.
- Tên cột `idColumn`/`keyColumn`, ordering và uniqueness đúng theo schema.

Đây là khía cạnh đáng mở rộng sau khi đã hiểu ví dụ Book một bảng. Đừng diễn giải quan hệ aggregate của Spring Data JDBC giống hoàn toàn `@OneToMany`/lazy JPA.

## 4. Project Java 17+ chạy được với @DataJdbcTest

Ví dụ dùng thư viện sách với một bảng `books` có identity ID, ISBN duy nhất và `stock` không âm. Repository cần chứng minh các yêu cầu:

1. Insert một cuốn sách và lấy được generated ID.
2. Đọc theo ID và derived query `findByIsbn`.
3. Chạy query SQL tùy chỉnh với threshold và thứ tự ổn định.
4. Update stock bằng repository save; đọc lại trực tiếp bằng JDBC.
5. Delete theo ID.
6. Unique constraint trên ISBN và CHECK constraint trên stock được DB thực thi.
7. `@Sql` tải dữ liệu fixture cho một test method.
8. Sau mỗi test, transaction rollback mặc định để dữ liệu không làm nhiễu các case khác.

**Cấu trúc thư mục:**

```text
src/
├── main/java/example/datajdbc/
│   ├── LibraryApplication.java
│   ├── Book.java
│   ├── BookRepository.java
│   ├── StockPolicy.java
│   └── StockPolicyDemo.java
└── test/
    ├── java/example/datajdbc/
    │   ├── BookRepositoryTest.java
    │   └── StockPolicyTest.java
    └── resources/
        ├── schema.sql
        └── sql/seed-books.sql
```

Trong bài này không cần web starter, REST controller hay H2 production. H2 được đưa lên **test runtime classpath** để Spring Boot tự chọn database nhúng khi chạy test.

### 4.1. build.gradle (đoạn phụ thuộc)

Với Spring Boot **3.4/3.5**, Java 17+ và một project Gradle đã cấu hình Boot plugin, repositories, dependency management và Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây **không phải** toàn bộ file `build.gradle` độc lập: phần `plugins`, phiên bản Boot, repositories và Java toolchain phải được tạo ở project gốc bằng Spring Initializr hoặc build hiện có. Boot BOM quản lý version của Spring Data JDBC, H2 và JUnit tương thích.

Không cần `spring-boot-starter-data-jpa`; đưa JPA starter vào chỉ để chạy test JDBC có thể làm classpath phức tạp và gây hiểu nhầm repository module. Nếu ứng dụng cần cả JDBC và JPA, phải cấu hình ranh giới repositories và lựa chọn slice một cách tường minh.

### 4.2. LibraryApplication.java

Tạo `src/main/java/example/datajdbc/LibraryApplication.java`:

```java
package example.datajdbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LibraryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }
}
```

Class nằm ở package gốc `example.datajdbc` để mặc định Spring Boot nhận repository và aggregate dưới cùng package. **Trong bài này, `main()` chủ yếu phục vụ việc tìm cấu hình ứng dụng cho test.** Để chạy ứng dụng production ngoài test, bạn phải cấu hình datasource/migrations riêng; H2 ở `testRuntimeOnly` không cung cấp database cho runtime production.

### 4.3. Book.java — entity Spring Data JDBC mutable

Tạo `src/main/java/example/datajdbc/Book.java`:

```java
package example.datajdbc;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {
    @Id
    private Long id;
    private String isbn;
    private String title;
    private int stock;

    public Book() {
        // Constructor không tham số cho mapping.
    }

    public Book(String isbn, String title, int stock) {
        this.isbn = isbn;
        this.title = title;
        this.stock = stock;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getIsbn() {
        return isbn;
    }

    public void setIsbn(String isbn) {
        this.isbn = isbn;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
```

**Tại sao dùng mutable class thay vì record trong ví dụ cơ bản?** Spring Data JDBC hỗ trợ nhiều kiểu đối tượng immutable, nhưng việc tạo ID qua database và cơ chế reconstruct/copy yêu cầu hiểu rõ constructor, wither hoặc mapping strategy. Class có no-args constructor, getters/setters và `Long id` nullable giúp tập trung vào test repository thay vì những chi tiết immutable mapping riêng.

`id == null` trên một instance mới cho phép repository thực hiện insert với identity column; sau `save`, đừng tự chọn ID tùy ý để đoán database đã chèn vào row nào. Dữ liệu ISBN/stock ở đây chưa bị validate trong Java constructor: test database constraint sẽ chứng minh DB thực sự chặn dữ liệu sai. Trong production, validation ở application boundary vẫn cần thiết và DB constraint là lớp bảo vệ bổ sung.

### 4.4. BookRepository.java — derived query và SQL @Query

Tạo `src/main/java/example/datajdbc/BookRepository.java`:

```java
package example.datajdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface BookRepository
        extends CrudRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    @Query("""
            SELECT id, isbn, title, stock
            FROM books
            WHERE stock >= :minimum
            ORDER BY isbn
            """)
    List<Book> findWithStockAtLeast(
            @Param("minimum") int minimum);
}
```

Hai kiểu query:

- `findByIsbn` là **derived query** cho property `isbn` của aggregate root. Spring Data JDBC hỗ trợ derivation cho nhiều điều kiện đơn giản trên properties trực tiếp; không mặc định hỗ trợ mọi kiểu join/complex nested condition của JPA.
- `@Query` cho phép SQL viết tay. `@Param("minimum")` ánh xạ named parameter `:minimum` trong SQL. Query chọn **đủ cột entity** mà mapper cần; `ORDER BY isbn` giúp expected order ổn định.
- `CrudRepository<Book, Long>` cung cấp `save`, `findById`, `findAll`, `deleteById`, `count`, `existsById`. Không cần viết implementation repository thủ công.
- Mọi `BookRepository` method ở ví dụ chạy **blocking JDBC**, không trả `Mono/Flux` và không được xem là reactive database access.

Tại Spring Data JDBC hiện hành, derived queries chủ yếu dành cho **simple properties** và select. Nếu có join phức tạp, native SQL với `@Query`, `JdbcTemplate` hoặc custom repository có thể phù hợp hơn. Query tùy chỉnh phải tự tính đến schema, dialect và named parameters.

### 4.5. schema.sql — database có identity, UNIQUE và CHECK

Tạo `src/test/resources/schema.sql`:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    isbn VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
```

Script này sử dụng SQL phù hợp **H2 2.x** trong cấu hình thông dụng. Trong dự án có migration framework hoặc database production khác, cân nhắc cú pháp dialect và chạy schema qua migrations của dự án.

Tại sao cần ràng buộc DB?

- `PRIMARY KEY` và identity: bảo đảm mỗi row có khóa riêng, ID được sinh.
- `NOT NULL`: ngăn dữ liệu thiếu ISBN/title/stock.
- `UNIQUE (isbn)`: ngăn hai cuốn sách dùng cùng ISBN trong database.
- `CHECK (stock >= 0)`: chống stock âm, ngay cả khi code Java không validate.

**Lưu ý:** `@DataJdbcTest` không tự tạo `books` chỉ vì có `@Table("books")`. Khi H2 nhúng có trên test classpath, SQL initialization thông dụng của Boot thực thi `schema.sql`. Nếu test báo “table BOOKS not found”, kiểm tra đường dẫn/classpath, SQL init mode, migration conflicts và datasource thực tế — không vội thay bằng mock repository.

### 4.6. SQL fixture: seed-books.sql

Tạo `src/test/resources/sql/seed-books.sql`:

```sql
INSERT INTO books (isbn, title, stock)
VALUES ('BK-900', 'Seeded JDBC Book', 4);
```

File fixture không có `id`; DB sẽ sinh identity ID. Trong test dùng `@Sql("/sql/seed-books.sql")` để nạp dữ liệu trước method cần kiểm tra. Đừng chèn file fixture này vào `data.sql` chung nếu bạn chỉ muốn dùng nó ở **một test method**.

## 5. Bộ test @DataJdbcTest hoàn chỉnh

Tạo `src/test/java/example/datajdbc/BookRepositoryTest.java`:

```java
package example.datajdbc;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJdbcTest
class BookRepositoryTest {

    @Autowired
    private BookRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void savesAggregateAndLoadsItById() {
        Book saved = repository.save(
                new Book("BK-001", "Learning Spring JDBC", 5));

        assertNotNull(saved.getId());

        Book loaded = repository.findById(
                saved.getId()).orElseThrow();

        assertEquals("BK-001", loaded.getIsbn());
        assertEquals("Learning Spring JDBC", loaded.getTitle());
        assertEquals(5, loaded.getStock());

        Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        assertEquals(Long.valueOf(1), rows);
    }

    @Test
    void derivedQueryFindsByIsbnAndReportsMissing() {
        repository.save(
                new Book("BK-002", "Database Essentials", 3));

        Book loaded = repository.findByIsbn(
                "BK-002").orElseThrow();
        assertEquals("Database Essentials",
                loaded.getTitle());

        assertTrue(repository.findByIsbn("BK-404").isEmpty());
    }

    @Test
    void declaredSqlQueryFiltersAndOrdersRows() {
        repository.save(new Book("BK-003", "Alpha", 5));
        repository.save(new Book("BK-004", "Beta", 0));
        repository.save(new Book("BK-005", "Gamma", 7));

        List<String> actual =
                repository.findWithStockAtLeast(4)
                        .stream()
                        .map(Book::getIsbn)
                        .toList();

        assertEquals(List.of("BK-003", "BK-005"), actual);
    }

    @Test
    void updatePersistsChangedStock() {
        Book saved = repository.save(
                new Book("BK-006", "Transactions", 2));

        saved.setStock(9);
        repository.save(saved);

        Integer stock = jdbc.queryForObject(
                "SELECT stock FROM books WHERE isbn = ?",
                Integer.class, "BK-006");
        assertNotNull(stock);
        assertEquals(9, stock.intValue());
    }

    @Test
    void deletingAggregateRemovesDatabaseRow() {
        Book saved = repository.save(
                new Book("BK-007", "SQL Design", 1));

        repository.deleteById(saved.getId());

        assertFalse(repository.existsById(saved.getId()));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE isbn = ?",
                Integer.class, "BK-007");
        assertNotNull(rows);
        assertEquals(0, rows.intValue());
    }

    @Test
    void duplicateIsbnFailsUniqueConstraint() {
        repository.save(
                new Book("BK-008", "One", 1));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.save(
                        new Book("BK-008", "Two", 2)));
    }

    @Test
    void negativeStockFailsCheckConstraint() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.save(
                        new Book("BK-009", "Invalid", -1)));
    }

    @Test
    @Sql("/sql/seed-books.sql")
    void sqlFixtureIsVisibleToRepositoryQuery() {
        Book seeded = repository.findByIsbn(
                "BK-900").orElseThrow();

        assertEquals("Seeded JDBC Book",
                seeded.getTitle());
        assertEquals(4, seeded.getStock());
    }
}
```

Đây là **8 JUnit test methods** trong một `@DataJdbcTest` class. Chúng kiểm tra repository và database **thật**, không mock `BookRepository` hay `JdbcTemplate`. Từng method dùng dữ liệu ISBN riêng; SQL fixture chỉ nạp ở method có `@Sql`.

### Phân tích tám test

**1. Insert/read-back:** `repository.save` thực hiện SQL insert; ID được sinh; `findById` đọc lại object từ DB. Assertion `JdbcTemplate.SELECT COUNT(*)` kiểm tra số row **ở phía database**, giảm rủi ro test chỉ nhìn object trong memory.

**2. Derived query:** `findByIsbn` được repository proxy thực thi; test kiểm tra cả found và missing. Đây là khác biệt so với việc mock `when(repository.findByIsbn(...))` — một mock hoàn toàn không chứng minh SQL/mapping.

**3. @Query có named parameter:** `:minimum` lọc hàng có `stock >= 4`, `ORDER BY isbn` giúp kết quả là `[BK-003, BK-005]` theo thứ tự rõ. Nếu bỏ `ORDER BY` mà vẫn assert order, test có thể phụ thuộc execution plan không bảo đảm.

**4. Update:** ID đã có khiến `save(saved)` cập nhật row. `JdbcTemplate` đọc trực tiếp cột `stock` để xác nhận số 9 thực sự được ghi vào DB trong transaction test.

**5. Delete:** `deleteById` loại row; kiểm tra cả `existsById` và SQL COUNT. Không dựa vào danh sách đã cache (Spring Data JDBC không có JPA first-level cache giống Hibernate).

**6. UNIQUE constraint:** ISBN trùng phải làm JDBC throw exception được Spring dịch thành `DataIntegrityViolationException`. Đây là ví dụ về **database constraint** chứ không phải một exception Java do constructor tự tạo.

**7. CHECK constraint:** stock âm bị DB từ chối; kiểm tra constraint thực sự có hiệu lực ở H2. Nếu production yêu cầu ràng buộc phức tạp/dialect riêng, cần test trên engine thật.

**8. @Sql fixture:** Spring TestContext chạy script trước test method, repository đọc được row `BK-900`. Với transaction rollback mặc định, dữ liệu seed trong test transaction thông thường cũng được rollback cuối method; không để test khác phụ thuộc row seed này.

**Điều bài test chưa xác nhận:** nhiều transaction đã commit khi test method kết thúc, hành vi concurrent transaction/isolation, migration của PostgreSQL, REST controller hay HTTP serialization. Cần thiết kế test rộng hơn nếu đó là contract.

## 6. Chạy code và đọc kết quả chính xác

Trong project có Gradle wrapper và các files đúng thư mục:

```bash
./gradlew test --tests example.datajdbc.BookRepositoryTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.datajdbc.BookRepositoryTest"
```

**Kỳ vọng** (khi dependencies/schema/H2 và Spring Boot test configuration đúng): **8 JUnit methods pass**. Kết quả hiển thị trên Gradle và các file test reports phụ thuộc runner/version, nên không hứa một chuỗi stdout cố định. Nếu chạy module con, hãy sử dụng đúng task dạng `:module:test`.

Trong IDE, đặt JUnit Platform/Java 17+ và để Gradle/IDE dùng cùng test classpath. Nếu IDE báo repository bean không tìm thấy, đừng thêm `@SpringBootTest` chỉ để che vấn đề: kiểm tra starter Data JDBC, package scanning, `@Table`/`@Id` imports và cấu hình test slice.

### Thứ tự các test không được xem là hợp đồng

JUnit 5 không đảm bảo tám method tự chạy theo thứ tự khai báo nếu không có cấu hình ordering. Bộ test không dựa vào row được tạo bởi method khác: mỗi method tự tạo data hoặc dùng `@Sql`. **Không viết test “method A insert, method B đọc được”** để chứng minh rollback/commit; đó là dependency theo thứ tự, dễ fail ngẫu nhiên và đi ngược isolation.

### Vì sao dùng JdbcTemplate trong cùng @DataJdbcTest?

`JdbcTemplate` được cấu hình trong slice để bạn có thể:

- Trực tiếp kiểm tra row count, cột SQL, foreign key của bảng con.
- Thiết lập dữ liệu tối thiểu khi không muốn dùng repository save cho fixture.
- So sánh SQL persistence với domain mapping, phát hiện lỗi chỉ sửa object trong memory.
- Kiểm tra constraint/quy tắc query với một nguồn quan sát khác repository method.

**Cẩn thận:** nếu cả `repository.findById` và `JdbcTemplate` đang dùng **cùng test transaction**, việc đọc thấy row **không chứng minh dữ liệu đã commit ngoài transaction**. Trong mục 9 sẽ phân biệt rõ.

## 7. Embedded H2: nhanh nhưng không giống mọi database production

Theo tài liệu Boot, `@DataJdbcTest` mặc định sử dụng embedded in-memory database khi driver phù hợp trên classpath và có thể **replace** datasource do ứng dụng cấu hình. H2 rất hữu ích cho những test:

- CRUD cơ bản với identity, `VARCHAR`, `INTEGER`.
- Simple derived queries và custom SQL không có dialect-specific syntax.
- Mapping property ↔ column, repository proxy và validation bằng constraint chuẩn.
- Bộ test chạy nhanh, không cần Docker/DB ngoài.

Tuy nhiên, khi ứng dụng production dùng PostgreSQL, MySQL/MariaDB, SQL Server hay Oracle:

- Kiểu `JSONB`, arrays, enum, timestamp/timezone, identity/sequence có thể khác.
- Case sensitivity, collation, quoted identifiers và reserved words có thể khác.
- Index, constraint semantics, transaction isolation và row locking có thể khác.
- `UPSERT`, `ON CONFLICT`, `RETURNING` hoặc stored procedures có thể không tương thích.
- Migration Flyway/Liquibase có thể chạy thành công trên H2 nhưng thất bại trên database production.

**Kết luận đúng từ H2 test:** “Spring Data JDBC repository và các câu SQL/constraint được kiểm tra chạy trên H2 trong test context”, **không** phải “SQL chắc chắn chạy đúng trên PostgreSQL production”. Nếu lỗi đích phụ thuộc engine, chuyển sang Testcontainers hoặc test environment có database engine tương ứng.

## 8. @AutoConfigureTestDatabase: giữ datasource thật khi cần

Khi muốn ngăn Boot thay datasource của test bằng H2, dùng:

```java
@DataJdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryRealDatabaseTest {
    @Autowired BookRepository repository;
}
```

Đây là snippet class structure, cần imports và datasource riêng đã được cấu hình. `Replace.NONE` có nghĩa **không thay DataSource**. Nó **không tự tạo PostgreSQL database** hoặc tự bảo đảm không kết nối nhầm dữ liệu production.

**Quy tắc an toàn rất quan trọng:** nếu test dùng datasource thật, chỉ trỏ vào **dedicated test database** có thể xóa dữ liệu và credential ít quyền nhất. Đừng chạy `@Sql`/repository.deleteAll()` trên URL database production; `@DataJdbcTest` và `Replace.NONE` không tự cung cấp sandbox.

Khi không dùng Testcontainers, có thể cung cấp:

- `application-test.properties` hoặc `@TestPropertySource` với URL/username/password của test DB.
- `@ActiveProfiles("test")` và config/secret quản lý an toàn.
- Hạ tầng migration đúng version và cleanup.
- Kiểm soát Docker/CI network/connectivity, concurrency, timeout.

Cần đọc rõ `AutoConfigureTestDatabase.Replace` theo phiên bản Boot. Không dựa vào default thay thế khi bạn cần chứng minh chính xác engine production.

## 9. Testcontainers cho Spring Data JDBC trên PostgreSQL

Với Spring Boot 3.4/3.5, có thể dùng Testcontainers để chạy một PostgreSQL container phục vụ test. Để tránh tự quản URL/port/username bằng property rời, Spring Boot hỗ trợ `@ServiceConnection` và tạo JDBC connection details cho container.

### 9.1. Dependencies bổ sung

Trong `build.gradle` đang dùng Boot BOM, ngoài các dependencies ở mục 4:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

Đây là **đoạn bổ sung** chứ không ghi đè các dòng starter Data JDBC/JUnit trước đó. CI cần có Docker/Container runtime được Testcontainers hỗ trợ, image phù hợp và quyền kéo/chạy container.

### 9.2. Class test PostgreSQL

Tạo `src/test/java/example/datajdbc/BookRepositoryPostgresTest.java` khi muốn có thêm test tích hợp với engine thật:

```java
package example.datajdbc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@DataJdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private BookRepository repository;

    @Test
    void savesOnPostgresUsingRealJdbcDriver() {
        Book saved = repository.save(
                new Book("BK-PG-001", "Postgres Mapping", 6));

        assertNotNull(saved.getId());

        Book reloaded = repository.findByIsbn(
                "BK-PG-001").orElseThrow();
        assertEquals("Postgres Mapping",
                reloaded.getTitle());
        assertEquals(6, reloaded.getStock());
    }
}
```

**Tại sao cần cả ba annotation?**

- `@Testcontainers` + `@Container` quản lý vòng đời container JUnit.
- `@ServiceConnection` cho Boot nhận connection details từ PostgreSQL container thay vì hardcode URL.
- `@AutoConfigureTestDatabase(replace = NONE)` ngăn test database auto-configuration thay connection container bằng H2.
- `@DataJdbcTest` vẫn giữ **slice hẹp** cho repository, JDBC và transaction.
- `properties = "spring.sql.init.mode=always"` cho phép chạy `src/test/resources/schema.sql` trên PostgreSQL **không phải embedded DB** ở ví dụ không dùng Flyway/Liquibase.

DDL ở mục 4.5 sử dụng `GENERATED BY DEFAULT AS IDENTITY`/`CHECK` được H2 và các phiên bản PostgreSQL hiện đại hỗ trợ, nên có thể dùng trong ví dụ đơn giản. Nhưng **production migration** có thể khác — khi ứng dụng dùng Flyway/Liquibase, hãy cho test dùng migration thật thay vì khởi tạo schema song song bằng `schema.sql`.

**Giới hạn của test này:** nó chứng minh Spring Data JDBC kết nối, lưu và đọc được trên PostgreSQL container cùng schema test. Không tự chứng minh cấu hình pool/TLS/network của production, nhiều service beans, hoặc một deployment hoàn chỉnh. Nhưng nó cung cấp bằng chứng đáng tin hơn H2 về dialect và database-specific behavior.

### 9.3. Một lựa chọn khác: @DynamicPropertySource

Nếu dự án Spring Boot/version chưa dùng được `@ServiceConnection` hoặc cần cấu hình khác, có thể dùng Testcontainers với `@DynamicPropertySource` để đặt `spring.datasource.url/username/password` từ container. Đây là **cách thay thế**, không cần trộn cả hai vào cùng ví dụ. Khi test chọn cách này, vẫn phải ngăn Boot thay datasource bằng embedded DB theo đúng version.

## 10. Transaction rollback: hiểu chính xác test đang quan sát gì

`@DataJdbcTest` được đánh dấu `@Transactional`. Theo Spring TestContext, một test method thường chạy trong một **test-managed transaction** và rollback ở cuối. Vì vậy:

```text
@BeforeEach / @Sql (thường tham gia test transaction)
     |
     v
@Test: repository.save(...)
     |
     v
@Test: jdbc.queryForObject(...)  <-- thấy thay đổi trong transaction
     |
     v
Test kết thúc
     |
     v
Spring Test rollback transaction
```

Đây là lý do một test có thể insert, query và assert thành công, rồi không để row tồn tại cho method khác.

**Bẫy:** bạn không được xem việc `findById` hoặc `JdbcTemplate` thấy dữ liệu **trong cùng transaction** như bằng chứng transaction đã commit. Để xác nhận hành vi commit thật, phải thiết kế test với boundary khác: tắt test-managed transaction, dùng `TestTransaction` kết thúc transaction và kiểm tra từ transaction riêng, hoặc dùng integration test thích hợp. Khi làm vậy, cleanup cần tường minh để không làm bẩn database.

### Tắt transaction test khi thật sự cần

```java
@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalRepositoryTest {
    // Các method test ở đây không được bao
    // bởi test-managed transaction mặc định.
}
```

Đây là **snippet không phải test class độc lập**, cần imports và test methods. Với `Propagation.NOT_SUPPORTED`, rollback tự động của **test transaction** không còn bảo vệ data. Repository methods có thể tự mở transaction tương ứng; dữ liệu có thể commit thật, nên phải có cleanup đáng tin ở `@AfterEach`/truncate/isolated DB/container.

**Không dùng `@Rollback(false)` chỉ để test xanh** mà quên dọn data. Khi chạy chung suite, việc không rollback có thể làm `UNIQUE` constraint fail ở test sau, hoặc rò dữ liệu test sang CI environment khác.

### @Sql và transaction

`@Sql("/sql/seed-books.sql")` chạy script theo lifecycle Spring TestContext. Khi có test transaction, SQL fixture thường tham gia transaction đó theo cấu hình mặc định; rollback cuối method giữ test độc lập.

Tùy `@SqlConfig(transactionMode = ISOLATED)`, script có thể commit transaction riêng. Khi ấy không được mặc định rằng rollback test xóa seed data. Kiểm tra transaction mode và cleanup tương ứng.

**Schema DDL không như row fixture:** `schema.sql` thường khởi tạo tại thời điểm ApplicationContext/DataSource khởi động, bên ngoài transaction của từng test method. DDL không được rollback sau mỗi method; đó là điều bình thường.

## 11. Khi @DataJdbcTest không tìm thấy bean

Slice test không nạp mọi `@Service`/`@Component` và `@ConfigurationProperties`. Nếu repository có custom converters, callbacks, naming strategies hoặc phụ thuộc vào bean riêng ngoài slice, test có thể không tìm thấy chúng.

Các cách xử lý đúng:

- Nếu bean là phần **cốt lõi của mapping cần test**, đưa configuration tương ứng vào slice bằng `@Import(MyJdbcConfig.class)` hoặc cấu hình chỉ định.
- Với `@ConfigurationProperties`, dùng `@EnableConfigurationProperties(MyProps.class)` khi cần đưa props bean vào context.
- Với custom conversions, kiểm tra API `AbstractJdbcConfiguration` và những bean mà repository thật sử dụng; đừng import toàn bộ ứng dụng chỉ để lấy một converter.
- Khi test cần service orchestration, security, event publisher hoặc nhiều adapters chạy thật, có thể chuyển sang `@SpringBootTest` thay vì mở rộng slice vô hạn.
- Nếu chỉ cần test JDBC DAO không dùng Spring Data JDBC repositories, cân nhắc `@JdbcTest` để có scope rõ hơn.

### @Import một cộng tác viên test một cách có chủ đích

Ví dụ chỉ minh họa cấu trúc:

```java
@DataJdbcTest
@Import(MyJdbcSupportConfiguration.class)
class RepositoryWithCustomMappingTest {
    @Autowired BookRepository repository;
}
```

Không coi đoạn này là class độc lập: `MyJdbcSupportConfiguration` phải được định nghĩa, imports phải phù hợp và cấu hình phải phục vụ contract bạn muốn kiểm tra. **Tránh @Import một cấu hình quá rộng có @ComponentScan toàn ứng dụng**, vì nó phá mục tiêu slice.

### @MockitoBean không phải giải pháp cho mọi lỗi slice

Với repository test, **không mock BookRepository** — nếu làm vậy, test không còn chạy SQL và không chứng minh Spring Data JDBC mapping. Mock có thể phù hợp cho một collaborator nằm ngoài phạm vi repository trong test rộng hơn, nhưng khi mục tiêu chính là SQL, giữ repository và datasource **thật**.

Tương tự, không dùng H2 để che schema migration bị lỗi: nếu app production dùng migration, hãy kiểm tra migration ở môi trường phù hợp thay vì thay bằng test schema không giống thực tế.

## 12. Aggregate mapping, query và vòng đời: các case nâng cao

### 12.1. Kiểm tra @MappedCollection

Khi aggregate root sở hữu một collection child, mapping có thể bao gồm:

```java
@Table("purchase_orders")
class PurchaseOrder {
    @Id Long id;

    @MappedCollection(idColumn = "order_id")
    Set<LineItem> items;
}
```

Đây **chỉ là snippet concept**, không phải entity/test có thể chạy độc lập; cần định nghĩa `LineItem`, schema bảng con, constructors và mapping semantics. Trong bộ test thật, hãy dùng `repository.save(root)` rồi query **hai bảng** bằng JdbcTemplate để xác minh:

- Root và child rows được insert đúng.
- `order_id` trỏ về root ID.
- Update/remove child phản ánh đúng semantics của aggregate persistence.
- Delete root dọn children đúng quy tắc của Spring Data JDBC.
- Business constraints và khóa ngoại vẫn đúng với database engine.

Đừng giả định `save(root)` trên một aggregate phức tạp chỉ update duy nhất một SQL row; Spring Data JDBC có thể thực hiện nhiều statement cho children tùy mapping và thuật toán lưu.

### 12.2. Custom SQL với @Query

Trong ví dụ, `@Query` dùng named parameter. Với Spring Data JDBC, custom query phải cung cấp **đủ cột** nếu return là aggregate cần ánh xạ đầy đủ, đặc biệt các property dùng bởi constructor. Nếu thiếu cột, mapping có thể tạo object thiếu dữ liệu hoặc fail. Một test @DataJdbcTest nên có case đọc đầy đủ object thay vì chỉ assert count.

**Phân trang/sắp xếp:** không mặc định `@Query` có thể tự viết lại SQL tùy theo mọi `Pageable`/`Sort` như JPA. Với String-based SQL tùy chỉnh, bạn chịu trách nhiệm câu `ORDER BY`, `LIMIT/OFFSET` và cách bind parameters theo dialect. Test cả boundaries và deterministic order.

### 12.3. @Modifying và optimistic locking

Khi dùng `@Modifying` cùng SQL UPDATE/DELETE tự viết, cần kiểm tra số hàng bị ảnh hưởng và ảnh hưởng lên domain state. Một modifying query trực tiếp có thể không gọi entity callbacks/auditing như repository save, tùy API và phiên bản.

Nếu aggregate có `@Version` để optimistic locking, hãy kiểm tra hai lượt update trên các snapshot cũ, version tăng và expected failure khi phát hiện conflict. **Không kết luận optimistic locking đúng chỉ vì `save` trên một entity đơn lẻ thành công.**

### 12.4. Converter và database value types

Với `BigDecimal`, `Instant`, enum, JSON, UUID, custom value object hoặc embedded mapping, test nên kiểm tra cả hai chiều:

1. Java object → database column: đúng SQL type, precision/scale, nullability.
2. Database column → Java object: round-trip đúng ý nghĩa, không mất timezone/precision.

H2 hữu ích cho nhiều kiểu phổ biến, nhưng cần Testcontainers khi contract phụ thuộc database-native JSONB, arrays, timezone, collation, locks hoặc extensions.

### 12.5. Kiểm tra query có hiệu quả và an toàn

- Dùng **named parameters**/prepared statements thay vì nối SQL với input từ người dùng.
- Với repository tìm kiếm, test input có dấu nháy/Unicode nếu contract cho phép; không tự interpolation.
- Dùng `ORDER BY` khi cần assert thứ tự.
- Nếu performance/index quan trọng, benchmark/query plan cần test trên engine thật và dataset đại diện; H2 với 3 rows không thể kết luận production query đã dùng index.
- Không mở stream JDBC trả kết quả lớn rồi quên đóng connection. Với repository query trả `Stream<T>`, dùng try-with-resources theo Spring Data JDBC docs.

## 13. Java SE demo độc lập: rule thuần không cần @DataJdbcTest

Khi chỉ cần kiểm tra một **quy tắc Java thuần**, không cần Spring context hay DB. Để phân biệt với database constraint, thêm một class chỉ xác định nhãn stock:

Tạo `src/main/java/example/datajdbc/StockPolicy.java`:

```java
package example.datajdbc;

public final class StockPolicy {
    private StockPolicy() {
    }

    public static String label(int stock) {
        if (stock < 0) {
            throw new IllegalArgumentException(
                    "stock must not be negative");
        }
        return stock == 0 ? "OUT_OF_STOCK" : "IN_STOCK";
    }
}
```

Tạo `src/main/java/example/datajdbc/StockPolicyDemo.java`:

```java
package example.datajdbc;

public class StockPolicyDemo {
    public static void main(String[] args) {
        System.out.println(StockPolicy.label(4));
        System.out.println(StockPolicy.label(0));

        try {
            StockPolicy.label(-1);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+**, không cần Spring/JUnit/JDBC:

```bash
javac -d out src/main/java/example/datajdbc/StockPolicy.java src/main/java/example/datajdbc/StockPolicyDemo.java
java -cp out example.datajdbc.StockPolicyDemo
```

Stdout **chính xác**:

```text
IN_STOCK
OUT_OF_STOCK
stock must not be negative
```

JUnit unit test tương ứng:

Tạo `src/test/java/example/datajdbc/StockPolicyTest.java`:

```java
package example.datajdbc;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockPolicyTest {
    @Test
    void labelsStockWithoutDatabase() {
        assertEquals("IN_STOCK", StockPolicy.label(4));
        assertEquals("OUT_OF_STOCK", StockPolicy.label(0));
    }

    @Test
    void rejectsNegativeStockInPureJava() {
        assertThrows(IllegalArgumentException.class,
                () -> StockPolicy.label(-1));
    }
}
```

Chạy riêng:

```bash
./gradlew test --tests example.datajdbc.StockPolicyTest
```

Class này có **2 JUnit test methods**. Nó chỉ chứng minh logic Java, không chứng minh `CHECK (stock >= 0)` tồn tại trên DB. Test `negativeStockFailsCheckConstraint` ở `BookRepositoryTest` mới chứng minh database reject stock âm. Hai mức test bổ sung, **không thay thế nhau**.

## 14. @Sql, migration và dữ liệu thử nghiệm độc lập

### Khi nào dùng @Sql?

Dùng `@Sql` khi một repository query cần dataset có cấu trúc mà dựng bằng nhiều lần `repository.save` quá dài hoặc dễ gắn coupling với method khác. Ví dụ test phân trang hay uniqueness cần 100 rows có thể dùng fixture script.

**Quy tắc dữ liệu:**

- Seed data có ID/ISBN độc lập, không trùng test khác.
- Không dựa vào thứ tự chạy method.
- Từng test tự tạo/seed dữ liệu nó cần.
- Tránh dùng dữ liệu thật hoặc credential production.
- Chọn rollback mặc định hoặc cleanup rõ khi tắt transaction test.
- Nếu dùng cùng context và DB dưới parallel execution, phải cô lập schema/database hoặc điều phối test phù hợp.

### Không nhập nhằng schema.sql với migrations

Nếu dự án production dùng Flyway/Liquibase, tốt nhất kiểm tra migration pipeline ở ít nhất một test chạy engine phù hợp. Với unit/slice test H2 bạn có thể dùng test-only schema đơn giản để tăng tốc, nhưng phải nêu rõ đây là **test schema**, không phải bằng chứng migrations production đã đúng.

Nếu Spring Boot tự chạy cả `schema.sql` và Flyway migration cùng tạo bảng, test có thể fail “table already exists”. **Không giải quyết bằng cách vô hiệu hóa toàn bộ migration trong mọi test**, vì bạn sẽ không còn phát hiện schema drift. Hãy quyết định rõ test nào chỉ cần schema stub nhanh và test nào là migration integration.

### Không dùng @DirtiesContext để xóa dữ liệu một cách máy móc

Spring TestContext có thể cache ApplicationContext giữa các tests. `@DataJdbcTest` rollback giúp cô lập những DML nằm trong test transaction, nên **thường không cần rebuild context sau mỗi method**. `@DirtiesContext` gây chi phí startup, không thay thế việc quản lý dữ liệu nếu bạn đã commit dữ liệu ngoài test transaction.

### Nếu test có transaction riêng/REQUIRES_NEW

Một method production đánh dấu `@Transactional(propagation = REQUIRES_NEW)` có thể chạy transaction riêng và commit, kể cả test được rollback sau đó. Khi bạn thực sự kiểm tra orchestration/proxy này, dùng test context phù hợp và cleanup; không dựa vào rollback của test transaction như bảo đảm tuyệt đối mọi side effect đều biến mất.

## 15. Lỗi phổ biến khi dùng @DataJdbcTest

**1. Nhầm @DataJdbcTest với @DataJpaTest.** `@Table` của Spring Data Relational không giống `@Entity` của JPA; kiểm tra imports/starter.

**2. Test chỉ dùng @JdbcTest rồi kỳ vọng BookRepository có sẵn.** `@JdbcTest` tập trung JDBC, không tự auto-config Spring Data JDBC repositories như `@DataJdbcTest`.

**3. Không có schema.sql/migration.** Repository bean tồn tại nhưng `save` thất bại vì bảng chưa được tạo.

**4. Dùng H2 để chứng minh PostgreSQL-specific SQL.** Cần Testcontainers/dialect production khi rủi ro là engine behavior.

**5. Tưởng slice tải mọi @Service/@Component.** Không; thêm bean cần thiết bằng @Import/config rõ ràng hoặc dùng full-context test cho workflow nhiều layer.

**6. Mock chính repository rồi báo test SQL xanh.** Mock không chạy database. Giữ repository và datasource thật trong test cần kiểm tra SQL.

**7. Test dùng @Transactional rồi nói dữ liệu đã commit.** Cùng test transaction đọc thấy row **trước rollback** không phải bằng chứng commit.

**8. Dùng @Rollback(false) hoặc Propagation.NOT_SUPPORTED rồi không dọn DB.** Có thể để lại row, làm test sau fail uniqueness hoặc leak data.

**9. Dùng @Sql ở ISOLATED mode rồi tin rằng rollback test xóa seed.** Script có thể commit riêng, cần cleanup độc lập.

**10. Thêm custom @ComponentScan toàn ứng dụng để làm slice pass.** Làm test khởi động nhiều bean ngoài nhu cầu, giảm tốc độ và che cấu hình slice sai.

**11. Không có deterministic ORDER BY.** Test assert list theo thứ tự SQL không bảo đảm, dễ flaky.

**12. Dùng @Query nhưng thiếu cột cần map entity.** Constructor/property mapping có thể fail hoặc dữ liệu thiếu; test round-trip đầy đủ.

**13. Không dùng @Param cho named SQL parameter hoặc tên khác nhau.** Kiểm tra annotation `@Param("minimum")` khớp `:minimum`.

**14. Quên database constraints.** Test constructor Java ném exception không chứng minh `UNIQUE/CHECK/NOT NULL` đang hoạt động trong DB.

**15. So object trong memory sau save rồi kết luận persisted.** Đọc lại qua repository hoặc JdbcTemplate để xác nhận SQL side effect.

**16. Trộn Data JDBC và R2DBC.** JDBC blocking không trở thành reactive chỉ vì ứng dụng có WebFlux.

**17. Quên Docker/CI runtime cho Testcontainers.** Container không tạo được làm test fail trước assertion. Tách test container/engine-specific nếu CI chưa hỗ trợ.

**18. Dùng datasource test trỏ nhầm production khi Replace.NONE.** Phải có dedicated DB, an toàn với thao tác xóa/schema và không dùng secret production.

## 16. Checklist trước khi chốt QA

**Phạm vi:**

- Entity mapping dùng `org.springframework.data.relational.core.mapping.Table` và `org.springframework.data.annotation.Id` đúng không?
- Repository là Spring Data JDBC hay JPA/R2DBC? Đã chọn `@DataJdbcTest` đúng module?
- Test có cần service/controller thật không? Nếu có, liệu slice đã đủ?
- `@Import`/custom converters có thực sự là phần mapping cần kiểm tra?

**Dữ liệu và schema:**

- Có `schema.sql`/migration tạo bảng trước khi repository query không?
- Cột, type, nullable, identity, constraints và field mapping đúng không?
- Fixture test có deterministic order, seed độc lập và không phụ thuộc method khác không?
- Với aggregate children, FK/collection mapping có test cả insert/update/delete?
- Nếu dùng production-specific SQL, đã chạy test trên engine phù hợp chưa?

**Assertions:**

- Test có gọi repository proxy và thực sự thực thi SQL không, hay bị mock?
- Có kiểm tra generated ID, read-back, update, delete và derived query không?
- Có kiểm tra SQL tùy chỉnh cùng order/parameters đúng không?
- Có assert constraint ở database chứ không chỉ validation Java không?
- Có kết hợp JdbcTemplate để quan sát row/cột thật khi cần không?

**Transaction/CI:**

- Có hiểu mặc định rollback không? Đọc trong cùng transaction không chứng minh commit.
- Nếu tắt rollback, có cleanup và dedicated test DB không?
- Testcontainers `@ServiceConnection`/`Replace.NONE`/schema initialization có phù hợp version Boot?
- Không đưa database credentials/production data vào fixture hoặc test logs?
- Bộ test chạy độc lập theo thứ tự bất kỳ và không bị ảnh hưởng bởi test song song?
- Test H2 xanh có được báo cáo **đúng phạm vi H2**, không phóng đại sang production?

**Kết luận:** `@DataJdbcTest` là công cụ hiệu quả để **kiểm tra Spring Data JDBC repositories trên database thật của test** mà không kéo theo toàn bộ ứng dụng. Nó khác `@JdbcTest` ở repository auto-configuration, khác `@DataJpaTest` ở cơ chế ORM, và khác `@SpringBootTest` ở phạm vi context. Dùng H2 cho feedback nhanh, `@Sql`/transaction rollback cho test độc lập, `JdbcTemplate` để kiểm tra side effect SQL; thêm Testcontainers khi cần bảo vệ dialect và constraints của database production.

## 17. Tài liệu tham khảo

- [Spring Boot 3.5 — @DataJdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html): phạm vi test slice, embedded DB, transaction và rollback.
- [Spring Boot — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @DataJdbcTest/@JdbcTest/@DataJpaTest và test database replacement.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries, @Query/@Param, mapping và giới hạn SQL.
- [Spring Data JDBC — Object Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): @Table/@Id, property access, aggregate mapping.
- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection, container lifecycle và connection details.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, @Transactional, TestTransaction, @Sql semantics.
