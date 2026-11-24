# Delegation token: ủy quyền service hành động thay người dùng

## 1. Bối cảnh và mục tiêu

Trong hệ thống nhiều service, một request thường bắt đầu từ người dùng rồi đi qua một hoặc nhiều service để hoàn thành nghiệp vụ. Ví dụ người dùng yêu cầu Orders Service đọc đơn hàng; Orders Service cần gọi Inventory Service để lấy tồn kho. Inventory cần biết **người dùng nào là chủ thể của quyền truy cập**, đồng thời phải biết **service nào đang thực hiện lời gọi thay người dùng đó**. Nếu chỉ dùng một service token, Inventory có thể biết Orders đang gọi nhưng mất ngữ cảnh ủy quyền của người dùng. Nếu chuyển tiếp user access token nguyên vẹn, token có thể sai audience hoặc không thể hiện actor.

**Delegation token** là cách gọi thường dùng cho access token thể hiện việc một actor được phép hành động thay một subject trong phạm vi xác định. Trong OAuth 2.0, một cách triển khai phổ biến là **Token Exchange theo RFC 8693**: service được xác thực với authorization server/security token service (STS), đưa token của subject vào phép trao đổi và nhận token mới dành cho resource server đích. Token mới có thể biểu diễn subject và actor theo profile mà STS cùng resource server đã thống nhất.

Lưu ý: “delegation token” không phải một token type độc lập bắt buộc có định dạng chung trong OAuth. Đây là **ngữ nghĩa ủy quyền**; token có thể là JWT hoặc opaque access token. RFC 8693 định nghĩa cơ chế trao đổi token và các khái niệm như `subject_token`, `actor_token`, claim `act` và `may_act`, còn cách cấp quyền và kiểm tra cụ thể phụ thuộc policy của authorization server và resource server.

Bài học thuộc chương **Token exchange** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, gắn với mô hình tin cậy và vòng đời token bảo mật, phân biệt JWT/opaque token, access/refresh token, xác thực, phân quyền OAuth 2.0/OIDC, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài này, người học có thể:

1. Phân biệt **subject**, **actor**, OAuth client và resource server trong một luồng delegation.
2. Giải thích sự khác nhau giữa **delegation** và **impersonation**.
3. Hiểu vai trò của `subject_token`, `actor_token`, `act`, `may_act`, `audience`, `resource` và `scope` trong token exchange.
4. Thiết kế token mới có audience hẹp, quyền tối thiểu và thời hạn phù hợp.
5. Xác minh delegation token tại downstream, quản lý chuỗi actor, cache, thu hồi, audit và kiểm thử an toàn.

## 2. Subject và actor: hai danh tính trong một hành động

Để hiểu delegation, cần tách hai câu hỏi:

- **Subject — ai là người mà quyền đang được đại diện?** Ví dụ người dùng `user-42` có quyền xem một đơn hàng.
- **Actor — thành phần nào đang thực hiện hành động?** Ví dụ `orders-service` gọi Inventory API trong quá trình xử lý request của `user-42`.

Một delegation token có thể thể hiện cả hai danh tính. Subject giữ ngữ cảnh ủy quyền gốc; actor cho biết service nào đang hành động thay subject. Resource server có thể dùng cả hai để quyết định: người dùng có quyền xem dữ liệu này không, và service gọi thay người dùng có được phép thực hiện loại hành động này không.

| Khái niệm | Ví dụ | Vai trò trong authorization |
| --- | --- | --- |
| Subject | `user-42` | Người dùng/chủ thể mà quyền truy cập đang được đại diện. |
| Actor | `orders-service` | Workload được phép thực hiện lời gọi thay subject. |
| OAuth client | `orders-service-client` | Client đã xác thực với STS để xin token. |
| Resource server | `inventory-api` | API nhận token và quyết định có cho phép thao tác hay không. |
| Audience | `inventory-api` | Định danh tài nguyên mà token mới được phát hành cho. |
| Scope | `inventory:read` | Quyền API được cấp cho token. |

Một service có thể đồng thời là resource server ở chặng trước và OAuth client ở chặng sau. Ví dụ Orders nhận user token như resource server, xác minh quyền xem order, rồi xác thực chính nó với STS để xin delegation token cho Inventory. Không được kết luận actor chỉ từ địa chỉ IP, header `X-Service-Name` do caller gửi hoặc tên pod trong request chưa được xác thực.

### 2.1. Ví dụ claims minh họa

