# ConstraintViolationException

Trong Spring for GraphQL, dữ liệu đầu vào thường được bind từ GraphQL argument vào Java object rồi kiểm tra bằng Jakarta Bean Validation. Ví dụ, mutation tạo sách có thể yêu cầu tiêu đề không được để trống, ISBN phải đúng định dạng và năm xuất bản nằm trong một khoảng hợp lệ. Khi một hoặc nhiều constraint không được thỏa mãn, Bean Validation có thể phát sinh **ConstraintViolationException**.

ConstraintViolationException chứa tập hợp các ConstraintViolation mô tả từng quy tắc bị vi phạm. Spring for GraphQL có thể chuyển exception này thành GraphQL errors thông qua cơ chế exception resolution. Nhờ đó, client nhận được thông báo lỗi có cấu trúc mà không cần server để lộ stack trace hoặc chi tiết nội bộ.

## ConstraintViolationException xuất hiện ở giai đoạn nào?

Một request GraphQL đi qua nhiều bước trước khi resolver trả dữ liệu:

~~~mermaid
flowchart TD
    A["GraphQL document và variables"] --> B["Parse và validate operation"]
    B --> C["Coercion scalar và enum"]
    C --> D["Bind argument vào Java object"]
    D --> E["Bean Validation"]
    E --> F["Gọi controller resolver"]
    F --> G["Service và domain logic"]
    G --> H["GraphQL response"]
    E --> X["ConstraintViolationException"]
    X --> Y["GraphQL exception resolver"]
    Y --> H
~~~

ConstraintViolationException thường xuất hiện ở bước Bean Validation, sau khi GraphQL đã chấp nhận kiểu dữ liệu và Spring đã bind argument vào Java object, nhưng trước khi phương thức controller được gọi thành công.

Điều này khác với các lỗi sau:

| Loại lỗi | Thời điểm | Ví dụ |
| --- | --- | --- |
| GraphQL parse/validation error | Trước khi thực thi resolver | Sai cú pháp, field không tồn tại, thiếu argument non-null |
| Scalar coercion error | Khi GraphQL chuyển đổi input | Truyền chuỗi vào argument Int hoặc enum value không hợp lệ |
| Argument binding error | Khi Spring chuyển map argument thành Java object | Không tạo được DTO hoặc không chuyển đổi được property |
| ConstraintViolationException | Khi Bean Validation kiểm tra object hoặc method parameter | title rỗng, quantity nhỏ hơn 1 |
| Domain exception | Trong service hoặc domain logic | Sản phẩm không tồn tại, người dùng không có quyền thực hiện |

Phân biệt đúng nguồn lỗi giúp chọn đúng nơi xử lý. ConstraintViolationException không phải lỗi cú pháp GraphQL và cũng không đồng nghĩa với lỗi bind argument.

## Bean Validation trong annotated controller

Spring for GraphQL hỗ trợ Bean Validation cho các phương thức annotated controller khi ứng dụng có một Validator bean. Thông thường, Spring Boot tạo LocalValidatorFactoryBean khi dependency validation có mặt trên classpath.

Với Gradle, có thể thêm starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Nếu dự án tự cấu hình validation, bảo đảm có Jakarta Validation provider như Hibernate Validator và một Validator bean tương thích. Spring for GraphQL sử dụng validator được cấu hình để kiểm tra các tham số controller có annotation phù hợp.

## Khai báo constraint trên input DTO

Giả sử API có mutation tạo sách:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}

input CreateBookInput {
  title: String!
  isbn: String!
  publishedYear: Int!
}

type Book {
  id: ID!
  title: String!
  isbn: String!
  publishedYear: Int!
}
~~~

Java record có thể khai báo constraint trực tiếp trên component:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateBookInput(
        @NotBlank(message = "Tiêu đề không được để trống")
        @Size(max = 150, message = "Tiêu đề không được vượt quá 150 ký tự")
        String title,

        @NotBlank(message = "ISBN không được để trống")
        @Pattern(
                regexp = "[0-9Xx-]{10,17}",
                message = "ISBN không đúng định dạng")
        String isbn,

        @NotNull(message = "Năm xuất bản là bắt buộc")
        @Min(value = 1450, message = "Năm xuất bản không hợp lệ")
        @Max(value = 2100, message = "Năm xuất bản không hợp lệ")
        Integer publishedYear) {
}
~~~

