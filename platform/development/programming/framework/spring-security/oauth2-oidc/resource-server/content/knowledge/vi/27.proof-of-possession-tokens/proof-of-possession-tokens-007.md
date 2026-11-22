# htm, htu và liên kết proof với phương thức, địa chỉ yêu cầu

**DPoP (Demonstrating Proof of Possession)** là cơ chế OAuth 2.0 ràng buộc access token với một khóa công khai của client. Khi gọi API, client gửi access token cùng một **DPoP proof JWT** được ký bằng private key tương ứng. Resource Server xác minh proof, kiểm tra access token đã được ràng buộc với cùng public key, rồi đối chiếu proof với HTTP request hiện tại.

Hai claim quyết định proof được gắn với request nào là:

- **htm**: HTTP method của request, ví dụ GET, POST, PATCH hoặc DELETE.
- **htu**: HTTP target URI của request, không gồm query string và fragment.

Nhờ hai claim này, proof ký cho một request GET tới một URI không thể được dùng tùy tiện cho một request POST hoặc một endpoint khác. Tuy nhiên, DPoP không ký toàn bộ HTTP message: query string, body và phần lớn headers không nằm trong htm/htu. Việc hiểu chính xác giới hạn đó, nhất là khi có reverse proxy và URL rewriting, là điều kiện để triển khai DPoP đúng.

Bài học tập trung vào **RFC 9449**, cách server so khớp htm/htu, quy tắc chuẩn hóa URI, các tình huống proxy, giới hạn method/URI binding và cách cấu hình, kiểm thử với Spring Security.

## 1. DPoP proof liên kết với request như thế nào?

Một access token Bearer thông thường có thể được sử dụng bởi bất kỳ bên nào đang nắm giữ token. DPoP bổ sung bằng chứng sở hữu private key: token được Authorization Server ràng buộc với public key, và client phải tạo một proof mới cho request.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof và public JWK
    AS-->>C: Access token token_type=DPoP, key binding
    C->>RS: Authorization: DPoP access-token
    C->>RS: DPoP: proof JWT cho request hiện tại
    RS->>RS: Verify proof signature và claims
    RS->>RS: So khớp htm với HTTP method
    RS->>RS: So khớp htu với request URI
    RS->>RS: Kiểm ath, cnf.jkt, iat, jti, nonce
    RS->>RS: Xác thực access token và authorization
    RS-->>C: Cho phép hoặc từ chối
~~~

DPoP proof chứng minh client giữ private key tương ứng với public key trong proof. Authorization Server ràng buộc access token với public key đó. Khi Resource Server nhận request, nó phải xác nhận proof và access token cùng tham chiếu tới một key.

**DPoP không thay thế access token và authorization.** Một proof có chữ ký đúng vẫn không tự cấp quyền đọc đơn hàng, xóa tài khoản hoặc truy cập tenant. Resource Server vẫn phải xác minh access token, issuer, audience, scope và domain policy.

## 2. Cấu trúc DPoP proof JWT

Theo RFC 9449, DPoP proof được gửi trong HTTP header có tên **DPoP**. Giá trị header là một JWT được ký bằng private key của client.

JOSE header tối thiểu:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-coordinate-x",
    "y": "public-coordinate-y"
  }
}
~~~

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| typ | Phải là dpop+jwt |
| alg | Thuật toán chữ ký bất đối xứng được hỗ trợ và cho phép |
| jwk | Public JWK của client; không được chứa private key |

Payload của proof cho một request protected resource có dạng:

~~~json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.com/v1/orders/42",
  "iat": 1893452400,
  "ath": "base64url-sha256-of-access-token"
}
~~~

| Claim | Ý nghĩa |
|---|---|
| **jti** | ID duy nhất của proof, dùng hỗ trợ phát hiện replay |
| **htm** | HTTP method của request |
| **htu** | HTTP target URI, bỏ query và fragment |
| **iat** | Thời điểm tạo proof |
| **ath** | Hash SHA-256 của access token, được base64url encode; bắt buộc khi proof đi cùng access token tới protected resource |
| **nonce** | Nonce do Authorization Server hoặc Resource Server cung cấp, nếu server yêu cầu |

Proof phải được tạo mới cho mỗi HTTP request. Không tái sử dụng một proof JWT cho nhiều lần gọi API, kể cả khi request có cùng method và URI.

### 2.1. Access token cũng phải được ràng buộc với key

Với JWT access token, key confirmation thường được biểu diễn qua claim cnf.jkt:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "user-123",
  "scope": "orders.read",
  "cnf": {
    "jkt": "SHA-256-JWK-thumbprint"
  }
}
~~~

**jkt** là JWK SHA-256 thumbprint của public key dùng ký DPoP proof.

Resource Server phải xác nhận:

1. Proof signature hợp lệ với public JWK trong proof.
2. Public key trong proof có thumbprint khớp cnf.jkt của access token.
3. ath khớp hash của access token được gửi trong request.

Nếu dùng opaque access token, thông tin key binding có thể được cung cấp qua introspection response theo thỏa thuận và hỗ trợ của Authorization Server/Resource Server.

### 2.2. HTTP headers của protected resource request

Một request DPoP điển hình:

~~~http
GET /v1/orders/42?expand=items HTTP/1.1
Host: api.example.com
Authorization: DPoP <dpop-bound-access-token>
DPoP: <signed-dpop-proof-jwt>
~~~

Có hai header với vai trò riêng:

- Authorization dùng scheme **DPoP** và mang access token đã được ràng buộc với key.
- DPoP mang proof JWT được tạo cho request hiện tại.

Với protected resource request, chỉ gửi Bearer token và DPoP proof mà không dùng đúng scheme/contract sẽ không tạo thành một DPoP request hợp lệ.

## 3. Claim htm: ràng buộc HTTP method

**htm** là HTTP method của request mà proof được gắn vào. Resource Server phải so khớp claim này với method của HTTP request hiện tại.

Ví dụ proof:

~~~json
{
  "htm": "POST",
  "htu": "https://api.example.com/v1/orders",
  "iat": 1893452400,
  "jti": "proof-001"
}
~~~

Proof trên được tạo cho request:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.com
~~~

Nếu cùng proof được gửi cho:

~~~http
DELETE /v1/orders HTTP/1.1
Host: api.example.com
~~~

thì method không khớp. Server phải từ chối proof.

### 3.1. Cùng URI nhưng khác method vẫn là request khác

| HTTP request | htm trong proof | Kết quả so khớp |
|---|---|---|
| GET /v1/orders/42 | GET | Khớp |
| POST /v1/orders/42 | GET | Không khớp |
| PATCH /v1/orders/42 | PATCH | Khớp |
| DELETE /v1/orders/42 | PATCH | Không khớp |
| OPTIONS /v1/orders/42 | GET | Không khớp |

Một URI có thể phục vụ nhiều operations theo method. DPoP dùng htm để phân biệt những thao tác này.

### 3.2. So khớp method theo HTTP semantics

HTTP method là token có tính phân biệt chữ hoa/chữ thường theo HTTP semantics. Client thông thường gửi các method chuẩn như GET, POST, PUT, PATCH, DELETE ở dạng chữ hoa và nên ghi htm đúng với method thực tế.

Không tự chuyển một method tùy ý thành một method khác để làm proof “khớp”. Với custom HTTP method, client và server phải thống nhất method thật được gửi và kiểm so khớp đúng giá trị đó.

### 3.3. Method override có thể phá ranh giới htm

Một số ứng dụng hỗ trợ các cơ chế như:

~~~http
POST /v1/orders/42 HTTP/1.1
X-HTTP-Method-Override: DELETE
~~~

hoặc form parameter:

~~~text
_method=DELETE
~~~

Ở tầng HTTP, request vẫn là **POST**. Nếu middleware sau đó đổi method thành DELETE trước khi controller xử lý, DPoP proof chỉ ràng buộc method POST trên wire; nó không tự ký method hiệu lực được ứng dụng tạo ra sau đó.

Điều này quan trọng vì proof JWT không ký toàn bộ request body hoặc headers. Một tham số override có thể thay đổi ý nghĩa nghiệp vụ mà không làm htm thay đổi.

Với DPoP-protected APIs, cách đơn giản và dễ kiểm soát là **không sử dụng method override**. Nếu hệ thống bắt buộc có cơ chế đó, phải thiết kế một ràng buộc request bổ sung được client/server cùng hiểu; không giả định htm đã bảo vệ method sau khi middleware rewrite.

## 4. Claim htu: ràng buộc HTTP target URI

**htu** là HTTP target URI của request, nhưng **không bao gồm query string và fragment**.

Ví dụ client gọi:

~~~http
GET /v1/orders/42?expand=items&locale=vi HTTP/1.1
Host: api.example.com
~~~

Giá trị htu trong proof là:

~~~text
https://api.example.com/v1/orders/42
~~~

Không phải:

~~~text
https://api.example.com/v1/orders/42?expand=items&locale=vi
~~~

Fragment như #details cũng không được đưa vào htu. Fragment là thành phần phía client và thông thường không được gửi trong HTTP request.

### 4.1. Những phần URI được ràng buộc

Một absolute URI có thể được nhìn theo các thành phần:

~~~text
scheme://host[:port]/path?query#fragment
~~~

Đối với htu, những phần có ý nghĩa là:

- **scheme**: http hoặc https.
- **host**: hostname hoặc IP của resource server.
- **port**: port nếu cần biểu diễn theo URI.
- **path**: đường dẫn tài nguyên.