Một JWT access token được STS phát hành cho Inventory có thể chứa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "act": {
    "sub": "orders-service"
  },
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

Đây là payload giả định để minh họa, không phải token sử dụng được. Chỉ khi chữ ký và các điều kiện token được xác minh, Inventory mới có thể tin `iss`, `sub`, `aud`, `scope` và `act`. Claim `act` theo RFC 8693 biểu diễn actor; trong ví dụ, `sub` vẫn là user, còn actor là Orders Service. STS quyết định có phát hành cấu trúc này hay không và resource server phải được cấu hình hiểu đúng ý nghĩa của nó.

`sub` không nhất thiết luôn là người dùng cuối: subject có thể là một workload hoặc thực thể khác tùy hệ thống. Hãy dựa vào profile token và hợp đồng giữa issuer/resource server, không suy luận từ tên claim.

## 3. Delegation khác impersonation như thế nào?

Hai mô hình có thể tạo ra token cho phép service thực hiện hành động liên quan đến một người dùng, nhưng ngữ nghĩa audit và authorization khác nhau.

### 3.1. Delegation — actor được phép hành động thay subject

Trong delegation, hệ thống giữ được sự phân biệt giữa **chủ thể được đại diện** và **actor thực hiện hành động**. Ví dụ `user-42` yêu cầu xem đơn hàng; Orders Service gọi Inventory thay user. Inventory có thể kiểm tra:

- Subject `user-42` có quyền đọc tồn kho liên quan tới đơn hàng hay không.
- Actor `orders-service` có được phép gọi Inventory theo quan hệ delegation đã được STS cấp hay không.
- Scope `inventory:read`, audience và tenant có phù hợp với request không.

Delegation không làm Orders trở thành user. Nó tạo một ngữ cảnh ủy quyền có giới hạn để Orders hành động thay subject.

### 3.2. Impersonation — hành động dưới danh nghĩa subject

Trong impersonation, service được phép hành động như thể nó là subject mục tiêu. Token đích có thể chỉ thể hiện danh tính của subject, tùy thiết kế; actor có thể không được thể hiện rõ trong claims mà downstream nhận. Vì vậy audit bên STS và hệ thống gọi trở nên đặc biệt quan trọng: phải biết **service nào đã yêu cầu impersonation, ai phê duyệt và phạm vi nào được cấp**.

Impersonation có rủi ro cao vì resource server có thể nhìn thấy user mà không phân biệt người dùng thật với service đang thay mặt họ. Chỉ cho phép khi có nhu cầu rõ ràng, policy giới hạn chặt chẽ, kiểm soát cấp quyền, audit đầy đủ và thời hạn ngắn.

| Tiêu chí | Delegation | Impersonation |
| --- | --- | --- |
| Subject | Chủ thể gốc được giữ trong ngữ cảnh token | Có thể là danh tính mà actor đang giả lập theo policy |
| Actor | Có thể được thể hiện rõ qua `act` | Có thể không được thể hiện ở token đích; cần audit ngoài token |
| Ý nghĩa | “Actor A hành động thay subject S” | “Actor A được phép hành động như S” |
| Kiểm tra ở downstream | Có thể xét cả subject và actor | Thường xét danh tính hiệu lực; phải có cách truy vết actor |
| Rủi ro chính | Actor chain hoặc scope bị mở rộng | Mất dấu actor thực tế, khó quy trách nhiệm |

RFC 8693 hỗ trợ mô tả actor trong token exchange, nhưng không tự quyết định hệ thống của bạn phải chọn delegation hay impersonation. Semantics phải được STS, client và resource server thống nhất.

## 4. OAuth 2.0 Token Exchange và các trường liên quan

RFC 8693 định nghĩa token endpoint grant type:

`urn:ietf:params:oauth:grant-type:token-exchange`

Các tham số chính:

| Tham số | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `grant_type` | Chỉ ra yêu cầu đang dùng token exchange | Bắt buộc, dùng URI grant type được định nghĩa. |
| `subject_token` | Token của subject được đưa vào phép trao đổi | Bắt buộc; loại token phải được mô tả bởi `subject_token_type`. |
| `subject_token_type` | Loại của subject token | Bắt buộc; ví dụ access token. |
| `actor_token` | Token đại diện actor, nếu luồng cần cung cấp actor token riêng | Tùy chọn; không phải mọi delegation flow đều cần trường này. |
| `actor_token_type` | Loại của actor token | Bắt buộc nếu có `actor_token`. |
| `requested_token_type` | Loại token client mong muốn nhận | Tùy chọn; thường yêu cầu OAuth access token. |
| `audience` | Định danh logic của resource server đích | Có thể là `inventory-api`, theo quy ước STS. |
| `resource` | URI của resource đích | Theo RFC 8693/RFC 8707; STS quyết định hỗ trợ và cách kết hợp. |
| `scope` | Quyền mà client đề nghị cho token mới | STS chỉ cấp phần được policy cho phép. |

