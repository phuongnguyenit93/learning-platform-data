# DataFetcherExceptionHandler

Trong GraphQL Java, DataFetcherExceptionHandler là SPI xử lý exception phát sinh khi một DataFetcher thực thi. Handler nhận thông tin về exception, field đang được resolve và vị trí của field trong operation; sau đó trả về DataFetcherExceptionHandlerResult chứa một hoặc nhiều GraphQLError. GraphQL engine dùng các lỗi đó để tạo ExecutionResult và áp dụng quy tắc null propagation của schema.

Với Spring for GraphQL, DataFetcherExceptionHandler là điểm mở rộng ở mức GraphQL Java. Ứng dụng Spring thường nên dùng DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler để ánh xạ exception theo cơ chế tích hợp sẵn. Chỉ thay DataFetcherExceptionHandler trực tiếp khi cần tùy biến thấp hơn và đã hiểu cách cấu hình đó tương tác với exception resolver chain của Spring.

## 1. DataFetcherExceptionHandler nằm ở đâu trong luồng thực thi?

Khi GraphQL thực thi một field, nó gọi DataFetcher tương ứng. DataFetcher có thể trả giá trị trực tiếp, trả CompletionStage hoặc ném exception. Với kết quả bất đồng bộ, CompletionStage cũng có thể hoàn tất ở trạng thái lỗi.

GraphQL Java chuyển exception trong quá trình fetch đến DataFetcherExceptionHandler. Handler chuyển exception thành GraphQLError. GraphQL engine gắn error vào response và áp dụng nullability của schema để quyết định field hoặc parent nào trở thành null.

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[Resolve field]
    B --> C[Invoke DataFetcher]
    C --> D{Fetch thành công?}
    D -->|Có| E[Giá trị field]
    D -->|Không| F[Exception]
    F --> G[DataFetcherExceptionHandler]
    G --> H[DataFetcherExceptionHandlerResult]
    H --> I[GraphQLError trong ExecutionResult]
    E --> J[GraphQL response]
    I --> J
    J --> K[Null propagation theo schema]
~~~

Handler không thay thế DataFetcher và không tạo ra giá trị nghiệp vụ thay cho field bị lỗi. Nó chỉ mô tả lỗi cần được đưa vào GraphQL result. Nếu muốn trả fallback value, resolver hoặc service phải chủ động trả giá trị phù hợp; nếu muốn trả data và errors cùng lúc, cân nhắc DataFetcherResult.

## 2. API của GraphQL Java

DataFetcherExceptionHandler có một phương thức chính:

~~~java
CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
    DataFetcherExceptionHandlerParameters handlerParameters);
~~~

Các kiểu dữ liệu quan trọng:

| Kiểu | Vai trò |
| --- | --- |
| DataFetcherExceptionHandler | Contract xử lý exception của DataFetcher |
| DataFetcherExceptionHandlerParameters | Ngữ cảnh của exception và field đang fetch |
| DataFetcherExceptionHandlerResult | Kết quả handler trả về cho GraphQL engine |
| GraphQLError | Error được thêm vào GraphQL response |
| DataFetchingEnvironment | Ngữ cảnh thực thi field, arguments, source object và context |
| ResultPath | Đường dẫn field trong response, bao gồm index của list và alias nếu có |
| SourceLocation | Vị trí field trong GraphQL document |

Handler trả CompletableFuture vì GraphQL Java hỗ trợ execution bất đồng bộ. Với mapping đơn giản, dùng CompletableFuture.completedFuture(...). Không thực hiện blocking I/O trong handler và không gọi join/get trên một future khác nếu việc đó có thể chặn thread xử lý GraphQL.

## 3. DataFetcherExceptionHandlerParameters cung cấp gì?

Parameters cung cấp thông tin cần để xây dựng error chính xác:

- getException(): exception gốc được GraphQL Java chuyển đến handler.
- getDataFetchingEnvironment(): field environment, gồm source object, arguments, GraphQLContext và field definition.
- getPath(): response path của field bị lỗi.
- getSourceLocation(): vị trí field trong document.

