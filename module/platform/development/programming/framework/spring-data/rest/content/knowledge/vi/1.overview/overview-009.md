# Kiến thức nền cần có và thứ tự học Spring Data REST

Spring Data REST giúp xuất bản các repository của Spring Data thành tài nguyên HTTP theo quy ước. Khi một repository được export, framework có thể cung cấp các endpoint đọc, tạo, cập nhật, xóa, tìm kiếm và quản lý liên kết giữa tài nguyên mà không cần viết một controller CRUD riêng cho từng entity. Dữ liệu thường được biểu diễn bằng JSON theo HAL, kèm các liên kết để client khám phá API.

Mục tiêu của bài này là giúp người học biết cần nắm kiến thức nào trước, hiểu luồng xử lý của Spring Data REST, dựng được một ứng dụng nhỏ và chọn thứ tự học đủ chắc để dùng framework an toàn trong dự án.

## 1. Spring Data REST là gì?

Spring Data REST nằm trên lớp repository abstraction của Spring Data. Ứng dụng vẫn định nghĩa repository như khi dùng Spring Data JPA, Spring Data MongoDB hoặc một module Spring Data khác. Spring Data REST đọc các repository được export và công bố chúng dưới dạng REST resource.

Cần phân biệt ba thành phần:

- **Spring Data** cung cấp abstraction cho truy cập dữ liệu: repository, query method, phân trang, sắp xếp và các kiểu dữ liệu như Page, Slice, Pageable.
- **Spring Data JPA** là một module Spring Data làm việc với JPA và nhà cung cấp persistence như Hibernate. Nó quản lý việc ánh xạ entity và thao tác cơ sở dữ liệu quan hệ.
- **Spring Data REST** công bố repository thành REST API và bổ sung các quy ước về resource, URI, HAL, tìm kiếm, projection, sự kiện và cấu hình endpoint.

Spring Data REST không tự thiết kế toàn bộ nghiệp vụ của ứng dụng. Nó tự động hóa lớp HTTP quanh repository. Những quy trình nghiệp vụ nhiều bước, payload đặc thù, quy tắc phân quyền phức tạp hoặc API cần một hợp đồng riêng vẫn có thể cần service và controller do ứng dụng tự viết.

Một số khả năng chính:

- Công bố collection resource và item resource từ repository.
- Hỗ trợ các thao tác HTTP theo khả năng của repository.
- Công bố query method dưới đường dẫn search.
- Hỗ trợ phân trang, sắp xếp và lọc qua query method.
- Biểu diễn liên kết giữa resource bằng hypermedia.
- Cho phép tùy chỉnh đường dẫn, tên relation, repository hoặc method được export.
- Hỗ trợ projection, event handler, validation và tích hợp với Spring Security.

## 2. Kiến thức nền cần có

Không cần học tất cả Spring Framework trước khi bắt đầu. Tuy vậy, người học nên có nền tảng ở các phần sau.

### 2.1. Java cơ bản và hướng đối tượng

Cần sử dụng thành thạo:

- Class, object, interface, access modifier và package.
- Constructor, encapsulation, kế thừa và đa hình.
- Generic type và interface có generic, ví dụ Repository<T, ID>.
- Collection như List, Set và Map.
- Exception, enum, annotation và lambda ở mức đọc hiểu.
- Optional và cách xử lý giá trị có thể vắng mặt.
- Quy ước getter, setter và constructor không tham số trong class được JPA quản lý.

Lý do: entity và repository là các kiểu Java. Spring Data dùng generic và annotation để suy ra kiểu entity, kiểu khóa chính và quy tắc truy vấn.

### 2.2. HTTP, REST và JSON

Đây là phần bắt buộc vì Spring Data REST tạo API HTTP. Hãy hiểu:

