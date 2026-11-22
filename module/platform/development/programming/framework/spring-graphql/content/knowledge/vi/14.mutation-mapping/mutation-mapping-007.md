# Mutation validation

## 1. Vì sao Mutation cần validation?

Mutation thay đổi trạng thái của hệ thống: tạo sách, cập nhật hồ sơ, đặt hàng hoặc hủy giao dịch. Một input không hợp lệ có thể làm dữ liệu sai, vi phạm quy tắc nghiệp vụ hoặc tạo ra trạng thái mà những phần khác của hệ thống không xử lý được.

Trong GraphQL, schema đã kiểm tra cấu trúc và kiểu dữ liệu của operation. Tuy nhiên, một giá trị đúng kiểu GraphQL chưa chắc hợp lệ với nghiệp vụ. Ví dụ, `title: String!` bảo đảm client truyền một chuỗi khác `null`, nhưng không bảo đảm chuỗi đó có nội dung, không quá dài hoặc không trùng với sách đã tồn tại.

Với Spring for GraphQL, validation của Mutation nên được tổ chức theo nhiều lớp: GraphQL kiểm tra hợp đồng operation, Bean Validation kiểm tra input DTO, service kiểm tra quy tắc nghiệp vụ và database giữ các ràng buộc cuối cùng. Mỗi lớp giải quyết một loại lỗi khác nhau.

## 2. Phân biệt các lớp validation

| Lớp | Kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| Parse và validation GraphQL | Cú pháp operation, tên field, argument, selection set và kiểu theo schema | Field không tồn tại, thiếu argument bắt buộc |
| Scalar coercion | Giá trị biến hoặc literal có chuyển được sang scalar đã khai báo không | Truyền chuỗi vào argument `Int!` |
| Bean Validation | Ràng buộc dữ liệu trên input DTO | Chuỗi không được để trống, số trang phải dương |
| Business validation | Quy tắc phụ thuộc dữ liệu và trạng thái nghiệp vụ | Tác giả không tồn tại, sách đã có ISBN, đơn hàng không thể hủy |
| Database constraint | Tính toàn vẹn dữ liệu khi ghi | Unique key, foreign key, not-null constraint |

GraphQL validation và scalar coercion diễn ra trước khi resolver Mutation được gọi. Bean Validation thường được thực hiện sau khi Spring for GraphQL bind argument thành Java object. Business validation được thực hiện trong service hoặc domain layer. Database constraint vẫn cần thiết vì hai request đồng thời có thể cùng vượt qua bước kiểm tra nghiệp vụ trước khi ghi dữ liệu.

Không nên cố đưa mọi quy tắc vào SDL. Schema diễn tả kiểu, nullability và cấu trúc input; các quy tắc như độ dài tối đa, định dạng đặc biệt, tính duy nhất hoặc chuyển trạng thái thường cần được kiểm tra ở Java và database.

## 3. Khai báo input cho Mutation

Nên gom dữ liệu đầu vào của một thao tác tạo mới vào `input object`. Ví dụ chức năng tạo sách:

```graphql
input CreateBookInput {
    title: String!
    isbn: String!
    authorId: ID!
    pageCount: Int!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Book {
    id: ID!
    title: String!
    isbn: String!
    pageCount: Int!
}
```

Schema quy định `input`, `title`, `isbn`, `authorId` và `pageCount` phải được cung cấp với giá trị khác `null`. `Int!` cũng yêu cầu giá trị thuộc miền số nguyên 32-bit của GraphQL. Những quy tắc như `title` không được chỉ chứa khoảng trắng hoặc `pageCount` phải lớn hơn 0 cần validation bổ sung.

Client gửi Mutation:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
        pageCount
    }
}
```

Variables:

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "isbn": "9780000000042",
    "authorId": "author-7",
    "pageCount": 320
  }
}
```

Nếu client bỏ `title` hoặc gửi `null` cho field `title: String!`, GraphQL từ chối request theo schema. Nếu gửi `pageCount` là một chuỗi, scalar coercion cũng từ chối trước khi resolver thực thi.

## 4. Thêm Bean Validation vào dự án

