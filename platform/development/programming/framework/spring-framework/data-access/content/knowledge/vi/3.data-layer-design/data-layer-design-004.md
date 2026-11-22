# Tiêm DataSource, template hoặc EntityManager thay cho tự tìm tài nguyên

Trong tầng truy cập dữ liệu của Spring, **repository/DAO nên nhận tài nguyên đã được cấu hình sẵn** từ Spring container thay vì tự tìm chúng bằng JNDI, gọi `DriverManager`, tự tạo connection pool, lấy `ApplicationContext.getBean(...)` trong logic nghiệp vụ hoặc tự mở `EntityManager` ở mỗi phương thức. Đây là ứng dụng của **Dependency Injection (DI)** và **Inversion of Control (IoC)** vào thiết kế tầng dữ liệu.

Mục tiêu không chỉ là giảm số dòng Java. Việc chuyển quyền tạo và quản lý tài nguyên về cấu hình ứng dụng giúp repository dễ kiểm thử, đổi database/driver, dùng pool có kiểm soát, tham gia đúng transaction và thể hiện rõ ai chịu trách nhiệm vòng đời của kết nối.

Bài học tập trung vào ba lựa chọn:

- **`DataSource`**: factory cung cấp JDBC `Connection`. Tiêm khi adapter phải làm việc trực tiếp với JDBC hoặc thư viện nhận `DataSource`.
- **`JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`**: công cụ Spring JDBC được cấu hình từ `DataSource`. Tiêm khi repository chủ động viết SQL, mapping kết quả và thực hiện update/batch.
- **`EntityManager`**: API Jakarta Persistence dùng cho entity/JPA. Thông thường sử dụng **shared `EntityManager` proxy** do Spring tiêm bằng `@PersistenceContext`, để persistence context thực tế được quản lý theo transaction.

## 1. Vấn đề: tự tìm tài nguyên tạo phụ thuộc hạ tầng ẩn

Ví dụ một DAO tự tìm DB mỗi lần đọc dữ liệu:

~~~java
// Ví dụ minh họa cách thiết kế cần cải thiện trong ứng dụng Spring.
public String findTitle(long id) throws java.sql.SQLException {
    String url = System.getenv("DB_URL");
    String user = System.getenv("DB_USER");
    String password = System.getenv("DB_PASSWORD");

    try (var connection =
                 java.sql.DriverManager.getConnection(url, user, password);
         var statement = connection.prepareStatement(
                 "SELECT title FROM books WHERE id = ?")) {
        statement.setLong(1, id);
        try (var rows = statement.executeQuery()) {
            return rows.next() ? rows.getString("title") : null;
        }
    }
}
~~~

Đoạn minh họa trên có bind parameter và đóng tài nguyên đúng mức cơ bản, nhưng nó gắn repository với tên biến môi trường, cách lấy mật khẩu, driver, vòng đời kết nối và handling lỗi SQL. Mỗi lần gọi `DriverManager` mở connection riêng, không dùng pool do Spring cấu hình. Connection này **không tự tham gia** transaction mà `DataSourceTransactionManager` đang quản lý cho một `DataSource` khác.

Những biểu hiện tương đương:

1. DAO gọi `new InitialContext().lookup("java:comp/env/jdbc/AppDS")` trong từng phương thức thay vì nhận một `DataSource` do configuration layer cung cấp.
2. DAO inject `ApplicationContext` rồi gọi `getBean("myJdbcTemplate")` khi thực thi query. Đây là **Service Locator**: dependency thật bị ẩn trong method.
3. DAO tự tạo `HikariDataSource` hoặc `EntityManagerFactory` nhiều lần; pool/factory bị nhân bản, có thể cạn connection và khó đóng.
4. Singleton DAO giữ một JDBC `Connection` hoặc JPA `EntityManager` thật làm field, rồi tái sử dụng qua các request/thread.
5. DAO tự gọi `commit`, `rollback`, `close` trên tài nguyên mà Spring transaction đang sở hữu.

**Thiết kế tốt hơn**: cấu hình resource thành bean, DAO khai báo loại object nó cần; Spring resolve dependency, áp dụng lifecycle và kết nối với hạ tầng transaction.

## 2. Sơ đồ sở hữu tài nguyên và lớp sử dụng

~~~text
Application configuration / Spring Boot auto-configuration
                     |
        +------------+-------------------+
        |                                |
  DataSource bean                 EntityManagerFactory bean
        |                                |
  JdbcTemplate bean                @PersistenceContext
  JdbcClient bean                        |
        |                         Shared EntityManager proxy
        |                                |
  JDBC repository                    JPA repository
        \                                /
         +--------- Service ------------+
                   @Transactional
                         |
                Controller / Job / API
~~~

