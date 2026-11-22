# Validation trên input object

GraphQL API thường nhận dữ liệu từ client qua các input object, đặc biệt trong Mutation tạo mới hoặc cập nhật tài nguyên. Schema SDL có thể yêu cầu field phải tồn tại và không được null, nhưng nhiều quy tắc dữ liệu cần kiểm tra sâu hơn: chuỗi không được rỗng, email đúng định dạng, số lượng phần tử nằm trong giới hạn, object lồng nhau phải hợp lệ, hoặc nhiều field phải thỏa một điều kiện kết hợp.

Spring for GraphQL hỗ trợ Bean Validation trên các annotated controller method. Khi ứng dụng có một Bean Validation `Validator`, `AnnotatedControllerConfigurer` có thể phát hiện validator đó. Controller đánh dấu tham số input bằng `@Valid` hoặc `@Validated`; Spring kiểm tra object trước khi gọi method. Nếu có constraint violation, quá trình thực thi phát sinh `ConstraintViolationException`, sau đó ứng dụng có thể chuyển lỗi thành GraphQL errors bằng exception resolution.

Bài học này trình bày cách kết hợp GraphQL input types với Jakarta Bean Validation, cách kiểm tra record/DTO và object lồng nhau, cách dùng validation groups, phân biệt lỗi schema, binding và validation, xử lý `ConstraintViolationException`, cùng kiểm thử và nguyên tắc đặt validation ở đúng tầng.

## 1. Các lớp kiểm tra dữ liệu đầu vào

Khi client gửi input object, dữ liệu đi qua nhiều bước trước khi đến service:

1. GraphQL parse và validate document.
2. GraphQL coercion kiểm tra kiểu scalar, enum, list, required field và nullability theo SDL.
3. Spring for GraphQL bind argument values vào Java DTO.
4. Bean Validation kiểm tra các constraint trên DTO nếu controller method yêu cầu.
5. Controller gọi service/domain để kiểm tra quy tắc nghiệp vụ và thực hiện use case.

Mỗi bước giải quyết một nhóm vấn đề khác nhau:

| Tầng | Kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| GraphQL SDL và coercion | Kiểu dữ liệu, field bắt buộc, nullability | `title: String!` bị thiếu hoặc nhận null |
| Argument binding | Ánh xạ GraphQL input sang Java object | Không chuyển được giá trị sang kiểu Java |
| Bean Validation | Constraint trên DTO và object lồng nhau | Title trống, email sai định dạng |
| Service/domain | Quy tắc phụ thuộc trạng thái và dữ liệu hệ thống | ISBN đã tồn tại, author không thuộc tenant |

Không nên dùng Bean Validation để thay thế SDL. Ví dụ `String!` thể hiện hợp đồng GraphQL rằng field không được null; `@NotBlank` thể hiện thêm quy tắc rằng chuỗi phải chứa ít nhất một ký tự không phải whitespace.

## 2. Khai báo input object trong GraphQL SDL

Giả sử API tạo một cuốn sách cùng thông tin tác giả:

```graphql
input AuthorInput {
  name: String!
  email: String!
}

input CreateBookInput {
  title: String!
  isbn: String!
  publishedYear: Int
  author: AuthorInput!
  tags: [String!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

SDL đảm bảo:

- `input` là kiểu dữ liệu đầu vào, không phải output object type.
- `input` của mutation là bắt buộc.
- `title`, `isbn`, `author`, `tags` không được null.
- Mỗi phần tử trong `tags` không được null.
- `publishedYear` có thể null hoặc không được gửi.

Nhưng SDL không nói rằng title phải có chữ, email phải đúng định dạng, ISBN phải theo mẫu nhất định, hay tags chỉ được có tối đa 10 phần tử. Các constraint đó phù hợp với Bean Validation.

## 3. Khai báo constraint trên Java input DTO

Với Spring Boot 3 trở lên, dùng Jakarta Bean Validation (`jakarta.validation.*`). DTO có thể là Java record:

```java
public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotBlank
        @Pattern(regexp = "^[0-9]{13}$")
        String isbn,

        @Min(1450)
        @Max(2100)
        Integer publishedYear,

        @NotNull
        @Valid
        AuthorInput author,

        @NotNull
        @Size(max = 10)
        List<@NotBlank String> tags) {
}
```

Input lồng nhau:

```java
public record AuthorInput(
        @NotBlank
        @Size(max = 100)
        String name,

        @NotBlank
        @Email
        String email) {
}
```

Các annotation thường dùng:

| Constraint | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null, không rỗng và có ký tự không phải whitespace |
| `@NotEmpty` | Chuỗi, collection, map hoặc array không được null và không rỗng |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Min`, `@Max` | Giới hạn số nguyên |
| `@DecimalMin`, `@DecimalMax` | Giới hạn số thập phân |
| `@Positive`, `@PositiveOrZero` | Giá trị dương hoặc không âm |
| `@Email` | Kiểm tra định dạng email ở mức cơ bản |
| `@Pattern` | Kiểm tra chuỗi theo regular expression |
| `@Past`, `@Future` | Kiểm tra mốc thời gian trong quá khứ hoặc tương lai |

`@NotBlank` phù hợp cho title và name. `@Email` không tự thay thế `@NotBlank`: một chuỗi rỗng có thể được xem là không vi phạm riêng constraint email, vì vậy thường kết hợp cả hai khi email là bắt buộc.

## 4. Kích hoạt Bean Validation trên controller argument

Controller đánh dấu input argument bằng `@Valid`:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Khi có Bean Validation `Validator` bean trong Spring ApplicationContext, `AnnotatedControllerConfigurer` tự phát hiện và bật validation cho annotated controller methods. Thông thường, ứng dụng Spring Boot dùng `spring-boot-starter-validation` để đưa Bean Validation provider và cấu hình validator vào context.

Với cấu hình Spring không dùng Boot auto-configuration, có thể khai báo `LocalValidatorFactoryBean`:

```java
@Configuration
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Đảm bảo dependency và namespace annotation tương thích với phiên bản nền tảng. Spring Boot 3+ dùng `jakarta.validation`; các ứng dụng Spring Boot 2 cũ dùng `javax.validation`.

Validation được thực hiện trước khi controller method được gọi. Nếu input không hợp lệ, code bên trong `bookService.create(input)` không chạy.

## 5. Validation cho nested input object

Một input object có thể chứa input object khác. Để Bean Validation đi sâu vào object lồng nhau, component hoặc property cha phải được đánh dấu `@Valid`:

```java
public record CreateBookInput(
        @NotBlank
        String title,

        @NotNull
        @Valid
        AuthorInput author) {
}

public record AuthorInput(
        @NotBlank
        String name,

        @NotBlank
        @Email
        String email) {
}
```

`@Valid` kích hoạt cascading validation: khi kiểm tra `CreateBookInput`, validator tiếp tục kiểm tra các constraint trong `AuthorInput`. Nếu thiếu `@Valid` trên component `author`, các constraint của `AuthorInput` sẽ không tự động được duyệt chỉ vì object đã được bind.

Phân biệt hai constraint:

- `@NotNull` yêu cầu object author phải có giá trị.
- `@Valid` yêu cầu kiểm tra các constraint bên trong object author.

Trong ví dụ SDL đã khai báo `author: AuthorInput!` nên GraphQL cũng chặn null trước controller. `@NotNull` vẫn có ích nếu DTO được tái sử dụng ở một luồng khác không đi qua GraphQL hoặc nếu muốn giữ hợp đồng validation ở Java layer.

## 6. Validation cho list và phần tử trong list

Input object thường chứa danh sách phần tử:

```graphql
input CreateOrderInput {
  note: String
  lines: [CreateOrderLineInput!]!
}

