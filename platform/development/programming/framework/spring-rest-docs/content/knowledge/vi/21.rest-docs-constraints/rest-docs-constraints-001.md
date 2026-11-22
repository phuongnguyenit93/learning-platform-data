# Vì sao mô tả constraint làm tài liệu hữu ích hơn

## 1. Mục tiêu và bối cảnh

Một bảng request/response fields chỉ cho người đọc biết **field nào tồn tại và field đó có ý nghĩa gì**. Nhưng khi tích hợp API, developer còn cần biết dữ liệu nào được chấp nhận: chuỗi dài tối đa bao nhiêu, trường nào bắt buộc, số phải nằm trong khoảng nào, email có đúng định dạng không, ngày kết thúc có sau ngày bắt đầu không, hoặc một mã có duy nhất trong hệ thống không.

Những quy tắc đó là **constraints (ràng buộc dữ liệu/nghiệp vụ)**. Khi tài liệu mô tả rõ constraint, người dùng API có thể tạo request hợp lệ ngay từ đầu, hiểu lý do request bị từ chối và xử lý lỗi nhất quán. Điều này quan trọng với **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; rồi biên soạn Asciidoctor/Markdown trong build và CI.

Sau bài học, bạn có thể phân biệt field description với constraint, kết hợp Bean Validation và HTTP tests, đưa constraint vào descriptor/template, kiểm thử dữ liệu hợp lệ/không hợp lệ và tránh mô tả sai hoặc lỗi thời.

> Spring REST Docs ghi nhận HTTP operation được kiểm thử. Nó không tự tạo endpoint, fixture hay quy tắc nghiệp vụ. Descriptor giúp xác minh tài liệu khớp payload; chúng không thay thế mọi assertion.

## 2. Field description và constraint trả lời hai câu hỏi khác nhau

Xét endpoint tạo tài khoản:

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 28,
  "password": "ExamplePass123"
}
~~~

Bảng field cơ bản:

| Field | Description |
| --- | --- |
| `name` | Tên hiển thị của tài khoản. |
| `email` | Địa chỉ email. |
| `age` | Tuổi người dùng. |
| `password` | Mật khẩu đăng ký. |

Bảng này chưa cho biết `name` có được để trống không, `email` cần định dạng nào, `age` tối thiểu bao nhiêu hoặc mật khẩu cần thỏa điều kiện gì.

Có thể bổ sung constraint:

| Field | Description | Constraint minh họa |
| --- | --- | --- |
| `name` | Tên hiển thị | Không null/rỗng; dài 2–80 ký tự. |
| `email` | Địa chỉ email | Bắt buộc; định dạng email hợp lệ; tối đa 254 ký tự theo contract. |
| `age` | Tuổi người dùng | Số nguyên từ 18 đến 120. |
| `password` | Mật khẩu đăng ký | Bắt buộc; ít nhất 12 ký tự và thỏa chính sách sản phẩm. |

Đây là **ví dụ hợp đồng**, không phải mặc định của Spring REST Docs, Bean Validation hay mọi API. Quy tắc thật phải lấy từ code, domain và quyết định sản phẩm đã xác nhận.

Tài liệu tốt giúp người đọc trả lời: field có bắt buộc xuất hiện không; kiểu và miền giá trị được chấp nhận là gì; dữ liệu sai dẫn đến status/error response nào; quy tắc được kiểm tra ở tầng nào.

## 3. Constraint làm tài liệu hữu ích hơn như thế nào?

### 3.1. Giúp client gửi request hợp lệ

Nếu tài liệu chỉ ghi `age` là tuổi, client có thể gửi `-5`, `0` hoặc một số rất lớn. Nếu giới hạn được công bố, client có thể validate trước khi gửi. Tương tự, mô tả email cần nói rõ bắt buộc hay tùy chọn, giới hạn độ dài và định dạng.

### 3.2. Làm rõ absent, null và empty

Ba request sau không nhất thiết có cùng ý nghĩa:

~~~json
{"name":"Lan"}
~~~

~~~json
{"name":"Lan","nickname":null}
~~~