Regular expression trên chỉ kiểm tra độ dài và nhóm ký tự được phép; nó chưa xác minh cấu trúc hay checksum của ISBN-10/ISBN-13. Nếu cần xác thực ISBN đầy đủ, hãy dùng custom constraint validator hoặc thư viện chuyên dụng.

Một số constraint thường dùng:

| Constraint | Mục đích |
| --- | --- |
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi phải có ít nhất một ký tự không phải khoảng trắng |
| @NotEmpty | Chuỗi, collection hoặc map không được rỗng |
| @Size | Giới hạn độ dài chuỗi hoặc số phần tử |
| @Min, @Max | Giới hạn giá trị số |
| @Positive, @PositiveOrZero | Kiểm tra số dương hoặc không âm |
| @Email | Kiểm tra định dạng email |
| @Pattern | Kiểm tra chuỗi theo regular expression |

Chọn constraint đúng với ý nghĩa dữ liệu. Ví dụ, @NotBlank phù hợp với title, còn @NotNull phù hợp với một số nguyên bắt buộc. Với Integer nullable, @Min không tự làm giá trị null trở thành không hợp lệ; cần kết hợp @NotNull nếu field bắt buộc.

## Kích hoạt validation bằng @Valid

Đánh dấu tham số input bằng @Valid để yêu cầu Spring for GraphQL kiểm tra các constraint trước khi gọi resolver:

~~~java
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
    public Book createBook(@Argument @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Khi input hợp lệ, phương thức createBook được gọi. Nếu có constraint bị vi phạm, Spring không gọi phần thân phương thức như một lần xử lý thành công mà phát sinh ConstraintViolationException. Vì thế, service không nên phải nhận object đã biết là không hợp lệ chỉ để tự kiểm tra lại các constraint cơ bản.

@Valid cũng có ý nghĩa cascade validation: nếu DTO chứa một object con, validator sẽ kiểm tra object con khi property được đánh dấu @Valid.

~~~java
public record AuthorInput(
        @NotBlank String name,
        @Email String email) {
}

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Valid AuthorInput author) {
}
~~~

Với collection object lồng nhau, có thể dùng container element validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotEmpty List<@Valid AuthorInput> authors) {
}
~~~

Khi đó validator kiểm tra cả constraint trên danh sách và constraint của từng phần tử AuthorInput.

## Phân biệt @Valid và @Validated

@Valid là annotation của Jakarta Validation, thường dùng để yêu cầu validation và cascade vào object lồng nhau. Spring cung cấp @Validated để chỉ định validation group.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.validation.annotation.Validated;

public interface CreateChecks {
}

public interface UpdateChecks {
}

public record BookInput(
        @NotBlank(groups = {CreateChecks.class, UpdateChecks.class})
        String title,

        @NotBlank(groups = CreateChecks.class)
        String isbn) {
}
~~~

Resolver có thể chọn group phù hợp:

~~~java
@MutationMapping
public Book createBook(
        @Argument @Validated(CreateChecks.class) BookInput input) {
    return bookService.create(input);
}
~~~

Hãy cấu hình và kiểm thử validation group theo phiên bản Spring for GraphQL và Jakarta Validation provider đang dùng. Nếu không cần group, @Valid là cách khai báo đơn giản và dễ hiểu.

## ConstraintViolationException chứa thông tin gì?

ConstraintViolationException cung cấp tập hợp ConstraintViolation. Mỗi violation mô tả một constraint không được thỏa mãn, thường bao gồm:

- propertyPath: đường dẫn tới property hoặc tham số bị lỗi.
- message: thông báo validation đã được resolve.
- messageTemplate: template message trước khi nội suy.
- invalidValue: giá trị không hợp lệ.
- rootBeanClass: kiểu bean được validation.
- constraintDescriptor: metadata của constraint.

Có thể đọc các violation trong Java:

~~~java
catch (ConstraintViolationException exception) {
    for (ConstraintViolation<?> violation
            : exception.getConstraintViolations()) {
        String field = violation.getPropertyPath().toString();
        String message = violation.getMessage();
        // Ghi nhận field và message theo chính sách logging
    }
}
~~~

