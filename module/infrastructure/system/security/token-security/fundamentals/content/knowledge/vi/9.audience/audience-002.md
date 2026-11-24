# Một token cho một resource hay nhiều resource?

## Mục tiêu học tập

Trong chương **Audience** của học phần bảo mật token, câu hỏi thiết kế thường gặp là: **nên cấp một access token chỉ dùng được tại một Resource Server, hay một access token có thể được nhiều Resource Server chấp nhận?**

Hai mô hình đều có thể tồn tại trong OAuth 2.0. Quyết định đúng phụ thuộc ranh giới tin cậy, chức năng của từng API, quyền được cấp và hậu quả khi token bị lộ. Sau bài học, bạn có thể:

1. Phân biệt **Resource Server (RS)** với **bản ghi/tài nguyên nghiệp vụ** và giải thích claim `aud` trong access token.
2. Hiểu ưu điểm, giới hạn và điều kiện dùng **access token một audience** so với **access token nhiều audience**.
3. Mô tả vai trò của `resource` theo **OAuth 2.0 Resource Indicators (RFC 8707)** và phân biệt nó với `aud`, `scope`, `iss`.
4. Thiết kế lời gọi giữa microservices bằng token phù hợp, bao gồm **client credentials**, **token exchange** hoặc ủy quyền thay mặt người dùng khi hệ thống hỗ trợ.
5. Kiểm tra issuer, audience, thời hạn, loại token, scope và quyền trên từng đối tượng; giảm rủi ro token substitution, lộ token và replay.

## 1. “Resource” trong câu hỏi là gì?

Trong OAuth 2.0, **Resource Server** là dịch vụ chứa tài nguyên được bảo vệ và nhận access token, ví dụ:

- **Orders API:** `https://api.example.test/orders`.
- **Billing API:** `https://api.example.test/billing`.
- **Reports API:** `https://reports.example.test`.

Mỗi API có thể phục vụ hàng nghìn bản ghi như `order-42` hay `invoice-99`. **Một token cho một Resource Server** không có nghĩa cấp một token riêng cho từng đơn hàng; token có thể cho phép yêu cầu truy cập nhiều đơn hàng **nằm trong cùng API**, nhưng API vẫn phải kiểm tra quyền trên từng đơn.

Trong ngữ cảnh bài này, “một resource” chủ yếu chỉ **một Resource Server hoặc một nhóm endpoint được cấu hình thành một tài nguyên đích trong hệ thống cấp token**. Việc một dịch vụ được chia thành nhiều URL, deployment hoặc microservice không tự quyết định nó có một hay nhiều audience: đó là **ranh giới bảo mật do kiến trúc định nghĩa**.

### Năm khái niệm không nên trộn lẫn

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **`iss` – issuer** | Ai được tin là bên phát hành token? | `https://auth.example.test`. |
| **`aud` – audience** | Bên nhận nào được phép xử lý token? | `orders-api`. |
| **`resource` – resource indicator** | Client muốn xin token để truy cập tài nguyên đích nào, nếu AS hỗ trợ RFC 8707? | `https://api.example.test/orders`. |
| **`scope` – phạm vi ủy quyền** | Token được phép yêu cầu loại thao tác nào? | `orders:read`. |
| **Authorization theo tài nguyên** | Principal có được thao tác trên bản ghi cụ thể không? | User A có được đọc `order-42` thuộc tenant B không? |

**Audience không phải scope.** Một token có `orders:read` nhưng `aud=billing-api` không được Orders API chấp nhận chỉ vì tên scope có chữ `orders`. Tương tự, token đúng audience và scope cũng không tự cấp quyền đọc đơn hàng thuộc người khác.

## 2. Hai mô hình phát hành access token

### Phương án A – Một token cho một Resource Server

Authorization Server (AS) phát hành token có **audience giới hạn vào RS đích**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Payload này chỉ là **minh họa**, không phải token dùng thật. `orders-api` được phép xem xét token sau khi xác minh đầy đủ; `billing-api` phải từ chối do sai audience. Nếu client muốn truy cập Billing, nó cần token **được AS cấp cho Billing** theo cơ chế ủy quyền tương ứng.

### Phương án B – Một token cho nhiều Resource Server

AS có thể phát hành một token với **nhiều audience**, nếu **cố ý hỗ trợ** mô hình ấy và các RS đã thống nhất quy tắc sử dụng:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api", "reports-api"],
  "scope": "orders:read reports:read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Orders API và Reports API **có thể** cùng nhận token trong ví dụ, nhưng mỗi bên phải:

1. Xác minh token đến từ issuer tin cậy và bản thân API nằm trong `aud`.
2. Hiểu chính xác scope nào dành cho API mình; `reports:read` không tự tạo quyền `orders:read`.
3. Thực thi kiểm tra quyền trên dữ liệu, tenant và thao tác của API đó.
4. Tuân thủ cùng một hợp đồng bảo mật về loại token, thuật toán, vòng đời, trạng thái thu hồi và các điều kiện bổ sung.

Token nhiều audience **không mặc nhiên là sai**, nhưng việc chọn mô hình này phải là quyết định cấp quyền có chủ đích của AS và các RS, không phải một API tự bỏ kiểm tra `aud` để dùng lại token của API khác.

### So sánh

| Tiêu chí | Token một RS | Token nhiều RS |
|---|---|---|
| **Phạm vi sử dụng** | Chỉ RS được chỉ định (hoặc nhóm RS được định nghĩa như một audience). | Các RS nằm trong danh sách audience đã cấp. |
| **Khi bị lộ** | Thường giới hạn được số dịch vụ có thể bị gọi. | Một bản sao token có thể được dùng ở nhiều dịch vụ hơn. |
| **Thiết kế scope** | Dễ gắn scope với API đích. | Cần quy tắc rõ scope nào áp dụng cho API nào. |
| **Vòng đời và thu hồi** | Có thể điều chỉnh TTL/chính sách riêng theo RS. | Các RS phải phối hợp việc xác minh, trạng thái và thu hồi. |
| **Tác vụ gọi nhiều API** | Có thể cần thêm lần cấp token hoặc token exchange. | Client có thể trình cùng token cho các RS được cấp phép. |
| **Rủi ro token confusion** | Dễ khoanh vùng hơn nếu mọi RS kiểm tra audience. | Tăng yêu cầu phân tách ngữ nghĩa và chính sách của từng RS. |
| **Ứng dụng phù hợp** | API có dữ liệu nhạy cảm, quyền khác biệt, ranh giới trust rõ. | Nhóm API có quan hệ tin cậy chặt, nhu cầu chung đã được đánh giá. |

**Nguyên tắc khởi đầu hữu ích:** ưu tiên token giới hạn đúng API cần gọi khi không có lý do rõ ràng để mở rộng audience. Nếu mô hình nhiều RS giải quyết được nhu cầu thực sự, hãy mô tả bằng chính sách cụ thể và đánh giá mức thiệt hại khi token bị sao chép.

## 3. Audience trong JWT và opaque access token

### JWT: claim `aud` được diễn giải như thế nào?

Theo JWT (RFC 7519), `aud` có thể là **chuỗi** hoặc **mảng chuỗi**. Resource Server phải kiểm tra định danh của mình **khớp một audience được chấp nhận**, theo đúng profile và chính sách.

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

Kiểm tra sai:

~~~text
if token.aud.toString().contains("orders"):
    allow()
~~~

Chuỗi `malicious-orders-api` hoặc `another-orders-api` có thể vượt một phép so khớp mơ hồ. Việc chuyển mảng thành chuỗi cũng có thể gây lỗi. Hệ thống cần **so sánh chính xác** với một hoặc nhiều giá trị audience đã cấu hình trước.

Một API cũng cần xem profile cho phép nhận `aud` dưới dạng nào và liệu danh sách audience đó có phù hợp chính sách của nó hay không. **Có tên API trong mảng audience chưa đủ cho phép** nếu token sai issuer, hết hạn, sai loại, thiếu scope hoặc bản ghi không thuộc quyền của principal.

### Opaque token: audience không nhất thiết nhìn thấy được

Với **opaque access token**, client chỉ nhìn thấy một chuỗi không có ý nghĩa để tự giải mã. RS có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** hoặc tra cứu nội bộ tin cậy:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456900
}
~~~

Đây là phản hồi **minh họa**. RS phải xác thực kết nối đến introspection endpoint, kiểm tra kết quả thuộc token vừa nhận và sử dụng metadata theo hợp đồng. **`active: true` chỉ là một điều kiện**, không có nghĩa token được cấp cho mọi RS. Nếu API cần audience nhưng phản hồi thiếu thông tin không thể xác minh, **không tự mặc định cho phép**.

Việc cache introspection có thể giảm độ trễ nhưng tạo khoảng trễ thu hồi. Khi cùng token được nhiều RS chấp nhận, cần tính đến sự không đồng bộ giữa chính sách và cache của các RS.

### ID token không nằm trong lựa chọn này

**OIDC ID token** cũng có `aud`, thường hướng tới **client ID** đã yêu cầu xác thực người dùng. Nó dùng để client đánh giá kết quả xác thực theo OIDC, **không phải access token để trình cho Resource Server**. Không được suy rằng ID token có chữ ký của cùng issuer là token nhiều audience dành cho mọi API.

