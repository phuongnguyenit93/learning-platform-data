# ValidationConstraints tìm constraint từ Bean Validation

## 1. Mục tiêu và bối cảnh

Bảng request/response fields cho biết field nào tồn tại và ý nghĩa của field, nhưng người dùng API còn cần biết giá trị nào được chấp nhận: chuỗi dài tối đa bao nhiêu, số nằm trong khoảng nào, email có đúng định dạng không hoặc hai ngày có thỏa điều kiện quan hệ không. Đó là **constraints (ràng buộc)**.

Spring REST Docs cung cấp API để tìm constraint từ Bean Validation và lấy mô tả tương ứng. Chức năng này hỗ trợ mục tiêu của **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet request, response, payload, tham số và header; rồi biên soạn tài liệu Asciidoctor/Markdown trong build và CI.

Sau bài học, bạn có thể dùng `ConstraintDescriptions`, hiểu hai loại resolver, tùy chỉnh mô tả qua resource bundle, gắn constraints vào field descriptors, và nhận diện giới hạn với nested, class-level và domain constraints.

> Tên đề mục dùng “ValidationConstraints”, nhưng API công khai trọng tâm của Spring REST Docs là **`ConstraintDescriptions`** cùng các resolver trong package `org.springframework.restdocs.constraints`. Không giả định có một class tên `ValidationConstraints` ở mọi version.

## 2. Từ Bean Validation tới API documentation

Ví dụ DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterMemberRequest {
    @NotBlank
    @Size(min = 2, max = 80)
    private String fullName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;
}
~~~

| Property | Annotation | Ý nghĩa cần truyền đạt |
| --- | --- | --- |
| `fullName` | `@NotBlank` | Không null, rỗng hoặc chỉ whitespace. |
| `fullName` | `@Size(min=2,max=80)` | Độ dài từ 2 đến 80. |
| `email` | `@NotBlank` | Không được để trống. |
| `email` | `@Email` | Định dạng email theo provider. |
| `email` | `@Size(max=254)` | Tối đa 254 ký tự theo contract ví dụ. |

Annotation có hiệu lực khi Bean Validation được kích hoạt, ví dụ controller nhận DTO với `@Valid`. Chúng **không tự động thêm cột constraints** vào snippet mặc định của Spring REST Docs.

~~~mermaid
flowchart LR
    A["DTO + Bean Validation annotations"] --> B["Bean Validation Validator"]
    B --> C["ConstraintDescriptions"]
    C --> D["Descriptions theo property"]
    D --> E["FieldDescriptor"]
    E --> F["REST Docs template"]
    F --> G["request-fields.adoc"]
~~~

Validator/resolver tìm metadata. Description resolver chuyển metadata thành câu chữ. Người viết đưa câu chữ vào descriptors/template. Chỉ lấy được descriptions chưa có nghĩa snippet tự sinh; cần gắn chúng vào `requestFields(...)` hoặc `responseFields(...)`.

## 3. Dùng ConstraintDescriptions

`ConstraintDescriptions` lấy danh sách mô tả constraints cho một property:

~~~java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

class RegisterMemberConstraints {
    List<String> describeFullName() {
        ConstraintDescriptions descriptions =
            new ConstraintDescriptions(RegisterMemberRequest.class);
        return descriptions.descriptionsForProperty("fullName");
    }

    List<String> describeEmail() {
        ConstraintDescriptions descriptions =
            new ConstraintDescriptions(RegisterMemberRequest.class);
        return descriptions.descriptionsForProperty("email");
    }
}
~~~

`descriptionsForProperty("fullName")` trả danh sách mô tả constraints mà resolver tìm thấy trên property. Kết quả có thể tương đương “Must not be blank” và “Must be between 2 and 80 characters”; câu chữ thực tế phụ thuộc resource bundle, locale và version.

### 3.1. Cơ chế mặc định

Theo tài liệu Spring REST Docs, constructor mặc định dùng:

- `ValidatorConstraintResolver` để tìm constraint qua Bean Validation `Validator`.
- `ResourceBundleConstraintDescriptionResolver` để lấy câu mô tả từ resource bundle.

Dự án cần Bean Validation provider phù hợp. Spring Boot thường cung cấp integration thông qua dependency validation; dự án không dùng Boot phải cấu hình provider/Validator tương ứng.

### 3.2. Phạm vi tìm kiếm mặc định

Tài liệu Spring REST Docs hiện nêu cơ chế mặc định chỉ hỗ trợ **property constraints**. Vì vậy:

