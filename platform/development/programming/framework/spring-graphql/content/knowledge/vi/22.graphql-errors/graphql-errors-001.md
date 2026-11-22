# GraphQLError

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của GraphQLError trong response GraphQL.
- Đọc các thành phần message, locations, path và extensions.
- Tạo lỗi có cấu trúc bằng GraphqlErrorBuilder.
- Phân loại lỗi bằng ErrorType của Spring for GraphQL.
- Ánh xạ exception nghiệp vụ thành GraphQL error bằng DataFetcherExceptionResolver.
- Phân biệt request error, execution error và response có partial data.
- Kiểm thử GraphQL errors bằng GraphQlTester.

## GraphQLError là gì?

GraphQLError là abstraction của GraphQL Java để biểu diễn một lỗi trong quá trình xử lý GraphQL operation. Một response GraphQL có thể chứa dữ liệu trong data, lỗi trong errors hoặc cả hai.

Ví dụ một query yêu cầu sách không tồn tại:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

Nếu server chọn cách báo lỗi cho trường hợp không tìm thấy, response có thể là:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách",
      "locations": [
        {
          "line": 2,
          "column": 3
        }
      ],
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

GraphQL error là dữ liệu có cấu trúc trong response. Client có thể dùng message để hiển thị thông tin phù hợp, path để xác định field gặp lỗi và extensions để xử lý theo mã lỗi ổn định.

Không phải mọi trường hợp không có dữ liệu đều cần GraphQLError. Nếu field nullable và resolver chủ động trả null vì tài nguyên không tồn tại theo semantics của API, response có thể chỉ chứa data với field null, không có errors. Hãy phân biệt rõ kết quả nghiệp vụ bình thường với lỗi thực thi.

## Các thành phần của GraphQL error

Một GraphQLError có thể cung cấp các thông tin sau:

| Thành phần | Ý nghĩa | Client thường dùng để |
| --- | --- | --- |
| message | Mô tả ngắn gọn vấn đề | Hiển thị hoặc ghi nhận lỗi |
| locations | Vị trí trong GraphQL document nơi lỗi liên quan | Đánh dấu operation hoặc hỗ trợ debug |
| path | Đường dẫn đến field trong response có lỗi | Xác định field/nhánh bị ảnh hưởng |
| extensions | Metadata bổ sung theo quy ước ứng dụng | Đọc error code, category hoặc thông tin máy đọc được |
| ErrorClassification | Phân loại lỗi theo GraphQL Java hoặc Spring | Phân biệt nhóm lỗi và xử lý nhất quán |

Không phải lỗi nào cũng có đủ mọi thành phần. Ví dụ lỗi cú pháp hoặc validation có thể có locations nhưng không có path vì resolver chưa được thực thi. Lỗi xảy ra trong resolver thường có path để chỉ field đã phát sinh lỗi.

### message

message là mô tả lỗi. Nên viết ngắn gọn, rõ nghĩa và phù hợp với người nhận response. Ví dụ:

- "Không tìm thấy sách"
- "Bạn không có quyền thực hiện thao tác này"
- "Dữ liệu đầu vào không hợp lệ"

Không đưa nội dung exception nội bộ, câu SQL, tên bảng, địa chỉ dịch vụ nội bộ, stack trace hoặc thông tin xác thực vào message. Message là một phần response gửi ra client.

### locations

locations là vị trí dòng và cột trong GraphQL document. Vị trí này giúp client hoặc công cụ phát triển xác định field/argument liên quan đến lỗi.

Ví dụ:

~~~graphql
query {
  bookById(id: "missing-book") {
    id
    title
  }
}
~~~

Nếu lỗi phát sinh khi phân giải bookById, location thường trỏ tới field trong operation. Nó không phải số dòng trong file Java chứa resolver.

### path

path là đường dẫn đến vị trí trong response. Phần tử của path có thể là tên field hoặc chỉ số phần tử trong list.

Ví dụ client dùng alias:

~~~graphql
query {
  featured: books {
    title
    author {
      name
    }
  }
}
~~~

Nếu lỗi xảy ra ở name của author trong phần tử thứ hai, path có thể là:

~~~json
["featured", 1, "author", "name"]
~~~

Path dùng alias featured vì đó là tên field trong response. Khi xử lý lỗi ở client, không nên giả định path luôn trùng tên field gốc trong schema.

