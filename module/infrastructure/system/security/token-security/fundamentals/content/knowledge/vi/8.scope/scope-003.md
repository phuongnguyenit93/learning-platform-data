# Scope theo resource server

## Mục tiêu học tập

Trong chương **Scope** của học phần bảo mật token, vấn đề quan trọng là: một access token có scope phù hợp **chỉ có ý nghĩa trong phạm vi Resource Server (API) mà token được cấp cho**. Hai API cùng nhận một chuỗi scope không có nghĩa chúng có thể dùng chung token hoặc diễn giải chuỗi đó thành quyền giống nhau.

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa **Authorization Server**, **Resource Server**, **client**, **scope**, **audience** và **resource indicator** trong OAuth 2.0/OIDC.
2. Thiết kế phạm vi ủy quyền cho từng API mà không tạo quyền dùng chung ngoài ý muốn giữa các dịch vụ.
3. Mô tả cách client yêu cầu token cho một tài nguyên đích và cách Resource Server kiểm tra token bằng JWT hoặc opaque token.
4. Phân biệt **token hợp lệ tại API**, **scope đủ để yêu cầu thao tác** và **quyền đối với bản ghi/tenant cụ thể**.
5. Nhận diện lỗi chuyển tiếp token sai audience, scope trùng tên nhưng sai ngữ nghĩa, token có quyền quá rộng, thiếu kiểm tra ở service và nguy cơ phát lại bearer token.

## 1. Scope không tồn tại độc lập với API nhận token

**Scope** biểu diễn phạm vi ủy quyền mà client được cấp khi truy cập tài nguyên. Trong OAuth 2.0, scope thường là những chuỗi như `orders:read`, `orders:write` hoặc `payments:refund`. Ý nghĩa của chúng do **Authorization Server (AS)** và **Resource Server (RS)** thống nhất, dưới một hợp đồng bảo mật cụ thể.

Xét hệ thống bán hàng gồm:

- **Orders API**: đọc và quản lý đơn hàng.
- **Billing API**: xem hóa đơn và hoàn tiền.
- **Profile API**: xem và chỉnh sửa thông tin tài khoản.

Ví dụ chính sách cấp quyền:

| Resource Server | Audience dùng trong ví dụ | Scope được định nghĩa | Ý nghĩa tại API đích |
|---|---|---|---|
| Orders API | `orders-api` | `orders:read` | Có thể yêu cầu đọc những đơn được phép xem. |
| Orders API | `orders-api` | `orders:write` | Có thể yêu cầu tạo/sửa đơn theo chính sách nghiệp vụ. |
| Billing API | `billing-api` | `billing:read` | Có thể yêu cầu đọc hóa đơn được phép xem. |
| Billing API | `billing-api` | `payments:refund` | Có thể yêu cầu hoàn tiền nếu đáp ứng chính sách phê duyệt. |
| Profile API | `profile-api` | `profile:read` | Có thể yêu cầu đọc hồ sơ được phép xem. |

Một token mang `scope=orders:read` và `aud=orders-api` **không** được Billing API dùng để cấp quyền đọc hóa đơn. Ngay cả khi cả hai API tin cùng một AS và dùng một cặp khóa ký, **audience** vẫn phải được kiểm tra độc lập với scope.

> **Nguyên tắc:** scope trả lời “được cấp phép yêu cầu loại thao tác nào?”, audience trả lời “token được dành cho bên nhận nào?”, còn chính sách phân quyền của API trả lời “principal được thao tác lên tài nguyên cụ thể nào?”.

### Đừng coi tên scope là quyền toàn cục

AS có thể định nghĩa scope theo chính sách riêng của từng hệ thống. Chuỗi `read` ở API A có thể mang ý nghĩa khác hoàn toàn chuỗi `read` ở API B. Nếu dùng tên quá chung, người thiết kế dễ mắc lỗi **scope confusion**: API mới nhận token của API khác chỉ vì cả hai đều kiểm tra `read`.

Tên có cấu trúc như `orders:read` hay `billing:read` thường dễ quản lý hơn, **nhưng tên có prefix chưa thay được việc kiểm tra audience**. Không có quy tắc OAuth chung nào tự động liên kết chuỗi `orders:read` với URL của Orders API; quan hệ này phải được AS và RS xác định rõ.

## 2. Phân biệt scope, audience, resource indicator và quyền trên tài nguyên

Các yếu tố này liên quan nhưng phục vụ những bước khác nhau:

