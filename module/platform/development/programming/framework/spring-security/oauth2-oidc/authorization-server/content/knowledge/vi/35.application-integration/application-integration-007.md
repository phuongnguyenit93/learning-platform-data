# Cấp audience và scope cho nhiều API hoặc gateway

## 1. Bài toán khi một Authorization Server bảo vệ nhiều API

Trong hệ thống có nhiều API, một client có thể cần đọc đơn hàng, tạo hóa đơn, tra cứu kho hoặc gọi một API tổng hợp phía sau API Gateway. Nếu Authorization Server chỉ cấp một access token chung cho mọi API mà không xác định rõ nơi token được phép sử dụng, token bị đánh cắp ở một nơi có thể bị phát lại ở nơi khác.

OAuth 2.0 cung cấp hai khái niệm bổ sung nhau để giới hạn quyền:

- **Audience (`aud`)** xác định Resource Server hoặc nhóm tài nguyên nào được phép nhận access token.
- **Scope (`scope`)** mô tả loại thao tác hoặc quyền mà token đại diện tại tài nguyên đó.

RFC 8707 bổ sung **Resource Indicator (`resource`)** để client chỉ rõ tài nguyên đích mà nó muốn truy cập khi xin token. Authorization Server kiểm tra yêu cầu đó theo policy và quyết định audience thực tế của token.

Bài thuộc chương **Tích hợp ứng dụng** của module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`. Nội dung tập trung vào cách thiết kế audience, scope và resource cho nhiều API hoặc gateway, cùng các extension point cần thiết trong Spring Authorization Server 1.5.8.

Sau bài học, bạn có thể:
1. Phân biệt audience, scope và resource indicator.
2. Thiết kế audience URI ổn định cho từng API, gateway hoặc tenant resource.
3. Đặt tên scope theo API và thao tác để tránh trùng nghĩa.
4. Ràng buộc scope với audience và client registration.
5. Tùy chỉnh claim `aud` trong JWT access token bằng `OAuth2TokenCustomizer`.
6. Xác định khi nào cần hỗ trợ RFC 8707 `resource` và cách lưu lựa chọn resource vào authorization.
7. Thiết kế token cho mô hình gọi API trực tiếp, qua gateway hoặc qua nhiều backend.
8. Kiểm tra audience và scope tại từng Resource Server.
9. Xử lý token opaque bằng introspection và quản lý token lifecycle.
10. Kiểm thử trường hợp scope sai, audience sai, multi-resource và token forwarding.

## 2. Các thành phần trong mô hình

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **OAuth2 Client** | Xin access token cho tài nguyên cần truy cập | `orders-web`, `billing-worker` |
| **Authorization Server (AS)** | Xác thực client/grant, kiểm tra policy và phát hành token | Spring Authorization Server |
| **Resource Indicator** | Chỉ ra tài nguyên đích trong authorization/token request | `https://api.example.com/orders/` |
| **Audience** | Định danh recipient được token cho phép | `https://api.example.com/orders/` |
| **Scope** | Mô tả quyền tại resource đã chọn | `orders.read`, `orders.write` |
| **Resource Server** | Xác minh token và thực thi quyền trên API | Orders API, Billing API |
| **API Gateway** | Điểm vào chung, xác minh token và định tuyến request | `https://gateway.example.com/` |

Một access token có thể được biểu diễn bằng JWT hoặc opaque/reference token. Dù dùng định dạng nào, policy vẫn phải xác định token được cấp cho tài nguyên nào và được phép thực hiện thao tác gì.

## 3. Phân biệt audience, scope và resource indicator

Ba khái niệm này thường xuất hiện trong cùng một flow nhưng trả lời ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| `resource` | Client muốn dùng token ở đâu? | `https://api.example.com/orders/` |
| `aud` | AS đã cho phép recipient nào nhận token? | `https://api.example.com/orders/` |
| `scope` | Token cho phép thao tác gì tại recipient đó? | `orders.read` |

**Resource là yêu cầu của client; audience là quyết định của AS.** Client có thể gửi một resource URI, nhưng AS phải kiểm tra URI đó có tồn tại, client có được phép truy cập và scope có phù hợp hay không. Không sao chép mù quáng giá trị `resource` từ request vào claim `aud`.

Ví dụ:

~~~text
resource = https://api.example.com/orders/
aud      = https://api.example.com/orders/
scope    = orders.read orders.write
~~~

Token trên được phát hành cho Orders API và mang hai quyền đọc/ghi đơn hàng. Billing API không được chấp nhận token đó chỉ vì nó được ký bởi cùng một Authorization Server.

Một scope không nên được dùng để thay thế audience. Ví dụ, `orders.read` mô tả thao tác đọc đơn hàng; nó không xác định token được phép gửi tới host hoặc API nào. Ngược lại, audience của Orders API không tự động cấp quyền đọc hoặc ghi đơn hàng.

### 3.1. Một token hợp lệ cần cả hai chiều kiểm soát

Resource Server cần xác minh:

1. Token được phát hành bởi issuer tin cậy.
2. Chữ ký và thời hạn token hợp lệ.
3. Audience có chứa đúng định danh của chính Resource Server.
4. Scope hoặc authority đủ cho endpoint đang gọi.
5. Các điều kiện bổ sung như tenant, ownership, trạng thái tài khoản hoặc policy nghiệp vụ đều thỏa mãn.

