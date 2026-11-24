# Server-side session store

Một ứng dụng SaaS dùng OAuth 2.0/OpenID Connect (OIDC) cho người dùng đăng nhập. Sau khi đăng nhập, trình duyệt cần gọi các endpoint như `/orders` và `/profile`. Có hai cách thiết kế thường gặp:

- Đưa access token và refresh token vào JavaScript/browser storage rồi để trình duyệt gửi access token tới API.
- Dùng **server-side session store**: trình duyệt chỉ giữ **session cookie** chứa định danh phiên khó đoán; backend giữ trạng thái đăng nhập và, nếu kiến trúc cần, lưu access/refresh token trong kho phía server.

Trong cách thứ hai, khi người dùng mở đơn hàng, trình duyệt gửi cookie; backend tra phiên, kiểm quyền, rồi gọi Resource Server bằng access token được cất phía server. Điều này **giảm khả năng JavaScript hoặc mã bên thứ ba đọc trực tiếp OAuth token**, nhưng không biến cookie phiên thành vô hại. **Session ID cũng là bí mật kiểu bearer**: kẻ đánh cắp cookie hợp lệ vẫn có thể thử sử dụng phiên cho đến khi bị hết hạn hoặc thu hồi.

Bài thuộc chương **Token storage** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Chúng ta sẽ phân biệt JWT và opaque token, access token, refresh token và session ID; thiết kế nơi lưu, cách phát hành/kiểm `iss`, `aud`, `scope`, xử lý OAuth 2.0/OIDC, bảo vệ cookie, vòng đời phiên, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **server-side session store** là gì và phân biệt phiên ứng dụng với OAuth access token, refresh token, ID token và phiên tại Identity Provider.
2. Mô tả kiến trúc Backend-for-Frontend (BFF), nơi browser giữ session cookie còn backend nắm OAuth credentials.
3. Thiết kế session ID không đoán được, cookie an toàn, dữ liệu phiên tối thiểu và thời hạn idle/absolute.
4. So sánh Redis, JDBC/database và in-memory session store về phân tán, consistency, độ sẵn sàng và thu hồi.
5. Xử lý session fixation, CSRF, XSS, session hijacking, logout và session rotation.
6. Thiết kế lưu trữ/refresh token phía server an toàn, đặc biệt khi nhiều request đồng thời và refresh token rotation.
7. Áp dụng Spring Security và Spring Session theo nguyên tắc bảo mật, kiểm thử các trường hợp âm tính và vận hành an toàn.

## 2. Session store phía server là gì?

**Server-side session store** là kho trạng thái mà backend quản lý, được tra cứu bằng một **session identifier** (session ID) do backend tạo và gửi cho client bằng cơ chế phù hợp, thường là cookie. Kho này có thể lưu liên kết tới người dùng, trạng thái xác thực, thời điểm hoạt động, CSRF context và thông tin khác mà backend cần.

Ví dụ khái niệm:

~~~text
Browser
  Cookie: __Host-session=RANDOM_SESSION_ID

Backend session store
  key: HMAC(sessionLookupKey, RANDOM_SESSION_ID)
  value:
    principal_id: user-742
    authentication_state: authenticated
    issued_at: ...
    last_seen_at: ...
    idle_expires_at: ...
    absolute_expires_at: ...
    revoked_at: null
    authorized_client_ref: grant-81f

Token/authorized-client store (server-side, protected)
  grant-81f:
    oauth_client_id: shop-bff
    issuer: https://login.example.com
    access_token: protected secret
    refresh_token: protected secret
    granted_scopes: [orders:read]
    audience: orders-api
    token_expires_at: ...
~~~

Đây là **mô hình dữ liệu minh họa**, không phải schema mặc định của Spring Session hay định dạng bắt buộc của OAuth. Có thể gộp hoặc tách session store và token store, nhưng phân quyền truy cập, thời hạn và khả năng thu hồi của hai loại dữ liệu phải rõ ràng.

### 2.1. Phân biệt năm loại trạng thái/dữ liệu

| Đối tượng | Ai sử dụng? | Dùng để làm gì? | Điều không nên nhầm |
|---|---|---|---|
| **Session ID của ứng dụng** | Browser gửi cho backend/BFF qua cookie | Tìm phiên ứng dụng phía server | **Không** phải OAuth access token có `aud`/`scope` cho API. |
| **Server-side session record** | Backend/ứng dụng | Duy trì trạng thái xác thực và các ràng buộc phiên | Không tự là phiên tại Identity Provider. |
| **OAuth access token** | Client được cấp token gửi tới Resource Server | Cấp quyền truy cập API trong audience/scope phù hợp | Không dùng thay session ID của browser trong kiến trúc BFF. |
| **OAuth refresh token** | OAuth client gửi cho Authorization Server | Xin access token mới theo grant/policy | Không gửi đến Resource Server hoặc để browser đọc trực tiếp nếu BFF giữ token. |
| **OIDC ID token / OP session** | ID token dành cho OIDC Client; OP session thuộc Identity Provider | Xác thực người dùng và duy trì phiên đăng nhập tại OP | Đăng xuất BFF không tự đảm bảo OP session hoặc mọi token đều bị thu hồi. |

**Một access token opaque không đồng nghĩa với session ID.** Cả hai có thể là chuỗi ngẫu nhiên, nhưng nơi xác minh và ý nghĩa khác nhau: access token do Authorization Server cấp cho Resource Server; session ID do ứng dụng quản lý để tìm session state.

### 2.2. Stateful session không có nghĩa OAuth token phải là opaque

BFF có thể lưu **JWT access token** đã ký hoặc **opaque access token** do AS cấp. Session cookie vẫn có thể chỉ là chuỗi ngẫu nhiên. Resource Server xác minh JWT bằng chữ ký/claims hoặc opaque bằng introspection; kiểu dữ liệu trong session store **không quyết định** định dạng access token.

Một ứng dụng cũng có thể dùng session store mà **không lưu OAuth token** nếu tất cả chức năng được thực hiện trực tiếp bởi backend dựa trên trạng thái riêng. Ngược lại, hệ thống dùng OAuth mà không có browser session cũng có thể phù hợp cho service-to-service.

## 3. Kiến trúc BFF: browser chỉ giữ session cookie

Một mô hình phổ biến là **Backend-for-Frontend (BFF)**. BFF là OAuth Client (thường confidential client), xử lý Authorization Code + PKCE, xác minh ID token theo OIDC nếu áp dụng, lưu OAuth token ở backend và tạo phiên ứng dụng cho browser.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant F as BFF / Web Backend
    participant AS as Authorization Server / OP
    participant S as Session and Token Store
    participant API as Orders Resource Server

    U->>B: Chọn Đăng nhập
    B->>F: GET /login
    F->>S: Tạo state, PKCE và nonce theo luồng
    F-->>B: Redirect tới AS
    B->>AS: Authorization request
    AS->>AS: Xác thực, kiểm client/grant/consent
    AS-->>B: Redirect với authorization code
    B->>F: Callback mang code và state
    F->>S: Kiểm state và lấy PKCE verifier
    F->>AS: Đổi code + PKCE + client auth nếu áp dụng
    AS-->>F: Access token, có thể refresh/ID token
    F->>F: Xác minh ID token OIDC nếu được cấp
    F->>S: Lưu authorized-client/token state; tạo session
    F-->>B: Set-Cookie session ID an toàn
    B->>F: GET /orders + Cookie session
    F->>S: Tra phiên và kiểm session policy
    S-->>F: Principal và token reference hợp lệ
    F->>API: Bearer access token dành cho orders-api
    API->>API: Kiểm issuer, audience, expiry, scope, resource policy
    API-->>F: Danh sách đơn được phép
    F-->>B: Response nghiệp vụ (không trả token)
~~~

**Luồng có hai điểm xác minh khác nhau:**

