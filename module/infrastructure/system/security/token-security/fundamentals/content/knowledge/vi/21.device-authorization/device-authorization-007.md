# Device client without browser

**Device client without browser** là mô hình OAuth 2.0 dành cho thiết bị **không có trình duyệt phù hợp** hoặc **khó nhập văn bản**, chẳng hạn smart TV, máy chơi game, máy in, đầu phát đa phương tiện, màn hình thông minh hoặc một số ứng dụng terminal. Thiết bị vẫn có thể kết nối mạng và gọi HTTPS, nhưng không bắt người dùng nhập mật khẩu trên màn hình nhỏ hay điều khiển từ xa.

Giải pháp chuẩn là **OAuth 2.0 Device Authorization Grant (RFC 8628)**. Thiết bị hiển thị **địa chỉ xác minh** và **mã ngắn dành cho người dùng**; người dùng mở trình duyệt trên **điện thoại hoặc máy tính khác**, đăng nhập vào Authorization Server (AS), kiểm tra yêu cầu rồi quyết định **Allow/Deny**. Trong khi đó, thiết bị ban đầu **poll token endpoint** để biết yêu cầu đã được chấp thuận chưa. Chỉ khi AS xác nhận grant hợp lệ, thiết bị mới nhận access token.

Bài học thuộc chương **Device authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nó gắn với mô hình tin cậy, vòng đời token, JWT và opaque token, access/refresh token, xác thực và phân quyền OAuth 2.0/OIDC, scope/audience/claims, lưu trữ, thu hồi và phòng chống credential bị đánh cắp hoặc phát lại.

> **Điểm quan trọng:** “Device client without browser” nghĩa là **thiết bị muốn truy cập API không cần tự mở browser**. Nó **không** có nghĩa toàn bộ quy trình không cần trình duyệt: **người dùng vẫn phải có thiết bị khác** để xác thực và chấp thuận. Không biến device flow thành cách xin token không cần người dùng hoặc cách lấy mật khẩu trực tiếp trên TV.

## 1. Khi nào thực sự dùng Device Authorization Grant?

RFC 8628 phù hợp khi hội đủ các điều kiện:

1. Thiết bị **đang có kết nối Internet** và thực hiện được **HTTPS outbound** tới các endpoint của AS.
2. Thiết bị có cách **hiển thị hoặc truyền một chiều** `verification_uri` và `user_code` tới người dùng — có thể là màn hình, máy in, âm thanh hoặc cách tương đương.
3. Người dùng có **điện thoại/máy tính khác có user agent** (thường là browser) để mở trang xác minh.
4. AS đã **hỗ trợ và cho phép** client sử dụng device authorization grant.
5. Có mục đích ủy quyền cho **một user cụ thể**, thay vì chỉ kết nối giữa hai service không có user.

| Bối cảnh | Device flow có phù hợp? | Vì sao? |
|---|---|---|
| Smart TV hiển thị mã trên màn hình | **Có** | Không phải gõ tài khoản/mật khẩu bằng remote |
| CLI chạy trên máy không có GUI nhưng có HTTPS | **Có thể** | In URI và code; user mở browser trên thiết bị khác |
| Máy in hoặc màn hình có bàn phím rất hạn chế | **Có thể** | Người dùng phê duyệt qua điện thoại |
| Ứng dụng native mobile có browser hệ thống đầy đủ | **Thông thường không ưu tiên** | Dùng Authorization Code + PKCE với external browser theo RFC 8252 |
| SPA web bình thường | **Không phải lựa chọn mặc định** | Browser đã có, phù hợp Authorization Code + PKCE |
| Cron job hoàn toàn không có người dùng | **Không phù hợp** | Xem xét `client_credentials` hoặc cơ chế workload identity được quản lý |
| Cảm biến không kết nối Internet và không có kênh hướng dẫn user | **Không đáp ứng điều kiện** | Cần đổi kiến trúc, gateway hoặc provisioning khác |
| Đăng nhập quản trị từ xa cho nhiều kiosk | **Cần đánh giá kỹ** | Phải xác minh đúng thiết bị đang sở hữu; dễ có remote phishing |

**Thiết bị thiếu browser không nhất thiết là confidential client.** TV/console có firmware hoặc binary phân phối rộng thường khó giữ client secret thực sự bí mật. Theo RFC 8628, loại này thường nên được xem là **public client** trừ khi có biện pháp bảo vệ credential đáng tin cậy bổ sung.

## 2. Mô hình tin cậy có hai thiết bị và ba dịch vụ

Các vai trò cần phân biệt:

- **Device Client:** ứng dụng chạy trên TV/CLI/máy in muốn xin quyền; nó **không điều khiển browser đăng nhập trên điện thoại**.
- **Secondary Device / User Agent:** điện thoại hoặc PC của user, mở HTTPS verification page của AS.
- **Authorization Server:** tạo mã, giữ trạng thái authorization, xác thực user, nhận consent, cấp token khi đủ điều kiện.
- **Resource Server:** API sử dụng access token, kiểm tra issuer, audience, scope và quyền trên tài nguyên.
- **User/Resource Owner:** người thật quyết định có cho thiết bị dùng quyền của mình không.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant TV as TV/CLI không có browser
    participant AS as Authorization Server
    participant PHONE as Browser trên điện thoại
    participant API as Resource Server

    U->>TV: Chọn Kết nối tài khoản
    TV->>AS: POST device_authorization (client_id, scope)
    AS-->>TV: device_code, user_code, verification_uri, expires_in, interval
    TV-->>U: Hiển thị URI + user_code (+ QR nếu hỗ trợ)
    par Device polling
        TV->>AS: POST /token với device_code
        AS-->>TV: authorization_pending
        TV->>TV: Chờ đúng interval trước request sau
    and User authentication on secondary device
        U->>PHONE: Mở verification_uri
        PHONE->>AS: Nhập user_code / xác thực tài khoản
        AS->>U: Xác nhận thiết bị và scope, Allow/Deny
        U->>AS: Chấp thuận
        AS->>AS: Gắn grant vào đúng device_code/client
    end
    TV->>AS: Poll tiếp sau thời gian chờ
    AS-->>TV: Access token (+ refresh/ID token nếu được cấp)
    TV->>API: Authorization: Bearer access_token
    API->>API: Verify token, audience, scope, object-level ACL
    API-->>TV: Dữ liệu được phép
~~~

**Không có browser redirect trở về TV theo mô hình chuẩn.** Điện thoại giao tiếp với AS; TV giao tiếp với AS và API bằng các kết nối riêng. TV biết kết quả qua **polling**, không phải do điện thoại gửi access token cho TV.

### Phân tách ranh giới tin cậy

Điện thoại có thể xác thực user bằng MFA và xác nhận scope; điều đó **không tự tin cậy firmware/ứng dụng trên TV**. TV có thể bị đánh cắp hoặc bị cài phần mềm độc hại. Ngược lại, TV có `device_code` hợp lệ chưa chứng minh user đã cho phép; AS phải gắn **quyết định approve/deny thực sự** vào đúng transaction.

## 3. Hai mã khác mục đích: device_code và user_code

RFC 8628 trả về **hai giá trị khác nhau**:

| Giá trị | Ai nhận? | Mục đích | Có hiển thị cho user? |
|---|---|---|---|
| **`device_code`** | Device Client | Credential độ ngẫu nhiên cao dùng ở **token endpoint khi polling** | **Không**, giữ riêng trên thiết bị |
| **`user_code`** | User trên secondary device | Mã dễ đọc/nhập, giúp AS ghép phiên ủy quyền với thiết bị | **Có**, hiển thị rõ |
| **`verification_uri`** | User | Trang HTTPS của AS nơi user nhập mã và approve/deny | **Có** |
| **`verification_uri_complete`** (tùy chọn) | Browser khác qua QR/NFC | URI đầy đủ tối ưu hóa mở trang/điền mã | Có thể đưa vào QR/NFC, **không thay yêu cầu hiển thị user_code** |
| **`expires_in`** | Device Client | Số giây hiệu lực **của device_code và user_code** | Có thể hiển thị đồng hồ đếm |
| **`interval`** (tùy chọn) | Device Client | Khoảng cách tối thiểu/khuyến nghị khi polling | Dùng để lập lịch, không phải thời hạn token |

**Không được đảo vai trò mã**: không gửi `user_code` tới token endpoint như `device_code`, và không đưa `device_code` lên màn hình/QR/clipboard để user nhập. `user_code` được thiết kế ngắn, entropy thấp hơn; nó cần rate limiting và thời hạn ngắn tại AS. `device_code` cần entropy đủ cao để attacker không thể đoán khi polling.

### Device flow không sử dụng authorization code

Đừng nhầm:

- **Authorization Code + PKCE:** browser redirect về client với `code`; client gửi `code_verifier`.
- **Device Authorization Grant:** AS trả `device_code` trực tiếp cho device client; user xác minh trên thiết bị khác; device poll token endpoint.
- **User code:** là mã xác nhận liên kết thiết bị, **không phải `code_verifier` PKCE** và không phải token gọi API.

RFC 8628 **không định nghĩa PKCE như một bước bắt buộc trong device grant**. Nếu AS/provider có phần mở rộng riêng, chỉ sử dụng theo hợp đồng đã tài liệu hóa, không tự gắn code_challenge vào flow rồi giả định chuẩn hỗ trợ.

## 4. Tìm và đăng ký đúng endpoint ở Authorization Server

Device client **không** gửi request khởi tạo tới authorization endpoint `/authorize` của Authorization Code flow. RFC 8628 định nghĩa thêm **device authorization endpoint**.

Ví dụ metadata AS minh họa, theo RFC 8414:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/authorize",
  "device_authorization_endpoint": "https://auth.example.test/oauth2/device_authorization",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/.well-known/jwks.json",
  "grant_types_supported": [
    "authorization_code",
    "urn:ietf:params:oauth:grant-type:device_code",
    "refresh_token"
  ]
}
~~~

Đây là **minh họa**; không phải AS nào cũng công bố đủ các trường hoặc hỗ trợ tất cả grant. Các URL cần lấy từ **metadata/cấu hình issuer đáng tin cậy**, kiểm tra HTTPS và đối chiếu issuer, không lấy endpoint từ QR hoặc tham số do attacker truyền vào.

### Cấu hình client

| Cấu hình | Cần hiểu |
|---|---|
| `client_id` | Định danh client do AS đăng ký; **không phải secret** |
| `grant_type` | AS phải cho phép `urn:ietf:params:oauth:grant-type:device_code` |
| `scope` | Quyền xin cấp, AS xác định scope thực tế được chấp thuận |
| `resource`/audience nếu AS hỗ trợ | Yêu cầu tài nguyên mục tiêu theo extension như RFC 8707; không tự quyết định token audience |
| Client authentication method | Public client thường dùng `none`; confidential client dùng phương thức đã đăng ký |
| Access token profile | Bearer, DPoP hoặc profile khác tùy AS/RS; không suy từ việc client là TV |
| Refresh token policy | Có thể cấp hoặc không; với public client cần bảo vệ replay và thu hồi thích hợp |

Một client secret hardcoded trong firmware/binary có thể bị trích xuất. **Không dựa vào secret phát cùng mọi thiết bị như bằng chứng phần cứng là đáng tin**. Trường hợp cần device attestation/certificate, phải thiết kế cơ chế riêng, không giả định RFC 8628 đã xác thực thiết bị vật lý.

## 5. Bước 1 — Device gửi device authorization request

Giả sử `orders-tv` cần đọc danh sách đơn hàng đã được user cho phép. Khi user bấm **“Kết nối tài khoản”**, thiết bị gửi request **POST qua HTTPS**:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=orders-tv&scope=orders%3Aread
~~~

Ở đây:

- `client_id` **bắt buộc nếu client không tự xác thực** với AS (mô hình public client).
- `scope` là tùy chọn theo RFC 8628; AS áp dụng registration, consent và least privilege.
- Confidential client, nếu được cấp credential, **phải xác thực** tại device authorization endpoint theo quy tắc áp dụng cho token endpoint.
- Request dùng `application/x-www-form-urlencoded` trong body, không tự ý biến thành GET query hay JSON khi AS chỉ hỗ trợ chuẩn.
- AS phải nhận biết client, validate grant, scope/policy và **rate-limit việc tạo device sessions** để tránh flood.
- Client **chỉ nên khởi tạo khi user chủ động yêu cầu**, không tự gửi request/poll khi vừa mở TV hoặc tự động lặp flow mới mỗi khi code hết hạn.

**Device chưa có quyền gọi API sau bước này.** Request thành công chỉ tạo một **pending authorization transaction**, không phải access token.

## 6. Bước 2 — AS trả mã và thông tin xác minh

Response thành công có HTTP 200 với JSON:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache
~~~

~~~json
{
  "device_code": "device-code-secret-demo-not-real",
  "user_code": "QKJM-PNRT",
  "verification_uri": "https://auth.example.test/device",
  "verification_uri_complete": "https://auth.example.test/device?user_code=QKJM-PNRT",
  "expires_in": 600,
  "interval": 5
}
~~~

**Các mã trong ví dụ đều giả**, không dùng làm dữ liệu xác thực thật. `expires_in=600` nghĩa là **hai mã sống 600 giây tính từ lúc AS cấp**, không phải thời hạn của access token sẽ được cấp sau này. `interval=5` yêu cầu device tôn trọng khoảng polling từ server.

### Trường nào bắt buộc?

- **REQUIRED:** `device_code`, `user_code`, `verification_uri`, `expires_in`.
- **OPTIONAL:** `verification_uri_complete`, `interval`.
- Khi không có `interval`, client **MUST dùng giá trị mặc định 5 giây** theo RFC 8628.

**Không đặt mặc định `interval=0`** để poll lập tức trong vòng lặp. Nếu server trả khoảng thời gian có giá trị bất thường, client cần validate hoặc dừng theo policy, không đẩy tải bất thường tới token endpoint.

### Đừng log raw response

`device_code` là bí mật đang sống trong pending transaction. Không ghi toàn bộ JSON vào console, error report, telemetry hoặc log CDN/proxy. Dùng **device authorization session reference giả danh**, client ID đã xác minh, timestamps, trạng thái, không lưu secret như một event ID.

## 7. Bước 3 — Device hiển thị hướng dẫn dễ hiểu

TV nên hiển thị rõ **dịch vụ/issuer** và hai thông tin user cần:

~~~text
Kết nối tài khoản Orders trên TV

1. Dùng điện thoại hoặc máy tính của BẠN.
2. Mở trình duyệt và truy cập:
       https://auth.example.test/device
3. Nhập mã:
       QKJM-PNRT
