# Device code reuse

Trong **OAuth 2.0 Device Authorization Grant (RFC 8628)**, một thiết bị khó nhập liệu hoặc không có trình duyệt đầy đủ (TV thông minh, máy in, thiết bị IoT hoặc CLI) có thể đăng nhập bằng cách hiển thị **mã người dùng** để chủ sở hữu mở một trình duyệt khác và phê duyệt quyền. Thiết bị nhận một **`device_code`** bí mật từ authorization server (AS), dùng mã này **lặp lại có kiểm soát** khi hỏi token endpoint xem người dùng đã hoàn tất xác thực/ủy quyền chưa.

Vậy **device code reuse** là đúng hay sai? Câu trả lời phụ thuộc vào **trạng thái giao dịch**. Trong khi phiên đang chờ phê duyệt, gửi nhiều yêu cầu polling với **cùng `device_code`** là cách giao thức được thiết kế. Nhưng khi code đã được **đổi thành token, hết hạn, bị từ chối hoặc hủy**, việc tiếp tục dùng code ấy để lấy token mới không được cho phép. Việc phân biệt **polling hợp lệ**, **replay**, **dùng lại `user_code`** và **device-code phishing** là thiết yếu.

Bài **“Device code reuse”** thuộc chương **Device authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối vòng đời device authorization với mô hình tin cậy OAuth 2.0/OIDC, access/refresh token, JWT/opaque token, issuer, audience, scope, lưu trữ, thu hồi và các biện pháp phòng chống code/token theft hoặc phát lại.

> **Quy tắc cốt lõi:** **Reuse cùng `device_code` khi `authorization_pending` là polling hợp lệ; reuse sau một lần đổi code thành công không được phát thêm token.** AS phải ràng buộc code với giao dịch/client, áp thời hạn, polling rate limit và bảo đảm chuyển trạng thái cuối cùng một cách nguyên tử.

## 1. Đặt device authorization vào đúng vai trò OAuth 2.0

Device Authorization Grant có bốn vai trò OAuth logic:

| Vai trò | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Resource owner** | Người dùng sở hữu tài khoản | Dùng trình duyệt thuận tiện để đăng nhập, xét consent |
| **OAuth client (device)** | TV/CLI/thiết bị đầu cuối | Xin `device_code`, hiển thị `user_code`, polling token endpoint |
| **Authorization server (AS/OP)** | Hệ thống cấp token/OIDC Provider | Phát cặp mã, xác thực user, xét grant, cấp token một lần |
| **Resource server (RS)** | API phát video, quản lý tài khoản | Xác minh access token và quyền truy cập tài nguyên |

**Client thiết bị** thường là **public client**: việc nhúng client secret vào firmware/app chạy trên phần cứng người dùng không biến nó thành bí mật. Tuy nhiên, một số client triển khai trong môi trường bảo vệ có thể là **confidential client** và phải xác thực theo registration.

**Không đồng nhất thiết bị với người dùng:** một TV chưa có user session chỉ đang **yêu cầu phê duyệt**. Không có quyền API cho đến khi AS cấp access token, và resource server kiểm tra token đúng mục đích.

## 2. Hai mã `device_code` và `user_code` không giống nhau

AS thường phát hai giá trị tương ứng với **một phiên authorization**:

| Trường | Ai giữ/sử dụng? | Mục đích | Mức độ nhạy cảm |
| --- | --- | --- | --- |
| **`device_code`** | Device client; gửi tới **token endpoint** | Xác định giao dịch để polling/đổi lấy token | **Credential bí mật**; không hiển thị, không log |
| **`user_code`** | Hiển thị cho user; nhập tại **verification URI** | Tìm giao dịch mà user muốn phê duyệt | Có thể hiển thị, nhưng cần chống đoán/phishing |
| **`verification_uri`** | Người dùng mở trên thiết bị thứ hai | Trang AS xác thực và nhận user code | Phải là origin AS tin cậy |
| **`verification_uri_complete`** | Link/QR đầy đủ khi AS hỗ trợ | Hỗ trợ không cần nhập thủ công code | Không thay xác thực/consent; phải xem xét phishing |
| **`expires_in`** | Client và AS | Giới hạn thời gian giao dịch | Không kéo dài bởi polling |
| **`interval`** | Device client | Khoảng cách tối thiểu giữa các lần polling | Phải tôn trọng, có thể tăng nếu `slow_down` |

**Không dùng `user_code` để gọi token endpoint** thay `device_code`. Ngược lại, không gửi `device_code` cho người dùng để họ nhập trong trình duyệt. Tách biệt hai mã giúp mã người dùng dễ nhập mà không phải công khai credential polling dài, khó đoán.

### 2.1. Tại sao `user_code` ngắn hơn?

Người dùng TV có thể phải gõ mã bằng điện thoại; do đó user code thường tương đối ngắn, dễ đọc và tránh ký tự dễ nhầm. AS phải bù cho không gian mã nhỏ hơn bằng:

- Sinh ngẫu nhiên đủ entropy theo threat model;
- Giới hạn số lần đoán tại verification endpoint;
- Hết hạn ngắn, one-time approval, chống enumeration;
- Không tiết lộ tài khoản, thiết bị hoặc grant khi code sai;
- Giám sát hành vi gửi nhiều code bất thường.

**Không dùng `user_code` làm mật khẩu đăng nhập.** Việc biết user code chỉ xác định giao dịch đang chờ; người dùng vẫn phải xác thực với AS và tự xét quyền.

## 3. Luồng thiết bị theo RFC 8628

~~~mermaid
sequenceDiagram
    autonumber
    participant D as TV / Device client
    participant AS as Authorization server
    actor U as Người dùng
    participant B as Browser trên điện thoại
    participant API as Resource server
    D->>AS: POST device_authorization (client_id, scope)
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>U: Hiển thị URI, user_code và thời gian còn lại
    D->>AS: POST token endpoint, device_code (poll 1)
    AS-->>D: authorization_pending
    U->>B: Mở đúng trang AS, nhập user_code
    B->>AS: Login và consent cho yêu cầu của thiết bị
    AS->>AS: Ràng buộc phê duyệt với đúng giao dịch
    D->>AS: POST token endpoint, cùng device_code (poll 2)
    AS-->>D: Access token (và token khác nếu policy cấp)
    D->>D: Dừng polling, đánh dấu giao dịch hoàn tất
    D->>API: Authorization Bearer access token
    API->>API: Validate token và quyền tài nguyên
~~~

**Điểm đáng chú ý:** Poll 1 và Poll 2 dùng **cùng một `device_code`**. Đây **không phải** lỗi triển khai. AS không được đánh dấu code “đã tiêu thụ” chỉ vì một lần polling khi user chưa hoàn tất authorization.

### 3.1. Device authorization request

URL thực tế do AS công bố/đăng ký, ví dụ `https://auth.example.com/oauth2/device_authorization`. Request minh họa:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=tv-player&scope=openid%20profile%20media.read
~~~

Ở đây `client_id` định danh client đã đăng ký. Nếu là confidential client theo registration, AS yêu cầu **client authentication** phù hợp; public client không giữ secret an toàn chỉ vì có client ID.

### 3.2. Phản hồi phát cặp mã

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "device_code": "<high-entropy-opaque-device-code>",
  "user_code": "WBJD-HQPK",
  "verification_uri": "https://auth.example.com/activate",
  "verification_uri_complete": "https://auth.example.com/activate?user_code=WBJD-HQPK",
  "expires_in": 600,
  "interval": 5
}
~~~

Đây là các giá trị **minh họa**. Theo RFC 8628, `verification_uri_complete` và `interval` là tùy chọn; nếu không có `interval`, client dùng **5 giây** làm khoảng polling mặc định. `expires_in` và `device_code`/`user_code`/verification URI là dữ liệu quan trọng phải được client xử lý chính xác.

**Không log response này nguyên vẹn.** `device_code` là credential đủ để polling; `user_code` và complete URI có thể hỗ trợ phishing nếu lộ hoặc bị kẻ khác gửi cho người dùng.

### 3.3. Màn hình thiết bị nên hiển thị gì?

Ví dụ:

~~~text
KẾT NỐI TÀI KHOẢN

