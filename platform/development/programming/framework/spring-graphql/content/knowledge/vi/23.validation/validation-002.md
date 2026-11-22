# @Valid

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `@Valid` khi nhận GraphQL input trong Spring for GraphQL.
- Cấu hình Bean Validation để Spring kiểm tra argument trước khi gọi controller method.
- Đặt constraint lên Java DTO hoặc record nhận dữ liệu từ GraphQL.
- Kích hoạt validation đệ quy cho input object lồng nhau và phần tử collection.
- Phân biệt ràng buộc SDL với Bean Validation và quy tắc nghiệp vụ.
- Dùng `@Validated` khi cần validation group.
- Xử lý `ConstraintViolationException` bằng `@GraphQlExceptionHandler`.
- Kiểm thử input hợp lệ, input không hợp lệ và bảo đảm service không chạy khi validation thất bại.

## 1. @Valid giải quyết vấn đề gì?

GraphQL SDL có thể kiểm tra kiểu dữ liệu và nullability của input. Ví dụ, `String!` yêu cầu client cung cấp một chuỗi không null. Tuy nhiên, SDL không thể diễn đạt đầy đủ các quy tắc như:

- Chuỗi không được rỗng hoặc chỉ chứa khoảng trắng.
- Email phải có định dạng phù hợp.
- Số lượng phải lớn hơn 0.
- Một danh sách phải chứa ít nhất một phần tử.
- Mã ISBN không vượt quá độ dài quy định.
- Các ngày bắt đầu và kết thúc phải thỏa mãn quan hệ nghiệp vụ.

Spring for GraphQL tích hợp Jakarta Bean Validation để kiểm tra Java object sau khi GraphQL đã bind argument vào controller method. Khi tham số được đánh dấu `@Valid`, Spring yêu cầu Validator kiểm tra các constraint trên object trước khi gọi method.

Ví dụ, mutation nhận BookInput:

~~~graphql
input BookInput {
  title: String!
  isbn: String!
}

type Mutation {
  addBook(input: BookInput!): Book!
}
~~~

SDL bảo đảm hai field có giá trị String và không null. Nhưng chuỗi rỗng vẫn là String hợp lệ theo GraphQL. Constraint `@NotBlank` có thể từ chối trường hợp đó.

`@Valid` là cầu nối giữa input đã được GraphQL bind và các constraint được khai báo trong Java DTO.

## 2. Cấu hình Bean Validation trong Spring Boot

Spring for GraphQL chỉ kích hoạt validation cho annotated controller khi trong Spring application context có một bean `jakarta.validation.Validator`. Trong Spring Boot, cách thông dụng là thêm starter validation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Dùng dependency management của Spring Boot để quản lý phiên bản tương thích; thông thường không cần tự chỉ định version cho starter.

Starter cung cấp Jakarta Bean Validation API và validation provider như Hibernate Validator. Spring Boot tự cấu hình Validator, thường thông qua `LocalValidatorFactoryBean`, để Spring for GraphQL có thể phát hiện và sử dụng.

Nếu không dùng Spring Boot auto-configuration, cần tự đăng ký Validator bean, ví dụ:

~~~java
@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Khi `AnnotatedControllerConfigurer` tìm thấy Validator bean, nó bật hỗ trợ Bean Validation cho các tham số method được đánh dấu `@Valid` hoặc `@Validated`.

Nếu chỉ thêm annotation `@Valid` nhưng không có validation provider hoặc Validator bean, đừng giả định constraint sẽ tự động được thực thi.

## 3. Đặt constraint lên input DTO

Giả sử API tạo một quyển sách với tiêu đề và ISBN:

~~~graphql
input BookInput {
  title: String!
  isbn: String!
}

type Mutation {
  addBook(input: BookInput!): Book!
}
~~~

Java record:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank
        String title,

        @NotBlank
        @Size(max = 13)
        String isbn) {
}
~~~

Các constraint có ý nghĩa:

- `@NotBlank`: giá trị không null và phải chứa ít nhất một ký tự không phải khoảng trắng.
- `@Size(max = 13)`: độ dài không vượt quá 13 ký tự.

