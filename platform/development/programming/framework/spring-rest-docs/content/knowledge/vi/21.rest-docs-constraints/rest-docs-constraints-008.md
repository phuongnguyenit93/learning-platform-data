# Mô tả tùy chỉnh cho constraint

## 1. Mục tiêu bài học

Bean Validation xác định một property không được rỗng, phải nằm trong khoảng số hoặc phải khớp định dạng. Spring REST Docs có thể tìm metadata constraint và chuyển chúng thành câu mô tả để đưa vào tài liệu API. Tuy nhiên, mô tả mặc định có thể chưa phù hợp ngôn ngữ, thuật ngữ hoặc quy ước sản phẩm. Khi đó cần **tùy chỉnh cách mô tả constraint**.

Bài học thuộc chương **Constraints** của module **SPRING_REST_DOCS**. Module hướng dẫn tạo tài liệu REST API có thể kiểm chứng từ HTTP tests với MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown rồi đưa vào build và CI.

Sau bài học, bạn có thể phân biệt runtime validation message với documentation description; ghi đè mô tả qua ResourceBundle; sử dụng constraint attributes; truyền resolver riêng vào ConstraintDescriptions; gắn descriptions vào field descriptor; và kiểm thử nội dung snippet để tránh lỗi thời.

> API trung tâm của Spring REST Docs là ConstraintDescriptions. Cơ chế mặc định dùng Bean Validation Validator để tìm property constraints và ResourceBundleConstraintDescriptionResolver để mô tả. Ưu tiên resource bundle khi chỉ cần đổi câu chữ; viết resolver riêng khi cần xử lý đặc biệt.

## 2. Runtime message khác documentation description

Một annotation có thể khai báo message:

~~~java
@NotBlank(message = "Tên không được để trống")
private String name;
~~~

Message này phục vụ **runtime validation**: ứng dụng trả thông báo khi request vi phạm. Spring REST Docs có cơ chế description riêng để giải thích constraint trong tài liệu.

| Nội dung | Mục đích | Ví dụ |
| --- | --- | --- |
| Bean Validation message | Báo lỗi khi request không hợp lệ | Tên không được để trống. |
| Constraint description | Giải thích quy tắc trong tài liệu | Phải gửi tên có ít nhất một ký tự không phải khoảng trắng. |
| Field descriptor description | Giải thích ý nghĩa field | Tên hiển thị của người dùng. |
| HTTP error response | Cho client biết request bị từ chối thế nào | 400 và payload lỗi theo contract. |

Thay đổi annotation message chưa chắc thay documentation description. Thay resource bundle của REST Docs cũng không tự thay error message do controller trả về.

## 3. ConstraintDescriptions và resolver mặc định

DTO minh họa:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
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

    @Min(18)
    private Integer age;
}
~~~

Lấy descriptions:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class);

List<String> nameRules =
    descriptions.descriptionsForProperty("fullName");

List<String> emailRules =
    descriptions.descriptionsForProperty("email");
~~~

Constructor mặc định sử dụng:

- ValidatorConstraintResolver để tìm property constraints qua Bean Validation Validator.
- ResourceBundleConstraintDescriptionResolver để lấy câu mô tả từ resource bundle.

Cơ chế tìm mặc định hiện hỗ trợ property constraints. Không kỳ vọng resolver tự trích xuất mọi class-level rule, method parameter constraint hoặc business rule trong service. Kết quả descriptionsForProperty là danh sách String; người viết phải gắn chúng vào descriptor hoặc template.

## 4. Ghi đè mô tả qua resource bundle

Cách đơn giản nhất là tạo resource bundle với base name:

~~~text
org.springframework.restdocs.constraints.ConstraintDescriptions
~~~

Mỗi key là fully qualified class name của annotation constraint cộng hậu tố .description. Với Jakarta Bean Validation:

~~~properties
jakarta.validation.constraints.NotBlank.description=Không được null, rỗng hoặc chỉ chứa khoảng trắng
jakarta.validation.constraints.NotNull.description=Giá trị không được null
jakarta.validation.constraints.Size.description=Độ dài phải nằm trong giới hạn được khai báo
jakarta.validation.constraints.Email.description=Phải có định dạng email hợp lệ
jakarta.validation.constraints.Min.description=Giá trị phải lớn hơn hoặc bằng giới hạn tối thiểu
jakarta.validation.constraints.Max.description=Giá trị không được vượt quá giới hạn tối đa
~~~

