# errors trong response GraphQL

GraphQL response có thể chứa cả dữ liệu và lỗi trong cùng một kết quả. Vì vậy, client không nên hiểu rằng có lỗi thì toàn bộ dữ liệu đều thất bại, hoặc có `data` thì operation chắc chắn không gặp lỗi. GraphQL phân biệt lỗi xảy ra trước khi thực thi operation với lỗi phát sinh trong lúc phân giải field; hai loại này có cấu trúc response và cách xử lý khác nhau.

Trong Spring for GraphQL, lỗi từ resolver có thể được ánh xạ thành `GraphQLError` bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. GraphQL engine chịu trách nhiệm đặt lỗi vào response, kèm thông tin vị trí và đường dẫn khi có thể. Thiết kế lỗi tốt giúp client biết field nào thất bại, dữ liệu nào vẫn dùng được và nên hiển thị hay xử lý tình huống ra sao mà không làm lộ chi tiết nội bộ của server.

Sau bài này, bạn có thể:

- Đọc cấu trúc `data` và `errors` của GraphQL response.
- Phân biệt request error với execution error.
- Hiểu `message`, `locations`, `path` và `extensions`.
- Giải thích partial data và quy tắc null propagation.
- Ánh xạ exception trong Spring for GraphQL thành GraphQL error.
- Phân biệt lỗi GraphQL với lỗi nghiệp vụ được biểu diễn trong payload.
- Thiết kế error code ổn định và không tiết lộ thông tin nhạy cảm.
- Kiểm thử response lỗi bằng `GraphQlTester`.

## 1. Cấu trúc GraphQL response

Một response thành công đơn giản có thể như sau:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

Nếu không có lỗi, response thường chỉ có `data`; không cần trả một mảng `errors` rỗng.

Khi có lỗi, response có thể chứa `data` và `errors` cùng lúc:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "locations": [
        { "line": 7, "column": 7 }
      ],
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

Trong ví dụ, `book.id` và `book.title` vẫn có dữ liệu. Chỉ field `author` bị lỗi và trở thành null vì field này được khai báo nullable. Client có thể tiếp tục hiển thị thông tin sách trong khi thông báo rằng dữ liệu tác giả tạm thời không khả dụng.

Một response có thể chứa nhiều lỗi nếu nhiều field độc lập gặp vấn đề. Mỗi phần tử trong `errors` mô tả một lỗi riêng; client nên đọc từng lỗi thay vì chỉ kiểm tra có hay không.

## 2. Request error và execution error

GraphQL phân biệt hai giai đoạn phát sinh lỗi.

**Request error** xảy ra trước khi thực thi operation. Ví dụ:

- GraphQL document sai cú pháp và không parse được.
- Query gọi field không tồn tại hoặc truyền argument sai kiểu.
- Operation không hợp lệ theo schema.
- Variable bắt buộc bị thiếu hoặc không thể coercion sang kiểu khai báo.
- Document có nhiều operation nhưng request không xác định operation cần chạy.

Khi có request error, GraphQL không thực thi resolver. Response có `errors` và không có entry `data`:

```json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'. Did you mean 'title'?",
      "locations": [
        { "line": 4, "column": 7 }
      ]
    }
  ]
}
```

**Execution error** xảy ra sau khi operation đã qua các bước kiểm tra và GraphQL bắt đầu phân giải field. Ví dụ resolver không tìm thấy resource, service bên ngoài timeout hoặc người dùng không đủ quyền đọc một field. Khi đó response có entry `data`; field lỗi được xử lý theo nullability và lỗi được đưa vào `errors`.

| Loại lỗi | Thời điểm | Resolver đã chạy? | Response thường gặp |
| --- | --- | --- | --- |
| Parse error | Parse document | Không | `errors`, không có `data` |
| Validation error | Kiểm tra document với schema | Không | `errors`, không có `data` |
| Variable coercion error | Chuẩn bị variables | Không | `errors`, không có `data` |
| Execution error | Đang resolve field | Có thể đã chạy một phần | `data` cùng `errors` |

Sự phân biệt này hữu ích khi chẩn đoán: lỗi request thường cần sửa query/schema/variables; execution error thường cần kiểm tra dữ liệu, quyền, resolver hoặc hệ thống phụ thuộc.

## 3. Các thành phần của một GraphQL error

Một phần tử `errors` có thể chứa những trường sau:

| Trường | Ý nghĩa |
| --- | --- |
| `message` | Mô tả ngắn gọn về lỗi |
| `locations` | Vị trí trong GraphQL document nơi lỗi liên quan, gồm line và column |
| `path` | Đường dẫn đến response field phát sinh lỗi |
| `extensions` | Metadata do implementation hoặc ứng dụng cung cấp |

Không phải mọi lỗi đều có đủ tất cả trường. Ví dụ, lỗi parse có thể có `locations` nhưng chưa có `path` vì chưa có field nào được thực thi. Một lỗi được tạo ở lớp ngoài GraphQL cũng có thể thiếu vị trí trong document.

### `message`

`message` là chuỗi mô tả lỗi cho người hoặc công cụ đọc. Hãy viết thông điệp ngắn, ổn định và không tiết lộ SQL, tên bảng nội bộ, stack trace, secret, token hoặc thông tin của người dùng khác.

### `locations`

`locations` là mảng vị trí trong document GraphQL, mỗi vị trí có `line` và `column` tính từ 1. Khi client dùng query nhiều dòng hoặc fragment, vị trí giúp tìm field/đoạn cú pháp liên quan.

### `path`

`path` chỉ đường dẫn đến field trong response. Các phần tử có thể là tên field hoặc chỉ số phần tử trong list. `path` sử dụng response key; nếu field được alias, path dùng alias đó.

Ví dụ:

```graphql
query {
    library: books {
        title
        writer: author {
            name
        }
    }
}
```

Nếu `author` của phần tử thứ hai gặp lỗi, path có thể là:

```json
["library", 1, "writer"]
```

Client có thể dùng path để đánh dấu đúng phần tử bị lỗi mà không cần suy đoán từ message.

### `extensions`

`extensions` là nơi ứng dụng có thể đưa metadata như error code, correlation ID hoặc thông tin phân loại đã được phép công khai:

```json
{
  "message": "Book not found",
  "path": ["book"],
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
```

`extensions` không phải một schema cố định do GraphQL quy định. Hãy thiết kế cấu trúc riêng có tài liệu, dùng mã lỗi ổn định và chỉ đưa metadata cần thiết cho client. Không đưa token, principal đầy đủ, câu SQL, stack trace hoặc nội dung exception nội bộ vào đây.

## 4. `data: null` khác với không có `data`

Hai response sau thể hiện hai tình huống khác nhau.

Request error, chưa thực thi:

```json
{
  "errors": [
    { "message": "Invalid query document" }
  ]
}
```

Execution error đã lan đến root:

```json
{
  "data": null,
  "errors": [
    {
      "message": "Required field could not be resolved",
      "path": ["book", "author", "name"]
    }
  ]
}
```

Ở response thứ nhất, `data` không xuất hiện vì operation chưa được thực thi. Ở response thứ hai, `data` xuất hiện với giá trị null vì operation đã chạy nhưng lỗi ở một field non-null lan lên tận root. Client không nên gộp hai trạng thái này thành cùng một kết quả.

## 5. Partial data: một phần dữ liệu vẫn hợp lệ

GraphQL có thể trả dữ liệu của những field thành công dù field khác thất bại. Điều này rất hữu ích với query lấy nhiều vùng dữ liệu độc lập:

```graphql
query Dashboard {
    profile {
        displayName
    }
    recommendations {
        id
        title
    }
    notifications {
        id
        message
    }
}
```

Nếu service recommendations bị lỗi nhưng profile và notifications vẫn thành công, response có thể như sau:

Ví dụ giả định field `recommendations` được khai báo nullable trong schema, nên lỗi có thể được biểu diễn bằng giá trị null tại field đó.

```json
{
  "data": {
    "profile": {
      "displayName": "An"
    },
    "recommendations": null,
    "notifications": [
      { "id": "n-1", "message": "Welcome back" }
    ]
  },
  "errors": [
    {
      "message": "Recommendations are temporarily unavailable",
      "path": ["recommendations"],
      "extensions": {
        "code": "RECOMMENDATIONS_UNAVAILABLE"
      }
    }
  ]
}
```

Client nên kiểm tra cả `data` lẫn `errors`. Nếu chỉ kiểm tra `errors.length > 0` rồi bỏ toàn bộ `data`, ứng dụng sẽ bỏ mất những field vẫn có thể hiển thị. Ngược lại, nếu chỉ đọc `data` và bỏ qua `errors`, client có thể âm thầm coi field null do lỗi là dữ liệu rỗng bình thường.

