# @NotNull, @NotBlank, @Size, @Pattern và @Email

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, tài liệu request cần giải thích những điều kiện mà dữ liệu đầu vào phải thỏa mãn. Bean Validation cung cấp các annotation chuẩn để biểu diễn nhiều điều kiện thông dụng. Năm annotation thường gặp là **@NotNull, @NotBlank, @Size, @Pattern và @Email**.

Khi các annotation được khai báo trên DTO, Spring REST Docs có thể tìm constraint của từng thuộc tính và cung cấp mô tả để đưa vào request-fields snippet. Nhờ đó tài liệu API giải thích được field bắt buộc hay tùy chọn, độ dài hợp lệ, định dạng chuỗi và định dạng email.

Sau bài này, bạn có thể:

- Phân biệt ý nghĩa và phạm vi kiểm tra của từng annotation.
- Chọn annotation phù hợp với kiểu dữ liệu và quy tắc nghiệp vụ.
- Kết hợp nhiều constraint trên một thuộc tính mà không tạo kỳ vọng sai.
- Khai báo constraint theo Jakarta Validation trong Spring Boot 3/4.
- Hiểu sự khác nhau giữa annotation constraint, việc chạy Validator và việc mô tả constraint trong REST Docs.
- Dùng ConstraintDescriptions để đưa mô tả ràng buộc vào snippet của API.
- Viết test kiểm chứng cả request hợp lệ và request không hợp lệ.

## 1. Tổng quan năm annotation

| Annotation | Kiểm tra điều gì? | Dùng điển hình |
| --- | --- | --- |
| **@NotNull** | Giá trị không được là null | ID, ngày tháng, object hoặc giá trị bắt buộc |
| **@NotBlank** | Chuỗi không được null, rỗng hoặc chỉ gồm whitespace | Tên, username, trường văn bản bắt buộc |
| **@Size** | Kích thước/độ dài nằm trong giới hạn min và max | Độ dài chuỗi, số phần tử collection, số entry map |
| **@Pattern** | Chuỗi phải khớp regular expression | Mã định danh, mã bưu chính, mã sản phẩm có định dạng |
| **@Email** | Chuỗi có định dạng email hợp lệ theo validator | Địa chỉ email trong request |

Ví dụ import:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
```

Các annotation trên thuộc **Jakarta Bean Validation**. Trong Spring Boot 3/4 thường dùng package jakarta.validation.constraints. Ở ứng dụng Spring Boot 2/Spring Framework 5 cũ, namespace thường là javax.validation.constraints; không trộn annotation javax với provider Jakarta trong cùng một cấu hình.

## 2. @NotNull — không chấp nhận giá trị null

### 2.1. Ý nghĩa

@NotNull yêu cầu giá trị thuộc tính không được là null.

```java
public class CreateOrderRequest {

    @NotNull
    private Long customerId;
}
```

Đối với riêng @NotNull:

| Giá trị | Kết quả |
| --- | --- |
| null | Không hợp lệ |
| 0L | Hợp lệ đối với riêng @NotNull |
| 15L | Hợp lệ |

@NotNull không kiểm tra số dương, số âm, khoảng giá trị hoặc sự tồn tại của customer trong database. Nếu ID phải dương, có thể bổ sung @Positive. Nếu ID phải tham chiếu đến bản ghi tồn tại, cần kiểm tra nghiệp vụ/service hoặc custom constraint.

### 2.2. Khi nào dùng?

Dùng @NotNull cho kiểu dữ liệu không phải chuỗi như:

- Long customerId
- LocalDate deliveryDate
- BigDecimal amount
- Address address

Đối với chuỗi, @NotNull vẫn cho phép chuỗi rỗng và chuỗi chỉ có khoảng trắng. Nếu muốn văn bản không rỗng và không chỉ có whitespace, dùng @NotBlank.

### 2.3. Kết hợp với constraint khác

```java
public class CreateOrderRequest {

