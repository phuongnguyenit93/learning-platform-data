# Audience và resource server

Giả sử người dùng An đăng nhập ứng dụng bán hàng và ứng dụng nhận được một JWT access token có chữ ký hợp lệ. Token được phát hành cho **Profile API** để xem hồ sơ cá nhân. Nếu ứng dụng đem token đó gọi **Payment API**, Payment API có nên chấp nhận chỉ vì token đúng chữ ký và còn hạn?

**Không.** Access token phải được cấp **cho đúng resource server** đang tiếp nhận yêu cầu. Trong JWT, claim **`aud` (audience)** giúp xác định những bên nhận token mà bên phát hành dự kiến. Nếu Payment API không nằm trong audience được phép, API phải từ chối, kể cả khi `iss` hợp lệ, `sub` là An và token có một scope trông có vẻ phù hợp.

Đây là ranh giới tin cậy trọng tâm của chương **Claims** trong module **Security Token Security Fundamentals**: hệ thống OAuth 2.0/OIDC phải phân biệt **ai phát hành token**, **token dành cho dịch vụ nào**, **token cấp những quyền gì** và **ai được phép truy cập tài nguyên cụ thể**. Hiểu đúng audience ngăn một token hợp lệ ở dịch vụ này trở thành “vé thông hành” ở dịch vụ khác.

**Sau bài học, bạn sẽ có thể:**

- Giải thích vai trò **authorization server** và **resource server**, cũng như `aud` biểu thị điều gì trong JWT.
- Phân biệt `aud` với `iss`, `sub`, `client_id`, `scope` và audience của **OIDC ID token**.
- Kiểm audience cho JWT access token và opaque access token qua introspection.
- Thiết kế audience trong hệ thống nhiều API/microservice; hiểu **resource indicators** và token exchange.
- Nhận diện lỗi **token substitution**, **confused deputy** và kiểm thử API theo nguyên tắc từ chối mặc định.

## 1. Authorization server, client và resource server là ai?

Trong OAuth 2.0, có những vai trò thường xuất hiện:

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Resource owner** | Chủ thể có quyền liên quan đến tài nguyên được bảo vệ; thường là người dùng | An sở hữu hồ sơ và hóa đơn |
| **Client** | Ứng dụng xin token và dùng token để gọi API | Ứng dụng quản lý bán hàng |
| **Authorization Server (AS)** | Xác thực và đánh giá grant/chính sách, cấp token | `https://login.example.test` |
| **Resource Server (RS)** | API lưu/điều khiển tài nguyên; xác minh token và phân quyền yêu cầu | Profile API, Invoice API, Payment API |

Một hệ thống có thể vận hành AS và RS trong cùng một sản phẩm, nhưng **vai trò về giao thức vẫn khác nhau**. Nhiều microservice có thể dùng chung một AS nhưng mỗi service có audience riêng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as An
    participant C as Sales App (OAuth client)
    participant AS as Authorization Server
    participant P as Profile API (resource server)
    participant B as Billing API (resource server)
    U->>C: Đăng nhập và yêu cầu xem hồ sơ
    C->>AS: Xin access token cho Profile API
    AS-->>C: Access token aud=profile-api
    C->>P: GET /me + access token
    P->>P: Kiểm issuer, audience, thời gian và quyền
    P-->>C: Trả hồ sơ được phép
    C->>B: GET /invoices + cùng token
    B->>B: aud=profile-api, không phải billing-api
    B-->>C: Từ chối token sai audience
~~~

**Điểm then chốt:** Việc người dùng An có tài khoản ở cả hai dịch vụ không có nghĩa một access token được cấp cho Profile API tự động có giá trị ở Billing API.

## 2. `aud` nói lên điều gì?

Trong JSON Web Token (RFC 7519), claim **`aud`** (*audience*) xác định bên nhận mà JWT được hướng tới. Bên xử lý JWT cần kiểm tra mình có thuộc đối tượng nhận được phép hay không. Trong một resource API dùng **JWT access token**, audience thường biểu thị **resource server/API** được AS cấp quyền nhận token đó.

Ví dụ JWT access token dành cho **Invoice API**:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "client_id": "sales-web",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "token-abc123"
}
~~~

