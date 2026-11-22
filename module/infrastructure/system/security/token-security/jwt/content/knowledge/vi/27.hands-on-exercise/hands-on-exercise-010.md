# Thiết kế nhiều API hoặc nhiều tenant với ranh giới tin cậy rõ ràng

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Thực hành tổng hợp. Bài thực hành này áp dụng cho thiết kế xác thực và phân quyền JWT trên nhiều API, nhiều tenant và nhiều dịch vụ; không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Mục tiêu bài thực hành

Bạn sẽ thiết kế một hệ thống có nhiều API và nhiều tenant sao cho mỗi request chỉ được chấp nhận trong đúng ranh giới tin cậy. Bài tập yêu cầu kết hợp việc phát hành JWT, xác minh chữ ký, lựa chọn issuer, audience, token profile, tenant context, service identity và authorization ở cấp tài nguyên.

Sau khi hoàn thành, bạn cần chứng minh được:

- API chỉ chấp nhận token do issuer đã cấu hình phát hành.
- Token dành cho API này không thể được dùng thay token dành cho API khác.
- Một tenant không thể đọc hoặc thay đổi dữ liệu của tenant khác chỉ bằng cách sửa path, query, header hoặc request body.
- Scope/role trong token không tự động cấp quyền trên mọi tài nguyên.
- Service-to-service call có danh tính và audience riêng, không vô tình nâng quyền từ service này sang service khác.
- Gateway, cache, JWKS và key rotation không làm suy yếu ranh giới xác minh.
- Các lỗi xác thực và phân quyền được xử lý nhất quán, có thể kiểm thử và quan sát.

Đây là bài thực hành thiết kế, không phải hướng dẫn triển khai bằng một framework cụ thể. Bạn có thể hiện thực bằng bất kỳ nền tảng nào miễn là chứng minh được các invariant và kết quả kiểm thử.

## 2. Bối cảnh hệ thống

Một nền tảng SaaS phục vụ nhiều tổ chức. Mỗi tổ chức là một tenant độc lập về dữ liệu và quyền truy cập. Một người dùng có thể là thành viên của nhiều tenant, nhưng tại mỗi request chỉ hoạt động trong một tenant context đã được xác thực.

Hệ thống có ba API nghiệp vụ:

| API | Audience đề xuất | Trách nhiệm |
| --- | --- | --- |
| Orders API | `https://api.example.test/orders` | Đơn hàng, giỏ hàng và trạng thái giao nhận |
| Billing API | `https://api.example.test/billing` | Hóa đơn, thanh toán và phương thức thanh toán |
| Admin API | `https://api.example.test/admin` | Quản trị tenant, thành viên và cấu hình bảo mật |

Ngoài ra có các thành phần:

- **Identity Provider (IdP):** xác thực người dùng, quản lý membership và phát hành access token.
- **API Gateway:** định tuyến request, áp dụng giới hạn lưu lượng và có thể thực hiện lớp xác minh ban đầu.
- **Orders, Billing, Admin:** các resource server có trách nhiệm tự bảo vệ API của mình.
- **Notification Worker:** service identity dùng để gửi thông báo khi đơn hàng thay đổi.
- **Audit Service:** nhận sự kiện bảo mật và nghiệp vụ đã được lọc dữ liệu nhạy cảm.
- **Tenant Data Store:** lưu dữ liệu có tenant ownership rõ ràng.

Có hai tenant mẫu:

| Tenant | Tên hiển thị | Mã định danh ví dụ |
| --- | --- | --- |
| Tenant A | Northwind Retail | `tenant-northwind` |
| Tenant B | Fabrikam Services | `tenant-fabrikam` |

Người dùng mẫu:

- Alice là thành viên của Tenant A, có quyền đọc và tạo order.
- Bob là thành viên của Tenant B, có quyền đọc order và xem hóa đơn.
- Carol là quản trị viên Tenant A, có quyền quản lý thành viên trong Tenant A.
- Notification Worker là workload identity, không phải người dùng tương tác.

Một số định danh trong bài chỉ là dữ liệu giả lập. Không dùng account, token, khóa hoặc dữ liệu production để làm fixture.

## 3. Xác định các ranh giới tin cậy

Trước khi thiết kế token, hãy phân biệt các ranh giới sau. Chúng có quan hệ với nhau nhưng không thay thế nhau.

| Ranh giới | Câu hỏi phải trả lời | Ví dụ kiểm soát |
| --- | --- | --- |
| Issuer trust | Ai được phép phát hành token? | Issuer allowlist, JWKS đã cấu hình |
| Cryptographic trust | Khóa nào được phép xác minh chữ ký? | Key binding, thuật toán allowlist, key rotation |
| API/resource boundary | Token được phát hành cho API nào? | `aud` riêng cho Orders/Billing/Admin |
| Token profile | JWT này đại diện loại credential nào? | Access token, ID Token, client assertion, DPoP proof |
| Client/actor boundary | Ứng dụng hoặc service nào đang gọi? | `client_id`, workload identity, actor policy |
| Tenant boundary | Request hoạt động trong tenant nào? | Tenant membership, tenant-bound context |
| Object boundary | Tài nguyên cụ thể thuộc tenant/chủ thể nào? | Ownership check, tenant predicate |
| Operation boundary | Hành động nào được phép? | Scope, role, policy và business rules |

