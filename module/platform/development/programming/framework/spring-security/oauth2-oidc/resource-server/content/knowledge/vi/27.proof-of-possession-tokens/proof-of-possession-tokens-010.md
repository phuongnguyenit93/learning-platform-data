# mTLS-bound token và việc đối chiếu token với chứng chỉ kết nối

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, Bearer Access Token thông thường có một đặc điểm quan trọng: bên nào có token đều có thể thử sử dụng nó. Nếu token bị lấy từ log, máy trạm, proxy hoặc một kết nối bị xâm phạm, kẻ lấy được token có thể gửi request đến API cho đến khi token hết hạn hoặc bị thu hồi.

**Mutual TLS (mTLS) certificate-bound Access Token** theo **RFC 8705** bổ sung một ràng buộc: Authorization Server gắn Access Token với **chứng chỉ X.509 của client**. Khi client gọi Resource Server, nó phải chứng minh possession của private key tương ứng thông qua TLS client authentication. Resource Server xác minh chứng chỉ ở tầng TLS, tính thumbprint của chứng chỉ và so sánh với confirmation claim trong token.

Ba thành phần phải đi cùng nhau:

- **Access Token**: credential mang issuer, subject/client, audience, scopes và thời hạn.
- **Client certificate**: chứng chỉ X.509 được trình trong TLS handshake; private key tương ứng nằm ở client.
- **Certificate binding**: claim `cnf.x5t#S256` trong Access Token chứa SHA-256 thumbprint của chứng chỉ đã được ràng buộc.

**mTLS-bound token không phải là token mới thay thế Access Token.** Client vẫn gửi Access Token trong Authorization header theo cơ chế Bearer, đồng thời trình đúng client certificate ở TLS connection. Resource Server chỉ chấp nhận token khi token hợp lệ và chứng chỉ kết nối khớp binding.

Bài học thuộc chương **Token ràng buộc khóa**, dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x** làm bối cảnh. Nội dung trình bày RFC 8705, quy trình cấp token, claim `cnf`, cách tính `x5t#S256`, cấu hình TLS, tích hợp Resource Server, TLS termination qua proxy, vòng đời chứng chỉ, kiểm thử và vận hành. Các URL, certificate và token trong ví dụ đều là dữ liệu giả.

## 1. Bearer token và vấn đề token bị đánh cắp

Với Bearer token thông thường:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource Server xác minh token. Nếu token hợp lệ và scope cho phép, request được xử lý. Server không có bằng chứng mật mã rằng người gửi chính là client đã nhận token ban đầu.

~~~text
Client hợp lệ ---- Bearer token T ----> Resource Server
       |
       +---- Token T bị sao chép ----> Attacker
                                        |
                                        +---- Bearer T ----> Resource Server
~~~

Attacker không cần private key nào khác ngoài việc nắm giữ T. TLS bảo vệ token trên đường truyền, nhưng không tự ngăn token bị sao chép từ nơi lưu trữ, endpoint hoặc log.

Với mTLS-bound token:

~~~text
Authorization Server phát hành T
  cnf.x5t#S256 = thumbprint(certificate C)

Client giữ private key tương ứng C
        |
        +-- TLS handshake tới Resource Server
        |      Client trình certificate C
        |      Chứng minh possession private key
        |
        +-- HTTP Authorization: Bearer T
                 |
                 v
          Resource Server
            - Xác minh TLS client certificate
            - Xác minh Access Token
            - Tính thumbprint(cert C)
            - So sánh với token.cnf.x5t#S256
            - Kiểm tra scope và domain permissions
~~~

Kẻ chỉ đánh cắp được T nhưng không có private key tương ứng **không thể hoàn thành TLS client authentication bằng chứng chỉ đã bind**. Đây là cơ chế **sender-constrained token** (token ràng buộc người gửi).

## 2. Ba khái niệm không được nhầm lẫn

| Thành phần | Vai trò | Nơi được xác minh |
| --- | --- | --- |
| **Access Token** | Mang quyền truy cập resource. | Spring Security JWT decoder hoặc opaque-token introspection. |
| **Client certificate** | Chứng minh possession private key qua TLS. | TLS server/proxy trong handshake. |
| **Certificate binding** | Xác nhận token được cấp cho đúng certificate. | Resource Server đối chiếu `cnf.x5t#S256` với certificate của kết nối. |

Chứng chỉ có thể được dùng ở hai giai đoạn OAuth khác nhau:

1. **mTLS client authentication tại Authorization Server**: chứng chỉ giúp xác thực OAuth client khi gọi token endpoint.
2. **Certificate-bound Access Token tại Resource Server**: cùng certificate được gắn với Access Token, và client phải chứng minh possession khi gọi API.

Hai mục đích có liên quan nhưng **không đồng nghĩa**. Việc AS dùng mTLS để xác thực client không tự chứng minh Resource Server đã kiểm tra token-to-certificate binding. Ngược lại, Resource Server có thể kiểm tra binding chỉ khi AS đã phát hành token với confirmation claim đúng theo contract.

## 3. RFC 8705: certificate-bound Access Token

**RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens** định nghĩa cách dùng chứng chỉ X.509 trong OAuth 2.0:

- Mutual TLS có thể được dùng để xác thực OAuth client với Authorization Server.
- Access Token có thể được **ràng buộc với client certificate**.
- Resource Server xác minh client certificate của kết nối và đối chiếu thumbprint với token.

### 3.1. Confirmation claim trong JWT Access Token

Nếu Access Token là JWT, payload có thể có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

`cnf` là **confirmation claim**. Trong profile certificate-bound của RFC 8705, member `x5t#S256` mang thumbprint SHA-256 của certificate.

### 3.2. Opaque Access Token

Opaque token không thể tự decode thành JWT claims ở Resource Server. Khi introspect, Authorization Server có thể trả metadata:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-client",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

Resource Server phải dùng **introspection response đã được xác thực** làm nguồn binding. Nếu AS không trả `cnf.x5t#S256` cho token được kỳ vọng là certificate-bound, Resource Server không có đủ thông tin để xác minh sender constraint và phải từ chối theo policy.