Ví dụ path có thể là:

~~~text
books[2].author.name
~~~

Nếu client dùng alias:

~~~graphql
query {
    featured: bookById(id: "book-01") {
        author {
            name
        }
    }
}
~~~

response path dùng response key featured, không nhất thiết là tên field bookById. Hãy giữ path do GraphQL cung cấp thay vì tự ghép chuỗi từ tên method Java.

## 4. Viết một DataFetcherExceptionHandler tùy chỉnh

Ví dụ handler tối giản:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherExceptionHandler;
import graphql.execution.DataFetcherExceptionHandlerParameters;
import graphql.execution.DataFetcherExceptionHandlerResult;
import org.springframework.stereotype.Component;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Component
public class SafeDataFetcherExceptionHandler
        implements DataFetcherExceptionHandler {

    @Override
    public CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
            DataFetcherExceptionHandlerParameters parameters) {

        GraphQLError error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Unable to complete this field")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();

        DataFetcherExceptionHandlerResult result =
            DataFetcherExceptionHandlerResult.newResult()
                .error(error)
                .build();

        return CompletableFuture.completedFuture(result);
    }
}
~~~

GraphqlErrorBuilder.newError(DataFetchingEnvironment) giúp gắn ngữ cảnh field vào error, bao gồm path và source location theo environment. ErrorType.INTERNAL_ERROR ở đây là classification của Spring for GraphQL. Nếu chỉ dùng GraphQL Java mà không có Spring, chọn ErrorClassification phù hợp với API đang dùng.

Handler trên trả message an toàn và code ổn định. Nó cố ý không đưa exception.getMessage() vào response vì message có thể chứa SQL, hostname, ID nội bộ hoặc dữ liệu nhạy cảm.

GraphQL Java có default handler là SimpleDataFetcherExceptionHandler. Handler mặc định tạo lỗi dạng ExceptionWhileDataFetching và giữ thông tin path/source location để gắn vào execution result. Khi thay bằng handler riêng, ứng dụng chịu trách nhiệm quyết định classification, message, extensions và logging; hãy kiểm tra response thực tế của phiên bản GraphQL Java đang dùng để tránh vô tình công khai exception detail.

## 5. Ánh xạ exception theo loại

Trong thực tế, không phải exception nào cũng nên trả cùng một message hoặc classification. Có thể phân nhánh theo exception:

~~~java
@Override
public CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
        DataFetcherExceptionHandlerParameters parameters) {

    Throwable exception = parameters.getException();
    GraphQLError error;

    if (exception instanceof BookNotFoundException) {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
    else if (exception instanceof AccessDeniedException) {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.FORBIDDEN)
            .message("You are not allowed to access this resource")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
    }
    else {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Unable to complete this field")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
    }

    return CompletableFuture.completedFuture(
        DataFetcherExceptionHandlerResult.newResult()
            .error(error)
            .build());
}
~~~

Ví dụ minh họa phân loại:

| Exception | GraphQL classification | Code công khai |
| --- | --- | --- |
| BookNotFoundException | NOT_FOUND | BOOK_NOT_FOUND |
| AccessDeniedException | FORBIDDEN | FORBIDDEN |
| Validation/domain input exception | BAD_REQUEST nếu phù hợp contract | INVALID_INPUT |
| Dependency timeout không thể phục hồi | INTERNAL_ERROR hoặc code dependency riêng | DEPENDENCY_UNAVAILABLE |
| Exception không dự kiến | INTERNAL_ERROR | INTERNAL_ERROR |

Không ánh xạ mọi exception thành BAD_REQUEST. Lỗi do database unavailable hoặc bug trong resolver không phải lỗi của client. Phân loại cần phản ánh đúng semantics API.

## 6. Giữ nguyên path và source location

GraphQL error có path giúp client xác định field nào bị lỗi trong response lồng nhau. Source location giúp công cụ phát triển chỉ đến vị trí trong document.

Nên tạo error từ DataFetchingEnvironment:

~~~java
GraphQLError error = GraphqlErrorBuilder
    .newError(parameters.getDataFetchingEnvironment())
    .message("Author information is temporarily unavailable")
    .errorType(ErrorType.INTERNAL_ERROR)
    .extensions(Map.of("code", "AUTHOR_UNAVAILABLE"))
    .build();
~~~

Tránh tự tạo error chỉ với message nếu đã có environment, vì bạn có thể làm mất path/location cần thiết. Với alias và list index, path do GraphQL Java cung cấp là nguồn đáng tin cậy.

Path không phải thông tin authorization. Không dựa vào path để quyết định user được phép đọc dữ liệu nào; authorization cần dựa trên principal và policy nghiệp vụ.

## 7. Xử lý exception wrapper

DataFetcher bất đồng bộ có thể hoàn tất bằng exception được bọc trong CompletionException hoặc ExecutionException. Khi cần phân loại exception gốc, có thể unwrap các wrapper phổ biến:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

private Throwable unwrap(Throwable error) {
    Throwable current = error;

    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }

    return current;
}
~~~

Sau đó phân loại:

~~~java
Throwable exception = unwrap(parameters.getException());
~~~

Chỉ unwrap những wrapper đã biết. Không đi sâu qua mọi cause một cách mù quáng vì exception gốc có thể không đại diện cho lỗi cần công bố. Giữ exception ban đầu cho logging nếu cần stack trace đầy đủ.

## 8. Đăng ký handler ở mức GraphQL Java

GraphQL Java cho phép cấu hình default DataFetcherExceptionHandler trên GraphQL.Builder. Trong Spring Boot, có thể dùng GraphQlSourceBuilderCustomizer để cấu hình GraphQL.Builder:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlJavaConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer customExceptionHandler(
            SafeDataFetcherExceptionHandler handler) {

        return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.defaultDataFetcherExceptionHandler(handler));
    }
}
~~~

Đoạn cấu hình này minh họa điểm mở rộng GraphQL Java ở mức thấp. API builder có thể khác theo phiên bản Spring Boot, Spring for GraphQL và GraphQL Java; cần kiểm tra dependency thực tế trước khi áp dụng.

Khi thay default handler, hãy xác nhận cấu hình mới không vô tình bỏ qua exception handling chain của Spring for GraphQL. Trong ứng dụng Spring, chain DataFetcherExceptionResolver là nơi tích hợp @GraphQlExceptionHandler và các resolver bean. Thay handler toàn cục có thể thay đổi hoặc bỏ qua hành vi mặc định đó.

Không đăng ký nhiều handler độc lập rồi giả định chúng tự chạy nối tiếp. GraphQL Java sử dụng một default handler cho execution; nếu cần nhiều bước phân giải, dùng resolver chain của Spring hoặc tự xây dựng chain có thứ tự rõ ràng.

## 9. Spring DataFetcherExceptionResolver là lựa chọn tích hợp

Spring for GraphQL cung cấp DataFetcherExceptionResolver để xử lý exception theo kiểu reactive và tích hợp với GraphQL execution. Spring kết hợp các resolver thành một chain. Mỗi resolver có thể xử lý exception hoặc để resolver tiếp theo thử xử lý.

Ví dụ kế thừa DataFetcherExceptionResolverAdapter:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
        }

        return null;
    }
}
~~~

Trả null có nghĩa resolver này không xử lý exception để resolver tiếp theo trong chain có thể thử. Đây là contract của Spring DataFetcherExceptionResolverAdapter; không áp dụng cách trả null cho DataFetcherExceptionHandler của GraphQL Java.

Resolver có thể trả một GraphQLError hoặc nhiều GraphQLError tùy nhu cầu. Chỉ tạo nhiều lỗi khi một exception thực sự tương ứng với nhiều lỗi field có ý nghĩa; tránh nhân bản một lỗi thành nhiều message giống nhau.

## 10. @GraphQlExceptionHandler