Chỉ kiểm tra scope mà bỏ qua audience sẽ tạo nguy cơ token redirect/replay sang API khác. Chỉ kiểm tra audience mà bỏ qua scope sẽ khiến mọi token hướng tới API đó có thể được dùng cho mọi thao tác.

## 4. Kiến trúc nhiều API và API Gateway

Có ba kiểu triển khai thường gặp.

### 4.1. Client gọi trực tiếp từng API

~~~mermaid
flowchart LR
    C[OAuth2 Client] -->|Token aud=Orders API| AS[Authorization Server]
    C -->|Bearer token| O[Orders API]
    C -->|Token aud=Billing API| AS
    C -->|Bearer token| B[Billing API]
    O --> D[(Orders DB)]
    B --> F[(Billing DB)]
~~~

Client xin token riêng cho mỗi API. Orders API chỉ nhận token có audience Orders API; Billing API chỉ nhận token có audience Billing API. Đây thường là lựa chọn dễ kiểm soát nhất khi client gọi nhiều API độc lập.

### 4.2. Client gọi qua gateway

~~~mermaid
flowchart LR
    C[Client] -->|Token aud=Gateway| G[API Gateway]
    G -->|Internal service identity| O[Orders API]
    G -->|Internal service identity| B[Billing API]
    O --> D[(Orders DB)]
    B --> F[(Billing DB)]
    AS[Authorization Server] -. issue .-> C
~~~

Token được cấp cho Gateway. Gateway xác minh audience và scope, sau đó gọi backend bằng cơ chế danh tính dịch vụ nội bộ được kiểm soát, chẳng hạn mTLS hoặc token riêng giữa gateway và backend.

Trong mô hình này, backend không nên nhận token có audience chỉ dành cho Gateway rồi tự coi nó là token hợp lệ của backend. Nếu backend cần xác minh access token end-to-end, token phải có audience dành cho backend hoặc Gateway phải lấy token mới phù hợp với backend.

### 4.3. Gateway chuyển tiếp token tới backend

~~~mermaid
flowchart LR
    C[Client] -->|Token aud=Gateway + API| G[API Gateway]
    G -->|Forward Bearer token| O[Orders API]
    G -->|Forward Bearer token| B[Billing API]
    AS[Authorization Server] -. issue .-> C
~~~

Cách này chỉ hợp lệ khi token được thiết kế rõ ràng để các backend nhận nó. Nếu token có nhiều audience, từng scope trong token phải có ý nghĩa với các resource tương ứng và policy phải loại bỏ mọi tổ hợp mơ hồ.

Không thêm hàng loạt audience vào token chỉ để tránh việc gateway xin token mới. Một token có nhiều audience làm tăng phạm vi replay nếu token bị lộ. Với gateway cần gọi nhiều backend, hãy cân nhắc token exchange hoặc xin token riêng cho từng backend.

## 5. Thiết kế audience URI ổn định

Audience thường được biểu diễn bằng URI định danh Resource Server hoặc API. Ví dụ:

~~~text
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/inventory/
https://gateway.example.com/
~~~

Audience là identifier trong security contract. Nó không bắt buộc phải là URL của một endpoint cụ thể hoặc một địa chỉ mà AS phải gọi tới.

Khi thiết kế audience:
- Dùng URI ổn định, có namespace thuộc quyền quản lý của tổ chức.
- Ưu tiên định danh ở cấp API/resource, không gắn với từng route nhỏ.
- Phân biệt các API độc lập ngay cả khi chúng cùng host.
- Không dùng hostname dev, IP nội bộ thay đổi hoặc URL tạm.
- Không đưa query string hoặc fragment vào resource identifier.
- Không tùy tiện đổi slash cuối, chữ hoa/thường hoặc path khi so sánh audience.
- Với API đa tenant, quyết định tenant nằm trong audience hay trong authorization context theo mô hình isolation.

Ví dụ nếu cùng host có nhiều API:

~~~text
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/admin/
~~~

Ba URI này là ba recipient khác nhau. Không nên rút gọn cả ba về `https://api.example.com/` nếu các API có ranh giới bảo mật hoặc nhóm vận hành khác nhau.

### 5.1. Audience theo tenant

Nếu token phải bị giới hạn vào một tenant resource cụ thể, audience có thể phản ánh định danh tenant:

~~~text
https://api.example.com/tenants/tenant-42/orders/
~~~

Cách này giúp phân biệt recipient theo tenant nhưng cần cân nhắc khả năng lộ cấu trúc định danh. Một lựa chọn khác là audience API cố định kết hợp claim tenant và policy membership. Dù chọn cách nào, Resource Server vẫn phải xác minh tenant ownership và không tin một claim tenant do client tự gửi.

## 6. Thiết kế scope theo API và thao tác

Scope nên mô tả hành động mà client được phép thực hiện tại API tương ứng. Ví dụ:

| API | Scope đọc | Scope ghi | Scope quản trị |
| --- | --- | --- | --- |
| Orders API | `orders.read` | `orders.write` | `orders.admin` |
| Billing API | `billing.invoices.read` | `billing.invoices.write` | `billing.admin` |
| Inventory API | `inventory.stock.read` | `inventory.stock.write` | `inventory.admin` |

Tên scope có namespace giúp người vận hành nhận biết scope thuộc API nào. Điều này cũng giúp AS xây dựng bảng mapping scope-to-audience và Resource Server áp dụng policy rõ ràng.

