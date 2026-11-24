# Authorization Code with PKCE

**Authorization Code with PKCE** là một trong những luồng OAuth 2.0 quan trọng nhất để ứng dụng xin **access token** gọi API theo sự ủy quyền; khi kết hợp **OpenID Connect (OIDC)**, luồng này còn phục vụ đăng nhập người dùng. Access token **không cần đi qua URL redirect**. Trong luồng này, Authorization Server (AS) cấp một **authorization code ngắn hạn, dùng một lần** cho client; client đổi code thành token tại **token endpoint**. **PKCE** (*Proof Key for Code Exchange*, đọc là “pixy”) bổ sung ràng buộc để người chỉ đánh cắp được authorization code **không thể tùy ý đổi code đó thành token** khi không sở hữu `code_verifier` phù hợp.

Bài học thuộc chương **OAuth2 flows** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là hiểu mô hình tin cậy, vòng đời phát hành–truyền–kiểm tra–hết hạn–thu hồi token, phân biệt JWT và opaque token, access/refresh/ID token, cùng việc kiểm tra issuer, audience, claims, scope và phòng chống đánh cắp/phát lại.

**Điểm chính:** PKCE **bảo vệ bước đổi authorization code**, nhưng **không phải client authentication**, **không thay kiểm tra `state`/issuer/redirect theo thiết kế**, **không tự bảo vệ token sau khi cấp**, và **không cấp thêm scope hoặc quyền truy cập tài nguyên**.

## 1. Authorization Code + PKCE giải quyết bài toán nào?

Trong OAuth 2.0 có ba bên thường xuyên trao đổi:

- **Client:** ứng dụng web, mobile, desktop, SPA hoặc backend muốn truy cập tài nguyên.
- **Authorization Server:** xác thực người dùng (khi cần), quyết định authorization grant, cấp authorization code, access token và có thể cấp refresh token.
- **Resource Server:** API nhận và kiểm tra access token trước khi cho phép truy cập dữ liệu.

**Resource owner** thường là người dùng cho các flow ủy quyền; **user agent** (trình duyệt hệ thống) chuyển người dùng đến trang đăng nhập/consent của AS. Không nên đồng nhất ứng dụng client với Resource Server hay cho rằng access token là bằng chứng đăng nhập dành cho mọi ứng dụng.

### Vì sao không trả access token ngay qua trình duyệt?

Các thiết kế cũ như **Implicit grant** có thể cấp access token qua front channel, ví dụ fragment trên URL callback. Token đi qua môi trường browser có thể gặp XSS, SDK bên thứ ba, extension, history, logging hoặc URL sharing.

Với **Authorization Code + PKCE**:

1. Browser chỉ được redirect trở lại với **authorization code** và thông tin liên kết giao dịch.
2. Client đổi code tại token endpoint qua HTTPS với `code_verifier`.
3. AS chỉ phát token nếu **code còn hợp lệ, đúng client/redirect và ràng buộc PKCE khớp**.
4. Client sử dụng access token ở Resource Server theo đúng audience/scope; refresh token, nếu có, chỉ dùng tại AS.

**Authorization code vẫn là credential nhạy cảm**. Code bị lộ có thể bị lợi dụng nếu attacker còn chiếm được verifier hoặc nếu flow có lỗi cấu hình. PKCE giảm nguy cơ **code interception**, không biến code thành dữ liệu công khai có thể ghi log tùy ý.

### Những thứ không giống nhau

| Hiện vật | Vai trò | Được gửi tới đâu? |
|---|---|---|
| `authorization code` | Kết quả authorization để đổi lấy token, ngắn hạn và dùng một lần | Client đưa tới **AS token endpoint** |
| `code_verifier` | Bí mật ngẫu nhiên cho **một giao dịch PKCE** | Client đưa tới **AS token endpoint**, không đặt trong authorization URL |
| `code_challenge` | Giá trị suy ra từ verifier để AS ràng buộc code | Gửi ở **authorization request** |
| `state` | Liên kết callback với authorization transaction; chống CSRF/login mix-up theo thiết kế | Đi và về qua authorization redirect, rồi được client kiểm tra |
| `nonce` OIDC | Liên kết ID token với authentication request khi sử dụng | Đưa trong OIDC request, sau đó kiểm tra ID token theo profile |
| **Access token** | Credential truy cập API theo scope/audience/thời hạn | Chỉ đến **Resource Server** được chỉ định |
| **Refresh token** | Credential xin token mới theo grant | Chỉ đến **AS token endpoint** |
| **ID token** | JWT OIDC về sự kiện xác thực người dùng dành cho client | **OIDC Client/Relying Party**, không dùng như access token API |

## 2. PKCE hoạt động thế nào?

PKCE gồm hai giá trị cốt lõi:

- **`code_verifier`:** chuỗi ngẫu nhiên entropy cao do client sinh cho **mỗi authorization transaction**. Theo RFC 7636, độ dài từ **43 đến 128 ký tự** thuộc tập ký tự không dành riêng (*unreserved*): chữ cái, chữ số, `-`, `.`, `_`, `~`.
- **`code_challenge`:** biến đổi công khai của verifier. Với phương thức **`S256`**, lấy SHA-256 của biểu diễn **ASCII** verifier, sau đó mã hóa Base64url **không padding**.

Công thức chính xác:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Ví dụ verifier có **32 byte ngẫu nhiên** mã hóa Base64url không padding sẽ dài **43 ký tự**, đủ mạnh cho PKCE khi nguồn sinh là CSPRNG. **Không dùng** `Math.random()`, timestamp, email, user ID, chuỗi cố định, số đếm hoặc `client_id` làm verifier.

### AS dùng challenge để ràng buộc code

~~~mermaid
flowchart LR
    C["Client sinh verifier ngẫu nhiên V"]
    H["S256: Base64url(SHA256(ASCII(V))) = C"]
    A["/authorize với code_challenge=C"]
    AS["AS lưu challenge gắn authorization code"]
    T["/token với code + code_verifier=V"]
    CHECK{"S256(V) khớp challenge của code?"}
    OK["Cấp token nếu grant và các kiểm tra khác hợp lệ"]
    NO["Từ chối invalid_grant"]

    C --> H
    H --> A
    A --> AS
    C -->|"Giữ V an toàn"| T
    AS --> CHECK
    T --> CHECK
    CHECK -->|"Có"| OK
    CHECK -->|"Không"| NO
~~~