input CreateOrderLineInput {
  productId: ID!
  quantity: Int!
}
```

DTO có thể khai báo constraint trên collection và cascade xuống từng phần tử:

```java
public record CreateOrderInput(
        @Size(max = 500)
        String note,

        @NotEmpty
        @Size(max = 50)
        List<@Valid CreateOrderLineInput> lines) {
}

public record CreateOrderLineInput(
        @NotBlank
        String productId,

        @Positive
        int quantity) {
}
```

Các constraint có phạm vi khác nhau:

- `@NotEmpty` yêu cầu danh sách phải có ít nhất một phần tử.
- `@Size(max = 50)` giới hạn tổng số phần tử.
- `List<@Valid CreateOrderLineInput>` yêu cầu cascade validation cho từng line.
- `@Positive` kiểm tra quantity của mỗi line.

Nếu cần giới hạn giá trị trực tiếp trên từng phần tử scalar, dùng type-use constraint:

```java
public record CreateBookInput(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags) {
}
```

GraphQL SDL vẫn nên mô tả đúng nullability của list và phần tử. Bean Validation bổ sung quy tắc về số lượng, độ dài hoặc giá trị mà SDL không biểu diễn.

## 7. Validation cho quy tắc liên quan nhiều field

Các constraint như `@NotBlank` hay `@Min` kiểm tra từng property. Một số quy tắc cần kết hợp nhiều field, ví dụ:

- Ngày kết thúc phải sau ngày bắt đầu.
- Chỉ được truyền một trong hai giá trị email hoặc phone.
- Khoảng giá trị phải có minimum nhỏ hơn maximum.

Có thể dùng class-level constraint với custom validator:

```java
@ValidDateRange
public record SearchPeriodInput(
        @NotNull LocalDate from,
        @NotNull LocalDate to) {
}
```

Annotation:

```java
@Constraint(validatedBy = DateRangeValidator.class)
@Target({ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateRange {

    String message() default "End date must be after start date";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Validator:

```java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, SearchPeriodInput> {

    @Override
    public boolean isValid(
            SearchPeriodInput value,
            ConstraintValidatorContext context) {

        if (value == null || value.from() == null || value.to() == null) {
            return true;
        }
        return value.to().isAfter(value.from());
    }
}
```

Trong ví dụ, `@NotNull` chịu trách nhiệm báo lỗi nếu một ngày bị thiếu; class-level validator chỉ kiểm tra quan hệ giữa hai ngày khi cả hai đã có giá trị. Tránh tạo nhiều lỗi trùng lặp cho cùng một tình huống.

Nếu muốn gắn class-level violation vào một property cụ thể, có thể dùng `ConstraintValidatorContext` để tắt default violation và thêm property node. Điều này giúp error metadata thể hiện field liên quan rõ hơn.

## 8. Validation groups với @Validated

Một DTO có thể được dùng trong nhiều use case. Quy tắc khi tạo mới có thể khác quy tắc khi cập nhật:

- Khi tạo mới, ISBN bắt buộc.
- Khi cập nhật, ISBN có thể không được gửi.
- Một số constraint chỉ áp dụng cho thao tác publish.

Bean Validation hỗ trợ validation groups:

```java
public interface Create {}
public interface Update {}
```

DTO:

```java
public record BookInput(
        @NotBlank(groups = Create.class)
        String title,

        @NotBlank(groups = Create.class)
        @Pattern(
                regexp = "^[0-9]{13}$",
                groups = {Create.class, Update.class})
        String isbn) {
}
```

Controller:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Validated(Create.class) BookInput input) {
    return bookService.create(input);
}

@MutationMapping
public Book updateBook(
        @Argument("input") @Validated(Update.class) BookInput input) {
    return bookService.update(input);
}
```

`@Validated` của Spring cho phép chỉ định group cần chạy. Nếu không dùng group, `@Valid` thường là cách ngắn gọn để chạy default group.

Khi có nested object và custom group, kiểm tra cách group được cascade. Có thể dùng `@ConvertGroup` nếu object con cần ánh xạ group của parent sang group khác. Đừng khai báo group quá nhiều nếu quy tắc chỉ khác nhau một vài điều kiện nghiệp vụ; khi đó hai input DTO riêng có thể dễ hiểu hơn.

## 9. Phân biệt GraphQL coercion, binding và Bean Validation

Ba lỗi đầu vào thường bị nhầm lẫn:

### GraphQL coercion error

SDL khai báo:

```graphql
input CreateBookInput {
  title: String!
  publishedYear: Int
}
```

Nếu client gửi `publishedYear: "twenty"` hoặc bỏ `title`, GraphQL engine từ chối input vì sai kiểu hoặc thiếu non-null value. Controller method chưa được gọi; Bean Validation chưa chạy.

### Argument binding error

Sau khi GraphQL đã coercion giá trị, Spring bind map input vào Java DTO. Nếu quá trình chuyển đổi hoặc tạo object thất bại, `GraphQlArgumentBinder` có thể phát sinh `BindException` chứa các field errors và argument path.

Ví dụ Java DTO yêu cầu một kiểu không tương thích với giá trị đã được GraphQL coercion. Đây là lỗi ánh xạ dữ liệu, không phải constraint violation.

### Bean Validation error

Input đã bind thành công thành Java object, nhưng vi phạm constraint như `@NotBlank`, `@Email` hoặc `@Size`. Khi đó Spring phát sinh `ConstraintViolationException`.

| Lỗi | Controller method được gọi? | Ví dụ |
| --- | --- | --- |
| GraphQL parse/validation/coercion | Không | Thiếu `String!`, sai scalar |
| Argument binding | Không | Không bind được input vào constructor/property |
| Bean Validation | Không | `title` là chuỗi chỉ chứa whitespace |
| Service/domain validation | Có | ISBN đã tồn tại trong database |

Spring for GraphQL không hỗ trợ tham số `BindingResult` theo cách Spring MVC thường dùng để controller tự đọc validation errors. Validation errors được xử lý như exception thông qua exception resolution.

## 10. Chuyển ConstraintViolationException thành GraphQL errors

Khi Bean Validation thất bại, exception chứa tập hợp `ConstraintViolation`. Có thể ánh xạ từng violation thành một GraphQL error để client biết property nào không hợp lệ.

Ví dụ resolver:

```java
@Component
public class InputValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected List<GraphQLError> resolveToMultipleErrors(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (!(exception instanceof ConstraintViolationException violationException)) {
            return null;
        }

        return violationException.getConstraintViolations().stream()
                .map(violation -> GraphqlErrorBuilder.newError(environment)
                        .errorType(ErrorType.BAD_REQUEST)
                        .message(violation.getMessage())
                        .extensions(Map.of(
                                "code", "INPUT_VALIDATION_FAILED",
                                "property", violation.getPropertyPath().toString()))
                        .build())
                .toList();
    }
}
```

Resolver thực hiện:

1. Chỉ nhận `ConstraintViolationException`; exception khác được để resolver tiếp theo xử lý.
2. Duyệt từng constraint violation.
3. Dùng `BAD_REQUEST` để phân loại lỗi input.
4. Đưa property path của DTO vào extensions.
5. Dùng `GraphqlErrorBuilder.newError(environment)` để GraphQL error gắn với đúng field đang thực thi.

Ví dụ response:

```json
{
  "data": null,
  "errors": [
    {
      "message": "must not be blank",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "property": "title"
      }
    },
    {
      "message": "must be a well-formed email address",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "property": "author.email"
      }
    }
  ]
}
```

`path` trong GraphQL error trỏ đến field GraphQL đang thực thi, ở ví dụ là mutation `createBook`. `property` trong extensions là đường dẫn property bên trong Java input object. Hai loại path phục vụ hai mục đích khác nhau.

Không đưa `violation.getInvalidValue()` vào response một cách mặc định. Giá trị không hợp lệ có thể chứa email, số điện thoại, token hoặc dữ liệu cá nhân. Thông điệp validation và property path thường đã đủ để client đánh dấu field cần sửa.

## 11. Dùng @GraphQlExceptionHandler thay cho resolver toàn cục

Nếu exception chỉ phát sinh từ annotated controller methods, có thể xử lý bằng `@GraphQlExceptionHandler`:

```java
@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public List<GraphQLError> handle(
            ConstraintViolationException exception,
            DataFetchingEnvironment environment) {

        return exception.getConstraintViolations().stream()
                .map(violation -> GraphqlErrorBuilder.newError(environment)
                        .errorType(ErrorType.BAD_REQUEST)
                        .message(violation.getMessage())
                        .extensions(Map.of(
                                "code", "INPUT_VALIDATION_FAILED",
                                "property", violation.getPropertyPath().toString()))
                        .build())
                .toList();
    }
}
```

Hai lựa chọn:

| Cơ chế | Khi phù hợp |
| --- | --- |
| `@GraphQlExceptionHandler` | Xử lý exception từ annotated controller, có thể đặt trong controller hoặc `@ControllerAdvice` |
| `DataFetcherExceptionResolver` | Chính sách chung cho DataFetcher, bao gồm DataFetcher đăng ký thủ công |

Chọn một cơ chế sở hữu rõ ràng cho `ConstraintViolationException`. Nếu cùng một exception được cả hai cơ chế xử lý, kết quả có thể khó dự đoán hoặc tạo cấu hình trùng lặp.

## 12. Tùy chỉnh thông điệp validation

Không nên để client phụ thuộc vào message mặc định của provider như `must not be blank`. Có thể định nghĩa message ngay trên constraint:

```java
public record CreateBookInput(
        @NotBlank(message = "Book title is required")
        @Size(max = 200, message = "Book title must not exceed 200 characters")
        String title) {
}
```

Hoặc dùng message key:

```java
public record CreateBookInput(
        @NotBlank(message = "{book.title.required}")
        @Size(max = 200, message = "{book.title.size}")
        String title) {
}
```

Các message key có thể được giải quyết qua Bean Validation message bundles, ví dụ `ValidationMessages.properties`:

```properties
book.title.required=Book title is required
book.title.size=Book title must not exceed 200 characters
```

Nếu API cần nhiều ngôn ngữ, cấu hình message bundles theo locale và bảo đảm locale được truyền vào GraphQL execution phù hợp. Client vẫn nên dùng error code để xử lý logic, thay vì phân tích chuỗi message đã được dịch.

## 13. Validation không thay thế quy tắc nghiệp vụ

Bean Validation phù hợp với constraint cấu trúc và dữ liệu:

- Chuỗi bắt buộc, độ dài, pattern.
- Số lượng, khoảng giá trị.
- Email, URL hoặc định dạng ngày.
- Nested input và list element.
- Điều kiện kết hợp các field trong cùng DTO.

Các quy tắc sau thường thuộc service/domain:

- ISBN hoặc email đã tồn tại trong database.
- Author có tồn tại và thuộc tenant hiện tại hay không.
- Người dùng có quyền tạo hoặc cập nhật tài nguyên hay không.
- Trạng thái hiện tại có cho phép chuyển sang trạng thái mới hay không.
- Số lượng hàng tồn kho có đủ tại thời điểm giao dịch hay không.

Không nên gọi database từ một constraint validator chỉ để kiểm tra uniqueness. Hai request đồng thời vẫn có thể vượt qua validation trước khi cùng ghi dữ liệu. Ràng buộc duy nhất phải được bảo vệ ở database và xử lý conflict ở service/domain.

Một validator nên dễ kiểm thử, ít side effect và tập trung vào quy tắc dữ liệu có thể đánh giá từ input. Service/domain vẫn phải kiểm tra các điều kiện phụ thuộc trạng thái hệ thống ngay tại thời điểm thực hiện use case.

## 14. Dependency và cấu hình tối thiểu

Với Spring Boot, thêm Bean Validation starter vào ứng dụng:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Hoặc Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Boot starter cung cấp Bean Validation provider và cấu hình validator cần thiết. Nếu tự cấu hình Spring context, bảo đảm có một Bean Validation `Validator` bean, thường là `LocalValidatorFactoryBean`, để `AnnotatedControllerConfigurer` có thể phát hiện.

Kiểm tra namespace import:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
```

