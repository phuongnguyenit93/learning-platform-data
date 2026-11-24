# Token exchange giữa service: ủy quyền đúng ngữ cảnh khi gọi service-to-service

## 1. Bối cảnh và mục tiêu học tập

Trong hệ thống microservices, một request thường đi qua nhiều dịch vụ. Ví dụ người dùng gọi **Orders Service** để xem chi tiết đơn hàng; Orders Service cần gọi **Inventory Service** để lấy trạng thái tồn kho. Access token do người dùng mang tới Orders Service có thể được cấp với `aud=orders-api`; token đó **không mặc nhiên được phép** sử dụng tại Inventory Service. Vấn đề đặt ra là làm sao để Orders Service thực hiện lời gọi tiếp theo mà vẫn giữ được danh tính, ngữ cảnh ủy quyền và nguyên tắc quyền tối thiểu.

**OAuth 2.0 Token Exchange** (RFC 8693) là một cơ chế cho phép một client được tin cậy đề nghị authorization server hoặc security token service (STS) trao đổi token hiện có lấy token khác phù hợp với tài nguyên đích, quyền truy cập và quan hệ đại diện. Cơ chế này đặc biệt hữu ích trong các lời gọi **service-to-service** đi qua nhiều ranh giới tin cậy.

Bài thuộc chương **Service to service** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: nắm mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access token, refresh token; hiểu xác thực, phân quyền, OAuth 2.0/OIDC; kiểm tra claims, scope, audience; lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại. Trọng tâm của bài là **token exchange giữa service**.

Sau khi học xong, bạn có thể:

1. Giải thích vì sao **chuyển tiếp nguyên access token** có thể sai audience hoặc mở rộng phạm vi tin cậy.
2. Phân biệt **token relay**, **token exchange**, **client credentials**, **delegation** và **impersonation**.
3. Đọc được request/response theo RFC 8693 và xác định vai trò của `subject_token`, `actor_token`, `audience`, `resource` và `scope`.
4. Thiết kế chuỗi lời gọi A → B → C sao cho access token mới dành riêng cho C và quyền không bị nâng tùy tiện.
5. Xử lý an toàn lỗi, bộ nhớ đệm, vòng đời token, thu hồi, DPoP/mTLS, log và kiểm thử tích hợp.

## 2. Bài toán: một access token không phải vé đi qua mọi service

Giả sử hệ thống gồm các thành phần:

| Thành phần | Vai trò | Phạm vi tin cậy |
| --- | --- | --- |
| **Client** (web/mobile) | Xin access token và gọi Orders Service | Chỉ được trình bày token cho tài nguyên mà token được cấp. |
| **Authorization Server / STS** | Phát hành, kiểm tra chính sách và trao đổi token | Là nơi quyết định có được ủy quyền gọi tiếp hay không. |
| **Orders Service (B)** | Resource server nhận lời gọi của client, đồng thời là OAuth client khi gọi tiếp | Phải kiểm token đầu vào và xác thực chính nó với STS khi exchange. |
| **Inventory Service (C)** | Resource server mà Orders Service muốn gọi | Chỉ chấp nhận access token dành cho Inventory và tự kiểm quyền. |

Client gửi access token có các claims giả định sau:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "web-client",
  "scope": "orders:read",
  "exp": 1893456000
}
```

Nếu Orders Service chuyển trực tiếp token này sang Inventory Service, Inventory Service chuẩn xác sẽ **từ chối** vì `aud=orders-api`, trong khi nó yêu cầu `aud=inventory-api`. Đây không phải lỗi cần sửa bằng cách bỏ kiểm tra `aud` ở C. Audience là ranh giới xác định token được phát hành cho resource server nào; chỉ có chữ ký hợp lệ và cùng issuer là **chưa đủ**.

Hướng phù hợp là: Orders Service xác thực access token đầu vào, xác định lời gọi cần thực hiện, sau đó sử dụng token exchange để yêu cầu **token mới** cho `inventory-api` với phạm vi quyền giới hạn, nếu STS cho phép.

## 3. Tổng quan luồng OAuth 2.0 Token Exchange

```mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant B as Orders Service (B)
    participant AS as Authorization Server / STS
    participant C as Inventory Service (C)

    U->>B: GET /orders/123; Bearer token_B (aud=orders-api)
    B->>B: Xác minh token_B, audience, scope và quyền trên order
    B->>AS: Token exchange: subject_token=token_B, audience=inventory-api
    Note over B,AS: B xác thực OAuth client; yêu cầu scope=inventory:read
    AS->>AS: Kiểm tra token_B, danh tính B và policy ủy quyền
    AS-->>B: token_C (aud=inventory-api; scope=inventory:read)
    B->>C: GET /inventory/items/sku-1; Bearer token_C
    C->>C: Kiểm issuer, signature/introspection, aud, scope và policy
    C-->>B: Trạng thái tồn kho được phép
    B-->>U: Kết quả tổng hợp đơn hàng