~~~json
{"name":"Lan","nickname":""}
~~~

- **Absent:** client không gửi `nickname`.
- **Explicit null:** client gửi field với giá trị JSON `null`.
- **Empty string:** client gửi chuỗi rỗng.

`@NotNull` không đồng nghĩa `@NotBlank`. `@NotBlank` yêu cầu chuỗi có ít nhất một ký tự không phải whitespace. Tài liệu cần diễn tả chính xác từng trạng thái thay vì gộp thành “bắt buộc”.

### 3.3. Giải thích vì sao request bị từ chối

Nếu contract nói `quantity` phải lớn hơn 0, người đọc hiểu vì sao `quantity = 0` bị từ chối. Khi tài liệu có error response mẫu, client còn biết field nào cần sửa hoặc mã lỗi nào cần xử lý.

### 3.4. Phát hiện thay đổi hợp đồng trong CI

Khi constraint đổi, cần cập nhật validation logic, test, descriptor và nội dung tài liệu. REST Docs phát hiện field payload thay đổi hoặc descriptor không còn khớp. Nó không tự phát hiện mọi thay đổi constraint nếu văn bản chỉ nằm trong mô tả thủ công; cần test và review riêng.

## 4. Constraint thường gặp và cách diễn giải

| Annotation | Ý nghĩa chung | Điều cần ghi rõ |
| --- | --- | --- |
| `@NotNull` | Giá trị không được null | Yêu cầu field hiện diện hay chỉ cấm giá trị null? |
| `@NotBlank` | Chuỗi không null và có ký tự không phải whitespace | Không để trống/chỉ có whitespace. |
| `@NotEmpty` | Chuỗi/collection/map/array không rỗng theo kiểu được hỗ trợ | Ít nhất một ký tự hoặc phần tử. |
| `@Size(min, max)` | Kích thước trong khoảng | Đơn vị và biên min/max. |
| `@Min` / `@Max` | Giá trị số nằm trong giới hạn | Giới hạn và tính bao gồm biên. |
| `@DecimalMin` / `@DecimalMax` | Giới hạn số thập phân | Biên bao gồm hay loại trừ. |
| `@Positive` / `@PositiveOrZero` | Số dương hoặc không âm | 0 có được chấp nhận không? |
| `@Email` | Chuỗi theo quy tắc email của provider | Không chứng minh mailbox tồn tại. |
| `@Pattern` | Giá trị khớp regular expression | Diễn giải bằng ngôn ngữ dễ hiểu. |
| `@Past` / `@Future` | Thời điểm trong quá khứ/tương lai theo validation clock | Mốc thời gian/múi giờ nếu có ý nghĩa. |
| `@Valid` | Kích hoạt validation object lồng nhau | Quy tắc lồng nhau và cách trả lỗi. |

Annotation không đồng nghĩa contract tự động. `@Email` không xác minh email thực sự tồn tại; `@Pattern` có thể chứa regex khó hiểu; `@Size` trên chuỗi và collection có đơn vị khác nhau. Giải thích bằng ngôn ngữ nghiệp vụ và xác nhận với provider đang dùng.

