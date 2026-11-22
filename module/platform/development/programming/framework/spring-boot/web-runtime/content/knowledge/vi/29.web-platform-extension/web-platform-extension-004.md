# Hỗ trợ Spring HATEOAS và liên kết tài nguyên trong phản hồi

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Mở rộng nền tảng web

## 1. HATEOAS giải quyết vấn đề gì?

Một REST API có endpoint **GET /api/books/1** trả JSON mô tả sách:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true
}
~~~

Client muốn xem tình trạng còn sách hoặc trở lại danh mục phải biết trước các đường dẫn như **/api/books/1/availability** và **/api/books**. Nếu server đổi route hoặc tổ chức tài nguyên, client đã hardcode URL dễ bị lỗi.

**HATEOAS** (*Hypermedia as the Engine of Application State*) là ràng buộc kiến trúc REST: representation từ server có **hypermedia controls**, ví dụ **links có quan hệ/rel rõ ràng**, để client khám phá các tài nguyên liên quan và những bước tiếp theo. Server không chỉ trả dữ liệu; nó còn chỉ ra đường điều hướng hợp lệ theo hợp đồng API.

Một response dạng **HAL JSON** có thể trông như sau:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    },
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "availability": {
      "href": "http://localhost:8080/api/books/1/availability"
    }
  }
}
~~~

**self** dẫn tới chính cuốn sách; **books** dẫn tới collection; **availability** là relation riêng của nghiệp vụ. Một client hiểu các relation này có thể theo **_links.availability.href** thay vì tự nối chuỗi URL. Client vẫn cần biết **entry point**, media type và semantics các rel; HATEOAS làm giảm coupling về đường dẫn, không loại bỏ mọi hợp đồng.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **resource**, **representation**, **link**, **link relation**, **HAL**, **affordance** và entry point.
2. Giải thích Spring Boot 3.x auto-configure **spring-boot-starter-hateoas** trên **Servlet Spring MVC** như thế nào.
3. Dùng **Link**, **RepresentationModel**, **EntityModel**, **CollectionModel**, **PagedModel** và **RepresentationModelAssembler** đúng phạm vi.
4. Tạo links từ mappings Spring MVC bằng **WebMvcLinkBuilder.linkTo(...)** và **methodOn(...)**, không tự ghép URL.
5. Chạy demo Java 17+ có GET item, collection, sub-resource, links theo trạng thái và HTTP 404.
6. Kiểm chứng **application/hal+json**, **_links**, **_embedded**, relation names và href bằng curl/JUnit.
7. Xử lý links sau reverse proxy với **server.forward-headers-strategy**, HTTPS và trusted Forwarded headers.
8. Hiểu ranh giới với authorization, pagination, WebFlux, Spring Data REST, HTTP cache và OpenAPI.

## 2. Resource, representation và relation không phải một thứ

**Resource** là một khái niệm được định danh bởi URI, ví dụ cuốn sách 1 hay danh mục sách. **Representation** là cách resource được mô tả trong HTTP response, ví dụ JSON hoặc HAL JSON. **Link** chứa href (đích) và rel (quan hệ). **Rel** nói link đó có nghĩa gì đối với representation.

Một số quan hệ:

| Rel | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **self** | Đường tới resource hiện tại | Thường có cho item/collection có URI ổn định. |
| **books** | Đường tới danh mục sách | Relation domain được API quy định. |
| **availability** | Đường tới trạng thái còn sách | Có thể hiện theo trạng thái trong representation. |
| **next**, **prev** | Phân trang tiến/lùi | Chỉ nên có khi còn trang phù hợp. |
| **first**, **last** | Trang đầu/cuối | Phụ thuộc pagination policy. |
| **profile** | Schema/semantic profile | Không thay authorization hoặc OpenAPI. |
| **search** | Điểm tìm kiếm hoặc URI Template | Client phải hiểu query variables. |

Relation **self/next/prev** thuộc các rel thông dụng; relation riêng như **books** hay **availability** phải được tài liệu hóa hoặc dùng URI/CURIE nếu cần namespace ổn định. Không nên thay nghĩa rel sau khi client đã phụ thuộc vào nó.

**Link không phải quyền truy cập.** Có link trong JSON không chứng minh người dùng có quyền thực hiện request. Nếu server bỏ link vì sách chưa available, URL vẫn có thể tồn tại và một người khác vẫn có thể tự gõ nó. Authentication/authorization bắt buộc được kiểm ở endpoint thực.

Một representation có thể chứa các controls khác nhau tùy state, permission hoặc workflow. Đó là điểm quan trọng hơn việc thêm một thuộc tính URL vô nghĩa vào JSON.

## 3. HAL JSON và media type

**HAL** (*Hypertext Application Language*) là một định dạng hypermedia đơn giản, có media type **application/hal+json**. Nó dùng các key đặc biệt:

- **_links**: map rel → object/array link chứa **href**, đôi khi **templated**, **title**, **type** hoặc metadata khác.
- **_embedded**: map rel → những resource representations nhúng trong response.
- Những field còn lại: dữ liệu domain/representation thông thường.

Ví dụ một item:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books/1"
    },
    "books": {
      "href": "https://api.example.test/api/books"
    }
  }
}
~~~

Ví dụ collection có hai books:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/1"
          }
        }
      },
      {
        "id": 2,
        "title": "Designing Web APIs",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/2"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books"
    }
  }
}
~~~

Không phải mọi response bắt buộc có **_embedded**. Collection rỗng có thể được biểu diễn khác nhau tùy fallback type và HAL converter. Một relation có thể có nhiều link được biểu diễn bằng array. Client phải phân biệt single/multiple links theo hợp đồng.

**HAL khác JSON thuần ở media type và cách biểu diễn hypermedia**. Nó không phải giao thức truyền riêng: status, headers, caching, TLS, authentication và HTTP methods vẫn là HTTP thông thường.

### URI Templates

Một link có query parameters có thể được mô tả bằng URI Template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/books{?q,page,size}",
      "templated": true
    }
  }
}
~~~

