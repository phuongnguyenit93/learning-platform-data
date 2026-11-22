# Xác thực TLS không tự thay thế kiểm tra liên kết chứng chỉ với token

Trong OAuth 2.0 Mutual-TLS (mTLS), client và server có thể xác thực chứng chỉ của nhau khi thiết lập kết nối TLS. Điều này giúp Resource Server biết **peer của kết nối TLS đang dùng chứng chỉ nào** và chứng chỉ đó có được trust policy chấp nhận hay không. Tuy nhiên, chỉ xác thực TLS **chưa đủ để chứng minh access token đang gửi thuộc về chính chứng chỉ đó**.

Giả sử client A nhận một access token được Authorization Server ràng buộc với certificate A. Kẻ tấn công lấy cắp token nhưng không có private key của A có thể mở một kết nối mTLS khác bằng certificate B hợp lệ. Nếu Resource Server chỉ kiểm tra “kết nối TLS có client certificate hợp lệ”, nó có thể chấp nhận certificate B và vẫn sử dụng token của A. Để ngăn trường hợp này, Resource Server phải **so sánh chứng chỉ client trên kết nối với dấu vân tay chứng chỉ được ràng buộc trong token**.

RFC 8705 định nghĩa **certificate-bound access tokens**. Với JWT access token, Authorization Server có thể đưa confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-client-certificate"
  }
}
~~~

`cnf.x5t#S256` là SHA-256 thumbprint của chứng chỉ X.509 client, tính từ encoding DER và mã hóa Base64URL không padding. Khi nhận request, Resource Server cần xác minh:

1. TLS peer certificate được xác thực theo trust policy.
2. Access token được xác minh theo JWT hoặc introspection profile.
3. Token có confirmation claim phù hợp.
4. Thumbprint trong token **khớp chính xác** với leaf client certificate trên kết nối mang request.

**TLS xác thực kết nối; certificate binding xác minh token được dùng cùng đúng chứng chỉ đã ràng buộc.** Hai kiểm tra này bổ sung cho nhau.

## 1. TLS server authentication, mTLS client authentication và token binding

Ba khái niệm thường bị nhầm:

| Cơ chế | Ai chứng minh điều gì? | Có xác minh token được ràng buộc với chứng chỉ không? |
| --- | --- | --- |
| TLS thông thường (one-way TLS) | Client xác minh server certificate; server chứng minh danh tính server với client | Không. Thông thường server không nhận client certificate |
| mTLS | Client và server xác thực chứng chỉ của peer trong TLS handshake | Chưa đủ. Chỉ chứng minh peer có chứng chỉ hợp lệ theo TLS policy |
| Certificate-bound access token | Resource Server so sánh client certificate của kết nối với confirmation thumbprint trong token | **Có**, nếu kiểm tra binding được thực thi đúng |

### TLS thông thường

Trong HTTPS thông thường, server trình bày server certificate để client xác minh hostname, chain, thời hạn và trust anchor. Client thường **không trình bày certificate**.

~~~text
Browser / API client                  Resource Server
       |                                    |
       | -------- TLS ClientHello --------> |
       | <------- Server Certificate ------ |
       | -- kiểm tra server identity ------ |
       |                                    |
       | ===== TLS application data =====> |
~~~

Server certificate trong sơ đồ là **chứng chỉ của server**, không phải chứng chỉ của OAuth client. Không thể lấy server certificate rồi so với `cnf.x5t#S256` của client token.

### Mutual TLS

Trong mTLS, server yêu cầu client trình bày certificate. Client chứng minh quyền sở hữu private key tương ứng trong TLS handshake; server kiểm tra certificate chain và policy:

~~~text
OAuth client                         Resource Server
     |                                     |
     | -------- TLS ClientHello ---------> |
     | <------- Server Certificate ------- |
     | <------- CertificateRequest ------- |
     | -------- Client Certificate ------> |
     | -------- CertificateVerify -------> |
     |                                     |
     |       TLS handshake complete       |
     |                                     |
     | ===== HTTP request + Bearer T =====>|
~~~

mTLS cho biết peer của kết nối đã chứng minh quyền sở hữu private key của client certificate. Nhưng nếu request còn mang một Bearer token không liên quan đến certificate, Resource Server vẫn cần kiểm tra mối liên kết đó.

### Certificate-bound access token

Khi Authorization Server phát hành token ràng buộc chứng chỉ, nó ghi nhận thumbprint của certificate theo cơ chế phát hành đã thỏa thuận. Resource Server nhận token và chứng chỉ ở request-time, tính thumbprint rồi so sánh:

~~~mermaid
flowchart TD
    A["Client mở mTLS tới Resource Server"] --> B["TLS kiểm tra certificate chain và proof of possession"]
    B --> C["Client gửi Bearer access token T"]
    C --> D["Resource Server xác minh JWT hoặc introspect token"]
    D --> E["Đọc cnf.x5t#S256 từ token"]
    B --> F["Lấy leaf client certificate của TLS request"]
    E --> G["So sánh thumbprint"]
    F --> G
    G --> H{"Khớp và cả hai phía hợp lệ?"}
    H -- "Có" --> I["Tiếp tục authorization scope/role/object"]
    H -- "Không" --> J["Từ chối token/request"]
~~~

Nếu token và certificate không khớp, token không được chấp nhận trên kết nối đó dù certificate riêng lẻ có chain hợp lệ và token riêng lẻ có chữ ký hợp lệ.

## 2. RFC 8705: hai khả năng mTLS có liên quan nhưng khác mục đích

RFC 8705 mô tả hai khả năng quan trọng:

1. **OAuth 2.0 Mutual-TLS Client Authentication:** OAuth client xác thực với Authorization Server bằng client certificate khi gọi token endpoint hoặc endpoint OAuth được hỗ trợ.
2. **OAuth 2.0 Certificate-Bound Access Tokens:** access token được ràng buộc với client certificate, và Resource Server xác minh client certificate khi token được sử dụng.