### extensions

extensions là vùng metadata mở rộng. Đây là nơi phù hợp để cung cấp mã lỗi ổn định:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "category": "NOT_FOUND"
}
~~~

Client nên dựa vào mã như BOOK_NOT_FOUND thay vì so sánh message tiếng Việt. Message có thể được biên tập hoặc dịch; mã lỗi nên ổn định theo contract API.

Chỉ đưa metadata đã được cho phép vào extensions. Không đặt principal, token, dữ liệu cá nhân, thông tin database hoặc chi tiết nội bộ vào đây.

## Tạo GraphQLError bằng GraphqlErrorBuilder

GraphQL Java cung cấp GraphqlErrorBuilder để tạo GraphQLError. Trong Spring for GraphQL, builder này thường được dùng khi ánh xạ exception hoặc khi resolver cần tạo lỗi có cấu trúc.

Ví dụ resolver đơn giản ném exception nghiệp vụ:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Trong ứng dụng thực tế, nên giữ controller tập trung vào điều phối và ánh xạ exception ở một resolver dùng chung. GraphqlErrorBuilder.newError(environment) hữu ích vì builder có thể lấy thông tin field execution như locations và path từ DataFetchingEnvironment.

Khi cần tạo lỗi trực tiếp từ resolver, có thể xây dựng GraphQLError:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Không tìm thấy sách")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
        .build();
~~~

GraphqlErrorBuilder.newError(environment) giúp gắn path và locations của field đang thực thi. Nếu tạo lỗi không gắn với một field cụ thể, có thể dùng builder không có DataFetchingEnvironment; khi đó path hoặc locations có thể không có.

Sau đó có thể trả lỗi cùng dữ liệu bằng DataFetcherResult nếu use case cần. Không cần tạo GraphQLError thủ công cho mọi exception; Spring cung cấp cơ chế exception resolver để chuẩn hóa lỗi tập trung.

## Phân loại lỗi với ErrorType

Spring for GraphQL cung cấp ErrorType để phân loại những nhóm lỗi phổ biến. Các giá trị thường dùng gồm:

| ErrorType | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| BAD_REQUEST | Request hoặc dữ liệu đầu vào không hợp lệ | Input không đáp ứng quy tắc |
| UNAUTHORIZED | Chưa xác thực hoặc thông tin xác thực không hợp lệ | Token không hợp lệ |
| FORBIDDEN | Đã xác thực nhưng không được phép thực hiện | Không có quyền sửa sách |
| NOT_FOUND | Không tìm thấy tài nguyên | Không có sách theo ID |
| INTERNAL_ERROR | Lỗi nội bộ không nên tiết lộ chi tiết | Lỗi không dự kiến ở server |

ErrorType là ErrorClassification được gắn vào GraphQLError. Client có thể dùng classification hoặc extensions code để phân loại. Hãy chọn loại phù hợp với ý nghĩa thực tế; không dùng INTERNAL_ERROR cho mọi lỗi nghiệp vụ đã biết.

Một API có thể dùng extensions.code chi tiết hơn:

| ErrorType | extensions.code |
| --- | --- |
| NOT_FOUND | BOOK_NOT_FOUND |
| BAD_REQUEST | INVALID_BOOK_TITLE |
| FORBIDDEN | BOOK_UPDATE_FORBIDDEN |
| UNAUTHORIZED | AUTHENTICATION_REQUIRED |
| INTERNAL_ERROR | INTERNAL_FAILURE |

ErrorType cung cấp nhóm tổng quát, còn code cho phép client xử lý từng trường hợp cụ thể. Không nên để client phụ thuộc vào tên exception Java hoặc nội dung log server.

## Ánh xạ exception bằng DataFetcherExceptionResolver

Trong Spring for GraphQL, DataFetcherExceptionResolver là extension point để xử lý exception phát sinh trong quá trình thực thi data fetcher. Thay vì mỗi controller tự tạo error response, có thể tạo một resolver tập trung để chuyển exception nghiệp vụ thành GraphQLError.

Ví dụ exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Exception resolver:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Không tìm thấy sách")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

Resolver trên chỉ xử lý BookNotFoundException. Khi trả null, nó cho biết exception này chưa được resolver hiện tại xử lý để các resolver tiếp theo trong chuỗi có cơ hội xử lý. Nếu không có resolver nào xử lý, cơ chế mặc định của Spring for GraphQL sẽ xử lý lỗi còn lại.

