# Device code denial và expiration

Một chiếc smart TV hiển thị: **“Truy cập https://auth.example.test/activate và nhập mã WJRD-KLHP để kết nối tài khoản.”** Người dùng dùng điện thoại mở trang đó, đăng nhập và quyết định **Cho phép** hoặc **Từ chối**. Trong khi chờ, TV liên tục hỏi Authorization Server (AS): *“Thiết bị của tôi đã được chấp thuận chưa?”* Điều gì xảy ra nếu người dùng **từ chối**, mã **hết hạn**, người dùng **không phản hồi**, hoặc AS yêu cầu TV **giảm tần suất hỏi**?

Đó là chủ đề **“Device code denial và expiration”** trong chương **Device authorization** của module **Security Token Security Fundamentals**. Bài học dựa trên **OAuth 2.0 Device Authorization Grant (RFC 8628)**, tập trung vào vòng đời `device_code`/`user_code`, trạng thái từ chối (`access_denied`), mã hết hạn (`expired_token`), trạng thái đang đợi (`authorization_pending`), hạn chế polling (`slow_down`), và cách client/AS xử lý **đúng bảo mật, không chạy vô hạn và không phát nhầm token**.

**Thông điệp cốt lõi:** Một `device_code` là **đầu vào để thiết bị hỏi trạng thái tại token endpoint**, **chưa phải access token**. Người dùng phải hoàn thành tương tác trên AS, AS còn phải kiểm client và grant, mã còn hạn và chưa bị tiêu thụ. Khi **DENIED** hoặc **EXPIRED**, thiết bị phải dừng phiên polling; **không** biến lỗi thành thành công, không dùng mã cũ để xin token vô hạn và không tự mở một phiên mới khi người dùng không yêu cầu.

## 1. Vì sao có Device Authorization Grant?

**Device Authorization Grant** phục vụ thiết bị có khả năng nhập liệu hoặc trình duyệt hạn chế: smart TV, máy chơi game, thiết bị đầu cuối CLI, máy in, IoT có màn hình nhỏ. Thay vì nhập mật khẩu trên thiết bị khó tin cậy, **người dùng xác thực với AS bằng một thiết bị khác** (điện thoại, laptop) có browser phù hợp.

| Thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| **Device client** | Smart TV / CLI | Xin cặp mã, hiển thị hướng dẫn, polling token endpoint theo `interval`, dừng khi terminal |
| **End user / Resource Owner** | Người dùng An | Mở `verification_uri` bằng thiết bị có browser, xác minh yêu cầu, chấp thuận hoặc từ chối |
| **Authorization Server** | `https://auth.example.test` | Phát mã, quản lý TTL/trạng thái, xác thực/định danh client và người dùng, xét consent, cấp token hoặc lỗi |
| **Resource Server** | Media API | Kiểm access token sau khi được cấp: issuer, audience, scope, expiry và quyền tài nguyên |

Trong module này, grant thuộc **vòng đời token bảo mật**, nhưng cần phân biệt rõ **authorization chưa được quyết định** với **access token đã được cấp**. Một thiết bị đang chờ `authorization_pending` không được sử dụng `device_code` để gọi Media API.

### Không phải Authorization Code + PKCE thông thường

Device grant **không có authorization code được browser trả trực tiếp đến redirect URI của TV**. TV nhận `device_code` qua **device authorization endpoint**, sau đó polling **token endpoint**. Người dùng nhập `user_code` tại giao diện AS; AS nối hành động này với phiên device authorization đã tạo.

`PKCE` bảo vệ Authorization Code Flow trước code interception, **không phải** bằng chứng bắt buộc thay thế `device_code` trong RFC 8628. Với device flow, cần các lớp bảo vệ **code entropy, client binding, thời hạn, chống đoán user code, hạn chế polling, bảo vệ UI phê duyệt và token handling sau khi cấp**.

## 2. Hai mã quan trọng: `device_code` và `user_code`

| Thuộc tính | `device_code` | `user_code` |
|---|---|---|
| **Ai nhận?** | Device client nhận trực tiếp từ AS | Device client nhận để **hiển thị cho người dùng** |
| **Ai sử dụng?** | Device gửi đến **token endpoint** để polling | Người dùng nhập tại **verification URI** trên thiết bị thứ hai |
| **Đặc tính** | Chuỗi có entropy cao, khó đoán; cần giữ bí mật | Ngắn, dễ đọc/gõ, có thể chứa nhóm ký tự/dấu gạch |
| **Là access token?** | **Không** | **Không** |
| **Mối đe dọa nổi bật** | Bị đánh cắp rồi kẻ khác polling lấy token khi grant được approve | Bị đoán/brute-force, nhập nhầm hoặc bị kẻ lừa đảo gửi code của phiên khác |
| **Vòng đời** | Gắn client/session, expires, trạng thái, tiêu thụ sau thành công | Gắn cùng transaction, hết hiệu lực theo chính sách của AS |

**Không gọi nhầm user code là “mật khẩu của người dùng”.** Mã được dùng để tìm **yêu cầu chờ phê duyệt**. Người dùng vẫn phải được xác thực tại AS và được trình bày chính xác quyền/client/device cần chấp thuận.

### Ba bất biến cần bảo đảm

1. **Không có quyền trước phê duyệt:** `device_code` + `user_code` chỉ xác định một transaction, không phải grant đã cấp.
2. **Phải thuộc cùng transaction:** AS không được lấy hành động approve của `user_code` thuộc transaction A rồi trả token cho `device_code` thuộc transaction B.
3. **Không dùng lại sau terminal:** Đã **DENIED**, **EXPIRED** hoặc **CONSUMED** thì không thể biến phiên cũ thành phiên active chỉ bằng việc gửi lại `device_code`.

## 3. Bắt đầu phiên: device authorization response

Device client gửi request đến **device authorization endpoint** do AS công bố, khác với token endpoint. Đường dẫn thực tế phụ thuộc nhà cung cấp; `/oauth/device_authorization` bên dưới chỉ là ví dụ.

~~~http
POST /oauth/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=tv-client&scope=media%3Aplay
~~~

Với **public device client**, `client_id` thường là định danh công khai. Nếu AS đăng ký client dạng **confidential** và yêu cầu client authentication, thiết bị phải áp dụng phương thức xác thực đã đăng ký; không coi `client_id` là password.

Phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "<high-entropy-device-code>",
  "user_code": "WJRD-KLHP",
  "verification_uri": "https://auth.example.test/activate",
  "verification_uri_complete": "https://auth.example.test/activate?user_code=WJRD-KLHP",
  "expires_in": 600,
  "interval": 5
}
~~~

Theo RFC 8628:

- `device_code`: **bắt buộc**, device dùng tại token endpoint.
- `user_code`: **bắt buộc**, để end user nhập tại verification URI.
- `verification_uri`: **bắt buộc**, nơi end user mở để hoàn tất tương tác.
- `verification_uri_complete`: **tùy chọn**, URI tiện dụng có thể chứa sẵn user code (ví dụ QR code).
- `expires_in`: **bắt buộc**, số **giây** mà cả `device_code` và `user_code` còn hiệu lực.
- `interval`: **tùy chọn**, khoảng thời gian tối thiểu giữa các lần device polling, **đơn vị giây**; nếu không có, client **phải dùng mặc định 5 giây**.

**Đừng tự gán ý nghĩa khác cho `expires_in`:** Đây là **hạn của device/user code**, **không phải TTL của access token sau khi cấp**. Access token response về sau có `expires_in` riêng, áp dụng cho access token.