| Yếu tố | Bên liên quan | Vai trò |
|---|---|---|
| **`scope`** | Client đề nghị; AS quyết định cấp; RS kiểm tra | Tập phạm vi ủy quyền cho phép yêu cầu những hành động nào. |
| **`resource` (resource indicator)** | Client gửi cho AS khi profile hỗ trợ | Xác định tài nguyên hoặc dịch vụ đích mà client muốn nhận token để truy cập. |
| **`aud` (audience)** | AS gắn vào token/metadata; RS đối chiếu | Ràng buộc token với một hoặc nhiều đối tượng nhận được phép. |
| **`iss` (issuer)** | AS phát hành; RS xác minh | Nguồn phát hành mà RS đã cấu hình tin cậy. |
| **Principal/subject** | AS cung cấp thông tin; RS thiết lập danh tính | Chủ thể cần xét quyền; có thể là người dùng hoặc ứng dụng/dịch vụ. |
| **Resource authorization** | RS và dữ liệu nghiệp vụ | Chủ thể có quyền đối với bản ghi, tenant, trạng thái và hành động cụ thể không. |

**Resource indicator** trong RFC 8707 là một cách để client nói với AS “tôi muốn token dành cho tài nguyên này”. Ví dụ:

~~~text
resource=https://api.example.test/orders
~~~

Giá trị `resource` được đưa vào yêu cầu cấp quyền theo giao thức khi AS hỗ trợ. AS dựa vào chính sách để cấp token giới hạn đúng tài nguyên đích. Trong ví dụ của bài này, AS ánh xạ tài nguyên `https://api.example.test/orders` thành audience `orders-api`. **Đây là quy ước minh họa:** trong hệ thống khác, audience có thể là chính URI hoặc một định danh khác theo hợp đồng; không được mặc định giá trị `resource` luôn bằng chuỗi `aud`.

Trong JWT access token, `aud` có thể là chuỗi hoặc mảng theo profile. Với opaque token, thông tin audience có thể đến từ **token introspection** hoặc kho trạng thái đáng tin cậy. **Không phải mọi access token đều là JWT**.

### Ba ranh giới được kiểm tra độc lập

Giả sử token đã được xác minh là của AS tin cậy:

~~~text
iss   = "https://auth.example.test"
aud   = "orders-api"
scope = "orders:read"
sub   = "user-123"
~~~

RS vẫn cần xét:

1. **Ranh giới nơi nhận:** request có thực sự đến `orders-api` không? Billing API phải từ chối token này.
2. **Ranh giới thao tác:** `orders:read` có cho phép gọi `DELETE /orders/42` không? Không, nếu xóa cần quyền khác.
3. **Ranh giới đối tượng:** user-123 có được đọc **order 42** của một chủ thể hoặc tenant khác không? Không, trừ khi có chính sách ủy quyền cụ thể cho phép.

Chữ ký JWT hợp lệ hoặc introspection trả `active=true` không tự bỏ qua ba kiểm tra trên.

## 3. Một luồng cấp access token theo Resource Server

Hãy xem client muốn gọi **Orders API**, và AS hỗ trợ Resource Indicators (RFC 8707) với quy ước ánh xạ đã mô tả.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as Shop Client
    participant AS as Authorization Server
    participant Orders as Orders API
    participant Billing as Billing API
    User->>Client: Muốn xem đơn hàng
    Client->>AS: Authorization request: scope=orders:read, resource=Orders URI, PKCE
    AS->>User: Xác thực / lấy quyết định ủy quyền khi cần
    AS-->>Client: Authorization code
    Client->>AS: Đổi code tại token endpoint (PKCE)
    AS-->>Client: Access token cho Orders API
    Client->>Orders: GET /orders + Bearer access token
    Orders->>Orders: Xác minh iss, aud, scope và quyền dữ liệu
    Orders-->>Client: Dữ liệu đơn được phép
    Client->>Billing: Thử dùng lại token Orders
    Billing-->>Client: Từ chối vì sai audience
~~~

Ví dụ **yêu cầu ủy quyền rút gọn**, chỉ minh họa các tham số liên quan:

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<STATE_PLACEHOLDER>&code_challenge=<PKCE_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Ứng dụng thật phải xử lý `state`, `redirect_uri`, `code_verifier`/`code_challenge` và các yêu cầu bảo mật khác theo luồng đã chọn. **Không phải AS nào cũng hỗ trợ tham số `resource`**; khi không hỗ trợ, cách chỉ định API đích phải được xác định bằng một hợp đồng tin cậy khác của hệ thống (ví dụ cấu hình client, loại grant hoặc cơ chế cấp audience riêng), không tự suy rằng scope là đủ để ràng buộc token.