- **Resource** là tài nguyên được nhận diện bằng URI; ví dụ một cuốn sách có URI riêng.
- **GET** đọc resource; **POST** thường tạo resource trong collection; **PUT** thay thế hoặc cập nhật resource theo hợp đồng endpoint; **PATCH** cập nhật một phần; **DELETE** xóa resource hoặc gỡ một liên kết tùy endpoint.
- Các status code phổ biến: 200, 201, 204, 400, 401, 403, 404, 409 và 500.
- Header Content-Type mô tả định dạng request body; Accept mô tả định dạng client muốn nhận.
- JSON object, array, string, number, boolean và null.
- Idempotency: gửi lặp một request có tạo ra cùng trạng thái hay gây thêm tác động.
- Query parameter, path variable, request body và response header.
- Phân trang, sắp xếp và ý nghĩa của page, size, sort.
- Khái niệm hypermedia: response có liên kết để client khám phá thao tác và resource tiếp theo.

Spring Data REST thường trả về HAL JSON. Vì vậy, ngoài JSON thông thường, hãy nhận biết hai thuộc tính quan trọng:

- **_links** chứa các liên kết như self, profile hoặc liên kết đến resource liên quan.
- **_embedded** chứa các resource được nhúng trong response collection.

Không nên giả định mọi response đều chỉ là một object JSON phẳng.

### 2.3. Spring Framework và Spring Boot

Nên hiểu các khái niệm sau trước khi tìm hiểu phần tự động export:

- Inversion of Control và Dependency Injection.
- Bean, ApplicationContext, component scan và cấu hình bằng annotation.
- Spring Boot auto-configuration và starter dependency.
- Cấu hình ứng dụng bằng application.properties hoặc application.yml.
- Spring MVC ở mức cơ bản: DispatcherServlet, controller, request mapping, message converter và exception handling.
- Profile, cấu hình theo môi trường và cách chạy ứng dụng.

Bạn không cần tự viết controller cho từng repository khi dùng Spring Data REST, nhưng hiểu Spring MVC sẽ giúp đọc stack trace, cấu hình HTTP và tích hợp endpoint tùy chỉnh.

### 2.4. Spring Data và tầng lưu trữ

Trước Spring Data REST, hãy biết cách tạo và dùng repository trực tiếp:

- Repository abstraction và repository interface.
- CrudRepository cho thao tác CRUD cơ bản.
- PagingAndSortingRepository cho phân trang và sắp xếp.
- JpaRepository khi dùng Spring Data JPA.
- Query method theo tên method, ví dụ findByTitleContainingIgnoreCase.
- @Query ở mức cơ bản khi cần truy vấn tùy chỉnh.
- Optional, List, Page, Slice, Pageable và Sort.
- Khác biệt giữa entity, repository, service và controller.

Nếu dùng JPA, cần thêm:

- @Entity, @Id, @GeneratedValue, @Column và @Table.
- Quan hệ @OneToOne, @OneToMany, @ManyToOne và @ManyToMany.
- Phía sở hữu quan hệ và mappedBy.
- Fetch type LAZY/EAGER, cascade và orphanRemoval.
- Persistence context, dirty checking và transaction.
- Vòng đời entity và các vấn đề khi serialize quan hệ lazy.

Các khái niệm JPA này rất quan trọng khi REST API cho phép client đọc hoặc thay đổi association giữa các entity. Nếu dùng MongoDB hay một store khác, thay kiến thức JPA bằng mô hình dữ liệu và quy tắc quan hệ của store đó.

### 2.5. Công cụ phát triển

Chuẩn bị:

- JDK phù hợp với phiên bản Spring Boot của dự án.
- Maven hoặc Gradle và hiểu dependency management.
- IDE có hỗ trợ Java và Spring.
- Một cơ sở dữ liệu phát triển như H2 hoặc database mà dự án sử dụng.
- curl, HTTPie hoặc Postman để gửi request và xem status code, header, body.
- Git để quản lý thay đổi.

Luôn chọn phiên bản Spring Boot và Spring Data tương thích theo dependency management của dự án. Không trộn các phiên bản Spring Data riêng lẻ một cách tùy tiện.

