# Actor và subject trong OAuth 2.0 Token Exchange

## 1. Vì sao phải phân biệt subject và actor?

Trong kiến trúc service-to-service, một request có thể bắt đầu từ người dùng rồi đi qua nhiều dịch vụ trước khi đến API cuối. Ví dụ Alice yêu cầu xem tồn kho của một sản phẩm. API Gateway chuyển request đến Orders API; Orders API gọi Inventory API để lấy số lượng còn lại.

Inventory cần trả lời hai câu hỏi riêng:

- **Subject:** quyền hoặc hành động đang được thực hiện thay mặt cho ai? Trong ví dụ, đó là Alice.
- **Actor:** thành phần nào đang trực tiếp thực hiện hành động thay mặt subject? Ở hop này, đó có thể là Orders API.

Nếu chỉ truyền `sub=alice`, Inventory biết người dùng liên quan nhưng có thể không biết service nào đã gọi nó. Nếu chỉ truyền `sub=orders-service`, Inventory biết workload gọi nhưng mất thông tin người dùng mà nghiệp vụ cần để kiểm tra quyền hoặc ghi audit.

OAuth 2.0 Token Exchange (RFC 8693) cung cấp cách biểu diễn và trao đổi token để Authorization Server (AS) có thể phát hành token cho resource đích, đồng thời giữ được ngữ nghĩa **subject và actor** khi chính sách cho phép.

Bài học này tập trung vào `subject_token`, `actor_token`, claim `sub`, `act` và `may_act`; phân biệt delegation với impersonation; và cách resource server dùng các thông tin đó để ra quyết định an toàn.

## 2. Định nghĩa subject, actor và OAuth client

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Subject** | Token đang đại diện cho ai hoặc chủ thể nào? | Người dùng Alice (`user-123`) |
| **Actor** | Ai đang hành động thay mặt subject? | `orders-service` |
| **OAuth client** | Client nào đã gửi yêu cầu đến token endpoint và được AS xác thực? | `orders-service-client` |
| **Resource server** | API nào sẽ nhận và sử dụng token được cấp? | `inventory-api` |
| **Authorization Server** | Bên xác thực, áp dụng policy và phát token? | `https://auth.example.test` |

Các vai trò có thể trùng nhau về mặt triển khai nhưng không đồng nghĩa về mặt bảo mật:

- OAuth client là danh tính của ứng dụng đang gọi token endpoint. Nó được xác thực bằng client secret, `private_key_jwt`, mTLS hoặc phương thức được AS hỗ trợ.
- Actor là bên đang thực hiện hành động thay mặt subject trong ngữ cảnh delegation. Actor có thể được xác định qua `actor_token`, qua danh tính client đã xác thực hoặc nguồn khác mà AS tin cậy.
- Subject là chủ thể mà token đại diện. Subject có thể là người dùng, service account hoặc một principal khác, tùy token và chính sách.
- Resource server là bên nhận token. Nó phải kiểm tra token dành cho chính mình và kiểm tra quyền trên tài nguyên cụ thể.

Không được mặc định `client_id`, `sub` và `act.sub` luôn là cùng một giá trị. Chúng trả lời các câu hỏi khác nhau.

## 3. Mô hình delegation: người dùng và service cùng xuất hiện

Giả sử Alice đã được cấp access token để gọi Orders API. Orders cần gọi Inventory API thay mặt Alice, nhưng Inventory chỉ chấp nhận token có audience `api://inventory`.

Luồng delegation có thể diễn ra như sau:

```
sequenceDiagram
    participant U as Alice / Client
    participant G as API Gateway
    participant O as Orders API
    participant AS as Authorization Server
    participant I as Inventory API
    U->>G: Request + access token của Alice
    G->>O: Chuyển request sau khi xác thực
    O->>AS: Token Exchange: subject token + actor identity
    AS->>AS: Xác minh subject, actor và policy delegation
    AS-->>O: Token mới aud=inventory, sub=Alice, act=Orders
    O->>I: Request + access token mới
    I->>I: Xác minh issuer, aud, sub, act, scope và quyền
    I-->>O: Kết quả
    O-->>G: Response
    G-->>U: Response
```

Token mới có thể thể hiện:

- `sub=user-123`: Alice là subject.
- `act.sub=orders-service`: Orders API là actor đang thực hiện request thay mặt Alice.
- `aud=api://inventory`: token dành cho Inventory API.
- `scope=inventory:read`: quyền được AS cấp cho thao tác đọc tồn kho.

Nhờ đó Inventory có thể kiểm tra cả quyền của Alice lẫn quyền/điều kiện của Orders service. Token exchange không tự động cho Alice hoặc Orders thêm quyền; AS chỉ cấp những quyền mà policy cho phép.

## 4. Impersonation khác delegation như thế nào?

RFC 8693 phân biệt hai mô hình quan trọng:

### 4.1. Impersonation — hành động như subject

Trong impersonation, client được phép hành động như subject. Resource server nhận token có subject là Alice và thường không được thông báo actor nào đã thực hiện việc impersonation thông qua claim `act`.

Ví dụ token:

```
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "api://inventory",
  "scope": "inventory:read",
  "client_id": "orders-service-client",
  "exp": 1795000600
}
```

Token cho thấy subject là Alice và client ID có thể cho biết client đã yêu cầu token. Tuy nhiên `client_id` không tự động mang ngữ nghĩa actor delegation. Nếu API chỉ dựa vào `sub`, nó có thể không phân biệt được người dùng tự gọi API hay một service đang impersonate người dùng.

Impersonation chỉ phù hợp khi hệ thống có cơ chế cho phép rõ ràng, giới hạn đối tượng được impersonate, scope, audience, thời hạn và audit. Không cho service tự gửi `sub=admin` rồi xem đó là bằng chứng quyền admin.

### 4.2. Delegation — actor hành động thay mặt subject

Trong delegation, token thể hiện subject và actor riêng biệt. Resource server biết ai là chủ thể được đại diện và ai là bên đang thực hiện hành động.

Ví dụ:

```
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "act": {
    "sub": "orders-service"
  },
  "aud": "api://inventory",
  "scope": "inventory:read",
  "client_id": "orders-service-client",
  "exp": 1795000600
}
```

Ở đây:

- `sub` xác định Alice.
- `act.sub` xác định Orders service là actor.
- `client_id` xác định OAuth client đã yêu cầu token; nó có thể trùng với actor trong ví dụ, nhưng không nên gộp hai khái niệm.
- `aud` xác định Inventory API là resource được phép nhận token.

Delegation hữu ích khi resource server cần policy kiểu: Alice có quyền đọc sản phẩm này, nhưng chỉ các workload được phê duyệt mới được gọi Inventory thay mặt Alice.

### 4.3. Bảng so sánh

| Tiêu chí | Impersonation | Delegation |
| --- | --- | --- |
| Subject trong token | Chủ thể được impersonate | Chủ thể được đại diện |
| Actor có được biểu diễn rõ? | Thường không qua claim `act` | Có thể được biểu diễn bằng claim `act` |
| Resource server phân biệt ai thực thi | Khó hơn nếu chỉ có subject | Có thể kiểm tra subject và actor |
| Audit | Cần nguồn audit bổ sung để biết bên impersonate | Có thể ghi nhận subject và actor từ token đã xác thực |
| Rủi ro | Dễ mất dấu actor và khó điều tra hành động giả danh | Cần policy rõ cho cả subject và actor |
| Khi phù hợp | Chỉ khi nghiệp vụ yêu cầu hành động như chính subject và có kiểm soát chặt | Khi một service thực hiện thao tác thay mặt người dùng/service khác |

Không có mô hình nào tự động an toàn. Việc lựa chọn phải phù hợp nghiệp vụ, AS và khả năng resource server kiểm tra.

## 5. Các claim `sub`, `act`, `may_act` và `client_id`

### 5.1. `sub`: chủ thể được đại diện

`sub` là subject của token. Trong delegation, `sub` thường giữ danh tính của chủ thể ban đầu, chẳng hạn Alice. Resource server không được suy ra quyền chỉ từ `sub`; nó phải xác thực token và áp dụng policy đối với thao tác, tenant và tài nguyên cụ thể.

Subject không bắt buộc luôn là con người. Một token có thể đại diện cho service account hoặc workload nếu AS và hợp đồng token quy định như vậy.

### 5.2. `act`: actor đang hành động