Một access token JWT mà AS có thể cấp trong mô hình minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Đây chỉ là **payload minh họa**, không phải token thật và không thể dùng để xác thực nếu thiếu bảo vệ mật mã phù hợp. Các claim thời gian là NumericDate (giây Unix). Nếu AS phát hành **opaque token**, client không thấy các claims; RS xác minh qua nguồn tin cậy để lấy audience, scope và trạng thái cần thiết.

### Client yêu cầu khác với AS đã cấp

Nếu client yêu cầu `orders:read orders:write`, AS có thể chỉ cấp `orders:read`. Client phải dựa trên **scope thực sự được cấp** và xử lý việc thiếu quyền, không lấy chuỗi scope yêu cầu ban đầu làm sự thật.

Khi sử dụng refresh token, phạm vi token mới cũng phải tuân theo giới hạn đã ủy quyền và chính sách AS; refresh không phải cách bí mật nâng scope lên quyền cao hơn.

## 4. Thiết kế namespace scope khi có nhiều API

Một hệ thống lớn cần quản lý rõ **scope thuộc domain/API nào**. Có ba chiến lược thường gặp:

| Chiến lược | Ví dụ | Đánh đổi |
|---|---|---|
| **Tên chung** | `read`, `write` | Dễ tái sử dụng nhưng khó phân biệt ngữ nghĩa; dễ scope confusion khi nhiều RS. |
| **Tên theo domain và action** | `orders:read`, `billing:read` | Dễ rà soát, thường phù hợp khi AS cấp token cho nhiều API. |
| **Tên chi tiết theo nghiệp vụ** | `orders:cancel`, `payments:refund`, `reports:export` | Quyền rõ và hẹp hơn nhưng nhiều scope cần quản trị và tài liệu. |

**Không phải cứ đặt nhiều scope là an toàn hơn.** Cần căn cứ các ranh giới nghiệp vụ thật: một số thao tác có thể dùng cùng permission, số khác như hoàn tiền hoặc xuất dữ liệu nhạy cảm nên có phạm vi riêng và kiểm tra điều kiện bổ sung.

Một mẫu hợp đồng tối thiểu giữa AS và RS:

~~~yaml
# Mô tả minh họa hợp đồng; không phải file cấu hình thực thi.
resource_servers:
  orders:
    resource_indicator: https://api.example.test/orders
    audience: orders-api
    accepted_scopes:
      - orders:read
      - orders:write
      - orders:cancel
  billing:
    resource_indicator: https://api.example.test/billing
    audience: billing-api
    accepted_scopes:
      - billing:read
      - payments:refund
~~~

Tài liệu hợp đồng nên nêu cụ thể:

1. **Định danh RS:** issuer tin cậy, resource indicator (nếu dùng), audience và endpoint API.
2. **Danh mục scope:** cú pháp, ý nghĩa, action được bảo vệ và chủ thể/client được phép yêu cầu.
3. **Chính sách cấp:** consent khi cần, grant được hỗ trợ, quyền tối thiểu và thời hạn access token.
4. **Chính sách thực thi:** API nào kiểm tra scope, quyền đối tượng, tenant và những ngoại lệ nghiệp vụ.
5. **Quy tắc thay đổi:** thêm/xóa/đổi nghĩa scope, tương thích client cũ và chiến lược thu hồi token đã cấp.

Không dùng câu “có scope `admin` là được mọi quyền” khi hệ thống có nhiều API và tenant. Cần chỉ rõ `admin` (nếu tồn tại) có nghĩa gì, thuộc RS nào và còn bị ràng buộc bởi những điều kiện nào.

## 5. Một access token có thể dành cho nhiều Resource Server không?

**Có thể, nếu AS chủ động hỗ trợ và các RS chấp nhận theo chính sách tin cậy chung.** Không phải mọi token đều bắt buộc chỉ có một audience. Tuy nhiên, cấp token có nhiều audience làm tăng số dịch vụ mà một bearer token bị lộ có thể được sử dụng.

### Minh họa một token nhiều audience

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["orders-api", "reporting-api"],
  "scope": "orders:read reports:read",
  "sub": "user-123",
  "exp": 1893456900
}
~~~

Token này **chỉ nên** được phát hành nếu AS có quy tắc cấp scope/audience minh bạch và cả hai RS được thiết kế để diễn giải claims chính xác. Mỗi RS phải chỉ chấp nhận scope được định nghĩa cho mình, không tự suy quyền từ scope của RS khác.

