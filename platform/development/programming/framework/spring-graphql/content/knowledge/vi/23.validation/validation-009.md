# Binding error theo field path

Khi một GraphQL mutation nhận input object, Spring for GraphQL phải chuyển dữ liệu GraphQL thành tham số Java của handler. Quá trình này có thể thất bại vì kiểu dữ liệu không tương thích, constructor hoặc property không bind được, hoặc dữ liệu vi phạm constraint validation. Để client biết chính xác trường nào cần sửa, server cần trả lỗi kèm **field path**.

Spring for GraphQL sử dụng **GraphQlArgumentBinder** để bind argument vào record, DTO, collection hoặc object lồng nhau. Các lỗi binding và validation được biểu diễn qua **BindingResult**, thường được bọc trong **BindException** khi không được xử lý ngay tại controller. **FieldError.getField()** cung cấp đường dẫn tới property lỗi, chẳng hạn **author.name** hoặc **chapters[0].title**.

Bài này trình bày cách tạo field path từ input object, cách xử lý BindException và Errors, cách chuyển lỗi thành GraphQL response có cấu trúc, phân biệt input field path với GraphQL response path, xử lý nested/list input, chuẩn hóa error code và kiểm thử bằng GraphQlTester.

## 1. Binding error là gì?

Giả sử schema nhận input để tạo sách:

~~~graphql
input CreateBookInput {
  title: String!
  pageCount: Int
  author: AuthorInput!
}

