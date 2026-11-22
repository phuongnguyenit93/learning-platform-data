# Che mật khẩu, Authorization header, cookie và dữ liệu cá nhân trong log — Spring Security Reactive

## 1. Mục tiêu và phạm vi

Log giúp chẩn đoán lỗi xác thực, phân quyền, độ trễ và sự cố HTTP. Nhưng trong ứng dụng Spring Security chạy trên Spring WebFlux, chỉ một dòng log ghi toàn bộ request, exception hoặc HTTP client exchange cũng có thể đưa mật khẩu, bearer token, session cookie, refresh token hay dữ liệu cá nhân vào file log, hệ thống tập trung, trace, dashboard và bản sao lưu.

Sau bài này, người học cần:
- Nhận diện mọi điểm sinh log có thể nhận dữ liệu nhạy cảm trong luồng reactive.
- Thiết kế sự kiện log theo **danh sách trường cho phép (allowlist)**; không tuần tự hóa nguyên request, response hoặc security context.
- Phân biệt **loại bỏ**, **thay bằng dấu che** và **giả danh hóa**; chọn cách xử lý theo mục đích quan sát.
- Viết bộ lọc HTTP an toàn cho WebFlux, cấu hình thư viện và kiểm thử rò rỉ ở cả log ứng dụng lẫn hệ thống quan sát.

**Nguyên tắc quyết định:** Nếu một giá trị không thực sự cần thiết để điều tra sự cố, đừng tạo giá trị đó trong log. Che ở bước xuất log chỉ là lớp bảo vệ bổ sung, không thay thế việc tránh thu thập bí mật.

## 2. Vì sao log là một đường rò rỉ dữ liệu?

Một request đi qua nhiều lớp: reverse proxy/API gateway → Reactor Netty → WebFlux WebFilter → Spring Security WebFilterChain → controller/handler → WebClient hoặc dịch vụ phụ thuộc → logging/tracing/metrics. Bất kỳ lớp nào có thể ghi dữ liệu trước khi lớp che ở ứng dụng chạy. Log còn được sao chép sang bộ thu thập, APM, SIEM, ticket hỗ trợ, bản dump và backup với quyền truy cập rộng hơn dữ liệu nghiệp vụ.

Các trường hợp thường gặp:
1. Debug trực tiếp headers làm lộ Authorization: Bearer ..., Authorization: Basic ..., Cookie hoặc Set-Cookie.
2. Ghi request body ở endpoint đăng nhập, đổi mật khẩu hoặc tạo tài khoản làm lộ password, OTP, recovery code.
3. Ghi URL hoàn chỉnh làm lộ email, mã đặt lại mật khẩu, authorization code trong query string; URL path cũng có thể chứa tên hoặc định danh cá nhân.
4. In đối tượng Authentication, SecurityContext, Jwt, OAuth2AccessToken hay exception nguyên vẹn làm lộ principal, claims, credential hoặc thông tin đầu vào có trong message.
5. Bật HTTP wiretap/access log hoặc log request/response của WebClient mà không kiểm soát nội dung.
6. Gắn email, số điện thoại, session ID hoặc JWT vào trace baggage, span attribute, metric label hoặc MDC rồi vô tình đẩy sang backend quan sát.

Không nên cho rằng một chuỗi “chỉ xuất hiện trong DEBUG” sẽ an toàn: mức log có thể bị tăng khi khắc phục sự cố, và dữ liệu đã phát ra rất khó thu hồi khỏi toàn bộ bản sao.

## 3. Phân loại dữ liệu và hành động phù hợp

