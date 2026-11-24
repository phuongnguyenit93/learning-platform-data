# Scope theo thao tác đọc, ghi hoặc quản trị

## Mục tiêu học tập

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, access token giúp truyền thông tin ủy quyền từ Authorization Server đến Resource Server. **Scope** là một cách biểu đạt giới hạn quyền được cấp trong OAuth 2.0. Thiết kế scope phù hợp giúp ứng dụng chỉ nhận quyền cần thiết để **đọc**, **ghi** hoặc thực hiện thao tác **quản trị** trên tài nguyên được bảo vệ.

Sau bài này, bạn có thể:

- Giải thích `scope` trong OAuth 2.0, cách biểu diễn nó trong yêu cầu cấp token, phản hồi token, JWT và kết quả introspection.
- Thiết kế bộ scope đọc/ghi/quản trị phù hợp với ranh giới API, tránh token có quyền quá rộng.
- Phân biệt **scope** với role, permission, audience, issuer và quyền truy cập một đối tượng/tenant cụ thể.
- Ánh xạ scope vào endpoint và thao tác nghiệp vụ; hiểu vì sao HTTP method không tự quyết định quyền.
- Mô tả quy trình Authorization Server cấp scope và Resource Server xác minh token, scope cùng chính sách dữ liệu.
- Phòng tránh leo thang đặc quyền, lạm dụng token bị đánh cắp hoặc phát lại và rủi ro từ scope quản trị.

## 1. Scope là giới hạn thao tác được cấp cho access token

Trong OAuth 2.0, `scope` mô tả **phạm vi truy cập mà một access token được phép đại diện**. Client có thể *yêu cầu* một số scope, nhưng **Authorization Server (AS) mới quyết định** phạm vi được cấp theo đăng ký client, người dùng (nếu có), consent và chính sách. **Resource Server (RS)** phải kiểm tra phạm vi đó trước khi thực hiện hành động.

Ví dụ hệ thống Orders API quy ước ba scope:

```text
orders:read    -> xem đơn hàng theo chính sách người dùng/client
orders:write   -> tạo và cập nhật đơn được phép
orders:admin   -> thao tác quản trị đơn hàng có kiểm soát
```

Các chuỗi `orders:read`, `orders:write`, `orders:admin` là **quy ước riêng của hệ thống minh họa**, không phải quyền được OAuth 2.0 định nghĩa sẵn. OAuth không mặc định rằng `write` bao gồm `read`, hay `admin` bao gồm mọi quyền; **AS và API phải thống nhất ngữ nghĩa** của từng scope.

Một access token chỉ có `orders:read` có thể gọi chức năng đọc mà API cho phép, nhưng không được mặc nhiên tạo, xóa hoặc quản trị đơn hàng. Quan trọng hơn, nó **cũng không mặc nhiên được đọc mọi đơn**: quyền trên từng đơn hàng, tenant, chủ sở hữu hoặc quan hệ phân quyền vẫn phải được API đánh giá.

### Scope đứng ở đâu trong mô hình tin cậy?

| Thành phần | Trả lời câu hỏi | Ví dụ | Trách nhiệm |
| --- | --- | --- | --- |
| `iss` (issuer) | Ai phát hành access token? | `https://identity.example.com` | RS chỉ tin issuer được cấu hình và xác minh được nguồn. |
| `aud` (audience) | Token được cấp cho API nào? | `api://orders` | RS từ chối token dành cho API khác. |
| `sub` / `client_id` | Chủ thể và client liên quan là ai? | `user-42`, `sales-portal` | Phục vụ nhận diện và đánh giá quyền theo ngữ cảnh. |
| `scope` | Token được cấp **những loại thao tác nào**? | `orders:read` | AS giới hạn khi phát hành; RS kiểm tra tại endpoint. |
| Role/permission | Chủ thể được trao vai trò/quyền nào theo mô hình ứng dụng? | `sales-agent` hoặc `approve_order` | Nguồn ủy quyền và API diễn giải theo policy. |
| Object/tenant policy | Có quyền trên **đơn cụ thể** hay không? | Đọc `order-101` của `tenant-a` | RS/PDP hoặc tầng dữ liệu đánh giá theo đối tượng hiện tại. |

**Một token có scope đúng vẫn có thể bị từ chối** vì sai issuer, sai audience, đã hết hạn, không đúng loại token hoặc không có quyền trên resource cụ thể.

## 2. Phân biệt scope đọc, ghi và quản trị

Một hệ thống nên bắt đầu từ các **hành động nghiệp vụ thực tế**, sau đó nhóm chúng thành scope phù hợp với mức rủi ro và nhu cầu của client.

| Nhóm | Scope minh họa | Thao tác có thể cho phép theo hợp đồng | Điều kiện bổ sung |
| --- | --- | --- | --- |
| **Đọc** | `orders:read` | Xem danh sách hoặc chi tiết đơn hàng. | Kiểm tra đơn/tenant/người được phép xem; ẩn trường nhạy cảm. |
| **Ghi** | `orders:create` | Tạo đơn mới. | Kiểm tra tenant, dữ liệu đầu vào và hạn mức. |
| **Ghi** | `orders:update` | Chỉnh sửa đơn đang cho phép cập nhật. | Kiểm tra owner/assignee, trạng thái và rule nghiệp vụ. |
| **Ghi nhạy cảm** | `orders:delete` | Xóa/hủy đơn theo chính sách. | Có thể yêu cầu quyền cao hơn, audit hoặc xác nhận riêng. |
| **Phê duyệt** | `orders:approve` | Phê duyệt hoặc từ chối đơn có ý nghĩa tài chính. | Kiểm tra thẩm quyền phê duyệt, giới hạn tiền, separation of duties. |
| **Quản trị** | `orders:admin` | Quản lý cấu hình/quy trình của module Orders. | Kiểm tra role quản trị đúng phạm vi, tenant và chính sách đặc quyền. |
| **Quản trị danh tính** | `users:roles:manage` | Thay đổi gán vai trò cho người dùng. | Ranh giới identity khác Orders; cần kiểm soát cực chặt và audit. |