## 3. Luồng xử lý cần hình dung

Với một request đọc danh sách sách, luồng tổng quát như sau:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Spring MVC]
    B --> C[Spring Data REST]
    C --> D[Repository proxy]
    D --> E[Spring Data module]
    E --> F[Database]
    F --> E
    E --> D
    D --> C
    C --> G[HAL JSON response]
    G --> A
~~~

Spring Data REST nhận request, xác định repository resource tương ứng, gọi repository proxy và để module Spring Data làm việc với store. Kết quả được chuyển thành HTTP response theo cấu hình representation và hypermedia.

Điều quan trọng là repository vẫn là điểm truy cập dữ liệu. Nếu cần nghiệp vụ trước hoặc sau thao tác lưu, hãy đặt nghiệp vụ ở service hoặc dùng cơ chế event phù hợp; không nên nhồi toàn bộ quy tắc miền vào entity setter hay dựa vào việc client gọi đúng thứ tự endpoint.

## 4. Dựng ứng dụng Spring Data REST tối thiểu

Ví dụ dưới đây dùng Java 17+, Spring Boot, Spring Data JPA và H2. Các dependency được quản lý bởi Spring Boot parent hoặc BOM của dự án; hãy chọn một phiên bản Spring Boot tương thích với JDK và hệ sinh thái đang dùng.

### 4.1. Dependency Maven

Thêm các dependency sau vào phần dependencies của pom.xml:

~~~xml
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

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dùng một database khác, thay H2 bằng driver tương ứng và cấu hình datasource. Nếu dùng Spring Data module khác JPA, thay starter lưu trữ và mô hình entity cho phù hợp.

### 4.2. Lớp khởi động

Tạo file CatalogApplication.java trong package gốc của ứng dụng:

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

@SpringBootApplication bật cấu hình ứng dụng, auto-configuration và component scan từ package chứa class này trở xuống. Đặt entity và repository trong package con để chúng được phát hiện tự động.

### 4.3. Entity Book

Tạo file Book.java:

~~~java
package com.example.catalog;

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

@Id đánh dấu khóa chính. @GeneratedValue để database/provider sinh giá trị id. @Entity và @Table ánh xạ class với bảng. Constructor không tham số cho phép JPA khởi tạo entity; getter và setter giúp framework và ứng dụng truy cập thuộc tính.

Ví dụ dùng field access vì @Id được đặt trên field. Trong dự án thật, thống nhất cách truy cập field/property và thiết kế equals/hashCode cẩn thận, nhất là với entity có id được sinh tự động.

### 4.4. Repository được export

Tạo file BookRepository.java:

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(collectionResourceRel = "books", path = "books")
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
~~~

JpaRepository cung cấp các thao tác repository cho entity Book với kiểu khóa Long. @RepositoryRestResource đặt đường dẫn collection là books và relation name là books. Method tìm kiếm được công bố dưới search với path by-title; @Param đặt tên query parameter là q.

Với cấu hình này, Spring Data REST có thể công bố collection tại /books và search resource tại /books/search/by-title.

### 4.5. Cấu hình H2

Thêm vào src/main/resources/application.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

H2 chạy trong bộ nhớ nên dữ liệu được tạo lại khi ứng dụng khởi động. create-drop phù hợp cho ví dụ học tập; không dùng cấu hình này cho dữ liệu production. Trong môi trường thật, quản lý schema bằng công cụ migration như Flyway hoặc Liquibase và cấu hình thông tin kết nối qua biến môi trường hoặc secret manager.

### 4.6. Chạy ứng dụng và thử API

Tại thư mục dự án, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng:

~~~powershell
mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng khởi động, thử các request:

Đọc API root để xem các liên kết được công bố:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Đọc collection sách:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/books
~~~

Tạo một sách:

~~~cmd
curl -i -X POST http://localhost:8080/books ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/hal+json" ^
  -d "{\"title\":\"Spring in Action\",\"author\":\"Craig Walls\"}"
~~~