### Khi hiển thị cho người dùng

~~~text
Kết nối TV của bạn

1. Mở https://auth.example.test/activate bằng điện thoại.
2. Nhập mã: WJRD-KLHP
3. Kiểm tra tên ứng dụng/thiết bị và quyền được yêu cầu.
4. Chọn Cho phép hoặc Từ chối.

Mã này sẽ hết hạn sau khoảng 10 phút.
Không chia sẻ mã cho người lạ yêu cầu qua chat/điện thoại.
~~~

Giao diện nên hiển thị **verification URI thuộc AS được tin cậy**, không dùng URL từ đầu vào tùy ý. Nếu dùng QR hoặc `verification_uri_complete`, cần cho người dùng xác minh tên miền và danh tính yêu cầu. **Không đưa `device_code` vào QR/URL public**; nó là giá trị nhạy cảm dùng để polling ở token endpoint.

## 4. Device polling tại token endpoint

Sau khi nhận response, thiết bị bắt đầu polling **token endpoint**, nhưng **không trước `interval` đã được chỉ định**. Ví dụ với public client:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&
device_code=<redacted-device-code>&
client_id=tv-client
~~~

Giá trị grant type **chính xác** khi chưa URL-encode là:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

AS phải kiểm `device_code` còn hiệu lực, thuộc **đúng client**, trạng thái phiên, số lần polling, yêu cầu grant và client authentication nếu cần.

### Kết quả polling có thể là gì?

| Trạng thái AS | Phản hồi token endpoint | Thiết bị làm gì? |
|---|---|---|
| **PENDING** | `authorization_pending` | Tiếp tục đợi ít nhất `interval` trước lần kế |
| **PENDING + đang poll quá nhanh** | `slow_down` | **Tăng interval thêm 5 giây** cho các lần sau rồi tiếp tục |
| **APPROVED và hợp lệ** | **Access token response thành công** | Nhận token, **dừng polling**, chuyển sang gọi RS đúng audience |
| **DENIED** | `access_denied` | **Dừng polling**, hiển thị bị từ chối, không tự retry grant |
| **EXPIRED** | `expired_token` | **Dừng polling**, dọn transaction; chỉ khởi tạo flow mới khi phù hợp |
| **Lỗi OAuth khác** | Ví dụ `invalid_client`, `invalid_grant` tùy trường hợp | Không coi là pending; xử lý lỗi/stop theo contract |

**Đặc biệt:** `access_denied` và `expired_token` **không phải tín hiệu để “thử lại vài giây nữa” với cùng code**. Đây là kết quả terminal của authorization session. `authorization_pending` và `slow_down` mới là trạng thái còn có thể tiếp tục polling theo RFC.

## 5. Bốn lỗi cần phân biệt: pending, slow_down, denied, expired

### `authorization_pending`: chưa có quyết định của người dùng

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"authorization_pending"}
~~~

Trạng thái này có nghĩa AS **chưa nhận được phê duyệt hoàn chỉnh** cho transaction. Không được cấp access token; client **có thể tiếp tục polling theo `interval`** cho tới khi kết quả thay đổi hoặc mã hết hạn. Không hiển thị “Đăng nhập thất bại” mỗi lần pending.

### `slow_down`: tiếp tục nhưng phải hỏi chậm hơn

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"slow_down"}
~~~

RFC 8628 yêu cầu client **tăng khoảng thời gian polling thêm 5 giây** sau `slow_down` và giữ mức tăng đó cho **các lần polling về sau**. Ví dụ `interval` ban đầu là 5 giây:

~~~text
T0     Device nhận interval=5
T0+5   Poll -> authorization_pending
T0+10  Poll -> slow_down
T0+20  Poll (đã tăng lên 10 giây) -> authorization_pending
T0+30  Poll (vẫn ít nhất 10 giây) -> slow_down
T0+45  Poll (đã tăng lên 15 giây)
~~~

Lịch trên **chỉ minh họa**, chưa tính jitter, network latency và server scheduler. Đừng reset về 5 giây sau một `authorization_pending` tiếp theo; như thế sẽ vi phạm yêu cầu tăng interval khi AS đã phát `slow_down`.

Nếu token request bị **network timeout**, RFC khuyến nghị client **giảm tần suất polling**, ví dụ dùng exponential backoff, để không làm AS quá tải. Với HTTP 429 hoặc `Retry-After`, cần tuân thủ chính sách/quota và không poll nhanh hơn ngưỡng đang hiệu lực; `Retry-After` không làm sống lại code đã expired.

### `access_denied`: end user đã từ chối

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"access_denied"}
~~~

AS đã ghi nhận người dùng **từ chối** yêu cầu ủy quyền (hoặc policy trả từ chối tương đương). Client **phải chấm dứt việc chờ phiên hiện tại theo hành vi RFC**, loại bỏ mã khỏi trạng thái đang dùng và hiển thị thông báo bình thường như: “Bạn đã từ chối kết nối. Thiết bị chưa được cấp quyền.” Không đổ lỗi cho người dùng, không tự đổi lỗi thành `authorization_pending`.

**Không âm thầm tạo một device authorization session mới ngay sau denial.** Một hành động từ chối phải được tôn trọng. Chỉ tạo phiên mới khi có **tương tác chủ động** và chính sách cho phép.

### `expired_token`: mã device đã hết hạn

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"expired_token"}
~~~

Hết `expires_in` đồng nghĩa device authorization session **không còn hợp lệ để hoàn tất**. Device phải **dừng polling**, xóa trạng thái transaction cũ, thông báo “Mã kết nối đã hết hạn. Hãy chọn thử lại để nhận mã mới.” Nếu người dùng vẫn ở trang verification, AS nên chỉ ra mã hết hạn và không cho **approval muộn** hồi sinh grant.

**Không nhầm `expired_token` ở device grant với access token JWT hết `exp` tại Resource Server.** Hai mốc thuộc **hai giai đoạn khác nhau**, có chính sách và chủ thể kiểm riêng.

## 6. Vòng đời và state machine của device authorization

Một mô hình AS tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Tạo device_code/user_code
    PENDING --> PENDING: Poll đúng interval / pending, slow_down
    PENDING --> APPROVED: User xác thực + approve, code còn hạn
    PENDING --> DENIED: User từ chối
    PENDING --> EXPIRED: Deadline đã tới
    APPROVED --> CONSUMED: Poll hợp lệ, AS cấp token một lần
    APPROVED --> EXPIRED: Deadline đã tới trước khi exchange
    DENIED --> [*]: Terminal, không cấp token
    EXPIRED --> [*]: Terminal, không cấp token
    CONSUMED --> [*]: Terminal, không phát lại token
~~~

Đây là **mô hình kiến trúc minh họa**, không phải tên bảng/trạng thái mà RFC buộc AS phải dùng. Một số AS có thể tiêu thụ grant ở bước khác; bất biến vẫn là **token chỉ cấp khi transaction được phê duyệt, còn hạn, đúng client và chưa được đổi trước đó**.

### Bất biến trạng thái

1. **PENDING không cấp token:** polling trả pending/slow_down, không có access token.
2. **DENIED là terminal:** không phát token cho device code đã bị từ chối.
3. **EXPIRED là terminal:** không phát token khi deadline đã tới, kể cả user bấm approve trễ.
4. **APPROVED chỉ có hiệu lực nếu còn hạn:** approval chưa được tiêu thụ và còn trong cửa sổ cho phép.
5. **CONSUMED không phát lại:** xử lý polling đồng thời trên nhiều AS instance phải bảo đảm không có hai kết quả cấp token trái chính sách.
6. **Client binding phải giữ nguyên:** không cấp token cho `client_id` khác chỉ vì biết device code.
7. **Response từ chối/expired không là refresh token:** không thử đổi mã terminal ở grant khác.

