# 27.3. PKCE, nonce, state và cơ chế chống replay tương ứng

Trong ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, trình duyệt thường rời ứng dụng để đến Authorization Server (AS) hoặc OpenID Provider (OP), sau đó quay lại ứng dụng với một authorization response. Một kẻ tấn công có thể cố gắng **chèn một response từ giao dịch khác**, **đánh cắp authorization code**, **phát lại một ID Token**, hoặc **dùng một token đã lộ để gọi API**.

Ba cơ chế thường gặp trong quá trình bảo vệ Authorization Code / OIDC Login là:

- **`state`**: liên hệ authorization response với **authorization request ban đầu** trong ngữ cảnh client/browser thích hợp; hỗ trợ ngăn login CSRF và các tình huống gắn nhầm giao dịch.
- **PKCE (Proof Key for Code Exchange)**: tạo quan hệ mật mã giữa **authorization request** và **token request** bằng cặp `code_challenge` / `code_verifier`; bảo vệ trước việc một bên có được authorization code nhưng không nắm verifier.
- **OIDC `nonce`**: liên hệ **ID Token** với **authentication request** đã bắt đầu; chống việc sử dụng một ID Token không thuộc yêu cầu hiện tại trong những flow áp dụng.

Những cơ chế này **bổ sung cho nhau, không thể thay thế tùy tiện cho nhau**. Chúng cũng **không tự ngăn access token bị đánh cắp và phát lại** tại Resource Server; vấn đề đó cần token validation, giới hạn audience/scope/lifetime, bảo vệ nơi lưu token và, khi phù hợp, các token có ràng buộc người gửi như DPoP hoặc mTLS.

Ví dụ flow chuẩn có thể có:

```text
Browser mở /oauth2/authorization/company
    |
    v
Spring Security tạo:
    state = S-opaque-random
    code_verifier = V-secret-random
    code_challenge = BASE64URL(SHA256(V))
    nonce = N-unique (khi flow OIDC sử dụng)
    |
    v
Authorization request -> OP
    state=S
    code_challenge=...
    code_challenge_method=S256
    nonce=...
    |
    v
Browser quay về callback:
    code=C
    state=S
    |
    v
Client kiểm tra correlation theo state
    |
    v
Token request:
    grant_type=authorization_code
    code=C
    code_verifier=V
    |
    v
OP kiểm tra PKCE, cấp tokens khi hợp lệ
    |
    v
Spring Security kiểm tra ID Token:
    chữ ký, issuer, audience, thời hạn, nonce khi áp dụng
    |
    v
Authentication hợp lệ mới được tạo
```

Bài thuộc chương **27. Bảo mật tích hợp**, sử dụng Spring Security 6.x trên Servlet làm ví dụ chính; có đối chiếu Reactive WebFlux. Mục tiêu là hiểu **lớp bảo vệ nào chống kiểu replay nào**, cách Spring Security lưu correlation và cách triển khai mà không vô tình vô hiệu hóa cơ chế bảo mật.

> **Phạm vi:** Java 17+, Spring Boot 3.x / Spring Security 6.x, OAuth 2.0 Authorization Code + OIDC. Các hostname `example.test` và token giá trị `REDACTED` chỉ để minh họa. Những đoạn tạo ngẫu nhiên độc lập là bài tập để hiểu PKCE; với production hãy ưu tiên bộ sinh và bộ kiểm tra của Spring Security.

---

## 1. Trước hết: replay là gì?

Trong xác thực và ủy quyền, **replay attack** là việc kẻ tấn công gửi lại một thông điệp, credential hoặc token đã tồn tại để hệ thống chấp nhận nó ngoài ngữ cảnh ban đầu.

Một số ví dụ khác nhau:

| Đối tượng bị phát lại | Kẻ tấn công muốn gì? | Những lớp bảo vệ liên quan |
| --- | --- | --- |
| Authorization response chứa `code` | Đăng nhập bằng response không thuộc flow browser hiện tại hoặc đổi code bị chặn bắt | `state`, PKCE, code one-time, redirect URI/client binding |
| Authorization code bị chặn bắt | Đổi code lấy access token tại token endpoint | **PKCE**, client authentication, code binding, code lifetime |
| ID Token cũ | Làm client chấp nhận một ID Token của request khác | **OIDC nonce**, ID Token validation, session/correlation binding |
| Access token bị đánh cắp | Gọi Resource Server thay chủ thể/token holder | Sender-constrained token, TLS, audience/scope/expiry, storage protection |
| Refresh token bị đánh cắp | Xin access token mới trong thời gian dài | Refresh rotation/reuse detection, sender-constraining, secure storage |
| Browser callback URL trong history | Thử xử lý lại code/state cũ | State consumption, authorization code one-time, expiry, PKCE |

**Không có một cơ chế “chống replay” duy nhất cho mọi hàng.** Chẳng hạn, `nonce` của OIDC không được Resource Server tự động dùng để từ chối một access token bị phát lại.

### 1.1. Phân biệt authorization CSRF và token theft

- **Login CSRF / authorization response injection:** attacker tìm cách đưa browser nạn nhân hoàn tất flow đăng nhập do attacker kiểm soát. Kết quả có thể là nạn nhân bị đăng nhập nhầm vào tài khoản của attacker hoặc ứng dụng liên kết nhầm identity.
- **Code interception:** attacker lấy được authorization code từ redirect hoặc từ một lỗ hổng khác; cố trao đổi nó trước client hợp lệ.
- **ID Token replay:** một ID Token từng hợp lệ được sử dụng lại ở ngữ cảnh xác thực khác.
- **Bearer token replay:** ai cầm token có thể sử dụng token ở API nếu không có sender binding và token vẫn hợp lệ.

Các tình huống trên có **điểm vào và ranh giới tin cậy khác nhau**. Vì thế Spring Security dùng nhiều yếu tố bảo vệ đồng thời.

## 2. Bảng so sánh state, PKCE và nonce

| Tiêu chí | `state` | PKCE | OIDC `nonce` |
| --- | --- | --- | --- |
| Chuẩn chính | OAuth 2.0 / security BCP | RFC 7636 / OAuth Security BCP | OpenID Connect Core |
| Giá trị phía client tạo | Opaque random state | Random `code_verifier` | Unique nonce |
| Được gửi trong authorization request? | Có | **`code_challenge`** và method | Có trong OIDC request khi sử dụng |
| Được đưa lại ở authorization response? | **Có**, `state` | Không trả verifier ở callback | Không phải callback parameter chuẩn của code flow |
| Được dùng ở token request? | Thường không | **`code_verifier`** | Không phải parameter đổi code chuẩn |
| Được đối chiếu ở đâu? | **Client/RP** với authorization request gốc | **Authorization Server** tại token endpoint | **Client/RP** với `nonce` claim của ID Token |
| Phòng vệ chính | Callback/request correlation, login CSRF | Code interception, unauthorized code exchange | ID Token replay/cross-request substitution |
| Có tự xác minh danh tính user? | Không | Không | Không; cần validation ID Token đầy đủ |
| Có ngăn access token bearer replay? | Không | Không | Không |
| Có thể tự bỏ nếu đã có cơ chế khác? | Không tùy tiện | Không tùy tiện | Tùy OIDC flow/chính sách; không bỏ nếu flow sử dụng |

**Câu cần nhớ:** `state` được **đối chiếu khi callback trở lại**, PKCE được **AS kiểm tra lúc đổi code**, còn `nonce` được **RP kiểm tra trong ID Token**. Cùng một browser flow nhưng ba điểm kiểm tra khác nhau.

### 2.1. Ai tin ai?

```text
state:
  RP tin dữ liệu request gốc trong repository/session của chính RP
  RP không tin "state" mới do callback tùy ý cung cấp

PKCE:
  AS ghi nhớ code_challenge gắn authorization code
  AS chỉ chấp nhận token request có code_verifier khớp

nonce:
  RP lưu ngữ cảnh nonce gắn authentication request
  RP xác minh nonce claim trong ID Token từ OP đã tin cậy
```

Bỏ qua một trong ba điểm kiểm tra sẽ làm yếu ranh giới tương ứng.

---

## 3. Toàn bộ sequence Authorization Code + PKCE + OIDC

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Browser
    participant RP as Spring Security OAuth2 Client
    participant Store as Authorization Request Store
    participant OP as OpenID Provider
    participant API as Resource Server

    Browser->>RP: GET /oauth2/authorization/company
    RP->>RP: Sinh state S, verifier V, challenge H(V), nonce N
    RP->>Store: Lưu request gốc + correlation context
    RP-->>Browser: 302 /authorize?state=S&code_challenge=H(V)&nonce=N
    Browser->>OP: Authorization request
    OP->>User: Xác thực + consent (khi cần)
    OP-->>Browser: Redirect /login/oauth2/code/company?code=C&state=S
    Browser->>RP: GET callback, code=C, state=S
    RP->>Store: Tìm/tiêu thụ request gốc theo browser + state
    alt Không tìm thấy / state sai
        RP-->>Browser: Login failure; không dùng code
    else Correlation hợp lệ
        RP->>OP: POST /token {code=C, code_verifier=V}
        OP->>OP: Kiểm tra code one-time, client, redirect URI, PKCE
        alt PKCE/code không hợp lệ
            OP-->>RP: OAuth2 error invalid_grant
            RP-->>Browser: Login failure
        else Token request hợp lệ
            OP-->>RP: Access Token + ID Token
            RP->>RP: Verify ID Token iss/aud/signature/exp/nonce
            alt ID Token không hợp lệ
                RP-->>Browser: Login failure
            else ID Token hợp lệ
                RP->>RP: Tạo Authentication
                RP-->>Browser: Session đăng nhập hợp lệ
                RP->>API: API call với access token đúng audience
            end
        end
    end