OAuth client gọi token endpoint cũng phải **xác thực chính nó**. Việc sở hữu `subject_token` không tự chứng minh service nào đang thực hiện exchange. STS có thể dùng client authentication bằng mTLS, `private_key_jwt`, client secret hoặc cơ chế khác theo cấu hình. Actor token (nếu có) và client authentication là hai dữ liệu khác nhau.

### 4.1. `subject_token` và `actor_token`

- `subject_token` đưa danh tính/ủy quyền của subject vào quá trình exchange.
- `actor_token` (nếu sử dụng) cung cấp token đại diện actor theo profile và policy mà STS hỗ trợ.
- Danh tính client được xác thực tại token endpoint cho biết **ứng dụng nào đang xin exchange**.

Không phải mọi triển khai cần `actor_token`. STS có thể xác định actor từ client authentication hoặc registration và phát hành `act` claim tương ứng theo policy. Ngược lại, nếu yêu cầu actor token, STS phải kiểm token đó, loại token, issuer và mối quan hệ giữa actor với subject.

### 4.2. Claim `act` và `may_act`

RFC 8693 định nghĩa hai claim quan trọng:

- **`act`**: claim trong token được phát hành để biểu diễn actor. Ví dụ `act.sub=orders-service` cho biết Orders Service là actor trong ngữ cảnh token đó. Actor chain có thể được biểu diễn lồng nhau theo quy tắc của RFC.
- **`may_act`**: claim trong subject token có thể biểu diễn actor nào được phép hành động thay subject. STS có thể dùng thông tin này làm đầu vào policy; sự hiện diện của claim không buộc STS phải cấp token nếu các điều kiện khác không đạt.

Ví dụ một subject token giả định có thể có:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "may_act": {
    "sub": "orders-service"
  },
  "exp": 1893456000
}
~~~

Claim `may_act` ở đây là dữ liệu được issuer tin cậy đưa vào token, không phải header để Orders tự thêm. STS cần xác minh chữ ký/token, kiểm client đang gọi, đối chiếu actor với `may_act` và áp dụng policy bổ sung trước khi phát hành delegation token. Không được hiểu `may_act` là quyền vô hạn hoặc bỏ qua scope/audience của token đích.

## 5. Luồng delegation từ đầu đến cuối

Giả sử người dùng xem thông tin tồn kho liên quan đến đơn hàng:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Client
    participant O as Orders API
    participant S as STS / Authorization Server
    participant I as Inventory API

    U->>O: GET /orders/123 + user access token
    O->>O: Verify token_B, aud=orders-api, orders:read
    O->>O: Kiểm tra quyền user trên order 123
    O->>S: Token exchange + client authentication
    Note over O,S: subject_token=user token; audience=inventory-api; scope=inventory:read
    S->>S: Validate subject, client/actor, may_act và policy
    S-->>O: Delegation access token_C
    O->>I: GET /items/sku-1 + token_C
    I->>I: Verify issuer, signature/introspection, aud, scope, act
    I->>I: Kiểm tra tenant và quyền trên dữ liệu
    I-->>O: Inventory result
    O-->>U: Response
~~~

### 5.1. Chặng user → Orders

Orders là resource server. Nó xác minh access token đầu vào:

1. Token là loại được API chấp nhận, thường là access token.
2. Issuer `iss` nằm trong danh sách tin cậy; chữ ký JWT hợp lệ hoặc opaque token introspection trả `active=true`.
3. `exp`, `nbf` và các giới hạn thời gian hợp lệ.
4. Audience chứa định danh Orders API.
5. Scope đủ cho action; quyền truy cập order cụ thể và tenant được kiểm tra theo dữ liệu nghiệp vụ.

Chỉ sau khi xác minh, Orders mới dùng context đã tin cậy để quyết định có gọi Inventory thay user. Không dùng `sub` từ JWT chỉ được decode nhưng chưa kiểm chữ ký.

### 5.2. Chặng Orders → STS