### “User chấp thuận vừa đúng lúc hết hạn” xử lý ra sao?

Đây là **race giữa approval và expiration**:

~~~text
deadline của transaction = 10:10:00 theo server time

10:09:59.900  User nhấn Cho phép
10:10:00.050  AS xử lý/commit approval
10:10:00.100  Device polling /token
~~~

Nếu transaction **đã expired trước khi approval được commit/được chấp nhận theo policy**, AS phải từ chối việc hồi sinh phiên đó. Nếu approval hợp lệ đã được ghi trước hạn, AS vẫn cần kiểm expiration tại **token issuance** theo cách triển khai đã cam kết. Không dựa vào timestamp do browser gửi hoặc đồng hồ của TV để quyết định grant hợp lệ.

AS nên định nghĩa **server-side authoritative deadline**, xử lý transition nguyên tử/serialized, dùng clock policy nhất quán giữa các replica; không để một node trả `expired_token` trong khi node khác phát access token từ cùng device_code sau deadline.

## 7. Phân biệt thời hạn mã device, mã người dùng và access token

Giả sử AS trả `expires_in=600` và `interval=5`. Đây là **thời hạn của authorization transaction**, không phải thời gian login của người dùng hay TTL của token về sau.

~~~text
T0:    AS phát device_code D1 + user_code U1
T0+5:  Device poll -> authorization_pending
T0+90: User mở verification_uri, chưa quyết định
T0+580: Device poll -> authorization_pending
T0+600: D1/U1 hết hạn
T0+610: Device poll -> expired_token (nếu vẫn gửi)

Nếu AS cấp token tại T0+120 sau approval:
  token response có expires_in riêng, ví dụ 900 giây
  RS kiểm access token expiry/audience/scope riêng
~~~

### Client tính hạn cục bộ ra sao?

Client nên theo dõi expiration bằng **đồng hồ đơn điệu (monotonic)** cho khoảng thời gian chạy, ưu tiên deadline **bảo thủ**. Nếu chỉ đặt deadline = “thời điểm nhận response + expires_in” có thể lạc quan hơn expiration thực tế tại AS, vì AS đã phát mã **trước khi response tới TV**. Có thể lấy thời điểm bắt đầu request làm mốc, trừ thêm safety margin cho network/scheduling.

\[
T_{\text{stop-local}} \le
T_{\text{request-start}} + \max(0,\ \texttt{expires\_in} - \Delta)
\]

Trong đó `Δ` là safety margin theo SLA/thời gian truyền (ví dụ vài giây); không có một giá trị cố định RFC bắt mọi thiết bị dùng. **AS luôn là nguồn quyết định cuối cùng** về hiệu lực code; client deadline chỉ để **dừng sớm** và tránh polling không cần thiết.

### Nếu user code và device code có “hạn khác nhau”?

Theo RFC 8628, trường `expires_in` mô tả thời gian hiệu lực **cả device code và user code**. Nếu hệ thống có UX/timeout nội bộ khác, nó vẫn không được cấp token ngoài **device authorization lifetime** đã công bố. Không tự gia hạn device_code chỉ vì user đã mở trang nhưng chưa bấm approve; không đổi `interval` hoặc `expires_in` của phiên cũ bằng request giả.

### Quy tắc dành cho thiết bị có đồng hồ sai

Thiết bị IoT có thể có wall clock không đồng bộ. Khi xác định thời gian giữa các lần polling và khoảng chờ còn lại, ưu tiên **elapsed time monotonic**; vẫn dùng HTTPS và validation cần thiết. Không “sửa” expired bằng cách chỉnh đồng hồ client; trạng thái hợp lệ do AS quyết định.

## 8. Denial là quyết định an ninh, không phải lỗi mạng

Người dùng có thể từ chối vì không nhận ra thiết bị, nghi bị lừa, không đồng ý scope, hoặc đơn giản không muốn kết nối. **`access_denied` phải được xem như quyết định ủy quyền**:

| Nguyên nhân | AS cần làm | Device cần làm |
|---|---|---|
| User bấm **Từ chối** | Ghi trạng thái DENIED/terminal, không cấp token | Dừng poll, thông báo từ chối không gây áp lực |
| User rời trang, chưa có quyết định | Giữ PENDING đến expiry hoặc theo policy | Poll chậm đúng interval; hết hạn thì dừng |
| User nhập user code đã hết hạn | Không cho approve code đó | Hiển thị mã mới **nếu user chủ động yêu cầu** |
| User nhập code không tồn tại | Không lộ grant/identity, kiểm tốc độ đoán mã | Không tự coi mã được cấp |
| Client nhận lỗi mạng | Giữ trạng thái cục bộ thận trọng | Backoff, không gán `access_denied` nếu AS chưa xác nhận |
| Client bị cancel local | Dừng UI/poll của client | Không tuyên bố AS đã DENIED nếu chưa có quyết định phía AS |

**Local cancel và AS denial là hai trạng thái khác nhau.** Một nút “Hủy” trên TV có thể đơn giản dừng polling và xóa code khỏi memory; RFC 8628 **không định nghĩa một revocation/cancel endpoint bắt buộc cho device authorization session đang PENDING**. Nếu sản phẩm muốn server-side cancel sớm, phải có API/policy riêng được bảo vệ và không giả định mọi AS hỗ trợ.

### Sau denial có phải revoke token không?

Nếu **chưa từng cấp access token** trong phiên, thì không có access token của phiên này để revoke. **Denial ngăn phát hành**, còn **OAuth Token Revocation (RFC 7009)** xử lý token/grant **đã phát hành**. Nếu device đã được cấp token trong một phiên cũ, từ chối **phiên mới** không tự thu hồi token cũ; logout/revoke cần được thiết kế riêng.

## 9. Thiết kế polling client an toàn: stop conditions và backoff

Một device client không nên triển khai:

~~~text
while (true) {
    POST /token (device_code)
    sleep(1 second)
}
~~~

Vòng lặp trên có thể vi phạm `interval`, bỏ qua `slow_down`, đốt quota, không dừng sau denial/expiry, và trở thành nguồn DoS cho AS nếu hàng nghìn thiết bị làm như vậy.

### Thuật toán polling đúng ý nghĩa RFC 8628

~~~text
session = deviceAuthorizationResponse
interval = session.interval nếu có, nếu không = 5 giây
deadline = local conservative deadline trước khi device_code hết hạn

while user chưa chủ động cancel:
    if deadline đã đến:
        stop; thông báo code đã hết hạn; không auto-start session mới

    wait ít nhất interval kể từ lần poll trước
    nếu deadline đã đến sau khi wait: stop

    result = POST /token với device_code, client binding
    nếu result = access_token response:
        stop polling; cất token an toàn và chuyển sang API
    nếu result = authorization_pending:
        giữ interval; tiếp tục tới lần poll hợp lệ kế
    nếu result = slow_down:
        interval = interval + 5 giây; tiếp tục tới lần poll kế
    nếu result = access_denied:
        stop; bỏ mã; hiển thị user đã từ chối
    nếu result = expired_token:
        stop; bỏ mã; hiển thị code hết hạn
    nếu result là network timeout/5xx:
        backoff theo chính sách; không poll nhanh hơn interval hiện hành
    nếu result là OAuth error khác:
        stop; xử lý lỗi theo chính sách; không tự coi là pending
