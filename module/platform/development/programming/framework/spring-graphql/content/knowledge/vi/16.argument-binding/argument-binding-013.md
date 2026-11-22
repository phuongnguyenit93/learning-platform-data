# Lỗi BindException

Trong Spring for GraphQL, dữ liệu argument từ GraphQL operation cần được chuyển thành kiểu Java mà controller yêu cầu. Quá trình này thường diễn ra tự động thông qua **GraphQlArgumentBinder**. Khi dữ liệu đã qua kiểm tra của GraphQL nhưng không thể bind thành Java object theo constructor hoặc property, Spring có thể phát sinh **BindException**.

Để xử lý đúng lỗi này, cần phân biệt hai giai đoạn: GraphQL kiểm tra và coercion dữ liệu theo SDL; sau đó Spring bind giá trị đã xử lý vào tham số Java. Bài học tập trung vào nguyên nhân BindException, cách đọc lỗi binding, thiết kế DTO phù hợp, chuyển lỗi thành GraphQL error và kiểm thử argument binding.

## 1. BindException là gì?

Khi controller khai báo `@Argument`, Spring for GraphQL lấy argument tương ứng từ GraphQL execution environment và chuyển thành kiểu Java của tham số.

Ví dụ schema:

~~~graphql
input BookSearchInput {
    keyword: String
    page: Int
    size: Int
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Controller:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Argument("input") BookSearchInput input) {
        return bookService.search(input);
    }
}
~~~

Spring cần chuyển map giá trị của `input` thành một instance `BookSearchInput`. Spring for GraphQL sử dụng `GraphQlArgumentBinder` để thực hiện việc bind này, bao gồm cả object lồng nhau, collection, array và map.

Nếu binder không thể tạo object đích hoặc không thể gán một hay nhiều giá trị vào thuộc tính Java, lỗi binding được tổng hợp và báo bằng `BindException` thuộc Spring Validation.

Ví dụ, một DTO khai báo constructor yêu cầu primitive `int page`, trong khi schema cho phép page bị bỏ qua hoặc null. Binder không thể truyền null vào tham số primitive. Đây là lỗi tương thích giữa dữ liệu đã bind và kiểu Java đích.

## 2. Phân biệt GraphQL input error và BindException

Không phải mọi lỗi argument đều là BindException. GraphQL và Spring kiểm tra dữ liệu ở các giai đoạn khác nhau.

| Giai đoạn | Thành phần xử lý | Ví dụ lỗi |
| --- | --- | --- |
| Parse operation | GraphQL parser | Thiếu dấu ngoặc hoặc sai cú pháp query. |
| Validate operation | GraphQL validator | Field không tồn tại, argument không được khai báo hoặc selection set sai. |
| Coercion input | GraphQL engine | Thiếu input field non-null, enum value không hợp lệ hoặc scalar không đúng kiểu. |
| Bind vào Java | GraphQlArgumentBinder | Không tạo được DTO, constructor không tương thích hoặc property không thể bind. |
| Validate nghiệp vụ | Controller/service/Bean Validation | Page size vượt giới hạn, chuỗi rỗng hoặc trạng thái chuyển đổi không hợp lệ. |
| Thực thi dữ liệu | Service/repository | Resource không tồn tại hoặc database gặp lỗi. |

Ví dụ, nếu SDL khai báo:

~~~graphql
input BookFilterInput {
    page: Int!
}
~~~

Client gửi:

~~~json
{
    "input": {}
}
~~~

Trong operation gọi `searchBooks(input: $input)`, biến `$input` được truyền object rỗng như trên.

GraphQL phát hiện thiếu field bắt buộc trước khi gọi resolver. Đây là lỗi input coercion; method controller chưa được gọi và không phải BindException do DTO.

Ngược lại, nếu SDL cho phép field nullable:

~~~graphql
input BookFilterInput {
    page: Int
}
~~~

nhưng Java DTO khai báo `int page`, request có thể vượt qua kiểm tra SDL rồi thất bại khi Spring cố bind null vào primitive. Đây là trường hợp có thể dẫn đến BindException.

Phân biệt giai đoạn lỗi giúp chọn đúng cách sửa: sửa operation/schema khi GraphQL từ chối dữ liệu, sửa DTO khi binding không thành công, hoặc sửa service khi dữ liệu hợp lệ về cấu trúc nhưng vi phạm nghiệp vụ.