Lệnh POST gửi JSON đến collection. Khi tạo thành công, response thường có status 201 Created và header Location trỏ đến item resource vừa tạo. Cách viết dấu xuống dòng và escape dấu nháy trong lệnh curl phụ thuộc shell; nếu dùng Git Bash hoặc Linux/macOS, thay ký tự nối dòng ^ bằng dấu gạch chéo ngược.

Đọc một item theo URI nhận được từ Location hoặc liên kết self:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/books/1
~~~

Tìm theo tiêu đề:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/books/search/by-title?q=spring"
~~~

Phân trang và sắp xếp:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/books?page=0&size=10&sort=title,asc"
~~~

page thường bắt đầu từ 0. size là số phần tử tối đa trong một trang. sort có thể chỉ định thuộc tính và hướng asc hoặc desc. Hãy kiểm tra cấu hình phân trang của ứng dụng nếu muốn giới hạn page size tối đa.

Response collection HAL thường có _embedded.books chứa các item, _links chứa liên kết self và các liên kết liên quan, cùng thông tin page khi endpoint trả về dạng phân trang. URI và nội dung cụ thể phụ thuộc dữ liệu, cấu hình và phiên bản; hãy dùng liên kết server trả về làm nguồn tham chiếu.

## 5. Resource, HTTP method và HAL

Khi đọc API được export, hãy phân biệt các loại resource:

- **API root** tại / thường liệt kê những repository resource có thể truy cập.
- **Collection resource** tại /books đại diện cho tập hợp sách.
- **Item resource** tại /books/{id} đại diện cho một sách.
- **Search resource** tại /books/search chứa các query method được export.
- **Association resource** tại URI biểu diễn quan hệ giữa hai entity, ví dụ /books/{id}/publisher nếu entity có thuộc tính publisher được công bố.

Các thao tác thường gặp:

| Mục tiêu | Request thường dùng | Ý nghĩa |
|---|---|---|
| Đọc collection | GET /books | Lấy danh sách và metadata phân trang |
| Đọc item | GET /books/{id} | Lấy một resource |
| Tạo item | POST /books | Tạo resource trong collection |
| Cập nhật đầy đủ | PUT /books/{id} | Gửi representation theo hợp đồng PUT |
| Cập nhật một phần | PATCH /books/{id} | Chỉ gửi các trường cần thay đổi |
| Xóa item | DELETE /books/{id} | Xóa resource nếu được phép |
| Tìm kiếm | GET /books/search/by-title?q=... | Gọi query method được export |

Với association, Spring Data REST có thể dùng media type text/uri-list để client gửi URI của resource liên quan. Ví dụ, khi liên kết một sách với publisher, request đến association endpoint có thể chứa URI của publisher. DELETE trên association endpoint thường gỡ liên kết; điều đó không đồng nghĩa xóa entity publisher. Hãy đọc đúng semantics của endpoint trước khi thao tác dữ liệu quan hệ.

HAL giúp client đi theo liên kết do server cung cấp. Client nên đọc href từ _links thay vì tự ghép URI dựa trên id hoặc giả định đường dẫn luôn cố định. Điều này làm client ít phụ thuộc vào thay đổi cấu hình path và relation.

## 6. Tùy chỉnh endpoint và representation

### 6.1. Đổi tên hoặc ẩn repository

@RepositoryRestResource cho phép tùy chỉnh collection path, relation và trạng thái export. Ví dụ:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "catalogItems",
    path = "catalog-items"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

Khi repository không được phép xuất hiện qua REST, dùng exported = false:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Có thể dùng @RestResource(exported = false) trên method để ẩn một query method cụ thể. Ẩn endpoint là một phần của thiết kế API; vẫn cần cấu hình bảo mật phù hợp cho mọi endpoint còn lại.

### 6.2. Tùy chỉnh base path

Có thể đặt base path chung, ví dụ trong application.properties:

~~~properties
spring.data.rest.base-path=/api
~~~