```

**Đọc sơ đồ theo ba ranh giới:**

1. **Client → Orders:** Token đầu vào là credential truy cập Orders. Orders là **resource server** ở chặng này.
2. **Orders → STS:** Orders đóng vai **OAuth client** được xác thực, gửi `subject_token` và yêu cầu token cho Inventory. STS phải kiểm tra **cả** token đầu vào, danh tính client gọi exchange và policy.
3. **Orders → Inventory:** Orders sử dụng **token mới**, được cấp cho `inventory-api`. Inventory tự xác thực và phân quyền token mới; không cần nhận token_B của client.

Tên `token_B`/`token_C` dùng để dễ hình dung, không phải tên chuẩn của giao thức. Việc exchange **không có nghĩa** token_B tự động bị thu hồi, không đảm bảo mọi STS đều hỗ trợ RFC 8693 và không mặc nhiên bảo toàn mọi claim của token cũ.

## 4. Ba chiến lược service-to-service và cách chọn

| Chiến lược | Credential gửi tới C | Phù hợp khi | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Token relay** | Chuyển nguyên access token của client/B | Token ban đầu **đã** có audience hợp lệ cho C, quyền và thiết kế tin cậy cho phép | Nguy cơ sai audience hoặc lộ token sang dịch vụ ngoài phạm vi; không thể đổi claims bằng cách sửa JWT. |
| **Token exchange** | Access token **mới** do STS cấp cho C | B gọi C thay người dùng; cần token đúng audience, scope và danh tính actor | Cần STS hỗ trợ; client B và subject phải được policy cho phép exchange. |
| **Client credentials** | Token đại diện **chính B** | B gọi C để thực hiện công việc hệ thống không cần quyền người dùng | Không tự thể hiện người dùng cuối; không được dùng thay cho việc ủy quyền hành động của user. |

Ví dụ đọc trạng thái hệ thống (`GET /internal/health`) có thể chỉ cần service token của Orders. Ngược lại, việc đặt hàng thay `user-42` thường cần ngữ cảnh ủy quyền của người dùng và một cơ chế delegation rõ ràng; dùng client credentials rồi tự gắn `X-User-Id: user-42` vào request là không đủ để C tin rằng hành động đã được người dùng ủy quyền.

## 5. Token exchange theo RFC 8693: tham số và phản hồi

### 5.1. Các tham số yêu cầu

Token exchange sử dụng **token endpoint** của authorization server, thường với HTTP `POST` và body `application/x-www-form-urlencoded`. RFC 8693 định nghĩa grant type:

`urn:ietf:params:oauth:grant-type:token-exchange`

| Tham số | Vai trò | Ghi chú |
| --- | --- | --- |
| `grant_type` | Xác định yêu cầu token exchange | Bắt buộc; giá trị URI như trên. |
| `subject_token` | Token biểu diễn chủ thể đang được trao đổi | Bắt buộc; có thể là access token JWT hoặc opaque tùy STS. |
| `subject_token_type` | Loại token ở `subject_token` | Bắt buộc; phổ biến là `urn:ietf:params:oauth:token-type:access_token`. |
| `actor_token` | Token biểu diễn actor đang hành động thay chủ thể | Tùy chọn; chỉ dùng khi profile/policy hỗ trợ và cần ngữ cảnh actor rõ ràng. |
| `actor_token_type` | Loại actor token | Bắt buộc **nếu** gửi `actor_token`. |
| `requested_token_type` | Loại token muốn nhận | Tùy chọn; thường yêu cầu OAuth access token. |
| `audience` | Định danh logic của đích nhận token | Ví dụ `inventory-api`; STS quyết định có chấp nhận hay không. |
| `resource` | URI tài nguyên đích | Ví dụ `https://inventory.example.internal/`; có thể được dùng thay hoặc kết hợp audience theo policy STS. |
| `scope` | Các quyền được yêu cầu cho token mới | Ví dụ `inventory:read`; yêu cầu **không tự động** được chấp thuận. |

OAuth client B còn phải **xác thực với token endpoint** theo cơ chế phù hợp với cấu hình STS, ví dụ `private_key_jwt`, mTLS client authentication hoặc client secret được quản lý an toàn. `subject_token` một mình **không** chứng minh B là bên được phép thực hiện exchange. Không bao giờ để một service bất kỳ tự nhận quyền exchange với token mà nó tình cờ có được.

### 5.2. HTTP request minh họa

