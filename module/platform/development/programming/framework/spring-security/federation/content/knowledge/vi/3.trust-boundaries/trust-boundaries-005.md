# Liên kết yêu cầu đăng nhập với phản hồi và phiên trình duyệt ban đầu

Trong federation, ứng dụng (Relying Party/Service Provider, RP/SP) gửi người dùng sang Identity Provider (IdP), rồi nhận phản hồi qua trình duyệt. Việc phản hồi **có chữ ký hợp lệ và đến từ IdP tin cậy** chưa đủ để xác định rằng **chính phiên trình duyệt đang nhận phản hồi đã khởi tạo yêu cầu đăng nhập ấy**. Hệ thống phải liên kết ba thứ: **yêu cầu ban đầu → phản hồi trả về → phiên trình duyệt đã bắt đầu giao dịch**.

Đây là ranh giới tin cậy quan trọng: **trình duyệt và mọi tham số ở callback là dữ liệu đầu vào chưa đáng tin**; ứng dụng chỉ chấp nhận khi chúng khớp với trạng thái giao dịch được lưu và xác minh phía máy chủ. Bài này tập trung vào luồng đăng nhập do ứng dụng khởi tạo (*SP/RP-initiated login*), phân tích song song OAuth 2.0/OpenID Connect (OIDC) và SAML 2.0.

## 1. Vì sao xác minh phản hồi vẫn chưa đủ?

Giả sử kẻ tấn công đăng nhập vào tài khoản của chính mình ở IdP rồi tìm cách gửi **phản hồi đăng nhập của kẻ tấn công** tới endpoint callback đang được trình duyệt nạn nhân mở. Nếu ứng dụng chỉ kiểm tra phản hồi hợp lệ mà không biết ai khởi tạo giao dịch, trình duyệt nạn nhân có thể bị gắn phiên ứng dụng của kẻ tấn công. Đây là một dạng **login CSRF / session swapping**, có thể khiến nạn nhân vô tình nhập dữ liệu vào tài khoản của kẻ tấn công.

Các câu hỏi khác nhau phải được kiểm chứng độc lập:

| Câu hỏi | Dữ kiện cần kiểm tra | Nếu bỏ qua |
| --- | --- | --- |
| Phản hồi có do đối tác tin cậy phát hành và còn hợp lệ? | Chữ ký, issuer, audience/client, thời gian, destination/recipient tùy giao thức. | Giả mạo token/assertion hoặc dùng phản hồi dành cho ứng dụng khác. |
| Phản hồi thuộc **lần đăng nhập nào**? | OAuth/OIDC: `state`, PKCE, `nonce` khi dùng. SAML: AuthnRequest ID và `InResponseTo`. | Chèn hoặc phát lại phản hồi vào giao dịch khác. |
| Giao dịch ấy do **phiên trình duyệt này** khởi tạo? | Bản ghi giao dịch lưu phía ứng dụng, gắn với phiên/cookie trình duyệt ban đầu. | Một phản hồi hợp lệ bị đưa vào phiên trình duyệt không liên quan. |
| Phản hồi đã từng được chấp nhận chưa? | Xử lý một lần, xóa giao dịch sau khi hoàn tất; chống replay theo cơ chế giao thức. | Dùng lại mã, assertion hoặc trạng thái đăng nhập. |

**Lưu ý:** `state`, `RelayState` và `InResponseTo` mang những ý nghĩa khác nhau. Không được coi một tham số nhận từ URL/form là bằng chứng tự thân rằng callback thuộc về trình duyệt hiện tại.

## 2. Mô hình giao dịch đăng nhập

