# graphql.error.type

Spring for GraphQL dùng Micrometer Observation để ghi nhận thời gian và kết quả của GraphQL request, từng DataFetcher và DataLoader. Một trong các key quan trọng là `graphql.error.type`. Key này giúp quan sát loại lỗi xảy ra trong lúc fetch dữ liệu, từ đó tìm field đang lỗi và nhóm nguyên nhân cần xử lý.

Trong observation mặc định của `graphql.datafetcher`, `graphql.error.type` là low-cardinality key có giá trị là class name của lỗi phát sinh trong data fetching. Nó cũng xuất hiện trong observation `graphql.dataloader` khi một lần batch loading gặp lỗi. Đây là thông tin phục vụ metrics/tracing; nó không đồng nghĩa với enum `org.springframework.graphql.execution.ErrorType` được dùng để phân loại GraphQL error gửi về client.

Phân biệt hai khái niệm này rất quan trọng. Ví dụ, resolver ném `BookNotFoundException` rồi exception handler chuyển lỗi thành `ErrorType.NOT_FOUND`. Observation có thể ghi nhận class của exception ở `graphql.error.type`, còn GraphQL response mang classification `NOT_FOUND`. Một giá trị mô tả lỗi ở tầng thực thi, giá trị còn lại mô tả loại lỗi theo contract API.

## 1. `graphql.error.type` là gì?

`graphql.error.type` là key trong metadata của Micrometer observation cho hoạt động data fetching. Với convention mặc định, nó biểu diễn class name của exception/error xảy ra khi DataFetcher hoặc DataLoader thực hiện công việc.

Ví dụ các giá trị có thể gặp tùy exception của ứng dụng:

| Lỗi trong data fetching | Giá trị quan sát minh họa |
| --- | --- |
| `BookNotFoundException` | `BookNotFoundException` |
| `AccessDeniedException` | `AccessDeniedException` |
| `DataIntegrityViolationException` | `DataIntegrityViolationException` |
| `TimeoutException` | `TimeoutException` |
| Không có lỗi | Observation có outcome thành công; convention xử lý giá trị error theo phiên bản |

Tên class giúp nhóm lỗi theo loại exception. Nó hữu ích hơn việc đưa toàn bộ message vào metric tag, vì message thường chứa ID, tên người dùng, query value hoặc dữ liệu thay đổi theo từng request.

Key này được định nghĩa là low-cardinality. Điều đó có nghĩa giá trị nên thuộc một tập hữu hạn và ổn định để hệ thống metrics không tạo quá nhiều time series. Dùng các exception class có ý nghĩa nghiệp vụ và số lượng hữu hạn giúp giữ cardinality ở mức kiểm soát được.

## 2. Phân biệt error type của observation và GraphQL ErrorType

Spring GraphQL có hai khái niệm cùng mang tên error type nhưng phục vụ hai mục đích khác nhau:

| Khái niệm | Nằm ở đâu | Giá trị biểu diễn | Mục đích |
| --- | --- | --- | --- |
| `graphql.error.type` | Micrometer observation `graphql.datafetcher` hoặc `graphql.dataloader` | Class name của lỗi data fetching | Metrics và tracing để chẩn đoán lỗi thực thi |
| `org.springframework.graphql.execution.ErrorType` | GraphQL `GraphQLError` | `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `INTERNAL_ERROR` | Phân loại lỗi trong GraphQL response để client hiểu semantics |

`ErrorType` của Spring GraphQL implements GraphQL Java `ErrorClassification`. Nó giúp ứng dụng phân loại lỗi theo ý nghĩa API:

- `BAD_REQUEST`: DataFetcher không thể hoặc không muốn lấy dữ liệu do lỗi được xem là từ phía client.
- `UNAUTHORIZED`: thiếu thông tin xác thực hợp lệ.
- `FORBIDDEN`: người gọi đã được xác thực nhưng không được phép đọc dữ liệu.
- `NOT_FOUND`: không tìm thấy dữ liệu hoặc ứng dụng không muốn tiết lộ dữ liệu đó có tồn tại.
- `INTERNAL_ERROR`: lỗi bất ngờ khiến DataFetcher không thể lấy dữ liệu.

Ví dụ một exception được ánh xạ:

~~~java
@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

Trong ví dụ này:

- Exception gốc là `BookNotFoundException`.
- Classification được gửi trong GraphQL error là `NOT_FOUND`.
- Observation data fetching có thể ghi nhận exception class ở `graphql.error.type`.

Không thay thế exception class bằng enum API trong đầu óc khi đọc dashboard. Hai giá trị trả lời hai câu hỏi khác nhau: lỗi nào phát sinh trong code, và client được thông báo lỗi thuộc nhóm nào.

## 3. Observation nào chứa key này?

Spring for GraphQL có các observation chính:

| Observation name | Phạm vi | Key liên quan |
| --- | --- | --- |
| `graphql.request` | Toàn bộ một GraphQL request | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | Một DataFetcher không tầm thường | `graphql.error.type`, `graphql.field.name`, `graphql.outcome` |
| `graphql.dataloader` | Một lần gọi DataLoader hoặc `@BatchMapping` | `graphql.error.type`, `graphql.loader.name`, `graphql.outcome` |

DataFetcher observation chỉ được tạo cho các hoạt động fetch được xem là non-trivial. Việc đọc property đơn giản từ một Java object thường là trivial và không tạo observation riêng. Vì vậy, không phải mọi field trong selection set đều có một sample `graphql.datafetcher`.

DataLoader observation theo dõi các lần gọi `@BatchMapping` và DataLoader được đăng ký thủ công. Nếu batch load lỗi, `graphql.error.type` giúp phân nhóm lỗi theo exception class; `graphql.loader.name` chỉ ra loader nào bị ảnh hưởng.

## 4. Các key mặc định của DataFetcher observation

Convention mặc định tạo các low-cardinality key:

| Key | Ý nghĩa |
| --- | --- |
| `graphql.error.type` | Class name của lỗi data fetching |
| `graphql.field.name` | Tên field đang được fetch |
| `graphql.outcome` | `SUCCESS` hoặc `ERROR` |

Key high-cardinality mặc định:

| Key | Ý nghĩa |
| --- | --- |
| `graphql.field.path` | Đường dẫn field trong GraphQL execution, ví dụ `/bookById` |

High-cardinality key phù hợp để bổ sung ngữ cảnh cho trace, nhưng không nên dùng làm metric label có số lượng giá trị lớn. Field path có thể khác nhau theo cấu trúc query và alias, vì vậy hãy kiểm tra quy ước export của Micrometer khi dùng nó trong tracing.

Ví dụ một lỗi ở field `Book.author` có thể tạo observation với các thuộc tính tương tự:

~~~text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: ERROR
graphql.error.type: AuthorServiceUnavailableException
graphql.field.path: /books/0/author
~~~

Đây là ví dụ minh họa giá trị, không phải output cố định cho mọi phiên bản hoặc mọi exporter. Field path thực tế phụ thuộc response path, alias và cấu trúc operation.

## 5. Key của GraphQL request observation

`graphql.request` đo toàn bộ thời gian thực thi một GraphQL request. Các low-cardinality key mặc định gồm:

| Key | Ý nghĩa |
| --- | --- |
| `graphql.operation.type` | `query`, `mutation`, `subscription` hoặc `operation` khi không parse được document |
| `graphql.outcome` | Kết quả tổng thể của GraphQL request |

`graphql.outcome` có các giá trị chính:

- `SUCCESS`: response GraphQL hợp lệ và không có errors.
- `REQUEST_ERROR`: không parse được request, hoặc response có errors nhưng không có error nào mang `ErrorType.INTERNAL_ERROR`.
- `INTERNAL_ERROR`: không tạo được GraphQL response hợp lệ, hoặc response có ít nhất một error mang `ErrorType.INTERNAL_ERROR`.

Điều này có nghĩa một GraphQL response có HTTP 200 vẫn có thể có `graphql.outcome=REQUEST_ERROR`. Ví dụ, một field trả `NOT_FOUND` trong response cùng partial data có thể khiến request outcome là REQUEST_ERROR theo convention. HTTP status và GraphQL outcome đo hai tầng khác nhau.

Request observation cũng có high-cardinality keys như execution ID và operation name. Chúng hữu ích để tìm một trace hoặc một request cụ thể, nhưng không phù hợp làm metric tag có cardinality lớn.

## 6. Exception đi vào observation như thế nào?

Khi DataFetcher thực thi, GraphQL instrumentation bao quanh hoạt động fetch và tạo observation. Nếu fetch thành công, outcome là success. Nếu DataFetcher ném exception, observation có thể ghi error và class của exception vào `graphql.error.type`.

Sau đó, cơ chế xử lý exception của Spring for GraphQL quyết định GraphQL error được trả về client như thế nào. Spring đăng ký DataFetcher exception handler mặc định và hỗ trợ nhiều `DataFetcherExceptionResolver`. Với annotated controller, có thể dùng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice`.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[GraphQL request observation]
    B --> C[DataFetcher observation]
    C --> D{DataFetcher chạy thành công?}
    D -->|Có| E[graphql.outcome = SUCCESS]
    D -->|Không| F[Capture exception class]
    F --> G[graphql.error.type]
    F --> H[DataFetcherExceptionResolver]
    H --> I[GraphQL ErrorClassification]
    I --> J[GraphQL response errors]
    E --> K[GraphQL response]
    J --> K
    K --> L[graphql.request outcome]