Ví dụ request sau đã lược bớt các header và chi tiết xác thực tùy nhà cung cấp. Các placeholder không chứa token thật:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-placeholder>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<access-token-for-orders>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=inventory-api
&scope=inventory%3Aread
```

Trong HTTP thực tế, các dòng body trên phải ghép thành **một body URL-encoded hợp lệ**; dấu xuống dòng ở đây chỉ để dễ đọc. Thư viện HTTP/OAuth nên thực hiện URL encoding chính xác. Header Basic chỉ là **một** lựa chọn xác thực client để minh họa; không đặt `client_secret` trong mã nguồn, shell history, cấu hình công khai hoặc log.

Nếu STS cho phép, phản hồi thành công có thể như sau:

```json
{
  "access_token": "<new-access-token-for-inventory>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 180,
  "scope": "inventory:read"
}
```

Theo RFC 8693, `issued_token_type` biểu thị **loại token đã phát hành**, còn `token_type` mô tả cách sử dụng token ở phía client (ví dụ Bearer). Một `issued_token_type=access_token` không có nghĩa token nhất định là JWT: nó cũng có thể là opaque token. `expires_in` là thời gian hiệu lực tính bằng giây từ lúc phản hồi; token có thể chứa claims riêng theo profile của authorization server. **Không** ghi `access_token` hoặc `subject_token` từ request/response này vào log.

### 5.3. Phân biệt `subject_token`, `actor_token` và xác thực client

- `subject_token` nêu chủ thể/credential đang được đưa vào phép trao đổi. Khi B đang xử lý request của `user-42`, nó có thể là token_B dành cho Orders Service.
- `actor_token` là một đầu vào **tùy chọn** để STS nhận diện một actor trong cấu hình delegation; không phải mọi luồng exchange đều dùng tham số này.
- **Client authentication** xác minh *ứng dụng nào* gọi token endpoint. Nó là một kiểm tra độc lập với thông tin chủ thể trong `subject_token` hoặc actor được diễn đạt qua `actor_token`.
- `act` claim trong token mới (nếu được STS phát hành theo profile hỗ trợ) có thể biểu diễn actor đang đại diện chủ thể. **Không tự bổ sung `act`** vào JWT do STS ký, và không giả định mọi token exchange đều có claim này.

Authorization server có thể dùng danh tính client được xác thực làm đầu vào cho chính sách của exchange dù request **không** mang `actor_token`. Việc có cần token actor riêng, claim `act`, quan hệ delegation hay impersonation là hợp đồng bảo mật của STS và resource server, không thể suy từ riêng `grant_type`.

## 6. Delegation và impersonation: ai thực sự đang hành động?

### 6.1. Delegation (hành động thay một chủ thể)

Trong **delegation**, token mới có thể thể hiện cả chủ thể ban đầu (`sub=user-42`) và actor được cho phép (`orders-service`). Với token định dạng JWT, một cấu trúc **minh họa** sau có thể được STS phát hành:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "inventory-api",
  "scope": "inventory:read",
  "act": {
    "sub": "orders-service"
  },
  "exp": 1893452700
}
```

`act` là claim có ý nghĩa khi hệ sinh thái thống nhất cách đánh giá và STS đã **ký hoặc xác nhận** nó. Inventory Service có thể áp chính sách như: `user-42` được đọc tồn kho; `orders-service` là actor được ủy quyền gọi Inventory trong luồng đơn hàng. Không dùng `sub` hay `act` lấy từ JSON giải mã chưa xác thực để quyết định phân quyền.

### 6.2. Impersonation (thực hiện như chủ thể)

Trong **impersonation**, token mới có thể chỉ thể hiện chủ thể mục tiêu, khiến resource server không quan sát trực tiếp actor ở claims theo profile đã định. Vì tác động audit lớn, STS phải có policy chặt chẽ đối với bên được phép impersonate. **Token exchange không đồng nghĩa với impersonation**; RFC 8693 hỗ trợ nhiều ngữ cảnh, và semantics phải được xác định ở cấu hình thực tế.

| Thuộc tính | Delegation | Impersonation |
| --- | --- | --- |
| Quan hệ hành động | B thực hiện *thay* người dùng A | B thực hiện thao tác được xem như A theo chính sách. |
| Thông tin để audit | Có thể giữ cả subject và actor theo profile | Actor có thể không xuất hiện trực tiếp trong token đích; cần audit STS đầy đủ. |
| Quyết định authorization | C có thể ràng buộc cả user và actor | C đánh giá theo danh tính/properties được token mới trình bày. |
| Rủi ro điển hình | Actor chain không được kiểm soát hoặc mở rộng quá mức | Mất khả năng phân biệt ai thực sự đã khởi tạo lời gọi. |

Trong chuỗi nhiều service, một STS có thể phát hành actor chain theo quy ước riêng; `act` lồng nhau theo RFC 8693 cần được tiêu thụ đúng profile. Tránh tự sao chép/cộng dồn claims actor của token cũ vào token mới. Mỗi hop phải được STS hoặc một cơ chế ủy quyền được tin cậy kiểm tra.

## 7. Những kiểm tra bắt buộc ở từng bước

### 7.1. Tại Orders Service: kiểm tra token đầu vào

Trước khi exchange, Orders Service đóng vai **OAuth 2.0 resource server**. Nó cần:

1. Đọc access token từ cơ chế được hỗ trợ (thường `Authorization: Bearer ...`), từ chối credential sai cú pháp hoặc mơ hồ.
2. Nếu token là **JWT**, xác minh chữ ký, thuật toán và key từ issuer tin cậy; kiểm `iss`, `exp`, `nbf`, `aud=orders-api` và loại token/profile khi áp dụng. Nếu token là **opaque**, dùng introspection có xác thực phù hợp và kiểm tra `active` cùng claims theo profile.
3. Kiểm tra scope/quyền cho yêu cầu ban đầu (`orders:read`) và quyền trên đơn hàng thật (tenant, ownership, trạng thái nghiệp vụ).
4. Chỉ dùng **principal/claims đã xác minh** để tạo ngữ cảnh exchange; không chấp nhận `sub`, `tenant` hoặc `scope` do client tự gửi qua header.
5. Xác định C có thật sự cần ngữ cảnh người dùng không; nếu không, cân nhắc service token theo client credentials.

