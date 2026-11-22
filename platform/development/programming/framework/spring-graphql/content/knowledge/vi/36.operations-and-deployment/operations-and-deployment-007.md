# Log request an toàn trong Spring for GraphQL

Log request giúp đội vận hành tìm nguyên nhân lỗi, theo dõi hiệu năng và phát hiện hành vi bất thường. Tuy nhiên, một GraphQL request có thể chứa document, variables, extensions và metadata từ transport. Những phần này thường mang dữ liệu do client kiểm soát, có thể bao gồm mật khẩu, access token, thông tin cá nhân, dữ liệu thanh toán hoặc nội dung nghiệp vụ.

Vì vậy, logging cho GraphQL cần được thiết kế theo nguyên tắc **chỉ ghi dữ liệu đã được cho phép**. Hãy ghi metadata đủ để truy vết một operation, đo thời gian và phân loại kết quả; tránh ghi toàn bộ request hoặc response. Việc lọc dữ liệu cần áp dụng ở ứng dụng, web server, reverse proxy, tracing backend và hệ thống tập trung log.

## 1. Mục tiêu của request logging

Một request log hữu ích cần trả lời được các câu hỏi vận hành:

- Request đến service nào, vào thời điểm nào?
- Request thuộc operation nào và kết quả thành công hay lỗi?
- Thời gian xử lý là bao lâu?
- Có thể liên kết log với trace, request khác hoặc lỗi cụ thể không?
- Có dấu hiệu vi phạm giới hạn, xác thực thất bại hoặc hành vi bất thường không?

Một log tốt không cần chứa toàn bộ dữ liệu client gửi. Ví dụ, để điều tra một lần PlaceOrder thất bại, thường chỉ cần operation label, request ID, outcome, duration, error category và một mã đơn hàng đã được phân loại cho phép. Không cần lưu địa chỉ giao hàng, số thẻ, mật khẩu hoặc access token.

Nên phân biệt ba mục tiêu:

| Loại log | Mục tiêu | Nội dung điển hình |
| --- | --- | --- |
| Operational log | Điều tra lỗi và hiệu năng | Request ID, operation, outcome, duration, error count. |
| Security audit log | Ghi nhận sự kiện bảo mật và nghiệp vụ quan trọng | Authentication failure, authorization denial, rate-limit event, hành động quản trị. |
| Trace/metric | Theo dõi phân tán và thống kê | Trace ID, span, operation type, field timing, low-cardinality outcome. |

Không nên biến mọi request log thành audit log. Audit event cần schema, quyền truy cập, retention và khả năng truy vết riêng theo yêu cầu tổ chức.

## 2. GraphQL request chứa những dữ liệu nào?

Một GraphQL request có các thành phần chính:

~~~json
{
  "query": "mutation PlaceOrder($input: PlaceOrderInput!) { placeOrder(input: $input) { id status } }",
  "operationName": "PlaceOrder",
  "variables": {
    "input": {
      "customerId": "customer-42",
      "deliveryAddress": "12 Example Street",
      "paymentToken": "secret-payment-token"
    }
  },
  "extensions": {
    "clientTrace": "client-specific-metadata"
  }
}
~~~

Các thành phần này không có cùng mức độ an toàn:

| Thành phần | API Spring GraphQL | Rủi ro khi ghi log |
| --- | --- | --- |
| GraphQL document | getDocument() | Có thể chứa literal nhạy cảm, tên field nội bộ hoặc nội dung query do client gửi. |
| Operation name | getOperationName() | Client kiểm soát được; có thể chứa ký tự điều khiển hoặc tạo cardinality rất cao. |
| Variables | getVariables() | Có thể chứa password, token, PII, dữ liệu thanh toán và input nghiệp vụ. |
| Extensions | getExtensions() | Metadata tùy giao thức; không nên giả định luôn vô hại. |
| HTTP headers | getHeaders() | Có thể chứa Authorization, Cookie, API key và thông tin nhận dạng. |
| Cookies | getCookies() | Có thể chứa session ID hoặc refresh token. |
| Request attributes/context | getAttributes() hoặc GraphQLContext | Có thể chứa principal, tenant, claims hoặc dữ liệu nội bộ. |
| Response data | getData() | Có thể chứa dữ liệu cá nhân hoặc dữ liệu nghiệp vụ được bảo vệ. |
| GraphQL errors | getErrors() | Error message có thể chứa input không hợp lệ, giá trị literal hoặc chi tiết nội bộ. |

