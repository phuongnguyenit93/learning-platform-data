# ConstraintDescriptionResolver và mô tả constraint

## 1. Vai trò của constraint trong tài liệu API

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Người tích hợp cần biết không chỉ tên và kiểu của field mà còn những giới hạn dữ liệu: chuỗi không được để trống, email phải hợp lệ, số nằm trong khoảng nào, hoặc ngày phải ở thời điểm nào.

Ví dụ DTO:

```java
class CreateUserRequest {
    @NotBlank
    @Size(min = 2, max = 60)
    String name;

    @NotBlank
    @Email
    String email;

    @NotNull
    @Min(18)
    @Max(120)
    Integer age;
}
```

Các annotation Bean Validation lưu ràng buộc ngay trong mã nguồn. Spring REST Docs có thể đọc metadata này và chuyển thành câu mô tả để đưa vào snippet. Nhờ vậy tài liệu dùng lại giới hạn được khai báo trong DTO thay vì viết thủ công ở nhiều nơi.

Các lớp chính trong package `org.springframework.restdocs.constraints`:

| Thành phần | Vai trò |
| --- | --- |
| `ConstraintDescriptions` | API lấy mô tả constraint theo class và property |
| `ConstraintResolver` | Tìm constraint áp dụng cho property |
| `ValidatorConstraintResolver` | Tìm constraint bằng Bean Validation `Validator` |
| `ConstraintDescriptionResolver` | Chuyển constraint đã tìm thấy thành câu mô tả |
| `ResourceBundleConstraintDescriptionResolver` | Resolver mặc định tra mô tả từ `ResourceBundle` |
| `Constraint` | Đại diện constraint bằng tên và map thuộc tính cấu hình |

Cần tách hai bước: **tìm constraint** và **diễn giải constraint**. `ConstraintDescriptionResolver` chỉ làm bước thứ hai. Muốn thay đổi cách tìm metadata, hãy xem `ConstraintResolver` hoặc `ValidatorConstraintResolver`.

## 2. Lấy mô tả bằng ConstraintDescriptions

Cách dùng cơ bản:

```java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateUserRequest.class);

List<String> nameDescriptions =
        descriptions.descriptionsForProperty("name");

List<String> emailDescriptions =
        descriptions.descriptionsForProperty("email");
```

`descriptionsForProperty("name")` trả danh sách mô tả các constraint trên **tên property Java** `name`, chẳng hạn `@NotBlank` và `@Size(min = 2, max = 60)`. Nội dung chính xác phụ thuộc resolver và resource bundle.

Tên property truyền vào không nhất thiết là JSON path. Nếu Java property là `displayName` nhưng JSON dùng `display_name` qua `@JsonProperty`, truy vấn constraint bằng `displayName`, còn descriptor REST Docs dùng path JSON `display_name`.

Mặc định constraint được tìm bằng Bean Validation `Validator`. Tài liệu Spring REST Docs hiện tại nêu rằng cơ chế mặc định hỗ trợ **property constraints**. Không giả định class-level, cross-field hoặc method constraints đều tự xuất hiện qua `descriptionsForProperty`. Quy tắc liên trường như ngày bắt đầu phải trước ngày kết thúc cần được mô tả và kiểm thử riêng, hoặc cần resolver tìm constraint phù hợp.

## 3. ConstraintDescriptionResolver là gì?

`ConstraintDescriptionResolver` là interface chuyển một đối tượng `Constraint` thành câu mô tả:

```java
public interface ConstraintDescriptionResolver {
    String resolveDescription(Constraint constraint);
}
```

`Constraint` cung cấp hai thông tin chính:

- `getName()`: tên đầy đủ của constraint, ví dụ `jakarta.validation.constraints.Size`.
- `getConfiguration()`: map thuộc tính như `min`, `max`, `value` hoặc `regexp`.

Resolver có thể tra từ điển theo tên constraint, dùng thuộc tính cấu hình để điền câu mô tả và trả kết quả. Nó không chạy validation trên dữ liệu; nó diễn giải metadata đã được tìm thấy.

