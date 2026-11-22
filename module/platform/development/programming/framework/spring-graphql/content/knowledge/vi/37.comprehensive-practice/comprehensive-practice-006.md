# Thêm GraphQL error handler

## Mục tiêu

Sau bài thực hành này, bạn có thể:

- Tạo GraphQL error handler cho exception phát sinh từ resolver.
- Dùng @GraphQlExceptionHandler ở controller hoặc @ControllerAdvice.
- Chọn ErrorType phù hợp và công bố error code ổn định qua extensions.
- Giữ lại field path và source location của GraphQL error.
- Dùng DataFetcherExceptionResolverAdapter cho DataFetcher tùy chỉnh.
- Phân biệt field execution errors với request-level errors và subscription errors.
- Kiểm thử error contract bằng GraphQlTester.
- Tránh để lộ SQL, stack trace, token hoặc thông tin nội bộ trong GraphQL response.

## Bài toán

API thư viện có query lấy sách theo ID. Khi sách không tồn tại, service ném BookNotFoundException. Nếu exception đi thẳng tới GraphQL engine, Spring for GraphQL sẽ xử lý theo cơ chế mặc định và trả lỗi nội bộ chung khi không có resolver nào nhận exception.

Client cần một error contract ổn định để phân biệt:

- Sách không tồn tại.
- Dữ liệu đầu vào không hợp lệ.
- Người dùng chưa đăng nhập.
- Người dùng không có quyền.
- Lỗi không mong đợi ở server.

Ta sẽ thêm một @ControllerAdvice để ánh xạ domain exception thành GraphQLError. Mỗi error có message an toàn, ErrorType và mã extensions.code để client xử lý mà không phải phân tích nội dung message.

## Khai báo schema và resolver

Tạo schema trong src/main/resources/graphql/book.graphqls:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Field book nullable để khi không tìm thấy sách, GraphQL có thể trả book: null cùng error tại field đó. Nếu đổi thành Book!, lỗi sẽ lan null lên parent theo quy tắc Non-Null của GraphQL.

Domain exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Service:

~~~java
public interface BookService {

    Book findById(String id);
}
~~~

Resolver:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Resolver không cần tự bắt BookNotFoundException. Exception được chuyển tới error handler tại ranh giới GraphQL data fetching.

## Tạo global error handler bằng @ControllerAdvice

@GraphQlExceptionHandler khai báo một method xử lý exception từ data fetching. Khi đặt trong một @Controller, handler chỉ áp dụng cho các mapping method thuộc controller đó. Khi đặt trong @ControllerAdvice, handler có thể áp dụng cho các GraphQL controller trong application.

Tạo handler dùng chung:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách được yêu cầu.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Spring for GraphQL chuẩn bị GraphqlErrorBuilder<?> theo DataFetchingEnvironment của field đang lỗi. Vì vậy, error giữ được path và locations tương ứng. Đây là cách nên dùng trong annotated exception handler; nếu tự tạo builder rỗng bằng GraphqlErrorBuilder.newError() thì có thể làm mất thông tin vị trí field.

Exception message nội bộ vẫn có thể chứa ID hoặc chi tiết kỹ thuật. Handler trả một message an toàn và mã lỗi ổn định, không chuyển nguyên exception.getMessage() tới client.

### Xử lý nhiều loại exception

Một handler có thể định nghĩa nhiều method, mỗi method xử lý một nhóm exception. Khi annotation không chỉ rõ value, Spring suy ra loại exception từ tham số exception trong chữ ký method:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách được yêu cầu.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidInput(
            BindException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ.")
                .extensions(Map.of("code", "INPUT_INVALID"))
                .build();
    }
}
~~~

Nếu cần chỉ định loại exception tường minh, có thể truyền một hoặc nhiều class vào value của @GraphQlExceptionHandler, ví dụ @GraphQlExceptionHandler({BookNotFoundException.class, LegacyBookException.class}). Chữ ký method phải nhận kiểu cha chung tương thích với các loại đã khai báo, thường là RuntimeException hoặc Throwable.