Trong một API đơn giản, `orders:write` có thể được định nghĩa là bao gồm *create* và *update*. Khi rủi ro tăng, hãy tách `delete`, `approve` hoặc `admin` thành scope riêng. Việc tách scope không có nghĩa ứng dụng phải xin tất cả: client chỉ nên yêu cầu đúng quyền phục vụ tác vụ.

**Scope quản trị không nên trở thành một “siêu quyền” không giới hạn.** Một quản trị viên của tenant A chưa chắc có quyền quản trị tenant B hoặc hệ thống định danh toàn cục. Khi có thể, dùng scope có ranh giới resource rõ ràng và kiểm tra vai trò/quyền quản trị cụ thể ở phía Resource Server.

### 2.1. Không suy scope chỉ từ HTTP method

Ánh xạ theo HTTP method là điểm khởi đầu, nhưng không đủ cho mọi nghiệp vụ:

| Request | Tác vụ thực | Scope gợi ý |
| --- | --- | --- |
| `GET /orders/101` | Xem đơn. | `orders:read` |
| `POST /orders` | Tạo đơn. | `orders:create` hoặc `orders:write` theo hợp đồng. |
| `PATCH /orders/101` | Sửa đơn. | `orders:update` hoặc `orders:write`. |
| `DELETE /orders/101` | Xóa đơn. | `orders:delete`; không tự cho phép chỉ vì có `orders:write`. |
| `POST /orders/101/approve` | Phê duyệt đơn. | `orders:approve` và policy phê duyệt. |
| `POST /reports/search` | Truy vấn báo cáo, dù là HTTP POST. | Có thể chỉ cần `reports:read`. |
| `GET /admin/export-accounts` | Xuất dữ liệu nhạy cảm, dù là GET. | Scope riêng như `accounts:export` cùng policy nhạy cảm. |

Vì vậy, không viết quy tắc tổng quát “GET = read, mọi POST/PUT/PATCH/DELETE = write”. Tên route và HTTP verb không mô tả hết mức độ nhạy cảm hoặc hậu quả của nghiệp vụ.

### 2.2. Scope rộng và scope hẹp

Hai chiến lược phổ biến:

- **Scope rộng** như `orders:read`, `orders:write`: ít tên, dễ quản trị client, nhưng mỗi scope có thể bao phủ nhiều endpoint và làm tăng hậu quả khi token lộ.
- **Scope theo hành động** như `orders:create`, `orders:update`, `orders:cancel`: chính xác hơn, nhưng cần quản lý danh mục scope và chính sách rõ ràng.

Không có một hệ đặt tên bắt buộc cho mọi hệ thống. Mục tiêu là **mỗi scope có ngữ nghĩa được viết rõ, có owner, có resource đích và được kiểm tra nhất quán**. Nếu quyền quá chi tiết đến từng bản ghi, nên cân nhắc kết hợp scope với ABAC/ReBAC/ACL thay vì tạo hàng triệu scope theo ID đối tượng.

## 3. Scope trong giao thức OAuth 2.0

Theo **RFC 6749 `3.3**, scope là danh sách các **scope-token** ngăn cách bằng dấu cách; tên scope do Authorization Server quy định và **phân biệt chữ hoa/chữ thường**. OAuth không tự diễn giải dấu hai chấm trong `orders:read` hay từ `admin` trong `orders:admin`.

Client có thể yêu cầu:

```text
scope=orders:read orders:update
```

Trong `application/x-www-form-urlencoded`, dấu cách và ký tự đặc biệt phải được encode đúng. Ví dụ yêu cầu cấp token trong luồng **Client Credentials** (client authentication không hiển thị secret thật):

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders%3Aread%20orders%3Aupdate
```