Đây là **template**, chưa phải URL cụ thể để gửi nguyên xi. Client cần hiểu RFC 6570 hoặc thư viện HAL để expand **q/page/size** và URL-encode đúng. Templated link không tự tạo @GetMapping search endpoint; server vẫn phải implement nó.

## 4. Spring HATEOAS có những API nào?

Spring HATEOAS bổ sung model, link builder và hỗ trợ serialize hypermedia cho Spring Framework. Những lớp quan trọng:

| Class / interface | Chức năng | Dùng khi |
| --- | --- | --- |
| **Link** | Href + rel và metadata | Tạo self/collection/related links. |
| **RepresentationModel<T>** | Model cơ sở có tập links | Tự tạo representation type hoặc wrapper. |
| **EntityModel<T>** | Bọc một object T với links | Trả một resource. |
| **CollectionModel<T>** | Bọc nhiều items với links của collection | Trả collection. |
| **PagedModel<T>** | Collection + PageMetadata | Trả trang dữ liệu. |
| **RepresentationModelAssembler<T,D>** | Chuyển DTO/domain T thành representation D | Tập trung link building và điều kiện. |
| **WebMvcLinkBuilder** | Tạo URI từ Spring MVC mappings | Không phải hardcode host/path. |
| **@Relation** | Quy định item/collection relation | Kiểm tên _embedded. |
| **LinkDiscoverers** | Tìm link theo rel trong hypermedia representations | Thường hỗ trợ phía client. |
| **Affordance** | Mô tả hành động khả dụng (method, input, v.v.) | Khi cần workflow/action semantics. |

**Spring HATEOAS không tự tạo CRUD API**, không quản lý database, không tự xác thực user và không tự biến mọi POJO thành HAL model có liên kết. Controller và assembler quyết định links được đưa vào response.

Các tên API ở blog cũ có thể khác: **ResourceSupport → RepresentationModel**, **Resource → EntityModel**, **Resources → CollectionModel**, **PagedResources → PagedModel**, **ResourceAssembler → RepresentationModelAssembler**, **ControllerLinkBuilder → WebMvcLinkBuilder**. Dùng API phù hợp Spring Boot 3.x thay vì copy snippet Boot 1.x.

## 5. Spring Boot 3.3 auto-configuration và dependency

Spring Boot cung cấp **spring-boot-starter-hateoas** chuyên dùng cho ứng dụng **Spring MVC (Servlet)**. Khi auto-configuration hoạt động, Boot chuẩn bị HAL support, Jackson **ObjectMapper** và các beans như **LinkDiscoverers**; bạn **không cần tự đặt @EnableHypermediaSupport** chỉ để bật starter.

Theo tài liệu Spring Boot 3.3:

- **spring-boot-starter-hateoas** dành cho MVC; **không kết hợp nó với Spring WebFlux** trong một reactive application. Với WebFlux, thêm **org.springframework.hateoas:spring-hateoas** trực tiếp cùng starter WebFlux.
- Mặc định, request **Accept: application/json** có thể nhận **application/hal+json** khi HAL là JSON mapping mặc định.
- Property **spring.hateoas.use-hal-as-default-json-media-type=false** đổi cách xử lý HAL-as-default-JSON; cần kiểm cả Accept application/json và Accept application/hal+json sau khi đổi.
- Nếu dùng **@EnableHypermediaSupport** để tự điều khiển cấu hình, có thể vô hiệu hóa phần Jackson customization do Boot cung cấp; tránh thêm nó nếu chưa cần.

Không coi auto-config là bảo đảm rằng mọi endpoint của app sẽ có **_links**. Nếu controller trả một DTO thuần và không xây EntityModel/links, app không thể tự biết relation domain để thêm.

### Dependencies của demo

Bài dùng **Spring Boot 3.3.13**, **Java 17+**, Maven và embedded Tomcat cho demo có thể tái hiện. Đây là ví dụ nhất quán với nhánh Boot 3.3; môi trường production mới nên chọn bản Boot đang được hỗ trợ và nhận đủ bản vá bảo mật.

Cấu trúc:

~~~text
hateoas-books-demo/
  pom.xml
  src/main/java/com/example/hateoas/
    HateoasBooksApplication.java
    BookDto.java
    AvailabilityDto.java
    BookModelAssembler.java
    BookController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/hateoas/
    BookHateoasIntegrationTests.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>hateoas-books-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-hateoas</artifactId>
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

Starter HATEOAS mang các dependencies hỗ trợ MVC/HAL; việc khai báo cả starter-web ở demo giúp mô hình Servlet rõ ràng. Không cần **spring-boot-starter-data-rest** nếu chỉ muốn viết REST controllers với liên kết do chính mình kiểm soát.

**src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=hateoas-books-demo

# Spring Boot 3.3 mac dinh dung HAL nhu JSON hypermedia.
# Khong can @EnableHypermediaSupport trong demo.
# spring.hateoas.use-hal-as-default-json-media-type=true
~~~

## 6. DTO: tách representation khỏi persistence model

Tạo **src/main/java/com/example/hateoas/BookDto.java**:

~~~java
package com.example.hateoas;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "book", collectionRelation = "books")
public record BookDto(long id, String title,
                      String author, boolean available) {
}
~~~

**@Relation** quy định item relation **book** và collection relation **books**, giúp HAL converter đặt collection dưới **_embedded.books** thay vì một tên mặc định suy theo class.

Tạo **src/main/java/com/example/hateoas/AvailabilityDto.java**:

~~~java
package com.example.hateoas;

public record AvailabilityDto(long bookId, boolean available) {
}
~~~

Các **record** hợp lệ với Java 17 và Jackson/Spring Boot 3. Dữ liệu domain nên đi qua DTO thay vì expose toàn bộ JPA entity, vì persistence model có thể chứa internal IDs, attributes riêng, lazy relations hoặc secrets không được phép đưa vào response.

**AvailabilityDto** không cần tự extends RepresentationModel. Ta sẽ bọc nó bằng **EntityModel<AvailabilityDto>** để thêm self và link quay lại sách.

## 7. RepresentationModelAssembler: trung tâm xây liên kết

Tạo **src/main/java/com/example/hateoas/BookModelAssembler.java**:

~~~java
package com.example.hateoas;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class BookModelAssembler
        implements RepresentationModelAssembler<
                BookDto, EntityModel<BookDto>> {

    @Override
    public EntityModel<BookDto> toModel(BookDto book) {
        EntityModel<BookDto> model = EntityModel.of(
                book,
                linkTo(methodOn(BookController.class)
                        .one(book.id())).withSelfRel(),
                linkTo(methodOn(BookController.class)
                        .all()).withRel("books")
        );

        if (book.available()) {
            model.add(linkTo(methodOn(BookController.class)
                    .availability(book.id())).withRel("availability"));
        }

        return model;
    }
}
~~~

Cách hoạt động:

- **RepresentationModelAssembler<T,D>** tách nhiệm vụ chuyển DTO thành hypermedia representation khỏi controller.
- **EntityModel.of(book, ...)** bọc dữ liệu và links.
- **linkTo(methodOn(BookController.class).one(book.id()))** tạo link theo Spring MVC mapping thực; **methodOn** là dummy invocation, không gọi controller business method để truy vấn dữ liệu.
- **withSelfRel()** đặt relation chuẩn self; **withRel("books")** đặt relation domain tới danh mục.
- Sách available có relation **availability** theo chính sách trình bày; sách không available thì relation ấy vắng mặt. Đó là sự biến đổi representation theo state, không phải logic ngăn người dùng tự gọi URL.
- Khi route đổi trong @RequestMapping/@GetMapping, link builder có thể tạo URL mới từ mapping, giảm lỗi hardcode path/host.
- Các phép tính permission hoặc repository lookup tốn kém không nên thực hiện riêng lẻ cho mỗi item trong assembler nếu có hàng nghìn rows; cần batch/preload để tránh N+1 queries.

### methodOn tạo proxy, không thực hiện request

Đoạn:

~~~java
Link self = linkTo(
        methodOn(BookController.class).one(1L)
).withSelfRel();
~~~

là **snippet minh họa**, cần import **org.springframework.hateoas.Link** và các static methods. Spring HATEOAS dùng proxy để ghi nhận method invocation/mapping; nó **không gọi repository, không thực hiện HTTP request và không chạy business code** của one(). Nếu method hoặc return type không proxy được, cần chọn overload của WebMvcLinkBuilder phù hợp và test link building.

## 8. Controller: item, collection và availability resource

Tạo **src/main/java/com/example/hateoas/BookController.java**:

~~~java
package com.example.hateoas;

import java.util.Comparator;
import java.util.Map;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private static final Map<Long, BookDto> BOOKS = Map.of(
            1L, new BookDto(1L, "Java Web Runtime",
                    "Nguyen An", true),
            2L, new BookDto(2L, "Designing Web APIs",
                    "Le Binh", false)
    );

    private final BookModelAssembler assembler;

    public BookController(BookModelAssembler assembler) {
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<BookDto> one(@PathVariable("id") long id) {
        return assembler.toModel(findBook(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<BookDto>> all() {
        var models = BOOKS.values().stream()
                .sorted(Comparator.comparingLong(BookDto::id))
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
                models,
                linkTo(methodOn(BookController.class)
                        .all()).withSelfRel()
        );
    }

    @GetMapping("/{id}/availability")
    public EntityModel<AvailabilityDto> availability(
            @PathVariable("id") long id) {

        BookDto book = findBook(id);
        AvailabilityDto data =
                new AvailabilityDto(book.id(), book.available());

        return EntityModel.of(
                data,
                linkTo(methodOn(BookController.class)
                        .availability(id)).withSelfRel(),
                linkTo(methodOn(BookController.class)
                        .one(id)).withRel("book")
        );
    }

    private BookDto findBook(long id) {
        BookDto book = BOOKS.get(id);
        if (book == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return book;
    }
}
~~~

Cấu trúc này cố ý dùng **Map** dữ liệu giả để không cần database. Khi áp dụng production, thay bằng service/repository có business validation, authentication và authorization.

**Các endpoint đã thực sự tồn tại:**

| Method / route | Representation | Links |
| --- | --- | --- |
| **GET /api/books/1** | EntityModel<BookDto> | self, books, availability |
| **GET /api/books/2** | EntityModel<BookDto> | self, books; không có availability rel |
| **GET /api/books** | CollectionModel<EntityModel<BookDto>> | self collection; mỗi item có links riêng |
| **GET /api/books/1/availability** | EntityModel<AvailabilityDto> | self, book |
| **GET /api/books/999** | 404 Not Found | Không tạo model book không tồn tại |

**Sách số 2 không có availability link nhưng endpoint /api/books/2/availability vẫn tồn tại** và có thể trả available=false. Điều này minh họa chính xác sự khác biệt giữa hypermedia navigation và route visibility/permission; không suy từ link thiếu rằng endpoint không tồn tại.

**CollectionModel** có self của danh mục, không phải self của item đầu tiên. **sorted(Comparator.comparingLong(...))** tạo thứ tự ổn định cho hai item demo; với database thật cần pagination/sort tại nguồn dữ liệu, không load toàn bảng vào JVM.

### Main class Spring Boot

Tạo **src/main/java/com/example/hateoas/HateoasBooksApplication.java**:

~~~java
package com.example.hateoas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HateoasBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(HateoasBooksApplication.class, args);
    }
}
~~~

Mỗi public class/record có file trùng tên, package root **com.example.hateoas** thống nhất để Spring component scan tìm BookController và BookModelAssembler. Không cần web.xml, @EnableHypermediaSupport hay custom HAL ObjectMapper trong demo.

## 9. Chạy và kiểm response bằng curl

Trong project có Maven và Java 17+, chạy:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Mở terminal thứ hai sau khi server chạy. Chọn **Accept: application/hal+json** để client yêu cầu representation HAL rõ ràng.

### Item có nhiều links

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1
~~~

Header thường có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

Body logic:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    },
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "availability": {
      "href": "http://localhost:8080/api/books/1/availability"
    }
  }
}
~~~

Thứ tự fields/rels không phải hợp đồng bất biến. Giá trị href giả định request trực tiếp localhost:8080, không qua reverse proxy.