Trên điện thoại/máy tính, truy cập:
  https://auth.example.com/activate

Nhập mã:
  WBJD-HQPK

Hết hạn trong: 10 phút

Chỉ phê duyệt nếu chính bạn đang đăng nhập trên thiết bị này.
~~~

Không hiển thị `device_code`, `client_secret`, access token hoặc refresh token trong UI/logs. Nếu dùng QR của `verification_uri_complete`, vẫn phải kiểm tra domain AS và bảo đảm user nhận biết mình đang phê duyệt **đúng client/thiết bị**.

## 4. Token polling: reuse hợp lệ trong trạng thái PENDING

Device client polling đến token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code
&device_code=<original-device-code>
&client_id=tv-player
~~~

Request body trên được xuống dòng chỉ để đọc; form thực tế phải encode đúng. Confidential client có thể phải gửi **Basic/JWT assertion/mTLS authentication** theo registration. `grant_type` là giá trị chuẩn `urn:ietf:params:oauth:grant-type:device_code`, **không phải** `authorization_code` hoặc `client_credentials`.

Khi user chưa phê duyệt:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"authorization_pending"}
~~~

Client **không xin device code mới sau mỗi `authorization_pending`**. Nó chờ đúng khoảng `interval`, rồi lặp lại **cùng device code**. Tạo device code mới liên tục sẽ sinh nhiều giao dịch chờ, gây quá tải, làm UI/code không khớp và mở thêm bề mặt phishing.

### 4.1. Polling khác replay ra sao?

| Hoạt động | Trạng thái AS | Hành vi đúng |
| --- | --- | --- |
| Polling lần đầu | PENDING | Trả `authorization_pending` |
| Polling lần hai sau `interval` | PENDING | Tiếp tục trả `authorization_pending` |
| Polling quá nhanh | PENDING | Có thể trả `slow_down`/rate-limit theo policy |
| Polling khi đã APPROVED | APPROVED, chưa consume | **Một** lần exchange thành công, AS consume grant/code |
| Polling lại sau exchange thành công | CONSUMED | **Không cấp thêm access/refresh token** |
| Polling sau khi user từ chối | DENIED | Không cấp token; terminal error |
| Polling sau hết hạn | EXPIRED | Không cấp token; thường `expired_token` |
| Polling bằng code bị hủy | CANCELLED/REVOKED | Không cấp token, báo lỗi theo contract |

**Sai lầm cần tránh:** Một hệ thống anti-replay đơn giản `if device_code đã thấy => reject` sẽ **phá hỏng giao thức**, bởi nó từ chối lần polling thứ hai hợp lệ khi user còn đang xác thực.

## 5. State machine: device code được dùng đến khi nào?

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: AS phát device_code và user_code
    PENDING --> PENDING: Polling hợp lệ, authorization_pending
    PENDING --> APPROVED: User xác thực và phê duyệt
    PENDING --> DENIED: User từ chối
    PENDING --> EXPIRED: expires_in kết thúc
    PENDING --> CANCELLED: Client/AS hủy theo policy
    APPROVED --> CONSUMED: Một exchange thành công
    APPROVED --> EXPIRED: Chưa exchange đến khi hết hạn
    DENIED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    CONSUMED --> [*]
~~~

Sơ đồ là **mô hình triển khai tham khảo**; RFC 8628 không bắt buộc các tên enum trong database. Những bất biến cần giữ:

1. `device_code` liên kết **duy nhất với một authorization transaction**, client registration, scopes/resource và expiry.
2. `user_code` chỉ tìm được **đúng transaction** và không thể tái gắn sang client/thiết bị khác.
3. Polling khi PENDING **không tiêu thụ** code.
4. Khi APPROVED, tối đa **một** exchange thành công được quyền phát token từ transaction.
5. DENIED/EXPIRED/CANCELLED/CONSUMED là các trạng thái **không còn cấp token** từ device code.
6. Mọi chuyển trạng thái phải chịu kiểm tra **expiry tại thời điểm quyết định**, không dựa vào đồng hồ hiển thị trên TV.
7. User code và device code cần **hết hiệu lực cùng transaction** theo contract; không hồi sinh một transaction cũ bằng request mới.

### 5.1. Approval không đồng nghĩa code đã tiêu thụ

User nhập `user_code` và nhấn Đồng ý → AS đánh dấu transaction đã **APPROVED**. Nhưng thiết bị có thể chưa polling lần tiếp theo; nếu AS chuyển sang CONSUMED ngay ở bước browser approval, thiết bị sẽ không đổi được token. **Consume xảy ra tại token exchange thành công**, không phải ngay tại nút Approve.

### 5.2. Dùng lại code sau CONSUMED không phải refresh

Nếu device client cần token mới sau khi access token hết hạn, nó sử dụng **refresh token grant nếu AS đã cấp refresh token và policy cho phép**, hoặc bắt đầu **device authorization mới**. Không được dùng lại `device_code` đã hoàn tất như một refresh token.

## 6. Xử lý các polling errors theo RFC 8628

RFC 8628 định nghĩa các kết quả quan trọng cho token endpoint:

| `error` | Ý nghĩa | Client nên làm gì? |
| --- | --- | --- |
| **`authorization_pending`** | User chưa hoàn thành authorization | Chờ tối thiểu `interval` trước khi poll lại |
| **`slow_down`** | Client polling quá nhanh hoặc AS yêu cầu giảm tần suất | **Tăng interval ít nhất 5 giây** cho lần hiện tại và những lần sau |
| **`access_denied`** | User từ chối yêu cầu | **Dừng polling**; báo từ chối, không dùng lại code |
| **`expired_token`** | Device code đã hết hạn | **Dừng polling**, yêu cầu flow mới nếu user muốn |
| **`invalid_client`** | Client authentication thất bại | Dừng/giải quyết cấu hình credential, không retry nóng |
| **`invalid_grant`** hoặc lỗi khác | Code/grant không hợp lệ, đã dùng hoặc lỗi chính sách tùy AS | Không cố phát lại vô hạn; dừng theo xử lý lỗi |

Ví dụ `slow_down`:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"slow_down"}
~~~

Nếu interval ban đầu 5 giây, sau `slow_down` client phải tăng thành **ít nhất 10 giây** cho lần polling này và các lần tiếp theo. Nếu AS lại yêu cầu `slow_down`, tăng thêm ít nhất 5 giây nữa theo RFC.

### 6.1. Không poll ngay sau `authorization_pending`

Sai:

~~~text
while true:
    POST /token?device_code=D
    if authorization_pending: retry immediately
~~~

Đúng theo ý tưởng:

~~~text
interval = interval_from_AS_or_5_seconds
while transaction_is_pending_and_not_expired:
    wait_at_least(interval)
    response = POST_token_with_same_device_code()
    if response == authorization_pending:
        continue
    if response == slow_down:
        interval += 5_seconds
        continue
    if response == success:
        stop_polling_and_securely_store_token()
    else:
        stop_and_report_terminal_error()
~~~

Với **network timeout/connection failure**, RFC 8628 còn khuyến nghị **giảm tần suất polling**, ví dụ exponential backoff; không tăng tải AS khi kết nối không ổn định. Retry sau timeout có thể xảy ra khi AS đã xử lý yêu cầu nhưng response bị mất: vì vậy **AS phải chống cấp token trùng khi device code đã CONSUMED**.

### 6.2. `interval` không được làm reset `expires_in`

`expires_in=600` nghĩa là thời gian sống của giao dịch tại thời điểm phát mã. Polling hay `slow_down` **không tự kéo dài** deadline. Client cần dừng khi hết thời gian, kể cả đang chờ response.

### 6.3. Các mã lỗi HTTP không chỉ dựa vào status

Token endpoint thường trả **HTTP 400 + JSON `error`** cho những kết quả đang chờ hoặc bị từ chối. Client phải parse **OAuth error code**, không coi mọi HTTP 400 là lỗi cấu hình cần xin device code mới, và không coi HTTP 200 là thành công nếu response JSON thiếu các trường token cần thiết.

## 7. Reuse nguy hiểm: cùng `device_code` sau khi đổi token

Sau khi user approve, một poll thành công có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "media.read"
}
~~~