    @NotNull
    @Positive
    private Long customerId;
}
```

Ở đây @NotNull từ chối null; @Positive yêu cầu giá trị lớn hơn 0. Hai annotation bổ sung cho nhau. @Positive thường coi null là hợp lệ để có thể kết hợp với @NotNull khi cần bắt buộc giá trị; hãy xem định nghĩa constraint của provider/API đang dùng.

## 3. @NotBlank — chuỗi không được rỗng hoặc chỉ có whitespace

### 3.1. Ý nghĩa

@NotBlank áp dụng cho chuỗi. Giá trị phải không null và chứa ít nhất một ký tự không phải whitespace theo quy tắc của Bean Validation/provider.

```java
public class CreateUserRequest {

    @NotBlank
    private String displayName;
}
```

Đối với riêng @NotBlank:

| Giá trị | Kết quả |
| --- | --- |
| null | Không hợp lệ |
| "" | Không hợp lệ |
| "   " | Không hợp lệ |
| "An" | Hợp lệ |
| " An " | Hợp lệ; annotation không tự trim chuỗi |

@NotBlank không chuẩn hóa dữ liệu. Nếu API muốn xóa khoảng trắng đầu/cuối, hãy thực hiện rõ trong quá trình xử lý hoặc dùng cơ chế chuẩn hóa phù hợp. Đừng ghi tài liệu rằng giá trị tự được trim chỉ vì DTO có @NotBlank.

### 3.2. Phân biệt @NotBlank, @NotEmpty và @NotNull

| Annotation | null | Chuỗi rỗng | Chuỗi chỉ whitespace |
| --- | --- | --- | --- |
| @NotNull | Không hợp lệ | Hợp lệ | Hợp lệ |
| @NotEmpty | Không hợp lệ | Không hợp lệ | Hợp lệ |
| @NotBlank | Không hợp lệ | Không hợp lệ | Không hợp lệ |

Chọn theo yêu cầu:

- Dữ liệu chỉ cần khác null: @NotNull.
- Chuỗi/collection phải có phần tử: @NotEmpty.
- Chuỗi phải có nội dung thực, không chỉ khoảng trắng: @NotBlank.

@NotBlank dành cho CharSequence, không phải constraint tổng quát cho List, Map hoặc số. Dùng @NotEmpty hoặc @NotNull cho các kiểu phù hợp.

## 4. @Size — giới hạn độ dài hoặc số lượng phần tử

### 4.1. Ý nghĩa

@Size yêu cầu kích thước nằm trong khoảng min/max. Ví dụ:

```java
public class CreateProductRequest {

    @Size(min = 2, max = 80)
    private String name;
}
```

Giá trị min/max bao gồm hai đầu:

| Độ dài | Kết quả với @Size(min=2,max=80) |
| --- | --- |
| 0 | Không hợp lệ |
| 1 | Không hợp lệ |
| 2 | Hợp lệ |
| 80 | Hợp lệ |
| 81 | Không hợp lệ |

Với String, @Size kiểm tra độ dài chuỗi theo cách provider Bean Validation định nghĩa. Với Collection, Map và mảng, nó kiểm tra số phần tử hoặc entry.

### 4.2. @Size không làm giá trị trở thành bắt buộc

Đây là điểm thường gây nhầm:

```java
@Size(min = 2, max = 80)
private String nickname;
```

Bean Validation constraint @Size chấp nhận null để có thể kết hợp với constraint khác. Nếu nickname là bắt buộc, cần thêm:

```java
@NotBlank
@Size(min = 2, max = 80)
private String nickname;
```

Nếu field là tùy chọn nhưng khi được cung cấp phải có độ dài hợp lệ, chỉ @Size có thể đúng ý định.

### 4.3. Giới hạn cho collection và map

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 20)
    private List<@NotNull Long> productIds;
}
```

Trong ví dụ, @NotEmpty yêu cầu list không null và có ít nhất một phần tử; @Size(max=20) giới hạn tối đa 20 phần tử; @NotNull trên phần tử yêu cầu mỗi ID không null, nếu provider và cấu hình hỗ trợ type-use/container element validation.