Khi đó các repository resource được đặt dưới /api. Sau khi đổi base path, cập nhật tài liệu, cấu hình client, CORS và integration test tương ứng.

### 6.3. Query method

Spring Data suy ra truy vấn từ tên method trong repository. Các method như findByTitle, findByAuthorContainingIgnoreCase hoặc findByPublishedAtAfter có thể được công bố dưới search nếu được export.

Tên method dài có thể khó đọc và không phù hợp với truy vấn phức tạp. Khi đó cân nhắc @Query, custom repository implementation hoặc một service/controller riêng. Không nên biến mọi truy vấn nội bộ thành endpoint công khai.

### 6.4. Projection

Projection giới hạn các thuộc tính được hiển thị cho một representation. Ví dụ:

~~~java
package com.example.catalog;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = Book.class)
public interface BookSummary {
    String getTitle();
}
~~~

Projection này chỉ khai báo trường title. Khi projection được đăng ký và endpoint hỗ trợ, client có thể yêu cầu representation bằng query parameter projection=summary. Projection giúp điều chỉnh dữ liệu trả về, nhưng không thay thế kiểm soát truy cập: không đưa dữ liệu nhạy cảm vào projection công khai và không xem projection là cơ chế phân quyền.

### 6.5. Event handler và validation

Spring Data REST cung cấp các sự kiện quanh vòng đời repository, ví dụ trước/sau create, save, delete và cập nhật link. Có thể xử lý các sự kiện này bằng @RepositoryEventHandler và các annotation như @HandleBeforeCreate hoặc @HandleBeforeSave.

Dùng event handler cho những kiểm tra hoặc tác vụ gắn trực tiếp với thao tác repository. Với nghiệp vụ nhiều bước, cần transaction rõ ràng, gọi nhiều repository hoặc tích hợp hệ thống ngoài, service layer thường dễ kiểm soát hơn.

Validation cần được cấu hình và kiểm thử cho cả create lẫn update. Có thể dùng Jakarta Bean Validation như @NotBlank, @Size và @Email, kết hợp validator theo cơ chế validation event của Spring Data REST. Đừng chỉ dựa vào kiểm tra ở giao diện; request HTTP có thể được gửi trực tiếp.

### 6.6. Controller tùy chỉnh

Khi cần endpoint có payload hoặc hành vi đặc thù, có thể bổ sung controller. @RepositoryRestController được tích hợp với cơ chế base path và cấu hình của Spring Data REST; @RestController thông thường phù hợp với API MVC do ứng dụng tự quản lý.

Hãy chọn controller cho nghiệp vụ hoặc hợp đồng HTTP không phù hợp với thao tác repository tự động. Tránh tạo một endpoint tùy chỉnh trùng chức năng với endpoint repository mà không có lý do rõ ràng.

## 7. Bảo mật và thiết kế API

Tự động export repository có thể làm lộ dữ liệu hoặc thao tác ghi ngoài dự kiến nếu không thiết kế cẩn thận. Trước khi triển khai, hãy:

1. Liệt kê repository nào được phép export; ẩn repository nội bộ bằng exported = false.
2. Cấu hình Spring Security cho từng nhóm endpoint và từng thao tác đọc/ghi.
3. Áp dụng quyền theo người dùng và tài nguyên khi nghiệp vụ yêu cầu; xác thực thành công không đồng nghĩa người dùng được phép sửa mọi entity.
4. Không trả về mật khẩu, token, thông tin cá nhân hoặc thuộc tính nội bộ qua entity representation hay projection.
5. Kiểm tra các association có thể cho phép người dùng gắn entity vào quan hệ mà họ không có quyền quản lý.
6. Giới hạn CORS theo origin cần thiết. CORS không thay thế authentication hoặc authorization.
7. Dùng HTTPS và cấu hình secret bên ngoài source code.
8. Xem xét API compatibility, migration dữ liệu, logging và audit trước khi đưa vào production.