## 3. GraphQlArgumentBinder thực hiện binding như thế nào?

GraphQlArgumentBinder nhận các giá trị argument đã được GraphQL xử lý và chuyển chúng thành object Java theo kiểu đích mà method controller khai báo.

Quá trình binding thường gồm:

1. Lấy map argument của field đang được thực thi.
2. Xác định kiểu Java đích từ tham số method hoặc thuộc tính cần bind.
3. Nếu kiểu đích là object, binder xử lý các thuộc tính con một cách đệ quy.
4. Tạo object qua constructor phù hợp hoặc constructor mặc định.
5. Với kiểu mutable, gán giá trị qua property accessor/setter.
6. Thu thập các lỗi binding phát sinh.
7. Nếu có lỗi, ném BindException chứa BindingResult; nếu không, trả object đã bind.

Binder hỗ trợ các cấu trúc như:

- Java class hoặc record.
- Object lồng nhau.
- List, collection và array.
- Map.
- Các kiểu dữ liệu có thể chuyển đổi bằng cơ chế conversion được cấu hình.

Ví dụ input lồng nhau:

~~~graphql
input AuthorFilterInput {
    name: String
    country: String
}

input BookSearchInput {
    keyword: String
    author: AuthorFilterInput
    tags: [String!]
}
~~~

Java DTO tương ứng:

~~~java
public record AuthorFilterInput(
        String name,
        String country
) {
}

public record BookSearchInput(
        String keyword,
        AuthorFilterInput author,
        List<String> tags
) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

Binder đi từ object `BookSearchInput` vào `author`, sau đó bind các field `name` và `country` cho `AuthorFilterInput`. Nếu một object con không thể tạo hoặc một giá trị không thể gán, lỗi có thể được ghi nhận ở field path tương ứng.

## 4. Nguyên nhân thường gặp: primitive nhận null

Java primitive như `int`, `long` và `boolean` không thể chứa null. Trong khi đó, GraphQL input field nullable có thể bị bỏ qua hoặc được truyền tường minh null.

Schema:

~~~graphql
input BookSearchInput {
    page: Int
    includeArchived: Boolean
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

DTO dễ gây lỗi:

~~~java
public record BookSearchInput(
        int page,
        boolean includeArchived
) {
}
~~~

Client có thể gửi object rỗng:

~~~json
{}
~~~

Hai field page và includeArchived đều có thể không có giá trị. Binder không thể truyền null vào hai tham số primitive của constructor.

Cách sửa phù hợp là dùng wrapper type:

~~~java
public record BookSearchInput(
        Integer page,
        Boolean includeArchived
) {
}
~~~

Sau đó áp dụng default ở service:

~~~java
public List<Book> search(BookSearchInput input) {
    int page = input.page() == null ? 0 : input.page();
    boolean includeArchived =
            Boolean.TRUE.equals(input.includeArchived());

    return bookRepository.search(page, includeArchived);
}
~~~

Nếu field thực sự bắt buộc, có thể khai báo non-null trong SDL và vẫn dùng wrapper type để biểu diễn rõ dữ liệu đầu vào. GraphQL sẽ từ chối thiếu/null trước khi resolver chạy.

Nguyên tắc:

- Dùng `Integer` thay cho `int` khi field có thể thiếu hoặc null.
- Dùng `Long` thay cho `long` nếu giá trị có thể null.
- Dùng `Boolean` thay cho `boolean` khi cần biểu diễn trạng thái chưa cung cấp.
- Chỉ dùng primitive khi hợp đồng đầu vào bảo đảm luôn có giá trị và cơ chế binding phù hợp.

## 5. Constructor của DTO không tương thích

Binder cần có cách tạo object Java. Với class bất biến hoặc record, constructor phải phù hợp với các thuộc tính đầu vào. Với class mutable, có thể dùng constructor mặc định và setter/property accessor.

Ví dụ DTO:

~~~java
public class BookFilterInput {

    private String keyword;
    private Integer page;

    public BookFilterInput(String keyword) {
        this.keyword = keyword;
    }

    public String getKeyword() {
        return keyword;
    }

}
~~~

Class này có constructor chỉ nhận keyword, không có constructor mặc định, và thuộc tính page không có setter. Constructor không nhận page nên binder không có cách ghi giá trị page còn lại vào object; cấu trúc DTO này có thể dẫn đến lỗi binding. Hãy để constructor nhận đủ field hoặc cung cấp property accessor có thể ghi giá trị đó.

Một cách thiết kế đơn giản là dùng record:

~~~java
public record BookFilterInput(
        String keyword,
        Integer page
) {
}
~~~

Hoặc dùng class mutable có constructor mặc định và setter:

~~~java
public class BookFilterInput {

    private String keyword;
    private Integer page;

    public BookFilterInput() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }
}
~~~