Với validation, có thể cần trả nhiều lỗi cho các field input. @GraphQlExceptionHandler hỗ trợ trả Collection<GraphQLError> để client nhận nhiều lỗi trong cùng response. Hãy chuẩn hóa cấu trúc extension và tên field input theo contract của API.

## Chọn ErrorType và error code

ErrorType là nhóm phân loại chung do Spring for GraphQL cung cấp. extensions.code là mã nghiệp vụ ổn định do ứng dụng thiết kế.

| ErrorType | Dùng khi | Ví dụ extensions.code |
| --- | --- | --- |
| BAD_REQUEST | Input hoặc yêu cầu nghiệp vụ không hợp lệ | INPUT_INVALID |
| UNAUTHORIZED | Chưa xác thực hoặc credential không hợp lệ | AUTHENTICATION_REQUIRED |
| FORBIDDEN | Đã xác thực nhưng không được phép thực hiện | ACCESS_DENIED |
| NOT_FOUND | Không tìm thấy resource | BOOK_NOT_FOUND |
| INTERNAL_ERROR | Lỗi bất ngờ hoặc lỗi nội bộ | INTERNAL_ERROR |

Không dùng NOT_FOUND cho mọi exception chỉ vì muốn tránh trả HTTP 500. Phân loại cần phản ánh nguyên nhân để client có thể xử lý đúng.

ErrorType có số lượng giá trị hữu hạn, phù hợp để phân loại tổng quát. extensions.code nên có danh sách mã riêng, ổn định và có tài liệu. Không dùng message làm mã lỗi vì message có thể đổi theo ngôn ngữ hoặc cách diễn đạt.

ErrorType là phân loại GraphQL error, không phải chỉ thị tự động đặt HTTP status theo mã lỗi. Transport vẫn áp dụng quy tắc status riêng; client nên đọc GraphQL response và extensions.code thay vì suy luận từ HTTP status.

Ví dụ client có thể xử lý:

~~~json
{
  "errors": [
    {
      "message": "Không tìm thấy sách được yêu cầu.",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ],
  "data": {
    "book": null
  }
}
~~~

Phần classification trong JSON là cách GraphQL Java/Spring biểu diễn ErrorType; các trường response cụ thể còn phụ thuộc error serializer và phiên bản. Client nên dựa vào extensions.code do ứng dụng quản lý.

## Handler cục bộ trong controller

Nếu exception chỉ có ý nghĩa với một controller, có thể đặt handler ngay trong controller:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Chọn phạm vi theo trách nhiệm:

- Handler trong controller: lỗi đặc thù của controller đó.
- @ControllerAdvice: lỗi dùng chung giữa nhiều controller.
- DataFetcherExceptionResolver: lỗi từ các DataFetcher không được triển khai bằng annotated controller.

Không khai báo cùng một exception ở nhiều handler có phạm vi chồng lấn nếu không có lý do rõ ràng. Handler trùng lặp khiến việc xác định nơi ánh xạ lỗi khó hơn.

## Xử lý exception từ DataFetcher tùy chỉnh

@GraphQlExceptionHandler được áp dụng tự động cho lời gọi controller method. Nếu ứng dụng đăng ký một graphql.schema.DataFetcher trực tiếp qua RuntimeWiringConfigurer, exception của data fetcher đó không đi qua controller exception handler.

Spring for GraphQL cung cấp DataFetcherExceptionResolver. Có thể kế thừa DataFetcherExceptionResolverAdapter để ánh xạ exception đồng bộ:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import java.util.Map;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class CatalogDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof CatalogUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("Dịch vụ danh mục hiện không khả dụng.")
                    .extensions(Map.of("code", "CATALOG_UNAVAILABLE"))
                    .build();
        }

        // Trả null để resolver tiếp theo có cơ hội xử lý.
        return null;
    }
}
~~~

