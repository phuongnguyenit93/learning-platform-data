# Client scope and audience

Một dịch vụ nền `invoice-worker` cần đọc đơn hàng để phát hành hóa đơn. Dịch vụ này không có người dùng tương tác ở mỗi lần chạy: nó dùng **OAuth 2.0 Client Credentials grant** để xin access token từ authorization server (AS), rồi gọi `Orders API`. Nếu token chỉ được cấp **`scope=orders.read`** và **`aud=https://api.example.test/orders`**, dịch vụ không được dùng token đó để thực hiện thanh toán tại `Payments API` hoặc phê duyệt đơn hàng.

Điều gì xảy ra nếu một kẻ tấn công lấy được token? **Audience** giúp giới hạn những resource server có thể chấp nhận token; **scope** giúp giới hạn những hành động có thể được xét cho phép tại resource server đó. Tuy nhiên, với **Bearer access token** còn hạn, kẻ cầm token vẫn có thể thử thực hiện các hành động **nằm trong phạm vi thực sự được cấp**. Vì vậy, hai giá trị này là các lớp **least privilege**, không phải giải pháp chống phát lại token bị đánh cắp.

Bài thuộc chương **Client credentials** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Chúng ta sẽ xây dựng mô hình tin cậy cho service-to-service, phân biệt danh tính client với danh tính người dùng, hiểu scope được yêu cầu và scope thực tế được cấp, xác định audience/resource bằng RFC 8707 khi phù hợp, xác minh JWT hoặc opaque access token, triển khai Spring Security và kiểm thử các tình huống sai quyền, sai audience, lộ credential hoặc thu hồi.

## 1. Client Credentials grant dùng để làm gì?

**Client Credentials grant**, định nghĩa trong RFC 6749 §4.4, cho phép một **confidential client** được AS xác thực và nhận access token để truy cập tài nguyên thuộc quyền của chính client, hoặc trong phạm vi ủy quyền đã được sắp xếp trước với AS.

Đặc điểm chính:

- Client thường là **backend service, worker, scheduled job hoặc hệ thống tích hợp** có khả năng giữ credential của client tương đối an toàn.
- Không cần authorization endpoint, browser redirect, `response_type=code` hoặc người dùng bấm consent cho **mỗi lần xin token**.
- Client gọi trực tiếp **token endpoint** qua TLS với `grant_type=client_credentials`.
- AS xác thực client bằng phương thức đã đăng ký rồi quyết định **scope và resource/audience được cấp** theo chính sách.
- Access token được client trình đến **resource server (RS)**. RS vẫn phải xác minh token và phân quyền endpoint/tài nguyên.
- Theo RFC 6749, **refresh token thường không nên được cấp** cho Client Credentials grant; client có thể tự xin access token mới bằng credential của nó khi cần.

**Không đồng nhất service identity với user identity.** Token của `invoice-worker` chỉ thể hiện một client/service theo hợp đồng, không có nghĩa mọi thao tác đó do người dùng `user-123` trực tiếp ủy quyền trong phiên đăng nhập hiện tại.

### Ví dụ các hệ thống dùng client credentials

| Client | Công việc | Scope hợp lý theo thiết kế minh họa | Resource dự kiến |
|---|---|---|---|
| `invoice-worker` | Đọc đơn đã chốt để tạo hóa đơn | `orders.read` | Orders API |
| `inventory-sync` | Đọc thay đổi kho | `inventory.read` | Inventory API |
| `nightly-reporter` | Đọc dữ liệu tổng hợp báo cáo | `reports.read` | Reports API |
| `payment-reconciler` | Đối soát trạng thái thanh toán | `payments.reconcile` | Payments API |
| `order-admin-job` | Xử lý thao tác nghiệp vụ đặc quyền | Chỉ scope thao tác cần thiết, có policy bổ sung | Orders API |

Tên client/scope ở đây chỉ là ví dụ về hợp đồng ứng dụng, **không** phải các tên được OAuth chuẩn hóa.

## 2. Phân biệt client identity, principal và resource owner

Trong OAuth 2.0 có các vai trò **resource owner**, **client**, **authorization server** và **resource server**. Với Client Credentials:

- **Client** được AS xác thực tại token endpoint, ví dụ `client_id=invoice-worker`.
- **Resource owner** không nhất thiết là một end user đang tương tác; quyền truy cập có thể dựa trên tài nguyên của client hoặc một thỏa thuận ủy quyền trước.
- **AS** quyết định client có được nhận token cho resource và scope cụ thể hay không.
- **RS** quyết định token đó có được thực hiện request với dữ liệu cụ thể hay không.

```mermaid
sequenceDiagram
    autonumber
    participant C as invoice-worker / Confidential Client
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    participant DB as Orders Data
    C->>AS: POST /token grant_type=client_credentials
    Note over C,AS: Xác thực client + xin scope orders.read / resource Orders
    AS->>AS: Kiểm tra đăng ký client, quyền grant, scope và resource
    AS-->>C: Access token có audience/scope được cấp
    C->>RS: GET /api/orders/ready-to-invoice + Bearer token
    RS->>RS: Validate token, aud, scope, service policy
    RS->>DB: Truy vấn dữ liệu trong giới hạn cho phép
    DB-->>RS: Danh sách đơn hàng
    RS-->>C: Kết quả
```

### `sub` và `client_id` có đồng nghĩa không?

Không nên giả định chúng luôn đồng nhất:

- `client_id` định danh OAuth client đã được AS cấp quyền; trong profile JWT access token RFC 9068, claim này có ngữ nghĩa riêng.
- `sub` là subject theo hợp đồng issuer/profile. Với client credentials, nó có thể đại diện cho **client/service**; một số AS ánh xạ tới định danh khác.
- Không lấy `sub` của token service-to-service để suy rằng đây là một **người dùng cuối đã đăng nhập**.
- Nếu hệ thống có nhiều issuer/tenant, việc nhận diện principal cần ràng buộc **issuer + client identity + tenant/context** theo chính sách, thay vì chỉ tin một chuỗi `sub` tự do.

**Nguyên tắc:** service principal đủ quyền gọi API ở cấp dịch vụ **không tự có quyền của một user**. Nếu cần thao tác thay mặt người dùng, phải có cơ chế ủy quyền/delegation hoặc token exchange được AS hỗ trợ theo đúng thiết kế; không giả mạo user ID trong header.

## 3. Token request của Client Credentials

Một confidential client gọi **token endpoint** trực tiếp với `application/x-www-form-urlencoded`. Ví dụ rút gọn:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