~~~text
Trình duyệt A             Ứng dụng RP/SP                   IdP
     |                         |                            |
     | 1. Yêu cầu đăng nhập    |                            |
     |------------------------>|                            |
     |                         | 2. Tạo transaction ngẫu nhiên
     |                         |    lưu trong session A      |
     |                         |                            |
     | 3. Redirect/AuthnRequest|                            |
     |<------------------------|                            |
     |------------------------ trình duyệt chuyển tới IdP -->|
     |                         |                            |
     |<----------------- 4. IdP xác thực / chuyển phản hồi ----|
     |                         |                            |
     | 5. Callback + cookie A  |                            |
     |------------------------>|                            |
     |                         | 6. Nạp transaction của A    |
     |                         |    đối chiếu correlation    |
     |                         |    xác minh phản hồi        |
     |                         |    sử dụng một lần          |
     |<--- 7. Phiên ứng dụng --|                            |
~~~

Ứng dụng cần lưu một **pending login transaction** với thời hạn ngắn, gắn với đúng phiên trình duyệt. Tối thiểu giao dịch có thông tin cần thiết để tìm đối tác tin cậy, đối chiếu yêu cầu/phản hồi và hoàn tất trao đổi token/assertion: định danh IdP, `state` hoặc ID AuthnRequest, PKCE `code_verifier` nếu là OAuth, `nonce` nếu giao thức yêu cầu/ứng dụng dùng, thời gian tạo và URI quay lại đã được kiểm tra.

Dữ liệu giao dịch phải được lưu/phát hành bằng cơ chế chống giả mạo, ràng buộc với phiên người dùng và **không rò rỉ bí mật**. Lưu ở session phía server là một lựa chọn thông dụng. Nếu dùng distributed store hoặc cookie đã được bảo vệ bằng cơ chế mật mã, thiết kế phải giữ nguyên tính **khó đoán, toàn vẹn, giới hạn thời gian, dùng một lần và ràng buộc phiên**.

## 3. Liên kết trong OAuth 2.0 / OpenID Connect

### 3.1. `state` liên kết authorization response với yêu cầu gốc

Ứng dụng tạo `state` ngẫu nhiên đủ mạnh cho **mỗi giao dịch**, lưu trạng thái kỳ vọng trong session trình duyệt A và đưa `state` vào authorization request. Callback hợp lệ phải trả đúng giá trị đó trong bối cảnh session A. Mục đích quan trọng là chống login CSRF và ngăn callback lạ được ghép với giao dịch khác.

Ví dụ minh họa (giá trị đã rút ngắn, **không sử dụng làm mã ngẫu nhiên thực tế**):

~~~text
Browser A, session=sess-A
GET /oauth2/authorization/corporate

Ứng dụng lưu tại sess-A:
  state = St-7g...A
  provider = corporate
  redirect_uri = https://rp.example.org/login/oauth2/code/corporate
  code_verifier = <giá trị bí mật ngẫu nhiên>
  nonce = <giá trị ngẫu nhiên, nếu dùng>
  created_at = <thời gian bắt đầu>

Callback:
GET /login/oauth2/code/corporate?code=...&state=St-7g...A

Ứng dụng tìm pending transaction trong sess-A,
đối chiếu state, provider và các tham số giao thức,
rồi mới xử lý trao đổi mã và tạo phiên đăng nhập.
~~~

Nếu trình duyệt **B** gửi cùng `state` nhưng session B không có pending transaction tương ứng, **phải từ chối**. Nếu response không có `state` phù hợp hoặc giao dịch đã hết hạn/đã dùng, cũng phải từ chối. Không được tạo một pending transaction mới từ tham số callback để hợp thức hóa nó.

### 3.2. PKCE và `nonce` bổ sung ràng buộc theo giao dịch

