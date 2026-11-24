# Scope consent và scope policy

## 1. Một scope được yêu cầu có đồng nghĩa với quyền được cấp?

Trong OAuth 2.0, **scope** là chuỗi định danh phạm vi truy cập mà client yêu cầu hoặc được authorization server (AS) cấp cho access token. Ví dụ ứng dụng `sales-dashboard` cần đọc đơn hàng qua `orders-api`:

~~~text
scope = orders.read
~~~

Tuy nhiên, client gửi `scope=orders.read` **không có nghĩa** AS phải cấp quyền đó. Ngay cả khi người dùng nhấn “Cho phép”, ứng dụng vẫn có thể bị chính sách của tổ chức chặn. Và nếu access token cuối cùng có `orders.read` thì `orders-api` vẫn cần kiểm tra người dùng có quyền đọc *đơn hàng cụ thể* hay không.

Bài **Scope consent và scope policy** trong chương **Scope** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS` giải thích ba tầng quyết định độc lập:

1. **Requested scope** – client muốn xin quyền nào?
2. **Consent và authorization-server policy** – người sở hữu tài nguyên/tổ chức có chấp thuận, và AS **được phép cấp** quyền nào?
3. **Resource-server policy** – token đã cấp có hợp lệ và chủ thể **được phép thực hiện** hành động này trên tài nguyên này không?

> **Consent không thay thế policy. Scope được cấp không thay thế phân quyền nghiệp vụ.**

Ví dụ xuyên suốt:

- **Client:** `sales-dashboard`, giao diện xem đơn hàng.
- **Resource owner:** Alice, nhân viên bán hàng.
- **Authorization server:** `https://auth.example.test`.
- **Resource server:** `orders-api`.
- **Scope được định nghĩa:** `orders.read` (đọc), `orders.write` (sửa).
- **Policy:** Alice chỉ được đọc đơn hàng thuộc tenant `shop-a`; dashboard chỉ được dùng `orders.read`.

Nếu dashboard yêu cầu cả `orders.read orders.write`, Alice có thể đồng ý, nhưng AS vẫn **không được cấp** `orders.write` cho client này. Nếu access token hợp lệ có `orders.read`, API vẫn phải từ chối truy cập đơn hàng của tenant `shop-b`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **scope request**, **user/admin consent**, **scope policy** và **resource authorization**.
- Mô tả cách AS quyết định scope thực sự được cấp và cách client nhận biết kết quả.
- Giải thích phạm vi consent trong OAuth 2.0/OIDC, kể cả đăng nhập, cấp quyền tăng dần và machine-to-machine.
- Thiết kế kiểm tra `scope`, `aud`, `iss`, thời hạn và quyền theo tài nguyên trong JWT hoặc opaque access token.
- Nhận diện lỗi over-scoping, consent phishing, cross-tenant access và những giới hạn của thu hồi consent.

## 2. Những khái niệm phải tách biệt

| Khái niệm | Ai quyết định chủ yếu? | Tác dụng | Không có nghĩa là |
| --- | --- | --- | --- |
| **Scope definition** | Chủ API/AS | Định nghĩa `orders.read`, `orders.write` có ý nghĩa gì | Một scope tự trở thành quyền toàn hệ thống |
| **Requested scope** | OAuth client | Đề nghị AS cấp tập scope cần cho chức năng | Client được phép sở hữu mọi scope đã yêu cầu |
| **User consent** | Người dùng/resource owner, khi cơ chế yêu cầu | Chấp thuận việc client truy cập trong phạm vi được hiển thị | Bỏ qua quyền, vai trò hoặc policy của tổ chức |
| **Admin consent / pre-authorization** | Quản trị viên hoặc cơ chế chính sách của tổ chức | Cho phép client tiếp cận nhóm quyền theo quy định hệ thống | Mọi người dùng có quyền đối với mọi tài nguyên |
| **AS scope policy** | Authorization server/IAM | Giới hạn scope theo đăng ký client, loại grant, user, tenant, rủi ro, điều kiện phiên | API phải tin mọi scope do client tự khai |
| **Granted scope** | AS sau khi đánh giá các điều kiện | Tập scope thực tế được cấp cho access token | Đã hoàn tất phân quyền object-level |
| **Resource-server authorization** | API/resource server và domain policy | Quyết định cho phép request tới bản ghi/hành động cụ thể | Chỉ kiểm tra chữ ký JWT là đủ |
| **Audience / resource binding** | AS cấp; API xác minh | Xác định token dành cho API nào | Một scope trùng tên cho phép gọi mọi API |

**Scope là cách biểu diễn quyền được ủy quyền ở một mức trừu tượng**. Scope `orders.read` thường mô tả loại thao tác, nhưng không tự liệt kê từng đơn hàng. AS có thể biết user được gán vai trò gì, còn API thường sở hữu dữ liệu và quy tắc nghiệp vụ chi tiết.

### 2.1. Scope được biểu diễn như thế nào?

Trong OAuth 2.0 (RFC 6749), tham số `scope` là danh sách các scope token **phân cách bằng dấu cách**, còn ý nghĩa từng scope do AS/resource server định nghĩa:

~~~text
scope=orders.read orders.write
~~~

Khi đưa vào URL form encoding, dấu cách thường trở thành `%20` hoặc `+` theo quy tắc mã hóa tương ứng:

~~~text
scope=orders.read%20orders.write
~~~

Scope token **phân biệt chữ hoa/chữ thường**. `orders.read` khác `Orders.Read`; `orders.readonly` không tự tương đương `orders.read`. Quyền không nên được kiểm tra bằng phép tìm chuỗi con như `scope.contains("orders.read")`.

