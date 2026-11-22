# Logging request metadata

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của interceptor trong vòng đời một GraphQL request.
- Dùng WebGraphQlInterceptor để ghi log metadata trước và sau khi GraphQL execution hoàn tất.
- Lấy request ID, operation name và các thông tin transport phù hợp.
- Đo thời gian xử lý bằng System.nanoTime().
- Phân biệt GraphQL errors trong response với exception làm pipeline kết thúc bất thường.
- Truyền request ID vào GraphQLContext để resolver có thể ghi log cùng correlation ID.
- Thiết kế structured logging với allowlist và redaction.
- Tránh ghi query document, variables, authorization header và dữ liệu nhạy cảm.
- Hiểu giới hạn của interceptor và mối quan hệ giữa logging, metrics, tracing.
- Kiểm thử log metadata qua HTTP hoặc WebFlux transport.

## 1. Vì sao cần logging metadata cho GraphQL?

Một GraphQL endpoint thường nhận nhiều loại operation trên cùng một URL, ví dụ Query, Mutation và Subscription. Chỉ nhìn access log của HTTP server, ta có thể biết request đến endpoint nào và mất bao lâu, nhưng khó biết operation nào được gửi và GraphQL execution trả về bao nhiêu lỗi.

Logging metadata giúp trả lời các câu hỏi vận hành:

- Operation nào đang được gọi thường xuyên?
- Request nào mất nhiều thời gian?
- Một GraphQL response có trả về field errors hay không?
- Request ID nào cần dùng để đối chiếu với log của resolver hoặc service?
- Một lỗi xuất hiện ở GraphQL execution hay ở pipeline xử lý request?

Ví dụ, hai request đều gọi POST /graphql nhưng một request chạy operation GetBook, còn request kia chạy operation SearchBooks. Ghi operation name cùng request ID và duration giúp phân tích rõ hơn mà không cần ghi toàn bộ nội dung truy vấn.

Metadata phù hợp để log thường gồm:

- Request ID do server hoặc transport cung cấp.
- Operation name.
- Thời gian xử lý.
- Số lượng GraphQL errors.
- Kết quả hoàn tất, lỗi pipeline hoặc bị hủy.
- Một số header đã được allowlist nếu thực sự cần.

Không nên mặc định ghi toàn bộ request body, variables, query document hoặc tất cả HTTP headers. Những phần đó có thể chứa token, thông tin cá nhân, dữ liệu nghiệp vụ và giá trị nhạy cảm.

## 2. WebGraphQlInterceptor nằm ở đâu?

Spring for GraphQL cung cấp WebGraphQlInterceptor để can thiệp vào request/response ở ranh giới web transport và GraphQL.

Interceptor nhận WebGraphQlRequest, sau đó gọi tiếp Chain để xử lý request. Kết quả là một publisher WebGraphQlResponse:

~~~java
public interface WebGraphQlInterceptor {

    Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain);
}
~~~

Có thể hình dung luồng:

~~~mermaid
flowchart TD
    A["HTTP / WebSocket transport"] --> B["WebGraphQlRequest"]
    B --> C["WebGraphQlInterceptor"]
    C --> D["chain.next(request)"]
    D --> E["GraphQL execution"]
    E --> F["WebGraphQlResponse"]
    F --> G["Interceptor observes response"]
    G --> H["Transport writes response"]
~~~

Interceptor phù hợp để ghi nhận metadata chung cho một GraphQL request. Nó có thể quan sát request trước khi chuyển tiếp và response sau khi execution hoàn tất.

Interceptor không thay thế HTTP access log. Một request lỗi ở tầng HTTP parsing, authentication filter hoặc routing trước khi được chuyển thành WebGraphQlRequest có thể chưa đi tới interceptor. Vì vậy, access log ở web server và GraphQL interceptor bổ sung thông tin cho nhau.

## 3. Đọc metadata từ WebGraphQlRequest

WebGraphQlRequest cung cấp thông tin về GraphQL request và transport. Các giá trị thường hữu ích gồm:

- getId(): định danh request.
- getOperationName(): tên operation do client gửi, có thể không có.
- getUri(): URI của request.
- getHeaders(): HTTP headers.
- getDocument() và getVariables(): nội dung operation và variables.