Spring Boot GraphQL starter tự phát hiện các bean DataFetcherExceptionResolver và đăng ký chúng với GraphQL engine. Có thể khai báo nhiều resolver; chúng được gọi theo thứ tự cho tới khi một resolver xử lý exception.

DataFetcherExceptionResolverAdapter cung cấp resolveToSingleError và resolveToMultipleErrors. Trả null từ các method này có nghĩa exception chưa được resolver hiện tại xử lý; Spring có thể chuyển sang resolver tiếp theo. Nếu không resolver nào xử lý, default handler trả lỗi INTERNAL_ERROR với message chung và execution ID để tránh lộ chi tiết implementation.

Trong ví dụ, CatalogUnavailableException là exception từ một custom data fetcher gọi dịch vụ catalog. Với controller method thông thường, ưu tiên @GraphQlExceptionHandler vì code ngắn và gắn trực tiếp với programming model.

## Những lỗi không được xử lý bởi data-fetcher error handler

Không phải mọi lỗi GraphQL đều đi qua @GraphQlExceptionHandler hoặc DataFetcherExceptionResolver.

| Loại lỗi | Vì sao không đi qua handler data fetcher | Nơi xử lý |
| --- | --- | --- |
| Parse error | Document không thể parse, chưa có field nào được thực thi | GraphQL engine trả request error |
| Validation error | Document không phù hợp schema, chưa gọi data fetcher | GraphQL engine trả request error; có thể dùng WebGraphQlInterceptor để biến đổi response |
| Variable coercion error | Variables không chuyển được sang kiểu schema trước execution | GraphQL engine trả request error |
| Exception trong resolver | Xảy ra khi data fetcher đang chạy | @GraphQlExceptionHandler hoặc DataFetcherExceptionResolver |
| Exception từ Subscription Publisher sau khi resolver trả về | Publisher chỉ phát lỗi sau khi data fetcher đã tạo publisher | SubscriptionExceptionResolver |
| WebSocket disconnect hoặc HTTP timeout | Lỗi transport, có thể không có GraphQL response | Transport/client/server handling |

DataFetcherExceptionResolver chỉ xử lý lỗi phát sinh khi data fetcher được gọi. Ví dụ query sai cú pháp hoặc chọn field không tồn tại sẽ bị từ chối trước execution nên không thể xử lý bằng resolver này.

Với request-level errors cần biến đổi, có thể dùng WebGraphQlInterceptor để quan sát ExecutionResult sau khi ExecutionGraphQlService xử lý. Không dùng interceptor để thay thế error mapping cho exception nghiệp vụ từ resolver.

Với subscription, DataFetcherExceptionResolver chỉ nhìn thấy lỗi khi data fetcher tạo publisher. Nếu publisher phát error signal sau đó, cần SubscriptionExceptionResolver để chuyển lỗi thành GraphQL errors gửi qua WebSocket hoặc transport tương ứng.

## GraphQL error response và partial data

Khi một field resolver ném exception, GraphQL có thể trả data một phần cùng errors:

~~~graphql
query {
  book(id: "missing") {
    id
    title
  }
}
~~~

Với schema book: Book nullable, response có thể là:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách được yêu cầu.",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Nếu query có nhiều root field và chỉ một field lỗi, các field còn lại vẫn có thể trả data. Client phải đọc cả data lẫn errors; không được bỏ toàn bộ data chỉ vì errors có mặt.

path dùng response key của field, vì vậy alias sẽ xuất hiện trong path thay cho tên schema field. locations trỏ tới vị trí field trong GraphQL document. Khi dùng GraphqlErrorBuilder<?> được inject, handler giữ được metadata này.

Nullability quyết định phạm vi null propagation:

- Field nullable bị lỗi: field đó có thể trở thành null, các sibling field vẫn có thể giữ data.
- Field non-null bị lỗi: null lan lên parent gần nhất có thể nhận null.
- Nếu root data không còn parent nullable để dừng lan truyền, data có thể trở thành null.