Một scope có thể bao hàm nhiều endpoint nếu chúng có cùng ý nghĩa quyền. Tránh tạo scope cho từng URL hoặc HTTP method khi không cần thiết; số lượng scope quá lớn sẽ làm consent, client registration và vận hành phức tạp.

Scope không phải role nội bộ. Role có thể được ánh xạ thành scope trong policy cấp token, nhưng hai khái niệm vẫn khác nhau:
- Role mô tả vị trí hoặc nhóm quyền của subject trong hệ thống.
- Scope mô tả quyền cụ thể mà client được cấp trong access token.
- Resource Server có thể cần kiểm tra thêm ownership, tenant hoặc trạng thái nghiệp vụ sau khi scope hợp lệ.

### 6.1. Scope phải có nghĩa đối với audience

Nếu token có:

~~~json
{
  "aud": ["https://api.example.com/orders/"],
  "scope": "orders.read billing.invoices.read"
}
~~~

thì `billing.invoices.read` không có ý nghĩa tại Orders API. Theo RFC 9068, các scope trong JWT access token phải có ý nghĩa với các resource được liệt kê trong audience.

AS nên từ chối tổ hợp scope/resource không tương thích. Không phát hành token chứa scope dư thừa chỉ vì client đã được đăng ký tất cả scope đó.

## 7. Đăng ký scope cho client trong RegisteredClient

Spring Authorization Server dùng `RegisteredClient` để khai báo tập scope mà client được phép yêu cầu. Ví dụ:

~~~java
@Bean
RegisteredClient registeredClient(
        PasswordEncoder passwordEncoder, Environment environment) {
    String clientSecret = environment.getRequiredProperty("app.clients.orders-web.secret");
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("orders-web")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri("https://orders.example.com/login/oauth2/code/oidc")
            .scope("orders.read")
            .scope("orders.write")
            .clientSettings(ClientSettings.builder()
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
~~~

Ví dụ trên chỉ minh họa client được phép yêu cầu hai scope của Orders API. `RegisteredClient` không tự định nghĩa scope nào thuộc audience nào. Ứng dụng cần policy bổ sung để ràng buộc client, scope và resource.

`clientSecret` phải được cấp từ secret manager hoặc cấu hình môi trường; không hard-code raw secret trong source code. Ví dụ cần import `org.springframework.core.env.Environment`.

Trong production:
- Không cấp `orders.write` cho client chỉ cần đọc.
- Không cấp `billing.invoices.read` cho client không có use case Billing.
- Tách client registration theo ứng dụng và trust boundary khi phù hợp.
- Kiểm tra consent và scope đã được Resource Owner chấp thuận.
- Dùng `JdbcRegisteredClientRepository` hoặc repository bền vững khác để duy trì registration.
- Quản lý secret qua secret manager và lưu giá trị đã encode theo cấu hình PasswordEncoder.

## 8. Xây dựng policy ràng buộc client, scope và audience

AS cần một policy trung tâm để trả lời:
- Client nào được phép truy cập audience nào?
- Scope nào thuộc audience đó?
- Client được yêu cầu một hay nhiều audience trong cùng token?
- Scope nào chỉ là OIDC scope, không phải API permission?
- Nếu client yêu cầu scope thuộc nhiều API, AS sẽ cấp nhiều token hay từ chối tổ hợp?

Ví dụ bảng policy:

| Client ID | Audience | Scope được phép |
| --- | --- | --- |
| `orders-web` | `https://api.example.com/orders/` | `orders.read`, `orders.write` |
| `billing-worker` | `https://api.example.com/billing/` | `billing.invoices.read`, `billing.invoices.write` |
| `ops-console` | `https://api.example.com/orders/` | `orders.read`, `orders.admin` |
| `ops-console` | `https://api.example.com/inventory/` | `inventory.stock.read`, `inventory.admin` |

Đây là policy ứng dụng; có thể lưu trong database hoặc configuration có version. `RegisteredClient.getScopes()` là allowlist scope theo client, còn policy resource phải kiểm tra thêm audience và quan hệ scope-resource.

### 8.1. Ví dụ service kiểm tra scope-to-audience

Đoạn code dưới đây minh họa policy phát hành một access token cho đúng một API. Nếu request chứa scope của nhiều API, policy từ chối để client xin token riêng:

~~~java
@Component
public class ResourceAudiencePolicy {

    private static final Map<String, String> SCOPE_TO_AUDIENCE = Map.of(
            "orders.read", "https://api.example.com/orders/",
            "orders.write", "https://api.example.com/orders/",
            "orders.admin", "https://api.example.com/orders/",
            "billing.invoices.read", "https://api.example.com/billing/",
            "billing.invoices.write", "https://api.example.com/billing/",
            "billing.admin", "https://api.example.com/billing/",
            "inventory.stock.read", "https://api.example.com/inventory/",
            "inventory.stock.write", "https://api.example.com/inventory/",
            "inventory.admin", "https://api.example.com/inventory/"
    );

    private static final Set<String> OIDC_SCOPES = Set.of(
            "openid", "profile", "email", "address", "phone", "offline_access"
    );

    private static final Map<String, Set<String>> CLIENT_AUDIENCES = Map.of(
            "orders-web", Set.of("https://api.example.com/orders/"),
            "billing-worker", Set.of("https://api.example.com/billing/"),
            "ops-console", Set.of(
                    "https://api.example.com/orders/",
                    "https://api.example.com/inventory/"
            )
    );

    public Set<String> resolveApiAudiences(
            RegisteredClient registeredClient,
            Set<String> authorizedScopes) {

        Set<String> allowedAudiences = CLIENT_AUDIENCES.getOrDefault(
                registeredClient.getClientId(), Set.of());

        Set<String> audiences = new LinkedHashSet<>();

        for (String scope : authorizedScopes) {
            String audience = SCOPE_TO_AUDIENCE.get(scope);

            if (audience == null) {
                if (OIDC_SCOPES.contains(scope)) {
                    continue;
                }
                throw invalidScope();
            }

            if (!allowedAudiences.contains(audience)) {
                throw invalidScope();
            }

            audiences.add(audience);
        }

        if (audiences.size() > 1) {
            throw invalidScope();
        }

        if (audiences.isEmpty() && (authorizedScopes.isEmpty()
                || authorizedScopes.stream().anyMatch(scope -> !OIDC_SCOPES.contains(scope)))) {
            throw invalidScope();
        }

        return Collections.unmodifiableSet(audiences);
    }

    private OAuth2AuthenticationException invalidScope() {
        return new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_SCOPE));
    }
}
~~~