Các ứng dụng Spring Boot 2 cũ dùng package `javax.validation`; không trộn annotation từ hai namespace trong cùng một ứng dụng.

## 15. Kiểm thử input validation bằng GraphQlTester

Kiểm thử nên gửi GraphQL operation thật để xác nhận validation chạy trước khi controller gọi service:

```java
@GraphQlTest(BookMutationController.class)
@Import(InputValidationExceptionResolver.class)
class BookInputValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void rejectsBlankTitleBeforeCallingService() {
        graphQlTester.document("""
                mutation {
                    createBook(input: {
                        title: "   "
                        isbn: "9781234567890"
                        author: {
                            name: "An Nguyen"
                            email: "an@example.com"
                        }
                        tags: ["graphql"]
                    }) {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertThat(errors).hasSize(1);
                    assertThat(errors.get(0).getExtensions())
                            .containsEntry("code", "INPUT_VALIDATION_FAILED")
                            .containsEntry("property", "title");
                });

        verifyNoInteractions(bookService);
    }
}
```

Test giả định:

- Schema có mutation `createBook(input: CreateBookInput!)`.
- `BookMutationController` nhận `@Argument @Valid CreateBookInput`.
- `InputValidationExceptionResolver` được import vào GraphQL test slice.
- Bean Validation starter có mặt trong test runtime.

