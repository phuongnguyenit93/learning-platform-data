# Mối liên hệ giữa Spring Data REST, Spring Data, Spring MVC và Spring HATEOAS

Bốn thành phần này thuộc các phần khác nhau của hệ sinh thái Spring. Chúng phối hợp để tạo một REST API dựa trên dữ liệu, nhưng mỗi thành phần giải quyết một trách nhiệm riêng:

- **Spring Data** cung cấp mô hình truy cập dữ liệu và các abstraction như Repository.
- **Spring Data REST** xuất các Spring Data Repository thành REST resource, nhờ đó có thể tạo các endpoint CRUD mà không phải viết controller cho từng repository.
- **Spring MVC** tiếp nhận và xử lý HTTP request trong ứng dụng Servlet: ánh xạ URL, gọi handler, chuyển đổi request/response và xử lý lỗi.
- **Spring HATEOAS** hỗ trợ biểu diễn tài nguyên theo hướng hypermedia, đặc biệt là các link điều hướng và định dạng HAL.

Có thể nhớ quan hệ chính như sau: Spring Data mô tả cách ứng dụng truy cập dữ liệu; Spring Data REST đưa repository ra HTTP; Spring MVC cung cấp hạ tầng web cho luồng HTTP đó; Spring HATEOAS bổ sung các liên kết giúp client khám phá API.

## 1. Vai trò của từng thành phần

### Spring Data: lớp truy cập dữ liệu

Spring Data là một họ dự án, không phải một REST framework. Nó cung cấp các abstraction dùng chung để thao tác với nhiều loại kho dữ liệu. Các module cụ thể triển khai abstraction đó cho từng công nghệ, chẳng hạn:

- Spring Data JPA: làm việc với cơ sở dữ liệu quan hệ thông qua JPA.
- Spring Data JDBC: truy cập cơ sở dữ liệu quan hệ theo mô hình JDBC.
- Spring Data MongoDB: làm việc với MongoDB.
- Spring Data Redis: làm việc với Redis.
- Spring Data Elasticsearch: làm việc với Elasticsearch.

Một repository thường là interface mô tả các thao tác dữ liệu:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {
    List<Person> findByNameContainingIgnoreCase(String name);
}
~~~

Khi ứng dụng khởi động, Spring Data tạo implementation phù hợp cho repository dựa trên module và cấu hình đang dùng. Với ví dụ trên, Spring Data JPA cung cấp implementation dùng JPA để truy vấn cơ sở dữ liệu.

Nếu chỉ có Spring Data, ứng dụng có thể inject repository vào service hoặc controller và gọi bằng Java. Repository **không tự trở thành một HTTP endpoint** chỉ vì nó kế thừa JpaRepository.

### Spring Data REST: xuất repository thành REST resource

Spring Data REST xây dựng trên Spring Data Repository và tự động xuất các repository được phép export thành REST resource. Nó cung cấp cách ánh xạ thao tác repository thành HTTP endpoint, quản lý resource, association, phân trang, sắp xếp, search resource và biểu diễn hypermedia.

Ví dụ, một repository quản lý Person có thể cung cấp:

- Endpoint collection để lấy danh sách và tạo Person.
- Endpoint item để đọc, cập nhật hoặc xóa một Person.
- Endpoint search cho các query method được export.
- Link đến các association giữa những domain object.

Spring Data REST giúp giảm mã lặp cho API CRUD có cấu trúc gần với repository. Nó không tự thiết kế nghiệp vụ của ứng dụng: quy tắc nghiệp vụ phức tạp, quy trình nhiều bước, tích hợp hệ thống ngoài và API contract chuyên biệt vẫn cần service/controller phù hợp.

### Spring MVC: hạ tầng xử lý HTTP

Spring MVC thuộc Spring Framework và triển khai mô hình web Servlet. Thành phần trung tâm là DispatcherServlet. Một request đi vào ứng dụng sẽ được ánh xạ đến handler phù hợp; các thành phần khác xử lý tham số, chuyển đổi dữ liệu, validation, exception và response.

Trong cấu hình Spring Data REST dùng WebMVC, Spring Data REST tích hợp vào hạ tầng Spring MVC để nhận request và phục vụ các repository resource. Vì vậy:

- Spring MVC chịu trách nhiệm về luồng xử lý HTTP của ứng dụng Servlet.
- Spring Data REST cung cấp các handler và quy tắc để repository trở thành REST resource.
- Spring MVC không quyết định dữ liệu được lưu trong JPA, MongoDB hay Redis.
- Spring Data REST không thay thế toàn bộ Spring MVC. Hai cơ chế có thể cùng tồn tại trong một ứng dụng.