~~~

**Lưu ý thời gian:** `interval` là khoảng **tối thiểu** giữa các lần polling, không phải lịch chính xác bắt buộc thiết bị luôn gửi đúng giây thứ N. Scheduler có thể chậm hơn, thêm jitter/backoff. Nếu polling mất vài giây, phải tính khoảng cách yêu cầu theo policy của AS; không gửi dồn những lần “bị lỡ” ngay khi kết nối trở lại.

### RFC-required và defensive policy

| Điều kiện | Yêu cầu hành vi |
|---|---|
| Không có `interval` trong device authorization response | Dùng **5 giây mặc định** theo RFC 8628 |
| `authorization_pending` | Chờ đủ khoảng polling trước khi lặp |
| `slow_down` | **Tăng thêm 5 giây** cho những lần sau |
| `access_denied` | **Không tiếp tục** gửi token request cho device code đã bị từ chối |
| `expired_token` | **Không tiếp tục** polling code cũ; có thể bắt đầu flow mới khi có người dùng tương tác |
| Access token response thành công | Dừng polling ngay; xử lý token theo profile |
| Network timeout/connection failure | **Giảm tần suất** polling, có thể dùng exponential backoff |
| HTTP 429/`Retry-After` | Phối hợp rate-limit policy, không vượt giới hạn `interval`/`slow_down` |
| Browser/local user bấm Hủy | Dừng polling client; không khẳng định AS đã DENIED nếu chưa xác minh |

### Tại sao không nên tự khởi động lại ngay sau `expired_token`?

Khi user mất điện thoại hoặc không quan tâm, một device tự gọi lại `/device_authorization` liên tục sau mỗi expiration sẽ:

- Tạo **nhiều user code mới** gây rối UI và gia tăng AS load.
- Kéo dài prompt đăng nhập ngoài mong muốn.
- Làm mất khả năng phân biệt người dùng **chủ động thử lại** với client spam.
- Tăng bề mặt social engineering vì mã mới cứ xuất hiện dù không có người dùng tương tác.

Thiết kế UX tốt là **“Mã đã hết hạn — Chọn Thử lại để tạo mã mới”**. Với CLI, cho phép lệnh rõ ràng hoặc xác nhận tương tác thay vì chạy vòng lặp vô hạn.

## 10. Java 17: poller tôn trọng denial, expiry và slow_down

Đoạn code sau là **mã minh họa tập trung vào state machine của client**, không phải SDK OAuth hoàn chỉnh. Giả định `TokenEndpoint` đã được triển khai bằng HTTP client đáng tin: HTTPS, client authentication/binding đúng registration, form encoding, parse status/JSON, timeout và **không log device code hoặc token**.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

final class DeviceCodePoller {

    enum Status {
        AUTHORIZATION_PENDING,
        SLOW_DOWN,
        ACCESS_DENIED,
        EXPIRED_TOKEN,
        SUCCESS,
        OTHER_ERROR
    }

    record DeviceSession(
        String clientId,
        String deviceCode,
        long expiresInSeconds,
        Long intervalSeconds
    ) {}

    record PollResult(Status status, String accessToken) {}

    interface TokenEndpoint {
        PollResult poll(String clientId, String deviceCode)
            throws Exception;
    }

    interface Cancellation {
        boolean isCancelled();
    }

    static String awaitAccessToken(
        DeviceSession session,
        TokenEndpoint endpoint,
        Cancellation cancellation
    ) throws Exception {
        if (session.expiresInSeconds() <= 0) {
            throw new IllegalStateException("Device code expired");
        }

        // Device response đã đi qua network. Trừ safety margin;
        // sản phẩm thực tế nên tính từ thời điểm request bắt đầu.
        long usableSeconds = Math.max(
            0L, session.expiresInSeconds() - 10L);
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(usableSeconds);

        // Theo RFC: nếu interval vắng mặt, dùng 5 giây.
        long interval = session.intervalSeconds() == null
            ? 5L
            : Math.max(1L, session.intervalSeconds());

        while (!cancellation.isCancelled()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new IllegalStateException("Device code expired");
            }

            long waitNanos = TimeUnit.SECONDS.toNanos(interval);
            if (remaining <= waitNanos) {
                // Không poll sát thời điểm code hết hạn.
                throw new IllegalStateException("Device code expired");
            }
            TimeUnit.NANOSECONDS.sleep(waitNanos);
            if (cancellation.isCancelled()) break;

            PollResult response = endpoint.poll(
                session.clientId(), session.deviceCode());

            switch (response.status()) {
                case AUTHORIZATION_PENDING -> {
                    // Giữ interval hiện hành.
                }
                case SLOW_DOWN -> {
                    // Áp dụng cho tất cả lần polling tiếp theo.
                    interval = Math.addExact(interval, 5L);
                }
                case ACCESS_DENIED ->
                    throw new IllegalStateException(
                        "User denied authorization");
                case EXPIRED_TOKEN ->
                    throw new IllegalStateException(
                        "Device code expired at server");
                case SUCCESS -> {
                    if (response.accessToken() == null ||
                        response.accessToken().isBlank()) {
                        throw new IllegalStateException(
                            "Invalid token response");
                    }
                    return response.accessToken();
                }
                default ->
                    throw new IllegalStateException(
                        "Non-retryable token endpoint error");
            }
        }
        throw new IllegalStateException("Authorization cancelled locally");
    }
}
~~~

**Giới hạn thiết yếu của ví dụ:**

- Mã dùng `Thread.sleep` qua `TimeUnit`, phù hợp để diễn giải state machine, **không phải lời khuyên chặn một thread cho mọi TV/CLI** trong server có hàng nghìn sessions. Production có thể dùng scheduler/non-blocking state machine.
- `System.nanoTime()` giúp đo khoảng thời gian đơn điệu trong JVM, nhưng deadline minh họa **được tính từ lúc nhận response**. Tốt hơn là ghi thời điểm **trước device authorization request**, trừ safety margin và xử lý `expires_in` theo hợp đồng AS. Không kéo dài hạn.
- `TokenEndpoint.poll` trong ví dụ không triển khai **network timeout/backoff, 429, OAuth JSON errors, correlation IDs**. Production phải xử lý lỗi mạng và giảm tần suất, không quay về loop poll nhanh.
- `Math.addExact` có thể báo lỗi tràn khi dữ liệu `interval` bất thường; client production cần **validate/cap input** và deadline. `expires_in`/`interval` phải được parse và kiểm hợp lệ.
- Không có `refresh_token`/ID token, client secret handling, DPoP/mTLS hay token storage trong `PollResult`. Những dữ liệu này cần được xử lý riêng nếu AS thực sự cấp.
- Dừng phía client **không bảo đảm transaction server-side đã bị hủy**. Một AS được quản trị đúng sẽ để transaction pending hết hạn nếu không có quyết định hoặc cơ chế cancel riêng.

### Vì sao dùng type `Status` thay vì kiểm chuỗi bằng `contains`?

Token endpoint có response **thành công** khác cấu trúc với OAuth **error**. Code production cần parse JSON, HTTP status và giá trị `error` một cách chính xác, không dùng:

~~~text
UNSAFE:
  if responseText.contains("pending") then retry
  if httpStatus == 400 then retry
  if body is not empty then assume success
~~~

