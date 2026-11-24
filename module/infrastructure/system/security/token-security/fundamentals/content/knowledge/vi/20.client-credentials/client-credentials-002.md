# Client authentication methods

Trong OAuth 2.0, **client authentication** là quá trình **authorization server (AS) xác minh danh tính của ứng dụng OAuth client** ở một endpoint yêu cầu xác thực client, điển hình là **token endpoint**. Nó trả lời câu hỏi: *“Ứng dụng nào đang xin token và có chứng minh được mình chính là client đã đăng ký không?”* Đây là câu hỏi **khác** với việc người dùng đã đăng nhập hay một access token có quyền đọc bản ghi nào.

Ví dụ, dịch vụ Java `billing-worker` cần gọi Orders API mà không có người dùng tương tác. Dịch vụ gửi `grant_type=client_credentials` tới AS và xác thực bằng `client_secret_basic`, một JWT assertion ký bằng private key, hoặc mTLS. Nếu AS chấp nhận, nó cấp **access token đại diện cho ứng dụng/service principal**. Orders API vẫn phải kiểm tra token đúng issuer, audience, hạn và scope; **client đã xác thực không tự trở thành administrator của mọi tenant**.

Trong chương **Client credentials** thuộc module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học **“Client authentication methods”** trình bày `client_secret_basic`, `client_secret_post`, `client_secret_jwt`, `private_key_jwt`, mTLS, trường hợp `none` của public client, và mối liên hệ với OAuth 2.0/OIDC, JWT/opaque access token, refresh token, scope/audience, lưu trữ, thu hồi, chống token theft/replay.

> **Nguyên tắc:** Client authentication xác minh **OAuth client với AS**; user authentication xác minh **người dùng**; access-token validation xác minh **token với RS**; authorization kiểm tra **quyền trên dữ liệu**. Không cơ chế nào tự thay thế ba cơ chế còn lại.

## 1. Vị trí của client authentication trong OAuth 2.0

| Vai trò | Công việc | Điểm cần phân biệt |
| --- | --- | --- |
| **Resource owner** | Chủ thể sở hữu hoặc kiểm soát quyền với tài nguyên; thường là user | Có thể xác thực tại AS/OP trong delegated grant |
| **Client** | Ứng dụng xin và sử dụng token | Phải chứng minh client identity nếu là confidential client và endpoint yêu cầu |
| **Authorization server (AS)** | Xác thực client, kiểm tra grant/policy, cấp/thu hồi token | Không cấp quyền chỉ vì tên `client_id` được khai |
| **Resource server (RS)** | API nhận access token | Kiểm tra token và quyền truy cập từng tài nguyên |

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Java service / OAuth client
    participant AS as Authorization server
    participant RS as Orders API
    C->>AS: POST /token grant_type=client_credentials
    Note over C,AS: client_secret_basic / private_key_jwt / mTLS
    AS->>AS: Validate client, method, grant, scopes, audience
    AS-->>C: JWT hoặc opaque access token
    C->>RS: GET /orders + Authorization Bearer token
    RS->>RS: Validate iss, aud, exp, scope, tenant, ownership
    RS-->>C: 200 / 401 / 403
~~~

Trong luồng này có **hai credential trao đổi khác nhau**:

1. **Client → AS:** client secret, JWT assertion hoặc chứng chỉ mTLS chứng minh client identity và chỉ được gửi tới endpoint phù hợp của AS.
2. **Client → RS:** access token được AS cấp; RS không nhận client secret làm bằng chứng quyền API trừ khi có giao thức riêng được thiết kế rõ.

AS có thể cấp **JWT hoặc opaque access token** bất kể client đã dùng Basic, JWT assertion hay mTLS để xác thực. Từ “JWT” trong `private_key_jwt` **không có nghĩa access token phải là JWT**.

## 2. Client authentication khác user authentication, PKCE và authorization

| Câu hỏi | Bằng chứng phổ biến | Bên kiểm tra |
| --- | --- | --- |
| **OAuth client nào đang xin token?** | Shared secret, signed assertion, client certificate | AS |
| **User nào đã đăng nhập, với mức bảo đảm nào?** | Passkey/MFA, OP session, `auth_time`, `acr` | AS/OP và OIDC client theo profile |
| **Access token nào được trình tại API?** | Bearer JWT hoặc opaque token; sender proof nếu được ràng buộc | RS |
| **Có được đọc/ghi đối tượng này không?** | Scope, principal type, tenant, membership, ownership | RS/business layer |

Với **`grant_type=client_credentials`**, không có user đang trực tiếp phê duyệt hoặc đăng nhập trong giao dịch. Token thường biểu diễn **ứng dụng/service principal** theo hợp đồng với AS, **không phải user-delegated token**. Một `sub` trong app-only JWT cần được hiểu theo **profile của issuer**, không mặc định là mã người dùng.

Với **Authorization Code Flow**, confidential client có thể xác thực tại token endpoint **ngoài** việc chứng minh `code_verifier` PKCE và xác thực người dùng tại OP. **PKCE bảo vệ việc đổi authorization code**, không xác thực shared secret/private key đã được client đăng ký.

## 3. Public và confidential clients

**Confidential client** có thể bảo vệ credential ở server hoặc môi trường vận hành đáng tin (ví dụ Java backend/BFF). **Public client** như SPA JavaScript hay native app cài trên thiết bị người dùng **không thể giữ một client secret bí mật chỉ bằng cách hard-code vào source/binary**.

| Loại | Ví dụ | Phương pháp điển hình |
| --- | --- | --- |
| Confidential backend | Java service, BFF, batch worker | Basic, JWT assertion hoặc mTLS |
| Public SPA | JavaScript trong browser | `none` + Authorization Code + PKCE |
| Public native client | Mobile/desktop app | `none` + PKCE và redirect theo native profile |
| Workload với PKI/KMS | Service có private key được bảo vệ | `private_key_jwt` hoặc mTLS |

