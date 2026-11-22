# Ẩn stack trace khỏi client

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao stack trace và chi tiết exception nội bộ không nên xuất hiện trong GraphQL response.
- Phân biệt GraphQL error dành cho client với exception và stack trace dùng cho vận hành server.
- Hiểu các thành phần `message`, `locations`, `path` và `extensions` của GraphQL error.
- Chuẩn hóa lỗi nghiệp vụ thành thông báo an toàn và mã lỗi ổn định.
- Xử lý exception bằng `@GraphQlExceptionHandler` và `@ControllerAdvice`.
- Nhận biết vai trò của `DataFetcherExceptionResolver` trong xử lý lỗi từ DataFetcher.
- Ghi stack trace ở server cùng request ID và field path để hỗ trợ điều tra.
- Tránh làm lộ SQL, tên bảng, đường dẫn file, hostname, token và dữ liệu cá nhân.
- Hiểu partial data và null propagation khi field gặp lỗi.
- Kiểm thử bằng `GraphQlTester` để xác minh response không chứa thông tin nội bộ.

## 1. Vì sao phải ẩn stack trace khỏi client?

Khi một resolver phát sinh exception, stack trace có thể chứa tên package, class, method, thư viện, cấu trúc hệ thống và vị trí lỗi. Với exception từ database hoặc HTTP client, thông tin còn có thể chứa SQL, tên bảng, hostname, đường dẫn nội bộ hoặc dữ liệu đầu vào.

Nếu đưa stack trace hoặc exception message nguyên bản vào GraphQL response, client có thể nhận được thông tin không cần thiết để sử dụng API nhưng lại hữu ích cho người muốn dò tìm cấu trúc hệ thống.

Ví dụ thông tin không nên gửi ra ngoài:

~~~text
org.springframework.dao.DataAccessResourceFailureException:
JDBC exception executing SQL [select * from internal_book ...]

    at com.example.catalog.BookRepository.findById(BookRepository.java:87)
    at com.example.catalog.BookService.findBook(BookService.java:42)
    at com.example.catalog.BookController.book(BookController.java:31)
    ...
Caused by: org.postgresql.util.PSQLException:
Connection to db-internal.prod.local refused
~~~

Client chỉ cần biết thao tác không hoàn tất và có thể dùng mã lỗi để quyết định bước tiếp theo. Stack trace cần được ghi ở server với quyền truy cập phù hợp.

Nguyên tắc thiết kế là tách hai đầu ra:

- **Client response:** thông báo ngắn, ổn định, không chứa chi tiết nội bộ.
- **Server diagnostics:** exception, stack trace, field path, request ID và thông tin kỹ thuật cần thiết để điều tra.

Không nên giải quyết vấn đề bằng cách bỏ toàn bộ thông tin lỗi. Cần giữ đủ dữ liệu chẩn đoán ở server, đồng thời giới hạn dữ liệu trả về client.

## 2. GraphQL error có những thành phần nào?

GraphQL response có thể chứa `data` và `errors`. Một error thường có các thành phần:

| Thành phần | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `message` | Mô tả lỗi dành cho người gọi | Phải được kiểm soát, không lấy nguyên exception message nội bộ |
| `locations` | Vị trí trong GraphQL document liên quan đến lỗi | Thường do GraphQL runtime cung cấp |
| `path` | Đường dẫn tới field phát sinh lỗi trong response | Hữu ích khi có alias hoặc nested field |
| `extensions` | Metadata mở rộng do runtime hoặc ứng dụng cung cấp | Chỉ chứa mã lỗi và metadata đã được cho phép |

Ví dụ response an toàn:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Đã xảy ra lỗi khi xử lý yêu cầu.",
            "locations": [
                {
                    "line": 2,
                    "column": 5
                }
            ],
            "path": [
                "book"
            ],
            "extensions": {
                "classification": "INTERNAL_ERROR",
                "code": "INTERNAL_ERROR"
            }
        }
    ]
}
~~~