Orders đóng vai OAuth client. Nó xác thực workload của mình, gửi subject token và yêu cầu token mới dành cho Inventory. STS kiểm:

- Subject token hợp lệ và có thể được dùng cho exchange.
- Client/actor được xác thực là Orders Service.
- Policy cho phép Orders đại diện subject đó.
- `audience`/`resource` đích được phép.
- Scope yêu cầu không vượt quyền được ủy quyền.
- Nếu có sender constraint hoặc actor token, binding và actor context phải hợp lệ.

STS có thể từ chối dù subject token còn hạn và chữ ký hợp lệ. Điều đó là bình thường: **xác thực subject không đồng nghĩa actor được phép hành động thay subject**.

### 5.3. Chặng Orders → Inventory

Inventory là resource server. Nó xác minh token mới như một access token dành cho chính Inventory. Nếu token là JWT, kiểm chữ ký, issuer, audience, hạn dùng và profile. Nếu opaque, introspect. Sau đó kiểm scope, actor/subject theo policy, tenant và quyền trên item. Không chấp nhận token chỉ vì request đến từ mạng nội bộ hoặc có header nói rằng Orders đã kiểm tra.

## 6. HTTP request/response minh họa

### 6.1. Request token exchange

Ví dụ dưới đây giả định STS hỗ trợ RFC 8693 và actor được xác định từ OAuth client đã xác thực. Cơ chế client authentication chỉ minh họa bằng placeholder:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <orders-client-authentication>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<user-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=inventory-api
&scope=inventory%3Aread
~~~

Đây là body URL-encoded được xuống dòng để dễ đọc; client HTTP phải mã hóa đúng. Nếu STS yêu cầu `actor_token`, `actor_token_type`, `resource` hoặc một profile riêng, phải tuân thủ hợp đồng của STS. Không tự thêm tham số actor để giả danh một service.

### 6.2. Response thành công

~~~json
{
  "access_token": "<new-delegation-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 180,
  "scope": "inventory:read"
}
~~~

`issued_token_type` cho biết loại token được phát hành; nó không nói token chắc chắn là JWT. `token_type=Bearer` mô tả cách client sử dụng token trong ví dụ. Token thực có thể là opaque và cần introspection. Không ghi access token trong response vào log, trace hoặc thông báo lỗi.

### 6.3. Response lỗi

| Lỗi | Nguyên nhân có thể | Hành vi |
| --- | --- | --- |
| `invalid_request` | Thiếu hoặc sai tham số exchange | Sửa cấu hình/request; không retry vô hạn. |
| `invalid_client` | Orders xác thực với STS thất bại | Kiểm client registration, secret/certificate/key; không bypass xác thực. |
| `invalid_grant` | Subject token không hợp lệ hoặc không được chấp nhận | Không gọi Inventory bằng token cũ. |
| `invalid_target` | Audience/resource yêu cầu không được phép | Giữ nguyên policy; không tự đổi target sang resource khác để thử. |
| `unauthorized_client` | Client không được phép dùng grant type hoặc exchange policy | Cần cấp quyền chính thức cho client nếu phù hợp. |
| Timeout/5xx | STS không sẵn sàng | Fail closed; retry giới hạn theo policy và trả lỗi hạ tầng đã chuẩn hóa. |

Mã lỗi cụ thể phụ thuộc STS và profile. Không trả chi tiết nội bộ, raw token hay client credential cho caller bên ngoài.

## 7. Quyền tối thiểu và audience của delegation token

Delegation token cần bị giới hạn ít nhất theo bốn chiều:

1. **Subject:** user hoặc chủ thể được đại diện.
2. **Actor:** service được phép thực hiện hành động.
3. **Audience/resource:** API cụ thể nhận token.
4. **Scope và context:** hành động được phép, tenant, dữ liệu và thời hạn.

Ví dụ:

| Chặng | Token | Audience | Scope |
| --- | --- | --- | --- |
| Client → Orders | User access token | `orders-api` | `orders:read` |
| Orders → STS | Subject token + Orders client authentication | Token endpoint của STS | Yêu cầu `inventory:read` cho target Inventory |
| Orders → Inventory | Delegation access token mới | `inventory-api` | `inventory:read` |

Không cấp token `aud=*`, scope `admin` hoặc thời hạn dài chỉ để tránh exchange thường xuyên. STS phải tính quyền token mới từ policy, không đơn thuần copy toàn bộ scope của subject token. Quyền đọc order không tự động ánh xạ thành quyền sửa tồn kho.