Nếu AS trả cả refresh token, điều đó phụ thuộc **grant, consent và chính sách**; RFC 8628 không yêu cầu mọi device authorization response có refresh token.

Lúc này:

- AS **đánh dấu device transaction đã tiêu thụ**;
- Device client dừng polling và bảo vệ token;
- `device_code` không còn quyền xin token khác;
- `user_code` không thể dùng lại để phê duyệt phiên mới;
- Quyền API phụ thuộc **access token thực tế** được cấp, không phụ thuộc user code từng hiển thị.

**Nếu token response bị mất trên mạng:** client có thể vô tình gửi lại cùng device code. AS phải **không tạo một token set mới** từ code đã tiêu thụ. Client nên xử lý thất bại an toàn và khởi tạo device flow mới khi cần; không tự xem một response retry là chắc chắn idempotent nếu AS không có contract cụ thể.

### 7.1. Hai pollers tranh nhau token

Một lỗi dễ gặp khi app có **hai threads, hai browser tabs, hai instances hoặc retry queue** đều polling cùng code:

~~~mermaid
sequenceDiagram
    autonumber
    participant P1 as Poller A
    participant AS as Authorization server
    participant P2 as Poller B
    Note over AS: device_code D ở APPROVED
    P1->>AS: POST /token D
    P2->>AS: POST /token D gần đồng thời
    AS->>AS: Atomic claim/consume D
    AS-->>P1: 200 + token set
    AS-->>P2: Từ chối: D đã consumed
~~~

Không được tạo tình huống cả A và B đều nhận **hai token sets khác nhau** từ cùng device code. Tính one-time phải được enforce **ở AS**, không chỉ bằng UI device hoặc `synchronized` trong một JVM.

### 7.2. Điều AS cần làm khi thấy code đã dùng

AS nên trả lỗi phù hợp với trạng thái và contract (ví dụ `invalid_grant` với code đã tiêu thụ), **không rò token set đã phát**, refresh token hay thông tin chủ tài khoản trong lỗi. Cần audit và có thể cảnh báo nếu observed replay patterns bất thường.

**Chú ý:** Lặp lại polling khi PENDING là hợp lệ; chỉ khi đi vào trạng thái terminal, việc lặp lại không được cấp thêm quyền.

## 8. Atomic consumption ở Authorization Server

AS cần tránh TOCTOU (*time-of-check to time-of-use*): hai request cùng đọc `APPROVED` rồi đều phát token trước khi đặt `CONSUMED`.

### 8.1. Bản ghi transaction tối thiểu

Một mô hình dữ liệu khái niệm:

~~~text
DeviceGrant:
  id                 (random internal identifier)
  device_code_hash   (lookup key)
  user_code_hash     (verification lookup key)
  client_id
  requested_scope
  granted_scope
  resource_audience
  status             PENDING/APPROVED/DENIED/EXPIRED/CONSUMED
  expires_at
  approved_subject
  approved_at
  consumed_at
  polling_interval
  last_poll_at
~~~

Đây **không phải schema bắt buộc** của RFC 8628. Nếu lưu code dưới dạng hash/HMAC, phải tránh để lookup và logs lộ secret; user code entropy thấp cần **rate limit** ngay cả khi được hash.

### 8.2. Transaction/row lock để phát token một lần

Pseudocode SQL, cố ý lược bỏ cú pháp phụ thuộc database:

~~~sql
BEGIN;

SELECT *
FROM device_grants
WHERE device_code_hash = :lookup_hash
FOR UPDATE;

-- Ứng dụng kiểm tra dưới cùng transaction:
-- 1. client_id/client auth khớp registration;
-- 2. expires_at > current DB time;
-- 3. status = APPROVED;
-- 4. subject, scopes, audience và grant policy hợp lệ.

UPDATE device_grants
SET status = 'CONSUMED', consumed_at = CURRENT_TIMESTAMP
WHERE device_code_hash = :lookup_hash
  AND status = 'APPROVED'
  AND expires_at > CURRENT_TIMESTAMP;

-- Yêu cầu affected_rows = 1.
-- Tạo/lưu kết quả cấp grant/token phù hợp,
-- duy trì tính nhất quán khi transaction commit.

COMMIT;
~~~

Đoạn này minh họa **atomic state transition**, chưa phải hệ thống token issuer hoàn chỉnh. Trong hệ thống thật, phải thiết kế thứ tự **persist authorization grant/token issuance** và commit sao cho failure không làm code bị consume mà không thể phục hồi theo chính sách. Không gửi token ra mạng trước khi trạng thái giao dịch đã được commit bền vững.

### 8.3. Nếu dùng Redis hoặc nhiều AS nodes

Đối với một **device grant**, thao tác claim `APPROVED → CONSUMED` cần atomic (ví dụ database transaction, compare-and-set hoặc script Redis bảo đảm nguyên tử). Nếu Redis có failover/replication async, cần tính đến durability, duplicate processing khi failover; **một lock TTL đơn giản không tự bảo đảm exactly-once token issuance**.

Các invariants quan trọng:

- Cùng device code không thể được claim thành công **hai lần**.
- Không cấp token khi giao dịch chưa approved hoặc đã expired.
- Client ID/client authentication phải khớp **client gắn với code**.
- Khi có token được cấp, trạng thái tiêu thụ phải bền vững và có audit.
- Nếu user deny/AS revoke, không có đường quay lại approved chỉ nhờ poll cũ.

## 9. User code reuse: phê duyệt lặp lại có nguy hiểm không?

`user_code` được nhập trên trang AS để tìm **một** device authorization transaction. Nó **không phải token** và không đủ để tự lấy access token ở token endpoint. Nhưng thiết kế sai có thể làm mã này bị dùng lại để phê duyệt nhiều giao dịch hoặc dùng code đã expired.

### 9.1. Trạng thái trang verify nên xử lý

| User nhập code | Trạng thái transaction | Phản ứng an toàn |
| --- | --- | --- |
| Code đúng, giao dịch đang PENDING | PENDING | Hiển thị client/scopes/device context, yêu cầu login/consent |
| User submit consent lần hai ngay trước poll | APPROVED | Không tạo grant/phê duyệt khác; UI có thể thông báo đã xử lý |
| Code đã đổi token xong | CONSUMED | Không cấp token thêm, không cho reuse |
| Code bị từ chối | DENIED | Không bật lại session; cần flow mới |
| Code hết hạn | EXPIRED | Không phê duyệt; yêu cầu thiết bị tạo mã mới |
| Code không tồn tại hoặc không khớp | Không hợp lệ | Thông báo chung và rate limit, tránh enumeration |

**Đừng dùng user code làm key cho một global “đã đăng nhập” flag** có thể ảnh hưởng một device khác. Mọi approval phải được ràng buộc với **đúng transaction và client**; khi code hết hạn không được chuyển kết quả sang mã khác.

### 9.2. Có thể phát lại cùng `user_code` cho transaction mới không?

Không nên **tái sử dụng có chủ đích** một user code còn có thể được người dùng/thiết bị ghi nhớ hoặc nằm trong cửa sổ hiệu lực. AS nên sinh code ngẫu nhiên mới, kiểm tra collision trong **tập active codes**, áp timeout/cooldown theo threat model, không để một code trỏ tới hai transactions đồng thời.

Vì user code ngắn, về mặt xác suất **không thể bảo đảm không bao giờ trùng mã trong suốt nhiều năm**. Mục tiêu là không tạo nhầm lẫn hoặc chuyển authorization giữa **các giao dịch đang có thể được chấp nhận**, đồng thời hạn chế phishing và đoán mã.

## 10. Client binding: một device code không thể đổi cho client khác

AS cần gắn device code với **OAuth client registration** khi phát hành. Nếu attacker lấy device code của `tv-player` rồi thử:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code
&device_code=<code-issued-to-tv-player>
&client_id=attacker-app
~~~

AS phải từ chối vì **client không khớp giao dịch**, kể cả user đã approve. Với confidential client, token endpoint còn phải xác thực secret/key/certificate của **đúng client**.

