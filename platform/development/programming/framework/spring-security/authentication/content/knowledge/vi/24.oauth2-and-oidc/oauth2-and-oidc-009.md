# Phân biệt ID token, access token, refresh token và phiên đăng nhập cục bộ

## 1. Bốn đối tượng có thể cùng tồn tại sau một lần đăng nhập

Khi người dùng đăng nhập vào một ứng dụng Spring Boot qua OpenID Connect (OIDC), có thể xuất hiện **ID token**, **access token**, **refresh token** và một **phiên đăng nhập cục bộ** (`HttpSession` với ứng dụng Servlet). Chúng có mục đích, bên phát hành, bên tiêu thụ, thời hạn và ranh giới tin cậy khác nhau.

Ví dụ: Alice truy cập `https://shop.example.test`, ứng dụng chuyển trình duyệt tới một OpenID Provider (OP) để đăng nhập. Sau khi nhận authorization code, ứng dụng đổi code tại token endpoint để nhận ID token, access token và đôi khi có refresh token. Spring Security xác thực kết quả OIDC, tạo `Authentication` và có thể lưu `SecurityContext` trong session HTTP. Trình duyệt được cấp cookie session để đi tiếp vào các trang của **ứng dụng**, còn access token được dùng khi **client gọi resource server**.

Điểm cần nhớ:

- **ID token trả lời:** “OP đã xác thực *ai* cho OAuth/OIDC client này, theo sự kiện đăng nhập nào?”.
- **Access token trả lời:** “Client đang được phép gọi *tài nguyên/API nào*, với quyền nào và trong thời hạn nào?”.
- **Refresh token trả lời:** “Client có thể xin access token mới từ authorization server theo grant hiện có hay không?”.
- **Phiên cục bộ trả lời:** “Ứng dụng đang duy trì trạng thái đăng nhập nào giữa các HTTP request của trình duyệt?”.

**Không có quan hệ một–một bắt buộc giữa bốn đối tượng.** Một ứng dụng session-based vẫn có thể phục vụ trang nội bộ sau khi access token gọi API bên ngoài hết hạn; một API stateless có thể nhận access token hợp lệ mà không tồn tại bất kỳ `HttpSession` nào; refresh token có thể không được cấp.

## 2. Bảng so sánh nhanh

| Tiêu chí | ID token (OIDC) | Access token (OAuth 2.0) | Refresh token (OAuth 2.0) | Phiên đăng nhập cục bộ |
| --- | --- | --- | --- | --- |
| Mục đích chính | Khẳng định sự kiện xác thực người dùng cho **OIDC client** | Cấp quyền truy cập **resource server/API** | Xin access token mới tại **token endpoint** | Duy trì trạng thái đăng nhập/`SecurityContext` giữa request đến ứng dụng |
| Bên phát hành/tạo | OpenID Provider | Authorization server | Authorization server (nếu chính sách cấp) | Ứng dụng và session container/repository |
| Bên tiêu thụ trực tiếp | OIDC client/relying party | Resource server đích; client mang token để gọi API | Authorization server; client giữ bí mật | Ứng dụng nhận cookie session của trình duyệt và tìm trạng thái phía server |
| Đối tượng mà token hướng tới | `aud` thường gồm `client_id` của relying party | Resource/API đích, theo thiết kế authorization server | Gắn với client/grant; không dùng làm credential cho resource server | Chính ứng dụng hoặc cụm ứng dụng chia sẻ session store |
| Định dạng | JWT có claims và chữ ký/biện pháp bảo vệ phù hợp OIDC | JWT hoặc opaque; cũng có định dạng khác theo hệ thống | Thường opaque, không buộc là JWT | Cookie chứa session ID; dữ liệu phiên nằm ở server hoặc kho session |
| Thời hạn | `exp` của ID token | `exp` hoặc TTL/token policy | Thời hạn, rotation/revocation tùy provider | Idle timeout, absolute timeout, logout, invalidation theo ứng dụng |
| Chứng minh điều gì | OP đã xác thực subject cho client theo OIDC | Quyền truy cập resource tương ứng nếu token **được xác minh hợp lệ** | Có thể yêu cầu cấp token mới khi còn hợp lệ và đúng client/grant | Trạng thái local còn tồn tại và được ứng dụng chấp nhận |
| Truyền đi đâu | Đến OIDC client qua flow được chuẩn hóa | Ví dụ `Authorization: Bearer ...` tới API đích | Chỉ tới token endpoint qua kênh bảo mật phù hợp | Cookie gửi về domain/path tương ứng; không tự gửi tới API khác |
| Lỗi thường gặp | Dùng ID token làm Bearer token cho API | Dùng access token làm bằng chứng đăng nhập client mà không xét audience | Đưa refresh token cho browser/JS hay resource server | Tưởng logout tại OP hoặc token hết hạn sẽ tự xóa session local |

Bảng trên mô tả mô hình điển hình cho **web app dạng server-side/BFF**. Với SPA hoặc native app, nơi lưu token và session có thể khác; vẫn phải giữ nguyên ranh giới xác thực, ủy quyền, refresh và quản lý phiên. Không coi mọi chuỗi trông giống JWT là cùng một loại token.