Trong xử lý GraphQL, không nên gửi nguyên invalidValue về client. Giá trị này có thể chứa email, số điện thoại, token hoặc dữ liệu nhạy cảm. Thông thường chỉ cần trả field path đã chuẩn hóa và message phù hợp.

## Chuyển ConstraintViolationException thành GraphQL error

Spring for GraphQL cung cấp @GraphQlExceptionHandler cho annotated controller. Handler có thể nằm trong chính controller để xử lý exception từ các resolver trong controller đó, hoặc đặt trong @ControllerAdvice để dùng chung cho nhiều controller.

Ví dụ global handler:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.List;
import java.util.Map;

@ControllerAdvice
public class GraphQlValidationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(this::toClientViolation)
                        .toList();

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ")
                .extensions(Map.of("violations", violations))
                .build();
    }

    private Map<String, String> toClientViolation(
            ConstraintViolation<?> violation) {
        return Map.of(
                "field", violation.getPropertyPath().toString(),
                "message", violation.getMessage());
    }
}
~~~

GraphqlErrorBuilder được Spring chuẩn bị theo DataFetchingEnvironment hiện tại. Vì vậy, error có thể mang field path và location tương ứng với resolver gây ra lỗi. ErrorType.BAD_REQUEST phân loại lỗi ở tầng GraphQL; nó không có nghĩa mọi transport HTTP bắt buộc phải trả status 400.

Ví dụ response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Dữ liệu đầu vào không hợp lệ",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "violations": [
          {
            "field": "createBook.input.title",
            "message": "Tiêu đề không được để trống"
          },
          {
            "field": "createBook.input.isbn",
            "message": "ISBN không đúng định dạng"
          }
        ]
      }
    }
  ]
}
~~~

Đường dẫn propertyPath cụ thể phụ thuộc cách controller parameter và input object được bind. Nếu muốn response ổn định cho frontend, nên chuẩn hóa tên field thành đường dẫn input công khai thay vì cam kết rằng propertyPath nội bộ luôn có cùng định dạng.

## Phân biệt lỗi validation và lỗi binding

GraphQlArgumentBinder có thể phát sinh BindException khi không thể tạo hoặc điền giá trị vào Java object. Bean Validation phát sinh ConstraintViolationException khi object đã được bind nhưng không thỏa constraint.

Ví dụ:

- Client gửi publishedYear là chuỗi không chuyển được thành Int: GraphQL coercion error.
- GraphQL input hợp lệ nhưng Java constructor không thể bind property: argument binding error.
- Java object đã được tạo nhưng title rỗng: ConstraintViolationException.
- Title hợp lệ nhưng ISBN đã được một quyển sách khác sử dụng: domain exception hoặc lỗi persistence tùy thiết kế.

Không nên dùng một handler cho mọi exception rồi trả cùng một thông báo. BindException có thể cần trả lỗi cấu trúc input; ConstraintViolationException cần trả danh sách constraint; domain exception cần phân loại theo quy tắc nghiệp vụ.

## Xử lý lỗi khi không dùng annotated controller

@GraphQlExceptionHandler áp dụng cho exception từ annotated controller methods. Nếu exception đến từ một DataFetcher được đăng ký trực tiếp hoặc từ một thành phần khác không chạy qua annotated controller, có thể dùng DataFetcherExceptionResolver.

Ví dụ:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class ValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected List<GraphQLError> resolveToMultipleErrors(
            Throwable exception,
            graphql.schema.DataFetchingEnvironment environment) {

        if (!(exception instanceof ConstraintViolationException violationException)) {
            return null;
        }

        List<GraphQLError> errors =
                violationException.getConstraintViolations().stream()
                        .map(violation -> GraphqlErrorBuilder.newError(environment)
                                .errorType(ErrorType.BAD_REQUEST)
                                .message(violation.getMessage())
                                .build())
                        .toList();

        return errors;
    }
}
~~~

Resolver trả null khi không xử lý exception để resolver tiếp theo trong chain có cơ hội xử lý. Nếu đã nhận trách nhiệm, trả danh sách GraphQLError. Spring Boot tự phát hiện bean DataFetcherExceptionResolver và đăng ký với GraphQlSource.