**`client_id` là định danh công khai, không phải bằng chứng sở hữu**. Một HTTP request chỉ chứa `client_id=billing-worker` không chứng minh bên gửi là billing-worker.

### 3.1. Method được chọn từ client registration

Client có thể được đăng ký:

~~~json
{
  "client_id": "billing-worker",
  "token_endpoint_auth_method": "private_key_jwt"
}
~~~

AS metadata có thể công bố:

~~~json
{
  "issuer": "https://auth.example.com",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "client_secret_post",
    "private_key_jwt",
    "tls_client_auth"
  ]
}
~~~

Đây là **ví dụ**, không phải mọi AS đều hỗ trợ đủ phương thức. **AS hỗ trợ một method không có nghĩa client bất kỳ được dùng method ấy**. Client registration, issuer metadata và grant policy phải khớp nhau. URL AS phải lấy từ cấu hình/discovery đáng tin, không từ input không kiểm chứng hoặc JWT header tùy ý.

## 4. Bảng tổng quan client authentication methods

| Method | Bằng chứng | Đặc điểm | Tình huống |
| --- | --- | --- | --- |
| **`client_secret_basic`** | Client ID/secret trong HTTP Basic header | Tương thích rộng; shared secret | Backend confidential client |
| **`client_secret_post`** | Client ID/secret trong form body | Dễ bị log body; ít được khuyến nghị | Chỉ khi AS/client không thể dùng Basic |
| **`client_secret_jwt`** | JWT assertion ký bằng shared secret | JWT có audience, expiration; MAC signing | AS/OIDC profile hỗ trợ |
| **`private_key_jwt`** | JWT assertion ký bằng private key | AS dùng public key đã đăng ký; không chia shared secret | Java workload dùng KMS/HSM |
| **`tls_client_auth`** | Xác thực bằng X.509 client certificate qua mTLS | Certificate identity + PKI trust | Service-to-service với PKI |
| **`self_signed_tls_client_auth`** | Self-signed certificate đã đăng ký | Mapping tới public cert/key theo registration | Workload với pinning certificate |
| **`none`** | Không có client secret authentication | Public client; vẫn cần PKCE/grant controls | SPA/native code flow |

Một AS có thể hỗ trợ các extension khác; hãy xác nhận **đúng method đã đăng ký** và chính sách khóa/thu hồi. Không đổi method chỉ vì một SDK cung cấp tham số cấu hình tiện lợi.

## 5. `client_secret_basic`: HTTP Basic ở token endpoint

Theo **RFC 6749 §2.3.1**, confidential client có thể gửi client ID/secret qua HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=orders.read
~~~

Header Basic **xác thực client với AS**. Sau đó, khi gọi API, client phải dùng **access token**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

**Không gửi Basic client secret đến Orders API** và không dùng access token thay client secret tại token endpoint, trừ khi có cơ chế client authentication đặc thù được AS hỗ trợ.

### 5.1. Encoding đúng OAuth 2.0

RFC 6749 yêu cầu form-encode client ID và secret theo `application/x-www-form-urlencoded`, rồi đặt chúng làm Basic username/password:

~~~text
username = formEncode(client_id)
password = formEncode(client_secret)

Authorization: Basic BASE64(ASCII(username + ":" + password))
~~~

Nếu secret chứa `:`, `+`, dấu cách, `%` hoặc ký tự đặc biệt, việc bỏ bước form-encode có thể khiến AS diễn giải sai. Chuỗi Base64 chỉ là **mã hóa biểu diễn**, không bảo vệ bí mật: proxy/attacker đọc được header có thể giải mã để lấy client credential.

### 5.2. Ưu điểm, nhược điểm

**Ưu điểm:** đơn giản, nhiều thư viện hỗ trợ, ít thành phần bổ sung. **Nhược điểm:** shared secret thường được sử dụng lặp lại qua nhiều token requests; nếu lộ, attacker có thể xin token mới đến khi secret bị rotate/revoke. Dùng HTTPS, xác minh TLS certificate/host của AS, secret manager và redaction trên mọi hop.

### 5.3. Client secret khác access token

Client secret dùng để **AS nhận diện một confidential client**. Access token mang phạm vi quyền để **RS quyết định xử lý API request**. Một token `scope=orders.read` có thể bị giới hạn ở đúng Orders API; client secret không tự thay audience hoặc scope.

## 6. `client_secret_post`: secret trong form body

Một số AS cho phép:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials
&client_id=billing-worker
&client_secret=<secret>
&scope=orders.read
~~~

Body trong ví dụ được ngắt dòng để đọc, request thật phải URL-encode đúng. RFC 6749 **không khuyến nghị** đặt client credentials trong body trừ khi client không thể dùng HTTP Basic.

- **HTTPS không loại bỏ rủi ro log request body** tại ingress/WAF/APM hoặc trong exception report.
- **Không gửi secret trong query string**, browser JS hoặc mobile binary.
- **Không gửi hai methods trong cùng request**, chẳng hạn Basic header **và** `client_secret` trong body: RFC 6749 quy định client không được dùng hơn một phương pháp authentication trên một request.
- Nếu client đã đăng ký `client_secret_basic`, không tự đổi sang Post mà chưa cập nhật contract.

## 7. JWT client assertion: `client_secret_jwt` và `private_key_jwt`

Thay vì đưa shared secret vào Basic/form, client có thể tạo **JWT assertion ngắn hạn** để chứng minh sở hữu khóa/secret đã đăng ký. **RFC 7523** mô tả JWT profile cho OAuth 2.0 client authentication; OIDC định nghĩa các tên method phổ biến.

