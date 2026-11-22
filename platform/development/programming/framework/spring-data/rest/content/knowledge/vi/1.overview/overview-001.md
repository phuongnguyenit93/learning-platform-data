# Spring Data REST là gì và bài toán tự động công bố repository qua HTTP

Spring Data REST là thành phần của hệ sinh thái Spring Data giúp biến các repository thành tài nguyên REST có thể truy cập qua HTTP. Thay vì tự viết một controller cho từng thao tác tạo, đọc, cập nhật và xóa dữ liệu (CRUD), ứng dụng có thể khai báo repository và để Spring Data REST tự tạo các endpoint tương ứng.

Cách làm này phù hợp với những API quản trị hoặc dịch vụ có nghiệp vụ CRUD tương đối chuẩn. Nó giúp giảm mã lặp, nhưng cũng khiến cấu trúc API gắn chặt hơn với repository và mô hình miền. Vì vậy, cần hiểu rõ tài nguyên nào được công bố và kiểm soát quyền truy cập trước khi dùng trong môi trường thật.

## 1. Bài toán: công bố dữ liệu qua HTTP

Một ứng dụng quản lý sách thường cần các thao tác:

- Lấy danh sách sách.
- Xem một quyển sách theo mã.
- Tạo sách mới.
- Sửa thông tin sách.
- Xóa sách.
- Tìm sách theo tiêu chí như tiêu đề.

Nếu tự xây dựng REST API bằng Spring MVC, ta thường phải viết controller, gọi service hoặc repository, chuyển đổi dữ liệu vào/ra, chọn mã trạng thái HTTP và xử lý các trường hợp lỗi. Với nhiều loại tài nguyên, phần mã này có thể lặp lại đáng kể.

Spring Data REST giải quyết phần CRUD phổ biến bằng cách đọc metadata của Spring Data repository và tự công bố các tài nguyên HTTP. Nhà phát triển vẫn định nghĩa entity, repository và quy tắc nghiệp vụ; framework đảm nhiệm phần ánh xạ repository thành REST resource.

Ví dụ, một repository quản lý `Book` có thể tạo ra các endpoint như:

| HTTP | Endpoint | Ý nghĩa |
|---|---|---|
| GET | `/api/books` | Lấy danh sách sách |
| GET | `/api/books/{id}` | Lấy một quyển sách |
| POST | `/api/books` | Tạo sách |
| PUT | `/api/books/{id}` | Thay thế/cập nhật tài nguyên |
| PATCH | `/api/books/{id}` | Cập nhật một phần tài nguyên |
| DELETE | `/api/books/{id}` | Xóa sách |

Các đường dẫn trên là kết quả của cấu hình ví dụ trong bài. Nếu không chỉ định đường dẫn, Spring Data REST tự suy ra đường dẫn collection từ kiểu domain; có thể kiểm tra các đường dẫn thực tế qua tài nguyên gốc của API.

## 2. Spring Data REST hoạt động như thế nào?

Spring Data REST tích hợp với các repository thuộc những module Spring Data tương ứng, chẳng hạn repository dùng JPA. Khi ứng dụng khởi động, framework phát hiện các repository được phép công bố, đọc kiểu domain và các phương thức được export, sau đó đăng ký các HTTP resource phù hợp.

Luồng xử lý tổng quát:

1. Client gửi HTTP request đến endpoint của tài nguyên.
2. Spring Data REST tìm repository resource tương ứng.
3. Framework chuyển request thành thao tác trên repository.
4. Repository làm việc với persistence provider hoặc datastore.
5. Kết quả được biểu diễn thành representation HTTP và trả về client.

Spring Data REST thường dùng HAL (Hypertext Application Language) để biểu diễn tài nguyên. JSON HAL có các trường như `_links` để mô tả liên kết đến tài nguyên liên quan và `_embedded` để chứa tài nguyên được nhúng. Client có thể đi theo các liên kết này thay vì phải tự đoán mọi URL.

Ví dụ, response của collection có thể chứa liên kết đến chính collection, tài nguyên gốc và các chức năng tìm kiếm. Cấu trúc chi tiết phụ thuộc repository, cấu hình và dữ liệu thực tế.

**Điểm cần nhớ:** Spring Data REST công bố repository được phát hiện và cho phép export. Nó không tự động biến mọi bảng trong cơ sở dữ liệu thành API. Phạm vi endpoint phụ thuộc repository, phương thức được export và cấu hình của ứng dụng.

## 3. Tạo ví dụ Spring Boot chạy được

