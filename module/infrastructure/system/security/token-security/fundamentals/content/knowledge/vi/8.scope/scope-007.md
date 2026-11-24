# Scope thay đổi theo client

Một ứng dụng bán hàng, cổng quản trị và dịch vụ xử lý đơn hàng có thể cùng gọi `orders-api`, nhưng **không nên được cấp cùng tập quyền**. Ứng dụng của khách hàng cần đọc đơn hàng của chính người dùng; dịch vụ báo cáo chỉ cần đọc dữ liệu đã được phép; hệ thống quản trị có thể yêu cầu quyền hoàn tiền với quy trình kiểm soát chặt chẽ hơn. Trong OAuth 2.0, **scope** là một cách để authorization server biểu diễn phạm vi quyền mà access token được cấp. Phạm vi này có thể **khác nhau theo client**.

Trong chương **Scope** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học giải thích tại sao một scope được yêu cầu không nhất thiết được cấp, vì sao các client khác nhau nhận các tập scope khác nhau, và resource server phải sử dụng scope như thế nào khi xác thực và phân quyền bằng JWT hoặc opaque access token. Các tình huống OAuth 2.0/OpenID Connect (OIDC), access token, refresh token, audience, lưu trữ, thu hồi và nguy cơ đánh cắp/phát lại cũng được đặt trong cùng mô hình tin cậy.

**Ý chính:** client có thể **yêu cầu** một tập scope, authorization server quyết định tập **được cấp**, còn resource server kiểm tra quyền **thực sự cần cho hành động và tài nguyên cụ thể**. Client không tự cấp quyền cho mình bằng cách thêm chuỗi vào tham số `scope`.

## 1. Scope trong OAuth 2.0 là gì?

Theo OAuth 2.0, scope là một tập giá trị dạng chuỗi biểu thị phạm vi truy cập được yêu cầu hoặc được cấp cho access token. Cách đặt tên và ý nghĩa của scope do authorization server và resource server cùng xác định theo hợp đồng tích hợp.

Ví dụ một API quản lý đơn hàng có thể định nghĩa:

| Scope ví dụ | Quyền chức năng được biểu diễn | Việc vẫn phải kiểm tra ở API |
| --- | --- | --- |
| `orders:read` | Được yêu cầu đọc dữ liệu đơn hàng | Chủ sở hữu đơn hàng, tenant, trường dữ liệu nào được xem |
| `orders:create` | Được yêu cầu tạo đơn hàng | Ai được tạo, hạn mức, sản phẩm và tình trạng khách hàng |
| `orders:cancel` | Được yêu cầu hủy đơn hàng | Trạng thái đơn, thời hạn hủy, quyền sở hữu |
| `orders:refund` | Được yêu cầu hoàn tiền | Vai trò nghiệp vụ, hạn mức, phê duyệt, tình trạng thanh toán |

Các tên trên **chỉ là ví dụ do hệ thống đặt**, không phải bộ scope chuẩn của OAuth. Chúng cần giữ **ngữ nghĩa ổn định** trong cùng một API và hợp đồng phát hành token. Nếu cùng chuỗi `orders:refund` được hiểu là «đọc hoàn tiền» ở client A nhưng là «thực hiện hoàn tiền» ở client B, nhà phát triển rất dễ cấu hình sai. Thay vì đổi nghĩa chuỗi theo client, nên giữ hành động rõ ràng và **giới hạn client nào có thể nhận scope đó**.

### 1.1. Cú pháp scope

Trong OAuth 2.0, tham số `scope` là danh sách các giá trị **phân tách bằng dấu cách**, giá trị là chuỗi phân biệt chữ hoa/chữ thường theo hợp đồng.

```text
scope=orders:read orders:create
```

Khi đưa vào URL hoặc form request, danh sách này phải được mã hóa đúng:

```text
scope=orders%3Aread%20orders%3Acreate
```

Trong JWT access token, claim `scope` thường là **một chuỗi phân tách bằng dấu cách** theo profile áp dụng (ví dụ RFC 9068). Một số hệ thống dùng claim riêng như `scp` dạng mảng, nhưng RS phải xử lý **theo hợp đồng thực tế của issuer**, không đoán tên/kiểu claim hoặc tự coi mọi mảng `permissions` đều tương đương `scope`.

Không kiểm tra scope bằng cách tìm chuỗi con:

```java
// Sai: "orders:read" là substring của "orders:read:all".
if (scopeString.contains("orders:read")) {
    allow();
}
```

Sau khi **xác minh token**, validator phải phân tích scope thành **tập giá trị** rồi so sánh chính xác, tránh lỗi `read` khớp nhầm `read:all` hoặc nhầm phân biệt hoa/thường.

## 2. Scope yêu cầu, scope client được phép và scope thực tế được cấp

Cần tách ba tập quyền khác nhau:

1. **Requested scopes** — tập mà client gửi trong authorization request hoặc token request.
2. **Allowed scopes** — tập tối đa mà authorization server cho phép client đó yêu cầu theo đăng ký client, grant type, resource/audience và chính sách.
3. **Granted scopes** — tập mà authorization server thực sự cấp cho lần ủy quyền/token sau khi xét quyền của resource owner, consent, rủi ro, quyền hiện hành và chính sách riêng.

Với mô hình đơn giản, kết quả cấp quyền thường thỏa:

```text
GrantedScopes ⊆ RequestedScopes ∩ ClientAllowedScopes ∩
                ResourceOwnerAllowedScopes ∩ ResourcePolicyScopes
```

Biểu thức là **mô hình giảng dạy**, không phải thuật toán bắt buộc của OAuth. Nếu client **không gửi `scope`**, authorization server có thể áp dụng phạm vi mặc định theo chính sách hoặc từ chối; không thể mặc định `RequestedScopes = tất cả`. Với `client_credentials` không có resource owner ủy quyền trực tiếp, điều kiện `ResourceOwnerAllowedScopes` được thay bằng **quyền của client/dịch vụ**.

Ví dụ:

```text
Client: partner-reporting
Requested:         {orders:read, orders:refund}
ClientAllowed:     {orders:read}
OwnerGranted:      {orders:read, orders:refund}
ResourcePermitted: {orders:read, orders:refund}
Kết quả:           {orders:read} (hoặc từ chối, tùy policy AS)
```

Trong trường hợp này, người dùng đồng ý «hoàn tiền» cũng **không giúp** client đối tác vượt giới hạn đăng ký. AS chỉ nên cấp phạm vi được phép, hoặc từ chối yêu cầu không hợp lệ theo chính sách.

Theo OAuth 2.0, khi phạm vi được cấp **khác phạm vi được client yêu cầu**, phản hồi thành công từ token endpoint phải biểu thị phạm vi được cấp bằng tham số `scope`. Client phải **đọc kết quả thực tế** thay vì mặc định AS đã cấp toàn bộ scope yêu cầu.

## 3. Vì sao scope khác nhau theo client?

**Client** là ứng dụng hoặc dịch vụ dùng OAuth. Mỗi client thường có `client_id`, tập grant type được phép, redirect URI (nếu có), loại client, các resource/audience và quyền tối đa riêng.

Giả sử hệ thống có ba client:

| Client | Đặc điểm | Scope có thể được AS cho phép yêu cầu | Điều kiện nghiệp vụ thêm |
| --- | --- | --- | --- |
| `shop-spa` | Public client chạy trong trình duyệt, đại diện người dùng | `orders:read`, `orders:create` | Chỉ thao tác trên đơn của chính người dùng; authorization code + PKCE |
| `partner-reporting` | Confidential web/backend của đối tác, truy cập dữ liệu được ủy quyền | `orders:read` | Consent, tenant đối tác và chính sách chia sẻ dữ liệu |
| `finance-batch` | Confidential service dùng `client_credentials` | `orders:read`, `orders:refund` nếu tổ chức cho phép | Quyền service principal, giới hạn hệ thống và kiểm soát giao dịch |

Mỗi client có thể yêu cầu cùng `orders:read`, nhưng **phạm vi đối tượng thực tế** vẫn khác nhau: `shop-spa` chỉ có thể xem đơn của người dùng; `partner-reporting` chỉ xem đơn thuộc hợp đồng đối tác; `finance-batch` chỉ truy cập phạm vi dịch vụ được cấu hình.

Những hạn chế đó thường **không thể mã hóa đủ bằng một scope**. Resource server phải kiểm tra chủ thể, owner, tenant, resource state và các policy nghiệp vụ.

### 3.1. Public client và confidential client

- **Public client** như SPA hoặc ứng dụng mobile không thể giữ bí mật `client_secret` nhúng trong JavaScript/mobile. Client vẫn có `client_id`, nhưng đó **không phải credential bí mật**. Với authorization code flow, sử dụng **PKCE** và những biện pháp bảo vệ luồng phù hợp.
- **Confidential client** như backend có nơi lưu bí mật an toàn có thể xác thực với AS bằng phương thức được hỗ trợ, ví dụ secret hoặc private-key JWT. Tuy nhiên, **confidential không tự động đồng nghĩa có scope rộng**; quyền vẫn do AS quyết định.
- **Machine-to-machine client** thường dùng `client_credentials`. Token đại diện cho client/service principal chứ không mang ý nghĩa người dùng vừa chấp thuận trong một màn hình consent.

Không nên cấp `orders:refund` cho một SPA chỉ vì SPA khó bảo vệ secret, nhưng cũng không nên kết luận rằng **mọi confidential client đều được phép hoàn tiền**. Phân loại public/confidential là năng lực xác thực và bảo vệ credential; **chính sách cấp scope** là quyết định phân quyền riêng.

### 3.2. Client đăng ký quyền không có nghĩa mọi request đều được cấp

Ngay cả khi AS cấu hình `partner-reporting` có quyền yêu cầu `orders:read`, người dùng có thể không được phép chia sẻ một số tenant hoặc AS có thể yêu cầu consent chưa được cấp. Trong một số luồng, AS sẽ từ chối nếu không đủ điều kiện; trong luồng khác, nó có thể cấp **tập scope nhỏ hơn** theo chính sách.

Điều quan trọng là *scope cho phép tối đa theo client* chỉ là **trần quyền**. Trên mỗi yêu cầu, AS vẫn cần đánh giá người dùng/chủ thể, resource, grant, rủi ro và trạng thái consent.

## 4. Mô hình tin cậy: client yêu cầu, authorization server quyết định

Trong OAuth 2.0, access token đi qua ba vai trò:

| Thành phần | Có thể làm gì? | Không được tự quyết định điều gì? |
| --- | --- | --- |
| **Client** | Chọn các scope muốn xin trong phạm vi chức năng cần dùng; trình access token cho API | Không thể tự biến scope yêu cầu thành scope được cấp hoặc sửa claim token để nâng quyền |
| **Authorization Server (AS)** | Xác thực client theo loại client, kiểm tra grant và chính sách, phát token với scope/audience phù hợp | Không nên cấp scope vượt quyền của client hoặc chủ thể ủy quyền |
| **Resource Server (RS)** | Xác minh access token, kiểm tra phạm vi và quyền trên tài nguyên tại lúc thực thi | Không được tin `scope`, `client_id`, `user_id` trong body/header mà client tự khai |

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client (shop-spa)
    participant AS as Authorization Server
    participant RS as Resource Server (orders-api)

    U->>C: Bấm "Xem đơn hàng"
    C->>AS: Authorization request (scope=openid orders:read, PKCE, state...)
    AS->>AS: Kiểm tra client, user, grant, consent, policy
    AS-->>C: Authorization code
    C->>AS: POST /token (code, code_verifier)
    AS-->>C: Access token có granted scope=orders:read
    C->>RS: GET /orders/42 (Bearer access token)
    RS->>RS: Xác minh token, audience, scope và owner/tenant
    RS-->>C: 200 nếu đủ quyền; ngược lại 401/403
```

Trong authorization code flow với OIDC, `openid` là scope yêu cầu dịch vụ định danh theo OIDC; `orders:read` là scope tài nguyên do hệ thống ứng dụng định nghĩa. Việc token response có ID token hay access token nào phụ thuộc luồng và quyền được cấp. **ID token có audience dành cho client**, không phải token gọi `orders-api`.

### 4.1. Vì sao không tin tham số `scope` ở request gọi API?

Giả sử client gửi:

```http
DELETE /orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
X-Requested-Scope: orders:refund
```

RS **không được** dùng `X-Requested-Scope` để quyết định quyền. Header này chỉ là dữ liệu do bên gọi tự cung cấp. RS phải lấy scope từ **access token đã xác minh** hoặc metadata introspection đáng tin, sau đó so khớp với action và tài nguyên.

Tương tự, `client_id` trong authorization request là định danh công khai; nó không chứng minh một public client là ứng dụng chính chủ hay được sở hữu bí mật bởi bên gửi. AS cần áp dụng ràng buộc phù hợp với grant, client registration, PKCE, redirect URI và client authentication theo loại client.

## 5. Access token có scope được biểu diễn như thế nào?

Một **JWT access token** theo profile được thỏa thuận có thể chứa:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "shop-spa",
  "scope": "orders:read orders:create",
  "iat": 1893456000,
  "exp": 1893459600
}
```

Đây là **payload minh họa**, chưa có JOSE header/chữ ký; các mốc thời gian chỉ mang tính ví dụ. Trong JWT access token theo RFC 9068, cần tuân thủ profile đầy đủ (bao gồm header `typ` phù hợp, các claim bắt buộc). Không tự coi một chuỗi JSON như token đã xác thực.

Tại RS:

1. Xác minh token được cấp bởi **issuer tin cậy**, bằng chữ ký và khóa/thuật toán được cấu hình, hoặc qua cơ chế được thiết kế.
2. Kiểm tra **`aud` dành cho `orders-api`**, `exp`, `nbf` nếu có, loại token/profile và các ràng buộc sender-constrained token nếu áp dụng.
3. Phân tích claim `scope` đúng **kiểu dữ liệu và ngữ nghĩa** theo hợp đồng issuer–RS.
4. So sánh chính xác scope cần thiết cho endpoint/action.
5. Kiểm tra `sub` hoặc service principal, tenant, owner, trạng thái và các quy tắc nghiệp vụ của tài nguyên.

**JWT được ký không mã hóa payload**; Base64URL decode chỉ giúp đọc, không chứng minh chữ ký hợp lệ. Scope và các claim khác có thể bị sửa trong chuỗi token giả; RS chỉ được tin sau khi xác minh.

Với **opaque access token**, RS không tự parse nội dung chuỗi. AS có thể cung cấp scope đã được cấp qua **token introspection** (RFC 7662), kèm trạng thái `active` và các thuộc tính được thỏa thuận. RS cần xác thực khi gọi introspection endpoint, dùng kết nối được bảo vệ, kiểm tra audience và quyền tương ứng. `active=true` không đồng nghĩa API cho phép mọi hành động.

### 5.1. Scope là điều kiện cần, chưa phải quyết định phân quyền cuối cùng

Ví dụ người dùng `user-123` có access token mang `orders:read`. Request:

```text
GET /orders/42
```

Nếu đơn 42 thuộc `user-456` hoặc tenant khác, RS vẫn phải **từ chối**. Bỏ qua kiểm tra tài nguyên tạo lỗ hổng truy cập đối tượng sai quyền (*Broken Object Level Authorization*, BOLA/IDOR).

Một policy có thể mô tả:

```text
allowReadOrder =
    valid_access_token
    AND token.audience contains "orders-api"
    AND token.scopes contains_exactly_member "orders:read"
    AND subject_is_allowed_on_requested_tenant
    AND (order.owner_id == subject_id OR approved_delegation_exists)
    AND order.visibility_policy_allows_read
```