| Claim | Câu hỏi | Giá trị trong ví dụ |
|---|---|---|
| `iss` | **Ai phát hành** token? | AS tại `https://login.example.test` |
| `sub` | Token mô tả **chủ thể nào**? | Người dùng An, theo hợp đồng của issuer |
| `aud` | Token **dành cho API nào nhận**? | `invoice-api` |
| `client_id` | **Client nào** được AS cấp token? | `sales-web` |
| `scope` | Token được cấp **phạm vi quyền gì**? | `invoice:read` |
| `iat`, `exp` | Token được phát hành và hết hạn khi nào? | NumericDate, tính bằng giây từ Unix epoch |
| `jti` | Định danh token là gì, nếu profile cung cấp? | `token-abc123` |

Các giá trị ID trong ví dụ là giả định. `client_id`, `scope` và ý nghĩa chi tiết của `sub` phải được hiểu theo **access-token profile** mà AS và API đã thống nhất; không phải mọi JWT đều có đủ các claim này.

### Audience không phải URL của mọi endpoint

Audience có thể là một định danh như `invoice-api` hoặc một URI như `https://api.example.test/invoices`, tùy AS và cấu hình của resource server. Nó **không bắt buộc** là địa chỉ URL đang nhận HTTP request, cũng không nhất thiết thay đổi theo mỗi path.

Ví dụ Invoice API có các endpoint:

~~~text
GET  https://api.example.test/invoices/42
POST https://api.example.test/invoices
GET  https://api.example.test/invoices/42/items
~~~

Cả ba có thể dùng chung audience `invoice-api`. Từng endpoint vẫn cần **scope và quyền riêng**. Ngược lại, chỉ vì token có audience là một URI gần giống hostname không có nghĩa API được phép so khớp bằng tiền tố URL.

**Quy tắc:** Resource server phải so `aud` với **định danh audience đã được cấu hình cho mình**, không dùng so khớp gần đúng, suy đoán từ hostname hoặc tự chấp nhận bất kỳ chuỗi nào bắt đầu bằng một prefix.

## 3. Kiểu dữ liệu của `aud` và cách kiểm đúng

Theo RFC 7519, `aud` có thể là:

- **Một JSON string** nếu chỉ có một audience.
- **Một JSON array các string** nếu có nhiều audience.

Hai payload sau đều có thể là cách biểu diễn hợp lệ của JWT:

~~~json
{
  "aud": "invoice-api"
}
~~~

~~~json
{
  "aud": ["invoice-api", "reporting-api"]
}
~~~

API có audience `invoice-api` có thể chấp nhận cả hai **về khía cạnh audience**, nếu profile triển khai cho phép và các kiểm tra khác đều đạt. API `payment-api` không được chấp nhận token này.

### Không dùng substring, startsWith hoặc so khớp tên gần giống

~~~text
expectedAudience = "invoice-api"

aud = "invoice-api"                    -> MATCH
aud = ["profile-api", "invoice-api"]   -> MATCH
aud = "invoice-api-v2"                 -> NO MATCH
aud = "other-invoice-api"              -> NO MATCH
aud = "https://api.example.test/invoices" -> NO MATCH
    (trừ khi đây chính là audience đã được cấu hình)
aud = 123                              -> INVALID TYPE
aud = ["invoice-api", 123]             -> INVALID TYPE
aud = null                             -> INVALID/MISSING
~~~

Tùy thư viện, JWT có `aud` là string hoặc array có thể được chuẩn hóa thành một danh sách string sau khi parse. **Chỉ dùng kết quả của thư viện sau khi JWT được kiểm tra hợp lệ**; không tự dùng một chuỗi JSON thô để tìm bằng `contains("invoice-api")`.

### Khi nào phải từ chối `aud` thiếu?

JWT tổng quát có một số registered claims mang tính tùy chọn; tuy nhiên **API sử dụng JWT access token theo profile yêu cầu audience** phải xem `aud` hợp lệ là điều kiện bắt buộc. Nếu không có audience, API không có bằng chứng rằng token dành cho mình và phải **fail closed**. Khi thiết kế profile OAuth cho các resource server, nên quy định audience bắt buộc, không xử lý “thiếu `aud` thì cho qua”.