```

Đây là sơ đồ **logic bảo mật**, không biểu diễn mọi trường hợp phụ của các implementation. Ví dụ OIDC nonce có thể được Spring Security biểu diễn bằng những attributes nội bộ thay vì giữ nguyên một chuỗi theo mẫu minh họa.

## 4. PKCE: chống đánh cắp authorization code như thế nào?

PKCE là viết tắt của **Proof Key for Code Exchange** (RFC 7636). Trước khi browser đến OP, client tạo một **`code_verifier`** khó đoán, rồi tính **`code_challenge`**.

Với method khuyến nghị **`S256`**:

\[
\text{code\_challenge} = \operatorname{BASE64URL\_NO\_PADDING}(\operatorname{SHA256}(\operatorname{ASCII}(\text{code\_verifier})))
\]

Trong authorization request, client gửi **challenge**, không gửi verifier. Khi đổi authorization code lấy token, client gửi **verifier**.

### 4.1. Vì sao cần hai giá trị?

```text
Client:
  V = random code_verifier
  C = S256(V)

Front-channel via browser:
  GET OP /authorize?code_challenge=C&code_challenge_method=S256

Back-channel:
  POST OP /token
    grant_type=authorization_code
    code=AUTHORIZATION_CODE
    code_verifier=V

OP:
  Verify S256(V) == C attached to authorization code
```

Attacker chỉ chặn bắt authorization code hoặc thấy challenge **không dễ suy ra verifier** nếu verifier có entropy đủ mạnh.

### 4.2. Tham số PKCE và ranh giới truyền dữ liệu

| Tên | Xuất hiện ở đâu? | Có nên giữ bí mật? |
| --- | --- | --- |
| `code_verifier` | Client giữ, gửi trong token request | **Có**; không đưa vào browser callback/log |
| `code_challenge` | Authorization request qua browser | Không cần secret, nhưng phải gắn đúng authorization code |
| `code_challenge_method` | Authorization request | Thường là `S256` |
| Authorization code | Callback qua browser, token request | Credential ngắn hạn; bảo vệ, không log |
| Client secret | Client authentication tại token endpoint, nếu confidential client | **Có**; không gửi ra browser |

**Không có chuyện OP “tự đoán” verifier từ challenge.** Nó kiểm tra giá trị verifier client gửi lúc token exchange.

### 4.3. Verifier phải đủ ngẫu nhiên

Theo RFC 7636, `code_verifier`:
- Có độ dài **43 đến 128 ký tự**;
- Dùng ký tự không dành riêng (unreserved) như chữ cái, chữ số, dấu gạch ngang, dấu chấm, underscore, tilde;
- Phải khó đoán, được sinh bằng **CSPRNG**;
- Khuyến nghị sinh ít nhất **32 octets ngẫu nhiên** rồi Base64URL không padding.

Không dùng:
- Username hoặc email;
- Timestamp đơn thuần;
- Counter tuần tự;
- `Math.random()`;
- UUID có entropy không phù hợp làm cơ chế duy nhất nếu không kiểm chứng;
- Một verifier cố định dùng cho mọi lần login.

### 4.4. S256 hay plain?

PKCE có `plain` và `S256`. Với `plain`, challenge chính là verifier nên có thể bị lộ qua front-channel. **Ưu tiên `S256`**, và không tự fallback từ S256 sang plain vì OP từ chối nếu chưa xác định đúng hợp đồng và threat model.

Nếu OP không hỗ trợ S256, đó là tín hiệu cần xem lại mức an toàn của tích hợp; không coi việc tắt PKCE là workaround mặc định.

### 4.5. PKCE bảo vệ public client và confidential client

Một hiểu lầm là “client đã có client secret thì không cần PKCE”. Client authentication và PKCE giải quyết những vấn đề khác nhau:

- **Client authentication** xác minh client identity ở token endpoint.
- **PKCE** ràng buộc token request với authorization request đã tạo challenge.

OAuth 2.0 Security Best Current Practice khuyến nghị PKCE rộng rãi, bao gồm nhiều confidential client scenarios. Không bỏ PKCE chỉ vì backend có `client_secret`.

### 4.6. PKCE không tự ngăn mọi code injection

PKCE làm khó việc **đổi code bị chặn bắt nếu không có verifier**, nhưng client vẫn cần:
- Correlation state;
- Chính xác client/redirect URI;
- Gắn authorization code với đúng AS;
- Tránh authorization server mix-up;
- Kiểm tra response và OIDC token theo issuer.

Một attacker làm lộ verifier cùng authorization code có thể vượt lớp PKCE. Vì thế session/transport/storage security vẫn bắt buộc.

---

## 5. Code Java minh họa cách tạo PKCE S256

Đây là **ví dụ học thuật** để hiểu công thức. Trong Spring Security production, ưu tiên `OAuth2AuthorizationRequestCustomizers.withPkce()` và cơ chế lưu verifier của framework.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceExample {

    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceExample() {}

    public static String newCodeVerifier() {
        byte[] randomBytes = new byte[32]; // 256 bit
        RANDOM.nextBytes(randomBytes);

        // 32 bytes -> 43 ký tự Base64URL không padding.
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);
    }

    public static String s256CodeChallenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (java.security.NoSuchAlgorithmException e) {
            // SHA-256 là thuật toán chuẩn có sẵn trong Java SE.
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static void main(String[] args) {
        String verifier = newCodeVerifier();
        String challenge = s256CodeChallenge(verifier);

        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: " + challenge.length());

        // Không in verifier/challenge hoặc authorization URL thật
        // từ một phiên đăng nhập production vào console/log.
    }
}
```

**Điểm chính:**

- Sử dụng `SecureRandom`, không dùng random của UI.
- Base64URL **không padding**, không phải Base64 thường với `+`, `/`, `=`.
- SHA-256 nhận byte ASCII của verifier, vì verifier chỉ chứa ký tự ASCII hợp lệ.
- Challenge có thể công khai; verifier cần được bảo vệ.
- Mỗi authorization request mới phải có **verifier mới**.

### 5.1. Không phải code test verifier bằng cách so sánh raw strings

Sai:

```java
boolean valid = codeVerifier.equals(codeChallenge);
```

Với `S256`, đúng là OP phải tính lại **S256(verifier)** rồi so với challenge đã gắn authorization code. **Client không được tự tin rằng một phép so sánh tại browser đủ thay kiểm tra của OP**.

### 5.2. Authorization Server phải thực thi PKCE

Client gửi challenge không tự tạo an toàn nếu Authorization Server **bỏ qua verifier ở token endpoint**. OP/AS phải:
1. Lưu challenge và method với authorization transaction/code;
2. Yêu cầu verifier tương ứng trong token request;
3. Kiểm tra S256;
4. Từ chối nếu mismatch hoặc thiếu verifier khi code gắn PKCE;
5. Áp dụng code expiration, one-time use và client/redirect binding.

Khi gặp AS triển khai PKCE sai, cần sửa/đổi provider hoặc có quyết định security rõ, không tuyên bố “đã an toàn vì client có PKCE parameter”.

## 6. State: correlation và chống login CSRF

`state` là giá trị client gửi trong authorization request và nhận lại ở authorization response.

```text
Authorization request:
    response_type=code
    client_id=portal-client
    redirect_uri=https://app.example.test/login/oauth2/code/company
    state=3jV2y...random

Callback:
    code=C123
    state=3jV2y...random
```

Spring Security phải đối chiếu callback `state` với dữ liệu của request gốc được lưu trong `AuthorizationRequestRepository`.

### 6.1. Vì sao state cần gắn với browser/session?

Giả sử attacker khởi động login trong browser của chính mình, nhận một authorization response hợp lệ rồi cố đưa response đó vào browser nạn nhân. Nếu RP chỉ nhận `code` mà không kiểm tra correlation, ứng dụng có thể hoàn tất một login khác với ý định của nạn nhân.

```text
Attacker browser:
  start login -> state=S_attacker, code=C_attacker

Victim browser:
  no matching request/state in its own session

Attempted injected callback:
  /login/oauth2/code/company?code=C_attacker&state=S_attacker

Secure RP:
  lookup victim session for S_attacker -> no match
  reject callback
```

**State phải được kiểm tra trong ngữ cảnh client/browser đã bắt đầu flow**, không chỉ là một chuỗi hợp lệ về mặt hình thức.

### 6.2. State có cần là secret tuyệt đối?

State được đưa qua **front-channel**: authorization URL và callback URL. Vì thế nó có thể xuất hiện ở browser history hoặc proxy log, không nên coi là secret không bao giờ lộ.

Tính bảo vệ dựa trên:
- Giá trị khó đoán;
- Request gốc lưu trong store đáng tin cậy;
- Ràng buộc browser/session hoặc cơ chế tương đương đã phân tích threat model;
- Đối chiếu exact value;
- Hạn sử dụng và one-time consumption;
- Không chấp nhận callback thiếu hoặc sai state trong flow yêu cầu state.

**Không dùng state như access token** và không cấp quyền dựa trên việc thấy `state` trùng một format.

### 6.3. Cẩn trọng với việc nhúng URL vào state

Có dự án encode return URL hoặc tenant context vào state. Nếu tự làm:
- Không cho state chứa một URL redirect tùy ý rồi redirect user theo nó;
- Bảo vệ integrity và binding của metadata;
- Không đưa PII/secret vào URL;
- Có allowlist return paths;
- Có TTL và one-time use.