**Issuer không đồng nghĩa tenant.** Một issuer có thể phát hành token cho nhiều tenant. Ngược lại, một tenant có thể sử dụng nhiều client hoặc nhiều issuer được liên kết. Không suy ra tenant chỉ từ hostname, `iss`, `sub`, `client_id` hoặc một header do client tự gửi.

**Audience không đồng nghĩa scope.** Audience xác định recipient dự kiến; scope mô tả phạm vi quyền được cấp. Token có audience Billing nhưng không có scope phù hợp vẫn không được phép xem hóa đơn.

**Scope không đồng nghĩa object ownership.** Scope `orders:read` có thể cho phép đọc loại tài nguyên order, nhưng server vẫn phải xác minh order cụ thể thuộc tenant mà principal đang hoạt động.

## 4. Thiết kế trust topology

Trong bài thực hành, sử dụng một issuer đã đăng ký:

- Issuer: `https://identity.example.test`
- Metadata/JWKS URI được cấu hình ngoài token.
- Mỗi API có audience riêng.
- Token profile access token được định nghĩa thống nhất.
- Tenant membership được quản lý tại IdP hoặc một membership service có thẩm quyền.

Sơ đồ tổng quan:

~~~mermaid
flowchart TD
    U["User / Client"] --> IDP["Trusted Identity Provider"]
    IDP -->|"Access token: aud Orders"| GW["API Gateway"]
    IDP -->|"Access token: aud Billing"| GW
    IDP -->|"Access token: aud Admin"| GW
    GW --> O["Orders API"]
    GW --> B["Billing API"]
    GW --> A["Admin API"]
    O --> DB["Tenant-aware Data Store"]
    B --> DB
    A --> DB
    O --> N["Notification Worker"]
    O --> AU["Audit Service"]
    B --> AU
    A --> AU
    IDP -. "Trusted metadata / JWKS" .-> O
    IDP -. "Trusted metadata / JWKS" .-> B
    IDP -. "Trusted metadata / JWKS" .-> A
~~~

Mỗi resource server phải có cấu hình trust độc lập hoặc một trust configuration dùng chung nhưng được namespace chính xác. Orders API không được tự động tin bất kỳ issuer nào chỉ vì Gateway đã nhận token. Nếu Gateway là enforcement point duy nhất, các backend phải được bảo vệ để không thể bị gọi trực tiếp từ mạng không tin cậy và phải xác minh tính toàn vẹn của identity context mà Gateway chuyển tiếp.

### 4.1. Khi nào nên dùng nhiều issuer?

Có thể có nhiều issuer vì các tổ chức dùng IdP riêng, có môi trường cloud/on-premise khác nhau hoặc có ranh giới pháp lý và vận hành độc lập.

Nếu có nhiều issuer:

- mỗi issuer phải được đăng ký và cấu hình rõ;
- mỗi issuer có metadata/JWKS source riêng;
- `iss` phải khớp chính xác issuer được chọn;
- cache key phải namespace theo issuer;
- `kid` giống nhau giữa hai issuer không được gây dùng chéo khóa;
- mỗi issuer có policy profile và mapping claim được kiểm soát;
- không tự động discovery/fetch metadata từ `iss` tùy ý trong token.

Một tenant không nhất thiết cần một issuer riêng. Chỉ tạo issuer riêng khi có yêu cầu trust, quản trị khóa hoặc quản trị danh tính độc lập thực sự. Tạo issuer riêng cho từng tenant làm tăng đáng kể số cấu hình, khóa, rotation và quy trình vận hành.

## 5. Định nghĩa hợp đồng access token

Thiết kế một token profile chung nhưng có audience và authorization claims phù hợp từng API. Nếu triển khai RFC 9068, tuân thủ đầy đủ profile JWT Access Token; nếu dùng profile nội bộ, tài liệu hóa rõ mọi claim và semantics.

Ví dụ header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "idp-signing-2026-01",
  "typ": "at+jwt"
}
~~~

Ví dụ payload cho Alice đang hoạt động trong Tenant A:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-alice",
  "aud": "https://api.example.test/orders",
  "client_id": "web-portal",
  "iat": 1900000000,
  "exp": 1900000300,
  "jti": "access-01H-EXAMPLE",
  "scope": "orders:read orders:create",
  "tenant_id": "tenant-northwind",
  "tenant_membership_version": 12
}
~~~

Các giá trị thời gian và định danh trên chỉ dùng để mô tả cấu trúc; fixture chạy thật phải dùng clock kiểm thử và khóa test.

### 5.1. Claim chuẩn và claim ứng dụng