### 4.1. DTO có Bean Validation constraints

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegisterAccountRequest(
    @NotBlank
    @Size(min = 2, max = 80)
    String name,

    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotNull
    @Min(18)
    @Max(120)
    Integer age,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record AddressRequest(
    @NotBlank @Size(max = 120) String city,
    @NotBlank @Size(max = 20) String postalCode
) {}
~~~

Ví dụ dùng Jakarta Bean Validation (`jakarta.validation`) và giả định ứng dụng có provider phù hợp. Với object lồng nhau, `@Valid` kích hoạt kiểm tra constraints của `AddressRequest` khi validation được gọi. Hành vi còn phụ thuộc validation groups, provider và cấu hình.

Controller cần bật validation:

~~~java
@PostMapping("/api/accounts")
public ResponseEntity<AccountResponse> register(
        @Valid @RequestBody RegisterAccountRequest request) {
    AccountResponse created = accountService.register(request);
    return ResponseEntity
        .created(URI.create("/api/accounts/" + created.id()))
        .body(created);
}
~~~

`@Valid` kích hoạt validation cho request object trong cấu hình Spring MVC phù hợp. Hãy test status/error mapping thực tế; không suy luận mọi ứng dụng đều trả cùng một JSON lỗi.

## 5. Spring REST Docs không tự hiển thị mọi validation annotation

`requestFields(...)` và `responseFields(...)` mô tả field path và description mà người viết khai báo. **Bảng snippet mặc định không tự đọc toàn bộ Bean Validation annotations rồi thêm cột constraint.**

~~~java
requestFields(
    fieldWithPath("email").description("Địa chỉ email của tài khoản")
)
~~~

Ví dụ này mô tả field. Nó không tự thêm `@NotBlank`, `@Email` hay `@Size(max = 254)` vào bảng.

Có ba lựa chọn:

1. Viết constraint trực tiếp trong description: đơn giản, cần giữ đồng bộ bằng review.
2. Đọc metadata Bean Validation bằng API của Spring REST Docs và đưa vào descriptor attributes.
3. Tạo custom snippet template để hiển thị cột constraint riêng.

Với vài field, description đầy đủ thường đủ. Với DTO lớn, metadata và template có thể giảm lặp lại; vẫn cần review constraints nghiệp vụ không biểu diễn bằng annotation.

## 6. Trích xuất constraint bằng ConstraintDescriptions

Spring REST Docs cung cấp `ConstraintDescriptions` trong module core để lấy mô tả constraints trên một kiểu Java. Ví dụ:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

public class AccountConstraintDescriptions {
    private final ConstraintDescriptions descriptions =
        new ConstraintDescriptions(RegisterAccountRequest.class);

    public List<String> forEmail() {
        return descriptions.descriptionsForProperty("email");
    }

    public List<String> forAge() {
        return descriptions.descriptionsForProperty("age");
    }
}
~~~

Descriptions có thể lấy từ message interpolation/resource bundle. Tùy version Spring REST Docs và validation provider, kết quả có thể khác; cấu hình message thân thiện, rõ ràng, không phụ thuộc thông báo mặc định khó hiểu.

Ví dụ resource bundle:

~~~properties
jakarta.validation.constraints.NotBlank.message=Không được để trống.
jakarta.validation.constraints.Email.message=Phải có định dạng email hợp lệ.
jakarta.validation.constraints.Size.message=Độ dài phải nằm trong khoảng cho phép.
jakarta.validation.constraints.Min.message=Giá trị không được nhỏ hơn giới hạn tối thiểu.
jakarta.validation.constraints.Max.message=Giá trị không được lớn hơn giới hạn tối đa.
~~~

Các message trên là ví dụ chung; constraint có tham số cần message template thể hiện giá trị min/max động. Không copy message mặc định nếu chúng làm lộ class name hoặc thuật ngữ nội bộ.

### 6.1. Đưa constraint vào descriptor attributes

REST Docs cho phép gắn metadata vào field descriptor qua `attributes(...)`:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

ConstraintDescriptions emailConstraints =
    new ConstraintDescriptions(RegisterAccountRequest.class);

FieldDescriptor emailField = fieldWithPath("email")
    .description("Địa chỉ email của tài khoản")
    .attributes(key("constraints").value(
        String.join("; ", emailConstraints.descriptionsForProperty("email"))
    ));
~~~

Đây là metadata do dự án đặt tên, không tự xuất hiện trong template fields mặc định. Nếu template không đọc `constraints`, nội dung sẽ không hiện trong bảng.

Helper có thể giảm lặp:

~~~java
public class ConstrainedFields {
    private final ConstraintDescriptions descriptions;

    public ConstrainedFields(Class<?> inputType) {
        this.descriptions = new ConstraintDescriptions(inputType);
    }

    public FieldDescriptor withPath(String path, String description) {
        List<String> constraints = descriptions.descriptionsForProperty(path);
        return fieldWithPath(path)
            .description(description)
            .attributes(key("constraints").value(String.join("; ", constraints)));
    }
}
~~~

Cách này giả định JSON path tương ứng Java property. Với field lồng nhau, collection, JSON name khác Java property hoặc DTO mapping riêng, cần ánh xạ đúng property path; không mặc định mọi JSON path đều dùng trực tiếp được với Bean Validation metadata.

## 7. Hiển thị constraint trong custom snippet template

Mục tiêu bảng Asciidoc có thể là:

~~~asciidoc
|===
|Field |Description |Constraints

|email
|Địa chỉ email của tài khoản
|Không được để trống; phải đúng định dạng email; tối đa 254 ký tự
|===
~~~

Để render cột constraint, tùy chỉnh template fields của phiên bản REST Docs đang dùng sao cho template đọc attribute `constraints` từ descriptor. Hãy sao chép template phù hợp từ artifact/version của dự án, thêm cột rồi kiểm tra output thực tế. Không thay template mà chưa xác minh cú pháp template engine.

Cách đơn giản hơn là viết constraint trong description:

~~~java
fieldWithPath("email")
    .description("Địa chỉ email. Bắt buộc; phải đúng định dạng; tối đa 254 ký tự.")
~~~

Cách này không cần custom template, nhưng văn bản thủ công phải được cập nhật khi annotation/domain rule thay đổi.

**Không tuyên bố constraint tự động hiển thị** chỉ vì đã tạo `ConstraintDescriptions`. Phải gắn metadata vào descriptor và có template render, hoặc viết trực tiếp trong description.

## 8. Kiểm chứng constraints bằng HTTP tests

### 8.1. Test dữ liệu hợp lệ

~~~java
@Test
void registerAccountWithValidData() throws Exception {
    mockMvc.perform(post("/api/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Lan Nguyen",
                  "email": "lan@example.com",
                  "age": 28,
                  "address": {
                    "city": "Ho Chi Minh City",
                    "postalCode": "700000"
                  }
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("accounts-register-valid",
            requestFields(
                fieldWithPath("name")
                    .description("Tên hiển thị; 2–80 ký tự, không để trống"),
                fieldWithPath("email")
                    .description("Email hợp lệ, tối đa 254 ký tự"),
                fieldWithPath("age")
                    .description("Tuổi từ 18 đến 120"),
                fieldWithPath("address").description("Địa chỉ"),
                fieldWithPath("address.city")
                    .description("Thành phố, tối đa 120 ký tự"),
                fieldWithPath("address.postalCode")
                    .description("Mã bưu chính, tối đa 20 ký tự")
            )
        ));
}
~~~

Ví dụ giả định endpoint và fixture trả `201 Created`. Constraint được ghi trong description để hoạt động với template mặc định. Nếu dự án dùng metadata/custom template, thay bằng helper và xác minh cột constraint được render.

### 8.2. Test dữ liệu không hợp lệ

~~~java
@Test
void rejectInvalidAccountData() throws Exception {
    mockMvc.perform(post("/api/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "L",
                  "email": "not-an-email",
                  "age": 15,
                  "address": {
                    "city": "",
                    "postalCode": "700000"
                  }
                }
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("accounts-register-invalid"));
}
~~~

Test chỉ giả định ứng dụng ánh xạ Bean Validation failure thành `400 Bad Request`. Payload vi phạm nhiều constraints. Để tài liệu hóa từng lỗi cụ thể, nên tách test theo tình huống để xác định rõ nguyên nhân response.

Error response minh họa:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Phải có định dạng email hợp lệ."
    },
    {
      "field": "age",
      "code": "Min",
      "message": "Tuổi phải từ 18 trở lên."
    }
  ]
}
~~~