Đối với `client_credentials`, `sub`/principal có thể là định danh **dịch vụ**, không nhất thiết là người dùng cuối. Khi đó quy tắc owner phải áp dụng service principal hoặc quyền được ủy quyền đúng cách; không ánh xạ ngầm service thành một user bất kỳ.

## 6. Audience và resource: cùng scope có thể không dùng được cho mọi API

Nếu hệ thống có `orders-api` và `billing-api`, cả hai có thể dùng chuỗi scope `read` theo quy ước lịch sử. Nhưng **scope không tự chứng minh token được cấp cho API nào**. Vì vậy:

- **`scope`** biểu diễn phạm vi hành động/quyền.
- **`aud`** hoặc resource indicator biểu diễn resource server/token audience được nhắm đến theo hợp đồng.
- **`client_id`** cho biết client liên quan tới grant/token theo profile, không thay cho audience.

Ví dụ:

```json
{
  "iss": "https://auth.example.test",
  "aud": "orders-api",
  "client_id": "shop-spa",
  "scope": "orders:read"
}
```

**`billing-api` không được chấp nhận token này** nếu audience không dành cho billing, kể cả khi billing có một endpoint đọc dữ liệu.

OAuth 2.0 cung cấp cơ chế **resource indicators** (RFC 8707) để client chỉ định tài nguyên đích trong yêu cầu cấp token khi AS hỗ trợ:

```text
resource=https://api.example.test/orders
scope=orders:read
```

Giá trị `resource` được AS diễn giải thành đối tượng tài nguyên/audience theo cấu hình. **Client gửi `resource` không bảo đảm AS sẽ cấp token cho resource đó**; AS vẫn phải kiểm tra client và chính sách. Nếu một access token có nhiều audience được cho phép, từng RS vẫn phải áp dụng scope và chính sách riêng, tránh để token của một hệ thống bị lạm dụng ở hệ thống khác.

Với kiến trúc microservice, không nên **chuyển tiếp mù quáng** access token vốn được cấp cho service A sang service B. Nếu B không thuộc audience, B phải từ chối. Khi cần B xử lý thay mặt người dùng, có thể sử dụng thiết kế delegation/token exchange thích hợp do AS hỗ trợ và bảo toàn giới hạn quyền.

## 7. Consent, user scope và OIDC scope

Trong luồng **delegated authorization** (client hoạt động thay mặt resource owner), AS có thể yêu cầu người dùng đồng ý chia sẻ một số quyền cho client. Nhưng **consent không phải nguồn duy nhất quyết định scope**:

- User có thể từ chối một phần scope; AS có thể cấp tập nhỏ hơn hoặc không cấp token tùy chính sách.
- User **không thể cấp quyền mình không có**. Một người dùng bình thường không thể đồng ý để client hoàn tiền nếu bản thân user không được phép.
- AS có thể không hiển thị consent ở mỗi lần đăng nhập, tùy thiết kế, quan hệ client, consent đã lưu và chính sách.
- Trong `client_credentials`, không có bước người dùng trực tiếp đồng ý trong chính grant đó; quyền được xác định cho client/service.

### 7.1. Scope OIDC không giống scope của API nghiệp vụ

OIDC định nghĩa các scope chuẩn như:

| Scope OIDC | Mục đích | Không nên suy diễn |
| --- | --- | --- |
| `openid` | Yêu cầu dịch vụ xác thực OIDC và ID token theo luồng | Quyền đọc mọi tài nguyên API |
| `profile` | Yêu cầu các claim profile người dùng theo OIDC | Quyền chỉnh sửa profile trong ứng dụng |
| `email` | Yêu cầu claim liên quan email theo OIDC | Người dùng đã có quyền dùng email làm tài khoản quản trị |
| `address` | Yêu cầu claim địa chỉ theo OIDC | Quyền đọc mọi địa chỉ trong dữ liệu nghiệp vụ |
| `phone` | Yêu cầu claim số điện thoại theo OIDC | Quyền thay số điện thoại hoặc quyền gọi SMS |
| `offline_access` | Xin quyền truy cập khi user không hiện diện, thường liên quan khả năng phát hành refresh token theo điều kiện OIDC | AS chắc chắn phát refresh token hoặc cấp quyền API không giới hạn |

`openid profile email` là một yêu cầu về định danh/claim từ OP, **không thay thế** `orders:read` trong access token của `orders-api`. ID token vẫn được phát hành cho **client/RP**, không được đưa vào `Authorization: Bearer` gửi cho API như access token.

Đặc biệt, scope `offline_access` không phải cách «ép» AS phải phát hành refresh token; AS còn kiểm tra consent, grant, client type và chính sách. Việc có refresh token không mở rộng quyền vượt những gì AS cho phép.

## 8. Scope thay đổi khi user, client hoặc hoàn cảnh thay đổi

Scope có thể khác nhau ở **hai mức**: (a) giới hạn được đăng ký cho mỗi client và (b) phạm vi thực tế AS quyết định ở từng lần cấp token.

### 8.1. Client được đổi cấu hình quyền

Giả sử ngày đầu `partner-reporting` chỉ có `orders:read`. Sau khi có hợp đồng mới, quản trị viên AS cập nhật client policy để cho phép thêm `orders:export`. Điều này **không tự bổ sung** `orders:export` vào các access token đã phát hành; client cần thực hiện luồng OAuth phù hợp để nhận token với quyền mới nếu AS chấp thuận.

