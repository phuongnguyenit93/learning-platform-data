# Thông báo đăng nhập thất bại và giới hạn tiết lộ danh tính

## Mục tiêu bài học

Một màn hình đăng nhập không chỉ kiểm tra mật khẩu. Nó còn quyết định **thông tin nào được tiết lộ cho người chưa xác thực**. Chỉ một câu như “Email chưa đăng ký”, “Tài khoản đã tồn tại nhưng bị khóa” hoặc một phản hồi nhanh bất thường cũng có thể giúp kẻ tấn công đoán được **tên đăng nhập/email nào có trong hệ thống**, tình trạng tài khoản, nhà cung cấp danh tính mà tài khoản sử dụng hoặc quy trình khôi phục được phép.

Bài học thuộc chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi tập trung vào **thông báo đăng nhập thất bại, giới hạn tiết lộ danh tính và cách kết hợp với các lớp bảo vệ HTTP/trình duyệt của Spring Security**: CSRF, CORS, session, security headers, CSP, HSTS và HTTP firewall. Ví dụ được trình bày cho cả **Servlet/Spring MVC** và **Reactive/WebFlux**.

Sau bài này, bạn có thể:

1. Phân tích **account enumeration** (dò tài khoản tồn tại) và **identity disclosure** qua thông báo, HTTP status, redirect, headers, độ dài body, thời gian phản hồi và những luồng ngoài login.
2. Thiết kế thông báo lỗi đăng nhập **đủ hữu ích cho người dùng nhưng không phân biệt tài khoản tồn tại với không tồn tại** trước khi có bằng chứng xác thực phù hợp.
3. Phân loại **lỗi credential (401/redirect), lỗi CSRF (thường 403), giới hạn yêu cầu (429) và lỗi dịch vụ (5xx)** mà không biến chúng thành oracle tiết lộ danh tính.
4. Cấu hình Spring Security **AuthenticationFailureHandler** cho Servlet và **ServerAuthenticationFailureHandler** cho Reactive/WebFlux.
5. Giữ **CSRF token trên POST /login**, CORS allowlist, session lifecycle, cookie flags, CSP và HTTPS trong khi xử lý lỗi đăng nhập.
6. Giảm rò rỉ qua **password reset, registration, invitation, SSO/OIDC, MFA, remember-me và khóa tài khoản**.
7. Thiết kế **rate limiting, audit, logging và hỗ trợ người dùng** không làm lộ credential hoặc tạo khả năng từ chối dịch vụ cho người dùng thật.
8. Viết kiểm thử **MockMvc, WebTestClient và browser end-to-end** cho phản hồi đồng nhất, tính khả dụng và những kênh rò rỉ phụ.

## 1. Một lỗi nhỏ trong thông báo có thể tiết lộ điều gì?

Giả sử ứng dụng tại https://accounts.example.com cho đăng nhập bằng email và mật khẩu. Hai trường hợp đều phải bị từ chối:

~~~text
Trường hợp A: nobody@example.test      + mật khẩu bất kỳ
Trường hợp B: existing@example.test    + mật khẩu sai
~~~

Nếu ứng dụng trả về hai thông điệp khác nhau:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error":"EMAIL_NOT_REGISTERED"}
~~~

và:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"INCORRECT_PASSWORD"}
~~~

thì người chưa đăng nhập có thể phân biệt **email nào đã có tài khoản**. Họ không cần biết mật khẩu; chỉ cần so sánh kết quả.

Rủi ro thường được gọi là **account enumeration** hoặc **username/email enumeration**. Nó có thể được sử dụng làm bước chuẩn bị cho phishing có chủ đích, password spraying, credential stuffing, quấy rối, hoặc suy luận việc một người có sử dụng dịch vụ nhạy cảm hay không.

### 1.1. Vì sao “chưa đăng nhập” vẫn là một ranh giới bảo mật?

Một endpoint công khai như POST /login phải cho phép người chưa xác thực gửi credential. Nhưng **được phép gửi request** không có nghĩa người gửi được quyền biết:

- Một email cụ thể đã đăng ký hay chưa.
- Tài khoản nào bị khóa, vô hiệu hóa, chưa xác minh hoặc đang bị điều tra gian lận.
- Một user có quyền quản trị, thuộc tenant, tổ chức hoặc nhóm nào.
- Tài khoản sử dụng đăng nhập mật khẩu, social login, SSO hay MFA nào.
- Địa chỉ email khôi phục, số điện thoại hoặc thiết bị được liên kết với người khác.
- Thời điểm đăng nhập gần nhất, số lần thất bại hoặc lịch sử reset mật khẩu.

Những chi tiết này có thể cần cho **người đã chứng minh quyền sở hữu tài khoản** hoặc đội hỗ trợ được phân quyền, nhưng **không nên xuất hiện chỉ vì có một username được nhập vào form**.

### 1.2. Mô hình ranh giới tin cậy

~~~mermaid
flowchart LR
    A["Browser chưa xác thực / người gửi HTTP request"] --> L["POST /login"]
    L --> CS["Spring Security: CSRF + auth pipeline"]
    CS --> P["AuthenticationProvider / user store"]
    P --> D{"Kết quả kiểm tra"}
    D -->|Sai thông tin| G["Failure handler: phản hồi công khai tổng quát"]
    D -->|Tài khoản bị hạn chế| G
    D -->|Tài khoản không tồn tại| G
    D -->|Đủ điều kiện| S["Authenticated session / MFA flow"]
    D --> T["Audit nội bộ có kiểm soát"]
    G --> A
~~~

**Hai đường thông tin phải khác nhau**: đường đến người chưa xác thực chỉ tiết lộ điều cần thiết để tiếp tục; đường audit nội bộ giữ thông tin phục vụ chẩn đoán nhưng phải giới hạn truy cập, thời gian lưu và dữ liệu cá nhân.

### 1.3. Thông báo công khai không đồng nghĩa kết quả backend bị gộp

Backend vẫn cần phân biệt:

- Không tìm thấy account.
- Password mismatch.
- Account locked/disabled/expired.
- Credential expired.
- Kết nối database hoặc IdP lỗi.
- Chính sách rate limit.
- CSRF token thiếu/sai.

**Không được bỏ các kiểm tra này.** Yêu cầu là **chuẩn hóa cách tiết lộ cho người chưa được tin cậy**, trong khi điều kiện xác thực, quyền và xử lý vận hành vẫn chính xác.

## 2. Account enumeration qua nhiều kênh hơn một câu thông báo

Một hệ thống có thể hiển thị cùng thông báo “Thông tin đăng nhập không hợp lệ” nhưng vẫn rò rỉ vì những khác biệt khác.

### 2.1. Bản đồ các kênh rò rỉ

| Kênh | Ví dụ rò rỉ | Hậu quả |
| --- | --- | --- |
| **Nội dung body** | “Email không tồn tại” khác “Mật khẩu sai”. | Đoán account tồn tại. |
| **HTTP status** | 404 cho user không có, 401 cho user có. | Dò tài khoản mà không cần xem body. |
| **Error code JSON** | USER_MISSING và PASSWORD_BAD có cùng message. | Client có thể suy ra trạng thái từ code. |
| **Redirect/Location** | /register khi user chưa có; /login?locked=1 khi user có. | Phân biệt qua URL hoặc history. |
| **Headers** | Một nhóm lỗi có header custom, challenge hoặc Set-Cookie khác. | Side channel qua metadata. |
| **Độ dài/kiểu body** | Error page lớn hơn nhiều chỉ khi account tồn tại. | Phân loại kết quả qua response size. |
| **Thời gian phản hồi** | User không có được trả ngay, user có chạy password hash tốn thời gian. | Timing-based enumeration. |
| **Rate-limit/lockout** | 429 chỉ khi username tồn tại và đã nhập sai nhiều lần. | Đoán account qua trạng thái throttle. |
| **Email/SMS bên ngoài** | Reset hiển thị “Đã gửi mail” chỉ khi user có tài khoản. | Suy luận từ UI hoặc workflow. |
| **Đăng ký tài khoản** | “Email này đã được sử dụng” ngay khi chưa xác minh chủ sở hữu. | Lộ dữ liệu thành viên. |
| **SSO/MFA/invitation** | “Tài khoản này dùng IdP X” hoặc “số điện thoại kết thúc 1234” trước xác thực. | Tiết lộ cơ chế và dữ liệu định danh. |
| **Frontend telemetry** | Log username, mã lỗi nội bộ hoặc tên exception vào analytics. | Rò dữ liệu qua hệ thống thứ ba. |

Tấn công có thể **so sánh nhiều tín hiệu đồng thời**. Chỉ sửa câu thông báo trên màn hình mà vẫn giữ status, error code hoặc redirect phân nhánh thường chưa đủ.

### 2.2. Ví dụ chỉ đổi message nhưng vẫn rò qua mã lỗi

Không nên trả:

~~~json
{"code":"UNKNOWN_USER","message":"Không thể đăng nhập."}
~~~

cho email không có và:

~~~json
{"code":"WRONG_PASSWORD","message":"Không thể đăng nhập."}
~~~

cho email có. Dù người dùng nhìn thấy cùng một dòng chữ, client hoặc người kiểm tra Network vẫn phân biệt được trạng thái.

Một hợp đồng công khai phù hợp hơn cho **credential không hợp lệ hoặc trạng thái account chưa được chứng minh quyền sở hữu**:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json; charset=UTF-8
Cache-Control: no-store

{"code":"LOGIN_FAILED","message":"Email hoặc mật khẩu không đúng, hoặc không thể đăng nhập bằng thông tin này."}
~~~

Đây là một **hợp đồng minh họa**, không phải quy định phải dùng chính xác câu chữ/HTTP status này trong mọi ứng dụng. Với **HTML form login**, Spring Security thường dùng **redirect tới /login?error** thay vì JSON 401. Dù chọn cách nào, phản hồi phải đồng nhất cho các nguyên nhân **không nên tiết lộ**.

### 2.3. Khác biệt ở tốc độ phản hồi

Một luồng xác thực tự viết có thể mắc lỗi:

~~~text
Nếu không thấy user:
    trả lỗi ngay trong vài mili-giây

Nếu thấy user:
    tính BCrypt/Argon2 password hash tốn công CPU
    rồi trả lỗi
~~~

Người gửi có thể đo thời gian trên nhiều lần thử và phát hiện chênh lệch có tính hệ thống.

Nguyên tắc phòng vệ:

- Không tạo nhánh **bỏ qua hoàn toàn kiểm tra mật khẩu** chỉ cho user không tồn tại, nếu nhánh đó tạo chênh lệch rõ rệt.
- Ưu tiên **AuthenticationProvider/PasswordEncoder chuẩn** của Spring Security có các biện pháp giảm lộ khác biệt; nếu tự viết, xem xét password verification path có chi phí tương đương.
- Kiểm tra timing qua **nhiều lần thử ở môi trường test**, không kết luận từ một request mạng duy nhất.
- Không dùng một lệnh sleep cố định như “giải pháp duy nhất”: tải hệ thống, cache, dependency và concurrency vẫn tạo chênh lệch; sleep có thể tăng nguy cơ DoS.
- Không cố hứa “HTTP response có thời gian bằng nhau tuyệt đối”; mục tiêu là **giảm những khác biệt có thể khai thác**, kết hợp rate limiting, monitoring và bảo vệ credential.

### 2.4. Error page và browser cũng là một phần giao diện

Màn hình có thể hiển thị thông báo tổng quát, nhưng mã HTML còn:

- Render tên exception hoặc username vào comment/debug element.
- Chèn thông báo từ query parameter chưa escape vào DOM.
- Dùng một redirect đến **/login?reason=ACCOUNT_LOCKED**.
- Gửi analytics event chứa **email/password** hoặc trường reason nội bộ.
- Có response khác biệt khi **Accept: text/html** so với **application/json**.

Hãy kiểm tra **Network, DOM đã render, headers, redirects và log/telemetry**, không chỉ màn hình cuối cùng.

## 3. Thiết kế thông báo cho người dùng: rõ nhưng không tiết lộ thừa

### 3.1. Quy tắc cốt lõi

Trước khi chứng minh user có quyền với một account, ưu tiên **một thông báo tổng quát cho các lỗi liên quan đến sự tồn tại của account/credential/trạng thái nhạy cảm**.

Ví dụ cho form login:

> Không thể đăng nhập với thông tin đã cung cấp. Hãy kiểm tra lại hoặc sử dụng chức năng khôi phục tài khoản.

Thay vì:

> Email không tồn tại. Hãy đăng ký tài khoản mới.

Hoặc:

> Email này tồn tại nhưng mật khẩu không đúng. Tài khoản đã bị khóa sau ba lần thử.

Câu thông báo tổng quát cần có **hành động tiếp theo hợp lý**, ví dụ kiểm tra lại thông tin, dùng luồng quên mật khẩu, hoặc liên hệ hỗ trợ chính thức. Tránh câu mơ hồ tuyệt đối khiến người dùng không biết làm gì.

### 3.2. Các trạng thái được gộp ở mức công khai