`client_id` do public client gửi là định danh, **không phải secret**. Device code là credential bí mật của một giao dịch, nhưng **không tự biến public client thành confidential client**. Bảo vệ device code, client binding, thời hạn và approval/consent cùng nhau.

### 10.1. Scope và resource không được thay khi polling

AS không cho caller thêm `scope=admin` hoặc `resource=payments-api` trong token polling để mở rộng grant ban đầu. Scopes và resource audience đã được xin/chấp nhận theo AS policy và approval tương ứng.

Client đăng ký `media.read`, được user approve `media.read`, thì access token chỉ được cấp quyền tương ứng. Nếu token audience là Media API, Orders API phải từ chối token đó dù cùng issuer.

## 11. Expiry, clock và mã sống lâu bất thường

Vì device code là một credential có thể bị đánh cắp, **thời hạn ngắn** giảm cửa sổ tấn công. `expires_in` trong response là số giây còn hiệu lực; AS phải lưu expiry và kiểm tra **theo thời gian đáng tin của server**.

Ví dụ:

~~~text
12:00:00  AS phát D, expires_in=600
12:05:00  User chưa approve, device tiếp tục poll
12:09:55  User approve
12:10:01  Device poll -> từ chối vì D đã hết hạn
~~~

Đừng cho phép `APPROVED` “vượt” `expires_at` rồi cấp token sau hạn, trừ khi profile/hợp đồng quy định khác một cách có kiểm soát. Với thiết kế cơ bản, expiry phải được kiểm tra ở cả bước user approval **và** token exchange.

**Polling không gia hạn deadline**; request mới phải bắt đầu một device authorization transaction **mới**, không đổi `expires_in` của code đã cấp.

### 11.1. Clock skew phía thiết bị

Client chỉ cần dùng **monotonic elapsed time** để dừng polling theo `expires_in`; không cần đồng hồ thiết bị khớp tuyệt đối giờ thế giới. AS chịu trách nhiệm quyết định code hết hạn dựa trên hệ thống thời gian đáng tin. Tránh dùng `Date.now()` bị chỉnh sửa giữa chừng làm căn cứ duy nhất cho bảo mật của AS.

### 11.2. Không để mã “lửng” không bao giờ kết thúc

Nếu AS không dọn `PENDING` và không enforce expiry khi query, attacker có thể tích lũy mã, khiến hệ thống thành nơi lưu vô hạn và mở bề mặt phishing. Dùng TTL cleanup, validation tại mỗi endpoint và giới hạn số giao dịch pending theo client/user/device theo policy.

## 12. Device-code phishing: reuse theo nghĩa social engineering

**Device authorization có một rủi ro đặc biệt:** attacker **tự khởi tạo một device code thật** cho app/thiết bị do attacker kiểm soát, rồi lừa người dùng hợp lệ nhập **user code của attacker** trên trang AS thật. Khi người dùng đăng nhập và phê duyệt, attacker có thể polling device code do chính mình giữ để nhận token theo scope được cấp.

~~~mermaid
sequenceDiagram
    autonumber
    participant X as Attacker/device của attacker
    participant AS as Authorization server
    actor U as Người dùng
    X->>AS: Xin device_code D_x và user_code U_x
    AS-->>X: D_x, U_x, verification_uri
    X-->>U: Lừa nhập U_x để nhận quà hoặc sửa lỗi
    U->>AS: Mở trang AS thật, nhập U_x
    AS->>U: Hiển thị client, scope, yêu cầu consent
    U->>AS: Nếu bị lừa, phê duyệt yêu cầu của X
    X->>AS: Poll D_x
    AS-->>X: Access token nếu grant được cấp
~~~

**Điều đáng sợ:** attack có thể dùng **trang AS thật, TLS thật và một mã hoàn toàn hợp lệ**. Đây không nhất thiết là lỗi RNG, code collision hay AS cấp trùng device code. Vấn đề là người dùng phê duyệt **nhầm giao dịch của attacker**, thường vì attacker dẫn dắt họ ngoài ngữ cảnh.

### 12.1. Biện pháp giảm rủi ro

**Tại AS/OP:**

- Hiển thị rõ **tên client đã xác minh**, thiết bị/loại thiết bị nếu có nguồn đáng tin, scopes và tài nguyên được yêu cầu.
- Nêu rõ: *“Chỉ phê duyệt nếu chính bạn vừa yêu cầu đăng nhập trên thiết bị đó.”*
- Dùng consent có ý nghĩa và yêu cầu xác nhận khi scope nhạy cảm; không silent-approve chỉ vì user đã đăng nhập SSO.
- Không để user code có thể được đoán hàng loạt, giới hạn tốc độ và giám sát tín hiệu bất thường.
- Cân nhắc ràng buộc thông tin hiển thị/confirmation UX với device transaction; tránh tạo trải nghiệm một-click quá dễ bị dụ.
- Kiểm tra chính sách user/service, app verification và mức rủi ro trước khi cấp refresh token dài hạn.

**Tại client/device:**

- Hiển thị code và verification URI **trực tiếp trên chính thiết bị đang cần login**; không gửi mã đăng nhập qua tin nhắn tùy tiện.
- Nêu tên ứng dụng và thời hạn để user biết chính xác giao dịch nào đang được yêu cầu.
- Nếu dùng QR, nhắc người dùng kiểm tra domain và thông tin giao dịch ở AS.

**Tại người dùng/quy trình hỗ trợ:**

- Không nhập mã được người lạ gửi qua chat/email/điện thoại, dù họ nói là nhân viên hỗ trợ.
- Không phê duyệt device login khi mình **không chủ động đăng nhập trên một thiết bị khác**.
- Nếu lỡ phê duyệt: thu hồi session/grant/token, kiểm tra thiết bị đã liên kết và audit hoạt động theo khả năng hệ thống.

**PKCE không mặc nhiên giải quyết device-code phishing**: attacker sở hữu device code của **chính giao dịch attacker tạo**, nên đã có đúng credential để polling sau khi nạn nhân approve.

## 13. Attacker đánh cắp `device_code` khi giao dịch đang pending

Khác với phishing ở mục trước, ở đây attacker **lấy được `device_code` gốc của thiết bị hợp lệ** từ log/debug/traffic hoặc bộ nhớ. Vì device code là credential polling, attacker có thể thử gọi token endpoint bằng code đó khi user approve.

| Điều kiện | Nguy cơ |
| --- | --- |
| Attacker chỉ có `user_code` | Chưa thể trực tiếp poll token; có thể lợi dụng social engineering, thử approval |
| Attacker chỉ có `device_code` của public client | Có thể cạnh tranh polling; rủi ro chiếm token nếu code được approve |
| Attacker có `device_code` nhưng không có confidential client credential | Client authentication có thể chặn việc đổi token nếu AS enforce đúng |
| Attacker có device code và secret của confidential client | Có thể cạnh tranh polling nếu giao dịch được approve |
| Attacker có Bearer access token đã phát | Có thể replay token tới RS nếu không sender-constrained |
| Attacker có refresh token | Có thể xin token mới đến khi bị revoke/rotation detection, tùy profile |

**Đừng coi `device_code` như chuỗi vô hại chỉ vì không phải access token.** Nó là một secret dùng để đổi token sau approval; cần HTTPS, entropy, client binding, TTL và logging redaction.

### 13.1. “Ai poll trước thì thắng” là vấn đề thật

Nếu AS phát token cho poll đầu tiên hợp lệ sau approval, attacker có bản sao code có thể **đua** với thiết bị thật. One-time consumption ngăn cấp token trùng nhưng **không tự bảo đảm người thắng là thiết bị thật**. Vì vậy phòng **rò device code** và dùng client authentication/sender constraints khi phù hợp cũng quan trọng như atomic consumption.

### 13.2. Device code khác DPoP-bound access token

DPoP/mTLS có thể ràng buộc **access token đã phát** với khóa/chứng chỉ, giúp giảm replay ở RS. Nhưng điều đó không tự chứng minh một `device_code` chưa bị lấy. Nếu muốn bảo vệ bước exchange thêm nữa, phải thiết kế cơ chế binding được AS hỗ trợ rõ (client authentication, device attestation/profile có bảo vệ), không tự mặc định DPoP bảo vệ toàn bộ Device Authorization Grant.

