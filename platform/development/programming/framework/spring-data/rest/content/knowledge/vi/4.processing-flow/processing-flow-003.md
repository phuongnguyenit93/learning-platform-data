# Bộ xử lý tài nguyên tập hợp, tài nguyên đơn, liên kết và tìm kiếm trong Spring Data REST

## Mục tiêu

Spring Data REST tự động xuất các Spring Data repository thành REST API. Mỗi phản hồi thường là một mô hình hypermedia theo HAL: dữ liệu được đặt trong phần nội dung hoặc `_embedded`, còn các đường dẫn có thể điều hướng nằm trong `_links`.

Khi cần bổ sung một liên kết, điều chỉnh biểu diễn hoặc cung cấp đường dẫn tới chức năng riêng, ta có thể đăng ký **RepresentationModelProcessor** của Spring HATEOAS. Processor nhận mô hình mà Spring Data REST đã dựng, xử lý mô hình đó rồi trả lại trước khi phản hồi được tuần tự hóa.

Bài này phân biệt bốn điểm cần mở rộng: tài nguyên tập hợp, tài nguyên đơn, tài nguyên liên kết (association) và tài nguyên tìm kiếm. Ví dụ dùng API hiện đại `RepresentationModelProcessor`, `EntityModel` và `CollectionModel`. Với dự án cũ, tên API có thể khác; phần cuối có ghi chú chuyển đổi.

## 1. Bốn loại tài nguyên được xuất

Giả sử ứng dụng quản lý `Person`, mỗi người có một `Department` và nhiều `Role`. Repository có thể được khai báo như sau:

~~~java
@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("lastName") String lastName,
            Pageable pageable);
}
~~~

Nếu base path của Spring Data REST là `/api`, các URL tiêu biểu là:

| Loại tài nguyên | URL ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tập hợp (collection) | `GET /api/people` | Danh sách người; có thể có phân trang và sắp xếp. `POST` tạo một người mới. |
| Đơn (item) | `GET /api/people/42` | Một người cụ thể. Thường hỗ trợ `GET`, `PUT`, `PATCH`, `DELETE`. |
| Liên kết (association) | `GET /api/people/42/department` | Theo một quan hệ từ người sang phòng ban. |
| Liên kết dạng tập hợp | `GET /api/people/42/roles` | Theo quan hệ có nhiều phần tử. |
| Tìm kiếm (search) | `GET /api/people/search` | Danh sách liên kết tới các query method được xuất. |
| Query method | `GET /api/people/search/by-last-name?lastName=Nguyen` | Thực thi một truy vấn cụ thể. |

Các tài nguyên này được khám phá qua liên kết. Ví dụ, tài nguyên gốc có liên kết tới `people`; tài nguyên tập hợp có liên kết `search` nếu repository có query method; tài nguyên đơn có các liên kết mang tên thuộc tính quan hệ. Client nên đi theo các liên kết HAL nhận được thay vì tự ghép URL theo quy ước.

Một phản hồi tập hợp có thể có dạng rút gọn như sau:

~~~json
{
  "_links": {
    "self": { "href": "http://localhost:8080/api/people" },
    "search": { "href": "http://localhost:8080/api/people/search" }
  },
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": { "href": "http://localhost:8080/api/people/42" },
          "department": {
            "href": "http://localhost:8080/api/people/42/department"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

## 2. RepresentationModelProcessor hoạt động như thế nào?

`org.springframework.hateoas.server.RepresentationModelProcessor<T>` là extension point để xử lý một `RepresentationModel`. Phương thức `process(T model)` nhận mô hình hiện có, có thể thêm liên kết hoặc thay đổi nội dung phù hợp, rồi phải trả lại mô hình.

Spring phát hiện processor được đăng ký dưới dạng bean, chẳng hạn bằng `@Component` hoặc `@Bean`. Kiểu generic `T` cho biết processor nhắm tới loại mô hình nào. Vì vậy, hãy chọn đúng kiểu mô hình mà endpoint trả về:

- `EntityModel<T>`: mô hình cho một entity.
- `CollectionModel<T>`: mô hình cho một tập hợp entity.
- `PagedModel<T>`: mô hình tập hợp có metadata phân trang; đây là một dạng collection model.
- `RepositorySearchesResource`: mô hình riêng mà Spring Data REST dùng cho trang liệt kê các query method.

Spring Data REST dùng `PersistentEntityResource` để biểu diễn entity repository. Kiểu này kế thừa `EntityModel`, đồng thời giữ metadata của persistent entity. Vì thế processor cho `EntityModel<Person>` là cách mở rộng phổ biến cho tài nguyên đơn.

Processor chỉ nên làm công việc của lớp biểu diễn: thêm liên kết, bổ sung affordance hoặc điều chỉnh mô hình đầu ra. Nếu cần tự xây dựng hoàn toàn một representation trong controller, hãy xem `RepresentationModelAssembler`; nếu cần thay đổi truy vấn hoặc nghiệp vụ, hãy xử lý ở repository/service/controller tương ứng.

## 3. Xử lý tài nguyên đơn

Một tài nguyên đơn thường là `EntityModel<Person>` (bên trong Spring Data REST có thể là `PersistentEntityResource`). Processor dưới đây thêm liên kết `export` vào mọi representation của `Person`:

~~~java
@Component
public class PersonItemProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.add(Link.of("/api/people/export").withRel("export"));
        return model;
    }
}
~~~

