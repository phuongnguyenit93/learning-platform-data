# `@Validated` trong Spring for GraphQL

GraphQL SDL kiểm tra kiểu dữ liệu, argument bắt buộc và nullability trước khi gọi resolver. Nhưng những quy tắc như tiêu đề không được để trống, số lượng phải lớn hơn 0 hoặc ISBN chỉ được phép có độ dài nhất định thuộc về validation nghiệp vụ của ứng dụng.

Spring for GraphQL tích hợp Jakarta Bean Validation với annotated controllers. Khi có `Validator` bean trong Spring context, `AnnotatedControllerConfigurer` có thể kiểm tra tham số handler trước khi gọi method. Ta có thể dùng `@Valid` để kích hoạt validation theo nhóm mặc định, hoặc dùng Spring `@Validated` để chọn validation groups như tạo mới và cập nhật.

## 1. `@Validated` là gì?

`@Validated` nằm trong package `org.springframework.validation.annotation`. Đây là annotation của Spring mở rộng cách dùng Bean Validation bằng khả năng chỉ định validation groups.

```java
import org.springframework.validation.annotation.Validated;

@Validated
public class Example {
}
```

Trong Spring for GraphQL, cách dùng thường gặp là đặt `@Validated` trực tiếp trên tham số method của annotated controller:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Validated(OnCreate.class) BookInput input) {
    return bookService.create(input);
}
```

`OnCreate.class` là nhóm validation được áp dụng cho `BookInput`. Nhờ đó, cùng một DTO có thể dùng trong nhiều mutation nhưng mỗi use case áp dụng các quy tắc khác nhau.

## 2. Chuẩn bị Bean Validation provider

Để validation hoạt động, ứng dụng cần một Bean Validation provider và một `Validator` bean mà Spring for GraphQL có thể phát hiện. Với Spring Boot, dependency thường dùng là `spring-boot-starter-validation`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Starter này đưa implementation như Hibernate Validator vào classpath và Spring Boot thường tự cấu hình validator cần thiết. Nếu tự cấu hình ứng dụng hoặc không có validator bean được tạo tự động, có thể khai báo `LocalValidatorFactoryBean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

`LocalValidatorFactoryBean` tích hợp Jakarta Bean Validation với Spring và có thể được inject như `jakarta.validation.Validator` hoặc Spring `org.springframework.validation.Validator`.

Với Spring Boot 3 trở lên, dùng package `jakarta.validation.*`. Các ví dụ cũ dùng `javax.validation.*` thuộc thế hệ dependency trước Jakarta EE 9; không trộn hai namespace trong cùng ứng dụng.

## 3. Khai báo constraint trên input object

Giả sử API có mutation tạo sách:

```graphql
input BookInput {
    id: ID
    title: String!
    isbn: String
    description: String
}

type Mutation {
    createBook(input: BookInput!): Book!
    updateBook(input: BookInput!): Book!
}
```

Java record có thể khai báo constraint trên các component:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank String title,
        @NotBlank @Size(max = 13) String isbn,
        @Size(max = 500) String description) {
}
```

Ý nghĩa các constraint:

- `@NotBlank` yêu cầu chuỗi khác null và có ít nhất một ký tự không phải khoảng trắng.
- `@Size(max = 13)` giới hạn độ dài chuỗi tối đa 13 ký tự.
- `description` nullable trong SDL và cũng có thể null trong Java; nếu có giá trị thì không được dài quá 500 ký tự.

`String!` trong SDL chỉ bảo đảm client phải cung cấp giá trị khác null. Nó không bảo đảm chuỗi có nội dung. `@NotBlank` bổ sung quy tắc đó ở tầng Bean Validation.

## 4. Kích hoạt validation bằng `@Valid`

Với một input object dùng nhóm mặc định, đặt `@Valid` trên tham số `@Argument`:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument("input") @Valid BookInput input) {
        return bookService.create(input);
    }
}
```

Spring for GraphQL bind argument thành `BookInput`, chạy Bean Validation rồi mới gọi method. Nếu dữ liệu vi phạm constraint, method `createBook` không được thực thi và validation exception được đưa vào GraphQL exception handling.