## 3. OAuth 2.0 và OIDC có vai trò khác nhau

**OAuth 2.0** là framework ủy quyền: resource owner cho phép một client truy cập một số tài nguyên do resource server quản lý. Bản thân OAuth 2.0 không định nghĩa một giao thức đăng nhập người dùng chuẩn bằng access token.

**OpenID Connect** xây trên OAuth 2.0 để định nghĩa đăng nhập liên kết và thông tin định danh. OIDC bổ sung khái niệm **ID token**, `openid` scope, UserInfo endpoint, yêu cầu xác thực/validation và những claim như `sub`, `iss`, `aud`. Trong web app hiện đại, thường dùng **Authorization Code flow**, với PKCE khi phù hợp, thay vì đặt token dài hạn trong URL.

Vai trò trong một hệ thống:

- **End user (Alice):** người dùng đăng nhập.
- **User agent (browser):** theo redirect và gửi cookie.
- **OIDC client / relying party (Spring Boot web app):** nhận authorization code, đổi token, kiểm tra ID token, tạo trạng thái đăng nhập local.
- **OpenID Provider / Authorization server (IdP):** xác thực Alice, phát hành token theo policy.
- **Resource server (API):** chỉ nhận và xác minh access token phù hợp với API.
- **Session repository:** lưu/khôi phục trạng thái local cho các request trình duyệt của web app.

Trong `client_credentials`, access token có thể đại diện cho **ứng dụng**, không cho một người dùng. Vì vậy, thấy `sub` hoặc scope trong access token không tự động có nghĩa người dùng đã đăng nhập qua OIDC.

## 4. Luồng đầy đủ: đăng nhập một lần, bốn vòng đời khác nhau

```text
Browser                    Spring Boot web client           OP / Authorization Server        Resource API
   |                                |                               |                         |
   | GET /orders                    |                               |                         |
   |------------------------------->| chưa có local login           |                         |
   |<--- 302 đến /authorize --------|                               |                         |
   |---------------------------- authorize + state + PKCE ------->|                         |
   |<------------------------- login/consent và redirect code ----|                         |
   | GET /login/oauth2/code/...     |                               |                         |
   |------------------------------->| POST /token: code + verifier |                         |
   |                                |------------------------------>|                         |
   |                                |<--- id_token, access_token,   |                         |
   |                                |     refresh_token? ----------|                         |
   |                                | validate OIDC ID token       |                         |
   |                                | tạo Authentication           |                         |
   |                                | lưu local SecurityContext    |                         |
   |<----- Set-Cookie: JSESSIONID --|                               |                         |
   |                                |                               |                         |
   | GET /orders + JSESSIONID       |                               |                         |
   |------------------------------->| load local session           |                         |
   |<----- HTML của /orders --------|                               |                         |
   |                                |                               |                         |
   |                                | GET /orders-api Bearer access_token ---------------------->|
   |                                |<---------------------------- response API -----------------|
   |                                |                               |                         |
   |                                | access token hết hạn          |                         |
   |                                | POST /token với refresh token (nếu có, còn hợp lệ)        |
   |                                |------------------------------>|                         |
   |                                |<-- access_token mới ----------|                         |
   |                                | local session có thể vẫn còn |                         |
```

Dòng `refresh_token?` có dấu hỏi vì authorization server **không bắt buộc** cấp refresh token. Việc nhận refresh token có thể tùy `offline_access`, client type, consent, rotation, lifetime và provider policy. Nếu không có refresh token, client có thể phải thực hiện một authorization flow mới khi cần gọi API.

**Phân biệt hai chiều đăng nhập/truy cập:** browser → Spring web app thường dùng cookie session; Spring web app → resource API dùng access token; không gửi ID token tới API như access token. Với mô hình BFF, backend có thể giữ access/refresh token bên server, giảm lộ credential cho JavaScript trong browser.

## 5. ID token: xác nhận danh tính cho OIDC client