### Vì sao thường ưu tiên token theo từng API?

- **Giảm thiệt hại khi bị lộ:** token cho `orders-api` không thể đem gọi `billing-api` khi Billing kiểm tra audience đúng.
- **Rõ ràng về mục đích:** không cần diễn giải scope thuộc API nào trong tập audience phức tạp.
- **Dễ kiểm tra và thu hồi theo ngữ cảnh:** TTL, chính sách phiên, phát hiện bất thường và quyền nhạy cảm có thể khác giữa API.
- **Tránh chia sẻ quyền vô tình:** một thành phần chỉ cần đọc đơn không nhất thiết được gửi cả token có quyền hoàn tiền.

Điều đó không có nghĩa “nhiều audience luôn sai”; lựa chọn phụ thuộc chính sách bảo mật, cấu trúc API và tiêu chuẩn/profile sử dụng. Điểm quan trọng là **AS phải cấp có chủ đích và RS phải kiểm tra đúng đối tượng nhận**.

## 6. Resource Server xác minh scope và audience thế nào?

Tại RS, quyết định nên theo nhiều lớp; không được chỉ tách chuỗi scope từ một JWT chưa xác minh.

~~~mermaid
flowchart TD
    A["Request tới Orders API"] --> B{"Có token và đúng định dạng?"}
    B -- Không --> X["401 Unauthorized"]
    B -- Có --> C{"Xác minh nguồn issuer và token?"}
    C -- Không --> X
    C -- Có --> D{"aud chứa orders-api? Đúng token type và còn hiệu lực?"}
    D -- Không --> X
    D -- Có --> E{"Scope cần cho action đã được cấp?"}
    E -- Không --> Y["403 Forbidden"]
    E -- Có --> F{"Principal có quyền trên order/tenant cụ thể?"}
    F -- Không --> Y
    F -- Có --> G["Cho phép thao tác đúng phạm vi"]
~~~

### JWT access token

Nếu token là JWT, dùng thư viện JWT/JOSE tin cậy để:

- Xác minh chữ ký với tập khóa phù hợp **issuer đã được cấu hình tin cậy**, giới hạn thuật toán và kiểm tra `iss`.
- Kiểm tra `aud` theo **giá trị kỳ vọng của RS hiện tại**; xử lý chuỗi/mảng đúng theo profile, không tìm chuỗi con.
- Kiểm tra `exp`, `nbf`, loại access token, trạng thái nếu có quy tắc thu hồi sớm và proof ràng buộc người gửi nếu token cần DPoP/mTLS.
- Chỉ sau bước trên mới lấy `scope` hoặc claim quyền được định nghĩa trong hợp đồng để phân quyền.

Trong profile JWT access token của RFC 9068, `scope` được biểu diễn theo quy tắc của profile khi có phạm vi được cấp. Không nên cho phép mọi dạng claim tùy ý hoặc tự gán `scope=admin` khi token không có trường bắt buộc.

### Opaque access token

Nếu token là opaque, RS không thể suy scope/audience bằng cách nhìn prefix hoặc độ dài chuỗi. RS thường dùng **token introspection** (RFC 7662), hoặc hệ thống tra cứu đã được thiết kế và bảo vệ, rồi kiểm tra phản hồi:

~~~json
{
  "active": true,
  "client_id": "shop-web",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456900
}
~~~

Đây là **phản hồi minh họa**, không phải dữ liệu thật. RS chỉ tin kết quả từ endpoint/kho trạng thái đáng tin cậy với xác thực và kênh bảo mật thích hợp. `active=true` **chưa đủ**: còn phải kiểm tra audience, scope và quyền tài nguyên. Nếu thiếu thuộc tính bắt buộc theo hợp đồng, **không mặc định cho phép**.

Cache introspection có thể làm chậm hiệu lực thu hồi; AS/RS phải thống nhất thời gian cache và yêu cầu cập nhật quyền.

### Mã giả cho Orders API

~~~text
handle(GET /orders/{orderId}, request):
    rawToken = parseBearerAuthorization(request)
    if rawToken missing or malformed:
        return 401

    policy = trustedResourceServerPolicy("orders-api")
    verified = validateAccessToken(rawToken, policy)
      # JWT: verify issuer, signature, key/alg, aud, exp, nbf, type
      # opaque: trusted introspection + active + metadata
    if verified invalid:
        return 401

    if policy.requiresSenderProof and not validateSenderProof(request, rawToken):
        return 401
    if not verified.scopes.containsExact("orders:read"):
        return 403

    order = ordersRepository.find(orderId)
    if order not found:
        return 404
    if not policy.canReadOrder(verified.principal, order):
        return 403  # Có thể dùng 404 theo chính sách che giấu tài nguyên

    return 200 with authorized order fields