Claim `act` được RFC 8693 định nghĩa để biểu diễn actor trong ngữ cảnh delegation. Nó là một JSON object; trường `sub` bên trong xác định actor.

```
{
  "sub": "user-123",
  "act": {
    "sub": "orders-service"
  }
}
```

`act` phải được đọc sau khi token được xác thực. Client không thể tự thêm hoặc sửa claim `act` trong JWT rồi mong resource server tin; sửa payload làm chữ ký không còn hợp lệ.

### 5.3. Delegation chain: actor lồng nhau

Một actor có thể đã nhận quyền từ một actor khác. RFC 8693 cho phép claim `act` chứa một claim `act` lồng nhau để thể hiện chuỗi delegation. Actor ở cấp ngoài cùng là actor hiện tại; các actor lồng bên trong thể hiện các bước trước đó trong chuỗi.

Ví dụ:

```
{
  "sub": "user-123",
  "act": {
    "sub": "inventory-facade",
    "act": {
      "sub": "orders-service",
      "act": {
        "sub": "api-gateway"
      }
    }
  },
  "aud": "api://inventory",
  "scope": "inventory:read"
}
```

Cách đọc từ ngoài vào trong:

1. `inventory-facade` là actor hiện tại đang gọi Inventory.
2. `orders-service` là actor trước đó đã ủy quyền/khởi tạo bước kế tiếp.
3. `api-gateway` là actor ở bước trước nữa trong chuỗi.

Không nên mặc định mọi AS đều giữ toàn bộ chuỗi actor. AS có thể rút gọn hoặc chỉ phát những thông tin được policy cho phép. Resource server phải hiểu đúng hợp đồng token và giới hạn độ sâu/độ dài nếu xử lý chuỗi lồng nhau.

### 5.4. `may_act`: ai có thể được phép hành động thay mặt subject?

RFC 8693 mô tả claim `may_act` như một cách biểu thị bên có thể được phép hành động thay mặt subject. Ví dụ subject token có thể mang thông tin:

```
{
  "sub": "user-123",
  "may_act": {
    "sub": "orders-service"
  }
}
```

Claim này có thể giúp AS xác định hoặc kiểm tra khả năng delegation. Tuy nhiên, **`may_act` không phải giấy phép tự động để actor lấy mọi token hoặc mọi scope**. AS vẫn phải kiểm tra client authentication, actor identity, audience, scope, policy hiện hành, trạng thái subject và ngữ cảnh yêu cầu. Resource server cũng không được dùng `may_act` như thay thế cho việc xác minh claim `act` trong token đầu ra.

Phân biệt:

| Claim | Ý nghĩa |
| --- | --- |
| `sub` | Chủ thể mà token đại diện |
| `act` | Actor hiện tại đang hành động thay mặt subject trong token được cấp |
| `may_act` | Thông tin về actor có thể được phép hành động thay mặt subject, theo policy AS |
| `client_id` | OAuth client đã yêu cầu token |
| `aud` | Resource server mà token được dành cho |

## 6. Token Exchange request: subject token và actor token

RFC 8693 định nghĩa Token Exchange Grant với grant type:

```
urn:ietf:params:oauth:grant-type:token-exchange
```

Các tham số chính:

| Tham số | Bắt buộc? | Vai trò |
| --- | --- | --- |
| `grant_type` | Có | Xác định Token Exchange Grant |
| `subject_token` | Có | Token/assertion đại diện cho subject |
| `subject_token_type` | Có | Loại của subject token |
| `actor_token` | Không | Token/assertion đại diện cho actor nếu cần |
| `actor_token_type` | Khi có `actor_token` | Loại của actor token |
| `requested_token_type` | Không | Loại token đầu ra mong muốn; access token là lựa chọn mặc định theo quy định |
| `audience` | Không | Resource/audience mong muốn |
| `resource` | Không | URI resource đích theo cơ chế resource indicators |
| `scope` | Không | Scope mong muốn cho token mới |

Một request minh họa:

```
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <orders-client-credentials-redacted>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<alice-orders-access-token>
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&actor_token=<orders-workload-token>
&actor_token_type=urn:ietf:params:oauth:token-type:access_token
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=api://inventory
&scope=inventory:read
```

Ý nghĩa:

- `subject_token` chứng minh danh tính subject theo loại token AS chấp nhận.
- `actor_token` chứng minh danh tính actor nếu flow cần một bằng chứng riêng cho actor.
- Client authentication xác định client đang gọi token endpoint. Nó là một lớp xác thực riêng, không tự động thay thế `subject_token` hay `actor_token`.
- `audience` yêu cầu token mới dành cho Inventory API.
- `scope` yêu cầu quyền tối thiểu cần cho thao tác.

AS có thể từ chối nếu không tin issuer của subject token, actor token sai, client không được phép exchange, actor không được phép đại diện subject, resource không hợp lệ hoặc scope vượt quá policy. Token exchange không phải cách “nâng cấp” token tùy ý.

Phản hồi thành công minh họa:

```
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory:read"
}
```

Các trường phản hồi thực tế tùy loại token và AS; `issued_token_type` cho biết loại token đã phát hành. Client cần bảo vệ token mới như credential, chỉ gửi đến resource được cấp và không log giá trị token.

## 7. AS phải xác minh điều gì trước khi phát token?

Token Exchange không bắt buộc AS phải phát token chỉ vì request đúng cú pháp. AS cần có policy rõ ràng cho từng client, subject, actor, resource và scope.

Một quy trình quyết định có thể gồm:

1. Xác thực OAuth client đang gọi token endpoint bằng phương thức đã đăng ký.
2. Kiểm tra grant type và quyền của client được phép dùng Token Exchange.
3. Xác minh `subject_token`: chữ ký/introspection, issuer, audience phù hợp với AS hoặc trust relationship, hạn, trạng thái và token type.
4. Nếu có `actor_token`, xác minh actor token tương tự và xác định chính xác actor.
5. Kiểm tra quan hệ subject–actor: actor có được phép đại diện subject không, có `may_act` hay policy delegation tương ứng không, có bị cấm theo tenant/đối tượng không.
6. Xác định audience/resource đích; chỉ phát token cho API mà client/actor được phép truy cập.
7. Tính scope/quyền đầu ra theo principle of least privilege; không tự động hợp nhất mọi scope từ subject token và actor token.
8. Đặt TTL, token type, sender constraint và claims phù hợp.
9. Phát token có chữ ký hoặc cơ chế bảo vệ được resource server tin cậy; audit quyết định cấp phát mà không lưu token nguyên văn.

Mô hình quyền hiệu lực có thể hình dung là giao của các giới hạn liên quan:

\[
P_{\text{effective}} \subseteq
P_{\text{subject}} \cap
P_{\text{actor}} \cap
P_{\text{client}} \cap
P_{\text{resource-policy}}
\]

Đây là mô hình tư duy về **giới hạn quyền**, không phải công thức bắt buộc của RFC. AS có thể áp dụng policy phức tạp hơn, nhưng không nên phát quyền rộng hơn mọi ràng buộc có liên quan.

## 8. Resource server kiểm tra subject và actor như thế nào?

Inventory API nhận access token mới phải xác thực token trước khi dùng bất kỳ claim nào:

- Kiểm issuer `iss` và chữ ký/khóa hoặc introspection.
- Kiểm audience có đúng `api://inventory`.
- Kiểm token type và các mốc `exp`, `nbf` cần thiết.
- Kiểm scope `inventory:read`.
- Đọc `sub` để biết subject được đại diện.
- Đọc `act.sub` để xác định actor nếu token theo mô hình delegation.
- Kiểm policy actor có được phép thực hiện thao tác này trên resource/tenant cụ thể không.
- Ghi audit subject, actor, hành động, resource và kết quả theo dữ liệu đã xác thực.

Ví dụ quyết định:

```
token = verifyAccessToken(request)

require token.iss == trustedIssuer
require token.aud contains "api://inventory"
require token.scope contains "inventory:read"

subject = token.sub
actor = token.act.sub

require subjectIsAllowed(subject, requestedItem)
require actorIsAllowed(actor, subject, "inventory:read")
require tenantPolicyAllows(subject, actor, requestedTenant)

return inventory.read(requestedItem)
```

Đây là pseudocode; các hàm kiểm tra phải dựa trên dữ liệu xác thực và policy thật. Nếu token không có `act`, API không được tự suy actor từ header do client gửi. Policy có thể chấp nhận token không có actor claim trong một số luồng service hoặc impersonation, nhưng phải phân biệt rõ trường hợp đó.