`code_challenge` có thể đi qua browser vì **nó không cho phép dễ dàng suy ngược verifier entropy cao**. `code_verifier` phải được giữ trong context giao dịch của client cho đến khi đổi code thành công, sau đó xóa.

### RFC 7636 test vector

RFC 7636 cung cấp một ví dụ chuẩn để kiểm tra cách tính `S256`:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Đây là **test vector công khai**, **không** sử dụng giá trị này làm verifier trong ứng dụng thật. Với mọi giao dịch thực, cần tạo verifier mới từ nguồn ngẫu nhiên mật mã.

### Vì sao dùng S256 thay vì plain?

RFC 7636 có phương thức `plain`, trong đó challenge chính là verifier. Nếu attacker quan sát được authorization request hoặc log chứa challenge, dùng `plain` có thể làm mất lợi ích PKCE. **Ưu tiên `S256`**, và đối với hệ thống hiện đại nên cấu hình chỉ chấp nhận S256 cho client hỗ trợ; không im lặng hạ cấp sang `plain` khi request ban đầu đã dùng S256.

## 3. Sơ đồ luồng end-to-end

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as System browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server

    C->>C: Sinh code_verifier V, state S, challenge S256(V)
    C->>B: Mở authorization URL
    B->>AS: GET /authorize: client_id, state S, challenge, method=S256
    AS->>AS: Kiểm tra client, redirect_uri, scopes và request
    AS->>U: Xác thực / MFA / consent khi cần
    AS->>AS: Ràng buộc code với client, redirect, challenge, grant
    AS-->>B: 302 redirect_uri?code=CODE&state=S
    B-->>C: Callback nhận code + state
    C->>C: Kiểm tra state, issuer / transaction context
    C->>AS: POST /token: code + code_verifier V + client auth nếu cần
    AS->>AS: Xác minh code, client, redirect, S256(V), trạng thái grant
    alt Hợp lệ
        AS-->>C: Access token (+ refresh / ID token nếu phù hợp)
        C->>API: Authorization: Bearer access_token
        API->>API: Kiểm tra token, audience, scope và quyền tài nguyên
        API-->>C: Dữ liệu được phép
    else Sai PKCE / code / grant
        AS-->>C: OAuth error, không cấp token
    end
~~~

**Quan trọng về trình tự:** user authentication tại AS là một việc; **đổi code bằng PKCE** là một việc khác; **API authorization bằng access token** là việc thứ ba. PKCE không thay thế bất kỳ lớp nào còn lại.

## 4. Điều kiện trước khi bắt đầu authorization request

Một client cần có thông tin AS và client registration phù hợp:

| Metadata/điều kiện | Ví dụ | Yêu cầu bảo mật |
|---|---|---|
| Issuer | `https://auth.example.test` | Chỉ tin AS đã cấu hình; chống mix-up khi có nhiều AS |
| Authorization endpoint | `https://auth.example.test/authorize` | HTTPS, lấy từ cấu hình/metadata tin cậy |
| Token endpoint | `https://auth.example.test/token` | HTTPS; không gửi code/verifier sang endpoint do attacker chọn |
| Client ID | `orders-mobile` hoặc `orders-bff` | Chỉ là định danh, **không phải secret** |
| Redirect URI | `https://app.example.test/auth/callback` | Đã đăng ký, đối chiếu chính xác theo quy tắc giao thức |
| Grant type | `authorization_code` | AS cho phép client dùng grant này |
| PKCE | `S256` | AS hỗ trợ và thực thi challenge/verifier |
| Scope/resource | `openid profile orders:read` hoặc `orders:read` | AS xét quyền; cấp đúng scope/audience, không tin client tự cấp |
| Client authentication | `private_key_jwt`, `client_secret_basic`, mTLS hoặc `none` | Theo loại client và phương thức đăng ký |

### Public client và confidential client

- **Public client:** SPA, native mobile/desktop app phân phối tới thiết bị của người dùng. Không thể giữ một **client secret hardcoded** thực sự bí mật. Thường dùng `token_endpoint_auth_method=none` và **PKCE S256**, với các ràng buộc code/client/redirect.
- **Confidential client:** backend web/BFF hoặc service giữ được secret/private key đúng cách. Khi đổi code, thực hiện **client authentication đã đăng ký** **và PKCE** theo chính sách; không xem việc đã có secret là lý do bỏ PKCE.
- **Native app:** dùng browser ngoài ứng dụng/system browser theo RFC 8252, không nhập mật khẩu user vào WebView tự kiểm soát; tránh custom redirect scheme lỏng lẻo và cân nhắc claimed HTTPS redirects khi phù hợp.
- **SPA:** token endpoint phải hỗ trợ mô hình public client và chính sách CORS đúng; không đưa client secret vào JavaScript bundle. CORS không phải cơ chế authentication của OAuth và không thay PKCE.

### Redirect URI không phải chi tiết giao diện

Redirect URI phải được đăng ký và xác minh đúng. Nó quyết định app/endpoint nào nhận authorization code; nếu cấu hình wildcard hoặc open redirect thiếu an toàn, code có thể đi đến attacker.

**Không chấp nhận `redirect_uri` bất kỳ do client gửi** rồi cho rằng PKCE đủ bù lại. AS phải kiểm tra URI với registration theo quy tắc áp dụng; native loopback redirect có quy tắc đặc thù về port theo RFC 8252. Client cũng phải gắn code với **authorization transaction và issuer đúng** trước khi đổi.

## 5. Bước 1 — Client tạo verifier, challenge và state

Một authorization transaction tối thiểu cần:

1. Tạo **`code_verifier` ngẫu nhiên mới**, giữ ngắn hạn cùng transaction; tính `code_challenge=S256(code_verifier)`.
2. Tạo **`state` khó đoán**, gắn với phiên client, issuer, redirect URI, scope/resource và thời điểm khởi tạo; kiểm tra và tiêu thụ một lần khi callback trở về.
3. Với OIDC, tạo **`nonce`** khi flow/profile yêu cầu hoặc client lựa chọn sử dụng để ràng buộc ID token với authentication request.
4. Chọn `redirect_uri` đã đăng ký, `client_id`, scope và audience/resource nếu AS hỗ trợ resource indicators.
5. Lưu verifier **không đặt trên authorization URL** và không đưa vào log/analytics.

Ví dụ logic nội bộ:

~~~text
transaction = {
    state: random_cryptographic_value(),
    code_verifier: random_cryptographic_value_43_to_128_chars(),
    expected_issuer: "https://auth.example.test",
    redirect_uri: "https://app.example.test/auth/callback",
    created_at: current_time(),
    used: false
}