Một hệ thống có thể bật một hoặc cả hai khả năng. **Không tự suy luận rằng bật mTLS client authentication ở token endpoint đồng nghĩa mọi access token đều đã certificate-bound.** Cần xác nhận Authorization Server thực sự phát confirmation claim và Resource Server thực sự kiểm tra nó.

### mTLS client authentication ở token endpoint

Client lấy token bằng một kết nối mTLS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

Trong TLS handshake, client trình bày certificate và chứng minh sở hữu private key. Authorization Server xác định client theo certificate mapping/registration đã cấu hình. Sau đó AS phát token theo policy.

Nếu AS được cấu hình phát **certificate-bound access token**, token có thể chứa:

~~~json
{
  "cnf": {
    "x5t#S256": "thumbprint-of-certificate-used-for-binding"
  }
}
~~~

### Resource Server kiểm tra binding ở request-time

Client phải tiếp tục dùng đúng certificate tương ứng khi gọi API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <certificate-bound-access-token>
~~~

Certificate không nằm trong HTTP Authorization header; nó được trao đổi ở **TLS handshake**. Resource Server lấy certificate peer từ TLS connection hoặc từ metadata được chuyển tiếp qua một proxy đáng tin cậy, rồi đối chiếu với `cnf`.

| Câu hỏi | mTLS client authentication | Certificate-bound access token |
| --- | --- | --- |
| Kiểm tra ở đâu? | Authorization Server khi OAuth client gọi endpoint | Resource Server khi nhận token |
| Bằng chứng | Client certificate và proof of possession trong TLS | Thumbprint trong token khớp client certificate của request |
| Đối tượng được xác thực | OAuth client tại AS | Token đang được sử dụng trên kết nối |
| Có cần cnf? | Không nhất thiết cho riêng client authentication | **Có confirmation binding theo profile** |
| Ngăn token bị đánh cắp dùng bằng certificate khác? | Không tự đủ | Có, nếu binding được kiểm tra |
| Có thay thế audience/scope validation? | Không | Không |

## 3. Thumbprint x5t#S256 được tính như thế nào?

Theo RFC 8705, giá trị `x5t#S256` là:

~~~text
BASE64URL-NOPAD(SHA-256(DER-ENCODED-CLIENT-CERTIFICATE))
~~~

Các bước:

1. Chọn **leaf client certificate** được trình bày trong TLS handshake, không phải root CA, intermediate CA hay server certificate.
2. Lấy encoding DER của certificate.
3. Tính SHA-256 trên toàn bộ DER bytes.
4. Mã hóa digest bằng Base64URL.
5. Bỏ padding `=`.
6. So sánh kết quả với giá trị `cnf["x5t#S256"]`.

Không hash PEM text có header/footer và newline. Không hash riêng public key, subject DN, serial number hoặc certificate chain. Những giá trị đó không phải công thức thumbprint của RFC 8705.

### Java helper

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
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(der);
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (CertificateEncodingException
                 | NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "Cannot calculate certificate thumbprint", exception);
        }
    }
}
~~~

SHA-256 phải có trong Java runtime. `X509Certificate.getEncoded()` trả encoding DER của certificate. Không thay bằng `getPublicKey().getEncoded()`, vì đó là encoding public key chứ không phải encoding certificate.

### So sánh an toàn

Không nên dùng phép so sánh chuỗi tùy tiện nếu có thể dùng constant-time comparison:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

static boolean sameThumbprint(String expected, String actual) {
    if (expected == null || actual == null) {
        return false;
    }
    return MessageDigest.isEqual(
        expected.getBytes(StandardCharsets.US_ASCII),
        actual.getBytes(StandardCharsets.US_ASCII));
}
~~~

Giá trị thumbprint Base64URL là chuỗi ASCII. Kiểm tra null/format và so sánh theo giá trị chính xác; không tự chuyển chữ hoa/thường hoặc bỏ ký tự để “làm cho khớp”.

## 4. Confirmation claim cnf trong JWT access token

Một JWT access token certificate-bound có thể có cấu trúc:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "client_id": "orders-worker",
  "scope": "orders.read orders.write",
  "iat": 1763164800,
  "exp": 1763168400,
  "cnf": {
    "x5t#S256": "a-valid-base64url-certificate-thumbprint"
  }
}
~~~

Đây là payload minh họa. Giá trị thumbprint cần được tính từ certificate thật đã ràng buộc bởi Authorization Server; chuỗi ví dụ không phải chứng chỉ hợp lệ.

Resource Server phải thực hiện hai nhóm kiểm tra.

**Token validation**

- Xác minh chữ ký JWT theo key/algorithm tin cậy.
- Kiểm tra issuer, audience, thời hạn và token profile.
- Xác định token có phải access token dành cho API hay không.
- Đọc confirmation claim từ token đã được xác minh.

**Certificate binding**

- Lấy client certificate của đúng TLS request.
- Xác định leaf certificate và bảo đảm TLS layer đã xác thực nó.
- Tính `x5t#S256` theo DER/SHA-256/Base64URL-no-padding.
- So sánh với `cnf.x5t#S256`.
- Từ chối nếu thiếu claim, thiếu certificate hoặc mismatch trên endpoint yêu cầu binding.

### Không đọc cnf trước khi xác minh token

Payload JWT chỉ là dữ liệu do người gửi cung cấp cho đến khi signature/issuer/profile được xác minh. Không được giải mã Base64URL rồi tin `cnf` hoặc scope trước bước xác thực. Nếu attacker tự tạo token có `cnf` khớp certificate của họ, token vẫn phải bị từ chối vì chữ ký/issuer không hợp lệ.

### Thiếu cnf có nghĩa gì?

Nếu endpoint yêu cầu **certificate-bound token**, token không có `cnf.x5t#S256` phải bị từ chối. Không tự fallback sang “Bearer token thông thường” cho cùng route nếu chính sách yêu cầu proof-of-possession.