grant_type=client_credentials&scope=orders.read
```

Header Basic chỉ là **placeholder** mô tả client authentication. Trong môi trường thật, AS có thể hỗ trợ `client_secret_basic`, `private_key_jwt`, mTLS hoặc phương thức khác theo đăng ký và profile. Không gửi client secret qua URL/query string hoặc ghi raw `Authorization` vào log.

Một response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Access token có thể là **JWT hoặc opaque**. Response không nhất thiết đưa `aud` ra ngoài JSON; audience có thể được biểu diễn trong JWT hoặc metadata từ introspection, tùy hợp đồng AS–RS. **Không suy diễn audience chỉ từ hostname của token endpoint.**

### Có thể bỏ `scope` trong request không?

Theo OAuth 2.0, `scope` trong token request là tham số tùy chọn. Khi client không yêu cầu scope cụ thể, AS có thể áp dụng **scope mặc định** hoặc từ chối theo policy. Với bảo mật:

- Không thiết kế mặc định “mọi scope của client” nếu công việc chỉ cần một quyền.
- Kiểm thử phạm vi **thực sự được cấp**, nhất là khi client không gửi `scope`.
- Đừng tự coi scope có trong client registration là scope đã được cấp cho token hiện tại.
- Khi scope trả về khác scope được yêu cầu, client phải xử lý **granted scope**, không bỏ qua sự thu hẹp quyền.

## 4. Scope là giới hạn loại hành động, không phải user role

Trong OAuth 2.0, **scope** biểu diễn phạm vi quyền truy cập mà AS cấp cho access token. Ý nghĩa cụ thể của chuỗi scope do hệ thống xác định và cần được **client–AS–RS thống nhất**.

Ví dụ một API đơn hàng:

| Scope | Hành động có thể được xét cho phép | Điều không tự động được cấp |
|---|---|---|
| `orders.read` | Đọc đơn hàng. | Không đọc mọi tenant, không sửa trạng thái. |
| `orders.create` | Tạo đơn hàng. | Không phê duyệt hoặc xóa đơn. |
| `orders.update` | Sửa dữ liệu đơn theo policy. | Không vượt quy tắc sở hữu/hạn mức. |
| `orders.approve` | Xét thao tác phê duyệt. | Không vượt quy tắc phân công hoặc kiểm tra hai người. |
| `orders.cancel` | Xét thao tác hủy đơn. | Không tự bỏ qua trạng thái đơn hoặc quyền tenant. |
| `orders.export` | Xuất dữ liệu trong phạm vi được phép. | Không mặc định xuất mọi thông tin nhạy cảm. |

**Scope không phải role:** `orders.approve` là một yêu cầu đối với hành động của token; role như `FINANCE_OPERATOR` hoặc `ORDER_MANAGER` có thể tồn tại ở policy khác. Client Credentials không tự có role người dùng cuối. RS có thể kết hợp scope với **service allowlist, role/authority đã được xác minh, tenant và chính sách nghiệp vụ**.

### Scope trong request và scope được cấp

Client có thể yêu cầu:

```text
scope=orders.read orders.approve
```

Nhưng AS chỉ cấp:

```text
scope=orders.read
```

Nếu client dùng token để gọi endpoint yêu cầu `orders.approve`, RS phải từ chối. Việc client từng yêu cầu scope đó **không phải bằng chứng được cấp quyền**.

AS cũng cần từ chối hoặc thu hẹp phạm vi khi client xin scope không thuộc quyền đăng ký. **Không để client tự chọn quyền bằng cách thêm chuỗi scope vào request**.

## 5. Scope có cú pháp và ngữ nghĩa cần so khớp chính xác

Theo OAuth 2.0, scope phổ biến được biểu diễn là **các token ngăn cách bằng một dấu cách**, và các scope values phân biệt chữ hoa/chữ thường.

Ví dụ:

```text
orders.read orders.update payments.read
```

Ở RS, nên parse thành **tập giá trị** rồi kiểm tra theo policy; không dùng so khớp chuỗi con:

```java
// Không an toàn: "orders.read-all" có thể chứa "orders.read".
boolean wrong = rawScope.contains("orders.read");

// Đúng: authorities/scopes đã parse từ access token được xác minh.
boolean hasRequired = grantedScopes.contains("orders.read");
```

Không tự diễn giải:

- `orders.*` được phép như wildcard nếu hệ thống không định nghĩa và thực thi ngữ nghĩa đó.
- `orders.read-all` tự bao gồm `orders.read`.
- `orders.write` tự bao gồm `orders.approve`.
- `Orders.Read` đồng nghĩa `orders.read`.
- `payments.charge` có thể dùng ở Orders API chỉ vì cùng issuer.

Nếu muốn dùng scope gộp hoặc mapping quyền, định nghĩa **policy rõ ràng tại RS/authorization layer**, không dựa vào tên trông gần giống nhau.

### AND và OR khi một route cần nhiều quyền

| Route/operation | Chính sách ví dụ | Cách hiểu |
|---|---|---|
| GET `/api/orders/{id}` | `orders.read` | Cần scope đọc. |
| POST `/api/orders/{id}/approve` | `orders.approve` | Cần scope phê duyệt. |
| POST `/api/orders/{id}/export` | `orders.read` **AND** `orders.export` | Phải có cả hai scope. |
| GET `/api/reports/summary` | `reports.read` **OR** quyền tương đương được policy định nghĩa | Đủ một trong các lựa chọn chính sách. |

**Không mặc định các scope luôn kết hợp bằng OR**. Route nghiệp vụ quyết định cần tất cả hay một trong số quyền; scope chỉ là đầu vào đã được xác minh.

## 6. Audience trả lời câu hỏi “token dành cho API nào?”

**Audience** xác định **bên nhận được dự kiến** của token, thường là claim `aud` trong JWT access token hoặc trường tương ứng trong introspection. Đối với access token, audience thường ràng buộc credential với một hoặc nhiều **resource servers**.

Giả sử có ba API:

| API | Resource identifier minh họa | Audience mà API kiểm tra |
|---|---|---|
| Orders API | `https://api.example.test/orders` | `https://api.example.test/orders` |
| Payments API | `https://api.example.test/payments` | `https://api.example.test/payments` |
| Inventory API | `https://api.example.test/inventory` | `https://api.example.test/inventory` |

Các chuỗi trên là **định danh logic/URI minh họa**, không bắt buộc endpoint thực tế có hostname/path đúng như identifier. AS và RS phải có **hợp đồng đồng nhất** về từng audience.

Một token có:

```json
{
  "iss": "https://id.example.test",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read"
}
```

**Orders API** có thể tiếp tục xem xét nếu token đã được xác minh và thỏa các điều kiện khác. **Payments API** phải từ chối vì audience không phù hợp, kể cả khi token có chữ ký đúng của cùng AS.

**Chỉ thêm `aud` vào token mà RS không kiểm tra thì audience không bảo vệ gì cả.**

### Audience không đồng nhất với client ID

Đây là một nhầm lẫn quan trọng:

- `client_id=invoice-worker` xác định **ai xin token**.
- `aud=https://api.example.test/orders` xác định **resource server nào dự kiến nhận token**.
- `scope=orders.read` xác định **những hành động nào được cấp quyền xét tới**.

Một JWT có `aud=invoice-worker` không tự phù hợp với Orders API chỉ vì invoice-worker là client đang gọi API; ngữ nghĩa này cần đúng theo **access-token profile** và hợp đồng AS–RS. Trong OIDC, `aud` của **ID token** lại hướng về **client/RP**. RS không được chấp nhận ID token như access token.

## 7. RFC 8707: chỉ định resource khi xin client credentials token

**OAuth 2.0 Resource Indicators** (RFC 8707) định nghĩa tham số `resource` giúp client nêu tài nguyên dự kiến sử dụng access token.

Ví dụ xin token cho Orders API:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

