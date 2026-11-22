# REST, HATEOAS và khả năng khám phá API qua liên kết

REST mô tả một phong cách kiến trúc để các hệ thống trao đổi thông tin thông qua tài nguyên và biểu diễn của tài nguyên. HATEOAS bổ sung nguyên tắc rằng phản hồi của API mang theo các liên kết chỉ ra client có thể đi tới tài nguyên hoặc thao tác tiếp theo bằng cách nào. Nhờ vậy, client khám phá API từ một điểm vào đã biết thay vì tự ghép mọi URL theo quy ước nội bộ của server.

Spring Data REST áp dụng cách tiếp cận này bằng cách xuất các Spring Data repository thành REST resource và mặc định biểu diễn chúng bằng HAL (Hypertext Application Language).

## 1. REST nhìn API như một tập hợp tài nguyên

Một **resource** là khái niệm mà hệ thống muốn cung cấp cho client, chẳng hạn sách, đơn hàng hoặc khách hàng. URI định danh tài nguyên; representation là dữ liệu mô tả trạng thái tài nguyên tại một thời điểm.

Ví dụ:

- **/books** định danh tập hợp sách.
- **/books/42** định danh một cuốn sách.
- **/orders/91** định danh một đơn hàng.

URI không nhất thiết phản ánh tên bảng hoặc cấu trúc database. Server có thể thay đổi cách lưu trữ mà vẫn giữ hợp đồng tài nguyên cho client.

REST là một **architectural style**, không đồng nghĩa với việc tạo một endpoint cho mỗi thao tác CRUD. REST đầy đủ được xây dựng từ các ràng buộc kiến trúc:

1. **Client–server:** giao diện client và phần xử lý/lưu trữ phía server có thể phát triển độc lập qua một hợp đồng trao đổi rõ ràng.
2. **Stateless:** mỗi request chứa đủ thông tin để server xử lý; server không dựa vào trạng thái phiên hội thoại ngầm được giữ giữa các request.
3. **Cacheable:** response cho biết dữ liệu có thể được cache hay không và trong điều kiện nào.
4. **Uniform interface:** các thành phần tương tác qua một giao diện thống nhất. Ràng buộc này gồm định danh tài nguyên, thao tác trên representation, thông điệp tự mô tả và hypermedia.
5. **Layered system:** client không cần biết request đi qua proxy, gateway hay lớp trung gian nào.
6. **Code on demand (tùy chọn):** server có thể gửi mã thực thi cho client, nhưng REST không bắt buộc dùng khả năng này.

HTTP thường được dùng để triển khai REST API. Một số quy ước HTTP quan trọng:

| Method | Ý nghĩa thường dùng | Safe | Idempotent |
|---|---|---:|---:|
| GET | Đọc representation | Có | Có |
| HEAD | Đọc metadata của response | Có | Có |
| POST | Tạo tài nguyên hoặc gửi yêu cầu xử lý | Không | Không được bảo đảm |
| PUT | Thay thế trạng thái tài nguyên đích | Không | Có |
| PATCH | Cập nhật một phần tài nguyên | Không | Không được bảo đảm |
| DELETE | Xóa tài nguyên đích | Không | Có về hiệu ứng dự kiến |

**Safe** nghĩa là request được thiết kế để không yêu cầu thay đổi trạng thái tài nguyên. **Idempotent** nghĩa là gửi cùng một request nhiều lần có cùng hiệu ứng dự kiến như gửi một lần; response HTTP giữa các lần gọi vẫn có thể khác nhau.

REST cũng dùng status code để mô tả kết quả: 200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found và 405 Method Not Allowed là những mã thường gặp. Status cụ thể phụ thuộc endpoint và cấu hình framework.

## 2. HATEOAS: để response chỉ đường cho client

HATEOAS là viết tắt của **Hypermedia as the Engine of Application State**. Client nhận được các liên kết trong representation và dùng chúng để khám phá những bước tiếp theo mà server đang cung cấp.

Một link thường có hai phần quan trọng:

- **href:** URI mà client có thể truy cập.
- **rel (relation):** ý nghĩa của liên kết, ví dụ **self**, **next**, **search**, **profile** hoặc một relation do ứng dụng định nghĩa.

Ví dụ response:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/42"
    },
    "author": {
      "href": "http://localhost:8080/api/books/42/author"
    }
  }
}
~~~

Client hiểu rằng response mô tả một cuốn sách và có liên kết mang relation **author**. Client không cần tự đoán endpoint của tác giả bằng cách ghép chuỗi từ ID hoặc tên class.

Một luồng khám phá API điển hình:

1. Client biết URL điểm vào của API, ví dụ **http://localhost:8080/api**.
2. Client gửi GET tới điểm vào và đọc các link trong response.
3. Client tìm link có relation phù hợp, chẳng hạn **books**, rồi truy cập URI trong **href**.
4. Từ collection, client đọc link tới từng item, link phân trang hoặc link **search**.
5. Từ item, client tiếp tục theo các link quan hệ như **author**, **publisher** hoặc thao tác mà server công bố.

Trong hệ thống hypermedia, các link có thể phản ánh trạng thái hiện tại. Ví dụ, đơn hàng chưa thanh toán có thể có link thanh toán; sau khi thanh toán, link đó có thể biến mất và một link khác xuất hiện. Client dựa vào hành động được công bố trong response để quyết định bước tiếp theo.

Client vẫn cần hiểu ý nghĩa của relation và media type. HATEOAS không loại bỏ hoàn toàn kiến thức nghiệp vụ phía client; nó giảm sự phụ thuộc vào cấu trúc URL và cho phép server điều khiển các đường đi hợp lệ qua hypermedia.

## 3. HAL biểu diễn link trong JSON

**HAL** là định dạng hypermedia phổ biến cho JSON. Spring Data REST mặc định dùng HAL để biểu diễn resource.

Các trường thường gặp:

- **_links:** các liên kết của resource hiện tại. Tên thuộc tính thường là relation; giá trị chứa **href** và có thể có thêm metadata.
- **_embedded:** các resource được nhúng trực tiếp trong representation, thường dùng cho phần tử của collection.
- **templated:** cho biết **href** là URI template có biến cần điền, chẳng hạn page, size hoặc q.
- **page:** metadata phân trang trong response collection của Spring Data REST.

Media type thường thấy là **application/hal+json**. Client có thể gửi header **Accept: application/hal+json** để yêu cầu representation HAL tường minh.

### Ví dụ resource gốc

Giả sử ứng dụng có repository cho sách. GET tới điểm vào có thể trả về link như sau:

~~~json
{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    }
  }
}
~~~

Relation **books** dẫn tới collection sách. Một số cấu hình còn cung cấp link metadata/profile. Client nên theo link thực tế trong response thay vì giả định endpoint metadata.

### Ví dụ collection resource

