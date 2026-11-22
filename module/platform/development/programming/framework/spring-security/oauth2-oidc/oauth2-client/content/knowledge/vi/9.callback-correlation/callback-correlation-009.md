# 9.9. Callback trùng lặp, mã đã dùng và giới hạn chống replay

## Mục tiêu

Trong **Spring Security OAuth 2.0 / OIDC Client**, callback là nơi ứng dụng nhận phản hồi từ Authorization Server (AS) hoặc OpenID Provider (OP). Với **Authorization Code flow**, callback thường chứa `code` và `state`. Đây là dữ liệu của một giao dịch ủy quyền cụ thể, không phải URL có thể được xử lý lại tùy ý.

Sau bài học, bạn có thể:

- Phân biệt callback hợp lệ với callback trùng do refresh, retry, hai tab, hết phiên và hành vi replay.
- Giải thích tại sao **authorization code phải ngắn hạn và chỉ được dùng một lần**.
- Phân biệt nhiệm vụ chống replay/correlation của `state`, `nonce` và PKCE.
- Mô tả cách Spring Security Servlet lưu Authorization Request trước callback, lấy và loại bỏ trạng thái đó khi nhận callback.
- Phân tích lỗi `invalid_grant`, thiếu request gốc, state không khớp và race condition.
- Thiết kế hành vi phục hồi an toàn mà không đổi lại code cũ hoặc bỏ qua kiểm tra giao thức.
- Hiểu ranh giới giữa chống replay tại callback và chống replay của token, session, API và nghiệp vụ.

## 1. Callback là bước cuối của một giao dịch Authorization Code

Giả sử **Employee Portal** được triển khai bằng Spring Boot, dùng đăng nhập OIDC với registration ID `corporate`. Người dùng truy cập một trang yêu cầu đăng nhập, Spring Security bắt đầu flow:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Spring Security sinh và lưu những thông tin cần thiết để đối chiếu phản hồi của OP, rồi chuyển browser đến authorization endpoint. Sau khi xác thực thành công, browser được redirect về:

~~~http
GET /login/oauth2/code/corporate?code=CODE_A&state=STATE_A HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=SESSION_A
~~~

Các giá trị `CODE_A`, `STATE_A` và `SESSION_A` là placeholder minh họa, không phải bí mật thật.

Ở callback hợp lệ, ứng dụng thực hiện:

1. Nhận biết registration `corporate` và tìm **Authorization Request đã khởi tạo**.
2. Đối chiếu `state` và các điều kiện callback/correlation.
3. Trao đổi code với token endpoint cùng xác thực client, PKCE verifier nếu flow dùng PKCE.
4. Nếu đây là OIDC Login, xác minh ID token theo issuer, audience, thời hạn, chữ ký và nonce khi được sử dụng.
5. Xây `Authentication` có principal OIDC, lưu `SecurityContext` theo chính sách phiên ứng dụng.
6. Redirect browser sang trang ứng dụng như `/dashboard`.

Những bước đó có ý nghĩa **một lần cho một giao dịch authorization**. Khi request đầu tiên thành công, authorization code đã được tiêu thụ.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant App as Spring Boot OIDC Client
    participant Provider as OP / Authorization Server
    User->>Browser: Mở trang yêu cầu đăng nhập
    Browser->>App: GET /oauth2/authorization/corporate
    Note over App: Tạo state, lưu Authorization Request
    App-->>Browser: Redirect đến OP
    Browser->>Provider: Authorization Request
    Provider->>User: Xác thực nếu cần
    Provider-->>Browser: Redirect code=CODE_A và state=STATE_A
    Browser->>App: Callback lần đầu
    Note over App: So khớp state và request gốc
    App->>Provider: Token request với CODE_A
    Provider-->>App: Token response hợp lệ
    Note over App: Kiểm tra OIDC, lập SecurityContext
    App-->>Browser: Redirect sang /dashboard
    Browser->>App: Callback cũ được gửi lại
    Note over App: Không còn pending request hoặc code đã dùng
    App-->>Browser: Xử lý thất bại an toàn
~~~

Callback trùng lặp có thể đến sau khi phiên đăng nhập đã tồn tại. Vì vậy **có session hợp lệ** không có nghĩa **code cũ vẫn có thể đổi token**.