1. **BFF** xác minh **session cookie/session state** để xác định người đang sử dụng ứng dụng. Với OIDC, BFF đã kiểm ID token đúng `iss`/`aud`/`exp` và các điều kiện theo luồng trước khi tạo session.
2. **Resource Server** xác minh **OAuth access token** mà BFF gửi, kiểm `iss`, `aud`, `scope`, thời hạn và quyền trên dữ liệu.

BFF **không nên trả access token hoặc refresh token về JavaScript** chỉ vì nó có thể lấy token từ store. Nếu UI cần gọi API, thường cho UI gọi route BFF; BFF gọi API với token đúng audience.

### 3.1. Vì sao BFF giảm rủi ro token theft?

Token không nằm trong `localStorage`, `sessionStorage` hoặc một biến JavaScript trên browser. Cookie `HttpOnly` khiến JavaScript thông thường không thể đọc giá trị cookie trực tiếp. Nhờ đó, một đoạn script độc hại trên trang không dễ sao chép access/refresh token để sử dụng tại API bên ngoài.

Nhưng **XSS vẫn có thể gửi request đã xác thực** từ browser bằng cookie của người dùng; `HttpOnly` không phải giải pháp chống XSS toàn diện. Nếu session cookie bị lấy qua máy bị chiếm quyền, proxy sai cấu hình hoặc log, kẻ khác vẫn có thể thử sử dụng phiên. Backend cần CSRF defense, CSP, input/output encoding, session expiry/revocation và các kiểm soát còn lại.

### 3.2. Không tự đưa ID token vào Resource Server

OIDC ID token thường có `aud` là `client_id` của BFF, không phải `orders-api`. BFF dùng ID token để kiểm kết quả xác thực và xây ngữ cảnh phiên; khi gọi `orders-api`, BFF gửi **access token** dành cho Orders API.

**Chữ ký hợp lệ từ cùng issuer không biến ID token thành access token.** Cũng không được chuyển tiếp refresh token đến API nghiệp vụ.

## 4. Session ID là bearer secret

Một session ID nên là **chuỗi không đoán được**, sinh từ **CSPRNG** (bộ sinh số giả ngẫu nhiên an toàn mật mã). Không dùng user ID, timestamp, email, IP address, sequence number hay `java.util.Random` làm giá trị phiên.

Ví dụ thiết kế có biên an toàn rộng: sinh **32 byte ngẫu nhiên = 256 bit entropy** rồi mã hóa Base64URL không padding (thường 43 ký tự). Nhiều hệ thống dùng khoảng 128 bit entropy trở lên cho session ID tùy profile và threat model; điều quan trọng là nguồn ngẫu nhiên tốt, uniqueness và quản lý vòng đời đúng.

### 4.1. Ví dụ Java sinh identifier

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class SessionIdGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ID_BYTES = 32;

    private SessionIdGenerator() {}

    public static String nextId() {
        byte[] raw = new byte[ID_BYTES];
        RANDOM.nextBytes(raw);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);
    }
}
~~~

Đây **chỉ là ví dụ về CSPRNG/encoding**. Trong Spring ứng dụng thực tế, nên để **framework/session manager đáng tin** cấp, xoay vòng và quản lý session ID; không tự xây toàn bộ hệ thống session bằng đoạn code trên.

### 4.2. Opaque cookie không phải cookie được mã hóa

Một session cookie có thể chứa duy nhất session ID random. Nó **không cần mang toàn bộ principal/roles** vì server đã có session state. Nếu app đặt toàn bộ user profile, role hoặc token vào cookie rồi ký nó, đó là **client-side session/state token** với threat model khác; không phải mô hình server-side session store thuần túy.

**Cookie ký không có nghĩa cookie mã hóa**. Với cookie chứa dữ liệu nhạy cảm dù đã ký, browser/thiết bị vẫn có thể nhìn thấy payload nếu không mã hóa. Lựa chọn đơn giản hơn thường là **session ID random + state ở backend**.

### 4.3. Hash/HMAC làm lookup key

Có thể lưu khóa tra cứu từ **hash hoặc HMAC** của session ID, thay vì lưu raw cookie ID trong store, nếu giải pháp/session framework hỗ trợ kiến trúc đó:

~~~text
cookie sent by browser:
  sid = RANDOM_SECRET

backend:
  lookupKey = HMAC_SHA256(dedicatedSessionLookupKey, sid)
  record = sessionStore.get(lookupKey)
~~~

Nếu session ID sinh đủ entropy, digest phù hợp có thể giảm tác động của lộ index. HMAC cần khóa riêng, bảo vệ và rotation phù hợp. Không tự áp dụng HMAC vào một framework đã có cơ chế quản lý session mà không hiểu cách tương tác với storage, TTL, logout và distributed nodes.

**Hash/HMAC session ID không sửa được lỗi sinh ID dễ đoán**. Nếu session ID chứa user ID hoặc timestamp, attacker có thể thử đoán dù store lưu digest.

## 5. Lưu gì trong server-side session store?

Một session record nên lưu **ít nhất những gì cần để kiểm trạng thái phiên và liên kết tới authorization context**.

| Thuộc tính | Ví dụ | Ghi chú bảo mật |
|---|---|---|
| `session_lookup_key` | Digest/HMAC hoặc key do framework quản lý | Định danh tra cứu, không ghi raw cookie secret vào log. |
| `principal_id` | `user-742` | Từ kết quả xác thực đã kiểm, không lấy từ request body. |
| `created_at` | Thời điểm bắt đầu phiên | Dùng để tính absolute lifetime. |
| `last_activity_at` | Mốc hoạt động tin cậy gần nhất | Không cập nhật tùy ý từ request lỗi/không xác thực nếu policy không cho. |
| `idle_expires_at` | Hết hạn do không hoạt động | Ngăn phiên tồn tại vô hạn khi bỏ quên. |
| `absolute_expires_at` | Hết hạn tối đa từ lúc tạo | Không kéo dài mãi chỉ bằng hoạt động liên tục. |
| `revoked_at`/`status` | `active` hoặc `revoked` | Hỗ trợ logout và quản trị phiên. |
| `authentication_context` | Mốc đăng nhập/assurance đã kiểm | Dùng cho reauthentication/step-up nếu cần. |
| `active_tenant_id` | `tenant-beta`, nếu có | Phải được kiểm membership/policy; không tự cấp quyền mọi tenant. |
| `csrf_context` | Token/seed tùy cơ chế | Dùng với CSRF strategy server-side khi cần. |
| `authorized_client_ref` | `grant-81f` | Tham chiếu tới OAuth token/authorized-client store được bảo vệ. |

**Không lưu tùy tiện** nguyên đối tượng user lớn, mật khẩu, private key, raw request, access/refresh token đã giải mã thành loggable DTO hoặc dữ liệu nghiệp vụ không cần thiết. Dữ liệu phiên nên có schema rõ ràng, khả năng nâng cấp phiên bản và thời hạn.

### 5.1. Có nên lưu access/refresh token trong session record?

BFF cần giữ token ở server để gọi API. Có hai cách:

- **Lưu token trong session state** được bảo vệ, nếu thư viện hỗ trợ và yêu cầu quy mô nhỏ/đơn giản; phải đánh giá serialization, quyền đọc store, TTL và cách rotate token.
- **Tách OAuth authorized-client/token store**, giữ trong session một tham chiếu có kiểm soát. Dễ phân quyền độc lập, encryption/rotation/retention của refresh token, và xử lý concurrency riêng.

Cả hai đều có thể dùng nếu bảo vệ đủ. **Server-side không tự đồng nghĩa an toàn**: nếu Redis/database bị lộ, token dạng rõ vẫn có thể bị dùng. Với refresh token, cân nhắc mã hóa ở tầng ứng dụng hoặc cơ chế secret store, TLS và giới hạn quyền. Quản lý key riêng, hạn chế dump/snapshot và không in token ra log.

### 5.2. Session store và OAuth token store khác nhau ở vòng đời