grant_type=client_credentials&scope=orders.read&resource=https%3A%2F%2Fapi.example.test%2Forders
```

Các điểm cần hiểu:

1. **AS phải hỗ trợ resource indicators** thì `resource` mới được xử lý theo chuẩn/hợp đồng.
2. `resource` là **định danh tài nguyên được yêu cầu**, không phải một lệnh buộc AS cấp bất kỳ audience do client chọn.
3. AS phải kiểm tra client có quyền xin token cho resource đó không; nếu không, từ chối hoặc xử lý theo chính sách.
4. AS có thể đặt audience của access token dựa vào resource indicator theo profile tương ứng; **RS chỉ tin audience thực tế đã được AS phát hành**.
5. Khi client không gửi `resource`, AS có thể áp dụng resource/audience mặc định theo đăng ký; mặc định quá rộng làm tăng blast radius.
6. Có thể có request chứa **nhiều resource indicators** nếu AS/flow hỗ trợ, nhưng việc phát token đa audience cần chính sách rõ và đánh giá rủi ro.

Với RFC 8707, resource identifier có định dạng URI tuyệt đối theo tiêu chuẩn; không tự tạo URI có fragment, không biến URL do user nhập thành resource được AS tin mà chưa có allowlist.

### Cách đặt audience theo nhu cầu

Một job chỉ đọc Orders API nên được cấp token có **một audience** dành cho Orders API. Nếu cùng job cần Payments API, cân nhắc **xin token riêng** cho resource Payments với scope chính xác, thay vì phát một token đa audience quyền rộng cho mọi API.

Không được giả định API gateway dùng chung hostname có nghĩa **mọi backend phía sau cùng là một audience**. Một gateway có thể xác thực đầu vào, nhưng từng resource server vẫn cần ranh giới authorization riêng.

## 8. Kết hợp scope và audience thành chính sách hai chiều

Một service có thể được phép đọc đơn hàng nhưng không được ghi; một token khác có thể được phép truy vấn Payments nhưng không được xử lý Orders. **Audience và scope là hai trục độc lập**.

| Token | Audience | Scope | GET Orders | Approve Orders | POST Payment |
|---|---|---|---|---|---|
| T1 | Orders API | `orders.read` | Có thể xét cho phép | Thiếu scope | Sai audience |
| T2 | Orders API | `orders.read orders.approve` | Có thể xét cho phép | Có thể xét cho phép | Sai audience |
| T3 | Payments API | `payments.read` | Sai audience | Sai audience | Thiếu scope thanh toán |
| T4 | Payments API | `payments.charge` | Sai audience | Sai audience | Có thể xét cho phép |
| T5 | Orders và Payments API | `orders.read payments.charge` | Có thể xét cho phép | Thiếu scope | Có thể xét cho phép |

Các chữ **“có thể xét cho phép”** có nghĩa **mới vượt qua kiểm tra audience/scope**, chưa có nghĩa đã được phép truy cập tài nguyên. RS còn kiểm tra issuer, chữ ký/trạng thái, thời hạn, service identity, tenant, data policy, hạn mức và các biện pháp nghiệp vụ khác.

```mermaid
flowchart TD
    Q[Client credentials access token tới Orders API] --> V{Credential hợp lệ và đúng token type?}
    V -- Không --> D[401: invalid_token]
    V -- Có --> A{aud chứa Orders API?}
    A -- Không --> D
    A -- Có --> S{scope đủ cho hành động?}
    S -- Không --> F[403: insufficient_scope]
    S -- Có --> C{Service principal được gọi operation này?}
    C -- Không --> N[403/404 theo policy]
    C -- Có --> T{Tenant, resource, hạn mức hợp lệ?}
    T -- Không --> N
    T -- Có --> P[PERMIT]
```

**Chữ ký hợp lệ không chứng minh audience/scope đúng.** Scope đúng không chứng minh client có quyền đọc dữ liệu của mọi tenant. Và một Bearer token đủ quyền vẫn có thể bị kẻ đánh cắp dùng trong phạm vi đó.

## 9. AS quyết định quyền cấp cho client như thế nào?

Một chính sách phát hành thực tế nên có **ma trận client–grant–resource–scope**:

| Client | Grant được phép | Resource được phép | Scope tối đa | Chính sách bổ sung |
|---|---|---|---|---|
| `invoice-worker` | `client_credentials` | Orders API | `orders.read` | Chỉ đơn “ready for invoice”; tenant được gán. |
| `inventory-sync` | `client_credentials` | Inventory API | `inventory.read` | Được đọc kho của miền nghiệp vụ tương ứng. |
| `payment-reconciler` | `client_credentials` | Payments API | `payments.read payments.reconcile` | Không có `payments.charge`. |
| `reporting-job` | `client_credentials` | Reports API | `reports.read` | Chỉ dữ liệu đã được phê duyệt xuất báo cáo. |

**Luồng cấp token nên kiểm tra:**

1. Client đã đăng ký và có hiệu lực hay không?
2. Phương thức xác thực client có hợp lệ với đăng ký không?
3. Client có được dùng `client_credentials` không?
4. Resource/audience được yêu cầu có thuộc danh sách client được phép không?
5. Các scope được yêu cầu có được cấp cho client **tại resource đó** không?
6. Chính sách tenant, hợp đồng đối tác, môi trường, thời hạn và assurance có cho phép không?
7. Token mới có được giới hạn **đúng phạm vi đã cấp**, không rộng hơn request/chính sách không?
8. Các sự kiện cấp token được audit an toàn mà không lưu raw secrets không?

Không nên xây dựng cơ chế phát token “AS nhận bất kỳ `scope` và `resource` nào do authenticated client gửi”. **Client authentication chỉ chứng minh client là ai; authorization grant policy quyết định client được làm gì và ở đâu**.

### Scope default cũng là quyền cần được kiểm soát

Nếu client không gửi scope, AS không nên tự cấp toàn bộ các quyền cấu hình chỉ vì đó là mặc định kỹ thuật. Các default scopes phải được review như bất kỳ quyền nào khác, đặc biệt ở client tích hợp đối tác và batch job ít được giám sát.

## 10. Token JWT trong Client Credentials: đọc claims đúng

Một access token JWT theo profile phù hợp có thể chứa payload minh họa:

```json
{
  "iss": "https://id.example.test",
  "sub": "service:invoice-worker",
  "client_id": "invoice-worker",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "iat": 1795410000,
  "exp": 1795410600,
  "jti": "random-token-reference"
}
```

Đây **chỉ là JSON payload ví dụ**, không phải JWT hoàn chỉnh được ký. Các mốc thời gian minh họa thời lượng 600 giây. Không dùng chuỗi token hoặc khóa ký thực trong tài liệu.

### Claims và giới hạn giải thích

| Claim | Ý nghĩa có thể dùng | Không nên suy diễn |
|---|---|---|
| `iss` | Issuer đã phát hành token. | Một issuer bất kỳ có HTTPS cũng đáng tin. |
| `client_id` | OAuth client được AS định danh theo profile. | Client này có mọi scope của AS. |
| `sub` | Subject/service principal theo hợp đồng AS. | Có một người dùng cuối đang đăng nhập. |
| `aud` | Resource server(s) được dự kiến nhận. | Chỉ cần chữ ký đúng là mọi API được nhận. |
| `scope` | Phạm vi quyền được cấp. | Quyền truy cập mọi tenant/bản ghi. |
| `exp`, `nbf`, `iat` | Quy tắc thời gian theo profile. | Token đã bị revoke chắc chắn bị RS biết ngay. |
| `jti` | Định danh token theo profile, hữu ích cho tương quan/denylist. | Có thể ghi raw token hoặc suy uniqueness toàn cầu nếu issuer không bảo đảm. |

RFC 9068 định nghĩa một **JWT Profile for OAuth 2.0 Access Tokens**, bao gồm các kiểm tra đặc thù như token type, issuer, audience và claims. Nhưng không phải mọi JWT do AS phát đều nhất thiết theo RFC 9068; RS phải dùng profile đã được AS và RS thống nhất, không tự động áp một schema sai cho mọi provider.

**Đặc biệt:** trong client credentials, nếu `sub` là định danh của service, không được ánh xạ nó thành tên người dùng cuối trong audit hay business authorization. Nếu API chỉ cho người dùng cuối gọi một route, cần policy từ chối service token ở route đó.

## 11. Opaque token vẫn cần audience và scope

Một AS có thể phát opaque access token thay cho JWT. RS không nên tự Base64-decode hay đoán quyền từ chuỗi opaque; có thể dùng **RFC 7662 Token Introspection** từ AS tin cậy.

Ví dụ response introspection:

```json
{
  "active": true,
  "iss": "https://id.example.test",
  "client_id": "invoice-worker",
  "sub": "service:invoice-worker",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "exp": 1795410600
}
```

Phía RS cần:

- Kết nối tới introspection endpoint **đã được cấu hình tin cậy**, có xác thực/ủy quyền caller và TLS.
- Kiểm tra `active=true` cùng claims/metadata mà chính sách bắt buộc.
- Kiểm tra **audience và scope giống như với JWT**, không chỉ vì AS trả HTTP 200.
- Phân biệt service principal và user principal, kiểm tra tenant/resource policy.
- Đặt TTL caching cẩn thận: cache `active=true` có thể trì hoãn hiệu lực revoke.
- Khi AS/introspection lỗi, không mặc định cho phép mọi request; áp dụng fail-closed hoặc cache đã xác minh còn hợp lệ theo chính sách.

Một số trường ngoài `active` là **optional trong RFC 7662**. Nếu thiếu thông tin cần thiết để xác minh audience/scope/client thì RS phải có cơ chế tin cậy khác hoặc từ chối, không “coi thiếu scope nghĩa là mọi scope”.

## 12. Resource server phải xác minh những gì?

Tại Orders API, kiểm tra nên bao gồm các lớp:

1. **Định dạng và loại token:** chỉ nhận access token theo profile AS–RS, không dùng refresh token hoặc ID token.
2. **Issuer/trust anchor:** issuer nằm trong allowlist; không lấy JWKS từ URL do token/header tự chỉ định.
3. **Tính xác thực:** JWT signature và allowlist thuật toán/khóa; hoặc opaque introspection/status tin cậy.
4. **Thời hạn và trạng thái:** `exp`, `nbf` nếu áp dụng, revocation/denylist khi cần.
5. **Audience:** token dành cho Orders API; so khớp **chính xác** resource identifier.
6. **Scope:** token có các scope cần cho operation, so khớp atomic và phân biệt chữ hoa/thường.
7. **Client/service policy:** client có được thực hiện operation đó hay chỉ user có quyền?
8. **Tenant và đối tượng:** đơn hàng, tài nguyên thuộc tenant/đơn vị mà service được phép truy cập?
9. **Hạn mức/rate limit và điều kiện nghiệp vụ:** không tự phát sinh quyền từ token.
10. **Audit:** ghi issuer/client, action, resource và quyết định mà không lộ raw token.

Không dùng quy tắc kiểu:

```java
// Nguy hiểm: bỏ kiểm tra aud, scope và policy.
if (jwtSignatureValid) {
    allowEverything();
}
```

Chữ ký JWT chỉ chứng minh token chưa bị sửa và được ký bởi khóa tương ứng, **không tự chứng minh token dành cho API này hoặc có đủ quyền**.

## 13. Spring Security 6.x: OAuth client dùng Client Credentials

Một backend Spring Boot có thể cấu hình OAuth2 Client registration cho service-to-service:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          invoice-worker:
            provider: internal-idp
            client-id: "INVOICE_WORKER_CLIENT_ID"
            client-secret: "CLIENT_SECRET_FROM_SECRET_STORE"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: orders.read
        provider:
          internal-idp:
            issuer-uri: "https://id.example.test"
```