### Một token có nhiều audience: đúng kiểu chưa chắc nên dùng

AS có thể cấp token cho nhiều resource server khi chính sách và token profile cho phép, nhưng điều này làm tăng nơi token có thể được sử dụng nếu bị lộ:

~~~json
{
  "aud": ["invoice-api", "payment-api"],
  "scope": "invoice:read payment:write"
}
~~~

Nếu Billing UI chỉ cần đọc hóa đơn, cấp token đồng thời có quyền ghi thanh toán sẽ mở rộng tác động của việc đánh cắp token. **Ưu tiên audience đủ hẹp** theo ranh giới resource server và cấp quyền tối thiểu. Việc cho phép đa audience là quyết định của AS/resource server theo hệ thống cụ thể, không phải lợi ích mặc định.

## 4. `aud` khác `scope` và quyền trên đối tượng thế nào?

Đây là ba tầng câu hỏi khác nhau:

1. **Audience:** *Token có được gửi đến API này không?*
2. **Scope/quyền chức năng:** *Token được phép yêu cầu loại hành động này không?*
3. **Quyền trên đối tượng và điều kiện nghiệp vụ:** *Chủ thể có quyền làm hành động đó trên bản ghi cụ thể này không?*

Ví dụ An gọi `GET /invoices/42`:

| Điều kiện | Token hoặc dữ liệu | Kết quả |
|---|---|---|
| Sai audience | `aud=profile-api` | **Từ chối token** ngay, dù có `invoice:read` |
| Đúng audience, thiếu scope | `aud=invoice-api`, `scope=invoice:write` | **Từ chối quyền** đọc |
| Đúng audience và scope nhưng sai tenant | `aud=invoice-api`, `scope=invoice:read`, hóa đơn 42 thuộc tenant khác | **Từ chối** theo chính sách tenant |
| Đúng audience, scope và quyền dữ liệu | An được phép xem hóa đơn 42 | **Có thể cho phép**, nếu token và mọi điều kiện khác hợp lệ |

Lưu ý: `scope` có thể dùng chuỗi các giá trị tách bằng dấu cách theo profile JWT access token OAuth 2.0; tên scope như `invoice:read` là quy ước nghiệp vụ, không phải giá trị bắt buộc do OAuth định nghĩa. Việc có scope **không tự chứng minh** người dùng sở hữu hóa đơn.

Một API không nên phân quyền bằng quy tắc “chỉ cần `aud` đúng là cho phép toàn bộ endpoint”. `aud` xác định **đích nhận**, không xác định toàn bộ khả năng của subject hay client.

## 5. `aud` của OIDC ID token khác audience của access token

Trong OpenID Connect, **ID token** dành cho **client (relying party)** để client xác minh sự kiện xác thực của người dùng. Thông thường, audience trong ID token chứa **OAuth client_id** của ứng dụng:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "sales-web",
  "auth_time": 1799999900,
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Trong khi đó, access token dành cho Invoice API có thể có:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

**Không chuyển ID token cho Invoice API và coi nó là access token.** Dù cả hai đều có thể là JWT và được ký bằng khóa của cùng một issuer, mục đích, audience và quy tắc kiểm chứng khác nhau. Một API không nên nhận token chỉ bằng điều kiện “chữ ký hợp lệ + `sub` tồn tại”.

Trong một số token profile có quy định `typ` ở JOSE header (chẳng hạn `at+jwt` cho JWT access token theo RFC 9068), API cũng phải xét **token type/profile** phù hợp. Không dựa duy nhất vào `typ` mà bỏ qua issuer, audience, chữ ký, thời gian hoặc chính sách quyền.

**Refresh token** lại dùng để xin access token mới tại authorization server; nó không phải vé truy cập trực tiếp resource server. Đừng dùng refresh token hoặc ID token làm bằng chứng quyền cho API.

## 6. Authorization Server chọn audience như thế nào?

Audience không nên do client tự ghi vào JWT rồi gửi cho API. **Authorization Server** quyết định token được cấp cho resource nào, theo đăng ký client, grant, scope, chính sách và yêu cầu tài nguyên.