**Audience và scope vẫn độc lập với subject/actor:**

- `sub` trả lời “đại diện cho ai?”
- `act` trả lời “ai đang hành động thay mặt?”
- `aud` trả lời “token dành cho API nào?”
- `scope` trả lời “token cho phép loại hành động nào?”

Đúng subject và actor nhưng sai audience vẫn phải bị từ chối. Đúng audience nhưng thiếu scope hoặc quyền đối tượng cũng phải bị từ chối.

## 9. Token exchange qua nhiều service: giữ đúng chuỗi actor

Một request có thể qua Gateway → Orders → Inventory → Warehouse. Khi mỗi service tiếp tục ủy quyền, AS có thể phát token với chuỗi actor lồng nhau nếu policy và định dạng cho phép.

Ví dụ token gửi tới Warehouse:

```
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "act": {
    "sub": "inventory-service",
    "act": {
      "sub": "orders-service",
      "act": {
        "sub": "api-gateway"
      }
    }
  },
  "aud": "api://warehouse",
  "scope": "warehouse:stock:read",
  "exp": 1795000600
}
```

Warehouse nhìn thấy actor hiện tại là Inventory service và có thể xem các actor trước đó theo chuỗi. Tuy nhiên, không nên biến chuỗi actor thành một danh sách tùy ý do client gửi. Mỗi bước phải được AS xác minh và phát hành theo policy.

Khi chuỗi delegation dài, cần cân nhắc:

- Giới hạn số lần exchange và độ sâu `act`.
- Chỉ giữ thông tin actor cần cho authorization/audit.
- Tránh đưa dữ liệu cá nhân không cần thiết vào token.
- Đặt TTL phù hợp và scope giảm dần theo từng resource.
- Ngăn một actor tự đưa chính mình vào chuỗi hoặc thay đổi thứ tự actor.
- Xác định service nào được phép exchange tiếp và resource nào được phép nhận token.

Không phải mọi hệ thống đều cần giữ toàn bộ chuỗi. Một số hệ thống ghi lịch sử delegation trong audit store và chỉ đưa actor hiện tại vào token. Cần bảo đảm audit store có thể liên kết an toàn với request/token mà không làm mất khả năng điều tra.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đồng nhất `sub` với actor | Mất thông tin ai đang thực thi thay mặt subject | Dùng `act` khi token cần thể hiện delegation |
| Đồng nhất `client_id` với `act.sub` | Nhầm client gọi AS với actor trong ngữ cảnh delegation | Xác định actor theo actor token hoặc policy AS |
| Tin `may_act` như quyền đã được cấp | Actor có thể được cấp quyền vượt policy | AS phải kiểm tra quan hệ và ngữ cảnh hiện hành |
| Client tự thêm `act` hoặc `sub` vào JWT | Giả mạo danh tính nếu resource server chỉ decode token | Xác thực chữ ký/issuer/audience; không tin payload chưa verify |
| Exchange token sang audience bất kỳ | Token bị dùng sai resource | Allowlist resource/audience theo client và actor |
| Hợp nhất scope của subject và actor | Quyền đầu ra có thể rộng hơn giới hạn của một bên | Tính quyền theo policy giao và least privilege |
| Dùng token của Orders cho Inventory | Cross-service token substitution | Exchange token mới có audience Inventory |
| Không giới hạn actor chain | Token phình to, khó audit, tăng bề mặt tấn công | Giới hạn độ sâu và giữ thông tin cần thiết |
| Gửi subject/actor token vào log | Rò rỉ credential có thể dùng lại | Redact token, chỉ log metadata an toàn |
| Dùng ID token thay subject access token | Nhầm mục đích OIDC và OAuth access token | Chỉ nhận loại token AS đã cấu hình cho exchange |
| Không kiểm tra quyền tài nguyên | Scope hợp lệ nhưng vẫn truy cập dữ liệu ngoài phạm vi | Authorization theo subject, actor, tenant và resource |
| Fallback sang impersonation khi delegation lỗi | Mất dấu actor và có thể vượt quyền | Fail closed; sửa policy hoặc flow exchange |

## 11. Bảo vệ token exchange trước replay và đánh cắp