Một controller do ứng dụng tự viết vẫn có thể dùng Spring MVC:

~~~java
@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping
    public List<ReportDto> getReports() {
        return reportService.findAll();
    }
}
~~~

Controller này phục vụ endpoint do ứng dụng thiết kế. Nó không tự động trở thành một repository resource của Spring Data REST.

### Spring HATEOAS: biểu diễn hypermedia và link

HATEOAS là viết tắt của Hypermedia as the Engine of Application State. Trong API hypermedia, response chứa các link mô tả những hành động hoặc tài nguyên liên quan mà client có thể tiếp tục truy cập. Client có thể khám phá API từ các link trong response thay vì phải tự ghép mọi URL theo quy ước nội bộ của server.

Spring HATEOAS cung cấp các kiểu dữ liệu và công cụ để tạo biểu diễn đó, ví dụ:

- **Link**: một liên kết có quan hệ (relation) và URI đích.
- **EntityModel**: bọc một domain object hoặc DTO và gắn các link.
- **CollectionModel**: bọc một tập hợp resource và các link của collection.
- **PagedModel**: biểu diễn collection có phân trang.
- **RepresentationModelAssembler**: chuyển domain object thành representation model.

Spring Data REST sử dụng khả năng hypermedia của Spring HATEOAS để trả về resource có link. Một định dạng thường gặp là HAL JSON, với các trường như **_links** và **_embedded**.

Spring HATEOAS không truy vấn database và cũng không tự tạo endpoint CRUD. Nó tập trung vào cách biểu diễn resource và điều hướng giữa các resource.

## 2. Cách các thành phần phối hợp

Trong một ứng dụng Spring Boot dùng Spring Data JPA và Spring Data REST trên Servlet stack, luồng khái quát như sau:

~~~mermaid
flowchart TD
    C["HTTP client"] --> M["Spring MVC"]
    M --> R["Spring Data REST"]
    R --> D["Spring Data Repository"]
    D --> S["Spring Data JPA"]
    S --> J["JPA provider"]
    J --> DB[("Database")]
    R -. "tạo representation và link bằng" .-> H["Spring HATEOAS / HAL"]
    H -. "được serialize thành HTTP response" .-> M
~~~

Diễn giải một request GET đến /people:

1. Client gửi HTTP request đến ứng dụng.
2. DispatcherServlet của Spring MVC tiếp nhận request và chuyển nó đến handler tương ứng.
3. Spring Data REST nhận diện resource được export và xác định repository cần gọi.
4. Spring Data Repository thực hiện thao tác. Với repository dựa trên JpaRepository, implementation của Spring Data JPA thực hiện truy vấn qua JPA provider.
5. Spring Data REST nhận kết quả và tạo biểu diễn resource. Spring HATEOAS hỗ trợ bổ sung self link, link đến collection, search hoặc association.
6. Spring MVC chuyển representation thành HTTP response và gửi về client.

Mỗi lớp có một câu hỏi riêng:

| Thành phần | Câu hỏi mà nó giải quyết |
|---|---|
| Spring Data | Ứng dụng truy cập dữ liệu qua abstraction nào? |
| Spring Data REST | Repository nào được xuất thành REST resource và endpoint nào được cung cấp? |
| Spring MVC | HTTP request được tiếp nhận, định tuyến và trả response như thế nào? |
| Spring HATEOAS | Response chứa dữ liệu và link điều hướng theo cấu trúc hypermedia nào? |
| Spring Data JPA (ví dụ) | Repository được thực thi trên cơ sở dữ liệu quan hệ bằng JPA ra sao? |

## 3. Ví dụ: xuất PersonRepository thành REST API

Ví dụ dưới đây dùng Spring Boot, Spring Data JPA, Spring Data REST và H2 để minh họa. Các đoạn code là những file riêng trong cùng một ứng dụng Spring Boot có class khởi động được đánh dấu bằng @SpringBootApplication.

### 3.1. Khai báo dependency

Với Gradle và Spring Boot dependency management, thêm các dependency sau vào khối dependencies hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    runtimeOnly 'com.h2database:h2'
}
~~~

Starter của Spring Boot quản lý phiên bản tương thích. Không nên tự chọn phiên bản Spring Data REST, Spring Data JPA và Spring HATEOAS rời rạc khi dự án đã dùng Spring Boot dependency management.

### 3.2. Domain entity

