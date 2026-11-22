# Ẩn token, secret, authorization code và dữ liệu cá nhân trong log

Authorization Server xử lý nhiều giá trị có thể cấp quyền truy cập hoặc tiết lộ danh tính người dùng. Một dòng log tưởng như vô hại có thể chứa access token, refresh token, authorization code, client secret, cookie phiên hoặc claim trong ID token. Khi log được chuyển sang hệ thống tập trung, APM, dịch vụ phân tích hay bản sao lưu, những giá trị đó có thể tồn tại lâu hơn vòng đời của request và được nhiều người truy cập hơn dữ liệu nghiệp vụ ban đầu.

Trong Spring Authorization Server, việc ghi log cần được thiết kế cùng với các luồng authorization code, PKCE, refresh token, introspection, revocation và OpenID Connect. Mục tiêu là giữ đủ thông tin để vận hành, điều tra lỗi và kiểm toán, đồng thời bảo đảm log không trở thành một bản sao của thông tin xác thực hoặc dữ liệu cá nhân.

## 1. Nhận diện dữ liệu không được ghi vào log

Hãy xem mọi dữ liệu đi qua endpoint OAuth 2.0/OIDC là dữ liệu có thể nhạy cảm cho đến khi được phân loại rõ ràng. Những trường sau không được ghi nguyên giá trị:

| Dữ liệu | Vị trí thường xuất hiện | Cách xử lý |
|---|---|---|
| Access token, refresh token, ID token và device code | Response của token endpoint; request introspection, revocation hoặc userinfo | Không ghi giá trị, kể cả một phần token. Dùng request ID hoặc mã tham chiếu nội bộ nếu cần đối chiếu |
| Authorization code | Query của redirect URI sau authorization endpoint; request gửi đến token endpoint | Không ghi query string, request body hoặc code |
| Client secret và client assertion | Form body, HTTP Basic Authorization hoặc JWT assertion trong client authentication | Không ghi header Authorization, assertion hoặc secret |
| PKCE code_verifier | Form body của token request | Không ghi body của token endpoint |
| State, nonce và device user_code | Authorization request, callback hoặc device authorization flow | Không ghi giá trị; chỉ ghi kết quả kiểm tra và mã sự kiện |
| Cookie, session ID và CSRF token | Cookie, Set-Cookie hoặc header liên quan đến phiên | Loại bỏ khỏi access log, application log và trace |
| Thông tin cá nhân | Principal, Authentication, ID token claims, userinfo và dữ liệu hồ sơ | Không ghi mặc định; nếu có nhu cầu kiểm toán, dùng mã tham chiếu giả danh đã được phê duyệt |
| Khóa ký và khóa riêng | JWK private members, keystore, biến môi trường hoặc cấu hình triển khai | Không ghi nội dung khóa, mật khẩu keystore hoặc giá trị secret từ cấu hình |

Các trường trong JWT cũng cần được bảo vệ. Không log toàn bộ JWT để xem sub, email, name, phone_number, address hay các claim khác. Việc token được ký hoặc mã hóa không làm cho nội dung của nó trở thành dữ liệu phù hợp để ghi log.

Không nên ghi toàn bộ đối tượng HttpServletRequest, Authentication, OAuth2Authorization, OAuth2Token, principal, claims hoặc request/response DTO. Những đối tượng này có thể chứa thông tin xác thực trong field lồng nhau, toString() hoặc thông tin lỗi. Hãy chọn từng trường an toàn cần ghi thay vì serialize toàn bộ đối tượng.

## 2. Thiết kế log theo allowlist

Một chính sách log an toàn bắt đầu từ allowlist: mỗi sự kiện chỉ phát ra các trường đã được xác định trước. Không dùng denylist làm biện pháp chính, vì một giao thức hoặc phiên bản thư viện mới có thể thêm trường nhạy cảm mà bộ lọc chưa biết.

Một sự kiện OAuth thường chỉ cần những thông tin như:

- Tên sự kiện, thời điểm và kết quả thành công/thất bại.
- Request ID hoặc trace ID do hệ thống sinh.
- Bí danh client đã được cấu hình và phê duyệt để xuất hiện trong log.
- Grant type hoặc loại thao tác, lấy từ tập giá trị đã kiểm soát.
- Số lượng scope hoặc nhóm scope đã được phân loại, nếu thực sự cần.
- Mã lỗi nội bộ đã chuẩn hóa, không phải nội dung exception hay thông điệp chứa dữ liệu request.
- Mã tham chiếu chủ thể đã giả danh nếu yêu cầu kiểm toán cần liên kết nhiều sự kiện của cùng một người dùng.

