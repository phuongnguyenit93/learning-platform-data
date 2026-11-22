# Spring HATEOAS và các lớp bao chứa liên kết

Một API REST thường trả về dữ liệu cùng các liên kết để client biết có thể thực hiện bước tiếp theo nào. Ví dụ, response của một khách hàng có thể chứa liên kết đến chính khách hàng đó, danh sách đơn hàng của khách hàng hoặc thao tác cập nhật. Cách thiết kế này tuân theo ý tưởng Hypermedia as the Engine of Application State (HATEOAS): client khám phá các hành động tiếp theo từ liên kết mà server cung cấp thay vì tự ghép mọi URL.

Spring HATEOAS cung cấp các lớp biểu diễn như `EntityModel`, `CollectionModel` và `PagedModel` để bọc nội dung cùng liên kết. `springdoc-openapi` tích hợp với các kiểu HATEOAS này để mô tả response trong OpenAPI. Khi khai báo kiểu trả về cụ thể, media type chính xác và metadata operation phù hợp, tài liệu có thể thể hiện cả dữ liệu lẫn cấu trúc hypermedia mà client nhận được.

## 1. HATEOAS bổ sung gì cho response REST?

Một response REST thông thường có thể chỉ chứa dữ liệu:

```json
{
  "id": "c-100",
  "name": "Nguyen An"
}
```

Client muốn xem đơn hàng của khách hàng có thể phải biết trước URL `/api/customers/c-100/orders`. Khi API dùng hypermedia, server có thể trả liên kết đó trong response:

```json
{
  "id": "c-100",
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/c-100"
    },
    "orders": {
      "href": "https://api.example.com/api/customers/c-100/orders"
    }
  }
}
```

Client đọc relation `orders` để khám phá liên kết đến đơn hàng. Server có thể thay đổi cấu trúc URL nội bộ mà không buộc client phải tự xây dựng URL, miễn là các relation và hợp đồng liên kết vẫn ổn định.

HATEOAS không yêu cầu mọi API phải nhúng mọi thao tác vào response. Hãy cung cấp những liên kết có ý nghĩa với trạng thái và quyền của tài nguyên. Ví dụ, liên kết `cancel` chỉ nên xuất hiện khi đơn hàng còn có thể hủy; client vẫn phải xử lý lỗi nếu trạng thái thay đổi giữa lúc đọc và lúc gọi thao tác.

## 2. Cài đặt Spring HATEOAS cùng springdoc

Với ứng dụng Spring Boot MVC dùng Spring HATEOAS và Swagger UI, các dependency thường gồm:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-hateoas</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`spring-boot-starter-hateoas` cung cấp các model, link builder và hỗ trợ hypermedia của Spring. `springdoc-openapi-hateoas` bổ sung tích hợp HATEOAS cho quá trình sinh OpenAPI; starter springdoc MVC UI cung cấp endpoint tài liệu cùng giao diện Swagger UI. Nếu chỉ cần JSON/YAML, dùng `springdoc-openapi-starter-webmvc-api` cùng module HATEOAS. Tài liệu module HATEOAS của springdoc 2.x hướng dẫn các starter WebMVC; nếu ứng dụng dùng WebFlux, kiểm tra ma trận hỗ trợ của đúng phiên bản trước khi giả định cùng module này áp dụng. Spring HATEOAS có link builder riêng cho WebFlux, nhưng điều đó không tự xác nhận springdoc HATEOAS integration cho WebFlux.

Giữ các phiên bản theo Spring Boot dependency management và nhánh springdoc tương thích. Không thêm đồng thời starter WebMVC và WebFlux chỉ để có HATEOAS; chọn stack web mà ứng dụng thực sự sử dụng.

## 3. `RepresentationModel` là lớp cơ sở cho hypermedia

`RepresentationModel<T>` là lớp cơ sở trong Spring HATEOAS cho các representation có liên kết. Nó cung cấp API để thêm và đọc các `Link`:

```java
public class CustomerRepresentation extends RepresentationModel<CustomerRepresentation> {

    private String id;
    private String name;

    // Constructor, getters and setters.
}
```

Có thể thêm liên kết trực tiếp:

```java
CustomerRepresentation model = new CustomerRepresentation();
model.add(Link.of("https://api.example.com/api/customers/c-100", "self"));
```

