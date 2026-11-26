# Input payload metadata trong Spring HATEOAS

Một affordance mô tả thao tác mà client có thể thực hiện trên tài nguyên, chẳng hạn tạo nhân viên, cập nhật đơn hàng hoặc tìm kiếm sản phẩm. Với thao tác nhận request body, client cần biết payload phải gửi gồm những trường nào, kiểu dữ liệu ra sao, trường nào bắt buộc và giới hạn hợp lệ là gì. Spring HATEOAS biểu diễn thông tin đó bằng input payload metadata.

Input payload metadata là phần mô tả payload đầu vào của một affordance. Spring HATEOAS có thể suy ra metadata từ kiểu tham số `@RequestBody` trong controller method được gắn với affordance, sau đó chuyển thông tin sang định dạng hypermedia cụ thể. Với HAL-FORMS, metadata này được hiển thị thành các thuộc tính của template và từng form property. Nhờ vậy, client có thể xây dựng biểu mẫu hoặc request phù hợp mà không phải đoán cấu trúc payload.

## 1. Input payload metadata là gì?

`AffordanceModel.InputPayloadMetadata` là abstraction của Spring HATEOAS mô tả payload đi vào server. Nó kế thừa `AffordanceModel.PayloadMetadata`, vì vậy chứa thông tin về kiểu payload và các property của payload; đồng thời bổ sung thông tin media type của request đầu vào.

Trong API, cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Input payload type | Class hoặc kiểu dữ liệu mà controller nhận từ request body, thường là DTO đầu vào. |
| Input payload metadata | Mô tả có cấu trúc về kiểu payload, các property và media type mà affordance cần nhận. |
| Output payload metadata | Mô tả dữ liệu mà thao tác có thể trả về cho client. |

Ví dụ, thao tác tạo nhân viên nhận `EmployeeInput` và trả về `EmployeeView`. Input metadata mô tả các trường của `EmployeeInput`; output metadata mô tả representation `EmployeeView`. Hai kiểu này có thể khác nhau vì dữ liệu client được phép gửi không nhất thiết giống dữ liệu server trả về.

Input payload metadata không phải request body thực tế, không phải DTO và cũng không phải bộ kiểm tra dữ liệu. Nó là thông tin mô tả được gắn vào affordance để media type có thể công bố cách gọi thao tác.

## 2. Spring HATEOAS lấy input payload từ đâu?

Khi tạo affordance bằng cách tham chiếu controller method, Spring HATEOAS phân tích mapping và chữ ký method. Nếu method có tham số `@RequestBody`, kiểu tham số đó được dùng làm mô hình payload đầu vào.

Ví dụ controller:

```java
@RestController
@RequestMapping("/employees")
class EmployeeController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<EmployeeView> createEmployee(
            @Valid @RequestBody EmployeeInput payload) {
        // Tạo nhân viên từ payload và trả representation.
    }

    @GetMapping
    CollectionModel<EntityModel<EmployeeView>> getEmployees() {
        // Trả collection nhân viên.
    }
}
```

Ở đây, `EmployeeInput` là kiểu đầu vào vì nó được gắn với `@RequestBody`. `EmployeeView` là kiểu dữ liệu đầu ra. `@Valid` yêu cầu Spring MVC áp dụng Bean Validation cho payload khi request thật được gửi tới method; annotation này cũng giúp các ràng buộc trên input model có ý nghĩa rõ ràng trong hợp đồng.

Spring HATEOAS không cần gọi method `createEmployee` để lấy metadata. Khi tạo affordance, nó phân tích thông tin method và kiểu tham số. Vì vậy, giá trị `null` thường được truyền vào lời gọi giả lập `methodOn(...)` cho tham số request body.

## 3. Gắn affordance có input payload vào link

Một cách phổ biến là tạo self link cho collection rồi gắn affordance của method POST tạo tài nguyên:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping
CollectionModel<EntityModel<EmployeeView>> getEmployees() {
    CollectionModel<EntityModel<EmployeeView>> model =
            employeeAssembler.toCollectionModel(employeeService.findAll());

    Link employees = linkTo(methodOn(EmployeeController.class).getEmployees())
            .withSelfRel()
            .andAffordance(afford(
                    methodOn(EmployeeController.class).createEmployee(null)
            ));

    model.add(employees);
    return model;
}
```

Link `self` trỏ tới collection nhân viên. Affordance được gắn vào link tham chiếu method `createEmployee(...)`; từ method này, Spring HATEOAS suy ra HTTP method POST, target, input type `EmployeeInput` và output type `EmployeeView`.

Khi client yêu cầu HAL-FORMS, serializer có thể chuyển affordance thành một template trong `_templates`. Nếu client chỉ yêu cầu HAL JSON, link vẫn được biểu diễn theo HAL; HAL cơ bản không hiển thị đầy đủ form property metadata như HAL-FORMS.

## 4. Input payload metadata được thể hiện trong HAL-FORMS

Để bật HAL-FORMS, ứng dụng có thể cấu hình:

```java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Client gửi request với header:

```http
GET /employees HTTP/1.1
Accept: application/prs.hal-forms+json
```

Response HAL-FORMS có thể chứa `_templates` mô tả thao tác tạo nhân viên:

```json
{
  "_links": {
    "self": {
      "href": "/employees"
    }
  },
  "_templates": {
    "createEmployee": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
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

Đây là ví dụ rút gọn. Template thực tế được tạo từ affordance và metadata của input model. Các thuộc tính như `contentType`, `method`, `target`, `title` và `properties` mô tả cách gửi request và những trường payload mà client có thể cung cấp.

HAL-FORMS là media type riêng được xây dựng trên nền HAL. Không nên xem HAL JSON và HAL-FORMS là hai tên gọi thay thế cho nhau: HAL-FORMS bổ sung template để mô tả thao tác và input.

## 5. Khai báo input DTO riêng cho payload

Input model nên phản ánh những trường client được phép gửi. Không nhất thiết dùng domain entity hoặc output representation làm kiểu đầu vào.

Ví dụ:

```java
public class EmployeeInput {

    @NotNull
    @NotBlank
    @Length(min = 2, max = 80)
    private String firstName;

    @NotNull
    @Email
    private String email;

    @Pattern(regexp = "[A-Z]{2}-[0-9]{6}")
    private String employeeCode;

    // Getter và setter.
}
```

DTO này xác định ba property đầu vào. Spring HATEOAS có thể đọc kiểu property và các annotation để xây metadata phù hợp cho media type. Ví dụ, `@NotNull` có thể được dùng để xác định property bắt buộc, `@Email` gợi ý loại input email và `@Pattern` cung cấp biểu thức chính quy.

Việc dùng DTO riêng giúp kiểm soát rõ payload mà client được phép gửi. Các trường như `id`, `createdAt`, `approvedBy` hoặc dữ liệu nội bộ do server quản lý không nên xuất hiện như trường có thể chỉnh sửa nếu client không được phép thay đổi chúng.

## 6. Metadata required và readOnly

HAL-FORMS có thể mô tả liệu một property có bắt buộc gửi hay có thể được chỉnh sửa hay không.

**required** thường được suy ra từ Bean Validation `@NotNull`. Nếu template dùng HTTP PATCH, Spring HATEOAS tự đặt các property thành không bắt buộc, phù hợp với thao tác cập nhật một phần. Các giá trị mặc định thường được lược bỏ khi serialize để response gọn hơn.

**readOnly** được đặt thành `true` nếu property không có setter. Có thể đánh dấu tường minh bằng Jackson `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` trên field hoặc accessor:

```java
public class EmployeeInput {

    private UUID id;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    public UUID getId() {
        return id;
    }

    // Không cung cấp setter cho id.
}
```

Nếu property là read-only, client không nên gửi nó trong payload thay đổi trạng thái. Tuy nhiên, metadata read-only trong form chỉ hướng dẫn client; server vẫn phải kiểm soát việc bind dữ liệu và từ chối hoặc bỏ qua trường không được phép theo chính sách của ứng dụng.

## 7. Metadata regex, min, max và độ dài

Các ràng buộc validation có thể được chuyển thành thuộc tính của form property. Một số ánh xạ thường gặp:

| Annotation hoặc nguồn metadata | Thuộc tính HAL-FORMS | Ý nghĩa |
| --- | --- | --- |
| `@Pattern` | `regex` | Giá trị phải khớp biểu thức chính quy. |
| `@NotNull` | `required` | Property phải có giá trị trong payload. |
| `@Min`, `@DecimalMin` | `min` | Giới hạn số tối thiểu. |
| `@Max`, `@DecimalMax` | `max` | Giới hạn số tối đa. |
| Hibernate Validator `@Length` | `minLength`, `maxLength` | Giới hạn độ dài chuỗi. |
| JSR-303 `@Size` và Hibernate Validator `@Range` | Các giới hạn phù hợp với kiểu property | Mô tả giới hạn kích thước hoặc khoảng giá trị. |

Ví dụ:

```java
public class EmployeeInput {