Ví dụ một audit event an toàn:

~~~json
{
  "event": "oauth.token.issued",
  "timestamp": "2026-11-16T14:25:30Z",
  "request_id": "req-7f2a91",
  "client_alias": "customer-portal",
  "grant_type": "authorization_code",
  "scope_count": 2,
  "outcome": "success"
}
~~~

request_id phải được sinh ở phía server hoặc gateway đáng tin cậy. Không mặc nhiên tin một header do client tự gửi rồi dùng nguyên giá trị đó làm correlation ID. Nếu cần ghi client, ưu tiên bí danh nội bộ; client_id không phải client secret nhưng vẫn có thể tiết lộ cấu trúc tích hợp của hệ thống.

Nếu kiểm toán bắt buộc phải liên kết sự kiện theo người dùng, có thể tạo subject_ref bằng HMAC-SHA-256 với khóa riêng được quản lý trong secret manager. HMAC có khóa giúp tránh việc đối chiếu trực tiếp bằng bảng tra cứu như hash thông thường của email hoặc username. Không dùng giá trị sub, email hay số điện thoại nguyên bản làm khóa tương quan. Giới hạn quyền truy cập khóa HMAC, quy định vòng đời và kế hoạch xoay vòng khóa.

## 3. Ghi log an toàn trong ứng dụng Spring

Tạo một lớp chuyên phát ra audit event. Lớp này nhận các giá trị đã được chọn từ luồng nghiệp vụ và chỉ ghi những trường thuộc schema cho phép. Ví dụ dưới đây dùng SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public final class OAuthAuditLog {

    private static final Logger log =
            LoggerFactory.getLogger(OAuthAuditLog.class);

    public void tokenIssued(
            String serverRequestId,
            String clientAlias,
            String grantType,
            int scopeCount) {

        log.info(
                "oauth.audit event=token_issued requestId={} " +
                        "clientAlias={} grantType={} scopeCount={} outcome=success",
                safeLabel(serverRequestId),
                safeLabel(clientAlias),
                safeGrantType(grantType),
                Math.max(scopeCount, 0)
        );
    }

    private static String safeLabel(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }

        String normalized =
                value.replaceAll("[\\r\\n\\p{Cntrl}]", "_");
        return normalized.substring(0, Math.min(normalized.length(), 64));
    }

    private static String safeGrantType(String value) {
        if (value == null) {
            return "unknown";
        }
        return switch (value) {
            case "authorization_code", "refresh_token", "client_credentials" -> value;
            default -> "other";
        };
    }
}
~~~

serverRequestId cần đến từ bộ tạo request ID đáng tin cậy. clientAlias cần được tra từ cấu hình nội bộ, không lấy trực tiếp một chuỗi tùy ý từ request. grantType nên là giá trị đã được kiểm soát. Hàm safeLabel giới hạn độ dài và loại ký tự điều khiển để giảm nguy cơ log injection; nó không thay thế việc phân loại dữ liệu. Nếu một giá trị không thuộc allowlist thì không đưa giá trị đó vào log.

Khi xử lý token trong Spring Authorization Server, hãy tránh các cách ghi log như:

~~~java
// Không an toàn: đối tượng có thể chứa token, principal hoặc thông tin xác thực.
log.debug("authorization={}", authorization);
log.debug("authentication={}", authentication);
log.debug("token response={}", tokenResponse);

// Không an toàn: header và body có thể chứa bearer token, code hoặc secret.
log.debug("authorizationHeader={}", request.getHeader("Authorization"));
log.debug("requestBody={}", requestBody);
~~~

Thay vào đó, ghi một sự kiện đã chuẩn hóa, ví dụ token_issued, token_refresh_failed, authorization_denied hoặc token_revoked, cùng request ID, bí danh client, grant type và mã kết quả. Với lỗi, ưu tiên mã lỗi nội bộ như invalid_grant hoặc client_authentication_failed. Không nối exception.getMessage() vào log nếu thông điệp có thể chứa URL, tham số, token hoặc dữ liệu người dùng. Stack trace cũng cần được kiểm soát vì message của exception và giá trị trong object có thể xuất hiện trong đó.