Ví dụ giả định các import Spring Security/SAS cần thiết đã được khai báo. Policy bỏ qua OIDC scopes như `openid` và `profile` khi tính API audience. Nếu token chỉ có OIDC scopes, hàm trả về tập rỗng để caller giữ policy mặc định dành cho flow OIDC; Resource Server API vẫn không được coi client ID là audience API.

Với client gọi API, request phải có ít nhất một API scope đã map hoặc một `resource` đã được extension xử lý. Không để request API thiếu scope rơi về audience client ID mặc định. Token chỉ có OIDC scopes là trường hợp riêng phục vụ OIDC flow; nếu áp dụng RFC 9068 cho mọi JWT access token, cần định nghĩa default resource indicator phù hợp cho flow đó hoặc dùng token format/policy riêng.

Một triển khai thực tế nên lấy `CLIENT_AUDIENCES` và `SCOPE_TO_AUDIENCE` từ cấu hình có version hoặc policy store, thay vì duy trì map tĩnh trong source code.

## 9. Tùy chỉnh audience của JWT access token trong Spring Authorization Server

Spring Authorization Server 1.5.8 cung cấp `OAuth2TokenCustomizer<JwtEncodingContext>` để tùy chỉnh claims trước khi JWT được encode. `JwtEncodingContext` có thông tin RegisteredClient, authorized scopes, authorization grant và authorization liên quan.

`JwtGenerator` mặc định sử dụng client ID làm audience của JWT. Đối với access token dành cho API, ứng dụng cần thay audience mặc định bằng resource identifier đã được policy phê duyệt.

Client ID là định danh client, không phải mặc nhiên là audience của API. Nếu triển khai JWT Access Token Profile theo RFC 9068, AS cần phát hành `aud` là resource indicator đã được xác định. Khi không có `resource` parameter, policy phải chọn default resource theo scope hoặc cấu hình; nếu scope trỏ tới nhiều default resource khác nhau thì từ chối request mơ hồ.

Ví dụ:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        ResourceAudiencePolicy audiencePolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        Set<String> audiences = audiencePolicy.resolveApiAudiences(
                context.getRegisteredClient(),
                context.getAuthorizedScopes()
        );

        if (!audiences.isEmpty()) {
            context.getClaims().audience(audiences);
            // Chỉ đặt typ khi token này tuân thủ JWT Access Token Profile RFC 9068.
            context.getJwsHeader().type("at+jwt");
        }
    };
}
~~~

`context.getClaims().audience(...)` đặt lại claim `aud` trong JWT. Khi scope map tới một API, token nhận audience URI của API đó thay cho client ID mặc định.

Các điểm cần lưu ý:
- Chỉ sửa audience cho access token; không thay audience của ID Token bằng API audience.
- Dùng `getAuthorizedScopes()` để dựa trên scope đã được AS chấp thuận, không đọc raw scope từ HTTP request.
- Kiểm tra cả client allowlist và scope-to-resource policy trước khi phát hành token.
- Nếu request chứa scope thuộc nhiều API, policy ví dụ từ chối thay vì tạo token có nhiều audience.
- Nếu ứng dụng đã có một `OAuth2TokenCustomizer<JwtEncodingContext>`, hãy hợp nhất logic vào một bean phù hợp; Spring Authorization Server hướng dẫn chỉ khai báo một customizer bean kiểu này.
- Đây là ví dụ cho JWT/self-contained access token. Opaque/reference token cần customizer và token generator tương ứng.

Việc đặt header `typ` thành `at+jwt` là yêu cầu khi chọn tuân thủ RFC 9068; chỉ thêm claim `aud` không tự làm JWT trở thành token theo profile này. Resource Server triển khai RFC 9068 cũng phải kiểm tra `typ` là `at+jwt` hoặc `application/at+jwt`, bên cạnh issuer, audience, chữ ký và thời hạn. Nếu không chọn profile RFC 9068, hãy công bố và áp dụng nhất quán token profile riêng của hệ thống.

Không nên dùng token customizer làm nơi duy nhất kiểm tra policy nếu ứng dụng cần trả lỗi chi tiết tại authorization request. Có thể kiểm tra scope/resource sớm trong authorization/token request processor, sau đó customizer dùng lại policy để gắn audience cuối cùng.

## 10. Resource Indicator theo RFC 8707