| Claim | Loại | Quy tắc |
| --- | --- | --- |
| `iss` | Registered claim | Phải khớp issuer tin cậy |
| `sub` | Registered claim | Định danh subject theo semantics của issuer |
| `aud` | Registered claim | Chỉ API/resource dự kiến |
| `exp` | Registered claim | Hết hạn theo policy thời gian |
| `iat` | Registered claim | Thời điểm phát hành, dùng cho freshness khi cần |
| `nbf` | Registered claim tùy chọn | Chưa có hiệu lực trước thời điểm này |
| `jti` | Registered claim | Định danh token, hữu ích cho audit/revocation |
| `client_id` | Profile claim | Định danh client theo profile access token |
| `scope` | Claim/profile authorization | Quyền thô được cấp trong phạm vi token |
| `tenant_id` | Custom claim | Tenant context đã được issuer xác thực |
| `tenant_membership_version` | Custom claim | Phiên bản membership để phát hiện thay đổi |

Không gọi `tenant_id` là claim chuẩn của JWT. Đây là claim ứng dụng; issuer và resource server phải thống nhất kiểu dữ liệu, nguồn tạo, semantics và cách thu hồi.

### 5.2. Không nhét toàn bộ quyền và dữ liệu tenant vào token

Token nên mang thông tin đủ để resource server xác định principal, recipient, tenant context và phạm vi quyền cần thiết. Không đưa toàn bộ danh sách đơn hàng, hồ sơ thành viên, cấu hình tenant hoặc dữ liệu cá nhân vào payload.

Nếu membership và quyền thay đổi thường xuyên, cân nhắc claim version hoặc truy vấn policy/membership service. Token snapshot không tự cập nhật khi user bị xóa khỏi tenant.

### 5.3. Một token cho một API hay nhiều API?

Mặc định phát hành token có audience riêng cho từng resource server. Điều này giới hạn tác động khi token bị lộ và giảm nguy cơ token substitution.

Ví dụ:

- Orders token: `aud = https://api.example.test/orders`
- Billing token: `aud = https://api.example.test/billing`
- Admin token: `aud = https://api.example.test/admin`

Không phát một token có audience quá rộng như `https://api.example.test/*` chỉ để giảm số lần xin token. Nếu có nhu cầu multi-audience, phải đánh giá rõ resource server nào được phép chấp nhận token và các rủi ro confused deputy.

## 6. Thiết kế authorization theo API

Tách authorization thành ít nhất ba lớp:

1. **Token-level:** token có đúng issuer, audience, profile, thời hạn và sender constraint không?
2. **Operation-level:** principal có scope/role hoặc policy cho action này không?
3. **Object-level:** tài nguyên cụ thể có thuộc tenant và phạm vi principal được phép truy cập không?

Ví dụ policy:

| API | Endpoint | Scope yêu cầu | Kiểm tra tenant/object |
| --- | --- | --- | --- |
| Orders | `GET /orders` | `orders:read` | Chỉ trả order của tenant context |
| Orders | `POST /orders` | `orders:create` | Gán tenant từ context đã xác minh |
| Orders | `GET /orders/{id}` | `orders:read` | Order phải thuộc tenant context |
| Billing | `GET /invoices` | `billing:read` | Chỉ invoice của tenant context |
| Billing | `POST /payments` | `payments:create` | Payment và invoice cùng tenant; áp dụng business policy |
| Admin | `GET /tenants/{id}/members` | `members:read` | `{id}` phải bằng tenant được quản trị |
| Admin | `POST /tenants/{id}/members` | `members:manage` | Kiểm tra role quản trị và tenant membership |

Role quản trị không được hiểu là quyền toàn cục trừ khi có một global-admin policy được định nghĩa riêng. `tenant_admin` của Tenant A không được quản trị Tenant B.

### 6.1. Scope là điều kiện cần, chưa phải điều kiện đủ

Ví dụ Alice có `orders:read` và token mang `tenant_id=tenant-northwind`. Alice gọi:

`GET /orders/order-fabrikam-9001`

Nếu order đó thuộc Tenant B, Orders API phải từ chối hoặc trả kết quả không tiết lộ sự tồn tại của order, theo chính sách chống enumeration. Việc scope `orders:read` hợp lệ không cho phép vượt qua tenant boundary.

### 6.2. Không lấy tenant context trực tiếp từ request

Client có thể gửi tenant trong path, query hoặc header:

- `/tenants/tenant-fabrikam/orders`;
- `?tenant_id=tenant-fabrikam`;
- `X-Tenant-ID: tenant-fabrikam`.

Các giá trị này chỉ là selector do client đề nghị. Server phải so sánh chúng với tenant context đã xác thực và kiểm tra membership/authorization. Không dùng chúng làm nguồn thẩm quyền.

Với endpoint tạo tài nguyên, server nên gán tenant ownership từ context đã xác minh, không tin `tenant_id` trong request body.

## 7. Quy trình phát hành token khi người dùng thuộc nhiều tenant

Alice thuộc Tenant A và Tenant C. Khi đăng nhập, IdP xác thực Alice và xác định các membership hiện tại. Alice chọn Tenant A trong giao diện. Lựa chọn này khởi tạo yêu cầu context, nhưng IdP phải kiểm tra Alice thực sự là thành viên Tenant A trước khi phát hành token.

Quy trình:

1. Client hoàn thành authentication flow với IdP.
2. IdP xác minh danh tính và session.
3. Client yêu cầu hoạt động trong Tenant A.
4. IdP hoặc membership service kiểm tra membership và trạng thái tenant.
5. Policy engine xác định role/scope trong Tenant A.
6. Authorization server phát access token có audience cho API đích, tenant context và thời hạn phù hợp.
7. API xác minh token và kiểm tra tenant/object policy.
8. Khi Alice chuyển sang Tenant C, client lấy context/token mới theo quy trình; không sửa claim trong JWT hiện tại.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant U as Alice
    participant C as Client
    participant I as Identity Provider
    participant M as Membership Service
    participant O as Orders API

    U->>C: Chọn Tenant A
    C->>I: Yêu cầu access token cho Orders + Tenant A
    I->>M: Kiểm tra Alice là member Tenant A
    M-->>I: Membership active, role và version
    I-->>C: Access token aud=Orders, tenant_id=A
    C->>O: Request + Bearer token
    O->>O: Verify issuer, signature, audience, time, profile
    O->>O: Check scope và tenant/object ownership
    O-->>C: Chỉ trả dữ liệu Tenant A
~~~

Nếu membership bị thu hồi sau khi token phát hành, hệ thống cần có chính sách xử lý: access token TTL ngắn, membership version, introspection, denylist hoặc event invalidation. Không giả định claim snapshot sẽ tự thay đổi.

## 8. Luồng service-to-service và delegated call

Notification Worker gọi Orders API hoặc nhận sự kiện order. Nó cần workload identity riêng. Không dùng token của Alice làm credential mặc định cho worker.

### 8.1. Workload identity

Token của Notification Worker có thể có:

- issuer được tin cậy;
- audience là API đích;
- client identity là Notification Worker;
- scope hẹp như `notifications:send`;
- subject/actor semantics được định nghĩa rõ;
- thời hạn ngắn;
- sender constraint nếu threat model yêu cầu.

Worker chỉ được phép thực hiện chức năng đã cấp. Nó không được có `admin:*` hoặc scope nghiệp vụ rộng chỉ vì chạy trong hạ tầng nội bộ.

### 8.2. Delegation giữ ngữ cảnh người dùng

Nếu Orders API cần gọi Billing API thay mặt Alice, không nên chuyển tiếp token Orders có audience sai sang Billing. Có thể dùng OAuth Token Exchange (RFC 8693) hoặc cơ chế delegation được đặc tả:

- subject token đại diện Alice;
- actor/client là Orders API;
- requested audience là Billing API;
- scope chỉ gồm hành động cần thiết;
- authorization server kiểm tra Orders API được phép delegate;
- token mới thể hiện rõ subject và actor theo profile;
- Billing API xác minh token và kiểm tra tenant/object policy của chính mình.

Không tự tạo claim `act` hoặc `may_act` với semantics tùy ý mà không định nghĩa profile và trust rules. Nếu không triển khai Token Exchange, dùng một service credential riêng và ghi nhận rõ hành động là do service thực hiện, không giả vờ là người dùng trực tiếp.

### 8.3. Tránh confused deputy

Một service có quyền rộng có thể bị endpoint công khai lạm dụng làm deputy. Để giảm rủi ro:

- xác định actor/service identity;
- giới hạn audience và scope;
- kiểm tra quyền delegate theo subject và resource;
- không tin tenant ID do service caller tự khai;
- ghi audit actor và subject tách biệt;
- không cho phép client tự chọn token exchange subject tùy ý.

## 9. Trách nhiệm của API Gateway và backend

Gateway có thể xác minh token trước khi định tuyến, nhưng không nên làm mờ ranh giới trách nhiệm.

Một mô hình an toàn:

- Gateway kiểm tra cấu trúc, giới hạn kích thước, token presence, rate limit và có thể xác minh issuer/audience ban đầu.
- Mỗi API backend xác minh token hoặc nhận identity context qua một kênh nội bộ được xác thực mạnh, có integrity protection và không thể bị giả mạo từ client.
- Backend kiểm tra audience/profile/tenant phù hợp với API của mình.
- Gateway loại bỏ header identity do client tự gửi trước khi thêm header nội bộ.
- Backend không nhận request trực tiếp từ mạng không tin cậy nếu dựa vào assertion của Gateway.
- Network policy hoặc mTLS bảo vệ đường truyền gateway-to-backend nếu kiến trúc yêu cầu.

Không tin các header như `X-User-ID`, `X-Tenant-ID`, `X-Roles` chỉ vì chúng xuất hiện trong request. Client có thể tự gửi các header đó. Nếu gateway chuyển tiếp identity, cần một contract nội bộ, xác thực nguồn gửi và bảo đảm client không thể ghi đè.

### 9.1. Gateway không được biến một token thành credential đa audience

Nếu gateway nhận access token cho Orders rồi gọi Billing bằng chính token đó, Billing phải từ chối vì audience không khớp. Gateway cần lấy token đúng audience hoặc dùng delegation/service credential phù hợp.

### 9.2. Bypass gateway

Nếu backend có public route hoặc địa chỉ nội bộ bị lộ, attacker có thể gọi trực tiếp để bỏ qua kiểm tra ở gateway. Kiểm thử phải xác minh backend không thể bị truy cập ngoài đường đi tin cậy hoặc vẫn tự xác minh đầy đủ.