Với Spring GraphQL, GraphQlRequest cung cấp document, operation name, variables và extensions. WebGraphQlRequest còn cung cấp URI, headers, cookies và attributes của HTTP request hoặc WebSocket handshake.

Không dùng request.toMap(), response.toMap() hoặc log trực tiếp object request/response. Các cách đó có thể tuần tự hóa nhiều trường hơn mức cần thiết, và toString() không phải là hợp đồng an toàn để ghi log.

## 3. Dữ liệu không nên ghi trực tiếp

Mặc định loại khỏi log:

- Authorization, Proxy-Authorization, Cookie, Set-Cookie.
- Password, OTP, API key, client secret, access token, refresh token, session ID.
- Private key, encryption key, database URL có credentials và connection string.
- Số thẻ, CVV, tài khoản ngân hàng và dữ liệu thanh toán.
- Dữ liệu sức khỏe, giấy tờ định danh và thông tin cá nhân nhạy cảm.
- Email, số điện thoại, địa chỉ, ngày sinh và tên đầy đủ nếu không có mục đích hợp lệ.
- GraphQL variables, raw request body, raw response data và extensions chưa được phân loại.
- GraphQL document có inline literal hoặc nội dung do người dùng cung cấp.
- Exception message hoặc GraphQL error message chưa được kiểm tra.

Không nên cho rằng biến GraphQL có tên id, filter hoặc search là an toàn. Giá trị của chúng vẫn có thể là email, số điện thoại, số tài khoản hoặc dữ liệu bí mật. Một biến input có thể chứa nhiều trường nhạy cảm lồng nhau.

Nếu cần liên kết hành động với một người dùng, hãy dùng định danh nội bộ đã được phê duyệt hoặc giá trị pseudonymized. Hash thông thường của email hay số điện thoại có thể bị dò bằng dictionary; nếu cần pseudonymization ổn định, cân nhắc HMAC với khóa quản lý riêng. Giá trị pseudonymized vẫn có thể là dữ liệu cá nhân và cần được bảo vệ.

## 4. Dùng allowlist thay vì cố che mọi trường nhạy cảm

Cách an toàn hơn là định nghĩa một schema log nhỏ và chỉ thêm trường đã được duyệt. Ví dụ:

| Field | Mục đích | Quy tắc |
| --- | --- | --- |
| event | Tên sự kiện | Giá trị cố định, ví dụ graphql.request.completed. |
| service | Tên service | Lấy từ cấu hình service, không lấy từ request. |
| environment | Môi trường | Giá trị cấu hình như prod, staging. |
| request_id | Liên kết log | ID giới hạn độ dài và đã sanitize. |
| trace_id | Liên kết distributed trace | Lấy từ tracing context đã được cấu hình. |
| operation | Nhãn operation | Chỉ dùng allowlist hoặc nhãn other. |
| outcome | Kết quả | Enum cố định như SUCCESS, REQUEST_ERROR, INTERNAL_ERROR. |
| duration_ms | Thời gian xử lý | Số nguyên không âm. |
| error_count | Số GraphQL errors | Số nguyên; không ghi message. |
| error_category | Phân loại lỗi | Enum/allowlist, không dùng exception message. |

Không đưa request ID, user ID, tenant ID, field path hoặc operation name tùy ý vào metric label. Các giá trị không giới hạn làm tăng cardinality và chi phí lưu trữ. Nếu cần giữ để điều tra, ghi chúng ở trace/log theo chính sách riêng và kiểm soát quyền truy cập.

## 5. Ghi log bằng WebGraphQlInterceptor

HTTP và WebSocket transport của Spring GraphQL gọi chuỗi WebGraphQlInterceptor trước khi request đến GraphQL Java. Đây là vị trí phù hợp để ghi metadata của request và response mà không phải tự đọc hoặc serialize body.