Các giá trị `INVOICE_WORKER_CLIENT_ID`/`CLIENT_SECRET_FROM_SECRET_STORE` là **placeholder**, không phải secret thực. Trong sản phẩm, lấy secret từ biến môi trường/secret manager theo quản trị phù hợp; không commit vào git, container image hay file cấu hình công khai.

**Quan trọng:** cấu hình `scope: orders.read` không có nghĩa Spring OAuth2 Client mặc định đã gửi **`resource=https://api.example.test/orders`** theo RFC 8707. Cần AS hỗ trợ và cấu hình/hợp đồng riêng cho resource indicator hoặc ánh xạ audience cho client. Đừng giả định audience chỉ vì đã đăng ký scope.

### Dùng `OAuth2AuthorizedClientManager` cho service job

Ở servlet/backend không gắn với một HTTP user request, một mẫu phổ biến là:

```java
@Configuration
public class ServiceTokenClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Đây là cấu hình minh họa Spring Security 6.x, bỏ `import` và cấu hình persistence. Nó cho phép manager dùng Client Credentials provider; **chưa tự giải quyết** hạn quyền theo audience, bảo vệ client secret, đồng bộ cache giữa node, mTLS/private_key_jwt, backoff, auditing và xử lý token endpoint outage.

Mẫu sử dụng service principal để xin access token:

```java
@Service
public class InvoiceOrdersClient {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient restClient = RestClient.create();

    public InvoiceOrdersClient(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String loadReadyOrders() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                    .withClientRegistrationId("invoice-worker")
                    .principal("invoice-worker-service")
                    .build();

        OAuth2AuthorizedClient authorized = manager.authorize(request);
        if (authorized == null || authorized.getAccessToken() == null) {
            throw new IllegalStateException("Access token unavailable");
        }

        String accessToken = authorized.getAccessToken().getTokenValue();

        return restClient.get()
                .uri("https://api.example.test/orders/ready-to-invoice")
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
    }
}
```

Ví dụ dùng `RestClient` của Spring Framework 6.1+ và giả định response là String; không phải client production đầy đủ. Các ứng dụng thật cần endpoint URLs từ cấu hình đáng tin, TLS, timeout/retry/circuit breaker, không log header/token, cache/isolation theo client+principal, handling 401/403 và business data authorization. Manager có thể tái sử dụng authorized client theo cách lưu trữ được cấu hình. Trong hệ thống đa node cần đánh giá token cache, race và quyền truy cập storage.

**Không dùng principal giả dạng user** ở `OAuth2AuthorizeRequest` để ám chỉ token mang quyền của user. Chuỗi principal ở đây phục vụ khóa quản lý authorized client trong OAuth2 Client machinery; bản chất grant vẫn là **client credentials**.

## 14. Spring Security 6.x: RS kiểm tra audience và scope

Một Orders API chấp nhận JWT access token cần kiểm tra audience **ngoài issuer và signature**. Ví dụ policy yêu cầu `aud=https://api.example.test/orders`:

```java
@Configuration
@EnableMethodSecurity
public class OrdersApiSecurity {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.test";
        String expectedAudience = "https://api.example.test/orders";

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = token -> {
            boolean matches = token.getAudience() != null
                    && token.getAudience().contains(expectedAudience);

            return matches
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Audience mismatch", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/*/approve")
                .hasAuthority("SCOPE_orders.approve")
            .anyRequest().denyAll());

        http.oauth2ResourceServer(rs ->
            rs.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

**Lưu ý thứ tự route matcher:** trong đoạn trên, `GET /api/orders/**` và `POST /api/orders/*/approve` có method khác nhau nên không chồng lấn. Với nhiều routes cùng method, khai báo matcher từ cụ thể tới tổng quát; tránh một broad matcher mở quyền hơn dự định. `anyRequest().denyAll()` giúp chặn route chưa được khai báo policy.

Đây là **mẫu minh họa**, không phải full production policy. Cần kiểm tra access-token type/profile (ví dụ RFC 9068 khi phù hợp), thuật toán ký, JWKS, clock skew, service-principal policy, đa issuer, tenant và object authorization. Với opaque token, cấu hình `OpaqueTokenIntrospector` và kiểm tra audience từ metadata tin cậy; `active=true` cùng scope mapping mặc định **không tự chứng minh audience phù hợp**.

### Spring scope mapping

Spring Security thường chuyển `scope`/`scp` từ access token đã được xác minh thành `GrantedAuthority` dạng:

```text
scope claim: "orders.read orders.approve"

