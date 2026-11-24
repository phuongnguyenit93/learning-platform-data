# Delegation giữa client và resource

## 1. OAuth 2.0 ủy quyền giữa những bên nào?

Trong chương **OAuth2 roles** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **delegation (ủy quyền)** là việc một client được trao khả năng truy cập **một resource cụ thể** trong **phạm vi xác định**, thay vì phải biết mật khẩu hay sở hữu toàn bộ đặc quyền của người dùng. OAuth 2.0 thiết kế một ranh giới tin cậy: **authorization server (AS)** cấp access token theo grant và policy; **resource server (RS)** chỉ cho client dùng token hợp lệ, được phát hành cho resource đó và đủ quyền.

Ví dụ: Alice dùng ứng dụng `sales-dashboard` để xem các đơn hàng mà Alice có quyền đọc. Ứng dụng không được tự tuyên bố `scope=orders.read` rồi lấy mọi đơn hàng. Nó phải đi qua quá trình ủy quyền hợp lệ, nhận access token **dành cho `orders-api`** và trình token khi gọi API. `orders-api` tiếp tục kiểm tra token, phạm vi truy cập và quyền của Alice đối với đơn hàng cụ thể.

> **Điểm cốt lõi:** Client **yêu cầu** quyền; AS **quyết định cấp** quyền; RS **thực thi** quyền. Người dùng có thể đồng ý một yêu cầu delegation nhưng không thể trao quyền vượt quá những gì bản thân hoặc chính sách tổ chức cho phép.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chính xác bốn OAuth roles: **resource owner**, **client**, **authorization server**, **resource server**.
2. Giải thích đường đi **yêu cầu quyền → consent/policy → cấp access token → kiểm tra tại RS**.
3. Tách **delegated user access** khỏi **app-only access** bằng client credentials và machine identity.
4. Sử dụng scope, audience, issuer, subject và client identity đúng ngữ cảnh; không xem token hợp lệ là quyền trên mọi object.
5. Thiết kế delegation giữa nhiều microservices bằng token exchange hoặc một mô hình service authority được kiểm soát.
6. Nhận diện confused deputy, token substitution, cross-tenant access, token theft và replay; triển khai kiểm tra trong Java/Spring Security.

Trong bài, các domain `example.test`, định danh client, token và bản ghi đều là ví dụ **giả định**, không phải endpoint hay credential sử dụng thực tế.

## 2. Bốn vai trò OAuth 2.0 và ranh giới trách nhiệm

RFC 6749 định nghĩa các vai trò cốt lõi như sau:

| Vai trò | Chịu trách nhiệm | Trong ví dụ đơn hàng | Không nên nhầm với |
| --- | --- | --- | --- |
| **Resource Owner (RO)** | Bên có khả năng cấp quyền truy cập tài nguyên được bảo vệ; khi là con người gọi là end-user | Alice có quyền đối với một số đơn hàng | OAuth client, AS hoặc người luôn có mọi quyền |
| **Client** | Ứng dụng yêu cầu truy cập tài nguyên, thay mặt RO hoặc nhân danh chính mình | `sales-dashboard` | Browser/user; client có thể có backend, frontend, nhiều thành phần |
| **Authorization Server (AS)** | Xác thực RO khi cần, đánh giá grant/consent/policy và cấp access token | `https://auth.example.test` | Resource server chỉ nhận token hoặc nơi mọi quyết định domain được giải quyết |
| **Resource Server (RS)** | Lưu trữ/phục vụ tài nguyên được bảo vệ, xác minh access token và phân quyền request | `orders-api` | AS cấp token; RS không được tự cấp scope qua request |

Một hệ thống thực tế có thể gộp AS và RS vào cùng sản phẩm hoặc cùng deployment. Dù vật lý ở đâu, **trách nhiệm logic và các phép kiểm tra vẫn phải được phân biệt**.

### 2.1. Sơ đồ delegation tối thiểu

~~~mermaid
flowchart LR
    U["Alice / Resource Owner"] -->|"Ủy quyền có kiểm soát"| AS["Authorization Server"]
    C["sales-dashboard / Client"] -->|"Xin scope + resource"| AS
    AS -->|"Phát hành access token cho orders-api"| C
    C -->|"Bearer access token"| RS["orders-api / Resource Server"]
    RS -->|"Xác minh token, scope, aud, object policy"| P["Đơn hàng được phép"]
    RS -.->|"JWKS hoặc introspection đáng tin"| AS
~~~

Đường nét đứt thể hiện RS có thể lấy khóa công khai từ JWKS hoặc hỏi trạng thái token qua introspection, tùy định dạng access token và thiết kế. Không có nghĩa mọi request JWT bắt buộc phải gọi AS.

### 2.2. Delegation không phải chuyển giao mật khẩu

Trong một OAuth flow được thiết kế đúng, client **không cần** biết mật khẩu của Alice để gọi `orders-api`. Alice xác thực tại AS hoặc nhà cung cấp danh tính liên quan; AS sau đó đánh giá quyền và cấp token phù hợp cho client.

Access token là **credential đại diện cho quyền được cấp trong ngữ cảnh nhất định**; nó không tự chứng minh Alice vừa đăng nhập hoặc được phép làm mọi việc Alice có thể làm. Trong OpenID Connect (OIDC), **ID token** phục vụ client xác thực end-user; **access token** được resource server nhận và xác minh để bảo vệ API.

### 2.3. “Client được phép truy cập” không đồng nghĩa “client là chủ sở hữu dữ liệu”

Một client có thể được phép đọc đơn hàng mà Alice được xem, nhưng không sở hữu quyền cập nhật tài khoản nhân sự hay truy cập đơn hàng thuộc tenant khác. AS có thể cấp scope `orders.read`, nhưng RS vẫn phải đối chiếu **quan hệ giữa principal, tenant và bản ghi**.

OAuth giải quyết khuôn khổ delegation, không chuẩn hóa toàn bộ mô hình domain như RBAC, ABAC hay access-control list cho từng object.

## 3. Hai ngữ cảnh chính: user-delegated và app-only

Không phải mọi access token đều “thay mặt người dùng”. Đây là ranh giới quan trọng nhất khi mô hình hóa các OAuth roles.

| Thuộc tính | **User-delegated access** | **App-only / machine-to-machine** |
| --- | --- | --- |
| Grant điển hình | Authorization Code + PKCE | Client Credentials |
| End-user trong grant | Có, thường cần authentication | Không cần user tương tác |
| Cơ sở quyền | Quyền của RO, client allowlist, consent nếu cần, AS policy | Client/service registration, workload identity và AS policy |
| Principal chính | User/subject cùng OAuth client/actor tùy profile | Client/service principal |
| Scope | Quyền client được delegation trong giới hạn user và policy | Quyền được cấp trực tiếp cho client/service |
| Resource server kiểm tra | Token + user/tenant/object ACL + client context nếu yêu cầu | Token + service identity/tenant/object policy |
| Refresh token | Có thể được cấp theo grant, client type và AS policy | Không nên mặc định cấp; RFC 6749 nói **SHOULD NOT** trong client credentials |
| Consent screen | Có thể xuất hiện, không bắt buộc mọi lần | Thường không có user consent screen |

**Sai lầm nguy hiểm:** đọc claim `sub` rồi luôn coi nó là một human end-user. Một AS có thể dùng `sub=client_id` hoặc một service principal cho client credentials theo profile. API cần biết **loại token và grant semantics** thay vì áp một cách diễn giải duy nhất cho mọi token.

### 3.1. User-delegated access

Ví dụ Alice dùng dashboard để đọc đơn hàng của chính nhóm bán hàng:

~~~text
RO:           Alice
Client:       sales-dashboard
AS:           auth.example.test
RS:           orders-api
Requested:    orders.read orders.write
Client policy: orders.read
Granted:      orders.read
Audience:     orders-api
~~~

Nếu Alice đồng ý cả đọc và ghi nhưng AS chỉ đăng ký quyền đọc cho `sales-dashboard`, AS vẫn không được cấp quyền ghi. Nếu token đã có `orders.read`, RS vẫn không được trả đơn hàng mà Alice không được xem.

### 3.2. App-only access

Ví dụ một job `inventory-sync` cần đọc danh mục sản phẩm:

~~~text
Principal:    inventory-sync-prod (service/client identity)
Grant:        client_credentials
Requested:    inventory.read
AS policy:    client được gọi inventory-api, không được gọi payments-api
Granted:      inventory.read
Audience:     inventory-api
~~~

Không có Alice cấp quyền cho job này. Phê duyệt quyền có thể do quản trị viên/cơ chế chính sách AS thực hiện. Nếu một hành động machine-to-machine được kích hoạt bởi yêu cầu từ Alice, backend vẫn phải biết liệu thao tác là **quyền riêng của service** hay **đang thực hiện thay mặt Alice**; không được dùng service token mạnh để vượt quyền người dùng.

### 3.3. Khi nào resource owner không phải end-user?

Theo định nghĩa của OAuth 2.0, resource owner là thực thể có khả năng cấp quyền truy cập; nó không nhất thiết luôn là con người. Tuy nhiên, các profile/grant có semantics riêng. Không dựng consent UI giả cho client credentials, và không gán human subject vào token machine chỉ để tái sử dụng một authorization rule vốn viết cho end-user.

## 4. Luồng delegated authorization: Authorization Code + PKCE

Đối với ứng dụng hướng tới người dùng, **Authorization Code + PKCE** là một luồng được khuyến nghị rộng rãi để client yêu cầu quyền mà không trực tiếp nắm mật khẩu người dùng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Resource Owner
    participant C as sales-dashboard / Client
    participant AS as Authorization Server
    participant RS as orders-api / Resource Server
    U->>C: Bấm "Xem đơn hàng"
    C->>AS: Authorization request: scope=orders.read, PKCE, state
    AS->>U: Authentication + consent nếu policy yêu cầu
    U-->>AS: Xác thực / cho phép
    AS->>AS: Kiểm tra client, redirect, quyền user, scope, resource
    AS-->>C: Authorization code về redirect URI đã đăng ký
    C->>AS: POST /token: code + code_verifier (+ client auth nếu cần)
    AS-->>C: Access token aud=orders-api, scope=orders.read
    C->>RS: GET /orders/123 + Authorization: Bearer AT
    RS->>RS: Verify issuer, signature/active, aud, exp, scope, tenant/ACL
    RS-->>C: Trả dữ liệu được phép hoặc 401/403
~~~

Các điều kiện bắt buộc phụ thuộc loại client và phiên bản/profile: confidential client phải xác thực phù hợp tại token endpoint; public client không được dựa vào một client secret nhúng trong browser/mobile để chứng minh bí mật. PKCE ràng buộc authorization code với `code_verifier`, trong khi `state` giúp client ràng buộc authorization response với transaction, ngăn CSRF theo thiết kế.

### 4.1. Authorization request minh họa

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20orders.read&state=<unpredictable-state>&code_challenge=<pkce-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

`openid` ở đây là scope OIDC dùng cho xác thực end-user; `orders.read` là scope nghiệp vụ để xin quyền ở `orders-api`. Để chỉ rõ API đích, AS có thể hỗ trợ **resource indicator** (RFC 8707), ví dụ `resource=https://orders.example.test/`, với quyết định audience dựa trên policy.

Các placeholder `<...>` chỉ để diễn giải; giá trị chạy thật phải được tạo đúng chuẩn và không đưa authorization code/PKCE verifier vào log.

### 4.2. Đổi code lấy token

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<authorization-code>&redirect_uri=<registered-redirect-uri>&client_id=sales-dashboard&code_verifier=<original-verifier>
~~~

Authorization code có thời hạn ngắn, bị ràng buộc với client và các điều kiện grant, và **chỉ được đổi một lần**. Nếu hai thread cùng đổi code, AS phải thực thi single-use nguyên tử; client không được lấy response mất do timeout làm lý do yêu cầu AS cấp token vô hạn từ cùng code.

Một token response giả định:

~~~json
{
  "access_token": "<access-token-for-orders-api>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Nếu response có ID token vì client dùng OIDC, ID token **không phải** bearer access token để gửi cho `orders-api`. Client phải dùng chính access token dành cho API. Với refresh token, việc AS cấp hay không còn phụ thuộc grant, scope, loại client, policy và các yêu cầu OIDC liên quan.

## 5. Client Credentials: quyền của service không phải quyền user

Trong OAuth client credentials grant, client xác thực với AS để xin access token cho **quyền của chính client** đã được phê duyệt:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

HTTP Basic ở đây là ví dụ khi confidential client được đăng ký sử dụng `client_secret_basic`; OAuth cũng có các phương pháp phù hợp khác như private-key JWT, mTLS hoặc workload identity federation theo profile/AS. Không hardcode client secret vào repository hoặc nhúng trong ứng dụng public client.

Nếu AS cấp JWT có audience `inventory-api`, `inventory-api` xác minh:

1. **Nguồn phát hành** và khóa ký hoặc introspection endpoint thuộc AS tin cậy.
2. **Token type/profile** đúng access token; token không phải ID token hay client assertion.
3. **Audience** là `inventory-api`, không phải một API khác.
4. **Scope** `inventory.read` đủ cho tác vụ; quyền client không vượt policy.
5. **Principal và tenant** là service/machine được phép truy cập dữ liệu cụ thể.

Một service token không nên được API ngầm hiểu là “Alice đã đồng ý” hoặc “Alice đang làm việc” nếu không có bằng chứng delegation hợp lệ. Kết luận “service được quyền X” khác hoàn toàn “Alice được quyền X”.

## 6. Scope, consent và scope policy: client không tự cấp quyền

Trong OAuth 2.0, client có thể **yêu cầu** một hoặc nhiều scope. AS đánh giá client registration, grant, quyền của resource owner hoặc service, consent khi áp dụng, chính sách tổ chức, audience và điều kiện rủi ro trước khi phát hành access token.

Ví dụ:

~~~text
Client requested:       orders.read orders.write
Registered client:      orders.read
Alice authorization:    orders.read orders.write (trong tenant shop-a)
Consent:                orders.read
AS policy allowed:      orders.read
Granted to client:      orders.read (cho orders-api)
~~~

AS có thể thu hẹp scope hoặc từ chối yêu cầu theo profile/chính sách; OAuth 2.0 không bắt buộc mọi AS tự động cấp phần giao còn hợp lệ. Khi granted scope khác requested scope, token response cần phản ánh granted scope theo RFC 6749. **Client phải dùng quyền thực sự được cấp, không dùng chuỗi scope mà nó tự gửi lên để quyết định quyền.**

### 6.1. Consent không thay thế quyền

**Consent** là sự chấp thuận cho client truy cập trong những điều kiện đã xác định. Alice không thể cấp cho `sales-dashboard` quyền đọc đơn hàng của tenant `shop-b` nếu Alice vốn không được đọc chúng. Một admin có thể phê duyệt app/scope theo chính sách tổ chức, nhưng admin consent cũng không tự cho mọi subject quyền trên mọi bản ghi.

Ngoài ra, **consent screen không bắt buộc xuất hiện trong mọi token issuance**: có thể đã consent trước đó, có chính sách pre-authorization, hoặc grant không có end-user tương tác như client credentials.

### 6.2. Scope khác role và object-level authorization

Một resource server có thể yêu cầu điều kiện:

~~~text
ALLOW GET /orders/123 IF:
  accessToken.validFor(orders-api)
  AND accessToken.hasExactScope("orders.read")
  AND principal.isActive()
  AND order(123).tenantId == principal.allowedTenant
  AND domainPolicy.canRead(principal, order(123))
~~~

Scope `orders.read` giới hạn **loại thao tác** client được ủy quyền; role/ACL/ABAC của hệ thống xác định **người nào truy cập bản ghi nào**. Dùng `scope.contains("orders.read")` là sai nếu scope là chuỗi vì có thể khớp nhầm `orders.readonly`; hãy tách danh sách scope theo profile và so khớp **token nguyên vẹn**.

### 6.3. Delegation nên là quyền tối thiểu

Một thiết kế tốt thường:

- Định nghĩa scope rõ theo API/tác vụ: `orders.read`, `orders.write`, `orders.export`.
- Chỉ xin `orders.read` khi người dùng cần xem danh sách; xin thêm `orders.write` bằng authorization flow hợp lệ nếu chức năng cần.
- Giới hạn scope theo registration và grant type, ví dụ client credentials không tự xin scope quản trị user.
- Áp quyền object/tenant tại RS, kể cả khi scope hợp lệ.
- Áp TTL ngắn và audience hẹp để giảm tác động nếu access token bị lộ.

**Không dùng refresh token để tự tăng scope** ngoài phạm vi grant được cấp. Request thêm quyền cần được AS đánh giá qua luồng hợp lệ; đối với refresh token, RFC 6749 không cho phép xin scope mở rộng vượt scope đã được resource owner cấp ban đầu.

## 7. Audience: bảo đảm token thực sự dành cho resource server

Một AS có thể phục vụ `orders-api`, `inventory-api` và `payments-api`. Vì tất cả cùng tin chữ ký AS, nếu RS chỉ kiểm tra `iss` và chữ ký mà **bỏ qua `aud`**, token dành cho API ít nhạy cảm có thể bị dùng ở API nhạy cảm — một đường dẫn điển hình đến **cross-resource token substitution** và **confused deputy**.

Ví dụ JWT payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["inventory-api"],
  "client_id": "sales-dashboard",
  "scope": "inventory.read",
  "exp": 1795400300
}
~~~

