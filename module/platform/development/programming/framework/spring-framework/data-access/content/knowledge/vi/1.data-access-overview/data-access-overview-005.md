# Phân biệt Spring Framework, Spring Data và trình cung cấp ORM

> **Mục tiêu:** Sau bài này, bạn có thể chỉ đúng thành phần nào quản lý ứng dụng và giao dịch, thành phần nào tạo Repository, thành phần nào thực sự ánh xạ đối tượng thành dữ liệu quan hệ và chạy truy vấn. Bối cảnh là tầng truy cập dữ liệu của ứng dụng Java dùng Spring.

## 1. Ba tên gọi, ba trách nhiệm khác nhau

| Thành phần | Bản chất và trách nhiệm chính | Ví dụ bạn thấy trong mã | Điều không nên gán nhầm |
| --- | --- | --- | --- |
| **Spring Framework** | Nền tảng IoC/DI, quản lý bean, AOP, giao dịch, tài nguyên và tích hợp truy cập dữ liệu (JDBC, JPA/ORM, R2DBC…). | `@Service`, `@Transactional`, `JdbcTemplate`, `PlatformTransactionManager`, `DataAccessException` | Không tự biến entity thành SQL như một ORM provider; không yêu cầu phải dùng Spring Data. |
| **Spring Data** | Họ dự án cung cấp mô hình Repository và tiện ích truy cập dữ liệu theo từng loại kho dữ liệu. | `CrudRepository`, `JpaRepository`, `findByTitle(…)`; các module JPA, JDBC, MongoDB, R2DBC… | Không phải một ORM provider thống nhất; không phải mọi module Spring Data đều dùng JPA hoặc Hibernate. |
| **Trình cung cấp ORM (ORM provider)** | Thư viện triển khai ánh xạ object–relational: quản lý entity, trạng thái đối tượng và SQL tương ứng cho cơ sở dữ liệu quan hệ. | Hibernate ORM, EclipseLink; `EntityManager`/persistence context khi dùng qua JPA | Không quản lý toàn bộ ứng dụng Spring và không tự cung cấp hệ Repository của Spring Data. |

Cách nhớ: **Spring Framework điều phối hạ tầng; Spring Data giúp viết tầng repository; ORM provider thực hiện công việc ánh xạ và tương tác với database.** Các lớp có thể phối hợp nhưng không phải là một sản phẩm hay một khái niệm.

Ví dụ phổ biến là `Spring Framework + Spring Data JPA + Hibernate ORM + PostgreSQL`. Trong cấu hình này, Hibernate là ORM provider được sử dụng qua chuẩn JPA; Spring Data JPA cung cấp repository; Spring Framework lo bean, cấu hình, giao dịch và tích hợp.

## 2. JPA, JDBC và Spring Boot nằm ở đâu?

Trước khi đọc kiến trúc, cần tách bốn khái niệm:

- **Jakarta Persistence (JPA)** là *đặc tả/API* cho persistence theo mô hình object–relational. `@Entity`, `@Id`, `EntityManager` và JPQL thuộc hệ API JPA (`jakarta.persistence`). Bản thân đặc tả **không** thực thi SQL; cần provider như Hibernate hoặc EclipseLink.
- **Hibernate ORM** là một *triển khai* JPA rất phổ biến, đồng thời có API riêng như `Session`. Có thể dùng Hibernate trực tiếp hoặc thông qua JPA, có hoặc không có Spring Data.
- **JDBC** là API Java để gửi SQL và nhận kết quả qua JDBC driver. ORM provider thường dùng JDBC bên dưới khi giao tiếp với cơ sở dữ liệu quan hệ; `JdbcTemplate` cũng dùng JDBC nhưng không cần ORM.
- **Spring Boot** xây trên Spring Framework để tự cấu hình theo dependency, hỗ trợ starter và vận hành ứng dụng. Boot có thể tự cấu hình `DataSource`, `EntityManagerFactory` và transaction manager khi đủ điều kiện; Boot **không** thay thế Spring Data hay Hibernate.

`JpaRepository` thuộc **Spring Data JPA**, không thuộc JPA specification. `@Transactional` thường dùng từ **Spring Framework** (`org.springframework.transaction.annotation.Transactional`). `@Entity` đến từ **Jakarta Persistence**, không phải annotation của Spring Data. Phân biệt nguồn gốc API giúp đọc code và xử lý lỗi đúng lớp.