input AuthorInput {
  name: String!
  email: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java handler nhận một record:

~~~java
public record CreateBookInput(
        String title,
        Integer pageCount,
        AuthorInput author) {
}

public record AuthorInput(
        String name,
        String email) {
}
~~~

Client gửi input có cấu trúc lồng nhau. Spring cần tạo CreateBookInput, sau đó tạo AuthorInput và gán các giá trị tương ứng.

Binding error có thể xảy ra khi:

- Spring không thể chuyển một giá trị sang kiểu Java đích.
- Không thể tạo object qua constructor hoặc property binding.
- Cấu trúc dữ liệu không tương thích với DTO.
- Bean Validation phát hiện constraint không thỏa mãn sau khi bind.

Ví dụ, pageCount phải lớn hơn 0 nhưng client gửi giá trị âm. Hoặc một field Java có kiểu enum/custom type nhưng giá trị không thể chuyển đổi theo cấu hình hiện tại.

Binding error khác với lỗi cú pháp GraphQL hoặc lỗi nghiệp vụ. Nó liên quan đến bước chuyển input thành object Java và kiểm tra constraint của object đó.

## 2. Vị trí của binding trong GraphQL execution

Một request đi qua các bước chính:

~~~mermaid
flowchart TD
    A[GraphQL document và variables] --> B[Parse document]
    B --> C[Validate theo schema]
    C --> D[Coerce GraphQL input]
    D --> E[GraphQlArgumentBinder]
    E --> F[Java record / DTO]
    F --> G[Bean Validation]
    G --> H[Controller handler]
    H --> I[Service và domain logic]
~~~

Mỗi bước có loại lỗi riêng:

| Giai đoạn | Ví dụ lỗi | Cơ chế xử lý |
|---|---|---|
| Parse | Document thiếu dấu ngoặc | GraphQL parser |
| Schema validation | Field input không tồn tại | GraphQL validation |
| Variable coercion | Giá trị không phù hợp scalar GraphQL | GraphQL input coercion |
| Argument binding | Không tạo hoặc chuyển đổi được Java target | GraphQlArgumentBinder / BindException |
| Bean Validation | @NotBlank, @Min, @Email không đạt | BindingResult / BindException |
| Business validation | Author không tồn tại, sách đã trùng | Service/domain exception hoặc payload nghiệp vụ |

Không phải mọi input sai đều tạo BindException. Ví dụ client truyền chuỗi vào biến Int! thường bị GraphQL từ chối ở bước coercion, trước khi annotated controller được gọi. @GraphQlExceptionHandler dành cho exception phát sinh trong quá trình xử lý field; nó không thay thế parser hoặc schema validator.

## 3. GraphQlArgumentBinder và BindingResult

Với annotated controller, @Argument yêu cầu Spring lấy argument của field hiện tại và bind vào kiểu Java đích.

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL sử dụng **GraphQlArgumentBinder** để chuyển cấu trúc input thành object. Binder hỗ trợ constructor binding, property binding, object lồng nhau và collection.

Khi bind, Spring thu thập lỗi vào **BindingResult**. Nếu lỗi không được xử lý qua tham số Errors hoặc BindingResult trong handler, quá trình có thể ném **BindException** chứa các lỗi đó.

Các kiểu lỗi quan trọng:

- **FieldError**: lỗi gắn với một property cụ thể.
- **ObjectError**: lỗi ở cấp toàn bộ object, không gắn với một field riêng.
- **BindingResult**: tập hợp field errors và global/object errors.
- **BindException**: exception mang BindingResult khi binding hoặc validation thất bại.

Để trả lỗi theo field path, cần đọc **FieldError.getField()** thay vì chỉ trả một message chung.

## 4. Field path là gì?

Field path là đường dẫn tới property bị lỗi trong object Java đang được bind.

Ví dụ DTO:

~~~java
public record CreateBookInput(
        String title,
        AuthorInput author) {
}

public record AuthorInput(
        String name,
        String email) {
}
~~~

Nếu author.name vi phạm @NotBlank, Spring có thể tạo FieldError với field path:

~~~text
author.name
~~~

Với collection lồng nhau:

~~~java
public record CreateBookInput(
        String title,
        List<ChapterInput> chapters) {
}

public record ChapterInput(
        String title,
        Integer pageNumber) {
}
~~~

Nếu tiêu đề của phần tử đầu tiên không hợp lệ, field path có dạng:

~~~text
chapters[0].title
~~~

Một số ví dụ:

| Cấu trúc input | Field path minh họa |
|---|---|
| title | title |
| author.name | author.name |
| chapters[0].title | chapters[0].title |
| addresses[1].postalCode | addresses[1].postalCode |
| settings.timeZone | settings.timeZone |

Đây là property path do cơ chế binding/validation của Spring cung cấp. Với DTO lồng nhau, path thường tương đối với object đích được bind. Tên argument GraphQL bên ngoài như input không nhất thiết tự động trở thành prefix của FieldError.getField().

Nếu ứng dụng dùng @BindParam để ánh xạ tên GraphQL khác tên Java, cần kiểm tra path thực tế và chuẩn hóa về tên field công khai mà client biết. Không nên tự đoán hoặc thêm prefix theo tên argument khi chưa xác minh.

## 5. Phân biệt input field path và GraphQL error path

Hai loại path này có mục đích khác nhau và không nên dùng thay thế nhau.

**Input field path** chỉ ra property trong input object có lỗi:

~~~text
author.email
chapters[0].title
~~~

**GraphQL error path** chỉ ra field trong response tree nơi lỗi được ghi nhận. Ví dụ mutation createBook phát sinh lỗi thì path của GraphQL error có thể là:

~~~json
{
  "path": ["createBook"]
}
~~~

Nếu client dùng alias:

~~~graphql
mutation {
  result: createBook(input: $input) {
    id
  }
}
~~~

GraphQL response path sử dụng alias result, còn input field path vẫn trỏ tới property bên trong input như author.email.

Vì vậy, nên đặt input path trong một extension riêng, chẳng hạn fieldErrors[].fieldPath. Không ghi input path vào thuộc tính GraphQL path, vì thuộc tính đó có nghĩa chuẩn là vị trí field trong response.

## 6. Khai báo validation cho input object

Để kiểm tra constraint, ứng dụng thường dùng Jakarta Bean Validation cùng Spring Boot validation starter.

Dependency:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-validation")
~~~

DTO:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Min(1) Integer pageCount,
        @Valid AuthorInput author) {
}

public record AuthorInput(
        @NotBlank String name,
        @Email String email) {
}
~~~

Các annotation có ý nghĩa:

- @NotBlank: chuỗi phải có ít nhất một ký tự không phải khoảng trắng.
- @NotNull: giá trị không được null.
- @Min(1): số phải lớn hơn hoặc bằng 1.
- @Email: giá trị phải có định dạng email hợp lệ theo validator.
- @Valid: kích hoạt validation đệ quy cho object lồng nhau.

Trong controller, đánh dấu input bằng @Valid:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL kích hoạt Bean Validation cho argument được đánh dấu. Nếu constraint không đạt, lỗi được đưa vào BindingResult và có thể được xử lý tại controller hoặc qua exception handling.

### Validation collection và phần tử

Với list input, cần kích hoạt validation cho từng phần tử:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        List<@Valid ChapterInput> chapters) {
}

public record ChapterInput(
        @NotBlank String title,
        @Min(1) Integer pageNumber) {
}
~~~