Đối với logging thông thường, chỉ cần một tập metadata nhỏ:

~~~java
String requestId = request.getId();

String operationName = request.getOperationName();
String operation = operationName != null
        ? operationName
        : "anonymous";
~~~

Operation name có thể không được client đặt tên. Khi đó có thể log một giá trị thay thế như anonymous.

Operation name cũng là metadata do client gửi. Trong môi trường production, nên giới hạn độ dài và loại bỏ ký tự điều khiển như carriage return hoặc newline trước khi ghi log để tránh log injection. Parameterized logging giúp tránh việc chuỗi này bị hiểu là format string, nhưng không tự loại bỏ ký tự điều khiển.

Không nên ghi trực tiếp getDocument() hoặc getVariables() vào log production. Query document có thể chứa inline literal; variables thường chứa email, số điện thoại, dữ liệu cá nhân hoặc thông tin nghiệp vụ. Nếu cần phân tích operation, hãy ưu tiên operation name, persisted query ID hoặc một fingerprint đã được tạo và kiểm soát riêng.

## 4. Viết interceptor ghi log request và response

Ví dụ dưới đây ghi request ID, operation name, thời gian xử lý và số lượng GraphQL errors:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class GraphQlRequestLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlRequestLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();
        String requestId = request.getId();

        String operationName = request.getOperationName();
        String operation = operationName != null
                ? operationName
                : "anonymous";

        log.info(
                "GraphQL request started requestId={} operation={}",
                requestId,
                operation
        );

        return chain.next(request)
                .doOnNext(response -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt
                    );

                    int errorCount = response.getErrors().size();

                    if (errorCount == 0) {
                        log.info(
                                "GraphQL request completed requestId={} operation={} durationMs={} errorCount={}",
                                requestId,
                                operation,
                                durationMs,
                                errorCount
                        );
                    }
                    else {
                        log.warn(
                                "GraphQL request completed with errors requestId={} operation={} durationMs={} errorCount={}",
                                requestId,
                                operation,
                                durationMs,
                                errorCount
                        );
                    }
                })
                .doOnError(exception -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt
                    );

                    log.warn(
                            "GraphQL request pipeline failed requestId={} operation={} durationMs={} exceptionType={}",
                            requestId,
                            operation,
                            durationMs,
                            exception.getClass().getSimpleName()
                    );
                })
                .doOnCancel(() ->
                        log.info(
                                "GraphQL request cancelled requestId={} operation={}",
                                requestId,
                                operation
                        )
                );
    }
}
~~~

Các điểm cần chú ý:

- Thời gian bắt đầu được ghi bằng System.nanoTime(), phù hợp để đo elapsed time.
- chain.next(request) tiếp tục chuỗi interceptor và GraphQL execution.
- doOnNext quan sát response khi publisher phát ra kết quả.
- response.getErrors().size() đếm lỗi GraphQL có trong response.
- doOnError quan sát exception làm publisher kết thúc bằng lỗi.
- doOnCancel ghi nhận trường hợp subscriber hủy việc chờ response.

Ví dụ không ghi message của exception vì message có thể chứa dữ liệu đầu vào hoặc chi tiết nội bộ. Nếu cần stack trace để điều tra, hãy áp dụng chính sách log và redaction phù hợp, đồng thời kiểm soát quyền truy cập log.

## 5. GraphQL errors khác pipeline exception

Đây là điểm quan trọng khi ghi log GraphQL.

Một GraphQL operation có thể được xử lý thành công ở cấp pipeline nhưng response vẫn chứa errors. Ví dụ:

- Resolver ném exception và exception được ánh xạ thành GraphQL error.
- Một field bị từ chối quyền truy cập.
- Một field nullable không thể tải dữ liệu.
- Một phần của selection set lỗi nhưng field khác vẫn trả dữ liệu.

Trong những trường hợp này, GraphQL thường trả WebGraphQlResponse có danh sách errors. Publisher vẫn có thể hoàn tất bình thường, vì vậy doOnNext chạy và doOnError không chạy.

