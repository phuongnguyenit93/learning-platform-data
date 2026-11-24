# Replay authorization code

## 1. Authorization code replay là gì?

Trong chương **Replay protection** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài **Replay authorization code** giải thích vì sao **authorization code** của OAuth 2.0 **chỉ được đổi lấy token thành công một lần**, cách bảo vệ nó khỏi bị đánh cắp/phát lại, và cách Authorization Server (AS) xử lý các request đồng thời hay retry sau lỗi mạng.

Một ứng dụng `sales-dashboard` cho Alice đăng nhập qua Authorization Code Flow:

~~~text
Browser → Authorization Server: user authentication + consent.
AS → Browser → Client callback: code=C1.
Client → AS token endpoint: code=C1 + client binding + PKCE verifier.
AS → Client: access token (+ ID token/refresh token nếu được cấp).
~~~

Kẻ tấn công hoặc một lỗi client có thể gửi lại:

~~~text
POST /token ... code=C1
POST /token ... code=C1
~~~

Nếu AS chấp nhận cả hai lần và phát **hai bộ token độc lập**, một authorization grant tạm thời đã bị biến thành credential **có thể replay**. Đây là lỗi nghiêm trọng: authorization code phải có **lifetime ngắn** và **single-use semantics**, không giống refresh token hoặc một idempotency key được phép tái dùng.

**RFC 6749 `4.1.2 quy định** authorization code **MUST NOT** được sử dụng hơn một lần; nếu dùng lại, AS **MUST** từ chối và **SHOULD** thu hồi những token đã phát từ code đó **khi có thể**. AS phải ràng buộc code với client identifier và redirect URI theo các điều kiện áp dụng. Code được phát để client **đổi ở token endpoint**, không phải bearer access token gửi tới Resource Server (RS).

> **Điểm cốt lõi:** **PKCE làm code bị đánh cắp khó đổi được hơn; PKCE không thay quy tắc code chỉ đổi thành công một lần.** Chữ ký/token validity cũng không thay kiểm tra trạng thái `USED` ở AS. Code replay protection phải hoạt động **nguyên tử giữa nhiều worker/node** và không được biến retry do timeout thành lần phát token thứ hai.

### Mục tiêu học tập

Sau bài, bạn sẽ:

1. Phân biệt authorization code với access token (AT), refresh token (RT), ID token và các loại replay khác.
2. Nêu các bất biến về **single-use, expiry, client binding, redirect binding và PKCE S256**.
3. Giải thích `state`, OIDC `nonce` và issuer binding đóng vai trò gì — và **không** thay kiểm tra nào.
4. Thiết kế AS token endpoint chống **double redemption**, TOCTOU và distributed race.
5. Xử lý callback lặp, token-response loss, retries và tình huống **không biết AS đã commit hay chưa**.
6. Áp dụng ví dụ Java/Spring, SQL transaction/CAS và test liên node an toàn.
7. Phân tích attack traces, log redaction, incident response và ma trận kiểm thử dương/âm.

Các miền `example.test`, mã code/token và khóa trong bài đều là **giả định để học**, không phải credential hoặc endpoint production.

## 2. Đặt authorization code vào mô hình tin cậy OAuth 2.0/OIDC

| Vai trò | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Resource Owner (RO)/End-user** | Alice | Đăng nhập tại AS/OP và cho phép phạm vi truy cập theo policy |
| **OAuth Client/Relying Party (RP)** | `sales-dashboard` | Khởi tạo authorization, bảo vệ verifier/transaction, nhận callback và đổi code |
| **Authorization Server/OpenID Provider (AS/OP)** | `https://auth.example.test` | Phát code, lưu client/redirect/PKCE/grant, kiểm code single-use, cấp AT/RT/ID token |
| **Resource Server (RS)** | `orders-api` | Chấp nhận **AT** đúng audience, scope và quyền đối tượng; **không** đổi authorization code |

### 2.1. Authorization code là một credential tạm thời, không phải token API

Authorization code là một giá trị được AS phát trong **authorization response**. Nó có thể trông như chuỗi ngẫu nhiên/opaque:

~~~text
code=Q4q2kQ_example_one_time_value
~~~

Độ dài/format không có ý nghĩa bảo mật nếu thiếu:

- **Entropy** đủ để khó đoán, dùng CSPRNG hoặc cơ chế bảo vệ tương đương.
- **Expiry** ngắn; RFC 6749 khuyến nghị tối đa **10 phút**, trong thực tế thường chọn ngắn hơn theo chính sách.
- **Client binding** tới registered `client_id`, cùng client authentication khi confidential.
- **Redirect binding** theo authorization request và token exchange.
- **PKCE binding** tới `code_challenge` đã lưu khi authorization request.
- **Grant/subject/scopes/resource binding** không thể tự mở rộng ở token endpoint.
- **Atomic single-use redemption** kể cả khi nhiều nodes cùng xử lý code.

**Không được** gửi authorization code tới RS làm `Authorization: Bearer ...`. RS xác minh OAuth access token, không tra code `USED` ở token endpoint thay client.

### 2.2. Phân biệt replay của từng loại credential

| Credential | Bên tiêu thụ | Replay threat | Biện pháp nổi bật |
| --- | --- | --- | --- |
| **Authorization code** | AS token endpoint | Đổi code một lần nữa để nhận token | **Single-use**, client/redirect binding, PKCE, expiry, atomic redeem |
| **Access token (bearer)** | RS | Attacker dùng lại AT bị đánh cắp trong TTL | Audience/scope/time, TLS, short TTL, DPoP/mTLS khi phù hợp, revocation |
| **Refresh token** | AS token endpoint | Dùng lại RT sau rotation hoặc token theft | Rotation/token-family reuse detection, binding, revocation, sender constraint |
| **OIDC ID token** | RP/OIDC client | Token substitution/login session mix-up | Signature, `iss`, `aud`, `exp`, `nonce`/`auth_time` theo yêu cầu |
| **DPoP proof** | Token endpoint/RS theo profile | Phát lại proof JWT với `jti`/`iat` | Proof validation, URI/method binding, replay cache, nonce khi có |
| **Device code** | AS token endpoint | Poll/redeem trái client/transaction | Binding, expiry, one-winner grant issuance |

Các cơ chế này **không thể thay thế nhau**. DPoP `jti` replay cache không xử lý authorization code đã được dùng; PKCE code verifier không chặn bearer AT bị sao chép **sau** issuance.

### 2.3. Replay có thể là tấn công hoặc lỗi kỹ thuật

Gặp hai request giống nhau không tự chứng minh attacker:

- Browser double-click/duplicate redirect.
- Client callback handler xử lý một code hai lần.
- Gateway/proxy retry `POST /token` sau timeout.
- Hai replica cùng xử lý callback do queue at-least-once.
- Kẻ tấn công đánh cắp code qua referrer/log và gửi lại.

**AS không được giảm mức bảo vệ chỉ vì thấy request có vẻ vô hại.** Điều khác nhau là **telemetry/incident response**, còn bất biến single-use phải giống nhau cho mọi nguồn replay.

## 3. Authorization Code Flow và điểm code được tiêu thụ

### 3.1. Luồng có PKCE

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant RP as sales-dashboard / Client
    participant AS as auth.example.test / AS
    participant RS as orders-api / RS
    RP->>RP: Create state + PKCE verifier/challenge (+ nonce for OIDC)
    RP-->>U: 302 to /authorize
    U->>AS: response_type=code; client_id; redirect_uri; code_challenge=S256
    AS->>AS: Authenticate Alice; evaluate scopes/audience/consent
    AS-->>U: Redirect code=C1 + state
    U->>RP: Callback code=C1 + state
    RP->>RP: Validate state/issuer; locate original verifier
    RP->>AS: POST /token code=C1 + code_verifier + client auth
    AS->>AS: Check expiry, client, redirect, PKCE, state=ISSUED
    AS->>AS: Atomic ISSUED -> CONSUMED + issue grant
    AS-->>RP: AT (+ ID token/RT when applicable)
    RP->>RS: GET /orders with AT aud=orders-api
    RS->>RS: Verify AT issuer/aud/time/scope and domain ACL
~~~

**Replay window** nằm tại bước token endpoint nhận lại `code=C1`, cho dù callback/browser lặp hay một attacker gọi endpoint trực tiếp.

### 3.2. Authorization request

~~~http
GET /oauth2/authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20orders.read&state=<high-entropy-state>&nonce=<oidc-nonce>&code_challenge=<s256-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Điều phải lưu ở AS khi phát code:

~~~text
code fingerprint / lookup
client_registration_id = sales-dashboard
redirect_uri = exactly registered URI used in request
code_challenge = <S256 challenge>
code_challenge_method = S256
resource_owner = Alice
granted_scopes = [openid, orders.read]
granted_resource/audience = orders-api
issuer/authorization context = https://auth.example.test
expires_at = issued_at + short TTL
status = ISSUED
~~~

Đây là **mô hình logic**, không phải record chuẩn bắt buộc trong RFC. AS có thể dùng encrypted/signed self-contained code mang trạng thái nhưng vẫn phải bảo đảm **single use** bằng một kho replay/consumption state hoặc cơ chế tương đương; chữ ký code không tự chặn đổi hai lần.

### 3.3. Callback không đổi code thành session ngay

AS redirect về:

~~~http
HTTP/1.1 302 Found
Location: https://client.example.test/login/oauth2/code/company?code=<one-time-code>&state=<high-entropy-state>
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

RP nhận callback chỉ có **authorization code** và state. Nó cần xác minh state (và issuer/mix-up defense), sau đó đổi code qua HTTPS token endpoint. Nếu muốn login OIDC, chỉ tạo authenticated RP session **sau khi** token exchange thành công và ID token được xác minh. Không lấy `code` hoặc query `sub` làm bằng chứng user identity.

### 3.4. Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <confidential-client-auth>

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=<original-pkce-verifier>
~~~

Với public client, không có secret Basic nhưng có `client_id` và PKCE theo registration. **Client authentication** và PKCE là hai lớp bảo vệ khác nhau: confidential client cần xác thực đã đăng ký, còn PKCE bảo vệ code khỏi bị đổi bởi bên không có verifier.

### 3.5. Sau exchange thành công

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read",
  "id_token": "<oidc-id-token-if-openid>",
  "refresh_token": "<refresh-token-if-granted>"
}
~~~

Không mặc định mọi AS đều cấp `refresh_token` hoặc `id_token`: OIDC ID token gắn với `openid` và OIDC flow/profile; RT tùy grant/client/consent/lifecycle policy. **Token endpoint phải từ chối code C1 sau redemption thành công**, không mint thêm AT/RT để “giúp retry thành công”.

## 4. Các bất biến giao thức không thể thương lượng

### 4.1. Code hết hạn nhanh và không đoán được

RFC 6749 yêu cầu code hết hạn sau thời gian ngắn và khuyến nghị **không quá 10 phút**. Đây không phải “mỗi code được phép dùng trong 10 phút”; nó vẫn chỉ dùng **một lần** trước expiry.

Ví dụ:

~~~text
Issued at 10:00:00
Expires at 10:02:00

10:00:15  First successful redemption → CONSUMED
10:00:16  Replay same code → invalid_grant
10:02:00  Unused code → expired, no token
~~~

Không dùng một chuỗi code tăng dần dễ đoán rồi dựa vào expiry để chống đoán mã. CSPRNG/secure token generator và lookup metadata phù hợp cần được kiểm thử.

### 4.2. Code được ràng buộc với client

Giả sử AS cấp `C1` cho `client_id=sales-dashboard`. Token request từ `client_id=other-app` phải bị từ chối, kể cả hai clients cùng issuer hoặc user Alice vừa xác thực.

Với confidential client, AS xác thực client và kiểm tra **authenticated client** trùng owner của code. Với public client, `client_id` không là secret; việc bảo vệ chủ yếu dựa trên **PKCE** và redirect/browser state với client binding ở AS.

