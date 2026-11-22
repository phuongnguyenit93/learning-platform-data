# Khai báo entity, repository và chạy API đầu tiên

Spring Data REST có thể tự công bố một Spring Data repository thành REST API. Để chạy được API đầu tiên, ứng dụng cần có ba phần chính: một entity mô tả dữ liệu, một repository khai báo cách truy cập dữ liệu và một ứng dụng Spring Boot để khởi động các thành phần đó. Khi thêm cấu hình cơ sở dữ liệu và base path, Spring Data REST tự tạo các endpoint HTTP mà không cần viết controller CRUD.

Bài này xây dựng một API quản lý sách nhỏ bằng Java 17+, Spring Boot 3.5.0, Spring Data JPA và H2. Sau khi chạy ứng dụng, ta sẽ gọi API bằng HTTP để đọc danh sách và tạo một quyển sách.

## 1. Ba thành phần cần có

### Entity

Entity là lớp Java ánh xạ tới dữ liệu được lưu trong database. Với JPA, lớp được đánh dấu bằng `@Entity`; một trường được đánh dấu `@Id` làm khóa chính. `@GeneratedValue` cấu hình cách sinh khóa khi thêm bản ghi mới.

Ví dụ, entity `Book` có thể có các thuộc tính `id`, `title` và `author`. Entity không tự tạo REST endpoint. Nó mô tả cấu trúc dữ liệu mà repository sẽ thao tác.

### Repository

Repository là interface định nghĩa cách ứng dụng truy cập dữ liệu. Khi kế thừa `JpaRepository<Book, Long>`, repository nhận được các thao tác có sẵn như `save`, `findById`, `findAll`, `deleteById`, cùng khả năng phân trang và sắp xếp.

Spring Data tạo implementation cho interface này khi ứng dụng khởi động. Ta không cần tự viết lớp triển khai CRUD cơ bản.

### Spring Data REST

Spring Data REST phát hiện repository được export và tạo REST resource tương ứng. Với repository quản lý `Book`, framework có thể cung cấp collection endpoint, item endpoint và các thao tác HTTP CRUD. `@RepositoryRestResource` cho phép đặt đường dẫn collection và tên relation trong HAL.

Luồng cơ bản:

1. Client gửi HTTP request tới một endpoint.
2. Spring Data REST ánh xạ endpoint tới repository.
3. Repository thực hiện thao tác trên entity thông qua JPA.
4. Spring Data REST chuyển kết quả thành HTTP response, thường sử dụng HAL JSON.

## 2. Tạo cấu trúc dự án

Tạo một Maven project có cấu trúc như sau. Đặt lớp khởi động, entity và repository trong cùng package hoặc các package con của package chứa lớp khởi động để Spring Boot có thể tự động tìm thấy chúng.

```text
spring-data-rest-first-api/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/books/
        │       ├── BookApiApplication.java
        │       ├── Book.java
        │       └── BookRepository.java
        └── resources/
            └── application.properties
```

## 3. Khai báo dependency Maven

Tạo file `pom.xml` ở thư mục gốc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-first-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
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

Các dependency có vai trò:

- `spring-boot-starter-data-rest`: tích hợp Spring Data REST, tự công bố repository thành REST resource.
- `spring-boot-starter-data-jpa`: tích hợp Spring Data JPA và Hibernate để thao tác với database quan hệ.
- `h2`: database nhẹ chạy trong bộ nhớ, phù hợp cho bài thực hành không cần cài database riêng.

Spring Boot parent quản lý các phiên bản thư viện tương thích. Không cần khai báo phiên bản riêng cho từng dependency ở trên. Phiên bản 3.5.0 được cố định để ví dụ có thể tái lập; khi bắt đầu dự án mới, hãy chọn bản Spring Boot đang được duy trì và tương thích với môi trường của mình.

## 4. Tạo entity Book

Tạo file `src/main/java/com/example/books/Book.java`:

```java
package com.example.books;

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

    @Column(nullable = false, length = 200)
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
```

Giải thích các annotation và thành phần:

- `@Entity` đánh dấu lớp là entity do JPA quản lý.
- `@Table(name = "books")` chỉ định tên bảng trong database. Nếu bỏ annotation này, JPA sẽ suy ra tên bảng theo quy tắc đặt tên.
- `@Id` xác định trường khóa chính.
- `@GeneratedValue(strategy = GenerationType.IDENTITY)` dùng cơ chế identity của database để sinh khóa chính khi insert.
- `@Column(nullable = false, length = ...)` khai báo ràng buộc cột ở mức schema. Đây không phải là kiểm tra dữ liệu đầu vào đầy đủ ở tầng API.
- Constructor không tham số có phạm vi `protected` để JPA có thể tạo entity. Constructor còn lại giúp tạo đối tượng mới từ mã Java.

Các getter giúp framework đọc thuộc tính khi tạo representation JSON; setter cho phép cập nhật thuộc tính trong ví dụ này. Trong ứng dụng thật, cần quyết định rõ trường nào client được phép thay đổi.

## 5. Khai báo BookRepository

Tạo file `src/main/java/com/example/books/BookRepository.java`:

```java
package com.example.books;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

Đọc khai báo này theo từng phần:

- `BookRepository` là repository quản lý entity `Book`.
- Tham số thứ nhất của `JpaRepository` là kiểu entity.
- Tham số thứ hai là kiểu dữ liệu của khóa chính; trong ví dụ này là `Long`.
- `path = "books"` đặt collection URL thành `/books` trước khi thêm base path.
- `collectionResourceRel = "books"` đặt tên relation của collection trong representation HAL.

Không cần tạo class `BookRepositoryImpl` cho các thao tác CRUD thông thường. Spring Data tạo implementation lúc ứng dụng khởi động. Các repository được export mặc định có thể được Spring Data REST công bố; annotation ở đây giúp đặt URL và relation một cách tường minh.

## 6. Tạo lớp khởi động Spring Boot

Tạo file `src/main/java/com/example/books/BookApiApplication.java`:

```java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
```

`@SpringBootApplication` bật cấu hình tự động và component scanning từ package `com.example.books` trở xuống. Nhờ đó, Spring Boot tìm được entity và repository trong cấu trúc dự án trên, đồng thời cấu hình các thành phần Spring Data JPA và Spring Data REST theo dependency đã thêm.

Phương thức `main` gọi `SpringApplication.run` để khởi động application context và web server nhúng. Không cần viết `@RestController` cho CRUD endpoint của `BookRepository`.

## 7. Cấu hình database và REST base path

Tạo file `src/main/resources/application.properties`:

```properties
spring.application.name=spring-data-rest-first-api

spring.datasource.url=jdbc:h2:mem:booksdb
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

spring.data.rest.base-path=/api
```

Ý nghĩa:

- `spring.datasource.url` tạo database H2 trong bộ nhớ có tên `booksdb`.
- `spring.datasource.username` và `spring.datasource.password` là thông tin kết nối ví dụ cho H2 local.
- `spring.jpa.hibernate.ddl-auto=create-drop` yêu cầu Hibernate tạo schema khi ứng dụng khởi động và xóa schema khi ứng dụng dừng.
- `spring.jpa.open-in-view=false` tắt Open EntityManager in View để tránh việc truy cập database ngầm trong quá trình render response.
- `spring.data.rest.base-path=/api` thêm tiền tố `/api` vào các endpoint do Spring Data REST công bố.

Với cấu hình này, collection path `/books` trở thành `/api/books`. H2 in-memory không giữ dữ liệu sau khi ứng dụng dừng; đây là lựa chọn cho thực hành. Khi triển khai thật, hãy cấu hình database bền vững, quản lý schema bằng migration và không dùng mật khẩu ví dụ.

## 8. Chạy ứng dụng lần đầu

Mở terminal tại thư mục chứa `pom.xml`, sau đó chạy:

```bash
mvn clean package
mvn spring-boot:run
```

Nếu dự án dùng Maven Wrapper, có thể chạy:

```bash
./mvnw clean package
./mvnw spring-boot:run
```

Trên Windows, dùng `mvnw.cmd` thay cho `./mvnw`.

Khi khởi động thành công, Spring Boot chạy web server mặc định tại cổng `8080`. Nếu cổng đó đang được chương trình khác sử dụng, thêm cấu hình sau vào `application.properties` để đổi cổng:

```properties
server.port=8081
```

Khi đó, thay `localhost:8080` bằng `localhost:8081` trong các lệnh HTTP bên dưới.

## 9. Kiểm tra API đầu tiên

### 9.1. Khám phá API root

Gửi request tới base path:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
```