## 6. Null propagation và non-null field

Nullability trong SDL quyết định lỗi ở field lan lên response như thế nào.

Giả sử:

```graphql
type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

`Book.author` nullable. Nếu resolver của `author` lỗi, GraphQL có thể đặt `author` thành null và giữ các field khác của book:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "GraphQL Essentials",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author lookup failed",
      "path": ["book", "author"]
    }
  ]
}
```

Nếu schema đổi thành `author: Author!`, field không được phép null. Khi resolver lỗi, GraphQL đẩy null lên parent `Book`. Nếu `Query.book` cũng khai báo `Book!`, null tiếp tục lan lên root và `data` có thể trở thành null.

Quy tắc khái quát:

1. Field nullable gặp execution error: giá trị field trở thành null; các field sibling vẫn có thể giữ dữ liệu.
2. Field non-null gặp error hoặc trả null: lỗi lan lên parent.
3. Nếu parent nullable, quá trình lan dừng ở parent đó và parent trở thành null.
4. Nếu chuỗi parent đều non-null, lỗi có thể lan tới root khiến `data` là null.

`path` vẫn chỉ field ban đầu phát sinh lỗi, dù giá trị null cuối cùng xuất hiện ở một ancestor. Vì vậy, client có thể dùng path để xác định nguyên nhân thay vì chỉ nhìn vị trí null trong data.

## 7. Exception trong resolver trở thành GraphQL error

Trong Spring for GraphQL, một exception phát sinh khi DataFetcher/resolver chạy có thể được xử lý bởi chuỗi `DataFetcherExceptionResolver`. Cơ chế này cho phép ánh xạ exception của ứng dụng thành một hoặc nhiều `GraphQLError`.

Với annotated controller, cách phổ biến là dùng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice` để xử lý exception có phạm vi rộng hơn.

Ví dụ domain exception:

```java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String bookId) {
        super("Book not found: " + bookId);
    }
}
```

Service ném exception theo ngôn ngữ nghiệp vụ:

```java
@Service
public class BookService {