File Person.java:

~~~java
package example.people;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Person() {
        // Constructor cần cho JPA.
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Ví dụ dùng Jakarta Persistence như các ứng dụng Spring Boot 3 trở lên. Dự án Spring Boot 2 cũ dùng namespace javax.persistence.

### 3.3. Repository và cấu hình REST resource

File PersonRepository.java:

~~~java
package example.people;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    itemResourceRel = "person"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Person> findByNameContainingIgnoreCase(@Param("name") String name);
}
~~~

Các annotation có ý nghĩa:

- **@RepositoryRestResource** đánh dấu repository được Spring Data REST export. **path = "people"** đặt đường dẫn collection; **collectionResourceRel = "people"** đặt relation dùng khi nhúng collection trong HAL; **itemResourceRel = "person"** đặt relation cho từng item.
- **@RestResource** tùy chỉnh đường dẫn và relation của query method.
- **@Param("name")** đặt tên query parameter mà client truyền lên endpoint search.

Vì repository được export, không cần viết một controller CRUD riêng cho Person chỉ để gọi các phương thức cơ bản của repository.

### 3.4. Cấu hình database cho ví dụ

File application.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:people
spring.jpa.hibernate.ddl-auto=create-drop
spring.h2.console.enabled=true
~~~

Cấu hình trên tạo database H2 trong bộ nhớ cho lần chạy ứng dụng. Đây là cấu hình minh họa; ứng dụng thực tế cần cấu hình database, migration, transaction và chính sách schema phù hợp với môi trường triển khai.

Chạy ứng dụng bằng Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

### 3.5. Các endpoint được cung cấp

Với repository ở trên và base path mặc định, các request tiêu biểu là:

| HTTP method | Endpoint | Ý nghĩa |
|---|---|---|
| GET | /people | Lấy collection Person |
| POST | /people | Tạo Person mới |
| GET | /people/{id} | Lấy một Person |
| PUT | /people/{id} | Thay thế representation của Person |
| PATCH | /people/{id} | Cập nhật một phần Person |
| DELETE | /people/{id} | Xóa Person |
| GET | /people/search/by-name?name=ada | Tìm Person theo tên |

Các thao tác cụ thể còn phụ thuộc repository được export, cấu hình Spring Data REST và quyền truy cập của request.

Ví dụ tạo một Person:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"Ada Lovelace"}' \
  http://localhost:8080/people
~~~

Ví dụ đọc collection:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people
~~~

Ví dụ gọi search resource:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/people/search/by-name?name=ada"
~~~

### 3.6. Đọc response HAL

Một response collection có thể có cấu trúc minh họa như sau (URI và số lượng phụ thuộc dữ liệu thực tế):

