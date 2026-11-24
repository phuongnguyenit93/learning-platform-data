# Proxy và gateway có thay đổi audience không?

**Trả lời ngắn:** Một **reverse proxy**, **load balancer** hay **API gateway** chỉ chuyển tiếp HTTP request **không tự làm thay đổi audience** của access token. Claim `aud` là một phần dữ liệu mà Authorization Server (AS) đã phát hành; với JWT access token được ký, việc sửa `aud` trực tiếp sẽ làm chữ ký không còn hợp lệ. Tuy nhiên, gateway **có thể tham gia một luồng cấp token mới** (chẳng hạn token exchange được AS hỗ trợ), hoặc chấm dứt việc sử dụng token bên ngoài và chuyển sang bằng chứng nội bộ khác. Khi đó **token mới hoặc bằng chứng mới** có thể dành cho một audience khác, chứ không phải token cũ tự biến đổi khi qua proxy.

Ví dụ: Trình duyệt gọi `https://api.example.test/orders/42` qua gateway; gateway chuyển request đến `http://orders-service:8080/orders/42`. Nếu access token chứa `"aud": "orders-api"`, việc đổi hostname và cổng mạng **không** đổi claim thành `orders-service`. Order API phải kiểm token theo audience **đã được AS và hệ thống thống nhất**, không đoán audience từ hostname nội bộ mà nó nhìn thấy.

Bài này thuộc chương **Audience** trong module **Security Token Security Fundamentals**. Ta sẽ xem vì sao điều đó quan trọng với JWT, opaque token, OAuth 2.0/OIDC, scope, issuer, kiểm soát quyền ở từng API, token exchange và phòng chống token bị dùng nhầm dịch vụ.

## 1. Tách ba thứ thường bị gọi chung là “đích”

Khi nói “token đi qua gateway đến API B”, cần phân biệt:

| Khái niệm | Nó mô tả gì? | Ví dụ |
|---|---|---|
| **HTTP destination** | Host, path, port thực tế của request ở mỗi chặng mạng | `api.example.test` → `orders-service:8080` |
| **OAuth resource identifier / audience** | Resource server logic mà token được phát hành để phục vụ; định danh theo hợp đồng với AS | `orders-api` hoặc `https://api.example.test/orders` |
| **Backend service identity** | Danh tính workload/microservice nhận kết nối hoặc gọi lẫn nhau | `spiffe://example.test/ns/prod/sa/orders` |

Ba giá trị này **có thể trùng nhau trong một thiết kế**, nhưng không bắt buộc. Sự khác nhau không phải lỗi; lỗi xảy ra khi bên nhận token **bỏ qua hợp đồng audience** và tự suy từ `Host` hoặc từ tên container.

Một access token minh họa:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "orders-api",
  "client_id": "sales-web",
  "scope": "orders:read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Token này mô tả:

- `iss`: bên phát hành token; phải trùng một issuer được resource server tin cậy.
- `aud`: bên nhận dự kiến, ở đây là **Order API** theo định danh logic `orders-api`.
- `sub`: chủ thể được token mô tả theo profile phát hành; không tự chứng minh HTTP request hiện tại do An gửi.
- `client_id`: client được cấp token, khi profile có và bảo đảm claim này.
- `scope`: quyền truy cập được cấp cho token; `orders:read` không mặc nhiên cho xem mọi đơn hàng.

Gateway có thể thay hostname, path, thêm request ID hoặc kết thúc TLS mà **không sửa các claim kể trên**. Muốn quyền hợp lệ, Order API vẫn phải xác minh token rồi kiểm scope, tenant, quan hệ sở hữu đơn hàng và chính sách nghiệp vụ.

## 2. JWT đã ký không thể bị “rewrite aud” mà vẫn giữ chữ ký cũ

Với access token JWT ở dạng **JWS Compact Serialization**, một token ký phổ biến có ba phần:

~~~text
BASE64URL(protected-header).BASE64URL(claims-payload).BASE64URL(signature)
~~~

Chữ ký bảo vệ nội dung header và payload đã được ký. Nếu gateway giải mã Base64URL, thay:

~~~json
{"aud": "gateway-api"}
~~~

bằng:

~~~json
{"aud": "orders-api"}
~~~