Ngược lại, khi quyền `orders:export` bị gỡ khỏi đăng ký client, **JWT đã phát hành** có thể vẫn chứa scope đó tới khi hết hạn nếu RS chỉ tự xác minh token offline. Với quyền cần thu hồi nhanh, phải có cơ chế phù hợp như TTL ngắn, kiểm tra quyền hiện hành, denylist hoặc introspection/revocation theo kiến trúc.

### 8.2. User hoặc consent đổi

Một người dùng có thể bị gỡ quyền quản lý sau khi access token đã phát hành. Token chứa `orders:refund` không có nghĩa quyền đó tồn tại mãi; RS cần chính sách xác định mức độ chấp nhận claim cũ và thời gian phản ánh cập nhật quyền.

**Thu hồi consent** thường phải được AS xử lý cùng với grant/refresh token liên quan theo chính sách; điều đó không bảo đảm mọi access token JWT đang lưu tại client sẽ bị mọi RS từ chối ngay nếu không có cơ chế trạng thái bổ sung.

### 8.3. Scope giới hạn theo ngữ cảnh

Trong một số hệ thống, AS còn cân nhắc rủi ro, thiết bị, ca trực hoặc lớp xác thực mới khi cấp scope. Ví dụ `orders:refund` chỉ được cấp sau bước **step-up authentication**.

Nhưng phải nhớ:

- Scope chứa trong token thường phản ánh **quyết định tại lúc phát hành**.
- Điều kiện nghiệp vụ hiện tại như số tiền giao dịch, tenant hoặc thời điểm thực hiện có thể đã thay đổi.
- RP có thể yêu cầu OIDC `max_age`/`acr_values`, xác minh `auth_time` và `acr` trong ID token cho client; nếu API cần assurance, phải dùng cơ chế **chuyển thông tin đáng tin cậy** qua AS/access token/introspection hoặc PDP.

**Không dùng ID token thay access token**, và không coi `amr=["pwd","otp"]` là bằng chứng đủ để hoàn tiền nếu chính sách còn yêu cầu quyền nghiệp vụ và chủ sở hữu.

## 9. Downscoping: cấp đúng quyền nhỏ nhất cần dùng

Nguyên tắc **least privilege** gợi ý client chỉ yêu cầu scope cần cho thao tác hiện tại. Một ứng dụng có thể cần `orders:read` khi người dùng mở trang lịch sử, nhưng chỉ xin `orders:create` trong luồng đặt hàng nếu thiết kế yêu cầu.

Lợi ích:

- Giảm tác động nếu access token bị lộ.
- Làm rõ consent cho người dùng.
- Giảm khả năng client dùng một access token rộng để gọi nhiều tính năng không liên quan.
- Tạo điều kiện cho AS/RS áp dụng chính sách riêng theo hành động và tài nguyên.

**Downscoping** nghĩa là xin hoặc cấp một token mới với phạm vi **hẹp hơn** quyền mà client/grant được phép; cơ chế chi tiết tùy OAuth grant/AS và profile hỗ trợ. Không phải mọi AS đều có endpoint downscope riêng.

Trong OAuth 2.0, khi dùng refresh token để xin access token mới, client **không được yêu cầu phạm vi mở rộng vượt quá grant ban đầu**, và AS phải thực thi giới hạn tương ứng. Một refresh token có thể giúp xin token với scope hẹp hơn theo chính sách, nhưng **không phải đường nâng quyền** khi người dùng/client chưa có grant mới.

Ví dụ:

```text
Grant đang có:       {orders:read, orders:create}
Refresh request:     scope=orders:read
Có thể được cấp:     {orders:read}

Refresh request:     scope=orders:refund
Không hợp lệ nếu scope này không thuộc grant/không được phép
```

Việc AS từ chối hay trả lỗi cụ thể phụ thuộc chính sách và tình huống, nhưng **không được mở rộng grant trái quy tắc OAuth**.

### 9.1. Scope rộng không nên được dùng làm «quyền dự phòng»

Một anti-pattern là xin `admin:*` từ lúc đăng nhập «để chắc chắn mọi chức năng chạy được». Nếu token này bị đánh cắp, kẻ tấn công có thể thử thực hiện nhiều thao tác hơn. Scope quá rộng cũng khiến việc giới hạn resource và audit khó khăn.

Nên thiết kế scope có ý nghĩa nghiệp vụ rõ, đủ chi tiết để hỗ trợ least privilege, nhưng không lạm dụng hàng nghìn scope riêng cho từng bản ghi. Quyền trên từng bản ghi/tenant thường phù hợp hơn với **resource policy, ABAC/RBAC hoặc mối quan hệ sở hữu**, thay vì đặt một scope cho mỗi ID đơn hàng.

## 10. Ví dụ quy trình cấp scope theo client

Giả sử AS lưu cấu hình chính sách dạng minh họa:

```yaml
# Pseudoconfiguration, không phải file cấu hình chuẩn OAuth
clients:
  shop-spa:
    type: public
    grants: [authorization_code]
    require_pkce: true
    allowed_resources: [orders-api]
    allowed_scopes: [openid, orders:read, orders:create]

  partner-reporting:
    type: confidential
    grants: [authorization_code]
    allowed_resources: [orders-api]
    allowed_scopes: [openid, orders:read]
    require_delegated_consent: true

  finance-batch:
    type: confidential
    grants: [client_credentials]
    allowed_resources: [orders-api]
    allowed_scopes: [orders:read, orders:refund]
    require_service_policy: true
```