Response này cho client biết field `book` không hoàn tất và có mã lỗi ổn định. Nó không tiết lộ tên exception Java, stack trace, câu SQL hoặc địa chỉ database.

Cấu trúc chính xác của `extensions` phụ thuộc error classification và cấu hình của ứng dụng. Hãy quy ước các mã lỗi công khai và giữ chúng ổn định để client có thể xử lý.

GraphQL error không định nghĩa một field chuẩn tên `stackTrace`. Stack trace thường bị lộ khi ứng dụng tự nối nó vào `message`, thêm vào `extensions`, hoặc dùng custom serializer/debug handler đưa exception nội bộ vào response. Vì vậy, cần rà soát cả error builder lẫn các lớp tùy chỉnh định dạng response.

## 3. Phân biệt exception, GraphQL error và HTTP error

Ba khái niệm này không đồng nghĩa:

- **Java exception:** đối tượng được ném ra khi xử lý gặp lỗi.
- **GraphQL error:** lỗi được biểu diễn trong response GraphQL, thường gắn với một field hoặc operation.
- **HTTP error:** trạng thái ở tầng transport, ví dụ request không thể được xử lý do lỗi giao thức hoặc hạ tầng.

Một exception từ resolver có thể được ánh xạ thành GraphQL error trong response. Khi đó HTTP request vẫn có thể nhận response GraphQL bình thường, kể cả khi response có `errors`.

Ví dụ, `Query.book` truy vấn database và service ném `BookNotFoundException`. Ứng dụng có thể ánh xạ exception này thành GraphQL error với mã `BOOK_NOT_FOUND`. Client nhận lỗi theo contract GraphQL thay vì nhận stack trace Java.

Ngược lại, lỗi parse hoặc validation của GraphQL document có thể xảy ra trước khi DataFetcher được gọi. `DataFetcherExceptionResolver` không phải nơi xử lý mọi lỗi HTTP hay mọi lỗi parse/validation. Cần chọn đúng tầng xử lý cho từng loại lỗi.

## 4. Không trả exception message trực tiếp

Cách làm nguy hiểm thường bắt đầu từ việc sử dụng `ex.getMessage()` để tạo response:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    try {
        return bookService.findById(id);
    }
    catch (Exception ex) {
        throw new RuntimeException(ex.getMessage(), ex);
    }
}
~~~

Exception message có thể đến từ:

- JDBC driver hoặc ORM.
- HTTP client và dịch vụ downstream.
- Filesystem hoặc thư viện xử lý file.
- Exception do lập trình viên tạo nhưng có nối dữ liệu đầu vào.
- Thông báo chứa ID, email hoặc thông tin cá nhân.

Không nên đưa `ex.getMessage()`, `ex.toString()` hoặc `ex.getStackTrace()` vào `message` hay `extensions` của GraphQL error.

Thay vào đó, ánh xạ exception đã biết sang thông báo công khai:

| Exception nội bộ | Thông báo client |
| --- | --- |
| `BookNotFoundException` | Không tìm thấy sách được yêu cầu. |
| `AccessDeniedException` | Bạn không có quyền thực hiện thao tác này. |
| `DuplicateBookException` | Sách đã tồn tại. |
| `DataAccessException` | Không thể hoàn tất thao tác lúc này. |
| Exception không dự kiến | Đã xảy ra lỗi khi xử lý yêu cầu. |

Thông báo công khai nên ngắn và không chứa chi tiết về cách hệ thống lưu trữ hoặc truy xuất dữ liệu.

## 5. Xử lý lỗi bằng @GraphQlExceptionHandler

Spring for GraphQL hỗ trợ `@GraphQlExceptionHandler` để ánh xạ exception phát sinh trong quá trình resolve thành GraphQL error.

Có thể đặt handler trong controller xử lý field liên quan hoặc dùng `@ControllerAdvice` để áp dụng cho nhiều controller. Với chính sách lỗi chung của API, global advice giúp giữ cách trả lỗi nhất quán.