### 4.3. Code được ràng buộc với redirect

Khi `redirect_uri` được gửi trong authorization request, theo RFC 6749 token request phải cung cấp giá trị **giống hệt** (subject to protocol rules) và AS xác minh trùng với giá trị ban đầu. Không chấp nhận một URI tùy ý chỉ vì cùng host hoặc “gần giống”.

Ví dụ:

~~~text
Authorize: https://client.example.test/callback
Redeem:    https://client.example.test/callback
→ May be valid if other checks pass.

Authorize: https://client.example.test/callback
Redeem:    https://client.example.test/callback/extra
→ Reject redirect mismatch.

Authorize: https://client.example.test/callback
Redeem:    https://attacker.example.test/callback
→ Reject redirect mismatch.
~~~

Các security profiles hiện đại khuyến nghị strict redirect URI matching, trừ ngoại lệ được đặc tả như native loopback redirect port theo RFC 8252. Không tự relax wildcard, query normalization hoặc open redirect handling để “sửa callback bị lỗi”.

### 4.4. Single-use là bất biến trên toàn AS cluster

Nếu hai token requests đồng thời dùng `C1`, không có chuyện:

~~~text
Node A reads state=ISSUED → create tokens.
Node B reads state=ISSUED → create another tokens.
Node A writes CONSUMED.
Node B writes CONSUMED.
~~~

Đây là **TOCTOU/double-spend** ở token endpoint. Kiểm tra `if (state==ISSUED)` rồi lưu `CONSUMED` bằng hai thao tác không đồng bộ không đủ. Cần **atomic compare-and-set/transaction** để có **tối đa một winner**.

### 4.5. Phát hiện replay và phản ứng sau replay

RFC 6749 yêu cầu AS **từ chối** một code được dùng hơn một lần và **SHOULD** revoke tokens đã cấp từ code đó **khi có thể**. Đây là phản ứng bảo mật vì attacker có thể đã nhận token từ lần redemption trước, hoặc một client bug đang retry.

AS nên lưu mối quan hệ `code fingerprint → grant/token family` an toàn để điều tra và thu hồi. Phải phân biệt:

- **Attempt với PKCE sai trước khi code được đổi:** thất bại verification, không cấp token; không nên để attacker dễ dàng phá hủy code của Alice chỉ bằng gửi verifier sai (chiến lược abuse/rate-limit tùy AS).
- **Attempt đúng binding sau code đã consumed:** replay thật/duplicate retry, AS từ chối và đánh giá revoke previous grant theo RFC/policy.
- **Attempt sai client/redirect:** từ chối, theo dõi bất thường; không để caller không được phép lạm dụng endpoint để thu hồi token của Alice qua việc đoán code.

### 4.6. Token issuance không được mở rộng phạm vi grant

Authorization code đã gắn với approved user/client/scopes/resources/tenant; token endpoint không được tin request mới:

~~~text
code=C1&scope=payments.admin&resource=payments-api
~~~

để tự nâng quyền. Những tham số ngoài authorization-code grant contract bị từ chối hoặc xử lý theo profile/AS policy chặt; granted scope/audience đến từ **authorization record đã được AS phê duyệt**, không từ client tự khai tại thời điểm redemption.

## 5. PKCE S256: bảo vệ code bị đánh cắp, không phải cơ chế cho phép replay

**Proof Key for Code Exchange (PKCE)** theo RFC 7636 buộc bên đổi authorization code phải chứng minh họ biết **`code_verifier` bí mật của authorization transaction gốc**. Phương thức `S256` được dùng rộng rãi và nên là mặc định; `plain` không được dùng khi có hỗ trợ S256 và security policy hiện đại yêu cầu S256.

### 5.1. Sinh verifier và challenge

Client tạo `code_verifier` entropy cao, cú pháp gồm 43–128 ký tự `unreserved` theo RFC 7636. Từ đó tính:

\[
\text{code\_challenge}
=\operatorname{BASE64URL}_{\text{no padding}}
\big(\operatorname{SHA256}(\operatorname{ASCII}(\text{code\_verifier}))\big)
\]

Ví dụ hai request thuộc **cùng transaction**:

~~~text
Authorization request:
  code_challenge = BASE64URL(SHA256(code_verifier))
  code_challenge_method = S256

Token request:
  code_verifier = original random verifier

AS:
  Compare S256(code_verifier) with stored code_challenge.
~~~

**Không gửi `code_verifier` trong authorization request**. `code_challenge` có thể xuất hiện qua browser/URL; verifier phải được client giữ bí mật/bind với authorization transaction tới lúc đổi code.

### 5.2. Java 17 tạo PKCE challenge

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class Pkce {
    private static final SecureRandom RNG = new SecureRandom();

    public static String generateVerifier() {
        byte[] random = new byte[32]; // 256-bit entropy
        RNG.nextBytes(random);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(random); // 43 characters
    }

    public static String s256Challenge(String verifier)
            throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(digest);
    }
}
~~~

Đoạn code minh họa đúng phép biến đổi S256; trong production framework OAuth nên lo PKCE persistence/transaction binding, validation và constant-time comparison khi phù hợp. Không tự lưu verifier vào URL, access log hoặc telemetry.

### 5.3. Attacker lấy code nhưng không có verifier

~~~text
Alice's client:
  code=C1
  verifier=V1 (private to RP transaction)

Attacker:
  steals C1 from redirect/referrer/log
  sends code=C1 + verifier=Vwrong

AS:
  S256(Vwrong) != challenge(C1)
  → invalid_grant / deny; no tokens.
~~~

PKCE làm **code interception** khó khai thác. Nhưng nếu attacker có cả **C1 và V1** (ví dụ XSS lấy session transaction hoặc malicious app điều khiển browser), PKCE không còn ngăn họ **cạnh tranh redeem**. Chính sách single-use, client authentication (nếu confidential), redirect binding, anti-leakage và detection vẫn cần.

### 5.4. PKCE không bằng client authentication

Với confidential backend client:

- **PKCE:** chứng minh token request đang giữ verifier của authorization transaction.
- **Client authentication:** chứng minh caller là confidential OAuth client được đăng ký.
- **Client ID/redirect binding:** chứng minh code được cấp đúng client và callback.

Một client secret bị đánh cắp không tự cung cấp verifier, và một verifier bị đánh cắp không tự cung cấp private key/secret của confidential client. Cả hai nên được kiểm tra khi profile yêu cầu.

Với public mobile/SPA client, **static secret nhúng trong binary/JS không phải bí mật**; PKCE càng quan trọng. Dùng external browser/native redirects theo security BCP và RFC 8252.

### 5.5. PKCE không thay state, nonce hay issuer binding

| Cơ chế | Bảo vệ chính | Không thay |
| --- | --- | --- |
| **`state`** | RP liên kết OAuth callback với request/session, giảm login CSRF/mix-up | AS single-use code, PKCE |
| **PKCE `S256`** | Ràng buộc code với verifier/client transaction | RP CSRF state, AS single-use |
| **OIDC `nonce`** | Ràng buộc ID token với OIDC authentication request khi dùng/được yêu cầu | Authorization code single-use |
| **Issuer/`iss` binding** | Đảm bảo callback/token từ đúng AS trong multi-issuer RP | PKCE, signature/claims validation |
| **Client authentication** | Xác thực confidential client | PKCE hoặc user consent |
| **`redirect_uri` binding** | Chặn code đổi cho callback URI khác | Code single-use |

Đừng tạo một biến `state=code_verifier` rồi dùng chung ở URL/browser; cần phân biệt mục đích và nơi bảo vệ các bí mật. Trong OIDC, RP phải xác minh ID token issuer/audience/expiry/nonce theo profile trước khi tạo authenticated session.

## 6. Năm nguồn authorization code replay trong thực tế

### 6.1. Kẻ tấn công đánh cắp code qua browser redirect

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    actor U as Alice Browser
    participant RP as Legitimate Client
    participant ATK as Attacker
    AS-->>U: Redirect code=C1
    U-->>RP: GET /callback?code=C1&state=...
    U-->>ATK: Code C1 leaks via unsafe referrer/log/redirect
    ATK->>AS: POST /token code=C1, verifier=unknown
    AS-->>ATK: invalid_grant (PKCE mismatch)
    RP->>AS: POST /token code=C1, correct verifier
    AS-->>RP: Token response once
    ATK->>AS: Replay code=C1
    AS-->>ATK: invalid_grant (used)
~~~

Trong ví dụ, PKCE ngăn attacker thiếu verifier đổi code. Nếu client bị XSS và lộ cả verifier, attacker có thể **đua redeem trước client**: AS chỉ bảo đảm **một bên thắng**, không tự biết bên thắng có phải người dùng mong muốn. Vì vậy cần phối hợp **tránh leak code/verifier**, client auth theo loại client, issuer/redirect binding, token-status monitoring và incident response.

### 6.2. Callback bị xử lý hai lần bởi chính RP

Một browser double-refresh:

~~~text
GET /callback?code=C1&state=S1
GET /callback?code=C1&state=S1
~~~

Hoặc hai Pods cùng nhận một callback qua queue/retry. Nếu RP tạo **hai jobs đổi code**, AS vẫn chỉ được phát token một lần. Client nên có **single-flight** theo authorization transaction hoặc **atomic callback state consume**, không chỉ dựa vào AS để giữ UX ổn định.

Không vì client tự gây duplicate mà làm AS bỏ single-use, và không **lặp lại POST /token không giới hạn** khi gặp `invalid_grant`.

### 6.3. Token endpoint timeout sau khi AS đã cấp token

~~~text
T0: RP sends C1 + verifier V1.
T1: AS atomically consumes C1 and creates token grant G1.
T2: AS writes HTTP 200 but response is lost.
T3: RP sees timeout / connection reset.
T4: RP retries POST /token with C1.
T5: AS rejects because C1 was already consumed.
~~~

Đây có thể là **normal retry after unknown outcome** chứ không phải malicious attack. Tuy nhiên, AS không được gửi lại AT/RT cũ chỉ vì request có cùng `code_verifier`; attacker có thể sở hữu một bản sao request đầy đủ. Client nên trình bày lỗi có thể khôi phục bằng **authorization transaction mới**, không tìm cách replay C1 để mint token lần hai.

### 6.4. Gateway/proxy tự retry một POST không idempotent

Một reverse proxy có chính sách “retry POST on 502/timeout” và gửi lại `grant_type=authorization_code`. Vì token endpoint có **single-use side effect**, retry tự động có thể biến response loss thành `invalid_grant`, hoặc gây tăng tần suất reuse detection.

Điều cần làm:

- Không retry mù quáng authorization-code grant.
- Nếu client/proxy có retry policy, phải biết semantics và fail safely.
- Log correlation bằng transaction ID an toàn (không raw code/verifier).
- Client bắt đầu lại Authorization Code Flow khi outcome không xác định mà không có token đã nhận.

### 6.5. Multi-AS authorization response mix-up

RP hỗ trợ OP-A và OP-B. Nếu một callback code của OP-A bị xử lý như code của OP-B, RP có thể gửi C1/PKCE verifier/client credential đến **sai token endpoint**. Đây là **authorization server mix-up**, không chỉ là code replay.

RP phải ràng buộc `state` với **expected issuer, client registration, token endpoint, redirect URI và verifier** của transaction. Khi AS hỗ trợ RFC 9207, có thể xác minh authorization response `iss`, cùng các OIDC protections khác. Không chọn token endpoint bằng `issuer`/URL do attacker tự khai.

## 7. Bảo vệ code tại RP: nhận callback, lưu transaction và dọn dữ liệu

AS bảo đảm code chỉ đổi một lần, nhưng client cũng phải bảo vệ **code/verifier** và ngăn xử lý callback sai transaction.

### 7.1. Data model cho authorization transaction tại RP

Ví dụ nội bộ:

~~~json
{
  "transaction_id": "login-tx-8102",
  "state_digest": "<protected-state-digest>",
  "expected_issuer": "https://auth.example.test",
  "client_registration_id": "sales-dashboard",
  "redirect_uri": "https://client.example.test/login/oauth2/code/company",
  "encrypted_code_verifier_ref": "<server-side-secret-reference>",
  "nonce_digest": "<oidc-nonce-binding>",
  "created_at": "2026-11-23T02:00:00Z",
  "expires_at": "2026-11-23T02:03:00Z",
  "callback_state": "WAITING"
}
~~~

Đây là **application-specific model**, không phải OAuth standardized JSON. Không lưu raw code/verifier/token vào analytics hoặc unencrypted cache. RP nên có **one-time correlation** theo state và verified client session.

### 7.2. Client-side callback state machine

~~~mermaid
stateDiagram-v2
    [*] --> WAITING: Start authorization
    WAITING --> EXCHANGING: Valid callback and atomic claim
    EXCHANGING --> COMPLETED: Token response verified
    EXCHANGING --> UNKNOWN: Timeout / lost response
    EXCHANGING --> FAILED: invalid_grant / policy error
    WAITING --> EXPIRED: Transaction TTL
    UNKNOWN --> RESTART_REQUIRED: Cannot safely replay code
    FAILED --> RESTART_REQUIRED: New authorization required
    COMPLETED --> [*]
    EXPIRED --> [*]
    RESTART_REQUIRED --> [*]
~~~

Client state machine **khác** AS code state machine: client chưa nhận response có thể ở `UNKNOWN` dù AS đã consumed. Đừng dùng `UNKNOWN` để hợp thức hóa redemption thứ hai.

### 7.3. Atomic callback claim tại RP

Một pattern:

~~~text
on callback(code=C1, state=S1):
    require state matches stored browser authorization transaction
    require expected issuer matches selected OP
    atomically transition transaction WAITING -> EXCHANGING
    if transition fails:
        do not send another POST /token
        render already-completed/expired/restart UX as appropriate
    exchange C1 with stored verifier once
    verify token response / ID token
    mark transaction COMPLETED or UNKNOWN/FAILED
~~~

Làm đúng ở RP giảm nhiễu và race, **không thể thay AS single-use**. Với distributed clients, atomic claim phải dùng **shared store/CAS**, không chỉ một `synchronized` trong một Pod.

### 7.4. Một callback hợp lệ không tự xác thực user

RP phải dùng OIDC ID token đã được xác minh (khi request có `openid`) hoặc profile OAuth phù hợp để tạo principal/session. Không nhận `sub`, `email`, `role` từ browser callback query. Không dùng code như API AT; các resource servers phải xác minh AT riêng.

### 7.5. Giảm rò code trong URI, logs và browser history

Các đường rò thông dụng:

- Browser `Referer` từ callback page tới third-party images/scripts.
- Client-side route chuyển `?code=C1` sang analytics/error reporter.
- Reverse proxy/WAF/access logs ghi raw query string.
- Open redirect ở redirect URI đã đăng ký.
- Request replay từ tracing/APM khi debug OAuth.
- Copy/paste URL callback vào ticket hoặc chat.

Biện pháp:

1. HTTPS/TLS certificate và hostname validation cho authorization/token/callback hops.
2. Callback endpoint xử lý code **server-side càng sớm càng tốt**; với SPA, tránh third-party resources trước khi dọn query.
3. `Referrer-Policy: no-referrer` (hoặc policy được đánh giá tương ứng) và `Cache-Control: no-store` với response chứa credential.
4. Strict redirect URI registration, không open redirect/callback URL tùy ý.
5. Redact `code`, `state` (nhất là khi được dùng như correlation secret), `code_verifier`, AT/RT trong logs/traces.
6. Đảm bảo browser/service worker/history không phát tán callback URL sang domain khác.

### 7.6. Browser refresh không nên tái phát hành grant

Sau callback/token exchange thành công, RP nên **redirect tới URL sạch** không có `code`/`state`. Refresh trang ứng dụng sau đăng nhập phải dùng local session hoặc OIDC flow mới khi cần, không gửi lại token request với code cũ được giữ trong browser history.

## 8. State machine tại AS: một code, một winner

Một AS cần mô hình trạng thái rõ:

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED: Authorized user/client, code generated
    ISSUED --> REDEEMED: Atomic valid token exchange
    ISSUED --> EXPIRED: TTL elapsed
    ISSUED --> INVALIDATED: Logout/grant cancelled/policy
    REDEEMED --> REPLAY_DETECTED: Duplicate redemption attempt
    REPLAY_DETECTED --> [*]: Reject; consider grant revoke
    REDEEMED --> [*]: No more redemptions
    EXPIRED --> [*]
    INVALIDATED --> [*]
~~~

Sơ đồ là **logic security state**, không phải tên trạng thái OAuth được RFC quy định. Trong implementation phân tán, có thể có `REDEEMING` tạm thời. Cần thiết kế failure recovery sao cho chỉ một token grant được commit và code không trở về `ISSUED` sau khi đã redeemed.

### 8.1. Bất biến bảo mật

Với mỗi authorization code fingerprint `C`:

\[
\#\{\text{successful redemptions of } C\} \leq 1.
\]

Đây là **điều kiện thành công được commit**, không phải “tối đa một HTTP request đến /token”. Một request thất bại client auth/PKCE không được tính như successful redemption.

Một transaction thành công phải thỏa:

~~~text
code exists and belongs to trusted AS
AND code.status == ISSUED
AND code.expiresAt > AS.now
AND authenticated/request client matches code.client
AND redirect URI matches original authorization request
AND PKCE S256(verifier) matches stored challenge
AND grant is still allowed, subject/resource/scope consistent
AND atomic consume-and-issue transaction wins
~~~

### 8.2. Kiểm tra và đổi trạng thái phải nguyên tử

Không được:

~~~java
// VULNERABLE TO RACE, DO NOT USE:
CodeRecord c = repository.find(code);
if (c.status() == ISSUED) {
    issueTokens(c);
    repository.markRedeemed(code);
}
~~~

Hai AS nodes có thể cùng đọc `ISSUED` trước khi một node update. Kết quả có thể là hai token grants dù row cuối cùng chỉ hiện `REDEEMED`.

**Đúng về mặt thiết kế:** transaction/CAS bảo đảm một và chỉ một worker được phép commit issuance từ code. Các workers thua nhận lỗi `invalid_grant` (hoặc normalized error thích hợp), không trả AT/RT.

### 8.3. “Đánh dấu used trước” có còn rủi ro không?

Nếu AS `SET code=USED` rồi **mới** phát token mà quá trình ký/lưu token thất bại, code đã consumed nhưng user không nhận token. Điều này **an toàn về chống replay**, nhưng giảm khả dụng. Client cần khởi động authorization flow mới.

Nếu AS phát token thành công **rồi mới** đánh dấu used bằng write không nguyên tử, crash/race có thể phát trùng token. Vì vậy nên có **transactional issuance** hoặc thiết kế atomic state/commit đủ mạnh: không chỉ đổi thứ tự hai thao tác.

### 8.4. Response bị mất không được “reset code” về unused

Sau commit:

~~~text
AS:  C1=REDEEMED; grant G1 committed; sends HTTP 200.
NET: response lost.
RP:  sees timeout.
~~~

Nếu AS vì thấy retry hợp lệ mà reset `C1=ISSUED`, sẽ phá single-use. **Không reset code chỉ để khôi phục UX**. Đánh dấu tình trạng issuance/response loss trong telemetry; client khởi tạo authorization mới nếu chưa có session/token hợp lệ.

### 8.5. Reuse detection không phụ thuộc raw code lưu lâu

AS có thể lưu **hash/HMAC fingerprint** của code và một tombstone `REDEEMED` trong retention ngắn để phân biệt replay với unknown code. Nếu xóa record ngay khi consume, reuse có thể chỉ hiện `invalid_grant` giống unknown/expired; điều này vẫn có thể chặn token issuance nhưng giảm khả năng phát hiện replay.

Không ghi full code vào audit. Token/hash lookup phải được bảo vệ tránh offline guessing, enumeration, DB leakage và high-cardinality logs.

## 9. Triển khai atomic redemption trong database và cluster

### 9.1. Một row mẫu

~~~sql
CREATE TABLE oauth_authorization_code_state (
    code_fingerprint VARBINARY(32) PRIMARY KEY,
    client_registration_id VARCHAR(128) NOT NULL,
    redirect_uri VARCHAR(2048) NOT NULL,
    challenge_s256 VARCHAR(128) NOT NULL,
    issuer_id VARCHAR(256) NOT NULL,
    subject_ref VARCHAR(256) NOT NULL,
    grant_ref VARCHAR(128),
    status VARCHAR(24) NOT NULL,
    issued_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    redeemed_at TIMESTAMP
);
~~~

Đây là **data model minh họa**, không copy nguyên vào production mà bỏ indexes/constraints, data retention, encryption, tenant/scope/audience binding và schema types phù hợp DB. `code_fingerprint` được tính từ code bí mật bằng hash/HMAC trong AS trust boundary; không dùng fingerprint làm credential của người dùng.

### 9.2. Dùng atomic compare-and-set

Ví dụ **PostgreSQL syntax minh họa**:

~~~sql
BEGIN;

UPDATE oauth_authorization_code_state
SET status = 'REDEEMED',
    redeemed_at = CURRENT_TIMESTAMP
WHERE code_fingerprint = :fingerprint
  AND status = 'ISSUED'
  AND expires_at > CURRENT_TIMESTAMP
  AND client_registration_id = :authenticated_client
  AND redirect_uri = :original_redirect
  AND challenge_s256 = :expected_challenge
RETURNING code_fingerprint, grant_ref;

-- If zero rows returned: invalid_grant, do not issue tokens.
-- If one row returned: commit grant/token issuance consistently
-- within same transaction/boundary before reporting success.

COMMIT;
~~~

**Cẩn trọng:** Code trên chỉ minh họa CAS. Trong một AS thực, trước khi update cần kiểm client authentication, PKCE verifier, grant policy, registration và các thuộc tính liên quan. `:expected_challenge` phải đến từ việc **tính S256 verifier do client gửi** và so với challenge lưu ban đầu, không phải challenge do caller tự khai. **Không commit trạng thái REDEEMED rồi gọi một storage độc lập để phát token mà không có failure plan**; cần xác định transaction boundary để tránh split-brain/partial issuance.

### 9.3. Tại sao CAS một row vẫn chưa đủ nếu phát token ở database khác?

Giả sử:

~~~text
DB-A CAS ISSUED -> REDEEMED succeeded.
Token service signs JWT and persists RT to DB-B.
Network partition occurs.
DB-A rolls back; DB-B issued RT remains.
Second worker tries C1 again after rollback.
~~~

Nếu không có transaction/outbox/unique issuance constraints và recovery rõ, hệ thống có thể **phát hai grants** dù mỗi database đơn lẻ có CAS.

Các lựa chọn:

- Token/grant issuance và code consumption trong **một ACID transaction** với cùng datastore.
- Dùng **unique grant issuance key** theo code fingerprint, idempotent internal processor có transaction/outbox và không trả OAuth token response hai lần.
- Dùng state machine `CLAIMED → ISSUED` có lease/fencing, phân biệt “claim đã thắng” với “issuance đã commit”, và retry nội bộ không mint grant mới.

Không dùng distributed lock có TTL ngắn làm **bằng chứng duy nhất** về one-time issuance: lock có thể hết hạn khi worker đang xử lý; worker thứ hai vẫn cần CAS/uniqueness ở durable state.

### 9.4. Redis atomic claim: giới hạn của GETDEL/Lua

Một Redis `GETDEL code-key` (hoặc Lua script kiểm state rồi đổi) có thể giúp **chỉ một worker lấy/claim code record**. Tuy nhiên:

- Redis key expiry/replication/failover ảnh hưởng độ bền state và recovery.
- Việc tiêu thụ Redis key không tự transaction với SQL token/grant store.
- Nếu Redis failover làm key `ISSUED` xuất hiện trở lại sau khi token đã cấp, replay có thể thành công nếu thiếu unique issuance constraint.
- Nếu worker crash sau claim, code có thể mất mà không cấp token; an toàn về single-use nhưng user phải login lại.

Do đó Redis claim phải đi kèm **durable issuance model và failure-injection tests**. Không copy giải pháp “SETNX used” mà chưa xét crash/failover/lease expiry.

### 9.5. Multi-region và consistency

Nếu cùng code có thể được redeem tại region A và B đồng thời, eventual-consistency replication thường **không đủ**:

~~~text
Region A sees C1=ISSUED.
Region B sees C1=ISSUED.
A issues AT-A, B issues AT-B.
Both replicate REDEEMED afterward.
~~~

Cần **single authoritative state** cho code, strong-consistent write/CAS hoặc routing code tới một partition/region có atomic issuance boundary. Quyết định latency vs availability phải ưu tiên bảo đảm single-use; khi không chứng minh được one-winner, **fail closed**, không phát token ở cả hai vùng.

### 9.6. Tombstone, expiry và cleanup

Một AS có thể giữ `REDEEMED` tombstone thêm một khoảng sau `expires_at` để:

- Phát hiện lượng code reuse/attack attempts.
- Truy vết code fingerprint ↔ token grant để revoke khi cần.
- Phân biệt code sai và code đã dùng trong internal audit.

Nhưng response bên ngoài **không nên tiết lộ** code đã thuộc về Alice, đã issued token nào hoặc lý do cụ thể. Retention phải giới hạn; dữ liệu audit/token fingerprint không được lưu vô hạn.

## 10. Retry, unknown outcome và idempotency: điểm rất dễ triển khai sai

### 10.1. Token endpoint không phải API “POST lại để lấy cùng kết quả”

Ở REST thông thường, một backend có thể thiết kế `Idempotency-Key` để trả lại kết quả cho request đã được xử lý. Nhưng **authorization code** được quy định là **single-use security credential**. Không được tự thêm tính năng:

~~~text
If code C1 was used and verifier matches:
    return the same access_token and refresh_token again
~~~

Thiết kế đó có thể cung cấp token cho bất kỳ ai **tái dựng được request** sau khi C1 được dùng. PKCE verifier là **bí mật giao dịch** chứ không phải căn cước client bất biến; nếu verifier và code cùng rò, attacker vẫn có thể lấy lại token từ một “idempotent cache”.

**Phân biệt:**

- **Idempotent internal grant creation:** việc xử lý nội bộ có thể dùng key/unique constraint để bảo đảm **không tạo hai grants**, kể cả khi worker retry sau crash.
- **OAuth external token exchange:** với `grant_type=authorization_code`, code **không được redeem thành công hơn một lần**; trả lại bộ token cho request replay là trái mục tiêu single-use trừ khi có một extension bảo mật được đặc tả/đánh giá riêng. Đừng tự xây extension này như mặc định.

### 10.2. HTTP 200 bị mất sau commit

Client nhìn thấy:

~~~text
POST /token ... code=C1 -> timeout
~~~

Nó **không biết** AS đã commit grant chưa. Hành vi an toàn:

1. Không coi timeout là “AS chắc chắn chưa xử lý”.
2. Không tự mở nhiều concurrent polls/retries với C1.
3. Dừng transaction hoặc dùng **chính sách retry đã được chuẩn hóa/chấp thuận** mà vẫn chịu `invalid_grant` nếu code đã dùng.
4. Nếu không có token nhận được, **khởi tạo Authorization Code Flow mới** theo user/session policy.
5. Ghi event timeout/unknown outcome bằng correlation ID không chứa code.

Nếu nhận response hợp lệ nhưng RP crash **sau khi lưu token an toàn** mà trước khi trả session cookie, ứng dụng có thể phục hồi local state theo transaction policy; điều đó khác với việc **đổi lại C1 tại AS**.

### 10.3. Không tự “unlock” code nếu token service lỗi

Một biến thể:

~~~text
AS claims code C1.
Token signing service times out.
AS sets C1 back to ISSUED.
Attacker and legitimate client race C1 again.
~~~

Nếu AS không biết token signing service đã commit/đưa AT/RT ra ngoài chưa, reset có thể **tạo lần cấp thứ hai**. Cần thiết kế **durable issuance state/outbox, unique grant identity và transaction fencing**; khi không chắc, dùng fail-closed và yêu cầu authorization mới, không mở lại code một cách lạc quan.

### 10.4. Retry có chủ đích vẫn phải kiểm concurrency

Một client hỏng có thể gọi `/token` từ hai Pod cùng lúc. Nếu cả hai trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"access_token": "..."}
~~~

thì test **thất bại**, kể cả AT trả về giống hệt string. Hai successful redemptions qua cùng code vi phạm one-time semantics; không cứu bằng lập luận “cùng token nên an toàn”.

### 10.5. Lỗi trả về và phân biệt nguyên nhân ở internal telemetry

Theo RFC 6749, token endpoint thường dùng `invalid_grant` khi authorization code không hợp lệ, hết hạn, đã được dùng, không khớp redirect URI hoặc client không phù hợp. AS không nên tiết lộ thông tin nhạy cảm ra ngoài:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_grant"}
~~~

Với sai **client authentication**, `invalid_client` và HTTP semantics riêng có thể phù hợp. **Internal metrics** có thể phân biệt `code_reused`, `code_expired`, `redirect_mismatch`, `pkce_mismatch` và `client_mismatch` nhưng không lộ raw code, verifier, user PII hoặc việc mã cụ thể có tồn tại cho caller không được phép.

### 10.6. Revoke tokens đã cấp khi phát hiện reuse

RFC 6749 nói AS **SHOULD revoke when possible all tokens previously issued based on reused code**. Quyết định có rút một grant vì replay đến từ bug retry hay theft cần bám chuẩn và threat model, **không** là lý do chấp nhận replay.

Một chính sách:

~~~text
If state == REDEEMED and same code observed:
    deny new redemption
    record replay event with code fingerprint and client identity
    lookup grant issued from the code
    revoke or quarantine associated tokens when possible/policy requires
    alert if frequency/source/risk suggests compromise
    avoid detailed token existence leakage to caller
~~~

**Không** cho một attacker không có client binding hợp lệ kích hoạt arbitrary token family revocation chỉ bằng việc gửi ngẫu nhiên code ID. Check client/PKCE/attack evidence và chống DoS token probing phải được thiết kế đồng thời với “revoke on replay”.

## 11. Spring Authorization Server: registration và token endpoint protections

Spring Authorization Server (SAS) hỗ trợ Authorization Code Flow, PKCE và token endpoint theo các lớp provider. Các API bên dưới mô tả **phiên bản Spring Authorization Server có `RegisteredClient`, `ClientSettings`, `OAuth2AuthorizationService`**, cần kiểm tra compatibility chính xác với bản triển khai.

### 11.1. Đăng ký confidential web client có PKCE bắt buộc

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

class SalesClientRegistration {
    static RegisteredClient create(
            PasswordEncoder encoder,
            String secretFromSecretManager) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId("sales-dashboard")
                .clientSecret(
                        encoder.encode(secretFromSecretManager))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri(
                        "https://client.example.test/login/oauth2/code/company")
                .scope(OidcScopes.OPENID)
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .refreshTokenTimeToLive(Duration.ofHours(8))
                        .reuseRefreshTokens(false)
                        .build())
                .build();
    }
}
~~~

**Giải thích:**

- `requireProofKey(true)` yêu cầu PKCE đối với client này theo SAS contract.
- `client_secret_basic` xác thực confidential client; secret phải từ protected store, không commit.
- `authorization_code`/`refresh_token` là **grants khác nhau**; refresh token cũng có bảo vệ rotation/replay riêng.
- `requireAuthorizationConsent(true)` điều khiển **consent UI**, không phải bảo vệ replay code. Có thể dùng false cho first-party baseline theo policy **mà vẫn phải single-use**.
- Access/refresh TTL là **giá trị ví dụ**, không đặt authorization code TTL chỉ bằng `accessTokenTimeToLive`.

Authorization code lifetime/state do AS authorization service/token configuration quyết định theo phiên bản; kiểm tra config chuyên biệt cho code TTL trong SAS thay vì suy từ `TokenSettings.accessTokenTimeToLive`.

### 11.2. Public client với PKCE

~~~java
RegisteredClient publicNative = RegisteredClient.withId(
            UUID.randomUUID().toString())
        .clientId("sales-mobile")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.NONE)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("com.example.sales:/oauth2redirect")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();
~~~

Đây là mẫu **public native** minh họa. Trong production, native redirects cần tuân RFC 8252 và platform/app-link registration. Không dùng static client secret nhúng trong ứng dụng; chỉ dùng `client_id` + PKCE theo public-client policy.

### 11.3. Phải kiểm tra triển khai authorization service dưới concurrency

Các AS implementations có thể dùng:

- `InMemoryOAuth2AuthorizationService` khi demo/test.
- `JdbcOAuth2AuthorizationService` hoặc persistence adapter tùy version.
- Custom `OAuth2AuthorizationService` trên database/Redis/distributed store.

**Đừng tự kết luận** “đã dùng Spring SAS nên code exchange nguyên tử ở mọi multi-node topology”. Chứng minh bằng **integration test trên đúng datastore, isolation level, cache/failover và token provider** đang dùng. Một in-memory service trên từng Pod **không** là shared transaction store production.

Khi viết custom provider/service, phải bảo toàn các validation của Spring: client authentication, authorization code grant, PKCE, redirect/client binding, token profile. Không override `OAuth2AuthorizationCodeAuthenticationProvider` chỉ để bỏ kiểm reuse hay trả token cached.

### 11.4. Policy ở token issuance vẫn phải kiểm AT audience

Sau khi code `C1` redeem thành công, SAS có thể phát JWT/opaque AT cho RS. AS cần gắn issued scopes/resource/audience đúng authorization grant, không tin `scope=orders.admin` do client gửi thêm tại token exchange. RS phải:

- Verify JWT issuer, signature, audience, expiry, token type/profile và `orders.read`; hoặc
- Dùng trusted introspection cho opaque AT rồi kiểm `active`, audience, scope và ACL.

**Đúng authorization code replay protection không thay access-token replay protection.** Một AT bearer bị đánh cắp sau issuance vẫn có thể replay tại RS nếu không có sender constraint hoặc revocation/state kiểm soát.

## 12. Spring Security OAuth2 Login phía client: không tự đổi code hai lần

### 12.1. OIDC client registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://auth.example.test
        registration:
          sales-dashboard:
            provider: company
            client-id: sales-dashboard
            client-secret: INJECT_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - orders.read
~~~

`INJECT_FROM_SECRET_MANAGER` chỉ là placeholder. Đối với confidential backend, giữ token/`code_verifier` và client secret trong **server-side protected state**, không đưa chúng tới client logs.

### 12.2. OAuth2 Login filter flow

~~~java
@Configuration
@EnableWebSecurity
class WebSecurity {
    @Bean
    SecurityFilterChain chain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());
        http.oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Spring Security cung cấp authorization request/response correlation và code exchange trong OAuth2 Login stack; **không** nên tự thêm một MVC callback controller cùng path `/login/oauth2/code/{registrationId}` rồi cũng gọi token endpoint. Hai handlers cùng xử lý một callback dễ gây duplicate redemption.

### 12.3. Kiểm tra PKCE request thực tế

Trong những phiên bản có API:

~~~java
@Bean
OAuth2AuthorizationRequestResolver pkceResolver(
        ClientRegistrationRepository registrations) {
    var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");
    resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());
    return resolver;
}
~~~