- Session cookie có thể hết hạn do idle timeout hoặc người dùng đăng xuất.
- Access token có `exp` riêng, thường ngắn hơn phiên.
- Refresh token theo grant/AS, có thể bị rotate/revoke độc lập.
- Đăng xuất phiên BFF **không tự chứng minh** OP session đã kết thúc hoặc access token cũ được mọi RS vô hiệu hóa.
- Nếu mất session store, việc khôi phục token store không tự tạo lại một phiên được tin; phải có cơ chế phục hồi xác thực đúng chính sách.

Tránh dùng một trường `expiresAt` duy nhất để diễn giải đồng thời ba thời hạn khác nhau.

## 6. Cookie an toàn cho session ID

Khi dùng HTTPS và cùng host phục vụ BFF, một lựa chọn cookie nghiêm ngặt:

~~~http
Set-Cookie: __Host-session=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Đây là giá trị minh họa, không phải credential thật. `__Host-` là prefix cookie có ràng buộc bổ sung ở các browser hỗ trợ: phải có `Secure`, `Path=/` và **không được có `Domain`**. Điều này giúp giới hạn khả năng một subdomain ghi đè cookie cho host khác.

| Thuộc tính | Tác dụng | Điều cần hiểu |
|---|---|---|
| `Secure` | Browser chỉ gửi cookie trên kết nối HTTPS phù hợp quy tắc. | Vẫn cần TLS đúng tại proxy/BFF; Secure không thay TLS. |
| `HttpOnly` | JavaScript không thể đọc cookie trực tiếp qua `document.cookie`. | XSS vẫn có thể gửi request bằng session hiện tại. |
| `SameSite=Lax` | Hạn chế gửi cookie trong nhiều tình huống cross-site. | Không thay CSRF token/Origin checks; lựa chọn phụ thuộc luồng điều hướng. |
| `SameSite=Strict` | Hạn chế cross-site mạnh hơn. | Có thể ảnh hưởng đăng nhập/redirect từ IdP hoặc liên kết ngoài. |
| `SameSite=None; Secure` | Cho phép các kịch bản cross-site khi browser/chính sách chấp nhận. | Tăng yêu cầu phòng CSRF và phụ thuộc chính sách third-party cookies. |
| `Path=/` | Cookie dùng trong phạm vi path này. | Là ràng buộc gửi cookie, không phải phân quyền server. |
| **Không có `Domain`** | Giữ cookie host-only. | Giảm bề mặt truy cập/ghi cookie từ subdomain. |
| `Max-Age`/`Expires` | Điều khiển thời hạn lưu ở browser. | **Không thay** expiration phía server. |

Nếu dùng cookie tên khác như `SESSION` của một cấu hình Spring Session, prefix `__Host-` chỉ có hiệu lực nếu **thực sự đặt tên cookie có prefix và thỏa đầy đủ ràng buộc**. Đặt text `__Host-session` trong tài liệu không tự thay đổi cấu hình framework.

### 6.1. Cookie phiên và persistent session

Một session cookie không có `Max-Age`/`Expires` thường được coi là phiên của trình duyệt, nhưng hành vi khôi phục phiên/restore tabs phụ thuộc browser. Server **phải có idle và absolute expiry** bất kể browser giữ cookie bao lâu.

Chức năng **Remember me** nên được thiết kế riêng, có hạn sử dụng, rotation/revocation và xác thực lại phù hợp; không kéo dài session ID vô hạn chỉ vì người dùng chọn “giữ đăng nhập”.

### 6.2. Reverse proxy và TLS termination

Nếu HTTPS kết thúc tại proxy/gateway, backend phải cấu hình đúng thông tin request an toàn để phát cookie `Secure` và tạo redirect URL chính xác. Chỉ tin forwarded headers từ **proxy đã xác thực/được cấu hình**, không tin mọi `X-Forwarded-Proto` do Internet tự gửi.

**HSTS, TLS end-to-end phù hợp và bảo vệ proxy–app** là các phần của cùng threat model. Cookie `Secure` không bù được khi ứng dụng để lộ session ID trong log hoặc HTTP nội bộ không được bảo vệ.

## 7. Session fixation và session rotation

**Session fixation** xảy ra khi attacker khiến nạn nhân sử dụng một session ID mà attacker đã biết, rồi chờ nạn nhân đăng nhập để chiếm phiên sau khi nó được nâng cấp thành authenticated.

**Quy tắc:** khi chuyển từ anonymous/pre-auth session sang authenticated session, phải **đổi session ID** hoặc tạo phiên mới và bảo đảm ID cũ không còn đại diện cho quyền đăng nhập.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Web Backend
    participant S as Session Store
    B->>A: Có session ID cũ /anonymous
    A->>A: Hoàn tất OAuth login và xác minh ID token
    A->>S: Rotate/migrate session state an toàn
    S-->>A: Session ID mới, ID cũ không còn quyền
    A-->>B: Set-Cookie session ID mới
    B->>A: Request tiếp theo với cookie mới
    A->>S: Kiểm session ID mới, expiry và trạng thái
    S-->>A: Authenticated principal
~~~

### 7.1. Khi nào nên đổi ID?

- **Sau login thành công** hoặc nâng session từ anonymous sang authenticated.
- **Sau nâng quyền** hoặc reauthentication nhạy cảm, theo policy.
- Khi phát hiện rủi ro session fixation hoặc compromise, có thể invalidate phiên cũ, yêu cầu xác thực lại.
- Định kỳ rotate phiên nếu ứng dụng yêu cầu, nhưng phải xử lý concurrent requests và session mapping đúng.

**Không nhất thiết rotate session ID mỗi request**; điều này có thể gây race, mất trạng thái, spam cookie và làm hệ thống phân tán khó vận hành. Phải đảm bảo ID cũ không tiếp tục có quyền theo yêu cầu security policy.

### 7.2. Không chỉ thay cookie trên browser

Nếu logout hoặc rotate mà **bản ghi phiên cũ vẫn active trên server**, attacker có cookie cũ vẫn có thể dùng. Cần invalidate/delete/mark revoked phía store và bảo đảm các node không nhận trạng thái cũ.

Nếu dùng middleware/session framework, dùng cơ chế **session fixation protection** được hỗ trợ thay vì tự viết thuật toán rotate cookie không đồng bộ với store.

## 8. Thời hạn idle, absolute và kiểm tra mỗi request

Server-side session nên có nhiều giới hạn:

| Giới hạn | Ví dụ | Mục đích |
|---|---|---|
| **Idle timeout** | 20–30 phút không hoạt động | Giảm cửa sổ phiên bỏ quên; con số là ví dụ tùy rủi ro. |
| **Absolute timeout** | 8–12 giờ từ login | Không cho phiên sống vô hạn vì hoạt động liên tục. |
| **Reauthentication freshness** | Yêu cầu đăng nhập/MFA lại khi thao tác tài chính | Không nhầm session còn hiệu lực với mức assurance còn đủ. |
| **Access token TTL** | 5–15 phút | Giới hạn thời gian dùng bearer token ở Resource Server. |
| **Refresh token lifetime** | Theo AS/grant/rotation policy | Giới hạn khả năng xin access token mới. |
| **Revocation** | Logout, khóa user, bị gỡ tenant | Vô hiệu hóa phiên trước khi hết hạn thường lệ. |

Các số chỉ là ví dụ thiết kế, không phải chuẩn bắt buộc cho mọi hệ thống.

### 8.1. Quy trình kiểm tra khi nhận cookie

~~~text
function authenticateSession(sessionCookie):
    if sessionCookie missing or malformed:
        reject

    record = sessionStore.lookupTrusted(sessionCookie)
    if record missing:
        reject

    now = trustedServerClock()

    if record.status != ACTIVE:
        reject
    if now >= record.idleExpiresAt:
        invalidate(record)
        reject
    if now >= record.absoluteExpiresAt:
        invalidate(record)
        reject
    if accountOrTenantPolicyRequiresReauth(record):
        reject or requireStepUp

    updateLastActivityWithSafeConcurrency(record, now)
    return trustedPrincipalAndSessionContext(record)
~~~