Trong Spring Security thông thường, **không cần tự encode toàn bộ session vào state**; repository lưu authorization request ở phía server là cách đơn giản hơn.

### 6.4. State khác CSRF token của POST form

CSRF token của `POST /logout` hoặc một form state-changing thuộc **Spring Security CSRF protection**. OAuth2 `state` bảo vệ authorization redirect flow.

Hai giá trị có thể cùng góp phần ngăn CSRF nhưng **không tự thay thế nhau**:
- OAuth2 state không phải token có thể gửi cho mọi form;
- CSRF token của form không tự thay trạng thái authorization request ở OIDC callback.

---

## 7. Nonce: ràng buộc OIDC ID Token với yêu cầu xác thực

OIDC có **ID Token**, khác với OAuth2 access token. Một ID Token chứa claims như:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "user-123",
  "aud": "portal-client",
  "iat": 1760000000,
  "exp": 1760000600,
  "nonce": "N-unique-value-from-request"
}
```

Trong ví dụ, timestamps và nonce là dữ liệu minh họa, không phải token thật.

Nếu client gửi `nonce` trong authentication request, OP phải trả giá trị tương ứng trong ID Token theo OIDC contract và RP phải xác minh nó.

### 7.1. Flow nonce

```text
RP:
  create nonce N
  store expected nonce for authentication request

Authorization request:
  nonce=N (hoặc representation do framework tạo đúng contract)

OP:
  issue ID Token including nonce claim corresponding to request

RP:
  validate ID Token signature / issuer / audience / expiry
  validate nonce matches expected value for this transaction
  accept Authentication only when all checks pass
```

Nếu attacker đưa một **ID Token cũ** từ giao dịch khác với nonce `N_old`, trong khi transaction hiện tại chờ `N_new`, RP phải từ chối.

### 7.2. Nonce trong OIDC code flow có bắt buộc không?

Theo OIDC Core:
- Trong **Authorization Code Flow**, `nonce` trong authentication request là **tùy chọn theo chuẩn**, nhưng nếu được gửi thì ID Token phải được kiểm tra đúng.
- Trong **Implicit Flow** và một số **Hybrid Flow**, nonce có yêu cầu bắt buộc của profile/flow.

Dù authorization code + PKCE là lựa chọn hiện đại, **không suy ra nonce vô dụng**. OIDC nonce là một lớp ràng buộc ID Token hữu ích, nhất là khi OP và Spring Security đã hỗ trợ tự động.

### 7.3. Không so sánh nonce bằng logic tự viết nếu framework có representation nội bộ

Một số framework tạo nonce ngẫu nhiên, lưu một representation trong authorization request attributes và gửi một representation dẫn xuất (ví dụ hash) tới OP. Khi callback, framework biết cách so sánh với ID Token claim.

Do đó, không viết:

```java
// KHÔNG NÊN: tự giả định cách lưu nonce nội bộ của Spring Security.
String storedNonce = request.getAttribute("nonce");
String returnedNonce = idToken.getClaimAsString("nonce");
if (storedNonce.equals(returnedNonce)) {
    // Cho đăng nhập ngay?
}
```

Đoạn này vừa có thể sai về representation, vừa bỏ qua ID Token signature/issuer/audience/expiry. **Ưu tiên OIDC validators mặc định của Spring Security**, không tái tạo logic nonce bằng đoạn so sánh tách rời.

### 7.4. Nonce không phải state

```text
state:
  authorization response <-> authorization request

nonce:
  ID Token <-> OIDC authentication request
```

State được trả trong **authorization response**. Nonce được trả trong **ID Token claim**, không phải một query parameter callback tùy ý mà RP tin.

### 7.5. Nonce cũng không thay kiểm tra các claims khác

Nonce đúng không chứng minh ID Token hợp lệ nếu:
- Chữ ký sai;
- `iss` là OP không được tin cậy;
- `aud` không khớp client;
- `exp` đã qua;
- `azp` cần kiểm tra nhưng không hợp lệ;
- JWT thuật toán không được chấp thuận;
- Token bị trộn từ client/provider khác.

**OIDC login chỉ thành công khi toàn bộ validation áp dụng đều thành công**.

---

## 8. Các bước bảo vệ của Spring Security Servlet

Một cấu hình đăng nhập OIDC cơ bản:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Để hoạt động, ứng dụng cần client registration OIDC hợp lệ. Spring Security phối hợp nhiều component:

| Component | Trách nhiệm |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Bắt đầu authorization request và redirect tới AS |
| `OAuth2AuthorizationRequestResolver` | Tạo request gồm state, redirect URI, scopes và PKCE/nonce khi được bật |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu authorization request/correlation qua browser redirect |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Implementation Servlet mặc định dùng HttpSession |
| `OAuth2LoginAuthenticationFilter` | Nhận callback, khôi phục authorization transaction và xác thực |
| `OAuth2LoginAuthenticationProvider` | Hỗ trợ OAuth2 code login |
| `OidcAuthorizationCodeAuthenticationProvider` | Xử lý OIDC code flow và ID Token validation |
| `ClientRegistrationRepository` | Cấu hình client/provider tin cậy |
| `OAuth2AccessTokenResponseClient` | Đổi authorization code lấy token theo grant |
| `JwtDecoder` / OIDC token validator | Xác minh JWT signature/claims theo provider |

**Không phải mọi component trên đều do ứng dụng phải tự tạo.** Spring Security cung cấp defaults phù hợp với các flow phổ biến. Tự thay filter/provider chỉ để “thêm một tham số” thường tăng rủi ro.

### 8.1. PKCE tự động trong các trường hợp mặc định

Ở Spring Security 6.x, client authorization infrastructure hỗ trợ PKCE và có logic bật trong những tình huống phù hợp, đặc biệt **public client** với `client-authentication-method: none`. Với confidential clients, có thể chủ động bật PKCE bằng customizer nếu OP hỗ trợ.

Không dựa vào giả định “có `spring-boot-starter-oauth2-client` là mọi registration đều dùng S256”. Hãy xác nhận request thực tế của từng registration trong môi trường test và chính sách hỗ trợ PKCE của AS.

### 8.2. OIDC nonce do framework phối hợp

Khi registration sử dụng scope `openid`, Spring Security OIDC Login có hỗ trợ nonce binding và ID Token verification theo flow. Hãy **để framework quản lý nonce và correlation metadata** thay vì thêm một nonce tùy ý vào URL rồi bỏ việc đối chiếu.

### 8.3. Repository là nơi liên hệ hai request HTTP

```text
GET /oauth2/authorization/company
    -> OAuth2AuthorizationRequest
       state=S, PKCE verifier in attributes, nonce context when used
    -> HttpSession authorization request repository

GET /login/oauth2/code/company?code=C&state=S
    -> repository loads/removes authorization request
    -> checks correlation
    -> token endpoint with verifier
    -> OIDC ID Token validation
```

Nếu browser không gửi lại cùng session cookie, hoặc session store không có request ban đầu, callback **không nên được chấp nhận**.

## 9. Bật PKCE tường minh bằng OAuth2AuthorizationRequestCustomizers

Một ứng dụng confidential client có thể chủ động thêm PKCE cho authorization code flow bằng API Spring Security:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PkceSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint ->
                    endpoint.authorizationRequestResolver(resolver)))
            .build();
    }
}
```

Khi resolver tạo authorization request cho một registration phù hợp, customizer:
- Sinh `code_verifier`;
- Tính `code_challenge` và chọn `S256`;
- Đặt public PKCE parameters vào authorization request;
- Lưu verifier trong metadata client-side của authorization request để token exchange dùng lại.

**Lưu ý:** ví dụ đặt resolver ở `/oauth2/authorization`, đúng path mặc định. Nếu ứng dụng đổi base URI, phải đồng bộ resolver, links và SecurityFilterChain. Không tự thay authorize URL sau khi resolver đã tạo request vì có thể làm lệch state/nonce/PKCE.

### 9.1. PKCE vẫn cần OP hỗ trợ

Nếu AS không hỗ trợ PKCE hoặc không thực hiện xác minh, thêm builder customizer chưa đủ để chống code interception. Cần xác minh AS thực sự từ chối token request có verifier sai hoặc thiếu.

### 9.2. Không gọi withPkce bằng cách thay state/nonce

`withPkce()@@ chuyên về PKCE. Nó **không có nghĩa state bị bỏ**, cũng **không phải một nonce customizer**. Đừng viết resolver mới và bỏ `state`/OIDC security attributes chỉ vì muốn bật PKCE.

### 9.3. PKCE cho confidential client có lợi gì?

Dù client secret được dùng tại token endpoint, việc ràng buộc code với verifier cụ thể vẫn giúp giảm rủi ro code injection/interception trong những điều kiện threat model được PKCE bao phủ. Giữ cả client authentication và PKCE khi OP cho phép.

---

## 10. application.yml minh họa OIDC + PKCE

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
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
          company:
            issuer-uri: https://id.example.test/realms/company
```

`issuer-uri` cho phép Spring Security tải metadata tin cậy từ OP khi được hỗ trợ. Authorization endpoint, token endpoint, JWK Set URI và chính sách PKCE phải được provider hỗ trợ nhất quán.

