# Không log token và secret trong Spring for GraphQL

Log giúp theo dõi hoạt động, điều tra sự cố và phát hiện hành vi bất thường. Nhưng log cũng là một nơi dễ làm lộ credential nếu ứng dụng ghi toàn bộ HTTP headers, GraphQL request body, variables, execution context hoặc exception message.

Trong Spring for GraphQL, dữ liệu nhạy cảm có thể xuất hiện ở nhiều lớp: HTTP Authorization header, Cookie, GraphQL variables, literal trong GraphQL document, WebSocket connection_init payload, RSocket metadata, GraphQLContext, kết quả mutation và thông tin lỗi. Quy tắc an toàn là chỉ ghi những trường cần thiết cho vận hành theo allowlist; không ghi nguyên request/response rồi mới tìm cách che secret sau đó.

Bài này áp dụng cho ứng dụng Spring for GraphQL dùng Query, Mutation, Subscription và các transport HTTP, WebSocket hoặc RSocket. Nội dung tập trung vào cách thiết kế log an toàn mà vẫn đủ thông tin để truy vết request và điều tra lỗi.

## 1. Vì sao token và secret không được xuất hiện trong log?

Log thường được chuyển tới nhiều hệ thống: console, file, container runtime, agent thu thập log, APM, SIEM, kho lưu trữ tập trung, bản sao lưu và công cụ hỗ trợ vận hành. Một người có quyền đọc log có thể không có quyền truy cập database hoặc secret manager của ứng dụng.

Nếu log chứa token hoặc secret, người đọc log có thể sử dụng chúng để:

- Mạo danh người dùng bằng access token hoặc session cookie.
- Dùng refresh token để tạo access token mới.
- Gọi API nội bộ bằng API key hoặc service credential.
- Truy cập database bằng connection string có username/password.
- Giải mã hoặc ký dữ liệu nếu log làm lộ encryption key/private key.
- Chiếm tài khoản qua mật khẩu, OTP, reset token hoặc recovery code.
- Truy cập dữ liệu cá nhân hoặc thông tin thanh toán được ghi kèm request.

Secret bị log có thể tồn tại lâu hơn vòng đời của credential trong ứng dụng vì log được sao lưu, nhân bản và lưu trữ theo retention policy. Việc xóa một dòng log ở một nơi không bảo đảm các bản sao đã biến mất.

## 2. Nhận diện dữ liệu nhạy cảm trong GraphQL

Không chỉ trường có tên token hoặc password mới là secret. Hãy xác định dữ liệu dựa trên khả năng cấp quyền, xác thực, khôi phục tài khoản hoặc tiết lộ thông tin riêng tư.

| Nhóm dữ liệu | Ví dụ trong GraphQL/Spring | Cách xử lý log |
| --- | --- | --- |
| Access/refresh token | Authorization: Bearer ..., token trong mutation login | Không log giá trị; nếu cần, log loại credential và kết quả xác thực. |
| Session credential | JSESSIONID, SESSION cookie, session ID | Không log raw value; dùng fingerprint có khóa nếu cần correlation. |
| Password/PIN/OTP | login(password), changePassword, verifyOtp | Không log giá trị, kể cả khi validation thất bại. |
| API key/client secret | X-API-Key, client_secret, webhook secret | Không log header hoặc input value. |
| Cryptographic key | Private key, signing key, encryption key | Tuyệt đối không log key material; chỉ log key identifier/version. |
| Database credential | JDBC URL có user/password, connection string | Che toàn bộ credential và các tham số nhạy cảm. |
| Personal/sensitive data | Email, số điện thoại, địa chỉ, thông tin sức khỏe | Chỉ log khi có căn cứ và nhu cầu; ưu tiên pseudonymization. |
| Payment data | Card number, CVV, bank account | Không log dữ liệu xác thực thanh toán; tuân thủ phạm vi PCI và quy định liên quan. |
| Recovery data | Password reset token, magic link, invite token | Không log token hoặc URL chứa token. |

