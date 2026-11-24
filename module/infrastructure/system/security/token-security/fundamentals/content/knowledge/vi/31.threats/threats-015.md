# Over-privileged scope

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **over-privileged scope** (scope vượt quá quyền cần thiết) là gì trong OAuth 2.0/OIDC, tại sao nó làm tăng **blast radius** khi access token hoặc client credentials bị lộ.
- Phân biệt **requested scope**, **client-registered/allowed scope**, **user-consented scope**, **granted scope**, **scope được ghi trong access token** và **quyền cuối cùng mà Resource Server (RS) thực thi**.
- Phân biệt **scope, role, permission, claim, audience, resource, tenant**; hiểu tại sao scope không tự biểu diễn đối tượng dữ liệu hoặc quyền sở hữu cụ thể.
- Nhận diện các mối đe dọa: scope inflation, consent phishing, token reuse giữa API, client credential lạm quyền, lỗi chọn resource/audience, lỗi mapping scope và privilege escalation khi refresh/token exchange.
- Thiết kế cấp quyền theo **least privilege**, **deny by default**, chính sách phát hành phía Authorization Server (AS) và kiểm quyền theo hành động/tài nguyên phía RS.
- Hiểu cách áp dụng authorization theo **client, subject, grant, audience/resource, API operation, tenant, risk context**, thay vì chỉ tin chữ ký token.
- Nêu giới hạn của JWT/JWS signature, opaque token, mTLS/DPoP sender-constraining, refresh-token rotation và token revocation đối với over-privileged scopes.
- Xây dựng pseudocode/Java/Spring Security và ma trận negative tests để ngăn token có scope quá rộng cấp quyền vượt chính sách.
- Thiết kế quy trình audit, giám sát scope drift, review consent, ứng phó khi token chứa quyền quá rộng đã được cấp, và checklist production.

## 1. Over-privileged scope là gì?

Trong OAuth 2.0, **scope** là tập các chuỗi do hệ thống định nghĩa để mô tả **phạm vi truy cập mà access token được yêu cầu hoặc được cấp**. Ví dụ minh họa của một hệ thống Orders:

~~~text
orders:read      Đọc dữ liệu đơn hàng được phép xem
orders:create    Tạo đơn hàng trong phạm vi được phép
orders:approve   Phê duyệt đơn hàng khi thỏa điều kiện nghiệp vụ
orders:refund    Yêu cầu hoặc thực hiện hoàn tiền theo policy
~~~

Các chuỗi này **không phải scope chuẩn toàn cầu**. Chúng là quy ước do AS/RS và API contract cùng định nghĩa.

**Over-privileged scope** xảy ra khi client hoặc access token được cấp **scope nhiều hơn, rộng hơn hoặc nhạy cảm hơn** mức cần thiết và được phép cho công việc đã xác định.

Ví dụ:

~~~text
Nhu cầu thực tế:
    Dashboard chỉ cần GET /api/orders.

Scope phù hợp:
    orders:read

Scope được cấp sai:
    orders:read orders:approve orders:refund

Rủi ro:
    Nếu token bị copy, attacker có thể thử các API phê duyệt/hoàn tiền.
    Nếu RS chỉ kiểm "scope có mặt" mà không kiểm quyền trên
    order/tenant cụ thể, hậu quả có thể lớn hơn rất nhiều.
~~~

Một token có **chữ ký JWT hợp lệ**, **issuer đúng** và **exp còn hạn** vẫn có thể quá quyền. Chữ ký xác nhận nội dung token được bảo vệ bằng key đáng tin; nó **không chứng minh mọi scope trong token đều cần thiết và đúng chính sách nghiệp vụ**.

### Phân biệt ba mức độ nguy hiểm

| Trường hợp | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Client được đăng ký scope quá rộng, nhưng token chỉ nhận scope hẹp | Tiềm năng leo quyền ở lần cấp token sau. | Thu hẹp client registration/allowed scope và quy trình consent/grant. |
| AS cấp token scope vượt nhu cầu hoặc ngoài policy | Token có năng lực rộng ngay lúc phát hành. | Sửa issuance policy, thu hồi token/grant sai và kiểm affected resources. |
| RS cho thực hiện hành động vượt scope hoặc vượt quyền trên tài nguyên | Lỗi thực thi authorization, có thể khai thác trực tiếp. | Sửa authorization tại RS, kiểm route/method/object và audit. |

**Least privilege phải được áp dụng ở cả AS và RS**. Giới hạn scope khi phát hành là cần thiết, nhưng không thay thế việc kiểm quyền tại từng API.

## 2. Tại sao đây là một threat chứ không chỉ là cấu hình xấu?

Scope rộng làm tăng **năng lực của credential**. Khi credential bị đánh cắp, cấu hình quá quyền biến một sự cố token theft nhỏ thành một vụ truy cập hoặc thay đổi dữ liệu diện rộng.

~~~mermaid
flowchart LR
    A["Client chỉ cần đọc Orders"] --> B["AS phát AT có read + approve + refund"]
    B --> C["Token được lưu trong browser/log/cache"]
    C --> D["Attacker sao chép Bearer AT"]
    D --> E["Gọi Orders Approve / Refund APIs"]
    E --> F["RS kiểm scope quá lỏng hoặc không kiểm resource"]
    F --> G["Thực hiện hành động ngoài nhu cầu ban đầu"]
~~~

Một chuỗi tấn công có thể không cần giả chữ ký, phá mật mã hoặc chiếm AS. Attacker chỉ cần có **Bearer access token còn hiệu lực** với năng lực vượt mức và tìm được API chấp nhận quyền đó.

### Thuộc tính bảo mật liên quan

- **Confidentiality:** scope đọc rộng có thể làm lộ nhiều records hoặc nhiều loại thông tin.
- **Integrity:** scope ghi/phê duyệt/xóa có thể cho thay đổi dữ liệu ngoài mục đích.
- **Availability:** scope admin hoặc bulk operations có thể làm gián đoạn dịch vụ.
- **Separation of duties:** một client có cả quyền tạo và phê duyệt cùng đối tượng có thể phá quy tắc hai người.
- **Accountability:** nếu dùng cùng token quyền cao cho nhiều workloads, khó xác định workload nào thật sự cần quyền.
- **Blast radius:** token lộ tại một nơi có thể được dùng ở nhiều endpoints hoặc services nếu scope và audience không được ràng chặt.

**Mục tiêu của least privilege không phải chỉ là giảm số scope có tên trong token**, mà là thu nhỏ **hành động, tài nguyên, thời gian và ngữ cảnh** mà credential có thể tác động.

## 3. Ai quyết định scope ở từng giai đoạn?

Không nên coi tham số **scope** trong authorization request là quyền đã được cấp.

~~~mermaid
flowchart TD
    C["OAuth Client: requested scope"] --> R["Client registration / policy allowlist"]
    R --> U["User/grant consent và subject authority, khi áp dụng"]
    U --> AS["Authorization Server: cấp authorized scope cho resource"]
    AS --> T["Access token ghi scope được cấp"]
    T --> RS["Resource Server: kiểm scope + object/tenant permission"]
    RS --> O["ALLOW hoặc DENY đúng operation"]
~~~

### Các tập quyền

Ký hiệu:

- **S_req:** scopes client xin.
- **S_client:** scopes được phép cho client registration/client type.
- **S_grant:** scopes được chủ thể/consent hoặc authorization grant cho phép.
- **S_resource:** scopes hợp lệ với resource/audience cụ thể.
- **S_risk:** scopes còn được policy cho phép trong ngữ cảnh hiện tại.
- **S_issued:** scopes thực sự được AS cấp và gắn vào token.

Đối với một policy định nghĩa scope là các nhãn độc lập và cho phép dùng phép giao, mô hình khái niệm là:

\[
S_{\text{issued}}\subseteq
S_{\text{req}}\cap S_{\text{client}}\cap S_{\text{grant}}
\cap S_{\text{resource}}\cap S_{\text{risk}}
\]

**Lưu ý:** đây là mô hình minh họa khi AS cấp một tập con các scope được yêu cầu. Trong OAuth, một AS có thể áp dụng **scope default/mapping/normalization** theo hợp đồng, và quan hệ giữa các scope có thể có phụ thuộc/hàm ý riêng. Không áp dụng phép giao máy móc cho tất cả trường hợp; cần **chính sách cấp quyền thực tế** được xác định trước và có kiểm thử. Điều bất biến là **client không tự có quyền chỉ vì yêu cầu nó**.

### Ví dụ request/response

~~~http
GET /authorize?response_type=code&client_id=dashboard-web&scope=openid%20orders%3Aread%20orders%3Arefund&state=EXAMPLE_STATE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Client xin cả **orders:refund**. Nếu client được đăng ký chỉ cho orders:read, AS **không được ngầm mở scope refund vì request có chuỗi đó**. AS có thể từ chối request hoặc xử lý thu hẹp theo policy/profile và protocol.

Khi AS cấp phạm vi khác đã yêu cầu, **OAuth token response cần thông báo scope thực sự đã cấp** theo yêu cầu RFC 6749:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Đây là response minh họa, không phải token thật. Client **không được mặc định** nhận được mọi scope đã xin chỉ vì token endpoint trả 200.

## 4. Scope, role, permission, claim và audience khác nhau

| Khái niệm | Ý nghĩa | Ví dụ | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Scope** | Khả năng được cấp cho OAuth access token theo API contract. | orders:read | Coi scope là quyền đọc mọi order của mọi tenant. |
| **Role** | Tập trách nhiệm/chức năng của principal trong ứng dụng. | OrderApprover | Gán nguyên role admin của user vào mọi client token. |
| **Permission** | Quyền thực hiện hành động đối với một resource cụ thể. | approve order#123 của tenant A | Chỉ kiểm role, không kiểm trạng thái order/ownership. |
| **Claim** | Thuộc tính có trong token do issuer tạo. | sub, aud, scope, client_id, tenant_id | Tin claims chưa verify signature/trust. |
| **Audience** | Resource hoặc bên nhận mà token nhắm tới. | orders-api | Dùng token intended cho Reports sang Payments. |
| **Resource indicator** | Định danh resource được client yêu cầu theo profile, ví dụ RFC 8707. | https://orders.example.test/api | Cho client chọn resource bất kỳ và tự gắn scope admin. |
| **Tenant/organization** | Biên dữ liệu/đơn vị của tài nguyên. | tenant-blue | Tin tenant_id trong request body mà không kiểm token+DB. |
| **Authorization grant/consent** | Kết quả cấp phép cho client theo context. | Dashboard được đọc orders của user | Cho quyền kéo dài hoặc đổi resource vô hạn không kiểm policy. |

### Một scope không phải quyền sở hữu mọi đối tượng

Access token có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-101",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_id": "tenant-blue",
  "exp": 1796000000
}
~~~