Khi sử dụng class phức tạp, cần kiểm tra:

- Constructor có thể được binder sử dụng không.
- Tham số constructor có tên và kiểu tương thích với input field không.
- Class mutable có constructor mặc định và setter/property accessor phù hợp không.
- Các field cần bind có thể truy cập qua property accessor không.
- Nested DTO có cùng quy tắc tạo object như DTO gốc không.

Không nên thêm constructor chỉ để làm binder hài lòng mà không xem xét ý nghĩa dữ liệu. Hãy chọn mô hình DTO rõ ràng, dễ kiểm thử và phù hợp với cấu trúc SDL.

## 6. Kiểu Java không khớp với kiểu trong SDL

SDL là hợp đồng kiểu dữ liệu mà client nhìn thấy. Java DTO cần có kiểu đích tương thích với các giá trị GraphQL sau coercion.

Ví dụ:

~~~graphql
input PriceRangeInput {
    minPrice: Float
    maxPrice: Float
}
~~~

DTO:

~~~java
public record PriceRangeInput(
        BigDecimal minPrice,
        BigDecimal maxPrice
) {
}
~~~

Việc bind cần có conversion phù hợp cho kiểu số được GraphQL cung cấp. Nếu ứng dụng dùng kiểu Java hoặc custom scalar không tương thích, binder có thể không chuyển đổi được giá trị.

Một số điểm cần rà soát:

- GraphQL `Int` thường được biểu diễn bằng kiểu số nguyên phù hợp; Java field không nên yêu cầu kiểu không thể nhận giá trị đó.
- GraphQL `Float` có ngữ nghĩa số thực; chọn kiểu Java và conversion nhất quán.
- GraphQL `ID` có thể nhận dạng chuỗi hoặc số nguyên theo quy tắc GraphQL; DTO thường dùng String nếu ID được xử lý như định danh.
- Enum Java cần tương thích với enum value mà schema công bố hoặc có mapping chuyển đổi được cấu hình.
- Custom scalar phải có coercing và conversion phù hợp với kiểu Java đích.

Không nên sửa SDL thành String chỉ để tránh lỗi bind số hoặc ngày giờ. Hãy giữ kiểu GraphQL phản ánh đúng hợp đồng API và cấu hình Java/custom scalar tương ứng.

## 7. Lỗi ở nested object và collection

BindException có thể xuất phát từ một field sâu bên trong input object.

Schema:

~~~graphql
input AddressInput {
    city: String
    postalCode: String
}

input AuthorInput {
    name: String
    address: AddressInput
}

input BookSearchInput {
    author: AuthorInput
}
~~~

DTO:

~~~java
public record AddressInput(
        String city,
        Integer postalCode
) {
}

public record AuthorInput(
        String name,
        AddressInput address
) {
}

public record BookSearchInput(
        AuthorInput author
) {
}
~~~

Ở đây postalCode được khai báo String trong SDL nhưng Java dùng Integer. Nếu client gửi mã bưu chính có ký tự chữ, việc chuyển đổi có thể thất bại. Ngay cả khi dữ liệu số có thể chuyển đổi, mô hình định danh bưu chính thường nên dùng String để giữ số 0 ở đầu và ký tự định dạng.

Một ví dụ phù hợp hơn:

~~~java
public record AddressInput(
        String city,
        String postalCode
) {
}
~~~

Với collection, cần bảo đảm kiểu phần tử Java phù hợp:

~~~graphql
input BookSearchInput {
    tags: [String!]
}
~~~

~~~java
public record BookSearchInput(List<String> tags) {
}
~~~

Nếu một phần tử không thể chuyển đổi sang kiểu Java tương ứng hoặc nested object bên trong list không thể tạo, binding có thể thất bại. Khi lỗi xuất hiện trong cấu trúc lồng nhau, hãy xem field path trong BindingResult để xác định đúng phần tử hoặc thuộc tính gây lỗi.