Ví dụ sau chỉ ghi request ID, operation label từ allowlist, tính hợp lệ, số lượng lỗi và thời gian xử lý:

~~~java
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SafeGraphQlRequestLoggingInterceptor
        implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGraphQlRequestLoggingInterceptor.class);

    private static final Set<String> KNOWN_OPERATIONS = Set.of(
            "GetBook",
            "SearchBooks",
            "PlaceOrder");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        long startedAt = System.nanoTime();

        String requestId = safeRequestId(request.getId());
        String operation = operationLabel(request.getOperationName());

        log.info(
                "graphql.request.started requestId={} operation={}",
                requestId,
                operation);

        return chain.next(request)
                .doOnNext(response -> {
                    long durationMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                            "graphql.request.completed requestId={} operation={} valid={} errorCount={} durationMs={}",
                            requestId,
                            operation,
                            response.isValid(),
                            response.getErrors().size(),
                            durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                            "graphql.request.failed requestId={} operation={} durationMs={} exceptionType={}",
                            requestId,
                            operation,
                            durationMs,
                            error.getClass().getSimpleName());
                });
    }

    private static String operationLabel(String operationName) {
        if (operationName == null || operationName.isEmpty()) {
            return "anonymous";
        }

        if (operationName.length() > 64) {
            return "other";
        }

        if (operationName.isBlank()) {
            return "anonymous";
        }

        return KNOWN_OPERATIONS.contains(operationName)
                ? operationName
                : "other";
    }

    private static String safeRequestId(String value) {
        if (value == null || value.isEmpty()) {
            return "unavailable";
        }

        String bounded = value.substring(0, Math.min(value.length(), 128));
        if (bounded.isBlank()) {
            return "unavailable";
        }

        String sanitized = bounded.replaceAll("[^A-Za-z0-9._-]", "_");
        return sanitized.substring(0, Math.min(sanitized.length(), 64));
    }
}
~~~

Trong Spring Boot, khai báo interceptor thành bean (ví dụ dùng @Component như trên) để Boot đưa nó vào chuỗi WebGraphQlInterceptor của WebGraphQlHandler. Nếu tự tạo WebGraphQlHandler, đăng ký interceptor bằng builder.interceptors(...).

Các điểm cần hiểu:

- Interceptor không đọc getDocument(), getVariables(), getExtensions(), headers hoặc cookies.
- operationLabel chỉ cho phép tên operation đã biết; tên do client gửi không được ghi tự do.
- safeRequestId loại ký tự điều khiển và giới hạn độ dài để giảm nguy cơ log injection.
- response.isValid() cho biết response có data hợp lệ theo contract GraphQL. Response vẫn có thể hợp lệ và chứa field errors; vì vậy log thêm errorCount.
- doOnError chỉ ghi exception type, không ghi error.getMessage() hoặc toàn bộ exception vào log request.
- System.nanoTime() dùng để đo duration, không dùng để ghi timestamp thực tế.

request.getId() là ID do transport cung cấp để liên kết request. Với WebFlux, ID mặc định có thể tương quan với log của server; với Spring MVC, ID được tạo riêng; với WebSocket, ID tương ứng message subscribe. Hãy xem nó là correlation value, không phải danh tính người dùng hoặc credential. Nếu cần bảo đảm ID do server cấp, tạo một correlation ID mới tại trusted edge và truyền qua context theo cách được kiểm soát.

Danh sách KNOWN_OPERATIONS trong ví dụ là minh họa. Trong ứng dụng có nhiều operation, có thể quản lý allowlist bằng cấu hình hoặc persisted-operation registry. Nếu không thể allowlist, chỉ ghi nhãn named/anonymous hoặc other, không ghi nguyên operation name do client tùy ý gửi.

## 6. Phân biệt request error và field error khi logging

GraphQL có thể trả partial data cùng errors. Một response có field error không nhất thiết là request thất bại hoàn toàn.

Ví dụ response có partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

isValid() có thể vẫn là true vì response có data khác null. Do đó, log cần ghi cả outcome/validity và số lượng lỗi. Không suy luận rằng valid=true đồng nghĩa không có lỗi.