### Item không có conditional link

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/2
~~~

Body vẫn có dữ liệu và **_links.self/books**, nhưng không có **_links.availability** theo assembler. Không nên kiểm logic business bằng cách chỉ xem link có hay không: endpoint vẫn có thể được gọi trực tiếp. Authorization phải enforce ở server.

### Collection có _embedded

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books
~~~

Body dạng rút gọn:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "author": "Nguyen An",
        "available": true,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/1"
          },
          "books": {
            "href": "http://localhost:8080/api/books"
          },
          "availability": {
            "href": "http://localhost:8080/api/books/1/availability"
          }
        }
      },
      {
        "id": 2,
        "title": "Designing Web APIs",
        "author": "Le Binh",
        "available": false,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/2"
          },
          "books": {
            "href": "http://localhost:8080/api/books"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books"
    }
  }
}
~~~

**_embedded.books** xuất hiện nhờ relation được chọn cho BookDto; nếu dùng tên class/relation tùy chỉnh khác, embedded key có thể khác. Client nên dùng relation theo contract, không giả định HAL luôn gọi mọi collection là data/items.

### Sub-resource availability

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1/availability
~~~

Body điển hình:

~~~json
{
  "bookId": 1,
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1/availability"
    },
    "book": {
      "href": "http://localhost:8080/api/books/1"
    }
  }
}
~~~

### Not found

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/999
~~~

Kỳ vọng status **404 Not Found**. Body lỗi tùy Spring Boot error configuration, không nhất thiết được HAL-serialize như EntityModel. Nếu dự án chuẩn hóa lỗi theo Problem Details (**application/problem+json**), phải test error negotiation riêng.

### Compare Accept headers

~~~bash
curl -si -H 'Accept: application/json' \
  http://localhost:8080/api/books/1

curl -si -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1
~~~

Theo tài liệu Boot 3.3, HAL được dùng như JSON media type mặc định khi HATEOAS auto-configuration hoạt động. Nếu đã cấu hình **spring.hateoas.use-hal-as-default-json-media-type=false**, thay converters hoặc chủ động @EnableHypermediaSupport, bạn cần kiểm Content-Type và schema response thực tế, không giả định cấu hình mới giữ nguyên behavior.

## 10. Link builder thay vì hardcode đường dẫn

Cách dễ gây lỗi:

~~~java
// Khong nen de URL co dinh localhost trong production.
String selfUrl = "http://localhost:8080/api/books/" + id;
~~~

Khi triển khai dưới HTTPS, context path, reverse proxy hoặc API v2, link hardcode trở nên sai. Sử dụng Spring MVC mappings:

~~~java
Link self = linkTo(
        methodOn(BookController.class).one(id)
).withSelfRel();
~~~

Snippet này cần import **org.springframework.hateoas.Link** và static methods của **WebMvcLinkBuilder**, đồng thời biến **id** trong scope. **methodOn(...)** tạo một dummy invocation để trích @RequestMapping/@GetMapping và path variable; nó **không gọi logic repository, không gọi HTTP và không chạy controller thật**.

So sánh:

~~~java
Link list = linkTo(BookController.class).withRel("books");
Link one = linkTo(
        methodOn(BookController.class).one(id)
).withSelfRel();
~~~

- **linkTo(BookController.class)** tạo link tới class-level mapping (**/api/books** trong demo).
- **linkTo(methodOn(...).one(id))** tạo link tới method-specific mapping (**/api/books/{id}**).
- Nếu controller class mapping chứa path variables hoặc nhiều method signatures phức tạp, dùng đúng overload/parameters và integration test.

**Không dùng methodOn từ background job ngoài Servlet request rồi mong nó biết hostname public của người dùng.** Khi không có HttpServletRequest, cần base URI thích hợp từ cấu hình/URI builder hoặc client-facing route rõ ràng.

### Link with query parameters

Ví dụ HAL link template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/books{?q,page,size}",
      "templated": true
    }
  }
}
~~~

URI Template cho phép client mở rộng q/page/size đúng quy tắc encoding. Tạo query string bằng cách nối dữ liệu người dùng chưa encode có thể sinh URL sai hoặc lộ thông tin nhạy cảm. Spring URI building APIs và Link templating thích hợp giúp giảm lỗi.

## 11. RepresentationModelAssembler và khả năng mở rộng

Code demo ngắn nên có thể xây links ngay trong controller; nhưng khi có nhiều endpoint/DTO/resource states, điều đó sẽ lặp code self/collection/related links.

**RepresentationModelAssembler** có thể:

- Chuyển domain DTO thành EntityModel có links.
- Dùng condition theo state và permission để hiển thị relation phù hợp.
- Cung cấp cùng một rel ở nhiều resource implementations.
- Giảm số lượng URL strings hardcode.
- Được test độc lập (và integration test qua HTTP thật).
- Hỗ trợ collection mapping qua **toCollectionModel(...)** khi phù hợp.

Một pipeline điển hình:

~~~text
GET /api/books/1
    |
    v
Controller -> Service -> Repository
    |
    v
DTO mapping / authorization context
    |
    v
BookModelAssembler.toModel(book)
    |
    +--> self
    +--> books
    +--> availability (neu state phu hop)
    |
    v
EntityModel<BookDto>
    |
    v
HAL message converter + Jackson
    |
    v
HTTP 200 Content-Type: application/hal+json
~~~

**Không gọi database/authorization service N lần cho N items chỉ để thêm links** nếu có thể batch-fetch hoặc đưa ngữ cảnh quyền vào assembler. HATEOAS có thể tăng overhead CPU/latency và kích thước payload; đo trong traffic thật.

### Empty collections

Với một collection không có phần tử, HAL converter đôi khi không suy được kiểu phần tử do Java generic type erasure và có thể không render **_embedded** như bạn mong. Spring HATEOAS cung cấp **CollectionModel.empty(...)**, **withFallbackType(...)** để trợ giúp thông tin type khi cần. Client cũng nên xử lý collection rỗng không có _embedded như một trường hợp hợp lệ theo API contract.

### Link nhiều giá trị cùng rel