Giả sử mọi cryptographic checks đều hợp lệ. Token vẫn **không được phép** dùng để truy cập order thuộc tenant-red, order thuộc principal khác hoặc đối tượng bị policy hạn chế. RS phải thực thi **record-level/tenant-level authorization** từ trạng thái đáng tin của mình.

### Scope không thay audience

Một token có orders:read nhưng **aud=reports-api** không được Orders nhận chỉ vì có chữ orders:read. Audience là **ranh giới nơi token được trình**, scope là **khả năng bên nhận có thể cân nhắc**, hai điều kiện đều cần đúng.

### Role không tự thành scope

User có role FinanceAdmin không có nghĩa bất kỳ OAuth client nào họ dùng cũng được nhận **payments:approve**. AS phải kiểm client registration, grant/consent, requested resource, policy/risk, rồi mới quyết định scope cấp.

## 5. Các dạng over-privileged scope

| Dạng | Ví dụ | Tác động |
| --- | --- | --- |
| **Excessive breadth** | orders:* hoặc read/write/admin chung. | Một token có thể gọi nhiều API hơn dự kiến. |
| **Unnecessary sensitive scope** | Dashboard xem danh sách được cấp orders:refund. | Token theft có thể trở thành fraud/modify. |
| **Cross-resource privilege** | Một AT dùng được cho Orders và Payments. | Lateral movement giữa services. |
| **Cross-tenant privilege** | Scope đọc không có tenant binding. | Dữ liệu nhiều tổ chức có thể bị đọc. |
| **Long-lived broad access** | AT rộng với exp dài hoặc RT giữ grant rộng. | Cửa sổ khai thác lớn. |
| **Client credential overgrant** | Batch worker cần reports:read nhưng được payments:approve. | Chiếm workload dẫn đến quyền thay đổi tài chính. |
| **Consent overreach** | App xin nhiều scope không gắn tính năng thật. | User đồng ý quyền không cần thiết. |
| **Scope escalation on refresh** | RT phát hành cho read nhưng AT mới có write. | Kéo dài/leo quyền không qua authorization phù hợp. |
| **Overbroad token exchange** | Downstream token nhận nhiều scope hơn nguồn và policy cho phép. | Service-to-service privilege escalation. |
| **Semantic mapping bug** | orders:read được coi tương đương orders:approve. | RS thực thi sai quyền. |
| **Default allow** | Nếu scope claim rỗng thì cấp quyền mặc định. | Missing claim biến thành admin. |
| **Wildcard/prefix matching** | orders:read:all bị chấp nhận như orders:read. | Lỗi parser/matcher tạo tăng quyền. |

**Scope “rộng” không tự là lỗi ở mọi tình huống.** Một service vận hành có thể được cấp quyền đặc biệt theo thủ tục kiểm soát, nhưng phải có **nhu cầu thật, rủi ro được chấp thuận, thời hạn, audit và enforcement**. Over-privilege là **sự lệch khỏi quyền tối thiểu cần thiết trong trust context**, không phải danh sách từ ngữ bị cấm tuyệt đối.

## 6. Mô hình tấn công: scope inflation

**Scope inflation** là tình huống scope được mở rộng sai qua một bước authorization hoặc token transformation.

Ví dụ:

~~~text
Client registration:
    allowed = {orders:read}

Requested:
    {orders:read, orders:approve}

Expected:
    deny orders:approve (hoặc reject request)

Actual bug:
    AS copies requested scope unchanged into JWT:
    scope = "orders:read orders:approve"
~~~

Một bug có thể rất đơn giản:

~~~java
// SAI: client input không được trở thành quyền đã cấp.
String grantedScope = request.getParameter("scope");

claims.put("scope", grantedScope);
~~~

**JWT signature hợp lệ không phát hiện lỗi này**: AS thật sự đã ký claims sai. Resource Server chỉ kiểm presence của scope thì sẽ tin quyền cao đó, trừ khi có kiểm tra chính sách/permission độc lập.

### Ba điểm dễ xuất hiện inflation

1. **Authorization endpoint:** yêu cầu scope bị coi là quyền thực tế trước khi so registration/consent.
2. **Token endpoint:** code/grant chỉ có read nhưng token claims generator lấy lại requestedScopes thay vì persistedGrantedScopes.
3. **Refresh/token exchange:** grant ban đầu hẹp nhưng client có thể thêm write/admin trong một request tiếp theo.

### Hậu quả không phụ thuộc định dạng token

Nếu AS phát một **opaque AT** có backend metadata scope sai, Resource Server introspection có thể nhận scope quá quyền tương tự JWT. Đổi từ JWT sang opaque **không tự sửa sai policy cấp quyền**.

## 7. Resource Server là ranh giới bắt buộc cuối cùng

Một RS nên đánh giá nhiều điều kiện:

~~~text
TOKEN ACCEPTANCE:
    correct trusted issuer
    AND correct audience
    AND correct token type/profile
    AND valid signature or trusted introspection
    AND exp/nbf, revocation and sender-binding rules satisfied

AUTHORIZATION:
    required scope for endpoint/method exists
    AND subject/client is allowed for this action
    AND tenant/resource ownership matches
    AND current resource state satisfies business policy
    AND additional controls (approval/step-up/SoD) hold when required
~~~

**Không nhập hai nhóm kiểm thành một câu “JWT hợp lệ thì cho qua”.** Một JWT đúng chữ ký chỉ chứng minh tính xác thực theo key trust; không khẳng định user được phê duyệt đơn hiện tại hoặc client có quyền thực hiện hành động high-risk.

### Ví dụ policy ở Orders API

| Endpoint | Scope tối thiểu | Kiểm tra nghiệp vụ |
| --- | --- | --- |
| GET /api/orders | orders:read | Chỉ danh sách được phép, tenant giới hạn. |
| GET /api/orders/{id} | orders:read | Order tồn tại, principal được phép xem order. |
| POST /api/orders | orders:create | Client/user được phép tạo trong tenant. |
| POST /api/orders/{id}/approve | orders:approve | User được phép approve, không tự approve và đúng trạng thái. |
| POST /api/orders/{id}/refund | orders:refund | Chính sách tài chính, giới hạn số tiền, approval bổ sung. |
| DELETE /api/orders/{id} | orders:delete | Chính sách xóa và lưu dấu audit. |

Các đường dẫn/scope chỉ là ví dụ. **orders:approve** có thể là điều kiện cần nhưng **không đủ**. Nếu order thuộc tenant khác, người dùng tự duyệt đơn của mình hoặc trạng thái nghiệp vụ không cho approve, RS phải từ chối.

## 8. Threat model: từ scope rộng đến lạm dụng API

~~~mermaid
sequenceDiagram
    participant C as Dashboard OAuth Client
    participant AS as Authorization Server
    participant X as Attacker
    participant RS as Orders API
    participant DB as Orders Database

    C->>AS: Xin scope=orders:read
    Note over AS: Client policy cấu hình sai cho quá nhiều scope
    AS-->>C: AT có read + approve + refund
    X-->>X: Sao chép AT từ log/storage bị lộ
    X->>RS: POST /orders/123/approve với AT
    RS->>RS: Verify JWT và thấy orders:approve
    alt RS kiểm thêm business permission
        RS-->>X: 403 Forbidden
    else RS chỉ kiểm scope
        RS->>DB: Cập nhật order đã phê duyệt
        DB-->>RS: OK
        RS-->>X: 200 OK
    end
~~~

Trong ví dụ, việc cấp scope quá rộng là lỗi **AS policy**, còn việc không kiểm quyền sở hữu/đơn hàng là lỗi **RS authorization**. Hai lỗi kết hợp tạo hậu quả lớn hơn một lỗi đơn lẻ.

### Nguyên tắc defense in depth

- AS **không phát scope không được policy cho phép**.
- Client **chỉ yêu cầu scope cần cho tính năng**.
- RS **từ chối operation ngoài scope**.
- RS **kiểm business permission ngay trên resource**.
- Logging và revocation giúp phát hiện, giới hạn hậu quả nhưng **không thay kiểm quyền**.

## 9. Least privilege ngay từ OAuth client registration

Authorization Server cần có cấu hình đáng tin cho **client_id**, loại client, grant types, redirect URIs, **allowed scopes** và **allowed resources**.