`subject_token` và `actor_token` đều là credential. Nếu bị lộ, chúng có thể bị dùng để yêu cầu token mới nếu AS chấp nhận chúng và client có quyền exchange.

Các biện pháp cần có:

- **TLS:** bảo vệ token endpoint và API đích; xác minh chứng chỉ server.
- **Client authentication:** xác thực client exchange; dùng secret, `private_key_jwt`, mTLS hoặc workload identity theo chính sách.
- **Token lifetime ngắn:** access token đầu ra chỉ sống đủ lâu cho tác vụ; không cấp TTL dài chỉ để giảm số lần exchange.
- **Audience giới hạn:** token mới chỉ dành cho resource đích.
- **Scope tối thiểu:** không chuyển mọi scope từ token đầu vào.
- **Sender-constrained token:** cân nhắc mTLS-bound hoặc DPoP để giảm khả năng replay bearer token.
- **Không log token:** che `subject_token`, `actor_token`, `access_token`, client assertion và Authorization header.
- **Replay controls:** với assertion JWT, kiểm tra `jti`, `exp`, `aud` và chống dùng lại theo policy; với access token, áp dụng TTL, revocation/introspection hoặc sender constraint khi phù hợp.
- **Audit:** lưu client, subject, actor, audience, scope, kết quả và correlation ID; không lưu bí mật nguyên văn.
- **Credential rotation:** quản lý vòng đời khóa/chứng chỉ/secret của actor và client; có quy trình thu hồi khi nghi bị lộ.

Nếu AS hoặc resource server dùng JWT offline validation, token đã phát hành có thể còn được chấp nhận đến `exp` trừ khi có cơ chế thu hồi/denylist/introspection hoặc khóa ký bị vô hiệu theo policy. Token exchange không tự giải quyết vấn đề thu hồi.

## 12. HTTP lỗi và xử lý thất bại

| Lỗi | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `invalid_client` | OAuth client xác thực thất bại | Kiểm client credential và method; không retry vô hạn |
| `invalid_grant` | Subject/actor token không hợp lệ, hết hạn, bị thu hồi hoặc grant không được chấp nhận | Xác minh token nguồn và policy; yêu cầu xác thực/ủy quyền lại nếu cần |
| `invalid_request` | Thiếu `subject_token_type`, `actor_token_type` hoặc tham số sai | Kiểm request theo RFC 8693 và hợp đồng AS |
| `invalid_scope` | Scope không hợp lệ hoặc vượt quyền | Xin scope được phép; không tự nâng quyền |
| `unauthorized_client` | Client không được phép sử dụng token exchange | Cập nhật policy/đăng ký qua quy trình quản trị |
| `unsupported_grant_type` | AS không hỗ trợ Token Exchange Grant | Kiểm khả năng AS và cấu hình |
| `401 invalid_token` tại resource | Token đầu ra sai, hết hạn, sai issuer/audience hoặc bị thu hồi | Invalidate đúng token và kiểm nguyên nhân |
| `403 insufficient_scope` | Token hợp lệ nhưng thiếu quyền | Kiểm policy cấp phát và quyền tài nguyên; không refresh lặp vô hạn |

Client nên có timeout, backoff và giới hạn retry cho token endpoint. Không fallback bằng cách gửi `subject_token` nguyên bản đến API đích nếu exchange thất bại. Nếu không lấy được token đúng audience/actor/scope, dừng thao tác và trả lỗi phù hợp.

## 13. Ví dụ nghiệp vụ: Alice xem tồn kho qua Orders

Giả sử:

- Alice có quyền xem đơn hàng và tồn kho của các sản phẩm thuộc tenant của mình.
- API Gateway xác thực access token của Alice.
- Orders API được phép gọi Inventory thay mặt Alice.
- Inventory chỉ nhận access token có `aud=api://inventory`, scope `inventory:read`.

Luồng đúng:

1. Gateway chuyển request đến Orders sau khi xác thực token dành cho Orders.
2. Orders kiểm tra Alice có quyền đọc đơn hàng tương ứng.
3. Orders gọi AS bằng OAuth client identity của chính nó.
4. Orders gửi subject token của Alice và actor token/danh tính workload theo cấu hình AS.
5. AS kiểm tra client được phép exchange, subject hợp lệ, actor được phép đại diện subject, scope và audience phù hợp.
6. AS phát token mới dành cho Inventory, giữ `sub=Alice`, thể hiện actor Orders qua `act` nếu dùng delegation.
7. Inventory xác thực token, kiểm audience, scope, subject, actor và quyền đối với sản phẩm/tenant.
8. Inventory trả kết quả; Orders tiếp tục xử lý và ghi audit.