Spring Data REST trả về tài nguyên gốc với các liên kết tới repository resource được export. Đây là cách khám phá những collection mà server công bố.

### 9.2. Đọc collection books

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
```

Lúc mới khởi động, database chưa có dữ liệu nên collection rỗng. Response HAL có thể chứa thông tin phân trang và liên kết trong `_links`; khi có phần tử, tài nguyên collection thường được biểu diễn trong `_embedded.books`.

Các điểm cần quan sát:

- HTTP status là `200 OK` khi request đọc thành công.
- `Content-Type` cho biết định dạng response.
- `_links` chứa các URI để client tiếp tục truy cập.
- `page` mô tả thông tin phân trang nếu response collection cung cấp phần này.

### 9.3. Tạo một quyển sách

Gửi request POST tới collection endpoint:

```bash
curl -i -X POST ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/hal+json" ^
  -d "{\"title\":\"Effective Java\",\"author\":\"Joshua Bloch\"}" ^
  http://localhost:8080/api/books
```

Lệnh trên dùng cú pháp nối dòng của Windows Command Prompt. Trên macOS/Linux hoặc Git Bash, dùng dấu gạch chéo ngược để nối dòng:

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Effective Java","author":"Joshua Bloch"}' \
  http://localhost:8080/api/books
```

Request gồm:

- Method `POST` để tạo một phần tử trong collection.
- Header `Content-Type: application/json` cho biết request body là JSON.
- Header `Accept: application/hal+json` yêu cầu response theo HAL JSON.
- JSON body cung cấp các thuộc tính mà entity nhận được.

Khi tạo thành công, server thường trả `201 Created` và header `Location` trỏ tới URI của item mới. Response body có thể có hoặc không tùy cấu hình trả body của Spring Data REST. Hãy đọc giá trị `Location` để biết URI và ID thực tế do database sinh ra.

### 9.4. Đọc lại tài nguyên vừa tạo

Dùng URI trong header `Location` để gửi GET. Ví dụ, nếu header cho biết item có ID là `1`:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books/1
```

Response thành công là `200 OK` và representation chứa dữ liệu sách đã lưu. ID trong ví dụ chỉ minh họa; không giả định database luôn cấp ID bắt đầu từ 1.

### 9.5. Đọc lại collection

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
```

Lúc này collection có thể chứa sách vừa tạo trong relation `books`. Như vậy, chỉ với entity, repository và cấu hình, ta đã tạo và gọi được API đầu tiên mà không cần viết controller CRUD.

## 10. Những endpoint cơ bản được tạo ra

Với repository `BookRepository` được export, Spring Data REST cung cấp các thao tác resource tiêu chuẩn. Các đường dẫn bên dưới dựa trên base path và collection path của ví dụ:

| HTTP method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/books` | Đọc collection |
| POST | `/api/books` | Tạo một book |
| GET | `/api/books/{id}` | Đọc một book |
| PUT | `/api/books/{id}` | Gửi representation đầy đủ để cập nhật/thay thế |
| PATCH | `/api/books/{id}` | Cập nhật một phần thuộc tính |
| DELETE | `/api/books/{id}` | Xóa một book |

Không phải mọi request đều thành công chỉ vì endpoint tồn tại. ID không có trong database, JSON sai định dạng, ràng buộc database hoặc cấu hình bảo mật đều có thể làm request thất bại. Khi kiểm tra, hãy đọc cả status code, header và response body.

## 11. Các lỗi khởi tạo thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Ứng dụng không khởi động | Maven không tải được dependency, JDK không đúng hoặc cấu hình sai | Kiểm tra `java -version`, `mvn -version` và phần đầu tiên của stack trace |
| Không tìm thấy entity/table | Entity nằm ngoài phạm vi package scan hoặc thiếu `@Entity` | Đặt entity trong package con của package ứng dụng và kiểm tra annotation |
| Repository không được công bố | Repository không được Spring Data phát hiện hoặc bị cấu hình `exported = false` | Kiểm tra package, kiểu repository và annotation export |
| Gọi sai URL nhận 404 | Quên base path hoặc sai collection path | Đối chiếu `spring.data.rest.base-path`, `@RepositoryRestResource(path=...)` và API root |
| POST nhận 400 | JSON không hợp lệ hoặc kiểu dữ liệu không khớp | Kiểm tra body JSON và response lỗi |
| POST nhận 415 | Thiếu hoặc sai Content-Type | Gửi `Content-Type: application/json` |
| GET nhận 406 | Header Accept yêu cầu media type không được hỗ trợ | Thử `Accept: application/hal+json` |
| Không kết nối được cổng 8080 | Server chưa chạy hoặc cổng bị chiếm | Kiểm tra log khởi động và `server.port` |

Nếu dùng PowerShell, lệnh `curl` có thể là alias của `Invoke-WebRequest`. Gọi `curl.exe` để chắc chắn sử dụng chương trình curl. Cú pháp nối dòng của PowerShell cũng khác Command Prompt; khi gặp lỗi quoting, hãy chạy request trên một dòng hoặc dùng đúng cú pháp shell đang mở.

## 12. Các lưu ý trước khi dùng trong ứng dụng thật

Ví dụ này tập trung vào việc khởi tạo API nên chưa cấu hình Spring Security, validation nghiệp vụ hoặc database production. Khi phát triển ứng dụng thật:

- Chỉ export những repository và thao tác mà client cần.
- Bảo vệ endpoint bằng xác thực và phân quyền ở server. Việc một liên kết không xuất hiện trong HAL không có nghĩa là tài nguyên được bảo vệ.
- Dùng Bean Validation và xử lý lỗi phù hợp để kiểm tra dữ liệu đầu vào; ràng buộc `nullable = false` ở cột database không thay thế validation ở API.
- Xem xét DTO hoặc projection khi entity có trường nội bộ không nên công bố.
- Đặt các quy tắc nghiệp vụ vào service/domain. Repository REST phù hợp với CRUD chuẩn; một quy trình nhiều bước có thể cần endpoint nghiệp vụ riêng.
- Dùng database bền vững và migration thay cho H2 in-memory cùng `create-drop` khi cần giữ dữ liệu.
- Kiểm thử API và quyền truy cập trước khi triển khai ra mạng công cộng.

## 13. Kết luận

Để chạy API đầu tiên với Spring Data REST, ta khai báo entity bằng JPA, tạo repository kế thừa `JpaRepository`, thêm dependency Spring Data REST và cấu hình ứng dụng Spring Boot. Spring Data REST phát hiện repository được export rồi tự tạo các REST resource. Với ví dụ `Book`, collection endpoint là `/api/books`; client có thể dùng GET để đọc và POST để tạo sách.

Khi hiểu vai trò của entity, repository, base path và các HTTP method, ta có thể tự khởi tạo API CRUD nhỏ và biết vị trí cần kiểm tra khi endpoint chưa hoạt động.