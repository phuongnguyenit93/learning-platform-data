# Bảo vệ state, callback và dữ liệu code trong trình duyệt

> **Chương: Authorization Code và PKCE.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Trọng tâm là **giữ đúng giao dịch đăng nhập**, **ngăn authorization code bị sử dụng sai** và **hạn chế lộ dữ liệu qua trình duyệt**.

## 1. Bài toán: trình duyệt là kênh chuyển tiếp, không phải nơi giữ bí mật dài hạn

Trong Authorization Code Flow, OAuth2/OIDC Client điều hướng trình duyệt sang Authorization Server. Sau đăng nhập và consent, Authorization Server chuyển trình duyệt về **redirect URI của Client**, thường với `code` và `state` trong query string. Client dùng `code` để gọi token endpoint qua kênh sau (back-channel). Vì trình duyệt có lịch sử truy cập, extensions, script, Referer và proxy/log trung gian, việc code xuất hiện trong URL callback tạo một bề mặt rủi ro riêng.

Ví dụ xuyên suốt:

- **Authorization Server / OpenID Provider:** `https://login.example.vn`, issuer cố định `https://login.example.vn`.
- **Confidential web client (Relying Party):** `portal-web` tại `https://portal.example.vn`, có backend Spring Boot.
- **Callback đã đăng ký:** `https://portal.example.vn/login/oauth2/code/portal`.
- **Resource Server:** `https://api.example.vn`, nhận access token do Authorization Server cấp.
- **Luồng:** Authorization Code + **PKCE S256**, `state` chống callback CSRF/nhầm giao dịch, và `nonce` riêng nếu dùng OIDC.

| Giá trị | Sinh và lưu ở đâu? | Đi qua trình duyệt? | Mục đích bảo mật |
|---|---|---|---|
| `state` | Client sinh ngẫu nhiên, liên kết với giao dịch/phiên browser | **Có**: authorization request và callback | Đối chiếu response với giao dịch do cùng Client khởi tạo; chống login CSRF, nhầm giao dịch |
| `code_verifier` | Client sinh ngẫu nhiên và giữ ở trạng thái giao dịch riêng | **Không nên đưa vào URL**; ở SPA nằm trong bộ nhớ/lưu trữ tạm của browser | Bí mật dùng chứng minh bên đổi code là bên đã mở giao dịch PKCE |
| `code_challenge` | Tính từ `code_verifier`, thường S256 | **Có**: authorization request | Ràng buộc code được cấp với `code_verifier` tương ứng |
| `code` | Authorization Server phát sau xác thực/consent | **Có**: callback URL của Authorization Code Flow thông thường | Credential dùng một lần để client đổi token; cần ngắn hạn, gắn client/redirect/PKCE |
| `nonce` (OIDC) | Client sinh và lưu cùng giao dịch | **Có** trong authorization request; xuất hiện trong ID Token để RP kiểm tra | Ràng buộc ID Token với giao dịch đăng nhập khi dùng nonce |
| Client secret/private key | Confidential client hoặc secret manager có thẩm quyền | **Không** | Xác thực confidential client tại token endpoint |
| Access/refresh token | Authorization Server cấp ở token endpoint | **Không xuất qua URL của Authorization Code Flow**; SPA có thể nhận token trong browser khi gọi token endpoint | Gọi API hoặc làm mới token; bảo vệ theo loại ứng dụng |

**Phân biệt trách nhiệm:**

- **Client/RP** sinh, lưu và kiểm tra `state`, duy trì `code_verifier`, xử lý callback, đổi code, xác minh ID Token nếu dùng OIDC.
- **Authorization Server** kiểm tra `client_id`/`redirect_uri`, lưu ràng buộc PKCE với authorization code, phát code ngắn hạn và từ chối code sai, hết hạn hoặc đã sử dụng.
- **Trình duyệt** chuyển hướng và mang authorization response về Client. Nó không phải một kho bí mật đáng tin cậy; không đặt client secret, refresh token hay `code_verifier` vào URL.
- **Resource Server** kiểm tra access token, issuer, audience, scope và chính sách API. Nó không dùng `state` hoặc authorization code để cấp quyền.

## 2. Luồng đầy đủ: ba giá trị bảo vệ ba ranh giới khác nhau

```mermaid
sequenceDiagram
    autonumber
    participant B as Trình duyệt
    participant C as OAuth2/OIDC Client (RP)
    participant AS as Authorization Server (OP)
    participant API as Resource Server

    B->>C: GET /private
    C->>C: Tạo transaction: state, verifier, nonce, redirect URI, issuer
    C->>C: challenge=BASE64URL(SHA256(verifier))
    C-->>B: 302 đến /oauth2/authorize?state&code_challenge&nonce...
    B->>AS: Authorization request qua HTTPS
    AS->>AS: Kiểm tra client_id, redirect_uri, scope, PKCE
    AS->>B: Đăng nhập và consent nếu cần
    AS->>AS: Phát code ngắn hạn, gắn client + redirect + challenge
    AS-->>B: 302 Location: https://portal.example.vn/login/oauth2/code/portal?code=...&state=...
    B->>C: GET callback?code=...&state=...
    C->>C: So khớp state với transaction đã lưu, consume một lần
    C->>C: Xác minh issuer/transaction; lấy code_verifier tương ứng
    C->>AS: POST /oauth2/token<br/>code + redirect_uri + code_verifier + client authentication
    AS->>AS: Kiểm tra code, client, redirect URI, PKCE; vô hiệu code
    AS-->>C: Token response qua HTTPS (OIDC có thể có id_token)
    C->>C: Nếu OIDC: xác minh id_token và nonce
    C-->>B: 303/302 đến trang sạch không mang code/state
    B->>C: GET /private
    C->>API: Authorization: Bearer ACCESS_TOKEN
    API-->>C: Tài nguyên nếu token/quyền hợp lệ
```

Dùng `state` **không thay thế** PKCE và ngược lại:

| Rủi ro | Cơ chế chính | Cơ chế bổ sung |
|---|---|---|
| Kẻ khác ép browser gọi callback bằng code thuộc phiên khác (login CSRF/code injection) | `state` ngẫu nhiên, gắn phiên, sử dụng một lần | PKCE và nonce/issuer check nếu áp dụng |
| Authorization code bị lộ qua URL và bị mang đi đổi token | PKCE S256 + client authentication khi confidential | Code dùng một lần, TTL ngắn, exact redirect binding, giảm rò rỉ |
| Code từ Authorization Server khác bị gửi nhầm token endpoint (mix-up) | Ràng buộc issuer/AS với transaction, kiểm tra issuer response khi hỗ trợ | Redirect URI riêng theo AS hoặc cơ chế theo RFC 9207 |
| ID Token cũ/thuộc giao dịch khác bị dùng lại | Kiểm tra chữ ký/`iss`/`aud`/`exp`/`nonce` | Session/transaction binding |
| Code/state bị ghi vào lịch sử, Referer, log | Callback chuyên dụng, không có third-party resources, no-referrer/no-store, điều hướng sang URL sạch sớm | PKCE, một lần sử dụng, giám sát và redaction |

Theo RFC 9700 (OAuth 2.0 Security Best Current Practice), các Client cần bảo vệ CSRF. Khi triển khai PKCE đúng và bảo đảm AS hỗ trợ, hoặc với OIDC nonce đúng cách, chuẩn nêu các cơ chế đó có thể góp phần chống CSRF; **giữ `state` gắn với phiên và sử dụng một lần vẫn là một lựa chọn vững chắc, dễ quan sát và kiểm thử**, đặc biệt với Client phục vụ nhiều issuer.

## 3. `state`: chống CSRF và khôi phục đúng giao dịch

### 3.1. Tính chất của một `state` an toàn

Một giá trị `state` tốt phải:

1. **Khó đoán:** sinh bằng bộ tạo số ngẫu nhiên mật mã như `SecureRandom`, với đủ entropy (ví dụ 32 byte ngẫu nhiên).
2. **Độc lập theo từng giao dịch:** hai tab hoặc hai lần người dùng bấm “Đăng nhập” nhận hai giá trị khác nhau.
3. **Gắn với trình duyệt/phiên đã khởi tạo:** Client lưu bản ghi giao dịch theo một session/server-side state có quyền kiểm soát; không tin `state` do callback gửi là bằng chứng tự đủ.
4. **Có thời hạn ngắn và sử dụng một lần:** xử lý response xong thì vô hiệu hóa transaction; code hoặc state replay không được tạo một phiên mới.
5. **Là mã tham chiếu khó đoán, không chứa dữ liệu riêng tư:** không chép email, access token, `code_verifier`, URL bất kỳ hoặc thông tin định danh vào `state` hiển thị trong URL.
6. **Áp dụng cho cả thành công lẫn lỗi:** callback `error=access_denied&state=...` cũng cần liên kết với request đúng.

Ví dụ sinh giá trị ngẫu nhiên riêng cho `state` bằng Java:

```java
import java.security.SecureRandom;
import java.util.Base64;

final class OAuthStateGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String createState() {
        byte[] random = new byte[32];    // 256 bit entropy
        RANDOM.nextBytes(random);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);
    }
}
```

Đoạn code chỉ **sinh state**, chưa phải implementation OAuth2 Client. Cần lưu state vào một giao dịch đáng tin và so sánh với response. Trong ứng dụng dùng `oauth2Login()`, Spring Security đã có thành phần quản lý authorization request/state; **không tự viết thêm controller callback** chỉ để áp dụng đoạn trên.

### 3.2. Lưu gì trong giao dịch?

Ví dụ mô hình dữ liệu lưu phía **backend client** (pseudocode, không phải một API của Spring):

```text
AuthTransaction {
  state:            "STATE_RANDOM_256_BITS"
  expectedIssuer:   "https://login.example.vn"
  clientId:         "portal-web"
  redirectUri:      "https://portal.example.vn/login/oauth2/code/portal"
  codeVerifier:     "RANDOM_PKCE_VERIFIER"
  nonce:            "RANDOM_OIDC_NONCE"
  browserSessionId: "SERVER_MANAGED_SESSION_REFERENCE"
  returnPath:       "/orders"           # Chỉ đường nội bộ đã kiểm tra
  createdAt:        2026-11-16T10:00:00Z
  expiresAt:        2026-11-16T10:05:00Z
  consumed:         false
}
```

Khi callback tới, Client cần tìm **đúng transaction do browser đó khởi tạo**, đối chiếu `state`, giới hạn thời gian và tiêu thụ **nguyên tử**. Với backend, có thể lưu theo session hoặc kho dữ liệu giao dịch có TTL; nếu có nhiều tab/IdP, có thể dùng map `state → transaction` theo session với chính sách xóa và giới hạn số lượng. Không cho người dùng đoán một state rồi truy xuất transaction của người khác.

**Thuật toán xử lý (pseudocode):**

```text
on GET callback:
    reject nếu request có code và error cùng lúc hoặc thiếu thông tin bắt buộc
    transaction = lookupPendingTransactionForCurrentBrowser(response.state)
    reject nếu không tìm thấy, hết hạn, sai session, sai client/issuer
    atomically consume transaction khi đã xác định hợp lệ
    nếu response.error:
        xử lý lỗi OIDC/OAuth2 theo transaction, không đổi code
    nếu response.code:
        gửi code, transaction.redirectUri và transaction.codeVerifier
        qua HTTPS back-channel tới token endpoint của issuer đã lưu
    chỉ sau khi token/ID Token được kiểm tra:
        tạo/cập nhật phiên client
        redirect browser tới returnPath nội bộ đã kiểm tra
```

Một endpoint callback bị gọi với `state` không hợp lệ phải **từ chối**, không được “khởi động lại và tự coi là hợp lệ”. Nếu có sai `state`, không thử đổi code để “xem có chạy không”. Không đặt lỗi kỹ thuật/giá trị state/code nguyên văn lên trang báo lỗi.

### 3.3. Nhiều tab, session store và vòng đời