challenge = BASE64URL(SHA256(ASCII(transaction.code_verifier)))
~~~

Bản ghi này là **pseudocode**, không có nghĩa lưu nguyên đối tượng trong localStorage/cookie không mã hóa. Với BFF, ưu tiên lưu verifier trong session/transaction store server-side; với SPA public client cần bảo vệ state theo khả năng browser, giảm XSS và thời gian sống.

### Phải sinh verifier mới cho từng lần authorization

Không dùng một verifier cố định cho toàn bộ client, nhiều tài khoản, nhiều tab hoặc nhiều authorization attempt. Nếu client cho phép hai giao dịch song song, **state** phải chọn đúng **verifier** tương ứng, không giữ một biến toàn cục bị ghi đè. Sau khi callback xử lý xong hoặc hết thời hạn, xóa record để giảm khả năng dùng lại.

## 6. Bước 2 — Gửi authorization request qua browser

Giả sử app `orders-web` cần đăng nhập người dùng (OIDC) và đọc đơn hàng; client đã sinh state và challenge từ verifier của transaction.

Ví dụ URL đã percent-encode:

~~~http
GET /authorize?response_type=code&client_id=orders-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fauth%2Fcallback&scope=openid%20profile%20orders%3Aread&state=<RANDOM_STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256&nonce=<OIDC_NONCE> HTTP/1.1
Host: auth.example.test
~~~

Các tham số:

| Parameter | Ý nghĩa và điểm cần kiểm tra |
|---|---|
| `response_type=code` | AS trả **authorization code**, không trả access token trực tiếp qua redirect |
| `client_id` | Định danh client đã đăng ký, **không phải bằng chứng client authentication** |
| `redirect_uri` | Callback đã đăng ký và được AS kiểm tra |
| `scope` | Quyền **xin cấp**, không phải quyền đã được cấp; `openid` yêu cầu OIDC khi áp dụng |
| `state` | Liên kết response với request trước đó, chống CSRF/authorization response injection |
| `code_challenge` | Giá trị S256 suy ra từ verifier bí mật của client |
| `code_challenge_method=S256` | Thông báo phương thức PKCE để AS lưu và kiểm tra |
| `nonce` | Ràng buộc ID token với request OIDC khi có và được xử lý theo profile |
| `resource` (nếu hỗ trợ) | Chỉ định tài nguyên/audience mong muốn theo RFC 8707 |

**Không được có `code_verifier`, access token, refresh token hoặc client secret trong authorization URL.** Client cũng không được nhét token vào `state` hoặc `nonce` cho “tiện mang thông tin”.

### AS phải làm gì ở authorization endpoint?

AS kiểm tra client ID, redirect URI, response type, PKCE challenge syntax và method, requested scopes/resource, authorization context, user authentication/consent (nếu cần) và policy. Khi chấp thuận, AS tạo một code:

- **Ngắn hạn, dùng một lần**, entropy đủ và khó đoán.
- **Gắn với client ID, redirect URI áp dụng, grant/user context**.
- **Gắn với chính xác `code_challenge` và `code_challenge_method` của transaction**.
- Chỉ cấp scope/resource thực sự được chấp thuận, không tự tin mọi scope client đã xin.

Nếu client/profile yêu cầu PKCE, AS phải từ chối authorization request không có challenge hợp lệ, **không cấp một code “không cần PKCE”** cho cùng luồng.

## 7. Bước 3 — User authentication, consent và callback

Sau khi AS xác thực user và xét grant, browser được chuyển đến redirect URI; ví dụ:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/auth/callback?code=<ONE_TIME_CODE>&state=<RANDOM_STATE>
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Client nhận callback qua HTTPS và thực hiện các kiểm tra **trước khi tin kết quả**:

1. **Transaction tồn tại?** Có session/cookie/transaction phù hợp với `state` và không quá hạn?
2. **State khớp?** So khớp giá trị trả về với record đã lưu; tiêu thụ record đúng cách để tránh replay.
3. **Issuer/AS đúng?** Nếu dùng nhiều AS, ràng buộc authorization response với issuer dự kiến; có thể sử dụng `iss` theo RFC 9207 khi AS hỗ trợ, bên cạnh binding giao dịch.
4. **Response thành công hay lỗi?** Nếu callback có `error` thay vì `code`, không cố exchange token; xử lý OAuth error theo protocol mà không tiết lộ nội dung nhạy cảm.
5. **Code được đổi ở token endpoint nào?** Chỉ dùng endpoint của AS đã lưu trong transaction, không lấy URL từ query không đáng tin.
6. **Redirect URI nhất quán?** Dùng đúng giá trị đã đăng ký/gửi khi bắt đầu; không thay bằng một callback tùy ý theo header `Host` bị giả mạo.

**Không lấy `state` làm bằng chứng user đã xác thực**; đó là binding giữa các bước của client. AS xác thực người dùng, còn client sau này kiểm tra ID token OIDC nếu có.

### Làm sạch URL callback

Authorization code có thể nằm trong query và bị ghi vào browser history, proxy/CDN log hoặc HTTP `Referer` từ trang callback. Vì vậy:

- Với **backend/BFF**, xử lý callback ở server rồi trả **`303 See Other`** đến URL cố định, không chứa `code`/`state`/token.
- Với **SPA**, chạy xử lý callback tối giản và `history.replaceState` **sớm**, trước analytics/third-party code, nhưng phải giữ đủ thông tin trong memory/transaction context để SDK hoàn tất validation/exchange.
- Cấu hình **`Referrer-Policy: no-referrer`**, `Cache-Control: no-store` cho callback và error page; không tải tài nguyên bên thứ ba trên trang chưa sạch.
- Tránh log raw URL/query, `Authorization` header, code, verifier, token và secret trong app/proxy/APM.

**Cleanup không phải thu hồi.** Nếu code/token đã được sao chép, client/AS vẫn phải áp dụng one-time usage, expiration, binding và quy trình incident/revocation thích hợp.

## 8. Bước 4 — Đổi code tại token endpoint

Client gửi **HTTP POST** đến token endpoint bằng `application/x-www-form-urlencoded`, có **authorization code và code_verifier gốc**:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<ONE_TIME_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Fauth%2Fcallback&client_id=orders-web&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

Đây là mẫu **public client**, không chứa client secret. Với **confidential client**, token request còn phải thực hiện **client authentication theo phương thức đăng ký**, ví dụ HTTP Basic, `private_key_jwt` hoặc mTLS. Không gửi secret dưới dạng query và không coi việc gửi `client_id` là đã authenticate client.

