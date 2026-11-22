# Document validation constraints từ Bean Validation

## 1. Mục tiêu: biến quy tắc validation thành một phần của API documentation

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Với API nhận JSON, người tích hợp cần biết field nào bắt buộc, độ dài tối đa, định dạng email, giới hạn số lượng và các quy tắc nghiệp vụ liên quan. Những quy tắc này thường được khai báo bằng Bean Validation annotations như `@NotNull`, `@NotBlank`, `@Size`, `@Email`, `@Min` hoặc `@Positive` trên DTO.

Nếu chỉ document tên, kiểu và mô tả field, người đọc có thể biết `email` là chuỗi nhưng không biết nó phải đúng định dạng email; biết `name` là chuỗi nhưng không biết giới hạn độ dài. Bài thực hành này kết hợp metadata Bean Validation với Spring REST Docs để đưa các constraints vào bảng `request-fields`.

Kết quả mong muốn:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| `name` | String | Tên hiển thị của khách hàng | Không được để trống; tối đa 80 ký tự |
| `email` | String | Địa chỉ email | Phải có định dạng email hợp lệ |
| `age` | Number | Tuổi | Phải lớn hơn hoặc bằng 18 |

Spring REST Docs có tiện ích `ConstraintDescriptions` để đọc constraints từ class/property và cung cấp mô tả dạng text. Test vẫn phải kiểm chứng request và validation behavior; việc đưa constraint vào snippet giúp tài liệu phản ánh metadata được khai báo trong DTO.

## 2. Khai báo Bean Validation trên request DTO

Ví dụ API tạo khách hàng:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotBlank
        @Email
        String email,

        @Min(18)
        Integer age
) {
}
```

Các annotation mô tả quy tắc:

| Annotation | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị không được là `null`. |
| `@NotBlank` | Chuỗi không được `null`, rỗng hoặc chỉ gồm whitespace. |
| `@NotEmpty` | Chuỗi/collection/map/array không được `null` hoặc rỗng; whitespace trong chuỗi vẫn có thể được chấp nhận. |
| `@Size(max = 80)` | Kích thước nằm trong giới hạn; với chuỗi là số ký tự, với collection là số phần tử. |
| `@Email` | Giá trị phải thỏa định dạng email theo validator đang dùng. |
| `@Min(18)` | Giá trị số phải lớn hơn hoặc bằng 18. |
| `@Positive` | Giá trị phải lớn hơn 0. |

Lưu ý: `@Size` thường cho phép `null`; nếu field bắt buộc, kết hợp với `@NotNull` hoặc `@NotBlank` phù hợp. `@Email` cũng không tự thay thế `@NotBlank` nếu field không được phép bỏ trống. Chọn tổ hợp annotation theo đúng contract của endpoint.

## 3. Bật validation ở tầng HTTP

Để constraints được thực thi khi client gửi request, controller cần kích hoạt validation cho request body. Với Spring MVC:

```java
@RestController
@RequestMapping("/api/customers")
class CustomerController {