- Một số implementation của `AuthorizationRequestRepository` theo session có thể không hỗ trợ song song vô hạn các authorization requests; **kiểm thử multi-tab** trước khi khẳng định hỗ trợ đầy đủ. Nếu cần, thiết kế repository lưu nhiều giao dịch theo state có TTL và giới hạn.
- Khi chạy nhiều pod, các callback có thể tới instance khác. Dùng session store chia sẻ (hoặc routing phiên phù hợp) để đọc đúng authorization request/`code_verifier`.
- Cookie session phải có `Secure`, `HttpOnly` và `SameSite` được kiểm thử trên top-level redirect; sai scheme/domain/path hoặc proxy forwarded headers sẽ làm mất session và gây `invalid_state`.
- Không tự ý đổi sang `SessionCreationPolicy.STATELESS` cho Spring Security `oauth2Login` nếu chưa xây dựng cơ chế lưu authorization request tương đương.
- `state` là giá trị **có thể xuất hiện ở URL**. Dù ngẫu nhiên, không coi nó như mật khẩu bí mật tuyệt đối. Hạn chế dữ liệu giao dịch lộ qua Referer/log.
- Khi người dùng nhấn “Back” rồi truy cập callback cũ, transaction đã tiêu thụ phải **bị từ chối**; có thể hiển thị lỗi nhẹ nhàng hoặc cho bắt đầu luồng đăng nhập mới.

## 4. PKCE S256: chứng minh ai được phép đổi authorization code

PKCE (Proof Key for Code Exchange, RFC 7636) giải quyết vấn đề code bị chặn và bị bên khác mang đi đổi token. Client sinh `code_verifier`, tính `code_challenge` và gửi challenge **trước** khi Authorization Server cấp code. Lúc đổi code, Client phải gửi **verifier gốc**; AS kiểm tra bằng cách tính lại challenge.

Với `S256`:

```text
code_verifier  = random string, 43–128 ký tự thuộc bảng ký tự RFC 7636
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

**Không dùng `plain` nếu hệ thống hỗ trợ S256.** Không lấy các chuỗi có thể đoán như timestamp, user ID hay session ID làm verifier. Không hardcode một verifier chung cho cả ứng dụng và không phát verifier lên URL của authorization request.

### 4.1. Sinh PKCE bằng Java

Ví dụ Java 17+ dưới đây độc lập với thư viện Spring (dùng trong test hoặc client tự triển khai giao thức; trong ứng dụng Spring Security nên để OAuth2 Client quản lý):

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

record PkcePair(String verifier, String challenge) {}

final class PkceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    static PkcePair newPair() throws GeneralSecurityException {
        byte[] random = new byte[32];
        RANDOM.nextBytes(random);

        String verifier = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

        String challenge = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);

        return new PkcePair(verifier, challenge);
    }
}
```

32 byte entropy sẽ cho verifier Base64URL không padding dài **43 ký tự**, đáp ứng độ dài PKCE. Digest SHA-256 là 32 byte, tạo challenge Base64URL dài **43 ký tự**. Chỉ truyền `challenge` ra authorization endpoint; giữ `verifier` trong dữ liệu giao dịch của Client và đưa nó vào **POST token request**. Nếu dùng SPA, verifier cần lưu trong bộ nhớ/trạng thái tạm của origin được bảo vệ và xóa sau khi xử lý; XSS vẫn có thể truy cập dữ liệu đang lưu trong trình duyệt, nên cần CSP và tránh third-party scripts.

### 4.2. Ba kiểm tra PKCE khác nhau

1. **Ở authorization endpoint của AS:** yêu cầu có `code_challenge` và `code_challenge_method=S256` theo chính sách client, validate định dạng và lưu challenge gắn với code sắp phát.
2. **Ở token endpoint của AS:** `code_verifier` phải có mặt và tái tạo đúng challenge đã ràng buộc. Thiếu/sai verifier ⇒ từ chối, thường là `invalid_grant`.
3. **Ở Client:** verifier dùng để đổi code phải là verifier lưu **cho cùng state/transaction**, không lấy từ callback, cookie do browser có thể sửa hoặc một verifier mới tự tạo tại token exchange.

PKCE không làm code vô hại khi bị lộ. Nếu kẻ tấn công lấy được đồng thời code và verifier qua XSS, storage hoặc log, nguy cơ vẫn tồn tại. Vì vậy PKCE đi cùng HTTPS, chống XSS, lưu verifier tối thiểu, TTL code ngắn và single-use code.

## 5. Callback: redirect URI chính xác và xử lý response an toàn

### 5.1. Redirect URI thuộc Client, không thuộc Authorization Server

Trong ví dụ, callback là:

```text
https://portal.example.vn/login/oauth2/code/portal
```

Đường dẫn này do **Spring Security OAuth2 Login trên Client** xử lý. Nó **không phải** `/oauth2/token` của AS và không phải đường dẫn tùy ý để trả giao diện có third-party assets. Với Authorization Code Flow thông thường, AS chuyển browser tới callback:

```http
HTTP/1.1 302 Found
Location: https://portal.example.vn/login/oauth2/code/portal?code=AUTH_CODE&state=STATE_RANDOM
Cache-Control: no-store
```

Dữ liệu trong ví dụ là placeholder. Ở phiên thực, AS còn phải kiểm tra client, xác thực người dùng, consent (nếu cần) và các ràng buộc khác trước khi phát code.

Theo RFC 9700, AS phải **so sánh redirect URI với URI đã đăng ký bằng chuỗi chính xác**, trừ ngoại lệ port cho redirect URI loopback của native app theo quy định. Không dùng so khớp prefix, wildcard, domain suffix tự chế hoặc cho thêm URL nhảy tiếp.