Ở cấu hình trên:
- `openid` là scope OIDC; ứng dụng mong đợi ID Token.
- `authorization_code` là grant chính, khác `refresh_token`.
- `client_secret_basic` là client authentication method, **không thay PKCE**.
- `redirect-uri` phải trùng URI được đăng ký tại OP.
- `client-secret` là bí mật backend, không được đưa ra browser.
- Resolver với `withPkce()@@ trong mục 9 là cách bật PKCE tường minh nếu cần.

### 10.1. Với public client thì sao?

Một public client không thể giữ client secret. Spring Security có cấu hình client authentication `none`; kết hợp Authorization Code + PKCE theo cấu hình/framework. Không đưa client secret giả vào SPA/mobile app hoặc tin rằng code verifier trong frontend luôn tuyệt đối bí mật trước XSS.

### 10.2. Browser-based app và BFF

Khi ứng dụng là **Backend-for-Frontend (BFF)**:
- Browser giữ session cookie của BFF;
- Backend giữ access/refresh tokens và PKCE verifier server-side;
- Authorization Code callback được backend xử lý;
- Browser không cần tiếp xúc với refresh token.

BFF giảm bề mặt lộ token ở browser nhưng vẫn cần CSRF/cookie protection, state, PKCE và OIDC nonce/ID Token validation.

---

## 11. Lưu state, code_verifier và nonce ở đâu?

Với Spring Security Servlet, **`HttpSessionOAuth2AuthorizationRequestRepository`** thường là repository mặc định để giữ `OAuth2AuthorizationRequest` qua redirects.

Mô hình logic:

```text
Browser cookie:
  JSESSIONID = opaque-session-id

Server HttpSession:
  pending OAuth2AuthorizationRequest:
    registrationId  = company
    state           = S
    redirectUri     = https://app.example.test/login/oauth2/code/company
    scopes          = [openid, profile]
    attributes      = [PKCE verifier, OIDC nonce context, ...]
    additionalParams = [code_challenge, code_challenge_method, nonce, ...]
```

Không giả định tất cả phiên bản Spring Security lưu cùng **tên key** hoặc representation của nonce trong attributes; framework có thể có xử lý nội bộ khác nhau.

### 11.1. Tại sao không đưa verifier vào cookie plaintext?

Nếu ứng dụng tự tạo cookie:

```text
Set-Cookie: code_verifier=<secret>
```

rồi gửi verifier từ browser mà không có integrity/session binding thích hợp, rủi ro lộ hoặc bị can thiệp tăng lên. Với Servlet confidential client, lưu trong server-side authorization request repository là cách thực dụng và phù hợp hơn.

### 11.2. State phải khớp phiên của browser

Cookie định danh session RP giúp callback tìm đúng request gốc. Nếu cookie khác/mất:

```text
Start login:
  Session A -> state S

Callback:
  Session B -> state S, but no matching original request
```

Hành vi an toàn: **từ chối**, yêu cầu bắt đầu lại flow; không đọc global map theo state mà bỏ qua ranh giới session.

### 11.3. Không đặt timeout vô hạn

Pending authorization request là một giao dịch ngắn hạn. Nếu tự làm repository/database:
- Đặt TTL;
- Giới hạn số flow pending;
- Xóa sau khi hoàn tất/tiêu thụ;
- Bảo vệ dữ liệu lưu trữ;
- Xử lý concurrency;
- Không lưu authorization request raw vào client-side localStorage.

Session timeout dài không làm authorization code/nonce vô hạn hiệu lực; AS vẫn có code lifetime và các ràng buộc riêng.

### 11.4. Session fixation và cookie

Khi user đăng nhập thành công, Spring Security có cơ chế session fixation protection và security context persistence tương ứng. Nhưng state/nonce flow diễn ra **trước khi user đã authenticated**, nên việc tạo/giữ session pending cần được bảo vệ:
- HTTPS;
- `Secure` và `HttpOnly` cookie attributes trong production;
- `SameSite` tương thích OIDC callback;
- Cookie domain/path chính xác;
- Session ID không xuất hiện trong URL/log;
- Không cho attacker cố định session ID của nạn nhân.

---

## 12. Callback phải được dùng một lần và fail closed

Một quy trình an toàn:

```text
GET /login/oauth2/code/company?code=C&state=S
        |
        v
Load matching authorization request from session
        |
        +-- None -> reject callback
        |
        v
Confirm state matches and transaction context valid
        |
        v
Remove/consume pending request
        |
        v
Exchange C with correct verifier V
        |
        +-- invalid_grant -> reject
        |
        v
Validate ID Token (+ nonce when used)
        |
        +-- invalid token -> reject
        |
        v
Create Authentication
```

Thao tác **remove** authorization request hạn chế việc client xử lý callback lặp lại. Tuy nhiên **AS cũng phải áp dụng one-time authorization code**; xóa state ở client không phải thay thế cho code one-time ở AS.

### 12.1. Replay callback URL

Lần đầu:

```text
/login/oauth2/code/company?code=C1&state=S1
```

đã hoàn tất; request gốc bị tiêu thụ. Nếu cùng URL quay lại:

```text
/login/oauth2/code/company?code=C1&state=S1
```

client không nên tìm thấy giao dịch pending để xác thực lại. Nếu token endpoint vẫn bị gọi, AS cũng phải từ chối code đã dùng.

**Không viết logic fallback “state đã dùng nhưng code vẫn còn thì cho qua”**.

### 12.2. Callback error cũng cần correlation chính xác

OP có thể trả:

```text
/login/oauth2/code/company?error=access_denied&state=S1
```

Dù là lỗi, đây vẫn là một phản hồi của authorization flow. Không dùng raw `error_description` để quyết định user nào đang đăng nhập, và không bỏ state binding chỉ vì OP trả error.

### 12.3. Từ chối khi đã mất request

Một browser giữ callback URL từ hôm trước không còn HttpSession hoặc pending request. Không “khôi phục bằng code” và không truy vấn một global collection theo raw state thiếu session binding; cho người dùng bắt đầu flow mới.

---

## 13. Nhiều tab và các authorization flows song song

Một browser có thể bắt đầu hai flows:

```text
Tab A -> Company, state=A, verifier=V_A, nonce=N_A
Tab B -> Partner, state=B, verifier=V_B, nonce=N_B

Callback B về trước
Callback A về sau
```

Nếu repository **chỉ có một slot pending request trong session**, flow B có thể ghi đè A. Khi callback A đến, state mismatch. Đây có thể là **giới hạn storage/concurrency**, không phải do AS gửi sai token.

### 13.1. Không giải quyết multi-tab bằng cách bỏ so khớp

Sai:

```text
Nếu state không match -> lấy request gần nhất -> thử code_verifier gần nhất
```

Điều này có thể trộn code/verifier/nonce giữa các requests hoặc providers, mở đường cho login CSRF, account mix-up và authorization failures.

Nếu sản phẩm cần multi-tab/parallel authorization:
- Kiểm tra behavior repository của Spring Security version cụ thể;
- Thiết kế store theo **(session, state)** hoặc tương đương;
- TTL và maximum pending requests rõ ràng;
- Remove đúng entry;
- Atomic update để tránh lost write;
- Không cho callback chọn session tùy ý;
- Tránh để PKCE verifier/nonce bị ghi đè bởi flow khác.

### 13.2. Nhiều providers không được dùng một bộ giá trị chung

Không tạo `state` hoặc `code_verifier` global dùng chung cho Company và Partner. Mỗi authorization request phải có context riêng; provider identity/issuer phải được ràng buộc đúng request.

### 13.3. Phân loại lỗi khi multi-tab

Nếu callback A có state mismatch nhưng OP A vẫn khỏe, không đánh dấu OP A là unavailable. Điều tra browser session, cookie, repository model và concurrency trước khi kết luận provider lỗi.

## 14. Nhiều provider: chống authorization server mix-up

Một hệ thống có thể tích hợp:

```text
company -> issuer https://id.company.example.test
partner -> issuer https://id.partner.example.test
```

Mỗi provider có:
- Authorization endpoint;
- Token endpoint;
- Client ID và client authentication;
- Redirect URI/policy;
- JWKS;
- Issuer;
- ID Token validation;
- State/nonce/PKCE context của từng flow.

**Authorization Server mix-up** là nhóm tấn công/lỗi khi client nhầm AS đã bắt đầu flow và gửi code/token tới sai endpoint hoặc tin nhầm response của provider khác.

### 14.1. State một mình không xác minh issuer

`state` liên kết callback với request đã lưu, nhưng client còn cần xác định **request gốc thuộc issuer/provider nào**. Một implementation nhiều AS phải ràng buộc authorization response với đúng AS, không chỉ nhìn path hoặc input do browser cung cấp.

Những cơ chế giảm rủi ro gồm:
- `ClientRegistration` cố định/trusted;
- Token endpoint mapping chính xác;
- Authorization response issuer identification (ví dụ `iss` theo RFC 9207 khi AS hỗ trợ);
- Distinct redirect URIs khi phù hợp;
- ID Token issuer/audience validation;
- Không lấy token endpoint từ query parameter;
- Không đổi registration sau khi callback đã đến.

### 14.2. PKCE không chứng minh issuer

Một verifier có thể giúp bảo vệ code exchange, nhưng không chứng minh “đây chắc chắn là OP Company” nếu client gửi authorization code và verifier tới **endpoint sai**.

AS endpoint selection phải đến từ registration/context tin cậy, không từ attacker-controlled callback parameter.

### 14.3. Nonce không thay issuer

ID Token có nonce khớp nhưng `iss` không đúng configured OP vẫn phải bị từ chối. Không chấp nhận ID Token từ một nhà cung cấp khác chỉ vì subject hoặc email giống nhau.

### 14.4. Subject identity

Định danh user OIDC ít nhất là:

```text
(issuer, subject)
```

Không dùng `sub` đơn lẻ hoặc email làm global identity key giữa các providers. Đó là vấn đề account mix-up quan trọng mà state/nonce/PKCE không tự giải quyết ở tầng nghiệp vụ.

---

## 15. PKCE, state và nonce còn chống được gì khi attacker có những thứ khác?

| Attacker kiểm soát/có được | State giúp gì? | PKCE giúp gì? | Nonce giúp gì? | Còn cần gì? |
| --- | --- | --- | --- | --- |
| Chỉ biết authorization code | Ràng buộc callback | Khó đổi code nếu không có verifier | ID Token binding sau exchange | Code one-time, AS binding |
| Có callback URL từ browser history | Bị từ chối khi transaction không còn pending/không cùng session | Verifier không nằm trong URL | ID Token đúng request | Session binding, TTL, log redaction |
| Có code + challenge | Correlation vẫn cần | Challenge không cho suy ra verifier với S256 | Không giải quyết code exchange | CSPRNG, TLS, protected verifier |
| Có code + verifier | Vẫn cần state/callback binding | PKCE có thể bị vượt | Bảo vệ ID Token use nếu khác request | Client authentication, AS one-time/redirect binding |
| Có ID Token cũ | Không dùng để validate ID Token trực tiếp | Không tự chặn ID Token replay | Có thể từ chối nonce cũ trong giao dịch mới | Signature/iss/aud/exp validation |
| Có access token bearer còn hạn | Không | Không | Không | DPoP/mTLS, expiry, scope/audience, secure storage |
| Có refresh token | Không trực tiếp | Không trực tiếp | Không trực tiếp | Rotation, reuse detection, sender binding |
| Kiểm soát sai token endpoint URL | Không giải quyết hết | Có thể rò code/verifier tới endpoint sai | Không giải quyết hết | Trusted registration, issuer/mix-up protection |
| XSS trong SPA | Có thể bị ảnh hưởng session/browser | Verifier có thể bị đánh cắp | Nonce có thể bị lộ/điều khiển | CSP, XSS defense, BFF/token containment |
| Có client secret | Không tự bảo vệ callback | Thêm rào cản code replay | Không thay ID Token validation | Secret rotation, least privilege |

**Threat model thực tế quan trọng hơn việc chỉ kiểm tra “có đủ ba parameter trong URL không”.**

## 16. Access token replay là bài toán khác

Bearer access token thường có thuộc tính: **ai cầm token hợp lệ có thể gọi API theo quyền của token**.

```text
Attacker steals access token T
        |
        v