| Kết quả xác thực nội bộ | Thông báo trước xác thực | Xử lý hệ thống |
| --- | --- | --- |
| User/email không tồn tại | Thông báo login failed tổng quát. | Audit/throttle theo chính sách, không tạo principal. |
| Password sai | Thông báo login failed tổng quát. | Password failure tracking, không tạo principal. |
| Account bị vô hiệu hóa | Thông báo tổng quát khi chưa chứng minh quyền sở hữu. | Giữ account disabled, hỗ trợ bằng kênh xác minh. |
| Account bị khóa | Thông báo tổng quát hoặc chính sách thông báo đã đánh giá rủi ro. | Áp dụng lockout/throttle, tránh tiết lộ trạng thái qua oracle. |
| Credential expired | Không công khai trạng thái nhạy cảm trước khi xác minh phù hợp. | Nếu đã chứng minh danh tính, chuyển sang luồng đổi mật khẩu an toàn. |
| User chưa xác minh email | Không tự động tiết lộ email đã đăng ký từ màn hình login. | Dùng out-of-band verification theo chính sách. |
| Mật khẩu đúng, cần MFA | Có thể hiển thị bước MFA sau khi password factor đã được kiểm chứng. | Chưa cấp quyền đầy đủ trước khi hoàn thành MFA. |
| Dịch vụ auth/IdP không khả dụng | Thông báo dịch vụ tạm thời không khả dụng. | Có thể trả 503/5xx phù hợp và log sự cố nội bộ. |

**Không gộp lỗi hạ tầng thành “sai mật khẩu” để che lỗi vận hành.** Nếu xác thực không thể thực hiện do dependency lỗi, ứng dụng nên phản ánh **lỗi dịch vụ** ở mức an toàn, tránh vừa đánh lừa user vừa làm sai telemetry.

### 3.3. Khi nào được hiển thị thông tin cụ thể hơn?

Mức tiết lộ có thể tăng sau khi có **bằng chứng đủ mạnh về quyền sở hữu tài khoản**. Ví dụ:

- Sau khi mật khẩu được xác minh, thông báo cần hoàn thành MFA.
- Sau khi user đăng nhập hoặc xác minh email/số điện thoại, hiển thị trạng thái cần cập nhật mật khẩu.
- Trong dashboard đã xác thực, giải thích quyền bị giới hạn hoặc lý do session sắp hết hạn.
- Nhân viên hỗ trợ được phân quyền và xác minh danh tính theo quy trình riêng có thể nhận thêm thông tin.

**Một trường username/email do client nhập vào không phải bằng chứng sở hữu tài khoản.** Cần xem xét mức tin cậy của mỗi bước, nhất là khi ứng dụng có SSO, passkey hoặc passwordless login.

### 3.4. UX giúp user thật mà không tạo oracle

Có thể cải thiện trải nghiệm bằng:

- Đặt trường mật khẩu ở trạng thái để user thử lại, nhưng **không giữ mật khẩu đã nhập trong HTML response, URL hoặc log**.
- Giữ lại username/email trong form ở phía client nếu phù hợp UX và chính sách riêng tư; không phản chiếu input chưa escape.
- Đưa đường dẫn **“Quên mật khẩu?”** hoặc **“Cần trợ giúp?”** cho cả hai nhóm account tồn tại/không tồn tại.
- Sử dụng cùng thông báo/số lần cho phép thử theo quy tắc không làm lộ sự tồn tại của account.
- Hỗ trợ ngôn ngữ và accessibility bằng thông điệp gắn với form qua **role=alert** hoặc mô hình tương đương.
- Cho phép trình quản lý mật khẩu hoạt động đúng với trường username/password, không dùng cơ chế UI làm giảm bảo mật.
- Khi xác thực cần MFA, cung cấp một workflow riêng với trạng thái đã được ràng buộc; không phơi bày account existence từ bước đầu.

### 3.5. Không trả password, session hoặc internal exception

Một response lỗi không được chứa:

~~~json
{
  "password": "example-secret",
  "sessionId": "opaque-session-id",
  "exception": "org.example.auth.UserAccountLockedException",
  "existingEmail": "existing@example.test",
  "hash": "$2a$12$..."
}
~~~

Đây là **mẫu nội dung cấm đưa ra client**, dùng để minh họa các loại thông tin phải loại bỏ. Kể cả trong môi trường debug, không truyền trực tiếp exception object, stack trace, password hash hoặc session ID vào response của login endpoint.

## 4. Phân biệt mã HTTP mà không biến status thành oracle

Không có một quy tắc duy nhất buộc mọi ứng dụng phải trả cùng status cho mọi loại lỗi; thiết kế phải dựa trên **loại lỗi** và **không phân biệt thông tin tài khoản nhạy cảm trong cùng loại**.

| Tình huống | Response có thể phù hợp | Cần tránh |
| --- | --- | --- |
| Form login sai credential | Redirect **302 tới /login?error** hoặc hợp đồng tương đương. | Redirect path khác nhau theo user tồn tại hay không. |
| API login sai credential | **401 Unauthorized** với error code tổng quát. | 404 cho user thiếu, 401 cho password sai. |
| POST login thiếu/sai CSRF token | Thường **403 Forbidden** từ CsrfFilter. | Gộp với password errors để rồi tắt CSRF cho tiện. |
| Request bị rate limit | **429 Too Many Requests**, Retry-After nếu áp dụng. | Trả 429 chỉ cho account có thật theo điều kiện quan sát được. |
| Authentication dependency lỗi | **503 Service Unavailable** hoặc 5xx phù hợp. | Đổi thành 401 giả “sai mật khẩu” khiến user lặp lại vô ích. |
| API cần authentication nhưng request thiếu session/token | **401** hoặc redirect tùy client contract. | Tiết lộ trạng thái account bất kỳ từ request chưa auth. |
| Principal đã xác thực nhưng thiếu quyền tài nguyên | **403 Forbidden** (hoặc policy che tài nguyên 404 ở một số API). | Dùng lỗi quyền để tiết lộ account khác trước xác thực. |
| Input sai định dạng cú pháp (không phải account existence) | **400 Bad Request** theo contract. | Suy từ “email đúng định dạng” rằng email có account. |

### 4.1. 401 so với 403 trong login

- **401** thường dùng khi request cần authentication hoặc credential không hợp lệ, đặc biệt ở API. Với HTTP Basic/Bearer, header **WWW-Authenticate** có các quy tắc/challenge riêng.
- **403** thường diễn tả request đã được hiểu nhưng bị từ chối quyền; **CSRF invalid/missing** trong Spring Security có thể dẫn tới 403 trước cả bước xác thực mật khẩu.
- **HTML formLogin** mặc định của Spring Security thường **redirect sau thất bại**, nên một request POST có thể trả 302 tới trang login lỗi. Điều này không sai khi người dùng là browser form, nhưng cần phân tích chuỗi redirect.
- **429** có thể hữu ích cho throttle, song nếu trigger/chỉ báo khác nhau giữa username có và không có, bản thân giới hạn lại trở thành enumeration oracle.

Giữ **phản hồi tương đương cho hai credential sai có khả năng bị so sánh**, nhưng không cần cố biến mọi lỗi CSRF, lỗi mạng hoặc lỗi service thành cùng một thông báo “sai password”.

### 4.2. Không để API response vô tình chứa HTML login

SPA gọi POST /login và nhận status 200 cuối cùng sau một chuỗi **302 tới /login?error**. Nếu frontend chỉ kiểm tra response.ok, nó có thể kết luận **login thành công** dù response cuối là HTML trang đăng nhập.

Với SPA, nên thống nhất contract như **204 cho login thành công, 401 + JSON tổng quát cho credential thất bại**, và kiểm tra **GET /api/me** để xác minh principal sau login. Đây là một lựa chọn, không phải mặc định formLogin.

### 4.3. Không tiết lộ identifier qua URL/redirect

Không nên redirect thành:

~~~http
Location: /login?error=UNKNOWN_USER&email=existing@example.test
~~~

Ngay cả khi browser chỉ hiển thị một dòng lỗi tổng quát, URL có thể được lưu trong history, log, analytics, screenshot hoặc Referer theo chính sách browser. Một đích an toàn hơn thường là:

~~~http
Location: /login?error
~~~

Trang đích phải dùng thông điệp **cố định**, không suy ra trạng thái account từ query parameters do client tùy ý đặt.

## 5. Spring Security Servlet: form login và thông báo thất bại an toàn

Với **Spring Security 6.x trên Spring MVC/Servlet**, cơ chế **formLogin** gọi AuthenticationManager/AuthenticationProvider rồi chuyển kết quả thất bại cho **AuthenticationFailureHandler**. Một form HTML truyền thống thường muốn redirect về trang login có thông báo chung.

### 5.1. FormLogin với một đích lỗi duy nhất

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HtmlLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login", "/help/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .failureUrl("/login?error")
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .build();
    }
}
~~~

Đoạn code giả định ứng dụng cung cấp **GET /login**, có AuthenticationProvider/UserDetailsService và credential test phù hợp. **formLogin mặc định đọc form parameters**, không tự parse JSON body. **POST /login vẫn cần CSRF token**; permitAll là quy tắc authorization, không bỏ CsrfFilter.

**failureUrl("/login?error")** dùng một URL chung cho các lỗi credential/status phải được ẩn. Không điều hướng /login?userMissing, /login?passwordBad hoặc /login?accountLocked dựa trên account existence. Trong security chains tùy chỉnh, phải kiểm tra đúng chain đang xử lý /login.

### 5.2. Trang lỗi chỉ hiển thị thông điệp cố định

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

Template Thymeleaf:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <h1>Đăng nhập</h1>

  <p th:if="${param.error}" role="alert">
    Không thể đăng nhập với thông tin đã cung cấp.
    Hãy kiểm tra lại hoặc sử dụng chức năng khôi phục tài khoản.
  </p>

  <form th:action="@{/login}" method="post">
    <label for="username">Email hoặc tài khoản</label>
    <input id="username" name="username" autocomplete="username">

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password">

    <button type="submit">Đăng nhập</button>
  </form>

  <a th:href="@{/help/password-reset}">Quên mật khẩu?</a>
</body>
</html>
~~~

Biểu thức **th:if** kiểm tra tham số error và chỉ quyết định hiển thị thông báo cố định. Không đưa trực tiếp exception message, tên user hoặc account status vào trang; tham số query cũng không phải bằng chứng một lần đăng nhập đã thực sự thất bại để dùng trong quyết định bảo mật.

Với tích hợp Spring MVC/Thymeleaf, **RequestDataValueProcessor** thường có thể chèn hidden CSRF parameter vào form POST có th:action. Kiểm tra **HTML đã render** thực tế; nếu không có token, cần sửa cách cấp/render token, **không tắt CSRF**.

### 5.3. Không trả exception.getMessage ra trang

Một chống mẫu:

~~~java
// KHÔNG làm với response công khai.
String publicMessage = authenticationException.getMessage();
~~~

AuthenticationException có thể chứa thông tin provider, account status hoặc exception message khác nhau theo tài khoản. Kể cả nếu hôm nay chuỗi này tổng quát, nó không phải public API có hợp đồng đảm bảo riêng tư. Hãy map kết quả về một **public error code do ứng dụng định nghĩa**; giữ exception chi tiết trong kênh nội bộ có kiểm soát.

Spring Security có **SimpleUrlAuthenticationFailureHandler** giúp redirect khi form login thất bại. Cần thận trọng nếu custom code đọc exception từ request/session và trực tiếp in ra HTML. Việc exception được lưu để xử lý nội bộ **không tự cấp quyền tiết lộ**.

### 5.4. FormLogin thất bại khác CSRF thất bại

~~~text
POST /login, thiếu hoặc sai CSRF token
  → CsrfFilter từ chối, thường 403
  → Không cần đến AuthenticationFailureHandler

POST /login, CSRF hợp lệ nhưng credential sai
  → AuthenticationManager/Provider từ chối
  → AuthenticationFailureHandler
  → Redirect /login?error hoặc JSON 401 theo contract
~~~

Lỗi CSRF cần được chẩn đoán theo session/token repository; không nên gộp nó thành sai mật khẩu để rồi bỏ CsrfFilter. Việc **401/403 khác nhau theo loại lỗi** không đồng nghĩa account enumeration nếu từng loại không phân biệt sự tồn tại của user.

## 6. Spring Security Servlet: JSON 401 thống nhất cho SPA

Khi frontend SPA tự gọi fetch, HTML redirect không phải lúc nào cũng thuận tiện. Có thể thống nhất **204 cho login thành công, 401 JSON tổng quát cho credential thất bại** và endpoint **GET /api/me** để xác nhận principal sau login.

### 6.1. AuthenticationFailureHandler trả thông điệp chung

~~~java
import java.io.IOException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

final class JsonLoginFailureHandler
        implements AuthenticationFailureHandler {

    private static final String BODY =
            "{\"code\":\"LOGIN_FAILED\","
            + "\"message\":\"Không thể đăng nhập với thông tin đã cung cấp.\"}";

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        // Không serialize exception, username hoặc trạng thái account.
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(BODY);
    }
}
~~~

Handler dùng **cùng status/code/body** cho các lỗi credential/account status không được phân biệt trước xác thực. Không phản chiếu username hoặc exception class. **Lỗi hạ tầng thật** có thể cần một nhánh xử lý dịch vụ tổng quát (ví dụ 503) được thiết kế dựa trên **loại sự cố**, không dựa trên sự tồn tại của account; không nên che database outage thành lỗi sai mật khẩu.

### 6.2. Cấu hình SecurityFilterChain dành cho SPA