Query và fragment bị bỏ qua theo RFC 9449.

| Request URL | Giá trị htu |
|---|---|
| https://api.example.com/v1/orders/42 | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42?expand=items | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42?locale=vi | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42#details | https://api.example.com/v1/orders/42 |

Vì query bị bỏ qua, ba request đầu có cùng htu. Điều này là thiết kế của DPoP, không phải lỗi parser.

### 4.2. Khác scheme, host, port hoặc path là khác URI

Các trường hợp sau thường không khớp với proof có htu là https://api.example.com/v1/orders/42:

| Request URI | Khác biệt |
|---|---|
| http://api.example.com/v1/orders/42 | Scheme |
| https://other.example.com/v1/orders/42 | Host |
| https://api.example.com:8443/v1/orders/42 | Port |
| https://api.example.com/v2/orders/42 | Path |
| https://api.example.com/v1/orders/43 | Resource path |

Server phải so htu với URI thực tế của request sau khi áp dụng quy tắc normalization được yêu cầu.

### 4.3. Query không được ký

Vì query string bị loại khỏi htu, proof không phân biệt:

~~~text
/v1/orders/42?view=summary
/v1/orders/42?view=full
/v1/orders/42?operation=export
~~~

Nếu query chỉ điều khiển cách trình bày hoặc filter dữ liệu mà quyền truy cập đã được kiểm riêng, đây có thể là một giới hạn chấp nhận được. Nhưng nếu query parameter quyết định một hành động nhạy cảm, **không được coi DPoP htu là chữ ký bảo vệ parameter đó**.

Tương tự, DPoP cơ bản không ký request body hoặc mọi HTTP headers. Nếu một thao tác phụ thuộc dữ liệu trong body, DPoP không tự chứng minh body đó là nội dung mà client đã ký.

Với các yêu cầu integrity rộng hơn, cần một giao thức request-signing hoặc extension có hợp đồng riêng giữa client và server. Không tự thêm claim tùy ý rồi giả định mọi DPoP implementation khác sẽ hiểu giống nhau.

## 5. Chuẩn hóa URI trước khi so htu

RFC 9449 khuyến nghị Resource Server dùng:

- **Syntax-based normalization** theo RFC 3986, mục 6.2.2.
- **Scheme-based normalization** theo RFC 3986, mục 6.2.3.

Mục tiêu là tránh từ chối sai những URI tương đương về mặt cú pháp hoặc scheme.

Ví dụ các khác biệt có thể xuất hiện:

~~~text
HTTPS://API.EXAMPLE.COM:443/v1/orders/42
https://api.example.com/v1/orders/42
~~~

Scheme/host có thể được chuẩn hóa về chữ thường; default port và các dạng URI tương đương được xử lý theo quy tắc normalization phù hợp.

### 5.1. Không tự viết một phép so chuỗi tùy tiện

Một phép so chuỗi tuyệt đối có thể từ chối URI tương đương. Ngược lại, một phép chuẩn hóa quá rộng có thể làm hai resource khác nhau bị coi là một.

Những sai lầm thường gặp:

- Chuyển toàn bộ path thành chữ thường, dù path có thể phân biệt chữ hoa/chữ thường.
- Xóa mọi dấu slash cuối mà không xét semantics của route.
- Decode toàn bộ percent-encoded characters một cách tùy tiện.
- Sort hoặc loại query parameters rồi tự đưa chúng vào htu.
- Coi hai host alias khác nhau là cùng một resource mà không có policy.
- Thay scheme https thành http chỉ vì backend nhận traffic nội bộ qua HTTP.
- Bỏ port khác nhau dù đó là hai public endpoints khác nhau.

Hãy dùng URI parsing/normalization đúng chuẩn, giữ nguyên những khác biệt có ý nghĩa và bỏ query/fragment theo DPoP specification. Không dùng một hàm lowercase toàn URL làm canonicalizer.

### 5.2. Percent-encoding và path segments

Các URI có thể biểu diễn một số ký tự bằng percent-encoding. RFC 3986 quy định cách chuẩn hóa những trường hợp tương đương, bao gồm encoding của unreserved characters và xử lý dot-segments trong quá trình normalization.

Không tự decode reserved characters như dấu phân cách path chỉ vì chúng đang được percent-encoded. Cần áp dụng đúng quy tắc syntax-based normalization và kiểm thử với URI mà reverse proxy, servlet container và router thực sự xử lý.

Ví dụ, server không nên tự giả định mọi path sau khi decode đều có cùng ý nghĩa với path gốc. Những khác biệt giữa encoded slash, path traversal, duplicate slash và route normalization phải được giải quyết nhất quán ở ingress và application.

## 6. Reverse proxy: URI client thấy và URI backend thấy