Kiểm tra **cả idle và absolute** ở backend, ngay cả khi Redis/JDBC có TTL. Redis TTL giúp dọn key nhưng không tự biểu diễn mọi quy tắc authorization, session status và absolute lifetime. Nếu thiếu dữ liệu hoặc store không sẵn sàng, **fail closed**, không coi cookie tự thân là đủ quyền.

### 8.2. Khi session hết hạn giữa request dài

Với upload, report hoặc giao dịch dài, cần xác định chính sách: kiểm phiên lúc bắt đầu đã đủ hay phải kiểm thêm trước commit/gửi kết quả? Với thao tác giá trị cao, cân nhắc **recheck authorization tại thời điểm thực thi**, transaction boundary và hạn chế race giữa quyền bị thu hồi với request đang chạy.

### 8.3. Logout và session invalidation

Đăng xuất cần:

1. Invalidate/delete/mark revoked bản ghi phiên trên server.
2. Trả cookie bị xóa hoặc hết hạn, **đúng tên/path/domain/attributes** để browser không gửi lại.
3. Xóa/liên kết lại authorized-client/token state theo chính sách; cân nhắc revoke refresh token và access token nếu AS hỗ trợ.
4. Không giả định logout khỏi BFF tự làm OP session hoặc mọi JWT access token không còn hiệu lực.

**Chỉ xóa cookie tại browser là chưa đủ** nếu session ID phía server còn active và đã bị attacker sao chép.

## 9. Chọn nơi lưu session: Redis, JDBC hay bộ nhớ

| Kho | Ưu điểm | Rủi ro/vấn đề |
|---|---|---|
| **In-memory từng instance** | Đơn giản, nhanh, ít phụ thuộc ngoài | Mất phiên khi restart; nhiều node phải dùng sticky session hoặc chia sẻ store; khó invalidate toàn cụm. |
| **Redis / distributed key-value** | Tra cứu nhanh, TTL, chia sẻ giữa các node, phù hợp nhiều ứng dụng web | Cần TLS, ACL, eviction policy, failover/replication, protection của snapshot và cache consistency. |
| **JDBC/relational database** | Transaction/durability, vận hành cùng DB quen thuộc | Chi phí I/O, cleanup expired records, index/locking, quy mô cao cần tối ưu. |
| **Dedicated session service** | Tách chính sách, có audit/thu hồi trung tâm | Tăng phụ thuộc mạng, latency, tính sẵn sàng và quyền API. |

### 9.1. Redis không mặc định là kho secret an toàn

Nếu Redis giữ session hoặc OAuth credentials:

- Không public Redis endpoint; đặt trong mạng hạn chế và yêu cầu **TLS/authentication/ACL** phù hợp.
- Tách credentials/roles của ứng dụng, giới hạn key patterns/commands khi có thể.
- Không log raw session ID/refresh token trong key names hoặc value dump.
- Đánh giá RDB/AOF snapshot, backup, replication và quyền admin vì chúng có thể chứa dữ liệu nhạy cảm.
- Không dùng eviction policy khiến key active bị xóa tùy ý mà ứng dụng lại **fail open**.
- Thiết lập session expiry ở store và kiểm absolute expiry tại app.
- Giám sát saturation, latency, key eviction, failover và session creation rate.

Nếu store tạm lỗi, ứng dụng có thể phải trả lỗi/đề nghị đăng nhập lại theo chính sách; **không nhận cookie chưa tra được** vì mục tiêu availability.

### 9.2. JDBC cần schema, TTL và cleanup rõ

Với database-backed session, cần index tra ID và expiration, transaction phù hợp, job xóa phiên hết hạn và công cụ invalidate theo user/device. Dùng connection/service account với **least privilege**; tránh cho một API đọc token/phiên của mọi ứng dụng nếu không cần.

### 9.3. Java serialization và phiên bản dữ liệu

Session thường chứa đối tượng Java. **Không deserialise dữ liệu tùy ý từ nguồn không tin**, đặc biệt với Java native object serialization không được giới hạn. Ưu tiên định dạng schema rõ, danh sách kiểu được phép, giới hạn kích thước và versioning.

Khi rolling deployment, node cũ và mới có thể đọc phiên do phiên bản khác ghi. Cần migration schema/backward compatibility hoặc kế hoạch invalidate có kiểm soát; **không vô tình biến lỗi deserialize thành phiên authenticated mặc định**.

## 10. Lưu OAuth token và xử lý refresh đồng thời

Trong BFF, browser chỉ gửi session cookie. Backend dùng session để tìm **OAuth authorized-client/token state**, lấy access token dành cho API, và nếu cần thì dùng refresh token trao đổi với Authorization Server.

~~~text
Browser --session cookie--> BFF
BFF --session lookup--> Session Store
BFF --grant reference--> Authorized Client / Token Store
BFF --access token (aud=orders-api)--> Orders Resource Server
BFF --refresh token--> Authorization Server token endpoint
~~~

Access token phải có issuer, audience, scope và thời hạn phù hợp; **không đưa refresh token vào cookie hoặc JSON response cho browser**. Phải phân biệt vòng đời session, access token và refresh token: một token hết hạn không tự đồng nghĩa browser session đã hết hạn, và browser session hết hạn không làm mọi access token còn sống bị thu hồi.

### 10.1. Đồng thời refresh với refresh token rotation

Hai request đến cùng lúc có thể nhận thấy access token hết hạn trên hai BFF instance. Nếu cả hai cùng dùng một refresh token `R1`:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as BFF instance A
    participant B as BFF instance B
    participant S as Token Store
    participant AS as Authorization Server
    A->>S: Đọc refresh token R1
    B->>S: Đọc refresh token R1
    A->>AS: Refresh R1
    AS-->>A: Access A2 và Refresh R2
    B->>AS: Refresh R1
    AS-->>B: invalid_grant hoặc reuse detected
    A->>S: Ghi R2
    B->>S: Có nguy cơ xử lý sai token family
~~~

Với nhiều triển khai refresh token rotation, `R1` bị vô hiệu sau khi được AS sử dụng thành công. Lần dùng thứ hai có thể bị xem là token reuse, dẫn tới `invalid_grant` hoặc chính sách thu hồi cả token family.

**Chiến lược phù hợp:**

1. Chỉ một request/worker thực hiện refresh cho cùng grant tại một thời điểm (**single-flight hoặc lock phân tán**).
2. Sau khi có lock, **đọc lại** token store; nếu request khác đã refresh, sử dụng bản mới.
3. Ghi access/refresh token mới bằng **compare-and-set/version** hoặc cơ chế atomic tương đương; không để kết quả cũ ghi đè mới.
4. Lock phải có timeout, xử lý crash, stale owner và chiến lược fail closed.
5. Không retry vô hạn bằng refresh token cũ khi AS trả `invalid_grant`; xử lý theo token family/revoke/relogin policy.
6. Nếu AS đã phát refresh token mới nhưng process crash trước khi lưu, có thể không khôi phục được grant; cần kế hoạch buộc xác thực lại khi cần.

Pseudocode minh họa:

~~~text
function getAccessTokenForSession(session):
    ref = session.authorizedClientRef
    record = tokenStore.read(ref)

    if record.accessToken has sufficient remaining lifetime:
        return record.accessToken

    with singleFlightLock(ref):
        latest = tokenStore.read(ref)

        if latest.accessToken has sufficient remaining lifetime:
            return latest.accessToken

        result = authorizationServer.refresh(
            client = configuredClient,
            refreshToken = latest.refreshToken
        )

        if result.invalid:
            invalidateGrantAndAffectedSessions(ref)
            requireLogin()

        tokenStore.compareAndReplace(
            ref,
            expectedVersion = latest.version,
            accessToken = result.accessToken,
            refreshToken = result.rotatedRefreshTokenIfProvided,
            newVersion = latest.version + 1
        )

        return result.accessToken
~~~

Đây là **mô hình**, không phải triển khai distributed lock hoàn chỉnh. Cách AS xử lý concurrency, rotation, reuse và token family tùy provider/profile. Nếu framework đã có authorized-client manager phù hợp, nên dùng/kiểm kỹ nó thay vì tự viết vòng refresh.

