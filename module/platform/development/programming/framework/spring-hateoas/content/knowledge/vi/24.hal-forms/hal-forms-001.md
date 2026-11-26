# HAL-FORMS là gì trong Spring HATEOAS?

Một REST API hypermedia không chỉ trả dữ liệu và URI. API còn có thể mô tả những thao tác mà client có thể thực hiện tiếp theo, chẳng hạn tạo nhân viên, cập nhật đơn hàng hoặc gửi yêu cầu phê duyệt. Khi thao tác cần dữ liệu đầu vào, client cần biết method HTTP, media type, các trường payload và một số ràng buộc của từng trường. HAL-FORMS là một định dạng hypermedia giúp server công bố thông tin đó bên cạnh các liên kết.

Spring HATEOAS hỗ trợ HAL-FORMS thông qua affordance. Ứng dụng liên kết một affordance với controller method; framework phân tích mapping, kiểu request body và metadata của property, sau đó serialize thành template trong response HAL-FORMS. Client có thể đọc template để xây dựng form hoặc tạo request phù hợp.

## 1. HAL-FORMS là gì?

HAL-FORMS là một media type hypermedia dựa trên HAL, có bổ sung form template để mô tả các thao tác mà client có thể thực hiện. Media type của HAL-FORMS JSON là:

```http
application/prs.hal-forms+json
```

HAL thông thường cung cấp các phần chính như:

- `_links`: các liên kết tới tài nguyên liên quan hoặc bước điều hướng tiếp theo.
- `_embedded`: các tài nguyên được nhúng trong representation hiện tại.

HAL-FORMS giữ cách biểu diễn đó và bổ sung:

- `_templates`: các template mô tả thao tác, method, content type, target và những property đầu vào.

Ví dụ, response collection nhân viên có thể công bố link `self` tới danh sách và một template để tạo nhân viên. Client đọc template, hiển thị form tương ứng rồi gửi POST tới target được mô tả.

HAL-FORMS hữu ích khi client muốn khám phá cách tương tác với API từ response. Client không cần ghi cứng toàn bộ cấu trúc request nếu server đã công bố affordance và metadata cần thiết.

## 2. HAL và HAL-FORMS khác nhau thế nào?

| Khả năng | HAL JSON | HAL-FORMS |
| --- | --- | --- |
| Liên kết `_links` | Có | Có |
| Tài nguyên nhúng `_embedded` | Có | Có |
| Template thao tác `_templates` | Không phải phần cốt lõi của HAL | Có |
| Mô tả HTTP method cho thao tác | Không được mô tả đầy đủ bởi link HAL cơ bản | Có trong template |
| Mô tả request content type | Không được mô tả đầy đủ bởi link HAL cơ bản | Có thể công bố trong template |
| Mô tả property đầu vào | Không có cấu trúc form chuẩn trong HAL cơ bản | Có, qua `properties` |

Một link HAL như `cancel` có thể cho biết URI liên quan tới hành động hủy, nhưng chỉ relation và `href` không mô tả đầy đủ payload hoặc cách gửi request. HAL-FORMS bổ sung template để diễn tả các thông tin tương tác đó.

HAL-FORMS không thay thế HAL. Nó mở rộng mô hình hypermedia với phần mô tả thao tác. Khi client yêu cầu `application/hal+json`, server có thể trả representation HAL thông thường; khi client yêu cầu `application/prs.hal-forms+json`, server có thể trả representation có thêm `_templates` nếu ứng dụng đã cấu hình và công bố affordance.

## 3. Cấu trúc tổng quát của một response HAL-FORMS

Một response HAL-FORMS có thể trông như sau:

```json
{
  "_links": {
    "self": {
      "href": "/employees"
    }
  },
  "_embedded": {
    "employees": [
      {
        "id": "e-42",
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "/employees/e-42"
          }
        }
      }
    ]
  },
  "_templates": {
    "default": {
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "name",
          "type": "text",
          "required": true
        },
        {
          "name": "email",
          "type": "email",
          "required": true
        }
      ]
    }
  }
}
```

Đây là ví dụ rút gọn để minh họa cấu trúc; tên template, target và danh sách property thực tế phụ thuộc affordance mà server tạo. Các thành phần có vai trò riêng:

- `_links.self` trỏ tới collection nhân viên.
- `_embedded.employees` chứa các representation nhân viên được nhúng.
- `_templates.default` mô tả một thao tác có thể thực hiện trên collection.
- `method` cho biết HTTP method mà client cần dùng.
- `contentType` cho biết media type của request body.
- `properties` mô tả các trường mà client có thể gửi.

Client không nên giả định template luôn có tên `default`. Nếu API công bố nhiều template hoặc đặt tên riêng, client cần đọc tên và nội dung thực tế trong `_templates`.

## 4. Affordance là nền tảng để tạo HAL-FORMS template

Trong Spring HATEOAS, affordance mô tả một hành động có thể thực hiện trên tài nguyên hoặc qua một liên kết. Affordance thường được tạo bằng cách tham chiếu controller method. Từ method, Spring HATEOAS có thể phân tích:

- HTTP method qua mapping như `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` hoặc `@DeleteMapping`.
- URI target qua mapping cấp class, mapping cấp method và các tham số path/query.
- Input payload type từ tham số `@RequestBody`.
- Output payload type từ kiểu trả về của method.
- Metadata property từ kiểu dữ liệu và các annotation liên quan.

Ví dụ, method `createEmployee(...)` nhận `@RequestBody EmployeeInput` và được gắn `@PostMapping`. Khi affordance tham chiếu method đó, HAL-FORMS có thể tạo template POST với các property lấy từ `EmployeeInput`.

Affordance không gọi controller method để thực hiện nghiệp vụ. Nó sử dụng thông tin mapping và kiểu dữ liệu để mô tả thao tác cho client.

## 5. Khai báo controller để công bố thao tác

Giả sử API quản lý nhân viên có endpoint GET collection và POST tạo mới:

```java
@RestController
@RequestMapping("/employees")
class EmployeeController {

    private final EmployeeService employeeService;
    private final EmployeeModelAssembler assembler;

    EmployeeController(
            EmployeeService employeeService,
            EmployeeModelAssembler assembler) {
        this.employeeService = employeeService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<EmployeeView>> getEmployees() {
        CollectionModel<EntityModel<EmployeeView>> model =
                assembler.toCollectionModel(employeeService.findAll());

        Link collection = linkTo(methodOn(EmployeeController.class).getEmployees())
                .withSelfRel()
                .andAffordance(afford(
                        methodOn(EmployeeController.class).createEmployee(null)
                ));

        model.add(collection);
        return model;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<EmployeeView> createEmployee(
            @Valid @RequestBody EmployeeInput input) {
        Employee employee = employeeService.create(input);
        return assembler.toModel(employee);
    }
}
```

Trong ví dụ:

1. `getEmployees()` trả collection representation.
2. `linkTo(methodOn(...).getEmployees())` tạo link self cho collection.
3. `afford(methodOn(...).createEmployee(null))` tham chiếu method POST tạo nhân viên.
4. `andAffordance(...)` gắn affordance vào link collection.
5. Khi serialize bằng HAL-FORMS, affordance có thể trở thành template tạo nhân viên.

Giá trị `null` trong `methodOn(...).createEmployee(null)` là placeholder để framework phân tích chữ ký method. Nó không phải payload thực tế và method không được gọi để tạo nhân viên ở bước xây link.

Các kiểu `Employee`, `EmployeeInput`, `EmployeeView`, `EmployeeService` và assembler là thành phần minh họa của ứng dụng. Trong dự án thực tế, nên tách DTO đầu vào khỏi domain entity và output representation.

## 6. Bật hỗ trợ HAL-FORMS

Với cấu hình Spring HATEOAS tường minh, có thể đăng ký media type HAL-FORMS bằng `@EnableHypermediaSupport`:

```java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Trong ứng dụng Spring Boot sử dụng starter HATEOAS, auto-configuration có thể thiết lập các thành phần hypermedia tương ứng. Hãy kiểm tra cấu hình thực tế nếu ứng dụng dùng cấu hình MVC tùy chỉnh hoặc chỉ bật một tập media type cụ thể.

Client yêu cầu HAL-FORMS qua header `Accept`:

```http
GET /employees HTTP/1.1
Accept: application/prs.hal-forms+json
```

Server cần có converter và cấu hình phù hợp để trả đúng media type. Nếu ứng dụng không hỗ trợ định dạng được yêu cầu, content negotiation có thể trả `406 Not Acceptable` tùy cấu hình.

## 7. Input model và metadata của property

Template HAL-FORMS có thể mô tả từng trường đầu vào. Spring HATEOAS suy ra metadata từ kiểu payload và các annotation mà nó hỗ trợ.

Ví dụ input DTO:

```java
public class EmployeeInput {

    @NotBlank
    @Size(min = 2, max = 80)
    private String name;

    @NotNull
    @Email
    private String email;

    @Pattern(regexp = "[A-Z]{2}-[0-9]{6}")
    private String employeeCode;

    // Getter và setter.
}
```

Các annotation có thể đóng góp vào metadata form:

| Annotation hoặc đặc điểm property | Metadata có thể được công bố |
| --- | --- |
| `@NotNull` | `required` |
| `@Pattern` | `regex` |
| `@Min`, `@DecimalMin` | `min` |
| `@Max`, `@DecimalMax` | `max` |
| `@Size`, `@Length` | Giới hạn kích thước hoặc độ dài phù hợp |
| `@Email` | Gợi ý input type email |
| Không có setter hoặc Jackson READ_ONLY | `readOnly` |

Spring HATEOAS cũng cung cấp `@InputType` để chỉ định loại input khi kiểu Java hoặc annotation validation chưa đủ để suy luận:

```java
@InputType("date")
private LocalDate startDate;
```

Metadata giúp client hiển thị giao diện nhập liệu phù hợp. Nó không thay thế Bean Validation hoặc quy tắc nghiệp vụ phía server.

## 8. Template có thể mô tả những gì?

Một HAL-FORMS template có thể chứa các thuộc tính sau:

| Thuộc tính | Vai trò |
| --- | --- |
| `title` | Tên hiển thị của thao tác. |
| `method` | HTTP method dùng để gửi request. |
| `contentType` | Media type của request body. |
| `target` | URI đích của thao tác khi cần chỉ định riêng. |
| `properties` | Danh sách trường đầu vào. |
| `name` | Tên property trong payload. |
| `type` | Loại input mà client có thể dùng để hiển thị trường. |
| `required` | Cho biết property có bắt buộc hay không. |
| `readOnly` | Cho biết property chỉ đọc. |
| `regex`, `min`, `max` | Một số ràng buộc dữ liệu. |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi. |
| `prompt`, `placeholder` | Gợi ý cho người dùng khi nhập dữ liệu. |
| `options` | Danh sách hoặc nguồn lựa chọn cho property. |

Không phải template nào cũng cần mọi thuộc tính. Serializer chỉ công bố metadata có thể suy ra hoặc được cấu hình. Client cần xử lý trường hợp một số metadata không có mặt.

## 9. Client sử dụng HAL-FORMS như thế nào?

Một client tổng quát có thể thực hiện quy trình sau:

1. Gửi request tới entry point hoặc endpoint đã biết và yêu cầu `application/prs.hal-forms+json`.
2. Đọc `_links` để khám phá tài nguyên và các relation.
3. Đọc `_templates` để tìm thao tác mà client muốn thực hiện.
4. Đọc `method`, `target`, `contentType` và `properties` của template.
5. Tạo giao diện hoặc payload theo metadata property.
6. Gửi request tới target bằng method và content type được mô tả.
7. Đọc response mới và tiếp tục điều hướng qua các link/affordance được công bố.

Ví dụ, template tạo nhân viên chỉ ra `POST`, target `/employees`, content type `application/json` và hai trường bắt buộc `name`, `email`. Client có thể hiển thị form, thu thập giá trị rồi gửi JSON tương ứng.

Client không nên ghép target từ tên controller hoặc tên class Java. Nó nên dùng URI được công bố trong template hoặc link liên quan. Tên property và relation cũng cần được đọc từ response, không suy ra từ cấu trúc code phía server.

## 10. HAL-FORMS không phải HTML form hoặc JSON Schema

HAL-FORMS mô tả template tương tác trong representation hypermedia. Nó không phải HTML form được server render và cũng không phải một bản JSON Schema đầy đủ.

Điểm khác biệt:

- HTML form chứa markup và thường được trình duyệt render trực tiếp.
- JSON Schema mô tả cấu trúc, kiểu và ràng buộc dữ liệu theo một ngôn ngữ schema tổng quát.
- HAL-FORMS mô tả thao tác hypermedia cùng các property cần thiết để client tạo request.

HAL-FORMS có thể công bố một số ràng buộc hữu ích, nhưng không mô tả tất cả quy tắc nghiệp vụ, điều kiện phân quyền hoặc mọi ràng buộc phức tạp. Client vẫn cần xử lý lỗi từ server sau khi gửi request.

## 11. Content negotiation và khả năng tương thích

Một API có thể hỗ trợ cả HAL JSON và HAL-FORMS. Client chọn representation bằng `Accept`:

```http
Accept: application/hal+json
```

hoặc:

```http
Accept: application/prs.hal-forms+json
```

Với HAL JSON, client nhận liên kết và embedded resource theo HAL. Với HAL-FORMS, client có thể nhận thêm `_templates` mô tả thao tác. Cùng một tài nguyên có thể được biểu diễn ở hai định dạng tùy media type được chọn.

Nếu client không hỗ trợ HAL-FORMS, nó vẫn có thể dùng HAL link nếu server công bố media type đó. Khi thiết kế API, hãy xác định media type nào được hỗ trợ, kiểm thử content negotiation và tránh giả định mọi client đều hiểu `_templates`.

## 12. Bảo mật và validation vẫn thuộc trách nhiệm server

Affordance chỉ mô tả khả năng tương tác. Việc công bố template POST không cấp quyền tạo nhân viên cho mọi người dùng. Endpoint vẫn phải xác thực, phân quyền và kiểm tra quy tắc nghiệp vụ khi request thực sự đến.

Tương tự, `required`, `regex`, `min` hoặc `max` trong template chỉ giúp client tạo request đúng hơn. Client có thể gửi payload sai, bỏ qua metadata hoặc tự tạo request thủ công. Server cần:

- Dùng DTO đầu vào với các trường được phép ghi.
- Kích hoạt Bean Validation bằng `@Valid` khi phù hợp.
- Kiểm tra quyền truy cập và điều kiện nghiệp vụ trong service.
- Không tin ID, role, trạng thái hoặc audit field do client gửi nếu chúng thuộc quyền quản lý của server.
- Trả lỗi có cấu trúc theo hợp đồng API khi payload không hợp lệ.

Nếu một thao tác chỉ khả dụng trong một số trạng thái, hãy công bố affordance theo trạng thái đó. Tuy nhiên, endpoint vẫn phải kiểm tra lại trạng thái để xử lý request cũ hoặc request được gửi trực tiếp.

## 13. Tùy chỉnh template và property

Spring HATEOAS cho phép tùy chỉnh metadata của HAL-FORMS thông qua `HalFormsConfiguration`. Ví dụ, một property có thể nhận danh sách lựa chọn inline:

```java
@Configuration
class HalFormsConfigurationSetup {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        HalFormsConfiguration configuration = new HalFormsConfiguration();
        configuration.withOptions(EmployeeInput.class, "department",
                metadata -> HalFormsOptions.inline(
                        "Engineering", "Finance", "Sales"));
        return configuration;
    }
}
```

Với danh sách lựa chọn thay đổi theo dữ liệu server, có thể cấu hình remote options trỏ tới tài nguyên cung cấp lựa chọn. Cách này giúp client khám phá danh sách giá trị hợp lệ mà không cần nhúng toàn bộ lựa chọn vào mọi template.

Các nhãn hiển thị, prompt và placeholder cũng có thể được cấu hình qua cơ chế message source/resource bundle của Spring HATEOAS. Hãy giữ nội dung hiển thị tách biệt với tên property và relation để có thể hỗ trợ nhiều ngôn ngữ.

## 14. Kiểm thử HAL-FORMS bằng MockMvc

Kiểm thử cần xác nhận response đúng media type và template được serialize. Ví dụ:

```java
mockMvc.perform(get("/employees")
        .accept("application/prs.hal-forms+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            "application/prs.hal-forms+json"))
    .andExpect(jsonPath("$._links.self.href").value("/employees"))
    .andExpect(jsonPath("$._templates").exists());
```

Nếu template có tên xác định, có thể kiểm tra method và property:

```java
mockMvc.perform(get("/employees")
        .accept("application/prs.hal-forms+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.default.method").value("POST"))
    .andExpect(jsonPath("$._templates.default.contentType")
            .value(MediaType.APPLICATION_JSON_VALUE))
    .andExpect(jsonPath("$._templates.default.properties[?(@.name == 'email')]")
            .exists());
```

Tên template thực tế phụ thuộc cách affordance được đặt tên và serialize. Hãy đọc response trong test trước khi cố định JSONPath. Ngoài ra, cần kiểm tra:

- `target` hoặc URI đích tương ứng với endpoint dự kiến.
- `method` khớp mapping controller.
- `contentType` khớp `consumes` hoặc cấu hình input media type.
- Property `required`, `readOnly`, `type` và validation metadata đúng.
- Template không xuất hiện khi thao tác không được công bố.
- Endpoint từ chối payload sai hoặc người dùng không có quyền.

## 15. Các lỗi thường gặp

**Nhầm HAL-FORMS với HAL JSON.** HAL JSON cơ bản không cung cấp form template như HAL-FORMS. Client phải yêu cầu đúng media type.

**Quên gắn affordance vào link.** Có controller method POST không có nghĩa template sẽ tự xuất hiện. Cần gắn affordance vào link của representation.

**Dùng output DTO làm input payload.** Input metadata được suy ra từ tham số `@RequestBody`, không phải mặc định từ kiểu trả về của method.

**Không khai báo media type đầu vào.** Nếu mapping không có `consumes` và affordance không đặt input media type, template có thể không có `contentType` như mong đợi.

**Cho rằng template là validation phía server.** Metadata chỉ hướng dẫn client; Bean Validation và kiểm tra nghiệp vụ vẫn phải chạy ở endpoint.

**Giả định tên template luôn là default.** Tên phụ thuộc cách đặt tên affordance. Client và test cần đọc template được công bố.

**Cho rằng affordance là cơ chế phân quyền.** Server phải kiểm tra quyền ở mỗi request, kể cả khi client có template từ response cũ.

**Không kiểm thử content negotiation.** Cần xác nhận `Content-Type` thực tế và cấu trúc `_templates` khi client yêu cầu HAL-FORMS.

## 16. Bài tập thực hành và tiêu chí hoàn thành

Hãy mở rộng API quản lý nhân viên để công bố affordance tạo mới:

1. Tạo `EmployeeInput` riêng với các trường `name`, `email` và `department`.
2. Khai báo `POST /employees` nhận `@Valid @RequestBody EmployeeInput` và `consumes = application/json`.
3. Tạo self link cho collection nhân viên bằng `WebMvcLinkBuilder`.
4. Gắn affordance của method POST vào link bằng `andAffordance(afford(methodOn(...)))`.
5. Bật HAL-FORMS và gửi request với `Accept: application/prs.hal-forms+json`.
6. Kiểm tra response có `_links`, `_embedded` và `_templates` theo cấu hình.
7. Kiểm tra template mô tả đúng method, target, content type và property.
8. Thêm validation metadata và options cho `department`.
9. Thử gửi payload sai để xác nhận server vẫn thực thi validation.
10. Thử người dùng không có quyền tạo nhân viên để xác nhận affordance không thay thế bảo mật endpoint.

Bạn đã hiểu HAL-FORMS khi có thể giải thích vì sao định dạng này mở rộng HAL, đọc được cấu trúc `_templates`, tạo affordance từ controller method, mô tả input payload cho client và kiểm thử content negotiation. HAL-FORMS giúp API công bố cách tương tác rõ ràng hơn, để client khám phá thao tác và tạo request dựa trên metadata do server cung cấp.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS Reference Documentation – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
