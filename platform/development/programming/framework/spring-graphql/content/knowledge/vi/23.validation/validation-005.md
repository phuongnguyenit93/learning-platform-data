# Validation trên @Argument

Trong Spring for GraphQL, argument của GraphQL operation được kiểm tra qua nhiều lớp. GraphQL kiểm tra cú pháp, schema và kiểu dữ liệu; Spring bind giá trị vào tham số Java; Bean Validation kiểm tra các quy tắc trên object đầu vào; service/domain tiếp tục kiểm tra các điều kiện phụ thuộc dữ liệu, trạng thái và quyền truy cập.

Với annotated controller, annotation **@Argument** nhận argument của field. Khi argument là input object, có thể kết hợp **@Valid** với Jakarta Bean Validation để kiểm tra DTO trước khi resolver chạy nghiệp vụ. Bài học này trình bày cách cấu hình validator, khai báo constraint, validate nested object và collection, chọn validation group, xử lý lỗi và kiểm thử bằng GraphQlTester.

## 1. Các lớp kiểm tra đầu vào

Một GraphQL request đi qua các giai đoạn sau:

1. **Parse:** parser đọc GraphQL document. Sai cú pháp sẽ bị từ chối.
2. **Validate document:** GraphQL kiểm tra field, argument và selection set có tồn tại trong schema hay không.
3. **Input coercion:** GraphQL kiểm tra scalar, enum, list, nullability và cấu trúc input object theo SDL.
4. **Argument binding:** Spring chuyển giá trị đã coercion thành kiểu Java mà resolver yêu cầu.
5. **Bean Validation:** Jakarta Validation kiểm tra các constraint trên object Java.
6. **Business validation:** service/domain kiểm tra dữ liệu hiện có, trạng thái, hạn mức và quyền.

Ví dụ SDL:

~~~graphql
input RegisterCustomerInput {
    displayName: String!
    email: String!
    age: Int!
    address: AddressInput!
    tags: [String!]
}

input AddressInput {
    city: String!
    postalCode: String
}

type Customer {
    id: ID!
    displayName: String!
    email: String!
}

type Mutation {
    registerCustomer(input: RegisterCustomerInput!): Customer!
}
~~~

SDL bảo đảm các field non-null có giá trị và giá trị có kiểu phù hợp. Tuy nhiên, SDL không thể diễn đạt mọi quy tắc, chẳng hạn email phải đúng định dạng, displayName phải dài ít nhất hai ký tự hoặc age phải từ 18 trở lên. Các quy tắc này phù hợp với Bean Validation.

| Lớp | Ví dụ | Thành phần xử lý |
| --- | --- | --- |
| GraphQL schema/coercion | Thiếu input non-null hoặc enum không hợp lệ | GraphQL engine |
| Java binding | Không tạo được DTO hoặc không chuyển được kiểu | GraphQlArgumentBinder |
| Bean Validation | Email sai định dạng hoặc tên chỉ có khoảng trắng | Jakarta Bean Validation |
| Business validation | Email đã tồn tại trong database | Service/domain |

Sơ đồ luồng:

~~~mermaid
flowchart TD
    A["GraphQL request"] --> B["Parse và validate document"]
    B --> C["Coerce argument theo SDL"]
    C --> D["Bind argument vào Java DTO"]
    D --> E["Bean Validation"]
    E --> F{"Constraint hợp lệ?"}
    F -->|Có| G["Gọi annotated controller"]
    F -->|Không| H["ConstraintViolationException"]
    H --> I["GraphQL exception handling"]
    I --> J["Response có errors"]
    G --> K["Service và business rules"]
~~~

Phân biệt các giai đoạn giúp chọn đúng cách sửa. Bean Validation không thể sửa operation sai cú pháp hoặc field không tồn tại trong SDL.

## 2. Thêm dependency và cấu hình Validator

Với Spring Boot, thêm starter validation để có Jakarta Validation API và implementation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Spring Boot thường tự cấu hình Validator khi dependency có mặt. AnnotatedControllerConfigurer sử dụng Validator bean để kiểm tra các tham số được đánh dấu @Valid hoặc @Validated.

