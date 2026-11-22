# Khởi tạo một JdbcTemplate đã cấu hình rồi tái sử dụng

Một `JdbcTemplate` là **công cụ thực thi JDBC đã biết cách lấy kết nối từ `DataSource` và thực hiện SQL theo các thiết lập chung**. Trong ứng dụng Spring, cách thiết kế thông thường là **tạo và cấu hình template một lần khi khởi động ứng dụng**, sau đó tiêm cùng instance đã cấu hình vào những repository/DAO cần dùng nó.

Đây là một nguyên tắc quan trọng của mục **JdbcTemplate** trong Spring Framework data-access: **`JdbcTemplate` thread-safe sau khi cấu hình xong**. Một bean template có thể được nhiều repository dùng đồng thời; mỗi thao tác lấy connection phù hợp với transaction hiện tại rồi trả tài nguyên đúng cách. Template **không phải** một JDBC `Connection` dùng chung, không tự lưu kết quả SQL và không có nghĩa mọi request chạy trên một connection.

Bài học hướng dẫn cách chọn vòng đời bean, cấu hình đúng thời điểm, tái sử dụng giữa nhiều repository, phối hợp connection pool/transaction và tránh việc tạo template mới hoặc thay đổi cấu hình trong từng request.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một `JdbcTemplate` đã cấu hình có thể chia sẻ an toàn giữa nhiều DAO, còn một `Connection` không nên giữ làm field của singleton DAO.
2. Tạo `DataSource` và `JdbcTemplate` trong Spring `@Configuration`, cấu hình `queryTimeout`/`fetchSize`/`maxRows` trước khi công bố bean và dùng constructor injection để tái sử dụng.
3. Hiểu `JdbcTemplate` được Spring Boot auto-configure như thế nào và khi nào không cần tự khai báo `@Bean`.
4. Viết và chạy ví dụ Java 17+ chứng minh nhiều repository dùng cùng bean template mà vẫn thực hiện SQL độc lập.
5. Phân biệt cấu hình template với connection pool, query timeout, transaction và per-request state; xử lý trường hợp nhiều `DataSource` hoặc nhiều yêu cầu cấu hình.
6. Nhận biết anti-pattern: `new JdbcTemplate(...)` trong mỗi phương thức, `setQueryTimeout(...)` giữa các request, giữ `Connection` lâu, dùng sai transaction manager hoặc giả định template tự cache SQL result.

## 2. Hiểu đúng ý nghĩa “khởi tạo một lần, tái sử dụng”

`JdbcTemplate` là lớp trong `org.springframework.jdbc.core`, được xây trên JDBC tiêu chuẩn. Đối tượng này chủ yếu lưu tham chiếu đến `DataSource` và những thiết lập chung cho việc thực thi SQL. Khi gọi `query(...)`, `update(...)`, `execute(...)` hoặc `batchUpdate(...)`, nó sẽ điều phối connection, statement, result set, callback và dịch ngoại lệ SQL.

~~~text
                  ApplicationContext
                         |
                         v
                  DataSource bean
                  (pool/connection factory)
                         |
                         v
                JdbcTemplate bean
                (configured once)
                     /       \
                    /         \
                   v           v
          BookReadRepository   BookWriteRepository
                   \           /
                    v         v
                     BookService
                         |
                    Controller/Job

Runtime:
  query A -> JdbcTemplate -> obtain transaction-aware Connection -> SQL -> release
  query B -> JdbcTemplate -> obtain transaction-aware Connection -> SQL -> release
~~~

Một instance template dùng chung nghĩa là cùng chính sách thực thi SQL và cùng nguồn cấp kết nối; **không có shared session cho mọi request**.

| Đối tượng | Có thể dùng chung như singleton? | Lý do |
| --- | --- | --- |
| `JdbcTemplate` đã cấu hình | Có, thông thường | Sau khi cấu hình hoàn tất, các phương thức vận hành đồng thời không cần sửa cấu hình template |
| `NamedParameterJdbcTemplate` đã cấu hình | Có, thông thường | Wrapper dùng chung JDBC operations đã cấu hình |
| `JdbcClient` được cấu hình | Có, thông thường | API fluent tạo statement specification riêng cho từng thao tác |
| `DataSource`/connection pool | Có, thông thường | Factory/pool điều phối các connection theo nhu cầu |
| JDBC `Connection` thực tế | Không nên giữ trong singleton repository | Có trạng thái session/transaction; cần mượn/trả theo operation |
| `PreparedStatement` hoặc `ResultSet` | Không | Tài nguyên gắn connection và lần thực thi cụ thể |
| `RowMapper` không có mutable state | Có thể tái sử dụng | Mapping phụ thuộc từng hàng, không ghi state request vào field |
| `RowMapper` có mutable state request | Không chia sẻ nếu không đồng bộ phù hợp | Dễ race khi nhiều query chạy song song |

