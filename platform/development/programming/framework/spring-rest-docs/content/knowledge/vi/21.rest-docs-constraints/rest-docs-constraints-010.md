# Đồng bộ validation runtime và tài liệu với Spring REST Docs

## 1. Vì sao validation và tài liệu phải đồng bộ?

Một API tạo khách hàng có thể nhận JSON như sau:

```http
POST /api/customers HTTP/1.1
Content-Type: application/json

{
  "name": "Nguyen An",
  "email": "an@example.test",
  "age": 28
}
```

Contract có thể quy định:

- name không được để trống và tối đa 100 ký tự.
- email phải có định dạng email hợp lệ.
- age phải nằm trong khoảng từ 18 đến 120.

Nếu tài liệu chỉ liệt kê tên field mà không giải thích giới hạn, người tích hợp có thể gửi dữ liệu bị server từ chối. Ngược lại, nếu tài liệu nói age là tùy chọn nhưng controller thực tế yêu cầu field này, tài liệu và hành vi runtime đã mâu thuẫn.

Spring REST Docs sinh snippet từ request/response trong kiểm thử HTTP. Các descriptor như fieldWithPath(...) mô tả cấu trúc payload; chúng không tự thực thi Jakarta Bean Validation, không tự suy ra mọi giới hạn nghiệp vụ từ annotation và không tự kiểm tra rằng phần mô tả văn bản khớp với validator. Muốn tài liệu đáng tin cậy, cần đồng bộ:

1. **Validation runtime:** quy tắc thật được thực thi trong ứng dụng.
2. **Test:** request hợp lệ và không hợp lệ chứng minh hành vi.
3. **Documentation:** descriptor và snippet giải thích đúng field, ràng buộc và error response.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP dùng MockMvc, WebTestClient hoặc REST Assured, rồi biên soạn snippet thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Constraints**, hướng dẫn đồng bộ validation runtime và tài liệu trong quy trình đó.

Sau bài học, bạn có thể:

1. Khai báo validation bằng Jakarta Bean Validation trong request model.
2. Kích hoạt validation ở controller và kiểm thử kết quả thực tế.
3. Mô tả giới hạn field trong Spring REST Docs bằng descriptor attributes hoặc nội dung description.
4. Document cả request hợp lệ và error response do validation.
5. Đưa kiểm thử và sinh tài liệu vào CI để phát hiện contract drift.

## 2. Validation runtime và descriptor có vai trò khác nhau

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Bean Validation | Thực thi quy tắc trên object | @NotBlank, @Email, @Size, @Min, @Max |
| Spring MVC/WebFlux binding | Chuyển request thành tham số/object và kích hoạt validation | @Valid @RequestBody |
| Test HTTP | Gửi dữ liệu, xác nhận status và response | MockMvc andExpect(...) |
| Spring REST Docs descriptor | Mô tả field, kiểu, ý nghĩa và constraint đã xác định | fieldWithPath("email").description(...) |
| Error response snippet | Công bố cấu trúc lỗi thực tế | responseFields(...) |
| Asciidoctor/Markdown | Ghép snippet vào hướng dẫn API | include::{snippets}/... |

Ví dụ descriptor:

```java
fieldWithPath("email")
    .description("Địa chỉ email của khách hàng")
```

chỉ mô tả field. Nó không tương đương với validator:

```java
@Email
@NotBlank
String email
```

Nếu validator thay đổi từ tối đa 100 ký tự thành tối đa 80 ký tự, nội dung description cũng phải được xem xét cập nhật. Spring REST Docs không thể tự suy ra ý nghĩa nghiệp vụ của tất cả annotation rồi bảo đảm văn bản là chính xác.

## 3. Khai báo constraint trong request model

