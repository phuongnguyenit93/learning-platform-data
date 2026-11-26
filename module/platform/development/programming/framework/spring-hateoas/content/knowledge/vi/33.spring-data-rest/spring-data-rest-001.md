# Spring Data REST và HATEOAS

Spring Data REST giúp công bố các Spring Data repository thành REST resource mà không phải tự viết controller CRUD cho từng aggregate. Framework tạo endpoint collection, endpoint item, hỗ trợ phân trang, tìm kiếm, quan hệ giữa tài nguyên và biểu diễn hypermedia. Spring Data REST tích hợp Spring HATEOAS để client khám phá API thông qua các link; định dạng mặc định phổ biến là HAL JSON.

Điều này phù hợp với các API có cấu trúc tài nguyên gần với repository và cần một cách nhanh chóng, nhất quán để công bố thao tác CRUD. Tuy nhiên, repository export không tự động tạo ra một API nghiệp vụ hoàn chỉnh. Bạn vẫn cần quyết định repository nào được công khai, trường dữ liệu nào được hiển thị, thao tác nào được phép, cách bảo vệ endpoint và khi nào cần custom controller.

## 1. Spring Data REST là gì?

Spring Data REST là một phần của hệ sinh thái Spring Data, có nhiệm vụ xuất bản repository thành REST API. Thay vì viết controller cho từng thao tác đọc, tạo, cập nhật và xóa, bạn khai báo repository và cấu hình cách framework công bố nó.

Ví dụ, repository quản lý `Person` có thể tự động cung cấp:

- Collection resource để liệt kê và tạo người.
- Item resource để đọc, cập nhật hoặc xóa một người.
- Search resource cho các query method được export.
- Link tới các association resource.
- Pagination links và page metadata khi repository hỗ trợ phân trang.

Spring Data REST sử dụng Spring HATEOAS để biểu diễn các resource dưới dạng hypermedia. Client có thể bắt đầu từ root endpoint, đọc link để tìm collection, rồi tiếp tục theo relation để truy cập item, search hoặc association.

## 2. Thêm dependency

Với ứng dụng Spring Boot dùng Spring Data JPA, dependency thường gồm starter JPA và starter Data REST:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
</dependencies>
```

Spring Boot quản lý phiên bản tương thích thông qua dependency management. Ứng dụng vẫn cần cấu hình datasource và dependency driver phù hợp với database đang sử dụng.

Spring Data REST không thay thế Spring Data JPA hoặc MongoDB repository module. Nó sử dụng repository được cung cấp bởi module lưu trữ tương ứng và xuất bản chúng qua HTTP.

## 3. Tạo repository và công bố resource

Giả sử ứng dụng có entity đơn giản:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
```

Khai báo repository:

```java
@RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
```

Khi repository được phát hiện và export, Spring Data REST tạo collection resource tại `/people` và item resource tại `/people/{id}`. `path` xác định URI path; `collectionResourceRel` xác định relation của collection trong HAL.

Nếu không chỉ định, framework suy ra path và relation từ kiểu domain/repository. Với API được client sử dụng lâu dài, nên đặt tên tường minh để tránh thay đổi ngoài ý muốn khi refactor tên class.

## 4. Collection resource và item resource

Với repository ở trên, các endpoint cơ bản thường có dạng:

| Resource | URI | Mục đích |
| --- | --- | --- |
| Collection | `GET /people` | Đọc danh sách người. |
| Collection | `POST /people` | Tạo người mới từ request body. |
| Item | `GET /people/{id}` | Đọc một người. |
| Item | `PUT /people/{id}` | Thay thế representation theo semantics được hỗ trợ. |
| Item | `PATCH /people/{id}` | Cập nhật một phần nếu được hỗ trợ/cấu hình. |
| Item | `DELETE /people/{id}` | Xóa người. |

Các method HTTP được export phụ thuộc vào method repository có sẵn và cấu hình exposure. Ví dụ, nếu repository không cung cấp thao tác xóa hoặc method đó bị ẩn, endpoint DELETE tương ứng sẽ không được cung cấp.

