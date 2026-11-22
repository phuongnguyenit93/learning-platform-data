# Validation trên `@Arguments`

## 1. `@Arguments` dùng để làm gì?

Một GraphQL field có thể nhận nhiều argument độc lập, chẳng hạn từ khóa tìm kiếm, mã tác giả, khoảng số trang và trạng thái phát hành. Khi dùng `@Argument`, controller nhận từng argument riêng hoặc nhận một object từ một argument có cấu trúc. Khi muốn gom **toàn bộ argument của field hiện tại** vào một Java object, Spring for GraphQL cung cấp annotation `@Arguments`.

Ví dụ, schema có field:

```graphql
type Query {
    searchBooks(
        keyword: String!
        authorId: ID
        minPages: Int
        maxPages: Int
    ): [Book!]!
}
```

Phương thức có thể nhận toàn bộ bốn argument vào một DTO:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

`@Arguments` lấy map argument của field `searchBooks` và bind các giá trị cấp cao nhất vào thuộc tính tương ứng của `SearchBooksArguments`. Nhờ đó, chữ ký resolver gọn hơn khi field có nhiều tiêu chí lọc và dễ áp dụng Bean Validation trên một object có kiểu rõ ràng.

`@Arguments` chỉ đại diện cho argument của field đang được phân giải. Nó không lấy toàn bộ variables của operation, không bao gồm selection set và cũng không tự đọc các argument của field cha hoặc field con khác.

## 2. Phân biệt `@Arguments` và `@Argument`

Hai annotation có mục đích khác nhau:

| Cách khai báo | Dữ liệu được bind |
| --- | --- |
| `@Argument SearchBooksInput input` | Giá trị của một argument có tên `input` thành object `SearchBooksInput` |
| `@Argument("keyword") String keyword` | Giá trị của riêng argument `keyword` |
| `@Arguments SearchBooksArguments arguments` | Toàn bộ argument của field thành một object `SearchBooksArguments` |
| `@Arguments Map<String, Object> arguments` | Map thô chứa toàn bộ argument của field |
| `@Argument Map<String, Object> filter` | Giá trị thô của một argument có tên `filter` |

Ví dụ hai schema có cấu trúc khác nhau:

**Một argument input object:**

```graphql
input BookSearchInput {
    keyword: String!
    authorId: ID
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
```

Resolver dùng `@Argument`:

```java
@QueryMapping
public List<Book> searchBooks(@Argument("input") BookSearchInput input) {
    return bookQueryService.search(input);
}
```

**Nhiều argument ở cấp field:**

```graphql
type Query {
    searchBooks(keyword: String!, authorId: ID): [Book!]!
}
```

Resolver dùng `@Arguments`:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Không dùng `@Arguments` để bind một argument tên `input`. Với cấu trúc đó, hãy dùng `@Argument("input")`. Ngược lại, nếu schema khai báo nhiều argument riêng ở cấp field, `@Arguments` giúp gom chúng vào một object.

## 3. Cách Spring bind toàn bộ arguments vào DTO

Spring for GraphQL sử dụng `GraphQlArgumentBinder` để tạo và điền dữ liệu vào method parameter. Khi parameter được đánh dấu `@Arguments`, binder lấy toàn bộ argument map của field và bind các key cấp cao nhất vào constructor hoặc thuộc tính của target object.

Ví dụ DTO dạng Java record:

```java
public record SearchBooksArguments(
    String keyword,
    String authorId,
    Integer minPages,
    Integer maxPages) {
}
```

Với operation:

```graphql
query SearchBooks(
    $keyword: String!
    $authorId: ID
    $minPages: Int
    $maxPages: Int
) {
    searchBooks(
        keyword: $keyword
        authorId: $authorId
        minPages: $minPages
        maxPages: $maxPages
    ) {
        id
        title
    }
}
```

và variables:

```json
{
  "keyword": "spring",
  "authorId": "author-7",
  "minPages": 100,
  "maxPages": 500
}
```