    @PostMapping
    ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse created = customerService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Ứng dụng cần Bean Validation implementation tương thích với phiên bản Spring/Jakarta Validation đang sử dụng. Với Spring Boot, dependency validation starter thường cung cấp integration cần thiết.

Đừng nhầm việc DTO có annotation với việc validation chắc chắn được thực thi. Nếu controller thiếu `@Valid`/`@Validated` ở vị trí phù hợp, hoặc validation provider không có trên classpath, request có thể không bị từ chối như tài liệu mô tả.

## 4. Đọc constraint descriptions bằng Spring REST Docs

Spring REST Docs cung cấp `ConstraintDescriptions` trong package `org.springframework.restdocs.constraints`:

```java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateCustomerRequest.class);

List<String> nameConstraints = constraints.descriptionsForProperty("name");
```

`descriptionsForProperty("name")` trả về danh sách mô tả constraint gắn với property `name`. Theo mặc định, resolver của Spring REST Docs tìm mô tả dựa trên constraint annotation và resource bundle của Spring REST Docs. Nếu không có mô tả tùy chỉnh, mô tả mặc định của constraint được sử dụng.

Có thể kiểm tra nhanh nội dung:

```java
System.out.println(constraints.descriptionsForProperty("name"));
```

Kết quả cụ thể phụ thuộc annotation, provider và resource bundle. Đừng phụ thuộc vào thứ tự hoặc câu chữ mặc định nếu tài liệu cần wording tiếng Việt ổn định; hãy định nghĩa mô tả riêng theo phần tiếp theo.

## 5. Tùy chỉnh mô tả constraints bằng resource bundle

Để tài liệu tiếng Việt dùng từ ngữ nhất quán, tạo resource bundle theo cơ chế constraint description resolver của Spring REST Docs. Một vị trí thường dùng là resource bundle `org/springframework/restdocs/constraints/ConstraintDescriptions.properties` trong test resources; có thể cung cấp biến thể locale như `ConstraintDescriptions_vi.properties` tùy cách ứng dụng chọn locale/resource bundle.

Ví dụ nội dung bundle:

```properties
NotBlank=Không được để trống hoặc chỉ chứa khoảng trắng
NotNull=Không được để trống
NotEmpty=Không được là null hoặc rỗng
Size=Kích thước phải nằm trong giới hạn cho phép
Email=Phải có định dạng email hợp lệ
Min=Phải lớn hơn hoặc bằng giá trị tối thiểu
Positive=Phải là số dương
```

Tên key cần khớp cách resolver đang tra cứu trong version Spring REST Docs của dự án. Nếu dùng annotation tùy chỉnh hoặc muốn mô tả theo từng property, cấu hình `ConstraintDescriptionResolver` phù hợp thay vì giả định mọi resolver đều dùng cùng một quy ước key.

Với mô tả theo locale, kiểm tra bundle thực tế được nạp trong test runtime. Đặt file ở đúng resource path, bảo đảm nó được copy vào test classpath và không bị bundle khác có độ ưu tiên cao hơn che khuất.

## 6. Tích hợp constraints vào field descriptors

Spring REST Docs không tự động thêm một cột “Constraints” vào mọi `request-fields` snippet chỉ vì DTO có Bean Validation annotations. Ta cần lấy descriptions và đưa chúng vào description của field descriptor hoặc cấu trúc tài liệu tùy chỉnh.

Ví dụ helper:

```java
private static String descriptionWithConstraints(
        String description, List<String> constraints) {
    if (constraints.isEmpty()) {
        return description;
    }
    return description + ". Constraints: " + String.join("; ", constraints);
}
```

Dùng trong test:

```java
ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateCustomerRequest.class);

mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
        .andExpect(status().isCreated())
        .andDo(document("customers-create",
                requestFields(
                        fieldWithPath("name")
                                .description(descriptionWithConstraints(
                                        "Tên hiển thị của khách hàng",
                                        constraints.descriptionsForProperty("name"))),
                        fieldWithPath("email")
                                .description(descriptionWithConstraints(
                                        "Địa chỉ email",
                                        constraints.descriptionsForProperty("email"))),
                        fieldWithPath("age")
                                .description(descriptionWithConstraints(
                                        "Tuổi khách hàng",
                                        constraints.descriptionsForProperty("age"))))));
```

Snippet `request-fields.adoc` sẽ chứa mô tả field kèm constraints trong cột Description. Cách này đơn giản, không cần thay đổi snippet template. Nếu muốn một cột riêng cho constraints, cần custom snippet template hoặc tự tạo bảng AsciiDoc từ metadata; không có cột riêng tự sinh chỉ bằng `ConstraintDescriptions`.

## 7. Tái sử dụng descriptors để tránh lặp

Khi nhiều test document cùng DTO, nên đóng gói field descriptors hoặc helper dùng chung. Ví dụ:

```java
final class CustomerRequestDocumentation {

    private static final ConstraintDescriptions CONSTRAINTS =
            new ConstraintDescriptions(CreateCustomerRequest.class);

    private static String describe(String text, String property) {
        List<String> descriptions = CONSTRAINTS.descriptionsForProperty(property);
        return descriptions.isEmpty()
                ? text
                : text + ". Constraints: " + String.join("; ", descriptions);
    }

    static FieldDescriptor[] fields() {
        return new FieldDescriptor[] {
                fieldWithPath("name").description(describe("Tên khách hàng", "name")),
                fieldWithPath("email").description(describe("Email liên hệ", "email")),
                fieldWithPath("age").description(describe("Tuổi", "age"))
        };
    }
}
```

Trong test:

```java
andDo(document("customers-create",
        requestFields(CustomerRequestDocumentation.fields())));
```

Ví dụ trên minh họa ý tưởng tổ chức code; cần import static `fieldWithPath` và `FieldDescriptor`, đồng thời có thể thay helper bằng builder phù hợp style dự án. Không nên tạo static cache nếu test cần resolver/locale khác nhau theo runtime; trong trường hợp đó, inject hoặc khởi tạo descriptions theo cấu hình test.

## 8. Document constraints lồng nhau và collection

DTO có thể chứa object con:

```java
public record AddressRequest(
        @NotBlank @Size(max = 120) String street,
        @NotBlank @Size(max = 60) String city,
        @Pattern(regexp = "[0-9]{5}") String postalCode) {
}

public record CreateCustomerRequest(
        @NotBlank @Size(max = 80) String name,
        @Valid AddressRequest address) {
}
```

Khi document `address.street`, `address.city`, hãy đọc constraints từ class chứa property `AddressRequest`, không phải từ root DTO:

```java
ConstraintDescriptions addressConstraints =
        new ConstraintDescriptions(AddressRequest.class);

fieldWithPath("address.street").description(
        descriptionWithConstraints("Tên đường", addressConstraints.descriptionsForProperty("street")))
```

Đối với collection, descriptor path của payload có thể là `items[].quantity`; class chứa annotation là kiểu phần tử collection. Cần lấy `ConstraintDescriptions` từ class phần tử tương ứng. Nếu property là container element constraint hoặc dùng annotation ở type-use, xác nhận phiên bản Bean Validation/provider và Spring REST Docs có đọc được metadata đó như mong đợi; không giả định mọi vị trí annotation đều được resolver hỗ trợ giống nhau.

## 9. Document constraints cho validation errors

API nên document cả response khi request không hợp lệ. Ví dụ controller trả `400 Bad Request` với danh sách field errors:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "message": "Phải có định dạng email hợp lệ"
    }
  ]
}
```

Test có thể document operation lỗi riêng:

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"An","email":"invalid","age":17}
                        """))
        .andExpect(status().isBadRequest())
        .andDo(document("customers-create-validation-error",
                responseFields(
                        fieldWithPath("code").description("Mã lỗi"),
                        fieldWithPath("errors[].field").description("Tên field không hợp lệ"),
                        fieldWithPath("errors[].message").description("Thông báo validation"))));
```

