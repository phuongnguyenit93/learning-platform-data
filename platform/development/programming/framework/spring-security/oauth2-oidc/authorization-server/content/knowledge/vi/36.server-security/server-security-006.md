# Chống brute force, credential stuffing và enumeration

> **Chương: Bảo vệ máy chủ.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Mục tiêu là bảo vệ luồng xác thực người dùng, client và các endpoint khôi phục tài khoản trước tấn công đoán mật khẩu, tái sử dụng credential bị rò rỉ, password spraying và dò tìm tài khoản.

## 1. Phân biệt các kiểu tấn công đăng nhập

Các cuộc tấn công tự động có thể dùng cùng một login endpoint nhưng có cách phân phối request khác nhau. Nếu chỉ giới hạn số lần thử theo IP, attacker có thể đổi proxy; nếu chỉ đếm theo username, attacker có thể khóa tài khoản của nạn nhân.

| Kiểu tấn công | Cách thực hiện | Dấu hiệu thường gặp | Mục tiêu |
|---|---|---|---|
| Brute force | Thử nhiều mật khẩu với một tài khoản | Một account nhận nhiều lần đăng nhập thất bại | Đoán được password |
| Password spraying | Thử một vài mật khẩu phổ biến trên nhiều account | Một nguồn hoặc cụm nguồn thử cùng pattern trên nhiều username | Tránh ngưỡng khóa từng account |
| Credential stuffing | Thử cặp username/password lấy từ breach khác | Nhiều cặp credential, nhiều account, IP/device phân tán | Tận dụng password reuse |
| Account enumeration | Dò account tồn tại qua message, status, timing hoặc flow khác nhau | Request khác biệt khi username tồn tại/không tồn tại | Thu thập danh sách tài khoản hợp lệ |
| MFA/OTP guessing | Thử mã OTP hoặc recovery code | Nhiều lần nhập sai cho một authenticator | Vượt qua yếu tố thứ hai |
| Client credential guessing | Đoán client secret tại token endpoint | Nhiều lỗi client authentication | Chiếm quyền OAuth client |

Ba kiểu đầu khác nhau về phân phối request nhưng đều có thể làm tăng tải cho Authentication Server. Account enumeration thường là bước chuẩn bị: attacker thu thập danh sách account trước khi chạy password spraying hoặc credential stuffing.

### 1.1. Ví dụ dễ nhận biết

- **Brute force:** 500 password khác nhau được thử vào alice@example.vn.
- **Password spraying:** password Spring2026! được thử một lần trên 500 account.
- **Credential stuffing:** 5.000 cặp username/password từ một vụ rò rỉ được phát lại trên Authorization Server.
- **Enumeration:** endpoint trả User not found khi account không tồn tại nhưng trả Invalid password khi account tồn tại.

Không phải mọi đợt đăng nhập thất bại đều là tấn công. Người dùng có thể gõ sai password, đổi thiết bị hoặc quên tài khoản. Phòng vệ phải giảm tốc độ attacker mà vẫn giữ đường khôi phục hợp lệ cho người dùng thật.

## 2. Vì sao Authorization Server là mục tiêu có giá trị cao?

Authorization Server thường là cổng xác thực dùng chung cho nhiều ứng dụng. Một account bị chiếm có thể mở đường tới nhiều relying party/resource server theo các client, scope và quyền đã được cấp.

Các bề mặt cần bảo vệ:

| Endpoint/flow | Rủi ro |
|---|---|
| Login form / authentication endpoint | Brute force, spraying, credential stuffing |
| Password reset / account recovery | Enumeration, OTP guessing, takeover |
| MFA enrollment / verification | OTP guessing, recovery-code guessing, MFA fatigue |
| OIDC authorization endpoint | Dẫn user vào login flow, tạo nhiều authentication transaction |
| Device verification | Dò user_code, thử chấp thuận thiết bị trái phép |
| Client token endpoint | Đoán client secret, lạm dụng client authentication |
| Client registration / dynamic registration | Tạo client rác, abuse registration và enumeration |
| Admin console | Chiếm tài khoản đặc quyền, thay redirect URI hoặc credential |

Spring Authorization Server xử lý OAuth2/OIDC protocol; xác thực người dùng thường do Spring Security và application login flow thực hiện. Bản thân SAS không tự cung cấp một chính sách rate limit hoàn chỉnh cho login form. Ứng dụng phải tích hợp throttling, anti-automation, MFA, account recovery và monitoring vào đúng endpoint.

### 2.1. Không trộn user authentication với client authentication

alice@example.vn là principal của người dùng. orders-service là OAuth client. Hai loại credential có vòng đời, ngưỡng throttling và quy trình xử lý khác nhau.

- User login: giới hạn theo account identifier, IP, device/session và risk signals.
- Client authentication: giới hạn theo client_id, nguồn request và client authentication method.
- Device authorization: giới hạn riêng việc tạo device code và nhập user code.
- MFA/OTP: giới hạn theo authenticator/account và thời gian sống của mã.

Không tăng bộ đếm password thất bại của user khi một confidential client gửi sai client_secret. Cũng không để lỗi client authentication làm lộ thông tin nội bộ của client registration.

## 3. Threat model và luồng phòng vệ