~~~json
{
  "_embedded": {
    "books": [
      {
        "title": "Spring in Action",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books{?page,size,sort}",
      "templated": true
    },
    "search": {
      "href": "http://localhost:8080/api/books/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Đây là representation minh họa. Host, URI, relation và metadata thực tế có thể khác theo cấu hình. Client nên đọc **href** từ response. Link **self** có URI template vì collection hỗ trợ tham số phân trang và sắp xếp.

### Ví dụ item resource

~~~json
{
  "title": "Spring in Action",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    }
  }
}
~~~

Nếu domain object có association, Spring Data REST có thể công bố link mang tên property association. Client theo link đó để đọc hoặc thao tác với association thay vì tự dựng đường dẫn.

**Phân biệt link và embedded resource:** link chỉ vị trí để truy cập resource; embedded resource đưa representation của resource vào response hiện tại. Nhúng dữ liệu có thể giảm số request, còn link giữ khả năng điều hướng và lấy dữ liệu độc lập.

## 4. Spring Data REST biến repository thành REST resource

Spring Data REST xuất các Spring Data repository thành HTTP resource. Với repository quản lý entity **Book**, framework thường tạo:

- **Collection resource**, ví dụ **/books**.
- **Item resource** cho từng bản ghi, ví dụ **/books/1**.
- **Search resource** nếu repository có query method được xuất.
- **Association resource** cho các quan hệ của entity.

Tên collection mặc định được suy ra từ tên domain class theo quy tắc của Spring Data REST. Có thể tùy chỉnh path và relation bằng **@RepositoryRestResource**.

Các thao tác HTTP thường được ánh xạ từ repository:

- Collection: GET để đọc danh sách, POST để tạo phần tử.
- Item: GET để đọc, PUT để thay thế, PATCH để cập nhật một phần và DELETE để xóa.
- Association: link cho phép client truy cập quan hệ giữa các resource.
- Search: GET tới search resource để khám phá query method được công bố.

Method không tồn tại hoặc bị đánh dấu **exported = false** sẽ không được xuất tương ứng. Không nên giả định mọi repository đều có đủ mọi HTTP method.

### Khám phá query method

Spring Data REST cung cấp search resource cho các query method được xuất. Client GET vào link **search** để lấy danh sách link tới từng truy vấn. Link truy vấn có thể là URI template chứa tham số cần truyền.

Ví dụ, repository khai báo phương thức tìm sách theo tiêu đề. Client khám phá relation **by-title** từ search resource, sau đó gọi link với tham số **q**. Cách này giúp client tìm được chức năng tìm kiếm từ hypermedia mà không cần biết trước toàn bộ URL.

### Association resource

Giả sử **Book** có property **author**. Spring Data REST có thể cung cấp link relation **author** trong item resource. Client theo link để đọc association. Việc liên kết hoặc gỡ liên kết được thực hiện theo HTTP method và media type mà association resource hỗ trợ; một số thao tác liên kết dùng **text/uri-list**.

Tên và đường dẫn association có thể tùy chỉnh bằng **@RestResource** trên property. Chỉ công bố những quan hệ mà client thực sự cần sử dụng.

## 5. Ví dụ Spring Data REST với Java 17+

Ví dụ sau tạo API quản lý sách. Spring Data REST tự xuất repository thành resource; không cần viết controller CRUD riêng.

### Dependencies

Trong dự án Spring Boot 3.x dùng Java 17+, thêm dependency sau và để Spring Boot dependency management quản lý phiên bản tương thích:

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
</dependencies>
~~~

### Entity Book

Tệp **src/main/java/com/example/library/Book.java**:

~~~java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
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
}
~~~

Entity có constructor không tham số để JPA khởi tạo object. ID được database sinh tự động. Representation REST không nhất thiết phải đưa ID thành field JSON vì client có thể dùng link **self**.

### Repository

Tệp **src/main/java/com/example/library/BookRepository.java**:

~~~java
package com.example.library;

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
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
~~~

**JpaRepository** cung cấp các thao tác lưu trữ. **@RepositoryRestResource** đặt path và relation cho collection. Query method được xuất thành search resource; **@RestResource** đặt path và relation dễ hiểu cho client. **@Param("q")** xác định tên tham số truy vấn.

### Application

Tệp **src/main/java/com/example/library/LibraryApplication.java**:

~~~java
package com.example.library;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LibraryApplication {

    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(BookRepository books) {
        return args -> books.saveAll(List.of(
            new Book("Spring in Action"),
            new Book("Effective Java")
        ));
    }
}
~~~

### Cấu hình

Tệp **src/main/resources/application.properties**:

~~~properties
spring.datasource.url=jdbc:h2:mem:library
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
~~~

Cấu hình base path khiến điểm vào của Spring Data REST nằm tại **/api**. H2 chạy trong bộ nhớ để ví dụ khởi động mà không cần cài database riêng.

### Chạy ứng dụng

Trong thư mục dự án, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
mvnw.cmd spring-boot:run
~~~

Ví dụ giả định Maven wrapper và dependency đã được cấu hình trong dự án Spring Boot. Khi ứng dụng chạy, repository được xuất dưới base path **/api**.

## 6. Thực hành khám phá API bằng HTTP

Các lệnh dưới đây minh họa request có thể thực hiện. Trong client hypermedia thực tế, hãy lấy URL từ link của response trước đó thay vì tự ghép đường dẫn.

### Bước 1: đọc điểm vào

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Đọc relation **books** trong **_links**, rồi dùng giá trị **href** để truy cập collection.

### Bước 2: đọc collection

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/books
~~~

Response chứa phần tử trong **_embedded.books**, link **self**, link **search** và metadata phân trang. Nếu có nhiều trang, client theo link phân trang được trả về thay vì tự tính URL tiếp theo.

### Bước 3: khám phá chức năng tìm kiếm

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/books/search
~~~

Search resource liệt kê link của query method. Với ví dụ trên, relation **by-title** dẫn tới endpoint tìm sách theo tiêu đề. URI template có thể chứa biến **q**.

Có thể gọi truy vấn bằng URL tương ứng:

~~~bash
curl -H "Accept: application/hal+json" "http://localhost:8080/api/books/search/by-title?q=spring"
~~~

Trong ứng dụng hypermedia, client lấy link **by-title** từ response search resource và điền giá trị q vào URI template.

### Bước 4: tạo một resource

~~~bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"title":"Designing Data-Intensive Applications"}' http://localhost:8080/api/books
~~~

Collection resource nhận POST để tạo sách. Response thường có status 201 Created; tùy header và cấu hình, response có thể chứa representation hoặc cung cấp URI mới qua header Location. Client dùng URI/link server trả về để đọc resource vừa tạo.

## 7. Thiết kế client để thật sự dùng HATEOAS

Một client hypermedia nên:

1. Chỉ cấu hình điểm vào và media type mà API hỗ trợ.
2. Đọc link theo relation có ý nghĩa nghiệp vụ.
3. Truy cập URI trong **href**; không nối chuỗi từ tên resource, ID hoặc quy tắc pluralization.
4. Nhận biết URI template và điền đúng biến được công bố.
5. Theo link phân trang do server cung cấp.
6. Xử lý relation có thể không xuất hiện khi thao tác không khả dụng.
7. Xử lý status code, lỗi mạng và thay đổi representation theo hợp đồng media type.