**Refresh token** cũng không phải access token đa RS: refresh token được sử dụng tại **token endpoint của AS** để xin access token mới, chứ không gửi trực tiếp đến API nghiệp vụ.

## 4. Yêu cầu token cho một hoặc nhiều tài nguyên với RFC 8707

OAuth 2.0 **Resource Indicators (RFC 8707)** định nghĩa tham số `resource` để client chỉ rõ tài nguyên đích mà nó muốn truy cập. Khi AS hỗ trợ, client có thể gửi tham số này trong yêu cầu ủy quyền và/hoặc yêu cầu token, tùy luồng.

Ví dụ client muốn token cho Orders API:

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<STATE>&code_challenge=<CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Request trên **lược bớt** nhiều chi tiết để tập trung vào `scope` và `resource`; ứng dụng thực tế phải áp dụng Authorization Code + PKCE, quản lý `state` và kiểm tra redirect URI theo quy tắc giao thức.

AS có thể dùng thông tin:

~~~text
Requested resource: https://api.example.test/orders
Requested scope:    orders:read

Issued access token (illustration):
  aud   = orders-api
  scope = orders:read
~~~

**Quan hệ `resource` → `aud` không nhất thiết là đẳng thức chuỗi.** Ở đây AS ánh xạ URI tài nguyên thành audience ID `orders-api`; hệ thống khác có thể dùng chính URI làm audience. AS và RS phải thống nhất giá trị mong đợi, thay vì để client tự đặt `aud` bên trong token.

### Yêu cầu nhiều `resource`

RFC 8707 cho phép client chỉ định **nhiều tài nguyên đích** bằng cách lặp lại tham số `resource`, trong giới hạn hỗ trợ và chính sách của AS. Ví dụ phần form gửi tới AS:

~~~text
scope=orders%3Aread%20reports%3Aread
resource=https%3A%2F%2Fapi.example.test%2Forders
resource=https%3A%2F%2Freports.example.test
~~~

Điều đó **không bắt buộc AS phải cấp một token dùng được ở cả hai RS**. AS phải đánh giá quyền, độ nhạy cảm và hợp đồng. Tùy khả năng và chính sách, AS có thể cấp token phù hợp với các tài nguyên được cho phép hoặc từ chối yêu cầu không phù hợp. Nếu cần mỗi RS có token riêng, client phải theo luồng xin/cấp token tương ứng. Không suy luận “đã gửi hai `resource` nên chắc chắn nhận được token hai audience”.

AS cũng cần kiểm tra resource mà client chỉ định có được phép, phù hợp client và scope hay không, tránh để người gọi tùy ý xin token dành cho dịch vụ không nằm trong chính sách cấp quyền.

### Nhiều resource nhưng chỉ có một nhóm quyền?

Nếu Orders API và Reports API đều nhận `read` nhưng mỗi bên diễn giải theo nghĩa khác nhau, AS cần một hợp đồng không mơ hồ. Một lựa chọn là namespace scope theo dịch vụ:

~~~text
orders:read
reports:read
~~~

Tuy vậy, đặt prefix rõ **không thay kiểm tra audience**. Một token có `orders:read` không được Orders API nhận khi `aud` của token chỉ là `reports-api`.

## 5. Luồng kiến trúc: một client gọi hai Resource Server

Giả sử ứng dụng hiển thị cả lịch sử đơn hàng lẫn báo cáo doanh số:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Shop Client
    participant AS as Authorization Server
    participant Orders as Orders API
    participant Reports as Reports API
    U->>C: Xem đơn và báo cáo
    C->>AS: Xin token cho orders-api, scope orders:read
    AS-->>C: Token O (aud=orders-api)
    C->>Orders: GET /orders + Token O
    Orders->>Orders: Xác minh O + policy dữ liệu
    Orders-->>C: Đơn hàng được phép
    C->>AS: Xin token cho reports-api, scope reports:read
    AS-->>C: Token R (aud=reports-api)
    C->>Reports: GET /reports + Token R
    Reports->>Reports: Xác minh R + policy dữ liệu
    Reports-->>C: Báo cáo được phép
~~~

Đây là **một phương án kiến trúc minh họa**. Client phải có luồng cấp/đổi token thực sự được AS hỗ trợ và không tự ý biến một refresh token thành quyền cấp token tùy ý. Với ứng dụng web, một **Backend for Frontend (BFF)** có thể giữ token phía máy chủ và điều phối lời gọi, giảm việc lộ bearer access token cho JavaScript trong trình duyệt.

Nếu AS cấp **một token nhiều audience** cho cả hai API, sơ đồ có thể dùng chung token, nhưng Orders và Reports **đều phải xác minh** nó dành cho mình, chỉ chấp nhận scope phù hợp và không vượt quyền trên dữ liệu. Không có bảo đảm rằng một token đa RS an toàn chỉ vì nó giảm số lần client xin token.