Để kiểm tra nested validation, gửi email sai định dạng và xác nhận property path là `author.email`. Để kiểm tra list element validation, gửi tag rỗng và xác nhận path chứa index phần tử theo Bean Validation provider.

### Kiểm thử input hợp lệ

Ngoài trường hợp bị từ chối, cần có test cho input hợp lệ:

```java
@Test
void acceptsValidInput() {
    CreateBookInput input = new CreateBookInput(
            "Spring for GraphQL",
            "9781234567890",
            2026,
            new AuthorInput("An Nguyen", "an@example.com"),
            List.of("graphql"));

    given(bookService.create(input))
            .willReturn(new Book("book-1", "Spring for GraphQL"));

    graphQlTester.document("""
            mutation {
                createBook(input: {
                    title: "Spring for GraphQL"
                    isbn: "9781234567890"
                    publishedYear: 2026
                    author: {
                        name: "An Nguyen"
                        email: "an@example.com"
                    }
                    tags: ["graphql"]
                }) {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("createBook.id")
            .entity(String.class)
            .isEqualTo("book-1");

    then(bookService).should().create(input);
}
```

Ví dụ giả định `Book` có constructor và các field được chọn trong response. Bổ sung imports cùng model theo ứng dụng thực tế.

## 16. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Constraint không chạy | Thiếu Validator bean hoặc thiếu Bean Validation provider | Thêm starter và kiểm tra validator trong context |
| `@Valid` không kiểm tra object lồng nhau | Nested property chưa có `@Valid` | Thêm cascading validation ở component/property |
| Nested object null không bị báo lỗi | Chỉ có `@Valid`, không có `@NotNull` | Dùng `@NotNull` khi object là bắt buộc |
| List rỗng vẫn hợp lệ | Chỉ dùng `@Size(max = ...)` | Thêm `@NotEmpty` hoặc `@Size(min = 1)` |
| Một phần tử trong list không được kiểm tra | Thiếu type-use `@Valid` hoặc element constraint | Khai báo `List<@Valid ItemInput>` |
| `@Email` chấp nhận chuỗi rỗng | `@Email` không đồng nghĩa với required | Kết hợp `@NotBlank` nếu bắt buộc |
| Sai kiểu nhưng ConstraintViolationResolver không chạy | GraphQL coercion hoặc argument binding thất bại trước validation | Xử lý đúng loại request/binding error |
| Service vẫn chạy dù input sai | Controller parameter chưa được đánh dấu `@Valid`/`@Validated` hoặc Validator chưa được phát hiện | Kiểm tra method signature và cấu hình |
| Không dùng được `BindingResult` | Spring for GraphQL xử lý validation errors qua exception | Dùng `@GraphQlExceptionHandler` hoặc resolver |
| Constraint group không chạy | Controller chọn group khác với group khai báo trên constraint | Kiểm tra `@Validated` và group membership |
| Error message lộ dữ liệu | Trả invalid value hoặc exception detail | Chỉ trả message và property metadata cần thiết |

