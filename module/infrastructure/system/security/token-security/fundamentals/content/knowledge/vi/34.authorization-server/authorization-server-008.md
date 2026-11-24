# Token generator

## 1. Token generator là gì trong Authorization Server?

Trong chương **Authorization server** thuộc module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **token generator** là thành phần của **Authorization Server (AS)** chịu trách nhiệm **tạo ra giá trị token và metadata tương ứng** theo kết quả xác thực client, kiểm tra grant, chính sách cấp quyền và loại token cần phát hành. Token generator có thể sinh chuỗi **opaque** không đoán được, dựng **JWT claims**, ký JWT bằng khóa tin cậy, đặt thời hạn và liên kết token với authorization/grant trong hệ thống.

Ví dụ:

~~~text
Resource owner:       Alice
OAuth client:         sales-dashboard
Authorization server: https://auth.example.test
Resource server:      orders-api
Requested scope:      orders.read
Target resource:      orders-api
~~~

Sau khi xác thực Alice, kiểm client, redirect URI, PKCE, consent và resource policy, AS có thể tạo một **JWT access token (AT)**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "client_id": "sales-dashboard",
  "scope": "orders.read",
  "iat": 1893455700,
  "exp": 1893456000,
  "jti": "at-unique-id-example"
}
~~~

Đây là **payload minh họa**, không phải JWT hoàn chỉnh hoặc token hợp lệ. Token thực cần header/payload/signature đúng profile, key/algorithm trust và **thời gian thực**, không dùng timestamps trong ví dụ để chạy production.

> **Nguyên tắc:** **Token generator không được tự quyết định cấp quyền bằng cách tin các tham số do client gửi.** Trước khi generate phải có **authenticated client, validated grant, granted scopes, permitted resource/audience, subject/actor/tenant context và AS policy**. Sau khi generate phải bảo đảm **ký/ngẫu nhiên hóa đúng, lưu trạng thái cần thiết, chống phát trùng hoặc dùng lại trái phép, bảo vệ secret và đưa token qua kênh phù hợp**.

Token generator là **mắt xích** trong quá trình token issuance, không đồng nghĩa toàn bộ Authorization Server. Một JWT được ký đúng nhưng `aud=admin-api` do client tự chọn có thể là token **hợp lệ về chữ ký nhưng sai ủy quyền**.

### 1.1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Vẽ ranh giới giữa **token endpoint/grant authentication**, **authorization policy**, **token generator**, **authorization persistence**, **key management** và **Resource Server validation**.
2. Phân biệt **JWT access token, opaque access token, refresh token, OIDC ID token, authorization code** và các credential liên quan.
3. Thiết kế giá trị token với **cryptographic randomness, uniqueness, signing algorithms, `kid`, issuer/audience binding, claims minimization, TTL và token purpose**.
4. Hiểu cách AS phát token cho **Authorization Code + PKCE, Client Credentials, Refresh Token, Token Exchange** mà không nhầm danh tính người dùng và service.
5. Triển khai và tùy biến Spring Authorization Server bằng **`OAuth2TokenGenerator`, `DelegatingOAuth2TokenGenerator`, `JwtGenerator`, `OAuth2AccessTokenGenerator`, `OAuth2RefreshTokenGenerator` và token customizers**.
6. Phân tích lỗi **claim injection, weak randomness, key rotation, duplicate issuance, refresh-token race, resource confusion, token exfiltration và revocation**.
7. Viết test dương/âm, kiểm thử fault injection và kiểm tra vận hành trước production.

Tất cả URLs `example.test`, token claims, client IDs, timestamps, mã và secrets trong bài chỉ là **giả định học tập**. Trong hệ thống thực, lựa chọn token profile và tham số bảo mật phải được kiểm chứng theo phiên bản framework, AS/RS contract và security policy.

## 2. Token generator đứng ở đâu trong OAuth 2.0/OIDC?

### 2.1. Bốn vai trò và ranh giới trách nhiệm

| Thành phần | Trách nhiệm chính | Không được làm |
| --- | --- | --- |
| **Resource Owner / End-user** | Xác thực/đồng ý quyền khi flow yêu cầu | Không tự “đúc” claims quyền cho API |
| **OAuth Client / OIDC RP** | Yêu cầu grant, thực hiện PKCE/client auth, giữ tokens đúng loại | Không tự sửa `aud`/`scope` rồi ký lại token như AS |
| **Authorization Server / OP** | Kiểm client/grant, áp policy, tạo và quản lý tokens, keys, revocation/introspection | Không phát quyền ngoài approved scopes/resources |
| **Resource Server** | Kiểm token phù hợp API: issuer, signature/`active`, audience, purpose, scope, expiry, ACL | Không nhận JWT chỉ vì chuỗi có ba phần Base64url |

Token generator là **thành phần nội bộ AS**. API business không nên gọi token generator để “lấy token đại diện Alice” mỗi khi thiếu quyền. Điều đó bỏ qua mô hình delegation/actor/policy và dễ tạo **confused deputy**.

### 2.2. Từ token request đến một token hợp lệ

~~~mermaid
flowchart LR
    CL["OAuth Client"] -->|"POST /token"| EP["Token endpoint"]
    EP --> AUTH["Client authentication + grant validation"]
    AUTH --> POL["AS authorization policy: subject, scopes, resource"]
    POL --> GEN["Token generator: value, claims, type, TTL"]
    GEN --> CRY["CSPRNG / JWT signer / KMS"]
    CRY --> DB["Authorization and token-state persistence"]
    DB --> RESP["Token response via protected channel"]
    RESP --> CL
    CL -->|"Access token"| RS["Resource Server"]
    RS -->|"JWT verification or introspection"| VAL["Issuer, audience, time, type, scope, ACL"]
~~~

Sơ đồ thể hiện **luồng logic**; bước generation, signing và persistence có thể chạy trong một transaction/processing pipeline theo implementation. **Không** suy thứ tự vật lý “persist luôn sau sign” là bắt buộc. Bất biến quan trọng là **không trả token thành công khi grant/authorization state không được commit nhất quán theo contract**.

### 2.3. Authenticator, policy, generator và token validator khác nhau

Ví dụ token endpoint nhận:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <registered-confidential-client-credential>

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&code_verifier=<pkce-verifier>
~~~

Một triển khai an toàn cần lần lượt giải quyết:

1. **Client authentication:** caller thực sự là confidential client được đăng ký, hoặc đúng loại public client.
2. **Grant validation:** code còn hạn, đúng client/redirect, PKCE S256 khớp, chưa được sử dụng.
3. **Policy:** subject Alice, approved scopes/resources, tenant, consent, restrictions và risk controls.
4. **Generation:** sinh AT và token khác nếu flow cho phép; gắn đúng claims/type/expiry và dùng khóa/CSPRNG.
5. **Commit/state:** code được consume nguyên tử; grant/token records, refresh family và revocation metadata nhất quán.
6. **Response:** trả token qua HTTPS body, `Cache-Control: no-store`; không đưa AT/RT vào redirect URL.

**Token generator chỉ trực tiếp chịu bước 4**, nhưng phải có **đầu vào đáng tin từ bước 1–3**, phối hợp với bước 5 và 6. Đừng gán việc “authorize user có được xem order 123 không” cho một lớp chỉ xây JWT.

### 2.4. Không phải grant nào cũng có user

Với `grant_type=client_credentials`, AS phát AT cho **machine client/service principal**. Không được tự tạo `sub=alice` hoặc `roles=user-admin` từ tham số client request. Nếu hệ thống dùng `sub` cho service identity, đó là profile/issuer policy riêng; Resource Server phải biết phân biệt user-delegated và app-only authority.

Với OAuth Token Exchange (RFC 8693), subject/actor có thể được giữ hoặc thay đổi theo **AS delegation policy**, không theo chuỗi `subject_token`/`requested_subject` mà client tự chọn. Token generator nhận **quyết định đã phê duyệt**, không biến token exchange thành identity minting tùy ý.

## 3. Các loại token: generator phải biết đang tạo credential gì

### 3.1. Bảng đối chiếu

| Loại credential | Bên tạo / bên dùng | Biểu diễn điển hình | Mục đích / lifecycle |
| --- | --- | --- | --- |
| **OAuth access token (JWT)** | AS phát, RS nhận | JWS JWT với `iss`/`aud`/`scope`/`exp` và profile phù hợp | Cho API đúng resource; có TTL ngắn, JWT offline validation/revocation trade-offs |
| **OAuth access token (opaque)** | AS phát, RS tra AS | Chuỗi random tham chiếu vào server-side token state | AS quản trị metadata/revocation, RS introspection (`active`/audience/scope) |
| **Refresh token** | AS phát, **client** giữ/gửi AS | Thường random opaque, có thể format khác theo AS | Xin AT mới theo approved grant; rotation/family/reuse detection/revocation |
| **OIDC ID token** | OP phát, OIDC RP xác minh | JWT authentication assertion | Xác nhận sự kiện/subject đăng nhập, `aud=client_id`, `nonce` khi dùng; **không gọi business API** |
| **Authorization code** | AS phát, client đổi ở token endpoint | Random opaque, TTL ngắn | **Single-use**; client/redirect/PKCE binding; không phải bearer AT |
| **Device/user code** | AS phát trong Device Authorization Grant | Code ngẫu nhiên theo định dạng/UX policy | Bind device authorization transaction; polling interval/expiry và single grant issuance |
| **Client assertion JWT** | Client tạo, AS xác minh | Signed JWT với `iss/sub=client_id`, `aud=token_endpoint` | Xác thực client tại AS, **không phải AT do AS cấp cho RS** |
| **DPoP proof JWT** | Client tạo, AS/RS xác minh | Per-request signed proof, `jti`/`iat`/`htm`/`htu` | Chứng minh sender key possession; **không phải AT** |

Token generator theo nghĩa hẹp trong Spring Authorization Server chủ yếu xử lý OAuth AS-issued tokens (authorization code/AT/RT/ID token theo flow, generator implementation và version). **Client assertion và DPoP proof không được AS tạo thay client**; chúng ở bảng để tránh nhầm các JWT cùng định dạng.

### 3.2. Opaque không có nghĩa là yếu; JWT không có nghĩa là tốt hơn

**Opaque AT**:

- Giá trị có thể là random reference đủ entropy, không lộ claims cho holder.
- AS lưu metadata và revocation state; RS phụ thuộc trusted introspection hoặc AS-mediated contract.
- Dễ có near-real-time revocation theo **cache freshness và AS availability**; không tự bảo đảm mọi RS biết revoke tức thì.

**JWT AT**:

- RS có thể verify chữ ký/ký hiệu thời hạn offline qua trusted JWKS.
- Giảm network introspection nhưng **claims có thể stale** tới `exp` nếu không có denylist/session checks.
- JWT payload **Base64url encoding không phải encryption**; bất kỳ holder nào có JWT có thể decode claims nếu không dùng JWE.
- Phải kiểm signature/issuer/audience/type/expiry/scope/ACL; chữ ký đúng không tự cấp quyền.

Chọn dựa vào **latency, AS availability, privacy, key distribution, token size, revocation SLA, partner integration và threat model**, không dựa trên khẩu hiệu “JWT luôn nhanh” hoặc “opaque luôn an toàn”.

### 3.3. OIDC ID token không thay OAuth access token

Một OIDC login có thể trả cả:

~~~json
{
  "access_token": "<AT-for-orders-api>",
  "id_token": "<ID-token-for-sales-dashboard>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid orders.read"
}
~~~

Token generator phải **tạo hai token theo hai profiles khác nhau**:

~~~text
ID token audience = client_id / RP.
Access token audience = intended resource server.
~~~

Một OIDC ID token có thể mang `auth_time`, `nonce`, `amr`/`acr` khi áp dụng; không tự gán API `orders.write` vào ID token để Resource Server tiêu thụ. Resource API phải từ chối ID token đưa trong `Authorization: Bearer`.

### 3.4. JWT access token profile và explicit typing

Theo **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, JWT AT dùng header `typ` mang `at+jwt` hoặc media type tương đương theo chuẩn:

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-key-2026",
  "typ": "at+jwt"
}
~~~

JWT header/payload phải được ký bằng đúng AS private key và verify tại RS bằng trusted issuer keyset. **`typ` giúp tránh cross-JWT confusion** (RFC 8725), nhưng không thay `aud`, `iss` và scope checks. Không phải mọi legacy JWT AT đều triển khai RFC 9068; **bảo vệ purpose cần một validator/profile tách biệt có contract rõ**, không chỉ chấp nhận mọi JWT cùng signing key.

## 4. Các bất biến bảo mật mà token generator phải duy trì

### 4.1. Danh sách bất biến

Một token hợp lệ do AS phát cần bảo đảm:

~~~text
The trusted AS authenticated the client (when required).
The grant type was permitted for that registered client.
The supplied grant/credential was valid and not reused illegally.
The subject/actor identity was derived from verified context.
Granted scopes subset of approved policy for client, user/service, target.
Audience/resource binding was approved, not client-invented.
Token purpose/profile is explicit and mutually non-confusable.
Issuer, audience, timestamps, lifetime, token ID and holder binding
  meet the chosen JWT/opaque/RT/ID-token profile.
Cryptographic signing / random generation is secure.
Issued state is persisted or intrinsically verifiable as required.
No duplicate redemption or refresh-token family resurrection occurs.
Token values are returned only to authorized client over secure channel.
~~~

**Quan hệ tập con**: granted scopes không được vượt approved policy. Nếu user chỉ đồng ý `orders.read`, AS không tự tạo `orders.admin` do client gửi `scope` ở token endpoint.

### 4.2. Các kiểm tra nằm ở những lớp khác nhau