## 8. Đọc BindException và BindingResult

BindException của Spring Validation chứa BindingResult, trong đó có danh sách lỗi theo object và field.

Có thể đọc các field error:

~~~java
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;

public void logBindingErrors(BindException exception) {
    for (FieldError error :
            exception.getBindingResult().getFieldErrors()) {

        log.warn(
                "Argument binding failed at field {}: {}",
                error.getField(),
                error.getDefaultMessage()
        );
    }
}
~~~

Các thông tin hữu ích:

| Thông tin | Ý nghĩa |
| --- | --- |
| `getObjectName()` | Tên object đang được bind. |
| `getField()` | Đường dẫn field gây lỗi. |
| `getDefaultMessage()` | Mô tả lỗi có thể hiển thị cho developer. |
| `getCode()` | Mã lỗi binding/validation. |
| `getRejectedValue()` | Giá trị bị từ chối, cần cẩn trọng khi log. |

Ví dụ field path có thể chỉ ra `author.address.postalCode`, giúp xác định lỗi nằm ở object lồng nhau thay vì toàn bộ argument.

Không nên ghi toàn bộ rejected value vào log production nếu dữ liệu có thể chứa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Chỉ log field path, mã lỗi và correlation ID khi có thể.

Cũng không nên gửi nguyên `getDefaultMessage()` hoặc rejected value ra client mà chưa kiểm tra. Thông báo binding đôi khi chứa chi tiết kiểu Java, tên thuộc tính hoặc dữ liệu nội bộ.

## 9. Chuyển BindException thành GraphQL error

Lỗi xảy ra trong quá trình gọi data fetcher có thể được xử lý bằng cơ chế exception resolution của Spring for GraphQL.

Có thể dùng `@GraphQlExceptionHandler` trong `@ControllerAdvice` để chuẩn hóa response:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(BindException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Dữ liệu argument không phù hợp với kiểu đầu vào.")
                .errorType(ErrorType.BAD_REQUEST)
                .build();
    }
}
~~~

Handler trả thông điệp chung cho client. Chi tiết kỹ thuật có thể được ghi ở server để developer tìm nguyên nhân.

Nếu cần trả danh sách field lỗi cho client, hãy tạo một cấu trúc extension có kiểm soát, chỉ chứa tên field và mã lỗi ổn định. Không đưa rejected value hoặc thông tin nội bộ vào response.

Một chiến lược khác là triển khai `DataFetcherExceptionResolver` khi muốn xử lý lỗi ở cấp toàn ứng dụng, gom nhiều loại exception vào một quy ước GraphQL error thống nhất. Chọn một cơ chế xử lý phù hợp để tránh cùng một exception bị chuyển đổi ở nhiều nơi với nội dung không nhất quán.

Lưu ý: lỗi parse, validation hoặc input coercion của GraphQL có thể xảy ra trước khi data fetcher chạy. `@GraphQlExceptionHandler` dành cho exception phát sinh trong quá trình thực thi resolver; nó không thay thế xử lý mọi request error của GraphQL.

## 10. Phân biệt BindException với Bean Validation

BindException và Bean Validation giải quyết hai vấn đề khác nhau.

- **Binding** chuyển dữ liệu đầu vào sang object Java.
- **Validation** kiểm tra object đã có cấu trúc phù hợp có thỏa quy tắc hay không.

Ví dụ DTO:

~~~java
public record CreateBookInput(
        String title,
        Integer pageCount
) {
}
~~~

Object có thể bind thành công nhưng vẫn không hợp lệ về nghiệp vụ: title rỗng hoặc pageCount âm.

Có thể dùng Jakarta Bean Validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @Min(1) @Max(5000) Integer pageCount
) {
}
~~~

Để constraint được thực thi, ứng dụng cần dependency và cấu hình validation phù hợp, đồng thời kích hoạt validation tại điểm nhận argument theo cách Spring for GraphQL hỗ trợ trong phiên bản đang dùng. Nếu không có bước kích hoạt, chỉ đặt annotation trên DTO không đảm bảo constraint tự chạy.

Với partial input, cần chú ý field bị bỏ qua và field null có ý nghĩa riêng. Constraint như `@NotBlank` có thể xử lý null theo quy tắc của chính constraint, nhưng không tự biểu diễn ý nghĩa “giữ nguyên” hay “xóa giá trị”. Hãy kết hợp validation với `ArgumentValue<T>` hoặc logic nghiệp vụ nếu cần phân biệt trạng thái hiện diện.