authorities:
  SCOPE_orders.read
  SCOPE_orders.approve
```

Tiền tố `SCOPE_` là quy ước framework, **không phải tiền tố AS bắt buộc chèn trong access token**. Một AS có schema custom phải được ánh xạ đúng bằng converter và test thật.

## 15. Scope và audience vẫn chưa đủ: service-level authorization

Giả sử token có audience Orders API và scope `orders.read`, nhưng service chỉ được đọc đơn thuộc tenant `tenant-a`. Nếu API tin tham số query tùy ý:

```http
GET /api/orders?tenant=tenant-b HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
```

rồi trả dữ liệu `tenant-b`, API đã mắc lỗi **Broken Object Level Authorization (BOLA)/tenant isolation**. Scope cho phép *loại hành động*, không tự mô tả *toàn bộ bản ghi được phép*.

Một thiết kế nên áp dụng:

- Ánh xạ **issuer + client identity** thành một service principal nội bộ.
- Kiểm tra principal có trong **allowlist/policy** cho operation đang gọi.
- Ánh xạ **tenant hoặc organization** từ nguồn đã xác minh, không tin header `X-Tenant-Id` do caller tùy ý tự khai.
- Tự động lọc dữ liệu ở repository/service layer theo phạm vi tenant/partner được phép.
- Xác minh quan hệ đối tượng và điều kiện nghiệp vụ (trạng thái, hạn mức, thời gian).
- Dùng **least privilege** cho service account; không lấy account quản trị toàn cục làm mặc định cho mọi job.
- Đối với đa tenant, có thể chọn **client riêng mỗi tenant** hoặc ràng buộc tenant trong token/policy server-side theo threat model.

Ví dụ pseudocode service:

```java
public List<Order> readReadyOrders(
        VerifiedServicePrincipal principal) {

    requireScope(principal, "orders.read");
    requireClientAllowed(principal.issuer(), principal.clientId());
    Set<String> permittedTenants = servicePolicy.tenantsFor(principal);

    return orderRepository.findReadyForInvoicing(permittedTenants);
}
```

Các class/function này **là pseudocode của hệ thống**, không phải Spring APIs có sẵn. Ý chính: danh sách tenant đến từ **policy tin cậy**, không phải một query parameter do service tự gửi.

## 16. Khi một service gọi nhiều API: không forward sai audience

Ví dụ invoice-worker cần:

1. Đọc Orders API với `orders.read`.
2. Ghi kết quả đối soát vào Payments API với `payments.reconcile`.

Thiết kế hợp lý:

```mermaid
flowchart LR
    W[invoice-worker] -->|Client Credentials: resource Orders, scope orders.read| AS[Authorization Server]
    AS -->|AT-Orders aud Orders| W
    W -->|Bearer AT-Orders| O[Orders API]
    W -->|Client Credentials: resource Payments, scope payments.reconcile| AS
    AS -->|AT-Payments aud Payments| W
    W -->|Bearer AT-Payments| P[Payments API]
```

Tránh phương án lấy **AT-Orders** rồi chuyển tiếp nó tới Payments API để “đỡ xin token thứ hai”. Payments API phải từ chối vì `aud` sai.

### Multi-audience token

JWT có thể có nhiều audience:

```json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/payments"
  ],
  "scope": "orders.read payments.reconcile"
}
```

Không có nghĩa token đa audience luôn không hợp lệ. Nếu AS/RS có chính sách chấp nhận, mỗi API có thể xử lý token theo audience của mình. Tuy nhiên, **một token bị lộ có thể bị dùng ở nhiều API**, nên cần đánh giá blast radius. Khi không có nhu cầu rõ, thường **token theo từng resource** dễ cô lập quyền và thu hồi hơn.

Đối với dịch vụ **A gọi B thay mặt người dùng**, đó không còn đơn thuần là “chuyển tiếp Client Credentials token”. Có thể cần **OAuth 2.0 Token Exchange** (RFC 8693) hoặc grant/ủy quyền khác được AS hỗ trợ để giữ đúng ranh giới user delegation và target audience.

## 17. Access token vs refresh token trong Client Credentials

Client Credentials thường dùng trực tiếp client authentication để xin access token mới khi cần:

```text
Client giữ credential đăng ký (secret/key/certificate)
   -> POST token endpoint với grant_type=client_credentials
   -> nhận access token ngắn hạn
   -> gọi API
   -> token sắp hết hạn
   -> gọi token endpoint lại bằng client credential
```

**Theo RFC 6749 §4.4.3, refresh token SHOULD NOT được đưa vào response Client Credentials.** Đây là khuyến nghị chuẩn, không phải khẳng định toán học rằng mọi AS đều không thể cấp trong mọi extension. Không giả định client credentials token response có refresh token, và cũng không tự nhúng một refresh token của người dùng vào service job.

Ba credential khác nhau:

| Credential | Bên nhận | Bảo vệ |
|---|---|---|
| **Client secret/private key/certificate** | AS token endpoint khi client authentication. | KMS/secret manager/HSM hoặc kho phù hợp, rotation, phân quyền, không nhúng vào client public. |
| **Access token** | Resource server có audience phù hợp. | HTTPS, TTL ngắn, scope/aud hẹp, không log, sender constraint khi cần. |
| **Refresh token** (nếu hệ thống có trong flow khác) | AS token endpoint. | Rotation/sender constraint, grant binding, revocation, lưu an toàn. |

**Bảo vệ client credential quan trọng hơn chỉ bảo vệ một access token.** Nếu kẻ tấn công đánh cắp client secret hoặc private key có thể xác thực dưới danh nghĩa client, họ có thể liên tục xin access token mới theo quyền của client cho đến khi credential bị thu hồi/thay đổi hoặc chính sách AS chặn.

## 18. Phương thức client authentication và token theft

Client Credentials dựa vào AS xác thực client theo một cơ chế đã đăng ký. Một số lựa chọn:

| Phương thức | Cách chứng minh client | Ưu điểm / giới hạn |
|---|---|---|
| `client_secret_basic` | Gửi client ID/secret trong HTTP Basic qua TLS. | Dễ tích hợp; secret đối xứng dễ bị sao chép, cần vault và rotation. |
| `client_secret_post` | Gửi secret trong form body theo hợp đồng AS. | Có thể tăng nguy cơ body logging; cần redaction và TLS. |
| `private_key_jwt` | Client ký JWT client assertion bằng private key tin cậy. | Giảm việc gửi secret đối xứng; cần quản lý khóa, replay prevention, `aud`/`exp` của assertion. |
| **mTLS client authentication** | Client chứng minh private key của chứng chỉ qua TLS. | Bảo vệ mạnh trong hạ tầng có quản lý cert, nhưng cần proxy/cert lifecycle đúng. |

**Client assertion dùng để xác thực client tại token endpoint khác JWT access token gửi API.** `aud` trên assertion thường chỉ đúng token endpoint/AS theo profile; `aud` trên access token dành cho resource server. Không được dùng access token làm client assertion hoặc ngược lại.

Các biện pháp cơ bản:

- Mỗi service có **client identity riêng**, tránh chia sẻ một secret toàn tổ chức.
- Lưu secret ở **secret manager**, giới hạn đọc theo workload identity, không đặt vào repo/docker image/log.
- Xoay vòng credentials theo quy trình, có thể hỗ trợ overlap ngắn được kiểm soát để triển khai không gián đoạn.
- Với private key, bảo vệ signing operations, giới hạn algorithms và ngăn assertion replay theo yêu cầu profile.
- Giới hạn rate/quota token issuance, quan sát bất thường theo client ID.
- Khi credential bị lộ, phải thu hồi/đổi credential và đánh giá access tokens đã cấp, không chỉ xóa cache client.

## 19. Scope/audience giảm thiệt hại nhưng không chống Bearer replay

Giả sử kẻ tấn công lấy được:

```text
AT-1: aud = Orders API
      scope = orders.read
      expires_in ≈ 10 minutes