4. Kiểm tra thiết bị và quyền yêu cầu trên trang chính thức.
5. Chỉ chấp thuận nếu chính bạn đang kết nối chiếc TV này.

Mã hết hạn sau khoảng 10 phút.
[Hủy]   [Thử lại (chỉ khi mã cũ hết hạn)]
~~~

Lưu ý:

- **Hiển thị `verification_uri` và `user_code`**. QR chỉ là tối ưu, không loại bỏ đường nhập thủ công.
- Không hiển thị `device_code`, access token, refresh token, client secret hay dữ liệu xác thực người dùng.
- Có thể nhóm mã bằng dấu gạch ngang, phông chữ dễ phân biệt `O/0`, `I/1` và hỗ trợ đọc bằng âm thanh khi cần.
- Thông báo rõ user đang **ủy quyền một thiết bị**, không phải nhập mã OTP/MFA để hoàn tất đăng nhập trên điện thoại.
- Khi user hủy, TV dừng poll và loại bỏ pending transaction; AS cũng nên có khả năng expire/revoke trạng thái theo chính sách.
- Không tự tái tạo mã mới liên tục khi user chưa yêu cầu — ngoài rủi ro UX, việc này tạo tải cho AS.

### Thiết bị không có màn hình thì sao?

RFC 8628 cho phép cách **truyền một chiều khác**, như đọc URI/code qua âm thanh hoặc giao tiếp gần được thiết kế thích hợp. Nhưng phải bảo vệ **sự hiện diện vật lý**: nếu bất kỳ người ở xa nào nhận được code và có thể thao tác, rủi ro chiếm phiên/phishing tăng.

Nếu thiết bị **không có màn hình, loa, bản in hoặc kênh truyền mã đáng tin**, hoặc không thể gọi HTTPS outbound, không thể áp dụng flow này theo các điều kiện cơ bản; cần cơ chế provisioning/gateway phù hợp khác.

## 8. verification_uri_complete, QR và rủi ro nhầm thiết bị

AS có thể trả `verification_uri_complete` chứa sẵn `user_code` để TV tạo QR hoặc NFC:

~~~text
https://auth.example.test/device?user_code=QKJM-PNRT
~~~

User quét QR trên TV và mở trang xác minh ở **browser của điện thoại**. Khi làm vậy:

1. TV **vẫn phải hiển thị `user_code`** ở dạng văn bản theo RFC 8628.
2. AS **nên hiển thị lại user_code và yêu cầu user kiểm tra khớp mã trên TV**.
3. AS vẫn yêu cầu **authentication, đánh giá consent và lựa chọn Allow/Deny**, không tự phê duyệt chỉ vì QR có user_code.
4. UI nên hiển thị thông tin client/thiết bị/scope có thể xác minh. Không tự giả định chuỗi “TV phòng khách” do một public client tự khai đã xác thực được phần cứng.
5. QR có thể bị dán đè/thay bằng mã độc. User cần xem **tên miền HTTPS AS chính thức** trên trình duyệt trước khi nhập mật khẩu.

**`verification_uri_complete` không được chứa `device_code` hoặc access/refresh token.** URL đã chứa user_code vẫn là thông tin nhạy cảm có thời hạn; tránh log full URL, analytics và Referrer đến bên ngoài khi chưa xác minh, đồng thời bảo vệ user code khỏi brute force.

## 9. Bước 4 — User xác minh trên một browser khác

Trên điện thoại/PC, user:

1. Mở **`verification_uri` chính thức của AS** (hoặc quét QR nếu hỗ trợ).
2. Nhập **`user_code`** hiển thị trên TV hoặc xác nhận mã đã điền.
3. **Đăng nhập và thực hiện MFA** nếu AS yêu cầu. TV không nhận mật khẩu, OTP hoặc cookie phiên của browser.
4. Xem AS đang xin cấp quyền cho **client/thiết bị nào** và với **scope nào**.
5. Kiểm tra mã trên điện thoại **đúng mã trên thiết bị mà mình đang sở hữu**.
6. Chọn **Approve/Allow** hoặc **Deny**.

AS nên bảo đảm user code:

- Chưa hết hạn, chưa được dùng/ghép sai hoặc bị hủy.
- Thuộc pending device session do chính AS phát hành và client được phép.
- Chỉ được xác minh với **rate limiting và giới hạn thử sai**; mã ngắn không chịu được brute force không giới hạn.
- Không bị dùng để tự động cấp token trước khi user xác nhận thiết bị và quyền.
- Được xử lý bằng HTTPS và giao diện chống phishing; không tiết lộ trạng thái user/code quá chi tiết cho bên không có quyền.

**Đăng nhập vào AS không bằng việc chấp thuận TV.** User có thể đăng nhập trên điện thoại nhưng bấm Deny. Device phải tiếp tục chờ theo interval cho đến khi nhận lỗi kết thúc hoặc trạng thái hết hạn, không coi việc browser đã mở verification page là consent.

## 10. Bước 5 — Device polling token endpoint

Sau khi hiển thị mã, TV gửi POST tới **token endpoint** đã cấu hình, sử dụng grant type đặc thù:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=device-code-secret-demo-not-real&client_id=orders-tv
~~~

Đây là dạng URL-encoded body cho **public client**. Với confidential client, áp dụng client authentication được đăng ký khi AS yêu cầu. `client_id` chỉ là **định danh**, không phải bí mật.

**Các ràng buộc bắt buộc trên AS:**

- `device_code` tồn tại, còn hạn, **gắn đúng client** đang gửi và grant/device session.
- Chưa được consume; không phát lại một token response mới nếu poll thứ hai dùng cùng code đã hoàn tất.
- User đã **chấp thuận đúng yêu cầu** (nếu chưa, trả `authorization_pending`).
- Scope và audience/token purpose chỉ thuộc phần AS cho phép.
- Client không vượt rate limit/polling policy; response lỗi không tiết lộ metadata của session khác.
- Token chỉ được phát hành tại thời điểm authorization hợp lệ, không phải ngay sau khi có user_code.

Nếu TV nhầm gửi `user_code` vào `device_code`, AS phải từ chối. Nếu TV bỏ `client_id` trong mô hình public client, request không đúng quy tắc RFC 8628. Nếu client gửi device_code tới **Resource Server**, API phải từ chối vì đây không phải access token.

## 11. Các response khi polling và điều kiện dừng

Trước khi user chấp thuận:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
~~~

~~~json
{
  "error": "authorization_pending"
}
~~~

Một số lỗi đặc thù RFC 8628:

| `error` | Ý nghĩa | Hành vi của device client |
|---|---|---|
| **`authorization_pending`** | User chưa hoàn tất approve/deny | **Tiếp tục poll**, nhưng phải chờ ít nhất interval trước lần tiếp |
| **`slow_down`** | Vẫn pending, client đang poll quá nhanh hoặc AS muốn giảm tải | **Tăng interval thêm ít nhất 5 giây** cho các lần polling tiếp theo |
| **`access_denied`** | User từ chối authorization | **Dừng polling**, báo từ chối, không xin token |
| **`expired_token`** | `device_code` hết hạn và phiên kết thúc | **Dừng polling**, chỉ tạo flow mới khi có tương tác user phù hợp |
| `invalid_client` | Client authentication/configuration thất bại | Dừng, xử lý lỗi cấu hình; không tự bỏ auth |
| `invalid_grant` hoặc lỗi OAuth khác | Grant/device_code sai, không hợp lệ hoặc bị revoke tùy AS | **Dừng polling**, không cố vá bằng mã khác |
| Network/connection timeout | Không biết chắc AS đã trả gì | **Giảm tần suất polling**, áp dụng backoff và deadline; không spam |