Nếu chỉ đặt @Size trên list, nó không tự bảo đảm từng phần tử hợp lệ.

### 4.4. Độ dài chuỗi không đồng nghĩa số byte

@Size trên chuỗi không diễn đạt giới hạn byte UTF-8 của payload. Một ký tự Unicode có thể chiếm nhiều byte khi mã hóa. Nếu API có giới hạn theo byte hoặc kích thước HTTP body, cần mô tả và kiểm tra riêng ở tầng phù hợp.

## 5. @Pattern — kiểm tra chuỗi theo regular expression

### 5.1. Ý nghĩa

@Pattern yêu cầu chuỗi phù hợp regular expression:

```java
public class CreateProductRequest {

    @Pattern(regexp = "^[A-Z]{3}-[0-9]{4}$")
    private String productCode;
}
```

Ví dụ chuỗi hợp lệ: ABC-1234, XYZ-0007.

Ví dụ không hợp lệ: abc-1234 (chữ thường), AB-1234 (thiếu chữ), ABC-123 (thiếu số), ABC-12345 (thừa số), ABC-1234-extra (có hậu tố).

### 5.2. Pattern không tự yêu cầu giá trị bắt buộc

Tương tự nhiều constraint kiểm tra định dạng, @Pattern chấp nhận null. Nếu field cần bắt buộc:

```java
@NotBlank
@Pattern(regexp = "^[A-Z]{3}-[0-9]{4}$")
private String productCode;
```

Nếu field tùy chọn, @Pattern đơn lẻ cho phép null; chuỗi rỗng không khớp biểu thức trên nên vẫn không hợp lệ. Hãy xác định rõ API coi chuỗi rỗng là không gửi, giá trị rỗng hay dữ liệu sai.

### 5.3. Regular expression theo Java

@Pattern dùng cú pháp regular expression của Java (java.util.regex.Pattern), không mặc nhiên là cú pháp JavaScript, PCRE hay một công cụ khác.

| Cú pháp | Ý nghĩa |
| --- | --- |
| ^ | Đầu chuỗi |
| $ | Cuối chuỗi |
| [A-Z] | Một chữ cái in hoa ASCII |
| [0-9] | Một chữ số |
| {3} | Lặp đúng ba lần |
| {2,8} | Lặp từ hai đến tám lần |
| + | Một hoặc nhiều lần |
| ? | Không có hoặc một lần |
| \\d trong Java string | Nhóm chữ số theo regex |

Trong Java source code, dấu gạch chéo ngược của regex cần được escape theo quy tắc string literal. Ví dụ, regex dùng nhóm chữ số viết:

```java
@Pattern(regexp = "\\d{4}")
private String year;
```

### 5.4. Cẩn trọng với regex quá phức tạp

Regex dài và nhiều nhánh có thể khó hiểu, khó bảo trì hoặc có chi phí xử lý lớn với đầu vào bất lợi. Nên:

- Đặt tên hằng hoặc dùng annotation tùy chỉnh khi biểu thức dài.
- Viết test cho cả mẫu đúng và sai.
- Tránh regex có backtracking nguy hiểm trên chuỗi rất dài.
- Giải thích quy tắc bằng câu chữ trong API docs; không yêu cầu người dùng tự giải mã regex.

## 6. @Email — kiểm tra định dạng địa chỉ email

### 6.1. Ý nghĩa

@Email kiểm tra một chuỗi có định dạng email hợp lệ theo implementation Bean Validation đang dùng:

```java
public class CreateUserRequest {

    @NotBlank
    @Email
    private String email;
}
```

Ví dụ thông dụng:

| Giá trị | Kỳ vọng thường gặp |
| --- | --- |
| an@example.com | Hợp lệ |
| user.name+tag@example.org | Thường hợp lệ |
| user@ | Không hợp lệ |
| @example.com | Không hợp lệ |
| not-an-email | Không hợp lệ |

### 6.2. @Email không xác minh email có tồn tại

