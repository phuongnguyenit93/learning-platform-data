# @DataJpaTest và thành phần persistence được tự cấu hình trong Spring Boot

## 1. Mục tiêu: kiểm thử tầng JPA thật, không kéo cả ứng dụng vào test

Một ứng dụng Spring Boot thường có chuỗi phụ thuộc `Controller → Service → Repository → EntityManager → DataSource → Database`. Nếu câu hỏi của test là **“entity mapping, Spring Data JPA repository, JPQL và ràng buộc database có đúng không?”**, việc nạp controller, HTTP server, security filters và các client bên ngoài thường không cần thiết.

`@DataJpaTest` là một **test slice** của Spring Boot, tập trung vào phần persistence sử dụng **Spring Data JPA**. Thay vì khởi động toàn bộ `ApplicationContext`, nó ưu tiên nạp entity và JPA repositories, đồng thời bật những auto-configuration cần cho persistence (JPA provider, `EntityManagerFactory`, `DataSource`, transaction support, test database, `TestEntityManager` và một số công cụ JDBC/schema tùy classpath).

Ví dụ các lỗi mà slice test này nên phát hiện:

- `@Column` hoặc `@JoinColumn` khai báo sai so với schema.
- Repository method name không ánh xạ được thành query hợp lệ.
- `@Query` dùng tên entity/property hoặc tham số JPQL sai.
- Quan hệ `@OneToMany`/`@ManyToOne`, fetch strategy, cascade hoặc orphan removal cho kết quả không mong đợi.
- Ràng buộc `UNIQUE`, `NOT NULL` hoặc foreign key phát lỗi khi SQL được thực thi.
- Trạng thái entity trong persistence context che khuất lỗi ghi/đọc dữ liệu thật.
- Query trên database test trả kết quả khác điều nghiệp vụ mong đợi.

**Không nên kết luận từ một `@DataJpaTest` xanh rằng HTTP API, `@Service` nghiệp vụ, Spring Security, transaction boundary của một service hay hệ thống production đã được kiểm chứng.** Những tầng đó thường không thuộc context của JPA slice.

## 2. Cơ chế @DataJpaTest và phạm vi bean

Trong **Spring Boot 3.5 / Spring Framework 6.x**, annotation này được import bằng:

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
```

Khai báo tối giản:

```java
@DataJpaTest
class BookRepositoryTest {
    // @Autowired BookRepository repository;
}
```

Đây là mẫu cú pháp; lớp repository/entity sẽ được định nghĩa đầy đủ ở mục 5. `@DataJpaTest` đã tích hợp Spring TestContext với JUnit Jupiter nên thông thường **không cần viết thêm `@ExtendWith(SpringExtension.class)`**.

Khi tạo context, Spring Boot áp dụng bộ lọc để **giới hạn component scan**, đồng thời chỉ bật những auto-configuration phù hợp với Data JPA. Khái quát:

```text
JUnit Jupiter
    |
    v
Spring TestContext + @DataJpaTest bootstrapper
    |
    +---- @Entity classes
    +---- Spring Data JpaRepository interfaces
    +---- EntityManagerFactory / Hibernate JPA
    +---- DataSource / JDBC driver / connection pool
    +---- JPA transaction manager
    +---- Test database auto-configuration
    +---- TestEntityManager (test helper)
    +---- JdbcTemplate (nếu hạ tầng JDBC thích hợp)
    +---- SQL initialization / Flyway / Liquibase (nếu có cấu hình)
    |
    +---- THƯỜNG KHÔNG nạp:
             @RestController, @Service nghiệp vụ,
             scheduler, message listener, HTTP clients tùy biến,
             đa số @Component / @ConfigurationProperties thông thường
```

Đây là sơ đồ về **loại thành phần được phép cấu hình**, không phải cam kết mọi bean đều xuất hiện trong mọi dự án. Classpath, dependency, entity scan, application config, các `@Import` và `@AutoConfigure...` bổ sung vẫn quyết định context thực tế.

### 2.1. Những thành phần persistence chính

| Thành phần | Vai trò | Điều có thể kiểm chứng |
|---|---|---|
| `@Entity` của Jakarta Persistence | Mapping class/field/association vào bảng, cột | DDL, insert/read, quan hệ và constraint |
| `JpaRepository<T,ID>` | Repository proxy do Spring Data tạo | `save`, `findById`, derived query, JPQL |
| `EntityManagerFactory` | Tạo persistence context; cấu hình provider | Metadata và mapping JPA |
| `EntityManager` | Theo dõi entity managed, `persist`, `flush`, `clear` | Dirty checking, SQL flush, query |
| `TestEntityManager` | Helper của Spring Boot test cho JPA | Tạo fixture nhanh, `persistAndFlush`, `persistFlushFind` |
| `DataSource` | Cấp kết nối JDBC | Kết nối tới H2/Testcontainers/DB đã chọn |
| `PlatformTransactionManager` | Quản lý transaction | Test-managed rollback và repository transaction |
| `JdbcTemplate` | Gửi SQL JDBC trực tiếp khi cần | Kiểm tra row/column thật, không phụ thuộc ORM cache |
| `TestDatabaseAutoConfiguration` | Cấu hình datasource thử nghiệm | Embedded DB hoặc giữ database test đã khai báo |
| Flyway/Liquibase | Migration theo cấu hình/classpath | Có thể chạy schema migration trong slice nếu phù hợp |

Trong Boot 3.5, danh sách auto-configuration thường có `JpaRepositoriesAutoConfiguration`, `HibernateJpaAutoConfiguration`, `DataSourceAutoConfiguration`, `TransactionAutoConfiguration`, `TestDatabaseAutoConfiguration` và `TestEntityManagerAutoConfiguration`, cùng một số cấu hình JDBC/SQL/migration tùy điều kiện.

**Không phải `@DataJpaTest` tạo thêm một database server thật.** Nếu thư viện embedded database như H2, HSQLDB hoặc Derby có trên classpath và được chọn, Boot có thể dùng database nằm trong process. Nếu muốn PostgreSQL/MySQL thật, cần kết nối tới database test hoặc container riêng.

### 2.2. Những thành phần thường bị loại khỏi slice

Một lớp `@Service` bình thường, kể cả nếu constructor nhận `BookRepository`, thường **không được quét tự động**. Tương tự, một `@RestController` cần service, một scheduler, custom HTTP client hoặc một Kafka listener không tự nhiên xuất hiện chỉ vì có `@DataJpaTest`.

Điều này giải thích lỗi `NoSuchBeanDefinitionException` khi cố `@Autowired BookService` trong JPA slice. Nếu mục tiêu chỉ kiểm tra repository, hãy inject repository thật trực tiếp. Nếu cần một converter/mapping component hỗ trợ JPA, có thể `@Import` **đúng bean phụ trợ** theo yêu cầu; nếu thực sự muốn kiểm tra service nghiệp vụ qua nhiều tầng, nên viết test khác có phạm vi thích hợp.

Một ngoại lệ quan trọng: application class dùng `@ComponentScan` tùy biến có thể làm vô hiệu hóa bộ lọc slice mặc định, khiến nhiều bean ngoài persistence bất ngờ được quét. Khi đó cần xem cấu hình scan; không nên chữa bằng cách thêm mock vô hạn cho mọi service của ứng dụng.

## 3. Transaction mặc định và rollback của JPA slice

`@DataJpaTest` được đánh dấu transactional: mỗi test method thông thường chạy **trong test-managed transaction**, và Spring TestContext **rollback** khi test kết thúc. Điều này giúp hạn chế dữ liệu thừa giữa các test.

```text
@BeforeEach / test method (trong transaction của test)
    |
    +-- repository.save(entity)
    +-- entityManager.flush()
    +-- repository.findBy...
    +-- assertions
    |