## 3. Luồng hoạt động trong một ứng dụng Spring Data JPA

```text
HTTP / Job / CLI
      |
      v
Controller / Application Service
      |   Spring Framework: inject bean, proxy @Transactional,
      |   quản lý ranh giới transaction và tài nguyên
      v
Repository interface + proxy (Spring Data JPA)
      |   save(), findById(), findByTitle()...
      v
EntityManager / JPA API (Jakarta Persistence)
      |
      v
Hibernate ORM hoặc EclipseLink (JPA provider)
      |   ánh xạ entity, persistence context, sinh/thi hành SQL
      v
JDBC driver / DataSource
      |
      v
Cơ sở dữ liệu quan hệ (PostgreSQL, MySQL, H2…)
```

*Lưu ý:* Quản lý transaction là trách nhiệm hạ tầng **bao quanh** lời gọi service/repository, không phải một bước SQL nối tiếp đơn giản. Spring có thể mở hoặc tham gia transaction, gắn tài nguyên persistence vào ngữ cảnh phù hợp, rồi commit hoặc rollback thông qua transaction manager và provider.

Ví dụ khi gọi `bookRepository.save(book)`:

1. Spring Data JPA nhận lời gọi trên repository proxy và dùng `EntityManager` để lưu entity (theo trạng thái entity, thường thông qua `persist` hoặc `merge`).
2. Provider như Hibernate quản lý trạng thái entity trong persistence context, xác định thao tác SQL cần thiết và thực hiện qua JDBC.
3. Cơ sở dữ liệu thực thi thao tác trong transaction; Spring điều phối lúc hoàn tất transaction.
4. `save()` **không đồng nghĩa** “đã commit ngay”: thời điểm SQL được gửi còn phụ thuộc flush, chiến lược sinh ID và truy vấn liên quan; commit là ranh giới transaction.

Thay Hibernate bằng một JPA provider tương thích có thể giữ lại nhiều API JPA và Spring Data JPA, nhưng vẫn phải kiểm tra cấu hình, dialect, mapping và những tính năng dành riêng cho provider.

## 4. Mỗi thành phần cung cấp những gì?

### Spring Framework: hạ tầng, giao dịch và nhiều cách truy cập dữ liệu

- **IoC/DI:** tạo bean, inject `DataSource`, repository và service; quản lý vòng đời.
- **Giao dịch:** `@Transactional`, `PlatformTransactionManager`, AOP proxy, cơ chế đồng bộ tài nguyên; cùng một service có thể phối hợp nhiều thao tác data access trong một transaction phù hợp.
- **Spring JDBC:** `JdbcTemplate`/`NamedParameterJdbcTemplate` giúp thực thi SQL, bind tham số, quản lý resource và chuyển đổi `SQLException`. Bạn vẫn kiểm soát SQL và ánh xạ kết quả.
- **Spring ORM:** tích hợp JPA/Hibernate, cấu hình factory, transaction, exception translation; không thay thế công cụ ORM.
- **Exception translation:** hỗ trợ quy về họ `DataAccessException` ở các điểm tích hợp phù hợp, giúp code ứng dụng ít phụ thuộc exception cụ thể của JDBC/provider.

Vì vậy có thể xây ứng dụng **Spring Framework + JdbcTemplate + database**, hoàn toàn không cần Spring Data hoặc ORM.

### Spring Data: trừu tượng Repository, nhưng tùy module

- **Spring Data Commons** định nghĩa khái niệm repository và hạ tầng chung, chẳng hạn `Repository` và `CrudRepository`.
- **Spring Data JPA** bổ sung `JpaRepository`, query method theo tên (`findByTitle`), `@Query`, phân trang, sắp xếp, specification và tích hợp với `EntityManager`. Module này **cần JPA provider** khi chạy persistence.
- **Spring Data JDBC** dùng mô hình ánh xạ aggregate đơn giản trên JDBC, **không dùng JPA/Hibernate** và không có persistence context/dirty tracking/lazy loading kiểu JPA.
- **Spring Data MongoDB** làm việc với kho tài liệu; **Spring Data R2DBC** cung cấp truy cập SQL theo hướng reactive với R2DBC driver. Chúng không biến thành Hibernate chỉ vì cùng mang tên Spring Data.

Repository giúp giảm code CRUD lặp lại, nhưng **không tự bảo đảm** tối ưu SQL, thiết kế quan hệ đúng, hay hết vấn đề N+1. Vẫn phải hiểu công nghệ lưu trữ phía dưới.