~~~yaml
# Policy minh họa, không phải schema client registration chuẩn.
clientId: orders-dashboard
allowedGrantTypes: [authorization_code]
allowedScopes: [openid, profile, orders:read]
allowedResources: [https://orders.example.test/api]
accessTokenMaxTtlSeconds: 600
~~~

### Client allowlist là trần quyền, không phải lệnh cấp

- Chỉ đăng ký scope cần cho chức năng hiện tại.
- Tách clients có trust/risk khác nhau; không dùng một super-client cho nhiều workloads.
- Không dùng chung credentials giữa development, staging và production.
- Ràng **client_id → allowed grant types → scopes → resources/audiences**.
- Bổ sung security review hoặc approval cho scopes nhạy cảm.
- Kiểm user, grant/consent và authorization policy **sau** bước client allowlist.
- Không cho client tự mở rộng registration bằng dữ liệu trong OAuth request.

Một client **có thể** được phép xin orders:approve nhưng user cụ thể vẫn có thể không được phê duyệt. Registration chỉ đặt **giới hạn tối đa**, không quyết định quyền trong mọi transaction.

## 10. Consent overreach và scopes người dùng không cần

Một app xem đơn hàng nhưng xin:

~~~text
openid profile orders:read orders:approve payments:refund offline_access
~~~

đang đưa ra rủi ro **consent overreach**. User có thể chấp thuận vì hiểu sai mô tả, UI quá phức tạp, hoặc tên app có vẻ đáng tin.

**Consent không tự vượt AS policy**: dù user bấm Allow, scope ngoài client registration, user entitlements hoặc resource policy vẫn phải bị từ chối.

Biện pháp:

1. **Minimum upfront consent:** chỉ yêu cầu scope thiết yếu cho tính năng đang dùng.
2. **Incremental authorization:** xin scope bổ sung khi user thực sự bắt đầu hành động đòi quyền mới, nếu hệ thống hỗ trợ.
3. **Scope descriptions rõ ràng:** phân biệt xem, tạo, duyệt, xóa và hoàn tiền.
4. **Sensitive scope review:** chỉ một số client đã được duyệt mới xin quyền đặc biệt.
5. **Step-up/reconsent khi cần:** yêu cầu bằng chứng mới cho nghiệp vụ nhạy cảm.
6. **Grant management:** user/admin xem và rút consent, AS thực thi thay đổi.
7. **Token issuance consistency:** AS dùng persisted granted scope, không copy chuỗi requestedScope thô.

Scope xuất hiện trong UI consent **chưa chứng minh** grant đã được ghi hay AT đã nhận scope ấy.

## 11. OIDC scopes không phải quyền nghiệp vụ của mọi API

Các scope thường gặp trong OpenID Connect:

~~~text
openid profile email address phone offline_access
~~~

có ý nghĩa liên quan authentication/claims và provider profile, **không tự cấp quyền** đối với Orders/Payments API.

Sai:

~~~text
if token.scope contains "openid":
    allow GET /api/orders
~~~

**openid** không tương đương orders:read. Tương tự, **ID token** gửi cho Relying Party/client không phải OAuth access token mặc định được Orders RS chấp nhận.

### offline_access và thời hạn quyền

Scope **offline_access** trong các profile OIDC có thể liên quan khả năng cấp refresh token. Nếu RT được phát cho grant quá rộng, client hoặc attacker giữ RT có thể tiếp tục xin AT trong thời gian grant còn hiệu lực.

**Không khẳng định offline_access luôn dẫn tới refresh token**: AS còn kiểm client/grant/consent/policy. RT rotation và reuse detection hỗ trợ phát hiện credential theft nhưng không tự thu hẹp granted scope.

## 12. Client Credentials: quyền workload không phải quyền end-user

OAuth 2.0 **Client Credentials Grant** cấp AT cho service/client dựa trên client authentication và authorization policy; không có end-user delegated consent trong request.

~~~http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports%3Aread
~~~

### Threat: machine token quá quyền

~~~text
Workload = reports-exporter
Required scope = reports:read
Misconfigured grant = reports:read payments:approve users:admin
~~~

Nếu secret/private key của exporter bị lộ, attacker có thể xin hoặc sử dụng tokens với quyền không liên quan tới báo cáo.

Bảo vệ:

- Mỗi workload có client identity/registration riêng và allowed scopes/resources cụ thể.
- Không tạo một service client siêu quyền để tái sử dụng cho mọi batch job.
- Giới hạn TTL và key/secret custody; dùng mTLS/private_key_jwt/workload identity khi phù hợp.
- RS kiểm client principal, tenant/data boundary và business permission.
- Không giả định **sub luôn là người dùng** khi xử lý client_credentials AT.
- Scope reports:read không tự cho phép đọc báo cáo của mọi tenant.

Mô hình **least privilege của machine-to-machine** không dựa vào consent của end-user mà dựa vào workload authorization và client/resource policy.

## 13. Refresh token: scope không được phình ra khi refresh

Giả sử original grant:

~~~text
client = orders-dashboard
resource = orders-api
granted scopes = {orders:read}
RT family = F
~~~

Client sau đó gửi:

~~~http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_RT1&scope=orders%3Aread%20orders%3Aapprove
~~~

**AS không được cấp orders:approve chỉ vì tham số scope xuất hiện.** Theo OAuth 2.0, scope được yêu cầu trong refresh không được bao gồm scope ngoài original grant; chính sách hiện thời còn có thể thu hẹp thêm.

~~~text
originalGranted = {orders:read}
requestedAtRefresh = {orders:read, orders:approve}

if requestedAtRefresh not permitted by originalGranted:
    reject escalation according to protocol/policy
~~~

Việc thêm quyền phải đi qua **authorization/grant update** phù hợp, không tự gắn vào refresh request.

### Rotation không giải quyết inflation

Refresh token rotation và reuse detection giúp phát hiện RT cũ bị dùng lại. Chúng **không kiểm granted scopes** nếu token endpoint copy raw requested scope vào AT mới.

### User bị mất role

Nếu user mất Approver role hoặc admin thu hồi consent, lần refresh mới không nên tiếp tục cấp approve không kiểm policy. AS phải xét grant, client, subject entitlements và current authorization.

Scope trong AT đã phát **không tự đổi khi user mất role**. Muốn chặn trước exp cần revocation/online policy ở RS hoặc token lifetime phù hợp.

## 14. Token exchange và downstream delegation

Trong kiến trúc nhiều services:

~~~text
Dashboard AT (aud=frontend-api, scope=orders:read)
    -> BFF
    -> Orders API
    -> Payments API
~~~

Một hệ thống có thể dùng OAuth Token Exchange (RFC 8693) để mint token downstream theo một trust/delegation contract.

### Threat: scope inflation khi exchange

~~~text
Input token:
    aud=frontend-api
    scope=orders:read

Requested output:
    aud=payments-api
    scope=payments:refund

Bug:
    AS chỉ verify input token rồi chấp nhận requested output
    mà không kiểm client/actor/delegation/resource policy.
~~~

**Input token hợp lệ không có nghĩa output token được phép có bất kỳ scope/resource nào.**

Một AS xử lý exchange cần kiểm actor/client identity, subject, resource, requested token type, delegation rights, risk context và output audience.

### Không so scope strings máy móc

Scope upstream/downstream có thể dùng tên khác nhau, nên output scope không nhất thiết là chuỗi trùng với input scope. Nhưng **output authority phải được chứng minh từ một policy đã định nghĩa và kiểm thử**, không do client tự khai.

### Confused deputy

BFF nắm một credential payments:refund của chính nó. Caller chỉ có orders:read nhưng yêu cầu BFF hoàn tiền.

Nếu BFF dùng **quyền cao của chính mình** thực hiện theo caller không đủ quyền, nó trở thành **confused deputy**. Cần kiểm caller authority, tenant, amount, operation policy và approvals **trước** khi dùng credential downstream.

## 15. Audience/resource indicator giới hạn nơi token sử dụng

OAuth Resource Indicators (RFC 8707) hỗ trợ chỉ định resource mục tiêu theo profile.

~~~http
GET /authorize?response_type=code&client_id=dashboard-web&resource=https%3A%2F%2Forders.example.test%2Fapi&scope=orders%3Aread&state=EXAMPLE_STATE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

AS cần kiểm client được xin resource, scope hợp lệ cho resource và grant/consent phù hợp.

### Hai lỗi nguy hiểm

1. **AT multi-audience quá rộng:** một token bị lộ có thể được dùng tại nhiều APIs.
2. **Cross-resource acceptance:** Orders chấp nhận AT có aud=payments-api vì cùng issuer và chuỗi scope trùng.

### Scope-name collision

~~~text
Orders scope = write (sửa đơn)
Payments scope = write (thay đổi thanh toán)
~~~

Nếu RS chỉ kiểm write mà bỏ audience, token có thể đi lạc miền tin cậy. Naming rõ như orders:write, payments:write giúp giảm nhầm nhưng **không thay audience validation**.

### Bảo vệ

- AS ràng allowed resources và scope với client/grant.
- RS kiểm issuer/audience/type của token cho đúng endpoint.
- Không dùng ID token hoặc UserInfo token thay Orders access token.
- Không để header từ token tự chọn JWKS/issuer trust ngoài allowlist.
- Không dùng một admin token cho nhiều services chỉ để giảm network overhead.
- Token exchange cần output audience và delegation policy cụ thể.

## 16. Scope quá rộng trong SaaS đa tenant

Một SaaS Orders phục vụ nhiều tổ chức. **orders:read** chỉ mô tả hành động tổng quát, không chỉ rõ order thuộc tenant hoặc chủ sở hữu nào.

Token ví dụ:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "orders-api",
  "sub": "user-blue-17",
  "client_id": "dashboard-web",
  "scope": "orders:read",
  "tenant_id": "tenant-blue",
  "exp": 1796000000
}
~~~

Nếu user-blue-17 gọi GET /api/orders/order-red-550, Orders RS phải xác minh **order thuộc tenant nào** và principal có quyền với order đó, không chỉ kiểm chuỗi orders:read.

### ABAC/ReBAC bổ sung scope

~~~text
allowReadOrder(principal, order):
    token contains orders:read
    AND principal is allowed in order.tenant
    AND (principal owns order OR allowed team relationship)
    AND current business policy allows visibility
~~~

Scope là một điều kiện **cần**, còn membership, ownership và trạng thái nghiệp vụ phải lấy từ DB hoặc policy service đáng tin.

### Không tin tenant do caller tự khai

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.test
X-Tenant-ID: tenant-red
Authorization: Bearer EXAMPLE_BLUE_USER_TOKEN
~~~

Header tenant có thể là routing hint, nhưng **không tự cấp quyền**. Server đối chiếu authenticated principal/client, tenant membership và ownership thực tế.

### Scope xuyên tenant có thể tồn tại không?

Có, cho support/admin được duyệt hoặc một workload nội bộ theo policy, nhưng cần:

- Client/service identity riêng và allowed tenant range.
- Reason code/ticket khi phù hợp.
- Step-up, approval, separation of duties.
- TTL ngắn, audit ở cấp record và alert truy cập bất thường.
- Explicit deny với đối tượng data classification đặc biệt.
- Review risk/privilege thường xuyên.

Tên scope có chữ all **không tự tạo quyền toàn cục** nếu RS chưa có quy tắc cụ thể.

## 17. Wildcards, string matching và policy ambiguity

Một số API định nghĩa scopes như:

~~~text
orders:*
admin
write
all
~~~

OAuth không cấm tên scope theo mẫu này, nhưng chúng dễ tạo quyền rất rộng và **lỗi matching** nếu mỗi API hiểu khác nhau.

### Sai lầm 1: substring matching

~~~java
// SAI: có thể nhận "not-orders:read" hoặc "orders:read:all".
if (scopeClaim.contains("orders:read")) {
    allowRead();
}
~~~

Đúng: parser scope theo token profile rồi kiểm **exact set membership**.

~~~text
Set<String> granted = parseGrantedScopes(verifiedAccessToken);

if (!granted.contains("orders:read")):
    DENY
~~~

RFC 6749 dùng các scope-token cách nhau bởi dấu cách trong scope parameter. Một số issuer phát JWT có **scope string** hoặc **scp array** tùy profile. RS phải theo agreement; không tự coi mọi claims đều là nguồn scope được phép và không nhập chuỗi tùy tiện.

### Sai lầm 2: prefix matching

~~~text
required = orders:read
granted = orders:read:all

if granted.startsWith(required):
    ALLOW
~~~

Một scope phân tầng không có quyền kế thừa mặc định chỉ từ dấu hai chấm. Nếu API hỗ trợ hierarchy/wildcards, cần **formal mapping policy**, review và negative tests.

### Sai lầm 3: case/normalization

Tên scope phải được so theo profile đã đăng ký. Không tự lowercase, strip prefix, bỏ dấu hoặc decode nhiều vòng nếu làm hai scope khác nhau thành một.

### Sai lầm 4: default grant

~~~text
if scope claim is missing:
    assume orders:admin
~~~

**Missing/invalid scope nên bị từ chối ở endpoint yêu cầu scope**, trừ khi một API có policy khác được định nghĩa rõ. Không bật quyền rộng như fallback khi claim bị thiếu.

## 18. Header/body do client khai không là quyền được cấp

Request nguy hiểm:

~~~http
POST /api/orders/123/approve HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_AT
X-User-Role: Admin
X-Requested-Scope: orders:approve
Content-Type: application/json

{"tenant_id":"tenant-blue","approved_by":"admin"}
~~~