Ngược lại, doOnError phản ánh exception làm chuỗi xử lý kết thúc bất thường, chẳng hạn lỗi hạ tầng hoặc lỗi trong pipeline trước khi tạo được response bình thường.

| Trường hợp | Tín hiệu trong interceptor | Cách log |
| --- | --- | --- |
| Response không có GraphQL error | doOnNext, errorCount = 0 | INFO |
| Response có một hoặc nhiều GraphQL errors | doOnNext, errorCount > 0 | WARN hoặc mức phù hợp với chính sách |
| Pipeline phát exception | doOnError | ERROR/WARN theo loại lỗi |
| Request bị hủy | doOnCancel | INFO hoặc DEBUG |

Không được coi mọi response có errors là HTTP transport failure. GraphQL có thể trả partial data cùng errors. Logging nên thể hiện rõ response có lỗi GraphQL nhưng operation vẫn được thực thi và tạo response.

Cũng không nên ghi toàn bộ error message một cách tự động. Error message có thể chứa ID, input hoặc thông tin nội bộ. Có thể log error count, error classification hoặc mã lỗi đã được chuẩn hóa và cho phép ghi.

## 6. Đo duration đúng cách

Dùng System.nanoTime() để đo thời gian trôi qua:

~~~java
long startedAt = System.nanoTime();

// Thực thi công việc cần đo

long elapsedNanos = System.nanoTime() - startedAt;
long durationMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Không nên dùng System.currentTimeMillis() để tính elapsed time vì đồng hồ hệ thống có thể được điều chỉnh. currentTimeMillis phù hợp với timestamp lịch; nanoTime phù hợp để đo duration.

Trong interceptor, thời gian đo quanh chain.next(request) phản ánh thời gian từ lúc interceptor bắt đầu cho đến khi response được phát ra. Đây là thời gian tổng của phần pipeline nằm bên trong interceptor, không phải thời gian riêng của một resolver hoặc một câu SQL.

Nếu cần phân tích chi tiết hơn, hãy đo thêm ở service, repository hoặc GraphQL instrumentation/Observation. Không suy ra resolver nào chậm chỉ từ tổng duration của request.

## 7. Truyền request ID vào GraphQLContext

Một request ID hữu ích hơn khi resolver và service có thể dùng cùng định danh đó trong log.

WebGraphQlRequest cho phép tùy chỉnh ExecutionInput trước khi thực thi. Có thể đưa request ID vào GraphQLContext:

~~~java
String requestId = request.getId();

request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context ->
                context.put("requestId", requestId)
        ).build()
);
~~~

Sau đó resolver có thể nhận giá trị bằng @ContextValue:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;

@QueryMapping
public Book book(
        @Argument("id") UUID id,
        @ContextValue("requestId") String requestId) {

    log.debug(
            "Resolving book requestId={} bookId={}",
            requestId,
            id
    );

    return bookService.findById(id);
}
~~~

Như vậy, log ở interceptor và log tại resolver có thể được đối chiếu bằng cùng request ID.

Chỉ truyền những metadata cần thiết. Không đưa toàn bộ WebGraphQlRequest, headers hoặc variables vào GraphQLContext. GraphQLContext có phạm vi execution; dữ liệu được đặt ở đây có thể được nhiều resolver trong cùng operation truy cập.

## 8. Correlation ID từ client và request ID nội bộ

Một số hệ thống gửi header correlation ID hoặc trace ID để liên kết request qua gateway và nhiều service.

Ví dụ header:

~~~http
X-Correlation-ID: 7f4b5c21-1f5a-4f2a-9f20-4d0e1c6f5a31
~~~

Có thể đọc header được allowlist:

~~~java
String externalCorrelationId =
        request.getHeaders().getFirst("X-Correlation-ID");
~~~

Tuy nhiên, giá trị client gửi lên không mặc nhiên đáng tin cậy. Nếu sử dụng nó trong log:

- Kiểm tra định dạng.
- Giới hạn chiều dài.
- Loại bỏ ký tự điều khiển và newline.
- Không dùng nó làm cơ chế xác thực.
- Có fallback về request ID do server cung cấp.
- Không cho phép giá trị tùy ý làm giả log entry hoặc gây log injection.