Tùy version/client type, cần nối resolver này vào `oauth2Login(...authorizationEndpoint(...))` và kiểm tra browser `/authorize` thật sự có `code_challenge_method=S256`. **Không** chỉ thấy bean tồn tại rồi giả định code verifier đã được lưu/đổi đúng.

Client không nên tạo `code_verifier` mới trong callback; phải lấy **original verifier** đã lưu cho authorization transaction `state`. Nếu state/session mất, dừng flow, không thử brute force verifier hoặc tái dùng verifier của transaction khác.

### 12.4. Chuyển đến trang sạch sau callback

Sau exchange thành công, ứng dụng nên chuyển browser khỏi URI chứa `code` và `state` tới application landing URL. Nếu callback được retry do network, client trả thông báo transaction đã hoàn tất hoặc restart, **không** gửi `POST /token` một lần nữa. Token endpoint của AS vẫn phải chống replay kể cả client sai.

### 12.5. Distributed sessions và multiple instances

Với nhiều Spring app Pods:

1. Session/authorization request repository cần strategy shared hoặc session affinity đáng tin.
2. Code verifier và state phải ràng buộc đúng transaction/browser.
3. Duplicate callback cần **atomic claim** ở shared state, không chỉ `synchronized`.
4. Callback processing phải tách `WAITING`, `EXCHANGING`, `COMPLETED`, `UNKNOWN`.
5. Không in raw code/verifier trong `AuthenticationException`/redirect error.
6. Nếu client không biết outcome và không có token, khởi tạo flow mới theo policy.

### 12.6. Không nhầm HTTP retry với refresh-token rotation

Sau login thành công, client có thể dùng RT để xin AT mới khi AS cho phép. Đó là một request **`grant_type=refresh_token`**, không dùng lại `grant_type=authorization_code` và C1. Rotation RT cũng có own reuse detection; không thể “relogin nhanh” bằng code đã dùng.

## 13. Client-side anti-replay còn phụ thuộc đúng issuer và response

### 13.1. OAuth login CSRF bằng authorization code injection

Attacker cố gửi callback chứa code từ authorization transaction của attacker vào browser Alice. Nếu RP không kiểm `state`/session binding, có thể tạo **login session confusion**: Alice bị login vào tài khoản attacker.

PKCE có thể hạn chế một số cách tấn công injection, nhưng RP **vẫn phải kiểm state/transaction** và issuer. Không đưa role/user mapping vào session dựa trên `code` chưa đổi/xác minh.

### 13.2. Callback với code ở URL lạ

Nếu RP hỗ trợ:

~~~text
/callback?code=C1&tokenEndpoint=https://attacker.example.test/token
~~~

và gửi `code_verifier`/client secret tới token endpoint được user cung cấp, attacker có thể đánh cắp credential. Token endpoint phải đến từ **trusted client registration/OP discovery** đã xác minh, không từ browser query hoặc unverified `iss`.

### 13.3. Redirect URI và open redirect

Một registered redirect URI `https://client.example.test/redirect?next=...` nếu có open redirect có thể **chuyển code ra ngoài**. AS phải quản trị exact redirect registration; RP phải loại bỏ open redirect/fragment leakage. PKCE là lớp phòng vệ bổ sung, **không cho phép mặc kệ code leakage**.

### 13.4. OIDC ID token và nonce

Trong OIDC Authorization Code Flow:

~~~text
Authorization request: scope=openid, nonce=N1 (if used)
ID token: signed, iss=expected, aud=client_id, nonce=N1
~~~

RP verify ID token signature, issuer, audience, expiry, nonce khi đã gửi/được yêu cầu. **OIDC nonce không đánh dấu authorization code C1 là USED** và không thay CAS ở AS. Một attacker có thể replay cùng C1 dù nonce không đổi; token endpoint vẫn phải từ chối lần sau.

### 13.5. Multi-issuer và RFC 9207 authorization response `iss`

Khi RP tin nhiều AS/OP, response có thể mang issuer identifier theo RFC 9207 hoặc OIDC cơ chế tương ứng. RP cần:

- Map `state` tới expected AS và client registration.
- So authorization response issuer nếu có/yêu cầu với expected issuer.
- Chỉ gọi token endpoint đã cấu hình cho transaction.
- Kiểm ID token issuer sau token exchange.
- Không đưa code/verifier đến AS khác để “thử xem endpoint nào nhận”.

Đây là **AS mix-up defense** độc lập với việc từng AS xử lý code replay.

### 13.6. PAR/JAR/JARM bảo vệ request/response nhưng vẫn cần single-use

OAuth Pushed Authorization Requests (PAR), JWT-Secured Authorization Request (JAR) và JWT-Secured Authorization Response Mode (JARM) có thể giảm tampering/lộ/đánh tráo dữ liệu ở những profile hỗ trợ. Tuy nhiên **authorization code vẫn là credential một lần**: AS phải bảo vệ lifecycle code ở token endpoint.

Không suy rằng một authorization response đã ký (JARM) làm code có thể đổi nhiều lần. Các profile nâng cao giải quyết **message integrity/binding** chứ không thay trạng thái redemption.

## 14. Threat model: kẻ tấn công có thể biết được gì?

Không thể chọn biện pháp chỉ từ nhận xét “code bí mật”. Cần phân loại attacker đã lấy được credential nào.

### 14.1. Attacker chỉ biết `client_id`

`client_id` thường là public identifier; biết nó **không** cho phép gọi token endpoint lấy AT từ code người khác. AS phải kiểm authorization code tồn tại, đúng client binding, redirect, expiry và PKCE; với confidential client còn client authentication.

Điều kiện ngăn attacker **đoán code** là entropy/tốc độ thử/timeout và token endpoint rate limits. Đừng dựa vào client_id là secret.

### 14.2. Attacker có code nhưng không có PKCE verifier

**Mục tiêu:** đổi C1 lấy token Alice.

**Biện pháp:** đúng PKCE `S256` làm token endpoint từ chối `code_verifier` sai, dù code chưa dùng. Client/server không được in verifier vào logs, session analytics hoặc browser URLs.

**Rủi ro còn lại:** attacker có thể gây traffic, brute force online hoặc cố làm thất bại flow nếu AS xử lý sai verifier thành “code consumed”. AS nên phân biệt failed verification với successful redemption, rate-limit theo issuer/client/source/correlation phù hợp và chống token probing.

### 14.3. Attacker có code và verifier, nhưng thiếu confidential client authentication

Nếu `sales-dashboard` là confidential backend với `client_secret_basic`, mTLS hoặc `private_key_jwt`, attacker vẫn thiếu credential của client để đổi code. Đây là **defense in depth**.

Đừng kết luận mọi first-party mobile/SPA có bảo vệ này: native/SPA thường là **public clients** và secret nhúng trong app không an toàn.

### 14.4. Attacker có full token request trước client

Giả sử attacker kiểm soát browser JS qua XSS và lấy được C1+V1, hoặc bị compromise tại BFF/proxy lấy cả client authentication. Họ gửi request hợp lệ trước:

~~~text
T0 AS issues C1 for Alice.
T1 Attacker steals C1, V1, client authentication context.
T2 Attacker redeems C1; gets G1 tokens.
T3 Legitimate RP tries C1; receives invalid_grant.
~~~

AS đã thực thi **single-use** đúng nhưng attacker vẫn có tokens. Vì vậy, **replay protection không đồng nghĩa chặn người nhanh nhất**; cần code/verifier confidentiality, sender constraints khi phù hợp, token revocation và replay anomaly detection. Khi legitimate RP gặp `invalid_grant`, đừng chỉ hiển thị lỗi rồi bỏ qua dấu hiệu nghi compromise.

### 14.5. Attacker chỉ có AT sau issuance

Code đã consumed, attacker không có C1. Họ vẫn có thể replay **bearer AT** đến `orders-api` nếu AT còn hạn và RS chấp nhận. Code replay controls **không giúp gì**; dùng AT TTL, audience/scope, RS authorization, DPoP/mTLS-bound tokens nếu hỗ trợ và AS/RS revocation policy.

### 14.6. Attacker có RT

Attacker có RT có thể xin AT mới theo grant policy, không cần authorization code cũ. Bảo vệ bằng RT rotation/token-family replay detection, sender constraint và revocation. Không cho phép client thử C1 lại để “khôi phục” RT đã bị revoke.

### 14.7. Internal attacker kiểm soát một AS replica

Nếu Pod-B chạy code cũ không có CAS, nó có thể accept duplicate C1 dù Pod-A bảo vệ đúng. Cần **một enforcement point chung** trong durable store/token-issuance boundary, audit deploy/version, fail-closed policy khi store không available.

### 14.8. Attacker gây race bằng request flooding

Một code C1 có thể bị gọi `POST /token` hàng trăm lần trong vài milliseconds. Nếu AS vừa kiểm vừa phát token không nguyên tử, concurrency làm lỗ hổng dễ tái hiện.

Hãy thiết kế cho **worst-case interleaving**, không chỉ test request tuần tự. Rate limiting chỉ làm giảm tải; nó **không** thay atomic one-winner guarantee (hai requests trong giới hạn vẫn có thể race).

### 14.9. Attacker dùng client khác hoặc redirect khác

Token endpoint phải từ chối ngay cả khi code C1 chưa được dùng. Một code thuộc `sales-dashboard` không thể đem đổi bằng `finance-dashboard`. Đánh giá redirect theo request gốc, không cho same-host prefix match tùy tiện.

### 14.10. Attacker tái sử dụng token response qua log/cache

Nếu reverse proxy/cache lưu response `POST /token` và trả lại khi thấy body giống nhau, attacker có thể nhận token từ **cache replay** mà AS không hề thấy request thứ hai. Ngăn lưu/caching token responses ở shared intermediaries, dùng `Cache-Control: no-store` theo OAuth semantics, bảo vệ TLS, logs và response credentials.

## 15. Telemetry, replay detection và cách không gây lộ bí mật

### 15.1. Metrics có thể hành động

| Metric minh họa | Mục đích | Lưu ý |
| --- | --- | --- |
| `authorization_code_issued_total` | Số codes AS đã phát theo client/AS region | Không log raw code |
| `authorization_code_redeemed_total` | Số successful code redemptions | Tránh đếm hai lần do retry response |
| `authorization_code_reused_total` | Attempts với code đã consumed | Correlate client/version/region/risk |
| `authorization_code_expired_total` | Code bị gửi sau `expires_at` | Phát hiện latency/browser UX |
| `authorization_code_pkce_failed_total` | S256 verifier không khớp | Attacker interception hoặc client storage bug |
| `authorization_code_client_mismatch_total` | Sai client binding | Phát hiện mix-up/probing |
| `authorization_code_redirect_mismatch_total` | Sai redirect binding | Thường do config drift hoặc attack |
| `authorization_code_atomic_conflict_total` | CAS row affected=0 vì concurrent redeem | Chứng minh một worker thua, không phải code double-issue |
| `token_response_unknown_outcome_total` | Client timeout/reset sau POST /token | Theo dõi retry/callback handling |
| `authorization_code_replay_revoke_total` | Grants/tokens được revoke vì code reuse theo policy | Đo false positives và incident |
| `token_exchange_issuance_duplicate_total` | Unique grant constraint violation | **Security alert**, điều tra multi-node race |

Metrics names là **ví dụ**, không phải metric chuẩn của Spring/RFC. Đừng đưa `code`, `code_verifier`, token raw, client secret, email/`sub` trực tiếp làm label.

### 15.2. Audit event tối thiểu, không raw secrets

~~~json
{
  "event": "authorization_code_redemption",
  "decision": "DENIED",
  "reason": "CODE_ALREADY_REDEEMED",
  "issuer_ref": "company-as-prod",
  "client_registration_ref": "sales-dashboard",
  "code_fingerprint_ref": "<non-reversible-protected-reference>",
  "authorization_grant_ref": "<protected-grant-reference>",
  "as_region": "region-a",
  "policy_version": 4,
  "correlation_id": "<opaque-correlation-id>"
}
~~~