## 14. Brute-force và reuse `user_code`: yêu cầu ở verification endpoint

Một code hiển thị ngắn đủ dễ nhập có thể dễ **đoán** hơn một device code ngẫu nhiên dài. Attacker không nhất thiết biết token nào cần đánh cắp; họ có thể thử nhiều `user_code` để phát hiện một giao dịch đang chờ. Bảo vệ phải được đặt **ở AS**, không chỉ tại giao diện thiết bị.

### 14.1. Các lớp phòng thủ

1. **Entropy mã:** dùng generator mật mã; chọn alphabet và độ dài đủ khó đoán theo lưu lượng, thời hạn và rate limits.
2. **Uniqueness trong active set:** không có hai pending transactions cùng `user_code`.
3. **Rate limiting:** giới hạn attempts theo IP/device/network, account/session và rủi ro; không dựa vào IP duy nhất.
4. **Response không tiết lộ quá mức:** code không tồn tại/hết hạn không trả tên tài khoản, client secret, device code hoặc scopes nhạy cảm.
5. **User authentication bắt buộc:** biết `user_code` không cho phép tự phê duyệt thay resource owner.
6. **Explicit approval:** user phải thấy rõ client và phạm vi trước khi grant; tránh CSRF trên trang phê duyệt.
7. **Expiration/cancellation:** hết hạn và denied là terminal, không revive bằng repeated submissions.
8. **Audit:** ghi attempt category, client/transaction alias và kết quả mà không log secret/code thực tế.

### 14.2. Verification endpoint là một điểm khác token endpoint

~~~text
Browser/phone:
  verification_uri + user_code
  -> xác thực user + consent

Device/TV:
  token_endpoint + device_code
  -> authorization_pending/slow_down hoặc token
~~~

Không cho `user_code` tự đóng vai `device_code` ở token endpoint. Không trả full `device_code` về browser sau khi user nhập mã; browser không phải bên được thiết kế để poll.

### 14.3. Nếu client cancel một giao dịch và tạo code mới

Thiết bị có thể mất màn hình, restart hoặc user chủ động hủy. Khi có một flow mới, code cũ phải được **expire/cancel** theo contract nếu có API hủy hoặc server cleanup. Nếu không có endpoint hủy theo chuẩn, thiết bị phải ngừng dùng mã cũ và AS vẫn enforce TTL; không được chuyển approval cũ sang transaction mới.

## 15. Java 17: bộ polling có kiểm soát

Ví dụ sau tập trung vào **state machine của polling**. Hàm HTTP/token parser được tách thành interface `TokenEndpoint` để không trộn logic timing với TLS, client authentication, JSON parsing hoặc secret storage. Trong thực tế, implementation của interface cần gửi **POST form** đến trusted token endpoint, kiểm tra TLS và xử lý JSON `error` theo RFC.

~~~java
import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public final class DeviceGrantPoller {
    public enum Kind {
        AUTHORIZATION_PENDING,
        SLOW_DOWN,
        ACCESS_DENIED,
        EXPIRED_TOKEN,
        SUCCESS,
        OTHER_ERROR
    }

    // accessToken chỉ được set khi SUCCESS;
    // tokenType và dữ liệu khác cần validation theo AS contract.
    public record Reply(
            Kind kind,
            String accessToken,
            String tokenType) {}

    public interface TokenEndpoint {
        Reply poll(String deviceCode)
            throws IOException, InterruptedException;
    }

    private DeviceGrantPoller() {}

    public static Reply awaitToken(
            String deviceCode,
            long expiresInSeconds,
            long intervalSeconds,
            TokenEndpoint endpoint)
            throws IOException, InterruptedException {

        Objects.requireNonNull(deviceCode);
        Objects.requireNonNull(endpoint);

        if (deviceCode.isBlank() || expiresInSeconds <= 0) {
            throw new IllegalArgumentException("Invalid device grant");
        }

        // RFC 8628: nếu AS không trả interval, client dùng 5 giây.
        long delaySeconds = intervalSeconds > 0 ? intervalSeconds : 5;
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(expiresInSeconds);

        while (true) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new IllegalStateException("Device grant expired");
            }

            long sleepNanos = Math.min(
                remaining,
                TimeUnit.SECONDS.toNanos(delaySeconds));
            TimeUnit.NANOSECONDS.sleep(sleepNanos);

            if (deadline - System.nanoTime() <= 0) {
                throw new IllegalStateException("Device grant expired");
            }

            Reply reply;
            try {
                reply = Objects.requireNonNull(endpoint.poll(deviceCode));
            } catch (IOException networkFailure) {
                // Backoff khi mạng lỗi; không retry nóng.
                delaySeconds = Math.min(delaySeconds * 2, 60);
                continue;
            }

            switch (reply.kind()) {
                case AUTHORIZATION_PENDING -> {
                    // Cùng device code, đợi interval ở vòng sau.
                }
                case SLOW_DOWN -> {
                    // RFC 8628: cộng ít nhất 5 giây.
                    delaySeconds += 5;
                }
                case SUCCESS -> {
                    if (reply.accessToken() == null
                            || reply.accessToken().isBlank()
                            || reply.tokenType() == null) {
                        throw new IllegalStateException(
                            "Malformed token response");
                    }
                    // Dừng polling ngay; token lưu an toàn ở caller.
                    return reply;
                }
                case ACCESS_DENIED, EXPIRED_TOKEN, OTHER_ERROR -> {
                    throw new IllegalStateException(
                        "Terminal device authorization result: "
                            + reply.kind());
                }
            }
        }
    }
}
~~~

**Phạm vi và điều kiện của ví dụ:**

- `expiresInSeconds` đến từ response AS đã parse và validate; `intervalSeconds` là giá trị `interval`, hoặc 0 khi AS không trả.
- `System.nanoTime()` được dùng để đo khoảng thời gian **monotonic** của transaction; không dùng làm server timestamp.
- Client phải xử lý **cancellation**, interruption, ứng dụng thoát/chạy lại và network reconnect theo kiến trúc.
- `Thread.sleep` (qua `TimeUnit.sleep`) ở đây là mẫu synchronous worker; ứng dụng UI nên dùng scheduler/coroutine async, không chặn UI thread.
- Nếu mạng lỗi, ví dụ backoff đến 60 giây; trong production phải bảo đảm **không giảm dưới interval mà AS yêu cầu**, xét jitter/backpressure và các hướng dẫn của nhà cung cấp.
- Response từ token endpoint cần parse lỗi `authorization_pending`, `slow_down`, `access_denied`, `expired_token` chính xác, giới hạn response size và không gửi raw token/log.
- Bộ poller chỉ được chạy bởi **một task chủ sở hữu của transaction**. AS vẫn phải enforce one-time grant độc lập với client.
- Khi thành công, caller phải validate `token_type` theo profile được phép (ví dụ `Bearer`), audience/scope khi phù hợp và bảo vệ token. Code này **không xác thực** JWT hay được dùng để gọi API trực tiếp.

### 15.1. Một poller cho một transaction

Không chỉ để `awaitToken` chạy trong nhiều tasks cùng device code. Có thể quản lý một transaction object:

~~~java
import java.util.concurrent.atomic.AtomicReference;

enum LocalGrantState {
    NEW, POLLING, COMPLETED, TERMINAL
}

final class DeviceGrantSession {
    private final AtomicReference<LocalGrantState> state =
        new AtomicReference<>(LocalGrantState.NEW);

    boolean startPollingOnce() {
        return state.compareAndSet(
            LocalGrantState.NEW, LocalGrantState.POLLING);
    }

    void markCompleted() {
        state.compareAndSet(
            LocalGrantState.POLLING, LocalGrantState.COMPLETED);
    }

    void markTerminal() {
        state.compareAndSet(
            LocalGrantState.POLLING, LocalGrantState.TERMINAL);
    }
}
~~~

Ví dụ chỉ chống duplicate poller **trong một process**. Nếu nhiều instances cùng giữ transaction, cần shared ownership/lease và retry policy; nhưng **AS one-time consumption mới là đường bảo vệ cuối** chống hai lần cấp token.

### 15.2. Java HTTP adapter cần làm gì?