RFC 8707 định nghĩa request parameter `resource` để client chỉ rõ protected resource mà nó muốn truy cập. Giá trị phải là absolute URI, không có fragment. RFC cho phép nhiều lần xuất hiện của `resource`, nhưng khuyến nghị dùng một resource trong đa số trường hợp.

Ví dụ authorization request:

~~~http
GET /oauth2/authorize?
    response_type=code&
    client_id=orders-web&
    redirect_uri=https%3A%2F%2Forders.example.com%2Flogin%2Fcallback&
    scope=orders.read&
    resource=https%3A%2F%2Fapi.example.com%2Forders%2F&
    state=STATE_VALUE
~~~

Ví dụ token request nếu client gửi resource tại Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Forders.example.com%2Flogin%2Fcallback&
resource=https%3A%2F%2Fapi.example.com%2Forders%2F
~~~

`resource` chỉ là yêu cầu của client. AS cần:
1. Parse URI và xác nhận absolute URI.
2. Từ chối URI có fragment; thông thường không chấp nhận query component nếu không có use case rõ ràng.
3. So sánh với resource registry/allowlist đã cấu hình.
4. Xác minh client được phép yêu cầu resource đó.
5. Xác minh mọi scope đã yêu cầu có ý nghĩa tại resource.
6. Giới hạn resource được yêu cầu theo grant/consent đã được chấp thuận.
7. Gắn resource đã được duyệt vào authorization/token context.
8. Phát hành token với audience tương ứng.

Không fetch URL do client gửi để “kiểm tra API có tồn tại” hoặc tải metadata tùy ý. Resource URI là identifier; nó không phải chỉ thị để Authorization Server gọi mạng tới địa chỉ do client kiểm soát.

### 10.1. Spring Authorization Server và resource parameter

Spring Authorization Server 1.5.8 cung cấp extension points để tùy chỉnh request processing tại Authorization Endpoint và Token Endpoint. Không nên giả định rằng chỉ thêm tham số `resource` vào request là SAS tự động xác minh resource và thay claim `aud`.

Nếu ứng dụng triển khai RFC 8707:
- Bổ sung logic converter/provider hoặc request validation tại endpoint phù hợp để parse `resource`.
- Áp dụng resource registry và client/resource policy.
- Lưu resource đã được duyệt vào `OAuth2Authorization` attributes đối với Authorization Code flow.
- Khi phát hành token, đọc lựa chọn đã được lưu từ `OAuth2TokenContext.getAuthorization()` thay vì tin một giá trị mới từ request.
- Với Client Credentials, đưa resource đã được kiểm tra vào custom grant/request context trước khi token được tạo.
- Với Refresh Token, chỉ cho phép resource mới nằm trong tập resource của grant ban đầu hoặc tập con được policy cho phép.

`OAuth2Authorization` có trường attributes để lưu state bổ sung. `OAuth2TokenContext` cung cấp `getAuthorization()` và `getAuthorizationGrant()`, nhờ đó custom token generation có thể truy cập resource selection đã được xác minh.

## 11. Lưu resource đã duyệt trong Authorization Code flow

Với Authorization Code, resource được chọn tại authorization request phải được ràng buộc với authorization code. Không nên để client đổi code rồi tự ý thay resource sang một API khác mà Resource Owner chưa chấp thuận.

Ví dụ mô hình state:

~~~text
OAuth2Authorization
-------------------
registered_client_id
principal_name
authorized_scopes
attributes:
  approved_resource = https://api.example.com/orders/
  resource_policy_version = 7
tokens:
  authorization_code
  access_token
  refresh_token
~~~

Luồng xử lý:
1. Authorization Endpoint nhận `resource` và scope.
2. Policy kiểm tra client, user consent và quan hệ resource-scope.
3. Authorization Server lưu `approved_resource` trong authorization attributes.
4. Client đổi authorization code tại Token Endpoint.
5. Token generator/customizer đọc resource đã lưu và đặt `aud`.
6. Refresh Token chỉ được dùng để lấy token cho resource đã được grant cho phép.

Nếu Token Request có `resource` khác với resource đã lưu trong authorization code, AS phải kiểm tra yêu cầu mới có phải tập con được phép hay không. Nếu không, từ chối bằng lỗi phù hợp như `invalid_target` hoặc `invalid_scope` theo semantics của extension.

## 12. Client Credentials và nhiều resource

Trong Client Credentials flow không có Resource Owner để consent. AS phải dựa trên client registration, resource allowlist và policy service-to-service.

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_BILLING_WORKER
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=billing.invoices.read&
resource=https%3A%2F%2Fapi.example.com%2Fbilling%2F
~~~

AS xác minh:
- Client đã xác thực.
- Client được cấp `client_credentials`.
- Client có scope `billing.invoices.read`.
- Audience Billing API được allowlist cho client đó.
- Policy workload/tenant cho phép thao tác này.

Client Credentials token đại diện cho client/workload, không phải người dùng cuối. Không đưa user roles hoặc user subject vào token theo giả định của Authorization Code flow.

Nếu một worker cần gọi cả Billing API và Inventory API, hãy cấp hai token với audience tương ứng. Nếu dùng một token nhiều audience, phải chứng minh mọi scope đều có nghĩa đối với tất cả resource được ghi trong `aud` và việc chia sẻ token không mở rộng quyền ngoài ý muốn.

## 13. Thiết kế audience cho API Gateway

Khi Gateway là recipient duy nhất của access token, audience có thể là:

~~~text
https://gateway.example.com/
~~~

