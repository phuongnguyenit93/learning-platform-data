# Scope consent trên device

## Mục tiêu học tập

Trong chương **Device authorization** của học phần **Token Security Fundamentals**, chủ đề **scope consent trên device** giải thích cách một người dùng xem và chấp thuận phạm vi truy cập mà ứng dụng trên **thiết bị hạn chế nhập liệu** (TV, thiết bị trình chiếu, máy in, thiết bị IoT có giao diện đơn giản) đang yêu cầu. Ở **OAuth 2.0 Device Authorization Grant (RFC 8628)**, người dùng thường thao tác đăng nhập và consent trên **thiết bị thứ hai có trình duyệt**, thay vì nhập mật khẩu hoặc phê duyệt ngay trên TV.

Điểm cốt lõi là tách ba câu hỏi: **thiết bị nào xin quyền?**, **người dùng đồng ý cho ứng dụng đó dùng những scope nào?**, và **Authorization Server/Resource Server thực sự cho phép truy cập gì?** Một mã ngắn hiển thị trên TV không tự tạo quyền; một nút “Cho phép” trên điện thoại không được biến thành quyền đọc mọi dữ liệu hoặc cho phép API bỏ kiểm tra token.

Sau bài này, bạn có thể:

1. Mô tả hai thiết bị, bốn vai trò OAuth và luồng từ `device_authorization` đến `token` bằng `device_code`.
2. Phân biệt **`device_code`**, **`user_code`**, **`verification_uri`**, **`verification_uri_complete`**, **scope yêu cầu** và **scope được cấp**.
3. Thiết kế trang consent hiển thị đúng **client, account, resource, scope, quyền nhạy cảm và truy cập ngoại tuyến** trên thiết bị xác minh.
4. Xây chính sách xác định granted scopes dựa trên **client registration, user entitlement, tenant policy, resource và user approval**.
5. Xử lý **`authorization_pending`**, **`slow_down`**, **`access_denied`**, **`expired_token`**, thời hạn và polling interval đúng RFC 8628.
6. Phân tích **device-code phishing**, liên kết nhầm thiết bị/người dùng, gian lận QR/code, token theft và ranh giới của PKCE, DPoP, mTLS.
7. Kết nối consent với cấp access/refresh token, kiểm tra audience/scope/tenant tại Resource Server và thu hồi quyền sau đó.

## 1. Vì sao consent trên device khác consent trong web thông thường?

Với ứng dụng web, người dùng có thể mở trang đăng nhập và màn hình OAuth consent **ngay trong trình duyệt đang chạy Client**. Nhưng nhiều thiết bị có:

- Điều khiển bằng remote, nút vật lý hoặc màn hình nhỏ.
- Không có bàn phím phù hợp để nhập tên đăng nhập, mật khẩu, MFA hoặc đọc mô tả dài.
- Trình duyệt hạn chế, hoặc không có trình duyệt đầy đủ.
- Yêu cầu ghép nối với tài khoản người dùng đang đăng nhập ở điện thoại/laptop.

**Device Authorization Grant** giải quyết vấn đề UX này bằng hai ngữ cảnh:

| Ngữ cảnh | Thiết bị ví dụ | Trách nhiệm |
|---|---|---|
| **Thiết bị chính (requesting device)** | Smart TV chạy Orders Viewer. | Yêu cầu device authorization, hiển thị hướng dẫn/mã, polling token endpoint và giữ token sau khi cấp. |
| **Thiết bị thứ hai (authorization/verification device)** | Điện thoại hoặc laptop có trình duyệt. | Mở website AS, đăng nhập, xác minh đúng mã/thiết bị, đọc và quyết định consent. |
| **Authorization Server (AS)** | `https://auth.example.test`. | Gắn mã với request, xác minh user/client/policy, thu consent, phát hành token cho thiết bị đã yêu cầu. |
| **Resource Server (RS)** | Orders API. | Kiểm tra token được cấp rồi quyết định thao tác và dữ liệu thực tế được phép truy cập. |

**Đừng hiểu “scope consent trên device” là thiết bị TV tự hiển thị trang consent đáng tin.** TV có thể nêu scope dự kiến để hỗ trợ user, nhưng **quyết định OAuth consent đáng tin phải được AS xử lý** trong phiên xác minh, thường trên thiết bị thứ hai.

### Ví dụ xuyên suốt

~~~text
Ứng dụng thiết bị:       Orders Viewer for TV
OAuth client_id:         orders-tv
Thiết bị chính:          TV ở phòng họp
Thiết bị xác minh:       Điện thoại của user
Authorization Server:    https://auth.example.test
Resource Server:         Orders API (aud = orders-api)
Scope ban đầu:           orders:read
User đăng nhập:          user-123 thuộc tenant-a
Mục đích:                Hiển thị đơn hàng được phép xem trên TV
~~~

Việc user đồng ý `orders:read` **không** tự cho TV quyền `orders:write`, quyền xem hóa đơn thanh toán, hay quyền xem đơn của tenant khác.

## 2. Device Authorization Grant khác Authorization Code + PKCE ra sao?

| Tiêu chí | Authorization Code + PKCE | Device Authorization Grant (RFC 8628) |
|---|---|---|
| Client khởi tạo | Authorization request/redirect trình duyệt. | `POST` tới **device authorization endpoint**. |
| Dữ liệu trung gian chính | Authorization code, `state` và PKCE challenge/verifier. | `device_code`, `user_code`, verification URI. |
| Chỗ user đăng nhập/consent | AS qua browser redirect, thường cùng thiết bị. | AS trên **thiết bị thứ hai**, thường khác thiết bị chạy Client. |
| Cách Client nhận token | Đổi authorization code với verifier và client auth khi áp dụng. | **Polling token endpoint** bằng `device_code` trong thời hạn. |
| PKCE | Bảo vệ authorization code exchange. | **Không phải bước chuẩn của grant**, vì không có authorization code để đổi bằng PKCE. |
| Các rủi ro nổi bật | Code interception/injection, callback/state, mix-up. | Lộ/mạo danh user code, lừa user xác minh flow của attacker, polling và liên kết sai thiết bị. |
| Quyền cuối cùng | Vẫn do AS giới hạn, RS xác minh token và quyền dữ liệu. | **Giống nguyên tắc này**, không được bỏ qua chỉ vì có user code. |

Không sử dụng Client Credentials flow thay Device Authorization nếu cần quyền **theo người dùng**. Client Credentials cấp quyền **ứng dụng/dịch vụ** theo registration; Device Authorization thường cho thiết bị tham gia một grant được user xác nhận trong mô hình thích hợp.

Không bắt user nhập mật khẩu trên TV và gửi trực tiếp cho ứng dụng chỉ vì đã có client ID. Luồng thiết bị giúp user tương tác với **Authorization Server** trên thiết bị nhập liệu an toàn hơn, tránh Client thu mật khẩu theo kiểu không cần thiết.

## 3. Scope, resource, consent, grant và token: năm khái niệm khác nhau

### Các lớp quyết định

| Khái niệm | Ví dụ | Ai kiểm soát? | Điểm cần nhớ |
|---|---|---|---|
| **Requested scope** | `orders:read`. | Client đưa ra yêu cầu. | Đây là **đề nghị**, chưa phải quyền được cấp. |
| **Resource/audience** | `orders-api`. | Client có thể chỉ định đích; AS quyết định token dành cho ai. | Không dùng token của Billing để gọi Orders. |
| **User consent** | User chấp nhận cho Orders Viewer đọc đơn được phép. | AS thu/ghi quyết định theo user, client, resource, tenant và giao dịch. | Không tự vượt quyền user hoặc tổ chức. |
| **Authorization grant** | Grant của user-123 cho orders-tv với `orders:read`. | AS quản lý, áp dụng chính sách/hạn dùng/thu hồi. | Có thể có consent trước đó, admin approval hoặc yêu cầu phê duyệt mới. |
| **Granted scope trên access token** | `scope="orders:read"`. | AS phát hành theo grant/policy. | RS phải kiểm tra scope đã cấp **và** quyền object. |