Ở mức vận hành, có thể phân loại:

| Tình huống | Log outcome gợi ý |
| --- | --- |
| Response có data và không có errors | SUCCESS |
| Request parse/validation error | REQUEST_ERROR |
| Response có partial data và field errors | PARTIAL_ERROR |
| Exception nội bộ không được xử lý | INTERNAL_ERROR |
| Lỗi transport trước/sau GraphQL execution | TRANSPORT_ERROR |

Đây là schema log của ứng dụng; không phải enum chuẩn bắt buộc của GraphQL. Hãy ánh xạ từ response/error category một cách rõ ràng và nhất quán.

Không ghi GraphQLError.getMessage() theo mặc định. Parser error có thể chứa token do client gửi; custom resolver có thể vô tình đưa giá trị input hoặc chi tiết database vào message. Ghi errorCount, error category đã allowlist và request ID là đủ cho phần lớn log vận hành. Khi cần điều tra sâu, dùng trace hoặc log nội bộ có kiểm soát, không đưa dữ liệu nhạy cảm ra log chung.

## 7. Spring GraphQL đã log exception như thế nào?

Spring for GraphQL đăng ký DataFetcherExceptionHandler để xử lý lỗi DataFetcher và hỗ trợ nhiều DataFetcherExceptionResolver.

Theo hành vi mặc định được mô tả trong tài liệu Spring GraphQL:

- Exception không được resolver xử lý sẽ được phân loại INTERNAL_ERROR và trả về thông báo tổng quát có execution ID.
- Exception không được xử lý được log ở mức ERROR cùng execution ID để liên kết với response.
- Exception đã được resolver xử lý được log ở mức DEBUG.

Điều này giúp tránh lộ chi tiết triển khai qua response gửi cho client. Tuy nhiên, ứng dụng vẫn cần rà soát exception message, custom resolver và log level của môi trường production. Không nên thêm một interceptor log lại nguyên exception hoặc message nếu Spring đã ghi nhận sự kiện tương ứng.

Resolver nên trả thông tin an toàn cho client. Không gắn password, token, SQL, connection string hoặc raw input vào GraphQL error message. Nếu cần ghi chi tiết exception để điều tra, hãy dùng logger nội bộ có quyền truy cập giới hạn, redact dữ liệu trước khi ghi và giữ execution ID để liên kết. Không trả stack trace hoặc message nội bộ cho client.

## 8. Cẩn thận với GraphQL Observation và tracing

Spring for GraphQL hỗ trợ Micrometer Observation cho request và các hoạt động DataFetcher/DataLoader. GraphQlObservationInstrumentation tạo các observation như:

- graphql.request: toàn bộ GraphQL request.
- graphql.datafetcher: thao tác DataFetcher không tầm thường.
- graphql.dataloader: hoạt động DataLoader và @BatchMapping.

Các key mặc định được chia theo cardinality:

| Nhóm | Ví dụ | Dùng ở đâu |
| --- | --- | --- |
| Low cardinality | graphql.operation.type, graphql.outcome, graphql.field.name | Metrics và traces. |
| High cardinality | graphql.execution.id, graphql.operation.name, graphql.field.path | Trace, không nên dùng làm metric tag. |

Observation event của GraphQL request có thể chứa đầy đủ error message. Error message có thể chứa token parser, literal hoặc input không hợp lệ do client gửi. Vì vậy, khi xuất traces sang hệ thống tập trung, cần kiểm tra convention, event attributes và exporter có đang lưu message nhạy cảm hay không.

Nguyên tắc khi cấu hình Observation:

- Chỉ đưa operation type và outcome có tập giá trị hữu hạn vào metrics.
- Không đưa request ID, user ID, tenant ID, raw operation name hoặc query text vào metric tags.
- Chỉ đưa high-cardinality values vào trace khi có mục đích và chính sách retention phù hợp.
- Không mặc định error message là dữ liệu an toàn.
- Dùng custom ObservationConvention để kiểm soát KeyValues do ứng dụng thêm.
- Kiểm tra cả span event, baggage, MDC và exporter; redaction ở logger không tự động redaction trace.