Với annotated controller, @GraphQlExceptionHandler là cách gần nghiệp vụ và ngắn gọn để ánh xạ exception:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> builder) {

        return builder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
~~~

Handler có thể đặt trong controller chứa DataFetcher hoặc trong @ControllerAdvice để áp dụng rộng hơn. Dùng resolver toàn cục cho lỗi dùng chung; dùng handler gần controller khi semantics phụ thuộc vào một nhóm operation cụ thể.

Không khai báo cùng một exception ở nhiều handler có phạm vi chồng lấn nếu không có quy tắc ưu tiên rõ ràng. Hãy test exception được xử lý bởi đúng handler.

## 11. Khi nào dùng DataFetcherExceptionHandler trực tiếp?

| Nhu cầu | Cách tiếp cận nên cân nhắc |
| --- | --- |
| Ánh xạ exception nghiệp vụ trong Spring controller | @GraphQlExceptionHandler |
| Resolver dùng chung nhiều controller | DataFetcherExceptionResolver hoặc DataFetcherExceptionResolverAdapter |
| Tích hợp lỗi với Spring application context | Spring resolver chain |
| Tùy biến hành vi GraphQL Java ở mức execution engine | DataFetcherExceptionHandler |
| Dùng GraphQL Java độc lập, không có Spring | DataFetcherExceptionHandler |
| Trả fallback data thay vì chỉ error | Resolver/service hoặc DataFetcherResult |
| Lỗi phát ra sau khi subscription publisher đã được trả về | SubscriptionExceptionResolver trong Spring for GraphQL |

Trong Spring application, ưu tiên abstraction của Spring nếu nó đáp ứng nhu cầu. Dùng SPI trực tiếp khi cần kiểm soát chính xác handler của GraphQL Java hoặc khi ứng dụng không sử dụng Spring GraphQL exception resolver.

## 12. Phạm vi xử lý: lỗi nào handler nhận và không nhận?

DataFetcherExceptionHandler xử lý exception phát sinh trong lúc GraphQL gọi DataFetcher, gồm lỗi đồng bộ và lỗi hoàn tất bất đồng bộ của fetch operation.

Nó không phải bộ xử lý mọi lỗi của ứng dụng:

| Loại lỗi | Nơi xử lý phù hợp |
| --- | --- |
| Exception trong DataFetcher | DataFetcherExceptionHandler hoặc Spring DataFetcherExceptionResolver |
| CompletionStage của DataFetcher hoàn tất lỗi | DataFetcherExceptionHandler hoặc Spring resolver chain |
| GraphQL document sai cú pháp | GraphQL parser/request execution |
| Field hoặc argument không hợp lệ theo schema | GraphQL validation |
| Variable không thể coercion | GraphQL input coercion |
| HTTP handshake, auth filter hoặc network failure | Web/security/transport layer |
| Exception phát ra sau khi subscription publisher đã được trả về | SubscriptionExceptionResolver |
| Exception trong code trước khi GraphQL execution bắt đầu | Application/transport layer |

Với subscription, cần phân biệt lỗi khi method tạo Publisher với lỗi stream phát ra sau đó. Lỗi khi tạo Publisher có thể xảy ra trong DataFetcher ban đầu. Lỗi onError sau khi Publisher đã được trả về thuộc lifecycle subscription và cần cơ chế SubscriptionExceptionResolver của Spring.

## 13. GraphQL null propagation

Handler trả GraphQLError; GraphQL engine vẫn áp dụng nullability của schema. Ví dụ:

~~~graphql
type Query {
    book: Book
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
~~~

Nếu resolver author lỗi, field author là non-null. GraphQL phải propagate null lên parent Book; vì book là nullable, response có thể có book: null cùng error path chỉ ra field author.

Nếu cả book cũng được khai báo non-null, null có thể lan tiếp lên data ở root. Vì vậy, thiết kế non-null cần tính đến khả năng dependency hoặc field con có thể thất bại.

DataFetcherExceptionHandler không thể ghi đè null propagation bằng cách chỉ trả một GraphQLError. Nếu cần một giá trị thay thế, hãy xử lý trong resolver hoặc trả DataFetcherResult với data/errors theo contract.

## 14. DataFetcherResult và partial data

DataFetcherExceptionHandler phù hợp khi DataFetcher ném exception và không có giá trị hợp lệ để trả. Nếu ứng dụng có thể trả dữ liệu một phần kèm cảnh báo, DataFetcherResult có thể phù hợp hơn:

~~~java
@QueryMapping
public DataFetcherResult<BookSummary> bookSummary(
        @Argument String id,
        DataFetchingEnvironment environment) {
    BookSummary summary = bookService.findSummary(id);

    GraphQLError warning = GraphqlErrorBuilder.newError(environment)
        .message("Some optional metadata is unavailable")
        .extensions(Map.of("code", "OPTIONAL_METADATA_UNAVAILABLE"))
        .build();

    return DataFetcherResult.<BookSummary>newResult()
        .data(summary)
        .error(warning)
        .build();
}
~~~

Ví dụ minh họa trường hợp có data hợp lệ và một warning/error bổ sung. Không dùng DataFetcherResult để che lỗi nghiêm trọng hoặc trả object không đầy đủ như thể mọi field đều thành công.

## 15. Logging và bảo mật error response

Handler chạy ở ranh giới giữa exception nội bộ và GraphQL response công khai. Cần tách thông tin cho client và thông tin dành cho log:

| Thông tin | GraphQL response | Log nội bộ |
| --- | --- | --- |
| Error code ổn định | Có | Có |
| Message an toàn, dễ hiểu | Có | Có thể có |
| Path của field | Có | Có |
| Execution/correlation ID | Có thể có | Có |
| Stack trace | Không | Có, khi cần |
| SQL, hostname, connection string | Không | Có kiểm soát và mask |
| Token, password, dữ liệu cá nhân | Không | Không log thô |

Không trả exception.getMessage() trực tiếp cho client. Message có thể chứa query SQL, tên bảng, địa chỉ host, file path, user ID hoặc dữ liệu từ input. Trả message chung cùng code ổn định; log exception đầy đủ ở server với access control phù hợp.

Tránh log cùng stack trace nhiều lần ở resolver, handler và global filter. Chọn một nơi sở hữu log exception để không tạo log noise. Dùng execution ID hoặc trace ID để nối response với log/trace.

## 16. Extensions và error code

GraphQL error có thể chứa extensions để client phân loại lỗi:

~~~json
{
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ],
  "data": {
    "bookById": null
  }
}
~~~

Đây là response minh họa; trường classification cụ thể phụ thuộc ErrorClassification và phiên bản. Không phụ thuộc client vào stack trace hoặc exception class nội bộ. Code như BOOK_NOT_FOUND là contract do ứng dụng kiểm soát, nên được versioning và ghi tài liệu.

Không đặt dữ liệu thay đổi theo từng request vào metric label. Error code nên có tập giá trị hữu hạn; ID và context chi tiết nên nằm trong log/trace có kiểm soát.

## 17. Kiểm thử DataFetcherExceptionHandler

Test cần xác nhận handler tạo đúng GraphQL error và GraphQL engine giữ đúng path. Với Spring for GraphQL, GraphQlTester có thể thực thi operation thật:

~~~java
@Test
void mapsBookNotFoundToGraphQlError() {
    var response = graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
            .isEqualTo("Book not found");
        assertThat(errors.get(0).getPath())
            .containsExactly("bookById");
        assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
    });
}
~~~