Một implementation `TokenEndpoint.poll(deviceCode)` cần:

1. Dùng token endpoint cố định từ **trusted issuer metadata/config**.
2. Gửi POST với `grant_type`, `device_code`, `client_id` hoặc client authentication theo registration.
3. Áp timeout và **không tự forward credentials khi redirect cross-origin**.
4. Đọc `Content-Type`, HTTP status và JSON `error` có giới hạn kích thước.
5. Phân biệt success token response và `authorization_pending`/terminal errors.
6. Không log `device_code`, Basic/client assertion, access/refresh token hoặc response body.
7. Giữ TLS certificate/hostname verification, không bật trust-all SSL context.

Không lấy token endpoint URL từ `verification_uri_complete` hay input do user nhập; URL AS phải được cấu hình/discover một cách đáng tin.

## 16. Java/Spring: triển khai ở phía Authorization Server

**Spring Security OAuth2 Resource Server** dùng để xác minh access token tại API, **không phải** tự động biến ứng dụng Java thành một AS hỗ trợ device authorization. Một authorization server cần implementation/version hỗ trợ Device Authorization Grant và state handling rõ ràng.

Kiến trúc tham khảo phía AS:

~~~mermaid
flowchart TD
    A["POST /device_authorization"] --> B["Validate client, grant, scope/resource"]
    B --> C["CSPRNG tạo device_code và user_code"]
    C --> D["Lưu transaction PENDING + TTL"]
    D --> E["User verification endpoint"]
    E --> F{"User login + consent"}
    F -->|Approve| G["APPROVED gắn subject/grant"]
    F -->|Deny| H["DENIED"]
    D --> I["POST /token device_code polling"]
    I --> J{"Đúng client, TTL, state?"}
    J -->|Pending| K["authorization_pending / slow_down"]
    J -->|Approved| L["Atomic consume và cấp token"]
    J -->|Terminal| M["Từ chối"]
    G --> J
~~~

### 16.1. Các trách nhiệm nên tách lớp

| Thành phần | Nhiệm vụ |
| --- | --- |
| `DeviceAuthorizationController` | Nhận request, validate client/scopes và phát response chuẩn |
| `DeviceGrantService` | Sinh code, lưu transaction, expiry và state transitions |
| `UserVerificationController` | Xác thực user, hiển thị client/scopes, xử lý consent và CSRF |
| `DeviceTokenGrantProvider` | Kiểm tra token polling, interval, client binding, atomic consumption |
| `TokenIssuer` | Phát JWT/opaque access token, refresh token theo policy |
| `Audit/RateLimitService` | Chống brute force user code, flooding và replay, logs đã lọc |

Các tên class là **gợi ý kiến trúc**, không phải APIs bảo đảm tồn tại nguyên tên trong Spring Authorization Server. Luôn kiểm tra version/framework và integration test ở **đúng endpoint thực**.

### 16.2. Kiểm tra state khi approval

Một POST `/activate/approve` có user session cookie phải có **CSRF protection**; user phải được xác thực và hiểu grant đang phê duyệt. Nếu `user_code` ở trạng thái EXPIRED/DENIED/CONSUMED, không thể đưa về APPROVED chỉ bằng gửi lại POST.

Ví dụ logic:

~~~text
approve(user_code, user_session, requested_action):
  require authenticated_user(user_session)
  require csrf_and_origin_policy_passed
  grant = lookup_by_user_code(user_code)
  require grant.status == PENDING
  require current_server_time < grant.expires_at
  show_and_bind_client_scope_device_context(grant)
  require explicit_user_consent_for_this_grant
  atomic_update(grant, PENDING -> APPROVED, subject=user_session.user)
~~~

**Không mặc định user_code là đủ để duyệt**. User phải đăng nhập và thực hiện consent theo chính sách AS; approvals phải được ràng buộc với transaction gốc và user session.

## 17. Access token sau device flow: không nhầm với device code

Khi device flow hoàn tất, **AS phát access token** cho client. Resource server có thể thấy token JWT đã ký hoặc token opaque và phải kiểm tra:

| Kiểm tra tại RS | JWT access token | Opaque access token |
| --- | --- | --- |
| Nguồn tin cậy | Verify chữ ký/JWS algorithm/key và `iss` | Introspection/lookup với AS đã tin |
| Audience | `aud` phải khớp API | Metadata resource/audience phải phù hợp |
| Thời hạn | `exp`, `nbf`, profile | `active`, `exp`/trạng thái theo hợp đồng |
| Scope | Scope thực tế được cấp | Scope introspection trả về |
| Principal | `sub`, `client_id` theo issuer profile | Metadata subject/client theo AS |
| Resource policy | Tenant, ownership, entitlement | Tenant, ownership, entitlement |
| Sender constraint | DPoP/mTLS khi có | DPoP/mTLS binding khi có |

**Device flow không cấp một “vé truy cập vĩnh viễn” chỉ vì user đã nhập mã.** Token được cấp có scope/audience/hạn theo chính sách; thiết bị không được dùng token Media API cho Payments API.

### 17.1. Token không đồng nghĩa session của user trên thiết bị khác

Người dùng xác thực bằng trình duyệt điện thoại, nhưng **TV thường nhận access token/refresh token theo grant dành cho TV**, không phải cookie session của browser điện thoại. Không sao chép browser session cookie hoặc ID token sang TV tùy tiện.

Với OIDC, `openid` có thể dẫn đến ID token theo profile của AS/OP. **ID token dành cho OIDC client**, không dùng thay access token ở resource server.

### 17.2. Refresh token khác tái sử dụng device code

Nếu AS cấp refresh token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token>
~~~

Đây là một **grant khác**, có client authentication/sender constraint nếu AS yêu cầu. Thiết bị không dùng lại:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:device_code
device_code=<old-consumed-device-code>
~~~

để xin token mới sau 30 ngày. Refresh token phải được lưu an toàn (OS secure storage/keystore khi phù hợp), có rotation/reuse detection hoặc sender constraint theo policy. Nếu refresh token bị revoke hoặc không được cấp, client bắt đầu **device authorization flow mới** khi cần.

### 17.3. Reuse refresh token và reuse device code là hai lỗi khác nhau

| Giá trị | Reuse hợp lệ | Reuse nguy hiểm |
| --- | --- | --- |
| `device_code` | Poll nhiều lần khi còn PENDING | Xin token lần hai sau CONSUMED/EXPIRED/DENIED |
| `user_code` | Hiển thị/nhập để phê duyệt đúng transaction | Dùng để đổi sang transaction khác hoặc reapprove flow cũ |
| Access token Bearer | Gọi nhiều API requests hợp lệ trước hạn | Bản sao bị attacker replay ở API |
| Refresh token rotation | Dùng **refresh token mới nhất** theo policy | Phát lại refresh token cũ đã được rotation |
| DPoP proof `jti` | Proof mới cho request mới | Phát lại proof đã dùng trong replay window |

Một hệ thống có thể xử lý từng loại “reuse” bằng **cơ chế khác nhau**, không thể áp một rule chung `mã nào thấy lần hai đều sai`.

## 18. Bảo vệ giao dịch device authorization trong vận hành

### 18.1. Secrets và dữ liệu được phép hiển thị

| Dữ liệu | Có thể hiển thị user? | Có nên log plaintext? |
| --- | --- | --- |
| `verification_uri` | Có | Có thể log domain/route theo policy |
| `user_code` | Có, trên device và form AS | **Không**, trừ audit policy đặc biệt có kiểm soát |
| `verification_uri_complete` | Có, có thể dùng QR | **Không log toàn link** vì chứa user code |
| `device_code` | **Không** | **Không** |
| Client ID/public name | Có, sau verify registration | Có thể log alias theo policy |
| Authorization code/user approval context | Chỉ phần UX cần thiết | Không log consent secrets, token/code |
| Access token / refresh token | **Không** | **Không** |
| Device code hash/HMAC fingerprint | Không cần | Chỉ theo audit policy, không làm metric label công khai |

AS nên hỗ trợ tracing bằng **transaction ID nội bộ** không thể dùng đổi token, thay vì log device code hoặc user code. Ẩn nguyên body/headers nhạy cảm ở reverse proxy, WAF, API gateway, APM và support tools.