Đây không phải schema RFC; tùy luật/chính sách PII retention, không cần mọi field ở mọi sự kiện. `code_fingerprint_ref` phải không giúp brute force/khôi phục raw code. Nếu code có entropy đủ cao, hash/HMAC phục vụ correlation có thể dùng, nhưng cần bảo vệ store, tránh gửi fingerprint đi công khai.

### 15.3. Phân biệt lỗi client với compromised code

| Tín hiệu | Khả năng là bug | Khả năng là attack |
| --- | --- | --- |
| Hai POST giống nhau trong cùng client correlation ID sau timeout | Proxy retry/duplicate callback | Attacker có full request hoặc shared logs |
| Code redeemed từ nguồn lạ trước client hợp lệ | Ít khả năng là user flow thường | Code/verifier/client credential compromise |
| Repeated wrong PKCE verifier cho nhiều codes | Client mất transaction state | Code interception/probing |
| Cross-client/redirect mismatch tăng sau deploy | Client config drift | Attempted code substitution/mix-up |
| Reuse spread across regions/Pods | Distributed bug hoặc retry fanout | Coordinated replay flooding |

Không thể xác định động cơ chắc chắn chỉ từ HTTP logs; phản ứng security ưu tiên **deny second redemption và giới hạn ảnh hưởng**. Đừng báo raw code/AT cho helpdesk “để kiểm tra”.

### 15.4. Đừng để telemetry làm phát tán code

Các nguồn thường quên:

- NGINX/access logs ghi full `$request_uri`.
- Application exception ghi `HttpServletRequest.getQueryString()`.
- APM tracing capture form fields `code`/`code_verifier`/`client_secret`.
- Debug HTTP client ghi `Authorization: Basic` và token response.
- Browser analytics ghi callback URL.
- Support tickets đính kèm ảnh/copy link chứa `code`.

Áp redaction tại **mọi hop**. Ngay cả code đã expired cũng không nên tiếp tục lộ trong logs vì log có thể chứa verifier/RT/AT kèm theo hoặc là ví dụ về pattern sai.

## 16. Edge cases trong môi trường phân tán

### 16.1. AS node clock lệch nhau

Một code expires tại 10:00:30 theo node A nhưng node B có clock chậm 30 giây. Nếu token endpoint không có clock consistency, code có thể được nhận quá hạn ở một vùng.

Biện pháp:

- Đồng bộ đồng hồ qua NTP và giám sát clock drift.
- Dùng trusted server time khi xét expiry trong atomic transaction khi phù hợp.
- Không tăng code TTL vô hạn để “giảm lỗi clock”.
- Test các mốc trước/bằng/sau expiry và node skew.

### 16.2. Database isolation và TOCTOU

Với transaction isolation level không đủ và logic `SELECT ... THEN INSERT TOKEN` tách rời, hai workers có thể cùng thấy `ISSUED`. Sử dụng **conditional UPDATE/unique issuance constraint/row lock** tùy DB, và kiểm tra **affected rows**. Một transaction không tự giải quyết race nếu không có serialization/conflict detection.

### 16.3. Replication lag và read replicas

Không dùng read replica eventual-consistent để quyết định code còn `ISSUED` rồi phát token từ primary. Một replica có thể chưa nhìn thấy `REDEEMED` sau request đầu. Nếu phải đọc replica, chỉ đọc cho non-security analytics; **redemption phải dựa trên authoritative write path**.

### 16.4. Queue at-least-once delivery

Nếu AS dùng job queue để sign/persist token, worker có thể nhận cùng issuance job hai lần sau crash/ack loss. Hãy dùng durable job ID gắn code fingerprint/unique grant identity và **idempotent internal commit** không tạo RT/token family thứ hai. Đừng trả token response từ **hai** jobs thành công đến client.

### 16.5. TTL cleanup chạy trước audit/replay detection

Nếu cleanup xóa record ngay sau expiry, AS có thể mất khả năng biết token đã từng redeemed hay chưa. Không ảnh hưởng single-use nếu code không thể đổi lại, nhưng làm replay detection/incident response yếu đi. Có thể giữ tombstone giới hạn và revoke mapping nếu cần, cân đối retention/PII policies.

### 16.6. AS deployment rollback

Version N hỗ trợ atomic consumption, version N-1 dùng read-then-write. Nếu rollback N-1 khi nhiều replicas đang chạy, lỗ hổng code replay có thể quay lại. Cần **schema/constraint enforcement ở shared store**, compatibility tests và deploy policy không cho phiên bản yếu hơn bỏ CAS.

### 16.7. Gateway retry khi request body đã được xử lý

Proxy có thể thấy connection reset, không biết upstream đã commit. Retry sang Pod-B có thể tạo double redemption nếu AS yếu. Cấu hình gateway không retry POST authorization code grant một cách mù quáng; **AS vẫn phải one-winner** để chống race từ bất kỳ caller nào.

### 16.8. Same code ở các issuer khác nhau

Hai AS có thể tình cờ phát một chuỗi code giống nhau do test fixtures hoặc format; **issuer namespace** là một phần của trust context. RP không gửi một code đến nhiều AS “để tìm nơi chấp nhận”. AS records/token response cũng phải được phân vùng theo issuer/client, không áp consent/grant của issuer A cho issuer B.

### 16.9. Lặp lại authorization request không đồng nghĩa replay code

Nếu Alice bắt đầu hai **authorization transactions khác nhau**, AS có thể phát **hai codes khác nhau** `C1` và `C2`, cả hai được đổi một lần theo grants/policy tương ứng:

~~~text
Authorization request R1 → code C1 → one successful exchange.
Authorization request R2 → code C2 → one successful exchange.
~~~

Đây không phải replay cùng authorization code. Nếu product muốn giới hạn concurrent sessions/grants, đó là **chính sách session/token issuance riêng**, không phải lý do đòi mọi user chỉ được login một lần.

### 16.10. High availability và fail closed

Khi authoritative code state store không thể truy cập, AS **không thể chứng minh code chưa consumed**. Không fallback sang local memory rồi tiếp tục cấp token. Trả server error có kiểm soát, client khởi tạo lại flow khi cần và AS khôi phục store/transaction state trước khi chấp nhận redemption mới.

## 17. Ma trận kiểm thử authorization code replay (65 ca)

Test harness nên gồm:

- AS test có authorization/token endpoints, 2+ nodes, shared code/grant state và fake signing/token provider.
- Confidential web client A, public mobile/SPA client B, client C khác registration, hai redirect URIs và hai AS issuers.
- Fake clock, deterministic fault injection, database transactional hooks/barriers, restart/failover simulation.
- Token issuance audit hoặc table unique grant để đếm **số successful committed grants**; **không chỉ đếm HTTP 200**.
- Một RS test để chứng minh access token đúng audience/scope và AT không bị đồng nhất với authorization code.

Không dùng secrets/tokens production. Test có **cặp positive/negative**; lỗi “luôn trả 401/invalid_grant” không chứng minh replay protection.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| R01 | Code C1 hợp lệ, client A, redirect đúng, verifier S256 đúng, chưa dùng | **Một** redemption thành công |
| R02 | Gửi lại C1 sau R01, cùng body hoàn toàn | `invalid_grant`; **không** cấp token lần hai |
| R03 | Gửi lại C1 với `code_verifier` khác | Không cấp token; không bypass consumed status |
| R04 | Gửi lại C1 từ IP/device khác với đủ request fields | Không cấp token; ghi security event phù hợp |
| R05 | C1 hết hạn dù chưa từng redeem | `invalid_grant`, không cấp token |
| R06 | C1 chưa hết hạn nhưng đã redeemed | `invalid_grant`, expiry không cho phép sử dụng lại |
| R07 | Client A code C1 được gửi ở token request client C | Từ chối cross-client binding |
| R08 | Confidential client secret sai | Từ chối client auth, không được cấp AT |
| R09 | Public client B thiếu client secret nhưng đúng registration/PKCE | Có thể thành công một lần theo public-client policy |
| R10 | Public client B cố dùng `client_secret=hardcoded` thay PKCE | Không coi static secret là đủ để bỏ PKCE |
| R11 | Token request redirect URI khác authorization request | `invalid_grant` hoặc lỗi phù hợp |
| R12 | Redirect URI khác do thêm slash/query mặc dù cùng host | Từ chối khi không match đúng registered/request URI |
| R13 | Redirect URI thuộc open redirect tới attacker | Security test chặn redirect/callback leakage |
| R14 | Callback RP thiếu hoặc sai `state` | RP không đổi code hoặc tạo session |
| R15 | Callback state thuộc transaction khác nhưng code vẫn còn active | RP từ chối session mismatch |
| R16 | Callback state đã consumed/replayed | RP không tạo token request thứ hai |
| R17 | Code đến từ issuer OP-B được xử lý bởi token endpoint OP-A | Từ chối/mix-up prevention, không leak verifier/secret |
| R18 | Authorization response `iss` sai expected issuer trong multi-AS | RP từ chối theo RFC 9207/profile |
| R19 | OIDC ID token `nonce` sai khi nonce được sử dụng | RP không tạo session dù code exchange đã thành công |
| R20 | Browser callback `code=C1` nhưng user-provided `sub=admin` | RP không tin browser-sub/role |
| R21 | Token request thiếu `code_verifier` khi C1 có PKCE challenge | Từ chối, không cấp token |
| R22 | Token request verifier sai S256 challenge | Từ chối, không cấp token |
| R23 | Client gửi `code_challenge_method=plain` trái policy S256 | AS từ chối authorization request khi profile yêu cầu S256 |
| R24 | Verifier đúng S256/ASCII/Base64url no padding | AS chấp nhận nếu mọi điều kiện khác đúng |
| R25 | Verifier quá ngắn/sai charset/kiểu dữ liệu | AS từ chối theo PKCE syntax |
| R26 | Verifier của transaction T2 dùng với C1 của T1 | PKCE mismatch; không cấp token |
| R27 | Attacker chỉ có C1, không có V1, thử nhiều verifier | Không redeem thành công; rate limiting/monitoring |
| R28 | Attacker có C1+V1 nhưng thiếu confidential client auth | Không redeem thành công |
| R29 | Attacker có đủ C1+V1+client auth, redeem trước RP | Tối đa một winner; incident monitoring vì RP sau đó thấy used code |
| R30 | Token endpoint xin `scope=payments.admin` vượt grant C1 | Không cấp scope ngoài approved authorization |
| R31 | Token endpoint xin resource `payments-api` khi C1 chỉ aud orders | Không mở rộng audience |
| R32 | Code C1 bị hủy bởi AS policy/user cancellation trước redemption | Từ chối |
| R33 | Hai token requests cùng C1 **đồng thời** trên một Pod | Tối đa một issuance commit |
| R34 | Hai requests cùng C1 trên **hai AS nodes** | Tối đa một issuance commit, loser bị từ chối |
| R35 | 100 requests cùng C1 vượt qua rate limiting vẫn tranh CAS | Không hơn một grant/token issuance |
| R36 | Two workers cả hai đọc `ISSUED` trước barrier | Atomic CAS chỉ một worker thắng |
| R37 | CAS affected rows=0 | Không gọi token mint/issue cho loser |
| R38 | Transaction retry sau deadlock/serialization failure | Không tạo grant thứ hai; recovery safe |
| R39 | Redis `GETDEL` một lần nhưng token store khác fail | Không tạo duplicated grants qua recovery |
| R40 | Redis failover/replica lag sau token commit | Code không trở lại trạng thái redeemable |
| R41 | Multi-region AS simultaneous redeem | One authoritative winner, không double-issue |
| R42 | Read replica stale báo C1 còn unused | Write path/CAS chặn duplicate |
| R43 | Queue worker nhận issuance job hai lần | Unique grant identity chặn token family thứ hai |
| R44 | Signing service lỗi **trước commit**, code đã claimed | Không mint trùng; AS fail safely, client có thể cần flow mới |
| R45 | Token grant đã commit nhưng HTTP 200 bị mất | Client outcome unknown, AS không chấp nhận reuse C1 |
| R46 | RP retry tự động cùng body C1 sau timeout | AS từ chối lần hai; không resend tokens qua unreviewed cache |
| R47 | Reverse proxy retry `POST /token` sang Pod khác | One-winner dù proxy cố retry |
| R48 | Idempotency cache trả lại AT/RT cho replay C1 | Security test **phải phát hiện/không cho** hành vi này |
| R49 | RP đã lưu token nhưng browser refresh callback URL | Không gửi lại exchange request; clean redirect |
| R50 | RP duplicate callback ở hai replicas cùng transaction | Client single-flight/transaction claim; AS vẫn one-winner |
| R51 | RP bắt đầu authorization transaction mới C2 sau C1 timeout | C2 có thể redeem một lần nếu user/grant policy cho phép |
| R52 | Hai codes C1/C2 của hai authorization requests hợp lệ | Mỗi code tối đa một redemption; không nhầm là replay của cùng code |
| R53 | Code C1 bị replay sau expiry và tombstone cleanup | Không cấp token dù không còn record |
| R54 | Reuse C1 sau commit có grant G1 để trace | Internal detection map fingerprint→G1; external response không lộ G1 |
| R55 | AS policy revoke tokens phát từ C1 khi code reused | Khi khả thi, revocation chạy đúng scope; không mint mới |
| R56 | Attacker random-probes unknown codes | Không lộ user/token existence; rate-limit và không gây arbitrary grant revocation |
| R57 | Clock skew giữa AS nodes sát `expires_at` | Không nhận code quá hạn theo authoritative policy |
| R58 | AS state store outage | Fail closed, không dùng local memory fallback phát token |
| R59 | Deployment rollback sang provider version bỏ CAS | CI/security test chặn phát hành trùng trước rollout |
| R60 | `code` hoặc `code_verifier` xuất hiện trong gateway/APM logs | Redaction test phát hiện và sửa |
| R61 | Raw `Authorization: Basic` và token response bị log | Redaction/security test phát hiện |
| R62 | Token response bị shared intermediary cache theo request body | Không tái phân phối token cho replay caller |
| R63 | AT đúng issuer/aud/scope được gửi RS | RS kiểm tra AT/token purpose/ACL, không cần code |
| R64 | Authorization code hoặc OIDC ID token gửi làm bearer tới RS | RS từ chối sai token type/purpose |
| R65 | RT rotation reuse sau login thành công | AS RT-family replay protections hoạt động riêng, không dùng C1 lại |