### AS kiểm tra gì ở token endpoint?

| Kiểm tra | Điều kiện để phát hành |
|---|---|
| **Client/registration** | Request thuộc client hợp lệ và grant type `authorization_code` được phép |
| **Client authentication** | Confidential client đã xác thực bằng phương thức đăng ký; public client áp dụng policy tương ứng |
| **Code** | Do AS phát hành, chưa hết hạn, chưa dùng/revoked và đúng client |
| **Redirect URI** | Khớp với giá trị ràng buộc khi cấp code theo quy tắc OAuth |
| **PKCE** | Tính `S256(code_verifier)`; so với challenge được lưu **cho chính code đó** |
| **Downgrade protection** | Nếu code gắn challenge thì phải có verifier đúng; không fallback sang “không PKCE” |
| **Grant/user/policy** | Grant/consent vẫn được phép; user/client/tenant policy không cấm |
| **Scope và audience** | Token chỉ mang quyền và resource được cấp, không vượt authorization |
| **Chống replay** | Code được tiêu thụ **nguyên tử** và không thể đổi hai lần đồng thời |

**Thứ tự nội bộ có thể thay đổi để tránh rò thông tin qua lỗi**, nhưng tất cả điều kiện cần thiết phải được xác minh trước khi cấp token hợp lệ.

### PKCE mismatch thì sao?

Nếu attacker có code nhưng gửi verifier sai, AS phải từ chối, thường bằng OAuth error **`invalid_grant`** theo RFC 7636. Client không thử tạo verifier mới để “khôi phục” code — nó không thể tạo một verifier khác có cùng S256 challenge một cách khả thi. Hướng xử lý thường là **khởi tạo authorization transaction mới**, sau khi kiểm tra lỗi mạng/cấu hình/session.

## 9. Java 17: tạo code_verifier và S256 code_challenge

Đoạn Java chuẩn JDK sau **có thể chạy độc lập** để tính PKCE, không gọi AS và không lưu token. Nó sinh 32 byte từ `SecureRandom`, mã hóa Base64url không padding thành verifier 43 ký tự và tính SHA-256 + Base64url cho challenge.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceS256 {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder BASE64URL =
            Base64.getUrlEncoder().withoutPadding();

    private PkceS256() {}

    public static String newVerifier() {
        byte[] randomBytes = new byte[32]; // 256 bits
        RNG.nextBytes(randomBytes);
        return BASE64URL.encodeToString(randomBytes);
    }

    public static String challenge(String verifier) {
        if (verifier == null
                || verifier.length() < 43
                || verifier.length() > 128
                || !verifier.matches("[A-Za-z0-9._~-]+")) {
            throw new IllegalArgumentException(
                    "Invalid PKCE code_verifier syntax"
            );
        }

        try {
            MessageDigest sha256 =
                    MessageDigest.getInstance("SHA-256");
            byte[] digest = sha256.digest(
                    verifier.getBytes(StandardCharsets.US_ASCII)
            );
            return BASE64URL.encodeToString(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", e
            );
        }
    }

    public static void main(String[] args) {
        String verifier = newVerifier();
        String codeChallenge = challenge(verifier);

        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: " + codeChallenge.length());
        // Trong production: KHÔNG in raw verifier/challenge trong log.

        String rfcVerifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String expected =
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
        if (!expected.equals(challenge(rfcVerifier))) {
            throw new IllegalStateException(
                    "RFC 7636 S256 vector mismatch"
            );
        }

        System.out.println("RFC 7636 test vector: PASS");
    }
}
~~~

Kết quả kiểm tra độ dài dự kiến:

~~~text
Verifier length: 43
Challenge length: 43
RFC 7636 test vector: PASS
~~~

**Cảnh báo khi đưa vào ứng dụng thực:**

- Lưu verifier theo **authorization transaction**, liên kết với state, redirect URI, issuer và thời gian; **không in verifier** trong log.
- Chỉ dùng verifier **một lần**, xóa sau khi callback/đổi code hoặc transaction hết hạn.
- Không cần lấy SHA-256 của verifier để lưu thay verifier ở client — token endpoint đòi **verifier gốc**.
- Không dùng cùng verifier cho nhiều user/tab/flow. `SecureRandom` là CSPRNG phù hợp, không dựa trên đồng hồ hoặc chuỗi dự đoán được.
- Đoạn code chỉ tạo PKCE; **không** xác minh state, cấp token hoặc kiểm tra quyền Resource Server.

## 10. JavaScript trong SPA: Web Crypto API và transaction context

SPA cần tạo verifier/challenge bằng **Web Crypto API** thay vì `Math.random()`. Ví dụ chạy trong **secure context (HTTPS)**:

~~~javascript
function base64url(bytes) {
    let binary = "";
    for (const value of bytes) {
        binary += String.fromCharCode(value);
    }

    return btoa(binary)
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replace(/=+$/, "");
}

function newRandomToken() {
    const bytes = new Uint8Array(32); // 256 bits
    crypto.getRandomValues(bytes);
    return base64url(bytes);
}

async function newPkceTransaction() {
    const codeVerifier = newRandomToken();
    const state = newRandomToken();

    const digest = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(codeVerifier)
    );

    const codeChallenge = base64url(new Uint8Array(digest));

    return { state, codeVerifier, codeChallenge };
}

// Chỉ ví dụ thuật toán, không phải implementation OAuth SDK đầy đủ.
// Không log codeVerifier, state hay đưa verifier vào authorization URL.
newPkceTransaction().then(({ codeChallenge }) => {
    console.log("Challenge length:", codeChallenge.length); // 43
});
~~~

**Đoạn code trên chỉ minh họa cách sinh PKCE**, không tạo authorization request hoặc lưu transaction. Trong SPA thật, OAuth SDK được duy trì nên:

1. Ánh xạ `state` với verifier, issuer, redirect URI và deadline của từng giao dịch.
2. Bảo vệ verifier tạm thời qua vòng redirect. `sessionStorage` có thể được SDK dùng trong một tab nhưng **script chạy trong origin, kể cả khi bị XSS, có thể đọc được**; nó không phải kho bí mật tuyệt đối. Không persist access/refresh token vào `localStorage` chỉ vì PKCE đã bật.
3. Dùng state để xác định đúng verifier ở callback và xóa transaction khi hoàn tất.
4. Xử lý callback trước analytics; không đưa `code`, `state`, verifier vào telemetry.
5. Dùng CORS/token endpoint theo cấu hình AS cho SPA public client; không nhúng client secret.