Ví dụ:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlExceptionAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlExceptionAdvice.class);

    @GraphQlExceptionHandler
    public GraphQLError handle(
            Exception exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("Không tìm thấy sách được yêu cầu.")
                    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        Object requestId =
                environment.getGraphQlContext().get("requestId");

        log.error(
                "Unhandled GraphQL exception requestId={} path={}",
                requestId,
                environment.getExecutionStepInfo().getPath(),
                exception
        );

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Đã xảy ra lỗi khi xử lý yêu cầu.")
                .extensions(Map.of("code", "INTERNAL_ERROR"))
                .build();
    }
}
~~~

Trong ví dụ:

- `@ControllerAdvice` đăng ký exception handler dùng chung cho các GraphQL controller.
- `@GraphQlExceptionHandler` đánh dấu method xử lý exception.
- `DataFetchingEnvironment` cung cấp thông tin field đang được resolve và GraphQL context.
- `GraphqlErrorBuilder` tạo GraphQL error gắn với execution environment.
- `ErrorType.NOT_FOUND` và `ErrorType.INTERNAL_ERROR` phân loại lỗi.
- `extensions.code` cung cấp mã lỗi ổn định cho client.
- Exception đầy đủ được truyền cho logger ở server, không đưa vào response.

Ví dụ dùng một handler tổng hợp để minh họa cách phân loại. Trong ứng dụng lớn, có thể tách handler cho từng exception cụ thể và một handler dự phòng cho exception không dự kiến. Hãy bảo đảm exception cụ thể được ánh xạ trước khi đi vào nhánh tổng quát.

## 6. Phân loại lỗi nghiệp vụ và lỗi hệ thống

Không phải mọi exception đều cần cùng một thông báo.

Lỗi nghiệp vụ đã biết có thể được diễn giải an toàn:

~~~java
if (exception instanceof BookNotFoundException) {
    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Không tìm thấy sách được yêu cầu.")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
}
~~~

Lỗi hệ thống không dự kiến nên dùng thông báo tổng quát:

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.INTERNAL_ERROR)
        .message("Đã xảy ra lỗi khi xử lý yêu cầu.")
        .extensions(Map.of("code", "INTERNAL_ERROR"))
        .build();
~~~

Không nên trả cùng một mã `INTERNAL_ERROR` cho mọi tình huống nghiệp vụ. Client cần phân biệt các trường hợp có thể xử lý, ví dụ:

- `BOOK_NOT_FOUND`
- `BOOK_ALREADY_EXISTS`
- `ACCESS_DENIED`
- `VALIDATION_FAILED`
- `INTERNAL_ERROR`

Không đưa tên class exception Java vào mã lỗi công khai. Mã lỗi là một phần contract của API; có thể giữ nguyên mã khi refactor package hoặc đổi implementation backend.

## 7. Vai trò của DataFetcherExceptionResolver

`DataFetcherExceptionResolver` là cơ chế ở tầng GraphQL execution để xử lý exception phát sinh từ DataFetcher và chuyển chúng thành danh sách GraphQL errors.

Trong Spring for GraphQL, có thể triển khai resolver tùy chỉnh hoặc sử dụng adapter để ánh xạ exception. Cơ chế này phù hợp khi cần xử lý lỗi tập trung ở tầng execution, thay vì đặt logic exception handler trong annotated controller.

Ví dụ khung resolver:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
class SafeDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("Không tìm thấy sách được yêu cầu.")
                    .build();
        }

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Đã xảy ra lỗi khi xử lý yêu cầu.")
                .build();
    }
}
~~~

`DataFetcherExceptionResolverAdapter` cung cấp cách triển khai đơn giản cho trường hợp một exception được ánh xạ thành một GraphQL error. Với yêu cầu phức tạp hơn, có thể triển khai trực tiếp `DataFetcherExceptionResolver`.