| Thuộc tính | `client_secret_jwt` | `private_key_jwt` |
| --- | --- | --- |
| Thuật toán ký thường gặp | MAC đối xứng, ví dụ HS256 theo policy | Chữ ký bất đối xứng, ví dụ RS256/ES256 |
| Ai giữ secret/private key? | Client và AS biết shared secret | **Client giữ private key**, AS có public key |
| Validation | MAC bằng secret client đã đăng ký | JWS signature bằng key client đã đăng ký |
| Rotation | Đổi shared secret ở hai phía | Đổi key pair và public-key registration/JWKS |
| Rủi ro khi lộ | Attacker ký assertion mới bằng secret | Attacker ký assertion mới bằng private key |

**JWT client assertion không phải JWT access token**: nó dành cho token endpoint của AS, có issuer/audience khác với JWT access token được cấp.

### 7.1. Payload JWT client assertion

~~~json
{
  "iss": "billing-worker",
  "sub": "billing-worker",
  "aud": "https://auth.example.com/oauth2/token",
  "iat": 1800000000,
  "exp": 1800000060,
  "jti": "unique-client-assertion-id"
}
~~~

Protected JWS header khi dùng private key có thể là:

~~~json
{
  "alg": "RS256",
  "kid": "billing-key-2026-11",
  "typ": "JWT"
}
~~~

Trong JWT client authentication:

1. `iss` và `sub` xác định **client đang được xác thực** theo RFC/profile.
2. `aud` phải xác định **authorization server dự kiến**; token endpoint URL có thể được AS chấp nhận, nhưng giá trị chính xác theo issuer contract.
3. `exp` phải được kiểm tra; `iat`, `nbf`, `jti` theo profile/policy.
4. `kid` chỉ giúp chọn khóa **trong key set của client đã đăng ký**, không thể dùng để tin khóa của một client khác.
5. AS phải **allowlist algorithm** phù hợp method/registration, từ chối `alg=none`, algorithm confusion và URL `jku` không tin cậy.

**Chú ý:** `iss=billing-worker` trong client assertion khác `iss=https://auth.example.com` trong access token. Không trộn validators của hai token profiles.

### 7.2. HTTP request với JWT client assertion

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials
&scope=orders.read
&client_id=billing-worker
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=<signed-jwt-assertion>
~~~

Các dòng form ở trên chỉ để minh họa; thực tế gửi một body `application/x-www-form-urlencoded`. `client_id` trong request phụ thuộc method/issuer contract, nhưng assertion vẫn phải được ràng buộc với đúng client. **Không gửi thêm Basic/client_secret_post** cùng JWT assertion.

### 7.3. AS phải kiểm tra JWT assertion

- Tìm đúng client registration và method được phép.
- Kiểm tra signature/MAC bằng **khóa gắn với chính client đó**.
- Validate `iss`, `sub`, `aud`, `exp`, và các claims thời gian/nonce theo profile.
- Dùng `jti` cùng replay cache nếu profile/AS policy yêu cầu chống assertion replay.
- Kiểm tra client được dùng grant/scope/resource đã yêu cầu.
- Từ chối assertion ký đúng nhưng sai audience, hết hạn, client bị disable hoặc key bị revoke.

**`private_key_jwt` tốt hơn về phân phối secret** khi AS chỉ cần public key, nhưng private key vẫn có thể bị đánh cắp từ workload. KMS/HSM, least-privilege signing và rotation vẫn cần thiết.

## 8. Chống replay JWT assertion

Một assertion được ký hợp lệ có thể bị sao chép từ logs rồi gửi lại trước `exp`. TTL ngắn **giảm cửa sổ** chứ không tự tạo one-time semantics.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp lệ
    participant AS as Authorization server
    participant X as Attacker
    C->>AS: client_assertion A, jti=J1
    AS->>AS: Verify signature, audience, exp, J1 unused
    AS-->>C: Access token
    X->>AS: Replay assertion A, jti=J1
    AS->>AS: Replay cache thấy J1 đã dùng
    AS-->>X: Từ chối theo anti-replay policy
~~~

Nếu AS quy định **assertion chỉ dùng một lần**, nó cần kiểm tra `jti` qua **atomic insert-if-absent** và TTL phù hợp với cửa sổ hiệu lực và clock skew. Nhiều AS instances phải dùng shared replay state hoặc ràng buộc tương đương; một set trong RAM từng node có thể bị bypass khi request tới node khác.

~~~text
key = client_id + assertion_jti + namespace/profile
if atomic_insert_if_absent(key, expires_at):
    tiếp tục validation đã đạt
else:
    từ chối replay
~~~

**Đừng nhầm** client assertion replay với refresh-token rotation reuse hay DPoP proof replay. Chúng có giá trị chứng minh và điểm xác minh khác nhau.

## 9. mTLS: `tls_client_auth` và `self_signed_tls_client_auth`

**RFC 8705** định nghĩa OAuth 2.0 Mutual-TLS Client Authentication và Certificate-Bound Access Tokens. Với **`tls_client_auth`**, client chứng minh sở hữu **private key của X.509 client certificate** qua TLS handshake; AS kiểm tra chuỗi chứng chỉ/PKI và định danh certificate tương ứng client registration.

~~~mermaid
flowchart LR
    C["Java workload\nprivate key + client certificate"] -->|"mTLS handshake"| AS["Authorization server"]
    AS --> REG["Client registration:\nsubject DN / SAN / trust policy"]
    AS --> TOKEN["Grant + scope + access token"]
~~~