### 10.2. Thời hạn độc lập

~~~text
session.idle_expires_at       != access_token.exp
session.absolute_expires_at   != refresh_token.expires_at
OP_session_expiry             != BFF_session_expiry
~~~

Không dùng một trường `expiresAt` duy nhất để đại diện cho tất cả. Khi access token hết hạn, BFF **có thể** refresh nếu session vẫn hợp lệ và grant cho phép. Khi session hết hạn, BFF phải từ chối cookie dù access token server-side còn hạn.

## 11. CSRF, XSS và session cookie

### 11.1. Cookie tự động được gửi tạo nguy cơ CSRF

Browser gửi session cookie theo luật cookie; người dùng không cần tự thêm Authorization header. Nếu không có bảo vệ **Cross-Site Request Forgery (CSRF)**, trang độc hại có thể thử khiến browser đã đăng nhập gửi request thay đổi trạng thái tới BFF.

Với ứng dụng xác thực bằng cookie, nên áp dụng:

- **CSRF token** do framework tạo và xác minh cho các request thay đổi trạng thái, theo thiết kế synchronizer token hoặc cơ chế tương đương.
- Kiểm **Origin/Referer** hoặc Fetch Metadata khi phù hợp, làm lớp phòng vệ bổ sung.
- Cookie `SameSite=Lax`/`Strict` tùy luồng đăng nhập; `SameSite` là **defense in depth**, không thay CSRF strategy.
- Không để GET gây thay đổi dữ liệu; bảo vệ endpoint POST/PUT/PATCH/DELETE phù hợp.
- Cấu hình CORS chính xác nếu frontend khác origin; **CORS không phải giải pháp CSRF toàn diện**.

**`HttpOnly` không chặn CSRF.** Nó hạn chế JavaScript đọc cookie, nhưng browser vẫn gửi cookie theo chính sách.

### 11.2. BFF không loại bỏ XSS

BFF giữ access/refresh token ở server giúp JavaScript thông thường **khó sao chép OAuth token**, nhưng XSS vẫn có thể thực hiện hành động thay người dùng qua BFF trong browser của họ. Vì vậy vẫn phải dùng output encoding, CSP, kiểm dữ liệu đầu vào, hạn chế script bên thứ ba và authorization từng endpoint.

Đối với thao tác nhạy cảm, có thể yêu cầu **reauthentication/step-up**, xác nhận giao dịch và kiểm authorization lại trước commit. `HttpOnly` không biến một trình duyệt đã bị XSS thành môi trường tin cậy.

### 11.3. Login CSRF và authorization flow

Trong Authorization Code + PKCE/OIDC:

- `state` ràng buộc/củng cố luồng authorization và bảo vệ trước các biến thể CSRF/mix-up theo profile.
- `code_challenge`/`code_verifier` ràng buộc việc đổi authorization code.
- `nonce` trong các luồng OIDC cần thiết giúp kiểm ID token gắn với yêu cầu xác thực.
- CSRF token của ứng dụng bảo vệ các **thao tác thay đổi trạng thái sau login**.

Không dùng một giá trị tùy ý để thay cả bốn vai trò. Nếu session trước login giữ `state`/PKCE verifier, cần chống session fixation và bảo vệ callback correlation.

### 11.4. Trường hợp frontend khác origin

Cookie có thể phải dùng `SameSite=None; Secure` trong ngữ cảnh cross-site được browser chấp nhận, nhưng phải tính thêm chính sách third-party cookies, CSRF, CORS credentials và Origin allowlist. Không bật CORS wildcard cho request có credentials. Nếu có thể, bố trí frontend và BFF dưới cùng site/origin để đơn giản hóa threat model.

## 12. Session store phân tán và khả năng thu hồi

Ứng dụng production thường có nhiều BFF instance. Nếu phiên chỉ nằm trong bộ nhớ của một node, request tới node khác sẽ không tìm thấy phiên. Hai lựa chọn:

1. **Sticky sessions:** load balancer ưu tiên cùng instance; đơn giản nhưng giảm khả năng failover và khó invalidate toàn cụm.
2. **Distributed store:** Redis, JDBC hoặc session service; các instance cùng đọc trạng thái nhưng phải xử lý consistency, độ trễ, TTL và failover.

### 12.1. Những điều kiện bất biến

- Logout tại instance A → instance B **không được nhận cookie cũ** sau khi trạng thái revoke có hiệu lực theo cam kết.
- Session ID được rotate khi login → ID cũ không được truy cập đặc quyền authenticated.
- Khi user bị khóa hoặc bị gỡ khỏi tenant, policy phải có cơ chế kiểm lại/invalidate để không dùng quyền lỗi thời quá giới hạn.
- Refresh token mới không bị node khác ghi đè bằng refresh token cũ.
- Session store bị lỗi hoặc record không đọc/validate được → **fail closed**, không coi cookie có định dạng hợp lệ là một phiên authenticated.

Cache local trước distributed store có thể khiến revocation bị chậm. Không quảng cáo “logout tức thì trên mọi node” nếu cấu hình cache làm token/phiên đã revoke vẫn được nhận trong một khoảng thời gian.

### 12.2. Metrics và telemetry an toàn

Ví dụ chỉ số vận hành:

~~~text
session_lookup_success_rate
session_store_latency_ms
session_store_unavailable_count
session_expired_idle_count
session_expired_absolute_count
session_invalidated_on_logout_count
session_rotation_failures_count
refresh_rotation_failures_count
csrf_rejected_requests_count
~~~

**Không dùng raw session ID, bearer token, refresh token hoặc email làm metric label**. Những giá trị đó vừa có thể làm lộ credential, vừa tăng cardinality. Logs/traces nên giữ mã lỗi, route template, service, request/trace ID đã được kiểm, không ghi `Cookie`/`Authorization`.

### 12.3. Redis outage không phải lý do fail open

Nếu Redis/JDBC không sẵn sàng, ứng dụng có thể trả lỗi dịch vụ tạm thời hoặc yêu cầu reauthentication theo chính sách. Tuy nhiên, **không cấp quyền dựa trên cookie khi chưa đọc được session record**. Nếu có cơ chế cache dự phòng, cần đánh giá TTL, invalidation và ranh giới thu hồi riêng.

## 13. Spring Security và Spring Session: ví dụ triển khai

Đối với web application Java/Spring, nên tận dụng các thành phần đã được kiểm chứng thay vì tự viết session protocol. **Spring Security** xử lý authentication, session fixation và CSRF; **Spring Session** có thể thay session storage mặc định bằng Redis/JDBC để chia sẻ giữa các instance.

Các ví dụ dưới đây mang tính **minh họa kiến trúc**. Cần kiểm tra API, dependency và hành vi mặc định theo phiên bản Spring Boot/Spring Security/Spring Session của dự án thực tế.

### 13.1. SecurityFilterChain cho BFF dùng OAuth2 Login

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .clearAuthentication(true)
                .invalidateHttpSession(true)
                .deleteCookies("__Host-session")
            );

        return http.build();
    }
}
~~~

- `oauth2Login` kích hoạt luồng OAuth2/OIDC login khi đã cấu hình client registration, endpoints và redirect URI phù hợp.
- `changeSessionId` là chiến lược bảo vệ **session fixation** khi authentication thành công; policy thực tế còn cần xử lý privilege escalation và session invalidation.
- `csrf(Customizer.withDefaults())` giữ CSRF protection cho web session. Với SPA, cách lấy/gửi CSRF token có thể đòi cấu hình `CsrfTokenRepository`/handler cụ thể.
- `invalidateHttpSession(true)` hủy phiên HTTP phía server; `deleteCookies("__Host-session")` chỉ đúng nếu ứng dụng thực sự dùng cookie tên đó.
- **Logout phía Spring không tự revoke refresh token, access JWT hoặc OP session**. Cần flow revoke/cleanup được thiết kế riêng nếu yêu cầu.

