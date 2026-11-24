# Token exchange giữa các microservices

> **Chương:** Token exchange  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Mô hình tin cậy và vòng đời token bảo mật; JWT, opaque token, access token, refresh token; phát hành, kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **OAuth 2.0 Token Exchange** và lý do một microservice cần đổi token khi gọi service tiếp theo.
2. Phân biệt **subject token**, **actor token**, **requested token type** và token được Authorization Server phát hành.
3. Mô tả sự khác nhau giữa **delegation** (ủy quyền thay mặt chủ thể) và **impersonation** (mạo danh theo chính sách được cho phép).
4. Thiết kế token có **audience/resource** và **scope** phù hợp với service đích, tránh chuyển tiếp một bearer token có quyền quá rộng.
5. Xây dựng chuỗi gọi nhiều microservices, xác thực client, kiểm tra token và áp dụng authorization ở từng service.
6. Nhận diện rủi ro token substitution, confused deputy, token replay, trust federation và cache token exchange sai ngữ cảnh.

## 1. Token exchange là gì?

**Token exchange** là quy trình một client gửi một token hiện có đến Authorization Server để yêu cầu một token khác phù hợp với ngữ cảnh sử dụng tiếp theo. Trong OAuth 2.0, cơ chế tiêu chuẩn hóa tại **RFC 8693 — OAuth 2.0 Token Exchange** định nghĩa một grant type mở rộng cho phép client yêu cầu đổi token, ví dụ đổi access token của người dùng thành access token có audience và quyền phù hợp với một API nội bộ.

Hãy xem luồng sau:

- Người dùng đăng nhập vào ứng dụng và nhận access token dành cho **Orders API**.
- **Orders Service** xử lý yêu cầu, cần gọi **Inventory Service** để kiểm tra tồn kho.
- Access token ban đầu chỉ dành cho Orders API. Orders Service không nên mặc định chuyển nguyên bearer token đó sang Inventory API.
- Orders Service gửi token hiện tại đến Authorization Server, xác thực chính nó và yêu cầu token mới dành riêng cho Inventory API, với scope cần thiết.
- Authorization Server kiểm tra chủ thể, caller, chính sách ủy quyền và phát hành token mới nếu hợp lệ.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User / Client
    participant O as Orders Service
    participant AS as Authorization Server
    participant I as Inventory Service

    U->>O: Request + access token dành cho Orders API
    Note over O: Xác minh token đầu vào<br/>và quyền truy cập đơn hàng
    O->>AS: Token exchange: subject token + client authentication<br/>audience=inventory-api, scope=inventory.read
    AS->>AS: Kiểm tra token, caller và policy
    AS-->>O: Access token mới dành cho Inventory API
    O->>I: Request + token mới
    I->>I: Kiểm tra issuer, audience, scope, expiry
    I-->>O: Kết quả tồn kho
    O-->>U: Response
~~~

Token mới thể hiện một quyền truy cập được Authorization Server cấp theo chính sách. Nó có thể giữ nguyên chủ thể người dùng, thể hiện thêm service đang hành động thay mặt người dùng, thu hẹp scope và giới hạn audience vào đúng resource server.

**Token exchange không phải thao tác đổi chuỗi token tại client.** Đây là một quyết định bảo mật của Authorization Server: xác minh token đầu vào, xác thực client yêu cầu đổi, đánh giá quyền và phát hành credential mới.

## 2. Các thành phần của Token Exchange

RFC 8693 định nghĩa những tham số quan trọng sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **subject_token** | Token đại diện cho chủ thể mà quyền truy cập gắn với | Access token của user-123 |
| **subject_token_type** | Loại token của subject_token | urn:ietf:params:oauth:token-type:access_token |
| **actor_token** | Token đại diện cho actor đang hành động thay mặt subject, nếu có | Token của orders-service |
| **actor_token_type** | Loại token của actor token | urn:ietf:params:oauth:token-type:access_token |
| **grant_type** | Grant type dùng cho token exchange | urn:ietf:params:oauth:grant-type:token-exchange |
| **requested_token_type** | Loại token client mong muốn được phát hành | urn:ietf:params:oauth:token-type:access_token |
| **audience** | Định danh resource server dự kiến nhận token | inventory-api |
| **resource** | URI định danh tài nguyên đích theo Resource Indicators | https://inventory.internal.example/ |
| **scope** | Quyền client yêu cầu cho token mới | inventory.read |

Các định danh token type là URI có ý nghĩa giao thức, không phải URL cần truy cập bằng trình duyệt. RFC 8693 định nghĩa các token type phổ biến như access token, refresh token, ID token, JWT và SAML assertion. Khả năng nhận từng loại token phụ thuộc Authorization Server và policy của hệ thống.