`@Valid` là annotation của Jakarta Validation để yêu cầu validation/cascade theo nhóm mặc định. Bản thân `@Valid` không phải một constraint và không chọn validation group khác.

## 5. `@Validated` và validation groups

Validation groups cho phép dùng cùng một DTO nhưng áp dụng các quy tắc khác nhau theo hành động. Ví dụ khi tạo sách cần ISBN, còn khi cập nhật chỉ cần ID và tiêu đề.

Đầu tiên, khai báo các group:

```java
import jakarta.validation.groups.Default;

public interface OnCreate extends Default {
}

public interface OnUpdate extends Default {
}
```

Hai group kế thừa `Default`, vì vậy khi validate `OnCreate` hoặc `OnUpdate`, các constraint thuộc nhóm mặc định cũng được áp dụng.

DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank String title,
        @NotBlank(groups = OnCreate.class) String isbn,
        @NotNull(groups = OnUpdate.class) String id,
        @Size(max = 500) String description) {
}
```

Controller:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.validation.annotation.Validated;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Validated(OnCreate.class) BookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("input") @Validated(OnUpdate.class) BookInput input) {
        return bookService.update(input);
    }
}
```

Với cách khai báo trên:

- Cả create và update đều yêu cầu `title` không trống vì constraint thuộc nhóm `Default`, được kế thừa bởi hai group.
- Create yêu cầu `isbn` không trống.
- Update yêu cầu `id` khác null.
- `description` luôn phải nằm trong giới hạn độ dài nếu được cung cấp.

Nếu một group không kế thừa `Default`, các constraint thuộc `Default` sẽ không tự động chạy khi chỉ validate group đó. Hãy quyết định rõ group inheritance hoặc gán constraint vào các group cần thiết để tránh vô tình bỏ qua validation.

## 6. Phân biệt `@Valid` và `@Validated`

| Đặc điểm | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| Nguồn gốc | Jakarta Bean Validation | Spring Framework |
| Mục đích | Kích hoạt cascade validation theo nhóm mặc định | Kích hoạt validation trong tích hợp Spring và có thể chọn groups |
| Chọn group | Không có thuộc tính group | Có thể truyền một hoặc nhiều group class |
| Cách dùng trong GraphQL | `@Argument @Valid Input input` | `@Argument @Validated(OnCreate.class) Input input` |

Chọn `@Valid` khi chỉ cần áp dụng các constraint mặc định. Chọn `@Validated` khi mutation cần group riêng, ví dụ `OnCreate`, `OnUpdate` hoặc `AdminOperation`.

Không cần đặt cả `@Valid` và `@Validated` trên cùng một tham số chỉ để “bật” validation. Chọn annotation phù hợp với group cần chạy và khai báo `@Valid` ở các thuộc tính lồng nhau khi cần cascade xuống object con.

## 7. Cascade validation cho object lồng nhau và collection

`@Validated` chọn group ở tham số controller, còn `@Valid` trên thuộc tính lồng nhau yêu cầu validator đi sâu vào object con.

Ví dụ schema:

```graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input PlaceOrderInput {
    customerId: ID!
    lines: [OrderLineInput!]!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}
```

DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record OrderLineInput(
        @NotBlank String productId,
        @Positive Integer quantity) {
}

public record PlaceOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderLineInput> lines) {
}
```

Controller:

```java
@MutationMapping
public Order placeOrder(
        @Argument("input") @Validated(OnCreate.class) PlaceOrderInput input) {
    return orderService.place(input);
}
```

`@NotEmpty` yêu cầu danh sách có ít nhất một phần tử. `@Valid` trên phần tử collection yêu cầu validator kiểm tra từng `OrderLineInput`; `@Positive` bảo đảm quantity lớn hơn 0. Nếu không cascade, constraint trong object con có thể không được thực thi khi chỉ validate object cha.

Với object lồng nhau có group riêng, group được cascade theo mặc định. Có thể dùng `@ConvertGroup` khi cần chuyển từ group của object cha sang group khác ở object con.

## 8. Validation trực tiếp trên scalar argument

Bean Validation trong annotated controllers không chỉ áp dụng cho input object. Các method parameter khác cũng có thể được kiểm tra bằng constraint trực tiếp.

Ví dụ query có keyword và page size:

```graphql
type Query {
    searchBooks(keyword: String!, pageSize: Int = 20): [Book!]!
}
```

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") @NotBlank String keyword,
        @Argument("pageSize") @Min(1) @Max(100) Integer pageSize) {
    return bookService.search(keyword, pageSize);
}
```

