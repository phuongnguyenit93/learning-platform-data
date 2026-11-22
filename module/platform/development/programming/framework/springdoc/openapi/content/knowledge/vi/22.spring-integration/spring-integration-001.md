# Spring Data REST và endpoint được tạo từ repository

## 1. Spring Data REST tạo API từ repository như thế nào?

Spring Data REST tự động xuất bản các repository Spring Data thành REST resources. Thay vì viết controller cho từng thao tác CRUD, ứng dụng khai báo repository interface; Spring Data REST phát hiện repository và tạo các endpoint HTTP tương ứng.

Ví dụ, repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

có thể tạo collection resource để đọc danh sách, tạo sản phẩm, truy cập từng sản phẩm, cập nhật và xóa tài nguyên. Các endpoint cụ thể phụ thuộc repository được export, cấu hình base path, loại repository và các annotation tùy chỉnh.

Springdoc OpenAPI có thể tạo tài liệu cho các endpoint này cùng với endpoint được khai báo bằng Spring MVC controller. Đây là điểm cần chú ý: operation có thể được sinh từ Spring Data REST handler mapping dù trong source code không có một phương thức controller tương ứng.

Để tài liệu chính xác, cần hiểu cả ba lớp:

1. **Repository** định nghĩa khả năng truy cập dữ liệu và các query method.
2. **Spring Data REST** quyết định resource, URL, HTTP method, HAL representation và quy tắc export.
3. **Springdoc OpenAPI** mô tả các operation được ứng dụng expose thành OpenAPI document.

Bài này tập trung vào việc mô tả các endpoint được tạo từ repository, cách tùy biến resource và cách kiểm tra tài liệu do Springdoc sinh ra.

## 2. Thêm dependency và bật Spring Data REST

Với ứng dụng Spring Boot dùng Spring MVC và Spring Data JPA, các dependency thường có dạng:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:<compatible-version>")

    runtimeOnly("com.mysql:mysql-connector-j")
}
~~~

Spring Data REST cung cấp repository exporter; Springdoc starter cung cấp OpenAPI endpoint và Swagger UI. Chọn phiên bản Springdoc tương thích với dòng Spring Boot và Spring Framework đang dùng. Với Spring Boot 3, dùng dòng Springdoc 2.x; dự án Spring Boot 2 cần chọn dòng Springdoc tương thích tương ứng.

Nếu ứng dụng chỉ cần OpenAPI JSON/YAML mà không cần Swagger UI, có thể chọn starter API thay cho starter UI phù hợp với web stack.

Trong các phiên bản Springdoc hỗ trợ thuộc tính bật/tắt Spring Data REST, có thể khai báo:

~~~yaml
springdoc:
  enable-data-rest: true
~~~

Hãy kiểm tra thuộc tính và giá trị mặc định theo đúng phiên bản Springdoc của dự án. Nếu repository endpoints không xuất hiện trong tài liệu, cần xác minh dependency, web stack, cấu hình scan và khả năng tích hợp của phiên bản đang dùng.

## 3. Repository được export thành resource

Ví dụ domain và repository:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private BigDecimal price;

    // getters and setters
}
~~~

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Nếu repository được Spring Data REST export, ứng dụng có thể expose collection resource theo tên mặc định suy ra từ domain type. Để kiểm soát URL và relation name, dùng @RepositoryRestResource:

~~~java
@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products",
    itemResourceRel = "product"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Với cấu hình này, collection resource có path /products. Item resource được truy cập dưới dạng /products/{id}. Tên collection và item relation được dùng trong HAL links và embedded representation.

Nếu ứng dụng đặt base path:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

các resource sẽ nằm dưới /api, ví dụ /api/products. Cần bảo đảm Springdoc mô tả đúng base path và các client dùng đúng URL.

Không nên dựa vào cách pluralize tên domain để viết client hoặc security rule. Nếu URL là hợp đồng công khai, hãy đặt path tường minh bằng @RepositoryRestResource và kiểm tra đường dẫn runtime.