### Ví dụ scope

~~~text
Requested by TV:
  orders:read orders:write

Allowed for registered client:
  orders:read

Allowed by tenant:
  orders:read

Actual user approval:
  orders:read

Effective grant:
  orders:read
~~~

AS **không được** cấp `orders:write` chỉ vì TV yêu cầu. Tùy chính sách/protocol, AS có thể **từ chối request ban đầu** hoặc **cấp phạm vi hẹp hơn**; nếu hỗ trợ reduced scope, token response phải phản ánh phạm vi thực tế theo OAuth.

**Consent không phải phép giao thuần tập hợp trong mọi hệ thống.** Policy thực tế còn xét tenant, từng resource, mức xác thực, loại thiết bị, consent đã lưu, data classification và thời hạn. Việc trình bày dưới dạng tập hợp chỉ hỗ trợ suy luận.

## 4. Luồng tổng thể: người dùng chấp thuận scope trên thiết bị thứ hai

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant TV as TV / Device Client
    participant AS as Authorization Server
    participant Phone as Browser trên điện thoại
    participant API as Orders API
    TV->>AS: POST device_authorization: client_id + scope/resource
    AS->>AS: Xác minh client registration và policy sơ bộ
    AS-->>TV: device_code, user_code, verification_uri, expires_in, interval
    TV-->>U: Hiện URL/QR và user_code
    TV->>AS: POST token: device_code
    AS-->>TV: authorization_pending
    U->>Phone: Mở verification_uri và nhập/xác minh user_code
    Phone->>AS: User login/session + user_code
    AS->>AS: Ánh xạ code tới transaction và kiểm tra policy
    AS-->>Phone: Trang hiển thị Client, tài nguyên, scope, account
    U->>Phone: Chọn Cho phép hoặc Từ chối
    Phone->>AS: Consent decision theo transaction đã xác minh
    AS->>AS: Ghi trạng thái approved/denied và granted scopes
    TV->>AS: Poll token endpoint theo interval
    alt Đã chấp thuận và code còn hiệu lực
        AS-->>TV: Access token, scope được cấp; refresh token nếu policy cho phép
        TV->>API: Authorization: Bearer access token
        API->>API: Verify issuer/audience/scope/tenant/owner
        API-->>TV: Chỉ dữ liệu được phép
    else Từ chối hoặc hết hạn
        AS-->>TV: access_denied hoặc expired_token
        TV-->>U: Thông báo không kết nối thành công
    end
~~~

Các bước xảy ra **bất đồng bộ**: TV có thể polling nhiều lần trong khi user vẫn đang nhập mã hoặc cân nhắc consent. Mốc “AS đã chấp thuận” **không đồng nghĩa token được push qua browser về TV**; thiết bị chính tiếp tục lấy token thông qua **token endpoint** với `device_code`.

## 5. Thiết bị xin device authorization như thế nào?

### Device authorization endpoint

Theo RFC 8628, Client bắt đầu bằng request dạng `application/x-www-form-urlencoded` đến device authorization endpoint của AS:

~~~http
POST /device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=orders-tv&scope=orders%3Aread
~~~

`client_id` xác định Client đã đăng ký. Nhiều TV/thiết bị hạn chế nhập liệu là **public client**, nên **không được giả định client ID là bí mật** hoặc nhúng shared client secret rồi xem thiết bị là confidential. Nếu Client thực sự là confidential và AS yêu cầu, nó phải thực hiện client authentication phù hợp; không phải mọi TV có thể bảo vệ credential.

Nếu AS hỗ trợ **Resource Indicators (RFC 8707)** cho profile triển khai, request có thể thêm:

~~~http
POST /device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=orders-tv&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

`resource` là **phần mở rộng khi AS hỗ trợ**, không phải tham số bắt buộc của RFC 8628. Cách ánh xạ `resource` thành claim `aud` hoặc metadata introspection do AS/profile quyết định.

### Response từ AS

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "<HIGH_ENTROPY_DEVICE_CODE_FOR_DEVICE_ONLY>",
  "user_code": "ABCD-EFGH",
  "verification_uri": "https://auth.example.test/activate",
  "verification_uri_complete": "https://auth.example.test/activate?user_code=ABCD-EFGH",
  "expires_in": 600,
  "interval": 5
}
~~~

Các giá trị chỉ là **placeholder**, user code minh họa. AS tự sinh mã theo chính sách. `verification_uri_complete` là **tùy chọn**, còn `verification_uri`, `device_code`, `user_code` và `expires_in` là những thành phần chính của phản hồi device authorization; `interval` cũng có thể không xuất hiện.

| Trường | Ai dùng? | Ý nghĩa bảo mật |
|---|---|---|
| **`device_code`** | **Thiết bị chính** gửi đến token endpoint. | Mã dài khó đoán, phải giữ bí mật khỏi người dùng/website bên ngoài; không hiển thị công khai trên TV/QR. |
| **`user_code`** | Người dùng nhập/xác nhận ở thiết bị thứ hai. | Mã ngắn dễ nhập, cần giới hạn thử sai và TTL vì entropy thấp hơn. |
| **`verification_uri`** | User mở website của AS. | URL cần trỏ đến đúng AS đáng tin, dùng HTTPS khi triển khai. |
| **`verification_uri_complete`** | User mở/scan QR có sẵn mã. | Giảm nhập liệu, **không được bỏ bước xác nhận đúng thiết bị/mã và consent**. |
| **`expires_in`** | TV và AS. | Số giây code còn giá trị từ khi response được cấp; không được polling vô hạn. |
| **`interval`** | TV. | Khoảng cách polling tối thiểu theo giây nếu AS cung cấp. |

**Không đưa `device_code` vào QR code hoặc màn hình xác minh.** `device_code` là credential dùng để nhận token sau khi user hoàn tất ủy quyền; `user_code` chỉ giúp liên kết phiên user trên thiết bị thứ hai với giao dịch đang chờ.

## 6. Mã nào được hiển thị trên TV và trên điện thoại?

TV thường hiển thị:

~~~text
KẾT NỐI ORDERS VIEWER

1. Trên điện thoại hoặc máy tính, mở:
   https://auth.example.test/activate

2. Nhập mã:
   ABCD-EFGH

3. Kiểm tra tên ứng dụng, tài khoản và quyền trên trang xác minh.
   Chỉ chọn Cho phép nếu bạn đang tự kết nối TV này.

Mã có thời hạn. Nếu quá hạn, chọn Bắt đầu lại.
~~~

### Với QR hoặc `verification_uri_complete`

TV cũng có thể hiển thị **QR mở `verification_uri_complete`**, giúp user không phải nhập `user_code`. Nhưng sau khi mở link, AS **nên hiển thị hoặc yêu cầu user xác nhận mã** và bảo đảm người dùng nhận ra thiết bị/ứng dụng đang ghép nối. RFC 8628 đặt trọng tâm vào việc giảm remote phishing khi dùng verification URI hoàn chỉnh: không biến click QR thành **consent âm thầm**.

### Các điều cần kiểm tra

1. **Đúng website AS:** domain, HTTPS, chứng chỉ và tên tổ chức theo nguồn đáng tin; không làm theo đường link giả từ email/tin nhắn.
2. **Đúng mã:** mã trên trang xác minh tương ứng với mã trên thiết bị user đang kết nối.
3. **Đúng ứng dụng và thiết bị:** thông tin hiển thị phải dựa trên registration/transaction được AS xác minh; device name do client tự khai **không phải bằng chứng danh tính mạnh**.
4. **Đúng account/tenant:** điện thoại có thể đang đăng nhập vào tài khoản khác với tài khoản user muốn dùng trên TV.
5. **Đúng quyền:** đọc kỹ scope, thời gian duy trì phiên, dữ liệu và cách thu hồi trước khi chấp thuận.

**Đừng nhập mã mà người lạ gửi qua chat hoặc đọc qua điện thoại để “xác minh tài khoản”.** Một mã như vậy có thể thuộc phiên do attacker tự khởi tạo, khiến token được cấp **cho thiết bị của attacker** sau khi nạn nhân chấp thuận.