**Thread-safe một khi đã cấu hình** không đồng nghĩa với an toàn nếu một thread liên tục gọi setter như `setQueryTimeout(...)` trong lúc thread khác đang truy vấn. **Hãy hoàn tất các setter ở bước khởi tạo**, rồi coi bean như cấu hình bất biến trong thời gian phục vụ request.

### 2.1. Vì sao không new JdbcTemplate trong mỗi query?

Ví dụ hoạt động nhưng không có lợi:

~~~java
// Anti-pattern: tạo lại template ngay trong từng business operation.
public String findTitle(long id) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    return template.queryForObject(
            "SELECT title FROM books WHERE id = ?",
            String.class, id);
}
~~~

`new JdbcTemplate(dataSource)` không tự mở JDBC connection ngay như `DriverManager.getConnection(...)`, và bản thân template khá nhẹ. Vì vậy gọi đó là “connection leak” trong mọi trường hợp là **không chính xác**. Vấn đề là tạo object thừa, lặp cấu hình, khó nhất quán `queryTimeout`/`fetchSize`/exception translation và làm dependency bị đặt sai chỗ.

Cách tốt hơn:

~~~java
public class BookReadRepository {
    private final JdbcTemplate jdbc;

    public BookReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findTitle(long id) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE id = ?",
                String.class, id);
    }
}
~~~

Đây là **đoạn class minh họa**, giả sử có Spring bean `JdbcTemplate` và bảng `books`. Với ID không tồn tại, `queryForObject` có thể ném `EmptyResultDataAccessException`; nếu nghiệp vụ cho phép không có hàng thì chọn `query(...)`/`Optional` thích hợp. Sự tái sử dụng ở đây diễn ra ở field `final` nhận từ constructor, không phải tự tìm template từ `ApplicationContext` trong mỗi lần gọi.

## 3. Lifecycle chuẩn của một template

Quy trình thiết lập nên tách rõ:

1. **Tạo `DataSource`:** Cấu hình URL, driver, username, secrets, pool size, timeout, validation/health check ở application configuration.
2. **Tạo `JdbcTemplate`:** Dùng constructor `new JdbcTemplate(dataSource)` hoặc factory `@Bean`, rồi chỉnh các tùy chọn chung nếu cần.
3. **Hoàn tất cấu hình:** `setQueryTimeout`, `setFetchSize`, `setMaxRows`, exception translator hoặc các cấu hình khác trước khi bean được dùng đồng thời.
4. **Công bố bean:** Spring quản lý bean trong `ApplicationContext`. Singleton là scope mặc định cho một `@Bean`, trừ khi cấu hình khác.
5. **Tiêm vào DAO:** Mỗi repository nhận template qua constructor, lưu tham chiếu `final` và gọi `query`/`update`. Không sửa setters trên template trong business method.
6. **Dọn tài nguyên:** `JdbcTemplate` xử lý JDBC resources của từng thao tác; Spring context/pool quản lý vòng đời `DataSource`. DAO không đóng injected `DataSource` hay template khi kết thúc một request.

Lưu ý: một `JdbcTemplate` có thể được tạo **một lần trong constructor của chính DAO** từ `DataSource` được inject; tài liệu Spring cho phép cách này. Tuy vậy, nếu nhiều DAO cần cấu hình template giống nhau thì một bean dùng chung là cách đơn giản để tránh cấu hình lặp và tránh sai khác giữa DAO.

## 4. Ví dụ Java 17+ chạy được: một template, hai repository

Ví dụ sử dụng **Spring Framework 6.2.11**, Java 17+ và H2 in-memory. Đây là ứng dụng Java có Spring `ApplicationContext`, không cần chạy Spring Boot. Ta cấu hình template đúng một lần, tiêm vào hai repository rồi chạy các câu SQL độc lập.

Cấu trúc project:

~~~text
jdbc-template-reuse/
├── settings.gradle
├── build.gradle
└── src/main/java/example/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-template-reuse'
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
    mainClass = 'example.App'
}
~~~

