# Tạo ứng dụng Spring Boot với Spring Data JPA và trình điều khiển JDBC

Bài học này hướng dẫn tạo một ứng dụng Spring Boot có API quản lý sách, dùng Spring Data JPA để thao tác dữ liệu và H2 làm cơ sở dữ liệu mẫu thông qua trình điều khiển JDBC. Ví dụ dùng Java 17, Maven và Spring Boot 3.5.0. Sau khi hoàn thành, ứng dụng có thể tạo, đọc, cập nhật, xóa và tìm sách theo tác giả.

## 1. Hiểu vai trò của từng thành phần

Các công nghệ trong ứng dụng đảm nhiệm những phần việc khác nhau:

| Thành phần | Vai trò |
|---|---|
| Spring Boot | Khởi tạo ứng dụng, cấu hình tự động, quản lý dependency và tích hợp các thành phần Spring |
| Spring Data JPA | Cung cấp repository và các thao tác truy cập dữ liệu theo mô hình JPA |
| JPA | Đặc tả Java cho ánh xạ đối tượng với dữ liệu quan hệ và thao tác persistence |
| Hibernate | JPA provider mặc định thường được Spring Boot cấu hình; thực thi các thao tác JPA và sinh SQL |
| JDBC | API chuẩn của Java để kết nối và gửi lệnh SQL tới cơ sở dữ liệu |
| JDBC driver | Thư viện của từng hệ quản trị, chuyển lời gọi JDBC thành giao thức mà cơ sở dữ liệu hiểu được |
| H2 | Cơ sở dữ liệu quan hệ nhúng dùng trong ví dụ để chạy thử mà không cần cài máy chủ DB |

Luồng xử lý điển hình:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Spring MVC Controller]
    B --> C[Spring Data Repository]
    C --> D[JPA EntityManager]
    D --> E[Hibernate]
    E --> F[JDBC API]
    F --> G[H2 JDBC Driver]
    G --> H[(H2 Database)]
~~~

Spring Data JPA không phải là JDBC driver. Repository làm việc ở mức đối tượng và JPA; Hibernate chuyển các thao tác đó thành SQL; JDBC driver thực hiện kết nối và trao đổi với cơ sở dữ liệu. Khi đổi H2 sang MySQL hoặc PostgreSQL, ứng dụng thay driver và cấu hình kết nối tương ứng.

## 2. Chuẩn bị môi trường

Cần có:

- JDK 17 trở lên và biến môi trường JAVA_HOME được cấu hình.
- Maven 3.6.3 trở lên, hoặc Maven Wrapper đi kèm dự án.
- IDE có hỗ trợ Java như IntelliJ IDEA, Eclipse hoặc VS Code.
- Kiến thức cơ bản về Java, Maven, HTTP và SQL.

Kiểm tra môi trường:

~~~bash
java -version
mvn -version
~~~

Kết quả cần cho thấy Java 17 trở lên và Maven có thể chạy. Nếu dùng Maven Wrapper, có thể thay lệnh mvn bằng ./mvnw trên Linux/macOS hoặc mvnw.cmd trên Windows.

## 3. Tạo cấu trúc dự án

Tạo dự án Maven với package gốc com.example.springdatajpa. Cấu trúc tối thiểu:

~~~text
spring-data-jpa-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/springdatajpa/
        │       ├── DemoApplication.java
        │       └── book/
        │           ├── Book.java
        │           ├── BookRepository.java
        │           ├── BookRequest.java
        │           └── BookController.java
        └── resources/
            └── application.properties
~~~

Có thể tạo dự án bằng Spring Initializr (start.spring.io): chọn Maven, Java, Spring Boot 3.5.x, Java 17, packaging Jar; thêm Spring Web, Spring Data JPA, Validation và H2 Database. Sau đó tạo các package và file theo cấu trúc trên.

## 4. Khai báo dependency trong pom.xml

Spring Data JPA starter cung cấp Spring Data JPA, Hibernate, Spring ORM, Spring JDBC và hỗ trợ transaction. H2 là driver JDBC của cơ sở dữ liệu H2. Spring Web tạo REST API; Validation kiểm tra dữ liệu đầu vào.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-jpa-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>spring-data-jpa-demo</name>
    <description>Demo Spring Boot with Spring Data JPA and H2 JDBC driver</description>

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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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