~~~mermaid
flowchart TD
    A["Login request"] --> B["Edge: WAF / CDN / IP reputation"]
    B --> C["Application: normalize account identifier"]
    C --> D["Check account bucket"]
    C --> E["Check IP / ASN bucket"]
    C --> F["Check device / session / endpoint risk"]
    D --> G{"All limits and risk policy pass?"}
    E --> G
    F --> G
    G -->|No| H["Generic throttle response / challenge"]
    G -->|Yes| I["Spring Security AuthenticationManager"]
    I --> J{"Credentials valid?"}
    J -->|No| K["Record failure + emit security event"]
    J -->|Yes| L["MFA / step-up if required"]
    L --> M["Create authenticated session"]
    K --> N["Generic login failure"]
    M --> O["Audit + success metrics"]
~~~

Các lớp có vai trò khác nhau:

1. **Edge:** chặn burst và nguồn có reputation xấu trước khi request tới ứng dụng.
2. **Application:** áp dụng bucket theo account, IP, endpoint và transaction.
3. **Authentication:** xác minh password/MFA bằng provider phù hợp.
4. **Risk engine:** yêu cầu step-up hoặc challenge khi hành vi bất thường.
5. **Monitoring:** phát hiện pattern phân tán và điều chỉnh policy.

Không có một ngưỡng hoặc CAPTCHA đơn lẻ nào đủ để chống mọi kiểu tấn công. Hãy kết hợp nhiều tín hiệu và đo tác động tới người dùng thật.

## 4. Rate limiting đa chiều

Rate limit nên dùng nhiều bucket độc lập. Mỗi bucket chống một dạng phân phối request khác nhau.

| Bucket | Khóa logic | Chống | Lưu ý |
|---|---|---|---|
| Account | Account identifier đã chuẩn hóa và pseudonymize | Nhiều IP cùng đánh một account | Áp dụng cả khi account không tồn tại |
| IP | IP nguồn đã được resolve qua trusted proxy | Một IP thử nhiều account | Không phải lớp duy nhất vì attacker đổi IP |
| IP + ASN/network | Nguồn mạng hoặc ASN | Nhiều IP trong cùng hạ tầng | Cần dữ liệu reputation đáng tin cậy |
| Device/session | Cookie/session identifier có bảo vệ | Bot đổi username nhưng giữ browser context | Không dùng fingerprint xâm lấn nếu không cần |
| Endpoint | Login, password reset, OTP, device verification | Abuse một flow cụ thể | Ngưỡng khác nhau theo endpoint |
| Client | client_id đã resolve | Đoán client secret hoặc abuse client | Tách khỏi user password bucket |
| Tenant/issuer | Tenant đã được xác minh | Một tenant bị tấn công hoặc gây tải | Không lấy tenant từ query parameter chưa xác minh |
| Global | Toàn hệ thống hoặc cụm dịch vụ | Burst lớn, bảo vệ capacity | Không để một account gây nghẽn toàn cụm |

OWASP Bot Management khuyến nghị ít nhất hai bucket độc lập cho login: per-username và per-IP. Nếu chỉ dùng khóa ghép login:<ip>:<username>, một IP có thể thử ngưỡng riêng trên vô hạn username vì mỗi cặp có bucket mới. Hãy kiểm tra từng bucket riêng và chỉ cho phép tiếp tục khi tất cả đều dưới ngưỡng.

### 4.1. Chuẩn hóa account identifier

Rate limit account bucket phải dùng cùng quy tắc canonicalization với quá trình tìm user:

- Chuẩn hóa khoảng trắng đầu/cuối nếu login contract cho phép.
- Chuẩn hóa Unicode theo policy đã công bố.
- Chuẩn hóa email/username theo quy tắc lookup thực tế; không tự lowercase nếu hệ thống coi identifier là case-sensitive.
- Không dùng password trong rate-limit key.
- Không ghi username/email thô vào Redis key hoặc log nếu có thể tránh.

Có thể tạo khóa pseudonymous bằng HMAC với secret riêng:

~~~text
accountKey = HMAC-SHA-256(rateLimitKey, canonicalAccountIdentifier)
ipKey      = HMAC-SHA-256(rateLimitKey, canonicalSourceIp)
~~~

HMAC key phải được quản lý như secret, có kế hoạch rotation và không dùng chung với signing key/token key. Pseudonymization giảm việc lộ PII trong cache/metrics nhưng không thay thế access control hoặc retention policy.

### 4.2. Thu thập IP sau reverse proxy

request.getRemoteAddr() thường trả địa chỉ của reverse proxy khi ứng dụng đứng sau load balancer. Nếu dùng X-Forwarded-For tùy tiện, attacker có thể tự đặt header để đổi IP bucket.

- Chỉ tin forwarded headers từ proxy/load balancer đã được allowlist.
- Proxy phải strip header do client gửi và ghi lại giá trị chuẩn.
- Chỉ lấy hop theo topology đã cấu hình; không chọn tùy tiện phần tử đầu tiên.
- Nếu không có trusted proxy, dùng remote address của kết nối.
- Kiểm thử IPv4, IPv6, NAT và nhiều proxy hop.

## 5. Chọn thuật toán và chính sách throttling

### 5.1. Token bucket hoặc sliding window

Token bucket cho phép burst nhỏ trong giới hạn và hồi phục dần theo thời gian. Sliding window đếm số lần thử trong cửa sổ thời gian gần nhất. Cả hai phù hợp hơn fixed-window counter đơn giản vì fixed window có thể cho phép burst ở hai phía ranh giới cửa sổ.

Ví dụ minh họa:

| Policy | Cửa sổ | Hành động khi vượt ngưỡng |
|---|---|---|
| Account bucket | 5 lần thất bại trong 10 phút | Progressive delay hoặc step-up |
| IP bucket | 30 lần trong 5 phút | Throttle nguồn trong thời gian ngắn |
| OTP bucket | Theo policy riêng của authenticator | Delay/disable authenticator theo chuẩn áp dụng |
| Password reset | Theo account và IP trong một cửa sổ riêng | Trả response generic và giới hạn gửi email/SMS |
| Client authentication | Theo client và nguồn request | Throttle client/source, cảnh báo vận hành |

Đây chỉ là giá trị khởi đầu để minh họa cách cấu hình. Ngưỡng production cần dựa trên lưu lượng bình thường, loại tài khoản, mức assurance, trải nghiệm người dùng và yêu cầu tuân thủ. Không sao chép các con số này thành một chuẩn chung.

### 5.2. Rate limit phải hoạt động trên nhiều instance

Một ConcurrentHashMap hoặc bộ đếm trong RAM chỉ giới hạn từng JVM. Nếu Authorization Server chạy 5 pod, attacker có thể phân tán request qua các pod và nhận hạn mức gấp nhiều lần.

Production nên dùng store dùng chung như Redis hoặc database counter có atomic update:

- Increment/check phải atomic để request đồng thời không vượt ngưỡng.
- Bucket có TTL và tự hết hạn theo policy.
- Dùng sliding window/token bucket có thời gian nhất quán.
- Có giới hạn memory và chiến lược eviction.
- Khi Redis/cache lỗi, xác định rõ fail-open hay fail-closed theo mức rủi ro; với login abuse protection quan trọng, thường cần circuit breaker và fallback giới hạn ở edge.
- Không để store rate limit trở thành điểm nghẽn hoặc một nguồn DoS mới.

### 5.3. Progressive delay và account lockout

Hard lockout vĩnh viễn rất dễ bị lạm dụng để từ chối dịch vụ: attacker chỉ cần gửi nhiều password sai cho tài khoản nạn nhân. Thay vào đó:

- Tăng delay theo số lần thất bại liên tiếp, có giới hạn tối đa.
- Áp dụng bucket theo account và IP độc lập.
- Có thể yêu cầu CAPTCHA hoặc MFA step-up khi risk tăng.
- Cho người dùng một đường recovery an toàn ngay cả khi login đang bị throttle.
- Chỉ reset account consecutive-failure counter sau khi toàn bộ authentication policy cần thiết đã hoàn tất.
- Thông báo cho người dùng về hoạt động bất thường theo cách không tiết lộ thông tin cho attacker.

NIST SP 800-63B-4 yêu cầu throttling đối với authenticator thuộc phạm vi áp dụng và nêu giới hạn tối đa 100 lần thất bại liên tiếp cho một authenticator trên một subscriber account, trừ khi loại authenticator có yêu cầu riêng. **100 là giới hạn trên, không phải ngưỡng khuyến nghị để mọi ứng dụng đặt mặc định.** Có thể và thường cần đặt ngưỡng thấp hơn theo risk. Các kỹ thuật giảm lockout DoS gồm tăng thời gian chờ và risk-based challenge.

### 5.4. Response khi vượt ngưỡng

Response nên đủ rõ để người dùng biết cần chờ hoặc thử phương thức xác thực khác, nhưng không tiết lộ bucket nào đã kích hoạt:

~~~http
HTTP/1.1 429 Too Many Requests
Cache-Control: no-store
Content-Type: application/json

{
  "error": "temporarily_unavailable",
  "message": "Unable to sign in right now. Please try again later."
}
~~~

Đây là response minh họa cho login application. Với OAuth2 protocol endpoint, phải tuân thủ error response của protocol và tránh tự tạo body không tương thích.

Không trả các thông tin như:

- Account tồn tại nhưng đã bị khóa.
- Bạn còn 2 lần thử.
- IP bucket đã vượt 20 request.
- Thời điểm chính xác account sẽ mở khóa nếu thông tin đó giúp attacker tối ưu lịch thử.

Có thể dùng 429 cho throttling nhưng phải bảo đảm response không trở thành một oracle để enumeration. Áp dụng response generic cho mọi identifier được xử lý trong cùng policy.

## 6. Tích hợp rate limiting với Spring Security

Spring Security chịu trách nhiệm xác thực credential qua AuthenticationManager và AuthenticationProvider. Rate limiter cần kiểm tra trước khi provider thực hiện password verification, rồi ghi nhận kết quả sau khi xác thực.

Một interface nghiệp vụ giúp tách filter khỏi Redis/database implementation:

~~~java
public interface LoginAbuseGuard {

    boolean isThrottled(String accountIdentifier, String sourceIp);

    void recordFailure(String accountIdentifier, String sourceIp);

    void recordSuccess(String accountIdentifier);
}
~~~

Implementation production cần:

- Canonicalize account identifier theo cùng policy với user lookup.
- HMAC account/IP key trước khi lưu.
- Kiểm tra hai bucket độc lập: account và source IP.
- Dùng Redis/Lua hoặc primitive atomic tương đương.
- Đặt TTL và progressive delay.
- Không lưu password hoặc raw credential.
- Chỉ reset account failure counter sau authentication thành công theo policy.

### 6.1. Filter kiểm tra trước UsernamePasswordAuthenticationFilter

Ví dụ filter cho form login tại /login:

~~~java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginRateLimitFilter extends OncePerRequestFilter {

    private final LoginAbuseGuard guard;
    private final ClientIpResolver clientIpResolver;

    public LoginRateLimitFilter(
            LoginAbuseGuard guard,
            ClientIpResolver clientIpResolver) {
        this.guard = guard;
        this.clientIpResolver = clientIpResolver;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
                || !"/login".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String account = request.getParameter("username");
        if (account == null) {
            account = "";
        }

        String sourceIp = clientIpResolver.resolve(request);

        if (guard.isThrottled(account, sourceIp)) {
            response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                    "Unable to sign in. Please try again later.");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

ClientIpResolver là component của ứng dụng, chỉ đọc forwarded headers từ proxy tin cậy. Nếu login processing URL hoặc username parameter đã được đổi trong formLogin, matcher và tên parameter trong filter phải đổi tương ứng. Không dùng filter này cho mọi POST request.

### 6.2. Ghi nhận failure và success

Có thể gắn handler vào form login. Ví dụ rút gọn:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

http
    .addFilterBefore(
            new LoginRateLimitFilter(loginAbuseGuard, clientIpResolver),
            UsernamePasswordAuthenticationFilter.class)
    .formLogin(form -> form
        .failureHandler((request, response, exception) -> {
            loginAbuseGuard.recordFailure(
                    request.getParameter("username"),
                    clientIpResolver.resolve(request));

            response.sendRedirect("/login?error");
        })
        .successHandler((request, response, authentication) -> {
            loginAbuseGuard.recordSuccess(authentication.getName());
            response.sendRedirect("/");
        }));
~~~

Ví dụ giả định form login dùng processing URL /login, parameter username, và redirect phù hợp với ứng dụng. Khi triển khai:

- failureHandler phải trả cùng nội dung/redirect cho sai password, account không tồn tại, disabled hoặc locked.
- Không ghi exception detail vào response.
- successHandler chỉ reset counter sau khi hoàn thành toàn bộ bước xác thực cần thiết, bao gồm MFA nếu policy yêu cầu.
- Nếu dùng custom authentication flow hoặc nhiều filter chain, gắn limiter vào đúng chain xử lý login.
- Với nhiều pod, LoginAbuseGuard phải dùng shared store.

Filter kiểm tra throttling trước password verification. Failure handler tăng counter sau khi AuthenticationManager trả lỗi. Các event của Spring Security có thể hỗ trợ audit/metrics, nhưng không thay thế request-aware handler vì event authentication không tự mang trusted client IP và endpoint context.

### 6.3. Authentication events để monitoring

ProviderManager có thể publish authentication success/failure events khi được cấu hình AuthenticationEventPublisher. Các event hữu ích gồm:

- AuthenticationFailureBadCredentialsEvent
- AuthenticationFailureLockedEvent
- AuthenticationFailureDisabledEvent
- AuthenticationSuccessEvent
- InteractiveAuthenticationSuccessEvent

Dùng event listener để cập nhật metrics, audit và cảnh báo. Không mặc định lấy IP từ event; nếu cần tương quan request, dùng request correlation ID hoặc handler/filter đã xác thực nguồn IP. Không log Authentication object nguyên vẹn nếu nó có thể chứa credential hoặc dữ liệu nhạy cảm.

## 7. Chống account enumeration

Attacker có thể xác định username/email tồn tại thông qua message, status code, redirect, response size, header, thời gian xử lý hoặc số lượng request phụ.

### 7.1. Dùng thông báo generic

Cùng một message nên được trả về khi:

- Username không tồn tại.
- Password sai.
- Account bị khóa hoặc disabled.
- Account chưa xác minh email.
- Login bị từ chối bởi policy nội bộ.

Ví dụ:

~~~text
Không thể đăng nhập. Vui lòng kiểm tra thông tin hoặc thử lại sau.
~~~

Không trả User not found, Password incorrect, Account locked hoặc MFA not enrolled ở public response. Support/admin có thể tra cứu trạng thái qua công cụ nội bộ được phân quyền.

### 7.2. Đồng nhất status, redirect và response shape

Không chỉ sửa text message. Hãy kiểm tra cả:

- HTTP status code.
- Redirect location và query parameters.
- Response body length/JSON structure.
- Header như Retry-After, X-Account-State.
- Số lần gọi database, email hoặc external provider.
- Thời gian xử lý có chênh lệch đủ để thống kê hay không.

Ví dụ password recovery nên luôn trả thông báo tương tự:

~~~text
Nếu thông tin phù hợp với tài khoản, chúng tôi sẽ gửi hướng dẫn tiếp theo.
~~~

Không cho biết email có tồn tại hay không. Gửi email qua queue bất đồng bộ và giới hạn theo account/IP để tránh endpoint recovery trở thành công cụ spam.

### 7.3. Giảm timing discrepancy

Nếu account không tồn tại, ứng dụng có thể kết thúc sớm trước khi thực hiện password hash comparison; nếu account tồn tại, password encoder có thể tốn nhiều thời gian. Attacker đo thời gian nhiều lần có thể phân biệt hai trường hợp.

Các biện pháp:

- Dùng dummy encoded password và thực hiện một lần PasswordEncoder.matches(...) khi account không tồn tại.
- Không trả response sớm chỉ dựa vào kết quả user lookup.
- Dùng cùng response path cho các loại credential failure.
- Tránh gọi external service chỉ trong nhánh account tồn tại.
- Đo phân phối latency trong test/load test; không cố tạo delay cố định quá lớn gây DoS.

Spring Security DaoAuthenticationProvider có cơ chế xử lý user-not-found nhằm giảm timing leak trong flow chuẩn; nếu thay bằng custom AuthenticationProvider, phải tự giữ tính chất tương đương. Không bỏ qua dummy hash vì thông báo đã được làm generic.

### 7.4. Enumeration ở các flow ngoài login

| Flow | Response cần thống nhất |
|---|---|
| Password reset | Nếu account tồn tại, hướng dẫn sẽ được gửi |
| Account recovery | Không xác nhận identifier có tồn tại |
| Registration | Không tiết lộ email đã đăng ký nếu policy yêu cầu privacy |
| MFA enrollment/recovery | Không tiết lộ user đã bật loại authenticator nào trước khi xác thực |
| Device verification | Không tiết lộ device/user code hợp lệ qua thông báo chi tiết |
| Client lookup/admin | Chỉ hiển thị chi tiết cho admin đã được authorize |

Enumeration protection không có nghĩa che giấu mọi thông tin trong mọi tình huống. Sau khi user đã xác thực đủ assurance hoặc admin có quyền, UI có thể hiển thị trạng thái cụ thể phù hợp nghiệp vụ.

## 8. Chống credential stuffing và password spraying

Credential stuffing dùng credential có thể hoàn toàn đúng. Password encoder mạnh và rate limit vẫn có thể không ngăn được một login thành công nếu attacker dùng cặp username/password hợp lệ bị rò rỉ.

### 8.1. MFA và phishing-resistant authentication

MFA là lớp phòng vệ quan trọng trước credential reuse. Ưu tiên authenticator chống phishing như WebAuthn/passkeys khi nền tảng hỗ trợ; với hệ thống hiện hữu có thể dùng TOTP hoặc phương thức phù hợp threat model.

Có thể yêu cầu step-up khi:

- Đăng nhập từ browser/device mới.
- IP/ASN có reputation xấu hoặc có nhiều account bị thử.
- Địa lý hoặc thời điểm bất thường so với hành vi đã biết.
- Có dấu hiệu bot/headless automation.
- User vừa đổi password hoặc recovery factor.
- Truy cập chức năng quản trị hoặc giao dịch rủi ro cao.

Không xem SMS OTP là lớp phòng vệ duy nhất cho tài khoản có giá trị cao. MFA fatigue/push bombing cũng cần kiểm soát bằng number matching, rate limit và thông báo context rõ ràng.

### 8.2. Kiểm tra password bị lộ

Trong quá trình đăng ký hoặc đổi password:

- Chặn password phổ biến, dễ đoán hoặc đã xuất hiện trong breach corpus theo policy.
- Dùng danh sách local hoặc dịch vụ có cơ chế k-anonymity; không gửi password plaintext tới bên thứ ba.
- Nếu kiểm tra password bị lộ khi login, chỉ dùng kết quả như risk signal để yêu cầu step-up/cảnh báo hoặc quy trình đổi password sau khi xác thực; không tạo một response khác biệt có thể dùng để dò account.
- Thông báo người dùng khi phát hiện credential có khả năng bị compromise.

Không bắt người dùng đổi password định kỳ nếu không có bằng chứng compromise hoặc yêu cầu policy. Khuyến khích password manager và cho phép paste/autofill.

### 8.3. IP reputation và device signals

Có thể dùng:

- IP reputation, ASN, proxy/VPN/Tor signal theo policy.
- Số lượng account khác nhau được thử từ một IP/subnet.
- Số lượng IP khác nhau thử cùng một account.
- TLS/HTTP connection fingerprint ở edge khi có cơ sở hợp pháp.
- Device/session identifier đã pseudonymize.
- Tần suất, khoảng thời gian và pattern request.
- Browser automation/headless signal.

Fingerprinting có thể ảnh hưởng privacy và accessibility. Ưu tiên passive/network signal trước, thu thập ít nhất có thể và có retention rõ ràng.

### 8.4. CAPTCHA và challenge thích ứng

CAPTCHA có thể làm automation đắt hơn nhưng không phải biện pháp chống bot tuyệt đối. Attacker có thể dùng solver farm, mô hình tự động hoặc dịch vụ thuê người giải.

Cách dùng hợp lý:

- Chỉ yêu cầu khi risk score tăng hoặc sau một số lần thất bại.
- Kết hợp với rate limit, MFA và IP/device signals.
- Không dùng CAPTCHA thay password/MFA.
- Cung cấp phương án accessibility và không khóa người dùng thật chỉ vì CAPTCHA provider gặp sự cố.
- Theo dõi solve rate và false-positive rate.

## 9. Bảo vệ các flow liên quan trong Authorization Server

### 9.1. Password reset và account recovery

- Rate limit theo account identifier và IP độc lập.
- Response generic cho account tồn tại/không tồn tại.
- Reset token/code đủ entropy, one-time-use và có TTL ngắn.
- Lưu reset token dạng hash nếu có thể.
- Không gửi reset link/code qua channel chưa được xác minh.
- Sau reset, cân nhắc revoke session/refresh token và thông báo user.
- Không cho reset flow trở thành đường vòng vượt account lockout hoặc MFA policy.

### 9.2. MFA/OTP và recovery code

Mỗi authenticator cần counter riêng theo account/authenticator, cùng IP/device risk signals. OTP có thời hạn ngắn nhưng attacker có thể thử nhiều mã trong cửa sổ đó; cần giới hạn số lần thử, chống replay và chỉ chấp nhận mã một lần.

Recovery code phải có entropy đủ, được lưu dạng hash và chỉ dùng một lần. Không log OTP/recovery code. NIST SP 800-63B-4 cũng yêu cầu throttling cho các authenticator thuộc phạm vi áp dụng, bao gồm recovery codes và OTP có output entropy thấp.

### 9.3. Device Authorization Flow

Device Authorization Grant có hai loại request:

- Client gọi device authorization endpoint để xin device_code và user_code.
- Người dùng nhập user_code tại verification endpoint để xác thực và chấp thuận.

Cần:

- Rate limit việc tạo device code theo client/IP.
- Rate limit việc nhập user code theo IP/session.
- User code đủ entropy theo thiết kế protocol, có TTL và giới hạn lần thử.
- Không tiết lộ user code hợp lệ/không hợp lệ bằng response khác biệt.
- Hiển thị client name và requested scopes trước khi user approve.
- Yêu cầu authentication và consent rõ ràng; không auto-approve chỉ vì code hợp lệ.
- Có audit cho approve, deny, expiry và brute-force signal.

### 9.4. Client authentication ở token endpoint

Confidential client có thể bị thử client_secret tại /oauth2/token, /oauth2/introspect hoặc /oauth2/revoke. Hãy áp dụng policy riêng theo client_id, IP/ASN, client authentication method và endpoint.

- Không dùng user account lockout counter cho lỗi client secret.
- Không trả thông tin nội bộ như client tồn tại, secret hash hoặc credential state.
- Ưu tiên private_key_jwt hoặc mTLS cho client phù hợp thay cho shared secret dài hạn.
- Theo dõi nhiều lần lỗi từ một client/source và cảnh báo chủ sở hữu.
- Không vô hiệu hóa hàng loạt client hợp lệ chỉ vì một nguồn gửi sai credential; dùng throttling và quy trình rotation có kiểm soát.

## 10. Observability, audit và phản ứng sự cố

Log/metrics cần trả lời được: ai bị nhắm tới, nguồn nào phát request, pattern nào đang xảy ra, policy nào đã kích hoạt và user hợp lệ có bị ảnh hưởng hay không.

### 10.1. Trường log nên có

| Trường | Ví dụ | Lưu ý |
|---|---|---|
| Event type | LOGIN_FAILURE | Phân biệt user/client/MFA/recovery |
| Account fingerprint | HMAC identifier | Không ghi username/email thô |
| Source IP | IP đã resolve | Tuân thủ privacy/retention |
| Tenant/issuer | Tenant đã xác minh | Không lấy từ query chưa tin cậy |
| Client ID | employee-portal | Client đã resolve trong registry |
| Device/session ID | Pseudonymous ID | Không log raw session cookie |
| Risk decision | STEP_UP_REQUIRED | Ghi policy code nội bộ |
| Rate bucket | ACCOUNT, IP, OTP | Không trả bucket cho public response |
| Correlation ID | Request trace ID | Dùng điều tra liên dịch vụ |
| Outcome | THROTTLED, FAILED, SUCCESS | Không chứa password/token |

Không ghi password, password hash, OTP, recovery code, authorization code, access token, refresh token hoặc client secret. Tránh dùng username/IP làm metric label có cardinality rất lớn; dùng aggregate counters, histogram và log/trace có kiểm soát.

### 10.2. Pattern cần cảnh báo

- Một account bị thử từ nhiều IP/ASN trong thời gian ngắn.
- Một IP thử nhiều account với số lần thấp trên mỗi account.
- Nhiều account nhận cùng pattern lỗi từ một cụm nguồn.
- Nhiều login thành công ngay sau một đợt credential failures.
- Tỷ lệ password reset/MFA recovery tăng đột biến.
- Nhiều client_id bị lỗi client authentication từ cùng nguồn.
- Device verification có nhiều user_code sai.
- Throttle false-positive tăng mạnh sau thay đổi policy.

### 10.3. Phản ứng khi nghi ngờ credential compromise

1. Xác định account/client, tenant, issuer và khoảng thời gian bị ảnh hưởng.
2. Tăng risk controls hoặc yêu cầu step-up cho nhóm bị nhắm tới.
3. Thông báo người dùng qua channel đã xác minh; không gửi thông tin nhạy cảm qua email không tin cậy.
4. Buộc đổi password khi có bằng chứng compromise; revoke session/refresh token theo policy.
5. Kiểm tra authorization/token issuance và hoạt động sau login đáng ngờ.
6. Rotation client secret hoặc chuyển sang phương thức xác thực mạnh hơn nếu client credential bị lộ.
7. Bảo toàn audit evidence và cập nhật detection rules sau incident.

## 11. Ma trận kiểm thử chống brute force, stuffing và enumeration

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Một account nhận nhiều password sai từ cùng IP | Account bucket tăng và kích hoạt delay/throttle |
| 2 | Một account bị thử từ nhiều IP | Account bucket vẫn giới hạn được distributed brute force |
| 3 | Một IP thử nhiều account | IP bucket giới hạn tổng volume |
| 4 | Attacker thay username liên tục trên cùng IP | Không tạo bucket độc lập chỉ theo cặp IP+username |
| 5 | Attacker đổi IP nhưng giữ một account | Account bucket vẫn áp dụng |
| 6 | Nhiều pod xử lý request cùng account | Shared store giữ counter nhất quán |
| 7 | Redis xử lý hai request đồng thời | Increment/check atomic, không vượt ngưỡng do race |
| 8 | Bucket hết TTL | Counter phục hồi đúng policy |
| 9 | Request dùng forwarded IP giả mạo | Không thay đổi IP bucket nếu proxy không tin cậy |
| 10 | Username có Unicode/space/case khác nhau | Canonicalization khớp user lookup policy |
| 11 | Account không tồn tại bị thử nhiều lần | Vẫn bị account bucket giới hạn |
| 12 | Account không tồn tại và sai password | Message/status/redirect tương đương |
| 13 | Account disabled và password sai | Không tiết lộ account state qua public response |
| 14 | Account locked và username sai | Không tạo response oracle |
| 15 | Login response timing cho account tồn tại/không tồn tại | Không có chênh lệch dễ khai thác qua thống kê |
| 16 | Password reset với email không tồn tại | Response giống email tồn tại |
| 17 | Password reset lặp nhiều lần | Rate limit gửi email và chống spam |
| 18 | Registration với email đã tồn tại | Không tiết lộ account theo policy |
| 19 | Password nằm trong breach corpus khi đổi password | Bị chặn hoặc yêu cầu chọn password khác |
| 20 | Login dùng password có dấu hiệu bị lộ | Risk policy có thể yêu cầu step-up/rotation |
| 21 | Login từ thiết bị mới | MFA/step-up theo policy |
| 22 | Một IP thử nhiều account | Risk engine phát hiện password spray/stuffing |
| 23 | CAPTCHA solver trả kết quả hợp lệ nhưng velocity bất thường | Các lớp risk khác vẫn có thể throttle |
| 24 | User thật bị throttle | Có thông báo generic và recovery path phù hợp |
| 25 | Account bucket bị attacker cố ý làm đầy | Không tạo permanent lockout dễ gây DoS |
| 26 | MFA OTP sai liên tiếp | Authenticator-specific throttle được áp dụng |
| 27 | OTP đúng đã dùng lại | Replay bị từ chối |
| 28 | Recovery code sai liên tiếp | Counter/throttle theo authenticator |
| 29 | Recovery code đúng dùng lần thứ hai | Bị từ chối |
| 30 | Device verification thử nhiều user_code | Throttle và response không tiết lộ code hợp lệ |
| 31 | Device authorization client tạo request quá nhanh | Client/IP quota được áp dụng |
| 32 | Confidential client gửi secret sai liên tiếp | Client-auth bucket tăng, không khóa user account |
| 33 | Client ID không tồn tại và secret sai | Không lộ registration detail ngoài protocol contract |
| 34 | AuthenticationFailureBadCredentialsEvent được publish | Metrics/audit nhận event mà không log credential |
| 35 | AuthenticationSuccessEvent sau MFA | Chỉ reset counter theo policy sau full authentication |
| 36 | Rate limiter store tạm unavailable | Fallback/fail policy đúng threat model, không mở vô hạn |
| 37 | Metric dashboard theo dõi failure/success/throttle | Không có raw username/password hoặc high-cardinality PII |
| 38 | Một nguồn bị chặn nhưng user đổi sang nguồn khác | Account bucket và risk policy vẫn áp dụng |
| 39 | Nhiều account bị thử một password phổ biến | Phát hiện pattern password spraying |
| 40 | Nhiều cặp credential bị phát lại trên nhiều thiết bị | Phát hiện credential stuffing và yêu cầu step-up |
| 41 | User bị disable sau login thành công trước đó | Session/token lifecycle xử lý theo account policy |
| 42 | Client secret rotation sau incident | Credential cũ bị vô hiệu hóa và audit được lưu |
| 43 | Rate limit chỉ cấu hình tại CDN | Integration test chứng minh application vẫn có identity-aware limit |
| 44 | Endpoint recovery/MFA bị bỏ khỏi policy | Security review phát hiện endpoint chưa được bảo vệ |
| 45 | Public response trả remaining attempts | Enumeration test thất bại |

### 11.1. Integration test với MockMvc

Ví dụ dưới đây kiểm tra filter/handler ở mức HTTP. LoginAbuseGuard là mock hoặc test implementation; test cần xác minh cả request bị throttle và request được chuyển tới authentication flow.

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void throttledLoginIsRejectedBeforeAuthentication() throws Exception {
    when(loginAbuseGuard.isThrottled("alice@example.vn", "203.0.113.10"))
            .thenReturn(true);

    mockMvc.perform(post("/login")
            .param("username", "alice@example.vn")
            .param("password", "not-a-real-password"))
        .andExpect(status().isTooManyRequests());

    verify(authenticationManager, never()).authenticate(any());
}

@Test
void failedLoginIncrementsAccountAndIpBuckets() throws Exception {
    when(loginAbuseGuard.isThrottled("alice@example.vn", "203.0.113.10"))
            .thenReturn(false);

    mockMvc.perform(post("/login")
            .param("username", "alice@example.vn")
            .param("password", "wrong-password"))
        .andExpect(status().is3xxRedirection());

    verify(loginAbuseGuard).recordFailure(
            "alice@example.vn", "203.0.113.10");
}
~~~

Test thứ hai giả định failure handler redirect về login page. Nếu ứng dụng dùng CSRF cho form login, test cần cung cấp CSRF token hợp lệ để request đến được rate limiter/authentication filter. ClientIpResolver trong test được cấu hình deterministic; không dựa vào X-Forwarded-For tùy ý.

Ngoài MockMvc, cần integration test Redis atomicity, TTL, multi-pod consistency, timing distribution và các endpoint reset/MFA/device verification. Không dùng một unit test cho filter để kết luận đã chống được distributed credential stuffing.

## 12. Troubleshooting và checklist production

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Attacker vượt rate limit bằng nhiều IP | Chỉ giới hạn theo IP | Thêm account bucket độc lập |
| Một IP thử hàng nghìn username | Chỉ dùng bucket IP+username | Thêm IP bucket tổng và account bucket |
| User thật bị khóa bởi attacker | Hard account lockout không có recovery | Progressive delay, step-up và recovery path |
| User enumeration dù message giống nhau | Status, timing, redirect hoặc header khác | Chuẩn hóa response và dummy hash |
| Rate limit mất sau pod restart | Counter lưu trong RAM | Shared Redis/database store |
| Một pod có ngưỡng khác pod khác | Local state hoặc config drift | Shared policy/configuration và atomic operation |
| Login bị throttle nhưng password reset không bị | Chỉ bảo vệ /login | Lập inventory và bảo vệ mọi authentication/recovery flow |
| Credential stuffing vẫn thành công | Credential đúng và không có MFA/risk signal | MFA/passkey, breached-password detection và anomaly detection |
| CAPTCHA bị vượt qua | Dùng CAPTCHA như lớp duy nhất | Kết hợp nhiều lớp và theo dõi behavior |
| Client secret sai làm khóa user | Dùng chung counter user/client | Tách client authentication throttling |
| Device user_code bị dò | Không có verification throttling | Giới hạn theo IP/session và TTL/code entropy |
| Forwarded IP bị giả mạo | Tin X-Forwarded-For từ mọi nguồn | Chỉ trust proxy đã cấu hình |
| Metrics lộ email/username | Dùng raw identifier làm label | HMAC pseudonymization và aggregate metrics |

### 12.1. Checklist production

- [ ] Đã phân biệt brute force, password spraying, credential stuffing và enumeration.
- [ ] Có rate limit theo account identifier và IP độc lập.
- [ ] Không chỉ dùng key ghép IP+username.
- [ ] Account identifier được canonicalize theo user lookup policy.
- [ ] Account/IP keys được pseudonymize và secret HMAC được quản lý an toàn.
- [ ] Rate limiter dùng atomic shared store cho nhiều instance.
- [ ] Dùng token bucket/sliding window hoặc thuật toán phù hợp, có TTL.
- [ ] Policy có progressive delay và giới hạn hard lockout để tránh DoS.
- [ ] Ngưỡng được tune theo traffic/risk; không coi 100 lần là mặc định.
- [ ] Response throttling không tiết lộ bucket hoặc số lần thử còn lại.
- [ ] Login, reset, recovery, MFA, device verification và client authentication có policy riêng.
- [ ] Login/reset/registration không làm lộ account existence qua message/status/timing.
- [ ] Custom AuthenticationProvider xử lý timing cho user không tồn tại.
- [ ] MFA/passkeys và risk-based step-up được áp dụng cho account nhạy cảm.
- [ ] Password mới được kiểm tra với breached/common password corpus.
- [ ] Webhook/edge/IP reputation không phải lớp bảo vệ duy nhất.
- [ ] Client credential failures không làm tăng user password counter.
- [ ] Authentication events được dùng cho monitoring nhưng không log credential.
- [ ] Audit không chứa password, OTP, recovery code, token hoặc secret.
- [ ] Có alert cho one-account-many-IP, one-IP-many-account và distributed patterns.
- [ ] Có incident playbook cho account/client compromise và session/token revocation.
- [ ] Có test multi-pod, concurrent requests, enumeration timing và recovery flow.

**Câu hỏi tự đánh giá**

1. Brute force, password spraying và credential stuffing khác nhau ở điểm nào?
2. Vì sao account enumeration thường là bước chuẩn bị cho credential attacks?
3. Vì sao rate limit chỉ theo IP không đủ?
4. Vì sao bucket chỉ dùng cặp IP+username có thể bị bypass?
5. Cần dùng account identifier canonicalized như thế nào để tạo bucket ổn định?
6. Vì sao nên HMAC username trước khi lưu vào Redis key hoặc metrics?
7. Token bucket và sliding window khác fixed window ở điểm nào?
8. Vì sao hard account lockout có thể trở thành denial-of-service vector?
9. NIST SP 800-63B-4 quy định giới hạn 100 attempts theo ý nghĩa nào?
10. Spring Security filter nào có thể kiểm tra rate limit trước password authentication?
11. Vì sao AuthenticationFailureHandler phù hợp để ghi nhận request context hơn authentication event đơn thuần?
12. AuthenticationFailureBadCredentialsEvent và AuthenticationSuccessEvent hữu ích cho mục đích gì?
13. Vì sao user không tồn tại cần được xử lý với timing tương tự password sai?
14. Làm thế nào giữ generic response cho password reset và account recovery?
15. Vì sao MFA/passkeys giúp chống credential stuffing?
16. Khi nào nên yêu cầu step-up MFA hoặc CAPTCHA?
17. Vì sao CAPTCHA không nên là lớp phòng vệ duy nhất?
18. Device Verification cần giới hạn những request nào?
19. Vì sao client secret failure cần bucket riêng với user password failure?
20. Cần theo dõi metrics nào để phát hiện password spraying và credential stuffing?

## Tài liệu tham khảo

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication response, timing discrepancy, login throttling, account lockout, CAPTCHA và MFA.
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): MFA, leaked-password detection, IP/device signals, CAPTCHA và defense-in-depth.
- [OWASP Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html): rate limiting theo account/IP, token bucket/sliding window, risk signals và privacy-aware fingerprinting.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): bảo vệ password recovery và chống account enumeration.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): throttling, authenticator failure limits, MFA và recovery.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): publish/consume authentication success và failure events.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): user lookup, password verification và PasswordEncoder.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): adaptive one-way password hashing và DelegatingPasswordEncoder.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): client authentication và OAuth2/OIDC endpoint customization.