Nếu dùng Spring DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler, test này xác nhận tích hợp Spring thực tế. Nếu thay GraphQL Java DataFetcherExceptionHandler trực tiếp, cần test cấu hình GraphQlSource/GraphQL.Builder đã đăng ký đúng handler.

## 18. Những trường hợp nên kiểm thử

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| DataFetcher thành công | Không có error ngoài dự kiến |
| Exception đồng bộ | Handler được gọi và error có path đúng |
| CompletionStage hoàn tất lỗi | Exception wrapper được xử lý theo policy |
| BookNotFoundException | Classification NOT_FOUND và code BOOK_NOT_FOUND |
| AccessDeniedException | Không lộ dữ liệu và classification phù hợp |
| Exception không xác định | INTERNAL_ERROR và message an toàn |
| Alias trong query | Path dùng response key alias |
| Field nằm trong list | Path giữ đúng index |
| Field non-null lỗi | Null propagation đúng schema |
| Request parse/validation lỗi | Không nhầm là DataFetcher exception |
| Subscription publisher phát onError | SubscriptionExceptionResolver xử lý |
| DataFetcherResult có partial data | Data và errors cùng được trả đúng contract |

Nên test cả response và side effect. Ví dụ khi authorization thất bại, xác nhận service không trả dữ liệu nhạy cảm; khi lỗi validation xảy ra, mutation không ghi dữ liệu.

