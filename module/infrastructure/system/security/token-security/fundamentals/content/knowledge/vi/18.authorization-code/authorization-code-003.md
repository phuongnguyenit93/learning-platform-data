# Response type code

Một client OAuth 2.0 mở trình duyệt đến authorization endpoint với tham số **`response_type=code`**. Sau khi người dùng xác thực và đồng ý (khi cần), authorization server (AS) điều hướng trình duyệt về địa chỉ callback kèm **authorization code**. Client dùng code đó, cùng những ràng buộc bắt buộc như **PKCE** và xác thực client tùy loại client, để nhận **access token tại token endpoint**.

Điểm mấu chốt: **`response_type=code` không yêu cầu AS trả access token trong redirect**. Code chỉ là credential **ngắn hạn, dùng một lần, bị ràng buộc với một giao dịch ủy quyền**. Nó phải được đổi ở đúng AS và không được gửi vào API nghiệp vụ như Bearer token. Thiết kế này tách **front channel** (trình duyệt/redirect) khỏi bước trao đổi token có kiểm soát, nhưng không tự an toàn nếu thiếu PKCE, `state`, redirect URI chính xác và kiểm tra issuer.

Bài thuộc chương **Authorization Code** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung giải thích chi tiết `response_type=code` trong OAuth 2.0 và OpenID Connect (OIDC), sự khác biệt giữa code, JWT/opaque access token, refresh token, ID token, các biện pháp chống code interception/replay, cách triển khai với Spring Security và ma trận kiểm thử từ authorization request đến API resource server.

## 1. Ý nghĩa chính xác của `response_type=code`

`response_type` là tham số trong **authorization request** gửi tới authorization endpoint. Giá trị `code` chọn **Authorization Code response type**, theo đó kết quả thành công tại redirect callback chứa **authorization code**, thay vì trực tiếp phát access token trong URL của trình duyệt.

Ví dụ khái niệm:

```text
Client:
  response_type = code

Authorization Server:
  1. Xác định client, redirect URI và yêu cầu cấp quyền.
  2. Thực hiện authentication/consent theo chính sách.
  3. Phát authorization code ngắn hạn, dùng một lần.
  4. Redirect về callback hợp lệ với code và state.
  5. Chờ client đổi code tại token endpoint.

Client:
  1. Kiểm tra callback, state, issuer và transaction.
  2. Đổi code cùng code_verifier và xác thực client nếu cần.
  3. Nhận access token; ID token/refresh token nếu có và phù hợp.
  4. Dùng access token đúng audience/scope để gọi API.
```

**Không nhầm ba tham số có tên gần nhau:**

| Thuộc tính | Gửi ở đâu? | Chức năng |
|---|---|---|
| `response_type=code` | Authorization endpoint | Chọn **kết quả front-channel** là authorization code. |
| `grant_type=authorization_code` | Token endpoint | Cho biết client đang đổi **authorization code lấy token**. |
| `code_challenge_method=S256` | Authorization endpoint | Chọn phương thức PKCE dùng để ràng buộc code với `code_verifier`. |

Một lỗi rất phổ biến là gửi `grant_type=authorization_code` tới authorization endpoint, hoặc gửi `response_type=code` tới token endpoint và mong AS hiểu. Mỗi tham số thuộc một bước riêng.

## 2. Các vai trò trong luồng Authorization Code

Trong OAuth 2.0, cần phân biệt:

- **Resource owner:** người dùng/chủ thể có quyền trên dữ liệu, tham gia authorization theo grant/chính sách.
- **Client:** ứng dụng xin quyền truy cập và nhận code/tokens, ví dụ `orders-web`, một SPA hoặc mobile app.
- **Authorization server (AS):** xác thực theo chính sách, xử lý consent/grant, phát code và tokens.
- **Resource server (RS):** API nhận access token, xác minh issuer, audience, thời hạn, scope và quyền nghiệp vụ.

Với OIDC, AS hỗ trợ OIDC được gọi là **OpenID Provider (OP)**; client dùng thông tin đăng nhập được gọi là **Relying Party (RP)**. OIDC bổ sung **ID token** để xác nhận authentication cho client. Dù sử dụng OIDC, business API vẫn cần **access token** phù hợp.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser / user-agent
    participant C as OAuth Client
    participant AS as Authorization Server / OP
    participant RS as Orders Resource Server
    U->>C: Bắt đầu đăng nhập / xin quyền
    C->>C: Sinh state, PKCE verifier/challenge
    C-->>B: Redirect tới authorization endpoint
    B->>AS: GET authorize?response_type=code&...
    AS->>U: Authentication / consent khi cần
    AS-->>B: 302 tới redirect_uri?code=...&state=...
    B->>C: Callback kèm authorization code
    C->>C: Kiểm tra state, issuer và transaction
    C->>AS: POST token, grant_type=authorization_code
    Note over C,AS: code + code_verifier + xác thực client nếu áp dụng
    AS-->>C: Access token; ID/refresh token khi phù hợp
    C->>RS: Bearer access token đúng audience
    RS->>RS: Token validation + authorization tài nguyên
    RS-->>C: Dữ liệu được phép hoặc từ chối
```

Trong **BFF/confidential web application**, client logic và việc đổi code thường nằm ở **backend**. Trong **SPA** hoặc **mobile public client**, ứng dụng có thể tự thực hiện token exchange với PKCE theo chính sách AS và khả năng nền tảng. Sơ đồ minh họa trách nhiệm logic, không buộc mọi thành phần phải chạy trên một máy.

## 3. Authorization request đầy đủ với `response_type=code`

Giả sử một web client:

| Cấu hình | Giá trị minh họa |
|---|---|
| Issuer tin cậy | `https://id.example.test` |
| Authorization endpoint | `https://id.example.test/oauth2/authorize` |
| Token endpoint | `https://id.example.test/oauth2/token` |
| Client ID | `orders-web` |
| Redirect URI đã đăng ký | `https://app.example.test/login/oauth2/callback` |
| Scope cần thiết | `openid orders.read` |
| Resource/API | `orders-api`, nếu AS dùng resource indicator hoặc audience tương ứng |

Yêu cầu đã rút gọn bằng cách xuống dòng để đọc, **không phải URL copy chạy nguyên văn**:

```http
GET /oauth2/authorize?
  response_type=code&
  client_id=orders-web&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcallback&
  scope=openid%20orders.read&
  state=RANDOM_STATE_FOR_THIS_TRANSACTION&
  code_challenge=BASE64URL_SHA256_CODE_VERIFIER&
  code_challenge_method=S256
HTTP/1.1
Host: id.example.test
```