Access token dành cho Orders Service không trở nên phù hợp với Inventory chỉ vì cùng issuer hoặc được nhận qua mạng nội bộ. Nếu token_B không hợp lệ cho B, **không gửi nó tới STS với hy vọng STS sẽ hợp thức hóa yêu cầu không đáng tin**.

### 7.2. Tại STS: kiểm tra quyền exchange

STS quyết định có phát hành token_C hay không dựa trên nhiều điều kiện:

- Token đầu vào còn hiệu lực, phát hành bởi issuer tin cậy, đúng kiểu và nằm trong chính sách được phép trao đổi.
- Client gọi exchange là **Orders Service được xác thực**, được cấp quyền sử dụng grant type và tài nguyên đích đã yêu cầu.
- Quan hệ giữa subject, client/actor, tenant và `inventory-api` cho phép thực hiện delegated access; nếu STS hỗ trợ `may_act` hoặc actor policy thì phải đánh giá đúng.
- `audience`/`resource` và `scope` được yêu cầu nằm trong giới hạn policy cho subject và actor. Việc request scope `inventory:admin` không làm tăng quyền chỉ vì B đã xác thực với STS.
- Token mới có thời hạn thích hợp, audience đủ hẹp, quyền tối thiểu và binding phù hợp nếu dùng sender-constrained token.

STS không nên mặc nhiên copy mọi scope, audience hoặc role của token cũ sang token mới. Quyền trong token_C có thể **khác tên** quyền của token_B vì nó áp dụng cho tài nguyên khác, nhưng quyền này phải được ánh xạ/cho phép theo chính sách đã thiết lập; không được là đường tắt leo thang đặc quyền.

### 7.3. Tại Inventory Service: xác minh token mới

Inventory phải độc lập xác minh JWT hoặc introspect opaque token_C, kiểm tra `iss`, `aud=inventory-api`, thời hạn, token type, scope `inventory:read` và quyền trên dữ liệu hiện tại. Nếu hệ thống dùng delegation/actor claim, C phải áp dụng policy tương ứng. Trường hợp Orders Service gửi nhầm token_B thì Inventory **từ chối**.

Không cho C tin chỉ vì request đến từ IP nội bộ hay vì đã có API Gateway. mTLS giữa workloads giúp xác thực đầu kết nối, nhưng không tự cung cấp ngữ cảnh người dùng, scope hoặc quyền trên dữ liệu.

## 8. Thiết kế token theo ranh giới tài nguyên

### 8.1. `audience` gắn với một resource server

Ví dụ cấu hình kỳ vọng:

| Chặng | Token | Audience được C/B chấp nhận | Quyền điển hình |
| --- | --- | --- | --- |
| Client → Orders | `token_B` | `orders-api` | `orders:read` |
| Orders → STS | `subject_token=token_B` + client authentication của Orders | STS xác minh B, token_B và yêu cầu exchange | Yêu cầu `inventory:read`; chưa được chấp thuận trước khi STS kiểm. |
| Orders → Inventory | `token_C` | `inventory-api` | `inventory:read` |

Một token với nhiều audience làm tăng số resource server có thể chấp nhận nếu bị lộ. Ưu tiên **audience riêng cho từng dịch vụ hoặc nhóm tài nguyên được thiết kế rõ**; không tạo token `aud=*` hay scope chung `full_access` chỉ để tránh exchange.

### 8.2. `scope` và quyền trên tài nguyên cụ thể

`inventory:read` có thể cho phép gọi endpoint đọc, nhưng không tự xác định user được phép xem kho ở tenant nào. Inventory phải kiểm tenant, ownership và ràng buộc dữ liệu từ nguồn đáng tin. Quyền truy cập thực tế là giao của: **quyền chủ thể**, **quyền actor/service**, **phạm vi token** và **policy resource server** theo mô hình đã thiết kế; không phải chỉ một chuỗi scope.

### 8.3. `resource` và `audience` không hoán đổi tùy tiện

RFC 8693 cho phép tham số `audience` (tên logic) và `resource` (URI của đích), nhưng STS có thể quy định một trong hai hoặc policy riêng khi gửi cả hai. OAuth 2.0 Resource Indicators (RFC 8707) cũng dùng `resource` ở ngữ cảnh xin token. Hãy sử dụng đúng quy ước của issuer, kiểm thử token_C thực sự có audience C chấp nhận, thay vì giả định chỉ gửi tham số là thành công.

## 9. Ví dụ triển khai Java/Spring

Giả sử Orders Service sử dụng Spring Security OAuth 2.0 Resource Server để xác thực JWT đầu vào. Ở tầng application, service chỉ gọi token exchange **sau khi** đã có `JwtAuthenticationToken` được Spring xác thực. Mã dưới đây minh họa một client trao đổi token với STS qua `WebClient`; các imports, cấu hình dependency và quản lý secret được lược bỏ để tập trung vào luồng.