Với Java record, constraint có thể đặt trên record component. Validation provider đọc metadata của record và kiểm tra các thành phần tương ứng.

Controller:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book addBook(
            @Argument("input") @Valid BookInput input) {
        return bookService.addBook(input);
    }
}
~~~

Spring thực hiện các bước:

1. GraphQL kiểm tra operation và coercion input theo SDL.
2. Spring bind argument `input` thành `BookInput`.
3. Bean Validation kiểm tra các constraint do `@Valid` kích hoạt.
4. Nếu validation thành công, Spring gọi `addBook`.
5. Nếu validation thất bại, method không được gọi và một `ConstraintViolationException` được phát sinh để xử lý trong exception chain.

Đặt `@Argument("input")` giúp tên argument rõ ràng và tránh phụ thuộc vào metadata tên tham số Java. `@Valid` kích hoạt validation trên object đã bind.

## 4. @Valid khác gì các constraint annotation?

Hai nhóm annotation có vai trò khác nhau:

- `@Valid` yêu cầu validation object và cascade xuống các object lồng nhau.
- Constraint như `@NotBlank`, `@Positive`, `@Size`, `@Email` định nghĩa điều kiện mà dữ liệu phải thỏa mãn.

Ví dụ:

~~~java
public record CustomerInput(
        @NotBlank String fullName,
        @Email String email) {
}
~~~

Nếu chỉ khai báo DTO như trên nhưng controller không kích hoạt validation, các constraint có thể chưa được chạy trong quá trình xử lý argument.

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument @Valid CustomerInput input) {
    return customerService.create(input);
}
~~~

Ở đây, `@Valid` kích hoạt việc kiểm tra các constraint trên `CustomerInput`.

Không cần đặt `@Valid` lên từng field scalar. Hãy đặt constraint trực tiếp lên field hoặc record component. `@Valid` ở một property có ý nghĩa khi property đó tham chiếu tới object cần cascade validation.

## 5. Validation cho input object lồng nhau

Input object có thể chứa object khác. Muốn validation đi sâu vào object con, cần đánh dấu property lồng bằng `@Valid`.

SDL:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateCustomerInput {
  fullName: String!
  email: String!
  address: AddressInput!
}

type Mutation {
  createCustomer(input: CreateCustomerInput!): Customer!
}
~~~

Java DTO:

~~~java
public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "\\d{5,6}")
        String postalCode) {
}

public record CreateCustomerInput(
        @NotBlank String fullName,
        @Email String email,
        @NotNull @Valid AddressInput address) {
}
~~~

Controller:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") @Valid CreateCustomerInput input) {
    return customerService.create(input);
}
~~~

Có hai tầng validation:

- `@Valid` trên tham số controller kích hoạt validation của `CreateCustomerInput`.
- `@Valid` trên property `address` yêu cầu validator tiếp tục kiểm tra các constraint của `AddressInput`.

Nếu thiếu `@Valid` ở property lồng, validator có thể kiểm tra constraint của object cha nhưng không cascade xuống các constraint bên trong object con.

Đây là nguyên nhân phổ biến khiến DTO cha được validate nhưng dữ liệu trong địa chỉ, thông tin thanh toán hoặc object con vẫn không bị kiểm tra.

## 6. Validation cho List và phần tử trong List

Với collection, cần phân biệt constraint trên collection với constraint trên từng phần tử.

SDL:

~~~graphql
input OrderLineInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  items: [OrderLineInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Java:

~~~java
public record OrderLineInput(
        @NotBlank String productId,
        @Positive Integer quantity) {
}

public record CreateOrderInput(
        @NotEmpty
        List<@NotNull @Valid OrderLineInput> items) {
}
~~~

Ý nghĩa:

- `@NotEmpty` yêu cầu danh sách có ít nhất một phần tử.
- `@NotNull` trên phần tử ngăn một phần tử null.
- `@Valid` trên phần tử kích hoạt validation cho từng `OrderLineInput`.
- `@NotBlank` kiểm tra productId.
- `@Positive` yêu cầu quantity lớn hơn 0.

Với collection lồng nhau, có thể kết hợp constraint trên container và type-use constraint trên phần tử. Hãy khai báo generic type cụ thể, chẳng hạn `List<OrderLineInput>`, để binder tạo đúng object Java.

Một danh sách không rỗng không đồng nghĩa với mọi phần tử đều hợp lệ. Cần kiểm tra cả kích thước collection, null element và constraint của từng object.

## 7. SDL nullability và Bean Validation bổ sung cho nhau

GraphQL SDL và Bean Validation kiểm tra dữ liệu ở hai tầng khác nhau.

| Quy tắc | SDL | Bean Validation |
|---|---|---|
| Field bắt buộc, không null | `String!` | `@NotNull` |
| Chuỗi không rỗng/khoảng trắng | Không có constraint chuẩn tương đương | `@NotBlank` |
| Chuỗi không rỗng | Không có constraint chuẩn tương đương | `@NotEmpty` |
| Giới hạn độ dài | Không có constraint chuẩn tương đương | `@Size` |
| Số lớn hơn 0 | Chỉ kiểm tra kiểu số | `@Positive` |
| Định dạng email | Chỉ kiểm tra String | `@Email` |
| Số phần tử tối thiểu | List type không quy định kích thước | `@Size` hoặc `@NotEmpty` |

Ví dụ, `title: String!` không chấp nhận null hoặc bị bỏ qua khi không có default value, nhưng vẫn chấp nhận `""` và `"   "`. `@NotBlank` bổ sung quy tắc không được rỗng hoặc toàn khoảng trắng.

Tương tự, `quantity: Int!` chỉ bảo đảm đầu vào là số nguyên không null. Nó vẫn chấp nhận 0 hoặc số âm. `@Positive` mới biểu diễn quy tắc lớn hơn 0.

Có thể dùng cả SDL và Bean Validation cho cùng một thuộc tính nếu muốn hợp đồng rõ ràng và DTO còn được tái sử dụng ở nơi khác. Tuy nhiên, cần hiểu một số constraint như `@NotNull` có thể lặp lại điều SDL đã bảo đảm trước khi controller được gọi.

## 8. @Valid và @Validated: khi nào dùng mỗi loại?

`@Valid` thuộc Jakarta Bean Validation và kích hoạt validation theo group mặc định (`Default`). `@Validated` thuộc Spring và cho phép chỉ định validation group.

Ví dụ khai báo group:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}
~~~

DTO:

~~~java
public record BookInput(
        @NotBlank(groups = {
                CreateChecks.class,
                UpdateChecks.class
        })
        String title,

        @NotBlank(groups = CreateChecks.class)
        String isbn) {
}
~~~

Controller dùng group khi tạo mới:

~~~java
@MutationMapping
public Book addBook(
        @Argument("input")
        @Validated(CreateChecks.class) BookInput input) {
    return bookService.addBook(input);
}
~~~

Một method cập nhật có thể dùng group khác:

~~~java
@MutationMapping
public Book updateBook(
        @Argument String id,
        @Argument("input")
        @Validated(UpdateChecks.class) BookInput input) {
    return bookService.updateBook(id, input);
}
~~~

Trong ví dụ này:

- Khi tạo mới, cả title và isbn đều được kiểm tra.
- Khi cập nhật, title được kiểm tra; isbn không nằm trong group UpdateChecks nên constraint đó không chạy.

Các constraint không khai báo group mặc định thuộc `Default.class`. Nếu chỉ gọi validation với một group riêng, constraint thuộc Default không tự động được chạy trừ khi group sequence hoặc cấu hình group được thiết kế để bao gồm chúng.

Dùng `@Valid` khi chỉ cần validation thông thường. Dùng `@Validated(Group.class)` khi cùng DTO có các quy tắc khác nhau theo luồng tạo mới, cập nhật hoặc quy trình nghiệp vụ.

## 9. Validation nhiều cấp và custom constraint