Token này **không được chấp nhận tại `orders-api`**. Kể cả nó có `scope=orders.read` và chữ ký đúng, `aud=inventory-api` đã xác định token **không dành cho orders**.

### 7.1. Audience là resource identity, không phải client ID

| Giá trị | Định nghĩa trong contract | Không được suy ra |
| --- | --- | --- |
| `iss=https://auth.example.test` | AS nào phát hành token | Mọi API tin AS đều có quyền chấp nhận |
| `aud=orders-api` | Token dành cho RS `orders-api` | User/client có quyền trên mọi đơn hàng |
| `client_id=sales-dashboard` | Client đã được cấp token | Đây là user hoặc resource |
| `sub=alice` | Chủ thể token theo profile | Alice hiện được phép làm mọi tác vụ |
| `scope=orders.read` | Quyền loại tác vụ đã được cấp | Được đọc cross-tenant |
| `exp` | Thời hạn chấp nhận token | Token chưa bị thu hồi hoặc quyền vẫn còn hiệu lực |

Trong OIDC, ID token thường có audience là **OIDC client**, còn OAuth access token có audience là **resource/API**. API không được nhận ID token thay access token chỉ vì signature và `sub` trông hợp lệ.

### 7.2. Resource Indicators (RFC 8707)

Nếu AS hỗ trợ, client có thể chỉ định resource cụ thể:

~~~text
resource=https://orders.example.test/
scope=orders.read
~~~

AS dùng resource request như **một đầu vào cần kiểm tra**. AS phải xác định client và grant có quyền truy cập resource đó; không được tự cấp mọi audience chỉ vì client gửi một URI hợp lệ. Với token profile dùng `aud="https://orders.example.test/"`, RS phải so sánh theo **định danh đã thống nhất với AS**, không tự suy từ `Host` header do client kiểm soát.

### 7.3. Multi-audience không mặc định là sai, nhưng làm rộng ranh giới

Một JWT có `aud=["orders-api","inventory-api"]` có thể hợp lệ theo cấu trúc JWT nếu AS chủ động cấp. Tuy nhiên, token bearer dùng được ở hai resource làm mở rộng nơi token có giá trị và đòi hỏi policy scope nhất quán. Với các API nhạy cảm, **ưu tiên token riêng cho mỗi resource**; nếu dùng multi-audience, RS phải có allowlist/policy rõ và kiểm tra audience của chính mình, không kiểm tra “token có ít nhất một audience trong danh sách API của công ty”.

## 8. Client identity, subject identity và actor: ai thực sự hành động?

Một token có thể biểu diễn **user đang được ủy quyền**, **service được quyền hành động**, hoặc **actor đang thay mặt subject**. Việc ghi nhận và kiểm tra sai vai trò dẫn đến lỗ hổng nghiệp vụ và audit gây hiểu nhầm.

### 8.1. Hai câu hỏi độc lập

Đối với request `POST /orders/123/cancel`:

1. **Ai là chủ thể được quyền tác động đến đơn hàng?** Ví dụ Alice, một service principal, hoặc một actor/subject rõ theo delegation.
2. **Client/workload nào đang trình token để thực hiện request?** Ví dụ `sales-dashboard` hoặc `order-orchestrator`.

Câu trả lời có thể khác nhau: Alice là user được delegation, còn `sales-dashboard` là client. Nếu `order-orchestrator` gọi backend thay Alice, actor có thể là `order-orchestrator` và subject là Alice theo token exchange profile.

### 8.2. Claim semantics phụ thuộc token profile

| Claim/thuộc tính | Thường biểu diễn gì? | Lưu ý |
| --- | --- | --- |
| `sub` | Subject của token | Có thể là user hoặc service, tùy grant/profile |
| `client_id` | OAuth client được cấp token | RFC 9068 có quy tắc cụ thể; không đồng nghĩa `sub` |
| `aud` | Resource server nhận token | Không phải luôn là client ID; xem loại token |
| `scope` | Quyền được cấp | Không đồng nghĩa role hoặc mọi object permission |
| `act` | Actor trong token-exchange profile khi có | Chỉ tin sau khi verify; cấu trúc/ngữ nghĩa phải theo AS contract |
| `azp` | Authorized party trong các profile có dùng, đặc biệt OIDC | Không áp nó thay `client_id` hoặc audience cho mọi JWT |
| `tenant_id` | Tenant theo extension của AS/app | Không phải registered claim phổ quát; cần hiểu nguồn và chính sách |
| `jti` | Token identifier | Hữu ích cho audit/revocation nếu AS/RS có trạng thái; không tự chống replay |

Không nên ghép tất cả claims `roles`/`groups`/`scp`/`scope` thành một tập quyền toàn hệ thống. Mỗi AS/token profile phải quy định rõ converter và mapping. Ví dụ Spring Security mặc định có thể chuyển OAuth scope sang authority `SCOPE_...`, còn custom roles cần được mapping riêng.

### 8.3. Phân biệt impersonation và delegation có actor

**Impersonation** thường mô tả một bên hành động như chủ thể khác, đôi khi không giữ danh tính actor trong token/đường truy vết. **Delegation có actor** giữ thông tin cả subject và actor khi contract hỗ trợ, để downstream biết ai đang đại diện cho ai.

Đối với hệ thống giao dịch quan trọng, hãy ưu tiên audit có đủ thông tin:

~~~text
subject = Alice
actor = order-orchestrator
client = sales-dashboard / exchange client theo contract
resource = payments-api
action = payments.create
authorization = grant/policy đã được AS và RS xác minh
~~~

Đây là **mô hình audit ứng dụng**, không phải tập claims chuẩn bắt buộc trong mọi token. Không tạo `act=order-orchestrator` bằng cách cho client tự thêm header `X-Actor` rồi dùng nó cấp quyền.

## 9. Delegation qua nhiều service: không chuyển tiếp access token tùy tiện

Một client có thể gọi service A, rồi service A cần gọi service B:

~~~text
Browser -> orders-api -> payments-api
~~~

Trên hop đầu, browser gửi token `aud=orders-api` cho `orders-api`. Khi orders gọi payments, **không mặc định chuyển tiếp nguyên token**: `payments-api` phải yêu cầu token **dành cho payments**, và quyền thực hiện thao tác thanh toán không tự xuất hiện từ scope đọc đơn hàng.

### 9.1. Mẫu nguy hiểm: forward Bearer token sai audience

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant O as orders-api
    participant P as payments-api
    U->>O: AT aud=orders-api, scope=orders.read
    O->>P: Forward cùng AT (sai resource)
    P->>P: Chỉ kiểm tra chữ ký/iss; bỏ aud
    P-->>O: Trả dữ liệu hoặc thực hiện hành động trái grant
~~~

Nếu `payments-api` có credential backend đủ mạnh và thực hiện hành động vì token sai resource, nó có thể trở thành **confused deputy**. Một issuer dùng chung không biến access token thành credential phổ quát giữa các API.

### 9.2. Token exchange theo RFC 8693