## 2. Vì sao callback có thể được gửi nhiều lần?

| Tình huống | Biểu hiện | Bản chất |
|---|---|---|
| Refresh callback | Người dùng tải lại `/login/oauth2/code/corporate` | Cùng URL bị gửi lại |
| Back/Forward | Trình duyệt mở lại callback cũ trong lịch sử | Flow đã hoàn tất |
| Network retry | Response đầu bị mất, proxy/client tự gửi lại request | Có thể backend đã thành công |
| Redirect trùng | Frontend hoặc middleware kích hoạt điều hướng hai lần | Hai callback gần như đồng thời |
| Hai tab login | Tab A có state A, tab B có state B | Hai flow riêng, có thể tranh chấp session |
| Session hết hạn | Callback đến sau khi request gốc bị xóa | Mất correlation |
| Load balancer | Login bắt đầu ở node A, callback tới node B | Thiếu state nếu kho session không dùng chung |
| Replay cố ý | Ai đó phát lại URL callback đã thu thập | Cố dùng lại giá trị giao thức |

**Một callback được gửi hai lần không đủ để kết luận có tấn công.** Ngược lại, request trông hợp lệ về HTTP không có nghĩa còn hợp lệ về giao thức OAuth/OIDC.

## 3. Authorization code: ngắn hạn và single-use

### 3.1. Tại sao code phải sử dụng một lần?

Authorization code là giá trị do AS phát hành, nhằm cho phép client đổi lấy token. Code:

- Có thời gian sống ngắn.
- Chỉ có thể được sử dụng **một lần**.
- Được gắn với client đã được cấp.
- Được ràng buộc với redirect URI theo điều kiện của flow.
- Có thể được liên kết với PKCE `code_challenge`.

Nó không phải access token và không nên được gửi đến Resource Server.

Ví dụ:

~~~text
T0  OP phát hành CODE_A
T1  Portal gửi CODE_A đến token endpoint
T2  OP xác minh và trả token hợp lệ
T3  Portal hoặc bên khác gửi lại CODE_A
T4  OP từ chối vì code đã được tiêu thụ
~~~

Một phản hồi có thể là:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
~~~

### 3.2. `invalid_grant` không chỉ có nghĩa “code đã dùng”

Lỗi token endpoint `invalid_grant` có thể cho biết code:

- Đã được sử dụng.
- Đã hết thời hạn.
- Không hợp lệ.
- Không khớp redirect URI.
- Được cấp cho client khác.
- Không thỏa một điều kiện của grant tương ứng.

Vì vậy, **không được chẩn đoán chắc chắn replay chỉ từ `invalid_grant`**. Cần xem luồng trước đó, registration, callback, mã lỗi, trạng thái phiên và thời điểm token request, nhưng không ghi token/code thật vào log.

### 3.3. AS chịu trách nhiệm thực thi single-use

Nếu hai request cùng tới token endpoint với `CODE_A`, AS phải đảm bảo không thể đổi một code thành hai lần cấp token hợp lệ. OAuth 2.0 yêu cầu từ chối code reuse; khi thấy code bị sử dụng nhiều lần, AS nên xem xét thu hồi token đã cấp từ code đó nếu khả thi.

Đây là trách nhiệm của AS. RP vẫn phải bảo vệ **state correlation và side effect của chính nó**.

Code single-use không có nghĩa `HttpSession`, access token hay thao tác kinh doanh cũng trở thành single-use.

### 3.4. Mạng timeout và kết quả không chắc chắn

Nếu Portal gửi token request và bị timeout, có thể xảy ra:

1. AS chưa nhận hoặc chưa xử lý code.
2. AS đã xử lý code và phát token, nhưng response không đến client.
3. Code đã hết hạn hoặc không hợp lệ vì nguyên nhân khác.

Retry mù cùng code không giải quyết được tất cả tình huống; nếu AS đã tiêu thụ code, retry sẽ thất bại. Khi không thể hoàn tất kết quả đáng tin cậy, ứng dụng thường phải **bắt đầu authorization flow mới**, tạo state, code challenge/verifier và các dữ liệu giao thức mới.

## 4. `state`: ràng buộc callback với request ban đầu

### 4.1. State được sinh trước khi redirect