## 11. Cách sửa DTO để tránh BindException

Khi gặp lỗi, không nên thay đổi hàng loạt kiểu Java. Hãy kiểm tra đúng field path và sửa nguyên nhân.

Một số nguyên tắc:

**Dùng wrapper cho field nullable.** Nếu SDL cho phép bỏ qua hoặc null, ưu tiên Integer, Long, Boolean thay cho primitive tương ứng.

**Giữ cấu trúc nested object đồng nhất.** Nếu SDL có AuthorInput chứa AddressInput, DTO cũng nên biểu diễn đúng quan hệ đó.

**Chọn constructor phù hợp.** Record phù hợp với DTO bất biến; class mutable cần constructor mặc định và setter/property accessor phù hợp nếu dùng kiểu binding đó.

**Chọn kiểu Java đúng ngữ nghĩa.** Mã bưu chính, số điện thoại và ID thường nên là String dù chúng có thể chứa chữ số. Số lượng và phép tính mới nên dùng kiểu số.

**Cấu hình conversion khi cần.** Với custom scalar hoặc kiểu miền riêng, cung cấp conversion/coercing phù hợp thay vì ép kiểu thủ công trong mọi resolver.

**Không dùng entity persistence làm input DTO.** Tạo input class riêng để kiểm soát field nào client được phép gửi và tránh bind nhầm thuộc tính nội bộ.

Ví dụ DTO được thiết kế rõ:

~~~graphql
input BookSearchInput {
    keyword: String
    page: Int
    size: Int
    author: AuthorFilterInput
}

input AuthorFilterInput {
    name: String
    countryCode: String
}
~~~

~~~java
public record AuthorFilterInput(
        String name,
        String countryCode
) {
}

public record BookSearchInput(
        String keyword,
        Integer page,
        Integer size,
        AuthorFilterInput author
) {
}
~~~

Các kiểu Java wrapper phù hợp với field nullable. Service chịu trách nhiệm chọn default và kiểm tra giới hạn page/size.

## 12. Kiểm thử lỗi binding bằng GraphQlTester

Nên kiểm thử cả trường hợp bind thành công và trường hợp gây BindException.

Ví dụ schema:

~~~graphql
input BookSearchInput {
    page: Int
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

DTO lỗi có thể dùng primitive:

~~~java
public record BookSearchInput(int page) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

Test gửi object không có page:

~~~java
@Test
void reportsBindingErrorWhenNullablePageCannotBindToPrimitive() {
    graphQlTester.document("""
            query SearchBooks($input: BookSearchInput!) {
                searchBooks(input: $input) {
                    id
                }
            }
            """)
        .variable("input", Map.of())
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Sau khi đổi DTO sang wrapper:

~~~java
public record BookSearchInput(Integer page) {
}
~~~

có thể kiểm thử object rỗng được bind thành công và service áp dụng default phù hợp.

Các trường hợp nên có trong bộ test:

- Input object hợp lệ với đủ field.
- Field nullable bị bỏ qua.
- Field nullable được gửi null.
- Primitive nhận field nullable bị bỏ qua.
- Nested DTO có field không thể bind.
- Collection có phần tử không tương thích.
- GraphQL từ chối enum hoặc scalar trước khi resolver chạy.
- BindException được chuyển thành GraphQL error theo quy ước.
- Bean Validation từ chối dữ liệu đã bind nhưng không thỏa quy tắc.
- Response không làm lộ rejected value hoặc chi tiết nội bộ.

Với test lỗi, không chỉ xác nhận `errors` có phần tử. Nên kiểm tra error type hoặc mã lỗi mà ứng dụng công bố, đồng thời xác nhận service không được gọi khi binding thất bại.

## 13. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| BindException khi field bị bỏ qua | Java primitive không nhận null. | Đổi sang wrapper như Integer hoặc Boolean. |
| Không tạo được DTO | Không có constructor phù hợp hoặc không có constructor mặc định/property accessor cần thiết. | Dùng record phù hợp hoặc class mutable có constructor/setter. |
| Lỗi ở nested field | DTO con không tương thích với nested input object. | Đối chiếu cấu trúc và kiểu từng cấp. |
| Không chuyển đổi được giá trị | Kiểu Java đích hoặc conversion không tương thích. | Dùng kiểu Java đúng ngữ nghĩa hoặc cấu hình converter/custom scalar. |
| Unknown input field | Client gửi field không có trong SDL. | Sửa operation; đây thường là lỗi GraphQL validation trước binding. |
| Thiếu non-null input field | Client bỏ qua field bắt buộc. | Bổ sung field; đây là lỗi GraphQL input coercion. |
| Enum value không hợp lệ | Giá trị không được khai báo trong enum schema. | Dùng enum value hợp lệ; GraphQL từ chối trước khi binder chạy. |
| DTO bind được nhưng dữ liệu sai nghiệp vụ | Chưa có validation sau binding. | Thêm Bean Validation hoặc kiểm tra trong service. |
| Client nhận lỗi quá chi tiết | Trả trực tiếp thông tin BindException. | Chuẩn hóa GraphQL error và log chi tiết an toàn ở server. |

## 14. Quy trình chẩn đoán BindException

Khi thấy BindException trong log hoặc GraphQL response, hãy kiểm tra theo thứ tự:

1. Xác định field GraphQL và resolver đang nhận argument.
2. Đọc object name, field path và default message trong BindingResult.
3. Đối chiếu field path với input type trong SDL.
4. Kiểm tra kiểu Java đích, đặc biệt primitive, wrapper và nested DTO.
5. Kiểm tra constructor, setter và property access của class.
6. Xác định giá trị bị bỏ qua, explicit null hay giá trị cụ thể.
7. Kiểm tra custom scalar hoặc conversion nếu kiểu dữ liệu miền riêng.
8. Phân biệt binding với Bean Validation và validation nghiệp vụ.
9. Kiểm tra exception resolver có chuẩn hóa lỗi đúng không.
10. Viết test tái hiện tối thiểu bằng GraphQlTester trước khi sửa DTO hoặc schema.

Sơ đồ chẩn đoán:

~~~mermaid
flowchart TD
    A["GraphQL nhận argument"] --> B["Parse, validate và coerce theo SDL"]
    B --> C{"Input hợp lệ theo schema?"}
    C -->|Không| D["GraphQL request/input error"]
    C -->|Có| E["GraphQlArgumentBinder"]
    E --> F{"Bind được Java object?"}
    F -->|Không| G["BindException"]
    F -->|Có| H["Bean/business validation"]
    H --> I{"Dữ liệu hợp lệ?"}
    I -->|Không| J["Validation error"]
    I -->|Có| K["Gọi service"]
    G --> L["Exception resolver / GraphQL error"]
    J --> L
    K --> M["Trả kết quả"]
~~~

Sửa lỗi theo field path cụ thể thường nhanh và an toàn hơn việc đổi toàn bộ DTO. Nếu nhiều field cùng lỗi, kiểm tra thiết kế constructor và kiểu Java trước.

## 15. Những điểm cần ghi nhớ

- `BindException` xuất hiện khi Spring không thể bind giá trị argument đã được GraphQL xử lý vào kiểu Java đích.
- `GraphQlArgumentBinder` hỗ trợ binding đệ quy cho object lồng nhau, collection, array và map.
- GraphQL parse, validation và input coercion diễn ra trước Java object binding.
- Field nullable có thể bị bỏ qua hoặc nhận null; Java primitive không thể biểu diễn hai trạng thái đó.
- Dùng wrapper type cho dữ liệu có thể null và thiết kế constructor/property accessor phù hợp.
- `BindingResult` cung cấp object name, field path và lỗi cụ thể để chẩn đoán.
- Binding error khác Bean Validation và validation nghiệp vụ.
- Có thể chuẩn hóa BindException thành GraphQL error bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`.
- Không gửi rejected value hoặc chi tiết nội bộ ra client.
- Dùng `GraphQlTester` để kiểm thử binding thành công, binding thất bại và hành vi của exception handler.

BindException thường chỉ ra sự không tương thích giữa dữ liệu GraphQL và mô hình Java mà resolver yêu cầu. Khi phân biệt đúng lỗi coercion, binding và validation, đồng thời thiết kế DTO theo nullability và cấu trúc SDL, ứng dụng Spring for GraphQL sẽ xử lý argument ổn định và dễ chẩn đoán hơn.