Spring TestContext: rollback test transaction
    |
    v
Thay đổi đã tham gia transaction đó không được commit
```

Điểm cần nhớ:

1. `repository.save(...)` **không tương đương commit**. JPA có thể trì hoãn SQL đến `flush`, hoặc thực thi INSERT sớm tùy chiến lược ID và provider.
2. `flush()` đẩy thay đổi pending từ persistence context tới database trong transaction, nhưng **không commit**.
3. `clear()` tách các managed entities khỏi persistence context; một lần đọc sau `clear` giúp giảm false positive do **first-level cache**.
4. Một test có transaction sẵn có thể che việc một service production thiếu `@Transactional`; test repository **không tự kiểm chứng** transaction boundary bên ngoài.
5. Nếu test mở một transaction mới `REQUIRES_NEW`, gọi API qua HTTP thread khác hoặc phát side effect ra hệ thống ngoài, rollback của test **không tự xóa** tất cả kết quả đó.
6. Có thể đổi cách kết thúc test transaction bằng `@Commit`, `@Rollback(false)` hoặc `TestTransaction`, nhưng phải hiểu dữ liệu đã commit có thể làm nhiễm test khác.

Đừng áp dụng `@DirtiesContext` cho mọi test chỉ để dọn record: nó loại context khỏi cache, tăng chi phí khởi tạo, nhưng **không phải công cụ xóa những hàng đã commit trong database dùng chung**.

## 4. Một ví dụ Java 17+ đầy đủ: BookRepository, Hibernate, H2

Ví dụ sử dụng **Spring Boot 3.5.x**, Java 17+, Spring Data JPA, Hibernate, H2, Spring Boot Test/JUnit Jupiter. Mục tiêu là kiểm tra **SQL/database thật trong một persistence slice**, không dùng Mockito để giả lập repository.

### 4.1. Cấu trúc thư mục

```text
build.gradle
src/main/java/com/example/jpaslice/
    BooksApplication.java
    Book.java
    BookRepository.java
    BookCatalogService.java
src/test/java/com/example/jpaslice/
    BookRepositoryTest.java