## 7. Trang scope consent trên thiết bị thứ hai phải hiển thị những gì?

**Trang consent thuộc AS**, không chỉ là modal bên trong app TV. AS cần kiểm tra transaction trước khi cho user quyết định.

### Giao diện minh họa

~~~text
XÁC NHẬN KẾT NỐI THIẾT BỊ

Bạn đang đăng nhập: user-123@tenant-a
Mã thiết bị:          ABCD-EFGH
Ứng dụng yêu cầu:     Orders Viewer for TV
Nguồn ứng dụng:       Thông tin đăng ký đã được AS kiểm tra
Tài nguyên:           Orders API

Ứng dụng muốn:
  ✓ Xem các đơn hàng mà tài khoản của bạn được phép đọc
    (orders:read)

Ứng dụng KHÔNG được cấp:
  ✗ Chỉnh sửa/hủy đơn (orders:write)
  ✗ Hoàn tiền (payments:refund)

Không có quyền truy cập ngoại tuyến dài hạn
trừ khi được nêu riêng và AS thực sự cấp.

Chỉ tiếp tục nếu bạn đang kết nối TV đã hiển thị mã này.

   [Từ chối]       [Cho phép đọc đơn hàng]
~~~

Đây là **mẫu nội dung giao diện**, không khẳng định một Client bất kỳ đã được “xác minh” trên thực tế. Nếu AS không có căn cứ kiểm chứng nhà phát triển, không nên tự hiển thị nhãn đáng tin.

### Các yếu tố bắt buộc phải suy xét

| Điều cần hiển thị | Câu hỏi người dùng cần trả lời | Rủi ro nếu bỏ qua |
|---|---|---|
| **Tên và nguồn Client** | “Tôi đang kết nối app nào?” | Consent phishing qua app giả danh. |
| **Mã hoặc thông tin đối chiếu** | “Đây có phải TV tôi vừa khởi tạo không?” | Cấp quyền cho phiên của attacker. |
| **Account đang đăng nhập** | “Tôi dùng đúng tài khoản/tenant chứ?” | Kết nối nhầm account hoặc lộ dữ liệu tổ chức. |
| **Resource/API** | “Ứng dụng sẽ truy cập loại dữ liệu nào?” | Giấu yêu cầu sang RS khác. |
| **Scope theo hành động** | “Đọc, ghi, xóa, xuất hay thanh toán?” | Nhầm quyền nhạy cảm với quyền xem thông thường. |
| **Quyền offline/duy trì truy cập** | “Thiết bị còn truy cập khi tôi rời điện thoại không?” | Chấp thuận refresh token mà không hiểu thời gian duy trì. |
| **Từ chối/thu hồi** | “Tôi có thể không cho phép hoặc ngắt kết nối sau này không?” | Consent không có lựa chọn thực chất. |

### Không chỉ hiển thị mã scope

`orders:read`, `reports:export` hoặc `offline_access` có thể không dễ hiểu. Dùng mô tả **theo hành động**, chẳng hạn:

- `orders:read` → “Xem những đơn hàng mà bạn được phép xem.”
- `orders:write` → “Tạo hoặc chỉnh sửa những đơn hàng trong phạm vi quyền của bạn.”
- `reports:export` → “Xuất báo cáo có chứa dữ liệu mà tài khoản được cấp quyền.”
- `offline_access` (nếu dùng OIDC theo profile) → “Cho phép ứng dụng duy trì quyền truy cập khi bạn không đang dùng thiết bị xác minh.”

Mô tả phải do **AS/RS policy** kiểm soát, không được hoàn toàn dựa vào văn bản tùy ý của Client. Mã scope giống nhau ở các API khác nhau không tự đồng nghĩa cùng quyền.

## 8. Scope được cấp không chỉ phụ thuộc nút “Cho phép”

Người dùng **không có quyền tạo thêm scope** cho Client bằng consent. Authorization Server cần kiểm tra:

~~~text
Requested scopes       = {orders:read, orders:write, reports:export}
Registered client      = {orders:read, orders:write}
User entitlement       = {orders:read, orders:write}
Tenant policy          = {orders:read}
Resource supported     = {orders:read, orders:write}
Approved by user       = {orders:read}

Effective grant:
  {orders:read}, nếu AS cho phép cấp subset này.

Không cấp:
  orders:write    (bị tenant policy/user approval giới hạn)
  reports:export  (ngoài registration/resource)
~~~

**Policy có thể từ chối toàn bộ giao dịch** nếu Client xin scope không được phép hoặc AS không hỗ trợ partial grant. Nếu hỗ trợ giảm scope, token được cấp phải phản ánh **granted scopes**, không âm thầm chép tất cả requested scopes vào access token.

### Bảng phân biệt các quyết định

| Kiểm soát | Câu hỏi | Bên chịu trách nhiệm |
|---|---|---|
| Client registration | Client có được dùng device grant, xin API và scope đó không? | AS. |
| Client type/authentication | Thiết bị public hay confidential, có cần xác thực client? | AS theo registration. |
| User authentication | Account trên điện thoại là ai, có đủ mức xác thực chưa? | AS. |
| User/tenant policy | Chủ thể có được phép cấp/ủy quyền scope này tại tenant đó không? | AS và nguồn entitlement tin cậy. |
| User consent | User có thực sự chấp thuận client này dùng quyền đã mô tả không? | AS trên verification flow. |
| Token issuance | Audience, scope, TTL, refresh grant, binding nào được cấp? | AS. |
| Object authorization | Người dùng/client có được đọc order cụ thể không? | RS. |

### Consent ≠ authentication ≠ authorization

- **Đăng nhập thành công:** AS biết chủ thể đang tương tác trên điện thoại.
- **Consent thành công:** user cho phép Client sử dụng những quyền được mô tả trong giới hạn policy.
- **Token được cấp:** AS xác định **phạm vi thực tế** và bảo vệ token.
- **API cho phép:** RS xác minh token và policy của bản ghi tại thời điểm gọi.

Không lược bỏ bất kỳ bước nào chỉ vì TV đã hiện đúng mã.

## 9. Consent đã lưu, consent bổ sung và admin consent

### Có phải lần kết nối nào cũng hỏi lại?

Không nhất thiết. AS có thể đã có **grant/consent** hợp lệ cho cùng user, client, resource, tenant và scope, hoặc tổ chức đã có phê duyệt phù hợp. Tuy nhiên **liên kết một thiết bị mới** vẫn có thể cần xác nhận thiết bị và giao dịch theo risk policy — không nên bỏ qua bước này chỉ vì user từng consent cho app.

| Trường hợp | Hướng xử lý có thể có |
|---|---|
| User từng cấp `orders:read` cho cùng client/resource/tenant | AS có thể tái sử dụng grant trong giới hạn chính sách; vẫn xác minh pairing mới. |
| TV lần này xin thêm `orders:write` | AS phải xét quyền mới và xin quyết định bổ sung hoặc từ chối. |
| Consent cũ đã bị thu hồi | Không tái sử dụng grant cũ, phải xét chính sách mới. |
| Tenant mới hoặc tài khoản khác | Không tự chuyển grant của user/tenant cũ. |
| Tenant admin cấm app | User không thể bỏ qua bằng cách tự chọn Cho phép. |
| Admin đã phê duyệt một số scope | AS có thể giảm tương tác, nhưng vẫn phải giới hạn theo resource/user và policy. |

### Incremental consent

Client nên xin **scope tối thiểu** lúc ghép nối, ví dụ `orders:read`. Nếu user bật tính năng quản trị sau này và cần `orders:write`, app phải khởi tạo quyết định authorization mới theo cách AS hỗ trợ.

**Không sửa phạm vi của token đang có** bằng cách đổi payload JWT hoặc thêm scope vào request API. Access token đã cấp không tự tăng quyền; quyết định mới phải đi qua AS.

### Partial consent

Nếu AS cho user chọn từng scope, ví dụ:

~~~text
[x] Xem đơn hàng       orders:read
[ ] Sửa đơn hàng       orders:write
~~~