```

Nếu RS kiểm tra đúng:

- `Payments API` từ chối AT-1 vì **sai audience**.
- `POST /api/orders/42/approve` từ chối vì **thiếu orders.approve**.
- `GET /api/orders/42` **vẫn có thể thành công** nếu service principal được phép đọc đơn đó.

Do đó, hạn chế audience/scope là cách **thu nhỏ blast radius**, không phải biện pháp phân biệt người trình token hợp pháp với kẻ đã đánh cắp bản sao Bearer token.

Các biện pháp bổ sung:

1. **HTTPS/TLS** giữa client–AS và client–RS; xác minh server certificate.
2. **Access token sống ngắn**, đặc quyền tối thiểu, không cấp multi-audience quá rộng.
3. **Token storage kín**, không ghi raw token vào logs, traces, error reports, URLs hoặc ticket hỗ trợ.
4. **Sender-constrained access token** như mTLS certificate-bound tokens (RFC 8705) hoặc DPoP (RFC 9449) khi AS/RS/client hỗ trợ đúng profile.
5. **Revocation/denylist/introspection** theo rủi ro; đánh giá JWT tự chứa còn sống đến `exp` nếu không có kênh thu hồi.
6. **Audit/rate limiting/alerting** theo client, issuer, audience, operation và tenant.
7. **Credential rotation và blast-radius review** nếu client secret/private key bị lộ.

Sender-constrained tokens cũng có giới hạn: nếu kẻ tấn công có cả token và private key liên kết, hoặc kiểm soát runtime client, vẫn có nguy cơ lạm dụng. DPoP/mTLS không thay kiểm tra audience, scope hoặc quyền đối tượng.

## 20. 401 và 403 khi API nhận client credentials access token

| Tình huống | Kết quả thường gặp | Vì sao |
|---|---|---|
| Không gửi access token tới API bảo vệ | `401 Unauthorized` | Thiếu credential. |
| Token sai chữ ký, issuer, loại, audience, đã hết hạn | `401 Unauthorized` | Token không hợp lệ đối với RS này. |
| Opaque introspection trả `active=false` | `401 Unauthorized` | Token không còn được AS công nhận. |
| Token hợp lệ nhưng thiếu `orders.read` | `403 Forbidden` | Có credential nhưng không đủ scope. |
| Token đủ scope nhưng service không được truy cập tenant | `403` hoặc `404` | Policy tài nguyên/tenant từ chối. |
| Token đủ scope nhưng operation chỉ dành cho user | `403 Forbidden` | Client service không đáp ứng principal-type policy. |

Theo RFC 6750, có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

hoặc khi token hợp lệ nhưng thiếu quyền:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.approve"
```

Khi **không có token**, challenge thường không cần gán `invalid_token`. Không trả raw token, client secret hoặc các claims nhạy cảm trong error body/log để debug.

**Token endpoint có mã lỗi khác resource API:** khi client authentication thất bại có thể là `invalid_client`; grant/scope/resource không hợp lệ có thể dẫn đến `unauthorized_client`, `invalid_scope`, `invalid_target` (với RFC 8707) hoặc lỗi khác theo ngữ cảnh. Không coi mọi lỗi token endpoint là một HTTP `401 invalid_token` của API.

## 21. Những lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng `client_credentials` để giả lập đăng nhập user. | Audit/user authorization bị sai, lộ dữ liệu người dùng. | Xem client là service principal; dùng user delegation khi cần. |
| Cấp `scope=admin` làm mặc định cho mọi service. | Token bị lộ có quyền quá rộng. | Scope granular theo operation và client policy. |
| AS cấp mọi scope mà client yêu cầu sau khi xác thực. | Client bị chiếm có thể xin thêm quyền. | Ma trận grant/resource/scope ở AS. |
| Không kiểm audience tại RS. | Token của API khác có thể bị dùng chéo. | Exact audience validation. |
| Dùng `client_id` thay `aud` khi chọn RS. | Nhầm bên xin token với bên nhận. | Phân biệt client ID và resource identifier. |
| So chuỗi con scope `contains("orders.read")`. | Dễ nhận nhầm `orders.read-all`. | Parse tập và so khớp atomic. |
| Chỉ kiểm scope, bỏ tenant/owner. | BOLA hoặc rò dữ liệu liên tenant. | Business authorization ở service/repository. |
| JWT có chữ ký hợp lệ thì cho mọi request. | Bỏ issuer/type/time/aud/scope. | Validation theo access-token profile đầy đủ. |
| Opaque `active=true` thì cho qua bất kể audience. | Nhận token dành cho API khác. | Validate introspection metadata và authorization. |
| Forward Orders token tới Payments API. | Sai audience, tăng token exposure. | Xin token phù hợp cho Payments. |
| Dùng một token đa audience cho mọi dịch vụ. | Một lần lộ ảnh hưởng nhiều resource servers. | Token hẹp theo resource nếu khả thi. |
| Lưu client secret trong source repo hoặc image. | Kẻ lấy secret có thể xin nhiều token mới. | Secret manager và credential rotation. |
| Nhúng client secret vào SPA/mobile và coi là confidential. | Secret có thể bị trích xuất. | Client credentials dùng workload có khả năng giữ credential. |
| Refresh token được giả định luôn có trong response. | Client token lifecycle sai chuẩn. | Client credentials thường xin access token mới bằng client auth. |
| Không xử lý cache/clock skew/revoke. | Token có thể được chấp nhận sau khi bị thu hồi. | TTL, revocation policy và cache invalidation khi cần. |
| Log `Authorization` hoặc client assertion. | Lộ credential và replay. | Redact, dùng trace/token references an toàn. |
| Scope cấp quyền tác vụ nhạy cảm không có business checks. | Leo thang quyền dù token đủ scope. | Hạn mức, tách nhiệm vụ, approval và policy kiểm toán. |

## 22. Ma trận kiểm thử client scope and audience

Giả sử AS tin cậy có issuer `https://id.example.test`, `invoice-worker` chỉ được xin `orders.read` cho `https://api.example.test/orders`, access token sống 10 phút; Orders API có kiểm tra audience, scope và tenant.