Đặt bundle trong classpath theo quy tắc Java ResourceBundle. Có thể dùng bundle mặc định và bundle locale tiếng Việt theo convention của dự án. Dùng package jakarta.validation.constraints cho Jakarta Bean Validation; dự án cũ dùng javax.validation phải khai báo key theo package annotation thực tế.

### 4.1. Ghi đè một constraint

Resource bundle có thể chỉ override một key. Ví dụ:

~~~properties
jakarta.validation.constraints.NotBlank.description=Không được để trống hoặc chỉ gồm dấu cách
~~~

Description của NotBlank được lấy từ bundle tùy chỉnh; constraints khác trên cùng property vẫn được resolver xử lý bình thường. Không cần tự viết resolver hoàn toàn mới chỉ để đổi một câu.

Nếu có nhiều locale, hãy bảo đảm locale được chọn trong build giống ngôn ngữ tài liệu. Không phụ thuộc locale cá nhân của máy developer vì CI có thể chạy với thiết lập khác.

### 4.2. Dùng attributes của constraint

Một số constraints có attributes:

| Constraint | Attribute | Ý nghĩa |
| --- | --- | --- |
| @Min(18) | value | Ngưỡng tối thiểu. |
| @Max(120) | value | Ngưỡng tối đa. |
| @Size(min=2,max=80) | min, max | Giới hạn kích thước. |
| @DecimalMin | value, inclusive | Ngưỡng và tính bao gồm biên. |
| @Digits | integer, fraction | Số chữ số phần nguyên/phần thập phân. |
| @Pattern | regexp, flags | Pattern và flags. |

Resource bundle hỗ trợ placeholder trỏ tới constraint attributes. Mô tả mặc định của Min có thể dùng placeholder cho value. Ví dụ bundle tiếng Việt:

~~~properties
jakarta.validation.constraints.Min.description=Giá trị phải từ ngưỡng tối thiểu được khai báo trở lên
jakarta.validation.constraints.Max.description=Giá trị không được vượt quá ngưỡng tối đa được khai báo
jakarta.validation.constraints.Size.description=Độ dài phải nằm trong khoảng min đến max được khai báo
~~~

Khi cần hiển thị con số cụ thể, dùng placeholder theo đúng tên attribute mà constraint cung cấp, rồi kiểm tra description thực tế được resolver trả về. Nếu bundle sai key, sai package hoặc locale không được tải, kết quả không như mong đợi.

Với Pattern, tránh in nguyên regex dài cho API consumer. Có thể override description thành ngôn ngữ nghiệp vụ, ví dụ “Mã đơn hàng gồm 3–20 ký tự in hoa, chữ số hoặc dấu gạch ngang”, nhưng câu chữ phải đúng với validator thực tế.

### 4.3. Tránh mô tả sai biên và đơn vị

DecimalMin/DecimalMax có thể phân biệt biên bao gồm hay loại trừ. Nếu inclusive=false, câu “từ 0.01 trở lên” có thể sai semantics. Size cũng có đơn vị khác nhau: ký tự với string, phần tử với collection/array, entry với map. Hãy diễn giải theo kiểu dữ liệu thực tế.

## 5. ResourceBundleConstraintDescriptionResolver

ResourceBundleConstraintDescriptionResolver là implementation có sẵn của ConstraintDescriptionResolver. Constructor không tham số dùng bundle mặc định theo base name org.springframework.restdocs.constraints.ConstraintDescriptions và locale mặc định. Constructor khác nhận một ResourceBundle cụ thể.

Ví dụ:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.constraints.ResourceBundleConstraintDescriptionResolver;

ResourceBundle bundle = ResourceBundle.getBundle(
    "org.springframework.restdocs.constraints.ConstraintDescriptions",
    Locale.forLanguageTag("vi")
);

ResourceBundleConstraintDescriptionResolver resolver =
    new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, resolver);
~~~

Cách này hữu ích khi cần cố định locale thay vì phụ thuộc default locale của JVM. Base name phải trỏ tới resource nằm trên classpath. Nếu bundle không được tìm thấy, kiểm tra classpath, tên bundle, locale và key fully qualified.

### 5.1. Các constructor của ConstraintDescriptions