rồi giữ phần signature cũ, resource server phải **từ chối vì chữ ký không hợp lệ**. Nếu gateway ký lại token bằng một khóa riêng, nó đã tạo **một token mới với nguồn phát hành/trust contract khác**. Việc đó chỉ an toàn khi được thiết kế như một cơ chế phát hành token/bằng chứng được ủy quyền: có issuer và khóa được tin, audience, subject/actor, scope, thời hạn, chính sách giới hạn và khả năng audit rõ ràng. Gateway không được tự suy rằng mình có quyền nâng scope hay giả danh người dùng.

**Không phải mọi JWT đều là JWS ba phần**: JWT cũng có thể dùng JWE để mã hóa. Với JWE, gateway càng không thể tự diễn giải hay sửa nội dung nếu không có quyền giải mã; dù có giải mã được, quy tắc về tính toàn vẹn và cấp lại token vẫn phải được tuân thủ.

Với **opaque access token**, chuỗi token cũng không thay đổi ý nghĩa chỉ vì đi qua proxy. Chính AS hoặc hệ thống introspection quyết định token có còn `active`, dành cho resource nào và có scope gì. Gateway không thể tự thay đổi binding của một opaque token bằng cách sửa header HTTP.

### Đổi `Host` không đồng nghĩa đổi `aud`

Ví dụ cùng một request trên hai chặng:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...redacted...
~~~

Sau khi gateway route vào mạng nội bộ:

~~~http
GET /orders/42 HTTP/1.1
Host: orders-service:8080
Authorization: Bearer eyJ...redacted...
X-Forwarded-Host: api.example.test
X-Forwarded-Proto: https
~~~

Đây là ví dụ **token relay**: byte của token được giữ nguyên, audience giữ nguyên. `X-Forwarded-Host` và `X-Forwarded-Proto` là metadata về đường đi HTTP, **không phải claim JWT** và không phải bằng chứng phân quyền. Các header forwarded có thể bị giả mạo nếu gateway không loại bỏ giá trị đến từ client và backend không giới hạn nguồn được tin.

## 3. Bốn mô hình gateway thường gặp

| Mô hình | Gateway làm gì với token bên ngoài? | Backend kiểm gì? | Audience có đổi không? |
|---|---|---|---|
| **A. Proxy thuần / token relay** | Chuyển tiếp nguyên access token đến resource API | API tự xác minh issuer, audience, thời hạn, scope và quyền dữ liệu | **Không** |
| **B. Gateway kiểm rồi relay** | Gateway kiểm sơ bộ token/route, sau đó chuyển nguyên token | Backend vẫn kiểm token dành cho mình hoặc thực thi trust contract được bảo vệ | **Không** |
| **C. Gateway chấm dứt token bên ngoài** | Gateway kiểm token rồi chuyển **ngữ cảnh nội bộ có bảo vệ** hoặc một token nội bộ do issuer được tin phát hành | Backend xác minh bằng chứng nội bộ, danh tính dịch vụ và quyền nghiệp vụ | Token bên ngoài **không bị sửa**; bằng chứng **mới** có thể có audience riêng |
| **D. Token exchange / phát hành lại** | Gateway hoặc service xin AS một access token **mới** cho backend | Backend xác minh token mới dành cho chính mình | **Có thể khác** ở **token mới**, không phải token cũ |

Không có một mô hình duy nhất đúng cho mọi hệ thống. Điều quan trọng là biết **thành phần nào là resource server**, token hoặc bằng chứng nào được chấp nhận ở mỗi hop, và **ai thực thi quyền đối tượng**.

### Mô hình A: reverse proxy chỉ route

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant C as Web client
    participant AS as Authorization Server
    participant G as Gateway / Reverse proxy
    participant O as Order API
    U->>C: Yêu cầu xem đơn hàng
    C->>AS: Xin token cho orders-api
    AS-->>C: Access token aud=orders-api
    C->>G: GET /orders/42 + bearer token
    G->>O: Forward request và token không đổi
    O->>O: Xác minh iss, aud, exp và scope
    O->>O: Kiểm người gọi được xem order 42
    O-->>G: 200 hoặc từ chối
    G-->>C: Chuyển phản hồi
~~~

Một đặc điểm của mô hình này là **Order API vẫn là resource server dùng access token**. Gateway có thể triển khai TLS termination, rate limiting, WAF, routing hoặc xác minh sơ bộ, nhưng nó không tự làm `aud` chuyển thành địa chỉ của backend.