Ở đây `@NotBlank`, `@Min` và `@Max` kiểm tra giá trị scalar sau khi GraphQL đã parse và bind argument. `pageSize` có default 20 trong SDL; Bean Validation giới hạn giá trị client có thể truyền trong khoảng 1 đến 100.

## 9. SDL validation và Bean Validation giải quyết hai lớp khác nhau

GraphQL engine kiểm tra contract của schema trước khi gọi resolver. Bean Validation kiểm tra quy tắc trên object/parameter Java sau khi argument đã được bind.

| Quy tắc | Nơi phù hợp |
| --- | --- |
| Argument bắt buộc phải có | SDL: `id: ID!` |
| Giá trị phải là số nguyên | GraphQL scalar `Int` |
| Chuỗi không được để trống | Bean Validation: `@NotBlank` |
| Số lượng phải lớn hơn 0 | Bean Validation: `@Positive` |
| Danh sách phải có phần tử | Bean Validation: `@NotEmpty` |
| Các field trong input phải thỏa quan hệ với nhau | Class-level constraint hoặc validation logic phù hợp |
| Người dùng có quyền thao tác trên tài nguyên | Authorization/service/domain, không chỉ Bean Validation |
| ISBN phải duy nhất trong database | Service/domain và database constraint |

Không dùng Bean Validation để thay thế GraphQL type system. Ví dụ, nếu `id` bắt buộc khác null, hãy khai báo `ID!` trong SDL; `@NotNull` có thể bổ sung kiểm tra ở Java nhưng không làm thay đổi contract của schema.

## 10. Constraint tùy chỉnh và quy tắc nhiều field

Các constraint chuẩn như `@NotBlank`, `@Size`, `@Positive` phù hợp với kiểm tra trên một giá trị. Với quy tắc phụ thuộc nhiều field, có thể tạo class-level constraint.

Ví dụ một input có ngày bắt đầu và kết thúc:

```java
@ValidDateRange
public record BookingInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
```

`@ValidDateRange` là custom constraint của ứng dụng, với `ConstraintValidator<ValidDateRange, BookingInput>` kiểm tra `endDate` không đứng trước `startDate`. Khi constraint không hợp lệ, validator tạo violation gắn với object hoặc property phù hợp.

Custom validator nên kiểm tra quy tắc xác định từ dữ liệu đầu vào. Tránh thực hiện network call hoặc truy vấn database trong validator để kiểm tra quyền, tồn tại hay tính duy nhất; các quy tắc đó thường thuộc application service/domain và cần xử lý transaction/concurrency.

## 11. Xử lý validation groups trong thiết kế API

Validation groups hữu ích khi cùng một input object phục vụ nhiều use case, nhưng không nên tạo quá nhiều group khiến quy tắc khó hiểu.

Một cách tổ chức:

- `Default`: quy tắc luôn đúng cho mọi thao tác, ví dụ tiêu đề không trống.
- `OnCreate`: quy tắc chỉ áp dụng khi tạo, ví dụ ISBN bắt buộc.
- `OnUpdate`: quy tắc chỉ áp dụng khi cập nhật, ví dụ ID phải có.
- `OnPublish`: quy tắc cần thỏa khi xuất bản, ví dụ nội dung và ảnh bìa đã đầy đủ.

Đặt tên group theo use case thay vì theo tên màn hình hoặc client. Một group nên biểu diễn một tập quy tắc có ý nghĩa ổn định ở server.

Nếu create và update có input khác nhau đáng kể, hai input type riêng đôi khi dễ hiểu và an toàn hơn một DTO lớn với nhiều group. Validation groups là công cụ tái sử dụng constraint, không phải lý do để gom mọi mutation vào một input object duy nhất.