Nếu API có cả endpoint Bearer-only và endpoint certificate-bound, phân vùng policy theo route/resource rõ ràng. Không để một token không ràng buộc gọi route cần binding chỉ vì nó có scope tương tự.

## 5. Opaque access token và introspection response

Certificate-bound token không bắt buộc phải là JWT. Một opaque token có thể được kiểm tra bằng introspection endpoint; response cần cung cấp confirmation data mà Resource Server có thể dùng.

Ví dụ response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1763168400,
  "cnf": {
    "x5t#S256": "a-valid-base64url-certificate-thumbprint"
  }
}
~~~

Flow:

~~~text
Bearer opaque token
       |
       v
Reactive/Servlet OpaqueTokenIntrospector
       |
       v
active == true?
       |
       v
principal attributes include cnf.x5t#S256?
       |
       v
compare with TLS peer certificate thumbprint
       |
       v
scope/audience/tenant/object authorization
~~~

**active: true không thay thế certificate binding.** Nếu API yêu cầu mTLS-bound tokens mà introspection response không có confirmation claim cần thiết, token không đạt contract của API.

Một số Authorization Server chỉ trả `cnf` cho client introspection được cấp quyền hoặc theo profile riêng. Hãy xác minh introspection client có thể nhận trường này và response thật đúng schema. Không suy ra certificate binding chỉ từ việc AS trả active=true.

## 6. TLS certificate validation và token binding là hai kiểm tra riêng

Một chứng chỉ client hợp lệ thường cần được kiểm tra ở TLS layer theo chính sách PKI:

- Certificate chain dẫn tới trust anchor được cấu hình.
- Thời hạn notBefore/notAfter.
- Key usage/extended key usage phù hợp với client authentication.
- Subject/SAN hoặc certificate identity mapping đúng client.
- Thuật toán/key size đáp ứng policy.
- Revocation qua OCSP/CRL nếu môi trường yêu cầu và TLS stack được cấu hình.
- Client chứng minh quyền sở hữu private key trong handshake.

Sau đó token binding còn phải kiểm tra:

- Token được cấp bởi issuer tin cậy.
- Token dành cho đúng resource/audience.
- `cnf.x5t#S256` tồn tại và hợp lệ.
- Thumbprint đúng bằng certificate client của **request hiện tại**.

| TLS peer certificate | Token | Kết quả binding |
| --- | --- | --- |
| Hợp lệ, thumbprint A | cnf chứa A | Binding khớp |
| Hợp lệ, thumbprint B | cnf chứa A | **Mismatch, từ chối** |
| Không có client certificate | cnf chứa A | **Không có proof, từ chối** |
| Certificate không được trust | cnf chứa thumbprint của nó | TLS handshake phải bị từ chối; binding không cứu được |
| Certificate A hợp lệ | Token không có cnf | Từ chối nếu endpoint yêu cầu certificate-bound token |
| Certificate A hợp lệ | JWT signature sai, cnf giả chứa A | Từ chối ở token validation |

Một client certificate được CA tin cậy không thể tự làm một access token bất kỳ trở thành hợp lệ.

## 7. Lấy client certificate ở Servlet và WebFlux

Resource Server chỉ có thể so sánh binding nếu lấy được **chứng chỉ của peer client cho request đó**. Cách lấy phụ thuộc server stack và nơi TLS kết thúc.

### Servlet container

Với TLS kết thúc trực tiếp tại Servlet container, Servlet API thường cung cấp certificate chain qua request attribute:

~~~java
import java.security.cert.X509Certificate;
import jakarta.servlet.http.HttpServletRequest;

X509Certificate[] certificates = (X509Certificate[])
    request.getAttribute("jakarta.servlet.request.X509Certificate");

if (certificates == null || certificates.length == 0) {
    // Không có client certificate trên kết nối này.
}

X509Certificate leafCertificate = certificates[0];
~~~

Trong ứng dụng Spring Boot 2/Spring Framework cũ dùng javax.servlet, tên attribute theo namespace Servlet tương ứng có thể khác. Hãy kiểm tra API/container version đang chạy, không hard-code một namespace cho mọi dự án.

Mảng certificate thường đặt leaf certificate trước, nhưng code cần dựa vào contract của container/connector và xác minh đúng certificate được dùng trong handshake. Không lấy certificate đầu tiên từ một header do client tự gửi.

### WebFlux

Với Spring WebFlux chạy trên server hỗ trợ TLS metadata, request có thể cung cấp `SslInfo`:

~~~java
import java.security.cert.X509Certificate;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.http.server.reactive.ServerHttpRequest;

X509Certificate[] peerCertificates(ServerHttpRequest request) {
    SslInfo sslInfo = request.getSslInfo();
    if (sslInfo == null) {
        return new X509Certificate[0];
    }
    X509Certificate[] certificates = sslInfo.getPeerCertificates();
    return certificates != null
        ? certificates
        : new X509Certificate[0];
}
~~~

Đoạn code minh họa cho WebFlux server có cung cấp peer certificate qua `SslInfo`. Hành vi cụ thể phụ thuộc Reactor Netty/servlet adapter, TLS connector và proxy topology. Nếu TLS đã kết thúc ở ingress, `getSslInfo()` có thể mô tả kết nối từ ingress tới ứng dụng, không phải kết nối ban đầu của client.

### Không dùng ThreadLocal để truyền certificate qua reactive flow

Trong WebFlux, không đặt certificate hoặc principal vào ThreadLocal rồi giả định request giữ nguyên thread. Dùng `ServerWebExchange`, Reactor Context và API request-scoped. Một publisher có thể đổi thread trong quá trình xử lý.

## 8. TLS termination ở reverse proxy: ranh giới tin cậy quan trọng

Trong production, TLS thường kết thúc tại load balancer, API gateway hoặc ingress:

~~~text
OAuth Client
   |
   | mTLS: client certificate A
   v
Ingress / API Gateway
   |
   | TLS mới tới application
   | backend peer certificate có thể là certificate của gateway
   v
Spring Resource Server
~~~