GET https://api.example.test/v1/report
Authorization: Bearer T
        |
        v
Resource Server quyết định có chấp nhận T không
```

Ở bước đó Resource Server thường không nhìn thấy:
- `state` của login;
- `code_verifier`;
- `nonce` của ID Token.

Vì vậy, không thể nói “đã dùng PKCE và nonce thì access token không thể bị replay”.

### 16.1. Biện pháp giảm bearer token replay

- **TLS/HTTPS** toàn bộ đường truyền;
- Không để token trong URL query;
- Không log Authorization header hoặc token response;
- Lưu token ở backend hoặc secure store phù hợp;
- Access token lifetime hợp lý;
- Scope và audience tối thiểu;
- Resource Server xác minh issuer, audience, signature/expiry hoặc introspection;
- Có revocation/token lifecycle policy;
- Cân nhắc **sender-constrained access tokens** như DPoP (RFC 9449) hoặc OAuth 2.0 mTLS (RFC 8705);
- Bảo vệ XSS/CSRF/session nếu browser-based app.

### 16.2. DPoP là gì?

**DPoP (Demonstrating Proof of Possession)** ràng buộc token với một cặp khóa của client và yêu cầu proof khi gọi API. Resource Server xác minh DPoP proof, method/URI, thời gian, unique identifier và key binding theo chuẩn.

DPoP còn có cơ chế chống replay **của proof** riêng, thường qua `jti`, thời gian và nonce khi AS/RS yêu cầu.

**DPoP nonce khác OIDC nonce.** Không dùng OIDC ID Token nonce làm DPoP proof nonce, dù cùng tên `nonce`.

### 16.3. mTLS sender-constrained access token

Trong mô hình OAuth mTLS, token có thể được ràng buộc với certificate client. Resource Server kiểm tra chứng chỉ khi nhận token; kẻ tấn công chỉ có token nhưng không có private key/certificate phù hợp khó sử dụng lại.

Cách triển khai phụ thuộc AS, RS và hạ tầng. Spring Security OAuth2 Client không tự làm mọi token thành sender-constrained chỉ vì bạn bật PKCE.

### 16.4. Refresh token rotation

Để giảm replay của refresh token, OP có thể phát `R2` khi client dùng `R1`, vô hiệu hóa R1 và phát hiện reuse.

```text
R1 -> refresh -> A2 + R2
R2 -> refresh -> A3 + R3

Attacker retry R1:
  AS detects reuse / invalid_grant
  may revoke token family according to policy
```

Refresh token rotation cần xử lý concurrency cẩn thận ở client vì hai requests cùng refresh một token có thể tạo false reuse/mất phiên.

---

## 17. ID Token replay và validation đầy đủ

Một ID Token có thể là JWT đã ký, nhưng **JWT signature hợp lệ không có nghĩa token thuộc login flow hiện tại**.

Client cần kiểm tra:
- **`iss`**: issuer chính xác của OP đã đăng ký;
- **`aud`**: client ID của ứng dụng có trong audience;
- **`azp`**: authorized party khi điều kiện OIDC yêu cầu;
- **`exp`** và các thời gian;
- **Signature**: thuật toán/keys tin cậy đúng OP;
- **`nonce`**: khi được gửi/flow yêu cầu, phải khớp expected nonce;
- Các ràng buộc OIDC khác phù hợp response type/flow;
- **`sub`** của UserInfo phải khớp ID Token nếu dùng UserInfo.

### 17.1. Vì sao không chấp nhận raw ID Token từ client browser?

Một endpoint tùy ý:

```http
POST /api/login
Content-Type: application/json

{"id_token":"JWT_FROM_BROWSER"}
```

không tự trở thành OIDC Authorization Code Login chỉ vì JWT có chữ ký đúng. Nó có thể thiếu state/nonce/transaction context, và token có thể được phát hành cho một client khác.

Nếu hệ thống xây một login/token-exchange flow riêng, phải áp dụng trust model/nonce/audience/issuer/anti-replay tương ứng, thay vì tự parse JWT rồi tạo Authentication không kiểm chứng.

### 17.2. Nonce đúng không cho phép bỏ qua expiry

Một ID Token cũ có nonce trùng vì verifier/nonce bị tái sử dụng hoặc transaction storage sai vẫn phải tuân thủ expiration và các checks khác. **Tất cả validation có tính kết hợp**, không phải OR.

### 17.3. c_hash và at_hash trong OIDC

Một số OIDC flows, đặc biệt **Hybrid/Implicit**, có claims `c_hash` hoặc `at_hash` để ràng buộc authorization code/access token với ID Token theo OIDC Core.

Đây là **các cơ chế bổ sung** cho flow tương ứng, không đồng nghĩa với PKCE `code_challenge`:
- `c_hash` được tính từ authorization code theo thuật toán quy định;
- `at_hash` được tính từ access token;
- PKCE challenge là hash của **code_verifier**;
- State là correlation string từ authorization request;
- Nonce là claim binding authentication request.

Không lấy công thức PKCE S256 áp vào `c_hash` hoặc ngược lại. Với Authorization Code Flow hiện đại, ưu tiên framework OIDC validations thay vì tự xây validation cho những response types không sử dụng.

---

## 18. Spring Security Reactive WebFlux: bản đối chiếu

Trên WebFlux, cùng giao thức nhưng lớp API khác:

| Servlet | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |
| `AuthorizationRequestRepository` | `ServerAuthorizationRequestRepository` |
| `OAuth2AuthorizationRequestRedirectFilter` | `OAuth2AuthorizationRequestRedirectWebFilter` |
| `OAuth2LoginAuthenticationFilter` | Reactive OAuth2 code login filters/converters |
| Blocking result | Reactor `Mono` |

Ví dụ SecurityWebFilterChain cơ bản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Spring Security WebFlux dùng `ServerOAuth2AuthorizationRequestResolver` và reactive repository để tạo/lưu/correlate authorization request. Nếu muốn tùy chỉnh PKCE hoặc nonce, phải dùng đúng **Reactive extension points**, không copy nguyên `DefaultOAuth2AuthorizationRequestResolver` của Servlet vào `ServerHttpSecurity`.

### 18.1. Reactive save/load/remove phải được compose

```java
Mono<Void> saved =
    repository.saveAuthorizationRequest(authRequest, exchange);
```

Chỉ tạo `Mono` rồi bỏ qua **không bảo đảm request được lưu**. Framework chuẩn compose publisher trước khi redirect.

```java
// Ý tưởng đúng:
return repository.saveAuthorizationRequest(authRequest, exchange)
    .then(redirectToProvider());
```

`redirectToProvider()` là pseudocode method trả `Mono<Void>`, không phải API có sẵn. Không gọi `.block()` trên event loop.

### 18.2. WebSession và nhiều instances

Nếu auth flow bắt đầu ở node A rồi callback tới node B, cần WebSession store phù hợp, ví dụ Spring Session/Redis, hoặc deployment strategy đã được kiểm chứng. Mất session ⇒ mất state/PKCE verifier/nonce context ⇒ **reject callback**.

### 18.3. Không tự coi PKCE là thay cho WebSession

Dù OP kiểm tra PKCE, RP vẫn phải liên hệ callback với authorization request gốc và đúng principal/browser. Không bỏ state handling chỉ vì Reactive client có PKCE.

## 19. Reverse proxy, cookie SameSite và lỗi correlation

Một môi trường production:

```text
Browser https://app.example.test
    |
    v