Ví dụ phản hồi:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
```

Ở đây client **yêu cầu** hai scope nhưng chỉ **được cấp** `orders:read`. Nếu chính sách AS cho phép cấp scope hẹp hơn, client phải dựa vào scope **được cấp thực tế** và điều chỉnh nghiệp vụ; nếu không thể thỏa yêu cầu, AS có thể trả lỗi như `invalid_scope`. Theo RFC 6749, khi scope được cấp khác với scope yêu cầu, trường `scope` trong token response là bắt buộc; nếu giống, trường này có thể không xuất hiện. **Không bao giờ suy quyền chỉ từ scope mà client đã yêu cầu.**

**Lưu ý:** đây là giao tiếp OAuth minh họa qua HTTPS; một sản phẩm IAM có thể có endpoint, thông số resource/audience và chính sách riêng. `client_credentials` tạo token theo quyền của **ứng dụng/service principal**, không phải quyền mặc định của một người dùng cuối. Luồng Authorization Code có người dùng và consent sẽ dẫn đến tập quyền được cấp theo chính sách khác.

### 3.1. Các đặc điểm dễ bỏ qua

| Tính chất | Hệ quả triển khai |
| --- | --- |
| Scope là **tập các token ngăn bằng dấu cách** trong `scope` theo OAuth. | `orders:read orders:update` là hai scope, không phải một tên ghép. |
| Tên scope phân biệt chữ hoa/chữ thường. | `orders:read` và `Orders:Read` có thể là hai scope khác nhau. |
| OAuth không quy định thứ bậc scope. | `orders:admin` **không mặc nhiên** tương đương `orders:read + orders:write`. |
| Client yêu cầu không đồng nghĩa AS cấp. | Client phải xử lý `invalid_scope`, thiếu scope hoặc tập scope bị giới hạn. |
| Scope có hiệu lực theo **resource và hợp đồng API**. | Trùng tên `read` ở hai API không đồng nghĩa cùng quyền hoặc có thể dùng chéo token. |
| Thứ tự scope không nên mang ngữ nghĩa nghiệp vụ. | Không so chuỗi thô nguyên văn để kết luận một tập scope có đủ quyền hay không. |

Để kiểm tra `orders:read`, hãy tách trường scope theo quy tắc OAuth và đối chiếu **tên scope đầy đủ**. Tránh kiểm tra substring như `scope.contains("read")`, vì `orders:read-all`, `reports:read` hay một chuỗi không hợp lệ đều có thể tạo ra kết quả sai.

## 4. Scope nằm ở đâu trong JWT và opaque access token?

### 4.1. JWT access token

Một JWT access token được ký theo hợp đồng có thể chứa payload minh họa:

```json
{
  "iss": "https://identity.example.com/realms/retail",
  "sub": "user-42",
  "client_id": "sales-portal",
  "aud": "api://orders",
  "scope": "orders:read orders:update",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900
}
```

Đây là **payload minh họa**, không phải JWT hoàn chỉnh; trong JWT access token profile **RFC 9068**, claim `scope` được thể hiện theo profile cùng các yêu cầu riêng về claims/header (ví dụ phân biệt loại token với `typ = "at+jwt"`). Những nhà cung cấp khác có thể sử dụng `scp`, `roles` hoặc cách mapping riêng. Resource Server phải dựa vào **hợp đồng issuer–API**, không tự suy đoán.

Một chuỗi JWT có ba phần `header.payload.signature` có thể bị bất cứ ai giải mã Base64url để đọc payload. **Chỉ đọc thấy `scope` không chứng minh quyền đã được cấp.** API cần xác minh chữ ký/MAC bằng khóa gắn với issuer tin cậy và kiểm tra `iss`, `aud`, thời hạn, token type cùng scope trước khi sử dụng.

### 4.2. Opaque access token

Một opaque token có thể chỉ là chuỗi không diễn giải được:

```text
Authorization: Bearer eyT9...reference-value...
```

Resource Server không được giả định đây là JWT hoặc tự phân tích `scope` từ chuỗi. Thay vào đó, nó dùng **introspection endpoint đáng tin cậy** (RFC 7662) theo hợp đồng với AS. Phản hồi minh họa:

```json
{
  "active": true,
  "client_id": "sales-portal",
  "sub": "user-42",
  "aud": "api://orders",
  "scope": "orders:read",
  "exp": 1800000900
}
```

Trong RFC 7662, `scope` là một trường của phản hồi introspection **khi áp dụng**; không phải mọi AS đều trả đủ claims ở mọi kịch bản. `active = true` **không có nghĩa** token có quyền quản trị hoặc dành cho API nào cũng được. API cần đủ bằng chứng về audience, scope, client/subject, trạng thái và policy cần thiết; thiếu dữ liệu bắt buộc thì nên từ chối theo hợp đồng hoặc sửa cấu hình introspection.

### 4.3. Refresh token và ID Token

- **Refresh token** là credential để client xin access token mới tại AS; thường là opaque và **không được dùng làm access token** khi gọi Resource Server. Khi refresh, scope mới không được mở rộng vượt phạm vi đã được cấp trước đó theo các điều kiện của RFC 6749 và chính sách AS; muốn quyền mới cần cơ chế ủy quyền tương ứng.
- **OIDC ID Token** là bằng chứng xác thực người dùng dành cho client OIDC, **không phải access token API**. Scope OIDC như `openid`, `profile`, `email` là tín hiệu yêu cầu OIDC/claims theo giao thức; `openid` không có nghĩa “được đọc mọi dữ liệu ở các API”.
- **Client assertion** như `private_key_jwt` dùng để xác thực OAuth client tại token endpoint; nó không thay thế access token có scope phù hợp của Resource Server.

## 5. Ai quyết định phạm vi được cấp?

**Authorization Server** có quyền phát hành access token. Tùy luồng, nó cần xem xét:

1. **Danh tính client** và phương thức xác thực client phù hợp. Client này có được dùng grant type đã yêu cầu không?
2. **Quyền client đã đăng ký**. Client chỉ được xin những scope/resource mà hệ thống cho phép, không tự nâng quyền bằng cách thêm `admin` vào request.
3. **Người dùng/ủy quyền** khi có. Trong Authorization Code flow, người dùng có thể không đủ quyền hoặc chưa đồng ý với một scope dù client đã yêu cầu.
4. **Resource đích/audience**. Các scope cần có ý nghĩa cho API được cấp token; resource indicator (RFC 8707) có thể hỗ trợ yêu cầu token cho tài nguyên cụ thể nếu AS triển khai.
5. **Chính sách theo ngữ cảnh**. Môi trường, tenant, mức rủi ro, yêu cầu xác thực tăng cường, trạng thái tài khoản hoặc hạn mức có thể thu hẹp tập quyền.
6. **Token lifetime và thuộc tính bảo vệ**. Token quyền cao có thể cần TTL ngắn, ràng buộc với người gửi hoặc cơ chế thu hồi khác.

```mermaid
flowchart TD
    A["Client yêu cầu scope<br/>+ resource đích"] --> B["AS xác thực client<br/>và kiểm tra grant"]
    B --> C["Xác định ngữ cảnh user/service<br/>và quyền gốc"]
    C --> D["Áp dụng chính sách resource,<br/>consent, tenant, mức rủi ro"]
    D --> E{"Scope được yêu cầu<br/>có được cấp không?"}
    E -- Không --> F["Từ chối hoặc cấp<br/>tập scope hẹp hơn theo policy"]
    E -- Có --> G["Cấp access token<br/>scope/audience/thời hạn phù hợp"]