| Điều kiện | Nơi kiểm chính | Vì sao không đặt trọn trong token generator? |
| --- | --- | --- |
| Client secret/`private_key_jwt`/mTLS | Token endpoint/client authentication | Generator không trực tiếp nhận credential browser để tự tin |
| Code single-use, redirect URI, PKCE | Authorization-code grant provider + state store | Cần transaction/atomic consumption, không chỉ claims building |
| User consent/admin policy/tenant rights | AS authorization policy | Không để customizer tự sinh `scope=admin` |
| Token type, aud/iss/expiry/claims | Generator + profile policy | Generator nhận approved context và xây token đúng |
| Key operations/randomness | Crypto provider/JWK/KMS/HSM | Không nhúng private key vào business controller |
| Refresh-token rotation/replay | Grant provider + durable token-family store | Generation mới phải gắn atomic lifecycle |
| Audience/scope/object ACL | Resource Server | AT hợp lệ không tự nói user đọc được từng bản ghi |
| Revocation/introspection | AS token-state service + RS cache policy | Ký JWT không tự cập nhật quyền đã thay đổi |

### 4.3. Fail closed khi thiếu dữ kiện đáng tin

Nếu AS không xác định được approved target audience, tenant binding, key ký, authorization record, client authentication hoặc grant state, nó **không nên** phát token với:

~~~json
{
  "aud": ["*"],
  "scope": "admin",
  "exp": 9999999999
}
~~~

để “tránh downtime”. Một generator thiếu context phải **từ chối phát hành/throw lỗi có kiểm soát** hoặc chuyển sang một policy được phê duyệt có đặc tả riêng; không dùng broad permissive defaults.

## 5. Đầu vào được phép: Token generation context

### 5.1. Context không phải “bản sao request HTTP”

Một **generation context** đáng tin cậy nên được tạo sau khi AS đã **xác thực và phê duyệt**. Ví dụ mô hình:

~~~json
{
  "issuer": "https://auth.example.test",
  "registered_client": "sales-dashboard",
  "validated_grant_type": "authorization_code",
  "authenticated_subject": "alice",
  "authorized_scopes": ["openid", "orders.read"],
  "approved_audience": ["orders-api"],
  "tenant": "company-a",
  "consent_reference": "consent-record-ref",
  "authorization_reference": "grant-record-ref",
  "token_type_requested": "access_token",
  "authentication_context": "verified-by-AS",
  "policy_version": "v8"
}
~~~

Đây là **application-specific pseudomodel**, không phải schema OAuth/Spring bắt buộc. Giá trị mỗi trường phải lấy từ **trusted grant state/registration/server policy**. Không làm:

~~~java
// Anti-pattern: client input is not an authorization decision.
String audience = request.getParameter("audience");
String scopes = request.getParameter("scope");
return signJwt(audience, scopes, request.getParameter("sub"));
~~~

Caller có thể yêu cầu scope/resource, nhưng **AS quyết định granted scopes và allowed audience**. Tương tự, `sub` user phải từ validated user authentication/grant, không phải `?sub=admin`.

### 5.2. Phân biệt request, approved grant và issued token

| Thông tin | Client có thể yêu cầu | AS phải phê duyệt | Generator lấy từ |
| --- | --- | --- | --- |
| `scope` | `orders.read orders.write` | Chỉ `orders.read` được user/client phép | Authorized scope set |
| `resource` / audience | `payments-api` | Client chỉ được `orders-api` → từ chối | Approved resource target |
| `sub` | Không được tự chỉ định tùy tiện cho delegated user | User/session được xác thực hoặc token exchange policy | Verified subject/actor |
| `client_id` | Định danh đăng ký | Client auth/binding hợp lệ | Registered/authenticated client |
| `tenant` | Có thể là hint/route request | Policy kiểm grant và subject thuộc tenant nào | Trusted tenant identity |
| `expires_in` | Không có quyền tự đặt vô hạn | AS/token policy cấp TTL | TokenSettings/policy |
| `cnf` key binding | DPoP key/mTLS certificate theo profile | AS xác minh proof và binding | Verified holder public key/fingerprint |

Nếu client xin `orders.write` mà chỉ được phép `orders.read`, AS có thể **thu hẹp** scope khi contract cho phép hoặc từ chối theo policy, nhưng không phát write scope. Nếu client xin resource không được phép, thông thường phải từ chối hoặc áp resource policy rõ; đừng âm thầm phát `aud=*`.

### 5.3. Claims cần được namespace và xác minh semantics

AS có thể đặt custom claims như `tenant_id`, `department`, `roles`. Các claims này phải có:

- **Định nghĩa chủ sở hữu:** hệ thống nào là nguồn dữ liệu đáng tin, cập nhật và revoke khi nào.
- **Schema và cardinality:** string, list, URI, enum; không cho user tùy ý inject bất kỳ JSON.
- **Audience:** claim chỉ xuất hiện khi resource cần nó; không lộ PII tới mọi APIs.
- **Lifetime:** thông tin có thể đổi nhanh (vai trò, nhóm, thuê bao) có thể stale tới `exp`.
- **Authorization contract:** RS có được phép dùng claim như quyền hay chỉ hiển thị UI?

Ví dụ `roles=["admin"]` trong token không thể tự hợp pháp nếu lấy từ client request. Cần role policy thuộc AS/domain authority; RS vẫn phải kiểm object/tenant ACL với bản ghi thực.

### 5.4. Generated context không phải chứng chỉ quyền vô điều kiện

Ngay cả khi AS cấp `scope=orders.read`, RS vẫn phải kiểm Alice có quyền đọc **order 123**. Token generator không thay nghiệp vụ quản lý đơn hàng; nó giới hạn **khả năng được trình token** đến API, không chứng minh dữ liệu cụ thể thuộc ai.

## 6. Tạo opaque token và mã bí mật: entropy, uniqueness, lookup

### 6.1. Opaque token là một **bearer secret**

Giả sử opaque AT:

~~~text
AT-EXAMPLE-MAuN8b99xJ42t-opaque-reference
~~~

Nó có thể được AS ánh xạ sang:

~~~text
token fingerprint:  <protected-token-lookup-key>
client:             sales-dashboard
subject:            alice
audience:           orders-api
scope:              orders.read
issued at:          10:00:00
expires at:         10:05:00
revoked:            false
purpose:            ACCESS_TOKEN
~~~

**Không dùng token value làm public database ID hoặc log correlation key**. Ai lấy được opaque token còn hiệu lực có thể trình đến RS; **định dạng không đọc được không làm token mất tính bearer**.

### 6.2. Dùng CSPRNG, không dùng UUID dự đoán hoặc PRNG yếu

Opaque bearer reference phải đủ entropy để chống đoán/brute force. Một ví dụ Java 17:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class OpaqueTokenValueFactory {
    private static final SecureRandom RANDOM =
            new SecureRandom();

    public static String nextValue() {
        byte[] bytes = new byte[32]; // 256 bits of random material
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

Đây là **mẫu sinh random bearer secret**, không phải implementation đầy đủ của `OAuth2TokenGenerator`. 32 bytes từ `SecureRandom` cho xấp xỉ 256-bit entropy khi nguồn ngẫu nhiên đáp ứng yêu cầu; **không có một độ dài 32 bytes bắt buộc cho mọi token OAuth**. Token generator trong framework nên dùng CSPRNG đã được kiểm chứng, với strength theo threat model/profile.

**Không nên**:

~~~java
// Predictable, unsafe examples. Do not use:
String tokenA = Long.toString(System.currentTimeMillis());
String tokenB = Integer.toString(new java.util.Random().nextInt());
String tokenC = "token-" + userId + "-" + sequence.incrementAndGet();
~~~

Date/time, counter, username hoặc pseudo-random không bảo mật làm token dễ đoán và có nguy cơ enumeration. **UUIDv4** thường dùng nguồn random để uniqueness nhưng không tự là bảo đảm đủ entropy cho mọi secret lifecycle; phải xét exact implementation và số bit ngẫu nhiên.

### 6.3. Entropy khác uniqueness và collision handling

Hai điều kiện độc lập:

1. **Unpredictability:** attacker không đoán được token tiếp theo.
2. **Uniqueness:** không có hai valid records vô tình trùng token value/lookup key.

CSPRNG mạnh làm collision cực hiếm nhưng không thay **unique database constraint** và hệ thống xử lý collision an toàn. Nếu cố tình sinh lại một token trùng mà code tự overwrite record Alice bằng metadata Bob, đó có thể gây **cross-user token substitution**.

### 6.4. Lưu token reference an toàn

Một thiết kế có thể lưu:

~~~text
token_lookup_key = HMAC-SHA256(server_secret, raw_token)
authorization_ref = grant-record-384
purpose = ACCESS_TOKEN
expires_at = server-controlled timestamp
status = ACTIVE
~~~

HMAC lookup là **lựa chọn thiết kế**, không phải RFC bắt buộc. Nếu lưu hash/HMAC:

- Chỉ chấp nhận token **đầy đủ chính xác**, không substring/prefix lookup.
- Bảo vệ HMAC secret và lookup store, chống side-channel/probing.
- Xác định cách rotate lookup secret mà không làm token đang active bị hỏng, hoặc có migration/dual-key policy.
- Không thay token ký JWT bằng việc HMAC token value rồi giả vờ đã verify JWT; đây là **state lookup cho opaque bearer**.
- Không log raw token, HMAC key hoặc full lookup data.

### 6.5. Device/user code có yêu cầu khác opaque AT

**Device code** và **user code** trong RFC 8628 cùng liên kết một device authorization transaction, nhưng user code thường **được người dùng gõ** và có giới hạn UX/độ dài. Do entropy user code có thể thấp hơn opaque AT, AS phải có **expiry, rate limiting, polling interval, binding, verification UI và abuse detection**. Không dùng một user code dễ gõ như bearer AT dài hạn.

### 6.6. Token value không nên tiết lộ trong logs/URLs

Khi token được phát thành công, client nhận qua token endpoint response body trên TLS:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<opaque-reference>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Đây là **response body minh họa**. Không đưa AT/RT trong `Location: /home?token=...`, URL fragment của app hoặc query media download; token endpoint response cũng phải được scrub ở proxies/APM. `Cache-Control: no-store` quan trọng nhưng không thay TLS, storage isolation và client authentication.

## 7. Tạo JWT: JWS, key material, `kid` và KMS/HSM

### 7.1. Một JWT có ba phần nhưng **chữ ký phải được kiểm**

JWT JWS Compact Serialization:

~~~text
BASE64URL(protected_header) . BASE64URL(payload) . BASE64URL(signature)
~~~

Token generator dựng header/payload và dùng **private signing key** hoặc symmetric secret theo algorithm/key profile. Resource Server phải chọn **trusted issuer keyset**, kiểm JWS signature, token type/purpose, audience/time/scope. Không chỉ `Base64.decode(jwt)` rồi tin `sub` hoặc `roles`.

### 7.2. JWS không mã hóa claims

Ví dụ payload:

~~~json
{
  "sub": "alice",
  "department": "payroll",
  "salary": 80000,
  "aud": "orders-api"
}
~~~

Người cầm JWT có thể đọc payload Base64url. Vì vậy **đừng đưa salary, địa chỉ, số định danh, health data, secret hoặc roles nội bộ không cần thiết vào JWT AT**. JWT **ký** bảo vệ integrity/authenticity nhưng không bảo mật payload. Khi thực sự cần confidentiality có thể đánh giá **JWE** hoặc opaque reference theo AS/RS contract, không coi JWE tự giải quyết audience/authorization.

### 7.3. Chọn thuật toán và khóa theo trust contract

AS có thể dùng các JWS algorithms được phê duyệt như RSA-PSS, RS256, ES256 hoặc EdDSA tùy thư viện/RS compatibility. Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "2026-rotated-key-01",
  "typ": "at+jwt"
}
~~~

**Không**:

- Tin `alg=none` hoặc tự thay JWS algorithm bằng request của client.
- Dùng RSA public key làm HMAC secret trong một verifier lẫn algorithm family.
- Follow `jku`/`x5u` từ JWT header chưa verify để tải attacker JWKS/SSRF.
- Giả định `kid` là URL/identity toàn cục; `kid` chỉ chọn key trong **trusted issuer-specific keyset**.
- Dùng cùng một static HMAC secret hardcoded trong mọi source/CI/browser app.

### 7.4. JWK/JWKS và private/public key

Mô hình thường gặp:

~~~text
AS:
  private signing key (restricted / KMS or HSM)
  public verification key(s) published in trusted JWKS

RS:
  expected issuer configured
  JWKS endpoint trusted via issuer metadata/configuration
  verify signature with public key(s)
  check aud/type/scope/expiry and domain ACL
~~~

Public JWKS **không** được chứa private RSA `d/p/q` hoặc symmetric secret `k`. AS có thể có nhiều keys trong rotation period; mỗi token có `kid` gắn active signing key. **Không bắt buộc mọi AS phải dùng KMS/HSM**, nhưng production phải có key governance, restricted access, backups, rotation, audit và incident response.

### 7.5. Signing key rotation cần thời gian giao nhau

Ví dụ:

~~~text
T0: AS signs AT with K-old, kid=old.
T1: AS publishes K-new public key in JWKS.
T2: AS begins signing new AT with K-new, kid=new.
T3: RS caches refresh trusted JWKS and verifies both old/new tokens.
T4: Once no valid old tokens depend on K-old (plus cache/skew),
    AS can retire public old key according to policy.
~~~

Không xóa K-old quá sớm làm RS từ chối valid AT, nhưng cũng không giữ compromised key vô hạn. Cache TTL, token lifetime và clock skew tạo **rotation overlap budget**; khi khóa bị lộ phải ưu tiên incident plan, revoke/denylist và thay key theo rủi ro, không luôn chờ token tự hết hạn.

### 7.6. KMS/HSM latency và failure modes

Nếu ký JWT bằng remote KMS/HSM:

- Cấu hình key ID/algorithm/permissions cố định hoặc allowlist.
- Không fallback “ký bằng test key” khi KMS timeout.
- Không log raw JWT/signing input chứa PII hoặc private key reference bí mật.
- Giới hạn signing concurrency/timeout, retry an toàn theo token issuance state.
- Không mint hai bộ token chỉ vì signing response mất và request được retry.
- Monitor signing errors/latency/key rotation và RS JWKS readiness.

Hệ thống phải phân biệt **signing successful** với **grant/authorization commit successful**. Một JWT đã ký nhưng token state không được persist đúng có thể tạo token ngoài ý muốn nếu được gửi trước transaction commit; cần thiết kế consistency rõ theo loại token.

### 7.7. Self-contained JWT không tự đảm bảo revocation

RS verify JWT offline có thể chấp nhận AT tới `exp` ngay cả khi AS revoke grant/RT, trừ khi RS có denylist/session-state check hoặc giải pháp khác. Token generator không thể “đổi chữ ký của JWT đã cấp” sau logout. Cần thiết kế **AT TTL và revocation SLA** cùng AS/RS; opaque introspection có trade-off khác về latency/caching.

## 8. JWT claims đúng nghĩa: issuer, audience, scope, type, subject

### 8.1. Claims không thể chọn tùy tiện

Một OAuth JWT AT theo profile:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "client_id": "sales-dashboard",
  "scope": "orders.read",
  "iat": 1893455700,
  "nbf": 1893455700,
  "exp": 1893456000,
  "jti": "at-unique-8fd3"
}
~~~