Nếu một rel có nhiều destinations, HAL có thể biểu diễn dạng array. Client không nên viết parser cho rằng **_links.<rel>** luôn có duy nhất một object; cần theo contract của rel đó. Với rel như next/prev thường một link; với relation domain khác có thể có nhiều.

## 12. Hypermedia affordance và workflow

Một order đang ở trạng thái **NEW** có thể trả rel **cancel** và **pay**, còn order đã shipped có rel **tracking**:

~~~text
Order NEW:
  self -> /orders/42
  pay  -> /orders/42/payment
  cancel -> /orders/42/cancellation

Order SHIPPED:
  self -> /orders/42
  tracking -> /orders/42/tracking
~~~

Đây là ví dụ workflow **minh họa**, không phải endpoints có trong demo sách. Một link href thuần thường chưa đủ để cho client biết hành động yêu cầu **POST/DELETE**, request body và auth details. Spring HATEOAS hỗ trợ **affordances** để mô tả hành động dựa trên controller methods, có thể dùng **afford(...)** và **andAffordance(...)** theo API tương ứng.

**Cần nhớ:**

1. Muốn mô tả một thao tác, backend phải có HTTP handler thực cho thao tác đó.
2. Không sinh link hứa hẹn action mà endpoint không hỗ trợ.
3. Không chỉ ẩn link khi user thiếu quyền: endpoint vẫn phải **enforce authorization**.
4. Không đưa session ID, JWT hoặc reset token vào href; URL dễ bị log/cache/chia sẻ.
5. Liên kết có điều kiện nên dựa trên state/permission **thực**, không tin claim không được xác minh từ client.
6. Client HATEOAS nên hiểu cách xử lý relation thiếu hoặc nhiều links, không dự đoán workflow một cách cứng nhắc.

**HATEOAS không phải authentication, authorization, CSRF protection hay validation.** Chúng vận hành song song.

## 13. Phân trang với PagedModel

Với collection lớn, **PagedModel<T>** thêm **PageMetadata** cho dữ liệu một trang. Đây là đoạn minh họa **không độc lập**, vì cần biến **pageContent** là collection EntityModel<BookDto> đã được lấy từ database và assembler:

~~~java
PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
                20,    // page size
                0,     // zero-based page number
                133,   // total elements
                7);    // total pages

PagedModel<EntityModel<BookDto>> result =
        PagedModel.of(
                pageContent,
                metadata,
                Link.of("https://api.example.test/api/books?page=0&size=20")
                        .withSelfRel());
~~~

Imports cần có **org.springframework.hateoas.PagedModel**, **EntityModel**, **Link** và **BookDto**. Với 133 elements, page size 20, totalPages 7 là nhất quán. **PagedModel** có thể xuất **page.size**, **page.totalElements**, **page.totalPages**, **page.number** tùy HAL mapping.

**Quan trọng:** đoạn PagedModel.of(...) ở trên chỉ truyền **self link**, **không tự tạo next/prev**. Nếu muốn page links tự động, phải tạo chúng rõ ràng hoặc dùng **PagedResourcesAssembler** với **Spring Data Page<T>** khi project có Spring Data web support phù hợp.

Ví dụ representation đã được application bổ sung next/prev:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.test/api/books?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 133,
    "totalPages": 7,
    "number": 0
  }
}
~~~

Trong ví dụ JSON này, **next** phải do code ngoài snippet PagedModel.of(...) thêm vào; đừng hiểu đó là output chính xác của snippet.

**Đừng để client tự tạo next bằng page+1 nếu server trả _links.next.href**. Đi theo server-provided next giúp tách client khỏi thuật toán pagination (offset/page/cursor). Self phải giữ đúng sort/filter/page và các query parameters cần thiết.

## 14. Reverse proxy và liên kết sai host/scheme

Mô hình production:

~~~text
Browser: https://api.example.test/catalog/api/books/1
    |
    v
Ingress / reverse proxy (TLS termination)
    |
    v
Spring Boot: http://books-service:8080/api/books/1
~~~

Backend nhận request qua HTTP nội bộ. Nếu link builder chỉ thấy host/scheme nội bộ, nó có thể trả:

~~~json
{
  "_links": {
    "self": {
      "href": "http://books-service:8080/api/books/1"
    }
  }
}
~~~

Đây là link **sai cho client bên ngoài**. Với HTTPS browser, link HTTP có thể bị mixed-content policy chặn, và hostname nội bộ không thể resolve.

Reverse proxy có thể cung cấp forwarding metadata:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Prefix: /catalog
~~~

Spring Boot 3.3 cho phép:

~~~properties
# Dung Spring Framework ForwardedHeaderFilter tren Servlet stack
server.forward-headers-strategy=framework
~~~

hoặc:

~~~properties
# Dung xu ly forwarded headers native cua embedded server
server.forward-headers-strategy=native
~~~

**FRAMEWORK** dùng hỗ trợ của Spring Framework; **NATIVE** dùng container; **NONE** bỏ qua header. Behavior của những strategy phụ thuộc môi trường và proxy, nên test ở public URL thật.

**Cực kỳ quan trọng về trust boundary:** client ngoài internet có thể tự gửi Forwarded/X-Forwarded-* giả. Chỉ bật xử lý các header này khi edge proxy đã **loại bỏ header không tin cậy và ghi lại giá trị chuẩn** và backend không bị truy cập trực tiếp từ nguồn không tin cậy. Nếu không, attacker có thể đưa hostname độc hại vào **_links.self** (link poisoning) hoặc redirect.

Với proxy path rewrite, kiểm cả **X-Forwarded-Prefix**, context path, TLS scheme và port; đừng chỉ kiểm hostname. Trường hợp service chạy sau nhiều lớp gateway/mesh, cần xác định lớp nào được quyền đưa public origin vào request.

### Test qua proxy

1. Gọi HTTPS public endpoint với Accept HAL.
2. Kiểm **_links.self.href** chứa **https://api.example.test/catalog/...** phù hợp.
3. Theo href trả về, xác nhận resource còn truy cập được.
4. Thử origin host khác/Forwarded giả ở edge và kiểm không có link poisoning.
5. Kiểm redirects, errors, collection links và pagination links chứ không chỉ một item.
6. Nếu proxy thay path, xác nhận **linkTo(methodOn(...))** vẫn tạo URL đúng từ effective request context.