| Dữ liệu | Ví dụ nguồn | Quy tắc trong log |
| --- | --- | --- |
| Mật khẩu, password confirmation, PIN, OTP, mã khôi phục | Form, JSON body, query, exception | **Không ghi** giá trị, kể cả một phần; log mã sự kiện như LOGIN_FAILED. |
| Authorization / Proxy-Authorization | Bearer JWT, opaque token, Basic credentials | **Không ghi** header hoặc token; nếu buộc biểu thị sự hiện diện, chỉ ghi auth_present=true/false. |
| Cookie / Set-Cookie | Session ID, refresh token, CSRF token, preference | Không ghi giá trị, không dump cả collection; cookie tùy chọn cũng cần đánh giá riêng. |
| API key, client secret, access/refresh token | Header, cấu hình, body, OAuth2/JWT | Không ghi; không xuất raw claims, token prefix/suffix hay kết quả toString() của credential. |
| Email, số điện thoại, họ tên, địa chỉ, mã định danh, ngày sinh, địa chỉ IP | Path, query, payload, principal, headers | Mặc định không ghi. Chỉ giữ trường thật sự cần có cơ sở nghiệp vụ, mức bảo vệ và thời hạn lưu rõ ràng. |
| Trạng thái và thông số kỹ thuật | HTTP method, status, thời lượng, tên route tĩnh, mã lỗi chuẩn hóa | Có thể ghi bằng allowlist, sau khi xác minh trường không chứa dữ liệu người dùng. |
| ID để tương quan | Request ID sinh bởi máy chủ, trace ID tin cậy | Có thể ghi nếu không phải token/session ID và không được tạo từ dữ liệu cá nhân. |

Ba kỹ thuật cần phân biệt:

- **Loại bỏ (omit):** Không tạo field trong sự kiện log. Phù hợp nhất với password, token, cookie và payload.
- **Che (redact):** Nếu cần ghi nhận có một trường nhạy cảm, ghi hằng số [REDACTED] hoặc cờ boolean. Ví dụ auth_present=true; tuyệt đối không đưa giá trị gốc vào format argument, exception hay MDC.
- **Giả danh hóa (pseudonymize):** Trường hợp cần liên kết sự kiện theo một định danh, dùng ID ngẫu nhiên của phiên điều tra hoặc HMAC bằng khóa bí mật được quản lý riêng. Hash thường trực tiếp email/số điện thoại không đủ an toàn trước dò từ điển. Giá trị giả danh vẫn có thể được xem là dữ liệu cá nhân tùy bối cảnh.

Không coi “ẩn 4 ký tự cuối”, URL encoding, Base64 hoặc mã hóa theo dạng dễ đảo ngược là bảo vệ thích hợp cho bearer token. Token đủ quyền truy cập phải được xử lý như mật khẩu.

## 4. Thiết kế schema log theo allowlist

Thay vì log toàn bộ đối tượng, định nghĩa sự kiện hữu ích với bộ vận hành:

| Field | Ví dụ | Lưu ý |
| --- | --- | --- |
| event | http_request, auth_failed, downstream_error | Giá trị từ danh mục cố định, không lấy raw exception text. |
| request_id | UUID do máy chủ tạo | Không sử dụng session ID, access token hoặc email làm correlation ID. |
| method | GET, POST | Thuộc tính do framework cung cấp. |
| route | /accounts/{accountId} | Lấy **mẫu route** đã đăng ký; không lấy URL path thực tế chứa ID. |
| status | 200, 401, 403, 500, unset | unset nếu response chưa có HTTP status; không giả định 200 khi lỗi. |
| duration_ms | 38 | Đo trên đồng hồ đơn điệu; không phụ thuộc đồng hồ hệ thống. |
| failure_code | BAD_CREDENTIALS, ACCESS_DENIED | Mã cố định; không ghép username, bearer token hoặc chi tiết request. |

Ví dụ sự kiện an toàn (giá trị chỉ minh họa):

~~~text
event=http_request request_id=2d894fd1-12e6-4fc8-aa7b-9dedf380780d method=POST route=/login status=401 duration_ms=24 signal=on_complete
event=auth_failed request_id=2d894fd1-12e6-4fc8-aa7b-9dedf380780d failure_code=BAD_CREDENTIALS
~~~

Không đưa vào schema: body, query string, toàn bộ URL, các headers tùy ý, cookie, thông tin đăng nhập, access token, JWT claims, principal.toString(), stack trace có message chứa request input. Ngay cả key của một đối tượng JSON có thể nhạy cảm nếu không được chọn lọc.