## 4. Các endpoint CRUD thường được tạo

Với repository export tiêu chuẩn, Spring Data REST có thể cung cấp các thao tác phổ biến:

| Resource | HTTP method | Mục đích |
|---|---|---|
| /api/products | GET | Đọc collection |
| /api/products | POST | Tạo item mới |
| /api/products/{id} | GET | Đọc một item |
| /api/products/{id} | PUT | Thay thế item |
| /api/products/{id} | PATCH | Cập nhật một phần item |
| /api/products/{id} | DELETE | Xóa item |

Bảng trên mô tả các operation thường gặp; endpoint thực tế còn phụ thuộc repository method được export, cấu hình exposure, kiểu ID, validation, event handler và custom repository behavior.

Spring Data REST có thể trả status và header khác nhau theo thao tác, ví dụ Location khi tạo resource. OpenAPI nên phản ánh response thực tế của ứng dụng, bao gồm status code, media type, headers và body.

Springdoc có thể phát hiện operation từ handler mapping của Spring Data REST. Sau khi khởi động ứng dụng, tải /v3/api-docs để kiểm tra các path và method được tạo. Không kết luận rằng tất cả HTTP method trong bảng đều có mặt chỉ vì repository extends JpaRepository.

## 5. Giới hạn export bằng @RepositoryRestResource

Có thể ẩn toàn bộ repository khỏi REST API:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Khi exported=false, Spring Data REST không xuất bản repository này như REST resource. Đây là cách giới hạn bề mặt HTTP được tạo tự động.

Có thể đổi tên resource bằng path và relation:

~~~java
@RepositoryRestResource(
    path = "catalog-items",
    collectionResourceRel = "catalogItems",
    itemResourceRel = "catalogItem"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Nếu resource đã được sử dụng bởi client, thay đổi path hoặc relation name có thể ảnh hưởng hợp đồng API. Hãy xem đây là thay đổi API cần quản lý version và migration.

Ẩn repository khỏi Spring Data REST không đồng nghĩa dữ liệu đã được bảo vệ ở mọi nơi. Repository vẫn có thể được sử dụng bởi service hoặc controller khác. Authorization vẫn cần được thực thi ở backend.

## 6. Mô tả repository và resource bằng @Description

Spring Data REST cung cấp annotation @Description để mô tả collection và item resource:

~~~java
@RepositoryRestResource(
    path = "products",
    collectionResourceDescription =
        @Description("Danh sách sản phẩm trong cửa hàng"),
    itemResourceDescription =
        @Description("Thông tin chi tiết của một sản phẩm")
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Các mô tả này giúp bổ sung metadata cho Spring Data REST, đặc biệt trong các cơ chế hypermedia/profile mà framework hỗ trợ.

Không nên mặc định rằng mọi @Description sẽ tự động trở thành summary hoặc description của OpenAPI operation trong mọi phiên bản Springdoc. Hãy kiểm tra JSON được sinh ra. Nếu OpenAPI cần nội dung cụ thể hơn, có thể bổ sung bằng OpenApiCustomizer hoặc cơ chế annotation mà phiên bản Springdoc hỗ trợ cho handler tương ứng.

Mục tiêu là giữ mô tả tài nguyên, operation và response thống nhất. Nếu collection resource có mô tả nghiệp vụ, tài liệu OpenAPI cũng nên giải thích client dùng resource đó trong tình huống nào.

## 7. Expose query method thành search endpoint

Spring Data REST có thể xuất bản các query method của repository dưới resource search. Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByNameContainingIgnoreCase(
        @Param("name") String name
    );
}
~~~

Endpoint tìm kiếm thường có dạng:

~~~http
GET /api/products/search/findByNameContainingIgnoreCase?name=keyboard
~~~

Spring Data REST tạo search resource cho query method được export. Tên method thường được dùng làm path mặc định; @RestResource cho phép đổi path và relation:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @RestResource(
        path = "by-name",
        rel = "byName",
        description = @Description("Tìm sản phẩm theo một phần tên")
    )
    List<Product> findByNameContainingIgnoreCase(
        @Param("name") String name
    );
}
~~~