Một GraphQL input có thể chứa secret dù schema không dùng tên trường nhạy cảm. Ví dụ trường credential, proof, authorizationCode hoặc challengeResponse đều cần được phân loại theo nghiệp vụ.

## 3. Các vị trí GraphQL thường làm lộ secret

### HTTP headers và cookies

Các header cần loại khỏi log thô:

- Authorization
- Proxy-Authorization
- Cookie
- Set-Cookie
- X-API-Key và các header API key tùy chỉnh
- Header chứa chữ ký, client secret hoặc credential nội bộ

Không log toàn bộ HttpHeaders bằng cách gọi toString hoặc serialize cả map. Header có thể chứa nhiều credential ngoài những tên phổ biến.

### GraphQL document và variables

Một request GraphQL thường có cấu trúc JSON:

~~~json
{
  "query": "mutation Login($input: LoginInput!) { login(input: $input) { accessToken } }",
  "operationName": "Login",
  "variables": {
    "input": {
      "username": "user@example.com",
      "password": "correct-horse-battery-staple"
    }
  }
}
~~~

Nếu log toàn bộ body, password có thể bị lưu lại. Không chỉ variables mới nhạy cảm: client cũng có thể viết literal trực tiếp trong document:

~~~graphql
mutation {
    login(input: {
        username: "user@example.com",
        password: "literal-password"
    }) {
        accessToken
    }
}
~~~

Do đó, không log raw GraphQL document, variables hoặc toàn bộ request body theo mặc định. Việc chỉ xóa field password khỏi variables vẫn không an toàn nếu secret có thể nằm trong literal, alias hoặc input object lồng nhau.

### GraphQLContext và Principal

GraphQLContext có thể chứa tenant, principal, locale, correlation ID hoặc metadata xác thực. Không log toàn bộ context, Principal.toString(), Authentication object hay SecurityContext. Các object này có thể chứa credential, authorities nội bộ hoặc thông tin cá nhân.

Nếu cần log danh tính, chỉ ghi một định danh đã được phê duyệt, có thể pseudonymize hoặc dùng mã nội bộ không mang ý nghĩa credential.

### WebSocket connection_init

GraphQL WebSocket client có thể gửi authentication payload khi khởi tạo kết nối. Payload có thể chứa access token hoặc session credential. Tránh bật frame-level logging hoặc debug logging có thể ghi nguyên nội dung connection_init.

Sau khi kết nối, các message subscribe/next/error cũng có thể chứa dữ liệu nghiệp vụ nhạy cảm. Không log toàn bộ frame hoặc event payload nếu chưa có chính sách phân loại.

### RSocket metadata

Nếu dùng RSocket, credential có thể nằm trong metadata hoặc setup payload thay vì HTTP Authorization header. Áp dụng cùng quy tắc: không dump metadata map, setup payload hoặc authentication object vào log.

## 4. Dùng allowlist thay vì log tất cả rồi redact

Allowlist xác định trước các trường được phép ghi. Cách này an toàn hơn denylist vì ứng dụng không thể biết hết mọi tên trường secret mà client có thể gửi.

Ví dụ các trường log thường đủ cho vận hành:

| Trường log | Ví dụ | Ghi chú |
| --- | --- | --- |
| event | graphql.request.completed | Tên sự kiện cố định. |
| operation | Login, SearchBooks | Chỉ ghi operation name đã kiểm soát hoặc chuyển thành nhãn an toàn. |
| correlationId | ID do server sinh | Không dùng access token/session ID làm correlation ID. |
| durationMs | 42 | Thời gian xử lý. |
| outcome | SUCCESS, GRAPHQL_ERROR, TRANSPORT_ERROR | Phân loại kết quả. |
| errorCount | 1 | Số lượng lỗi, không phải toàn bộ error payload. |
| errorCode | BOOK_NOT_FOUND | Chỉ dùng mã lỗi đã được phê duyệt. |
| userRef | HMAC/pseudonymous ID | Không ghi raw token hoặc session ID. |
| transport | HTTP, WEBSOCKET, RSOCKET | Hữu ích để phân loại nguồn request. |