| Method | Cách xác thực |
| --- | --- |
| **`tls_client_auth`** | Certificate được kiểm tra theo PKI/trust chain và subject DN/SAN identity đã đăng ký |
| **`self_signed_tls_client_auth`** | Client certificate tự ký được đăng ký tin cậy trực tiếp trong AS client metadata |

**Có certificate bất kỳ chưa đủ**: AS phải liên kết cert public key/identity với **client đúng**. Không tin `X-Client-Cert` hoặc `X-Forwarded-Client-Cert` do caller Internet tự khai khi TLS bị terminate ở proxy.

### 9.1. mTLS client auth khác certificate-bound access token

Certificate-bound token có thể chứa confirmation metadata `cnf`:

~~~json
{
  "cnf": {
    "x5t#S256": "<certificate-thumbprint>"
  }
}
~~~

- **mTLS client authentication:** AS xác thực client khi **xin token**.
- **mTLS-bound access token:** RS xác minh access token được trình bởi bên sở hữu **chứng chỉ client tương ứng**.

Sử dụng mTLS tại token endpoint **không tự biến access token thành sender-constrained token**. Nếu AS cấp Bearer access token thuần, bản sao token bị lấy vẫn có thể được replay. Certificate-bound access token cần AS/RS cùng hỗ trợ và kiểm tra đúng.

## 10. Public client `none` và PKCE

Public SPA/native có thể đăng ký:

~~~json
{
  "client_id": "orders-spa",
  "token_endpoint_auth_method": "none"
}
~~~

`none` nghĩa là **không có client secret authentication**, không phải “AS bỏ xác minh authorization code/grant”. Với **Authorization Code + PKCE**, AS vẫn kiểm tra:

1. Client ID và redirect URI đã đăng ký.
2. Authorization code còn hạn, chưa dùng và đúng client.
3. `code_verifier` khớp `code_challenge` S256 đã gắn vào code.
4. Các kiểm tra state/callback phía client, issuer và policy AS.

**PKCE không phải phương thức client authentication của confidential client**; nó ràng buộc việc đổi code với giao dịch khởi tạo.

### 10.1. Public SPA có được dùng client credentials grant?

**RFC 6749 §4.4 quy định client credentials grant chỉ được dùng bởi confidential clients.** Không nhúng `client_secret` vào SPA/native app rồi xin access token quyền service. Khi browser cần quyền user, dùng Authorization Code + PKCE; khi cần background service access, đặt confidential workload client trên backend.

### 10.2. Phân biệt user password và OAuth client secret

User password/passkey/MFA chứng minh user với OP/AS, còn client secret/private key/certificate chứng minh ứng dụng với AS. Client secret không đại diện cho “mật khẩu admin của người dùng” và không cho phép tự đăng nhập thay user.

## 11. Client credentials grant và service principal

Ví dụ một service Java xin access token bằng Basic client authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <billing-worker-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=orders.read
~~~

Phản hồi mẫu:

~~~json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
~~~

Theo **RFC 6749**, AS **SHOULD NOT** cấp refresh token cho client credentials grant. Khi access token hết hạn, confidential client thường **xác thực lại tại token endpoint** để xin access token mới. Không mặc định dùng refresh token dài hạn cho service-to-service chỉ vì client cần chạy liên tục.

### 11.1. App-only không phải user-delegated

Một token client credentials thường biểu diễn **ứng dụng/service principal**, không đại diện cho user đang đăng nhập:

- Không cho phép một request app-only gọi endpoint yêu cầu user-delegated authorization nếu không có policy chuyên biệt.
- Không tự suy ra `sub` luôn là người dùng; phụ thuộc token profile của issuer.
- Nếu worker chạy cho tenant Acme, phải có **service-to-tenant grant** hoặc policy gắn tenant với service identity, không tin `X-Tenant-Id` do caller tự khai.
- Audit cần ghi rõ **client/application identity** và khi thích hợp, workload hoặc grant context.

### 11.2. Scope được xin khác quyền được cấp

Client có thể yêu cầu:

~~~text
scope=orders.read
resource=https://api.example.com/orders
~~~

Tham số `resource` thuộc **RFC 8707** khi AS hỗ trợ. AS phải kiểm tra client registration, grant, resource và scope policy trước khi cấp token. **Client authentication thành công không cho phép chọn audience hoặc scope tùy ý.**

Một access token dành cho Orders API phải bị **Payments API** từ chối dù do cùng AS phát hành. Resource server xác minh token và quyền một lần nữa, không tin chỉ vì AS đã xác thực `billing-worker`.

## 12. Java 17: gọi token endpoint bằng `client_secret_basic`

Ví dụ sau dùng **Java standard `HttpClient`** với HTTPS endpoint cố định. Client ID/secret được lấy từ cấu hình backend bảo vệ; trong production ưu tiên secret manager hoặc workload identity thay vì đặt plaintext trong source code.

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

public final class ClientCredentialsTokenClient {
    private static final URI TOKEN_ENDPOINT =
        URI.create("https://auth.example.com/oauth2/token");

    private ClientCredentialsTokenClient() {}

    private static String formEncode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public static String requestTokenResponse() throws Exception {
        String clientId = System.getenv("OAUTH_CLIENT_ID");
        String clientSecret = System.getenv("OAUTH_CLIENT_SECRET");

        if (clientId == null || clientId.isBlank()
                || clientSecret == null || clientSecret.isBlank()) {
            throw new IllegalStateException("OAuth client is not configured");
        }

        // RFC 6749 2.3.1: form-encode trước khi tạo Basic.
        String pair = formEncode(clientId) + ":" + formEncode(clientSecret);
        String basic = "Basic " + Base64.getEncoder()
            .encodeToString(pair.getBytes(StandardCharsets.US_ASCII));

        String body = "grant_type=client_credentials"
            + "&scope=" + formEncode("orders.read");

        HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder(TOKEN_ENDPOINT)
            .timeout(Duration.ofSeconds(8))
            .header("Content-Type", "application/x-www-form-urlencoded")
            .header("Accept", "application/json")
            .header("Authorization", basic)
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();

        HttpResponse<String> response =
            http.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            // Không đưa client secret/token/error body vào log.
            throw new IllegalStateException(
                "Token endpoint returned status " + response.statusCode());
        }