ID token là **JWT** theo OpenID Connect. Nó được phát hành bởi OP cho client đã tham gia flow. Một payload chỉ mang tính minh họa:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": "web-client",
  "exp": 1796205600,
  "iat": 1796202000,
  "nonce": "nonce-registered-by-client"
}
```

Các con số timestamp minh họa; không sử dụng payload này làm token thật. Người đọc có thể **decode** payload JWT, nhưng decode Base64URL **không phải xác thực**. Client phải kiểm tra ID token theo profile/flow OIDC áp dụng, gồm ít nhất:

1. **Chữ ký, thuật toán và khóa tin cậy:** kiểm tra theo metadata/JWKS của OP đã cấu hình; không chấp nhận thuật toán tùy ý do token tự khai báo.
2. **`iss`:** phải trùng chính xác issuer tin cậy; tránh tin nhầm token từ tenant/provider khác.
3. **`aud`:** phải chứa `client_id` của chính OIDC client nhận ID token; khi có nhiều audience, áp dụng thêm điều kiện `azp` phù hợp chuẩn.
4. **`exp`, `iat`:** kiểm tra thời gian hợp lệ và quy tắc clock skew. Nếu flow/policy cần `auth_time`, kiểm tra thêm mức độ mới của sự kiện đăng nhập.
5. **`nonce`:** khi authorization request đã gửi nonce, kiểm tra nonce trong ID token khớp giá trị được lưu và gắn với phiên login flow; cùng với `state` giúp chống nhầm lẫn request/response, nhưng **`state` và `nonce` là hai cơ chế khác nhau**.
6. **`sub`:** là định danh subject trong phạm vi issuer, thường ổn định hơn email hoặc tên hiển thị; ứng dụng nên dùng khóa ghép `(iss, sub)` khi liên kết người dùng.

**Không dùng `id_token` làm `Authorization: Bearer` cho resource API.** `aud` của nó thường là OIDC client, không phải API; một resource server nhận nhầm sẽ phá ranh giới audience và token type. Ngược lại, access token phát hành cho API không thay thế quy trình kiểm chứng ID token của OIDC client.

**ID token hết hạn có khiến web app logout ngay không?** Không tự động. `exp` xác định hiệu lực của **token** trong bối cảnh xác thực/validation, nhưng một web app đã hoàn tất login có thể duy trì `HttpSession` theo thời hạn riêng. Nếu nghiệp vụ yêu cầu re-authentication hoặc freshness (giao dịch giá trị cao), phải cấu hình policy tương ứng; không suy từ `exp` rằng session local đã bị hủy.

## 6. Access token: quyền truy cập API, không phải cookie đăng nhập

Access token là credential dùng để truy cập **resource server**. Client có thể gửi:

```http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-redacted>
```

Đây là request mẫu, **không phải một token thật**. Resource server phải xác minh token theo format:

- **JWT access token:** kiểm tra chữ ký/thuật toán, issuer, thời gian, **audience/resource đích**, các yêu cầu về token type theo profile áp dụng, scope/authority và policy của endpoint. Không chỉ kiểm tra `sub`.
- **Opaque access token:** API không thể tin từ việc tự phân tích chuỗi; cần cơ chế introspection hoặc giải pháp được authorization server thiết kế để xác định active status và metadata.
- **Bearer token:** ai chiếm được credential hợp lệ có thể sử dụng trong giới hạn token. Bảo vệ bằng TLS, thời hạn ngắn, scope tối thiểu, audience restriction và sender-constrained token (DPoP/mTLS) khi cần.

**Thời hạn access token độc lập với login session.** Khi access token hết hạn, cuộc gọi API bằng token cũ có thể bị từ chối `401`; web app vẫn có thể đang đăng nhập local. Client có refresh token hợp lệ có thể xin access token mới và gọi lại API; refresh thất bại có thể làm chức năng gọi API không hoạt động, nhưng không mặc nhiên xóa mọi session của web app.

**Scope ≠ role local:** token có scope `orders:read` không chứng minh role `ROLE_ADMIN` trong ứng dụng. Spring Security Resource Server có thể ánh xạ scope thành authority `SCOPE_orders:read`, nhưng quyền cuối cùng vẫn theo chính sách trên từng API, tenant và tài nguyên cụ thể. Cần kiểm tra quyền sở hữu bản ghi (object-level authorization) ngoài scope.

**Phản hồi thường gặp:** thiếu/sai/hết hạn token → `401 Unauthorized` (API có thể gửi `WWW-Authenticate: Bearer ...`); token hợp lệ nhưng không đủ quyền → `403 Forbidden`. Các policy khác, CSRF hay gateway có thể ảnh hưởng mã phản hồi; không đoán trạng thái chỉ từ một ví dụ.

## 7. Refresh token: cấp lại quyền truy cập, không xác thực lại user trong web session

Refresh token được client đưa tới **token endpoint của authorization server**, theo grant `refresh_token`. Kết quả có thể là access token mới, và tùy server là refresh token mới. Refresh token **không được gửi cho resource API hoặc dùng làm cookie `JSESSIONID`**.

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-redacted>
```

Đoạn request chỉ cho thấy *hướng trao đổi*; trong triển khai thật có thể phải xác thực client, dùng sender constraint và các trường HTTP khác theo giao thức. Không lưu hoặc in refresh token thật trong log, URL, exception, trace hay response JSON trả về browser.

Các đặc điểm quan trọng:

- Authorization server quyết định **có cấp refresh token hay không**; không giả định login OIDC nào cũng có.
- Refresh token có thể bị revoke, hết hạn do inactivity, logout hoặc thay đổi chính sách; việc còn giữ chuỗi token **không chứng minh** refresh vẫn thành công.
- **Rotation:** sau mỗi lần refresh, server có thể cấp refresh token mới và vô hiệu token cũ; client phải cập nhật bản được lưu theo cách an toàn và tránh race khi nhiều request cùng refresh.
- **Replay detection:** nếu token đã rotate bị tái sử dụng trái phép, server có thể phát hiện và thu hồi token family/grant theo policy. RFC 9700 yêu cầu refresh token dành cho public client phải được sender-constrained hoặc dùng rotation.
- **Bảo vệ lưu trữ:** với ứng dụng backend confidential client, thường giữ token phía server trong store được giới hạn truy cập và mã hóa/kiểm soát truy cập phù hợp. Với SPA/native app, phải dùng phương án an toàn theo client type, không coi localStorage là vùng bí mật của backend.
- **Refresh token != “giữ đăng nhập vô thời hạn”:** việc refresh thành công không tự gia hạn `HttpSession`, cũng không chứng minh người dùng vừa thực hiện lại MFA hoặc đăng nhập tương tác tại OP.

Đôi khi nhà cung cấp trả `invalid_grant` khi refresh token hết hạn, bị thu hồi hoặc không còn hợp lệ. Client cần xử lý bằng cách dừng gọi API bằng token lỗi, xóa/đánh dấu trạng thái authorized client phù hợp và yêu cầu authorization lại nếu cần; không lặp refresh vô hạn hay tiếp tục sử dụng access token đã hết hạn.

## 8. Phiên đăng nhập cục bộ: trạng thái ứng dụng, không phải token của OP

Trong ứng dụng **Spring Security Servlet** dùng `oauth2Login()`, sau khi OIDC login thành công, Spring Security thường duy trì một `Authentication` đại diện cho `OidcUser` trong `SecurityContext`. Nếu cấu hình mặc định cho phép stateful login, context này thường được lưu qua `SecurityContextRepository`, điển hình là `HttpSessionSecurityContextRepository`.

Trình duyệt chỉ cần gửi cookie phiên của ứng dụng trên request sau:

```http
GET /account HTTP/1.1
Host: shop.example.test
Cookie: JSESSIONID=<opaque-session-id>
```

Cookie ở đây là **chìa khóa tra cứu session local**, không chứa JWT ID/access token theo mặc định và không chứng minh một access token còn sống. `HttpSession` có thể chứa `SPRING_SECURITY_CONTEXT` cùng dữ liệu khác theo ứng dụng. Cách lưu thực tế có thể là bộ nhớ node, Spring Session/Redis hoặc repository tùy biến.

### Vòng đời riêng

- **Idle timeout:** không có request trong thời gian quy định thì session có thể hết hạn; không đồng nghĩa token OP bị revoke.
- **Absolute timeout:** ứng dụng có thể đặt thời hạn tối đa bất kể hoạt động để buộc đăng nhập lại; cần triển khai riêng theo policy.
- **Logout local:** xóa authentication và invalidate session; IdP có thể vẫn giữ SSO login, nên truy cập lại có thể đăng nhập liên kết nhanh mà không cần nhập mật khẩu.
- **Logout tại OP:** OP hết session hoặc báo logout không bảo đảm local app biết ngay nếu không có front-channel/back-channel logout, token/session introspection hoặc integration tương ứng.
- **Session fixation protection:** sau đăng nhập, ứng dụng có thể đổi session ID để tránh fixation. Không lấy việc session ID đổi làm dấu hiệu ID token được refresh.
- **Cookie security:** dùng HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp flow, domain/path hạn chế; với web app dùng cookie auth, áp dụng bảo vệ **CSRF** cho thao tác thay đổi trạng thái.

**Lưu ý về Spring Security 6+:** một filter tự dựng `Authentication` và đặt vào `SecurityContextHolder` có thể cần gọi `SecurityContextRepository.saveContext(...)` để lưu đúng giữa request. `oauth2Login()` có cơ chế lưu context khi xác thực; đừng suy rằng mọi custom authentication tự được lưu chỉ vì set holder.

### Authentication và OAuth2AuthorizedClient là hai kho dữ liệu logic khác nhau

- `SecurityContext` / `Authentication`: “web app đang coi request này là ai và có quyền gì?”.
- `OAuth2AuthorizedClient`: quan hệ giữa **client registration**, principal, **access token** và có thể **refresh token**; Spring Security quản lý qua `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService`.
- `OidcUser.getIdToken()`: ID token/claims gắn với OIDC principal đã đăng nhập.
- `HttpSession`: nơi có thể lưu các trạng thái trên tùy cấu hình, nhưng không đồng nhất về vòng đời.

`OAuth2AuthorizedClientManager` có thể quản lý acquire/refresh access token nếu grant/provider hỗ trợ. Việc access token được refresh trong authorized-client repository **không tự đổi** `Authentication` hoặc tạo lại phiên đăng nhập OIDC của người dùng.

## 9. Các timeline dễ nhầm lẫn