Spring Data REST tạo resource từ repository contract. Hãy kiểm tra các method thực tế được công bố thay vì giả định mọi repository luôn có đầy đủ CRUD.

## 5. Khám phá API từ root bằng HAL

Client có thể bắt đầu bằng request GET tới root của Spring Data REST application:

```http
GET / HTTP/1.1
Accept: application/hal+json
```

Response root thường chứa các link tới repository resource đã export, ví dụ:

```json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
```

Từ link `people`, client gửi GET để đọc collection. HAL thường đặt item trong `_embedded` và các link điều hướng trong `_links`:

```json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    }
  }
}
```

Ví dụ rút gọn trên minh họa cấu trúc HAL; response thực tế có thể có thêm `profile`, `search`, page metadata và các relation association. Client nên đọc relation từ response thay vì tự ghép URI từ tên entity.

## 6. Pagination và sorting được tích hợp

Nếu repository hỗ trợ `PagingAndSortingRepository` hoặc `JpaRepository`, collection resource có thể nhận query parameter phân trang và sắp xếp:

```http
GET /people?page=0&size=20&sort=lastName,asc
Accept: application/hal+json
```

Các tham số thường dùng:

| Tham số | Ý nghĩa |
| --- | --- |
| `page` | Chỉ số trang, mặc định bắt đầu từ `0`. |
| `size` | Số phần tử yêu cầu trong một trang. |
| `sort` | Thuộc tính và hướng sắp xếp, ví dụ `lastName,asc`. |

HAL response có thể chứa `_embedded`, các link `first`, `prev`, `self`, `next`, `last` khi phù hợp và object `page` với `size`, `number`, `totalElements`, `totalPages`.

Đặt default và maximum page size phù hợp trong cấu hình Spring Data REST/Web để giới hạn tài nguyên. Không dựa vào giao diện client để ngăn request có size quá lớn. Hãy kiểm thử cả page metadata và URI của link tiếp theo.

## 7. Export query method thành search resource

Spring Data REST có thể xuất bản các query method của repository thành search endpoint. Ví dụ:

```java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastName(
            @Param("name") String lastName,
            Pageable pageable);
}
```

Client có thể khám phá search link trong collection và gọi:

```http
GET /people/search/by-last-name?name=Nguyen&page=0&size=10
Accept: application/hal+json
```

`path` tùy chỉnh URI của search method; `rel` đặt relation của link; `@Param` xác định tên query parameter. Nếu không tùy chỉnh, Spring Data REST có thể suy ra path và relation từ tên query method.

Không phải mọi method trong repository đều nên được công khai. Query method chỉ nên export nếu client thực sự cần khả năng đó và đầu vào đã được thiết kế như một phần hợp đồng API.

## 8. Association được biểu diễn bằng link

Giả sử một người có địa chỉ:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne
    private Address address;

    // Các thuộc tính và accessor khác.
}
```

Nếu `Address` được export thành repository resource phù hợp, representation của `Person` có thể công bố link association `address`:

```json
{
  "firstName": "An",
  "_links": {
    "self": {
      "href": "/people/1"
    },
    "address": {
      "href": "/people/1/address"
    }
  }
}
```

Client theo link `address` để đọc hoặc tương tác với association resource theo các HTTP method mà Spring Data REST hỗ trợ cho cardinality và cấu hình tương ứng. Điều này giúp tránh serialize toàn bộ object graph hai chiều vào một response.

Link association không nhất thiết có nghĩa dữ liệu liên quan đã được nhúng. Nếu client cần dữ liệu địa chỉ ngay trong response, hãy cân nhắc projection/excerpt thay vì giả định mọi quan hệ JPA sẽ tự động inline.

## 9. Projections và excerpt projections

Mặc định, Spring Data REST trình bày các thuộc tính của domain type được export. Nếu cần một view gọn hơn, có thể khai báo projection:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
```

Client có thể yêu cầu projection qua query parameter:

```http
GET /people/1?projection=summary
Accept: application/hal+json
```

Projection interface phải được Spring Data REST phát hiện, thường bằng cách đặt trong cùng package với domain type hoặc package con; cũng có thể đăng ký tường minh qua cấu hình projection.