| Claim | Ý nghĩa | Nguồn phải đáng tin | RS phải làm gì? |
| --- | --- | --- | --- |
| `iss` | AS đã phát token | Configured AS issuer | Exact expected issuer allowlist |
| `sub` | Subject của token theo AS profile | Verified user/service identity/grant | Không nhầm user với client; đối chiếu domain principal |
| `aud` | Intended resource(s) | Approved resource policy | **Expected audience của chính RS** |
| `client_id` | OAuth client nhận token | Registered/authenticated client | Áp client/partner policy nếu cần |
| `scope` | Granted OAuth capabilities | AS approval/consent/scope policy | Exact scope matching + domain ACL |
| `iat` | Issuance timestamp | AS trusted clock | Sanity/age checks theo profile |
| `nbf` | Not-before timestamp | AS trusted clock | Từ chối token trước thời gian valid |
| `exp` | Expiry timestamp | AS token lifetime policy | Reject expired; bounded skew |
| `jti` | Token identifier | AS unique generator | Correlation/replay-denylist nếu thiết kế, không phải bí mật |
| `cnf` | Sender-constrained key/cert binding | AS validated DPoP/mTLS context | Verify holder proof/cert khi token bound |
| `tenant_id` (custom) | Tenant domain | Trusted AS/tenant service | So với resource/record tenant, không tin header client |

Theo RFC 9068, một số claims có tính **required** cho JWT AT profile. Bảng trên diễn giải chung; **không** có nghĩa mọi loại token phải có toàn bộ chúng hoặc `scope`/`nbf` luôn bắt buộc ở mọi profile. AS/RS phải thỏa thuận **profile và bộ required claims chính xác**, đặc biệt khi chuyển từ legacy JWT sang RFC 9068.

### 8.2. `iss` cần nhất quán và stable

Issuer phải có giá trị chuẩn hóa, phù hợp metadata và RS trust config. Không phát JWT với:

~~~text
iss = http://localhost:9000   (in production)
~~~

chỉ vì container AS nhìn thấy `Host: localhost` qua reverse proxy. Issuer cần được cấu hình/định tuyến đáng tin, không lấy trực tiếp untrusted `Host`/`X-Forwarded-Host`. RS phải so đúng issuer (theo parser/profile) và JWKS thuộc issuer đó.

### 8.3. `aud` là recipient binding, không phải hostname tùy ý

Nếu AS phát AT cho `orders-api`, token dành `payments-api` **không được** chấp nhận tại orders. Nếu AS phát multi-audience có chủ ý, các RS liên quan phải kiểm membership exact và đánh giá blast radius. Client gửi `resource=admin-api` không có nghĩa generator được tự tạo `aud=admin-api`; phải qua resource policy.

### 8.4. `scope` không phải quyền object và không thay `aud`

~~~text
AT-1: aud=orders-api, scope=orders.read
AT-2: aud=payments-api, scope=orders.read
~~~

Orders chỉ chấp nhận AT-1 nếu mọi điều kiện khác đúng. Khi Alice đọc order của Bob cùng tenant, **scope orders.read chưa chứng minh owner/entitlement**; RS còn kiểm ACL. Không dùng string substring search (`scope.contains("read")`), phải parse grants thành **set** với exact scope names.

### 8.5. `sub` của app-only vs user-delegated access

Không giả định `sub` luôn là email user:

~~~text
Authorization Code:
  user-delegated subject = alice
  client_id = sales-dashboard

Client Credentials:
  app/service subject = sync-worker (profile-dependent)
  client_id = inventory-sync
  no resource owner Alice
~~~

RS/AS cần rõ model `grant_type`/client identity/actor claims. Một machine token có thể được quyền machine-only operations, không tự có user entitlements hoặc quyền impersonation.

### 8.6. Claim injection và tenant escalation

Tấn công:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read&tenant_id=company-b&sub=admin
~~~

Nếu customizer dùng `request.getParameter("tenant_id")` và `sub` để build JWT, attacker có thể tạo token đúng chữ ký nhưng giả danh tenant/admin.

**Phòng vệ:** token generator lấy `tenant_id`, service subject và granted scopes từ **trusted registration/authorization policy**; thông tin client request chỉ làm input đề nghị để **được kiểm duyệt**, không phải claim source.

### 8.7. `jti` và token replay

Một `jti` ngẫu nhiên/duy nhất giúp theo dõi JWT hoặc denylist trong một số hệ thống. Nhưng:

- `jti` **không tự ngăn bearer token replay** nếu RS không có sender constraint/replay policy.
- Một JWT AT có cùng `jti` mà bị copy có thể được trình nhiều lần trong TTL theo bearer semantics.
- Nếu AS bảo vệ replay bằng denylist, phải có store freshness/expiry và tránh cross-issuer `jti` collision.
- Không sử dụng `jti` như refresh-token rotation identifier khi chưa có thiết kế family/grant rõ.

## 9. Thời gian sống: token TTL và clock safety

### 9.1. Các mốc thời gian

Token generator thường xác định:

\[
\text{expiresAt} = \text{issuedAt} + \text{configuredLifetime}
\]

Với JWT:

\[
\texttt{exp} > \texttt{iat}
\]

Đây là **mô hình cơ bản**, không phải mọi token cần `iat` giống nhau; expiration/grant policy phải tương thích token profile và AS/RS clocks. Dùng **trusted server clock** và time duration arithmetic an toàn; không nhận arbitrary `expires_in=999999999` từ client.

### 9.2. TTL của các token khác nhau

| Token | TTL thường chọn | Lưu ý |
| --- | --- | --- |
| Authorization code | Rất ngắn; RFC 6749 khuyến nghị tối đa **10 phút** | **Single-use** dù còn hạn |
| OAuth access token | Ngắn theo risk/AS/client/resource policy | Cân bằng API latency và exposure/revocation |
| Refresh token | Dài hơn AT khi được cấp | Rotation/reuse detection, absolute/inactivity lifetime và revocation |
| OIDC ID token | Theo OP/RP authentication policy | Không đồng nhất với AT TTL, check `nonce`/`auth_time` theo flow |
| Device code | Theo device grant policy/`expires_in` | Polling interval, approval deadline, no replay grant |
| User code | Theo device transaction | Human-entered; online guess rate limiting |

**Không có một TTL duy nhất đúng cho mọi ứng dụng.** Ví dụ AT 5 phút/RT 8 giờ trong phần Java chỉ là minh họa. API tài chính high-risk có thể cần step-up/revocation nhanh; application nội bộ low-risk có profile khác.

### 9.3. Clock skew cần giới hạn

AS và RS có thể lệch vài giây. Một RS thường có bounded clock skew khi xác minh `exp`/`nbf`, nhưng không được cấu hình nới quá rộng để token hết hạn từ lâu vẫn được nhận.

Các test cần có:

~~~text
AT issued at 10:00:00
AT expires at 10:05:00

10:04:59 → time-valid if all other checks pass
10:05:00 → expired by strict exp semantics, subject to bounded skew
10:07:00 → reject under short skew budget
~~~

Khi AS ký token với clock nhảy ngược hoặc `exp≤iat`, generator phải fail/protect profile chứ không tự phát token vô hạn. Kiểm timezone, epoch units (seconds vs milliseconds), overflow và maximum duration.

### 9.4. Absolute/inactivity TTL của refresh tokens

Refresh rotation không mặc nhiên làm grant sống mãi. Một chính sách có thể có:

~~~text
Refresh token family created: 2026-11-23 00:00 UTC.
Absolute grant expiry:        2026-11-30 00:00 UTC.
Inactivity timeout:           24 hours.
AT lifetime:                  5 minutes.
RT rotation:                  enabled.
~~~

Mỗi RT mới không được vô hạn hóa absolute expiry nếu policy nói không. AS cần quản lý server-side family/grant expiry bên cạnh từng token `exp`. Khi user logout hoặc consent bị thu hồi, chính sách revoke phải áp cho family/grant liên quan; client không tự “làm mới RT” bằng cách tái dùng token cũ.

### 9.5. TTL và key rotation

Một JWT AT đã phát với K-old cần key verification đến khi token hết hạn theo overlap policy. Khi tăng AT TTL từ 5 phút lên 2 giờ, team phải đánh giá lại:

- JWKS rotation overlap.
- RS/cache refresh.
- Blast radius khi AT leak.
- Revocation SLA và logout semantics.
- Stale roles/tenant claims.

**Thay TTL của generator là thay đổi security contract**, không chỉ tuning performance.

## 10. Phát token theo grant: Code, Client Credentials, Refresh và Token Exchange

### 10.1. Authorization Code + PKCE

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant RP as sales-dashboard / OAuth Client
    participant AS as Authorization Server
    participant DB as Grant and token store
    RP->>RP: Generate state, PKCE verifier/challenge
    RP-->>U: 302 to /authorize
    U->>AS: Authorize request + S256 challenge
    AS->>AS: Authenticate Alice, consent, resource policy
    AS->>DB: Store authorization code binding client/redirect/PKCE
    AS-->>U: Callback with code C1
    U->>RP: code=C1 and state
    RP->>AS: POST /token C1, verifier, client auth
    AS->>DB: Check C1 and atomic single-use redemption
    AS->>AS: Generate AT (+ ID token/RT when allowed)
    AS->>DB: Commit authorization/token state consistently
    AS-->>RP: Token response once
~~~

**Security invariants:**

- `code` short TTL, single-use; AS bind đúng client/redirect/PKCE S256.
- User subject và scopes lấy từ original authorization grant, **không** tự đổi ở token endpoint.
- AT phát cho đúng resource/audience; ID token nếu OIDC `openid` và conditions hợp lệ.
- RT tùy client/grant/policy, không bắt buộc mọi code exchange.
- Hai requests redeem cùng code đồng thời: **tối đa một successful redemption**; không mint đôi.

### 10.2. Client Credentials (machine-to-machine)

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-service-client-auth>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