Trong nhiều ứng dụng, không cần tự tạo subclass. Các wrapper chuyên biệt `EntityModel`, `CollectionModel` và `PagedModel` đã cung cấp cách biểu diễn phổ biến hơn. `RepresentationModel` hữu ích khi muốn tạo kiểu representation riêng và kiểm soát cấu trúc dữ liệu.

## 4. `EntityModel<T>` bọc một tài nguyên

`EntityModel<T>` biểu diễn một tài nguyên đơn cùng các liên kết. Generic `T` là kiểu nội dung mà API muốn trả về:

```java
EntityModel<CustomerResponse> model = EntityModel.of(
    new CustomerResponse(customer.getId(), customer.getName()),
    Link.of("https://api.example.com/api/customers/c-100", "self")
);
```

Khi serialize theo HAL, nội dung của `CustomerResponse` thường nằm ở cấp ngoài cùng cùng với `_links`:

```json
{
  "id": "c-100",
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/c-100"
    }
  }
}
```

Không nên hiểu `EntityModel<T>` như một object JSON có thuộc tính `content` bao quanh dữ liệu. Wrapper là kiểu Java hỗ trợ serialization hypermedia; hình dạng JSON cuối cùng phụ thuộc media type và hypermedia module được cấu hình.

Giữ generic cụ thể như `EntityModel<CustomerResponse>` thay vì raw `EntityModel`. Thông tin kiểu giúp Jackson serialize đúng nội dung và springdoc có thể suy luận schema của tài nguyên bên trong.

## 5. `CollectionModel<T>` bọc một tập tài nguyên

`CollectionModel<T>` biểu diễn một tập phần tử cùng liên kết của collection:

```java
List<EntityModel<CustomerResponse>> customers = customerService.findAll()
    .stream()
    .map(customerAssembler::toModel)
    .toList();

CollectionModel<EntityModel<CustomerResponse>> collection =
    CollectionModel.of(customers);
```

Với HAL, collection thường được biểu diễn bằng `_embedded` và `_links`:

```json
{
  "_embedded": {
    "customers": [
      {
        "id": "c-100",
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-100"
          }
        }
      },
      {
        "id": "c-101",
        "name": "Tran Binh",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers"
    }
  }
}
```

Tên `customers` trong `_embedded` là collection relation. Spring HATEOAS có thể suy luận relation từ tên kiểu hoặc cấu hình relation provider; có thể khai báo rõ bằng `@Relation` để giữ tên ổn định.

## 6. Đặt tên relation bằng `@Relation`

Relation là tên có ý nghĩa mà client dùng để hiểu liên kết hoặc nhóm phần tử nhúng. Với một representation, có thể khai báo item relation và collection relation:

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "customer", collectionRelation = "customers")
public record CustomerResponse(String id, String name) {}
```

`itemRelation = "customer"` đặt tên relation cho một phần tử; `collectionRelation = "customers"` đặt tên cho danh sách phần tử trong `_embedded`. Tên này là một phần hợp đồng hypermedia mà client có thể sử dụng, vì vậy nên chọn tên ổn định, dễ hiểu và nhất quán.

Không nên đổi relation tùy tiện khi client đã phụ thuộc vào nó. Thay đổi `customers` thành `clients` có thể làm client không còn tìm thấy danh sách trong `_embedded`, dù URL endpoint và dữ liệu không đổi.

## 7. Tạo link theo mapping bằng `WebMvcLinkBuilder`

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo liên kết dựa trên mapping của controller. Cách này tránh hard-code đường dẫn trong assembler:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class CustomerModelAssembler
        implements RepresentationModelAssembler<Customer, EntityModel<CustomerResponse>> {

    @Override
    public EntityModel<CustomerResponse> toModel(Customer customer) {
        CustomerResponse content = new CustomerResponse(
            customer.getId(),
            customer.getName()
        );

        return EntityModel.of(
            content,
            linkTo(methodOn(CustomerController.class).getById(customer.getId()))
                .withSelfRel()
        );
    }
}
```

`methodOn(...)` tạo lời gọi controller giả lập để Spring HATEOAS đọc mapping method; method đó không được thực thi để lấy dữ liệu. `linkTo(...)` dựng URL từ mapping, còn `withSelfRel()` gắn relation chuẩn `self`.

Nếu controller có base mapping `/api/customers` và method `@GetMapping("/{id}")`, link được tạo theo mapping hiện tại. Khi đổi mapping, link builder có thể theo thay đổi đó mà không phải sửa chuỗi URL trong assembler.