### Hệ quả vận hành cần cân nhắc

- **Thời hạn:** Orders có thể chấp nhận TTL khác Reports; một token chung phải đáp ứng chính sách của tất cả nơi nhận.
- **Thu hồi:** khi người dùng mất quyền Reports nhưng vẫn được xem Orders, hệ thống cần biết thu hồi token chung có cắt cả hai quyền hay có cơ chế cập nhật chính sách kịp thời.
- **Giám sát:** logs của mỗi RS cần cho biết audience, thao tác và quyết định theo cách không lộ token. Đừng ghi nguyên chuỗi bearer token.
- **Tính sẵn sàng:** xin nhiều token tăng tương tác với AS, nhưng không có nghĩa mỗi API call đều phải xin mới nếu có cache token phù hợp và còn hiệu lực.
- **Phân tách dữ liệu:** API chứa dữ liệu nhạy cảm cần cân nhắc token riêng với quyền hẹp và thời hạn khác biệt.

## 6. Khi microservice gọi microservice: đừng chuyển tiếp token tùy tiện

Một vấn đề rất thực tế: **Orders API cần gọi Billing API** để kiểm tra tình trạng thanh toán. Client chỉ gửi token có `aud=orders-api`. Orders có nên chuyển nguyên token ấy cho Billing không?

**Không, trừ khi token thật sự được cấp cho Billing và các bên có hợp đồng cho phép việc đó.** Trong trường hợp `aud=orders-api`, Billing phải từ chối token, ngay cả khi cả hai API cùng tin một AS.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Orders as Orders API
    participant AS as Authorization Server
    participant Billing as Billing API
    Client->>Orders: Token O (aud=orders-api)
    Orders->>Orders: Xác minh token O và quyền đọc đơn
    Orders->>AS: Xin token mới cho billing-api theo chính sách
    Note over Orders,AS: client credentials hoặc token exchange nếu được hỗ trợ
    AS-->>Orders: Token B (aud=billing-api, scope phù hợp)
    Orders->>Billing: Gọi với token B
    Billing->>Billing: Xác minh token B và quyền nghiệp vụ
    Billing-->>Orders: Kết quả được phép
~~~

### Các lựa chọn theo ngữ cảnh

| Cách làm | Khi nào phù hợp | Điều không được nhầm |
|---|---|---|
| **Client credentials** | Orders gọi Billing với quyền của **dịch vụ Orders**. | Token service không tự đại diện cho người dùng đã gọi Orders. |
| **Token exchange (RFC 8693)** | AS cho phép đổi token đầu vào lấy token mới có audience/scope phù hợp cho Billing. | Quyền của token đầu ra do AS quyết định; Orders không tự sửa claim `aud` hoặc `scope`. |
| **Ủy quyền thay mặt người dùng** | Nghiệp vụ cần giữ ngữ cảnh người dùng và AS hỗ trợ luồng delegation phù hợp. | Phải phân biệt chủ thể, client và actor; kiểm tra cả quyền người dùng lẫn quyền dịch vụ theo chính sách. |
| **Token nhiều audience được cấp từ đầu** | AS và cả hai RS chủ động chấp nhận mô hình dùng chung. | Không bỏ qua audience; cần phạm vi quyền và ranh giới trust rõ ràng. |

Sai lầm phổ biến là tắt kiểm tra `aud` ở Billing vì “cùng hệ thống nội bộ”. Điều đó tạo nguy cơ **token substitution** và có thể góp phần vào lỗi **confused deputy**: dịch vụ có quyền rộng hành động thay người gọi mà không xét đúng ai được ủy quyền làm gì.

### Resource Server có phải là client ở lời gọi downstream?

Có thể. Khi Orders API gọi Billing API, **Orders trở thành client của Billing** ở tương tác đó, dù nó vẫn là Resource Server đối với client bên ngoài. Vai trò OAuth được xác định **theo từng quan hệ giao tiếp**, không phải nhãn cố định cho cả ứng dụng.

## 7. Nhiều audience nhưng authorization vẫn độc lập

Giả sử AS đã phát hành access token có:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api", "reports-api"],
  "scope": "orders:read reports:read",
  "tenant_id": "tenant-a",
  "exp": 1893456900
}
~~~

Orders API nhận yêu cầu:

~~~http
GET /orders/order-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_PLACEHOLDER>
~~~

Nhưng bản ghi:

~~~json
{
  "id": "order-42",
  "tenantId": "tenant-b",
  "ownerId": "user-999",
  "status": "PAID"
}
~~~