Trace ID giúp nối log và trace nhưng không phải bí mật xác thực. Chỉ lấy trace ID từ tracing context được cấu hình, không lấy trực tiếp từ header tùy ý mà không kiểm tra.

## 9. HTTP GET có thể làm lộ query và variables

Spring GraphQL mặc định chỉ nhận HTTP POST. GET có thể được bật rõ ràng nếu ứng dụng cần cache hoặc EventSource, nhưng GraphQL request sẽ được truyền qua query string:

~~~text
/graphql?query=...&operationName=SearchBooks&variables=...
~~~

Query string thường xuất hiện trong:

- Access log của reverse proxy và web server.
- Browser history.
- HTTP Referer.
- Log của gateway, CDN và hệ thống giám sát mạng.

Vì vậy, nếu variables có thể chứa thông tin nhạy cảm, không bật GET cho endpoint đó trừ khi đã xử lý các đường lộ dữ liệu liên quan. GraphQL GET chỉ nên thực thi Query; Mutation phải dùng phương thức phù hợp và không được thực thi qua GET.

Ngay cả khi ứng dụng chỉ dùng POST, không nên bật request-body logging tại proxy, gateway, filter hoặc HTTP client/server debug mà chưa có chính sách redaction. WebGraphQlInterceptor chạy sau transport; nó không thể xóa dữ liệu đã bị ghi ở access log trước đó.

Cần kiểm tra riêng:

- Reverse proxy / ingress access log có ghi query string không.
- API gateway có log request body không.
- Web server có bật wiretap hoặc debug payload không.
- WebSocket handshake có log headers/cookies không.
- RSocket interceptor có ghi payload không.
- APM agent có tự capture request/response body không.

## 10. Log injection và dữ liệu do client kiểm soát

Operation name, request ID, error text và metadata có thể do client kiểm soát. Nếu ghi trực tiếp ký tự CR/LF hoặc delimiter, attacker có thể tạo log line giả hoặc làm sai cấu trúc log.

Không ghép chuỗi log bằng dữ liệu đầu vào:

~~~java
// Không an toàn: dữ liệu client có thể chứa CR/LF.
log.warn("GraphQL request failed: " + operationName);
~~~

Dùng message template cố định và tham số:

~~~java
log.warn("GraphQL request failed operation={}", safeOperation);
~~~

Parameterized logging giúp giữ message template cố định, nhưng không tự loại bỏ CR/LF khỏi giá trị. Hãy dùng structured JSON encoder có escaping đúng, giới hạn độ dài và chuẩn hóa dữ liệu đầu vào trước khi ghi.

Ví dụ helper:

~~~java
public final class SafeLogValue {

    private SafeLogValue() {
    }

    public static String sanitize(String value, int maxLength) {
        if (value == null) {
            return "null";
        }

        int limit = Math.max(0, maxLength);
        String bounded = value.substring(0, Math.min(value.length(), limit));
        return bounded
                .replace('\r', '_')
                .replace('\n', '_')
                .replace('\t', '_');
    }
}
~~~

Helper này chỉ xử lý ký tự điều khiển và độ dài. Nó không phải hàm redaction bí mật. Không truyền raw variables, headers, exception message hoặc query text vào helper rồi cho rằng chúng đã an toàn.

Với structured logging, hãy để logging framework encode chuỗi đúng định dạng JSON. Không tự ghép JSON bằng string concatenation.

## 11. Structured logging với Spring Boot

Structured logging ghi mỗi event dưới dạng JSON hoặc format có schema rõ ràng. Điều này giúp hệ thống tập trung log lọc theo request ID, service, outcome và duration mà không phải parse chuỗi tự do.

Spring Boot từ 3.4 hỗ trợ structured logging với các format như ECS và Logstash; các phiên bản mới hơn còn có GELF. Ví dụ cấu hình ECS:

~~~yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs

spring:
  application:
    name: catalog-graphql
~~~

Có thể bổ sung metadata service:

~~~yaml
logging:
  structured:
    ecs:
      service:
        name: catalog-graphql
        version: 1.0.0
        environment: production
~~~