### ORM provider: ánh xạ và cơ chế persistence

Với Hibernate trong vai trò JPA provider, những việc tiêu biểu là:

- Dựa trên mapping `@Entity`, `@Table`, `@Column`, `@ManyToOne`… để liên hệ class/quan hệ và bảng/cột.
- Quản lý trạng thái entity trong **persistence context**; theo dõi thay đổi (dirty checking), flush thay đổi và có thể trì hoãn tải quan hệ theo mapping/fetch strategy.
- Xử lý JPQL/criteria và các thao tác persistence để tạo, chuẩn bị và thực thi SQL qua JDBC.
- Cung cấp tính năng chuyên biệt như chiến lược fetch, batch, cache cấp hai (khi cấu hình), và cơ chế sinh ID.

ORM không “xóa” sự tồn tại của SQL, database index, transaction isolation hoặc JDBC driver. Chất lượng truy vấn và mô hình dữ liệu vẫn quyết định hiệu năng.

## 5. Bốn cách ghép thành phần đều hợp lệ

| Lựa chọn | Đường truy cập dữ liệu | Khi nào phù hợp |
| --- | --- | --- |
| **Spring JDBC** | Spring Framework → `JdbcTemplate` → JDBC → DB | SQL cần kiểm soát chặt, báo cáo/query đặc thù, mapping đơn giản; **không cần** Spring Data hay ORM. |
| **JPA trực tiếp** | Spring Framework → DAO dùng `EntityManager` → JPA provider → JDBC → DB | Cần ORM nhưng muốn tự viết DAO, không dùng repository abstraction của Spring Data. |
| **Spring Data JPA** | Spring Framework → `JpaRepository` → JPA → provider → JDBC → DB | Domain có entity/quan hệ và nhiều CRUD/query repository; cần ORM và muốn giảm boilerplate. |
| **Spring Data JDBC** | Spring Framework + Spring Data JDBC → JDBC → DB | Aggregate rõ ràng, thích mapping đơn giản, SQL dễ dự đoán, không cần persistence context JPA. |

Không có quy tắc “dự án Spring bắt buộc phải dùng Spring Data JPA”. Chọn theo mô hình dữ liệu, kỹ năng nhóm, mức độ kiểm soát truy vấn và chi phí vận hành.

## 6. Ví dụ chạy được: thấy cả ba lớp trong một ứng dụng

Ví dụ dùng **Java 17+, Maven, Spring Boot 3.5.16, Spring Data JPA và H2**. Spring Boot chỉ giúp cấu hình nhanh cho bài thực hành. Đặt các file Java cùng package `com.example.layers`. Ví dụ này *là một project nhiều file*, không biên dịch riêng từng đoạn bằng lệnh `javac` thiếu dependency.

**`pom.xml`** — Boot quản lý phiên bản tương thích của Spring, Spring Data, Hibernate và H2; không cần tự ghép version của từng thư viện:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-data-layers</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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

**`src/main/java/com/example/layers/Book.java`** — entity được mô tả bằng *annotation của Jakarta Persistence*; Hibernate đọc mapping này:

```java
package com.example.layers;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() { } // JPA cần constructor không tham số

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

**`src/main/java/com/example/layers/BookRepository.java`** — interface là phần của *Spring Data JPA*. Spring Data tạo repository proxy/implementation; bạn không phải viết thủ công CRUD phổ biến:

```java
package com.example.layers;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(String title);
}
```

**`src/main/java/com/example/layers/BookService.java`** — `@Service`, constructor injection và `@Transactional` là phần do *Spring Framework* cung cấp:

```java
package com.example.layers;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void create(String title) {
        repository.save(new Book(title));
    }

    @Transactional(readOnly = true)
    public List<Book> findByTitle(String title) {
        return repository.findByTitle(title);
    }
}
```

**`src/main/java/com/example/layers/DemoApplication.java`** — gọi từ bean khác qua Spring proxy để transaction có hiệu lực:

```java
package com.example.layers;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            service.create("Spring");
            System.out.println("books=" + service.findByTitle("Spring").size());
        };
    }
}
```

**`src/main/resources/application.properties`** — chỉ tạo schema tự động để học với database H2 trong bộ nhớ; môi trường production cần quản lý migration bằng công cụ thích hợp:

```properties
spring.datasource.url=jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=false
```

Chạy trong thư mục chứa `pom.xml` (máy cần JDK 17+ và Maven):

```bash
mvn spring-boot:run
```

Trong log khởi động có dòng do ứng dụng in ra:

```text
books=1
```

H2 tạo database mới trong bộ nhớ; lệnh tạo một `Book` rồi tìm đúng một bản ghi. Đây là kết quả minh họa của một lần chạy với database rỗng, không phải cam kết thứ tự hoặc nội dung của mọi dòng log Spring Boot.

**Đọc lại theo từng lớp:** `BookService` và transaction là **Spring Framework**; `BookRepository`/`findByTitle` là **Spring Data JPA**; `@Entity` và `EntityManager` thuộc **JPA**; Hibernate **triển khai ORM và tạo/thực thi SQL qua JDBC**; H2 là **database**. `spring-boot-starter-data-jpa` kéo vào các thư viện tích hợp mặc định, vì vậy việc không tự khai báo `hibernate-core` trong POM **không có nghĩa** là chương trình không dùng Hibernate.

## 7. Cùng bài toán nếu bỏ Spring Data

Dưới đây là **hai đoạn minh họa độc lập**, không phải file bổ sung cần thiết để chạy project ở mục 6.

**Chỉ dùng Spring Framework + JPA provider:** tự viết DAO qua API chuẩn JPA, vẫn được Spring inject và quản lý transaction.

```java
@Repository
public class BookJpaDao {
    @PersistenceContext
    private EntityManager entityManager;

    public Book find(long id) {
        return entityManager.find(Book.class, id);
    }
}
```

Đoạn trên cần import `jakarta.persistence.EntityManager`, `jakarta.persistence.PersistenceContext` và `org.springframework.stereotype.Repository`, đồng thời cần bean/config JPA. `@Repository` đánh dấu custom DAO; exception translation phụ thuộc hạ tầng cấu hình. **Không có `JpaRepository` nhưng vẫn có ORM** vì `EntityManager` làm việc với provider.

**Chỉ dùng Spring Framework + JDBC:** viết SQL và mapping kết quả trực tiếp, không sử dụng entity JPA, Hibernate hay Spring Data:

```java
@Repository
public class BookJdbcDao {
    private final JdbcTemplate jdbc;

    public BookJdbcDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<BookRow> findByTitle(String title) {
        return jdbc.query(
            "select id, title from books where title = ?",
            (rs, rowNum) -> new BookRow(
                rs.getLong("id"), rs.getString("title")
            ),
            title
        );
    }
}