```

Trong một thiết kế thông thường, quyền cấp cho access token là **phần giao của các giới hạn có liên quan**: tập client được xin, quyền chủ thể, resource và chính sách AS. Tuy nhiên, cách giao cụ thể khác nhau giữa quyền **delegated user** và quyền **application**; với Client Credentials không có người dùng cuối để lấy “giao quyền người dùng”.

### 5.1. Ví dụ hai loại client

| Client và luồng | Yêu cầu | Quyết định có thể đúng |
| --- | --- | --- |
| `sales-portal` dùng Authorization Code với nhân viên bán hàng. | `orders:read orders:update` | Nếu nhân viên chỉ có quyền xem, AS có thể chỉ cấp `orders:read` hoặc yêu cầu lại ủy quyền theo policy; API vẫn kiểm tra đơn hàng cụ thể. |
| `report-job` dùng Client Credentials. | `orders:read orders:admin` | Nếu job chỉ được đăng ký đọc báo cáo, AS từ chối `orders:admin` và chỉ cấp scope theo chính sách. |
| `tenant-admin-console` có người dùng quản trị tenant A. | `orders:admin` | AS có thể cấp scope theo policy; Orders API vẫn phải kiểm tra **admin của tenant nào** và thao tác cụ thể. |

**MFA hoặc đăng nhập thành công không tự tạo quyền admin.** Xác thực mạnh hơn hỗ trợ bảo vệ phiên đặc quyền, nhưng chủ thể phải có **ủy quyền quản trị hợp lệ**. Tương tự, khi một service có `client_secret` đúng, điều đó chỉ chứng minh danh tính client; không tự cấp các scope ngoài đăng ký.

## 6. Resource Server cần kiểm tra nhiều lớp

Giả sử Orders API bảo vệ endpoint:

```text
GET    /orders/{id}            -> orders:read
PATCH  /orders/{id}            -> orders:update
DELETE /orders/{id}            -> orders:delete
POST   /orders/{id}/approve    -> orders:approve
POST   /admin/orders/settings  -> orders:admin
```

Sau khi client có access token, API không nên chỉ kiểm tra tên scope:

```mermaid
flowchart TD
    A["Request + access token"] --> B{"Token hợp lệ?<br/>iss, chữ ký/trạng thái,<br/>exp/nbf, token kind"}
    B -- Không --> X["401 / Từ chối"]
    B -- Có --> C{"Audience có bao gồm<br/>API đích?"}
    C -- Không --> X
    C -- Có --> D{"Scope đủ cho<br/>thao tác hiện tại?"}
    D -- Không --> Y["403 / Từ chối"]
    D -- Có --> E{"User/client có quyền trên<br/>tenant, đối tượng và trạng thái?"}
    E -- Không --> Y
    E -- Có --> F["Thực hiện và ghi audit<br/>theo chính sách"]