~~~java
import java.util.List;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSpaLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .requestMatchers("/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginProcessingUrl("/login")
                        .failureHandler(new JsonLoginFailureHandler())
                        .successHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT))
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Đây là **phương án thay thế form HTML ở mục 5**, không khai báo hai chain trùng matcher trong cùng ứng dụng. Ứng dụng thực còn cần authentication provider, GET /csrf, GET /api/me, cookie config và phân quyền API.

**CORS** phải cấp quyền cho **/csrf và /login**, không chỉ /api/**. Preflight OPTIONS thường không có session cookie; phải được xử lý CORS trước những auth filters có thể chặn. Nhưng POST /login thực vẫn cần token CSRF hợp lệ và credential đúng.

### 6.3. Endpoint cấp CSRF token cho anonymous browser

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreLoginCsrfController {

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "token", token.getToken()));
    }
}
~~~

Việc truy xuất getToken() giúp deferred token được materialize theo cơ chế Spring Security hiện hành. Một anonymous session có thể được tạo để lưu token; điều đó không phải xác thực user. **Không cache chung** response CSRF, không cấp quyền đọc nó cho mọi origin với credentials.

### 6.4. Frontend gửi form parameters và xử lý status đúng

~~~javascript
async function login(username, password) {
  const api = "https://api.example.com";
  const tokenResponse = await fetch(api + "/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!tokenResponse.ok) {
    showTemporaryLoginProblem();
    return;
  }

  const csrf = await tokenResponse.json();

  const response = await fetch(api + "/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body: new URLSearchParams({ username, password }),
    redirect: "error"
  });

  if (response.status === 401) {
    showGenericLoginError();
    return;
  }
  if (!response.ok) {
    showTemporaryLoginProblem();
    return;
  }

  const me = await fetch(api + "/api/me", {
    credentials: "include",
    cache: "no-store"
  });
  if (!me.ok) {
    showTemporaryLoginProblem();
    return;
  }
  updateAuthenticatedUI(await me.json());
}
~~~

Các hàm **showGenericLoginError, showTemporaryLoginProblem, updateAuthenticatedUI** do frontend tự triển khai. FormLogin mặc định mong chờ **application/x-www-form-urlencoded**; muốn POST JSON cần authentication filter/handler riêng có kiểm tra CSRF phù hợp.

Sau login, token CSRF trước authentication có thể bị xóa bởi **CsrfAuthenticationStrategy**; frontend cần lấy token mới trước POST nghiệp vụ. Không log password/token hoặc đưa credential vào URL.

### 6.5. Những mã lỗi công khai nên được giới hạn

| Mã công khai | Nhóm sự cố | Câu hiển thị |
| --- | --- | --- |
| **LOGIN_FAILED** | Credential/account status không nên tiết lộ. | “Không thể đăng nhập với thông tin đã cung cấp.” |
| **REQUEST_REJECTED** | Request hoặc CSRF không hợp lệ. | “Không thể xử lý yêu cầu. Hãy tải lại trang và thử lại.” |
| **TOO_MANY_REQUESTS** | Giới hạn theo chính sách không tạo oracle. | “Bạn đã thử quá nhiều lần. Vui lòng thử lại sau.” |
| **SERVICE_UNAVAILABLE** | Dependency đăng nhập tạm thời lỗi. | “Dịch vụ đăng nhập đang gián đoạn. Hãy thử lại sau.” |

Không trả **UNKNOWN_USER, WRONG_PASSWORD, LOCKED_USER, MFA_NOT_ENABLED** ra API công khai trước khi xác minh quyền sở hữu phù hợp. Phản hồi nên có content type, Cache-Control và schema thống nhất trong cùng lớp credential failure.

## 7. Spring Security Reactive/WebFlux: ServerAuthenticationFailureHandler

**Spring Security WebFlux** dùng **ServerHttpSecurity** và **SecurityWebFilterChain** thay cho HttpSecurity/Servlet. Khi form login thất bại, điểm mở rộng tương ứng là **ServerAuthenticationFailureHandler**.

### 7.1. Handler Reactive trả JSON chung

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.authentication
        .ServerAuthenticationFailureHandler;

import reactor.core.publisher.Mono;

final class ReactiveJsonLoginFailureHandler {

    static ServerAuthenticationFailureHandler create() {
        return (webFilterExchange, exception) -> {
            ServerHttpResponse response =
                    webFilterExchange.getExchange().getResponse();

            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
            response.getHeaders().setCacheControl("no-store");

            byte[] body = (
                    "{\"code\":\"LOGIN_FAILED\","
                    + "\"message\":\"Không thể đăng nhập với thông tin đã cung cấp.\"}"
                    ).getBytes(StandardCharsets.UTF_8);

            return response.writeWith(Mono.just(
                    response.bufferFactory().wrap(body)));
        };
    }
}
~~~

Handler không phân nhánh theo UsernameNotFoundException, DisabledException, LockedException hoặc nội dung do provider trả về. Response công khai trong cùng loại credential failure có **schema, status và thông điệp ổn định**.

**Đây là ví dụ handler cho authentication failures**, không bao trùm CSRF rejection, CORS error hoặc dependency outage. Những loại lỗi đó cần xử lý riêng theo security chain và error contract, không ghi đè mọi exception thành LOGIN_FAILED.

### 7.2. Cấu hình SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSpaLoginSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/csrf", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .authenticationFailureHandler(
                                ReactiveJsonLoginFailureHandler.create()))
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Đoạn code trên giả định ứng dụng có authentication manager/provider và có một endpoint cấp CSRF token reactive. **Form login default success** có thể vẫn redirect theo cấu hình hiện hành; SPA cần tùy chỉnh **ServerAuthenticationSuccessHandler**/response contract nếu muốn một success status không redirect, thay vì dùng fetch theo redirect rồi tưởng authentication thành công.

**Reactive failure handler không thay CSRF**: POST /login thiếu token có thể bị chặn trước khi handler xác thực chạy. Nên kiểm thử riêng cùng một cookie/WebSession.

### 7.3. CORS source cho WebFlux SPA

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive
        .UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveLoginCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/csrf", config);
        source.registerCorsConfiguration("/login", config);
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Kết nối source với **ServerHttpSecurity** trong ứng dụng SPA:

~~~java
// Đặt trong cấu hình SecurityWebFilterChain được chọn:
http.cors(cors -> cors.configurationSource(corsConfigurationSource()));
~~~

Không trộn **org.springframework.web.cors.reactive** với UrlBasedCorsConfigurationSource của Servlet. Nếu CORS được quản lý ở gateway/edge hoặc một cấu hình WebFlux khác, phải tránh chính sách chồng lắp/mâu thuẫn.

### 7.4. Tránh rò rỉ qua body khi writeWith

WebFlux xử lý response bất đồng bộ, nên handler cần trả **Mono<Void>** gắn với việc ghi response. Không nên gọi block() để đợi IO trong request path. Khi xử lý exception, không gửi stack trace hoặc AuthenticationException trực tiếp vào response.

Nếu ứng dụng có **WebExceptionHandler/ErrorWebExceptionHandler** tùy chỉnh, cần kiểm tra chúng **không thay response tổng quát** bằng một error page chi tiết sau khi authentication failure handler trả kết quả. Cũng cần kiểm tra logs nội bộ không chứa form password hoặc Authorization header.

## 8. AuthenticationProvider và thời gian phản hồi

Giới hạn tiết lộ danh tính phải được đánh giá ở **AuthenticationProvider/UserDetailsService**, không chỉ trong failure handler.

### 8.1. DaoAuthenticationProvider và UsernameNotFoundException

Trong Spring Security Servlet, **DaoAuthenticationProvider** sử dụng UserDetailsService và PasswordEncoder. Các nhánh ngoại lệ có thể gồm:

- **UsernameNotFoundException** khi UserDetailsService không tìm thấy user.
- **BadCredentialsException** khi credential sai.
- **DisabledException, LockedException, AccountExpiredException, CredentialsExpiredException** theo trạng thái account.
- Ngoại lệ hạ tầng nếu user store/identity service không khả dụng.

**AbstractUserDetailsAuthenticationProvider** có tùy chọn **hideUserNotFoundExceptions**, phổ biến được bật mặc định, nhằm chuyển lỗi user không tồn tại thành lỗi credential tổng quát thay vì đưa nguyên UsernameNotFoundException ra ngoài.

Lưu ý quan trọng: **ẩn loại exception không tự bảo đảm thời gian phản hồi và mọi nhánh ở các lớp khác là như nhau**. Nếu ứng dụng tự dùng UserDetailsService hoặc AuthenticationProvider tùy chỉnh, phải kiểm tra riêng.

### 8.2. Không tự tạo nhánh trả lỗi quá sớm

Một chống mẫu dạng pseudo-code:

~~~text
user = findByEmail(request.email)

if user == null:
    return USER_MISSING immediately

if !passwordEncoder.matches(request.password, user.passwordHash):
    return WRONG_PASSWORD

return authenticated
~~~

Dù sau đó frontend thay cả hai message thành LOGIN_FAILED, nhánh “user không tồn tại” có thể không chạy **password hash verification**, tạo khác biệt có thể đo.

Một hướng thiết kế là sử dụng **authentication provider đã được kiểm chứng**, giữ cơ chế giảm khác biệt khi user không tồn tại, và nếu tự xây dựng hệ thống thì bảo đảm đường xác thực thất bại **không cố ý bỏ qua mọi bước tốn công chỉ khi account không tồn tại**. Những chi tiết như hash giả dùng cho account không tồn tại cần được triển khai đúng với PasswordEncoder thực, không tự bịa một chuỗi hash sai định dạng rồi gây khác biệt mới.

### 8.3. Đánh giá timing nên dựa trên thống kê

Timing là **kênh phụ khó triệt tiêu tuyệt đối** do network jitter, cache, GC, database, thread scheduling, load balancer, hash algorithm và rate limiting.

Một phép thử có ích trong **staging**:

1. Tạo ít nhất hai **tài khoản test**: account tồn tại và identifier không tồn tại.
2. Với account tồn tại, cố tình dùng mật khẩu **sai**; không dùng credential người thật.
3. Với identifier không tồn tại, dùng đầu vào có cùng cấu trúc/độ dài tương tự.
4. Cấp CSRF token và session hợp lệ cho cả hai để tránh đo nhầm **403 từ CsrfFilter**.
5. Thực hiện **một số lượng request nhỏ, được giới hạn**, xen kẽ thứ tự và ghi cả server-side latency.
6. So sánh median/phân phối/thành phần xử lý, kiểm tra xem khác biệt có lặp lại hay không.
7. Kiểm tra cả cache warm-up, nhiều instance, connection reuse, trạng thái throttling và lỗi provider.
8. Cải thiện nhánh xác thực hoặc auth-provider config theo nguyên nhân thật; không gắn sleep ngẫu nhiên tùy ý để che mọi lỗi.

Không dùng một ngưỡng thời gian cố định như “chênh lệch dưới 20 ms thì an toàn” cho mọi ứng dụng; mức tin cậy phụ thuộc threat model và điều kiện đo.

### 8.4. Không so sánh password bằng chuỗi thuần

Với mật khẩu, sử dụng **PasswordEncoder thích hợp** và lưu **one-way password hash** có tham số cost đủ mạnh theo chính sách hiện hành. Không lưu password plaintext, không dùng equals trên mật khẩu đầu vào so với chuỗi trong database, không tự viết crypto.

Một minh họa xác thực ở mức API:

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;

final class PasswordVerifier {
    private final PasswordEncoder encoder;

    PasswordVerifier(PasswordEncoder encoder) {
        this.encoder = encoder;
    }

    boolean verify(String rawPassword, String storedHash) {
        return encoder.matches(rawPassword, storedHash);
    }
}
~~~

Ví dụ này **không phải AuthenticationProvider hoàn chỉnh**, không xử lý user-not-found timing hoặc account status. Trong ứng dụng thật, nên dùng **AuthenticationManager/Provider tích hợp** và PasswordEncoder được cấu hình đúng, đồng thời giữ sự khác biệt nội bộ khỏi public response.

### 8.5. Không “hạ cấp” lỗi provider để tránh lộ tài khoản

Giả sử database đang unavailable. Nếu backend biến mọi lỗi đó thành **BadCredentialsException**, frontend hiển thị thông báo “Sai mật khẩu” và có thể yêu cầu user nhập lại liên tục, gây khóa tài khoản hoặc mất dữ liệu.

Nên có **mã lỗi dịch vụ công khai** như SERVICE_UNAVAILABLE, không nêu tên database, endpoint IdP, stack trace hoặc lỗi của user cụ thể. Phân biệt **sự cố xác thực không thể kiểm tra** với **credential đã được xác minh là sai** là cần thiết để vận hành đúng.

### 8.6. MFA, account lock và chi phí phòng vệ

Một cơ chế khóa account theo nhiều lần thử sai có thể giúp chống brute-force, nhưng cũng có thể bị lạm dụng để **khóa tài khoản người dùng thật** hoặc tạo enumeration oracle qua khác biệt status.

Các biện pháp cân bằng:

- Rate limit theo **nhiều tín hiệu** (IP, device, session, identifier được chuẩn hóa, rủi ro) và kế hoạch chống distributed attacks.
- Không trả “tài khoản này đã bị khóa” khi chỉ biết identifier chưa xác thực nếu chính sách riêng tư yêu cầu che.
- Thiết kế challenge/step-up hoặc xác minh bằng kênh sở hữu để giảm ảnh hưởng người dùng thật.
- Không cho phép attacker gây khóa account vô hạn mà không có cơ chế phục hồi và giám sát.
- Không lưu/hiển thị **số lần thất bại của một tài khoản cụ thể** trước khi người gửi chứng minh quyền sở hữu.
- Không coi MFA hoặc CAPTCHA là thay thế cho generic failure messages và xác minh credential.

## 9. CSRF, session và browser: đừng chẩn đoán nhầm login failure

Trong ứng dụng dùng cookie/session, POST /login là **hành động thay đổi trạng thái xác thực**. Ngay cả browser chưa đăng nhập vẫn cần CSRF token theo mô hình form login được bảo vệ.

### 9.1. GET /login và POST /login

~~~text
GET /login
  → Trang login có thể cấp CSRF token cho anonymous session

POST /login + token
  → CsrfFilter xác minh request
  → AuthenticationProvider xác minh credential/account
  → AuthenticationFailureHandler khi credential sai
     hoặc authentication success + session strategy khi hợp lệ
~~~

Một POST thiếu CSRF token bị từ chối **trước** khi password được đánh giá. Vì thế 403 do CSRF không phải một mẫu account enumeration nếu mọi username đều cùng bị chặn; đồng thời ứng dụng vẫn nên có thông báo thích hợp cho user để tải lại form.

### 9.2. Không dùng CORS làm bộ lọc xác thực

- **Same-Origin Policy (SOP)** giới hạn JavaScript đọc dữ liệu cross-origin trong browser.
- **CORS** là chính sách server cho JavaScript thuộc origin nào đọc response cross-origin và gửi một số request được browser kiểm soát.
- **CSRF token** xác minh request unsafe từ browser dùng credential tự gửi theo repository.
- **Authentication** quyết định principal.
- **Authorization** quyết định quyền trên tài nguyên.

CORS **không ngăn mọi form POST**, không chặn HTTP client trực tiếp, và không xác minh mật khẩu. Tương tự, việc trả **Access-Control-Allow-Origin** chính xác không có nghĩa login error response đã không tiết lộ account existence cho origin được cho phép hoặc HTTP client ngoài browser.

### 9.3. Cookie và nhiều tab

Cookie session nên được thiết kế với **Secure, HttpOnly, SameSite và Path/Domain** phù hợp. Dùng tiền tố **__Host-** nếu điều kiện Secure, Path=/ và không có Domain được đáp ứng:

~~~http
Set-Cookie: __Host-APPSESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie Secure/HttpOnly hỗ trợ bảo vệ session, không giải quyết trực tiếp enumeration. Một tab có thể login/logout và đổi session cookie trong khi tab khác vẫn giữ UI state cũ. Sau login thành công, CSRF token cũ có thể bị xóa/rotate; frontend cần lấy token mới trước POST nghiệp vụ.

Không xóa một authenticated session đang hoạt động chỉ vì **một request lỗi credential** không rõ nguồn mà chưa xác định chính sách; nếu endpoint đổi tài khoản hoặc reauthentication, cần mô hình state transition và CSRF/session rõ ràng.

### 9.4. Lưu ý với lỗi 403, 401 và redirect

| Browser thấy | Có thể là | Không nên làm |
| --- | --- | --- |
| 403 trước request tới provider. | Thiếu/sai CSRF token. | Tắt CSRF toàn site. |
| 401 JSON khi credential sai. | AuthenticationFailureHandler của API. | Trả exception chi tiết theo account. |
| 302 tới /login?error. | Form login thất bại theo HTML contract. | Dùng query account status khác nhau. |
| 401 từ /api/me sau login attempt. | Chưa có authenticated session hoặc cookie không gửi. | Suy rằng email không tồn tại. |
| OPTIONS /login 401/403. | Preflight bị CORS/auth/gateway chặn. | Ép cookie vào OPTIONS hoặc bỏ kiểm tra credential. |
| Fetch báo CORS error. | Browser không được đọc response. | Kết luận server chưa xử lý request hoặc tự retry liên tục. |
| Login success nhưng POST tiếp theo 403. | CSRF token trước login đã bị xóa. | Đưa token cũ vào localStorage để dùng mãi. |

### 9.5. Cơ chế cookie/CSRF repository khi dùng SPA

Nếu SPA dùng **HttpSessionCsrfTokenRepository**, một endpoint GET /csrf trả token cho browser có credentials là một cách. Nếu dùng **CookieCsrfTokenRepository** và JavaScript đọc cookie XSRF-TOKEN, cần chú ý **raw token vs XOR-masked token** trong Spring Security 6; request handler phải phù hợp kiểu token mà frontend gửi.

**Không bật HttpOnly=false cho session cookie chỉ vì frontend cần CSRF token.** Một CSRF cookie dành cho JavaScript và session ID cookie có vai trò bảo mật khác nhau.

## 10. Password reset, registration và invitation: account enumeration không dừng ở /login

Một sản phẩm có thông báo login tổng quát nhưng **/forgot-password**, **/register** hoặc **/invitation/status** trả lời khác nhau theo account existence vẫn có thể bị dò danh sách user.

### 10.1. Quên mật khẩu: cùng thông điệp cho mọi email hợp lệ

Một thiết kế dễ rò:

~~~text
POST /forgot-password với email không có
  → 404 "Tài khoản không tồn tại"

POST /forgot-password với email có
  → 200 "Đã gửi email đặt lại mật khẩu"
~~~

Một lựa chọn tốt hơn cho các yêu cầu **đúng định dạng**:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json; charset=UTF-8
Cache-Control: no-store

{"message":"Nếu địa chỉ này có thể sử dụng để khôi phục, hướng dẫn sẽ được gửi qua kênh đã đăng ký."}
~~~

Không có nghĩa server phải gửi email đến một địa chỉ không có account. Server có thể chỉ gửi **liên kết khôi phục** đến địa chỉ đã được xác minh/đăng ký theo chính sách, nhưng **phản hồi public không cho biết trạng thái tồn tại**.

Tuy vậy, API phải chống spam/abuse, giới hạn tốc độ và theo dõi chi phí gửi email. Nếu với account tồn tại server **đồng bộ gửi email** trước khi trả response còn account không tồn tại trả ngay, cùng status/body vẫn có **timing leak**. Có thể thiết kế queue/async workflow và xử lý tương đồng phù hợp, nhưng không hứa bảo đảm constant time tuyệt đối.

### 10.2. Reset token không thay CSRF token

Một **password reset token** thường được gửi qua email hoặc kênh sở hữu, có thời hạn, ràng buộc mục đích và có thể dùng một lần. Nó **khác CSRF token** của form POST.

Khi user đang ở trang nhập mật khẩu mới:

- Kiểm tra reset token hợp lệ, còn hạn, đúng tài khoản và chưa được dùng.
- Không để reset token xuất hiện trong logs, analytics, Referer hoặc URL chia sẻ.
- Kiểm tra mật khẩu mới theo chính sách và dùng PasswordEncoder an toàn.
- Quyết định có thu hồi session/refresh token cũ sau password reset hay không.
- Nếu form sử dụng session/cookie có thể tự gửi, đánh giá **CSRF** độc lập với reset token.
- Không lộ việc một identifier tồn tại qua reset token error response nếu yêu cầu riêng tư đòi che.

Một đường reset link có secret trong URL đôi khi là một phần giao thức recovery, nhưng phải giảm rò rỉ qua Referrer-Policy, cache, logs, analytics và cơ chế đổi sang một phiên reset an toàn; không cho token lan sang website thứ ba.

### 10.3. Registration và email đã tồn tại

Đăng ký thường muốn báo “Email đã được sử dụng”, tạo thuận lợi cho user thật nhưng cũng có thể giúp người ngoài xác minh tư cách thành viên.

Có nhiều lựa chọn cần cân nhắc theo sản phẩm:

| Thiết kế | Ưu điểm | Đánh đổi/rủi ro |
| --- | --- | --- |
| **Thông báo tồn tại ngay** | UX đơn giản. | Cho phép enumeration; không phù hợp dịch vụ nhạy cảm. |
| **Luôn nhận yêu cầu, xác minh qua email** | Hạn chế tiết lộ trước khi người gửi chứng minh quyền với email. | UX phức tạp hơn, cần rate limit/anti-spam. |
| **Chuyển sang luồng “đăng ký hoặc đăng nhập” chung** | Có thể giảm phản hồi phân nhánh. | Phải quản lý token, account linking và session correlation. |
| **Dịch vụ thành viên công khai** | Việc tồn tại account có thể vốn đã công khai. | Vẫn không nên lộ status nhạy cảm, MFA, email recovery hay credential. |

**Không thể che mọi thông tin về sự tồn tại** trong một sản phẩm công khai hồ sơ người dùng; quyết định cần dựa trên threat model, nghĩa vụ riêng tư và UX. Nhưng việc một profile công khai tồn tại không cấp quyền tiết lộ **mật khẩu có sai hay không, account bị khóa hay đang dùng SSO nào**.

### 10.4. Invitation, magic link và passwordless login

Một endpoint như:

~~~text
POST /invite/lookup?email=person@example.test
~~~

nếu trả “Có lời mời vào tổ chức X” cho bất kỳ ai biết email thì có thể tiết lộ quan hệ giữa cá nhân và doanh nghiệp.

Với **magic link/passwordless login**, phản hồi ban đầu nên tránh phân biệt email có account hay không, nếu chính sách bảo mật yêu cầu. Link/token phải:

- Có thời hạn, mục đích rõ và phạm vi sử dụng được kiểm soát.
- Được chuyển qua kênh sở hữu đã xác minh; không trả token trong response công khai.
- Chống replay/đăng nhập nhầm browser khi giao thức yêu cầu correlation.
- Không được sử dụng cho tài khoản khác chỉ vì email/username do client khai.
- Có rate limiting và kiểm soát gửi email/SMS.
- Không tiết lộ phone/email đầy đủ trên UI chưa xác thực.

### 10.5. Account linking có thể tạo rò rỉ tinh vi

Người dùng đăng nhập qua social provider và hệ thống nhận email đã tồn tại ở một local account. Nếu phản hồi là:

> Email này đã có tài khoản mật khẩu, hãy đăng nhập bằng mật khẩu để liên kết.

thì trong một số flow, thông điệp có thể cho biết **email có account tại ứng dụng** cho một bên chưa chứng minh quyền sở hữu email đó.

Cần phân biệt email **đã được provider xác minh**, mức tin cậy của claim, account linking consent, user session hiện tại và chính sách xác thực lại. Chỉ thực hiện link tài khoản sau khi các điều kiện này được xác minh, không tự ghép account vì string email trùng nhau.

## 11. SSO/OAuth2/OIDC, MFA và các trạng thái nhạy cảm

### 11.1. Login liên kết cũng có failure response

Trong **OAuth2/OIDC login**, lỗi có thể xảy ra khi:

- **state** không khớp authorization request đang chờ.
- Authorization code hết hạn, đã dùng hoặc bị tráo.
- **PKCE** không khớp.
- **ID token** có issuer/audience/chữ ký/nonce không hợp lệ.
- Provider tạm thời lỗi.
- Người dùng tại IdP không đáp ứng policy ứng dụng.
- Account mapping/linking bị từ chối.

Không trả toàn bộ error_description, raw token, email, subject ID, tenant hoặc provider diagnostic ra redirect tới browser.

Một thông điệp public có thể là:

> Không thể hoàn tất đăng nhập qua nhà cung cấp đã chọn. Vui lòng thử lại hoặc liên hệ hỗ trợ.

Kết quả nội bộ cần xác định chính xác flow lỗi để phục vụ điều tra. **Không che lỗi giao thức bằng cách bỏ kiểm tra state, PKCE, nonce, issuer hoặc audience** chỉ để user login thành công.

### 11.2. CSRF trong OAuth2 login khác một form POST

Với form username/password dùng session, **CSRF token** gắn request login với luồng hợp lệ. Với OAuth2 Authorization Code Flow, **state** liên kết callback với authorization request do client/browser khởi tạo; **PKCE** ràng buộc code với verifier, còn **nonce** được dùng trong điều kiện OIDC tương ứng.

Không dùng OAuth2 state để thay CSRF token cho POST nghiệp vụ, cũng không yêu cầu một CSRF form token tùy ý cho mọi callback GET nếu giao thức đang dùng state/correlation đúng cách.

Nếu IdP sử dụng **form_post response mode**, phải phân tích riêng SameSite cookie, endpoint callback POST, CSRF matcher và giao thức xác minh. Chỉ cân nhắc ngoại lệ CSRF hẹp cho callback giao thức **đã được bảo vệ bằng state/token validation**, không tắt CSRF toàn site.

### 11.3. Khi nào có thể tiết lộ MFA step?

Một response nói **“Tài khoản X đã bật MFA qua số điện thoại kết thúc 1234”** ngay khi chỉ nhận username là một dạng disclosure về account và số điện thoại.

Nếu user đã **chứng minh password factor** hoặc hoàn thành bước định danh đáng tin khác, ứng dụng có thể điều hướng sang MFA challenge cụ thể theo policy. Nhưng:

- Chưa hoàn tất MFA thì chưa nên cấp phiên/quyền hoàn chỉnh.
- Không trả secret TOTP, recovery code hoặc credential factor trong client response.
- Không cho client tự khai “mfaVerified=true” để vượt qua bước thứ hai.
- Giao diện lỗi ở giai đoạn đầu vẫn không nên lộ account có MFA hay không.
- Không gợi ý số điện thoại/email phục hồi quá chi tiết trước khi chứng minh quyền.
- Có chống brute force/abuse trên OTP và recovery flows riêng.

### 11.4. Account locked/disabled: khác biệt vận hành và riêng tư

Đội hỗ trợ đôi khi muốn thông báo chính xác “Tài khoản bị khóa”. Việc công khai thông tin này cho bất kỳ ai nhập email có thể cho phép enumeration.

Một chiến lược:

1. Trước khi người gửi chứng minh quyền sở hữu, hiển thị thông điệp **không thể đăng nhập** chung.
2. Nếu tài khoản bị hạn chế, gửi hướng dẫn qua **kênh đã được xác minh** khi hợp lệ và không tạo spam.
3. Sau bước xác minh mạnh hoặc trong dashboard đã authenticated, có thể hiển thị trạng thái cụ thể theo nhu cầu.
4. Audit nội bộ giữ nguyên lý do để vận hành; hạn chế quyền xem, không in ra client.
5. Không dùng khóa account làm hình phạt có thể bị người ngoài kích hoạt vô hạn mà không có quy trình khôi phục.

### 11.5. Một danh sách IdP hoặc tenant cũng có thể nhạy cảm

Một trang nhập email rồi tự động nói “Bạn phải dùng SSO của Công ty Y” tiết lộ có thể **email thuộc tenant hoặc công ty nào**. Trong hệ thống enterprise, **home realm discovery** có lợi cho UX nhưng cần đánh giá riêng tư.

Tùy sản phẩm, có thể:

- Chỉ hiển thị lựa chọn IdP sau khi người dùng kiểm chứng một kênh sở hữu hoặc được tổ chức xác định qua context đáng tin.
- Dùng domain-based routing khi danh tính doanh nghiệp vốn công khai và rủi ro được chấp nhận.
- Không dùng tổ chức/tenant lookup làm quyền truy cập hệ thống.
- Giới hạn query, audit và tránh nêu membership chi tiết cho người chưa xác thực.

## 12. Rate limiting, bot protection và logging không làm lộ danh tính

Thông điệp chung chỉ là một lớp. Endpoint login còn cần quản lý lưu lượng, chống brute-force và audit, nhưng phải tránh biến chính những cơ chế đó thành nguồn rò thông tin.

### 12.1. Rate limiting nhiều chiều

| Tín hiệu | Giá trị | Rủi ro nếu dùng đơn độc |
| --- | --- | --- |
| **Client IP** | Chặn một nguồn thử nhiều request. | NAT/shared IP và botnet làm sai lệch; proxy header có thể bị giả. |
| **Username/email đã chuẩn hóa** | Phát hiện password spraying vào cùng account. | Trả throttle riêng cho user tồn tại tạo enumeration/DoS. |
| **Browser/session/device signal** | Liên kết những lần thử có chung ngữ cảnh. | Có thể bị xóa/đổi và liên quan riêng tư. |
| **Network/ASN/risk score** | Phân loại lưu lượng bất thường. | False positive, khó giải thích và cần quản lý dữ liệu. |
| **Global/concurrency limits** | Bảo vệ auth service khỏi quá tải. | Có thể ảnh hưởng người dùng hợp lệ toàn hệ thống. |
| **Identity provider limits** | Bảo vệ upstream IdP/API. | Phản hồi lỗi provider có thể khác biệt theo tenant/account. |

Một ứng dụng nên có **đường phục hồi cho user thật**, chống dùng lockout làm công cụ tấn công từ chối dịch vụ, và kiểm soát false positives. Các tín hiệu phải được đo/giám sát chứ không đặt ngưỡng tùy tiện rồi bỏ mặc.

### 12.2. Trả 429 mà không tiết lộ account tồn tại

Một mẫu dễ lộ:

~~~text
Nếu username có tài khoản và số lần sai cao → 429
Nếu username không có tài khoản             → 401
~~~

Người ngoài có thể lợi dụng 429 như một **oracle account existence**.

Chính sách tốt hơn cần xem xét throttle theo **nguồn request, identifier được chuẩn hóa và rủi ro độc lập**, với public response không xác nhận account tồn tại. Không có một thuật toán duy nhất phù hợp mọi sản phẩm, nhưng các ngưỡng và phản hồi phải được kiểm thử đối xứng với user có/không có account.

Nếu trả **Retry-After**, bảo đảm giá trị không vô tình để lộ trạng thái khóa của một account cụ thể.

### 12.3. CAPTCHA và challenge cũng là một kênh phụ

Nếu CAPTCHA chỉ xuất hiện khi email đã đăng ký hoặc khi số lần login sai của user có thật đạt ngưỡng, người ngoài có thể đoán account existence.

Khi cần CAPTCHA/challenge, đánh giá trigger dựa trên **rủi ro request hoặc nguồn lưu lượng**, kết hợp các tín hiệu được phép; tránh khiến phản hồi công khai khác biệt chỉ vì account có/không tồn tại. Không coi CAPTCHA là giải pháp thay CSRF, PasswordEncoder hoặc MFA.

### 12.4. Logging: đủ chẩn đoán nhưng không để lộ secrets

Một bản ghi audit có thể chứa:

~~~json
{
  "event": "AUTHENTICATION_FAILED",
  "resultCategory": "BAD_CREDENTIALS",
  "requestId": "test-request-id-42",
  "loginChannel": "FORM",
  "originCategory": "SAME_ORIGIN",
  "timestamp": "2026-11-26T08:00:00Z"
}
~~~

Đây là **mẫu cấu trúc**, không phải log từ hệ thống thật. Có thể giữ loại lỗi nội bộ để hỗ trợ vận hành; cần kiểm soát RBAC, masking, retention và các yêu cầu bảo vệ dữ liệu cá nhân.

**Không log**:

- Password, OTP, recovery code hoặc secret xác thực.
- Session ID, CSRF token, Bearer/refresh token đầy đủ.
- Raw Authorization, Cookie, Set-Cookie headers.
- URL reset password kèm token hoặc OAuth authorization code.
- Stack trace có dữ liệu nhạy cảm trên hệ thống logs không bảo vệ.
- Username/email plaintext khi không thật sự cần phục vụ điều tra và không có cơ sở xử lý dữ liệu phù hợp.

Nếu cần tương quan những lần thử theo identifier mà giảm lưu plaintext, có thể cân nhắc **HMAC có secret được bảo vệ** trên identifier đã chuẩn hóa, quản lý vòng đời key và giới hạn truy cập. **Hash thường không có secret** của một tập email có thể đoán được không tự bảo đảm ẩn danh.

### 12.5. Spring Security authentication events

Spring Security có cơ chế phát các **authentication success/failure events** trong những cấu hình thích hợp. Ứng dụng có thể dùng các event này để đo tỷ lệ thất bại, phát hiện xu hướng và kết nối hệ thống audit.

Không gửi nguyên AuthenticationException hoặc Authentication object vào analytics bên thứ ba; chúng có thể chứa principal metadata hoặc chi tiết provider. Chỉ map sang một **schema audit hạn chế**, và tránh double-counting nếu failure handler và listener cùng ghi sự kiện.

### 12.6. IP thực sau reverse proxy

Tại production:

~~~text
Browser → CDN/WAF → Reverse proxy → Spring Security
~~~

Một client ngoài có thể tự đặt **X-Forwarded-For, Forwarded hoặc X-Real-IP** trong request. Nếu backend tin mù quáng, attacker có thể né rate limiting, giả IP người khác hoặc làm hỏng audit.

Thiết lập **trusted proxy chain**, loại bỏ/ghi đè forwarded headers do client có thể tự khai và xác lập host/scheme/IP từ tầng tin cậy. Spring Boot forwarding config **không tự chứng minh proxy là trusted**; phải có kiểm soát đường mạng/edge.

### 12.7. Monitoring cần nhìn failure rate nhưng không công khai identity

Dashboard cho đội vận hành có thể tổng hợp:

- Tỷ lệ failed login theo endpoint/đường xác thực/phiên bản triển khai.
- 401/403/429/5xx theo thời gian và khu vực, không cần liệt kê email người dùng.
- CSRF failures trên POST /login, CORS preflight rejects.
- Password spraying/credential stuffing indicators theo mức độ rủi ro.
- Thời gian phụ thuộc UserDetailsService/IdP, độ trễ password hash và rate limiting.
- Tỷ lệ user thật hoàn thành recovery/MFA sau lỗi.

Các chỉ số cụ thể ở mức account cần quyền kiểm soát truy cập và chính sách bảo vệ dữ liệu; dashboard public hoặc dashboard vendor không nên chứa danh sách identifier tùy ý.

## 13. Kiểm thử Servlet: cùng kết quả công khai cho user không có và mật khẩu sai

Mục tiêu của kiểm thử là **không để sự tồn tại của account làm thay đổi phản hồi công khai trong cùng loại login failure**. Các kịch bản phải giữ đủ CSRF token và đi qua authentication provider để tránh so sánh nhầm 403 của CsrfFilter.

### 13.1. Ma trận so sánh cần có

| Trường hợp | Credential / trạng thái | Phản hồi công khai kỳ vọng |
| --- | --- | --- |
| A | Email đúng định dạng, **không có account**. | LOGIN_FAILED chung, 401 JSON hoặc redirect lỗi chung. |
| B | Email có account, **mật khẩu sai**. | Cùng lớp response với A. |
| C | Account **disabled** nhưng người gửi chưa chứng minh quyền sở hữu. | Không tiết lộ account status qua response công khai theo policy. |
| D | Account **locked**, credential chưa đủ xác minh. | Không biến locked thành public oracle. |
| E | User hợp lệ + mật khẩu đúng. | Thành công theo flow, tạo đúng authenticated principal. |
| F | Thiếu/sai CSRF token. | Bị CsrfFilter từ chối; không kiểm tra credential và không đổi principal. |
| G | Identity store tạm thời không khả dụng. | Lỗi dịch vụ an toàn, không giả credential sai. |
| H | Quá nhiều request theo chính sách. | Throttle không phân biệt account existence vô ý. |
| I | Request JSON tới formLogin mặc định. | Xử lý đúng hợp đồng form parameters hoặc trả request error an toàn. |

Các case A–D nên so sánh **status/code/body/headers/redirect**, kết hợp kiểm tra timing và rate limiting. Case E khác kết quả vì user đã chứng minh đúng credential — đây không phải thông tin cần che bằng cách từ chối cả đăng nhập hợp lệ.

### 13.2. MockMvc: account không tồn tại và password sai

Với Spring Security Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class PublicLoginFailureMvcTest {

    @Autowired
    MockMvc mvc;

    private MvcResult failedLogin(String username) throws Exception {
        return mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", "definitely-wrong-test-password"))
            .andReturn();
    }

    @Test
    void unknownAccountAndWrongPasswordHaveSamePublicResponse()
            throws Exception {

        // User test known@example.test đã tồn tại theo fixture.
        MvcResult unknown = failedLogin("nobody@example.test");
        MvcResult wrongPassword = failedLogin("known@example.test");

        assertEquals(401, unknown.getResponse().getStatus());
        assertEquals(401, wrongPassword.getResponse().getStatus());

        assertEquals(
                unknown.getResponse().getContentAsString(),
                wrongPassword.getResponse().getContentAsString());

        assertEquals(
                unknown.getResponse().getContentType(),
                wrongPassword.getResponse().getContentType());

        assertEquals(
                unknown.getResponse().getHeader("Cache-Control"),
                wrongPassword.getResponse().getHeader("Cache-Control"));

        assertFalse(unknown.getResponse().getContentAsString()
                .contains("UsernameNotFoundException"));
    }
}
~~~

**Giả định:** Test application sử dụng **JsonLoginFailureHandler** ở mục 6, có account fixture **known@example.test**, mật khẩu trong test luôn sai và không áp dụng throttle khác nhau giữa hai request. Nếu ứng dụng dùng **formLogin HTML redirect**, đổi phép kiểm tra thành so status/Location và **HTML trang login cuối** cho cùng loại credential failure.

Test này kiểm tra phản hồi cơ bản nhưng **không chứng minh không có timing side channel, enumeration qua password reset hoặc account-based throttle**. Cần test bổ sung.

### 13.3. Test status CSRF riêng biệt

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// Trong lớp test đã cấu hình MockMvc:
mvc.perform(post("/login")
        .param("username", "known@example.test")
        .param("password", "test-secret"))
    .andExpect(status().isForbidden());

mvc.perform(post("/login")
        .with(csrf().useInvalidToken())
        .param("username", "known@example.test")
        .param("password", "test-secret"))
    .andExpect(status().isForbidden());
~~~

Ngay cả khi credential test đúng, **CSRF token thiếu/sai phải không tạo authenticated principal** trong session-based form login. Khi formLogin trả JSON 401 cho credential sai, test 403 ở đây xác nhận phân biệt **request protection** với **authentication failure**.

### 13.4. Test locked/disabled account không rò qua response

Tạo fixture **locked@example.test** hoặc **disabled@example.test** trong môi trường test, rồi thử login với credential không đủ quyền sở hữu theo policy. So sánh:

- HTTP status và Content-Type.
- Public error code/message.
- Location redirect.
- Headers như WWW-Authenticate, Cache-Control hoặc custom error headers.
- Kích thước body, DOM hiển thị và những trường JSON phụ.
- Không có stack trace, exception type hay account status trong response.
- Không thay đổi authenticated principal hoặc mở session có quyền.

Đồng thời xác minh provider vẫn **không cho account bị khóa/vô hiệu hóa đăng nhập**. Thông báo chung không được biến thành một cách bỏ qua account status.

### 13.5. Test credential đúng là điều kiện riêng

Một user test có mật khẩu đúng phải vượt authentication policy và nhận session/quyền theo cấu hình, không bị hệ thống “che sự tồn tại” đến mức mọi lần login đều trả lỗi chung.

Nếu có MFA, thành công ở bước password có thể đưa người dùng vào **MFA pending state** chứ chưa cấp quyền ứng dụng đầy đủ. Cần test rằng API nhạy cảm vẫn bị chặn đến khi yếu tố bổ sung được kiểm tra.

### 13.6. Kiểm thử login failure không làm lộ credential trong logs

Dùng logging test appender hoặc hệ thống quan sát staging có kiểm soát để xác minh:

- Password, OTP, session ID và CSRF token không xuất hiện dưới dạng đầy đủ.
- Request body của POST /login không bị log nguyên văn ở proxy/WAF/gateway.
- Exception loại ACCOUNT_LOCKED nếu cần audit chỉ nằm trong kênh được phân quyền, không nằm trong public response.
- Authentication event không tạo nhiều bản ghi trùng nhau hoặc đính kèm raw principal credential.
- Logs có request/correlation ID để điều tra nhưng ID không encode identifier hoặc account status.

## 14. Kiểm thử WebFlux và kiểm thử browser end-to-end

### 14.1. WebTestClient: hai credential failure phải cùng public code

Với SecurityWebFilterChain và ReactiveJsonLoginFailureHandler đã cấu hình:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

// webTestClient đã bind vào WebFlux application test.
// Test account known@example.test có tồn tại theo fixture.

webTestClient
    .mutateWith(csrf())
    .post().uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
            "username", "nobody@example.test")
            .with("password", "wrong-test-password"))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectBody()
    .jsonPath("$.code").isEqualTo("LOGIN_FAILED");

webTestClient
    .mutateWith(csrf())
    .post().uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
            "username", "known@example.test")
            .with("password", "wrong-test-password"))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectBody()
    .jsonPath("$.code").isEqualTo("LOGIN_FAILED");
~~~

Đây là **đoạn test minh họa**, không phải một lớp test hoàn chỉnh. Nó giả định WebFlux formLogin nhận form data và handler trả JSON 401. Kiểm thử schema/body đồng nhất cần bổ sung đối chiếu **headers và response full body** bằng cách thu kết quả response và so sánh, không chỉ JSONPath code.

**WebTestClient.mutateWith(csrf())** là tiện ích của spring-security-test; nó **không tự mô phỏng browser cookie/CORS/CSRF lifecycle đầy đủ**. Cần test tích hợp với cookie jar/WebSession qua nhiều request để xác minh session và token.

### 14.2. Điều kiện browser để test đúng lớp

Ví dụ frontend tại https://app.example.com gọi backend tại https://api.example.com.

Trong DevTools:

1. Mở **Network**, chọn Preserve log để thấy **OPTIONS, POST và redirects**.
2. Quan sát GET /csrf có hợp lệ, response actual có CORS/Cache-Control phù hợp.
3. Gửi login với một identifier không tồn tại, password giả; lưu status, body, headers, Location và thời gian.
4. Gửi login với một account test tồn tại nhưng password sai; so phản hồi công khai.
5. Kiểm tra hiển thị UI đúng message, không có account status/exception trong DOM.
6. Xem Cookie/Set-Cookie và lý do browser chặn cookie nếu có.
7. Thử password reset/registration/MFA discovery theo cùng nguyên tắc account existence.
8. Quan sát proxy/gateway không log password hoặc field nhạy cảm.
9. Với request thành công, gọi GET /api/me để xác nhận principal và session.
10. Kiểm tra logout xóa session/credential theo policy, không dựa vào UI hiện ra.

**Không dùng credential của người khác hoặc account production không được phép**. Việc kiểm thử side channel nên thực hiện trên staging hoặc môi trường được chủ sở hữu hệ thống phê duyệt với mức lưu lượng giới hạn.

### 14.3. Bảng kiểm soát dấu hiệu rò rỉ trong DevTools

| DevTools khu vực | Quan sát | Cảnh báo |
| --- | --- | --- |
| **Network → Status** | 401/403/302/429/5xx theo lớp lỗi. | User có/không có account nhận status khác nhau trong cùng loại credential failure. |
| **Network → Headers** | Location, Cache-Control, custom error headers, Set-Cookie. | Header hoặc redirect chứa trạng thái account/email. |
| **Network → Response** | JSON/HTML cuối cùng, content length. | Message hoặc error code nội bộ khác nhau theo account. |
| **Network → Timing** | Latency các request test tương đương. | Account không tồn tại luôn nhanh hơn rõ rệt. |
| **Application → Cookies** | Session/CSRF cookies, Domain, Path, Secure, SameSite. | Cookie sai scope dẫn đến lỗi 403 bị nhầm thành credential failure. |
| **Console** | CSP/CORS/Mixed Content logs. | Login thất bại do browser policy nhưng bị hiển thị như email chưa đăng ký. |
| **Sources/DOM** | Error message render và data attributes. | Frontend giấu trạng thái account bằng CSS nhưng vẫn chứa trong DOM. |
| **Network → Initiator** | Form submit/XHR/redirect chain. | Auto retry sai credential hoặc gửi nhiều lần không chủ ý. |

### 14.4. curl có thể kiểm tra response nhưng không mô phỏng toàn bộ browser

Trong môi trường kiểm thử bạn sở hữu:

~~~bash
# Chỉ mô phỏng preflight tới endpoint login của SPA.
curl -i -X OPTIONS "https://api.example.com/login" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Để kiểm tra **lỗi credential thật**, cần một **CSRF token/cookie jar hợp lệ** theo backend, không phải tự gửi POST thiếu token rồi nhìn response 403. Test harness có thể giữ cookie jar xuyên qua GET /csrf và POST /login.

**curl không thực thi SOP, CORS, SameSite hoặc CSP như browser**. Nó có thể tự đặt Origin/Sec-Fetch-Site, nên các header đó không xác thực người gửi đối với HTTP client ngoài browser.

### 14.5. Đo timing side channel với điều kiện kiểm soát

Một báo cáo kiểm thử nên ghi:

- Loại UserDetailsService/AuthenticationProvider và PasswordEncoder đang dùng.
- Môi trường/phiên bản/instance được đo, trạng thái warm-up và tải nền.
- Số lượng request **có giới hạn**, thứ tự thử nghiệm được hoán đổi hợp lý.
- Latency phân phối cho user không tồn tại so với account test có mật khẩu sai.
- Có bị rate limit, CAPTCHA, session invalidation hoặc cache ảnh hưởng không.
- Có nhánh service riêng theo tenant/IdP/record status không.
- Biện pháp cải thiện: bỏ early return bất thường, dùng provider chuẩn, tối ưu session store, xử lý rate limiting công bằng.
- Tác động đến user thật và server khi thay đổi chi phí password hash hoặc delay.

Một câu “chúng tôi thêm sleep 100 ms” không đủ chứng minh an toàn; cần xem dữ liệu thử nghiệm và threat model tổng thể.

### 14.6. Test hồi quy sau khi thay AuthenticationProvider

Khi thay từ local user store sang LDAP, SAML, OIDC hoặc custom service, kiểm thử cũ có thể chỉ bắt username/password errors mà không bao phủ thông điệp lỗi từ provider mới.

Cần bổ sung test cho:

- Provider unreachable/timeout.
- User not mapped, inactive, not authorized for tenant.
- MFA pending/cancelled.
- State/nonce/PKCE mismatch ở OIDC callback.
- SSO linking conflict.
- Account deactivated sau khi user có session.
- Password expiration hoặc forced reauthentication.
- Proxy/CORS errors trong callback/redirect.
- Localization sang ngôn ngữ mới.

Không đưa **raw error_description** từ IdP vào HTML hay JSON của ứng dụng cho browser chưa xác thực.


## 15. Chẩn đoán lỗi đăng nhập mà không mở thêm kênh tiết lộ

Một lỗi login có thể bắt nguồn từ **authentication**, **CSRF**, **CORS**, **CSP**, **cookie/session**, **IdP**, **proxy** hoặc **rate limiting**. Chẩn đoán đúng tầng vừa giúp sửa lỗi nhanh hơn, vừa tránh việc “chữa” bằng cách mở rộng các chính sách bảo mật.

### 15.1. Bảng triệu chứng và cách điều tra

| Triệu chứng | Lớp cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Email không có trả 404, email có mật khẩu sai trả 401. | Public failure mapping. | Thống nhất lỗi credential công khai, không phân biệt account existence. |
| Cùng message nhưng code JSON khác nhau. | API error schema. | Gộp public code cho credential/status cần ẩn. |
| Cùng body nhưng redirect khác nhau. | FormLogin failureUrl/handler. | Dùng đích lỗi chung; không đưa username/reason vào Location. |
| Tài khoản có luôn mất nhiều thời gian hơn. | UserDetailsService, PasswordEncoder, cache. | Kiểm tra early return và đường password verification, đo thống kê. |
| 429 chỉ xuất hiện với user có thật. | Rate limiting/lockout policy. | Thiết kế throttle không tạo account oracle. |
| CAPTCHA chỉ xuất hiện với email đã đăng ký. | Bot/risk challenge. | Đánh giá trigger theo rủi ro request, không chỉ existence. |
| POST /login với mật khẩu đúng trả 403. | CsrfFilter, session/token repository. | Kiểm tra CSRF trước khi quy thành lỗi credential. |
| SPA /csrf trả 401 trước login. | Authorization matcher. | Cho anonymous nhận token hợp lệ, giữ CSRF cho POST login. |
| OPTIONS /login bị 401, POST không xuất hiện. | CORS/preflight/gateway. | CORS trước auth, đúng allowed origins/methods/headers. |
| Login POST được xử lý nhưng frontend báo CORS. | Actual response CORS/redirect. | Xem Network response thực và session state. |
| POST trả 302 đến trang login rồi final 200 HTML. | Form login redirect vs SPA fetch. | Thống nhất 204/401 contract hoặc xử lý redirect đúng. |
| Login thành công nhưng POST nghiệp vụ sau đó 403. | Token CSRF cũ sau authentication. | Lấy token mới, kiểm tra principal/quyền. |
| Tên user hiện trong query string lỗi. | Redirect/log/history/Referrer. | Không đưa identifier vào Location/URL lỗi. |
| Form lỗi xuất hiện HTML/JS không mong muốn. | Output encoding/XSS. | Escape dữ liệu, dùng template safe output, CSP. |
| Forgot-password dùng 200/404 theo email. | Recovery enumeration. | Public response chung, gửi hướng dẫn qua kênh sở hữu. |
| Registration trả “email đã có” trên sản phẩm nhạy cảm. | Signup UX/privacy. | Chuyển sang email verification hoặc chấp nhận rủi ro có căn cứ. |
| OIDC error chứa email/issuer/token. | OAuth failure handler/callback. | Map sang lỗi công khai, log an toàn, giữ state/token validation. |
| User bị khóa nhưng UI vẫn cho đăng nhập. | AuthenticationProvider/account policy. | Giữ kiểm tra trạng thái nội bộ, chỉ tổng quát hóa thông điệp công khai. |
| Đăng nhập lại sai sau browser reload. | Cookie Secure/SameSite/Path, session store. | Network Cookies/Set-Cookie, session TTL và reverse proxy. |
| Lỗi chỉ có ở một server instance. | User/session/CSRF store không đồng nhất. | Kiểm tra repository dùng chung, cấu hình secrets/cache. |
| Auth service hỏng nhưng UI báo “Sai mật khẩu”. | Exception mapping hạ tầng. | Trả lỗi service chung, không giả credential mismatch. |
| Failed login được log nguyên request body. | Access/HTTP logging, WAF/APM. | Tắt/mask credential và header nhạy cảm. |
| Rate limit bị né bằng X-Forwarded-For. | Trusted proxy chain. | Làm sạch forwarded headers tại edge. |
| Trang đăng nhập bị nhúng từ site ngoài. | CSP frame-ancestors/X-Frame-Options. | Đặt policy trên response HTML login, không chỉ API JSON. |
| Login UI lỗi sau thêm CSP. | script-src/form-action/connect-src. | Kiểm tra policy của document HTML, nới theo allowlist thật. |

### 15.2. Chẩn đoán theo thứ tự