AS xác thực service client, áp client registration/scopes/resource policy rồi phát AT cho machine identity. **Không cấp RT trong Client Credentials Grant theo RFC 6749 `4.4.3: refresh token SHOULD NOT be included.** Nếu một vendor extension có lifecycle khác, phải hiểu đúng contract thay vì coi RT là mặc định. Không tự gắn Alice làm `sub` cho machine grant.

### 10.3. Refresh Token Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-client-auth>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<current-rt>
~~~

AS phải:

1. Xác thực/bind client và RT/grant theo policy.
2. Xác minh RT active, chưa expired/revoked/reused trái family policy.
3. Áp lại scope/resource/consent/policy; không phát quyền mới ngoài approved grant.
4. Phát AT mới; nếu rotation bật, phát RT mới và **atomically invalidate old RT**.
5. Ghi issued grant/family state, ngăn old RT được dùng lại để phát tiếp.

Đừng gọi generator “sinh một RT mới” rồi bỏ qua **reuse detection**. Nếu RT bị đánh cắp/replayed, cần token-family revocation/quarantine theo security BCP và AS policy.

### 10.4. OAuth Token Exchange (RFC 8693)

Một service cần token audience-bound cho downstream có thể dùng token exchange khi AS hỗ trợ:

~~~text
Caller service-a holds AT aud=service-a, subject=alice.
Service-a requests token exchange for resource service-b.
AS validates subject token, caller/actor, target, scopes/policy.
Generator issues NEW AT aud=service-b with constrained authority.
~~~

Nếu caller tự gửi `requested_token_type=...`/`resource=admin-api`/`scope=admin.write`, AS chỉ phát theo **approved token exchange policy**, không sao chép nguyên claims của subject token hoặc “nâng quyền” dựa trên service trust. Subject/actor semantics phải rõ, không giả impersonation.

### 10.5. Device Authorization Grant và generator

Theo RFC 8628, AS có thể sinh **device code** và **user code** để người dùng hoàn tất xác thực trên thiết bị khác. Device code phải gắn client/device transaction, expiry và polling rate; user code cần format dễ gõ và chống đoán online.

Sau khi người dùng chấp thuận, device polling hợp lệ dẫn đến **một authorization grant/token issuance**, không phát AT vô hạn khi nhiều polling requests cùng “winner”. `authorization_pending`/`slow_down`/`expired_token` và `access_denied` là **device grant protocol outcomes**; generator chỉ tạo token khi grant đã được authorize.

### 10.6. Không nhầm refresh với phát lại Authorization Code

Sau Code Flow thành công:

~~~text
Code C1 → consumed permanently.
RT R1   → may refresh AT later according to policy.
~~~

Client **không** dùng lại C1 khi AT hết hạn. Nếu token endpoint timeout sau khi AS commit issuance, replay C1 không phải “idempotent retry tạo token giống cũ”; AS phải từ chối reused code. Client có thể phải khởi động **authorization transaction mới** nếu không nhận được token và không có safe recovery contract.

## 11. Spring Authorization Server: `OAuth2TokenGenerator` và các thành phần

Spring Authorization Server (SAS) có mô hình **`OAuth2TokenGenerator<T extends OAuth2Token>`** để tạo token theo `OAuth2TokenContext`. Trong những phiên bản SAS có API tương ứng, các triển khai thường dùng:

| Thành phần Spring Authorization Server | Chức năng | Lưu ý |
| --- | --- | --- |
| `OAuth2TokenGenerator` | Contract tạo token từ generation context | Không phải token endpoint/grant validator |
| `DelegatingOAuth2TokenGenerator` | Thử tuần tự các generators cho đúng token type/context | Thứ tự/format quyết định generator nào trả token |
| `JwtGenerator` | Tạo JWT thông qua `JwtEncoder`, thường cho self-contained AT và OIDC ID token | Ký JWS đúng key/typ/profile, chỉ dùng approved claims |
| `OAuth2AccessTokenGenerator` | Tạo OAuth access token, thường dùng cho reference/opaque AT | Có claims customizer cho access token metadata |
| `OAuth2RefreshTokenGenerator` | Tạo refresh token | Rotation/grant lifecycle vẫn do provider/authorization service phối hợp |
| `OAuth2AuthorizationCodeGenerator` | Tạo authorization code nếu bản SAS hỗ trợ thành phần này | Code single-use/PKCE/expiry thuộc toàn authorization flow |
| `JwtEncodingContext` | Context cho `JwtGenerator` và `OAuth2TokenCustomizer<JwtEncodingContext>` | Tùy biến JWS header/claims theo token type |
| `OAuth2TokenClaimsContext` | Context cho `OAuth2AccessTokenGenerator` customizer | Tùy biến claims metadata của reference AT theo contract |
| `OAuth2AuthorizationService` | Lưu/tra cứu authorization và token state | Quan trọng cho replay/revocation/refresh lifecycle |
| `RegisteredClientRepository` | Client registration, grants, redirect URI, scopes, token settings | Không cho browser tự khai registration metadata |

**Version note:** API class names/builder methods và default token generator chain có thể thay đổi theo SAS version. Kiểm tài liệu của phiên bản đang chạy và chạy integration tests, không chỉ biên dịch một snippet rồi suy bảo mật của toàn flow.

### 11.1. Luồng logic của `DelegatingOAuth2TokenGenerator`

~~~mermaid
flowchart TD
    C["Validated OAuth2TokenContext"] --> D["DelegatingOAuth2TokenGenerator"]
    D --> J["JwtGenerator"]
    J -->|"Can generate JWT for context"| JW["Signed JWT AT / OIDC ID token"]
    J -->|"Not applicable"| A["OAuth2AccessTokenGenerator"]
    A -->|"Reference AT context"| OPQ["Opaque AT"]
    A -->|"Not applicable"| R["OAuth2RefreshTokenGenerator"]
    R -->|"Refresh context"| RT["Refresh token"]
    R -->|"No supported generator"| ERR["Generation fails; no token issuance"]
~~~

Sơ đồ mô tả khả năng **delegation**; không giả định mọi request sẽ chạy qua JWT rồi opaque rồi refresh theo đúng trình tự trong tất cả SAS versions/configurations. Mỗi generator có thể trả **token** hoặc `null` khi context/token type không phù hợp; nếu không có generator hỗ trợ, flow phải fail chứ không phát generic untyped credential.

### 11.2. `RegisteredClient` quyết định grant và token format

Mẫu Java/Spring Authorization Server:

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

final class SalesDashboardRegistration {
    static RegisteredClient create(
            PasswordEncoder encoder, String secretFromVault) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId("sales-dashboard")
                .clientSecret(encoder.encode(secretFromVault))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://client.example.test/callback")
                .scope("openid")
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .authorizationCodeTimeToLive(
                                Duration.ofMinutes(2))
                        .accessTokenTimeToLive(
                                Duration.ofMinutes(5))
                        .refreshTokenTimeToLive(
                                Duration.ofHours(8))
                        .reuseRefreshTokens(false)
                        .accessTokenFormat(
                                OAuth2TokenFormat.SELF_CONTAINED)
                        .build())
                .build();
    }
}
~~~

**Giải thích:**

- `client_secret_basic` là **client authentication** của confidential client; secret thật phải từ secret manager, không hardcode/log.
- `requireProofKey(true)` yêu cầu PKCE theo client config; cần AS/client hỗ trợ `S256` và kiểm authorization request/token exchange thực.
- `authorizationCodeTimeToLive` điều khiển code TTL trong API/version tương ứng; code vẫn **single-use**.
- `accessTokenFormat(SELF_CONTAINED)` cấu hình **format** của AT, không tự cấu hình JWKS signer, audience/claims hoặc revocation.
- `reuseRefreshTokens(false)` liên quan rotation behavior, **không thay** transactionally safe RT family reuse detection.
- `requireAuthorizationConsent(true)` liên quan user consent, **không cho customizer tự thêm scopes**.

**Cần có** `RegisteredClientRepository`/password encoder/JWKSource/authorization service và server security filters đúng phiên bản; snippet này chỉ dựng registration. Nếu client là public SPA/native, không lưu static secret nhúng trong JS/app, dùng client authentication `NONE`, Code+PKCE và redirect URI profile phù hợp.

### 11.3. Chọn opaque access token

Với client/resource cần introspection, AS có thể đăng ký:

~~~java
.tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build())
~~~

Đây là **method chain trong `RegisteredClient` builder**, không phải class/file hoàn chỉnh. `REFERENCE` thường kích hoạt reference/opaque AT generator khi chain đúng; phải kiểm AS đang lưu/đáp introspection metadata, RS có client auth đến endpoint và kiểm `active`/audience/scope/token purpose.

### 11.4. `JwtEncoder` và key material

Một wiring ý tưởng:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@Bean
JwtEncoder jwtEncoder(
        JWKSource<SecurityContext> trustedSigningJwkSource) {
    return new NimbusJwtEncoder(trustedSigningJwkSource);
}
~~~

**Không tạo `JWKSource` bằng key hardcoded ở production.** Source phải được cấp quyền ký, có key lifecycle và JWKS publication phù hợp. KMS/HSM integration có thể cần custom `JwtEncoder` và remote signing policy; không bắt buộc dùng Nimbus `JWKSource` nếu kiến trúc khác, nhưng AS/RS vẫn phải có compatible signature algorithm, `kid` và trusted verification keys.

### 11.5. Custom `DelegatingOAuth2TokenGenerator`

Khi thực sự cần thay chain mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenGenerator<?> tokenGenerator(
        JwtEncoder encoder,
        OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
        OAuth2TokenCustomizer<OAuth2TokenClaimsContext>
                referenceCustomizer) {

    JwtGenerator jwt = new JwtGenerator(encoder);
    jwt.setJwtCustomizer(jwtCustomizer);

    OAuth2AccessTokenGenerator opaque =
            new OAuth2AccessTokenGenerator();
    opaque.setAccessTokenCustomizer(referenceCustomizer);

    OAuth2RefreshTokenGenerator refresh =
            new OAuth2RefreshTokenGenerator();

    return new DelegatingOAuth2TokenGenerator(
            jwt, opaque, refresh);
}
~~~

**Không copy nguyên chain vào mọi deployment**: SAS mặc định có thể tự cấu hình generator theo `JwtEncoder`, `JWKSource` và token-format settings; custom bean có thể ghi đè wiring mặc định hoặc ảnh hưởng issuance khác (OIDC ID token, authorization code/device/custom grants). Khi tự thay chain, **phải** test Authorization Code + PKCE, Refresh Token, Client Credentials, OIDC ID token và các extensions đang hỗ trợ. Nếu framework phiên bản cụ thể dùng generator riêng cho authorization code/device grants, giữ đúng chain/endpoint integration; không tự giả định ba generators ở ví dụ là đủ cho mọi loại grant.

### 11.6. Test sau khi đăng ký generator

Một bean khởi tạo thành công **không chứng minh** token issuance an toàn. Cần xác minh:

~~~text
Registered client has SELF_CONTAINED AT.
AS issues JWT AT with trusted iss, aud, typ, scope and exp.
RS verifies using trusted JWKS and rejects wrong aud/type/scope.

Registered client has REFERENCE AT.
AS issues opaque AT, stores authorized grant metadata.
RS introspects and rejects active token for a different resource.

OpenID login requests openid.
AS generates valid OIDC ID token for client_id and verified subject.
RS rejects ID token as OAuth AT.
~~~

Không dùng “token bắt đầu bằng eyJ” làm bằng chứng chắc chắn token thuộc đúng type hoặc có thể được RS chấp nhận.

## 12. Spring JWT customizer: claims có điều kiện theo token purpose

### 12.1. `OAuth2TokenCustomizer<JwtEncodingContext>`

JWT customizer có thể chỉnh JWS header và JWT claims **trước signing**. Quy tắc đầu tiên: **chỉ thay access-token claims khi token type là access token**; không tự đưa audience của business API vào ID token.

Ví dụ với một policy component do ứng dụng tự xây:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer(
        ApprovedTokenPolicy approvedTokenPolicy) {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return; // Keep OIDC ID token profile separate.
        }

        ApprovedTokenAttributes attributes =
                approvedTokenPolicy.resolve(
                        context.getRegisteredClient(),
                        context.getAuthorizationGrantType(),
                        context.getPrincipal(),
                        context.getAuthorizedScopes());

        context.getJwsHeader().type("at+jwt");
        context.getClaims().audience(
                List.of(attributes.audience()));
        context.getClaims().claim(
                "tenant_id", attributes.tenant());
    };
}
~~~

`ApprovedTokenPolicy` và `ApprovedTokenAttributes` là **domain abstractions phải triển khai riêng**, không phải classes Spring cung cấp. `resolve(...)` chỉ được trả audience/tenant sau khi kiểm **trusted registration, actual subject/actor, grant, scopes, resource request và tenant authority**. Không lấy audience từ HTTP header hoặc query do browser điều khiển. Với AT không gắn tenant, policy có thể **không đặt claim tenant** thay vì để `tenant_id="*"`.

### 12.2. Policy component nên có một allowlist có thể kiểm chứng

Ví dụ hợp đồng logic:

~~~text
Registered client: sales-dashboard
Allowed grant types: authorization_code, refresh_token
Authorized scope: orders.read
Allowed audience: orders-api
Subject: validated Alice
Tenant: verified company-a membership

Any other resource or arbitrary tenant requested:
  DENY issuance or apply explicitly documented narrowing.
~~~

**Chính sách này thuộc AS**, không nằm trong JWT builder. Với nhiều clients/resources, dùng registry/policy engine/bounded ABAC; không hardcode global `aud=orders-api` cho tất cả clients rồi cho mọi token đi qua cùng API.

### 12.3. Tại sao không lấy `request.getParameter("roles")`?

~~~java
// VULNERABLE CUSTOMIZER IDEA: never use client-supplied role.
context.getClaims().claim(
        "roles", request.getParameter("roles"));
~~~

Attacker có thể gửi `roles=admin`; AS ký claim giả, RS có thể tin. **Signature chỉ chứng minh AS đã ký**, không chứng minh claim có nguồn phù hợp. Custom claims phải đến từ trusted directory/entitlement service, verified principal và scoped AS policy.

### 12.4. Không tạo `sub` mới từ một username string

Với user-delegated code flow, subject đến từ original authenticated authorization. Với `client_credentials`, subject/identity là machine principal theo profile. **Không gán cùng `sub` cho hai user chỉ vì email giống nhau**; hệ thống OIDC dùng `(iss, sub)` như identity binding, và customizer không được phép tự biến service principal thành Alice.

### 12.5. ID token customizer là nhánh khác

OIDC ID token có claims phục vụ authentication:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": "sales-dashboard",
  "exp": 1893456000,
  "iat": 1893455700,
  "auth_time": 1893455600,
  "nonce": "login-nonce"
}
~~~

AS/OP phải áp OIDC Core rules (claim presence theo flow/request, `nonce` khi áp dụng, `auth_time` khi requested/required, audience/`azp` semantics). Không đặt `aud=orders-api` cho ID token vì đang tạo JWT ở cùng `JwtGenerator`; phải phân biệt bằng **token type/context**.

Trong một số Spring Authorization Server versions, ID token customization qua `JwtEncodingContext` dựa trên `context.getTokenType()` có giá trị `id_token`/OIDC constant; hãy dùng đúng API/constant của phiên bản và test token output với OIDC RP thật. **Tùy biến OIDC claims không thay thế ID token signature/issuer/nonce validation tại RP.**

### 12.6. Claims minimization và kích thước JWT

Không đưa toàn bộ roles/group lists, địa chỉ, hồ sơ cá nhân hoặc session state vào JWT chỉ vì customizer làm được. JWT quá lớn có thể:

- Bị reverse proxy từ chối vì HTTP header size.
- Rò PII vì payload Base64url decode được.
- Làm stale entitlements khi group membership thay đổi.
- Tăng bề mặt token substitution nếu cùng token được gửi nhiều RS.

Tốt hơn: chỉ đặt **minimum audience-specific claims**, dùng domain API/entitlement service hoặc opaque introspection khi cần dữ liệu động; định nghĩa schema/size limits và test worst-case group count.

## 13. Spring opaque token customizer: metadata cho introspection

### 13.1. `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>`

Với reference/opaque AT, giá trị token có thể chỉ là random secret; metadata do AS lưu. SAS `OAuth2AccessTokenGenerator` hỗ trợ customizer cho access-token claims khi phù hợp.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext>
referenceTokenCustomizer(ApprovedTokenPolicy policy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        ApprovedTokenAttributes approved = policy.resolve(
                context.getRegisteredClient(),
                context.getAuthorizationGrantType(),
                context.getPrincipal(),
                context.getAuthorizedScopes());

        context.getClaims().claim(
                "aud", List.of(approved.audience()));
        context.getClaims().claim(
                "tenant_id", approved.tenant());
    };
}
~~~

Ví dụ cần imports/bean wiring đúng SAS version. **Không** hiểu `OAuth2TokenClaimsContext` là introspection response HTTP: AS phải **lưu metadata** trong authorization service và cấu hình introspection endpoint cho RS được phép, có client authentication và profile scope/audience semantics.

### 13.2. `active=true` chưa chứng minh đúng resource

Response minh họa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "client_id": "sales-dashboard",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Resource Server `payments-api` phải **từ chối** vì audience là `orders-api`. Theo RFC 7662, các fields ngoài `active` có thể **optional**; nếu AS không trả `aud`, cần một **caller-specific/resource-bound introspection contract** đã được kiểm chứng hoặc thay đổi AS để cung cấp đủ binding, không chỉ tin `active=true` chung cho mọi tokens.

### 13.3. Introspection cache và revocation freshness

Một RS có thể cache positive introspection responses để giảm latency. Phải bảo đảm:

~~~text
cache key includes trusted AS / RS caller / token fingerprint
expected audience and token purpose cannot be confused
positive cache TTL <= token expiry and revocation freshness budget
revoked token must become rejected within promised SLA
cache failure never turns "unknown" into active=true
~~~

Nếu AS đã revoke RT/grant nhưng RS dùng cached `active=true` quá lâu, token có thể vẫn được chấp nhận. **Generator không tự điều khiển mọi RS cache**; AS/RS cần hợp đồng chung về trạng thái token.

### 13.4. Opaque AT không tự động là “RT”

Một chuỗi opaque có thể là AT, RT, code hoặc device code. **AS token purpose metadata** phải ngăn client gửi RT tới RS rồi được introspection trả active như AT; `token_type_hint=access_token` từ caller chỉ là hint, không chứng minh token type. RS phải xác minh contract và chỉ chấp nhận access-token purpose.

## 14. Generation, persistence và atomicity: sinh token không đồng nghĩa đã cấp thành công

### 14.1. Ba mốc khác nhau

Một request token có thể trải qua:

~~~text
GENERATED:
  Memory contains AT/RT values or signed JWT bytes.

COMMITTED:
  AS durable state records validated grant/token issuance,
  code redemption and/or RT rotation.

DELIVERED:
  Authorized OAuth client actually receives token endpoint response.
~~~

Ba mốc **không đồng nhất**. Một JWT được ký trong memory chưa chắc đã được ghi trạng thái hoặc gửi tới client. Một grant đã commit nhưng HTTP response bị mất sẽ tạo **unknown outcome** ở client. Token generator không được tự biến lỗi request network thành lý do phát **một bộ token khác** mà không kiểm grant lifecycle.

### 14.2. Authorization code chỉ đổi thành công một lần

Giả sử `C1` là code hợp lệ. Hai requests đến đồng thời:

~~~mermaid
sequenceDiagram
    participant A as AS Node A
    participant B as AS Node B
    participant DB as Authoritative Grant Store
    A->>DB: Check C1 / prepare atomic redeem
    B->>DB: Check C1 / prepare atomic redeem
    A->>DB: CAS C1 ISSUED -> REDEEMED + grant commit
    DB-->>A: winner
    B->>DB: CAS same C1
    DB-->>B: loser / 0 rows
    A-->>A: May return one issued token response
    B-->>B: Reject reused code; no token generation success
~~~

Một anti-pattern:

~~~java
// VULNERABLE: two AS replicas may both mint token families.
CodeRecord code = repo.findCode(rawCode);
if (code.isActive()) {
    var at = generator.generate(accessTokenContext);
    var rt = generator.generate(refreshTokenContext);
    repo.markUsed(rawCode);
    return new TokenResponse(at, rt);
}
~~~

**Đúng:** cần **atomic one-winner consumption/issuance** qua DB transaction, conditional update, unique grant-issuance key hoặc cơ chế nhất quán tương đương. Kiểm status rồi update hai bước không bảo vệ trên nhiều AS nodes. `synchronized` trong một JVM không bảo vệ giữa Pods.

### 14.3. SQL CAS minh họa

~~~sql
BEGIN;

UPDATE oauth_authorization_code
SET status = 'REDEEMED',
    redeemed_at = CURRENT_TIMESTAMP
WHERE code_fingerprint = :fingerprint
  AND status = 'ISSUED'
  AND expires_at > CURRENT_TIMESTAMP
  AND client_id = :authenticated_client
RETURNING authorization_id;

-- If zero rows: invalid_grant; do not mint/commit tokens.
-- Verify redirect URI, PKCE and all grant properties in
-- trusted application logic or guarded transaction.
-- Commit associated grant/token state consistently.

COMMIT;
~~~

Đây là **SQL/persistence pseudocode**, không phải schema Spring SAS/DDL production. PKCE verifier phải được kiểm với stored challenge; redirect URI phải so đúng request gốc; subject/scopes/audience phải đến từ authorization record. Một conditional update **không tự** bảo vệ nếu service phát JWT/RT ở database khác hoặc gửi response **trước commit**.

### 14.4. Mất response sau commit

~~~text
T0 Client sends POST /token code=C1, PKCE verifier V1.
T1 AS validates and commits redemption + grant G1.
T2 AS constructs HTTP 200 with AT1/RT1.
T3 Network drops response.
T4 Client sees timeout and retries C1.
T5 AS rejects C1 as already redeemed.
~~~

AS không được “giúp” bằng cách:

~~~text
if (usedCode && sameVerifier)
    return previouslyIssuedRefreshTokenAndAccessToken;
~~~

Điều này có thể **cho attacker có bản sao request** nhận lại credential từ token endpoint, phá single-use semantics. **Internal idempotency** ngăn tạo hai grants là đúng; **external repeat redemption** trả lại AT/RT từ một code đã dùng là thứ cần tránh trong Authorization Code Flow chuẩn. Client nên bắt đầu authorization flow **mới** nếu token không đến và không có một extension bảo mật chuyên biệt đã được duyệt.

### 14.5. Refresh-token rotation và concurrent redemption

Giả sử R1 là RT hiện tại và hai workers đồng thời dùng:

~~~text
Worker A: refresh R1 -> wants AT2 + RT2.
Worker B: refresh R1 -> wants AT3 + RT3.
~~~

Nếu AS không có **atomic rotate** thì R1 có thể phát hai RT descendants, làm mất token-family replay detection. Một chính sách rotation nên:

1. Xác minh R1 active/bound đúng client/grant.
2. Cấp **tối đa một successful rotation** cho family/version hiện tại.
3. Invalidate R1 khi commit R2/AT2.
4. Ghi parent/child/grant/family state đủ để phát hiện reuse.
5. Khi R1 bị replay, áp revoke/quarantine family theo security BCP/policy.
6. Không để worker retry sau timeout hồi sinh R1 hoặc lưu R2 sau logout.

**Token generator có thể sinh R2**, nhưng **grant provider/persistence** cần đảm bảo R2 không trở thành một “nhánh” ngoài ý muốn do concurrent requests.

### 14.6. Logout race với background refresh

~~~text
T0 Background worker starts refresh with R1.
T1 User logs out, BFF deletes session and asks AS to revoke grant.
T2 AS refresh R1 succeeds before revocation propagates.
T3 Worker stores R2 again into token cache after logout.
~~~

Một BFF có thể sử dụng **session/grant generation fencing** và compare-and-set:

~~~text
load grant generation = 7
on logout: mark LOGGING_OUT and bump generation = 8
worker completes refresh with R2
worker save only if generation is still 7 and ACTIVE
CAS fails → discard R2; reconcile grant/revocation safely
~~~

Đây là **client and AS lifecycle coordination**, không chỉ generator crypto. Đừng dùng một singleton refresh token store; cache phải partition theo issuer/client/user/tenant/grant/resource và phục vụ logout/revocation đúng scope.

### 14.7. Token signing thành công nhưng DB commit thất bại

Nếu AS đã ký JWT AT nhưng database transaction fail:

- **Không trả JWT** như token được phát hợp lệ nếu contract đòi server-side grant state.
- Nếu JWT đã được trả trước commit, RS có thể vẫn chấp nhận offline JWT dù AS không có authorization record: cần xem đây là issuance-consistency failure.
- Với opaque AT, RS introspection thường thấy inactive/unknown khi record chưa persist, nhưng không nên dựa vào điều đó để bỏ transaction correctness.
- Với RT, record không tồn tại hoặc mapping inconsistent làm refresh/revocation unpredictable.

Điều khiển **response-after-commit** khi cần và dùng outbox/unique issuance keys hoặc transactional persistence phù hợp. Không giả định một distributed mutex TTL ngắn thay unique/atomic durable constraint.

### 14.8. Multi-region, cache và failover

Trong active-active AS:

~~~text
Region A sees code C1 unused.
Region B sees code C1 unused because replication lags.
A issues grant G1.
B issues grant G2.
Later both replicate "REDEEMED".
~~~

Giải pháp cần **single authoritative write path**, strong-consistent CAS/quorum hoặc region/partition affinity có fencing và durable issuance constraints. Khi không chứng minh được one-winner, **fail closed**; không chuyển sang local in-memory generator/cache và tiếp tục cấp token để duy trì availability.

### 14.9. Authorization service trong Spring là một security dependency

Spring `OAuth2AuthorizationService` lưu/truy cập authorization state và các tokens được liên kết. Với production cluster, persistence adapter phải được đánh giá:

- Atomicity trên grant/redemption/rotation, không chỉ Java object serialization.
- Token-state lookup uniqueness và expires/revoked mapping.
- Concurrent requests trên **cùng grant/code/refresh family** qua nhiều nodes.
- Crash/restart/DB rollback/replica lag.
- Credential encryption at rest, access controls, log redaction và retention.

Không suy “đã cài `JdbcOAuth2AuthorizationService` nên mọi race automatically solved” nếu không có integration/fault-injection tests trên **datastore/isolation level cụ thể**.

## 15. Threat model của token generator

### 15.1. Claim injection

Attacker gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=payments.admin&aud=admin-api&sub=alice&tenant_id=company-b
~~~

Nếu AS tự đọc và ký raw parameters thành claims, token đúng chữ ký nhưng giả quyền/subject/tenant. **Defense:** authenticated client, allowed grant, validated scope/resource policy, subject/actor nguồn tin cậy, customizer không lấy untrusted request claims.

### 15.2. Weak randomness / predictable opaque bearer

AS dùng token value từ epoch timestamp + user ID, attacker có thể đoán các AT đang active. **Defense:** CSPRNG, entropy đủ theo token type, exact match lookup, collision-resistant durable constraints, rate limiting và revoke khi compromise.

### 15.3. Key trust/algorithm confusion

AS chọn `alg` từ client param hoặc RS tải `jku` untrusted, có thể tạo token forging/acceptance. **Defense:** trusted AS key policy, approved algorithms, signer private key protected, JWKS public-only, `kid` scoped to issuer, RS verify exact issuer/audience/type.

### 15.4. Overbroad audience/scope

Một client xin `orders.read` nhưng generator phát `aud=["*"]`, `scope="admin"`, khiến token bị dùng tại nhiều APIs. **Defense:** approval policy trước generation, resource indicators RFC 8707, least-privilege audiences/scopes, RS domain ACL.

### 15.5. Cross-JWT confusion

AS ký ID token và JWT AT bằng cùng key, RS chỉ verify signature rồi chấp nhận ID token. **Defense:** explicit token typing RFC 8725/RFC 9068, per-purpose validators, correct `aud` and scope. JWT ID token là **authentication assertion cho RP**, không phải bearer AT cho API.

### 15.6. Token exfiltration từ response/logs

Proxy/APM log `Authorization`, token endpoint body hoặc redirect `?access_token=...`. **Defense:** TLS/certificate validation, HTTPS token endpoint, `Cache-Control: no-store`, no bearer tokens in URL, logging redaction/retention và protected client storage.

### 15.7. Replay Authorization Code

Hai AS nodes đổi cùng code thành hai grants vì kiểm `USED` không nguyên tử. **Defense:** atomic code consumption and grant issuance, one-winner assertion, deny used codes and consider revoke previously issued tokens per RFC 6749.

### 15.8. Refresh-token theft/replay

Attacker lấy RT rồi rotate thành RT2, trong khi legitimate client còn RT1. **Defense:** rotation with reuse detection/token family, client binding, DPoP/mTLS sender constraints khi phù hợp, revocation/consent/session policy và replay audit.

### 15.9. Bearer AT theft và replay tại Resource Server

Code+PKCE/generator có thể hoạt động đúng nhưng AT bị lấy từ logs và replay. **Defense:** AT audience/scope/expiry, short TTL, sender-constrained access tokens (RFC 9449 DPoP/RFC 8705 mTLS) khi phù hợp, RS revocation/status/ACL. **DPoP proof là credential do client tạo**, AS chỉ bind AT với verified key/proof.

### 15.10. Consent/role freshness

User bị rút quyền payroll nhưng JWT AT còn `roles=["payroll-admin"]` đến khi `exp`. **Defense:** TTL/denylist/online policy checks cho high-risk actions; không coi JWT claims là dynamic live authorization database.

### 15.11. Side channels và oracle

Token issuance endpoint có thể tiết lộ user existence/grant status qua error details, timing hoặc logs. **Defense:** standard OAuth error codes, bounded error detail, rate limiting, consistent client authentication, audit không raw tokens. Không biến lookup fingerprint thành một endpoint tra “Alice đã login chưa?” cho client bất kỳ.

### 15.12. Test signing key trong production

AS fallback từ HSM timeout sang static dev private key. Attacker đã biết key có thể forge JWT. **Defense:** deployment config guard, key custody, separate test/prod issuers, fail closed nếu signer unavailable, prevent test keys from promotion and scan build artifacts.

### 15.13. Subject/actor confusion khi token exchange

Service A có quyền mạnh và xin token `sub=alice` cho admin API dù Alice chưa đồng ý. **Defense:** actor/subject/target delegation policy RFC 8693, no arbitrary impersonation, audience-constrained downstream AT và accurate audit.

### 15.14. Introspection cache mix-up

AS trả `active=true` cho opaque token dùng ở HR, `payments-api` dùng kết quả cache và cho phép. **Defense:** AS introspection response/RS caller contract có **audience/purpose binding**, cache partition theo AS/RS/resource, RS tự kiểm scope và ACL.

## 16. Vận hành: keys, metrics, rollback và incident response

### 16.1. Những chỉ số nên theo dõi

| Metric minh họa | Đo lường | Ý nghĩa bảo mật |
| --- | --- | --- |
| `as_token_issued_total` theo token type/client/policy | Issuance thành công | Bất thường khi số token hoặc scope tăng |
| `as_token_generation_failure_total` theo cause | Generator/crypto/policy lỗi | Key outage, missing aud, unsafe fallback |
| `as_jwt_sign_latency_seconds` | Signing KMS/HSM latency | Có thể ảnh hưởng retry/concurrency |
| `as_signing_key_unknown_total` | RS key lookup problem | Rotation/JWKS drift hoặc attacker JWT |
| `as_opaque_collision_total` | Lookup uniqueness conflict | CSPRNG/persistence bug, cần alert |
| `as_code_redeem_conflict_total` | Dùng lại/concurrent authorization code | One-winner enforcement/replay signal |
| `as_refresh_reuse_detected_total` | Old RT reused after rotation | Theft hoặc race/client bug |
| `as_invalid_audience_request_total` | Xin resource không được policy cho | Client misconfiguration/privilege probing |
| `as_token_claims_policy_denied_total` | Không có đủ trusted claims/tenant | Fail-closed policy audit |
| `as_token_revocation_total` theo outcome | RT/AT/grant revocation | SLA/logout monitoring |
| `as_introspection_active_false_total` | Token inactive/expired/revoked | Resource server behavior |
| `as_token_response_unknown_total` | Token endpoint response lost/timed out | Idempotency/retry analysis |
| `as_token_family_duplicate_descendant_total` | Rotation branch/unique constraint conflict | **Security alert**, kiểm multi-node issuance |

Tên là **ví dụ**, không phải standard Spring metrics. Không dùng raw AT/RT/ID token, `jti`, email/`sub`, client secrets hoặc full JWT payload trong labels/logs. Nên dùng registered client ID, issuer ref, token purpose, policy version, reason code và protected correlation ID.

### 16.2. Audit event bảo vệ bí mật

~~~json
{
  "event": "oauth_token_issuance",
  "decision": "GRANTED",
  "grant_type": "authorization_code",
  "client_registration_ref": "sales-dashboard",
  "token_profile": "jwt-at",
  "resource_ref": "orders-api",
  "approved_scope_set_ref": "orders-read-only",
  "issuer_ref": "company-as",
  "grant_ref": "<protected-correlation-ref>",
  "policy_version": "v8"
}
~~~

Không log raw token value, refresh family secret, signing key, client assertion, PKCE verifier hoặc full HTTP body. Nếu phải truy vết token, dùng protected non-reversible fingerprint hoặc grant reference có access control/retention.

### 16.3. Key rotation runbook

1. Tạo/gắn K-new trong protected key store, kiểm algorithm và permissions.
2. Publish **public K-new** qua trusted JWKS, không lộ private material.
3. Kiểm RS trust/JWKS refresh nhận K-new; test JWT ký bằng K-new.
4. Chuyển active signer sang K-new, phát `kid=new`.
5. Duy trì K-old verification đúng overlap budget cho tokens hợp lệ.
6. Ghi metrics reject/unknown kid, canary, rollback có kiểm soát.
7. Sau expiry/cache/skew policy, retire K-old; nếu compromised, ưu tiên revocation/incident plan khác bình thường.

Không coi rotation thành công chỉ vì AS phát JWT mới; **RS phải verify được token mới** mà không tin `jku` không được kiểm soát. Key compromise có thể buộc revoke/denylist và emergency process.

### 16.4. AS outage và fail closed

Nếu datastore/token signer unavailable:

- Trả error token endpoint thích hợp; **không** tự sinh unsigned JWT hay opaque token không được persist.
- Không bypass client authentication, grant validation, PKCE hoặc audience checks.
- Không tự đổi `aud`/`scope` thành wildcard.
- Không trả lại AT/RT từ unprotected retry cache.
- Monitor unknown outcomes và có recovery semantics cho client.

Đây là trade-off **availability vs authorization integrity**. Một token được phát không kiểm soát có thể tồn tại sau khi hệ thống hồi phục và gây ảnh hưởng rộng.

### 16.5. Incident khi phát hiện token generator phát sai quyền

Nếu generator phát `aud=payments-api` cho client chỉ được `orders-api`:

1. Dừng/canary rollback policy change làm phát sai, bảo đảm rollback không khôi phục key/permission yếu.
2. Xác định **token purpose, client, issuer, audience, scopes, subject/tenant và grant refs** qua audit metadata, không raw tokens.
3. Kiểm RS nào đã chấp nhận token sai; khoanh vùng object/tenant data accessed.
4. Thu hồi RT/grants/tokens khi AS hỗ trợ; với JWT offline RS cần denylist/session state/TTL strategy.
5. Kiểm key compromise/credential leakage có xảy ra hay chỉ là claim-mapping bug.
6. Bổ sung tests không cho role/resource/tenant claim lấy từ untrusted request.
7. Đánh giá privacy/compliance response theo mức độ truy cập sai.
8. Cập nhật runbook và policy/registration change control.

**Không báo “đã khắc phục toàn bộ” chỉ vì generator mới phát claims đúng**: các AT sai đã phát trước đó có thể còn `exp` và được RS tin nếu không có revoke/denylist.

## 17. Ma trận kiểm thử token generator (85 ca)

Thiết lập **test AS/OP** với các clients:

- `sales-dashboard` confidential Authorization Code + PKCE, OAuth/OIDC scopes.
- `inventory-sync` confidential Client Credentials, machine identity.
- `mobile-app` public client Code + PKCE.
- `partner-client` chỉ được audience/scope hạn chế.
- `orders-api`/`payments-api` là hai Resource Servers có trust/audience khác nhau.
- JWT signer/JWKS test, opaque reference token store, refresh family, fake clock và shared DB/AS nodes.

Kiểm thử **đúng ba kết quả**: token output/profile, AS durable state/grant và RS **accept/reject** theo recipient. Không kết luận generator an toàn chỉ vì `POST /token` trả HTTP 200. Token và key trong tests đều là **fixture vô hại**, không lấy production credential.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| G01 | Confidential client Code+PKCE hợp lệ, approved `orders.read` | AS phát AT đúng audience/scope và commit grant |
| G02 | OIDC Code Flow có `openid`, đúng subject/nonce/issuer | AS phát ID token đúng RP audience; RP verify được |
| G03 | Client Credentials của service hợp lệ | AS phát app-only AT, không giả end-user |
| G04 | Opaque AT được tạo cho resource đúng | Random reference, metadata/introspection đầy đủ và RS chấp nhận đúng resource |
| G05 | JWT AT theo RFC 9068 | JWS signature hợp lệ, `typ=at+jwt`, required claims/profile đúng |
| G06 | Client xin AT `aud=orders-api` và scope `orders.read` được phép | AS phát audience/scope đúng approved resource |
| G07 | Client gửi `scope=orders.admin` vượt registration/consent | AS không tự cấp admin scope |
| G08 | Client gửi `resource=payments-api` không được phép | AS từ chối hoặc policy narrowing có đặc tả, không wildcard |
| G09 | Client gửi `sub=admin` trong token request | AS không lấy client input làm verified subject |
| G10 | Client gửi `tenant_id=company-b` cho user tenant A | AS không tạo claim tenant B trái policy |
| G11 | `client_id` thuộc client khác với authenticated client | Token endpoint từ chối/binding đúng |
| G12 | Confidential client secret/private_key_jwt không hợp lệ | Không gọi successful token issuance |
| G13 | Public client không có secret nhưng PKCE S256 đúng | Có thể đổi code hợp lệ một lần theo public registration |
| G14 | Public client thiếu/sai PKCE verifier | Từ chối, không phát AT/RT |
| G15 | Authorization code hết hạn | `invalid_grant`, không mint token |
| G16 | Authorization code đã redeemed | `invalid_grant`, không mint thêm token |
| G17 | Code thuộc client A đem đổi cho client B | Từ chối cross-client binding |
| G18 | Code đổi với redirect URI khác request gốc | Từ chối redirect mismatch |
| G19 | Code có correct PKCE nhưng issuer/AS mix-up | Không gửi code/verifier tới AS lạ; flow bị từ chối |
| G20 | AT đúng `iss`, `aud=orders-api`, scope đủ, time valid | Orders RS chấp nhận token layer |
| G21 | Cùng JWT AT nhưng `aud=payments-api` gửi orders | Orders từ chối wrong audience |
| G22 | ID token hợp lệ đưa làm bearer tại orders | RS từ chối sai token type/purpose |
| G23 | RT dạng opaque còn active đưa làm bearer tới orders | RS không coi RT là AT |
| G24 | Client assertion JWT đưa vào business API | RS từ chối |
| G25 | DPoP proof JWT đưa làm bearer AT | RS từ chối wrong token purpose |
| G26 | JWT AT không có `exp` khi profile yêu cầu | AS không phát hoặc RS từ chối |
| G27 | JWT AT `exp≤iat` | Generator/profile guard từ chối |
| G28 | JWT `nbf` ở tương lai ngoài bounded skew | RS từ chối |
| G29 | JWT `exp` đã qua ngoài bounded skew | RS từ chối |
| G30 | `iat` dạng milliseconds thay vì NumericDate seconds | Test phát hiện sai epoch units/profile |
| G31 | AT lifetime client request cố nâng lên 1 năm | AS giữ configured TTL/policy cap |
| G32 | RT rotation không kéo dài absolute grant expiry trái policy | AS giới hạn family lifecycle |
| G33 | Code TTL 2 phút, dùng lại sau 10 giây đã consumed | Không redeem lần hai dù còn hạn |
| G34 | AS CSPRNG tạo nhiều opaque tokens | High entropy/unpredictability tests và không dễ đoán |
| G35 | Generator giả dùng timestamp + sequence làm opaque token | Security tests/static checks phát hiện |
| G36 | Opaque token collision được inject có chủ đích | DB uniqueness/handling không overwrite token record khác user |
| G37 | Opaque token fingerprint lookup partial/prefix match | Không chấp nhận token thiếu/mang suffix bất kỳ |
| G38 | Opaque AT bị revoke, introspection `active=false` | RS từ chối theo cache freshness contract |
| G39 | Opaque AT active=true nhưng `aud=payments-api` được hỏi tại orders | Orders từ chối |
| G40 | Introspection thiếu `aud` nhưng caller-bound contract không có | Fail closed; không chỉ dùng active=true |
| G41 | Introspection request có `token_type_hint=access_token` nhưng token là RT | Không được đổi mục đích RT thành AT |
| G42 | RS shared positive introspection cache giữa audiences | Test phát hiện cache trust-context substitution |
| G43 | JWT signed bằng active trusted signing key | RS verify đúng signature/kid/issuer |
| G44 | JWT có `alg=none` hoặc algorithm không allowlisted | RS từ chối |
| G45 | JWT header `jku` trỏ attacker JWKS | RS không tự trust key từ header |
| G46 | JWT dùng `kid` cùng chuỗi với key từ issuer khác | RS không cross-issuer trust |
| G47 | AS JWKS public response vô tình chứa private JWK params | Security test bắt lỗi nghiêm trọng |
| G48 | AS ký token với K-new đã publish, RS refresh JWKS | RS verify JWT mới |
| G49 | K-old bị bỏ trước khi tokens K-old hết hạn | Canary phát hiện valid-token rejection/regression |
| G50 | Signing KMS/HSM outage | AS fail closed, không ký bằng dev key |
| G51 | JWT AT thiếu `aud` do customizer bug | Resource validator từ chối |
| G52 | JWT AT `typ=JWT` thay `at+jwt` khi profile bắt buộc | RS từ chối cross-JWT confusion |
| G53 | OIDC ID token `aud=sales-dashboard` | RP nhận đúng, RS orders từ chối |
| G54 | OIDC ID token `nonce` sai request gốc khi nonce được sử dụng | RP từ chối login |
| G55 | OIDC ID token `iss` sai trusted issuer | RP từ chối |
| G56 | OIDC `aud` có nhiều clients, `azp` sai profile | RP từ chối theo OIDC rules |
| G57 | JWT customizer chạy cho ID token và gắn `typ=at+jwt` sai | Test phát hiện token-purpose contamination |
| G58 | Opaque customizer không lưu `aud` theo contract | AS/RS integration test fail thay vì bỏ audience |
| G59 | Machine AT từ client credentials được trình tại user-only route | RS/domain authorization từ chối |
| G60 | AT `scope=orders.read` nhưng order thuộc tenant khác | RS domain ACL từ chối |
| G61 | Service A xin token exchange cho `service-b` đúng policy | AS phát new audience-bound delegated AT |
| G62 | Service A xin token exchange `admin.write` trái delegation | AS từ chối privilege escalation |
| G63 | Service A forward nguyên AT `aud=service-a` tới service-b | B từ chối wrong audience |
| G64 | DPoP-bound AT và proof/key/`ath`/`htu` đúng | RS chấp nhận sender layer nếu AT/policy đúng |
| G65 | DPoP proof sai key/`jti` replay | RS từ chối |
| G66 | mTLS-bound AT và cert fingerprint sai | RS từ chối sender binding |
| G67 | Sender proof đúng nhưng AT wrong audience | RS vẫn từ chối |
| G68 | Hai requests cùng code C1 trên hai AS nodes | **Tối đa một** successful redemption/grant commit |
| G69 | 100 concurrent token requests cùng code C1 | One-winner, no duplicate RT families |
| G70 | CAS loser trả 0 rows | Không phát token từ loser |
| G71 | AS signs JWT nhưng DB transaction rollback | Không có externally successful issuance ngoài policy |
| G72 | Grant G1 commit, HTTP 200 response bị mất | Client outcome unknown; C1 không được redeem lần hai |
| G73 | Token endpoint retry C1 sau response loss | Từ chối reuse, không resend AT/RT từ cache |
| G74 | Redis/DB failover làm code C1 có vẻ chưa dùng | Durable CAS/unique issuance chặn replay |
| G75 | Multi-region eventual-consistency race | Fail closed hoặc one-winner; không hai grants |
| G76 | RT R1 refresh một lần, rotation thành R2 | R1 invalidated, R2 active, AT mới đúng policy |
| G77 | RT R1 bị dùng lại sau rotation | AS detect reuse, revoke/quarantine family theo policy |
| G78 | Hai concurrent refresh requests cùng R1 | Tối đa một successful rotation; không hai RT descendants |
| G79 | Refresh worker ghi R2 sau khi logout/session generation changed | CAS/fencing ngăn resurrection |
| G80 | Consent/role bị rút sau AT JWT đã cấp | RS revocation/TTL/domain checks theo SLA, không suy JWT đổi tự động |
| G81 | Token response gửi trong HTTP `Location` query | Regression test phát hiện và cấm AT/RT URL leakage |
| G82 | Token endpoint proxy/APM log raw code, RT, client secret hoặc AT | Redaction/security tests phát hiện |
| G83 | Spring `SELF_CONTAINED` registration nhưng JWT signer/config thiếu | AS fail safely, không tự tạo opaque/unsigned token sai contract |
| G84 | Spring `REFERENCE` AT introspection và JS customizer claims | Output/metadata đúng contract, không nhầm OIDC ID token |
| G85 | Thay `OAuth2TokenGenerator` bean custom rồi chạy Code, RT, OIDC, client credentials và device flow | Mỗi supported flow hoạt động đúng, không bypass policy |

### 17.1. Positive controls là bắt buộc

Để kiểm đúng audience của AT, test:

~~~text
Positive:
  trusted AS signs JWT AT with iss=expected,
  aud=orders-api, typ=at+jwt, exp future,
  scope=orders.read.
  → Orders resource server accepts token layer.

Negative:
  Same issuer/key/subject/scope/time/type,
  change only aud=payments-api.
  → Orders resource server rejects.
~~~

Nếu cả hai token đều bị từ chối vì RS không tải được trusted JWKS, test **chưa chứng minh** audience validator. Nếu cùng token `aud=orders-api` bị từ chối ở domain ACL vì order thuộc Bob, hãy tách **token validation** và **object authorization** để test đúng lớp.

### 17.2. Token generator claim policy tests

~~~text
Setup:
  client=sales-dashboard
  approved scopes=[orders.read]
  approved aud=[orders-api]
  verified tenant=company-a

Test A: request scope orders.read
  → generated AT scope=orders.read.

Test B: request scope orders.admin
  → no admin scope granted.

Test C: request tenant_id=company-b
  → generated token must not contain company-b as trusted tenant.

Test D: request sub=admin
  → generated token subject must remain trusted principal.
~~~

Khi một request bị AS từ chối trước generator, đó là kết quả đúng **AS policy**; đừng tự đưa test malicious request vào customizer rồi chỉ assert nó ignore param khi token provider chưa xác thực client.

### 17.3. Atomic Code Grant test bằng concurrency barrier

~~~text
Setup:
  C1 status=ISSUED, expires in 2 minutes.
  Two valid requests have same C1, correct PKCE and client.

Worker A: validate and wait just before atomic consume.
Worker B: validate and wait just before atomic consume.
Release both workers.

Require:
  successful redemption count == 1
  grant commit count == 1
  new refresh token family count <= 1
  loser receives no token
  replay status remains denied after crash/restart.
~~~

Một test `synchronized` trong cùng JVM không mô phỏng hai AS Pods. Cần chạy trên **real shared authorization store**, DB isolation config, two-node deployment, replication/failover scenario và xác nhận tokens thật sự được minted/committed.

### 17.4. Refresh rotation and logout race

~~~text
Worker Refresh reads R1, generation=7, waits at barrier.
Worker Logout marks session/grant LOGGED_OUT, generation=8.
AS revocation/cleanup runs according to policy.
Release Refresh; even if AS returns R2,
  client store CAS generation==7 fails.
R2 must not restore authenticated session.
~~~

Test server-side **RT family state** riêng với client token cache. Không chỉ kiểm UI đã logout; thử refresh R1/R2 theo AS policy, kiểm revoked grants và RS ability to reject old AT theo expiry/revocation SLA.

### 17.5. Fault injection với KMS, store và HTTP

| Lỗi được tiêm | Kết quả an toàn |
| --- | --- |
| KMS signing timeout | Không fallback unsigned/test signing key; không commit issuance trái policy |
| DB commit failure sau JWT signing | Không trả token như success trước durable commit |
| HTTP 200 bị mất sau commit | Client unknown outcome; AS vẫn deny replay code |
| JWKS publish fail khi bắt đầu key mới | Rollback signing switch hoặc đảm bảo RS verification path, không phát tokens RS không verify được |
| Opaque introspection endpoint tạm outage | RS fail closed hoặc dùng cache còn hợp lệ trong budget, không auto active=true |
| Redis failover/replication lag | Durable one-winner code/refresh issuance state vẫn đúng |
| Clock jump / `exp` overflow | Generator không phát token quá hạn/vô hạn |

### 17.6. Các tests phải kiểm privacy/transport

Một bộ test end-to-end nên xác nhận:

~~~text
NO access_token / refresh_token / id_token in:
  - URL query, path, fragment and HTTP Location redirects
  - public client HTML bootstrap and analytics payloads
  - reverse proxy / WAF / ingress / APM logs
  - exception messages and support tickets

YES:
  - HTTPS token response to authenticated/approved client
  - Cache-Control: no-store
  - protected client storage
  - RS audience/scope/expiry/type/ACL checks
~~~

PKCE verifier, authorization code và client credentials cũng là bí mật cần redaction. Trong test dùng fake values, không thu thập raw production tokens để “kiểm tính ngẫu nhiên”.

## 18. Bảy tình huống thực tế: triệu chứng, nguyên nhân và sửa đúng

### Tình huống A: AS ký JWT hợp lệ nhưng phát nhầm audience admin

**Bối cảnh:** `sales-dashboard` chỉ được gọi `orders-api`. Một developer thêm customizer:

~~~java
// ANTI-PATTERN: client-controlled audience, do not deploy.
context.getClaims().audience(
        List.of(request.getParameter("audience")));
~~~

Attacker gửi `audience=admin-api`. JWT được AS ký đúng và `exp` còn hạn, nhưng **admin-api** đang chỉ verify chữ ký/issuer và chấp nhận token.

**Nguyên nhân:** Claim injection ở AS generator kết hợp thiếu recipient policy ở RS. **Chữ ký đúng không bảo đảm AS đã duyệt quyền.**

**Sửa:** AS approved-resource policy lấy từ client registration/grant/subject, không từ raw client input; RS check expected `aud=admin-api`, scope và ACL. Rà soát tokens đã phát sai, revoke/denylist theo SLA, thêm negative tests cho unauthorized resource. Không chỉ đổi `aud` ở một UI mà bỏ server-side validation.

### Tình huống B: Opaque token đoán được bằng timestamp

**Bối cảnh:** Hệ thống tự viết opaque AT value:

~~~text
opaque_token = "at-" + epochMillis + "-" + clientId
~~~

Attacker suy thời điểm phát, đoán token values và thử introspection/API. Một số token đoán trúng có thể còn hiệu lực.

**Nguyên nhân:** Giá trị bearer token thiếu entropy; có prefix/time/client ID không làm nó an toàn.

**Sửa:** CSPRNG entropy đủ mạnh, token collision constraints, exact lookup, rate limiting/replay monitoring, revoke exposed tokens và xóa source tạo token yếu. Không chỉ Base64 encode timestamp hoặc UUID predictable để “làm token nhìn ngẫu nhiên”.

### Tình huống C: Có JWT signer nhưng không cấu hình mục đích token

**Bối cảnh:** AS phát OIDC ID token và OAuth AT bằng cùng JWS signing key. `orders-api` kiểm signature/expiry, chấp nhận mọi JWT của issuer, nên client gửi ID token làm Bearer và gọi API thành công.

**Nguyên nhân:** Cross-JWT token confusion (RFC 8725), thiếu token type/purpose và audience validation.

**Sửa:** JWT AT profile RFC 9068 nếu AS/RS hỗ trợ: `typ=at+jwt`, `aud=orders-api`, scopes; OIDC ID token có `aud=client_id` và RP validation riêng. RS verify issuer/signature/typ/aud/expiry/scope/ACL; không dùng một generic decoder “mọi JWT cùng key đều hợp lệ”.

### Tình huống D: KMS timeout làm AS fallback sang khóa test

**Bối cảnh:** Token endpoint gặp KMS latency, team thêm fallback private key trong config để “không mất login”. Một test key đã xuất hiện trong development artifact; attacker ký JWT claims tùy ý và RS tin JWKS cũ.

**Nguyên nhân:** **Crypto fail-open**, key custody và môi trường test/prod không tách rời. JWT signing thành công không đồng nghĩa token do trusted production security process phát hành.

**Sửa:** Fail closed khi KMS key/signer không sẵn, harden permission/key IDs, phát trusted JWKS chính xác, rotation và incident response. Không đưa private signing keys vào source hoặc logs; kiểm RS key trust và token purpose/audience ngay cả khi signer hợp lệ.

### Tình huống E: Double-mint refresh token trên hai AS nodes

**Bối cảnh:** Hai request Refresh Token Grant dùng RT R1 cùng lúc. Node A sinh RT R2, Node B sinh RT R3, cả hai save dù R1 đáng lẽ single-use theo rotation policy.

**Nguyên nhân:** Generator tạo values đúng nhưng **authorization persistence không atomic**, không có one-winner family transition. Status cuối của R1 có thể là revoked mà vẫn có hai descendants active.

**Sửa:** Durable RT family, compare-and-set generation/version, unique descendant constraint, reused-old-RT detection/revocation và fail-closed khi store unavailable. Test trên hai nodes/barrier cùng datastore, không chỉ test `OAuth2RefreshTokenGenerator` unit.

### Tình huống F: Opaque introspection trả active nhưng sai Resource Server

**Bối cảnh:** AS phát opaque AT với metadata `aud=hr-api`. `payroll-api` gọi introspection và thấy `active=true`, cho phép vì code RS chỉ đọc cờ `active`.

**Nguyên nhân:** Introspection status được coi là toàn bộ authorization. AS generator có thể phát audience đúng nhưng RS đã **bỏ resource binding**.

**Sửa:** AS cung cấp aud/purpose metadata hoặc RS-specific introspection contract được test; RS so audience/scopes/object ACL. Cache introspection phải partition theo AS/RS/expected resource và bounded freshness. Không sửa bằng cách làm mọi AT có `aud=["hr-api","payroll-api"]`.

### Tình huống G: JWT AT đã cấp vẫn được RS chấp nhận sau logout

**Bối cảnh:** Alice nhận JWT AT `exp=10:15` và RT R1. Tại 10:02 Alice logout, RP hủy session, AS revoke RT. Attacker đã đánh cắp JWT AT và vẫn gọi `orders-api` lúc 10:04; RS chỉ verify JWS/exp.

**Nguyên nhân:** Token generator và RS đang dùng **self-contained JWT offline validation**, còn revocation chủ yếu tác động RT/grant. JWT signature và `exp` không tự đổi khi logout.

**Sửa:** Thiết kế logout/AT revocation SLA từ trước: AT TTL ngắn, denylist/session-state checks, opaque introspection nếu phù hợp và sender-constrained AT cho threat model. Không tuyên bố “logout đã hủy mọi token” nếu RS còn accept JWT cũ; đo thực tế freshness của RS.

## 19. Checklist production cho token generator và token issuance

### 19.1. Grant/policy trước generation

1. **Registered clients:** Client ID, authentication method, allowed grants, redirect URIs, scopes/resources rõ và được quản trị?
2. **Client authentication:** Confidential client secret/private-key JWT/mTLS kiểm theo registration, public client không bị gắn static secret giả?
3. **PKCE:** Code Flow dùng S256 khi policy yêu cầu, code verifier gắn authorization transaction đúng?
4. **Single-use authorization code:** Code TTL ngắn và atomic one-winner trên mọi AS nodes?
5. **Subject:** Verified user/service/actor identity không lấy raw `sub` từ token request?
6. **Scope:** Granted scope là kết quả consent/admin/AS policy, không tự mở rộng từ requested scope?
7. **Resource/audience:** Issuer/resource indicators được AS approve, không wildcard/default broad?
8. **Tenant/actor:** Các claims multi-tenant/delegation có source tin cậy và policy ràng buộc?
9. **Token exchange:** Client/subject/actor/target/scope được phép trước khi mint downstream AT?
10. **Fail closed:** Thiếu authorization context/consent/registration/entitlement không tự phát token?

### 19.2. Format, entropy và token purpose

11. **Token profiles:** JWT AT, opaque AT, RT, OIDC ID token, code/device code có purpose và validator riêng?
12. **Entropy:** Opaque AT/RT/code sinh từ CSPRNG đủ mạnh, không timestamp/counter?
13. **Uniqueness:** Token fingerprints/IDs có unique constraint và collision handling an toàn?
14. **JWT AT typing:** RFC 9068 `typ=at+jwt`/profile được áp nếu contract dùng; ID token không bị gắn AT type?
15. **Issuer:** `iss` ổn định/trusted, không lấy untrusted Host/Forwarded header?
16. **Audience:** AT audience theo RS, ID token audience theo RP/client, không tráo?
17. **Subject/client:** `sub`/`client_id`/`azp`/actor semantics được định nghĩa theo grant/profile?
18. **Scope:** Claims chứa exact authorized scopes, không substring hoặc client-injected role?
19. **Custom claims:** PII tối thiểu, schema/size/retention rõ, không đưa arbitrary business object vào JWT?
20. **Sender binding:** DPoP/mTLS `cnf` chỉ gắn khi proof/certificate đã được xác minh đúng profile?

### 19.3. Crypto, keys và thời gian

21. **JWS algorithms:** Allowlist thuật toán và key types được phê duyệt, không `alg=none`/algorithm confusion?
22. **Private keys:** KMS/HSM/keystore bảo vệ signing key, không hardcode hoặc publish trong JWKS?
23. **JWKS:** Public keys chỉ từ issuer trusted metadata/config, `kid` scoped, không follow attacker `jku`?
24. **Rotation:** Overlap key validity, RS JWKS refresh/caches, emergency key compromise procedure?
25. **KMS outage:** Fail closed, không fallback dev signer hoặc bỏ signature?
26. **TTL:** AT/RT/ID/code/device lifetimes theo policy, không do client tự đặt?
27. **Timestamps:** `iat`, `nbf`, `exp`/epoch units/overflow/bounded skew được kiểm?
28. **Revocation SLA:** JWT offline vs opaque introspection và RS cache freshness đã định lượng?
29. **Claims freshness:** Role/tenant changes trong JWT không bị coi là live ACL vô hạn?
30. **Token sizes:** JWT header size/claims cardinality/privacy và gateway limits được test?

### 19.4. State/persistence và concurrency

31. **Authorization service:** Persistent grant/token state có bảo vệ encryption/access controls/retention?
32. **Code CAS:** Concurrent redeem cùng code chỉ commit một grant/token family?
33. **RT rotation:** Old RT invalidated atomically, reuse detection/family revocation theo policy?
34. **No double-mint:** DB retry/queue redelivery/KMS timeout không phát hai RT descendants?
35. **Lost response:** HTTP 200 mất không dẫn AS trả lại token qua insecure replay code cache?
36. **Commit-before-response:** Grant/token-state consistency được bảo đảm trước khi coi request success?
37. **Multi-node:** Đã test 2+ AS nodes, DB isolation, Redis failover, replication lag và region partition?
38. **Logout race:** Background refresh không thể ghi RT mới vào session đã invalidated?
39. **Opaque introspection:** `active`/audience/token purpose/scopes mapping đúng, RS-specific caller authentication?
40. **Error handling:** Khi policy/crypto/store unavailable, không phát bearer token “tạm thời”?

### 19.5. Spring integration, vận hành và test

41. **SAS versions:** `OAuth2TokenGenerator`, `JwtGenerator`, customizers và `TokenSettings` tương thích phiên bản đang deploy?
42. **Generator chain:** Thay `DelegatingOAuth2TokenGenerator` không làm hỏng ID token, code, RT/device/custom grants?
43. **SELF_CONTAINED vs REFERENCE:** Registration dùng format đúng, RS có validators/introspection tương ứng?
44. **JWT customizer:** Chỉ chỉnh AT claims cho `ACCESS_TOKEN`, không làm ô nhiễm OIDC ID token profile?
45. **Opaque customizer:** Claims metadata được persist và RS introspection nhận contract đúng?
46. **Resource server tests:** Verify đúng issuer, signature/`active`, audience, purpose, time, scopes và object/tenant ACL?
47. **Negative tests:** Wrong scope/aud/tenant/subject, code replay, RT reuse, key errors và token-type confusion đều được test?
48. **Positive tests:** Có valid issued tokens/flows được accept trước khi kiểm wrong-audience hoặc expiry cases?
49. **Log/privacy:** Không raw AT/RT/ID/code/verifier/client secret trong body logs, URL/redirects, APM hoặc support tools?
50. **Operations:** Metrics, signer rotation runbook, token revocation/incident response và issuance policy change control đã có owner?

## 20. Câu hỏi tự kiểm tra, tài liệu tham khảo và kết luận

### 20.1. Hai mươi hai câu hỏi tự kiểm tra

**Câu 1. Token generator khác token endpoint như thế nào?**

**Token endpoint** xử lý OAuth request/grant/client authentication; **token generator** tạo giá trị token và metadata/claims theo một context **đã được AS xác thực và phê duyệt**. Authorization persistence và RS validation là các lớp khác.

**Câu 2. Có thể cho token generator lấy `scope=admin` trực tiếp từ HTTP request không?**

Không. Client có thể **yêu cầu** scope nhưng AS phải kiểm grant/client/subject/consent/policy; generator chỉ nhận **authorized scopes**. Nếu customizer đưa raw `scope` vào JWT, AS đang ký một quyền chưa được phê duyệt.

**Câu 3. Opaque AT có thể là một chuỗi random và RS không đọc được claims không?**

Có. Opaque AT thường là một reference secret được AS ánh xạ tới metadata; RS dùng trusted introspection và vẫn phải kiểm `active`/audience/purpose/scope/ACL theo contract.

**Câu 4. JWT ký số có giữ bí mật các claims không?**

Không. JWT JWS bảo vệ authenticity/integrity; payload có thể Base64url decode. Không nhét PII/secret vào JWT. Nếu cần confidentiality, đánh giá JWE hoặc opaque format cùng policy/phần mềm phù hợp.

**Câu 5. Một JWT có chữ ký đúng có tự cấp quyền gọi mọi API trong tổ chức không?**

Không. Resource Server cần **expected issuer, audience, token type, expiry, scope và domain ACL**; ký đúng không chứng minh AT dành cho RS đó.

**Câu 6. Refresh token có phải access token thứ hai với TTL dài không?**

Không. RT dành cho **AS token endpoint** để xin AT mới theo grant/client policy; nó có rotation/reuse/revocation riêng và không được RS chấp nhận như AT.

**Câu 7. ID token OIDC có dùng làm Bearer AT được không?**

Không. ID token là authentication assertion cho RP/client, `aud` thường là client ID, có validation `nonce`/`auth_time`/`azp` theo OIDC. API cần OAuth access token profile đúng recipient/scope.

**Câu 8. Tại sao opaque token cần CSPRNG?**

Nó là **bearer secret**. Nếu giá trị dễ đoán bằng timestamp/counter/`Random` yếu, attacker có thể guess token còn active và gọi RS. Entropy cao, uniqueness constraints và online abuse controls đều cần.

**Câu 9. Một token có `jti` duy nhất thì có tự chống bearer replay không?**

Không. `jti` chỉ là identifier; nếu RS không lưu trạng thái chống replay, sender proof hoặc revocation policy, cùng AT bearer vẫn có thể được trình lại trong TTL.

**Câu 10. `kid` trong JWT header có được dùng làm URL tìm signing key tự do không?**

Không. `kid` là selector trong **trusted issuer-specific JWKS**. Không để token chưa verify chỉ định attacker `jku`/`x5u` hoặc ép verifier chuyển thuật toán.

**Câu 11. Khi xoay khóa, vì sao cần overlap giữa K-old và K-new?**

AT đã cấp bởi K-old có thể còn hợp lệ tới `exp`. RS cần verification key tương ứng trong transition window; K-new phải được publish/caches nhận trước khi AS ký bằng nó. Key compromise có thể cần emergency revoke thay vì overlap bình thường.

**Câu 12. Nếu KMS signing unavailable, AS có nên ký bằng khóa thử nghiệm?**

Không. Đó là fail-open security flaw. AS nên trả lỗi có kiểm soát, không phát token không tin cậy; khôi phục signer/KMS qua operational runbook.

**Câu 13. `OAuth2TokenFormat.SELF_CONTAINED` và `REFERENCE` khác nhau ở đâu?**

Trong Spring Authorization Server, `SELF_CONTAINED` thường dùng JWT AT có thể verify offline, còn `REFERENCE` thường tạo opaque AT tra metadata/introspection. **TokenSettings không tự bảo đảm** audience/type/claims hoặc revocation; phải cấu hình generator, AS state và RS đúng.

**Câu 14. `DelegatingOAuth2TokenGenerator` làm gì?**

Nó điều phối nhiều `OAuth2TokenGenerator` dựa trên token context/type/format. Có thể kết hợp `JwtGenerator`, `OAuth2AccessTokenGenerator` và `OAuth2RefreshTokenGenerator`. Khi thay default chain, phải test OIDC ID token/code/device/custom grants theo version.

**Câu 15. Vì sao `JwtEncodingContext` cần kiểm token type trước khi thêm claims?**

Vì cùng JWT generator có thể tạo **OAuth AT** và **OIDC ID token**. Nếu customizer gắn `typ=at+jwt`, `aud=orders-api` cho ID token, sẽ tạo cross-token-type confusion và phá OIDC RP validation.

**Câu 16. Có thể đặt `exp` lấy từ `expires_in` do client gửi để tăng khả dụng không?**

Không. Client không quyết định token TTL vượt AS/token policy; generator tính thời hạn từ **trusted server clock** và registered client settings/risk policy, với giới hạn tối đa và overflow/skew checks.

**Câu 17. Vì sao generator hoạt động đúng nhưng hai AS nodes vẫn có thể phát hai RT từ cùng code?**

Vì lỗi có thể nằm ở **grant consumption/persistence atomicity**, không phải crypto generator. Cần one-winner CAS/transaction/unique issuance state giữa nodes, không chỉ `synchronized` ở một JVM.

**Câu 18. Nếu AS commit grant nhưng HTTP 200 bị mất, client có quyền dùng lại code để nhận AT/RT không?**

Không theo Authorization Code Flow chuẩn. Code single-use; AS phải từ chối reuse. Client coi outcome unknown và thực hiện authorization mới nếu cần, không yêu cầu AS resend token từ một code đã consumed như insecure idempotency cache.

**Câu 19. Refresh-token rotation có tự phát hiện kẻ tấn công không?**

Không chỉ bằng việc tạo R2. AS cần **durable family relationship, atomic invalidation của R1, detection khi R1 reused, policy revoke/quarantine** và sender binding khi phù hợp. Hai concurrent refresh requests cần được test.

**Câu 20. Tại sao `active=true` từ introspection chưa đủ cho mọi Resource Server?**

Vì token có thể active nhưng **`aud` dành cho API khác**, hoặc token là RT/khác purpose. RS phải kiểm resource/purpose/scope theo AS introspection contract, có caller-specific binding khi metadata thiếu và domain ACL riêng.

**Câu 21. JWT AT đã cấp và còn `exp` có tự bị từ chối ngay sau logout không?**

Không nếu RS chỉ verify JWT offline và không có status/denylist check. Cần đánh giá AT TTL, revoke/grant state, RS introspection/session checks, sender constraints và revocation freshness SLA.

**Câu 22. Test quan trọng nhất khi thay custom token generator là gì?**

Một tập **positive/negative integration tests** từ grant hợp lệ đến RS acceptance, cộng concurrency/fault injection: đúng scopes/aud/type/issuer/key, code single-use, RT rotation one-winner, OIDC ID token tách biệt, opaque introspection, wrong audience rejection, KMS/DB outage fail-closed.

### 20.2. Tài liệu tiêu chuẩn và hướng dẫn triển khai

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, authorization grants, access/refresh tokens, authorization code single-use và client binding.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, bearer/refresh token protection, resource isolation, reuse detection và security practices cho AS/RS.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge`/S256, authorization code interception protection.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`/`sub`/`aud`/`iat`/`nbf`/`exp`/`jti` và JWT NumericDate semantics.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS, protected headers, signature algorithms và key usage.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, key types/`kid`, public verification keys.
- [RFC 7516 — JSON Web Encryption](https://www.rfc-editor.org/rfc/rfc7516): JWE confidentiality, khác với JWS signature.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, key trust, cross-JWT confusion, explicit typing và issuer/audience checks.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `typ=at+jwt`, OAuth JWT AT required claims/profile và resource server validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque/active token metadata, RS caller authorization, optional claims và cache/security concerns.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): AT/RT revocation endpoint và contract.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource-bound access token requests, audience restriction.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): actor/subject/target token semantics và downstream delegation.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens và proof key binding.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và certificate-bound access tokens.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device code/user code generation, verification và polling lifecycle.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token profile, `iss`, `aud`, `nonce`/`auth_time`, RP/OP responsibilities.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer/OP metadata/JWKS trust.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`/`TokenSettings`, `OAuth2AuthorizationService`, `OAuth2TokenGenerator`/customizers.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization/token/introspection/revocation endpoints và grant policies.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): AS filters/beans/generator wiring và customization.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): trusted `JwtDecoder`, issuer/audience/expiry validation và scope mapping.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, active/metadata validation.
- [Spring Security — OAuth2 Login and Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): client registration, authorization code flow và protected token usage.