Binder tạo `SearchBooksArguments` với các thuộc tính tương ứng. Với Java record, Spring có thể dùng canonical constructor. Với class thông thường, binder cũng có thể dùng constructor phù hợp hoặc default constructor kết hợp setter. Việc bind object lồng nhau được thực hiện đệ quy.

Tên argument GraphQL phải khớp với tên thuộc tính hoặc constructor parameter theo quy tắc binding đang dùng. Nếu dự án có naming convention khác, có thể cấu hình `GraphQlArgumentBinder.Options` thông qua `AnnotatedControllerConfigurer`.

## 4. Khai báo constraint trên DTO dùng với `@Arguments`

Sau khi bind thành object có kiểu, có thể dùng Jakarta Bean Validation để kiểm tra các ràng buộc dữ liệu.

Ví dụ DTO tìm sách:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record SearchBooksArguments(
    @NotBlank(message = "Từ khóa tìm kiếm không được để trống")
    @Size(max = 100, message = "Từ khóa không được vượt quá 100 ký tự")
    String keyword,

    @Size(max = 64, message = "Mã tác giả không được vượt quá 64 ký tự")
    String authorId,

    @Min(value = 1, message = "Số trang tối thiểu phải lớn hơn 0")
    Integer minPages,

    @Min(value = 1, message = "Số trang tối đa phải lớn hơn 0")
    @Max(value = 10000, message = "Số trang tối đa không được vượt quá 10000")
    Integer maxPages) {
}
```

Các constraint thường dùng:

| Constraint | Mục đích |
| --- | --- |
| `@NotNull` | Giá trị không được là null |
| `@NotBlank` | Chuỗi phải có ít nhất một ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi hoặc collection không được rỗng |
| `@Size` | Giới hạn độ dài chuỗi hoặc số phần tử collection |
| `@Min`, `@Max` | Giới hạn giá trị số |
| `@Positive`, `@PositiveOrZero` | Kiểm tra số dương hoặc không âm |
| `@Pattern` | Kiểm tra chuỗi theo regular expression |
| `@Email` | Kiểm tra định dạng email theo validation provider |

Nên dùng wrapper như `Integer` khi argument có thể không được truyền hoặc có thể null. Java primitive như `int` không thể biểu diễn null. Nếu schema khai báo argument `Int!`, GraphQL đã bảo đảm argument không null trước khi resolver được gọi; Bean Validation vẫn có ích để kiểm tra miền giá trị như số phải dương.

## 5. Kích hoạt Bean Validation trên `@Arguments`

Đặt `@Valid` trên cùng method parameter với `@Arguments`:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Arguments @Valid SearchBooksArguments arguments) {
        return bookQueryService.search(arguments);
    }
}
```

Khi Spring for GraphQL phát hiện một Bean Validation `Validator` trong application context, `AnnotatedControllerConfigurer` kích hoạt validation cho annotated controller method. Nếu object vi phạm constraint, validation exception được ném trước khi phương thức resolver được gọi.

`@Valid` đánh dấu object cần kiểm tra constraint. Nó không tự tạo validator. Ứng dụng cần có Bean Validation provider và bean `Validator`, thường được cấu hình thông qua Spring Boot validation starter.

Với Spring Boot 3 trở lên, dùng namespace `jakarta.validation`. Dự án Spring Boot 2 cũ thường dùng `javax.validation`; không trộn hai namespace trong cùng cấu hình.

## 6. Thêm dependency validation

Với Spring Boot, thêm starter để có Bean Validation provider và tích hợp Spring:

Maven:

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

Spring Boot thường tự cấu hình `LocalValidatorFactoryBean` khi có dependency phù hợp. Nếu ứng dụng tự quản lý validation, cần đăng ký một bean triển khai `jakarta.validation.Validator` để `AnnotatedControllerConfigurer` phát hiện và sử dụng.

Nếu DTO có annotation nhưng không có validator provider, các constraint có thể không được thực thi. Hãy kiểm tra dependency, bean validation và cấu hình controller trước khi kết luận `@Valid` không hoạt động.