~~~

`graphql.error.type` mô tả exception trong hoạt động fetch. `ErrorType` mô tả classification của GraphQL error sau khi xử lý. Khi exception được map, cả hai thông tin có thể cùng hữu ích để đối chiếu log, trace và response.

## 7. Mapping exception thành GraphQL ErrorType

Với annotated controller, `@GraphQlExceptionHandler` cho phép xây dựng GraphQL error bằng `GraphqlErrorBuilder` đã được chuẩn bị theo `DataFetchingEnvironment` hiện tại:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument Long id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handle(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

Nếu muốn áp dụng handler cho nhiều controller, đặt method trong `@ControllerAdvice`. Với DataFetcher không được tạo từ annotated controller, dùng `DataFetcherExceptionResolver` hoặc `DataFetcherExceptionResolverAdapter`.

Nên trả message an toàn và hữu ích cho client. Stack trace, SQL, tên host nội bộ, access token và chi tiết hạ tầng cần nằm trong log nội bộ có kiểm soát, không đưa vào GraphQL response.

Nếu exception không được resolver nào xử lý, Spring GraphQL mặc định phân loại thành `INTERNAL_ERROR` và trả message tổng quát có execution ID. Exception chưa được resolve được log ở ERROR; exception đã được resolve được log ở DEBUG theo cơ chế mặc định. Có thể dùng execution ID để nối error phía client với log server.

## 8. Request-level error không có DataFetcher error type

Không phải mọi GraphQL error đều phát sinh từ DataFetcher. Một số lỗi xảy ra trước execution:

- GraphQL document sai cú pháp.
- Field hoặc argument không tồn tại trong schema.
- Variable không đúng kiểu.
- Operation không hợp lệ hoặc không thể chọn để thực thi.

Những lỗi này là request-level errors. Chúng không có field path và không đi qua DataFetcher exception resolver vì chưa có DataFetcher nào được gọi. Do đó, không nên mong đợi luôn có một `graphql.datafetcher` observation hoặc một `graphql.error.type` tương ứng cho lỗi parse/validation.

Ở mức request, hãy xem `graphql.outcome` và error events của trace. Nếu cần tùy chỉnh request-level errors, xem xét `WebGraphQlInterceptor` hoặc transport-level handling phù hợp; `DataFetcherExceptionResolver` không xử lý lỗi xảy ra trước execution.

### Lưu ý với subscription publisher

Subscription DataFetcher ban đầu thường trả về một Publisher. Nếu method tạo Publisher thành công nhưng Publisher phát error sau đó, lỗi xảy ra sau lần gọi DataFetcher ban đầu. `DataFetcherExceptionResolver` không xử lý lỗi phát ra từ subscription Publisher; Spring for GraphQL có contract `SubscriptionExceptionResolver` để chuyển lỗi stream thành GraphQL error cho transport.

Vì vậy, khi điều tra subscription, hãy phân biệt lỗi lúc tạo Publisher với lỗi trong lúc stream đang chạy. Không giả định mọi lỗi subscription đều xuất hiện dưới `graphql.error.type` của DataFetcher observation ban đầu. Hãy kiểm tra subscription error handling, WebSocket trace/transport và log có execution hoặc connection context phù hợp.

## 9. DataLoader và graphql.error.type

`graphql.dataloader` observation theo dõi lần gọi DataLoader, bao gồm `@BatchMapping` và DataLoader được đăng ký thủ công. Các low-cardinality key mặc định gồm:

| Key | Ý nghĩa |
| --- | --- |
| `graphql.error.type` | Class name của lỗi trong data loading |
| `graphql.loader.name` | Tên DataLoader |
| `graphql.outcome` | `SUCCESS` hoặc `ERROR` |

High-cardinality key mặc định gồm `graphql.loader.size`, thể hiện số phần tử được load trong batch.

Ví dụ, nếu loader `authorById` thường xuyên lỗi với `AuthorRepositoryTimeoutException`, dashboard có thể lọc theo loader name và error type để xác định batch loading là nguồn gây lỗi. Nếu nhiều DataFetcher khác nhau cùng phụ thuộc loader đó, lỗi sẽ hiện ra ở tầng loader thay vì chỉ nhìn từng field riêng lẻ.

Đừng gắn ID từng author, book hoặc user vào metric tag. Những giá trị đó có thể rất nhiều và thay đổi liên tục. Dùng loader name và exception class để phân nhóm; dùng trace/log có kiểm soát để tìm một request cụ thể.

## 10. Bật GraphQL observations

Observations chỉ được ghi khi ứng dụng có `ObservationRegistry` và `GraphQlObservationInstrumentation` được gắn vào GraphQL execution.

Với Spring Boot, auto-configuration có thể cung cấp instrumentation khi các điều kiện cần thiết được đáp ứng, chẳng hạn GraphQL và Micrometer Observation có trên classpath cùng một `ObservationRegistry`. Điều kiện và package auto-configuration thay đổi theo dòng phiên bản Boot; hãy kiểm tra bean thực tế nếu ứng dụng tùy chỉnh `GraphQlSource` hoặc không dùng Boot starter.

Với cấu hình cần đăng ký tường minh, instrumentation được tạo bằng `ObservationRegistry`:

~~~java
@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    GraphQlObservationInstrumentation graphQlObservationInstrumentation(
            ObservationRegistry observationRegistry) {
        return new GraphQlObservationInstrumentation(observationRegistry);
    }
}
~~~