Nếu ingress kết thúc mTLS, Servlet container hoặc Reactor Netty phía sau thường chỉ nhìn thấy **certificate của ingress** trên kết nối upstream. So sánh thumbprint của ingress với `cnf` của client sẽ sai.

Ba cách kiến trúc thường gặp:

1. **TLS passthrough:** chuyển nguyên TLS session đến Resource Server để ứng dụng trực tiếp xác thực client certificate.
2. **Trusted certificate propagation:** ingress xác minh client certificate rồi chuyển thông tin certificate đã xác thực qua một kênh/header nội bộ được bảo vệ.
3. **Gateway thực hiện token binding:** gateway có đủ thông tin đã xác thực về client certificate và token, tự kiểm tra binding trước khi forward request; backend tin gateway theo trust contract riêng.

### Forwarded certificate header không tự đáng tin

Một số proxy có thể truyền certificate metadata, ví dụ XFCC hoặc header nội bộ theo cấu hình. Nếu dùng:

- Ingress phải **xóa header cùng tên do client gửi vào** trước khi ghi giá trị đã xác minh.
- Backend chỉ chấp nhận request từ proxy được tin cậy qua network policy/mTLS.
- Header phải có format/schema được thống nhất, bao gồm certificate chain/leaf identity cần thiết.
- Không dùng một giá trị DN text hoặc subject string thay cho certificate DER thumbprint nếu contract yêu cầu `x5t#S256`.
- Bảo đảm header không bị sửa bởi proxy khác hoặc service trung gian không tin cậy.
- Log không được chứa toàn bộ certificate/PII ngoài nhu cầu vận hành.

Nếu client có thể tự gửi `X-Client-Cert`, `X-SSL-CERT` hoặc header tương tự trực tiếp tới backend, attacker có thể giả mạo certificate identity. **Không lấy certificate binding từ header client-controlled.**

### Proxy-to-application mTLS khác client-to-proxy mTLS

Nếu gateway dùng mTLS với backend, backend xác thực **gateway**. Điều đó bảo vệ đường nội bộ nhưng không tự chứng minh gateway đã xác thực certificate của OAuth client đúng cách. Cần trust contract riêng cho forwarded identity và bảo vệ header.

## 9. Certificate binding không thay thế các kiểm tra JWT khác

Một token có `cnf` đúng vẫn cần mọi validator thông thường:

~~~text
Valid JWT signature
AND trusted issuer
AND correct audience
AND exp / nbf valid
AND accepted access-token profile
AND required scope/permissions
AND certificate thumbprint matches TLS peer
AND tenant/object policy passes
~~~

### Token có binding đúng nhưng audience sai

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

Nếu request tới Orders API mang certificate A, binding khớp nhưng token vẫn không dành cho `orders-api`. Resource Server phải từ chối ở audience validation.

### Token đúng scope nhưng certificate sai

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

Request dùng certificate B, dù B được CA tin cậy và token có `SCOPE_orders.read`, vẫn phải bị từ chối vì binding mismatch.

### Sau binding vẫn phải kiểm tra quyền đối tượng

Certificate-bound token chứng minh token được sử dụng cùng certificate đã ràng buộc. Nó không tự chứng minh caller được đọc mọi order. Service vẫn cần kiểm tra tenant, owner, membership, sharing, assignment và trạng thái nghiệp vụ.

## 10. Spring Security không tự suy ra token binding chỉ từ TLS

Bật HTTPS hoặc yêu cầu client certificate ở server connector không tự khiến Spring Security so sánh `cnf.x5t#S256` với peer certificate. Tương tự, bật `oauth2ResourceServer().jwt()` chỉ cấu hình xác minh JWT theo decoder/validators; không nên giả định nó tự thực hiện certificate binding nếu ứng dụng chưa cấu hình chức năng đó.

Spring Security cung cấp các cơ chế nền:

- OAuth2 Resource Server xác thực Bearer JWT hoặc opaque token.
- `JwtDecoder` và `OAuth2TokenValidator<Jwt>` kiểm tra chữ ký/claims của JWT.
- Opaque token introspector lấy principal/attributes từ AS.
- X.509 support có thể ánh xạ certificate peer thành Authentication trong các use case phù hợp.
- Filter/authorization manager có thể áp dụng policy theo request sau authentication.

**X.509 authentication và certificate-bound access token validation vẫn là hai nhiệm vụ.** X.509 filter có thể tạo Authentication từ certificate, nhưng không tự biết rằng Bearer token `cnf` phải khớp với certificate đó.

Một cách tổ chức dễ kiểm soát:

1. TLS connector hoặc trusted ingress xác thực client certificate.
2. Resource Server xác thực Bearer token.
3. Binding enforcement component lấy cả Authentication đã xác thực và client certificate của request.
4. Component so sánh `cnf.x5t#S256`.
5. Authorization rules tiếp tục kiểm tra scope/role và object policy.

API và class cụ thể khác nhau giữa Servlet và WebFlux, vì vậy không sao chép filter Servlet sang reactive chain.

## 11. Ví dụ enforcement trong Spring Security Servlet

Ví dụ dưới đây minh họa một **custom filter** cho các route yêu cầu certificate-bound JWT. Nó chạy sau `BearerTokenAuthenticationFilter`, khi JWT authentication đã được tạo. Trong ứng dụng thực, cần giới hạn filter vào đúng route và xử lý cả token type mà hệ thống chấp nhận.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CertificateBindingFilter extends OncePerRequestFilter {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        // Request chưa authenticated được entry point/authorization xử lý.
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            filterChain.doFilter(request, response);
            return;
        }

        Map<String, Object> confirmation =
            jwtAuth.getToken().getClaim("cnf");
        Object expectedValue = confirmation != null
            ? confirmation.get("x5t#S256")
            : null;

        X509Certificate[] certificates = (X509Certificate[])
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(expectedValue instanceof String expected)
                || certificates == null
                || certificates.length == 0
                || certificates[0] == null) {
            reject(response);
            return;
        }

        String actual = CertificateThumbprints.x5tS256(certificates[0]);
        boolean matches = MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII));

        if (!matches) {
            reject(response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private static void reject(HttpServletResponse response)
            throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer error=\"invalid_token\"");
    }
}
~~~