@Valid ở type argument giúp validator đi vào từng ChapterInput. Khi một phần tử sai, field path có thể chứa index như chapters[0].pageNumber.

Nếu cần list không rỗng, có thể thêm constraint ở chính list:

~~~java
public record CreateBookInput(
        @NotEmpty List<@Valid ChapterInput> chapters) {
}
~~~

Constraint ở cấp collection và constraint ở phần tử tạo ra loại lỗi khác nhau. Lỗi @NotEmpty gắn với path chapters; lỗi @NotBlank của phần tử gắn với path như chapters[0].title.

## 7. Xử lý lỗi cục bộ bằng Errors hoặc BindingResult

Nếu muốn controller tự quyết định cách trả lỗi validation trong mutation payload, có thể khai báo tham số **Errors** ngay sau argument được đánh dấu validation.

~~~java
@MutationMapping
public CreateBookPayload createBook(
        @Argument("input") @Valid CreateBookInput input,
        Errors errors) {

    if (errors.hasErrors()) {
        return CreateBookPayload.invalid(
                validationErrorMapper.toUserErrors(errors));
    }

    Book book = bookService.create(input);
    return CreateBookPayload.success(book);
}
~~~

Errors hoặc BindingResult phải đặt ngay sau tham số argument tương ứng để Spring liên kết đúng tập lỗi với input đó.

Cách này phù hợp khi API chủ ý biểu diễn validation như kết quả nghiệp vụ dự kiến, ví dụ:

~~~graphql
type UserError {
  fieldPath: String!
  code: String!
  message: String!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}
~~~

Controller có thể chuyển từng FieldError thành một UserError. Trong trường hợp này, resolver vẫn trả payload bình thường và không cần phát top-level GraphQL error chỉ vì người dùng nhập sai.

Nếu input không bind được thành object, cần kiểm tra cách binder cung cấp lỗi cho Errors trong phiên bản đang dùng. Với những lỗi binding được ném ra dưới dạng BindException, có thể dùng exception handler tập trung như phần tiếp theo.

## 8. Xử lý BindException bằng @GraphQlExceptionHandler

Nếu controller không nhận Errors/BindingResult, hoặc muốn chuẩn hóa lỗi binding cho nhiều controller, có thể dùng **@GraphQlExceptionHandler** trong controller hoặc **@ControllerAdvice**.

Ví dụ handler toàn cục:

~~~java
@ControllerAdvice
public class GraphQlBindingExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(
            BindException exception,
            DataFetchingEnvironment environment) {

        List<Map<String, Object>> fieldErrors =
                exception.getFieldErrors().stream()
                        .map(this::toFieldError)
                        .toList();

        List<String> objectErrors =
                exception.getGlobalErrors().stream()
                        .map(this::safeMessage)
                        .toList();

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ")
                .extensions(Map.of(
                        "code", "INPUT_BINDING_FAILED",
                        "fieldErrors", fieldErrors,
                        "objectErrors", objectErrors))
                .build();
    }

    private Map<String, Object> toFieldError(FieldError error) {
        return Map.of(
                "fieldPath", error.getField(),
                "code", toPublicCode(error),
                "message", safeMessage(error));
    }

    private String safeMessage(ObjectError error) {
        String message = error.getDefaultMessage();
        return StringUtils.hasText(message)
                ? message
                : "Giá trị không hợp lệ";
    }

    private String toPublicCode(FieldError error) {
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }
        return switch (error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Min", "Max", "Positive", "PositiveOrZero" -> "OUT_OF_RANGE";
            case "Email" -> "INVALID_FORMAT";
            case "Size" -> "INVALID_LENGTH";
            default -> "INVALID_VALUE";
        };
    }
}
~~~

Ví dụ minh họa cách ánh xạ lỗi thành một GraphQLError tổng hợp. Cần bổ sung import tương ứng cho BindException, BindingResult, FieldError, ObjectError, GraphQLError, GraphqlErrorBuilder, ErrorType, DataFetchingEnvironment và StringUtils.

Các điểm quan trọng:

- exception.getFieldErrors() lấy lỗi gắn với property.
- error.getField() trả field path.
- error.getCode() là mã nội bộ do Spring/validator tạo; nên ánh xạ sang mã API ổn định.
- error.isBindingFailure() giúp phân biệt lỗi chuyển đổi/binding với constraint validation.
- getDefaultMessage() cung cấp thông điệp đã được resolver message xử lý nếu có.
- exception.getGlobalErrors() lấy lỗi ở cấp object.