| URI đã đăng ký | URI request | Kết quả |
|---|---|---|
| `https://portal.example.vn/login/oauth2/code/portal` | Cùng chuỗi | Hợp lệ |
| Giống bên trái | `https://portal.example.vn/login/oauth2/code/portal/` | Không trùng vì thêm `/` |
| Giống bên trái | `http://portal.example.vn/login/oauth2/code/portal` | Không trùng vì khác scheme |
| Giống bên trái | `https://portal.example.vn.evil.test/login/oauth2/code/portal` | Không trùng vì khác host |
| Giống bên trái | `https://portal.example.vn/login/oauth2/code/portal?next=https://evil.test` | Không trùng nếu query này không được đăng ký chính xác |

AS phải **không chuyển hướng response** đến redirect URI sai hoặc chưa được xác minh. Ngay cả khi request sai, không được phản hồi lỗi theo redirect tới URI do attacker tự cung cấp. Các lỗi authorization response gửi về **URI đã xác minh** cũng phải kèm và được Client kiểm tra `state` theo hợp đồng giao thức.

### 5.2. Client xử lý callback theo thứ tự có kiểm soát

Tại callback, Client cần:

1. Đọc tham số `code`/**hoặc** `error` và `state`; không chấp nhận các tham số mâu thuẫn hoặc bị lặp theo cách khiến parser/validator hiểu khác nhau.
2. Khôi phục authorization request gốc từ session/transaction store **của chính browser** và đối chiếu state, issuer, registration ID/redirect URI.
3. Kiểm tra chống **authorization server mix-up** nếu Client hỗ trợ nhiều issuer (xem mục 5.3).
4. Khi response có `code`, đổi code tại **token endpoint đã gắn với request ban đầu**; không lấy token URL từ query của callback.
5. Chỉ sau token/ID Token validation mới tạo/cập nhật phiên Client và điều hướng tới trang đích **cùng origin/được allowlist**.
6. Không render trang callback với analytics/pixel/script bên ngoài khi URL còn chứa `code`/`state`; không đưa raw URL vào log.

Các giá trị `redirect_uri`, `client_id`, `code_challenge` và issuer cần liên kết với **authorization request gốc**. PKCE và client authentication chỉ hỗ trợ xác minh giao dịch khi chúng được lưu giữ và dùng đúng; tự lắp ghép token request từ query callback có thể làm sai ranh giới tin cậy.

### 5.3. Bảo vệ mix-up khi có nhiều Identity Provider

Một Client có thể đăng nhập bằng nhiều OP. Nếu callback từ OP A bị xử lý như đến từ OP B, Client có thể gửi code đến token endpoint sai, làm lộ code hoặc dẫn đến nhầm danh tính (authorization server mix-up).

Theo RFC 9700/RFC 9207, một biện pháp là sử dụng tham số `iss` trong authorization response khi OP hỗ trợ, kiểm tra **chính xác** với issuer đã lưu cho transaction. Với OIDC, có thể dùng bảo đảm issuer trong ID Token/response theo quy tắc tương ứng; một cách khác là đăng ký **redirect URI riêng cho từng Authorization Server**.

Không suy luận issuer đáng tin chỉ từ `iss` mà browser gửi rồi tự chọn token endpoint đó. **Nguồn gốc tin cậy** phải là cấu hình/transaction do Client tạo trước. Cần kiểm thử tùy phiên bản Spring Security và khả năng hỗ trợ `iss` trong authorization response, vì không phải mọi deployment đều xử lý RFC 9207 tự động.

## 6. Giảm lộ code và state qua trình duyệt

### 6.1. Những nơi code có thể lọt ra

| Kênh | Kịch bản | Hướng giảm rủi ro |
|---|---|---|
| **Referer/Referrer** | Callback render trang có ảnh/font/script từ domain ngoài hoặc người dùng bấm link ngoài; URL chứa `code`/`state` có thể xuất hiện trong Referer | `Referrer-Policy: no-referrer`, không dùng third-party resources trên callback, chuyển sang URL sạch sớm |
| **Browser history** | `callback?code=...&state=...` có thể được giữ trong history | Backend xử lý ngay và redirect sang URL không có tham số nhạy cảm; SPA dùng `history.replaceState(...)` sớm sau khi đọc state/code |
| **Reverse proxy/access logs** | NGINX/Ingress/APM ghi query string toàn bộ callback | Không ghi query nhạy cảm; redact `code`, `state`, `session_state` nếu có, `id_token`/token nếu xuất hiện |
| **Error pages và exception** | Stack trace/HTML hiển thị full request URL hoặc raw params | Trả lỗi chung, correlation ID; chỉ log loại lỗi, loại flow, client ID khi phù hợp |
| **Third-party JS, analytics, tag manager** | Script đọc `window.location.href` hoặc `location.search` | Không nhúng script không kiểm soát trên callback; CSP nghiêm ngặt, chỉ tài nguyên cần thiết |
| **Browser extension, XSS** | Script trái phép lấy dữ liệu trên origin của Client | Giảm XSS, CSP, dependency review, session cookie bảo vệ; ưu tiên BFF khi phù hợp |
| **URL được copy/screenshot** | Người dùng gửi callback URL trong ticket hoặc chat | Hiển thị URL sạch sau hoàn tất; hướng dẫn che `code`/`state` khi debug |
| **Token qua URL** | Ứng dụng tự redirect `?access_token=...` sau exchange | Không đưa access/refresh/ID Token lên URL; dùng session server-side hoặc cơ chế lưu an toàn |

**Authorization code không nên bị coi là vô hại chỉ vì “dùng một lần”.** Nó có thể bị đánh cắp **trước khi** Client kịp đổi. PKCE và client authentication giúp giảm khả năng lạm dụng code, nhưng ứng dụng vẫn phải tránh phát tán nó.

### 6.2. Callback xử lý nhanh và trả URL sạch

Với **server-side web client**, lý tưởng là callback được filter Spring Security nhận, kiểm tra state, thực hiện token exchange ở backend, tạo phiên rồi redirect sang trang đích không chứa code/state. Đừng dùng callback như một trang React/Thymeleaf chứa tracker và nút điều hướng khi query còn nguyên.

Response header khuyến nghị khi có dữ liệu nhạy cảm:

```http
Cache-Control: no-store
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'
X-Content-Type-Options: nosniff
```

CSP trên chỉ là một mẫu nghiêm cho trang callback đơn giản. Nếu callback chỉ trả `302`/`303` thì không nhất thiết có HTML để CSP điều khiển, nhưng **không ghi log query** và dùng `Cache-Control: no-store`, `Referrer-Policy: no-referrer` vẫn có ích. Kiểm thử response thực tế qua CDN/proxy; `no-store` không “xóa” được dữ liệu đã từng vào log hoặc history.

Với SPA buộc xử lý callback trong JavaScript, xử lý và làm sạch URL **trước khi** khởi chạy analytics/third-party bundle:

```javascript
// Minh họa tối giản cho callback SPA; vẫn cần OAuth2/OIDC library chuẩn.
const params = new URLSearchParams(window.location.search);
const code = params.get("code");
const state = params.get("state");
const error = params.get("error");

// Đọc values trước, loại query ngay từ address bar/history hiện hành.
// Không log hay gửi code/state cho analytics.
window.history.replaceState(
  window.history.state,
  "",
  window.location.pathname
);

// Bước tiếp theo: gọi cơ chế kiểm tra transaction/state, PKCE
// và exchange token đã được thiết kế cho public browser client.
// Không tự tin code/state chỉ vì URL có hai tham số đó.
```

Đoạn code trên **chỉ minh họa thao tác làm sạch URL**, không phải một OAuth2 Client an toàn hoàn chỉnh. Nếu callback dùng query khác không nhạy cảm, chỉ giữ lại những tham số được allowlist; không preserve toàn bộ query. Việc gọi `replaceState` không ngăn XSS hoặc browser extension đã thấy URL trước đó.

### 6.3. Có nên đổi `response_mode` sang `form_post`?

Một số OP/client hỗ trợ `response_mode=form_post`, đưa authorization response tới callback bằng HTML form POST thay vì query URL. RFC 9700 đề cập đây là một lựa chọn giảm rủi ro trong browser history/Referer.

Tuy nhiên:

- Cần **cả hai phía hỗ trợ** response mode tương ứng; đừng tự thêm `response_mode=form_post` rồi giả định Spring Security OAuth2 Login mặc định sẽ nhận POST.
- Cross-site POST có thể gặp khác biệt với `SameSite=Lax` session cookie và CSRF filter; cần kiểm thử và cấu hình callback riêng có kiểm soát.
- Form POST chỉ **giảm một đường rò rỉ**, không thay thế kiểm tra state, PKCE, issuer, redirect URI, TTL hoặc xác thực client.

Đối với Spring MVC web client dùng callback mặc định, dùng Authorization Code + PKCE trên **top-level GET redirect** vẫn có thể an toàn khi callback được xử lý nhanh, URL không bị log và code được ràng buộc chặt.

## 7. Đổi code tại token endpoint và chống replay

Token request phải đi qua HTTPS, dùng `application/x-www-form-urlencoded` và gửi `code_verifier` cùng code/redirect URI. Ví dụ request của confidential client:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_CREDENTIALS

grant_type=authorization_code&code=AUTH_CODE&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=ORIGINAL_PKCE_VERIFIER
```

Dòng request là **mẫu minh họa**; giá trị mã hóa/secret không sử dụng được trong thực tế. `Authorization: Basic ...` áp dụng khi client đăng ký `client_secret_basic`; một **public client** dùng `ClientAuthenticationMethod.NONE` không gửi confidential client secret, nhưng phải mang `client_id` theo cách giao thức/triển khai yêu cầu.

Server kiểm tra:

1. Code tồn tại, chưa hết hạn, chưa bị dùng/thu hồi.
2. Code gắn **đúng RegisteredClient** đang đổi và `redirect_uri` đã dùng trong authorization request.
3. `code_verifier` đúng với `code_challenge` đã ràng buộc với code, theo `S256`.
4. Client authentication hợp lệ nếu client thuộc loại confidential; grant/scope/consent đúng chính sách.
5. Sau exchange thành công, code **không thể dùng lại**; yêu cầu đổi code lần hai phải bị từ chối, thường với `invalid_grant`.

**Không gửi code qua GET đến token endpoint**, không lưu code vào access token, không phát access token qua query URL. Token response thường chứa `access_token`, có thể có `refresh_token` và (trong OIDC) `id_token`; giữ token trong tầng Client phù hợp. Nếu cần debug, log `invalid_grant` và correlation ID thay vì toàn bộ request body/Authorization header.

Theo RFC 6749/RFC 9700, authorization code phải bị vô hiệu sau lần dùng đầu. Khi phát hiện code dùng lại, server nên cân nhắc thu hồi token được phát từ code đó theo chính sách để hạn chế replay; hành vi cụ thể phải được kiểm thử ở Spring Authorization Server triển khai.

## 8. Cấu hình Spring Authorization Server bắt buộc PKCE và callback chính xác

Dưới đây là bean minh họa **phía Authorization Server**, đăng ký một confidential web client `portal-web`. Các API tương ứng Spring Authorization Server 1.x; hãy dùng phiên bản Spring Boot/Spring Security/Spring Authorization Server tương thích trong dự án.

```java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        @Value("${PORTAL_CLIENT_SECRET}") String rawSecret) {

    RegisteredClient portal = RegisteredClient
            .withId("registration-portal-web")
            .clientId("portal-web")
            .clientSecret(passwordEncoder.encode(rawSecret))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .authorizationCodeTimeToLive(Duration.ofMinutes(3))
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(portal);
}
```

**Giải thích các lựa chọn:**

- `requireProofKey(true)` buộc client dùng PKCE cho Authorization Code Flow. **Public client** càng phải dùng PKCE; ví dụ confidential client cũng yêu cầu để tăng khả năng chống code injection/interception.
- `redirectUri(...)` là **đường nhận callback phía Client**, không phải token endpoint. Chỉ khai báo URI công khai hợp lệ, so khớp chính xác.
- `authorizationCodeTimeToLive(Duration.ofMinutes(3))` giới hạn thời gian sống code; 3 phút chỉ là **ví dụ chính sách**, không phải quy định bắt buộc.
- `passwordEncoder.encode(rawSecret)` lưu **hash** của client secret phía Authorization Server; secret bản rõ nằm ở secret store của Client. Không hardcode mật khẩu vào mã nguồn.
- `requireAuthorizationConsent(true)` yêu cầu xử lý consent theo chính sách; nó **không thay thế** `state` hay PKCE.
- `InMemoryRegisteredClientRepository` chỉ phù hợp demo/test; production cần registry và authorization service bền vững, bảo đảm code dùng một lần xuyên các instance.

Cần bổ sung `PasswordEncoder` bean, `SecurityFilterChain` cho endpoint AS và user login, `AuthorizationServerSettings.issuer(...)`, `OAuth2AuthorizationService`/consent service và signing/JWKSource nếu phát JWT/OIDC token. Không lấy code demo trên làm một Authorization Server hoàn chỉnh.

### 8.1. Client public khác gì?

Nếu đăng ký SPA/native app, thay authentication method bằng `ClientAuthenticationMethod.NONE`, **không** có `clientSecret` và bắt buộc PKCE. Redirect URI phải phù hợp loại ứng dụng (HTTPS origin/callback được đăng ký chính xác; native app có quy tắc loopback riêng). Khả năng client giữ verifier/token trong browser làm mức rủi ro khác backend confidential client; xem mục 10.

### 8.2. Giữ code trong `OAuth2AuthorizationService`

Spring Authorization Server dùng `OAuth2AuthorizationService` quản lý authorization code và trạng thái authorization, với implementation in-memory/JDBC. Khi chạy nhiều pod, cần một nguồn dữ liệu **chia sẻ và nhất quán** để code do pod A cấp được pod B đổi một lần hợp lệ; không tự tạo bộ nhớ code riêng ở mỗi pod. Thiết kế storage/transaction đủ chắc để không có hai token exchanges đồng thời cùng dùng một code thành công.

Không tự xây controller `/oauth2/authorize` hoặc `/oauth2/token` chỉ để sửa callback: ưu tiên cấu hình endpoint/filter/provider có sẵn và kiểm thử bảo mật, nhất là PKCE, client binding và replay.

## 9. Spring Security OAuth2 Client: giữ state và verifier ở phía RP

Trên **ứng dụng Client Spring Boot** tại `https://portal.example.vn`, cấu hình OIDC như sau:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-idp:
            issuer-uri: https://login.example.vn

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Trong ví dụ:

- `/oauth2/authorization/portal` bắt đầu OAuth2 login trên Client, khác với `/oauth2/authorize` của AS.
- `/login/oauth2/code/portal` là callback mặc định do Spring Security OAuth2 Login nhận.
- `issuer-uri` để tìm metadata OP theo discovery và xác minh issuer OIDC; token endpoint không lấy từ tham số callback.
- Cookie session giữ dữ liệu tương quan authorization request. `SameSite=Lax` thường thích hợp top-level GET callback, nhưng phải **kiểm thử thực tế** qua reverse proxy và browser.
- Không đưa secret thật vào `application.yml`. `PORTAL_CLIENT_SECRET` được cấp từ secret store/biến môi trường.

### 9.1. Yêu cầu PKCE tường minh cho confidential Spring Security Client

Với Spring Security OAuth2 Client, chế độ public client có thể tự bật PKCE theo cấu hình. Nếu Authorization Server buộc PKCE cho **confidential client**, nên kiểm tra request thực tế và cấu hình resolver thêm PKCE một cách tường minh nếu bản Spring sử dụng chưa tự bật:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class PortalLoginSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clients) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                        clients, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint ->
                    endpoint.authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

`OAuth2AuthorizationRequestCustomizers.withPkce()` thêm `code_challenge`, `code_challenge_method` vào authorization request và lưu `code_verifier` trong **attributes của authorization request** để dùng ở token exchange. Nó không có nghĩa verifier an toàn nếu ứng dụng tùy biến repository và làm mất attribute đó.

Mặc định, Spring Security cung cấp `HttpSessionOAuth2AuthorizationRequestRepository` để lưu `OAuth2AuthorizationRequest` giữa lần redirect đi và callback về, giúp tìm lại request gốc và kiểm tra state. Với hệ thống multi-tab/multi-pod hoặc session lưu phân tán, nên kiểm thử trường hợp đồng thời thay vì tự giả định một request cache luôn hỗ trợ mọi tình huống.

### 9.2. Khi nào cần custom `AuthorizationRequestRepository`?

Chỉ custom khi có yêu cầu rõ ràng như nhiều tab song song, cookie policy đặc biệt hoặc kho session phân tán. Contract chính bao gồm:

```java
void saveAuthorizationRequest(
        OAuth2AuthorizationRequest request,
        HttpServletRequest httpRequest,
        HttpServletResponse httpResponse);

OAuth2AuthorizationRequest loadAuthorizationRequest(
        HttpServletRequest httpRequest);

OAuth2AuthorizationRequest removeAuthorizationRequest(
        HttpServletRequest httpRequest,
        HttpServletResponse httpResponse);
```

Đây là chữ ký **rút gọn để học tập**; xem interface/các nullability annotation đúng phiên bản. Custom implementation phải giữ **nguyên vẹn state, redirect URI, nonce, PKCE verifier và issuer/provider binding**, TTL và quy tắc consume. Không chuyển sang cookie unsigned chứa verifier; nếu dùng cookie cần thiết kế mã hóa/xác thực và cookie policy an toàn, chống replay và tampering.

Không viết một controller `@GetMapping("/login/oauth2/code/portal")` để “đọc code” khi `oauth2Login()` đã cấu hình: callback được xử lý bởi `OAuth2LoginAuthenticationFilter`. Handler tự chế dễ bỏ mất so khớp state, token exchange hoặc kiểm tra ID Token.

## 10. BFF so với SPA: code và token tồn tại ở đâu?

| Thiết kế | Nơi xử lý callback/code | Nơi giữ `code_verifier` | Nơi nhận/giữ token | Lưu ý bảo mật |
|---|---|---|---|---|
| **Confidential web client / Backend for Frontend (BFF)** | Server Spring Boot phía Client | Server-side session/authorization request store | Backend/authorized-client store; browser nhận cookie phiên | Hạn chế JS tiếp xúc token; CSRF/cookie/session vẫn phải bảo vệ |
| **SPA public client thuần browser** | JS ở origin SPA | Trạng thái giao dịch tạm bên browser | Browser nhận access token qua token endpoint; lưu theo threat model | Không có client secret đáng tin; bắt buộc PKCE, chống XSS và rò token |
| **Native public app** | Redirect qua browser hệ điều hành về app-link/loopback | Lưu tạm trong ứng dụng | App sử dụng token theo nền tảng | Theo RFC 8252, dùng external user-agent, callback được đăng ký, PKCE |

Khi có lựa chọn kiến trúc, **BFF** giảm số vị trí mà JavaScript có thể đọc token. Tuy nhiên, cần bảo vệ cookie, CSRF, session fixation và truy cập backend; BFF không loại bỏ mọi rủi ro.

Với SPA public client, cần thêm:

1. Sử dụng thư viện OAuth2/OIDC chuyên dụng hỗ trợ state, PKCE S256, nonce, discovery, issuer validation và callback cleanup.
2. Hạn chế third-party script và XSS bằng CSP, escaping và dependency review; không dùng long-lived token trong `localStorage` như một lựa chọn “mặc định an toàn”.
3. Đảm bảo CORS token endpoint chỉ cho phép origin cần thiết theo cấu hình AS; CORS **không thay thế** kiểm soát redirect URI, state/PKCE hay Authorization Server policy.
4. Dùng các cơ chế lưu token và làm mới token theo chuẩn, đặc tính của trình duyệt và chính sách nguy cơ; rút ngắn thời gian sống token khi phù hợp.
5. Không coi việc xóa query bằng `replaceState` là đủ để ngăn script ác ý chạy trước bước đó.

## 11. Kiểm thử bảo mật: trạng thái, callback, code và PKCE

Một bài kiểm thử đầy đủ cần có **Client, Authorization Server, browser/session và token endpoint**; không chỉ unit test hàm tạo state. Nên dùng tài khoản/credential giả trên môi trường test, và tuyệt đối không đưa code/verifier/token thật vào log test.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Thành công chuẩn | Đăng nhập Authorization Code + PKCE S256 với state hợp lệ | Client kiểm tra state, đổi code một lần, token hợp lệ; URL cuối sạch |
| Thiếu `state` ở callback | Loại bỏ tham số state | Client từ chối; không gọi token endpoint |
| `state` bị thay | Sửa một ký tự state | Client từ chối; không tạo session đăng nhập |
| `state` từ browser khác | Copy callback URL sang một browser khác chưa mở flow | Client từ chối vì không có transaction ràng buộc |
| Replay callback | Mở lại cùng URL callback sau khi đã xử lý | Không tạo phiên mới hoặc đổi code lần nữa |
| Nhiều tab | Mở đồng thời hai login requests với state khác nhau | Đúng cặp giao dịch hoặc lỗi rõ, không trộn state/verifier |
| Thiếu PKCE | Bỏ `code_challenge` khi RegisteredClient bắt buộc | Authorization Server từ chối authorization request |
| Sai `code_verifier` | Đổi code với verifier khác | Token endpoint từ chối, thường `invalid_grant` |
| Đổi code hai lần | Gửi cùng code đã dùng tới token endpoint | Lần sau bị từ chối; xem xét revocation policy nếu replay |
| Code hết hạn | Chờ quá TTL code rồi đổi | Token endpoint từ chối |
| Đổi redirect URI | Thêm `/` cuối, đổi scheme/host/port | AS từ chối URI sai; không redirect code ra ngoài |
| Sai `redirect_uri` lúc exchange | Dùng callback khác URI đã dùng khi cấp code | Token endpoint từ chối |
| Thử open redirect | Gửi `next=https://evil.test` hoặc URI na ná domain thật | Không được dùng URI tùy ý để chuyển code |
| Mix-up đa issuer | Cố dùng callback từ issuer A cho transaction B | Client từ chối hoặc tách callback đúng AS |
| Lộ qua Referer | Callback có external image/link trong môi trường test | Không gửi full URL nhạy cảm tới origin ngoài; tốt nhất không có external asset |
| Browser history | Hoàn thành login rồi xem URL/history | Trang cuối không còn code/state; callback đã xử lý không thể replay |
| Access log | Kiểm tra proxy/APM logs khi callback có code giả | Không lưu raw `code`/`state`/token/verifier |
| Lỗi từ AS | `error=access_denied&state=...` đúng/sai | Đúng: hiển thị lỗi an toàn; sai: từ chối callback |
| Mất session | Xóa cookie rồi dùng callback | Không đổi code; hướng dẫn bắt đầu lại flow |
| Sự cố reverse proxy | Request chạy qua HTTPS public host, pod khác xử lý callback | URI, cookie, session và state khớp |
| OIDC nonce sai | ID Token có nonce khác transaction | RP từ chối ID Token |
| SPA script đọc URL | Giám sát network và tải third-party trên callback | URL được làm sạch sớm, không phát dữ liệu nhạy cảm đi ngoài |

### 11.1. Ba bài kiểm thử tích hợp ưu tiên

**Kiểm thử A — callback CSRF:** Dùng browser 1 tạo state `S1`, browser 2 tạo state `S2`. Gửi callback chứa code từ browser 2 cùng state `S2` vào browser 1. Client phải **không** liên kết tài khoản của browser 2 cho browser 1; không được bỏ kiểm state vì code có thể hợp lệ trên server.

**Kiểm thử B — PKCE mismatch:** Tạo authorization request với `code_challenge=BASE64URL(SHA256(V1))`, lấy code và đổi bằng `code_verifier=V2`. Kết quả phải từ chối; đổi code đã thành công lần trước phải bị từ chối cả khi dùng đúng `V1`.

**Kiểm thử C — rò code qua browser:** Kiểm tra callback có `code` và `state` bằng một trình duyệt/test proxy. Đảm bảo không gửi request tới origin thứ ba trong khi URL này còn tồn tại; log reverse proxy/observability đã redact; client đưa trình duyệt sang trang sạch sau khi xử lý.

### 11.2. Các lỗi thường gặp khi tích hợp Spring

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `invalid_state` hoặc `authorization_request_not_found` | Cookie/session mất, multi-tab, session store/TTL, callback vào sai instance | Kiểm tra `HttpSessionOAuth2AuthorizationRequestRepository`, SameSite/HTTPS và session routing |
| `invalid_redirect_uri` | Khác `{baseUrl}` do proxy, trailing slash, http/https hoặc registration ID | So sánh đúng callback trong request, RegisteredClient và ClientRegistration |
| `invalid_grant` khi đổi code | Verifier sai/mất, code hết hạn/đã dùng, redirect URI hoặc client sai | Kiểm tra transaction binding, PKCE S256, code TTL và single-use |
| `invalid_client` | Secret của confidential client sai hoặc method khác cấu hình | Kiểm tra client authentication; giữ secret ngoài log |
| PKCE không xuất hiện ở authorization request | Confidential client chưa bật PKCE ở resolver hoặc cấu hình bị override | Bật `withPkce()` phù hợp, kiểm tra code challenge ngoài trình duyệt |
| Sau login browser vẫn thấy `code` | Callback render trang nội dung/SPA chưa dọn URL | Dùng callback filter server-side và redirect; hoặc SPA cleanup sớm |
| OAuth2 callback trả 404/405 | Tự định nghĩa handler trùng filter, callback path/HTTP method khác cấu hình | Dùng callback mặc định hoặc đồng bộ `redirectionEndpoint` và redirect URI |
| Callback không quay về trang gốc | Saved request/return path mất hoặc tùy biến success handler sai | Lưu return path nội bộ, không dùng open redirect |
| Code hợp lệ nhưng OIDC login lỗi | `iss`/`aud`/`nonce` ID Token không khớp | Kiểm tra discovery, issuer và transaction OIDC |
| Chạy một pod tốt, nhiều pod lỗi | Authorization service hoặc session store chỉ nằm trong RAM | Dùng persistence/session chia sẻ và atomic consume |

## 12. Checklist vận hành trước khi công bố Authorization Code Flow

- [ ] Mỗi authorization request có `state` ngẫu nhiên, gắn browser/transaction, TTL rõ ràng và sử dụng một lần.
- [ ] Client không chứa dữ liệu nhạy cảm trong `state`, không tin `state` do callback gửi mà thiếu transaction server-side.
- [ ] PKCE `S256` được bật và kiểm tra ở cả authorization/token endpoints; `code_verifier` không nằm trong URL hoặc log.
- [ ] Authorization Server so khớp **exact redirect URI**, không cho wildcard hoặc open redirect.
- [ ] Authorization code ngắn hạn, gắn client/redirect/PKCE, chỉ đổi một lần và chống replay.
- [ ] Client dùng issuer/token endpoint từ cấu hình đáng tin, áp dụng biện pháp chống mix-up khi có nhiều AS.
- [ ] Callback không chứa third-party scripts/analytics khi URL có code/state; dùng `Referrer-Policy: no-referrer` và `Cache-Control: no-store`.
- [ ] Sau callback, URL đích sạch; browser history và reverse proxy logs không giữ giá trị nhạy cảm ngoài chính sách.
- [ ] Confidential client giữ secret/token ở backend; SPA/public client không giả vờ có secret và có XSS/PKCE/storage policy.
- [ ] Cookie session có `Secure`, `HttpOnly` và `SameSite` phù hợp; không bỏ CSRF protections cho các form/endpoint state-changing.
- [ ] Nhiều tab, nhiều pod, session hết hạn, callback bị replay, mix-up và PKCE mismatch đều có integration test.
- [ ] Không ghi nguyên văn authorization code, access token, refresh token, ID Token, client secret, verifier hoặc full callback URL vào log/ticket.
- [ ] Sử dụng TLS, giám sát lỗi `invalid_grant`/`invalid_state`/`invalid_redirect_uri` và có quy trình xử lý rò dữ liệu.

**Câu hỏi tự kiểm tra**

1. Vì sao `state` và `code_verifier` không thể thay thế hoàn toàn cho nhau?
2. Khi callback có `code` đúng nhưng `state` không khớp session, Client nên xử lý ra sao?
3. Vì sao `code_challenge` được gửi tới AS nhưng `code_verifier` chỉ xuất hiện khi đổi code?
4. Redirect URI `https://portal.example.vn/callback` và `https://portal.example.vn/callback/` có tương đương khi so khớp không?
5. PKCE đã bật có cho phép đặt Google Analytics ngay trên callback khi URL còn có `code` không?
6. Nếu Client dùng nhiều issuer, vì sao phải lưu issuer được chọn cùng transaction?
7. `HttpSessionOAuth2AuthorizationRequestRepository` của Spring Security giữ dữ liệu phục vụ những bước nào? Điều gì xảy ra nếu session mất?
8. Tại sao một authorization code đã dùng không được đổi lại ngay cả khi cùng client gửi đúng verifier?

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code Grant, redirect endpoint, code lifetime và client authentication.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): code verifier, S256 challenge và token exchange.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): exact redirect URI, CSRF, mix-up, leak qua Referer/history và single-use code.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): biện pháp chống authorization server mix-up.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): redirect URI loopback và PKCE cho native client.
- [Spring Security — Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): OAuth2 Client, resolver, public client và PKCE.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization request repository và callback handling.
- [Spring Security — HttpSessionOAuth2AuthorizationRequestRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html).
- [Spring Security — OAuth2AuthorizationRequestCustomizers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html): `withPkce()`.
- [Spring Authorization Server — Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2AuthorizationService` và `ClientSettings`.
- [Spring Authorization Server — SPA with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): luồng authorization code cho public browser client.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): nonce và kiểm tra ID Token trong OIDC.