1. Xác định **origin, URL, method, content type và security chain** của request.
2. Kiểm tra browser có thực sự gửi POST hay bị CSP/CORS/Mixed Content chặn trước.
3. Với POST /login, xác định **CSRF token hợp lệ và cookie cùng phiên**; nếu không, lỗi chưa tới password validation.
4. Kiểm tra **AuthenticationFailureHandler/ServerAuthenticationFailureHandler** tạo response nào và có redirect hay không.
5. Đối chiếu **user không có** và **user có mật khẩu sai** trong môi trường test: status, body, public code, headers, Location.
6. Kiểm tra những nhánh khác: account locked/disabled, service outage, rate limit, MFA.
7. Đo timing và phân tích các thành phần ở môi trường test với lưu lượng hạn chế.
8. Kiểm tra frontend có vô tình render exception message hoặc tài khoản vào DOM/log/analytics.
9. Kiểm tra **password reset, registration, OIDC/SSO** có còn lộ account existence.
10. Dùng logs nội bộ có kiểm soát để xác định nguyên nhân, rồi sửa đúng tầng mà không nới rộng CSRF/CORS/auth.

### 15.3. HTTPS, HSTS và security headers trên HTML login

Một trang login nên dùng HTTPS và các header phòng vệ phù hợp:

~~~http
Strict-Transport-Security: max-age=31536000
Content-Security-Policy: default-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Cache-Control: no-store
~~~

**Đây là policy minh họa**, không phải copy nguyên vào mọi hệ thống. Nếu login page sử dụng script hoặc form action hợp lệ từ IdP/đối tác, phải xem xét chính sách tương ứng. **includeSubDomains** cho HSTS chỉ nên bật sau khi kiểm kê hỗ trợ HTTPS của mọi subdomain liên quan. HSTS bảo vệ đường truyền trong browser đã biết policy; nó **không giấu account existence** hay thay CSRF.

CSP phải gắn với **response document HTML của login/frontend**. Chỉ cấu hình CSP trên API JSON khác origin không tự bảo vệ trang HTML login.

### 15.4. HTTP firewall và parsing request

Spring Security HTTP firewall, reverse proxy hoặc WAF có thể từ chối request bất thường trước khi authentication provider chạy, ví dụ URL encoded bất thường, method không cho phép hoặc header sai cấu trúc. Điều đó **khác credential failure**, và không nên sửa bằng cách nới firewall vô điều kiện.

Nếu hai tầng xử lý đường dẫn/host/method không nhất quán, cần kiểm tra **HTTP request parsing, allowed path và proxy normalization**. Không dùng chính sách “chỉ cho frontend origin” hoặc “chỉ IP nội bộ” để thay AuthenticationManager.

### 15.5. Hỗ trợ người dùng khi không thể nói rõ account status

Một hướng dẫn hỗ trợ an toàn:

- Đề nghị user xác minh **địa chỉ trang chính thức** và kiểm tra thông tin đã nhập.
- Cho phép dùng **quên mật khẩu**, nhưng phản hồi reset không xác nhận email có account.
- Nếu hỗ trợ SSO, đưa đường dẫn tới **trang đăng nhập chính thức** hoặc chọn tổ chức theo context đáng tin.
- Khi tài khoản bị hạn chế, sử dụng **kênh đã xác minh** để cung cấp hướng dẫn chi tiết.
- Không yêu cầu người dùng gửi password, OTP, backup code hoặc session cookie cho đội hỗ trợ.
- Không yêu cầu screenshot có Authorization, Set-Cookie, reset link hoặc dữ liệu nhạy cảm.
- Nhân viên hỗ trợ không nên tiết lộ tình trạng tài khoản cho người chỉ cung cấp username/email.

Mục tiêu không phải che giấu mọi lỗi kỹ thuật khỏi user, mà là **cấp đúng lượng thông tin cho chủ thể đã được xác minh**.

## 16. Bài tập tình huống: giới hạn tiết lộ danh tính

### Tình huống A — Email không có, mật khẩu sai

POST /login với email không tồn tại trả “Email chưa đăng ký”; email đã đăng ký với mật khẩu sai trả “Sai mật khẩu”. Có vấn đề gì?

**Đáp án:** Đây là **account enumeration**. Người chưa xác thực có thể biết email tồn tại. Cần cùng một phản hồi public cho hai tình huống credential failure và giữ lý do chi tiết trong audit nội bộ được phân quyền.

### Tình huống B — Cùng câu chữ nhưng khác HTTP status

Backend trả thông báo “Không thể đăng nhập” cho cả hai trường hợp, nhưng status là 404 khi email không tồn tại và 401 khi password sai. Đã an toàn chưa?

**Đáp án:** Chưa. HTTP status vẫn là tín hiệu khác biệt. Phải kiểm tra cả **status, JSON code, body, headers và redirect**, không chỉ câu hiển thị.

### Tình huống C — JSON error code khác nhau

Một SPA chỉ hiển thị “Đăng nhập thất bại”, nhưng API trả UNKNOWN_USER cho email không có và INVALID_PASSWORD cho email có. Có còn lộ account không?

**Đáp án:** Có. Bất kỳ client hay người kiểm tra Network đều đọc được public code. Dùng **LOGIN_FAILED** chung khi chưa có bằng chứng sở hữu account.

### Tình huống D — Redirect chứa account status

Form login thất bại và redirect đến /login?reason=LOCKED nếu tài khoản bị khóa, /login?reason=BAD_PASSWORD nếu mật khẩu sai. Có an toàn nếu UI bỏ qua reason không?

**Đáp án:** Không. URL, Location header, history, logs và analytics vẫn tiết lộ trạng thái. Dùng redirect tới **một URL lỗi chung** như /login?error.

### Tình huống E — User-not-found trả rất nhanh

Custom AuthenticationProvider trả lỗi ngay khi không thấy user, nhưng kiểm tra BCrypt khi user có. Dù response body giống nhau, có thể bị dò không?

**Đáp án:** Có nguy cơ **timing enumeration**. Cần đánh giá đường password verification, sử dụng provider chuẩn và đo thống kê trong test; không dựa vào một lệnh sleep cố định làm biện pháp duy nhất.

### Tình huống F — Tất cả lỗi đều trả 401, kể cả database hỏng

Identity store không sẵn sàng nhưng backend luôn trả “Sai email hoặc mật khẩu” vì muốn giữ thông điệp chung. Có đúng không?

**Đáp án:** Không nên che lỗi hạ tầng thành credential sai. Có thể dùng **503 với thông điệp dịch vụ tổng quát**, không lộ database/stack trace, đồng thời không làm khác biệt theo account existence.

### Tình huống G — 429 chỉ khi user có thật

Rate limiter tăng counter trong account record. Với email có thật, lần thử thứ năm trả 429; với email không có, luôn 401. Rủi ro gì?

**Đáp án:** **429 trở thành account enumeration oracle**, còn attacker có thể gây khóa user thật. Cần rate limiting theo nhiều tín hiệu với phản hồi/throttle đã đánh giá công bằng và chống DoS.

### Tình huống H — CAPTCHA chỉ cho email đã đăng ký

UI hiện CAPTCHA nếu backend tìm thấy account, còn email không tồn tại không có CAPTCHA. Đây có phải rò rỉ dù message chung không?

**Đáp án:** Có. Challenge xuất hiện khác nhau là tín hiệu tồn tại. Cần đánh giá trigger dựa trên risk/request thay vì chỉ account existence.

### Tình huống I — Không có CSRF token, POST /login nhận 403

Một tester gửi email không tồn tại và email có mật khẩu sai tới POST /login, cả hai đều nhận 403. Tester kết luận chống enumeration hoàn hảo. Đúng không?

**Đáp án:** Không. Có thể cả hai bị **CsrfFilter từ chối trước authentication**, nên chưa thử được nhánh account lookup. Cần cấp token hợp lệ và giữ đúng session khi kiểm thử.

### Tình huống J — POST JSON tới formLogin mặc định

SPA gửi JSON username/password và nhận HTML trang login. Developer cho rằng điều này chứng minh không có account tương ứng. Hợp lý không?

**Đáp án:** Không. **formLogin mặc định thường đọc form parameters**, không tự phân tích JSON. Phải xác định API contract và redirect chain trước khi kết luận lỗi credential.

### Tình huống K — GET /csrf bị 401

SPA cần token trước login nhưng backend bảo vệ GET /csrf như authenticated API. Người dùng không thể login. Có nên tắt CSRF cho POST /login?

**Đáp án:** Không. Cho anonymous nhận token từ endpoint phù hợp và giữ CSRF trên login. **Login CSRF** tồn tại cả khi user chưa xác thực.

### Tình huống L — OPTIONS /login không có cookie

Browser gửi OPTIONS preflight, gateway trả 401 vì thiếu session cookie. Team muốn bắt browser gắn Cookie vào OPTIONS. Nên làm gì?

**Đáp án:** Cấu hình **CORS trước authentication** tại tầng thích hợp; preflight thường không có cookie session. POST thực vẫn phải qua CSRF và credential verification.

### Tình huống M — Reset password trả 404 cho email không có

Login API đã dùng thông điệp chung, nhưng /forgot-password trả 404 khi account không tồn tại. Đã giải quyết enumeration chưa?

**Đáp án:** Chưa. Recovery endpoint là một nguồn rò. Có thể trả thông báo chung như **“Nếu địa chỉ được đăng ký, hướng dẫn sẽ được gửi”** và gửi chỉ qua kênh sở hữu hợp lệ.

### Tình huống N — Reset response chung nhưng thời gian khác nhau

Với account có thật, server gửi email đồng bộ rồi mới trả 202; account không có trả ngay. Vẫn có nguy cơ gì?

**Đáp án:** **Timing side channel** qua workflow reset. Xem xét xử lý queue/async và đường request tương đồng có kiểm soát, đồng thời giới hạn abuse và giám sát hiệu năng.

### Tình huống O — Registration nói email đã tồn tại

Một dịch vụ có nhu cầu bảo vệ danh tính thành viên nhưng form đăng ký trả “Email này đã có tài khoản” cho bất kỳ ai. Có nên giữ UX này không?

**Đáp án:** Đây là quyết định cần đánh giá riêng tư. Với dịch vụ nhạy cảm, nên dùng **email verification/registration flow tổng quát** để người gửi chứng minh quyền sở hữu trước khi nhận chi tiết.

### Tình huống P — MFA hint xuất hiện trước xác thực

Chỉ cần nhập email, ứng dụng cho biết account đã bật TOTP và số điện thoại phục hồi kết thúc bằng 1234. Có phù hợp không?

**Đáp án:** Không nên mặc định. Đây là tiết lộ thông tin account/factor trước khi chứng minh quyền. Chỉ hiển thị chi tiết theo policy sau khi đã đạt một mức xác minh thích hợp.

### Tình huống Q — Mật khẩu đúng rồi mới yêu cầu MFA

User cung cấp mật khẩu đúng và nhận bước nhập OTP. Có bắt buộc giấu hoàn toàn việc MFA được bật ở giai đoạn này không?

**Đáp án:** Không nhất thiết. Khi password factor đã được xác minh, ứng dụng có thể hiển thị bước MFA theo flow; **không cấp quyền đầy đủ trước khi OTP/factor thứ hai hợp lệ**.

### Tình huống R — OIDC failure handler in nguyên exception

Callback OAuth2/OIDC bị từ chối vì state mismatch. Trang lỗi hiển thị toàn bộ exception, issuer, subject và auth request URL. Có phù hợp không?

**Đáp án:** Không. Hiển thị một thông báo login qua provider thất bại **tổng quát**, giữ chi tiết giao thức trong audit nội bộ; vẫn phải kiểm tra state/PKCE/nonce/issuer/audience đúng, không bỏ kiểm tra để che lỗi.

### Tình huống S — SSO home realm discovery

Chỉ cần nhập email, API trả tên tenant/IdP và tổ chức quản lý account. Có rủi ro gì?

**Đáp án:** Có thể tiết lộ **membership/organization**. Tùy tính công khai của domain và UX, cần ràng buộc việc tiết lộ với nguồn tin cậy hoặc xác minh ownership, và rate-limit discovery.

### Tình huống T — Account locked nhưng chưa chứng minh quyền sở hữu

Một người nhập email của người khác và nhận “Tài khoản này đang bị khóa vì hoạt động bất thường”. Có nên công khai thông tin này không?

**Đáp án:** Thường không. Đây là **account-state disclosure**. Giữ lỗi công khai tổng quát và cung cấp hướng dẫn chi tiết qua kênh xác minh phù hợp, trong khi backend vẫn không cho account bị khóa login.

### Tình huống U — Frontend phản chiếu identifier qua innerHTML

Trang login render thông báo có username người dùng nhập bằng innerHTML và không escape. Ngoài enumeration còn lỗi gì?

**Đáp án:** Có nguy cơ **DOM XSS**. Dùng textContent hoặc template engine auto-escaping, tránh nối input vào HTML và áp dụng CSP phù hợp trên HTML document.

### Tình huống V — Analytics ghi nguyên request body

AuthenticationFailureHandler trả thông báo chung nhưng gateway gửi request body chứa password đến hệ thống analytics. Đã bảo vệ bí mật credential chưa?

**Đáp án:** Chưa. Logging/telemetry cũng là ranh giới dữ liệu. Không lưu password/OTP/token, giới hạn dữ liệu audit, quyền truy cập và thời gian lưu.

### Tình huống W — IP limit tin X-Forwarded-For từ client

Attacker tự đổi X-Forwarded-For ở mỗi request để né rate limiting. Nguyên nhân?

**Đáp án:** Backend tin **forwarded header chưa được xác lập nguồn**. Phải làm sạch headers tại proxy, chỉ tin trusted proxy chain, không dùng IP do client tự khai làm bằng chứng duy nhất.