```java
public record ExchangeResponse(
    @JsonProperty("access_token") String accessToken,
    @JsonProperty("issued_token_type") String issuedTokenType,
    @JsonProperty("token_type") String tokenType,
    @JsonProperty("expires_in") Long expiresIn,
    @JsonProperty("scope") String scope
) {}

@Service
public class TokenExchangeClient {
    private static final String GRANT =
        "urn:ietf:params:oauth:grant-type:token-exchange";
    private static final String ACCESS_TOKEN_TYPE =
        "urn:ietf:params:oauth:token-type:access_token";

    private final WebClient webClient;

    public TokenExchangeClient(WebClient.Builder builder,
                               @Value("${security.sts.token-endpoint}") String tokenEndpoint,
                               @Value("${security.sts.client-id}") String clientId,
                               @Value("${security.sts.client-secret}") String clientSecret) {
        // Demo dùng Basic client authentication. Ở production có thể dùng
        // mTLS/private_key_jwt và secret manager theo yêu cầu của STS.
        this.webClient = builder.baseUrl(tokenEndpoint)
            .defaultHeaders(h -> h.setBasicAuth(clientId, clientSecret))
            .build();
    }

    public Mono<String> forInventory(String validatedIncomingAccessToken) {
        MultiValueMap<String, String> data = new LinkedMultiValueMap<>();
        data.add("grant_type", GRANT);
        data.add("subject_token", validatedIncomingAccessToken);
        data.add("subject_token_type", ACCESS_TOKEN_TYPE);
        data.add("requested_token_type", ACCESS_TOKEN_TYPE);
        data.add("audience", "inventory-api");
        data.add("scope", "inventory:read");

        return webClient.post()
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(data))
            .retrieve()
            .bodyToMono(ExchangeResponse.class)
            .map(response -> {
                if (response.accessToken() == null
                    || response.accessToken().isBlank()
                    || !ACCESS_TOKEN_TYPE.equals(response.issuedTokenType())
                    || !"Bearer".equalsIgnoreCase(response.tokenType())) {
                    throw new IllegalStateException("Invalid STS token response");
                }
                return response.accessToken();
            });
    }
}
```

Khi sử dụng client:

```java
// Tại controller/service đã qua Spring Security Resource Server.
// jwt phải là Jwt đã được decoder xác minh issuer, chữ ký, hạn dùng
// VÀ đã được validator/policy kiểm aud=orders-api, scope=orders:read.
public Mono<InventoryDto> loadInventory(Jwt jwt, String sku) {
    return exchangeClient.forInventory(jwt.getTokenValue())
        .flatMap(inventoryToken -> inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .headers(h -> h.setBearerAuth(inventoryToken))
            .retrieve()
            .bodyToMono(InventoryDto.class));
}
```

**Giới hạn có chủ đích của ví dụ:** đây là mã minh họa, chưa phải cấu hình production hoàn chỉnh. Đường dẫn STS phải là HTTPS được cấu hình sẵn, kết nối bảo mật phải xác minh chứng chỉ, và Orders cần validate audience/scope cho token đầu vào vì `issuer-uri` **không tự động kiểm đúng audience của mọi route**. Sử dụng secret manager, timeout, giới hạn kích thước phản hồi, error mapping, retry an toàn, circuit breaker và kiểm tra policy của token_C theo hợp đồng STS. `WebClient` logger/filter, APM/tracing, reverse proxy và công cụ debug phải **không ghi** form body chứa `subject_token`, header Basic hay access token trả về.

Để giảm phụ thuộc vào một STS cụ thể, có thể bọc logic thành giao diện `TokenExchangeService` rồi cấu hình client theo profile thật của nhà cung cấp; không được mặc định tất cả server OAuth 2.0 hỗ trợ grant `token-exchange` hoặc trả về cùng claims.

## 10. Vòng đời token và cache khi trao đổi

### 10.1. Hạn dùng của token mới

STS thường cấp token_C có thời gian sống ngắn và phạm vi hẹp. Có thể chọn chính sách token_C chỉ dùng trong một request hoặc trong khoảng thời gian nhỏ đủ cho nhiều lời gọi tương đương. **RFC 8693 không bảo đảm** token_C sẽ hết hạn cùng lúc với token_B; vì vậy hệ thống phải thiết kế rõ TTL, quy tắc tái sử dụng, giới hạn phiên và chính sách thu hồi theo nhu cầu bảo mật.

### 10.2. Khi nào có thể cache?

Đổi token cho **mỗi lời gọi** có thể gây tăng độ trễ, tải STS và tạo điểm nghẽn. Cache token_C có thể hữu ích, nhưng khóa cache phải phân biệt tối thiểu các ngữ cảnh thực sự ảnh hưởng tới authorization:

```text
issuer + subject/subject-session + authenticated-actor/client
+ target audience/resource + granted scope + tenant/context
+ token binding / policy version (nếu có ảnh hưởng)
```