**Quy tắc chuẩn rất quan trọng:** RFC 8628 yêu cầu client **dừng polling khi nhận mã lỗi khác `authorization_pending` và `slow_down`**. Đừng viết loop kiểu “bất kỳ HTTP 400 nào cũng sleep rồi thử lại”.

### Thành công

Sau khi user đã approve, AS có thể trả một OAuth token response:

~~~json
{
  "access_token": "<ACCESS_TOKEN_ISSUED_BY_AS>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<REFRESH_TOKEN_IF_GRANTED>"
}
~~~

`expires_in` ở token response trên là **thời gian access token**, không phải `expires_in` của device authorization response. **Refresh token không phải lúc nào cũng được cấp**. Nếu OIDC được yêu cầu với `openid` và provider hỗ trợ profile tương ứng, response có thể bao gồm **`id_token`** theo OIDC; client phải xác minh ID token đúng chuẩn, không dùng nó làm token gọi API.

## 12. Polling interval: 5 giây mặc định và slow_down cộng 5 giây

Quy tắc RFC 8628 cần hiện thực chính xác:

1. Nếu device authorization response có `interval` hợp lệ, dùng **số giây đó** làm nhịp tối thiểu khi polling.
2. Nếu **không có `interval`**, client **MUST dùng 5 giây**.
3. Trước **mỗi request polling tiếp theo**, đợi đủ interval tối thiểu; đừng lập tức thử lại.
4. Khi nhận `slow_down`, client **MUST tăng interval thêm 5 giây** cho **lần tiếp theo và mọi lần sau**. Nếu nhận thêm `slow_down`, tiếp tục tăng.
5. Khi **connection timeout**, client **MUST giảm tần suất polling**; **exponential backoff** (ví dụ gấp đôi interval mỗi lần timeout) được khuyến nghị.
6. Dừng khi `expires_in` hết hạn, user bấm Cancel, nhận lỗi kết thúc hoặc token response hợp lệ.

Ví dụ với interval ban đầu 5 giây:

| Thời điểm minh họa | Sự kiện | Interval áp dụng cho lần tới |
|---|---|---|
| `t=0` | Nhận device_code và hiển thị mã | **5 giây** |
| `t≈5s` | Poll #1 → `authorization_pending` | 5 giây |
| `t≈10s` | Poll #2 → `slow_down` | **10 giây** |
| `t≈20s` | Poll #3 → `authorization_pending` | **10 giây**, không trở về 5 |
| `t≈30s` | Poll #4 → connection timeout | Giảm tần suất, ví dụ thành **20 giây** |
| `t≈50s` | Poll #5 → success hoặc pending | Còn thời hạn thì xử lý theo response |

Các mốc là ví dụ **bỏ qua network latency** để dễ hiểu; triển khai phải bảo đảm khoảng cách thực tế **không nhỏ hơn interval yêu cầu**. Không có một “mỗi 1 giây thử cho nhanh” theo chuẩn. Với nhiều thiết bị cùng polling, vi phạm nhịp này có thể trở thành **tải lớn/DoS ở token endpoint**.

### Deadline nên đo bằng thời gian đơn điệu

- `expires_in` đến từ AS, tính **deadline cục bộ khi nhận response**. Trong runtime có hỗ trợ, dùng monotonic clock (ví dụ `System.nanoTime`) để tránh thay đổi đồng hồ hệ thống giữa chừng.
- Không coi user đã approve là lý do tiếp tục poll **sau hạn device_code**.
- Không reset deadline khi gặp `authorization_pending`, `slow_down` hoặc timeout.
- Sau hủy/hết hạn, giải phóng timer, network call pending và secret trong memory theo khả năng.
- Polling ban đầu nên chờ interval như trong sơ đồ; dù implementation có chiến lược khác phù hợp chuẩn, **không được gây request liên tục**.

## 13. State machine và concurrency trên device/AS

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: User chọn Kết nối
    REQUESTED --> PENDING: Nhận device_code/user_code
    PENDING --> PENDING: authorization_pending + chờ interval
    PENDING --> SLOWER: slow_down
    SLOWER --> PENDING: Tăng interval thêm 5 giây
    PENDING --> APPROVED: User approve trên browser khác
    PENDING --> DENIED: User deny
    PENDING --> EXPIRED: Chạm expires_at
    PENDING --> CANCELLED: User hủy trên TV
    APPROVED --> CONSUMED: Device poll thành công, AS cấp token
    DENIED --> [*]: access_denied
    EXPIRED --> [*]: expired_token
    CANCELLED --> [*]: Dừng polling và dọn
    CONSUMED --> [*]: Lưu token theo policy
~~~

Đây là **mô hình học tập**, không phải enum được RFC bắt buộc. Khi user approve, trạng thái AS có thể chuyển từ pending sang approved, nhưng TV chỉ biết qua **lần poll hợp lệ tiếp theo**.

### Mỗi lần kết nối là một transaction riêng

- TV bấm Connect lần hai phải tạo **device session mới**, không dùng lại `device_code` cũ với `user_code` mới.
- Nếu app có nhiều account/tenant, giữ context/issuer/client/scope riêng cho từng session.
- Một thiết bị không nên khởi tạo hàng trăm pending sessions vì auto-retry; giới hạn số flow đồng thời.
- AS phải **gắn user_code với đúng device_code và client**, tránh ghép chéo.
- Khi đã cấp token thành công, AS phải **consume device grant atomically** để hai poll đồng thời không cấp token ngoài ý muốn.
- Lỗi mạng sau khi AS đã commit token có thể khiến TV không nhận được response; không làm device_code thành credential dùng lại vô hạn để “lấy token vừa cấp”.

## 14. Mã ngắn, brute force và session spying

`user_code` được người dùng nhập nên thường **ngắn hơn và dễ đọc hơn device_code**. Điều này tạo bề mặt brute force nếu AS không giới hạn số lần thử.

### Các biện pháp ở AS

- Sinh `user_code` đủ entropy **khi kết hợp TTL hữu hạn, rate limiting và những kiểm soát khác**.
- Giới hạn tốc độ theo IP/account/session/device code và tổng lượng thử; xử lý abuse phân tán.
- Không trả thông tin giúp attacker liệt kê user/thiết bị khi code sai.
- Định dạng code thân thiện, hạn chế ký tự dễ nhầm, có cơ chế kiểm lỗi nhập nếu phù hợp.
- Chỉ link code với client được phép, trạng thái PENDING và deadline chính xác.
- Khi user đã approve/deny, không để user_code cũ tiếp tục ghép sang session khác.

### Session spying: nhìn trộm mã trên TV

Ví dụ trong phòng chờ hoặc khách sạn, một người đứng gần nhìn thấy `user_code`. Nếu kẻ đó nhập mã và chấp thuận bằng tài khoản của mình **nhanh hơn chủ thiết bị**, họ có thể làm TV liên kết với tài khoản không mong muốn. AS cần bảo vệ bằng **xác nhận thiết bị/quyền rõ ràng**, và device UI cần cân nhắc môi trường công cộng khi hiển thị mã.