Khi cần delegation giữa services, AS/security token service (STS) có thể hỗ trợ **OAuth 2.0 Token Exchange**:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant O as orders-api / downstream client
    participant AS as Authorization Server / STS
    participant P as payments-api
    U->>O: AT1: aud=orders-api
    O->>O: Verify AT1, quyền Alice trên yêu cầu
    O->>AS: Token exchange: AT1 + resource=payments-api + scope
    AS->>AS: Check client, subject, actor, scope, audience, policy
    AS-->>O: AT2: aud=payments-api, quyền được phép
    O->>P: Authorization: Bearer AT2
    P->>P: Verify AT2 + subject/actor + object policy
    P-->>O: Kết quả hợp lệ hoặc từ chối
~~~

Một request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-service-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<incoming-access-token>&subject_token_type=urn:ietf:params:oauth:token-type:access_token&resource=https%3A%2F%2Fpayments.example.test%2F&scope=payments.create
~~~

Đây là ví dụ về **cấu trúc giao thức**, không phải endpoint luôn được AS hỗ trợ. Token exchange chỉ thành công nếu AS đã đăng ký client/actor, hiểu subject token, xác minh trust, cho phép resource và scope, và kiểm tra policy tương ứng. AS **không được tự động nâng quyền** từ `orders.read` thành `payments.create` chỉ vì một service có khả năng gọi token endpoint.

### 9.3. Subject và actor trong token exchange

RFC 8693 cung cấp các khái niệm subject token, actor token và claim `act` trong những cấu hình/profile phù hợp. Ví dụ payload **để minh họa cách giữ dấu vết delegation**, không phải output bắt buộc của mọi AS:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["payments-api"],
  "scope": "payments.create",
  "client_id": "order-orchestrator",
  "act": {
    "sub": "order-orchestrator"
  },
  "exp": 1795400300
}
~~~

Resource server phải hiểu rõ `sub`, `act` và `client_id` theo contract của AS trước khi dùng để phân quyền. Không cho actor tự khai báo `sub=admin` hoặc client tự chọn quyền sau exchange.

### 9.4. Token exchange khác chuyển tiếp token và khác client credentials

| Cách gọi xuống service B | Identity/authority | Rủi ro cần tránh |
| --- | --- | --- |
| Forward access token của A | Token vẫn `aud=A`, có thể không hợp lệ tại B | B bỏ audience và chấp nhận sai resource |
| Token exchange/OBO | Token mới `aud=B`; có thể bảo toàn user/actor theo profile | AS tự nâng quyền hoặc RS không hiểu actor |
| Client credentials của service A | Service A hành động bằng quyền **của nó** | Bỏ qua quyền Alice nếu thao tác do Alice yêu cầu |
| Backend giữ token riêng được cấp cho B | Token đúng B và được cấp theo grant phù hợp | Cache sai principal/tenant/scope hoặc lộ credential |

**Không có cách nào mặc nhiên đúng cho mọi nghiệp vụ.** Nếu service thực hiện tác vụ hệ thống độc lập, app-only token có thể phù hợp. Nếu thực hiện thao tác nhạy cảm thay mặt Alice, cần cơ chế delegation hoặc ràng buộc user authorization bảo đảm quyền thực tế của Alice.

## 10. Resource server không trao quyền bằng cách chỉ xác minh chữ ký

Trong RS, **authentication/validation** và **authorization** là hai bước khác nhau. Authentication của bearer token thường có nghĩa RS xác minh credential hợp lệ từ AS tin cậy và tạo security principal đúng profile. Authorization hỏi principal/client/actor có quyền thực hiện **thao tác này trên tài nguyên này** không.

### 10.1. Checklist validation trước khi cấp quyền

Với JWT access token:

1. Chỉ chấp nhận định dạng/profile access token đã quy định; tránh nhầm ID token, refresh token hay JWT client assertion.
2. Cấu hình issuer tin cậy, JWKS/key set và thuật toán cho phép; không tải `jku`/`x5u` tùy ý trong JOSE header.
3. Xác minh chữ ký JWT và claims dạng dữ liệu hợp lệ; áp giới hạn parser/DoS hợp lý.
4. Yêu cầu `iss` đúng và `aud` chứa **expected audience của chính RS**.
5. Kiểm tra `exp`, `nbf` và các quy tắc thời gian theo profile, với clock skew nhỏ.
6. Kiểm tra granted scope/authority đúng action, loại grant/principal và tenant/domain policy.

Với opaque access token, RS dùng **introspection endpoint được cấu hình và xác thực**; chỉ tin `active` và các metadata theo hợp đồng được AS trả về. `active=true` không tự cho phép token ở mọi API: cần bảo đảm audience/resource binding, scope, principal và quyền object. Không fail open khi introspection timeout.

### 10.2. Bảng quyết định khi Alice gọi orders-api

| Trạng thái token/request | Kết quả tại `orders-api` |
| --- | --- |
| JWT ký đúng, issuer đúng, `aud=orders-api`, `scope=orders.read`, Alice có quyền order 123 | Cho phép đọc order 123 |
| JWT ký đúng, issuer đúng, `aud=inventory-api`, scope giống nhau | **Từ chối** vì sai resource |
| JWT đúng audience nhưng không có `orders.read` | **Từ chối** do insufficient scope |
| JWT đúng audience/scope, order thuộc tenant khác | **Từ chối** do object policy |
| JWT `exp` hết hạn | **Từ chối** dù user còn session |
| ID token OIDC với `sub=alice` dùng như access token | **Từ chối** vì sai token type/purpose |
| Client credentials token hợp lệ của `inventory-sync`, nhưng endpoint yêu cầu user-delegated action | **Từ chối** nếu service không được policy cho phép |
| Opaque token `active=false` | **Từ chối** kể cả client gửi scope tùy ý ngoài request |

Ở API dùng OAuth Bearer, token không hợp lệ thường trả `401` kèm `WWW-Authenticate: Bearer error="invalid_token"`; token hợp lệ nhưng thiếu scope thường trả `403` với `insufficient_scope` theo RFC 6750. Với object-level policy, hệ thống có thể chọn `403` hoặc `404` theo chống lộ thông tin.

### 10.3. Không tạo quyền từ header do client gửi

Không để frontend tự gửi:

~~~http
X-User: alice
X-Role: ADMIN
X-Tenant: shop-a
X-Actor: trusted-orchestrator
~~~

rồi dùng các giá trị đó thay thế token validation. Nếu gateway cung cấp identity headers cho backend, phải có **trust boundary bảo vệ hop**, gateway ghi đè header từ client và backend chỉ tin gateway xác thực. Trong nhiều hệ thống, RS xác minh access token trực tiếp dễ kiểm toán hơn.

## 11. AS policy và resource policy phải bổ sung cho nhau

**Authorization server policy** xác định token nào được phép phát hành. **Resource-server policy** xác định hành động nào được thực hiện trên tài nguyên hiện tại. Trong nhiều hệ thống, AS không sở hữu dữ liệu đơn hàng nên không thể ra quyết định cuối cùng cho từng order ID.

### 11.1. Các quyết định thường nằm ở AS

| Chính sách | Câu hỏi AS kiểm tra | Ví dụ |
| --- | --- | --- |
| Client registration | Client có được quyền xin grant/scope này? | Dashboard chỉ có `orders.read` |
| Client authentication | Confidential client có chứng minh danh tính đúng? | Private key JWT hoặc mTLS được đăng ký |
| Resource owner | Alice có được quyền delegation hành động này? | User có quyền thuộc tenant `shop-a` |
| Consent/pre-authorization | RO/admin/organization đã cho phép client truy cập trong phạm vi này? | Consent `orders.read` |
| Audience/resource | Token được cấp cho resource nào? | `aud=orders-api` |
| Grant restrictions | User-delegated hay client credentials, loại grant có được cho phép? | Không cấp scope user-only cho machine client |
| TTL/refresh | Access token sống bao lâu, có cấp refresh token không? | AT 5 phút, RT theo policy |
| Risk and session controls | Có cần MFA/step-up, thiết bị tin cậy hay điều kiện khác? | Export nhạy cảm yêu cầu xác thực mạnh |

Không phải tất cả khả năng trên là yêu cầu cấu hình bắt buộc của OAuth 2.0 core; có những policy phụ thuộc IAM product và extension cụ thể. Điều cần giữ là **token được cấp theo cơ sở quyền đáng tin**, không theo ý muốn đơn phương của client.