Token có thể vượt qua kiểm tra issuer, chữ ký, audience, thời gian và scope, **nhưng vẫn không được đọc order-42** nếu user-123 không có quyền liên tenant được cấp riêng.

Với Reports API, `reports:read` cũng không đồng nghĩa người dùng được xem mọi báo cáo. Reports cần xét chủ sở hữu dữ liệu, phạm vi nhóm, tenant, cấu hình chia sẻ và điều kiện nghiệp vụ riêng.

### Tại sao “quyền đủ trên một API” không chuyển sang API khác?

Mỗi RS có **tài nguyên và policy** khác nhau. Sở hữu đơn hàng là một quan hệ; truy cập báo cáo tổng hợp của toàn công ty là quan hệ khác. Ngay cả khi hai RS dùng chung subject `user-123`, chúng vẫn phải kiểm tra authorization tại **điểm thực hiện**.

Một access token nhiều audience **không thay thế** RBAC, ABAC, ReBAC hoặc cơ chế quyền trên từng đối tượng. Một token có quyền chỉ là một **đầu vào** để RS quyết định.

## 8. Resource Server phải xác minh token theo chính sách của chính mình

### Đường kiểm tra khái quát

~~~mermaid
flowchart TD
    A["Nhận access token ở Resource Server X"] --> B{"Đúng dạng token, kênh truyền và profile?"}
    B -- Không --> R1["401 / Từ chối"]
    B -- Có --> C{"Xác minh từ issuer đáng tin?"}
    C -- Không --> R1
    C -- Có --> D{"X có thuộc audience được chấp nhận?"}
    D -- Không --> R1
    D -- Có --> E{"Token còn hiệu lực, trạng thái phù hợp?"}
    E -- Không --> R1
    E -- Có --> F{"Scope cần cho hành động của X có mặt?"}
    F -- Không --> R2["403 / Từ chối"]
    F -- Có --> G{"Principal có quyền trên tài nguyên cụ thể?"}
    G -- Không --> R2
    G -- Có --> OK["Cho phép trong phạm vi được cấp"]
~~~

Khi dùng **sender-constrained token** như DPoP/mTLS, RS phải kiểm tra thêm proof sở hữu khóa/chứng chỉ ở bước xác minh; chỉ kiểm tra nội dung JWT không đủ.

### Mã giả cho Orders API

~~~text
handle(GET /orders/{orderId}, request):
    rawToken = getBearerOrConfiguredProofToken(request)
    if missing or malformed:
        return 401

    rsPolicy = trustedPolicyFor("orders-api")
    principalAndGrants = verifyAccessToken(rawToken, rsPolicy)
        # JWT: trusted issuer/key, allowed algorithm, signature,
        #      token type, exp/nbf, audience, optional revocation state
        # opaque: trusted introspection/lookup, active, claims/metadata
    if invalid or not intendedFor("orders-api"):
        return 401

    if rsPolicy.senderProofRequired and not verifySenderProof(request, rawToken):
        return 401
    if "orders:read" not in principalAndGrants.grantedScopes:
        return 403

    order = repository.findById(orderId)
    if not found:
        return 404
    if not canRead(principalAndGrants.principal, order, currentPolicy):
        return 403  # hoặc 404 nếu cần che giấu sự tồn tại
    return 200 with allowed order data
~~~

Đây là mã giả về logic, **không phải code triển khai xác minh mật mã**. Cần dùng thư viện và cấu hình issuer/JWKS hoặc introspection đáng tin cậy. Không bao giờ quyết định quyền bằng cách chỉ `decode` JWT rồi đọc `aud`/`scope` trong payload chưa được xác minh.

### Ví dụ Java: kiểm tra audience chính xác trên claims đã xác minh

~~~java
import java.util.Set;

record VerifiedAccessToken(
    String issuer,
    Set<String> audiences,
    Set<String> scopes,
    boolean active
) {}

final class OrdersTokenPolicy {
    private static final String EXPECTED_ISSUER = "https://auth.example.test";
    private static final String EXPECTED_AUDIENCE = "orders-api";

    static boolean validForOrdersRead(VerifiedAccessToken token) {
        return token != null
                && token.active()
                && EXPECTED_ISSUER.equals(token.issuer())
                && token.audiences() != null
                && token.audiences().contains(EXPECTED_AUDIENCE)
                && token.scopes() != null
                && token.scopes().contains("orders:read");
    }
}
~~~

**Giới hạn của ví dụ:** `VerifiedAccessToken` phải được tạo **chỉ sau khi** lớp bảo mật hoàn tất xác minh chữ ký hoặc introspection, thời hạn, loại token, trạng thái, audience và proof nếu cần. `Set.contains` ở đây là so khớp giá trị **chính xác**, không phải tìm chuỗi con. Method trên không thay thế kiểm tra ownership, tenant, trạng thái đơn hoặc chính sách thu hồi.