    @NotNull
    @Min(18)
    @Max(70)
    private Integer age;

    @Pattern(regexp = "[A-Z]{2}-[0-9]{6}")
    private String employeeCode;

    @Length(min = 2, max = 80)
    private String firstName;
}
```

HAL-FORMS có thể công bố giới hạn này để client kiểm tra và tạo giao diện nhập liệu thuận tiện. Server vẫn cần Bean Validation và xử lý lỗi thực tế; client có thể gửi request không tuân thủ metadata hoặc cố ý bỏ qua form.

## 8. Metadata type và InputType

Loại input có thể được suy ra từ kiểu Java hoặc annotation validation. Ví dụ `String` thường được hiển thị dưới dạng text, `LocalDate` có thể thành date và `@Email` có thể gợi ý email input.

Nếu muốn chỉ định rõ loại input, Spring HATEOAS cung cấp annotation `@InputType`:

```java
public class EmployeeInput {

    @InputType("email")
    private String contactAddress;

    @InputType("date")
    private LocalDate startDate;
}
```

`@InputType` cho phép ghi đè loại input được suy ra tự động. Giá trị thường tương ứng với loại input HTML mà media type có thể biểu diễn, nhưng annotation không giới hạn cách một media type tùy chỉnh sử dụng giá trị này.

Chỉ định type rõ ràng hữu ích khi kiểu Java chưa đủ để suy ra cách nhập phù hợp. Hãy chọn loại input tương thích với client và media type mà API công bố.

## 9. Metadata media type của input payload

Input payload metadata còn mô tả media type mà server mong đợi nhận. Trong HAL-FORMS, thuộc tính `contentType` của template chỉ xuất hiện khi mapping controller khai báo `consumes` hoặc affordance được cấu hình media type đầu vào một cách tường minh.

Ví dụ controller:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
EntityModel<EmployeeView> createEmployee(
        @RequestBody EmployeeInput payload) {
    // Xử lý payload JSON.
}
```

Mapping `consumes` cho biết thao tác nhận `application/json`. Khi tạo affordance từ method này, Spring HATEOAS có thể đưa content type vào metadata của template.

Nếu tạo affordance thủ công, có thể đặt input type và media type:

```java
Link createEmployee = Affordances.of(Link.of("/employees", "employees"))
        .afford(HttpMethod.POST)
        .withInput(EmployeeInput.class)
        .withInputMediaType(MediaType.APPLICATION_JSON)
        .withName("createEmployee")
        .toLink();
```

`withInput(...)` đăng ký kiểu payload đầu vào; `withInputMediaType(...)` khai báo media type mong đợi. Có thể dùng `withInputMediaTypes(...)` nếu thao tác chấp nhận nhiều media type. Cách tạo thủ công hữu ích khi không thể suy ra affordance trực tiếp từ controller method hoặc khi muốn kiểm soát rõ metadata.

## 10. Phân biệt input payload với query parameter và output payload

Không phải mọi tham số của controller đều là input payload property:

| Tham số controller | Vai trò trong request | Nơi mô tả trong affordance |
| --- | --- | --- |
| `@PathVariable` | Thành phần URI xác định tài nguyên hoặc target. | URI của link/affordance. |
| `@RequestParam` | Tham số query của request. | Query parameter metadata. |
| `@RequestBody` | Nội dung body gửi tới server. | Input payload metadata. |
| Kiểu trả về của method | Dữ liệu server trả về. | Output payload metadata. |

Ví dụ method tìm kiếm có thể nhận `@RequestParam String name` mà không có request body. Khi đó, tên tìm kiếm là query parameter chứ không phải property trong input payload. Ngược lại, method POST nhận `@RequestBody EmployeeInput` sẽ tạo metadata cho các trường của `EmployeeInput`.

Nếu một thao tác không có request body, input payload metadata có thể là `NONE`; affordance vẫn có thể có query parameters. Nếu một thao tác nhận cả path variable, query parameter và body, từng phần cần được mô tả đúng vị trí của nó.

## 11. Tùy chỉnh options, prompt và placeholder

Ngoài kiểu và ràng buộc, HAL-FORMS có thể công bố danh sách lựa chọn, nhãn hướng dẫn và placeholder cho property.