Gateway kiểm tra token, scope và policy định tuyến. Sau đó Gateway gọi backend bằng một trong các mô hình:

| Mô hình | Token/credential gửi tới backend | Điều kiện |
| --- | --- | --- |
| Gateway service identity | mTLS hoặc credential riêng của gateway | Backend tin cậy workload identity của gateway |
| Downstream token exchange | Token mới có audience của backend | AS hỗ trợ token exchange và policy delegation |
| Forward original token | Token có audience chứa backend | Backend tự xác minh issuer, audience, scope và thời hạn |

Nếu token chỉ có `aud=https://gateway.example.com/`, Orders API phải từ chối token đó. Gateway không thể thay đổi claim `aud` bằng cách sửa header hoặc viết lại token; việc đó làm mất tính toàn vẹn chữ ký.

### 13.1. Gateway kiểm tra route và scope

Ví dụ route policy:

| Route | Audience token | Scope bắt buộc |
| --- | --- | --- |
| `GET /orders/**` | Gateway | `orders.read` |
| `POST /orders/**` | Gateway | `orders.write` |
| `GET /billing/**` | Gateway | `billing.invoices.read` |

Gateway có thể map route tới backend, nhưng scope phải có ý nghĩa với API đích. Backend vẫn cần xác thực workload identity hoặc token dành cho chính nó nếu backend có thể được truy cập ngoài gateway.

### 13.2. Khi gateway forward token

Nếu gateway forward nguyên Bearer token:
- Token phải có audience chứa backend nhận request.
- Backend phải tự xác minh chữ ký/issuer/audience/expiry và scope.
- Gateway không được thêm audience hoặc scope bằng cách sửa token.
- Cần đánh giá nguy cơ token bị replay tại mọi API có mặt trong `aud`.
- Không forward token tới service không nằm trong audience.

Nếu gateway cần gọi nhiều backend nhưng token ban đầu chỉ dành cho gateway, hãy dùng token exchange hoặc service credential riêng. Không nới audience ban đầu chỉ để thuận tiện định tuyến.

## 14. Resource Server xác minh audience trong Spring Security

Mỗi API cần biết audience identifier mà nó chấp nhận. Ví dụ Orders API:

~~~java
@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.example.com";
    String jwkSetUri = "https://auth.example.com/oauth2/jwks";
    String expectedAudience = "https://api.example.com/orders/";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The access token is not intended for Orders API",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    OAuth2TokenValidator<Jwt> typeValidator = jwt -> {
        Object typ = jwt.getHeaders().get("typ");
        if ("at+jwt".equals(typ) || "application/at+jwt".equals(typ)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "JWT is not an OAuth 2.0 access token", null));
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            issuerAndTimeValidator,
            audienceValidator,
            typeValidator
    ));

    return decoder;
}
~~~

Sau đó gắn decoder vào Resource Server:

~~~java
@Bean
SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(ordersJwtDecoder()))
        );

    return http.build();
}
~~~

Ví dụ giả định các bean/import còn lại đã được khai báo. `JwtValidators.createDefaultWithIssuer` xác minh các validator mặc định như issuer và thời gian; audience validator bổ sung điều kiện recipient.

Spring Security `JwtGrantedAuthoritiesConverter` mặc định ánh xạ scope thành authority có prefix `SCOPE_`. Vì vậy `orders.read` trở thành `SCOPE_orders.read` để dùng trong authorization rule.

Mỗi API nên cấu hình audience riêng. Không dùng một decoder chấp nhận mọi audience của toàn bộ hệ thống nếu các API có trust boundary khác nhau.

## 15. Audience và scope trong token opaque

Opaque/reference token không cho Resource Server tự đọc JWT claims. Resource Server gửi token tới Token Introspection Endpoint của AS để lấy trạng thái và metadata.

RFC 8707 cho phép audience restriction được biểu diễn trong trường `aud` cấp cao nhất của introspection response. Resource Server vẫn phải kiểm tra:
- `active` là true.
- `iss` là issuer được tin cậy nếu policy yêu cầu.
- `aud` chứa resource identifier của API hiện tại.
- `scope` có quyền cần cho endpoint.
- Các claim bổ sung như tenant hoặc client ID đáp ứng policy.

Trong SAS, `OAuth2TokenCustomizer<JwtEncodingContext>` chỉ tùy chỉnh JWT. Nếu dùng opaque access token, cần cấu hình `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` với `OAuth2AccessTokenGenerator` và bảo đảm introspection response trả audience đã được policy duyệt.

Ví dụ phần customizer cho reference token:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueAccessTokenCustomizer(
        ResourceAudiencePolicy audiencePolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        Set<String> audiences = audiencePolicy.resolveApiAudiences(
                context.getRegisteredClient(),
                context.getAuthorizedScopes()
        );

        if (!audiences.isEmpty()) {
            context.getClaims().audience(new ArrayList<>(audiences));
        }
    };
}
~~~

Customizer này cần được gắn với `OAuth2AccessTokenGenerator` đang dùng. Khi tự cấu hình `OAuth2TokenGenerator`, gọi `setAccessTokenCustomizer(...)` trên generator opaque; nếu generator mặc định được SAS cấu hình, kiểm tra cách Spring Boot/SAS kết nối bean customizer trong phiên bản ứng dụng.

Không giả định đổi token format từ JWT sang opaque sẽ tự động giữ nguyên mọi claim custom. Hãy kiểm thử introspection response trên đúng generator và authorization service đang dùng.