### 3.3. Token type và Authorization header

Certificate-bound Access Token theo RFC 8705 vẫn thường được gửi bằng **Bearer authorization scheme**:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Sự khác biệt nằm ở **TLS client certificate và bước đối chiếu binding**, không phải đổi scheme thành một scheme HTTP mới. Điều này khác DPoP, nơi client gửi proof trong header `DPoP` và sử dụng token type `DPoP`.

Không suy ra rằng mọi Bearer token đều certificate-bound. Resource Server cần biết token nào **bắt buộc** có binding theo issuer/client/resource contract và từ chối nếu thiếu claim.

## 4. Thumbprint x5t#S256 được tính như thế nào?

`x5t#S256` là **Base64url-encoded SHA-256 thumbprint của DER-encoded X.509 certificate**.

~~~text
certificateDer = X509Certificate.getEncoded()
digest         = SHA-256(certificateDer)
thumbprint     = BASE64URL(digest) without padding
~~~

Điểm quan trọng:

- Hash **certificate DER bytes**, không phải PEM text có header/footer/newlines.
- Không hash public key riêng lẻ (SPKI) thay cho certificate.
- Không hash certificate chain hoặc CA certificate nếu token binding được tạo từ client certificate leaf.
- Không dùng SHA-1.
- Base64url encoding phải đúng quy tắc JOSE, không padding.

### 4.1. Ví dụ cách tính bằng Java

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.cert.CertificateEncodingException;
import java.security.cert.X509Certificate;
import java.util.Base64;

public final class CertificateThumbprints {

    private CertificateThumbprints() {
    }

    public static String x5tS256(X509Certificate certificate) {
        try {
            byte[] der = certificate.getEncoded();
            byte[] digest =
                MessageDigest.getInstance("SHA-256").digest(der);

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (CertificateEncodingException
                 | NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "Cannot calculate certificate thumbprint", ex);
        }
    }
}
~~~

Đoạn code chỉ tính thumbprint; **nó không xác minh certificate chain, validity, EKU, revocation hoặc TLS handshake**. Những bước đó phải được TLS stack hoặc thành phần proxy tin cậy thực hiện.

### 4.2. Vì sao không so sánh Subject CN?

Hai certificate có thể có cùng Subject/CN nhưng khác public key hoặc serial number. Ngược lại, certificate mới khi rotate có thể có Subject tương tự nhưng DER bytes khác:

~~~text
Certificate C1:
  Subject = CN=orders-client
  thumbprint = H1

Certificate C2:
  Subject = CN=orders-client
  thumbprint = H2

H1 != H2
~~~

Binding dùng **thumbprint chính xác của certificate**, không phải CN, SAN hay chuỗi tên subject. Các trường subject/SAN có thể phục vụ policy nhận dạng client riêng, nhưng không thay `x5t#S256`.

## 5. Quy trình phát hành certificate-bound token

Client có certificate C và private key tương ứng. Khi lấy Access Token, client gửi request qua kết nối TLS có client authentication tới Authorization Server.

~~~text
Client                         Authorization Server
  |                                    |
  | Tạo/được cấp certificate C         |
  | Giữ private key k                  |
  |                                    |
  | TLS handshake với AS               |
  | Client Certificate: C              |
  | Proof of private-key possession    |
  |----------------------------------->|
  |                                    |
  | POST /oauth2/token                 |
  | grant_type=client_credentials ...  |
  |----------------------------------->|
  |                                    |
  | AS xác thực OAuth client theo      |
  | mTLS policy (nếu cấu hình)         |
  |                                    |
  | AS phát hành Access Token T         |
  | cnf.x5t#S256 = thumbprint(C)        |
  |                                    |
  | access_token=T, token_type=Bearer  |
  |<-----------------------------------|
~~~

Trong ví dụ này, mTLS vừa xác thực client tại token endpoint vừa cung cấp certificate để bind token. Với authorization-code flow, refresh hoặc những grant khác, chi tiết request thay đổi, nhưng nguyên tắc binding vẫn phải theo RFC 8705 và AS contract.

### 5.1. Ví dụ token request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

Client certificate được trình trong **TLS handshake**, không gửi certificate như một form field. Server xác thực client theo TLS certificate policy và có thể phát hành token gắn với thumbprint của certificate.

### 5.2. Token response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

Nếu token là JWT, claim `cnf` nằm trong payload đã được AS ký. Nếu opaque, Resource Server cần nhận binding qua introspection.

### 5.3. Client authentication và token binding là hai kiểm tra

Không được viết kết luận:

> “AS yêu cầu mTLS khi lấy token, nên mọi API nhận token này tự động biết certificate.”

Resource Server có thể ở một domain, TLS listener hoặc proxy khác. Nó cần **nhận certificate của kết nối client** và so sánh thumbprint với token. Nếu RS chỉ nhận Bearer header trên kết nối TLS thông thường không có client certificate, nó không thể chứng minh possession của certificate đã bind.

## 6. Gọi Resource Server bằng certificate-bound token

Client mở TLS connection đến Resource Server, trình đúng certificate C và gửi Access Token T:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Client certificate **không xuất hiện trong HTTP header thông thường**. Nó được trình ở TLS handshake; TLS server nhận được peer certificate sau khi client authentication được yêu cầu và thành công.

Resource Server kiểm tra:

~~~text
TLS connection
  - client certificate chain hợp lệ?
  - certificate còn hạn và được phép làm client?
  - TLS stack đã xác minh private-key possession?
          |
          v
HTTP Authorization: Bearer T
  - Access Token hợp lệ?
  - issuer/audience/exp/scope đúng?
  - token có cnf.x5t#S256?
          |
          v
certificate thumbprint == token.cnf.x5t#S256?
          |
     +----+----+
     |         |
    Yes        No
     |         |
     v         v
 Continue    Reject
     |
     v
 Domain authorization
~~~