Hãy chọn một cơ chế phù hợp với cấu trúc ứng dụng. `@GraphQlExceptionHandler` thuận tiện khi muốn xử lý gần controller hoặc trong `@ControllerAdvice`; `DataFetcherExceptionResolver` phù hợp với logic xử lý exception tập trung ở tầng execution. Tránh đăng ký nhiều handler cùng xử lý một exception mà không có quy tắc ưu tiên rõ ràng.

## 8. Những lỗi không đi qua DataFetcherExceptionResolver

`DataFetcherExceptionResolver` xử lý exception phát sinh trong quá trình thực thi DataFetcher. Nó không thay thế tất cả cơ chế xử lý lỗi của GraphQL và HTTP.

Ví dụ:

| Giai đoạn | Ví dụ lỗi | Nơi xử lý phù hợp |
| --- | --- | --- |
| HTTP transport | Request body không đọc được, kết nối bị ngắt | Web server và transport layer |
| GraphQL parse | Query document sai cú pháp | GraphQL parser/execution |
| GraphQL validation | Field không tồn tại hoặc argument sai schema | GraphQL validation |
| DataFetcher execution | Resolver hoặc service ném exception | `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` |
| Bean validation | Input vi phạm constraint | Validation và exception mapping phù hợp |
| Hạ tầng downstream | Database hoặc HTTP service lỗi trong resolver | Resolver exception handling cùng logging/monitoring |

Không cố dùng một resolver để xử lý lỗi trước khi DataFetcher được gọi. Cần hiểu lỗi xảy ra ở giai đoạn nào để cấu hình đúng tầng.

Dù lỗi parse/validation không đi qua resolver exception, vẫn cần kiểm tra response của chúng để bảo đảm không có custom error handler nào thêm stack trace hoặc thông tin nhạy cảm vào message/extensions.

## 9. Ghi stack trace ở server, không gửi cho client

Ẩn stack trace khỏi response không có nghĩa là bỏ stack trace khỏi hệ thống giám sát. Khi exception không dự kiến xảy ra, server cần log đủ thông tin để điều tra.

Ví dụ:

~~~java
Object requestId =
        environment.getGraphQlContext().get("requestId");

log.error(
        "Unhandled GraphQL exception requestId={} path={}",
        requestId,
        environment.getExecutionStepInfo().getPath(),
        exception
);
~~~

Đối số cuối cùng `exception` cho phép SLF4J ghi stack trace ở server. Trong response, chỉ trả thông báo tổng quát và mã lỗi.

Nên ghi kèm:

- Request ID hoặc correlation ID.
- GraphQL field path.
- Operation name nếu có và đã được chuẩn hóa.
- Exception type.
- Stack trace cho lỗi hệ thống cần điều tra.
- Thời điểm và service instance theo chuẩn logging của hệ thống.

Không ghi toàn bộ variables hoặc token vào log cùng stack trace. Exception message đôi khi chứa input hoặc SQL, vì vậy log phải được bảo vệ, truy cập theo vai trò và áp dụng redaction khi cần.

## 10. Dùng request ID để nối log và response

Một mã request giúp tìm được log tương ứng khi client gửi báo cáo lỗi.

Request ID có thể được đặt vào `GraphQLContext` tại interceptor hoặc nơi tạo execution input. Exception handler đọc cùng key để ghi log.

Ví dụ lấy request ID:

~~~java
Object requestId =
        environment.getGraphQlContext().get("requestId");
~~~

Client có thể nhận mã lỗi ổn định như `INTERNAL_ERROR`. Nếu API cần hỗ trợ người dùng gửi mã tham chiếu cho bộ phận hỗ trợ, có thể cung cấp một `correlationId` đã được tạo và kiểm soát riêng trong `extensions`.

Không đưa stack trace vào `extensions` chỉ để hỗ trợ debug. `extensions` vẫn là một phần response được gửi cho client. Mã tham chiếu là đủ để hệ thống nội bộ tra log.