## 7. Validation các object lồng nhau

Một field có thể nhận argument chứa input object lồng nhau. `@Arguments` bind top-level arguments vào DTO; với từng thuộc tính con, cần cascade validation bằng `@Valid`.

SDL:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
}

input PageRange {
    min: Int
    max: Int
}

type Query {
    searchBooks(filter: BookFilter!, pageRange: PageRange): [Book!]!
}
```

DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record SearchBooksArguments(
    @NotNull(message = "Bộ lọc là bắt buộc")
    @Valid
    BookFilter filter,

    @Valid
    PageRange pageRange) {
}

public record BookFilter(
    @NotBlank(message = "Từ khóa không được để trống")
    String keyword,

    @Size(max = 64)
    String authorId) {
}

public record PageRange(
    @Min(1)
    Integer min,

    @Min(1)
    Integer max) {
}
```

Khi `@Valid` được đặt trên thuộc tính `filter` và `pageRange`, Bean Validation đi tiếp vào object con để kiểm tra constraint. Nếu thiếu cascade validation, các constraint bên trong object lồng nhau có thể không được chạy.

Với collection lồng nhau, dùng cascade validation cho phần tử:

```java
public record BulkSearchArguments(
    @NotEmpty
    List<@NotNull @Valid BookFilter> filters) {
}
```

`@NotEmpty` kiểm tra collection có ít nhất một phần tử; `@NotNull` và `@Valid` kiểm tra từng phần tử và các constraint bên trong phần tử đó.

## 8. Validation quy tắc liên quan giữa nhiều arguments

Một số quy tắc không thể kiểm tra độc lập trên từng field. Ví dụ `minPages` không được lớn hơn `maxPages`. Có thể kiểm tra ở cấp class bằng custom constraint hoặc một phương thức kiểm tra được Bean Validation nhận diện.

Ví dụ dùng `@AssertTrue`:

```java
import jakarta.validation.constraints.AssertTrue;

public record SearchBooksArguments(
    @NotBlank String keyword,
    Integer minPages,
    Integer maxPages) {

    @AssertTrue(message = "Số trang tối thiểu không được lớn hơn số trang tối đa")
    public boolean isPageRangeValid() {
        return minPages == null
            || maxPages == null
            || minPages <= maxPages;
    }
}
```

Quy tắc được kiểm tra trên toàn bộ object, vì nó cần đồng thời hai giá trị. Với nghiệp vụ phức tạp hơn, nên tạo custom class-level constraint gồm annotation và `ConstraintValidator` để có thể gắn lỗi vào field phù hợp.

Bean Validation chỉ xác nhận tính hợp lệ của dữ liệu đầu vào theo quy tắc đã khai báo. Các quy tắc phụ thuộc database như tác giả có tồn tại, sách có thuộc tenant hiện tại hoặc ISBN có duy nhất vẫn nên được kiểm tra ở service/domain layer và được bảo vệ bằng constraint ở database khi cần.

## 9. Dùng `@Validated` để chọn validation group

Nếu cùng một DTO được dùng cho nhiều thao tác với bộ quy tắc khác nhau, có thể khai báo validation group.

Định nghĩa group:

```java
public interface BasicSearch {
}

public interface AdvancedSearch extends BasicSearch {
}
```

Constraint theo group:

```java
public record SearchBooksArguments(
    @NotBlank(groups = BasicSearch.class)
    String keyword,

    @Size(max = 64, groups = AdvancedSearch.class)
    String authorId) {
}
```

Chọn group ở method parameter:

```java
import org.springframework.validation.annotation.Validated;

@QueryMapping
public List<Book> searchBooks(
        @Arguments @Validated(AdvancedSearch.class)
        SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Trong ví dụ, `AdvancedSearch` kế thừa `BasicSearch`, nên chọn `AdvancedSearch` cũng chạy constraint thuộc `BasicSearch`. Constraint không khai báo group thuộc `Default`; nếu cần chạy cả `Default`, hãy cho group tùy chỉnh kế thừa `Default` hoặc cấu hình group sequence phù hợp.

Không thêm validation group nếu tất cả operation dùng cùng quy tắc. Với một DTO chỉ có một mục đích, `@Valid` thường đơn giản và dễ hiểu hơn.

## 10. Dùng `@Arguments Map` và giới hạn của validation tự động

`@Arguments` cũng có thể nhận `Map<String, Object>` để lấy raw map của toàn bộ arguments:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String keyword = (String) arguments.get("keyword");
    return bookQueryService.search(keyword);
}
```

Cách này hữu ích khi cần xử lý động hoặc xây dựng một adapter chung, nhưng map thô không có cấu trúc bean và không tự mang constraint như `@NotBlank`, `@Min` hay `@Size`. Đặt `@Valid` trên `Map<String, Object>` không tự biến các key trong map thành các thuộc tính DTO có constraint.

Nếu cần validation tự động, ưu tiên typed DTO:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments @Valid SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Nếu bắt buộc phải nhận map thô, hãy chuyển đổi sang DTO có kiểu hoặc gọi `Validator` một cách tường minh sau khi tạo object phù hợp. Tránh ép kiểu trực tiếp từ map mà không kiểm tra vì lỗi kiểu có thể chỉ xuất hiện lúc runtime.

Lưu ý về phiên bản: từ Spring for GraphQL 1.2, `@Argument Map<String, Object>` lấy raw value của argument có tên tương ứng; để lấy toàn bộ map argument của field, dùng `@Arguments Map<String, Object>`.

## 11. Phân biệt GraphQL validation, binding và Bean Validation

Một request đi qua nhiều bước kiểm tra trước khi service nghiệp vụ xử lý:

| Bước | Ví dụ lỗi | Kết quả |
| --- | --- | --- |
| Parse/validation GraphQL | Field không tồn tại hoặc thiếu argument non-null | Resolver không được gọi |
| Scalar coercion | Truyền chuỗi vào argument `Int` | GraphQL từ chối input trước khi bind DTO |
| Argument binding | Giá trị không thể chuyển sang thuộc tính Java hoặc constructor không phù hợp | `BindException` với các field error |
| Bean Validation | `keyword` chỉ chứa khoảng trắng hoặc `minPages` nhỏ hơn 1 | Validation exception trước khi gọi method |
| Business validation | Tác giả không tồn tại hoặc người dùng không có quyền xem tenant | Service/domain trả lỗi nghiệp vụ |
| Database constraint | Unique key bị vi phạm bởi hai request đồng thời | Persistence exception được xử lý ở tầng ghi dữ liệu |

Các bước này có mục đích khác nhau. Ví dụ `keyword: String!` chỉ bảo đảm giá trị không null theo GraphQL; `@NotBlank` kiểm tra chuỗi có nội dung; service mới có thể kiểm tra từ khóa có khớp quy tắc tìm kiếm hoặc người dùng có quyền tìm trong phạm vi dữ liệu đó hay không.

Không dùng Bean Validation để thay thế GraphQL schema validation. Cũng không nên đưa mọi quy tắc nghiệp vụ vào constraint trên DTO nếu quy tắc đó phụ thuộc dữ liệu hoặc trạng thái hệ thống.

## 12. Xử lý lỗi binding và validation trong GraphQL response

Theo cơ chế annotated controller, nếu binding thất bại, `GraphQlArgumentBinder` ném `BindException` và tích lũy các lỗi theo đường dẫn argument. Nếu Bean Validation phát hiện constraint violation, exception validation được ném trước khi method resolver được gọi. Theo tài liệu Spring for GraphQL, trường hợp Bean Validation thường được biểu diễn bằng `ConstraintViolationException`.

Có thể chuẩn hóa lỗi bằng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice` dành cho GraphQL. Ví dụ handler:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.validation.BindException;
import java.util.List;
import java.util.Map;

@GraphQlExceptionHandler
public GraphQLError handleBindingError(
        BindException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .message("Arguments không đúng định dạng")
        .extensions(Map.of("code", "INVALID_ARGUMENTS"))
        .build();
}
```