- **PKCE**: client tạo `code_verifier` ngẫu nhiên, gửi `code_challenge` đến Authorization Server; khi đổi authorization code phải xuất trình đúng verifier. Cơ chế này giảm rủi ro code interception/injection. Với bảo vệ CSRF bằng PKCE, verifier phải thực sự **gắn với client và phiên trình duyệt khởi tạo**, Authorization Server phải hỗ trợ và thực thi PKCE; không thay một `state` đúng bằng chuỗi verifier gửi bừa từ callback.
- **OIDC `nonce`**: khi dùng, ứng dụng lưu nonce mong đợi gắn với giao dịch và xác minh claim `nonce` trong ID token. Nonce giúp ràng buộc ID token với lần xác thực và chống replay. Quy tắc có/không có nonce phụ thuộc OIDC flow và cấu hình; không được tự bỏ xác minh nonce nếu đã gửi nó trong request.
- **ID token** phải được xác minh chữ ký, issuer, audience, thời hạn và các ràng buộc OIDC liên quan. **Access token** không tự thay thế được kiểm tra danh tính của OIDC client.
- **Authorization code** chỉ đổi tại token endpoint đúng của issuer đã chọn, cùng `redirect_uri`, client authentication và PKCE theo cấu hình. Callback phải bị từ chối khi issuer không tương ứng với authorization transaction (*mix-up defense*), đặc biệt với client hỗ trợ nhiều IdP.

RFC 9700 khuyến nghị dùng PKCE cho confidential clients và yêu cầu với public clients, cùng ràng buộc challenge/nonce vào giao dịch và user agent. Giá trị `state` có thể còn mang trạng thái ứng dụng nhưng phải được bảo vệ toàn vẹn/chống tráo; tốt nhất chỉ lưu một khóa ngẫu nhiên rồi tra trạng thái nhạy cảm phía server.

### 3.3. Quy trình xử lý callback OIDC an toàn

1. Nhận callback tại **redirect URI đã đăng ký chính xác**, dùng HTTPS và cấu hình reverse proxy chuẩn.
2. Xác định **phiên trình duyệt hiện tại từ cookie/session đáng tin cậy**; không lấy session ID từ query parameter hoặc request body do người dùng tự nhập.
3. Nạp transaction đang chờ thuộc session ấy; nếu không có, hết hạn hoặc đã dùng thì từ chối.
4. So sánh `state`; kiểm tra IdP/issuer của giao dịch (và biện pháp mix-up), `redirect_uri`, client registration.
5. Đổi `code` cùng PKCE verifier của **chính transaction đó**; không sử dụng verifier từ nguồn chưa được bảo vệ.
6. Xác minh ID token theo OIDC, bao gồm `nonce` khi được dùng. Chỉ tạo `Authentication` sau khi các điều kiện đều đạt.
7. Đánh dấu transaction đã tiêu thụ theo cách **nguyên tử**, không cho callback song song chấp nhận lại; bảo vệ phiên đăng nhập sau thành công bằng cơ chế chống session fixation, cookie an toàn và quyền tối thiểu.
8. Nếu cần redirect về màn hình người dùng định mở, chỉ dùng **đường dẫn đã kiểm tra/allowlist**, tránh open redirect gây lộ mã hoặc đưa người dùng đến website giả.

Một lỗi ở bất cứ bước nào phải kết thúc bằng **không xác thực**, có thể ghi log correlation ID và loại lỗi ở mức an toàn; không ghi nguyên authorization code, token, cookie, hay `code_verifier` vào log.

## 4. Liên kết trong SAML 2.0 (SP-initiated SSO)

Trong SAML, ứng dụng SP gửi **`AuthnRequest`** có `ID` duy nhất. SP giữ bản yêu cầu ấy trong session trình duyệt ban đầu. IdP gửi **`Response`** đến Assertion Consumer Service (ACS), thường bằng HTTP POST, với `InResponseTo` tham chiếu ID yêu cầu; phần `SubjectConfirmationData` của bearer assertion cũng có thể chứa `InResponseTo` theo profile.

Các giá trị cần phân biệt:

| Giá trị | Nguồn | Vai trò |
| --- | --- | --- |
| `AuthnRequest/@ID` | SP tạo và lưu khi bắt đầu. | Định danh lần yêu cầu xác thực. |
| `Response/@InResponseTo` | IdP trả về dựa trên AuthnRequest. | Liên kết response với request đã phát. |
| `SubjectConfirmationData/@InResponseTo` | Trong assertion theo bearer SSO profile. | Ràng buộc assertion với AuthnRequest tương ứng. |
| `RelayState` | Đi kèm SAML request/response qua binding. | Duy trì trạng thái ứng dụng/định tuyến giao dịch; **không tự chứng minh sở hữu phiên**. |
| Browser session cookie | Trình duyệt gửi đến SP. | Cho phép SP khôi phục giao dịch **đã khởi tạo từ trình duyệt này**. |
| `Destination`, `Recipient`, `AudienceRestriction` | Trong response/assertion. | Giới hạn điểm nhận/phần mềm được phép dùng assertion; bổ sung nhưng không thay thế ràng buộc session. |

**Kiểm tra chuẩn cho SP-initiated:** SP phải lấy AuthnRequest gốc từ transaction đáng tin gắn session và yêu cầu `InResponseTo` khớp; tiếp đó xác minh response/assertion thuộc IdP tin cậy, có chữ ký hợp lệ theo profile, đúng issuer, `Destination`/ACS, `Recipient`, audience, thời hạn và SubjectConfirmation. Phải xử lý assertion ID/response ID chống replay và chỉ chấp nhận một lần.

**IdP-initiated (unsolicited) SSO** không có AuthnRequest do SP mở trước nên không có cùng ràng buộc `InResponseTo`. Nếu sản phẩm cho phép, đó là **luồng riêng với chính sách rủi ro riêng**. Không âm thầm chuyển từ kiểm tra SP-initiated thất bại sang chế độ unsolicited để “cho đăng nhập thành công”.

### 4.1. Sai lầm rất thường gặp: chỉ tra bằng `RelayState`

Giả sử SP lưu mọi AuthnRequest trong cache chia sẻ và dùng `RelayState` từ phản hồi làm khóa tra yêu cầu, **mà không chứng minh trình duyệt hiện tại đã khởi tạo request ấy**. Kẻ tấn công có thể dùng callback chứa một mã tham chiếu hợp lệ để gắn luồng của chính họ vào phiên nạn nhân. Vì vậy, cache phân tán phải lưu kèm chứng cứ ràng buộc browser session và phải xác thực lại chứng cứ đó khi callback; không mặc nhiên tin `RelayState` hay `InResponseTo` đến từ form POST.

Nếu trình duyệt mất cookie vì chính sách `SameSite` trong luồng SAML POST liên site, cách khắc phục là thiết kế session/cookie hoặc correlation store phù hợp với luồng và yêu cầu bảo mật. **Không sửa bằng cách bỏ qua kiểm tra session hoặc InResponseTo.**

## 5. Minh họa bằng Java 17: tương quan phiên và dùng một lần

Ví dụ dưới đây **chỉ mô phỏng** phép kiểm tra transaction phía máy chủ; không triển khai OIDC/SAML, không xác minh chữ ký, không thay Spring Security hoặc thư viện giao thức. Trong ứng dụng thật, tên session lấy từ container/web session đã bảo vệ, dữ liệu được lưu bền an toàn phù hợp mô hình triển khai, và toàn bộ xác minh token/assertion phải thành công trước khi phát phiên ứng dụng.

Tệp `LoginCorrelationDemo.java`:

~~~java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LoginCorrelationDemo {
    record Pending(String state, String idp) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ConcurrentMap<String, Pending> REQUESTS =
            new ConcurrentHashMap<>();

    static String begin(String browserSession, String idp) {
        byte[] random = new byte[32];
        RANDOM.nextBytes(random);
        String state = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);
        REQUESTS.put(browserSession, new Pending(state, idp));
        return state;
    }

    static boolean verifyAndConsume(
            String browserSession, String state, String idp) {
        Pending pending = REQUESTS.get(browserSession);
        return pending != null
                && pending.state().equals(state)
                && pending.idp().equals(idp)
                && REQUESTS.remove(browserSession, pending);
    }

    public static void main(String[] args) {
        String stateA = begin("session-A", "idp-corporate");

        System.out.println(verifyAndConsume(
                "session-B", stateA, "idp-corporate"));
        System.out.println(verifyAndConsume(
                "session-A", stateA, "idp-corporate"));
        System.out.println(verifyAndConsume(
                "session-A", stateA, "idp-corporate"));
    }
}
~~~