Thiết kế nullability và error contract cần nhất quán. Không đánh dấu mọi field là non-null nếu client cần tiếp tục hiển thị phần dữ liệu không bị lỗi.

## Kiểm thử error handler bằng GraphQlTester

Thêm dependency test nếu dự án chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
~~~

Với Spring Boot 4, @GraphQlTest tự cấu hình GraphQL infrastructure và GraphQlTester, không cần khởi động HTTP server. Controller advice có thể được import tường minh trong test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
@Import(GlobalGraphQlExceptionHandler.class)
class BookErrorHandlerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void mapsBookNotFoundToGraphQlError() {
        given(bookService.findById("missing"))
                .willThrow(new BookNotFoundException("missing"));

        graphQlTester.document("""
                query BookDetails {
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
                    assertThat(errors.get(0).getMessage())
                            .isEqualTo("Không tìm thấy sách được yêu cầu.");
                    assertThat(errors.get(0).getPath())
                            .containsExactly("book");
                    assertThat(errors.get(0).getExtensions())
                            .containsEntry("code", "BOOK_NOT_FOUND");
                });
    }
}
~~~

Test xác minh ba phần của error contract:

1. Message trả về là nội dung an toàn đã định nghĩa.
2. Path trỏ đúng field book.
3. Extension code là BOOK_NOT_FOUND, không phụ thuộc message.

@GraphQlTest chỉ nạp một phần application context. Các service/repository cần được mock hoặc import riêng. Với Spring Boot 3.x, package của @GraphQlTest là org.springframework.boot.test.autoconfigure.graphql.GraphQlTest; từ Spring Boot 4, package chuyển sang org.springframework.boot.graphql.test.autoconfigure.GraphQlTest.

Nếu test cần HTTP filter, security chain hoặc transport behavior, dùng @SpringBootTest kết hợp HttpGraphQlTester thay cho slice test.

### Danh sách test nên có

| Trường hợp | Điều cần xác minh |
| --- | --- |
| BookNotFoundException | NOT_FOUND và BOOK_NOT_FOUND |
| BindException hoặc lỗi input | BAD_REQUEST và INPUT_INVALID |
| AccessDeniedException | FORBIDDEN và ACCESS_DENIED |
| AuthenticationException | UNAUTHORIZED và AUTHENTICATION_REQUIRED |
| Exception không được ánh xạ | INTERNAL_ERROR và message chung |
| Nested resolver lỗi | Path có đủ parent/field segment |
| Field có alias | Path dùng alias trong response |
| Field nullable bị lỗi | Partial data được giữ |
| Field non-null bị lỗi | Null propagation đúng schema |
| Custom DataFetcher exception | DataFetcherExceptionResolver xử lý |
| Request validation error | Không gọi data-fetcher resolver |

## Nguyên tắc bảo mật khi trả lỗi

GraphQL error là một phần public API response. Không trả nguyên exception message hoặc stack trace cho client trong production.

Không đưa các thông tin sau vào message hoặc extensions:

- SQL statement, tên bảng và chi tiết database.
- Đường dẫn file, hostname, internal URL hoặc tên class implementation.
- Stack trace, token, password, session ID hoặc secret.
- Thông tin cá nhân của người dùng khác.
- Giá trị input nhạy cảm mà client không cần biết.

Hãy dùng message ngắn, có thể hiển thị cho người dùng; extensions.code ổn định cho logic client; executionId hoặc trace ID trong log nội bộ để điều tra. Default handler của Spring for GraphQL cũng dùng message chung cho exception chưa được xử lý và ghi log cùng execution ID.

Không ánh xạ mọi exception thành BAD_REQUEST. Nếu database hoặc downstream service gặp lỗi, việc phân loại thành lỗi input sẽ khiến client hiểu sai và có thể không báo sự cố cho vận hành.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @GraphQlExceptionHandler không được gọi | Exception phát sinh từ custom DataFetcher không phải controller method | Dùng DataFetcherExceptionResolver |
| Handler chỉ chạy ở một controller | Handler được đặt trong @Controller | Chuyển sang @ControllerAdvice nếu cần dùng chung |
| Response thiếu path hoặc locations | Tự tạo GraphQLError bằng builder không gắn DataFetchingEnvironment | Inject GraphqlErrorBuilder<?> hoặc dùng newError(environment) |
| Client phải phân tích message để biết lỗi | Chưa có extensions.code ổn định | Định nghĩa error code và contract |
| Lỗi database bị trả nguyên exception message | Handler truyền exception.getMessage() | Dùng message an toàn, giữ chi tiết trong log |
| Request sai field không vào handler | Validation thất bại trước khi data fetcher chạy | Để GraphQL engine xử lý request error hoặc dùng WebGraphQlInterceptor khi cần |
| Subscription publisher error không được map | DataFetcherExceptionResolver chỉ xử lý lúc tạo Publisher | Đăng ký SubscriptionExceptionResolver |
| Dữ liệu sibling biến mất sau một field error | Field non-null làm null lan lên parent | Rà soát nullability theo contract |
| Nhiều resolver cùng xử lý một exception | Resolver chain hoặc handler scope chồng lấn | Phân định trách nhiệm và thứ tự resolver |
| Test báo lỗi dù đang kiểm tra error mong đợi | GraphQlTester mặc định coi errors là assertion failure khi verify | Dùng errors().expect(...) hoặc errors().satisfy(...) để kiểm tra |

## Thực hành tổng hợp

Hoàn thiện error handling cho API thư viện:

1. Tạo schema Query.book(id: ID!): Book.
2. Viết BookNotFoundException và để service ném exception khi không có sách.
3. Viết BookController với @QueryMapping.
4. Tạo GlobalGraphQlExceptionHandler bằng @ControllerAdvice.
5. Dùng @GraphQlExceptionHandler ánh xạ BookNotFoundException sang NOT_FOUND và BOOK_NOT_FOUND.
6. Thêm handler cho BindException với BAD_REQUEST và INPUT_INVALID.
7. Tạo DataFetcherExceptionResolverAdapter cho một custom DataFetcher gọi dịch vụ ngoài.
8. Gửi query có ID không tồn tại và kiểm tra errors.message, errors.path, errors.extensions.code.
9. Kiểm tra field nullable trả partial data đúng như schema.
10. Gửi query có field không tồn tại để xác minh request-level validation error không đi qua data-fetcher handler.
11. Thử exception chưa được xử lý và xác minh default INTERNAL_ERROR không lộ chi tiết nội bộ.
12. Viết test cho lỗi authorization và kiểm tra mã UNAUTHORIZED/FORBIDDEN tương ứng.

Sau khi hoàn thành, hãy giải thích vì sao cần phân biệt @GraphQlExceptionHandler với DataFetcherExceptionResolver, vì sao request validation error không đi qua hai cơ chế này và tại sao client nên dựa vào extensions.code.

## Ghi nhớ

Thêm GraphQL error handler bằng @GraphQlExceptionHandler để ánh xạ exception từ annotated controller thành GraphQLError. Đặt trong @Controller nếu chỉ áp dụng cục bộ hoặc @ControllerAdvice nếu dùng chung. Inject GraphqlErrorBuilder<?> để giữ path và locations; phân loại bằng ErrorType và công bố mã ổn định trong extensions.code. Với custom DataFetcher, dùng DataFetcherExceptionResolverAdapter. Request parse/validation errors xảy ra trước execution; subscription publisher errors cần SubscriptionExceptionResolver. Kiểm thử error contract bằng GraphQlTester và luôn trả message an toàn, không để lộ chi tiết nội bộ.

## Tài liệu tham khảo

- [Spring for GraphQL – Annotated Controllers, @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL – Request Execution, Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL – Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [DataFetcherExceptionResolverAdapter API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolverAdapter.html)