Thông báo lỗi thực tế có thể khác resource bundle mô tả constraints. Constraint description giải thích quy tắc của field; validation error message mô tả lỗi cụ thể trong response. Hai phần có liên quan nhưng không nên đánh đồng.

## 10. Kiểm chứng constraints bằng test hợp lệ và không hợp lệ

Tài liệu chỉ đáng tin khi test xác nhận cả hai phía:

**Request hợp lệ:**

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"An","email":"an@example.com","age":25}
                        """))
        .andExpect(status().isCreated())
        .andDo(document("customers-create",
                requestFields(CustomerRequestDocumentation.fields())));
```

**Request không hợp lệ:**

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":" ","email":"invalid","age":15}
                        """))
        .andExpect(status().isBadRequest())
        .andDo(document("customers-create-invalid",
                requestFields(CustomerRequestDocumentation.fields()),
                responseFields(
                        fieldWithPath("code").description("Mã lỗi"),
                        fieldWithPath("errors[].field").description("Field không hợp lệ"),
                        fieldWithPath("errors[].message").description("Thông báo lỗi"))));
```

Hai test cần phù hợp với error handling thực tế của ứng dụng. Nếu validation errors được chuyển thành một schema khác, cập nhật response descriptors tương ứng. Đảm bảo test thực sự kích hoạt validation bằng `@Valid` và validation provider.

## 11. Phân biệt constraint description và validation message

Bean Validation có thể dùng `message` trên annotation:

```java
@NotBlank(message = "Tên không được để trống")
@Size(max = 80, message = "Tên tối đa 80 ký tự")
String name
```

`ConstraintDescriptions` cung cấp mô tả constraint cho tài liệu; validation provider dùng message khi constraint thất bại. Hai hệ thống có mục đích khác nhau:

| Nội dung | Mục đích | Ví dụ |
| --- | --- | --- |
| Constraint description | Giải thích quy tắc field trong API reference. | “Không được để trống; tối đa 80 ký tự.” |
| Validation message | Thông báo cho client/người dùng khi dữ liệu vi phạm. | “Tên không được để trống.” |
| Error response | Hợp đồng HTTP khi request không hợp lệ. | `400` với `field` và `message`. |

Nếu muốn cùng một câu chữ ở tài liệu và response, cần thiết kế message/resource bundle có chủ đích và test cả hai. Không giả định `ConstraintDescriptions` tự lấy đúng message đã gắn trong annotation ở mọi cấu hình.

## 12. Những giới hạn cần lưu ý

- `ConstraintDescriptions` đọc metadata constraint; nó không chạy validator và không chứng minh endpoint đang thực thi validation.
- Custom class-level constraint có thể không gắn trực tiếp với một field cụ thể. Cần document ở cấp object hoặc mô tả quy tắc nghiệp vụ riêng.
- Cross-field validation (ví dụ `startDate` phải trước `endDate`) thường cần class-level validator; không ép mô tả thành constraint của một field nếu điều đó gây hiểu nhầm.
- Constraint trên getter/property access, field access, container element hoặc type-use cần kiểm tra theo provider và version.
- Constraint mô tả độ dài/giá trị có thể phụ thuộc nhóm validation (validation groups). `ConstraintDescriptions` không tự chọn nhóm request đang được controller sử dụng.
- Annotation tùy chỉnh cần description resolver/resource bundle phù hợp; nếu không có, mô tả có thể thiếu hoặc dùng fallback không đủ rõ.
- Không document constraint nội bộ không thuộc public contract nếu điều đó làm lộ chi tiết triển khai không cần thiết.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `descriptionsForProperty` trả danh sách rỗng | Property không có constraint, sai property name hoặc resolver không tìm được metadata. | Kiểm tra DTO, getter/field access và tên property. |
| Constraint description là tiếng Anh | Resource bundle tiếng Việt chưa được nạp hoặc key không khớp. | Kiểm tra bundle path, locale và resolver lookup. |
| Test pass nhưng validation không chạy | Controller thiếu `@Valid`/`@Validated` hoặc thiếu provider. | Kiểm tra HTTP test invalid và dependency validation. |
| Request fields snippet không có constraint | Field descriptor vẫn dùng description tĩnh. | Kết hợp `ConstraintDescriptions` vào descriptor description. |
| Field nested không có mô tả | Đọc constraints từ root DTO thay vì class con. | Tạo `ConstraintDescriptions` cho nested type. |
| Optional field bị mô tả là bắt buộc | DTO annotation hoặc mô tả chưa phản ánh contract. | Kiểm tra `@NotNull`/`@NotBlank`, groups và optionality thực tế. |
| Error response message khác constraint description | Hai hệ thống phục vụ mục đích khác nhau. | Document rule và error message riêng, test cả hai. |
| Custom constraint không có description | Resolver/bundle không có mapping cho annotation. | Bổ sung mô tả hoặc custom resolver. |
| Constraint group không khớp request | Controller validate group khác với mặc định. | Document group thực tế và test behavior tương ứng. |

## 14. Checklist thực hành

- [ ] DTO request có Bean Validation annotations đúng với API contract.
- [ ] Controller kích hoạt validation bằng `@Valid`/`@Validated` phù hợp.
- [ ] Validation provider có trên runtime classpath.
- [ ] `ConstraintDescriptions` đọc đúng class và property.
- [ ] Resource bundle mô tả constraints có locale/ngôn ngữ phù hợp.
- [ ] Field descriptors đưa constraint descriptions vào snippet.
- [ ] Nested properties lấy metadata từ đúng nested type.
- [ ] Class-level/cross-field constraints được giải thích ở cấp phù hợp.
- [ ] Test request hợp lệ và không hợp lệ xác nhận behavior thực tế.
- [ ] Validation error response được document riêng nếu thuộc public contract.
- [ ] Đã phân biệt constraint descriptions với validation messages.
- [ ] Generated `request-fields.adoc` và HTML/PDF cuối hiển thị đúng mô tả.

Kết hợp Bean Validation với Spring REST Docs giúp API reference mô tả rõ hơn các điều kiện đầu vào mà client phải tuân thủ. `ConstraintDescriptions` cung cấp mô tả từ metadata; field descriptors đưa nội dung đó vào snippets; HTTP tests xác nhận endpoint thực sự chấp nhận hoặc từ chối request theo quy tắc. Giữ riêng constraint description, validation error message và error response sẽ giúp tài liệu chính xác, dễ hiểu và có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring REST Docs – Constraint Descriptions](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs – ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