Ví dụ dưới đây dùng Java 17+, Spring Boot 3.5.0, Spring Data JPA, Spring Data REST và cơ sở dữ liệu H2 trong bộ nhớ. Phiên bản trong ví dụ là mốc cụ thể để minh họa; dự án thực tế nên dùng bản vá Spring Boot còn được duy trì và tương thích với môi trường triển khai.

Cấu trúc thư mục:

```text
spring-data-rest-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/demo/
        │       ├── DemoApplication.java
        │       ├── Book.java
        │       └── BookRepository.java
        └── resources/
            └── application.properties
```

### 3.1. Khai báo dependency

Tạo file `pom.xml`:

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

- `spring-boot-starter-data-rest` cung cấp khả năng công bố repository thành REST resource.
- `spring-boot-starter-data-jpa` cung cấp tích hợp JPA và Hibernate.
- H2 là cơ sở dữ liệu trong bộ nhớ để chạy thử mà không cần cài một database riêng.

### 3.2. Tạo entity

Tạo `src/main/java/com/example/demo/Book.java`:

```java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;
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

Entity mô tả dữ liệu được lưu. Với JPA, `@Entity` đánh dấu lớp là persistent entity; `@Id` xác định khóa chính và `@GeneratedValue` yêu cầu persistence provider sinh giá trị khóa theo chiến lược đã chọn.

### 3.3. Khai báo repository

Tạo `src/main/java/com/example/demo/BookRepository.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(
        @Param("title") String title
    );
}
```

Khai báo này có hai tác dụng:

- `JpaRepository<Book, Long>` cung cấp các thao tác repository phổ biến cho entity `Book`.
- `@RepositoryRestResource` yêu cầu Spring Data REST công bố repository với collection path là `books` và relation name là `books`.

Phương thức truy vấn theo tên `findByTitleContainingIgnoreCase` được Spring Data JPA diễn giải thành truy vấn tìm tiêu đề có chứa chuỗi truyền vào, không phân biệt chữ hoa/chữ thường. `@RestResource` đặt đường dẫn tìm kiếm thành `by-title`, nên endpoint tìm kiếm là `/api/books/search/by-title`. `@Param("title")` xác định tên query parameter trên URL.

### 3.4. Tạo lớp khởi động ứng dụng

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;

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
    CommandLineRunner seedBooks(BookRepository books) {
        return args -> {
            if (books.count() == 0) {
                books.saveAll(List.of(
                    new Book("Clean Code", "Robert C. Martin"),
                    new Book("Effective Java", "Joshua Bloch")
                ));
            }
        };
    }
}
```

Runner thêm hai bản ghi mẫu khi database chưa có sách. Việc này giúp có dữ liệu để kiểm tra endpoint GET và tìm kiếm ngay sau khi ứng dụng khởi động.

### 3.5. Cấu hình ứng dụng

Tạo `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:booksdb
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

spring.data.rest.base-path=/api
```

`spring.data.rest.base-path=/api` đặt tiền tố chung cho các endpoint do Spring Data REST tạo. Vì vậy collection `books` được truy cập tại `/api/books`.

H2 trong bộ nhớ chỉ tồn tại trong vòng đời ứng dụng. `create-drop` tạo schema khi khởi động và xóa schema khi ứng dụng dừng; cấu hình này tiện cho ví dụ nhưng không phù hợp để lưu dữ liệu lâu dài trong production.

### 3.6. Chạy ứng dụng

Tại thư mục có `pom.xml`, chạy:

```bash
mvn spring-boot:run
```

Khi ứng dụng khởi động thành công, server mặc định lắng nghe tại cổng 8080. Log khởi động phụ thuộc phiên bản và môi trường nên không có một stdout cố định để đối chiếu. Nếu cổng 8080 đang được sử dụng, hãy đổi cổng bằng cấu hình `server.port`.

## 4. Gọi các endpoint được tạo tự động

Các ví dụ dưới đây giả sử ứng dụng đang chạy tại `http://localhost:8080`. Header `Accept: application/hal+json` yêu cầu representation HAL.

### 4.1. Khám phá API từ tài nguyên gốc

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api
```

Tài nguyên gốc cung cấp các liên kết đến repository resource đã được công bố. Đây là điểm bắt đầu hữu ích để client khám phá API và kiểm tra tên relation thực tế.

### 4.2. Lấy danh sách sách

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/books
```

Response collection thường chứa thông tin phân trang, các liên kết điều hướng và danh sách tài nguyên được nhúng trong `_embedded.books`. Tên relation `books` đến từ cấu hình `collectionResourceRel`.