## 5. Mẫu WebFilter ghi access log an toàn trong Spring WebFlux

Ví dụ sau dùng Java 17+, Spring Framework 6 / Spring Boot 3, Spring WebFlux và SLF4J. Đây là lớp component của một ứng dụng Spring có dependencies tương ứng; không phải chương trình Java độc lập chạy chỉ bằng javac. Lớp chỉ ghi field trong allowlist. Khi handler khớp route, dùng pattern từ framework thay vì đường dẫn thực tế; với request không khớp, dùng chữ unmatched.

~~~java
package example.logging;

import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class SafeHttpLoggingWebFilter implements WebFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeHttpLoggingWebFilter.class);

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        long started = System.nanoTime();
        String requestId = UUID.randomUUID().toString();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched"
                            : pattern.toString();

                    HttpStatusCode status = exchange.getResponse().getStatusCode();
                    String statusCode = status == null
                            ? "unset"
                            : Integer.toString(status.value());

                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    LOG.info(
                            "event=http_request request_id={} method={} route={} " +
                            "status={} duration_ms={} signal={}",
                            requestId, method, route, statusCode, elapsedMs,
                            signal.name().toLowerCase(Locale.ROOT));
                })
                .contextWrite(context -> context.put("requestId", requestId));
    }
}
~~~

**Giải thích kỹ thuật:**
- WebFilter chạy trong xử lý reactive; chain.filter(exchange) trả về Mono<Void>. doFinally chạy khi subscription hoàn tất, lỗi hoặc bị hủy. Ghi signal giúp phân biệt tình huống, còn status có thể chưa được thiết lập; unset thể hiện đúng điều đó.
- Không đọc exchange.getRequest().getURI(), getQueryParams(), getHeaders(), getCookies(), request body hay principal. Vì vậy việc URL chứa token hoặc cookie mang session không làm thay đổi dữ liệu mà bộ lọc xuất ra.
- HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE được lấy sau khi chain xử lý. Khi framework không có pattern, bộ lọc dùng unmatched. Chỉ dùng các pattern từ cấu hình route tin cậy; nếu hệ thống có route được tạo động từ dữ liệu người dùng, phải chuẩn hóa thêm.
- UUID do máy chủ sinh phục vụ tương quan. contextWrite truyền requestId qua Reactor Context cho downstream reactive operators; đoạn code không dựa vào ThreadLocal/MDC để giữ ID qua thread khác nhau.
- Không ghi response body. Nếu ứng dụng đã có hệ thống trace ID đáng tin, có thể dùng trace ID đã được kiểm soát thay cho việc phát sinh một request ID độc lập, để liên kết sự kiện nhất quán.

**Vị trí bộ lọc:** Spring Security WebFlux cũng dùng các WebFilter; hãy xác minh thứ tự và phạm vi thực tế của filter khi tích hợp với SecurityWebFilterChain. Bộ lọc ví dụ tập trung vào an toàn dữ liệu; yêu cầu “mọi request đều có access log” còn cần tính đến lỗi ở tầng Netty, gateway và trường hợp request chưa vào WebFlux.

## 6. Những cách log nguy hiểm và cách thay thế

Các dòng dưới đây minh họa **điều cần tránh**, được đặt trong ngữ cảnh đã có exchange hoặc jwt; đây không phải một chương trình độc lập:

~~~java
// Nguy hiểm: có thể chứa Authorization, Cookie, API key.
log.debug("headers={}", exchange.getRequest().getHeaders());

// Nguy hiểm: query/path có thể chứa reset_token, email, số điện thoại.
log.info("uri={}", exchange.getRequest().getURI());

// Nguy hiểm: ghi toàn bộ JWT hoặc nội dung credential.
log.debug("jwt={}", jwt.getTokenValue());

// Nguy hiểm: toString của đối tượng có thể chứa dữ liệu bất ngờ.
log.warn("authentication={}", authentication);
~~~

Thay bằng các sự kiện được định nghĩa từ trước:

~~~java
// Các biến method, route, statusCode là giá trị đã được kiểm soát.
log.info("event=http_request method={} route={} status={}",
        method, route, statusCode);

