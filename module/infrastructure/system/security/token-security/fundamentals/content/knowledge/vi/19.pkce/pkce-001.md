# Proof Key for Code Exchange

**Proof Key for Code Exchange (PKCE, đọc gần như “pixy”)** là cơ chế mở rộng của **OAuth 2.0 Authorization Code Flow**, được chuẩn hóa trong **RFC 7636**, nhằm làm cho **authorization code bị đánh cắp trở nên khó đổi lấy token hơn**. Thay vì chỉ đưa mã ủy quyền (`code`) đến token endpoint, client còn phải chứng minh rằng nó nắm giữ một giá trị bí mật ngẫu nhiên đã được cam kết khi bắt đầu luồng: **`code_verifier`**.

Ví dụ, một mobile app mở trình duyệt hệ thống để người dùng đăng nhập. Authorization server trả code thông qua app redirect URI. Một ứng dụng khác có thể cố chặn hoặc chiếm code đó. Nếu authorization code không có thêm ràng buộc, attacker có thể thử đổi code lấy access token. Với PKCE **`S256`**, authorization server chỉ chấp nhận bên gửi đúng `code_verifier` tương ứng với `code_challenge` đã gắn vào code lúc phát hành.

Bài học này thuộc chương **PKCE**, chủ đề **“Proof Key for Code Exchange”**, trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung nối PKCE với mô hình tin cậy, vòng đời JWT/opaque access token và refresh token, OAuth 2.0/OpenID Connect (OIDC), issuer, audience, scope, lưu trữ an toàn, thu hồi và phòng chống code/token theft hoặc replay.

> **Điểm cốt lõi:** PKCE ràng buộc **authorization code với giao dịch của client đã khởi tạo flow**. PKCE **không phải** chữ ký JWT, không xác thực danh tính user, không thay scope/audience validation và không tự ràng buộc access token với thiết bị sau khi token đã phát hành.

## 1. PKCE giải quyết vấn đề gì?

Trong Authorization Code Flow, client lần lượt:

1. Chuyển user tới **authorization endpoint** của authorization server (AS).
2. User được xác thực và/hoặc cấp consent theo chính sách AS.
3. AS trả về một **authorization code ngắn hạn, dùng một lần** qua callback.
4. Client đổi code ở **token endpoint** để nhận access token (và các token khác khi profile cho phép).

Authorization response thường đi qua **front-channel**, tức trình duyệt và cơ chế redirect mà client không kiểm soát tuyệt đối. Code có thể bị lộ bởi app link/URI scheme interception, open redirect, log, lịch sử trình duyệt, extension, lỗi callback hoặc thiết bị bị xâm nhập.

**Mối đe dọa chính:** một attacker có code của flow do client hợp lệ khởi tạo, rồi cố gắng gửi code ấy đến token endpoint **trước** client hợp lệ.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp lệ
    participant AS as Authorization server
    participant X as Attacker
    C->>AS: Authorization request
    AS-->>C: Authorization code (front-channel)
    Note over X,C: Attacker lấy được bản sao code
    X->>AS: POST /token với code bị lấy
    AS-->>X: Nguy cơ trả access token nếu thiếu ràng buộc
~~~

Trong trường hợp **không có PKCE** hoặc cơ chế bảo vệ tương đương, token endpoint có thể chỉ dựa vào code, client registration, redirect URI và client authentication (nếu là confidential client). Với **public client** không giữ được client secret an toàn, bảo vệ chống code interception đặc biệt quan trọng.

### 1.1. Public client là gì?

| Loại client | Ví dụ | Vì sao PKCE hữu ích? |
| --- | --- | --- |
| **Public SPA** | Ứng dụng JavaScript trong browser | Không có client secret bí mật trong JS; cần ràng buộc code với lần khởi tạo |
| **Native mobile/desktop** | App iOS, Android, desktop | Redirect URI/app link có thể bị chặn, cấu hình sai hoặc bị lợi dụng |
| **Confidential web/BFF** | Java/Spring backend giữ credential | Client authentication vẫn cần; PKCE tạo lớp bảo vệ bổ sung trước code injection/interception |
| **Machine-to-machine client credentials** | Service xin token không qua browser/code | **Không phải** Authorization Code Flow; không có code để dùng PKCE |

**Khuyến nghị hiện đại:** dùng PKCE với **Authorization Code Flow** cho cả public và confidential clients khi được AS hỗ trợ, đặc biệt bắt buộc đối với các public clients theo chính sách/best practices áp dụng. PKCE **không làm một public client trở thành confidential client**.

## 2. Ba giá trị cần phân biệt

| Tên | Bên tạo | Xuất hiện ở đâu? | Tính chất |
| --- | --- | --- | --- |
| **`code_verifier`** | OAuth client trước khi redirect | Lưu tạm phía client; gửi ở **token request** | Chuỗi bí mật ngẫu nhiên, khó đoán |
| **`code_challenge`** | Client tính từ verifier | **Authorization request** | Cam kết về verifier; với `S256`, là Base64url(SHA-256(verifier)) |
| **`code_challenge_method`** | Client chọn phương thức AS hỗ trợ | **Authorization request** | Ví dụ **`S256`**; không phải thuật toán ký JWT |

Không nên nhầm:

- `code`: **authorization code** do AS cấp **sau** khi flow được cho phép.
- `state`: giá trị liên kết authorization response với transaction/phiên client.
- `nonce`: giá trị OIDC dùng ràng buộc **ID token** với authentication request.
- `client_secret`: credential dùng cho **confidential client authentication**; không phải `code_verifier`.
- `access_token`: credential dùng để gọi **resource server**, không phải proof PKCE.

### 2.1. Công thức S256

\[
\texttt{code\_challenge}
=\operatorname{BASE64URL\_NO\_PADDING}
  \left(\operatorname{SHA256}
  \left(\operatorname{ASCII}(\texttt{code\_verifier})\right)\right)
\]

**Giải thích:** client lấy chuỗi verifier theo bộ ký tự ASCII quy định, tính băm SHA-256 (32 byte), mã hóa Base64url và **bỏ dấu `=` padding**. Kết quả thường có **43 ký tự** cho digest SHA-256.

**`S256` không phải mã hóa hai chiều:** AS không cần giải mã challenge để lấy verifier; nó chỉ tính lại challenge từ verifier khi client đổi code và so sánh.