## 15. HTTP content negotiation và caching

Một client muốn HAL nên gửi:

~~~http
GET /api/books/1 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Server HAL response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

Khi API hỗ trợ nhiều representations tùy Accept, cần cân nhắc **Vary: Accept** và cấu hình shared cache/CDN để không phát nhầm representation. **Không khẳng định Spring luôn tự thêm một Vary header cụ thể**; kiểm headers và cache key thực tế.

**EntityModel.of(...) không tự tạo Cache-Control, ETag hay Last-Modified.** Nếu response có links được cá nhân hóa theo quyền, đặc biệt thận trọng với **public caching**. Một user không nên nhận links chứa thông tin riêng tư hoặc điều hướng dành cho user khác từ shared CDN cache.

Nếu ETag dựa trên representation bytes, thay đổi links cũng có thể làm ETag thay đổi. Nếu chỉ hash domain object mà links phụ thuộc user/permissions, cần cân nhắc validator và cache policy để tránh revalidation sai.

**Đổi sang HAL không thay HTTP status semantics:** GET thường 200, không có resource 404, tạo mới có thể 201 và header Location, lỗi validation 400, access denied 403. Error response có thể dùng **Problem Details**; không bắt buộc mọi response lỗi cũng chứa _links.

### Compatibility khi chuyển từ JSON cũ

- Công bố **application/hal+json** trong API docs và ví dụ client.
- Test client chỉ chấp nhận **application/json** vì Boot 3.3 có HAL-as-default-JSON behavior.
- Nếu đổi **spring.hateoas.use-hal-as-default-json-media-type=false**, test negotiation và converters thật.
- Không thay tên rel/embedded keys mà không đánh giá clients đang parse chúng.
- Với collection rỗng và error responses, client phải xử lý schema biến thể hợp lệ.
- Nếu representation schema thay đổi lớn, lập migration/versioning plan hợp lý; HATEOAS không làm biến mất mọi breaking changes.

## 16. Integration test chạy HTTP thật bằng random port

Cấu hình đã có dependency **spring-boot-starter-test**. Test sau xác minh rằng HAL được serialize đúng qua HTTP connector chứ không chỉ assembler tạo object trong memory.

Tạo **src/test/java/com/example/hateoas/BookHateoasIntegrationTests.java**:

~~~java
package com.example.hateoas;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHateoasIntegrationTests {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://localhost:" + port + path))
                .header("Accept", "application/hal+json")
                .GET()
                .build();
        return http.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void itemHasExpectedLinks() throws Exception {
        HttpResponse<String> response = get("/api/books/1");
        assertEquals(200, response.statusCode());

        assertTrue(response.headers()
                .firstValue("content-type")
                .orElse("").startsWith("application/hal+json"));

        JsonNode body = json.readTree(response.body());
        assertEquals(1, body.path("id").asInt());
        assertEquals("Java Web Runtime",
                body.path("title").asText());

        String base = "http://localhost:" + port;
        assertEquals(base + "/api/books/1",
                body.path("_links").path("self")
                        .path("href").asText());
        assertEquals(base + "/api/books",
                body.path("_links").path("books")
                        .path("href").asText());
        assertEquals(base + "/api/books/1/availability",
                body.path("_links").path("availability")
                        .path("href").asText());
    }

    @Test
    void unavailableBookHidesAvailabilityRel()
            throws Exception {
        HttpResponse<String> response = get("/api/books/2");
        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        assertFalse(body.path("available").asBoolean(true));
        assertFalse(body.path("_links").has("availability"));
    }

    @Test
    void collectionHasBooksAndSelfLink() throws Exception {
        HttpResponse<String> response = get("/api/books");
        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        JsonNode books = body.path("_embedded").path("books");
        assertTrue(books.isArray());
        assertEquals(2, books.size());
        assertEquals("http://localhost:" + port + "/api/books",
                body.path("_links").path("self")
                        .path("href").asText());
    }

    @Test
    void unknownBookIs404() throws Exception {
        assertEquals(404, get("/api/books/999").statusCode());
    }
}
~~~

Lệnh:

~~~bash
mvn test
~~~

**JUnit test tạo embedded Spring Boot server trên RANDOM_PORT**, dùng Java 17 standard HttpClient để gửi request và ObjectMapper đọc JSON. Nhờ đó test kiểm đúng Content-Type, links và URLs có port thực, không chỉ xác nhận bean tồn tại.

Điểm cần nhớ:

- JSON field order không được test cứng.
- Test localhost không kiểm reverse proxy forwarding; cần test qua edge để bảo đảm public HTTPS links.
- Demo không có Spring Security; khi thêm security, cần test cả authenticated, unauthenticated và permission-specific relations.
- Với collection rỗng, thêm testcase riêng nếu project thực có empty result.
- Với API dùng pagination, test **next/prev/self** theo state và filter/sort.
- Khi test nhiều data volumes, tránh chỉ kiểm status 200 và bỏ qua số lượng _embedded items hoặc valid href.

### Client có thể theo link trong test

Một test hypermedia đúng hướng có thể:

~~~text
GET /api/books/1
    |
    +-- doc response -> _links.availability.href
    |
    +-- client GET href tu response (khong hardcode path)
    |
    +-- assert response bookId=1, available=true
~~~

Bài này minh họa quy trình; trong dự án thật nên viết helper parse href theo rel rồi gọi URI trả về, đồng thời kiểm scheme/host nằm trong phạm vi được tin cậy trước khi gửi credentials.

## 17. Client tiêu thụ HAL response

Một JavaScript client đơn giản có thể đọc relation thay vì tự ghép đường dẫn:

~~~javascript
async function getAvailability(bookUrl) {
  const res = await fetch(bookUrl, {
    headers: { Accept: "application/hal+json" }
  });

  if (!res.ok) {
    throw new Error("Book HTTP " + res.status);
  }

  const book = await res.json();
  const href = book._links?.availability?.href;

  if (!href) {
    return { available: false, reason: "not-offered" };
  }

  const availableRes = await fetch(href, {
    headers: { Accept: "application/hal+json" }
  });

  if (!availableRes.ok) {
    throw new Error("Availability HTTP " + availableRes.status);
  }

  return availableRes.json();
}
~~~

Đây là function minh họa cần được gọi trong một page/frontend có access, CORS và credentials phù hợp, không phải file Java chạy độc lập.

**Một số quy tắc client quan trọng:**

- Đừng tự suy link chỉ vì relation thiếu; UI/workflow cần xử lý trường hợp không có.
- Một rel có thể có nhiều links, nên parser phải theo contract single vs array.
- Href có thể là URI Template, phải expand trước khi dùng.
- Nếu một API trả href sang hostname khác, đừng tự gửi Bearer token hoặc cookie của API A sang host lạ; kiểm trusted origins.
- Nếu GET tiếp theo trả 401/403, xử lý authentication/authorization như HTTP thông thường.
- Không dùng HATEOAS links như cơ chế thay cho OpenAPI schema hoặc validation of response.
- Nếu frontend ở origin khác, browser CORS vẫn áp dụng; HATEOAS không bật CORS tự động.

## 18. Spring Data REST, OpenAPI và Spring WebFlux

### Spring Data REST khác Spring HATEOAS

| Công nghệ | Chức năng | Tạo CRUD endpoints tự động? |
| --- | --- | --- |
| **Spring HATEOAS** | Link/representation/assembler/HAL APIs | **Không**. |
| **Spring Data REST** | Expose Spring Data repositories theo REST conventions | **Có thể**, khi cấu hình/expose. |
| **Spring MVC** | HTTP controller mapping, validation, converters | Không tự tạo HAL links từ DTO thuần. |
| **Spring Boot HATEOAS auto-config** | Chuẩn bị HAL/Jackson/LinkDiscoverers | Không tự tạo repository/controllers. |

Không thêm **spring-boot-starter-data-rest** chỉ để có EntityModel/CollectionModel. Việc tự export repositories có những hệ quả security, serialization và API surface riêng.

### OpenAPI và hypermedia bổ trợ nhau

**OpenAPI** giúp mô tả endpoints, methods, input/output schemas, security schemes và status codes ở mức hợp đồng tĩnh. **HATEOAS** cho biết tại runtime có links/relations nào tương ứng resource state. Một hệ thống có thể dùng cả hai: OpenAPI cho SDK/documentation/test, HAL links cho discoverability/workflow.

HATEOAS không loại bỏ nhu cầu versioning, backwards compatibility, authentication hay error model.

### WebFlux không dùng starter HATEOAS MVC theo cách demo

Tài liệu Spring Boot 3.3 khuyến cáo **spring-boot-starter-hateoas** dành cho **Spring MVC** và không nên kết hợp trực tiếp với **Spring WebFlux**. Đối với WebFlux, dùng **spring-boot-starter-webflux** và dependency trực tiếp **org.springframework.hateoas:spring-hateoas**, áp dụng reactive link/assembler APIs phù hợp.

Đừng copy **WebMvcLinkBuilder** dựa trên Servlet request vào một reactive WebFlux controller rồi coi nó là đường triển khai chuẩn. Phải xác định web application type, codecs và request context thật. Nếu project có cả starter-web và starter-webflux, Boot thường chọn Servlet MVC theo mặc định.

## 19. Hiệu năng, bảo mật và lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| DTO JSON không có _links | Chưa dùng EntityModel/assembler | Bọc dữ liệu và thêm links theo rel. |
| Không có _embedded.books | Tên relation không như mong muốn, collection rỗng, mapping khác | Kiểm @Relation, fallback type và HAL output thật. |
| Content-Type không là application/hal+json | Accept/MessageConverter/Boot property khác hoặc auto-config bị thay | Test Accept và HATEOAS setup. |
| Link self chỉ tới localhost/host nội bộ | Reverse proxy không xử lý Forwarded headers | Bật strategy có kiểm soát và test public HTTPS. |
| methodOn tạo href sai | Mapping hoặc parameters chưa khớp, ngoài request context | Kiểm annotations, signature, linkTo overload và tests. |
| Client báo 404 theo link | Link stale, route chưa có, path rewrite sai | Kiểm endpoint tồn tại và link builder/proxy. |
| Bỏ link availability nhưng endpoint vẫn trả 200 | Link visibility không phải authorization | Thiết kế link semantics và enforce ACL ở endpoint. |
| PagedModel chỉ có self, không có next | Chưa tạo next hoặc không dùng paging assembler | Tạo links trang đúng điều kiện. |
| Mọi resource có link tới nơi user không được phép | Assembler không xét state/permissions | Lọc link nếu cần UX; vẫn kiểm quyền ở backend. |
| Response kích thước lớn bất thường | Embedded quá sâu hoặc quá nhiều per-item links | Pagination, selective embedding, cache, gzip nếu phù hợp. |
| N+1 queries khi assemble collection | Assembler gọi DB cho từng relation | Prefetch/batch permission/data, đo DB metrics. |
| HAL qua CDN lộ link theo user khác | Shared cache không phân biệt personalization | Cache-Control phù hợp, không public-cache private representation. |
| Client cố gửi token tới href host khác | Không validate hostname và trust scope | Hạn chế destination, không forward credentials tùy tiện. |
| Starter HATEOAS MVC không hợp reactive app | Nhầm dependency WebFlux | Dùng spring-hateoas trực tiếp với reactive APIs. |
| Có Spring HATEOAS nhưng CRUD endpoints không tự sinh | Nhầm với Spring Data REST | Tự viết controllers hoặc chọn Spring Data REST có chủ đích. |
| Test status=200 nhưng link bị sai | Không kiểm _links/_embedded/href | Thêm contract/integration tests. |

**Bảo mật:** Relation chỉ là metadata điều hướng. User có thể sửa URL, gọi API trực tiếp, giả Origin hoặc gửi token sai. Backend phải enforce authentication/authorization và business-state checks. Với links tạo từ header host/Forwarded, cần kiểm trust boundary để tránh host-header poisoning. Không đưa token/PII vào URL.