Không đăng ký thêm một instrumentation trùng lặp nếu Boot đã tự cấu hình. Trước tiên xác minh ứng dụng chỉ có một nguồn cấu hình phù hợp và observations thực sự được phát.

Để xuất metrics, ứng dụng cần một MeterRegistry phù hợp, ví dụ Prometheus registry, và có thể expose Actuator metrics endpoint theo cấu hình vận hành. Để xuất traces, cấu hình Micrometer Tracing cùng exporter tương ứng. Observation API là lớp instrumentation chung; backend metrics/tracing quyết định dữ liệu được lưu và hiển thị ở đâu.

## 11. Đọc graphql.error.type trong dashboard

Khi điều tra lỗi, nên kết hợp ít nhất ba thuộc tính:

1. `graphql.error.type` để biết exception class nào xuất hiện.
2. `graphql.field.name` để biết field nào thường gặp lỗi.
3. `graphql.outcome` để phân biệt fetch thành công và thất bại.

Với DataLoader, kết hợp `graphql.loader.name` và `graphql.error.type`. Với toàn request, xem `graphql.operation.type` và `graphql.outcome`.

Ví dụ cách đặt câu hỏi khi đọc dashboard:

| Quan sát | Hướng điều tra |
| --- | --- |
| Một error class tăng đột ngột ở nhiều field | Kiểm tra dependency hoặc exception mapping dùng chung |
| Chỉ một field có outcome ERROR | Kiểm tra resolver/service của field đó |
| Nhiều field lỗi cùng một loader name | Kiểm tra batch loader và repository phía sau |
| Request outcome là REQUEST_ERROR nhưng không có INTERNAL_ERROR | Xem lỗi nghiệp vụ, validation hoặc authorization trong GraphQL response |
| Request outcome là INTERNAL_ERROR | Tìm exception chưa xử lý hoặc lỗi nội bộ khiến response không hợp lệ |
| HTTP 200 nhưng GraphQL request outcome là REQUEST_ERROR | Đọc GraphQL errors thay vì chỉ nhìn HTTP status |