Đây là danh sách **khái niệm**, không có nghĩa nên đưa raw `subject_token` vào cache key hoặc log. Cache key cần được thiết kế tránh lộ danh tính/credential, ví dụ dùng tham chiếu an toàn và phân vùng dữ liệu. Không cache token_C chỉ theo `sub=user-42`: cùng người dùng có thể có nhiều phiên, client, tenant, audience, scope hoặc quyền khác nhau. Không tái sử dụng token_C giữa hai actor hoặc hai ngữ cảnh ủy quyền nếu STS không xác nhận chúng tương đương.

TTL cache phải nhỏ hơn hoặc bằng thời gian token_C còn hiệu lực **trừ thời gian dự phòng**, đồng thời xét chính sách revocation và sự thay đổi quyền. Khi token_C hết hạn thì phải exchange lại theo policy; không gửi token hết hạn cho C rồi dựa vào C để xử lý. Chỉ lưu token trong bộ nhớ được bảo vệ/secret store cần thiết; không ghi token vào distributed cache không có kiểm soát mã hóa và quyền truy cập.

### 10.3. Thu hồi và thay đổi quyền

Việc refresh, revoke hay logout token_B **không mặc nhiên** làm token_C đã phát hành mất hiệu lực tức thì ở mọi STS. JWT tự xác minh có thể tiếp tục được chấp nhận tới `exp` nếu C không có cơ chế phát hiện thu hồi; opaque token dùng introspection có thể kiểm tra `active` nhưng cache introspection tạo độ trễ. Hãy định nghĩa chính sách propagation/invalidating của STS và resource server, giới hạn TTL cho token_C, và cân nhắc revocation event/denylist cho tác vụ rủi ro cao.

Không chuyển **refresh token** của người dùng cho Inventory Service để tự gia hạn. Refresh token chỉ dành cho những OAuth client và luồng đã được cấp phép lưu giữ/đổi nó; trong service-to-service token exchange thường chỉ cần access token ngắn hạn cho C.

## 11. Các nguy cơ bảo mật và biện pháp

| Nguy cơ | Tình huống | Biện pháp |
| --- | --- | --- |
| **Confused deputy** | B nhận token dành cho B rồi dùng để xin token quyền cao ở C | STS kiểm cả subject, client/actor, audience và scope; không cho tự nâng quyền. |
| **Lạm dụng exchange grant** | Một client bất kỳ có được token bị lộ và xin token cho C | Xác thực client B và allowlist quyền exchange/target cụ thể. |
| **Sai audience** | Relay `token_B` (`aud=orders-api`) thẳng tới `inventory-api` | Exchange để lấy token_C đúng audience; C luôn kiểm audience. |
| **Scope escalation** | B yêu cầu `inventory:admin` từ token chỉ có quyền đọc đơn hàng | STS kiểm policy mapping và least privilege, từ chối quyền không được phép. |
| **Actor spoofing** | B tự ghi `act`/`sub` hoặc header `X-User-Id` giả vào lời gọi | Chỉ tin claims do STS xác thực/ký và định danh workload được kiểm chứng. |
| **Token theft** | Raw `subject_token`/`access_token` xuất hiện trong request log STS hoặc APM | Không log body token exchange, Authorization hoặc response token; bảo vệ TLS, tracing, storage. |
| **Token replay** | Kẻ tấn công sao chép bearer token_C và gọi Inventory | Token ngắn hạn, audience hẹp; cân nhắc sender-constrained token và replay controls. |
| **Cross-tenant leakage** | Cache token_C theo user mà bỏ qua tenant hoặc actor | Cache key/policy theo ngữ cảnh đầy đủ và kiểm tenant ở C. |
| **STS downtime** | B bỏ qua exchange, gửi token_B cho C để “chữa cháy” | Fail closed; timeout/circuit breaker; không chuyển credential sai đối tượng. |
| **Nhiều hop không kiểm soát** | B exchange sang C, C tiếp tục exchange sang D với scope rộng | Mỗi hop cần policy, audience/scope cụ thể, hạn mức chuỗi delegation và audit. |
| **Sai token type** | B đưa ID token hoặc refresh token làm access token gọi C | Kiểm loại token/profile; dùng đúng token được STS cho phép exchange. |
| **Mất ngữ cảnh người dùng** | Dùng client credentials của B cho request cần quyền user | Thiết kế delegation theo STS; phân biệt service identity với end-user identity. |

### 11.1. DPoP và mTLS sender-constrained token

Với **bearer access token**, kẻ có bản sao token có thể thử dùng nó đến hết hạn. **DPoP** (RFC 9449) và **mTLS-bound access token** (RFC 8705) có thể ràng buộc token với khóa/chứng chỉ của bên được phép sử dụng, giảm nguy cơ token bị phát lại chỉ từ bản sao chuỗi token.