## 16. Một request có nhiều audience: khi nào nên cho phép?

RFC 8707 cho phép client gửi nhiều resource indicators. RFC 9068 yêu cầu AS không phát hành JWT access token nếu quyền được cấp trở nên mơ hồ.

Một token nhiều audience chỉ nên được phát hành khi:
- Từng resource đã được xác thực và allowlist.
- Mỗi scope có thể liên hệ rõ ràng với resource tương ứng.
- Các Resource Server có cùng trust boundary phù hợp.
- Client thực sự cần dùng cùng token ở nhiều resource.
- Rủi ro replay và phạm vi token được chấp nhận.
- Có test chứng minh mỗi API chỉ thực hiện đúng quyền của nó.

Ví dụ token:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": [
    "https://api.example.com/orders/",
    "https://api.example.com/inventory/"
  ],
  "scope": "orders.read inventory.stock.read",
  "client_id": "ops-console"
}
~~~

Orders API chỉ sử dụng `orders.read`; Inventory API chỉ sử dụng `inventory.stock.read`. Nếu một scope có thể bị diễn giải tại nhiều API, hoặc một API không thể xác định scope nào áp dụng cho mình, AS nên từ chối tổ hợp thay vì phát hành token.

Trong đa số hệ thống, một access token cho một resource giúp giảm phạm vi rủi ro và dễ quan sát hơn. Client có thể xin nhiều token độc lập.

## 17. Downstream token exchange và delegation

Một gateway hoặc API tổng hợp đôi khi cần gọi backend thay mặt user. Có thể dùng OAuth 2.0 Token Exchange theo RFC 8693 nếu AS triển khai flow này.

Ví dụ về ý tưởng:
1. Client nhận token dành cho Gateway.
2. Gateway xác thực token đầu vào và xác định backend cần gọi.
3. Gateway dùng credential/workload identity của mình để yêu cầu token mới.
4. AS kiểm tra subject token, actor, client, resource và scope.
5. AS phát hành token ngắn hạn có audience của backend và scope tối thiểu.
6. Backend xác minh token mới như một Resource Server độc lập.

Token exchange không phải cách gateway tự sửa `aud` của token hiện có. AS phải phát hành token mới và ghi nhận delegation context theo policy.

Nếu backend chỉ cần biết request đến từ Gateway và không cần user delegation, mTLS/service identity có thể đơn giản hơn token exchange. Chọn mô hình theo nhu cầu authorization và audit.

## 18. Lỗi giao thức và cách phản hồi

| Tình huống | Lỗi gợi ý | Ý nghĩa |
| --- | --- | --- |
| Resource URI không hợp lệ/không biết | `invalid_target` | Resource indicator sai hoặc không được AS hỗ trợ |
| Scope không được client cấp | `invalid_scope` | Client không được phép xin scope đó |
| Scope không thuộc resource | `invalid_scope` hoặc `invalid_target` | Tổ hợp scope/resource không hợp lệ theo policy |
| Client không được dùng resource | `invalid_target` | Client không nằm trong allowlist resource |
| Token có audience không khớp API | `invalid_token` | Resource Server từ chối token |
| Token hết hạn hoặc chữ ký sai | `invalid_token` | Token không hợp lệ |
| Token hợp lệ nhưng thiếu scope | `insufficient_scope` | Token thiếu quyền cho endpoint |

Không tiết lộ chi tiết nội bộ của resource registry, policy hoặc tenant trong error response công khai. Ghi log mã policy, client ID, resource identifier đã chuẩn hóa và correlation ID; không ghi raw access token.

## 19. Ma trận kiểm thử audience và scope

| Tình huống | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Orders audience | Xin `orders.read` | Token có audience Orders API |
| Billing audience | Xin `billing.invoices.read` | Token có audience Billing API |
| Wrong API | Gửi Orders token tới Billing API | Billing API trả `invalid_token` |
| Scope escalation | Client chỉ có `orders.read` xin `orders.admin` | AS trả `invalid_scope` |
| Scope/resource mismatch | Xin `billing.invoices.read` với Orders resource | AS từ chối |
| Unknown resource | Gửi resource URI ngoài registry | AS trả `invalid_target` |
| Non-absolute resource | Gửi relative URI | AS từ chối |
| Fragment in resource | Gửi URI có `#fragment` | AS từ chối |
| Multiple resources | Xin Orders và Billing trong một request | Từ chối theo policy một resource/token hoặc chỉ cấp nếu policy multi-audience rõ ràng |
| Gateway-only token | Forward token chỉ có audience Gateway tới Orders API | Orders API từ chối |
| Backend token | Exchange token sang Orders audience | Orders API chấp nhận nếu scope hợp lệ |
| Missing audience | Token không có audience API | API từ chối |
| Wrong token type | API áp dụng RFC 9068 nhận JWT có `typ` khác `at+jwt`/`application/at+jwt` | Resource Server trả `invalid_token` |
| Client not allowed | Client xin audience ngoài allowlist | AS từ chối |
| OIDC-only scope | Xin `openid profile` | Không tự cấp API audience hoặc API permission |
| Ambiguous default resource | Scope trỏ tới nhiều default resource khi không có `resource` | AS từ chối tổ hợp mơ hồ |
| Opaque token | Introspection token Orders tại Billing API | Billing API kiểm tra `aud` và từ chối |
| Expired token | Gửi token đã hết hạn | Resource Server trả `invalid_token` |
| Tenant mismatch | Token có tenant không thuộc request/resource | API từ chối theo tenant policy |
| Refresh token resource | Xin refresh token cho resource ngoài grant ban đầu | AS từ chối |
| Gateway route scope | Gọi POST orders với token chỉ có `orders.read` | Gateway/API từ chối |

