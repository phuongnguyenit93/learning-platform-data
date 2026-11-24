# Private key authentication

Một dịch vụ nền **reports-worker** cần lấy access token để gọi Reports API. Thay vì đặt **client_secret** cố định trong biến môi trường trên nhiều máy chủ, nhóm bảo mật đăng ký **public key** của dịch vụ tại Authorization Server và để dịch vụ dùng **private key** của mình ký một **JWT client assertion** mỗi khi gọi token endpoint. Authorization Server kiểm chữ ký bằng public key đã đăng ký trước khi quyết định cấp access token.

Đó là ý tưởng của **private key authentication** trong OAuth 2.0, thường được triển khai bằng phương thức **private_key_jwt**: **chứng minh danh tính OAuth client bằng quyền sở hữu private signing key**, thay vì gửi shared client secret. Cách làm này đặc biệt hữu ích cho các **confidential clients** trong môi trường máy–máy, nhưng nó **không tự cấp quyền cho client**, **không tự ràng buộc access token với khóa ký**, và **không loại bỏ trách nhiệm bảo vệ private key**.

Bài học thuộc chương **Client credentials** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ private key authentication với mô hình tin cậy và vòng đời JWT, opaque token, access token và refresh token trong OAuth 2.0/OIDC: phát hành, xác minh claims, scope/audience, quản lý khóa, lưu trữ, thu hồi và ngăn credential bị đánh cắp hoặc phát lại.

Sau bài học, bạn sẽ phân biệt **client authentication** với **grant** và **authorization**, hiểu cấu trúc JWT assertion, biết client ký và Authorization Server xác minh như thế nào, thiết kế quản lý khóa/rotation, xử lý lỗi và viết kiểm thử thành công lẫn thất bại.

## 1. Client authentication trả lời câu hỏi nào?

Trong OAuth 2.0, **Authorization Server (AS)** có thể cấp access token cho client sau khi client chứng minh danh tính và trình bày một grant hợp lệ. Hai câu hỏi này khác nhau:

1. **Client authentication:** “Ứng dụng đang gọi token endpoint có thực sự là client đã đăng ký không?”
2. **Authorization grant evaluation:** “Client đó có được dùng grant này để nhận token cho scope và resource yêu cầu không?”

Một dịch vụ có thể **xác thực đúng bằng private key**, nhưng vẫn phải bị từ chối nếu không được phép dùng **client_credentials**, yêu cầu scope **payments:charge** ngoài quyền hoặc yêu cầu access token dành cho audience không được cấp.

| Khái niệm | Ai kiểm tra? | Bằng chứng / kết quả |
|---|---|---|
| **Client authentication** | Authorization Server tại token endpoint | Bí mật dùng chung, private key JWT assertion, mTLS hoặc cơ chế được đăng ký |
| **Client Credentials grant** | Authorization Server | Loại grant **client_credentials** và quyền của chính client |
| **Access token issuance** | Authorization Server | Token đã được cấp với audience, scope, thời hạn, loại token phù hợp |
| **Access token validation** | Resource Server | Chữ ký JWT hoặc introspection opaque token; issuer, audience, thời hạn và profile |
| **Authorization tại API** | Resource Server / policy engine | Quyền cụ thể của service principal đối với endpoint hoặc tài nguyên |

**Private key authentication là phương thức xác thực client, không phải tên một OAuth grant.** Trong ví dụ máy–máy, ta kết hợp:

~~~text
grant_type = client_credentials
token_endpoint_auth_method = private_key_jwt
~~~

Phương thức **private_key_jwt** cũng có thể được sử dụng tại token endpoint với những grant khác nếu Authorization Server và đăng ký client cho phép, chẳng hạn khi confidential web client đổi authorization code. Ngược lại, **JWT Bearer Authorization Grant** theo RFC 7523 sử dụng một JWT làm **grant** và có **grant_type khác**; không được nhầm nó với JWT dùng để **xác thực client**.

## 2. Vì sao chọn private key thay cho shared client secret?

Với **client_secret_basic** hoặc **client_secret_post**, client và Authorization Server cùng biết một bí mật được dùng để xác thực. Nếu bí mật đó bị lộ, bên có bí mật có thể giả mạo client cho đến khi nó được thu hồi hoặc đổi.

Với **private_key_jwt**:

- Client **giữ private key**, tạo chữ ký trên một JWT client assertion ngắn hạn.
- Authorization Server **giữ hoặc lấy public key đáng tin** gắn với client đã đăng ký.
- Khi nhận assertion, AS xác minh chữ ký và claims, rồi áp dụng các kiểm tra client/grant/policy.
- **Private key không cần được gửi trong HTTP token request**.

| Tiêu chí | Shared client secret | Private key JWT authentication |
|---|---|---|
| Vật liệu xác thực ở client | Shared secret | Private signing key |
| Vật liệu AS cần để xác minh | Shared secret hoặc dạng xác minh tương ứng | Public key đã đăng ký |
| Có gửi secret/key gốc trong token request? | Có thể gửi secret qua Basic hoặc body, được bảo vệ bởi TLS | **Không gửi private key**; gửi assertion đã ký |
| Quản lý xoay khóa | Đổi shared secret ở các bên | Đăng ký key mới, chuyển signer, gỡ public key cũ |
| Nguy cơ nổi bật | Secret bị sao chép, rò qua cấu hình/log | Private key bị xuất, ký thay client; JWT assertion bị replay |
| Phù hợp | Confidential client có kho secret an toàn | Confidential client có khả năng giữ signing key an toàn, có thể dùng KMS/HSM |

**Public key được công bố không phải bí mật**. Bảo mật đến từ việc kẻ tấn công **không có private key tương ứng** và AS chỉ tin những public key được đăng ký đúng client. Nếu private key bị lấy cắp, kẻ tấn công có thể ký assertion hợp lệ mới; chữ ký không giúp phát hiện người ký là kẻ xâm nhập.

Private key authentication đặc biệt có lợi khi private key được bảo vệ bằng **KMS/HSM** hoặc một kho khóa có cơ chế hạn chế xuất, kiểm soát quyền ký và audit. Nếu ứng dụng sao chép private key dạng PEM vào mọi container image hoặc repository, lợi ích vận hành và an ninh có thể bị suy giảm đáng kể.

## 3. Ranh giới tin cậy: public key phải thuộc đúng client

Một Authorization Server không được tin public key bất kỳ chỉ vì một JWT đưa ra **kid** hoặc URL lấy khóa. Cần có **client registration** được bảo vệ trước:

~~~text
Client registration (mô hình minh họa):
  client_id: reports-worker
  token_endpoint_auth_method: private_key_jwt
  token_endpoint_auth_signing_alg: RS256
  registered_jwks_uri: https://keys.example.org/reports-worker/jwks.json
  allowed_grant_types: [client_credentials]
  allowed_scopes: [reports:read]
  allowed_resources: [reports-api]