- Constraint trực tiếp trên property như `@NotBlank`, `@Size` là trường hợp chính.
- Không mặc định class-level constraint sẽ được trả về bởi `descriptionsForProperty(...)`.
- Rule ở service, repository hoặc rule engine không tự được trích xuất.
- Với object lồng nhau, collection và JSON field name tùy chỉnh, cần xác minh property path và mapping sang field path.

Cross-field/domain rules cần được mô tả riêng và kiểm thử riêng. Không gán cho `ConstraintDescriptions` khả năng mà resolver không cung cấp.

## 4. Gắn descriptions vào request fields

Có thể nối descriptions vào field description:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

ConstraintDescriptions constraints =
    new ConstraintDescriptions(RegisterMemberRequest.class);

requestFields(
    fieldWithPath("fullName").description(
        "Tên đầy đủ. " + String.join("; ",
            constraints.descriptionsForProperty("fullName"))
    ),
    fieldWithPath("email").description(
        "Email liên hệ. " + String.join("; ",
            constraints.descriptionsForProperty("email"))
    )
)
~~~

Cách này hoạt động với template mặc định vì constraint được đưa vào description. Nếu descriptions mặc định là tiếng Anh, cấu hình bundle/resolver bằng ngôn ngữ của tài liệu thay vì để lẫn ngôn ngữ.

### 4.1. Helper tái sử dụng

~~~java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.payload.FieldDescriptor;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public class ConstrainedFields {
    private final ConstraintDescriptions descriptions;

    public ConstrainedFields(Class<?> inputType) {
        this.descriptions = new ConstraintDescriptions(inputType);
    }

    public FieldDescriptor withPath(String property, String description) {
        List<String> constraints =
            this.descriptions.descriptionsForProperty(property);
        String details = String.join("; ", constraints);
        String fullDescription = details.isBlank()
            ? description : description + " " + details;
        return fieldWithPath(property).description(fullDescription);
    }
}
~~~

`String.isBlank()` yêu cầu Java 11 trở lên. Ví dụ giả định tên JSON field trùng Java property. Nếu JSON dùng `full_name` còn DTO dùng `fullName`, helper cần nhận riêng JSON field path và Bean Validation property name.

## 5. Descriptor attributes và custom template

Thay vì ghép constraint vào description, có thể lưu metadata riêng:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class);

FieldDescriptor email = fieldWithPath("email")
    .description("Email liên hệ")
    .attributes(key("constraints").value(
        String.join("; ", descriptions.descriptionsForProperty("email"))
    ));
~~~

Key `constraints` do dự án đặt tên. Template fields mặc định không tự render key này nếu không đọc nó.

Bảng mục tiêu có thể gồm cột riêng:

~~~asciidoc
|===
|Field |Description |Constraints

|email
|Email liên hệ
|Không được để trống; định dạng email hợp lệ; tối đa 254 ký tự
|===
~~~

Để hiển thị, sao chép template fields đúng version của dự án, bổ sung cột đọc descriptor attribute rồi chạy test xác minh. Cú pháp interpolation phụ thuộc template thực tế; không mặc định một placeholder tự hoạt động trong mọi version.

## 6. Tùy chỉnh mô tả qua resource bundle

Spring REST Docs mặc định dùng resource bundle base name:

~~~text
org.springframework.restdocs.constraints.ConstraintDescriptions
~~~

Mỗi key gồm fully qualified name của annotation và hậu tố `.description`. Ví dụ:

~~~properties
jakarta.validation.constraints.NotBlank.description=Không được null, rỗng hoặc chỉ chứa khoảng trắng
jakarta.validation.constraints.Size.description=Độ dài phải nằm trong giới hạn min và max được khai báo
jakarta.validation.constraints.Email.description=Phải có định dạng email hợp lệ
jakarta.validation.constraints.Min.description=Giá trị không được nhỏ hơn ngưỡng tối thiểu
jakarta.validation.constraints.Max.description=Giá trị không được lớn hơn ngưỡng tối đa
~~~

Đặt file theo quy tắc Java ResourceBundle và locale dự án. Với Jakarta Bean Validation dùng package `jakarta.validation.constraints`; dự án cũ dùng `javax.validation` cần key đúng package thực tế.

### 6.1. Attributes của constraint