Trong HTTP thực tế, query phải nằm trên **một request target hợp lệ**, được URL-encode chính xác. Các chuỗi `RANDOM_STATE_FOR_THIS_TRANSACTION` và `BASE64URL_SHA256_CODE_VERIFIER` là **placeholder**, không phải giá trị đủ entropy hay thử nghiệm có thể dùng ngay.

### Phân tích tham số

| Tham số | Mục đích | Quy tắc bảo mật |
|---|---|---|
| `response_type=code` | Chọn code flow. | Authorization response thành công trả code, không trả access token trong URL. |
| `client_id` | Nhận diện client đã đăng ký. | **Không phải secret**; AS xác minh client/redirect/grant theo đăng ký. |
| `redirect_uri` | Callback để gửi kết quả authorization. | Phải khớp một URI hợp lệ đã đăng ký; AS và client kiểm soát open redirect. |
| `scope` | Yêu cầu phạm vi truy cập. | AS quyết định **scope thực tế được cấp**; không lấy scope yêu cầu làm quyền đã có. |
| `state` | Ràng buộc response với một authorization transaction của client. | Khó đoán, đủ entropy, chống CSRF/login injection; verify một lần. |
| `code_challenge` | Cam kết PKCE đối với verifier bí mật tạm thời. | Dẫn xuất từ verifier mới của **từng transaction**. |
| `code_challenge_method=S256` | Sử dụng SHA-256 + Base64URL no padding. | Không downgrade sang `plain` khi không có lý do tương thích và chính sách rõ. |

Trong **OIDC**, `scope` phải chứa `openid` để yêu cầu authentication theo OIDC. Có thể thêm `nonce` khi thiết kế yêu cầu, đặc biệt để bảo vệ ràng buộc kết quả xác thực; nếu gửi `nonce`, client phải kiểm tra `nonce` trong ID token theo quy tắc OIDC.

Nếu AS hỗ trợ **Resource Indicators** (RFC 8707), client có thể gửi tham số `resource` để chỉ rõ API dự kiến nhận access token. Tuy nhiên, đừng giả định chuỗi `resource` tự động trở thành `aud` mà không có hợp đồng AS–RS.

## 4. Vì sao `response_type=code` không trả access token qua redirect?

**Front channel** gồm browser, authorization redirect và callback URI: URL có thể xuất hiện trong lịch sử truy cập, debugging, reverse proxy logs hoặc bị ảnh hưởng bởi open redirect/referrer. **Back channel/token exchange** là trao đổi trực tiếp với token endpoint qua TLS theo cơ chế client phù hợp, tránh phải đưa access token vào redirect URL.

Với code flow:

```text
Front channel:
  Authorization Server -> browser -> Client callback
  Chứa: code (ngắn hạn, một lần) + state (+ iss nếu hỗ trợ).

Token exchange:
  OAuth Client -> Authorization Server token endpoint
  Chứa: code + PKCE verifier + client authentication nếu áp dụng.
  Trả: access token, và các token khác nếu được chính sách cấp.
```

Code vẫn là **credential nhạy cảm**: nếu lộ trước khi được đổi, nó có thể bị tấn công, đặc biệt khi PKCE/redirect binding bị thiết kế sai. Nhưng việc dùng code một lần, thời hạn ngắn, PKCE và ràng buộc client làm giảm giá trị của bản sao code trên front channel.

**Không gửi authorization code tới resource server**:

```http
# Sai: authorization code không phải Bearer access token.
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer AUTHORIZATION_CODE_PLACEHOLDER
```

Resource server chỉ nhận **access token đúng profile, audience và scope**. Nó không “đổi code” thay client nếu không có giao thức và vai trò được ủy quyền riêng.

## 5. Authorization response thành công: code, state và issuer

Sau khi AS hoàn tất luồng và cấp authorization code, một response thành công điển hình:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/callback?code=CODE_ONCE_EXAMPLE&state=STATE_ORIGINAL_EXAMPLE
Cache-Control: no-store
```

Client cần kiểm tra callback đã đến **đúng redirect URI**, `state` khớp transaction đang chờ, chưa hết hạn và chưa được xử lý trước đó. Nếu AS hỗ trợ **OAuth 2.0 Authorization Server Issuer Identification** (RFC 9207), response có thể có thêm `iss` để ràng buộc nguồn:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/callback?code=CODE_ONCE_EXAMPLE&state=STATE_ORIGINAL_EXAMPLE&iss=https%3A%2F%2Fid.example.test
```

Client phải đối chiếu issuer trong response với AS đã chọn cho transaction theo hồ sơ áp dụng. Đối với **multi-AS client**, chống authorization server mix-up đặc biệt quan trọng: không dùng một code của issuer A để gọi token endpoint B.

### Code thành công không phải bằng chứng đăng nhập hoàn tất

Khi nhận callback chứa code, client mới chỉ có **kết quả authorization bước đầu**. Client chưa nên thiết lập phiên authenticated cho người dùng dựa vào chuỗi code chưa được đổi. Cần:

1. Kiểm tra `state` và transaction liên quan.
2. Kiểm tra issuer và callback/redirect constraints.
3. Đổi code với `code_verifier` đúng.
4. Kiểm tra token response; với OIDC, xác minh ID token theo profile.
5. Thiết lập session/principal sau khi xác minh cần thiết.
6. Chỉ sử dụng access token cho resource server dự kiến nhận.

Một ứng dụng chỉ thấy `code=...` rồi lấy user ID từ query callback để “đăng nhập” là **token/identity substitution vulnerability**.

## 6. Authorization error response và xử lý đúng

AS có thể từ chối ủy quyền, ví dụ người dùng từ chối consent:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/callback?error=access_denied&state=STATE_ORIGINAL_EXAMPLE
```

Những mã lỗi authorization thường gặp gồm `invalid_request`, `unauthorized_client`, `access_denied`, `unsupported_response_type`, `invalid_scope`, `server_error` và `temporarily_unavailable`.

Client cần:

- Kiểm tra `state` và issuer/binding cho **cả callback thành công lẫn callback lỗi** theo chính sách áp dụng.
- Không coi `error=...` là một code hoặc tự gửi token exchange.
- Không log code, state bí mật, access token hay dữ liệu người dùng không cần thiết trong URL callback.
- Hiển thị thông điệp chung, không tiết lộ client secret, signing keys hay cấu hình nội bộ.
- Hủy/tiêu thụ authorization transaction khi kết thúc, tránh callback trễ được áp dụng lần hai.

**AS không nên chuyển hướng tới một `redirect_uri` không hợp lệ hoặc không khớp đăng ký** chỉ để hiển thị lỗi. Với redirect URI không hợp lệ, AS phải xử lý lỗi theo chính sách mà không vô tình đưa thông tin nhạy cảm đến một attacker-controlled redirect.

## 7. PKCE: điều kiện bảo vệ code trước interception

**Proof Key for Code Exchange (PKCE, RFC 7636)** ràng buộc authorization code với một giá trị bí mật ngẫu nhiên do client tạo trước khi bắt đầu flow. Nó đặc biệt quan trọng với **public clients** như SPA/mobile, và theo thực hành bảo mật OAuth hiện đại nên được áp dụng cho cả các client phù hợp khác.

Cơ chế **S256**:

```text
code_verifier  = chuỗi ngẫu nhiên đủ entropy, theo syntax RFC 7636
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256