| Tài nguyên được tiêm | Bản chất | Sở hữu vòng đời | Tác vụ thường gặp |
| --- | --- | --- | --- |
| `DataSource` | Factory lấy JDBC connection | Spring/Boot/container hoặc pool do ứng dụng tạo | Cấu hình JDBC, API thấp, tích hợp thư viện JDBC |
| `JdbcTemplate` | SQL executor và mapper đồng bộ | Spring bean, mượn/trả connection qua resource helper | CRUD SQL, `RowMapper`, batch |
| `NamedParameterJdbcTemplate` | SQL template với `:namedParameter` | Spring bean dùng `DataSource`/template | Bind tên, truy vấn nhiều tham số, `IN (:ids)` |
| `JdbcClient` | Fluent JDBC API (Spring Framework 6.1+) | Spring bean hoặc tạo từ factory | Query/update với mapping ngắn gọn |
| `EntityManagerFactory` | Factory tạo JPA persistence contexts | Spring/provider; thường chia sẻ được giữa threads | Bootstrap JPA, custom context lifecycle đặc biệt |
| `EntityManager` thật | Session có trạng thái, không thread-safe | Theo transaction/context cụ thể | JPA entity và query trong operation |
| Shared `EntityManager` proxy | Delegating proxy chọn entity manager theo ngữ cảnh | Spring/JPA infrastructure | DAO singleton dùng `@PersistenceContext` |
| `JpaRepository` của Spring Data | Repository proxy bao quanh JPA | Spring Data | CRUD/derived queries/paging cho entity |

**Factory khác session.** `DataSource` có thể là singleton vì nó cấp nhiều connection khi được yêu cầu, còn một `Connection` giữ trạng thái transaction/session và không phù hợp làm field singleton. `EntityManagerFactory` cũng khác với `EntityManager` thật: factory được dùng chung, còn entity manager có persistence context riêng.

`JdbcTemplate` thông thường thread-safe **sau khi cấu hình xong**, nên có thể inject một bean vào nhiều repository. Với `EntityManager`, tính an toàn khi inject vào singleton dựa vào **shared proxy** mà Spring tạo; không có nghĩa một persistence context thật tự nhiên thread-safe.

## 3. Constructor injection: cách mặc định cho repository

Spring hỗ trợ constructor, setter/method và field injection. Với dependency bắt buộc, **constructor injection** dễ nhìn thấy, làm trường `final`, fail sớm khi cấu hình thiếu và cho phép tạo object trực tiếp trong unit test.

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookJdbcRepository {
    private final JdbcTemplate jdbc;

    public BookJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findTitle(long id) {
        return jdbc.query(
                "SELECT title FROM books WHERE id = ?",
                rs -> rs.next() ? rs.getString("title") : null,
                id
        );
    }
}
~~~

Đây là **class minh họa trong ứng dụng Spring đã có bean `JdbcTemplate` và bảng `books`**, không phải chương trình standalone. `@Repository` được component scan phát hiện nếu scan đúng package; Spring gọi constructor và cung cấp bean `JdbcTemplate`. Với class có đúng **một constructor**, không cần ghi thêm `@Autowired` trên constructor.

`JdbcTemplate.query` ở đây dùng `ResultSetExtractor` để lấy giá trị từ `ResultSet`; nếu yêu cầu chính xác một hàng, nên chọn API bảo đảm cardinality và ràng buộc khóa ở database.

Service cũng inject repository, thay vì biết SQL connection:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookJdbcRepository books;

    public BookService(BookJdbcRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public String titleOf(long id) {
        return books.findTitle(id);
    }
}
~~~

`@Transactional(readOnly = true)` yêu cầu transaction manager và Spring transaction proxy hoạt động. `readOnly` là hint/tối ưu, **không phải** một lệnh cấm ghi dữ liệu chắc chắn ở mọi database/provider.

### 3.1. Các lựa chọn injection khác

- **`@Bean` factory method parameter**: nhận `DataSource` từ container rồi tạo `JdbcTemplate`; phù hợp cho Java configuration.
- **Setter/method injection**: dùng khi dependency thực sự tùy chọn hoặc cần cấu hình lại; với dependency bắt buộc, constructor rõ hơn.
- **Field `@Autowired`**: vẫn hoạt động trên bean do Spring quản lý, nhưng khó khởi tạo độc lập và khó thiết kế immutable; không cần ưu tiên cho DAO mới.
- **`@PersistenceContext`**: cơ chế Jakarta Persistence đặc biệt dành cho shared `EntityManager`; không đồng nhất với `@Autowired EntityManager` mặc định.
- **`@Qualifier`**: cần khi có nhiều bean cùng kiểu, ví dụ `reportingJdbcTemplate` và `writeJdbcTemplate`.

### 3.2. Composition root được phép tạo object

Một `@Bean` method như sau là DI hợp lệ:

~~~java
@Configuration
class DataAccessConfig {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean
    BookJdbcRepository bookJdbcRepository(JdbcTemplate jdbc) {
        return new BookJdbcRepository(jdbc);
    }
}
~~~