        // Caller backend tin cậy phải parse JSON và bảo vệ token.
        return response.body();
    }
}
~~~

**Giới hạn của ví dụ:**

1. Chỉ minh họa **`client_secret_basic`**; AS phải cho phép method này với client được đăng ký.
2. Dùng default TLS verification của JVM; không tạo trust-all SSL context hoặc bỏ hostname verification.
3. Token endpoint là URI cố định theo issuer trust config, **không** lấy từ client input, JWT `jku` hoặc redirect tùy ý.
4. Response JSON chưa được parse: code production phải kiểm tra `access_token`, `token_type`, `expires_in`, `scope`/resource, schema và giới hạn payload.
5. Response body và Basic header là **dữ liệu nhạy cảm**; không log, không trả về browser, không đặt vào URL.
6. Environment variables là minh họa đơn giản; process/debug/container tooling vẫn có thể lộ chúng. Dùng secret manager/KMS và least privilege khi có thể.
7. JVM `String`/garbage collector không bảo đảm xóa bytes của secret ngay lập tức; giảm số bản sao và không phát tán heap dumps.
8. Không retry vô hạn khi AS lỗi; dùng timeout/backoff/circuit breaker và không gửi credentials theo redirect cross-origin.

### 12.1. Sau khi có access token

Chỉ sau khi code backend parse và xác minh token response theo contract:

~~~java
// TokenResponse là đối tượng đã parse/validate do ứng dụng định nghĩa.
String accessToken = tokenResponse.accessToken();

HttpRequest apiRequest = HttpRequest.newBuilder(
        URI.create("https://api.example.com/orders"))
    .header("Authorization", "Bearer " + accessToken)
    .header("Accept", "application/json")
    .GET()
    .build();
~~~

Đoạn này là **minh họa**, không phải một class Java độc lập. Không dùng client secret trong API request. Tránh truyền một bearer token vào URL tùy ý (SSRF/token exfiltration); endpoint API phải được allowlist.

## 13. Spring Security OAuth2 Client: cấu hình theo registration

Với **Spring Boot 3 / Spring Security 6**, ví dụ một confidential client dùng client credentials grant:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing-worker:
            provider: internal-as
            client-id: billing-worker
            client-secret: <injected-secret-placeholder>
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: orders.read
        provider:
          internal-as:
            token-uri: https://auth.example.com/oauth2/token
~~~

**Không ghi client secret thật vào Git.** `client-authentication-method` phải khớp registration ở AS. Với sản phẩm thật, tích hợp secrets từ nguồn bảo vệ, đặt HTTPS/certificate validation, timeout và token cache phù hợp.

Spring Security có **OAuth2 Authorized Client Manager** để xin/quản lý access token theo grant. Nhưng cấu hình lưu token, client principal, cache và rotation phụ thuộc phiên bản/ứng dụng; không giả định một biến YAML đủ để hỗ trợ đầy đủ `private_key_jwt` hoặc mTLS nếu HTTP client, signer/keystore và AS chưa được cấu hình.

### 13.1. Backend job không dùng user session giả

Client credentials grant nên dùng **workload/service principal** làm identity khi AS và client manager cho phép. Không mượn session của user để giữ token service và không dùng một token duy nhất cho mọi user/tenant khi policy khác nhau. Token cache nên phân biệt client registration, resource/audience, scope và tenant/grant nếu cần.

### 13.2. Quyền tối thiểu theo workload

~~~text
billing-worker:
    orders.read

settlement-worker:
    payments.write

Không gộp thành một super-admin credential cho mọi dịch vụ.
~~~

Mỗi service hoặc nhóm công việc quan trọng nên có identity/grant được audit và thu hồi độc lập, không chia sẻ một client secret rộng khắp chỉ để giảm số đăng ký.

## 14. Secret, private key, certificate: bảo vệ và rotation

**Khả năng xác thực client chỉ mạnh bằng khả năng bảo vệ credential đó.** Client secret/private key bị lộ cho phép attacker xin **access token mới**, có thể kéo dài sự cố hơn việc chỉ lộ một Bearer token ngắn hạn.

### 14.1. Các đường lộ thường gặp

- Source code, Git history, container image, CI/CD logs hoặc build artifacts.
- Shell history, process arguments, debug command chứa secret.
- Reverse proxy/WAF/APM thu thập `Authorization`, body `client_secret`, `client_assertion`.
- Tracing spans, exception dumps, heap dumps, support tickets, chat và screenshots.
- Kubernetes secret/RBAC quá rộng, bản sao backup và phân quyền secret manager kém.
- Client secret hard-code vào SPA/mobile binary hoặc config được browser tải.

**JWT assertion đã ký vẫn là credential tạm thời**: ai giữ bản sao còn hạn có thể thử phát lại. Đừng log raw assertion chỉ vì nó được ký bằng private key.

### 14.2. Chọn nơi lưu

| Loại | Nơi lưu hợp lý | Kiểm soát |
| --- | --- | --- |
| Shared client secret | Secret manager/protected backend configuration | Least privilege, access logs, rotation |
| Private key JWT | KMS/HSM hoặc keystore bảo vệ | Quyền ký, audit, public-key registration |
| mTLS private key | Protected keystore/certificate manager | Cert lifecycle, PKI chain, non-exportability khi có |
| Public JWKS | Registry/JWKS tin cậy gắn client | Algorithm allowlist, key mapping, rotation |
| Access token | Backend token cache/store có TTL | Không log, không dùng sai audience, revoke khi cần |