Không đưa các trường sau vào allowlist mặc định:

- Raw Authorization/Cookie headers.
- Raw request body, GraphQL document và variables.
- Raw GraphQLContext, Principal hoặc Authentication.
- Raw response body hoặc subscription event payload.
- Exception message chưa được kiểm duyệt.
- Database URL, connection string hoặc secret manager response.

## 5. Ví dụ log không an toàn và log an toàn

### Cách không an toàn

~~~java
log.info("GraphQL request: {}", request);
log.debug("GraphQL headers: {}", request.getHeaders());
log.debug("GraphQL context: {}", executionInput.getGraphQLContext());
log.error("GraphQL failed: {}", exception.getMessage(), exception);
~~~

Các cách trên có thể ghi request, header, context hoặc exception chứa credential. Chỉ hạ log level xuống DEBUG không giải quyết vấn đề nếu môi trường production có thể bật DEBUG/TRACE để điều tra sự cố.

### Cách an toàn hơn

Ghi event với các trường được chọn rõ ràng:

~~~java
log.info(
        "graphql.request.completed operation={} correlationId={} durationMs={} errorCount={}",
        operationLabel,
        correlationId,
        durationMs,
        errorCount);
~~~

Với lỗi, ưu tiên ghi loại lỗi và mã lỗi nội bộ đã phân loại:

~~~java
log.warn(
        "graphql.request.failed operation={} correlationId={} exceptionType={}",
        operationLabel,
        correlationId,
        exception.getClass().getSimpleName());
~~~

Nếu cần stack trace để điều tra, hãy dùng một luồng log hạn chế quyền truy cập, có redaction đã kiểm thử và retention ngắn phù hợp. Đừng tự động ghi toàn bộ exception object ở mọi logger vì message, cause hoặc custom field có thể chứa secret.

## 6. Tạo WebGraphQlInterceptor chỉ ghi metadata an toàn

WebGraphQlInterceptor cho phép quan sát request và response ở HTTP/WebSocket transport. Không cần log body để biết operation nào đang chạy, thời gian xử lý và có bao nhiêu GraphQL errors.

Ví dụ dưới đây chỉ ghi operation label nằm trong allowlist, correlation ID do server sinh, thời gian và số lỗi:

~~~java
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SafeGraphQlLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGraphQlLoggingInterceptor.class);

    private static final Set<String> ALLOWED_OPERATIONS =
            Set.of("SearchBooks", "CreateOrder", "TrackOrder");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        long startedAt = System.nanoTime();
        String correlationId = UUID.randomUUID().toString();
        String operation = safeOperationLabel(request.getOperationName());

        return chain.next(request)
                .doOnNext(response -> log.info(
                        "graphql.request.completed operation={} correlationId={} durationMs={} errorCount={}",
                        operation,
                        correlationId,
                        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt),
                        response.getErrors().size()))
                .doOnError(error -> log.warn(
                        "graphql.request.failed operation={} correlationId={} exceptionType={}",
                        operation,
                        correlationId,
                        error.getClass().getSimpleName()));
    }

    private String safeOperationLabel(String operationName) {
        if (operationName == null || !ALLOWED_OPERATIONS.contains(operationName)) {
            return "OTHER";
        }
        return operationName;
    }
}
~~~

Điểm cần lưu ý:

- Interceptor không đọc hoặc ghi request body.
- Không serialize request headers, variables, GraphQLContext hoặc response data.
- Operation name chỉ được ghi nếu nằm trong allowlist. Operation name do client gửi nên không nên mặc định xem nó là dữ liệu đáng tin cậy.
- Correlation ID được server tạo mới, không lấy từ Authorization header hoặc cookie.
- Khi lỗi reactive xảy ra, ví dụ chỉ ghi exception class. Nếu cần stack trace, phải có chính sách log riêng.
- Interceptor này không tự động bảo vệ log của reverse proxy, gateway, WebSocket frame logger hoặc APM agent; các lớp đó cần cấu hình riêng.