AS phải ràng buộc lựa chọn **với transaction đã lưu**. Không tin form body chứa `approved_scopes=admin` mà không đối chiếu requested scopes, registration, user/tenant entitlement và policy hiện hành.

Nếu AS không hỗ trợ partial consent, giao diện nên nói rõ người dùng chỉ có thể **cho phép toàn bộ tập hợp lệ** hoặc **từ chối**, không giả tạo checkbox rồi vẫn phát mọi scope.

## 10. Gắn consent với đúng user code và đúng thiết bị

Đây là phần bảo mật đặc trưng của Device Authorization Grant. AS phải biết **phiên nào đang chờ người dùng xác minh**, chứ không nhận một nút “Allow” tự do làm bằng chứng.

### Giao dịch được lưu phía AS

~~~text
device_authorization_transaction:
    transaction_id = internal-id
    device_code_hash_or_verifier = protected, high-entropy
    user_code_hash_or_lookup = protected, rate-limited
    client_id = orders-tv
    requested_resource = orders-api
    requested_scope = {orders:read}
    created_at = timestamp
    expires_at = short TTL
    poll_interval = 5 seconds
    state = pending
    approved_subject = null
    approved_tenant = null
    granted_scope = empty
    consumed = false
~~~

Schema trên chỉ là **mô hình dữ liệu minh họa**. Cách lưu hash/lookup code phụ thuộc AS; user code có entropy thấp hơn device code nên phải có **rate limiting mạnh**, không mặc nhiên dùng một hash đơn giản thay chống brute force.

### State machine

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Device authorization request
    Pending --> Pending: Poll authorization_pending
    Pending --> Approved: User xác thực, xác nhận mã, consent hợp lệ
    Pending --> Denied: User từ chối hoặc policy cấm
    Pending --> Expired: TTL hết
    Approved --> Consumed: Device lấy token thành công một lần
    Approved --> Expired: Hết hạn trước khi nhận token (theo policy)
    Denied --> [*]
    Expired --> [*]
    Consumed --> [*]
~~~

AS cần bảo đảm **authorization decision và việc tiêu thụ device code có tính nhất quán**, tránh phát nhiều kết quả không tương thích do hai polling request đồng thời.

### Các kiểm tra khi user nhấn Cho phép

1. `user_code` đúng với **transaction đang pending**, còn hạn và chưa bị sử dụng.
2. User đã xác thực đủ theo chính sách và đồng ý trong **phiên AS phù hợp**.
3. **Client ID và metadata** đến từ registration đáng tin, không được caller sửa bằng form POST.
4. User đang chọn đúng **account/tenant** và resource.
5. **Approved scopes** nằm trong requested scopes và quyền được AS/policy cho phép.
6. Website AS đã bảo vệ thao tác xác nhận bằng **CSRF defense** phù hợp.
7. Quyết định được ghi **atomically**, gắn subject/tenant/granted scope với device authorization transaction.
8. Không chuyển token trực tiếp vào query URL của thiết bị thứ hai hoặc sang website ngoài AS.

### Mã giả cho quyết định consent

~~~text
approveDeviceTransaction(verificationSession, userCode, selectedScopes):
    require authenticated AS user session
    require CSRF and transaction integrity checks

    tx = lookupPendingTransactionByUserCode(userCode)
    if tx missing, expired, denied, or alreadyConsumed:
        reject

    client = trustedClientRegistry.find(tx.clientId)
    if client missing or not allowed device_authorization_grant:
        reject

    policy = evaluateCurrentAuthorizationPolicy(
        user=verificationSession.subject,
        tenant=verificationSession.tenant,
        client=client,
        resource=tx.requestedResource,
        scopes=tx.requestedScopes
    )
    if policy denies:
        reject

    approved = validateSelection(selectedScopes)
    if not subset(approved, tx.requestedScopes):
        reject
    if not subset(approved, policy.allowedScopes):
        reject
    if approved empty and policy requires nonempty grant:
        reject

    showOrVerifyClientAndUserCodeConfirmation(tx, client)
    atomicallyMarkApproved(
        tx, subject=verificationSession.subject,
        tenant=verificationSession.tenant,
        grantedScopes=approved
    )
~~~

Đây là **pseudocode bảo mật**, không phải code đầy đủ của Authorization Server. Đặc biệt, **không để `selectedScopes` hoặc `client_id` từ browser thay transaction gốc** và không coi text tên thiết bị do Client tự khai là chứng nhận thiết bị đáng tin.

## 11. Polling token endpoint trong lúc user đang cân nhắc consent

TV thường không nhận authorization response redirect. Thay vào đó, nó **poll token endpoint** bằng device code.

### Request

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=<DEVICE_CODE>&client_id=orders-tv
~~~

Giá trị `grant_type` sau URL decoding là **`urn:ietf:params:oauth:grant-type:device_code`**. Public client cung cấp `client_id`; confidential client phải xác thực tại token endpoint theo phương thức đã đăng ký và quy tắc RFC 8628/OAuth hiện hành.

**Thiết bị không gửi `user_code` để lấy token.** `user_code` phục vụ liên kết người dùng ở verification endpoint. `device_code` là credential cho **đúng giao dịch** do thiết bị đã khởi tạo.

### Khi chưa có quyết định

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "authorization_pending"
}
~~~

Thiết bị **tiếp tục chờ** và chỉ poll lại khi đến khoảng thời gian cho phép; **không** thử đăng nhập hộ user hoặc tự chấp thuận scope.

### Các trạng thái cần xử lý

| Lỗi từ token endpoint | Ý nghĩa | Hành vi thiết bị |
|---|---|---|
| **`authorization_pending`** | User chưa hoàn thành authorization. | Tiếp tục polling theo `interval`, có giới hạn thời gian. |
| **`slow_down`** | Client polling quá nhanh hoặc AS yêu cầu giảm tải. | **Tăng interval ít nhất 5 giây** cho các lần polling kế tiếp theo RFC 8628. |
| **`access_denied`** | User từ chối grant. | **Dừng** polling, không có access token; thông báo rõ, không gây áp lực. |
| **`expired_token`** | Device code đã hết hạn. | **Dừng**, yêu cầu user khởi tạo giao dịch mới nếu muốn. |
| **Lỗi client authentication/invalid request** | Client không hợp lệ hoặc request sai. | Dừng và chẩn đoán cấu hình; không tự bỏ xác thực. |
| **Lỗi mạng/timeout** | Có thể AS không phản hồi. | Lùi tần suất polling, thường exponential backoff, không vòng lặp dồn dập. |

### Interval và thời hạn

- Nếu AS trả `interval`, Client **không polling nhanh hơn khoảng đó**.
- Nếu không có `interval`, RFC 8628 quy định **mặc định 5 giây**.
- Mỗi khi nhận `slow_down`, tăng khoảng polling **thêm 5 giây** theo đặc tả cho các lần tiếp theo; không tự reset về interval ban đầu ngay.
- Nếu gặp network timeout, nên **giảm tần suất** theo backoff phù hợp, ví dụ tăng khoảng chờ luỹ tiến.
- Dừng khi hết `expires_in` hoặc AS trả lỗi kết thúc.
- Để bảo vệ tài nguyên AS, tránh các TV đồng loạt poll theo một nhịp cố định; cân nhắc jitter **không làm vi phạm interval tối thiểu**.

### Vì sao polling quan trọng đối với consent?

Token endpoint không được **phát token khi trạng thái còn pending**. User đang đọc màn hình permission trên điện thoại có thể cần thời gian. `authorization_pending` là một trạng thái bình thường, không phải lỗi để TV chuyển sang **grant khác quyền rộng hơn** hoặc bỏ qua policy.

## 12. Sau khi consent, access token được cấp thế nào?

Khi AS đã xác minh user và grant phù hợp, một lần polling từ **đúng Client/device code còn hiệu lực** có thể nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN_FOR_ORDERS>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read",
  "refresh_token": "<OPTIONAL_REFRESH_TOKEN_IF_POLICY_ALLOWS>"
}
~~~