## 19. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng DataFetcherExceptionHandler để xử lý mọi lỗi HTTP | Không bắt được lỗi parse, auth filter hoặc transport | Xử lý đúng tầng request/transport |
| Nhầm handler GraphQL Java với DataFetcherExceptionResolver của Spring | Cấu hình sai abstraction hoặc bỏ qua resolver chain | Phân biệt SPI thấp và Spring integration |
| Trả exception message cho client | Rò rỉ SQL, host hoặc dữ liệu nội bộ | Dùng message an toàn và error code |
| Tạo GraphQLError không có path | Client khó xác định field lỗi | Dùng GraphqlErrorBuilder.newError(environment) |
| Chặn thread trong handleException | Giảm throughput hoặc deadlock | Trả CompletableFuture và tránh blocking |
| Trả null từ DataFetcherExceptionHandler | Không tuân thủ contract của GraphQL Java | Luôn trả DataFetcherExceptionHandlerResult |
| Thay default handler và bỏ qua Spring resolver chain | @GraphQlExceptionHandler có thể không chạy như mong đợi | Ưu tiên Spring resolver hoặc test rõ cấu hình |
| Ánh xạ mọi lỗi thành BAD_REQUEST | Che lỗi server/dependency | Phân loại theo semantics |
| Dùng handler để tạo fallback data | Trộn error mapping với business logic | Dùng resolver/service hoặc DataFetcherResult |
| Xử lý subscription stream error bằng handler fetch ban đầu | Bỏ sót lỗi phát sau khi Publisher được trả về | Dùng SubscriptionExceptionResolver |

## 20. Nguyên tắc sử dụng DataFetcherExceptionHandler

DataFetcherExceptionHandler là SPI mức thấp của GraphQL Java, nhận exception cùng DataFetchingEnvironment và trả DataFetcherExceptionHandlerResult bất đồng bộ. Dùng GraphqlErrorBuilder với environment để giữ path và source location; phân loại lỗi bằng ErrorClassification phù hợp và chỉ đưa message/code an toàn vào response.

Trong Spring for GraphQL, ưu tiên DataFetcherExceptionResolver, DataFetcherExceptionResolverAdapter hoặc @GraphQlExceptionHandler cho xử lý lỗi nghiệp vụ. Nếu cấu hình DataFetcherExceptionHandler trực tiếp, hãy xác nhận nó không làm mất resolver chain mặc định. Phân biệt exception của DataFetcher với lỗi parse/validation, transport và subscription publisher.

Kiểm thử path, alias, list index, classification, extensions, null propagation, async failure và message bảo mật bằng GraphQlTester. Handler nên làm nhiệm vụ chuyển exception thành GraphQL error; business fallback, partial data, authorization và transaction phải được xử lý ở lớp phù hợp.

## Tài liệu tham khảo

- [GraphQL Java — DataFetcherExceptionHandler API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandler.html)
- [GraphQL Java — DataFetcherExceptionHandlerParameters API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandlerParameters.html)
- [GraphQL Java — DataFetcherExceptionHandlerResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandlerResult.html)
- [Spring for GraphQL — Request Execution and Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