Có thể phân trang và sắp xếp bằng query parameter:

```bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/books?page=0&size=10&sort=title,asc"
```

`page` bắt đầu từ 0. `size` yêu cầu số phần tử trong một trang; giới hạn tối đa còn phụ thuộc cấu hình Spring Data REST.

### 4.3. Lấy một quyển sách

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/books/1
```

Mã `1` là ví dụ về ID. Trong ứng dụng thật, client cần lấy URI của item từ liên kết trong response collection hoặc từ response tạo mới.

### 4.4. Tạo sách mới

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Domain-Driven Design","author":"Eric Evans"}' \
  http://localhost:8080/api/books
```

Request gửi JSON đại diện cho entity. Khi tạo thành công, server trả mã `201 Created` và thông tin vị trí tài nguyên mới qua header `Location`. Việc có trả thêm body hay không phụ thuộc cấu hình trả response body của Spring Data REST.

### 4.5. Cập nhật và xóa

Dùng `PUT` khi muốn gửi representation để thay thế/cập nhật tài nguyên theo hợp đồng của endpoint:

```bash
curl -i -X PUT \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Domain-Driven Design","author":"Eric Evans"}' \
  http://localhost:8080/api/books/1
```

Dùng `PATCH` khi chỉ muốn thay đổi một phần dữ liệu:

```bash
curl -i -X PATCH \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"author":"Eric Evans"}' \
  http://localhost:8080/api/books/1
```

Xóa tài nguyên bằng:

```bash
curl -i -X DELETE http://localhost:8080/api/books/1
```

Hãy kiểm tra response status và representation sau mỗi thao tác. Ví dụ trên minh họa các phương thức HTTP phổ biến; quy tắc validation, quyền truy cập và xử lý lỗi vẫn cần được cấu hình phù hợp với ứng dụng.

### 4.6. Gọi endpoint tìm kiếm

Phương thức repository đã khai báo tạo search resource:

```bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "title=java" \
  http://localhost:8080/api/books/search/by-title
```

Spring Data REST đặt các query method được export dưới nhánh `search`. Tên path và tên tham số được điều khiển bởi `@RestResource` và `@Param` trong ví dụ.

## 5. Tùy chỉnh phạm vi công bố

Không phải repository nào cũng nên trở thành API công khai. Spring Data REST cung cấp annotation và cấu hình để điều chỉnh endpoint.

### 5.1. Đổi đường dẫn và tên relation

```java
@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

- `path` quyết định phần đường dẫn URL của collection.
- `collectionResourceRel` quyết định tên relation trong representation HAL.

Có thể đổi base path chung bằng thuộc tính:

```properties
spring.data.rest.base-path=/api
```

### 5.2. Ẩn repository hoặc phương thức

Nếu không muốn công bố toàn bộ repository, có thể đặt `exported = false`:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
```

Nếu chỉ muốn ẩn một phương thức, có thể ghi đè phương thức repository và đánh dấu:

```java
@RestResource(exported = false)
@Override
void deleteById(Long id);
```

Hãy xác định chính xác các phương thức cần công bố. Ẩn một endpoint giúp thu hẹp API được tạo tự động, nhưng không thay thế cơ chế xác thực và phân quyền.

### 5.3. Bổ sung endpoint nghiệp vụ riêng

Spring Data REST không buộc ứng dụng phải dùng nó cho mọi API. Có thể kết hợp repository resource tự động với controller/service thông thường. Những luồng như thanh toán, duyệt đơn, tính giá, gọi hệ thống bên ngoài hoặc phối hợp nhiều aggregate thường cần endpoint riêng để thể hiện rõ nghiệp vụ, kiểm tra điều kiện và kiểm soát transaction.

## 6. Khi nào nên dùng và những giới hạn cần hiểu

Spring Data REST phù hợp khi:

- Tài nguyên có các thao tác CRUD tương đối chuẩn.
- Repository và mô hình domain phản ánh khá sát API mà client cần.
- Muốn có phân trang, sắp xếp, tìm kiếm repository và liên kết HAL mà không phải tự viết nhiều controller.
- Nhóm phát triển chấp nhận API được suy ra từ repository và có quy trình quản lý thay đổi API.

Nên cân nhắc controller/service riêng khi:

- Một request cần phối hợp nhiều repository hoặc nhiều bước nghiệp vụ.
- API cần DTO riêng, quy trình xác nhận nhiều bước hoặc response không tương ứng trực tiếp với entity.
- Cần kiểm soát chặt hợp đồng API độc lập với cấu trúc persistence.
- Endpoint có quy tắc quyền truy cập hoặc validation đặc thù theo từng thao tác.