Constraint có attributes như `min`, `max` và `value`. Resolver của REST Docs có thể dùng các attributes đó để tạo description. Khi cần thông điệp chứa số cụ thể, hãy cấu hình bundle/resolver phù hợp và **kiểm tra output thực tế** với DTO có giá trị min/max đã biết. Đừng để câu mô tả chung chung như “nằm trong giới hạn” nếu người dùng API cần biết giới hạn đó là bao nhiêu.

### 6.2. Description khác runtime validation message

| Nội dung | Mục đích | Ví dụ |
| --- | --- | --- |
| Annotation `message` | Báo lỗi cho request không hợp lệ | `Email không đúng định dạng` |
| Resource bundle `.description` | Giải thích constraint trong tài liệu | `Phải nhập email hợp lệ` |

Hai thông điệp có thể dùng cùng câu chữ nhưng khác mục tiêu. Runtime message gắn với violation cụ thể; documentation description giải thích quy tắc cho người tích hợp.

## 7. Tùy chỉnh resolver

`ConstraintDescriptions` hỗ trợ constructor truyền resolver riêng. Hai abstraction chính:

- `ConstraintResolver` tìm constraints trên class/property.
- `ConstraintDescriptionResolver` chuyển constraint thành description.

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(
        RegisterMemberRequest.class,
        constraintResolver,
        descriptionResolver
    );
~~~

Hai biến resolver phải là implementation phù hợp API/version đang dùng. `ValidatorConstraintResolver` tùy chỉnh hữu ích khi cần Validator/provider riêng. `ResourceBundleConstraintDescriptionResolver` hoặc implementation `ConstraintDescriptionResolver` riêng hữu ích khi cần thay câu chữ, locale hoặc cách diễn giải attributes.

Custom resolver không làm cho mọi business rule tự xuất hiện. Rule chỉ được thực thi trong service/domain layer vẫn cần mô tả và test riêng.

## 8. Nested properties và mapping path

Ví dụ DTO lồng nhau:

~~~java
public class RegisterMemberRequest {
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    @Size(max = 120)
    private String city;
}
~~~

JSON:

~~~json
{"address":{"city":"Ho Chi Minh City"}}
~~~

| Loại path | Ví dụ | Mục đích |
| --- | --- | --- |
| Bean property | `address.city` | Tra cứu metadata property. |
| REST Docs field path | `address.city` | Mô tả JSON field. |
| Array field path | `items[].sku` | Mô tả field trong phần tử array. |

Hai loại path đầu thường giống nhau ở DTO đơn giản, nhưng không luôn luôn. Nếu JSON mapping đổi tên, cần ánh xạ property Java với JSON field riêng. Với collection/container element constraints, đừng mặc định resolver tự ánh xạ đầy đủ sang cú pháp array; xác minh theo version/provider.

## 9. Class-level và cross-field constraints

Ví dụ rule ngày kết thúc không được trước ngày bắt đầu:

~~~java
@ValidDateRange
public class BookingRequest {
    private LocalDate startDate;
    private LocalDate endDate;
}
~~~

Đây là constraint ở cấp object. Không mặc định `descriptionsForProperty("startDate")` tự mô tả quan hệ giữa hai ngày.

Tài liệu nên diễn giải:

| Field/rule | Constraint |
| --- | --- |
| `startDate` | Ngày bắt đầu theo ISO-8601. |
| `endDate` | Ngày kết thúc theo ISO-8601. |
| Quan hệ hai field | `endDate` phải sau hoặc bằng `startDate`. |

Mô tả rule cross-field trong phần giải thích hoặc custom descriptor; viết HTTP test cho tổ hợp hợp lệ và không hợp lệ. Các rule như uniqueness, quyền sở hữu tài nguyên, hạn mức tín dụng và workflow cũng cần mô tả/test ở tầng domain.

## 10. Kết hợp với HTTP tests

Ví dụ test hợp lệ dùng descriptions trong request fields:

~~~java
@Test
void documentRegisterMember() throws Exception {
    ConstraintDescriptions constraints =
        new ConstraintDescriptions(RegisterMemberRequest.class);

    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "fullName": "Lan Nguyen",
                  "email": "lan@example.com"
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("members-register",
            requestFields(
                fieldWithPath("fullName").description(
                    "Tên thành viên. " + String.join("; ",
                        constraints.descriptionsForProperty("fullName"))
                ),
                fieldWithPath("email").description(
                    "Email liên hệ. " + String.join("; ",
                        constraints.descriptionsForProperty("email"))
                )
            )
        ));
}
~~~

Ví dụ giả định endpoint có hai field và request hợp lệ. Test cần ở lớp đã cấu hình MockMvc/REST Docs và có imports tương ứng.