Secret manager/PKI không tự bảo vệ token nếu service có quyền ký/xin token **quá rộng**. Giảm scopes và giới hạn grant/audience là thành phần quan trọng của defense-in-depth.

### 14.3. Quy trình rotation có kiểm soát

1. Sinh secret/key/certificate mới qua nguồn đáng tin.
2. Đăng ký khóa mới với AS; nếu hỗ trợ, có khoảng **overlap ngắn** để chuyển đổi không gián đoạn.
3. Triển khai client dùng credential mới, kiểm thử token endpoint và API.
4. Theo dõi `invalid_client`, key alias, cert expiry và success rate không lộ bí mật.
5. Thu hồi credential cũ; xóa bản sao không còn cần thiết.
6. Nếu credential compromise, đánh giá access tokens/grants đã cấp và khả năng revoke sớm.

**Thay client secret không tự làm JWT access token đã phát hết hạn.** Cần AS/RS token revocation/introspection/denylist/token lifetime policy để giảm tác động.

## 15. Reverse proxy, mTLS và trusted headers

Proxy có thể kết thúc TLS và chuyển HTTP request vào AS:

~~~text
Client --mTLS--> Gateway --TLS/mTLS--> Authorization server

Nếu AS chỉ thấy certificate của gateway:
  certificate nào chứng minh OAuth client ban đầu?
~~~

Nếu gateway thực hiện TLS termination, AS thường **không thấy trực tiếp client certificate gốc**. Không được dựa vào `X-SSL-Client-Cert` hoặc `X-Forwarded-Client-Cert` do caller Internet tự gửi.

Kiến trúc hợp lệ phải xác định **nơi thực hiện client certificate authentication**, strip/overwrite headers từ untrusted caller, bảo vệ kênh/asertion gateway → AS và **chặn bypass gateway**. Cần kiểm thử certificate mapping thực tế, không suy ra trust chỉ vì mTLS giữa hai hop nội bộ.

### 15.1. Basic/JWT assertion cũng có rủi ro ở proxy

Thành phần kết thúc TLS có thể thấy client secret/ `client_assertion`. Cần redact ở CDN, ingress, WAF, API gateway, APM, debug middleware; không chỉ trong log ứng dụng Java.

### 15.2. Không gửi credential khi token endpoint redirect

HTTP client phải sử dụng **trusted token endpoint cố định**, kiểm soát redirects, đặc biệt cross-origin. Một `302` tới attacker host không được biến thành việc forward Basic secret hay JWT assertion cho host đó.

## 16. DPoP có phải client authentication method?

**DPoP (RFC 9449)** sử dụng proof JWT theo HTTP request để chứng minh sender có private key và có thể ràng buộc access token với public key. DPoP có các claims như `htm`, `htu`, `iat`, `jti` và `ath` khi áp dụng.

**DPoP không mặc nhiên thay thế** `client_secret_basic`, `private_key_jwt` hoặc `tls_client_auth`. Ví dụ một public SPA có thể đăng ký method `none` nhưng dùng DPoP-bound token; một confidential client có thể dùng **private-key JWT để AS nhận diện client** và DPoP cho token/request binding.

| Bảo vệ | Bên kiểm tra | Mục đích |
| --- | --- | --- |
| Basic/JWT/mTLS client authentication | AS token endpoint | Client identity |
| PKCE | AS token endpoint | Authorization code binding |
| DPoP proof/token binding | AS/RS theo profile | Sender proof và token replay resistance |
| JWT/opaque access token validation | RS | Issuer, audience, time, scope, active |
| Object authorization | RS/business service | Tenant/owner/action permission |

**Access token có `jti` thường được dùng nhiều API requests hợp lệ**; một DPoP proof có `jti` replay lại cần bị từ chối trong cửa sổ phù hợp. Không đánh đồng hai loại token/proof.

## 17. Chọn method theo threat model

| Tiêu chí | Basic shared secret | JWT client assertion | mTLS |
| --- | --- | --- | --- |
| Độ phức tạp ban đầu | Thấp | Trung bình: signer/JWKS | Cao hơn: PKI/network/cert |
| Credential gốc | Shared secret | Shared secret hoặc private key | Private key + certificate |
| Hạn ngắn cho bằng chứng gửi | Secret được dùng lặp | JWT assertion có `exp` | TLS handshake/cert validity |
| Phát hiện replay bản sao request | Không dựa vào Basic header | Cần `jti`/replay policy | Proof of possession tại TLS |
| Rotation | Shared secret | Signing key/secret + JWKS/registration | Cert/key + PKI mapping |
| Ràng buộc access token mặc định? | Không | Không | Không; yêu cầu certificate-bound policy riêng |
| Phù hợp | Backend nhỏ với secret manager | Workload dùng KMS/HSM | Hệ thống có mTLS/PKI chuẩn hóa |

**Không có phương thức “tốt nhất” cho mọi môi trường.** Cần xét: AS có hỗ trợ và cho phép method không, credential được giữ ở đâu, lượng service/tenant, rotation, audit, compliance, năng lực PKI/KMS, TLS proxy topology và rủi ro token bị phát lại.

Trong hạ tầng có KMS signer an toàn, `private_key_jwt` giảm việc chia shared secret. Trong hệ thống có workload PKI ổn định, mTLS thuận lợi. `client_secret_basic` vẫn có thể an toàn nếu TLS, secret manager, least privilege và rotation được triển khai đúng.

## 18. Access token được cấp vẫn cần RS validation