Nếu dùng nhiều interceptor, hãy bảo đảm interceptor logging không nằm sau một interceptor khác đã ghi raw headers/body. Quy tắc allowlist cần áp dụng xuyên suốt chain.

## 7. Không copy Authorization header vào GraphQLContext để log

Spring for GraphQL có thể dùng HttpRequestHeaderInterceptor để sao chép một số HTTP header vào GraphQLContext. Chỉ map header thực sự cần cho nghiệp vụ; không map Authorization, Cookie hoặc API key chỉ để tiện debug.

Ví dụ mapping một header không nhạy cảm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration
class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Region")
                .build();
    }
}
~~~

Nếu ứng dụng cần access token để xác thực, hãy để Spring Security xử lý credential và cung cấp principal/authentication qua security context. Không cần copy raw token vào GraphQLContext. Resolver chỉ nên nhận principal hoặc thông tin quyền cần thiết, không nhận lại credential thô.

## 8. Không log response hoặc GraphQL errors nguyên bản

Secret không chỉ nằm trong request. Mutation có thể trả API key một lần, refresh token hoặc thông tin nhạy cảm. Resolver error cũng có thể chứa invalid value, SQL fragment, upstream URL, token hoặc exception message từ dependency.

Không log:

~~~java
log.info("GraphQL response: {}", response);
log.error("GraphQL errors: {}", response.getErrors());
~~~

Thay vào đó, ghi số lượng lỗi và mã lỗi đã chuẩn hóa:

~~~java
int errorCount = response.getErrors().size();
log.info("graphql.response.completed errorCount={}", errorCount);
~~~

Nếu cần phân tích error category, hãy ánh xạ exception sang mã ổn định như VALIDATION_FAILED, ACCESS_DENIED hoặc UPSTREAM_UNAVAILABLE. Tránh dùng raw message do client hoặc dependency cung cấp làm log field.

## 9. Che dữ liệu nếu buộc phải ghi một phần

Ưu tiên bỏ hẳn trường nhạy cảm khỏi log. Chỉ mask khi có yêu cầu nghiệp vụ được phê duyệt và vẫn cần một phần giá trị để điều tra.

Ví dụ:

| Dữ liệu gốc | Cách xử lý ưu tiên |
| --- | --- |
| Authorization: Bearer eyJ... | Không ghi header; nếu cần, ghi credentialType=BEARER. |
| Session ID | Không ghi raw ID; dùng HMAC fingerprint nếu cần correlation. |
| Email | Dùng user reference hoặc che một phần nếu được phép. |
| API key | Chỉ ghi key identifier/version, không ghi secret value. |
| Database URL | Ghi tên datasource hoặc database alias, không ghi URL có credential. |
| Password/OTP/reset token | Không ghi bất kỳ phần nào của giá trị. |

Không dùng phép thay thế đơn giản như chỉ giữ 4 ký tự cuối của access token hoặc API key. Một phần token vẫn có thể giúp tương quan hoặc hỗ trợ tấn công, và không mang lại giá trị chẩn đoán đáng kể.

Nếu cần liên kết các log của cùng session, OWASP khuyến nghị không ghi raw session ID. Có thể dùng salted hash/fingerprint để correlation. Trong hệ thống cần chống việc đoán giá trị hoặc tái sử dụng fingerprint ngoài mục đích log, ưu tiên HMAC với khóa riêng dành cho logging, được quản lý và luân chuyển độc lập.

Không dùng hash không khóa cho dữ liệu có entropy thấp như email, số điện thoại hoặc username nếu có thể dò từ điển. Pseudonymization không đồng nghĩa với dữ liệu đã ẩn danh.

## 10. Redaction phải xảy ra trước khi dữ liệu rời ứng dụng

Một pipeline log có thể gồm:

~~~mermaid
flowchart LR
    A[HTTP / WebSocket / RSocket request] --> B[Application]
    B --> C[Allowlist và sanitize trước log call]
    C --> D[Structured log event]
    D --> E[Log agent]
    E --> F[Central log platform]
    F --> G[Retention / archive]
~~~

Nếu ứng dụng gửi raw token vào appender rồi mới redact ở log collector, secret đã đi qua process memory, file tạm, agent buffer hoặc network. Redaction sau khi thu thập không thể bảo đảm xóa hết các bản sao.

Vì vậy:

1. Không tạo log event chứa secret.
2. Nếu có sanitizer, chạy nó trước khi gọi logger.
3. Chỉ truyền các trường đã được chọn vào structured logging encoder.
4. Cấu hình log agent, gateway và APM để loại bỏ header/body nhạy cảm như lớp phòng vệ bổ sung.
5. Kiểm tra cả log file, console, container logs, trace attributes và bản sao lưu.

## 11. Cẩn thận với structured logging, MDC và tracing

Structured logging giúp log có trường rõ ràng và dễ truy vấn, nhưng JSON không tự động làm dữ liệu an toàn. Nếu đưa token vào field authorization, encoder vẫn sẽ ghi token đó.

Spring Boot hỗ trợ structured logging với các format như ECS, GELF và Logstash. Có thể bổ sung MDC hoặc các field ad-hoc, nhưng chỉ thêm metadata đã được phê duyệt:

~~~yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs
~~~

Không đặt Authorization, raw session ID, password hoặc secret vào MDC. MDC có thể được đưa vào mọi log line của request, làm tăng phạm vi rò rỉ.

Với tracing/OpenTelemetry/APM, không gắn raw token, cookie, GraphQL variables hoặc request/response body vào span attributes hay span events. Các trace thường được gửi đến hệ thống khác và có retention riêng. Dùng các thuộc tính ít nhạy cảm như operation label, transport, duration, error category và correlation ID.

## 12. Kiểm tra các lớp log ngoài ứng dụng

Ngay cả khi WebGraphQlInterceptor an toàn, credential vẫn có thể bị ghi ở lớp khác:

| Thành phần | Rủi ro | Biện pháp |
| --- | --- | --- |
| Reverse proxy / ingress | Log URI/query string, headers hoặc request body | Chỉ log route cần thiết; loại Authorization/Cookie; không log body. |
| API gateway / WAF | Request inspection hoặc debug capture | Tắt body capture chứa credential; bật redaction theo chính sách. |
| Web server access log | Ghi query string hoặc header | Không dùng raw request target khi GET có thể chứa variables nhạy cảm. |
| WebSocket frame logger | Ghi connection_init payload và event frame | Không log payload xác thực hoặc nội dung frame. |
| RSocket logging | Ghi metadata/setup payload | Redact credential metadata trước khi ghi. |
| APM agent | Tự động capture HTTP body, header và exception | Tắt capture nhạy cảm, cấu hình field allowlist/denylist và xác minh. |
| Container platform | Thu thập stdout/stderr | Không in secret ra console; giới hạn quyền đọc và retention. |
| CI/CD và startup diagnostics | In environment/configuration | Không dump toàn bộ config hoặc secret environment variable. |

Không giả định một lớp đã che dữ liệu thì lớp tiếp theo cũng được bảo vệ. Kiểm tra cấu hình thực tế từ client đến nơi lưu log.

## 13. Chống log injection và log flooding

Operation name, user agent, correlation header, error input và một số metadata do client gửi đều là dữ liệu không đáng tin cậy. Nếu ghi trực tiếp chuỗi chứa newline hoặc ký tự điều khiển, kẻ tấn công có thể tạo log giả hoặc làm sai cấu trúc log.

Các biện pháp:

- Ưu tiên operation name nằm trong allowlist.
- Giới hạn độ dài cho mọi trường do client kiểm soát.
- Loại hoặc encode CR, LF và ký tự điều khiển trước khi log.
- Dùng structured logging thay vì nối chuỗi log thủ công.
- Không đưa raw GraphQL query, alias, path hoặc variables vào log.
- Giới hạn tần suất và kích thước log cho request lỗi lặp lại.
- Không ghi toàn bộ stack trace cho lỗi do client gây ra nếu không cần thiết.