Một cách chuẩn để client diễn đạt resource server mục tiêu là **OAuth 2.0 Resource Indicators (RFC 8707)**. Client có thể gửi tham số `resource` khi tương tác với AS để chỉ định tài nguyên muốn truy cập. Giá trị này là URI xác định tài nguyên theo đặc tả; URI/resource indicator cụ thể phải được AS chấp nhận và quản trị.

Ví dụ minh họa một yêu cầu cấp token:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-redacted>

grant_type=client_credentials&
scope=invoice%3Aread&
resource=https%3A%2F%2Fapi.example.test%2Finvoices
~~~

Ở ví dụ `client_credentials` này, một service xin quyền đọc Invoice API **bằng quyền của chính service**; không có người dùng cuối bắt buộc. AS phải xác thực client theo cơ chế thích hợp, xem xét service được phép xin tài nguyên và scope hay không, rồi quyết định có phát hành token hay từ chối. Ví dụ trên chỉ minh họa shape HTTP; request thực tế còn phụ thuộc cấu hình endpoint và client authentication.

Với ứng dụng có người dùng, tham số `resource` cũng có thể được dùng trong authorization request và/hoặc token request theo luồng và hỗ trợ của AS. Khi dùng Authorization Code Flow, client cần tuân thủ các kiểm soát của flow như **PKCE**, redirect URI và ràng buộc code; không vì có `resource` mà bỏ qua các kiểm soát này.

### `resource` và `aud` có phải luôn bằng nhau?

Không nhất thiết về **chuỗi biểu diễn**. `resource` là **tham số yêu cầu** dùng để chỉ định resource server; `aud` là **claim do AS phát hành** trong token JWT hoặc thông tin tương đương từ AS. Cách AS ánh xạ resource URI đến audience identifier phụ thuộc profile và cấu hình.

Ví dụ:

~~~text
Client requested resource:
  https://api.example.test/invoices

AS configured audience for Invoice API:
  invoice-api

JWT access token:
  "aud": "invoice-api"
~~~

Mô hình ánh xạ trên chỉ hợp lệ nếu được **AS và API thống nhất** theo profile áp dụng. Nếu hệ thống theo một profile quy định audience phải là resource URI, thì phải tuân thủ profile đó thay vì tùy ý đổi thành alias.

**Tuyệt đối không** để client chọn tùy ý `aud=admin-api` chỉ bằng một tham số rồi AS cấp token mạnh hơn quyền được đăng ký. AS cần kiểm cả client được phép truy cập resource nào và các scope nào được cấp tại resource đó.

## 7. Kiểm audience ở resource server: JWT và opaque token

### JWT access token

Đối với JWT access token, resource server cần:

1. **Xác định loại token/profile được chấp nhận** để tránh dùng ID token hoặc JWT mục đích khác.
2. **Xác minh chữ ký** theo khóa và thuật toán đã cấu hình tin cậy cho issuer; không lấy URL khóa tùy ý từ header do token tự chỉ định.
3. **Kiểm issuer** (`iss`) trùng cấu hình nguồn phát hành được phép.
4. **Kiểm audience** (`aud`) có chính xác định danh resource server này.
5. **Kiểm thời gian** (`exp`, `nbf` khi có, và điều kiện khác theo profile), trạng thái/thu hồi nếu kiến trúc cần.
6. **Kiểm scope và quyền trên tài nguyên** trước khi thực thi thao tác.

~~~mermaid
flowchart TD
    A["Nhận access token"] --> B{"Đúng loại token?"}
    B -- "Không" --> X["Từ chối 401"]
    B -- "Có" --> C["Xác minh chữ ký/issuer hoặc introspection"]
    C --> D{"Nguồn tin cậy và hiệu lực hợp lệ?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Resource server có trong aud?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Scope và quyền nghiệp vụ phù hợp?"}
    F -- "Không" --> Y["Từ chối 403 hoặc 404 theo chính sách"]
    F -- "Có" --> Z["Thực thi hành động được phép"]
~~~

Sơ đồ mô tả **các điều kiện cần được xác minh**. Trong thực tế, thư viện có thể parse header/payload trước khi kiểm chữ ký, nhưng **không được coi claims chưa xác minh là nguồn đáng tin cho quyết định bảo mật**.

Mã giả:

~~~text
function getInvoice(request, invoiceId):
    ctx = validateAccessToken(
        request.bearer,
        allowedIssuer = "https://login.example.test",
        expectedAudience = "invoice-api",
        expectedTokenType = "access"
    )
    if ctx.invalid:
        return HTTP_401

    if not ctx.scopes.containsExactly("invoice:read"):
        return HTTP_403

    invoice = repository.findWithinTenant(invoiceId, ctx.verifiedTenant)
    if invoice == null:
        return HTTP_404

    if not policy.canReadInvoice(ctx.subject, ctx.clientId, invoice):
        return HTTP_403_or_404_by_policy

    return HTTP_200_with_allowed_invoice_fields
~~~

Các trường `verifiedTenant`, `clientId` ở đây là **ngữ cảnh được tạo từ hợp đồng token và dữ liệu tin cậy**, không phải claims chuẩn mà mọi token buộc phải có. Nếu token không mang tenant, API có thể lấy membership từ nguồn nội bộ có thẩm quyền. `validateAccessToken` là mã giả, không phải API chuẩn.

### Opaque access token

Một opaque token có thể là chuỗi ngẫu nhiên như `m3J...`, không thể tự parse ra `aud`. Resource server thường gọi **OAuth 2.0 Token Introspection (RFC 7662)** hoặc dịch vụ kiểm token tin cậy.

Phản hồi introspection minh họa:

~~~json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user:an",
  "aud": ["invoice-api"],
  "client_id": "sales-web",
  "scope": "invoice:read",
  "exp": 1800000900
}
~~~

Resource server phải kiểm **`active`** và **audience/mục đích/trạng thái** theo hợp đồng với AS, sau đó kiểm quyền nghiệp vụ. Introspection không tự làm biến mất nhu cầu **kiểm audience**. AS có thể trả thông tin đã giới hạn theo resource server được phép introspect, nhưng RS vẫn cần thực thi policy mà hệ thống đã định nghĩa.

Nếu phản hồi introspection không chứa `aud` hoặc trường tương đương, chỉ nên chấp nhận theo một **hợp đồng được thiết kế rõ** thực sự ràng buộc token với resource server. Nếu API không xác định được token được cấp cho mình, **từ chối mặc định**. Cache introspection cần có giới hạn thời gian phù hợp; token có thể bị thu hồi trong khi kết quả cache còn hiệu lực.

## 8. Ví dụ cấu hình Spring Security để kiểm audience

Trong Spring Security 6.x, khi dùng JWT Resource Server, việc cấu hình một issuer đáng tin **không đồng nghĩa mọi bản triển khai mặc nhiên kiểm audience đúng API**. Hãy gắn audience validator theo hợp đồng của Invoice API.

Ví dụ cấu hình minh họa:

~~~java
@Configuration
@EnableWebSecurity
public class InvoiceApiSecurityConfig {
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.oauth2.issuer}") String issuer,
            @Value("${security.oauth2.jwks-uri}") String trustedJwksUri) {

        // JWK Set URI phải đến từ cấu hình đáng tin của hệ thống.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwksUri)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> invoiceAudience = jwt ->
            jwt.getAudience().contains("invoice-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token", "Audience is not invoice-api", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, invoiceAudience));

        return decoder;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:read")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đây là **đoạn minh họa**, cần imports/dependencies, cấu hình chính xác JWK/issuer/thuật toán được tin, token type/profile, quyền nghiệp vụ và các phần bảo vệ HTTP khác trước khi dùng trong production. Không nhận `trustedJwksUri` từ token hay request; mã `SCOPE_invoice:read` giả định converter của Spring ánh xạ claim `scope` sang authorities đúng như hợp đồng. Các phiên bản Spring Security có thể có API cấu hình validator khác nhau.

**Điều Spring filter này chưa làm:** Kiểm hóa đơn 42 có thuộc tenant/người dùng được phép hay không. Việc đó phải được xử lý tại service/policy khi truy xuất dữ liệu thực. Trong hệ thống có token exchange, có thể còn phải kiểm actor/client và ràng buộc delegation.

## 9. Microservices, token forwarding và token exchange

Một lỗi kiến trúc thường gặp là **chuyển tiếp access token của API A sang API B**. Giả sử:

~~~text
Browser --> Report API (aud = report-api)
Report API --> Invoice API (??? cùng bearer token ???)
~~~