```

### 4.2. Gradle build file tối thiểu

Tệp `build.gradle` (Groovy DSL; chọn một phiên bản patch Boot 3.5.x có trong môi trường):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dự án cần Gradle/JDK tương thích với Spring Boot 3.5 plugin và kết nối tới repository artifact. Nếu đang dùng Maven, cần `spring-boot-starter-parent` hoặc Spring Boot BOM phù hợp và các dependency tương đương.

`spring-boot-starter-data-jpa` cung cấp JPA/Hibernate và Spring Data; H2 cung cấp embedded database cho test. `spring-boot-starter-test` cung cấp JUnit Jupiter/AssertJ/Spring test support. `TestEntityManager` được tạo bởi `@DataJpaTest` theo auto-config tương ứng.

**Lưu ý:** Đặt `runtimeOnly 'com.h2database:h2'` nghĩa là H2 cũng ở runtime classpath của ứng dụng demo. Trong dự án production cần PostgreSQL/MySQL, có thể chỉ đưa H2 vào `testRuntimeOnly` và khai báo driver production đúng; đừng để ứng dụng production vô tình kết nối H2 chỉ vì test đang xanh.

### 4.3. Spring Boot application class

Tệp `src/main/java/com/example/jpaslice/BooksApplication.java`:

```java
package com.example.jpaslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(BooksApplication.class, args);
    }
}
```

Lớp `@SpringBootApplication` nằm ở package cha để Spring Boot tìm entity/repository khi test bootstrap. Mặc dù có application class, `@DataJpaTest` **vẫn chọn JPA slice**, không khởi động toàn bộ application hay HTTP server.

### 4.4. JPA entity có ràng buộc UNIQUE

Tệp `src/main/java/com/example/jpaslice/Book.java`:

```java
package com.example.jpaslice;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "library_books",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_library_books_isbn",
                columnNames = "isbn"))
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 40)
    private String isbn;

    @Column(nullable = false, length = 200)
    private String title;

    protected Book() {
        // Constructor cho JPA provider.
    }

    public Book(String isbn, String title) {
        this.isbn = Objects.requireNonNull(isbn, "isbn");
        this.title = Objects.requireNonNull(title, "title");
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

    public void rename(String newTitle) {
        this.title = Objects.requireNonNull(newTitle, "newTitle");
    }
}
```

Các chi tiết có ý nghĩa:
- `@Entity` đưa lớp vào JPA entity scan.
- `@Id`, `@GeneratedValue(IDENTITY)` khai báo primary key `Long` được database/provider sinh.
- `@Table(name="library_books")` đặt tên bảng tường minh; không dựa hoàn toàn vào implicit naming.
- `UniqueConstraint` yêu cầu ISBN không được trùng ở mức schema (khi DDL/migration đã tạo constraint).
- `@Column(nullable=false)` khai báo ràng buộc mapping/schema; nó **không tự thay thế Bean Validation** cho input HTTP.
- `rename` thay đổi entity **managed**, là tình huống tốt để kiểm tra dirty checking.

Không áp dụng entity này trực tiếp làm HTTP response trong ứng dụng thật nếu có field nội bộ hoặc lazy associations. Phạm vi ở đây là persistence.

### 4.5. Spring Data JPA repository thật

Tệp `src/main/java/com/example/jpaslice/BookRepository.java`:

```java
package com.example.jpaslice;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    long countByIsbn(String isbn);

    List<Book> findByTitleContainingIgnoreCaseOrderByTitleAsc(
            String fragment);

    @Query("""
            select b from Book b
            where b.isbn like concat(:prefix, '%')
            order by b.isbn asc
            """)
    List<Book> findIsbnStartingWith(
            @Param("prefix") String prefix);
}
```

Spring Data JPA tạo repository implementation/proxy theo cấu hình context; trong test ta inject **repository thật**, không tạo Mockito mock. Các derived query được phân tích từ method name, `@Query` dùng JPQL (tên entity/property Java, không phải SQL table name).

**Phân biệt:** `Book` là tên entity class, `isbn` là thuộc tính Java. Trong JPQL `select b from Book b`; còn khi dùng native SQL, tên bảng ở ví dụ là `library_books`.

### 4.6. Service bình thường — cố ý không thuộc slice

Tệp `src/main/java/com/example/jpaslice/BookCatalogService.java`:

```java
package com.example.jpaslice;