Các constraint có sẵn đủ cho nhiều trường hợp, nhưng đôi khi cần kiểm tra quan hệ giữa nhiều field. Ví dụ, ngày kết thúc phải sau ngày bắt đầu hoặc một input phải có ít nhất một trong hai trường email và phone.

Có thể tạo class-level constraint với annotation riêng và một `ConstraintValidator`.

DTO:

~~~java
@ValidDateRange
public record BookingInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
~~~

Annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {

    String message() default "endDate must be after startDate";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingInput> {

    @Override
    public boolean isValid(
            BookingInput value,
            ConstraintValidatorContext context) {

        if (value == null ||
                value.startDate() == null ||
                value.endDate() == null) {
            return true;
        }

        return value.endDate().isAfter(value.startDate());
    }
}
~~~

Các constraint `@NotNull` xử lý trường hợp thiếu ngày. Class-level validator chỉ kiểm tra quan hệ giữa hai ngày khi cả hai đã có giá trị.

Khi cần gắn lỗi vào một property cụ thể thay vì tên object, `ConstraintValidatorContext` cho phép tạo property node phù hợp. Điều này giúp client hiển thị lỗi gần với field tương ứng.

Không nên nhồi mọi quy tắc domain vào custom validator. Validation phù hợp với điều kiện có thể kiểm tra từ input object. Các quy tắc phụ thuộc database, quyền truy cập hoặc trạng thái hiện tại vẫn nên được kiểm tra trong service/domain layer.

## 10. Validation thất bại xảy ra trước khi controller method chạy

Khi Bean Validation phát hiện constraint violation, Spring for GraphQL không gọi tiếp method handler. Một `ConstraintViolationException` được phát sinh và đi vào exception handling chain.

Điều đó có nghĩa là:

- Service không được gọi.
- Không có transaction nghiệp vụ nào được bắt đầu từ method đó.
- Controller không nhận một object “gần hợp lệ” để tự quyết định tiếp.
- Exception cần được xử lý để tạo GraphQL error phù hợp.

Khác với Spring MVC, annotated GraphQL controller không hỗ trợ nhận `BindingResult` trong method signature để tự đọc lỗi validation ngay cạnh tham số. Các lỗi được xử lý qua exception mechanism.

Đây là điểm cần nhớ khi chuyển một controller REST sang GraphQL: không thể bê nguyên cách nhận `BindingResult` trong Spring MVC vào GraphQL handler method.

## 11. Xử lý ConstraintViolationException bằng @GraphQlExceptionHandler

Spring for GraphQL hỗ trợ `@GraphQlExceptionHandler` để chuyển exception phát sinh từ controller invocation thành GraphQL error. Có thể đặt handler trong controller để xử lý lỗi cục bộ hoặc trong `@ControllerAdvice` để áp dụng cho nhiều controller.

Ví dụ global handler:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(violation -> Map.of(
                                "field",
                                violation.getPropertyPath().toString(),
                                "message",
                                violation.getMessage()))
                        .toList();

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Input validation failed")
                .extensions(Map.of(
                        "code", "INPUT_VALIDATION_FAILED",
                        "violations", violations))
                .build();
    }
}
~~~

Spring chuẩn bị `GraphqlErrorBuilder` theo DataFetchingEnvironment hiện tại và cung cấp vào method exception handler. Nhờ vậy, error có thể mang path và source location của field đang được resolve.

Ví dụ response minh họa:

~~~json
{
  "data": {
    "addBook": null
  },
  "errors": [
    {
      "message": "Input validation failed",
      "path": ["addBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "violations": [
          {
            "field": "addBook.input.title",
            "message": "must not be blank"
          }
        ]
      }
    }
  ]
}
~~~

Nội dung path của violation phụ thuộc vào cấu trúc object và Bean Validation provider. Không đưa giá trị đầu vào bị từ chối vào response vì nó có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm.

Nếu muốn thông báo đơn giản, có thể chỉ trả mã lỗi chung và không expose danh sách constraint. Quan trọng là giữ định dạng lỗi ổn định để client xử lý.

## 12. Phân biệt GraphQL validation, binding error và Bean Validation