### 17.1. Positive control bắt buộc trước khi test replay

Một test `R02` chỉ có ý nghĩa nếu `R01` đã đổi code thành công trong đúng môi trường:

~~~text
Create fresh code C1 bound to client A, redirect R, challenge S256(V).
Redeem C1 with valid client A + R + V:
    require exactly one HTTP 200 with verified tokens
    require exactly one committed authorization grant.
Redeem C1 again with the same A + R + V:
    require non-success invalid_grant
    require committed grant count remains one
    require no second AT/RT family is minted.
~~~

Nếu cả hai attempts bị từ chối vì JWKS/secret/config sai, bạn **chưa** kiểm được replay semantics.

### 17.2. Race test bằng synchronization barrier

~~~text
Setup code C1 state=ISSUED.

Worker A:
    validate client+redirect+PKCE
    wait at pre-CAS barrier
Worker B:
    validate same client+redirect+PKCE
    wait at pre-CAS barrier

Release:
    concurrently CAS ISSUED -> REDEEMED

Assertions:
    success count == 1
    failure count == 1
    committed grants == 1
    minted ATs == 1
    minted RT families <= 1
    no unauthorized token response for loser
~~~

Phải dùng **shared database/Redis/authorization service thật** trong test, với hai process/nodes khi cần. `synchronized` trong cùng JVM không mô phỏng race production đa node.

### 17.3. Test token-response loss

~~~text
1. Client sends C1, V1 to token endpoint.
2. AS validates and commits G1, marks C1 redeemed.
3. Fault injector drops HTTP 200 response before client receives it.
4. Client records UNKNOWN outcome, no authenticated session/token.
5. Client retries C1 only to test AS defense:
       AS responds invalid_grant, no second issuance.
6. Client starts new authorization flow C2 per policy.
7. AS issues G2 only if C2 represents a new valid grant.
~~~

Lỗi response mất **không cho phép AS trả lại G1 tokens cho replay request** chỉ vì giống body. Nếu AS có crash recovery nội bộ, test thêm unique issuance key, outbox processing và lease fencing.

### 17.4. Test client binding và verifier với các biến độc lập

Giữ issuer, code TTL và user context hợp lệ; thay **một điều kiện** mỗi lần:

| Test | Đổi gì so với positive control? | Muốn chứng minh |
| --- | --- | --- |
| Wrong client | `client_id=client-B` | AS code/client binding |
| Wrong redirect | `redirect_uri=other` | AS redirect binding |
| Wrong verifier | `V2` thay `V1` | PKCE enforcement |
| Wrong issuer | Gửi code tới AS-B | Issuer/client transaction routing |
| Expired code | Fake clock > expiry | TTL enforcement |
| Reused code | Redeem C1 thành công rồi lại dùng | Single-use enforcement |

Nếu một test sai redirect đồng thời gửi verifier sai, error không cho biết **redirect validator** có hoạt động đúng không. Viết assertions trong test harness để cô lập nguyên nhân.

### 17.5. Test audit và revoke-on-reuse không thành token probing

Sau một replay đã bị từ chối:

~~~text
External response:
    generic invalid_grant; no user/grant/token details.

Internal audit:
    code fingerprint + client registration + reason + correlation ID.

If policy triggers revocation:
    grant tokens associated with C1 are handled only after
    sufficient verified context; do not revoke Alice's tokens because
    an unauthenticated attacker guessed a code string.
~~~

Kết hợp với rate-limit tests, credential leakage tests và incident playbooks. Việc báo `invalid_grant` đúng là điều kiện cần, nhưng **không đủ** để kết luận toàn bộ vận hành an toàn.

## 18. Sáu tình huống thực tế có phân tích nguyên nhân

### Tình huống A: Lộ code trong access log nhưng PKCE chặn được redemption

**Bối cảnh:** `sales-dashboard` dùng Authorization Code + PKCE S256. Gateway ghi `GET /login/oauth2/code/company?code=C1&state=S1` vào log. Một người có quyền truy cập log lấy được C1 và gửi tới `/token` mà không có verifier.

**Quan sát:**

~~~text
Attacker: code=C1, code_verifier=Vwrong → invalid_grant.
RP:       code=C1, code_verifier=V1     → token response once.
~~~

**Nguyên nhân/điểm bảo vệ:** PKCE ràng buộc C1 với `S256(V1)` của transaction. Nhưng việc token/code đã nằm trong log **vẫn là incident data handling**; nếu logs đồng thời chứa verifier hoặc credentials, bảo vệ bị phá.

**Giải pháp:** Redact query/body nhạy cảm ở proxy, APM, frontend; giới hạn quyền đọc logs và retention. Xem xét replay telemetry, ngăn public clients brute force và test no-credential-leak. Không kết luận “PKCE đã chặn nên log code là vô hại”.

### Tình huống B: Kẻ tấn công có cả code và verifier, đổi trước RP

**Bối cảnh:** Một XSS trong SPA lấy authorization transaction state chứa `C1` và `V1`. Attacker chạy token exchange trước legitimate client.

~~~text
T0  AS issues C1 for public SPA.
T1  XSS steals C1 and V1.
T2  Attacker redeems C1 successfully, receives AT (and RT if granted).
T3  SPA tries C1, AS returns invalid_grant.
~~~

**Điểm cần hiểu:** AS single-use **hoạt động đúng** — chỉ một bên thành công — nhưng bên đó có thể là attacker. PKCE không chống được attacker lấy cả code/verifier.

**Giải pháp:** Giảm XSS/token exposure, chỉ dùng scripts tin cậy, CSP phù hợp, giới hạn RT issuance/browser storage, cân nhắc BFF, DPoP/mTLS-bound tokens theo rủi ro, audit `invalid_grant` bất thường. AS theo RFC 6749 **SHOULD revoke khi có thể** tokens đã phát từ code bị reuse; cần review scope ảnh hưởng trong incident.

### Tình huống C: Lỗi HTTP 504 khiến RP đổi code hai lần

**Bối cảnh:** BFF gửi `POST /token` C1, AS commit G1 nhưng gateway cắt HTTP response. RP retry vì cho rằng request chưa thành công.

~~~text
First POST C1 → AS commits, response dropped.
Second POST C1 → AS rejects invalid_grant.
Browser sees login unsuccessful.
~~~

**Nguyên nhân:** Network timeout không nói được AS có commit hay chưa. **Đúng behavior** của token endpoint là từ chối replay, ngay cả khi UX bất tiện.

**Giải pháp:** Tắt retry tự động không có semantic guard, phát hiện `UNKNOWN` outcome và bắt đầu Authorization Code Flow mới nếu client chưa nhận/lưu tokens. Bên trong AS dùng durable unique issuance/transactional commit để không tạo token family thứ hai sau crash; không trả lại G1 token như “idempotent response” cho replay C1.

### Tình huống D: Hai AS replicas cùng phát token từ một code

**Bối cảnh:** Pod-A và Pod-B dùng cùng database nhưng mỗi Pod làm `SELECT code.status`, tạo tokens, rồi mới `UPDATE status='REDEEMED'`.

~~~text
Pod A SELECT C1 → ISSUED
Pod B SELECT C1 → ISSUED
Pod A INSERT grant G1
Pod B INSERT grant G2
Pod A UPDATE C1 → REDEEMED
Pod B UPDATE C1 → REDEEMED
~~~

**Nguyên nhân:** TOCTOU và issuance side effects không nằm trong atomic boundary. Row cuối là `REDEEMED` **không chứng minh** từng có chỉ một issuance.

**Giải pháp:** Conditional UPDATE/CAS hoặc transaction lock + unique grant issuance key, commit consumption/issuance nhất quán. Test thật với 2+ Pods, barrier và fault injection; assert **one committed grant and at most one successful exchange**. Một Redis lock có TTL cũng không thay durable CAS khi lock có thể hết hạn giữa chừng.

### Tình huống E: Callback của attacker đăng nhập nhầm tài khoản

**Bối cảnh:** RP không kiểm `state`. Attacker lấy authorization code thuộc phiên của họ rồi dụ browser Alice gọi `/callback?code=attacker-code`. RP đổi code và tạo session mang account attacker trong browser Alice.

**Nguyên nhân:** Đây là **login CSRF/authorization code injection**, không nhất thiết là code reuse. Code có thể được đổi **đúng một lần** nhưng gắn vào sai RP browser session.

**Giải pháp:** RP bắt buộc callback-to-transaction binding qua `state`, đúng issuer/client/redirect/PKCE, OIDC ID token validation và `nonce` khi dùng. AS vẫn giữ single-use; không dùng một lớp bảo vệ để suy lớp còn lại đã đủ.

### Tình huống F: Sau downgrade failover, code bị dùng lần hai

**Bối cảnh:** AS cluster nhận C1 tại region A, đã cấp AT. Failover đến region B có replica state chưa ghi `REDEEMED`; region B cấp thêm AT khi client/gateway retry.

**Nguyên nhân:** AS sử dụng **eventual consistency** để ra quyết định one-time redemption hoặc token issuance không có unique grant constraint toàn vùng.