Với Spring Boot, thêm starter validation để kích hoạt tích hợp Jakarta Bean Validation. Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Các ví dụ dưới đây dùng `jakarta.validation.*`, phù hợp với Spring Boot 3 trở lên. Dự án Spring Boot 2 sử dụng namespace `javax.validation.*`; cần chọn package theo phiên bản Spring đang dùng và không trộn hai namespace trong cùng một ứng dụng.

## 5. Đặt constraint trên input DTO

Tạo Java record tương ứng với `CreateBookInput`:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateBookInput(
    @NotBlank(message = "Tiêu đề không được để trống")
    @Size(max = 200, message = "Tiêu đề không được vượt quá 200 ký tự")
    String title,

    @NotBlank(message = "ISBN không được để trống")
    @Pattern(
        regexp = "[0-9-]{10,17}",
        message = "ISBN phải có từ 10 đến 17 chữ số hoặc dấu gạch nối"
    )
    String isbn,

    @NotBlank(message = "Mã tác giả không được để trống")
    String authorId,

    @NotNull(message = "Số trang là bắt buộc")
    @Min(value = 1, message = "Số trang phải lớn hơn 0")
    @Max(value = 10000, message = "Số trang không được vượt quá 10000")
    Integer pageCount
) {
}
```

Các annotation thường dùng:

| Constraint | Mục đích |
| --- | --- |
| `@NotNull` | Giá trị không được là `null` |
| `@NotBlank` | Chuỗi phải khác `null` và có ít nhất một ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi hoặc collection không được rỗng |
| `@Size(min, max)` | Giới hạn độ dài chuỗi hoặc số phần tử collection |
| `@Min`, `@Max` | Giới hạn giá trị số |
| `@Positive`, `@PositiveOrZero` | Kiểm tra số dương hoặc không âm |
| `@Pattern` | Kiểm tra chuỗi theo regular expression |
| `@Email` | Kiểm tra chuỗi theo quy tắc email của provider |

Nên dùng wrapper như `Integer` cho giá trị có thể thiếu để `@NotNull` phát hiện trường hợp null. Java primitive như `int` không biểu diễn được null. Tuy nhiên, nếu SDL đã khai báo `Int!`, GraphQL đã chặn giá trị null trước khi Bean Validation chạy; `@NotNull` vẫn có ích khi DTO được sử dụng từ những luồng khác hoặc khi muốn giữ ràng buộc rõ ràng ở Java.

Regular expression ISBN trong ví dụ chỉ minh họa định dạng đầu vào đơn giản. Nếu cần kiểm tra ISBN-10 hoặc ISBN-13 theo checksum, hãy dùng validator chuyên biệt thay vì coi biểu thức này là kiểm tra ISBN đầy đủ.

## 6. Kích hoạt validation với `@Valid` trong `@MutationMapping`

Spring for GraphQL hỗ trợ validation trên argument được bind vào controller. Đặt `@Valid` trên tham số `@Argument` để yêu cầu Bean Validation kiểm tra DTO trước khi gọi logic Mutation:

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
    public Book createBook(@Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Khi DTO vi phạm constraint, Spring for GraphQL không tiếp tục gọi phương thức Mutation như một lần tạo mới thành công. Validation exception được chuyển vào cơ chế xử lý lỗi GraphQL. Cần quyết định cách trình bày lỗi cho client, chẳng hạn ánh xạ thành GraphQL error có mã và danh sách field lỗi, hoặc chủ động trả một payload có cấu trúc validation error.

`@Valid` kích hoạt kiểm tra constraint trên object được bind. Với object lồng nhau, cần đặt `@Valid` trên thuộc tính con để cascade validation xuống object đó.

## 7. Validation cho input lồng nhau và danh sách

Mutation có thể nhận cấu trúc phức tạp, ví dụ tạo sách kèm các chương. Schema:

```graphql
input ChapterInput {
    title: String!
    sequence: Int!
}

input CreateBookWithChaptersInput {
    title: String!
    chapters: [ChapterInput!]!
}

type Mutation {
    createBookWithChapters(input: CreateBookWithChaptersInput!): Book!
}
```

DTO Java:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record ChapterInput(
    @NotBlank(message = "Tên chương không được để trống")
    @Size(max = 150, message = "Tên chương không được vượt quá 150 ký tự")
    String title,

    @NotNull
    @Positive(message = "Thứ tự chương phải lớn hơn 0")
    Integer sequence
) {
}

public record CreateBookWithChaptersInput(
    @NotBlank
    @Size(max = 200)
    String title,

    @NotEmpty(message = "Sách phải có ít nhất một chương")
    List<@NotNull @Valid ChapterInput> chapters
) {
}
```