### 11.2. Những quyết định thường nằm ở resource server

~~~text
Resource request: GET /v1/orders/123
Actor/subject:   Alice through sales-dashboard
Access token:    iss=auth.example.test; aud=orders-api; scope=orders.read

orders-api:
  (1) Validate token profile and issuer/signature/status
  (2) Validate aud/exp/nbf and exact granted scope
  (3) Resolve order 123 from trusted data store
  (4) Enforce order.tenantId == principal.allowedTenant
  (5) Enforce assignment/owner/role/domain constraints
  (6) Audit subject + client/actor + action
~~~

Nếu order 123 thuộc tenant B trong khi Alice chỉ có quyền tenant A, RS phải từ chối dù token được AS ký hợp lệ. Không chỉ lấy `tenant_id` từ URL, query param hoặc header rồi coi client đã chứng minh thuộc tenant đó.

### 11.3. Bounded delegation

Một hệ thống an toàn nên coi delegated authority là **bị chặn trên bởi nhiều ranh giới**:

\[
\text{AllowedAction} =
\text{ValidTokenForResource}
\land \text{GrantedScope}
\land \text{PrincipalPermission}
\land \text{DomainPolicy}
\]

Đây là biểu diễn logic minh họa, không phải công thức giao thức bắt buộc. Với user delegation, có thể thêm actor/client policy, consent và tenant constraints. Với machine identity, không dùng “quyền của Alice” làm điều kiện nếu không tồn tại Alice; thay bằng policy của service principal.

Không nên dựng API trả dữ liệu chỉ vì `hasAuthority("SCOPE_orders.read")` mà bỏ kiểm tra quyền với bản ghi.

## 12. Access token, refresh token và vòng đời delegation

Delegation không kết thúc ở thời điểm AS cấp token. Quyền của user, đăng ký client, consent và trạng thái phiên có thể thay đổi trong khi token còn hiệu lực.

### 12.1. Access token sống ngắn, refresh token không phải access token

- **Access token** được client gửi tới RS; phải đúng issuer/audience/scope/time/token profile.
- **Refresh token** được client gửi tới **token endpoint của AS** để xin AT mới nếu grant và policy còn hợp lệ. Không gửi RT tới resource API.
- **ID token** của OIDC giúp client xác thực end-user; không dùng làm bearer token cho API.
- **Authorization code** là credential ngắn hạn dùng một lần trong authorization code flow; không được dùng trực tiếp để gọi RS.

Một access token bearer có thể bị sao chép và phát lại trong thời gian hiệu lực. Cấp token ngắn hạn **giảm thời gian nguy cơ** nhưng không loại bỏ replay tức thì.

### 12.2. Refresh-token rotation và phạm vi grant

Nếu AS dùng refresh-token rotation, một RT được đổi thành RT mới và bản cũ bị vô hiệu:

~~~text
RT-1 --refresh--> RT-2 --refresh--> RT-3
~~~

Việc dùng lại RT cũ có thể bị coi là replay và dẫn đến revocation theo chính sách AS. Client cần **single-flight**, tránh nhiều tab/Pod cùng đổi RT-1, lưu cặp AT/RT mới theo version/CAS và không tự tăng scope hoặc audience ngoài grant được cho phép.

Đối với client credentials, thường không cấp refresh token; service xác thực lại với AS để xin AT theo policy. Không thêm một user consent screen giả vào client credentials chỉ để mô phỏng user delegation.

### 12.3. Logout/revocation và quyền thay đổi

Khi Alice logout hoặc rút consent:

1. Ứng dụng đóng session local và xóa những token nó quản lý.
2. Nếu cần ngăn xin AT mới, gọi revocation endpoint (RFC 7009) hoặc grant/session revocation API theo AS.
3. RS phải xác định **access token còn hạn** có bị chặn ngay không. JWT xác minh offline có thể tiếp tục được chấp nhận tới `exp` nếu không có trạng thái thu hồi/denylist bổ sung.
4. Với opaque token, introspection có thể trả `active=false` khi AS đã revoke; cache `active=true` vẫn có thể gây trễ.
5. Nếu user mất role/tenant permission, domain policy nên chặn phù hợp; không mặc định claim role cũ trong JWT cập nhật tức thì.

**Logout không đồng nghĩa refresh-token rotation.** Rotation duy trì một grant còn hợp lệ; logout nhằm chấm dứt khả năng tiếp tục dùng grant/RT theo phạm vi được yêu cầu.

### 12.4. Thời điểm AS và RS không nhất quán

Ví dụ:

~~~text
10:00 AS phát hành AT cho Alice, aud=orders-api, exp=10:05.
10:01 Admin rút quyền đọc đơn hàng của Alice.
10:02 RS xác minh JWT offline và chỉ check scope.
~~~

RS có thể còn chấp nhận token cũ nếu nó không kiểm tra quyền domain hiện tại hoặc trạng thái revoked. Nếu policy yêu cầu thu hồi ngay, cần kiểm tra trạng thái user/ACL, introspection/denylist hoặc cơ chế đồng bộ tương đương. Việc chọn TTL ngắn đơn thuần không thể đảm bảo revocation tức thời.

## 13. Phòng chống token theft, replay và confused deputy

| Mối đe dọa | Hệ quả trong delegation | Biện pháp |
| --- | --- | --- |
| **Bearer token theft** | Attacker gửi access token thay client hợp lệ | TLS, hạn chế log/storage, TTL ngắn, scope/audience hẹp, sender constraint khi cần |
| **Token replay** | Token bị sao chép được trình nhiều lần khi còn hạn | DPoP/mTLS-bound AT và replay checks đúng profile; không chỉ dựa vào `jti` có mặt |
| **Cross-resource token substitution** | Token của A bị dùng ở B | RS check `aud` chính xác, AS cấp token cho resource đã phê duyệt |
| **Confused deputy** | Service quyền cao bị lợi dụng hành động vượt quyền caller | Phân biệt user/service authority, token exchange và domain checks |
| **Consent phishing/over-scoping** | App độc hại xin quyền rộng hơn nhu cầu | Client allowlist, publisher validation, scope tối thiểu, consent UX rõ |
| **Cross-tenant access** | Token scope đúng nhưng đọc bản ghi tenant khác | Tenant/object policy từ dữ liệu đáng tin tại RS |
| **Token type confusion** | ID token hoặc client assertion dùng làm access token | Kiểm tra token type/profile và audience |
| **Stale permission** | Access token cũ vẫn chứa scope/role khi quyền đã rút | TTL, online state checks, revocation/ACL policy |
| **Key/source confusion** | RS tin khóa/JWKS của issuer không được phê duyệt | Cấu hình issuer/JWKS tin cậy; không fetch `jku` tùy ý |
| **Client credential leak** | Attacker mint AT qua client credentials | Secret manager, private-key auth/workload identity, rotation, audit |

### 13.1. Sender-constrained tokens không thay audience

Bearer token thông thường chỉ cần bị sao chép là có thể trình lại. **DPoP (RFC 9449)** gắn token với public key và yêu cầu HTTP proof phù hợp (`htm`, `htu`, `iat`, `jti`, `ath`/nonce theo profile). **mTLS certificate-bound access token (RFC 8705)** gắn token với chứng chỉ client; RS phải so ràng buộc token–certificate với TLS peer đã xác minh.

Hai cơ chế này giảm giá trị của chuỗi token bị sao chép **một mình**. Nhưng:

- Client hợp lệ sở hữu private key vẫn **không được** dùng token `aud=orders-api` ở `payments-api`.
- Actor có thể vẫn vượt quyền nếu RS chỉ check possession proof mà không check scope/domain.
- Nếu attacker chiếm cả token lẫn private key/proof generation, sender constraint không còn là bảo đảm đầy đủ.

### 13.2. TLS và nơi lưu token

Mọi trao đổi `authorization_code`, access token, refresh token và client authentication phải dùng TLS với **certificate + hostname validation**. Một HTTP client có `TrustManager` chấp nhận mọi chứng chỉ có thể gửi RT/client secret tới attacker giả mạo AS.