Một số nhà cung cấp dùng claim `scp` dạng mảng hoặc quyền trong `roles`. Đó là **hợp đồng profile riêng**; không được coi mọi chuỗi `roles`, `scp` và `scope` là đồng nghĩa rồi tự động hợp nhất để cấp đặc quyền.

### 2.2. Scope, permission, role và policy

Xét một nhân viên có role `SALESPERSON` và access token chứa scope `orders.read`. Role nói về nhóm quyền của nhân viên trong hệ thống, còn scope giới hạn những thao tác mà client được ủy quyền qua token. Quy tắc cuối cùng có thể là:

~~~text
CHO PHÉP đọc đơn hàng NẾU
    access token hợp lệ cho orders-api
    VÀ có scope "orders.read"
    VÀ user đang hoạt động
    VÀ user thuộc tenant của đơn hàng
    VÀ role/ACL nghiệp vụ cho phép đọc đơn hàng đó.
~~~

Không chỉ dùng `roles = ["ADMIN"]` trong access token rồi cho phép mọi API; role cần được hiểu trong đúng issuer, audience, ứng dụng và tenant. Scope là một phần của cơ chế **ủy quyền**, nhưng nó không tự thay thế mô hình RBAC/ABAC hoặc kiểm tra quyền sở hữu.

## 3. Luồng cấp scope: yêu cầu, consent, policy, phát hành

Ví dụ OAuth 2.0 **Authorization Code + PKCE** cho một người dùng đăng nhập và đồng ý cho dashboard đọc đơn hàng:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice (resource owner)
    participant C as sales-dashboard (OAuth client)
    participant AS as Authorization Server
    participant RS as orders-api (resource server)
    U->>C: Chọn "Xem đơn hàng"
    C->>AS: Authorization request: orders.read orders.write
    AS->>AS: Kiểm tra client, redirect_uri, PKCE, tenant, policy
    AS->>U: Hiển thị quyền có thể chấp thuận (nếu cần)
    U-->>AS: Đồng ý quyền đọc
    AS->>AS: Quyết định granted scope theo consent và policy
    AS-->>C: Authorization code
    C->>AS: Đổi code + PKCE verifier lấy token
    AS-->>C: Access token chỉ có orders.read, aud=orders-api
    C->>RS: GET /orders/123 với Bearer access token
    RS->>RS: Verify token + scope + quyền trên order 123
    RS-->>C: 200 hoặc 401/403
~~~

Trong luồng thực tế, AS có thể yêu cầu đăng nhập/MFA, áp đặt chính sách truy cập có điều kiện hoặc **không hiển thị consent screen** nếu đã có consent phù hợp trước đó. OAuth 2.0 không bắt buộc mỗi lần cấp token phải xuất hiện một màn hình consent.

### 3.1. Quyết định của AS có thể hình dung bằng một giao các điều kiện

Đối với hệ thống đơn giản, granted scope có thể được xem như:

\[
S_{\mathrm{granted}} \subseteq
S_{\mathrm{requested}}
\cap S_{\mathrm{client\ allowed}}
\cap S_{\mathrm{owner\ authorized}}
\cap S_{\mathrm{consented}}
\cap S_{\mathrm{policy\ allowed}}
\]

Đây là **mô hình tư duy**, không phải thuật toán bắt buộc của OAuth 2.0. Một số grant không có end-user/consent; hệ thống có thể áp scope mặc định khi client không gửi `scope`; các quyền phụ thuộc ngữ cảnh có thể không biểu diễn thành tập đơn giản. Điều **không thay đổi** là AS chỉ cấp quyền nằm trong chính sách cấp quyền hợp lệ, và client **không tự quyết định** kết quả.

Với ví dụ:

~~~text
Requested:         {orders.read, orders.write}
Client allowed:    {orders.read}
User consented:    {orders.read}
AS policy allowed: {orders.read}
Granted:           {orders.read}
~~~

Khi một yêu cầu scope không đáp ứng chính sách, AS có thể cấp **ít scope hơn** nếu luồng/chính sách cho phép hoặc trả lỗi `invalid_scope`/`access_denied` tùy nguyên nhân và giai đoạn. Không nên khẳng định mọi AS luôn tự động thu nhỏ tập scope thay vì từ chối.

### 3.2. Câu trả lời có thẩm quyền đến từ đâu?

OAuth 2.0 token response ví dụ:

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Khi scope được cấp khác scope mà client yêu cầu, RFC 6749 yêu cầu AS trả `scope` trong token response. Nếu giống với scope được yêu cầu, trường này có thể bị lược bỏ. Client phải dựa vào kết quả grant và policy API, **không** tự giả định rằng có quyền `orders.write` chỉ vì đã gửi request chứa scope đó.

Nếu token là JWT theo profile chứa `scope`, resource server chỉ tin giá trị claim **sau khi** kiểm tra issuer, chữ ký, audience và thời hạn. Nếu token opaque, resource server lấy scope và trạng thái từ **introspection endpoint tin cậy**. Token response mà client đọc không tự thay thế việc API xác minh credential thực nhận.

## 4. User consent là gì và không phải là gì?

**Consent** là sự chấp thuận của người có thẩm quyền đối với một client và phạm vi truy cập nhất định trong quá trình ủy quyền. Trong các hệ thống OAuth/OIDC hướng tới người dùng, AS có thể hiển thị:

> Ứng dụng **Sales Dashboard** muốn **đọc đơn hàng** của bạn. Bạn có cho phép không?

Việc hiển thị tên ứng dụng, nhà phát hành, mục đích, loại dữ liệu và thời gian hiệu lực rõ ràng giúp người dùng hiểu quyền họ trao. Consent có thể được ghi nhận để không hỏi lại khi cùng client/scope vẫn còn hiệu lực, hoặc được quản lý bởi chính sách tổ chức.

### 4.1. Consent có quyền hạn hữu hạn