Ví dụ dùng Jakarta Bean Validation:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 100)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @Min(18)
        @Max(120)
        Integer age
) {}
```

Các annotation thể hiện quy tắc ở mức dữ liệu:

| Constraint | Quy tắc thường gặp | Lưu ý |
| --- | --- | --- |
| @NotNull | Giá trị không được là null | Không tự cấm chuỗi rỗng hoặc khoảng trắng |
| @NotBlank | Chuỗi không được null và phải chứa ít nhất một ký tự không phải khoảng trắng | Dùng cho text bắt buộc |
| @NotEmpty | Chuỗi, collection hoặc array không được null/rỗng | Chuỗi chỉ có khoảng trắng vẫn có thể qua |
| @Size(min, max) | Giới hạn kích thước chuỗi/collection/array | Không thay thế @NotNull |
| @Email | Kiểm tra chuỗi theo quy tắc email của provider | Không chứng minh địa chỉ tồn tại hoặc nhận thư được |
| @Min, @Max | Giới hạn giá trị số phù hợp | Kiểm tra biên dưới/trên |
| @DecimalMin, @DecimalMax | Giới hạn giá trị số thập phân | Có thuộc tính inclusive |
| @Positive, @PositiveOrZero | Giá trị dương hoặc không âm | Chọn theo domain |
| @Pattern | Chuỗi phải khớp regular expression | Regex phải phản ánh đúng contract |

Không phải mọi constraint đều áp dụng cho mọi kiểu dữ liệu. Đọc Javadoc của annotation và provider đang dùng, đồng thời viết test tại các giá trị biên.

### 3.1. Ràng buộc bắt buộc và tính optional trong tài liệu

Một field có @NotBlank thường không thể được gửi dưới dạng null, chuỗi rỗng hoặc chỉ khoảng trắng nếu validation được kích hoạt. Trong Spring REST Docs, không đánh dấu descriptor đó là optional chỉ vì một test fixture không có field.

Ngược lại, field age trong ví dụ là Integer không có @NotNull; nếu contract cho phép vắng mặt, tài liệu nên thể hiện rõ điều đó. Tuy nhiên, @Min(18)/@Max(120) chỉ kiểm tra khi có giá trị không null; chúng không tự biến age thành bắt buộc.

Mỗi field cần phân biệt ba khía cạnh:

- **Presence:** field có được phép vắng trong JSON không?
- **Nullability:** nếu key có mặt, giá trị null có được chấp nhận không?
- **Value constraint:** nếu có giá trị, phạm vi hoặc định dạng hợp lệ là gì?

optional() trong descriptor hỗ trợ mô tả field có thể vắng trong payload snippet. Nó không tự định nghĩa nullability hoặc validation nghiệp vụ. Description phải nêu rõ những điều này khi người tích hợp cần biết.

## 4. Kích hoạt validation trong controller

Với Spring MVC, request body cần được bind và validation kích hoạt, ví dụ:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/api/customers")
    @ResponseStatus(HttpStatus.CREATED)
    CustomerResponse create(@Valid @RequestBody CreateCustomerRequest request) {
        return new CustomerResponse("CUS-100", request.name(), request.email());
    }
}

record CustomerResponse(String id, String name, String email) {}
```

Để Jakarta Bean Validation hoạt động, ứng dụng cần có implementation/provider tương ứng trên classpath, thường thông qua dependency validation starter của Spring Boot. Annotation trên model nhưng thiếu provider hoặc không kích hoạt validation ở điểm vào không đủ bảo đảm request bị kiểm tra.

Với nested object, kích hoạt cascade validation bằng @Valid ở field lồng:

```java
public record AddressRequest(
        @NotBlank String city,
        @NotBlank String countryCode
) {}

public record CreateCustomerRequest(
        @NotBlank @Size(max = 100) String name,
        @NotBlank @Email String email,
        @Valid AddressRequest address
) {}
```

Nếu address bắt buộc, thêm constraint phù hợp như @NotNull bên cạnh @Valid. @Valid yêu cầu cascade validation khi object có mặt; nó không tự làm object trở thành required.

## 5. Document constraint trong Spring REST Docs

Spring REST Docs không có descriptor tự động biến mọi Bean Validation annotation thành contract hoàn chỉnh. Cách rõ ràng là dùng descriptor field và mô tả giới hạn đã xác định:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("name")
        .description("Tên khách hàng; bắt buộc, không chỉ gồm khoảng trắng, tối đa 100 ký tự"),
    fieldWithPath("email")
        .description("Email; bắt buộc, đúng định dạng email, tối đa 254 ký tự"),
    fieldWithPath("age")
        .description("Tuổi; nếu được gửi phải nằm trong khoảng 18 đến 120")
        .optional()
)
```

Descriptor age được đánh dấu optional trong ví dụ vì request model cho phép null/vắng mặt. Nếu contract bắt buộc tuổi, thay đổi model bằng constraint phù hợp và bỏ optional() sau khi test xác nhận.

### 5.1. Dùng attributes khi muốn cấu trúc metadata rõ ràng

Có thể đính kèm attributes vào field descriptor và dùng custom snippet template để hiển thị constraint theo định dạng riêng:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("name")
    .description("Tên khách hàng")
    .attributes(
        key("constraints").value("Bắt buộc; không chỉ gồm khoảng trắng; tối đa 100 ký tự"),
        key("example").value("Nguyen An")
    )
```