@Email chỉ kiểm tra định dạng theo validator. Nó không gửi email, xác minh domain có mailbox thực, chứng minh người dùng sở hữu địa chỉ hoặc kiểm tra địa chỉ có được phép dùng trong hệ thống hay không. Nếu cần xác minh quyền sở hữu, ứng dụng thường gửi link hoặc mã xác nhận và kiểm tra quy trình đó riêng.

### 6.3. @Email và @NotBlank

Trong Bean Validation, @Email chấp nhận null để có thể phối hợp với constraint bắt buộc. Nếu email là field required, kết hợp:

```java
@NotBlank
@Email
private String email;
```

Nếu email tùy chọn, có thể chỉ dùng @Email; hãy xác định rõ chính sách với chuỗi rỗng. Chuỗi rỗng khác null và thường không được coi là email hợp lệ.

### 6.4. Không có một regex email đơn giản bao phủ mọi trường hợp

Định dạng email có nhiều quy tắc và khác biệt giữa validator. Không nên kết luận @Email chỉ chấp nhận một regex đơn giản hoặc chắc chắn hỗ trợ mọi dạng địa chỉ theo mọi chuẩn. Nếu API áp dụng chính sách riêng, hãy cấu hình validator hoặc viết custom constraint, sau đó mô tả chính sách chính xác trong tài liệu.

## 7. Kết hợp các annotation cho một DTO

Ví dụ DTO tạo tài khoản:

```java
package com.example.users;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class CreateUserRequest {

    @NotBlank
    @Size(min = 2, max = 80)
    private String displayName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @NotBlank
    @Size(min = 12, max = 72)
    private String password;

    @NotNull
    private Long tenantId;

    @NotBlank
    @Pattern(regexp = "^[A-Z]{2}-[0-9]{6}$")
    private String invitationCode;

    // Getter/setter hoặc record accessors
}
```

Giải thích:

| Field | Quy tắc | Ý nghĩa cần ghi trong tài liệu |
| --- | --- | --- |
| displayName | NotBlank + Size | Bắt buộc, dài 2–80 ký tự |
| email | NotBlank + Email + Size | Bắt buộc, định dạng email và tối đa 254 ký tự |
| password | NotBlank + Size | Bắt buộc, 12–72 ký tự |
| tenantId | NotNull | Không được thiếu giá trị |
| invitationCode | NotBlank + Pattern | Bắt buộc, hai chữ hoa, dấu gạch ngang và sáu chữ số |

Các giới hạn trong ví dụ là **chính sách minh họa của một API**, không phải giới hạn phổ quát bắt buộc bởi Bean Validation. Hãy chọn min/max và regex theo yêu cầu thật của hệ thống.

## 8. Bean Validation có thực sự chạy khi nhận request không?