### Tình huống X — MockMvc dùng with(csrf()) đều thành công

Test API login của account không có và mật khẩu sai đều 401 với code LOGIN_FAILED. Có chắc không có enumeration qua các kênh khác không?

**Đáp án:** Chưa. Test còn cần **body/headers/redirect, locked account, rate limit, timing, recovery/registration/SSO**, browser và hạ tầng thật. with(csrf()) chỉ hỗ trợ đưa request qua CSRF layer.

### Tình huống Y — Lỗi login vì mạng nhưng UI báo user không tồn tại

Frontend catch tất cả fetch errors rồi hiển thị “Email chưa đăng ký”. Có hậu quả gì?

**Đáp án:** Vừa tiết lộ/khẳng định sai account existence vừa gây nhầm lẫn. Phải phân loại **lỗi xác thực được server trả, lỗi CORS/network và lỗi dịch vụ**; không suy trạng thái tài khoản từ fetch exception.

### Tình huống Z — Public error tổng quát, internal audit cụ thể

API trả LOGIN_FAILED cho user thiếu, password sai và account locked; audit nội bộ giữ mã nguyên nhân với RBAC, không lưu credential. Cách làm này hợp lý không?

**Đáp án:** Có, nếu hệ thống **vẫn thực thi đúng account policy**, không biến lỗi dịch vụ thành sai mật khẩu, giới hạn quyền truy cập audit và đã kiểm thử side channels. Đây là nguyên tắc **công khai tối thiểu, chẩn đoán nội bộ đủ dùng**.

## 17. Checklist triển khai và kiểm thử trước release

### 17.1. Public login error contract

- [ ] Các trường hợp **user không tồn tại** và **password sai với user tồn tại** có thông điệp công khai tương đương.
- [ ] Các trạng thái **locked, disabled, expired, chưa xác minh** được tiết lộ chỉ theo mức tin cậy/ownership đã đánh giá.
- [ ] **HTTP status, public code, body, Location, headers** không phân nhánh theo account existence trong cùng loại failure.
- [ ] HTML form login dùng một URL lỗi chung, ví dụ **/login?error**, không thêm username/status vào query.
- [ ] SPA có contract rõ ràng: credential failure tổng quát, auth success xác minh principal, lỗi dịch vụ riêng.
- [ ] Exception class, stack trace, password hash, user record, tenant hoặc MFA setting không xuất hiện trong public response.
- [ ] Authentication dependency lỗi không bị che thành **sai mật khẩu** nếu chưa kiểm chứng credential.
- [ ] Thông điệp công khai đủ hướng dẫn thao tác tiếp theo, hỗ trợ accessibility và localization.
- [ ] Input từ người dùng được output encode; không dùng innerHTML với exception/username không đáng tin.
- [ ] Không dùng query parameter **error** làm bằng chứng cấp quyền hoặc trạng thái đăng nhập.

### 17.2. Spring Security Servlet

- [ ] SecurityFilterChain áp dụng cho GET/POST /login đã được xác định, không có chain chồng lắp ngoài ý định.
- [ ] AuthenticationProvider/UserDetailsService kiểm tra password, account status và quyền nội bộ chính xác.
- [ ] **AuthenticationFailureHandler** map các lỗi credential cần ẩn thành một thông điệp công khai phù hợp.
- [ ] Nếu dùng form HTML, **failureUrl** không phân biệt sự tồn tại của account.
- [ ] Nếu dùng SPA, JSON failure response có status/schema/body/cache policy rõ ràng.
- [ ] **POST /login vẫn có CSRF protection** khi dùng cookie/session; permitAll không làm tắt CsrfFilter.
- [ ] Template login có hidden CSRF token thật; POST thiếu/sai token bị từ chối trước xác thực.
- [ ] Session ID được bảo vệ trước fixation khi login thành công; failure không tự cấp authenticated principal.
- [ ] **DaoAuthenticationProvider/PasswordEncoder** và user-not-found path được đánh giá về timing.
- [ ] Không viết custom authentication bằng cách set SecurityContext rồi bỏ qua session strategy/persistence.

### 17.3. Spring Security WebFlux/Reactive

- [ ] Dùng **SecurityWebFilterChain/ServerHttpSecurity**, không trộn các lớp Servlet.
- [ ] **ServerAuthenticationFailureHandler** trả public response thống nhất khi credential không hợp lệ.
- [ ] WebSession và CSRF repository được cấp/resolve đúng cho form login anonymous.
- [ ] Reactive Mono pipeline ghi response đúng và không gọi block() trong request path.
- [ ] OAuth2 login/redirect có xử lý lỗi riêng, không serialize raw provider exception.
- [ ] Nếu SPA cần JSON success, backend có **ServerAuthenticationSuccessHandler** đúng contract thay vì redirect mặc định.
- [ ] CORS source WebFlux dùng đúng gói reactive, với allowed origins/methods/headers rõ ràng.
- [ ] WebTestClient kiểm tra credential failure và CSRF failure riêng biệt.

### 17.4. Các luồng ngoài login

- [ ] **Forgot-password** không trả trạng thái account existence qua public status/body/redirect.
- [ ] Reset email/SMS chỉ được gửi qua kênh sở hữu hợp lệ, có chống spam/rate limiting.
- [ ] Luồng reset token có expiry, purpose, chống replay và không làm lộ token ở logs/Referrer.
- [ ] Registration xác định rõ chính sách tiết lộ email đã có tài khoản, phù hợp tính riêng tư của sản phẩm.
- [ ] Invitation và magic-link flows không tiết lộ membership/tenant ngoài phạm vi được phép.
- [ ] OIDC/OAuth2 callback giữ **state/PKCE/nonce/issuer/audience** validation, không công khai exception/token.
- [ ] MFA challenge chỉ tiết lộ yếu tố phù hợp sau mức chứng minh quyền sở hữu cần thiết.
- [ ] SSO tenant discovery được đánh giá rủi ro tiết lộ tổ chức hoặc account existence.
- [ ] Remember-me, token refresh và account switch không tạo user state sai hoặc bỏ kiểm tra authentication.
- [ ] Những thay đổi auth state được kiểm thử qua login/logout/session và multi-tab.

### 17.5. Rate limiting, privacy và observability

- [ ] Throttle không cho người ngoài phân biệt account thật qua **429/Retry-After** hoặc sự xuất hiện CAPTCHA.
- [ ] Có phòng vệ password spraying/credential stuffing phù hợp tải thật, không khóa account vô hạn theo input giả.
- [ ] Có cơ chế phục hồi hợp lệ khi user thật gặp rate limit/lockout.
- [ ] IP nguồn được xác lập bằng **trusted proxy chain**, không tin X-Forwarded-For tùy ý.
- [ ] Audit có resultCategory nội bộ nhưng không chứa raw password, token, session ID và dữ liệu cá nhân thừa.
- [ ] Quyền truy cập, retention, encryption và export của logs được kiểm soát.
- [ ] Telemetry bên thứ ba không nhận request body của POST /login hoặc raw exception.
- [ ] Có metrics 401/403/429/5xx, auth latency, CSRF errors và IdP availability theo mức tổng hợp phù hợp.
- [ ] Bất kỳ correlation ID nào cũng không encode account existence, credential hoặc thông tin nhạy cảm.
- [ ] Không tạo một endpoint “check email exists” công khai chỉ để frontend tối ưu UX mà bỏ threat model.

### 17.6. Bảo vệ trình duyệt và HTTP

- [ ] Login page dùng HTTPS, cookie có **Secure/HttpOnly/SameSite/Path/Domain** phù hợp.
- [ ] HSTS được triển khai theo chính sách và phạm vi host phù hợp; không bật includeSubDomains khi chưa kiểm kê HTTPS.
- [ ] Trang HTML login có CSP phù hợp với **script-src/form-action/frame-ancestors**, không chỉ API JSON.
- [ ] Error page không cache công khai dữ liệu theo phiên; các endpoint như GET /csrf có **no-store**.
- [ ] CORS allowlist dành cho SPA, không phản chiếu mọi Origin khi sử dụng credentials.
- [ ] OPTIONS preflight được xử lý trước authentication ở tầng cần thiết; POST thực vẫn qua CSRF/auth.
- [ ] Gateway, WAF, HTTP firewall và Spring có cách hiểu URL/method/headers nhất quán.
- [ ] Error response không để lộ stack trace, framework internals hoặc account status qua header.
- [ ] Browser console/DevTools không có lời gọi tới endpoint bên thứ ba mang username/password/reset token ngoài chủ đích.

### 17.7. Kiểm thử âm tính và hồi quy

- [ ] **Known user + wrong password** và **unknown user + password** có cùng lớp public response.
- [ ] Test so sánh cả **status, body, public code, Content-Type, Cache-Control và Location**.
- [ ] Account locked/disabled không bị lộ trước ownership verification theo policy.
- [ ] CSRF token thiếu/sai trả lỗi phù hợp và không tạo authenticated principal.
- [ ] Credential đúng đăng nhập được, session fixation được bảo vệ và quyền API đúng.
- [ ] Authentication dependency outage trả lỗi dịch vụ an toàn, không làm lộ cấu hình nội bộ.
- [ ] Password reset/registration/invitation/SSO được kiểm tra enumeration xuyên các entry points.
- [ ] Rate limiting, CAPTCHA và lockout không tạo public oracle theo username.
- [ ] Timing test trong staging có điều kiện/số lượng request giới hạn; không kết luận từ một lần đo.
- [ ] MockMvc/WebTestClient kiểm tra phản hồi công khai và có browser test kiểm tra cookie, redirect, CORS, CSP.
- [ ] Multi-instance và reverse proxy không tạo khác biệt response theo account hoặc làm mất CSRF/session.
- [ ] QA kiểm tra logs, APM, analytics không ghi credential hoặc exception nhạy cảm.

## 18. Ghi nhớ

1. **Thông báo đăng nhập thất bại là một ranh giới tiết lộ thông tin**, không chỉ là phần văn bản UX. Người chưa xác thực không tự có quyền biết email/user có account hoặc account đang ở trạng thái nào.
2. **Account enumeration có nhiều kênh**: message, status, error code, redirect, header, body length, thời gian phản hồi, CAPTCHA, throttle và các luồng reset/registration/SSO.
3. Với hai lỗi **username không tồn tại** và **username tồn tại nhưng mật khẩu sai**, ưu tiên **một phản hồi công khai tương đương** về code/body/status/redirect theo cùng contract, đồng thời giữ nguyên kiểm tra nội bộ.
4. **Ẩn account existence không đồng nghĩa bỏ authentication policy.** Account locked vẫn phải bị chặn; lỗi IdP/database thật cần chẩn đoán nội bộ và thông báo dịch vụ thích hợp.
5. **DaoAuthenticationProvider/PasswordEncoder** và timing phải được đánh giá. Chỉ gộp exception messages không loại bỏ mọi timing side channel; sleep cố định không phải giải pháp toàn diện.
6. Trong **Servlet**, dùng **AuthenticationFailureHandler** hoặc failureUrl của formLogin để trả thông điệp tổng quát. Trong **WebFlux**, dùng **ServerAuthenticationFailureHandler** và đảm bảo reactive response không serialize exception.
7. **POST /login dùng cookie/session vẫn cần CSRF token**. Lỗi 403 từ CsrfFilter khác với 401/redirect từ credential failure; **permitAll và CORS không thay thế CSRF protection**.
8. SPA cần hợp đồng frontend/backend rõ: **401 LOGIN_FAILED** cho credential sai, **204 hoặc success contract** cho login thành công, và kiểm tra principal qua endpoint được bảo vệ.
9. **Forgot-password, registration, magic link, invitation, MFA và OIDC/SSO** cần cùng chính sách giảm disclosure; chỉ sửa POST /login là chưa đủ.
10. **Rate limiting và account lockout** phải chống brute force mà không biến 429/CAPTCHA thành công cụ dò account hoặc gây DoS cho user thật.
11. **Audit nội bộ có thể chi tiết hơn response công khai**, nhưng phải bảo vệ password, token, session ID và thông tin cá nhân theo quyền truy cập, retention và chính sách logs.
12. **Bảo vệ HTTP/trình duyệt nhiều lớp** gồm TLS/HSTS, cookie flags, CSP, CORS, CSRF, session, proxy/HTTP firewall và authorization; không lớp nào tự bảo đảm mọi thông tin nhạy cảm đã được giấu.
13. **Kiểm thử cốt lõi**: hai credential failure có phản hồi công khai tương đương; request sai CSRF không đi tới auth provider; account hợp lệ đăng nhập được; dữ liệu nội bộ không lộ qua network, UI, logs hoặc side channels.

## Tài liệu tham khảo định hướng

Khi áp dụng thực tế, đối chiếu **phiên bản Spring Security** mà dự án đang sử dụng; API/đường dẫn và các giá trị mặc định có thể thay đổi theo phiên bản:

- [Spring Security Reference — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security Reference — Servlet DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Reactive Form Login](https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/form.html)
- [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reference — MockMvc Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)

**Nguyên tắc kết thúc bài:** Hãy xác định **ai đang hỏi, người đó đã chứng minh quyền sở hữu gì, và thông tin nào thật sự cần tiết lộ**. Mọi chi tiết bổ sung chỉ nên được cấp khi có căn cứ tin cậy tương ứng; phần còn lại thuộc về xử lý bảo mật và audit nội bộ.