Với property có tập giá trị hữu hạn, có thể dùng `HalFormsConfiguration` để khai báo options:

```java
@Configuration
class HalFormsOptionsConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        HalFormsConfiguration configuration = new HalFormsConfiguration();
        configuration.withOptions(EmployeeInput.class, "department",
                metadata -> HalFormsOptions.inline("Engineering", "Finance", "Sales"));
        return configuration;
    }
}
```

Trong ví dụ, property `department` có thể được hiển thị như lựa chọn từ danh sách. Với danh sách thay đổi theo dữ liệu server, `HalFormsOptions.remote(...)` có thể trỏ tới tài nguyên cung cấp lựa chọn.

Các thuộc tính hiển thị cho người dùng như title, prompt và placeholder có thể được quốc tế hóa bằng resource bundle `rest-messages` mà Spring HATEOAS cấu hình mặc định. Ví dụ:

```properties
createEmployee._template.title=Create employee
EmployeeInput.firstName._prompt=First name
EmployeeInput.firstName._placeholder=Enter the employee's first name
```

Tên key chính xác cần khớp tên affordance và kiểu input model mà ứng dụng sử dụng. Có thể dùng key theo tên kiểu đầy đủ nếu nhiều model có property trùng tên.

## 12. InputPayloadMetadata trong API mở rộng media type

Trong ứng dụng thông thường, bạn hiếm khi cần tự tạo một implementation của `AffordanceModel.InputPayloadMetadata`. Thường bạn khai báo controller method, input DTO và các annotation; Spring HATEOAS xây metadata để media type sử dụng.

Tuy nhiên, nếu đang phát triển một media type tùy chỉnh, abstraction này rất quan trọng. `ConfiguredAffordance` cung cấp `getInputMetadata()` để media type implementation đọc metadata đầu vào; `getOutputMetadata()` cung cấp metadata đầu ra riêng.

Một số API chính của input metadata:

| API | Ý nghĩa |
| --- | --- |
| `getType()` | Kiểu payload, kế thừa từ `PayloadMetadata`. |
| `stream()` | Duyệt các property metadata của payload. |
| `getMediaTypes()` | Danh sách media type đầu vào được hỗ trợ hoặc mong đợi. |
| `getPrimaryMediaType()` | Media type đầu tiên nếu có; có thể không có giá trị. |
| `getI18nCodes()` | Các mã dùng để tra tên payload qua cơ chế quốc tế hóa. |
| `withMediaTypes(...)` | Tạo metadata mới với danh sách media type được chỉ định. |

`AffordanceModel.PropertyMetadata` mô tả từng property như tên, kiểu, input type, required, read-only, pattern, min/max và độ dài. Media type implementation có thể dùng thông tin này để chuyển sang cấu trúc đặc thù của định dạng đó.

Khi xây media type riêng, không nên giả định mọi input đều là một Java class thông thường. API metadata được thiết kế để media type có thể làm việc với abstraction payload và property, thay vì chỉ phụ thuộc trực tiếp vào `ResolvableType`.

## 13. Input metadata không thay thế validation và bảo mật

Metadata giúp client biết cách tạo payload, nhưng không phải cơ chế thực thi quy tắc nghiệp vụ. Một client có thể bỏ qua `required`, gửi sai regex hoặc tự thêm trường không được công bố.

Server vẫn cần:

- Dùng DTO đầu vào với các trường được phép ghi.
- Kích hoạt Bean Validation bằng `@Valid` khi cần.
- Kiểm tra quyền và trạng thái nghiệp vụ trong service.
- Không tin các trường định danh hoặc audit do client gửi nếu chúng thuộc quyền quản lý của server.
- Trả lỗi validation theo hợp đồng API, ví dụ status phù hợp và Problem Details nếu ứng dụng hỗ trợ.
- Kiểm thử request sai dữ liệu, thiếu trường bắt buộc và giá trị vượt giới hạn.

Việc ẩn một property khỏi HAL-FORMS không bảo đảm client không thể gửi property đó. Tương tự, `readOnly` là metadata hướng dẫn giao diện; server phải kiểm soát dữ liệu được bind và cập nhật.

## 14. Kiểm thử input payload metadata

Nên kiểm thử hai phần: affordance được tạo từ đúng controller method và metadata được serialize đúng theo media type.

Với MockMvc, gọi endpoint collection bằng HAL-FORMS:

```java
mockMvc.perform(get("/employees")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._templates.createEmployee.method").value("post"))
    .andExpect(jsonPath("$._templates.createEmployee.contentType")
            .value(MediaType.APPLICATION_JSON_VALUE))
    .andExpect(jsonPath("$._templates.createEmployee.properties[?(@.name == 'firstName')]")
            .exists());
```

Tên template có thể là `default` khi chỉ có một affordance hoặc được đặt theo tên method/tên đã cấu hình. Hãy dùng đúng tên template trong response của ứng dụng.

Ngoài ra, nên kiểm tra:

- `required` được tạo theo `@NotNull` và quy tắc PATCH.
- `readOnly` được tạo cho property không có setter hoặc được đánh dấu Jackson READ_ONLY.
- `regex`, min/max và giới hạn độ dài phản ánh annotation trên input model.
- `type` phản ánh kiểu property hoặc `@InputType`.
- `contentType` phản ánh `consumes` hoặc cấu hình input media type tường minh.
- Query parameter không bị nhầm thành property của request body.
- Output payload metadata không bị nhầm với input payload metadata.
- Request thực tế vẫn bị server từ chối khi vi phạm validation hoặc quyền truy cập.

## 15. Các lỗi thường gặp

**Dùng output DTO làm input model.** Kiểu trả về không nhất thiết là kiểu request body. Hãy kiểm tra tham số `@RequestBody` của method được gắn affordance.

**Cho rằng input metadata là request body thật.** Đây chỉ là mô tả để media type tạo affordance; payload thật được gửi ở request sau đó.

**Quên khai báo `consumes`.** HAL-FORMS có thể không hiển thị `contentType` nếu mapping không khai báo media type nhận và affordance cũng không đặt media type tường minh.

**Nhầm query parameter với payload property.** `@RequestParam` được mô tả như query parameter; `@RequestBody` tạo input payload metadata.

**Dùng domain entity làm input model.** Điều này có thể để lộ trường nội bộ và khiến client gửi dữ liệu không được phép thay đổi. Tạo DTO đầu vào riêng.

**Cho rằng metadata tự validate request.** Cần `@Valid`, Bean Validation và kiểm tra nghiệp vụ ở server.

**Không kiểm thử HAL-FORMS.** HAL JSON thông thường không chứng minh input metadata được serialize đúng. Gửi `Accept: application/prs.hal-forms+json` trong test.

**Tự tạo InputPayloadMetadata khi không cần.** Với ứng dụng thông thường, để Spring HATEOAS suy ra metadata từ controller và input DTO. Chỉ làm việc trực tiếp với abstraction này khi xây media type hoặc affordance tùy chỉnh.

## 16. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng API quản lý nhân viên có affordance tạo và cập nhật:

1. Tạo `EmployeeInput` riêng cho request body, không dùng domain entity làm payload.
2. Khai báo `POST /employees` nhận `@Valid @RequestBody EmployeeInput` và `consumes = application/json`.
3. Định nghĩa `@NotNull`, `@Email`, `@Pattern`, giới hạn độ dài và `@InputType` phù hợp trên các property.
4. Gắn affordance của method POST vào self link collection bằng `andAffordance(afford(methodOn(...)))`.
5. Yêu cầu HAL-FORMS và kiểm tra `_templates`, `method`, `contentType` và `properties`.
6. Thêm affordance PATCH với cùng input model hoặc input model phù hợp, sau đó xác nhận property không bắt buộc theo quy tắc PATCH.
7. Thử cấu hình options, prompt và placeholder cho một property.
8. Viết test gửi payload thiếu trường hoặc sai định dạng và xác nhận server vẫn thực hiện validation.
9. Phân biệt input metadata, output metadata và query parameter trong response affordance.

Bạn đã hiểu input payload metadata khi có thể xác định đúng kiểu request body từ controller, tạo affordance gắn với thao tác nhận payload, mô tả property bằng validation và input type, công bố media type, đọc cấu trúc HAL-FORMS và phân biệt metadata hướng dẫn client với validation thực tế trên server. Đây là nền tảng để API mô tả thao tác một cách đủ rõ để client tạo request đúng mà không phải đoán payload.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference Documentation – Defining HAL-FORMS metadata](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms.metadata)
- [AffordanceModel.InputPayloadMetadata API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/AffordanceModel.InputPayloadMetadata.html)
- [AffordanceModel.PropertyMetadata API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/AffordanceModel.PropertyMetadata.html)
- [InputType API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/InputType.html)