**Cả token lẫn certificate đều phải được xác minh**. Một certificate được TLS trust nhưng không khớp token vẫn không được dùng với token đó; một token có claim `cnf` đúng nhưng TLS connection không có certificate hợp lệ cũng không được chấp nhận.

## 7. Tầng TLS phải xác minh client certificate

mTLS có nghĩa **cả server và client xác thực certificate trong TLS handshake**:

- Client xác minh server certificate để biết đang kết nối đúng Resource Server.
- Resource Server xác minh client certificate theo trust anchors/policy.
- TLS stack kiểm tra proof-of-possession của private key qua handshake.
- Ứng dụng lấy peer certificate đã được TLS stack chấp nhận và đối chiếu token binding.

### 7.1. Những kiểm tra certificate cần xem xét

| Kiểm tra | Ý nghĩa |
| --- | --- |
| Certificate chain | Xây dựng chain tới trust anchor được cấu hình. |
| Validity period | `notBefore`/`notAfter` phù hợp thời điểm hiện tại. |
| Key usage | Phù hợp với mục đích client authentication. |
| Extended Key Usage | Có `clientAuth` theo policy. |
| Algorithm/key strength | Đáp ứng security baseline. |
| Certificate revocation | CRL/OCSP hoặc cơ chế revocation phù hợp policy. |
| Name/identity policy | SAN/subject/issuer nếu hệ thống có policy nhận dạng bổ sung. |
| Thumbprint binding | Certificate leaf đang dùng khớp `cnf.x5t#S256` trong token. |

**Thumbprint match không thay thế certificate validation.** Nếu server chỉ hash một certificate do client tự gửi trong HTTP body mà không xác minh chain/private-key possession, attacker có thể gửi public certificate copy và giả mạo binding.

### 7.2. Certificate revocation khác Access Token revocation

Nếu certificate bị revoke tại CA:

- TLS server cần có chính sách kiểm tra CRL/OCSP hoặc nguồn trạng thái chứng chỉ phù hợp.
- Việc certificate có thumbprint trùng token không chứng minh certificate vẫn được phép sử dụng.
- Nếu TLS stack không kiểm tra certificate revocation theo policy, một certificate bị revoke có thể vẫn qua chain validation tùy triển khai.
- Access Token có thể cần revoke riêng tại AS; hai lifecycle không tự động đồng bộ.

Khi có sự cố private key/certificate bị lộ, thường phải **thu hồi certificate, revoke tokens đã bind với nó, cấp certificate mới và phát token mới**.

## 8. Cấu hình mTLS inbound trong Spring Boot

Với embedded Tomcat/Jetty hỗ trợ cấu hình SSL phù hợp, ví dụ:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/orders-server.p12
    key-store-type: PKCS12
    key-store-password: CHANGE_ME_FROM_SECRET_STORE
    trust-store: file:/run/secrets/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: CHANGE_ME_FROM_SECRET_STORE
    client-auth: need
~~~

Ý nghĩa:

- **key-store** chứa server certificate/private key để client xác minh API.
- **trust-store** chứa CA/trust anchors mà API dùng để xác minh client certificate.
- **client-auth: need** yêu cầu client trình certificate; handshake không có certificate hợp lệ sẽ thất bại trước khi vào controller/security filter.

Các giá trị password ở trên là placeholder, phải được lấy từ secret manager/environment theo cơ chế của deployment. Không commit password hoặc private key vào repository.

### 8.1. client-auth need, want và none

| Giá trị | Hành vi khái quát | Trường hợp sử dụng |
| --- | --- | --- |
| `need` | Bắt buộc client certificate ở TLS handshake. | Listener/endpoint yêu cầu mTLS cho toàn bộ kết nối. |
| `want` | Yêu cầu certificate nhưng có thể tiếp tục nếu không có, tùy TLS/container behavior. | Chỉ dùng khi ứng dụng có policy phân biệt rõ route và không để thiếu cert lọt qua protected endpoints. |
| `none` | Không yêu cầu client certificate. | API không dùng mTLS inbound. |

**`client-auth: need` thường áp dụng ở cấp TLS connector/listener**, không chỉ một controller. Nếu cùng listener có public endpoints không yêu cầu mTLS, cần thiết kế listener/gateway riêng hoặc cơ chế routing được kiểm soát; không giả định Spring Security path matcher có thể yêu cầu TLS handshake certificate sau khi handshake đã hoàn tất.

### 8.2. Trust store của server khác trust store phía client

- Client trust store: client tin server certificate của API.
- Server trust store: API tin CA phát hành client certificate.

Hai phía có thể dùng CA khác nhau. Không đưa toàn bộ public internet CA bundle vào trust store client certificate nếu chỉ một nhóm CA/PKI nội bộ được phép gọi API.

### 8.3. Tách listener public và mTLS

Một deployment có thể có:

~~~text
Public HTTPS listener :443
  - endpoints công khai
  - Bearer token theo policy riêng

mTLS listener :8443
  - yêu cầu client certificate
  - certificate-bound Access Token
  - chỉ nhận từ network/client đã đăng ký
~~~

Việc tách listener giúp giảm nhầm lẫn giữa routes cần mTLS và routes không cần. Nhưng mọi đường truy cập tới protected resource phải được kiểm soát; không để cùng endpoint certificate-bound vô tình được mở qua public listener mà bỏ qua binding check.

## 9. Đối chiếu token với certificate trong ứng dụng Spring Security

Spring Security có thể xác thực JWT Access Token hoặc introspect opaque token. Tuy nhiên, **chỉ bật JWT/opaque Resource Server không tự bảo đảm token-to-TLS-certificate thumbprint binding ở mọi cấu hình**. Ứng dụng cần một integration thực thi việc đối chiếu certificate của kết nối với `cnf.x5t#S256`.

### 9.1. X509 authentication không tự thay certificate-bound token validation

Spring Security có cơ chế `x509()` để xác thực client certificate và có thể ánh xạ subject/certificate identity thành principal. Đây là **một cơ chế authentication bằng certificate**. Nó không tự đồng nghĩa với việc:

~~~text
verified Access Token.cnf.x5t#S256
             ==
thumbprint(TLS peer certificate)
~~~

Nếu endpoint yêu cầu **OAuth Access Token được bind với certificate**, phải thực hiện so sánh này một cách tường minh. Không dùng CN mapping làm thay thế cho `x5t#S256`.

### 9.2. Lấy peer certificate từ Servlet request

Khi TLS client authentication được xử lý trực tiếp bởi Servlet container, peer certificate chain thường có thể được lấy từ request attribute theo Servlet API:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.security.cert.X509Certificate;

public final class PeerCertificateExtractor {

    private static final String CERT_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    private PeerCertificateExtractor() {
    }

    public static X509Certificate requireLeaf(
            HttpServletRequest request) {
        Object value = request.getAttribute(CERT_ATTRIBUTE);

        if (!(value instanceof X509Certificate[] chain)
                || chain.length == 0
                || chain[0] == null) {
            throw new IllegalArgumentException(
                "A verified TLS client certificate is required");
        }

        return chain[0];
    }
}
~~~

Trong Servlet API, attribute chuẩn thường chứa mảng X.509 peer certificates của TLS connection, leaf certificate đứng đầu. Kiểm tra đúng behavior của **container/connector** đang triển khai; nếu TLS kết thúc ở proxy thì ứng dụng có thể không thấy certificate gốc của client trong request attribute.

**Không thay extractor này bằng cách đọc một header tùy ý do client gửi**, ví dụ `X-Client-Cert`, nếu proxy chưa xác thực và xóa header đầu vào. Phần proxy được giải thích ở mục 13.

### 9.3. So sánh thumbprint bằng Java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import org.springframework.security.authentication.BadCredentialsException;

public final class CertificateBindingVerifier {

    private CertificateBindingVerifier() {
    }

    public static void verify(
            String expectedX5tS256,
            X509Certificate peerCertificate) {

        if (expectedX5tS256 == null
                || expectedX5tS256.isBlank()
                || peerCertificate == null) {
            throw new BadCredentialsException(
                "Certificate-bound token requirements are missing");
        }

        String actual =
            CertificateThumbprints.x5tS256(peerCertificate);

        boolean matches = MessageDigest.isEqual(
            expectedX5tS256.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII));

        if (!matches) {
            throw new BadCredentialsException(
                "Access token is not bound to this TLS certificate");
        }
    }
}
~~~

`MessageDigest.isEqual` giúp so sánh byte arrays theo cách phù hợp cho giá trị nhạy cảm hơn so với phép so sánh string thông thường; tuy nhiên toàn bộ implementation vẫn cần được review theo security requirements. Giá trị expected phải đến từ **Access Token đã xác minh** hoặc introspection response đã được xác thực.

## 10. Tích hợp với JwtAuthenticationProvider bằng AuthenticationManagerResolver

Một điểm kỹ thuật quan trọng: `OAuth2TokenValidator<Jwt>` thường được gọi trong quá trình decode token và **không nhận HttpServletRequest/peer certificate trực tiếp**. Vì thế không thể đơn giản viết validator cần certificate rồi kỳ vọng Spring tự truyền TLS request vào.

Một cách tích hợp minh họa cho Servlet là:

1. Dùng `JwtDecoder` để xác minh Access Token chuẩn.
2. Dùng `JwtAuthenticationProvider` để tạo Authentication.
3. Bọc AuthenticationManager theo từng HttpServletRequest.
4. Sau khi token được xác minh, đọc `cnf.x5t#S256` từ Jwt đã xác thực.
5. Lấy peer certificate từ request attribute của TLS connection.
6. So sánh thumbprint trước khi trả Authentication về cho Spring Security.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.security.cert.X509Certificate;
import java.util.Map;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.jwt.JwtDecoder;

public final class MtlsBoundAuthenticationManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private final AuthenticationManager delegate;

    public MtlsBoundAuthenticationManagerResolver(
            JwtDecoder jwtDecoder) {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(jwtDecoder);
        this.delegate = provider::authenticate;
    }

    @Override
    public AuthenticationManager resolve(
            HttpServletRequest request) {

        // Certificate phải đến từ TLS stack tin cậy.
        X509Certificate peer =
            PeerCertificateExtractor.requireLeaf(request);

        return authentication -> {
            Authentication result =
                delegate.authenticate(authentication);

            if (!(result instanceof JwtAuthenticationToken jwtAuth)) {
                throw new BadCredentialsException(
                    "Expected JWT bearer authentication");
            }

            Map<String, Object> cnf =
                jwtAuth.getToken().getClaimAsMap("cnf");

            Object rawThumbprint = cnf == null
                ? null : cnf.get("x5t#S256");

            if (!(rawThumbprint instanceof String expected)) {
                throw new BadCredentialsException(
                    "Certificate confirmation claim is missing");
            }

            CertificateBindingVerifier.verify(expected, peer);
            return result;
        };
    }
}
~~~

Đây là **mẫu integration**, không phải một cấu hình production đầy đủ. Cần bổ sung:

- JwtDecoder đã kiểm tra issuer, audience, expiration, not-before và allowed algorithms.
- TLS listener thật sự yêu cầu/verify client certificate.
- Error handling/challenge phù hợp.
- Các loại token không certificate-bound phải có policy riêng; endpoint yêu cầu mTLS-bound không được chấp nhận token thiếu `cnf`.
- Test request qua đúng TLS connector/container.
- Nếu dùng nhiều issuer/tenant, resolver phải chọn decoder từ trusted configuration; không lấy JWKS URI từ token chưa xác thực.