**Điểm cần ghi nhớ:** **Token generator trong Authorization Server là thành phần tạo giá trị và claims của token từ context đã được AS xác thực/ủy quyền**, không phải nơi cấp quyền tùy ý theo request client. Generator có thể tạo **opaque AT với CSPRNG và server-side metadata**, **JWT AT với JWS signer/JWKS, `iss`/`aud`/`typ`/`scope`/`exp`**, **refresh token** theo grant rotation policy và **OIDC ID token** dành cho RP — mỗi loại có mục đích và validation riêng. Spring Authorization Server cung cấp **`OAuth2TokenGenerator`, `DelegatingOAuth2TokenGenerator`, `JwtGenerator`, `OAuth2AccessTokenGenerator`, `OAuth2RefreshTokenGenerator` và customizers** để cấu hình pipeline theo phiên bản. **Crypto đúng chưa đủ:** phải kiểm client/grant/policy, ký/ngẫu nhiên hóa an toàn, cấp token cho đúng resource/subject, commit authorization state **nguyên tử** khi cần, chống code replay/refresh-token reuse, bảo vệ key/token/logs, theo dõi revocation và để Resource Server kiểm issuer/audience/type/time/scope/object ACL. **Một JWT ký hợp lệ vẫn là lỗi bảo mật nếu AS phát sai quyền hoặc RS nhận sai token purpose.**