Với `ConstraintViolationException`, có thể xây dựng handler riêng để trả mã `VALIDATION_FAILED` và danh sách lỗi field:

```java
@GraphQlExceptionHandler
public GraphQLError handleConstraintViolation(
        ConstraintViolationException exception,
        DataFetchingEnvironment environment) {

    List<Map<String, String>> violations = exception.getConstraintViolations()
        .stream()
        .map(violation -> Map.of(
            "field", violation.getPropertyPath().toString(),
            "message", violation.getMessage()
        ))
        .toList();

    return GraphqlErrorBuilder.newError(environment)
        .message("Arguments không hợp lệ")
        .extensions(Map.of(
            "code", "VALIDATION_FAILED",
            "violations", violations
        ))
        .build();
}
```

Cấu trúc response cụ thể phụ thuộc error contract của ứng dụng. Không trả stack trace, câu SQL hoặc chi tiết nội bộ trong message gửi client.

Nếu cần nhiều handler dùng chung cho các controller, dùng `@ControllerAdvice`. Nếu lỗi đến từ `DataFetcher` không phải annotated controller, cần xử lý qua `DataFetcherExceptionResolver` phù hợp.

Spring GraphQL annotated controller không sử dụng cơ chế `BindingResult` theo cách của Spring MVC để giữ lỗi ngay cạnh tham số. Hãy thiết kế exception handling trong GraphQL để chuyển lỗi thành `GraphQLError`.

## 13. Kiểm thử validation trên `@Arguments` bằng `GraphQlTester`

Kiểm thử nên gửi operation thật với nhiều top-level arguments và xác nhận resolver không chạy khi DTO vi phạm constraint.

Ví dụ schema:

```graphql
type Query {
    searchBooks(
        keyword: String!
        minPages: Int
        maxPages: Int
    ): [Book!]!
}
```

Resolver:

```java
@QueryMapping
public List<Book> searchBooks(
        @Arguments @Valid SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Test với keyword chỉ chứa khoảng trắng:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class SearchBooksValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsBlankKeyword() {
        graphQlTester.document("""
            query {
                searchBooks(keyword: "   ", minPages: 10) {
                    id
                    title
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getExtensions()).containsEntry(
                    "code", "VALIDATION_FAILED")
            ));
    }
}
```

Ví dụ giả định ứng dụng đã đăng ký handler `ConstraintViolationException` như phần trước và handler trả extension `code = VALIDATION_FAILED`. Trong test thực tế, nên kiểm tra error code và extension field errors ổn định thay vì phụ thuộc hoàn toàn vào message.

Các ca kiểm thử nên có:

- Tất cả arguments hợp lệ và resolver trả kết quả đúng.
- Thiếu argument non-null: GraphQL từ chối trước khi resolver được gọi.
- Chuỗi rỗng hoặc chỉ có khoảng trắng: Bean Validation từ chối.
- Số âm hoặc vượt giới hạn: constraint số từ chối.
- Input object lồng nhau vi phạm constraint: cascade validation phát hiện lỗi.
- Hai argument vi phạm quy tắc chéo: class-level validation phát hiện lỗi.
- Argument không thể bind sang Java type: kiểm tra BindException.
- Dùng validation group: chỉ các group đã chọn được áp dụng theo cấu hình.
- Validation thất bại: service không được gọi và không có side effect.

Có thể dùng Mockito verify để xác nhận `bookQueryService.search(...)` không được gọi trong ca validation thất bại. Điều này chứng minh validation diễn ra trước khi business method thực thi.