### 3.1. ResourceBundleConstraintDescriptionResolver

Resolver mặc định `ResourceBundleConstraintDescriptionResolver` tra resource bundle có base name:

```text
org.springframework.restdocs.constraints.ConstraintDescriptions
```

Mỗi key là tên đầy đủ của constraint cộng hậu tố `.description`. Ví dụ:

```properties
jakarta.validation.constraints.NotNull.description=Trường này không được null
jakarta.validation.constraints.NotBlank.description=Trường này không được để trống
jakarta.validation.constraints.Size.description=Độ dài phải từ ${min} đến ${max} ký tự
jakarta.validation.constraints.Email.description=Phải là địa chỉ email hợp lệ
jakarta.validation.constraints.Min.description=Giá trị phải lớn hơn hoặc bằng ${value}
jakarta.validation.constraints.Max.description=Giá trị phải nhỏ hơn hoặc bằng ${value}
```

Các placeholder `${min}`, `${max}` và `${value}` trong resource bundle được thay bằng thuộc tính cấu hình của constraint. Vì vậy cùng một key Size có thể cho kết quả khác nhau ở `name` và `password`.

Tên class trong key phải khớp namespace annotation. Ứng dụng dùng Jakarta Validation có key bắt đầu bằng `jakarta.validation.constraints`. Dự án cũ dùng `javax.validation.constraints` cần key theo namespace đó.

### 3.2. Ghi đè mô tả mặc định

Resource bundle phù hợp khi cần dịch câu mô tả sang tiếng Việt, thống nhất thuật ngữ domain, bổ sung mô tả cho annotation riêng hoặc thay cách diễn đạt mặc định mà vẫn giữ giá trị động từ annotation.

Ví dụ:

```properties
jakarta.validation.constraints.Size.description=Độ dài phải từ ${min} đến ${max} ký tự
```

Nếu `name` có `min = 2, max = 60`, mô tả trả về có thể là “Độ dài phải từ 2 đến 60 ký tự”. Không ghi cứng con số trong từng descriptor nếu annotation đã chứa metadata.

## 4. Tùy biến ConstraintDescriptionResolver

Khi resource bundle không đủ linh hoạt, có thể triển khai interface. Ví dụ sau ánh xạ một số constraint phổ biến sang câu tiếng Việt và thay placeholder bằng cấu hình:

```java
import java.util.Map;

import org.springframework.restdocs.constraints.Constraint;
import org.springframework.restdocs.constraints.ConstraintDescriptionResolver;

class VietnameseConstraintDescriptionResolver
        implements ConstraintDescriptionResolver {

    private static final Map<String, String> TEMPLATES = Map.of(
        "jakarta.validation.constraints.NotBlank",
        "Không được để trống",
        "jakarta.validation.constraints.Email",
        "Phải là địa chỉ email hợp lệ",
        "jakarta.validation.constraints.Size",
        "Độ dài phải từ ${min} đến ${max} ký tự",
        "jakarta.validation.constraints.Min",
        "Giá trị phải lớn hơn hoặc bằng ${value}"
    );

    @Override
    public String resolveDescription(Constraint constraint) {
        String template = TEMPLATES.get(constraint.getName());
        if (template == null) {
            return "Phải thỏa mãn constraint " + constraint.getName();
        }

        String result = template;
        for (Map.Entry<String, Object> entry
                : constraint.getConfiguration().entrySet()) {
            result = result.replace(
                    "${" + entry.getKey() + "}",
                    String.valueOf(entry.getValue()));
        }
        return result;
    }
}
```

Kết nối resolver tùy chỉnh:

```java
ConstraintDescriptions descriptions =
        new ConstraintDescriptions(
                CreateUserRequest.class,
                new VietnameseConstraintDescriptionResolver());

List<String> nameRules =
        descriptions.descriptionsForProperty("name");
```

Constructor này thay resolver mô tả; bước tìm constraint vẫn dùng `ValidatorConstraintResolver` mặc định.