### Lỗi HTTP và phản ứng của client

| Tình huống | Phản hồi thường dùng | Lưu ý |
|---|---|---|
| Thiếu token; token sai chữ ký, hết hạn, sai issuer/audience | **401 Unauthorized** | Có thể dùng `WWW-Authenticate: Bearer` với lỗi `invalid_token` phù hợp. |
| Token đúng RS nhưng thiếu scope cho hành động | **403 Forbidden** | Có thể dùng `insufficient_scope` và thông tin scope cần thiết theo chính sách. |
| Scope đủ nhưng tài nguyên thuộc tenant khác | **403** hoặc **404** | 404 có thể che giấu sự tồn tại của tài nguyên. |
| Không kiểm tra được introspection hoặc JWKS | **Không cấp quyền** | Xử lý lỗi tạm thời theo kiến trúc, không mặc định chấp nhận token. |

Không đưa nguyên access token vào log hay thông báo lỗi. Client không nên tự refresh lặp vô hạn khi gặp `403`; thiếu scope hoặc quyền trên tài nguyên thường cần một quyết định ủy quyền khác.

## 9. An toàn khi một token đi qua nhiều hệ thống

### 9.1. Hạn chế phạm vi khi token bị đánh cắp

Với **bearer access token**, bên nào sở hữu chuỗi token hợp lệ có thể trình token và được phục vụ trong giới hạn token, trừ khi có cơ chế ràng buộc người gửi. Khi một token dùng được tại ba RS, bản sao bị lộ **có thể** mang quyền đến cả ba. Token cấp cho một RS làm giảm phạm vi đó nếu mọi RS kiểm tra audience đúng.

~~~text
Token O:  aud=orders-api
          scope=orders:read

Attacker lấy được Token O:
  gọi Orders API  -> có thể thành công trong phạm vi quyền, khi token còn hiệu lực
  gọi Billing API -> phải bị từ chối vì sai audience
~~~

**Chữ ký JWT, mã hóa JWE và tên scope hẹp không tự ngăn replay.** Kẻ tấn công có thể trình bản sao token còn hạn mà không cần sửa hay giải mã. Để giảm rủi ro:

- Dùng HTTPS/TLS; không đặt token trong URL/query, log, trace, analytics hoặc ticket hỗ trợ.
- Hạn chế scope, audience và TTL theo nhu cầu của client.
- Bảo vệ token trong trình duyệt, mobile và backend; bảo vệ refresh token và cơ chế xoay/thu hồi.
- Xây dựng khả năng thu hồi token, kiểm tra trạng thái phiên và kế hoạch phản ứng sự cố.
- Khi cần, dùng **DPoP** hoặc **mTLS certificate-bound access token** và xác minh proof ở RS để việc sao chép riêng token thường không đủ sử dụng.

### 9.2. Lộ token ở một Resource Server

Nếu một RS ghi bearer token vào log hoặc công cụ giám sát, token dùng chung nhiều RS có thể gây hệ quả lan rộng hơn. Ngay cả RS nhận đúng audience cũng phải **giữ kín token**. Nếu các API có mức độ bảo vệ log, nhân sự vận hành hoặc dữ liệu khác nhau, việc chia sẻ chung token cần được đánh giá kỹ.

### 9.3. Thay đổi quyền, hết hạn và thu hồi

Token ký có `exp` ở tương lai vẫn có thể được các RS chấp nhận cho đến khi hết hạn nếu chỉ kiểm tra cục bộ chữ ký/claims. Việc người dùng đổi mật khẩu, đăng xuất, mất quyền hoặc bị khóa không tự bảo đảm access token cũ hết hiệu lực ngay. Nếu các RS xử lý cache/trạng thái khác nhau, chúng có thể **không đồng bộ thời điểm từ chối token**.

Vì vậy mô hình nhiều RS cần thỏa thuận:

1. Ai chịu trách nhiệm **nguồn trạng thái** token, phiên và quyền?
2. TTL và độ lệch đồng hồ được phép là bao nhiêu?
3. RS có introspection, denylist, kiểm tra session version hay chính sách thu hồi nào?
4. Khi xóa một quyền ở Reports, token chung phải bị thu hồi toàn bộ hay có chính sách đánh giá quyền hiện hành riêng tại RS?
5. Hệ thống xử lý thế nào khi dịch vụ xác minh bị lỗi hoặc không trả đủ dữ liệu?

## 10. Chọn kiến trúc theo ranh giới tin cậy

### Tình huống A – Hai API có dữ liệu khác nhau