**Không có nghĩa user_code là OTP/MFA** để người xem cung cấp cho bất kỳ website nào. Nó chỉ ghép một **pending device authorization session**. Một mã 8 ký tự chỉ an toàn khi AS có đủ entropy, TTL và rate limiting, **không phải vì số ký tự tự nó bảo đảm bảo mật**.

## 15. Remote phishing: dụ user phê duyệt thiết bị của kẻ khác

Đây là rủi ro đặc thù nhất của device flow.

### Kịch bản tấn công

1. Attacker khởi động Device Authorization Grant trên **thiết bị hoặc ứng dụng họ kiểm soát**, nhận `user_code=A123-B456`.
2. Attacker nhắn tin cho nạn nhân: “Để xác minh tài khoản, mở trang đăng nhập chính thức rồi nhập mã A123-B456.”
3. Nạn nhân mở **đúng trang AS thật**, đăng nhập và bấm Approve, nhưng **đang cấp quyền cho thiết bị của attacker**.
4. Attacker tiếp tục poll bằng `device_code` của họ và nhận access token được cấp theo grant của nạn nhân.

Điểm tinh vi: **trang xác minh có thể là website chính thức 100%**. Kiểm tra HTTPS/domain cần thiết nhưng **chưa đủ**, vì attacker lợi dụng chính luồng cấp quyền hợp lệ.

### Cách phòng ngừa

**Authorization Server:**

- Nói rõ “Bạn đang cấp quyền cho một thiết bị khác”, không mô tả như OTP/MFA thông thường.
- Hiển thị client name, thông tin thiết bị có thể xác thực, scope/resource và tài khoản đang cấp quyền.
- Bắt user xác nhận **mã trên trang trùng mã đang hiện trên thiết bị họ sở hữu**; với QR/`verification_uri_complete`, bước này đặc biệt quan trọng.
- Cung cấp nút Deny rõ ràng, không tự approve khi chỉ đăng nhập/nhập mã.
- Cảnh báo hành vi bất thường, giới hạn thử mã và giám sát các grant nhạy cảm.

**Device Client/UI:**

- Hiển thị domain chính thức, code, thời hạn và thông điệp “Chỉ nhập mã này nếu bạn đang tự kết nối thiết bị”.
- Không yêu cầu gửi code qua điện thoại/chat/email cho người hỗ trợ.
- Không che dấu scope hoặc chuyển hướng sang trang đăng nhập giả.

**Người dùng:** Không nhập mã do người lạ gửi để “xác minh tài khoản”. Chỉ nhập mã đang hiển thị trên **thiết bị của chính mình mà mình đang trực tiếp thiết lập**.

## 16. Public client, client authentication và thiết bị bị chiếm quyền

TV, máy in, CLI được phân phối tới người dùng thường là **public client**, dù có `client_id`. Kẻ có thiết bị có thể giải nén binary, đọc firmware hoặc hook network/API; không mặc định một client secret hardcoded là bí mật.

| Kiểu client | Điểm cần làm |
|---|---|
| **Public device client** | Gửi `client_id` ở device authorization và token request; dùng TLS, bảo vệ device_code, không đưa secret dùng chung vào firmware |
| **Confidential client thực sự** | Xác thực client tại **cả device authorization endpoint và token endpoint** theo phương thức đã đăng ký |
| **Thiết bị có khóa hardware-backed/attestation** | Có thể áp dụng thêm bằng chứng thiết bị nếu AS hỗ trợ; không tự suy từ RFC 8628 |
| **Thiết bị bị malware/root** | Mã và token có thể bị lấy khi đang dùng; secure storage chỉ giảm một phần rủi ro |
| **Shared/public TV** | Không nên lưu refresh token vô hạn; cần logout, gỡ thiết bị và quản lý user/guest context |

**Không đưa password của user vào TV** để thay cho browser thứ hai. Device grant được thiết kế để **tách user authentication khỏi thiết bị hạn chế input**.

### Client ID có bảo vệ gì?

`client_id` giúp AS xác định registration/grant policy và bind device_code. Nó **không chứng minh** firmware hay phần cứng là hàng thật. Đối với threat model yêu cầu chống thiết bị giả, cần policy và cơ chế attest/binding riêng.

## 17. Java 17: quản lý polling đúng theo RFC 8628

Ví dụ Java 17 dưới đây mô phỏng **state machine polling** độc lập với thư viện OAuth cụ thể. `TokenEndpoint` là interface: implementation thật phải gửi **HTTPS POST form-urlencoded** tới đúng AS token endpoint, **không log raw device_code/token**, parse JSON có kiểm soát và chỉ trả kết quả đã phân loại.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class DeviceGrantPolling {
    private DeviceGrantPolling() {}

    public enum Status {
        AUTHORIZATION_PENDING,
        SLOW_DOWN,
        ACCESS_DENIED,
        EXPIRED_TOKEN,
        SUCCESS,
        NETWORK_TIMEOUT,
        OTHER_ERROR
    }

    public enum Outcome {
        APPROVED,
        DENIED,
        EXPIRED,
        FAILED,
        CANCELLED
    }

    public record Session(
            String deviceCode,
            int expiresInSeconds,
            Integer intervalSeconds
    ) {
        public Session {
            Objects.requireNonNull(deviceCode);
            if (deviceCode.isBlank() || expiresInSeconds <= 0) {
                throw new IllegalArgumentException("Bad device response");
            }
            if (intervalSeconds != null && intervalSeconds <= 0) {
                throw new IllegalArgumentException("Bad polling interval");
            }
        }
    }

    public interface TokenEndpoint {
        // Chỉ trao đổi device_code tại đúng AS qua HTTPS.
        // Nếu success, phần token phải xử lý riêng, không log/print.
        Status attempt(String deviceCode);
    }

    public interface Waiter {
        void sleep(Duration duration) throws InterruptedException;
    }

    public interface Cancellation {
        boolean cancelled();
    }

    public static Outcome run(
            Session session,
            TokenEndpoint tokenEndpoint,
            Waiter waiter,
            Cancellation cancellation,
            Clock clock
    ) throws InterruptedException {
        int interval = session.intervalSeconds() == null
                ? 5 : session.intervalSeconds();
        Instant deadline = clock.instant().plusSeconds(
                session.expiresInSeconds()
        );

        while (clock.instant().isBefore(deadline)) {
            if (cancellation.cancelled()) {
                return Outcome.CANCELLED;
            }

            Duration remaining =
                    Duration.between(clock.instant(), deadline);
            if (remaining.compareTo(Duration.ofSeconds(interval)) < 0) {
                return Outcome.EXPIRED;
            }

            // Chờ trước lần poll đầu và giữa các lần poll.
            waiter.sleep(Duration.ofSeconds(interval));

            if (cancellation.cancelled()) {
                return Outcome.CANCELLED;
            }
            if (!clock.instant().isBefore(deadline)) {
                return Outcome.EXPIRED;
            }

            Status status = tokenEndpoint.attempt(
                    session.deviceCode()
            );

            switch (status) {
                case SUCCESS:
                    return Outcome.APPROVED;
                case AUTHORIZATION_PENDING:
                    break; // tiếp tục, giữ nguyên interval
                case SLOW_DOWN:
                    if (interval > Integer.MAX_VALUE - 5) {
                        return Outcome.FAILED; // Không overflow.
                    }
                    interval += 5;
                    break;
                case NETWORK_TIMEOUT:
                    // Timeout => giảm tần suất polling. 2x là ví dụ.
                    if (interval > Integer.MAX_VALUE / 2) {
                        return Outcome.FAILED; // Không overflow.
                    }
                    interval *= 2;
                    break;
                case ACCESS_DENIED:
                    return Outcome.DENIED;
                case EXPIRED_TOKEN:
                    return Outcome.EXPIRED;
                default:
                    return Outcome.FAILED;
            }
        }

        return Outcome.EXPIRED;
    }
}
~~~