**Hiệu năng:** Link building có thể tăng byte size/CPU, đặc biệt với hàng nghìn collection items; dùng pagination, batch-fetch permission, caching hợp lệ và giảm embedded depth. Bật compression có thể tiết kiệm bandwidth nhưng cũng có CPU trade-off; đo p95/p99 và request volume thật.

## 20. Checklist triển khai production

- [ ] Xác nhận nhu cầu hypermedia và các use cases sẽ hưởng lợi từ discoverability.
- [ ] Dùng starter HATEOAS MVC đúng stack; phân biệt với Data REST/WebFlux.
- [ ] Test HAL serialization và Content-Type với Accept: application/hal+json.
- [ ] Dùng EntityModel cho item, CollectionModel cho collection, PagedModel cho trang dữ liệu.
- [ ] Định nghĩa rel semantics rõ và ổn định; @Relation cho embedded collection khi cần.
- [ ] Sinh links bằng WebMvcLinkBuilder từ Spring MVC mappings, không hardcode localhost.
- [ ] Tập trung link generation trong RepresentationModelAssembler hoặc service riêng.
- [ ] Với links theo state/permission, vẫn enforce security trên endpoint đích.
- [ ] Không đưa secret, private URL hoặc thông tin nhạy cảm vào href.
- [ ] Bảo vệ forwarded headers bằng trusted proxy; kiểm HTTPS/hostname/context prefix.
- [ ] Kiểm self/related/collection links khi chuyển qua proxy hoặc versioned routes.
- [ ] Tạo next/prev/first/last đúng với paging state và filter/sort; không nhầm metadata với links tự động.
- [ ] Xử lý collection rỗng, multiple links per rel, URI templates và errors.
- [ ] Đặt HTTP cache/ETag/Vary phù hợp khi representation khác theo user/Accept.
- [ ] Kiểm link structure và actual follow-link behavior qua HTTP tests; không chỉ test status.
- [ ] Theo dõi payload bytes, CPU, latency, số SQL queries khi tạo links trên collection.
- [ ] Lập kế hoạch rel/schema compatibility và client migration.
- [ ] Chọn Spring Boot version được bảo trì và cập nhật bản vá production.

## 21. Tự kiểm tra kiến thức

**1. HATEOAS nghĩa là gì?**  
Hypermedia as the Engine of Application State: server trả links/controls hướng dẫn client khám phá resources và workflow.

**2. EntityModel khác CollectionModel thế nào?**  
EntityModel bọc một object cùng links; CollectionModel bọc nhiều items và links của collection.

**3. Dùng starter-hateoas là mọi @RestController tự có self link?**  
Không. Ứng dụng phải chủ động xây EntityModel/Link/assembler.

**4. methodOn có gọi business logic thật không?**  
Không. Nó ghi lại dummy method invocation để lấy mapping/arguments khi tạo link.

**5. @Relation(collectionRelation="books") có tác dụng gì?**  
Chỉ định relation cho embedded collection, giúp HAL dùng _embedded.books thay vì tên mặc định.

**6. Vì sao self của collection khác self của từng item?**  
Chúng đại diện những resources có URI khác nhau: /api/books so với /api/books/{id}.

**7. Không thấy availability link có nghĩa endpoint chắc chắn không tồn tại?**  
Không. Link visibility là policy của representation, không phải router hoặc authorization.

**8. PagedModel tự tạo next chỉ từ PageMetadata?**  
Không nhất thiết. Cần tạo next/prev links hoặc dùng paging assembler phù hợp.

**9. Khi nào links bị sai host/protocol sau deploy?**  
Khi proxy/TLS termination làm backend chỉ thấy internal http host; cần trusted forwarded headers hoặc public base URI policy.

**10. Có thể tin X-Forwarded-Host từ mọi request?**  
Không. Proxy biên phải xóa/ghi đè header không tin cậy.

**11. Spring HATEOAS và Spring Data REST có giống nhau?**  
Không. HATEOAS xây links/models; Data REST có thể export repository endpoints.

**12. Client có nhất thiết dùng hardcoded URI sau khi biết rel?**  
Không. Client có thể theo href server cung cấp cho rel đã hiểu.

**13. Với Boot 3.3, Accept application/json có thể trả HAL không?**  
Có. HAL có thể là JSON default media type theo auto-configuration; kiểm property và response thực tế.

**14. Có nên gửi Bearer token tới mọi href nhận được?**  
Không. Kiểm trusted host/scheme và credential scope để tránh rò secret.

**15. Có dùng starter-hateoas MVC trực tiếp với WebFlux không?**  
Không nên. Boot docs hướng dẫn dùng spring-hateoas dependency trực tiếp với reactive stack.

## 22. Nguồn tham khảo chính thống

- **Spring Boot 3.3 – Spring HATEOAS:** https://docs.spring.io/spring-boot/3.3/reference/web/spring-hateoas.html — auto-config, HAL media types, MVC starter, WebFlux distinction.
- **Spring HATEOAS – Reference Documentation:** https://docs.spring.io/spring-hateoas/docs/current/reference/html/ — representation models, relation providers, link builders, HAL và affordances; cần đối chiếu với version được BOM quản lý.
- **Spring HATEOAS – WebMvcLinkBuilder API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html — linkTo, methodOn.
- **Spring HATEOAS – PagedModel API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/PagedModel.html — PageMetadata.
- **Spring HATEOAS – CollectionModel API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/CollectionModel.html — collection và fallback type.
- **Spring Boot 3.3 – Running Behind Proxy:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — server.forward-headers-strategy và forwarded headers.
- **Spring Framework – MVC Forwarded Headers:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — ForwardedHeaderFilter và trust boundary.
- **Spring – Building a Hypermedia-Driven RESTful Web Service:** https://spring.io/guides/gs/rest-hateoas/
- **HAL specification:** https://stateless.group/hal_specification.html — _links/_embedded, link relations.
- **RFC 6570 – URI Template:** https://www.rfc-editor.org/rfc/rfc6570