Một cách làm an toàn là dùng request ID nội bộ làm định danh chính, còn correlation ID bên ngoài được lưu như một trường metadata riêng sau khi validate.

Nếu hệ thống đã dùng distributed tracing, ưu tiên trace ID do tracing infrastructure quản lý. Tránh tự tạo nhiều loại ID trùng ý nghĩa mà không có quy ước rõ ràng.

## 9. Chọn metadata được phép ghi log

Logging nên dùng allowlist thay vì lấy tất cả headers rồi cố gắng loại bỏ những header nhạy cảm.

Ví dụ các trường có thể hữu ích nếu chính sách hệ thống cho phép:

| Metadata | Lưu ý |
| --- | --- |
| Request ID | Ưu tiên định danh nội bộ, duy nhất |
| Operation name | Có thể là anonymous nếu client không đặt tên |
| Duration | Ghi đơn vị rõ ràng, ví dụ milliseconds |
| GraphQL error count | Không cần ghi toàn bộ message |
| HTTP method | Có thể dùng nếu phân tích theo transport |
| Content-Type | Chỉ ghi khi cần chẩn đoán transport |
| User-Agent | Có thể chứa chuỗi dài hoặc dữ liệu không đáng tin cậy |
| Correlation ID | Validate và giới hạn độ dài trước khi log |

Tránh ghi các giá trị sau vào log thông thường:

- Authorization và Proxy-Authorization.
- Cookie và Set-Cookie.
- Access token, refresh token hoặc API key.
- Toàn bộ GraphQL variables.
- Query document có inline literal.
- Password, OTP, thông tin thanh toán và dữ liệu cá nhân.
- Toàn bộ response data.

Nếu cần debug một request cụ thể, hãy dùng cơ chế bật log có thời hạn, có kiểm soát truy cập và redaction theo chính sách bảo mật. Không bật logging payload nhạy cảm đại trà ở production.

## 10. Structured logging

Structured logging giúp hệ thống log có thể lọc và tổng hợp theo trường thay vì phân tích chuỗi message tự do.

Ví dụ một log event có cấu trúc:

~~~json
{
    "event": "graphql.request.completed",
    "requestId": "req-7f2a",
    "operation": "GetBook",
    "durationMs": 34,
    "errorCount": 0
}
~~~

Các field nên có tên ổn định giữa các service:

- event: loại sự kiện.
- requestId: định danh request.
- operation: tên GraphQL operation.
- durationMs: thời gian thực thi.
- errorCount: số GraphQL errors.
- outcome: completed, completed_with_errors, pipeline_failed hoặc cancelled.

Không nhồi toàn bộ metadata vào một chuỗi duy nhất. Khi dùng JSON encoder hoặc structured logging framework, hãy truyền các field riêng để hệ thống log có thể index và truy vấn.

Tránh đưa ID có cardinality quá cao vào metric label. Request ID phù hợp với log và trace, nhưng thường không phù hợp làm tag cho metric vì có thể tạo số lượng time series rất lớn.

## 11. Ghi log lỗi nhưng không làm lộ dữ liệu

Một GraphQL error có thể chứa message dành cho client. Message đó không nhất thiết phù hợp để đưa nguyên văn vào log.

Ví dụ, không nên mặc định ghi:

~~~java
response.getErrors().forEach(error ->
        log.warn("GraphQL error: {}", error.getMessage())
);
~~~

Thay vào đó, có thể log số lượng lỗi và loại lỗi đã được chuẩn hóa:

~~~java
int errorCount = response.getErrors().size();

log.warn(
        "GraphQL response contains errors requestId={} operation={} errorCount={}",
        requestId,
        operation,
        errorCount
);
~~~

Nếu cần thêm thông tin, hãy tạo error code ổn định trong extensions theo quy ước ứng dụng và chỉ ghi những mã được phép. Tránh ghi stack trace cho lỗi validation thông thường; stack trace nên dành cho lỗi hệ thống cần điều tra.

Đừng dùng log message của client làm format string. Luôn dùng placeholder của logging framework và truyền giá trị làm tham số.

## 12. Logging trong reactive pipeline và MDC