Header và body do caller gửi **không phải trusted authorization assertions**.

RS phải dựa vào:

1. Access token hoặc introspection result đã verify/trust.
2. Authenticated client/principal.
3. DB hoặc authorization policy metadata đáng tin.
4. Delegation/approval state đã xác thực nếu hành động cần.

Nếu gateway truyền identity headers nội bộ:

- Không cho client Internet bypass gateway.
- Xóa hoặc ghi đè headers caller tự gán.
- Xác thực gateway→backend.
- Không để backend tin X-User-Role từ bất kỳ nguồn nào.
- Cân nhắc service-to-service mTLS và internal policy binding.

**Scope không thể được nâng chỉ bằng cách caller tuyên bố mình cần scope cao hơn.**

## 19. Authorization Server phải cấp scope theo deny-by-default

Một AS nên coi requested scope là **yêu cầu chưa được ủy quyền**, rồi tạo granted scopes từ chính sách tin cậy.

~~~text
1. Authenticate client nếu flow yêu cầu.
2. Validate grant type, redirect URI, PKCE và client binding.
3. Resolve client registration: allowed scopes/resources.
4. Resolve grant, user consent/entitlement khi áp dụng.
5. Resolve intended resource và audience policy.
6. Apply sensitive scope, tenant, time và risk limits.
7. Decide actual granted scopes (hoặc reject).
8. Persist grant/authorization theo lifecycle và transaction.
9. Mint token với granted scopes, aud, iss, typ, exp đúng.
10. Audit policy decision, không log raw access token.
~~~

### Pseudocode issuance

~~~text
function issue(request, authenticatedClient, trustedGrant):
    require client active and grant type allowed
    resource = resolveTrustedResource(request, client)
    require resource in client.allowedResources

    requested = parseScopeTokensStrictly(request.scope)
    require requested within client.allowedScopes
    require requested known for resource

    if grantType == authorization_code:
        require trusted authorization transaction
        grantedCeiling = persistedGrant.allowedScopes
        require subject/consent policy

    if grantType == client_credentials:
        grantedCeiling = workloadPolicy(client, resource)
        require no implicit end-user privileges

    if grantType == refresh_token:
        require RT active/bound to client
        grantedCeiling = originalGrant.allowedScopes
        require no new scope beyond original grant

    actual = applyIssuerPolicy(
        requested, grantedCeiling,
        client, resource, currentRisk
    )

    if actual not permitted:
        reject per OAuth/profile contract

    persist authorization context
    sign AT with actual scopes and specific audience
~~~

Đây là **mô hình policy minh họa**, không bắt buộc mọi AS phải reject toàn bộ request khi có scope ngoài allowlist: AS có thể thu hẹp theo hợp đồng hoặc từ chối. Điều bất biến là **client request không phải quyết định cấp quyền cuối cùng**.

### Default scope cần review

Sai:

~~~text
if request.scope empty:
    grant all scopes registered for client
~~~

Một AS có thể dùng default scope theo RFC 6749/policy, nhưng **không nên chọn mặc định quyền cao nhất**. Default phải được định nghĩa, giới hạn và kiểm thử.

## 20. Token claims: nguồn phạm vi phải đáng tin

JWT access token minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-101",
  "aud": "orders-api",
  "client_id": "dashboard-web",
  "scope": "orders:read",
  "iat": 1796000000,
  "exp": 1796000600
}
~~~

Đây là payload mô phỏng, không phải token được ký. Claims chỉ được tin sau JWT signature/key trust/issuer validation.

### Nguồn quyền có thể khác nhau

- **scope:** một chuỗi các scope-token cách nhau bằng dấu cách theo OAuth/JWT AT profile.
- **scp:** một số issuers dùng mảng hoặc dạng khác theo provider contract.
- **roles/permissions:** claims riêng, không tự đồng nghĩa OAuth scope.
- **authorization_details:** quyền có cấu trúc trong Rich Authorization Requests (RFC 9396) theo profile.
- **tenant_id/sub/client_id:** context để đánh giá resource permission, không tự trao mọi quyền.

**Đừng tự union scope, scp, roles và permissions thành tập quyền rộng nhất.** Nếu hệ thống dùng nhiều claims, phải có issuer-specific mapping và precedence rõ ràng.

Ví dụ:

~~~json
{
  "scope": "orders:read",
  "roles": ["ADMIN"]
}
~~~

Nếu Orders RS tự coi bất kỳ ADMIN role claim nào là orders:approve, nó có thể mở quyền dù AT chỉ được cấp read. Phải kiểm role claim **được phát cho đúng resource, từ issuer tin cậy và được local policy diễn giải đúng**.

### Chữ ký hợp lệ vẫn có thể chứa overgrant

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "orders-api",
  "sub": "user-read-only",
  "scope": "orders:approve"
}
~~~

Nếu AS bug cấp token như trên, chữ ký chỉ xác nhận AS đã ký claims đó. RS vẫn phải kiểm **principal được phép approve order hiện tại hay không**, và có thể tham vấn quyền hiện tại/denylist khi yêu cầu.

## 21. Java 17: kiểm exact scope membership

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

public final class ExactScopePolicy {

    private ExactScopePolicy() {}

    public static Set<String> parseScopes(String verifiedClaim) {
        if (verifiedClaim == null || verifiedClaim.isBlank()) {
            return Collections.emptySet();
        }

        String[] parts = verifiedClaim.trim().split(" +");
        Set<String> values = new HashSet<>(Arrays.asList(parts));

        for (String item : values) {
            if (item.isBlank() || item.length() > 128) {
                throw new IllegalArgumentException("Invalid scope");
            }
        }

        return Set.copyOf(values);
    }

    public static boolean containsExact(
            String verifiedScopeClaim, String required) {
        return parseScopes(verifiedScopeClaim).contains(required);
    }

    public static void main(String[] args) {
        if (!containsExact("orders:read orders:create", "orders:read")) {
            throw new AssertionError("Read must match");
        }
        if (containsExact("orders:read", "orders:approve")) {
            throw new AssertionError("Approve must not match");
        }
        if (containsExact("not-orders:read", "orders:read")) {
            throw new AssertionError("Substring confusion");
        }

        System.out.println("Exact scope tests PASS");
    }
}
~~~

### Giới hạn rõ ràng

- Tham số **verifiedScopeClaim** chỉ đến từ AT đã verify issuer/audience/signature/type; không lấy từ HTTP header.
- Parser chỉ minh họa **space-delimited scope**. scp arrays hoặc custom claims phải có parser riêng theo issuer profile.
- Cần giới hạn total token size, số scope tokens, syntax/length và trùng lặp theo policy.
- Không tự convert roles và client request thành scope.
- Exact membership chỉ kiểm một điều kiện; RS còn phải kiểm **tenant, ownership, resource state và operation-specific policy**.

**Sai:** dùng String.contains("orders:read") trên raw scope string, vì not-orders:read cũng chứa substring đó.

## 22. Spring Security: endpoint scope không thay object permission

Giả sử Spring Security Resource Server kiểm JWT access token cho Orders API. Nó cần **token validation**, **route scope check** và **business authorization**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/orders", "/api/orders/*")
                .hasAuthority("SCOPE_orders:read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/*/approve")
                .hasAuthority("SCOPE_orders:approve")
                .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
                jwt.jwtAuthenticationConverter(converter)));

        return http.build();
    }
}
~~~

Cấu hình này mới minh họa **route-level exact scope**. Nó chưa tự kiểm subject được phép approve một order cụ thể, chưa mô tả CSRF/session của ứng dụng, và chưa cấu hình JWT decoder.

### JwtDecoder kiểm issuer/audience

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://identity.example.test";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(
                "https://identity.example.test/.well-known/jwks.json")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience));

    return decoder;
}
~~~

Ví dụ cần đặt trong @Configuration class; còn thiếu **token type/profile, revocation, claims bắt buộc và domain authorization**. JWKS URI, algorithms và issuer phải khớp hệ thống thật, không lấy từ header jku do token tự khai.

### Những lỗi cần tránh

- Dùng default **authenticated()** cho mọi POST route thay vì scope chính xác.
- Cho một route matcher rộng che mất rule nhạy cảm phía sau.
- Map cả roles/permissions ngoài issuer profile thành authorities mạnh.
- Bỏ audience hoặc token type để chấp nhận JWT từ mọi API cùng issuer.
- Cho client_credentials principal mặc định có user admin privileges.
- Coi authority SCOPE_orders:approve là bằng chứng user được approve **mọi đơn**.

API Spring Security/Nimbus có thể khác theo dependency versions; phải compile/test trên stack thực tế. Với opaque token, dùng introspection + authority mapping đúng contract thay JWT decoder.

## 23. Resource-level authorization và TOCTOU

Method-level policy minh họa:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

public final class OrderApplicationService {

    private final OrderRepository repository;
    private final OrderAuthorizationPolicy policy;

    public OrderApplicationService(
            OrderRepository repository,
            OrderAuthorizationPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders:approve') " +
        "and @orderPolicy.canApprove(authentication, #p0)"
    )
    public void approve(String orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);

        // Trong production: DB transaction, locking/version check.
        policy.assertCanApproveCurrentOrder(order);
        order.approve();
        repository.save(order);
    }
}
~~~

Đây là **mô hình pseudo-Java**, chưa compile độc lập vì repository, domain entities và Spring bean **orderPolicy** là các thành phần do ứng dụng định nghĩa.

### canApprove phải xét gì?

~~~text
principal/client has authenticated context
AND access token contains exact orders:approve scope
AND principal is member of order tenant
AND business role/permission permits approval
AND principal is not self-approving if SoD forbids it
AND order current state can be approved
AND amount/approval limits are satisfied
~~~

RS nên kiểm current order state **trong transaction** để tránh time-of-check/time-of-use race. Không tin tenant/owner/role do caller gửi trong JSON body.

### Phản hồi 401 và 403

- **401** khi credential thiếu/invalid theo Bearer authentication.
- **403** khi principal đã xác thực nhưng thiếu scope/permission.
- Theo RFC 6750, Bearer RS có thể dùng **insufficient_scope** trong WWW-Authenticate khi token không đủ scope, không tiết lộ chi tiết nhạy cảm của tenant hoặc record khác.

**Route scope check ngăn call thiếu quyền tối thiểu; object-level policy quyết định action trên tài nguyên cụ thể.**

## 24. JWT, opaque, JWE, DPoP và mTLS có giải quyết over-privilege không?