| Constructor | Tác dụng |
| --- | --- |
| ConstraintDescriptions(Class<?>) | Resolver mặc định cho việc tìm và mô tả. |
| ConstraintDescriptions(Class<?>, ConstraintResolver) | Thay cơ chế tìm constraint, giữ resolver mô tả mặc định. |
| ConstraintDescriptions(Class<?>, ConstraintDescriptionResolver) | Giữ cách tìm mặc định, thay resolver mô tả. |
| ConstraintDescriptions(Class<?>, ConstraintResolver, ConstraintDescriptionResolver) | Tùy chỉnh cả tìm kiếm và mô tả. |

Nếu chỉ đổi câu chữ, constructor nhận ConstraintDescriptionResolver là đủ. Không thay Validator resolver nếu việc tìm property constraints vẫn đúng.

## 6. Viết ConstraintDescriptionResolver riêng

Interface ConstraintDescriptionResolver có phương thức:

~~~java
String resolveDescription(Constraint constraint);
~~~

Phương thức nhận một Constraint do Spring REST Docs tạo từ metadata validation và trả về câu mô tả. Khi cần logic riêng, triển khai interface này. Một hướng an toàn là ủy quyền cho ResourceBundleConstraintDescriptionResolver trước, sau đó áp dụng các quy tắc chuẩn hóa đã được kiểm soát.

~~~java
import org.springframework.restdocs.constraints.Constraint;
import org.springframework.restdocs.constraints.ConstraintDescriptionResolver;

public class ProjectConstraintDescriptionResolver
        implements ConstraintDescriptionResolver {

    private final ConstraintDescriptionResolver delegate;

    public ProjectConstraintDescriptionResolver(
            ConstraintDescriptionResolver delegate) {
        this.delegate = delegate;
    }

    @Override
    public String resolveDescription(Constraint constraint) {
        String description = this.delegate.resolveDescription(constraint);
        // Áp dụng quy tắc riêng đã được kiểm thử nếu cần.
        return description;
    }
}
~~~

Ví dụ là wrapper minh họa điểm mở rộng; constructor phải được cung cấp delegate tương ứng. Nếu không thêm logic xử lý, kết quả vẫn là mô tả của delegate. Không giả định class tự động dịch chỉ vì tên có chữ Project.

Sử dụng:

~~~java
ResourceBundleConstraintDescriptionResolver resourceResolver =
    new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptionResolver customResolver =
    new ProjectConstraintDescriptionResolver(resourceResolver);

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, customResolver);
~~~

Khi resolver thực sự thay đổi câu chữ, cần test output cho từng custom rule, locale fallback và trường hợp không có mapping. Tránh replace chuỗi tổng quát nếu một cụm từ phụ thuộc attributes hoặc ngữ cảnh.

## 7. Mô tả custom constraint annotation

Ứng dụng có thể định nghĩa annotation riêng:

~~~java
@Target({ ElementType.FIELD, ElementType.PARAMETER })
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StrongPasswordValidator.class)
public @interface StrongPassword {
    String message() default "Mật khẩu không đáp ứng chính sách";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Nếu Validator nhận diện đây là property constraint, REST Docs có thể tìm metadata tương ứng. Để cung cấp description, thêm resource bundle key theo fully qualified annotation name:

~~~properties
com.example.validation.StrongPassword.description=Mật khẩu phải có ít nhất 12 ký tự và đáp ứng chính sách mật khẩu của hệ thống
~~~

Mô tả phải phản ánh validator thực tế. Nếu validator chỉ kiểm tra độ dài, không thêm yêu cầu chữ hoa/chữ số. Nếu policy thay đổi theo tenant hoặc cấu hình, tài liệu cần giải thích phạm vi thay vì mô tả một giới hạn cố định cho mọi người dùng.

## 8. Gắn description vào field descriptor

Sau khi có danh sách mô tả, có thể nối trực tiếp vào description:

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, resolver);

requestFields(
    fieldWithPath("fullName").description(
        "Tên đầy đủ. " + String.join("; ",
            descriptions.descriptionsForProperty("fullName"))
    ),
    fieldWithPath("email").description(
        "Email liên hệ. " + String.join("; ",
            descriptions.descriptionsForProperty("email"))
    )
)
~~~

Cách này dùng được với template mặc định vì constraint nằm trong description. Nó dễ triển khai nhưng có thể làm cột mô tả dài khi DTO lớn.