```

**Lưu ý:** mã HTTP trên sơ đồ là quy ước minh họa. Với OAuth Bearer (RFC 6750), token thiếu/hỏng thường dẫn đến `401 Unauthorized`, còn không đủ scope thường là `403 Forbidden` và có thể kèm `WWW-Authenticate` với lỗi `insufficient_scope`. Đối với đối tượng nhạy cảm, API có thể dùng `404 Not Found` theo chính sách để không tiết lộ sự tồn tại.

### 6.1. Ví dụ kiểm tra ở API bằng Java

Pseudocode dưới đây minh họa các điều kiện cần, **không phải API thực của một thư viện**:

```java
Order updateOrder(String orderId, UpdateOrderCommand command, HttpRequest request) {
    // Middleware đã verify JWT hoặc introspect opaque token bằng nguồn tin cậy.
    VerifiedAccessToken token = resourceServer.authenticate(request);

    requireIssuer(token, configuredIssuer);
    requireAudience(token, "api://orders");
    requireAccessTokenKind(token);
    requireScope(token.scopes(), "orders:update"); // kiểm tra tên token chính xác

    Order order = orderRepository.findById(orderId)
        .orElseThrow(NotFoundException::new);

    // Kiểm tra quyền trên tài nguyên từ dữ liệu có thẩm quyền.
    requireCanUpdateOrder(
        token.subject(),
        token.clientId(),
        order.tenantId(),
        order.ownerId(),
        order.status()
    );

    validateBusinessTransition(order, command);
    return orderService.applyUpdateWithAuthorization(order, command);
}
```

Hàm `resourceServer.authenticate` phải **xác minh đầy đủ** chữ ký/thuật toán/claims của JWT hoặc gọi introspection tin cậy với opaque token; đoạn này không cố tự viết lại mật mã. Các bước kiểm tra quyền và cập nhật dữ liệu cần được thiết kế tránh lỗi *time-of-check/time-of-use*, nhất là khi trạng thái resource có thể thay đổi đồng thời.

Đoạn **sai**:

```java
// SAI: vừa tin scope chưa verify, vừa bỏ qua quyền trên orderId cụ thể.
String scope = decodeJwtPayloadWithoutVerification(token).get("scope");
if (scope.contains("write")) {
    return orderRepository.updateAnyOrder(request.orderId(), request.body());
}
```

Lỗi ở đây gồm: (1) đọc claim mà chưa kiểm chứng token, (2) so substring thay vì scope-token chính xác, (3) cho phép cập nhật mọi order mà không kiểm tra tenant/owner hoặc trạng thái.

### 6.2. Spring Security và mapping scope

Với cấu hình Spring Security Resource Server thông dụng, scope của JWT hoặc `scope`/`scp` được framework chuyển thành **GrantedAuthority** dạng `SCOPE_<scope-name>` theo converter mặc định và cấu hình đang áp dụng. Ví dụ:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderView getOrder(String orderId) {
    return orderService.getAuthorizedOrder(orderId);
}
```

Điều kiện ở annotation là **kiểm tra scope tại method**; `getAuthorizedOrder` vẫn phải đánh giá quyền của người gọi trên `orderId`. Trong dự án thật, kiểm tra converter/mapping cho issuer đang dùng, cấu hình JWT/opaque introspection, xử lý issuer/audience và phương pháp bật method security. Không giả định tất cả nhà cung cấp đều dùng `scope` hoặc tạo authority theo cùng quy ước.

### 6.3. Scope không thay thế kiểm tra đối tượng

Giả sử hai đơn hàng:

```text
order-101 -> tenant-a, owner=user-42
order-202 -> tenant-b, owner=user-77
```

Người dùng `user-42` có access token hợp lệ với `aud=api://orders` và `scope=orders:read`. Nếu họ đổi URL từ `/orders/order-101` sang `/orders/order-202`, Orders API phải **từ chối truy cập order-202** nếu không có quyền theo chính sách. Đây là vấn đề **Broken Object Level Authorization (BOLA/IDOR)**; token chứa scope đọc không phải giấy phép đọc mọi bản ghi.

Kiểm tra **tenant**, **owner**, quyền nhóm, trạng thái đơn và các điều kiện ABAC/ReBAC nên dùng thông tin có thẩm quyền ở phía server. Dữ liệu `tenantId` hoặc `ownerId` do client tự truyền trong query/body không được dùng để tự cấp quyền.

## 7. Thiết kế scope quản trị có kiểm soát

Scope quản trị thường cho phép thao tác tác động lớn: đổi chính sách, cấu hình, xuất dữ liệu, quản lý tài khoản hoặc thay đổi vai trò. Vì rủi ro cao, nên tách rõ **quản trị chức năng** với **quản trị toàn hệ thống**.

| Tình huống | Thiết kế phù hợp | Điều cần tránh |
| --- | --- | --- |
| Quản trị module Orders của tenant A. | `orders:admin` + role/claim tenant admin + kiểm tra tenant A. | Chấp nhận `orders:admin` để sửa mọi tenant. |
| Xóa/hủy giao dịch tài chính. | Scope riêng `orders:delete` hoặc `orders:cancel`, thêm policy phê duyệt. | Gộp mọi thao tác nhạy cảm vào `orders:write`. |
| Thay role người dùng trong IAM. | Scope như `users:roles:manage` tại API IAM, kiểm tra thẩm quyền quản trị danh tính. | Cho token dành cho Orders API quyền quản lý tài khoản. |
| Xuất dữ liệu diện rộng. | Scope export riêng, giới hạn dataset và audit; có thể yêu cầu xác thực tăng cường. | Coi `read` là quyền tự do xuất toàn bộ dữ liệu khách hàng. |

Các kiểm soát nên cân nhắc:

1. **Chỉ cấp khi cần** (just-in-time hoặc session ngắn nếu AS hỗ trợ), tránh giữ token có scope quản trị trong job hoặc trình duyệt suốt thời gian dài.
2. **Tách định danh và credential** cho workload quản trị với workload đọc thường xuyên; giới hạn nơi sử dụng token.
3. **Xác thực tăng cường và phê duyệt** cho thao tác rủi ro cao, tùy chính sách; việc có scope admin không chứng minh đã thỏa điều kiện phê duyệt cụ thể.
4. **Ghi audit** ai/ứng dụng nào làm gì, với tài nguyên nào và thời điểm nào; không ghi raw token hoặc client secret.
5. **Thu hồi quyền nhanh** khi tài khoản mất vai trò quản trị; cân nhắc token sống ngắn, tra cứu quyền động/introspection, denylist hoặc session controls.
6. **Giới hạn audience** để token quản trị của API A không được dùng ở API B.