### 2.2. Test vector từ RFC 7636

Ví dụ công khai trong RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Đây là **test vector**, không phải verifier dùng trong production. Nếu code tạo ra challenge khác, thường do lỗi encode ASCII/UTF-8, Base64 chuẩn thay vì Base64url, padding `=`, newline ẩn hoặc hash sai nội dung.

## 3. PKCE hoạt động trong hai bước như thế nào?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth client
    participant B as Browser
    participant AS as Authorization server
    C->>C: Sinh verifier bằng CSPRNG
    C->>C: challenge = BASE64URL(SHA256(verifier))
    C->>B: Điều hướng tới authorization URL
    B->>AS: response_type=code + challenge + S256
    AS->>AS: Validate client, redirect_uri, consent
    AS->>AS: Lưu challenge/method gắn với code
    AS-->>B: Redirect callback?code=...&state=...
    B-->>C: Authorization code
    C->>C: Validate state/issuer và lấy verifier đã lưu
    C->>AS: POST token: code + code_verifier
    AS->>AS: Kiểm tra code chưa dùng, client, redirect
    AS->>AS: Tính lại challenge từ verifier và so sánh
    alt Mọi điều kiện hợp lệ
        AS-->>C: Access token (+ token theo profile)
    else Bất kỳ điều kiện nào sai
        AS-->>C: invalid_grant / lỗi phù hợp
    end
~~~

**Mối ràng buộc quan trọng:** AS phải lưu phương thức `S256` và `code_challenge` **cùng authorization code/giao dịch**. Khi đổi code, không được dùng challenge mới do caller gửi để thay thế challenge ban đầu.

### 3.1. Authorization request

Ví dụ query được ngắt dòng cho dễ đọc:

~~~http
GET /oauth2/authorize?response_type=code
  &client_id=orders-spa
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
  &scope=openid%20orders.read
  &state=<random-state>
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256 HTTP/1.1
Host: auth.example.com
~~~

Request thật nằm trên một dòng query và phải URL-encode đúng. `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state` là các tham số khác của authorization request; PKCE **chỉ bổ sung** challenge/method.

Trong mô hình production, **tự sinh verifier mới cho từng authorization transaction**. Không dùng lại verifier test ở trên hoặc một verifier chung cho mọi người dùng.

### 3.2. Authorization response

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/callback?code=<one-time-code>&state=<state>
Cache-Control: no-store
~~~

Trước khi đổi code, client phải:

- Kiểm tra `state` gắn với authorization request hiện hành; xem thêm **issuer mix-up defense** nếu hỗ trợ nhiều AS.
- Xác minh callback/redirect URI đúng transaction đã khởi tạo.
- Tìm lại **verifier của đúng transaction**, không lấy verifier mới hoặc verifier của tab khác.
- Giữ code ngắn hạn, không lưu vào log, analytics, URL của domain khác hoặc error report.

### 3.3. Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code
&client_id=orders-spa
&code=<one-time-code>
&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

Body trong ví dụ được xuống dòng **chỉ để trình bày**. Request thật phải encode đúng form. Với confidential client, client còn phải **xác thực chính nó** bằng phương pháp đã đăng ký; PKCE không thay thế điều đó.

AS tính:

~~~text
computed = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
expected = code.code_challenge

if computed != expected:
    reject token request
else:
    continue normal checks (client, redirect, expiry, one-time, policy)
~~~

**Chỉ sau khi các điều kiện bắt buộc đều đạt**, AS mới cấp token. `code_verifier` không phải tham số để client quyết định scope hay issuer.

## 4. Quy tắc sinh `code_verifier` đúng RFC 7636

RFC 7636 quy định cú pháp của verifier:

~~~abnf
code-verifier = 43*128unreserved
unreserved   = ALPHA / DIGIT / "-" / "." / "_" / "~"
~~~

Nghĩa là:

- Độ dài **43 đến 128 ký tự**.
- Chỉ dùng chữ cái ASCII, chữ số, dấu `-`, `.`, `_`, `~`.
- Sinh bằng **cryptographically secure random number generator (CSPRNG)** với entropy đủ lớn.
- Cách được khuyến nghị là sinh **32 byte ngẫu nhiên** (256 bit), rồi Base64url không padding, tạo chuỗi **43 ký tự**.

| Cách tạo | Đánh giá | Vì sao? |
| --- | --- | --- |
| 32 byte CSPRNG + Base64url không padding | **Tốt** | Đủ entropy, đúng cú pháp |
| 64 byte CSPRNG + Base64url không padding | Tốt | Khoảng 86 ký tự, trong giới hạn |
| `Math.random()` + timestamp | **Không an toàn** | Không bảo đảm entropy khó đoán |
| Username/email/session ID | **Không an toàn** | Có thể dự đoán hoặc liên kết người dùng |
| Chuỗi hard-code trong ứng dụng | **Không an toàn** | Dùng lại trên nhiều phiên, người khác có thể biết |
| Một verifier duy nhất cho mọi tab/user | **Không an toàn** | Mất ràng buộc từng authorization transaction |
| Verifier dài 20 ký tự | **Không hợp lệ** | Vi phạm cú pháp RFC 7636 |

**Không có yêu cầu tự “hash verifier trước khi lưu” như cách lưu mật khẩu** ở client. Verifier là bí mật ngắn hạn phải được giữ nguyên để gửi token endpoint. Nếu lưu trong backend/session store, cần bảo vệ truy cập và xóa sau khi hoàn tất/timeout.

## 5. Java 17: tạo verifier và challenge đúng chuẩn