Scope thường là quyền API ở mức tổng quát. Inventory vẫn phải kiểm tra user có được xem item trong tenant hiện tại không. Một delegation token hợp lệ không đồng nghĩa subject có quyền trên mọi bản ghi.

## 8. JWT và opaque delegation token

### 8.1. JWT

JWT có thể chứa subject, actor, audience, scope, thời gian và các claims liên quan. Resource server xác minh chữ ký bằng khóa của issuer tin cậy; kiểm `iss`, `aud`, `exp`, `nbf`, token type/profile và các claim được yêu cầu. Khóa JWKS có thể được cache nhưng phải xử lý rotation, key ID không tìm thấy và issuer không khả dụng.

Không chấp nhận JWT chỉ vì parse được JSON hoặc thuật toán trong header tự khai báo. Không sửa payload để thay `sub`, `act`, `aud` hay scope; thay claim làm chữ ký không hợp lệ.

### 8.2. Opaque token

Opaque token không công khai claims cho resource server. Inventory có thể dùng endpoint introspection theo RFC 7662, xác thực chính nó với STS và kiểm `active`, audience, scope cùng metadata được trả về. Introspection timeout hoặc lỗi không được coi như `active=true`.

### 8.3. Cách chọn

| Tiêu chí | JWT | Opaque |
| --- | --- | --- |
| Xác minh | Kiểm chữ ký và claims tại resource server | Thường gọi introspection |
| Thu hồi | Offline validation có thể tiếp tục chấp nhận tới `exp` nếu không có cơ chế bổ sung | Có thể phản ánh trạng thái active qua introspection; cache vẫn tạo độ trễ |
| Claims actor | Có thể được biểu diễn trong JWT theo profile | Resource server đọc qua introspection nếu STS trả thông tin phù hợp |
| Vận hành | Quản lý JWKS, key rotation, clock skew | Quản lý endpoint, client auth, timeout, cache và availability |

Định dạng token không quyết định token có phải delegation hay không; ngữ nghĩa subject/actor do STS và resource server thống nhất.

## 9. Delegation qua nhiều service: actor chain

Một luồng có thể dài hơn hai chặng: User → API Gateway → Orders → Inventory → Warehouse. Khi mỗi service tiếp tục gọi service khác, hệ thống cần quyết định actor hiện tại và lịch sử delegation được thể hiện ra sao.

RFC 8693 cho phép claim `act` có cấu trúc lồng nhau để biểu diễn actor chain. Ví dụ minh họa:

~~~json
{
  "sub": "user-42",
  "aud": "warehouse-api",
  "scope": "warehouse:read",
  "act": {
    "sub": "inventory-service",
    "act": {
      "sub": "orders-service"
    }
  }
}
~~~

Đây chỉ là ví dụ hình thức; STS phải phát hành token theo quy tắc của RFC và profile hệ thống. Không tự nối claims actor vào JWT rồi ký bằng khóa ứng dụng. Resource server cần hiểu đúng actor hiện tại và actor trước đó theo policy. Actor chain dài có thể làm tăng độ phức tạp, vì vậy nên giới hạn số hop, target và loại actor được phép.

Mỗi chặng nên có:

- Token đúng audience của resource server tiếp theo.
- Scope tối thiểu cho hành động tại chặng đó.
- Actor được STS xác thực và cho phép.
- Thời hạn phù hợp với chuỗi xử lý.
- Audit event ghi subject/actor reference, target, policy và correlation ID.

Nếu service C nhận token của A nhưng lời gọi thực tế do D thực hiện, không được che giấu sự thay đổi actor. Cần exchange lại hoặc sử dụng cơ chế delegation được định nghĩa cho chặng mới.

## 10. Java/Spring: tổ chức luồng delegation

Ví dụ dưới đây là pseudocode theo kiểu Spring WebFlux. Nó tập trung vào thứ tự tin cậy: xác minh user token ở resource server, exchange với STS bằng danh tính workload, rồi dùng token mới gọi Inventory.

~~~java
public record ExchangeResponse(
    @JsonProperty("access_token") String accessToken,
    @JsonProperty("issued_token_type") String issuedTokenType,
    @JsonProperty("token_type") String tokenType,
    @JsonProperty("expires_in") Long expiresIn,
    @JsonProperty("scope") String scope
) {}