record BookRow(long id, String title) { }
```

Đoạn JDBC cần import `java.util.List`, `org.springframework.jdbc.core.JdbcTemplate` và `org.springframework.stereotype.Repository`, có bảng `books` và bean `JdbcTemplate`. `BookRow` chỉ là DTO/record, **không phải JPA entity**. Spring JDBC quản lý thao tác JDBC thông dụng, còn SQL do lập trình viên viết. Đây là đoạn minh họa phải được đặt trong project có dependency Spring JDBC; nó không phải chương trình Java độc lập.

## 8. Chọn cách nào cho dự án?

- **Chọn Spring Data JPA + Hibernate** khi domain có nhiều entity/quan hệ, cần persistence context, dirty checking, mapping đối tượng và muốn repository CRUD ít boilerplate. Cần hiểu fetch plan, transaction, query thực tế và migration schema.
- **Chọn Spring Data JDBC** khi mô hình aggregate đơn giản, muốn repository abstraction nhưng không muốn cơ chế entity session, lazy loading/dirty checking của JPA. Đọc kỹ cách lưu aggregate và truy vấn của module này.
- **Chọn JdbcTemplate hoặc JDBC trực tiếp** khi SQL là trung tâm, truy vấn đặc thù, bulk operation hay yêu cầu kiểm soát câu lệnh cao; chấp nhận tự viết SQL và mapping.
- **Chọn JPA trực tiếp qua EntityManager** khi cần ORM nhưng repository abstraction không phù hợp, ví dụ DAO/query rất đặc thù. Vẫn tận dụng tích hợp transaction và quản lý bean của Spring.

Các cách trên không loại trừ việc dùng phối hợp trong một hệ thống, nhưng khi phối hợp nhiều cơ chế truy cập dữ liệu phải thiết kế ranh giới transaction, mapping và tài nguyên thống nhất, tránh ngầm giả định chúng tự đồng bộ.

## 9. Các nhầm lẫn dễ gây lỗi

1. **“Dùng Spring Data JPA là không cần Hibernate.”** Sai: Spring Data JPA làm việc qua JPA, cần một provider tương thích. Starter của Boot thường mang Hibernate theo mặc định.
2. **“JPA và Hibernate là một.”** Sai: JPA là đặc tả/API; Hibernate là một triển khai (và có API riêng). EclipseLink cũng là một JPA provider.
3. **“Mọi Spring Data đều là ORM.”** Sai: Spring Data JDBC, MongoDB và R2DBC không sử dụng mô hình ORM JPA/Hibernate.
4. **“`@Entity`, `@Transactional` và `JpaRepository` đều của Spring Data.”** Sai: lần lượt là Jakarta Persistence, Spring Framework (trong ví dụ này), Spring Data JPA.
5. **“`save()` luôn ghi SQL và commit ngay.”** Sai: commit ở ranh giới transaction; thời điểm insert/update SQL có thể phụ thuộc flush, sinh ID và trạng thái entity. Hãy kiểm tra SQL thật khi cần.
6. **“`@Transactional` trên mọi phương thức đều tự hoạt động.”** Không luôn đúng: với AOP proxy mặc định, lời gọi từ chính một phương thức sang phương thức khác trong *cùng instance* (self-invocation) không đi qua proxy. Transaction manager cũng phải được cấu hình phù hợp.
7. **“`@Transactional(readOnly = true)` bảo đảm database từ chối ghi.”** Không: đây là chỉ dẫn/hint cho hạ tầng liên quan; không thay thế quyền database hoặc ràng buộc nghiệp vụ.
8. **“Repository tự giải quyết N+1 và lazy loading.”** Không: provider vẫn quyết định truy vấn. Truy cập quan hệ lazy bên ngoài persistence context có thể lỗi; cần định nghĩa fetch plan, DTO/projection, query và kiểm tra log SQL.
9. **“Có Spring Boot là không cần hiểu transaction/provider.”** Không: Boot tự cấu hình theo classpath và properties; khi hiệu năng, rollback hoặc mapping sai, phải truy nguyên tới đúng tầng.
10. **“Đổi provider JPA là chắc chắn tương đương 100%.”** Không: API chuẩn tăng khả năng thay thế, nhưng dialect, SQL phát sinh, tính năng riêng và cấu hình vẫn có khác biệt.

## 10. Tự kiểm tra hiểu biết

**Tình huống A:** Code có `@Service`, `@Transactional` và `JdbcTemplate`, không có `JpaRepository` hoặc `@Entity`. Có Spring Data/Hibernate không? → **Không bắt buộc có**; đây có thể chỉ là Spring Framework + JDBC.

**Tình huống B:** Interface `OrderRepository extends JpaRepository<Order, Long>`, entity dùng `@Entity`, runtime có Hibernate. Ai làm gì? → **Spring Data JPA** tạo repository; **JPA** định nghĩa persistence API/mapping; **Hibernate** là provider thực thi ORM; **Spring Framework** tích hợp, inject và điều phối transaction.

**Tình huống C:** Dùng `CrudRepository` của Spring Data JDBC. Có `EntityManager` và lazy loading JPA không? → **Không**; dùng repository abstraction không tự kéo theo ORM kiểu JPA.

**Tình huống D:** Bỏ Spring Data JPA nhưng vẫn inject `EntityManager` để chạy JPQL. Có còn ORM không? → **Có**; Spring Data là lớp tiện ích tùy chọn nằm trên JPA/provider.

## 11. Tài liệu tham khảo chính thức

- Spring Framework — Data Access: https://docs.spring.io/spring-framework/reference/data-access.html
- Spring Framework — ORM Integration: https://docs.spring.io/spring-framework/reference/data-access/orm/introduction.html
- Spring Framework — `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — Reference: https://docs.spring.io/spring-data/jpa/reference/
- Spring Data JDBC — Why Spring Data JDBC?: https://docs.spring.io/spring-data/relational/reference/jdbc/why.html

**Ghi nhớ cốt lõi:** `Spring Framework` = hạ tầng ứng dụng/giao dịch; `Spring Data` = repository theo datastore; `JPA` = đặc tả persistence; `Hibernate/EclipseLink` = ORM provider; `JDBC driver` = cầu nối SQL đến database.