Một rủi ro thiết kế phổ biến là công bố trực tiếp persistence entity như hợp đồng API lâu dài. Khi schema database thay đổi, representation hoặc quan hệ cũng có thể thay đổi theo. Với hệ thống có nhiều client hoặc yêu cầu versioning, cân nhắc DTO và controller/service riêng để kiểm soát hợp đồng API.

## 8. Kiểm thử endpoint

Unit test cho repository giúp kiểm tra truy vấn và persistence, nhưng chưa đủ để xác nhận Spring Data REST đã export đúng endpoint. Nên có integration test khởi động application context và gọi HTTP endpoint qua MockMvc hoặc công cụ kiểm thử tương đương.

Ví dụ kiểm tra collection resource bằng MockMvc:

~~~java
package com.example.catalog;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exposesBooksCollectionAsHal() throws Exception {
        mockMvc.perform(get("/books")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Đây là integration test cho HTTP representation; cần dependency spring-boot-starter-test ở scope test. Test không phụ thuộc collection có sách hay chưa vì nó chỉ xác nhận endpoint và liên kết self. Có thể mở rộng để kiểm tra:

- POST tạo dữ liệu và trả status/header phù hợp.
- GET item trả đúng field và link.
- Query method có tên path và query parameter đúng.
- Phân trang, sắp xếp và giới hạn page size.
- PUT/PATCH không làm mất dữ liệu ngoài dự kiến.
- Thêm/gỡ association đúng quyền và đúng quan hệ.
- Repository hoặc field nhạy cảm không được export.
- Người chưa xác thực hoặc không đủ quyền nhận status phù hợp.
- Validation trả lỗi có thể hiểu được khi dữ liệu không hợp lệ.

Khi test HAL, kiểm tra cả dữ liệu và liên kết. Đừng chỉ kiểm tra JSON field rồi bỏ qua hợp đồng hypermedia.

## 9. Thứ tự học đề xuất

Học theo các bước sau để mỗi phần dựa trên kiến thức của phần trước:

1. **Java và HTTP/REST:** ôn interface, generic, annotation, JSON, HTTP method, status code, header và REST resource. Kết quả cần đạt: tự giải thích được request/response của một API CRUD.
2. **Spring Boot và Spring MVC:** tạo ứng dụng, cấu hình bean, chạy server, viết một controller GET/POST đơn giản. Kết quả cần đạt: biết request đi vào Spring như thế nào và cách đọc log khi endpoint lỗi.
3. **Spring Data:** tạo repository, query method, Page, Pageable và Sort. Kết quả cần đạt: truy vấn dữ liệu qua repository mà chưa cần REST export.
4. **JPA hoặc module lưu trữ đang dùng:** tạo entity, quan hệ, transaction và schema. Kết quả cần đạt: hiểu entity được lưu và tải như thế nào, đặc biệt là quan hệ lazy/cascade.
5. **Spring Data REST cơ bản:** thêm starter, export một repository, gọi API root, collection và item. Kết quả cần đạt: giải thích được endpoint nào được tạo từ repository nào.
6. **HAL và thao tác HTTP:** đọc _links, _embedded, phân trang, tạo/cập nhật/xóa và association. Kết quả cần đạt: viết được client thử API dựa trên link server trả về.
7. **Tùy chỉnh và bảo vệ API:** custom path/rel, search, projection, exported=false, validation, event handler, CORS và Spring Security. Kết quả cần đạt: chỉ công bố dữ liệu và thao tác mà ứng dụng thực sự cho phép.
8. **Integration test và vận hành:** kiểm tra HTTP contract, lỗi, quyền, migration, logging và tương thích client. Kết quả cần đạt: có thể đánh giá API trước khi triển khai.

Không nên nhảy thẳng đến projection hoặc event handler khi chưa hiểu repository và HAL. Nếu chưa hiểu association trong JPA, endpoint liên kết sẽ rất khó kiểm tra an toàn.

## 10. Bài tập thực hành theo từng mức

Dùng cùng ứng dụng Book để tránh phải thay đổi ngữ cảnh liên tục:

- **Mức 1:** export BookRepository và dùng GET đọc collection, item.
- **Mức 2:** tạo ba sách bằng POST; kiểm tra status code, Location và HAL links.
- **Mức 3:** thêm tìm kiếm theo title; thử kết quả có và không có dữ liệu.
- **Mức 4:** thử page, size và sort; xác nhận page bắt đầu từ 0 và thứ tự sắp xếp.
- **Mức 5:** tạo Publisher và quan hệ Book–Publisher; thử đọc, gắn và gỡ association.
- **Mức 6:** tạo projection chỉ trả title; xác nhận field khác không xuất hiện trong representation đó.
- **Mức 7:** ẩn một repository nội bộ và bảo vệ thao tác ghi bằng Spring Security.
- **Mức 8:** viết integration test cho create, read, update, delete, search, association và authorization.

Sau mỗi bài tập, kiểm tra response thực tế bằng curl hoặc Postman, đọc log ứng dụng và viết test để giữ hành vi mong muốn.

## 11. Lỗi thường gặp và cách tránh

- **Thêm Spring Data JPA nhưng quên Spring Data REST:** repository vẫn hoạt động trong Java nhưng endpoint REST tự động không xuất hiện. Kiểm tra starter và auto-configuration.
- **Đặt repository ngoài package scan:** Spring không phát hiện repository. Đặt class khởi động ở package gốc hoặc cấu hình scan rõ ràng.
- **Nhầm tên endpoint:** path và relation có thể chịu ảnh hưởng của tên domain, annotation và cấu hình. Xem API root và HAL links để xác định URI thực tế.
- **Dùng query parameter sai tên:** tên trong URL phải khớp @Param hoặc tên được Spring Data suy ra. Kiểm tra method đã được export chưa.
- **Serialize quan hệ lazy ngoài transaction:** response có thể phát sinh truy vấn bổ sung hoặc lỗi khi truy cập proxy đã đóng. Thiết kế representation, fetch plan và transaction có chủ đích.
- **Export toàn bộ repository:** client có thể thấy dữ liệu hoặc thao tác không dự kiến. Chỉ export những gì là hợp đồng API và kiểm thử quyền truy cập.
- **Hiểu sai DELETE association:** thao tác có thể chỉ gỡ liên kết chứ không xóa entity ở đầu kia. Kiểm tra endpoint và trạng thái database sau thao tác.
- **Coi projection là bảo mật:** projection chỉ điều chỉnh representation. Authorization vẫn phải được thực hiện ở tầng bảo mật và nghiệp vụ.
- **Đưa quy tắc nghiệp vụ phức tạp vào event handler:** luồng nhiều bước khó đọc và khó kiểm soát transaction. Chuyển nghiệp vụ sang service phù hợp.
- **Chỉ kiểm thử repository:** repository test không chứng minh URI, HAL, status code, header và authorization đúng. Bổ sung integration test HTTP.

## 12. Checklist trước khi dùng trong dự án

- [ ] Đã hiểu Java generic, annotation và interface.
- [ ] Đã hiểu HTTP method, status code, JSON và REST resource.
- [ ] Đã biết cấu hình và chạy ứng dụng Spring Boot.
- [ ] Đã dùng repository và query method của Spring Data.
- [ ] Đã hiểu entity, transaction và quan hệ của persistence store đang dùng.
- [ ] Đã đọc được HAL _links và _embedded.
- [ ] Đã xác định repository nào được phép export.
- [ ] Đã kiểm soát quyền đọc, ghi và cập nhật association.
- [ ] Đã kiểm tra validation, projection và dữ liệu nhạy cảm.
- [ ] Đã có integration test cho HTTP contract và security.

Spring Data REST phát huy hiệu quả khi mô hình repository phù hợp với resource API mà client cần. Hãy bắt đầu bằng một repository nhỏ, quan sát HAL response, sau đó mới mở rộng sang quan hệ, projection, validation và bảo mật.