Đây là một trong những nguyên nhân phổ biến khiến DPoP htu mismatch.

Giả sử client gọi public endpoint:

~~~text
https://api.example.com/v1/orders/42
~~~

Gateway chuyển tiếp tới backend:

~~~text
http://orders-service.internal:8080/orders/42
~~~

Client tạo proof với:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/v1/orders/42"
}
~~~

Nhưng Servlet backend có thể nhìn thấy:

~~~text
http://orders-service.internal:8080/orders/42
~~~

Nếu Resource Server đem URI nội bộ này so trực tiếp với htu, proof hợp lệ từ góc nhìn client sẽ bị từ chối.

### 6.1. Phải xác định public request URI đáng tin

Resource Server cần so htu với URI tương ứng của request mà client thực sự gửi tới protected resource. Trong triển khai có reverse proxy, ứng dụng phải có cách tái dựng scheme, host, port và path công khai chính xác.

Các thông tin thường liên quan:

- Forwarded header theo RFC 7239.
- X-Forwarded-Proto.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Prefix hoặc path rewrite do gateway quản lý.

Không phải tất cả proxy đều dùng cùng header hoặc cùng cách rewrite. Hãy xác định rõ public URL và backend URL trong kiến trúc.

### 6.2. Chỉ tin forwarded headers từ proxy được quản lý

Các header Forwarded/X-Forwarded-* có thể được client tự gửi nếu edge proxy không loại bỏ chúng. Nếu ứng dụng tin trực tiếp một giá trị do attacker cung cấp, attacker có thể tác động scheme/host/port/path mà server dùng để kiểm htu.

Quy tắc triển khai:

1. Edge proxy phải xóa hoặc ghi đè forwarded headers đến từ client bên ngoài.
2. Chỉ proxy/gateway được tin cậy mới được phép gửi thông tin URI forwarding.
3. Backend chỉ tin forwarded headers từ những nguồn proxy đã cấu hình.
4. Không cho client tự quyết định Host hoặc public prefix dùng trong DPoP comparison.
5. Test đường đi qua proxy thật, không chỉ gọi thẳng backend.

### 6.3. Spring hỗ trợ xử lý forwarded request

Trong Servlet stack, Spring có **ForwardedHeaderFilter**. Trong WebFlux, có **ForwardedHeaderTransformer**. Chúng có thể điều chỉnh cách ứng dụng nhìn scheme, host và request URI theo forwarded headers.

Nhưng việc bật filter/transformer **không tự làm forwarded headers trở nên đáng tin**. Proxy trust boundary phải được thiết lập trước. Nếu backend có thể truy cập trực tiếp từ Internet, không được mặc định mọi forwarded header đều đến từ gateway.

### 6.4. Path rewrite cần có hợp đồng rõ

Nếu public route là:

~~~text
/v1/orders/42
~~~

nhưng proxy rewrite thành:

~~~text
/orders/42
~~~

thì Resource Server cần biết public path tương ứng để so htu. Không thể chỉ lấy backend path rồi so với proof của client.

Có ba hướng thiết kế thường gặp:

- Proxy giữ nguyên public path khi forward.
- Backend nhận forwarded prefix/path từ proxy tin cậy và framework tái dựng public URI.
- Ứng dụng có mapping công khai được quản lý rõ ràng để chuyển backend request về URI công khai.

Dù chọn cách nào, client và server phải dùng cùng một URI representation sau normalization. Không suy ra public path từ một header tùy ý.

## 7. DPoP kiểm tra gì và không kiểm tra gì?

Khi Resource Server nhận một DPoP proof, RFC 9449 yêu cầu kiểm tra nhiều điều kiện. htm và htu chỉ là hai trong số đó.

| Kiểm tra | Mục đích |
|---|---|
| Chỉ có một DPoP header | Tránh nhiều proof mơ hồ |
| Proof là JWT hợp lệ | Đảm bảo cấu trúc và chữ ký |
| typ = dpop+jwt | Xác định loại proof |
| alg bất đối xứng được phép | Tránh none/symmetric algorithms không phù hợp |
| JWK chỉ chứa public key | Không nhận private key từ client |
| Signature hợp lệ | Chứng minh possession private key |
| htm khớp method | Ràng buộc method |
| htu khớp request URI | Ràng buộc endpoint |
| iat trong thời gian cho phép | Giới hạn tuổi proof |
| jti chưa được sử dụng | Hạn chế replay |
| nonce khớp nếu server yêu cầu | Tăng khả năng chống replay |
| ath khớp access token | Gắn proof với token đang gửi |
| cnf.jkt khớp proof key | Gắn access token với cùng public key |

### 7.1. ath không thay thế htm/htu

ath là hash của access token. Nó giúp proof được gắn với token cụ thể đang trình.