`@Valid` trên phần tử list yêu cầu validation đi tiếp vào từng `ChapterInput`. `@NotEmpty` kiểm tra danh sách phải có ít nhất một phần tử. `@NotNull` trên phần tử ngăn một phần tử null lọt vào DTO trong những luồng binding có thể tạo ra giá trị đó.

Nếu chỉ đặt `@Valid` ở tham số Mutation mà không cascade validation cho thuộc tính lồng nhau, các constraint bên trong object con có thể không được kiểm tra như mong muốn. Hãy kiểm thử cả phần tử đầu, phần tử cuối và danh sách rỗng.

## 8. Business validation trong service hoặc domain layer

Bean Validation phù hợp với các ràng buộc trên một object đầu vào: không rỗng, độ dài, miền số hoặc định dạng. Những quy tắc phụ thuộc dữ liệu hiện tại phải được kiểm tra trong service hoặc domain layer.

Ví dụ khi tạo sách:

- Tác giả có tồn tại hay không.
- ISBN đã được dùng cho sách khác hay chưa.
- Người dùng hiện tại có quyền tạo sách trong thư viện này không.
- Thư viện có đang cho phép nhận sách mới không.

Service minh họa:

```java
public Book create(CreateBookInput input) {
    Author author = authorRepository.findById(input.authorId())
        .orElseThrow(() -> new AuthorNotFoundException(input.authorId()));

    if (bookRepository.existsByIsbn(input.isbn())) {
        throw new DuplicateIsbnException(input.isbn());
    }

    Book book = Book.create(
        input.title().trim(),
        input.isbn(),
        author,
        input.pageCount()
    );

    return bookRepository.save(book);
}
```

Ví dụ giả định domain exception được định nghĩa trong ứng dụng. Việc kiểm tra ISBN trước khi lưu cải thiện thông báo nghiệp vụ, nhưng không thay thế unique constraint ở database. Hai request đồng thời vẫn có thể cùng kiểm tra thấy ISBN chưa tồn tại; database phải là nơi bảo đảm tính duy nhất cuối cùng.

Với thao tác thay đổi nhiều bảng hoặc nhiều aggregate, hãy đặt ranh giới transaction trong service. Nếu một bước validation hoặc persistence thất bại, dữ liệu phải được rollback theo chính sách transaction của nghiệp vụ.

## 9. Chọn cách trả validation error cho client

Có hai cách phổ biến để biểu diễn lỗi validation trong GraphQL. Cần chọn theo hợp đồng API và trải nghiệm client.

### Cách A: Trả GraphQL errors

Đây là lựa chọn phù hợp khi validation exception được xử lý như lỗi của lần thực thi field. Response có thể chứa `data` và `errors`, ví dụ:

```json
{
  "data": null,
  "errors": [
    {
      "message": "Dữ liệu đầu vào không hợp lệ",
      "path": ["createBook"],
      "extensions": {
        "code": "BAD_REQUEST",
        "fieldErrors": [
          {
            "field": "title",
            "message": "Tiêu đề không được để trống"
          }
        ]
      }
    }
  ]
}
```

Trong ví dụ, field `createBook` được khai báo non-null (`Book!`). Khi resolver phát sinh lỗi, null propagation đẩy giá trị null lên root nên `data` là `null`. Nếu field trả về kiểu nullable `Book`, response có thể giữ object `data` và đặt riêng `createBook` thành `null`.

Client đọc `errors` và `extensions` để hiển thị lỗi theo field. Không nên phụ thuộc hoàn toàn vào HTTP status code; GraphQL response có quy tắc riêng và client cần đọc nội dung `data` cùng `errors`.

### Cách B: Trả typed payload

Nếu lỗi nghiệp vụ là kết quả dự kiến mà client cần xử lý như một nhánh bình thường, có thể đưa validation errors vào kiểu output:

```graphql
type ValidationError {
    field: String!
    message: String!
}

type CreateBookPayload {
    book: Book
    validationErrors: [ValidationError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Resolver có thể gọi `Validator` để lấy các constraint violation rồi chuyển thành `ValidationError`:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.List;

public CreateBookPayload createBook(CreateBookInput input) {
    var violations = validator.validate(input);

    if (!violations.isEmpty()) {
        List<ValidationError> errors = violations.stream()
            .map(violation -> new ValidationError(
                violation.getPropertyPath().toString(),
                violation.getMessage()
            ))
            .toList();

        return new CreateBookPayload(null, errors);
    }

    Book book = bookService.create(input);
    return new CreateBookPayload(book, List.of());
}
```

Ví dụ giả định `Validator`, `ValidationError` và `CreateBookPayload` đã được inject hoặc định nghĩa tương ứng. Với cách này, không đặt `@Valid` trên tham số nếu muốn tự nhận kết quả từ `Validator` và đóng gói thành payload; nếu `@Valid` ném exception trước khi phương thức được gọi thì nhánh xử lý thủ công sẽ không chạy.

Typed payload giúp client phân biệt rõ kết quả thành công và lỗi validation dự kiến. Tuy nhiên, cần thống nhất quy ước: khi có `validationErrors`, `book` là null; khi thành công, `validationErrors` là danh sách rỗng. Lỗi hệ thống bất ngờ vẫn nên đi qua GraphQL `errors`, không giả dạng thành lỗi validation.

## 10. Ánh xạ validation exception thành GraphQL error

Nếu chọn cách A, có thể xử lý `MethodArgumentNotValidException` bằng `@GraphQlExceptionHandler` trong controller hoặc một `@ControllerAdvice` dành cho GraphQL.

Ví dụ handler cục bộ:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import java.util.List;
import java.util.Map;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.MethodArgumentNotValidException;

@GraphQlExceptionHandler
public GraphQLError handleValidation(
        MethodArgumentNotValidException exception,
        DataFetchingEnvironment environment) {

    List<Map<String, String>> fieldErrors = exception.getBindingResult()
        .getFieldErrors()
        .stream()
        .map(error -> Map.of(
            "field", error.getField(),
            "message", error.getDefaultMessage() == null
                ? "Giá trị không hợp lệ"
                : error.getDefaultMessage()
        ))
        .toList();

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.BAD_REQUEST)
        .message("Dữ liệu đầu vào không hợp lệ")
        .extensions(Map.of("fieldErrors", fieldErrors))
        .build();
}
```

Đoạn mã minh họa việc chuyển các field error thành extension có cấu trúc. Hãy xác nhận exception thực tế từ phiên bản Spring for GraphQL đang dùng và điều chỉnh handler cho đúng loại exception mà argument validation phát sinh. Có thể xử lý thêm các domain exception như `DuplicateIsbnException` hoặc `AuthorNotFoundException` bằng handler riêng.

Chỉ đưa thông tin hữu ích và an toàn vào response. Không trả stack trace, câu SQL, tên bảng, thông tin kết nối hoặc nội dung nhạy cảm trong input. Chi tiết kỹ thuật nên được ghi ở log nội bộ với correlation ID.

## 11. Kiểm thử validation của Mutation bằng `GraphQlTester`

Nên kiểm tra cả operation sai schema, input sai constraint, business rule thất bại và trường hợp thành công. Ví dụ kiểm thử Bean Validation với GraphQlTester:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class CreateBookMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsBlankTitle() {
        graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
            .variable("input", Map.of(
                "title", "   ",
                "isbn", "9780000000042",
                "authorId", "author-7",
                "pageCount", 320
            ))
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                    .contains("Dữ liệu đầu vào không hợp lệ")
            ));
    }
}
```

Ví dụ giả định handler ánh xạ validation exception thành message như phần trước và test context đã cấu hình service cần thiết. Với API typed payload, thay vì kiểm tra `errors`, hãy kiểm tra `validationErrors` chứa field và message mong đợi.

Các ca kiểm thử quan trọng:

- Thiếu input bắt buộc hoặc gửi sai scalar type: GraphQL từ chối trước khi gọi resolver.
- Chuỗi rỗng hoặc chỉ có khoảng trắng: Bean Validation từ chối.
- Giá trị vượt giới hạn: Bean Validation từ chối.
- Input object lồng nhau hoặc list có phần tử không hợp lệ: cascade validation phát hiện lỗi.
- Tác giả không tồn tại hoặc ISBN đã dùng: business validation trả kết quả lỗi phù hợp.
- Hai request tạo cùng định danh: database constraint vẫn bảo vệ tính toàn vẹn.
- Input hợp lệ: Mutation gọi service và trả dữ liệu đúng.
- Validation thất bại: xác nhận không có bản ghi mới được tạo.