Trong Authorization Request, client tạo `state` ngẫu nhiên, khó đoán. Dữ liệu request đang chờ có thể bao gồm:

~~~text
registrationId: corporate
state:          STATE_A
redirectUri:    https://portal.example.com/login/oauth2/code/corporate
scope:          openid profile email
nonce:          NONCE_A (nếu dùng)
PKCE data:      verifier/challenge (nếu dùng)
~~~

OP trả lại `state` trong authorization response. Spring Security cần xác định response đó khớp với request được lưu trong ngữ cảnh đăng nhập.

### 4.2. State giúp chống login CSRF

Nếu RP chấp nhận mọi authorization code được gửi tới callback mà không đối chiếu một yêu cầu đã khởi tạo, bên khác có thể tìm cách ép browser nạn nhân xử lý một kết quả ủy quyền không thuộc flow của nạn nhân.

`state` là một phần của cơ chế **correlation** để RP trả lời:

> Callback này có đến từ yêu cầu authorization mà chính browser/phiên hiện tại đã bắt đầu không?

Đừng đặt state cố định theo `userId`, email hoặc client ID. Các giá trị đó dễ đoán hoặc không phân biệt được các giao dịch khác nhau.

### 4.3. State không khớp phải bị từ chối

Giả sử ứng dụng lưu pending request có `STATE_A`, nhưng callback gửi:

~~~text
code=CODE_X&state=STATE_UNKNOWN
~~~

RP không được:

- Bỏ qua state rồi thử đổi code.
- So khớp một phần state.
- Thử code với nhiều client/provider khác nhau.
- Sử dụng request gần nhất bất kể state.
- Tin một user ID do browser gửi thay cho correlation.

Không có Authorization Request gốc phù hợp thì không có cơ sở tin callback là phản hồi của flow hiện tại.

### 4.4. State cũ phải ngừng là pending request

Một luồng hợp lệ:

~~~text
Trước callback:
    STATE_A -> Authorization Request A đang chờ

Callback lần 1:
    STATE_A khớp
    A được xử lý/loại khỏi trạng thái pending

Callback lần 2:
    STATE_A không còn pending request
    RP từ chối callback
~~~

Do đó callback trùng có thể thất bại **trước token exchange**. Trong trường hợp đó không nhất thiết có một `invalid_grant` từ OP vì request chưa tới token endpoint.

## 5. `nonce` và PKCE bảo vệ các bước khác nhau

### 5.1. OIDC nonce

`nonce` liên kết một ID token với Authentication Request khi được sử dụng.

~~~text
Authorization Request:
    state = STATE_A
    nonce = NONCE_A

ID token:
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "nonce": "NONCE_A"
}
~~~

Đây chỉ là payload minh họa, không phải ID token hợp lệ có chữ ký.

- `state`: liên kết **callback** với Authorization Request.
- `nonce`: liên kết **ID token** với OIDC Authentication Request.
- Authorization code: giá trị **đổi token một lần**.
- PKCE: chứng minh bên đổi code nắm verifier phù hợp.

Nonce không thay thế state. Một ID token có nonce hợp lệ từ lần đăng nhập trước **không khiến code cũ được phép dùng lại**.

Khi OIDC dùng nonce, RP phải kiểm tra nonce cùng các điều kiện token khác. ID token phải được xác minh chữ ký, issuer, audience, thời gian và điều kiện liên quan trước khi tin bất kỳ claim nào.

### 5.2. PKCE

Trong Authorization Code flow với PKCE:

1. Client tạo `code_verifier` khó đoán.
2. Client gửi `code_challenge`, thường theo phương pháp `S256`, trong Authorization Request.
3. AS gắn challenge với code được phát hành.
4. Khi đổi code, client gửi verifier.
5. AS kiểm tra verifier phù hợp challenge.

~~~text
Authorization Request:
  code_challenge=CHALLENGE_A
  code_challenge_method=S256

Token Request:
  code=CODE_A
  code_verifier=VERIFIER_A
~~~

PKCE giảm rủi ro **code interception**: lấy được code mà không nắm verifier không đủ để đổi token. Nó không thay thế state, callback binding hoặc client authentication khi cần.

### 5.3. So sánh các cơ chế