Nếu ứng dụng không dùng auto-configuration, có thể khai báo LocalValidatorFactoryBean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration(proxyBeanMethods = false)
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Ứng dụng Spring Boot 3 trở lên dùng namespace jakarta.validation. Không trộn các import javax.validation của hệ sinh thái cũ với jakarta.validation trong cùng cấu hình.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

Chỉ đặt annotation @Valid trong source code chưa đủ nếu application context không có validation provider hoặc Validator bean. Khi validation không chạy, hãy kiểm tra dependency và cấu hình trước.

## 3. Khai báo constraint trên input DTO

Input object GraphQL thường được ánh xạ vào Java record hoặc class. Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

public record AddressInput(
        @NotBlank
        @Size(max = 80)
        String city,

        @Pattern(
                regexp = "[0-9A-Za-z -]{3,12}",
                message = "Postal code không đúng định dạng"
        )
        String postalCode
) {
}

public record RegisterCustomerInput(
        @NotBlank
        @Size(min = 2, max = 80)
        String displayName,

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
        AddressInput address,

        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags
) {
}
~~~

Các constraint chính:

| Constraint | Ý nghĩa |
| --- | --- |
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không được null, rỗng hoặc chỉ chứa whitespace |
| @NotEmpty | Chuỗi, collection, map hoặc array không được rỗng |
| @Size | Giới hạn độ dài chuỗi hoặc kích thước collection |
| @Email | Kiểm tra định dạng email cơ bản |
| @Min, @Max | Giới hạn giá trị số |
| @Pattern | Kiểm tra chuỗi theo regular expression |
| @Valid | Kích hoạt cascade validation trên object lồng nhau |

Với record, constraint đặt trên record component được Jakarta Bean Validation kiểm tra qua các thành phần tương ứng. Với class thông thường, có thể đặt constraint trên field hoặc getter theo access strategy của Bean Validation.

Không dùng primitive cho input field có thể bị bỏ qua hoặc nhận null. Integer có thể biểu diễn giá trị chưa được cung cấp; int thì không.

## 4. Kích hoạt validation bằng @Valid trên @Argument

Đặt @Valid trên tham số @Argument để yêu cầu Spring for GraphQL validate object đã bind trước khi gọi method:

~~~java
import jakarta.validation.Valid;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CustomerMutationController {

    private final CustomerService customerService;

    public CustomerMutationController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @MutationMapping
    public Customer registerCustomer(
            @Argument("input") @Valid RegisterCustomerInput input) {
        return customerService.register(input);
    }
}
~~~

Khi argument input được bind thành RegisterCustomerInput, Bean Validation kiểm tra các constraint trước khi method controller thực thi. Nếu có constraint không thỏa mãn, Spring for GraphQL phát sinh ConstraintViolationException. Resolver và service không được gọi.

Ví dụ client gửi input có email sai, age dưới 18 và city chỉ chứa khoảng trắng. Request vẫn có thể hợp lệ theo cấu trúc SDL, nhưng Bean Validation sẽ từ chối nội dung.

## 5. Phân biệt @Valid và @Validated

Hai annotation có liên quan nhưng mục đích khác nhau:

| Annotation | Vai trò |
| --- | --- |
| jakarta.validation.Valid | Kích hoạt cascade validation theo group mặc định |
| org.springframework.validation.annotation.Validated | Cho phép chọn validation group hoặc group sequence; cũng được dùng trong method validation |

Với input object đơn giản, dùng @Valid:

~~~java
@MutationMapping
public Customer registerCustomer(
        @Argument("input") @Valid RegisterCustomerInput input) {
    return customerService.register(input);
}
~~~

Khi cần chọn group, có thể dùng @Validated trên tham số argument theo cơ chế validation của Spring for GraphQL:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") @Validated(OnCreate.class) CustomerInput input) {
    return customerService.create(input);
}
~~~

Validation group được trình bày ở phần sau. Hãy kiểm tra cách kích hoạt tương ứng với phiên bản Spring for GraphQL đang sử dụng.