Nếu chỉ thấy HTTP 400 rồi tiếp tục polling, client sẽ lặp vô hạn sau `access_denied`/`expired_token` và có thể mất tín hiệu cảnh báo `invalid_client`/`invalid_grant`.

## 11. Authorization Server: xử lý terminal state và concurrency

Một AS có thể lưu mỗi device authorization transaction với dữ liệu như:

| Trường nội bộ minh họa | Ý nghĩa |
|---|---|
| `transaction_id` | Khóa nội bộ duy nhất |
| `device_code_digest` | Giá trị tra cứu an toàn từ device code entropy cao |
| `user_code_lookup` | Lookup có kiểm soát và chống brute force |
| `client_id` | Client registration mà device authorization được cấp |
| `requested_scopes` / `resource` | Quyền/resource yêu cầu; phải được AS kiểm |
| `created_at` / `expires_at` | Server-side authoritative lifetime |
| `status` | PENDING, APPROVED, DENIED, EXPIRED, CONSUMED hoặc mô hình tương đương |
| `approved_subject` | Người dùng đã approve nếu thành công |
| `attempts` / `last_poll_at` / `poll_interval` | Rate limit user code/polling và `slow_down` |
| `version` | Tránh race giữa approve/deny/expire/consume |

Đây là **schema tham khảo**, không phải format do RFC 8628 bắt AS phải lưu. AS có thể lưu opaque code dưới dạng digest/HMAC tùy entropy và threat model, đồng thời kiểm truy cập database, retention và log.

### Mã giả cho authorization server

~~~text
createDeviceAuthorization(client, requestedScopes):
    validate client registration, scope/resource policy
    D = new high-entropy unique device_code
    U = new human-friendly user_code with uniqueness control
    expiresAt = authoritativeServerNow + configuredLifetime
    store transaction:
        D, U, client, requestedScopes, expiresAt, status=PENDING
    return device_code, user_code, verification_uri,
           expires_in, interval

verifyUserCode(user, U, decision):
    authenticate user on trusted AS site
    enforce rate limit and protect user_code lookup
    tx = lookup(U)
    if missing or tx.expired or tx.status != PENDING:
        show safe invalid/expired/terminal message
        do not re-activate tx
    display bound client/device, requested scopes and resource
    if user chooses DENY:
        atomically transition PENDING -> DENIED
    else if user explicitly APPROVES:
        atomically transition PENDING -> APPROVED with subject/grant

pollTokenEndpoint(client, D):
    validate actual client identity/binding
    tx = lookupByDeviceCode(D)
    if invalid binding: reject per OAuth security contract
    if serverNow >= tx.expiresAt:
        atomically mark EXPIRED if not already terminal
        return expired_token
    if tx.status == DENIED:
        return access_denied
    if tx.status == PENDING:
        enforce interval; return authorization_pending or slow_down
    if tx.status == APPROVED:
        atomically transition APPROVED -> CONSUMED
        issue tokens only for approved grant/client/resource/scopes
    if tx.status == CONSUMED:
        reject replay; do not issue another token
~~~

**Chú ý thứ tự kiểm và terminal status:** Đoạn mã giả ưu tiên `expiresAt` trước `DENIED` chỉ để minh họa một chính sách báo lỗi. Trong thực tế nếu mã đã bị DENIED rồi cũng qua hạn, AS phải bảo đảm **không phát token**; quyết định trả `access_denied` hay `expired_token` cần nhất quán với trạng thái/hợp đồng và không tạo kênh tiết lộ thông tin trái yêu cầu.

### Hai request polling cùng lúc sau approval

~~~text
AS state: APPROVED, code D1 chưa tiêu thụ

TV poll #A: D1 -> node AS-1
TV poll #B: D1 -> node AS-2

SAI:
  cả hai cùng thấy APPROVED -> cùng phát token/refresh token

ĐÚNG:
  atomic compare-and-set APPROVED -> CONSUMED
  tối đa một token issuance được chấp nhận theo policy
  request còn lại bị từ chối; không tạo grant thứ hai
~~~

Một transaction/DB consistency mechanism có thể dùng lock, CAS/version, transactional update hoặc mô hình phát hành có idempotency phù hợp; cần bảo đảm **token issuance và mark consumed** không để lại trạng thái bất nhất khi crash giữa hai thao tác. Đừng chỉ khóa trong process Java nếu nhiều replica.

### Race giữa approve, deny và expiry

Khi người dùng vừa bấm **Từ chối** còn một tab khác bấm **Cho phép**, AS phải chọn **một transition terminal hợp lệ theo thứ tự commit**. Không thể để PENDING -> DENIED rồi PENDING -> APPROVED sau đó do hai node ghi đè. Khi deadline đã tới, transaction **không được chấp thuận hồi tố**. Tests phải chạy cạnh tranh thực sự, không chỉ mock từng handler tuần tự.

## 12. Bảo mật `user_code`: chống brute force và remote phishing

Khác `device_code` entropy cao, `user_code` được thiết kế **ngắn/dễ gõ**. Vì vậy endpoint nhập user code là mục tiêu có thể bị **đoán mã trực tuyến**. AS phải kết hợp đủ entropy trong thời hạn sử dụng, giới hạn số lần đoán và rate limit theo nguồn/thiết bị/phiên có kiểm soát.

### Tấn công đoán user code

~~~text
Attacker:
  thử user_code AAAAAAAA
  thử user_code AAAAAAAB
  thử user_code AAAAAAAC
  ...

Nếu AS không rate-limit và user_code ít entropy:
  attacker có thể tìm được transaction đang PENDING
~~~

AS cần:

- Dùng mã đủ entropy cho thời hạn ngắn và số lượng phiên đồng thời.
- **Rate limit online guessing** theo nhiều tín hiệu (session/IP/thiết bị/client/user) và tránh làm nạn nhân bị khóa dễ dàng chỉ bằng ID tự khai.
- Không tiết lộ **mã này thuộc người dùng nào** hoặc dữ liệu profile cho người chưa xác thực.
- Không cho duyệt một request lạ bằng cách **tự động approve** khi code được nhận; bắt buộc đăng nhập và xác nhận consent rõ ràng.
- Làm các thông báo lỗi code sai/hết hạn phù hợp, không biến thành mã dò grant đang active.

### Remote phishing: attacker nhờ nạn nhân approve code của attacker

Một tình huống tinh vi:

~~~mermaid
sequenceDiagram
    autonumber
    participant X as Attacker có device X
    participant AS as Authorization Server
    participant U as Nạn nhân
    X->>AS: Xin device_code DX, user_code UX
    AS-->>X: DX + UX + verification_uri
    X->>U: "Đăng nhập để sửa tài khoản, nhập mã UX"
    U->>AS: Mở verification URI của AS, nhập UX
    AS->>U: Hiện client/device + scopes đang xin
    alt User phát hiện yêu cầu lạ
        U->>AS: Từ chối
        AS-->>X: access_denied khi polling
    else User bị đánh lừa và approve
        U->>AS: Cho phép
        AS-->>X: Token có thể được cấp cho device X
    end
~~~

**Không được nói “URL xác minh thuộc domain AS nên chắc chắn an toàn”.** Trang AS hợp lệ vẫn có thể nhận **mã do attacker tạo**. UX và chính sách của AS cần cảnh báo người dùng chỉ nhập code **đang hiển thị trên thiết bị do họ tự khởi tạo**, xác nhận **tên ứng dụng/thiết bị**, **scope**, và nếu phù hợp **mã đối chiếu/đặc điểm thiết bị**.