Phản hồi là **minh họa**; `refresh_token` có thể hoàn toàn vắng mặt. `scope` trong OAuth token response bắt buộc phản ánh **sự khác biệt với scope request** nếu granted scope khác requested scope, và có thể lược bỏ nếu không thay đổi. Không được xem giá trị trong request cũ là bằng chứng được cấp toàn bộ scope.

### JWT access token minh họa

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "orders-tv",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456600,
  "tenant_id": "tenant-a"
}
~~~

Đây chỉ là **claims minh họa**. Access token có thể là **JWT được ký** hoặc **opaque string**. Các claim cụ thể tùy AS/profile; không giả định mọi device token đều có trường `device_id`, `tenant_id` hoặc định dạng JWT. Với opaque token, RS có thể tra cứu metadata qua **token introspection (RFC 7662)**.

### Đúng resource/audience

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS>
~~~

Orders API cần:

1. Xác minh issuer, signature/JWKS hoặc opaque introspection đáng tin.
2. Kiểm tra token dành cho **`aud=orders-api`**, không dùng OIDC ID token hay refresh token làm access token.
3. Kiểm tra `exp`, `nbf`, loại token, trạng thái thu hồi và sender proof khi có.
4. Kiểm tra `orders:read` thực sự có trong **granted scope**.
5. Kiểm tra quyền user/client trên **từng order, tenant, thuộc tính dữ liệu**.

**Mã `user_code` không được trình tới Orders API.** Nó chỉ phục vụ xác minh/ghép nối; API cần access token được cấp đúng giao thức.

## 13. Refresh token và `offline_access` trên thiết bị dùng lâu dài

Một TV có thể cần duy trì đăng nhập nhiều ngày. Tuy nhiên, việc user đồng ý kết nối **không đồng nghĩa refresh token được cấp vô hạn**.

### Các câu hỏi cần nêu rõ tại consent

- Ứng dụng chỉ dùng quyền khi người dùng đang ở trước TV hay còn truy cập **sau khi user rời điện thoại**?
- TV là **thiết bị cá nhân** hay thiết bị chung trong phòng họp/khách sạn?
- Có cần lưu token dài hạn không; có lựa chọn **không lưu phiên** không?
- User có thể xem **danh sách thiết bị đã kết nối** và ngắt kết nối từ tài khoản không?
- Quyền có bị giới hạn theo tenant, loại dữ liệu hoặc thời hạn tổ chức không?

### OIDC và `offline_access`

Nếu AS/Client sử dụng **OpenID Connect**, scope `offline_access` có ý nghĩa riêng theo OIDC và chính sách OP. Ví dụ request:

~~~text
scope=openid orders:read offline_access
~~~

**Không coi `offline_access` là một scope được mọi OAuth 2.0 AS hỗ trợ mặc định.** User consent hoặc admin policy liên quan có thể được yêu cầu, nhưng việc Client xin scope này **không bảo đảm** refresh token sẽ xuất hiện trong phản hồi.

### Refresh token cần bảo vệ ở đâu?

Với TV/public client, refresh token là credential rất nhạy cảm. Các nguyên tắc:

1. Không hiển thị refresh token qua UI, QR, user code, URL hoặc log.
2. Dùng secure storage/keystore có sẵn trên nền tảng nếu phù hợp; hạn chế export và backup token.
3. Áp dụng **refresh token rotation** hoặc **sender-constraining** cho public client theo BCP/profile và khả năng AS.
4. Phát hiện reuse, thu hồi grant/token family khi có dấu hiệu chiếm đoạt theo policy.
5. Token mới không được vượt scope, resource hoặc quyền của grant ban đầu.
6. Có quy trình **logout, unlink device, revoke grant** và làm rõ hành vi khi TV bị mất/bán/chuyển chủ.

### Không lưu thông tin xác thực user trên TV

Device Authorization được thiết kế để tránh việc user phải nhập mật khẩu trên TV. **Không thu password/MFA recovery code trong app TV** chỉ để tạo “phiên bền vững”; hãy dùng token đúng mục đích, lưu an toàn và cho user chủ động thu hồi quyền.

## 14. Device-code phishing: khi trang AS thật vẫn có thể bị lợi dụng

Đây là rủi ro đặc biệt của Device Authorization Grant.

### Kịch bản giả mạo

1. Attacker khởi tạo **device authorization transaction trên thiết bị/ứng dụng họ kiểm soát**, nhận một `user_code` hợp lệ và `device_code` bí mật.
2. Attacker gửi thông điệp cho nạn nhân như: “Để xác minh tài khoản, vào website này và nhập mã ABCD-EFGH.”
3. Nạn nhân mở **website AS thật**, đăng nhập tài khoản của họ và nhập mã do attacker cung cấp.
4. Nếu nạn nhân chấp thuận quyền được hỏi, AS đánh dấu **giao dịch của attacker** là authorized.
5. **Attacker dùng `device_code` của mình** để polling token endpoint và có thể nhận access token trong phạm vi grant.

~~~mermaid
sequenceDiagram
    participant Attacker as Thiết bị attacker
    participant AS as Authorization Server thật
    participant V as Nạn nhân / điện thoại
    Attacker->>AS: Tạo device flow cho client/phiên attacker
    AS-->>Attacker: device_code (bí mật) + user_code
    Attacker-->>V: Dụ nhập user_code qua tin nhắn
    V->>AS: Mở trang xác minh AS thật và nhập mã
    AS-->>V: Hiển thị Client, scope và ngữ cảnh
    V->>AS: Nếu bị lừa: chấp thuận
    AS->>AS: Đánh dấu transaction của attacker được cấp quyền
    Attacker->>AS: Poll bằng device_code đang giữ
    AS-->>Attacker: Token nếu không có biện pháp khác chặn
~~~

**Trang đăng nhập đúng domain không bảo đảm an toàn** nếu user đang phê duyệt **giao dịch do attacker khởi tạo**. Đây là **lừa đảo cấp quyền OAuth**, không nhất thiết yêu cầu lấy mật khẩu.

### Phòng ngừa cho người dùng

- Chỉ nhập mã sau khi **chính bạn vừa khởi tạo kết nối trên thiết bị mình nhận ra**.
- Đối chiếu mã trên màn hình AS với mã đang hiển thị trên TV thật.
- Xác minh tên ứng dụng, dữ liệu được xin, tài khoản/tenant và sự cần thiết của quyền.
- **Không làm theo mã thiết bị qua email, chat, cuộc gọi hoặc thông báo lạ**, kể cả khi người gửi khẳng định là hỗ trợ kỹ thuật.
- Dùng trang “Thiết bị/ứng dụng đã kết nối” để rút quyền nếu đã phê duyệt nhầm.

### Phòng ngừa cho AS và sản phẩm

1. Hiển thị rõ **đây là kết nối một thiết bị/ứng dụng khác**, không phải bước xác minh bảo mật thông thường.
2. Xác minh và trình bày **client identity** từ registration tin cậy; giới hạn đăng ký client có khả năng lạm dụng.
3. Yêu cầu user xác nhận mã/thiết bị ngay cả khi vào từ `verification_uri_complete`/QR theo UX phù hợp.
4. Áp dụng **rate limiting** cho user-code lookup, token endpoint và các hoạt động đáng ngờ.
5. Hạn chế scope nhạy cảm/admin/financial action, dùng step-up authentication hoặc admin approval theo policy.
6. Gắn grant với đúng user/tenant/resource, ghi audit và hỗ trợ revoke nhanh.
7. Không cho Client tùy ý thay mô tả scope hoặc tên app trên màn hình AS để giả danh.
8. Có cảnh báo/hướng dẫn khi user đi từ link không rõ nguồn hoặc thấy giao dịch chưa chủ động khởi tạo.

**Xác nhận mã chỉ giảm nhầm pairing**; nó không tự ngăn attacker gửi cho nạn nhân một mã có thật của phiên attacker. Tín hiệu quan trọng là **user có thực sự chủ động bắt đầu kết nối thiết bị đang hiện mã đó hay không**.

## 15. Lộ user code, brute force và token polling abuse

### `user_code` được thiết kế để người dùng nhập