### 8.1. Descriptor attributes và custom snippet

Có thể lưu constraint trong attribute riêng:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

FieldDescriptor email = fieldWithPath("email")
    .description("Email liên hệ")
    .attributes(key("constraints").value(
        String.join("; ", descriptions.descriptionsForProperty("email"))
    ));
~~~

Key constraints do dự án đặt tên. Template mặc định không tự render attribute nếu không đọc key này. Một custom fields snippet có thể thêm cột Constraints:

| Field | Description | Constraints |
| --- | --- | --- |
| fullName | Tên đầy đủ | Không để trống; độ dài 2–80 ký tự. |
| email | Email liên hệ | Định dạng email hợp lệ; tối đa 254 ký tự. |

Để hiển thị cột riêng, sao chép template fields đúng version Spring REST Docs, thêm logic đọc descriptor attribute và chạy test xác minh snippet. Không sử dụng cú pháp template từ version khác mà chưa kiểm tra.

## 9. HTTP tests chứng minh description phản ánh validation

DTO ví dụ:

~~~java
public class CreateMemberRequest {
    @NotBlank
    @Size(min = 2, max = 80)
    private String name;

    @NotBlank
    @Email
    private String email;
}
~~~

Test hợp lệ:

~~~java
@Test
void createMemberWithValidInput() throws Exception {
    ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateMemberRequest.class, resolver);

    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"Lan Nguyen","email":"lan@example.com"}
                """))
        .andExpect(status().isCreated())
        .andDo(document("members-create",
            requestFields(
                fieldWithPath("name").description(
                    "Tên thành viên. " + String.join("; ",
                        descriptions.descriptionsForProperty("name"))
                ),
                fieldWithPath("email").description(
                    "Email. " + String.join("; ",
                        descriptions.descriptionsForProperty("email"))
                )
            )
        ));
}
~~~

Ví dụ giả định endpoint và fixture trả 201 Created, và resolver đã được cấu hình trước test. Lớp test cần cấu hình MockMvc/REST Docs và các imports phù hợp.

Test không hợp lệ:

~~~java
@Test
void rejectInvalidMemberEmail() throws Exception {
    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"Lan Nguyen","email":"not-an-email"}
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("members-create-invalid"));
}
~~~

400 Bad Request là giả định error contract. Ứng dụng có thể ánh xạ validation failures sang status hoặc schema khác. Cần assert đúng response và mô tả đúng error fields; không coi format lỗi trên là mặc định của REST Docs.

### 9.1. Test các giá trị biên

| Rule | Giá trị hợp lệ | Giá trị nên thử |
| --- | --- | --- |
| @NotBlank | "Lan" | Chuỗi rỗng, whitespace, null. |
| @Size(min=2,max=80) | Dài 2 và 80 | Dài 1 và 81. |
| @Email | lan@example.com | Chuỗi sai định dạng. |
| @Min(18) | 18 | 17. |
| @Max(120) | 120 | 121. |

Nếu resource bundle đổi, HTTP validation có thể vẫn pass nhưng snippet description khác. Nên review diff snippet hoặc có kiểm tra đầu ra mô tả phù hợp trong CI.

## 10. Locale và tính ổn định trong CI

Constructor mặc định của ResourceBundleConstraintDescriptionResolver dùng default locale và thread context class loader. Nếu developer và CI có locale khác nhau, snippet có thể sinh ra hai ngôn ngữ khác nhau.

Để ổn định:

- Chọn locale rõ ràng khi tạo ResourceBundle.
- Bảo đảm bundle nằm trong classpath của task sinh snippet.
- Không phụ thuộc locale cá nhân trên máy.
- Kiểm tra UTF-8 và ký tự tiếng Việt sau build.
- Giữ descriptions ổn định để diff chỉ phản ánh thay đổi có chủ đích.

Nếu cần kết quả cố định, tạo ResourceBundle theo locale mong muốn rồi truyền vào constructor nhận bundle như ví dụ ở trên.

## 11. Giới hạn cần hiểu

Tùy chỉnh description cải thiện ngôn ngữ tài liệu nhưng không thay đổi hành vi validation:

1. Description không thực thi validation; HTTP tests vẫn phải gửi dữ liệu và assert kết quả.
2. ConstraintDescriptions mặc định tìm property constraints; class-level, method parameter và domain constraints cần mô tả riêng.
3. Resource bundle chỉ thay câu chữ cho annotation có key; nó không phát hiện mọi business rule.
4. Custom template chỉ render metadata nếu descriptor đã gắn attribute đúng key.
5. Placeholder phải phản ánh đúng attributes, đơn vị và biên inclusive/exclusive.
6. Documentation description không đồng nghĩa runtime error message.
7. Nếu constraint phụ thuộc tenant, feature flag hoặc cấu hình động, tài liệu cần nói rõ phạm vi.

## 12. CI và review thay đổi

~~~mermaid
flowchart TD
    A["Thay đổi annotation hoặc policy"] --> B["Cập nhật ResourceBundle / resolver"]
    B --> C["HTTP tests hợp lệ, không hợp lệ và biên"]
    C --> D{"Validation assertions pass?"}
    D -->|No| E["Fail build"]
    D -->|Yes| F["Sinh REST Docs snippets"]
    F --> G["Review descriptions và field tables"]
    G --> H["Render Asciidoctor/Markdown"]
    H --> I{"Snippet và docs pass?"}
    I -->|No| E
    I -->|Yes| J["Package / Publish"]
~~~

Khi description thay đổi, review cả raw request/response lẫn request-fields/response-fields. Render task phải chạy sau test sinh snippet, không include artifacts cũ. Nếu custom template đổi, xác minh cột constraints không làm mất field description đang có.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Description vẫn tiếng Anh | Bundle tiếng Việt không được tải hoặc locale sai | Kiểm tra base name, locale, classpath và resolver. |
| Key tùy chỉnh không có tác dụng | Sai fully qualified annotation name hoặc thiếu hậu tố description | Đối chiếu package và key chính xác. |
| Placeholder không thay | Sai tên attribute hoặc constraint không có attribute đó | Kiểm tra metadata và output. |
| Runtime message đổi nhưng docs không đổi | Bean Validation message khác REST Docs description | Cập nhật đúng bundle documentation. |
| Docs đổi nhưng runtime error giữ nguyên | Chỉ sửa REST Docs bundle | Cập nhật validation message nếu cần. |
| Custom description không hiện | Chưa gắn descriptor hoặc template không đọc attribute | Kiểm tra descriptor và template. |
| Locale CI khác máy dev | Dùng default JVM locale | Cố định locale khi tạo resolver. |
| Custom constraint không có mô tả | Bundle thiếu key | Thêm key hoặc resolver riêng. |
| Mô tả sai biên | Không kiểm tra inclusive/exclusive | Đối chiếu attributes và test biên. |
| Business rule không xuất hiện | Không phải property constraint | Mô tả và test ở tầng domain/API. |

## 14. Bài thực hành

Tạo DTO CreateProductRequest:

~~~java
public class CreateProductRequest {
    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin(value = "0.01", inclusive = true)
    @DecimalMax(value = "1000000.00", inclusive = true)
    private BigDecimal price;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,20}")
    private String sku;
}
~~~

Thực hiện:

1. Dùng ConstraintDescriptions lấy descriptions cho name, price và sku.
2. Tạo resource bundle theo base name của Spring REST Docs; override NotBlank, Size, DecimalMin và DecimalMax.
3. Dùng placeholders cho attributes và xác minh description trả về đúng min/max.
4. Tạo resolver với ResourceBundle locale tiếng Việt; xác nhận CI sinh kết quả giống nhau.
5. Gắn descriptions vào field descriptor; thử ghép trong description và cột constraints qua custom template.
6. Viết HTTP tests cho request hợp lệ, giá bằng 0, SKU sai pattern và tên vượt độ dài.
7. So sánh runtime error message với documentation description.
8. Thay một giới hạn và review snippet diff, tài liệu cuối và pipeline.

**Tiêu chí hoàn thành:** tùy chỉnh được constraint descriptions theo ngôn ngữ/thuật ngữ dự án; hiển thị đúng trong field snippet; hiểu sự khác nhau giữa runtime message và documentation description; có HTTP tests và CI giữ tài liệu đồng bộ với validation logic.

## Tài liệu tham khảo

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Spring REST Docs — ResourceBundleConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ResourceBundleConstraintDescriptionResolver.html)
- [Spring REST Docs — ConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptionResolver.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