Người dùng nên được khuyến khích **bấm Từ chối** khi không nhận ra yêu cầu. Khi denial đã được ghi nhận, thiết bị của attacker chỉ nhận `access_denied`, không có quyền phát hành access token từ session đó.

### `verification_uri_complete` và QR code không miễn kiểm user intent

Một QR chứa user code giúp nhập nhanh nhưng có thể bị chèn vào email/chat giả mạo. AS không được tự động cho phép chỉ vì browser mở `verification_uri_complete`. Cần giữ tương tác xác thực/consent thích hợp và hiển thị rõ request mà người dùng đang phê duyệt.

## 13. Hạn chế leak khi vận chuyển mã và token

**`device_code` là giá trị nhạy cảm** vì ai có nó (và đáp ứng client binding) có thể hỏi token endpoint; nếu user approve sau đó, attacker sở hữu đúng code có thể tìm cách nhận token. Cần giữ device code khỏi URL, log và kênh hỗ trợ.

| Giá trị | Kênh phù hợp | Tránh |
|---|---|---|
| `device_code` | HTTPS POST device → AS token endpoint | Query URL, QR, clipboard chia sẻ, screenshot/log/analytics |
| `user_code` | Hiển thị trên device để người dùng nhập tại trang AS | Gửi cho người lạ, biến thành credential cho API, log không cần thiết |
| `verification_uri` | URL AS tin cậy hiển thị để mở bằng browser | URL do attacker chỉ định |
| `verification_uri_complete` | Link/QR tiện dụng nếu AS hỗ trợ và user kiểm nguồn | Tự động approve; log URL chứa mã trên nhiều hệ thống |
| **Access token sau cấp** | `Authorization: Bearer` tới đúng RS theo RFC 6750 hoặc proof-bound profile | Device code endpoint, query URL, log, API sai audience |
| **Refresh token nếu có** | Token endpoint của AS, lưu trữ bảo vệ theo client profile | Gửi cho RS, bỏ rotation/reuse detection |
| **OIDC ID token nếu có** | Client kiểm xác thực/issuer/audience theo OIDC | Gửi thay access token tới Resource Server |

### TLS và HTTP response caching

Device authorization endpoint và token endpoint phải dùng **HTTPS** được xác minh đúng. Token/authorization response chứa mã nhạy cảm không được đi qua HTTP cache không kiểm soát; ví dụ sử dụng `Cache-Control: no-store` và `Pragma: no-cache`. Proxy, APM, tracing và exception handling cần redact request body/response có chứa code/token.

**JWT access token có chữ ký vẫn có thể lộ claims** vì JWS không tự mã hóa payload. Khi RS nhận token, nó phải xác minh issuer, chữ ký/khóa hoặc introspection, audience, expiry, scope và quyền nghiệp vụ. **Không** suy quyền từ việc AS từng phát mã device hợp lệ.

## 14. Denial/expiration khác revoke, refresh và logout như thế nào?

| Sự kiện | Giai đoạn | Kết quả | Không đồng nghĩa với |
|---|---|---|---|
| `authorization_pending` | Trước approval | Chưa phát token, còn chờ | User đã từ chối hoặc mã hết hạn |
| `slow_down` | Trước approval, polling quá nhanh theo AS | Giảm nhịp poll; chưa phát token | Grant đã được cấp |
| `access_denied` | Authorization session | User/policy từ chối; dừng phiên | AS revoke mọi access token/phiên khác của account |
| `expired_token` | Device/user code lifetime | Mã device hết hạn; không phát token qua phiên này | JWT access token ở API hết `exp` |
| **Access token expiry** | Sau token issuance | RS từ chối token sau expiry | Device code hết hạn trong phiên mới |
| **Refresh token rotation** | Sau khi đã có grant/token, nếu AS cấp refresh token | Thay refresh token hiện hành; phát hiện reuse theo policy | Polling `device_code` |
| **RFC 7009 revocation** | Sau khi token/grant được cấp | AS xử lý yêu cầu thu hồi token/grant | User nhấn từ chối khi chưa được cấp token |
| **Local logout/cancel** | Client/session | Dọn dữ liệu/phiên ở client | AS đã nhận quyết định DENIED |

Nếu user từ chối phiên device **D2**, nhưng TV đã đăng nhập từ grant cũ **G1**, trạng thái token của G1 không tự thay đổi. Muốn TV ngừng sử dụng access token cũ, cần **logout/revocation** theo chính sách phù hợp. Không xóa token cũ chỉ vì một phiên kết nối mới bị denial, trừ khi sản phẩm chủ đích áp dụng chính sách bảo mật rộng hơn và thông báo rõ.

### Sau approval, AS có thể cấp JWT hoặc opaque access token

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "media-api",
  "client_id": "tv-client",
  "scope": "media:play",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Đây chỉ là **payload JWT minh họa**, không phải JWT đã ký. `sub` có thể là subject được xác thực qua thiết bị thứ hai theo profile; `client_id` mô tả client được cấp token. Bearer token hợp lệ vẫn có thể bị sao chép và phát lại tại Media API cho tới khi hết hạn hoặc bị RS chặn. **Device Authorization Grant không tự biến access token thành sender-constrained**; nếu threat model yêu cầu, cân nhắc DPoP/mTLS theo profile và hỗ trợ client/AS/RS.

## 15. Quan sát, cảnh báo và xử lý sự cố

Một hệ thống hỗ trợ hàng trăm nghìn TV/CLI cần biết **phiên nào pending quá lâu, có denial nào bất thường, polling có vượt quota không**, mà không để log trở thành kho chứa `device_code` và access token.

| Metric/audit | Nên ghi | Không nên ghi |
|---|---|---|
| `device_authorization_started` | Client registration đã xác minh, scope class, thiết bị/flow type, timestamp, request ID | Raw `device_code`, `user_code` |
| `device_authorization_approved` | Internal transaction ID, approved scope/subject metadata có ACL, thời điểm | Token response, plaintext user code |
| `device_authorization_denied` | Client, lý do policy class nếu thích hợp, thời điểm, correlation ID | Password, thông tin nhạy cảm của người dùng |
| `device_authorization_expired` | Số phiên expiry, nhóm client, khoảng chờ | Mã device dùng làm metric label |
| `device_poll_pending_total` | Tần suất pending theo client type | Raw device code |
| `device_poll_slow_down_total` | Số lần AS yêu cầu giảm nhịp | Secret/token và user code |
| `user_code_guess_denied` | Rate limit events, tín hiệu brute force có kiểm soát | Danh sách toàn bộ mã bị đoán |
| `device_code_replay_rejected` | Tỷ lệ mã consumed/terminal bị gửi lại | Giá trị device code nguyên bản |

Những metadata như subject ID, device ID và địa chỉ mạng có thể là dữ liệu cá nhân. Cần kiểm quyền truy cập audit log, retention hợp lý và ngưỡng cảnh báo tránh quá nhiều false positives.

### Tín hiệu đáng chú ý

- Một `client_id` liên tục mở session mới ngay sau `expired_token` mà không có hành động user.
- Tỷ lệ `slow_down` tăng cao vì thiết bị poll nhanh hơn `interval`.
- Một nguồn mạng thử rất nhiều `user_code` khác nhau.
- `access_denied` tăng sau khi client thay UX khiến người dùng không nhận ra device.
- Device authorization session đã marked EXPIRED nhưng AS khác vẫn cấp token.
- Token issuance thành công từ mã terminal đã từng bị ghi DENIED/CONSUMED.
- User phàn nàn bị yêu cầu nhập code mà họ không thấy trên thiết bị của mình (dấu hiệu phishing).