AS có thể giải quyết yêu cầu bằng logic khái niệm:

```java
// Pseudocode: các kiểu dữ liệu/dịch vụ là minh họa.
TokenGrant grantScopes(
    RegisteredClient client,
    OAuthGrant grant,
    Set<String> requested,
    Resource audience
) {
    verifyGrantAllowed(client, grant);
    verifyClientAuthenticationOrPkce(client, grant);
    verifyAllowedResource(client, audience);

    Set<String> requestedOrDefault =
        requested.isEmpty()
            ? scopePolicy.defaultScopesFor(client, grant, audience)
            : requested;

    if (!client.allowedScopes().containsAll(requestedOrDefault)) {
        // Một AS có thể từ chối thay vì tự giảm scope.
        throw invalidScope();
    }

    Set<String> permitted =
        scopePolicy.permittedForPrincipal(client, grant, audience);
    Set<String> consented =
        consentPolicy.grantedOrNotRequired(client, grant, audience);

    Set<String> granted = intersect(
        requestedOrDefault, permitted, consented
    );
    if (granted.isEmpty() && policyRequiresScope()) {
        throw invalidScope();
    }
    return tokenIssuer.issue(
        client, grant, audience, granted, policyBasedLifetime()
    );
}
```

Đoạn code chỉ minh họa **thứ tự trách nhiệm và nguyên tắc giới hạn quyền**. Trong triển khai thật, confidential client authentication, authorization code/PKCE, consent, token binding và grant validation phải do framework OAuth/AS được kiểm thử thực hiện; không dùng pseudocode làm implementation production.

Chính sách của AS cũng cần xác định **vì sao client không được nhận scope**: chưa đăng ký, user từ chối, sai grant, sai resource, điều kiện xác thực chưa đạt hoặc chính sách tổ chức. Nội bộ nên ghi audit với thông tin cần thiết, nhưng không ghi raw authorization code, access token hay refresh token.

## 11. Resource server thực thi scope như thế nào?

RS cần quyết định theo **token thực tế đã được xác minh**, không phụ thuộc vào tham số scope mà client từng xin.

Ví dụ API Java giả định có `AccessTokenVerifier` được cấu hình sẵn để kiểm tra access token đúng issuer, audience, token type và expiry. Các class dưới đây là pseudocode, không phải API của một thư viện cụ thể:

```java
Response getOrder(String rawBearerToken, String orderId) {
    VerifiedAccessToken token = verifier.verify(
        rawBearerToken,
        "https://auth.example.test",
        "orders-api"
    );

    // Token issuer đã xác minh chuỗi scope thành tập giá trị chính xác.
    if (!token.scopes().contains("orders:read")) {
        return forbidden("insufficient_scope");
    }

    Order order = ordersRepository.findById(orderId);
    if (order == null) {
        return notFound();
    }

    // Tránh BOLA/IDOR: scope không quyết định owner/tenant.
    if (!token.tenantId().equals(order.tenantId())) {
        return forbidden("cross_tenant");
    }
    if (!authorizationPolicy.canReadOrder(
            token.subject(), token.clientId(), order)) {
        return forbidden("not_authorized_for_resource");
    }

    return ok(order);
}
```

**Lưu ý:** ví dụ giả định token đại diện người dùng, có tenant từ nguồn đã xác minh. Token `client_credentials` cần chính sách principal riêng. Không tin `tenantId` từ query/body nếu nó có thể bị client sửa.

Với bearer token, khi thiếu/không có token hợp lệ, RS thường trả **401 Unauthorized** cùng header `WWW-Authenticate` phù hợp; khi token hợp lệ nhưng thiếu scope cần thiết, dùng **403 Forbidden** và có thể trả thông tin `insufficient_scope` theo RFC 6750. Việc trả 404 để che sự tồn tại tài nguyên là lựa chọn policy cụ thể.

### 11.1. API gateway có thể thực thi thay RS không?

Gateway có thể kiểm tra issuer/audience/scope ở lớp ngoài, nhưng lớp nghiệp vụ vẫn phải bảo vệ **quyền đối với đối tượng**. Nếu gateway truyền kết quả xác thực vào service qua header, RS chỉ được tin header đó khi kênh từ gateway đã được bảo vệ, request trực tiếp có thể giả mạo header bị ngăn và các trách nhiệm kiểm tra được thiết kế rõ ràng.

Không tự tin `X-Scopes: orders:refund` trong request đi từ Internet. Cũng không nên chỉ ẩn nút chức năng trên giao diện vì client có thể gọi API trực tiếp.

## 12. Scope, refresh token và việc quyền bị rút

Một access token JWT có thể còn hợp lệ sau khi AS gỡ `orders:refund` khỏi client. Cần phân biệt:

| Thay đổi | Điều gì xảy ra? | Cơ chế phản ánh quyền hiện hành |
| --- | --- | --- |
| Client không còn được xin `orders:refund` | AS không nên cấp mới quyền đó | Cập nhật client policy, kiểm tra trong lần cấp token kế tiếp |
| User mất quyền hoàn tiền | Token cũ có thể vẫn mang scope đã cấp | Kiểm tra quyền động tại RS, TTL phù hợp, introspection/denylist nếu cần |
| Refresh token bị thu hồi | Client không thể dùng refresh token đó để xin token mới | AS áp dụng token revocation/rotation theo chính sách |
| JWT access token bị đánh cắp | Kẻ tấn công có thể thử dùng trong thời gian token còn hiệu lực | Bảo vệ lưu trữ, HTTPS, TTL, thu hồi/trạng thái bổ sung, mTLS/DPoP khi thích hợp |
| Opaque token được AS đánh dấu inactive | RS có thể biết qua introspection | Cache introspection phải đủ ngắn và có invalidation theo rủi ro |

**Refresh token** dùng tại authorization server để xin access token mới; không được gửi refresh token cho API nghiệp vụ. Việc client có refresh token không có nghĩa client luôn có thể lấy token chứa mọi scope từng yêu cầu: AS phải xét grant, client và quyền hiện hành khi phát hành lại.

Khi sử dụng **refresh token rotation**, refresh token cũ bị vô hiệu sau lần đổi thành công; reuse detection có thể giúp phát hiện token bị đánh cắp. Rotation **không tự động** thu hẹp scope trong access token còn tồn tại hoặc thay thế việc RS kiểm tra phân quyền.

## 13. An toàn của scope khi token bị đánh cắp hoặc phát lại

Scope hẹp có tác dụng **giảm thiểu tác động** khi token bị lộ, nhưng không ngăn được kẻ tấn công **dùng chính quyền hẹp đó**.

Ví dụ: token bị lộ chỉ có `orders:read` sẽ khó dùng để gọi endpoint yêu cầu `orders:refund` nếu RS kiểm tra đúng. Tuy nhiên, kẻ tấn công vẫn có thể thử đọc những đơn thuộc phạm vi token cho phép. Vì vậy:

- Dùng HTTPS; không đưa bearer token vào URL, log, analytics hoặc bộ nhớ client không phù hợp.
- Với public client, cân nhắc luồng token/session an toàn, phòng chống XSS và sử dụng backend-for-frontend khi phù hợp; không nhúng client secret trong SPA.
- Giới hạn lifetime; cân nhắc **sender-constrained token** như mTLS hoặc DPoP để giảm khả năng sử dụng token bị đánh cắp khi profile/hạ tầng hỗ trợ.
- Xác minh `iss`, `aud`, token type, scope và thời hạn ở RS. Chữ ký JWT không bảo đảm bí mật nội dung token; đừng đưa dữ liệu nhạy cảm không cần thiết vào claim.
- Theo dõi bất thường và khả năng thu hồi/quản lý phiên theo mức độ rủi ro. Token bị đánh cắp có thể bị phát lại trước khi hết hạn; **scope không phải cơ chế replay protection**.

Việc thêm `"scope": "orders:refund"` vào payload JWT của client không tạo quyền mới, vì chữ ký không còn hợp lệ. Nếu RS chỉ Base64URL decode mà không xác minh chữ ký, **mọi giới hạn scope đều có thể bị vượt qua** bằng token giả mạo.

## 14. Những sai lầm thường gặp

| Sai lầm | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| Client gửi `scope=admin` và AS luôn cấp | Client tự nâng quyền | AS kiểm tra allowed/granted scopes theo client, grant và chủ thể |
| AS coi mọi confidential client đều có quyền quản trị | Client có secret nhưng vượt quyền | Phân biệt client authentication với authorization |
| Frontend ẩn nút hủy đơn nhưng API không kiểm tra scope/owner | Người dùng gọi endpoint trực tiếp | RS kiểm tra token và quyền tài nguyên |
| RS so sánh scope bằng `contains()` trên chuỗi | `read` khớp nhầm `read:all` | Parse thành tập và so khớp giá trị chính xác |
| RS chỉ kiểm tra scope mà không kiểm tra `aud` | Token của API khác được chấp nhận | Bắt buộc xác minh audience cho RS |
| RS chỉ kiểm tra scope mà không kiểm tra tenant/owner | BOLA/IDOR, đọc dữ liệu người khác | Phân quyền từng tài nguyên với principal đã xác minh |
| Coi requested scope là granted scope | Thực hiện hành động chưa được AS cấp | Đọc scope phản hồi và access token đã xác minh |
| Dùng ID token `openid profile` gọi API | Sai mục đích và audience token | Dùng access token dành cho RS, ID token chỉ cho RP |
| Tự ép kiểu claim `scp`/`scope` không có contract | Nhầm quyền khi khác issuer/profile | Strict schema và validator theo token profile |
| Refresh request xin scope ngoài grant | Nâng quyền từ refresh token | AS giới hạn phạm vi refresh theo grant và policy |
| Gỡ scope khỏi client nhưng vẫn tin JWT cũ vô hạn | Quyền đã rút chưa được phản ánh | TTL, introspection, denylist hoặc kiểm tra quyền động |
| Dùng scope làm bằng chứng xác thực mới/MFA | Nhầm authorization với authentication assurance | Bổ sung chính sách step-up và bằng chứng tin cậy |
| Token `client_credentials` bị coi là user token | Quyền dịch vụ bị ánh xạ sai sang người dùng | Policy theo service principal; delegation rõ ràng nếu có user |
| Đưa bearer token vào URL để debug scope | Token lộ trong log/history/referrer | Dùng kênh/thiết bị quan sát an toàn, không ghi raw token |