**Đây là mã minh họa, không phải client OAuth production:**

1. `Clock` ở đây đơn giản hóa kiểm thử. Production nên dùng **monotonic deadline** và cơ chế lịch hẹn **không chặn luồng UI**; `Waiter` chỉ là abstraction cho phần chờ.
2. `NETWORK_TIMEOUT` là kết quả giả định do adapter HTTPS phát hiện. **Connection timeout phải làm giảm tần suất**; thuật toán nhân đôi trong ví dụ là lựa chọn minh họa.
3. Hàm chỉ trả `APPROVED`, **không giữ access/refresh token**. Implementation thực tế của `TokenEndpoint` cần chuyển token response tới lớp lưu trữ an toàn sau khi AS cấp.
4. Chỉ polling ở đúng **token endpoint của issuer tin cậy** và theo đúng grant type. Không để `deviceCode` vào URL, log, error message hoặc HTTP GET.
5. Với `slow_down`, interval tăng thêm **5 giây từ giá trị hiện tại** và không được giảm xuống trước lần poll tiếp theo.
6. Khi user hủy/hết hạn, app cần hủy cả request/timer đang chờ, dọn pending session và UI; interface `Cancellation` không tự abort một socket đang blocked.
7. Không retry vô hạn khi AS trả lỗi khác pending/slow_down. Mỗi poll phải qua rate limit và deadline.
8. Nếu dùng nhiều client flows, không dùng cùng `deviceCode` ở nhiều timer; mỗi session chỉ có một poller chủ sở hữu.

### Pseudocode thiết lập request thực tế

~~~text
startDeviceFlow(client):
    assert trusted HTTPS issuer/metadata
    response = POST device_authorization(
        client_id, requested_scopes,
        authenticated_client_if_required
    )
    validate device_code, user_code, verification_uri, expires_in
    minInterval = response.interval ?? 5

    display verification_uri + user_code
    if verification_uri_complete available:
        optionally render QR AND display user_code

    state = PENDING
    while state == PENDING and before_monotonic_deadline:
        wait_at_least(minInterval)
        response = POST token_endpoint(
            grant_type = DEVICE_CODE_GRANT_URN,
            device_code = secret_device_code,
            client_id_or_registered_client_auth
        )

        if response is success:
            store_received_tokens_safely()
            stop
        if error == authorization_pending:
            continue
        if error == slow_down:
            minInterval += 5 seconds
            continue
        if connection_timeout:
            minInterval = increase_backoff(minInterval)
            continue

        stop_on_other_error()

    discard_device_code_and_ui_when_terminated()
~~~

Không chạy mã ví dụ trên như một cách đăng nhập bảo mật hoàn chỉnh: còn phải kiểm tra metadata/issuer, TLS, timeout, AS consent, API authorization và refresh token lifecycle.

## 18. Authorization Server phải lưu và tiêu thụ transaction thế nào?

Device grant không đơn thuần là một mã ngắn được người dùng nhập. AS cần ánh xạ **hai code tới cùng một authorization transaction** với trạng thái nhất quán:

~~~json
{
  "device_session_ref": "dev-session-pseudo-041",
  "client_id": "orders-tv",
  "device_code_ref": "hmac-or-hash-reference",
  "user_code_ref": "rate-limited-lookup-reference",
  "status": "PENDING",
  "scope_requested": "orders:read",
  "scope_granted": null,
  "subject": null,
  "expires_at": "2026-11-23T10:10:00Z",
  "poll_interval_seconds": 5,
  "redeemed_at": null
}
~~~

**Đây là schema logic, không phải wire format của RFC**. Không lưu raw `device_code` như log hoặc primary key có thể bị xem rộng rãi; dùng reference/digest/HMAC theo threat model và kiểm soát quyền đọc. `user_code` tuy ngắn có thể cần tra cứu, nhưng kho tra cứu phải chịu rate limiting/TTL và kiểm toán.

### Các chuyển trạng thái tối thiểu

| Trạng thái | Ai gây ra? | Polling token endpoint |
|---|---|---|
| **PENDING** | AS tạo session | Trả `authorization_pending` |
| **APPROVED** | User xác thực và chấp thuận | Có thể cấp token khi code/client/binding hợp lệ |
| **DENIED** | User từ chối | Trả `access_denied` |
| **EXPIRED** | Deadline của mã | Trả `expired_token` |
| **CONSUMED** | AS cấp token và consume grant thành công | Không cấp token lần thứ hai |
| **CANCELLED/REVOKED** | Hủy/thu hồi theo policy | Từ chối theo lỗi phù hợp |

Với hệ thống nhiều AS instances/regions, **chấp thuận user** và **poll token** có thể tới hai node khác nhau; trạng thái phải đồng bộ đủ để không có double issue hoặc grant confusion. Trạng thái consume/issuance cần **atomic transaction** hoặc cơ chế tương đương. Không dựa vào biến memory của một node hay thời gian Redis key tự hết hạn để thay validation ở token endpoint.

### SQL minh họa atomic claim sau approve

~~~sql
-- Pseudocode PostgreSQL: tham số, token creation/transaction
-- và kiểm tra binding do ứng dụng/AS triển khai riêng.

UPDATE device_authorizations
SET status = 'CONSUMED',
    redeemed_at = CURRENT_TIMESTAMP
WHERE device_code_ref = :trusted_device_code_ref
  AND client_id = :authenticated_or_identified_client
  AND status = 'APPROVED'
  AND expires_at > CURRENT_TIMESTAMP
RETURNING device_session_ref, grant_ref;

-- Chỉ khi đúng 1 row thắng, transaction mới được cấp token.
-- Token issuance metadata và consume cần commit nhất quán.
-- Không có kết quả => Không được cấp token.
~~~

Không lấy `device_code_ref` do client tự khai; AS phải tính từ `device_code` được gửi tới endpoint. Đoạn SQL trên chưa phải toàn bộ server implementation, không giải quyết việc revoke/cancel hoặc signing token.

## 19. Token được cấp: JWT/opaque, audience, scope và refresh token

Device flow chỉ quyết định **cách người dùng ủy quyền**. Access token sau đó vẫn tuân các nguyên tắc bảo mật OAuth thông thường:

- **JWT access token:** Resource Server phải xác minh chữ ký, thuật toán được phép, issuer, audience, time claims, token purpose và scope; không chỉ Base64url decode claims.
- **Opaque access token:** Resource Server introspect/tra trạng thái từ AS đáng tin cậy (RFC 7662) và kiểm tra `active`/audience/scope/permissions.
- **`token_type=Bearer`** mô tả cách sử dụng token, **không nói token là JWT**. Sender-constrained token như DPoP/mTLS có ràng buộc chứng minh khóa riêng nếu profile và thiết bị hỗ trợ.
- **ID token (OIDC)** phục vụ client xác minh authentication, không dùng thay access token tại API.
- **Refresh token:** chỉ dùng tại AS token endpoint theo grant; không dùng `user_code` hoặc `device_code` để refresh. AS có thể không cấp refresh token và có thể yêu cầu reauthorization sau phiên hiện tại.
- **Scope/audience:** requested `orders:read` không đồng nghĩa user được đọc mọi order; Resource Server vẫn kiểm tra tenant/object authorization.