Trong mô hình **BFF**, backend có thể giữ code_verifier server-side và token trong session/credential store bảo vệ, giảm khả năng JavaScript lấy access/refresh token. Cách chọn SPA thuần hay BFF phụ thuộc threat model và kiến trúc, nhưng **cả hai đều cần PKCE**.

## 11. Authorization Server: chống downgrade, code interception và replay

PKCE chỉ mạnh khi AS thực thi đúng. Một ví dụ pseudocode tại token endpoint:

~~~text
exchangeAuthorizationCode(request):
    require HTTPS and registered token endpoint
    parse form; reject malformed or duplicate security parameters

    client = identifyClientByRegistration(request)
    authenticateClientIfRequired(client)

    codeRecord = lookupAuthorizationCode(request.code)
    require codeRecord exists, unexpired, unused, correct issuer
    require codeRecord.client_id == client.id
    require redirect_uriMatchesOriginalBinding(
        request.redirect_uri, codeRecord.redirect_uri
    )

    if codeRecord.code_challenge_method == "S256":
        require syntacticallyValidVerifier(request.code_verifier)
        expected = BASE64URL(SHA256(ASCII(request.code_verifier)))
        require expected == codeRecord.code_challenge
    else:
        reject if current policy requires S256
        validate only explicitly permitted legacy methods

    require active grant and permitted scopes/audience
    atomically mark code consumed and commit issuance state
    issue access token (+ refresh / ID token only if allowed)
~~~

### Ba lỗi triển khai đặc biệt nguy hiểm

**Lỗi A — PKCE downgrade:** client gửi challenge khi authorization nhưng token endpoint cho đổi code **không cần verifier** nếu field `code_verifier` bị bỏ trống. Điều đó phá hỏng ràng buộc PKCE.

**Lỗi B — Challenge không gắn với từng code:** server lưu challenge theo client ID mà không theo authorization transaction. Hai tab hoặc hai user dùng cùng client có thể ghi đè nhau, dẫn tới từ chối sai hoặc bỏ qua kiểm tra.

**Lỗi C — Code replay/race:** hai request đồng thời cùng đổi một code. Nếu server chỉ đánh dấu “used” sau khi phát token mà không đồng bộ nguyên tử, code có thể bị đổi hai lần.

**Thêm hai điểm:** nếu server cho phép `alg=none` ở JWT khác, tự tải khóa từ URL attacker hoặc cấp scope/audience vượt grant, PKCE vẫn không sửa được. PKCE là một lớp chống **interception ở code exchange**, không phải một cơ chế thay thế validation và authorization.

## 12. Threat model: PKCE ngăn gì và không ngăn gì?

| Tấn công hoặc lỗi | PKCE S256 có giúp không? | Biện pháp còn cần |
|---|---|---|
| Attacker chỉ lấy được authorization code từ redirect | **Có**, nếu attacker không có verifier và AS kiểm tra đúng | Code một lần/hạn ngắn, client binding, redirect chính xác |
| App khác chặn redirect native/custom scheme | **Có**, chống đổi code đơn lẻ | External browser, redirect URI an toàn, PKCE, state |
| Authorization code bị ghi vào web/proxy log | **Giảm khả năng đổi code nếu verifier không lộ** | Redact query, no-referrer, redirect URL sạch |
| Attacker lấy được **cả code và verifier** | **Không** | Bảo vệ transaction storage/runtime, XSS, device security |
| Attacker có thể thực thi JS cùng origin (XSS) | **Không đủ** | CSP, chống XSS, giảm token trong browser, BFF khi phù hợp |
| CSRF/login response injection | **Không nên chỉ mặc định dựa vào PKCE** | State/transaction binding, issuer/mix-up protection, nonce khi cần |
| AS chấp nhận redirect URI attacker | **Không sửa được cấu hình yếu** | Strict redirect registration, chống open redirect |
| Client secret bị lộ | **Không** | Quản lý credential, rotate/revoke, client auth đúng |
| Bearer access token bị sao chép sau issuance | **Không** | TLS, token storage, TTL, revocation, DPoP/mTLS khi phù hợp |
| Refresh token bị lấy và replay | **Không** | Rotation hoặc sender constraint, token family/reuse detection |
| API dùng access token sai audience/scope | **Không** | Resource Server verify `iss`/`aud`/scope và object policy |
| User bị lừa consent quyền quá rộng | **Không** | AS consent/policy, least privilege, UX và giám sát |
| Authorization code được gửi tới AS sai (mix-up) | **Không tự ngăn** | Bind issuer/token endpoint với transaction, RFC 9207 nếu hỗ trợ |

**Không gọi PKCE là “mã hóa authorization code”.** Nó không mã hóa code, không ký authorization response, không xác thực user và không cung cấp tính bí mật cho access token. Nó là một **proof-of-possession ở bước đổi code**, chứng minh bên đổi code biết verifier khớp với challenge ban đầu.

## 13. `state`, `nonce` và kiểm tra issuer: ba lớp khác PKCE

### State — liên kết response với giao dịch

`state` nên là giá trị khó đoán, được lưu theo transaction và kiểm tra ở callback. Nó giúp client từ chối response không bắt nguồn từ flow mình khởi tạo, hỗ trợ chống CSRF/login CSRF và mapping verifier cho nhiều tab.

Một thiết kế có thể dùng PKCE để giảm một số nguy cơ CSRF khi có điều kiện được chuẩn bảo mật cho phép, nhưng **không nên suy diễn “có PKCE là bỏ state luôn an toàn”**. Với ứng dụng học tập và hệ thống nhiều AS, dùng state và transaction binding rõ ràng là cách thực hành dễ kiểm chứng.

### Nonce — ràng buộc ID token trong OIDC

`nonce` là cơ chế của **OpenID Connect**, không phải OAuth scope hay PKCE challenge. Client có thể đưa nonce vào authorization request theo OIDC flow/profile; khi nhận ID token, client kiểm tra claim `nonce` phù hợp nếu đã yêu cầu. Nó giúp chống replay/sai kết hợp ID token trong authentication transaction, **không thay scope/audience validation của access token**.

Với OIDC **Authorization Code Flow**, nonce **không phải lúc nào cũng bắt buộc theo cùng cách như các hybrid/implicit flow lịch sử**; việc áp dụng phải phù hợp profile và hợp đồng AS/client.

### Issuer và mix-up