| ID | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| CC01 | Client xác thực hợp lệ, xin `client_credentials` với `orders.read` và resource Orders. | AS cấp token nếu policy cho phép. |
| CC02 | Client secret sai hoặc client bị khóa. | AS từ chối client authentication. |
| CC03 | Public client không được cấp quyền Client Credentials thử gọi token endpoint. | AS từ chối theo client/grant policy. |
| CC04 | Client `invoice-worker` xin `orders.approve` ngoài quyền. | AS từ chối hoặc không cấp scope vượt policy. |
| CC05 | Client xin `payments.charge` cho Payments API ngoài resource allowlist. | AS từ chối hoặc xử lý theo policy, không tự cấp quyền. |
| CC06 | Client không gửi `scope`. | Áp dụng default được review hoặc từ chối, không mặc định full privilege. |
| CC07 | AS cấp scope hẹp hơn scope yêu cầu. | Client/RS chỉ dùng scope đã được cấp. |
| CC08 | Token `aud=Orders` gọi Orders GET với `orders.read`. | Có thể được cho phép nếu policy còn lại thỏa. |
| CC09 | Token `aud=Orders` gửi tới Payments API. | Payments từ chối do sai audience. |
| CC10 | Token `aud=Payments` gửi tới Orders API dù chữ ký đúng. | Orders từ chối. |
| CC11 | Token đúng audience nhưng thiếu `orders.approve`. | Endpoint approve từ chối `403`. |
| CC12 | Token có scope `orders.read-all`, route yêu cầu `orders.read`. | Từ chối nếu không có explicit mapping. |
| CC13 | Token có `Orders.Read` thay vì `orders.read`. | Không tự coi tương đương. |
| CC14 | Token JWT đúng audience nhưng sai chữ ký. | RS từ chối. |
| CC15 | Token JWT đúng chữ ký nhưng issuer không nằm trong allowlist. | RS từ chối. |
| CC16 | Token hết hạn hoặc `nbf` chưa tới. | RS từ chối theo time policy. |
| CC17 | ID token OIDC được gửi thay access token. | RS từ chối sai token type/audience. |
| CC18 | Refresh token được gửi vào business API. | RS từ chối sai mục đích token. |
| CC19 | Opaque introspection `active=true` nhưng audience khác. | RS từ chối. |
| CC20 | Opaque introspection `active=false`. | RS từ chối. |
| CC21 | AS/introspection không khả dụng và không có cache hợp lệ. | RS không tự `PERMIT`. |
| CC22 | Token có đúng scope nhưng client không có service-level policy. | RS từ chối. |
| CC23 | Token có `orders.read` nhưng query tenant khác. | RS từ chối theo tenant/owner. |
| CC24 | Client credentials token gọi route chỉ dành cho logged-in user. | RS từ chối theo principal-type policy. |
| CC25 | Client cố gắn header `X-User-Id` để giả user. | RS bỏ qua hoặc kiểm tra trong nguồn ủy quyền tin cậy; không impersonate. |
| CC26 | Client cần Orders và Payments, dùng token riêng cho hai resources. | Cả hai API nhận đúng token/audience; không cross-use. |
| CC27 | Multi-audience token được phát theo policy. | Test từng API, phạm vi quyền và rủi ro blast radius. |
| CC28 | Token Bearer bị sao chép nhưng còn hiệu lực. | Kẻ giữ token có thể dùng trong aud/scope được cấp nếu không có sender constraint. |
| CC29 | mTLS/DPoP-bound access token thiếu bằng chứng người gửi phù hợp. | RS từ chối. |
| CC30 | Client secret bị lộ; AS chỉ revoke access token hiện tại. | Test phát hiện nguy cơ attacker xin token mới bằng credential cũ; cần rotate/revoke client credential. |
| CC31 | JWT token bị revoke nhưng RS chỉ xác minh chữ ký/`exp`. | Test thể hiện cửa sổ hiệu lực còn lại nếu không có denylist. |
| CC32 | Introspection cache `active=true` sau revoke. | Đánh giá độ trễ theo TTL/invalidation; không tuyên bố thu hồi tức thì. |
| CC33 | Scope trong Spring converter không ánh xạ đúng authority. | Integration test bắt lỗi, không mở route mặc định. |
| CC34 | Route mới không có matcher/permission. | `anyRequest().denyAll()` chặn. |
| CC35 | Client secret/access token xuất hiện trong log/tracing. | Redaction/security test báo lỗi. |
| CC36 | Client_credentials API rate limiting theo service/tenant. | Ngăn quá tải theo policy mà không thay authorization. |
| CC37 | AS chấp nhận `resource` tùy ý không ràng buộc client. | Security test phát hiện, yêu cầu resource allowlist. |
| CC38 | Access token mới với scope rộng hơn grant/đăng ký client. | AS phải từ chối/giới hạn; không leo thang quyền. |

### Kiểm thử ở nhiều lớp

- **AS/token endpoint integration tests:** client authentication, grant permissions, resource indicators, cấp scope thực tế, JWT/opaque issuance, TTL và lỗi grant/resource.
- **Resource server integration tests:** JWT signature, issuer, `aud`, type/time, scope, opaque introspection, tenant/owner/service policy.
- **Spring Security authorization tests:** endpoint matcher, `SCOPE_` mapping, default deny; đừng nhầm mock principal với JWT validation thật.
- **Secret/storage tests:** scanning git/config, vault access policy, secret rotation, log redaction, timeout và thu hồi.
- **Security/incident tests:** token theft, multi-audience, replay, denylist/introspection caching, DPoP/mTLS proof validation.
- **Service-to-service end-to-end tests:** Orders token không dùng tại Payments, service job không giả user và audit phân biệt client principal với user principal.

Dùng `@WithMockUser` hoặc Spring Security Test `jwt()` có thể chứng minh rule/authority đã được mapping, **không chứng minh access JWT thực tế có chữ ký/audience hợp lệ hoặc AS đã kiểm scope trước khi phát hành**. Cần thử token thật được ký bởi AS kiểm thử hoặc introspection mock theo hợp đồng rõ.

## 23. Audit và ứng phó khi credential bị lộ

Các sự kiện có thể ghi: `CLIENT_TOKEN_REQUESTED`, `CLIENT_AUTH_FAILED`, `TOKEN_ISSUED`, `AUDIENCE_MISMATCH`, `SCOPE_DENIED`, `SERVICE_POLICY_DENIED`, `CLIENT_CREDENTIAL_ROTATED` hoặc `TOKEN_REVOKED`.

| Dữ liệu audit | Mục đích |
|---|---|
| `trace_id`, `event_id`, thời điểm UTC | Liên kết các request giữa AS, client và RS. |
| `issuer`, `client_id` đã xác minh | Xác định service principal đáng tin. |
| `resource/audience`, granted scope references | Hiểu phạm vi token và quyết định policy. |
| `operation`, `tenant_ref`, `resource_ref` | Điều tra ảnh hưởng dữ liệu. |
| `decision`, `reason_code`, `policy_version` | Phân biệt token invalid với thiếu scope hoặc sai tenant. |
| `grant_ref`, token reference/digest an toàn | Tương quan vòng đời mà không lưu raw token. |

**Không ghi raw access token, client secret, private key, mTLS private key, client assertion JWT hoặc header Authorization**. Một hệ thống logging có thể được nhiều nhóm đọc; lưu bí mật ở đó làm tăng nguy cơ đánh cắp/replay.

### Khi phát hiện token bị lộ