Khi ứng dụng có nhiều loại exception, có thể tách resolver theo nhóm nghiệp vụ hoặc tạo một resolver tổng hợp. Cần tránh nhiều resolver cùng xử lý một exception theo các cách khác nhau.

### Không để lộ exception message

Ví dụ exception có message chứa ID hoặc thông tin nội bộ:

~~~java
throw new BookNotFoundException("book-101");
~~~

Không nên trả thẳng exception.getMessage() cho client nếu message đó có thể chứa thông tin không được phép tiết lộ. Resolver ở trên dùng message đã được kiểm soát và extensions code ổn định.

Đối với lỗi không dự kiến, hãy ghi log exception ở server với correlation ID và trả thông điệp tổng quát. Không chuyển stack trace hoặc chi tiết cấu hình vào GraphQLError.

## Request error và execution error

GraphQL có thể phát hiện lỗi ở các giai đoạn khác nhau:

| Nhóm lỗi | Xảy ra khi nào | Resolver có chạy không? | Ví dụ |
| --- | --- | --- | --- |
| Syntax error | Parse GraphQL document | Không | Thiếu dấu ngoặc hoặc sai cú pháp |
| Validation error | Kiểm tra operation với schema | Không | Truy vấn field không tồn tại |
| Input coercion error | Chuyển variables/literal sang kiểu schema | Field tương ứng chưa được thực thi | Truyền String vào argument Int! |
| Execution error | Trong lúc resolver hoặc field execution chạy | Có | Service ném exception |

Request error thường khiến operation không thể thực thi, vì vậy response không có dữ liệu hữu ích từ resolver. Execution error xảy ra trong quá trình phân giải field; các field độc lập khác vẫn có thể thành công và response có thể chứa partial data.

Ví dụ:

~~~json
{
  "data": {
    "bookById": null,
    "serviceStatus": "UP"
  },
  "errors": [
    {
      "message": "Không tìm thấy sách",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Trong response này, field bookById gặp lỗi nhưng serviceStatus vẫn trả kết quả. GraphQL không yêu cầu toàn bộ response phải thất bại chỉ vì một field có lỗi. Nullability có thể làm lỗi lan truyền lên object cha hoặc toàn bộ data nếu các field cha là non-null.

## GraphQLError và DataFetcherResult

Resolver thường trả về một giá trị thông thường. Khi cần trả dữ liệu cùng một hoặc nhiều lỗi, có thể dùng DataFetcherResult<T>:

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

@QueryMapping
public DataFetcherResult<Book> bookDetails(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    Book book = bookService.findById(id).orElse(null);
    if (book == null) {
        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(GraphqlErrorBuilder.newError(environment)
                        .message("Không tìm thấy sách")
                        .errorType(ErrorType.NOT_FOUND)
                        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                        .build())
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
}
~~~

DataFetcherResult cho phép đính kèm errors, local context hoặc extensions cùng data. Nó hữu ích khi một resolver có thể cung cấp dữ liệu hợp lệ nhưng cũng cần báo một vấn đề cụ thể. Nếu data là null cho field non-null, null propagation vẫn áp dụng.

Không dùng DataFetcherResult để che giấu lỗi hệ thống hoặc trả response thành công giả. Hãy dùng nó khi semantics thực sự là có dữ liệu và có cảnh báo/lỗi ở một phần kết quả.

## Thiết kế error contract cho client

Một error contract tốt giúp client xử lý lỗi nhất quán mà không phụ thuộc implementation server:

~~~json
{
  "message": "Bạn không có quyền sửa sách này",
  "extensions": {
    "code": "BOOK_UPDATE_FORBIDDEN",
    "category": "FORBIDDEN",
    "requestId": "req-7f31"
  }
}
~~~

Nên thống nhất:

- Mã lỗi là chuỗi ổn định, không đổi theo tên class Java.
- Category hoặc ErrorType phản ánh nhóm lỗi tổng quát.
- Message không chứa dữ liệu nội bộ và có thể được bản địa hóa.
- Request/correlation ID chỉ được đưa ra nếu đó là mã an toàn để client cung cấp khi hỗ trợ.
- Không trả dữ liệu nhạy cảm trong extensions.

Client có thể xử lý theo code:

~~~typescript
switch (error.extensions?.code) {
  case "BOOK_NOT_FOUND":
    showBookUnavailable();
    break;
  case "BOOK_UPDATE_FORBIDDEN":
    showPermissionMessage();
    break;
  default:
    showGenericError();
}
~~~

Đây là ví dụ phía client. Ứng dụng nên có nhánh mặc định để xử lý mã lỗi mới mà client chưa biết.

## Kiểm thử GraphQLError bằng GraphQlTester

GraphQlTester cho phép kiểm tra errors trong response cùng với data. Ví dụ:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .variable("id", "missing-book")
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("Không tìm thấy sách");
});
~~~

Với API có error contract, hãy kiểm tra thêm:

1. extensions.code bằng BOOK_NOT_FOUND.
2. Classification phù hợp, ví dụ NOT_FOUND.
3. path trỏ tới đúng field response.
4. locations trỏ tới vị trí field trong operation khi có thể xác định.
5. Field nullable có giá trị null như dự kiến.
6. Các field độc lập khác vẫn trả partial data khi phù hợp.
7. Exception không dự kiến không làm lộ stack trace hoặc thông tin nội bộ.

Ngoài test resolver, nên kiểm tra lỗi syntax, validation và input coercion để xác nhận client nhận được lỗi phù hợp ngay cả khi resolver chưa chạy.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client phải so sánh message để xử lý | Không có mã lỗi ổn định trong extensions | Thêm extensions.code và tài liệu hóa |
| Error không có path | Lỗi xảy ra trước execution hoặc builder không nhận environment | Phân biệt request error và execution error; dùng builder có DataFetchingEnvironment khi phù hợp |
| Không thấy partial data | Field lỗi làm null lan truyền qua các field non-null | Kiểm tra nullability và error path |
| Lộ tên class hoặc SQL trong response | Trả exception message trực tiếp | Ánh xạ sang message an toàn và log chi tiết ở server |
| Exception nghiệp vụ trở thành lỗi nội bộ | Chưa có DataFetcherExceptionResolver phù hợp | Đăng ký resolver và kiểm thử mapping |
| Nhiều resolver xử lý cùng exception | Các exception resolver chồng lấn | Phân định trách nhiệm và thứ tự xử lý |
| Client không nhận diện category | Dùng mã lỗi không nhất quán | Chuẩn hóa ErrorType và extensions.code |
| Dùng null để biểu diễn mọi lỗi | Trộn kết quả không có dữ liệu với lỗi thực thi | Trả null chỉ khi đó là semantics hợp lệ; lỗi hệ thống phải được báo rõ |

## Thực hành tổng hợp

Xây dựng error contract cho API thư viện:

1. Tạo BookNotFoundException cho trường hợp không tìm thấy sách.
2. Tạo BookUpdateForbiddenException cho trường hợp người dùng không có quyền cập nhật.
3. Dùng DataFetcherExceptionResolverAdapter để ánh xạ hai exception sang GraphQLError.
4. Gán ErrorType phù hợp và extensions.code lần lượt là BOOK_NOT_FOUND và BOOK_UPDATE_FORBIDDEN.
5. Dùng GraphqlErrorBuilder.newError(environment) để giữ locations và path.
6. Không trả exception message nội bộ cho client.
7. Viết GraphQlTester kiểm tra message, path, classification, extensions và partial data.
8. Thử làm một resolver ném exception không được xử lý để kiểm tra fallback error handling.

Sau khi hoàn thành, hãy giải thích sự khác nhau giữa request error và execution error, vì sao extensions.code ổn định hơn message và khi nào nên trả DataFetcherResult.

## Ghi nhớ

GraphQLError biểu diễn lỗi có cấu trúc trong response GraphQL. Các thông tin quan trọng gồm message, locations, path, extensions và error classification. GraphqlErrorBuilder giúp tạo lỗi; dùng builder với DataFetchingEnvironment để gắn path và vị trí field khi lỗi phát sinh trong execution. Trong Spring for GraphQL, DataFetcherExceptionResolver ánh xạ exception thành lỗi theo một contract tập trung. Request errors xảy ra trước resolver, còn execution errors có thể đi cùng partial data và chịu ảnh hưởng của null propagation. Hãy cung cấp extensions.code ổn định, không để lộ chi tiết nội bộ và kiểm thử cả lỗi lẫn dữ liệu bằng GraphQlTester.