Trong ứng dụng thực tế, endpoint `/api/people/export` phải tồn tại và được bảo vệ theo chính sách truy cập của ứng dụng. Nên tạo link bằng `WebMvcLinkBuilder.linkTo(methodOn(...))` hoặc API link phù hợp khi cần tránh cố định host và đường dẫn. Nếu ứng dụng cấu hình base path, hãy kiểm tra link sinh ra có bao gồm base path đó.

Một processor có thể được giới hạn theo kiểu entity bằng generic như trên. Điều này tránh việc thêm link dành cho Person vào representation của những domain type khác.

## 4. Xử lý tài nguyên tập hợp

Tài nguyên tập hợp được biểu diễn bằng `CollectionModel`; kết quả phân trang thường dùng `PagedModel`, vốn kế thừa collection model. Có thể thêm một liên kết chung cho tập hợp bằng processor sau:

~~~java
@Component
public class PeopleCollectionProcessor
        implements RepresentationModelProcessor<
                CollectionModel<PersistentEntityResource>> {

    @Override
    public CollectionModel<PersistentEntityResource> process(
            CollectionModel<PersistentEntityResource> model) {

        boolean containsPerson = model.getContent().stream()
                .anyMatch(resource -> resource.getPersistentEntity()
                        .getType().equals(Person.class));

        if (containsPerson) {
            model.add(Link.of("/api/people/summary").withRel("summary"));
        }

        return model;
    }
}
~~~

Ở đây processor kiểm tra metadata của phần tử để chỉ thêm liên kết khi tập hợp chứa Person. Vì kiểm tra dựa trên phần tử, một tập hợp rỗng không thể được nhận diện theo cách này. Nếu cần xử lý cả trang rỗng, hãy dựa vào liên kết `self`/mapping đã cấu hình để nhận diện collection hoặc đưa logic riêng vào endpoint tương ứng.

Liên kết thêm vào collection model nằm ở cấp tập hợp; nó không tự động được thêm vào từng phần tử. Nếu muốn mỗi Person có một liên kết riêng, dùng processor `EntityModel<Person>` ở phần trước.

## 5. Xử lý tài nguyên liên kết (association)

Association là sub-resource được tạo từ thuộc tính quan hệ của entity. Ví dụ:

~~~java
@Entity
public class Person {

    @ManyToOne
    @RestResource(path = "department", rel = "department")
    private Department department;

    @ManyToMany
    @RestResource(path = "roles", rel = "roles")
    private Set<Role> roles = new HashSet<>();
}
~~~

Tên đường dẫn và relation mặc định lấy từ tên thuộc tính; `@RestResource` trên thuộc tính cho phép đổi tên hoặc đặt `exported = false` để không xuất association đó.

Association một-một hoặc nhiều-một trả về representation của một entity; association một-nhiều hoặc nhiều-nhiều trả về representation dạng tập hợp. Do đó, processor xử lý association thường vẫn dùng các kiểu mô hình đã gặp:

- Association đơn: processor cho `EntityModel<Department>` hoặc kiểu entity đích tương ứng.
- Association nhiều phần tử: processor cho `CollectionModel<PersistentEntityResource>` hoặc kiểu collection phù hợp.

**Không có một kiểu public riêng tên là `AssociationResource` để dùng làm generic cho mọi association trong API hiện đại.** Representation của association dùng lại mô hình entity/tập hợp. Vì vậy, processor nhắm tới kiểu entity đích có thể chạy cho cả endpoint item của entity đó lẫn endpoint association trả về entity đó. Nếu cần phân biệt theo đúng URL association, hãy dựa trên self link/mapping hoặc tạo endpoint tùy chỉnh có logic riêng; đừng giả định generic type tự phân biệt được hai route.

Các thao tác association cũng khác nhau theo cardinality. `GET` đọc quan hệ; `PUT` gắn URI của tài nguyên đích; `POST` chỉ áp dụng cho association dạng tập hợp để thêm phần tử; `DELETE` gỡ liên kết. Với `PUT` và `POST`, payload tiêu chuẩn là `text/uri-list`. Một association đơn không thể nhận nhiều URI trong cùng yêu cầu `PUT`.

Nếu mục tiêu chỉ là đổi tên link quan hệ trên representation của Person, cấu hình `@RestResource` trên thuộc tính thường rõ ràng hơn việc viết processor. Dùng processor khi cần thêm hành vi biểu diễn vượt quá metadata mapping mặc định.

## 6. Xử lý tài nguyên tìm kiếm

`GET /people/search` trả về các liên kết tới query method đã được export. Đây là trang chỉ mục tìm kiếm, không phải kết quả của một truy vấn cụ thể. Spring Data REST dùng kiểu `RepositorySearchesResource` cho representation này.

Ta có thể đăng ký processor riêng và kiểm tra domain type bằng `getDomainType()`:

~~~java
@Component
public class PersonSearchProcessor
        implements RepresentationModelProcessor<RepositorySearchesResource> {

    @Override
    public RepositorySearchesResource process(
            RepositorySearchesResource model) {

        if (model.getDomainType().equals(Person.class)) {
            model.add(Link.of("/api/people/search/recent{?days}")
                    .withRel("recent"));
        }

        return model;
    }
}
~~~

Đường dẫn `/api/people/search/recent` trong ví dụ phải trỏ tới một custom search endpoint thực sự. Trong ứng dụng có base path khác, hãy sinh URL từ mapping của controller hoặc cấu hình tương ứng thay vì giữ chuỗi cố định.

Với query method nằm trực tiếp trên repository, thường không cần tự thêm link: dùng `@RestResource(path = "by-last-name", rel = "byLastName")` để điều chỉnh path và relation. Processor tìm kiếm hữu ích khi muốn công bố thêm liên kết tới chức năng tìm kiếm tùy chỉnh, chẳng hạn endpoint được triển khai bằng `@BasePathAwareController`.

Processor cho `RepositorySearchesResource` chỉ xử lý trang chỉ mục `/search`. Kết quả của query method có thể là một entity hoặc collection; khi đó processor entity/collection tương ứng mới là nơi bổ sung liên kết cho kết quả.

## 7. Đăng ký nhiều processor và giới hạn phạm vi

Có thể đăng ký nhiều processor trong cùng application context. Mỗi processor nên có kiểu generic rõ ràng và chỉ thay đổi phần representation mà nó sở hữu.

Một số nguyên tắc thực tế:

1. Dùng generic cụ thể như `EntityModel<Person>` hoặc `RepositorySearchesResource` khi có thể; tránh processor quá rộng làm thay đổi mọi response.
2. Nếu dùng processor collection chung, lọc theo metadata entity hoặc self link. Nhớ xử lý trường hợp collection rỗng.
3. Chọn relation name ổn định, duy nhất và có ý nghĩa với client. Không ghi đè `self`, `search` hoặc relation mặc định nếu không có lý do rõ ràng.
4. Chỉ thêm link tới endpoint thực sự tồn tại. Link hypermedia giúp khám phá API, nhưng không thay thế kiểm tra quyền ở endpoint.
5. Tránh truy vấn database tốn kém cho từng phần tử trong processor. Nếu dữ liệu cần thiết không có sẵn, cân nhắc assembler hoặc endpoint chuyên biệt.
6. Kiểm tra cả response collection, item, association đơn, association nhiều phần tử, trang search và query result. Cùng một kiểu representation có thể được dùng ở nhiều route.

## 8. Kiểm thử

Có thể dùng Spring MVC Test/MockMvc để gọi endpoint và kiểm tra HAL JSON. Những điểm cần xác nhận:

- `GET /api/people`: link cấp collection xuất hiện đúng relation; metadata phân trang vẫn còn.
- `GET /api/people/42`: link do item processor thêm xuất hiện trong `_links`.
- `GET /api/people/42/department` và `GET /api/people/42/roles`: representation association vẫn đúng dạng entity hoặc collection và không mất link mặc định.
- `GET /api/people/search`: link tùy chỉnh chỉ xuất hiện cho domain type Person.
- `GET /api/people/search/by-last-name`: query method vẫn nhận đúng tham số và trả kết quả như mong đợi.
- Khi thay đổi base path, các link tùy chỉnh vẫn trỏ tới đúng endpoint.

Ví dụ kiểm tra một relation bằng JSONPath:

~~~java
mockMvc.perform(get("/api/people/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.export.href").exists());
~~~

Nên kiểm tra nội dung và status code của endpoint đích riêng biệt. Việc link xuất hiện trong JSON không chứng minh endpoint đã được triển khai hoặc người gọi có quyền truy cập.

## 9. API cũ và API hiện đại

Các dự án Spring Data REST/Spring HATEOAS cũ có thể gặp những tên kiểu sau:

| API cũ | API hiện đại |
| --- | --- |
| `ResourceProcessor<T>` | `RepresentationModelProcessor<T>` |
| `Resource<T>` | `EntityModel<T>` |
| `Resources<T>` | `CollectionModel<T>` |
| `PagedResources<T>` | `PagedModel<T>` |
| `ResourceSupport` | `RepresentationModel<?>` |

Dùng đúng import và kiểu generic theo phiên bản Spring Boot/Spring Data mà dự án đang quản lý. Không trộn API cũ và mới trong cùng một ví dụ. Khi nâng cấp, hãy kiểm tra cả package import, kiểu trả về controller và kiểu generic của processor.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): mô tả collection, item, association, search và query method resources.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): tùy chỉnh repository exposure và HTTP method exposure.
- [Spring Data REST — Integration](https://docs.spring.io/spring-data/rest/reference/integration.html): tạo link tới collection, item và search resource bằng `RepositoryEntityLinks`.
- [Spring Data REST API — RepositorySearchesResource](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositorySearchesResource.html): kiểu representation dành cho search resource.
- [Spring HATEOAS API — RepresentationModelProcessor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html): hợp đồng `process(model)` để xử lý representation model.