`src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate first = context.getBean(JdbcTemplate.class);
            JdbcTemplate second = context.getBean(JdbcTemplate.class);
            BookWriter writer = context.getBean(BookWriter.class);
            BookReader reader = context.getBean(BookReader.class);

            first.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(100) NOT NULL
                    )
                    """);

            writer.insert(1L, "Spring");
            writer.insert(2L, "JDBC");

            System.out.println(
                    "Same template bean: " + (first == second));
            System.out.println("Titles: " + reader.findAllTitles());
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:books;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource source) {
            JdbcTemplate template = new JdbcTemplate(source);
            template.setQueryTimeout(10);
            return template;
        }

        @Bean
        public BookWriter bookWriter(JdbcTemplate template) {
            return new BookWriter(template);
        }

        @Bean
        public BookReader bookReader(JdbcTemplate template) {
            return new BookReader(template);
        }
    }

    public static class BookWriter {
        private final JdbcTemplate jdbc;

        public BookWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public int insert(long id, String title) {
            return jdbc.update(
                    "INSERT INTO books(id, title) VALUES (?, ?)",
                    id, title);
        }
    }

    public static class BookReader {
        private final JdbcTemplate jdbc;

        public BookReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<String> findAllTitles() {
            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    (rs, rowNum) -> rs.getString("title"));
        }
    }
}
~~~

Từ thư mục `jdbc-template-reuse`, khi có JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

Stdout của chương trình:

~~~text
Same template bean: true
Titles: [Spring, JDBC]
~~~

**Vì sao chương trình cho kết quả này?**

- `Config.dataSource()` tạo một `DataSource` cho toàn application context. `DriverManagerDataSource` chỉ phù hợp demo/test; nó **không có connection pool**.
- `Config.jdbcTemplate(DataSource)` tạo một `JdbcTemplate`, gọi `setQueryTimeout(10)` **trước khi bean được sử dụng**, sau đó trả về cho container. Spring dùng singleton scope mặc định.
- `BookWriter` và `BookReader` đều nhận cùng bean `JdbcTemplate`; chúng không tự tạo template và không giữ `Connection`.
- Lấy `context.getBean(JdbcTemplate.class)` hai lần trả về cùng reference, nên `first == second` là `true`. Điều này chứng minh **identity của bean** trong context, không chứng minh có một connection duy nhất.
- `writer.insert(...)` dùng parameter placeholder `?`; `reader.findAllTitles()` dùng `RowMapper`, một callback biến từng hàng SQL thành `String`. `ORDER BY id` giúp thứ tự kết quả ổn định.
- Template tự lấy/release JDBC connection cho từng thao tác. Nếu ứng dụng đặt những thao tác vào một Spring-managed transaction phù hợp, template có thể dùng connection bound với transaction thay vì mượn connection độc lập.
- `try-with-resources` đóng Spring context khi kết thúc; trong hệ thống thật context thường sống đến lúc ứng dụng shutdown.

**Giới hạn mẫu:** Chương trình cố ý không mở transaction cho hai lệnh INSERT, nhằm tập trung minh họa lifecycle và reuse của template. Nếu có yêu cầu “hai INSERT cùng thành công hoặc rollback”, cần cấu hình transaction manager và service boundary như mục 8. H2 có thể khác PostgreSQL/MySQL/Oracle về dialect và transaction behavior.

## 5. Cấu hình template một lần: những thuộc tính nào cần quan tâm?

`JdbcTemplate` cho phép điều chỉnh một số thuộc tính ảnh hưởng cách tạo/điều khiển JDBC statement. Đặt chúng trong `@Bean` hoặc cấu hình Boot khi khởi động, **không thay đổi mỗi request**.

~~~java
@Bean
JdbcTemplate jdbcTemplate(DataSource source) {
    JdbcTemplate jdbc = new JdbcTemplate(source);
    jdbc.setQueryTimeout(10);   // giây; ảnh hưởng Statement timeout
    jdbc.setFetchSize(200);     // hint cho driver về số hàng mỗi lần fetch
    jdbc.setMaxRows(500);       // giới hạn số hàng mà Statement trả về
    return jdbc;
}
~~~

Đoạn trên nằm trong `@Configuration` đã có `DataSource`, là ví dụ cấu hình chứ không phải chương trình độc lập. Các con số **chỉ minh họa**, không phải cấu hình tốt nhất cho mọi hệ thống.

| Tùy chọn | Ý nghĩa | Cần tránh |
| --- | --- | --- |
| `setQueryTimeout(int seconds)` | Yêu cầu JDBC statement timeout; driver/DB quyết định cách thực thi | Tưởng đây là HTTP timeout, transaction timeout hoặc SLA end-to-end |
| `setFetchSize(int rows)` | Hint số hàng driver nên lấy mỗi lần với query result | Tưởng nó tự phân trang SQL hoặc luôn giảm memory |
| `setMaxRows(int rows)` | Giới hạn số hàng JDBC statement có thể trả về | Áp dụng chung lên template dùng cả truy vấn cần đầy đủ dữ liệu |
| `setExceptionTranslator(...)` | Tùy chỉnh cách chuyển `SQLException` thành `DataAccessException` | Tự bắt SQLException mọi nơi rồi mất thống nhất exception contract |
| `setIgnoreWarnings(boolean)` | Kiểm soát xử lý `SQLWarning` | Xem mọi warning là lỗi nghiêm trọng mà không hiểu driver và workload |

**Timeout:** Theo JDBC và Spring, `setQueryTimeout` là thiết lập cho statement. Nếu có transaction timeout do Spring quản lý, thời gian transaction còn lại có thể ghi đè timeout của template. Đừng dựa vào template timeout để thay cho timeout kết nối, thời gian chờ pool, HTTP deadline hay transaction isolation.

**Fetch size:** Là hint phụ thuộc driver/DB/cursor và trạng thái transaction; không đồng nghĩa truy vấn chỉ trả `200` dòng. Với dữ liệu lớn, bạn vẫn cần phân trang, streaming/callback có kiểm soát hoặc giới hạn business query. Thử nghiệm trên driver thực.

**Max rows:** Hữu ích cho template dành riêng cho màn hình tìm kiếm chỉ cho xem một số bản ghi, nhưng có thể gây bất ngờ nếu dùng cùng template cho truy vấn báo cáo cần mọi hàng. Hãy đặt giới hạn trong SQL khi cần ý nghĩa business rõ ràng; nếu policy khác nhau, cấu hình template riêng có chủ đích.

### 5.1. Không thay đổi cấu hình bean đã được chia sẻ khi xử lý request

~~~java
// Sai: hai request có thể đồng thời thay đổi queryTimeout trên cùng bean.
public List<Book> search(boolean urgent) {
    jdbc.setQueryTimeout(urgent ? 1 : 30);
    return jdbc.query(SQL, bookRowMapper);
}
~~~

Đây chỉ là **anti-pattern minh họa**, giả sử `SQL` và `bookRowMapper` tồn tại. Trong một ứng dụng nhiều thread, request A thay đổi timeout cho request B, khiến hành vi không dự đoán được. `JdbcTemplate` an toàn cho các **phương thức thực thi sau khi cấu hình đã ổn định**, không bảo đảm việc thay đổi các setter trên một bean đang dùng chung là an toàn.

Cách sửa theo mức nhu cầu:

1. Nếu policy chung: đặt timeout một lần trong config.
2. Nếu khác transaction/use case: cân nhắc timeout ở transaction boundary (`@Transactional(timeout = ...)`) nếu phù hợp semantics.
3. Nếu cần nhóm query có cấu hình hoàn toàn khác: tạo **hai bean `JdbcTemplate`** được cấu hình riêng từ cùng `DataSource`, inject bằng qualifier.
4. Nếu cần policy theo từng statement: sử dụng API JDBC/statement callback phù hợp, bảo đảm timeout không bị thay đổi qua field của singleton template.

Không tạo hàng trăm template theo từng request chỉ để thay timeout; cũng không sửa trên bean global rồi cố “set lại” trong `finally`, vì các thread vẫn có thể đan xen.

## 6. Spring Boot: thường không cần tự new hay @Bean JdbcTemplate

Trong Spring Boot với `spring-boot-starter-jdbc` (hoặc starter kéo theo JDBC infrastructure), JDBC driver và cấu hình `DataSource` hợp lệ, Boot thường **auto-configure `JdbcTemplate` và `NamedParameterJdbcTemplate`**. Spring Boot hiện cũng có thể auto-configure `JdbcClient` từ `NamedParameterJdbcTemplate` tương ứng.

Repository chỉ cần:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    private final JdbcTemplate jdbc;

    public ProductJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int rename(long id, String newName) {
        return jdbc.update(
                "UPDATE products SET name = ? WHERE id = ?",
                newName, id);
    }
}
~~~

Đây là class trong ứng dụng Spring Boot đã có bảng `products` và bean `JdbcTemplate`, không phải chương trình tự chạy. Spring constructor-inject template có sẵn. Với một constructor, không bắt buộc ghi `@Autowired`.

Spring Boot cho phép thiết lập một số thuộc tính template bằng `spring.jdbc.template.*`, ví dụ:

~~~yaml
spring:
  jdbc:
    template:
      query-timeout: 10s
      fetch-size: 200
      max-rows: 500
~~~

Đây là **ví dụ thuộc tính cấu hình**, không khuyến nghị áp dụng đồng loạt các giá trị trên. Nếu đặt `max-rows` ở cấu hình dùng chung, mọi consumer template chịu cùng chính sách giới hạn, dễ làm mất dữ liệu mong muốn trong báo cáo. Cần hiểu workload trước khi chọn giá trị.

**Khi nào viết `@Bean` riêng?**

- Spring Framework thuần chưa có auto-configuration;
- Ứng dụng có nhiều `DataSource` và cần template theo từng DB;
- Cần custom behavior mà các property/customizer tiêu chuẩn không đáp ứng;
- Cần nhóm template có policy khác nhau (ví dụ reporting và operational).

Nếu tự khai báo `JdbcTemplate` trong Boot, xem xét điều kiện auto-configuration: bean tự định nghĩa có thể khiến auto-configuration lùi lại. Tránh tạo hai bean cùng type khiến injection không rõ ràng. Đừng tự khai báo `@Bean` chỉ để nhận lại một bean Boot đã cung cấp.

### 6.1. NamedParameterJdbcTemplate và JdbcClient có chia sẻ JdbcTemplate không?

Có thể cấu hình `NamedParameterJdbcTemplate` bọc **chính** JDBC operations đã cấu hình:

~~~java
@Bean
NamedParameterJdbcTemplate namedJdbc(JdbcTemplate classic) {
    return new NamedParameterJdbcTemplate(classic);
}
~~~

`NamedParameterJdbcTemplate` hỗ trợ SQL dùng `:name`, rồi chuyển sang JDBC operations. Khi tạo wrapper từ `classic`, policy của template nền được kế thừa. Cần import `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate`.

`JdbcClient` là fluent façade cho thao tác JDBC; có thể tạo từ `DataSource` hoặc template thích hợp. **Tạo từ cùng `DataSource` không tự chứng minh wrapper đang tham chiếu đến cùng object `JdbcTemplate`**; điều quan trọng là bạn chọn cách wiring rõ ràng và cấu hình nhất quán. Không cần tạo client mới trong từng business method nếu Spring đã auto-configure bean đó.

## 7. Reuse template không phải reuse Connection hoặc ResultSet

Một thao tác điển hình:

~~~text
Repository.findById(...)
  -> JdbcTemplate.query(...)
     -> DataSourceUtils.getConnection(dataSource)
        -> current transaction-bound connection if available
        -> otherwise borrow/get from DataSource
     -> prepare statement and bind parameters
     -> execute SQL
     -> map ResultSet row(s)
     -> close Statement/ResultSet
     -> release connection when appropriate
  -> repository receives object/DTO/list
~~~

Các điểm cần nhớ:

- `JdbcTemplate` giữ tham chiếu đến `DataSource`, không giữ một connection sống mãi; với pool, mỗi operation mượn connection và trả pool khi xong, trừ khi đang có transaction giữ connection.
- `JdbcTemplate` không tự cache kết quả query; cache kết quả là trách nhiệm khác (cache application/DB) và cần chính sách invalidation rõ ràng.
- `RowMapper` được gọi cho các hàng trong kết quả hiện tại; tránh dùng một `ArrayList` field trong mapper singleton để tích lũy kết quả giữa request.
- Template xử lý phần lớn mã `try/finally` và dịch `SQLException`; bạn vẫn phải viết SQL, bảo vệ input, ánh xạ đúng cột và thiết kế index/pagination.
- Một template dùng chung không biến JDBC blocking thành non-blocking. Với reactive SQL, R2DBC sử dụng `ConnectionFactory` và API riêng.

### 7.1. Connection pool vẫn là tài nguyên khác

`JdbcTemplate` không phải pool. Với production, `DataSource` thường là pooled `HikariDataSource` được Boot quản lý. Pool size, connection timeout, max lifetime và database connection limits ảnh hưởng hành vi đồng thời.

Ví dụ cấu hình `application.yml` cho database PostgreSQL (giả sử driver, DB, credentials đã được cấp):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: app_user
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

Password nên đến từ environment/secrets manager, không ghi trong DAO. Cấu hình trên là gợi ý bố cục, không tự tạo DB hay user. Đặt pool size dựa vào giới hạn database và đo thực tế; nhiều template dùng chung **không** có nghĩa phải tăng pool tương ứng.

Tránh tạo `HikariDataSource` bên trong mỗi DAO và tránh gọi `close()` trên `DataSource` được inject khi một request kết thúc: pool thuộc lifecycle của application context.

## 8. Reuse template và ranh giới transaction

Tái sử dụng cùng template **không có nghĩa mọi method call luôn nằm trong cùng transaction**. Transaction thuộc tầng nghiệp vụ và transaction manager.

Với JDBC imperative, `DataSourceTransactionManager` hoặc `JdbcTransactionManager` quản lý connection trong transaction cho `DataSource` tương ứng. `JdbcTemplate` dùng `DataSourceUtils` nên sẽ lấy đúng connection đã bind khi được gọi từ transaction hợp lệ.

~~~text
Service @Transactional method
     |
     +--> repositoryA.insert()  --\
     |                              } same Spring-managed JDBC transaction
     +--> repositoryB.update()  --/
     |
 commit or rollback
~~~

Ví dụ dưới là **mã minh họa tích hợp**, giả sử repository và transaction manager đã cấu hình:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookRegistrationService {
    private final BookWriter writer;
    private final AuditWriter audit;

    public BookRegistrationService(
            BookWriter writer, AuditWriter audit) {
        this.writer = writer;
        this.audit = audit;
    }

    @Transactional
    public void register(long id, String title) {
        writer.insert(id, title);
        audit.record(id, "CREATED");
    }
}
~~~

Hai repository phải dùng template được cấu hình với **cùng `DataSource` được transaction manager điều phối**; `AuditWriter` là class minh họa của ứng dụng. Chỉ có `@Transactional` mà chưa bật transaction infrastructure hoặc gọi qua proxy sẽ không tự bảo đảm rollback.

Nếu một repo tự gọi `DriverManager.getConnection(...)`, đó là connection nằm ngoài transaction do Spring điều phối. Nếu có nhiều `DataSource`, cũng không tự atomic vì hai pool cùng trỏ đến một server.

Các lưu ý quan trọng:

- Với chế độ proxy mặc định, lời gọi phải đi qua Spring bean proxy; `this.register(...)` từ cùng object có thể bypass interceptor.
- Mặc định Spring rollback khi có `RuntimeException` hoặc `Error`; checked exception thường cần `rollbackFor` hoặc quy tắc cấu hình phù hợp.
- Transaction timeout có thể ghi đè statement timeout của template; đừng sửa `jdbc.setQueryTimeout` giữa request để đáp ứng deadline khác nhau.
- Transaction không nên giữ quá lâu vì làm tăng thời gian giữ connection/locks.
- `@Transactional(readOnly = true)` là hint, không phải lớp bảo vệ tuyệt đối ngăn SQL ghi.

## 9. Nhiều DataSource: không ép mọi truy vấn dùng một template

“Khởi tạo một template rồi tái sử dụng” áp dụng **cho một tập repository chia sẻ một cấu hình và một nguồn dữ liệu**. Nếu ứng dụng có hai database khác nhau hoặc yêu cầu chính sách SQL khác nhau, dùng nhiều template **có chủ đích**.

~~~java
@Configuration
public class MultiJdbcConfig {
    @Bean("ordersJdbc")
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource ds) {
        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.setQueryTimeout(5);
        return jdbc;
    }

    @Bean("reportsJdbc")
    JdbcTemplate reportsJdbc(
            @Qualifier("reportsDataSource") DataSource ds) {
        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.setQueryTimeout(30);
        return jdbc;
    }
}
~~~

Đây là **config minh họa**, giả sử `ordersDataSource` và `reportsDataSource` đã được định nghĩa; bổ sung imports từ `org.springframework.context.annotation`, `org.springframework.beans.factory.annotation.Qualifier`, `javax.sql.DataSource` và `JdbcTemplate`. Không phải chương trình standalone.

Repository chọn dependency rõ ràng:

~~~java
public ReportDao(
        @Qualifier("reportsJdbc") JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
~~~

Đoạn constructor minh họa nằm trong `ReportDao` với field `JdbcTemplate jdbc`; bean `ReportDao` cũng phải được Spring quản lý. Khi có nhiều `DataSource`, kiểm tra transaction manager tương ứng và đặt `@Transactional(transactionManager = "...")` nếu cần để tránh transaction áp dụng sai resource.

Một template cho mỗi `DataSource`/policy là hợp lý; một template cho mỗi HTTP request thường không có lý do thiết kế.

## 10. Unit test, integration test và bằng chứng tái sử dụng

### 10.1. Unit test cho DAO

Vì repository nhận dependency qua constructor, bạn có thể inject mock/fake `JdbcOperations` (interface mà `JdbcTemplate` triển khai) khi thiết kế DAO theo interface, hoặc inject test `JdbcTemplate` dùng H2. Với unit test không cần DB, hãy kiểm tra mapping business ở lớp service, còn SQL syntax cần integration test.

Ví dụ repository nhận abstraction:

~~~java
import org.springframework.jdbc.core.JdbcOperations;

public class BookReadDao {
    private final JdbcOperations jdbc;

    public BookReadDao(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public Long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }
}
~~~

Đây là snippet cần bảng `books` và dependency được tiêm. Có thể khởi tạo `new BookReadDao(jdbcTemplate)` trong integration test hoặc `new BookReadDao(mockJdbcOperations)` trong unit test. Không cần tạo connection thật cho mọi unit test.

### 10.2. Integration test cho bean và SQL

Các mức xác minh có ý nghĩa:

1. **Identity:** Trong một `ApplicationContext`, hai lần `getBean(JdbcTemplate.class)` trả về cùng instance khi dùng singleton bean; hai repository cùng được inject bean đó.
2. **Behavior:** Insert/query qua hai repo trả kết quả nhất quán, mapping đúng và parameter binding an toàn.
3. **Transaction:** Thử hai insert trong một service `@Transactional`, ném runtime exception rồi xác minh cả hai rollback.
4. **Pool:** Kiểm tra datasource metrics (active/idle/pending connections) dưới tải; template shared không chứng minh pool có size phù hợp.
5. **Database thật:** Nếu SQL dùng dialect/lock/transaction đặc thù, chạy trên DB tương thích production, ví dụ Testcontainers, thay vì chỉ tin H2.

Với Spring Boot, `@JdbcTest` giúp kiểm thử JDBC slice; nếu bạn cần business service và transaction wiring đầy đủ thì dùng cấu hình kiểm thử bao gồm các bean liên quan. Test chỉ khởi tạo DAO bằng `new` không thể chứng minh proxy transaction đang hoạt động.

### 10.3. Kiểm chứng concurrency

Không cần tạo một template riêng cho từng thread. Có thể đặt workload gồm nhiều request đọc/ghi song song, sau đó kiểm tra correctness, pool waiting/timeout và lỗi DB.

**Không nhầm:** Template dùng chung là an toàn, nhưng code callback của bạn có thể không an toàn nếu dùng biến shared mutable. Ví dụ `RowMapper` lưu một `StringBuilder` field dùng chung rồi append mỗi hàng từ nhiều thread là một nguồn race, dù `JdbcTemplate` hoàn toàn an toàn.

## 11. Những lỗi thường gặp và cách sửa

| Hiện tượng/nhận định | Nguyên nhân | Hành động phù hợp |
| --- | --- | --- |
| “Mỗi DAO phải có JdbcTemplate mới vì nhiều thread.” | Hiểu nhầm thread safety | Chia sẻ bean đã cấu hình; tránh mutable request state |
| “Tôi tạo JdbcTemplate mỗi query để đảm bảo sạch dữ liệu.” | Nhầm template với connection/session | Tái sử dụng template; để nó quản lý connection theo operation |
| “new JdbcTemplate(ds) mỗi lần chắc chắn leak connection.” | Đánh đồng tạo template với mở JDBC connection | Tránh tạo lặp vì khó cấu hình/không cần, nhưng phân biệt với leak thật |
| Query timeout thay đổi bất thường giữa request | Setter được gọi trên shared bean lúc runtime | Cố định config lúc startup hoặc dùng policy riêng |
| Query báo cáo mất hàng | `setMaxRows` trên template dùng chung | Dùng SQL limit có chủ đích hoặc template khác |
| Fetch size có nhưng RAM vẫn cao | Driver không stream như giả định hoặc code giữ cả List | Kiểm tra driver/cursor, transaction, projection, paging |
| `JdbcTemplate` bean không tồn tại | Chưa có auto-config, `DataSource` hoặc `@Bean` | Bổ sung cấu hình/dependencies phù hợp |
| Nhiều `JdbcTemplate` không inject được | Nhiều bean cùng type | `@Qualifier`, `@Primary` có chủ đích |
| DAO có template nhưng transaction không rollback | Sai manager/resource, self-invocation hoặc exception swallowed | Đặt transaction ở service qua proxy và test rollback |
| Pool connection cạn | Transaction dài, query chậm, pool quá nhỏ hoặc code tự mở connection | Quan sát metrics, tối ưu SQL và sửa lifecycle |
| SQL injection | Ghép input trực tiếp vào SQL | Dùng `?`, named bind và allowlist identifier |
| Test H2 xanh nhưng PostgreSQL lỗi | Khác dialect/case/collation/isolation | Test DB tương thích production |

### 11.1. Anti-pattern: thay đổi timeout rồi khôi phục

~~~java
// Không an toàn với một JdbcTemplate dùng chung:
int old = jdbc.getQueryTimeout();
try {
    jdbc.setQueryTimeout(1);
    return jdbc.query(SQL, mapper);
} finally {
    jdbc.setQueryTimeout(old);
}
~~~

Dù có `finally`, hai thread có thể interleave: A đổi timeout, B chạy query, C đổi lại giá trị khác. Giải pháp là **không mutate shared bean khi request đang chạy**.

### 11.2. Anti-pattern: giữ một Connection trong repository

~~~java
// Không nên làm trong singleton repository:
class BadDao {
    private final java.sql.Connection sharedConnection;

    BadDao(javax.sql.DataSource source)
            throws java.sql.SQLException {
        this.sharedConnection = source.getConnection();
    }
}
~~~

Connection có session/transaction state, có thể bị đóng, giữ pool slot lâu và không an toàn cho concurrent operations. Cần template hoặc mượn/trả connection trong từng operation với `DataSourceUtils` nếu buộc phải dùng JDBC thuần.

### 11.3. Anti-pattern: tự tìm bean bên trong DAO

~~~java
// Không nên giải quyết dependency bằng service locator mỗi lần:
JdbcTemplate jdbc =
        applicationContext.getBean(JdbcTemplate.class);
~~~

Code dựa vào container global trong thân method, làm dependency khó nhìn và khó unit test. Dùng constructor injection:

~~~java
public BookDao(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
~~~

Hai đoạn trên là snippet minh họa, không phải class hoàn chỉnh. Composition root/`@Configuration` chịu trách nhiệm lắp dependency; DAO chỉ thực thi SQL.

## 12. Các câu hỏi tự kiểm tra và bài tập

1. `JdbcTemplate` có thể chia sẻ an toàn vì sao? Điều kiện “once configured” giới hạn việc gọi setter lúc nào?
2. So sánh vòng đời `JdbcTemplate`, `DataSource` và `Connection`. Cái nào chứa trạng thái transaction của một JDBC operation?
3. Tại sao hai DAO cùng inject `JdbcTemplate` chưa chắc hai phương thức cùng một transaction?
4. Sửa DAO đang `new JdbcTemplate(dataSource)` trong mỗi request sang constructor injection, rồi cấu hình `@Bean` trong Spring.
5. Thay `setQueryTimeout(10)` bằng một policy cho reporting có timeout khác. Bạn sẽ chọn template bean thứ hai hay transaction timeout? Giải thích theo use case.
6. Tạo thêm `BookStatisticsRepository` trong ví dụ runnable, nhận template đã cấu hình, query `COUNT(*)`; kiểm tra vẫn có đúng một bean `JdbcTemplate` và kết quả đúng.
7. Viết integration test: một service gọi hai DAO cùng datasource, thao tác thứ hai ném runtime exception; xác nhận cả hai không commit. Nếu không rollback, nên kiểm tra những điều gì?
8. Trên hệ thống có database OLTP và reporting, vẽ sơ đồ hai `DataSource`, hai template, hai transaction manager và lựa chọn bean ở mỗi DAO.

## 13. Checklist triển khai thực tế

- [ ] `DataSource`/pool được tạo trong configuration/Boot và có lifecycle rõ ràng.
- [ ] Một `JdbcTemplate` được cấu hình **đầy đủ trước khi xử lý request** rồi tái sử dụng như singleton bean.
- [ ] Repository inject `JdbcTemplate`/`JdbcOperations` qua constructor; không service-locate bean hoặc tạo template trong từng query.
- [ ] Không giữ JDBC `Connection`, `PreparedStatement`, `ResultSet` hoặc mutable request state trong singleton DAO.
- [ ] `setQueryTimeout`, `setFetchSize`, `setMaxRows` được hiểu đúng và kiểm chứng theo driver/workload.
- [ ] Không sửa setter của template global khi request đồng thời đang thực thi.
- [ ] Nếu Boot đã auto-configure template, ưu tiên inject trực tiếp, không tạo bean trùng vô cớ.
- [ ] Nếu có nhiều datasource/policy, dùng các template bean riêng với `@Qualifier`.
- [ ] Transaction boundary ở service, đúng transaction manager và được gọi qua proxy; kiểm thử rollback thật.
- [ ] Dùng bind parameters để tránh SQL injection; query có index, pagination và timeout phù hợp.
- [ ] Quan sát JDBC metrics, pool saturation, slow query và exception translation dưới tải thực.

**Ghi nhớ:** Hãy **cấu hình một `JdbcTemplate` cho mỗi `DataSource`/chính sách hợp lý, rồi chia sẻ bean đã hoàn tất cấu hình**. `JdbcTemplate` thread-safe trong việc thực thi sau startup; `DataSource` chịu trách nhiệm cấp kết nối; Spring transaction quản lý phạm vi commit/rollback; repository chỉ nhận dependency và thực hiện SQL.

## Tài liệu chính thức

- [Spring Framework — JdbcTemplate Best Practices](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — Using JDBC with Spring](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — JDBC Connections and DataSource](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Boot — SQL Databases, JdbcTemplate and JdbcClient](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