Đây là ví dụ tối giản. Trong production cần chính sách cho placeholder chưa thay, kiểu dữ liệu, locale và constraint chưa có template. Nếu muốn giữ đầy đủ hành vi chuẩn khi thay placeholder, thường nên tùy chỉnh resource bundle thay vì tự viết lại logic.

## 5. Chọn ResourceBundle theo locale

`ResourceBundleConstraintDescriptionResolver` có constructor mặc định và constructor nhận một `ResourceBundle` cụ thể. Ví dụ:

```java
import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.constraints.ResourceBundleConstraintDescriptionResolver;

ResourceBundle bundle = ResourceBundle.getBundle(
        "org.springframework.restdocs.constraints.ConstraintDescriptions",
        Locale.forLanguageTag("vi"));

ResourceBundleConstraintDescriptionResolver resolver =
        new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateUserRequest.class, resolver);
```

Cấu trúc bundle theo base name chuẩn có thể là:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── constraints/
                ├── ConstraintDescriptions.properties
                └── ConstraintDescriptions_vi.properties
```

Constructor mặc định dùng default locale và thread context class loader. Nếu cần kết quả nhất quán giữa máy developer và CI, nên chỉ định locale hoặc cấu hình môi trường build thống nhất.

Không cần viết resolver tùy chỉnh chỉ để dịch mô tả. Resource bundle đơn giản hơn cho trường hợp này.

## 6. Ghép constraint descriptions vào FieldDescriptor

Sau khi lấy mô tả, có thể ghép vào description của field:

```java
ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateUserRequest.class);

String nameDescription = "Tên hiển thị của người dùng. "
        + String.join("; ",
            constraints.descriptionsForProperty("name"));

requestFields(
    fieldWithPath("name").description(nameDescription)
)
```

Có thể tạo helper để dùng chung:

```java
static String withConstraints(
        String businessDescription,
        List<String> constraintDescriptions) {

    if (constraintDescriptions.isEmpty()) {
        return businessDescription;
    }

    return businessDescription + " Ràng buộc: "
            + String.join("; ", constraintDescriptions);
}
```

Dùng helper:

```java
ConstraintDescriptions userConstraints =
        new ConstraintDescriptions(CreateUserRequest.class);

requestFields(
    fieldWithPath("name").description(
        withConstraints(
            "Tên hiển thị của người dùng",
            userConstraints.descriptionsForProperty("name"))),
    fieldWithPath("email").description(
        withConstraints(
            "Địa chỉ liên hệ",
            userConstraints.descriptionsForProperty("email")))
)
```

`requestFields` thường phù hợp vì Bean Validation thường được áp dụng trên DTO request. Có thể thêm constraint vào response field nếu contract response thực sự bảo đảm quy tắc đó, nhưng không mặc định validation đầu vào chứng minh mọi response đều tuân thủ cùng constraint.

## 7. Đưa constraint vào metadata cho custom snippet

Nếu muốn tách business description khỏi constraint description, có thể gắn metadata vào descriptor:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

List<String> nameConstraints =
        userConstraints.descriptionsForProperty("name");

requestFields(
    fieldWithPath("name")
        .description("Tên hiển thị của người dùng")
        .attributes(key("constraints").value(nameConstraints))
)
```

Attribute không tự tạo cột mới trong snippet mặc định. Custom snippet template phải đọc `constraints` và render nó. Ví dụ bảng mong muốn:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| name | String | Tên hiển thị của người dùng | Không để trống; dài từ 2 đến 60 ký tự |
| email | String | Địa chỉ liên hệ | Định dạng email hợp lệ |

Đây là cách phù hợp khi nhóm muốn chuẩn hóa constraint thành cột riêng. Cần cấu hình đúng template và kiểm tra snippet sau khi render; không giả định descriptor attribute tự xuất hiện trong output mặc định.

## 8. MockMvc: sinh request fields kèm constraint