Một số giới hạn thực tế:

1. **API gắn với mô hình repository:** thay đổi entity, repository hoặc tên phương thức truy vấn có thể ảnh hưởng đến representation và endpoint.
2. **Entity không nhất thiết là hợp đồng API tốt:** việc trả entity trực tiếp có thể làm lộ trường nội bộ hoặc khiến client phụ thuộc vào cấu trúc lưu trữ.
3. **Không thay thế tầng nghiệp vụ:** các quy tắc như chuyển trạng thái hợp lệ, kiểm tra tồn kho hoặc tính phí nên nằm trong service/domain phù hợp.
4. **Quan hệ được biểu diễn bằng liên kết:** client cần hiểu HAL và theo các URI quan hệ; không nên giả định mọi association luôn xuất hiện như object lồng nhau.
5. **Cần kiểm soát hiệu năng:** phân trang, fetch strategy, truy vấn tìm kiếm và số lượng liên kết cần được đánh giá với dữ liệu thực tế.

## 7. Bảo mật trước khi đưa lên môi trường thật

Repository được export sẽ tạo ra bề mặt HTTP có thể truy cập. Nếu ứng dụng không cấu hình bảo vệ phù hợp, dữ liệu có thể bị đọc hoặc thay đổi ngoài ý muốn.

Trước khi triển khai, cần:

- Thêm Spring Security và cấu hình xác thực, phân quyền cho các endpoint.
- Chỉ export những repository và phương thức thực sự cần thiết.
- Giới hạn thao tác theo vai trò và theo quyền sở hữu dữ liệu khi nghiệp vụ yêu cầu.
- Kiểm tra dữ liệu đầu vào và các ràng buộc nghiệp vụ; không coi việc entity có setter là đủ để cho phép cập nhật mọi trường.
- Kiểm tra các trường được serialize. Dùng projection hoặc controller/DTO khi cần representation phù hợp; projection không phải cơ chế phân quyền.
- Cấu hình CORS có chủ đích nếu client chạy ở origin khác.
- Dùng database bền vững, migration/schema management và cấu hình secrets phù hợp cho production; không dùng H2 in-memory cùng `create-drop` để lưu dữ liệu thật.

Không nên dựa vào việc client không nhìn thấy một liên kết HAL để bảo vệ tài nguyên. Quyền truy cập phải được kiểm tra ở phía server cho từng request.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| `404 Not Found` | Sai base path, collection path hoặc repository không được export | Gọi tài nguyên gốc `/api`, kiểm tra `_links` và annotation |
| `405 Method Not Allowed` | Phương thức HTTP không được hỗ trợ cho resource đó hoặc endpoint đã bị ẩn | Kiểm tra loại resource và cấu hình export |
| `400 Bad Request` | JSON sai định dạng, kiểu dữ liệu không hợp lệ hoặc validation thất bại | Kiểm tra request body và thông tin lỗi trả về |
| `415 Unsupported Media Type` | Thiếu hoặc sai `Content-Type` | Gửi `Content-Type: application/json` cho JSON body |
| `406 Not Acceptable` | Server không thể trả representation theo `Accept` được yêu cầu | Thử `Accept: application/hal+json` |
| Không thấy search resource | Phương thức truy vấn không được export hoặc repository chưa được phát hiện | Kiểm tra method, annotation và tài nguyên `search` |
| Không thấy trường mong muốn | Trường không được serialize hoặc representation bị giới hạn | Kiểm tra getter, mapping, projection và response thực tế |

Khi dùng PowerShell trên Windows, lệnh `curl` có thể là alias của `Invoke-WebRequest` ở một số phiên bản. Có thể gọi rõ `curl.exe` để chạy đúng chương trình curl.

## 9. Kết luận

Spring Data REST tự động công bố các Spring Data repository thành REST resource qua HTTP. Chỉ với entity và repository, ứng dụng có thể có CRUD endpoint, search resource, phân trang, sắp xếp và representation HAL. Đây là cách nhanh để xây dựng API cho những tài nguyên có hành vi CRUD chuẩn.

Giá trị của Spring Data REST nằm ở việc giảm mã kết nối lặp lại. Để dùng đúng, cần chọn repository được export, hiểu API được sinh ra, bảo vệ endpoint và chuyển các quy trình nghiệp vụ phức tạp sang service/controller chuyên biệt khi cần.