Structured logging không tự làm dữ liệu an toàn. Nếu ứng dụng đưa token vào message hoặc MDC, JSON encoder vẫn sẽ ghi token đó thành một field. Hãy xây dựng allowlist trước khi gọi logger.

Spring Boot cho phép include/exclude/rename một số JSON members. Đây là lớp phòng vệ bổ sung cho output format, không thay thế việc không đưa dữ liệu nhạy cảm vào log event ngay từ đầu.

Nếu sử dụng MDC để thêm request ID, hãy bảo đảm MDC được dọn sau request và được truyền đúng qua async/reactive boundary. Với WebFlux, không giả định ThreadLocal/MDC tự đi theo mọi bước Reactor pipeline; dùng context propagation phù hợp hoặc truyền correlation metadata trong Reactor Context.

## 12. Interceptor nào phù hợp với transport?

Spring GraphQL hỗ trợ nhiều transport và mỗi transport có điểm interception riêng:

| Transport | Extension point | Phạm vi |
| --- | --- | --- |
| HTTP | WebGraphQlInterceptor | Request/response của GraphQL qua HTTP. |
| WebSocket | WebGraphQlInterceptor hoặc WebSocketGraphQlInterceptor | Từng GraphQL request và lifecycle của connection/subscription. |
| RSocket | RSocketQlInterceptor | Request/response GraphQL qua RSocket. |

Một WebGraphQlInterceptor không phải nơi duy nhất cần kiểm tra. Access log của proxy, WebSocket handshake logging và RSocket payload logging nằm ở những lớp khác nhau.

Với WebSocket, tránh ghi connection_init payload hoặc headers chứa token. Với subscription, tránh log mỗi event payload đầy đủ; hãy log số event, trạng thái stream, thời lượng, cancellation và error category.

## 13. MDC và correlation ID

Correlation ID giúp tìm tất cả log liên quan đến một request. Có thể dùng transport request ID, GraphQL execution ID hoặc trace ID đã được cấu hình.

Quy tắc:

- Ưu tiên ID do server hoặc tracing system cấp.
- Nếu chấp nhận ID từ client, giới hạn độ dài và ký tự; không dùng ID đó để xác thực.
- Không để correlation ID trở thành metric tag không giới hạn.
- Không đưa token hoặc user identity vào correlation ID.
- Khi request chạy bất đồng bộ, bảo đảm context được truyền và dọn đúng cách.
- Ghi ID ở request start, completion và internal error để dễ liên kết.

Ví dụ log an toàn:

~~~text
event=graphql.request.completed
service=catalog-graphql
request_id=6d3f1f7a
trace_id=4bf92f3577b34da6
operation=SearchBooks
outcome=SUCCESS
error_count=0
duration_ms=42
~~~

Ví dụ này không chứa document, variables, authorization header hoặc response data.

## 14. Log sự kiện bảo mật nào?

Không chỉ log lỗi kỹ thuật. Những sự kiện sau có thể hữu ích cho phát hiện và điều tra:

| Sự kiện | Dữ liệu phù hợp để ghi |
| --- | --- |
| Authentication failure | Thời điểm, request ID, phương thức xác thực, outcome; không ghi credential. |
| Authorization denial | Operation/field label, error category, actor pseudonym nếu được phép. |
| Query depth/complexity limit | Operation label, measured depth/cost, configured limit, outcome. |
| Rate limit | Client category hoặc pseudonym, limit bucket, request ID, outcome. |
| Invalid persisted query | Persisted query hash đã được phân loại, operation label nếu biết. |
| Mutation quản trị | Actor pseudonym, action, entity type, entity ID được phép, outcome. |
| Schema/introspection policy violation | Operation category, outcome, request ID. |
| Logging pipeline failure | Sink, retry count, degraded state; không ghi payload của request để bù. |

Security audit log cần ghi sự kiện có ý nghĩa, không phải dump mọi request body. Nếu log actor hoặc tenant, hãy xác định mục đích, phân loại dữ liệu và retention trước khi triển khai.

Không lấy IP từ X-Forwarded-For một cách mù quáng. Chỉ tin forwarded headers từ proxy được cấu hình là trusted; cân nhắc masking hoặc pseudonymization nếu IP không cần thiết cho mục đích điều tra.