Nếu đặt constraint trực tiếp trên scalar parameter của resolver, ví dụ @Min trên argument kiểu Integer, đó là method parameter validation. Cách kích hoạt phụ thuộc phiên bản Spring Framework và cấu hình ứng dụng. Trong mô hình Spring AOP truyền thống, controller/bean thường được đánh dấu @Validated; các phiên bản Spring Framework mới hơn có cơ chế method validation tích hợp. Tránh kích hoạt đồng thời nhiều cơ chế khiến cùng constraint bị chạy lặp.

## 6. Validation cho nested object và collection

@Valid trên input object ngoài cùng không tự động cascade vào mọi object con. Đánh dấu @Valid trên thuộc tính lồng nhau cần kiểm tra:

~~~java
public record AuthorInput(
        @NotBlank String name,
        @Email String email
) {
}

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Valid AuthorInput author
) {
}
~~~

@NotNull và @Valid có vai trò riêng: @NotNull yêu cầu object con tồn tại; @Valid yêu cầu kiểm tra constraint bên trong object con.

Với collection chứa input object:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record OrderLineInput(
        @NotBlank String productCode,
        @Min(1) @Max(100) Integer quantity
) {
}

public record CreateOrderInput(
        @NotEmpty
        @Size(max = 50)
        List<@NotNull @Valid OrderLineInput> lines
) {
}
~~~

Với collection chứa scalar, có thể dùng container element constraints:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        List<@NotBlank @Size(max = 30) String> tags
) {
}
~~~

Phân biệt:

- @Size trên list kiểm tra số lượng phần tử.
- Constraint trên List<@NotBlank String> kiểm tra từng chuỗi.
- @Valid trên phần tử object kích hoạt kiểm tra các thuộc tính bên trong.
- GraphQL list type và nullability vẫn được kiểm tra trước ở giai đoạn input coercion.

## 7. Chọn constraint theo ý nghĩa dữ liệu

Một số constraint dựng sẵn thường dùng:

| Constraint | Dùng cho | Lưu ý |
| --- | --- | --- |
| @NotNull | Giá trị bắt buộc | Chỉ kiểm tra null |
| @NotBlank | Chuỗi bắt buộc có ký tự khác whitespace | Không áp dụng cho số hoặc collection |
| @NotEmpty | Chuỗi, collection, map hoặc array không rỗng | Không kiểm tra nội dung từng phần tử |
| @Size | Độ dài chuỗi hoặc kích thước collection | Null thường hợp lệ; kết hợp @NotNull nếu bắt buộc |
| @Min, @Max | Giới hạn số nguyên | Null thường hợp lệ; kết hợp @NotNull nếu bắt buộc |
| @DecimalMin, @DecimalMax | Giới hạn số thập phân | Hữu ích với BigDecimal |
| @Positive, @PositiveOrZero | Số dương hoặc không âm | Kết hợp @NotNull nếu không cho phép null |
| @Email | Định dạng email | Không xác nhận hộp thư tồn tại |
| @Pattern | Chuỗi theo regular expression | Regex cần được kiểm thử |
| @Past, @Future | Ngày/thời điểm so với hiện tại | Chọn kiểu ngày giờ và clock phù hợp |

Ví dụ:

~~~java
public record RegisterAuthorInput(
        @NotBlank
        @Size(max = 120)
        String fullName,

        @NotBlank
        @Email
        String email,

        @NotNull
        @Min(18)
        @Max(120)
        Integer age
) {
}
~~~

Một thuộc tính có thể cần nhiều constraint đồng thời:

~~~java
public record CreateBookInput(
        @NotBlank(message = "ISBN không được để trống")
        @Size(min = 10, max = 17, message = "Độ dài ISBN không hợp lệ")
        @Pattern(
                regexp = "[0-9Xx-]+",
                message = "ISBN chỉ được chứa chữ số, X hoặc dấu gạch nối"
        )
        String isbn
) {
}
~~~

Định dạng trên chỉ minh họa cách kết hợp constraint, chưa thay thế thuật toán kiểm tra ISBN-10/ISBN-13 và checksum. Nếu cần xác thực ISBN thực sự, hãy viết validator chuyên biệt hoặc dùng thư viện domain phù hợp.

Lưu ý về null:

- @NotBlank từ chối null, chuỗi rỗng và chuỗi chỉ có whitespace.
- @Email thường chấp nhận null; kết hợp @NotBlank nếu email bắt buộc.
- @Size thường chấp nhận null; kết hợp @NotNull nếu field bắt buộc.
- @Min và @Max thường chấp nhận null; kết hợp @NotNull nếu không cho phép bỏ trống.

SDL và Bean Validation có thể bổ sung cho nhau. Ví dụ String! bảo đảm giá trị không null ở lớp GraphQL, còn @NotBlank còn từ chối chuỗi rỗng hoặc chỉ có khoảng trắng ở lớp Java.

## 8. Dùng @Validated cho validation groups

Một input có thể được dùng trong nhiều operation nhưng yêu cầu khác nhau. Ví dụ khi tạo khách hàng phải có email; khi cập nhật một phần, email có thể được bỏ qua.

Khai báo group:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

Gắn group vào constraint:

~~~java
public record CustomerProfileInput(
        @NotBlank(groups = {OnCreate.class, OnUpdate.class})
        @Size(max = 80, groups = {OnCreate.class, OnUpdate.class})
        String displayName,

        @NotBlank(groups = OnCreate.class)
        @Email(groups = {OnCreate.class, OnUpdate.class})
        String email
) {
}
~~~

Chọn group ở tham số argument:

~~~java
import org.springframework.validation.annotation.Validated;

@MutationMapping
public Customer createCustomer(
        @Argument("input") @Validated(OnCreate.class) CustomerProfileInput input) {
    return customerService.create(input);
}

@MutationMapping
public Customer updateCustomer(
        @Argument("input") @Validated(OnUpdate.class) CustomerProfileInput input) {
    return customerService.update(input);
}
~~~

@Valid dùng validation group mặc định. Spring @Validated cho phép chỉ định group hoặc group sequence. Một constraint chỉ gắn OnCreate sẽ không tự chạy khi method chọn OnUpdate.

Ví dụ trên minh họa group theo từng argument. Hãy kiểm tra validation hints được hỗ trợ trong phiên bản Spring for GraphQL đang dùng. Nếu group ở vị trí tham số không phù hợp với cấu hình hiện tại, có thể tách DTO cho create/update hoặc gọi Validator.validate(input, OnCreate.class) tại application service.

Không dùng group để thay thế DTO riêng khi create và update có cấu trúc đầu vào rất khác nhau. DTO riêng thường dễ hiểu hơn khi quy tắc phát triển phức tạp.

## 9. Cross-field validation

Một số quy tắc cần so sánh nhiều thuộc tính. Ví dụ ngày kết thúc phải sau ngày bắt đầu.

Định nghĩa annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Documented
@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "endDate phải sau startDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, DateRangeInput> {

    @Override
    public boolean isValid(
            DateRangeInput value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return value.endDate().isAfter(value.startDate());
    }
}
~~~

Input record:

~~~java
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidDateRange
public record DateRangeInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {
}
~~~

Validator class-level chỉ kiểm tra quan hệ giữa hai ngày khi cả hai đã có giá trị. @NotNull chịu trách nhiệm bắt buộc từng ngày. Có thể tùy chỉnh ConstraintValidatorContext để gắn violation vào field endDate thay vì toàn object, giúp client hiển thị lỗi đúng input control.

## 10. Omitted, explicit null và partial update

Với mutation cập nhật, field bị bỏ qua và field được gửi explicit null có thể mang hai ý nghĩa khác nhau:

- Omitted: client không yêu cầu thay đổi thuộc tính.
- Explicit null: client muốn xóa giá trị nếu nghiệp vụ cho phép.
- Có giá trị: client muốn đặt giá trị mới.

Nếu DTO chỉ dùng nullable field thông thường, omitted và explicit null có thể cùng trở thành null sau binding. Khi cần phân biệt, Spring for GraphQL cung cấp ArgumentValue<T>:

~~~java
public record UpdateBookInput(
        ArgumentValue<String> description,
        ArgumentValue<Integer> pageCount
) {
}
~~~

Service kiểm tra isOmitted() để giữ nguyên thuộc tính khi client không gửi field. Nếu field được gửi explicit null, kiểm tra value() để áp dụng chính sách xóa hoặc từ chối.

Bean Validation cần phù hợp với semantics của update:

- @NotBlank trên field bắt buộc của create có thể không phù hợp với field update được phép omitted.
- @Size thường cho phép null, vì vậy có thể kiểm tra giá trị khi client thực sự gửi.
- Nếu cần kiểm tra giá trị chỉ khi present, có thể xử lý ở application service hoặc dùng validator hỗ trợ semantics đó.
- Không tự biến omitted thành giá trị mặc định trước khi biết nghiệp vụ muốn giữ nguyên hay thay đổi.

Với partial update phức tạp, DTO riêng và validation theo từng trạng thái thường dễ bảo trì hơn một DTO dùng chung cho mọi mutation.

## 11. Phân biệt ConstraintViolationException, BindException và GraphQL request error

Các lỗi đầu vào có thể phát sinh ở những giai đoạn khác nhau:

| Loại lỗi | Thời điểm | Ví dụ | Cách xử lý |
| --- | --- | --- | --- |
| GraphQL parse/validation/coercion error | Trước khi resolver chạy | Sai cú pháp, field không tồn tại, thiếu input non-null, enum sai | Sửa operation hoặc SDL |
| BindException | Spring không thể bind argument vào kiểu Java đích | Constructor/property binding hoặc chuyển đổi kiểu thất bại | Sửa DTO, kiểu Java hoặc conversion |
| ConstraintViolationException | Argument đã bind nhưng vi phạm Bean Validation | age = 16 trong khi @Min(18) | Ánh xạ thành GraphQL validation error |
| Business exception | Trong service/domain | Email đã tồn tại hoặc trạng thái không cho phép | Xử lý theo quy tắc nghiệp vụ |

Đừng gộp BindException và ConstraintViolationException thành một lỗi không phân biệt. Hai lỗi chỉ ra hai vấn đề khác nhau: dữ liệu không thể chuyển thành Java object, hoặc object đã tạo được nhưng không thỏa constraint.

## 12. Chuyển validation failure thành GraphQL error

Có thể dùng @GraphQlExceptionHandler trong @ControllerAdvice để chuẩn hóa ConstraintViolationException:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import jakarta.validation.ConstraintViolationException;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.List;
import java.util.Map;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleConstraintViolation(
            ConstraintViolationException exception,
            DataFetchingEnvironment environment) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(violation -> Map.of(
                                "field", violation.getPropertyPath().toString(),
                                "message", violation.getMessage()
                        ))
                        .toList();

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ")
                .extensions(Map.of(
                        "code", "VALIDATION_FAILED",
                        "violations", violations
                ))
                .build();
    }
}
~~~

DataFetchingEnvironment giúp GraphqlErrorBuilder giữ path và source location của field đang thực thi. Property path trong violations mô tả thuộc tính Java vi phạm; GraphQL path chỉ field resolver thất bại. Hai đường dẫn phục vụ hai mục đích khác nhau.

Không đưa invalid value vào response. Giá trị bị từ chối có thể chứa email, số điện thoại, token hoặc dữ liệu nhạy cảm. Thông báo constraint cũng nên được thiết kế cho client và không tiết lộ cấu trúc nội bộ.

Có thể xử lý BindException riêng nếu cần:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class GraphQlBindingAdvice {

@GraphQlExceptionHandler
public GraphQLError handleBindException(
        BindException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.BAD_REQUEST)
            .message("Không thể bind GraphQL argument")
            .extensions(Map.of("code", "ARGUMENT_BINDING_FAILED"))
            .build();
}
}
~~~

Nếu dùng method validation cho scalar parameter, exception có thể khác tùy cơ chế và phiên bản Spring Framework. Hãy xử lý đúng loại exception mà ứng dụng thực tế phát sinh.

## 13. Validation không thay thế business rule và authorization

Bean Validation phù hợp với quy tắc cấu trúc và giới hạn cục bộ của dữ liệu:

- Chuỗi bắt buộc, độ dài và định dạng.
- Giá trị số trong một khoảng.
- Số lượng phần tử của collection.
- Quan hệ đơn giản giữa các thuộc tính.
- Nội dung của từng phần tử trong list.

Một số quy tắc cần service/domain xử lý:

- Email đã được đăng ký bởi khách hàng khác hay chưa.
- Mã sản phẩm có tồn tại và còn được bán hay không.
- Người dùng hiện tại có quyền tạo đơn hàng cho tenant được yêu cầu hay không.
- Số lượng đặt có vượt tồn kho tại thời điểm ghi dữ liệu hay không.
- Trạng thái hiện tại có cho phép chuyển sang trạng thái mới hay không.

Không gọi database hoặc dịch vụ từ constraint validator cho mọi quy tắc nghiệp vụ nếu điều đó làm validation khó dự đoán hoặc tạo race condition. Ví dụ, email có thể chưa tồn tại lúc kiểm tra nhưng được request khác đăng ký trước khi transaction ghi dữ liệu. Quy tắc duy nhất vẫn cần được bảo vệ bằng unique constraint ở database và xử lý conflict trong service.

Validation cũng không phải authorization. Một input có cấu trúc hoàn toàn hợp lệ vẫn có thể yêu cầu hành động mà principal hiện tại không được phép thực hiện.

## 14. GraphQL errors, partial data và null propagation

Khi validation thất bại trong một resolver, GraphQL có thể trả response chứa errors và giá trị null tại field bị lỗi. Các field độc lập khác vẫn có thể trả dữ liệu nếu schema cho phép.

Nếu field được khai báo nullable, lỗi có thể chỉ làm field đó thành null. Nếu field hoặc parent là non-null, null propagation có thể lan lên parent gần nhất cho phép null. Vì vậy, nullability trong SDL là một phần của hợp đồng lỗi.

Client nên dựa vào error code ổn định trong extensions thay vì so sánh nguyên văn message. Ví dụ code VALIDATION_FAILED có thể đi kèm danh sách field path và constraint message an toàn.

## 15. Kiểm thử validation bằng GraphQlTester

Kiểm thử qua GraphQL operation thực tế để xác nhận SDL, argument binding, Bean Validation và exception handling.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(CustomerMutationController.class)
@Import(GraphQlValidationAdvice.class)
class CustomerValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    CustomerService customerService;

    @Test
    void rejectsInvalidEmailBeforeCallingService() {
        GraphQlTester.Response response = graphQlTester.document("""
                mutation {
                    registerCustomer(input: {
                        displayName: "Lan Nguyen"
                        email: "not-an-email"
                        age: 28
                        address: { city: "Da Nang" }
                    }) {
                        id
                        displayName
                    }
                }
                """)
                .execute();

        response.errors().satisfy(errors -> {
            assertThat(errors).isNotEmpty();
            assertThat(errors.get(0).getExtensions())
                    .containsEntry("code", "VALIDATION_FAILED");
        });

        verifyNoInteractions(customerService);
    }
}
~~~

Test cần có Validator bean trong application context. Khi dùng @GraphQlTest, nếu test slice không tự nạp validation configuration, hãy import cấu hình có LocalValidatorFactoryBean hoặc cấu hình test tương ứng. Đảm bảo validation provider có trong test runtime.

Các trường hợp nên kiểm thử:

1. Input hợp lệ được resolver xử lý.
2. Field non-null bị thiếu hoặc nhận null bị GraphQL từ chối trước Bean Validation.
3. Chuỗi rỗng hoặc chỉ có whitespace bị @NotBlank từ chối.
4. Giá trị vượt @Size, @Min hoặc @Max.
5. Nested object được cascade validation.
6. Collection có phần tử không hợp lệ.
7. Cross-field constraint phát hiện quan hệ ngày không hợp lệ.
8. Validation group tạo mới và cập nhật chạy đúng nhóm.
9. Omitted và explicit null giữ đúng semantics của partial update.
10. BindException được phân biệt với ConstraintViolationException.
11. Service không được gọi khi validation thất bại.
12. GraphQL error có code/path đúng và không chứa invalid value.