### 10.1. Gắn resolver vào SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MtlsApiSecurityConfiguration {

    @Bean
    SecurityFilterChain mtlsApiChain(
            HttpSecurity http,
            MtlsBoundAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .securityMatcher("/mtls-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/mtls-api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

Trong ví dụ, `AuthenticationManagerResolver` giữ reference tới request để đọc peer certificate khi Authentication được thực hiện. Hãy kiểm tra filter ordering và container lifecycle của ứng dụng cụ thể. Với các phiên bản/framework integration khác, có thể chọn một authentication provider/filter chuyên biệt; yêu cầu không đổi: **binding check phải hoàn thành trước khi Authentication được sử dụng để authorize endpoint**.

### 10.2. Audience/issuer validator vẫn phải có

Resolver phía trên chỉ minh họa certificate binding; nó không tự tạo toàn bộ JWT trust policy. Một decoder cần cấu hình issuer và audience, ví dụ khái niệm:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(
        "https://identity.example.test")
        .build();

// Gắn validators:
// - issuer chính xác
// - audience chứa orders-api
// - exp/nbf theo clock policy
// - thuật toán ký được allowlist
~~~

Không đưa token vào binding verifier trước khi decoder xác minh chữ ký và claims. Không tin `cnf` từ một JWT chỉ mới base64-decode payload.

## 11. Tích hợp với OpaqueTokenIntrospector

Nếu Access Token opaque, dùng introspection để lấy principal:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

Có thể xây một wrapper quanh `OpaqueTokenIntrospector` hoặc một `AuthenticationManager` chuyên biệt:

1. Introspect token qua HTTPS với client credentials của Resource Server.
2. Chỉ tiếp tục nếu `active` là boolean `true`.
3. Lấy `cnf.x5t#S256` từ principal attributes đã được introspector tin cậy trả về.
4. Đối chiếu với peer certificate của request.
5. Nếu thiếu binding hoặc mismatch, từ chối Authentication.
6. Sau đó mới áp scope và domain authorization.

Không dùng raw opaque token làm certificate thumbprint, và không tự decode opaque token để tìm `cnf`. Nếu AS không trả `cnf`, contract tích hợp chưa đủ cho certificate-bound enforcement.

### 11.1. Không biến lỗi introspection thành Bearer fallback

Một token được AS cấp với certificate binding mà RS không thể đọc binding phải bị từ chối trên endpoint yêu cầu mTLS-bound token. Không nên:

~~~text
Introspection không có cnf
   -> bỏ qua binding
   -> chấp nhận như Bearer token
~~~

Đó là **hạ cấp sender constraint** và có thể làm mất mục tiêu bảo vệ ban đầu.

## 12. mTLS client authentication và certificate-bound token khác nhau ở đâu?

Hai flow thường dùng chung certificate nhưng cần hiểu rõ:

### 12.1. Client authentication tại Authorization Server

Client dùng certificate trong TLS handshake tới **token endpoint**. AS xác thực client theo certificate và mapping client registration.

~~~text
Client -- mTLS certificate --> Authorization Server
                              |
                              +-- nhận dạng OAuth client
~~~

### 12.2. Certificate binding ở Resource Server

Client dùng certificate để kết nối tới **Resource Server**. RS đối chiếu thumbprint với token đã phát hành.

~~~text
Client -- mTLS certificate + Access Token --> Resource Server
                                             |
                                             +-- verify cnf.x5t#S256
~~~

### 12.3. Bảng phân biệt

| Tình huống | AS token endpoint | Resource Server |
| --- | --- | --- |
| mTLS client authentication | Certificate xác thực OAuth client. | Không tự chứng minh token bound. |
| Certificate-bound Access Token | AS ghi thumbprint vào token khi phát hành. | So thumbprint của TLS peer certificate với token. |
| Cả hai cùng bật | AS có thể dùng cert để authenticate và bind token. | RS vẫn phải xác minh binding. |
| Chỉ có cert ở AS | Client chứng minh với AS. | Nếu RS không nhận cert, không thể đối chiếu token binding. |
| Chỉ có cert ở RS | RS có thể kiểm tra certificate. | Nhưng token phải được AS phát hành với binding phù hợp. |

**mTLS ở một chặng mạng không tự lan sang chặng khác.** Certificate ở kết nối client→AS không tự xuất hiện trong kết nối client→RS, và ngược lại.

## 13. TLS termination ở reverse proxy hoặc API gateway

Một triển khai phổ biến:

~~~text
Client -- mTLS --> Gateway -- HTTP/internal TLS --> Spring Resource Server
~~~

Gateway nhận và xác minh client certificate, nhưng TLS connection tới Spring có thể được tạo bởi **gateway**, không phải client. Khi đó Spring thấy certificate của gateway hoặc không thấy peer certificate nào.

Nếu ứng dụng lấy certificate từ TLS connection nội bộ rồi so với token, nó có thể đang so **gateway certificate**, không phải client certificate gốc. Kết quả sẽ sai hoặc tạo một trust gap.

### 13.1. Ba lựa chọn kiến trúc

**Lựa chọn A — End-to-end mTLS tới ứng dụng:** gateway passthrough TLS hoặc kiến trúc bảo toàn peer certificate tới Resource Server. Spring nhận được certificate client gốc từ TLS stack.

**Lựa chọn B — Gateway xác minh và truyền identity certificate qua kênh nội bộ tin cậy:** gateway xác thực mTLS client, sau đó gửi certificate identity/representation đã xác minh tới ứng dụng qua header chuẩn hoặc giao thức nội bộ được bảo vệ. Ứng dụng chỉ tin thông tin này từ gateway được xác thực; gateway phải xóa mọi header trùng tên do client gửi.

**Lựa chọn C — Gateway tự thực thi token binding:** gateway xác minh token và certificate binding đầy đủ trước khi chuyển request. Backend chỉ tin gateway theo một security contract rõ, không tự giả định đã kiểm tra nếu chưa có bằng chứng.

### 13.2. Header forwarding không được tin trực tiếp

Không làm:

~~~http
X-Client-Certificate: -----BEGIN CERTIFICATE-----
...
~~~

nếu client có thể tự gửi header này tới ứng dụng. Attacker có thể tự khai certificate bất kỳ.

Nếu sử dụng certificate forwarding:

- Dùng cơ chế chuẩn/định dạng đã thống nhất, ví dụ **RFC 9440 — Client-Cert HTTP Header Field** khi phù hợp.
- Gateway phải xóa header do client cung cấp trước khi tạo header forwarding của mình.
- Kết nối gateway→application cần được bảo vệ, thường bằng mTLS và network policy.
- Application chỉ chấp nhận forwarding header từ gateway/identity proxy đã được xác thực.
- Gateway phải xác minh certificate chain và possession trước khi khẳng định certificate đó là peer certificate.
- Giới hạn kích thước, encoding và parse certificate an toàn.
- Không để public network gọi trực tiếp backend và giả header nội bộ.

**Forwarded certificate là một assertion của proxy**, không còn là peer certificate mà Spring TLS stack trực tiếp nhận từ client. Phải bảo vệ integrity của assertion và danh tính proxy.

### 13.3. Forwarded headers khác X.509 peer certificate

Spring Boot/Tomcat có thể xử lý `Forwarded`/`X-Forwarded-*` để tái dựng URL, nhưng điều đó không có nghĩa container tự xác minh một certificate được gửi qua header. URL forwarding và **client certificate forwarding** là hai cơ chế khác nhau; đừng bật trust cho mọi forwarded header chỉ để giải quyết mTLS.

## 14. Certificate rotation và token lifecycle

Giả sử token T1 được bind với certificate C1:

~~~text
T1.cnf.x5t#S256 = thumbprint(C1)
~~~

Client đổi certificate sang C2:

~~~text
thumbprint(C2) != thumbprint(C1)
~~~

T1 **không tự động chuyển sang bind C2**. Nếu client gửi T1 trên TLS connection dùng C2, Resource Server phải từ chối.

### 14.1. Rotation có overlap

Một quy trình:

1. Tạo C2 và lưu private key mới an toàn.
2. Đăng ký/được AS chấp nhận C2 theo client registration policy.
3. Lấy Access Token T2 có `cnf.x5t#S256 = thumbprint(C2)`.
4. Trong thời gian chuyển đổi, client có thể giữ C1/T1 nếu policy cho phép và C1 chưa bị revoke.
5. Chuyển traffic sang C2/T2.
6. Revoke T1/credential C1 hoặc chờ hết lifecycle theo policy.
7. Xác nhận mọi service/replica không còn chấp nhận token bind với C1 nếu C1 bị compromise.

Không cấp token mới gắn C2 rồi dùng nó qua TLS connection vẫn trình C1.

### 14.2. Certificate hết hạn hoặc bị revoke

TLS certificate validation cần kiểm tra validity và revocation theo chính sách. Token có thể còn `exp` sau khi certificate hết hạn; nhưng handshake mới phải từ chối certificate không hợp lệ. Cũng nên revoke Access Token gắn với certificate bị compromise ở AS để các kiểm tra khác phản ánh đúng trạng thái.

### 14.3. Connection pooling và HTTP/2

Certificate được trình khi thiết lập TLS connection. Client connection pool cần được phân vùng theo **certificate identity/key material**:

- Không dùng một connection đã bắt tay bằng C1 để giả định nó đang trình C2.
- Khi rotate certificate, tạo kết nối TLS mới dùng C2.
- HTTP/2 có thể multiplex nhiều requests trên một connection; các streams dùng cùng TLS peer certificate của connection đó.
- Nếu nhiều tenants/service identities dùng các certificate khác nhau, không chia sẻ pool/connection tùy tiện.

Việc đổi file certificate trên disk không thay certificate đã được dùng trong một TLS connection đang mở.

## 15. TLS session resumption và certificate identity

TLS session resumption có thể tái sử dụng trạng thái phiên để giảm chi phí handshake. Resource Server phải dựa vào **TLS stack đã xác thực peer identity của connection hiện tại**, kể cả khi có resumption; không tự giả định một request không có certificate attribute vì handshake mới không gửi full chain là client không có identity.

Khi cấu hình TLS termination/proxy hoặc session resumption:

- Kiểm tra container có expose peer certificate đúng cho resumed session không.
- Đảm bảo session ticket/cache không vượt chính sách certificate rotation/revocation.
- Khi certificate bị compromise, có thể cần invalidate TLS sessions/tickets và đóng connection cũ.
- Đối chiếu token binding trên **certificate identity thực tế của connection**, không dùng một certificate được lưu trong session application không còn liên quan.

Chi tiết phụ thuộc TLS version, provider, server connector và cách vận hành session tickets; cần kiểm thử trên đúng stack production.

## 16. DPoP khác mTLS-bound token thế nào?

Hai cơ chế đều ràng buộc token với khóa client nhưng thực thi khác tầng:

| Tiêu chí | DPoP | mTLS-bound token |
| --- | --- | --- |
| Bằng chứng possession | Client ký DPoP proof JWT. | TLS client authentication bằng certificate/private key. |
| Public key binding | `cnf.jkt` là JWK thumbprint. | `cnf.x5t#S256` là certificate thumbprint. |
| Request proof | Mỗi request có header `DPoP`. | Proof possession diễn ra trong TLS handshake/connection. |
| Access Token header | Scheme `DPoP`. | Thông thường `Bearer`. |
| Thành phần kiểm tra | Application/proof verifier và replay cache. | TLS stack/proxy + token binding verifier. |
| Hạ tầng | Không bắt buộc client certificate. | Cần client cert PKI/trust configuration ở RS hoặc proxy. |
| Phù hợp | Public clients, browser/native app khi khó dùng client cert. | Service-to-service, enterprise PKI, workload identity. |

DPoP proof thường bind method/URI và Access Token hash cho từng request. mTLS-bound token dựa vào certificate đã xác thực của TLS connection; nó không ký HTTP body hay từng method/URI như DPoP.

## 17. TLS certificate identity không tự là user identity

Certificate có thể đại diện:

- Một OAuth client/service.
- Một workload hoặc thiết bị.
- Một ứng dụng cài đặt.
- Một tổ chức theo PKI policy.

Nó không tự chứng minh **người dùng cuối** là ai. Nếu một service dùng mTLS-bound Access Token cho nhiều user, token vẫn cần subject/claims và domain policy tương ứng.

### 17.1. Subject và SAN

Có thể có policy bổ sung:

~~~text
certificate SAN URI = spiffe://example.test/ns/orders/sa/worker
token client_id      = orders-worker
token aud            = orders-api
token cnf.x5t#S256   = thumbprint(certificate)
~~~

Những giá trị SAN/URI/subject có thể giúp map workload identity nếu PKI contract quy định. Nhưng binding RFC 8705 vẫn dựa trên **certificate thumbprint**, không thay bằng so sánh một chuỗi CN.

### 17.2. Scope và tenant authorization vẫn cần

Một certificate hợp lệ của service-orders cùng token bind đúng có thể được phép gọi API nhưng vẫn không được truy cập mọi tenant:

~~~text
TLS certificate valid
  AND Access Token valid
  AND certificate thumbprint matches cnf
  AND aud = orders-api
  AND scope = orders.read
  AND workload belongs to tenant alpha
  AND order belongs to alpha
~~~

Thiếu một điều kiện cần thiết thì từ chối. **mTLS-bound token không thay BOLA/tenant ownership checks.**

## 18. Những lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ bật mTLS nhưng không đọc `cnf`. | Client cert nào được trust cũng có thể dùng token không bind. | So sánh thumbprint của TLS peer cert với token. |
| Chỉ kiểm tra `cnf.x5t#S256` nhưng không yêu cầu mTLS. | Client có thể gửi public cert copy mà không chứng minh private-key possession. | TLS client authentication bắt buộc. |
| So sánh CN/SAN thay thumbprint. | Hai certificates khác nhau có thể cùng tên. | RFC 8705 certificate thumbprint. |
| Hash PEM text thay DER bytes. | Thumbprint không khớp. | SHA-256 của `certificate.getEncoded()`. |
| Hash public key/SPKI thay certificate. | Sai thuật toán binding. | Hash DER-encoded X.509 certificate leaf. |
| Dùng CA certificate thay leaf client cert. | Binding không đại diện certificate kết nối. | Dùng peer leaf certificate. |
| Không xác minh certificate chain/EKU/validity. | Certificate tự ký hoặc không đúng mục đích có thể được nhận. | TLS truststore/client-auth policy. |
| Dùng `x509()` như thể nó tự kiểm tra cnf. | X.509 principal được xác thực nhưng token binding chưa được so. | Custom token-certificate binding check. |
| AS dùng mTLS nhưng RS không có client cert. | Binding không được thực thi ở resource. | mTLS tại RS hoặc trusted gateway assertion. |
| Tin `X-Client-Cert` do client gửi. | Header spoofing, giả peer certificate. | Strip header; chỉ tin proxy đã xác thực. |
| Proxy terminate TLS nhưng app hash cert của proxy. | So sánh sai certificate identity. | Forward original client cert qua trusted channel hoặc end-to-end mTLS. |
| Token T1 bound C1 nhưng client đổi sang C2. | Thumbprint mismatch. | Xin token mới bind C2. |
| Không kiểm tra CRL/OCSP theo policy. | Certificate revoked có thể vẫn được dùng tùy TLS stack. | Thiết lập certificate revocation checking. |
| Chia sẻ HTTP connection pool giữa nhiều cert. | Request đi qua connection có peer cert khác dự kiến. | Pool/connection tách theo certificate identity. |
| Cho token bound đi qua Bearer listener không mTLS. | Bypass sender constraint. | Chặn mọi route/listener không thực thi binding. |
| Chỉ test certificate đúng. | Không phát hiện mismatch/missing cert/proxy bypass. | Negative tests và integration TLS thực. |

## 19. Kiểm thử certificate-bound Access Token

Kiểm thử cần chạy qua **TLS handshake thật** hoặc một test proxy có hành vi xác thực certificate được kiểm soát. Mock request header đơn thuần không chứng minh client đã sở hữu private key.

### 19.1. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token bind C1, TLS connection trình C1 hợp lệ | Qua certificate binding, tiếp tục authorization. |
| Token bind C1, TLS connection trình C2 | **Từ chối**. |
| Token bind C1, không có client cert | TLS handshake bị từ chối nếu listener yêu cầu mTLS. |
| Certificate chain không được trust | TLS handshake thất bại. |
| Certificate hết hạn | TLS handshake thất bại theo validation. |
| Certificate bị revoke theo policy | Bị từ chối qua CRL/OCSP hoặc cơ chế revocation được cấu hình. |
| Token không có `cnf` trên endpoint bắt buộc mTLS-bound | Từ chối, không fallback Bearer. |
| `cnf.x5t#S256` sai format/không khớp | Từ chối. |
| Token chữ ký sai/expired/wrong issuer | Từ chối dù cert đúng. |
| Token audience sai | Từ chối. |
| Token đúng cert nhưng thiếu scope | 403 theo authorization. |
| Client gửi header giả certificate | Không tin header từ public client. |
| Proxy forward cert đã xác minh | Chỉ chấp nhận khi proxy/channel nằm trong trust boundary. |
| Client rotate C1 → C2 nhưng vẫn dùng T1 | Từ chối; T1 vẫn bind C1. |
| Token mới T2 bind C2, connection dùng C2 | Qua binding. |
| HTTP/2 connection dùng C1 gửi token T2 bind C2 | Từ chối. |
| Listener public không yêu cầu mTLS gọi endpoint protected | Phải bị chặn bởi route/architecture policy. |

### 19.2. Unit test cho thumbprint

Có thể kiểm tra helper với test certificate fixture:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import java.security.cert.X509Certificate;

class CertificateThumbprintsTest {

    @Test
    void sameDerCertificateHasStableThumbprint() {
        X509Certificate cert = loadTestCertificate();

        String first =
            CertificateThumbprints.x5tS256(cert);
        String second =
            CertificateThumbprints.x5tS256(cert);

        assertEquals(first, second);
    }

    private X509Certificate loadTestCertificate() {
        // Load certificate fixture đã tạo riêng cho test.
        // Không dùng certificate/private key production.
        throw new UnsupportedOperationException(
            "Provide a test certificate fixture");
    }
}
~~~

Phần `loadTestCertificate` là fixture hook cần được triển khai bằng test resource riêng. Đây chỉ là ví dụ cách test tính ổn định của thumbprint, không phải test mTLS handshake.

### 19.3. Integration test qua TLS

1. Tạo test CA, client certificate C1/C2 và server certificate.
2. Cấu hình Resource Server test listener trust test CA và yêu cầu client certificate.
3. Phát hành JWT test có `cnf.x5t#S256` tính từ C1.
4. Dùng HTTP client keystore chứa C1 để gọi endpoint; kiểm tra authentication có thể qua.
5. Gọi cùng token bằng connection/keystore C2; phải bị từ chối.
6. Gọi không có client certificate; TLS handshake phải fail khi listener dùng `client-auth: need`.
7. Gửi token thiếu `cnf`; endpoint certificate-bound phải từ chối.
8. Gửi token sai issuer/audience/scope để xác minh các validators khác vẫn hoạt động.
9. Nếu có proxy, chạy lại qua proxy và thử giả mạo forwarded certificate header.
10. Kiểm tra certificate rotation, connection pool và certificate revocation policy.

Không thể dùng `MockMvc` thuần để chứng minh TLS client certificate handshake đã được xác minh bởi container. MockMvc có thể hữu ích cho phần security logic sau khi inject một certificate fixture, nhưng cần **separate end-to-end TLS test** để xác minh transport boundary.

## 20. Vận hành và observability

Các chỉ số hữu ích:

- TLS handshake success/failure theo nhóm nguyên nhân.
- Client certificate chain/validity/revocation failures.
- Token validation failures (issuer/audience/expiration/signature).
- Certificate thumbprint binding mismatch.
- Missing `cnf` trên endpoint yêu cầu certificate-bound token.
- Client certificate rotation/expiry sắp tới.
- Proxy forwarded-certificate validation failures.
- Requests bị từ chối vì token/certificate mismatch.

Không log private key, raw Access Token, Authorization header hoặc toàn bộ certificate chain không cần thiết. Certificate là public material nhưng có thể chứa thông tin nhận dạng nhạy cảm; chỉ ghi fingerprint/serial/issuer metadata theo chính sách và quyền truy cập phù hợp.

### 20.1. Certificate expiry monitoring

Theo dõi `notAfter` để chủ động rotate trước khi client mất khả năng mở TLS connection. Alert nên đủ sớm để client:

- Đăng ký certificate mới.
- Xin Access Token bind với thumbprint mới.
- Cập nhật connection pools.
- Xác nhận token cũ được revoke/hết hạn theo policy.

### 20.2. Trust store updates

Khi thêm/bỏ CA:

- Rollout truststore có kiểm soát.
- Theo dõi các clients bị ảnh hưởng.
- Không đưa CA rộng hơn cần thiết.
- Xác nhận mọi replicas có trust configuration đồng nhất.
- Có kế hoạch xử lý connection/session đã mở trước thay đổi trust.

### 20.3. Fail closed khi không lấy được peer certificate

Nếu endpoint yêu cầu mTLS-bound token nhưng app không đọc được certificate:

- Không fallback sang so CN từ token.
- Không tin header certificate từ client.
- Không bỏ qua binding vì “gateway đã có thể xác minh”.
- Kiểm tra proxy contract hoặc từ chối request.

**Không thể xác minh binding thì không được coi token đã thỏa sender constraint.**

## 21. Lộ trình triển khai

1. **Chọn client certificate PKI:** CA, issuance, identity mapping, key protection, expiry và revocation.
2. **Thống nhất RFC 8705 với Authorization Server:** mTLS client authentication, certificate-bound token issuance và `cnf.x5t#S256`.
3. **Xác định token format:** JWT có thể đọc claim sau signature validation; opaque token phải introspect được `cnf`.
4. **Thiết lập mTLS tại Resource Server:** truststore, client-auth policy, listener/route boundaries.
5. **Đọc đúng peer certificate:** trực tiếp từ TLS stack hoặc từ trusted proxy assertion có integrity.
6. **Tính thumbprint chuẩn:** SHA-256 trên DER certificate leaf, Base64url không padding.
7. **Tích hợp Spring Security:** token validation + certificate binding trước khi authorize; không nhầm `x509()` với cnf comparison.
8. **Giữ validators khác:** issuer, audience, expiration, algorithm, scope, tenant/owner.
9. **Xử lý TLS termination:** end-to-end mTLS hoặc trusted forwarding theo cơ chế chuẩn; strip client-supplied headers.
10. **Thiết kế certificate rotation/revocation:** token cũ vẫn bind cert cũ; cấp token mới sau rotate.
11. **Kiểm thử TLS thật:** correct/wrong/missing/revoked certificate, token thiếu/mismatch cnf, proxy spoofing.
12. **Giám sát và runbook:** certificate expiry, truststore rollout, mismatch, handshake errors và emergency revoke.

**Ghi nhớ:** mTLS-bound Access Token là một **Access Token được ràng buộc với X.509 client certificate**. Authorization Server đặt `cnf.x5t#S256` bằng Base64url(SHA-256(DER certificate)); client trình đúng certificate trong TLS handshake tới Resource Server; Resource Server xác minh certificate ở tầng TLS, xác thực token và so sánh thumbprint. **mTLS client authentication ở token endpoint không tự chứng minh Resource Server đã kiểm tra binding**. Spring Security cần một integration thực thi đối chiếu trước authorization; TLS termination qua proxy phải bảo vệ identity certificate được forward. Certificate binding giảm rủi ro token bị đánh cắp đơn lẻ, nhưng vẫn cần TLS, certificate lifecycle, token validation, scope và domain authorization.

## Tài liệu tham khảo

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 9440 — Client-Cert HTTP Header Field](https://www.rfc-editor.org/rfc/rfc9440).
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html).
- [Spring Boot — SSL Configuration](https://docs.spring.io/spring-boot/reference/features/ssl.html).