~~~

Trong đó, `verified.scopes` phải là tập scope được **chuẩn hóa từ dữ liệu đã xác minh**. So khớp **chính xác** theo danh sách được cấp: đừng dùng `scopeString.contains("read")` vì token có `reports:read` không hề chứng minh quyền `orders:read`.

## 7. Scope được cấp không thay quyền theo từng đối tượng

Giả sử một access token hợp lệ cho Orders API:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "exp": 1893456900
}
~~~

Trong khi đơn hàng yêu cầu đọc:

~~~json
{
  "id": "order-42",
  "ownerId": "user-999",
  "tenantId": "tenant-b",
  "status": "PAID"
}
~~~

Token đi qua kiểm tra issuer, chữ ký, audience, hạn dùng và scope, nhưng người dùng **không được đọc order-42** nếu không có quyền liên tenant cụ thể. Chính sách có thể đòi đồng thời:

~~~text
scope includes orders:read
AND principal.tenant == order.tenant
AND (
    principal.subject == order.owner
    OR principal has delegated orders:read:any in this tenant
)
~~~

**Scope thường là giới hạn quyền ở cấp API/action, không phải chứng nhận quyền trên từng bản ghi.** Hệ thống phải kiểm tra BOLA/IDOR, chủ sở hữu, tenant, quan hệ được ủy quyền và trạng thái dữ liệu ở nơi thực hiện thao tác. Một role `admin` của tenant A không tự làm chủ thể thành admin của tenant B.

### Ví dụ policy Java (không tự triển khai JWT verifier)

Đoạn dưới đây chỉ minh họa **kiểm tra quyền sau khi lớp bảo mật đã xác minh token**:

~~~java
import java.util.Objects;
import java.util.Set;

record VerifiedPrincipal(
    String subject,
    String tenantId,
    Set<String> scopes,
    Set<String> permissions
) {}

record Order(String id, String ownerId, String tenantId) {}

final class OrderPolicy {
    static boolean mayRead(VerifiedPrincipal principal, Order order) {
        if (principal == null || order == null
                || principal.scopes() == null
                || !principal.scopes().contains("orders:read")) {
            return false;
        }
        if (principal.tenantId() == null
                || principal.tenantId().isBlank()
                || !Objects.equals(principal.tenantId(), order.tenantId())) {
            return false;
        }
        boolean owner = principal.subject() != null
                && Objects.equals(principal.subject(), order.ownerId());
        boolean delegatedRead = principal.permissions() != null
                && principal.permissions().contains("orders:read:any");
        return owner || delegatedRead;
    }
}
~~~

`VerifiedPrincipal` phải được dựng từ **security context đã xác minh**, trong đó quyền theo tenant được lấy hoặc kiểm tra từ nguồn đáng tin. Khi quyền có thể thay đổi trong lúc token còn hạn, cần cơ chế độ tươi và thu hồi phù hợp. Quyền đọc không tự cấp quyền sửa/xóa đơn.

## 8. Microservices: chuyển tiếp token sang API khác có đúng không?

Giả sử client gọi Orders API, và Orders API cần gọi Billing API để tính công nợ. Có hai mối quan hệ cần tách:

1. **Client → Orders API:** access token cho `orders-api` với `orders:read`.
2. **Orders API → Billing API:** danh tính và quyền của Orders API khi gọi `billing-api`, hoặc một hình thức ủy quyền *on behalf of* người dùng được AS hỗ trợ.

**Chuyển nguyên access token đầu vào** từ Orders sang Billing thường sai nếu `aud=orders-api`. Billing API phải từ chối, ngay cả khi JWT có cùng chữ ký AS và có scope đọc đơn.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Orders as Orders API
    participant AS as Authorization Server
    participant Billing as Billing API
    Client->>Orders: Bearer token aud=orders-api
    Orders->>Orders: Xác minh và phân quyền truy cập đơn
    Orders->>AS: Xin token cho billing-api theo luồng được cho phép
    Note over Orders,AS: Có thể là client credentials hoặc token exchange
    AS-->>Orders: Access token aud=billing-api, scope phù hợp
    Orders->>Billing: Bearer token aud=billing-api
    Billing->>Billing: Xác minh token, scope và quyền nghiệp vụ
    Billing-->>Orders: Chỉ dữ liệu được phép