@Service
public class DelegationTokenClient {
    private static final String GRANT =
        "urn:ietf:params:oauth:grant-type:token-exchange";
    private static final String ACCESS_TOKEN =
        "urn:ietf:params:oauth:token-type:access_token";

    private final WebClient stsClient;

    public DelegationTokenClient(WebClient.Builder builder,
                                 String configuredTokenUri,
                                 OAuthClientAuthentication clientAuthentication) {
        // clientAuthentication dùng mTLS/private_key_jwt hoặc cơ chế STS yêu cầu.
        this.stsClient = clientAuthentication.configure(builder)
            .baseUrl(configuredTokenUri)
            .build();
    }

    public Mono<String> exchangeForInventory(String verifiedUserToken) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", GRANT);
        form.add("subject_token", verifiedUserToken);
        form.add("subject_token_type", ACCESS_TOKEN);
        form.add("requested_token_type", ACCESS_TOKEN);
        form.add("audience", "inventory-api");
        form.add("scope", "inventory:read");

        return stsClient.post()
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(form))
            .retrieve()
            .bodyToMono(ExchangeResponse.class)
            .map(response -> {
                if (response.accessToken() == null
                    || response.accessToken().isBlank()
                    || !ACCESS_TOKEN.equals(response.issuedTokenType())
                    || !"Bearer".equalsIgnoreCase(response.tokenType())) {
                    throw new IllegalStateException("Invalid STS response");
                }
                return response.accessToken();
            });
    }
}
~~~

Ở controller/service đã qua Spring Security Resource Server:

~~~java
public Mono<InventoryDto> getInventory(JwtAuthenticationToken authentication,
                                       String sku) {
    Jwt jwt = authentication.getToken(); // đã được decoder/validator xác minh

    // Validator phải kiểm aud=orders-api và scope orders:read theo policy.
    return delegationTokenClient.exchangeForInventory(jwt.getTokenValue())
        .flatMap(delegatedToken -> inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .headers(h -> h.setBearerAuth(delegatedToken))
            .retrieve()
            .bodyToMono(InventoryDto.class));
}
~~~

Đây là **ví dụ khung**, không phải cấu hình production hoàn chỉnh. Cần bổ sung validator audience/scope, kiểm tra quyền trên order, timeout, TLS và client authentication theo STS, giới hạn response, xử lý lỗi, observability đã scrub secret và quản lý token trong bộ nhớ. Cấu hình issuer của Spring Resource Server không mặc nhiên bảo đảm mọi audience được kiểm theo từng route. Nếu dùng opaque token, cấu hình introspection thay cho JWT decoder.

Không ghi `verifiedUserToken`, `delegatedToken`, form body, header Authorization hoặc thông tin xác thực client vào log. Không lưu token mới vào singleton field dùng chung cho mọi user. Nếu cache, key phải tách subject, actor, tenant, audience, scope và các yếu tố policy/binding liên quan.

## 11. Vòng đời, lưu trữ, cache và thu hồi

### 11.1. Thời hạn token

Delegation token thường nên có TTL ngắn, đủ cho request hoặc một nhóm tác vụ có cùng ngữ cảnh. Token không nên sống lâu hơn nhu cầu ủy quyền. STS có thể phát hành token có thời hạn độc lập với subject token; vì vậy việc user token hết hạn hoặc bị thu hồi không tự động chứng minh delegation token cũng lập tức mất hiệu lực.

Với tác vụ nhạy cảm, cân nhắc thời hạn ngắn, introspection, revocation event hoặc denylist theo `jti` nếu profile/hạ tầng hỗ trợ. Xác định rõ độ trễ chấp nhận được giữa thời điểm thu hồi và thời điểm resource server dừng chấp nhận token.

### 11.2. Cache an toàn

Cache token exchange có thể giảm độ trễ và tải STS nhưng dễ gây rò quyền nếu khóa cache quá đơn giản. Cache context cần xét:

~~~text
issuer + subject/session + actor/client
+ audience/resource + granted scope + tenant
+ token binding + policy version (nếu có ảnh hưởng)
~~~

Không dùng raw token làm cache key; không cache token delegation chỉ theo `sub`. TTL cache phải nhỏ hơn thời gian token còn hiệu lực, có khoảng dự phòng cho clock skew và có quy tắc invalidation khi quyền/tenant/session thay đổi. Không chia sẻ token giữa hai actor nếu STS không xác nhận hai ngữ cảnh tương đương.

### 11.3. Lưu trữ