Với ứng dụng Spring WebFlux, dùng link builder dành cho WebFlux thay vì `WebMvcLinkBuilder`. Hai API có cách xử lý request context khác nhau; không trộn builder MVC vào ứng dụng reactive.

## 8. Dùng `RepresentationModelAssembler` để tách việc tạo representation

`RepresentationModelAssembler<T, D>` chuyển một domain object thành representation model. Nó giúp gom logic chuyển DTO và tạo liên kết ở một nơi thay vì lặp lại trong controller:

```java
@RestController
@RequestMapping("/api/customers")
class CustomerController {

    private final CustomerService customerService;
    private final CustomerModelAssembler assembler;

    CustomerController(CustomerService customerService,
                       CustomerModelAssembler assembler) {
        this.customerService = customerService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    @Operation(summary = "Lấy khách hàng theo mã")
    EntityModel<CustomerResponse> getById(@PathVariable String id) {
        Customer customer = customerService.getById(id);
        return assembler.toModel(customer);
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    @Operation(summary = "Liệt kê khách hàng")
    CollectionModel<EntityModel<CustomerResponse>> findAll() {
        List<EntityModel<CustomerResponse>> items = customerService.findAll()
            .stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(
            items,
            linkTo(methodOn(CustomerController.class).findAll()).withSelfRel()
        );
    }
}
```

Controller trả kiểu wrapper cụ thể. Spring HATEOAS serialize nội dung và liên kết; springdoc đọc kiểu trả về để tạo response schema. Khi thêm một endpoint mới, có thể tái sử dụng assembler để bảo đảm mỗi item có cấu trúc và self link nhất quán.

Không đưa entity JPA trực tiếp ra ngoài chỉ vì `EntityModel` có thể bọc nó. Dùng DTO/representation model để kiểm soát field công khai, tránh lộ thuộc tính nội bộ và tránh serialization đi qua quan hệ lazy không mong muốn.

## 9. `PagedModel<T>` biểu diễn collection có phân trang

`PagedModel<T>` mở rộng ý tưởng collection bằng metadata phân trang. Khi dùng Spring Data, `PagedResourcesAssembler<T>` có thể chuyển `Page<T>` thành `PagedModel` và gắn các liên kết điều hướng:

```java
@GetMapping(value = "/paged", produces = MediaTypes.HAL_JSON_VALUE)
@Operation(summary = "Liệt kê khách hàng có phân trang")
PagedModel<EntityModel<CustomerResponse>> findPage(
    Pageable pageable,
    PagedResourcesAssembler<Customer> pagedAssembler
) {
    Page<Customer> page = customerService.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

HAL response của một trang có thể chứa `_embedded`, `_links` và metadata `page`:

```json
{
  "_embedded": {
    "customers": [
      {
        "id": "c-100",
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-100"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/paged?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/api/customers/paged?page=1&size=20"
    },
    "last": {
      "href": "https://api.example.com/api/customers/paged?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 0
  }
}
```

Các liên kết `first`, `prev`, `next`, `last` xuất hiện tùy vị trí trang và chính sách assembler. Metadata `page.number` trong Spring Data thường zero-based. Client nên theo liên kết do server trả về thay vì tự tính URL trang tiếp theo.

`Page<T>` và `PagedModel<T>` không phải cùng một kiểu response. `Page<T>` là abstraction dữ liệu phân trang ở tầng Spring Data; `PagedModel<T>` là representation hypermedia có thể thêm links và metadata theo định dạng HATEOAS. Nếu API cam kết HAL, hãy trả `PagedModel` thay vì phơi trực tiếp `Page` rồi giả định response tự có các liên kết điều hướng.

## 10. HAL media type và cấu trúc response

HAL (Hypertext Application Language) là một định dạng hypermedia phổ biến trong Spring HATEOAS. Media type thường dùng là `application/hal+json`, được Spring HATEOAS cung cấp qua hằng số `MediaTypes.HAL_JSON_VALUE`.

Khai báo `produces = MediaTypes.HAL_JSON_VALUE` trên mapping giúp Spring MVC công bố loại response mà endpoint tạo ra. Client có thể gửi `Accept: application/hal+json` để yêu cầu representation HAL.

Ví dụ request:

```http
GET /api/customers/c-100 HTTP/1.1
Accept: application/hal+json
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

Nếu API còn hỗ trợ JSON thông thường, cần xác định rõ mỗi media type có hình dạng payload nào và cấu hình `produces`/content negotiation tương ứng. Không công bố `application/json` nếu response thực tế luôn là HAL mà client cần đọc `_links`.

## 11. Springdoc mô tả các wrapper HATEOAS

Springdoc có tích hợp với Spring HATEOAS để phân tích các kiểu model và tạo OpenAPI schema. Khai báo kiểu trả về với generic cụ thể là cách quan trọng để giữ thông tin nội dung:

```java
EntityModel<CustomerResponse>
CollectionModel<EntityModel<CustomerResponse>>
PagedModel<EntityModel<CustomerResponse>>
```

Với springdoc 2.x, tích hợp này được cung cấp qua module riêng `springdoc-openapi-hateoas`; thêm module đó cùng starter WebMVC API/UI tương ứng. Property `springdoc.enable-hateoas` điều khiển hỗ trợ HATEOAS và mặc định được bật. Nếu module chưa có trong classpath hoặc property bị tắt, đừng kỳ vọng các wrapper được xử lý theo tích hợp HATEOAS.

Khi method trả `EntityModel<CustomerResponse>`, springdoc có thể mô tả representation của khách hàng cùng phần liên kết. Với collection và page, schema còn phản ánh cấu trúc bọc và metadata hypermedia. Cấu trúc component và tên schema cụ thể có thể khác giữa phiên bản springdoc, Swagger Core và cấu hình HAL; hãy xem output thực tế trong `/v3/api-docs` thay vì phụ thuộc vào tên component sinh tự động.

Ví dụ khai báo operation:

```java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
@Operation(
    operationId = "getCustomerById",
    summary = "Lấy khách hàng theo mã",
    description = "Trả về dữ liệu khách hàng cùng các liên kết hypermedia."
)
EntityModel<CustomerResponse> getById(@PathVariable String id) {
    return assembler.toModel(customerService.getById(id));
}
```

Thông tin trả về từ kiểu Java cho springdoc biết wrapper và generic content; `@Operation` bổ sung ý nghĩa của operation. Nếu cần ghi rõ response code hoặc mô tả, dùng `@ApiResponse`. Chỉ đặt `@Schema(implementation = ...)` khi thật sự cần override suy luận; annotation implementation không đúng có thể làm mất cấu trúc wrapper/generic mà springdoc vốn nhận diện được.

## 12. Phân biệt HAL `_links` với OpenAPI `links`

Hai khái niệm cùng tên nhưng nằm ở hai tầng khác nhau:

| Thành phần | Nơi xuất hiện | Mục đích |
| --- | --- | --- |
| HAL `_links` | JSON response runtime | Cung cấp URL và relation để client điều hướng tài nguyên hoặc hành động tiếp theo. |
| OpenAPI Response Object `links` | Đặc tả OpenAPI | Mô tả quan hệ từ response của operation này đến operation khác, giúp công cụ hiểu cách truyền dữ liệu giữa các operation. |

`EntityModel` và `CollectionModel` tạo `_links` trong payload HAL. Trường `links` của OpenAPI là metadata trong document, không tự chèn `_links` vào response runtime. Ngược lại, server trả `_links` không tự động tạo mọi OpenAPI Link Object mô tả workflow giữa các operation.

Nếu API dùng HATEOAS, hãy mô tả schema response và media type trong OpenAPI. Chỉ thêm OpenAPI `links` khi muốn công bố rõ mối quan hệ có thể thực hiện giữa các operation cho tooling hoặc workflow.

## 13. Kiểm tra response HAL và OpenAPI document

Nên xác minh cả serialization runtime lẫn schema được sinh ra:

1. Gọi endpoint với `Accept: application/hal+json` và xác nhận `Content-Type` là `application/hal+json`.
2. Với tài nguyên đơn, kiểm tra field nội dung cùng `_links.self.href`.
3. Với collection, kiểm tra `_embedded` dùng đúng collection relation và mỗi item có link cần thiết.
4. Với trang, kiểm tra `_links` điều hướng cùng metadata `page`.
5. Mở `/v3/api-docs`, tìm operation và xác nhận response content có media type HAL.
6. Kiểm tra schema được tạo cho wrapper và generic content; xác nhận `$ref` đều trỏ đến component tồn tại.
7. Mở Swagger UI và kiểm tra response schema/example có thể đọc được.
8. Thử client theo relation thay vì tự ghép URL để xác nhận link dẫn đến operation hợp lệ.

Ví dụ kiểm tra endpoint đơn bằng MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerHateoasTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsCustomerWithSelfLink() throws Exception {
        mockMvc.perform(get("/api/customers/{id}", "c-100")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value("c-100"))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Test này kiểm tra response runtime. Nên có test riêng cho `/v3/api-docs` để xác nhận operation và media type được công bố; hai kiểm tra không thay thế nhau.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response có dữ liệu nhưng không có `_links` | Trả DTO trực tiếp thay vì representation model, hoặc không thêm link | Dùng `EntityModel`/`RepresentationModel` và tạo link tường minh. |
| Collection không có `_embedded` như mong đợi | Relation name được suy luận khác hoặc wrapper không phải `CollectionModel` | Dùng `CollectionModel` và khai báo `@Relation(collectionRelation = ...)` nếu cần. |
| Link có URL sai host hoặc prefix | Tạo URL hard-code hoặc proxy/forwarded header cấu hình sai | Dùng link builder theo mapping và kiểm tra forwarded headers. |
| `EntityModel` bị mô tả như object Java không đúng | Raw generic, schema override sai hoặc tích hợp HATEOAS không hoạt động | Giữ generic cụ thể, kiểm tra dependency và `/v3/api-docs`. |
| Response trả `application/json` nhưng client cần HAL | Mapping không khai báo HAL hoặc content negotiation chưa đúng | Khai báo `produces = MediaTypes.HAL_JSON_VALUE` và kiểm tra `Accept`. |
| Swagger UI không hiển thị cấu trúc `_links` rõ ràng | Schema component sinh ra khác dự kiến hoặc media type chưa được mô tả | Kiểm tra schema thô và khai báo response content phù hợp khi cần. |
| Paged response thiếu link next/last | Trang hiện tại ở cuối, không có dữ liệu hoặc không dùng `PagedResourcesAssembler` | Kiểm tra page metadata và cách chuyển `Page` sang `PagedModel`. |
| Đổi relation làm client lỗi | Client phụ thuộc vào tên `_embedded` hoặc relation cũ | Giữ relation ổn định hoặc quản lý thay đổi như một thay đổi hợp đồng. |
| Swagger có OpenAPI `links` nhưng JSON không có `_links` | Nhầm Link Object của OpenAPI với HAL link runtime | Tạo `Link` trong representation model; OpenAPI links chỉ mô tả workflow tài liệu. |

## 15. Nguyên tắc áp dụng

- Dùng `EntityModel<T>` cho một tài nguyên, `CollectionModel<T>` cho collection và `PagedModel<T>` cho collection có phân trang.
- Giữ generic cụ thể để Jackson và springdoc nhận diện nội dung bên trong wrapper.
- Dùng `RepresentationModelAssembler` để tách logic chuyển DTO và tạo link khỏi controller.
- Tạo link theo controller mapping bằng `WebMvcLinkBuilder` trong MVC hoặc builder tương ứng trong WebFlux.
- Dùng `@Relation` để cố định item/collection relation khi client phụ thuộc vào tên đó.
- Công bố đúng media type, thường là `application/hal+json` khi dùng HAL.
- Không trả entity persistence trực tiếp nếu DTO giúp kiểm soát dữ liệu công khai tốt hơn.
- Phân biệt HAL `_links` trong response với OpenAPI `links` trong tài liệu.
- Kiểm tra response runtime, `/v3/api-docs` và Swagger UI sau khi thay đổi wrapper hoặc relation.

Spring HATEOAS cung cấp các wrapper để biểu diễn tài nguyên, collection và trang dữ liệu cùng liên kết hypermedia. Khi controller trả kiểu `EntityModel`, `CollectionModel` hoặc `PagedModel` có generic cụ thể, springdoc có thể mô tả cấu trúc response trong OpenAPI; media type HAL và relation name giúp client hiểu cách đọc `_links` và `_embedded`. Hãy kiểm tra đồng thời JSON runtime và tài liệu sinh ra để bảo đảm schema, liên kết và hợp đồng API thống nhất.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – `EntityModel`](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS – `CollectionModel` và `PagedModel`](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Springdoc OpenAPI v2 – Modules và Spring HATEOAS support](https://springdoc.org/v2/modules.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