Giả sử `billing-worker` được AS xác thực bằng private-key JWT, sau đó AS cấp access token **minh họa**:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "service-billing-worker",
  "client_id": "billing-worker",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "at-service-001"
}
~~~

Resource server phải kiểm tra:

1. **Nguồn token:** JWS signature/alg/key và `iss` nếu JWT; hoặc introspection/`active` với opaque token.
2. **Audience:** token phải dành cho chính API nhận request.
3. **Thời gian/loại:** `exp`, `nbf`, token type, principal type.
4. **Scope:** `orders.read` không cho phép endpoint đòi `orders.write`.
5. **Quyền tổ chức:** workload được phép với tenant nào theo trusted grant/policy.
6. **Object ownership:** chỉ đọc dữ liệu thuộc tenant/grant được cấp.
7. **Sender constraint** nếu DPoP/mTLS-bound, không hạ cấp thành bearer thuần.

Ví dụ truy vấn database:

~~~sql
SELECT *
FROM orders
WHERE id = :order_id
  AND tenant_id = :authorized_tenant_id;
~~~

Giá trị `:authorized_tenant_id` đến từ **trusted token/grant policy**, không từ request header `X-Tenant-Id` tự khai.

### 18.1. `401` khác `403`

- **401 Unauthorized:** API không xác nhận được access token hợp lệ, ví dụ thiếu/sai chữ ký/hết hạn/audience sai.
- **403 Forbidden:** token đã xác thực nhưng scope/tenant/ownership/role không đủ.
- **`invalid_client` ở token endpoint:** AS không xác thực được OAuth client, **không** nghĩa user thiếu role.
- **`unauthorized_client`:** client không được phép sử dụng grant/method theo AS registration.
- **`invalid_scope`:** phạm vi yêu cầu không hợp lệ/không được cấp; đổi client auth method mạnh hơn không tự mở rộng scope.

## 19. Bảng lỗi và phản ứng bảo mật

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Client không gửi auth khi endpoint yêu cầu | AS từ chối `invalid_client` |
| Basic secret sai/đã rotate | AS từ chối, không cho fallback |
| Client đăng ký Basic nhưng gửi Post | AS từ chối nếu method không được phép |
| Gửi Basic cùng Post/JWT assertion | AS từ chối vì dùng nhiều auth methods |
| JWT assertion `alg=none` hoặc chữ ký sai | AS từ chối |
| JWT assertion sai `aud`, `iss`, `sub` hoặc hết `exp` | AS từ chối |
| JWT `kid` trùng client khác | Không dùng key của client khác |
| JWT assertion `jti` bị replay | Từ chối theo AS replay policy |
| mTLS certificate sai SAN/DN/registration | AS từ chối |
| Proxy giả `X-Client-Cert` | Không chấp nhận như mTLS proof |
| Public SPA dùng client credentials với secret nhúng | Từ chối/đổi kiến trúc |
| Client hợp lệ xin grant/scope không được phép | Không cấp quyền vượt registration |
| Client secret bị thu hồi nhưng JWT AT còn hạn | Kiểm tra token revocation/denylist policy |
| AS timeout hoặc redirect cross-origin | Không fail open, không lộ credential |

**Không nên debug bằng cách log raw secrets.** Có thể log client alias, method, issuer alias, key ID đã được kiểm soát, trạng thái/error category, request ID và latency. Tách token-request logs khỏi user/RS access logs.

## 20. Những sai lầm triển khai phổ biến

### 20.1. “`client_id` đã xác thực client”

**Sai.** ID công khai; chỉ confidential client authentication theo đăng ký mới chứng minh quyền sử dụng secret/key/certificate.

### 20.2. “PKCE thay client secret”

**Sai.** PKCE bảo vệ authorization code exchange, không thay xác thực confidential client.

### 20.3. “HTTPS làm `client_secret_post` không thể lộ”

**Sai.** HTTPS bảo vệ transport; proxy, application logs và APM vẫn có thể ghi body.

### 20.4. “JWT assertion ký đúng thì được mọi scope”

**Sai.** AS còn kiểm tra grant/scope/audience; RS còn kiểm tra token và object policy.

### 20.5. “`kid` ở JWT bất kỳ đủ để xác định khóa”

**Sai.** Khóa phải được đăng ký và ràng buộc đúng client; không cho arbitrary `jku` làm nguồn tin cậy.

### 20.6. “Đã mTLS với AS thì Bearer token không bị replay”

**Sai.** Cần certificate-bound access token và RS kiểm tra sender binding nếu mục tiêu là chống bản sao token.

### 20.7. “SPA hard-code secret có thể làm service-to-service”

**Sai.** Secret ở public client không thể được bảo vệ đúng nghĩa; dùng backend workload client hoặc Code+PKCE theo user grant.

### 20.8. “Rotate secret là access token cũ tự vô hiệu”

**Sai.** Access token đã phát có thể còn hợp lệ tới `exp`; cần revocation/introspection/denylist tùy chính sách.

### 20.9. “Gộp mọi service vào một client super-admin”

**Rủi ro.** Khó giới hạn quyền, audit, cô lập compromise và rotation. Tách identities theo workload và nhu cầu permission.

## 21. Bộ kiểm thử bắt buộc