Scope như `admin` không nên được mặc định có hiệu lực **toàn cục**. Khi nhiều API cùng dùng một issuer, việc chấp nhận trùng tên role/scope mà không xác minh audience và resource context có thể dẫn đến **privilege confusion**.

## 8. Scope và role, permission, RBAC/ABAC/ReBAC

Scope thường là **giới hạn quyền được đưa vào access token cho client dùng với API**, còn role và permission thể hiện **cấu trúc phân quyền** của hệ thống:

| Cơ chế | Ví dụ | Phạm vi diễn giải |
| --- | --- | --- |
| **Scope** | `orders:update` | Token được phép yêu cầu thao tác cập nhật Orders API theo policy. |
| **Role (RBAC)** | `sales-manager` | Vai trò của người dùng trong tổ chức hoặc tenant. |
| **Permission** | `APPROVE_ORDER` | Quyền nghiệp vụ cụ thể, có thể được cấp qua role hoặc policy. |
| **ABAC** | Chỉ sửa đơn có `tenantId` thuộc tập được phân công và trạng thái `DRAFT`. | Quyết định dựa trên thuộc tính chủ thể, tài nguyên và môi trường. |
| **ReBAC** | Chỉ sửa đơn khi là owner hoặc thuộc nhóm xử lý được gán. | Quyết định dựa trên quan hệ chủ thể–đối tượng. |

Ví dụ một nhân viên có role `sales-manager`, nhưng token đang dùng chỉ mang `orders:read`. API **không nên tự bỏ qua scope** để cho phép cập nhật chỉ vì role manager. Ngược lại, token có `orders:update` cũng **không đủ** nếu người dùng không có quan hệ được phép sửa đơn đó.

Một mô hình quyết định có ích:

```text
allow(request) =
    validAccessToken
    AND trustedIssuer
    AND expectedAudience
    AND requiredScopePresent
    AND principalHasBusinessPermission
    AND resourceBelongsToAllowedTenant
    AND currentResourceStateAllowsAction
```

Các điều kiện này có thể được đánh giá ở middleware, method authorization, policy engine và tầng dữ liệu, nhưng **không điều kiện nào thay cho điều kiện còn lại**. Nếu quyền nghiệp vụ thay đổi nhanh, cần chính sách kiểm tra trạng thái đủ cập nhật thay vì chỉ tin role được nhúng trong JWT cũ.

## 9. Audience và Resource Indicators: cấp scope đúng API

Không thể hiểu scope tách rời **API nhận token**. Giả sử tổ chức có:

```text
Orders API:  aud=api://orders;  scopes=orders:read, orders:update
Billing API: aud=api://billing; scopes=billing:read, billing:approve
IAM API:     aud=api://identity; scopes=users:roles:manage
```

Access token có `scope=billing:approve` nhưng `aud=api://orders` **không được Billing API chấp nhận** chỉ vì tên scope chứa `billing`. Audience trả lời “token được phát hành **cho API nào**”, scope trả lời “được thực hiện **thao tác nào ở đó**”. Cả hai phải hợp lệ đồng thời.

Nếu AS hỗ trợ **Resource Indicators** (RFC 8707), client có thể chỉ định tài nguyên đích trong yêu cầu:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.com%2Forders
```

`resource` là **yêu cầu** của client, không cho phép client tự chọn bất kỳ audience nào. AS xác minh client có quyền truy cập resource và scope không, sau đó phát hành token với audience theo hợp đồng (có thể ánh xạ `resource` thành `api://orders`). RS phải kiểm tra audience thực tế được công bố trong token/introspection.

### 9.1. Dịch vụ trung gian và downscoping

Khi Orders API gọi Billing API để đọc hóa đơn cho một đơn hàng, **không chuyển nguyên access token chỉ dành cho Orders sang Billing**. Nếu chính sách cho phép, dịch vụ có thể dùng một phương thức cấp token cho Billing hoặc **Token Exchange** (RFC 8693) để nhận token mới có audience và scope hẹp, đồng thời giữ đúng ngữ cảnh ủy quyền:

```mermaid
sequenceDiagram
    autonumber
    participant P as Portal
    participant O as Orders API
    participant AS as Authorization Server
    participant B as Billing API
    P->>O: Token A (aud=orders, orders:read)
    O->>O: Xác minh token A, quyền trên order
    O->>AS: Xin token cho Billing theo policy
    AS->>AS: Xác thực caller + quyền exchange/resource
    AS-->>O: Token B (aud=billing, billing:read)
    O->>B: Token B + request hợp lệ
    B->>B: Kiểm tra issuer, audience, scope, đối tượng
    B-->>O: Dữ liệu Billing được phép
```

**Token Exchange không mặc nhiên được AS hỗ trợ hoặc cho phép.** AS phải kiểm tra danh tính actor, quyền delegation và giới hạn token mới. Việc chuyển sang token có quyền cao hơn người dùng hoặc service cho phép là lỗi **confused deputy/privilege escalation**, dù chữ ký các token đều hợp lệ.

## 10. Vòng đời scope khi cấp lại, thu hồi và token bị lộ

Scope có thể trở nên **lỗi thời** khi người dùng thay vai trò, client bị vô hiệu hoặc quản trị viên thu hồi quyền:

- **JWT access token tự chứa:** chữ ký có thể vẫn hợp lệ đến `exp` ngay cả khi quyền gốc đã bị gỡ, nếu API không kiểm tra trạng thái mới. Cần TTL phù hợp, policy/ACL động hoặc cơ chế thu hồi bổ sung.
- **Opaque access token:** introspection có thể phản ánh trạng thái/giới hạn quyền mới, tùy AS và TTL cache của Resource Server. `active=true` vẫn phải đi cùng kiểm tra audience/scope/policy.
- **Refresh token:** dùng để xin access token mới; AS phải ràng buộc nó với client và phạm vi đã được ủy quyền, đồng thời kiểm tra thu hồi và chính sách hiện tại. Refresh không phải cách tự cấp thêm `admin`.
- **Bearer token bị lộ:** người cầm token có thể thử dùng trong khi còn hiệu lực. Giới hạn audience, scope và TTL giảm phạm vi thiệt hại, nhưng không tự ngăn phát lại.
- **Sender-constrained token:** mTLS certificate-bound access token (RFC 8705) hoặc DPoP (RFC 9449) có thể giảm khả năng sử dụng token bị sao chép nếu AS và RS xác minh bằng chứng sở hữu khóa đúng cách.

Với scope nhạy cảm, thiết kế **thu hồi thực tế** và **kiểm tra quyền ở thời điểm request** quan trọng không kém cách đặt tên. Đổi `client_secret` sau sự cố không có nghĩa tất cả access token cũ đã mất hiệu lực.

### 10.1. Tình huống scope bị nâng trái phép

Kẻ tấn công có token hợp lệ với `orders:read`, sau đó tự sửa payload thành `orders:read orders:admin` và encode lại. Nếu token là JWT dạng JWS, **chữ ký sẽ không còn hợp lệ**; Resource Server kiểm chứng đúng phải từ chối.

Nhưng nếu AS **thật sự** phát hành token có `orders:admin` nhầm cho client thường, chữ ký vẫn hợp lệ. Cần chặn tại **chính sách cấp scope của AS** và **kiểm tra quyền chi tiết của RS**. Mật mã không tự biết một người có được phép quản trị tenant hay không.

## 11. Các lỗi thiết kế scope phổ biến

| Sai sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cấp `admin` cho mọi client để tránh lỗi `403`. | Một token bị lộ có thể gây thiệt hại diện rộng. | Cấp quyền tối thiểu theo client, tác vụ và resource. |
| Cho rằng `orders:write` mặc nhiên cho phép xóa, duyệt và đổi quyền. | Thao tác rủi ro cao bị đưa vào nhóm quyền thông thường. | Định nghĩa action rõ, tách scope cho hành động nhạy cảm. |
| Kiểm tra `scope.contains("read")`. | Tên scope tương tự có thể bị nhận nhầm. | Parse thành các scope-token chính xác, đối chiếu tên đầy đủ. |
| Coi role `ADMIN` trong JWT là quyền toàn cục. | Người quản trị tenant A có thể truy cập tenant B. | Phạm vi role/permission theo resource/tenant, policy động. |
| Bỏ qua `aud` nếu token có scope phù hợp. | Token dành cho API khác có thể được dùng trái mục đích. | Xác minh audience của chính Resource Server. |
| Chỉ decode JWT rồi đọc scope. | Attacker có thể tự khai scope trong payload. | Verify signature/MAC với khóa issuer tin cậy trước khi tin. |
| Để client tự chọn scope cao bất kỳ tại token endpoint. | Leo thang quyền từ cấp phát token. | AS đối chiếu đăng ký, grant, user/consent và resource policy. |
| Dùng scope đọc để trả mọi trường dữ liệu. | Rò rỉ thông tin cá nhân, dữ liệu nhạy cảm hoặc tenant khác. | Phân quyền ở cấp đối tượng/trường dữ liệu, giới hạn response. |
| Dùng token Client Credentials như token quyền người dùng. | Service quyền cao thực hiện việc user không được phép. | Phân biệt application permission với delegated user permission. |
| Chỉ xoay client secret và tưởng token đã cấp bị hủy. | JWT còn hạn vẫn có thể được API chấp nhận. | Xử lý revocation, TTL, trạng thái token và policy RS. |
| Coi `openid` là scope quyền quản trị API. | Nhầm OIDC authentication với authorization của Resource Server. | Tách OIDC scopes/ID Token khỏi API access scopes. |

## 12. Tình huống thực hành

Một cửa hàng vận hành Orders API với scope:

```text
orders:read     Xem đơn được phân quyền
orders:update   Sửa đơn được phân quyền ở trạng thái DRAFT
orders:approve  Phê duyệt đơn trong hạn mức của người dùng
orders:admin    Cấu hình module Orders trong tenant được quản trị
```

Nhân viên `u-17` có quyền đọc và sửa đơn nháp của tenant A nhưng không có quyền phê duyệt. Client `sales-portal` xin token cho `aud=api://orders` với `scope=orders:read orders:update orders:approve`. AS cấp token chỉ có `orders:read orders:update`.