Không bật DEBUG hoặc TRACE rộng cho org.springframework.security, Spring Authorization Server hay các filter xử lý OAuth trên môi trường production nếu chưa kiểm tra nội dung log thực tế. Khi cần chẩn đoán, chỉ bật trong thời gian ngắn, giới hạn người truy cập và xác minh trước rằng cấu hình không ghi credential hoặc payload.

## 4. Bảo vệ request log, access log và trace

Chỉ cấu hình application logger là chưa đủ. Authorization code có thể xuất hiện trong URL callback; client secret, code verifier và refresh token có thể nằm trong body; bearer token và cookie có thể nằm trong header. Các lớp proxy, web server, tracing agent và APM đều có thể ghi lại request trước khi ứng dụng xử lý.

**Ở application layer:** Với endpoint /oauth2/authorize, /oauth2/token, /oauth2/introspect, /oauth2/revoke, device authorization và OIDC userinfo, chỉ ghi method, path đã chuẩn hóa, status, thời gian xử lý và request ID. Không ghi query string, header Authorization, Cookie, Set-Cookie hoặc body. Nếu dùng CommonsRequestLoggingFilter, không bật includePayload, includeHeaders hay includeQueryString cho các endpoint này.

**Ở reverse proxy:** Tránh log biến chứa toàn bộ request line hoặc query string. Với Nginx, có thể định nghĩa access log chỉ dùng URI path và metadata vận hành:

~~~nginx
log_format oauth_safe
    '$request_method $uri $status $body_bytes_sent $request_time';

access_log /var/log/nginx/oauth_access.log oauth_safe;
~~~

$uri không chứa query arguments. Tránh đưa $request, $request_uri, $args, $http_authorization, $http_cookie hoặc $http_referer vào format này. Nếu cần ghi địa chỉ IP để chống lạm dụng hoặc điều tra sự cố, hãy đánh giá đó là dữ liệu cá nhân, giới hạn quyền truy cập và thời gian lưu giữ theo chính sách của tổ chức.

**Ở tracing và APM:** Chỉ thêm thuộc tính đã được duyệt như route template, HTTP status, grant type, outcome và trace ID. Không gắn request/response body, token, claims, cookie hoặc toàn bộ URL có query vào span. Kiểm tra cả auto-instrumentation vì agent có thể tự thu thập header hoặc payload.

**Ở MDC:** Chỉ đặt request ID, trace ID và các nhãn an toàn. Không đặt token, username, email, session ID hay nội dung request vào MDC. Xóa các giá trị được thêm vào trong finally để tránh dữ liệu của request trước rò sang request tiếp theo khi thread được tái sử dụng:

~~~java
MDC.put("requestId", serverRequestId);
try {
    // Xử lý nghiệp vụ và ghi audit event an toàn.
} finally {
    MDC.remove("requestId");
}
~~~

Nếu dùng Tomcat access log, tránh pattern ghi nguyên request line như %r khi request có thể chứa query nhạy cảm; chỉ ghi path và các trường vận hành đã được duyệt. Cấu hình phải được kiểm tra ở đúng phiên bản server đang chạy.

## 5. Phân biệt audit log và diagnostic log

Audit log trả lời các câu hỏi: ai hoặc client nào thực hiện loại thao tác nào, vào thời điểm nào, kết quả ra sao và sự kiện thuộc request nào. Diagnostic log hỗ trợ tìm lỗi kỹ thuật như timeout, lỗi kết nối database hoặc lỗi ký token. Hai loại log có mục đích, người đọc và thời hạn lưu giữ khác nhau, nhưng đều phải tuân thủ nguyên tắc không chứa credential.

Với Authorization Server, các sự kiện kiểm toán hữu ích gồm cấp token, refresh token, thu hồi token, introspection, consent được chấp thuận hoặc từ chối, đăng nhập thất bại và thay đổi cấu hình client. Mỗi sự kiện chỉ nên ghi metadata tối thiểu. Chẳng hạn, ghi scope_count hoặc nhóm scope đã phân loại thay vì toàn bộ danh sách scope nếu tên scope có thể tiết lộ quyền truy cập nhạy cảm.