WebGraphQlInterceptor trả về Mono, do đó callback có thể chạy trên thread khác với thread ban đầu khi pipeline chuyển scheduler.

MDC của SLF4J thường dựa trên ThreadLocal. Nếu tự đặt MDC ở đầu interceptor rồi xóa trong một finally block đồng bộ, giá trị có thể không còn đúng khi callback chạy ở thread khác. Ngược lại, MDC có thể bị sót trên thread được tái sử dụng nếu không được dọn đúng cách.

Có hai hướng:

- Truyền request ID trực tiếp như structured logging field trong từng log statement.
- Nếu cần MDC hoặc tracing context tự động, cấu hình context propagation tương thích với Reactor và observability stack của ứng dụng.

Ví dụ truyền trực tiếp:

~~~java
log.info(
        "GraphQL resolver completed requestId={} field={}",
        requestId,
        "Book.author"
);
~~~

Đừng dựa vào ThreadLocal tự phát để mang principal, tenant hoặc request ID qua reactive boundary. Dùng GraphQLContext, Reactor Context hoặc cơ chế context propagation được cấu hình rõ ràng.

## 13. Đăng ký interceptor

Có thể đăng ký WebGraphQlInterceptor thông qua WebGraphQlConfigurer:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlConfigurer;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
class GraphQlWebConfiguration implements WebGraphQlConfigurer {

    private final GraphQlRequestLoggingInterceptor loggingInterceptor;

    GraphQlWebConfiguration(
            GraphQlRequestLoggingInterceptor loggingInterceptor) {
        this.loggingInterceptor = loggingInterceptor;
    }

    @Override
    public void configureInterceptors(
            List<WebGraphQlInterceptor> interceptors) {

        interceptors.add(loggingInterceptor);
    }
}
~~~

Cách đăng ký này giúp interceptor tham gia chuỗi xử lý web GraphQL. Trong ứng dụng Spring Boot, có thể tổ chức interceptor như Spring bean và kết nối qua cấu hình web GraphQL của ứng dụng.

Khi có nhiều interceptor, cần hiểu mỗi interceptor có thể sửa request, thêm context hoặc quan sát response. Logging interceptor nên giữ nhiệm vụ quan sát và ghi log; tránh thay đổi variables hoặc response data ngoài mục tiêu của nó.

## 14. Logging interceptor không thay thế metrics và tracing

Logging, metrics và tracing phục vụ các câu hỏi khác nhau.

| Công cụ | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Logging | Điều gì đã xảy ra với request cụ thể? | Request ID, operation name, error count |
| Metrics | Xu hướng tải và hiệu năng ra sao? | Request rate, latency histogram, error rate |
| Tracing | Request đi qua những service/span nào? | Trace ID, span GraphQL, database span |

Không nên tạo metric riêng cho từng request ID hoặc operation name tùy ý do cardinality có thể tăng cao. Với metrics, ưu tiên tập nhãn giới hạn như operation category, transport và outcome.

Nếu Spring Boot Actuator và Micrometer đã được cấu hình, hãy tận dụng observation và tracing hiện có. Logging interceptor có thể bổ sung metadata nghiệp vụ hoặc request-specific fields, nhưng không nên tạo một hệ thống timing song song không thống nhất với metrics.

## 15. Kiểm thử logging metadata

Để xác minh interceptor thật sự được gọi, test cần đi qua web GraphQL transport. Một test chỉ gọi trực tiếp ExecutionGraphQlService có thể bỏ qua WebGraphQlInterceptor.

Có thể dùng HttpGraphQlTester hoặc WebGraphQlTester tùy transport của ứng dụng, kết hợp với test appender để thu log.

Ví dụ operation dùng trong test:

~~~graphql
query GetBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Các điều cần xác minh:

1. Request được gửi qua HTTP hoặc WebFlux transport.
2. Log bắt đầu có request ID và operation name.
3. Log hoàn tất có duration và error count.
4. Response có GraphQL errors vẫn được ghi nhận qua nhánh response.
5. Pipeline exception được ghi nhận qua nhánh error.
6. Request cancellation được xử lý nếu test harness hỗ trợ.
7. Variables, Authorization và Cookie không xuất hiện trong log.
8. Request ID trong resolver log khớp request ID tại interceptor nếu đã truyền vào GraphQLContext.