## 17. Nguyên tắc thiết kế input validation

- Dùng SDL để mô tả input type, scalar, required field và nullability.
- Dùng DTO riêng cho từng input object hoặc use case.
- Dùng `@Valid` trên controller argument để kích hoạt Bean Validation.
- Dùng `@Valid` trên nested property hoặc list element để cascade.
- Dùng `@NotNull`, `@NotBlank`, `@Size`, `@Pattern` và các constraint phù hợp với ý nghĩa dữ liệu.
- Dùng `@Validated` khi cần validation groups.
- Giữ Bean Validation tập trung vào constraint có thể đánh giá từ input.
- Để service/domain kiểm tra uniqueness, authorization và trạng thái hệ thống.
- Phân biệt GraphQL coercion error, argument binding error và constraint violation.
- Chuẩn hóa `ConstraintViolationException` thành GraphQL error code ổn định.
- Đưa property path vào extensions nếu client cần đánh dấu field.
- Không trả invalid value, stack trace hoặc thông tin nội bộ cho client.
- Kiểm thử cả input hợp lệ, input sai, nested object và collection elements.

## 18. Bài tập thực hành

Xây dựng mutation tạo đơn hàng có nested input:

1. Khai báo `CreateOrderInput` và `CreateOrderLineInput` trong SDL.
2. Tạo Java record cho hai input DTO.
3. Thêm constraint cho mã sản phẩm, số lượng, ghi chú và số lượng dòng.
4. Dùng `List<@Valid CreateOrderLineInput>` để kiểm tra từng dòng.
5. Viết `@MutationMapping` nhận `@Argument @Valid CreateOrderInput`.
6. Cấu hình Bean Validation provider và xác nhận controller được gọi khi input hợp lệ.
7. Thử gửi danh sách rỗng, quantity bằng 0, product ID trống và ghi chú quá dài.
8. Tạo custom class-level constraint kiểm tra ngày giao hàng sau ngày đặt hàng.
9. Thêm validation group cho create và update.
10. Chuyển `ConstraintViolationException` thành GraphQL errors có code `INPUT_VALIDATION_FAILED` và property path.
11. Kiểm tra lỗi GraphQL coercion riêng với lỗi Bean Validation.
12. Xác nhận service không được gọi khi input vi phạm constraint.

Sau bài tập, bạn cần giải thích được validation diễn ra ở giai đoạn nào, cách cascade qua nested input, khi nào dùng `@Valid` hoặc `@Validated`, và vì sao quy tắc phụ thuộc database phải được kiểm tra ở service/domain.

## 19. Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)

Chi tiết exception, validator auto-detection và namespace `javax.validation`/`jakarta.validation` phụ thuộc phiên bản Spring Framework và Spring Boot. Khi nâng cấp dependency, hãy kiểm tra reference documentation đúng phiên bản ứng dụng đang sử dụng.