| Bảo vệ | Có thể giúp | Không tự giải quyết |
| --- | --- | --- |
| **JWS/signed JWT** | Xác minh issuer và integrity của claims. | AS đã ký một scope quá quyền, RS tin sai nghiệp vụ. |
| **Opaque AT + introspection** | RS hỏi AS về active/scope theo contract. | AS cấp metadata overgrant hoặc RS không kiểm resource. |
| **JWE** | Bảo vệ confidentiality của token claims. | Token vẫn có scope quá quyền và có thể bị replay nếu Bearer. |
| **Short AT lifetime** | Giảm thời gian quyền rộng có thể bị lạm dụng. | Ngăn request sai trong thời gian token còn hiệu lực. |
| **RT rotation** | Phát hiện reuse của refresh token đã tiêu thụ. | Ngăn scope inflation trong refresh nếu policy cấp token sai. |
| **DPoP** | Giảm nguy cơ kẻ chỉ sao chép AT dùng được token. | Chặn holder đã được cấp scope quá quyền hoặc attacker có cả holder key. |
| **mTLS-bound AT** | Ràng token với client certificate. | Giảm quyền của client đã được cấp sai. |
| **Token revocation** | Có thể chặn token/grant quá quyền trước exp khi RS biết state. | Tự sửa issuance bug khiến AS tiếp tục cấp mới. |
| **RBAC/ABAC/ReBAC** | Kiểm subject, tenant, object, action ở RS. | Tự làm hẹp client registration ở AS. |
| **Key rotation** | Xử lý sự cố signing key khi thực sự cần. | Thu hẹp scope sai mà không sửa policy. |

**Cryptography giữ token đáng tin về mặt kỹ thuật; least-privilege policy quyết định token ấy được phép làm gì.**

### Sender-constrained token vẫn có thể over-privileged

DPoP-bound AT scope payments:refund chỉ được dùng với key holder hợp lệ, nhưng nếu **client thật được cấp refund không cần thiết**, hoặc attacker chiếm cả client runtime và private key, sender binding không chặn hành động quá quyền.

### Offline JWT và thay đổi policy

JWT RS verify offline có thể chưa biết user mất role hoặc grant bị thu hồi. Nếu high-risk permission cần đổi ngay, cân nhắc:

- AT lifetime ngắn tương xứng rủi ro.
- Online authorization/ABAC check theo current DB state.
- Token/grant version, denylist hoặc introspection với propagation SLO.
- Sender-binding và client security để giảm replay.
- Audit hoạt động quyền cao theo issuer/client/principal/resource.

### Không lẫn token format với security architecture

Một opaque token có thể mang scope quá rộng qua introspection. Một JWE có thể giấu scope nhưng không giảm quyền. Một JWT có thể mang scope hẹp và được RS thực thi tốt. **Định dạng token không tự xác định chính sách quyền**.

## 25. Đánh giá rủi ro theo blast radius

Severity của over-privileged scope không chỉ dựa vào số scope names mà phụ thuộc **năng lực thực tế** và khả năng attacker tận dụng.

### Ma trận đánh giá

| Yếu tố | Rủi ro thấp hơn | Rủi ro cao hơn |
| --- | --- | --- |
| **Hành động** | Read dữ liệu ít nhạy cảm. | Refund, admin, delete, security settings. |
| **Resource** | Một resource/audience cụ thể. | Nhiều APIs hoặc toàn tổ chức. |
| **Tenant** | Bound một tenant nhỏ. | Cross-tenant/global. |
| **Token lifetime** | AT ngắn, revocation khả thi. | AT dài, offline cache khó revoke. |
| **Credential storage** | BFF/secure store với access hạn chế. | Browser storage/logs/CI artifact có rủi ro lộ. |
| **Sender constraint** | DPoP/mTLS đúng profile. | Bearer token dễ replay khi bị copy. |
| **Client identity** | Một workload riêng, ít service. | Credential dùng chung nhiều services. |
| **RS policy** | Scope + object-level authorization. | Chỉ kiểm signature hoặc wildcard scope. |
| **Audit** | Có quyết định và log resource-level. | Không thể xác định actor/action/tenant. |
| **Revocation** | Có SLO rõ, RS đồng bộ state. | Không có cách rút token trước exp. |

Các cột là **định hướng định tính**, không phải điểm số chuẩn. Một scope read dữ liệu mật có thể rất nguy hiểm; một quyền write hạn chế có thể ít rủi ro hơn. Cần xét **data classification, business impact, exposure và attacker capabilities**.

### Ví dụ blast radius

~~~text
AT A:
    scope = orders:read
    aud = orders-api
    tenant = tenant-blue
    ttl = 5 phút

AT B:
    scope = orders:read orders:approve orders:refund
    aud = orders-api + payments-api
    tenant = all
    ttl = 24 giờ
~~~

Nếu cả hai bị đánh cắp, **AT B có phạm vi rủi ro lớn hơn** khi RS thực thi các quyền đó. Giảm scope, audience, tenant và thời hạn giúp giảm năng lực mà attacker thừa hưởng.

### Chú ý quyền gián tiếp

Một scope trông vô hại có thể gọi API export dữ liệu hàng loạt hoặc trigger một workflow chạy với quyền cao khác. Review phải nhìn **call graph và side effects**, không chỉ tên scope.

## 26. Phát hiện scope drift và overgrant trong vận hành

Một hệ thống cần phát hiện:

- Client đột nhiên xin scope nhạy cảm chưa từng dùng.
- Client registration được sửa để thêm write/admin.
- Token response chứa scope ngoài original grant/allowlist.
- Access token phát cho sai audience/resource.
- Cùng client_id nhận scopes rất khác giữa environments hoặc giữa AS instances.
- Mức sử dụng approve/refund tăng đột biến sau deploy.
- Token từ client_credentials lại được chấp nhận trên route chỉ dành cho delegated user.
- Một số RS replicas chấp nhận scope khi replicas khác từ chối.
- Scope wildcard, missing-claim default hoặc role-to-scope mapping bị bật sau update.
- Grant đã revoke nhưng RT vẫn mint token cùng quyền cũ.
- Token exchange đầu ra có permissions ngoài delegation contract.

### Event names minh họa

~~~text
OAUTH_SCOPE_REQUESTED_OUTSIDE_CLIENT_ALLOWLIST
OAUTH_SCOPE_GRANTED_OUTSIDE_GRANT
OAUTH_SCOPE_GRANTED_OUTSIDE_RESOURCE_POLICY
OAUTH_SENSITIVE_SCOPE_GRANTED
OAUTH_SCOPE_INFLATION_BLOCKED
OAUTH_REFRESH_SCOPE_ESCALATION_DENIED
OAUTH_TOKEN_EXCHANGE_SCOPE_ESCALATION_DENIED
OAUTH_ACCESS_TOKEN_WRONG_AUDIENCE
RS_INSUFFICIENT_SCOPE
RS_RESOURCE_LEVEL_PERMISSION_DENIED
RS_CROSS_TENANT_AUTHORIZATION_DENIED
RS_SCOPE_MAPPING_POLICY_MISMATCH
CLIENT_SCOPE_REGISTRATION_CHANGED
SENSITIVE_SCOPE_APPROVAL_REQUIRED
TOKEN_OVERGRANT_INCIDENT_CONFIRMED
~~~

Đây chỉ là **tên telemetry nội bộ**, không phải OAuth error codes chuẩn.

### Metrics và các câu hỏi

| Metric | Câu hỏi |
| --- | --- |
| **scope_request_reject_rate** | Client nào thường xin scope ngoài allowlist? |
| **scope_grant_delta** | Scope đã cấp có khác intended grant/resource policy không? |
| **sensitive_scope_issuance** | Bao nhiêu AT mang approve/refund/admin được phát? |
| **client_scope_registration_changes** | Client nào được mở thêm quyền, ai phê duyệt? |
| **refresh_scope_escalation_attempts** | Có request RT cố xin quyền vượt original grant? |
| **token_exchange_grant_delta** | Output delegation có quá rộng không? |
| **cross_resource_denials** | AT sai audience đang được gửi tới API nào? |
| **tenant_permission_denials** | Có cố truy cập record ngoài tenant không? |
| **authorization_policy_version_skew** | Có RS/AS replica đang chạy policy version cũ? |
| **revocation_enforcement_lag** | Sau overgrant incident, AT còn được chấp nhận bao lâu? |

### Log an toàn

Một audit decision có thể chứa:

~~~json
{
  "event": "OAUTH_SCOPE_GRANTED_OUTSIDE_CLIENT_ALLOWLIST",
  "request_id": "example-req-78",
  "issuer": "https://identity.example.test",
  "client_id": "orders-dashboard",
  "resource": "orders-api",
  "requested_scopes": ["orders:read", "orders:refund"],
  "granted_scopes": ["orders:read"],
  "policy_version": "orders-policy-v4",
  "decision": "NARROWED"
}
~~~

Không log raw AT/RT, client secret, Authorization header, PII không cần thiết hoặc private key. Nếu scopes chứa thông tin nhạy cảm qua custom naming, giới hạn quyền xem/retention và tránh dùng giá trị không kiểm soát làm high-cardinality metrics labels.

### Detect drift giữa nhiều replicas

Nếu một RS chỉ kiểm orders:read để approve còn replica khác yêu cầu orders:approve, các request có thể nhận kết quả ngẫu nhiên. Review **configuration consistency**, route patterns và policy versions cho tất cả replicas/regions, không chỉ test một node.

## 27. Ứng phó sự cố khi AT đã được cấp scope quá quyền

Khi phát hiện một AS hoặc RS cho phép scope quá rộng, nên xử lý như **authorization incident** có khả năng lộ hoặc sửa dữ liệu, không chỉ đổi một cấu hình rồi bỏ qua tokens đã phát.

### Playbook

~~~mermaid
flowchart TD
    A["Phát hiện overgrant hoặc RS scope bypass"] --> B["Tạo incident, xác minh issuer/client/resource/scope"]
    B --> C["Xác định root cause: registration, consent, AS issuance, RS enforcement"]
    C --> D["Chặn phát token quyền cao mới"]
    D --> E["Sửa RS authorization và kiểm routes/object policy"]
    E --> F["Revoke token/grant/RT family chịu ảnh hưởng theo scope"]
    F --> G["Kiểm RS đã từ chối token quyền cao cũ"]
    G --> H["Điều tra activity, tenant/data impact"]
    H --> I["Khôi phục grant tối thiểu và vận hành bình thường"]
    I --> J["Audit, regression tests, postmortem"]
~~~

### Bước 1 — Xác định phạm vi

- **Issuer**, client_id, subject/client principal, grant_id và token profile.
- **Sensitive scopes** bị cấp sai, resource/audience và tenants liên quan.
- **Thời gian lỗi** bắt đầu/kết thúc, key version và AS policy version.
- Các AT đã mint trong khoảng lỗi, TTL tối đa, RS caches/replicas.
- RT families, consent/grants và token exchange descendants có thể tiếp tục mint AT.
- API calls thực tế đã dùng quyền cao, resource IDs và dữ liệu bị tác động.
- Có kèm token theft, client credential leak hoặc chỉ cấu hình issuance/RS bug?

Không gửi raw bearer tokens hoặc secrets qua incident chat để điều tra. Dùng audit identifiers, token fingerprints được bảo vệ và truy vấn issuance ledger có phân quyền.