### Subject và actor

- **Subject** là chủ thể mà quyền đang được đại diện, ví dụ người dùng đã đăng nhập.
- **Actor** là client/service thực hiện hành động thay mặt subject, ví dụ Orders Service gọi Inventory Service.
- **Issued token** là token mới do Authorization Server phát hành cho ngữ cảnh đích.

Trong JWT, claim **sub** thường biểu diễn subject. Claim **act** có thể biểu diễn actor hiện tại. Cấu trúc claim và cách ánh xạ danh tính cần được Authorization Server cùng resource server thống nhất. Không tự suy ra actor chỉ từ tên client gửi trong HTTP header.

Ví dụ minh họa claims của token được phát hành:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": "inventory-api",
  "scope": "inventory.read",
  "act": {
    "sub": "orders-service"
  },
  "exp": 1893456000,
  "jti": "issued-token-id"
}
~~~

Đây là payload minh họa, không phải token có thể sử dụng. JWT thực tế phải có chữ ký hợp lệ; resource server còn phải kiểm tra issuer, audience, thời gian, thuật toán, scope và các policy khác.

## 3. Delegation và impersonation

Hai khái niệm này có ảnh hưởng trực tiếp đến cách service diễn giải token được đổi.

### Delegation — ủy quyền thay mặt subject

Trong delegation, người dùng vẫn là **subject**, còn service là **actor** thực hiện một hành động được ủy quyền. Ví dụ:

- Alice yêu cầu Orders Service xem thông tin đơn hàng.
- Orders Service cần gọi Inventory Service để đọc trạng thái tồn kho.
- Token mới biểu diễn Alice là subject, Orders Service là actor và chỉ cấp inventory.read.

Inventory Service có thể ghi nhận cả người dùng và service gọi API để audit.

### Impersonation — mạo danh theo policy

Trong impersonation, một client được phép hành động dưới danh tính của một chủ thể khác theo chính sách rõ ràng của Authorization Server. Đây là quyền nhạy cảm, có thể làm mất khả năng phân biệt actor nếu hệ thống không lưu dấu vết phù hợp.

Không được coi impersonation là hành vi mặc định của mọi token exchange. Chỉ cấp khi có nhu cầu nghiệp vụ rõ ràng, giới hạn actor, subject, audience, scope và thời hạn. Audit phải giữ được thông tin ai đã thực hiện hành động và hành động thay mặt ai.

| Tiêu chí | Delegation | Impersonation |
|---|---|---|
| Chủ thể | Subject vẫn được thể hiện | Caller có thể được biểu diễn như subject theo semantics của hệ thống |
| Actor | Có thể thể hiện rõ bằng act | Cần audit rõ danh tính caller ban đầu dù API downstream có thể thấy danh tính được impersonate |
| Quyền | Quyền được ủy quyền, thường giới hạn theo subject và actor | Quyền mạo danh cần policy đặc biệt và kiểm soát chặt |
| Rủi ro | Service lạm dụng quyền được ủy quyền | Che khuất danh tính actor, leo thang quyền hoặc giả danh người dùng |
| Kiểm soát | Giới hạn actor, resource, scope, thời hạn | Allowlist actor/subject, audit bất biến, phê duyệt và policy riêng |

Tên gọi và semantics cụ thể phải được định nghĩa nhất quán giữa Authorization Server và các API. Không nên chỉ nhìn thấy claim sub rồi kết luận token đang dùng delegation hay impersonation; cần hiểu contract phát hành token.

## 4. Vì sao microservices cần token exchange?

Giả sử kiến trúc có các thành phần:

~~~mermaid
flowchart LR
    C["Web / Mobile Client"] --> G["API Gateway"]
    G --> O["Orders Service"]
    O --> I["Inventory Service"]
    O --> P["Payment Service"]
    I --> W["Warehouse Service"]
    AS["Authorization Server"] -.-> G
    AS -.-> O
    AS -.-> I
    AS -.-> P
    AS -.-> W
~~~

Nếu token của client được cấp cho Gateway hoặc Orders API nhưng bị chuyển nguyên qua tất cả service, sẽ xuất hiện các vấn đề:

1. **Audience không phù hợp:** Inventory Service nhận token vốn chỉ dành cho Orders API. Token có audience không khớp phải bị từ chối.
2. **Quyền quá rộng:** Token ban đầu có orders.read, orders.write, payments.initiate; Inventory Service chỉ cần inventory.read.
3. **Khó truy vết actor:** Log ở downstream không phân biệt được user nào yêu cầu và service nào thực sự gọi.
4. **Khó cô lập sự cố:** Token bị lộ tại một service có thể bị dùng ở nhiều resource nếu audience/scope quá rộng.
5. **Ranh giới tin cậy không rõ:** Service downstream có thể vô tình chấp nhận token do một issuer hoặc client không được phép phát hành.