Excerpt projection là projection được áp dụng mặc định cho item khi chúng được hiển thị trong collection hoặc quan hệ liên quan. Có thể khai báo trên repository:

```java
@RepositoryRestResource(excerptProjection = PersonSummary.class)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
```

Excerpt projection được thiết kế cho bản xem trước trong collection; nó không tự động áp dụng cho item resource khi gọi `/people/{id}`. Client có thể yêu cầu projection cụ thể ở item resource bằng query parameter.

Thay đổi excerpt projection có thể thay đổi payload collection mà client đang sử dụng. Hãy xem đó là thay đổi hợp đồng và kiểm thử tương thích trước khi phát hành.

## 10. Tùy chỉnh path và collection relation

`@RepositoryRestResource` cho phép tùy chỉnh path và relation:

```java
@RepositoryRestResource(
        collectionResourceRel = "customers",
        path = "customers"
)
public interface CustomerRepository extends JpaRepository<Customer, UUID> {
}
```

Trong đó:

- `path = "customers"` tạo đường dẫn collection `/customers`.
- `collectionResourceRel = "customers"` xác định relation của collection trong HAL.
- Item resource thường nằm dưới `/customers/{id}`.

Giữ relation ổn định ngay cả khi đổi tên repository hoặc class entity. Client hypermedia nên phụ thuộc vào relation và `href`, không phụ thuộc vào tên Java.

## 11. Đổi base path và cấu hình RepositoryRestConfigurer

Có thể đặt base path bằng cấu hình Spring Boot:

```yaml
spring:
  data:
    rest:
      base-path: /api
```

Khi đó repository resources được đặt dưới `/api`, ví dụ `/api/people`. Client vẫn nên bắt đầu từ root endpoint được công bố và theo các link, thay vì tự gắn prefix.

Nếu cần cấu hình bằng Java, có thể đăng ký `RepositoryRestConfigurer`:

```java
@Configuration
class DataRestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
```

Configurer cung cấp các hook để tùy chỉnh repository detection, exposure, conversion, CORS và các khía cạnh khác của Spring Data REST. Chỉ bật những thay đổi cần thiết và kiểm thử URI thực tế sau khi cấu hình.

## 12. Ẩn repository method hoặc toàn bộ repository

Không phải repository method nào cũng nên trở thành endpoint. Có thể ẩn một query method:

```java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(exported = false)
    List<Person> findByInternalFlag(boolean internalFlag);
}
```

Có thể tắt export toàn bộ repository:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, UUID> {
}
```

Điều này giúp giới hạn bề mặt API. Tuy nhiên, ẩn một link hoặc endpoint không thay thế Spring Security. Mọi request tới resource được export vẫn phải được xác thực, phân quyền và kiểm tra dữ liệu ở server.

Hãy rà soát cả CRUD method mặc định, search method, association resource và các repository được phát hiện tự động. Repository nội bộ không nên vô tình trở thành API công khai chỉ vì nó nằm trong package được scan.

## 13. Thêm link dùng chung bằng RepresentationModelProcessor

Spring Data REST tích hợp Spring HATEOAS và có thể áp dụng các bean `RepresentationModelProcessor` để bổ sung link vào representation được export.

Ví dụ thêm link hướng dẫn cho `Person`:

```java
@Component
class PersonModelProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.add(Link.of("/docs/people", "help"));
        return model;
    }
}
```

Trong ứng dụng thực tế, nên tạo URI từ controller mapping bằng `WebMvcLinkBuilder` thay vì hard-code host hoặc path. Processor phù hợp với link dùng chung cho mọi representation thuộc kiểu model được nhắm tới; link đặc thù một endpoint có thể được tạo ở custom controller hoặc assembler.

Nếu processor được áp dụng tự động, hãy kiểm thử response Spring Data REST qua HTTP để xác nhận link xuất hiện đúng. Gọi trực tiếp `process(...)` chỉ kiểm tra logic processor, chưa chứng minh exporter đã áp dụng bean trong response.

## 14. Bổ sung endpoint nghiệp vụ bằng custom controller

Spring Data REST phù hợp với CRUD resource theo repository. Khi cần endpoint không ánh xạ trực tiếp thành repository method, có thể bổ sung controller riêng.

Ví dụ dùng `@RepositoryRestController` để tạo endpoint gắn với base path Spring Data REST:

```java
@RepositoryRestController
class PersonSummaryController {