// Chỉ log mã lỗi ổn định, không log username hoặc credential.
log.warn("event=auth_failed reason=BAD_CREDENTIALS");
~~~

**Không ghi cả tập headers rồi hy vọng một regex ở log sink sẽ bắt mọi bí mật.** Header tên tùy chỉnh như X-Api-Key, X-Auth-Token hoặc tên do dịch vụ đối tác đặt rất dễ vượt qua danh sách denylist; các chuỗi secret có thể xuất hiện bên ngoài field dự đoán. Nếu có nhu cầu quan sát headers, chỉ chọn từng header thật sự an toàn và kiểm tra cả tên lẫn giá trị theo chính sách. Content-Type hoặc User-Agent cũng cần được đánh giá khi có thể chứa dữ liệu tùy ý.

## 7. Đăng nhập, lỗi xác thực và phân quyền trong Spring Security Reactive

Những đường nhạy cảm nhất thường là đăng nhập, đổi mật khẩu, forgot-password, OAuth2 callback, refresh token và xử lý CSRF/session. Đối với Spring Security:

1. **Authentication thất bại:** Ghi auth_failed và mã nguyên nhân đã chuẩn hóa (BAD_CREDENTIALS, ACCOUNT_LOCKED, TOKEN_EXPIRED khi được phân loại có kiểm soát). Không in username, form login body, AuthenticationException.getMessage() từ nguồn không kiểm soát hoặc đối tượng Authentication.
2. **Authorization thất bại:** Ghi access_denied, mẫu route, HTTP status và request ID. Không ghi toàn bộ GrantedAuthority, security context hoặc JWT claims mặc định; các role có thể tiết lộ quyền nội bộ.
3. **JWT/OAuth2:** Không ghi getTokenValue(), chuỗi token, Authorization code, refresh token, ID token hay danh sách claims đầy đủ. Nếu cần thống kê lỗi, dùng mã INVALID_SIGNATURE, EXPIRED, MISSING_TOKEN (được xác định nội bộ) và số lượng tổng hợp.
4. **Session/cookie:** Không ghi JSESSIONID, SESSION, XSRF-TOKEN hay Set-Cookie. Cookie có cờ HttpOnly hoặc Secure vẫn hiện trong HTTP headers ở server; các cờ đó không ngăn server ghi log.
5. **Exception và stack trace:** Một exception message có thể chứa path, input, response body hoặc dữ liệu người dùng. Chỉ log exception class được phép hoặc mã lỗi đã ánh xạ. Khi thực sự cần stack trace để điều tra, kiểm soát message, nơi lưu, quyền xem và thời hạn trước khi bật.

Ví dụ cách định dạng một sự kiện xác thực đáng dùng:

~~~text
event=auth_failed request_id=<server-generated-id> mechanism=password failure_code=BAD_CREDENTIALS
event=access_denied request_id=<server-generated-id> route=/admin/reports status=403
~~~

Dấu <server-generated-id> ở trên là ký hiệu minh họa, không phải nội dung log cố định. Nên giữ phản hồi gửi cho người dùng ở mức phù hợp để tránh lộ việc tài khoản có tồn tại hay không; chính sách thông báo đăng nhập là quyết định riêng với chính sách log.

## 8. WebClient và Reactor Netty: tránh lộ ở lớp HTTP thấp hơn

WebClient được dùng phổ biến trong dịch vụ WebFlux. Interceptor hoặc ExchangeFilterFunction dễ vô tình log request.headers(), request.url() hay response body khi điều tra lỗi downstream. Đặc biệt, body reactive là luồng một lần tiêu thụ: đọc body chỉ để log có thể làm thay đổi hành vi, tốn bộ nhớ, vi phạm backpressure và đưa dữ liệu vào log.

Có thể ghi service name cố định, method và status thay vì URL/headers/body. Ví dụ bean trong ứng dụng Spring, với tên đích đã xác định khi lập trình:

~~~java
package example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class SafeWebClientConfiguration {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeWebClientConfiguration.class);

    @Bean
    WebClient billingWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://billing.example.internal")
                .filter((request, next) ->
                        next.exchange(request)
                                .doOnNext(response -> LOG.info(
                                        "event=outbound_http service=billing " +
                                        "method={} status={}",
                                        request.method().name(),
                                        response.statusCode().value())))
                .build();
    }
}
~~~

Đây là ví dụ bean cần project Spring WebFlux và base URL thật được cung cấp qua cấu hình khi triển khai. Để ghi latency/error, có thể mở rộng bằng doOnError hoặc doFinally nhưng chỉ log loại lỗi/mã chuẩn hóa, không ghi thông điệp exception hay response body tùy ý. Không tự động biến request.url() thành field dù host có vẻ cố định: query/path có thể chứa token.

**Reactor Netty wiretap:** Các cấu hình bật wiretap và DEBUG/TRACE có thể phát ra headers và nội dung mạng tùy chế độ. Không bật wiretap ghi payload trong môi trường có dữ liệu thật chỉ để khắc phục sự cố. Nếu buộc chẩn đoán tầng giao vận, chỉ dùng môi trường cách ly với dữ liệu giả, thời hạn rất ngắn, người phê duyệt và kiểm soát quyền truy cập.

**HTTP access log của Reactor Netty, proxy và gateway:** Đây là các nguồn log riêng; chúng có thể ghi request target gồm query string trước khi WebFilter xử lý. Phải kiểm tra format/thành phần và chính sách redaction ở chính từng lớp. Bộ lọc WebFlux an toàn không tự động làm sạch log do Netty hoặc reverse proxy xuất ra.

## 9. Cấu hình mức log có kiểm soát

Ví dụ cấu hình nền cho application.yml:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: INFO
    org.springframework.web: INFO
    reactor.netty: INFO
~~~

Mục đích là tránh bật DEBUG/TRACE rộng rãi cho các package liên quan đến HTTP và security tại môi trường có dữ liệu thật. Các mức này **không phải cơ chế che dữ liệu**: một lệnh log.info sai vẫn rò rỉ; một logger khác hoặc cấu hình access log/wiretap riêng vẫn có thể xuất dữ liệu. Hãy kiểm tra cấu hình hiệu lực của mọi profile triển khai, thư viện giao tiếp, gateway, sidecar, agent APM và log collector.

Nếu hệ thống dùng JSON log/structured logging, chỉ serialize DTO/schema các trường đã được duyệt. Filter masking ở encoder, collector hoặc SIEM có thể bổ sung để bắt lỗi sơ suất, nhưng không đảm bảo loại mọi biến thể của secrets, encoded strings, multiline payload hoặc log tạo từ thư viện thứ ba.

## 10. Reactor Context, MDC và tracing

Reactive pipeline có thể đổi thread qua publishOn, subscribeOn hoặc khi xử lý I/O; một ThreadLocal/MDC gán ở thread nhận request không mặc nhiên có mặt trong mọi callback. Đừng coi việc MDC “không xuất hiện” là lý do để copy Authentication, bearer token hay thông tin cá nhân vào MDC.

- Truyền **chỉ metadata an toàn** (request ID, trace ID đã kiểm soát, tên operation) bằng Reactor Context. Nếu cần đưa vào MDC, dùng cơ chế context propagation tương thích với phiên bản Reactor/Micrometer đang sử dụng và luôn dọn đúng phạm vi.
- Không đưa raw Authorization header, cookie, token, email hoặc body vào Reactor Context, MDC, tracing baggage, span name, span attributes.
- Span name nên là tên operation hoặc mẫu route, chẳng hạn HTTP GET /orders/{id}; không dùng raw URL có query hoặc path chứa định danh.
- Tránh metric labels chứa user ID, email, token hoặc giá trị tự do từ request: vừa nhạy cảm vừa gây cardinality cao. Dùng method, route template, status và error class ở danh mục cố định.
- Kiểm tra các công cụ auto-instrumentation: agent có thể tự ghi HTTP URL, request headers, query params hoặc exception message; áp dụng allowlist/redaction ở cấu hình agent và backend, không chỉ ở mã nguồn.