Token exchange cho phép phát hành token mới theo **đích sử dụng** và **ngữ cảnh gọi**. Đây là một công cụ xây dựng quyền tối thiểu, không phải lý do để bỏ xác thực client hoặc authorization ở service đích.

### Khi nào không cần exchange?

Không nhất thiết phải đổi token cho mọi lần gọi. Nếu kiến trúc sử dụng access token có audience và scope đã được thiết kế cho đúng resource, hoặc service-to-service dùng client credential riêng phù hợp với nghiệp vụ, có thể không cần exchange.

Quyết định phụ thuộc vào việc downstream cần giữ ngữ cảnh người dùng hay chỉ cần danh tính workload. Hãy chọn cách đơn giản nhất vẫn giữ được ranh giới tin cậy và quyền tối thiểu.

## 5. Quy trình token exchange theo RFC 8693

Một flow điển hình gồm:

1. Client (ví dụ Orders Service) đã xác thực với Authorization Server bằng cơ chế được đăng ký, chẳng hạn client_secret_basic, private_key_jwt hoặc mTLS.
2. Client gửi subject_token và subject_token_type; có thể gửi actor_token và actor_token_type nếu policy cần actor token riêng.
3. Client yêu cầu token type, audience/resource và scope cần cho downstream.
4. Authorization Server xác minh token đầu vào: chữ ký hoặc introspection, issuer, thời hạn, audience và trạng thái.
5. Authorization Server xác minh client, quan hệ tin cậy giữa issuer và client, quyền exchange, actor/subject và policy của resource đích.
6. Authorization Server phát hành token mới hoặc từ chối yêu cầu.
7. Client gọi API đích bằng token mới; API đích tự xác minh token và phân quyền.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders Service
    participant AS as Authorization Server
    participant I as Inventory API

    O->>AS: POST /token<br/>grant_type=token-exchange<br/>subject_token + subject_token_type<br/>audience + scope
    Note over O,AS: Client authentication qua TLS<br/>và phương thức đã đăng ký
    AS->>AS: Validate subject token
    AS->>AS: Authenticate client + evaluate exchange policy
    alt Policy cho phép
        AS-->>O: access_token mới + issued_token_type + expires_in
        O->>I: GET /inventory/items/42<br/>Authorization: Bearer exchanged token
        I->>I: Validate token + audience + scope
        I-->>O: Inventory response
    else Không được phép
        AS-->>O: OAuth error
    end
~~~

### Token đầu vào phải được xác minh

Nếu subject_token là JWT:

- Chỉ chấp nhận issuer đã tin cậy; xác minh chữ ký bằng key được gắn với issuer đó.
- Kiểm tra iss, aud, exp, nbf (nếu có), thuật toán cho phép và các yêu cầu riêng của access token.
- Kiểm tra token đúng loại và mục đích; không coi ID token OIDC là access token gọi API.
- Kiểm tra scope, subject, tenant, trạng thái và policy được phép exchange.
- Nếu token có act hoặc may_act, xử lý theo semantics và policy đã thống nhất.

Nếu subject_token là opaque token, Authorization Server cần cơ chế xác minh trạng thái/metadata đáng tin cậy, ví dụ introspection nội bộ. Không giải mã một chuỗi opaque rồi tự suy đoán claims.

**Không được bỏ qua audience của token đầu vào chỉ vì đang đổi token.** Authorization Server phải xác minh token thực sự được phép dùng trong ngữ cảnh exchange và client hiện tại có quyền thực hiện việc đổi đó.

## 6. Ví dụ HTTP request và response

Token exchange sử dụng token endpoint được Authorization Server công bố. Request body là form URL-encoded. Client authentication được thực hiện theo cấu hình OAuth client, ví dụ HTTP Basic, mTLS hoặc private_key_jwt; không tự ý đưa client secret vào body nếu phương thức đăng ký không yêu cầu.

### 6.1. Request cơ bản

Ví dụ Orders Service đổi access token đầu vào thành token dành cho Inventory API:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.internal.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<incoming-user-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=inventory-api
&scope=inventory.read
~~~

Trong ví dụ này:

- subject_token là access token hiện có, đại diện cho subject.
- audience=inventory-api yêu cầu token mới dành cho Inventory API.
- scope=inventory.read giới hạn quyền cần thiết.
- Authorization: Basic ... chỉ minh họa client authentication; cần dùng đúng phương thức được đăng ký và bảo vệ kết nối TLS.
- requested_token_type nêu loại token mong muốn. Authorization Server có quyền từ chối loại không hỗ trợ.

