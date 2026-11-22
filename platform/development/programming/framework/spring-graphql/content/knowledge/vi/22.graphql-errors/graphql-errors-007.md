# Exception ở controller

Trong Spring for GraphQL, exception phát sinh khi một resolver xử lý field có thể được chuyển thành GraphQL error thông qua `@GraphQlExceptionHandler`. Annotation này cho phép đặt logic xử lý lỗi ngay trong controller hoặc gom xử lý chung vào một class `@ControllerAdvice`.

Cách tổ chức này giúp tách lỗi nghiệp vụ khỏi chi tiết response GraphQL. Service có thể ném exception thể hiện tình huống như không tìm thấy sách, trạng thái đơn hàng không cho phép hủy hoặc tài khoản đã tồn tại. Controller advice chuyển exception thành lỗi có message an toàn, mã lỗi ổn định và classification phù hợp để client xử lý.

## 1. Exception ở resolver khác gì lỗi GraphQL?

Một GraphQL operation có thể thất bại ở nhiều giai đoạn:

1. **Parse**: document sai cú pháp, ví dụ thiếu dấu ngoặc hoặc dấu phân cách.
2. **Document validation**: query dùng field không tồn tại, thiếu selection set hoặc sai vị trí fragment.
3. **Input coercion**: variable hoặc argument không đúng kiểu, vi phạm nullability.
4. **Field execution**: resolver hoặc service ném exception trong lúc thực thi field.

`@GraphQlExceptionHandler` chủ yếu xử lý exception phát sinh trong quá trình thực thi data fetcher/resolver. Các lỗi parse, validation document và coercion xảy ra trước khi controller method được gọi; vì vậy handler ở controller không thể xử lý chúng như một exception nghiệp vụ thông thường.

Ví dụ query hợp lệ về cú pháp nhưng sách không tồn tại:

```graphql
type Query {
    book(id: ID!): Book
}
```

```java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
```

`BookNotFoundException` phát sinh trong lúc resolver chạy. Đây là tình huống phù hợp để exception handler chuyển nó thành GraphQL error.

## 2. Cấu trúc GraphQL response khi có lỗi

Theo GraphQL response format, kết quả thực thi có thể chứa `data`, `errors` hoặc cả hai. Mỗi phần tử trong `errors` có thể có `message`, `locations`, `path` và `extensions`.

Ví dụ lỗi ở field `book`:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách.",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

Một lỗi ở field không nhất thiết làm toàn bộ operation thất bại. Các field khác vẫn có thể trả dữ liệu nếu không phụ thuộc vào field lỗi và quy tắc nullability cho phép. `path` cho biết vị trí field xảy ra lỗi trong response; nếu query dùng alias, path dùng response key là alias.

`extensions` là nơi phù hợp để cung cấp metadata bổ sung như mã lỗi hoặc thông tin phân loại mà client cần. Không đưa stack trace, câu SQL, đường dẫn file, tên host nội bộ hoặc thông tin xác thực vào đây.

## 3. Tạo exception nghiệp vụ

Exception nên mô tả tình huống nghiệp vụ mà service phát hiện. Ví dụ:

```java
package com.example.graphql.book;

public class BookNotFoundException extends RuntimeException {

    private final String bookId;

    public BookNotFoundException(String bookId) {
        super("Book not found: " + bookId);
        this.bookId = bookId;
    }

    public String getBookId() {
        return bookId;
    }
}
```

Service ném exception khi không tìm thấy dữ liệu:

```java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Book findById(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

Service không cần biết GraphQL response có cấu trúc thế nào. Exception thể hiện lỗi nghiệp vụ; tầng GraphQL quyết định cách công bố lỗi qua response. Cùng service đó có thể được tái sử dụng từ REST controller hoặc một luồng xử lý khác.

## 4. Xử lý exception ngay trong controller

`@GraphQlExceptionHandler` có thể đặt trên method trong một `@Controller`. Handler cục bộ phù hợp khi exception chỉ liên quan đến các resolver trong controller đó hoặc cách hiển thị lỗi phụ thuộc vào ngữ cảnh của controller.

```java
package com.example.graphql.book;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import org.springframework.graphql.execution.ErrorType;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Không tìm thấy sách.")
            .build();
    }
}
```

Handler nhận exception cần xử lý và `DataFetchingEnvironment` để tạo lỗi gắn với vị trí field đang thực thi. `GraphqlErrorBuilder.newError(environment)` giúp giữ thông tin vị trí và path của field. `ErrorType.NOT_FOUND` phân loại lỗi theo Spring for GraphQL; message được trả ra là nội dung đã kiểm soát, không sử dụng trực tiếp message nội bộ có thể chứa ID hoặc dữ liệu nhạy cảm.

Handler trong `BookController` có phạm vi cục bộ của controller đó. Nếu `AuthorController` cũng ném `BookNotFoundException`, handler này không tự động trở thành handler dùng chung cho controller kia.

## 5. Dùng @ControllerAdvice cho xử lý lỗi toàn cục

Khi nhiều controller cần cùng một quy tắc ánh xạ exception, đặt handler trong class được đánh dấu `@ControllerAdvice`. Cách này tránh lặp lại cùng logic trong từng controller.

```java
package com.example.graphql.error;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Không tìm thấy tài nguyên được yêu cầu.")
            .build();
    }
}
```

`@ControllerAdvice` cho phép áp dụng handler cho các annotated controller trong phạm vi component scan. Có thể tạo nhiều advice theo nhóm lỗi hoặc module; khi phạm vi giao nhau, dùng thứ tự advice có chủ đích và tránh khai báo nhiều handler cùng nhận một exception theo cách mơ hồ.

Handler cục bộ trong controller phù hợp với logic chỉ dành cho controller đó. Handler trong `@ControllerAdvice` phù hợp với quy ước chung như not found, conflict, validation hoặc lỗi hệ thống. Nên chọn một nơi làm nguồn xử lý chính cho từng loại exception để tránh hành vi khó dự đoán.

## 6. Trả mã lỗi qua extensions

Client thường cần mã lỗi ổn định để quyết định hành động, ví dụ hiển thị form, yêu cầu đăng nhập lại hoặc cho phép người dùng thử lại. Message có thể thay đổi theo ngôn ngữ, vì vậy không nên dùng message làm định danh lỗi.

Có thể thêm mã lỗi trong `extensions`:

```java
import java.util.Map;