Kiểm thử cần xác minh cả token response, JWT claims hoặc introspection response và quyết định tại từng API. Một token có chữ ký hợp lệ chưa chứng minh nó được phép tới đúng resource.

## 20. Bài tập tình huống

Một hệ thống thương mại điện tử có Orders API, Billing API và Inventory API. Client `ops-console` cần đọc đơn hàng và tồn kho. Client `billing-worker` chỉ cần đọc hóa đơn. Tất cả API đứng sau một Gateway.

Các audience:

~~~text
https://gateway.example.com/
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/inventory/
~~~

Các scope:

~~~text
orders.read
orders.write
billing.invoices.read
billing.invoices.write
inventory.stock.read
inventory.stock.write
~~~

Hãy phân tích:

1. Khi `ops-console` gọi Gateway để đọc Orders, token nên có audience nào?
2. Nếu Gateway forward token tới Orders API, audience cần đáp ứng điều kiện gì?
3. Vì sao `billing-worker` không nên nhận `orders.read`?
4. Nếu client xin `orders.read` và `inventory.stock.read` trong một request, AS nên cấp một token nhiều audience hay từ chối?
5. Khi nào nên dùng token exchange?
6. Nếu token là opaque, Resource Server kiểm tra audience ở đâu?
7. Scope nào cần thiết cho thao tác `POST /orders`?
8. Làm thế nào kiểm thử token Gateway-only bị Orders API từ chối?
9. Nếu tenant `tenant-42` chỉ có quyền Orders, cần ràng buộc tenant và audience ra sao?
10. Đề xuất cách quan sát request bị từ chối do sai audience mà không ghi raw token vào log.

**Gợi ý:** Tách audience Gateway khỏi audience của từng backend. Nếu backend tự xác minh token, token phải được phát hành cho backend đó. Map từng scope sang một API và từ chối scope/resource không tương thích. Chỉ dùng multi-audience khi scope có thể được gắn rõ ràng với từng resource; nếu không, xin token riêng hoặc dùng token exchange.

## 21. Checklist triển khai production

1. **Resource registry:** định nghĩa URI ổn định cho từng API, gateway và tenant resource cần phân biệt.
2. **Scope taxonomy:** đặt tên scope theo API và thao tác; tránh trùng nghĩa giữa các API.
3. **Client allowlist:** giới hạn audience và scope theo từng RegisteredClient.
4. **Scope-resource binding:** duy trì policy map scope tới audience và client.
5. **Resource parameter:** nếu dùng RFC 8707, parse absolute URI, reject fragment và validate theo allowlist.
6. **Authorization persistence:** lưu resource đã duyệt vào authorization attributes để ràng buộc với code/refresh token.
7. **JWT customization:** đặt claim `aud` cho access token theo policy; không sửa audience ID Token.
8. **Default audience:** hiểu audience client ID mặc định của JwtGenerator và thay nó khi token dành cho API.
9. **Gateway:** xác định gateway là recipient hay chỉ là router; không forward token sai audience.
10. **Backend validation:** mỗi Resource Server kiểm tra issuer, signature, expiry, audience và scope.
11. **Opaque token:** bảo đảm introspection trả audience và Resource Server kiểm tra trường đó.
12. **Multi-resource:** chỉ cấp token nhiều audience khi scope-resource relationship không mơ hồ.
13. **Token exchange:** phát hành token downstream mới với audience/scope tối thiểu khi cần delegation.
14. **Tenant:** xác minh tenant membership/ownership ngoài việc kiểm tra audience.
15. **Lifecycle:** giới hạn TTL, revoke token và cập nhật policy khi client/resource bị thu hồi.
16. **Observability:** log policy decision, client, resource, scope và correlation ID; không log raw token.
17. **Testing:** kiểm tra positive/negative cases ở AS, Gateway, API và introspection.
18. **Documentation:** công bố resource identifier, scope, error semantics và quy trình onboarding API.

## 22. Tài liệu chuẩn và Spring cần đối chiếu

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): scope và authorization/token request.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): bảo vệ bearer token và chống token redirect.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): introspection response cho opaque/reference token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegation và token dành cho downstream resource.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): tham số `resource`, audience restriction và `invalid_target`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): claim `aud`, `scope`, validation và quan hệ scope-resource.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, OAuth2TokenContext và OAuth2TokenCustomizer.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): extension points của Authorization Endpoint và Token Endpoint.
- [Spring Authorization Server 1.5.8 — Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): cấu hình OAuth2TokenCustomizer cho JWT access token.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, JwtAuthenticationConverter và JWT validation.

**Ghi nhớ:** Audience xác định API nào được phép nhận access token; scope xác định thao tác nào được phép tại API đó; resource indicator là yêu cầu của client để AS biết token sẽ được dùng ở đâu. AS phải kiểm tra client, resource và scope như một policy thống nhất rồi phát hành token với audience phù hợp. Với nhiều API, ưu tiên token riêng cho từng resource; nếu dùng gateway, phân biệt token dành cho gateway với token dành cho backend. Mỗi Resource Server phải tự xác minh audience và scope trước khi thực thi request.