### Khi nghi có device code bị đánh cắp

1. Bảo vệ log/telemetry và nguồn rò; coi `device_code` là nhạy cảm.
2. Xác định client và transaction từ metadata **không cần xuất raw code ra báo cáo**.
3. Chặn phiên đang pending hoặc đã approve theo chính sách AS; nếu đã cấp access/refresh token, áp dụng **revoke ở AS/RS** thích hợp.
4. Kiểm liệu user bị lừa nhập code hay session được approve hợp lệ; phân biệt user intent với replay.
5. Đặt lại chính sách rate limit, TTL, token binding, UI và kiểm thử concurrency.

Không chỉ xóa màn hình mã trên TV rồi giả định AS đã xóa phiên. AS có trạng thái độc lập và có thể còn ghi nhận approval/token issuance tùy thời điểm.

## 16. Ma trận kiểm thử denial, expiration và polling

Giả định:

~~~text
Device client ID: tv-client (public)
Device authorization endpoint: https://auth.example.test/device_authorization
Token endpoint: https://auth.example.test/oauth2/token
Verification URI: https://auth.example.test/activate
expires_in = 600 giây
interval = 5 giây
Resource server: media-api
scope = media:play
~~~

| Tình huống | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| **Khởi tạo hợp lệ** | Public client đã đăng ký xin scope hợp lệ | AS trả device_code/user_code/verification_uri/expires_in, interval tùy chọn |
| **Thiếu `interval`** | Response không có interval | Client mặc định **5 giây** |
| **Poll quá sớm** | Gửi `/token` ngay sau device auth | Client phải tuân thủ interval; AS có thể trả `slow_down` |
| **User chưa phản hồi** | Client poll sau 5 giây | `authorization_pending`, không có access token |
| **User vẫn pending nhiều vòng** | AS liên tục trả pending | Client duy trì interval, dừng khi hết hạn |
| **`slow_down` một lần** | AS trả slow_down khi interval=5 | Các lần sau **ít nhất 10 giây** |
| **`slow_down` hai lần** | AS lại trả slow_down | Client tăng lên **ít nhất 15 giây**, không reset về 5 |
| **Network timeout** | Poll bị mất response | Giảm tần suất/backoff, không bắn dồn retry |
| **HTTP 429** | AS/edge rate limit | Tôn trọng backoff/`Retry-After` và hạn expiry |
| **User approve trước hạn** | AS ghi approve hợp lệ, client poll | Token cấp đúng client/grant, polling dừng |
| **User bấm Từ chối** | AS transition PENDING → DENIED | Token endpoint trả `access_denied`, client dừng |
| **User rời trang** | Không có quyết định | Pending đến expiry, rồi expired; không tự approve/deny |
| **Hết hạn khi đang PENDING** | Server clock ≥ deadline | `expired_token`; không cấp token |
| **Dùng mã sau expiration** | User nhập U1 tại AS khi U1 hết hạn | UI báo expired; không hồi sinh transaction |
| **Approval sát deadline** | Approve/expire đồng thời ở AS replicas | Có một trạng thái commit nhất quán, không cấp token sau terminal expiry |
| **Deny cạnh tranh approve** | Hai tab cùng thao tác trái ngược | Chỉ một transition hợp lệ, không approve sau DENIED |
| **Poll cạnh tranh sau approval** | Hai request cùng `device_code` | Không phát hai grant/token ngoài chính sách |
| **Poll sau consumed** | D1 đã đổi thành công, gửi lại | AS từ chối replay; không cấp token lần nữa |
| **Poll sau DENIED** | Client lặp request với D1 đã bị từ chối | Không cấp token; client đúng phải đã dừng |
| **Sai `client_id`** | Device code cấp cho client A, polling bằng client B | AS từ chối theo client binding, không tiết lộ token |
| **Confidential client sai credential** | Client yêu cầu xác thực nhưng cung cấp secret sai | Lỗi client authentication; không coi là pending |
| **`user_code` bị đoán** | Một nguồn thử mã hàng loạt | Rate limit và không lộ danh tính/grant |
| **Mã nhập nhầm** | User nhập U khác không tồn tại | Thông báo phù hợp, không approve session khác |
| **Remote phishing** | Attacker gửi mã của mình cho nạn nhân | UI AS hiển thị chính xác request; user có thể từ chối |
| **AS có downtime** | Mất mạng trước deadline | Client backoff, không kéo dài mã, không tuyên bố approved |
| **AS trả lỗi khác** | `invalid_client`/`invalid_grant` | Stop/xử lý lỗi theo chính sách; không retry như pending |
| **Local cancel** | Người dùng bấm Hủy trên TV | Device dừng polling, xóa trạng thái local; không giả định AS đã DENIED |
| **Expired không auto restart** | Client nhận `expired_token` | Dừng, hiển thị nút “Thử lại”; không mở phiên vô hạn |
| **JWT access token sai audience** | Token từ TV gửi tới API khác | Resource Server từ chối dù device grant đã approve |
| **Token bị lộ sau approval** | Attacker sao chép bearer access token | PKCE/device flow không chặn tự động; kiểm TTL/revoke/sender binding |
| **Log dữ liệu nhạy cảm** | Kiểm gateway/APM/exception | Không xuất raw device_code, token, client secret |

### Kiểm thử bằng đồng hồ giả và concurrency

Chỉ mock một polling request trả `expired_token` chưa đủ. Nên dùng **fake clock** phía AS và transaction store kiểm deadline chính xác, ví dụ:

~~~text
T0:     issue D1 (expires_at=T0+600s)
T0+599: device poll -> authorization_pending
T0+600: user clicks approve; concurrent expiration job
T0+601: device poll -> expired_token / terminal rejection

Assert:
  issued_access_tokens(D1) == 0
  session_state(D1) in {EXPIRED, terminal state no-issuance}
  no path can set transaction back to PENDING or APPROVED
~~~

**Test trên chỉ là kịch bản khi approval không được commit hợp lệ trước deadline.** Nếu approval đã hoàn tất trước hạn, test phải kiểm token issuance theo **chính sách hạn/tiêu thụ** của AS, không tuyên bố mọi approval sát hạn đều không hợp lệ. Chạy test concurrency trên nhiều AS node hoặc transaction layer thay vì chỉ `synchronized` trong một JVM.

## 17. Bài tập tình huống: smart TV, hai mã và một quyết định

Một TV đăng ký `client_id=tv-client`, AS trả:

~~~json
{
  "device_code": "D1-opaque-redacted",
  "user_code": "WJRD-KLHP",
  "verification_uri": "https://auth.example.test/activate",
  "expires_in": 600,
  "interval": 5
}
~~~

TV hỏi token endpoint tại các thời điểm:

| Giây từ T0 | Phản hồi | Ý nghĩa |
|---|---|---|
| 5 | `authorization_pending` | User chưa quyết định |
| 10 | `slow_down` | AS yêu cầu tăng polling interval |
| 20 | `authorization_pending` | Đang chờ ở interval mới 10 giây |
| 30 | `access_denied` | User đã bấm từ chối |

**Câu 1. Sau giây 30, TV có được tiếp tục poll với D1 tại giây 40, 50 không?**

**Không.** `access_denied` là terminal. Device phải dừng session này, bỏ D1 khỏi trạng thái đang sử dụng và hiển thị thông báo người dùng từ chối kết nối.