Nhưng nếu chỉ kiểm ath mà không kiểm htm/htu, proof không được ràng buộc với đúng request method và URI. RFC yêu cầu các kiểm tra này cùng được thực hiện.

### 7.2. jti và replay detection

Proof có jti duy nhất và iat nằm trong một cửa sổ thời gian ngắn. Server có thể lưu jti đã dùng để ngăn một proof bị gửi lại nhiều lần.

Một proof được tạo cho GET /orders/42 vẫn có thể bị replay lại đúng endpoint và method nếu attacker đánh cắp toàn bộ proof trong thời gian còn hợp lệ. htm/htu ngăn việc chuyển proof sang endpoint/method khác; **jti replay cache và time window** giúp ngăn dùng lại proof tại cùng endpoint.

Với nhiều Resource Server instances, replay cache cục bộ của từng node không bảo đảm phát hiện proof được gửi lần đầu tới node A rồi lần hai tới node B. Nếu yêu cầu replay prevention trên toàn cụm, cần cache/state dùng chung hoặc cơ chế đồng bộ phù hợp.

Spring Security cung cấp **DPoPProofReplayValidator** với cache để kiểm tra jti đã dùng và thời gian iat. Cần cấu hình cache/lifecycle theo kiến trúc. Một cache in-memory trên một instance không tự bảo vệ các replicas khác.

### 7.3. Nonce

Authorization Server hoặc Resource Server có thể trả header **DPoP-Nonce**. Client phải đưa nonce gần đây đó vào claim nonce trong proof kế tiếp.

Nonce giúp server yêu cầu proof gắn với một challenge gần đây, tăng khả năng chống replay trong các bối cảnh phù hợp. Client không tự chọn nonce có giá trị bảo mật thay cho server.

## 8. Ví dụ so khớp htm và htu

Giả sử client gọi:

~~~http
PATCH /v1/orders/42?notify=true HTTP/1.1
Host: api.example.com
Authorization: DPoP <access-token>
DPoP: <proof>
~~~

Payload proof đã ký:

~~~json
{
  "jti": "a7f2f4c9-0d20-4d3f-a8e3-4f5e6d7c8b9a",
  "htm": "PATCH",
  "htu": "https://api.example.com/v1/orders/42",
  "iat": 1893452400,
  "ath": "base64url-sha256-of-access-token"
}
~~~

Server thực hiện:

1. Method thực tế là PATCH, htm là PATCH: khớp.
2. URI công khai sau normalization là https://api.example.com/v1/orders/42: khớp.
3. Query notify=true bị bỏ qua trong htu comparison theo RFC.
4. Proof signature, key binding, ath, iat, jti và nonce được kiểm theo policy.
5. Access token được xác minh.
6. Authorization kiểm scope và quyền sửa đơn hàng.

Nếu request thay thành:

~~~http
DELETE /v1/orders/42?notify=true HTTP/1.1
Host: api.example.com
~~~

thì htm không khớp. Nếu request thay thành:

~~~http
PATCH /v1/orders/43?notify=true HTTP/1.1
Host: api.example.com
~~~

thì htu không khớp.

Nếu query đổi thành notify=false nhưng method/path giữ nguyên, htm/htu vẫn khớp. Đây là giới hạn được thiết kế của DPoP; nếu query điều khiển hành động nhạy cảm, cần bảo vệ semantics đó ở tầng khác.

## 9. Spring Security hỗ trợ DPoP như thế nào?

Spring Security có các thành phần DPoP ở những release line hiện đại:

- **DPoPAuthenticationToken**: chứa access token, proof, method và resource URI.
- **DPoPAuthenticationProvider**: xác thực DPoP-bound access token.
- **DPoPProofJwtDecoderFactory**: tạo decoder cho DPoP proof.
- **DPoPAuthenticationConverter**: trích DPoP access token/proof từ Servlet request.
- **DPoPAuthenticationEntryPoint**: tạo challenge/error cho DPoP.
- **DPoPProofReplayValidator**: kiểm tra jti/iat bằng cache.

Một khác biệt về phiên bản cần nhớ:

- Một số thành phần DPoP như DPoPAuthenticationProvider và DPoPAuthenticationToken có từ Spring Security 6.5.
- **DPoPConfigurer** của OAuth2 Resource Server DSL được bổ sung từ Spring Security 7.1.
- DPoPProofReplayValidator có từ Spring Security 6.5.12.

Không chép cấu hình DSL của Spring Security 7.1 vào dự án 6.5 mà không kiểm API/version.

### 9.1. Cấu hình Servlet Resource Server với DPoP