| Thời điểm / sự kiện | ID token | Access token | Refresh token | Session cục bộ và kết quả |
| --- | --- | --- | --- | --- |
| Vừa OIDC login thành công | Client đã xác thực ID token | Có thể nhận để gọi API/UserInfo | Có thể có hoặc không | Tạo `Authentication`; trình duyệt bắt đầu dùng cookie session |
| 10 phút sau, access token hết hạn | Không cần dùng lại cho từng request trang | Token cũ không nên được API chấp nhận | Nếu còn hợp lệ có thể xin token mới | Session web có thể vẫn đăng nhập |
| ID token đã qua `exp` | Không còn dùng nó như một ID token mới chưa hết hạn | Có thể vẫn hợp lệ | Có thể vẫn hợp lệ | Session có thể tiếp tục đến khi app yêu cầu re-auth |
| Refresh token bị revoke | Không nhất thiết thay đổi | Token đã cấp có thể còn hiệu lực tới `exp`/thu hồi theo API | Refresh thất bại | Session local có thể còn; nghiệp vụ cần chọn policy |
| User logout chỉ ở web app | Không có token mới từ thao tác logout local | Có thể còn hiệu lực cho tới khi hết hạn/revoke | Có thể cần revoke/cleanup riêng | Session bị invalidated và context local bị xóa |
| User logout tại OP | OP không còn SSO login | Access token có thể chưa bị vô hiệu ở mọi API | Có thể bị revoke theo OP policy | App cần cơ chế đồng bộ để chấm dứt session local |
| Browser xóa `JSESSIONID` | Không tự revoke | Không tự revoke | Không tự revoke | Browser mất khả năng tham chiếu session cũ; server có thể còn session đến timeout |
| API nhận token từ `client_credentials` | Không liên quan đăng nhập user | Đại diện client/grant | Thường không cần refresh trong flow này | Không yêu cầu user session |

**Không áp đặt cùng một TTL** cho mọi loại token/session chỉ vì cùng xuất hiện sau đăng nhập. Thời hạn cần được thiết kế theo mức rủi ro, độ nhạy API, yêu cầu xác thực lại, UX và khả năng revoke.

## 10. Ví dụ Java 17 chạy độc lập để kiểm tra tính độc lập của vòng đời

Đoạn sau **không phải thư viện xác minh JWT, không liên hệ IdP và không tạo session thật**. Nó mô phỏng một trạng thái ứng dụng để thấy access/ID token hết hạn không tự thay đổi biến “session local còn hoạt động”.

Lưu thành `TokenLifetimeExample.java`:

```java
import java.time.Instant;

public class TokenLifetimeExample {

    record Snapshot(
        boolean localSessionActive,
        Instant idTokenExpiresAt,
        Instant accessTokenExpiresAt,
        boolean refreshTokenPresent
    ) {}

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        Snapshot state = new Snapshot(
            true,
            now.minusSeconds(60),
            now.minusSeconds(30),
            true
        );

        System.out.println("localSessionActive="
            + state.localSessionActive());
        System.out.println("idTokenExpired="
            + !now.isBefore(state.idTokenExpiresAt()));
        System.out.println("accessTokenExpired="
            + !now.isBefore(state.accessTokenExpiresAt()));
        System.out.println("refreshTokenPresent="
            + state.refreshTokenPresent());
        System.out.println("canInferRefreshWorks=false");
    }
}
```

Chạy với JDK 17+:

```bash
javac TokenLifetimeExample.java
java TokenLifetimeExample
```

Stdout chính xác:

```text
localSessionActive=true
idTokenExpired=true
accessTokenExpired=true
refreshTokenPresent=true
canInferRefreshWorks=false
```

Việc có refresh token trong snapshot **không có nghĩa nó còn hợp lệ**. Việc local session active cũng không thay thế các kiểm tra authorization tại endpoint. Ví dụ cố định `now` để dễ tái lập; ứng dụng thực phải dùng clock đáng tin và các validator theo protocol.

## 11. Minh họa trong Spring Security: web login và resource API tách biệt

Ví dụ bên dưới mô tả **Spring Boot Servlet, Java 17+, Spring Security 6+**. Hai `SecurityFilterChain` đại diện cho hai cách xác thực trong **cùng ứng dụng minh họa**: `/web/**` dùng OIDC login/session, `/api/**` dùng JWT bearer token. Khi triển khai, client registration và issuer/JWK của IdP phải là các giá trị thật đã tin cậy.

Thêm các dependency vào dự án Spring Boot đã cấu hình plugin/BOM tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Ví dụ `application.yml` của một **môi trường đã có OIDC provider**; thay URL/ID và cấp secret từ secret manager/env (không commit client secret thật):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web:
            provider: demo-idp
            client-id: web-client-id
            client-secret: demo-secret-from-secure-config
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          demo-idp:
            issuer-uri: https://idp.example.test/realms/demo
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

Đây là **cấu hình mẫu**, không thể thực thi login thật với domain `example.test`. Với client public/PKCE, cách cấu hình xác thực client khác. Với resource server, issuer validation và timestamp thôi **chưa thay thế** yêu cầu xác minh audience API; cấu hình thêm validator `aud` và token profile/permission theo issuer thực tế.

Đặt nguồn `src/main/java/example/IdentityBoundariesApplication.java`:

```java
package example;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityBoundariesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityBoundariesApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        // Chỉ /api/** dùng Bearer access token theo Resource Server.
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            // Chỉ hợp lý nếu API chain thực sự chỉ nhận Bearer,
            // không dùng cookie browser làm credential.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        // Các route khác được xử lý bằng web OIDC login.
        return http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityBoundaryController {

    @GetMapping("/web/whoami")
    Map<String, Object> web(
            @AuthenticationPrincipal OidcUser user,
            HttpServletRequest request) {
        return Map.of(
            "subject", user.getSubject(),
            "hasLocalSession", request.getSession(false) != null
        );
    }

    @GetMapping("/api/whoami")
    Map<String, String> api(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        return Map.of("subject",
            subject == null ? "(subject missing)" : subject);
    }
}
```

Đoạn mã dùng Spring Security và Boot Servlet **khi có provider thật và cấu hình cần thiết**; endpoint `/web/whoami` giả định request đã OIDC-authenticated. Nếu ứng dụng cho phép form login, Basic Auth hoặc anonymous theo các chain khác, cần kiểm tra kiểu `Authentication` trước khi dùng `OidcUser`. Import `HttpStatus` trong listing không cần dùng và có thể bỏ khi áp dụng, không ảnh hưởng Java compilation.

**Vì sao tách chain?**

1. `/api/**` là resource server: nó phải xác minh **access token dành cho API**, không tự sử dụng web session để bỏ qua bearer authentication. `STATELESS` ngăn chain API dựa vào HTTP session làm nơi lưu context; middleware khác cũng phải tôn trọng thiết kế stateless.
2. Các route web dùng `oauth2Login()`: sau OIDC login, controller đọc `OidcUser` từ `Authentication` của web session. Giá trị `hasLocalSession` chỉ cho biết session HTTP có tồn tại, **không** khẳng định refresh token hoặc access token còn hiệu lực.
3. API `/api/whoami` lấy claim `sub` từ JWT đã qua resource server filter; **không lấy ID token từ `OidcUser`**.
4. Việc API cũng dùng đúng issuer OP với OIDC client chỉ là ví dụ cấu hình; **`aud` của ID token cho `web-client-id` không được coi là audience của API**. Chỉ chấp nhận access token với audience, loại token và quyền phù hợp.

### Kiểm tra audience JWT tại resource server

Trong Spring Security khi cấu hình `JwtDecoder` tùy biến, có thể kết hợp validator issuer/thời gian mặc định và validator audience:

```java
// Đoạn minh họa tích hợp vào @Configuration, dùng issuer và
// audience được đọc từ cấu hình đã tin cậy.
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.api-audience}") String audience) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> validator =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new JwtClaimValidator<java.util.List<String>>(
                "aud",
                actual -> actual != null && actual.contains(audience))
        );

    decoder.setJwtValidator(validator);
    return decoder;
}
```

Các import bổ sung cho đoạn này:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

Đây là **snippet tích hợp**, không phải class Java độc lập. Cấu hình `app.security.issuer` và `app.security.api-audience` phải được thêm trong môi trường triển khai; việc gọi `withIssuerLocation` yêu cầu metadata/JWKS của IdP truy cập được lúc cần. Chính sách thực tế có thể cần xác minh thêm `typ`/JWT access token profile, client ID, scopes, tenant, sender constraint và revocation.

## 12. Nhìn vào OAuth2AuthorizedClient mà không làm lộ token

Spring Security biểu diễn token phía **OAuth2 client** bằng `OAuth2AuthorizedClient`. Trong một ứng dụng đã có `oauth2Login()`, có thể đọc state bằng `OAuth2AuthorizedClientService` hoặc repository phù hợp, ví dụ snippet sau:

```java
// Snippet đặt trong một @RestController được bảo vệ; các dependency
// OAuth2AuthorizedClientService, Authentication và HttpServletRequest
// do Spring cung cấp. Chỉ nên dùng endpoint nội bộ khi chẩn đoán.
@GetMapping("/internal/auth-summary")
Map<String, Object> summary(
        Authentication authentication,
        HttpServletRequest request) {

    if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
        throw new ResponseStatusException(
            HttpStatus.FORBIDDEN, "OIDC login required");
    }

    OAuth2AuthorizedClient client =
        authorizedClientService.loadAuthorizedClient(
            oauth.getAuthorizedClientRegistrationId(),
            oauth.getName());

    return Map.of(
        "localSessionPresent", request.getSession(false) != null,
        "accessTokenStored", client != null
            && client.getAccessToken() != null,
        "refreshTokenStored", client != null
            && client.getRefreshToken() != null
    );
}
```

Giả định controller có field `private final OAuth2AuthorizedClientService authorizedClientService;` được constructor-inject và import các class tương ứng. **Lưu ý:** với cấu hình dùng `OAuth2AuthorizedClientRepository` tùy biến, dữ liệu có thể không nằm trong service được tiêm; kiểm tra đúng cơ chế lưu đã cấu hình. Không đọc trực tiếp refresh/access token để in ra log/response. Việc token được **lưu** không nói gì về hiệu lực hiện tại hoặc khả năng refresh; đó là kết quả của validation/trao đổi riêng.