Authorization request:
  gửi code_challenge + method, KHÔNG gửi code_verifier.

Token request:
  gửi authorization code + code_verifier.

AS:
  lấy challenge đã liên kết với code
  tính lại challenge từ verifier
  chỉ đổi code nếu khớp và các ràng buộc khác đều hợp lệ.
```

**Điều kiện của `code_verifier`:** RFC 7636 quy định chuỗi dài từ **43 đến 128 ký tự**, thuộc tập ký tự unreserved `A-Z a-z 0-9 - . _ ~`. Một phương án phổ biến là 32 byte ngẫu nhiên mật mã, Base64URL không padding thành chuỗi 43 ký tự. Không dùng timestamp, email, `Math.random()` hoặc chuỗi chung cho mọi phiên làm verifier.

### Ví dụ Java tạo PKCE verifier/challenge

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL =
            Base64.getUrlEncoder().withoutPadding();

    public static String newVerifier() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return URL.encodeToString(bytes);
    }

    public static String challengeS256(String verifier) throws Exception {
        byte[] sha256 = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return URL.encodeToString(sha256);
    }

    public static void main(String[] args) throws Exception {
        String verifier = newVerifier();
        String challenge = challengeS256(verifier);
        // Lưu verifier an toàn trong authorization transaction.
        // Chỉ gửi challenge ra authorization endpoint.
        System.out.println("challenge=" + challenge);
    }
}
```

Ví dụ **không in verifier**, vì đó là bí mật tạm thời của giao dịch. Trong ứng dụng thật, lưu verifier được ràng buộc với session/transaction hoặc một kho an toàn của client cho đến token exchange; không giữ vô thời hạn hay nhúng vào URL.

### PKCE không thay `state` hoặc validation token

PKCE giúp người không giữ verifier **không đổi được code bị chặn**. Nhưng PKCE không tự giải quyết mọi vấn đề: XSS chạy trong chính client có thể truy cập transaction/verifier tùy kiến trúc; code đã đổi thành access token có thể bị lộ; token endpoint và RS vẫn cần bảo vệ issuer, audience, scope, thời gian và revocation.

Sử dụng `state` khó đoán, ràng buộc transaction để chống login CSRF/response injection, đặc biệt với client hỗ trợ nhiều authorization transactions. Khi OIDC có `nonce`, client phải kiểm tra ID token `nonce` theo yêu cầu. Với nhiều AS, xử lý issuer mix-up vẫn riêng biệt.

## 8. Authorization code phải bị ràng buộc và chỉ được dùng một lần

Authorization code **không đơn giản là một chuỗi tùy ý có thể đổi ở mọi token endpoint**. AS cần lưu/kiểm tra đủ ràng buộc.

| Ràng buộc | Tại sao cần? | Lỗi nếu bỏ qua |
|---|---|---|
| **Client ID** | Code được phát cho đúng client đã bắt đầu authorization. | Client khác có thể thử đổi code. |
| **Redirect URI** | Code gắn với redirect URI hợp lệ của transaction. | Code từ callback này bị đổi qua callback khác. |
| **PKCE challenge** | Chỉ bên giữ verifier tương ứng được đổi code. | Intercepted code có thể bị dùng. |
| **Issuer/AS** | Code thuộc AS đã phát hành. | Code bị gửi sai token endpoint, mix-up/rò rỉ. |
| **Resource owner/grant** | AS biết yêu cầu đã được xác thực/ủy quyền theo chính sách. | Code bị tách khỏi quyền người dùng. |
| **Scopes/resources đã cho phép** | Token mới không được vượt grant. | Leo thang scope/audience khi đổi code. |
| **Thời hạn** | Giảm cửa sổ code bị lộ có thể bị dùng. | Code dùng được quá lâu. |
| **Trạng thái một lần** | Code đã đổi không được phát tokens thêm lần nữa. | Replay/double issuance. |

Theo RFC 6749, authorization code **nên hết hạn nhanh**, với thời gian tối đa khuyến nghị **10 phút**. Ứng dụng thực tế thường chọn ngắn hơn phù hợp độ trễ và UX. Code **phải chỉ được sử dụng một lần**; khi code bị dùng lại, AS phải từ chối và có thể thu hồi token đã cấp trước đó từ code đó khi thích hợp.

### Vì sao cần nguyên tử ở phía AS?

Giả sử hai request cùng đổi một code tại thời điểm gần như đồng thời:

```text
Request A: read code=unused
Request B: read code=unused
Request A: issue token -> mark used
Request B: issue token -> mark used
```

Nếu AS không có transaction lock/CAS/unique state transition, **một code có thể phát nhiều token**. Cần **consume one-time atomically** trước hoặc cùng quá trình cấp tokens theo thiết kế nhất quán, xử lý retry/crash/replay và audit. Client cũng không nên gửi hai token requests đồng thời với cùng code.

## 9. Token exchange: `grant_type=authorization_code`

Sau khi client nhận code và kiểm tra callback, client gửi yêu cầu **HTTP POST tới token endpoint** của đúng issuer đã chọn.

Ví dụ confidential web client, dữ liệu xác thực Basic là **placeholder**:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

grant_type=authorization_code&
code=CODE_ONCE_EXAMPLE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcallback&
code_verifier=VERIFIER_MATCHING_ORIGINAL_CHALLENGE
```

Payload hiển thị thành nhiều dòng cho dễ đọc; khi gửi thực phải encode đúng `application/x-www-form-urlencoded`. Nếu authorization request có `redirect_uri`, token request phải cung cấp giá trị **giống hệt** theo quy định. Confidential client cần xác thực với AS bằng cơ chế đã đăng ký; PKCE **không thay thế** client authentication nếu AS yêu cầu.

Public client như SPA/native có thể gửi `client_id` trong body khi thích hợp và **không mang client secret cố định trong mã/browser/app package**. Dù không có client secret, AS vẫn phải đối chiếu `client_id`, code, redirect và PKCE.

### Token endpoint trả về gì?

Một response minh họa cho OIDC code flow:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read",
  "id_token": "SIGNED_ID_TOKEN_EXAMPLE"
}
```

**`id_token` chỉ có trong OIDC khi điều kiện OIDC được thỏa**, không phải phần bắt buộc của OAuth 2.0 authorization code flow thuần túy. `refresh_token` **có thể có hoặc không**, tùy loại client, grant, consent và chính sách AS; không nên mặc định luôn được cấp.