## 15. Bảo vệ log sau khi ghi

Log có thể chứa metadata vận hành và thông tin cá nhân. Hãy bảo vệ cả quá trình ghi, truyền, lưu và truy cập:

- Giới hạn quyền đọc log theo vai trò và nhu cầu công việc.
- Ghi nhận và theo dõi hoạt động truy cập log.
- Mã hóa khi truyền log tới hệ thống tập trung và khi lưu trữ nếu chính sách yêu cầu.
- Bảo vệ tính toàn vẹn, phát hiện sửa/xóa trái phép.
- Giới hạn kích thước event và tốc độ ghi để tránh log flooding làm đầy đĩa.
- Có cảnh báo khi log pipeline ngừng hoạt động hoặc queue bị đầy.
- Định nghĩa retention theo mục đích, phân loại dữ liệu và nghĩa vụ pháp lý.
- Không giữ log lâu hơn thời hạn đã phê duyệt; cũng không xóa sớm khi còn nghĩa vụ lưu trữ.
- Bảo vệ bản sao, backup, export và file tạm theo cùng chính sách.
- Khi gửi log cho bên thứ ba, kiểm tra hợp đồng, vị trí lưu trữ và quyền truy cập.

Không dùng chung một policy retention cho mọi log. Operational logs, security audit logs và traces có thể cần thời hạn lưu khác nhau.

## 16. Logging không được làm hỏng request processing

Logging có chi phí CPU, I/O và bộ nhớ. Một request có thể resolve hàng trăm field; log từng field hoặc từng DataLoader item có thể tạo lượng log rất lớn.

Một số nguyên tắc:

- Ghi một event ở đầu và cuối request khi cần, thay vì log mọi resolver.
- Dùng metrics/traces cho latency và thống kê có cấu trúc.
- Giới hạn độ dài field do client kiểm soát.
- Không serialize toàn bộ variables/response chỉ để đếm kích thước.
- Cân nhắc sampling cho log thành công có lưu lượng cao.
- Luôn giữ lại các security event bắt buộc theo policy.
- Dùng bounded async appender/queue và theo dõi dropped events.
- Tránh ghi log đồng bộ tới remote sink trên thread xử lý request.
- Có chính sách khi logging backend bị lỗi: operational log không nên làm request bình thường thất bại; audit bắt buộc cần cơ chế bền vững và quyết định fail-open/fail-closed theo yêu cầu nghiệp vụ.

Sampling chỉ áp dụng cho loại log có thể giảm theo chính sách. Không sampling tùy tiện các sự kiện bảo mật hoặc audit bắt buộc.

## 17. Kiểm thử logging an toàn

Một bài kiểm thử tốt cần chứng minh dữ liệu nhạy cảm không xuất hiện trong log. Chỉ kiểm tra rằng interceptor đã được gọi là chưa đủ.

Các trường hợp nên kiểm tra:

1. Variables chứa password, accessToken, email hoặc payment token không xuất hiện trong log.
2. Header Authorization và Cookie không xuất hiện.
3. Extensions không bị serialize tự động.
4. Error message chứa raw input không được ghi nguyên văn.
5. Operation name lạ được chuyển thành nhãn other.
6. Request ID có CR/LF được chuẩn hóa và giới hạn độ dài.
7. Response data không xuất hiện trong log.
8. Request hoàn tất có duration và error count.
9. Request lỗi transport có exception type nhưng không có message nhạy cảm.
10. Trace ID được liên kết đúng nhưng không xuất hiện trong metric labels.
11. Log GET/access log không lưu query string hoặc variables nhạy cảm.
12. WebSocket/RSocket log không ghi payload xác thực hoặc subscription event data.

Ví dụ kiểm thử sanitizer:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SafeLogValueTests {

    @Test
    void removesLineBreaksAndLimitsLength() {
        String result = SafeLogValue.sanitize(
                "SearchBooks\r\nforged-entry",
                16);

        assertThat(result).doesNotContain("\r", "\n");
        assertThat(result).hasSizeLessThanOrEqualTo(16);
    }
}
~~~