Không nên đưa error.getRejectedValue() vào response theo mặc định. Giá trị bị từ chối có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc nội dung người dùng không nên được ghi lại.

## 9. Thiết kế GraphQL error extensions cho field path

Một contract lỗi có thể được thiết kế như sau:

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
        "code": "INPUT_BINDING_FAILED",
        "fieldErrors": [
          {
            "fieldPath": "title",
            "code": "REQUIRED",
            "message": "Tiêu đề không được để trống"
          },
          {
            "fieldPath": "author.email",
            "code": "INVALID_FORMAT",
            "message": "Email không đúng định dạng"
          },
          {
            "fieldPath": "chapters[0].pageNumber",
            "code": "OUT_OF_RANGE",
            "message": "Số trang phải lớn hơn 0"
          }
        ]
      }
    }
  ]
}
~~~

Trong response này:

- path: ["createBook"] là GraphQL response path.
- fieldErrors[].fieldPath là path bên trong input object.
- extensions.code là mã lỗi tổng quát.
- fieldErrors[].code là mã lỗi cho từng field.

Client có thể dùng fieldPath để gắn lỗi vào đúng input control. Không nên yêu cầu client phân tích message để tìm field lỗi.

### Một error tổng hợp hay nhiều error riêng?

Có hai cách phổ biến:

| Cách | Ưu điểm | Lưu ý |
|---|---|---|
| Một GraphQLError chứa fieldErrors | Gom lỗi của một input vào một contract dễ xử lý | Client cần đọc extension array |
| Nhiều GraphQLError, mỗi error một field | Từng lỗi có message và metadata riêng | Cần giữ response path đúng field resolver và thống nhất mã lỗi |

Với lỗi validation của một input object, một error tổng hợp thường dễ tiêu thụ hơn. Nếu ứng dụng chọn nhiều GraphQLError, không được đặt input property path vào GraphQL path; vẫn nên đặt nó trong extension như fieldPath.

## 10. Binding lỗi ở nested object

Giả sử input có địa chỉ giao hàng:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateOrderInput {
  customerName: String!
  shippingAddress: AddressInput!
}
~~~

Java DTO:

~~~java
public record CreateOrderInput(
        @NotBlank String customerName,
        @Valid AddressInput shippingAddress) {
}

public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "^[0-9]{5,10}$") String postalCode) {
}
~~~

Nếu postalCode sai định dạng, FieldError path có thể là:

~~~text
shippingAddress.postalCode
~~~

Khi chuyển sang response, giữ nguyên đường dẫn nested để client xác định đúng input control.

Nếu DTO dùng tên Java khác với GraphQL input field, cần có bước chuyển đổi từ property path Java sang public field path. Có thể tạo một mapper riêng cho các alias hoặc binding name đã định nghĩa; tránh sửa chuỗi bằng cách cắt prefix tùy tiện vì có thể làm sai path nested.

## 11. Binding lỗi trong list và collection

Với input chứa danh sách phần tử:

~~~graphql
input LineItemInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  items: [LineItemInput!]!
}
~~~

Java:

~~~java
public record CreateOrderInput(
        @NotEmpty List<@Valid LineItemInput> items) {
}

public record LineItemInput(
        @NotBlank String productId,
        @Min(1) Integer quantity) {
}
~~~

Nếu phần tử thứ hai có quantity bằng 0, field path có thể là:

~~~text
items[1].quantity
~~~

Index giúp client biết phần tử nào trong mảng có lỗi. Nếu list được sắp xếp hoặc lọc lại giữa lúc submit và lúc hiển thị, client nên dùng index cùng với stable item ID khi cần đối chiếu.

Không nên bỏ index khi chuẩn hóa path, vì items[0].quantity và items[2].quantity là hai lỗi khác nhau.

### List lồng nhau

Với cấu trúc lồng nhiều cấp:

~~~text
shipments[0].packages[2].weight
~~~

Path cho biết shipment đầu tiên, package thứ ba có field weight không hợp lệ. Hãy giữ đầy đủ các segment và index để UI có thể định vị lỗi chính xác.

## 12. Tên field GraphQL và tên property Java khác nhau

Thông thường, tên input field GraphQL trùng với tên component/property Java:

~~~graphql
input CreateBookInput {
  title: String!
}
~~~

~~~java
public record CreateBookInput(String title) {
}
~~~

Nếu tên khác nhau, Spring for GraphQL cung cấp **@BindParam** để chỉ định tên input field dùng cho constructor binding.