    public BookView findById(String id) {
        return bookRepository.findViewById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

Exception handler chuyển exception thành lỗi công khai phù hợp:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
```

Trong ví dụ, client nhận message và code ổn định, không nhận ID nội bộ trong exception hoặc chi tiết truy vấn. Spring for GraphQL kết hợp kết quả resolver với thông tin execution để đưa lỗi vào response.

`@GraphQlExceptionHandler` phù hợp với lỗi phát sinh trong quá trình phân giải GraphQL. Lỗi parse, validation hoặc variable coercion xảy ra trước khi resolver chạy nên không được xử lý như exception từ DataFetcher; GraphQL engine tạo request error tương ứng.

## 8. Chọn DataFetcherExceptionResolver hay @GraphQlExceptionHandler

Hai cơ chế này có phạm vi và cách tổ chức khác nhau:

| Cơ chế | Khi phù hợp |
| --- | --- |
| `@GraphQlExceptionHandler` trong controller | Lỗi gắn với controller hoặc nhóm resolver cụ thể |
| `@GraphQlExceptionHandler` trong `@ControllerAdvice` | Quy tắc xử lý exception dùng chung cho nhiều controller |
| `DataFetcherExceptionResolver` | Cần resolver tập trung, xử lý theo loại exception hoặc tích hợp logic ánh xạ lỗi tùy chỉnh |

`DataFetcherExceptionResolver` là extension point của Spring for GraphQL để xử lý exception từ DataFetcher. Resolver có thể nhận exception cùng `DataFetchingEnvironment` và trả kết quả GraphQL error theo API của framework. Khi cần một chính sách thống nhất cho nhiều module hoặc cần phân loại exception phức tạp, đây là lựa chọn phù hợp.

Không cần triển khai cả ba cơ chế cho cùng một exception nếu một handler đơn giản đã đáp ứng yêu cầu. Hãy tránh nhiều nơi cùng xử lý một exception theo các cách khác nhau khiến message, error code và logging không nhất quán.

## 9. Phân loại lỗi và error code ổn định

Client thường cần một mã lỗi máy đọc được hơn là phải phân tích nội dung `message`. Có thể chuẩn hóa các code theo nhóm:

| Error code ví dụ | Ý nghĩa | Hành động client thường thực hiện |
| --- | --- | --- |
| `BAD_INPUT` | Input không hợp lệ theo quy tắc ứng dụng | Hiển thị lỗi nhập liệu |
| `BOOK_NOT_FOUND` | Resource không tồn tại hoặc không được phép hiển thị | Hiển thị trạng thái không tìm thấy |
| `FORBIDDEN` | Người dùng đã xác thực nhưng không đủ quyền | Ẩn/chặn thao tác và thông báo phù hợp |
| `UNAUTHENTICATED` | Chưa có danh tính xác thực hợp lệ | Yêu cầu đăng nhập hoặc làm mới phiên |
| `UPSTREAM_UNAVAILABLE` | Hệ thống phụ thuộc tạm thời không khả dụng | Cho phép retry theo policy |
| `INTERNAL_ERROR` | Lỗi không dự kiến ở server | Hiển thị thông báo chung và ghi nhận hỗ trợ |

Các tên trên là quy ước do ứng dụng lựa chọn, không phải toàn bộ enum bắt buộc của GraphQL. Hãy duy trì danh mục code, mô tả và khả năng retry rõ ràng. Không đổi code chỉ vì câu chữ `message` được chỉnh sửa hoặc dịch sang ngôn ngữ khác.

Spring for GraphQL cung cấp `ErrorType` để phân loại một số nhóm lỗi phổ biến như `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND` và `INTERNAL_ERROR`. Có thể dùng `errorType(...)` để gắn classification, đồng thời thêm mã nghiệp vụ trong `extensions` nếu client cần phân biệt nhiều lỗi trong cùng một nhóm.

## 10. Không biến mọi lỗi thành INTERNAL_ERROR hoặc null

Hai cách xử lý cực đoan đều làm API khó sử dụng:

- Trả mọi lỗi thành `INTERNAL_ERROR`: client không phân biệt được resource không tồn tại, input sai hay thiếu quyền.
- Bắt exception rồi trả null: lỗi bị biến thành dữ liệu vắng mặt, `errors` không còn phản ánh nguyên nhân và client không thể xử lý đúng.

Hãy phân loại lỗi theo ngữ nghĩa:

- Resource không tồn tại: `NOT_FOUND` hoặc code nghiệp vụ tương ứng.
- Người dùng đã đăng nhập nhưng thiếu quyền: `FORBIDDEN`.
- Chưa xác thực: `UNAUTHORIZED` hoặc request bị security layer từ chối trước GraphQL.
- Input sai theo hợp đồng ứng dụng: `BAD_REQUEST`/validation error phù hợp.
- Lỗi không dự kiến: `INTERNAL_ERROR` với message công khai chung.

Nếu resource không tồn tại và resource không thuộc quyền xem cần được che giấu như nhau, service có thể cố ý trả cùng một lỗi công khai để tránh resource enumeration. Đây là quyết định bảo mật cần được áp dụng nhất quán.

## 11. GraphQL error và lỗi nghiệp vụ trong payload

Không phải mọi tình huống nghiệp vụ không thành công đều phải là execution error. Ví dụ, một mutation tạo đơn hàng có thể bị từ chối vì giỏ hàng chưa thanh toán hoặc mã giảm giá không còn hiệu lực. API có thể biểu diễn đây là kết quả nghiệp vụ bình thường trong payload:

```graphql
type UserError {
    code: String!
    message: String!
    field: String
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}
```

Response có thể thành công ở cấp GraphQL nhưng payload chứa lỗi nghiệp vụ:

```json
{
  "data": {
    "createOrder": {
      "order": null,
      "userErrors": [
        {
          "code": "COUPON_EXPIRED",
          "message": "The coupon has expired",
          "field": "couponCode"
        }
      ]
    }
  }
}
```

Nên dùng payload khi client cần xử lý lỗi dự kiến như một phần của luồng nghiệp vụ và muốn nhận cấu trúc có kiểu. Dùng GraphQL `errors` cho lỗi thực thi field, lỗi hệ thống, authorization hoặc lỗi làm operation không thể hoàn tất theo hợp đồng.

Một lỗi validation có thể được biểu diễn bằng payload hoặc GraphQL error tùy thiết kế API. Điều quan trọng là chọn semantics nhất quán, tài liệu hóa và không trả cùng một lỗi theo hai cách tùy tiện.

## 12. Bảo mật message, extensions và log

GraphQL error là dữ liệu gửi tới client. Không đưa các thông tin sau vào `message` hoặc `extensions`:

- Stack trace hoặc tên class nội bộ không cần thiết.
- SQL, tên bảng, câu truy vấn hoặc cấu trúc database.
- Password, access token, refresh token hoặc credential.
- Principal đầy đủ, danh sách quyền nội bộ hoặc claim nhạy cảm.
- Dữ liệu của resource khác hoặc chi tiết tenant mà caller không được xem.
- Nội dung exception từ thư viện bên thứ ba nếu có thể tiết lộ cấu hình hệ thống.

Thay vào đó, gửi message ngắn gọn và code ổn định. Log phía server có thể lưu exception gốc, stack trace và correlation ID để điều tra. Không ghi token hoặc dữ liệu nhạy cảm vào log chỉ để debug.

Nếu dùng correlation ID, bảo đảm ID được tạo hoặc xác minh ở server/gateway đáng tin cậy. Có thể đưa ID đó vào `extensions` để client gửi kèm khi báo lỗi, nhưng không dùng nó làm bằng chứng xác thực hoặc quyền truy cập.

## 13. Lỗi từ Spring Security và authorization

Một exception `AccessDeniedException` phát sinh trong resolver/service có thể được ánh xạ thành GraphQL error `FORBIDDEN`:

```java
@ControllerAdvice
public class SecurityGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(AccessDeniedException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.FORBIDDEN)
                .message("You are not allowed to access this resource")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
```

Nếu request bị từ chối ở Spring Security filter chain trước khi đến GraphQL handler, response có thể là HTTP 401/403 của transport/security layer chứ không phải GraphQL response có `errors`. Nếu authorization được kiểm tra trong lúc resolve field, lỗi có thể xuất hiện trong mảng `errors` và tuân theo null propagation.

Phân biệt hai giai đoạn này giúp client xử lý đúng: lỗi HTTP authentication có thể yêu cầu đăng nhập lại; lỗi field-level authorization có thể chỉ khiến một phần dữ liệu không truy cập được.

## 14. Lỗi trong list và nested field

`path` có thể chứa chỉ số list để chỉ ra phần tử cụ thể gặp lỗi. Ví dụ:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

Nếu tác giả của phần tử thứ ba không tải được, path có thể là:

```json
["books", 2, "author"]
```

Nếu list field hoặc item là non-null, lỗi có thể lan rộng hơn theo nullability:

```graphql
type Query {
    books: [Book!]!
}
```

Với `[Book!]!`, list không được null và từng item cũng không được null. Nếu một phần tử `Book` bị null do lỗi ở một field non-null bên trong, null có thể lan qua item, list và root tùy các kiểu cha. Nếu muốn các phần tử khác vẫn được giữ khi một item lỗi, cần thiết kế nullability của list/item và field con phù hợp.

Không dùng `path` để suy ra index trong một danh sách khác sau khi client đã sort hoặc filter lại dữ liệu ở giao diện. Path mô tả vị trí trong response GraphQL cụ thể của operation đó.

## 15. Client nên xử lý response như thế nào?

Client cần đọc `data` và `errors` độc lập:

1. Nếu không có `errors`, hiển thị dữ liệu theo `data`.
2. Nếu có `errors` và `data` vẫn chứa object, giữ lại các field hợp lệ và đánh dấu phần bị lỗi theo `path`.
3. Nếu không có `data`, xử lý request error trước execution; kiểm tra document, schema hoặc variables.
4. Nếu `data` là null, operation đã có thể chạy nhưng lỗi non-null đã lan đến root; hiển thị trạng thái lỗi phù hợp.
5. Dùng `extensions.code` để chọn hành động máy đọc được; không parse `message` để quyết định logic.
6. Retry chỉ với lỗi có thể retry và theo policy; không tự retry lỗi validation, forbidden hoặc input sai.

Không nên dựa duy nhất vào HTTP status code để kết luận GraphQL operation thành công hay thất bại. Cách transport ánh xạ lỗi sang HTTP status phụ thuộc loại lỗi, server và GraphQL over HTTP integration. Với GraphQL response hợp lệ, client cần đọc cấu trúc response và mảng `errors`.

## 16. Kiểm thử lỗi bằng GraphQlTester

`GraphQlTester` cho phép kiểm tra cả dữ liệu lẫn errors. Ví dụ resolver của `book` ném `BookNotFoundException` và exception handler ánh xạ thành `BOOK_NOT_FOUND`:

```java
graphQlTester.document("""
        query {
            book(id: "missing") {
                id
                title
            }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage()).isEqualTo("Book not found");
    });
```

Với partial data, kiểm tra field khác vẫn có dữ liệu và field lỗi có giá trị null:

```java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

Sau đó kiểm tra lỗi tương ứng qua `.errors()` và đường dẫn field theo response. Tùy phiên bản `GraphQlTester`, có thể dùng `errors().satisfy(...)` hoặc API assertion path để xác nhận dữ liệu null.

Các test nên bao gồm:

1. Request parse/validation error không gọi resolver và không có `data`.
2. Variable coercion error được trả trước execution.
3. Exception ở nullable field tạo partial data và error path đúng.
4. Exception ở non-null field gây null propagation đúng schema.
5. Alias và list index được thể hiện chính xác trong `path`.
6. `extensions.code` ổn định theo loại lỗi.
7. Lỗi authorization không tiết lộ thông tin nhạy cảm.
8. Lỗi dự kiến trong mutation payload không bị nhầm với execution error.
9. Lỗi hệ thống được log phía server nhưng message gửi client vẫn an toàn.

## 17. Những lỗi thường gặp

- **Cho rằng mọi response có lỗi đều không có data:** execution error có thể trả partial data.
- **Nhầm request error với execution error:** request error xảy ra trước resolver và không có entry `data`.
- **Chỉ đọc message:** client nên dùng `path` và `extensions.code` để xử lý có cấu trúc.
- **Bỏ qua null propagation:** field non-null có thể làm null lan lên nhiều cấp.
- **Trả null để thay cho exception:** client không nhận được thông tin lỗi trong `errors`.
- **Đưa stack trace vào extensions:** làm lộ cấu trúc và dữ liệu nội bộ.
- **Map mọi exception thành cùng một code:** client không thể phân biệt lỗi nghiệp vụ, quyền và lỗi hệ thống.
- **Dùng message làm error code:** message có thể thay đổi hoặc được dịch; code cần ổn định.
- **Dùng GraphQL errors cho mọi kết quả nghiệp vụ:** một số lỗi dự kiến phù hợp hơn với payload có kiểu.
- **Chỉ kiểm tra HTTP status:** GraphQL response có thể chứa partial data và errors cùng lúc.
- **Quên kiểm tra alias/list index trong path:** client đánh dấu sai phần tử bị lỗi.
- **Coi lỗi ở HTTP security layer là lỗi resolver:** lỗi trước GraphQL execution có thể không có GraphQL response body theo cùng cấu trúc.

## 18. Quy trình thiết kế và xử lý GraphQL errors

Khi triển khai một field hoặc mutation có thể phát sinh lỗi, hãy thực hiện:

1. Xác định lỗi xảy ra trước execution hay trong quá trình resolve field.
2. Chọn nullability cho field theo khả năng thất bại và mức partial data cần giữ.
3. Định nghĩa exception nghiệp vụ có ý nghĩa ở service/domain.
4. Dùng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` để ánh xạ exception.
5. Chọn `ErrorType` phù hợp và error code ổn định trong `extensions`.
6. Viết message an toàn, không chứa stack trace hoặc thông tin nhạy cảm.
7. Quyết định lỗi dự kiến nên nằm trong GraphQL `errors` hay payload nghiệp vụ có kiểu.
8. Ghi log exception gốc ở server với correlation ID phù hợp.
9. Kiểm thử `data`, `errors`, `locations`, `path`, `extensions` và null propagation.
10. Hướng dẫn client xử lý partial data, retry và các code lỗi.

GraphQL errors là một phần của hợp đồng response, không chỉ là thông báo debug. Request errors ngăn operation bắt đầu; execution errors có thể chỉ ảnh hưởng một field và vẫn giữ partial data. Khi hiểu `locations`, `path`, `extensions` và null propagation, đồng thời ánh xạ exception bằng cơ chế Spring for GraphQL phù hợp, server có thể cung cấp lỗi rõ ràng, an toàn và hữu ích cho client.

## Tài liệu tham khảo

- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring for GraphQL — DataFetcherExceptionResolver](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolver.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