Nếu AS chỉ hỗ trợ impersonation, token đầu ra có thể không thể hiện actor qua `act`. Khi đó cần một cơ chế audit đáng tin cậy khác để giữ dấu vết Orders đã thực thi hành động. Không được giả định chỉ vì `client_id=orders-service-client` là đủ chứng minh actor ở mọi hệ thống.

## 14. Checklist triển khai và kiểm thử

Trước khi bật token exchange trong production, cần trả lời:

- Subject token được phát hành bởi issuer nào và AS xác minh bằng cách nào?
- Actor được xác định bằng actor token, client authentication hay workload identity?
- Client nào được phép exchange cho subject nào?
- `may_act` có được dùng không, và policy nào xác minh quyền delegation?
- Token đầu ra giữ subject, phát actor claim và audience ra sao?
- Resource server kiểm tra `sub`, `act`, `aud`, scope và tenant như thế nào?
- Delegation chain có được giữ không, giới hạn độ sâu và dữ liệu nào?
- Token exchange thất bại thì hệ thống dừng hay có phương án được phê duyệt nào?
- Token và assertion được bảo vệ, thu hồi, audit và giám sát ra sao?

Các test tối thiểu:

| Test | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| T1 | Subject Alice hợp lệ, actor Orders được phép, audience Inventory và scope đúng | AS phát token mới theo policy |
| T2 | Subject token hết hạn | AS từ chối exchange |
| T3 | Actor token sai chữ ký/issuer | AS từ chối exchange |
| T4 | Client xác thực hợp lệ nhưng không được phép exchange | AS từ chối |
| T5 | Actor không được phép đại diện Alice | AS từ chối |
| T6 | `may_act` chỉ cho phép Service A nhưng actor là Service B | AS từ chối theo policy |
| T7 | Token đầu ra có `sub=Alice`, `act.sub=Orders` | Inventory phân biệt subject và actor |
| T8 | Token đầu ra sai `aud` | Inventory từ chối |
| T9 | Token đúng audience nhưng thiếu `inventory:read` | Inventory từ chối do thiếu scope |
| T10 | Token bị sửa claim `act` nhưng chữ ký không hợp lệ | Resource server từ chối |
| T11 | Actor chain vượt giới hạn cấu hình | AS từ chối hoặc rút gọn theo policy đã công bố |
| T12 | Client gửi ID token trong khi AS chỉ chấp nhận access token làm subject token | AS từ chối loại token không phù hợp |
| T13 | Subject có quyền đọc nhưng actor không có quyền gọi Inventory | AS/resource policy từ chối |
| T14 | Token exchange trả `invalid_grant` | Client không fallback sang relay token sai audience |
| T15 | Token bị phát lại từ nguồn không có sender proof hợp lệ | Bị từ chối khi sender constraint được áp dụng |

## 15. Ghi nhớ và chuẩn tham khảo

`subject` và `actor` trả lời hai câu hỏi khác nhau. `sub` nhận diện chủ thể mà token đại diện; `act` nhận diện actor đang thực hiện hành động thay mặt subject; `may_act` có thể chỉ ra actor được phép trong ngữ cảnh policy. `client_id` nhận diện OAuth client yêu cầu token, còn `aud` nhận diện resource server được phép nhận token.

**Delegation giữ rõ cả subject và actor; impersonation thể hiện hành động như subject và thường không biểu diễn actor qua `act`.** AS phải xác minh token nguồn, client, actor, quan hệ ủy quyền, audience và scope trước khi phát token mới. Resource server phải xác minh token đầu ra và áp dụng quyền trên tài nguyên thực tế.

Tài liệu chuẩn để đối chiếu:

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): `subject_token`, `actor_token`, `act`, `may_act`, delegation và impersonation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth client, grant, access token và client authentication.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp` và cấu trúc JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và xác minh phía resource server.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): xác định resource/audience khi xin token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái và metadata token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): giảm rủi ro replay bằng proof-of-possession.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện hành.