| Yêu cầu | Quyết định | Giải thích |
| --- | --- | --- |
| `GET /orders/A-101`; đơn thuộc tenant A và user được phép xem. | **Cho phép** nếu token hợp lệ. | Đúng audience, scope và policy đối tượng. |
| `PATCH /orders/A-101`; đơn đang `DRAFT` và user được phép sửa. | **Cho phép** nếu token hợp lệ. | Đúng `orders:update` và rule nghiệp vụ. |
| `POST /orders/A-101/approve`. | **Từ chối**. | AS không cấp `orders:approve`; user cũng không có quyền phê duyệt. |
| `GET /orders/B-202`; đơn thuộc tenant B. | **Từ chối**. | Có `orders:read` nhưng không có quyền trên đối tượng. |
| `DELETE /orders/A-101`; token có `orders:update`. | **Từ chối** nếu yêu cầu quyền xóa riêng. | `update` không mặc nhiên chứa `delete`. |
| `POST /admin/orders/settings`; user không phải admin tenant A. | **Từ chối**. | Không có `orders:admin` và không đủ policy quản trị. |
| Dùng token Orders gọi Billing API có `aud=api://billing`. | **Từ chối tại Billing**. | Access token không dành cho Billing API. |
| Token đã hết hạn dù có `orders:read`. | **Từ chối**. | Token không còn hiệu lực. |

**Câu hỏi tự kiểm tra**

1. Vì sao `scope=orders:read` không tự cho phép đọc tất cả đơn trong hệ thống?
2. `orders:admin` có tự động bao gồm `orders:update` không? Ai quyết định?
3. Vì sao một HTTP `POST` có thể chỉ cần scope đọc?
4. Client xin `orders:approve` nhưng AS chỉ cấp `orders:read`. Phía client nên tin tập scope nào?
5. Tại sao token được ký hợp lệ, có `orders:approve` vẫn có thể phải từ chối phê duyệt đơn?
6. Khi nào nên tách scope `orders:write` thành `orders:create`, `orders:update` và `orders:delete`?
7. Sau khi tài khoản mất vai trò quản trị, vì sao JWT cũ vẫn có thể được nhận và cách giảm rủi ro là gì?

**Gợi ý trả lời:** (1) Scope cho phép loại thao tác, còn quyền theo tenant/owner/đối tượng do API kiểm tra. (2) Không mặc định; AS/API quy định ngữ nghĩa và policy. (3) HTTP method không phản ánh đầy đủ nghiệp vụ, ví dụ POST tìm kiếm báo cáo. (4) Scope được cấp thực tế trong token/response, không phải request. (5) Cần đúng issuer/audience/thời hạn, token type, giới hạn phê duyệt và trạng thái tài nguyên. (6) Khi tác vụ có rủi ro và đối tượng được ủy quyền khác nhau. (7) Chữ ký còn hợp lệ đến `exp`; giảm TTL, kiểm tra policy động, introspection/thu hồi khi cần.

## 13. Checklist thiết kế và triển khai

- [ ] Xác định rõ ý nghĩa từng scope đọc, ghi, duyệt, xóa và quản trị; quy định scope có bao gồm nhau hay không.
- [ ] Gắn scope với **resource/audience**; tránh các chuỗi quá chung như `read`, `write` hoặc `admin` không có ngữ cảnh API.
- [ ] Đăng ký phạm vi được xin của từng client; AS kiểm tra grant type, user/consent, tenant và resource policy trước khi cấp.
- [ ] Client sử dụng **scope được cấp**, xử lý thiếu scope/`invalid_scope`; không tự nâng quyền dựa trên yêu cầu gửi đi.
- [ ] Resource Server xác minh issuer, chữ ký hoặc introspection, audience, thời hạn, token type và scope trước khi xử lý.
- [ ] Kiểm tra scope-token theo **tên đầy đủ**, không dùng substring, không suy quyền qua HTTP method đơn thuần.
- [ ] Thực thi thêm authorization theo tenant, owner, ACL/ABAC/ReBAC và trạng thái của resource.
- [ ] Tách hành động nhạy cảm như approve, delete, export và role management khỏi scope ghi thông thường.
- [ ] Với token quản trị, giới hạn TTL, audience, nơi lưu, audit, thu hồi và xác thực tăng cường khi cần.
- [ ] Phân biệt quyền client credentials với delegated user access; không dùng ID Token/refresh token làm access token API.
- [ ] Kiểm thử trường hợp sai audience, sai issuer, token hết hạn, thiếu scope, scope gần giống tên, sai tenant và quyền bị thu hồi.

## Tài liệu nền tảng

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** mục `3.3` (Access Token Scope), cấp token, phản hồi scope và Client Credentials grant.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách mang bearer token và lỗi `insufficient_scope`.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái `active` và scope trong phản hồi introspection.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource đích và yêu cầu token cho API cụ thể.
- **RFC 8693 — OAuth 2.0 Token Exchange:** trao đổi token và giới hạn quyền theo chính sách AS.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** biểu diễn claims của access token JWT và kiểm tra tại Resource Server.
- **OpenID Connect Core 1.0:** `openid`, `profile`, `email`, ID Token và phạm vi OIDC.
- **RFC 8705 / RFC 9449:** mTLS sender-constrained token và DPoP giúp giảm nguy cơ dùng lại token bị đánh cắp.

**Ghi nhớ:** **Scope giới hạn loại thao tác**, **audience giới hạn API nhận token**, còn **quyền trên đối tượng và tenant** do Resource Server kiểm tra. Scope `read`, `write` hay `admin` chỉ có ý nghĩa theo hợp đồng và chính sách thực tế; một access token được phát hành đúng vẫn không trở thành giấy phép truy cập toàn bộ tài nguyên. Hãy cấp **ít quyền đủ dùng**, phân tách thao tác nhạy cảm và kiểm tra nhiều lớp trong suốt vòng đời token.