Khi Alice đồng ý cho dashboard đọc đơn hàng:

- Alice **không thể** cấp quyền đọc đơn hàng tenant `shop-b` nếu Alice vốn không có quyền đó.
- Alice **không thể** vượt qua lệnh chặn ứng dụng hoặc scope từ policy của AS/tổ chức.
- Consent đối với `orders.read` **không bao gồm** `orders.write` trừ khi chính sách định nghĩa rõ ràng và quyền này được cấp đúng cách.
- Consent không nhất thiết đồng nghĩa với token có giá trị vô thời hạn; token vẫn có `exp` và có thể bị thu hồi.
- API vẫn phải kiểm tra danh tính, phạm vi, tenant và ACL đối với bản ghi.

Consent là một **đầu vào cho quyết định cấp quyền**, chứ không phải một thông điệp từ user gửi thẳng tới API để bỏ qua phân quyền.

### 4.2. Consent screen phải khớp quyền thực tế

Một thiết kế tốt dùng scope tên rõ và mô tả dễ hiểu:

| Scope | Mô tả trên consent UI | Điều API cho phép |
| --- | --- | --- |
| `orders.read` | Xem đơn hàng mà bạn được phép truy cập | GET và tác vụ đọc trong tenant/quyền hợp lệ |
| `orders.write` | Tạo hoặc chỉnh sửa đơn hàng được phép | Ghi dữ liệu, vẫn kiểm tra trạng thái/owner/tenant |
| `orders.export` | Xuất dữ liệu đơn hàng được phép | Xuất tập dữ liệu tuân thủ chính sách và hạn mức |

Nếu UI chỉ nói “Truy cập dữ liệu của bạn” nhưng cấp `orders.export` và `orders.write`, người dùng khó đánh giá phạm vi thực sự. Đồng ý do bị đánh lừa bởi tên ứng dụng giả, tên scope khó hiểu hoặc consent screen không khớp là một hình thức **consent phishing/social engineering**.

### 4.3. Consent lần đầu, consent tăng dần và consent lại

**Incremental authorization** nghĩa là client chỉ xin scope cần cho chức năng đang được sử dụng, rồi xin thêm khi người dùng kích hoạt chức năng mới.

Ví dụ:

1. Alice mở trang danh sách → dashboard xin `orders.read`.
2. Alice chọn “Chỉnh sửa đơn hàng” → client có thể khởi tạo một authorization request mới xin thêm `orders.write`.
3. AS kiểm tra lại policy, quyền và consent theo chính sách hiện tại.
4. Chỉ sau khi được cấp scope phù hợp, client mới gọi API ghi.

Không nên xin trước `orders.write orders.export customers.delete` chỉ vì **có thể** sau này ứng dụng sẽ dùng. Xin ít quyền từ đầu giúp giảm thiệt hại nếu token bị đánh cắp và làm thông điệp consent dễ hiểu hơn.

### 4.4. OIDC consent và các scope đặc biệt

OpenID Connect (OIDC) xây trên OAuth 2.0 và sử dụng scope `openid` để chỉ ra yêu cầu xác thực OIDC. Các scope OIDC như `profile`, `email` có ý nghĩa đối với việc yêu cầu **claims về end-user**, không tự động biến ID token thành access token cho mọi API.

`offline_access` là scope OIDC liên quan đến yêu cầu access khi end-user không hiện diện, thường gắn với quyền cấp refresh token tùy chính sách AS. OIDC có những yêu cầu riêng về consent cho offline access và ngoại lệ theo điều kiện chuẩn; **không nên hiểu** rằng chỉ cần gửi `offline_access` là AS bắt buộc cấp refresh token. `prompt=consent` là tham số OIDC có thể yêu cầu hiển thị consent trong trường hợp phù hợp; nó **không ép** AS vượt policy.

Quyền truy cập dữ liệu nghiệp vụ như `orders.read` nên được thiết kế theo API/authorization model thay vì coi `openid profile email` tương đương quyền đọc cơ sở dữ liệu đơn hàng.

## 5. Scope policy ở authorization server

Authorization server có thể thực thi policy trước khi cấp token, bao gồm:

| Loại policy | Câu hỏi AS cần giải quyết | Ví dụ |
| --- | --- | --- |
| **Client registration/allowlist** | Client này được đăng ký những scope nào? | `sales-dashboard` chỉ có `orders.read` |
| **Grant type** | Scope này có hợp với `authorization_code`, `client_credentials` hoặc token exchange không? | Job machine không xin quyền dành riêng cho user |
| **Resource owner** | Chủ thể hiện tại có được quyền ủy quyền thao tác này không? | Alice không cấp quyền admin mà cô không sở hữu |
| **Tenant/organization** | Tổ chức có chặn scope hoặc client không? | Tenant `shop-a` không cho app thứ ba xuất dữ liệu |
| **Consent / prior grant** | Người có thẩm quyền đã chấp thuận đúng client/scope chưa? | Dashboard chưa được consent `orders.write` |
| **Authentication strength** | Thao tác có yêu cầu MFA/step-up không? | Export dữ liệu lớn cần xác thực mạnh |
| **Risk/context** | Thiết bị, vị trí, bảo đảm phiên, trạng thái ứng dụng có đạt yêu cầu? | Từ chối token nhạy cảm từ thiết bị không đạt chuẩn |
| **Audience/resource** | Token được cấp cho API nào? | `aud=orders-api`, không thể dùng tại `billing-api` |
| **TTL/refresh policy** | Token sống bao lâu, có cấp refresh token không? | `orders.export` có TTL ngắn và hạn chế refresh |