Đừng tắt CSRF chỉ vì endpoint nhận JSON. Một BFF được xác thực bằng cookie có threat model khác API stateless chỉ dùng bearer Authorization header.

### 13.2. Spring Session Redis và cookie host-only

Ví dụ khi đã cài dependency Spring Session Redis và kết nối Redis an toàn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class RedisSessionConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer =
            new DefaultCookieSerializer();

        serializer.setCookieName("__Host-session");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");

        // Không đặt Domain: cần cookie host-only.
        return serializer;
    }
}
~~~

Ví dụ đặt **idle timeout 30 phút** và cookie `Secure`/`HttpOnly`/`SameSite=Lax`/`Path=/`. Cần kiểm `Set-Cookie` thật ở browser, đường đi qua HTTPS proxy, cookie name lúc logout và compatibility theo môi trường.

**Các giới hạn của ví dụ:**

1. Mã trên **không** tự cấu hình Redis TLS/ACL, encryption của token store hay kiểm absolute session timeout.
2. `maxInactiveIntervalInSeconds` phản ánh thời gian **không hoạt động**, không thay policy hết hạn tuyệt đối.
3. Spring Boot có thể auto-configure Spring Session nếu có dependency; tránh cấu hình nhiều session repositories xung đột.
4. Cookie tên `__Host-session` phải có `Secure`, `Path=/`, không có `Domain`; nếu thực tế trả `Domain` hoặc dùng HTTP, không đáp ứng quy tắc prefix.
5. Spring Session lưu **HTTP session attributes**. Nó không tự bảo đảm mọi OAuth refresh token được mã hóa, có refresh locking hoặc được revoke đúng.

Nếu cấu hình vẫn dùng cookie `JSESSIONID` của servlet container hay `SESSION` theo một cấu hình Spring Session, cần thống nhất tên cookie trong serializer, logout handler và kiểm thử. Không chỉ đổi string trong Java rồi giả định cookie thực tế đã đổi.

### 13.3. OAuth2AuthorizedClientRepository và token custody

Spring Security có abstraction như `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientRepository` và `OAuth2AuthorizedClientService` để quản lý access/refresh token gắn client/principal. Nơi lưu thực tế phụ thuộc implementation và cấu hình.

Đối với BFF:

- Kiểm client registration là **confidential client** khi backend đủ khả năng bảo vệ credentials, cùng cấu hình PKCE theo chính sách.
- Đảm bảo authorized client/tokens chỉ nằm ở **server-side**; không đưa token vào API JSON cho browser.
- Kiểm implementation đang lưu token trong session, memory, JDBC hay custom store và cách bảo vệ dữ liệu lúc lưu.
- Nếu dùng refresh token rotation, cần cơ chế concurrency/lost update đã nói ở mục 10.
- Khi session logout hoặc revoked, xóa liên kết authorized client và cân nhắc gọi AS revocation endpoint.
- Không log `OAuth2AuthorizedClient` hoặc token response bằng `toString()`/JSON serializer.

**Lưu session vào Redis không đồng nghĩa OAuth2AuthorizedClient luôn được lưu trong Redis**. Hai abstraction có thể có storage path khác nhau; phải xác minh cấu hình thực tế.

### 13.4. Cấu hình cookie không thay Resource Server validation

BFF dùng session cookie để nhận dạng browser, nhưng khi gọi downstream API vẫn gửi **OAuth access token** dành cho API. Orders Resource Server phải xác minh chữ ký/issuer/audience/expiry/scope hoặc introspection trước khi truy cập dữ liệu, dù BFF và API do cùng đội vận hành.

## 14. Ranh giới tin cậy giữa Browser, BFF, AS và Resource Server

Giả sử web app phục vụ người dùng `user-742` ở tenant Beta:

~~~text
Browser -> BFF:
  Cookie: __Host-session=RANDOM_SESSION_ID
  GET /tenants/beta/orders/42

BFF:
  lookup session ID -> principal user-742
  check active session, idle/absolute expiry
  check tenant context and application-level policy
  get access token for orders-api from protected token store

BFF -> Orders API:
  Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS
  GET /tenants/beta/orders/42

Orders API:
  verify access token iss, aud=orders-api, exp, scope=orders:read
  verify principal/client, tenant membership and order ownership
  return only permitted fields
~~~

### 14.1. Tại sao phải kiểm hai lần?

- **BFF** xác minh session cookie, CSRF và trạng thái phiên để xác định browser request có được tiếp tục hay không.
- **Resource Server** xác minh access token và quyền trên tài nguyên để bảo vệ API khỏi những caller không được phép, kể cả BFF bị cấu hình sai hoặc client khác.
- **AS/OP** chịu trách nhiệm cấp token/đăng nhập và kiểm các grant; không nhất thiết biết mọi policy của đơn hàng tại thời điểm request.

Không được gắn role toàn cục `admin` vào session rồi dùng quyền đó ở mọi tenant. Một user có thể admin ở tenant Anpha nhưng viewer ở Beta; quyết định phải theo **(principal, target tenant, action, resource)**.

### 14.2. Session ID không phải OAuth access token

Session cookie là bí mật để BFF tra trạng thái nội bộ. API không nên nhận nguyên session ID của BFF như token OAuth, trừ khi có một mô hình xác thực session riêng đã được thiết kế và bảo vệ. Trong OAuth BFF thông thường:

~~~text
Browser <-> BFF         : session cookie
BFF <-> Resource Server : OAuth access token
BFF <-> Authorization Server : OAuth grant / refresh token
~~~

Dù session ID và opaque access token đều là chuỗi khó đoán, **issuer, nơi xác minh, audience và mục đích sử dụng khác nhau**.

### 14.3. Session tồn tại không đồng nghĩa OAuth grant còn hợp lệ

User có thể bị xóa membership, client bị disabled hoặc refresh grant bị thu hồi trong khi BFF session vẫn active. Khi gọi API, backend phải xử lý token validation/refresh failure đúng policy; với thao tác nhạy cảm, có thể cần tra quyền hiện tại/step-up.

Không sử dụng session `authenticated=true` để bỏ qua `aud`, `scope` hoặc object-level authorization.

## 15. Session hijacking, replay và logout

### 15.1. Nếu attacker lấy session cookie

Session ID sinh bằng CSPRNG khó đoán nhưng **một bản sao thật bị lộ** qua log, thiết bị nhiễm mã độc hoặc kết nối sai cấu hình vẫn có thể bị sử dụng lại trước khi phiên hết hiệu lực.

Các biện pháp:

- HTTPS, cookie `Secure`/`HttpOnly`/`SameSite` và host-only khi phù hợp.
- Không đặt session ID trong query string, logs, trace baggage, metric labels hoặc error response.
- Session rotation sau login/privilege change; idle và absolute timeout.
- Server-side invalidation khi logout, revoke account/session hoặc phát hiện dấu hiệu compromise.
- CSRF, XSS, CSP và reauthentication/transaction confirmation cho thao tác nhạy cảm.
- Giám sát hành vi bất thường và cung cấp tính năng xem/đăng xuất phiên theo thiết bị nếu sản phẩm yêu cầu.

IP/User-Agent có thể là **tín hiệu rủi ro**, nhưng khóa cứng session theo IP có thể gây false positive ở mạng di động/NAT/roaming, còn header client có thể bị giả mạo. Đánh giá bảo mật và quyền riêng tư trước khi đưa vào policy.

### 15.2. Nếu OAuth token bị lộ từ backend store

Cookie `HttpOnly` chỉ bảo vệ phía browser, **không ngăn việc đánh cắp token nếu server-side store hoặc backup bị chiếm**.

- Access JWT hợp lệ có thể bị phát lại ở RS đến `exp` nếu không có revocation/state check.
- Opaque token có thể bị vô hiệu sớm qua AS/lookup/introspection, tùy cache.
- Refresh token bị lộ có thể cho phép xin access token mới nếu đủ binding/điều kiện; rotation/reuse detection và client authentication giảm rủi ro.
- DPoP/mTLS sender-bound token giúp hạn chế việc dùng bản sao thiếu proof sở hữu khóa/chứng chỉ, nhưng RS phải xác minh binding thật.