Request ID phục vụ tương quan không được sử dụng như một bí mật xác thực. Nếu nhận X-Request-ID từ client, coi đó là input không tin cậy: chỉ chấp nhận độ dài/bảng ký tự hạn chế, ngăn chèn newline, hoặc tự sinh ID. Không dùng giá trị header do client gửi nguyên văn làm log field.

## 11. Nếu bắt buộc quan sát payload nghiệp vụ

Một số luồng cần bằng chứng cho trạng thái giao dịch hoặc bước xử lý. Hãy ghi **biến cố nghiệp vụ đã trích trường an toàn** thay vì request/response JSON: event=payment_confirmed, result=declined, provider_code từ allowlist; tuyệt đối không lưu số thẻ, CVV, access token, mật khẩu hay nội dung tự do.

Quy trình chọn field:
1. Viết rõ câu hỏi vận hành cần trả lời; chỉ chọn trường trả lời câu hỏi đó.
2. Xác định nguồn nào do người dùng/đối tác kiểm soát và có thể chứa bí mật ngay cả trong error message.
3. Chọn kiểu giá trị giới hạn (enum, boolean, trạng thái, số đo). Với string tự do, mặc định loại bỏ.
4. Kiểm tra tác động đến dữ liệu cá nhân, quyền đọc, retention, export và sao lưu.
5. Kiểm thử cả trường hợp lỗi, retry, timeout, cancel và response bất thường.
6. Xem xét lại mỗi khi endpoint, DTO, SDK hoặc instrumentation thay đổi.

Mã hóa dữ liệu nhạy cảm để lưu tập trung có thể là một biện pháp bảo vệ lưu trữ, nhưng không làm cho việc ghi bí mật vào log trở thành cần thiết hay an toàn. Bí mật một khi đã bị sao chép qua hệ thống quan sát sẽ rất khó xóa đồng bộ.

## 12. Kiểm thử rò rỉ với sentinel và readback log

Đừng chỉ review code; hãy kiểm tra **đầu ra thật** của logger, access log gateway, tracing và collector ở môi trường thử nghiệm.

**Bộ tình huống tối thiểu:**

| Tình huống thử | Dữ liệu thử cố ý đưa vào | Kỳ vọng |
| --- | --- | --- |
| Đăng nhập sai | password=PASSWORD_SENTINEL_731 | Không có sentinel trong log, trace, error message hoặc response ngoài ý muốn. |
| Bearer không hợp lệ | Authorization: Bearer TOKEN_SENTINEL_742 | Chỉ còn event/mã lỗi chuẩn hóa; không có token hay một phần token. |
| Session cookie | Cookie: SESSION=COOKIE_SENTINEL_753 | Không có cookie value trong log ứng dụng, proxy hoặc Netty. |
| URL có query nhạy cảm | /reset?token=QUERY_SENTINEL_764 | Log HTTP dùng mẫu route, không dùng URL/query thật. |
| Payload có PII | email=PII_SENTINEL_775 | Không có email/raw body trong bất kỳ log sink nào. |
| Lỗi downstream | response body chứa ERROR_SENTINEL_786 | Không log raw body hoặc exception message chứa sentinel. |

Các sentinel trên là chuỗi thử nghiệm không phải credential thật. Dùng cả chuỗi có dấu cách, dấu xuống dòng và biến thể URL-encoded nếu lớp log có xử lý/biến đổi dữ liệu. Thử cho GET/POST, 2xx/4xx/5xx, lỗi trước khi route được match, timeout, retry và cancel. Thu log tại các nguồn thực tế, tìm cả giá trị nguyên dạng và biểu diễn đã mã hóa; xác minh field allowlist vẫn có đủ method, route, status, duration và request ID để vận hành.

Với Spring Boot có thể dùng WebTestClient để bắn request và OutputCaptureExtension (spring-boot-test) để bắt output trong integration test; kết quả sẽ phụ thuộc app, endpoint và appender. **Cần assert không chứa sentinel**, đồng thời assert có event tương ứng. Một unit test của hàm che chuỗi đơn lẻ không thể chứng minh gateway, Netty hay APM không làm rò dữ liệu.