### 18.2. Replay detection metrics

Có thể giám sát:

- Số transactions PENDING/APPROVED/DENIED/EXPIRED/CONSUMED theo client alias;
- Số `authorization_pending`, `slow_down`, token successes, terminal errors;
- Số attempts dùng code đã CONSUMED, sai client, code hết hạn;
- Số duplicate user-code submissions, brute-force verification attempts;
- Độ trễ từ phát mã → approval → token exchange;
- Rate/token issuance theo client/thiết bị và bất thường theo network/region.

Không thêm raw token/code vào metrics labels, log queries hoặc tracing baggage. Tránh cardinality bùng nổ do mỗi code thành một label.

### 18.3. Cache và database retention

Transaction phải hết hạn và được dọn khỏi active storage, nhưng **dọn TTL không thay kiểm tra expiry khi request tới**. AS có thể lưu audit summary đã lọc (result, timestamp, client alias) theo retention, không giữ mã plaintext hoặc token không cần thiết mãi.

**Tối ưu hiệu năng không được làm mất atomic one-time semantics.** Khi cache phân tán/Redis failover, cần test duplicate exchange và bảo đảm kết quả sau restart/replica promotion.

## 19. Khi thiết bị mất mạng, tắt nguồn hoặc restart

### 19.1. Đang PENDING rồi mất kết nối

Client có thể tạm dừng polling, sau đó tiếp tục dùng **cùng device code** nếu transaction còn hạn và storage bảo vệ có thể phục hồi. Khi restart, nếu không còn verifier/device code và không thể phục hồi an toàn, **tạo flow mới**, không cố lấy user code từ màn hình cũ để biến thành device code.

### 19.2. Token đã cấp nhưng response bị mất

AS có thể đã consume code và phát token, nhưng thiết bị không nhận HTTP response. Một retry cùng code **không được làm AS cấp token set thứ hai**. Client cần thông báo login chưa hoàn tất ở phía thiết bị, dừng retry vô hạn và khởi tạo flow mới hoặc sử dụng cơ chế khôi phục **được AS thiết kế có bảo đảm an toàn**, không tự suy ra idempotent recovery.

### 19.3. Thiết bị đổi owner hoặc được factory reset

Đừng lưu `device_code`, access/refresh token và user session lâu hơn vòng đời cần thiết. Khi reset/transfer owner:

- Xóa token và transaction còn lưu trên thiết bị;
- Thu hồi session/device grant/refresh token phía AS nếu API và policy hỗ trợ;
- Xác thực lại khi chủ mới dùng;
- Không “reuse” user code/device code của chủ cũ để kết nối tài khoản chủ mới.

### 19.4. Nhiều thiết bị dùng cùng một tài khoản

Một user có thể phê duyệt **nhiều device transactions khác nhau** cho nhiều TV. Mỗi transaction phải có code riêng, client/device context và audit riêng. **Không gom mọi device đang chờ thành một mã duy nhất của user**, vì sẽ làm việc revoke/consent và ranh giới thiết bị trở nên mơ hồ.

## 20. Error-handling matrix: lỗi ở bước nào?

| Biểu hiện | Nơi xảy ra | Ý nghĩa và hành động |
| --- | --- | --- |
| Device authorization endpoint trả `invalid_client` | AS | Client auth sai; không có code hợp lệ để poll |
| Device authorization endpoint trả `invalid_scope` | AS | Scope không hợp lệ; sửa registration/permission |
| Token endpoint trả `authorization_pending` | AS | **Tiếp tục poll cùng code** sau interval |
| Token endpoint trả `slow_down` | AS | Tăng interval ít nhất 5 giây |
| Token endpoint trả `access_denied` | AS | User từ chối; dừng transaction |
| Token endpoint trả `expired_token` | AS | Device code hết hạn; dừng và bắt đầu flow mới nếu muốn |
| Token endpoint trả `invalid_grant` sau success | AS | Code không còn hợp lệ/đã tiêu thụ theo policy; không cấp lại |
| Token endpoint trả `invalid_client` khi polling | AS | Device client auth fail; dừng, sửa cấu hình |
| Token endpoint trả 5xx hoặc network timeout | AS/network | Backoff, giới hạn retry, kiểm tra deadline; không poll nóng |
| User verification UI báo code sai | AS/browser | Không tiết lộ transaction khác; rate limit |
| AS approval thành công nhưng TV không nhận token | Client/AS | Kiểm tra poller, TTL, duplicate processing/response loss |
| API trả `401 invalid_token` sau khi login | RS | Token sai issuer/audience/hạn/signature/active |
| API trả `403 insufficient_scope` | RS | Access token thiếu quyền endpoint |
| API trả `403` hoặc `404` cho bản ghi khác tenant | RS | Object-level authorization phải được giữ |

**Không sửa lỗi `expired_token` bằng cách kéo dài hạn server cho mã cũ hoặc cấp token từ code đã tiêu thụ.** Đó là thay đổi chính sách bảo mật, không phải xử lý lỗi UX.

## 21. Các sai lầm và ngộ nhận phổ biến

### 21.1. “Device code chỉ được gửi một lần”

**Sai với Device Authorization Grant.** Thiết bị cần lặp polling cùng `device_code` trong trạng thái PENDING theo interval.

### 21.2. “Cứ thấy mã lần thứ hai là replay attack”

**Sai.** Cần kết hợp trạng thái transaction, client binding, hạn và khoảng polling; chỉ terminal reuse mới không được cấp lại token.

### 21.3. “Đã user approve là chuyển code thành CONSUMED”

**Sai.** APPROVED là user đã phê duyệt; CONSUMED là khi token exchange thành công.

### 21.4. “Phê duyệt cùng user code hai lần sẽ cấp hai token sets”

**Sai thiết kế.** User-code approval gắn với một transaction; AS chỉ cấp tối đa một lần khi device code exchange.

### 21.5. “`interval=5` nghĩa là poll mỗi 100 ms để login nhanh”

**Sai.** Tôn trọng minimum interval, tăng khi `slow_down` và backoff khi lỗi mạng.

### 21.6. “Device code đã cấp token thì dùng như refresh token”

**Sai.** Device code là credential giao dịch ngắn hạn. Sau login dùng refresh token grant nếu được cấp hoặc bắt đầu flow mới.

### 21.7. “Trang đăng nhập AS thật nên device-code phishing không thể xảy ra”

**Sai.** Attacker có thể tự lấy mã thật rồi lừa user approve giao dịch của attacker trên trang AS thật.

### 21.8. “Atomic consumption đủ để ngăn kẻ lấy device code”

**Không đủ.** Atomicity ngăn **phát token hai lần**, nhưng kẻ lấy code có thể đua để nhận **token duy nhất** trước thiết bị thật.

### 21.9. “Device flow xác thực user xong nên API cho mọi quyền”

**Sai.** RS vẫn phải xác minh token đúng issuer/audience/scope, tenant và ownership.

### 21.10. “Dùng lại code cũ sau khi factory reset giúp đăng nhập tiện hơn”

**Sai.** Chủ mới cần phiên/grant mới; mã cũ và token của chủ trước phải được xóa/thu hồi.

## 22. Các tình huống thực tế và cách phân tích

**Tình huống A — TV poll liên tục và nhận `authorization_pending`.**

Thiết bị gửi cùng `device_code` sau mỗi 5 giây, user chưa vào verification URI. **Đây là hành vi đúng**, không phải replay. Thiết bị cần giữ interval và dừng đúng deadline.

**Tình huống B — Pollers A/B cùng nhận 200 và hai access tokens.**

Hai AS instances cùng đọc APPROVED rồi phát token trước khi đánh dấu CONSUMED. **Lỗi race condition ở AS**; cần row lock/compare-and-set/transaction bền vững để chỉ một lần exchange thành công.

**Tình huống C — User nhập lại `user_code` đã dùng sau một ngày.**

AS phải từ chối vì transaction hết hạn/đã consumed. **Không chuyển approval cũ** sang một device mới, dù cùng user và client.

**Tình huống D — Nhân viên được gửi mã “kiểm tra bảo mật” qua chat.**