Ví dụ:

~~~graphql
input CreateBookInput {
  book_title: String!
}
~~~

~~~java
public record CreateBookInput(
        @BindParam("book_title") @NotBlank String title) {
}
~~~

@BindParam giúp binder tìm đúng input key để tạo constructor argument. Tuy nhiên, error path có thể phản ánh tên property hoặc binding path mà binder/validator sử dụng. Nếu API cần trả đúng tên book_title, hãy viết một bước mapping từ path nội bộ sang tên GraphQL công khai và kiểm thử mapping đó.

Không nên cho rằng đổi tên constructor parameter tự động làm thay đổi field path trong mọi tình huống.

## 13. Chuẩn hóa error code

Spring và Bean Validation có thể tạo các code như NotBlank, NotNull, typeMismatch, Size hoặc Email. Đây là code phục vụ binding/message resolution nội bộ.

Client API nên nhận mã ổn định, ví dụ:

| Lỗi nội bộ | Mã API đề xuất |
|---|---|
| NotBlank | REQUIRED |
| NotNull | REQUIRED |
| NotEmpty | REQUIRED |
| typeMismatch hoặc binding failure | INVALID_TYPE |
| Min, Max, Positive | OUT_OF_RANGE |
| Email, Pattern | INVALID_FORMAT |
| Size | INVALID_LENGTH |
| Constraint chưa được ánh xạ | INVALID_VALUE |

Đây chỉ là quy ước API ví dụ. Ứng dụng cần thống nhất mapping cho toàn bộ input types.

Không nên gửi nguyên danh sách FieldError.getCodes() cho client vì nó có thể chứa tên object, property hoặc class Java nội bộ. Chuyển thành mã công khai ổn định trước khi serialize.

## 14. Binding error và business validation

Không phải mọi lỗi có field path đều là binding error.

Ví dụ:

- author.email không đúng định dạng: Bean Validation.
- items[0].quantity nhỏ hơn 1: Bean Validation.
- input.pageCount không chuyển được sang kiểu Java: binding/conversion.
- authorId có format đúng nhưng không tồn tại trong database: business validation.
- Người dùng không được phép dùng authorId đó: authorization.

Business validation thường cần tra cứu domain hoặc kiểm tra trạng thái hiện tại. Nó nên được xử lý ở service/domain layer và trả về exception hoặc payload theo API contract.

Có thể dùng cùng cấu trúc fieldPath cho business validation nếu lỗi gắn với một input field, nhưng không nên giả mạo BindException cho lỗi domain. Hãy tạo một kiểu lỗi nghiệp vụ rõ ràng và dùng mapper chung nếu muốn cùng format response.

## 15. Bảo mật khi trả binding errors

Lỗi theo field path giúp client sửa dữ liệu dễ hơn, nhưng không có nghĩa mọi thông tin từ BindingResult đều nên công khai.

Tránh đưa các giá trị sau vào GraphQL response:

- Rejected value có thể chứa dữ liệu nhạy cảm.
- Tên class, constructor hoặc property nội bộ không thuộc API contract.
- Exception message từ conversion service nếu nó tiết lộ implementation.
- Stack trace hoặc cause.
- Tên bảng, câu SQL hoặc chi tiết database.

Hãy:

- Chỉ trả fieldPath, mã lỗi công khai và message đã kiểm soát.
- Dùng message thân thiện, không chứa giá trị bí mật.
- Log chi tiết ở server với correlation ID phù hợp.
- Không ghi raw variables hoặc rejected values nếu không cần.
- Kiểm tra quyền trước khi tiết lộ liệu một field/resource có tồn tại.

## 16. Kiểm thử field path bằng GraphQlTester

GraphQlTester giúp kiểm tra GraphQL response khi binding hoặc validation thất bại.

Ví dụ query mutation:

~~~graphql
mutation {
  createBook(input: {
    title: " "
    pageCount: 0
    author: {
      name: " "
      email: "invalid"
    }
  }) {
    id
  }
}
~~~

Test cơ bản:

~~~java
@SpringBootTest
class BookBindingErrorTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnBindingError() {
        GraphQlTester.Response response = graphQlTester.document("""
                mutation {
                    createBook(input: {
                        title: " "
                        pageCount: 0
                        author: {
                            name: " "
                            email: "invalid"
                        }
                    }) {
                        id
                    }
                }
                """)
            .execute();