Ứng dụng cần đọc đơn hàng và thực hiện hoàn tiền. Hoàn tiền thường có mức rủi ro cao hơn việc đọc đơn. Một lựa chọn hợp lý là **token riêng theo API**, `orders:read` chỉ dùng tại Orders, `payments:refund` chỉ dùng tại Billing, với điều kiện bổ sung cho hoàn tiền. Điều này giảm việc quyền nhạy cảm bị mang theo đến các thành phần không cần nó.

### Tình huống B – Một nhóm endpoint thực chất là một Resource Server logic

Một nền tảng chia Orders thành nhiều dịch vụ triển khai nội bộ nhưng quản lý chúng như **một tài nguyên bảo vệ logic** với cùng chính sách issuer/audience. Có thể dùng audience chung cho nhóm này **nếu đó là ranh giới bảo mật được thiết kế rõ**, và mỗi điểm tiếp nhận vẫn thực thi quyền liên quan. Số lượng deployment không đồng nhất với số lượng audience.

### Tình huống C – Giao diện tổng hợp gọi nhiều API

Client có thể nhận token riêng cho Orders/Reports hoặc dùng token nhiều audience nếu AS thực sự hỗ trợ và rủi ro được đánh giá. Khi client ở trình duyệt, cân nhắc BFF để quản lý token trên backend. Việc giảm số lần cấp token cần được cân bằng với diện tấn công mở rộng.

### Tình huống D – Backend A gọi Backend B

Ưu tiên **token đích phù hợp** từ AS theo giao dịch đã được hỗ trợ: service token, token exchange hoặc delegated token. Nếu token đầu vào chỉ có `aud=A`, B phải từ chối. Không tự sửa payload JWT, không tắt audience validation ở B.

### Tình huống E – Nhiều tổ chức hoặc tenant

Một hệ thống có hai tenant dùng chung AS vẫn cần **isolation theo tenant** tại từng API. `aud` cho biết token dành cho RS, **không cho biết mọi bản ghi trong RS đều có thể truy cập**. Đối chiếu tenant trong principal đã xác minh với tenant thực của đối tượng và các quyền được ủy nhiệm; đừng tin tenant ID do caller tự truyền trong query.

## 11. Ma trận kiểm thử audience và quyền

Giả sử Orders API yêu cầu `aud=orders-api` và scope `orders:read`. Đơn `order-42` thuộc `tenant-a`, do `user-123` sở hữu; mọi token dưới đây đều phải qua bước xác minh nguồn phát hành và thời hạn:

| Token/Request | Kỳ vọng | Lý do |
|---|---|---|
| `aud=orders-api`, `scope=orders:read`; user-123 đọc order-42 | **Cho phép** nếu toàn bộ policy khác đáp ứng. | Đúng nơi nhận, scope và quyền trên đơn. |
| `aud=billing-api`, `scope=orders:read`; user-123 đọc order-42 | **Từ chối**. | Scope không bù được audience sai. |
| `aud=["orders-api","reports-api"]`, `scope=orders:read`; user-123 đọc order-42 | **Có thể cho phép**, nếu RS hỗ trợ token nhiều audience. | Phải kiểm tra issuer/type/TTL và quyền tài nguyên. |
| `aud=["billing-api","reports-api"]`, `scope=orders:read`; user-123 đọc order-42 | **Từ chối**. | Audience không chứa Orders. |
| `aud=orders-api`, `scope=reports:read`; user-123 đọc order-42 | **Từ chối**. | Thiếu scope dành cho action của Orders. |
| `aud=orders-api`, `scope=orders:read`; user-999 tenant B đọc order-42 | **Từ chối**. | Không có ownership/ủy quyền liên tenant phù hợp. |
| `aud=orders-api` nhưng token hết hạn | **Từ chối**. | Audience đúng không thay thời hạn. |
| OIDC ID token có `aud=shop-web` và `sub=user-123` dùng gọi Orders | **Từ chối**. | Sai loại/mục đích token và không có audience API. |
| Opaque token introspection `active=true` nhưng không thể xác minh audience bắt buộc | **Từ chối**. | Thiếu căn cứ xác thực token dành cho Orders. |
| Bearer token đúng audience bị sao chép, chưa bị thu hồi | **Có thể bị lạm dụng** trong phạm vi quyền. | Audience không tự ngăn replay. |

Tập kiểm thử cần bao gồm **audience dạng chuỗi/mảng**, sai chính tả, tên chứa chuỗi con, issuer lạ, scope nhầm API, trạng thái thu hồi và các đường gọi service nội bộ. Đừng chỉ thử tình huống token hợp lệ với người dùng sở hữu bản ghi; các tình huống sai audience và sai tenant thường phát hiện lỗi bảo mật quan trọng.

## 12. Câu hỏi luyện tập