## 11. Không nuốt exception bằng cách trả null

Một cách xử lý dễ gây hiểu nhầm là bắt mọi exception rồi trả `null`:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    try {
        return bookService.findById(id);
    }
    catch (Exception exception) {
        return null;
    }
}
~~~

Cách này làm client không phân biệt được:

- Sách không tồn tại.
- Người dùng không có quyền xem.
- Database không hoạt động.
- Service downstream timeout.
- Có lỗi lập trình trong resolver.

Nếu field nullable, GraphQL có thể trả `null` mà không có error, khiến client hiểu nhầm đó là kết quả hợp lệ.

Hãy ném exception nghiệp vụ phù hợp hoặc để exception đi qua cơ chế xử lý lỗi tập trung. Chỉ trả `null` khi null là một kết quả hợp lệ theo schema và nghiệp vụ.

## 12. Partial data và null propagation

GraphQL có thể trả dữ liệu của những field thành công cùng errors của field thất bại.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Query {
    book(id: ID!): Book
}
~~~

Nếu `internalNotes` lỗi nhưng `book` và `title` vẫn hợp lệ, response có thể chứa `book` với `internalNotes: null` cùng một error có path trỏ tới field đó.

Nếu field lỗi được khai báo non-null, GraphQL áp dụng null propagation lên parent gần nhất có thể nhận null. Vì vậy, việc ẩn stack trace không thay đổi semantics của nullability.

Không nên đổi mọi field thành nullable chỉ để tránh lỗi lan lên parent. Hãy thiết kế schema theo ý nghĩa dữ liệu và ánh xạ lỗi theo contract.

## 13. Các dữ liệu tuyệt đối không đưa vào GraphQL error

Không đưa các thông tin sau vào `message` hoặc `extensions`:

- Stack trace hoặc danh sách stack frame.
- `exception.toString()` hoặc exception message chưa được kiểm duyệt.
- SQL, câu truy vấn database hoặc tên bảng nội bộ.
- Địa chỉ database, hostname, IP và port nội bộ.
- Đường dẫn file, thư mục triển khai hoặc tên máy chủ.
- Access token, refresh token, API key, cookie hoặc session ID.
- Password, OTP, dữ liệu thanh toán và thông tin cá nhân.
- Request variables hoặc toàn bộ object đầu vào.
- Nội dung response của hệ thống downstream có chứa dữ liệu riêng tư.

Chỉ gửi thông tin cần thiết cho client như thông báo an toàn, mã lỗi và correlation ID đã được kiểm soát.

## 14. Kiểm thử để xác minh stack trace không bị lộ

Kiểm thử nên xác minh cả error contract và việc không có thông tin nội bộ trong response.