### 6.2. Request có actor token

Nếu policy yêu cầu chứng minh actor riêng, request có thể có thêm:

~~~text
actor_token=<orders-service-actor-token>
actor_token_type=urn:ietf:params:oauth:token-type:access_token
~~~

Actor token phải được xác minh và ràng buộc với client đang gọi. Không cho phép client tùy ý khai tên service trong body rồi coi đó là danh tính actor. Danh tính client phải được chứng minh bằng client authentication và/hoặc token actor được tin cậy.

### 6.3. Response minh họa

~~~json
{
  "access_token": "<new-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Client phải dùng issued_token_type, token_type, expires_in và scope theo hợp đồng của Authorization Server. Không giả định token mới luôn là JWT; nó có thể là opaque token. Nếu là opaque token, Inventory API có thể cần introspection để kiểm tra metadata.

### 6.4. Gọi Inventory API

~~~http
GET /inventory/items/42 HTTP/1.1
Host: inventory.internal.example
Authorization: Bearer <new-access-token>
~~~

Inventory API xác minh token mới theo policy riêng, bao gồm issuer, audience, thời hạn, scope, trạng thái và quyền truy cập item 42. Không dựa vào việc Orders Service đã đổi token thành công để bỏ qua authorization tại Inventory API.

## 7. Audience, resource và scope: giới hạn token cho đúng đích

### Audience

**audience (aud)** cho biết token được dự định gửi đến resource server nào. Token có aud=orders-api không nên được Inventory API chấp nhận chỉ vì cả hai cùng nằm trong mạng nội bộ.

Khi exchange, client có thể yêu cầu audience hoặc resource tùy Authorization Server và profile triển khai. Hệ thống phải ánh xạ chúng đến resource server đã đăng ký, không phát token cho URI tùy ý do caller tự cung cấp.

**Resource Indicators for OAuth 2.0 (RFC 8707)** định nghĩa tham số resource để chỉ định tài nguyên đích. Đây là khái niệm có liên quan nhưng không nên tự coi resource và audience luôn là hai trường đồng nhất; cần theo đúng profile của Authorization Server.

### Scope

**scope** mô tả quyền được cấp, ví dụ:

- inventory.read: đọc tồn kho.
- inventory.reserve: giữ hàng.
- payments.create: tạo yêu cầu thanh toán.
- orders.cancel: hủy đơn hàng.

Client yêu cầu scope không có nghĩa Authorization Server phải cấp scope đó. Server có thể cấp ít hơn, từ chối hoặc yêu cầu điều kiện bổ sung.

Một nguyên tắc tốt là **downscoping**: token mới có quyền hẹp hơn token đầu vào. Ví dụ token đầu vào có orders.read orders.write inventory.read payments.create, nhưng Orders Service chỉ yêu cầu inventory.read cho Inventory API.

~~~mermaid
flowchart TD
    A["Token đầu vào<br/>aud=orders-api<br/>scope=orders.read orders.write<br/>inventory.read payments.create"] --> E["Token Exchange Policy"]
    E --> B["Token đầu ra<br/>aud=inventory-api<br/>scope=inventory.read"]
    B --> I["Inventory API<br/>chỉ chấp nhận inventory.read"]
~~~

Không nên cấp quyền mới vượt quá quyền subject được phép ủy quyền hoặc quyền actor được phép thực hiện. Policy có thể kết hợp quyền subject, quyền actor, client registration, resource, tenant, loại thao tác và trạng thái phiên.

## 8. Phân biệt token exchange với các cơ chế gần giống

| Cơ chế | Mục đích | Token/credential sau xử lý |
|---|---|---|
| **Token forwarding** | Chuyển tiếp token hiện tại sang service khác | Vẫn cùng token; audience và scope không đổi |
| **Token exchange (RFC 8693)** | Đổi token hiện tại lấy token mới theo subject/actor/resource/policy | Token mới do Authorization Server phát hành |
| **Client Credentials Grant** | Service xác thực chính nó để xin token | Token thường đại diện client/service, không mặc định có user subject |
| **Refresh token grant** | Dùng refresh token xin access token mới | Access token mới trong cùng authorization grant theo policy |
| **Token introspection (RFC 7662)** | Hỏi trạng thái và metadata của token | Không phát hành token mới |
| **OIDC ID token** | Truyền thông tin xác thực đăng nhập cho OIDC client | Không phải access token dành cho resource API |
| **mTLS / workload identity** | Xác thực peer hoặc workload ở tầng kết nối | Không tự phát hành access token hay xác định quyền API |

### Token forwarding

Forwarding đơn giản có thể phù hợp khi token được cấp ngay từ đầu cho downstream resource hoặc có audience chung theo thiết kế rõ ràng. Tuy nhiên, forwarding token sai audience là lỗi bảo mật và dễ tạo quyền quá rộng.

### Client credentials

Nếu Orders Service chỉ cần đọc dữ liệu tồn kho với tư cách chính nó, không cần giữ ngữ cảnh người dùng, có thể dùng client credentials để lấy token của orders-service dành cho inventory-api. Nếu nghiệp vụ cần biết thao tác đang thực hiện thay mặt Alice, token exchange có thể biểu diễn subject Alice cùng actor Orders Service theo policy.

### Refresh token

Refresh token dùng tại token endpoint để xin access token mới theo grant ban đầu. Token exchange dùng một token hiện có làm đầu vào cho việc phát hành token trong một ngữ cảnh subject/actor/resource khác. Hai grant type không thay thế nhau.

## 9. Token exchange trong chuỗi nhiều microservices

Giả sử:

API Gateway → Orders Service → Inventory Service → Warehouse Service

Mỗi lần gọi tiếp theo cần xác định rõ subject, actor, audience và scope.

~~~mermaid
flowchart LR
    U["User Alice"] --> G["API Gateway"]
    G -->|"Token A<br/>aud=orders-api"| O["Orders Service"]
    O -->|"Exchange A → B<br/>aud=inventory-api"| I["Inventory Service"]
    I -->|"Exchange B → C<br/>aud=warehouse-api"| W["Warehouse Service"]
    AS["Authorization Server"] -.-> O
    AS -.-> I
~~~

Ví dụ:

| Hop | Subject | Actor | Audience | Scope |
|---|---|---|---|---|
| Gateway → Orders | Alice | Gateway hoặc client theo policy | orders-api | orders.read |
| Orders → Inventory | Alice | orders-service | inventory-api | inventory.read |
| Inventory → Warehouse | Alice | inventory-service | warehouse-api | warehouse.stock.read |

Khi mỗi service exchange token tiếp, Authorization Server phải đánh giá actor chain và policy. Token đầu ra có thể ghi nhận actor hiện tại; nếu hệ thống cần giữ lịch sử actor trước đó, phải thiết kế cách biểu diễn và audit phù hợp. Không tự giả định mọi issuer đều giữ nguyên toàn bộ chuỗi actor theo cùng một định dạng.

### Tránh confused deputy

**Confused deputy** xảy ra khi service có quyền mạnh bị lừa sử dụng quyền đó cho caller không đủ quyền. Ví dụ Orders Service có thể xin token payments.refund cho mọi đơn hàng, nhưng người dùng Alice chỉ được xem đơn của mình.

Để tránh:

- Kiểm tra subject token và quyền của subject trước khi exchange.
- Ràng buộc actor với client đã xác thực; không tin actor name do caller khai.
- Authorization Server chỉ cho Orders Service exchange sang resource/scope được cho phép.
- Giữ thông tin subject và actor để downstream kiểm tra chính sách.
- Resource server kiểm tra quyền trên đối tượng cụ thể (owner, tenant, trạng thái), không chỉ scope.
- Không cho client tự tăng scope hoặc thay audience bằng URI tùy ý.

## 10. Xác thực client và ranh giới tin cậy

Token exchange không bỏ qua **client authentication**. Authorization Server cần biết chính xác service nào đang yêu cầu đổi token. Những phương thức có thể sử dụng tùy đăng ký:

- **client_secret_basic:** client gửi client ID và secret theo HTTP Basic qua TLS; secret phải được bảo vệ và rotation đúng cách.
- **private_key_jwt:** client ký assertion bằng private key, Authorization Server xác minh public key đã đăng ký.
- **mTLS client authentication:** client chứng minh sở hữu private key của chứng chỉ được đăng ký.
- Các phương thức khác được Authorization Server hỗ trợ và policy cho phép.

Ngoài client authentication, Authorization Server còn phải kiểm tra quan hệ trust của subject_token issuer. Nếu token được phát hành bởi một IdP khác, phải có cấu hình federation và mapping issuer rõ ràng; không chấp nhận token từ issuer bất kỳ chỉ vì chữ ký hợp lệ theo một CA chung.

### Ví dụ ranh giới tin cậy

~~~mermaid
flowchart TD
    A["Orders Service<br/>client identity đã xác thực"] --> T["Token Endpoint"]
    S["Subject token<br/>issuer đã đăng ký"] --> T
    P["Exchange policy<br/>actor + subject + resource + scope"] --> T
    T -->|Cho phép| N["Token mới<br/>audience=inventory-api"]
    T -->|Từ chối| D["OAuth error"]
    N --> I["Inventory API<br/>tự xác minh token"]
~~~

Nếu token endpoint bị gọi từ service không được phép, dù subject token hợp lệ, server vẫn có thể từ chối. Nếu Orders Service có quyền exchange, nó cũng không được tự do đổi token sang mọi resource và mọi scope.

## 11. JWT và opaque token sau token exchange

Token exchange không yêu cầu token đầu ra phải là JWT. Quyết định chọn JWT hay opaque token thuộc Authorization Server và kiến trúc resource server.

| Đặc điểm | JWT access token | Opaque access token |
|---|---|---|
| Dữ liệu | Claims được mã hóa Base64URL và ký | Chuỗi tham chiếu không tự biểu diễn claims |
| Xác minh | Resource server xác minh chữ ký và claims | Resource server gọi introspection hoặc cơ chế tra cứu tin cậy |
| Thông tin actor/subject | Có thể thể hiện bằng sub, act và claims khác | Có thể trả về từ introspection |
| Thu hồi | Offline validation có thể tiếp tục chấp nhận tới exp, trừ khi có cơ chế bổ sung | Có thể kiểm tra trạng thái active, tùy cache và server |
| Cache | Cần kiểm soát key/JWKS và thời hạn token | Cần kiểm soát kết quả introspection và độ trễ revoke |
| Rủi ro | Claims sai audience hoặc key validation yếu | Introspection không an toàn, cache stale hoặc token endpoint lộ |

Với JWT, resource server phải xác minh chữ ký, issuer, audience, thời gian, thuật toán và policy. Không chỉ decode payload rồi tin sub, scope hoặc act.

Với opaque token, resource server hoặc gateway cần introspection endpoint được bảo vệ, thường xác thực resource server. Kết quả introspection có thể bao gồm active, scope, client_id, sub, aud, iss, exp và các metadata khác tùy Authorization Server.

## 12. Kiểm tra và phân quyền tại service đích

Inventory Service không được tin rằng Orders Service đã kiểm tra mọi thứ. Nó cần:

1. Xác minh token do issuer được tin cậy phát hành.
2. Xác minh aud chứa chính Inventory API hoặc identifier được định nghĩa.
3. Kiểm tra exp, nbf, thời gian hệ thống và các yêu cầu token profile.
4. Kiểm tra scope inventory.read cho thao tác đọc.
5. Đọc subject và actor theo contract đã thống nhất; xác định service caller được phép thực hiện hành động nào.
6. Kiểm tra tenant, owner, trạng thái item và các điều kiện nghiệp vụ.
7. Audit hành động với trace ID, subject, actor và resource ID; không ghi raw token.

### 401 và 403

- **401 Unauthorized:** token thiếu, sai, hết hạn, issuer/audience không hợp lệ hoặc token không được chấp nhận.
- **403 Forbidden:** token hợp lệ nhưng thiếu scope/quyền hoặc actor/subject không được phép truy cập tài nguyên.

HTTP status cụ thể phụ thuộc API policy, nhưng một request không được thành công chỉ vì service gọi nó đã thực hiện token exchange thành công.

## 13. Cache token exchange đúng cách

Token exchange có thể tạo thêm tải lên Authorization Server. Client thường cache token đầu ra trong thời gian hợp lệ, nhưng cache key phải bao gồm đủ ngữ cảnh bảo mật.

Các thành phần cache key có thể gồm:

- Client/actor identity đã xác thực.
- Subject identity và authorization context cần thiết.
- Audience/resource đích.
- Scope thực tế được cấp.
- Loại token yêu cầu.
- Tenant hoặc policy context nếu ảnh hưởng quyết định cấp quyền.
- Phiên bản credential hoặc policy khi cần invalidation.

**Không cache chỉ theo audience** nếu nhiều người dùng hoặc actor khác nhau có thể nhận token khác nhau. Nếu cache token của Alice rồi dùng cho Bob, service có thể vô tình cho Bob mượn quyền của Alice.

### TTL và invalidation

- Cache không vượt quá expires_in hoặc exp; trừ hao clock skew và thời gian gọi downstream.
- Không lưu access token trong cache công khai, shared log hoặc hệ thống không có ACL.
- Khi subject session bị revoke hoặc policy thay đổi, cần xác định cách vô hiệu cache token exchange.
- Với opaque token, cân nhắc trạng thái introspection và cache TTL.
- Khi nhận 401 do token hết hạn hoặc bị thu hồi, chỉ exchange lại theo chính sách; không retry vô hạn.
- Tránh stampede khi nhiều request đồng thời cùng exchange token; có thể dùng single-flight theo cache key.

## 14. Rủi ro bảo mật và cách phòng tránh

| Rủi ro | Mô tả | Kiểm soát |
|---|---|---|
| **Token substitution** | Dùng token không đúng loại hoặc không đúng issuer làm subject token | Kiểm tra token type, issuer, audience, chữ ký/trạng thái |
| **Audience confusion** | Token dành cho API A bị dùng ở API B | Audience riêng cho resource, kiểm tra chặt ở downstream |
| **Scope escalation** | Caller yêu cầu quyền vượt quá quyền được ủy quyền | Downscoping, policy kết hợp subject + actor + resource |
| **Confused deputy** | Service có quyền mạnh bị lừa hành động cho subject không đủ quyền | Kiểm tra subject, actor và object-level authorization |
| **Actor spoofing** | Caller tự khai orders-service trong header/body | Client authentication và actor token đáng tin |
| **Token replay** | Bearer token bị đánh cắp rồi phát lại | TLS, token TTL ngắn, sender-constrained token, mTLS/DPoP khi phù hợp |
| **Token leakage** | Token xuất hiện trong log, trace, URL hoặc exception | Redaction, secret handling, giới hạn quyền đọc |
| **Issuer confusion** | Chấp nhận token từ issuer ngoài federation | Allowlist issuer, key mapping và policy tin cậy |
| **Cache cross-user** | Token của subject này được dùng cho subject khác | Cache key bao gồm subject/actor/context |
| **Exchange endpoint abuse** | Client dùng token endpoint để xin token cho resource không liên quan | Rate limit, client allowlist, resource/scope policy, audit |
| **Overly long token lifetime** | Token exchange phát token mới có tuổi thọ quá dài | TTL ngắn, giới hạn theo token đầu vào và policy |
| **Refresh token misuse** | Dùng refresh token như subject token tùy tiện hoặc gửi tới API | Giới hạn token type và grant; refresh token chỉ dùng tại token endpoint |

### Giảm replay

Bearer token có thể được sử dụng bởi bất kỳ bên nào nắm giữ nó. Để giảm rủi ro:

- Chỉ gửi token qua TLS; không đưa vào URL hoặc query string.
- Dùng access token thời hạn ngắn và audience hẹp.
- Cân nhắc **mTLS certificate-bound access token** hoặc **DPoP** khi resource server và client hỗ trợ.
- Bảo vệ private key, certificate và token cache.
- Không ghi token vào log, trace, metric label, exception hoặc crash report.
- Dùng jti/replay detection nếu token profile và policy hỗ trợ, nhưng không mặc định claim jti tự ngăn replay.

Token exchange không tự động biến bearer token thành sender-constrained token. Nếu muốn ràng buộc token với chứng chỉ/khóa, cần cơ chế phát hành và kiểm tra binding rõ ràng.

## 15. Ví dụ lệnh kiểm thử token endpoint

Có thể dùng curl để kiểm tra flow ở môi trường phát triển. Ví dụ dưới đây dùng placeholder; không đưa token hoặc secret thật vào shell history, ticket hoặc log chia sẻ.

~~~bash
curl --fail-with-body --silent --show-error \
  --request POST "https://auth.internal.example/oauth2/token" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --user "<client-id>:<client-secret>" \
  --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  --data-urlencode "subject_token=<incoming-access-token>" \
  --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "requested_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "audience=inventory-api" \
  --data-urlencode "scope=inventory.read"
~~~

Lệnh minh họa client authentication bằng HTTP Basic thông qua --user; chỉ dùng nếu client đăng ký client_secret_basic. Trong production, ưu tiên credential injection từ secret manager và cơ chế không để lộ secret trong command history/process listing. Không dùng --insecure để bỏ qua TLS certificate verification.

### Kiểm tra negative cases

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Subject token hết hạn | Authorization Server từ chối exchange |
| Subject token sai issuer/chữ ký | Từ chối |
| Subject token audience không được phép dùng trong exchange | Từ chối theo policy |
| Client không có quyền exchange | Từ chối client |
| Actor token không hợp lệ hoặc không khớp client | Từ chối |
| Yêu cầu scope vượt quyền subject/actor | Cấp scope hẹp hơn hoặc từ chối |
| Audience không nằm trong resource allowlist | Từ chối |
| Token đầu ra gửi đến API sai audience | Resource server trả 401 |
| Token đúng audience nhưng thiếu scope | Resource server trả 403 |
| Dùng token của subject A trong request subject B | Không được dùng chéo; cache và policy phải cô lập |
| Dùng ID token làm access token khi server không hỗ trợ | Từ chối |
| Token bị replay từ client không sở hữu key/cert | Bị từ chối nếu sender-constrained policy được bật |

## 16. Ví dụ tình huống và cách phân tích

### Tình huống A — Orders Service chuyển nguyên token cho Inventory API

Token của Alice có aud=orders-api. Orders Service gửi token đó đến Inventory API. Inventory API kiểm tra audience và trả 401.

**Phân tích:** Đây là kết quả đúng. Orders Service cần exchange token với audience inventory-api nếu policy cho phép, hoặc dùng một workload token nếu không cần ngữ cảnh Alice. Không sửa Inventory API để chấp nhận mọi audience.

### Tình huống B — Orders Service đổi token với scope quá rộng

Orders Service yêu cầu inventory.read inventory.write warehouse.admin, trong khi nghiệp vụ chỉ cần đọc tồn kho. Authorization Server cấp toàn bộ scope vì policy không giới hạn.

**Phân tích:** Policy exchange đang cho phép escalation. Cần downscope, giới hạn scope theo actor/resource và quyền subject; resource server vẫn phải kiểm tra thao tác thực tế.

### Tình huống C — Inventory API không biết ai là người dùng

Orders Service đổi token chỉ đại diện cho chính nó bằng client credentials. Inventory API thấy sub=orders-service nhưng không biết Alice là subject ban đầu.

**Phân tích:** Đây có thể là thiết kế đúng nếu nghiệp vụ chỉ cần tin Orders Service. Nếu cần audit hoặc phân quyền theo Alice, cần token exchange có delegation context và contract subject/actor phù hợp. Không tự thêm X-User-Id để thay thế subject token đã xác minh.

### Tình huống D — Cache token exchange dùng nhầm giữa hai người dùng

Cache được lập theo audience + scope. Alice và Bob cùng yêu cầu inventory.read; request của Bob lấy token đã exchange cho Alice từ cache.

**Phân tích:** Cache key thiếu subject/actor context. Phải cô lập cache theo danh tính và policy context; nếu không thể xác định key an toàn, không dùng chung token giữa các subject.

### Tình huống E — Actor token bị giả mạo

Client gửi actor_token tự tạo hoặc khai orders-service trong request. Authorization Server không xác minh actor token mà vẫn cấp token mới.

**Phân tích:** Server đang tin dữ liệu tự khai. Phải xác thực client, xác minh actor token và ràng buộc actor với client registration/policy. Tên service trong header không phải bằng chứng danh tính.

## 17. Checklist thiết kế trước production

- Authorization Server có hỗ trợ RFC 8693 không? Các loại subject/actor token nào được hỗ trợ?
- Client nào được phép exchange? Phương thức client authentication có đủ mạnh không?
- Issuer của subject token có nằm trong trust configuration không?
- Token đầu vào có đúng loại, đúng audience và còn hiệu lực không?
- Subject và actor có được thể hiện nhất quán trong token đầu ra và audit không?
- Resource/audience có được giới hạn vào danh sách API đã đăng ký không?
- Scope được downscope theo quyền subject, actor và nghiệp vụ như thế nào?
- Token đầu ra là JWT hay opaque? Resource server xác minh chữ ký hoặc introspection ra sao?
- Token lifetime, revocation, cache và retry có đáp ứng yêu cầu bảo mật không?
- Có cơ chế sender-constrained token nếu cần chống replay bearer token không?
- Service downstream có tự xác minh token và kiểm tra quyền trên đối tượng không?
- Log, trace, metric và exception đã loại token/secret chưa?
- Negative tests đã bao phủ issuer sai, audience sai, scope thiếu, actor giả, token hết hạn và cache cross-user chưa?

## 18. Tổng kết

**Token exchange** cho phép một microservice dùng token hiện có làm đầu vào để yêu cầu Authorization Server phát hành token mới phù hợp với service đích và ngữ cảnh quyền. Trong OAuth 2.0, RFC 8693 chuẩn hóa grant type này với các tham số như subject_token, subject_token_type, actor_token, requested_token_type, audience và scope.

Khi thiết kế chuỗi microservices, cần phân biệt **subject** (chủ thể được đại diện) và **actor** (service thực hiện hành động), hiểu rõ delegation/impersonation, giới hạn audience/resource, downscope quyền và xác thực client. Mỗi resource server vẫn phải tự kiểm tra issuer, audience, thời hạn, scope và authorization trên tài nguyên cụ thể.

Token exchange giúp giảm việc chuyển tiếp bearer token có quyền quá rộng, nhưng chỉ an toàn khi Authorization Server thực thi policy chặt chẽ, token được bảo vệ, cache được cô lập theo subject/actor và token đầu ra được xác minh tại service đích. Một token mới chỉ có giá trị trong đúng ranh giới tin cậy và quyền mà hệ thống đã cấp.