Phải bảo vệ Redis/JDBC/token store bằng network isolation, least privilege, TLS, encryption/secret management, backup policy và audit. Không coi “server-side” là đồng nghĩa không thể rò bí mật.

### 15.3. Logout: ít nhất ba việc có thể cần tách riêng

1. **BFF session logout:** invalidate/delete phiên trên server và trả cookie hết hiệu lực đúng tên/path/domain.
2. **OAuth token/grant revocation:** xóa authorized-client state, cân nhắc gửi revocation đến AS (RFC 7009) hoặc theo cơ chế provider; không mặc định refresh token tự hết hạn khi xóa cookie.
3. **OIDC provider/global logout:** nếu cần single logout giữa nhiều ứng dụng, dùng cơ chế OP/front-channel/back-channel tương ứng được hỗ trợ, với bảo vệ theo profile.

**Xóa cookie browser không có nghĩa session cũ đã bị vô hiệu tại server.** Và việc revoke refresh token không mặc nhiên thu hồi mọi access JWT đã cấp mà RS vẫn kiểm cục bộ.

## 16. Khi nào nên dùng server-side session store?

| Bối cảnh | Hướng cân nhắc | Trade-off |
|---|---|---|
| Web app có backend/BFF và cần giữ refresh token khỏi JavaScript | **Session cookie + server token store** | CSRF, session lifetime, Redis/JDBC và refresh concurrency |
| SPA gọi trực tiếp API bằng access token | Kiến trúc OAuth browser client phù hợp, cân nhắc chuyển sang BFF | Token exposure cho JS, bảo vệ storage và XSS |
| API stateless service-to-service | Thường không cần browser session; dùng access token đúng audience | Client credentials, secret management và API authorization |
| Ứng dụng một node nhỏ trong môi trường hạn chế | In-memory session có thể chấp nhận theo yêu cầu | Restart mất session, không scale/failover tự nhiên |
| Web nhiều instance cần logout toàn cụm | Redis/JDBC/distributed session store | Phụ thuộc store, latency, consistency và eviction/cleanup |
| Hệ thống yêu cầu vô hiệu hóa quyền gần như tức thời | Stateful session + state/revocation checks cho token | Cache invalidation, hiệu suất và độ sẵn sàng |
| Cross-site embedded app | Thiết kế cookie/CSRF/CORS/browser restrictions riêng | Third-party cookie policy và gia tăng bề mặt tấn công |

Không có thiết kế nào tự động an toàn tuyệt đối. **Lợi ích chính của BFF/session store là giảm OAuth token exposure ở browser**, đổi lại backend phải giữ và bảo vệ phiên/secret có trạng thái.

## 17. Ma trận kiểm thử bảo mật

Một hệ thống session store nên được kiểm thử ở cả **HTTP layer**, **session repository**, **OAuth token store** và **Resource Server**.

| Tình huống | Kết quả mong đợi |
|---|---|
| Cookie thiếu hoặc không hợp lệ | Không tạo authenticated session ngầm; chuyển login/trả `401` theo hợp đồng. |
| Session ID có định dạng đúng nhưng không có trong store | Từ chối, không tự tạo bản ghi cho người dùng đã đăng nhập. |
| Session bị revoke hoặc logout | Cookie cũ không còn được chấp nhận ở bất kỳ instance nào theo policy. |
| Idle timeout đã hết | Từ chối dù cookie trình duyệt vẫn tồn tại. |
| Absolute timeout đã hết nhưng request vừa hoạt động | Từ chối/yêu cầu reauthentication. |
| Đăng nhập từ anonymous session có ID do attacker biết | ID mới sau login; ID cũ không có quyền authenticated. |
| Cookie thiếu `Secure`, `HttpOnly` hoặc cấu hình `SameSite` sai | Integration test phát hiện `Set-Cookie` không đạt yêu cầu. |
| Cookie tên `__Host-session` nhưng có `Domain` | Không thỏa ràng buộc prefix; phải sửa cấu hình. |
| Request thay đổi trạng thái không có CSRF token | Bị chặn theo CSRF policy. |
| Cross-site request có Origin không được phép | Không vượt qua kiểm Origin/CSRF/CORS. |
| XSS thử đọc `HttpOnly` cookie | Không đọc trực tiếp được qua JS; các hành vi XSS khác vẫn cần phòng vệ. |
| Redis/JDBC không sẵn sàng | Không fail open; trả lỗi/reauth hợp lệ và an toàn. |
| Session bị xóa do eviction | Không chấp nhận cookie như phiên hợp lệ. |
| Hai BFF request đồng thời refresh một token | Không lost update hoặc gây reuse do race nội bộ. |
| Refresh token cũ đã rotate được dùng lại | Bị AS từ chối; BFF xử lý grant/session theo policy. |
| User bị khóa hoặc bị gỡ khỏi tenant | Phiên/quyền bị vô hiệu hoặc rechecked trong giới hạn policy. |
| JWT access token đúng chữ ký nhưng sai `aud` | Resource Server từ chối. |
| Token đúng `aud` nhưng thiếu `scope` hoặc không có quyền với resource | Resource Server từ chối. |
| ID token được đưa vào header Bearer của Resource Server | Từ chối token sai mục đích/đối tượng nhận. |
| Session logout nhưng JWT access token còn hạn | Hành vi theo TTL/revocation cam kết, không giả định logout BFF thu hồi JWT. |
| Session schema thay đổi khi rolling deployment | Phiên không được deserialize thành quyền sai hoặc authenticated mặc định. |
| Session ID/refresh token xuất hiện trong logs/traces | Test thất bại; chặn thu thập và redact tại nguồn. |
| Browser phục hồi cookie sau restart | Server vẫn kiểm idle/absolute/status trước khi công nhận phiên. |

### 17.1. Canary credential để kiểm rò rỉ

Sử dụng **giá trị giả** trong môi trường test; không dùng cookie hay OAuth token thật.

~~~text
CANARY_SESSION_ID_DO_NOT_LOG_007
CANARY_ACCESS_TOKEN_DO_NOT_LOG_007
CANARY_REFRESH_TOKEN_DO_NOT_LOG_007
~~~

Đưa chúng vào các luồng cookie, token refresh thử nghiệm và request lỗi; quét application logs, gateway logs, OpenTelemetry attributes/events, collector, APM và alert sinks.

**Yêu cầu:** không có giá trị canary trong telemetry hoặc HTTP error response; vẫn có `trace_id`, `http.route`, HTTP status và error code an toàn.

### 17.2. Kiểm thử session lifecycle với pseudocode

~~~text
test "session fixation":
    oldId = createAnonymousSession()
    performValidOidcLoginUsing(oldId)
    newId = responseSessionCookie()

    assert newId != oldId
    assert oldId cannot access authenticated endpoint
    assert newId can access endpoint after authorization checks

test "logout across nodes":
    sid = loginOnNodeA()
    assert nodeB.canReadSession(sid)

    logoutOnNodeA(sid)

    assert nodeA.rejects(sid)
    assert nodeB.rejects(sid)

test "idle and absolute expiry":
    sid = createSession(idle=30m, absolute=8h)
    advanceTrustedTestClock(31m)
    assert requestWith(sid) is denied

    sid2 = createSession(idle=30m, absolute=8h)
    keepActiveWithinIdleFor(9h)
    assert requestWith(sid2) is denied by absolute policy

test "refresh single-flight":
    createGrantWithExpiringAccessAndRefreshTokenR1()
    runTwoRequestsConcurrentlyOnDifferentNodes()
    assert no stale refresh token overwrites newer value
    assert no unnecessary reuse-triggered grant revocation
~~~

Các phép test là pseudocode; dùng clock test và mock AS phù hợp, không dựa vào `Thread.sleep` để chứng minh expiry. Với Redis/JDBC thật, thêm integration tests mô phỏng failover, eviction, network interruption và rollback deployment.