~~~

Đường dẫn, tên key và cấu hình chỉ là ví dụ. Một AS có thể đăng ký **public JWK trực tiếp** thay vì một **jwks_uri**, hoặc hỗ trợ thuật toán khác theo chính sách. Nguồn khóa được **gắn với client_id trong registry đáng tin**, không do caller tự thay đổi trong mỗi token request.

~~~mermaid
flowchart LR
    K["Private key ở reports-worker"] -->|"Ký JWT assertion"| J["Client assertion"]
    J -->|"POST /token"| AS["Authorization Server"]
    R["Client registry: client_id, alg, public JWK/JWKS URI"] --> AS
    AS -->|"Xác minh chữ ký + claims + replay"| A{"Client hợp lệ?"}
    A -->|Không| D["invalid_client / Reject"]
    A -->|Có| P{"Grant, scope, audience được phép?"}
    P -->|Không| E["Reject"]
    P -->|Có| T["Phát access token"]
    T --> C["reports-worker"]
    C -->|"Bearer access token"| RS["Reports API"]
~~~

### Public JWK và private JWK khác nhau

Ví dụ **public JWK** RSA công bố cho AS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "reports-key-2026-11",
      "alg": "RS256",
      "n": "<public-modulus-base64url>",
      "e": "AQAB"
    }
  ]
}
~~~

**n** ở đây chỉ là placeholder, không phải modulus thật để kiểm chữ ký. Public JWKS chỉ chứa thành phần **công khai**; với RSA, **không** đưa các trường private như **d, p, q, dp, dq, qi** vào JWKS công khai. Với EC, private component **d** cũng không được công bố.

**JWKS của client** được AS dùng để xác minh **client assertions**; **JWKS của Authorization Server** thường được Resource Server dùng để xác minh **JWT access token do AS ký**. Đây là **hai mục đích, hai quan hệ tin cậy**, dù đều dùng chuẩn JWK/JWS.

## 4. JWT client assertion chứa gì?

Trong phương thức **private_key_jwt**, client tạo một **JWS JWT** được ký bằng private key đã đăng ký. Ví dụ JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "reports-key-2026-11",
  "typ": "JWT"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "reports-worker",
  "sub": "reports-worker",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1795400000,
  "exp": 1795400060,
  "jti": "assertion-example-91a6"
}
~~~

Các giá trị chỉ dùng để học; thời gian minh họa không phải thời điểm thực. Assertion thực tế phải được **ký bằng private key thật được bảo vệ** và tạo mốc thời gian từ đồng hồ tin cậy.

| Thành phần | Ý nghĩa | Quy tắc kiểm tra |
|---|---|---|
| **iss** | Client phát hành JWT assertion | Với client authentication theo RFC 7523, là **client_id** |
| **sub** | Chủ thể mà assertion xác thực | Với client authentication theo RFC 7523, cũng là **client_id** |
| **aud** | Authorization Server là bên nhận dự kiến | Chỉ chấp nhận giá trị audience AS đã cấu hình cho token endpoint/profile |
| **exp** | Hết hạn assertion theo NumericDate | Bắt buộc trong RFC 7523, phải chưa hết hạn |
| **iat** | Thời điểm phát hành theo NumericDate | Có thể được đưa vào để kiểm tuổi tối đa/clock skew theo policy |
| **jti** | JWT ID | Hữu ích để phát hiện assertion bị dùng lại; nếu AS yêu cầu replay prevention thì phải lưu/kiểm |
| **alg** | Thuật toán ký trong protected header | Chỉ nhận thuật toán được đăng ký và phù hợp public key |
| **kid** | Định danh khóa trong header | Chỉ chọn key trong tập **đã tin của client này** |

Theo **RFC 7523**, các claims **iss, sub, aud, exp** là các yêu cầu nền tảng đối với JWT dùng cho client authentication; **iat** và **jti** không phải luôn bắt buộc bởi RFC 7523, nhưng AS có thể yêu cầu theo profile/chính sách an toàn. Để phòng replay tốt hơn, nên dùng **jti duy nhất**, **exp ngắn** và cache/ledger chống dùng lại ở phía AS.

### Đừng nhầm aud với Resource Server audience

Assertion có **aud hướng tới Authorization Server**, ví dụ token endpoint **https://auth.example.org/oauth2/token** theo hợp đồng triển khai. Access token mà AS trả về sau đó có thể có **aud=reports-api**. Hai audience này **khác nhau**:

~~~text
Client assertion: aud -> Authorization Server / token endpoint
Issued access token: aud -> Resource Server / Reports API
~~~

Không dùng **aud=reports-api** trong client assertion rồi trông đợi AS chấp nhận, và không dùng JWT client assertion để gọi Reports API. Về mặt RFC 7523, token endpoint URL **có thể** là giá trị aud; profile như OIDC **private_key_jwt** thường xác định audience tương ứng với token endpoint. Hãy kiểm hợp đồng **audience được AS chấp thuận**, không tự thay đổi từ issuer sang endpoint URL hoặc ngược lại mà không có cấu hình.

## 5. Luồng client credentials với private_key_jwt

~~~mermaid
sequenceDiagram
    participant C as reports-worker
    participant K as KMS/HSM hoặc private key store
    participant AS as Authorization Server
    participant RS as Reports API
    C->>C: Chuẩn bị iss=sub=client_id, aud, exp, jti
    C->>K: Yêu cầu ký assertion bằng private key
    K-->>C: Chữ ký JWS; private key không xuất nếu dùng HSM/KMS phù hợp
    C->>AS: POST /token: client_credentials + client_assertion
    AS->>AS: Tra registration client và public JWK
    AS->>AS: Kiểm alg/kid/chữ ký/iss/sub/aud/exp/jti
    AS->>AS: Kiểm grant, scope, audience và trạng thái client
    AS-->>C: Access token cho reports-api nếu được phép
    C->>RS: Bearer access token
    RS->>RS: Validate issuer, audience, exp, scope, quyền nghiệp vụ
    RS-->>C: Kết quả được phép
~~~

Cần phân biệt **ba bằng chứng độc lập**:

1. Client assertion chứng minh **client đang gọi token endpoint** nắm private key đã đăng ký.
2. **Client Credentials grant** cho biết AS đang được yêu cầu cấp quyền theo **danh tính của client**, không tự đại diện cho người dùng cuối.
3. Access token do AS cấp là credential dùng tại **Resource Server**, phải được API xác minh riêng.

**Client Credentials grant thường không cần refresh token**: confidential client có thể xác thực với AS để xin access token mới khi cần. OAuth 2.0 quy định refresh token **thông thường không nên được cấp** trong flow này. Nếu có chính sách khác, cần đánh giá rõ vì sao thêm credential dài hạn.