~~~

Các phương án tùy quan hệ tin cậy:

| Phương án | Khi nào phù hợp | Điều cần kiểm soát |
|---|---|---|
| **Token riêng cho service** (ví dụ `client_credentials`) | Orders gọi Billing với **danh tính dịch vụ** và quyền được cấp cho service. | Không tự biến quyền của service thành quyền người dùng; kiểm tra nghiệp vụ và tenant. |
| **Token exchange** (RFC 8693) | AS hỗ trợ trao đổi token để cấp token mới cho audience/scope đích theo chính sách. | Không tự mở rộng quyền, giữ vết chủ thể/actor và delegation phù hợp. |
| **On-behalf-of theo profile hệ thống** | Quyền phụ thuộc người dùng gốc và AS có cơ chế delegation tương ứng. | Khác biệt giữa user, client, actor; hạn chế audience/scope, chống confused deputy. |

**Token exchange không phải “client tự sửa claim `aud`”.** Nó là giao dịch với AS để xét chính sách và phát hành token mới. Không nhất thiết hệ thống nào cũng hỗ trợ RFC 8693. Khi không có cơ chế phù hợp, phải thiết kế ranh giới service rõ ràng, không bỏ qua kiểm tra audience để “cho hệ thống chạy”.

### Gateway kiểm tra scope đã đủ chưa?

API Gateway có thể xác minh token, route hoặc áp dụng chính sách chung. Nhưng service sở hữu dữ liệu thường là nơi biết **order nào thuộc user và tenant nào**. Nếu chỉ kiểm tra `orders:read` tại gateway rồi service tự trả bất kỳ order ID, hệ thống vẫn có lỗi BOLA. Resource Server chịu trách nhiệm cuối cùng về quyền trên dữ liệu của mình.

## 9. Thu hẹp scope, thu hồi và chống token bị lạm dụng

### Quyền tối thiểu theo Resource Server

- Client chỉ xin scope cần dùng cho chức năng hiện tại, ví dụ `orders:read` khi chỉ hiển thị đơn.
- AS chỉ cấp scope được phép cho **client, principal, tài nguyên đích** và chính sách ủy quyền.
- RS chỉ chấp nhận scope dành cho mình, và kiểm tra permission/ownership cho từng thao tác.
- Với thao tác nhạy cảm như `payments:refund`, cân nhắc TTL ngắn, kiểm tra quyền hiện hành, phê duyệt bổ sung và phân tách vai trò.

### Refresh token không phải cách vượt phạm vi

**Refresh token** được dùng ở token endpoint để xin access token mới, không gửi trực tiếp cho API nghiệp vụ. Việc làm mới không được cho phép client tùy tiện **nâng scope vượt quyền đã ủy quyền**. Khi người dùng bị thu hồi quyền, AS/RS cần thiết kế quy tắc vô hiệu hóa hoặc cập nhật token, trạng thái phiên và cache sao cho mức trễ chấp nhận được.

### Scope và audience giới hạn thiệt hại, không tự ngăn replay

Bearer access token bị sao chép có thể được attacker trình lại khi còn hiệu lực. **Scope hẹp** làm giảm loại hành động có thể bị lạm dụng; **audience hẹp** giảm số API có thể nhận token; **TTL ngắn** giảm thời gian khai thác. Nhưng nếu attacker gửi token cho đúng RS với đúng scope trước khi hết hạn, request vẫn có thể được chấp nhận.

Các biện pháp bổ sung gồm:

- HTTPS/TLS; không đưa bearer token vào URL, log, analytics, crash report, ticket hỗ trợ.
- Lưu trữ phù hợp nền tảng; giảm khả năng XSS đọc token trong trình duyệt và bảo vệ refresh token.
- Chính sách thu hồi, theo dõi phiên, phát hiện sử dụng bất thường và độ trễ cache phù hợp.
- **DPoP** hoặc **mTLS certificate-bound access token** khi cần ràng buộc người gửi với khóa/chứng chỉ; RS phải kiểm tra proof phù hợp.

JWT đã ký hay opaque token được introspection là hai cách triển khai token; **không cách nào tự giải quyết hoàn toàn rủi ro đánh cắp và phát lại**.

## 10. Phản hồi lỗi và khả năng vận hành

Khi thực thi policy ở RS, phân biệt lỗi xác minh với lỗi thiếu quyền:

| Trường hợp | Phản hồi thường dùng | Ghi chú |
|---|---|---|
| Thiếu token, token sai chữ ký, sai issuer, hết hạn hoặc sai audience | **401 Unauthorized** | Với bearer, có thể dùng `WWW-Authenticate` và `invalid_token` phù hợp. |
| Token hợp lệ nhưng thiếu scope cho action | **403 Forbidden** | Có thể dùng `insufficient_scope` và nêu scope cần thiết theo chính sách. |
| Token hợp lệ, scope đủ, nhưng không được xem order/tenant cụ thể | **403** hoặc **404** | 404 có thể giúp tránh lộ sự tồn tại của tài nguyên. |
| RS không xác minh được token vì nguồn introspection/JWKS lỗi | **Từ chối cấp quyền** | Có thể phản hồi lỗi tạm thời phù hợp; không tự cho qua vì dịch vụ xác minh lỗi. |

Ví dụ phản hồi thiếu scope theo RFC 6750:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:read"
~~~

Client có thể cần xin scope mới **qua luồng ủy quyền phù hợp**. Việc refresh token nhiều lần không tự khắc phục thiếu quyền. Tránh tự động yêu cầu scope quá rộng “để khỏi lỗi”; cần giải quyết đúng action và resource.

Khi log quyết định phân quyền, nên ghi **RS**, **action**, **mã lý do từ chối**, **principal đã xác minh** và thông tin tài nguyên ở mức cho phép, nhưng **không ghi nguyên token**. Nên phân biệt các chỉ số như “audience không khớp”, “thiếu scope” và “sai tenant” để phát hiện thiết kế sai hoặc hành vi bất thường.

## 11. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Có `scope=read` là đọc được mọi API.” | Scope có ngữ nghĩa theo hợp đồng và chỉ có giá trị trong phạm vi RS được cấp. | Kiểm tra audience trước, rồi kiểm tra scope của API hiện tại. |
| “`orders:read` tự chứng minh `aud=orders-api`.” | Chuỗi scope không phải cơ chế xác nhận audience. | AS/RS phải xác định audience riêng. |
| “Cùng AS ký thì mọi service dùng token như nhau.” | Bỏ qua đối tượng nhận và nguy cơ token substitution. | Mỗi RS kiểm tra `aud` của chính mình. |
| “Resource indicator luôn bằng chuỗi `aud`.” | Ánh xạ do AS/profile quy định, không mặc nhiên là cùng một chuỗi. | Tài liệu hóa URI resource và audience kỳ vọng. |
| “AS phải cấp đúng mọi scope client đề nghị.” | AS có thể từ chối hoặc cấp tập scope hẹp hơn. | Dùng quyền **thực sự được cấp**. |
| “Có quyền đọc API tức đọc được mọi bản ghi.” | Bỏ qua owner, tenant và quyền nghiệp vụ. | Object-level authorization tại RS. |
| “API Gateway đã kiểm tra scope thì service không cần xét order.” | Gateway thường không đủ ngữ cảnh tài nguyên. | Kiểm tra quyền trong service/dữ liệu. |
| “Forward token Orders sang Billing là bình thường.” | Token có thể sai audience và tạo confused deputy. | Xin token đúng đích hoặc token exchange theo chính sách. |
| “Nhiều audience luôn sai.” | Một số kiến trúc hỗ trợ có chủ đích. | Kiểm soát chặt issuer, audience, scope và mô hình rủi ro. |
| “JWT có `jti` hoặc `scope` hẹp là không thể phát lại.” | Không ngăn người có bearer token dùng lại ở đúng API. | Bảo vệ token, TTL, thu hồi và sender-constrained nếu cần. |

## 12. Tình huống tự luyện

**Tình huống A — Đúng scope nhưng sai API.** Client gửi token có `aud=orders-api` và `scope=orders:read` sang Billing API. Billing xác minh được chữ ký của AS. Có nên cho phép không?

**Giải thích:** Không. Billing không nằm trong audience. Cần token được AS cấp đúng cho Billing và scope phù hợp với hành động ở Billing.

**Tình huống B — Scope ngắn trùng tên.** Orders và Profile đều định nghĩa `read` với nghĩa khác nhau, hai API không kiểm tra audience. Vì sao nguy hiểm?

**Giải thích:** Token của một API có thể bị hiểu nhầm là quyền của API khác. Cần kiểm tra audience theo RS, đồng thời đặt tên và tài liệu hóa scope rõ ràng.

**Tình huống C — Client xin scope rộng.** Ứng dụng yêu cầu `orders:read orders:write`, nhưng AS chỉ cấp `orders:read`. Ứng dụng muốn sửa đơn nên làm gì?