@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.NOT_FOUND)
        .message("Không tìm thấy sách.")
        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
        .build();
}
```

Response có thể có dạng:

```json
{
  "errors": [
    {
      "message": "Không tìm thấy sách.",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

Các extension khác có thể được framework thêm tùy loại lỗi. Hợp đồng client nên dựa vào field mã lỗi do ứng dụng quy định, ví dụ `code`, thay vì phụ thuộc vào nội dung message hoặc chi tiết triển khai nội bộ.

## 7. Xử lý nhiều loại exception

Một ứng dụng thường có nhiều nhóm lỗi nghiệp vụ. Có thể tạo handler riêng cho từng exception:

```java
import java.util.Map;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {
        return error(environment, ErrorType.NOT_FOUND,
            "Không tìm thấy sách.", "BOOK_NOT_FOUND");
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookConflict(
            BookConflictException exception,
            DataFetchingEnvironment environment) {
        return error(environment, ErrorType.BAD_REQUEST,
            "Không thể thực hiện thay đổi với sách này.", "BOOK_CONFLICT");
    }

    private GraphQLError error(
            DataFetchingEnvironment environment,
            ErrorType errorType,
            String message,
            String code) {
        return GraphqlErrorBuilder.newError(environment)
            .errorType(errorType)
            .message(message)
            .extensions(Map.of("code", code))
            .build();
    }
}
```

Trong ví dụ, hai exception nghiệp vụ được chuyển thành hai mã lỗi khác nhau. Import `java.util.Map` cần được thêm cho helper.

Không nên tạo một handler tổng quát bắt mọi `Exception` rồi trả nguyên `exception.getMessage()`. Cách đó dễ làm lộ chi tiết nội bộ và biến lỗi lập trình thành thông báo công khai. Chỉ ánh xạ các exception dự kiến; lỗi không nhận diện cần được ghi log ở server và trả thông báo chung an toàn.

## 8. Phân loại lỗi và lựa chọn ErrorType

Spring for GraphQL cung cấp `ErrorType` để phân loại lỗi thường gặp. Một số classification có thể dùng cho các tình huống như:

| Classification | Tình huống ví dụ |
| --- | --- |
| `BAD_REQUEST` | Input hoặc yêu cầu nghiệp vụ không hợp lệ |
| `UNAUTHORIZED` | Request chưa được xác thực |
| `FORBIDDEN` | Người dùng đã xác thực nhưng không có quyền |
| `NOT_FOUND` | Resource không tồn tại hoặc không được công bố |
| `INTERNAL_ERROR` | Lỗi hệ thống ngoài dự kiến |

Chọn classification theo ý nghĩa của lỗi, không chỉ theo tên exception Java. Ví dụ `AccessDeniedException` nên được phân loại là forbidden; lỗi database timeout thường là internal error. Mã lỗi trong `extensions.code` có thể chi tiết hơn classification chung.

GraphQL error classification không đồng nghĩa với HTTP status code của toàn request. Một GraphQL operation có thể trả HTTP 200 nhưng body chứa `errors`, đặc biệt khi lỗi xảy ra trong quá trình thực thi. Transport có quy tắc riêng cho một số lỗi request; client nên đọc GraphQL response body thay vì chỉ dựa vào HTTP status.

## 9. Nullability và việc lan truyền lỗi

Khi resolver ném exception, field tương ứng được xem là lỗi thực thi. GraphQL áp dụng quy tắc nullability của schema để quyết định field nào trở thành null và lỗi lan truyền tới đâu.

Ví dụ:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author!
}
```

Nếu resolver của `Book.author` lỗi, field `author` không thể trả null vì được khai báo `Author!`. Null sẽ lan truyền lên object `Book`; nếu `Query.book` nullable, kết quả `book` có thể trở thành null. Nếu mọi field cha trên đường đi đều non-null, null có thể lan đến `data` ở root.

Do đó, chọn nullability là một phần của thiết kế error behavior. Không nên đánh dấu mọi field là non-null chỉ để schema trông chặt chẽ. Hãy phản ánh khả năng dữ liệu và quyết định xem lỗi ở một field con có nên làm mất cả object cha hay không.

## 10. Validation error không đi qua handler của controller

`@GraphQlExceptionHandler` không thay thế GraphQL document validation. Ví dụ client chọn field `unknownField` không tồn tại trong schema hoặc truyền chuỗi cho argument `Int!`; request bị từ chối trước khi resolver chạy.

Các lỗi này thường được GraphQL engine tạo trực tiếp trong response. Nếu cần quan sát hoặc chuẩn hóa lỗi request ở cấp transport, có thể xem xét `WebGraphQlInterceptor` để đọc `WebGraphQlResponse` sau execution. Không nên cố bắt lỗi parse/validation trong controller vì controller method chưa được gọi.

Tương tự, lỗi xảy ra trong filter xác thực HTTP trước khi request đến GraphQL handler thuộc phạm vi Spring Security/web layer. Dùng đúng extension point cho từng giai đoạn giúp mã xử lý lỗi rõ ràng và không bỏ sót lỗi.

## 11. Xử lý lỗi authorization an toàn

Lỗi xác thực và phân quyền cần được xử lý cẩn thận vì message có thể tiết lộ sự tồn tại của resource hoặc thông tin người dùng.

Ví dụ handler cho quyền bị từ chối:

```java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.FORBIDDEN)
        .message("Bạn không có quyền thực hiện thao tác này.")
        .extensions(Map.of("code", "ACCESS_DENIED"))
        .build();
}
```

Không đưa tên role, policy nội bộ, tenant ID hoặc điều kiện quyền chi tiết vào message nếu client không cần biết. Việc ánh xạ exception thành GraphQL error cũng không thay thế kiểm tra quyền ở resolver/service. Server phải thực thi authorization trước khi trả dữ liệu hoặc thay đổi trạng thái.

Trong một số hệ thống, `NOT_FOUND` và `FORBIDDEN` được cố ý trả giống nhau để không tiết lộ resource tồn tại nhưng người dùng không được phép xem. Đây là quyết định chính sách bảo mật cần áp dụng nhất quán.

## 12. Ghi log exception mà không làm lộ dữ liệu

Client cần message dễ hiểu, còn log server cần đủ thông tin để chẩn đoán. Hai mục đích này không nên dùng chung một chuỗi exception thô.

Một handler có thể ghi log có kiểm soát trước khi trả lỗi:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    private static final Logger log =
        LoggerFactory.getLogger(GraphQlExceptionAdvice.class);

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        log.info("Book lookup failed, path={}",
            environment.getExecutionStepInfo().getPath());

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Không tìm thấy sách.")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

Với lỗi hệ thống, log exception kèm stack trace ở server theo mức độ phù hợp và gắn correlation ID/trace ID nếu ứng dụng có. Tránh log access token, cookie, toàn bộ GraphQL variables hoặc thông tin cá nhân không cần thiết. Client chỉ nhận message an toàn và mã lỗi có thể xử lý.

## 13. Kiểm thử exception handler với GraphQlTester

Có thể dùng `GraphQlTester` để xác minh exception từ resolver được chuyển thành GraphQL error. Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookController.class)
class BookExceptionHandlerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsBookNotFoundToGraphQlError() {
        graphQlTester.document("""
                query {
                    book(id: "missing-book") {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
```