## 10. Ràng buộc dữ liệu ở tầng lưu trữ

Authorization tại API phải được củng cố bằng tenant-aware data access.

Mỗi bản ghi tenant-scoped cần có tenant ownership rõ ràng. Ví dụ:

| Bảng/aggregate | Khóa định danh | Tenant ownership |
| --- | --- | --- |
| Order | `order_id` | `tenant_id` |
| Invoice | `invoice_id` | `tenant_id` |
| Payment | `payment_id` | `tenant_id` và liên kết invoice |
| Membership | `membership_id` | `tenant_id` + `subject_id` |
| Tenant setting | `setting_id` | `tenant_id` |

Mọi truy vấn đọc/cập nhật/xóa cần ràng buộc tenant. Ví dụ logic:

~~~sql
SELECT order_id, status, total
FROM orders
WHERE order_id = :requested_order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

Đây là SQL minh họa. `authenticated_tenant_id` phải đến từ context đã được xác minh, không lấy trực tiếp từ query parameter hoặc request body.

Khi cập nhật, kiểm tra tenant trong cùng thao tác để tránh TOCTOU:

~~~sql
UPDATE orders
SET status = :new_status
WHERE order_id = :requested_order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

Kiểm tra số bản ghi bị tác động. Nếu không có bản ghi phù hợp, không tiếp tục side effect như gửi thanh toán hoặc phát thông báo.

Có thể bổ sung row-level security, schema/database tách biệt hoặc tenant-specific encryption key tùy mức cô lập yêu cầu. Dù dùng cơ chế nào, API vẫn phải xác thực principal và quyền trước khi truy cập dữ liệu.

## 11. Quy trình xác minh JWT tại từng API

Mỗi API có một validation policy cụ thể:

1. Giới hạn kích thước token và parse định dạng theo profile.
2. Chọn issuer từ allowlist hoặc cấu hình đã đăng ký.
3. Lấy khóa từ JWKS/metadata được tin cậy cho issuer đó.
4. Chọn key theo `kid` trong đúng issuer namespace.
5. Kiểm tra `alg` nằm trong allowlist và key type phù hợp.
6. Xác minh chữ ký hoặc giải mã theo profile.
7. Kiểm tra `iss` chính xác.
8. Kiểm tra `aud` có chứa audience của API hiện tại.
9. Kiểm tra `exp`, `nbf`, `iat` và clock skew.
10. Kiểm tra `typ` và token profile.
11. Kiểm tra claim cần thiết như `sub`, `client_id`, `tenant_id`, scope.
12. Kiểm tra revocation/membership version/sender constraint nếu policy yêu cầu.
13. Tạo authenticated context bất biến cho request.
14. Thực hiện authorization operation-level và object-level.

Không sử dụng claims trước khi chữ ký và issuer trust được xác minh. Nếu cần đọc `iss` chưa xác minh để chọn issuer ứng viên, chỉ dùng nó để tra cứu allowlist tĩnh; không fetch metadata từ URL tùy ý.

### 11.1. Token profile khác nhau phải có validator riêng

| Token | Nơi sử dụng | Vì sao không thay thế nhau |
| --- | --- | --- |
| Access Token | Resource server tương ứng audience | Cấp quyền gọi API trong scope/resource |
| ID Token | OIDC client | Chứng minh kết quả authentication cho client |
| Client Assertion | Authorization Server/token endpoint | Xác thực client theo profile |
| DPoP Proof | Kèm request dùng DPoP-bound token | Chứng minh possession và request binding |
| Service Token | API/service đích | Đại diện workload/client identity |

Một JWT hợp lệ về chữ ký có thể sai token type. Mỗi endpoint phải biết loại token nó chờ và từ chối token profile khác.

## 12. Bảng quyết định authorization mẫu

Dùng bảng quyết định để tránh policy ngầm và dễ biến thành test.

| Principal | API | Audience | Tenant context | Scope/role | Resource tenant | Kết quả |
| --- | --- | --- | --- | --- | --- | --- |
| Alice | Orders | Orders | Northwind | `orders:read` | Northwind | Allow |
| Alice | Orders | Orders | Northwind | `orders:read` | Fabrikam | Deny |
| Alice | Billing | Orders | Northwind | `billing:read` | Northwind | Deny: audience |
| Bob | Billing | Billing | Fabrikam | `billing:read` | Fabrikam | Allow |
| Carol | Admin | Admin | Northwind | `members:manage`, tenant_admin | Northwind | Allow theo policy |
| Carol | Admin | Admin | Northwind | `members:manage`, tenant_admin | Fabrikam | Deny |
| Notification Worker | Orders | Orders | Northwind | `orders:read` | Northwind | Theo workload policy |
| Notification Worker | Admin | Admin | Northwind | Không có admin scope | Northwind | Deny |

Kết quả authorization phải dựa trên toàn bộ điều kiện. Không suy ra `Allow` chỉ từ một cột scope.

## 13. Bộ dữ liệu và fixture cho bài tập

Tạo fixture tối thiểu:

### 13.1. Issuer và key set

