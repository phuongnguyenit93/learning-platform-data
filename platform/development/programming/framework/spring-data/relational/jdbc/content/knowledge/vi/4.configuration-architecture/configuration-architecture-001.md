# Auto-configuration của Spring Boot cho Spring Data JDBC

## 1. Auto-configuration giải quyết vấn đề gì?

Khi xây dựng ứng dụng truy cập cơ sở dữ liệu quan hệ bằng JDBC, ta thường phải cấu hình nhiều thành phần: `DataSource` (nguồn kết nối), JDBC driver, `JdbcTemplate`, `NamedParameterJdbcTemplate`, hạ tầng ánh xạ dữ liệu, transaction manager và repository. **Spring Boot auto-configuration** tự tạo các bean hạ tầng thông dụng khi nhận thấy ứng dụng đáp ứng điều kiện tương ứng.

Trong ứng dụng có dependency **Spring Data JDBC**, Boot có thể cấu hình đường đi từ kết nối database đến repository:

~~~mermaid
flowchart TD
    A["Spring Boot application<br/>@SpringBootApplication"] --> B["Auto-configuration<br/>đánh giá điều kiện"]
    B --> C["DataSource<br/>kết nối/pool JDBC"]
    C --> D["JdbcTemplate<br/>NamedParameterJdbcTemplate"]
    D --> E["Hạ tầng Spring Data JDBC<br/>mapping, conversions, dialect"]
    E --> F["BookRepository<br/>CrudRepository"]
    F --> G["Thực thi SQL JDBC"]
    G --> C
    C --> H[("Relational Database")]
    B --> I["Transaction Manager"]
    I --> C
~~~

Một lớp ứng dụng thường **không cần tự khai báo** `@Bean DataSource`, `@Bean JdbcTemplate` hoặc `@EnableJdbcRepositories` chỉ để thực hiện thao tác JDBC thông thường. Tuy nhiên, **tự cấu hình không có nghĩa là tự tạo bảng, thiết kế aggregate hay tự chọn database**. Những phần đó vẫn là trách nhiệm cấu hình, schema và thiết kế dữ liệu của ứng dụng.

Bài viết sử dụng quy ước quen thuộc của **Spring Boot 3.x** và **Spring Data JDBC**. Tên một số lớp cấu hình và các điều kiện chi tiết có thể khác giữa các phiên bản; khi cần tùy biến sâu phải đối chiếu đúng phiên bản ứng dụng.

## 2. Điều kiện để auto-configuration hoạt động

`@SpringBootApplication` bao gồm cơ chế `@EnableAutoConfiguration`. Khi tạo `ApplicationContext`, Spring Boot đọc các auto-configuration có trên classpath và quyết định đăng ký bean theo các điều kiện phổ biến:

- **`@ConditionalOnClass`**: thư viện hoặc lớp tương ứng phải có trên classpath.
- **`@ConditionalOnBean` / `@ConditionalOnSingleCandidate`**: phải có bean thỏa mãn điều kiện, đôi khi cần xác định được một bean ưu tiên.
- **`@ConditionalOnMissingBean`**: chỉ tạo bean mặc định khi ứng dụng chưa cung cấp bean tương đương.
- **`@ConditionalOnProperty`**: bật hoặc tắt một nhánh cấu hình bằng property.
- Những điều kiện khác về môi trường, tài nguyên, loại ứng dụng hoặc thứ tự khởi tạo cũng có thể ảnh hưởng.

Đây là cơ chế **có điều kiện**, không phải một danh sách bean luôn tồn tại ở mọi ứng dụng. Thiếu driver, không có `DataSource` phù hợp, cấu hình hai database thiếu bean chính hoặc tự vô hiệu hóa repository đều có thể làm cho một phần hạ tầng không được tạo.

### Dependency tối thiểu

Trong ứng dụng Spring Boot sử dụng Gradle và PostgreSQL:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