        response.errors()
                .expect()
                .message("Dữ liệu đầu vào không hợp lệ")
                .verify();
    }
}
~~~

Để kiểm tra nội dung fieldErrors, có thể dùng response.errors().satisfy(...) và kiểm tra extensions của từng response error theo API GraphQlTester của phiên bản đang dùng. Mục tiêu kiểm thử là xác nhận các path như title, pageCount, author.name và author.email xuất hiện đúng, không chỉ xác nhận có lỗi.

Nên bổ sung test cho:

1. Scalar coercion error bị GraphQL từ chối trước resolver.
2. FieldError ở property cấp cao.
3. FieldError trong nested object.
4. FieldError trong phần tử list có index.
5. Global/object error không có field path.
6. Binding failure và Bean Validation failure có mã API khác nhau.
7. @BindParam ánh xạ đúng tên field công khai.
8. Errors/BindingResult được nhận ngay sau argument tương ứng.
9. @GraphQlExceptionHandler trả GraphQLError có response path đúng.
10. Input field path nằm trong extensions, không ghi đè GraphQL response path.
11. Rejected value và stack trace không xuất hiện trong response.
12. Business validation được phân biệt với binding validation.

Nếu cần test riêng mapper từ BindingResult sang field error DTO, có thể viết unit test cho mapper mà không cần chạy GraphQL execution.

## 17. Những lỗi thường gặp khi ánh xạ binding error theo path

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client chỉ nhận một message chung | Không đọc BindingResult.getFieldErrors() | Trả danh sách field errors trong extensions hoặc payload |
| Path thiếu cấp nested | Chỉ lấy tên field cuối cùng | Dùng đầy đủ FieldError.getField() |
| Lỗi list không chỉ ra phần tử | Loại bỏ index trong path | Giữ nguyên dạng items[0].field |
| Client hiểu nhầm GraphQL path | Ghi input path vào GraphQLError.path | Đặt input path trong extensions.fieldErrors[].fieldPath |
| Không thấy BindException | Lỗi xảy ra ở GraphQL coercion trước binder | Xác định đúng giai đoạn lỗi |
| Error code thay đổi sau refactor | Gửi thẳng Spring validation code | Map sang mã API ổn định |
| Lộ dữ liệu người dùng | Trả rejectedValue | Không serialize giá trị bị từ chối |
| Nested validation không chạy | Thiếu @Valid ở object hoặc collection element | Kích hoạt cascade validation |
| Tên path khác SDL | DTO dùng property name khác hoặc @BindParam | Map path về tên GraphQL công khai |
| Lỗi domain bị coi là binding | Dùng chung exception không rõ nghĩa | Phân loại binding, validation và business error |

## 18. Quy trình triển khai binding error theo field path

Khi thiết kế input validation cho GraphQL:

1. Khai báo input object trong SDL với scalar, list và nested input rõ ràng.
2. Tạo Java record/DTO có tên property tương ứng với input field.
3. Dùng @BindParam nếu tên constructor/property khác tên GraphQL.
4. Thêm constraint Jakarta Validation cho field và object cần kiểm tra.
5. Dùng @Valid cho nested object và từng phần tử collection.
6. Đánh dấu argument bằng @Argument và @Valid.
7. Chọn Errors/BindingResult nếu mutation cần trả validation trong payload.
8. Nếu để exception thoát ra, xử lý BindException bằng @GraphQlExceptionHandler hoặc exception resolver.
9. Lấy FieldError.getField() để giữ đầy đủ nested path và list index.
10. Ánh xạ code nội bộ sang mã lỗi API ổn định.
11. Đưa input field path vào extension riêng, không nhầm với GraphQL response path.
12. Không trả rejected value, stack trace hoặc thông tin nội bộ.
13. Kiểm thử coercion, binding, nested/list validation và business errors riêng biệt.

Binding error theo field path giúp client biết chính xác property nào trong input cần sửa. Spring for GraphQL cung cấp GraphQlArgumentBinder và BindingResult để thu thập lỗi; FieldError.getField() giữ đường dẫn nested property và index của collection. Khi chuyển lỗi thành GraphQL response, hãy phân biệt input field path với response path, chuẩn hóa error code và chỉ trả message an toàn. Với mutation cần trả lỗi validation như kết quả nghiệp vụ, có thể dùng Errors/BindingResult; với lỗi cần xử lý tập trung, dùng @GraphQlExceptionHandler. Kiểm thử cả nested object, list và tên field được bind tùy chỉnh để contract lỗi luôn nhất quán.
