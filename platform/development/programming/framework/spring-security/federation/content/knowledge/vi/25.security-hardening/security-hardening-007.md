# Giới hạn kích thước SAMLResponse, XML và dữ liệu thuộc tính

> **Chủ đề:** Spring Security – federation. **Nhóm:** Gia cố an toàn. Bài Knowledge độc lập này trình bày cách thiết kế **giới hạn tài nguyên theo từng tầng** khi Spring Security làm SAML 2.0 Service Provider/Relying Party (SP/RP) và nhận `SAMLResponse` từ Identity Provider/Asserting Party (IdP/AP). Phạm vi trọng tâm là HTTP-POST Binding, Java 17+, Spring Boot Servlet, Spring Security SAML 2.0 và OpenSAML. Mọi mức dung lượng trong ví dụ là **ngân sách khởi điểm minh họa, không phải giới hạn mặc định hoặc con số bắt buộc từ SAML**: cần đo dữ liệu IdP thật, xác nhận với đối tác, thử nghiệm và lập chính sách theo tài nguyên.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt kích thước **HTTP request body**, giá trị form-urlencoded `SAMLResponse`, chuỗi Base64, **byte XML sau Base64 decode**, DOM/XML object tree và dữ liệu AttributeStatement sau khi xác minh.
2. Giải thích tại sao chặn request body lớn ở NGINX/Ingress **không** thay thế giới hạn sau decode, độ sâu XML, entity expansion và số lượng thuộc tính.
3. Xác định những tấn công liên quan: request flooding, memory/CPU exhaustion, XML parser DoS, XXE/SSRF, oversized signature/encrypted assertion, attribute-count explosion và log amplification.
4. Cấu hình giới hạn HTTP POST ở reverse proxy và embedded Tomcat/Spring Boot, đồng thời tránh nhầm các thiết lập multipart với POST binding SAML.
5. Đặt guard trước `Saml2WebSsoAuthenticationFilter` để kiểm **định dạng và ngân sách Base64/XML** mà không tự viết lại trình xác thực SAML.
6. Giữ nguyên các kiểm tra mật mã, issuer, audience, destination, recipient, thời gian, request correlation và replay của OpenSAML/Spring Security.
7. Áp **attribute budget sau khi xác minh chữ ký**: số tên thuộc tính, số giá trị, độ dài từng giá trị, tổng kích thước và allowlist những trường thật sự cần.
8. Hiểu tác động của `EncryptedAssertion`, nhiều `Assertion`, nhiều `AttributeValue`, group claims và dữ liệu người dùng lớn tới ngân sách.
9. Xử lý `413 Content Too Large`, `400 Bad Request`, lỗi chữ ký/issuer và lỗi nội bộ một cách nhất quán, không lộ SAMLResponse/raw XML trong log.
10. Chạy được ví dụ Java 17 thuần mô phỏng ngân sách trước parse và sau trust verification, có stdout chính xác.
11. Lập ma trận QA gồm ranh giới `limit-1`/`limit`/`limit+1`, chunked POST, malformed Base64, DOCTYPE/XXE, encrypted assertions, signature wrapping, group explosion và cluster.
12. Chọn cách nâng giới hạn có phê duyệt thay vì tắt kiểm soát hoặc tin nội dung do IdP/browser gửi chỉ vì request có `SAMLResponse`.

**Quy tắc vàng:** Không có một `maxSamlResponseSize` chung tự xử lý mọi rủi ro. Cần nhiều **giới hạn độc lập** và phải **từ chối cả request** khi vượt giới hạn; không truncate XML, bỏ bớt attributes hoặc cố xác minh một chữ ký trên dữ liệu đã bị thay đổi.

## 2. Mô hình luồng và vị trí phát sinh chi phí

Trong SAML 2.0 Web Browser SSO HTTP-POST:

```text
Browser               Edge Proxy / WAF          Spring/Tomcat                  OpenSAML
   |                         |                       |                           |
   | POST /login/saml2/sso/corp                    |                           |
   | Content-Type: application/x-www-form-urlencoded                           |
   | body=SAMLResponse=<Base64 XML>&RelayState=...                               |
   |------------------------>|                       |                           |
   |                [1] raw body limit               |                           |
   |                         |                       |                           |
   |                         | ---- HTTP POST -----> |                           |
   |                         |               [2] Tomcat form parsing             |
   |                         |               [3] SAMLResponse character limit    |
   |                         |               [4] Base64 decode byte limit        |
   |                         |                       |----- decoded XML --------->|
   |                         |                       |                      [5] secure XML parse
   |                         |                       |                      [6] signature / issuer
   |                         |                       |                          / audience / time
   |                         |                       |<----- verified principal--|
   |                         |               [7] attribute count/value budget    |
   |                         |               [8] local user + tenant mapping     |
   |                         |               [9] SecurityContext/session         |
   |<------------------------|<----------------------|                           |
```

Mô hình này có ít nhất **chín điểm** người vận hành có thể kiểm soát, nhưng không phải tất cả đều là cùng một API. Chẳng hạn:

- Reverse proxy có thể chặn request body trước JVM, giảm áp lực CPU/heap.
- Tomcat xử lý form POST theo quy tắc servlet; có giới hạn số byte dùng để parse form parameters và số lượng parameters.
- Spring Security `Saml2WebSsoAuthenticationFilter` trích xuất `SAMLResponse` bằng request parameter, xác định registration rồi chuyển cho authentication manager.
- OpenSAML tạo DOM/XML objects, xác minh chữ ký, xử lý encrypted assertions và các điều kiện SAML. Đây là các phép tính có chi phí cao và có thể cấp phát bộ nhớ nhiều lần lớn hơn byte input.
- Principal sau validation có thể chứa hàng nghìn group values; nếu copy vào HttpSession, Redis, audit logs hay business requests, bề mặt DoS chưa kết thúc ở parser.

**Nhầm lẫn cần tránh:** HTTP status 413 ở edge nói rằng **form body** quá lớn; nó không chứng minh XML có chữ ký sai. Lỗi signature của OpenSAML khác với lỗi ngân sách request. Những sự kiện này phải được đo riêng, không trả chi tiết secrets cho browser.

## 3. Bản chất dữ liệu: SAMLResponse không phải XML trực tiếp trong HTTP POST

Ví dụ minh họa SAML POST Binding:

```http
POST /login/saml2/sso/corp HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PHNhbWxwOlJlc3BvbnNlLi4u&RelayState=opaque
```

Giá trị `SAMLResponse` là **Base64 của XML SAML Response**, được truyền thành form parameter theo quy tắc URL encoding. XML thường có cấu trúc:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-id" Version="2.0"
    Destination="https://sp.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <!-- Signature, Status và Assertion chỉ là phần minh họa -->
  <saml:Assertion ID="_assertion-id">
    <saml:AttributeStatement>
      <saml:Attribute Name="groups">
        <saml:AttributeValue>team-finance</saml:AttributeValue>
        <saml:AttributeValue>team-operations</saml:AttributeValue>
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
```

Đây **không phải phản hồi SAML hợp lệ để đăng nhập**: ví dụ đã lược bỏ các điều kiện/chữ ký bắt buộc theo trust contract. Không được dùng XML tự viết này để qua xác minh chữ ký. Muốn test happy path, sử dụng IdP staging phát **SAML Response thật và được ký** với registration/ACS đúng.

### 3.1. Base64 và URL encoding làm kích thước tăng

Công thức Base64 chuẩn cho `n` byte đầu vào:

```text
base64Length = 4 * ceil(n / 3)

XML bytes    Base64 ASCII chars (xấp xỉ)
     3                   4
   300                 400
 30,000             40,000
300,000            400,000
450,000            600,000
```

HTTP form body còn có tên parameter `SAMLResponse=`, `RelayState`, encoding của ký tự đặc biệt Base64 như `+`, `/`, `=` và có thể các params khác. Vì vậy **HTTP body thường lớn hơn Base64 string**, nhưng độ chênh phụ thuộc URL encoding/partner/browser. Ngay cả Base64 không có padding một phần cũng phải tuân thủ cách parse được thư viện chấp nhận.

**Không so trực tiếp `SAMLResponse.length()` với số byte raw XML**. `String.length()` của Java đếm UTF-16 code units; Base64 thông thường toàn ASCII nên gần tương ứng số ký tự ASCII, nhưng AttributeValue XML có thể là UTF-8 đa byte. Đối với giá trị Unicode và giới hạn log/session, đo **UTF-8 bytes**, không chỉ số Java characters.

### 3.2. Không áp giải nén nhầm binding

- HTTP-POST Binding thường nhận **Base64-encoded XML**, không có bước “DEFLATE raw XML” tương tự HTTP-Redirect Binding cho SAML messages.
- HTTP-Redirect Binding thường áp dụng DEFLATE+Base64+URL encoding lên `SAMLRequest` hoặc `SAMLResponse` theo binding, có nguy cơ expansion riêng nếu hỗ trợ.
- HTTP Content-Encoding `gzip`/`br` ở lớp HTTP là chuyện khác, có thể bị proxy giải nén. Nếu sản phẩm không hỗ trợ request compression tại ACS, nên **từ chối không-identity Content-Encoding**, tránh compression bombs.
- `EncryptedAssertion` là mã hóa XML theo XML Encryption; khi được giải mã, XML có thể biến thành một subtree DOM/object lớn hơn ciphertext. Nó **không** đồng nghĩa HTTP compression. Cần kiểm cả trước/sau decrypt theo kiến trúc.

**Không tự triển khai inflate SAMLResponse HTTP-POST “để hỗ trợ thêm”** nếu không có thỏa thuận binding và kiểm dung lượng sau giải nén. Cách đó có thể biến một request nhỏ thành payload khổng lồ.

## 4. Threat model: tại sao kích thước lớn thành lỗi an ninh?

| Tấn công/lỗi | Đầu vào/đường xử lý | Hậu quả |
| --- | --- | --- |
| **HTTP body flood** | Hàng nghìn POST lớn tới ACS | Chiếm bandwidth, sockets, proxy buffers, temp files |
| **Chunked upload không có Content-Length** | Transfer-Encoding chunked hoặc request streaming | Bỏ qua các guard chỉ nhìn header Content-Length |
| **Form parameter flood** | Nhiều keys lạ/duplicate `SAMLResponse` | CPU parse/hash, memory, ambiguous input |
| **Base64 khổng lồ** | Một field `SAMLResponse` dài | Cấp phát String/byte arrays, GC pressure |
| **DOM/XML tree quá lớn** | XML hợp lệ nhưng nhiều nodes/attrs | Heap growth, parsing latency, OOM |
| **XML entity expansion** | DTD/internal entity chain | CPU/memory exponential; “Billion Laughs” |
| **XXE/external resource** | DOCTYPE, external DTD/entity/XInclude | SSRF, local-file disclosure, network calls |
| **XML Signature wrapping** | Nhiều assertions/IDs/reference ambiguity | Có thể lấy identity từ node không được ký nếu thư viện/config lỗi |
| **Signature verification DoS** | Nhiều signatures, transforms, references | Tăng CPU trước khi xác định message invalid |
| **Encrypted assertion overload** | Nhiều EncryptedAssertion/keys | CPU giải mã và tăng DOM/heap |
| **Attribute explosion** | `groups`/`memberOf` có hàng nghìn giá trị | Memory, session bloat, Redis/network amplification |
| **Long text/markup values** | AttributeValue vài MB, nhiều Unicode | Log/JSON/HTML rendering overhead, XSS nếu render sai |
| **Multi-tenant registration confusion** | IdP A phát payload to cho SP/tenant B | Resource exhaustion hoặc authorization misbinding |
| **Logout/metadata XML bỏ sót** | `SAMLRequest` ở SLO, metadata parser hoặc XML upload | Đường DoS ngoài ACS |
| **Observability amplification** | Log raw `SAMLResponse`, XML, attributes | Disk/cost/privacy incident |
| **Unbounded retries** | IdP phát đúng message nhưng RP từ chối, browser loop | Login storm, tăng tải chính hệ thống |

Một IdP đáng tin cũng có thể phát assertion quá lớn do AD group bùng nổ hoặc bug cấu hình. **Giới hạn tài nguyên vẫn cần áp cho đối tác tin cậy**; trust về chữ ký không phải giấy phép dùng vô hạn heap/CPU.

### 4.1. Mô hình khuếch đại

Giả sử raw form body 700 KiB:

```text
700 KiB HTTP body
  -> ~550 KiB Base64 string (rough estimate)
  -> ~410 KiB XML bytes
  -> DOM nodes + Java XML objects + signature/decrypt intermediates
  -> Java String/List/Map attributes in principal
  -> HttpSession / Spring Session Redis serialization
  -> logs/events/cache/JSON responses