import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {

    private final BookRepository repository;

    public BookCatalogService(BookRepository repository) {
        this.repository = repository;
    }

    public long countAllBooks() {
        return repository.count();
    }
}
```

Lớp này tồn tại để chứng minh giới hạn **component scan**: repository là bean trong JPA slice; service `@Service` bình thường thì **không tự được nạp**. Test ở bước sau sẽ xác nhận thực tế đó qua `ApplicationContext`.

### 4.7. Bộ JUnit test hoàn chỉnh

Tệp `src/test/java/com/example/jpaslice/BookRepositoryTest.java`:

```java
package com.example.jpaslice;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.ApplicationContext;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class BookRepositoryTest {

    @Autowired
    BookRepository books;

    @Autowired
    TestEntityManager entities;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @Autowired
    ApplicationContext context;

    @Test
    void usesEmbeddedH2DatabaseInThisTestSetup() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void savesAndReadsAfterClearingPersistenceContext() {
        Book saved = books.saveAndFlush(
                new Book("ISBN-100", "JPA Fundamentals"));
        assertNotNull(saved.getId());

        // Tránh tự nhận lại entity managed từ first-level cache.
        entities.clear();

        Book read = books.findById(saved.getId()).orElseThrow();
        assertEquals("ISBN-100", read.getIsbn());
        assertEquals("JPA Fundamentals", read.getTitle());

        Integer rows = jdbc.queryForObject(
                "select count(*) from library_books where isbn = ?",
                Integer.class,
                "ISBN-100");
        assertNotNull(rows);
        assertEquals(1, rows.intValue());
    }

    @Test
    void derivedQueryFiltersAndSorts() {
        entities.persist(new Book("ISBN-101", "Spring Data"));
        entities.persist(new Book("ISBN-102", "Postgres Guide"));
        entities.persist(new Book("ISBN-103", "Spring AOP"));
        entities.flush();
        entities.clear();

        List<String> titles = books
                .findByTitleContainingIgnoreCaseOrderByTitleAsc("SPRING")
                .stream()
                .map(Book::getTitle)
                .toList();

        assertEquals(
                List.of("Spring AOP", "Spring Data"),
                titles);
    }

    @Test
    void explicitJpqlQueryUsesEntityProperties() {
        entities.persist(new Book("ISBN-200", "One"));
        entities.persist(new Book("ISBN-201", "Two"));
        entities.persist(new Book("CODE-999", "Other"));
        entities.flush();
        entities.clear();

        List<String> isbn = books.findIsbnStartingWith("ISBN-")
                .stream()
                .map(Book::getIsbn)
                .toList();

        assertEquals(
                List.of("ISBN-200", "ISBN-201"), isbn);
    }

    @Test
    void dirtyCheckingUpdatesManagedEntityAfterFlush() {
        Book created = entities.persistAndFlush(
                new Book("ISBN-301", "First Title"));
        Long id = created.getId();
        assertNotNull(id);
        entities.clear();

        Book managed = books.findById(id).orElseThrow();
        managed.rename("Updated Title");

        // Không gọi books.save(managed):
        // JPA nhận thay đổi trên managed entity khi flush.
        entities.flush();
        entities.clear();

        Book reloaded = books.findById(id).orElseThrow();
        assertEquals("Updated Title", reloaded.getTitle());
    }

    @Test
    void databaseRejectsDuplicateIsbnOnFlush() {
        books.saveAndFlush(new Book("ISBN-DUP", "First Book"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> books.saveAndFlush(
                        new Book("ISBN-DUP", "Second Book")));

        // Không tiếp tục query sau khi SQL constraint violation:
        // transaction đã có thể bị đánh dấu rollback-only.
    }

    @Test
    void ordinaryServiceIsNotAutoScannedByJpaSlice() {
        assertTrue(
                context.getBeansOfType(BookCatalogService.class).isEmpty());
        assertFalse(context.getBeansOfType(
                BookRepository.class).isEmpty());
    }
}
```

### 4.8. Đọc kết quả đúng phạm vi

| Test method | Chứng minh được | Chưa chứng minh |
|---|---|---|
| `usesEmbeddedH2DatabaseInThisTestSetup` | DataSource đang chỉ đến H2 trong cấu hình mẫu | Production cũng chạy trên H2 |
| `savesAndReadsAfterClearingPersistenceContext` | INSERT/query thật và đường JDBC nhìn thấy row sau flush | Transaction đã commit và được client ngoài đọc |
| `derivedQueryFiltersAndSorts` | Repository derived query, case-insensitive filter và sort trong H2 | PostgreSQL collation hoàn toàn giống H2 |
| `explicitJpqlQueryUsesEntityProperties` | JPQL được parse/chạy, prefix filter và ordering đúng dữ liệu mẫu | JPQL đã được thử với mọi volume/plan production |
| `dirtyCheckingUpdatesManagedEntityAfterFlush` | Hibernate dirty checking hoạt động với managed entity | Entity detached cũng tự được cập nhật |
| `databaseRejectsDuplicateIsbnOnFlush` | H2 schema có unique constraint và lỗi được translate qua repository | Mọi database dialect đều sinh/translate cùng exception |
| `ordinaryServiceIsNotAutoScannedByJpaSlice` | Context đã chọn repository nhưng không quét service thường | Không có bất kỳ component tùy biến nào trong mọi @DataJpaTest |

**Test 2 sử dụng cả `books.findById` sau `clear` và SQL qua `JdbcTemplate`** để quan sát dữ liệu đã flush. Nếu chỉ viết `assertEquals(saved, books.findById(id).orElseThrow())` mà không xóa persistence context, Hibernate có thể trả cùng managed object từ cache cấp một, làm test thiếu sức mạnh phát hiện lỗi mapping/SQL.

Ví dụ dùng `DataIntegrityViolationException` trong môi trường Spring Data JPA/Hibernate/H2. Trên JPA provider hoặc driver khác, thời điểm exception hoặc cách translate có thể khác; test ở đây có **phạm vi công bố rõ** là cấu hình mẫu Boot 3.5/Hibernate/H2.

Lớp trên có bảy `@Test`, không có `System.out.println` hay output console cố định. Chỉ tuyên bố các ca **thực tế PASS** sau khi chạy Gradle/Maven và xem report; đoạn mã tự nó không phải kết quả chạy.

## 5. Chạy test đúng cách

Với Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.jpaslice.BookRepositoryTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jpaslice.BookRepositoryTest"
```

Nếu dự án có Maven wrapper tương ứng:

```bash
./mvnw -Dtest=BookRepositoryTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=BookRepositoryTest test
```

Lệnh giả định dự án đã có wrapper, JDK 17+, dependencies test và runner JUnit Platform phù hợp. Nếu project đa module, phải chạy task/module chứa code mẫu; nếu không có wrapper, có thể dùng Gradle/Maven được cài sẵn với version tương thích.

Kiểm tra đúng kết quả trong `build/reports/tests/test/index.html` (Gradle) hoặc `target/surefire-reports/` (Maven). Với ví dụ, báo cáo nên liệt kê bảy test được phát hiện; nếu build chỉ báo `UP-TO-DATE`, `NO-SOURCE` hoặc `SKIPPED`, cần kiểm tra lại trước khi ghi nhận bài test đã được thực thi mới.

## 6. TestEntityManager, EntityManager và JdbcTemplate khác nhau thế nào?

`TestEntityManager` là helper do Spring Boot cung cấp trong JPA test, **không phải một JPA provider mới** và không thay thế `EntityManager` trong production. Nó cung cấp một số thao tác tiện:

```java
Book saved = entities.persistAndFlush(
        new Book("ISBN-A", "A"));
Long id = saved.getId();

entities.clear();
Book loaded = entities.find(Book.class, id);
```

Đây là đoạn minh họa bên trong test có `entities` đã inject; thực tế có thể chọn `persistFlushFind` để thực hiện persist + flush + find gọn hơn.

| API | Tác dụng | Cần cẩn thận |
|---|---|---|
| `entities.persist(entity)` | Đưa entity vào persistence context | SQL có thể chưa flush/commit |
| `entities.persistAndFlush(entity)` | Persist rồi flush | Flush **không phải commit** |
| `entities.persistFlushFind(entity)` | Persist + flush + find theo ID | Không bảo đảm lần find độc lập với first-level cache như một `clear()` trước đó |
| `entities.clear()` | Xóa managed entities khỏi persistence context | Thay đổi chưa flush có thể mất |
| `entities.getEntityManager()` | Lấy JPA EntityManager thật | Giao dịch và lifecycle vẫn do context quản lý |
| `books.saveAndFlush(entity)` | Lưu qua repository rồi flush | Không cam kết transaction commit |
| `jdbc.queryForObject(sql, ...)` | Đọc database qua JDBC | Không đi qua ORM entity cache, nhưng vẫn có thể tham gia **cùng transaction** |

Đừng dùng `persistFlushFind` rồi khẳng định nó **chắc chắn** buộc một SELECT vật lý từ database sau khi persistence context đã được xóa; API đó không tự biểu đạt thao tác `clear`. Khi mục tiêu là kiểm chứng SQL đọc trở lại, dùng chuỗi `flush → clear → find` rõ ràng.

### 6.1. Vì sao flush sớm quan trọng với constraint?

Trong JPA, `save` đôi khi chưa phát toàn bộ SQL ngay. Nếu test dùng:

```java
Book saved = books.save(
        new Book("ISBN-EX", "Title"));
assertNotNull(saved);
```

test có thể pass mà constraint lỗi chỉ phát hiện **sau khi test method kết thúc** hoặc trong một thời điểm flush khác. Đặc biệt với unique/foreign key constraints, nên thực hiện `saveAndFlush` hoặc `EntityManager.flush` tại điểm bạn muốn assert failure.

Tuy nhiên, với `GenerationType.IDENTITY`, một INSERT có thể diễn ra **ngay khi persist** để lấy generated ID; đừng assert chính xác “SQL chỉ xuất hiện khi gọi flush” cho mọi entity/provider. Ý nghĩa của `flush` là yêu cầu đồng bộ pending persistence actions, không phải lời hứa rằng nó là câu SQL đầu tiên.

### 6.2. Vì sao test rollback vẫn nhìn thấy dữ liệu trong cùng transaction?

Vì Spring test transaction đang active, code bên trong transaction có thể đọc những row mà nó vừa insert/flush, dù chúng **chưa commit cho connection độc lập**. Do đó:

```java
assertEquals(1L, books.countByIsbn("ISBN-100"));
```

trong cùng test chứng minh repository query nhìn thấy dữ liệu thuộc transaction hiện tại; nó không chứng minh một request HTTP bên ngoài có thể đọc được trước commit. Muốn test visibility/isolation/commit thật, thiết kế **đường đọc ở transaction/connection khác** và kiểm soát transaction boundary chủ động.

## 7. Embedded database và @AutoConfigureTestDatabase

`@DataJpaTest` thường có cơ chế **test database auto-configuration**. Ở Boot 3.5, default `AutoConfigureTestDatabase.Replace` là **`NON_TEST`**: một DataSource bình thường có thể bị thay bằng embedded test database, trong khi một số kết nối được nhận diện là **test database** (ví dụ Testcontainers service connection hoặc `spring.datasource.url` từ `@DynamicPropertySource`) có thể được giữ.

Không nên đơn giản hóa thành câu “`@DataJpaTest` luôn thay mọi DataSource bằng H2”. Việc thay thế phụ thuộc **annotation, connection, classpath và dữ liệu nguồn**; nếu không có embedded driver hoặc cấu hình DB hợp lệ, context có thể không khởi động.

### 7.1. Những chế độ replace phổ biến

Trong Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
```

Đoạn minh họa đặt trên test class, **không phải file Java độc lập**.

| Replace mode | Ý nghĩa |
|---|---|
| `ANY` | Thay DataSource hiện có bằng test database khi có thể, kể cả datasource do user khai báo |
| `AUTO_CONFIGURED` | Chỉ thay DataSource được Boot auto-configure |
| `NON_TEST` | Default của Boot 3.5; không thay các datasource được nhận diện là test database |
| `NONE` | Giữ datasource đã cấu hình, không thay bằng embedded DB theo test database auto-config |

**Dùng `NONE` khi thật sự muốn kết nối Testcontainers PostgreSQL hoặc database test đã chỉ định.** Nhưng `NONE` **không tự khởi động container, không tạo schema và không biến URL production thành an toàn**. Phải chắc chắn cấu hình đang trỏ tới DB test cô lập, đặc biệt khi test có khả năng xóa/ghi dữ liệu.

### 7.2. Điều gì xảy ra nếu H2 có trên classpath?

Trong ví dụ mục 4, H2 có trên classpath và ta không cung cấp PostgreSQL test URL nên context sẽ dùng H2. Có thể kiểm chứng database product name từ `DataSource.getConnection().getMetaData()`, thay vì chỉ dựa vào một dòng log nói “embedded”.

**H2 không phải PostgreSQL/MySQL/Oracle.** Những điểm có thể khác:
- SQL dialect, reserved words và syntax của native queries.
- JSON/JSONB, array types, generated columns, upsert hoặc partial indexes.
- Identity/sequence behavior.
- Collation, `ILIKE`, case sensitivity và order của Unicode.
- Transaction isolation, lock timing, deadlocks và constraint semantics.
- Tính tương thích của migration SQL từ Flyway/Liquibase.

Vì thế, JPA slice + H2 phù hợp kiểm tra nhanh **entity mapping/query tổng quát**, nhưng chưa đủ cho những tính năng database phụ thuộc dialect.

## 8. Khi cần database production-like: @DataJpaTest với Testcontainers

Một cách giữ test slice gọn mà vẫn kiểm tra **PostgreSQL thực** là dùng Testcontainers. Cách này cần Docker/container runtime và PostgreSQL JDBC driver, nên không phù hợp môi trường không có quyền chạy container.

### 8.1. Dependency cho Testcontainers

Trong cùng dự án Spring Boot 3.5, bổ sung các dòng tương thích với Boot BOM:

```groovy
dependencies {
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Đây là **phần bổ sung** vào `dependencies` của build ở mục 4, không phải một build file thay thế. Để giữ ứng dụng production dùng PostgreSQL, đưa driver vào runtime phù hợp; để H2 chỉ xuất hiện ở test, có thể đưa H2 vào `testRuntimeOnly`.

### 8.2. Một lớp test sử dụng PostgreSQL container

Tệp `src/test/java/com/example/jpaslice/BookRepositoryPostgresTest.java`:

```java
package com.example.jpaslice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("books_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    BookRepository books;

    @Test
    void repositoryStoresDataInRealPostgres() {
        Book persisted = books.saveAndFlush(
                new Book("PG-100", "PostgreSQL Mapping"));

        assertNotNull(persisted.getId());
        assertEquals(
                1L, books.countByIsbn("PG-100"));
    }
}
```

Trong cấu hình này:
- JUnit/Testcontainers extension quản lý vòng đời static container.
- `@DynamicPropertySource` cung cấp JDBC URL/username/password từ container khi Spring tạo datasource. URL thực chứa host và mapped port phù hợp; không hard-code `localhost:5432`.
- `@AutoConfigureTestDatabase(replace=NONE)` ngăn Spring thay container datasource bằng H2.
- `@DataJpaTest` vẫn chỉ nạp JPA slice, không khởi động HTTP server hay business services.
- `ddl-auto=create-drop` tạo schema từ entity mapping cho bài test minh họa. **Không dùng cách này trên database chia sẻ/production**, và không coi đây là test xác minh migration scripts.
- Test vẫn **rollback theo test-managed transaction**; query count trong chính transaction đó không chứng minh dữ liệu đã commit ngoài test.

Trong Spring Boot hỗ trợ `@ServiceConnection` và `spring-boot-testcontainers`, có thể thay đăng ký JDBC properties thủ công bằng Boot service connection khi image/connection type được nhận diện. Chọn **một cách cấu hình** có chủ đích; không đăng ký cùng một datasource từ nhiều nguồn mà không kiểm tra thứ tự ưu tiên.

**Context cache và container lifecycle:** nếu context được cache nhưng static container của một lớp khác đã dừng, datasource có thể trỏ tới port cũ. Khi chia sẻ resource nhiều test classes, thiết kế container lifetime tương ứng hoặc điều khiển context cleanup rõ ràng; đừng dùng static mutable URL một cách vô tội vạ.

## 9. Migration và schema: Hibernate DDL khác Flyway/Liquibase

Ví dụ H2 và Testcontainers ở trên dùng:

```properties = "spring.jpa.hibernate.ddl-auto=create-drop"
```

Cấu hình đó nói Hibernate **tạo và xóa schema từ entity mapping** trong vòng đời context. Nó phù hợp khi bài học tập trung vào JPA mapping, nhưng **không xác minh** file migration SQL mà production sử dụng.

Nếu ứng dụng dùng Flyway hoặc Liquibase:
1. Đặt migration vào đường dẫn dự án được công cụ nạp, ví dụ `db/migration` của Flyway.
2. Dùng cùng database dialect như production khi migration có SQL đặc thù.
3. Để migration tạo schema test; cân nhắc `spring.jpa.hibernate.ddl-auto=validate` để Hibernate kiểm tra entity mapping so với schema đã migrate.
4. Kiểm tra auto-configuration migration có được bật trong JPA slice và datasource đã đúng chưa; đừng assume migration luôn chạy chỉ vì artifact tồn tại.
5. Assert dữ liệu/schema sau migration, nhất là index, unique constraint, column length và default values.

**Tránh vừa Hibernate `create-drop` vừa kỳ vọng migrations sẽ là nguồn schema duy nhất.** Dùng một chủ sở hữu schema rõ ràng; nếu migration đã chạy, Hibernate có thể cần validate thay vì recreate.

### 9.1. @Sql để tạo fixture và cleanup

Spring TestContext hỗ trợ `@Sql` để chạy SQL trước/sau test. Ví dụ mẫu:

```java
@Sql(
    scripts = "/sql/books-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Test
void readsMigrationFixture() {
    // repository query...
}
```

Đây là **đoạn minh họa**, yêu cầu import `org.springframework.test.context.jdbc.Sql` và một file script thật. Nếu chạy cùng test-managed transaction của `@DataJpaTest`, SQL fixture có thể **bị rollback cuối test**. Nếu cấu hình `ISOLATED` hoặc commit ra DB dùng chung, cleanup cần được thiết kế tường minh; không để dữ liệu shared làm test phụ thuộc thứ tự.

Không đưa `schema.sql`, Flyway scripts và Hibernate `ddl-auto=create` đồng thời vào test chỉ để “chắc chắn có bảng”; chúng có thể tranh chấp việc tạo schema và khiến lỗi khó chẩn đoán.

## 10. First-level cache và false positives trong persistence tests

JPA `EntityManager` giữ một **persistence context**; các entity đã load/managed có thể được trả lại từ first-level cache theo identity. Vì vậy:

```java
Book book = books.save(new Book("X-1", "Saved"));
assertEquals("Saved", books.findById(book.getId())
                          .orElseThrow().getTitle());
```

Đây là đoạn minh họa. Nó giúp kiểm tra một phần đường repository nhưng **có thể chưa chứng minh dữ liệu đã được đọc từ SQL**: entity đang managed và find theo ID có thể quay lại cùng instance.

Cách mạnh hơn:

```java
Book book = books.saveAndFlush(
        new Book("X-2", "Saved"));
Long id = book.getId();

entities.clear();

Book fromDatabase = books.findById(id).orElseThrow();
assertEquals("Saved", fromDatabase.getTitle());
```

Khi kết hợp với `JdbcTemplate` kiểm tra row, test có thêm một quan sát không qua JPA entity cache. Tuy nhiên, việc dùng cùng transaction vẫn **không** chứng minh commit đã xảy ra.

### 10.1. N+1 queries và lazy loading

Trong `@DataJpaTest` mỗi test thường có transaction active, nên một lazy association có thể được truy cập hợp lệ trong test, dù production code truy cập ngoài transaction sẽ bị `LazyInitializationException`. Tình trạng đó khiến test “tất cả xanh” nhưng API thật lỗi.

Để kiểm tra lazy loading/fetch graph:
- Khai báo rõ nơi cần fetch bằng `JOIN FETCH`, `@EntityGraph` hoặc DTO projection phù hợp.
- `flush`/`clear`, load entity bằng query mục tiêu và quan sát SQL count hoặc Hibernate statistics nếu cần kiểm soát N+1.
- Tách test đo query count/transaction boundary khỏi những test đơn giản về mapping.
- Không gọi trực tiếp lazy collection trong test transaction rồi kết luận controller serialize thành JSON ngoài transaction chắc chắn an toàn.

N+1 là vấn đề hiệu năng và SQL shape, không phải chỉ là vấn đề object equality. Một test dựa vào đúng dữ liệu nhưng không quan sát SQL có thể bỏ sót hàng trăm query trong production.

## 11. @DataJpaTest có kiểm tra transaction commit/rollback của service không?

**Không tự động.** Service thường bị lọc ra khỏi JPA slice. Khi test muốn bảo vệ một use case như “tạo Order và OrderLine phải atomic”, cần xác định **transaction boundary đặt ở lớp nào**:

- Repository test: kiểm tra JPA mapping, query, constraint.
- Service transaction test: giữ service thật và transaction manager thật, thường dùng `@SpringBootTest` hoặc context test cấu hình đầy đủ phần cần kiểm tra.
- HTTP integration test: gọi qua server thật; server thread thường có transaction **riêng**, không mượn test transaction từ client thread.

Trong test service, nếu chính test method `@Transactional`, một service không được annotate vẫn có thể chạy trong transaction đã được test framework tạo. Điều này làm giảm sức mạnh của assertion “transaction đang active”. Để kiểm tra commit/rollback thực tế, test nên bắt đầu ngoài test transaction hoặc dùng cơ chế kết thúc transaction có chủ đích, rồi đọc lại database ở transaction độc lập.

`@DataJpaTest` cho phép override:

```java
@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalRepositoryTest {
    // Test tự quản lý transaction nếu cần.
}
```

Đoạn trên là cú pháp minh họa, cần imports `org.springframework.transaction.annotation.Transactional` và `Propagation`; không phải tệp Java hoàn chỉnh. **Khi tắt test-managed transaction, dữ liệu có thể được commit và không tự rollback**, nên phải có cleanup hoặc database lifecycle phù hợp.

Nếu cần thao tác kiểm thử ở transaction đã active:

```java
TestTransaction.flagForRollback();
TestTransaction.end();
```

Đó là đoạn minh họa trong test có transaction do Spring TestContext đang quản lý, không áp dụng trong mọi context. `TestTransaction` điều khiển **transaction của test thread**, không tự điều khiển transaction của một HTTP request được server xử lý trên thread khác.

## 12. So sánh @DataJpaTest với các test slices khác

| Mục tiêu | Công cụ thường phù hợp | Điều cần nhớ |
|---|---|---|
| JPA entity mapping và JpaRepository | `@DataJpaTest` | Persistence slice, rollback mặc định |
| JDBC trực tiếp qua JdbcTemplate | `@JdbcTest` | Không cần JPA provider/repositories |
| Spring Data JDBC repositories | `@DataJdbcTest` | Khác JPA entity lifecycle/dirty checking |
| Reactive R2DBC repositories | `@DataR2dbcTest` | Reactive stack, transaction model khác |
| MVC controller và JSON response | `@WebMvcTest` | Service/repository thường phải mock |
| WebFlux annotated controller | `@WebFluxTest` | WebTestClient, Mono/Flux, không chứng minh JPA |
| Service + Repository + DB + config | `@SpringBootTest` hoặc context integration phù hợp | Nặng hơn; kiểm tra đường đi thật |
| HTTP server thật + full workflow | `@SpringBootTest(RANDOM_PORT)` | Server thread transaction khác test thread |
| Business logic thuần Java | JUnit + Mockito nếu cần | Không cần Spring context |
| Migration SQL production-specific | Testcontainers + migration/validate | Ưu tiên database/dialect production-like |

Không nên thay `@DataJpaTest` bằng `@SpringBootTest` chỉ vì một bean service thiếu, khi mục tiêu của test vốn là repository. Ngược lại, không dùng một JPA slice đã `@Import` nhiều service, controller, scheduler và API client rồi gọi đó là “slice nhẹ”; lúc ấy phạm vi đã gần integration test và chi phí/độ rủi ro cao hơn.

## 13. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Hướng chẩn đoán |
|---|---|---|
| `Failed to configure a DataSource` | Không có embedded driver, URL hoặc cấu hình test datasource hợp lệ | Xem classpath H2/HSQL/Derby, Replace mode và JDBC URL |
| `Unable to find a @SpringBootConfiguration` | Test nằm ngoài package hierarchy của application | Đặt test cùng package/cấp con hoặc cấu hình bootstrap rõ |
| `NoSuchBeanDefinitionException: BookService` | Service không thuộc JPA slice | Inject repository, import có chủ đích hoặc chuyển test service |
| `Not a managed type: Book` | Entity scan không nhận `@Entity` hoặc package ngoài base | Kiểm tra `@Entity`, package scan/`@EntityScan` nếu cần |
| `Table ... not found` | DDL chưa tạo, migration chưa chạy hoặc datasource/schema sai | Xem DDL/migrations/datasource và `ddl-auto` |
| Derived query fail khi context khởi động | Property name hoặc return type sai | Soát tên thuộc tính entity và method name |
| `@Query` fail khi khởi động/gọi | JPQL syntax/param name sai | Soát entity property và `@Param`; phân biệt SQL native |
| Test save/find xanh nhưng SQL chưa được kiểm chứng | First-level cache che lỗi hoặc chưa flush | `flush → clear → reload`; kiểm tra thêm JDBC |
| Unique constraint test không thấy lỗi | SQL chưa thực thi hoặc schema thiếu constraint | `saveAndFlush`, kiểm tra DDL đã tạo |
| Constraint test ném lỗi nhưng test khác fail | Transaction rollback-only/DB state bị nhiễm | Không query sau SQL lỗi trong cùng test; để rollback và cô lập fixtures |
| Test H2 xanh nhưng PostgreSQL fail | Dialect, collation, locking, migration khác | Dùng Testcontainers PostgreSQL và migration thật |
| Test unexpectedly dính database production | `replace=NONE` và URL đang chỉ môi trường sai | Bảo vệ datasource URL, tách profile/secrets; không chạy destructive tests trên production |
| Flyway `schema history` lỗi | Schema do Hibernate/migration cùng tạo hoặc checksum mismatch | Chọn schema owner, chạy migration theo cách production |
| `LazyInitializationException` ngoài test | Test có transaction active che lifecycle | Kiểm tra fetch plan và service boundaries |
| N+1 queries không được phát hiện | Chỉ assert output, không kiểm tra SQL count | Dùng query statistics/log với fixture đủ lớn |
| Context nạp quá nhiều bean | Custom `@ComponentScan`/Import phá slice filter | Giảm scan/import, giữ JPA-only config |
| Test chạy riêng xanh nhưng suite đỏ | Context cache, shared DB hoặc fixture bị commit | Dùng transaction rollback, unique keys, cleanup, cô lập container |
| Boot 4 import `@DataJpaTest` không tìm thấy | Package/module đã đổi so với Boot 3.x | Sử dụng module và package test Boot 4 phù hợp |

**Ưu tiên đọc root cause** trong `Caused by`, không chữa một assertion khi application context còn chưa khởi tạo xong. `@DataJpaTest` giúp giảm số loại bean và vì thế thường giúp khoanh vùng lỗi nhanh hơn full context.

## 14. Lưu ý phiên bản: Boot 3.5 và Boot 4.x

Bộ mã ở mục 4 và 8 được thiết kế theo **Spring Boot 3.5.x / Java 17+**, với imports:

```java
org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest
org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager
org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase
```

Đây là danh sách package, không phải nội dung một file Java.

Trong **Spring Boot 4.x**, hệ thống module/test auto-configuration được tách lại. Các kiểu tương ứng hiện nằm trong các package/module mới, ví dụ:

```java
org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest
org.springframework.boot.jpa.test.autoconfigure.TestEntityManager
org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase
```

Cần dependency test như `spring-boot-data-jpa-test` và các module phù hợp với Boot 4/BOM. **Không ghép `spring-test`/Boot test 4.x với Boot 3.5 runtime chỉ để sửa import.** Giữ nhất quán toàn bộ dependency versions và chọn code theo đúng dòng dự án.

Những nguyên tắc **không đổi** dù module đổi tên:
- Persistence slice chỉ nạp các thành phần liên quan, không phải full application.
- Entity/repository test nên chạy với database và transaction thực.
- Flush khác commit; first-level cache có thể làm test quá dễ đạt.
- H2 không chứng minh những hành vi PostgreSQL/MySQL đặc thù.
- Test database replacement/connection và migrations phải được kiểm soát tường minh khi độ tin cậy phụ thuộc chúng.

## 15. Checklist khi viết @DataJpaTest

- [ ] Đã xác định mục tiêu là entity mapping/repository query/database constraints, không phải toàn bộ HTTP/service workflow.
- [ ] `@DataJpaTest` đúng package theo Boot version; không thêm `@SpringBootTest` cùng lớp chỉ để có mọi bean.
- [ ] `@Entity` và `JpaRepository` nằm trong phạm vi scan, không bị mất bởi cấu hình component scan tùy biến.
- [ ] Hạ tầng JPA, `DataSource`, transaction manager và test database đã thực sự được tạo.
- [ ] Biết datasource đang là H2/embedded, container hay database test đã cấu hình; không chỉ suy luận từ tên profile.
- [ ] Nếu dùng Testcontainers, đã dùng `Replace.NONE` hoặc cơ chế nhận diện DB test đúng và lifecycle container phù hợp.
- [ ] Đã phân biệt `persist/save`, `flush`, `clear` và `commit`.
- [ ] Test kiểm tra database thực có `flush → clear → reload` hoặc JDBC assertion khi phù hợp.
- [ ] Fixtures có dữ liệu đại diện; unique/foreign key và query edge cases được kiểm tra, không chỉ happy path.
- [ ] Migrations/Flyway/Liquibase không mâu thuẫn với Hibernate `ddl-auto`.
- [ ] H2 không được dùng làm bằng chứng cho SQL dialect/locking/index production-specific nếu không có test production-like DB.
- [ ] Không phụ thuộc thứ tự test hoặc dữ liệu đã commit trong DB dùng chung.
- [ ] Đã cân nhắc lazy loading, N+1 và transaction boundaries ngoài test thread.
- [ ] Nếu service thiếu trong slice, đã chọn đúng loại test thay vì kéo toàn bộ application context vào.
- [ ] Đã thực thi đúng test task/lớp, xác minh số test thực chạy và đọc reports trước khi tuyên bố PASS.

## 16. Tài liệu chính thức

- [Spring Boot 3.5 – Auto-configured Data JPA Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): entity/repository scan, embedded DB, transactions/rollback, `TestEntityManager`.
- [Spring Boot 3.5 – Test Slices Appendix](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): danh sách những auto-configuration được import vào `@DataJpaTest`.
- [Spring Boot 3.5 – DataJpaTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): package, annotation, thuộc tính `showSql` và `properties`.
- [Spring Boot 3.5 – AutoConfigureTestDatabase Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html): Replace policies và nguồn embedded database.
- [Spring Boot 4 – Data JPA Testing](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): phạm vi slice trong dòng mới.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): derived queries, JPQL, repositories và persistence semantics.

**Kết luận:** `@DataJpaTest` tập trung vào phần persistence **thật**: Spring Data JPA repositories, entity mappings, Hibernate/EntityManager, datasource, transaction và các helper như `TestEntityManager`. Test mặc định có transaction và rollback, còn database có thể là embedded H2 hoặc một database test phù hợp. Muốn test vững, dùng assertions trên SQL/persistence sau `flush` và `clear`, kiểm tra constraints và query trên database tương thích yêu cầu, đồng thời tách riêng những rủi ro service transaction, HTTP, security và tích hợp hạ tầng nằm ngoài JPA slice.