| Cơ chế | Trách nhiệm | Không thay thế |
|---|---|---|
| Code single-use | AS không cấp token nhiều lần từ một code | State, PKCE, logic nghiệp vụ |
| `state` | RP liên kết callback với request đã tạo | PKCE, xác minh ID token |
| `nonce` | RP ràng buộc ID token với yêu cầu OIDC | State, single-use code |
| PKCE | AS ràng buộc đổi code với verifier | State, redirect URI |
| Client authentication | Confidential client chứng minh danh tính tại token endpoint | PKCE và correlation |
| HTTPS | Bảo vệ dữ liệu giao thức khi truyền | Kiểm tra logic protocol |

Dùng nhiều lớp đúng nhiệm vụ tạo ra hệ thống khó bị chiếm code hoặc đánh tráo response hơn.

## 6. Spring Security xử lý callback bằng những thành phần nào?

Với Servlet stack, các URL mặc định thường là:

~~~text
Bắt đầu login: /oauth2/authorization/corporate
Callback:       /login/oauth2/code/corporate
~~~

Các thành phần chính:

| Thành phần | Nhiệm vụ |
|---|---|
| `ClientRegistration` | Thông tin client, grant, redirect URI và provider |
| `OAuth2AuthorizationRequestRedirectFilter` | Tạo bước redirect tới OP |
| `OAuth2AuthorizationRequestResolver` | Xây Authorization Request |
| `OAuth2AuthorizationRequestRepository` | Lưu, tra cứu, xóa request đang chờ |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Implementation dùng `HttpSession`, thường có trong Servlet OIDC Login |
| `OAuth2LoginAuthenticationFilter` | Tiếp nhận và xử lý callback |
| OAuth2/OIDC authentication providers | Token exchange và các bước xác minh cần thiết |
| `SecurityContextRepository` | Lưu và khôi phục Authentication sau login |
| `OAuth2AuthorizedClientService` / `Repository` | Quản lý token đã cấp cho client/principal |

**Không cần tự viết controller nhận `/login/oauth2/code/corporate`** nếu đang dùng callback mặc định của `oauth2Login()`.

### 6.1. Authorization Request Repository

Interface repository có các thao tác:

~~~java
OAuth2AuthorizationRequest loadAuthorizationRequest(
        HttpServletRequest request);