Mã này ngắn hơn device code để người dùng nhập bằng bàn phím điện thoại. Vì thế:

- Không dùng nó như secret có entropy cao.
- AS cần **giới hạn thử mã**, thời hạn ngắn, khóa/tăng trễ tạm thời khi bị đoán nhiều lần.
- Không cho user-code lookup tiết lộ thông tin tài khoản, scope nhạy cảm, danh tính user hoặc trạng thái quá chi tiết cho người chưa xác thực.
- Không chấp nhận một user code đã hết hạn/đã hoàn tất như một transaction mới.

### `device_code` có mục đích khác

`device_code` là mã dài khó đoán dành cho Client và AS, dùng tại token endpoint. Phải:

- Chỉ đưa tới **thiết bị Client** đã khởi tạo, không nhúng vào QR hoặc màn hình hướng dẫn người dùng.
- Không in vào access logs, crash logs, support tickets, telemetry hoặc browser history.
- Ràng buộc với client registration, trạng thái giao dịch, TTL và chính sách xác thực nếu có.
- Chỉ cho phép **lấy token theo kết quả đã được user/AS chấp thuận**; chống dùng lại không đúng cách.

### Polling quá nhanh

Một tập hợp thiết bị lỗi có thể tạo lượng lớn request tới AS, dù không có attacker. Ngoài `interval`/`slow_down`, AS cần rate limiting, quota, tối ưu lookup và phát hiện bất thường. Client cần dừng khi giao dịch kết thúc; không retry vô hạn mỗi 100 ms.

## 16. Consent trong môi trường nhiều user, nhiều tenant và thiết bị chung

### Đúng user trên điện thoại nhưng TV thuộc ai?

TV có thể đặt ở khách sạn hoặc phòng họp. Điện thoại đăng nhập `user-123@tenant-a`, nhưng TV nằm trong không gian công cộng. Nếu app có thể giữ refresh token, việc bấm “Cho phép” có thể vô tình mở **phiên đăng nhập lâu dài trên thiết bị chung**.

Biện pháp cần cân nhắc:

1. Hiển thị account/tenant và mô tả **thiết bị nào đang nhận quyền**.
2. Cho user biết phiên có duy trì sau khi họ rời đi không; cân nhắc short-lived session/no refresh trên thiết bị chung.
3. Có nút **Ngắt kết nối ngay trên TV** và trên trang quản lý tài khoản.
4. Không hiển thị trường dữ liệu nhạy cảm trên màn hình chung nếu không có xác nhận bổ sung.
5. Tuân thủ tenant policy và data classification dù user consent.

### Một scope hợp lệ vẫn có thể vượt quyền trên bản ghi

~~~text
Trusted access token:
    sub       = user-123
    client_id = orders-tv
    aud       = orders-api
    scope     = orders:read
    tenant    = tenant-a

Requested order:
    id        = order-999
    tenant    = tenant-b
    owner     = user-999

Result:
    DENY, trừ khi có quyền liên tenant/owner override hợp lệ.
~~~

Không thể lấy `orders:read` rồi kết luận user có quyền đọc **mọi order**. Resource Server phải thực thi owner/tenant và chính sách nghiệp vụ theo dữ liệu thật.

### Device không nhất thiết là actor có quyền quản trị

Một client là TV app có thể chỉ được đăng ký quyền đọc. Nếu nó cố xin `payments:refund`, AS nên từ chối theo policy dù người dùng đang có role admin. **Consent user không làm client tự động có khả năng sử dụng toàn bộ quyền của user.**

### Một Client, nhiều thiết bị vật lý

Hai TV cài cùng app có thể chia sẻ `client_id=orders-tv` nhưng **mỗi phiên device authorization phải có mã và trạng thái riêng**. Nếu hệ thống cần phân biệt device nào được cấp quyền, phải quản lý device identity/registration **theo cơ chế đáng tin**, không dựa vào một query `device_id=meeting-room-tv` do caller tự khai.

## 17. Java: mô hình client polling bảo đảm consent chưa xong thì chưa có token

Đoạn mã dưới đây minh họa **logic điều khiển polling**, không tự triển khai toàn bộ OAuth client/AS. Trong triển khai thật nên dùng client library đáng tin, endpoint metadata và cơ chế xử lý JSON/TLS được kiểm chứng.

### Mô hình dữ liệu

~~~java
import java.time.Duration;
import java.time.Instant;

record DeviceGrant(
    String deviceCode,
    String userCode,
    String verificationUri,
    Instant expiresAt,
    Duration interval
) {
    DeviceGrant {
        if (deviceCode == null || deviceCode.isBlank()) {
            throw new IllegalArgumentException("Missing device code");
        }
        if (userCode == null || userCode.isBlank()) {
            throw new IllegalArgumentException("Missing user code");
        }
        if (interval == null || interval.compareTo(Duration.ZERO) <= 0) {
            interval = Duration.ofSeconds(5);
        }
    }
}
~~~

Ví dụ giả định bước trước đã nhận `device_code`/`user_code`/`verification_uri` và `expires_in` từ AS, tính `expiresAt` theo đồng hồ thời gian đáng tin. **Không đặt toàn bộ response hoặc device code trong log**.

### Xử lý các trạng thái polling

~~~java
import java.time.Duration;

enum DevicePollDecision {
    WAIT, RETRY_SLOWER, SUCCESS, DENIED, EXPIRED, FAIL
}

record DevicePollState(Duration minInterval, DevicePollDecision decision) {
    static DevicePollState initial(Duration serverInterval) {
        Duration interval = serverInterval == null
                ? Duration.ofSeconds(5) : serverInterval;
        if (interval.compareTo(Duration.ZERO) <= 0) {
            throw new IllegalArgumentException("Invalid polling interval");
        }
        return new DevicePollState(interval, DevicePollDecision.WAIT);
    }

    DevicePollState onOAuthError(String error) {
        return switch (error) {
            case "authorization_pending" ->
                    new DevicePollState(minInterval, DevicePollDecision.WAIT);
            case "slow_down" ->
                    new DevicePollState(
                            minInterval.plusSeconds(5),
                            DevicePollDecision.RETRY_SLOWER);
            case "access_denied" ->
                    new DevicePollState(minInterval, DevicePollDecision.DENIED);
            case "expired_token" ->
                    new DevicePollState(minInterval, DevicePollDecision.EXPIRED);
            default ->
                    new DevicePollState(minInterval, DevicePollDecision.FAIL);
        };
    }

    DevicePollState onSuccess() {
        return new DevicePollState(minInterval, DevicePollDecision.SUCCESS);
    }
}
~~~

Đây là **trạng thái tối thiểu**, chưa có HTTP request, scheduler, deadline, retry/jitter, authentication hay token validation. Phần orchestrator phải bảo đảm:

~~~text
deviceGrant = requestDeviceAuthorizationFromTrustedAS()
displayVerificationInstructions(deviceGrant.verificationUri, deviceGrant.userCode)
pollState = initial(deviceGrant.interval)
deadline = deviceGrant.expiresAt

while before(deadline):
    waitAtLeast(pollState.minInterval)
    result = POST_AS_TOKEN_ENDPOINT(
        grant_type = urn:ietf:params:oauth:grant-type:device_code,
        device_code = deviceGrant.deviceCode,
        client_auth_or_client_id = configuredClientIdentity
    )
    if result.networkTimeout:
        pollState = applyNetworkBackoffWithoutViolatingMinimum(pollState)
        continue
    if result.success:
        acceptOnlyValidTokenResponseWithinExpectedGrant(result)
        stop
    pollState = pollState.onOAuthError(result.error)
    if pollState.decision in {DENIED, EXPIRED, FAIL}:
        stopAndReportAppropriateMessage()
~~~

**Quan trọng:** logic phải nhận diện lỗi network **trước** khi giả định đã có OAuth `error`; mã giả trên cố ý lược phần exception/timeout và scheduler chi tiết. Không dùng vòng lặp busy-wait, không reset `slow_down`, không cấp token ở trạng thái pending.

### Java/Spring Security trong hệ thống thực