## 6. HTTP request: grant_type và client_assertion_type là hai trường khác nhau

Ví dụ request tới token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports%3Aread&client_id=reports-worker&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&client_assertion=<signed-client-JWT>
~~~

Trong request thật, tất cả giá trị phải được **form-url-encode đúng quy tắc**; JWT assertion là chuỗi gồm các phần Base64url và chữ ký, không phải JSON payload thuần. Các trường cốt lõi:

| Tham số | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| **grant_type** | **client_credentials** | Client xin access token theo quyền của chính mình |
| **scope** | **reports:read** | Quyền mong muốn, AS phải kiểm và giới hạn |
| **client_id** | **reports-worker** | Xác định client đăng ký; bắt buộc hay tùy theo quy tắc cụ thể của AS/profile |
| **client_assertion_type** | **urn:ietf:params:oauth:client-assertion-type:jwt-bearer** | Cho biết JWT được dùng làm **client authentication assertion** |
| **client_assertion** | JWT compact JWS đã ký | Chứng minh quyền ký private key phù hợp client |

**Quan trọng:** Không thay **grant_type=client_credentials** thành giá trị **urn:ietf:params:oauth:grant-type:jwt-bearer** nếu mục tiêu chỉ là xác thực client bằng private_key_jwt. Giá trị **grant-type:jwt-bearer** thuộc **JWT assertion authorization grant** theo RFC 7523, có quy trình xác định chủ thể/ủy quyền riêng. Hai cơ chế có thể cùng dùng JWT nhưng phục vụ **vai trò khác nhau**.

Không đặt private key, PEM, client secret hoặc mật khẩu vào request. TLS bắt buộc để bảo vệ request/response; JWT client assertion dù đã ký vẫn là **authentication credential có thể bị phát lại nếu còn hiệu lực và AS không chống replay**.

### Response khi thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token-for-reports-api>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "reports:read"
}
~~~

Đây là ví dụ không chứa token thật. **expires_in=900** là thời hạn access token minh họa bằng giây, không phải TTL của JWT client assertion. AS phải quyết định audience, scope và thời hạn dựa trên client/grant/policy, **không tự động chép mọi quyền client yêu cầu**.

## 7. Java: tạo client assertion bằng private RSA key

Ví dụ sau dùng API của thư viện **Nimbus JOSE + JWT** để minh họa cách tạo assertion theo mô hình Java. Đây là ví dụ **minh họa logic ký**, không bao gồm phương thức tải private key, cấu hình token endpoint hay toàn bộ xử lý OAuth. Cần sử dụng thư viện được cập nhật và phiên bản API tương thích trong hệ thống thực tế.

~~~java
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

public final class PrivateKeyJwtAssertion {
    private PrivateKeyJwtAssertion() {}

    public static String create(
            String clientId,
            String tokenEndpointAudience,
            String keyId,
            RSAPrivateKey privateKey
    ) throws Exception {
        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(clientId)
                .subject(clientId)
                .audience(tokenEndpointAudience)
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(60)))
                .jwtID(UUID.randomUUID().toString())
                .build();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID(keyId)
                .build();

        SignedJWT assertion = new SignedJWT(header, claims);
        assertion.sign(new RSASSASigner(privateKey));
        return assertion.serialize();
    }
}
~~~

Điểm cần lưu ý:

- **RSAPrivateKey** được giả định đã lấy từ **nguồn an toàn và được ủy quyền**. Không hard-code private key, không commit PEM vào repository, không in biến privateKey ra log.
- Nếu HSM/KMS **không cho xuất private key**, thay **RSASSASigner** thao tác trực tiếp bằng cơ chế ký thông qua provider hoặc API dịch vụ quản lý khóa đã được đánh giá; private key không cần nằm trong heap ứng dụng.
- **60 giây** chỉ là thời hạn assertion minh họa. AS có thể yêu cầu TTL tối đa khác, độ lệch đồng hồ và claims khác. Luôn tuân thủ policy phía AS.
- **UUID ngẫu nhiên** làm jti hỗ trợ định danh assertion. Độ duy nhất cần đủ cho yêu cầu replay detection; AS phải thực sự kiểm và lưu jti nếu muốn từ chối reuse.
- **tokenEndpointAudience** là giá trị AS chấp nhận làm aud cho client assertion, không phải URL Reports API.
- Trường **kid** chọn key đã đăng ký của **client này**, không phải URL tự cấp để AS tải khóa tùy ý.

### Gửi request bằng client HTTP

Pseudocode:

~~~text
assertion = createPrivateKeyJwt(
    clientId = "reports-worker",
    aud = trustedTokenEndpointAudience,
    keyId = registeredKeyId
)

response = POST trustedTokenEndpoint over TLS
    Content-Type: application/x-www-form-urlencoded
    body:
      grant_type = client_credentials
      scope = reports:read
      client_id = reports-worker
      client_assertion_type =
        urn:ietf:params:oauth:client-assertion-type:jwt-bearer
      client_assertion = assertion

if response.success:
    use response.access_token only for approved Resource Server
else:
    handle OAuth error without logging assertion or credentials
~~~

Không dùng lại assertion trong hàng đợi hoặc lưu vào cache như một shared secret “để tiết kiệm ký”. Client nên ký một assertion **mới cho mỗi token request**, với jti mới và tuổi đời ngắn phù hợp chính sách.

## 8. Authorization Server xác minh client assertion như thế nào?

Một verifier tốt không chỉ gọi hàm **decode JWT**. Quy trình nên theo các lớp:

~~~mermaid
flowchart TD
    A["POST /token với client_assertion"] --> B{"Request và method được đăng ký hợp lệ?"}
    B -->|Không| X["Reject: invalid_client/invalid_request phù hợp"]
    B -->|Có| C["Tra client registry theo client_id được phép"]
    C --> D{"Client bật private_key_jwt?"}
    D -->|Không| X
    D -->|Có| E["Chọn public key thuộc chính client này"]
    E --> F{"alg/key type và chữ ký hợp lệ?"}
    F -->|Không| X
    F -->|Có| G{"iss=sub=client_id, aud đúng AS, exp/iat/nbf hợp lệ?"}
    G -->|Không| X
    G -->|Có| H{"jti mới, chưa replay theo policy?"}
    H -->|Không| X
    H -->|Có| I{"client active, grant/scope/audience được phép?"}
    I -->|Không| X
    I -->|Có| J["Cấp access token phù hợp"]
~~~

Các bước kiểm cụ thể:

1. **Phân tích request:** POST, form encoding, client_assertion_type hợp lệ, kích thước assertion có giới hạn; không cho quá nhiều giá trị tham số mâu thuẫn.
2. **Định danh client:** lấy client_id theo cơ chế được AS hỗ trợ và đối chiếu với **iss/sub của assertion đã xác minh**. Dữ liệu chưa xác minh chỉ có thể là gợi ý tra cứu client trong registry allowlist.
3. **Xác định phương thức đã đăng ký:** client phải được phép dùng private_key_jwt và thuật toán/khoá tương ứng.
4. **Chọn key:** trong **registered public keys của client đó**, có thể dùng **kid** để tìm đúng key. Không chọn key thuộc client hoặc issuer khác chỉ vì kid trùng.
5. **Xác minh mật mã:** chữ ký JWS, thuật toán được phép, loại key phù hợp, cấu trúc JWT/JOSE đúng profile. **Không** chấp nhận **alg=none** hoặc nhầm khóa bất đối xứng thành HMAC key.
6. **Xác minh claims:** **iss, sub, aud, exp** đúng; kiểm **iat, nbf, jti** nếu có hoặc theo policy; từ chối giá trị sai kiểu, quá hạn hoặc audience không được phép.
7. **Chống replay:** nếu dùng jti cache, kiểm và ghi nhận **một lần theo client/issuer và cửa sổ hiệu lực**, bảo vệ atomic khi có nhiều AS instance.
8. **Kiểm trạng thái client/grant:** client đang active, grant_type được bật, scope/resource được phê duyệt, có giới hạn sử dụng hợp lý.
9. **Phát token:** chỉ cấp access token nếu mọi lớp kiểm đạt; không ghi assertion/raw token vào log hoặc tracing.

**Không coi chữ ký hợp lệ là đủ**: một assertion do client ký đúng nhưng có **aud sai**, **exp đã hết**, **iss/sub không khớp**, **jti bị dùng lại**, hoặc client không có quyền với resource phải bị từ chối theo kiểm tra tương ứng.

## 9. Issuer, subject và audience: dễ nhầm nhất trong client authentication

Trong ví dụ private_key_jwt, **iss** và **sub** đều là **reports-worker**, không phải issuer URL của Authorization Server:

~~~text
JWT client assertion:
  iss = reports-worker
  sub = reports-worker
  aud = https://auth.example.org/oauth2/token

OAuth access token được cấp sau đó:
  iss = https://auth.example.org
  sub = reports-worker (tùy profile của service token)
  aud = reports-api
~~~

AS là bên **nhận và xác minh client assertion**. Sau khi xác thực client, AS trở thành **issuer của access token mới**, với key/trust policy riêng.

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Đặt iss của client assertion bằng URL AS thay vì client_id | AS không nhận diện được client theo RFC 7523 client authentication | **iss/sub phải khớp client_id** |
| Dùng aud=reports-api trong assertion | Assertion không dành cho token endpoint/AS | Dùng **audience của AS theo contract** |
| Cho AS chấp nhận mọi aud | Assertion có thể bị replay ở endpoint khác nếu dùng chung key | Kiểm aud đúng giá trị được phép |
| Bỏ exp hoặc cho exp quá xa | Assertion bị đánh cắp có thời gian tái sử dụng lớn | Yêu cầu exp hợp lệ, TTL ngắn |
| Tin kid trước khi biết client | Có thể nhận khóa của client khác | Key lookup trong **tập khóa đăng ký của client** |
| Dùng iss/sub sau decode như bằng chứng đã xác thực | Dữ liệu do caller tự khai được tin trước khi kiểm chữ ký | Chỉ thiết lập authenticated client sau **verify** |

Mốc thời gian **exp, iat, nbf** là **NumericDate** theo chuẩn JWT, tính theo giây Unix epoch, không phải mặc định là mili giây. Cho phép một lượng **clock skew nhỏ theo policy**, không mở rộng vô hạn để che lỗi đồng bộ đồng hồ.

## 10. Replay protection với JWT client assertions

Client assertion bản thân nó là một credential: nếu kẻ tấn công sao chép được chuỗi JWS còn hạn, họ có thể thử gửi lại tại token endpoint. Chữ ký hợp lệ xác minh ai **có khả năng tạo** assertion, nhưng không tự chứng minh đây là lần sử dụng đầu tiên.

### Một vòng đời an toàn

~~~text
10:00:00  Client ký assertion A1:
          iss=sub=reports-worker, aud=token-endpoint,
          iat=10:00:00, exp=10:01:00, jti=J1
10:00:02  AS nhận A1, kiểm chữ ký + claims + J1 chưa dùng
10:00:02  AS ghi nhận J1 đã dùng và có thể cấp access token
10:00:04  A1 được gửi lại với cùng J1
10:00:04  AS phát hiện replay và từ chối theo chính sách
~~~

Mốc và TTL chỉ là ví dụ. Với **jti-based replay detection**, AS cần:

- Khóa nhận diện như **(client_id, jti)**, có thể kèm issuer/profile namespace thích hợp.
- Cửa sổ ghi nhớ ít nhất đủ cho **toàn bộ thời gian assertion có thể còn được chấp nhận**, kể cả skew.
- Thao tác **atomic check-and-insert** trên kho trạng thái chia sẻ; không chỉ dùng Set trong bộ nhớ một AS instance nếu chạy cluster.
- Giới hạn TTL, kích thước và tốc độ request để giảm nguy cơ lạm dụng bộ nhớ/DoS.
- Phân biệt việc JWT sai chữ ký/claims với JWT hợp lệ bị replay; không ghi assertion thô vào log.

**RFC 7523 không bắt buộc mọi triển khai phải yêu cầu jti**. Tuy nhiên, nếu hệ thống tuyên bố chống replay bằng jti, nó phải **thực sự thực thi trạng thái một lần**. Test chỉ kiểm jti có tồn tại trong payload là chưa đủ.

### Concurrency và retry

Nếu hai token requests dùng cùng assertion A1 đến hai AS nodes đồng thời, một thiết kế one-time-jti phải cho **tối đa một request** được chấp nhận. Nếu request đầu đã được xử lý nhưng HTTP response bị mất, client nên **tạo assertion mới với jti mới**, không tự retry mãi cùng A1. Việc cấp access token mới vẫn chịu policy, rate limit và kiểm quyền của client.

Đừng nhầm assertion replay với **refresh token rotation** hoặc **authorization code single-use**. Mỗi cơ chế bảo vệ một credential khác nhau. Với Client Credentials grant, việc **client xin access token mới bằng assertion mới** là hoạt động hợp lệ khi chính sách cho phép; còn việc **phát lại cùng assertion** có thể bị từ chối theo replay policy.

## 11. JOSE header, kid và nguy cơ algorithm/key confusion

JOSE header xuất hiện trước khi verify, nên **chưa đáng tin**. Các trường cần xử lý:

| Header | Được dùng để làm gì? | Ràng buộc an toàn |
|---|---|---|
| **alg** | Thuật toán ký JWT | Chỉ chấp nhận tập thuật toán đã đăng ký/allowlist theo client và key |
| **kid** | Chọn public key có cùng ID trong registry | Không xem kid là định danh toàn cục hoặc quyền tin key mới |
| **typ** | Thông tin kiểu JWT/JWS | Kiểm theo profile nếu cần; không tự tạo trust chỉ vì typ=JWT |
| **jku/x5u** | Có thể trỏ đến nguồn khóa/chứng thư trong JOSE | **Không** tự tải và tin URL từ assertion chưa xác minh |
| **crit** | Các tham số JOSE quan trọng | Thư viện phải xử lý đúng hoặc từ chối |

### Tấn công key substitution

Mẫu **sai**:

~~~text
header = decodeHeader(clientAssertion)
jwks = fetch(header.jku)    # URL do caller tự khai
key = jwks.find(header.kid)
if verifySignature(clientAssertion, key):
    acceptAsClient()
~~~

Kẻ tấn công có thể trỏ tới public key của chính họ và ký assertion bằng private key tương ứng. Việc verify thành công với **key do kẻ tấn công chọn** không chứng minh họ là client được đăng ký.

Mẫu **đúng**:

~~~text
candidateClientId = parseUntrustedClientIdentifier(request)
registration = trustedClientRegistry.lookup(candidateClientId)
require registration.active
require registration.authMethod == private_key_jwt

key = registration.authorizedPublicKeys.find(header.kid)
require allowedAlgorithmForClientAndKey(header.alg, key)
require verifyJwsSignature(assertion, key)
require verifiedClaims.iss == registration.clientId
require verifiedClaims.sub == registration.clientId
require expectedAudienceAndTimeAndReplayChecks(verifiedClaims)
~~~

Đây là **pseudocode**, không phải đầy đủ logic parse, lỗi, quản lý cache hoặc chống SSRF. Nếu lấy JWKS từ **jwks_uri đã đăng ký**, AS cần giới hạn nguồn tin cậy, TLS, kiểm certificate/redirect/caching và chính sách làm mới. Một **kid giống nhau** ở hai client không khiến key của client A dùng được để xác thực client B.

Không cho JWT tự chọn **HS256** khi client đã đăng ký **RS256**, hoặc cho **alg=none** đi qua nhánh bỏ xác minh. **Algorithm confusion** là lỗi chọn sai loại key/thuật toán theo dữ liệu caller tự khai.

## 12. Private key storage: kiểm soát quyền ký quan trọng hơn chỗ đặt file

Private key của confidential client là một **credential dài hạn** có khả năng tạo assertion mới. Mức độ bảo vệ phải tương xứng:

1. **KMS/HSM hoặc key store an toàn:** khi có thể, dùng khóa **non-exportable** và giới hạn API ký theo workload identity.
2. **Least privilege:** chỉ workload được phép ký cho client đó có quyền sử dụng key; tách quyền quản trị key, deploy và xem log.
3. **Không hard-code:** không đưa private PEM vào source code, Docker image, config repo, build artifact, unit test output hoặc chat/ticket.
4. **Secret distribution:** nếu buộc phải nạp key vào tiến trình, dùng kênh cấp phát an toàn, phân quyền hệ điều hành, hạn chế bản sao/backup và ưu tiên key rotation chủ động.
5. **Chống exfiltration qua observability:** không ghi JWK private fields, JWT client assertion, Authorization header hoặc raw token endpoint request.
6. **Giám sát thao tác ký:** theo dõi số lần ký, danh tính workload, lỗi key access và hành vi bất thường, không log private key hoặc assertion thô.
7. **Khóa theo môi trường:** không dùng chung private key và client registration giữa development, staging và production.
8. **Chuẩn bị quy trình thu hồi:** có thể ngừng ký, gỡ public key đã bị lộ, chuyển sang key mới và kiểm tất cả AS instances.

**Private key authentication không tự giúp browser SPA trở thành confidential client.** Nếu private key nằm trong bundle JavaScript hoặc native app có thể bị giải nén/đọc rộng rãi, attacker có thể lấy private key để tự ký. Loại client phải được đánh giá theo khả năng **giữ credential bí mật** trong môi trường thực, không theo tên thư viện.

## 13. Key rotation, JWKS cache và xử lý khóa bị xâm phạm

Trong vận hành bình thường, private key có thể cần được xoay để giới hạn rủi ro. Một quy trình minh họa:

| Giai đoạn | Client / khóa | Authorization Server |
|---|---|---|
| **T0: trạng thái hiện tại** | Client ký bằng **K1** | Public key **K1** đã được đăng ký và chấp nhận |
| **T1: chuẩn bị** | Sinh **K2** ở môi trường an toàn; chưa ký production | Đăng ký public **K2**, cho phép **K1 + K2** trong giai đoạn chuyển tiếp |
| **T2: chuyển signer** | Client tạo assertion mới với **kid=K2** | AS chọn K2, xác minh chữ ký |
| **T3: xác minh triển khai** | Tất cả instance đã dùng K2 | Quan sát không còn assertion hợp lệ cần K1, qua TTL assertion và cache phù hợp |
| **T4: hoàn tất** | Ngừng sử dụng K1 | Gỡ/disable public K1, thu hẹp trust |

**Không gỡ K1 quá sớm** nếu còn instance chưa chuyển signer; nhưng cũng **không giữ K1 mãi** vì lý do tương thích. Độ trễ cập nhật JWKS/cache phải được tính trong kế hoạch.

### Khi private key bị lộ: rotation thông thường không đủ

Nếu **K1 bị xâm phạm**, attacker có thể ký assertion mới bằng K1. Khi đó:

- **Dừng chấp nhận K1 càng sớm càng khả thi trên toàn bộ Authorization Server instances**, kể cả nơi còn cache JWKS cũ.
- Điều tra token đã được phát cho client qua các assertions đáng ngờ; thu hồi/giới hạn access token khi cần theo mô hình revocation.
- Đánh giá đường xâm nhập key store, CI/CD, workload identity, log và backup.
- Cấp K2 an toàn, cập nhật registration và xác minh quyền ký của workload hợp pháp.
- Theo dõi hậu quả: một access token đã được cấp hợp lệ bởi AS cho attacker có thể còn hiệu lực tại Resource Server nếu không có cơ chế thu hồi sớm.

**Xóa key khỏi JWKS không bảo đảm mọi cache ngừng dùng key ngay**, và **xoay private key client không đồng nghĩa private signing key của Authorization Server đã lộ**. Hai loại key phục vụ hai trust domains riêng, cần xử lý sự cố đúng phạm vi.