```

Đây là **ví dụ định tính**. Không có hệ số “XML x10 RAM” bảo đảm cho mọi runtime; tăng bộ nhớ phụ thuộc XML shape, parser, OpenSAML, allocations, policy mapping và JVM heap. Cần đo heap allocation/GC và p95 parse time bằng payload hợp lệ có kích thước gần giới hạn.

## 5. Thiết kế ngân sách tài nguyên đa tầng

### 5.1. Một ví dụ ngân sách ban đầu cho 1 ứng dụng

| Vị trí | Ngân sách minh họa | Đơn vị thực | Vì sao |
| --- | --- | --- | --- |
| NGINX/Ingress `client_max_body_size` | **1 MiB** | HTTP request body bytes | Chặn trước JVM, kể cả upload/chunked |
| Tomcat `max-http-form-post-size` | **1 MiB** | Bytes form POST đưa vào parameter parsing | Không để container parse form quá lớn |
| Tomcat `max-parameter-count` | **16** | Số parameters GET+POST | Chặn parameter flooding/duplicates |
| App guard `MAX_BASE64_CHARS` | **650.000** | Base64 string characters | Hạn chế Base64 input trước decode |
| App guard `MAX_XML_BYTES` | **450.000** | Decoded XML byte[] length | Chặn XML quá lớn trước OpenSAML |
| XML parser `maxElementDepth` | **64** | Nesting depth | Chặn XML sâu bất thường |
| XML parser `entityExpansionLimit` | **100** hoặc DTD bị cấm | Count | Hạn chế entity amplification; ưu tiên cấm DTD |
| XML parser `totalEntitySizeLimit` | **10.000** hoặc DTD bị cấm | Chars/size theo parser | Backstop chống amplification |
| Post-verification `MAX_ATTRIBUTE_NAMES` | **32** | Tên Attribute hợp lệ | Giảm số fields chuyển vào principal/session |
| Post-verification `MAX_TOTAL_VALUES` | **128** | Tổng các values | Giảm group explosion |
| Post-verification `MAX_SINGLE_VALUE_BYTES` | **2.048** | UTF-8 bytes một value | Ngăn text khổng lồ |
| Post-verification `MAX_TOTAL_ATTRIBUTE_BYTES` | **32 KiB** | Tổng UTF-8 của names+values | Giới hạn session/cache/serialization |

**Đây là profile ví dụ**, không được tuyên bố đáp ứng mọi federation. Một đối tác có 150 group values hợp lệ sẽ bị từ chối bởi ví dụ trên; phải thỏa thuận group strategy, quyền nào thật sự cần và giới hạn theo registration. Có thể đặt nhiều profile dựa trên nhu cầu đã kiểm chứng, không dùng một giới hạn toàn cầu mà không đo.

Mối quan hệ được thiết kế có chủ ý:

```text
HTTP form body <= 1,048,576 bytes
Base64 chars  <=   650,000 chars
decoded XML   <=   450,000 bytes
attribute blob <=  32,768 UTF-8 bytes

4 * ceil(450,000 / 3) = 600,000 Base64 characters
=> Cho một ít headroom cho variation/malformed content,
   nhưng decoded XML vẫn có giới hạn riêng.
```

**Vì sao giới hạn Base64 650.000 lớn hơn 600.000?** Guard có thể phát hiện XML >450.000 sau decode dù encoded field chưa vượt chính ngưỡng string. Trong production có thể chọn trần encoded gần sát hợp đồng và bổ sung kiểm nguyên vẹn padding/format. Các giá trị không phải default Spring Security.

### 5.2. Quy tắc chọn ngưỡng dựa trên thực nghiệm

1. Thu thập thống kê **payload hợp lệ** theo IdP/tenant/test cohort, chỉ đo size/histogram, **không lưu raw assertions**.
2. Đo raw body bytes, Base64 chars, decoded XML bytes, XML element count/depth, attributes number/total bytes, CPU p95/p99/heap.
3. Tách các nguồn dữ liệu bất thường: nested groups, nhiều encrypted assertions, embedded certificate chains, custom attribute JSON dài.
4. Tính headroom cho biến động hợp lý, nhưng không dùng “max observed ×100” vô căn cứ.
5. Đàm phán IdP attribute release: chỉ gửi nhóm/role cần thiết, dùng stable opaque ID hoặc lookup backend có ACL khi group membership quá lớn.
6. Định nghĩa profile cho từng `RelyingPartyRegistration`/đối tác, quản trị thay đổi qua review và audit.
7. Đánh giá tác động tới accessibility/availability: một user legitimate có nhiều nhóm không nên vô tình bị khóa khỏi mọi công việc; cần luồng xử lý/ticket rõ ràng.
8. Kiểm thử các ngưỡng ±1 đơn vị **đúng tầng**. Một `MAX_XML_BYTES` test cần Base64 hợp lệ trong body hợp lệ để tránh bị chặn trước bởi proxy.
9. Quan sát saturation ở peak load, tránh chọn giới hạn chỉ dựa một máy dev có heap lớn.
10. Gắn policy version vào deployment/metrics để biết vì sao một đối tác vừa bắt đầu bị 413 sau thay đổi.

## 6. HTTP POST và Spring Security SAML 2.0: endpoint nào nhận dữ liệu?

Trong Spring Security Servlet, ACS endpoint theo cấu hình thường là:

```text
POST /login/saml2/sso/{registrationId}
POST /login/saml2/sso             (một số trường hợp lookup registration từ state/response)
```

Bên gửi gửi form `SAMLResponse`. `Saml2WebSsoAuthenticationFilter` sử dụng authentication converter để tạo `Saml2AuthenticationToken`, sau đó authentication provider dựa trên OpenSAML kiểm chữ ký và conditions rồi mới tạo `Saml2Authentication`.

- `/saml2/authenticate/{registrationId}` dùng tạo AuthnRequest; **không** phải ACS nhận Response.
- `/logout/saml2/sso` hoặc endpoint SLO cấu hình khác xử lý `SAMLRequest`/`SAMLResponse` của logout, cần guard riêng.
- `/saml2/metadata` tải/publish metadata; nếu ứng dụng còn **import metadata từ URL** thì phải xử lý XML/HTTP response size và SSRF riêng, không dùng ACS guard cho mọi metadata fetch.
- Nếu tùy biến `saml2Login(...loginProcessingUrl(...))` hoặc multi-tenant route, cập nhật đồng bộ ACS ở RelyingPartyRegistration, IdP metadata, WAF và filter guard. Không để ACS custom nằm ngoài tất cả giới hạn.

**Không dùng `web.ignoring()` để “bỏ qua security cho ACS”**. ACS phải được SAML authentication filter xử lý để kiểm signature/issuer/audience, không phải controller REST tự nhận XML.

## 7. NGINX/Ingress: chặn sớm HTTP body

Đây là **fragment cấu hình NGINX** cho RP có endpoint `/login/saml2/sso/{registrationId}`. TLS đã được tổ chức thiết lập; reverse proxy gửi tới backend HTTPS với xác minh server certificate.

```nginx
# Fragment trong server { listen 443 ssl; ... }
location ^~ /login/saml2/sso/ {
    # Ngân sách chung của form body tại ingress:
    client_max_body_size 1m;
    client_body_timeout 10s;
    proxy_request_buffering on;

    # HTTPS upstream với server identity verification:
    proxy_pass https://saml-backend.internal.example.org:8443;
    proxy_ssl_server_name on;
    proxy_ssl_name saml-backend.internal.example.org;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate
        /etc/nginx/trust/saml-backend-ca.pem;

    proxy_set_header Host sp.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host sp.example.org;

    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
}
```

**Lưu ý quan trọng:**

- `client_max_body_size 1m` kiểm kích thước **HTTP request body ở edge**; NGINX thường trả HTTP **413** khi body vượt hạn, trước khi gửi upstream.
- `proxy_request_buffering on` làm proxy đọc/buffer request trước khi gửi backend. Lựa chọn buffering có tác động temp files/disk và latency; cần capacity planning, timeouts, disk permissions. Nó **không** thay size limit.
- `client_body_timeout` là idle timeout giữa các lần đọc body, không phải total end-to-end deadline tuyệt đối; cần request rate/connection limits riêng để chống slow clients.
- `proxy_ssl_verify on` bảo vệ kết nối tới backend; không nằm trực tiếp trong SAML size policy nhưng cần giữ TLS trust khi truyền chứng cứ xác thực.
- `Host`/`X-Forwarded-Host` canonical ở proxy phải phù hợp ACS public URL. Edge phải strip `Forwarded` và mọi forwarded header do client chưa tin tự gửi trước khi thiết lập lại, tránh recipient/destination mismatch.
- Nếu dùng `/login/saml2/sso` **không có registrationId**, phải đặt policy tương ứng cho exact location đó, hoặc dùng một regex/location cấu hình đúng. Đừng để endpoint này nhận body không giới hạn chỉ vì match thiếu dấu `/`.
- Nếu có nhiều ingress/gateway (CDN → WAF → NGINX), cần kiểm size ở **đúng ingress thực tế** và đảm bảo limit không bị override bởi đường dự phòng/alternate host.
- NGINX `client_max_body_size 0` có thể tắt kiểm tra: **không** dùng để “sửa login lỗi” khi IdP phát quá nhiều groups.
- `nginx -t` kiểm syntax, **không** chứng minh HTTP 413/PKIX/route đúng. Cần test qua public host và theo dõi upstream bytes.

### 7.1. HTTP 413, chunked requests và body buffering

Đừng chỉ đọc `Content-Length` từ browser rồi tin rằng body sẽ nhỏ. Request có thể có no Content-Length, `Transfer-Encoding: chunked`, hoặc proxy đã chuẩn hóa/chuyển đổi framing. **NGINX có thể kiểm body đã đọc**, trong khi một Servlet Filter chỉ xem `getContentLengthLong()` có thể nhận `-1`.

Nếu phải xử lý request streaming trực tiếp ở app mà không có ingress bảo đảm, cần một **bounded-read body wrapper** thực sự đếm bytes trước mọi `getParameter*`/XML parse, tương thích Servlet container form parsing và request replay. Đây là việc tinh vi; không dùng một filter đọc `ServletInputStream` rồi vẫn gọi `getParameter("SAMLResponse")` mà không cache/replay hợp lệ: dữ liệu có thể đã bị tiêu thụ trước Spring Security.

### 7.2. Nếu IdP bị 413 sau tăng số nhóm

Quy trình sửa đúng:

1. Xác định tầng trả 413 (CDN, WAF, NGINX, Tomcat, app guard).
2. So kích thước payload hợp lệ bằng metrics đã redacted.
3. Xác định nhóm nào cần trong SAML; giảm/thu gọn attribute release nếu có thể.
4. Nếu cần tăng limit, điều chỉnh có chủ đích **các tầng liên quan** và kiểm memory/CPU/session/Redis.
5. Đặt test signed fixture đại diện đối tác và regression tests negative.
6. Không bypass size check riêng cho `?idp=trusted` do browser tự gửi; policy registration phải được xác minh.

## 8. Tomcat/Spring Boot: form limits khác multipart và upload

Với **Spring Boot 3.x/Spring Security 6.x chạy embedded Tomcat**, ví dụ trong `src/main/resources/application.yml`:

```yaml
server:
  tomcat:
    max-http-form-post-size: 1MB
    max-parameter-count: 16
    max-swallow-size: 2MB
  max-http-request-header-size: 8KB

spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:corp-idp-signing.crt"
```

**Cảnh báo mã cấu hình:** Các giá trị IdP/certificate chỉ là placeholder; đây là fragment của Spring Boot project, không phải cấu hình chạy thật nếu chưa có IdP staging và RelyingPartyRegistration/ACS đúng. Không đưa IdP signing certificate vào truststore TLS để thay việc verify XML Signature. Ngược lại, HTTPS cert IdP không mặc nhiên là XML signing key.

- `server.tomcat.max-http-form-post-size` giới hạn kích thước nội dung POST mà Tomcat parse thành parameters (`application/x-www-form-urlencoded`/phần multipart theo quy tắc container). **Không** phải giới hạn mọi HTTP request body của mọi content type.
- `server.tomcat.max-parameter-count` giới hạn số parameters trong query + POST; ngăn `SAMLResponse=...` lẫn hàng trăm fields rác gây parser CPU/memory.
- `max-swallow-size` giới hạn lượng request body mà Tomcat có thể bỏ qua sau một lỗi/abort để giữ kết nối. **Không** thay `max-http-form-post-size` hoặc kích thước raw body.
- `server.max-http-request-header-size` hạn chế request line/headers; **không** giới hạn Base64 trong POST body.
- `spring.servlet.multipart.max-file-size`, `max-request-size` dành cho multipart uploads **không** phải biện pháp chính cho SAML HTTP-POST Binding `application/x-www-form-urlencoded`.
- Jetty, Undertow và Boot 4/Security 7 có property semantics/version khác nhau; đối chiếu **docs của đúng embedded server và version**. Không sao chép `server.tomcat.*` vào Jetty rồi tin nó có hiệu lực.
- Tomcat có thể xử lý lỗi vượt `maxPostSize` khác nhau theo config/container; không đảm bảo mọi oversize đều trả đúng 413. Kiểm thực tế response/status và **không chấp nhận partial/empty form như một login hợp lệ**.
- Nếu có proxy HTTP/2 → HTTP/1.1 hoặc service mesh, mỗi layer có riêng framing/body limits. Cần policy hiệu lực trên **toàn bộ đường gọi thật**.

### 8.1. Thứ tự kiểm quan trọng

Một Servlet Filter kiểm `request.getParameter("SAMLResponse")` đã khiến container **parse form** trước khi filter đo độ dài value. Vì thế:

```text
Ingress raw-body limit
    -> Tomcat form/parameter limit
        -> Spring pre-SAML filter checks Base64/XML bytes
            -> OpenSAML secure parse, signature and assertions
                -> post-verification attribute budget
                    -> local user mapping + session persistence
```

**Không tuyên bố Java filter bên dưới ngăn mọi memory allocation ở container.** Nó là **lớp bảo vệ bổ sung trước OpenSAML**, còn giới hạn ngoài JVM và container mới chặn sớm hơn.

## 9. Spring Security guard: từ chối Base64/XML quá lớn trước OpenSAML

### 9.1. Scope và quy tắc của filter

Chỉ áp cho **POST ACS** đã cấu hình; những đường như SAML SLO phải có budget riêng. Guard:

- Kiểm method, URL, Content-Type, Content-Encoding và query policy.
- Ưu tiên kiểm `getContentLengthLong()` nếu biết; **không** coi đây là chốt bảo vệ chunked.
- Đọc `getParameterValues("SAMLResponse")` qua Tomcat đã đặt giới hạn form; bắt buộc đúng **một** giá trị.
- Kiểm số parameters; Base64 char count trước decode.
- Base64 decode bằng `java.util.Base64.getDecoder()`, từ chối invalid data; đo số byte XML sau decode và không giữ byte[] trong session/log.
- **Không parse XML ở đây** để tránh double-parser/differential behavior. Spring/OpenSAML làm parse và validation tiếp.
- Với request vượt budget, chặn **toàn bộ request**, không cắt chuỗi rồi cho provider dùng XML thiếu dữ liệu.
- Không in `SAMLResponse` hoặc XML trong log/error response.

### 9.2. Java filter trong ứng dụng Spring Boot

File `src/main/java/com/example/saml/SamlAcsSizeGuard.java`:

```java
package com.example.saml;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class SamlAcsSizeGuard extends OncePerRequestFilter {

    private static final long MAX_FORM_BYTES = 1_048_576L;
    private static final int MAX_BASE64_CHARS = 650_000;
    private static final int MAX_XML_BYTES = 450_000;
    private static final int MAX_FORM_PARAMS = 8;
    private static final int MAX_RELAY_BYTES = 256;

    private static boolean isAcs(String path) {
        return "/login/saml2/sso".equals(path)
            || path.startsWith("/login/saml2/sso/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Servlet path thường bỏ context path.
        String path = request.getServletPath();
        if (!isAcs(path) || !"POST".equals(request.getMethod())) {
            chain.doFilter(request, response);
            return;
        }

        // Chính sách lab: ACS không có query string.
        // Nếu ACS của đối tác cần query tĩnh đã đăng ký,
        // hãy thiết kế matcher riêng, không bỏ hẳn kiểm tra.
        if (request.getQueryString() != null) {
            response.sendError(400, "Unexpected ACS query string");
            return;
        }

        String contentType = request.getContentType();
        if (contentType == null ||
            !contentType.toLowerCase(Locale.ROOT)
                .startsWith("application/x-www-form-urlencoded")) {
            response.sendError(415, "Unsupported SAML POST content type");
            return;
        }

        String encoding = request.getHeader("Content-Encoding");
        if (encoding != null &&
            !"identity".equalsIgnoreCase(encoding)) {
            response.sendError(415, "Compressed request not supported");
            return;
        }

        // Chỉ chặn sớm được khi biết length. Chunked/-1:
        // bắt buộc phải có ingress/container byte limit.
        long bodyBytes = request.getContentLengthLong();
        if (bodyBytes > MAX_FORM_BYTES) {
            response.sendError(413, "SAML request body too large");
            return;
        }

        // Việc gọi getParameter* KÍCH HOẠT form parsing:
        // Tomcat max-http-form-post-size phải được cấu hình.
        String[] values = request.getParameterValues("SAMLResponse");
        if (values == null || values.length != 1 ||
            values[0] == null || values[0].isEmpty()) {
            response.sendError(400, "Exactly one SAMLResponse required");
            return;
        }

        if (request.getParameterMap().size() > MAX_FORM_PARAMS) {
            response.sendError(400, "Too many SAML form parameters");
            return;
        }

        String samlBase64 = values[0];
        if (samlBase64.length() > MAX_BASE64_CHARS) {
            response.sendError(413, "SAMLResponse base64 too large");
            return;
        }

        String relayState = request.getParameter("RelayState");
        if (relayState != null &&
            relayState.getBytes(StandardCharsets.UTF_8).length >
                MAX_RELAY_BYTES) {
            response.sendError(413, "RelayState too large");
            return;
        }

        final byte[] xml;
        try {
            xml = Base64.getDecoder().decode(samlBase64);
        }
        catch (IllegalArgumentException ex) {
            response.sendError(400, "Malformed SAMLResponse base64");
            return;
        }

        if (xml.length == 0) {
            response.sendError(400, "Empty SAMLResponse");
            return;
        }

        if (xml.length > MAX_XML_BYTES) {
            response.sendError(413, "Decoded SAML XML too large");
            return;
        }

        // KHÔNG gọi DocumentBuilder.parse(xml) ở đây.
        // KHÔNG thay đổi request parameters hay XML đã ký.
        // Spring Security/OpenSAML tiếp tục validation.
        chain.doFilter(request, response);
    }
}
```

**Mức tin cậy của ví dụ:**

- Class trên dùng Jakarta Servlet + Spring Web `OncePerRequestFilter` trong project Spring Boot. Nó **không** phải chương trình `javac` độc lập; cần dependencies Spring.
- Filter kiểm **độ dài và Base64 syntax**, không bảo đảm nội dung là XML hợp lệ, issuer đúng hoặc chữ ký hợp lệ. Bất kỳ Base64 hợp lệ nào nhỏ hơn limit vẫn có thể bị OpenSAML từ chối.
- `startsWith("application/x-www-form-urlencoded")` là một kiểm tra định dạng thực dụng, nhưng nên dùng parser Content-Type chặt chẽ và charset contract của ứng dụng nếu có yêu cầu cao; không chấp nhận content type không phù hợp.
- Một proxy có thể đã giải nén Content-Encoding trước JVM; bản sample giả định policy edge từ chối compressed ACS request và không tự decompress.
- Ngưỡng `MAX_RELAY_BYTES=256` là **chính sách minh họa**. HTTP-POST/Redirect SAML Bindings có những ràng buộc riêng cho RelayState theo profile; phải chọn đúng interoperability contract. RelayState phải được liên kết transaction/session đáng tin, không chỉ kiểm độ dài.
- `getParameterMap()` có thể đã được Tomcat parse trước khi Java đếm. Không dùng `getParameter*` thay raw-body limit.
- Các giá trị error string là mã lỗi chung, **không** echo người dùng hay Base64/NameID. App có thể có `ErrorController`/standard response handler để nhất quán UX/logging.
- Cần bổ sung ingress rate limiting, connection limits và timeouts; filter này không tự giải quyết distributed flood hoặc request-body slowloris.
- Đảm bảo filter chạy **trước Spring SAML converter**. Nếu app đổi `loginProcessingUrl`, đồng bộ chính xác route ở filter này.

### 9.3. Gắn filter vào đúng SecurityFilterChain

File `src/main/java/com/example/saml/SamlSecurityConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2WebSsoAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        // Filter chỉ tạo trong chain; tránh @Bean Filter bên ngoài
        // khiến Boot tự đăng ký thêm global Servlet Filter.
        http.addFilterBefore(
            new SamlAcsSizeGuard(),
            Saml2WebSsoAuthenticationFilter.class);

        return http.build();
    }
}
```

**Phạm vi config:** Spring Security 6.x/Boot 3.x, Java 17+, Servlet. Phải có `spring-security-saml2-service-provider` và `RelyingPartyRegistration`/IdP signing certificates phù hợp. Với Spring Security 7.x, đối chiếu Javadoc/migration, đặc biệt kiểu principal/response authentication converter và các callback; đừng trộn mã của hai major versions trong cùng ví dụ.

**Bắt buộc kiểm order:** Một ứng dụng có thể khai báo nhiều `SecurityFilterChain`. Guard phải nằm **trong chain nhận ACS request**, không chỉ trong chain của business API. Test bằng request POST giả vào ACS và xác nhận guard trả 413 khi vượt giới hạn, **trước** khi OpenSAML parse.

### 9.4. Ưu điểm và phần chưa giải quyết của filter

| Lớp | Guard này có bảo vệ? | Còn cần gì? |
| --- | --- | --- |
| Raw HTTP body lớn | **Một phần**, khi Content-Length biết | Ingress byte limit thực, chunked/streaming |
| Container parameter parsing | **Không trước parse** | Tomcat max form size/parameter count |
| Base64 cực dài | **Có**, sau form parse | Connection/rate controls |
| Decoded XML bytes lớn | **Có** | Secure parser/decrypt complexity budgets |
| XXE/DTD/entity expansion | **Không** | OpenSAML/JAXP parser hardening |
| XML signature wrapping | **Không** | Secure OpenSAML validators and signed-node binding |
| EncryptedAssertion expansion | **Không sau decrypt** | Library-specific node/complexity budgets |
| Nhiều SAML AttributeValues | **Không** | Post-validation attribute limits/allowlist |
| Cached role/tenant grant | **Không** | Authoritative authorization |
| SAML replay/InResponseTo | **Không** | SAML authentication provider + request correlation |
| Total server CPU under flood | **Không** | WAF/rate/concurrency/timeouts, sizing |

**Không coi guard là một “SAML parser” hoặc “SAML validator” thay thế.** Nên viết test chứng minh sau khi guard cho qua, OpenSAML vẫn từ chối message unsigned, issuer lạ, audience sai, expired assertion và subject recipient không đúng.

## 10. XML hardening: DOCTYPE, entity expansion, parser limits

### 10.1. Tại sao giới hạn byte XML là chưa đủ?

XML chỉ vài kilobytes nhưng chứa DTD/entity có thể nở thành dữ liệu rất lớn khi parser expand, hoặc tham chiếu external resources. XML có độ sâu hàng nghìn phần tử cũng làm parser/DOM đệ quy, cấp phát nhiều object và tăng CPU.

Các lớp bảo vệ:

- **Không cho DTD/DOCTYPE** trên untrusted SAML Response khi không có nhu cầu.
- **Không cho external general/parameter entities và external DTD**; chặn fetch local/network.
- Tắt **XInclude** trừ khi protocol thực sự cần, vì XInclude có thể fetch ngoài DTD.
- Bật JAXP `FEATURE_SECURE_PROCESSING` và deny external access qua `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA`.
- Đặt processing limits (depth, entity expansion, total entity size, XML name size, element attributes, số node) theo parser/JDK hỗ trợ.
- Không cho XML parser tự download schema/XSD từ URL trong message.
- Chỉ xác thực XML Signature qua thư viện được hỗ trợ, không parse tự do bằng DOM rồi chọn `getElementsByTagName("Assertion").item(0)`.
- **Fail startup/deployment** nếu security parser settings mà policy yêu cầu không được hỗ trợ, thay vì bắt exception rồi tiếp tục parse insecure.

### 10.2. Ví dụ JAXP parser cho XML do chính ứng dụng xử lý

Đoạn sau **chỉ minh họa hardening cho một parser riêng**, không phải lời khuyên thay OpenSAML's parser bằng custom DOM rồi reserialize signed SAML:

```java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public final class HardenedXmlReader {

    public static Document readBoundedXml(InputStream stream)
            throws Exception {

        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newDefaultInstance();

        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);

        // Không cho DOCTYPE và các tài nguyên XML ngoài.
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);

        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        factory.setAttribute("jdk.xml.maxElementDepth", "64");
        factory.setAttribute("jdk.xml.entityExpansionLimit", "100");
        factory.setAttribute("jdk.xml.totalEntitySizeLimit", "10000");

        DocumentBuilder builder = factory.newDocumentBuilder();

        // stream BẮT BUỘC đã bị giới hạn byte trước khi gọi.
        // Không parse URL/file name do user tự đưa vào.
        return builder.parse(stream);
    }
}
```

**Điều kiện áp dụng:**

- `DocumentBuilderFactory.newDefaultInstance()` có từ JDK 9, dùng parser mặc định của JDK. Với implementation khác, property/feature có thể khác.
- `FEATURE_SECURE_PROCESSING` **không tự chặn mọi external entity**; phải khóa external access và DOCTYPE/DTD.
- `"jdk.xml.maxElementDepth"` và các processing limits là JDK XML properties; giá trị hỗ trợ và defaults khác theo JDK/vendor. Test trên đúng Java runtime.
- Đây không phải code để gọi trực tiếp trên `SAMLResponse` rồi lấy NameID. Dùng **OpenSAML/Spring Security** để parse và validate SAML theo giao thức. Nếu tự parse riêng để “đếm trước”, bạn vừa cấp phát DOM lần thứ hai vừa tạo nguy cơ **parser differential và signature wrapping**.
- Nếu ứng dụng thực sự cần kiểm XML tree shape, hãy dùng extension point được thư viện hỗ trợ, bảo đảm vẫn kiểm **đúng node đã được ký** và giới hạn trước các allocations lớn ở nơi có thể.
- Không tắt parser restrictions chỉ vì một IdP gửi DTD; SAML Web SSO thông thường không cần DTD. Nếu một đối tác đặc biệt yêu cầu XML constructs không phù hợp, phải review và thay đổi hợp đồng bảo mật.

### 10.3. Các thuộc tính JDK XML nên biết

| Property/feature | Giới hạn | Tầng áp dụng |
| --- | --- | --- |
| `XMLConstants.FEATURE_SECURE_PROCESSING` | Bật chế độ xử lý an toàn và một số limits | DOM/SAX/XPath/Transformer theo implementation |
| `XMLConstants.ACCESS_EXTERNAL_DTD` | Nguồn protocol được đọc cho DTD | XML parser/schema |
| `XMLConstants.ACCESS_EXTERNAL_SCHEMA` | Nguồn protocol được đọc cho XSD | SchemaFactory/Parser |
| `jdk.xml.entityExpansionLimit` | Tổng lần expand entities | JAXP parser |
| `jdk.xml.totalEntitySizeLimit` | Tổng kích thước expanded entities | JAXP parser |
| `jdk.xml.maxElementDepth` | Độ sâu XML tree | JAXP parser |
| `jdk.xml.maxXMLNameLimit` | Độ dài tên XML elements/attrs | JAXP parser |
| `jdk.xml.elementAttributeLimit` | Số XML **attributes** trên một element | JAXP parser |
| `jdk.xml.maxGeneralEntitySizeLimit` | Kích thước entity riêng lẻ | JAXP parser |
| `jdk.xml.maxOccurLimit` | Nút grammar khi xử lý XSD maxOccurs | Schema validation |

**Cần phân biệt:** XML **attribute** `Name="..."` trên một element khác với phần tử **SAML Attribute** `<saml:Attribute Name="groups">`, và khác với **AttributeValue**. `jdk.xml.elementAttributeLimit` **không** giới hạn số phần tử `<saml:Attribute>` hoặc số `<saml:AttributeValue>`. Phải thiết kế riêng logic SAML attribute budget sau validation.

### 10.4. OpenSAML không nhất thiết dùng parser của bạn

Spring Security dựa vào OpenSAML; OpenSAML có parser pool/unmarshaller/security defaults riêng. Việc đặt một `DocumentBuilderFactory` trong Spring Bean **không tự thay XML parser dùng bởi OpenSAML**. Phải đối chiếu cấu hình parser pool và extension points của đúng OpenSAML version:

1. Kiểm dependency `spring-security-saml2-service-provider` và OpenSAML transitives trong `mvn dependency:tree`.
2. Kiểm các parser features mặc định của OpenSAML và các security advisories hiện hành.
3. Nếu tùy biến parser, dùng **supported initialization/parser pool configuration**, không sử dụng reflection hoặc thay parser global theo suy đoán.
4. Kiểm assertion với DOCTYPE/XXE bị từ chối trong integration test thật (signed fixture không thể được “chèn” sau khi ký mà vẫn valid).
5. Không “parse, sửa XML, rồi verify signature” bằng DOM đã được normalize theo cách riêng.
6. Giữ XML parser/decrypt/validation budgets và rate limits tương ứng. Không tin JVM default limit một cách mù quáng.

## 11. Kiểm tra chữ ký, encrypted assertions và XML Signature Wrapping

**Giới hạn kích thước ≠ xác minh SAML trust.** Sau pre-parse budget, OpenSAML/Spring Security phải tiếp tục kiểm:

- SAML Response/Assertion signature bằng **IdP trusted signing certificate** đúng registration, signature algorithms được cho phép.
- `Issuer` đúng IdP, `Destination` đúng ACS, `AudienceRestriction` đúng SP entityID.
- `SubjectConfirmationData.Recipient` đúng callback, `InResponseTo` correlation đúng request khi flow yêu cầu.
- `NotBefore/NotOnOrAfter`, bearer confirmation time, replay/one-time use policy.
- Xử lý encrypted assertions bằng **SP decryption credentials** khi IdP dùng encryption.
- Chỉ ánh xạ principal/attributes từ **assertion đã được validate và gắn đúng chữ ký**, không chọn một unsigned assertion có tên trường giống nhau.
- Chặn signed XML wrapping/duplicate ID/reference ambiguity theo library policy và phiên bản đã vá.
- Không tin `RelayState` để quyết định tenant hoặc redirect external tùy ý.
- Không cho response status `Success` tự thay điều kiện signature/issuer/recipient.
- Không tin XML attributes từ request trước khi provider trả authenticated principal.

### 11.1. Ngân sách trước và sau giải mã

```text
HTTP POST byte limit
   |
   v