Ví dụ giả định test context cung cấp `BookService` mock hoặc test bean ném `BookNotFoundException` cho ID `missing-book`. Có thể kiểm tra sâu hơn `message`, `path` và `extensions.code` theo API `ResponseError` của phiên bản Spring GraphQL đang dùng.

Nên kiểm thử các tình huống:

- Exception được ném từ root query resolver.
- Exception được ném từ nested field resolver.
- Handler cục bộ và handler trong `@ControllerAdvice` có phạm vi đúng.
- Exception không được nhận diện không làm lộ message nội bộ.
- Validation/coercion error vẫn được GraphQL engine trả về dù resolver không chạy.
- Non-null propagation phù hợp với schema.
- Authorization error không tiết lộ dữ liệu nhạy cảm.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@GraphQlExceptionHandler` không được gọi | Exception xảy ra trước resolver hoặc handler không nằm trong phạm vi | Xác định giai đoạn lỗi và kiểm tra controller/advice bean |
| Handler cục bộ không bắt exception từ controller khác | Handler chỉ áp dụng trong controller sở hữu nó | Dùng `@ControllerAdvice` cho xử lý dùng chung |
| Client nhận message nội bộ | Trả trực tiếp `exception.getMessage()` | Dùng message an toàn và mã lỗi ổn định |
| `data` trở thành null ngoài dự kiến | Field non-null gây null propagation | Rà soát nullability và xử lý lỗi field |
| Client chỉ kiểm tra HTTP status và bỏ sót lỗi | GraphQL execution error có thể đi cùng HTTP 200 | Kiểm tra cả `errors` trong GraphQL response |
| Lỗi validation không qua controller handler | Request bị từ chối trước resolver | Dùng GraphQL response/interceptor cho quan sát cấp request |
| Nhiều handler cùng nhận một exception | Advice overlap hoặc mapping không rõ | Tổ chức handler và thứ tự advice có chủ đích |

## 15. Checklist thiết kế exception handler

- Exception có thể hiện đúng lỗi nghiệp vụ và được ném từ tầng phù hợp?
- Handler được đặt cục bộ hay toàn cục đúng phạm vi?
- Message trả cho client có an toàn và dễ hiểu?
- `extensions.code` có ổn định để client xử lý?
- Classification phản ánh đúng not found, forbidden, bad request hay internal error?
- Error path và vị trí field có được giữ lại?
- Nullability của schema có tạo ra null propagation mong muốn?
- Lỗi parse/validation/coercion có được phân biệt với lỗi resolver?
- Log server đủ thông tin nhưng không chứa bí mật hoặc dữ liệu không cần thiết?
- Test đã xác minh cả response lỗi và phạm vi handler?

`@GraphQlExceptionHandler` giúp chuyển exception phát sinh trong controller resolver thành GraphQL error có cấu trúc. Dùng handler cục bộ cho quy tắc riêng của controller và `@ControllerAdvice` cho quy tắc chung; giữ message công khai an toàn, cung cấp mã lỗi ổn định trong `extensions` và chọn classification phù hợp. Đồng thời, cần hiểu lỗi parse/validation xảy ra trước resolver, quy tắc null propagation của schema và khác biệt giữa GraphQL errors với HTTP status để client xử lý lỗi chính xác.