## 14. Lỗi thường gặp khi dùng `@Arguments`

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| DTO nhận toàn null | Tên top-level argument không khớp thuộc tính hoặc constructor parameter | Đối chiếu SDL, DTO và cấu hình name resolver |
| DTO chỉ nhận một argument | Dùng `@Argument` thay vì `@Arguments` | Dùng `@Arguments` khi cần toàn bộ map của field |
| Không bind được nested object | DTO con không có constructor/setter phù hợp hoặc kiểu không khớp | Kiểm tra constructor, setter và nested type |
| `@Valid` không chạy | Thiếu Validator bean hoặc thiếu validation provider | Thêm starter và kiểm tra `LocalValidatorFactoryBean` |
| Constraint trên object con không chạy | Thiếu `@Valid` cascade ở thuộc tính con hoặc phần tử collection | Đặt `@Valid` đúng vị trí |
| `@NotBlank` không phát hiện chuỗi khoảng trắng | Constraint không gắn trên DTO được bind hoặc validator không hoạt động | Kiểm tra binding và validation provider |
| `@Arguments Map` không phát hiện constraint | Map thô không có bean property constraints | Bind vào typed DTO hoặc validate thủ công |
| Bị nhầm BindException với validation exception | Binding và Bean Validation là hai giai đoạn khác nhau | Xử lý riêng lỗi bind và lỗi constraint |
| Validation group bỏ qua constraint mặc định | Group được chọn không bao gồm `Default` | Cho group kế thừa `Default` hoặc cấu hình group sequence |
| Client nhận lỗi kỹ thuật khó hiểu | Chưa chuẩn hóa GraphQL exception response | Dùng `@GraphQlExceptionHandler` hoặc `@ControllerAdvice` |
| Service vẫn chạy dù input sai | Không gắn `@Valid`/`@Validated` hoặc validator không được phát hiện | Kiểm thử method invocation và cấu hình validator |

## 15. Checklist triển khai validation trên `@Arguments`

- [ ] Dùng `@Arguments` khi cần bind toàn bộ top-level arguments của một field.
- [ ] Dùng `@Argument` khi chỉ cần một argument cụ thể hoặc một input object có tên.
- [ ] Dùng typed DTO thay cho raw map khi cần Bean Validation tự động.
- [ ] Tên argument GraphQL khớp với thuộc tính hoặc constructor parameter của DTO.
- [ ] Có Bean Validation provider và Validator bean.
- [ ] Đặt `@Valid` hoặc `@Validated` trên parameter `@Arguments`.
- [ ] Đặt cascade `@Valid` trên object con và collection element khi cần.
- [ ] Dùng wrapper type khi cần biểu diễn giá trị null.
- [ ] Dùng class-level constraint cho quy tắc phụ thuộc nhiều argument.
- [ ] Phân biệt GraphQL validation, binding, Bean Validation và business validation.
- [ ] Xử lý `BindException` và validation exception thành GraphQL errors phù hợp.
- [ ] Không trả thông tin nội bộ trong lỗi validation.
- [ ] Kiểm thử input hợp lệ, input sai, nested object và side effect bằng `GraphQlTester`.

## Kết luận

`@Arguments` dùng để bind toàn bộ argument của field GraphQL hiện tại vào một Java object. Khác với `@Argument`, vốn lấy một argument có tên, `@Arguments` ánh xạ các argument cấp cao nhất thành thuộc tính của DTO. Đây là lựa chọn phù hợp khi resolver có nhiều filter hoặc tham số tìm kiếm cần được gom thành một cấu trúc có kiểu.

Để validation tự động hoạt động, hãy đặt `@Valid` hoặc `@Validated` trên parameter `@Arguments`, bảo đảm ứng dụng có Bean Validation provider và khai báo constraint trên DTO. Với object lồng nhau, cần cascade bằng `@Valid`; với quy tắc liên quan nhiều thuộc tính, dùng class-level constraint. Phân biệt lỗi GraphQL schema, lỗi binding và lỗi Bean Validation để xử lý đúng, sau đó kiểm thử bằng `GraphQlTester` nhằm bảo đảm resolver không thực hiện nghiệp vụ khi arguments không hợp lệ.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: `@Arguments` and Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — `Arguments` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Arguments.html)
- [Spring for GraphQL — `GraphQlArgumentBinder` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