void saveAuthorizationRequest(
        OAuth2AuthorizationRequest authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

OAuth2AuthorizationRequest removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
~~~

Đoạn trên mô tả chữ ký các thao tác quan trọng, không phải một class Java hoàn chỉnh.

- `saveAuthorizationRequest` lưu dữ liệu trước khi redirect sang OP.
- `loadAuthorizationRequest` tìm request đang chờ tương ứng.
- `removeAuthorizationRequest` loại bỏ request đã xử lý theo contract của implementation.

Nếu custom repository không xóa trạng thái đang chờ sau khi xử lý, callback cũ có thể tiếp tục tìm thấy request gốc, gây rủi ro trong correlation hoặc side effect. **Repository không thay cho quy tắc code single-use của AS.**

### 6.2. Vì sao callback cũ có thể lỗi dù session còn sống?

Phiên Servlet có thể vẫn chứa `SecurityContext` sau login, nhưng Authorization Request đã được tiêu thụ. Hai loại dữ liệu khác nhau:

~~~text
HttpSession
├── SecurityContext đã xác thực
└── Authorization Request đang chờ
      (có thể đã bị loại sau callback)
~~~

Đừng giả định `HttpSession` tồn tại thì callback cũ phải hợp lệ. Ngược lại, `HttpSession` có thể được tạo trước login nhưng chưa có Authentication.

## 7. Các tình huống callback trùng lặp

### 7.1. Callback thứ hai đến sau callback đầu thành công

~~~text
Callback #1:
    state khớp pending request
    code được AS chấp nhận
    Spring Security tạo Authentication
    browser được redirect sang /dashboard

Callback #2:
    state không còn pending request
    hoặc code không còn dùng được
    authentication flow không thể thành công thêm một lần
~~~

Callback thứ hai có thể bị chặn ở repository hoặc token endpoint. Người dùng có thể thấy trang lỗi dù lần đầu đã tạo phiên đăng nhập hợp lệ.

Ứng dụng nên xử lý trải nghiệm này **không tiết lộ code/state**, cho phép quay về ứng dụng nếu phiên còn hợp lệ hoặc bắt đầu login mới.

### 7.2. Hai callback đồng thời

~~~text
Request A: tìm STATE_A -> có
Request B: tìm STATE_A -> cũng có thể thấy
Request A: tiến tới xử lý
Request B: tiến tới xử lý
AS: chỉ một lần đổi CODE_A có thể thành công
~~~

Nếu repository dùng thao tác đọc rồi xóa tách rời, hai luồng có thể cùng thấy state trước khi một luồng xóa.

Khi xây custom repository cho môi trường đồng thời, cần cân nhắc **atomic consume**: chỉ một request được lấy và tiêu thụ pending state thành công. Cơ chế cụ thể phụ thuộc session store, database, Redis hoặc giải pháp đồng bộ được dùng.

AS vẫn phải đảm bảo code single-use; RP cần bảo vệ thêm các side effect của mình.

### 7.3. Hai tab, hai Authorization Request riêng biệt

~~~text
Tab A:
  state=STATE_A
  verifier=VERIFIER_A

Tab B:
  state=STATE_B
  verifier=VERIFIER_B
~~~

Đây là **hai flow khác nhau**, không nhất thiết là replay. Tuy nhiên, nếu repository chỉ giữ một pending request trên mỗi `HttpSession`, tab B có thể thay thế request của tab A. Callback A khi đó không tìm được request gốc.

Nếu sản phẩm cần đăng nhập song song qua nhiều tab, repository phải hỗ trợ nhiều pending requests theo state, có TTL, giới hạn số lượng và ràng buộc session. **Không tắt kiểm tra state** để hỗ trợ nhiều tab.

### 7.4. Session cũ hoặc sai browser

Nếu browser xóa cookie, session hết hạn hoặc callback được mở ở browser khác, Portal có thể mất Authorization Request gốc. Dù URL vẫn có code/state, callback không được ghép vào phiên khác theo suy đoán.

Cách phục hồi là tạo Authorization Request mới với state, verifier và nonce mới nếu cần.

### 7.5. Retry sau timeout

Một proxy có thể gửi lại callback nếu response đầu thất lạc. Backend có thể đã xử lý và lưu Authentication thành công, nhưng retry vẫn dùng code cũ nên bị từ chối.

Do đó callback là một endpoint GET **có ý nghĩa một giao dịch giao thức**. Không nên retry mù chỉ vì HTTP method là GET.

## 8. Race condition khi tự lưu state

Một custom repository có thể thực hiện:

~~~text
request = store.get(state)
if request exists:
    process(request)
    store.delete(state)
~~~

Với hai request song song:

~~~text
A: get(STATE_A) -> có
B: get(STATE_A) -> có
A: process
B: process
A: delete
B: delete
~~~

Hai request đều vượt qua bước kiểm tra ban đầu. Để ngăn việc này, hệ thống có yêu cầu cao về concurrency nên dùng cơ chế **atomic get-and-delete**, transaction hoặc locking phù hợp.

Khi thiết kế kho request đang chờ, cần xem xét:

- State có đủ entropy và được gắn với phiên/browser đáng tin cậy.
- Client registration và redirect URI được giữ đúng ngữ cảnh.
- State hết hạn có được dọn hay không.
- Một phiên được giữ tối đa bao nhiêu pending requests.
- Thao tác tiêu thụ có an toàn với nhiều instance không.
- Lỗi hoặc cancel có để lại state có thể tái dùng ngoài ý muốn không.

Một map trong memory một JVM không tự cung cấp cơ chế đồng bộ giữa các node.

## 9. Load balancer và session store

Giả sử:

~~~text
Browser
  |
Load balancer
  |----- Portal A
  |----- Portal B
~~~

Tab bắt đầu login qua Portal A, nơi lưu pending request vào `HttpSession` nội bộ. Callback lại được gửi đến Portal B không có cùng session data.

Kết quả có thể là lỗi **không tìm thấy authorization request**, dù `code` và `state` là giá trị do OP hợp lệ phát hành.

Các phương án:

- Kho session chia sẻ/đồng bộ, chẳng hạn một triển khai Spring Session phù hợp.
- Session affinity khi thực sự đáp ứng yêu cầu kiến trúc, hiểu giới hạn khi instance lỗi/scale.
- Cookie, domain/path, `Secure`/`SameSite` và cấu hình reverse proxy nhất quán.
- Redirect URI public chính xác đã đăng ký với OP.
- Bảo vệ forwarded headers để không dựng URL từ host không tin cậy.

Không được bỏ `state` để “chữa” việc session bị mất giữa các instance.

## 10. Cấu hình Spring Boot và Servlet Login

### 10.1. Dependency và client registration

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Một ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

`corporate` là registration ID trong Spring; callback thực tế phải được OP cho phép. `openid` cho biết đây là OIDC Login, còn client ID/secret được cấp riêng trong quá trình đăng ký client tại provider.

### 10.2. Filter chain mặc định

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login-error", "/assets/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Spring Security xử lý callback theo flow; ứng dụng không cần tự tạo một controller đọc `code` và gọi token endpoint.

### 10.3. Điều hướng sau login thành công

Một cách giảm refresh callback là đưa browser tới URL thường sau khi login. Ví dụ cấu hình success URL:

~~~java
http.oauth2Login(login -> login
        .defaultSuccessUrl("/dashboard", true));
~~~

Phương thức này đặt trong cấu hình `HttpSecurity` khi ứng dụng muốn luôn chuyển tới `/dashboard`. Nếu muốn trở về saved request, có thể giữ behavior mặc định.

Browser được đưa khỏi URL nhạy cảm:

~~~text
/login/oauth2/code/corporate?code=...&state=...
~~~

và chuyển đến:

~~~text
/dashboard
~~~

Refresh `/dashboard` không dùng lại authorization code.

### 10.4. Xử lý callback lỗi bằng failure handler

Có thể cấu hình một lỗi login chung:

~~~java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

http.oauth2Login(login -> login
        .failureHandler(
                new SimpleUrlAuthenticationFailureHandler("/login-error")));
~~~

Đây là đoạn cấu hình minh họa trong `HttpSecurity`, không phải class hoàn chỉnh độc lập. Trang `/login-error` nên hiển thị thông báo chung:

> Yêu cầu đăng nhập không còn hiệu lực hoặc không thể hoàn tất. Hãy thử đăng nhập lại.

Đừng đưa `code`, `state`, `code_verifier`, ID token, access token hoặc session cookie vào query của trang lỗi hay thông báo người dùng.

**Failure handler không phải nơi để thử lại code cũ.** Nếu cần phục hồi, bắt đầu một flow mới có state/verifier mới.

## 11. Phân biệt lỗi callback

| Dấu hiệu | Tầng phát hiện | Nguyên nhân có thể |
|---|---|---|
| `state` thiếu/không khớp | RP/repository | Sai flow, callback giả, session cũ |
| Không có request gốc | RP/repository | Đã xử lý, session hết hạn hoặc mất state giữa node |
| `invalid_grant` | AS token endpoint | Code đã dùng, hết hạn, sai client/redirect URI hoặc invalid grant khác |
| PKCE verifier sai | AS token endpoint | Verifier không khớp challenge |
| `invalid_client` | AS token endpoint | Client authentication không đúng |
| ID token `nonce` sai | RP/OIDC validation | Token không phù hợp request gốc |
| ID token sai `iss`, `aud`, chữ ký | RP/OIDC validation | Kết quả xác thực không đáng tin cậy |
| `access_denied` | AS authorization response | Người dùng từ chối hoặc OP không cấp quyền |

Không nên tự động kết luận “bị hack” khi thấy `invalid_grant`, nhưng cũng không bỏ qua nếu lỗi xuất hiện bất thường với tần suất cao.

### 11.1. Callback thứ hai hiển thị lỗi dù lần đầu thành công

Một callback cũ có thể khiến UI báo lỗi trong khi session từ request đầu vẫn hợp lệ, hoặc failure handling tùy cấu hình có thể ảnh hưởng trạng thái khác.

Cách xử lý hợp lý:

1. Không coi callback cũ là yêu cầu login mới hợp lệ.
2. Không đổi lại code đã dùng.
3. Trang lỗi có lối quay về ứng dụng hoặc bắt đầu đăng nhập mới.
4. Nếu kiểm tra phiên hiện tại, chỉ tin `Authentication` thực sự đã được Spring Security xác lập.
5. Không tự xóa mọi dữ liệu nghiệp vụ vì một callback URL cũ bị tải lại.

Tránh điều hướng lỗi về URL được bảo vệ rồi liên tục khởi động đăng nhập lại, tạo vòng lặp redirect.

## 12. Giới hạn của chống replay ở callback

### 12.1. Access token không phải authorization code

Sau khi đổi code, client có thể nhận access token dùng gọi API. **Code single-use không làm bearer access token trở thành single-use.**

Nếu access token bị lộ, bên giữ token có thể cố sử dụng lại nó trong thời hạn còn hiệu lực, trừ khi Resource Server hoặc cơ chế token-binding ngăn chặn.

Resource Server phải có chính sách riêng về chữ ký/kiểm tra token, issuer, audience, scope, expiry và quyền nghiệp vụ. Có thể sử dụng sender-constrained tokens như mTLS/DPoP ở hệ thống hỗ trợ.

### 12.2. Refresh token có replay policy riêng

Refresh token, nếu được cấp, có vòng đời và quy tắc sử dụng khác authorization code. Một số Authorization Server sử dụng **refresh token rotation** và phát hiện token reuse.

Không suy ra rằng mọi refresh token đều single-use chỉ vì code ở bước callback single-use.

### 12.3. `state` không thay thế CSRF bảo vệ nghiệp vụ

`state` chống login CSRF/correlation trong authorization flow. Nó không tự bảo vệ:

- Form thay đổi dữ liệu dựa trên session cookie.
- POST phê duyệt hay thanh toán.
- Session fixation.
- Quyền truy cập từng bản ghi.
- Tấn công tái sử dụng bearer access token.

Ứng dụng web dựa trên session vẫn cần chính sách CSRF thích hợp; API vẫn phải xác minh token và quyền.

### 12.4. Login thành công không làm nghiệp vụ idempotent

Một success handler có thể tạo user nội bộ hoặc ghi nhật ký. Những side effect này nên có quy tắc riêng:

- Dùng `issuer + subject` làm khóa liên kết tài khoản phù hợp.
- Áp unique constraint/upsert cho việc tạo account.
- Dùng correlation ID hoặc idempotency key khi cần ngăn ghi trùng nghiệp vụ.
- Không thực hiện chuyển tiền/phê duyệt đơn chỉ vì OIDC callback thành công.

Ngay cả khi mỗi authorization code chỉ dùng một lần, người dùng vẫn có thể khởi tạo **nhiều flow login mới hợp lệ**. Nghiệp vụ phải kiểm soát việc thực hiện trùng độc lập với OAuth/OIDC.

## 13. Quan sát và chẩn đoán an toàn

Khi xử lý sự cố callback, nên theo dõi:

- Thời điểm bắt đầu flow và thời điểm callback.
- Registration ID, tên môi trường, instance phục vụ request.
- Có/không pending Authorization Request phù hợp.
- Loại lỗi đã chuẩn hóa và tầng phát hiện.
- Có nhiều callback gần nhau hoặc nhiều flow trong cùng session không.
- Load balancer, session store, cookie và redirect URI public.
- Correlation ID riêng được thiết kế không phải credential.

**Không ghi nguyên văn**:

~~~text
authorization code
state
code_verifier
nonce
access token
refresh token
ID token
client secret
session ID hoặc session cookie
~~~

Nếu cần nhận biết callback trùng trong telemetry, nên dùng định danh sự kiện riêng hoặc fingerprint được kiểm soát để không thể dùng như credential.

### Quy trình điều tra

1. Browser refresh `/login/oauth2/code/...` hay `/dashboard`?
2. Callback đầu đã tạo Authentication/session thành công chưa?
3. Callback sau bị chặn vì mất state hay đã gửi token request đến OP?
4. Nếu `invalid_grant`, kiểm tra các giả thuyết code hết hạn, code đã dùng, sai client/redirect URI/PKCE.
5. Có hai flow từ hai tab hoặc cùng một callback được gửi hai lần không?
6. Session có được chia sẻ giữa instance, cookie có đến backend không?
7. Có custom repository hoặc failure/success handler làm mất state hoặc tạo side effect không?

Chẩn đoán dựa trên trạng thái đã giảm nhạy cảm; không cần đưa code/token thật ra log.

## 14. Tình huống thực hành

**Tình huống A — Refresh callback:** Browser gửi lại URL `code=CODE_A&state=STATE_A` sau khi login thành công. Giữ nguyên kiểm tra state/code, trả lỗi hoặc trang phục hồi phù hợp, và chuyển browser sang trang ứng dụng sau login.

**Tình huống B — Hai tab:** Tab A và B có state khác nhau. Nếu repository không hỗ trợ pending requests đồng thời, callback của một tab có thể thất bại. Cần repository multi-state có TTL và cơ chế tiêu thụ một lần nếu yêu cầu sản phẩm cần cả hai tab.

**Tình huống C — Hai node:** Node A lưu Authorization Request, node B không thấy khi callback đến. Sửa kho session hoặc routing; không bỏ correlation.

**Tình huống D — Hai callback đồng thời:** Hai thread cùng đọc state trước khi bị xóa. AS vẫn phải thực thi code single-use; custom repository của RP cần chống race và kiểm soát side effect.

**Tình huống E — `invalid_grant` ở lần đầu:** Không mặc định là replay. Kiểm tra expiry, redirect URI, client registration, PKCE, request song song và thời điểm token request.

**Tình huống F — URL callback bị lộ:** Code đã dùng không cấp token thêm lần nữa. Với code chưa dùng, PKCE, client authentication, redirect URI binding và HTTPS giảm nguy cơ chiếm code; tránh log/referrer làm lộ query.

## 15. Câu hỏi tự kiểm tra

**1. Authorization code có thể đổi token hai lần không?**  
Không. Code ngắn hạn, single-use; AS phải từ chối code đã dùng.

**2. `state` và `nonce` khác nhau thế nào?**  
State ràng buộc callback với Authorization Request; nonce ràng buộc ID token với OIDC Authentication Request khi dùng nonce.

**3. Callback trùng luôn đến token endpoint và nhận `invalid_grant`?**  
Không. Repository tại RP có thể từ chối sớm vì không tìm thấy Authorization Request gốc.

**4. `invalid_grant` có chứng minh một cuộc tấn công replay?**  
Không. Code hết hạn, sai client/redirect URI hoặc điều kiện grant khác cũng có thể gây lỗi này.

**5. Vì sao callback lỗi khi chạy hai instance?**  
Pending request/session có thể chỉ tồn tại ở instance khởi tạo login; cần chia sẻ state hoặc routing phù hợp.

**6. Có thể bỏ kiểm tra state để hỗ trợ hai tab?**  
Không. Hãy thiết kế repository lưu nhiều pending requests được ràng buộc bằng state và phiên.

**7. Code single-use có chống replay mọi API không?**  
Không. Access token và API có cơ chế bảo vệ riêng.

**8. Tại sao cần idempotency ở nghiệp vụ dù OAuth đã có single-use?**  
Vì người dùng và hệ thống có thể gửi lại thao tác nghiệp vụ hoặc khởi động nhiều flow login hợp lệ khác nhau; code single-use không bảo đảm một business action chỉ chạy một lần.

**9. Nên làm gì khi callback cũ hết hiệu lực?**  
Không thử lại code cũ; cho người dùng quay về ứng dụng nếu đã có phiên hợp lệ hoặc bắt đầu flow authorization mới.

## Ghi nhớ

**Authorization code** có thời hạn ngắn và chỉ đổi token một lần. **`state`** ràng buộc callback với request đang chờ ở RP. **`nonce`** ràng buộc ID token với yêu cầu OIDC khi áp dụng, còn **PKCE** ràng buộc code với verifier khi token exchange.

Spring Security Servlet có filter và `OAuth2AuthorizationRequestRepository` để xử lý correlation. Khi cần custom repository cho nhiều tab, nhiều node hoặc callback song song, phải xử lý TTL, session binding và tiêu thụ state một lần. Sau login thành công, chuyển browser sang URL ứng dụng bình thường; lỗi callback trùng phải được phục hồi an toàn.

Các biện pháp này bảo vệ **luồng đăng nhập**. Chúng không thay thế bảo vệ bearer token tại Resource Server, quản lý session, CSRF của ứng dụng web hoặc idempotency của thao tác nghiệp vụ.