Nếu Report API nhận token có `aud=report-api` rồi gửi nguyên token sang Invoice API, Invoice API phải **từ chối vì sai audience**. Việc hai dịch vụ chạy trong cùng Kubernetes cluster hoặc cùng doanh nghiệp không tự cho phép bỏ qua `aud`.

Một thiết kế có thể dùng **token exchange** (RFC 8693), khi AS hỗ trợ:

~~~mermaid
sequenceDiagram
    actor U as An
    participant C as Sales App
    participant A as Report API
    participant AS as Authorization Server
    participant B as Invoice API
    U->>C: Yêu cầu báo cáo hóa đơn
    C->>A: Bearer token aud=report-api
    A->>A: Xác minh token và policy của A
    A->>AS: Xin token downstream cho Invoice API
    AS->>AS: Kiểm client, token nguồn và delegation
    AS-->>A: Access token mới, aud=invoice-api
    A->>B: Gọi Invoice API bằng token mới
    B->>B: Kiểm aud=invoice-api và quyền trên hóa đơn
    B-->>A: Chỉ trả dữ liệu được phép
~~~

Trong một hệ thống delegation, token mới có thể giữ `sub` của người dùng An và thể hiện actor như Report API theo profile AS áp dụng. **Không tự thêm `act`, `sub` hoặc `aud` vào payload rồi coi như đã được AS ủy quyền.**

Nếu Report API sử dụng `client_credentials` để gọi Invoice API bằng quyền dịch vụ, token downstream có thể đại diện cho **service** chứ không phải người dùng An. Khi đó policy của Invoice API phải phù hợp với quyền service, không suy diễn rằng service có toàn bộ quyền của An.

### Audience ở gateway và nhiều service

Có hai mẫu kiến trúc chính:

| Mẫu | Cách cấp audience | Rủi ro và trách nhiệm |
|---|---|---|
| **Audience chung cho một nhóm API được quản lý như một resource server** | Các endpoint dùng một định danh logic chung, ví dụ `sales-api` | Dễ vận hành, nhưng tăng phạm vi có thể dùng token; các service vẫn phải kiểm scope, tenant và quyền từng resource |
| **Audience riêng từng API** | `report-api`, `invoice-api`, `payment-api` | Ranh giới hẹp hơn; cần cơ chế xin/đổi token khi gọi chéo API; B luôn kiểm audience của B |

Không có một mô hình duy nhất đúng cho mọi sản phẩm. Điều quan trọng là **audience phản ánh ranh giới tài nguyên đã xác định**, được AS và RS thống nhất, và không bị bỏ qua chỉ vì traffic đến từ gateway hoặc mạng nội bộ.

## 10. Audience giúp chống loại tấn công nào — và không chống được gì?

### Token substitution / token confusion

Kẻ tấn công có một JWT access token hợp lệ cho **Profile API**. Nếu **Admin API** chỉ kiểm chữ ký với cùng JWK của AS và không kiểm `aud`, token Profile API có thể bị dùng sai mục đích để gọi Admin API. Đây là một dạng **token substitution/confusion**: bằng chứng được cấp cho bên A bị chấp nhận tại bên B.

**Phòng vệ:** Xác minh issuer, chữ ký/loại token, thời gian và **audience chính xác** trước khi kiểm scope/quyền.

### Confused deputy

Một dịch vụ có quyền mạnh bị client ít quyền yêu cầu thực hiện tác vụ trên resource mà client không được phép. Audience sai hoặc chính sách delegation lỏng có thể làm giảm khả năng phân biệt ai thực sự được ủy quyền. **Phòng vệ:** Kiểm audience ở từng resource server, nguồn/actor của yêu cầu, scope và chính sách trên đối tượng.

### Token bị đánh cắp hoặc bị phát lại

Audience hẹp làm token bị đánh cắp **khó dùng ở API khác**; nó **không ngăn** kẻ tấn công dùng lại bearer token **tại chính API nằm trong audience** khi token còn hiệu lực. Cần thêm các lớp bảo vệ:

- HTTPS/TLS, lưu token an toàn, không ghi bearer/refresh token vào log hoặc URL.
- Access token sống đủ ngắn, phạm vi scope tối thiểu, cơ chế thu hồi/introspection phù hợp.
- Sender-constrained token như **mTLS hoặc DPoP** nếu kiến trúc hỗ trợ và RS thực sự kiểm bằng chứng ràng buộc người gửi.
- Reauthentication/step-up với hành động nhạy cảm, kiểm quyền dữ liệu và xác nhận giao dịch nếu có giá trị cao.
- Giám sát các mẫu truy cập bất thường và chống replay riêng cho các thao tác dùng một lần.

**Kết luận bảo mật:** Audience là **điều kiện cần để token đến đúng đích**, không phải giải pháp thay thế cho phân quyền hoặc bảo vệ toàn bộ vòng đời token.

## 11. Chọn HTTP status và xử lý lỗi

| Tình huống | Phản hồi điển hình | Nguyên nhân |
|---|---|---|
| Không có access token tại API riêng tư | **401 Unauthorized** | Chưa có bằng chứng được chấp nhận |
| Token sai chữ ký, issuer, thời gian, loại token hoặc audience | **401 Unauthorized**, có thể kèm `invalid_token` | Token không hợp lệ cho API này |
| Token hợp lệ đúng audience nhưng thiếu scope | **403 Forbidden**, có thể kèm `insufficient_scope` | Token không có quyền chức năng |
| Token đúng audience/scope nhưng thiếu quyền trên bản ghi | **403** hoặc **404** theo chính sách | Không có quyền trên resource cụ thể |
| API public có rule cho phép truy cập ẩn danh | Thành công theo chức năng | Không yêu cầu token theo chính sách đã khai báo |

Ví dụ phản hồi cho bearer token không hợp lệ với Invoice API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Tránh trả về token nguyên bản, các claims bí mật, chi tiết khóa ký hoặc thông tin tài nguyên của tenant khác trong response lỗi. Log nội bộ nên ghi **mã lỗi và correlation ID** an toàn để chẩn đoán, thay vì ghi bearer token.

## 12. Kiểm thử: đừng chỉ thử token đúng

Một kiểm thử tốt phải có cả token **hợp lệ về chữ ký nhưng không dành cho API**. Chính những token này cho thấy hệ thống có thực sự kiểm audience hay chỉ đang kiểm chữ ký.

| Kịch bản kiểm thử | Điều kiện | Kết quả mong đợi tại Invoice API |
|---|---|---|
| Token đúng API | `aud=invoice-api`, issuer/thời gian/quyền hợp lệ | Có thể cho phép theo policy đối tượng |
| Token dành cho Profile API | `aud=profile-api`, chữ ký vẫn hợp lệ | **401**, từ chối sai audience |
| Audience khác tên gần giống | `aud=invoice-api-v2` | **401**, không dùng startsWith/substring |
| Audience array có Invoice API | `aud=["profile-api","invoice-api"]` | Có thể chấp nhận về audience nếu profile cho phép; còn phải kiểm quyền |
| Audience array không có Invoice API | `aud=["profile-api","payment-api"]` | **401** |
| Audience thiếu hoặc sai kiểu | Không có `aud`, hoặc `aud=123` | **401** cho profile access token yêu cầu audience |
| ID token OIDC của client | `aud=sales-web`, cùng issuer và khóa ký | **401**, không coi ID token là access token |
| Token hết hạn | `exp` quá thời điểm hiện tại | **401**, dù `aud` đúng |
| Token thiếu scope | `aud=invoice-api` nhưng không có `invoice:read` | **403** hoặc từ chối phù hợp |
| Đổi hóa đơn sang tenant khác | Đúng token, đúng `aud`, nhưng tài nguyên sai tenant | **403/404**, không để lộ dữ liệu |
| Opaque token introspection trả `active=false` | Chuỗi token không còn hiệu lực | **401** |
| Opaque token active nhưng AS nói dành cho API khác | Introspection còn hiệu lực, sai resource/audience | **401** |
| Report API chuyển token của mình cho Invoice API | `aud=report-api` tại B | **401**, dùng token downstream phù hợp |
| JWT ký bằng khóa không tin cậy | Payload `aud=invoice-api` nhưng chữ ký giả | **401**, không tin claim chưa xác minh |

### Tình huống tự đánh giá