Body này là **ví dụ contract**, không phải định dạng mặc định của REST Docs/Spring Boot. Ứng dụng có thể dùng Problem Details (RFC 9457) hoặc schema riêng. Test status, media type, field và message theo error handler thực tế.

### 8.3. Test các giá trị ở biên

| Constraint | Hợp lệ minh họa | Cần kiểm tra thất bại |
| --- | --- | --- |
| `@NotBlank` | `"Lan"` | `""`, `"   "`, null |
| `@Size(min=2, max=80)` | Dài 2 và 80 | Dài 1 và 81 |
| `@Min(18)` | 18 | 17 |
| `@Max(120)` | 120 | 121 |
| `@Email` | `lan@example.com` | `not-an-email` |
| `@NotNull` | Có giá trị | null/field thiếu theo kiểu binding |

Không nhất thiết test mọi tổ hợp nếu đã có phân vùng tương đương hợp lý, nhưng cần bao phủ biên quan trọng. Field kiểu primitive như `int` không biểu diễn null giống `Integer`; điều này ảnh hưởng cách phân biệt field thiếu và giá trị mặc định sau binding.

## 9. Constraint của response cũng quan trọng

Constraint không chỉ áp dụng cho input. Response có thể có guarantees về kiểu, định dạng, phạm vi hoặc quan hệ giữa field:

| Field | Mô tả | Constraint/guarantee |
| --- | --- | --- |
| `id` | Mã tài khoản | Số nguyên dương, ổn định. |
| `status` | Trạng thái tài khoản | Một trong `PENDING`, `ACTIVE`, `LOCKED`. |
| `createdAt` | Thời điểm tạo | ISO-8601/RFC 3339, UTC theo contract. |
| `roles` | Danh sách role | Chỉ chứa role công khai được API cho phép. |

Các guarantees này cần được bảo vệ bằng response tests. `responseFields(...)` kiểm tra field được mô tả theo payload; nó không tự xác minh total bằng tổng dòng hàng hoặc enum chỉ gồm giá trị hợp lệ. Dùng assertion domain phù hợp và ghi rõ quy tắc trong tài liệu.

## 10. Constraint không phải lúc nào cũng là Bean Validation

Một số quy tắc không thể biểu diễn đầy đủ bằng annotation trên property:

- Email phải chưa được đăng ký (uniqueness cần truy vấn dữ liệu).
- Mã đơn hàng phải thuộc khách hàng đang đăng nhập.
- Ngày giao hàng phải phù hợp lịch vận chuyển.
- Tổng tiền không vượt hạn mức tín dụng.
- Một trạng thái chỉ được chuyển sang trạng thái kế tiếp trong workflow.

Đây là **domain/business constraints**. Chúng có thể được thực thi ở service/domain layer và kiểm thử qua HTTP. Tài liệu cần mô tả điều kiện và error response; `ConstraintDescriptions` không tự trích xuất được chúng.

Ví dụ `@Email` kiểm tra hình thức chuỗi theo provider, không chứng minh email tồn tại; uniqueness cần test riêng cho email chưa dùng và email đã đăng ký. Tài liệu hóa status và error code theo cam kết của API.

## 11. Đưa constraint vào tài liệu cuối

Asciidoctor có thể include raw payload và bảng field:

~~~asciidoc
= Accounts API

== Đăng ký tài khoản

Tên phải có 2–80 ký tự; email phải đúng định dạng và không vượt quá giới hạn; tuổi từ 18 đến 120.

=== HTTP request
include::{snippets}/accounts-register-valid/http-request.adoc[]

=== Request fields and constraints
include::{snippets}/accounts-register-valid/request-fields.adoc[]

=== Validation error
include::{snippets}/accounts-register-invalid/http-response.adoc[]

=== Error fields
include::{snippets}/accounts-register-invalid/response-fields.adoc[]
~~~

`request-fields.adoc` chỉ hiển thị constraint nếu description đã chứa constraint hoặc custom template render metadata. Bảng mặc định không tự phản ánh toàn bộ Bean Validation annotations.

Với Markdown, chỉ thị Asciidoctor `include::{snippets}/...[]` không được mọi Markdown renderer hiểu trực tiếp; cần template hoặc bước chuyển đổi/nhúng phù hợp.

## 12. CI và kiểm soát thay đổi constraint

Khi constraint thay đổi, xem xét đồng thời:

1. DTO/Bean Validation annotation hoặc domain rule.
2. Error handler và response contract.
3. HTTP tests cho dữ liệu hợp lệ, không hợp lệ và giá trị biên.
4. Field descriptors và mô tả constraint.
5. Raw snippets và tài liệu cuối.