| Test case | Kỳ vọng |
| --- | --- |
| Basic đúng ID/secret | AS xác thực rồi kiểm tra grant/scope |
| Basic secret có `:`, `+`, `%`, khoảng trắng | Form encoding chính xác |
| Basic sai/hết hiệu lực | Từ chối `invalid_client` |
| Basic và Post cùng request | Từ chối nhiều auth methods |
| Client đăng ký Basic nhưng dùng Post | Từ chối theo registration policy |
| Public client cố dùng client credentials với hard-coded secret | Không được phát service credential |
| `private_key_jwt` ký đúng bằng key đăng ký | AS kiểm tra toàn bộ JWT claims |
| JWT assertion sai `iss`/`sub` | Từ chối |
| JWT assertion sai `aud` | Từ chối dù chữ ký đúng |
| JWT assertion hết hạn hoặc `nbf` tương lai khi policy áp dụng | Từ chối |
| JWT assertion `alg=none` | Từ chối |
| HS256–RS256 key confusion | Từ chối algorithm/key mismatch |
| JWT assertion `kid` trùng client khác | Không trộn key sets |
| JWT assertion cùng `jti` gửi lại | Từ chối nếu anti-replay được áp |
| Hai AS nodes nhận cùng assertion | Replay state/atomicity thống nhất |
| mTLS certificate sai client registration | Từ chối |
| mTLS certificate hết hạn/trust chain sai | Từ chối |
| Caller tự khai `X-Client-Cert` | Không được xác thực |
| Client hợp lệ dùng grant bị cấm | `unauthorized_client` |
| Client hợp lệ xin scope vượt quyền | AS từ chối/hạn chế, không cấp rộng |
| App-only token gọi endpoint cần user delegation | RS từ chối theo principal type |
| Token dành Orders API gọi Payments API | RS từ chối `aud` |
| App-only token đọc tenant không được cấp | RS từ chối object authorization |
| Rotate/revoke client credential | Test tác động đến token đã phát và revoke policy |
| Client secret/JWT assertion xuất hiện trong logs | Kiểm thử bảo mật thất bại |
| Token endpoint redirect tới host khác | Không gửi Basic/JWT assertion tới host lạ |
| Key/secret rotation với overlap | Key mới hoạt động, key cũ ngừng theo plan |
| AS outage | Backoff/circuit breaker, không fail open |
| DPoP/mTLS-bound token thiếu proof/cert ở RS | RS từ chối |

### 21.1. Các tầng test

- **Unit:** Basic form encoding, JWT client assertion claims, algorithm/key mapping.
- **Authorization-server integration:** từng method được đăng ký và các trường hợp thiếu/sai credential.
- **TLS/proxy:** certificate mapping, trusted headers, upstream verification, redaction.
- **RS/token:** JWT hoặc opaque validation, audience/scope và revocation.
- **Business:** principal type, tenant, ownership, không coi app-only là user.
- **Vận hành:** rotation, AS outage, JWT assertion replay cache nhiều instances.

Chỉ dùng **test credentials/tokens**. Không dán secrets production vào test fixtures, CI logs, screenshots, issue trackers hoặc chat.

## 22. Checklist production

1. **Xác định client type:** public SPA/native hay confidential Java/BFF/workload.
2. **Đăng ký method rõ ràng:** Basic/Post/JWT/mTLS/`none` phù hợp AS và client registration.
3. **Không trộn identity:** client auth, user auth, token validation và resource authorization là các bước khác nhau.
4. **Quản lý secret/key:** secret manager/KMS/HSM/PKI, rotation, least privilege và logging redaction.
5. **Dùng trusted AS endpoint:** HTTPS/TLS verification, metadata đáng tin, không forward credentials theo redirect lạ.
6. **Đúng giao thức:** Basic form encoding, Post chỉ khi cần; một method mỗi request.
7. **JWT assertions:** `iss/sub/aud/exp`, ký bằng key client đúng, algorithm allowlist, `jti` anti-replay khi policy yêu cầu.
8. **mTLS:** certificate mapping, chain/SAN/DN policy hoặc registered self-signed cert; không tin proxy headers tùy ý.
9. **PKCE/DPoP không thay nhau:** PKCE chống code interception, DPoP/tls-bound token chống token replay theo profile.
10. **Client credentials grant đúng:** dùng confidential workload, app-only principal và scopes/audience tối thiểu.
11. **Không giả định refresh token:** client credentials thường xin AT mới bằng client authentication; theo dõi hạn/revocation.
12. **API kiểm tra độc lập:** `iss`, `aud`, `exp`, scope, tenant và quyền object, JWT/opaque validation.
13. **Có kế hoạch sự cố:** thu hồi client secret/key, token/grant liên quan và xử lý access token còn hạn.
14. **Kiểm thử âm và đa node:** wrong method, JWT replay, algorithm confusion, cert mismatch, proxy spoof, AS outage.

## 23. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client authentication (§2.3), confidential/public clients và client credentials grant (§4.4).
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT assertion, `iss`, `sub`, `aud`, `exp` và validation.
- [RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7521): khung assertion client authentication.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): `tls_client_auth`, self-signed certificate method và access token binding.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `token_endpoint`, `token_endpoint_auth_methods_supported` và discovery.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): token endpoint authentication, `client_secret_jwt`, `private_key_jwt` và ID token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth client security, PKCE, token theft và refresh token replay.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` và `code_challenge`, khác client authentication.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens và proof replay.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource/audience.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra opaque/JWT token tại RS.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoke grant/token không đồng nhất với rotate client credential.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, client credentials grant và authorized-client management trong Java.

**Ghi nhớ:** **Client authentication methods quyết định cách OAuth client chứng minh danh tính với authorization server.** `client_secret_basic/post` dùng shared secret, `client_secret_jwt/private_key_jwt` dùng signed JWT assertions, mTLS dùng client certificate, còn public client `none` không có bí mật và phải tuân các kiểm soát grant như PKCE. **Client credentials grant đại diện cho ứng dụng/service principal, không tự đại diện người dùng.** Sau khi AS xác thực client và phát access token, RS vẫn phải kiểm tra issuer, audience, thời hạn, scope, tenant, object authorization và các cơ chế chống token replay cần thiết.