Nếu token_B ràng buộc với khóa của client, Orders Service không thể mặc nhiên sao chép token_B và DPoP proof/chứng chỉ của client để gọi C. Tại bước exchange, STS và Orders phải thiết kế cơ chế hợp lệ cho việc chấp nhận subject token ràng buộc bên gửi và phát hành token_C **ràng buộc với workload B** khi cần. DPoP proof gắn với HTTP method và URI đích; không sử dụng lại proof của chặng trước cho một endpoint khác. Không âm thầm hạ cấp sender-constrained token thành bearer khi chuyển ranh giới tin cậy.

### 11.2. Mạng riêng và TLS chưa đủ để phân quyền

Kênh HTTPS/mTLS bảo vệ tính bí mật/xác thực đầu kết nối. Nó không thay thế access token `aud=inventory-api`, quyền `inventory:read`, chủ thể được phép và kiểm tra dữ liệu nghiệp vụ tại C. Ngược lại, một JWT ký hợp lệ không tự bảo vệ khỏi token bị lộ trên mạng plaintext hoặc trong log. Service-to-service an toàn cần **cả** xác thực workload/kết nối **và** kiểm soát quyền theo tài nguyên.

## 12. Xử lý lỗi, retry và quan sát hệ thống

| Lỗi / HTTP điển hình | Nguồn | Hành vi an toàn |
| --- | --- | --- |
| `400 invalid_request` | Token endpoint nhận thiếu/sai tham số | Sửa request/config; không retry vô hạn. |
| `400 invalid_grant` hoặc lỗi token theo nhà cung cấp | Subject token không hợp lệ hoặc không thể dùng để exchange | Không cho phép tiếp tục bằng token không phù hợp. |
| `400 invalid_target` (RFC 8693) | Audience/resource yêu cầu không được cho phép | Không đổi sang audience tùy ý hoặc mở rộng quyền để thử lại. |
| `401 invalid_client` | Xác thực OAuth client của B thất bại | Kiểm credential/certificate/registration; không dùng fallback không xác thực. |
| Timeout hoặc `5xx` từ STS | Hạ tầng cấp token không sẵn sàng | Fail closed; retry có giới hạn/backoff nếu an toàn; báo lỗi dịch vụ phù hợp. |
| `401` từ Inventory | Token_C hết hạn, sai issuer/audience hoặc không hợp lệ | Không gửi token_B; rà soát STS/validator, có thể lấy token_C mới nếu lý do cho phép. |
| `403` từ Inventory | Token_C hợp lệ nhưng thiếu scope/quyền nghiệp vụ | Không tự xin scope cao hơn; kiểm chính sách cấp quyền. |

Mã lỗi cụ thể phụ thuộc STS và framework. Tại API gọi từ client, nên phân biệt lỗi token của **client → Orders** (`401/403` theo RFC 6750) với lỗi hệ thống **Orders → STS** (có thể là `502/503` hoặc lỗi hạ tầng được chuẩn hóa). Không trả raw thông tin STS, giá trị token hay credential trong body lỗi.

Đối với lời gọi nghiệp vụ không idempotent, **không tự động retry** sau timeout mà chưa xác định yêu cầu đã được xử lý hay chưa. Token exchange tại STS có thể retry theo chính sách nhà cung cấp, nhưng lời gọi xuống Inventory/Payments cần chiến lược riêng, ví dụ idempotency key khi thích hợp.

Các dữ liệu quan sát nên gồm `request_id`, `trace_id` đáng tin, source service, target service, loại kết quả exchange, thời gian xử lý, nhóm lỗi và mã policy/decision nếu được cung cấp. **Không log** `subject_token`, `actor_token`, token_C, client secret, Authorization header, refresh token hoặc toàn bộ JWT claims. Audit quan hệ actor/delegation theo metadata đã xác thực và chính sách bảo vệ dữ liệu; không tự tin claims giải mã chưa xác minh.

## 13. Kiểm thử tích hợp cần có