Chạy trên Java 17 trở lên:

~~~bash
javac LoginCorrelationDemo.java
java LoginCorrelationDemo
~~~

Kết quả chắc chắn (dù giá trị ngẫu nhiên của `state` thay đổi):

~~~text
false
true
false
~~~

Giải thích: callback từ **B** bị từ chối do không có pending request trong session B; lần đầu từ **A** hợp lệ; lần thứ hai từ A bị từ chối do transaction đã được tiêu thụ. Demo cố ý chỉ giữ **một** pending request mỗi session; hệ thống hỗ trợ nhiều tab đăng nhập song song phải lập bản ghi **riêng cho từng transaction** với khóa ngẫu nhiên, thời gian hết hạn và xóa nguyên tử. Không dùng bản `ConcurrentHashMap` trong ví dụ làm kho giao dịch phân tán thật.

## 6. Spring Security Servlet hỗ trợ ràng buộc này như thế nào?

Spring Security có các cơ chế quản lý yêu cầu đang chờ, vì vậy thông thường ứng dụng nên cấu hình giao thức qua framework và **giữ nguyên các lớp xác minh/correlation mặc định**.

| Luồng | Thành phần Spring Security | Chức năng liên quan |
| --- | --- | --- |
| OAuth 2.0/OIDC | `OAuth2AuthorizationRequestRedirectFilter`, `OAuth2AuthorizationRequestResolver` | Tạo và chuyển authorization request. |
| OAuth 2.0/OIDC | `AuthorizationRequestRepository` | Lưu yêu cầu từ lúc khởi tạo đến callback; mặc định dùng `HttpSessionOAuth2AuthorizationRequestRepository`. |
| OAuth 2.0/OIDC | `OAuth2LoginAuthenticationFilter` | Tải và xác minh giao dịch phù hợp khi nhận authorization response. |
| SAML 2.0 | `Saml2WebSsoAuthenticationRequestFilter` | Tạo/gửi `AuthnRequest`. |
| SAML 2.0 | `Saml2AuthenticationRequestRepository` | Lưu `AuthnRequest`; mặc định dùng `HttpSessionSaml2AuthenticationRequestRepository`. |
| SAML 2.0 | `Saml2WebSsoAuthenticationFilter` và authentication provider của OpenSAML | Nạp giao dịch, phân tích và xác minh SAML response/assertion. |

Ví dụ cấu hình **một ứng dụng OIDC Servlet** bằng Spring Boot có dependency `spring-boot-starter-security` và `spring-boot-starter-oauth2-client`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **cấu hình bên trong dự án Spring Boot**, không phải tệp có thể `javac` độc lập. Ngoài lớp cấu hình, ứng dụng cần khai báo `ClientRegistration`/issuer và client credentials hợp lệ qua application properties hoặc bean. Spring quản lý authorization request trong HttpSession theo mặc định; không phải tự tạo callback controller nhận `state` rồi gọi token endpoint thủ công.

Với ứng dụng SAML, cấu hình tương ứng là `saml2Login(Customizer.withDefaults())` cùng `RelyingPartyRegistration` và metadata/chứng thư IdP đúng. Giữ validation mặc định, đặc biệt `InResponseTo`, audience, issuer, signature, thời hạn, recipient/destination. Tên provider và cách tùy biến có thể khác theo phiên bản Spring Security/OpenSAML; kiểm tra tài liệu **đúng phiên bản** nếu thay repo hoặc validator.

### 6.1. Cookie, reverse proxy và nhiều instance