Nếu client tích hợp nhiều AS, attacker có thể cố làm client đổi code ở **token endpoint không đúng issuer**. Client phải ghi issuer dự kiến trong transaction, so khớp authorization response (có thể dùng tham số `iss` RFC 9207 nếu AS hỗ trợ) và chỉ gọi token endpoint của issuer tin cậy tương ứng.

**Không lấy URL token endpoint từ một tham số callback do browser gửi**. Dù code_verifier đúng, gửi verifier sang AS attacker vẫn làm lộ dữ liệu transaction.

## 14. Access token, refresh token và ID token sau khi đổi code

Một token response OAuth điển hình (ví dụ minh họa, không chứa credential thật):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "<REFRESH_TOKEN_IF_GRANTED>",
  "scope": "orders:read"
}
~~~

Token response **không nhất thiết có refresh token**. Ví dụ trên chỉ minh họa token response OAuth 2.0 thông thường; nếu client thực hiện **OIDC Authorization Code Flow** với scope `openid`, token response thành công **phải có `id_token`** theo OIDC Core. Client phải dùng token đúng mục đích:

| Loại | Bên nhận | Kiểm tra/ứng dụng |
|---|---|---|
| **Access token** | Resource Server có audience tương ứng | API verify JWT (chữ ký, `iss`, `aud`, `exp`, scope) hoặc introspect opaque token, rồi check quyền dữ liệu |
| **Refresh token** | AS token endpoint | AS kiểm tra grant/client binding, rotation/revocation và phạm vi quyền xin lại |
| **ID token** | OIDC Client/Relying Party | Client verify issuer, audience là client ID, signature, time, nonce nếu yêu cầu và profile |
| **Authorization code** | AS token endpoint | Đổi **một lần** với PKCE, không dùng gọi API |

### JWT và opaque không làm thay đổi vai trò PKCE

PKCE xảy ra **trước khi token được cấp**, và không phụ thuộc access token cuối cùng là JWT hay opaque. Sau khi phát hành:

- **JWT access token** (JWS/JWE theo profile) được API xác minh mật mã và claims; Base64url decode payload **không** đủ tin cậy.
- **Opaque access token** thường cần introspection/trạng thái tin cậy từ AS; `active:true` chưa đủ nếu sai audience/scope.
- `token_type: Bearer` mô tả cách trình token, **không nói định dạng là JWT**.
- **Sender-constrained access token** như DPoP/mTLS có thể được AS hỗ trợ; Resource Server còn kiểm tra proof/key binding, ngoài JWT/introspection.

Với endpoint `GET /orders/123`, token có `scope=orders:read` vẫn cần chính sách **user/client/tenant sở hữu đơn hàng**. PKCE thành công không cấp quyền đọc mọi order.

## 15. Lưu token, refresh token rotation và logout

Luồng Code + PKCE có thể bảo vệ authorization code rất tốt nhưng vẫn không an toàn nếu client xử lý token sai sau đó.

### Chọn nơi lưu token theo mô hình client

- **BFF/confidential web client:** token ở backend/session store được bảo vệ; browser thường giữ **cookie phiên ứng dụng** có `Secure`/`HttpOnly`/`SameSite` phù hợp. BFF phải xử lý CSRF và session fixation.
- **SPA public client:** giảm tối đa token tồn tại lâu trong browser; cân nhắc token ngắn hạn trong memory, CSP, chống XSS và kiến trúc BFF nếu threat model cho phép. `localStorage` không bảo vệ bearer token khỏi script chạy cùng origin.
- **Native mobile:** dùng iOS Keychain hoặc Android Keystore-backed encryption cho refresh token nếu cần persist; có thể giữ access token ngắn hạn trong memory. Không nhúng client secret trong binary.
- **Desktop:** dùng secure storage do OS hỗ trợ và policy phù hợp; không ghi token vào plain config/log.

### Refresh và rotation

Nếu được cấp refresh token, client dùng `grant_type=refresh_token` tại AS token endpoint, không chạy lại PKCE cho mỗi access token refresh. **PKCE bảo vệ lần đổi authorization code**, còn refresh token phải được bảo vệ bằng **client/grant binding, rotation hoặc sender constraint** theo loại client và chính sách AS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: Authorization code + PKCE verifier
    AS-->>C: AT1 + RT1 (nếu được cấp)
    C->>RS: API request với AT1
    RS-->>C: 200 OK
    C->>AS: Refresh token RT1 tại token endpoint
    AS->>AS: Kiểm tra grant, client, RT1, rotation/policy
    AS-->>C: AT2 + RT2 nếu áp dụng rotation
    C->>C: Lưu RT2 an toàn, vô hiệu/không dùng lại RT1
    C->>RS: API request với AT2
~~~

Khi phát hiện **refresh token reuse**, AS có thể revoke token family/grant theo chính sách. Client phải tránh concurrent refresh không điều phối và xử lý crash giữa lúc AS rotation RT với lúc local storage được cập nhật.

### Logout có thu hồi access token ngay không?

Không mặc định. Xóa cookie/token local **không làm tất cả bản sao access token ngoài thiết bị mất hiệu lực**. AS có thể revoke refresh token/grant theo RFC 7009 hoặc cơ chế quản trị riêng. Với JWT được Resource Server xác minh offline, API có thể cần denylist/introspection/state hoặc chờ `exp` để từ chối token đã phát hành. Thiết kế phải nêu rõ độ trễ thu hồi chấp nhận được.

## 16. So sánh triển khai: SPA, native app và BFF

| Khía cạnh | SPA public client | Mobile/native public client | Web BFF confidential client |
|---|---|---|---|
| Authorization UI | Browser redirect | System/external browser | Browser được chuyển từ backend sang AS |
| Client secret bảo mật | **Không** trong JS | **Không** trong app binary | Có thể giữ ở backend |
| PKCE S256 | Có, mỗi transaction | Có, mỗi transaction | Có, cùng client authentication |
| Verifier giữa hai bước | OAuth SDK/transaction storage ngắn hạn, chống XSS | App secure transaction context | Server-side session/transaction store |
| Code redirect | URL của SPA | App Link/Universal Link hoặc redirect được hỗ trợ | Backend callback |
| Token endpoint | Public client, CORS/AS config phù hợp | Public client theo AS | Backend gửi token request với client auth |
| Access token sau issuance | Memory/token policy; cần chống XSS | Memory; secure storage khi phải persist | Backend, browser không cần nhìn thấy |
| Refresh token | Chỉ khi policy và cơ chế bảo vệ phù hợp | Secure storage và rotation/sender constraint | Kho backend bảo vệ và rotation |
| Rủi ro đặc trưng | XSS, third-party scripts, browser storage | Redirect interception, device compromise | Secret leakage, session/CSRF, BFF compromise |