Khai báo annotation trên DTO mới chỉ tạo metadata constraint. Để Spring MVC kích hoạt validation cho request body, controller thường dùng @Valid hoặc @Validated phù hợp:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateUserRequest request) {
        // Lưu người dùng
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Ứng dụng cũng cần Bean Validation implementation trên classpath, ví dụ starter validation phù hợp với phiên bản Spring Boot.

Nếu thiếu @Valid hoặc validation không được kích hoạt, request có thể đi vào controller dù DTO chứa annotation. REST Docs có thể vẫn đọc metadata để tạo mô tả constraint; việc đó không chứng minh endpoint thực sự từ chối dữ liệu sai.

### 8.1. Phân biệt ba bước

| Bước | Thành phần | Mục đích |
| --- | --- | --- |
| Khai báo annotation | DTO/model | Mô tả quy tắc validation |
| Thực thi validation | Bean Validation + Spring MVC/WebFlux | Kiểm tra object khi request đi vào |
| Đưa mô tả vào tài liệu | REST Docs ConstraintDescriptions + field descriptor | Giải thích quy tắc cho người dùng API |

Ba bước liên quan nhưng không thay thế nhau.

## 9. Dùng ConstraintDescriptions để ghi constraint vào REST Docs

Spring REST Docs có thể tìm constraint của thuộc tính và chuyển chúng thành câu mô tả.

### 9.1. Tạo ConstraintDescriptions

```java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateUserRequest.class);

List<String> emailRules =
        constraints.descriptionsForProperty("email");
```

emailRules chứa các mô tả cho constraint tìm thấy trên thuộc tính email, chẳng hạn @NotBlank, @Email và @Size. Mô tả mặc định có thể được điều chỉnh bằng resource bundle.

### 9.2. Ghép vào request field descriptor

Ví dụ với MockMvc:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

List<String> emailRules =
        new ConstraintDescriptions(CreateUserRequest.class)
                .descriptionsForProperty("email");

this.mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "displayName": "An Nguyen",
                          "email": "an@example.com",
                          "password": "StrongPass123",
                          "tenantId": 10,
                          "invitationCode": "AB-123456"
                        }
                        """))
        .andExpect(status().isCreated())
        .andDo(document("users-create",
                requestFields(
                        fieldWithPath("displayName")
                                .description("Tên hiển thị."),
                        fieldWithPath("email")
                                .description("Địa chỉ email. " +
                                        String.join(" ", emailRules)),
                        fieldWithPath("password")
                                .description("Mật khẩu người dùng."),
                        fieldWithPath("tenantId")
                                .description("Mã tenant."),
                        fieldWithPath("invitationCode")
                                .description("Mã mời.")
                )));
```

Ví dụ minh họa cách ghép mô tả vào descriptor; import và setup MockMvc, controller, validation provider và response assertion cần có trong test class thực tế. Nên tạo ConstraintDescriptions một lần cho DTO và tái sử dụng.

### 9.3. Dịch mô tả sang tiếng Việt

Các mô tả constraint mặc định thường bằng tiếng Anh. Có thể cung cấp resource bundle để thay thế:

```properties
jakarta.validation.constraints.NotNull.description=Không được để giá trị null.
jakarta.validation.constraints.NotBlank.description=Không được rỗng hoặc chỉ chứa khoảng trắng.
jakarta.validation.constraints.Size.description=Độ dài hoặc số lượng phần tử phải nằm trong giới hạn cho phép.
jakarta.validation.constraints.Pattern.description=Giá trị phải khớp định dạng được quy định.
jakarta.validation.constraints.Email.description=Phải có định dạng địa chỉ email hợp lệ.
```

Resource bundle phải nằm trên classpath test/tác vụ biên soạn và theo base name Spring REST Docs quy định. Tên key phải khớp fully qualified class name của annotation constraint cộng hậu tố .description. Nếu dự án có constraint tùy chỉnh, thêm key tương ứng hoặc dùng ConstraintDescriptionResolver riêng.

## 10. Kiểm thử từng constraint

Nên kiểm thử các ranh giới, không chỉ một ví dụ hợp lệ:

| Constraint | Ca hợp lệ | Ca không hợp lệ nên kiểm tra |
| --- | --- | --- |
| @NotNull | Một giá trị khác null | null |
| @NotBlank | "An" | null, "", "   " |
| @Size(min=2,max=4) | Độ dài 2 và 4 | Độ dài 1 và 5 |
| @Pattern(regexp="^[A-Z]{2}[0-9]{3}$") | AB123 | ab123, A123, AB1234 |
| @Email | user@example.com | user@, @example.com, text không phải email |

Có thể kiểm tra trực tiếp qua Validator:

```java
Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();

Set<ConstraintViolation<CreateUserRequest>> violations =
        validator.validate(request);

assertThat(violations).isEmpty();
```

Trong test thực tế, nên quản lý vòng đời ValidatorFactory hoặc dùng Validator bean do Spring cung cấp. Với request HTTP, hãy kiểm thử cả response lỗi và response thành công để tài liệu hóa hành vi endpoint.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| @NotNull làm chuỗi không được rỗng | Nó chỉ từ chối null; dùng @NotBlank hoặc @NotEmpty theo ý định |
| @Size tự bắt buộc field | @Size chấp nhận null; kết hợp @NotNull/@NotBlank nếu cần |
| @Pattern tự bắt buộc field | @Pattern chấp nhận null; thêm constraint bắt buộc khi cần |
| @Email xác minh hộp thư tồn tại | Nó chỉ kiểm tra định dạng theo validator |
| @NotBlank tự trim chuỗi | Nó không sửa giá trị đầu vào |
| @Size trên String là giới hạn byte HTTP | Nó không mô tả giới hạn byte payload |
| Có annotation thì Spring chắc chắn validate request | Cần kích hoạt validation ở controller và có provider |
| ConstraintDescriptions thực thi validation | Nó đọc metadata để tạo mô tả |
| REST Docs tự tạo toàn bộ tài liệu constraint | Ứng dụng phải đưa mô tả vào descriptor/template |

## 12. Lưu ý về namespace và phiên bản

- Spring Boot 3/4 sử dụng Jakarta Validation và package jakarta.validation.*.
- Spring Boot 2/Spring Framework 5 dùng hệ Java EE cũ với package javax.validation.*.
- Không trộn API javax.validation với provider Jakarta Validation trong cùng ứng dụng.
- Kiểm tra phiên bản Bean Validation API/provider và JDK; annotation trong source phải đến từ đúng API được resolve.
- Với annotation hoặc constraint tùy chỉnh, xác minh resolver REST Docs nhận được metadata và resource bundle có mô tả tương ứng.

## 13. Bài thực hành

1. Tạo DTO CreateUserRequest có displayName, email, password, tenantId và invitationCode theo phần 7.
2. Viết test Validator kiểm tra trường hợp hợp lệ và không hợp lệ cho năm annotation.
3. Kích hoạt validation trên controller bằng @Valid và xác minh response lỗi theo exception handling của ứng dụng.
4. Dùng ConstraintDescriptions lấy mô tả cho từng property.
5. Tạo resource bundle tiếng Việt và xác nhận mô tả trong request-fields snippet đã được dịch.
6. Thử bỏ @NotBlank khỏi email nhưng giữ @Email; kiểm tra chuỗi null/rỗng và giải thích vì sao annotation định dạng không tự bắt buộc field.
7. Thử đổi max của @Size và quan sát mô tả constraint cùng test boundary thay đổi thế nào.

**Câu hỏi tự đánh giá**

1. @NotNull khác @NotBlank như thế nào?
2. Vì sao @Size không đủ để làm một field trở thành bắt buộc?
3. @Pattern dùng loại regular expression nào?
4. @Email có thể xác minh địa chỉ tồn tại hay không?
5. Khi nào cần kết hợp @NotBlank với @Email?
6. @Size trên String có tương đương giới hạn số byte UTF-8 không?
7. Vì sao annotation constraint không tự chứng minh endpoint đang validate request?
8. ConstraintDescriptions đóng vai trò gì trong quá trình tạo snippet REST Docs?

## Tài liệu tham khảo chính thức

- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): định nghĩa constraint built-in, Validator và metadata.
- [Jakarta Validation API — NotNull](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/notnull): ý nghĩa @NotNull.
- [Jakarta Validation API — NotBlank](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/notblank): điều kiện chuỗi không blank.
- [Jakarta Validation API — Size](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/size): giới hạn kích thước và kiểu được hỗ trợ.
- [Jakarta Validation API — Pattern](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/pattern): regular expression và flags.
- [Jakarta Validation API — Email](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/email): constraint định dạng email.
- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): ConstraintDescriptions, resolver và cách dùng mô tả constraint trong tài liệu.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Bean Validation với Spring.

**Kết luận thực hành:** Chọn constraint theo đúng ý nghĩa dữ liệu: @NotNull kiểm tra null, @NotBlank kiểm tra nội dung chuỗi, @Size kiểm soát độ dài/số lượng, @Pattern kiểm tra định dạng bằng regex và @Email kiểm tra hình thức email. Kích hoạt validation thực sự ở ứng dụng, kiểm thử các trường hợp biên, rồi dùng ConstraintDescriptions để đưa mô tả đã được kiểm chứng vào request-field snippet của Spring REST Docs.