**Spring Security Resource Server** có thể xác minh access token bằng cấu hình JWT/opaque phù hợp; đó là phần **nhận token tại API**, không phải phần thiết bị khởi tạo Device Grant. Khi xây Client TV hoặc AS, kiểm tra **phiên bản thư viện hỗ trợ Device Authorization Grant**, các endpoint cần có, cách lưu trạng thái transaction, CSRF trên verification UI và client authentication; không giả định một cấu hình `oauth2Login()` (Authorization Code) sẽ tự xử lý thiết bị polling theo RFC 8628.

## 18. Authorization Server nên kiểm thử consent trên device như thế nào?

### Ma trận kiểm thử end-to-end

Giả sử `orders-tv` được đăng ký chỉ với `orders:read` cho `orders-api`, user `user-123` thuộc tenant A. AS trả `interval=5`, `expires_in=600`.

| Kịch bản | Kết quả mong đợi | Kiểm chứng |
|---|---|---|
| TV gửi device authorization request hợp lệ | AS trả device code, user code, verification URI, TTL và interval. | Đúng RFC 8628 initiation. |
| Client không được đăng ký grant thiết bị | AS từ chối. | Grant policy. |
| Client xin `orders:write` ngoài registration | Không cấp scope đó; có thể từ chối toàn request. | Client allowed scopes. |
| User code hiển thị nhưng chưa có user xác minh | Token endpoint trả `authorization_pending`. | Không tự cấp token. |
| Device polling nhanh hơn interval | AS có thể trả `slow_down`/rate limit; client phải tăng khoảng chờ. | Polling compliance. |
| `interval` không có trong response | Client dùng mặc định 5 giây. | RFC default. |
| User nhập user code sai | AS không tiết lộ giao dịch/identity; giới hạn thử. | Chống brute force/enumeration. |
| User code hết hạn | AS từ chối xác minh; TV nhận `expired_token` khi polling. | TTL. |
| User nhập mã từ phiên khác | Không chấp thuận nhầm thiết bị. | Transaction binding. |
| User mở QR với `verification_uri_complete` | AS vẫn hiển thị/cho xác nhận đúng mã và quyền. | Chống nhầm lẫn pairing. |
| User đang ở account/tenant khác | Không tái dùng grant của account/tenant ban đầu. | Identity/tenant binding. |
| Client giả tên ứng dụng uy tín | AS dựa vào registration/verification thực và không gắn nhãn sai. | Consent phishing defense. |
| User bấm Từ chối | Token endpoint trả `access_denied`; TV dừng. | Denial respected. |
| User bấm Cho phép quyền đọc hợp lệ | AS ghi đúng user/client/resource/approved scope. | Consent grant. |
| Browser sửa form thêm `payments:refund` | AS không cấp quyền cấy thêm. | Server-side scope evaluation. |
| Form consent bị gửi lại | Không tạo hai grant/token ngoài policy. | Atomic decision. |
| Thiếu CSRF protection trên trang AS | Test đánh dấu fail/chặn request giả mạo. | Verification UI safety. |
| User đã consent cho app trước đó | AS vẫn xác minh pairing/device transaction theo policy. | No silent device linking. |
| Token response cấp ít scope hơn request | Phạm vi được trả đúng theo hợp đồng và Client chỉ dùng granted scope. | Scope downscoping. |
| Access token `aud=billing-api` gửi Orders | Orders từ chối. | Audience validation. |
| Token `orders:read` nhưng request sửa đơn | Orders từ chối, thường 403. | Scope authorization. |
| Token đọc order thuộc tenant khác | Orders từ chối. | Object/tenant authorization. |
| TV gửi `user_code` tới token endpoint thay `device_code` | AS từ chối request. | Code purpose separation. |
| Attacker đoán `device_code` | Xác suất thành công phải rất thấp, AS rate limit và ràng buộc. | Device code secrecy. |
| Hai TV có cùng client ID và flow song song | Mỗi TV chỉ nhận token cho transaction riêng. | Multi-device isolation. |
| Device code đã được dùng thành công | Không được phát lại kết quả trái policy khi reuse. | One-time/consistency. |
| User rút grant rồi TV refresh lại | AS từ chối refresh trên grant đã thu hồi. | Consent revocation. |
| JWT access token cũ vẫn còn hạn khi revoke | RS xử lý theo trạng thái/TTL thực tế, không tuyên bố revoke tức thời. | Token lifecycle. |
| TV bị mất/bán, user chọn unlink | Session/grant/token của device được vô hiệu hóa theo policy. | Device lifecycle. |
| Attacker gửi user code qua email rồi victim consent | Test tabletop phát hiện/phòng ngừa kịch bản phishing. | User-initiated consent. |
| Network timeout khi polling | Backoff, không request storm hoặc fail-open. | Availability và bảo mật. |
| AS trả `slow_down` hai lần | Khoảng chờ tăng thêm 5 giây mỗi lần, không reset. | RFC backoff. |
| Client gửi device code lên URL/log | Audit phát hiện và yêu cầu redaction. | Credential protection. |

### Kiểm thử không chỉ từ phía TV

Cần kiểm tra **ba điểm**:

1. **Thiết bị Client:** mã, UI, polling interval, lưu token, dừng/timeout/unlink.
2. **Authorization Server:** verification UI, account/tenant, consent policy, transaction atomicity, grant/tokens, rate limits.
3. **Resource Server:** issuer, audience, scope, thời hạn, sender binding, object/tenant authorization.

Một UI test “đã hiện nút Cho phép” **không chứng minh** token đã được cấp đúng scope hoặc mã từ thiết bị attacker bị ngăn lạm dụng.

## 19. Các ngộ nhận về scope consent trên device

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Có `user_code` là đã được cấp quyền.” | User code chỉ liên kết phiên xác minh. | Cần AS xác thực user, consent, policy và phát token. |
| “User nhập mã trên TV.” | Thiết bị chính thường khó nhập liệu. | User nhập/xác nhận trên **thiết bị thứ hai** qua website AS. |
| “`device_code` và `user_code` có thể dùng thay nhau.” | Device code dành token polling; user code dành user verification. | Không đưa device code ra UI/QR. |
| “TV có client ID nên đáng tin tuyệt đối.” | Client ID không phải secret. | Registration, auth nếu áp dụng, scope và code binding vẫn cần. |
| “Đăng nhập trên điện thoại là đã consent.” | Authentication chỉ xác định user. | Phải có grant/consent phù hợp và policy. |
| “Scope trên TV là scope được cấp.” | Client chỉ đề nghị quyền. | AS quyết định granted scope. |
| “User là admin thì TV được mọi scope.” | Client và tenant policy vẫn giới hạn. | Least privilege và step-up. |
| “Có `orders:read` thì TV xem mọi đơn.” | Scope không thay owner/tenant checks. | RS kiểm tra dữ liệu cụ thể. |
| “QR là bước bảo mật chắc chắn.” | QR có thể dẫn tới URL sai hoặc transaction của attacker. | AS domain, code confirmation, user-initiated pairing. |
| “`verification_uri_complete` có nghĩa bấm mở là tự approve.” | Điều này tạo nguy cơ remote phishing. | Hiển thị/kiểm tra mã và consent. |
| “TV phải polling thật nhanh để user không chờ.” | Gây request storm và vi phạm interval. | Tôn trọng `interval`/`slow_down`. |
| “Token response luôn có refresh token.” | AS/policy có thể không cấp. | Cần thiết kế offline session riêng. |
| “PKCE sẽ bảo vệ `device_code`.” | Device grant không dùng authorization code exchange theo PKCE. | Bảo vệ code, polling, client và transaction theo RFC 8628. |
| “Thu hồi consent tự xóa mọi JWT tại RS.” | JWT offline có thể còn hiệu lực đến TTL nếu không có state check. | Thu hồi grant/token và RS enforcement. |
| “Đúng issuer là đủ để nhận token.” | Token có thể dành cho RS khác. | Audience, scope, type, exp và quyền object. |

## 20. Tình huống tự luyện