### Mô hình B: gateway kiểm token trước, backend vẫn có ranh giới riêng

Gateway có thể từ chối token sai issuer, hết hạn hoặc không có scope chung **trước khi** request đến API. Điều đó hữu ích nhưng không đủ khi backend có nhiều cách được gọi trực tiếp, hoặc cần kiểm chủ sở hữu đơn hàng:

~~~text
Gateway:
  validate token for a configured protected resource
  enforce route-level policy
  forward trusted request

Order API:
  validate expected token/proof for its own boundary
  enforce order:read and ownership/tenant policy
~~~

Nếu gateway và backend đều kiểm **cùng access token**, chúng phải thống nhất audience nào được cấp cho resource API và các token profile liên quan. Không nên để gateway nhận `aud=api-gateway` rồi backend mặc nhiên nhận mọi token đó như token dành cho Order API chỉ vì gateway đã cho đi qua.

### Mô hình C: gateway là nơi sử dụng token bên ngoài

Gateway có thể là **resource server ở ranh giới public**, nhận access token `aud=api-gateway` và **không relay** access token đó tới backend. Sau khi xác minh, gateway giao tiếp với backend bằng một cơ chế tin cậy riêng, chẳng hạn:

- Kết nối mTLS xác định được danh tính gateway và truyền ngữ cảnh người dùng đã xác thực bằng một **assertion có chữ ký**, giới hạn audience/TTL.
- Gateway xin token nội bộ **dành riêng cho Order API** từ một issuer mà backend tin cậy.
- Service mesh hoặc gateway cung cấp **identity và authorization context** theo một cơ chế đã được thiết kế và bảo vệ đầu cuối.

Ở backend, một assertion có `aud=orders-api` vẫn phải được kiểm **issuer, chữ ký, thời hạn, subject/actor và policy**. Nếu chỉ gửi `X-User-Id: user:an` bằng HTTP thông thường, attacker có thể tự khai người dùng khi tìm được đường gọi trực tiếp. mTLS **chứng minh kết nối từ gateway được cấp quyền**, nhưng không tự xác nhận header tùy ý đến từ user/đã được cấp quyền đối tượng. Gateway phải **xóa** các header bảo mật do client gửi trước khi tự thêm, và backend phải không thể bị truy cập qua đường vòng không được bảo vệ.

**Phân biệt:** Đây là việc **đổi cơ chế tin cậy tại boundary**, không phải gateway tự sửa claim `aud` của JWT bên ngoài.

### Mô hình D: gateway hoặc service xin token downstream

Khi token bên ngoài có audience của gateway/API A nhưng backend B cần token khác, **OAuth 2.0 Token Exchange (RFC 8693)** là một lựa chọn nếu AS hỗ trợ. Client/service nộp subject token cùng thông tin resource/audience và chính sách áp dụng để xin token mới. AS quyết định có cho phép việc đại diện, phạm vi quyền và đích nhận hay không:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway / Report API
    participant AS as Authorization Server
    participant B as Order API
    C->>G: Access token aud=report-api
    G->>G: Xác minh token và quyền tại G
    G->>AS: Token exchange xin token dành cho orders-api
    AS->>AS: Kiểm grant, client/actor, scope, audience và chính sách
    AS-->>G: Access token MỚI aud=orders-api, scope được cấp
    G->>B: Gọi với token MỚI
    B->>B: Xác minh token, aud, scope và quyền trên order
    B-->>G: Kết quả được phép hoặc từ chối
~~~

Token mới có thể giữ người dùng ở `sub` và biểu diễn actor qua `act` theo profile token exchange, hoặc đại diện cho chính service trong mô hình `client_credentials`. **Không được coi mọi token exchange là tự động an toàn hoặc tự động downscope**: AS phải thực thi chính sách không cho quyền tăng vượt grant/subject/client/actor được phép, còn backend kiểm quyền trên tài nguyên.

## 4. Audience phải theo resource server logic, không theo hostname tình cờ

Trong kiến trúc thực tế:

~~~text
Public URL:
  https://api.example.test/orders/42