~~~json
{
  "_embedded": {
    "people": [
      {
        "name": "Ada Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          },
          "person": {
            "href": "http://localhost:8080/people/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
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

Các phần đáng chú ý:

- **_embedded.people** chứa các item trong collection theo relation đã cấu hình.
- **_links.self** trỏ đến chính resource hiện tại.
- **_links.person** là link đến item theo relation đã cấu hình.
- **_links.search** cho biết resource search có thể được khám phá từ collection.
- **page** mô tả thông tin phân trang.

HAL không chỉ là JSON chứa dữ liệu. Các link cho biết client có thể đi tiếp đến đâu. Một client hypermedia nên đọc link theo relation thay vì giả định mọi URI luôn có một cấu trúc cố định.

## 4. Khi nào dùng Spring Data REST và khi nào tự viết controller?

Spring Data REST phù hợp khi resource gần với một repository và API chủ yếu cung cấp thao tác dữ liệu tiêu chuẩn. Ví dụ: một ứng dụng quản trị nội bộ cần CRUD cho một số entity, hoặc một service muốn công bố resource repository với phân trang, search và link hypermedia.

Nên cân nhắc service/controller tự thiết kế khi endpoint đại diện cho một hành động nghiệp vụ thay vì một entity. Ví dụ:

- Đặt hàng cần kiểm tra tồn kho, tính giá, áp mã giảm giá, ghi nhận thanh toán và phát sự kiện.
- Một request phải phối hợp nhiều repository hoặc gọi hệ thống bên ngoài.
- API công khai cần DTO riêng, quy tắc versioning, validation và cấu trúc response ổn định theo hợp đồng.
- Quyền đọc/ghi khác nhau theo trường dữ liệu hoặc theo từng trạng thái nghiệp vụ.
- Không muốn client thao tác trực tiếp với entity và repository nội bộ.

Hai cách tiếp cận có thể cùng tồn tại. Dùng Spring Data REST cho các repository resource đơn giản, còn dùng service và Spring MVC controller cho các use case nghiệp vụ. Giữ logic nghiệp vụ trong service giúp cả controller tự viết và luồng khác tái sử dụng cùng quy tắc.

## 5. Tùy chỉnh và kiểm soát việc export

Spring Data REST có các điểm mở rộng thường dùng:

- **@RepositoryRestResource(path = "...")** đổi đường dẫn resource; có thể đặt **exported = false** để không export repository.
- **@RestResource(path = "...", rel = "...")** tùy chỉnh search method hoặc association; có thể đặt **exported = false** để ẩn một method khỏi REST API.
- **RepositoryRestConfigurer** tùy chỉnh cấu hình chung như base path, cách export và một số quy tắc biểu diễn.
- **Projection** và excerpt projection giúp chọn các thuộc tính được hiển thị trong representation.
- Các cơ chế validation và event của Spring Data REST có thể tham gia vào vòng đời thao tác repository.

Projection chỉ điều chỉnh dữ liệu được biểu diễn; nó không thay thế kiểm soát truy cập. Nếu API có dữ liệu nhạy cảm, cần cấu hình authorization và kiểm tra quyền trên endpoint, repository/service và thao tác tương ứng.

Việc một repository được export có thể làm lộ cả thao tác ghi. Trước khi công bố API, hãy xác định rõ repository nào được phép truy cập, method nào được phép gọi và ai được phép đọc hoặc thay đổi dữ liệu. Không nên xem việc Spring Data REST tự tạo endpoint là một chính sách bảo mật.

## 6. Những nhầm lẫn thường gặp

1. **Spring Data không đồng nghĩa Spring Data REST.** Spring Data cung cấp abstraction truy cập dữ liệu; Spring Data REST là thành phần tùy chọn xuất repository thành REST resource.
2. **Spring MVC không phải lớp persistence.** MVC xử lý HTTP request/response; Spring Data và module store-specific xử lý truy cập dữ liệu.
3. **Spring Data REST không phải một repository implementation.** Nó gọi repository đã được Spring Data tạo và cung cấp cách truy cập repository qua HTTP.
4. **Spring HATEOAS không phải REST controller hay ORM.** Nó hỗ trợ tạo representation và link hypermedia.
5. **Có repository không có nghĩa phải export repository.** Một repository có thể chỉ được service sử dụng nội bộ.
6. **Có link không đồng nghĩa client được phép truy cập.** Authorization vẫn phải được kiểm tra khi client gọi endpoint đích.
7. **Không nên mặc định mọi association đều được nhúng thành object đầy đủ.** Spring Data REST thường cung cấp link đến association resource; representation cụ thể phụ thuộc cấu hình, projection và cách truy cập.
8. **Không nên để client phụ thuộc vào URI tự ghép nếu API đã cung cấp link.** Dùng relation trong HAL giúp client ít phụ thuộc vào cấu trúc URL nội bộ hơn.

## 7. Bảng ghi nhớ

| Thành phần | Trách nhiệm chính | Ví dụ dễ nhận biết |
|---|---|---|
| Spring Data | Abstraction truy cập dữ liệu | JpaRepository, CrudRepository |
| Spring Data REST | Xuất repository thành REST resource | @RepositoryRestResource, /people |
| Spring MVC | Xử lý request/response trên Servlet stack | DispatcherServlet, @RestController, @GetMapping |
| Spring HATEOAS | Tạo representation có hypermedia link | Link, EntityModel, CollectionModel, HAL |
| Spring Data JPA | Thực thi repository trên JPA | JpaRepository, entity mapping |

Khi đọc một ứng dụng Spring, hãy lần theo request từ controller hoặc Spring Data REST handler, đến service/repository, rồi đến module lưu trữ. Khi đọc response HAL, hãy phân biệt dữ liệu domain trong body với các link do Spring HATEOAS cung cấp. Nhìn theo trách nhiệm đó sẽ giúp xác định đúng nơi cần thêm endpoint, quy tắc nghiệp vụ, truy vấn dữ liệu hoặc link điều hướng.

## 8. Tài liệu chính thức

- Spring Data REST: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Repository abstraction: https://docs.spring.io/spring-data/commons/reference/repositories.html
- Spring Framework — Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring HATEOAS: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- Spring Boot — Spring Data REST: https://docs.spring.io/spring-boot/reference/data/nosql.html