### Bước 2 — Chặn nguồn phát tiếp

- Disable/rollback client registration scope overgrant.
- Sửa token issuance để scope chỉ lấy từ **authorized grant**, không từ raw requested parameter.
- Dừng refresh/token exchange escalation.
- Cập nhật RS route/object policy nếu có authorization bypass.
- Nếu client compromised, revoke client credentials và hạn chế grant.
- Nếu AS signer/key bị compromise thật, có thể cần **key revocation**, nhưng không tự revoke signing key khi vấn đề chỉ là scope policy.

### Bước 3 — Xử lý tokens và grants đã phát

**Sửa issuance bug không làm token quyền cao đã phát tự hết hạn**. Cần quyết định:

- Revoke affected **opaque tokens** trong AS store.
- Với JWT self-contained, RS cần denylist/token version/introspection hoặc cơ chế offline revocation phù hợp.
- Revoke/narrow **refresh-token families/grants** có khả năng mint thêm AT sai.
- Buộc reauthorization/reconsent hoặc reauthentication khi yêu cầu.
- Cân nhắc short-term resource API blocks cho hành động high-risk khi propagation chậm.
- Đo actual enforcement ở tất cả RS/gateway/replicas.

### Bước 4 — Khôi phục

- Client chỉ xin scopes cần thiết.
- AS phát đúng scope/audience/TTL sau security review.
- RS kiểm scopes và object permission đúng qua integration tests.
- Cấp lại grants/tokens tối thiểu khi đã an toàn.
- Kiểm không còn overprivileged AT được mint/accepted sau change.
- Theo dõi affected client versions và false positives do policy thu hẹp.

### Bước 5 — Postmortem

Phân biệt root cause:

| Root cause | Cải tiến cần làm |
| --- | --- |
| Client registration quá rộng | Access review, registration approval, scope inventory. |
| Consent UI xin sai scope | Incremental consent, UX clarity, review request templates. |
| AS dùng requestedScope thay grantedScope | Issuance invariants, policy engine tests. |
| Refresh/token exchange escalation | Grant lineage checks, delegation tests. |
| RS thiếu route/method check | Central policy, deny-all defaults, API contract tests. |
| RS thiếu tenant/object-level permission | Domain authorization service và IDOR/BOLA tests. |
| Token revocation truyền chậm | SLO, revocation state propagation và runbook. |

**Không xem incident kết thúc khi một database row đã được sửa**; cần xác nhận token cũ bị giới hạn theo yêu cầu và những authorization decisions sai không còn xảy ra.

## 28. Các tình huống đe dọa thực tế

### Case A — Dashboard read-only được cấp refund

**Bối cảnh:** Dashboard chỉ liệt kê Orders, nhưng AS phát AT có orders:read và payments:refund do client registration copypaste.

**Rủi ro:** Bearer AT bị lộ từ browser/log có thể dùng gọi Payments refund endpoints nếu audience/authorization bị nới rộng.

**Bảo vệ:** client allowlist theo tính năng; AS cấp đúng scope/audience; Payments kiểm aud, refund scope và business permissions. Revoke các token overgrant đã phát.

### Case B — User role Approver tự biến thành mọi client scope

**Bối cảnh:** User có role Approver trong admin portal. AS tự lấy mọi user role rồi gắn orders:approve vào AT của một mobile read-only app.

**Lỗi:** quyền của principal bị **nhầm** với quyền được grant cho OAuth client.

**Bảo vệ:** giao của client registration, grant/consent, subject permissions và resource policy; mobile app chỉ nhận orders:read nếu đó là authorization.

### Case C — Consent phishing

**Bối cảnh:** App bên thứ ba hứa hiển thị trạng thái đơn, nhưng xin orders:approve, orders:refund và offline_access.

**Rủi ro:** User cho phép quyền không hiểu rõ; RT có thể duy trì quyền rộng.

**Bảo vệ:** sensitive scope review/consent UX, incremental authorization, grant inventory, ability to revoke consent, scope exposure monitoring.

### Case D — Client Credentials super-client

**Bối cảnh:** Năm batch jobs dùng cùng client_id và client secret, được đăng ký payments:approve, users:admin, reports:read.

**Rủi ro:** Chiếm một job/report exporter có thể dùng quyền của tất cả jobs.

**Bảo vệ:** tách client identity theo workload, scope/resource allowlist riêng, client key custody, short TTL và alerts.

### Case E — Refresh escalation

**Bối cảnh:** RT family ban đầu cấp orders:read, nhưng token endpoint cho RT xin orders:approve.

**Lỗi:** token endpoint dùng requested scope thay original grant scopes.

**Bảo vệ:** enforce refresh scope không vượt original authorization/current policy; require fresh grant update cho scope cao.

### Case F — Token exchange privilege inflation

**Bối cảnh:** Frontend AT read-only được trao đổi thành payments:refund AT không qua delegation check.

**Bảo vệ:** actor/subject/resource/delegation policy, output audience cụ thể, RS kiểm permission; không cho client tự chọn scope output.

### Case G — Scope-name collision giữa APIs

**Bối cảnh:** Orders và Payments đều có write. Payments chấp nhận Orders AT vì issuer/signature đúng và không kiểm audience.

**Bảo vệ:** exact audience/resource validation, profile scopes có namespace và local policy mapping.

### Case H — orders:read được coi khớp not-orders:read

**Bối cảnh:** RS dùng string.contains("orders:read") trên scope claim thô.

**Lỗi:** substring matching làm sai semantics, attacker có token chứa một scope khác nhưng vẫn qua read check.

**Bảo vệ:** parse strict thành scope-token set, exact membership, property-based/fuzz tests.

### Case I — Tenant header spoofing

**Bối cảnh:** User tenant-blue có orders:read; request header X-Tenant-ID=tenant-red khiến API trả dữ liệu red.

**Lỗi:** RS lấy tenant từ caller input thay authenticated principal và order ownership.

**Bảo vệ:** authenticated tenant context, trusted DB membership, row-level isolation và cross-tenant negative tests.

### Case J — ID token confusion

**Bối cảnh:** Dashboard gửi ID token chứa email/roles đến Orders; Orders chỉ verify cùng issuer key và kiểm role.

**Lỗi:** nhận sai token type và audience; ID token không phải Orders AT.

**Bảo vệ:** OAuth access-token profile/typ/aud, explicit scopes và resource-level checks; không nhận ID token cho API.

### Case K — Scope admin wildcard sau deploy

**Bối cảnh:** API đổi matcher từ exact orders:approve thành prefix orders:* mà không review.

**Rủi ro:** Nhiều token dùng trước đó có thêm năng lực ngoài dự kiến, dù AS không đổi.

**Bảo vệ:** policy versioning, change review, negative tests, canary và alert scope mapping drift.

### Case L — Token hợp lệ nhưng đơn tự duyệt

**Bối cảnh:** User có orders:approve và phê duyệt một order do chính mình tạo, trái quy định separation of duties.

**Lỗi:** kiểm scope đúng nhưng thiếu business policy.

**Bảo vệ:** method-level permission + current resource owner/state + distinct approver requirement trong transaction.

### Case M — Token lộ và scope rộng

**Bối cảnh:** Một bearer AT có reports:read và user:admin được ghi vào application log.

**Rủi ro:** attacker dùng nguyên token, không cần giả chữ ký hoặc giải mã JWE.

**Bảo vệ:** redact tokens, scope/aud minimization, short TTL, sender-binding khi phù hợp, revocation và điều tra.

### Case N — Client mất quyền nhưng JWT còn hạn

**Bối cảnh:** Admin rút orders:approve khỏi user. Một JWT phát trước đó vẫn chứa approve và RS verify offline.

**Rủi ro:** request approve vẫn có thể chạy đến exp nếu RS chỉ kiểm signature/scope claim cũ.

**Bảo vệ:** resource-level current permission, token/grant revocation hoặc online authorization checks theo SLA.

### Case O — BFF confused deputy

**Bối cảnh:** BFF có internal payments:refund token. Caller chỉ có orders:read nhưng lừa BFF gọi refund API.

**Bảo vệ:** BFF kiểm user/client authority trước downstream call, không dùng privileged credential để thực thi yêu cầu không được ủy quyền.

### Case P — Admin role claim trong wrong tenant

**Bối cảnh:** Token có role=Admin của tenant-blue nhưng API xem nó như global Admin để sửa dữ liệu tenant-red.

**Bảo vệ:** role issuer+tenant scoping, object-level tenant policy, không nâng scope từ role string không rõ context.

### Case Q — Opaque introspection trả scope rộng

**Bối cảnh:** AS store đánh dấu opaque AT có orders:approve sai; RS introspect active=true và chấp nhận.

**Kết luận:** opaque token không phòng được AS overgrant. Cần sửa metadata/policy, revoke token và kiểm quyền RS.

### Case R — Permission được “nới” qua đường phụ

**Bối cảnh:** Chính endpoint POST /approve có check orders:approve, nhưng một endpoint /bulk-update không có scope policy vẫn thay trạng thái order thành Approved.

**Bảo vệ:** API inventory/call graph, kiểm mọi write paths, method/object authorization tests và deny by default.

**Bài học chung:** over-privileged scope thường đi cùng **một lỗi phụ** ở client registration, issuance, audience, tenant boundary hoặc RS enforcement. Nhiều lớp kiểm giúp hạn chế hệ quả khi một lớp sai.

## 29. Negative tests cho over-privileged scope

Kiểm thử nên dùng **test clients, synthetic token claims, dữ liệu tenant giả và keys kiểm thử được phép**, không dùng raw credential production. Ngoài HTTP status, hãy kiểm **không có side effect** và không có token/grant overprivileged được phát hành.

| Kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **Read-only client request read** | Client chỉ allowed orders:read, xin read. | Có thể cấp read nếu grant/policy phù hợp. |
| **Read-only client request approve** | Client chỉ allowed read, xin approve. | AS từ chối hoặc không cấp approve theo contract. |
| **Read-only client request refund** | Client xin payments:refund không đăng ký. | AS không cấp. |
| **Empty scope default** | Client không gửi scope. | Không tự cấp all/admin; áp default policy an toàn. |
| **Requested raw scope copied** | Input scope khác persisted grant. | Token dùng actual granted scope, không raw request. |
| **Consent withheld** | User không chấp thuận sensitive scope. | AS không cấp scope đó. |
| **Consent display mismatch** | UI hiển thị read nhưng token chứa write. | Test phát hiện issuance bug. |
| **User lacks approver role** | Client được xin approve, subject không có authority. | AS không cấp approve hoặc RS từ chối theo policy. |
| **User role revoked** | Existing JWT còn approve, user mất role. | RS/current policy hoặc revocation control chặn theo SLA. |
| **Client registration changed** | Allowed approve bị rút. | New issuance không còn approve; xử lý grants cũ theo policy. |
| **Staging scope in prod** | Client/token staging được dùng production. | Issuer/resource/client policy từ chối. |
| **Wrong grant type** | Read-only mobile xin client_credentials trái registration. | AS từ chối. |
| **User-only scope via client_credentials** | Service principal xin quyền chỉ cho delegated user. | AS từ chối nếu policy không cho machine access. |
| **Machine scope cross workload** | Reports workload xin payments:approve. | AS từ chối. |
| **Shared super-client** | Job A dùng quyền Job B không cần. | Security review/test phát hiện registration overgrant. |
| **Refresh scope expansion** | Original grant read, RT xin read+approve. | AS không cấp approve. |
| **Refresh after consent revoke** | Original grant approve đã bị rút. | AS không mint AT approve theo current policy. |
| **Refresh token family compromised** | RT reuse, family bị revoke. | Không mint AT mới, kể cả scope read. |
| **Token exchange escalation** | Input orders:read, output payments:refund không có delegation. | Exchange bị từ chối. |
| **Token exchange allowed mapping** | Valid delegated workflow được duyệt. | Chỉ cấp output scope/audience theo trusted policy. |
| **Confused deputy BFF** | Caller read-only yêu cầu BFF hoàn tiền bằng service credential. | BFF từ chối trước downstream call. |
| **Wrong audience** | Orders AT gửi Payments. | Payments từ chối dù signature đúng. |
| **Multi-audience unauthorized** | AT gửi tới API ngoài aud set. | Từ chối. |
| **Wrong issuer** | AT hợp lệ của issuer B gửi tới Orders tin issuer A. | Từ chối. |
| **ID token as access token** | OIDC ID token gửi Orders. | Từ chối token type/profile. |
| **Unsigned JWT** | alg=none gửi route cần JWT AT. | Từ chối. |
| **Unknown signing key** | kid không thuộc issuer trust set. | Từ chối, không fetch untrusted jku. |
| **JWT expired** | AT có exp quá hạn. | Từ chối. |
| **JWT nbf future** | AT chưa có hiệu lực. | Từ chối. |
| **Opaque AT overgrant** | Introspection trả scope rộng sai. | Test phát hiện AS metadata/RS authorization bug. |
| **Scope claim missing** | Endpoint yêu cầu orders:read nhưng token thiếu scope. | Từ chối, không default admin. |
| **Empty scope string** | Claim scope="" gửi approve. | Từ chối. |
| **Scope read vs approve** | Token chỉ read gọi approve. | 403/insufficient_scope theo contract. |
| **Scope approve vs refund** | Token chỉ approve gọi refund. | Từ chối. |
| **Scope substring** | Claim not-orders:read, require orders:read. | Từ chối. |
| **Scope prefix** | Claim orders:read:all, require orders:read. | Không tự chấp nhận nếu policy không định nghĩa hierarchy. |
| **Scope wildcard** | Claim orders:*, require orders:refund. | Chỉ nhận nếu explicit reviewed mapping; mặc định từ chối. |
| **Case mismatch** | Scope dùng chữ hoa/thường khác profile. | Exact profile matching, không tự normalize nguy hiểm. |
| **Duplicate scope tokens** | Claim lặp scope nhiều lần. | Parser xử lý nhất quán, không tăng quyền. |
| **Malformed scope claim** | Scope ở dạng type sai/ký tự/size ngoài profile. | Từ chối hoặc bỏ quyền theo safe policy, không cấp rộng. |
| **scope vs scp conflict** | scope=read, scp=[approve] từ provider không được map. | Không union hai nguồn trái policy. |
| **roles used as scopes** | scope=read, roles=[ADMIN]. | Không tự cấp approve khi thiếu policy rõ. |
| **Missing principal** | Token machine không có end-user identity. | Không fail open thành global admin. |
| **Wrong client_id claim** | Token/client mismatch với grant. | Từ chối theo token/client binding profile. |
| **Tenant header injection** | Header X-Tenant-ID tự khai tenant khác. | Không mở quyền dữ liệu tenant đó. |
| **Tenant path substitution** | User blue request order tenant-red. | 403/404 theo privacy contract, không trả data. |
| **Record ownership violation** | Scope read đúng nhưng record private của người khác. | Từ chối. |
| **Self-approval** | Approver tự duyệt order do chính mình tạo khi SoD cấm. | Từ chối. |
| **Wrong order state** | Order đã canceled nhưng caller có approve. | Từ chối. |
| **Refund limit exceeded** | Có refund scope nhưng số tiền vượt policy. | Từ chối hoặc yêu cầu approval mới. |
| **Route missing scope check** | Một alternate endpoint thực hiện approve. | Test phát hiện, default-deny. |
| **HTTP method bypass** | GET route bảo vệ read, POST cùng path chỉ authenticated(). | POST bị bảo vệ theo action scope. |
| **Bulk endpoint bypass** | /bulk-update không kiểm write permission. | Từ chối hoặc kiểm từng object/action. |
| **GraphQL resolver bypass** | Resolver mutating không áp operation-level scope. | Từ chối; authorization ở resolver/domain layer. |
| **Gateway header spoof** | Client tự gửi X-User-Role=Admin. | Backend không tin header untrusted. |
| **Gateway bypass** | Truy cập backend trực tiếp tránh scope check. | Network/auth boundary từ chối. |
| **RS replica policy drift** | Replica A yêu cầu approve, B chỉ authenticated. | Deployment/test phát hiện mismatch. |
| **Sensitive scope spike** | Deploy khiến issuance approve tăng bất thường. | Alert/rollback/review. |
| **Bearer token replay** | Attacker sao chép AT read+refund. | Phơi bày blast radius; sender binding/revoke theo threat model. |
| **DPoP bound AT wrong key** | Token có refund scope nhưng proof key không khớp. | Từ chối sender binding. |
| **mTLS bound AT wrong cert** | Token có approve nhưng certificate mismatch. | Từ chối. |
| **Old JWT after revoke** | Token quyền cao đã revoked nhưng còn exp. | RS enforcement đạt SLO, không tiếp tục nhận. |
| **RT still minting after incident** | AS fix AT issuance nhưng RT grant chưa thu hồi. | Không mint overgrant; xử lý affected grant. |
| **Unknown jti denylist injection** | Attacker tự khai jti/family ID của người khác. | Không revoke đối tượng theo input chưa xác thực. |
| **Overgrant logs raw token** | Event logging ghi bearer AT/RT. | Secret scanning/redaction fail gate. |
| **Untrusted requested resource** | Client đổi resource sang API nhạy cảm ngoài registration. | AS từ chối resource/audience escalation. |
| **Cross-tenant admin role** | Role Admin tenant A dùng trên tenant B. | Domain authorization từ chối. |
| **Approval state race** | Resource đổi trạng thái giữa policy check và commit. | Transactional re-check ngăn sai quyền. |

### Bộ test tối thiểu cho CI

~~~text
1. Client only allowed orders:read cannot obtain orders:approve.
2. Original RT grant orders:read cannot refresh into orders:approve.
3. Client Credentials reports-only cannot obtain payments:refund.
4. Orders RS rejects Payments audience even with valid signature.
5. Orders approve route rejects read-only AT.
6. Approve-scope AT still cannot approve another tenant's order.
7. Admin role claim not scoped to Orders does not imply approve.
8. Missing/malformed scope is not treated as wildcard/admin.
9. Old overgrant token is rejected after revocation policy propagation.
10. All AS/RS replicas enforce the same policy version.
~~~

**Kiểm end-to-end phải xác nhận cả quyết định AS lẫn quyết định RS và side effects của nghiệp vụ**, không chỉ test parser scope.

## 30. Checklist production: giảm over-privileged scope

1. **API inventory:** Mọi API, method, resolver và background operation có scope/authorization contract?
2. **Scope semantics:** Các scope names được định nghĩa rõ theo hành động, resource và đối tượng?
3. **Least privilege:** Mỗi client chỉ đăng ký scopes cần cho tính năng thật?
4. **Client separation:** Không dùng chung super-client giữa workloads hoặc tiers khác nhau?
5. **Grant types:** Client chỉ được dùng những OAuth flows phù hợp?
6. **Sensitive scope review:** Scope admin, approve, delete, refund có approval/owner?
7. **Default scope:** Request thiếu scope không được biến thành grant tất cả quyền?
8. **Requested vs granted:** AS phân biệt client yêu cầu với quyết định đã cấp?
9. **Consent:** User nhìn thấy quyền đúng và scope nhạy cảm được xử lý phù hợp?
10. **Consent limits:** User không thể consent quyền ngoài user/client/resource policy?
11. **Grant persistence:** AS lưu scopes thực sự được cấp theo client/subject/resource?
12. **Token issuance:** Token claims chỉ mang granted scope, không raw requested scope?
13. **Granted scope response:** Client có thể xác định scope thực sự được cấp?
14. **Resource indicators:** AS kiểm resource/audience mà client được yêu cầu?
15. **Audience:** RS chỉ nhận AT dành cho chính nó?
16. **Token type:** ID token, access token và client assertions không bị dùng lẫn?
17. **Issuer trust:** RS verify correct issuer/JWKS/algorithm allowlist?
18. **Scope parser:** Exact token membership, không substring/prefix vô tình?
19. **Scope claim shape:** Parser theo issuer profile, không tự union scope/scp/roles?
20. **Missing claim:** Không fail-open khi token thiếu scope cần thiết?
21. **Role mapping:** Role/permission được xét trong đúng issuer/tenant/resource context?
22. **Client Credentials:** Service principal không tự thành user admin?
23. **Workload registration:** Client Credentials scopes/resources được giới hạn riêng?
24. **Refresh:** Không thể xin thêm scope ngoài original grant hoặc current policy?
25. **RT grant revocation:** Rút consent/role ảnh hưởng AT mới phát đúng policy?
26. **Token exchange:** Output scope/audience cần delegation authorization rõ?
27. **Confused deputy:** BFF không dùng quyền riêng để làm action caller không được phép?
28. **Object-level check:** Scope không thay ownership/tenant/resource authorization?
29. **Tenant isolation:** Tenant hint từ client không tự cấp quyền?
30. **Separation of duties:** Quyền approve/refund có policy chống self-approval khi cần?
31. **Business state:** Quyền còn phụ thuộc trạng thái record, amount, limit và workflow?
32. **Concurrency:** Authorization được kiểm lại trong transaction khi TOCTOU nguy hiểm?
33. **Method-level rules:** GET/POST/PATCH/DELETE và bulk endpoints có policy riêng?
34. **GraphQL/gRPC/jobs:** Các đường thực thi ngoài REST cũng được kiểm quyền?
35. **Default deny:** Endpoint/resolver không đăng ký policy bị từ chối?
36. **Gateway trust:** Không có backend bypass hoặc forged identity headers?
37. **AT TTL:** Sensitive scopes có lifetime/risk controls phù hợp?
38. **Sender constraints:** DPoP/mTLS khi cần giảm token replay risk?
39. **Revocation:** Có cách rút AT/grant/RT đã cấp sai trong SLO?
40. **Policy drift:** Mọi AS/RS replicas dùng cùng reviewed policy version?
41. **Observability:** Có metrics về overgrant, scope request rejects và sensitive actions?
42. **Audit:** Ghi issuer/client/grant/resource/action decision mà không log bearer token raw?
43. **Privacy:** Token/user/tenant metadata có retention và access controls?
44. **Client registration change:** Có owner, approval và rollback cho tăng quyền?
45. **Security testing:** Negative tests cho scope inflation, cross-resource, cross-tenant?
46. **Production probe:** Có kiểm thực tế các high-risk routes với low-privilege token?
47. **Incident plan:** Có runbook revoke overgrant tokens/grants và chặn issuance bug?
48. **Periodic review:** Scopes không còn dùng được thu hồi, sensitive scopes được recertify?