Với access token, AS có thể cấp JWT hoặc opaque token. `response_type=code` **không quy định định dạng access token**. Client không được tự mở rộng scope từ `orders.read` thành `orders.approve`; RS sẽ xác minh access token/metadata thực tế.

**Token response có chứa credential:** AS/client nên áp dụng `Cache-Control: no-store`, TLS, giới hạn logs, tránh lưu token qua URL/analytics. Đặc biệt với BFF, access/refresh token nên nằm ở backend và browser chỉ giữ session cookie đã bảo vệ.

## 10. Token endpoint errors và `invalid_grant`

Những tình huống khiến code exchange thất bại:

- Code sai, giả mạo, hết hạn hoặc **đã dùng một lần**.
- `code_verifier` không khớp `code_challenge` của authorization transaction.
- Code được phát cho **client_id khác** hoặc redirect URI khác.
- Client authentication sai đối với confidential client.
- Issuer/token endpoint bị chọn nhầm.
- Authorization grant không còn hợp lệ theo AS.

Ví dụ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_grant"}
```

Client **không nên retry vô hạn cùng một code** khi gặp `invalid_grant`; code có thể đã được tiêu thụ hoặc AS đang bảo vệ chống replay. Hướng xử lý thường là hủy authorization transaction cũ, thực hiện luồng authorization mới khi cần.

Nếu token endpoint timeout đúng lúc trao đổi code, client có thể không biết AS **đã dùng code và phát token** hay chưa. Không mặc định tiếp tục gọi cùng code nhiều lần cho đến khi thành công; thiết kế retry cần cân nhắc code one-time, trạng thái phía client và UX reauthorization.

Lỗi `invalid_client` thuộc nhóm xác thực client, khác lỗi `invalid_grant`. Thông báo/log cần có mã lỗi và correlation ID nhưng **không ghi raw code, verifier hoặc tokens**.

## 11. Browser/BFF, SPA và mobile xử lý `response_type=code` khác nhau

Cùng một giá trị `response_type=code` có thể phục vụ những loại client với ranh giới tin cậy rất khác nhau.

| Loại client | Nơi giữ `code_verifier` | Nơi đổi code | Bảo vệ chính |
|---|---|---|---|
| **Confidential web app/BFF** | Backend session hoặc authorization request repository bảo vệ. | Backend gọi token endpoint. | Client authentication, PKCE, state/session binding, cookie/CSRF. |
| **SPA public client** | Trong runtime browser/transaction storage phù hợp. | Browser gọi token endpoint khi AS hỗ trợ CORS/flow. | PKCE S256, state, chống XSS, cẩn thận token storage. |
| **Mobile native public client** | Token manager/transaction state của app. | App gọi token endpoint qua TLS. | PKCE, external user-agent, redirect URI/claimed HTTPS, Keychain/Keystore. |
| **Desktop native** | App storage tạm cho transaction. | App gọi token endpoint. | PKCE, browser system, loopback/redirect theo RFC 8252. |

### BFF: browser không cần giữ OAuth tokens

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant APP as Backend-for-Frontend
    participant AS as Authorization Server
    participant API as Orders API
    B->>APP: GET /login
    APP->>APP: Sinh state + verifier trong server session
    APP-->>B: Redirect authorize?response_type=code&challenge=...
    B->>AS: Authorization request qua browser
    AS-->>B: Redirect callback với code + state
    B->>APP: GET /login/callback?code=...&state=...
    APP->>APP: Verify state/issuer/transaction
    APP->>AS: POST token với code + verifier + client authentication
    AS-->>APP: Access token + ID/refresh token nếu cấp
    APP-->>B: Session cookie HttpOnly/Secure và redirect sạch
    B->>APP: Request dữ liệu với cookie phiên
    APP->>API: Bearer access token cho API
    API-->>APP: Dữ liệu trong phạm vi quyền
```

Browser cookie phải được cấu hình đúng `HttpOnly`, `Secure`, `SameSite`, `Domain`/`Path`, session fixation và CSRF defense. BFF **giảm việc đưa refresh token vào JavaScript** nhưng không tự loại bỏ XSS/CSRF hoặc nguy cơ chiếm cookie phiên.

### SPA: PKCE không biến browser thành confidential client

SPA chạy trong JavaScript không bảo vệ được secret cố định trước người kiểm soát browser/app. Không nhúng `client_secret` vào bundle rồi coi đó là bảo vệ client. Nếu AS cấp refresh token cho public client, cần **rotation hoặc sender constraint** theo OAuth security best practice, cùng chính sách lưu/thu hồi phù hợp. Cân nhắc BFF khi ứng dụng xử lý dữ liệu nhạy cảm.

Một authorization code đã được PKCE bảo vệ vẫn có thể bị khai thác nếu script độc hại kiểm soát runtime, hoặc ứng dụng lộ access token sau khi đổi code. PKCE **chống interception code**, không phải giải pháp toàn diện cho storage.

### Mobile: external user-agent thay embedded webview

Theo RFC 8252, mobile native apps nên mở đăng nhập bằng **external user-agent** như system browser/secure browser tab, dùng PKCE và redirect URI đã đăng ký. Embedded webview có thể khiến app quan sát/điều khiển trang đăng nhập và credential của AS.

Private-use URI schemes có nguy cơ bị app khác đăng ký tranh; claimed HTTPS app links/universal links có thể bảo đảm liên kết ứng dụng tốt hơn khi cấu hình đúng. Dù dùng loại redirect nào, PKCE, `state` và kiểm tra callback/issuer vẫn cần thiết. Không hardcode confidential client secret trong APK/IPA.

## 12. OIDC Authorization Code flow: ID token xuất hiện khi nào?

Trong **OIDC code flow**, client thường gửi:

```text
response_type=code
scope=openid profile
client_id=orders-web
state=<random-state>
code_challenge=<S256-challenge>
code_challenge_method=S256
nonce=<optional-nonce-according-to-profile>
```

**Authorization response trên callback chỉ chứa code và state (cùng issuer param nếu áp dụng)**. ID token **không được phát trong URL callback của code flow**; nó thường được trả ở **token endpoint** sau khi đổi code.

| Credential | Được gửi tới đâu? | Kiểm tra quan trọng |
|---|---|---|
| Authorization code | Token endpoint của đúng AS. | One-time, expiry, client, redirect URI, PKCE. |
| Access token | Resource server đúng `aud`. | Issuer, chữ ký/introspection, loại, `exp`, audience, scope và quyền dữ liệu. |
| ID token | OIDC client/RP. | Chữ ký OP, `iss`, `aud` chứa client ID, thời gian, `nonce`/`azp` khi áp dụng. |
| Refresh token | Token endpoint của AS. | Client/grant binding, expiry, rotation/reuse detection hoặc sender constraint. |