Không đưa token vào query URL, log, tracing, error message hoặc analytics. Trong browser, cân nhắc BFF bảo vệ RT phía server và quản lý cookie session an toàn; không tin rằng `HttpOnly` tự ngăn CSRF/XSS. Native app nên dùng secure storage phù hợp nền tảng và lưu ý refresh token rotation/revocation.

### 13.3. Confused deputy với service token quyền cao

Một ví dụ nguy hiểm:

~~~text
Alice: được xem đơn hàng 123, không được hủy thanh toán.
orders-api: có service token payments.admin cho công việc nội bộ.
Alice gọi POST /orders/123/cancel-payment.
orders-api: chỉ check Alice đã đăng nhập, rồi dùng payments.admin để hủy.
~~~

Nếu không có quy tắc ủy quyền nghiệp vụ xác định Alice được phép hủy khoản thanh toán đó, `orders-api` dùng đặc quyền service làm thay điều Alice không được phép. Đây là **confused deputy**, kể cả mọi token có chữ ký hợp lệ.

Phòng vệ là kiểm tra **quyền caller trên hành động cụ thể** và giới hạn service authority; khi cần delegation trực tiếp tới payments, dùng AS token exchange/OBO theo policy, giữ subject/actor và audience đúng. Service token chỉ được dùng cho thao tác hệ thống độc lập theo contract.

## 14. Java/Spring Security: phân biệt resource server và OAuth client

Spring Security có hai nhóm khả năng dễ bị nhầm:

- **Resource Server:** nhận bearer access token từ caller, xác minh nó và bảo vệ API.
- **OAuth2 Client:** lấy/quản lý access token mà ứng dụng sẽ dùng **khi chính nó gọi một API khác**.

Một service trong microservice architecture **có thể vừa là RS vừa là OAuth client**, nhưng đây là **hai chiều tin cậy**. Nhận token `aud=orders-api` từ Alice không có nghĩa service được chuyển token đó đến `payments-api`.

### 14.1. Cấu hình resource server nhận JWT

Ví dụ Spring Boot/Spring Security 6.x cho `orders-api`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

`issuer-uri` giúp chọn issuer tin cậy và JWKS qua metadata theo framework/version. **Nó không tự biết audience nghiệp vụ `orders-api` của bạn** trong mọi cấu hình. Cần kiểm tra audience độc lập trước khi tạo principal có quyền.

### 14.2. JwtDecoder xác minh issuer và audience

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class OrdersResourceSecurity {

    private static final String TRUSTED_ISSUER =
            "https://auth.example.test";
    private static final String JWKS_URI =
            "https://auth.example.test/oauth2/jwks";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Access token was not issued for orders-api",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audience));
        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Diễn giải:**

1. Decoder lấy khóa từ JWKS URL **cố định thuộc issuer đáng tin**, không từ URL tùy ý trong JWT.
2. `JwtValidators.createDefaultWithIssuer` kiểm tra issuer và các điều kiện mặc định của framework; audience validator yêu cầu `aud` chứa **đúng `orders-api`**.
3. `SCOPE_orders.read` và `SCOPE_orders.write` minh họa mapping scope thành authority theo converter mặc định của Spring Security. Nếu AS dùng `scp` dạng mảng, roles khác hoặc custom token profile, converter cần được cấu hình **có chủ đích**.
4. Ví dụ giả định JWT ký RS256; trong production, thuật toán/trust/key rotation/token `typ` profile phải khớp hợp đồng AS và thư viện đang dùng.
5. Chỉ kiểm tra scope ở route **chưa đủ** để ngăn cross-tenant và broken object-level authorization.

Đây là ví dụ minh họa; cần import những class Spring đúng phiên bản, bổ sung cấu hình method security, exception handling, CSRF/cookie nếu ứng dụng sử dụng browser session và giới hạn endpoint không được liệt kê.

### 14.3. Object-level policy dùng principal đã xác minh

~~~java
@Service
class OrderQueryService {
    private final OrdersRepository orders;

    OrderQueryService(OrdersRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)")
    public OrderView getOrder(String orderId) {
        return orders.findById(orderId)
                .map(OrderRecord::toView)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
    }
}

@Component("orderPolicy")
class OrderPolicy {
    private final OrdersRepository orders;

    OrderPolicy(OrdersRepository orders) {
        this.orders = orders;
    }

    public boolean canRead(Authentication auth, String orderId) {
        if (!(auth instanceof JwtAuthenticationToken token)) {
            return false;
        }

        String subject = token.getToken().getSubject();
        String tenant = token.getToken()
                .getClaimAsString("tenant_id");
        if (subject == null || tenant == null) {
            return false;
        }

        return orders.findById(orderId)
                .map(order ->
                        tenant.equals(order.getTenantId())
                        && order.canBeReadBy(subject))
                .orElse(false);
    }
}
~~~

`OrdersRepository`, `OrderRecord`, `OrderView`, `OrderNotFoundException` và `order.canBeReadBy` là **đối tượng thuộc domain giả định**, phải triển khai riêng. `#orderId` trong SpEL cần cấu hình Java compile giữ tên tham số hoặc dùng phương thức gắn tên phù hợp. Ví dụ chỉ minh họa **user-delegated JWT** mà `sub` tương ứng người dùng theo AS contract; không áp nó nguyên xi cho app-only token hoặc opaque token.

Nếu một API cho cả human user và service account truy cập, cần hai nhánh policy rõ ràng:

~~~text
if principal is verified USER-delegated identity:
    check user scope + user tenant + order ownership
else if principal is verified SERVICE identity and allowed for this endpoint:
    check service scope + service tenant + service-specific policy
else:
    deny
~~~

Đặc biệt, không xác định loại principal chỉ dựa vào claim do client tự gửi. Token type/identity semantics phải đến từ **token đã xác minh và profile AS**; `sub` có thể có ý nghĩa khác nhau giữa grants. Với opaque token, `Authentication` không nhất thiết là `JwtAuthenticationToken`; ứng dụng cần adapter chuyển metadata đáng tin vào một domain principal thống nhất.

### 14.4. Ứng dụng trở thành OAuth client để gọi API khác

Nếu `inventory-sync` dùng client credentials, Spring Security OAuth2 Client có thể quản lý token cho một registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
        registration:
          inventory:
            provider: company-as
            client-id: inventory-sync-prod
            client-secret: CLIENT_SECRET_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read
~~~

`CLIENT_SECRET_FROM_SECRET_MANAGER` là **placeholder**, không phải giá trị secret được dùng thật; ở production cấu hình cần được inject từ secret manager/biến môi trường được bảo vệ. Đối với private-key JWT, mTLS hay workload federation, cấu hình client authentication sẽ khác.

Một authorized-client manager minh họa:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());
    return manager;
}
~~~

Khi xin AT:

~~~java
OAuth2AuthorizeRequest authorizeRequest = OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory")
        .principal("inventory-sync-prod")
        .build();

OAuth2AuthorizedClient authorized =
        authorizedClientManager.authorize(authorizeRequest);

if (authorized == null) {
    throw new IllegalStateException("Token authorization failed");
}

String accessToken = authorized.getAccessToken().getTokenValue();
// Chỉ gửi tới inventory-api qua HTTPS;
// không log accessToken hoặc tái sử dụng tại payments-api.
~~~

Đoạn code chỉ thể hiện client credentials trong service và việc **lấy token có kiểm soát**; không tự thực hiện token exchange/OBO và không chứng minh AT có audience đúng nếu AS chưa có policy tương ứng. Khi service cần delegation **thay mặt Alice**, phải dùng luồng/profile có AS authorization rõ và xác minh cả subject/actor, không mặc định manager client credentials biến service token thành user-delegated token.

### 14.5. Một service vừa RS vừa client

Đối với `orders-api`, có thể:

~~~text
Inbound:
  Receive Alice's AT, aud=orders-api
  Verify token + user scope + domain permission

Outbound:
  Obtain a distinct AT, aud=payments-api
  Via valid token exchange / approved service grant
  Preserve delegation context if action is on behalf of Alice
  Call payments-api with this distinct token
~~~

Không viết HTTP interceptor tự động forward mọi `Authorization` header của inbound request sang downstream. Một interceptor như vậy có thể làm lộ token sang host khác hoặc biến hệ thống thành confused deputy nếu downstream không kiểm tra audience.