**Câu 2. Sau `slow_down` ở giây 10, có được quay lại interval 5 giây nếu lần sau là `authorization_pending` không?**

**Không.** RFC 8628 yêu cầu tăng interval **thêm 5 giây cho những lần polling về sau**. Ở ví dụ này, từ 5 lên ít nhất 10 giây, giữ mức tăng trừ khi có thay đổi tiếp theo từ AS/quota policy.

**Câu 3. Nếu user không phản hồi tới giây 600, TV nên làm gì?**

Dừng polling khi mã hết hạn theo deadline bảo thủ; nếu còn request gửi tới AS thì sẽ nhận `expired_token`. Hiển thị mã đã hết hạn và chỉ tạo phiên mới khi người dùng chủ động chọn thử lại.

**Câu 4. User bấm Cho phép trên điện thoại sau giây 600 và gửi lại cùng user code. Có được cấp token không?**

**Không.** AS phải kiểm thời hạn transaction theo server time và không hồi sinh D1/U1 đã expired; có thể cho bắt đầu một phiên mới **với code mới** nếu người dùng yêu cầu.

**Câu 5. Một người lạ gửi chính mã WJRD-KLHP qua tin nhắn và bảo An nhập để xác minh tài khoản. An có nên làm theo không?**

**Không.** An chỉ nên nhập mã đang hiển thị trên **thiết bị họ chủ động kết nối**, kiểm domain AS, tên ứng dụng/thiết bị và scope tại màn hình consent. Mã gửi qua tin nhắn có thể là user code của **device do attacker kiểm soát**.

**Câu 6. Khi AS trả `access_denied`, có cần gọi RFC 7009 để revoke token của phiên đang pending không?**

**Không có access token mới để revoke** nếu phiên chưa được cấp token. RFC 7009 áp dụng cho token/grant đã phát hành; token của các phiên cũ là chuyện khác.

**Câu 7. Nếu TV nhận được access token thành công trước hạn nhưng sau đó TV bị mất cắp, mã user_code có còn giúp người nhặt truy cập API không?**

**Không** theo ý nghĩa trực tiếp của user code đã consumed: quyền sử dụng API dựa vào **access token và chính sách RS**, không dựa vào user code. Cần bảo vệ token trên thiết bị, logout/revoke theo AS/RS và kiểm scope/audience/expiry.

**Câu 8. AS có thể cấp token hai lần khi hai request polling sau approval đến cùng lúc không?**

Không được tạo **hai lần token issuance ngoài chính sách** do race. Cần trạng thái `CONSUMED`/single-use được thực thi nguyên tử, xử lý network retry và idempotency thích hợp nếu AS hỗ trợ, không chỉ kiểm status rồi cập nhật sau.

## 18. Checklist trước khi đưa device authorization vào production

1. **Đúng grant:** Dùng RFC 8628 khi thiết bị không tiện browser/nhập liệu; không nhầm `device_code` với authorization code/PKCE hay access token?
2. **Đúng endpoint:** Device authorization endpoint phát mã; token endpoint nhận `urn:ietf:params:oauth:grant-type:device_code`?
3. **Client binding:** `device_code` gắn client registration và grant; confidential client xác thực theo cấu hình nếu cần; `client_id` public không phải password?
4. **Response đầy đủ:** Có `device_code`, `user_code`, `verification_uri`, `expires_in`; `interval` tùy chọn và mặc định 5 giây nếu vắng?
5. **Mã sinh an toàn:** Device code entropy cao; user code ngắn nhưng đủ entropy/rate limit cho cửa sổ hoạt động?
6. **Trang xác minh an toàn:** AS domain đáng tin, user authentication, client/device/scopes hiển thị rõ, không auto-approve từ QR/URI?
7. **Polling không vượt quota:** Chờ đủ interval, tăng thêm 5 giây mỗi `slow_down`, giảm tần suất khi network timeout?
8. **Stop đúng lỗi:** `authorization_pending`/`slow_down` có thể tiếp tục; `access_denied`/`expired_token` là terminal, không retry code cũ?
9. **Deadline do AS quyết định:** Cả mã user/device cùng lifetime `expires_in`, local deadline bảo thủ và không phụ thuộc wall clock thiết bị?
10. **Concurrency được kiểm:** Approve/deny/expire/consume có CAS/transaction; không cấp token sau terminal hoặc cấp hai grant do race?
11. **Không tạo vòng lặp vô hạn:** Sau expiration/denial không tự tạo mã liên tục; có nút thao tác thử lại rõ ràng?
12. **Phân biệt cancel với denial:** Local cancel dừng UI/poll, không giả định có chuẩn cancel API hay AS đã từ chối?
13. **Bảo vệ social engineering:** User biết chỉ nhập mã từ device mình chủ động thao tác; AS cảnh báo mã lạ/thiết bị không nhận ra?
14. **Không log secrets:** Device code, access/refresh token, client secret không xuất hiện trong URL/APM/tracing; hạn chế QR chứa mã nhạy cảm?
15. **Token sau issuance được bảo vệ:** Bearer/JWT/opaque RS kiểm `iss`, `aud`, `exp`, `scope` và quyền object; refresh token storage/reuse detection theo profile?
16. **Revocation được hiểu đúng:** Denial phiên chưa cấp token không revoke phiên cũ; logout/sự cố phải xử lý AS/RS theo RFC 7009/chính sách?
17. **Chịu lỗi AS và mạng:** Có timeout/backoff/429 handling, không nới deadline hoặc fail-open khi mất kết nối?
18. **Test đường tấn công:** User code brute force, mã lạ, remote phishing, expired approval race, cross-client device code, replay, multi-node AS và token leak?

**Ghi nhớ:** Với OAuth 2.0 Device Authorization Grant, **`authorization_pending` nghĩa là chưa có quyết định**, **`slow_down` nghĩa là phải tăng khoảng cách polling**, **`access_denied` nghĩa là user/policy đã từ chối**, còn **`expired_token` nghĩa là phiên device authorization đã hết hạn**. **Hai lỗi sau là terminal**: client không tiếp tục dùng mã cũ để lấy token. AS phải bảo đảm expiration, denial, approval và token issuance có **trạng thái đáng tin và không race**; client phải tôn trọng interval, dừng đúng lúc và bảo vệ code. Sau khi được cấp, **access token vẫn phải được Resource Server xác minh, lưu giữ và thu hồi theo cơ chế riêng** — device flow không thay token security.

### Chuẩn và tài liệu tham khảo

- **RFC 8628 — OAuth 2.0 Device Authorization Grant:** `device_code`/`user_code`, `verification_uri`, `expires_in`, `interval`, `authorization_pending`, `slow_down`, `access_denied`, `expired_token` và các cân nhắc bảo mật user-code/phishing.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** vai trò OAuth, token endpoint, client authentication, error handling và authorization grants.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** các lớp bảo vệ token, refresh token, client và ủy quyền trong OAuth.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** truyền bearer access token và hậu quả bị đánh cắp.
- **RFC 7662 — OAuth 2.0 Token Introspection:** RS kiểm trạng thái opaque/reference access token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant đã phát hành, không đồng nghĩa denial chưa phát token.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp` và giới hạn JWT self-contained.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token và validation tại RS.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** bảo vệ sender-constrained access token khi profile/client hỗ trợ.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication và certificate-bound tokens.
- **OpenID Connect Core 1.0:** phân biệt ID token và access token khi AS/OP hỗ trợ OIDC.