Chọn một nơi xử lý rõ ràng cho mỗi exception. Tránh tạo nhiều handler cùng bắt ConstraintViolationException nhưng trả các thông báo hoặc cấu trúc extensions khác nhau.

## Partial data và null propagation

GraphQL cho phép response có cả data và errors. Khi một field resolver thất bại do validation, các field khác trong cùng operation có thể vẫn trả dữ liệu. Tuy nhiên, giá trị null tại field lỗi sẽ tuân theo nullability của schema.

Ví dụ:

~~~graphql
type Query {
  profile: Profile
  searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

Nếu searchBooks phát sinh validation error, field này được xem là null. Vì schema khai báo [Book!]! là non-null, null có thể lan lên Query root và làm data trở thành null. Nếu field được khai báo nullable, các field sibling như profile vẫn có thể trả kết quả.

Do đó, thiết kế nullability ảnh hưởng trực tiếp tới phạm vi dữ liệu còn lại khi một resolver lỗi. Hãy cân nhắc việc một field có thực sự bắt buộc non-null trong mọi tình huống hay không.

## Validation trong service và domain

Bean Validation tại controller rất hữu ích để phản hồi sớm với input sai. Tuy nhiên, service có thể được gọi từ REST endpoint, message consumer, scheduler hoặc test mà không đi qua GraphQL controller. Vì vậy, các invariant quan trọng của nghiệp vụ không nên chỉ tồn tại ở GraphQL resolver.

Có thể phân chia trách nhiệm:

- GraphQL SDL kiểm tra kiểu, nullability và cấu trúc operation.
- Bean Validation kiểm tra định dạng và giới hạn dữ liệu đầu vào.
- Service/domain kiểm tra quy tắc nghiệp vụ phụ thuộc trạng thái hiện tại.
- Database constraint bảo vệ tính toàn vẹn cuối cùng như unique key, foreign key và not-null.

Ví dụ, @Size(max = 150) có thể giới hạn độ dài title, nhưng chỉ database mới bảo đảm unique ISBN khi nhiều request chạy đồng thời. Service có thể kiểm tra ISBN đã tồn tại để trả thông báo dễ hiểu, nhưng unique constraint vẫn cần có để ngăn race condition.

## Message localization và thông báo cho client

Constraint message có thể được khai báo trực tiếp:

~~~java
@NotBlank(message = "Tiêu đề không được để trống")
String title
~~~

Hoặc lấy từ Validation MessageSource:

~~~java
@NotBlank(message = "{book.title.required}")
String title
~~~

File ValidationMessages.properties:

~~~properties
book.title.required=Book title is required
book.isbn.invalid=ISBN format is invalid
~~~

Khi ứng dụng hỗ trợ nhiều ngôn ngữ, message interpolation có thể dựa trên locale của validation context. Hãy xác định cách locale được truyền từ GraphQL request tới validator nếu cần trả message theo ngôn ngữ client.

Thông báo gửi client nên ngắn gọn, có thể hành động và không chứa tên class nội bộ, câu SQL, stack trace hoặc giá trị bí mật. Có thể ghi đầy đủ exception ở server log với correlation ID để phục vụ chẩn đoán, nhưng không trả toàn bộ chi tiết đó trong GraphQL response.

## Kiểm thử ConstraintViolationException

Spring for GraphQL cung cấp GraphQlTester để kiểm thử mutation và GraphQL errors. Ví dụ input hợp lệ:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL",
            "isbn", "978-1234567890",
            "publishedYear", 2025))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