Một số điều kiện thuộc tính năng của AS/IAM cụ thể và **không được chuẩn OAuth 2.0 áp đặt như cấu hình bắt buộc**. Kiến trúc phải mô tả rõ nơi thực thi để không lầm tưởng AS đã kiểm tra điều kiện mà chỉ API mới biết.

### 5.1. Resource indicators và giới hạn audience

Client có thể yêu cầu scope `orders.read`, nhưng nếu token cấp cho `payments-api` thì `orders-api` vẫn phải từ chối. Trong hệ thống hỗ trợ Resource Indicators (RFC 8707), client có thể chỉ rõ resource đích:

~~~text
scope=orders.read
resource=https://orders.example.test/
~~~

AS có thể dùng thông tin này để cấp access token có audience tương ứng. Cách diễn giải `resource` và `aud` phụ thuộc AS/token profile; resource server phải kiểm tra audience **chính xác theo hợp đồng**. Không dùng việc hai API có scope trùng tên như một lý do chia sẻ access token cho mọi nơi.

### 5.2. Scope policy và scope naming

Các tên `orders.read`/`orders.write` là **quy ước ứng dụng**, không phải danh mục scope chuẩn bắt buộc của OAuth. Cần mô tả semantics rõ ràng, quản lý phiên bản và tránh tên quá tổng quát:

- Scope `admin` không có namespace dễ bị hiểu khác nhau giữa API.
- Scope `read` có thể quá rộng nếu token sử dụng cho nhiều resource.
- Scope `orders.*` nếu được hỗ trợ cần contract rõ ràng; đừng giả định wildcard là đặc tính mặc định của OAuth.
- Dùng tên scope cho quyền tác vụ API, còn ràng buộc theo user, tenant, record, thời gian hoặc trạng thái giao dịch ở policy chi tiết.

Nếu client không gửi `scope`, AS có thể cấp scope mặc định hoặc xử lý theo policy của mình. Client và API cần có hợp đồng nhất quán; không tự coi “thiếu scope” là “có mọi quyền”.

## 6. Resource-server policy: có scope đúng vẫn chưa chắc được truy cập

Sau khi AS cấp access token, **resource server (RS)** chịu trách nhiệm kiểm tra token và quyền cụ thể. Đây là điểm dễ nhầm nhất giữa **consent** và **authorization**: người dùng đồng ý cho một ứng dụng “đọc đơn hàng” không có nghĩa ứng dụng được đọc **đơn hàng của tất cả mọi người**.

Giả sử token đã được cấp cho Alice:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "shop-a",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

Đây là **payload minh họa**, chưa phải JWT hoàn chỉnh. API cần lấy claims từ token **đã xác minh** hoặc từ introspection đã xác thực, không dùng JSON do client tự đính kèm request.

Với `GET /v1/orders/123`, `orders-api` phải kiểm tra:

1. **Token validation:** token còn hợp lệ, có issuer đã tin cậy; JWT có chữ ký hợp lệ hoặc opaque token `active: true` tại AS có thẩm quyền.
2. **Audience:** `aud` chứa định danh `orders-api`; token cấp cho API khác bị từ chối.
3. **Scope:** token được cấp `orders.read`, đủ cho thao tác đọc; `orders.write` mới dành cho thao tác ghi theo policy.
4. **Principal/tenant:** `sub`, `client_id` hoặc actor được hiểu đúng theo loại grant/token profile; `tenant_id` đúng tenant đang xử lý.
5. **Object-level authorization:** đơn hàng 123 thuộc `shop-a` và Alice thực sự có quyền đọc đơn hàng này theo nghiệp vụ.
6. **Điều kiện ngữ cảnh:** account còn hoạt động, đơn hàng không bị khóa, yêu cầu step-up khi cần hoặc các quy tắc tổ chức khác.

Kiểm tra scope ở route layer và object-level policy ở domain/service layer bổ sung cho nhau.

~~~mermaid
flowchart TD
    R["Request + access token"] --> T{"Token hợp lệ và dành cho orders-api?"}
    T -->|"Không"| N1["Từ chối 401 / lỗi xác minh"]
    T -->|"Có"| S{"Có scope yêu cầu?"}
    S -->|"Không"| N2["Từ chối 403 insufficient_scope"]
    S -->|"Có"| P{"Principal/tenant được phép với order này?"}
    P -->|"Không"| N3["Từ chối 403 hoặc 404 theo chính sách bảo mật"]
    P -->|"Có"| A["Cho phép hành động"]
~~~

Mã lỗi cụ thể tùy lý do và contract API. Theo OAuth 2.0 Bearer Token Usage (RFC 6750), token thiếu/không hợp lệ thường dẫn tới `401` với `WWW-Authenticate` phù hợp; thiếu scope thường dùng `403` và `error="insufficient_scope"`. Không nên dùng lỗi 403 để xác nhận sự tồn tại của tài nguyên bí mật nếu policy lựa chọn trả 404 nhằm hạn chế lộ thông tin.

### 6.1. Scope không thay thế access control trên từng bản ghi

| Request | Scope hợp lệ? | Quyền nghiệp vụ? | Kết quả |
| --- | --- | --- | --- |
| Alice đọc đơn hàng của `shop-a` | Có `orders.read` | Alice được xem đơn hàng | Cho phép |
| Alice đọc đơn hàng của `shop-b` | Có `orders.read` | Sai tenant | Từ chối |
| Alice sửa đơn hàng `shop-a` | Chỉ có `orders.read` | Dù Alice là owner | Từ chối do thiếu `orders.write` |
| Dashboard có `orders.write` sửa đơn hàng đã khóa | Có | Business policy cấm sửa đơn khóa | Từ chối |
| Token issuer đúng nhưng `aud=billing-api` | Có chuỗi `orders.read` | Không xét tiếp | Từ chối vì audience |