Ví dụ, nếu client cần xem tác giả của một cuốn sách, client tìm relation **author** trong representation của sách và gọi URI tương ứng. Client không nên mặc định endpoint luôn có dạng **/books/{id}/author**, vì server có thể thay đổi path mà vẫn giữ relation.

Relation là một phần của hợp đồng API. Hãy chọn tên có ý nghĩa và duy trì ngữ nghĩa ổn định. Nếu relation thay đổi ý nghĩa, client có thể hiểu sai hành động dù URI vẫn truy cập được.

## 8. Bảo mật và kiểm soát phạm vi xuất repository

Tự động xuất repository giúp giảm mã CRUD, nhưng cần xem xét kỹ repository nào được công khai. Không nên mặc định mọi repository trong ứng dụng đều phù hợp để trở thành API.

Một số cách kiểm soát:

- Dùng Spring Security để xác thực và phân quyền ở server. Việc ẩn một link không thay thế kiểm tra quyền trên endpoint.
- Dùng **@RepositoryRestResource(exported = false)** để không xuất repository không dành cho client.
- Dùng **@RestResource(exported = false)** cho method hoặc association không nên công bố.
- Dùng projection hoặc DTO khi cần giới hạn field được trả về.
- Kiểm tra validation, xử lý lỗi và quyền truy cập cho cả thao tác đọc lẫn ghi.
- Không để client sửa trực tiếp field nội bộ chỉ vì entity có setter.

Nếu nghiệp vụ có quy trình nhiều bước, kiểm tra điều kiện phức tạp hoặc cần orchestration riêng, hãy cân nhắc custom controller và Spring HATEOAS. Khi đó có thể dùng **EntityModel**, **CollectionModel** và API tạo link để thiết kế representation có hypermedia.

## 9. Những nhầm lẫn thường gặp

**Nhầm HATEOAS với việc thêm object _links.** Có field **_links** chưa đủ. Client cần thực sự dùng relation để khám phá bước tiếp theo.

**Nhầm HAL với HATEOAS.** HATEOAS là ràng buộc kiến trúc; HAL là định dạng biểu diễn hypermedia. Có thể triển khai hypermedia bằng định dạng khác.

**Hard-code mọi URL.** Khi client tự dựng đường dẫn từ ID hoặc tên entity, nó phụ thuộc vào cấu trúc URL và không tận dụng khả năng khám phá.

**Cho rằng mọi repository method đều tự động xuất.** Việc xuất phụ thuộc kiểu repository, method có sẵn, cấu hình và thuộc tính **exported**.

**Cho rằng thiếu link đồng nghĩa với được bảo vệ.** Quyền truy cập luôn phải được kiểm tra ở server. Client không thể dùng việc link không xuất hiện làm cơ chế bảo mật.

**Nhầm embedded data với link.** Embedded data là representation được đưa vào response hiện tại; link là chỉ dẫn để truy cập resource.

**Bỏ qua URI template và pagination.** Client cần đọc biến template và theo link phân trang, không giả định collection luôn nằm trên một response duy nhất.

**Cho rằng Spring Data REST phù hợp với mọi API.** Nó phù hợp khi resource và repository mapping phản ánh tốt nghiệp vụ. API có workflow đặc thù có thể cần endpoint và representation được thiết kế riêng.

## 10. Checklist khi thiết kế hoặc sử dụng API hypermedia

- [ ] Có một điểm vào rõ ràng cho client.
- [ ] Mỗi resource có relation và link phù hợp.
- [ ] Client theo **href** từ response thay vì tự ghép URL.
- [ ] Relation có tên và ý nghĩa ổn định.
- [ ] URI template, phân trang và search link được xử lý đúng.
- [ ] Media type và cấu trúc representation được thống nhất.
- [ ] HTTP method và status code phản ánh đúng kết quả.
- [ ] Repository, method và field được xuất có chủ đích.
- [ ] Authentication và authorization được kiểm tra ở server.
- [ ] Integration test kiểm tra cả dữ liệu lẫn link điều hướng.

## 11. Kết luận

REST tổ chức API quanh tài nguyên và representation. HATEOAS đưa liên kết điều hướng vào representation để client khám phá tài nguyên và hành động tiếp theo. HAL biểu diễn các link đó trong JSON thông qua **_links** và **_embedded**. Spring Data REST kết hợp các ý tưởng này bằng cách xuất Spring Data repository thành collection, item, search và association resource.

Khi sử dụng Spring Data REST, hãy bắt đầu từ resource gốc, theo relation tới collection, item và search resource, rồi tiếp tục theo link server cung cấp. Client càng dựa vào relation và media type của API, nó càng ít phụ thuộc vào chi tiết URL nội bộ.

## Tài liệu tham khảo

- [Spring Data REST Reference — Introduction](https://docs.spring.io/spring-data/rest/reference/intro.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot Reference — Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring HATEOAS API — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