## 14. Client authentication không làm access token tự trở thành proof-of-possession

Một hiểu nhầm nguy hiểm: “Vì client ký JWT bằng private key tại token endpoint, access token nhận lại chắc chắn chỉ client ấy mới sử dụng được.”

Điều đó **không tự đúng**.

**private_key_jwt** chứng minh danh tính client **trong request cấp token**. Nếu AS trả **Bearer access token**, người khác lấy được chuỗi bearer token có thể thử gọi API trong audience/scope/thời hạn của nó, ngay cả khi họ **không có private key** dùng để xác thực client ban đầu.

| Cơ chế | Bảo vệ điều gì? | Có tự ràng buộc access token? |
|---|---|---|
| **private_key_jwt** | Xác thực client với AS bằng chữ ký JWT | **Không mặc định** |
| **mTLS client authentication** | Xác thực client ở AS bằng chứng thư | Không tự động, trừ khi AS/RS cấu hình token binding theo mTLS |
| **mTLS-bound access token** | Yêu cầu proof bằng chứng thư khi dùng token | Có, nếu RS kiểm ràng buộc đúng profile |
| **DPoP-bound access token** | Yêu cầu proof ký bằng khóa tương ứng cho request | Có, nếu AS phát và RS xác minh proof/token binding đúng giao thức |
| **Bearer JWT/opaque access token** | Credential truy cập Resource Server | Có thể bị tái sử dụng bởi người giữ token nếu không có sender-constraining |

Nếu yêu cầu chống replay access token khi bị đánh cắp, cần thiết kế **sender-constrained tokens** như mTLS/DPoP khi các bên hỗ trợ, cộng với TTL, audience, scope, bảo vệ lưu trữ và giám sát. Không lẫn **khóa ký client assertion** với **khóa ký JWT access token của AS** hoặc **khóa DPoP**; các khóa có thể khác nhau và phải được quản lý theo hợp đồng giao thức.

## 15. Vai trò của JWT, opaque token, claims, scope và audience

Sau khi xác minh private_key_jwt, AS có thể cấp access token cho reports-worker dưới dạng **JWT** hoặc **opaque**:

### JWT access token dành cho Reports API

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "reports-worker",
  "aud": "reports-api",
  "client_id": "reports-worker",
  "scope": "reports:read",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "access-example-572"
}
~~~

JSON này **chưa phải JWT có chữ ký** và chỉ để minh họa. Nếu sử dụng **RFC 9068 JWT access token profile**, token phải tuân thủ các claims/header bắt buộc của profile, được ký bằng key AS được RS tin, và Resource Server kiểm đầy đủ.

### Opaque access token

Nếu AS cấp opaque access token, Reports API thường kiểm qua **OAuth 2.0 Token Introspection (RFC 7662)** hoặc nguồn trạng thái tin cậy:

~~~json
{
  "active": true,
  "client_id": "reports-worker",
  "sub": "reports-worker",
  "aud": ["reports-api"],
  "scope": "reports:read",
  "exp": 1795400900
}
~~~

**active=true** là metadata trạng thái, **không thay** kiểm audience, loại token và policy. HTTP 200 từ introspection không có nghĩa token đang active. Resource Server phải biết chính xác token được cấp cho API của mình, thuộc loại access token, còn thời hạn và được quyền thực hiện thao tác.

### Tại sao không dùng JWT client assertion để gọi API?

JWT client assertion thường có **aud=token endpoint/AS**, không phải **reports-api**, và chức năng của nó là **client authentication**. Dù assertion được ký hợp lệ bằng private key của reports-worker, Reports API phải **từ chối nếu nó được gửi như Bearer access token**. Tương tự, refresh token hoặc OIDC ID token không được thay access token tại Resource Server.

**Scope reports:read** cho phép API đánh giá quyền đọc báo cáo nhưng không tự cho phép đọc mọi báo cáo thuộc mọi tenant. Resource Server còn kiểm resource ownership, tenant, role/chính sách dịch vụ và trạng thái hiện hành.

## 16. Multi-client, multi-tenant và cách chọn public key an toàn

Trong AS có nhiều OAuth clients, mỗi client có thể đăng ký nhiều public keys và có **kid trùng nhau**. Bởi vậy quy trình chọn key cần bắt đầu từ **client registration** và cấu hình tin cậy:

~~~text
reports-worker:
    kid=prod-key   -> public key A

billing-worker:
    kid=prod-key   -> public key B
~~~

Nếu assertion tự khai **iss=reports-worker** nhưng được ký bằng private key của **billing-worker**, AS không được dùng **public key B** chỉ vì kid giống nhau. Chữ ký phải được xác minh bằng key đã đăng ký cho **reports-worker**; nếu không khớp thì từ chối.

Với tenant:

- Nếu mỗi tenant có OAuth client riêng, **client_id + key registration + allowed grant/scope/resource** phải tách rạch ròi.
- Nếu nhiều tenant cùng dùng một service principal, AS và Resource Server cần **tenant authorization contract** để tránh client có scope chung tự chọn tenant bất kỳ.
- Client assertion **không tự là chứng cứ người dùng đã đồng ý hoặc thuộc một tenant**. Đừng cho caller nhúng **tenantId** tùy ý vào assertion để mở quyền.
- Việc chuyển một client từ staging sang production không nên chỉ là đổi audience; dùng **registration và key policy riêng**.
- Public key đến từ JWKS được đăng ký phải được gắn với đúng client, không nhận URL từ claim **iss** hoặc header **jku** như nguồn tự do.

Nếu hệ thống có nhiều Authorization Servers, client phải ký assertion cho **đúng audience AS/token endpoint** của giao dịch, không tái sử dụng một JWT assertion có aud quá rộng. Trong hệ thống federation hoặc broker, điều kiện chấp nhận mỗi AS/profile cần được quy định riêng.

## 17. Lỗi OAuth và hành vi fail closed

Token endpoint nên trả lỗi phù hợp với nguyên nhân, không tiết lộ private key, assertion hoặc nội dung nhạy cảm.

| Trường hợp | Lỗi thường gặp | Hành vi an toàn |
|---|---|---|
| Client assertion sai chữ ký | **invalid_client** | Không cấp token |
| Client dùng thuật toán không được đăng ký | **invalid_client** hoặc lỗi phù hợp contract | Không fallback sang alg yếu hơn |
| iss/sub không khớp client_id | **invalid_client** | Không xác thực client |
| aud sai AS/token endpoint | **invalid_client** | Không chấp nhận assertion của nơi nhận khác |
| exp hết hạn hoặc thiếu exp | **invalid_client** | Không cấp token |
| jti đã dùng lại trong profile yêu cầu replay detection | **invalid_client** | Từ chối, ghi sự kiện an toàn |
| Client đã disable hoặc bị thu hồi key | **invalid_client** | Không chấp nhận JWT mới của client/key |
| Client xác thực hợp lệ nhưng grant không được phép | **unauthorized_client** | Không cấp token theo grant đó |
| Scope yêu cầu không hợp lệ/vượt quyền | **invalid_scope** hoặc từ chối/thu hẹp theo hợp đồng | Không nâng quyền |
| Form body sai hoặc thiếu tham số bắt buộc | **invalid_request** | Không cấp token |
| JWKS hoặc kho client registry không truy cập được an toàn | Lỗi phụ thuộc hệ thống phù hợp, có thể **5xx/503** | **Fail closed**, không tự tin JWT chưa xác minh |