Không chỉ kiểm tra message. Nên kiểm tra cả error path, extension code hoặc `fieldErrors`, đồng thời xác nhận service/repository không thực hiện ghi dữ liệu khi input không hợp lệ.

## 12. Lỗi thường gặp khi validation Mutation

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@Valid` không phát hiện constraint | Thiếu `spring-boot-starter-validation` hoặc thiếu annotation `@Valid` trên argument | Kiểm tra dependency, provider và vị trí `@Valid` |
| Chuỗi chỉ có khoảng trắng vẫn hợp lệ | Dùng `@NotNull` hoặc `@NotEmpty` thay vì `@NotBlank` | Dùng `@NotBlank` cho chuỗi cần nội dung |
| Constraint của object lồng nhau không chạy | Thiếu cascade `@Valid` trên thuộc tính hoặc phần tử | Thêm `@Valid` đúng vị trí và kiểm thử nested input |
| Giá trị sai kiểu không đến được resolver | GraphQL scalar coercion từ chối trước khi gọi method | Kiểm tra SDL, scalar và kiểu variable |
| Kiểm tra unique vẫn tạo bản ghi trùng khi tải cao | Chỉ kiểm tra bằng truy vấn `exists` trước khi save | Bổ sung unique constraint ở database và ánh xạ lỗi constraint |
| Validation exception trả lỗi chung khó hiểu | Chưa ánh xạ field errors hoặc chưa chuẩn hóa error code | Dùng `@GraphQlExceptionHandler` hoặc typed payload |
| Client không hiển thị lỗi theo field | Không đọc `errors.extensions` hoặc `validationErrors` | Chuẩn hóa response contract và cập nhật client |
| Thông báo lỗi làm lộ dữ liệu nội bộ | Trả nguyên exception hoặc chi tiết persistence | Chỉ trả message an toàn; ghi chi tiết trong log |
| Resolver vừa tự validate vừa bị `@Valid` chặn | Trộn hai chiến lược exception-based và typed payload | Chọn một luồng validation rõ ràng cho từng Mutation |

## 13. Checklist thiết kế Mutation validation

- [ ] Input object trong SDL thể hiện đúng cấu trúc và nullability.
- [ ] Scalar coercion và GraphQL document validation được hiểu là lớp kiểm tra đầu tiên.
- [ ] DTO Java có constraint phù hợp với quy tắc dữ liệu.
- [ ] `spring-boot-starter-validation` đã được thêm khi dùng Bean Validation.
- [ ] `@Valid` được đặt trên `@Argument` hoặc validation được gọi chủ động.
- [ ] Object lồng nhau và phần tử collection có cascade validation khi cần.
- [ ] Business rule được kiểm tra trong service/domain layer.
- [ ] Database có unique, foreign key và constraint cần thiết để bảo vệ dữ liệu.
- [ ] Đã chọn GraphQL errors hoặc typed payload cho validation error và thống nhất contract.
- [ ] Error response không chứa stack trace hoặc thông tin nội bộ.
- [ ] Có kiểm thử input sai, business rule sai, thành công và tính toàn vẹn dữ liệu.

## Kết luận

Mutation validation cần phối hợp nhiều lớp. GraphQL kiểm tra operation và scalar theo schema; Bean Validation kiểm tra các ràng buộc trên input DTO; service/domain layer kiểm tra quy tắc nghiệp vụ; database bảo vệ tính toàn vẹn khi dữ liệu được ghi đồng thời.

Trong Spring for GraphQL, có thể dùng `@Valid` trên tham số `@Argument` của `@MutationMapping` để kích hoạt Bean Validation. Sau đó, chọn cách trình bày lỗi phù hợp: ánh xạ exception thành GraphQL error có `extensions` hoặc trả typed payload cho các lỗi nghiệp vụ dự kiến. Khi response được chuẩn hóa và có kiểm thử bằng `GraphQlTester`, client có thể hiển thị lỗi chính xác và server tránh ghi dữ liệu không hợp lệ.