`OAuth2AuthorizedClientManager` có thể xin mới/refresh token cho outbound HTTP client (`RestClient`/`WebClient`), nhưng ứng dụng phải chọn scope/grant/authorized-client repository phù hợp. Tránh tự xây một scheduler gửi refresh định kỳ để “giữ login” nếu không có yêu cầu rõ ràng và cơ chế xử lý rotation, logout, failure.

## 13. Kiểm thử các ranh giới độc lập

Khi viết bài test, tạo **những tình huống có thể khác nhau**, thay vì giả định mọi token/session cùng sống và cùng chết.

| Bài test | Chuẩn bị | Assertion |
| --- | --- | --- |
| ID token sai audience | ID token có `aud=another-client` | OIDC client từ chối login, không dựng session đã xác thực |
| ID token sai issuer/nonce | `iss` hoặc `nonce` không khớp request | Login bị từ chối |
| Access token cho API khác | JWT hợp lệ về chữ ký nhưng `aud` không chứa API | Resource server từ chối (thường 401) |
| Access token hết hạn | `exp` trước thời gian hiện tại | API từ chối; web session hiện tại có thể vẫn còn |
| Thiếu scope | Token hợp lệ thiếu `orders:read` | Protected endpoint trả 403 theo policy |
| Refresh thành công/rotation | Access token hết hạn, refresh token còn dùng được | Client lưu token mới, không tái dùng refresh token cũ |
| Refresh thất bại | Refresh token đã revoke/expired | Không lặp vô hạn, yêu cầu flow mới khi cần |
| Logout local | Browser có session, gọi logout app | Session/context bị xóa; token upstream được xử lý theo policy |
| Logout IdP | OP đã kết thúc SSO session | App local được cập nhật theo back-channel/front-channel/policy |
| Cookie không có | Gọi web protected endpoint không session | Redirect tới login hoặc 401 phù hợp; bearer API không dựa vào cookie |
| API chỉ có ID token | Gửi token có audience dành cho web client | Bị từ chối bởi audience/token-type validation |
| API có access token `client_credentials` | Token đại diện ứng dụng | Không tự gán đó là session của một end user |

### MockMvc: thử ranh giới OIDC principal và JWT principal

Trong test Java có `spring-security-test`, các request post-processor `oidcLogin()` và `jwt()` giúp tạo đối tượng principal giả lập:

```java
// Đoạn phương thức đặt trong test @SpringBootTest + @AutoConfigureMockMvc.
// Giả định MockMvc đã được @Autowired và các chain/controller ở trên.
// jwt() / oidcLogin() giả lập Authentication, KHÔNG kiểm tra
// chữ ký token hoặc thực hiện OAuth2/OIDC flow thật.
@Test
void browserIdentityAndApiIdentityComeFromDifferentContexts()
        throws Exception {

    mvc.perform(get("/web/whoami")
            .with(oidcLogin().idToken(
                token -> token.claim("sub", "alice-oidc"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice-oidc"));

    mvc.perform(get("/api/whoami")
            .with(jwt().jwt(token -> token.subject("service-jwt"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("service-jwt"));
}
```

Các static import chính dùng trong test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

**Ý nghĩa giới hạn:** test trên chứng minh controller/authorization dùng đúng principal khi đã mô phỏng đăng nhập, **không chứng minh** validator của ID token hay JWT từ IdP thực chạy đúng. Muốn chứng minh audience/issuer/signature/nonce/refresh, cần integration test với token server/decoder thật hoặc test validator cụ thể, trong đó có token lỗi và đường đi lỗi. Test session timeout/logout phải thực sự giữ/đổi cookie và repository giữa các request; `with(oidcLogin())` trên một request **không tự chứng minh** một lần login thật đã tạo phiên trong browser.

## 14. Những lỗi kiến trúc thường gặp