Metrics cho biết xu hướng và nhóm lỗi. Trace cho thấy một request cụ thể đi qua transport, GraphQL request, DataFetcher, DataLoader và dependency như thế nào. Log có execution ID/correlation ID giúp nối các dữ liệu đó.

## 12. Cardinality và dữ liệu nhạy cảm

`graphql.error.type` được thiết kế là low-cardinality key. Tuy nhiên, ứng dụng vẫn có thể làm cardinality tăng nếu tạo quá nhiều exception class động hoặc dùng một class riêng cho từng giá trị dữ liệu.

Không dùng các giá trị sau làm metric tag:

- Exception message chứa ID, email, username hoặc query input.
- Stack trace hoặc tên SQL statement có biến thể theo request.
- Resource ID, tenant ID hoặc user ID.
- GraphQL variables hoặc toàn bộ document.
- Raw field path có thể tăng theo alias và cấu trúc query.

Giữ exception class ổn định và có ý nghĩa. Nếu ứng dụng có nhiều exception class nội bộ, có thể chuẩn hóa chúng thành một nhóm hữu hạn trong custom convention, ví dụ `DEPENDENCY_FAILURE`, `AUTHORIZATION_FAILURE` hoặc `VALIDATION_FAILURE`. Việc chuẩn hóa phải giữ đủ thông tin chẩn đoán trong log/trace và không làm mất khả năng phân biệt lỗi quan trọng.

Không đưa exception class nội bộ hoặc chi tiết implementation vào response cho client chỉ vì chúng đang được ghi trong observation. Metric tag và public GraphQL error contract là hai kênh khác nhau.

## 13. Tùy chỉnh DataFetcherObservationConvention

Spring for GraphQL cho phép thay đổi key values bằng `DataFetcherObservationConvention`. Với Spring Boot, cung cấp convention dưới dạng bean là cách tích hợp thuận tiện. Có thể kế thừa `DefaultDataFetcherObservationConvention` rồi override phần tạo error type.

Ví dụ chuẩn hóa một số exception class thành nhóm ổn định:

~~~java
@Configuration
public class GraphQlObservationConventionConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {

            @Override
            protected KeyValue errorType(DataFetcherObservationContext context) {
                Throwable error = context.getError();
                String value = classify(error);
                return KeyValue.of("graphql.error.type", value);
            }

            private String classify(Throwable error) {
                if (error == null) {
                    return "none";
                }
                if (error instanceof AccessDeniedException) {
                    return "AUTHORIZATION_FAILURE";
                }
                if (error instanceof TimeoutException) {
                    return "DEPENDENCY_TIMEOUT";
                }
                if (error instanceof BookNotFoundException) {
                    return "NOT_FOUND";
                }
                return "UNEXPECTED_FAILURE";
            }
        };
    }
}
~~~

Ví dụ trên là một policy tùy chỉnh: mọi exception không nằm trong allowlist được gom vào `UNEXPECTED_FAILURE`. Hãy kiểm tra các class import theo phiên bản Micrometer/Spring GraphQL của ứng dụng. Nếu muốn giữ nguyên class name mặc định, có thể kế thừa convention mặc định mà không override method.

Khi override convention, giữ các key mặc định khác bằng cách chỉ tùy chỉnh đúng key cần thiết. Nếu tự triển khai toàn bộ `DataFetcherObservationConvention`, phải duy trì các key cần thiết cho dashboard hiện tại và hiểu rõ thay đổi sẽ ảnh hưởng đến metrics/traces.

## 14. Kiểm thử error type observation

Không nên chỉ kiểm tra GraphQL response để kết luận `graphql.error.type` được ghi đúng. Response kiểm tra error classification; observation test kiểm tra metadata được phát.

Một kịch bản kiểm thử nên:

1. Cấu hình `ObservationRegistry` dành cho test.
2. Thực thi một GraphQL operation có DataFetcher ném exception xác định.
3. Xác nhận response có GraphQL error classification mong đợi.
4. Xác nhận DataFetcher observation có `graphql.error.type` tương ứng với convention.
5. Xác nhận `graphql.field.name` và `graphql.outcome` phù hợp.
6. Thực thi một request thành công để xác nhận outcome không bị giữ trạng thái lỗi từ request trước.

Có thể dùng Micrometer Observation test support hoặc một ObservationHandler ghi lại context được start/stop. Nếu kiểm tra metrics, dùng registry test như SimpleMeterRegistry và xác nhận timer/tag sau khi operation hoàn tất. Cách lấy observation cụ thể phụ thuộc test support và phiên bản Micrometer đang dùng.

Nên có các trường hợp:

- DataFetcher thành công.
- DataFetcher ném exception và được `@GraphQlExceptionHandler` xử lý.
- Exception không được xử lý và trở thành `INTERNAL_ERROR`.
- Request parse/validation lỗi trước khi DataFetcher chạy.
- DataLoader batch call lỗi.
- Nhiều field dùng chung một dependency và cùng phát sinh một error class.
- Custom convention chuẩn hóa exception theo nhóm.

Khi test error đã được handler xử lý, đừng chỉ assert HTTP status. Kiểm tra cả GraphQL response error, observation outcome và tag theo đúng tầng.

## 15. Lỗi thường gặp

| Cách hiểu hoặc cấu hình sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `graphql.error.type` với `ErrorType.NOT_FOUND` | Đọc sai ý nghĩa tag | Phân biệt exception class trong observation với GraphQL ErrorClassification |
| Chỉ kiểm tra HTTP status | Bỏ sót GraphQL errors trong response HTTP 200 | Xem `graphql.outcome` và errors của GraphQL response |
| Không có ObservationRegistry | Không có GraphQL observations | Cấu hình Micrometer Observation và xác minh registry |
| Nghĩ mọi field đều có datafetcher observation | Đếm thiếu so với số field trong query | Property fetcher trivial có thể không được instrument riêng |
| Tìm request parse error qua graphql.error.type | Không thấy tag tương ứng | Request error xảy ra trước DataFetcher; xem request observation |
| Đưa exception message vào metric tag | Cardinality tăng và có thể lộ dữ liệu | Dùng class/group ổn định, giữ message trong log có kiểm soát |
| Dùng field path làm metric label | Tạo nhiều time series | Giữ path ở high-cardinality trace context |
| Exception handler che hết chi tiết nội bộ | Client không thấy nguyên nhân kỹ thuật | Dùng execution ID để nối response với log/trace nội bộ |
| Tùy chỉnh convention nhưng bỏ key mặc định | Dashboard cũ mất tag | Kế thừa default convention và chỉ override key cần thiết |
| Đăng ký instrumentation trùng | Có thể tạo observation/metrics trùng | Kiểm tra auto-configuration và GraphQlSource customization |

## 16. Nguyên tắc sử dụng graphql.error.type

Hãy xem `graphql.error.type` là nhãn kỹ thuật cho lỗi xảy ra trong data fetching. Dùng nó để nhóm exception class ở DataFetcher và DataLoader; kết hợp với field name, loader name và outcome để tìm vị trí gây lỗi. Dùng request observation để xem kết quả tổng thể của GraphQL operation, vì lỗi parse/validation có thể xảy ra trước khi DataFetcher được gọi.

Giữ low-cardinality tags ổn định, không đưa message, ID, variables hoặc stack trace vào metric labels. Nếu exception class quá phân tán, chuẩn hóa chúng bằng custom observation convention và giữ chi tiết đầy đủ trong log/trace có kiểm soát.

Khi xây dựng GraphQL error response, dùng GraphQL ErrorClassification hoặc Spring GraphQL ErrorType để biểu diễn semantics cho client. Khi theo dõi hệ thống, dùng `graphql.error.type` để hiểu exception class trong quá trình fetch. Kết hợp hai lớp giúp dashboard trả lời được cả câu hỏi kỹ thuật và câu hỏi nghiệp vụ mà không làm lẫn contract API với telemetry.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution và exception handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers và @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring GraphQL ErrorType API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/execution/ErrorType.html)
- [DefaultDataFetcherObservationConvention API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DefaultDataFetcherObservationConvention.html)