Ví dụ lỗi xác thực client:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_client"
}
~~~

HTTP status là **ví dụ theo ngữ cảnh**; RFC 6749 có quy tắc riêng cho **invalid_client**, bao gồm trường hợp xác thực bằng header Authorization và challenge tương ứng. Không giả định mọi AS đều luôn trả 401 cho mọi invalid_client. Với **invalid_scope** hoặc **unauthorized_client**, vấn đề nằm ở quyền/grant, không phải private key verification nhất thiết đã thất bại.

Log nên có **client_id đã được chuẩn hóa/kiểm soát**, request ID, mã lỗi, key ID nội bộ khi an toàn và latency; không ghi **client_assertion**, access token, raw JWT payload hoặc private key. Claims từ assertion chưa xác minh không được đưa vào audit như danh tính đã xác thực.

## 18. Ma trận kiểm thử private key authentication

Các bài test cần kiểm **không có token được phát hành** trong các trường hợp thất bại, không chỉ HTTP status.

| ID | Trường hợp | Kết quả mong đợi |
|---|---|---|
| **S01** | JWT assertion ký đúng private key đã đăng ký, iss/sub/aud/exp hợp lệ, jti mới, grant/scope hợp lệ | **Success**, cấp access token đúng audience |
| **S02** | Client chuyển từ K1 sang K2 đã đăng ký trong giai đoạn rotation | **Success** với K2 theo policy |
| **S03** | Client dùng private_key_jwt với authorization_code grant được AS cho phép | Xác thực client thành công, grant vẫn phải được kiểm riêng |
| **F01** | JWT bị sửa payload sau khi ký | Từ chối vì chữ ký sai |
| **F02** | JWT được ký bằng private key không nằm trong registration client | Từ chối |
| **F03** | Assertion tự khai iss của client A nhưng ký bằng key client B có cùng kid | Từ chối, không chọn key giữa các client |
| **F04** | Header alg=none | Từ chối |
| **F05** | Header chuyển RS256 sang HS256 dù client chỉ đăng ký RS256 | Từ chối, không algorithm confusion |
| **F06** | Header jku trỏ đến JWKS của attacker | Không tin URL tùy ý, từ chối nếu không verify bằng registered key |
| **F07** | iss không bằng client_id | Từ chối |
| **F08** | sub không bằng client_id | Từ chối |
| **F09** | aud=reports-api thay vì expected token endpoint/AS audience | Từ chối |
| **F10** | exp đã qua | Từ chối |
| **F11** | exp thiếu, sai kiểu, hoặc TTL vượt policy | Từ chối |
| **F12** | nbf ở tương lai hoặc iat bất thường theo policy | Từ chối |
| **F13** | jti trùng giá trị đã dùng trong replay cache | Từ chối theo replay policy |
| **F14** | Hai AS instances nhận đồng thời cùng assertion/jti | Tối đa một lần chấp nhận nếu policy one-time-jti |
| **F15** | client_assertion_type sai hoặc không được hỗ trợ | Từ chối |
| **F16** | Client không được phép dùng private_key_jwt | Từ chối |
| **F17** | Client authentication đúng nhưng yêu cầu grant client_credentials chưa được cho phép | Từ chối grant |
| **F18** | Client authentication đúng nhưng scope=payments:charge vượt quyền | Không cấp scope vượt quyền |
| **F19** | Client xin audience ngoài danh sách resource được duyệt | Từ chối |
| **F20** | K1 bị thu hồi nhưng vẫn nằm trong JWKS cache của một AS node | K1 phải bị từ chối theo cơ chế thu hồi tin cậy |
| **F21** | JWT client assertion được gửi làm Bearer đến Reports API | Resource Server từ chối sai loại/audience |
| **F22** | AS trả access token JWT/opaque nhưng Reports API nhận sai issuer/audience | Resource Server từ chối |
| **F23** | Debug log/APM/tracing được bật tại token endpoint | Không có assertion, private key hoặc access token thô |
| **F24** | AS tạm không truy cập được registry hoặc public key đã đăng ký | Không cấp token theo cơ chế fail-open |

### Những assertions kiểm thử có giá trị nhất

- **S01** phải kiểm cả token thật sự được cấp, issuer/audience/scope/thời hạn và quyền tại Resource Server.
- **F01–F06** chứng minh AS không tin JWT chỉ vì parse được header/payload hoặc có một public key ngẫu nhiên.
- **F07–F12** chứng minh claims của client authentication không bị bỏ qua.
- **F13–F14** chứng minh replay cache/one-time semantics hoạt động qua **nhiều instance**, nếu đây là chính sách được triển khai.
- **F17–F19** chứng minh **client authentication thành công không tự động cấp mọi quyền**.
- **F20/F23** kiểm khả năng phản ứng sự cố và vệ sinh credential, thường bị bỏ quên trong unit tests.

Đối với negative tests, dùng **test keys và test clients**. Không đưa private key hoặc bearer token production vào công cụ web/CI artifacts chỉ để thử xác minh chữ ký.

## 19. Tình huống thực tế: báo cáo và thanh toán

Giả sử một nền tảng có hai confidential clients:

| Client | Public key registration | Quyền được cấp |
|---|---|---|
| **reports-worker** | K1, K2 theo vòng đời rotation | client_credentials, aud=reports-api, scope=reports:read |
| **billing-worker** | B1 | client_credentials, aud=payments-api, scope=payments:charge |

### Tình huống A — Reports worker lấy token hợp lệ

reports-worker ký assertion bằng K2, với **iss=sub=reports-worker**, **aud=token endpoint**, **exp ngắn**, jti mới. AS xác minh K2 thuộc reports-worker, cấp access token **aud=reports-api, scope=reports:read**. Reports API kiểm access token và quyền đọc báo cáo.

### Tình huống B — Dùng đúng key nhưng xin quyền của Billing

reports-worker ký đúng bằng K2 nhưng gửi **scope=payments:charge** và yêu cầu token cho Payments API. **AS phải từ chối hoặc không cấp quyền vượt policy**, mặc dù client đã xác thực thành công. Private key chứng minh danh tính client, không làm nó thành quản trị viên của mọi API.