Base64 string limit
   |
   v
Decoded XML byte limit
   |
   v
OpenSAML secure parse + crypto validation
   |
   +-- Signature verification
   +-- EncryptedAssertion/EncryptedID decryption
   +-- Signed response / assertion conditions
   +-- Validation result
   |
   v
Verified attribute budget
   |
   v
Local identity + tenant authorization
```

**Nếu XML chứa EncryptedAssertion:** trước decrypt vẫn phải có body/XML limit; sau decrypt, object tree có thể lớn hơn encrypted payload. Attribute budget sau validated decryption là lớp **chặn dữ liệu business/session**; nó không ngăn được mọi allocation **trong lúc** decrypt. Nếu rủi ro cao, xem xét maximum assertion count, encrypted data node count, signatures/references/transforms cùng provider-specific bounds và hợp đồng IdP không phát assertion quá nhiều.

### 11.2. Đừng “chữa” oversized assertion bằng truncate

Các cách sai:

```text
SAMLResponse = SAMLResponse.substring(0, MAX)
XML = XML.replaceAll("<AttributeValue>...", "")
Only take first Assertion before signature checks
Ignore Signature when XML is too big
Use unsigned NameID when signed Assertion too large
Silently drop extra groups and allow ROLE_USER
Set maxPostSize=-1 / client_max_body_size 0 globally
```

- Truncate Base64/XML làm mất integrity và có thể tạo lỗi parser/crypto.
- Bỏ bớt attributes **trước validation** thay đổi signed XML, phá signature semantics hoặc tạo parser mismatch.
- Bỏ qua một số roles mà không rõ quy tắc có thể làm privilege decisions không ổn định. Đúng hơn: **fail closed** với thông báo chung và yêu cầu IdP giảm dữ liệu/ứng dụng dùng lookup đáng tin.
- Không chấp nhận unsigned assertion do parser bị fail trên signed assertion lớn.

## 12. Giới hạn dữ liệu thuộc tính sau trust verification

SAML AttributeStatement có thể mang nhiều `<saml:Attribute>`, mỗi cái có nhiều `<saml:AttributeValue>`, có thể chứa non-string XMLObject. Một đối tác có thể phát hàng nghìn groups. Việc chấp nhận và ánh xạ **toàn bộ** vào `Authentication`/`HttpSession` khiến:

- `GrantedAuthorities` bùng nổ, tăng memory/cost kiểm role.
- Serialization `SPRING_SECURITY_CONTEXT` vào Redis tăng độ trễ/network/storage.
- Session replication/backup và cluster failover trở nên đắt.
- Log/audit/quy trình export nhân bản các claim không cần thiết.
- Ứng dụng có thể tạo authorization bypass nếu mapping `groups`→`ROLE_ADMIN` không có allowlist hoặc issuer trust contract.

### 12.1. Chọn attribute release tối thiểu

| Thuộc tính/claim | Có cần? | Hướng xử lý an toàn |
| --- | --- | --- |
| `NameID` hoặc immutable external subject | Thường cần định danh | Gắn với trusted `Issuer`/registration, kiểm format/độ dài |
| `email` | Có thể cần để liên hệ | Không dùng làm khóa identity duy nhất nếu có thể đổi/tái sử dụng |
| `displayName` | UX | Giới hạn bytes, escape khi render HTML, không log tràn |
| `groups` | Có thể cần authorization | Chỉ các groups do IdP được phê duyệt; giới hạn số lượng, mapping least privilege |
| `department`, `costCenter` | Business | Validate schema; không biến raw text thành SQL/command |
| `entitlements` | Nhạy cảm | Dùng signed/verified context, version/issuer binding, local policy |
| Rich XML attributes | Hiếm | Cần schema và hardening riêng, không tự gọi `toString()` lên arbitrary objects |
| Blob/certificate/custom JSON encoded in XML | Thường không cần | Từ chối hoặc đưa qua kênh khác có giới hạn riêng |

**Không bao giờ cấp `ROLE_ADMIN` vì thuộc tính `groups` chứa chuỗi `admin` mà bạn lấy từ bất kỳ IdP mới nào.** Mapping phải gắn với issuer/registration, namespace group, tenant membership và policy ứng dụng.

### 12.2. Vấn đề AttributeValue không phải luôn String

Spring Security 6.x `Saml2AuthenticatedPrincipal#getAttributes()` trả `Map<String, List<Object>>`, vì SAML cho phép values có nhiều kiểu. Trong một policy chấp nhận **chỉ text attributes**, có thể:

1. Reject mọi value không phải `String` theo hợp đồng với IdP.
2. Không gọi `value.toString()` trên arbitrary object để tính size khi object có thể serialize/lazy-load/gây chi phí lớn.
3. Đo `value.getBytes(StandardCharsets.UTF_8).length` để giới hạn byte Unicode.
4. Giới hạn tổng attributes/values trước khi tạo authority objects và trước khi persist session.
5. Đừng serialize toàn bộ raw SAMLResponse hoặc XML tree trong business model chỉ để lấy một group.
6. Nếu đối tác cần structured values, viết parser/mapper typed được giới hạn và kiểm thử như một feature riêng.

### 12.3. Java policy class giới hạn verified attributes

Ví dụ **trong ứng dụng Spring 6.x**, file `src/main/java/com/example/saml/VerifiedAttributeBudget.java`:

```java
package com.example.saml;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

public final class VerifiedAttributeBudget {

    private static final int MAX_NAMES = 32;
    private static final int MAX_VALUES = 128;
    private static final int MAX_VALUE_BYTES = 2_048;
    private static final int MAX_TOTAL_BYTES = 32_768;

    private VerifiedAttributeBudget() { }

    /**
     * Chỉ gọi SAU KHI OpenSAML đã validate Response/Assertion.
     * Đối tác trong ví dụ phải phát text AttributeValues.
     */
    public static void check(Map<String, List<Object>> attrs) {
        if (attrs == null || attrs.size() > MAX_NAMES) {
            throw new IllegalArgumentException(
                "Verified SAML attribute count exceeded");
        }

        int valueCount = 0;
        int totalBytes = 0;

        for (var entry : attrs.entrySet()) {
            String name = entry.getKey();
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "SAML attribute name invalid");
            }

            totalBytes +=
                name.getBytes(StandardCharsets.UTF_8).length;

            List<Object> values = entry.getValue();
            if (values == null) {
                throw new IllegalArgumentException(
                    "SAML attribute values unavailable");
            }

            if ((long) valueCount + values.size() > MAX_VALUES) {
                throw new IllegalArgumentException(
                    "SAML attribute values exceeded");
            }
            valueCount += values.size();

            for (Object value : values) {
                if (!(value instanceof String text)) {
                    throw new IllegalArgumentException(
                        "Unexpected non-text SAML attribute");
                }

                int bytes =
                    text.getBytes(StandardCharsets.UTF_8).length;

                if (bytes > MAX_VALUE_BYTES) {
                    throw new IllegalArgumentException(
                        "SAML value too large");
                }

                totalBytes += bytes;
                if (totalBytes > MAX_TOTAL_BYTES) {
                    throw new IllegalArgumentException(
                        "Total SAML attributes too large");
                }
            }
        }

        if (totalBytes > MAX_TOTAL_BYTES) {
            throw new IllegalArgumentException(
                "Total SAML attribute bytes exceeded");
        }
    }
}
```

**Đây là logic chính sách, chưa tự được nối vào SAML provider.** Nó không được gọi bằng cách tự decode XML trước Spring, và không nên đặt chỉ tại MVC controller sau khi session đã được cấp. Trong provider/custom converter theo đúng Spring Security version, thực thi **sau signature/conditions validation nhưng trước Authentication thành công được lưu**.

Trong production, thay `IllegalArgumentException` bằng `Saml2AuthenticationException`/policy-specific authentication failure đúng với phiên bản API (không biến malformed input thành 500), không log toàn bộ attribute values. Nên kiểm tổng byte bằng logic chống overflow `if (bytes > MAX_TOTAL_BYTES - totalBytes) reject` nếu policy nâng ngưỡng tới kích thước lớn; mẫu này có tổng tối đa nhỏ nhờ chặn name count/values sớm nhưng vẫn cần mã production phòng thủ.

### 12.4. Điểm nối với Spring Security 6.5 / OpenSAML 5

Một đường mở rộng thường dùng trong Spring Security 6.5 là:

```java
// Fragment có chủ đích, không phải class hoàn chỉnh.
// Áp dụng khi đang dùng đúng OpenSaml5AuthenticationProvider
// và converter trả Saml2Authentication/Saml2AuthenticatedPrincipal.

OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();

OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter
    defaultConverter =
    new OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication authentication =
        defaultConverter.convert(responseToken);

    Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) authentication.getPrincipal();

    VerifiedAttributeBudget.check(principal.getAttributes());

    return authentication;
});

// Đăng ký provider trong SecurityFilterChain qua:
// saml2Login(saml -> saml.authenticationManager(
//     new ProviderManager(provider)));
```

**Quan trọng về phiên bản/API:**

- Đoạn trên cần import các lớp `OpenSaml5AuthenticationProvider`, `Saml2Authentication`, `Saml2AuthenticatedPrincipal`, `ProviderManager` phù hợp Spring Security 6.5; dùng như **fragment trong cấu hình** đã có IdP/RelyingPartyRegistration, không độc lập chạy bằng javac.
- Trong Spring Security 7, `Saml2AuthenticatedPrincipal` được đánh dấu deprecated theo hướng `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. Phải cập nhật converter theo version; không trộn APIs.
- Khi converter chỉ kiểm **sau** khi OpenSAML đã tạo objects, nó bảo vệ khỏi lưu attributes quá lớn/role explosion, nhưng **không** chặn hoàn toàn chi phí parsing/decryption trước converter. Nếu cần hard upper bound về nodes/attribute structures **trước** allocation lớn, tùy biến validator/parser pool bằng extension point có test; không thay thế default signature checks.
- Nếu để `IllegalArgumentException` thoát lên và client nhận 500, hãy thay bằng exception đúng authentication policy và failure handler có mã lỗi sanitized; verify end-to-end.
- Converter chỉ nên đọc **verified** assertion/attributes mà provider đã bind đúng signed object. Không chọn một assertion khác bằng custom XPath/regex.

### 12.5. Vì sao không xóa thừa attributes rồi cứ cho đăng nhập?

Một IdP gửi `groups` dài có thể vô tình vượt giới hạn:

- Nếu mapping ứng dụng có policy rõ “chỉ cần hai role được allowlist”, có thể thiết kế IdP phát những roles nhỏ hoặc backend kiểm membership từ authority store.
- **Không tùy tiện truncate** danh sách groups, vì một user có group quyền quan trọng ở phần bị cắt, hoặc code lấy “group đầu tiên” có thể thay ý nghĩa authorization.
- Nếu policy cho phép drop **một số non-security attributes** sau khi signature đã validate, phải thiết kế deterministic allowlist, không ảnh hưởng principal/tenant/role decisions và có audit.
- Với SAML metadata/attribute contract, IdP và SP nên thỏa thuận một **stable subject** và tập attribute tối thiểu; khi quá ngưỡng, thông báo lỗi chung và mở quy trình xem xét thay vì nới toàn bộ hệ thống.
- Trong mọi trường hợp không cấp quyền từ dữ liệu chưa được xác minh.

## 13. EncryptedAssertion, certificate và signature complexity

Một SAML Response có thể chứa:

```xml
<samlp:Response ...>
  <ds:Signature>...</ds:Signature>
  <saml:EncryptedAssertion>...</saml:EncryptedAssertion>