Endpoint lúc này có dạng:

~~~http
GET /api/products/search/by-name?name=keyboard
~~~

Trong đó path của search method là by-name và query parameter là name. @Param giúp đặt tên parameter công khai rõ ràng, tránh phụ thuộc vào tên tham số Java hoặc compiler metadata.

Springdoc cần mô tả path, query parameter, kiểu response và status của search operation. Sau khi sinh tài liệu, kiểm tra parameter name có đúng name và operation có nằm dưới /search hay không.

## 8. Ẩn query method bằng @RestResource

Một query method có thể không được phép gọi trực tiếp qua REST:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @RestResource(exported = false)
    List<Product> findByInternalStatus(String status);
}
~~~

exported=false ngăn Spring Data REST công bố query method này thành search endpoint.

Có thể đổi path hoặc relation của query method bằng @RestResource:

~~~java
@RestResource(path = "active", rel = "activeProducts")
List<Product> findByActiveTrue();
~~~

Khi thay đổi export, hãy kiểm tra cả repository search resource và OpenAPI document. Operation không còn được export không nên tiếp tục xuất hiện trong tài liệu. Ngược lại, operation xuất hiện trong tài liệu nhưng runtime trả 404 là dấu hiệu tài liệu và handler mapping chưa đồng nhất.

Không dùng việc ẩn query method như một cơ chế authorization. Nếu một query vẫn được gọi từ service hoặc endpoint khác, quyền truy cập dữ liệu vẫn cần được kiểm soát ở tầng bảo mật và nghiệp vụ.

## 9. Phân trang và sắp xếp của collection resource

Spring Data REST hỗ trợ phân trang và sắp xếp cho collection resource. Các query parameter phổ biến:

| Parameter | Ý nghĩa | Ví dụ |
|---|---|---|
| page | Chỉ số trang, thường bắt đầu từ 0 | page=0 |
| size | Số phần tử tối đa trong trang | size=20 |
| sort | Property và hướng sắp xếp | sort=name,asc |

Ví dụ:

~~~http
GET /api/products?page=0&size=20&sort=name,asc
~~~

Có thể truyền nhiều điều kiện sort nếu API hỗ trợ:

~~~http
GET /api/products?page=0&size=20&sort=category,asc&sort=price,desc
~~~

Response collection thường có metadata page như size, number, totalElements và totalPages. Client dùng metadata này để xây dựng điều hướng trang.

Springdoc có thể mô tả query parameters và response schema được tạo từ Spring Data REST. Tuy nhiên, cần kiểm tra chính xác parameter names, default values, giới hạn size và kiểu response trong OpenAPI JSON. Không nên giả định mọi cấu hình Pageable của Spring MVC đều áp dụng giống hệt cho Spring Data REST.

Nếu hệ thống giới hạn kích thước trang tối đa, tài liệu cần nêu rõ giới hạn để client không gửi size quá lớn. Backend phải thực thi giới hạn đó, kể cả khi OpenAPI schema có mô tả maximum.

## 10. HAL representation và hypermedia links

Spring Data REST thường dùng HAL (Hypertext Application Language) để biểu diễn resource. Một collection response có thể có dạng:

~~~json
{
  "_embedded": {
    "products": [
      {
        "name": "Mechanical Keyboard",
        "price": 120.00,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/products/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/products?page=0&size=20"
    },
    "search": {
      "href": "https://api.example.com/api/products/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Các phần quan trọng:

- _embedded chứa resource được nhúng trong collection.
- _links chứa các liên kết hypermedia để client khám phá thao tác tiếp theo.
- page chứa metadata phân trang.
- Mỗi item có thể có links riêng như self và links tới association.

HAL giúp client khám phá API qua quan hệ link thay vì phải hard-code mọi URL. Khi viết tài liệu, cần giải thích các relation quan trọng và media type mà endpoint trả về, thường là application/hal+json.

Không nhầm HAL link với OpenAPI Link Object. HAL link là dữ liệu hypermedia trong response; OpenAPI Link Object mô tả quan hệ giữa các operation trong hợp đồng tài liệu. Hai khái niệm có mục đích và cấu trúc khác nhau.

## 11. Schema HAL trong OpenAPI

Response HAL không phải một DTO phẳng thông thường. Collection có thể chứa _embedded, _links và page; item có thể chứa các relation link và property nghiệp vụ.

Springdoc có thể dùng hỗ trợ Spring HATEOAS để xử lý một số model hypermedia. Trong các phiên bản có thuộc tính tương ứng, cấu hình có thể bao gồm:

~~~yaml
springdoc:
  enable-hateoas: true
  enable-data-rest: true
~~~

Hãy xác minh các thuộc tính theo phiên bản Springdoc. Nếu tài liệu tạo ra schema quá chung, thiếu nội dung _embedded hoặc không thể hiện đúng item type, hãy kiểm tra OpenAPI JSON và bổ sung schema/customizer phù hợp.

Một schema collection có thể cần thể hiện:

- _embedded chứa danh sách resource.
- _links chứa relation và href.
- page chứa size, number, totalElements và totalPages.
- Item schema mô tả các field nghiệp vụ.
- Media type application/hal+json.

Không nên ép response HAL thành application/json nếu runtime thực tế trả application/hal+json. Media type là một phần của hợp đồng và ảnh hưởng cách client giải mã response.

## 12. Projection và excerpt projection

Projection cho phép Spring Data REST công bố một góc nhìn của entity. Ví dụ:

~~~java
@Projection(
    name = "productSummary",
    types = Product.class
)
public interface ProductSummary {

    Long getId();

    String getName();

    BigDecimal getPrice();
}
~~~

Projection có thể được dùng khi client cần một representation gọn. Repository có thể khai báo excerpt projection mặc định:

~~~java
@RepositoryRestResource(
    path = "products",
    excerptProjection = ProductSummary.class
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Client cũng có thể yêu cầu projection theo query parameter nếu projection được export và endpoint hỗ trợ:

~~~http
GET /api/products/42?projection=productSummary
~~~

Tài liệu OpenAPI cần làm rõ representation nào được trả về mặc định và projection nào có thể được chọn. Nếu nhiều projection tạo ra response schema khác nhau, hãy kiểm tra xem Springdoc có mô tả đầy đủ từng biến thể không.

Không nên coi projection là authorization. Ẩn một field khỏi projection không thay thế kiểm tra quyền truy cập field hoặc dữ liệu nhạy cảm ở backend.

## 13. Association resource và quan hệ giữa entity

Spring Data REST có thể export association giữa entity thành các resource link. Ví dụ Product tham chiếu Category. Resource product có thể chứa relation tới category trong _links.

Các thao tác association có thể được expose dưới path gắn với item, tùy loại association và cấu hình repository. Client có thể đọc liên kết để khám phá resource liên quan thay vì tự ghép URL.

Khi mô tả association:

- Nêu relation name và ý nghĩa nghiệp vụ.
- Giải thích URL đích và media type.
- Mô tả request body hoặc URI representation nếu operation cập nhật association yêu cầu.
- Ghi rõ authorization cần thiết.
- Kiểm tra response HAL và OpenAPI schema thực tế.

Không nên giả định mọi association đều có cùng HTTP method hoặc request body. Cách cập nhật quan hệ còn phụ thuộc loại association, repository exposure và cấu hình Spring Data REST.

## 14. Tùy chỉnh tên resource và base path

Có hai cấp cấu hình URL thường gặp:

**Base path toàn bộ Spring Data REST:**

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

**Path riêng của repository:**

~~~java
@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Kết hợp hai cấu hình, collection resource có thể được truy cập tại /api/products.

Nếu thay base path hoặc repository path sau khi client đã tích hợp, đây là thay đổi hợp đồng. Cần cập nhật OpenAPI document, gateway route, security matcher, CORS policy và client configuration đồng thời.

Nên kiểm tra root resource sau khi khởi động. Spring Data REST thường cung cấp discovery links; các relation trong root giúp client biết collection resource đang được export.

## 15. Tùy biến OpenAPI cho repository resources

Springdoc có thể tạo operation từ repository handler mapping. Nếu cần chuẩn hóa tag hoặc metadata cho một vùng path, có thể dùng OpenApiCustomizer.

Ví dụ gắn tag Products cho các operation dưới /api/products:

~~~java
@Bean
OpenApiCustomizer productRepositoryTagCustomizer() {
    return openApi -> {
        openApi.addTagsItem(
            new Tag()
                .name("Products")
                .description("Các resource sản phẩm được tạo từ ProductRepository")
        );

        if (openApi.getPaths() == null) {
            return;
        }

        openApi.getPaths().forEach((path, pathItem) -> {
            if (path.startsWith("/api/products")) {
                pathItem.readOperations()
                    .forEach(operation -> operation.addTagsItem("Products"));
            }
        });
    };
}
~~~

Customizer này chỉ thay đổi tài liệu OpenAPI. Nó không thay đổi URL, quyền truy cập hoặc hành vi repository.

Nếu base path hoặc repository path thay đổi, điều kiện startsWith cần được cập nhật. Với nhiều repository, có thể xây dựng mapping giữa path prefix và tag để tránh gắn nhầm operation.

Tránh tạo lại toàn bộ Paths trong customizer vì Springdoc đã sinh các operation từ handler mapping. Chỉ bổ sung hoặc điều chỉnh trường cần thiết để giữ nguyên operation và schema đã được phát hiện.

## 16. Khi endpoint repository không xuất hiện trong OpenAPI

Nếu Spring Data REST endpoint hoạt động nhưng không có trong /v3/api-docs, hãy kiểm tra theo thứ tự:

1. Spring Data REST dependency đã nằm trên runtime classpath.
2. Springdoc starter tương thích với Spring Boot và web stack.
3. Tính năng tích hợp Data REST/HATEOAS được bật theo cấu hình của phiên bản.
4. Repository thực sự được export và không đặt exported=false.
5. Repository nằm trong application context được Spring quản lý.
6. Base path và repository path đúng với URL runtime.
7. Query method không bị @RestResource(exported=false).
8. Springdoc path/package filters không loại operation.
9. OpenAPI document được tạo sau khi Spring Data REST handler mapping đã đăng ký.
10. Không có customizer loại bỏ path hoặc ghi đè document.

Nếu operation xuất hiện nhưng thiếu schema hoặc mô tả, kiểm tra media type, HAL model, projection và generic type. Có thể bổ sung metadata bằng OpenApiCustomizer sau khi xác nhận cấu trúc runtime.

Không nên tự tạo controller giả chỉ để Swagger UI hiển thị operation nếu endpoint thật đã được Spring Data REST quản lý. Điều đó có thể tạo tài liệu trùng hoặc khiến OpenAPI mô tả một endpoint không tồn tại.

## 17. Bảo vệ repository endpoints và tài liệu

Repository endpoint được sinh tự động vẫn là HTTP API thật. Cần áp dụng authentication và authorization theo chính sách ứng dụng:

- Giới hạn repository hoặc method được export.
- Dùng Spring Security để bảo vệ collection và item resource.
- Kiểm tra quyền theo đối tượng khi đọc, sửa hoặc xóa.
- Bảo vệ query method có thể tiết lộ dữ liệu nhạy cảm.
- Kiểm soát association endpoint.
- Không coi việc ẩn operation khỏi OpenAPI là biện pháp bảo mật.

Tài liệu OpenAPI cũng cần chính sách truy cập riêng. Người dùng được xem Swagger UI không nhất thiết có quyền gọi POST hoặc DELETE. Ngược lại, repository endpoint có thể được bảo vệ dù tài liệu vẫn được công khai.

Spring Data REST có thể dùng security configuration của ứng dụng và các cơ chế authorization tương ứng. Hãy kiểm tra request runtime với người dùng không có quyền, người dùng có quyền đọc và người dùng có quyền ghi.

## 18. Kiểm thử OpenAPI và HAL response

Sau khi khởi động ứng dụng, kiểm tra các endpoint:

~~~http
GET /api
GET /api/products
GET /api/products/search
GET /v3/api-docs
~~~

Nếu có base path khác, thay các URL theo cấu hình thực tế.

Có thể dùng MockMvc để kiểm tra collection response:

~~~java
mockMvc.perform(get("/api/products")
        .accept("application/hal+json")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
    .andExpect(jsonPath("$._embedded.products").isArray())
    .andExpect(jsonPath("$.page.number").value(0));
~~~

Test trên kiểm tra HAL representation và page metadata. Tên relation products cần khớp collectionResourceRel thực tế.

Có thể kiểm tra OpenAPI document:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/products']").exists())
    .andExpect(jsonPath("$.paths['/api/products/search/by-name']").exists());
~~~

Đường dẫn search phải thay bằng path được cấu hình trong repository. Ngoài việc kiểm tra path tồn tại, cần xác minh HTTP method, query parameter, response media type, schema và security requirement.

## 19. Những thay đổi có thể phá vỡ client

Spring Data REST tự sinh endpoint, nhưng thay đổi cấu hình repository vẫn có thể phá vỡ client:

| Thay đổi | Ảnh hưởng có thể xảy ra |
|---|---|
| Đổi @RepositoryRestResource(path) | URL collection/item thay đổi |
| Đổi collectionResourceRel | Tên relation trong _embedded thay đổi |
| Đổi itemResourceRel | Relation của item thay đổi |
| Đổi @RestResource(path) | Search endpoint thay đổi |
| exported=false | Resource hoặc operation biến mất |
| Đổi projection/excerptProjection | JSON response thay đổi |
| Đổi entity field hoặc serialization | Schema và payload thay đổi |
| Đổi base-path | Tất cả repository URL thay đổi |
| Đổi page size hoặc sort behavior | Kết quả và điều hướng trang thay đổi |

Trước khi thay đổi, hãy lưu OpenAPI document hiện tại và mẫu HAL response. So sánh tài liệu mới với bản cũ, xác định client nào bị ảnh hưởng và lập kế hoạch version/migration nếu cần.

Không nên dựa vào tên method repository như một hợp đồng ổn định. Path công khai nên được khai báo rõ bằng annotation và được kiểm tra bằng contract test.

## 20. Nguyên tắc tích hợp Spring Data REST với Springdoc

Khi dùng repository-generated endpoints, hãy áp dụng các nguyên tắc:

1. Xác định repository nào được export và đặt path tường minh cho resource công khai.
2. Dùng @RepositoryRestResource để quản lý collection path và relation name.
3. Dùng @RestResource để đặt tên hoặc ẩn query method.
4. Dùng @Param để cố định tên query parameter.
5. Mô tả pagination, sorting và search theo URL runtime.
6. Hiểu HAL _embedded, _links và page metadata.
7. Phân biệt HAL links với OpenAPI Link Objects.
8. Dùng projection có chủ đích và kiểm tra response schema.
9. Dùng OpenApiCustomizer để bổ sung tag/metadata mà không ghi đè toàn bộ Paths.
10. Bảo vệ repository endpoints bằng authorization ở backend.
11. Kiểm tra /v3/api-docs cùng HAL response thực tế.
12. Quản lý thay đổi path, relation, projection và base path như thay đổi hợp đồng API.

Spring Data REST giúp tạo REST resources trực tiếp từ repository, còn Springdoc giúp công bố hợp đồng OpenAPI cho những endpoint đó. Khi URL, relation, HAL representation và metadata phân trang được kiểm tra cùng tài liệu được sinh, client có thể tích hợp với repository API mà không phải đoán cấu trúc hoặc phụ thuộc vào chi tiết triển khai nội bộ.