1. Chặn nguồn rò rỉ, redact logs/tracing, giới hạn quyền đọc và xóa các bản sao theo quy trình dữ liệu.
2. Xác định issuer, client identity, audience, scope, thời điểm phát hành/hết hạn và RS liên quan bằng nguồn đã xác minh.
3. Thu hồi token/grant theo khả năng AS; áp dụng denylist/introspection invalidation nếu cần.
4. Xem **request đã được PERMIT**, không chỉ những request 401/403 bị chặn.
5. Đánh giá mức độ truy cập business data/tenant và tác động nghiệp vụ trong khoảng token còn hợp lệ.
6. Nếu **client secret/private key** bị lộ, xoay/thu hồi chính credential, xử lý token đã cấp và các client/services liên quan.
7. Cập nhật least privilege: giảm scopes, audience, TTL và cải thiện sender constraint khi phù hợp.

Một access token JWT tự chứa đã phát hành có thể vẫn được RS chấp nhận đến `exp` nếu RS không có cơ chế kiểm tra revoke riêng. Thu hồi client secret ngăn xin token mới nhưng **không bảo đảm mọi access token cũ lập tức vô hiệu**.

## 24. Tình huống thực hành

### Tình huống A — Token hợp lệ nhưng sai audience

`invoice-worker` được cấp token `aud=https://api.example.test/orders`, `scope=orders.read`. Do tiện xử lý, service chuyển cùng token đến `https://api.example.test/payments`.

**Câu hỏi:** Payments API có thể cho phép vì cùng AS phát token không?

> **Không.** Audience ràng buộc token với resource được cấp. Payments API phải từ chối token không có audience của mình, dù issuer/chữ ký vẫn hợp lệ.

### Tình huống B — Scope request không phải grant

Client gửi `scope=orders.read orders.approve` nhưng AS response cho biết chỉ cấp `orders.read`. Job gọi route approve.

**Câu hỏi:** Có thể dựa vào scope từng yêu cầu không?

> **Không.** Scope thực sự được cấp nằm trong access token/metadata đã xác minh. Orders API phải từ chối approve vì thiếu `orders.approve`.

### Tình huống C — Service token bị coi là user token

Service có token `client_id=invoice-worker` và `sub=service:invoice-worker`. API yêu cầu user đang đăng nhập, nhưng code dùng `sub` làm user ID.

**Câu hỏi:** Rủi ro gì?

> Sai ngữ nghĩa principal, có thể dẫn đến impersonation/authorization bypass hoặc audit sai. API cần phân biệt service với end user và chọn grant/delegation phù hợp khi phải hành động thay người dùng.

### Tình huống D — AS cấp nhiều audience mặc định

Một AS phát token cho cả Orders, Payments và Inventory dù client chỉ cần Orders. Token bị ghi vào log gateway.

**Câu hỏi:** Làm thế nào giảm phạm vi thiệt hại?

> Cấu hình resource/scope policy để token dành riêng Orders API khi khả thi; dùng TTL ngắn, redaction và thu hồi. Khi kẻ tấn công có token đa audience, mọi API chấp nhận nó đều có thể bị ảnh hưởng trong phạm vi scope.

### Tình huống E — Secret bị lộ, chỉ xóa token cache

Người vận hành phát hiện client secret của `invoice-worker` bị commit. Họ xóa access token khỏi cache của job và khởi động lại service.

**Câu hỏi:** Sự cố đã kết thúc chưa?

> **Chưa.** Kẻ có secret vẫn có thể xin access token mới tại AS. Phải thu hồi/rotate client credential, điều tra access tokens đã cấp, giới hạn grant và chặn nguồn lộ.

### Tình huống F — JWT tự chứa sau revoke

AS revoke grant của `invoice-worker` nhưng Orders API chỉ kiểm chữ ký, audience và `exp` của JWT hiện có.

**Câu hỏi:** API có biết grant đã revoke ngay không?

> **Không chắc.** JWT vẫn có thể qua validation đến `exp` nếu thiếu denylist hoặc kiểm tra trạng thái. Cần cam kết revocation latency rõ và cơ chế enforcement phù hợp.

### Tự kiểm tra

1. `client_credentials` đại diện cho client hay người dùng cuối? Khi nào cần delegation khác?
2. Vì sao client authentication không đồng nghĩa client được xin mọi scope/resource?
3. Khác biệt giữa requested scope và granted scope trong token response là gì?
4. Audience của access token khác client ID và audience của ID token thế nào?
5. RFC 8707 `resource` giúp giải quyết vấn đề gì, và AS vẫn phải kiểm tra điều gì?
6. Vì sao nên xin hai access tokens hẹp cho hai APIs thay vì forward một token đa audience?
7. JWT có chữ ký đúng nhưng `aud` sai phải bị RS xử lý thế nào?
8. Opaque token có `active=true` đã đủ để cho phép API chưa?
9. Vì sao scope `orders.read` không tự cho đọc đơn của mọi tenant?
10. Client Credentials token có nên chứa refresh token theo RFC 6749 không?
11. Bị lộ access token khác gì bị lộ client secret/private key?
12. JWT access token và opaque token khác nhau thế nào về revocation/caching?
13. DPoP/mTLS giúp giới hạn việc phát lại token ở điều kiện nào?
14. Vì sao test scope mapping bằng mock principal chưa chứng minh signature/audience validation?

## 25. Ghi nhớ

- **Client Credentials grant** phục vụ **confidential client/service-to-service**, không tự đại diện người dùng đăng nhập. Client gửi `grant_type=client_credentials` đến token endpoint và được AS xác thực.
- **Scope trả lời “token được xét làm gì?”**, **audience trả lời “API nào được nhận token?”**. Cả hai phải được AS cấp theo policy và RS kiểm tra từ **token/metadata đã xác minh**.
- **Requested scope không phải granted scope**. Client không tự có quyền vì yêu cầu scope trong token request hoặc vì metadata AS liệt kê `scopes_supported`.
- **`client_id` khác `aud`**: client là bên xin token, audience là resource server nhận token. ID token OIDC và access token cũng có audience/mục đích khác nhau.
- **RFC 8707 `resource`** giúp client nêu tài nguyên dự kiến; AS vẫn phải kiểm tra resource allowlist và cấp token đúng chính sách. Không forward token sai audience.
- **JWT/opaque access token** vẫn cần validation: issuer, chữ ký/introspection, loại token, thời hạn, audience, scope và quyền trên resource/tenant.
- **Client Credentials thường không cấp refresh token** theo khuyến nghị RFC 6749; client có thể xin access token mới bằng credential của mình.
- **Bảo vệ client secret/private key đặc biệt quan trọng** vì lộ credential có thể cho phép xin thêm token. Sử dụng secret manager, rotation, TLS, audit và least privilege.
- **Scope và audience giảm blast radius, không tự ngăn Bearer token replay**. TTL ngắn, revocation/denylist/introspection và sender constraint như DPoP/mTLS bổ sung khả năng bảo vệ.
- **API phải mặc định từ chối khi thiếu quyền** và phân biệt service principal với user principal, kiểm soát từng operation, tenant và business resource.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): §4.4 Client Credentials grant, token request/response, scopes và client authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền access token, `invalid_token` và `insufficient_scope`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số `resource`, resource/audience binding.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile, issuer, audience, scope và client identity.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, scope, audience và client metadata cho opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và giới hạn propagation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): endpoint discovery và khả năng AS.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token/đổi audience khi AS hỗ trợ theo hợp đồng delegation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token security, hạn quyền, audience binding và chống token bị đánh cắp/phát lại.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): xác thực client bằng mTLS, ràng buộc access token với người giữ khóa.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token/`aud` và phân biệt danh tính client với access API.
- [Spring Security — OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html) và [Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình Client Credentials, authorized-client manager và validation JWT trong Spring.