Ví dụ cho Spring Security 7.1 trở lên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DPoPSecurityConfiguration {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Ví dụ này giả định ứng dụng đã cấu hình JwtDecoder/issuer/audience validators và Authorization Server phát hành **DPoP-bound access tokens**. Với opaque token, dùng introspection configuration tương ứng để cung cấp thông tin public key binding.

DPoP configurer của Servlet có thể tùy chỉnh request matcher, authentication converter, success handler và failure handler. Mặc định converter tạo DPoPAuthenticationToken từ request; provider xác minh proof và access token.

### 9.2. Spring Security 6.5

Spring Security 6.5 có một số building blocks DPoP, nhưng DSL .dPoP(...) của OAuth2ResourceServerConfigurer được ghi nhận từ 7.1. Nếu dùng 6.5, kiểm tra đúng API/Javadoc của minor release và cách wiring provider/converter/entry point. Không tự ghép class từ 6.5 với configurer chỉ có trong 7.1.

### 9.3. WebFlux

Cấu hình .dPoP(...) được tài liệu hóa ở đây thuộc **Servlet HttpSecurity**. WebFlux dùng ServerHttpSecurity và reactive authentication managers; không chép nguyên DSL Servlet vào SecurityWebFilterChain.

Nếu Resource Server dùng WebFlux cần DPoP, hãy xác nhận hỗ trợ chính thức của release đang dùng hoặc thiết kế reactive authentication integration tương ứng. Không dùng blocking Servlet DPoPAuthenticationProvider trong Reactor event loop và không tự bỏ qua htm/htu vì reactive stack.

## 10. URI và reverse proxy trong Spring: checklist cấu hình

Với Spring MVC sau reverse proxy, kiểm tra:

- Ứng dụng nhận được scheme công khai là https khi client gọi HTTPS.
- Host/port là public host/port được proxy xác lập.
- Path nhìn thấy bởi DPoP converter là public path tương ứng.
- ForwardedHeaderFilter chỉ xử lý forwarded headers từ trusted proxy.
- Edge proxy xóa forwarded headers do client tự gửi.
- Host header không được lấy từ nguồn tùy ý.
- Không có path rewrite chưa được đưa vào mapping.
- URI normalization áp dụng đúng RFC 3986.

Với WebFlux, các thành phần forwarded-header xử lý request có API khác; kiểm tra đúng cách cấu hình WebFlux thay vì dùng Servlet filter.

### 10.1. Ví dụ public và backend URI

| Thuộc tính | Client nhìn thấy | Backend có thể nhìn thấy |
|---|---|---|
| Scheme | https | http |
| Host | api.example.com | orders-service.internal |
| Port | 443 | 8080 |
| Path | /v1/orders/42 | /orders/42 |
| Query | ?expand=items | Có thể được forward hoặc rewrite |

Proof được tạo theo public URI. Resource Server cần một request view đáng tin cậy tương ứng public URI để so htu.

Nếu proxy đổi path, phải giữ thông tin public prefix hoặc có mapping rõ. Nếu backend không thể tái dựng URI client đã gọi một cách tin cậy, hãy điều chỉnh gateway/routing architecture trước khi bật DPoP.

## 11. Các tình huống dễ gây mismatch

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mọi proof đều báo htu mismatch sau ingress | Backend thấy http/internal host | Cấu hình trusted forwarded URI |
| Chỉ sai khi đi qua gateway | Proxy rewrite path hoặc prefix | Đồng bộ public path mapping |
| Chỉ sai trên HTTPS termination | Backend nhìn scheme http | Tin forwarded proto từ proxy được quản lý |
| Một số hostname alias thành công | Client và server chọn host khác nhau | Chuẩn hóa public hostname |
| Default port tạo mismatch | URI được biểu diễn khác nhau | Áp RFC 3986 scheme normalization |
| Path có percent-encoding bị từ chối | Client/server normalize khác nhau | Dùng URI parser và quy tắc chuẩn hóa tương thích |
| Request POST bị từ chối sau middleware | Method override làm đổi method | Tắt override trên DPoP route hoặc có binding bổ sung |
| Proof dùng được với nhiều query | Query bị loại khỏi htu | Không coi query là phần được DPoP ký |
| Proof bị từ chối ở node khác | Replay cache chỉ cục bộ hoặc clock khác nhau | Shared replay state và đồng bộ clock |
| Proof hợp lệ nhưng token bị từ chối | ath hoặc cnf.jkt không khớp | Kiểm access token/key binding |

## 12. Kiểm thử htm/htu trong Resource Server

Không chỉ test một request thành công. Cần có positive và negative tests cho từng thành phần binding.

### 12.1. Ma trận htm

| Request method | htm trong proof | Kết quả mong đợi |
|---|---|---|
| GET | GET | Khớp |
| POST | POST | Khớp |
| GET | POST | Từ chối |
| DELETE | PATCH | Từ chối |
| OPTIONS | GET | Từ chối |

Kiểm cả custom methods nếu ứng dụng có sử dụng.

### 12.2. Ma trận htu

| Request URI | htu trong proof | Kết quả mong đợi |
|---|---|---|
| https://api.example.com/v1/orders/42 | Cùng URI | Khớp |
| https://api.example.com/v1/orders/43 | URI khác path | Từ chối |
| https://other.example.com/v1/orders/42 | Host khác | Từ chối |
| http://api.example.com/v1/orders/42 | Scheme khác | Từ chối |
| https://api.example.com:8443/v1/orders/42 | Port khác | Từ chối |
| Cùng URI, query khác | Cùng htu sau khi bỏ query | htu vẫn khớp |
| URI tương đương theo RFC 3986 normalization | URI tương đương | Khớp theo quy tắc normalization |

Các test URI tương đương cần được xây theo RFC 3986, không tự mở rộng phép chuẩn hóa vượt quá tiêu chuẩn.

### 12.3. Test qua proxy

Dùng test environment có reverse proxy/gateway:

1. Client tạo proof cho public URI.
2. Proxy terminate TLS và forward tới backend.
3. Backend nhận forwarded metadata từ proxy tin cậy.
4. Resource Server dựng URI phù hợp.
5. Proof hợp lệ được chấp nhận.
6. Gửi cùng request với forwarded host/proto bị giả mạo từ client; edge phải xóa/ghi đè và không để attacker điều khiển htu comparison.
7. Kiểm path rewrite và public prefix.

Test gọi thẳng controller/backend không đủ để chứng minh URI reconstruction hoạt động đúng trong production.

### 12.4. Test giới hạn query và body

Tạo hai request cùng method/path nhưng query khác nhau. DPoP htm/htu vẫn có thể khớp vì query bị loại.

Điều này không có nghĩa hai request được phép thực hiện cùng business action. Test cần chứng minh authorization/domain layer vẫn kiểm các query/body parameters quan trọng.

### 12.5. Test replay

- Gửi proof với jti mới: có thể được chấp nhận.
- Gửi lại cùng proof trong thời gian hợp lệ: phải bị phát hiện theo replay policy.
- Gửi cùng proof tới một node khác: kiểm shared replay cache nếu hệ thống nhiều instances.
- Gửi proof có iat quá cũ hoặc ở tương lai ngoài clock policy: từ chối.
- Gửi proof thiếu nonce khi server yêu cầu nonce: từ chối và xử lý challenge phù hợp.

### 12.6. Test access token binding

Ngoài htm/htu, cần kiểm:

- ath tính trên đúng access token được gửi.
- cnf.jkt khớp thumbprint của proof public key.
- Token không bị dùng bằng Bearer scheme nếu token được cấp dưới dạng DPoP-bound.
- Proof ký bằng private key khác bị từ chối.
- Proof header chứa private JWK material bị từ chối.
- typ hoặc alg không đúng policy bị từ chối.

Dùng key pair test và access token test có binding thật; không chỉ inject một Authentication giả rồi kết luận DPoP đã được xác minh.

## 13. Những anti-pattern cần tránh

**Chỉ kiểm chữ ký proof.** Chữ ký hợp lệ chưa đủ; phải so htm, htu, iat, jti, ath, key binding và nonce khi cần.

**So htu với backend URL nội bộ.** Client ký public URL, backend lại so với hostname/port/path sau proxy.

**Tin mọi X-Forwarded-* header.** Client có thể giả mạo nếu edge không xóa và backend không giới hạn proxy trust.

**Lowercase toàn bộ URI.** Path có thể phân biệt chữ hoa/chữ thường; không dùng phép chuẩn hóa tùy tiện.

**Đưa query vào htu.** RFC 9449 loại query và fragment khỏi htu.

**Cho rằng DPoP ký request body.** DPoP cơ bản không ký body hoặc mọi headers.

**Dùng method override trên protected route.** htm ràng buộc HTTP method trên wire, không tự ràng buộc method được rewrite sau đó.

**Tái sử dụng proof.** Mỗi HTTP request cần proof riêng và jti duy nhất.

**Chỉ có replay cache cục bộ trong hệ thống nhiều nodes.** Một proof có thể được replay sang node khác nếu không có shared state phù hợp.

**Coi DPoP là authorization.** Scope, audience, tenant, role và quyền trên tài nguyên vẫn cần được kiểm.

**Dùng DPoP proof như token truy cập độc lập.** Proof chứng minh possession key; access token vẫn quyết định quyền OAuth.

## 14. Quy trình triển khai thực tế

**Bước 1 — Xác nhận Authorization Server hỗ trợ DPoP.** Token response cần báo token_type DPoP và access token được ràng buộc với public key.

**Bước 2 — Xác định URI công khai.** Ghi rõ scheme, host, port và path mà client nhìn thấy cho từng route.

**Bước 3 — Kiểm tra reverse proxy.** Xác định TLS termination, host forwarding, prefix/path rewrite và proxy trust boundary.

**Bước 4 — Cấu hình Resource Server.** Dùng DPoP-aware converter/provider/configurer đúng Spring Security version; xác minh access token và proof.

**Bước 5 — Kiểm htm.** Đảm bảo method so khớp với HTTP method thực tế, không bị method override làm thay đổi semantics sau bước DPoP.

**Bước 6 — Kiểm htu.** Bỏ query/fragment, áp RFC 3986 syntax-based và scheme-based normalization, so với public request URI đáng tin cậy.

**Bước 7 — Kiểm key/token binding.** Verify proof signature, public JWK, ath và cnf.jkt.

**Bước 8 — Thiết kế replay/nonce.** Giới hạn tuổi proof, jti uniqueness, cache chia sẻ khi cần và nonce policy.

**Bước 9 — Giữ authorization độc lập.** Kiểm issuer, audience, scopes, tenant, ownership và domain policy.

**Bước 10 — Test cả ingress.** Kiểm method mismatch, path/host/scheme mismatch, forwarded header spoofing, query/body boundary và replay qua nhiều instances.

## 15. Câu hỏi tự kiểm tra

**1. htm là gì?**

Là HTTP method của request mà DPoP proof được gắn vào. Resource Server phải so khớp nó với method hiện tại.

**2. htu có chứa query string không?**

Không. RFC 9449 yêu cầu bỏ query và fragment khi tạo/so sánh htu.

**3. Một proof cho GET /orders/42 có thể dùng cho DELETE /orders/42 không?**

Không. htm khác nhau.

**4. Một proof cho /orders/42 có thể dùng khi path đổi thành /orders/43 không?**

Không. htu khác nhau.

**5. Nếu query thay đổi nhưng method/path không đổi, htu có thay đổi không?**

Không. Query bị loại khỏi htu. Các tham số quan trọng vẫn phải được kiểm trong authorization/domain logic.

**6. DPoP có ký request body không?**

Không trong cơ chế cơ bản. Nó ràng buộc method và URI cùng với access token/key binding, không phải toàn bộ HTTP message.

**7. Vì sao reverse proxy có thể gây htu mismatch?**

Vì client dùng public scheme/host/path, còn backend có thể nhìn thấy internal scheme/host/path sau TLS termination hoặc rewrite.

**8. Có nên tin X-Forwarded-Host do request gửi tới không?**

Không mặc định. Chỉ tin forwarded metadata do proxy được quản lý xác lập, sau khi edge loại bỏ giá trị client tự gửi.

**9. Spring Security DPoP DSL có từ phiên bản nào?**

DPoPAuthenticationProvider có từ 6.5; DPoPConfigurer của OAuth2 Resource Server DSL có từ 7.1. Phải đối chiếu đúng release line.

**10. DPoP có thay thế scope/role authorization không?**

Không. Nó chứng minh possession key và ràng buộc proof với request/token; quyền truy cập vẫn do access token và authorization policy quyết định.

## Kết luận

**htm và htu là hai claim ràng buộc DPoP proof với HTTP request cụ thể.** htm phải khớp method thực tế; htu phải khớp target URI sau khi bỏ query/fragment và áp dụng URI normalization theo RFC 3986.

Sự khác biệt giữa URL client nhìn thấy và URL backend nhìn thấy sau reverse proxy là một ranh giới triển khai quan trọng. Resource Server phải dựng URI công khai từ forwarded metadata chỉ được tin cậy từ proxy được quản lý. Nếu method bị override hoặc query/body chứa ý nghĩa nghiệp vụ nhạy cảm, không được giả định htm/htu đã ký toàn bộ request.

Trong Spring Security, cần dùng đúng DPoP components và API theo version; đồng thời kiểm proof signature, jti/iat, ath, cnf.jkt và nonce khi cần. **DPoP giúp chống việc dùng access token bị đánh cắp bởi bên không giữ private key, nhưng không thay thế authorization, replay protection hoặc request integrity cho body/query.**

### Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP), Section 4.2–4.3](https://www.rfc-editor.org/rfc/rfc9449.html)
- [RFC 9449 — Public Key Confirmation and DPoP-Protected Resource Requests](https://www.rfc-editor.org/rfc/rfc9449.html#section-6)
- [RFC 9449 — DPoP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc9449.html#section-7.1)
- [RFC 9449 — DPoP Proof Replay](https://www.rfc-editor.org/rfc/rfc9449.html#section-11.1)
- [RFC 3986 — URI Generic Syntax, Section 6.2](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html)
- [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html)
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html)
- [Spring Security API — DPoPProofJwtDecoderFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html)
- [Spring Security API — DPoPProofReplayValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html)
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