1. **API tin ID token vì “đều là JWT”:** signature hợp lệ vẫn không đủ; token có `aud` dành cho web client không được chấp nhận tại resource server.
2. **UI xem access token là bằng chứng duy nhất rằng người dùng đang đăng nhập:** access token được cấp để truy cập một resource cụ thể; có thể hết hạn trước session, hoặc đại diện application trong client credentials.
3. **Đưa refresh token vào header Bearer của API:** resource server không nên tiếp nhận refresh token làm credential; refresh token chỉ dành cho token endpoint.
4. **Cho JavaScript truy cập secret/token server-side không cần thiết:** dùng BFF hoặc cơ chế an toàn phù hợp client type; tránh xuất refresh token ra HTML, log hay lỗi exception.
5. **Đồng nhất `JSESSIONID` với JWT:** cookie session thường là ID opaque để lookup state local, không phải ID token hoặc access token.
6. **Lấy `exp` trong ID token để tự logout mọi session:** có thể không đúng policy; cần chủ động cấu hình re-authentication, idle/absolute session timeout, step-up khi nghiệp vụ cần.
7. **Quên issuer/audience/nonce:** token ký đúng nhưng dành cho client/tenant khác có thể bị chấp nhận nhầm nếu validator lỏng.
8. **Chỉ kiểm tra expiry access token mà bỏ quyền API:** scope/audience/token type/object ownership đều cần kiểm tra khi thích hợp.
9. **Lưu refresh token mà không tính rotation/concurrency:** hai outbound request đồng thời refresh cùng token cũ có thể gây `invalid_grant` và làm hỏng trạng thái nếu không đồng bộ.
10. **Nghĩ local logout tự thu hồi mọi token:** phải kết hợp revoke token, cleanup authorized client và logout OP theo thiết kế; JWT đã cấp có thể còn hiệu lực đến khi hết hạn.
11. **Nghĩ logout OP tự invalid session ứng dụng:** cần front-channel/back-channel logout hoặc cơ chế đồng bộ phiên và chính sách thu hồi.
12. **Không phân biệt resource server và OAuth2 client:** `oauth2Login()` phục vụ đăng nhập người dùng cho web app; `oauth2ResourceServer().jwt()` xác minh bearer token trên API; `OAuth2AuthorizedClientManager` phục vụ gọi API outbound và refresh khi đủ điều kiện.
13. **Dùng ID token để lấy dữ liệu có thể thay đổi liên tục:** ID token phản ánh claims tại thời điểm phát hành; profile/role mới cần quy trình cập nhật riêng. Không dùng token lâu đời như database thời gian thực.
14. **Mở endpoint debug in cả token:** chỉ trả metadata ít nhạy cảm cần thiết; không log `Authorization` header, access token, refresh token, ID token hay cookie session.

## 15. Cách chọn cơ chế cho hệ thống thật

- **Website server-rendered hoặc BFF:** dùng OIDC `oauth2Login()` cho web, cookie session `HttpOnly`/`Secure`/`SameSite` hợp lý; backend giữ authorized client và refresh token trong store phù hợp; chỉ gửi access token đến API có audience tương ứng.
- **Backend API nhận bearer token:** cấu hình Resource Server để kiểm tra issuer, signature hoặc introspection, thời gian, audience, scope/authority và các policy bổ sung; tránh dựa vào session của browser.
- **Service-to-service:** dùng `client_credentials` với scope/audience được cấp; không dựng giả user session.
- **SPA/native app:** dùng Authorization Code + PKCE theo client type; quản lý token dựa trên hướng dẫn bảo mật hiện hành và đặc thù platform, tránh giả định có nơi lưu secret an toàn như backend.
- **Ứng dụng yêu cầu đăng nhập lại theo độ nhạy:** dùng `max_age`/`auth_time`/`acr` hoặc cơ chế step-up thích hợp, cùng chính sách session absolute timeout; không xem refresh token còn sống là bằng chứng MFA mới.
- **Thu hồi nhanh:** chọn token TTL, introspection/revocation, back-channel logout, session index/version, event-driven invalidation phù hợp; yêu cầu mức bảo đảm cụ thể (“request kế tiếp”, “trong N giây”, hay “ngay lập tức”) để test được.

### Checklist tự kiểm tra trước khi đưa vào production

- [ ] Đã xác định **đúng audience và consumer** của ID token, access token, refresh token và cookie session.
- [ ] OIDC client kiểm tra ID token theo chuẩn và gắn `state`/`nonce` với login flow khi sử dụng.
- [ ] Resource server có chính sách validate token type, issuer, audience, time, scope và object authorization phù hợp.
- [ ] Refresh token chỉ lưu/được gửi tới thành phần cần thiết; rotation, revocation, concurrency và failure đều được kiểm thử.
- [ ] Browser session có bảo vệ cookie, CSRF, session fixation, idle/absolute timeout và logout local.
- [ ] Đã phân biệt “token hết hạn”, “session hết hạn”, “user logout OP”, “revoke refresh” và “revoke access”.
- [ ] Đã kiểm thử 401/403, thời điểm hết hạn chéo, API stateless không cookie, web session không bearer token.
- [ ] Có kế hoạch cleanup `OAuth2AuthorizedClient` khi logout/revoke theo repository đang dùng.

**Ghi nhớ:** ID token xác nhận đăng nhập **cho client**; access token cấp truy cập **API**; refresh token giúp client xin **token mới**; local session giúp **ứng dụng web** nhớ người dùng qua các request. Mỗi lớp cần đúng đối tượng tiêu thụ, thời hạn, quyền hạn và chính sách thu hồi của riêng nó.

## 16. Tài liệu chuẩn để tra cứu

- OpenID Connect Core 1.0 — ID token và validation: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://datatracker.ietf.org/doc/html/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://datatracker.ietf.org/doc/html/rfc6750
- OAuth 2.0 Token Revocation (RFC 7009): https://datatracker.ietf.org/doc/html/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://datatracker.ietf.org/doc/html/rfc9700
- Spring Security — OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth 2.0 Client / Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Testing OAuth 2.0 with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