</samlp:Response>
```

Trong trường hợp encryption:

1. XML “bọc ngoài” có thể nhỏ, nhưng after decrypt cần dựng assertion và attributes.
2. Có thể có nhiều encrypted objects, encrypted keys và XML signatures; tổng chi phí CPU tăng theo count/complexity.
3. Việc giải mã phải dùng **decryption credential của SP** đúng registration, không dùng tùy tiện IdP signing cert.
4. Kiểm **cipher algorithm allowlist** và giới hạn số lượng assertions/EncryptedAssertions theo hợp đồng IdP.
5. Không accept “partial success” khi một assertion decrypt fail nhưng parser trả một assertion khác không có chữ ký hợp lệ.
6. Sau decryption phải kiểm signed-node binding, conditions, audience và subject confirmation.
7. Nếu có nhiều valid assertions theo profile, ứng dụng cần policy rõ cái nào dùng; không chọn dễ dãi assertion chứa role mong muốn.
8. Encrypted data/crypto can be expensive even when HTTP body < size limit, nên cần per-request budgets, rate limits, CPU metrics và test tải.

**Không nới maxXMLBytes thành vô hạn để cứu một IdP gửi nhiều EncryptedAssertions.** Đầu tiên xác định IdP đang phát nội dung gì, chữ ký/encryption scheme có cần thiết không và có thể giảm attributes/duplicate assertions không.

## 14. RelayState, parameters trùng và response pollution

`RelayState` thường là opaque correlation state; nó không phải một route/URL được tin sẵn.

**Các vấn đề cần chặn:**

- Nhiều field `SAMLResponse` trong body hoặc query+body gây ambiguous `getParameter()` precedence. Chỉ nhận **một** field.
- Có `SAMLResponse` trong query string khi ACS trông đợi body. Chính sách sample chọn reject query toàn bộ để tránh HTTP parameter pollution; nếu có IdP profile dùng query tĩnh thì phải thiết kế rõ.
- `RelayState` quá dài, trùng lặp, chứa URL external hoặc giả dạng tenant ID. Giới hạn bytes và xác minh rằng nó phù hợp request/session correlation đã tạo; không dùng trực tiếp làm `redirect`.
- Field lạ như `username`, `role`, `tenant` gửi kèm SAMLResponse. **Không** dùng chúng để xác thực/ủy quyền; có thể reject theo allowlist form parameter đã thống nhất.
- Nếu proxy/Servlet container decode `+`, `%2B` hoặc Unicode sai, Base64 có thể bị biến đổi. Chẩn đoán encoding, không tắt checksum/signature hoặc “sửa Base64 bằng replace space thành +” theo suy đoán.
- Không đẩy assertion vào GET/query vì nó có thể rò trong URL/referrer/log và vượt giới hạn headers/URLs; dùng binding đúng metadata.
- Nếu Content-Type là `multipart/form-data` nhưng SAML integration chỉ chấp nhận URL-encoded POST, reject thay vì mời app tự hỗ trợ upload XML.

## 15. Logging, HTTP error và UX khi vượt ngân sách

### 15.1. Phân loại lỗi theo tầng

| Loại | HTTP thường gặp | Ý nghĩa |
| --- | --- | --- |
| Edge raw body vượt | **413** | Request body lớn hơn policy tại ingress |
| App Base64/XML byte budget vượt | **413** | Payload quá lớn trước SAML parser |
| Form sai, thiếu/trùng `SAMLResponse` | **400** | Request structure không đúng |
| Content-Type/Content-Encoding không hỗ trợ | **415** | Binding payload transport không được hỗ trợ theo policy |
| XML parse fail / DOCTYPE / XXE | Thường **400** hoặc auth failure | Malformed/prohibited XML; không login |
| Signature invalid, issuer/audience sai, expired assertion | Auth failure, redirect/login/401 theo app | Không trusted SAML authentication |
| Attribute budget vượt sau validation | Auth failure, thông báo chung | Verified assertion quá lớn cho hợp đồng app |
| WAF blocked/rate limited | **429** hoặc gateway status | Request rate/session policy |
| Hạ tầng IdP/network lỗi | 5xx hoặc domain-specific unavailable | Khác với malformed assertions |

**Đừng cố ép tất cả thành HTTP 413.** XML ký sai là lỗi authentication, không phải bandwidth. Nếu parser xảy ra `OutOfMemoryError`, đó là lỗi vận hành nghiêm trọng và rất có thể guard đến quá muộn; không catch rồi trả 200 với user mặc định.

### 15.2. Dữ liệu được phép đưa vào metrics

Nên đo:

```text
saml_acs_requests_total{registration,decision,reason}
saml_acs_body_bytes_histogram{registration}
saml_base64_chars_histogram{registration}
saml_decoded_xml_bytes_histogram{registration}
saml_parse_duration_seconds{registration}
saml_signature_validation_failure_total{registration}
saml_attribute_names_histogram{registration}
saml_attribute_values_histogram{registration}
saml_attribute_bytes_histogram{registration}
saml_session_serialized_bytes_histogram{application}
saml_acs_inflight_requests{node}
saml_413_total{layer,route}
saml_xml_security_rejections_total{reason}
```

**Không log**:

```text
Raw SAMLResponse / Base64
Raw decoded XML / Assertion / NameID nếu PII
Full AttributeStatement / group values
XML signing or decryption private keys
Session cookies, RelayState opaque secrets
SAML signing certificates as sensitive dump in every error
Full Authorization headers / tokens
```

Cardinality control: không dùng username/NameID, arbitrary issuer URL, XML attribute values hay request ID làm Prometheus label. Dùng allowlisted registrationId, reason category và bounded sizes. Error response nên dùng correlation ID vô hại, tránh echo payload.

### 15.3. Runbook khi đối tác báo 413

1. Ghi thời gian, registrationId/IdP, status, ingress route, chính sách version và correlation ID (không xin toàn bộ SAMLResponse qua email).
2. Xác định **layer** trả 413: CDN, WAF, NGINX, Tomcat hay app guard.
3. Kiểm các histogram raw body/Base64/XML/attributes, không mở debug raw XML production.
4. Yêu cầu IdP kiểm attribute release, nested groups và encrypted assertions trong môi trường test.
5. Nếu hợp lệ cần tăng, cân nhắc **ngưỡng riêng registration** và tiêu thụ tài nguyên p95/p99, không nâng tất cả endpoints.
6. Kiểm boundary tests, malicious fixtures, CPU/memory/Redis serialization.
7. Triển khai canary, theo dõi thay đổi CPU/GC/413 rate và khả năng login.
8. Viết kết quả QA có giới hạn mới, owner phê duyệt, lý do, ngày đánh giá lại.
9. Nếu vượt giới hạn thường xuyên do một partner, đề xuất giảm group claims, chuyển sang backend userinfo/entitlement lookup có authentication và caching đúng.
10. Không làm lỗi người dùng bằng retry loop vô hạn hoặc khuyến nghị “mở Developer Tools rồi gửi toàn bộ SAMLResponse”.

## 16. Java 17 độc lập: mô phỏng ngân sách theo hai pha

Ví dụ này chạy bằng **JDK 17 không cần Spring, IdP hay certificate**. Nó minh họa **ngân sách trước XML parse** và **ngân sách attribute giả lập sau trust verification**. Nó KHÔNG xác minh chữ ký, không parse XML, không tạo SAMLResponse hợp lệ và **không chứng minh an ninh của một SP thực**.

File `SamlPayloadBudgetDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class SamlPayloadBudgetDemo {

    private static final int MAX_FORM_BYTES = 1_048_576;
    private static final int MAX_BASE64_CHARS = 650_000;
    private static final int MAX_XML_BYTES = 450_000;
    private static final int MAX_ATTRIBUTE_NAMES = 32;
    private static final int MAX_VALUES = 128;
    private static final int MAX_VALUE_BYTES = 2_048;
    private static final int MAX_ATTRIBUTE_BYTES = 32_768;

    static String envelopeDecision(int bodyBytes, String base64) {
        if (bodyBytes > MAX_FORM_BYTES) {
            return "REJECT_FORM_BYTES";
        }
        if (base64 == null || base64.isEmpty()) {
            return "REJECT_BASE64";
        }
        if (base64.length() > MAX_BASE64_CHARS) {
            return "REJECT_BASE64_CHARS";
        }

        byte[] xml;
        try {
            xml = Base64.getDecoder().decode(base64);
        }
        catch (IllegalArgumentException ex) {
            return "REJECT_BASE64";
        }

        if (xml.length == 0) {
            return "REJECT_XML_EMPTY";
        }
        if (xml.length > MAX_XML_BYTES) {
            return "REJECT_XML_BYTES";
        }

        // Chỉ có nghĩa "cho phép đến bước parse/verify tiếp theo".
        return "ALLOW_PREPARSE";
    }

    // attrs là fixture giả định ĐÃ ĐƯỢC xác minh qua SAML.
    // Production không nhận map này trực tiếp từ browser.
    static String attributeDecision(Map<String, List<String>> attrs) {
        if (attrs == null || attrs.size() > MAX_ATTRIBUTE_NAMES) {
            return "REJECT_ATTRIBUTE_NAMES";
        }

        int valueCount = 0;
        int byteCount = 0;
        for (var entry : attrs.entrySet()) {
            String name = entry.getKey();
            if (name == null || name.isBlank()) {
                return "REJECT_ATTRIBUTE_NAME";
            }

            byteCount +=
                name.getBytes(StandardCharsets.UTF_8).length;

            List<String> values = entry.getValue();
            if (values == null ||
                (long) valueCount + values.size() > MAX_VALUES) {
                return "REJECT_ATTRIBUTE_VALUES";
            }

            valueCount += values.size();

            for (String value : values) {
                if (value == null) {
                    return "REJECT_ATTRIBUTE_VALUE";
                }
                int n = value.getBytes(StandardCharsets.UTF_8).length;
                if (n > MAX_VALUE_BYTES) {
                    return "REJECT_ATTRIBUTE_VALUE_BYTES";
                }
                byteCount += n;
                if (byteCount > MAX_ATTRIBUTE_BYTES) {
                    return "REJECT_ATTRIBUTE_TOTAL_BYTES";
                }
            }
        }

        return byteCount > MAX_ATTRIBUTE_BYTES
            ? "REJECT_ATTRIBUTE_TOTAL_BYTES"
            : "ALLOW_MAPPED";
    }

    public static void main(String[] args) {
        String validDemoXml = Base64.getEncoder().encodeToString(
            "<demo/>".getBytes(StandardCharsets.UTF_8));

        String hugeXml = Base64.getEncoder().encodeToString(
            new byte[MAX_XML_BYTES + 1]);

        System.out.println("smallEnvelope=" +
            envelopeDecision(150, validDemoXml));

        System.out.println("largeBody=" +
            envelopeDecision(MAX_FORM_BYTES + 1, validDemoXml));

        System.out.println("badBase64=" +
            envelopeDecision(150, "%%%"));

        System.out.println("largeXml=" +
            envelopeDecision(700_000, hugeXml));

        System.out.println("smallAttributes=" +
            attributeDecision(
                Map.of("groups", List.of("ops", "staff"))));

        Map<String, List<String>> manyNames =
            new LinkedHashMap<>();
        for (int i = 0; i < 33; i++) {
            manyNames.put("field" + i, List.of("x"));
        }
        System.out.println("manyNames=" +
            attributeDecision(manyNames));

        System.out.println("manyValues=" +
            attributeDecision(
                Map.of("groups", java.util.Collections.nCopies(
                    129, "x"))));

        System.out.println("longValue=" +
            attributeDecision(
                Map.of("groups", List.of("x".repeat(2_049)))));

        Map<String, List<String>> aggregate =
            new LinkedHashMap<>();
        for (int i = 0; i < 19; i++) {
            aggregate.put("g" + i,
                List.of("x".repeat(1_800)));
        }
        System.out.println("aggregate=" +
            attributeDecision(aggregate));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 SamlPayloadBudgetDemo.java
java SamlPayloadBudgetDemo
```

Stdout xác định:

```text
smallEnvelope=ALLOW_PREPARSE
largeBody=REJECT_FORM_BYTES
badBase64=REJECT_BASE64
largeXml=REJECT_XML_BYTES
smallAttributes=ALLOW_MAPPED
manyNames=REJECT_ATTRIBUTE_NAMES
manyValues=REJECT_ATTRIBUTE_VALUES
longValue=REJECT_ATTRIBUTE_VALUE_BYTES
aggregate=REJECT_ATTRIBUTE_TOTAL_BYTES
```

**Giải thích:**

- `smallEnvelope=ALLOW_PREPARSE` chỉ nói Base64 của `<demo/>` nhỏ và decode được. `<demo/>` **không** phải SAML Response có chữ ký; OpenSAML sẽ không cho login.
- `largeBody=REJECT_FORM_BYTES`: raw form body vượt giới hạn.
- `badBase64=REJECT_BASE64`: Base64 syntax sai; không nên “cứ thay dấu cho decode được”.
- `largeXml=REJECT_XML_BYTES`: encoded value còn dưới 650.000 chars nhưng XML byte[] dài 450.001, bị chặn riêng.
- `smallAttributes=ALLOW_MAPPED`: map giả lập nhỏ, còn cần identity + authorization thực.
- `manyNames=REJECT_ATTRIBUTE_NAMES`: 33 tên >32.
- `manyValues=REJECT_ATTRIBUTE_VALUES`: 129 values >128.
- `longValue=REJECT_ATTRIBUTE_VALUE_BYTES`: một text value có 2.049 UTF-8 bytes >2.048.
- `aggregate=REJECT_ATTRIBUTE_TOTAL_BYTES`: 19 values ×1.800 bytes cộng names >32 KiB.
- Mã không làm TLS, XML parse, certificate chain, signature, audience, recipient, replay hoặc IdP source matching. Hai hàm chỉ mô phỏng **resource budgets**, tuyệt đối không sử dụng để cấp Authentication trong production.

## 17. Kiểm thử tích hợp với IdP thực và fixtures có chữ ký

**Để kiểm một case khác signature failure**, phải dùng fixture đã ký hợp lệ với IdP test hoặc tạo fixture bằng IdP/key test rồi ký lại **sau khi** sửa nội dung. Nếu lấy một SAMLResponse signed rồi thêm 10.000 AttributeValue bằng thao tác sửa text, signature sẽ invalid trước hoặc cùng lúc với check attribute và có thể làm lệch kết luận test.

### 17.1. Happy path

1. Đăng ký SAML RP `corp`, ACS `https://sp.example.org/login/saml2/sso/corp` và trust IdP test đúng.
2. IdP test phát signed Response, đúng issuer/audience/recipient/destination/time và có group values hợp đồng.
3. Ghi **chỉ các metrics kích thước**, không giữ SAMLResponse gốc trong log hoặc report.
4. Browser POST form qua CDN/NGINX/Tomcat/Spring Security.
5. Edge raw body limit, Tomcat form limits, app Base64/XML guard cho qua.
6. OpenSAML parse/verify, signature/conditions PASS.
7. Attribute budget PASS, local user/tenant mapping PASS.
8. Local SecurityContext/session được tạo, app trả resource được phân quyền.
9. Kiểm Redis/session serialized bytes nằm trong ngân sách; refresh/login không gây GC storm.

### 17.2. Ma trận boundary và negative tests

| Test | Dữ liệu/thiết lập | Kỳ vọng |
| --- | --- | --- |
| **HTTP body limit -1** | Form body nhỏ hơn 1 MiB đúng 1 byte | Không bị edge chặn vì size; còn phải qua SAML validation |
| **HTTP body limit** | Bằng 1 MiB | Đúng policy “> limit” thường chấp nhận; test thực NGINX |
| **HTTP body limit +1** | Vượt 1 MiB đúng 1 byte | 413 ở edge, không đến OpenSAML |
| **Chunked POST** | Không có Content-Length, body vượt | Proxy/container vẫn reject, không bypass |
| **Many form parameters** | 17+ keys khi Tomcat giới hạn 16 | Reject; không crash |
| **Duplicate SAMLResponse** | Hai trường cùng tên | 400, không chọn “first” |
| **SAMLResponse in query** | POST có query `SAMLResponse=...` | Guard reject theo policy, tránh parameter pollution |
| **Missing SAMLResponse** | Form không có field | 400 |
| **Malformed Base64** | Có `%%%` hoặc padding lỗi | 400, không fallback permissive |
| **Encoded char limit +1** | Base64 >650.000 chars nhưng HTTP body dưới proxy limit | 413 tại app guard |
| **Decoded XML bytes limit +1** | Base64 đúng, XML 450.001 bytes | 413, không XML parse |
| **Decoded XML empty** | Base64 của 0 bytes | 400 |
| **Small unsigned XML** | `<demo/>` hoặc SAML unsigned | Guard có thể pass, OpenSAML authentication FAIL |
| **DOCTYPE/XXE** | XML chứa DTD/external entity | XML parse security reject; không đọc file/gọi network |
| **Entity amplification** | Nested entities/billion-laughs | Parser rejects, CPU/memory bounded |
| **XML depth >64** | Nhiều nested elements | Reject ở parser limit khi config hiệu lực |
| **XML name cực dài** | Huge element/attribute names | Reject theo XML name/byte budget |
| **Many DOM nodes** | Hàng nghìn XML elements trong byte budget | Node/parser complexity policy reject hoặc benchmark giới hạn |
| **Many XML signatures** | Nhiều Reference/Transforms | Reject unsupported complexity/invalid signatures |
| **Signature wrapping** | Duplicate IDs, unsigned assertion chen thêm | Reject; không lấy unsigned NameID/role |
| **Wrong issuer** | Signed by wrong IdP trust/registration | Authentication FAIL |
| **Wrong audience** | AudienceRestriction cho SP khác | Authentication FAIL |
| **Wrong recipient** | SubjectConfirmationData.Recipient khác ACS | Authentication FAIL |
| **Wrong Destination** | Response Destination khác public ACS | Authentication FAIL |
| **Expired Assertion** | NotOnOrAfter đã qua | Authentication FAIL |
| **Replay** | Gửi lại Response/ticket theo correlation policy | Reject theo anti-replay/OneTimeUse/request policy |
| **EncryptedAssertion valid** | Signed/encrypted fixture đúng dưới budgets | Decrypt/verify success, chỉ verified attributes |
| **EncryptedAssertion expansion** | Nhiều decrypted values khiến budget vượt | Không tạo session, record bounded failure |
| **Multiple Assertions** | Hơn số assertions cho phép theo hợp đồng | Reject hoặc xử lý đúng provider policy, không chọn unsigned |
| **Many SAML attribute names** | 33 verified names | Fail attribute budget |
| **Many values** | 129 verified values | Fail attribute budget |
| **One long value** | UTF-8 >2.048 bytes | Fail attribute budget |
| **Aggregate values too large** | Tổng UTF-8 >32 KiB | Fail attribute budget |
| **Nested group explosion** | IdP test phát hàng trăm groups | Reject/IdP reduces groups theo contract |
| **Unicode multi-byte value** | Vietnamese/emoji, byte count > char count | Dùng UTF-8 byte budget đúng |
| **RelayState oversized** | >policy, signed response vẫn valid | Guard reject |
| **Content-Encoding gzip** | HTTP compressed POST ngoài policy | 415/reject tại edge/app, không inflate |
| **POST wrong Content-Type** | JSON, multipart hoặc XML trực tiếp | 415/reject theo ACS binding |
| **SAML SLO endpoint** | Large `SAMLRequest` logout | Có size/parse/signature budget riêng |
| **Metadata import** | Very large/untrusted metadata XML | Separate bounded fetch/parse and SSRF protection |
| **Redis/session bloat** | Verified attributes lớn sát budget | Session serialized bytes vẫn có bounded SLA |
| **Login burst** | Nhiều signed small responses/sec | Rate/concurrency limits, no CPU exhaustion |
| **Two pods different config** | Ingress A limit 1m, B unlimited | Fail deployment consistency; sửa policy drift |
| **IdP partner changes attributes** | Group release tăng 2× | Alert, explicit review; không tự tăng global limits |
| **Error logs leak XML** | Request invalid large | Không ghi raw SAMLResponse/XML/NameID |
| **Browser retry loop** | IdP vẫn gửi oversized response | Có graceful error, tránh auto-redirect storm |

### 17.3. Lưu ý bộ test không được nhầm mục tiêu

Nếu muốn test **decoded XML limit**, phải chuẩn bị request body và encoded chars **nằm dưới** giới hạn raw/encoded, nếu không request sẽ bị edge chặn trước và bạn chưa chứng minh app guard.

Nếu muốn test **attribute budget sau xác minh**, phải dùng signed assertion có count/value vượt profile nhưng toàn bộ request vẫn nhỏ hơn network/XML budgets. Nếu sửa nội dung sau ký, bài test sẽ chỉ chứng minh signature invalid, không chứng minh attribute count được kiểm.

Nếu muốn test **XML entity expansion**, không nhất thiết có signed message hợp lệ (DOCTYPE làm hỏng XML/signature contract): mục tiêu là parser **reject trước khi truy xuất network hoặc tiêu thụ tài nguyên quá mức**. Đây là test hardening parser, không cần xác nhận một SAML signed message được accept.

Nếu muốn test **HTTP POST size với Content-Length -1**, phải gửi chunked upload qua **đúng public ingress**, không chỉ unit-test Servlet Filter ở JVM.

## 18. Test tự động trong Spring Security mà không gọi IdP production

### 18.1. Ba cấp test nên tách

1. **Unit tests Java:** `SamlPayloadBudgetDemo`/attribute policy kiểm boundary arithmetic và fail-closed; không giả vờ verify SAML.
2. **Servlet integration tests:** Dùng MockMvc hoặc embedded Tomcat để xác minh filter order, oversized Base64/decoded XML, Content-Type và HTTP statuses. MockMvc **không mô phỏng hoàn toàn** ingress/chunked/Tomcat connector limits.
3. **Real SAML integration tests:** IdP staging phát signed encrypted/unencrypted fixtures, browser ACS có correlation/time/issuer/recipient hợp lệ. Test invalid cases và đo memory/CPU/session.
4. **Infrastructure tests:** NGINX/WAF/k8s ingress 413, chunked body, body buffering/temp file, rate limits, multiple replicas và certificate/route.
5. **Load/performance tests:** p95/p99 parse latency, GC allocation, heap high-water mark, CPU and queue depths ở near-limit payload + concurrency.

Một MockMvc test đơn lẻ cho 413 không thay được test thực TLS/NGINX/body streaming. Ngược lại, một synthetic huge Base64 không có chữ ký là đủ để chứng minh **pre-parse guard**, không đủ cho post-validation mapping.

### 18.2. Mẫu test scenarios bằng bảng fixture

```text
fixture-small-signed.xml               valid,  25 KiB, 3 attributes
fixture-near-limit-signed.xml          valid, 445 KiB, bounded attributes
fixture-too-many-groups-signed.xml     valid, 300 KiB, 180 group values
fixture-expired-signed.xml             expired NotOnOrAfter
fixture-foreign-issuer-signed.xml      wrong trusted issuer
fixture-encrypted-many-values.xml      decrypts to oversized attribute set
fixture-invalid-duplicate-id.xml       signature-wrapping/ID ambiguity
fixture-xxe-doctype.xml                untrusted XML parser rejection test
```

Tên file chỉ minh họa cấu trúc test, **không phải tệp có sẵn** hoặc yêu cầu tạo chúng ở repository. Mỗi signed fixture cần được tạo/ký bởi IdP test với certificates riêng; tuyệt đối không lưu private key production hay user data production trong CI.

### 18.3. Điều kiện PASS khi “đã giới hạn tài nguyên”

Một triển khai được coi PASS nếu:

- Request vượt raw HTTP limit không vào app parser, kể cả streaming/chunked.
- Form lớn/nhiều parameters bị Tomcat/edge từ chối, không silently chọn partial parameters.
- Encoded/XML limits reject trước OpenSAML.
- XML parser từ chối DOCTYPE/XXE, không truy xuất URL/file test.
- Signed-response validation vẫn bắt buộc trên mọi payload nhỏ, không có bypass.
- Verified attributes vượt policy không được đưa vào active `SecurityContext`/HttpSession/Redis.
- IdP fixture hợp lệ gần ngưỡng vẫn login được trong latency/memory SLA.
- Không có raw SAMLResponse/XML/secret leak trong logs/errors/metrics.
- Tất cả pods/regions/ingress routes dùng cùng security policy version.
- Tenant/issuer-specific exceptions có owner/expiry/change approval và test bảo vệ tương ứng.

## 19. Xử lý sự cố thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Browser báo 413 trước khi tới Spring | NGINX/WAF/CDN body budget | Xác định request size, IdP release, ingress policy |
| Chỉ một user không login | User có rất nhiều groups/attributes | Đo attribute count qua redacted telemetry, giảm release |
| Spring thấy empty SAMLResponse | Tomcat form parser limit/parameter limit bị vượt | Kiểm Tomcat logs/status, config form size |
| `Invalid character in Base64` | Form encoding làm hỏng `+`/`%2B`, request tamper | Fix IdP/browser form URL encoding, không decode permissive |
| Raw body dưới limit nhưng XML bytes vượt | Encoded/decoded budgets khác nhau | Xem MAX_XML_BYTES, cân nhắc giảm IdP XML |
| XML parser OOM dù body nhỏ | Entity expansion, deep XML, many nodes | Enforce DOCTYPE/XXE/depth/node limit, update library |
| CPU spike khi login | Signatures/decrypt/complex XML | Crypto complexity/rate budget, optimize IdP response |
| `Signature validation failed` sau khi bỏ groups | Ai đó chỉnh signed XML sau ký | Chỉ IdP thay attribute release rồi ký lại |
| Invalid recipient/destination sau reverse proxy | Forwarded host/proto/ACS mismatch | Sửa canonical ACS/trusted headers |
| Login thành công nhưng Redis session quá lớn | Verified attributes/roles lưu không giới hạn | Post-validation budget, map minimal identity |
| Some tenants always denied | Budget global không fit IdP contracts | Profile limits per trusted registration |
| IdP timeout/retry liên tục | Error handling gây login loop | Dừng auto retry, hiển thị lỗi sanitized với request ID |
| `XMLConstants` property unsupported | JAXP provider/library khác | Fail configuration, dùng supported parser/security settings |
| 413 trả 502 ở client | Proxy buffering/swallow/timeouts/upstream connection | Test integration statuses, improve error boundary |
| Mã JWT/Group mapping vẫn cấp quyền sau limit | Attribute checks ở controller quá muộn | Enforce before Authentication/session creation |
| 403 từ business resource | Không nhất thiết do SAML size | Phân biệt authorization tenant/role và SAML login failure |
| Khác hiệu năng giữa pods | JVM heap/OpenSAML/config drift | Align versions, heaps, ingress limits and test load |
| Metadata fetch OOM | Unbounded external XML download/parser | Separate metadata max bytes/depth/SSRF controls |
| SAML SLO DoS | ACS guard không bao SLO | Add policy cho logout request/response |
| Payload leak trong traces | APM ghi request body/form parameters | Disable/redact body, retention control and incident review |

### 19.1. Cây quyết định nhanh

```text
User reports "SAML login fails"
           |
           v
Did proxy/WAF return HTTP 413?
  |-- YES -> inspect raw-body size & IdP attribute release.
  |
  +-- NO -> Did Tomcat reject form/parameters?
               |-- YES -> verify max form & param limits.
               |
               +-- NO -> Did pre-SAML guard reject?
                           |-- BASE64/XML SIZE -> 413 by policy.
                           |-- FORM/BASE64 INVALID -> 400/415.
                           |
                           +-- NO -> Did OpenSAML parse securely?
                                       |-- NO -> DTD/XXE/depth/invalid XML.
                                       |
                                       +-- YES -> Signature/issuer/audience?
                                                     |-- FAIL -> SAML trust.
                                                     |
                                                     +-- PASS -> Attribute budget?
                                                                |-- FAIL -> partner contract
                                                                |           or values too large.
                                                                |
                                                                +-- PASS -> Local user/roles/
                                                                             tenant/session.
```

**Không sửa lỗi sai tầng:** Một HTTP 413 không được chữa bằng cách disable signature verification. Một XML signature invalid không được chữa bằng cách nâng body limit. Một 403 do thiếu quyền tenant không phải nguyên nhân từ parser/size.

## 20. Quy tắc tăng giới hạn và ngoại lệ đối tác

### 20.1. Trường hợp hợp lệ cần payload lớn

Ví dụ một IdP yêu cầu truyền vài trăm certificate attributes hoặc nested group chain; doanh nghiệp có thể không thể giảm ngay. Trước khi nới:

1. Xác minh use case thực sự cần thông tin đó trong SAML assertion để cấp quyền.
2. Thử thiết kế chỉ gửi stable subject + minimal claims, còn entitlement lookup ở backend theo source tin cậy.
3. Nếu cần large group membership, định nghĩa **max groups/total bytes** theo tenant/registration và áp least privilege.
4. Đo parse/decrypt/validate CPU, peak heap, session serialized bytes, Redis bandwidth và p95 login under concurrent load.
5. Đảm bảo Java/NGINX/Tomcat/JAXP/OpenSAML có controls tương thích.
6. Chọn limit có headroom hợp lý, không vô hạn.
7. Ghi policy review/approval và ngày hết hạn ngoại lệ.
8. Test cả signed positive fixtures và malicious negative fixtures với limit mới.
9. Roll canary theo registration, so 413/latency/GC/heap/errors.
10. Khi IdP sửa release, hạ limit về mức tối thiểu phù hợp.

**Không dùng query string do browser chọn (`?tenant=vip`, `?idp=trusted`) để tự chọn ngưỡng lớn.** Profile phải xuất phát từ registration/trust context đã xác minh; riêng tầng ingress trước validation có thể dựa vào trusted host/path route và WAF policy, không dựa vào body chưa được ký.

### 20.2. Nên làm gì với các nhiều group values?

Một số lựa chọn có đánh đổi:

- IdP chỉ phát nhóm **liên quan ứng dụng**, hạn chế nested/transitive groups không cần.
- IdP phát một `role` đã được phê duyệt theo app thay vì toàn bộ memberships.
- SP nhận stable subject, sau đó backend lookup groups/entitlements từ directory/authorization service đã được xác thực và cache có TTL/invalidation.
- Nếu các groups cần cho UI, trả từ API phân trang với kiểm quyền thay vì nhồi vào signed assertion/session.
- Phân tách identity vs authorization; giữ SAML Response chỉ làm chứng minh đăng nhập, policy backend mới cấp quyền trên dữ liệu.
- Không tự hash tên group rồi coi hash là authorization claim trừ khi hệ phát hành và hệ nhận cùng kiểm signed mapping và collision handling.
- Tăng size chỉ là fallback sau khi đánh giá các cách giảm dữ liệu.

## 21. Bài tập và đáp án

**Câu 1.** IdP gửi HTTP body 900 KiB, giá trị Base64 590.000 chars, XML sau decode 442 KiB, tổng attributes sau verify 20 KiB. Profile ở mục 5 chấp nhận không?

**Đáp án:** Có thể qua **các giới hạn kích thước minh họa** (tùy các controls khác), nhưng vẫn phải parse securely, verify SAML signature/issuer/audience/recipient/time, kiểm các count/depth/attribute values và local authorization. Không được coi “nhỏ” nghĩa là trusted.

**Câu 2.** Một XML chỉ 8 KiB nhưng có DOCTYPE liên kết entities nở ra hàng trăm MB. `MAX_XML_BYTES=450.000` có đủ không?

**Đáp án:** Không. Size raw/decoded XML không ngăn entity expansion; cần cấm DTD/XXE, giới hạn expansions/depth/node và dùng parser hardened.

**Câu 3.** Một Servlet filter chỉ so `request.getContentLengthLong() > 1MiB`. Request chunked không có Content-Length có thể bypass không?

**Đáp án:** Có thể. `getContentLengthLong()` thường là `-1`. Dùng ingress body limit kiểm bytes thực, Tomcat form limit và bounded reader nếu thật sự cần direct streaming.

**Câu 4.** Tomcat có `spring.servlet.multipart.max-request-size: 1MB`. Nó có bảo vệ SAML HTTP-POST binding không?

**Đáp án:** Không phải chốt chính. SAML POST là `application/x-www-form-urlencoded`, dùng `server.tomcat.max-http-form-post-size`/parameter count và ingress body limit.

**Câu 5.** SAMLResponse có chữ ký sai nhưng payload rất nhỏ. Có thể cho đăng nhập vì không vượt size budget không?

**Đáp án:** Không. Size budget chỉ giới hạn tài nguyên; authentication provider phải verify signature/trust/conditions.

**Câu 6.** Gỡ các `AttributeValue` khỏi một Response đã ký tại gateway rồi để Spring validate phần còn lại. Có an toàn không?

**Đáp án:** Không. Thay đổi signed XML trước verification có thể phá signature/binding hoặc gây XML signature wrapping; IdP phải giảm dữ liệu **trước khi ký** hoặc SP áp mapping có chủ đích **sau validation**.

**Câu 7.** Base64 field có 600.000 ASCII chars; decoded XML có thể khoảng bao nhiêu byte?

**Đáp án:** Nếu padding hợp lệ, tối đa khoảng 450.000 bytes, dựa công thức `4*ceil(n/3)`. Actual bytes phụ thuộc padding/format; dùng byte length **sau decode** để thực thi chặt.

**Câu 8.** Sau signature validation, `groups` có 160 values nhưng policy tối đa 128. Có nên lấy 128 giá trị đầu và tạo ROLE theo đó?

**Đáp án:** Không nên mặc định. Cần fail closed với policy rõ, đề nghị IdP giảm groups hoặc dùng hậu kiểm backend; truncate làm quyền/tenant mapping thiếu nhất quán.

**Câu 9.** Application chỉ đặt `jdk.xml.elementAttributeLimit=10`. Đã chặn 1.000 phần tử `<saml:Attribute>` chưa?

**Đáp án:** Chưa. JAXP property đó giới hạn XML attributes trên **một element**, khác với số **SAML Attribute elements**. Cần kiểm application-specific attribute budget.

**Câu 10.** Dùng XML parser JAXP khác để parse rồi lấy first NameID trước khi đưa XML cho OpenSAML verify. Điều gì sai?

**Đáp án:** Có nguy cơ tin unverified content/parser differential/signature wrapping. Chỉ ánh xạ principal từ assertion đã được OpenSAML validate.

**Câu 11.** HTTP request bị NGINX trả 413 nhưng Spring log không có dòng nào. Đây có phải lỗi Spring Security SAML provider không?

**Đáp án:** Không. Proxy chặn trước khi request tới app; kiểm ingress body limit và đối tác IdP release.

**Câu 12.** Có nên log Base64/XML đầy đủ để chẩn đoán vì SAMLResponse đã được ký?

**Đáp án:** Không. Assertion có thể chứa PII/roles/session identifiers; chữ ký không biến dữ liệu thành public. Chỉ log size, registration ID, error category, trace ID đã sanitized theo chính sách.

## 22. Checklist nghiệm thu trước production

- [ ] Đã vẽ SAML HTTP-POST flow: IdP → browser → edge → Tomcat → Spring SAML filter → OpenSAML → principal/session.
- [ ] Hiểu raw HTTP form body, Base64 chars, decoded XML bytes, DOM/OpenSAML objects và verified attributes là **các ngân sách khác nhau**.
- [ ] Edge/Ingress/WAF có `client_max_body_size` hoặc tương đương cho **tất cả** ACS routes, kể cả đường không có registrationId nếu dùng.
- [ ] Size policy hoạt động với Content-Length, chunked, HTTP/2-to-HTTP/1 và request buffering.
- [ ] Tomcat/Jetty/Undertow form-post limits và parameter-count limits đúng server/version, không nhầm multipart.
- [ ] Guard chạy trước `Saml2WebSsoAuthenticationFilter`, sau container form limit; không gây double-filter registration.
- [ ] Giới hạn chiều dài `SAMLResponse`, decoded XML bytes và reject invalid Base64/multiple fields.
- [ ] Không parse XML riêng trước OpenSAML để lấy NameID/attributes; không truncate signed XML.
- [ ] XML parser cấm DTD/XXE/external entities/XInclude không cần, dùng FSP và processing limits theo version.
- [ ] Cấu hình thực sự của **OpenSAML parser pool** được kiểm tra, không giả định một JAXP Bean tự ảnh hưởng thư viện.
- [ ] SAML signature/issuer/audience/destination/recipient/time/correlation/replay bắt buộc, không bị size guard thay thế.
- [ ] EncryptedAssertion có decryption and post-decrypt complexity/attribute budget, không chỉ cipher size.
- [ ] Số assertions/XML nodes/signature refs có chính sách phù hợp nếu IdP/profile có nhu cầu đặc biệt.
- [ ] Post-verification limit kiểm names, values, single UTF-8 bytes, tổng bytes, types và allowlisted attributes.
- [ ] Nhóm/roles chỉ được map từ issuer/registration hợp đồng; không tạo `ROLE_ADMIN` từ raw group text.
- [ ] Local account/tenant/resource authorization vẫn fail closed dù SAML response hợp lệ và nhỏ.
- [ ] Không chấp nhận duplicate `SAMLResponse`, RelayState injection, untrusted route/tenant selectors hoặc Content-Encoding ngoài policy.
- [ ] ACS guard không làm sai CSRF/request correlation logic của Spring Security SAML.
- [ ] SAML SLO/metadata XML/HTTP-Redirect binding có riêng budget/XXE/SSRF controls.
- [ ] Response vượt ngân sách trả error sanitized (413/400/415 hoặc authentication fail thích hợp), không tạo login loop.
- [ ] Monitoring ghi size/count/latency/rate/heap trends với bounded labels, không log raw SAML/XML/PII.
- [ ] Tested real signed IdP fixtures và encrypted assertions, không chỉ XML unsigned/mutated.
- [ ] Negative tests đã kiểm limit-1/limit/limit+1, malformed Base64, XXE, deep nodes, groups explosion, duplicate form params và signature wrapping.
- [ ] Integration/performance tests kiểm p95/p99 parsing, heap, GC và serialized session bytes dưới peak concurrency.
- [ ] Tất cả pods/ingress regions dùng cùng chính sách, có canary/revert và version metadata.
- [ ] Khi IdP thay group release, có runbook xác định tầng lỗi; không tắt size limit bằng giá trị unlimited.
- [ ] Exception per trusted IdP/registration được review, expiry và audit, không lấy từ query/header untrusted.
- [ ] Mọi certificates/signing credentials, sample assertions và user attributes được bảo vệ trong staging/CI/production.
- [ ] Đã phân biệt việc **HTTP size PASS** với **SAML authentication PASS** và **business authorization PASS**.

**Kết luận:** Gia cố tài nguyên cho SAML Web SSO phải dùng **phòng thủ nhiều lớp**: giới hạn raw HTTP body tại edge, kích thước/số tham số form trong Servlet container, giới hạn Base64 và XML bytes trước OpenSAML, hardened XML parsing/crypto validation, rồi **attribute budget sau khi SAML được xác minh** để tránh bùng nổ dữ liệu danh tính, quyền và phiên. Không lớp nào thay được lớp khác. Một SP an toàn từ chối toàn bộ request quá lớn, tiếp tục xác minh signature/issuer/audience/recipient/time với request nhỏ, chỉ map dữ liệu đã được tin và áp chính sách tenant/resource riêng.

## 23. Tài liệu tham khảo chính thức

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): HTTP-POST `SAMLResponse`, ACS endpoints, `Saml2WebSsoAuthenticationFilter` và OpenSAML validation flow.
2. [Spring Security – Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Response converter, signature/conditions validation, assertions, attributes, custom provider và migration differences.
3. [Spring Security 6.5 – Saml2WebSsoAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html): đường nhận SAML SSO.
4. [Spring Security 6.5 – Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `Map<String,List<Object>>` attributes và `getFirstAttribute`.
5. [Spring Security – SAML2 migration notes](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/migration-7/saml2.html): API changes và OpenSaml5AuthenticationProvider response converter.
6. [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.tomcat.max-http-form-post-size`, `max-parameter-count`, `max-swallow-size` và header size.
7. [Apache Tomcat – HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): `maxPostSize`, `maxParameterCount`, việc form parameter parsing khác raw body limit.
8. [NGINX – ngx_http_core_module: client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size): giới hạn request body/HTTP 413.
9. [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): buffering, `proxy_pass` và upstream HTTPS.
10. [OASIS – SAML 2.0 HTTP Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect bindings, Base64, RelayState và transport profile.
11. [OASIS – SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Response`, `Assertion`, `AttributeStatement`, conditions và XML objects.
12. [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): DOCTYPE, external entities, secure JAXP factories.
13. [OWASP – Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): application/resource limits và request flooding.
14. [Oracle Java 17 – JAXP Security Guide](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html): `jdk.xml.*` processing limits, `FEATURE_SECURE_PROCESSING` và external access.
15. [OWASP – XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): XML parser hardening và XML signature handling.
16. [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): không log dữ liệu nhạy cảm, bounded event structure.
17. [OWASP – Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): allowlist và giới hạn input size/structure.
18. [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực đầu vào/response và session boundaries.