    private final PersonRepository repository;

    PersonSummaryController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/{id}/summary")
    @ResponseBody
    ResponseEntity<PersonSummaryView> summary(@PathVariable Long id) {
        return repository.findById(id)
                .map(person -> ResponseEntity.ok(
                        new PersonSummaryView(
                                person.getFirstName(),
                                person.getLastName())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

`@RepositoryRestController` tích hợp controller với hạ tầng Spring Data REST và base path. Với controller MVC thông thường, route và message converter có thể nằm ngoài phạm vi cấu hình của exporter. Hãy chọn annotation phù hợp với mục tiêu tích hợp và kiểm thử đường dẫn cuối cùng.

Nếu endpoint trả một DTO thuần, hãy cân nhắc thêm link hypermedia bằng `EntityModel` hoặc `RepresentationModel` để client có thể tiếp tục điều hướng theo cùng phong cách API.

## 15. Validation và sự kiện repository

Spring Data REST hỗ trợ tích hợp với Bean Validation. Có thể đặt annotation như `@NotBlank`, `@Email`, `@Size` trên thuộc tính hoặc dùng validator tùy chỉnh để kiểm tra dữ liệu trước khi lưu.

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Size(max = 80)
    private String firstName;

    @Email
    private String email;
}
```

Spring Data REST cũng cung cấp repository event handler để xử lý các giai đoạn như trước/sau create, save hoặc delete. Dùng event handler cho logic phù hợp với vòng đời repository, nhưng tránh nhồi toàn bộ quy tắc nghiệp vụ phức tạp vào listener. Những quy trình cần transaction orchestration hoặc nhiều bước nên được đặt trong service và công bố qua custom endpoint.

Validation metadata và lỗi trả về cần được kiểm thử qua request HTTP thực tế. Không dựa vào client để thực thi các annotation validation.

## 16. Bảo mật API repository export

Repository export làm cho các method repository có thể truy cập qua HTTP. Điều đó không có nghĩa mọi người dùng đều được phép gọi mọi method.

Khi đưa Spring Data REST vào ứng dụng, cần:

- Bật xác thực và phân quyền bằng Spring Security.
- Giới hạn HTTP method và repository resource theo vai trò người dùng.
- Kiểm tra quyền truy cập theo từng bản ghi hoặc tenant, không chỉ theo URL.
- Ẩn repository và query method nội bộ bằng cấu hình export phù hợp.
- Kiểm tra association resource vì nó cũng có thể cho phép đọc hoặc thay đổi quan hệ.
- Không công bố field nhạy cảm chỉ vì entity có getter.
- Kiểm thử request trực tiếp tới endpoint kể cả khi link không được hiển thị.

HATEOAS giúp client khám phá khả năng được công bố, nhưng link không phải cơ chế authorization. Server phải bảo vệ mọi endpoint độc lập với response trước đó.

## 17. Kiểm thử Spring Data REST bằng MockMvc

Có thể dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để kiểm tra exporter cùng repository thực tế:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRepositoryRestTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    PersonRepository repository;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
        repository.save(new Person("An", "Nguyen"));
    }

    @Test
    void exposesPeopleCollectionAsHal() throws Exception {
        mockMvc.perform(get("/people")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.people").isArray());
    }
}
```

Ví dụ giả định collection relation đã được đặt thành `people`. Nếu ứng dụng có base path, hãy gọi `/api/people`. Nếu security được bật, test cần cấu hình người dùng hoặc authentication phù hợp.

Nên kiểm thử thêm:

- Root endpoint có link tới repository đã export.
- Item resource có self link.
- Search method xuất hiện dưới relation `search` và trả đúng kết quả.
- Pagination links và `page` metadata đúng.
- Association link trỏ đúng resource.
- Projection và excerpt projection chỉ công bố trường dự kiến.
- Repository hoặc method `exported = false` không xuất hiện.
- Request không có quyền bị từ chối kể cả khi gọi URI trực tiếp.

## 18. Khi nào nên dùng Spring Data REST?

Spring Data REST phù hợp khi:

- API gần với aggregate và repository model.
- CRUD là phần lớn thao tác cần công bố.
- Cần nhanh chóng tạo API hypermedia nhất quán.
- Client có thể tiêu thụ HAL và khám phá resource bằng link.
- Dữ liệu có thể được điều chỉnh bằng projection, excerpt và repository configuration.

Custom Spring MVC controller với Spring HATEOAS có thể phù hợp hơn khi:

- Endpoint thể hiện use case nghiệp vụ thay vì CRUD trực tiếp.
- Một thao tác phối hợp nhiều aggregate hoặc nhiều service.
- Request/response cần DTO và semantics riêng.
- Quyền truy cập và quy tắc trạng thái phức tạp.
- Cần kiểm soát chặt chẽ HTTP contract, status code hoặc workflow.

Hai cách có thể cùng tồn tại. Spring Data REST công bố các resource CRUD ổn định; custom controller cung cấp các thao tác nghiệp vụ và vẫn có thể dùng Spring HATEOAS để tạo link tới repository resource.

## 19. Các lỗi thường gặp

**Cho rằng mọi repository đều nên export.** Rà soát repository detection và chỉ công bố interface cần thiết.

**Xem Spring Data REST là CRUD controller không cần thiết kế API.** Path, relation, projection, association và exposure đều là một phần hợp đồng cần quyết định.

**Trả entity với mọi field mặc định.** Kiểm tra dữ liệu được công khai; dùng projection hoặc custom representation khi cần giới hạn trường.

**Nhầm association link với embedded resource.** Link dẫn tới association endpoint; projection/excerpt có thể đưa dữ liệu liên quan vào response.

**Cho rằng excerpt projection tự áp dụng cho item resource.** Excerpt chủ yếu áp dụng khi item nằm trong collection hoặc resource liên quan; item endpoint cần projection được yêu cầu rõ.

**Ẩn link rồi nghĩ endpoint đã được bảo vệ.** Security phải kiểm tra request trực tiếp ở server.

**Dùng Spring Data REST cho workflow nhiều bước.** Chuyển quy trình nghiệp vụ phức tạp sang service và custom controller.

**Hard-code URI trong processor.** Dùng link builder theo controller mapping và kiểm thử URI sau base path/proxy.

**Không kiểm tra thay đổi excerpt hoặc relation.** Đây là thay đổi hợp đồng có thể ảnh hưởng client đang chạy.

## 20. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng API quản lý người dùng bằng Spring Data REST:

1. Tạo entity `Person` và repository `PersonRepository` kế thừa `JpaRepository`.
2. Dùng `@RepositoryRestResource` để đặt path `people` và collection relation `people`.
3. Gọi root endpoint với HAL JSON và khám phá link tới collection.
4. Đọc collection, item và tạo một item bằng request phù hợp.
5. Thêm query method `findByLastName` với `@RestResource` và `@Param`.
6. Kiểm tra search link và kết quả lọc.
7. Thêm association tới `Address` và xác nhận association link.
8. Tạo projection `PersonSummary` và excerpt projection cho collection.
9. Cấu hình base path `/api` và xác nhận link được cập nhật.
10. Ẩn một repository method nội bộ và bảo vệ các endpoint bằng Spring Security.
11. Thêm một `RepresentationModelProcessor` để công bố link trợ giúp.
12. Viết MockMvc test cho root, collection, item, search, projection và security.

Bạn đã hiểu Spring Data REST và HATEOAS khi có thể giải thích cách repository trở thành REST resource, khám phá API từ root HAL, dùng search và association link, kiểm soát representation bằng projection, cấu hình export, bổ sung processor/custom controller và bảo vệ endpoint. Hãy chọn Spring Data REST cho resource CRUD phù hợp và kết hợp custom controller khi cần diễn đạt use case nghiệp vụ rõ ràng.

## Tài liệu tham khảo chính thức

- [Spring Data REST Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST – Repository resources and discoverability](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST – Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