### Tình huống C — Bị lấy cắp một JWT client assertion

Kẻ tấn công lấy được assertion A1 từ debug log rồi gửi lại trong thời hạn. Nếu AS có replay cache theo jti và A1 đã được dùng, request phải bị từ chối. Nếu AS không có cơ chế replay tương ứng, **chữ ký và exp một mình không ngăn phát lại trong cửa sổ sống**; cần giảm thời gian sống, kiểm soát telemetry và áp dụng replay policy thích hợp.

### Tình huống D — Private key K1 bị xâm phạm

Khác với lộ một assertion, kẻ tấn công có thể **tạo nhiều assertions mới** có chữ ký đúng bằng K1. Phải **ngừng tin K1 tại AS**, điều tra token đã cấp và xử lý token còn khả năng truy cập API. Chỉ chờ assertions cũ hết hạn không đủ vì attacker có thể ký assertion mới cho đến khi K1 bị thu hồi.

### Tình huống E — Access token bearer bị lộ nhưng private key vẫn an toàn

Kẻ lấy access token có thể thử gọi Reports API khi token còn hạn, dù không ký được client assertion mới. **private_key_jwt không tự chống bearer access token replay**. Dùng TTL ngắn, scope/audience giới hạn, bảo vệ log/storage và sender-constraining khi phù hợp.

## 20. Checklist triển khai và vận hành

1. **Đúng mục đích:** Private key được dùng làm **client authentication**, không nhầm JWT assertion grant hoặc access token?
2. **Đúng loại client:** Client có khả năng bảo vệ private key an toàn và được đăng ký là confidential client?
3. **Đúng registration:** AS lưu **client_id, auth method, signing algorithms, public keys/JWKS URI, grant types, scopes/resources** trong cấu hình đáng tin?
4. **Đúng form request:** **grant_type=client_credentials** và **client_assertion_type** đầy đủ, JWT được gửi như assertion chứ không gửi private key?
5. **JOSE:** alg allowlist theo client, key đúng kiểu, kid chỉ tra trong registration, không tin jku/x5u tùy ý?
6. **JWT claims:** iss/sub bằng client_id, aud đúng AS, exp hợp lệ; iat/nbf/jti theo profile/policy?
7. **Replay:** Assertion sống ngắn, jti mới và cache one-time atomic nếu policy chống replay yêu cầu?
8. **TLS:** Token endpoint và public JWKS URI dùng TLS với certificate verification đúng; không log request/response nhạy cảm?
9. **Key custody:** Private key lưu ở KMS/HSM/secret store an toàn, không vào source, image, log, CI artifacts?
10. **Rotation:** Có thể thêm K2, chuyển signer, xác nhận mọi instance, gỡ K1 sau giai đoạn phù hợp?
11. **Compromise:** Có đường **disable key ngay**, gỡ cache cũ và thu hồi/giảm tác động token đã cấp?
12. **Grant policy:** Client đã xác thực không được tự nâng scope, audience hoặc nhận quyền user chưa được ủy quyền?
13. **Access token:** JWT/opaque access token được AS phát với issuer, audience, scope, TTL và profile phù hợp?
14. **Resource Server:** API kiểm chữ ký/introspection, đúng audience, scope, thời hạn và policy tài nguyên; từ chối client assertions/ID/refresh tokens?
15. **Sender-constraining:** Nếu cần chống bearer access token bị dùng lại, AS và RS hỗ trợ DPoP/mTLS token binding riêng?
16. **Observability:** Chỉ audit reason code/request ID/key label an toàn; không ghi assertion, private key, token hoặc decoded payload nhạy cảm?
17. **Tests:** Có success, wrong key, wrong client, wrong aud, expired, replay/concurrency, alg confusion, key rotation và secret leakage tests?
18. **Phụ thuộc:** Khi không xác minh được key/registry/AS state, hệ thống **fail closed** thay vì cho phép?

## 21. Câu hỏi tự đánh giá

**1. Private key authentication khác Client Credentials grant thế nào?** Private key authentication xác minh **client là ai**; Client Credentials grant quy định **client xin token theo quyền của chính client**. Chúng thường được dùng cùng nhau nhưng không phải một khái niệm.

**2. Client có gửi private key đến token endpoint không?** Không. Client ký JWT assertion bằng private key; AS xác minh bằng public key đã đăng ký.

**3. Tại sao iss và sub của client assertion thường bằng client_id?** Theo RFC 7523 client authentication, JWT được phát hành và đại diện cho chính OAuth client đang xác thực.

**4. Audience của JWT client assertion là Reports API hay Authorization Server?** Authorization Server/token endpoint theo hợp đồng. Access token do AS cấp mới có audience dành cho Reports API.

**5. Có thể dùng cùng một JWT assertion trong nhiều token requests không?** Không nên. Assertion ngắn hạn với jti mới cho mỗi request giúp chống replay; AS cần kiểm trạng thái jti nếu áp dụng chính sách one-time.

**6. Một private_key_jwt có chữ ký hợp lệ đã đủ để AS cấp mọi scope chưa?** Chưa. AS còn kiểm client active, grant_type, quyền scope, audience và resource policy.

**7. kid có chứng minh một public key thuộc client không?** Không. kid chỉ là nhãn chọn key; AS phải tìm trong **public keys được đăng ký của chính client đó**.

**8. Có thể tải JWKS từ jku trong JWT assertion để verify không?** Không mặc định. Nguồn key phải đến từ **registration đáng tin**, tránh attacker tự chọn key hoặc URL.

**9. private_key_jwt có làm access token nhận được tự chống replay không?** Không. Nếu access token là bearer, bên giữ nó có thể thử sử dụng; chống replay ở Resource Server cần biện pháp riêng như sender-constraining khi phù hợp.

**10. Nếu private key bị lộ, chỉ chờ exp của assertion hiện tại là đủ?** Không. Kẻ tấn công có thể ký assertion mới; AS phải ngừng tin key bị lộ và xử lý token đã cấp theo chính sách sự cố.

**Ghi nhớ:** **private_key_jwt cho phép confidential client chứng minh quyền sở hữu private signing key tại Authorization Server mà không gửi private key qua token request.** AS phải xác minh **public key được đăng ký đúng client, thuật toán/chữ ký, iss=sub=client_id, audience của AS, thời hạn và replay policy**, rồi mới kiểm **grant, scope và resource** trước khi phát access token. Private key cần được bảo vệ, xoay và thu hồi đúng cách; access token trả về vẫn phải được Resource Server kiểm **issuer, audience, thời hạn và quyền trên tài nguyên**, và bearer token bị đánh cắp vẫn cần biện pháp giảm replay riêng.