Ví dụ kiểm thử interceptor nên dùng appender test hoặc logger capture để kiểm tra output thực tế. Tạo request fixture với variables và headers giả lập chứa secret marker, chạy qua interceptor, sau đó xác nhận log có request ID/outcome nhưng không chứa các marker bí mật.

Không dùng secret thật trong test; dùng chuỗi giả như TEST_ONLY_SECRET_123.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong log | Log toàn bộ headers hoặc request body | Chỉ log allowlist metadata. |
| Password xuất hiện trong trace | Variables hoặc error message được export thành span event | Kiểm tra Observation events và exception messages; loại dữ liệu nhạy cảm. |
| Log có nhiều dòng giả | Client đưa CR/LF vào operation name hoặc ID | Sanitize, giới hạn độ dài và dùng structured encoder. |
| Access log có query/variables | Bật GraphQL GET hoặc proxy ghi query string | Tắt GET khi variables nhạy cảm; cấu hình access log ở proxy. |
| Operation name tạo metric cardinality lớn | Dùng tên operation do client gửi làm metric tag | Dùng allowlist/enum label hoặc chỉ để giá trị high-cardinality trong trace. |
| Không tìm được request qua nhiều service | Correlation ID không được truyền xuyên transport | Dùng trace context và request ID được kiểm soát. |
| Log lặp nhiều lần | Interceptor, exception resolver và transport đều ghi cùng một lỗi | Chọn một lớp chịu trách nhiệm cho từng event; liên kết bằng request ID. |
| Log bị đầy hoặc tăng chi phí | Log từng field/event hoặc body lớn | Sampling có kiểm soát, giới hạn kích thước và dùng metrics/traces. |
| MDC bị lẫn giữa request | ThreadLocal không được dọn hoặc context không truyền đúng qua async/reactive | Dùng context propagation và kiểm thử concurrency. |
| Không có log khi logging backend lỗi | Không theo dõi queue/sink failure | Thêm health signal, dropped-event metric và alert. |
| Log chứa stack trace nhạy cảm | Exception message hoặc suppressed exception chứa input | Rà soát exception trước khi ghi; chỉ xuất stack trace vào sink có quyền hạn phù hợp. |

## 19. Checklist triển khai

1. Xác định mục tiêu riêng cho operational log, security audit và trace.
2. Định nghĩa schema log allowlist và phân loại từng field.
3. Không log raw GraphQL document, variables, extensions, request body hoặc response data.
4. Không log Authorization, Cookie, API key, password, token hoặc session ID.
5. Dùng WebGraphQlInterceptor cho HTTP/WebSocket và RSocketQlInterceptor cho RSocket khi cần.
6. Ghi request ID, operation label đã allowlist, outcome, error count và duration.
7. Sanitize mọi giá trị client kiểm soát; giới hạn độ dài và chống CR/LF.
8. Dùng structured logging encoder; parameterized logging không tự ngăn log injection.
9. Kiểm tra access log, reverse proxy, APM, debug log và GET query string.
10. Rà soát Observation events vì error message có thể được ghi vào trace.
11. Không dùng high-cardinality values làm metric labels.
12. Bảo vệ log bằng quyền truy cập, mã hóa, integrity monitoring và retention policy.
13. Giới hạn tốc độ/kích thước log và theo dõi logging pipeline.
14. Kiểm thử bằng secret marker để chứng minh dữ liệu nhạy cảm không xuất hiện.
15. Ghi lại chính sách logging trong tài liệu vận hành và review khi schema/transport thay đổi.

## 20. Tài liệu tham khảo

- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Logging and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

Log request an toàn trong Spring for GraphQL bắt đầu bằng việc xác định dữ liệu nào thật sự cần cho vận hành. Hãy ghi metadata có cấu trúc, giới hạn và có thể truy vết; để document, variables, headers, cookies, response data và error message ở ngoài log mặc định. Kết hợp interceptor đúng transport, Observation được kiểm soát, structured logging, bảo vệ kho log và kiểm thử bằng secret marker để vừa điều tra được sự cố vừa hạn chế rò rỉ dữ liệu.