Attacker tự khởi tạo device flow và gửi user code cho nạn nhân. Nạn nhân mở AS thật và bị lừa approve. **Device-code phishing**, không phải lỗi token signature. Cần UX xác minh request được chủ động tạo, giáo dục và audit/revoke.

**Tình huống E — Token response bị mất và client retry.**

AS đã phát token nhưng gói tin phản hồi mất. Retry device code bị từ chối vì CONSUMED; đó là **an toàn**. Thiết bị phải có recovery UX, không yêu cầu AS phát bộ token thứ hai vô điều kiện.

**Tình huống F — Thiết bị dùng device code để đổi access token sau 30 ngày.**

Code đã hết hạn từ lâu. Không thể refresh qua device grant cũ; dùng refresh token (nếu được cấp, còn hợp lệ và được bảo vệ) hoặc authorization flow mới.

**Tình huống G — Kẻ khác lấy `device_code` từ log TV.**

Attacker poll trước khi TV nhận token. Code bị dùng đúng một lần nhưng **token có thể tới attacker**. Cần bảo vệ logs/storage/device, client binding và giới hạn/thông báo/revoke grant theo policy.

**Tình huống H — Login xong, Media API cho phép xem video của tenant khác.**

Đây là **object-level authorization failure**, không phải lỗi device code reuse. Token phải được RS kiểm tra đúng tenant/entitlement/ownership.

## 23. Ma trận kiểm thử an toàn

| Test case | Kỳ vọng |
| --- | --- |
| AS phát device authorization response hợp lệ | Có device_code, user_code, verification_uri, expires_in |
| `interval` không được AS trả | Client mặc định poll không nhanh hơn 5 giây |
| Client polling lần 1 khi PENDING | `authorization_pending` |
| Client polling lần 2 cùng code khi PENDING | Vẫn có thể `authorization_pending`, không bị false replay |
| Polling dưới interval | AS áp `slow_down`/rate limit đúng policy |
| AS trả `slow_down` một lần | Client tăng interval ít nhất 5 giây |
| AS trả `slow_down` nhiều lần | Interval tăng cộng dồn, không reset |
| Timeout mạng khi polling | Backoff, không busy loop |
| Client tiếp tục polling sau `expires_in` | Dừng local; AS từ chối |
| User approve đúng user code trước expiry | Transaction chuyển APPROVED |
| User approve mã đã expired/consumed | AS không duyệt lại |
| User deny | Token endpoint trả terminal denial, không cấp token |
| Device poll lần đầu sau approval | Đổi thành công tối đa một lần |
| Device poll lại sau success | Không cấp thêm token |
| Hai pollers đồng thời lúc APPROVED | Tối đa một exchange thành công |
| AS multi-node/Redis failover cùng code | Atomic consumption bền vững theo threat model |
| Device code sai/không tồn tại | Từ chối không lộ transaction |
| Device code đúng nhưng `client_id` khác | Từ chối |
| Confidential device client thiếu authentication | Từ chối |
| User code dễ đoán được thử hàng loạt | Rate limit, hạn chế enumeration |
| Hai pending transactions có cùng user code | Không được mapping mơ hồ |
| User code cũ trùng một flow mới | Không chuyển consent/grant nhầm |
| User code gửi qua phishing chat | Kiểm thử UX/cảnh báo/consent, audit |
| Device code bị log qua WAF/APM | Kiểm thử security thất bại; phải redact |
| Token response bị mất sau AS consume | Retry không phát token set mới |
| Thiết bị restart khi PENDING còn hạn | Resume đúng transaction nếu có storage an toàn, hoặc flow mới |
| Device code được dùng làm refresh token | Từ chối |
| Refresh token rotation reuse | Xử lý theo refresh token policy, không nhầm device polling |
| Device JWT access token sai issuer/audience | RS từ chối |
| Opaque access token `active=false` | RS từ chối |
| Token đủ scope nhưng sai tenant/owner | RS từ chối |
| DPoP/mTLS-bound token thiếu sender proof | RS từ chối |
| Factory reset/chuyển chủ | Xóa transaction/token cũ, revoke grant khi cần |

### 23.1. Tầng kiểm thử

**Unit tests:** interval defaults/`slow_down`, monotonic deadline, state transition, error mapping, không log secret.

**AS integration tests:** issue/poll/approve/deny/expire/consume, client binding, user-code rate limits, token issuance atomicity.

**Concurrency tests:** nhiều polling requests đồng thời và nhiều AS instances; xác nhận không có hai lần issuance.

**End-to-end device tests:** TV UI hiển thị URI/user code, người dùng mở browser đúng domain, xác thực/consent, TV nhận token đúng một lần.

**Security/abuse tests:** device-code phishing simulation có kiểm soát, user-code enumeration, log leakage, wrong audience, stolen device code và revocation.

Không dùng code/token production trong fixtures, screenshots, support tickets hoặc CI artifacts.

## 24. Checklist triển khai production

1. **Đúng RFC 8628:** phát `device_code`, `user_code`, `verification_uri`, `expires_in` và `interval` khi có.
2. **Phân biệt hai mã:** device code bí mật dùng polling; user code dễ nhập chỉ dùng verification UI.
3. **Sinh bằng CSPRNG:** entropy và uniqueness phù hợp, không tạo code đoán được từ timestamp/user ID.
4. **Ràng buộc transaction:** client registration, scopes/resource, trạng thái, expiry và user approval.
5. **Polling có kiểm soát:** reuse cùng device code khi PENDING, tôn trọng `interval`, `slow_down` và network backoff.
6. **Dừng ở terminal state:** denied/expired/cancelled/consumed không tiếp tục xin token bằng code cũ.
7. **Consume nguyên tử:** tối đa một exchange thành công, kể cả hai AS nodes và retry sau network timeout.
8. **Không dùng device code làm refresh token:** dùng grant/rotation/revocation riêng hoặc khởi tạo flow mới.
9. **Chống user-code guessing:** rate limit, TTL, anti-enumeration và uniqueness ở tập active.
10. **Chống device-code phishing:** UI client/scope rõ ràng, user tự khởi tạo login, consent và cảnh báo mã lạ.
11. **Bảo vệ device code:** HTTPS, memory/storage theo thiết bị, không log/QR/hiển thị code bí mật.
12. **Client binding:** đúng client ID và client authentication nếu confidential; không cho chuyển code giữa clients.
13. **Giới hạn quyền token:** issuer, audience, scope, user/service principal, tenant và ownership theo policy.
14. **Bảo vệ access/refresh token:** TTL, secure storage, refresh token rotation/sender constraints và revoke khi cần.
15. **Theo dõi an toàn:** metrics không lộ code, audit state transitions, replay/abuse alerts.
16. **Kiểm thử failure/restart:** lost response, multi-poller, AS outage, code expired/denied và factory reset.

## 25. Tài liệu tham khảo

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device/user codes, polling, `authorization_pending`, `slow_down`, `access_denied`, `expired_token` và phishing/security considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client roles, token endpoint, access/refresh tokens và client authentication.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): giảm rủi ro token theft/replay, refresh token protection và OAuth threat model.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền access token và rủi ro Bearer replay.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token và metadata `active`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi access/refresh token hoặc grant theo AS policy.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token validation tại resource server.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu resource/audience khi AS hỗ trợ.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession và giảm replay access token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): client certificate authentication và certificate-bound access tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt ID token, access token và OIDC client semantics.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): quyền trên tài nguyên vẫn cần được RS kiểm tra.

**Ghi nhớ:** **Device code reuse chỉ sai khi hiểu nhầm hoặc bỏ qua vòng đời giao dịch.** Trong **RFC 8628**, client được **poll nhiều lần với cùng `device_code` khi chưa có quyết định**, tuân `interval` và `slow_down`. Sau khi user phê duyệt, **tối đa một token exchange thành công** được phép; DENIED/EXPIRED/CONSUMED không được hồi sinh hoặc dùng làm refresh token. Hãy bảo vệ **cả device code và user code**, chống phỏng đoán/phishing, enforce client binding và atomic consumption; sau khi nhận token, API vẫn xác minh **issuer, audience, scope, thời hạn và quyền trên dữ liệu**.