Nên có test cho operation không đặt tên để xác minh fallback anonymous. Cũng nên kiểm tra header correlation ID có giá trị dài hoặc chứa ký tự không hợp lệ sẽ bị bỏ qua hoặc chuẩn hóa theo chính sách ứng dụng.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có log từ interceptor | Request chưa đi tới WebGraphQlInterceptor hoặc interceptor chưa được đăng ký | Kiểm tra transport và WebGraphQlConfigurer |
| Chỉ log được request nhưng không có duration | Chưa quan sát publisher response | Dùng doOnNext và đo elapsed time |
| GraphQL response có errors nhưng không vào doOnError | GraphQL errors nằm trong response bình thường | Kiểm tra response.getErrors() |
| Mọi lỗi đều bị ghi là transport failure | Gộp GraphQL errors và pipeline exception | Tách doOnNext với doOnError |
| Request ID thay đổi giữa interceptor và resolver | Chưa truyền ID vào GraphQLContext hoặc dùng ID khác | Dùng cùng một key và nguồn request ID |
| MDC bị mất khi chuyển thread | MDC dựa trên ThreadLocal trong reactive pipeline | Truyền field trực tiếp hoặc cấu hình context propagation |
| Log chứa token hoặc dữ liệu cá nhân | Ghi toàn bộ headers, document hoặc variables | Dùng allowlist, redaction và kiểm thử log |
| Log bị giả mạo qua header | Tin tưởng correlation ID client gửi lên mà không validate | Kiểm tra format, length và ký tự điều khiển |
| Log quá nhiều làm tăng chi phí | Ghi mọi field và payload ở INFO | Chọn event cần thiết, dùng DEBUG có kiểm soát |
| Metrics tăng cardinality | Dùng request ID làm metric tag | Đưa request ID vào log/trace, giữ metric labels có giới hạn |

## 17. Quy trình triển khai logging metadata

Khi thêm logging cho GraphQL endpoint, hãy thực hiện theo trình tự:

1. **Xác định điểm quan sát.** Dùng WebGraphQlInterceptor cho metadata ở ranh giới web GraphQL.
2. **Chọn trường được phép log.** Bắt đầu với request ID, operation name, duration và error count.
3. **Ghi log đầu request.** Lấy metadata trước khi gọi chain.next(request).
4. **Đo thời gian.** Dùng System.nanoTime() để tính elapsed duration.
5. **Quan sát response.** Ghi error count từ WebGraphQlResponse.getErrors().
6. **Tách lỗi pipeline.** Dùng doOnError cho exception làm publisher kết thúc bất thường.
7. **Truyền correlation.** Đưa request ID vào GraphQLContext nếu resolver cần log cùng ID.
8. **Bảo vệ dữ liệu.** Không log variables, document, Authorization hoặc Cookie.
9. **Kiểm tra reactive context.** Không dựa vào MDC/ThreadLocal nếu chưa cấu hình propagation.
10. **Kiểm thử qua transport.** Dùng HttpGraphQlTester hoặc WebGraphQlTester và xác minh cả nội dung log.

## 18. Tổng kết

WebGraphQlInterceptor là điểm phù hợp để ghi log metadata của một GraphQL request trước và sau khi request đi qua GraphQL execution. Các trường hữu ích thường gồm request ID, operation name, duration, error count và outcome. Dùng System.nanoTime() để đo thời gian, quan sát response bằng doOnNext và tách exception của pipeline bằng doOnError.

GraphQL errors thường nằm trong WebGraphQlResponse và không nhất thiết làm publisher phát lỗi. Vì vậy, cần phân biệt response có errors với pipeline exception. Có thể truyền request ID vào GraphQLContext để resolver ghi log nhất quán bằng @ContextValue. Hãy dùng structured logging, allowlist và redaction; không ghi query document, variables, authorization header hoặc cookie vào log thông thường. Kết hợp interceptor với access log, metrics và tracing sẽ giúp quan sát hệ thống mà vẫn giữ dữ liệu request an toàn.