**Không dùng ID token làm access token.** Cả hai có thể do cùng AS/OP phát hành và cùng có `sub`, `exp`, nhưng audience/mục đích khác nhau. Code flow không đồng nghĩa “ID token đăng nhập xong thì API có quyền”; API phải nhận và xác minh access token riêng.

Nếu client gửi `nonce` trong authorization request, phải so sánh với claim `nonce` trong ID token theo quy tắc OIDC. `nonce` không phải replacement cho `state` và không phải authorization scope.

## 13. Scope, audience và resource sau khi đổi code

Giả sử client gửi authorization request có:

```text
scope=openid orders.read orders.approve
resource=https://api.example.test/orders
```

AS chỉ cho phép `orders.read` theo policy. Token response có thể ghi:

```json
{
  "access_token": "TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "scope": "orders.read",
  "expires_in": 600
}
```

Điều đó có nghĩa client phải dựa vào **scope đã được cấp thực tế**, không lấy scope từng yêu cầu để tính quyền. Khi gọi `POST /orders/42/approve`, resource server phải từ chối nếu access token thiếu `orders.approve`.

**Audience** giới hạn bên nhận. Ví dụ access token JWT đã ký có:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900
}
```

Đây là **payload minh họa**, không phải JWT đã ký. `payments-api` phải từ chối token này dù chữ ký đúng vì `aud` không dành cho Payments. `orders-api` phải kiểm tra scope và quyền owner/tenant sau khi token hợp lệ.

RFC 8707 định nghĩa tham số `resource` khi AS hỗ trợ resource indicators. Tùy hệ thống, AS có thể sử dụng định danh resource để chọn audience token; **đừng tự giả định `resource` luôn bằng `aud` dạng chuỗi** nếu chưa có hợp đồng. Những token dành cho nhiều API chỉ được chấp nhận theo chính sách multi-audience của từng resource server.

### Authorization code không mang quyền trực tiếp tại RS

Client không thể gửi code đến API rồi yêu cầu API suy scope hay role từ code. Quyền API đến từ **access token được AS cấp sau token exchange và đã được RS xác minh**, kết hợp chính sách nghiệp vụ của RS.

## 14. Các đe dọa đối với `response_type=code`

| Mối đe dọa | Cách lỗi xuất hiện | Biện pháp chính |
|---|---|---|
| **Code interception** | Browser URL, deep link hoặc proxy lộ code trước token exchange. | PKCE S256, one-time code, TTL ngắn, TLS, callback an toàn. |
| **Authorization code injection** | Attacker nhét code thuộc transaction khác vào callback. | `state`/session binding, issuer/redirect validation, PKCE và code binding. |
| **Login CSRF** | Trình duyệt bị ép nhận callback của session/identity khác. | `state` khó đoán, one-time, ràng buộc browser transaction, OIDC checks. |
| **Authorization server mix-up** | Client gửi code của AS A đến token endpoint AS B. | Ràng buộc issuer/transaction, RFC 9207 hoặc cơ chế mix-up defense thích hợp. |
| **Open redirect** | Callback hoặc redirect intermediates chuyển code đến domain attacker. | Exact registered redirect URIs, không dùng open-redirect endpoints. |
| **Code replay/race** | Hai token requests dùng cùng authorization code. | AS consume code nguyên tử một lần, client chỉ gửi một lần. |
| **PKCE downgrade** | Client dùng `plain` hoặc bỏ challenge khi policy cần S256. | Enforce S256, không tự fallback yếu đi. |
| **Client impersonation** | Public app nhúng secret tưởng là confidential. | Phân loại client đúng, PKCE, client authentication thực sự khi có thể. |
| **Referrer/log leakage** | Callback URL với code bị ghi vào logs/analytics/Referer. | Redaction, Referrer-Policy, no third-party trên callback, clean redirect. |
| **Token substitution** | ID token hoặc code được dùng như API access token. | Token type/profile và audience validation. |
| **Overprivileged scope** | AS cấp nhiều quyền hơn nhu cầu hoặc RS chỉ kiểm token valid. | Minimal scopes, resource indicators, RS authorization đúng. |
| **Refresh-token misuse** | Client lưu refresh token nguy hiểm sau code flow. | BFF khi phù hợp, rotation/sender constraint, revocation, bảo vệ storage. |

Một authorization code không tự chứng minh người dùng chính chủ đang điều khiển client. Nếu attacker kiểm soát cả client/runtime hoặc phiên browser, cần những lớp bảo vệ khác ngoài code/PKCE.

## 15. Callback URL, query, `response_mode` và tránh lộ code

Với `response_type=code`, authorization response thường dùng **query** trên redirect URI. Một số AS hỗ trợ **OAuth 2.0 Form Post Response Mode** để trả các tham số bằng một HTTP POST qua trình duyệt thay vì query.

| Phương án | Cách nhận code | Lợi điểm | Giới hạn |
|---|---|---|---|
| **Query (thông dụng)** | `GET /callback?code=...&state=...` | Dễ tích hợp với web backend và browser. | Code có thể nằm trong URL logs/history/referrer nếu cấu hình kém. |
| **`response_mode=form_post` khi AS hỗ trợ** | Browser POST form chứa `code`/`state` đến callback. | Giảm việc đặt code trong URL query. | Code vẫn qua front channel; cần TLS, kiểm tra state, CSRF policy và body redaction. |
| **Fragment** | Fragment `#...` ở browser. | Phù hợp các flow/response modes khác tùy chuẩn. | **Không phải lựa chọn mặc định của code flow**; tránh tự chuyển sang implicit flow/token-in-fragment. |

Khi dùng query callback, backend nên xử lý code nhanh chóng, kiểm tra transaction và sau đó **redirect đến URL sạch** không chứa `code`, `state` hoặc `error_description` nhạy cảm. Ví dụ:

```http
HTTP/1.1 303 See Other
Location: /app/orders
Cache-Control: no-store
Referrer-Policy: no-referrer
```

Các header/redirect là **biện pháp bổ sung**, không thay one-time code/PKCE. Trên trang callback, tránh tải third-party resources trước khi loại code khỏi URL; giới hạn logging của reverse proxy và server, không ghi toàn bộ URL query có code.

Nếu ứng dụng dùng `response_mode=form_post`, CSRF framework cần nhận diện đây là **OAuth callback hợp lệ với state/binding đúng**, không đơn giản tắt toàn bộ CSRF trên ứng dụng. Kiểm soát callback phải được thiết kế theo flow.

## 16. Spring Security OAuth2 Client với `response_type=code`

Một ứng dụng web backend Spring Boot có thể sử dụng Spring Security OAuth2 Client/OIDC login để triển khai authorization code flow; nên dùng **framework thay vì tự tạo token exchange/ID token validator**.