## 15. Bộ kiểm thử gợi ý

| Trường hợp | Kỳ vọng |
| --- | --- |
| `shop-spa` yêu cầu `orders:read` | AS cấp nếu user/grant/policy cho phép |
| `shop-spa` yêu cầu `orders:refund` không thuộc allowed scopes | AS từ chối hoặc không cấp scope đó theo chính sách |
| `partner-reporting` xin `orders:read` nhưng consent chưa đạt | Không cấp ngoài chính sách ủy quyền |
| `finance-batch` xin `orders:refund` qua `client_credentials` | Chỉ cấp nếu quyền dịch vụ và client registration cho phép |
| Client không gửi `scope` | Áp dụng default scope rõ ràng hoặc từ chối theo AS policy |
| AS cấp tập scope nhỏ hơn yêu cầu | Client nhận biết actual granted scope; không coi đã có scope bị cắt |
| Token có `orders:read:all` nhưng endpoint yêu cầu `orders:read` | Không được khớp sai bằng substring |
| Token dành cho `orders-api` đi tới `billing-api` | Bị từ chối do audience |
| Access token có `orders:read` nhưng truy cập đơn khác tenant | Bị từ chối bởi resource policy |
| User token bị dùng cho endpoint chỉ chấp nhận service principal | Bị từ chối theo grant/principal policy |
| Service token bị coi là user `sub` | Bị từ chối hoặc được xử lý theo chính sách dịch vụ, không tự giả user |
| Chữ ký JWT bị sửa để thêm `orders:refund` | Token bị từ chối |
| Opaque token inactive nhưng trả `scope` từ cache cũ | Không được cho phép vượt chính sách cache/trạng thái |
| User bị rút quyền trong khi access token JWT còn hạn | Áp dụng chính sách phản ánh thu hồi đã định nghĩa |
| Refresh token xin scope ngoài grant ban đầu | Không được mở rộng grant |
| API nhận ID token thay access token | Từ chối |
| Token có scope đúng nhưng giao dịch không còn ở trạng thái cho phép | Bị từ chối ở lớp nghiệp vụ |

Để xác minh chất lượng triển khai, nên kiểm thử cả **token đã ký hợp lệ** từ issuer thử nghiệm lẫn token giả mạo/sai audience; test đồng thời quyền owner/tenant và thay đổi policy. Mọi ví dụ ở đây là mô hình học tập, chưa phải test suite hay tích hợp của framework cụ thể.

## 16. Checklist khi thiết kế scope theo client

1. **Định nghĩa rõ scope:** mỗi scope có một ý nghĩa ổn định theo API/resource; không dùng cùng chuỗi với quyền mâu thuẫn giữa client.
2. **Đăng ký giới hạn client:** danh sách allowed scopes gắn với client, grant type, resource, loại client và chính sách ủy quyền.
3. **Phân biệt các tập:** requested, allowed và granted scopes phải rõ; client không giả định AS luôn cấp tất cả yêu cầu.
4. **Bảo vệ OAuth flow:** authorization code + PKCE cho public client; confidential client phải xác thực theo phương thức AS hỗ trợ; xử lý redirect URI, state và nonce khi áp dụng.
5. **Audience đúng API:** scope không thay thế resource indicator/audience; RS kiểm tra đúng issuer, audience, token type và thời hạn.
6. **Enforcement tại RS:** parse scope chính xác và kiểm tra quyền owner, tenant, hạn mức, trạng thái ở resource thực.
7. **Phân biệt OAuth/OIDC:** scope `openid`/`profile` không tự là quyền API; ID token không được dùng thay access token.
8. **Vòng đời và refresh:** token mới/refresh không tự mở rộng grant; đã có cơ chế gỡ quyền, thu hồi, TTL và xử lý claim cũ.
9. **Giảm thiểu quyền:** xin/cấp scope đủ dùng; cân nhắc downscoping, bảo vệ token và sender constraint khi cần.
10. **Quan sát và kiểm thử:** audit scope được cấp/bị từ chối theo chính sách nhưng không log raw token; test sai audience, sai tenant, client bị giới hạn và quyền đổi theo thời gian.

## Tổng kết

**Scope thay đổi theo client** vì mỗi client có mục đích, loại grant, resource, mức tin cậy và quyền tối đa khác nhau. Trong OAuth 2.0, **authorization server quyết định scope được cấp** sau khi xét requested scopes, client registration, quyền chủ thể, consent và policy; **resource server xác minh access token và thực thi scope trên tài nguyên thật**. Cùng một scope có thể được nhiều client sử dụng nhưng không được biến thành quyền vô hạn hoặc bỏ qua audience, tenant, owner và trạng thái nghiệp vụ. Kết hợp least privilege, downscoping, ràng buộc audience, kiểm soát vòng đời token và cơ chế chống đánh cắp/phát lại giúp giới hạn rủi ro khi hệ thống tăng số lượng client.

**Tài liệu tham khảo:** RFC 6749 (The OAuth 2.0 Authorization Framework, scope và token response); RFC 6750 (Bearer Token Usage); RFC 7636 (PKCE); RFC 7662 (Token Introspection); RFC 7009 (Token Revocation); RFC 8707 (Resource Indicators for OAuth 2.0); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); RFC 9700 (OAuth 2.0 Security Best Current Practice); OpenID Connect Core 1.0.