**Câu 1.** Một JWT có chữ ký đúng, `aud=orders-api` và `scope=orders:read`. Billing API cũng tin issuer này và có cùng khóa công khai. Billing có được chấp nhận token không?

**Giải thích:** Không. Billing không phải audience được cấp. Chữ ký chỉ hỗ trợ xác minh nguồn phát hành/toàn vẹn; quyền sử dụng tại API nào còn phụ thuộc audience.

**Câu 2.** AS phát hành token có `aud=["orders-api","reports-api"]`, nhưng chỉ có scope `orders:read`. Reports API có được cho phép `GET /reports` không?

**Giải thích:** Không, nếu Reports API yêu cầu `reports:read`. Việc nằm trong audience không tự cấp mọi scope. API còn phải kiểm tra policy dữ liệu.

**Câu 3.** Client gửi hai tham số `resource` trong yêu cầu OAuth 2.0 theo RFC 8707. Có chắc nó sẽ nhận một token được cả hai RS chấp nhận?

**Giải thích:** Không. AS phải hỗ trợ yêu cầu, đánh giá chính sách và quyết định cấp token. Client cần kiểm tra kết quả được cấp, không suy quyền từ tham số mình đã gửi.

**Câu 4.** Orders API nhận token `aud=orders-api` rồi muốn gọi Billing. Có thể tự thay claim `aud` sang `billing-api` và ký lại bằng khóa riêng của Orders không?

**Giải thích:** Không. Orders không tự trở thành AS đáng tin của Billing. Phải dùng luồng cấp/đổi token do AS cho phép, đồng thời giới hạn scope theo quyền thực.

**Câu 5.** Token một audience có bảo vệ hoàn toàn trước đánh cắp không?

**Giải thích:** Không. Token bị sao chép vẫn có thể được trình lại ở **đúng** RS cho đến khi hết hạn hoặc bị thu hồi, nếu là bearer token. Audience hẹp chỉ giảm phạm vi ảnh hưởng.

**Câu 6.** Một token đúng audience và scope `orders:read` nhưng chủ thể thuộc tenant A; request đọc đơn của tenant B. Có được trả dữ liệu không?

**Giải thích:** Không, trừ khi có ủy quyền liên tenant rõ ràng đã được kiểm tra. Cần kiểm tra quyền trên bản ghi, không chỉ token.

## Checklist ra quyết định

1. **Xác định RS logic:** API nào thực sự chia sẻ cùng chính sách tin cậy? Đừng chỉ dựa vào tên host, số deployment hay tên microservice.
2. **Xác định audience:** một token chỉ một RS hay nhiều RS có chủ đích; mỗi RS có expected audience nào?
3. **Xác định phạm vi quyền:** scope nào áp dụng cho từng RS/action; tránh scope chung mơ hồ và cấp quyền quá rộng.
4. **Xác định cách yêu cầu token:** `resource` theo RFC 8707 nếu AS hỗ trợ; mô tả rõ cách AS ánh xạ tới audience.
5. **Kiểm tra đúng loại và nguồn:** JWT signature/issuer hoặc opaque introspection, hạn dùng, trạng thái, audience, token purpose và proof nếu cần.
6. **Phân quyền theo dữ liệu:** ownership, tenant, role, permission và trạng thái nghiệp vụ tại Resource Server.
7. **Thiết kế downstream:** token riêng, client credentials hay token exchange; không forward token sai audience.
8. **Giới hạn tác động khi lộ token:** TTL, scope/audience hẹp, HTTPS, lưu trữ an toàn, không log token, thu hồi và sender-constrained token nếu cần.
9. **Quản lý thay đổi:** versioning/chính sách audience và scope, cập nhật cấu hình RS, cache trạng thái và cơ chế thu hồi.
10. **Kiểm thử phủ định:** token của RS khác, audience gần giống, nhiều audience, thiếu scope, sai tenant, token sai loại và replay.

## Ghi nhớ

**Một access token có thể dành cho một hoặc nhiều Resource Server nếu Authorization Server thực sự cấp quyền đó và từng Resource Server kiểm tra đúng ranh giới tin cậy.** Token một audience thường giúp giới hạn nơi token bị lộ có thể được dùng; token nhiều audience có thể đáp ứng nhu cầu chia sẻ đã được thiết kế nhưng làm tăng yêu cầu phối hợp và phạm vi ảnh hưởng khi rò rỉ. **`resource`** chỉ tài nguyên đích khi xin token theo RFC 8707; **`aud`** chỉ bên nhận được phép; **`scope`** giới hạn thao tác; **authorization** quyết định quyền trên từng đối tượng. Không có lựa chọn audience nào thay thế xác minh issuer, thời hạn, thu hồi, phân quyền theo tenant hay biện pháp chống bearer token bị phát lại.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