Với API xử lý dữ liệu đa tenant, **đừng tin tenant ID từ URL hoặc header client** mà không đối chiếu với chủ thể/quyền và tài nguyên. Nếu cần impersonation hoặc delegation giữa các dịch vụ, thiết kế phải nêu rõ actor/subject và ranh giới tin cậy.

### 6.2. Quyền thay đổi sau khi token đã phát hành

Giả sử Alice mất quyền đọc đơn hàng sau khi AS cấp JWT có `orders.read` và `exp` còn 5 phút. Một API chỉ kiểm tra JWT ngoại tuyến có thể tiếp tục chấp nhận **scope trong token** tới khi hết hạn. Nếu nghiệp vụ cần thu hồi hiệu lực tức thời, cần thêm kiểm tra trạng thái account/ACL tại API, introspection hoặc cơ chế thu hồi/bảng từ chối phù hợp.

Điều này nhấn mạnh: **scope trong access token mô tả quyền tại thời điểm cấp theo hợp đồng**, không phải phép kiểm tra quyền nghiệp vụ thời gian thực mặc định.

## 7. Delegated scope, application scope và machine-to-machine

Không phải mọi token có scope đều phát sinh từ consent của end-user. Cần phân biệt ngữ cảnh ủy quyền:

| Ngữ cảnh | Người dùng tương tác? | Nguồn quyết định cấp scope | Điểm cần kiểm tra ở API |
| --- | --- | --- | --- |
| **Delegated access** qua authorization code | Thường có | Quyền của resource owner, consent nếu cần, client/tenant policy | Cả scope và quyền của user trên tài nguyên |
| **Machine-to-machine** qua client credentials | Không cần end-user | Đăng ký client, admin/service policy và AS | Client/service identity, scope, audience, tenant, ACL nghiệp vụ |
| **On-behalf-of / token exchange** | User có thể là chủ thể gốc | AS xét quyền delegation của actor, subject, resource và policy | Đúng actor/subject, audience và quyền được ủy quyền |
| **Refresh access token** | Thường không yêu cầu UI mỗi lần | Grant/refresh-token policy và quyền được phép còn hiệu lực | Token mới có quyền phù hợp và còn được chấp nhận |

Trong OAuth 2.0 `client_credentials`, client sử dụng quyền của **chính mình** hoặc quyền đã được thỏa thuận trước. Không có consent screen của Alice vì Alice không tham gia grant. Một quản trị viên có thể duyệt trước các quyền của `reporting-job`, nhưng đó là **admin authorization/policy**, không phải “user consent” cho mọi end-user.

### 7.1. Ví dụ quyền cho service account

Giả sử `inventory-sync` cần đọc danh sách sản phẩm:

~~~text
client_id: inventory-sync-prod
grant_type: client_credentials
requested_scope: inventory.read inventory.write
client_policy_allowed: inventory.read
audience: inventory-api
~~~

AS chỉ nên cấp `inventory.read` theo policy hoặc từ chối yêu cầu vượt quyền. Resource server phân quyền theo identity của service và tenant tương ứng; không được tự gán `sub=alice` chỉ vì một request HTTP từ người dùng trước đó dẫn tới job.

Client credentials thường **không cần refresh token**; client có thể xác thực lại với AS để lấy access token mới theo cơ chế được hỗ trợ. Theo RFC 6749, refresh token **SHOULD NOT** được cấp cho client credentials grant.

### 7.2. Backend gọi thay mặt Alice

Giả sử frontend gọi `orders-service` với user-delegated token của Alice; `orders-service` cần gọi `shipping-service`. Đừng mặc định chuyển tiếp token của `orders-api` sang `shipping-api`: token có thể có sai audience. Một cách tiếp cận là dùng token exchange/delegation được AS và cả hai API hỗ trợ, bảo toàn quyền phù hợp của Alice và danh tính actor khi cần.

Nếu `orders-service` dùng service token có quyền mạnh hơn, nó vẫn phải kiểm tra quyền của Alice tại ranh giới đáng tin; nếu không, đây có thể là lỗi **confused deputy**: service quyền cao thực hiện thao tác mà user gốc không được phép.

## 8. Scope consent trong OAuth/OIDC: ví dụ request và cấp quyền

Một authorization request minh họa cho ứng dụng đã đăng ký dùng Authorization Code + PKCE:

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20orders.read&state=<random-state>&code_challenge=<base64url-sha256>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

`state` cần được client tạo và kiểm tra để liên kết authorization response với phiên request, chống CSRF/mix-up theo thiết kế; `code_challenge` phải tương ứng với `code_verifier` của PKCE khi đổi authorization code. Đây là request minh họa, không phải giá trị có thể dùng chạy thật. AS phải xác minh chính xác `client_id`, `redirect_uri` và các điều kiện grant.

Sau khi AS hoàn thành authentication, policy và consent theo ngữ cảnh, client đổi code lấy token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<authorization-code>&redirect_uri=<registered-redirect-uri>&client_id=sales-dashboard&code_verifier=<original-code-verifier>
~~~

Lưu ý: phương thức client authentication tại token endpoint tùy loại client và đăng ký AS; một confidential client còn phải xác thực theo phương thức được cho phép. Ví dụ trên minh họa tham số trong luồng PKCE, không thay thế yêu cầu xác thực confidential client.

Token response có thể trả:

~~~json
{
  "access_token": "<access-token-for-orders-api>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Nếu authorization request còn có `openid`, một OIDC response có thể kèm `id_token` tùy flow và điều kiện chuẩn. **ID token** phục vụ OIDC client xác thực end-user; `orders-api` chỉ nên nhận **access token** dành cho API, không nhận ID token thay thế.

Khi người dùng kích hoạt chức năng mới, client phải xin quyền mới qua luồng được AS hỗ trợ; không tự sửa payload JWT `scope`, không gửi thêm scope bằng HTTP header đến resource server, và không sửa chuỗi opaque access token.

## 9. Java/Spring Security: scope policy ở API

Ví dụ sau sử dụng Spring Boot/Spring Security 6.x, JWT access token từ issuer đã cấu hình. Mục tiêu của ví dụ: **từ chối token sai issuer/audience và kiểm tra scope đúng từng route**, sau đó kiểm tra quyền trên đơn hàng ở service layer.

### 9.1. Cấu hình resource server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

`issuer-uri` chọn issuer tin cậy, hỗ trợ framework xác định JWKS qua metadata và áp dụng một số validator chuẩn theo phiên bản. **Cần thêm audience validator** cho `orders-api`; một token có chữ ký/issuer đúng nhưng dành cho API khác không thể được chấp nhận.

Ví dụ một `JwtDecoder` có xác minh issuer và audience:

~~~java
@Configuration
@EnableMethodSecurity
class OrdersSecurityConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String trustedIssuer = "https://auth.example.test";
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> correctAudience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token", "Sai audience", null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, correctAudience));
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

Ví dụ giả định framework dùng `JwtGrantedAuthoritiesConverter` mặc định để chuyển claim `scope`/`scp` thành authority `SCOPE_...`. Nếu AS dùng format khác, phải cấu hình converter rõ ràng, **không tự đưa mọi role/claim chưa hiểu thành authority**. Cần bổ sung kiểm tra token profile như `typ` khi hợp đồng AS đòi hỏi, các yêu cầu thuật toán/khoá và giới hạn kiểm tra theo phiên bản thư viện.

### 9.2. Object-level policy trong service

Để tránh đọc chéo tenant, method service có thể yêu cầu cả scope và domain policy:

~~~java
@Service
class OrdersService {
    private final OrdersRepository orders;

    OrdersService(OrdersRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)")
    public OrderView getOrder(String orderId) {
        return orders.findOrderViewById(orderId)
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
        if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tenantId =
                jwtAuth.getToken().getClaimAsString("tenant_id");
        String subject = jwtAuth.getToken().getSubject();

        if (tenantId == null || subject == null) {
            return false;
        }
        return orders.findById(orderId)
                .map(order -> tenantId.equals(order.getTenantId())
                        && order.canBeReadBy(subject))
                .orElse(false);
    }
}
~~~

Đây là ví dụ cấu trúc: các kiểu `OrdersRepository`, `OrderView`, `OrderNotFoundException` và `order.canBeReadBy` thuộc domain ứng dụng. Cần import các class Spring Security và bảo đảm tham số `#orderId` có thể được SpEL nhận diện (ví dụ build bật giữ tên tham số hoặc dùng `@P` khi cần).

**Điểm then chốt:** `@PreAuthorize` được thực thi **sau khi** bearer access token đã được Spring Security xác minh. Domain policy đọc claims từ principal đã xác thực và dữ liệu đơn hàng thật. Với opaque token, principal/token attributes và kiểu `Authentication` có thể khác; cần dùng một adapter nhất quán theo profile thay vì ép mọi request thành `JwtAuthenticationToken`.

Ứng dụng cũng cần chính sách đối với PUT/PATCH/DELETE, giới hạn thao tác và endpoint không có trong ví dụ; default deny được đặt để tránh vô tình bỏ lọt route. Bộ kiểm tra trên không tự thực hiện consent UI: **consent nằm ở AS**, còn API thực thi quyền.

### 9.3. Introspection cho opaque token

Với opaque access token, ứng dụng có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: EXTERNAL_SECRET_REFERENCE
~~~

Giá trị `EXTERNAL_SECRET_REFERENCE` chỉ là placeholder; credential thật phải lấy từ secret manager/cơ chế bảo vệ phù hợp. API chỉ tin introspection endpoint đã xác định, xác thực khi gọi, kiểm tra `active` và ràng buộc đúng resource/audience, rồi kiểm tra scope/tenant/domain policy theo response của AS. `active: true` **không tự động** cho phép mọi hành động; nếu introspection lỗi hoặc không xác minh được, phải fail closed.

## 10. Vòng đời consent, scope và token

Consent và access token có **vòng đời khác nhau**. Một ứng dụng có thể giữ bản ghi consent để lần sau không cần hỏi lại, trong khi access token chỉ sống vài phút. Ngược lại, việc gỡ consent tại AS không bảo đảm mọi JWT đã cấp bị vô hiệu tức thì ở resource server.

~~~mermaid
flowchart TD
    C["Client xin scope"] --> P["AS kiểm tra consent + policy"]
    P --> G{"Được cấp?"}
    G -->|"Không"| D["Từ chối hoặc yêu cầu cấp quyền hợp lệ"]
    G -->|"Có"| T["Phát hành access token có aud/scope/TTL"]
    T --> A["RS xác minh token và phân quyền"]
    A --> V{"Thay đổi consent/role/policy?"}
    V -->|"Chưa"| A
    V -->|"Có"| R["AS cập nhật grant/trạng thái hoặc từ chối lần cấp tiếp"]
    R --> X["RS kiểm tra trạng thái/ACL hoặc chờ token hết hạn theo policy"]
~~~

| Biến cố | Tác động có thể có | Cần thiết kế rõ |
| --- | --- | --- |
| Người dùng từ chối consent | Không tạo grant cho scope cần đồng ý | Ứng dụng phải xử lý thiếu quyền mà không lỗi vòng lặp |
| Người dùng thu hồi consent | AS ngừng/thu hồi grant hoặc token theo triển khai | JWT đã phát hành và refresh token có bị revoke không? |
| Admin chặn app hoặc scope | AS có thể từ chối cấp token mới | Có cần chặn ngay token còn hiệu lực tại RS không? |
| User bị hạ role/xóa khỏi tenant | Domain policy không cho phép truy cập nữa | API kiểm tra ACL hiện thời hay tin snapshot token? |
| Access token hết `exp` | RS từ chối token hết hạn | Client xin access token mới qua luồng hợp lệ |
| Refresh token bị thu hồi/rotation thất bại | Không thể xin token mới bằng refresh token đó | Xử lý re-authentication và sự cố token bị đánh cắp |
| Client credential bị lộ | Kẻ khác có thể xin token trong quyền client | Rotate credential, audit token, revocation kế hoạch ứng phó |

RFC 7009 định nghĩa token revocation endpoint trong OAuth 2.0, nhưng việc revocation **có hiệu lực ngay** tại mọi RS còn phụ thuộc định dạng token và cách kiểm tra trạng thái. Token JWT kiểm tra cục bộ có thể còn dùng được tới `exp` nếu không có denylist/introspection/cơ chế kiểm soát bổ sung. Opaque token có thể phản ánh `active: false` qua introspection, nhưng cache câu trả lời `active: true` vẫn tạo độ trễ thu hồi.

### 10.1. Khi refresh token xin scope mới

Theo OAuth 2.0, scope được yêu cầu khi dùng refresh token **không được mở rộng** ra ngoài phạm vi đã được resource owner cấp ban đầu; nếu client xin ít hơn có thể downscope tùy khả năng AS. Việc xin thêm quyền phải qua luồng cấp quyền hợp lệ và policy, chứ không tự biến refresh token thành quyền quản trị. Khi AS hỗ trợ gia hạn hoặc grant bị thu hồi, client phải chấp nhận việc không thể xin token mới.

**Đừng gộp lẫn ba việc**: xóa consent UI/grant, revoke refresh token và làm invalid access token đã phát hành. Chúng có thể cần những API/hành động vận hành khác nhau và cần kiểm thử SLA thu hồi.

## 11. Những rủi ro thiết kế scope và consent

| Rủi ro | Kịch bản | Kiểm soát |
| --- | --- | --- |
| **Over-scoping** | Client chỉ cần đọc nhưng yêu cầu `orders.*` hoặc `orders.admin` | Least privilege; scope allowlist theo client |
| **Consent phishing** | Kẻ xấu tạo app tên giống ứng dụng nội bộ, xin `orders.export` | Xác minh client/publisher, consent UI rõ và admin policy |
| **Scope escalation qua client** | Client tự gửi `scope=orders.write` ở token request | AS kiểm tra grant và chính sách, không tin request |
| **Cross-resource confusion** | Token đúng chữ ký có `scope=orders.read` nhưng `aud=billing-api` | RS kiểm tra audience phù hợp |
| **Cross-tenant access** | Alice có scope đọc nhưng hỏi order của tenant khác | Kiểm tra tenant/ownership theo dữ liệu thực |
| **Token theft/replay** | JWT có scope rộng bị lộ qua log | TTL ngắn, scope/audience hẹp, loại bỏ token khỏi log, mTLS/DPoP khi phù hợp |
| **Stale consent/role** | Admin rút quyền nhưng token cũ vẫn còn hạn | Thu hồi/cập nhật trạng thái và domain authorization thời gian thực |
| **String-matching sai** | `orders.readonly` vượt check `contains("orders.read")` | So exact scope token theo profile |
| **Token type confusion** | API chấp nhận ID token có claims trông giống quyền | Chỉ chấp nhận access token đúng loại/audience/profile |
| **Scope name collision** | Hai API cùng dùng `read` và chia token | Namespace scope, aud/resource binding, issuer policy |

### 11.1. Consent phishing cụ thể diễn ra thế nào?

Một ứng dụng không đáng tin giả tên `Sales Dashboard Pro` rồi yêu cầu `orders.read orders.export`. Người dùng thấy tên quen và nhấn đồng ý. AS có thể cấp token nếu tổ chức cho phép app đó xin scope và user có quyền. Kẻ xấu sử dụng token trong phạm vi được cấp để xuất dữ liệu.

Vấn đề ở đây không nhất thiết là chữ ký JWT sai: token **có thể hoàn toàn hợp lệ**. Kiểm soát cần ở đăng ký client, xác minh danh tính publisher, danh sách ứng dụng được phê duyệt, chính sách scope, consent UX và khả năng thu hồi grant/token. AS và RS nên ghi audit dấu vết cấp quyền/truy cập nhưng không ghi nguyên bearer token.

### 11.2. Scope quá rộng và token bị đánh cắp

Nếu token có `orders.read orders.write orders.export` bị lộ, kẻ cầm token có thể phát lại trong các quyền đó đến khi token hết hạn hoặc bị vô hiệu, trừ khi có **sender-constrained token** và API xác minh ràng buộc tương ứng. DPoP (RFC 9449) hoặc mTLS certificate-bound access token (RFC 8705) giúp giảm rủi ro sao chép bearer token nếu được hỗ trợ đúng; chúng không thay thế kiểm tra scope, tenant và chính sách tài nguyên.

Giảm scope và audience **giảm mức thiệt hại** của token lộ; TTL ngắn **giảm thời gian thiệt hại**. Không một biện pháp đơn lẻ nào thay thế quy trình phát hành, lưu trữ, thu hồi và giám sát token.

## 12. Ba bài tập tình huống

### Tình huống A: User đồng ý quyền cao hơn client được phép

`sales-dashboard` chỉ được đăng ký `orders.read` nhưng request `orders.read orders.write`. Alice nhấn đồng ý cả hai trên một màn hình do ứng dụng tự tạo.

**Câu hỏi:** AS có thể cấp `orders.write` dựa trên nút “Đồng ý” đó không?

**Giải đáp:** Không được vượt client/AS policy. Chỉ consent được AS tin cậy và xác minh trong grant hợp lệ mới có ý nghĩa; mọi scope vẫn phải thuộc quyền client và resource owner theo policy. AS có thể từ chối yêu cầu hoặc cấp tập hẹp hơn theo hợp đồng.

### Tình huống B: Token hợp lệ nhưng khách hàng ở tenant khác

Token của Alice có chữ ký đúng, `aud=orders-api`, `scope=orders.read`, `tenant_id=shop-a`. Alice gọi `GET /orders/999`, nhưng đơn hàng 999 thuộc `shop-b`.

**Câu hỏi:** Scope và consent đủ để trả dữ liệu không?

**Giải đáp:** Không. RS phải đối chiếu tài nguyên và tenant thực tế, sau đó từ chối. Nếu API chỉ check `orders.read` thì tồn tại lỗ hổng broken object-level authorization.

### Tình huống C: Admin thu hồi consent trong khi JWT còn hạn

Admin thu hồi grant của dashboard lúc 10:00. Một JWT có `orders.read` được cấp lúc 09:59, `exp` lúc 10:04. `orders-api` kiểm tra JWT hoàn toàn ngoại tuyến.

**Câu hỏi:** Token lập tức bị vô hiệu lúc 10:00 không?

**Giải đáp:** Không thể mặc định như vậy. API có thể còn chấp nhận token tới khi `exp` nếu không kiểm tra trạng thái hay domain policy bổ sung. Thiết kế phải xác định cơ chế thu hồi và mức trễ chấp nhận được.

## 13. Checklist và câu hỏi tự kiểm tra

Trước khi triển khai hệ thống scope và consent:

1. **Scope taxonomy:** Từng scope có tên, mục đích, API đích và quyền rõ ràng? Có scope quá rộng không?
2. **Client policy:** Client được phép xin những scope nào theo grant type, tenant và đăng ký?
3. **User/admin consent:** Màn hình consent mô tả đúng quyền, nguồn client và khả năng thu hồi? Có policy pre-approval và giới hạn quyền?
4. **AS issuance:** Scope cấp thực tế nằm trong policy? Khi scope bị giảm, token response phản ánh kết quả? Có aud/resource binding?
5. **Token validation:** RS kiểm tra issuer, JWT signature hoặc opaque introspection, audience, thời hạn và đúng loại access token?
6. **Authorization:** RS kiểm tra exact scope và quyền bản ghi/tenant theo principal đã xác thực?
7. **Lifecycle:** Consent bị rút, user đổi role, refresh/access token hết hạn hoặc bị revoke sẽ có hiệu lực khi nào?
8. **Threat defense:** Có bảo vệ token khi truyền/lưu, tránh log bearer và giám sát consent phishing, over-scoping, token replay?
9. **Tests:** Có thử token sai audience, thiếu scope, cross-tenant, consent bị rút, AS timeout, role thay đổi và token còn hiệu lực?

**Câu hỏi 1:** Client yêu cầu `orders.read orders.write`, AS chỉ trả `scope=orders.read`. Client được gọi POST sửa đơn hàng không?

**Trả lời:** Không. Quyền thực tế được cấp chỉ có `orders.read`. Request POST đòi scope ghi phải bị từ chối.

**Câu hỏi 2:** Alice đồng ý `orders.read`. Điều đó cho phép dashboard đọc mọi đơn hàng của công ty không?

**Trả lời:** Không. API còn phải kiểm tra quyền của Alice theo tenant, bản ghi, trạng thái account và policy nghiệp vụ.

**Câu hỏi 3:** Job dùng client credentials có luôn phải mở consent screen cho người dùng không?

**Trả lời:** Không. Client credentials không dùng end-user tương tác; quyền được cấp theo client registration và AS/admin policy.

**Câu hỏi 4:** Một access token có `scope=orders.read` nhưng `aud=payments-api` có dùng tại `orders-api` không?

**Trả lời:** Không. Audience và đúng mục đích token là kiểm tra bắt buộc độc lập với scope.

**Câu hỏi 5:** Thu hồi consent ở AS có bảo đảm JWT đã cấp hết hiệu lực ngay?

**Trả lời:** Không nhất thiết. Phụ thuộc cơ chế thu hồi và cách RS xác minh; cần TTL, denylist, introspection hoặc domain-state check tùy yêu cầu.

**Câu hỏi 6:** `openid email profile` có đồng nghĩa với scope `orders.read` không?

**Trả lời:** Không. Scope OIDC liên quan xác thực và claims về người dùng; quyền đọc đơn hàng thuộc API/business policy riêng.

## Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `scope`, authorization grant, consent/ủy quyền, token response và refresh token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token, `401/403` và `insufficient_scope`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope `openid`, `profile`, `email`, `offline_access` và consent trong OIDC.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): bảo vệ authorization code flow.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): giới hạn token theo resource/audience.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims `scope`, `aud`, `iss` và yêu cầu token profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): metadata và trạng thái opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): ủy quyền giữa các dịch vụ/actor theo mô hình được hỗ trợ.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — DPoP](https://www.rfc-editor.org/rfc/rfc9449): hạn chế sử dụng token bị đánh cắp.

**Điểm cần nhớ:** Scope mô tả quyền truy cập mà client **yêu cầu** hoặc AS **cấp**, consent là sự chấp thuận của chủ thể có thẩm quyền trong các luồng phù hợp, còn **scope policy** ràng buộc quyền được cấp theo client/user/tenant/resource và chính sách tổ chức. Resource server vẫn phải kiểm tra token, audience, scope và quyền trên từng tài nguyên. Cả nút “Đồng ý” lẫn claim `scope` hợp lệ đều không tự cho phép truy cập vượt chính sách.