Các bước kiểm tra xảy ra ở những thời điểm khác nhau:

| Loại kiểm tra | Ví dụ | Thời điểm |
|---|---|---|
| GraphQL parse/validation | Query sai cú pháp, field không tồn tại | Trước DataFetcher |
| GraphQL input coercion | Truyền chuỗi vào argument Int, thiếu field non-null | Trước DataFetcher |
| Argument binding | Không tạo được DTO hoặc chuyển đổi property thất bại | Khi Spring bind argument |
| Bean Validation | Chuỗi rỗng, số âm, email không hợp lệ | Sau binding, trước method invocation |
| Business validation | Sản phẩm hết hàng, người dùng không có quyền | Trong service/domain |

Ví dụ:

- SDL khai báo `quantity: Int!`; truyền `"two"` sẽ bị GraphQL từ chối trước controller.
- Truyền `quantity: 0` là đúng kiểu Int, nhưng `@Positive` sẽ từ chối trước khi method chạy.
- Truyền `quantity: 2` hợp lệ về dữ liệu, nhưng service vẫn có thể từ chối vì sản phẩm hết hàng.

Argument binding thất bại có thể phát sinh `BindException`; Bean Validation thất bại phát sinh `ConstraintViolationException` theo cơ chế validation của annotated controller. Hai loại lỗi nên được xử lý riêng nếu client cần mã lỗi hoặc cấu trúc chi tiết khác nhau.

## 13. Không thay thế business validation bằng @Valid

Bean Validation phù hợp để kiểm tra cấu trúc và điều kiện của dữ liệu đầu vào. Nhưng không phải mọi quy tắc nghiệp vụ đều có thể kiểm tra ở DTO.

Ví dụ:

- `@Positive quantity` kiểm tra số lượng lớn hơn 0.
- Service kiểm tra số lượng đó có vượt tồn kho hiện tại hay không.
- `@Email` kiểm tra định dạng email cơ bản.
- Service kiểm tra email đã được đăng ký hay chưa.
- `@NotNull customerId` kiểm tra có mã khách hàng.
- Service kiểm tra người dùng hiện tại có quyền đặt hàng cho khách hàng đó hay không.

Các kiểm tra phụ thuộc database, security principal, transaction hoặc trạng thái domain nên nằm trong service/domain layer.

Không nên gọi repository từ `ConstraintValidator` cho mọi constraint chỉ để gom tất cả validation vào DTO. Điều đó có thể tạo truy vấn ẩn, khó kiểm soát transaction và khiến validation trở nên khó kiểm thử.

## 14. Kiểm thử @Valid bằng GraphQlTester

Nên kiểm thử từ GraphQL operation thực tế để xác nhận SDL, argument binding, Bean Validation và exception handling hoạt động cùng nhau.

Ví dụ input:

~~~java
public record BookInput(
        @NotBlank String title,
        @NotBlank @Size(max = 13) String isbn) {
}
~~~

Mutation:

~~~java
@MutationMapping
public Book addBook(
        @Argument("input") @Valid BookInput input) {
    return bookService.addBook(input);
}
~~~

Test dữ liệu không hợp lệ:

~~~java
@Test
void shouldRejectBlankTitleBeforeCallingService() {
    graphQlTester.document("""
            mutation AddBook($input: BookInput!) {
                addBook(input: $input) {
                    id
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "   ",
                    "isbn", "1234567890123"))
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Input validation failed");
            });

    verifyNoInteractions(bookService);
}
~~~

Test này giả định ứng dụng đã đăng ký `GraphQlValidationAdvice` như ví dụ trước. Việc xác minh service không được gọi chứng minh validation diễn ra trước method invocation.

Test dữ liệu hợp lệ:

~~~java
@Test
void shouldCreateBookWhenInputIsValid() {
    when(bookService.addBook(any(BookInput.class)))
            .thenReturn(new Book(
                    "b-01", "GraphQL in Practice", "1234567890123"));

    graphQlTester.document("""
            mutation AddBook($input: BookInput!) {
                addBook(input: $input) {
                    title
                    isbn
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "GraphQL in Practice",
                    "isbn", "1234567890123"))
            .execute()
            .path("addBook.title")
            .entity(String.class)
            .isEqualTo("GraphQL in Practice");

    verify(bookService).addBook(any(BookInput.class));
}
~~~

Các trường hợp nên có trong bộ test:

1. Input hợp lệ được bind và method chạy.
2. Chuỗi rỗng hoặc toàn khoảng trắng bị `@NotBlank` từ chối.
3. Chuỗi vượt giới hạn bị `@Size` từ chối.
4. Object lồng nhau được cascade validation.
5. Phần tử list không hợp lệ bị phát hiện.
6. Constraint group được áp dụng đúng theo thao tác create/update.
7. GraphQL non-null hoặc scalar coercion lỗi trước khi Bean Validation chạy.
8. `ConstraintViolationException` được chuyển thành GraphQL error có mã ổn định.
9. Service không được gọi khi validation thất bại.
10. Response không làm lộ giá trị nhạy cảm của input.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@Valid` không chạy | Không có Validator bean hoặc validation provider | Thêm starter validation hoặc đăng ký Validator |
| DTO cha được validate nhưng object con không | Thiếu `@Valid` trên property lồng | Đánh dấu cascade validation |
| List không kiểm tra từng phần tử | Chỉ có constraint trên collection | Dùng `List<@Valid ItemInput>` |
| Chuỗi rỗng vẫn được chấp nhận | Chỉ dùng GraphQL `String!` hoặc `@NotNull` | Dùng `@NotBlank` |
| Số 0 vẫn được chấp nhận | SDL `Int!` chỉ kiểm tra kiểu và null | Dùng `@Positive` hoặc constraint phù hợp |
| Constraint group không chạy | Controller chọn group khác với group trên constraint | Đồng bộ `@Validated` và thuộc tính groups |
| Controller không nhận BindingResult | GraphQL annotated controller không hỗ trợ cách này như Spring MVC | Xử lý exception qua `@GraphQlExceptionHandler` |
| Client nhận lỗi quá chi tiết | Trả trực tiếp dữ liệu violation hoặc rejected value | Chỉ công bố field path, message và mã lỗi cần thiết |

## 16. Checklist triển khai @Valid

Trước khi đưa mutation hoặc Query nhận input vào sử dụng:

- [ ] Có Bean Validation provider và Validator bean.
- [ ] DTO có constraint phù hợp với quy tắc dữ liệu.
- [ ] Tham số input được đánh dấu `@Valid` hoặc `@Validated`.
- [ ] Object lồng có `@Valid` để cascade.
- [ ] Collection có constraint trên container và phần tử khi cần.
- [ ] SDL nullability khớp với hợp đồng đầu vào.
- [ ] Validation group được chọn đúng cho từng use case.
- [ ] `ConstraintViolationException` được chuyển thành GraphQL error ổn định.
- [ ] Business validation vẫn nằm trong service/domain layer.
- [ ] Test xác nhận method/service không chạy khi validation thất bại.
- [ ] Error response không làm lộ giá trị input nhạy cảm.

## Kết luận

`@Valid` cho phép Spring for GraphQL kích hoạt Jakarta Bean Validation trên argument đã được bind thành Java object. Khi có Validator bean, `AnnotatedControllerConfigurer` kiểm tra tham số trước khi gọi controller method. Constraint violation làm phát sinh `ConstraintViolationException`, có thể được chuyển thành GraphQL error bằng `@GraphQlExceptionHandler` hoặc cơ chế exception resolver phù hợp.

SDL kiểm tra cấu trúc, kiểu và nullability; Bean Validation kiểm tra điều kiện của dữ liệu; service/domain layer xử lý quy tắc phụ thuộc trạng thái và nghiệp vụ. Kết hợp đúng ba tầng, cascade validation cho object lồng và test bằng `GraphQlTester` giúp input API rõ ràng, dễ sử dụng và an toàn hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handler)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Jakarta Validation API — @Valid](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid)