Ví dụ cấu hình provider và client (placeholder, không có secret thật):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-login:
            provider: orders-idp
            client-id: "ORDERS_WEB_CLIENT_ID_PLACEHOLDER"
            client-secret: "ORDERS_WEB_CLIENT_SECRET_FROM_SECRET_MANAGER"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,orders.read
        provider:
          orders-idp:
            issuer-uri: "https://id.example.test"
```

Ở hệ thống thật, đọc client ID/secret từ cấu hình bảo vệ; không commit secret vào repository. `issuer-uri` phải là **issuer đã tin cậy**, không phải giá trị client tự gửi. Framework dùng metadata của AS/OP để khám phá endpoint/JWKS theo khả năng, nhưng cần policy chống mix-up, callback redirect matching và secure storage phù hợp.

Cấu hình security chain minh họa:

```java
@Configuration
public class WebClientSecurity {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated()
        );

        http.oauth2Login(Customizer.withDefaults());
        http.oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
```

Đoạn mã bỏ `import` và các cấu hình cụ thể về redirect/session/cookie/CSRF. Spring Security có thể quản lý `state`/authorization transaction/đổi code/ID token validation theo flow, nhưng ứng dụng vẫn phải kiểm chứng **PKCE được bật như chính sách mong muốn**, ranh giới issuer/redirect, session fixation, bảo vệ authorized-client token store và scope được áp dụng khi gọi API.

### Bật PKCE theo cấu hình resolver

Với các phiên bản Spring Security có API tương ứng, có thể tùy biến `OAuth2AuthorizationRequestResolver` để thêm PKCE cho code flow:

```java
@Bean
OAuth2AuthorizationRequestResolver pkceRequestResolver(
        ClientRegistrationRepository registrations) {

    DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                    registrations, "/oauth2/authorization");

    resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

    return resolver;
}
```

Cần **gắn resolver này vào `oauth2Login().authorizationEndpoint()`** ở SecurityFilterChain của ứng dụng; chỉ khai báo bean như trên **không tự bảo đảm nó được dùng**. Đây là ví dụ cấu phần cho Spring Security 6.x, không phải mã production đầy đủ. Nên kiểm tra phiên bản thư viện, hành vi mặc định PKCE của loại client, các endpoint đã đăng ký và test thực tế rằng authorization request có `code_challenge_method=S256` và token exchange gửi verifier tương ứng.

Đối với ứng dụng BFF, refresh/access tokens nên ở backend. Không trả tokens vào HTML/template chỉ để browser có thể đọc; browser giữ session cookie được bảo vệ và backend gọi resource API với access token đúng audience/scope.

## 17. Authorization Code flow với public client và token storage

### SPA

Một SPA có thể mở authorization endpoint với `response_type=code`, giữ `state` và `code_verifier` theo transaction, rồi gọi token endpoint bằng `fetch` nếu AS hỗ trợ public client và CORS đúng. **CORS không tự làm flow an toàn**: vẫn cần PKCE, exact redirect, issuer binding và chống XSS.

Nếu AS phát refresh token cho SPA, theo OAuth 2.0 Security BCP, public client cần **refresh token rotation hoặc sender constraint** theo chính sách thích hợp. Đừng lưu refresh token lâu dài trong browser storage dễ truy cập bởi JavaScript mà không đánh giá nguy cơ XSS; cân nhắc BFF khi có thể.

### Native/mobile

Mobile dùng external user-agent và PKCE; sau token exchange, lưu refresh token trong **iOS Keychain** hoặc kho mã hóa sử dụng **Android Keystore** theo kiến trúc. Không nhúng client secret vào package. Khi logout, xóa token local, thu hồi refresh token/grant ở AS nếu được hỗ trợ và xử lý access token đã cấp chưa hết hạn theo cơ chế RS.

### Token storage không liên quan trực tiếp `response_type` nhưng ảnh hưởng an toàn

`response_type=code` quyết định cách AS trả **authorization response**. Nó **không** quy định nơi client lưu access token, có được refresh token hay không, hoặc RS dùng JWT hay opaque token. Các quyết định storage, rotation, revocation, TTL, audience và scope là những lớp tiếp theo của vòng đời token.

## 18. Resource server kiểm tra token sau code exchange

Sau khi token endpoint phát access token, client gọi Orders API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
```

Resource server phải xác minh:

1. **Issuer/trust anchor:** token do AS được phép cấp; không tải JWKS từ issuer/header tùy ý.
2. **Tính hợp lệ:** JWT chữ ký/thuật toán/key/type/claims hoặc opaque introspection `active` từ AS tin cậy.
3. **Thời hạn:** `exp`, `nbf` và chính sách đồng hồ; trạng thái revocation nếu hệ thống yêu cầu.
4. **Audience:** token dành cho `orders-api`, không phải chỉ cho `payments-api` hoặc OIDC client.
5. **Scope:** endpoint đọc yêu cầu `orders.read` theo hợp đồng; không dùng scope đã yêu cầu trong authorize request thay cho scope token.
6. **Quyền dữ liệu:** chủ thể có quyền với đơn hàng `42`, tenant phù hợp và điều kiện nghiệp vụ.

```mermaid
flowchart TD
    C[Authorization Code đã được đổi] --> AT[Access token]
    AT --> V{JWT/opaque validation hợp lệ?}
    V -- Không --> E[401 Unauthorized]
    V -- Có --> A{Audience đúng Resource Server?}
    A -- Không --> E
    A -- Có --> S{Scope đủ cho endpoint?}
    S -- Không --> F[403 Forbidden]
    S -- Có --> O{Owner / tenant / policy cho phép?}
    O -- Không --> F
    O -- Có --> OK[Thực thi thao tác]
```

**Với JWT tự chứa**, RS có thể không biết token bị revoke trước khi `exp` nếu thiếu denylist/introspection. **Với opaque token**, introspection có thể phát hiện `active=false` nhưng cache có thể trì hoãn. Dù dùng code flow trước đó, một bearer access token còn hiệu lực bị đánh cắp vẫn có thể bị phát lại trong audience/scope được cấp.

## 19. Lỗi và phản hồi HTTP cần phân biệt