`spring-boot-starter-data-jdbc` mang vào Spring Data JDBC cùng các thành phần Spring JDBC, quản lý transaction và dependency hạ tầng liên quan. Driver JDBC của hệ quản trị thực tế vẫn cần có ở runtime. Nếu ứng dụng dùng dependency management của Spring Boot, thông thường không cần tự khai báo version cho các dependency mà Boot đang quản lý.

Để thực hành với H2 in-memory, thay driver:

~~~groovy
runtimeOnly("com.h2database:h2")
~~~

**Chỉ thêm driver chưa đủ để kết nối tới PostgreSQL:** database phải tồn tại, thông tin kết nối phải hợp lệ và ứng dụng phải truy cập được host/port tương ứng.

## 3. Những lớp auto-configuration quan trọng

Các tên dưới đây là những auto-configuration tiêu biểu trong Spring Boot 3.x:

| Auto-configuration | Trách nhiệm chính | Điều kiện điển hình |
|---|---|---|
| `DataSourceAutoConfiguration` | Tạo `DataSource`, dùng pool kết nối khi có thư viện và cấu hình thích hợp | Có hỗ trợ JDBC và cấu hình nguồn dữ liệu đủ điều kiện |
| `JdbcTemplateAutoConfiguration` | Tạo `JdbcTemplate` và `NamedParameterJdbcTemplate` khi cần | Có `DataSource` thích hợp, chưa có bean tương đương |
| `JdbcRepositoriesAutoConfiguration` | Kích hoạt quét/tạo Spring Data JDBC repository và hạ tầng liên quan | Có Spring Data JDBC cùng những bean/cấu hình cần thiết |
| `DataSourceTransactionManagerAutoConfiguration` | Cấu hình transaction manager JDBC mặc định | Có `DataSource` phù hợp, chưa có transaction manager thay thế |
| `TransactionAutoConfiguration` | Hỗ trợ transaction khai báo trong ngữ cảnh Boot | Có hạ tầng quản lý transaction tương ứng |
| `SqlInitializationAutoConfiguration` | Tích hợp chạy script `schema.sql` và `data.sql` khi phù hợp | Database, script và chế độ khởi tạo đáp ứng điều kiện |
| Auto-configuration Flyway/Liquibase | Tích hợp công cụ migration khi được cài | Có thư viện migration và cấu hình phù hợp |

Có thể hiểu kiến trúc theo từng tầng: **DataSource → Spring JDBC → Spring Data JDBC → Repository**; transaction manager phối hợp với JDBC để quản lý giao dịch.

### 3.1. DataSource: điểm xuất phát

`DataSource` là interface thuộc JDBC (`javax.sql.DataSource`), cung cấp kết nối `Connection`. Khi dùng starter JDBC thông dụng, Boot thường sử dụng **HikariCP** làm connection pool nếu nó có trên classpath và chưa có cấu hình thay thế.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/library
    username: library_user
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
~~~

Boot thường suy ra JDBC driver từ URL khi driver phù hợp có trên classpath. Không nhất thiết phải đặt `spring.datasource.driver-class-name` trong cấu hình phổ biến. `spring.datasource.hikari.*` chỉ có tác dụng khi nguồn dữ liệu thực tế sử dụng HikariCP.

Connection pool quản lý kết nối vật lý để tái sử dụng; pool **không phải repository**, không tự tạo bảng và không định nghĩa logic nghiệp vụ hay transaction.

### 3.2. JdbcTemplate và NamedParameterJdbcTemplate

Khi `DataSource` có sẵn và các điều kiện phù hợp, Spring Boot có thể đăng ký bean `JdbcTemplate` và `NamedParameterJdbcTemplate`. Ứng dụng chỉ cần constructor injection:

~~~java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class SqlBookReader {
    private final NamedParameterJdbcTemplate jdbc;

    public SqlBookReader(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
~~~

`JdbcTemplate` hỗ trợ `?` theo vị trí, còn `NamedParameterJdbcTemplate` hỗ trợ `:tenThamSo`. Cả hai là **Spring JDBC**, khác với repository Spring Data JDBC ở tầng trừu tượng cao hơn. Spring Data JDBC dùng hạ tầng Spring JDBC phía dưới; nó không cần `EntityManager` hoặc Hibernate.

Một số tùy chỉnh template có thể thực hiện qua property:

~~~yaml
spring:
  jdbc:
    template:
      query-timeout: 5s
      fetch-size: 100
~~~

`fetch-size` là gợi ý cho JDBC driver, không phải cam kết trả từng batch chính xác 100 hàng. `query-timeout` giới hạn thời gian thực thi JDBC statement khi driver hỗ trợ; đây không phải timeout bao trùm mọi thao tác network/request/transaction.

### 3.3. Hạ tầng mapping và repository của Spring Data JDBC

Khi các điều kiện được đáp ứng, phần cấu hình repository dùng những thành phần Spring Data JDBC như:

- **`JdbcMappingContext`**: metadata ánh xạ entity và aggregate.
- **`JdbcCustomConversions`** và conversion service: chuyển đổi kiểu Java với giá trị đọc/ghi database.
- **`JdbcAggregateTemplate`** cùng các thành phần data access bên dưới: thao tác lưu/tải aggregate.
- **`Dialect`**: hỗ trợ các khác biệt về SQL của hệ quản trị cơ sở dữ liệu được Spring Data JDBC nhận diện.

Những thành phần này cho phép repository ánh xạ đối tượng và gửi SQL cần thiết. Tuy nhiên, Spring Data JDBC **không duy trì persistence context theo cơ chế JPA**, không tự cung cấp lazy loading cho tất cả quan hệ và không tự giải quyết mọi truy vấn báo cáo nhiều bảng.

### 3.4. Transaction manager JDBC

Khi có một `DataSource` phù hợp và chưa có transaction manager thay thế, Boot có thể tạo transaction manager JDBC, thường dựa trên `JdbcTransactionManager` / `DataSourceTransactionManager`.

Repository Spring Data JDBC và `JdbcTemplate` có thể cùng tham gia transaction khai báo qua `@Transactional` khi sử dụng chung hạ tầng `DataSource` và transaction manager tương thích. Với nhiều `DataSource` hoặc nhiều transaction manager, cần chỉ định rõ lựa chọn bằng `@Primary`, `@Qualifier` hoặc tên transaction manager trong cấu hình transaction phù hợp.

## 4. Ví dụ hoàn chỉnh: ứng dụng H2 với repository tự cấu hình

Ta tạo ứng dụng quản lý sách nhỏ để thấy rõ phần Boot tự tạo và phần ứng dụng phải chuẩn bị.

### 4.1. Cấu trúc package và tài nguyên

~~~text
src/main/
├── java/com/example/catalog/
│   ├── CatalogApplication.java
│   ├── Book.java
│   ├── BookRepository.java
│   └── BookService.java
└── resources/
    ├── application.yml
    └── schema.sql
~~~

Đặt các class trong cùng package gốc `com.example.catalog` hoặc các package con giúp Boot phát hiện component và repository bằng phạm vi quét thông dụng.

### 4.2. Dependencies và application.yml

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("com.h2database:h2")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog
  datasource:
    url: jdbc:h2:mem:catalogdb;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  sql:
    init:
      mode: embedded
~~~

Trong ví dụ này H2 là **database nhúng trong bộ nhớ**. Chế độ script initialization `embedded` cho phép Boot chạy `schema.sql` và `data.sql` với database embedded phù hợp; đây là chế độ mặc định thông dụng. Cờ `DB_CLOSE_DELAY=-1` là cấu hình riêng của H2 để giữ database in-memory trong vòng đời JVM.

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    author VARCHAR(120) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

**Bảng xuất hiện nhờ script SQL.** Việc đặt `@Table("books")` trên entity không khiến Spring Data JDBC tự sinh lệnh `CREATE TABLE`.

### 4.3. Aggregate root và repository

`Book.java`:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
        @Id Long id,
        String title,
        String author,
        BigDecimal price
) {}
~~~

`BookRepository.java`:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository extends CrudRepository<Book, Long> {
    List<Book> findByAuthor(String author);
}
~~~

Spring Data JDBC hiểu `Book` là aggregate root có khóa chính `id` và thao tác với bảng `books`. Repository interface kế thừa `CrudRepository`; với cấu hình mặc định phù hợp, **không cần viết class triển khai** hoặc thêm `@EnableJdbcRepositories`.

`findByAuthor` là derived query theo thuộc tính `author`, thuộc phạm vi query derivation của Spring Data JDBC. Khi yêu cầu SQL phức tạp hơn, có thể sử dụng query được khai báo tường minh hoặc template JDBC.

### 4.4. Service dùng repository và transaction

`BookService.java`:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public Book create(String title, String author, BigDecimal price) {
        return books.save(new Book(null, title, author, price));
    }

    @Transactional(readOnly = true)
    public List<Book> booksByAuthor(String author) {
        return books.findByAuthor(author);
    }
}
~~~