## 18. Tình huống thực hành: SaaS nhiều tenant

Hệ thống đặt:

~~~text
OIDC issuer:         https://login.example.com
Confidential client: shop-bff
Resource Server:     orders-api
User:                user-742

Membership:
  tenant-anpha -> admin
  tenant-beta  -> viewer

Browser session:
  principal = user-742
  active tenant = tenant-beta
  idle timeout = 30 minutes
  absolute timeout = 8 hours

OAuth access token:
  issuer = https://login.example.com
  audience = orders-api
  scope = orders:read
  exp = within current session lifetime
~~~

### Câu hỏi 1: đổi tenant bằng header?

Browser sửa `X-Tenant-Id: tenant-anpha` và muốn được dùng quyền admin Anpha ngay. Có được cho phép không?

**Không tự động.** BFF và RS phải kiểm tenant context đã xác thực, membership/role tại tenant mục tiêu và quyền trên resource. Nếu ứng dụng gắn một active tenant vào phiên/token, cần luồng chuyển tenant được kiểm soát và cập nhật state/token phù hợp. Header do client tự gửi không phải bằng chứng quyền.

### Câu hỏi 2: phiên còn, access token hết hạn?

Session còn 5 giờ absolute lifetime nhưng access JWT vừa hết hạn. Người dùng bắt buộc đăng nhập lại ngay không?

**Không nhất thiết.** BFF có thể dùng refresh token ở server theo grant hợp lệ để xin access token mới. Tuy nhiên, nếu refresh token đã bị thu hồi, client/grant bị vô hiệu hoặc policy yêu cầu reauthentication thì BFF phải xử lý tương ứng. Không lấy `exp` của access JWT làm hạn duy nhất của browser session.

### Câu hỏi 3: chỉ xóa cookie khi logout?

Người dùng logout, BFF xóa cookie browser nhưng giữ session record active thêm 10 phút. Có an toàn không?

**Không phù hợp với kỳ vọng logout.** Nếu attacker đã sao chép cookie, session cũ vẫn có thể sử dụng. Logout phải invalidate/revoke phía server và bảo đảm các node không nhận cookie cũ theo chính sách.

### Câu hỏi 4: Redis mất kết nối?

BFF không thể tra session store nhưng cookie có dạng hợp lệ. Backend có nên tự cho phép để tránh lỗi dịch vụ không?

**Không.** Không có bằng chứng phiên active đã được kiểm; phải fail closed. Có thể trả lỗi tạm thời hoặc yêu cầu login lại tùy trải nghiệm, nhưng không cấp quyền chỉ dựa vào cookie.

### Câu hỏi 5: đưa refresh token vào cookie HttpOnly cho đơn giản?

Điều này có thể tồn tại trong các kiến trúc khác nhau, nhưng **thay đổi mục tiêu của BFF giữ OAuth token chỉ ở server**. Với mô hình ở đây, browser nên cầm session ID random, còn refresh token được bảo vệ trong server-side authorized-client/token store. `HttpOnly` không thay thế việc bảo vệ token, CSRF/XSS và server revocation.

### Câu hỏi 6: hai request đồng thời refresh R1?

BFF instance A dùng `R1` lấy `R2`; instance B vừa đọc `R1` từ trước và cũng refresh. Cần sửa gì?

**Đồng bộ refresh theo grant/session**, đọc lại sau lock, ghi token mới atomically, xử lý lỗi rotation/reuse và trường hợp process crash. Không retry vô hạn token đã rotate và không để writer cũ ghi đè trạng thái mới.

### Bài tập thiết kế

Hãy viết bản phác thảo cho session service gồm: `principal_id`, `created_at`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at`, `status`, `active_tenant_id` (nếu có), `authorized_client_ref` và `session_version`. Sau đó trả lời:

1. Tài khoản ứng dụng nào được đọc/ghi session store? Có cần phân quyền Redis ACL/schema riêng không?
2. Raw session ID có xuất hiện trong DB key, debug log hoặc metrics không?
3. Có cần tách token store để mã hóa và rotate refresh token độc lập không?
4. Logout toàn cụm và revoke user/tenant membership được lan truyền ra sao?
5. Khi store bị lỗi, request trả phản hồi nào mà không làm lộ token?
6. Đã có test chứng minh session fixation protection, CSRF, expiration và refresh race chưa?

## 19. Checklist triển khai cuối bài

- [ ] Đã phân biệt browser session, OP/AS session, access token, refresh token và ID token.
- [ ] Nếu dùng BFF, browser chỉ giữ session ID; OAuth token được giữ phía server và không trả về JavaScript.
- [ ] Session ID được sinh từ CSPRNG/framework, đủ entropy, không chứa user ID hoặc timestamp dễ đoán.
- [ ] Cookie có `Secure`, `HttpOnly`, `SameSite`, Path/Domain đúng; `__Host-` chỉ dùng khi thỏa mọi ràng buộc.
- [ ] HTTPS/TLS và proxy trust được cấu hình an toàn, không tin forwarded headers tùy ý.
- [ ] Có session rotation khi login/privilege transition để chống session fixation.
- [ ] Session record có idle timeout, absolute timeout, revoke state và server-side validation mỗi request.
- [ ] Logout invalidate session phía store và xóa cookie đúng tên/path/domain; không chỉ xóa cookie.
- [ ] CSRF protection áp dụng cho web cookie-authenticated; XSS/CSP/output encoding cũng được xử lý.
- [ ] Redis/JDBC session store có TLS, ACL, least privilege, backup protection, TTL, cleanup và fail-closed behavior.
- [ ] Session serialization có schema/versioning, giới hạn kiểu dữ liệu và rollback/migration an toàn.
- [ ] Authorized-client/token store bảo vệ refresh token, không log/trace raw secrets.
- [ ] Refresh token rotation có concurrency control/single-flight/CAS thích hợp, không dùng lại token đã rotate.
- [ ] Resource Server vẫn kiểm access token `iss`, `aud`, `exp`, `scope` và quyền trên tài nguyên/tenant.
- [ ] Revocation BFF session, OAuth token/grant và OP logout có chính sách riêng, không giả định tác động dây chuyền.
- [ ] Có negative tests cho session hijacking, fixation, CSRF, timeout, logout nhiều node, Redis failure và refresh race.
- [ ] Không xuất raw session cookie, access/refresh token, authorization code hoặc OAuth secrets vào log/trace.
- [ ] Khi thiếu bằng chứng phiên/authorization hợp lệ, hệ thống **fail closed**.

**Ghi nhớ:** server-side session store giữ trạng thái đăng nhập ở backend, để browser cầm một **session ID ngẫu nhiên** thay vì trực tiếp giữ OAuth access/refresh token. BFF giảm nguy cơ OAuth token bị JavaScript đọc, nhưng session ID vẫn là bearer secret. Hãy bảo vệ cookie, chống CSRF/fixation/replay, kiểm thời hạn và revocation tại store, bảo vệ Redis/JDBC/token store và để Resource Server tiếp tục kiểm audience, scope và quyền thực tế.

### Tài liệu chuẩn để tra cứu

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** OAuth client, access token, refresh token và grant.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bảo vệ bearer credential và giới hạn sử dụng.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code flow.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token tại AS.
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác minh trạng thái opaque access token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token dành cho Resource Server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained tokens.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** quản lý token, refresh rotation và phòng chống lạm dụng.
- **OpenID Connect Core 1.0:** ID token, nonce, audience và xác minh tại OIDC Client.
- **OWASP Session Management Cheat Sheet:** session ID, cookie, session fixation, timeout và logout.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** CSRF token, Origin, SameSite.
- **OWASP HTML5 Security Cheat Sheet / OAuth 2.0 Cheat Sheet:** browser storage và OAuth client security.
- **Spring Security Reference / Spring Session Reference:** session management, OAuth2 Login, CSRF, Redis-backed sessions.
- **Redis Security Documentation:** TLS, ACL, network isolation, persistence và backup.