Ưu tiên giữ token trong bộ nhớ ngắn hạn đúng phạm vi request. Nếu phải lưu để phục vụ job hoặc cache, dùng kho bí mật được kiểm soát, mã hóa, phân quyền theo workload và thời hạn rõ ràng. Tránh lưu raw token trong DB nghiệp vụ, queue, dead-letter queue, file cấu hình, crash dump, log hoặc trace.

Refresh token không nên được dùng để làm cho delegation token “sống mãi”. Chỉ OAuth client được cấp phép mới được giữ và dùng refresh token theo policy; resource server downstream không nên nhận refresh token của user.

## 12. Sender-constrained token và chống replay

Bearer token có thể bị replay nếu kẻ tấn công lấy được chuỗi token. **DPoP** (RFC 9449) và **mTLS-bound access token** (RFC 8705) có thể ràng buộc token với khóa/chứng chỉ của bên sở hữu.

Nếu user token được ràng buộc với khóa của client, service không thể mặc nhiên copy token và proof của client để gọi Inventory. STS cần hỗ trợ exchange phù hợp, xác minh binding của subject token và phát hành token mới ràng buộc với workload/actor đích khi cần. DPoP proof gắn với HTTP method và URI; không dùng lại proof của request client cho URL downstream.

mTLS giữa service giúp xác thực workload và bảo vệ kênh, nhưng không tự cấp quyền user. Token vẫn cần audience/scope hợp lệ và Inventory vẫn kiểm tra quyền dữ liệu. Không hạ cấp sender-constrained token thành bearer chỉ vì relay dễ triển khai hơn.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng token admin chung cho nhiều service | Quyền rộng, khó thu hồi và audit sai actor | Cấp workload identity riêng, scope tối thiểu. |
| Không xác minh subject token trước exchange | STS nhận credential không đáng tin hoặc sai audience | Resource server xác minh token và quyền trước; STS cũng xác minh subject token. |
| Chỉ xác thực Orders với STS, không kiểm subject | Orders có thể xin quyền cho user bất kỳ | STS kiểm cả subject, actor/client và policy. |
| Tin `act` do service tự thêm | Actor giả, giả mạo ủy quyền | Chỉ tin claim do issuer tin cậy phát hành và ký. |
| Dùng `may_act` như wildcard | Mọi service có thể hành động thay subject | Actor được giới hạn theo danh tính và policy cụ thể. |
| Token sai audience vẫn được relay | Downstream chấp nhận credential không dành cho nó nếu validator lỗi | Kiểm `aud` ở từng resource server; exchange khi cần. |
| Scope token mới lớn hơn quyền được ủy quyền | Privilege escalation | STS downscope theo policy; không copy toàn bộ role. |
| Coi delegation là impersonation | Mất actor attribution | Phân biệt `sub` và `act`; audit cả hai. |
| Cache token chỉ theo user ID | Lẫn actor, tenant, session và quyền | Cache key theo đầy đủ context hoặc không cache. |
| Log token exchange body | Lộ subject/actor/access token | Scrub body/header tại app, proxy, APM và trace. |
| STS lỗi thì bỏ qua exchange | Dùng token không phù hợp, bypass policy | Fail closed, retry có giới hạn và báo lỗi hạ tầng. |
| Dùng delegation token cho job vô thời hạn | Token hết hạn hoặc quyền user đã thay đổi | Thiết kế job authorization/workload identity riêng. |