### Checklist dành cho thiết kế scope mới

Trước khi thêm một scope, team API nên trả lời:

~~~text
What action does it permit?
What resource and data category does it cover?
Does it include bulk/admin effects?
Which clients may request it?
Does delegated user authority matter?
Which audiences may receive it?
What exact object/tenant check is still required?
What token lifetime/revocation behavior is appropriate?
Who approves changes and audits usage?
How are negative tests written?
~~~

Nếu không trả lời được, **chưa nên mở một scope quyền cao** chỉ vì API route cần cách phân biệt client.

## 31. Bài tập vận dụng

### Bài tập 1 — Granted scope không phải requested scope

Một client registered only orders:read gửi scope=orders:read orders:refund. AS xử lý thành công và ký AT có cả hai scope vì copy raw request.

**Câu hỏi:** Cơ chế nào sai?

**Phân tích:** AS đã nhầm **requested** với **authorized granted**. Phải dùng client registration, resource, grant/consent và subject/workload policy để quyết định, không copy input. Token có chữ ký đúng vẫn có thể là token phát sai quyền.

### Bài tập 2 — User Approver nhưng mobile app read-only

User có role Approver ở web admin, dùng một mobile client chỉ đăng ký orders:read. AS cấp mobile AT orders:approve do lấy mọi roles của user làm scope.

**Câu hỏi:** User có role Approver có đủ để mobile được quyền approve không?

**Phân tích:** Không. Client registration và consent/grant **độc lập** với quyền của user. Cần cùng kiểm client được cấp quyền, user hiện tại được phép, đúng resource và risk/authorization policy. Scope của mobile vẫn read nếu đó là grant hợp lệ.

### Bài tập 3 — Token có scope approve nhưng order sai tenant

Một access token hợp lệ có aud=orders-api, scope=orders:approve, tenant_id=tenant-blue. Caller muốn approve order thuộc tenant-red.

**Câu hỏi:** Có thể cho qua vì scope đúng không?

**Phân tích:** Không. Scope là điều kiện cần. RS kiểm **order.tenant**, principal membership/authority, trạng thái và SoD. Một claim tenant_id chưa đủ nếu resource ownership/tenant thực tế không khớp.

### Bài tập 4 — Client Credentials report exporter

Một batch client cần đọc reports cho tenant-blue, nhưng client_id được cấp users:admin và payments:refund. Team đề xuất bảo vệ bằng việc ký JWT RS256 và bật mTLS.

**Câu hỏi:** Điều này có sửa over-privilege không?

**Phân tích:** Không. RS256 bảo vệ integrity/token origin; mTLS giảm token replay khi chỉ AT bị copy. Chúng **không giảm quyền** đã grant sai. Phải thu hẹp registration, grant, audience, tenant và RS policy.

### Bài tập 5 — BFF gọi downstream refund

BFF giữ một credential riêng với payments:refund. Browser caller đưa AT chỉ có orders:read, nhưng gọi BFF endpoint /refund.

**Câu hỏi:** Đâu là confused deputy?

**Phân tích:** BFF không được dùng **quyền riêng** để thực hiện action mà caller chưa được ủy quyền. Nó cần kiểm caller scope/permission, tenant, amount/approval và delegation contract trước khi gọi Payments, dù downstream service credential của nó hợp lệ.

### Bài tập 6 — Cùng chuỗi write ở hai API

Orders AT chứa scope=write, aud=orders-api. Payments API cũng yêu cầu scope=write và tin cùng issuer key.

**Câu hỏi:** Payments có nên chấp nhận token này không?

**Phân tích:** Không, vì **audience sai**. Scope-name collision không thay issuer/audience validation. Thiết kế có namespace scopes giúp rõ hơn nhưng vẫn cần đúng intended resource.

### Bài tập 7 — Permission được thu hồi nhưng JWT còn hạn

User mất quyền approve lúc 10:00, AT JWT chứa orders:approve hết hạn 10:20. RS chỉ kiểm signature, exp và scope.

**Câu hỏi:** Có thể xảy ra gì?

**Phân tích:** User có thể tiếp tục approve trong cửa sổ còn hạn nếu RS không tham vấn current permission hoặc revocation state. Nếu nghiệp vụ yêu cầu rút quyền tức thì, phải có **RS state check/denylist/introspection hoặc token version/SLO**. Không mặc định claims trong AT tự cập nhật.

### Bài tập 8 — Scope parser dùng substring

Token có scope=not-orders:read. Code RS dùng scopes.contains("orders:read") và cho đọc dữ liệu.

**Câu hỏi:** Sửa ra sao?

**Phân tích:** Parse space-delimited scopes (hoặc profile khác theo issuer) thành tập **scope tokens exact** rồi so đúng phần tử orders:read. Nếu muốn hierarchy, viết policy mapping explicit và tests; không dùng substring/prefix.

### Bài tập 9 — Refresh token escalation

Original grant chỉ có orders:read. Client gửi refresh_token grant với scope=orders:read orders:approve. AS trả AT có approve vì user hiện tại có role Approver.

**Câu hỏi:** Có đủ căn cứ để cấp approve không?

**Phân tích:** Không. Quyền user có thể là điều kiện cần, nhưng **original RT grant không có approve**. AS không được tự nâng scope khi refresh; cần grant update/authorization phù hợp.

### Bài tập 10 — Khắc phục overgrant đã phát

Một lỗi cấu hình đã cấp payments:refund cho 500 AT còn hạn và 200 RT families. Team chỉ sửa allowed scope của client registration.

**Câu hỏi:** Đã hết rủi ro chưa?

**Phân tích:** Chưa. AT đã phát có thể vẫn được RS chấp nhận, RT families có thể tiếp tục xin AT nếu grant state không được sửa. Cần **điều tra issuance window, revoke/narrow tokens/grants, kiểm RS enforcement, sửa policy và audit actions đã xảy ra**.

### Cây quyết định dành cho một API operation

~~~mermaid
flowchart TD
    A["HTTP request với token"] --> B{"Token issuer, type, aud, time hợp lệ?"}
    B -->|Không| D["DENY"]
    B -->|Có| C{"Required exact scope có trong granted scopes?"}
    C -->|Không| D
    C -->|Có| E{"Principal/client được phép hành động này?"}
    E -->|Không| D
    E -->|Có| F{"Đúng tenant, owner, business state và approval?"}
    F -->|Không| D
    F -->|Có| G{"Token/grant/sender proof còn hợp lệ khi áp dụng?"}
    G -->|Không| D
    G -->|Có| H["ALLOW operation được ủy quyền"]
~~~

## Kết luận

**Over-privileged scope là một rủi ro cấp quyền, không phải một lỗi có thể khắc phục chỉ bằng mật mã.** JWT có chữ ký hợp lệ hoặc opaque token trả active=true vẫn có thể mang quyền vượt nhu cầu, vượt client grant hoặc vượt authority của principal. Nếu Resource Server chỉ kiểm scope mà không kiểm **audience, tenant, ownership, nghiệp vụ và trạng thái**, hậu quả có thể là truy cập dữ liệu trái phép hoặc thực hiện hành động quyền cao.

Những nguyên tắc quan trọng nhất:

- **Requested không phải granted:** client request, consent UI và user role chỉ là những input để AS quyết định; AS phải áp client registration, grant, subject/workload permissions và resource policy.
- **Scope phải có ranh giới:** ràng với **resource/audience, token type, client identity, thời hạn và ngữ cảnh cấp quyền**, không dùng một token admin chung cho mọi API.
- **Scope không phải object permission:** mỗi endpoint/action cần exact scope check; mỗi record/tenant cần authorization riêng, có kiểm trạng thái nghiệp vụ và separation of duties khi áp dụng.
- **Không tự tăng quyền qua refresh hoặc token exchange:** scope mới phải có căn cứ authorization và delegation rõ, không được sinh từ raw requestedScope.
- **Role và OIDC claims không thay OAuth scope:** ID token không phải access token cho RS; role Admin trong một hệ thống/tenant không tự là quyền Admin ở hệ thống khác.
- **Không dùng substring, prefix hoặc default-allow mơ hồ:** parse scope theo issuer profile, so exact membership hoặc một formal permission mapping được review.
- **Không nhầm sender-binding với least privilege:** DPoP, mTLS, JWS/JWE và TLS giúp bảo vệ token/holder hoặc đường truyền nhưng không giảm quyền do AS hoặc RS đã cấu hình sai.
- **Overgrant đã phát cần xử lý:** sửa configuration không tự rút JWT còn hạn hay refresh-token grant. Cần token/grant revocation, policy update, propagation SLO và kiểm chứng tại các Resource Servers.
- **Security observability và negative tests phải đo năng lực thực tế:** kiểm token bị từ chối, resource không bị thay đổi, tenants không bị đọc chéo, và AS không còn phát scope nhạy cảm ngoài policy.

Một thiết kế an toàn kết hợp **least-privilege issuance ở Authorization Server**, **audience và token-profile validation**, **resource-level authorization ở Resource Server**, **sender-constraining khi phù hợp**, và **giám sát/thu hồi quyền theo vòng đời**. Chỉ khi những lớp này cùng đúng, việc thu hẹp scope mới thực sự giảm blast radius của token theft, replay và privilege escalation.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): tham số scope, grant, client và token endpoint.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer tokens, insufficient_scope và giới hạn bảo mật.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): rút token/grant liên quan.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái active và metadata của token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token và authority trong delegation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): ràng resource/audience trong authorization.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained tokens.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): trust, JWT profiles và token confusion.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token claims, scope và audience.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): biểu diễn yêu cầu authorization chi tiết ngoài scope đơn giản.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constraining và proof validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth security recommendations, token theft và authorization controls.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, scopes và authentication flow.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): practical OAuth hardening.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object-level authorization.
- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): Broken Object Level Authorization (API1) và Broken Function Level Authorization (API5).
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT validation, storage và vận hành.