| Ca kiểm thử | Đầu vào / điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Exchange hợp lệ | User token_B hợp lệ, B được STS cho phép exchange sang `inventory-api` | STS cấp token_C `aud=inventory-api`, scope hẹp; C nhận và kiểm độc lập. |
| Sai audience đầu vào | Token_B dành cho `payments-api`, gọi Orders | Orders từ chối trước exchange, không gọi C. |
| Token_B hết hạn | `exp` đã qua hoặc introspection inactive | Orders từ chối; không gửi token đến STS cho xử lý trái policy. |
| B chưa được đăng ký | Client B không được cấp grant token exchange | STS từ chối; Orders fail closed. |
| Client authentication thất bại | Sai secret/chứng chỉ/private_key_jwt | STS không cấp token; không có token_C. |
| Scope escalation | B xin `inventory:admin` ngoài quyền cho phép | STS từ chối hoặc cấp quyền bị thu hẹp theo policy; C không chấp nhận quyền vượt quá token. |
| Target không được phép | B yêu cầu `audience=payments-api` khi chỉ được Inventory | STS từ chối (`invalid_target` nếu phù hợp). |
| Dùng nhầm ID token | `subject_token_type` là access token nhưng payload là ID token | STS từ chối theo quy tắc token type/profile. |
| C nhận nhầm token_B | Orders bỏ qua exchange và relay token_B | C từ chối do sai audience. |
| Token_C không đủ quyền bản ghi | `inventory:read` hợp lệ nhưng khác tenant | C trả 403/che giấu dữ liệu theo policy; audit ở C. |
| Exchange thành công, C lỗi mạng | STS cấp token_C nhưng C timeout | Không ghi đây là lỗi xác thực user; phân biệt lỗi downstream và retry có kiểm soát. |
| STS không sẵn sàng | Token endpoint timeout/5xx | Không fallback sang token_B hoặc tự cấp token. |
| Cross-tenant cache | Cùng user nhưng đổi tenant/session | Không dùng token_C của tenant/session trước. |
| Token_C đã hết hạn | Cache còn token_C quá TTL | Không gửi token hết hạn; exchange lại hoặc fail theo policy. |
| Revocation | Token_B/token_C bị thu hồi theo cơ chế STS | Chính sách hiệu lực/độ trễ thu hồi được tuân thủ; không tuyên bố thu hồi tức thì nếu chưa thiết kế. |
| DPoP/mTLS bound | Token của chặng trước gắn khóa/cert khác | Không dùng lại proof; exchange/ủy quyền theo binding thực tế. |
| Log leakage | Truy vết request exchange và lỗi STS | Không có raw credential trong access log, APM, trace hoặc lỗi trả về. |
| Chuỗi B → C → D | C cần gọi tiếp D bằng ngữ cảnh ủy quyền | Mỗi hop có token/policy target riêng; actor chain (nếu dùng) có nguồn đáng tin. |

Kiểm thử nên quan sát **HTTP request thực sự gửi ra**: token_B chỉ đến STS đúng điểm cho phép; Inventory chỉ nhận token_C; target URL cố định nằm trong allowlist; Authorization header có đúng credential; không rò token vào redirect hoặc log. Đồng thời xác minh việc STS từ chối không bị chuyển thành `ALLOW` ở ứng dụng.

## 14. Checklist triển khai

- [ ] Xác định B là resource server ở chặng nhận và OAuth client ở chặng exchange.
- [ ] Kiểm token_B theo issuer, chữ ký/introspection, token type, `aud=orders-api`, thời hạn, scope và quyền nghiệp vụ trước exchange.
- [ ] Xác thực B với STS bằng cơ chế phù hợp; grant, subject và target nằm trong policy cho phép.
- [ ] Dùng `subject_token_type`, `audience`/`resource`, `requested_token_type`, `scope` theo profile STS thực tế.
- [ ] Phân biệt delegation với impersonation; quy tắc `actor_token`, `act`, `sub` được định nghĩa rõ nếu sử dụng.
- [ ] Chỉ dùng token_C do STS phát hành để gọi C; C tự kiểm `iss`, `aud`, expiry, scope, binding và quyền trên dữ liệu.
- [ ] Duy trì nguyên tắc quyền tối thiểu, audience hẹp, TTL hợp lý; không tự ý tăng quyền ở nhiều hop.
- [ ] Bảo vệ token_B, token_C, secret và proof khỏi log, URL, trace, cache không kiểm soát.
- [ ] Định nghĩa TTL/cache key theo actor, chủ thể, tenant, audience, scope, session và binding nếu cần.
- [ ] Có chiến lược thu hồi/đổi token, STS timeout, retry, circuit breaker và fail closed.
- [ ] Kiểm thử cả thành công, thất bại, lỗi audience/scope, cross-tenant, replay, STS downtime và credential leak.

## 15. Tổng kết và tài liệu tham khảo

**Token exchange giữa service** giải quyết bài toán đưa ngữ cảnh ủy quyền qua nhiều resource server mà không bắt từng dịch vụ chấp nhận token dành cho dịch vụ khác. Token_B được phát hành cho Orders Service; STS, sau khi xác thực Orders và đánh giá quyền của subject/actor, có thể phát hành token_C phù hợp với Inventory Service. Sự tách biệt này giúp giới hạn audience, quyền, thời gian sống và khả năng audit ở từng ranh giới. Token exchange chỉ an toàn khi mỗi thành phần **kiểm tra đúng token và thực thi đúng policy**, kể cả khi hệ thống chạy hoàn toàn trong mạng nội bộ.

Tài liệu tiêu chuẩn liên quan:

- **RFC 8693 — OAuth 2.0 Token Exchange:** grant type, `subject_token`, `actor_token`, audience/resource, `act` và phản hồi token.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** vai trò client, authorization server, access token và cấp quyền.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bảo vệ bearer token trên HTTP và xử lý lỗi tài nguyên.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra opaque access token và trạng thái `active`.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token và trách nhiệm của các thành phần liên quan.
- **RFC 7519 / RFC 9068:** JWT và JWT Profile for OAuth 2.0 Access Tokens; claims như `iss`, `sub`, `aud`, `exp`.
- **RFC 8707 — Resource Indicators:** chỉ rõ tài nguyên mục tiêu khi xin token.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client và ràng buộc token bằng chứng chỉ.
- **RFC 9449 — OAuth 2.0 DPoP:** sender-constrained access token bằng bằng chứng sở hữu khóa.