Ingress / TLS termination
    |
    v
Spring Boot http://app-internal:8080
```

Nếu `redirect_uri` được dựng thành `http://app-internal:8080`, OP có thể từ chối `redirect_uri_mismatch` hoặc callback trở lại khác origin, làm mất cookie.

### 19.1. Forwarded headers

Spring Boot có thể cần:

```yaml
server:
  forward-headers-strategy: framework
```

Chỉ sử dụng nếu proxy tin cậy **lọc/ghi đè Forwarded/X-Forwarded-* headers**. Không tin raw `X-Forwarded-Host` từ internet để tạo redirect URI.

### 19.2. Cookie SameSite

Trong OIDC Authorization Code Flow phổ biến, OP redirect browser bằng **top-level GET** về callback. Cookie `SameSite=Lax` thường tương thích trong trường hợp này.

Với `response_mode=form_post` (cross-site POST), Lax có thể khiến browser không gửi session cookie. Khi đó callback không tìm thấy state/verifier/nonce context.

**Không “chữa” bằng cách tắt state validation.** Cần kiểm tra response mode/CSRF/cookie policy và browser behavior. Với SameSite=None, trình duyệt hiện đại thường yêu cầu Secure; quyết định phải dựa trên threat model.

### 19.3. Session timeout

Nếu user mất thời gian dài ở OP:
- Pending authorization request có thể hết hạn;
- Cookie/session ID có thể bị thay;
- Callback state không còn khớp.

Đúng là báo phiên đăng nhập hết hạn và bắt đầu flow mới. Không nới lỏng correlation để nhận URL callback cũ.

---

## 20. Đừng làm lộ dữ liệu bảo mật qua log

Authorization redirect/callback có thể chứa:
- `code`;
- `state`;
- `code_challenge`;
- `nonce`;
- Provider error descriptions.

Token endpoint request có:
- `code_verifier`;
- `client_secret` hoặc client assertion;
- Authorization code;
- Refresh token.

Token endpoint response có:
- Access token;
- ID Token;
- Refresh token.

**Không log nguyên request/response body và headers** cho các endpoints này trong production.

### 20.1. Logging tối thiểu

Ví dụ event:

```json
{
  "event": "oidc_login_flow",
  "registration_id": "company",
  "phase": "callback_validation",
  "outcome": "state_mismatch",
  "trace_id": "internal-correlation-id"
}
```

Đây là schema của ứng dụng, không phải log mặc định của Spring Security. Không sử dụng raw OAuth2 state như trace ID.

### 20.2. Không in nonce dù “không phải secret tuyệt đối”

Nonce được gửi qua browser, nhưng nó vẫn là correlation context. Logging raw nonce giúp liên kết thông tin giao dịch một cách không cần thiết, tăng khả năng lộ qua telemetry. Chỉ log event category.

### 20.3. Tránh query string trong access logs

Request có thể là:

```text
/login/oauth2/code/company?code=SECRET_CODE&state=S123
```

Web server, reverse proxy, CDN và APM đều có thể ghi path/query. Cần redaction cho code, state và các fields nhạy cảm. Không gửi callback URL nguyên vẹn vào analytics hoặc error reports.

### 20.4. Không expose authorized client trong JSON

Một controller debug:

```java
// KHÔNG NÊN trả đối tượng chứa access/refresh token.
@GetMapping("/debug/token")
public OAuth2AuthorizedClient debug() { ... }
```

Có thể làm lộ tokens. Dùng metadata đã lọc (registrationId, token expiresAt nếu policy cho phép) và bảo vệ endpoint chẩn đoán.

## 21. Các sai lầm thiết kế và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Dùng `state` cố định | Correlation có thể đoán/tái sử dụng | Tạo state khó đoán cho từng flow |
| Dùng verifier cố định | PKCE mất tính unique | CSPRNG, verifier mới mỗi request |
| Dùng `plain` không có lý do | Verifier lộ qua challenge | Ưu tiên S256 |
| Gửi `code_verifier` trong authorize URL | Tiết lộ bí mật PKCE qua browser | Chỉ gửi challenge |
| Gửi verifier qua callback query | Lộ verifier và phá ranh giới token request | Giữ server-side |
| Lưu state/verifier trong JS localStorage không có bảo vệ | XSS có thể lấy credentials | BFF/server-side session khi phù hợp |
| Không lưu authorization request | Không có dữ liệu so sánh state/nonce | Repository tin cậy |
| Callback thiếu state vẫn cho qua | Login CSRF/injection | Fail closed |
| Callback đã xử lý vẫn dùng lại | Replay/login mix-up | Remove pending state, code one-time |
| Dùng nonce như state duy nhất mà không phân tích flow | Bỏ callback correlation | Dùng đúng framework/BCP |
| Chỉ xem nonce mà bỏ ID Token signature | Token giả vẫn được tin | Verify signature/iss/aud/exp |
| Bỏ nonce validation khi đã gửi nonce | ID Token replay risk | Giữ OIDC validation |
| Lấy ID Token từ provider A dùng cho B | Mix-up/identity confusion | Issuer-specific trust |
| Dùng email để liên kết users các OP | Account takeover/mix-up | (issuer, subject) + linking policy |
| Dùng PKCE thay client authentication | Confidential client không được xác thực đúng | Cả hai khi áp dụng |
| Tự fallback S256 → plain | Làm yếu protection | Kiểm tra OP support, không downgrade âm thầm |
| Xử lý `invalid_grant` bằng retry vô hạn | Authorization code one-time, rate limit | New flow/controlled recovery |
| Timeout OP ⇒ bỏ state check | Authentication bypass | Sửa availability/session |
| Chỉ disable CSRF để OIDC login hoạt động | Tăng rủi ro các form và logout | Cấu hình CSRF/endpoint hợp lý |
| Chỉ lưu một pending flow khi cần multi-tab | State/verifier/nonce ghi đè | Repo keyed by session+state |
| Callback trên node khác thiếu session store | Correlation thất bại | Shared session/persistence |
| Access token bị lộ nhưng nghĩ PKCE đủ bảo vệ | Bearer replay tại API | Sender-constrained token và token hygiene |
| Refresh token bị lấy cắp nhưng chỉ tăng nonce | Không chặn refresh replay | Rotation/reuse detection và storage |
| Log query callback | Lộ code/state | Redact logs/APM |
| Cho user chọn token endpoint | Credential exfiltration/SSRF | Trusted ClientRegistration và allowlist |
| XSS làm mất PKCE security nhưng không xử lý | Browser context bị chiếm | CSP, input sanitization, secure architecture |

---

## 22. Phân tích các trường hợp tấn công

### Tình huống A — Attacker chỉ lấy được authorization code

Attacker thấy `code=C` trong một callback bị rò rỉ nhưng **không có `code_verifier`**.

**PKCE giúp gì?**

> AS đã gắn `code_challenge=S256(V)` với code. Khi attacker gọi token endpoint mà thiếu V, token request bị từ chối. Client authentication và các binding khác vẫn cần theo flow.

### Tình huống B — Attacker có code và code_challenge

Attacker thấy code và public challenge trong browser URL.

**Có suy ra verifier không?**

> Với S256 và verifier đủ entropy, việc suy ra V từ SHA-256 challenge là không khả thi trong mô hình bảo mật giả định. Không dùng `plain` hoặc verifier yếu.

### Tình huống C — Authorization response bị chèn vào browser khác

Attacker khởi động flow có `state=S_A` rồi gửi callback URL cho nạn nhân.

**State giúp gì?**

> Nạn nhân không có authorization request tương ứng trong session. Client từ chối callback; không xác thực theo code của attacker.

### Tình huống D — State bị mất do cookie

Người dùng bắt đầu login, rồi callback không gửi `JSESSIONID`.

**Có nên tự chấp nhận code nếu PKCE vẫn bật?**

> Không. Client phải tìm được authorization request/correlation context gốc; cần sửa SameSite, cookie domain/path, session persistence hoặc bắt đầu flow mới.

### Tình huống E — ID Token hợp lệ nhưng thuộc login cũ

Attacker đưa ID Token có chữ ký đúng, `iss` đúng, `exp` còn hạn, nhưng nonce của request khác.

**Nonce giúp gì?**

> Khi RP chờ nonce của giao dịch hiện tại, token nonce cũ không khớp nên bị từ chối. Nhưng signature/issuer/audience/expiry vẫn phải được kiểm tra song song.

### Tình huống F — Nonce đúng nhưng issuer sai

ID Token có nonce khớp nhưng `iss` thuộc OP khác.

**Có được đăng nhập không?**

> Không. Nonce không thay issuer validation. Phải từ chối ID Token không thuộc provider đã đăng ký cho flow.

### Tình huống G — Access token bị lấy cắp

Token T đã cấp hợp lệ, attacker có T và gọi API.

**PKCE/state/nonce có giúp trực tiếp không?**

> Không. Resource Server thường không nhận các giá trị đó. Cần token lifetime/audience/scope/TLS/storage và sender-constrained token khi phù hợp.

### Tình huống H — Authorization code bị dùng lần thứ hai

Client đã đổi code C thành token, sau đó có request đổi lại cùng code C.

**Ai phải từ chối?**

> Authorization Server phải thực thi **code one-time use** và thời hạn. Client cũng phải tiêu thụ authorization request ban đầu; không dựa vào state removal như cơ chế duy nhất.

### Tình huống I — Client không gửi code_verifier