Ví dụ dùng JUnit Jupiter, MockMvc, Spring REST Docs MockMvc, Bean Validation API và một provider như Hibernate Validator. Với Spring Boot, dependency validation thường được cung cấp qua starter validation tương ứng.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CreateUserConstraintDocumentationTest {

    private MockMvc mockMvc;

    private final ConstraintDescriptions constraints =
            new ConstraintDescriptions(CreateUserRequest.class);

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new UserController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentCreateUserRequestConstraints() throws Exception {
        String nameDescription = "Tên người dùng. "
                + String.join("; ",
                    constraints.descriptionsForProperty("name"));
        String emailDescription = "Địa chỉ email. "
                + String.join("; ",
                    constraints.descriptionsForProperty("email"));

        mockMvc.perform(post("/api/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name": "Lan Nguyen",
                              "email": "lan@example.test"
                            }
                            """))
                .andExpect(status().isCreated())
                .andDo(document("users-create-constraints",
                        requestFields(
                                fieldWithPath("name")
                                        .description(nameDescription),
                                fieldWithPath("email")
                                        .description(emailDescription)
                        )
                ));
    }

    record CreateUserRequest(
            @NotBlank @Size(min = 2, max = 60) String name,
            @NotBlank @Email String email) {}

    @RestController
    static class UserController {
        @PostMapping("/api/users")
        ResponseEntity<Void> create(
                @Valid @RequestBody CreateUserRequest request) {
            return ResponseEntity.status(201).build();
        }
    }
}
```

Trong ví dụ, `ConstraintDescriptions` đọc annotation trên DTO; `descriptionsForProperty` trả mô tả theo tên property; `String.join` ghép constraint vào `FieldDescriptor`; `@Valid` kích hoạt Bean Validation khi Spring bind request; `requestFields` xác minh payload và sinh snippet.

Test gửi dữ liệu hợp lệ để nhận `201 Created`. Ứng dụng thực tế cần thêm test request sai để chứng minh validation được kích hoạt và trả status/lỗi đúng contract. Có câu mô tả trong snippet không tự chứng minh validation đang bật ở runtime.

## 9. Constraint tự định nghĩa

Ứng dụng có thể có constraint riêng như `@VietnamesePhoneNumber` hoặc `@ValidSku`. Để mô tả bằng bundle, key dùng fully-qualified name của annotation cộng `.description`.

Ví dụ annotation:

```java
@Constraint(validatedBy = VietnamesePhoneNumberValidator.class)
@Target({ FIELD, PARAMETER, ANNOTATION_TYPE })
@Retention(RUNTIME)
public @interface VietnamesePhoneNumber {
    String message() default "Số điện thoại không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Key trong bundle:

```properties
com.example.validation.VietnamesePhoneNumber.description=Phải là số điện thoại Việt Nam theo định dạng được API chấp nhận
```

Nếu bundle không có key tương ứng, resolver mặc định không thể đưa ra câu mô tả domain mong muốn. Hãy bổ sung message và viết test xác nhận.

Với resolver tự viết, cần chính sách cho constraint chưa biết: trả fallback có tên constraint hoặc fail sớm trong test tài liệu để buộc bổ sung mô tả. Không nên trả chuỗi rỗng hoặc âm thầm bỏ qua constraint mới nếu contract yêu cầu công bố đầy đủ.

## 10. ConstraintResolver và ValidatorConstraintResolver

Spring REST Docs tách cơ chế **tìm constraint** khỏi cơ chế **diễn giải constraint**:

| Thành phần | Trách nhiệm | Khi nào tùy biến? |
| --- | --- | --- |
| `ValidatorConstraintResolver` | Dùng Bean Validation `Validator` tìm constraint trên property | Khi cần thay Validator/provider hoặc truy cập metadata |
| `ConstraintResolver` | Trừu tượng hóa việc tìm constraint theo property và class | Khi cần nguồn/cách tìm khác |
| `ConstraintDescriptionResolver` | Chuyển constraint đã tìm thành câu mô tả | Khi cần dịch, đổi thuật ngữ hoặc hỗ trợ custom constraint |
| `ResourceBundleConstraintDescriptionResolver` | Tra mô tả từ resource bundle | Khi cần thông điệp theo locale/bundle |

Mặc định:

```java
new ConstraintDescriptions(CreateUserRequest.class)
```

sử dụng resolver dựa trên Validator để tìm constraint và resource-bundle resolver để mô tả. Nếu chỉ cần đổi câu tiếng Việt, truyền `ConstraintDescriptionResolver` hoặc bundle mới là đủ. Nếu muốn thay cách tìm metadata, cung cấp `ConstraintResolver` riêng qua constructor tương ứng.

Tài liệu Spring REST Docs hiện tại nêu giới hạn hỗ trợ property constraints. Quy tắc liên trường như `startDate < endDate` cần mô tả và kiểm thử nghiệp vụ riêng; không giả định `descriptionsForProperty` tự đọc class-level rule.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Danh sách mô tả rỗng | Property không có constraint, sai tên hoặc Validator không tìm được | Kiểm tra DTO và tên Java property |
| Không có mô tả custom annotation | Thiếu key bundle theo fully-qualified name | Thêm key .description hoặc custom resolver |
| Placeholder không được thay | Key thuộc tính không khớp hoặc resolver tự viết chưa xử lý | Dùng đúng resolver và placeholder |
| Lỗi namespace javax/jakarta | Annotation và bundle khác namespace | Dùng namespace theo dependency |
| Mô tả trùng ý business | Ghép constraint vào câu đã lặp | Tách business meaning khỏi validation rule |
| Constraint không phản ánh HTTP behavior | Annotation có nhưng validation không chạy | Kiểm tra `@Valid`, provider và test request invalid |
| Template không hiển thị attribute | Dùng snippet mặc định | Cấu hình template đọc attribute |
| Class-level constraint không hiện | Cơ chế mặc định tập trung property constraints | Mô tả/test quy tắc liên trường hoặc resolver riêng |
| Kết quả khác nhau giữa máy và CI | Locale mặc định khác nhau | Chỉ định locale/resource bundle |

## 12. Bài thực hành

Dùng `CreateUserRequest` ở mục 8:

1. Lấy mô tả `@NotBlank` và `@Size(min = 2, max = 60)` qua `descriptionsForProperty("name")`.
2. Thêm `@Pattern` cho field `phone` và bổ sung mô tả tiếng Việt trong bundle.
3. Tạo `@VietnamesePhoneNumber`, thêm key bundle theo fully-qualified name và xác nhận description.
4. Thay resolver mặc định bằng `VietnameseConstraintDescriptionResolver`; thử constraint đã biết và chưa có template.
5. Truyền bundle locale Việt Nam vào `ResourceBundleConstraintDescriptionResolver` và so sánh default locale.
6. Ghép constraint descriptions vào `requestFields` và kiểm tra snippet có giới hạn min/max.
7. Tạo custom snippet template có cột Constraints, gắn attribute `constraints` và xác nhận template render đúng.
8. Gửi request không hợp lệ để xác nhận Bean Validation thực sự chặn request.
9. Thêm quy tắc ngày bắt đầu trước ngày kết thúc; viết test nghiệp vụ và mô tả riêng.

**Tiêu chí hoàn thành:** bạn có thể lấy constraint từ Bean Validation bằng `ConstraintDescriptions`, hiểu ranh giới giữa `ConstraintResolver` và `ConstraintDescriptionResolver`, ghi đè mô tả bằng resource bundle, viết resolver tùy chỉnh, gắn câu mô tả vào descriptor/snippet và kiểm tra tài liệu phản ánh validation đang thực thi.

## Tài liệu tham khảo

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): tìm constraint, resource bundle và chèn mô tả vào snippet.
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html): constructor và `descriptionsForProperty`.
- [Spring REST Docs — ConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptionResolver.html): `resolveDescription(Constraint)`.
- [Spring REST Docs — Constraint API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/Constraint.html): `getName()` và `getConfiguration()`.