- Dùng HTTPS và cookie phiên có `Secure`, `HttpOnly`, cấu hình `SameSite` phù hợp. OAuth redirect GET và SAML POST cross-site có nhu cầu cookie khác nhau; kiểm thử trên trình duyệt thật, nhất là trường hợp IdP khác site.
- Nếu callback đi đến một instance khác, phải có cơ chế chia sẻ session/transaction an toàn hoặc bảo đảm routing phù hợp. Callback không tìm thấy giao dịch **phải thất bại an toàn**, không tắt kiểm tra.
- Khi phía trước có reverse proxy, cấu hình URI public và cách xử lý header forwarded từ proxy **đáng tin cậy**; sai scheme/host có thể làm redirect URI, destination/recipient không khớp.
- Với nhiều IdP hoặc nhiều tenant, xác định registration/issuer từ transaction đã tin cậy; tránh nhận toàn bộ lựa chọn IdP từ trường do callback tự khai.
- Khi người dùng mở đồng thời hai luồng login cùng session, xác định repository lưu một hay nhiều transaction; giao dịch ghi đè/callback sai có thể gây lỗi đăng nhập. Không “sửa” bằng cách chấp nhận callback thiếu correlation.

## 7. Bảng kiểm và tình huống kiểm thử

| Thử nghiệm | Kết quả an toàn mong đợi |
| --- | --- |
| Callback trả `state` đúng nhưng cookie thuộc session khác. | Từ chối, không tạo phiên đăng nhập. |
| Callback thiếu hoặc sai `state`. | Từ chối; không tự suy ra lại transaction. |
| Authorization code hợp lệ nhưng thiếu/sai PKCE verifier. | Trao đổi code thất bại; không tạo phiên. |
| ID token có `nonce` không khớp transaction. | Từ chối xác thực OIDC. |
| Trả code từ IdP B cho giao dịch vốn bắt đầu với IdP A. | Từ chối theo issuer/client/transaction binding. |
| SAML `InResponseTo` không trỏ về AuthnRequest còn chờ của **cùng phiên**. | Từ chối SP-initiated login. |
| SAML response có chữ ký hợp lệ nhưng audience/recipient sai. | Từ chối; chữ ký đúng không đủ. |
| Gửi lại callback đã hoàn tất. | Từ chối lần thứ hai. |
| Callback đến sau khi transaction hết hạn hoặc session bị xóa. | Từ chối; yêu cầu người dùng khởi tạo đăng nhập mới. |
| Muốn đưa người dùng về một `returnUrl` bên ngoài không được phép. | Không redirect đến URL tự do của bên thứ ba. |

**Dấu hiệu cần quan sát khi debug:** transaction không tìm thấy, state/nonce mismatch, sai issuer/registration, `InResponseTo` mismatch, callback mất cookie, request hết hạn, code trao đổi thất bại. Log **mã giao dịch đã băm hoặc định danh nội bộ an toàn**, loại lỗi, timestamp và IdP đã cấu hình; tránh log token, assertion chứa PII, cookie hoặc verifier.

## 8. Ghi nhớ

1. **Tin cậy đối tác** trả lời “ai phát hành phản hồi?”; **correlation** trả lời “phản hồi này thuộc lần đăng nhập nào?”; **session binding** trả lời “lần đăng nhập ấy xuất phát từ trình duyệt nào?”.
2. OAuth/OIDC sử dụng `state` cùng transaction lưu an toàn, PKCE và `nonce` khi áp dụng; SAML sử dụng AuthnRequest, `InResponseTo`, `RelayState` có kiểm soát và session correlation.
3. Mọi callback phải được xác minh và chỉ sử dụng một lần. Không phục hồi phiên đăng nhập từ một tham số callback chưa gắn với phiên trình duyệt.
4. Các thư viện Spring Security triển khai logic chuẩn; phần tùy biến repository/callback phải **bảo toàn hoặc tăng** kiểm tra bảo mật, không bỏ validation cho tiện tích hợp.

## Tài liệu tham khảo

- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0 — state và nonce](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Authorization Code và AuthorizationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