Không cần tự khai báo phiên bản cho H2 hoặc các starter khi dùng Spring Boot parent vì dependency management của Spring Boot quản lý các phiên bản tương thích. Không cần thêm spring-boot-starter-jdbc chỉ để Spring Data JPA hoạt động; JPA starter đã kéo theo các thư viện JDBC cần thiết.

## 5. Tạo lớp khởi động Spring Boot

File DemoApplication.java:

~~~java
package com.example.springdatajpa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

@SpringBootApplication kết hợp cấu hình, auto-configuration và component scanning. Đặt lớp này ở package gốc để Spring quét các lớp trong package con book, bao gồm controller, repository và entity.

## 6. Cấu hình kết nối H2 bằng JDBC driver

File src/main/resources/application.properties:

~~~properties
spring.application.name=spring-data-jpa-demo

spring.datasource.url=jdbc:h2:mem:booksdb;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console
~~~

Ý nghĩa các thuộc tính:

- spring.datasource.url xác định loại DB, tên database và chế độ kết nối. Tiền tố jdbc:h2: cho biết sử dụng H2.
- spring.datasource.driver-class-name chỉ rõ lớp driver. Với H2, lớp này là org.h2.Driver. Spring Boot thường có thể tự suy ra driver từ URL nên dòng này có thể bỏ.
- username và password là thông tin xác thực của database mẫu.
- spring.jpa.hibernate.ddl-auto=update yêu cầu Hibernate cập nhật schema dựa trên entity. Chế độ này tiện cho học tập; hệ thống production nên quản lý schema bằng Flyway hoặc Liquibase và thường đặt ddl-auto=validate.
- show-sql và format_sql giúp quan sát SQL do Hibernate sinh ra.
- open-in-view=false tránh giữ EntityManager mở xuyên suốt thời gian xử lý response web.
- H2 Console cho phép xem database tại /h2-console khi ứng dụng đang chạy.

URL trên tạo database trong bộ nhớ. Dữ liệu tồn tại trong vòng đời JVM hiện tại và sẽ mất khi tiến trình ứng dụng kết thúc. DB_CLOSE_DELAY=-1 giữ database trong bộ nhớ cho tới khi JVM dừng, không biến nó thành database lưu trữ lâu dài.

## 7. Tạo entity ánh xạ bảng dữ liệu

Entity biểu diễn một đối tượng được lưu trong database. File book/Book.java:

~~~java
package com.example.springdatajpa.book;

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

    @Column(nullable = false, length = 150)
    private String title;

    @Column(nullable = false, length = 120)
    private String author;

    protected Book() {
        // JPA cần constructor không tham số.
    }

    public Book(String title, String author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthor() {
        return author;
    }

    public void setAuthor(String author) {
        this.author = author;
    }
}
~~~

Các annotation quan trọng:

- @Entity đánh dấu lớp được JPA quản lý.
- @Table(name = "books") đặt tên bảng tương ứng.
- @Id đánh dấu khóa chính.
- @GeneratedValue(strategy = GenerationType.IDENTITY) giao việc sinh khóa chính cho database theo cơ chế identity.
- @Column cấu hình cột, giới hạn độ dài và yêu cầu không null.
- Constructor không tham số phải có ít nhất mức truy cập protected để JPA tạo entity. Constructor còn lại giúp ứng dụng tạo đối tượng mới.

Tên bảng và cột có thể được Hibernate tạo dựa trên entity khi schema được cấu hình tự động. Entity nên tập trung vào dữ liệu và quy tắc miền; không nên đưa logic HTTP vào entity.

## 8. Tạo Spring Data repository

File book/BookRepository.java:

~~~java
package com.example.springdatajpa.book;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByAuthorIgnoreCase(String author);
}
~~~

Kế thừa JpaRepository<Book, Long> cung cấp sẵn các thao tác phổ biến như:

| Phương thức | Tác dụng |
|---|---|
| save(entity) | Lưu entity mới hoặc cập nhật entity |
| findById(id) | Tìm theo khóa chính, trả về Optional |
| findAll() | Lấy danh sách entity |
| existsById(id) | Kiểm tra khóa chính có tồn tại |
| deleteById(id) | Xóa theo khóa chính |
| count() | Đếm số bản ghi |

Spring Data tạo implementation cho interface repository lúc ứng dụng khởi động. Không cần tự viết lớp triển khai CRUD.