Ví dụ API đúng:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

TV không gửi `device_code`, `user_code`, ID token hoặc refresh token trong header trên. Nếu user từ chối trên điện thoại, TV **không nhận access token mới**.

### Public device client và refresh-token replay

Theo OAuth Security BCP (RFC 9700), refresh token cho public client cần biện pháp phát hiện/restrict replay như **rotation hoặc sender constraint** phù hợp. TV cần bảo vệ RT ở OS secure storage/hardware-backed key khi khả dụng, xóa khi logout/thiết bị bị gỡ quyền và xử lý refresh reuse.

## 20. Logout, thu hồi và thiết bị dùng chung

Sau khi TV đã được cấp token, pending `device_code` nên được consume; việc user đóng browser trên điện thoại **không tự đăng xuất TV**.

### Vòng đời vận hành sau authorization

| Hành động | Kết quả cần xử lý |
|---|---|
| User chọn **Hủy** khi TV còn đang chờ | Dừng polling, xóa `device_code`/mã khỏi UI, AS session hết hạn/revoke theo policy |
| User chọn **Deny** trên điện thoại | AS ghi denied, TV nhận `access_denied` và ngừng |
| User **Approve** | TV nhận token qua poll hợp lệ; lưu token theo security policy |
| Access token hết hạn | Refresh qua AS nếu có RT hợp lệ, hoặc xin grant mới qua device flow |
| User logout TV | Xóa local AT/RT/session, yêu cầu AS revoke refresh/grant theo khả năng và policy |
| TV bị mất/bán/chuyển chủ | User/admin có cơ chế **remove/revoke linked device** từ account portal đáng tin cậy |
| RT bị nghi lộ | Revoke RT family/grant, rà AT đã cấp; không chỉ xóa màn hình user_code |
| Access JWT đã phát hành bị nghi lộ | API cần revocation state/denylist/introspection hoặc giới hạn bằng TTL; logout không tự chặn JWT offline |

**Device code không phải refresh token.** Không dùng lại nó sau success hoặc expiration để xin access token mới. Việc cấp/thu hồi access token và refresh token xảy ra ở vòng đời **sau** authorization.

### Thiết bị dùng chung có rủi ro riêng

Với TV trong khách sạn, phòng họp hoặc khu vực công cộng, app phải làm rõ **user hiện tại**, cơ chế guest mode, tự logout, xóa token khi reset, xóa tài khoản đã liên kết và khả năng revoke từ xa. **Có secure storage không nghĩa thiết bị công cộng tự được phép giữ tài khoản mãi mãi**.

## 21. Case study: TV chưa có browser nhưng có API access

Giả sử user dùng TV `orders-tv` trong phòng khách. AS `https://auth.example.test`, Orders API `https://orders-api.example.test`, scope yêu cầu `orders:read`. AS phát device/user code có lifetime **10 phút** và polling interval **5 giây** — các con số **chỉ là cấu hình ví dụ**, không phải default bắt buộc.

| Thời điểm UTC | TV | Điện thoại/AS | Kết quả |
|---|---|---|---|
| **10:00:00** | User chọn Connect; TV POST `/device_authorization` | AS tạo device session D1 | D1 đang PENDING |
| **10:00:01** | TV hiển thị `https://auth.example.test/device` và `QKJM-PNRT` | — | Chưa có access token |
| **10:00:06** | Poll #1 với D1 | AS trả `authorization_pending` | TV tiếp tục, đợi ≥5s |
| **10:00:12** | Poll #2 với D1 | AS trả `slow_down` | TV tăng interval từ 5 lên **10s** |
| **10:00:16** | TV chờ | User nhập user_code trên điện thoại, đăng nhập MFA | AS vẫn chưa tự approve |
| **10:00:19** | TV chờ | User xác minh mã/thiết bị/scope rồi bấm Approve | AS chuyển D1 sang APPROVED |
| **10:00:22** | Poll tiếp đúng nhịp | AS xác minh D1/client và cấp token | D1 CONSUMED |
| **10:00:23** | TV lưu token và gọi Orders API | API check audience/scope/ACL | Dữ liệu đúng quyền |

### Ba biến thể cần xử lý khác nhau

**A. User bấm Deny:** AS trả `access_denied`; TV dừng polling, thông báo không kết nối, không xin token.

**B. User không hoàn tất trong 10 phút:** hết hạn `device_code`/`user_code`; TV dừng polling. Không tự động tạo mã mới mỗi giây; chỉ bắt đầu flow mới khi user yêu cầu.

**C. Attacker gửi user_code của TV thuộc attacker:** nạn nhân có thể thấy **đúng trang AS thật**, nhưng khi approve lại cấp quyền cho thiết bị của attacker. Cơ chế kiểm tra **đang sở hữu thiết bị nào và mã nào** là bắt buộc về mặt threat model, không được bỏ qua vì có HTTPS.

## 22. Ma trận kiểm thử Device client without browser

| Test | Thao tác | Kết quả mong đợi |
|---|---|---|
| **T1 — User initiation** | App mở TV nhưng user chưa bấm Connect | Không tạo device authorization sessions/poll tự động |
| **T2 — Public client** | POST device auth có `client_id`, không secret | AS nhận diện đúng client và chính sách |
| **T3 — Confidential client** | Client đăng ký auth nhưng không gửi credential | AS từ chối khi thiếu client authentication |
| **T4 — Required response** | AS trả JSON thiếu `device_code`/`user_code`/URI/expiry | Client từ chối response không hợp lệ |
| **T5 — Interval omitted** | AS không trả `interval` | Client dùng **5 giây mặc định** |
| **T6 — Pending** | User chưa approve; poll token endpoint | `authorization_pending`, tiếp tục chờ đúng interval |
| **T7 — Slow down** | AS trả `slow_down` một lần | Tăng interval **ít nhất 5s** cho các lần tiếp |
| **T8 — Repeated slow down** | AS trả `slow_down` hai lần | Tăng tổng **ít nhất 10s**, không reset |
| **T9 — Timeout** | Token endpoint connection timeout | Giảm frequency, exponential backoff và deadline |
| **T10 — Denied** | User bấm Deny trên browser khác | AS trả `access_denied`, client ngừng poll |
| **T11 — Expired** | `expires_in` hết mà chưa approve | Không cấp token; client dừng |
| **T12 — Cancel** | User chọn Hủy trên TV | Dừng timer/poll, cleanup mã |
| **T13 — Wrong code type** | Dùng `user_code` ở token endpoint | Bị từ chối; không coi user code là device code |
| **T14 — Wrong client** | Client B poll `device_code` của A | AS từ chối, không lộ trạng thái grant A |
| **T15 — Double poll** | Hai request đồng thời sau approval | AS consume một lần, không double issue |
| **T16 — QR code** | Quét `verification_uri_complete` | AS vẫn hiển thị code và yêu cầu so khớp trước approve |
| **T17 — Remote phishing** | User nhập code của thiết bị không thuộc họ | UI hiển thị cảnh báo/thiết bị, có lựa chọn Deny rõ |
| **T18 — User-code guessing** | Nhiều mã đoán sai từ các nguồn | Rate limit/anti-abuse, không lộ session |
| **T19 — Session spying** | Mã hiển thị trên TV công cộng | Giảm quan sát mã và xác nhận device ownership |
| **T20 — Log privacy** | Canary device_code/RT trong staging | Không lộ trong URL, logs, analytics, crash/HAR |
| **T21 — JWT validation** | TV gọi API với AT sai `aud`/scope | Resource Server từ chối |
| **T22 — Wrong purpose** | Dùng device_code/ID token/RT gọi API | Resource Server từ chối |
| **T23 — RT rotation** | Refresh thành công rồi reuse RT cũ | AS phát hiện và xử lý theo policy |
| **T24 — Offline/clock change** | TV đổi wall clock, chập chờn Internet | Không poll quá hạn hoặc vượt interval, dùng deadline ổn định |
| **T25 — Lost device** | Revoke linked TV từ account portal | AS ngăn refresh, API tuân revocation policy |
| **T26 — Multi-user TV** | User A logout, user B connect | Không dùng token/cached data của A trong phiên B |