## 15. Bộ kiểm thử âm/dương cho delegation

Các bài test nên có AS và ít nhất hai RS giả lập (`orders-api`, `payments-api`), tạo token test từ khóa riêng. Khi thử audience, scope hay principal, **giữ các điều kiện còn lại hợp lệ** để biết chính xác validator nào đang hoạt động; một hệ thống luôn từ chối vì JWKS sai không chứng minh audience policy an toàn.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| D01 | Alice dùng token user-delegated `aud=orders-api`, `orders.read`, order đúng tenant | Đọc được order theo domain policy |
| D02 | Client xin `orders.write` nhưng chỉ được cấp `orders.read` | Client/API không tự suy ra quyền ghi |
| D03 | Scope request ngoài registration/policy | AS từ chối hoặc giới hạn grant theo hợp đồng |
| D04 | Alice consent scope nhưng không có quyền business với order tenant khác | RS từ chối object-level access |
| D05 | Token user-delegated bị dùng ở resource sai `aud` | RS từ chối dù chữ ký đúng |
| D06 | JWT có `aud=payments-api` nhưng claim `scope=orders.read` | `orders-api` từ chối |
| D07 | JWT thiếu `aud` khi access-token profile yêu cầu | RS từ chối |
| D08 | JWT `aud=["orders-api","payments-api"]` | Chỉ chấp nhận khi RS/AS cho phép multi-audience rõ ràng |
| D09 | Token `iss` là AS không được tin cậy | RS từ chối |
| D10 | Token đúng issuer nhưng chữ ký sai | RS từ chối |
| D11 | Token hết `exp` ngoài clock skew | RS từ chối |
| D12 | Client gửi ID token OIDC đến orders API | RS từ chối do sai token purpose/audience |
| D13 | Client gửi refresh token tới resource API | RS từ chối |
| D14 | Client gửi `X-Role: ADMIN` nhưng token không có quyền tương ứng | RS không cấp quyền dựa trên header |
| D15 | Machine token có `sub=inventory-sync-prod` bị ép thành human Alice | Chính sách loại grant/principal từ chối user-only action |
| D16 | User token của Alice bị dùng như quyền riêng của service admin | RS/domain policy từ chối việc nâng quyền |
| D17 | Service token app-only `aud=inventory-api`, `scope=inventory.read` | Được phép tác vụ machine phù hợp |
| D18 | Machine token dành cho inventory dùng gọi payments | Payments từ chối vì audience |
| D19 | Token exchange với client/actor đủ quyền và resource hợp lệ | AS có thể cấp token mới đúng aud/scope |
| D20 | Token exchange cố xin `payments.admin` ngoài delegation | AS từ chối theo policy |
| D21 | `orders-api` forward token `aud=orders-api` sang payments | Payments từ chối do sai aud |
| D22 | Token exchange trả `act` giả mạo từ token không được verify | RS từ chối hoặc bỏ claim chưa tin |
| D23 | Delegated AT có `sub=alice`, actor=orchestrator và scope đúng | Phân quyền/audit subject và actor theo contract |
| D24 | Opaque token introspection trả `active=false` | RS từ chối |
| D25 | Opaque token `active=true` nhưng không chứng minh đúng resource | RS từ chối hoặc yêu cầu AS contract bảo đảm resource binding |
| D26 | Introspection/JWKS TLS thất bại không có kết quả tin cậy | Fail closed, không cấp quyền |
| D27 | User mất quyền order trong lúc JWT còn hạn | Domain policy hoặc revocation đáp ứng SLA thu hồi |
| D28 | Logout/revoke RT nhưng JWT AT cũ còn hạn | RS tuân theo TTL/revocation policy đã công bố |
| D29 | Hai browser tab refresh RT rotation đồng thời | Client single-flight; AS xử lý reuse theo policy |
| D30 | Access token DPoP/mTLS-bound bị dùng với khóa/cert sai | RS từ chối dù scope và aud đúng |
| D31 | Token cache theo client ID nhưng trộn Alice và Bob | Kiểm thử phát hiện/cấm trả token sai principal |
| D32 | Token cache dùng lại `aud=orders-api` cho `payments-api` | Client/RS từ chối; cache phải phân vùng theo resource |
| D33 | Alice gọi hủy thanh toán, service dùng service token admin nhưng Alice không có quyền | Domain policy chặn confused deputy |
| D34 | Client bị chặn tại AS nhưng user đã consent trước | AS không cấp token mới vượt policy |
| D35 | User consent `orders.read` và muốn thêm `orders.write` | Yêu cầu authorization/grant mới hợp lệ, không tự tăng scope bằng RT |
| D36 | Token đúng mọi claims nhưng bản ghi thuộc tenant khác | RS từ chối với ACL/tenant policy |

### 15.1. Test “role confusion” có kiểm soát

Tạo hai token test có các trường giống nhau về issuer/exp/audience:

~~~json
{
  "user_delegated": {
    "sub": "alice",
    "client_id": "sales-dashboard",
    "aud": ["orders-api"],
    "scope": "orders.read"
  },
  "client_credentials": {
    "sub": "inventory-sync-prod",
    "client_id": "inventory-sync-prod",
    "aud": ["orders-api"],
    "scope": "orders.read"
  }
}
~~~

Hai JSON object chỉ là **claims minh họa**, không phải JWT hợp lệ. Khi tạo token test, phải ký bằng khóa test được RS tin và dùng token profile phân biệt loại principal/authorized client. Nếu endpoint được thiết kế **chỉ cho user-delegated token**, request của machine client phải bị từ chối theo policy ngay cả khi scope trùng. Ngược lại, endpoint dành cho machine identity không nên yêu cầu một user session giả.

Không suy đoán loại token chỉ bằng chuỗi `sub` giống email người dùng. Dùng thông tin grant/principal/actor đã được AS xác minh và hợp đồng xác định rõ, thay vì heuristic như `sub.contains("@")`.

### 15.2. Test delegation nhiều hop

Lập một luồng:

~~~text
Alice → orders-api (AT1, aud=orders-api)
orders-api → AS token exchange (AT1, subject/actor theo contract)
AS → orders-api (AT2, aud=payments-api)
orders-api → payments-api (AT2)
~~~

Kiểm thử tối thiểu:

1. AT1 chỉ được `orders-api` chấp nhận, `payments-api` từ chối.
2. AT2 có audience payments và scope được cấp thực sự, không phải toàn bộ scope client tự xin.
3. AS kiểm tra quyền actor thực hiện exchange và ràng buộc delegated subject/resource.
4. `payments-api` đối chiếu quyền trên khoản thanh toán cụ thể, không chỉ đọc `act` rồi cho phép.
5. Audit tách **subject**, **actor**, **client**, resource và action; không ghi raw AT1/AT2.
6. Đường lỗi token exchange timeout hoặc `invalid_grant` **không fallback** sang service admin token trái policy.

### 15.3. Đo lường kết quả thay vì chỉ HTTP status

Một phản hồi `403` là cần nhưng chưa đủ. Cần chứng minh request trái quyền **không kích hoạt side effects**, ví dụ không ghi giao dịch, không gọi backend bằng credential đặc quyền, không tạo audit “success” giả và không đưa token/claims nhạy cảm vào log. Với request đọc, kiểm tra response không tiết lộ metadata tồn tại của object tenant khác nếu policy muốn che giấu bằng 404.

## 16. Ba tình huống thực tế

### Tình huống A: Người dùng đồng ý nhưng resource server trả dữ liệu tenant khác

Alice consent để `sales-dashboard` có scope `orders.read`. Token do AS ký có `sub=alice`, `aud=orders-api` và `scope=orders.read`. Alice sửa URL từ `/orders/123` sang `/orders/999`, nơi order 999 thuộc tenant khác. API chỉ kiểm tra token + scope và trả order.

**Nguyên nhân:** Delegation theo scope bị nhầm với quyền trên mọi object; thiếu kiểm tra tenant/ownership ở RS (*broken object-level authorization*).

**Giải pháp:** AS cấp scope tối thiểu và audience đúng; RS tra dữ liệu order đáng tin, kiểm tra tenant/owner/role/ACL trước khi đọc hoặc ghi. Không lấy order tenant từ header do client tự khai để quyết định quyền.