Attributes là metadata dành cho snippet template. Chúng không kích hoạt validator và không tự xác minh annotation trên DTO. Nếu template mặc định không hiển thị attribute tùy chỉnh, cần điều chỉnh template hoặc ghi constraint trong description(...).

### 5.2. Tránh mô tả constraint bằng một con số lặp lại không có nguồn

Nếu @Size(max = 100) đổi thành @Size(max = 80), con số trong description hoặc attribute có thể cũ. Giảm rủi ro bằng cách:

1. Giữ constraint trong request model làm nguồn thực thi.
2. Đặt test ở các biên như 100 và 101 ký tự.
3. Khi review thay đổi validator, đồng thời xem xét descriptor.
4. Trong CI, chạy test document strict để phát hiện field mới/thiếu và chạy test biên để chứng minh behavior.

Test không thể tự chứng minh description văn bản là đúng nếu description không được so sánh với nguồn constraint. Có thể bổ sung convention, custom annotation/documentation metadata hoặc test chuyên biệt nếu dự án cần tự động hóa phần này.

## 6. Kiểm thử request hợp lệ và document bằng MockMvc

Ví dụ test thành công:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CustomerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new CustomerController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsCreateCustomer() throws Exception {
        mockMvc.perform(post("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Nguyen An",
                                  "email": "an@example.test",
                                  "age": 28
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("CUS-100"))
                .andExpect(jsonPath("$.email").value("an@example.test"))
                .andDo(document("customer-create",
                        requestFields(
                                fieldWithPath("name")
                                        .description("Tên khách hàng; bắt buộc; tối đa 100 ký tự"),
                                fieldWithPath("email")
                                        .description("Email; bắt buộc; đúng định dạng; tối đa 254 ký tự"),
                                fieldWithPath("age")
                                        .description("Tuổi; nếu được gửi phải từ 18 đến 120")
                                        .optional()
                        ),
                        responseFields(
                                fieldWithPath("id").description("Mã khách hàng được tạo"),
                                fieldWithPath("name").description("Tên khách hàng"),
                                fieldWithPath("email").description("Email khách hàng")
                        )));
    }
}
```

Test này thực hiện request qua controller và tạo snippet customer-create. Nếu request không qua validation, assertion isCreated() thất bại và snippet thành công không được sinh từ request lỗi.

Trong dự án tích hợp Spring Boot đầy đủ, dùng application context và filter/security thực tế nếu chúng ảnh hưởng đến binding, validation hoặc error handling. standaloneSetup(...) hữu ích cho ví dụ nhỏ, nhưng không thay thế kiểm thử cấu hình ứng dụng.

## 7. Kiểm thử constraint ở các giá trị biên

Chỉ test một request hợp lệ không đủ chứng minh constraint được thực thi. Nên chọn giá trị ngay dưới, đúng tại và ngay trên ranh giới:

| Field/constraint | Request value | Kết quả mong đợi |
| --- | --- | --- |
| name @NotBlank | "" hoặc "   " | Bị từ chối |
| name @Size(max=100) | 100 ký tự | Được chấp nhận nếu điều kiện khác hợp lệ |
| name @Size(max=100) | 101 ký tự | Bị từ chối |
| email @Email | an@example.test | Được chấp nhận nếu không vi phạm constraint khác |
| email @Email | not-an-email | Bị từ chối |
| age @Min(18) | 17 | Bị từ chối |
| age @Min(18) | 18 | Đạt biên dưới |
| age @Max(120) | 121 | Bị từ chối |

Ví dụ test âm tính:

```java
@Test
void rejectsInvalidCustomerEmail() throws Exception {
    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Nguyen An",
                              "email": "not-an-email",
                              "age": 28
                            }
                            """))
            .andExpect(status().isBadRequest());
}

@Test
void rejectsCustomerNameLongerThanMaximum() throws Exception {
    String longName = "A".repeat(101);
    String body = """
            {"name":"%s","email":"an@example.test","age":28}
            """.formatted(longName);

    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isBadRequest());
}
```

Các test trên chứng minh status theo error handling mặc định hoặc đã cấu hình của ứng dụng. Nếu application dùng @ControllerAdvice để chuyển MethodArgumentNotValidException thành error format riêng, hãy xác nhận chính format đó thay vì giả định response mặc định.

## 8. Document error response do validation

Một API tốt cần cho client biết cấu trúc lỗi khi gửi payload không hợp lệ. Ví dụ error contract:

```json
{
  "type": "VALIDATION_ERROR",
  "message": "Request contains invalid fields",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

Mô hình response:

```java
record FieldViolation(String field, String code, String message) {}
record ApiValidationError(
        String type,
        String message,
        List<FieldViolation> violations) {}
```

Một @RestControllerAdvice có thể ánh xạ lỗi validation thành schema ổn định. Phần xử lý cụ thể phụ thuộc Spring version, exception type và chính sách ứng dụng; điều quan trọng là test HTTP xác nhận response thực tế.

Ví dụ descriptor cho response lỗi:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("type").description("Mã nhóm lỗi"),
    fieldWithPath("message").description("Thông báo tổng quát"),
    fieldWithPath("violations").description("Danh sách lỗi validation"),
    fieldWithPath("violations[].field").description("Tên field không hợp lệ"),
    fieldWithPath("violations[].code").description("Mã constraint hoặc mã lỗi"),
    fieldWithPath("violations[].message").description("Thông báo cho field")
)
```

Test nên gửi request không hợp lệ và document response:

```java
@Test
void documentsValidationErrorForInvalidEmail() throws Exception {
    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Nguyen An",
                              "email": "not-an-email",
                              "age": 28
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.type").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.violations[0].field").value("email"))
            .andDo(document("customer-create-invalid-email",
                    responseFields(
                            fieldWithPath("type").description("Mã nhóm lỗi"),
                            fieldWithPath("message").description("Thông báo tổng quát"),
                            fieldWithPath("violations").description("Danh sách lỗi validation"),
                            fieldWithPath("violations[].field").description("Tên field không hợp lệ"),
                            fieldWithPath("violations[].code").description("Mã constraint"),
                            fieldWithPath("violations[].message").description("Thông báo lỗi")
                    )));
}
```

Đây là ví dụ minh họa; nó giả định ứng dụng trả đúng JSON error contract được mô tả. Hãy điều chỉnh assertion và descriptor theo response thực tế, không thêm snippet từ một body tưởng tượng.

## 9. Nested validation và danh sách lỗi

Với request có object lồng nhau:

```java
public record AddressRequest(
        @NotBlank String city,
        @Pattern(regexp = "^[A-Z]{2}$") String countryCode
) {}

public record CreateCustomerRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Valid @NotNull AddressRequest address
) {}
```

@Valid trên address yêu cầu cascade validation; @NotNull khiến address bắt buộc. Nếu thiếu @Valid, constraint trong AddressRequest có thể không được cascade theo cách mong muốn.

Tài liệu request:

```java
requestFields(
    fieldWithPath("name").description("Tên khách hàng; bắt buộc"),
    fieldWithPath("email").description("Email hợp lệ; bắt buộc"),
    fieldWithPath("address.city").description("Thành phố; bắt buộc"),
    fieldWithPath("address.countryCode")
        .description("Mã quốc gia gồm đúng hai chữ cái viết hoa")
)
```

Tài liệu cần thể hiện cấu trúc nested field và constraint ở từng field. Test nên có một trường hợp invalid ở nested path, ví dụ address.countryCode = "VNM", rồi xác nhận violation chỉ ra đúng đường dẫn.

Nếu object lồng nhau là optional, có thể dùng @Valid mà không có @NotNull; khi object có mặt, các constraint con được kiểm tra. Descriptor tương ứng nên dùng optional() cho subsection/field nếu nó được phép vắng.

## 10. Cross-field và business constraints

Một số quy tắc không thuộc riêng một field:

- startDate phải trước endDate.
- currency phải phù hợp với country.
- Ít nhất một trong email hoặc phone phải có.
- discount không được lớn hơn total.

Có thể triển khai bằng class-level constraint/custom validator hoặc kiểm tra ở service/domain. Ví dụ:

```java
@ValidDateRange
public record BookingRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {}
```

Constraint custom @ValidDateRange cần validator kiểm tra cả hai giá trị và gắn violation vào field hoặc object path thích hợp. Spring REST Docs không tự phát hiện logic này từ tên annotation.

Trong tài liệu, mô tả rule như một điều kiện giữa các field:

```java
requestFields(
    fieldWithPath("startDate").description("Ngày bắt đầu; định dạng ISO-8601"),
    fieldWithPath("endDate").description("Ngày kết thúc; phải sau startDate")
)
```

Test tối thiểu cần bao gồm:

1. Khoảng ngày hợp lệ.
2. endDate bằng startDate.
3. endDate trước startDate.
4. Một hoặc cả hai field bị thiếu/null nếu contract có quy định.

Đối với business constraints, mô tả cần nói rõ điều kiện và response lỗi. Đừng cố diễn tả toàn bộ rule thành một annotation đơn lẻ trong bảng field nếu quan hệ nằm giữa nhiều field.

## 11. Enum, pattern và giới hạn phức tạp

Một field có thể bị ràng buộc bởi tập giá trị hữu hạn:

```java
public enum CustomerType {
    INDIVIDUAL, BUSINESS
}

public record CustomerCategoryRequest(
        @NotNull CustomerType type,
        @Pattern(regexp = "^[A-Z0-9-]{3,20}$")
        String externalCode
) {}
```

Document:

```java
requestFields(
    fieldWithPath("type")
        .description("Loại khách hàng: INDIVIDUAL hoặc BUSINESS"),
    fieldWithPath("externalCode")
        .description("Mã đối tác gồm 3–20 ký tự in hoa, chữ số hoặc dấu gạch nối")
        .optional()
)
```

Với regex dài hoặc phức tạp, đừng chỉ chép nguyên biểu thức Java vào tài liệu rồi để client tự giải mã. Hãy mô tả rule bằng ngôn ngữ rõ ràng và cung cấp ví dụ hợp lệ/không hợp lệ nếu cần. Nếu regex là nguồn contract quan trọng, cân nhắc công bố schema OpenAPI/JSON Schema hoặc mô tả máy đọc được dùng chung.

## 12. Tránh contract drift giữa annotation và tài liệu

Các nguyên nhân thường làm tài liệu lệch khỏi runtime:

| Thay đổi runtime | Rủi ro tài liệu |
| --- | --- |
| @Size(max=100) đổi thành @Size(max=80) | Description vẫn nói tối đa 100 ký tự |
| Thêm @NotNull | Tài liệu vẫn đánh dấu field optional |
| Bỏ @Valid ở nested object | Tài liệu vẫn tuyên bố constraint con được kiểm tra |
| Thêm enum value | Bảng giá trị hợp lệ không cập nhật |
| Thay error schema trong @ControllerAdvice | responseFields hoặc ví dụ lỗi lỗi thời |
| Thay validator cross-field | Mô tả quan hệ ngày/giá trị không còn đúng |

Khi sửa request DTO, validation annotation, custom validator hoặc error handler, review đồng thời:

- Test hợp lệ và test invalid ở các biên.
- Field descriptor và description/attributes.
- Error response descriptors cùng HTTP status.
- Snippet Asciidoctor/Markdown và ví dụ client.

## 13. Strict documentation và CI

Strict requestFields(...) giúp phát hiện field trong payload test chưa được mô tả hoặc descriptor bắt buộc vắng mặt. Nó hữu ích khi schema thay đổi, nhưng không thay thế test validation:

- Strict REST Docs kiểm tra cấu trúc field đã document.
- Bean Validation kiểm tra giá trị theo constraint runtime.
- HTTP test kiểm tra mapping từ violation sang status/error payload.
- Review tài liệu kiểm tra ý nghĩa văn bản, ví dụ giới hạn và quy tắc nghiệp vụ.

Quy trình build thường gồm:

1. Compile ứng dụng và test.
2. Chạy test validation hợp lệ/không hợp lệ.
3. Sinh snippet Spring REST Docs.
4. Chạy Asciidoctor để include snippet và render tài liệu.
5. Lưu artifact tài liệu trong pipeline hoặc publish theo quy trình dự án.

Ví dụ Gradle khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Nếu dự án dùng Maven, chạy lifecycle goal đã được cấu hình cho test và Asciidoctor. Chi tiết task/dependency tùy cấu hình dự án; bảo đảm Asciidoctor phụ thuộc output snippet từ test và thất bại khi snippet bắt buộc bị thiếu.

### 13.1. Gợi ý tách test

| Nhóm test | Mục tiêu | Có cần sinh snippet? |
| --- | --- | --- |
| Valid request documentation test | Tạo snippet request/response thành công | Có |
| Validation boundary tests | Chứng minh min/max, size, pattern | Không nhất thiết |
| Invalid request documentation test | Document error contract đại diện | Có, nếu error contract là nội dung public |
| Custom/cross-field validator tests | Chứng minh business rule | Không nhất thiết |

Không cần tạo thư mục snippet cho mọi giá trị invalid. Chọn trường hợp đại diện giúp trang tài liệu dễ đọc, trong khi bộ test có thể bao phủ nhiều biên hơn.

## 14. Checklist thực hành

Khi thêm hoặc thay đổi validation của một endpoint:

- [ ] Request DTO có constraint phù hợp với kiểu dữ liệu và contract.
- [ ] Controller thực sự kích hoạt validation bằng @Valid/cơ chế tương ứng.
- [ ] Nested object có cascade validation khi cần.
- [ ] Optional, null và empty được phân biệt rõ.
- [ ] Có test giá trị hợp lệ và test biên/không hợp lệ.
- [ ] requestFields(...) hoặc requestPartFields(...) mô tả đúng field và giới hạn.
- [ ] Error response có schema ổn định và được document nếu là public contract.
- [ ] Custom/cross-field rule có mô tả cùng test riêng.
- [ ] Test snippet và Asciidoctor chạy trong CI.

## 15. Bài tập thực hành

Xây dựng endpoint tạo booking:

```http
POST /api/bookings
Content-Type: application/json

{
  "customerEmail": "an@example.test",
  "startDate": "2026-12-01",
  "endDate": "2026-12-05",
  "guestCount": 2,
  "note": "Near the elevator"
}
```

Contract:

- customerEmail: bắt buộc, đúng định dạng email.
- startDate, endDate: bắt buộc, định dạng ngày ISO; endDate phải sau startDate.
- guestCount: từ 1 đến 8.
- note: tùy chọn, tối đa 300 ký tự.

Thực hiện:

1. Tạo request record với @NotBlank, @Email, @NotNull, @Min, @Max, @Size phù hợp.
2. Viết class-level validator cho quy tắc endDate sau startDate, hoặc triển khai rule tại tầng domain và giải thích lựa chọn.
3. Kích hoạt validation ở controller.
4. Viết MockMvc test cho request hợp lệ, email sai, guestCount ngoài biên, note quá dài và ngày kết thúc không hợp lệ.
5. Document request fields với mô tả chính xác về presence, format và range.
6. Chuẩn hóa error response, document một lỗi đại diện bằng responseFields(...).
7. Chạy test và Asciidoctor trong build/CI.

**Tiêu chí hoàn thành:** Validator thực thi đúng contract; test chứng minh giá trị biên và lỗi; descriptor không đánh dấu sai field optional; error response snippet khớp response runtime.

## 16. Ghi nhớ

Validation runtime và tài liệu Spring REST Docs là hai lớp bổ sung cho nhau. Jakarta Bean Validation cùng controller thực thi quy tắc; test HTTP chứng minh request nào được chấp nhận hoặc từ chối; descriptor và response snippet giải thích contract đó cho người tích hợp. fieldWithPath(...) không tự chạy validator, optional() không thay thế nullability rule và strict documentation không thay thế test giá trị biên. Đồng bộ cả ba lớp trong build/CI giúp tài liệu phản ánh đúng hành vi API theo thời gian.

### Tài liệu tham khảo

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring REST Docs — Request Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-fields.html)
- [Spring REST Docs — Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/response-fields.html)