Các `import` cần thiết là `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.jdbc.core.JdbcTemplate` và `javax.sql.DataSource`. Đoạn này minh họa configuration, giả sử có bean `DataSource`. `new` trong **composition root** là bình thường: đó là nơi lắp ráp dependency. Điều cần tránh là service/DAO tự tạo pool hoặc tự tìm global context trong mỗi business operation. Nếu đồng thời bật component scan cho `BookJdbcRepository`, tránh khai báo bean trùng.

## 4. Ví dụ hoàn chỉnh: Java 17, Spring JDBC, DI và rollback

Để nhìn thấy chính xác đường đi của dependency, ví dụ dùng Spring Framework trực tiếp, **không** dùng Spring Boot. Cần Java 17+, Gradle tương thích, Spring Framework 6.2.11 và H2 2.3.232.

Cấu trúc:

~~~text
spring-data-di/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-data-di'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.11'
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
~~~

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

import javax.sql.DataSource;
import java.util.List;

public class App {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            BookGateway gateway = context.getBean(BookGateway.class);
            BookService service = context.getBean(BookService.class);

            gateway.createSchema();
            service.addInitialBooks();

            try {
                service.insertThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("Rollback: " + ex.getMessage());
            }
            System.out.println(gateway.findTitles());
        }
    }

    @Configuration
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:di_example;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public BookGateway bookGateway(JdbcTemplate jdbc) {
            return new JdbcBookGateway(jdbc);
        }

        @Bean
        public BookService bookService(BookGateway gateway) {
            return new BookService(gateway);
        }
    }

    public interface BookGateway {
        void createSchema();
        void insert(long id, String title);
        List<String> findTitles();
    }

    public static class JdbcBookGateway implements BookGateway {
        private final JdbcTemplate jdbc;

        public JdbcBookGateway(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public void createSchema() {
            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(100) NOT NULL
                    )
                    """);
        }

        @Override
        public void insert(long id, String title) {
            jdbc.update(
                    "INSERT INTO books (id, title) VALUES (?, ?)",
                    id, title
            );
        }

        @Override
        public List<String> findTitles() {
            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    (rs, rowNum) -> rs.getString("title")
            );
        }
    }

    public static class BookService {
        private final BookGateway books;

        public BookService(BookGateway books) {
            this.books = books;
        }

        @Transactional
        public void addInitialBooks() {
            books.insert(1L, "Spring");
            books.insert(2L, "JDBC");
        }

        @Transactional
        public void insertThenFail() {
            books.insert(3L, "Temporary");
            throw new IllegalStateException("intentional");
        }
    }
}
~~~

Tại thư mục `spring-data-di`, khi đã có JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

Stdout chính xác của chương trình:

~~~text
Rollback: intentional
[Spring, JDBC]
~~~

**Giải thích từng bước:**

1. `AnnotationConfigApplicationContext` đọc `Config` và các `@Bean`. Chỉ `Config` biết JDBC URL và cách tạo `DataSource`; DAO và service không biết.
2. Spring truyền `DataSource` vào factory method tạo `JdbcTemplate`, truyền template vào `JdbcBookGateway`, rồi truyền `BookGateway` vào `BookService`.
3. `@EnableTransactionManagement` bật infrastructure xử lý `@Transactional`. Lời gọi `context.getBean(BookService.class)` lấy bean được Spring quản lý, nên `addInitialBooks()` và `insertThenFail()` có transaction interceptor.
4. `DataSourceTransactionManager` quản lý một JDBC connection cho transaction. `JdbcTemplate` dùng cơ chế transaction-aware của Spring, nên các insert trong cùng service method thuộc cùng transaction.
5. `insertThenFail()` chèn hàng thứ ba rồi ném `IllegalStateException`. Đây là runtime exception, mặc định khiến transaction rollback; hàng tạm thời không tồn tại trong truy vấn cuối.
6. `ORDER BY id` làm thứ tự kết quả xác định; `DB_CLOSE_DELAY=-1` giữ database H2 in-memory trong JVM khi connection cuối được đóng.
7. `try-with-resources` đóng **Spring context**. DAO không giữ connection làm field, không tự gọi commit/rollback.

**Giới hạn ví dụ:** `DriverManagerDataSource` tạo connection mới mỗi lần được yêu cầu và **không cung cấp pool**. Chỉ dùng ở demo/test đơn giản; ứng dụng thực tế nên cấu hình connection pool (ví dụ HikariCP) qua Spring Boot hoặc config phù hợp. H2 phù hợp học cơ chế DI/transaction, không chứng minh mọi hành vi khóa/isolation giống database production.

Cấu hình `@Bean` đã đăng ký hai implementation `JdbcBookGateway` và `BookService` nên không cần gắn `@Repository`/`@Service` trong ví dụ này. Nếu chuyển qua component scan, hãy chọn một cách đăng ký bean thống nhất để tránh bean trùng.

## 5. Khi nào inject DataSource, JdbcTemplate, JdbcClient?

### 5.1. SQL thông thường: inject template/client

Chọn template hoặc client khi code phải chạy SQL, ánh xạ dòng sang DTO và cập nhật bảng. Spring JDBC giúp:

- Mượn/trả connection, statement, result set đúng phạm vi;
- Dùng placeholder và bind parameter để tránh SQL injection qua giá trị;
- Dịch lỗi JDBC sang hệ `DataAccessException`;
- Tham gia transaction do Spring quản lý với đúng `DataSource`;
- Cung cấp `RowMapper`, batching, truy vấn có tên và thao tác cập nhật rõ ràng.

Ví dụ với `JdbcClient` (Spring Framework 6.1+, snippet trong bean được cấp `JdbcClient`):

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;
import java.util.Optional;

public class BookQueryDao {
    private final JdbcClient jdbc;

    public BookQueryDao(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<String> title(long id) {
        return jdbc.sql(
                "SELECT title FROM books WHERE id = :bookId")
            .param("bookId", id)
            .query(String.class)
            .optional();
    }
}
~~~

Với Spring Framework thuần, tạo bean khi cần:

~~~java
@Bean
JdbcClient jdbcClient(DataSource dataSource) {
    return JdbcClient.create(dataSource);
}
~~~

Đoạn `@Bean` nằm trong `@Configuration` và giả sử `DataSource` đã tồn tại. `optional()` cho biết rõ trường hợp không có hàng; nếu nhiều hàng, đây là lỗi cardinality, cần bảo đảm uniqueness ở schema hoặc truy vấn.

### 5.2. Inject DataSource trực tiếp: chỉ khi cần API JDBC thấp

Một số thư viện bên thứ ba yêu cầu `DataSource`, hoặc adapter cần API đặc thù của JDBC/driver. Trường hợp đó inject `DataSource` là đúng, nhưng không giữ kết nối trong field singleton.

Nếu bắt buộc tự dùng JDBC trong transaction Spring, `DataSourceUtils` giúp lấy connection theo transaction hiện tại:

~~~java
import org.springframework.jdbc.datasource.DataSourceUtils;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class LegacyJdbcAdapter {
    private final DataSource dataSource;

    public LegacyJdbcAdapter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findTitle(long id) throws SQLException {
        Connection connection =
                DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement statement =
                    connection.prepareStatement(
                            "SELECT title FROM books WHERE id = ?")) {
                statement.setLong(1, id);
                try (ResultSet rows = statement.executeQuery()) {
                    return rows.next()
                            ? rows.getString("title") : null;
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
~~~

Đây là **class adapter minh họa** cần `DataSource` và bảng `books`; không chạy độc lập. `DataSourceUtils.getConnection` có thể tìm connection đã bind vào transaction của Spring; `releaseConnection` tránh đóng nhầm kết nối đang do transaction giữ. Nếu dùng JDBC thuần, bạn còn phải quyết định exception translation/statement timeout; `JdbcTemplate` xử lý phần lớn việc này cho ứng dụng.

Đừng tự `commit()/rollback()` trên connection đang thuộc transaction Spring. Nếu tích hợp một API JDBC cũ chỉ gọi `DataSource.getConnection()`, tìm hiểu `TransactionAwareDataSourceProxy`; code Spring JDBC mới nên ưu tiên template hoặc `DataSourceUtils`.

### 5.3. Không tiêm Connection vào singleton

~~~java
// Anti-pattern: connection state bị giữ qua nhiều request/thread.
class WrongDao {
    private final java.sql.Connection connection;

    WrongDao(javax.sql.DataSource dataSource)
            throws java.sql.SQLException {
        connection = dataSource.getConnection();
    }
}
~~~

Mỗi kết nối có trạng thái transaction, timeout, session và có thể bị đóng/không hợp lệ sau một thời gian. Giữ connection qua request khiến pool khó thu hồi, mất isolation và dễ sai khi chạy đồng thời. Injection nên đưa **factory** hoặc **abstraction quản lý mượn/trả connection**, không đưa một connection sống mãi.

## 6. EntityManager: shared proxy khác EntityManager thật

JPA không chỉ chạy SQL; nó quản lý **persistence context** chứa entity managed, identity map và dirty checking. Phân biệt:

- **`EntityManagerFactory`:** Factory cung cấp entity manager, thường thread-safe và sống theo application context.
- **`EntityManager` thật:** Có persistence context, giữ state, **không thread-safe**; không share như singleton giữa các request.
- **Shared EntityManager proxy:** Spring đưa cho repository qua `@PersistenceContext` (mặc định `PersistenceContextType.TRANSACTION`). Proxy delegate đến entity manager phù hợp với transaction hiện tại.

### 6.1. @PersistenceContext: cách mặc định trong DAO JPA

Giả sử ứng dụng đã cấu hình JPA provider, entity `BookEntity` có `@Entity` và `@Id`, cùng `JpaTransactionManager`. Hai class sau là **ví dụ tích hợp**, không phải chương trình standalone:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class BookJpaGateway {
    @PersistenceContext
    private EntityManager entityManager;

    public BookEntity find(long id) {
        return entityManager.find(BookEntity.class, id);
    }

    public void create(BookEntity book) {
        entityManager.persist(book);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaBookService {
    private final BookJpaGateway books;

    public JpaBookService(BookJpaGateway books) {
        this.books = books;
    }

    @Transactional
    public void rename(long id, String newTitle) {
        BookEntity book = books.find(id);
        if (book == null) {
            throw new IllegalArgumentException(
                    "Book not found: " + id);
        }
        book.setTitle(newTitle);
    }
}
~~~

`BookEntity` phải có setter `setTitle` và mapping tương ứng. Trong transaction, JPA provider quản lý entity; thay đổi trên managed entity có thể được flush thành SQL khi cần, rồi commit nếu transaction thành công. **Flush không đồng nghĩa commit.**

Không gọi `entityManager.close()` trên proxy do Spring tiêm, không tự `getTransaction().begin()/commit()` ở DAO Spring. `@PersistenceContext` mặc định giải quyết lifecycle bằng hạ tầng Spring/JPA.

**Cảnh báo:** `@PersistenceContext(type = EXTENDED)` tạo extended context có state, không thread-safe và **không thích hợp cho singleton DAO** phục vụ đồng thời nhiều request. Chỉ dùng khi đã thiết kế lifecycle stateful rõ ràng.

### 6.2. Constructor injection của EntityManager có khác gì?

Constructor injection một `EntityManagerFactory` có thể thực hiện trực tiếp nếu factory được đăng ký là bean. Tuy nhiên, trong Spring Framework thuần, **shared `EntityManager`** dùng với `@Autowired`/constructor injection thường cần được **đăng ký thành bean**; `@PersistenceContext` không mặc nhiên tạo một bean `EntityManager` có thể resolve theo type cho mọi constructor.

Ví dụ đăng ký shared proxy (đoạn cấu hình độc lập, giả sử có `EntityManagerFactory` được quản lý):

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.SharedEntityManagerCreator;

@Configuration
public class JpaConfig {
    @Bean
    EntityManager sharedEntityManager(EntityManagerFactory factory) {
        return SharedEntityManagerCreator
                .createSharedEntityManager(factory);
    }
}
~~~

Sau đó, constructor-inject `EntityManager` vào DAO là hợp lệ vì dependency là **shared proxy**. Với nhiều persistence unit, mỗi factory cần cấu hình proxy/qualifier tương ứng; không đăng ký bean trùng nếu hệ thống đã cung cấp shared proxy. Cách dễ hiểu cho phần lớn custom JPA DAO vẫn là `@PersistenceContext`.

`@PersistenceUnit` có thể tiêm `EntityManagerFactory` vào field/method. Chỉ tự `createEntityManager()` khi thật sự cần quản lý lifecycle khác thông thường và chịu trách nhiệm đóng/transaction; không sử dụng cho CRUD DAO mặc định.

### 6.3. Spring Data JPA có thể che phần EntityManager

Nếu dùng `JpaRepository<BookEntity, Long>` của Spring Data JPA, service chỉ cần constructor-inject repository interface; Spring Data tạo implementation và truy cập JPA. Ví dụ minh họa cần dependency Spring Data JPA, không chỉ `spring-orm`:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {
}
~~~

Không cần inject `EntityManager` vào custom DAO nếu chức năng của `JpaRepository` đã giải quyết mục đích. Custom repository dùng EntityManager khi cần JPQL/Criteria, entity graph, query đặc thù hoặc thao tác flush có kiểm soát.

## 7. DI và transaction: hai trách nhiệm khác nhau

**DI** trả lời “DAO lấy dependency ở đâu?”. **Transaction** trả lời “những câu SQL/operation nào cùng commit hoặc rollback?”. Injection đúng là điều kiện tốt nhưng chưa đủ bảo đảm atomicity.

### 7.1. DataSourceTransactionManager và JdbcTemplate

~~~text
Controller/Job
     |
     v
Service proxy (@Transactional)
     |
     +--> TransactionManager.begin()
     |        |
     |        +--> bind JDBC Connection to current thread
     |
     v
Service.businessOperation()
     |
     +--> Repository -> JdbcTemplate
     |                   |
     |                   +--> DataSourceUtils gets bound Connection
     |
     +--> Repository -> JdbcTemplate (same DataSource/transaction)
     |
     v
commit() or rollback()
     |
     +--> release/unbind Connection
~~~

`DataSourceTransactionManager` hoặc `JdbcTransactionManager` quản lý transaction JDBC cục bộ dựa trên **một `DataSource`**. `JdbcTemplate` dùng `DataSourceUtils` nên có thể tự tham gia transaction hiện tại. Nếu DAO mở kết nối bằng `DriverManager` hoặc tiêm nhầm `DataSource` khác, lệnh SQL có thể nằm ngoài transaction.

Với JPA, `JpaTransactionManager` quản lý `EntityManager`/transaction của provider. JDBC và JPA **có thể** tham gia cùng local transaction khi dùng cùng `DataSource` và cấu hình hợp lệ, không tự suy luận chỉ dựa vào việc cả hai cùng kết nối đến một máy chủ database.

### 7.2. @Transactional hoạt động qua proxy

- Phương thức phải được gọi qua **Spring-managed bean proxy** trong chế độ proxy mặc định; `this.otherMethod()` từ cùng instance không đi qua proxy của `otherMethod`.
- Gọi `new BookService(...)` ngoài container dùng được cho unit test logic nhưng không tự kích hoạt `@Transactional`.
- `@EnableTransactionManagement` hoặc cấu hình Boot thích hợp và đúng `PlatformTransactionManager` là điều kiện cần cho transaction imperative.
- Theo mặc định Spring rollback với `RuntimeException`/`Error`; checked exception thường không rollback trừ khi cấu hình `rollbackFor` hoặc quy tắc mặc định đã thay đổi.
- Bắt exception rồi nuốt lỗi trong method có thể khiến transaction commit dù use case thất bại, nếu không đánh dấu rollback.
- `readOnly=true` là hint, không phải cơ chế bảo mật chống UPDATE.
- Transaction nên bao một use case ngắn, không ôm HTTP call, đợi queue hoặc xử lý file lâu.

Điều này giải thích vì sao ví dụ runnable ở mục 4 lấy `BookService` từ context và gọi public method trên bean: Spring proxy mới quan sát được invocation để tạo transaction.

## 8. Spring Boot và cấu hình tập trung

Trong ứng dụng Spring Boot có driver, starter và điều kiện auto-configuration phù hợp, Boot thường cấu hình `DataSource` có pool và template JDBC/JPA infrastructure. Repository không cần tự biết URL.

Cấu hình minh họa `application.yml` cho ứng dụng có JDBC starter và PostgreSQL driver:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: learning_user
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
~~~

Đây là cấu hình ví dụ; database, user và schema cần tồn tại riêng. Password thật phải đến từ environment/secrets manager, không hard-code vào repository hay commit file bí mật.

Bean repository có thể rất nhỏ:

~~~java
@Repository
public class SpringBookDao {
    private final JdbcTemplate jdbc;

    public SpringBookDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int rename(long id, String title) {
        return jdbc.update(
                "UPDATE books SET title = ? WHERE id = ?",
                title, id
        );
    }
}
~~~

Đây là snippet cho ứng dụng đã cấu hình JDBC và bảng `books`. Nếu `JdbcClient` không được cung cấp trong cấu hình cụ thể, có thể tạo một bean qua `JdbcClient.create(dataSource)`. Không tạo tùy tiện hai bean `DataSource`/`JdbcTemplate` cùng kiểu khi auto-configuration đã hoạt động.

| Stack | Dependency được inject ở service/repository | Tài nguyên nền |
| --- | --- | --- |
| Spring JDBC | `JdbcTemplate` / `JdbcClient` | `DataSource` + JDBC driver |
| Spring Data JPA | Repository interface hoặc JPA `EntityManager` | `EntityManagerFactory` + JDBC `DataSource` |
| JDBC adapter đặc thù | `DataSource` | JDBC driver, pool |
| R2DBC reactive | `DatabaseClient` / reactive repository | `ConnectionFactory` + R2DBC driver |

**Phạm vi:** R2DBC xuất hiện để tránh nhầm resource: `ConnectionFactory` reactive không thể thay cho `DataSource` JDBC. Bài này chỉ tập trung inject `DataSource`, template và `EntityManager` theo đề bài.

## 9. Nhiều DataSource hoặc persistence unit: cần định danh chính xác

Khi có hai `JdbcTemplate` hoặc hai `DataSource`, Spring không luôn biết bean nào nên được inject theo type. Dùng qualifier trong constructor:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;

public class ReportingDao {
    private final JdbcTemplate reportingJdbc;

    public ReportingDao(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate reportingJdbc) {
        this.reportingJdbc = reportingJdbc;
    }

    public long countBooks() {
        Long result = reportingJdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        return result == null ? 0L : result;
    }
}
~~~

Đây là snippet giả sử bean có tên `reportingJdbcTemplate` và bảng `books` tồn tại. `@Primary` có thể chọn bean mặc định, nhưng **không tự chọn transaction manager** phù hợp cho mọi operation.

Khi có nhiều transaction manager, service có thể đặt:

~~~java
@Transactional(transactionManager = "reportingTransactionManager")
public void rebuildReport() {
    reportingDao.rebuild();
}
~~~

Đoạn này minh họa method trong service; yêu cầu có `reportingDao` và bean manager mang tên `reportingTransactionManager`. Bean đó phải quản lý resource mà repository sử dụng.

Với JPA nhiều persistence unit, `@PersistenceContext(unitName = "orders")` có thể chọn unit được định danh đúng trong JPA config; `JpaTransactionManager` phải tương ứng với `EntityManagerFactory`. Hai local transaction ở hai database **không tự tạo atomic transaction phân tán**. Nếu use case thật sự phải ghi trên nhiều nguồn, cần chiến lược nhất quán riêng.

## 10. Thiết kế để test được

Constructor injection cho phép tạo service bằng fake repository mà không cần Spring context:

~~~java
import java.util.ArrayList;
import java.util.List;

interface BookGateway {
    void insert(long id, String title);
    List<String> findTitles();
}

final class FakeBookGateway implements BookGateway {
    private final List<String> titles = new ArrayList<>();

    @Override
    public void insert(long id, String title) {
        titles.add(title);
    }

    @Override
    public List<String> findTitles() {
        return List.copyOf(titles);
    }
}
~~~

Đây là **minh họa test double**, dùng interface chung tương tự ví dụ mục 4; ở project thật nên import interface production, không định nghĩa lại. Khi unit test tự `new BookService(fake)`, logic được test, **transaction annotation không tự có hiệu lực**.

Phân biệt:

1. **Unit test service:** Fake/mock repository kiểm tra quyết định nghiệp vụ, exception và thứ tự gọi; không chứng minh transaction SQL.
2. **Integration test JDBC:** Dùng Spring Test/Boot `@JdbcTest`, database thích hợp để kiểm tra SQL syntax, mapper, constraint và rollback.
3. **Integration test JPA:** Dùng Spring Test/Boot `@DataJpaTest` để xác thực entity mapping, query, flush/lazy loading và đúng transaction.
4. **Integration test multi-bean wiring:** Khi có nhiều data source/manager, kiểm tra repository thực sự sử dụng đúng database; không chỉ test rằng context khởi động được.

Test trọng yếu sau refactor: bắt đầu transaction ở service, thực hiện hai INSERT, cố ý ném runtime exception trước commit rồi kiểm tra cả hai hàng đều không được ghi. Nếu một hàng vẫn tồn tại, điều tra call qua proxy, đúng `DataSource`, manager và các connection có bị tự mở ngoài Spring không.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho `JdbcTemplate` | Chưa có bean/starter/driver, auto-config không khớp | Kiểm tra dependency, `DataSource`, component scan/config |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type | `@Qualifier` rõ ràng, `@Primary` khi cần default |
| Field `@Autowired` bị `null` | DAO được tạo thủ công bằng `new` hoặc không nằm trong Spring | Tạo/register bean đúng, constructor injection |
| `@Transactional` không rollback | Self-invocation, gọi ngoài proxy, manager sai hoặc exception bị nuốt | Đặt transaction ở service bean, test rollback |
| DAO commit dù service ném lỗi | Connection tạo bằng `DriverManager`/DataSource khác | Dùng `JdbcTemplate`/`DataSourceUtils` cùng resource |
| Hết pool connection | Giữ connection lâu, không release, transaction kéo dài | Dùng template, release đúng, theo dõi pool metrics |
| JPA `TransactionRequiredException` | Thao tác ghi không có transaction hợp lệ | `@Transactional` và `JpaTransactionManager` đúng |
| JPA concurrency lỗi ngẫu nhiên | Share một `EntityManager` thật giữa threads | Dùng `@PersistenceContext` proxy, tránh EXTENDED ở singleton |
| Không inject được EntityManager qua constructor | Không có shared proxy bean cho autowire | Dùng `@PersistenceContext` hoặc đăng ký shared proxy |
| Hai database bị nhầm lẫn | Type-only injection chọn default bean sai | Qualifier + manager/resource mapping rõ ràng |
| Test trên H2 chạy nhưng production lỗi | SQL dialect/isolation khác DB production | Test bổ sung bằng database tương thích production |
| Lộ credential | URL/password nằm trong DAO hoặc log | Cấu hình externalized secrets, không log dữ liệu nhạy cảm |

### Bốn hiểu lầm nguy hiểm

**“Tiêm `DataSource` rồi DAO nên gọi `dataSource.close()`.”** DAO không sở hữu pool/factory do Spring tạo. Container quản lý lifecycle bean; connection mượn từng operation mới được release theo đúng cơ chế.

**“Tiêm `EntityManager` tức là một context sống toàn ứng dụng.”** Với `@PersistenceContext` mặc định, đối tượng được tiêm là shared proxy, không đồng nghĩa giữ mọi entity managed mãi mãi. Entity có thể trở thành detached sau transaction.

**“`@Repository` tự bật transaction.”** Annotation này giúp đánh dấu component/repository và có thể tham gia exception translation khi infrastructure phù hợp, nhưng không thay `@Transactional` hay transaction manager.

**“`new JdbcTemplate(dataSource)` trong constructor luôn sai.”** Việc tạo template từ `DataSource` đã được inject có thể chạy đúng; tuy nhiên một bean template dùng chung làm cấu hình timeout/customization nhất quán hơn khi nhiều DAO cần cùng policy. Lỗi chính là business code tự tạo *DataSource/connection* và ẩn dependency.

## 12. Quy trình chuyển DAO cũ sang DI

1. **Kiểm kê phụ thuộc:** Xác định DAO cần SQL template, JDBC API trực tiếp, JPA EntityManager hay chỉ Spring Data repository.
2. **Đưa cấu hình ra composition root:** Connection URL, credentials, driver, pool, transaction manager và JPA provider thuộc cấu hình, không thuộc business method.
3. **Tạo/kiểm tra bean:** Dùng auto-configuration hợp lệ của Boot hoặc `@Bean` có tham số dependencies; tránh bean trùng.
4. **Đổi lookup thành injection:** Constructor injection cho JDBC DAO/service; `@PersistenceContext` cho JPA DAO khi cần.
5. **Bảo toàn transaction:** Xác định service use case, đúng manager và đường gọi qua proxy; không để JDBC code mở connection rời.
6. **Xóa quản lý tài nguyên thừa:** Không còn pool mới ở mỗi request, field Connection, manual commit/rollback hoặc đóng injected EntityManager.
7. **Viết test phù hợp:** Happy path, không có hàng, lỗi constraint, rollback, multi-DataSource, concurrency.
8. **Theo dõi runtime:** SQL query count, active/idle/waiting connection, timeout, slow query, N+1 nếu có ORM.

Khi code cũ đã có transaction manual, cần hiểu đầy đủ behavior trước khi bỏ. Mục tiêu là chuyển sở hữu transaction về đúng tầng và bảo toàn tính nhất quán nghiệp vụ.

## 13. Câu hỏi ôn tập và checklist

Tự giải thích các câu sau:

1. Vì sao `DataSource` dùng chung qua nhiều repository được còn một `Connection` đơn lẻ không nên là field singleton?
2. Khác nhau giữa inject `JdbcTemplate` và inject `DataSource`? Khi nào chọn mỗi cách?
3. `@PersistenceContext` mặc định mang lại entity manager thật hay shared proxy? Điều gì xảy ra khi có nhiều request?
4. Vì sao `this.save()` không kích hoạt transaction proxy dù `save` có `@Transactional`?
5. Nếu service dùng hai `DataSource`, tại sao một `@Transactional` mặc định không bảo đảm atomic xuyên cả hai?
6. Trong test tự `new BookService(fake)`, ta kiểm tra được logic nào và chưa thể chứng minh điều gì?
7. Với nhiều persistence unit, làm sao chỉ rõ `EntityManager` và transaction manager phù hợp?

Checklist khi triển khai:

- [ ] DAO/service công khai dependency qua constructor; JPA dùng `@PersistenceContext` hoặc shared proxy được cấu hình đúng.
- [ ] Driver, pool, secret và factory thuộc application config; repository không tự đọc môi trường hoặc service-locate bean.
- [ ] Không giữ `Connection`/`EntityManager` thật trong singleton.
- [ ] SQL thông thường sử dụng `JdbcTemplate`/`JdbcClient` và bind parameter.
- [ ] JDBC thấp nếu bắt buộc dùng `DataSourceUtils` để cùng transaction và release đúng cách.
- [ ] `@Transactional` đặt trên service bean, đi qua proxy và chọn đúng transaction manager.
- [ ] Nhiều `DataSource`/template/persistence unit có qualifier và routing minh bạch.
- [ ] Integration test kiểm chứng SQL, mapping, exception và rollback thật.
- [ ] Quan sát pool, timeout, query count và bảo vệ credentials.

**Ghi nhớ:** Repository chỉ cần nói **nó cần `DataSource`, template hay `EntityManager`**; composition root quyết định **tạo/config tài nguyên ở đâu và ai đóng**; transaction infrastructure quyết định **những thao tác nào cùng commit/rollback**. Tách ba trách nhiệm đó là trọng tâm của thiết kế tầng dữ liệu trong Spring.

## Tài liệu chính thức

- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — DataSource và Connection](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework 6.2 — JPA và EntityManager Injection](https://docs.spring.io/spring-framework/reference/6.2/data-access/orm/jpa.html)
- [Spring Framework — Transaction Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Internals](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/)