Tên findByAuthorIgnoreCase là derived query. Spring Data phân tích tên phương thức và tạo truy vấn tìm sách theo tác giả, không phân biệt chữ hoa/chữ thường. Có thể định nghĩa thêm các phương thức như findByTitleContainingIgnoreCase(String keyword) khi có nhu cầu tìm theo một phần tiêu đề.

## 9. Tạo DTO cho dữ liệu đầu vào

File book/BookRequest.java:

~~~java
package com.example.springdatajpa.book;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookRequest(
        @NotBlank @Size(max = 150) String title,
        @NotBlank @Size(max = 120) String author
) {
}
~~~

DTO (Data Transfer Object) xác định dữ liệu API nhận từ client. Record của Java 17 phù hợp với DTO bất biến. @NotBlank từ chối giá trị null, chuỗi rỗng hoặc chỉ có khoảng trắng; @Size giới hạn độ dài để phù hợp với cấu hình cột entity. Controller dùng @Valid để kích hoạt kiểm tra.

## 10. Tạo REST controller sử dụng repository

File book/BookController.java:

~~~java
package com.example.springdatajpa.book;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<Book> findAll(
            @RequestParam(name = "author", required = false) String author) {
        if (author == null || author.isBlank()) {
            return repository.findAll();
        }
        return repository.findByAuthorIgnoreCase(author);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Book> findById(@PathVariable("id") Long id) {
        return repository.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<Book> create(@Valid @RequestBody BookRequest request) {
        Book saved = repository.save(
                new Book(request.title(), request.author()));
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    @PutMapping("/{id}")
    public ResponseEntity<Book> update(
            @PathVariable("id") Long id,
            @Valid @RequestBody BookRequest request) {
        return repository.findById(id)
                .map(book -> {
                    book.setTitle(request.title());
                    book.setAuthor(request.author());
                    return ResponseEntity.ok(repository.save(book));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable("id") Long id) {
        if (!repository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }

        repository.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller nhận HTTP request, kiểm tra DTO, gọi repository và trả HTTP response. Repository chịu trách nhiệm persistence. Constructor injection giúp dependency rõ ràng và dễ kiểm thử. Trong ứng dụng lớn, nên bổ sung service layer để gom nghiệp vụ, transaction và phối hợp nhiều repository; ví dụ này gọi repository trực tiếp để tập trung vào luồng Spring Data JPA.

Các endpoint:

| HTTP method | URL | Chức năng |
|---|---|---|
| GET | /api/books | Lấy tất cả sách |
| GET | /api/books?author=... | Tìm sách theo tác giả |
| GET | /api/books/{id} | Lấy một sách theo ID |
| POST | /api/books | Tạo sách |
| PUT | /api/books/{id} | Cập nhật sách |
| DELETE | /api/books/{id} | Xóa sách |

## 11. Chạy ứng dụng

Tại thư mục chứa pom.xml, chạy:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói rồi chạy file JAR:

~~~bash
mvn clean package
java -jar target/spring-data-jpa-demo-0.0.1-SNAPSHOT.jar
~~~

Khi khởi động thành công, Spring Boot mở web server mặc định ở cổng 8080. Hibernate tạo hoặc cập nhật bảng books trong H2 theo cấu hình. Nếu cổng 8080 đang được sử dụng, đổi cổng bằng thuộc tính server.port, ví dụ server.port=8081.

## 12. Kiểm tra API CRUD

Dùng curl hoặc Postman. Ví dụ tạo sách:

~~~bash
curl -i -X POST http://localhost:8080/api/books   -H "Content-Type: application/json"   -d '{"title":"Clean Code","author":"Robert C. Martin"}'
~~~

Response mẫu:

~~~http
HTTP/1.1 201
Content-Type: application/json

{"id":1,"title":"Clean Code","author":"Robert C. Martin"}
~~~

Lấy danh sách:

~~~bash
curl http://localhost:8080/api/books
~~~

Response sau khi tạo một sách:

~~~json
[
  {
    "id": 1,
    "title": "Clean Code",
    "author": "Robert C. Martin"
  }
]
~~~

Tìm theo tác giả:

~~~bash
curl "http://localhost:8080/api/books?author=robert%20c.%20martin"
~~~

Lấy theo ID:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Cập nhật:

~~~bash
curl -i -X PUT http://localhost:8080/api/books/1   -H "Content-Type: application/json"   -d '{"title":"Clean Code - Updated","author":"Robert C. Martin"}'
~~~

Xóa:

~~~bash
curl -i -X DELETE http://localhost:8080/api/books/1
~~~

POST trả HTTP 201 Created; GET trả HTTP 200 OK nếu tìm thấy; PUT trả HTTP 200 OK nếu cập nhật thành công; DELETE trả HTTP 204 No Content nếu xóa thành công. ID không tồn tại trả HTTP 404 Not Found. Dữ liệu đầu vào không hợp lệ bị từ chối với HTTP 400 Bad Request nhờ Bean Validation. Khi thử trên Windows PowerShell, có thể gọi curl.exe để tránh alias curl của PowerShell.

## 13. Kiểm tra dữ liệu trong H2 Console

Mở http://localhost:8080/h2-console trong khi ứng dụng đang chạy. Nhập các thông tin:

- JDBC URL: jdbc:h2:mem:booksdb
- User Name: sa
- Password: để trống

Chọn Connect, sau đó chạy:

~~~sql
SELECT * FROM BOOKS;
~~~

Có thể xem dữ liệu đã lưu và các cột do Hibernate tạo. Console chỉ nên bật trong môi trường phát triển cục bộ; không công khai H2 Console trên môi trường production.

## 14. Thay H2 bằng cơ sở dữ liệu khác

JDBC driver phụ thuộc hệ quản trị cơ sở dữ liệu. Khi chuyển sang MySQL, bỏ dependency H2 và thêm MySQL Connector/J:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Tạo database trước, ví dụ:

~~~sql
CREATE DATABASE books_db;
~~~

Cấu hình kết nối MySQL trong application.properties:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/books_db
spring.datasource.username=app_user
spring.datasource.password=change-this-secret
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=true
~~~

Tạo tài khoản database phù hợp và cung cấp mật khẩu qua biến môi trường hoặc secret manager trong môi trường triển khai; không commit mật khẩu thật vào Git. Với schema mới, cần chạy migration trước khi dùng ddl-auto=validate. Nếu đang thử nghiệm cục bộ, có thể tạm dùng update, nhưng cần hiểu rằng Hibernate có thể thay đổi schema.

Với PostgreSQL, dependency runtime tương ứng là org.postgresql:postgresql và URL có dạng jdbc:postgresql://localhost:5432/books_db. Username, password và schema cần khớp cấu hình máy chủ. Không dùng org.h2.Driver cho MySQL hoặc PostgreSQL; mỗi loại database cần driver tương ứng. Khi đổi driver và URL, code entity và repository thường không phải thay đổi nếu chỉ dùng các tính năng JPA portable.

## 15. Transaction và cách Spring Data JPA lưu dữ liệu

Các phương thức ghi và đọc được cung cấp bởi repository có cơ chế transaction phù hợp. Khi nghiệp vụ gồm nhiều thao tác phải thành công hoặc thất bại cùng nhau, nên đặt chúng trong một service method có @Transactional:

~~~java
package com.example.springdatajpa.book;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Book renameBook(Long id, String newTitle) {
        Book book = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Book not found: " + id));

        book.setTitle(newTitle);
        return repository.save(book);
    }
}
~~~

@Transactional tạo ranh giới transaction cho nghiệp vụ. Nếu phương thức hoàn tất bình thường, transaction được commit; nếu có lỗi phù hợp, transaction có thể rollback theo quy tắc rollback của Spring. Trong transaction JPA, entity được quản lý có thể được Hibernate dirty-check và ghi thay đổi khi flush/commit; gọi save ở ví dụ giúp thể hiện rõ thao tác repository.

Một transaction nên bao trùm một đơn vị nghiệp vụ nhất quán. Tránh mở transaction quá rộng trong khi gọi dịch vụ bên ngoài hoặc chờ người dùng. Với ứng dụng thực tế, nên dùng exception phù hợp và ánh xạ lỗi thành HTTP status có ý nghĩa.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Failed to configure a DataSource | Thiếu driver hoặc URL kết nối | Kiểm tra dependency runtime, spring.datasource.url và cấu hình username/password |
| Cannot load driver class | Sai driver class hoặc thiếu driver JAR | Đối chiếu driver với DB; H2 dùng org.h2.Driver |
| Connection refused | Database server chưa chạy hoặc sai host/port | Kiểm tra dịch vụ DB, cổng và firewall |
| Access denied | Sai tài khoản, mật khẩu hoặc quyền | Kiểm tra credential và quyền truy cập database |
| Table not found | Schema chưa được tạo hoặc tên bảng sai | Kiểm tra entity, ddl-auto và migration |
| Port 8080 already in use | Ứng dụng khác đang chiếm cổng | Dừng tiến trình đang dùng cổng hoặc đổi server.port |
| API trả 404 | Sai URL hoặc bản ghi không tồn tại | Kiểm tra mapping controller và ID |
| API trả 400 | JSON sai cấu trúc hoặc validation thất bại | Kiểm tra Content-Type, tên trường và giá trị title/author |
| Dữ liệu H2 biến mất sau khi dừng ứng dụng | H2 đang chạy ở chế độ in-memory | Dùng file-based H2 hoặc database lâu dài nếu cần giữ dữ liệu |

Đọc log đầy đủ từ nguyên nhân gốc (root cause), thường nằm trong các dòng Caused by. Không xử lý lỗi kết nối bằng cách tắt kiểm tra bảo mật hoặc mở database ra mạng công cộng.

## 17. Nguyên tắc khi đưa ứng dụng vào môi trường thật

- Dùng database server phù hợp và driver chính thức tương ứng; quản lý connection pool qua cấu hình Spring Boot.
- Đưa thông tin xác thực ra khỏi mã nguồn, dùng biến môi trường hoặc secret manager.
- Quản lý thay đổi schema bằng Flyway hoặc Liquibase; đặt Hibernate ddl-auto=validate hoặc none sau khi migration được kiểm soát.
- Chọn transaction boundary ở service layer cho nghiệp vụ nhiều bước.
- Dùng DTO thay vì nhận hoặc trả entity trực tiếp khi API phức tạp; tránh vô tình công khai trường nội bộ.
- Bổ sung validation, xử lý exception, phân trang và sắp xếp cho endpoint danh sách lớn.
- Viết integration test với database phù hợp. H2 tiện cho test nhanh nhưng có khác biệt SQL và hành vi so với MySQL/PostgreSQL; kiểm tra bằng Testcontainers hoặc môi trường DB tương ứng nếu phụ thuộc tính năng riêng.
- Tắt H2 Console và SQL logging chi tiết ở production; không để lộ thông tin nhạy cảm trong log.

## 18. Tóm tắt kiến thức cần nhớ

1. Spring Boot tự cấu hình DataSource khi có dependency và thuộc tính kết nối phù hợp.
2. JDBC driver là cầu nối giữa JDBC API và giao thức của hệ quản trị cơ sở dữ liệu.
3. Spring Data JPA cung cấp repository; Hibernate thực thi JPA và giao tiếp với DB thông qua JDBC.
4. Entity ánh xạ lớp Java với bảng; repository cung cấp CRUD và derived query.
5. DTO và Bean Validation giúp kiểm soát dữ liệu API nhận vào.
6. H2 in-memory phù hợp để học và chạy demo; dữ liệu sẽ mất khi ứng dụng kết thúc.
7. Khi chuyển database, thay driver và cấu hình kết nối; kiểm tra lại schema, SQL dialect và migration.
8. Với ứng dụng thực tế, quản lý transaction ở service layer và schema bằng công cụ migration.

## 19. Checklist tự kiểm tra

- [ ] JDK 17+ và Maven hoạt động.
- [ ] pom.xml có Spring Web, Spring Data JPA, Validation và H2.
- [ ] Spring Boot khởi động thành công.
- [ ] H2 DataSource kết nối được và bảng books được tạo.
- [ ] POST tạo được sách và trả HTTP 201.
- [ ] GET đọc được danh sách và một bản ghi.
- [ ] Tìm theo author hoạt động không phân biệt hoa thường.
- [ ] PUT cập nhật được bản ghi.
- [ ] DELETE xóa được bản ghi và trả HTTP 204.
- [ ] ID không tồn tại trả HTTP 404; dữ liệu không hợp lệ trả HTTP 400.
- [ ] Hiểu cách thay H2 driver bằng driver của MySQL hoặc PostgreSQL.