**Giải thích:** Không tự coi `orders:write` đã được cấp. Client cần luồng yêu cầu quyền phù hợp; RS phải từ chối thao tác ghi khi thiếu scope, kể cả khi người dùng đã đăng nhập.

**Tình huống D — Token được cấp cho nhiều API.** AS chủ động phát hành token có `aud=["orders-api","reporting-api"]` và scope riêng của từng API. Orders API phải kiểm tra điều gì?

**Giải thích:** Orders phải xác minh nguồn phát hành, audience có chính nó, thời hạn/trạng thái và **chỉ scope có ý nghĩa với Orders**. Vẫn cần phân quyền theo đơn hàng/tenant. Chính sách nhiều audience phải được thiết kế từ trước, không tự suy quyền.

**Tình huống E — Scope đủ nhưng khác tenant.** Token hợp lệ cho Orders với `orders:read`; order 42 thuộc tenant B trong khi principal thuộc tenant A. Có trả dữ liệu không?

**Giải thích:** Không, trừ khi có cơ chế ủy quyền liên tenant được cấp riêng và kiểm tra rõ. Scope không thay kiểm tra đối tượng.

**Tình huống F — Downstream service.** Orders cần gọi Billing và chỉ có token đầu vào `aud=orders-api`. Có thể dùng nguyên token đó rồi tắt audience check tại Billing không?

**Giải thích:** Không. Phải dùng luồng được AS hỗ trợ để có token cho Billing (ví dụ service token hoặc token exchange), cùng quyền tối thiểu cho công việc cần thực hiện.

**Tình huống G — Đánh cắp token.** Attacker sao chép bearer token chỉ có `orders:read` và `aud=orders-api`. Token còn hạn. Họ có thể gọi Orders API không?

**Giải thích:** Có thể, trong phạm vi quyền token nếu không có ràng buộc người gửi hoặc cơ chế thu hồi. Audience/scope giúp giảm thiệt hại nhưng không tự ngăn phát lại token.

## Checklist thiết kế scope theo Resource Server

1. **Khai báo RS rõ ràng:** issuer tin cậy, resource indicator (nếu dùng), audience, khóa/introspection endpoint và loại token được chấp nhận.
2. **Định nghĩa scope theo API:** tên và ý nghĩa nhất quán, tách read/write/hành động nhạy cảm; không lạm dụng quyền toàn cục.
3. **Cấp quyền có kiểm soát:** AS kiểm tra client, principal, tài nguyên đích, scope yêu cầu và quyết định cấp thực tế.
4. **Kiểm tra audience trước scope:** RS xác minh token đúng nơi nhận và đúng mục đích; không suy audience từ tên scope.
5. **So khớp scope chính xác:** dùng tập scope đã chuẩn hóa từ dữ liệu xác minh, tránh tìm chuỗi con hoặc tự cấp mặc định.
6. **Phân quyền theo dữ liệu:** bảo vệ owner, tenant, trạng thái và action tại service; chặn BOLA/IDOR.
7. **Thiết kế lời gọi downstream:** không tự chuyển tiếp bearer token sai audience; dùng token riêng/trao đổi token theo chính sách.
8. **Giới hạn vòng đời:** TTL, refresh, thu hồi, rotation, cache trạng thái và độ tươi quyền phù hợp.
9. **Bảo vệ token:** TLS, lưu trữ an toàn, không ghi token vào log/URL; cân nhắc DPoP/mTLS nếu rủi ro replay cao.
10. **Kiểm thử từ chối:** sai issuer, sai audience, thiếu scope, scope trùng tên, sai tenant, token hết hạn/bị thu hồi, token dùng nhầm API và thao tác vượt quyền.

## Ghi nhớ

**Scope theo Resource Server** nghĩa là phạm vi ủy quyền phải được **phát hành và diễn giải trong đúng ngữ cảnh API đích**. Scope chỉ nói token được phép yêu cầu loại thao tác nào; **audience** giới hạn nơi token được nhận; **resource indicator** giúp client chỉ rõ đích khi AS hỗ trợ; **authorization** quyết định quyền trên từng bản ghi. Cần xác minh tất cả các lớp đó cùng trạng thái token và ranh giới tenant. Thiết kế scope/audience hẹp giảm thiệt hại khi access token bị lộ, nhưng muốn chống dùng lại bearer token còn cần bảo vệ token và các biện pháp vòng đời/ràng buộc người gửi thích hợp.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