**Không lấy client authentication của BFF làm lý do bỏ PKCE**. Ngược lại, **PKCE không biến public client thành confidential client**. Các lớp bảo vệ khác nhau, bổ trợ nhau.

## 17. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách chẩn đoán an toàn |
|---|---|---|
| `invalid_request` tại `/authorize` | Thiếu hoặc sai `code_challenge`/`code_challenge_method`, redirect URI không hợp lệ | Kiểm tra tham số **đã redact**, client registration, S256 và URL encoding |
| Callback `state` không khớp | Session/tab sai, transaction bị thay, CSRF hoặc browser storage bị dọn | Từ chối giao dịch, rà mapping state–verifier, không log raw state |
| `invalid_grant` tại `/token` | Code hết hạn/đã dùng, verifier không đúng, redirect/client binding sai | Đối chiếu transaction ID và lỗi có cấu trúc, không ghi code/verifier |
| Dùng một verifier cho mọi request | Verifier hardcoded/cached, không gắn state | Sinh CSPRNG mới cho từng flow |
| Token endpoint chấp nhận thiếu verifier | PKCE downgrade / server validation lỗi | AS phải gắn challenge với code và từ chối |
| SPA lỗi CORS tại token endpoint | AS chưa cấu hình public client/token endpoint | Điều chỉnh CORS/AS policy đúng nguồn; không đưa client secret vào JS |
| Token có scope khác requested | AS chỉ cấp phạm vi được chấp thuận | Dùng **granted scope**, không tự suy ra từ authorization URL |
| API trả `401 invalid_token` | Access token sai issuer/audience, hết hạn, sai profile hoặc bị revoke | Kiểm tra verifier AS/RS và token purpose, không refresh vô hạn |
| API trả `403 insufficient_scope` | Token hợp lệ nhưng thiếu scope cần thiết | Làm lại authorization phù hợp nếu cần thêm quyền, không bypass API |
| Logout xong JWT vẫn gọi được API | API xác minh offline, không biết revoke | Thiết kế chặn sớm hoặc token TTL ngắn theo threat model |
| Callback URL rò `code` vào logs | Raw URL/Referer bị thu, cleanup muộn | No-referrer, redirect sạch sớm, redaction CDN/APM |
| Đăng nhập nhầm tài khoản | Login CSRF, xử lý state/issuer/nonce sai | Kiểm tra state/context và OIDC ID token đúng profile |

### Phân loại HTTP 401 và 403

Resource Server nhận một access token **không hợp lệ** thường trả `401 Unauthorized` với `WWW-Authenticate` phù hợp cho Bearer. Token **hợp lệ nhưng thiếu scope** thường dẫn đến `403 Forbidden`, có thể kèm `insufficient_scope`. **PKCE mismatch** là lỗi tại **token endpoint**, không phải một mã phân quyền API.

Client cần xử lý riêng ba loại lỗi: authorization failure, token exchange failure và API authorization failure. Không dùng một “retry login vô hạn” cho tất cả.

## 18. Case study: mã code bị lấy cắp qua callback log

Ứng dụng `orders-mobile` dùng Authorization Code + PKCE S256 để xin `orders:read` từ AS `https://auth.example.test`, sau đó gọi Orders API.

### Dòng thời gian

| Thời điểm giả định | Sự kiện | Ý nghĩa |
|---|---|---|
| 10:00:00 | App tạo verifier **V**, challenge **C=S256(V)** và state **S** | V giữ trong transaction context; C đi qua browser |
| 10:00:01 | Browser mở `/authorize?...code_challenge=C&state=S` | AS sẽ ràng buộc C với code |
| 10:00:20 | User đăng nhập và đồng ý `orders:read` | AS cấp authorization code **K** ngắn hạn |
| 10:00:21 | Redirect callback chứa `code=K&state=S` | K có thể xuất hiện ở callback/log nếu cấu hình kém |
| 10:00:22 | Một hệ thống log không được phép ghi lại K | Attacker có K nhưng **không có V** |
| 10:00:23 | Attacker thử đổi K bằng verifier tự tạo `V2` | AS tính S256(V2) không khớp C → **từ chối** |
| 10:00:24 | Client hợp lệ đổi K bằng V đúng | AS cấp token **nếu** code chưa bị tiêu thụ và mọi ràng buộc khác hợp lệ |
| 10:00:25 | Client gọi Orders API bằng access token | API kiểm tra issuer/audience/scope/expiry và quyền trên object |

Trong tình huống này, PKCE giúp ngăn kẻ chỉ giữ K đổi code. Nhưng hai hạn chế cần nêu rõ:

1. Nếu attacker đã chiếm app/browser và đọc được **cả K lẫn V**, PKCE không còn bảo đảm chống attacker đó.
2. Nếu authorization response bị tráo hoặc code bị gửi sang AS khác, cần **state/issuer/transaction binding**, không chỉ so S256.

Sau sự cố log, nhóm vận hành cần **ngừng lưu code**, hạn chế quyền xem log, kiểm tra lịch sử truy cập, đổi code flow khi cần và áp dụng chính sách xử lý credential liên quan; **đừng kết luận “đã có PKCE nên không cần điều tra”**.

### Sáu câu hỏi tự kiểm tra

**Câu 1.** `code_challenge` có phải một bí mật client giữ kín không? **Không.** Nó được gửi trong authorization request; bí mật ngẫu nhiên là verifier.

**Câu 2.** Attacker chỉ có code K, không có V. Có thể đổi code ở token endpoint chuẩn PKCE S256 không? **Không**, nếu AS ràng buộc và kiểm tra PKCE đúng.

**Câu 3.** PKCE có thay thế `client_secret_basic` của confidential client không? **Không.** Client authentication và PKCE có mục đích khác nhau.

**Câu 4.** Đã dùng PKCE có thể bỏ kiểm tra `aud` và `scope` tại API không? **Không.** API vẫn phải xác minh access token và quyền tài nguyên.

**Câu 5.** Refresh token có cần gửi `code_verifier` ở mỗi lần refresh không? **Không theo Refresh Token grant thông thường.** Refresh dùng token/grant binding, rotation/sender constraint và policy riêng.

**Câu 6.** Authorization code nằm trong query callback có được gửi vào analytics/log vì “không phải access token” không? **Không.** Phải tránh lộ code và làm sạch URL sớm.

## 19. Ma trận kiểm thử bảo mật Code + PKCE