## 12. Lỗi validation được chuyển thành GraphQL error

Khi validation thất bại, Spring for GraphQL phát sinh `ConstraintViolationException`. Exception được đưa qua cơ chế xử lý lỗi GraphQL; controller method không được gọi.

Có thể xử lý bằng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice` để chuẩn hóa lỗi cho client:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleValidation(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ")
                .extensions(java.util.Map.of("code", "VALIDATION_FAILED"))
                .build();
    }
}
```

Ví dụ trên trả một message tổng quát và mã lỗi ổn định. Nếu muốn trả danh sách field lỗi, hãy chuyển `ConstraintViolation` thành cấu trúc `extensions` đã được lọc, chỉ bao gồm field path và mã lỗi cần thiết. Tránh đưa invalid value, thông tin cá nhân, tên class nội bộ hoặc chi tiết triển khai vào response.

Một lựa chọn khác là xử lý exception qua `DataFetcherExceptionResolver`. Chọn một cơ chế chung để tránh cùng một exception bị ánh xạ khác nhau giữa các controller.

## 13. Phân biệt lỗi binding và lỗi validation

Hai loại lỗi thường xuất hiện gần nhau nhưng xảy ra ở hai bước khác nhau:

1. **Binding error:** Spring không thể chuyển GraphQL argument thành kiểu Java đích, ví dụ input object không tương thích constructor/property hoặc giá trị không chuyển đổi được. Spring for GraphQL có thể phát `BindException`.
2. **Validation error:** Binding thành công nhưng object vi phạm constraint như `@NotBlank`, `@Positive` hoặc group đang áp dụng. Spring for GraphQL phát `ConstraintViolationException`.

Ví dụ client gửi `quantity: "many"` cho argument `Int` có thể bị GraphQL từ chối ở bước parse/coercion trước khi method được gọi. Nếu client gửi `quantity: -2`, giá trị là một `Int` hợp lệ nhưng vi phạm `@Positive`; đây là lỗi Bean Validation.

Nên phân loại các lỗi này rõ ràng để client biết nên sửa kiểu dữ liệu, cấu trúc input hay giá trị nghiệp vụ.

## 14. `@Validated` ở tham số controller và ở cấp class

Trong annotated controller của Spring for GraphQL, cách trực tiếp để chọn validation group cho một argument là đặt `@Validated(Group.class)` ngay trên tham số handler method.

Spring `@Validated` cũng được dùng ở cấp class hoặc method cho Spring-driven method validation thông qua AOP, thường với `MethodValidationPostProcessor`. Đây là cơ chế method validation chung của Spring, khác với việc `AnnotatedControllerConfigurer` kiểm tra argument của GraphQL controller. Đừng chỉ thêm `@Validated` ở cấp class rồi cho rằng mọi GraphQL input đã được cascade validation theo group mong muốn; hãy đặt annotation trên tham số cần validate và kiểm thử handler thực tế.

Nếu dùng method validation AOP cho service, có thể đặt `@Validated` ở service class và constraint trên tham số method service. Khi đó cần hiểu proxy/AOP, self-invocation và exception path của service. Dù dùng ở tầng nào, quy tắc nghiệp vụ quan trọng vẫn nên được bảo vệ trong application service/domain để không phụ thuộc duy nhất vào GraphQL adapter.

## 15. Kiểm thử `@Validated` với GraphQlTester

Kiểm thử nên xác nhận cả trường hợp hợp lệ và không hợp lệ, đồng thời xác nhận service không bị gọi khi validation thất bại.

Ví dụ mutation tạo sách với input sai:

```java
import java.util.Map;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void createBookRejectsBlankTitle() {
    graphQlTester.document("""
            mutation CreateBook($input: BookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
                "title", "   ",
                "isbn", "9781234567890"))
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}
```

Test giả định `GraphQlTester`, `bookService` và mock/fixture đã được cấu hình trong test context. Có thể kiểm tra `extensions.code` nếu exception handler đã chuẩn hóa mã lỗi.

Kiểm thử validation groups bằng hai request độc lập:

```java
@Test
void createBookRequiresIsbn() {
    graphQlTester.document("""
            mutation {
                createBook(input: { title: "Spring GraphQL" }) {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}

@Test
void updateBookDoesNotRequireIsbn() {
    graphQlTester.document("""
            mutation {
                updateBook(input: { id: "book-10", title: "Updated title" }) {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .verify();
}
```

Test giả định `graphQlTester` và `bookService` đã được cấu hình trong test context; với test update thành công, mock service cần trả về một `Book` hợp lệ. Request tạo mới thiếu ISBN bị chặn bởi `OnCreate`, còn request cập nhật không cần ISBN vì `isbn` không thuộc `OnUpdate`. Cả hai vẫn áp dụng constraint `Default` do group kế thừa `Default`.

Các trường hợp nên kiểm tra:

1. Constraint nhóm Default được áp dụng cho create và update.
2. Constraint `OnCreate` chỉ áp dụng cho mutation tạo mới.
3. Constraint `OnUpdate` chỉ áp dụng cho mutation cập nhật.
4. Nested object và collection được cascade validation qua `@Valid`.
5. Scalar argument vi phạm `@NotBlank`, `@Min` hoặc `@Max` bị từ chối.
6. Binding error được phân biệt với constraint violation.
7. Handler service không được gọi khi validation thất bại.
8. GraphQL error không làm lộ invalid value hoặc thông tin nội bộ.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@Valid` không chạy | Không có Validator bean/provider hoặc chưa đặt annotation trên tham số | Thêm validation starter/Validator bean và đặt `@Valid` hoặc `@Validated`. |
| Group `OnCreate` không chạy | Dùng nhầm `@Valid` hoặc không truyền group vào `@Validated` | Dùng `@Validated(OnCreate.class)` trên tham số. |
| Constraint Default không chạy khi chọn group | Group tùy chỉnh không kế thừa Default và constraint không khai báo group đó | Kế thừa `Default` hoặc gán constraint vào group cần thiết. |
| Field trong object con không được kiểm tra | Thiếu `@Valid` ở thuộc tính hoặc phần tử collection | Thêm cascade validation đúng vị trí. |
| `String!` vẫn nhận chuỗi rỗng | Non-Null chỉ loại bỏ null, không kiểm tra nội dung | Dùng `@NotBlank` hoặc constraint phù hợp. |
| Method được gọi dù input không hợp lệ | Validation không được kích hoạt hoặc validator không được phát hiện | Kiểm tra validator bean, annotation và integration test. |
| Client thấy lỗi binding thay vì validation | Argument không bind được trước khi Bean Validation chạy | Kiểm tra SDL, kiểu input và Java constructor/property. |
| Lộ dữ liệu trong error message | Trả nguyên exception/invalid value cho client | Chuẩn hóa message và chỉ trả mã/path đã được lọc. |

## 17. Checklist triển khai `@Validated`

1. Thêm Bean Validation provider và bảo đảm có `Validator` bean.
2. Dùng `jakarta.validation` với Spring Boot 3+.
3. Đặt `@Valid` trên argument nếu chỉ cần nhóm mặc định.
4. Đặt `@Validated(Group.class)` trên tham số GraphQL cần validation theo nhóm.
5. Khai báo group rõ ràng theo use case và quyết định cách kế thừa `Default`.
6. Thêm `@Valid` vào object/collection lồng nhau để cascade validation.
7. Dùng SDL cho kiểu, required và nullability; dùng Bean Validation cho quy tắc giá trị.
8. Giữ quy tắc nghiệp vụ và authorization quan trọng trong service/domain.
9. Chuẩn hóa `ConstraintViolationException` thành GraphQL error an toàn cho client.
10. Kiểm thử group, nested validation, binding error và việc service không chạy khi input sai.

`@Validated` giúp Spring for GraphQL áp dụng đúng tập constraint theo từng use case. Khi kết hợp validator bean, validation groups, cascade `@Valid` và xử lý GraphQL error rõ ràng, controller có thể từ chối input không hợp lệ trước khi chạy nghiệp vụ mà vẫn giữ schema và contract client dễ hiểu.

Tài liệu tham khảo: [Spring for GraphQL — Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation), [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html), và [Spring `@Validated` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html).