Ví dụ với `GraphQlTester`:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
            }
        }
        """)
        .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("Đã xảy ra lỗi khi xử lý yêu cầu.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "INTERNAL_ERROR");
    assertThat(errors.get(0).getMessage())
            .doesNotContain(" at com.example.");
    assertThat(errors.get(0).getExtensions())
            .doesNotContainKey("stackTrace");
});
~~~

Test này giả định service phát sinh exception không dự kiến và global handler ánh xạ nó thành lỗi tổng quát.

Nên có thêm test cho exception nghiệp vụ:

~~~java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("Không tìm thấy sách được yêu cầu.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Các trường hợp nên kiểm thử:

- Exception nghiệp vụ được ánh xạ thành thông báo và mã lỗi công khai.
- Exception không dự kiến trả thông báo tổng quát.
- Response không chứa stack trace hoặc exception class.
- Response không chứa SQL, hostname hoặc đường dẫn nội bộ.
- Server log vẫn ghi exception và request ID theo chính sách.
- GraphQL error path trỏ đúng field.
- Partial data và null propagation tuân theo schema.
- Lỗi parse/validation không bị custom handler biến thành response chứa thông tin nội bộ.

Không chỉ kiểm tra chuỗi `stackTrace`. Hãy kiểm tra cả `message`, `extensions` và các trường tùy chỉnh khác mà ứng dụng có thể thêm vào response.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client nhìn thấy tên class Java | Trả `exception.toString()` hoặc `getMessage()` | Ánh xạ sang thông báo công khai |
| Response chứa stack frame | Tự thêm stack trace vào message/extensions | Xóa dữ liệu chẩn đoán khỏi response |
| Exception database làm lộ SQL | Trả nguyên exception message | Dùng thông báo tổng quát và log nội bộ |
| Không có log để điều tra | Chỉ thay exception bằng error chung rồi bỏ exception gốc | Log exception ở server với request ID |
| Mọi lỗi đều thành `INTERNAL_ERROR` | Không phân loại exception nghiệp vụ | Ánh xạ exception cụ thể sang mã lỗi |
| Field trả null nhưng không có error | Resolver bắt exception rồi trả null | Dùng exception mapping khi null không phải kết quả hợp lệ |
| `DataFetcherExceptionResolver` không chạy | Lỗi xảy ra ở parse/validation hoặc transport | Xử lý tại đúng tầng |
| Client không biết field nào lỗi | Error không gắn execution environment/path phù hợp | Dùng `GraphqlErrorBuilder.newError(environment)` |
| Thông báo lỗi thay đổi theo database driver | Dùng exception message làm API contract | Dùng message và error code ổn định |
| Log chứa dữ liệu nhạy cảm | Ghi variables hoặc exception message không kiểm soát | Allowlist, redaction và giới hạn quyền truy cập log |

## 16. Quy trình triển khai error handling an toàn

Khi thiết kế xử lý exception cho GraphQL API, hãy thực hiện theo trình tự:

1. **Phân loại nguồn lỗi.** Xác định lỗi thuộc transport, parse, validation hay DataFetcher execution.
2. **Định nghĩa error contract.** Chuẩn hóa `message`, `ErrorType` và `extensions.code`.
3. **Ánh xạ lỗi nghiệp vụ.** Trả thông báo công khai cho exception đã biết.
4. **Xử lý exception không dự kiến.** Trả thông báo tổng quát, không nối exception message.
5. **Ghi diagnostics ở server.** Log exception, stack trace, request ID và field path theo chính sách.
6. **Giữ response tối thiểu.** Không đưa SQL, hostname, token, stack trace hoặc variables vào error.
7. **Rà soát nullability.** Xác định partial data và null propagation theo SDL.
8. **Kiểm tra các resolver khác.** Không để resolver tự bắt lỗi rồi trả null ngoài ý nghĩa nghiệp vụ.
9. **Kiểm thử error contract.** Dùng `GraphQlTester` để kiểm tra message, code, path và dữ liệu bị lộ.
10. **Theo dõi production.** Dùng request ID để liên kết client report với log và trace nội bộ.

## 17. Tổng kết

Ẩn stack trace khỏi client là yêu cầu quan trọng khi xây dựng GraphQL API an toàn. Exception và stack trace cần được giữ ở server để phục vụ chẩn đoán; GraphQL response chỉ nên chứa thông báo đã kiểm soát, mã lỗi ổn định và metadata thực sự cần thiết cho client.

Trong Spring for GraphQL, có thể dùng `@GraphQlExceptionHandler` cùng `@ControllerAdvice` hoặc `DataFetcherExceptionResolver` để ánh xạ exception từ DataFetcher thành GraphQL errors. Hãy phân biệt lỗi nghiệp vụ với lỗi hệ thống, không trả `getMessage()`, `toString()` hoặc stack trace trong `message`/`extensions`, và ghi diagnostics ở server cùng request ID và field path. Kiểm thử bằng `GraphQlTester` giúp xác minh error contract, partial data và null propagation đồng thời phát hiện việc vô tình làm lộ thông tin nội bộ.