Có thể kiểm thử validator riêng bằng Jakarta Validator để xác nhận constraint và class-level rule. Tuy nhiên, unit test validator không thay thế test qua GraphQL vì nó không kiểm tra SDL, argument binding hoặc exception mapping.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| @Valid không có tác dụng | Không có Validator bean hoặc validation provider | Thêm starter validation và kiểm tra application context |
| Object ngoài được validate nhưng object con không được validate | Thiếu @Valid trên thuộc tính lồng nhau | Thêm cascade validation ở đúng thuộc tính |
| Chuỗi rỗng vẫn qua @Email | @Email không thay thế kiểm tra presence | Kết hợp @NotBlank với @Email |
| List có quá nhiều phần tử vẫn qua | Chưa giới hạn collection | Dùng @Size(max = ...) trên list |
| Item trong list không được validate | Thiếu container element constraint hoặc @Valid | Dùng List<@NotBlank String> hoặc List<@Valid ItemInput> |
| Client nhận lỗi chung chung | Chưa ánh xạ ConstraintViolationException | Dùng @GraphQlExceptionHandler hoặc DataFetcherExceptionResolver |
| BindException bị nhầm với validation | Lỗi bind và lỗi constraint là hai giai đoạn khác nhau | Phân loại exception và trả error code riêng |
| Validation group không chạy | Constraint không thuộc group được chọn | Kiểm tra groups trên từng constraint và @Validated |
| Constraint validator gọi database gây chậm | Trộn validation cấu trúc với quy tắc nghiệp vụ | Đưa kiểm tra phụ thuộc dữ liệu vào service/domain |
| Response làm lộ dữ liệu nhạy cảm | Trả invalid value hoặc exception message nguyên gốc | Chỉ trả field path, message an toàn và error code |

## 17. Quy trình triển khai validation trên @Argument

Khi thêm validation cho một GraphQL input:

1. Khai báo cấu trúc, scalar và nullability trong SDL.
2. Tạo Java input DTO/record với constraint phù hợp.
3. Thêm Bean Validation provider tương thích với Spring Boot.
4. Bảo đảm application context có Validator bean.
5. Dùng @Valid trên tham số @Argument để kích hoạt object validation.
6. Dùng @Valid ở các thuộc tính lồng nhau và container element constraints cho collection.
7. Dùng @Validated khi cần validation groups hoặc method validation.
8. Phân biệt ConstraintViolationException với BindException và GraphQL request errors.
9. Ánh xạ lỗi thành GraphQL errors có mã ổn định và không tiết lộ invalid value.
10. Để service/domain xử lý các quy tắc phụ thuộc trạng thái dữ liệu và authorization.
11. Kiểm thử valid input, invalid input, nested validation, groups và việc service không được gọi khi validation thất bại.

## 18. Những điểm cần ghi nhớ

- GraphQL SDL kiểm tra cấu trúc và kiểu đầu vào trước khi Bean Validation chạy.
- @Argument bind argument vào tham số Java; @Valid yêu cầu cascade validation cho input object.
- Cần có Bean Validation provider, chẳng hạn spring-boot-starter-validation.
- Dùng @NotBlank, @Size, @Min, @Max và @Email theo ý nghĩa dữ liệu.
- Đánh dấu @Valid trên nested object và phần tử object trong collection để kiểm tra đệ quy.
- @Validated hỗ trợ validation group và method validation theo cơ chế Spring tương ứng.
- Dùng wrapper type cho input field có thể null hoặc bị bỏ qua.
- ConstraintViolationException biểu thị constraint không thỏa mãn; BindException biểu thị lỗi bind argument vào Java target.
- ArgumentValue<T> giúp phân biệt omitted và explicit null khi cập nhật một phần.
- Bean Validation phù hợp với quy tắc trên dữ liệu; business validation phụ thuộc trạng thái phải ở service/domain.
- Dùng GraphQlTester để kiểm tra schema, binding, validation và response errors.

Validation trên @Argument tạo một ranh giới rõ giữa dữ liệu GraphQL và logic ứng dụng. Khi kết hợp SDL, DTO, Bean Validation và business validation đúng vai trò, Spring for GraphQL có thể từ chối input sai sớm, trả lỗi nhất quán và giữ resolver tập trung vào nghiệp vụ.

## Tài liệu tham khảo

- Spring for GraphQL — Annotated Controllers: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Exceptions: https://docs.spring.io/spring-graphql/reference/controllers.html#controllers-exceptions
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/3.0/
- Hibernate Validator Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/