**Tình huống A — Đăng nhập xong mà TV chưa có token.** TV đang polling và nhận `authorization_pending` dù user đã đăng nhập trên điện thoại. Có phải lỗi?

**Giải thích:** Chưa chắc. User authentication không nhất thiết đã hoàn thành consent; AS có thể vẫn chờ quyết định hoặc đang xử lý. TV phải tiếp tục poll trong giới hạn interval/TTL, không bỏ qua consent.

**Tình huống B — Scope bị giới hạn.** TV xin `orders:read orders:write`, nhưng Client registration chỉ cho `orders:read`. User bấm Cho phép. AS có thể cấp cả hai?

**Giải thích:** Không. AS chỉ được cấp quyền hợp lệ theo registration, user/tenant policy và consent; có thể từ chối hoặc downscope theo thiết kế.

**Tình huống C — Ai đó gửi mã qua chat.** Nạn nhân nhận “Vào website AS thật và nhập ABCD-EFGH để bảo vệ tài khoản”. Họ chưa mở TV nào. Có nên nhập mã?

**Giải thích:** Không. Mã có thể thuộc device authorization transaction của attacker. Chỉ nhập/xác nhận mã từ thiết bị do mình chủ động ghép nối, kiểm tra Client/scope trước khi cho phép.

**Tình huống D — QR tự đưa vào trang consent.** QR chứa `verification_uri_complete`, trên điện thoại trang consent hiện ngay và không cho user xem mã. Điều gì cần cân nhắc?

**Giải thích:** AS nên tạo bước xác nhận mã/thiết bị phù hợp để giảm remote phishing và tránh biến click link thành grant âm thầm. QR không thay user verification.

**Tình huống E — Chấp thuận trên tài khoản sai.** User có hai account cá nhân/doanh nghiệp; điện thoại đang đăng nhập account cá nhân, TV cần dữ liệu doanh nghiệp. Có tự chuyển quyền được không?

**Giải thích:** Không. AS xác minh subject/tenant của session đang consent, có thể yêu cầu chọn lại tài khoản; không ghép grant tenant khác chỉ dựa vào user code.

**Tình huống F — TV đặt ở phòng họp.** Người dùng đồng ý `offline_access` cho app TV dùng chung. Điểm nguy hiểm?

**Giải thích:** Nếu AS cấp refresh token, TV có thể duy trì quyền sau khi người dùng rời đi. Nên mô tả rõ thời hạn, lưu trữ, unlink và cân nhắc giới hạn/không cấp offline token cho thiết bị chung.

**Tình huống G — Poll quá nhanh.** Server đặt `interval=5`, Client gọi mỗi giây và nhận `slow_down` hai lần. Cần làm gì?

**Giải thích:** Không polling mỗi giây. Tôn trọng interval tối thiểu, sau mỗi `slow_down` tăng khoảng thêm **5 giây**, đồng thời quản lý deadline và backoff mạng.

**Tình huống H — Hết hạn.** Sau 10 phút user mới nhập user code trong khi `expires_in=600` đã qua. AS có nên cho phép transaction cũ?

**Giải thích:** Không. AS từ chối code hết hạn; TV ngừng poll và có thể khởi tạo một giao dịch mới với mã mới.

**Tình huống I — Đúng scope, sai order.** User đã consent `orders:read`, TV gọi `/orders/order-999` thuộc tenant khác. RS có được trả?

**Giải thích:** Không, trừ khi có quyền liên tenant/override rõ ràng. AS consent giới hạn grant; RS quyết định quyền trên object.

**Tình huống J — Revocation.** User unlink TV, nhưng bản sao JWT access token còn hạn. RS chỉ verify chữ ký/`exp`. Token có thể vẫn dùng?

**Giải thích:** Có thể. Cần thời hạn phù hợp và cơ chế RS biết trạng thái thu hồi/entitlement nếu nghiệp vụ yêu cầu chặn sớm.

**Tình huống K — Device code xuất hiện trong QR.** Developer thay vì user code đã đưa cả device code vào QR để “tiện debug”. Có ổn không?

**Giải thích:** Không. Ai có device code có thể thử lấy token sau khi người dùng chấp thuận. QR chỉ nên phục vụ mở verification URI/có thể mang user code, **không lộ device code**.

**Tình huống L — Một TV bị mất.** User đã ghép nối trước đó, TV chứa refresh token. Cần xử lý gì?

**Giải thích:** Cho user ngắt liên kết, thu hồi grant/refresh token và session/device credential liên quan, kiểm tra token đã cấp, đánh giá TTL/sender-binding và áp dụng bảo vệ thiết bị.

## Checklist triển khai Scope consent trên device

1. **Chọn đúng grant:** Device Authorization (RFC 8628) cho thiết bị hạn chế nhập liệu cần user authorization; không dùng Client Credentials để giả quyền user.
2. **Đăng ký Client và quyền tối thiểu:** client type, grant được phép, resource/audience, scope, tenant policy và trạng thái ứng dụng.
3. **Xin mã đúng endpoint:** device authorization request qua HTTPS, nhận `device_code`, `user_code`, verification URI, TTL và interval.
4. **Bảo vệ hai loại mã:** device code khó đoán và chỉ cho thiết bị/AS; user code dễ nhập nhưng rate limited, TTL ngắn, không dùng làm access token.
5. **Hướng dẫn pairing rõ ràng:** đúng domain AS, mã trên TV, QR/verification URI, tránh link lạ.
6. **Thiết kế consent ở AS:** hiển thị Client, user/account/tenant, resource, scope bằng ngôn ngữ người dùng hiểu, quyền offline và lựa chọn Từ chối.
7. **Kiểm tra transaction binding:** user code → đúng device request; chống sửa client/scope qua form, CSRF, atomic decision và expiry.
8. **Chỉ cấp quyền được phép:** scope không vượt Client registration, user entitlement, tenant policy, resource và approval; quản lý partial/incremental consent đúng profile.
9. **Polling theo RFC:** `authorization_pending`, `slow_down` (+5 giây), `access_denied`, `expired_token`, default `interval=5`, network backoff và deadline.
10. **Phát token đúng scope/audience:** AS quyết định token type/TTL/refresh; TV không giả định mọi scope đã yêu cầu đều được cấp.
11. **RS kiểm tra quyền:** issuer, signature/introspection, audience, exp/nbf, scope, sender proof khi có, tenant và object authorization.
12. **Giảm phishing:** chỉ duyệt pairing user tự khởi tạo, xác nhận code/device ngay cả với QR, hiển thị app identity và chống user-code brute force.
13. **Bảo vệ token trên thiết bị:** keystore/storage theo nền tảng, không log, refresh rotation/sender binding nếu cần, không lưu mật khẩu user.
14. **Hỗ trợ unlink và revoke:** danh sách thiết bị, xóa phiên, thu hồi grant/refresh token, kiểm tra hiệu lực access token và xử lý TV bị mất/bán.
15. **Kiểm thử đường phủ định:** sai/expired code, nhiều TV, từ chối, scope vượt quyền, tenant khác, phishing, polling abuse, revoke và bearer replay.

## Ghi nhớ

**Scope consent trên device** là quyết định người dùng đưa ra **trên website Authorization Server ở thiết bị thứ hai** cho một Device Authorization transaction đang chờ trên TV/IoT. **`user_code`** giúp người dùng liên kết đúng giao dịch; **`device_code`** là bí mật để Client polling token endpoint, **không được hiển thị cho user**. AS phải xác minh Client, user, tenant, resource, consent và scope thực sự được phép; TV phải xử lý `authorization_pending`, `slow_down`, `access_denied` và `expired_token` đúng RFC 8628. QR hay trang đăng nhập AS thật **không tự chứng minh user đang duyệt thiết bị của mình**: chỉ ghép nối khi người dùng chủ động bắt đầu và xác nhận đúng ứng dụng/mã/quyền. Sau khi cấp, access/refresh token vẫn phải được bảo vệ, có thời hạn/thu hồi và **Resource Server luôn xác minh audience, scope cùng quyền trên tài nguyên cụ thể**.

### Tài liệu tham khảo

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — offline_access và ID Token](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