`CertificateThumbprints.x5tS256(...)` là helper ở phần trước. Filter trên minh họa JWT path; opaque token cần đọc `cnf` từ principal attributes theo implementation introspector và contract introspection.

### Gắn filter vào đúng chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain certificateBoundApi(
        HttpSecurity http,
        CertificateBindingFilter bindingFilter) throws Exception {
    return http
        .securityMatcher("/api/mtls/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_orders.read"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> { }))
        .addFilterAfter(
            bindingFilter, BearerTokenAuthenticationFilter.class)
        .build();
}
~~~

Đây là **mẫu cấu hình Servlet**, cần điều chỉnh theo phiên bản Spring Security và API của ứng dụng. Nếu `CertificateBindingFilter` được khai báo như servlet Filter bean, tránh để Spring Boot đăng ký nó hai lần: vừa trực tiếp với servlet container vừa trong SecurityFilterChain. Có thể cần cấu hình `FilterRegistrationBean` để tắt container registration và chỉ dùng vị trí Spring Security dự định.

### Những điều ví dụ cần được hoàn thiện trong production

- Matcher chỉ bao phủ endpoint yêu cầu certificate-bound token.
- TLS connector phải thực sự yêu cầu/kiểm tra client certificate, hoặc ứng dụng nhận metadata certificate từ ingress đáng tin cậy.
- Nếu không có JWT Authentication, chain vẫn phải từ chối route bảo vệ qua authorization; không để request anonymous đi qua filter rồi vào controller.
- Opaque token cần binding extractor tương ứng.
- Token thiếu `cnf` phải bị từ chối trên route này.
- Certificate chain validation, EKU, revocation và client identity mapping phải được cấu hình ở TLS/proxy layer.
- Filter phải xử lý lỗi tính thumbprint theo hướng fail closed; không để lỗi encoding tạo một nhánh bỏ qua.
- Test mismatch và missing certificate qua MockMvc.

Đoạn code không thay thế implementation hoàn chỉnh cho mọi connector/proxy. Nếu certificate được terminate tại gateway, servlet attribute có thể chứa certificate của gateway; phải dùng nguồn forwarded identity đã xác thực theo phần proxy.

## 12. WebFlux: thực thi binding trong reactive request

Với WebFlux, thông tin TLS của request có thể được lấy từ `ServerHttpRequest.getSslInfo()` khi server adapter cung cấp peer certificates. Việc so sánh phải nằm trong reactive request flow và nhận cả Authentication đã xác thực, ServerWebExchange của request hiện tại và certificate peer tương ứng.

Khung helper đọc certificate:

~~~java
import java.security.cert.X509Certificate;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.http.server.reactive.ServerHttpRequest;

X509Certificate[] peerCertificates(ServerHttpRequest request) {
    SslInfo sslInfo = request.getSslInfo();
    if (sslInfo == null) {
        return new X509Certificate[0];
    }
    X509Certificate[] certificates = sslInfo.getPeerCertificates();
    return certificates != null
        ? certificates
        : new X509Certificate[0];
}
~~~

Sau khi lấy principal, binding check có thể được tích hợp vào `ReactiveAuthorizationManager<AuthorizationContext>` hoặc một WebFilter được đặt đúng vị trí trong security flow. Pseudocode:

~~~java
Mono<AuthorizationDecision> authorize(
        Mono<Authentication> authentication,
        ServerWebExchange exchange) {

    return authentication
        .filter(JwtAuthenticationToken.class::isInstance)
        .cast(JwtAuthenticationToken.class)
        .map(jwtAuth -> {
            String expected = readX5tS256(jwtAuth.getToken());
            X509Certificate certificate =
                firstPeerCertificate(exchange.getRequest());

            boolean allowed = expected != null
                && certificate != null
                && sameThumbprint(
                    expected,
                    CertificateThumbprints.x5tS256(certificate));

            return new AuthorizationDecision(allowed);
        })
        .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

Đây là **pseudocode mô tả composition**, không phải một class hoàn chỉnh cho mọi phiên bản Spring Security. Chữ ký `ReactiveAuthorizationManager` và kiểu authorization result có thay đổi giữa các version; hãy đối chiếu API đang dùng. Một authorization denial thường biểu hiện 403; nếu contract cần coi binding mismatch là invalid Bearer token và trả 401, hãy thiết kế authentication failure handling tương ứng thay vì ngầm coi mọi authorization denial là `invalid_token`.

**Không dùng block() hoặc ThreadLocal** để lấy SecurityContext/certificate. Hãy compose Mono trong cùng subscriber flow.

## 13. TLS termination và forwarded certificate: cấu hình phải bảo vệ header

Khi dùng ingress/gateway, cần xác định rõ **ai là người xác thực client certificate** và **ai là người thực hiện thumbprint comparison**.

### TLS passthrough

~~~text
Client --mTLS--> Resource Server
                    |
                    +-- TLS connector thấy client peer cert
                    +-- Bearer authentication
                    +-- cnf thumbprint comparison
~~~

Đây là mô hình trực tiếp nhất cho ứng dụng cần peer certificate, nhưng có thể giảm khả năng gateway thực hiện routing/inspection TLS.

### Gateway terminate mTLS và forward certificate

~~~text
Client --mTLS--> Trusted Gateway --mTLS/private network--> Resource Server
                     |
                     +-- validate client certificate
                     +-- strip client-supplied cert headers
                     +-- inject verified certificate metadata
                                      |
                                      v
                           Binding verifier at backend
~~~

Ở mô hình này, backend phải có cách xác minh header đến từ đúng gateway. Các biện pháp thường cần:

- Backend chỉ nhận traffic từ gateway qua network policy.
- Gateway và backend dùng mTLS nội bộ hoặc kênh tương đương.
- Gateway xóa mọi header certificate do client gửi rồi ghi metadata đã xác minh.
- Backend chỉ tin proxy identities được cấu hình, không tin tất cả X-Forwarded-*.
- Format certificate/chain được xác định; nếu cần thumbprint, nên tính từ certificate DER tương ứng thay vì so sánh subject text.
- Có test giả mạo header gửi trực tiếp từ client và xác nhận backend từ chối.

Không bật một property “trust forwarded certificate” cho mọi request. Việc tin header là một quyết định trust boundary.

### Proxy-to-application mTLS khác client-to-proxy mTLS

Nếu gateway dùng mTLS với backend, backend xác thực **gateway**. Điều đó bảo vệ đường nội bộ nhưng không tự chứng minh gateway đã xác thực certificate của OAuth client đúng cách. Cần trust contract riêng cho forwarded identity và bảo vệ header.

## 14. Certificate binding không thay thế các kiểm tra JWT khác

Một token có `cnf` đúng vẫn cần mọi validator thông thường:

~~~text
Valid JWT signature
AND trusted issuer
AND correct audience
AND exp / nbf valid
AND accepted access-token profile
AND required scope/permissions
AND certificate thumbprint matches TLS peer
AND tenant/object policy passes
~~~

### Token có binding đúng nhưng audience sai

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

Nếu request tới Orders API mang certificate A, binding khớp nhưng token vẫn không dành cho `orders-api`. Resource Server phải từ chối ở audience validation.

### Token đúng scope nhưng certificate sai

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

Request dùng certificate B, dù B được CA tin cậy và token có `SCOPE_orders.read`, vẫn phải bị từ chối vì binding mismatch.

### Sau binding vẫn phải kiểm tra quyền đối tượng

Certificate-bound token chứng minh token được sử dụng cùng certificate đã ràng buộc. Nó không tự chứng minh caller được đọc mọi order. Service vẫn cần kiểm tra tenant, owner, membership, sharing, assignment và trạng thái nghiệp vụ.

## 15. Certificate renewal, rotation và token lifetime

Thumbprint được tính trên **toàn bộ certificate DER**. Vì vậy, khi certificate được gia hạn/cấp lại, thumbprint thường thay đổi ngay cả khi client tiếp tục dùng cùng public/private key pair, bởi serial, validity hoặc certificate encoding khác.

~~~text
Certificate A:
  thumbprint = THUMB-A
  Token T1: cnf.x5t#S256 = THUMB-A

Certificate B (renewed):
  thumbprint = THUMB-B

T1 + Certificate A -> binding khớp
T1 + Certificate B -> binding mismatch
Token T2 được cấp mới với Certificate B -> binding khớp
~~~

Kế hoạch rotation nên có:

1. Đăng ký/cho phép certificate mới tại Authorization Server theo client identity policy.
2. Xác nhận token endpoint phát token mới với thumbprint certificate mới.
3. Client chuyển sang certificate mới và token mới theo rollout đã định.
4. Giữ certificate cũ đủ lâu cho token cũ còn hợp lệ nếu policy cho phép overlap.
5. Hết overlap thì thu hồi certificate cũ và/hoặc token cũ.
6. Xác minh mọi Resource Server instance đã nhận trust/certificate configuration mới.

Không đổi certificate nhưng tiếp tục gửi token bound với thumbprint cũ. Không tự sửa claim `cnf` trong token; chỉ Authorization Server được phát hành token mới theo cơ chế tin cậy.

### Thu hồi certificate và thu hồi token là hai vòng đời

- **Certificate revocation:** PKI/CA/OCSP/CRL hoặc trust registry quyết định certificate có còn được chấp nhận không.
- **Access token revocation:** Authorization Server quyết định token có còn active không.
- **Binding comparison:** chứng minh token đang được sử dụng với đúng certificate được ràng buộc.

Một certificate chưa bị revoke nhưng token đã hết hạn vẫn phải bị từ chối. Một token còn hạn nhưng certificate bị revoke phải bị từ chối ở TLS/trust layer. Một token active nhưng certificate khác thumbprint phải bị từ chối ở binding layer.

## 16. Certificate binding bảo vệ điều gì và không bảo vệ điều gì?

### Chỉ có Bearer token

~~~text
Client A nhận token T
Attacker lấy T
Attacker gửi Authorization: Bearer T
Resource Server chỉ kiểm tra T hợp lệ
=> Attacker có thể dùng token đến khi hết hạn/revoke
~~~

### Token bound với certificate A

~~~text
Client A:
  private key A + certificate A
  token T: cnf = thumbprint(A)

Attacker lấy T nhưng chỉ có certificate B:
  TLS mTLS với B có thể thành công
  token T có cnf thumbprint(A)
  request certificate thumbprint(B)
  => mismatch, từ chối
~~~

### Điều cơ chế này không giải quyết

- Attacker lấy được **cả access token và private key** của client.
- Malware điều khiển client process có thể dùng key thông qua HSM/keystore nếu được cấp quyền.
- Gateway xác thực certificate sai hoặc chuyển tiếp metadata giả mạo.
- Resource Server không kiểm tra `cnf` hoặc so với nhầm proxy certificate.
- Issuer phát token với thumbprint sai hoặc token profile không được xác thực.
- Audience/scope/tenant/object authorization bị cấu hình lỏng.
- TLS private key bị lộ hoặc certificate authority bị compromise.
- Replay trong môi trường mà attacker vẫn có quyền dùng đúng key/certificate.

Certificate-bound token **giảm rủi ro token bị đánh cắp riêng lẻ**, không biến token thành vô hiệu với mọi kiểu compromise.

## 17. Certificate-bound token khác DPoP

Certificate-bound access tokens và **Demonstrating Proof of Possession (DPoP)** đều nhằm ràng buộc access token với khóa của client, nhưng proof và claim khác nhau.

| Nội dung | mTLS certificate-bound token | DPoP |
| --- | --- | --- |
| Bằng chứng | Client certificate trong TLS handshake | DPoP proof JWT được client ký cho request |
| Token confirmation | `cnf.x5t#S256` | `cnf.jkt` |
| Ràng buộc | Thumbprint của X.509 client certificate | Thumbprint của public JWK |
| Yêu cầu transport | TLS với client certificate/mTLS theo profile | DPoP proof gắn với HTTP request; vẫn dùng TLS |
| Chứng minh possession | TLS handshake chứng minh client có private key của certificate | Chữ ký proof JWT chứng minh có private key JWK |
| Kiểm tra request | So certificate trên connection với token | Kiểm tra proof JWT, method/URI/time/nonce và token binding |

Không lấy `cnf.jkt` so với certificate thumbprint. Không dùng `x5t#S256` để kiểm tra DPoP proof. Hai cơ chế có thể cùng hướng đến sender-constrained tokens nhưng **không thay thế nhau**.

## 18. Kiểm thử certificate binding

Test cần tách:

1. TLS client certificate có được chấp nhận ở handshake không?
2. JWT/introspection có xác minh token không?
3. `cnf.x5t#S256` có được đọc từ token đã xác minh không?
4. Thumbprint có được tính từ đúng leaf certificate không?
5. Binding mismatch có bị từ chối trước controller/business side effect không?
6. Proxy forwarded certificate có chống giả mạo không?

### Unit test cho thumbprint

Có thể dùng test certificate fixture được tạo riêng cho test. Tính expected thumbprint độc lập hoặc dùng fixture giá trị đã biết; kiểm tra:

- Cùng certificate DER cho cùng thumbprint.
- Certificate khác tạo thumbprint khác.
- Encoding Base64URL không padding.
- So sánh null/missing claim trả false.
- Không hash PEM text hoặc public key encoding.

Không dùng private key/certificate production trong test fixture.

### MockMvc test matrix

Với Servlet, test filter/chain có thể mock hoặc thiết lập request certificate attribute trong test harness:

| Token | Request certificate | Kỳ vọng |
| --- | --- | --- |
| JWT signature hợp lệ, cnf=A | A hợp lệ | Binding pass; tiếp tục authorization |
| JWT signature hợp lệ, cnf=A | B hợp lệ | 401 invalid_token theo binding policy |
| JWT signature hợp lệ, thiếu cnf | A hợp lệ | Từ chối route certificate-bound |
| JWT signature hợp lệ, cnf=A | Không có cert | Từ chối |
| JWT signature sai, payload cnf=A | A hợp lệ | Từ chối ở JWT validation |
| Token đúng binding, thiếu scope | A hợp lệ | Binding pass, authorization 403 |
| Token đúng binding, audience sai | A hợp lệ | Từ chối ở token validation |
| Token đúng binding, cert đã hết hạn/revoked | TLS/trust policy từ chối | Không tới business handler |
| Header certificate giả từ client | Không có trusted proxy identity | Không được coi header là certificate đã xác thực |

Một unit test tự set `jakarta.servlet.request.X509Certificate` **không chứng minh TLS handshake hoặc PKI validation**. Nó chỉ test phần so sánh binding. Cần integration test với server HTTPS/mTLS và certificate test CA để kiểm chứng connector.

### WebFlux test matrix

Với WebFlux, cần test `ServerHttpRequest.getSslInfo()` trên server/adapter có TLS support. `WebTestClient` bind trực tiếp vào controller có thể không có TLS peer certificate như runtime thật. Khi cần kiểm tra handshake, dùng HTTPS test server với client certificate và trust store test.

Test reactive binding cũng phải xác nhận:

- Authentication và certificate thuộc cùng request/subscriber.
- Không dùng certificate từ một request khác hoặc ThreadLocal stale.
- Mismatch tạo decision denied và controller không được gọi.
- Publisher không block()/subscribe() độc lập.
- Proxy mode chỉ tin certificate metadata từ gateway đã xác thực.

## 19. Cấu hình TLS client authentication theo môi trường

Spring Boot có thể cấu hình TLS server client-auth ở connector. Ví dụ khái niệm:

~~~yaml
server:
  ssl:
    enabled: true
    key-store: /run/secrets/server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_PASSWORD_FROM_SECRET_STORE
    trust-store: /run/secrets/client-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: CLIENT_TRUSTSTORE_PASSWORD_FROM_SECRET_STORE
    client-auth: need
~~~

Tên property và behavior cần đối chiếu Spring Boot version/container đang dùng. `client-auth: need` thường yêu cầu client certificate trên **connector đó**. Nếu connector cũng phục vụ public health hoặc route không yêu cầu mTLS, yêu cầu certificate toàn cục có thể khiến những request đó không kết nối được.

Các lựa chọn kiến trúc:

- Dedicated port/connector cho route mTLS-bound.
- Ingress/gateway terminate mTLS và chuyển certificate metadata qua trust channel.
- TLS connector cấu hình optional client certificate nếu stack hỗ trợ, rồi binding filter yêu cầu certificate ở route tương ứng.

Không giả định một HTTP path có thể thay đổi yêu cầu TLS handshake sau khi connection đã được thiết lập. TLS handshake xảy ra trước HTTP routing; vì vậy mTLS bắt buộc theo connector/connection, không đơn giản là một rule requestMatchers.

### Trust store và CA

Trust store phải chứa CA/intermediate phù hợp để xác minh client certificate. Không import certificate client bất kỳ thành trust anchor chỉ để test nhanh; điều đó có thể biến trust policy thành allowlist sai.

Tùy policy, cần kiểm tra CA chain/path building, Extended Key Usage `clientAuth`, Key Usage, certificate validity, revocation status/OCSP/CRL nếu được yêu cầu, subject/SAN hoặc certificate-to-client mapping, certificate renewal và CA rollover.

## 20. Ma trận kiểm chứng dev, staging và production

Certificate binding thường thất bại khi dev, staging và production có topology khác nhau. Cần bảng capability riêng:

| Hạng mục | Dev | Staging | Production |
| --- | --- | --- | --- |
| TLS termination point | App/local proxy | Ingress staging | Gateway/ingress production |
| Client certificate request | Optional/required theo test | Giống production càng sát càng tốt | Theo policy đã phê duyệt |
| Client CA trust | Test CA riêng | Staging CA | Production CA/PKI |
| Certificate profile | Key/cert test | Certificate gần production | CA, EKU, key size, renewal policy |
| Token cnf | Có thumbprint test | AS staging phát đúng cert binding | AS production contract |
| JWT/opaque mode | Đã xác nhận | Đã xác nhận | Đã xác nhận |
| Introspection exposes cnf | Đã test nếu opaque | Đã test | Đã test |
| Proxy forwarding | Header test chống spoof | Ingress config test | Trusted proxy chain/network policy |
| Thumbprint calculation | DER/SHA-256/Base64URL | Cross-implementation test | Versioned contract |
| Certificate rotation | Test A → B | Test overlap/rollout | Runbook/monitoring |
| Certificate revocation | Test CA fixture | Test propagation | OCSP/CRL/trust registry SLA |
| Token revocation | AS test | End-to-end | SLO/incident process |
| Failure response | Missing/mismatch | Missing/mismatch/proxy | Contract 401/5xx and alert |
| Private key storage | Local keystore/test HSM | Secret store/HSM | HSM/TPM/managed key service nếu yêu cầu |

Không để certificate test CA của dev được trust ở production. Không dùng chung client private key giữa các môi trường. Nếu production TLS kết thúc ở gateway, phải test chính xác certificate forwarding và header spoofing trong topology thật.

## 21. Những lỗi thường gặp

**“HTTPS đang hoạt động nên certificate binding đã được bảo vệ.”** HTTPS thường chỉ xác thực server. Client certificate cần mTLS, và token binding còn cần thumbprint comparison.

**“Bật mTLS là đủ.”** mTLS chứng minh peer có certificate/private key hợp lệ; token có thể thuộc certificate khác. Phải so `cnf.x5t#S256`.

**“Dùng server certificate để so cnf.”** Sai đối tượng. `cnf.x5t#S256` ở đây ràng buộc client certificate.

**“Chỉ so subject DN hoặc serial number.”** RFC 8705 sử dụng SHA-256 thumbprint của certificate DER. Subject/serial không thay công thức đó.

**“Hash PEM text.”** Sai byte input. Hash DER encoding của certificate.

**“Hash public key là tương đương.”** Không. Certificate thumbprint và public-key thumbprint là các giá trị khác nhau.

**“JWT có cnf nên không cần verify signature.”** Không. Claim chỉ đáng tin sau token validation.

**“Introspection trả active=true nên không cần so certificate.”** Không. Phải đọc và kiểm tra cnf nếu endpoint yêu cầu bound token.

**“Gateway forward X-Client-Cert là backend có thể tin.”** Không nếu header client gửi không bị strip và backend không xác thực gateway.

**“Bật client-auth need trên connector rồi chỉ route /api/mtls/** mới cần cert.”** TLS handshake diễn ra trước HTTP route; connector có thể yêu cầu certificate cho mọi request trên port đó.

**“Certificate renewal giữ nguyên thumbprint nếu public key không đổi.”** Không. Thumbprint tính trên toàn bộ certificate DER; certificate mới thường có thumbprint mới.

**“Token binding thay thế scope, audience và owner check.”** Không. Binding chỉ ràng buộc token với certificate; các kiểm tra còn lại vẫn cần.

**“X.509 authentication của Spring Security tự kiểm tra cnf.”** Không nên giả định. X.509 authentication và Bearer token binding là hai nhiệm vụ riêng.

## 22. Quy trình triển khai certificate-bound access token

1. **Chốt profile:** xác định RFC 8705, JWT hay opaque token, `cnf.x5t#S256` và API/resource audience.
2. **Cấu hình Authorization Server:** client registration, mTLS authentication nếu cần và phát hành certificate-bound access token.
3. **Lấy token test:** dùng certificate A; xác minh token/introspection trả đúng thumbprint A.
4. **Cấu hình TLS peer authentication:** trust CA, certificate chain, EKU, expiry và revocation theo policy.
5. **Xác định topology:** TLS passthrough hay trusted gateway termination; không nhầm proxy certificate với client certificate.
6. **Triển khai binding enforcement:** lấy leaf certificate của request, tính DER/SHA-256/Base64URL-no-padding và so với token confirmation.
7. **Fail closed:** thiếu certificate, thiếu cnf, mismatch, lỗi parsing hoặc không có trusted proxy metadata đều không được cấp quyền.
8. **Tiếp tục token validation:** signature/introspection, issuer, audience, time, token type và claim profile.
9. **Tiếp tục authorization:** scope, role, tenant, owner, sharing và trạng thái tài nguyên.
10. **Quản lý vòng đời:** certificate renewal/rotation, token lifetime, revoke, CA rollover và key storage.
11. **Kiểm thử:** thumbprint unit test, JWT/introspection test, TLS handshake test, mismatch, missing cert, proxy spoofing và certificate rotation.
12. **Theo dõi vận hành:** binding mismatch, missing peer cert, TLS handshake failures, unknown CA, cert expiry và token validation errors; không log access token/private key.
13. **Xác nhận từng môi trường:** dùng CA, client cert, token và topology riêng cho dev/staging/production.

**Điểm cần nhớ:** TLS/mTLS xác minh peer và bảo vệ kết nối, nhưng **không tự chứng minh Bearer access token thuộc về client certificate đang dùng**. Với certificate-bound access token theo RFC 8705, Resource Server phải xác minh token trước, lấy `cnf.x5t#S256`, lấy leaf client certificate đã được xác thực từ đúng TLS request, tính SHA-256 thumbprint trên DER rồi so sánh. Nếu certificate mismatch, thiếu certificate hoặc thiếu binding claim trên route yêu cầu mTLS-bound token, phải từ chối. Chỉ sau khi binding khớp mới tiếp tục scope, audience, tenant và object-level authorization.