| Test | Đầu vào/hành động | Kết quả mong đợi |
|---|---|---|
| **T1 — S256 vector** | Verifier RFC 7636 và challenge tương ứng | Tính ra đúng `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM` |
| **T2 — Random verifier** | Sinh 32 byte CSPRNG mỗi transaction | Verifier 43 ký tự, khác nhau và có entropy đủ |
| **T3 — Wrong verifier** | Đổi code hợp lệ bằng verifier khác | AS từ chối, không cấp token |
| **T4 — Missing verifier** | Authorization dùng S256, token request thiếu verifier | AS từ chối, không fallback |
| **T5 — Code replay** | Dùng cùng authorization code hai lần | Chỉ một exchange thành công tối đa |
| **T6 — Concurrent exchange** | Hai token requests đồng thời với một code | Code tiêu thụ nguyên tử, không cấp hai bộ token |
| **T7 — Wrong client** | Client B cố đổi code của A | AS từ chối |
| **T8 — Redirect mismatch** | Dùng redirect URI khác với binding | AS từ chối |
| **T9 — Tampered state** | Callback trả state sai/mất | Client từ chối trước exchange |
| **T10 — AS mix-up** | Code issuer A bị xử lý tại endpoint B | Client từ chối; không gửi verifier sang B |
| **T11 — User denies consent** | Authorization response có `error=access_denied` | Client không token exchange, cleanup/error phù hợp |
| **T12 — Plain downgrade** | Yêu cầu method yếu/không hợp lệ khi policy chỉ S256 | AS từ chối |
| **T13 — Multi-tab** | Hai flow song song cùng client | Mỗi state chọn đúng verifier, không ghi đè |
| **T14 — Expired code** | Đổi code hết hạn | AS từ chối `invalid_grant` phù hợp |
| **T15 — Scope reduction** | Xin `read write`, AS chỉ cấp `read` | Client xử lý scope thực tế, không cho write |
| **T16 — Callback Referer** | Trang callback chứa code test canary và tải assets | Không rò raw code trong Referer/log/analytics theo policy |
| **T17 — Token validation** | Dùng access token sai audience/hết hạn | Resource Server từ chối |
| **T18 — ID token substitution** | Đưa ID token vào API như Bearer | API từ chối; kiểm tra token purpose/audience |
| **T19 — Refresh replay** | RT1 rotation thành RT2 rồi gửi lại RT1 | AS phát hiện reuse và xử lý family theo policy |
| **T20 — Lost device/token** | Revoke grant/refresh, thử token còn hạn | AS không refresh; API chặn theo SLA/cơ chế trạng thái |

**Chỉ sử dụng code/token giả hoặc môi trường staging được phép.** Không ghi raw token, PKCE verifier hoặc authorization code production vào test report, HAR, console, CI logs hay công cụ tìm kiếm.

## 20. Checklist triển khai Authorization Code with PKCE

1. **Dùng `response_type=code`**, tránh implicit flow trả access token qua authorization redirect trong thiết kế mới.
2. **Mỗi authorization transaction có verifier ngẫu nhiên mới** từ CSPRNG, 43–128 ký tự unreserved, ưu tiên 32 byte entropy.
3. **Tính challenge chuẩn S256:** Base64url **không padding** của SHA-256 trên ASCII verifier.
4. **Gửi `code_challenge` và `code_challenge_method=S256` ở `/authorize`**, **không gửi verifier qua front channel**.
5. **Lưu verifier an toàn, ngắn hạn và gắn đúng state/issuer/redirect/client**, hỗ trợ nhiều transaction song song.
6. **Kiểm tra `state` và issuer ở callback**, chống CSRF, login injection và AS mix-up; kiểm tra `nonce` khi OIDC flow/profile yêu cầu.
7. **Đăng ký và so khớp redirect URI đúng**, tránh wildcard/open redirect; native app dùng external user agent.
8. **Đổi code bằng POST tới token endpoint đã cấu hình**, qua TLS với verifier gốc và redirect URI theo binding.
9. **Thực hiện client authentication khi client là confidential**, không dùng client secret hardcoded trong public SPA/mobile.
10. **AS gắn challenge với authorization code**, kiểm tra S256 và từ chối thiếu/sai verifier; không hạ cấp sang plain/không PKCE.
11. **Code ngắn hạn, một lần và tiêu thụ nguyên tử**, ràng buộc đúng client/grant/redirect.
12. **Scope và audience do AS quyết định**, token chỉ cấp những quyền được phép; không tự tin requested scope đã được granted.
13. **Làm sạch callback URL và log**, `no-referrer`/`no-store`, BFF `303` hoặc SPA `history.replaceState` trước analytics.
14. **Không nhầm loại token:** access token cho API, ID token cho client OIDC, refresh token cho token endpoint.
15. **Bảo vệ token sau issuance:** storage phù hợp, TLS, TTL, rotation/reuse detection, sender constraint và revocation theo threat model.
16. **API vẫn phải authorize độc lập:** kiểm tra JWT/opaque token, issuer, audience, expiry, exact scope, tenant và object policy.
17. **Bắt lỗi rõ lớp:** `invalid_grant` ở exchange, `401 invalid_token`/`403 insufficient_scope` tại API, tránh retry vô hạn.
18. **Kiểm thử âm tính toàn chuỗi:** verifier sai/thiếu, code replay, multi-tab, wrong client, wrong redirect, CSRF/mix-up, URL leak và token misuse.

**Kết luận:** Authorization Code + PKCE S256 tạo một **ràng buộc giữa authorization request và token exchange**: người cầm code phải chứng minh biết verifier của chính transaction đó. Đây là lớp chống code interception quan trọng cho **public client** và có ích cho cả **confidential client**. Một hệ thống an toàn còn phải kiểm tra **state/issuer/redirect/client**, chỉ cấp **scope/audience** được phép, bảo vệ **access/refresh/ID token sau phát hành**, và kiểm tra quyền tại Resource Server — PKCE không thay thế những lớp bảo vệ này.

### Tài liệu chuẩn để tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code grant, client registration, token endpoint và response.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge`, S256 và test vector.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, redirect security và refresh token protection.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user agent, loopback và claimed HTTPS redirects.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): `iss` trong authorization response để giảm mix-up.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): phân biệt audience/resource khi xin quyền API.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình bearer token và lỗi tại API.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token/grant theo giao thức.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cấu trúc JWT access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, scope `openid`, `nonce` và OIDC authorization code flow.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): kiểm tra bảo mật ở client, AS và Resource Server.