- Issuer A: `https://identity.example.test`.
- Key set có hai public key test trong giai đoạn rotation.
- Mỗi key có `kid` riêng và private key chỉ dùng trong test signer.
- Một issuer không tin cậy giả lập để kiểm thử từ chối.
- Không tái sử dụng cùng `kid` mà không namespace issuer.

### 13.2. Người dùng và membership

| Subject | Tenant | Membership | Role |
| --- | --- | --- | --- |
| `user-alice` | `tenant-northwind` | Active | `order_reader`, `order_creator` |
| `user-alice` | `tenant-fabrikam` | None | None |
| `user-bob` | `tenant-fabrikam` | Active | `order_reader`, `billing_reader` |
| `user-carol` | `tenant-northwind` | Active | `tenant_admin` |
| `user-carol` | `tenant-fabrikam` | None | None |

### 13.3. Resource fixtures

| Resource ID | Loại | Tenant |
| --- | --- | --- |
| `order-nw-001` | Order | `tenant-northwind` |
| `order-fk-001` | Order | `tenant-fabrikam` |
| `invoice-nw-001` | Invoice | `tenant-northwind` |
| `invoice-fk-001` | Invoice | `tenant-fabrikam` |

### 13.4. Token fixture cần tạo

Tạo ít nhất các fixture:

- Alice + Orders audience + Northwind tenant + `orders:read`;
- Alice + Billing audience + Northwind tenant + `billing:read` nếu policy cho phép;
- Bob + Billing audience + Fabrikam tenant + `billing:read`;
- Carol + Admin audience + Northwind tenant + `members:manage`;
- Notification Worker + Orders audience + workload scope;
- token sai issuer;
- token sai audience;
- token có tenant claim không còn membership;
- token sai profile;
- token ký bằng key không thuộc issuer;
- token hết hạn và token bị revoke.

Mỗi fixture cần metadata gồm profile, issuer, audience, subject/client, tenant, scope, `kid`, thuật toán, thời gian hiệu lực và expected result. Không đưa private key hoặc raw production credential vào fixture.

## 14. Các nhiệm vụ thực hành

### Bài 1 — Vẽ trust boundary

Vẽ sơ đồ có IdP, Gateway, ba API, worker và data store. Trên sơ đồ, đánh dấu:

- nơi token được phát hành;
- nơi khóa được tin cậy và cache;
- nơi token được xác minh;
- nơi tenant context được tạo;
- nơi authorization diễn ra;
- nơi dữ liệu được cô lập;
- các đường gọi service-to-service.

**Kết quả cần nộp:** sơ đồ và một đoạn giải thích vì sao mỗi trust boundary tồn tại.

### Bài 2 — Viết token contract

Định nghĩa token profile và bảng claim:

- claim chuẩn;
- custom claim;
- kiểu dữ liệu;
- nguồn tạo;
- audience;
- TTL;
- issuer;
- thuật toán/key type;
- quy tắc revocation;
- endpoint được phép nhận.

**Kết quả cần nộp:** JSON fixture đã giả lập và bảng contract. Chỉ đưa dữ liệu không nhạy cảm vào ví dụ.

### Bài 3 — Thiết lập validation policy cho từng API

Tạo ba policy riêng:

- Orders chỉ nhận access token có audience Orders;
- Billing chỉ nhận access token có audience Billing;
- Admin chỉ nhận access token có audience Admin.

Mỗi policy xác định issuer allowlist, thuật toán, key source, profile, claim bắt buộc, clock skew và scope. Kiểm tra cùng một token được gửi tới API sai audience phải bị từ chối.

**Kết quả cần nộp:** bảng policy và kết quả test audience isolation.

### Bài 4 — Thực hiện tenant isolation

Với Alice trong Northwind:

- đọc order của Northwind thành công;
- đọc order của Fabrikam bị từ chối;
- thay path tenant thành Fabrikam vẫn bị từ chối;
- sửa `X-Tenant-ID` thành Fabrikam vẫn bị từ chối;
- gửi body `tenant_id=tenant-fabrikam` khi tạo order không làm thay đổi tenant ownership;
- truy vấn database luôn lọc theo authenticated tenant context.

**Kết quả cần nộp:** policy object-level, truy vấn tenant-aware và log test đã redact.

### Bài 5 — Thực hiện delegated service call

Orders cần gọi Billing để lấy thông tin thanh toán của order. Thiết kế một trong hai phương án:

- token exchange/delegation có subject Alice, actor Orders API, audience Billing và scope tối thiểu;
- service credential của Orders API, trong đó Billing xác minh workload identity và policy cho phép hành động service.

Chỉ rõ phương án có giữ user context hay không. Billing phải tự xác minh token và kiểm tra tenant của invoice.

**Kết quả cần nộp:** sequence diagram, token contract cho delegated call và test confused-deputy.

### Bài 6 — Kiểm tra gateway và backend

Thử gửi trực tiếp tới backend, bỏ qua Gateway. Thử thêm các header `X-User-ID`, `X-Tenant-ID`, `X-Roles` từ client. Chứng minh backend không tin header do client tự kiểm soát.