Authorization request có PKCE challenge, nhưng token request không có `code_verifier`.

**Kết quả mong đợi?**

> AS từ chối, thường là `invalid_grant` theo xử lý lỗi phù hợp. Không sửa bằng cách tắt PKCE trên token exchange.

### Tình huống J — Dùng code_verifier của tab khác

Tab A tạo verifier V_A, tab B tạo V_B. Callback A dùng nhầm V_B.

**Kết quả?**

> PKCE mismatch; không nên cố “thử lần lượt tất cả verifiers”. Cần repository lưu mỗi flow độc lập.

### Tình huống K — Đổi provider token endpoint từ query parameter

App có Company và Partner, callback nhận `provider=partner` từ browser và gửi Company code đến Partner token endpoint.

**Rủi ro?**

> Authorization server mix-up, rò code/verifier/client credentials và trust confusion. Token endpoint phải đến từ registration/context được lưu tin cậy, không phải raw callback input.

### Tình huống L — Nonce bị dùng cho đăng xuất OIDC

Developer muốn dùng nonce của ID Token như `state` cho RP-Initiated Logout.

**Có nên không?**

> Không tự động. OIDC login nonce và logout-state correlation là hai giao dịch khác nhau. Nếu logout callback cần state, hãy thiết kế riêng theo logout spec.

### Tình huống M — Refresh token rotation chạy đồng thời

Hai requests cùng refresh R1; request thứ nhất nhận R2, request thứ hai bị `invalid_grant`.

**Đây có phải PKCE lỗi?**

> Không. Đây là concurrency của refresh-token lifecycle. Cần serialized refresh/locking/versioning và policy xử lý rotation/reuse detection phù hợp.

### Tình huống N — DPoP proof bị replay

Resource Server yêu cầu DPoP; attacker chép lại một proof đã dùng.

**OIDC nonce có ngăn không?**

> Không. DPoP dùng proof-specific `jti`, timestamp và có thể DPoP nonce được AS/RS yêu cầu. Không trộn với OIDC authentication nonce.

### Tình huống O — Authorization endpoint không thể truy cập

OP timeout trước khi redirect về callback.

**Có nên bỏ state trong những lần sau?**

> Không. Availability và correlation là hai vấn đề khác. Cho user thử lại/new flow với timeout/backoff phù hợp; không giảm security để xử lý OP outage.

### Tình huống P — Hai OP có cùng subject string

Company và Partner đều phát `sub="42"`.

**Có được coi cùng user không?**

> Không. Sử dụng tuple **(issuer, subject)** và account linking policy. State/nonce không tự chứng minh hai accounts thuộc cùng một người.

---

## 23. Thiết kế các kiểm thử quan trọng

Trong một dự án Spring Security thật, nên có kiểm thử tích hợp với **mock Authorization Server/OIDC test provider** để xác nhận behaviors. Đây là các **kịch bản học tập**, không phải yêu cầu chạy test của repository trong bước tạo bài.

### 23.1. PKCE tests

| Test | Setup | Kết quả mong đợi |
| --- | --- | --- |
| S256 request | Flow PKCE enabled | Authorize URL có `code_challenge` + `code_challenge_method=S256` |
| Verifier generation | Hai flows riêng | Verifiers khác nhau, đủ entropy/length |
| Token request | Callback đúng flow | Token endpoint nhận đúng `code_verifier` |
| Wrong verifier | Đổi code với V khác | AS trả lỗi; login thất bại |
| Missing verifier | Code đã gắn challenge | AS từ chối |
| Plain downgrade | OP yêu cầu plain | Client không tự downgrade âm thầm |
| Intercepted code | Attacker có code nhưng không verifier | Không đổi được token |

### 23.2. State tests

| Test | Setup | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | Callback đúng `state`/session | Flow tiếp tục |
| Wrong state | Callback thay `state` | Từ chối |
| Missing state | Không có state trên callback | Từ chối nếu flow đòi state |
| Wrong session | Callback từ browser khác | Không tìm request; từ chối |
| Session timeout | Pending request expired | Không reuse callback |
| Replay | Gửi callback sau khi đã dùng | Không hoàn tất lần hai |
| Multi-tab | Hai pending flows | Không trộn state/verifier/nonce |
| Unknown registration | Callback URL/provider sai | Không lấy token từ OP không tin |

### 23.3. Nonce & ID Token tests

| Test | Setup | Kết quả mong đợi |
| --- | --- | --- |
| Matching nonce | ID Token từ request đúng | Qua nonce validation khi các check khác đúng |
| Wrong nonce | Token từ authentication request khác | Từ chối |
| Missing nonce | Flow đã gửi nonce | Từ chối theo OIDC validation |
| Wrong issuer | Nonce đúng nhưng `iss` sai | Từ chối |
| Wrong audience | Nonce đúng nhưng `aud` sai | Từ chối |
| Expired ID Token | Nonce đúng nhưng `exp` quá hạn | Từ chối |
| Wrong signature | Nonce đúng nhưng signature sai | Từ chối |
| Wrong UserInfo sub | UserInfo subject khác ID Token | Không tin UserInfo |

### 23.4. Security operations tests

- Không ghi code/state/verifier/ID Token trong application/access logs.
- Cookie session đúng Path/Domain/Secure/SameSite.
- Callback qua reverse proxy dựng đúng public redirect URI.
- Session store hoạt động với nhiều instances.
- Provider A fail không khiến OP B callback bị xử lý sai.
- `invalid_grant` không tạo retry loop.
- Khi access token bị từ chối, Resource Server vẫn kiểm tra audience/scope.
- Authorization flow mới tạo state/verifier/nonce mới.

---

## 24. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| OP báo `invalid_grant` khi token exchange | Code dùng lại/hết hạn, verifier sai, redirect URI/client mismatch | Code lifetime, PKCE challenge/verifier, token request; không log raw |
| Callback có code nhưng `authorization_request_not_found` | Session/state bị mất, callback path sai | Cookie, session store, TTL, reverse proxy |
| Một tab login được, tab khác state mismatch | Repository không giữ nhiều pending flows | Multi-tab design, key theo state |
| Token endpoint không nhận verifier | Chưa bật PKCE hoặc custom token client làm mất params | Request resolver, response client, S256 |
| Authorize URL có `plain` | PKCE config/OP compatibility | Ưu tiên S256, tránh downgrade |
| Client secret đúng nhưng code không đổi được | PKCE verifier mismatch hoặc code/redirect mismatch | Client auth không thay PKCE |
| ID Token nonce mismatch | Trộn request, nonce cũ, callback không thuộc flow | Authorization request context, OIDC validation |
| ID Token issuer mismatch | Sai OP, mix-up, configuration issuer | Registration, `iss`, JWK set |
| JWKS không tải được | Network/OP outage hoặc rotation | Cache policy, fail closed |
| Token validation pass nhưng user sai | Account linking theo email/sub sai | Key theo (issuer, sub) |
| Login xong API 401 | Token sai audience/expired/revoked | Resource Server validation, correct token |
| PKCE enabled nhưng API token bị replay | Bearer token theft | Token hygiene/DPoP/mTLS |
| Logout xong token vẫn dùng được | Logout không auto revocation | Token lifecycle/RS policy |
| Redirect callback localhost trên production | Proxy/baseUrl sai | Forwarded headers tin cậy, redirect registration |
| form_post callback thiếu session | SameSite=Lax trên cross-site POST | Cookie/response mode phù hợp |
| WebFlux callback không thấy request | Reactive publisher không được compose hoặc WebSession mất | Mono save/load/remove, session store |
| Custom provider selector đọc raw query | Token endpoint/trust confusion | Backend allowlisted registrations |
| Log có `code_verifier` | Debug logging HTTP body | Redaction/secrets handling |
| OP hỗ trợ code nhưng không hỗ trợ PKCE S256 | Legacy provider | Compatibility/security review; không tự tắt PKCE |
| Callback replay thành công | Không consume state, AS code reuse bug | One-time semantics, repository cleanup, AS validation |
| Nonce so sánh raw lệch trong custom code | Framework có representation nội bộ | Dùng built-in OIDC validation |
| Callback POST trả CSRF 403 | Response mode/filter configuration | Không disable CSRF toàn cục; cấu hình flow đúng |
| Nhiều instances chỉ lỗi ngẫu nhiên | In-memory session không chia sẻ | Spring Session/Redis hoặc routing phù hợp |

### 24.1. Không quy mọi invalid_grant cho PKCE

`invalid_grant` có thể do:
- Authorization code expired/reused;
- Redirect URI không khớp;
- Client registration sai;
- Code được phát cho client khác;
- PKCE verifier sai;
- Các chính sách AS khác.

Vì thế, log phân loại và kiểm tra request metadata (đã redaction), không khẳng định ngay “PKCE bị lỗi”.

### 24.2. Không quy mọi nonce mismatch cho OP bị lỗi

Nếu nonce mismatch:
- Có thể state/session/authorization request bị trộn;
- Có thể code bị đưa từ flow khác;
- Có thể custom code so sánh sai representation;
- Có thể provider trả nonce không đúng contract.

**Không bỏ nonce validation** để xác định lỗi. Tách từng layer để tìm nguyên nhân.

---

## 25. Checklist thiết kế bảo mật tích hợp

Khi review một OAuth2/OIDC Client production, đặt các câu hỏi:

1. Authorization Code Flow có dùng PKCE S256 khi được OP hỗ trợ/được yêu cầu?
2. Verifier sinh bằng CSPRNG, mới mỗi flow và đủ độ dài?
3. Verifier chỉ được giữ trong trusted transaction context và gửi tới token endpoint?
4. AS có thực sự kiểm tra verifier khớp challenge gắn code?
5. Callback có đối chiếu `state` với request gốc gắn browser/session?
6. Pending authorization request có TTL và được tiêu thụ một lần?
7. OIDC login có giữ nonce binding và không tự bỏ validation?
8. ID Token được xác minh issuer, audience, signature, expiry và các checks OIDC liên quan?
9. Multi-provider có trust boundary theo registration/issuer?
10. API nhận access token có kiểm tra issuer/audience/scope/expiry hoặc introspection?
11. Access/refresh tokens được bảo vệ khỏi logs/XSS và lưu đúng tầng?
12. Có xem xét sender-constrained tokens nếu bearer replay là rủi ro lớn?
13. Session cookie, SameSite, HTTPS và reverse proxy có tương thích callback?
14. Nhiều tabs/nodes có gây mất state/verifier/nonce không?
15. Không tự retry authorization code hoặc dùng lại callback đã tiêu thụ?
16. Không tự chuyển provider/đổi token endpoint theo input không tin cậy?
17. Không dùng email/sub đơn lẻ để gắn user giữa providers?
18. Có tests âm tính cho state mismatch, verifier mismatch và wrong nonce?
19. Có observability phân biệt callback error, PKCE error, ID Token error và Resource Server error?
20. Có phương án phục hồi bằng **flow mới**, không hạ security?

Các câu hỏi trên là **tài liệu học/checklist kiến trúc**, không phải chỉ thị thực hiện STEP 5 QA hoặc chạy test trong bước viết Markdown.

---

## 26. Câu hỏi tự kiểm tra

### Câu 1. PKCE viết tắt của gì và bảo vệ điều gì?

> **Proof Key for Code Exchange**. Nó ràng buộc token exchange với authorization request tạo challenge, nhằm giảm nguy cơ attacker chỉ có authorization code đem đổi lấy token.

### Câu 2. Trong S256, công thức code_challenge là gì?

> `BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`.

### Câu 3. Code verifier gửi ở authorization request hay token request?

> **Token request**. Authorization request gửi **code_challenge** và **code_challenge_method**.

### Câu 4. State được client kiểm tra ở thời điểm nào?

> Khi nhận authorization response/callback, đối chiếu với authorization request gốc trong repository và browser/session context phù hợp.

### Câu 5. Nonce được so sánh với dữ liệu ở đâu?

> Với **`nonce` claim trong ID Token** mà OP cấp, theo flow/representation do OIDC client framework xử lý.

### Câu 6. Nonce đúng có cho phép bỏ kiểm tra chữ ký ID Token không?

> **Không.** Nonce là một ràng buộc bổ sung; signature, issuer, audience, expiry và những checks khác vẫn phải hợp lệ.

### Câu 7. Có client secret rồi có thể bỏ PKCE không?

> Không nên suy luận như vậy. Client authentication và PKCE bảo vệ các mối đe dọa khác nhau; dùng PKCE S256 theo AS support/policy.

### Câu 8. Callback có code hợp lệ nhưng state sai. Có nên thử gọi token endpoint?

> **Không.** Callback không thuộc authorization request gốc đã xác minh; từ chối flow, không bypass correlation.

### Câu 9. Một access token JWT bị đánh cắp. PKCE có chặn replay tới API không?

> **Không trực tiếp.** PKCE bảo vệ authorization code exchange. API token replay cần audience/scope/expiry validation và sender-constrained tokens như DPoP/mTLS khi phù hợp.

### Câu 10. Tại sao không dùng cùng code_verifier cho mọi login?

> Vi phạm tính mới/khó đoán của PKCE binding, làm giảm khả năng chống code interception/injection và tạo tương quan không an toàn giữa flows.

### Câu 11. Vì sao không đặt `code_verifier` trong browser redirect URL?

> URL có thể lộ qua browser history, proxy logs, referrer hoặc analytics; verifier phải được giữ an toàn đến token request.

### Câu 12. OIDC Code Flow có luôn bắt buộc nonce theo chuẩn không?

> Không theo mọi tình huống: nonce là tùy chọn trong Authorization Code Flow theo OIDC Core, nhưng **nếu flow gửi nonce thì cần kiểm tra đúng**, và nó là một lớp bảo vệ quan trọng. Những response types khác có yêu cầu nonce riêng.

### Câu 13. Spring Security Servlet dùng repository mặc định nào?

> **`HttpSessionOAuth2AuthorizationRequestRepository`**, thuộc contract `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`.

### Câu 14. Spring Security WebFlux dùng repository nào?

> **`WebSessionOAuth2ServerAuthorizationRequestRepository`**, thuộc contract `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>`.

### Câu 15. Hai tab login song song khiến state bị ghi đè. Có nên nhận callback dù không match?

> **Không.** Cần thiết kế repository hỗ trợ nhiều pending requests nếu sản phẩm cần, giữ nguyên matching và one-time consumption.

### Câu 16. Provider A và B cùng `sub="123"`. Có phải cùng người?

> Không. Danh tính OIDC cần issuer; dùng ít nhất `(iss, sub)`, account linking theo policy riêng.

### Câu 17. RFC 9207 liên quan gì?

> Nó định nghĩa **issuer identification trong OAuth2 authorization response**, hữu ích để phòng authorization server mix-up trong multi-AS clients. Đây là lớp khác PKCE/state/nonce.

### Câu 18. DPoP nonce khác OIDC nonce chỗ nào?

> DPoP nonce thuộc proof-of-possession/replay management khi gọi AS/RS; OIDC nonce gắn ID Token với authentication request.

### Câu 19. Nếu token endpoint báo invalid_grant, có nên tự tắt PKCE rồi thử lại code?

> **Không.** Xác định code expiry/reuse/redirect/PKCE và khởi động flow mới khi cần. Không hạ security vì lỗi.

### Câu 20. Tại sao phải bảo vệ cookie SameSite/Path/Domain?

> Vì callback cần quay về đúng session để tìm state/verifier/nonce context. Mất cookie có thể làm correlation thất bại.

### Câu 21. Tại sao không chỉ kiểm tra JWT signature?

> Một token ký đúng có thể thuộc issuer khác, client khác, hết hạn hoặc giao dịch cũ. Cần đầy đủ issuer/audience/expiry/nonce và các ràng buộc OIDC áp dụng.

### Câu 22. Khi user refresh trang callback cũ, ứng dụng nên làm gì?

> Từ chối callback đã tiêu thụ và, nếu cần, hướng dẫn bắt đầu một authorization flow mới; không dùng lại authorization code.

---

## 27. Tổng kết theo ranh giới kiểm tra

```text
Authorization Request
    |
    +-- state generated         [Client: callback correlation]
    |
    +-- verifier generated      [Client: giữ riêng]
    |        |
    |        +-- challenge S256(verifier) ---> Authorization Server
    |
    +-- nonce generated         [Client: expected OIDC ID Token binding]
    |
    v
Browser / OP authorization flow
    |
    v
Authorization Response
    code + state
    |
    +-- Client: state matches stored request/session?
    |      |
    |      +-- NO -> REJECT
    |      +-- YES -> continue
    |
    v
Token Request
    code + verifier
    |
    +-- AS: code valid, unconsumed, for correct client/redirect?
    +-- AS: S256(verifier) matches stored challenge?
    |      |
    |      +-- NO -> invalid_grant
    |      +-- YES -> issue tokens
    |
    v
ID Token Validation (OIDC)
    |
    +-- Signature, iss, aud, exp, nonce and other applicable claims?
    |      |
    |      +-- NO -> REJECT
    |      +-- YES -> Authentication allowed
    |
    v
Resource Server API
    |
    +-- Access token must still pass audience/scope/expiry checks
    +-- Bearer replay is separate; DPoP/mTLS when appropriate
```

**Điểm cần nhớ:**

1. **State** ràng buộc **authorization response với request gốc**; cần lưu/đối chiếu đúng browser context và tiêu thụ giao dịch.
2. **PKCE S256** ràng buộc **token request với authorization request** qua verifier/challenge; client secret không thay thế mục đích này.
3. **OIDC nonce** ràng buộc **ID Token với authentication request**; không thay chữ ký, issuer, audience hay expiry validation.
4. Ba cơ chế này cùng giảm code/callback/ID Token replay, nhưng **không tự chống access token bearer replay**.
5. **Spring Security có sẵn filters, repositories và validators**; ưu tiên customizer hẹp như `OAuth2AuthorizationRequestCustomizers.withPkce()` hơn việc viết lại protocol.
6. **Không lẫn Servlet và WebFlux**: HttpSession authorization request repository khác WebSession reactive repository.
7. **Multi-tab, session timeout, SameSite và reverse proxy** có thể làm mất correlation; không bỏ state/nonce/PKCE để né lỗi vận hành.
8. **Nhiều provider cần issuer-specific trust và mix-up protections**, không lấy token/JWK/registration của provider khác làm fallback.
9. **Replay protection phải bao phủ toàn bộ vòng đời**: code one-time, state consumption, ID Token validation, refresh token rotation và sender-constrained access tokens khi thích hợp.
10. **Fail closed và log an toàn**: không in code, verifier, nonce, ID Token, access/refresh token hoặc session cookies.

### Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security 6.5 — Servlet OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html)
- [Spring Security 6.5 — Servlet OAuth2 Login Core](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [Spring Security 6.5 API — OAuth2AuthorizationRequestCustomizers](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html)
- [Spring Security 6.5 API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [Spring Security 6.5 API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [Spring Security 6.5 — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html)