Kiểm thử bảo vệ phải được chạy lại khi nâng cấp Spring Security, Reactor Netty, đổi mức log hoặc thêm filter/instrumentation mới. Trong môi trường phát triển dùng secret giả; không lấy password hay token thật để chứng minh một chức năng logging.

## 13. Vận hành, lưu trữ và xử lý khi phát hiện leak

- Áp dụng nguyên tắc ít quyền nhất cho người xem dashboard, truy vấn log, export, bản lưu trữ và support attachment; ghi audit việc truy cập dữ liệu nhạy cảm nếu hệ thống có khả năng.
- Đặt retention theo nhu cầu điều tra thực tế; kiểm soát sao lưu và các pipeline copy dữ liệu sang bên thứ ba. Redaction ở viewer không đủ vì dữ liệu gốc có thể còn trong chỉ mục/storage.
- Nếu phát hiện token/cookie đã xuất hiện trong log: ngăn nguồn ghi tiếp, vô hiệu hóa hoặc thu hồi token/session có thể bị lộ, rotate credentials liên quan, đánh giá phạm vi dữ liệu và các bản sao, phối hợp quy trình ứng phó sự cố, dọn/xóa theo chính sách áp dụng. Không paste bí mật vào ticket hay log khác khi báo lỗi.
- Với dữ liệu cá nhân đã rò, xử lý theo chính sách bảo mật, thỏa thuận xử lý dữ liệu và nghĩa vụ pháp lý áp dụng. Không mặc định rằng chỉ che trên dashboard là đã khắc phục.

## 14. Lỗi phổ biến và checklist tự kiểm tra

**Sai lầm thường gặp:**
- Chỉ che từ khóa password mà quên Authorization, Cookie, X-Api-Key, refresh_token, custom headers hoặc các phiên bản viết hoa/thường khác nhau.
- Ghi toàn bộ ServerWebExchange, HttpHeaders, request URI, Authentication hoặc Jwt bằng toString() vì tưởng chỉ chứa metadata.
- Dùng raw URL để phân nhóm log/trace/metric thay vì route template.
- Tin rằng cấu hình INFO, HttpOnly cookie, TLS hoặc mã hóa ổ đĩa tự động bảo đảm log không rò dữ liệu.
- Chỉ kiểm tra log controller mà quên WebClient, proxy, Netty, agent APM và xử lý exception.
- Dùng hash không khóa của email làm “ẩn danh” hoặc chèn user ID vào metric labels, khiến dễ liên kết/đoán hoặc bùng nổ cardinality.
- Bật wiretap, access log chi tiết hoặc DEBUG/TRACE ở production rồi quên tắt.

**Checklist trước khi phát hành:**
- [ ] Schema log chủ yếu là event/method/route-template/status/duration/request_id và mã lỗi allowlist.
- [ ] Không có request/response body, toàn bộ headers/cookies, raw URI, password, token, claims, credentials, PII trong log.
- [ ] Spring Security/WebFlux/WebClient/Reactor Netty/gateway/agent observability đều đã được kiểm tra riêng.
- [ ] Error logging không tự động phát ra exception message chứa input.
- [ ] Reactor Context, MDC, trace baggage và metric attributes chỉ mang metadata an toàn.
- [ ] Kiểm thử sentinel qua cả luồng thành công và lỗi, trong tất cả các log sink liên quan, đều đạt.
- [ ] Đã giới hạn quyền truy cập, thời hạn lưu và đường export log; có quy trình thu hồi credential khi rò rỉ.

**Ghi nhớ:** Trong ứng dụng Spring Security Reactive, bảo vệ log bắt đầu từ việc **không đưa bí mật vào sự kiện log**. Một sự kiện HTTP hữu ích vẫn có thể cho biết điều gì xảy ra, ở route nào, lúc nào, mất bao lâu và tương quan với request nào mà không cần biết password, Authorization header, cookie hay thông tin cá nhân của người dùng.