**Kết quả cần nộp:** network trust assumptions, header sanitization rules và kết quả bypass test.

### Bài 7 — Xử lý membership và key rotation

Thu hồi membership của Alice trong Northwind và xoay signing key:

- xác định token cũ còn được chấp nhận bao lâu;
- xác định cách cập nhật membership version hoặc revocation state;
- công bố key mới trước khi dùng;
- giữ overlap có giới hạn;
- loại key cũ theo policy;
- invalidation cache ở mọi node/region;
- đo thời gian từ revoke/rotation tới khi request bị từ chối.

**Kết quả cần nộp:** state transition, TTL/revocation policy và test multi-node.

## 15. Ma trận kiểm thử bắt buộc

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Alice gọi Orders với token đúng issuer/audience/tenant/scope | Allow |
| T02 | Alice dùng Orders token gọi Billing | Deny: audience mismatch |
| T03 | Token ký bởi issuer không tin cậy | Deny |
| T04 | Token đúng chữ ký nhưng sai `typ` | Deny |
| T05 | Alice đọc order thuộc Northwind | Allow |
| T06 | Alice đọc order thuộc Fabrikam | Deny hoặc 404 theo anti-enumeration policy |
| T07 | Alice sửa `X-Tenant-ID` thành Fabrikam | Deny |
| T08 | Alice gửi body `tenant_id=tenant-fabrikam` khi tạo order | Server gán tenant từ context hoặc deny |
| T09 | Carol quản trị thành viên Northwind | Allow |
| T10 | Carol dùng role tenant_admin của Northwind quản trị Fabrikam | Deny |
| T11 | Notification Worker gọi endpoint Admin | Deny |
| T12 | Client tự gửi `X-User-ID` giả | Bị bỏ qua hoặc request bị từ chối |
| T13 | Backend bị gọi trực tiếp ngoài Gateway | Không thể bypass trust boundary |
| T14 | Cùng `kid` xuất hiện ở hai issuer | Key lookup không dùng chéo issuer |
| T15 | Token có audience nhiều API ngoài policy | Deny |
| T16 | Membership bị thu hồi sau khi token phát hành | Deny trong SLA đã cam kết |
| T17 | Token ký bằng key cũ trong overlap hợp lệ | Kết quả theo rotation policy |
| T18 | Token ký bằng key đã compromise/revoke | Deny sau invalidation deadline |
| T19 | Cache entry của Orders được dùng tại Billing | Không cache hit sai audience/profile |
| T20 | Service Orders delegate quyền quá rộng | Deny theo scope/actor policy |
| T21 | Token hết hạn hoặc `nbf` chưa tới | Deny |
| T22 | Request hợp lệ nhưng scope thiếu | 403 |
| T23 | Token thiếu hoặc sai chữ ký | 401 |
| T24 | Hai request đồng thời cập nhật resource tenant-scoped | Không tạo race làm vượt tenant boundary |

Với mỗi test, ghi lại fixture ID, endpoint, principal, audience, tenant context, expected result, actual result, reason code và request ID. Không ghi raw JWT, private key, cookie hoặc secret vào test report.

## 16. Phân biệt 401 và 403

Một quy ước hữu ích:

- **401 Unauthorized:** không có credential hợp lệ, token thiếu, chữ ký sai, issuer/audience/profile sai hoặc token hết hạn.
- **403 Forbidden:** token hợp lệ nhưng principal không có scope/role hoặc không được phép thực hiện action trên resource.
- **404 Not Found:** có thể được dùng thay cho 403 khi policy yêu cầu không tiết lộ sự tồn tại của tài nguyên thuộc tenant khác.

Không dùng status code để tiết lộ tenant hoặc object có tồn tại hay không. Response body nên có error code ổn định, không đưa claim hoặc chi tiết nội bộ nhạy cảm ra ngoài.

## 17. Cache, revocation và consistency trong hệ thống nhiều API

Nếu ba API dùng chung verification cache, cache key phải chứa tối thiểu issuer, token profile, expected audience, policy/configuration version và fingerprint token. Không dùng cache entry của Orders để chấp nhận request ở Billing.

Nếu authorization decision được cache, key cần phản ánh tenant, subject, action, resource và policy version. Khi membership hoặc role thay đổi, cache phải được invalidated hoặc hết hạn trong SLA.

Với multi-region:

- xác định consistency model của revocation store;
- phát invalidation event tới tất cả API;
- có version/sequence để chống event đến sai thứ tự;
- có TTL fallback khi event bị mất;
- đo độ trễ revoke đầu-cuối;
- không coi timeout của revocation service là trạng thái chưa thu hồi.

Nếu không có cơ chế thu hồi trực tuyến, phải công bố rõ rằng token có thể tiếp tục được chấp nhận tới khi hết hạn. Không tuyên bố logout/revoke tức thời nếu kiến trúc không bảo đảm điều đó.

## 18. Quan sát và audit mà không lộ token

Mỗi API nên ghi event an toàn:

- request ID;
- service/API alias;
- issuer alias;
- token profile;
- client alias;
- subject reference giả danh hóa khi cần;
- tenant reference theo policy;
- audience;
- authorization decision;
- reason code;
- policy version;
- thời gian xử lý và region.