| Giai đoạn | Tình huống | Xử lý điển hình |
|---|---|---|
| Authorization request | `response_type` không được AS hỗ trợ. | Authorization error `unsupported_response_type` khi redirect hợp lệ; AS không redirect tới URI không hợp lệ. |
| Authorization request | `redirect_uri` sai đăng ký. | Từ chối, không chuyển code/error tùy tiện đến URI đó. |
| Authorization request | Người dùng không cấp quyền. | Callback lỗi `access_denied` nếu redirect hợp lệ, kèm `state` khi có. |
| Callback | `state` sai hoặc thiếu so với transaction. | Hủy giao dịch, không đổi code. |
| Callback | `iss` không khớp AS đã chọn khi áp dụng. | Chặn mix-up, không gửi code tới token endpoint sai. |
| Token request | `code_verifier` sai, code hết hạn/đã dùng. | `invalid_grant` (thường HTTP 400). |
| Token request | Xác thực confidential client sai. | `invalid_client` theo quy tắc token endpoint. |
| Token request | Code thuộc client/redirect khác. | Từ chối exchange, thường `invalid_grant`. |
| Resource API | Access token sai issuer/audience/time/type hoặc chữ ký. | Thường HTTP `401 invalid_token`. |
| Resource API | Token hợp lệ nhưng thiếu scope. | Thường HTTP `403 insufficient_scope`. |
| Resource API | Token đủ scope nhưng không được xem bản ghi. | HTTP `403` hoặc `404` theo policy dữ liệu. |

Không đồng nhất `invalid_grant` tại token endpoint với `invalid_token` ở resource server. Chúng thuộc **những bước và đối tượng credential khác nhau**.

## 20. Ma trận kiểm thử `response_type=code`

Giả định AS `https://id.example.test`, client `orders-web`, redirect URI đã đăng ký, PKCE S256 và Orders API có audience `orders-api`.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| C01 | Authorization request có `response_type=code`, client/redirect/scope hợp lệ. | AS hoàn tất authentication/consent khi cần và trả code. |
| C02 | `response_type=token` trong hệ thống chỉ hỗ trợ code. | AS từ chối theo profile, không phát access token trực tiếp. |
| C03 | Thiếu `response_type` hoặc giá trị sai cú pháp. | Từ chối request. |
| C04 | `client_id` không có đăng ký hợp lệ. | Không phát code/token. |
| C05 | `redirect_uri` trỏ domain attacker hoặc open redirect. | Không redirect code đến URI đó. |
| C06 | Authorization response thiếu `state` trong khi client đã gửi state. | Client từ chối callback. |
| C07 | `state` khác transaction đang chờ. | Client từ chối, không đổi code. |
| C08 | Callback `state` được replay sau khi đã xử lý. | Không tạo phiên/token exchange mới. |
| C09 | Client multi-AS nhận `iss` khác AS đã chọn. | Chặn mix-up, không gửi code tới token endpoint khác. |
| C10 | `code_challenge_method=S256` hợp lệ và token request có đúng verifier. | Exchange thành công nếu các điều kiện khác đạt. |
| C11 | Token request dùng `code_verifier` sai. | AS trả `invalid_grant`. |
| C12 | Không gửi PKCE trong client/profile bắt buộc. | AS từ chối theo policy. |
| C13 | Client cố downgrade sang `plain` dù policy yêu cầu S256. | AS từ chối. |
| C14 | Code được dùng lại lần hai. | AS từ chối replay, không phát thêm token. |
| C15 | Hai token requests đồng thời cùng dùng một code. | Chỉ một lần consume có thể thành công; bảo đảm nguyên tử. |
| C16 | Code hết hạn trước exchange. | Từ chối `invalid_grant`. |
| C17 | Code của client A bị client B đổi. | Từ chối do client binding. |
| C18 | `redirect_uri` ở token request khác authorization transaction. | AS từ chối. |
| C19 | Confidential client gửi secret sai. | Từ chối xác thực client. |
| C20 | Public SPA/mobile nhúng một client secret vào bundle. | Test/đánh giá kiến trúc phát hiện sai phân loại client. |
| C21 | OIDC code flow: callback có code nhưng chưa token response. | Client không thiết lập authenticated session quá sớm. |
| C22 | ID token `aud` sai client ID hoặc chữ ký sai. | OIDC client từ chối sau token exchange. |
| C23 | Có `nonce` trong authorize request nhưng ID token nonce không khớp. | OIDC client từ chối. |
| C24 | AS cấp scope hẹp hơn scope client yêu cầu. | Client/RS dựa vào granted scope, không dựa vào request ban đầu. |
| C25 | Access JWT cho `payments-api` gửi đến `orders-api`. | RS từ chối vì sai audience. |
| C26 | Access token đúng audience nhưng thiếu `orders.approve`. | API approve từ chối `403`. |
| C27 | Token có scope đọc nhưng order thuộc tenant khác. | RS từ chối theo object-level authorization. |
| C28 | Client dùng authorization code thay bearer access token. | RS từ chối credential sai loại. |
| C29 | BFF nhận callback, URL code vẫn còn trong analytics/referrer. | Security test redaction/clean redirect thất bại. |
| C30 | Form-post response mode được AS hỗ trợ. | Client nhận POST callback, kiểm tra state/issuer và CSRF binding đúng. |
| C31 | Token endpoint timeout sau khi AS đã consume code. | Không retry vô hạn; xử lý outcome không chắc chắn và authorization mới. |
| C32 | Token response có refresh token cho public client. | Rotation/sender constraint và secure storage được kiểm thử. |
| C33 | Mobile dùng embedded webview thay external user-agent. | Phát hiện mẫu không phù hợp RFC 8252. |
| C34 | Logout/revoke sau code exchange nhưng access JWT chưa hết hạn. | Test thể hiện giới hạn revocation khi RS chỉ xác minh tự chứa. |
| C35 | Opaque access token introspection trả `active=false`. | RS từ chối dù code flow trước đó đã thành công. |
| C36 | Không có authorization trên route mới. | Default deny, không suy quyền chỉ vì user đã đăng nhập. |

### Phân tầng kiểm thử

- **Unit tests**: verifier/challenge PKCE, state transaction, exact redirect URI, issuer binding, parse callbacks.
- **Integration tests với AS thử nghiệm**: thực sự cấp authorization code, exchange qua token endpoint, code one-time, PKCE S256, client/redirect binding và token response.
- **Browser end-to-end tests**: redirect/query hoặc form post, session cookie, history/referrer/logs, login CSRF, nhiều tab và back-button.
- **Resource server integration tests**: JWT chữ ký/audience/scope/expiry, opaque introspection, quyền tenant/owner, revoke/cache.
- **Mobile tests**: external user-agent, deep/app links, state/issuer, Keychain/Keystore, resume sau background.

Một test dùng fake `Authentication` hoặc Spring Security Test `jwt()` có thể kiểm tra route authorization nhưng **không chứng minh AS đã xác minh PKCE hoặc resource server đã kiểm JWT signature thật**. Cần tách rõ các tầng test.

## 21. Audit mà không làm lộ code hoặc tokens

Những sự kiện có thể ghi:

| Event | Dữ liệu tối thiểu phù hợp |
|---|---|
| `AUTHORIZATION_STARTED` | Transaction reference, client ID, issuer dự kiến, redirect URI reference, timestamp. |
| `AUTHORIZATION_CALLBACK_RECEIVED` | Kết quả, issuer đã xác minh, state-match flag, request/trace ID. |
| `TOKEN_EXCHANGE_SUCCEEDED` | Client reference, grant reference, scope đã cấp, event time; **không ghi token**. |
| `TOKEN_EXCHANGE_REJECTED` | Mã `invalid_grant`/`invalid_client` và policy version. |
| `CODE_REPLAY_DETECTED` | Code digest/reference an toàn, client/grant context, outcome. |
| `RESOURCE_ACCESS_DENIED` | Verified principal, audience, required scope, reason code, resource reference. |

**Không ghi** authorization code nguyên bản, `code_verifier`, access token, refresh token, ID token, client secret, cookie phiên, header `Authorization` hay callback query đầy đủ. Với correlation cần dùng transaction ID hoặc HMAC/digest có quản lý khóa, không lấy credential làm log identifier.

Một `TOKEN_EXCHANGE_SUCCEEDED` **không chứng minh** request sau đó được RS cho phép; authorization cấp resource vẫn phải kiểm tra riêng.

## 22. Bài tập tình huống

### A. Callback có code nhưng state sai

Ứng dụng đã bắt đầu login transaction T1. Callback chứa code có vẻ hợp lệ nhưng `state` không bằng state đã lưu.

**Kết luận:** Từ chối callback, không gửi code tới token endpoint. Nếu vẫn đổi code, client có thể nhận nhầm response hoặc bị login CSRF/code injection.

### B. Code bị sao chép nhưng PKCE verifier không lộ

Kẻ tấn công đọc được code từ URL callback nhưng không có `code_verifier` tương ứng.

**Kết luận:** Với AS thực thi PKCE S256 đúng, attacker không thể đổi code chỉ với chuỗi code. Client vẫn phải ngăn rò rỉ code, bảo vệ verifier, giới hạn TTL và một lần sử dụng.

### C. Client gửi code tới token endpoint của issuer khác

Một client hỗ trợ hai nhà cung cấp đăng nhập; callback của issuer A bị gắn vào transaction issuer B.

**Kết luận:** Phải chặn bằng issuer/transaction binding và mix-up defense. Không thử gửi code sang nhiều token endpoints để tìm nơi “đổi được”.

### D. OIDC callback không có ID token

Sau `response_type=code`, callback chỉ chứa `code` và `state`. Lập trình viên báo lỗi vì không thấy `id_token` ở URL.

**Kết luận:** Đó là hành vi bình thường của OIDC Authorization Code flow. Client đổi code ở token endpoint, sau đó nhận và xác minh ID token nếu OIDC được yêu cầu/cấp hợp lệ.

### E. AS đã cấp access token nhưng API không cho phép

Token có `aud=orders-api`, `scope=orders.read`, nhưng client gọi API phê duyệt đơn hàng.

**Kết luận:** Code flow thành công không đồng nghĩa mọi quyền được cấp. Resource server cần `orders.approve` và kiểm tra nghiệp vụ, thường từ chối `403 insufficient_scope`.

### F. Code đã bị đổi nhưng browser retry callback

Browser reload callback cũ mang code đã được sử dụng. Client thử token exchange lần nữa và nhận `invalid_grant`.

**Kết luận:** Không retry code cũ hoặc coi đây là lý do bỏ code one-time. BFF nên chuyển người dùng sang URL sạch sau callback, quản lý transaction đã hoàn thành và nếu cần bắt đầu authorization mới.

### Tự kiểm tra

1. `response_type=code` và `grant_type=authorization_code` xuất hiện ở hai endpoint nào?
2. Tại sao response callback có code nhưng không có access token?
3. PKCE `code_challenge` và `code_verifier` được gửi ở bước nào?
4. Vì sao PKCE S256 không tự thay `state` và issuer binding?
5. Một authorization code phải được AS ràng buộc với những thông tin nào?
6. Vì sao code chỉ dùng một lần, kể cả khi hai request đồng thời?
7. OIDC ID token xuất hiện lúc nào trong pure code flow và ai kiểm tra nó?
8. Vì sao `scope` trong authorize request có thể khác scope của access token?
9. Client SPA và web BFF khác nhau ở nơi giữ verifier, token và client secret như thế nào?
10. `response_mode=form_post` giải quyết phần nào và không giải quyết phần nào?
11. Resource server phải kiểm tra audience/scope gì sau khi code đã được đổi?
12. Vì sao access token bị đánh cắp vẫn có thể được RS chấp nhận dù authorization code từng dùng PKCE đúng?

## 23. Ghi nhớ

- **`response_type=code` chọn Authorization Code response**, trong đó browser redirect mang code ngắn hạn chứ không trực tiếp mang access token.
- **Token exchange là bước khác**: `grant_type=authorization_code` ở token endpoint, kèm code, `code_verifier` và xác thực client khi áp dụng.
- **PKCE S256, state, redirect URI và issuer binding** là các lớp bảo vệ quan trọng chống code interception, login CSRF, code injection và AS mix-up.
- **Authorization code ràng buộc client/redirect/PKCE, hết hạn nhanh và chỉ dùng một lần**; không đưa code tới resource API như Bearer.
- **OIDC ID token được cấp tại token endpoint của code flow**, dành cho OIDC client; API nghiệp vụ dùng access token phù hợp.
- **Scope request không phải scope grant; resource/audience phải đúng API**. Resource server tiếp tục kiểm tra JWT/opaque token, `iss`, `aud`, `exp`, scope, tenant và owner.
- **BFF, SPA và mobile có cùng flow nhưng trust boundary khác nhau**: confidential client authentication ở backend; public client dùng PKCE không có secret bí mật cố định; mobile dùng external user-agent.
- **Không ghi code, verifier hoặc tokens vào logs/URL không cần thiết**; xử lý callback và chuyển sang URL sạch khi phù hợp.
- **Code flow không tự ngăn token bị đánh cắp hoặc phát lại sau khi cấp**; access-token lifetime, refresh rotation, revocation, sender constraint và bảo vệ storage vẫn quan trọng.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code grant, `response_type=code`, token exchange và mã lỗi.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): verifier, challenge, S256 và chống code interception.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, chống mix-up, redirect và bảo vệ token.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer trong authorization response và mix-up defense.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user-agent, native redirect và PKCE.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource identifier và audience.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): access token cho RS, `invalid_token`, `insufficient_scope`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims, token type, audience và JWT access token validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): trạng thái và thu hồi access/refresh token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC code flow, ID token, nonce, audience và validation.
- [OAuth 2.0 Form Post Response Mode](https://openid.net/specs/oauth-v2-form-post-response-mode-1_0.html): trả authorization response qua form POST.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) và [OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): tích hợp authorization code/OIDC client với Spring.