Với input không hợp lệ:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
            }
        }
        """)
    .variable("input", Map.of(
            "title", " ",
            "isbn", "invalid",
            "publishedYear", 2200))
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .contains("Dữ liệu đầu vào không hợp lệ");
        assertThat(errors.get(0).getExtensions())
                .containsKey("violations");
    });
~~~

Nên kiểm thử:

- Input hợp lệ được chuyển vào resolver.
- Mỗi constraint bị vi phạm tạo thông tin lỗi phù hợp.
- Nhiều constraint cùng thất bại được trả về theo cấu trúc nhất quán.
- Nested object và collection được cascade validation.
- Validation group chạy đúng theo use case.
- Exception handler không trả invalidValue hoặc dữ liệu nhạy cảm.
- Service không được gọi khi validation thất bại.
- Lỗi domain được phân biệt với lỗi constraint.
- Null propagation phù hợp với SDL.

Ngoài GraphQlTester, có thể kiểm thử DTO trực tiếp bằng Validator để xác minh constraint độc lập với GraphQL. Integration test vẫn cần thiết để xác nhận Spring for GraphQL thực sự kích hoạt validation và exception handler được đăng ký.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @Valid không tạo lỗi validation | Chưa có Validator bean hoặc thiếu validation provider | Thêm starter validation và kiểm tra cấu hình Validator |
| ConstraintViolationException không được chuyển thành lỗi mong muốn | Chưa đăng ký @GraphQlExceptionHandler hoặc DataFetcherExceptionResolver phù hợp | Kiểm tra phạm vi handler và exception chain |
| Input sai nhưng service vẫn chạy | Validation chưa được kích hoạt trên tham số | Kiểm tra @Valid/@Validated và controller configurer |
| Không kiểm tra object lồng nhau | Thiếu @Valid trên property hoặc phần tử collection | Thêm cascade validation |
| Null vẫn lọt qua @Min | @Min không thay thế @NotNull | Kết hợp @NotNull nếu field bắt buộc |
| Lỗi trả lộ dữ liệu đầu vào | Đưa invalidValue hoặc toàn bộ exception vào extensions | Chỉ trả field path và message đã chọn lọc |
| Handler không bắt được lỗi từ custom DataFetcher | @GraphQlExceptionHandler chỉ gắn với annotated controller flow | Đăng ký DataFetcherExceptionResolver |
| Frontend không biết field nào sai | Chỉ trả một message tổng quát | Thêm danh sách violations trong extensions |
| Data bị null ngoài dự kiến | Non-null propagation từ field lỗi | Rà soát nullability của field và parent |

## Nguyên tắc xử lý ConstraintViolationException

Khi triển khai validation cho Spring for GraphQL, hãy nhớ:

1. **Kích hoạt Bean Validation đúng cách.** Có Validator bean và provider tương thích Jakarta Validation.
2. **Đặt constraint trên DTO.** Dùng @Valid ở tham số resolver để kiểm tra input trước khi gọi phương thức.
3. **Dùng cascade validation.** Đánh dấu @Valid cho object lồng nhau và phần tử collection cần kiểm tra.
4. **Phân biệt nguồn lỗi.** Coercion, binding, constraint và domain exception cần cách xử lý phù hợp.
5. **Chuyển exception thành GraphQL errors.** Dùng @GraphQlExceptionHandler cho annotated controller hoặc DataFetcherExceptionResolver cho data fetcher tổng quát.
6. **Trả thông tin lỗi an toàn.** Không đưa invalidValue, token, stack trace hoặc chi tiết nội bộ vào response.
7. **Giữ invariant ở domain và database.** Validation tại GraphQL không thay thế kiểm tra nghiệp vụ ở các entry point khác.
8. **Kiểm thử cả response và side effect.** Xác nhận resolver/service không thực thi khi input không hợp lệ.
9. **Thiết kế nullability có chủ đích.** Một validation error có thể kích hoạt null propagation lên field cha.

ConstraintViolationException biểu diễn việc một hoặc nhiều quy tắc Bean Validation không được thỏa mãn. Trong Spring for GraphQL, exception thường phát sinh khi tham số controller có @Valid được kiểm tra trước khi resolver chạy. Dùng @GraphQlExceptionHandler hoặc DataFetcherExceptionResolver để chuyển violation thành GraphQL errors có cấu trúc, phân biệt với lỗi coercion, binding và domain; đồng thời giữ thông tin trả về ở mức an toàn. Cách tổ chức này giúp client biết input nào cần sửa mà vẫn bảo vệ được dữ liệu và tính nhất quán của hệ thống.

## Tài liệu tham khảo

- [Spring for GraphQL - Annotated Controllers: Validation và Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution và Exception Resolution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework - Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
