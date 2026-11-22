# Error extensions

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của trường extensions trong một GraphQL error.
- Thiết kế error code ổn định để client xử lý theo quy tắc thay vì so sánh message.
- Đưa metadata an toàn như error code, field validation và request ID vào error extensions.
- Tạo extensions bằng GraphqlErrorBuilder trong Spring for GraphQL.
- Chuẩn hóa extensions khi ánh xạ exception bằng DataFetcherExceptionResolver.
- Phân biệt error extensions với response extensions, path, locations và HTTP status.
- Kiểm thử error extensions bằng GraphQlTester.

## Error extensions là gì?

GraphQL response có thể chứa danh sách errors. Mỗi error có các trường chuẩn như message, locations và path khi phù hợp. Ngoài ra, GraphQL cho phép server cung cấp một object extensions để đính kèm metadata riêng của ứng dụng.

Ví dụ:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND",
        "requestId": "req-8f31"
      }
    }
  ]
}
~~~

Trong ví dụ này:

- message mô tả ngắn gọn lỗi.
- path cho biết field response gặp lỗi.
- extensions.code là mã máy đọc được để client xác định loại lỗi.
- extensions.requestId giúp người dùng hoặc client liên hệ lỗi với log phía server nếu mã này được thiết kế để công khai.

extensions không phải một field trong GraphQL schema và client không truy vấn nó bằng selection set. Đây là metadata được gửi cùng error trong response. Cấu trúc bên trong do ứng dụng quy định, vì vậy server và client cần thống nhất contract.

Không phải response nào cũng có error extensions. Nếu operation thành công, danh sách errors có thể không xuất hiện. Nếu field nullable trả null theo semantics bình thường và không có lỗi thực thi, cũng không cần tạo một error chỉ để đính kèm metadata.

## Vì sao cần error code?

Không nên để client phân loại lỗi bằng cách so sánh nội dung message. Message có thể thay đổi khi sửa câu chữ, dịch sang ngôn ngữ khác hoặc bổ sung thông tin hướng dẫn.

Ví dụ, các message sau có thể cùng biểu diễn một tình huống:

- "Không tìm thấy sách"
- "Sách không tồn tại hoặc đã bị xóa"
- "We could not find this book"

Client cần một mã ổn định:

~~~json
{
  "message": "Không tìm thấy sách",
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
~~~

Khi message thay đổi, client vẫn có thể xử lý BOOK_NOT_FOUND. Mã lỗi là một phần của API contract; đổi hoặc xóa mã có thể làm client cũ không còn xử lý đúng.

Một error code tốt nên:

- Có ý nghĩa rõ ràng và duy nhất trong phạm vi API.
- Không phụ thuộc tên exception Java hoặc cấu trúc package.
- Dùng nhất quán ở mọi resolver có cùng loại lỗi.
- Không chứa ID người dùng, token hoặc dữ liệu động.
- Được tài liệu hóa để client biết hành vi cần thực hiện.

Ví dụ một số mã lỗi:

| Code | Ý nghĩa | Hành vi client có thể thực hiện |
| --- | --- | --- |
| BOOK_NOT_FOUND | Không tìm thấy sách | Hiển thị trạng thái không tìm thấy |
| BOOK_UPDATE_FORBIDDEN | Người dùng không được sửa sách | Hiển thị thông báo quyền truy cập |
| VALIDATION_FAILED | Dữ liệu đầu vào không hợp lệ | Hiển thị lỗi tại form |
| DUPLICATE_BOOK_ISBN | ISBN đã được dùng | Yêu cầu người dùng kiểm tra ISBN |
| RATE_LIMITED | Vượt giới hạn request | Cân nhắc thử lại theo chính sách |
| INTERNAL_FAILURE | Lỗi nội bộ không dự kiến | Hiển thị thông báo chung và cung cấp request ID nếu có |

Không nên tạo code quá tổng quát như ERROR cho mọi tình huống. Cũng không nên tạo code quá chi tiết cho từng câu chữ message. Hãy chọn mức phân loại giúp client quyết định được hành động.

## Thiết kế cấu trúc extensions

Một cấu trúc phổ biến là đặt mã lỗi trong code, sau đó thêm một số metadata có ích:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "price",
      "code": "MUST_BE_POSITIVE"
    },
    {
      "field": "name",
      "code": "MUST_NOT_BE_BLANK"
    }
  ],
  "requestId": "req-8f31"
}
~~~

Không phải mọi error đều cần mọi thuộc tính. Chỉ gửi thông tin có ý nghĩa cho loại lỗi đó:

| Thuộc tính | Mục đích | Lưu ý |
| --- | --- | --- |
| code | Mã lỗi ổn định | Nên có cho các lỗi ứng dụng cần client xử lý |
| fieldErrors | Danh sách lỗi theo field input | Chỉ trả tên field và mã validation an toàn |
| requestId | Liên kết response với log | Chỉ công khai ID tra cứu không nhạy cảm |
| retryable | Gợi ý lỗi có thể thử lại | Phải dựa trên semantics thực tế, không suy ra từ mọi lỗi server |
| retryAfterSeconds | Khoảng chờ gợi ý trước khi thử lại | Chỉ dùng khi server có chính sách cụ thể |

Đừng biến extensions thành bản sao của exception hoặc toàn bộ request context. Metadata càng nhiều thì contract càng khó duy trì và nguy cơ lộ thông tin càng lớn.

### Không nhầm error extensions với response extensions

GraphQL cũng cho phép metadata ở cấp response, bên ngoài danh sách errors:

~~~json
{
  "data": {
    "books": []
  },
  "extensions": {
    "cost": 4,
    "requestId": "req-8f31"
  }
}
~~~

Đây là extensions cấp response, thường dùng cho metadata áp dụng cho toàn operation như query cost hoặc request ID. Còn errors[i].extensions thuộc về một lỗi cụ thể.

Hai vị trí này có phạm vi khác nhau:

- Response extensions: metadata chung của lần thực thi.
- Error extensions: metadata mô tả một lỗi cụ thể.

Không đặt error code của một field vào response extensions nếu operation có thể có nhiều lỗi khác nhau. Đặt code trên từng error để client ghép đúng mã với đúng path.

## Tạo error extensions bằng GraphqlErrorBuilder

GraphQL Java cung cấp GraphqlErrorBuilder để tạo GraphQLError. Có thể dùng extensions(Map<String, Object>) để đính kèm metadata:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Không tìm thấy sách")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "requestId", requestId))
        .build();
~~~

newError(environment) giúp builder gắn thông tin field execution như path và locations khi có thể. errorType cung cấp phân loại tổng quát; extensions.code là mã chi tiết do API của ứng dụng định nghĩa.

Không nên giả định rằng tên hoặc cấu trúc classification mặc định của GraphQL Java luôn giống nhau giữa các phiên bản. Nếu client cần một thuộc tính ổn định, hãy công bố rõ trong extensions của ứng dụng, ví dụ code.

### Tập trung error code thành constant

Tránh gõ chuỗi mã lỗi tùy ý ở nhiều resolver. Có thể dùng enum:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    BOOK_UPDATE_FORBIDDEN,
    VALIDATION_FAILED,
    DUPLICATE_BOOK_ISBN,
    INTERNAL_FAILURE
}
~~~

Một helper nhỏ giúp tạo lỗi nhất quán:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

public final class ApiGraphQlErrors {

    private ApiGraphQlErrors() {
    }

    public static GraphQLError notFound(
            DataFetchingEnvironment environment,
            ApiErrorCode code,
            String message,
            String requestId) {

        return GraphqlErrorBuilder.newError(environment)
                .message(message)
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of(
                        "code", code.name(),
                        "requestId", requestId))
                .build();
    }
}
~~~

Helper chỉ nên chứa quy tắc chung thực sự dùng lại được. Không xây dựng một framework error phức tạp nếu ứng dụng chỉ có vài loại lỗi đơn giản.

## Chuẩn hóa extensions bằng DataFetcherExceptionResolver

Trong Spring for GraphQL, DataFetcherExceptionResolver cho phép chuyển exception từ resolver hoặc service thành GraphQLError. Đây là nơi phù hợp để bảo đảm mọi exception nghiệp vụ có cùng cấu trúc extensions.

Ví dụ exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Resolver:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class ApiExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Không tìm thấy sách")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        if (exception instanceof DuplicateBookIsbnException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("ISBN đã được sử dụng")
                    .errorType(ErrorType.BAD_REQUEST)
                    .extensions(Map.of(
                            "code", "DUPLICATE_BOOK_ISBN"))
                    .build();
        }

        return null;
    }
}
~~~

Resolver này chuyển exception đã biết thành mã lỗi công khai. Các exception khác được để cho resolver tiếp theo hoặc cơ chế mặc định xử lý. Khi mở rộng danh sách lỗi, hãy bảo đảm mỗi loại exception được ánh xạ theo một quy tắc rõ ràng.

Không đưa exception.getMessage() trực tiếp vào response nếu message có thể chứa dữ liệu nội bộ. Message công khai nên được kiểm soát; chi tiết kỹ thuật đầy đủ được ghi log phía server.

### Thêm request ID vào extensions

Nếu ứng dụng đã có request/correlation ID trong GraphQLContext, exception resolver có thể đọc ID từ DataFetchingEnvironment và đính kèm vào error:

~~~java
String requestId =
        environment.getGraphQlContext().get("correlationId");

return GraphqlErrorBuilder.newError(environment)
        .message("Không tìm thấy sách")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "requestId", requestId))
        .build();
~~~

Trong triển khai thực tế, cần xử lý trường hợp request ID có thể vắng mặt trước khi dùng Map.of, vì Map.of không chấp nhận key hoặc value null. Có thể tạo map có điều kiện hoặc dùng helper đã kiểm tra giá trị.

Request ID chỉ nên là mã tra cứu an toàn. Không đưa access token, session ID, cookie hoặc toàn bộ header vào extensions.

## Error extensions cho validation

Một lỗi validation có thể cần chỉ ra nhiều field đầu vào không hợp lệ. Thay vì buộc client phân tích message, server có thể trả một mã chung cùng danh sách field errors:

~~~json
{
  "message": "Dữ liệu đầu vào không hợp lệ",
  "extensions": {
    "code": "VALIDATION_FAILED",
    "fieldErrors": [
      {
        "field": "name",
        "code": "MUST_NOT_BE_BLANK"
      },
      {
        "field": "price",
        "code": "MUST_BE_POSITIVE"
      }
    ]
  }
}
~~~

Client có thể ánh xạ mã field error sang thông báo phù hợp với ngôn ngữ giao diện. Server vẫn chịu trách nhiệm xác thực; metadata này chỉ mô tả kết quả validation.

Ví dụ helper tạo validation error:

~~~java
Map<String, Object> extensions = Map.of(
        "code", "VALIDATION_FAILED",
        "fieldErrors", List.of(
                Map.of(
                        "field", "name",
                        "code", "MUST_NOT_BE_BLANK"),
                Map.of(
                        "field", "price",
                        "code", "MUST_BE_POSITIVE")));

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Dữ liệu đầu vào không hợp lệ")
        .errorType(ErrorType.BAD_REQUEST)
        .extensions(extensions)
        .build();
~~~

Đây là cấu trúc do ứng dụng định nghĩa, không phải định dạng validation bắt buộc của GraphQL. Hãy giữ tên thuộc tính và mã field error ổn định, đồng thời không gửi rejected value nếu giá trị đó có thể chứa thông tin cá nhân hoặc bí mật.

## Phân biệt error code, ErrorType và HTTP status

Ba khái niệm này phục vụ các tầng khác nhau:

| Thành phần | Phạm vi | Ví dụ |
| --- | --- | --- |
| extensions.code | Mã nghiệp vụ ổn định do API định nghĩa | BOOK_NOT_FOUND |
| ErrorType | Phân loại lỗi tổng quát của Spring for GraphQL | NOT_FOUND, BAD_REQUEST |
| HTTP status | Trạng thái của HTTP response/transport | 200, 4xx, 5xx theo cách server xử lý request |

GraphQL execution error có thể xuất hiện cùng data một phần. Vì vậy, không thể suy ra mọi lỗi GraphQL đều phải trả HTTP 4xx hoặc 5xx. HTTP status phụ thuộc giai đoạn lỗi, transport và cấu hình server. Error code trong extensions cũng không tự thay đổi HTTP status.

Client GraphQL nên đọc nội dung response và error extensions theo contract. Với các lỗi ở tầng HTTP như không kết nối được server, gateway timeout hoặc response không phải GraphQL, client vẫn cần xử lý HTTP/network error riêng.

## Thiết kế metadata an toàn

extensions được gửi tới client, vì vậy hãy xem mọi giá trị trong đó là dữ liệu công khai.

Nên đưa vào:

- Error code đã được tài liệu hóa.
- Field name và validation code không chứa giá trị nhạy cảm.
- Request ID ngẫu nhiên hoặc mã tra cứu không mang quyền truy cập.
- Gợi ý retry nếu server xác định rõ điều kiện và thời gian.

Không đưa vào:

- Stack trace hoặc tên class nội bộ nếu không cần thiết.
- SQL, tên bảng, connection string hoặc địa chỉ dịch vụ nội bộ.
- Access token, refresh token, cookie hoặc session secret.
- Toàn bộ input object hoặc giá trị người dùng gửi.
- Principal, quyền chi tiết hoặc dữ liệu tenant không được phép công khai.

Nếu cần chẩn đoán sâu, hãy ghi log chi tiết ở server và liên kết bằng request ID. Đừng dùng error extensions như kênh debug thay cho logging có kiểm soát.

## Client xử lý extensions

Client nên phân nhánh theo extensions.code và luôn có nhánh mặc định cho mã chưa biết:

~~~typescript
function handleGraphQLError(error: GraphQLError) {
  switch (error.extensions?.code) {
    case "BOOK_NOT_FOUND":
      showBookNotFound();
      return;
    case "BOOK_UPDATE_FORBIDDEN":
      showPermissionDenied();
      return;
    case "VALIDATION_FAILED":
      showFieldErrors(error.extensions.fieldErrors);
      return;
    default:
      showGenericError();
  }
}
~~~

Nếu response có nhiều errors, hãy xử lý từng error riêng và dùng path để liên kết lỗi với field tương ứng. Một operation có thể có nhiều field lỗi với các mã khác nhau.

Client không nên giả định extensions luôn tồn tại hoặc luôn có code. Syntax error, validation error hoặc lỗi do middleware có thể có cấu trúc khác. Luôn kiểm tra kiểu và giá trị trước khi truy cập.

## Kiểm thử error extensions bằng GraphQlTester

GraphQlTester cho phép kiểm tra GraphQLError trong response. Ví dụ:

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
    GraphQLError error = errors.get(0);
    assertThat(error.getMessage())
            .isEqualTo("Không tìm thấy sách");
    assertThat(error.getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Ngoài code và message, hãy kiểm tra:

1. path trỏ đúng field response, kể cả khi query dùng alias.
2. locations trỏ đúng vị trí trong operation khi lỗi xảy ra ở field.
3. extensions không chứa token, stack trace hoặc dữ liệu nội bộ.
4. Validation error có fieldErrors đúng cấu trúc.
5. Partial data vẫn có mặt khi các field độc lập khác thành công.
6. Error code không đổi khi message được chỉnh sửa hoặc bản địa hóa.
7. Exception không được nhận diện có fallback error an toàn.

Nên có contract test để bảo đảm client và server cùng hiểu một tập mã lỗi. Khi đổi tên hoặc xóa code, cần xem đó là thay đổi API có thể ảnh hưởng client.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client phụ thuộc vào message | Không có error code ổn định | Định nghĩa extensions.code |
| Một error không có extensions | Lỗi đến từ parser, validator hoặc middleware khác | Client phải hỗ trợ error không có metadata tùy chỉnh |
| Code lỗi không nhất quán giữa resolver | Mỗi controller tự đặt chuỗi mã | Tập trung code và mapping exception |
| Extensions chứa dữ liệu nhạy cảm | Đưa exception, input hoặc principal vào response | Chỉ gửi metadata công khai và an toàn |
| Request ID gây lỗi khi tạo Map | Giá trị null được truyền vào Map.of | Chỉ thêm key khi có giá trị hoặc dùng map có thể xử lý null |
| Client không biết mã mới | Không có nhánh fallback | Xử lý mã chưa biết bằng thông báo chung |
| Nhầm code với HTTP status | Trộn tầng GraphQL và HTTP transport | Xử lý error extensions và HTTP/network status riêng |
| Validation message khó phân tích | Chỉ trả một message tự do | Trả fieldErrors với field và code ổn định |

## Thực hành tổng hợp

Thiết kế error extensions cho API thư viện:

1. Định nghĩa tập mã BOOK_NOT_FOUND, BOOK_UPDATE_FORBIDDEN, VALIDATION_FAILED và INTERNAL_FAILURE.
2. Tạo enum hoặc constant để tránh lặp chuỗi code.
3. Dùng DataFetcherExceptionResolverAdapter ánh xạ exception nghiệp vụ thành GraphQLError.
4. Gắn ErrorType phù hợp và extensions.code cho từng lỗi.
5. Với validation, trả fieldErrors gồm tên field và mã lỗi; không gửi rejected value nhạy cảm.
6. Đưa correlation ID an toàn vào extensions.requestId nếu có.
7. Viết GraphQlTester kiểm tra code, message, path và cấu trúc extensions.
8. Kiểm tra client có nhánh fallback cho error không có extensions hoặc code chưa biết.
9. Xác minh response không chứa stack trace, token, SQL hoặc thông tin nội bộ.

Sau khi hoàn thành, hãy giải thích vì sao error code là contract của API, vì sao ErrorType không thay thế mã nghiệp vụ và vì sao HTTP status cần được xử lý riêng.

## Ghi nhớ

Error extensions là metadata do ứng dụng đính kèm vào từng GraphQL error. Hãy dùng extensions.code ổn định để client xử lý lỗi, còn message dành cho thông tin dễ đọc. Spring for GraphQL có thể tạo GraphQLError bằng GraphqlErrorBuilder và chuẩn hóa exception qua DataFetcherExceptionResolver. Có thể bổ sung field validation hoặc request ID nếu chúng an toàn và có ích. Phân biệt error extensions với response extensions, ErrorType và HTTP status. Luôn kiểm tra dữ liệu extensions trước khi gửi, không để lộ chi tiết nội bộ và kiểm thử error contract bằng GraphQlTester.