~~~mermaid
flowchart TD
    A["Thay đổi constraint"] --> B["Cập nhật validation/domain logic"]
    B --> C["Chạy HTTP tests: valid + invalid + boundary"]
    C --> D{"Assertions pass?"}
    D -->|Không| E["Fail CI"]
    D -->|Có| F["Spring REST Docs sinh snippets"]
    F --> G["Render Asciidoctor/Markdown"]
    G --> H{"Constraint và error docs đầy đủ?"}
    H -->|Không| E
    H -->|Có| I["Review và publish"]
~~~

Nếu giới hạn age đổi từ 18–120 sang 21–100 mà chỉ sửa annotation, mô tả thủ công có thể vẫn ghi 18–120. CI chỉ bắt sai lệch nếu tests/descriptors/template kiểm tra được; văn bản mô tả thủ công cần review. Task tài liệu phải phụ thuộc test sinh snippet và chỉ publish khi test lẫn render đều đạt.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tài liệu chỉ ghi ý nghĩa field, không ghi giới hạn | Description thiếu constraint | Bổ sung miền giá trị, đơn vị và biên. |
| Annotation đổi nhưng bảng không đổi | Template mặc định không tự render annotations | Dùng ConstraintDescriptions, custom attributes/template hoặc cập nhật description. |
| Message lộ thuật ngữ Java | Message mặc định/provider không phù hợp | Cấu hình message thân thiện. |
| `@NotNull` bị hiểu như field luôn phải xuất hiện | Nhầm validation value với JSON presence/binding | Mô tả absent/null riêng và test từng trường hợp. |
| Optional field sai mô tả | Nhầm optional với null/empty | Kiểm tra contract và phân biệt absent/null/empty. |
| Validation status khác kỳ vọng | Exception handler/configuration thay đổi mapping | Xác nhận HTTP response thực tế. |
| `@Email` bị mô tả là email tồn tại | Nhầm format với mailbox verification | Chỉ mô tả kiểm tra định dạng; kiểm tra uniqueness riêng. |
| Relaxed descriptors che field mới | Dùng relaxed chỉ để test xanh | Review schema change, cập nhật descriptor. |
| ConstraintDescriptions trả danh sách rỗng | Thiếu provider, sai class/property path hoặc metadata không được nhận diện | Kiểm tra dependency/provider, path và resolver. |
| Custom attribute không hiện | Template không render attribute | Sửa template và kiểm tra output. |
| Tài liệu không theo kịp logic | Không có test/review gắn với thay đổi validation | Thêm boundary tests và CI gate. |

## 14. Bài thực hành

Thiết kế endpoint `POST /api/members`:

~~~json
{
  "fullName": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 28,
  "phone": "0901234567"
}
~~~

Contract giả định:

- `fullName`: bắt buộc, 2–80 ký tự, không chỉ whitespace.
- `email`: bắt buộc, đúng định dạng, tối đa 254 ký tự.
- `age`: số nguyên từ 18 đến 120.
- `phone`: bắt buộc, theo định dạng điện thoại sản phẩm công bố.

Thực hiện:

1. Tạo DTO với Bean Validation constraints và custom validator nếu hợp đồng yêu cầu.
2. Viết HTTP tests cho request hợp lệ và các trường hợp sai: tên trống, email sai, tuổi 17, phone sai định dạng.
3. Assert status/error payload theo exception handler thật.
4. Dùng `requestFields(...)`; ghi constraint trong description hoặc dùng `ConstraintDescriptions` + custom attributes/template.
5. Sinh snippet cho request hợp lệ và error response; mở raw snippet và include vào Asciidoctor.
6. Đổi giới hạn tuổi/độ dài tên; xác nhận boundary test và tài liệu cập nhật đồng bộ.
7. Chạy pipeline và bảo đảm không publish nếu assertions, descriptor hoặc render thất bại.

**Tiêu chí hoàn thành:** người đọc hiểu field có nghĩa gì và giá trị nào hợp lệ; constraint phản ánh logic được test; error response dùng được cho client; thay đổi validation tạo diff và kiểm tra rõ ràng trong CI.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