Test invalid riêng:

~~~java
@Test
void rejectInvalidMemberEmail() throws Exception {
    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "fullName": "Lan Nguyen",
                  "email": "not-an-email"
                }
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("members-register-invalid"));
}
~~~

Status `400` là giả định contract; error handler thực tế có thể trả status/body khác. Khi error body có schema, khai báo response fields tương ứng. Chỉ tài liệu hóa kết quả đã được test xác nhận.

## 11. Tài liệu cuối và CI

Asciidoctor có thể include:

~~~asciidoc
= Members API

== Đăng ký thành viên

=== HTTP request
include::{snippets}/members-register/http-request.adoc[]

=== Request fields and constraints
include::{snippets}/members-register/request-fields.adoc[]

=== Validation error
include::{snippets}/members-register-invalid/http-response.adoc[]
~~~

Snippet field chỉ có constraint nếu description chứa nó hoặc custom template render metadata. Thuộc tính `snippets` phải trỏ đến output directory. Markdown renderer thuần thường không xử lý trực tiếp cú pháp Asciidoctor include.

~~~mermaid
flowchart TD
    A["DTO / constraint thay đổi"] --> B["HTTP tests: valid + invalid + boundary"]
    B --> C{"Assertions pass?"}
    C -->|Không| D["Fail CI"]
    C -->|Có| E["ConstraintDescriptions + descriptors"]
    E --> F["Sinh REST Docs snippets"]
    F --> G["Render tài liệu"]
    G --> H{"Docs pass?"}
    H -->|Không| D
    H -->|Có| I["Review và publish"]
~~~

Khi annotation thay đổi, xem lại bundle, descriptions, boundary tests và tài liệu. Snippet generation không tự bảo đảm văn bản thủ công đồng bộ. Task render phải chạy sau task test sinh snippets và không include artifact cũ còn sót.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `descriptionsForProperty(...)` trả rỗng | Property không có constraint hoặc sai tên | Kiểm tra DTO và property path. |
| Không tìm thấy constraint | Thiếu provider hoặc Validator không phù hợp | Kiểm tra dependency/provider/resolver. |
| Custom constraint không có mô tả | Bundle thiếu key | Thêm key `.description` hoặc custom resolver. |
| Description thiếu min/max | Bundle hoặc cách diễn giải attributes chưa đúng | Kiểm tra attributes và output. |
| Mô tả vẫn tiếng Anh | Locale/bundle chưa cấu hình | Tạo bundle ngôn ngữ phù hợp. |
| Nested field không tìm thấy | Java property path khác JSON field path | Tách mapping hai loại path. |
| Class-level rule không hiện | Resolver mặc định tập trung property constraints | Mô tả riêng và viết HTTP test cross-field. |
| Annotation đổi nhưng docs không đổi | Description thủ công/template không đọc metadata | Tự động hóa hoặc review docs. |
| Custom attribute không xuất hiện | Template không render attribute | Cập nhật template và kiểm tra snippet. |
| Mô tả mạnh hơn validator | Diễn giải sai semantics/provider | Kiểm tra constraint và test biên. |

## 13. Bài thực hành

Tạo DTO `CreateProductRequest`:

~~~java
public class CreateProductRequest {
    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("1000000.00")
    private BigDecimal price;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,20}")
    private String sku;
}
~~~

Thực hiện:

1. Tạo `ConstraintDescriptions(CreateProductRequest.class)`, lấy descriptions cho `name`, `price` và `sku`.
2. Thay min/max trong annotations và quan sát descriptions.
3. Tạo resource bundle tiếng Việt với key `.description`; kiểm tra locale/output.
4. Gắn descriptions vào `requestFields(...)` bằng description hoặc attributes.
5. Nếu dùng attributes, tùy chỉnh template có cột Constraints và xác minh snippet.
6. Viết HTTP tests cho request hợp lệ, giá bằng 0, SKU sai pattern và tên vượt độ dài.
7. Đối chiếu status/error response thực tế với tài liệu rồi build Asciidoctor.
8. Thêm class-level rule nếu có và giải thích vì sao cần mô tả/test riêng.

**Tiêu chí hoàn thành:** biết cách tìm property constraints bằng `ConstraintDescriptions`, tùy chỉnh câu mô tả và hiển thị chúng trong field snippet; hiểu giới hạn cơ chế mặc định; và bảo đảm tài liệu phản ánh validation logic mà HTTP tests kiểm chứng.

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