Với `id == null` và cột identity, Spring Data JDBC thực hiện INSERT, lấy khóa được tạo và trả về `Book` có ID. Vì `Book` là record bất biến, **đối tượng được trả về từ `save` có thể khác đối tượng truyền vào**; cần sử dụng giá trị trả về.

`@Transactional` tạo ranh giới giao dịch khi lời gọi đi qua Spring proxy và transaction manager được cấu hình đúng. Service không phải tự mở/đóng JDBC connection.

`CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Trong ví dụ không có `@Bean DataSource`, `@Bean JdbcTemplate`, `@EnableJdbcRepositories` hoặc `@Bean PlatformTransactionManager`. Boot và Spring Data JDBC chuẩn bị bean cần thiết khi điều kiện đáp ứng.

### 4.5. Quá trình khởi động ở mức khái niệm

1. Boot đọc `application.yml` và dependency trên classpath.
2. Auto-configuration xác định có thể tạo `DataSource` H2.
3. JDBC auto-configuration cung cấp `JdbcTemplate` và `NamedParameterJdbcTemplate` nếu chưa có bean thay thế.
4. Cơ chế SQL initialization chạy `schema.sql` khi chế độ script cho phép.
5. Spring Data JDBC tạo hạ tầng mapping, conversion, dialect và proxy repository.
6. Spring đăng ký `BookService`, tiêm `BookRepository`.
7. Khi gọi `save(...)` hay `findByAuthor(...)`, Spring Data JDBC sử dụng JDBC để thực thi SQL qua nguồn kết nối đã cấu hình.

Đây là **mối quan hệ phụ thuộc và kết quả quan sát được**, không phải lời hứa mọi class cấu hình chạy tuần tự đúng từng số bước. Boot dùng cơ chế sắp xếp auto-configuration và lifecycle bean/initializer riêng.

## 5. Chuyển sang PostgreSQL: kết nối, schema và migration

Với database bên ngoài như PostgreSQL, thay JDBC driver và cung cấp cấu hình:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/library}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10

  sql:
    init:
      mode: never
~~~

Các biến môi trường `DB_USERNAME` và `DB_PASSWORD` cần được cung cấp khi chạy; không hard-code mật khẩu production vào mã nguồn. `spring.sql.init.mode=never` thể hiện ý định không dùng script initializer mặc định của Boot trên môi trường đó.

### Những gì Boot tự làm và ứng dụng vẫn phải làm

| Công việc | Boot/Spring Data JDBC tự động hóa? | Trách nhiệm của ứng dụng |
|---|---|---|
| Tạo `DataSource` từ driver, URL và pool | Có, nếu các điều kiện đủ | Driver, cấu hình và database sẵn sàng |
| Cung cấp template JDBC và repository | Có, nếu dependency và bean phù hợp | Repository interface và package quét |
| Ánh xạ `Book` với bảng `books` | Có cơ chế mapping | Thiết kế aggregate, khóa, cột và kiểu dữ liệu |
| Tạo bảng từ `@Table` tương tự DDL generation của JPA | **Không** | Script hoặc migration tạo schema |
| Tự áp dụng mọi thay đổi schema giữa phiên bản | **Không** | Thiết kế và vận hành migration |
| Quản lý transaction JDBC mặc định | Có thể | Chỉ định ranh giới nghiệp vụ và chính sách rollback |
| Tạo index tối ưu cho mỗi truy vấn | **Không** | Thiết kế index, theo dõi query plan |

### Chọn script initialization hay migration

Spring Boot có cơ chế `schema.sql`, `data.sql` với `spring.sql.init.mode`:

- `embedded`: chạy script khi có embedded database thích hợp; đây là giá trị mặc định thường dùng.
- `always`: cho phép chạy script với cả database bên ngoài.
- `never`: tắt cơ chế script initialization này.

Với database cần duy trì lâu dài, **Flyway** hoặc **Liquibase** thường phù hợp hơn vì chúng theo dõi version migration và hỗ trợ kiểm soát thay đổi schema. Khi dependency migration hiện diện và các điều kiện được đáp ứng, Boot có thể tự cấu hình tích hợp tương ứng.

Không nên để hai cơ chế quản lý schema cùng tạo/sửa bảng thiếu kiểm soát; hãy xác định rõ công cụ nào sở hữu việc migration.

## 6. Repository scanning và @EnableJdbcRepositories

Với cấu trúc mặc định, `@SpringBootApplication` trong package gốc xác định vị trí bắt đầu quét. Spring Data JDBC có thể tự phát hiện repository interface hợp lệ ở các package bên dưới:

~~~text
com.example.catalog
├── CatalogApplication          <-- @SpringBootApplication
├── domain
│   └── Book
├── repository
│   └── BookRepository          <-- nằm dưới package gốc
└── service
    └── BookService
~~~

Nếu repository ở ngoài phạm vi quét, có thể không có bean `BookRepository`. Một lựa chọn là đổi tổ chức package; với kiến trúc phức tạp hơn, có thể chỉ định:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@SpringBootApplication
@EnableJdbcRepositories(basePackages = "com.example.catalog.repository")
public class CatalogApplication {
    // ...
}
~~~

Trong ứng dụng đơn giản, `@EnableJdbcRepositories` thường không cần thiết. Khi cấu hình repository thủ công, phải hiểu rõ phạm vi, dependency và các bean hạ tầng đang được Boot cung cấp.

### Ứng dụng có nhiều Spring Data store

Nếu có cả Spring Data JDBC và Spring Data JPA (hoặc store khác), Spring Data có thể bật chế độ **strict repository configuration** để xác định repository nào thuộc store nào. Một interface kế thừa `CrudRepository` đơn thuần có thể cần dấu hiệu xác định hoặc phạm vi quét tường minh.

Hướng xử lý là tách package repository theo store, áp dụng annotation mapping đúng công nghệ và cấu hình phạm vi repository nếu cần. **`org.springframework.data.relational.core.mapping.Table` của Spring Data JDBC khác với `jakarta.persistence.Table` của JPA**.

## 7. Cơ chế back off: tùy chỉnh bean mà không viết lại toàn bộ hạ tầng

Boot sử dụng `@ConditionalOnMissingBean` ở nhiều vị trí để **nhường quyền cho bean do người dùng định nghĩa**.

Ví dụ tùy chỉnh `JdbcTemplate`:

~~~java
package com.example.catalog;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class JdbcConfiguration {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setFetchSize(200);
        template.setQueryTimeout(10);
        return template;
    }
}
~~~

Khi bean `JdbcTemplate` của ứng dụng đáp ứng điều kiện, Boot không cần tạo bean mặc định tương đương. Các auto-configuration khác vẫn có thể hoạt động và dùng bean do ứng dụng cung cấp.

**Lưu ý:** tự tạo bean hạ tầng có thể làm thay đổi cách Boot áp dụng property/customizer. Nếu chỉ muốn chỉnh query timeout hoặc fetch size, nên cân nhắc property `spring.jdbc.template.*` trước.

Tương tự, nếu tự tạo `DataSource`, ứng dụng phải quản lý driver, pool và lifecycle phù hợp; các lớp phía trên có thể tái sử dụng bean này khi các điều kiện đủ.

### Tắt riêng repository auto-configuration

Khi dùng Spring JDBC trực tiếp mà không muốn Boot tạo Spring Data JDBC repository:

~~~yaml
spring:
  data:
    jdbc:
      repositories:
        enabled: false
~~~

Thiết lập này tắt phần repository tự động, **không đồng nghĩa vô hiệu hóa toàn bộ `DataSource` và `JdbcTemplate`**.

Nếu thật sự cần loại trừ một auto-configuration, Boot cũng hỗ trợ `exclude`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.data.jdbc.JdbcRepositoriesAutoConfiguration;

@SpringBootApplication(exclude = JdbcRepositoriesAutoConfiguration.class)
public class CatalogApplication {}
~~~

Việc loại trừ chỉ nên thực hiện khi hiểu rõ các bean/phụ thuộc liên quan. Với nhu cầu bật/tắt repository đơn giản, property chuyên biệt thường rõ nghĩa hơn.

## 8. Auto-configuration không thay thế thiết kế aggregate

Auto-configuration dựng hạ tầng, còn quy tắc dữ liệu Spring Data JDBC vẫn cần được thiết kế.

### Aggregate root và mapping

Repository Spring Data JDBC thường quản lý **aggregate root**. Quan hệ giữa các entity trong aggregate được lưu/tải theo nguyên tắc của Spring Data JDBC, khác với JPA. Có repository bean không có nghĩa framework xử lý mọi `JOIN`, báo cáo hay chuỗi quan hệ phức tạp như mong muốn.

`@Id` xác định khóa chính, `@Table` và `@Column` (khi cần) giúp ánh xạ tên bảng/cột. Dialect hỗ trợ SQL theo database được nhận diện. Một JDBC driver hoạt động với `JdbcTemplate` **chưa chắc đủ** để Spring Data JDBC repository hỗ trợ đầy đủ dialect của hệ quản trị ít phổ biến.

### SQL thủ công và repository cùng tồn tại

Ngay trong ứng dụng có `BookRepository`, ta vẫn có thể dùng `NamedParameterJdbcTemplate` cho truy vấn báo cáo:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookReportDao {
    private final NamedParameterJdbcTemplate jdbc;

    public BookReportDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countByAuthor(String author) {
        String sql = """
                SELECT COUNT(*)
                FROM books
                WHERE author = :author
                """;

        Long count = jdbc.queryForObject(
                sql,
                new MapSqlParameterSource("author", author),
                Long.class
        );
        return count.longValue();
    }
}
~~~

Repository và DAO có thể cùng sử dụng `DataSource` do Boot cấu hình. SQL trực tiếp **không tự kích hoạt toàn bộ aggregate callbacks hoặc optimistic locking do repository quản lý**; những invariant quan trọng phải được bảo vệ tường minh nếu kết hợp hai cách ghi.

## 9. Transaction tự cấu hình và ranh giới nghiệp vụ

Giả sử cần lưu hai cuốn sách như một thao tác thống nhất:

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookBatchService {
    private final BookRepository books;

    public BookBatchService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void addPair() {
        books.save(new Book(null, "Spring JDBC", "Lan",
                new BigDecimal("120000")));
        books.save(new Book(null, "Spring Data JDBC", "Lan",
                new BigDecimal("150000")));
    }
}
~~~

Nếu transaction manager JDBC được cấu hình đúng, hai lời gọi repository tham gia cùng transaction; khi thao tác thứ hai ném ngoại lệ runtime ra ngoài phương thức, Spring thông thường rollback cả hai.

Những điểm cần hiểu:

- `@Transactional` ở **service** mô tả ranh giới nghiệp vụ rõ hơn việc giả định hai lời gọi repository riêng lẻ tự tạo một transaction chung.
- Trong cấu hình proxy mặc định, **self-invocation** (phương thức cùng bean gọi một phương thức `@Transactional` khác của chính nó) thường không đi qua proxy để mở transaction mới.
- Mặc định Spring rollback với `RuntimeException` hoặc `Error`; checked exception cần chính sách `rollbackFor` khi nghiệp vụ yêu cầu.
- Khi có nhiều `DataSource`, transaction manager JDBC cục bộ không tự điều phối giao dịch phân tán giữa các database.
- `readOnly = true` là ý định/gợi ý với hạ tầng transaction; không phải cơ chế phân quyền đọc dữ liệu tuyệt đối.

## 10. Quan sát auto-configuration thực tế

Vì điều kiện phụ thuộc classpath và các bean hiện diện, cách hữu ích nhất để biết **vì sao bean được tạo hoặc không được tạo** là đọc **Condition Evaluation Report** của ứng dụng.

### 10.1. Bật báo cáo khi khởi động

Có thể chạy ứng dụng với `--debug`:

~~~shell
java -jar catalog.jar --debug
~~~

Boot in thông tin các auto-configuration **matched** và **did not match**, kèm lý do điều kiện. Trong báo cáo, có thể tìm:

~~~text
DataSourceAutoConfiguration
JdbcTemplateAutoConfiguration
JdbcRepositoriesAutoConfiguration
DataSourceTransactionManagerAutoConfiguration
SqlInitializationAutoConfiguration
~~~

Ví dụ nếu `JdbcRepositoriesAutoConfiguration` không match, xem điều kiện nào không đáp ứng: thiếu dependency, không có bean cần thiết, property đã tắt hoặc có cấu hình người dùng thay thế.

### 10.2. Kiểm tra qua Actuator

Nếu ứng dụng có Spring Boot Actuator, endpoint `/actuator/conditions` có thể cung cấp báo cáo điều kiện. Cấu hình exposure ví dụ cho môi trường phát triển nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Endpoint chẩn đoán nội bộ cần được bảo vệ phù hợp, không nên mở công khai Internet vô điều kiện.

### 10.3. Phân biệt loại lỗi

Condition report giúp giải thích **bean có/không có**. Nó không thay thế việc kiểm tra:

- Log `SQLException` và `DataAccessException` để hiểu lỗi SQL.
- Schema, quyền truy cập và tính tồn tại của bảng.
- Query plan, index và tốc độ truy vấn.
- Connection pool, timeout và transaction khi hệ thống có tải.

Có thể chẩn đoán theo tầng: auto-configuration → bean → kết nối → mapping → SQL → transaction.

## 11. Lỗi phổ biến

| Biểu hiện | Nguyên nhân thường gặp | Cách tiếp cận |
|---|---|---|
| `Failed to configure a DataSource` | Không có JDBC URL hoặc database nhúng/driver phù hợp | Kiểm tra starter, driver và `spring.datasource.*` |
| `No suitable driver` | Driver không có ở runtime hoặc URL không tương thích | Thêm driver đúng và xác nhận JDBC URL |
| `Connection refused` | Database chưa chạy, host/port/network sai | Kiểm tra kết nối và quyền từ môi trường chạy |
| Không tìm được `BookRepository` | Repository ở ngoài package quét, bị tắt hoặc store không rõ | Kiểm tra package, property enabled và condition report |
| `Table "BOOKS" not found` / `relation does not exist` | Chưa tạo bảng, khác schema hoặc script chưa chạy | Kiểm tra migration/script và mapping tên bảng |
| Không xác định được dialect | Database không nhận diện hoặc chưa được hỗ trợ đầy đủ | Kiểm tra metadata, driver và khả năng mở rộng dialect |
| Nhiều `DataSource` gây mơ hồ | Không xác định được bean chính hoặc transaction manager | Đặt `@Primary` / `@Qualifier` và cấu hình tường minh |
| Có `@Table` nhưng database trống | Spring Data JDBC không sinh DDL từ entity | Viết `schema.sql` hoặc migration |
| `@Transactional` không rollback như mong đợi | Self-invocation, manager sai, ngoại lệ bị bắt hoặc sai ranh giới | Kiểm tra đường gọi qua proxy và chính sách rollback |
| Repository truy vấn sai cột | Tên vật lý hoặc mapping không khớp schema | Kiểm tra `@Table`, `@Column` và cột thực tế |

**Trình tự xử lý:** kiểm tra dependency/driver → `DataSource` → condition report → repository scanning → schema/mapping → SQL → transaction. Không nên chữa mọi lỗi bằng cách thêm `@EnableJdbcRepositories` hoặc tự khai báo tất cả bean mà chưa tìm ra nguyên nhân.

## 12. Kiểm thử riêng tầng Spring Data JDBC

Spring Boot có test slice **`@DataJdbcTest`** để tải một phần ngữ cảnh phục vụ kiểm thử repository/JDBC, thay vì khởi động cả ứng dụng web.

Ví dụ sử dụng H2 và `schema.sql` trên test classpath:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class BookRepositoryTest {
    @Autowired
    BookRepository books;

    @Test
    void savesBookAndReadsItBack() {
        Book saved = books.save(new Book(
                null, "Data JDBC", "Minh", new BigDecimal("99000")
        ));

        assertThat(saved.id()).isNotNull();
        assertThat(books.findById(saved.id()))
                .isPresent()
                .get()
                .extracting(Book::title)
                .isEqualTo("Data JDBC");
    }
}
~~~

`@DataJdbcTest` thường cấu hình những thành phần JDBC/repository cần thiết và có thể thay thế `DataSource` bằng database embedded trong môi trường test thông thường. Nếu muốn dùng PostgreSQL thật hoặc Testcontainers, phải cấu hình database test cùng chính sách thay thế phù hợp (ví dụ `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` trong trường hợp cần giữ DataSource đã cấu hình).

Thử bằng H2 tốt để học cơ chế repository, nhưng không chứng minh mọi cú pháp SQL, isolation và constraint sẽ giống PostgreSQL. Truy vấn phụ thuộc dialect nên được kiểm thử với database mục tiêu.

Nếu chỉ kiểm thử `JdbcTemplate`, có thể sử dụng test slice **`@JdbcTest`**. Khi cần kiểm tra toàn bộ ngữ cảnh ứng dụng, dùng **`@SpringBootTest`**.

## 13. Bài tập thực hành

1. Tạo dự án Boot có `spring-boot-starter-data-jdbc` và H2. Thêm `BookRepository`, gọi `findByAuthor` mà không tạo bean JDBC thủ công.
2. Tạm bỏ `schema.sql`, thử gọi `save` và giải thích vì sao `@Table` không làm bảng xuất hiện.
3. Bật `--debug`, tìm bốn auto-configuration JDBC quan trọng và ghi điều kiện khiến chúng match.
4. Đặt `spring.data.jdbc.repositories.enabled=false`; quan sát repository injection thay đổi thế nào trong khi `DataSource` và `JdbcTemplate` vẫn có thể tồn tại.
5. Tạo `@Bean JdbcTemplate` tùy chỉnh, quan sát cơ chế back off của Boot.
6. Chuyển repository ra ngoài package gốc, tìm lý do không được phát hiện và điều chỉnh phạm vi quét.
7. Dùng `@Transactional` lưu hai sách, cố ý ném lỗi runtime giữa thao tác và kiểm tra rollback.

## 14. Tổng kết kiến thức cốt lõi

- **Spring Boot auto-configuration** tự đăng ký hạ tầng Spring JDBC và Spring Data JDBC **dựa trên điều kiện** classpath, bean, property và môi trường.
- Ứng dụng thông dụng cần starter thích hợp, JDBC driver, thông tin kết nối và repository nằm trong phạm vi quét.
- Boot có thể tạo `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate`, transaction manager và kích hoạt Spring Data JDBC repositories. Bean tự định nghĩa có thể thay thế cấu hình mặc định khi điều kiện back off tương ứng được áp dụng.
- Spring Data JDBC **ánh xạ aggregate và thực hiện truy cập dữ liệu**; nó không tự tạo bảng từ `@Table`.
- Script initialization, Flyway và Liquibase là những cơ chế quản lý schema riêng biệt với ánh xạ repository.
- Khi thành phần nào đó không xuất hiện, hãy dựa vào **Condition Evaluation Report** để tìm điều kiện thiếu trước khi thêm cấu hình thủ công.