Một công ty có ba resource server dùng chung AS:

~~~text
User API      audience = user-api
Invoice API   audience = invoice-api
Payment API   audience = payment-api
~~~

Frontend nhận được hai token:

~~~json
{
  "token_A": {
    "iss": "https://login.example.test",
    "sub": "user:an",
    "aud": "invoice-api",
    "scope": "invoice:read"
  },
  "token_B": {
    "iss": "https://login.example.test",
    "sub": "user:an",
    "aud": "payment-api",
    "scope": "payment:create"
  }
}
~~~

Giả sử cả hai là access token hợp lệ, còn hạn, có chữ ký đúng. Trả lời:

1. **Có thể dùng token A để gọi Payment API không?** Không. `aud` chỉ dành cho Invoice API; scope đọc hóa đơn không thay thế audience.
2. **Có thể dùng token B để gọi Invoice API không?** Không. Token B chỉ dành cho Payment API.
3. **Nếu token A có thêm `payment:create` nhưng `aud` vẫn là `invoice-api` thì sao?** Payment API **vẫn từ chối** do audience sai.
4. **Nếu token A có `aud=["invoice-api","payment-api"]` thì có được tạo thanh toán không?** Chưa thể kết luận. Cần xác nhận token profile/AS cho phép đa audience, token có scope/quyền thanh toán cần thiết, subject/client có quyền trên tài nguyên và chính sách nghiệp vụ được thỏa.
5. **Nếu Invoice API nhận token A và xem hóa đơn của người khác?** Audience đúng chưa đủ; API phải kiểm quyền object-level và tenant.

## 13. Checklist thiết kế audience cho API

1. **Đặt tên resource server rõ ràng:** Có audience identifier được AS và API thống nhất chưa? Có định nghĩa giữa URI và alias không?
2. **Yêu cầu access token đúng profile:** API có từ chối ID token, refresh token và JWT không dành cho mục đích truy cập không?
3. **Xác minh trước khi tin claims:** Có kiểm issuer, chữ ký/khóa tin cậy hoặc introspection, thời hạn và trạng thái không?
4. **Kiểm audience chính xác:** Có xử lý cả string và array theo profile, không so khớp gần đúng, không chấp nhận audience thiếu không?
5. **Giới hạn quyền:** Có kiểm scope, vai trò, subject/client/actor và quyền trên đối tượng thay vì chỉ kiểm `aud` không?
6. **Đúng luồng cấp token:** AS có kiểm client, resource indicator và giới hạn scope, không cho client tùy ý xin audience mạnh hơn không?
7. **Kiểm downstream:** API A gọi B có token dành riêng cho B hoặc cơ chế delegation được tin cậy không?
8. **Kiểm tình huống đa audience:** Nếu cho phép, có cân nhắc tác động khi token bị đánh cắp không?
9. **Quản trị vòng đời:** Có chiến lược hết hạn, thu hồi, introspection cache, bảo vệ token và sender-constraining khi cần không?
10. **Kiểm thử âm tính:** Có thử token đúng chữ ký nhưng sai audience, ID token, claim sai kiểu, token bị thu hồi và dữ liệu sai tenant không?

**Ghi nhớ:** `iss` trả lời **“ai phát hành?”**, `aud` trả lời **“phát hành cho API nào nhận?”**, `scope` trả lời **“được cấp khả năng gì?”**, còn kiểm **quyền trên resource cụ thể** trả lời **“chủ thể có được làm việc này với dữ liệu này không?”**. Resource server an toàn phải kiểm cả bốn thay vì chỉ tin vào một JWT hợp lệ.

### Chuẩn tham khảo

- **RFC 7519 — JSON Web Token (JWT):** định nghĩa `aud` và cách biểu diễn string/array.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** vai trò client, authorization server, resource server và scope.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** tham số `resource` để định hướng access token tới tài nguyên mục tiêu.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token, kiểm audience và token type theo ngữ cảnh OAuth.
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác minh trạng thái và thông tin token khi dùng opaque/reference token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** cơ chế xin token downstream phù hợp với audience khác trong kiến trúc nhiều dịch vụ.
- **OpenID Connect Core 1.0:** ID token dành cho client, khác access token dành cho resource server.