Kiểm thử với credential **staging/canary giả**, không in raw token/device_code production ra log hoặc report. Với polling concurrency, cần test nhiều TV và nhiều AS nodes để phát hiện rate limit, clock drift và double issuance.

## 23. Những nhầm lẫn phổ biến

**“Không có browser nghĩa là không cần user đăng nhập.”** Sai. User đăng nhập/approve **trên browser của thiết bị khác**.

**“`user_code` là OTP/MFA để nhập vào bất kỳ tin nhắn hỗ trợ nào.”** Sai. Nó là mã ghép pending authorization với thiết bị đang kết nối; nhập mã của attacker có thể cấp quyền cho attacker.

**“`device_code` và `user_code` là hai tên cho cùng một giá trị.”** Sai. Một mã dùng để poll tại token endpoint, một mã dùng để user xác minh.

**“Client ID được gửi tức là đã xác thực thiết bị.”** Sai. Với public client, client ID là định danh, không phải secret, không chứng minh hardware possession.

**“Dùng PKCE verifier thay `device_code` cho bảo mật hơn.”** Sai theo flow chuẩn. PKCE là extension cho authorization code exchange; RFC 8628 định nghĩa grant/token request riêng.

**“QR có mã rồi thì AS có thể tự approve.”** Sai. QR chỉ giảm việc nhập code, không thay bước xác nhận user/thiết bị/scope.

**“Poll càng nhanh càng tiện.”** Sai. Phải tôn trọng `interval`, `slow_down` và backoff khi timeout.

**“AS trả `authorization_pending` là lỗi nên bỏ luôn flow.”** Sai. Đây là trạng thái chưa xong, cho phép poll tiếp theo quy tắc. Ngược lại, với **`access_denied`/`expired_token`/lỗi khác**, phải dừng.

**“TV nhận token thì user code trở thành refresh token.”** Sai. Device grant/code đã được consume; refresh flow (nếu có RT) là luồng khác.

**“Token trên TV là JWT nên API chỉ cần decode payload.”** Sai. API phải xác minh JWT chữ ký/issuer/audience/thời gian/scope hoặc introspect opaque token và kiểm tra quyền trên tài nguyên.

## 24. Checklist triển khai và tài liệu tham khảo

### Checklist

1. **Dùng Device Authorization Grant (RFC 8628)** đúng mục đích: client không có browser phù hợp hoặc input bị hạn chế, có HTTPS và kênh chỉ dẫn user.
2. **Đảm bảo có browser trên thiết bị thứ hai**; nếu không có user/secondary device thì chọn kiến trúc khác.
3. **Đăng ký client với device grant và issuer đúng**; lấy device authorization/token endpoints từ metadata/cấu hình tin cậy.
4. **Không hardcode client secret trong firmware public client** rồi coi TV đã được xác thực.
5. **Khởi tạo khi user yêu cầu**, POST form-urlencoded qua TLS tới device authorization endpoint.
6. **Phân biệt và bảo vệ hai mã:** `device_code` chỉ ở device/token endpoint, `user_code` hiển thị cho user, mã đều có deadline.
7. **Hiển thị `verification_uri`/`user_code`**, có thể QR `verification_uri_complete` nhưng vẫn hiển thị code để user so khớp.
8. **AS yêu cầu user authentication + confirmation + consent**, nêu rõ thiết bị và scope; không approve chỉ vì user quét QR.
9. **Chống remote phishing:** không nhận mã gửi qua tin nhắn lạ; xác minh user đang sở hữu chính thiết bị đó.
10. **Chống brute force/spy:** user-code entropy + rate limit + TTL, bảo vệ màn hình/kênh truyền mã theo môi trường.
11. **Poll đúng grant type** `urn:ietf:params:oauth:grant-type:device_code`, không gửi mã tới API.
12. **Tôn trọng interval:** mặc định 5s khi thiếu, `slow_down` tăng thêm 5s cho mọi lần sau, timeout giảm frequency.
13. **Dừng đúng lúc:** approval thành công, Deny, expired, Cancel hoặc lỗi ngoài pending/slow_down; không tự loop mã mới.
14. **AS bind device_code với client/grant** và consume atomically; nhiều node/regions không được double issue.
15. **Dùng monotonic deadline** hoặc cơ chế tương đương để giới hạn polling trong `expires_in`.
16. **Không log raw codes/token/headers**, dùng reference pseudonym cho audit và không đưa device_code vào QR/URL.
17. **Sau khi có token:** lưu AT/RT an toàn theo thiết bị, API xác minh audience/issuer/scope/permissions, không dùng ID token hoặc device_code thay access token.
18. **Refresh, logout và device removal:** rotation/revocation theo policy, có phương án gỡ liên kết khi TV mất/bán/chuyển người dùng.
19. **Kiểm thử âm tính**: polling backoff, brute force, phishing, callback/AS confusion, wrong client, double polling, expiry và token misuse.
20. **Đánh giá lại thiết kế** nếu thiết bị có browser đầy đủ: Authorization Code + PKCE thường phù hợp hơn cho native app thông thường.

### Tài liệu tham khảo

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): toàn bộ flow, hai mã, polling, xử lý lỗi, bảo mật và UX.
- [RFC 8628, Section 3.1–3.5](https://www.rfc-editor.org/rfc/rfc8628#section-3): device authorization request/response, user interaction và token polling.
- [RFC 8628, Section 5](https://www.rfc-editor.org/rfc/rfc8628#section-5): user-code brute force, device trust, remote phishing và session spying.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client types, token endpoint và access token response.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `device_authorization_endpoint` và `grant_types_supported` discovery.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token security, client/grant protection và refresh token replay.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): khi nào native app có browser nên dùng Authorization Code + PKCE.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token và transport an toàn.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token/grant khi logout hoặc mất thiết bị.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token khi môi trường hỗ trợ proof key.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): rủi ro và phòng vệ OAuth trong thực tế.

**Kết luận:** một **device client không có browser** vẫn có thể được user ủy quyền an toàn bằng cách **khởi tạo device grant qua HTTPS, hiển thị `user_code`, để user approve trên browser khác và polling đúng nhịp với `device_code` bí mật**. Điểm khó nhất không phải in mã lên TV mà là **ngăn kẻ khác dụ user approve sai thiết bị, bảo vệ trạng thái trên AS và ngừng polling/thu hồi token đúng vòng đời**. Sau khi cấp token, API vẫn phải xác minh JWT/opaque access token, audience, scope, hạn sử dụng và quyền dữ liệu; device flow không tạo ngoại lệ cho các quy tắc này.