Đặt log tập trung trong hệ thống có phân quyền theo vai trò, mã hóa khi truyền và khi lưu, theo dõi truy cập, thời hạn lưu giữ rõ ràng và quy trình xóa theo chính sách. Audit log cần có biện pháp phát hiện sửa đổi hoặc xóa trái phép. Không cấp quyền đọc log OAuth rộng như quyền đọc log ứng dụng thông thường.

## 6. Kiểm thử để phát hiện rò rỉ

Kiểm thử phải chứng minh rằng giá trị nhạy cảm không xuất hiện trong log sau khi đi qua từng luồng. Dùng dữ liệu giả lập có dấu hiệu dễ nhận biết, ví dụ test-access-token-DO-NOT-LOG, test-refresh-token-DO-NOT-LOG, test-client-secret-DO-NOT-LOG và email giả. Không dùng token hoặc secret đang hoạt động làm dữ liệu kiểm thử.

Một assertion cơ bản trên log đã thu thập:

~~~java
assertThat(capturedLog)
        .doesNotContain(
                accessToken,
                refreshToken,
                authorizationCode,
                clientSecret,
                codeVerifier,
                testEmail
        );
~~~

Chạy kiểm thử qua authorization code với PKCE, đổi code lấy token, refresh token, revocation, introspection, client authentication và userinfo. Kiểm tra cả log ứng dụng, access log của proxy/web server, trace/APM và hệ thống thu thập exception. Một bài test chỉ kiểm tra logger trong ứng dụng không phát hiện được việc gateway hoặc agent ghi nguyên URL và header.

Ngoài kiểm tra chuỗi nhạy cảm, xác nhận log vẫn có các trường vận hành cần thiết như event name, request ID, route, status, duration và outcome. Như vậy nhóm vận hành vẫn truy vết được sự kiện mà không cần đọc credential.

## 7. Xử lý khi phát hiện secret đã lọt vào log

Hãy coi token hoặc secret xuất hiện trong log là dữ liệu đã bị lộ. Xác định loại credential, khoảng thời gian, hệ thống log nhận dữ liệu, người hoặc dịch vụ đã truy cập và các bản sao đã được tạo. Thu hồi token còn hiệu lực; xoay vòng client secret hoặc khóa bị ảnh hưởng theo quy trình quản lý khóa; đánh giá các phiên và authorization còn liên quan. Với khóa ký, phối hợp kế hoạch rollover và hiệu lực của token đã phát hành để tránh tạo ra khoảng trống xác minh.

Sau khi khống chế, xử lý các bản sao trong log tập trung, APM, export và backup theo chính sách lưu giữ và quy trình ứng phó sự cố. Ghi lại phạm vi ảnh hưởng bằng metadata an toàn, sửa cấu hình tại nguồn rồi chạy lại kiểm thử canary để xác nhận dữ liệu không còn xuất hiện. Chỉ xóa một dòng ở application log không giải quyết được các bản sao đã được chuyển sang hệ thống khác.

## 8. Checklist trước khi đưa Authorization Server vào production

- [ ] Không ghi access token, refresh token, ID token, authorization code, device code, client secret, client assertion hoặc PKCE verifier.
- [ ] Không ghi header Authorization, Cookie, Set-Cookie, request body, response body hoặc query string của endpoint OAuth/OIDC.
- [ ] Không serialize Authentication, principal, OAuth2Authorization, token object hoặc claims vào log.
- [ ] Audit event dùng schema allowlist, request ID đáng tin cậy và mã lỗi đã chuẩn hóa.
- [ ] Client identifier và subject reference được xử lý theo chính sách phân loại dữ liệu.
- [ ] Proxy, web server, tracing agent, APM và exception reporter đã được kiểm tra riêng.
- [ ] MDC chỉ chứa metadata an toàn và được dọn sau mỗi request.
- [ ] Kiểm thử bằng secret giả xác nhận các giá trị nhạy cảm không xuất hiện ở mọi log sink.
- [ ] Log tập trung có phân quyền, mã hóa, theo dõi truy cập và thời hạn lưu giữ phù hợp.

Khi các kiểm soát này được áp dụng đồng nhất, log của Spring Authorization Server vẫn hỗ trợ giám sát vòng đời token, điều tra lỗi và kiểm toán các luồng OAuth 2.0/OIDC mà không lưu lại những giá trị có thể dùng để chiếm quyền hoặc nhận diện người dùng.