API gateway route:
  /orders/**  ->  http://orders-service.default.svc:8080/**

AS + Order API contract:
  issuer   = https://login.example.test
  audience = orders-api
~~~

Với token `aud=orders-api`, Order API có thể chấp nhận dù request URL nội bộ khác public URL, miễn các điều kiện token và quyền khác đạt. Nếu AS định nghĩa audience là URI `https://api.example.test/orders` thì backend phải so sánh với **URI đó**, không tự đổi thành `http://orders-service...`. Cả hai cách đặt tên đều có thể được lựa chọn theo hợp đồng/profile; không nên trộn các quy tắc trong cùng hệ thống.

### Điều gì không được dùng để suy audience?

Không tự tính expected audience từ:

- Header `Host` do client gửi; trong nhiều kiến trúc nó có thể bị thay đổi bởi proxy.
- `X-Forwarded-Host`, `Forwarded`, `X-Original-URL` hay header tự khai không được kiểm nguồn.
- Tên service discovery, tên pod, hostname nội bộ hay cổng lắng nghe.
- Chuỗi path hoặc giá trị query do attacker điều khiển.
- Claim `aud` của token **chưa được xác minh**; không dùng giá trị do token tự khai để cấu hình tiêu chí kiểm của chính nó.

Thay vào đó, resource server dùng **audience identifier được cấu hình đáng tin cậy** hoặc quy tắc ánh xạ được kiểm soát, nhất quán với AS. Việc chọn validator theo route phải lấy từ cấu hình policy của hệ thống, không để input không đáng tin tự quyết định mình cần được kiểm theo audience nào.

### Resource indicators khi xin token

**RFC 8707 (Resource Indicators for OAuth 2.0)** cho phép client chỉ định resource mong muốn bằng tham số `resource` khi giao tiếp với AS theo các luồng được hỗ trợ:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic <client-authentication-redacted>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders%3Aread&
resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

Đây là **yêu cầu**, không phải quyền tự cấp; AS vẫn xác thực client, kiểm grant, resource được phép và scope, rồi quyết định phát hành. Quan hệ giữa resource URI và `aud` phụ thuộc profile và cấu hình của AS; với profile có quy định cụ thể, phải tuân thủ quy định đó. Backend chỉ chấp nhận audience **thực tế trong token đã xác minh** theo hợp đồng của mình.

## 5. Token relay, token exchange và token nội bộ: chọn cách nào?

| Điều kiện hệ thống | Hướng thường phù hợp | Lưu ý |
|---|---|---|
| Gateway chỉ reverse proxy, backend là RS trực tiếp | **Relay token dành cho backend** | Backend kiểm `aud` của chính mình, scope và quyền đối tượng |
| Gateway xác minh để lọc request và backend cũng nhận token | **Kiểm lặp theo từng boundary cần bảo vệ** | Không cho backend dựa mù vào kết luận gateway; chuẩn hóa validator |
| Token ngoài dành cho gateway, backend không nhận trực tiếp | **Chấm dứt external token + bằng chứng nội bộ đáng tin** | Backend vẫn cần nhận dạng caller và kiểm quyền, chống đường vòng |
| Service A gọi B thay mặt người dùng nhưng token chỉ dành cho A | **Token exchange hoặc cơ chế phát hành downstream được AS hỗ trợ** | AS kiểm delegation/actor/scope; token mới dành cho B |
| Service batch gọi B bằng quyền của chính mình | **Client credentials** với audience B | Không giả định có người dùng cuối; policy riêng cho service |
| AS cấp token cho nhóm API chung có cùng audience logic | **Shared audience có chủ đích** | Phạm vi dùng token rộng hơn; phải kiểm quyền riêng ở mỗi API |

**Không chọn cách giải quyết bằng việc bỏ kiểm audience ở backend** chỉ để “hệ thống chạy được”. Nếu gateway và backend chưa thống nhất ranh giới token, cần làm rõ ai là RS, token được cấp cho ai và cơ chế bằng chứng cho từng hop.

## 6. Một token có nhiều audience có giải quyết được mọi thứ không?

Theo RFC 7519, `aud` có thể là một JSON string hoặc array of strings:

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "report-api"]}
~~~

Một resource server được cấu hình là `orders-api` có thể chấp nhận token có `aud` dạng mảng chứa đúng `orders-api` **nếu token profile và policy cho phép**. Nhưng token đa audience không phải lời giải mặc định cho mọi call giữa các microservice:

1. **Tăng phạm vi token có thể bị dùng nếu rò rỉ:** một bearer token hợp lệ ở nhiều service sẽ có thêm đích để kẻ cắp thử sử dụng.
2. **Không giải quyết delegation:** service A có được hành động thay user ở B hay không vẫn là quyết định chính sách.
3. **Không thay thế scope:** `orders:read` không cho phép `payments:write`, và không cấp quyền trên từng bản ghi.
4. **Không thay thế xác thực người gửi:** với bearer token, `client_id` và `sub` trong claims không chứng minh tiến trình hiện cầm token là bên hợp pháp.

Khi có thể, ưu tiên phát hành token với **audience hẹp theo resource server** và **scope tối thiểu**. Chỉ dùng audience chung hoặc đa audience khi đã xác định rõ trust boundary và tác động của việc token bị đánh cắp.

## 7. Nếu gateway nhận OIDC ID token thì sao?

**OIDC ID token** dành cho **client (relying party)**, thường có `aud` là `client_id` của ứng dụng đăng nhập. Một ID token như:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "sales-web",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

không phải access token cho Order API. Việc nó có chữ ký hợp lệ của cùng AS và gateway đã xác thực người dùng **không biến nó thành access token**. Gateway phải dùng ID token cho mục đích OIDC tại client, còn để gọi API cần **access token hoặc bằng chứng nội bộ phù hợp** được resource server chấp nhận.

Đối với **JWT access token theo RFC 9068**, có những yêu cầu profile như token type `at+jwt` và các claims OAuth; resource server cần kiểm profile được hỗ trợ để giảm **token confusion**. Không chỉ kiểm chữ ký rồi đọc `sub`, cũng không dựa độc nhất vào `typ` để bỏ qua issuer/audience/hiệu lực.

## 8. Opaque token và introspection phía gateway/backend

Một opaque access token không thể tự parse ra `aud` bằng cách decode Base64URL. Gateway hoặc backend có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** qua kênh tin cậy:

~~~json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": ["orders-api"],
  "client_id": "sales-web",
  "scope": "orders:read",
  "exp": 1800000900
}
~~~

Các điều kiện vẫn giống về bản chất: xác định AS đáng tin, token đang hoạt động, audience/mục đích dành cho API, scope và quyền đối tượng. **Gateway gọi introspection không tự thay đổi token**. Một AS có thể giới hạn phản hồi introspection theo resource server được phép hỏi, nhưng API không nên đoán điều đó nếu không có hợp đồng bảo đảm rõ.

Nếu phản hồi không có `aud` hoặc một binding tương đương đáng tin, backend phải biết AS và cơ chế bảo vệ của hệ thống **thực sự ràng buộc token vào resource nào**. Khi không chứng minh được token dành cho mình, hãy **fail closed**. Cache introspection nên có thời hạn phù hợp vì việc thu hồi token hoặc quyền có thể xảy ra trước khi cache hết hạn.

## 9. Với mTLS và DPoP, proxy có thể làm hỏng ràng buộc token

Audience không thay đổi khi qua proxy, nhưng **bằng chứng người gửi** (proof of possession) có thể bị ảnh hưởng bởi cách proxy kết thúc kết nối hoặc viết lại URL.

### Access token ràng buộc chứng chỉ (mTLS)

Với token bị ràng buộc với client certificate, resource server phải xác minh ràng buộc thích hợp với chứng chỉ dùng trong luồng tương ứng. Nếu gateway kết thúc mTLS từ client và mở một kết nối mTLS khác đến backend bằng chứng chỉ **của gateway**, backend không thể đơn giản coi chứng chỉ ở hop trong là chứng chỉ của client ban đầu. Cần một kiến trúc kiểm token/ràng buộc tại điểm phù hợp hoặc cơ chế chứng thực nội bộ được backend tin cậy.

### DPoP

DPoP có thể ràng buộc access token với một khóa của client và dùng proof bao gồm các thuộc tính như HTTP method và URI mục tiêu. Nếu proxy **đổi path, host hoặc scheme**, backend cần hiểu đúng **URI bên ngoài** theo trust contract để kiểm proof, hoặc gateway là điểm kiểm DPoP và tạo bằng chứng downstream riêng. Không lấy `X-Forwarded-*` do client tự gửi làm URI được chứng thực; chỉ dùng giá trị đã được proxy tin cậy chuẩn hóa và bảo vệ.

**Bài học:** “Proxy không đổi `aud`” không có nghĩa proxy vô hình với mọi bảo vệ token. Chữ ký JWT, audience, scope và các ràng buộc người gửi là **các điều kiện độc lập**, mỗi điều kiện cần được kiểm tại trust boundary thích hợp.

## 10. Kiểm audience và quyền ở backend: ví dụ Java/Spring

Trong Spring Security 6.x, resource server dùng JWT thường kiểm chữ ký, issuer và thời gian theo cấu hình, nhưng **đừng giả định audience luôn được kiểm đúng API nếu chưa cấu hình validator**.

Một ví dụ cấu hình cho Order API:

~~~java
@Configuration
public class OrderApiSecurityConfig {
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.oauth2.issuer}") String issuer,
            @Value("${security.oauth2.jwks-uri}") String trustedJwksUri) {

        // Chỉ dùng JWKS URI đã được cấu hình từ nguồn tin cậy.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(trustedJwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> targetAudience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token is not intended for orders-api", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, targetAudience));
        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đoạn mã chỉ là **khung minh họa**: cần imports/dependencies, cấu hình thuật toán/JWK đáng tin, kiểm token profile/loại, các bảo vệ web và kiểm quyền nghiệp vụ trong service. `SCOPE_orders:read` giả định cách ánh xạ scope thông dụng của Spring Security; mapping có thể được tùy biến. Với API dùng opaque token, hãy dùng cơ chế introspection phù hợp thay vì JWT decoder.

**Điểm cần chú ý:** `orders-api` là hằng số cấu hình **được AS và Order API thống nhất**. Không dùng `request.getServerName()`, header `Host` hoặc hostname container để làm expected audience. Trong một triển khai khác, audience có thể là resource URI, nhưng cũng phải được cấu hình rõ.

### Kiểm thêm quyền trên từng đối tượng

~~~text
function getOrder(request, id):
    ctx = verifiedAccessTokenContext(
        issuer = "https://login.example.test",
        audience = "orders-api"
    )
    if ctx.invalid:
        return HTTP_401
    if not ctx.scopes.containsExactly("orders:read"):
        return HTTP_403

    order = repository.findWithinTenant(id, ctx.verifiedTenant)
    if order == null:
        return HTTP_404
    if not policy.mayReadOrder(ctx.subject, ctx.clientOrActor, order):
        return HTTP_403_or_404_by_policy

    return HTTP_200_with_allowed_fields
~~~

`verifiedTenant` và `clientOrActor` là **ngữ cảnh đã được kiểm chứng theo hợp đồng token/nguồn quyền**, không phải những claim có sẵn bắt buộc trong mọi access token. Resource server phải tự thực thi authorization trên tài nguyên ngay cả khi token đã được gateway kiểm.

## 11. Lỗi kiến trúc thường gặp

| Sai lầm | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| Gateway rewrite `Host` nên backend đổi expected `aud` theo host mới | Token hợp lệ bị từ chối hoặc đội phát triển bỏ kiểm audience để “chạy được” | Dùng audience logic từ cấu hình tin cậy |
| Gateway nhận token `aud=gateway-api` rồi relay đến mọi backend | Backend có thể chấp nhận nhầm token không dành cho mình | Thiết kế endpoint gateway như RS và dùng bằng chứng downstream riêng, hoặc cấp token đúng backend |
| Backend không kiểm audience vì gateway đã kiểm chữ ký | Token hợp lệ của API A có thể bị dùng ở API B | Kiểm theo boundary và contract; tránh đường gọi trực tiếp bypass |
| Gateway sửa payload `aud` và giữ signature cũ | JWT không hợp lệ | Không sửa JWT đã ký; phát hành token mới đúng quy trình nếu cần |
| Gateway tự ký token mới và tự gán mọi scope | Vượt quyền, mất kiểm soát issuer/actor | AS/issuer được tin phải áp dụng grant, delegation, downscoping |
| Tin `X-User-Id` và `X-Tenant-Id` đến từ client | Giả mạo principal và vượt tenant | Loại bỏ header từ ngoài; truyền ngữ cảnh đã xác thực theo kênh được bảo vệ |
| Dùng OIDC ID token làm access token ở gateway | Token confusion, sai audience và mục đích | Xác minh token profile và dùng access token/bằng chứng phù hợp |
| Nhận nhiều audience tùy ý mà không kiểm scope | Mở rộng vùng token bị dùng và vượt quyền | Giới hạn audience/scope và kiểm object-level authorization |
| Chuyển tiếp token ràng buộc mTLS/DPoP mà không kiểm bằng chứng phù hợp ở hop sau | Ràng buộc người gửi bị bỏ qua hoặc luôn thất bại | Xác định điểm kiểm proof, URL/cert canonical và bằng chứng downstream |
| Gateway cache introspection quá lâu | Token bị thu hồi vẫn được coi là active | TTL/cache theo chính sách, kiểm trạng thái/thu hồi cần thiết |

Một dạng rủi ro nổi bật là **confused deputy**: API hoặc gateway có quyền rộng bị client ít quyền khiến nó thực hiện hành động không được phép. Audience là một ranh giới, nhưng phải kết hợp **scope, subject/client/actor và quyền theo đối tượng** để tránh dịch vụ trở thành “người đại diện bị lợi dụng”.

## 12. Ma trận kiểm thử cho proxy/gateway

Giả sử hệ thống:

~~~text
Public ingress: https://api.example.test
Gateway:        gateway-prod
Order API:      orders-api   (backend orders-service:8080)
Payment API:    payment-api  (backend payments-service:8080)
Issuer:         https://login.example.test
~~~

Mỗi phép thử dưới đây nên được thực hiện cả qua gateway và qua **mọi đường vào backend được phép tồn tại**; nếu backend không được phép gọi trực tiếp, cần xác minh đường vào trực tiếp thực sự bị chặn.

| Kịch bản | Điều kiện | Kỳ vọng |
|---|---|---|
| **Route rewrite thông thường** | Token `aud=orders-api`, request public tới `/orders/42` và backend có host khác | Order API xử lý nếu token, scope và quyền đối tượng hợp lệ |
| **Token của API khác** | Token `aud=payment-api` gửi đến Order API | **401 / invalid_token**, không vì chung issuer mà cho qua |
| **Token của gateway** | Token `aud=gateway-api` được relay nguyên tới backend mong đợi `orders-api` | Backend **từ chối** nếu không có contract chấp nhận token này |
| **Đa audience có chủ đích** | Token `aud=["orders-api","payment-api"]` | Mỗi API chỉ cân nhắc chấp nhận nếu profile/policy cho phép, sau đó kiểm scope và quyền |
| **Audience gần giống** | `aud=orders-api-v2` khi expected là `orders-api` | **Từ chối**, không so tiền tố |
| **Token thiếu `aud` hoặc sai kiểu** | JWT access token thuộc profile đòi audience | **Từ chối** |
| **Issuer lạ hoặc signature bị sửa** | Payload có `aud=orders-api` nhưng không đáng tin | **Từ chối** trước khi dùng claims cấp quyền |
| **OIDC ID token** | `aud=sales-web`, dùng làm bearer tại Order API | **Từ chối** do sai mục đích/token profile |
| **Token exchange hợp lệ** | Gateway có token mới từ AS với `aud=orders-api`, scope giảm | Order API kiểm token mới và quyền trên resource |
| **Token exchange xin tăng scope** | Gateway xin scope ngoài quyền client/subject | AS phải **từ chối** hoặc giới hạn theo policy; không tự cấp quyền tăng |
| **Header giả mạo** | Client gửi `X-User-Id: admin` và `X-Forwarded-Host` | Không được thay đổi principal, audience hay quyền |
| **Opaque token đã thu hồi** | Introspection trả `active=false` | **Từ chối** ở hop chịu trách nhiệm kiểm |
| **Sai quyền đối tượng** | Đúng `aud=orders-api` và `scope=orders:read` nhưng order khác tenant | **403 hoặc 404**; không lộ dữ liệu |
| **Bỏ qua gateway** | Client gọi trực tiếp backend qua cổng nội bộ | Không được truy cập nếu đường vào không được phép; backend vẫn kiểm policy |
| **DPoP/mTLS sai ngữ cảnh** | Proxy đổi URL/cert nhưng không có cơ chế kiểm proof hợp lệ | **Từ chối** hoặc xử lý qua thiết kế binding phù hợp; không bỏ kiểm proof |

### Bài tập tình huống

AS phát hành token:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "report-api",
  "scope": "orders:read",
  "exp": 1800000900
}
~~~

Client gọi `https://api.example.test/reports/daily`. Gateway đưa token đến **Report API**. Sau đó Report API lấy token nguyên bản gửi đến **Order API** qua `http://orders-service:8080`.

**Câu 1:** Gateway có khiến `aud` tự đổi thành `orders-api` sau khi route không?

**Đáp án:** Không. Audience token vẫn là `report-api`; rewrite đường đi HTTP không sửa nội dung token.

**Câu 2:** Order API nên chấp nhận vì token có `scope=orders:read` và issuer đúng không?

**Đáp án:** Không. Token **không dành cho Order API**. Scope không thay thế audience. Order API cần từ chối token sai audience.

**Câu 3:** Làm thế nào để Report API đọc đơn hàng hợp lệ mà vẫn bảo toàn delegation?

**Đáp án:** Report API có thể xin **token downstream dành cho `orders-api`** từ AS qua cơ chế được hỗ trợ, ví dụ token exchange, với scope và subject/actor được AS cho phép. Order API xác minh token mới, rồi tiếp tục kiểm quyền An trên từng đơn hàng. Một phương án khác là dùng **service credential và policy service** nếu hoạt động được phép với danh tính service, nhưng không được tự giả rằng nó thay mặt An.

**Câu 4:** Nếu gateway tự gắn `X-User-Id: user:an` vào request đến Order API thì có đủ không?

**Đáp án:** Chưa đủ. Backend cần tin được **nguồn, tính toàn vẹn và quyền sử dụng ngữ cảnh**, chặn các header giả từ client và kiểm quyền đối tượng; chỉ có một header do proxy chuyển tiếp không tạo delegation an toàn.

## 13. Checklist thiết kế trước khi triển khai

1. **Resource server nào chấp nhận token tại từng hop?** Gateway là RS, backend là RS hay cả hai?
2. **Audience identifier là gì?** Đó là URI hay ID logic do AS định nghĩa? Mỗi service có validator từ cấu hình tin cậy?
3. **Proxy có đang relay token hay chấm dứt token bên ngoài?** Hợp đồng cho ngữ cảnh downstream có rõ ràng và được bảo vệ?
4. **Có tránh tự đổi expected audience theo Host, X-Forwarded-Host hoặc hostname container?** Chỉ dùng thông tin định tuyến đã được tin cậy cho những mục đích thích hợp.
5. **Có phân biệt reissue/token exchange với sửa JWT?** Token mới phải do issuer được tin cấp và theo chính sách không nâng quyền ngoài ý muốn.
6. **Có kiểm token profile và đúng audience?** Phân biệt JWT/opaque, access/ID/refresh token, issuer, `exp`, `scope`, actor/client.
7. **Backend có kiểm quyền nghiệp vụ?** Scope, tenant, owner, role và trạng thái đối tượng đều được áp dụng tại ranh giới phù hợp?
8. **Có bảo vệ đường vào nội bộ?** mTLS/service identity, xác minh assertion nội bộ, chống giả header và chặn bypass gateway?
9. **Token bị đánh cắp hoặc thu hồi thì sao?** TTL, introspection cache, downscoping, ràng buộc người gửi và log an toàn có đủ không?
10. **Có kiểm thử qua cả proxy và đường vào trực tiếp?** Test token đúng chữ ký nhưng sai audience, route rewrite, multi-aud, delegation, DPoP/mTLS và dữ liệu sai tenant.

**Ghi nhớ:** **Proxy/gateway không tự đổi `aud` của access token khi route request.** Nếu cần một audience khác ở backend, phải có **token/bằng chứng mới theo hợp đồng tin cậy**, ví dụ do Authorization Server phát hành sau token exchange. Resource server không được bỏ kiểm audience vì token đi qua mạng nội bộ; đồng thời audience đúng chỉ là **một điều kiện**, vẫn cần kiểm issuer, hiệu lực, scope và quyền trên tài nguyên cụ thể.

### Chuẩn tham khảo

- **RFC 7519 — JSON Web Token (JWT):** claim `aud` và yêu cầu kiểm bên nhận JWT.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** các vai trò AS, RS, client và grant.
- **RFC 6750 — Bearer Token Usage:** gửi bearer token và xử lý token không hợp lệ.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** chỉ định resource đích khi xin token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims và quy tắc profile JWT access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** tra hiệu lực và ngữ cảnh của opaque token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** xin token mới cho resource/audience downstream.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token vào khóa và proof HTTP.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc token vào chứng chỉ.
- **OpenID Connect Core 1.0:** ID token dành cho client, khác access token của resource server.