### Tình huống B: Service quyền cao trở thành confused deputy

Alice có quyền đọc đơn hàng nhưng không được hoàn tiền. `orders-api` sở hữu service credential `payments.refund` cho tác vụ vận hành. Endpoint `POST /orders/123/refund` chỉ kiểm tra Alice đã đăng nhập; sau đó dùng service token để gọi payments hoàn tiền.

**Nguyên nhân:** Quyền của **service** được dùng thay cho **quyền delegation của Alice** mà không có chính sách cho phép hành động này.

**Giải pháp:** Domain policy xác minh Alice thực sự được hoàn tiền đối với order 123; nếu payments cần biết chủ thể/actor thì dùng OBO/token exchange được AS hỗ trợ, cấp đúng audience/scope và audit. Nếu thao tác vận hành hệ thống cần service credential, phải tách endpoint/caller policy rõ và không cho user tùy ý kích hoạt.

### Tình huống C: Frontend gửi ID token làm “access token”

Sau login OIDC, client nhận ID token có `aud=sales-dashboard` và access token `aud=orders-api`. Do bug ở frontend, nó gửi ID token qua `Authorization: Bearer` tới `orders-api`. API chỉ verify chữ ký cùng issuer và đọc `sub=alice`, nên chấp nhận.

**Nguyên nhân:** Nhầm OIDC authentication assertion cho client với OAuth authorization credential dành cho API (**token type/audience confusion**).

**Giải pháp:** RS chỉ nhận access token theo profile đã quy định, yêu cầu expected audience `orders-api`, expiry, scope và domain permission; từ chối ID token có audience của client. Client không sử dụng ID token để gọi RS. Đây là lý do phải hiểu **role client khác role RS**, dù cả hai đều thấy một JWT do cùng AS ký.

## 17. Checklist thiết kế delegation và câu hỏi tự kiểm tra

### 17.1. Checklist trước production

1. **Roles rõ ràng:** Xác định RO, client, AS và RS cho từng flow; service có vừa làm RS vừa OAuth client không?
2. **Kiểu quyền:** Phân biệt user-delegated access, app-only service identity và actor/subject của token exchange.
3. **Client registration:** Grant types, redirect URIs, client authentication, scopes và resource allowlist có được quản trị?
4. **Grant và consent:** AS đã kiểm tra quyền RO/admin, consent khi cần và policy trước khi cấp token?
5. **Audience:** Mỗi RS có expected `aud` riêng; client/token exchange xin token đúng resource?
6. **Scope:** Scope được cấp thực sự là gì; API có kiểm tra exact scope và không dùng scope như object ACL?
7. **Token type:** API từ chối ID token/refresh token/client assertion; JWT/opaque được validate theo profile đáng tin?
8. **Subject/actor:** Domain có hiểu rõ `sub`/`client_id`/`act` theo grant/profile, không suy diễn human từ service token?
9. **Multi-hop:** Không forward bearer token sai audience; OBO/exchange có policy chống nâng quyền và audit đầy đủ?
10. **Domain authorization:** Tenant, owner, role/ACL, trạng thái tài nguyên và actor permissions được kiểm tra tại RS?
11. **Lifecycle:** TTL, refresh rotation, logout, revocation và tác động lên AT còn hạn được xác định rõ?
12. **Transport/security:** TLS/certificate validation, token storage/log redaction, DPoP/mTLS khi thích hợp và giới hạn replay?
13. **Incident/audit:** Logs ghi client/subject/actor/resource/action an toàn, theo dõi scope escalation và confused deputy?
14. **Tests:** Có kiểm thử user vs machine, cross-tenant, cross-audience, ID token misuse, multi-hop exchange và race/revocation?

### 17.2. Câu hỏi tự kiểm tra

**Câu 1.** Alice consent `orders.read` cho dashboard. Dashboard có thể đọc mọi đơn hàng của công ty không?

**Trả lời:** Không. Consent là một phần của quá trình cấp quyền cho client, còn `orders-api` phải kiểm tra quyền của Alice đối với từng order và tenant.

**Câu 2.** Trong `client_credentials`, access token có thể đại diện cho một end-user Alice không?

**Trả lời:** Không mặc định. Grant này sử dụng quyền của **client/service**, không có Alice tham gia như resource owner trong request. Nếu nghiệp vụ cần hành động thay Alice, phải có cơ chế delegation riêng được AS/RS hỗ trợ và xác minh.

**Câu 3.** `orders-api` có thể chuyển tiếp token `aud=orders-api` sang `payments-api` vì cả hai cùng tin issuer không?

**Trả lời:** Không. `payments-api` phải xác minh audience của chính mình. Khi cần delegation giữa API, sử dụng token exchange/OBO hoặc một service-grant thiết kế đúng, không forward tùy tiện token sai resource.

**Câu 4.** Access token có `scope=payments.create` đã đủ cho service thực hiện mọi thanh toán chưa?

**Trả lời:** Chưa. RS còn kiểm tra issuer, audience, token profile, principal/actor, tenant, quy tắc đối tượng và điều kiện nghiệp vụ.

**Câu 5.** JWT ký đúng nhưng `aud=sales-dashboard` có thể là ID token gửi cho client. RS được nhận làm access token không?

**Trả lời:** Không. RS phải kiểm tra đúng loại access token và audience của resource mình; không dùng ID token OIDC làm credential truy cập API.

**Câu 6.** Nếu một service dùng client credentials để gọi payments thay Alice, điều gì có thể sai?

**Trả lời:** Service có thể sử dụng quyền mạnh của mình để thực hiện hành động Alice không được phép (*confused deputy*). Cần kiểm tra user/domain authorization ở ranh giới phù hợp và/hoặc dùng token exchange giữ subject/actor.

**Câu 7.** Client có thể tự mở rộng scope bằng refresh token sau khi user rời khỏi ứng dụng không?

**Trả lời:** Không. Refresh không được mở rộng quyền ra ngoài grant ban đầu; xin quyền mới phải đi qua cơ chế authorization/policy hợp lệ.

**Câu 8.** mTLS hoặc DPoP-bound token có còn cần audience validation không?

**Trả lời:** Có. Proof sở hữu khóa không chứng minh token được cấp cho API đang nhận request; kiểm tra audience và quyền vẫn độc lập.

**Câu 9.** `sub` và `client_id` có luôn giống nhau không?

**Trả lời:** Không. Trong user-delegated access, `sub` thường là user còn `client_id` là ứng dụng được cấp token. Trong app-only, token profile có thể biểu diễn service principal khác; AS contract quyết định cách hiểu chính xác.

**Câu 10.** Thu hồi consent tại AS có chặn ngay mọi JWT access token đã cấp không?

**Trả lời:** Không tự động. JWT xác minh offline có thể còn hợp lệ đến `exp` nếu RS không kiểm tra trạng thái/denylist hoặc domain policy thời gian thực.

## 18. Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): bốn OAuth roles, authorization grants, scope và token endpoint.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc authorization code với client transaction.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền access token tới RS và lỗi `invalid_token`/`insufficient_scope`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): chỉ định resource/audience khi xin token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token cho downstream resource, subject token và actor context.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token claims như `iss`, `aud`, `client_id`, `scope`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims `sub`, `iss`, `aud`, `exp` và `jti`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token validation và `active`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi access/refresh token theo policy AS.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token replay, refresh rotation, bảo vệ OAuth và sender constraint.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): giảm token type/algorithm/key confusion.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và end-user authentication ở OIDC.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bảo vệ API bằng bearer access token.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): đăng ký client và quản lý authorized client tokens.

**Điểm cần ghi nhớ:** OAuth delegation **không phải** “client có token là được làm mọi thứ”. **Resource owner** là nguồn quyền trong những luồng delegation phù hợp; **client** yêu cầu quyền, **authorization server** kiểm tra grant/consent/policy rồi cấp token, và **resource server** xác minh token **dành cho chính mình** trước khi thực thi scope cùng quyền nghiệp vụ. Phải phân biệt **user-delegated token**, **app-only service token**, **subject/actor qua token exchange**, và không dùng ID token hay token sai audience để gọi API. Ranh giới rõ giữa client–AS–RS cùng TTL, revocation, TLS, least privilege và object-level authorization là cách tránh token confusion, privilege escalation và confused deputy.