Structured JSON encoder thường escape một số ký tự, nhưng vẫn cần kiểm soát kích thước và nội dung field. Không xem encoding là thay thế cho allowlist.

## 14. Bảo vệ log sau khi đã tạo

Log an toàn vẫn có thể chứa user reference, operation metadata, IP hoặc thông tin vận hành. Cần bảo vệ chính hệ thống lưu log:

- Chỉ cấp quyền đọc log cho nhóm cần thiết theo vai trò.
- Mã hóa dữ liệu khi truyền và khi lưu trữ.
- Giới hạn retention theo mục đích, quy định và chính sách tổ chức.
- Theo dõi truy cập, export, sửa đổi và xóa log.
- Tách quyền quản trị ứng dụng khỏi quyền quản trị log khi có thể.
- Bảo vệ backup và bản sao log giống như kho dữ liệu gốc.
- Kiểm tra log pipeline không âm thầm bỏ log security event quan trọng.
- Không lưu log debug tạm thời lâu hơn cần thiết.

Không ghi secret không có nghĩa là bỏ qua audit. Có thể ghi ai đã thực hiện hành động, hành động gì, tài nguyên thuộc loại nào, kết quả thành công/thất bại và mã tham chiếu an toàn mà không ghi credential hoặc payload nhạy cảm.

## 15. Kiểm thử để chứng minh secret không xuất hiện trong log

Một test hữu ích phải đưa marker secret giả vào các vị trí khác nhau, thực hiện request và xác nhận marker không xuất hiện trong log capture.

Ví dụ test với Spring Boot OutputCapture:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.junit.jupiter.api.extension.ExtendWith;

@ExtendWith(OutputCaptureExtension.class)
class GraphQlLoggingSecurityTests {

    @Test
    void doesNotLogAuthorizationToken(CapturedOutput output) {
        String fakeToken = "test-token-DO-NOT-LOG-7f9a";

        // Gửi GraphQL request qua test HTTP client với Authorization header.
        // Phần helper đại diện cho fixture của ứng dụng.
        performAuthenticatedGraphQlRequest(fakeToken);

        assertThat(output.getAll())
                .doesNotContain(fakeToken)
                .doesNotContain("Authorization: Bearer");
    }

    @Test
    void doesNotLogPasswordFromGraphQlVariables(CapturedOutput output) {
        String fakePassword = "test-password-DO-NOT-LOG-2c4e";

        performLoginMutation(fakePassword);

        assertThat(output.getAll())
                .doesNotContain(fakePassword);
    }
}
~~~

Hai helper trong ví dụ là test fixture do ứng dụng cung cấp; chúng phải gửi request qua HTTP handler thật và chờ request hoàn tất trước khi kiểm tra output.

Mở rộng test để bao phủ:

1. Authorization bearer token và cookie/session ID.
2. Password, OTP, reset token trong GraphQL variables.
3. Secret được viết trực tiếp thành literal trong GraphQL document.
4. WebSocket connection_init payload.
5. RSocket metadata nếu transport này được bật.
6. GraphQLContext và Principal không bị serialize.
7. Exception message và validation error không echo secret.
8. Mutation response chứa token một lần không bị log.
9. Structured logs, access logs, traces và APM capture.
10. CR/LF và payload rất dài không thể giả mạo hoặc làm tràn log.

Dùng marker giả duy nhất cho mỗi loại secret để biết chính xác đường đi của dữ liệu. Không dùng credential thật trong test, staging log hoặc ví dụ tài liệu.

## 16. Quy trình phản ứng khi phát hiện secret đã bị log

Nếu phát hiện token hoặc secret trong log, cần coi đó là một lần lộ credential:

1. Xác định loại secret, phạm vi hệ thống và khoảng thời gian bị ghi.
2. Thu hẹp quyền đọc log và ngăn log tiếp tục phát tán.
3. Thu hồi hoặc rotate credential nếu còn hiệu lực.
4. Xác định các bản sao: file local, log agent, SIEM, APM, backup và export.
5. Xử lý bản ghi theo quy trình xóa/retention được phê duyệt; không xóa dấu vết audit bắt buộc.
6. Kiểm tra truy cập log trong khoảng thời gian có nguy cơ.
7. Sửa nguồn log ở application, gateway hoặc agent.
8. Thêm regression test để xác nhận secret marker không còn xuất hiện.

Chỉ xóa dòng log ở một dashboard không đủ nếu dữ liệu đã được sao chép sang hệ thống khác. Nếu credential có thể đã bị truy cập, rotate/revoke quan trọng hơn việc chỉ che hiển thị.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong DEBUG log | Log cả request hoặc headers | Bỏ log dump; dùng allowlist metadata. |
| Password bị ghi trong mutation trace | APM tự động capture GraphQL body/variables | Tắt body capture hoặc cấu hình redaction tại agent. |
| Token nằm trong WebSocket logs | Debug frame logger ghi connection_init | Không log payload frame; chỉ log loại message và kết quả handshake. |
| Secret vẫn xuất hiện sau khi đã mask variables | Secret nằm trong literal hoặc nested input khác | Không log document/body; ưu tiên allowlist. |
| Raw session ID được dùng làm correlation | Dùng credential làm request identifier | Sinh correlation ID mới hoặc dùng HMAC fingerprint. |
| MDC làm lộ token trên mọi log line | Đưa Authorization vào MDC | Chỉ đưa metadata an toàn vào MDC và dọn context đúng lifecycle. |
| Exception log lộ connection string | Log toàn bộ exception message/stack trace không kiểm soát | Chuẩn hóa lỗi; giới hạn sink có quyền truy cập nếu cần stack trace. |
| Gateway log lộ query variables | GET request hoặc access log chứa query string | Không đưa secret vào URL; cấu hình access log theo route an toàn. |
| Secret bị lộ trong startup log | Dump environment/configuration | Chỉ log tên cấu hình hoặc secret reference, không log value. |

## 18. Checklist Không log token và secret

1. Dùng allowlist cho application log; không dump toàn bộ request/response.
2. Không log Authorization, Cookie, Set-Cookie, API key hoặc credential header.
3. Không log GraphQL document, variables hoặc raw request body.
4. Không log GraphQLContext, Principal, Authentication hoặc RSocket metadata.
5. Không log WebSocket connection_init payload và frame chứa dữ liệu nhạy cảm.
6. Không log mutation response có token, key hoặc secret.
7. Không log exception message/stack trace chưa được đánh giá có chứa dữ liệu nhạy cảm.
8. Chỉ dùng correlation ID do server tạo; pseudonymize user/session reference khi cần.
9. Redact trước log call; không dựa vào xử lý sau khi log đã được thu thập.
10. Kiểm soát MDC, structured logging, tracing, APM và gateway/access logs.
11. Sanitize dữ liệu do client kiểm soát để chống log injection và log flooding.
12. Hạn chế quyền đọc, retention, export và backup của log.
13. Kiểm thử bằng secret marker giả trên mọi transport được bật.
14. Có quy trình revoke/rotate credential và xử lý bản sao log khi phát hiện rò rỉ.

Không log token và secret là một yêu cầu xuyên suốt từ GraphQL resolver đến transport, gateway, APM và kho lưu trữ log. Spring for GraphQL cung cấp interceptor để ghi metadata ở cấp request, nhưng ứng dụng phải chủ động chọn trường được phép ghi. Khi log theo allowlist, không serialize payload/context, pseudonymize thông tin cần correlation và kiểm thử toàn bộ pipeline, đội vận hành vẫn có thể truy vết request mà không biến log thành nơi lưu credential.

Tài liệu tham khảo:
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Logging and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