**Giải pháp:** Single authoritative write path cho code, strong-consistent CAS hoặc partition affinity, persistent issuance keys/fencing; nếu state không đủ tin cậy, **từ chối phát token** thay vì fail-open. Test region failover ngay tại commit boundary, đo emitted tokens lẫn durable grants. Thiết kế recovery không “khôi phục” code đã consumed.

## 19. Checklist trước production và câu hỏi tự kiểm tra

### 19.1. Checklist AS authorization code issuance

1. **Entropy:** Code được sinh khó đoán bằng CSPRNG/approved mechanism, không tuần tự và không chứa PII?
2. **Code TTL:** Có short expiry theo policy và không vượt giới hạn khuyến nghị của RFC 6749 nếu không có lý do được phê duyệt?
3. **One-time:** Mỗi code có **tối đa một successful redemption**, không phân biệt node/region?
4. **Client binding:** Code gắn registered client và token endpoint kiểm đúng authenticated/request client?
5. **Redirect binding:** Giá trị `redirect_uri` trùng authorization request và registered policy?
6. **PKCE:** S256 được yêu cầu theo client/security policy và verifier được kiểm chính xác?
7. **Grant scope:** Token issuance chỉ dùng approved subject/scopes/resources/tenant, không mở rộng từ token request?
8. **Issuer trust:** Code/grant thuộc đúng AS issuer; không có cross-issuer namespace collision được tin?
9. **DB constraints:** Có CAS/transaction/unique issuance key thay vì `read then write`?
10. **Multi-region:** Replica/commit/failover strategy giữ single-use hoặc fail closed khi state không xác định?

### 19.2. Checklist token endpoint và failure handling

11. **TLS:** Authorization/token endpoints HTTPS, valid certificate/hostname, không trust-all?
12. **Request syntax:** `grant_type=authorization_code` và `code` theo form encoding; không trộn RT/access token làm code?
13. **Confidential client auth:** Secret/private-key JWT/mTLS được kiểm theo registration khi áp dụng?
14. **Public client PKCE:** Không yêu cầu static secret giả nhưng phải bảo vệ PKCE và redirect?
15. **Atomic state:** Validation có thể làm trước, nhưng consume-and-issue phải có **atomic winner**?
16. **One response:** Không trả lại AT/RT cho reused code qua idempotency cache hoặc proxy?
17. **Replay reaction:** `invalid_grant` trên duplicate, revoke related tokens khi có thể/theo RFC/policy và có abuse controls?
18. **Unknown outcome:** Network timeout sau commit không khiến AS reset code hay mint grant mới?
19. **Expired/invalid:** Không dùng expired/unknown/revoked code, không lộ chi tiết token ownership?
20. **Response:** Token responses không bị shared-cache/log, có HTTPS và security headers phù hợp?

### 19.3. Checklist client/RP

21. **Browser state:** `state` được sinh ngẫu nhiên, bind callback/browser/request và one-time consume?
22. **PKCE verifier:** Lưu an toàn đúng transaction, không sinh lại trong callback và không gửi ở authorization request?
23. **OIDC nonce:** Khi gửi/yêu cầu, ID token `nonce`/`iss`/`aud`/`exp` được RP verify trước login?
24. **Multi-AS:** Client routing token endpoint từ trusted issuer registration, không từ unverified query?
25. **Callback:** Không có hai handlers/Pods cùng đổi C1 do thiếu transaction claim?
26. **Clean URL:** Sau login callback, redirect browser sang route không chứa `code`/`state`?
27. **Retry:** Không tự động gửi lại code sau timeout/5xx như một idempotent POST?
28. **Recovery UX:** Khi `invalid_grant`/unknown outcome, restart authorization với code mới thay vì replay C1?
29. **Credential storage:** AT/RT/ID token và client secret nằm ở store phù hợp loại client, không trong URL/log?
30. **Domain authorization:** AT đúng purpose/audience/scope vẫn phải qua object/tenant ACL ở RS?

### 19.4. Checklist test/observability và incident response

31. **Positive controls:** Token exchange một lần thành công trước khi thử duplicate?
32. **Concurrency:** Có tests hai requests cùng lúc/2+ nodes/100+ workers và assertions token/grant count?
33. **Fault injection:** Có thử crash sau CAS, lost response, network split, Redis/DB failover, queue redelivery?
34. **Replay audit:** Có fingerprint/correlation ID không chứa raw code/verifier/AT/RT?
35. **Security metrics:** Detect duplicate/reuse, wrong client/redirect/PKCE, unusual request storms?
36. **Revocation:** Có mapping code→grant đủ để xử lý tokens đã phát khi replay được phát hiện?
37. **Rolling deploy:** Schema/constraint giữ replay protection ngay cả khi nhiều AS versions chạy đồng thời?
38. **Logs:** Gateway, APM, JS telemetry, support reports đều redact credentials?
39. **Client isolation:** Không dùng one global PKCE verifier hoặc `state` cho nhiều browser sessions?
40. **SLA:** Có kỳ vọng rõ về code TTL, replay response, token revocation và độ trễ phân tán?

### 19.5. Mười sáu câu hỏi tự kiểm tra

**Câu 1. Authorization code có thể đổi token bao nhiêu lần?**

**Một lần thành công tối đa.** Mọi lần sử dụng sau đó phải bị từ chối theo RFC 6749; khi dùng lại, AS nên thu hồi các token đã phát từ code đó **khi có thể**.

**Câu 2. Code còn hạn 2 phút có được dùng lại sau khi đã đổi ở giây thứ 10 không?**

Không. `expires_at` chỉ đặt giới hạn thời gian, không biến code thành credential có thể sử dụng nhiều lần.

**Câu 3. PKCE S256 bảo vệ điều gì?**

Ràng buộc code với **original code_verifier** của authorization transaction. Bên chỉ lấy được code mà không có verifier thường không đổi được, nhưng PKCE không thay one-time check.

**Câu 4. Nếu attacker có cả code và verifier, single-use có cứu được không?**

AS vẫn giới hạn **một winner**, nhưng attacker có thể redeem trước user. Cần anti-leakage, confidential client authentication khi áp dụng, token revocation/monitoring và sender constraint cho AT nếu phù hợp.

**Câu 5. `state` và `nonce` có thay được `code.status=REDEEMED` không?**

Không. `state` liên kết RP callback với authorization transaction; OIDC `nonce` ràng buộc ID token khi dùng. AS vẫn phải lưu/kiểm single-use code.

**Câu 6. AS nhận hai request đồng thời cùng C1, đều có PKCE đúng. Có thể trả hai HTTP 200 không?**

Không. **Tối đa một successful redemption**; durable atomic CAS/transaction/unique issuance constraint phải chặn request thứ hai.

**Câu 7. Một `synchronized` block trong Java có đủ cho cluster ba AS Pods không?**

Không. Lock trong JVM không đồng bộ giữa Pods; cần shared authoritative state/atomic write hoặc thiết kế tương đương.

**Câu 8. Vì sao Redis `GETDEL` chưa đủ khi token grant nằm trong PostgreSQL?**

GETDEL chỉ atomic trong Redis; nó không transaction với issuance ở PostgreSQL và có rủi ro failover/partial commit. Cần durable one-winner issuance boundary.

**Câu 9. Nếu token endpoint timeout, client có nên retry C1 đến khi có 200 không?**

Không. AS có thể đã commit grant. Client cần coi outcome là unknown và khởi tạo flow mới nếu chưa có token, không mint thêm bằng replay.

**Câu 10. Có thể trả lại bộ AT/RT cũ khi code C1 bị dùng lại với cùng verifier không?**

Không nên trong OAuth code flow chuẩn: điều đó biến replay thành cách lấy token từ credential đã consumed. Internal idempotency để tránh **double mint** khác việc cho **external repeat redemption** thành công.

**Câu 11. Authorization code replay có giống refresh-token reuse không?**

Không. Code là một lần đổi initial grant; RT có vòng đời refresh/rotation và token-family detection riêng. Cả hai cần chống replay nhưng không dùng cùng semantics.

**Câu 12. Authorization code bị gửi làm bearer tới `orders-api` có hợp lệ không?**

Không. RS chấp nhận OAuth access token đúng purpose/audience/scope/ACL; authorization code chỉ gửi tới AS token endpoint.

**Câu 13. Vì sao code replay có thể do lỗi hợp lệ của client?**

Browser double callback, proxy retry sau timeout, queue redelivery hoặc hai Pods xử lý cùng callback đều có thể tạo duplicate requests. AS phải từ chối reuse như nhau, còn logs/incident handling phân loại nguồn.

**Câu 14. `invalid_grant` sau một timeout có chứng minh attacker không?**

Không. Có thể AS đã commit và response bị mất. Điều này vẫn cần telemetry và policy revoke-on-reuse, nhưng không được tự kết luận động cơ chỉ từ lỗi.

**Câu 15. Nếu AS có JWT self-contained authorization code ký đúng, còn cần trạng thái không?**

Có nếu muốn đảm bảo **single-use**. Chữ ký chứng minh dữ liệu không bị sửa, không tự chứng minh code chưa redeemed; cần spent-code tracking/atomic mechanism tương đương.

**Câu 16. Khi user login lại và AS phát C2 khác C1, đó có phải replay không?**

Không. Hai authorization grants/requests khác nhau có thể có mỗi code riêng, mỗi code đổi tối đa một lần. Chính sách hạn chế concurrent sessions là vấn đề khác.

## 20. Tài liệu chuẩn và nguồn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code Grant (`4.1), code lifetime/client/redirect binding, **one-time redemption** và token endpoint `invalid_grant`.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge`, `S256` và bảo vệ code interception.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth security BCP, PKCE, authorization code injection/mix-up, refresh token replay và audience restrictions.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user-agent, redirect URI handling và PKCE cho native public clients.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): authorization response `iss` để giảm AS mix-up.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): chuyển authorization request qua back-channel được bảo vệ.
- [RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): request integrity và validation.
- [RFC 9102 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Response Mode (JARM)](https://www.rfc-editor.org/rfc/rfc9102): authorization response integrity/issuer protection.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi RT/AT; phân biệt với authorization code replay.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái AT ở RS và revocation freshness.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token replay ở RS, khác code replay tại token endpoint.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT AT purpose, issuer, audience và token profile ở RS.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519) và [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation và token confusion; chữ ký JWT không thay AS spent-code state.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): giới hạn audience/resource trong authorization và token issuance.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation/subject/actor và grant khác với authorization-code redemption.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained AT và proof replay protection, không thay code single-use.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, ID token, `nonce` và RP authentication.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings`, `OAuth2AuthorizationService`, token settings.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization/token endpoints, PKCE, code grant và extension points.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): client authorization request, callback state handling, token exchange.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client management và token lifecycle.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác minh access token tại API, khác authorization code redemption.

**Điểm cần ghi nhớ:** **Authorization code trong OAuth 2.0 là credential ngắn hạn và chỉ được redeem thành công một lần.** AS phải bind code vào client/redirect/PKCE/approved grant, kiểm thời hạn và thực hiện **atomic consume-and-issue** trên shared authoritative state để chặn replay cả khi hai Nodes, retries hoặc multi-region failover xảy ra. **PKCE S256** làm code bị lộ khó đổi được nếu attacker không có original verifier, nhưng không thay quy tắc single-use và không cứu được nếu attacker lấy cả code/verifier/client credentials. Khi response token mất sau AS commit, client không được yêu cầu AS **mint hoặc trả lại token nhờ dùng lại code**; hãy xử lý unknown outcome và khởi tạo authorization mới nếu cần. Cần tách **callback state/OIDC nonce/issuer validation** khỏi **AS code redemption**, và tách code replay khỏi **bearer AT/RT replay**. Triển khai an toàn đòi hỏi client/AS/RS đều kiểm đúng trust boundary, không rò code/verifier qua logs/URL, có telemetry/revocation policy và kiểm thử concurrency/failure-injection thực tế.