Không ghi raw JWT, refresh token, cookie, private key hoặc toàn bộ claims. Không dùng token hoặc `jti` làm metric label cardinality cao.

Audit nên phân biệt subject và actor trong delegated call. Ví dụ, Alice là subject còn Orders API là actor. Điều này giúp điều tra hành động do service thực hiện thay mặt người dùng mà không nhập nhằng danh tính.

## 19. Tiêu chí nghiệm thu

Bài thực hành chỉ đạt khi có bằng chứng cho từng mục:

| Tiêu chí | Bằng chứng |
| --- | --- |
| Issuer trust rõ ràng | Danh sách issuer và nguồn JWKS đã cấu hình |
| API isolation | Audience matrix và test token sai API |
| Tenant isolation | Test cross-tenant read/write và tenant-aware query |
| Object authorization | Test IDOR và ownership |
| Client/service identity | Token contract và service-to-service tests |
| Delegation | Sequence diagram và actor/subject policy |
| Gateway/backend boundary | Bypass test và header sanitization |
| Key lifecycle | Rotation/revocation tests |
| Membership lifecycle | Test thu hồi membership và SLA |
| Cache correctness | Test cache namespace và invalidation |
| Error handling | Quy tắc 401/403/404 |
| Privacy/observability | Log schema và bằng chứng không có raw credential |

Không chỉ nộp sơ đồ hoặc mô tả. Cần có test thực thi hoặc test harness có thể chạy lại, fixture giả lập và kết quả rõ ràng. Mọi ngoại lệ policy phải được ghi thành quyết định thiết kế có người chịu trách nhiệm.

## 20. Các câu hỏi tự đánh giá

1. Vì sao `iss` đúng nhưng token vẫn có thể không đáng tin?
2. Vì sao một token có `aud` Orders không được dùng ở Billing?
3. `tenant_id` trong JWT chứng minh điều gì và không chứng minh điều gì?
4. Vì sao `orders:read` không đủ để đọc mọi order?
5. Nếu Alice thuộc hai tenant, ai xác minh tenant context khi phát hành token?
6. Khi membership bị thu hồi, token snapshot được xử lý thế nào?
7. Vì sao service-to-service call cần actor identity?
8. Khi nào nên dùng token exchange thay vì service credential?
9. Vì sao Gateway không thể tin `X-Tenant-ID` do client gửi?
10. Nếu backend có thể bị gọi trực tiếp, trust boundary thay đổi ra sao?
11. Cache key cần chứa những thành phần nào để tránh cross-API reuse?
12. Khi key bị compromise, invalidation phải lan tới những cache nào?
13. Vì sao cùng `kid` giữa hai issuer không được dùng chung key entry?
14. Khi revocation service timeout, vì sao không được mặc định token còn active?
15. Làm sao đo được độ trễ từ lúc revoke membership tới lần request cuối cùng được chấp nhận?

## 21. Mở rộng nâng cao

Sau khi hoàn thành phần cơ bản, chọn một hoặc nhiều tình huống:

- **Multi-issuer federation:** thêm một IdP thứ hai, mapping issuer và claim riêng, kiểm tra `kid` collision và issuer confusion.
- **Tenant isolation mạnh:** tách database/schema hoặc encryption key theo tenant; đánh giá vận hành và khôi phục.
- **Sender-constrained token:** thêm DPoP hoặc mTLS-bound access token; kiểm tra key binding và replay.
- **Token exchange:** bổ sung delegated call qua nhiều service, giới hạn actor chain và scope attenuation.
- **Nested JWT/JWE:** mã hóa hoặc ký lồng nhau theo profile; xác minh từng lớp và phân biệt confidentiality với issuer authentication.
- **Regional failover:** mô phỏng mất kết nối revocation event giữa hai region và đo stale acceptance.
- **Tenant migration:** chuyển dữ liệu giữa tenant, bảo đảm token cũ và cache không giữ quyền trên tenant nguồn.
- **Break-glass administration:** thiết kế global administrator với issuer/role/policy riêng, audit tăng cường và thời hạn ngắn.

Mỗi mở rộng phải thêm threat model, policy và test tương ứng. Không mở rộng quyền chỉ bằng cách thêm một role hoặc audience rộng hơn.

## 22. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer, audience, thuật toán và phân biệt token profile.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token profile.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation và token exchange.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): truy vấn trạng thái token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token.
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/): đặc biệt Broken Object Level Authorization, Broken Authentication và Broken Function Level Authorization.
- [OWASP Multi-Tenant Application Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): nguyên tắc cô lập tenant trong ứng dụng nhiều tenant.

**Ghi nhớ:** Thiết kế nhiều API hoặc nhiều tenant an toàn cần ràng buộc đồng thời issuer, audience, token profile, client/actor, tenant context và object ownership. JWT cung cấp bằng chứng đã được issuer ký; resource server vẫn phải xác minh trust, giới hạn token đúng API và thực hiện authorization ở cấp hành động lẫn tài nguyên. Mọi luồng service-to-service, gateway, cache và revocation đều phải giữ nguyên các ranh giới đó.