## 14. Kiểm thử tích hợp

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Delegation hợp lệ | User token đúng issuer/audience/scope; actor được phép | STS cấp token mới đúng audience/scope, có actor context theo profile. |
| User token sai audience | Token dành cho Payments được đưa vào Orders | Orders từ chối trước exchange. |
| User token hết hạn | `exp` đã qua | Không exchange; trả lỗi xác thực phù hợp. |
| Chữ ký JWT sai | Sửa `sub`/`scope` mà không ký lại | Token bị từ chối; không dùng claims chưa xác minh. |
| Opaque token inactive | Introspection `active=false` | Không exchange và không forward. |
| Introspection timeout | STS không phản hồi | Fail closed; ghi lỗi hạ tầng, không mặc định token hợp lệ. |
| Actor không được phép | `orders-service` không nằm trong policy/`may_act` | STS từ chối exchange. |
| Actor token sai | `actor_token` sai type, issuer hoặc subject | STS từ chối. |
| Client authentication sai | Orders dùng sai credential | STS từ chối `invalid_client`; không có token mới. |
| Target không được phép | Xin `audience=payments-api` ngoài allowlist | STS từ chối `invalid_target` hoặc lỗi policy tương ứng. |
| Scope vượt quyền | Xin `inventory:admin` trong khi policy chỉ cho read | STS từ chối hoặc chỉ cấp scope được phép theo policy. |
| Token mới sai audience | STS trả token không có `aud=inventory-api` | Orders không gửi token tới Inventory; phát hiện lỗi cấu hình/issuer. |
| Downstream kiểm tra độc lập | Gửi token có chữ ký hợp lệ nhưng `aud` sai tới Inventory | Inventory từ chối. |
| Tenant mismatch | Subject có quyền ở tenant A, request truy cập tenant B | Inventory từ chối theo policy dữ liệu. |
| Actor chain sai | Service C tự khai actor D mà STS không xác nhận | Resource server không tin actor chain giả. |
| Token bị replay | Dùng token bearer bị sao chép hoặc proof DPoP cũ | Áp dụng TTL/binding/replay control; request không hợp lệ bị từ chối. |
| Cache context khác | Cùng subject nhưng actor/tenant/scope khác | Không dùng lại token từ context trước. |
| Revocation | Token bị thu hồi | Hành vi phù hợp với cơ chế revocation/introspection và độ trễ đã thiết kế. |
| STS downtime | Token endpoint timeout/5xx | Không fallback sang user token sai audience. |
| Token leak | Kiểm log, trace, exception, proxy | Không có raw `subject_token`, `actor_token`, access token hoặc client secret. |
| Redirect/SSRF | Upstream redirect tới host ngoài | Không forward credential tới host không tin cậy. |

Kiểm thử không chỉ xác nhận HTTP status. Cần kiểm tra token được gửi **đến đúng hostname**, audience và scope của token mới, actor context đã xác minh, không có token trong log và không có fallback khi STS từ chối. Với downstream, cần kiểm tra cả quyền trên từng bản ghi/tenant.

## 15. Checklist thiết kế delegation token

- [ ] Xác định rõ subject, actor, OAuth client và resource server trong mỗi hop.
- [ ] Phân biệt delegation với impersonation; quy định cách audit actor.
- [ ] Xác minh subject token trước exchange và xác thực workload với STS.
- [ ] Chỉ cho actor đã được policy cho phép; đánh giá `may_act` nếu profile sử dụng.
- [ ] Để STS phát hành `act` và token mới; không tự sửa hoặc ký lại claims.
- [ ] Giới hạn audience/resource, scope, tenant và thời hạn theo nguyên tắc least privilege.
- [ ] Downstream xác minh issuer, chữ ký/introspection, token type, audience, expiry, scope và actor.
- [ ] Có chính sách rõ cho JWT/opaque token, JWKS rotation, introspection, revocation và cache.
- [ ] Không log/lưu token, refresh token, actor token hoặc client secret ở nơi không cần thiết.
- [ ] Xử lý DPoP/mTLS binding theo từng hop; không reuse proof sai URI.
- [ ] Giới hạn số hop và loại actor trong chuỗi delegation.
- [ ] Fail closed khi STS hoặc policy service không khả dụng; không hạ cấp sang token sai audience.
- [ ] Kiểm thử cross-tenant, privilege escalation, actor spoofing, replay, cache và token leakage.

## 16. Kết luận và tài liệu tham khảo

Delegation token cho phép một service hành động thay một subject trong một phạm vi có kiểm soát. Điểm cốt lõi là **không trộn subject với actor**: user là chủ thể được đại diện; service là actor thực hiện lời gọi; STS xác minh quan hệ ủy quyền và cấp token mới cho resource server đích. Delegation khác impersonation, và việc có token hợp lệ không tự chứng minh actor được phép hành động thay subject. Mỗi resource server cần kiểm audience, scope, actor context và quyền trên dữ liệu của chính nó.

Tiêu chuẩn và tài liệu nên đối chiếu:

- **RFC 8693 — OAuth 2.0 Token Exchange:** subject/actor token, `act`, `may_act`, audience và token exchange grant.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** client, authorization server, resource owner và client credentials.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi bearer token và xử lý lỗi.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi access token/refresh token.
- **RFC 7519 — JSON Web Token:** cấu trúc và claims JWT.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT dành cho access token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** chỉ định resource mục tiêu khi xin token.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS và token ràng buộc chứng chỉ.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với bằng chứng sở hữu khóa.