Ví dụ Java dùng `SecureRandom`, `MessageDigest` và `Base64.getUrlEncoder().withoutPadding()`. Đây là đoạn code tự chứa cho mục đích minh họa PKCE generation, không phải thư viện OAuth đầy đủ:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceSupport {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder BASE64_URL =
        Base64.getUrlEncoder().withoutPadding();

    private PkceSupport() {}

    public static String generateVerifier() {
        byte[] random = new byte[32]; // 256-bit entropy
        RNG.nextBytes(random);
        return BASE64_URL.encodeToString(random); // 43 chars
    }

    public static String challengeS256(String verifier) {
        if (verifier == null
                || verifier.length() < 43
                || verifier.length() > 128
                || !verifier.matches("[A-Za-z0-9._~-]+")) {
            throw new IllegalArgumentException("Invalid PKCE verifier");
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
            return BASE64_URL.encodeToString(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public static void main(String[] args) {
        String verifier = generateVerifier();
        String challenge = challengeS256(verifier);

        // Chỉ hiển thị thông tin KHÔNG nhạy cảm khi debug.
        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: " + challenge.length());
    }
}
~~~

**Không in giá trị thực của `verifier` vào log** trong ứng dụng thật. Việc in độ dài trong demo giúp xác minh cú pháp mà không rò credential. Trong luồng thực, client liên kết verifier với `state` và transaction bằng storage/session phù hợp, rồi gửi verifier đúng một lần ở token endpoint.

### 5.1. Kiểm thử Java bằng test vector RFC

~~~java
String verifier =
    "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String expected =
    "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

if (!expected.equals(PkceSupport.challengeS256(verifier))) {
    throw new AssertionError("PKCE S256 implementation mismatch");
}
~~~

Test vector là dữ liệu **công khai**; đừng dùng nó làm verifier trong session production. Với unit tests thực tế, kiểm tra cả độ dài, ký tự hợp lệ, sự khác nhau giữa nhiều verifier và các trường hợp input không hợp lệ.

## 6. JavaScript trong browser: Web Crypto thay vì `Math.random()`

Ví dụ dùng Web Crypto trên **secure context (HTTPS)**:

~~~javascript
function base64url(bytes) {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function newCodeVerifier() {
  const random = new Uint8Array(32);
  crypto.getRandomValues(random);
  return base64url(random);
}

async function s256Challenge(verifier) {
  const ascii = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", ascii);
  return base64url(new Uint8Array(digest));
}

async function beginAuthorization() {
  const verifier = newCodeVerifier();
  const challenge = await s256Challenge(verifier);

  const state = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const nonce = base64url(crypto.getRandomValues(new Uint8Array(32)));

  // Giao dịch authorization ngắn hạn, không phải token storage.
  const tx = {
    verifier,
    nonce,
    issuer: "https://auth.example.com",
    createdAt: Date.now()
  };
  sessionStorage.setItem("oauth.tx." + state, JSON.stringify(tx));

  const url = new URL("https://auth.example.com/oauth2/authorize");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", "orders-spa");
  url.searchParams.set(
    "redirect_uri", "https://app.example.com/callback"
  );
  url.searchParams.set("scope", "openid orders.read");
  url.searchParams.set("state", state);
  url.searchParams.set("nonce", nonce);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  location.assign(url.toString());
}
~~~

**Giới hạn của ví dụ:**

1. Đã dùng CSPRNG cho `verifier`, `state`, `nonce`; mỗi giá trị có mục đích **khác nhau**.
2. `sessionStorage` chỉ là ví dụ lưu **authorization transaction tạm** qua full-page redirect; không phải kho lưu access/refresh token được khuyến nghị.
3. Nếu XSS chạy cùng origin, attacker có thể đọc transaction storage. **PKCE không chống XSS kiểm soát JavaScript**, nên phải phòng DOM XSS, bảo vệ third-party scripts và dùng CSP/Trusted Types khi thích hợp.
4. Phải có callback handler kiểm tra `state`, issuer, TTL và đánh dấu transaction chỉ dùng một lần; snippet này **chưa bao gồm** callback/token exchange.
5. Authorization endpoint, client registration, redirect URI phải đến từ **cấu hình đã tin cậy**, không phải tham số arbitrary của URL do attacker gửi.
6. Với production nên dùng thư viện OAuth/OIDC được bảo trì và hỗ trợ PKCE/state/issuer-mix-up defense; code mẫu chỉ cho thấy **cách tạo các giá trị**.

### 6.1. Vì sao không giữ verifier chỉ trong biến JavaScript?

Browser thường **điều hướng sang authorization server rồi quay về**, làm document SPA ban đầu bị hủy. Nếu verifier chỉ ở một biến closure của document cũ, callback có thể **không còn giá trị** để đổi code.

Tùy threat model:

- **BFF/Java backend:** giữ PKCE verifier và transaction trong **server-side session** là lựa chọn tốt khi có backend tin cậy.
- **SPA:** thư viện có thể dùng `sessionStorage` hoặc cơ chế tương đương **chỉ cho transaction ngắn hạn**. Bảo vệ XSS, TTL, xóa sau khi xử lý.
- **Native app:** giữ verifier trong bộ nhớ/storage theo vòng đời ứng dụng và platform, không công khai qua URL/intent/log.

Không đánh đồng “lưu tạm PKCE verifier cho callback” với “được phép lưu access token dài hạn trong localStorage”.

## 7. Authorization server phải lưu và kiểm tra những gì?

AS cần **ràng buộc PKCE với authorization code** khi phát code. Một bản ghi logic có thể bao gồm:

~~~text
AuthorizationCodeRecord:
  code_hash           = HMAC hoặc digest của code ngẫu nhiên
  client_id           = orders-spa
  redirect_uri        = https://app.example.com/callback
  code_challenge      = E9Melhoa...
  method              = S256
  scope_granted       = orders.read
  resource_audience   = https://api.example.com/orders
  subject             = user-42
  issued_at           = ...
  expires_at          = ...
  consumed            = false
~~~

Đây là **mô hình dữ liệu minh họa**, không phải schema bắt buộc của OAuth. Code phải có entropy đủ cao, hết hạn ngắn và được dùng **một lần**. AS nên tránh lưu code plaintext nếu có thể lookup bằng digest/HMAC an toàn.

### 7.1. Kiểm tra tại token endpoint

Khi nhận token request, AS cần:

1. Xác định client, thực hiện **client authentication** nếu client confidential và xác định grant type đúng.
2. Kiểm tra code được **phát cho đúng client**, còn hạn, chưa dùng, không bị thu hồi.
3. Kiểm tra `redirect_uri` phù hợp với giá trị đã gắn vào authorization code và quy tắc OAuth/profile.
4. Nếu code gắn PKCE, yêu cầu `code_verifier` đúng cú pháp.
5. Áp đúng **`code_challenge_method` đã lưu**, tính lại challenge và so sánh an toàn.
6. Kiểm tra authorization grant, scopes/resource và chính sách phát hành token.
7. Đánh dấu code đã tiêu thụ **atomically**, tránh hai token requests đồng thời đều thành công.
8. Chỉ khi tất cả điều kiện đạt mới phát access/refresh/ID token theo policy; không trả verifier/code lại trong response.

**Không được cho client thay `code_challenge_method` ở token request** để chọn cách verify thuận lợi hơn. AS phải dùng method được **cam kết lúc authorization request**.

### 7.2. Atomic one-time use và replay

Hai request đồng thời cùng gửi một code:

~~~text
Request A: code=X, verifier=V
Request B: code=X, verifier=V

AS kiểm tra code X chưa dùng bằng transaction/CAS/lock.
Kết quả: TỐI ĐA một lần đổi code thành công.
Request còn lại bị từ chối.
~~~

Nếu check `consumed=false` rồi cập nhật ở nhiều lệnh không đồng bộ, hai node AS có thể đều cấp token. Triển khai phải dùng transaction, constraint hoặc compare-and-swap, và có chính sách xử lý việc **code đã được dùng lại** (ví dụ điều tra/thu hồi token liên quan khi chuẩn và threat model yêu cầu).

**PKCE không thay tính một-lần của authorization code.** Nó chỉ ràng buộc bên có code với verifier đúng.

## 8. `S256` và `plain`: chính sách được phép

RFC 7636 định nghĩa hai phương thức:

| Method | Công thức | Đánh giá sử dụng |
| --- | --- | --- |
| **`S256`** | `BASE64URL(SHA256(ASCII(verifier)))` | **Ưu tiên**, tránh lộ verifier chỉ từ authorization request |
| **`plain`** | `challenge = verifier` | Tương thích lịch sử trong một số bối cảnh hạn chế; không dùng mặc định |

Với `plain`, nếu attacker thấy authorization request chứa `code_challenge`, attacker cũng biết chính verifier. Điều này làm mất phần bảo vệ quan trọng của PKCE trước một số tình huống nghe lén/log front-channel.

**Không tự fallback từ `S256` xuống `plain`** nếu authorization server hoặc client có lỗi. Nếu hệ thống yêu cầu `S256`, request có `plain` hoặc thiếu method phải bị từ chối theo policy.

### 8.1. Method bị thiếu có ý nghĩa gì?

Theo **RFC 7636**, nếu `code_challenge` có nhưng `code_challenge_method` bị bỏ qua, giá trị mặc định về mặt cú pháp là **`plain`**. Vì vậy, client muốn `S256` phải **gửi tường minh `code_challenge_method=S256`**.

Với AS chỉ cho `S256`, nó nên từ chối request thiếu method thay vì âm thầm hiểu là an toàn tương đương.

### 8.2. “Hash” không đồng nghĩa chữ ký số

SHA-256 ở PKCE là hàm băm một chiều giúp tạo **commitment**. Nó **không** dùng private key, JWS `alg` hay JWKS. JWT access token có thể được ký RS256/ES256 hoặc là opaque token; **PKCE không phụ thuộc vào định dạng access token cuối cùng**.

## 9. PKCE và `state`: khác nhau và bổ sung nhau

Một nguồn nhầm lẫn thường gặp là cho rằng “đã có PKCE thì không cần `state`” hoặc “đã có `state` thì không cần PKCE”.

| Cơ chế | Được tạo khi nào? | Bên nào kiểm tra? | Bảo vệ trọng tâm |
| --- | --- | --- | --- |
| **PKCE verifier/challenge** | Trước authorization request | **Authorization server tại token endpoint** | Đánh cắp authorization code / ràng buộc flow |
| **`state`** | Trước authorization request | **Client tại callback** | Liên kết authorization response với transaction, CSRF/callback confusion |
| **OIDC `nonce`** | Trước OIDC request | **OIDC client sau khi verify ID token** | Ràng buộc ID token với authentication request |
| **Issuer response `iss`** | AS trả ở authorization response khi hỗ trợ | **Client tại callback** | Chống authorization-server mix-up |

Một số cấu hình PKCE đúng có thể được sử dụng như **một thành phần chống CSRF** theo các security BCP/profile phù hợp; nhưng điều đó đòi hỏi client/AS ràng buộc transaction chặt chẽ. **Dùng `state` ngẫu nhiên và kiểm tra nó vẫn là thực hành rõ ràng, dễ audit**, đặc biệt với browser callbacks và các flow có nhiều transaction.

### 9.1. Tại sao vẫn cần kiểm tra callback?

Một callback giả:

~~~http
GET /callback?code=<attacker-code>&state=<unknown-state> HTTP/1.1
Host: app.example.com
~~~

Nếu client không kiểm tra state/transaction mà cố lấy verifier của một phiên khác, nó có thể gây login CSRF, session confusion hoặc làm token request thất bại không dự kiến. **Không lấy verifier “mới nhất” ở một biến global** khi nhiều tab/flow đang chạy.

### 9.2. OIDC ID token không phải access token

Khi dùng `scope=openid`, OP có thể trả **ID token** tại token endpoint. Client phải verify `iss`, `aud=client_id`, chữ ký, `exp`, `nonce` (nếu đã yêu cầu) và các claims theo profile. Access token dùng gọi API phải có **audience của resource server**; không dùng ID token thay access token dù PKCE đã thành công.

## 10. PKCE và redirect URI: cần cả hai

**Redirect URI matching** hạn chế nơi AS trả authorization response; PKCE hạn chế ai có thể **đổi code** khi đã biết code. Hai lớp bảo vệ khác nhau:

~~~text
AS /authorize:
  client_id = orders-spa
  redirect_uri = https://app.example.com/callback  (đã đăng ký)
  code_challenge = C
  method = S256

AS /token:
  same client_id
  code hợp lệ, chưa dùng
  redirect_uri khớp
  verifier chứng minh C
~~~

**Không thay exact redirect URI validation bằng PKCE.** Nếu AS cho phép `redirect_uri=https://attacker.example` hoặc có open redirect, attacker có thêm đường lấy code và gây nhầm phiên; các rủi ro quanh token/transaction vẫn còn.

| Rủi ro | Kiểm soát liên quan |
| --- | --- |
| Redirect URI trỏ host không đăng ký | AS validate registered redirect URI |
| Code bị chặn ở callback | PKCE S256, one-time/short-lived code |
| Callback được gắn vào sai phiên | `state`, transaction binding |
| Gửi code sang token endpoint của issuer khác | Issuer binding/`iss` hoặc mix-up defense |
| Callback là open redirect | Client allowlist return paths, không redirect tùy ý |
| Access token được gửi tới API sai | RS validate `aud`, `iss`, `scope` và type |

Với native apps, **RFC 8252** quy định thực hành dùng external user-agent và redirect phù hợp; loopback URI có ngoại lệ về port theo điều kiện chuẩn. PKCE đặc biệt có ý nghĩa khi URI scheme/app links có khả năng bị tranh chấp.

## 11. PKCE cho SPA, native và BFF/Java khác nhau thế nào?

### 11.1. SPA chạy trong browser

- Dùng **Authorization Code + PKCE S256**.
- Không nhúng client secret vào JavaScript.
- Giữ transaction/verifier tạm và bảo vệ callback `state`, issuer, TTL.
- Access token nên có hạn ngắn và được lưu theo threat model; cân nhắc **in-memory** thay cho Web Storage bền vững.
- Nếu sử dụng refresh token cho public client, cần cơ chế chống replay như **refresh token rotation hoặc sender constraint** theo chính sách/chuẩn áp dụng.
- Browser XSS có thể lợi dụng phiên hoặc đọc storage đang hoạt động; PKCE không loại bỏ điều đó.

### 11.2. Native mobile/desktop

- Mở authorization request bằng **trình duyệt hệ thống / external user-agent**, không nhúng form mật khẩu tự quản lý.
- Dùng **PKCE S256** và redirect URI đúng native-app profile (app links/universal links/loopback khi phù hợp).
- Giữ verifier trong bộ nhớ/OS storage phù hợp tới lúc callback đến; không log code/verifier.
- Đừng dựa vào client secret được nhúng trong binary; attacker có thể reverse-engineer.
- Token storage sau khi đổi code cần tách riêng: access token ngắn hạn và refresh token trong secure platform storage khi cần.

### 11.3. Backend for Frontend và Spring Boot

- Java backend giữ transaction PKCE và client credential trong **server-side session/token store bảo vệ**.
- Browser nhận session cookie **Secure, HttpOnly, SameSite phù hợp** thay vì OAuth token raw khi kiến trúc cho phép.
- Backend xử lý callback, kiểm tra state, issuer và đổi code với `code_verifier`.
- Confidential client vẫn thực hiện **client authentication** ở token endpoint; PKCE là lớp bảo vệ bổ sung.
- Không bỏ CSRF/session protection vì cookie `HttpOnly`; backend cũng phải kiểm tra authorization tại từng API.

**Spring Security OAuth2 Client** có thể quản lý authorization code login và PKCE theo registration/client settings/phiên bản đang dùng. Cần **kiểm tra behavior thực tế**, không giả định “mọi client tự bật PKCE S256” mà không có integration test.

## 12. Mẫu lưu transaction an toàn

Một bản ghi transaction phía client/BFF có thể là:

~~~json
{
  "state_ref": "opaque-random-state",
  "issuer": "https://auth.example.com",
  "client_id": "orders-spa",
  "redirect_uri": "https://app.example.com/callback",
  "code_verifier": "<random-verifier>",
  "nonce": "<random-oidc-nonce>",
  "created_at": "2026-11-23T02:00:00Z",
  "status": "PENDING"
}
~~~

**Đây là JSON minh họa**, không phải dữ liệu production. `code_verifier` là bí mật ngắn hạn; state/nonce cũng cần được ràng buộc chính xác với phiên.

### 12.1. Bất biến transaction

1. Mỗi `state` ánh xạ đến **một** verifier và một issuer dự kiến.
2. Có **TTL** ngắn; không nhận callback sau khi transaction hết hạn.
3. **One-time consumption:** callback được xử lý một lần dù browser gửi lại URL.
4. Nhiều tab/luồng chạy đồng thời phải có **transaction keys riêng**; không ghi đè một biến global.
5. Không phản hồi verifier/secret lại cho client không đáng tin hoặc ghi vào URL/log.
6. Nếu token exchange thất bại, hủy transaction/flow phù hợp; **không tái dùng authorization code** đã bị token endpoint từ chối.

### 12.2. Khi redirect làm mất memory

Trong SPA, full-page redirect có thể hủy JS document, khiến verifier chỉ tồn tại trong closure không còn. Cần chọn storage tạm phù hợp hoặc dùng BFF. **Storage của verifier không bắt buộc giống storage của access token** sau khi flow kết thúc.

### 12.3. CSRF với session cookie trong BFF

Việc callback OAuth mang state/PKCE không tự làm mọi route BFF an toàn trước CSRF. Các request thay đổi tài nguyên dùng cookie phiên vẫn cần CSRF defense, Origin/SameSite phù hợp và object-level authorization.

## 13. PKCE chống được loại tấn công nào?

| Tình huống | PKCE S256 có ích không? | Giới hạn |
| --- | --- | --- |
| Attacker chỉ biết **authorization code** | **Có**, không biết verifier tương ứng | Code vẫn phải một lần/hạn ngắn |
| Attacker thấy **authorization request/challenge** | **Có**, S256 không trực tiếp lộ verifier | Challenge phải được tạo từ verifier entropy cao |
| Redirect URI bị đổi thành domain attacker | PKCE giảm khả năng đổi code nhưng **không giải quyết toàn bộ** | AS bắt buộc validate redirect URI |
| Attacker lấy **cả code và verifier** | **Không đủ** | Cần chống XSS/log leak/device compromise |
| Attacker lấy **access token Bearer đã phát** | **Không** | Token TTL/audience/scope, storage, DPoP/mTLS, revoke |
| Attacker lấy **refresh token** | **Không** | Refresh token rotation/sender constraint |
| Client gửi code tới **AS sai (mix-up)** | **Không đủ** | State/issuer binding/RFC 9207 |
| Resource server bỏ qua `aud` | **Không** | RS phải validate issuer/audience/type/scope |
| XSS chạy trong SPA đang mở | **Không đủ** | XSS có thể đọc storage/gọi API |
| User bị lừa consent cho client độc hại | Không phải trọng tâm PKCE | Client registration, consent, phishing defenses |
| Code bị replay song song | PKCE không thay one-time semantics | AS phải consume code atomically |

**PKCE không phải sender-constrained access token.** Sau khi AS đã cấp token, việc bảo vệ Bearer token khỏi replay yêu cầu các biện pháp khác như hạn ngắn, audience hẹp, lưu trữ an toàn và DPoP/mTLS nếu được hỗ trợ.

## 14. Các lỗi PKCE thường gặp

### 14.1. Dùng Base64 chuẩn thay vì Base64url

Sai:

~~~text
Base64 standard:  + / =
Base64url:        - _   (không padding)
~~~

Trong PKCE `S256`, digest phải được mã hóa **Base64url không padding**. Không gửi chuỗi dạng hex SHA-256 thay cho challenge. Test vector RFC là cách xác nhận nhanh.

### 14.2. Hash verifier không đúng bytes

Hàm SHA-256 phải nhận **ASCII bytes của verifier**, không phải bytes của dữ liệu ngẫu nhiên ban đầu, không phải Base64-decode(verifier) rồi mới hash và không thêm newline.

~~~text
ĐÚNG:
  verifier text -> ASCII bytes -> SHA-256 -> Base64url

SAI:
  random bytes -> SHA-256 -> Base64url
  (nếu verifier đã được encode thành chuỗi khác)
~~~

Nếu client và AS dùng công thức khác nhau, token endpoint trả lỗi dù user đăng nhập thành công.

### 14.3. Sinh verifier mới trước khi đổi code

Sai:

~~~text
/authorize: verifier = V1; challenge = S256(V1)
/token:     verifier = V2 (mới sinh)
=> S256(V2) != S256(V1): invalid_grant
~~~

**Đúng:** giữ đúng verifier của transaction gốc đến khi đổi code, sau đó xóa.

### 14.4. Đặt `code_verifier` trong authorization URL

Sai:

~~~text
/authorize?...&code_verifier=<secret>
~~~

**Đúng:** authorization request chỉ có `code_challenge` và `code_challenge_method`; verifier gửi **sau** qua back-channel tại token endpoint.

### 14.5. Bỏ `code_challenge_method` nhưng tưởng vẫn là S256

Theo RFC 7636, khi method thiếu, mặc định tương ứng **`plain`**. Client muốn S256 phải ghi tường minh.

### 14.6. Dùng state, nonce và verifier như cùng một giá trị

Các giá trị có nhiệm vụ và phạm vi tiết lộ khác nhau. Tốt nhất **sinh độc lập**, không copy một random string cho tất cả trường và không log chúng thành một record dễ tìm.

### 14.7. Chấp nhận token request không PKCE để “tương thích”

Nếu AS/client đã yêu cầu PKCE, code thiếu challenge không được đổi như một grant bình thường. **Tấn công PKCE downgrade** có thể xảy ra nếu đường fallback cho phép bỏ qua proof. Ràng buộc yêu cầu PKCE theo client/profile và code.

### 14.8. Dùng PKCE làm lý do không kiểm tra redirect URI

PKCE chỉ chống một phần code interception. Redirect URI giả, wildcard hoặc open redirect vẫn gây rủi ro; AS cần exact-match theo chuẩn/ngoại lệ đúng và client phải xử lý callback an toàn.

## 15. Mã lỗi và chẩn đoán

| Biểu hiện | Lớp phát hiện | Khả năng nguyên nhân |
| --- | --- | --- |
| `invalid_request` ở authorization endpoint | AS | PKCE challenge sai cú pháp, thiếu tham số bắt buộc, method không hỗ trợ theo policy |
| `invalid_grant` ở token endpoint | AS | Code hết hạn/đã dùng, verifier không khớp, client/redirect sai |
| `invalid_client` | AS token endpoint | Confidential client authentication thất bại |
| Callback báo state mismatch | OAuth client | Không tìm thấy transaction, CSRF/callback mix-up, hết TTL |
| `iss` authorization response không khớp | OAuth client | Sai issuer hoặc mix-up |
| `401 invalid_token` khi gọi API | Resource server | Access token sai, expired, sai issuer/audience/signature |
| `403 insufficient_scope` | Resource server | Token hợp lệ nhưng không có scope yêu cầu |
| Browser báo CORS tại token endpoint | Browser/AS CORS | Token endpoint không cho origin SPA hoặc preflight sai |

**Đừng đọc `invalid_grant` là “mật khẩu người dùng sai”.** Nó thường là lỗi ở bước **đổi authorization code**, bao gồm PKCE, redirect URI, thời hạn và tính một lần. Để chẩn đoán, dùng transaction ID, client alias, error category và thông tin về độ dài/phương thức challenge; **không log code/verifier/token**.

## 16. PKCE trong hệ sinh thái JWT, opaque, scope và audience

PKCE hoạt động **trước khi token được phát**, không quy định token cuối là JWT hay opaque.

~~~mermaid
flowchart TD
    A["Authorization request + PKCE S256"] --> B["AS phát authorization code"]
    B --> C["Client đổi code + verifier đúng"]
    C --> D{"Token type do AS quyết định"}
    D --> E["JWT access token"]
    D --> F["Opaque access token"]
    E --> G["RS verify signature,\niss, aud, exp, scope"]
    F --> H["RS introspection / lookup,\nactive, aud, scope"]
    G --> I["Resource authorization:\ntenant, owner, policy"]
    H --> I
~~~

### 16.1. Scope được xin khác scope được cấp

Client có thể xin `scope=orders.read orders.write` nhưng AS chỉ cấp `orders.read` theo consent và policy. PKCE thành công **không ép AS cấp mọi scope**. Resource server dựa trên token/introspection thực tế.

### 16.2. Audience được chọn bởi AS

Client có thể dùng resource indicator (RFC 8707) để xin access token cho Orders API; AS xác định audience được cấp. RS phải kiểm tra `aud` đúng mình, dù token được cấp qua code flow có PKCE.

### 16.3. Refresh token không được PKCE bảo vệ sau khi phát

Nếu AS cấp refresh token, lần refresh tiếp theo dùng `grant_type=refresh_token`, **không chạy PKCE cho authorization code lại**. Refresh token cần lưu trữ an toàn, rotation/sender constraint theo policy, TTL và revocation.

### 16.4. OAuth token validation không kết thúc ở PKCE

Access token đúng chữ ký và scope vẫn cần kiểm tra:

- `iss`/trusted issuer và JWS algorithm/key khi JWT;
- `aud`/resource server;
- `exp`, `nbf`, loại token/profile;
- scope/role theo hợp đồng, user/service principal;
- tenant, record ownership, permission thực tế và trạng thái thu hồi;
- sender constraint (DPoP/mTLS) nếu token yêu cầu.

## 17. PKCE và những cơ chế không thể thay thế

| Cơ chế | Bảo vệ điều gì? | PKCE có thay thế không? |
| --- | --- | --- |
| **Client authentication** | Xác minh confidential client tại token endpoint | **Không** |
| **`state`/transaction binding** | Gắn callback với phiên khởi tạo, CSRF/mix-up defense | Không thay toàn bộ; cần theo profile |
| **OIDC `nonce`** | Ràng buộc ID token với authentication request | **Không** |
| **Redirect URI validation** | Chặn AS trả code sai nơi | **Không** |
| **PAR/JAR** | Giảm lộ/thay đổi authorization request parameters | **Không** |
| **Access token signature/introspection** | Chứng minh token được AS phát và còn hợp lệ | **Không** |
| **DPoP/mTLS-bound access token** | Ràng buộc token với khóa/chứng chỉ sender | **Không** |
| **Refresh token rotation** | Phát hiện replay refresh token cũ | **Không** |
| **MFA/step-up** | Mức bảo đảm xác thực user | **Không** |
| **Object-level authorization** | Quyền trên dữ liệu, tenant và nghiệp vụ | **Không** |

PKCE phải được xem như **một lớp trong mô hình tin cậy nhiều tầng**, không phải nhãn “OAuth đã an toàn” cho mọi API và mọi token.

## 18. PKCE trong reverse proxy, PAR và multi-issuer

### 18.1. Reverse proxy và public redirect URI

Nếu Java BFF nằm sau ingress, `redirect_uri` public có thể là `https://app.example.com/login/oauth2/code/provider`, trong khi backend nhận request từ `http://bff:8080`. Cần cấu hình **public origin và trusted forwarding** đúng. Không dựng redirect URI dựa vào spoofed `X-Forwarded-Host` hoặc nới AS redirect allowlist.

PKCE không sửa được lỗi callback bị gửi sai host hoặc token exchange dùng sai `redirect_uri`.

### 18.2. PAR/JAR có thay PKCE không?

**PAR (RFC 9126)** đẩy authorization request lên AS qua back-channel; **JAR (RFC 9101)** có thể bảo vệ tính toàn vẹn nội dung bằng Request Object. Dù authorization request được bảo vệ, **code vẫn cần được đổi an toàn tại token endpoint**. Vì vậy PKCE vẫn có vai trò độc lập.

### 18.3. Multi-issuer và token endpoint mix-up

Client hỗ trợ nhiều OP phải lưu **issuer dự kiến** trong transaction và kiểm tra issuer response khi profile hỗ trợ (chẳng hạn `iss` theo RFC 9207). Không chọn token endpoint dựa trên query từ callback. Nếu gửi code/verifier sang AS không đúng, PKCE không đủ để bảo vệ toàn bộ credential và luồng xác thực.

## 19. Những tình huống thực tế

**Tình huống A — Mobile authorization code bị chặn.** App A bắt đầu flow với verifier ngẫu nhiên; app B giành custom URI callback và nhận code.

**Phân tích:** nếu B chỉ có code, AS phải từ chối token request thiếu/sai verifier. Vẫn cần app redirect registration, external user-agent, URI scheme/app links đúng và thiết bị an toàn.

**Tình huống B — SPA đổi code bị `invalid_grant` sau reload.** Verifier chỉ nằm trong biến JS, document cũ bị hủy khi redirect sang OP.

**Phân tích:** callback không có verifier của giao dịch gốc. Dùng transaction storage ngắn hạn phù hợp hoặc BFF/server session; không sinh verifier mới ở callback.

**Tình huống C — Login thành công nhưng Orders API trả 403.** PKCE đúng, token chỉ có `orders.read`; client gọi POST tạo đơn hàng.

**Phân tích:** PKCE xác minh code exchange, không tự cấp `orders.write`. API từ chối theo scope và policy.

**Tình huống D — Authorization server chấp nhận `plain` dù client yêu cầu S256.** Một route/phân hệ token endpoint dùng policy mặc định khác.

**Phân tích:** triển khai dễ bị downgrade. Ràng buộc method với code và client policy; kiểm thử âm cả trường hợp thiếu method và challenge.

**Tình huống E — Attacker lấy cả code và verifier từ log.** Proxy ghi URL callback, frontend log transaction state/verifier.

**Phân tích:** PKCE không bảo vệ khi proof cũng bị lộ. Redact logs, giới hạn quyền truy cập, kiểm tra nguyên nhân và xử lý credential liên quan.

**Tình huống F — Hai tab cùng đăng nhập.** Tab A có state/verifier A; tab B có state/verifier B.

**Phân tích:** nếu ứng dụng dùng một `currentVerifier` global, callback A có thể đổi nhầm verifier B. Lưu transaction theo state, TTL và one-time consumption.

**Tình huống G — Native app có client secret hard-code.** Developer nghĩ secret trong binary thay PKCE.

**Phân tích:** secret có thể bị trích xuất; native app là public client theo threat model thông thường. Dùng PKCE, đăng ký redirect và token storage OS phù hợp.

**Tình huống H — Bearer access token bị đánh cắp sau code flow.** Attacker thấy token trong network log và gọi API.

**Phân tích:** PKCE đã hoàn thành nhiệm vụ trước đó, không ngăn bearer replay. Cần TTL, issuer/audience/scope validation, bảo vệ token, revocation và cân nhắc sender constraints.

## 20. Bộ kiểm thử bắt buộc

| Test case | Kỳ vọng |
| --- | --- |
| Verifier mới sinh từ 32 byte CSPRNG | 43 ký tự Base64url, không có `=` |
| Verifier RFC 7636 test vector | Challenge đúng `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM` |
| Verifier dài dưới 43 hoặc trên 128 ký tự | Từ chối hoặc không tạo request |
| Verifier chứa ký tự ngoài unreserved | Từ chối |
| Challenge chứa Base64 padding `=` | Từ chối/không khớp theo policy chuẩn |
| Authorization request có `S256` và challenge hợp lệ | AS lưu cùng code |
| Token request với verifier đúng, code/redirect/client hợp lệ | Đổi code **một lần** thành công |
| Token request thiếu verifier cho code đã gắn challenge | Từ chối |
| Token request có verifier sai | `invalid_grant` hoặc lỗi chuẩn tương ứng |
| Client dùng verifier mới ở callback | Không đổi code được |
| Auth request thiếu `code_challenge_method` khi AS chỉ cho S256 | Từ chối, không mặc định coi là S256 |
| Attacker đổi method từ S256 sang plain | Không làm code trở thành token |
| Authorization code đã dùng lại | Từ chối, chống replay |
| Hai token requests đồng thời dùng cùng code | Tối đa một request thành công |
| Code bị đánh cắp nhưng không có verifier | Attacker không đổi token được |
| Code và verifier đều bị lộ | Phát hiện giới hạn PKCE; xử lý sự cố và log protection |
| Redirect URI sai đăng ký | AS không phát code về URI sai |
| Token request đổi redirect URI | Từ chối theo ràng buộc code/redirect |
| Callback thiếu/sai/hết hạn `state` | Client từ chối, không đổi code |
| OIDC `nonce` trong ID token sai | Client từ chối ID token |
| Multi-issuer `iss` response khác transaction | Từ chối, không dùng token endpoint sai |
| SPA reload mất verifier | Flow phục hồi an toàn, không tự fallback |
| Nhiều tab/transactions | Không trộn verifier/state |
| Public client nhúng `client_secret` | Kiểm tra bảo mật thất bại |
| Token đúng PKCE nhưng sai `aud` | API từ chối |
| Token đúng scope nhưng dữ liệu tenant khác | API từ chối object authorization |
| Access token bị thu hồi hoặc quá `exp` | API từ chối theo validation/revocation policy |
| Refresh token rotation reuse | AS xử lý theo token family/replay policy, không dùng PKCE thay thế |

### 20.1. Test ở tầng nào?

- **Unit test:** verifier generation, challenge algorithm, cú pháp/độ dài, RFC vector.
- **Authorization integration test:** AS nhận `code_challenge`, ràng buộc code và verifier, rejection cho method/verifier sai.
- **Browser/native integration test:** redirect, state, transaction storage, callback một lần, cross-tab và issuer binding.
- **Token endpoint concurrency test:** hai requests một code, chỉ một lần thành công.
- **Resource server authorization test:** JWT/opaque validation, audience/scope và ownership độc lập với PKCE.

**Mock một principal đã đăng nhập không chứng minh PKCE an toàn.** Cần kiểm thử thật đường `/authorize` → callback → `/token` ở môi trường test.

### 20.2. Không biến test thành nguồn lộ bí mật

Dùng verifier/code/token thử nghiệm, không đưa token thật vào bug report, console logs, CI artifacts hoặc screenshot. Nếu muốn debug so sánh challenge, có thể dùng **test vector công khai** và đo chiều dài thay vì log session secrets.

## 21. Checklist production

1. **Xác định client type:** public SPA/native hay confidential BFF; PKCE gắn với Authorization Code Flow.
2. **Dùng `S256` tường minh:** AS hỗ trợ/bắt buộc theo policy; không fallback `plain` vô thức.
3. **Verifier khó đoán:** CSPRNG tối thiểu mức entropy phù hợp (thực hành tốt 32 byte), 43–128 ký tự unreserved.
4. **Một verifier cho mỗi flow:** không hard-code, không reuse giữa user/tab/session.
5. **Lưu transaction đúng scope:** `state`, verifier, issuer, redirect URI, nonce, TTL; xóa sau callback/timeout.
6. **Authorization request đúng:** `response_type=code`, client ID, registered redirect URI, scope, state, challenge và S256.
7. **Token request đúng:** code, code verifier, cùng client/redirect và confidential client authentication khi cần.
8. **AS ràng buộc code atomically:** hạn ngắn, one-time, PKCE method/challenge cố định, chống token issuance race.
9. **Callback an toàn:** state/issuer binding, lỗi `invalid_grant` phù hợp, không log code/verifier.
10. **Bảo vệ redirect:** exact match, HTTPS cho web, loopback/native exceptions đúng profile; chống open redirect.
11. **Nếu OIDC:** kiểm tra ID token/nonce và step-up claims khi cần; không dùng ID token gọi API.
12. **Bảo vệ token sau khi cấp:** access token lưu an toàn, refresh rotation/sender constraint, revoke, TTL phù hợp.
13. **RS vẫn xác minh:** JWT signature/algorithm hoặc opaque introspection, issuer, audience, scope và resource rights.
14. **Giảm XSS/log leak:** CSP, kiểm soát dependencies, redaction tại proxy/client/backend và không đưa secret vào URL.
15. **Kiểm thử âm:** verifier sai, code reuse, S256/plain downgrade, callback mismatch, wrong issuer, token replay.

## 22. Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): cú pháp verifier, công thức `S256`, `plain`, ràng buộc authorization code và test vector.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code, client registration, redirect URI, token endpoint, `state`.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE best practices, authorization code injection/interception, mix-up và refresh token bảo vệ.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): native apps, external user-agent, loopback redirect và PKCE.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): phản hồi `iss` để giảm mix-up với nhiều issuer.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `nonce`, ID token validation và OIDC authentication flow.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource/audience của access token.
- [RFC 9126 — Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): gửi request qua back-channel; bổ sung, không thay PKCE.
- [RFC 9101 — JWT-Secured Authorization Request](https://www.rfc-editor.org/rfc/rfc9101): Request Object và tính toàn vẹn authorization request.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens và chống replay sau phát hành.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): client authentication và certificate-bound access tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token validation tại resource server.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth2 client registration, authorization code flow và ứng dụng Java/Spring.

**Ghi nhớ:** **PKCE (RFC 7636) làm cho authorization code bị đánh cắp không đủ để đổi token**, bằng cách yêu cầu client chứng minh `code_verifier` tương ứng với `code_challenge` **S256** đã gắn vào code. Sinh verifier mới bằng CSPRNG cho mỗi flow, giữ nó chỉ trong transaction phù hợp, kiểm tra state/issuer/redirect, và yêu cầu AS verify PKCE cùng one-time code và client policy. **PKCE không bảo vệ access token sau khi phát hành**: API vẫn phải kiểm tra issuer, audience, thời gian, scope, quyền trên dữ liệu và các cơ chế chống token theft/replay cần thiết.
