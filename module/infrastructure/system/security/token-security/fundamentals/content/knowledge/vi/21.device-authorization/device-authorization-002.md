# User code và verification URI

## 1. Bài toán: đăng nhập trên thiết bị khó nhập liệu

Trong chương **Device authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, ta xét cách một ứng dụng chạy trên **TV, máy chơi game, thiết bị IoT hoặc giao diện dòng lệnh** xin quyền truy cập API mà không yêu cầu người dùng nhập mật khẩu ngay trên thiết bị đó. Cách tiếp cận được tiêu chuẩn hóa trong **OAuth 2.0 Device Authorization Grant (RFC 8628)**.

Ví dụ, Alice mở ứng dụng **Shop TV** để xem đơn hàng của mình. TV khó nhập mật khẩu và có thể không có trình duyệt thích hợp. Shop TV hiển thị:

~~~text
Để kết nối Shop TV với tài khoản của bạn:

1. Trên điện thoại hoặc máy tính, mở:
   https://login.example.com/activate

2. Nhập mã:
   T8KQ-M7PL

3. Kiểm tra ứng dụng và quyền được yêu cầu trước khi xác nhận.

Mã hết hạn sau một khoảng thời gian ngắn.
~~~

Alice sử dụng **điện thoại** đang có trình duyệt để mở địa chỉ của Authorization Server, đăng nhập nếu cần, nhập mã và quyết định có cấp quyền cho ứng dụng trên TV hay không. Khi yêu cầu được chấp thuận, TV có thể nhận **access token** để gọi API. TV **không nhận mật khẩu của Alice** trong quy trình này.

Ở đây xuất hiện hai thành phần quan trọng:

- **`user_code`**: mã ngắn, dễ đọc và dễ nhập, dùng để **liên kết thao tác trên thiết bị thứ hai với một yêu cầu cấp quyền đang chờ**.
- **`verification_uri`**: địa chỉ HTTPS của Authorization Server mà Alice mở trên điện thoại hoặc máy tính để nhập mã, đăng nhập và xem xét quyết định cấp quyền.

**Điểm cốt lõi:** nhập đúng `user_code` không tự động biến mã thành access token hoặc chứng minh người dùng đã đăng nhập. Mã giúp **tìm đúng yêu cầu ghép nối**. Authorization Server vẫn phải xác thực người dùng theo chính sách, hiển thị ngữ cảnh ứng dụng/phạm vi quyền và ghi nhận **quyết định chấp thuận hoặc từ chối** trước khi phát hành token.

### Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt `user_code`, `device_code`, `verification_uri`, `verification_uri_complete`, authorization code, access token và refresh token.
2. Diễn giải chính xác luồng **device authorization → user verification → polling token endpoint** theo RFC 8628.
3. Thiết kế mã dễ nhập nhưng khó đoán, có TTL, rate limiting, single-use và mapping đến đúng yêu cầu.
4. Giải thích vì sao QR/link tự điền code vẫn cần bước xác nhận có chủ ý của người dùng.
5. Nhận diện **device-code phishing** và tình huống kẻ tấn công dụ người dùng cấp quyền cho một thiết bị không phải của họ.
6. Áp dụng bảo vệ issuer, client, scope, audience, grant state, token storage và authorization theo resource/action.
7. Thiết kế kiểm thử âm tính cho sai mã, đoán mã, nhiều thiết bị, yêu cầu hết hạn, polling và phát lại mã.

## 2. Những vai trò và giá trị rất dễ nhầm

Một device flow thường có bốn vai trò:

| Vai trò | Trách nhiệm trong ví dụ |
|---|---|
| **Resource owner** | Alice, người có khả năng xem xét và cấp quyền truy cập dữ liệu của mình |
| **Device client** | Shop TV, một OAuth client chạy trên TV, có khả năng nhập liệu hạn chế |
| **Authorization Server (AS)** | `login.example.com`, tạo mã ghép nối, xác thực Alice và phát token |
| **Resource Server (RS)** | Orders API, chỉ chấp nhận access token đúng audience/scope và áp quyền đối với đơn hàng |

Điện thoại/trình duyệt Alice dùng là một **thiết bị thứ hai** để tương tác với AS, không nhất thiết là OAuth client nhận token. Trong device flow, **device client là bên polling và nhận access token**, không phải trình duyệt điện thoại đang nhập user code.

### 2.1. So sánh các giá trị trên wire

| Giá trị | Ai nhận? | Dùng ở đâu? | Mức nhạy cảm và đặc tính |
|---|---|---|---|
| **`user_code`** | AS trả về cho thiết bị; thiết bị **hiển thị cho người dùng** | Trang nhập mã tại verification URI | Ngắn, dễ gõ, có nguy cơ bị đoán; phải giới hạn thử và hạn dùng |
| **`verification_uri`** | AS trả về cho thiết bị | Người dùng mở trên trình duyệt khác | URL HTTPS của AS, không chứa access token; phải xác minh nguồn |
| **`verification_uri_complete`** | AS có thể trả về cho thiết bị | Link/QR dẫn đến trang xác minh đã điền code hoặc thông tin tương đương | Tùy chọn, thuận tiện nhưng có thể mang pairing code trong URL; cần phòng rò rỉ |
| **`device_code`** | AS trả về cho thiết bị | Thiết bị gửi tới **token endpoint** khi polling | Giá trị đủ entropy, **không hiển thị làm mã nhập của người dùng** |
| **Authorization code** | Client khác trong Authorization Code flow nhận qua redirect | Đổi code ở token endpoint bằng flow riêng | Không phải `user_code`; Device Grant không cần browser redirect code về TV |
| **Access token** | OAuth client sau khi cấp quyền xong | Truy cập resource server đúng audience | Credential API, có thể là JWT hoặc opaque; không đặt trong URI |
| **Refresh token** | Có thể được cấp cho client theo policy | Xin access token mới tại AS | Credential có thể sống dài; phải bảo vệ chống bị đánh cắp/phát lại |
| **ID token** (OIDC) | OIDC client khi dùng profile phù hợp | Xác minh thông tin đăng nhập tại client | Không tự thay thế OAuth access token của API |

**`user_code` và `device_code` là hai mã có vai trò khác nhau.** Đặc biệt, `user_code` có thể hiển thị công khai trên màn hình TV để con người nhập; `device_code` là handle dành cho **polling token endpoint**, không gửi lên trang nhập mã như một tham số UI thông thường.

### 2.2. Đây không phải đăng nhập bằng OTP trên TV

User code **không phải mật khẩu của Alice, mã OTP đăng nhập, mã MFA, mã khôi phục tài khoản hay access token**. Việc Alice nhập user code trên trang AS nhằm xác định *yêu cầu nào* đang chờ được chấp thuận.

Nếu một người lạ gửi Alice một mã và bảo "hãy nhập để xác minh tài khoản", đó là dấu hiệu đáng nghi: **mã có thể thuộc một yêu cầu device authorization do chính người lạ khởi tạo**.

### 2.3. Device flow khác Authorization Code + PKCE

| Tiêu chí | Authorization Code + PKCE | Device Authorization Grant |
|---|---|---|
| Trình duyệt nơi user thao tác | Thường cùng trải nghiệm với client/callback | Thường trên **thiết bị thứ hai** |
| Giá trị người dùng thấy | Login/consent và redirect | **Verification URI + user code** |
| Giá trị client đổi thành token | Authorization code + verifier | **Device code** và client binding |
| Cách client chờ kết quả | Nhận browser callback code | **Polling token endpoint** |
| Rủi ro nổi bật | Code interception, redirect/mix-up, PKCE downgrade | Đoán user code, phishing ghép nối, polling quá nhanh |
| Token nhận sau khi hoàn tất | Access token; ID/refresh khi profile cho phép | Access token; refresh/ID khi profile/AS cho phép |

Không được thiết kế TV giả lập flow PKCE bằng cách lấy `user_code` thay cho `authorization_code` rồi gửi vào tham số `grant_type=authorization_code`. Mỗi grant có endpoint, dữ liệu và quy tắc riêng.

## 3. Toàn cảnh luồng với user code và verification URI

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant D as Shop TV
    participant AS as Authorization Server
    participant B as Trình duyệt điện thoại
    participant RS as Orders API

    D->>AS: POST /device_authorization (client_id, scope)
    AS->>AS: Tạo device_code và user_code, TTL, trạng thái PENDING
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>U: Hiển thị https://login.example.com/activate và T8KQ-M7PL
    D->>AS: POST /token (device_code, grant_type=device_code)
    AS-->>D: authorization_pending

    U->>B: Mở verification_uri trên điện thoại
    B->>AS: Truy cập trang nhập user_code
    U->>B: Nhập T8KQ-M7PL
    AS->>AS: Tra yêu cầu PENDING, kiểm tra mã/TTL/rate limit
    AS-->>B: Đăng nhập nếu cần và hiển thị Shop TV + quyền yêu cầu
    U->>B: Xác minh đúng TV và chọn Chấp thuận
    B->>AS: Xác nhận quyết định
    AS->>AS: Gắn approval với subject, client, scope và device transaction
    D->>AS: POST /token (polling lại đúng interval)
    AS-->>D: Access token khi được chấp thuận
    D->>RS: Authorization: Bearer access_token
    RS->>RS: Validate issuer, audience, thời gian, scope, resource permission
    RS-->>D: Dữ liệu được phép
~~~

Sơ đồ nhấn mạnh rằng **trình duyệt và TV không chuyển access token trực tiếp cho nhau**. Trình duyệt làm việc với Authorization Server để xác nhận giao dịch; TV sử dụng `device_code` để lấy token từ Authorization Server sau khi trạng thái được chấp thuận.

Nếu Alice từ chối, yêu cầu hết hạn hoặc mã sai, TV **không được phát token**. Trạng thái được xác định ở AS, không phải chỉ dựa vào việc TV hiện thông báo "đã ghép nối".

## 4. Bước khởi tạo: client xin cặp user_code và device_code

Trước hết, TV gửi HTTP POST đến **device authorization endpoint** của AS. Endpoint này khác với token endpoint dùng để polling.

Ví dụ public client:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=shop-tv&scope=orders%3Aread
~~~

Theo RFC 8628, client gửi `client_id` nếu không sử dụng client authentication; `scope` là tham số OAuth theo hợp đồng. Nếu là confidential client và có phương thức xác thực được đăng ký, AS cần thực thi client authentication phù hợp. `client_id` của public client là **định danh công khai**, không phải secret.

### 4.1. Phản hồi mẫu của AS

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "<OPAQUE_HIGH_ENTROPY_DEVICE_CODE>",
  "user_code": "T8KQ-M7PL",
  "verification_uri": "https://login.example.com/activate",
  "verification_uri_complete": "https://login.example.com/activate?user_code=T8KQ-M7PL",
  "expires_in": 900,
  "interval": 5
}
~~~

Các giá trị là **minh họa**, không phải token hoặc mã đang hoạt động. Trong RFC 8628:

| Trường response | Bắt buộc? | Ý nghĩa |
|---|---|---|
| `device_code` | Có | Code dành cho client dùng khi polling token endpoint |
| `user_code` | Có | Mã con người nhập vào trang xác minh |
| `verification_uri` | Có | URL AS mà người dùng phải mở để xác minh |
| `verification_uri_complete` | Không | Link tùy chọn chứa sẵn code/thông tin tương đương, phù hợp QR hoặc chuyển không cần gõ |
| `expires_in` | Có | Số **giây** trước khi `device_code`/`user_code` hết hiệu lực |
| `interval` | Không | Thời gian tối thiểu **tính bằng giây** giữa những lần client polling |

**Không nhầm `expires_in` với thời hạn access token**. Ở phản hồi này, nó mô tả thời hạn của **yêu cầu device authorization chưa hoàn tất**. Access token được cấp về sau có TTL riêng.

### 4.2. Tại sao AS phải tạo hai mã?

Mục tiêu thiết kế khác nhau:

- `user_code` phải đủ ngắn, dễ đọc, dễ nhập bằng điều khiển từ xa hoặc bàn phím di động, đồng thời được bảo vệ khỏi đoán thử.
- `device_code` không dành cho người nhập, nên có thể dài và đủ entropy để khó đoán; nó là handle mà chỉ thiết bị đã khởi tạo cần giữ để polling.

AS lưu liên kết một-một theo **giao dịch device authorization đang hoạt động**:

~~~text
device transaction:
    device_code_verifier -> giao dịch #D-104
    user_code_normalized -> giao dịch #D-104
    client_id            -> shop-tv
    requested_scopes     -> orders:read
    allowed_resources    -> https://orders.example.com
    created_at           -> thời điểm cấp mã
    expires_at           -> thời điểm hết hạn
    status               -> PENDING
~~~

Đây là metadata **minh họa của AS**, không phải JSON payload bắt buộc hay schema chuẩn. AS phải có cách tra cứu user code chính xác, tránh collision với code đang hoạt động, và giữ trạng thái đủ nhất quán cho cả trang xác minh và token polling.

### 4.3. Device authorization endpoint không cấp access token

Lúc nhận yêu cầu khởi tạo, AS **chưa có quyết định của Alice** và không được xem `client_id=shop-tv` là quyền truy cập tài khoản Alice. Phản hồi chỉ chứa thông tin để **bắt đầu và ghép nối** giao dịch. Nếu AS trả ngay access token để gọi Orders API ở bước này, device flow đã mất phần kiểm soát chính của người dùng.

## 5. Cách hiển thị user code và verification URI cho người dùng

Thiết bị cần hiển thị thông tin rõ, có thể hành động được, và không gây nhầm lẫn với mã đăng nhập hay mật khẩu.

### 5.1. Màn hình gợi ý

~~~text
Kết nối Shop TV

Trên điện thoại hoặc máy tính:

  1. Mở: login.example.com/activate
  2. Nhập mã: T8KQ-M7PL
  3. Kiểm tra "Shop TV" và quyền "Xem đơn hàng"
     trước khi chọn Chấp thuận.

Mã còn hiệu lực trong khoảng 15 phút.

[Hủy]                  Đang chờ xác nhận...
~~~

Thiết kế nên:

- Hiển thị **tên miền đầy đủ** của AS tin cậy; khi cần, hiển thị URL có giao thức HTTPS để người dùng không bị đưa đến website giả.
- Hiển thị mã với font lớn, phân nhóm ký tự dễ đọc; không đánh lừa người dùng rằng họ cần đưa mật khẩu vào TV.
- Giải thích rõ phải tự mở trang trên **điện thoại hoặc máy tính tin cậy**.
- Hiển thị tiến trình chờ, thời gian hết hạn và cách **hủy** nếu không muốn liên kết.
- Có **đường thủ công bằng URL + user code** ngay cả khi hỗ trợ QR.
- Tránh che khuất mã/URL bằng hình quảng cáo, banner hoặc thông điệp thiếu tin cậy.

Nếu verification URI là trang có nhiều tài khoản hoặc nhiều profile, AS phải xác định user đang đăng nhập và **hiển thị danh tính đang chấp thuận**, để tránh cấp quyền bằng nhầm tài khoản.

### 5.2. Định dạng user code phục vụ con người

Ví dụ mã `T8KQ-M7PL` được chia thành hai nhóm để dễ đọc. Đây là **một lựa chọn thiết kế**, không phải mẫu cố định bắt buộc của RFC 8628. AS có thể dùng số, chữ hoa hoặc một bảng chữ cái được chọn để tránh nhầm như `O/0`, `I/1`, tùy sản phẩm.

Khi tiếp nhận mã, AS có thể chuẩn hóa theo chính sách rõ ràng:

~~~text
Hiển thị:  T8KQ-M7PL
Người dùng gõ: t8kq m7pl
Chuẩn hóa theo hợp đồng: T8KQM7PL
Tra cứu mã đang PENDING
~~~

Đó là **chính sách UX của AS**, không phải quy tắc OAuth buộc mọi mã không phân biệt chữ hoa/thường. Nếu cho phép bỏ dấu nối, khoảng trắng hoặc phân biệt chữ thường, phải áp giống nhau ở giao diện và backend, tránh việc nhiều mã nhập khác nhau trở thành cùng một định danh ngoài dự tính.

### 5.3. URI phải dễ gõ, nhưng nguồn phải đáng tin

`verification_uri` nên ngắn và dễ nhớ, nhưng vẫn là URL đến **Authorization Server đáng tin qua HTTPS**. Người dùng không nên gõ một miền được in từ email ngẫu nhiên mà không kiểm tra nguồn. Thiết bị nên hiển thị URL do AS trả về theo **issuer/metadata đã cấu hình tin cậy**; client không được tự nhận mọi URL do server không xác thực trả về là an toàn.

Nếu thiết bị bị thay firmware hoặc client bị cấu hình tới AS giả, chỉ riêng việc có đường dẫn trông giống `/activate` không chứng minh website là AS chính thức. Cần kiểm tra TLS, issuer, client registration và hợp đồng endpoint.

## 6. `verification_uri_complete`: liên kết và QR đã chứa mã

Ngoài `verification_uri`, AS **có thể** trả về `verification_uri_complete`:

~~~json
{
  "verification_uri": "https://login.example.com/activate",
  "verification_uri_complete": "https://login.example.com/activate?user_code=T8KQ-M7PL",
  "user_code": "T8KQ-M7PL"
}
~~~

Đường dẫn đầy đủ có thể dùng để tạo QR code trên TV hoặc cung cấp một liên kết thuận tiện cho thiết bị hỗ trợ truyền link. Khi Alice mở link:

1. Trình duyệt tới đúng trang HTTPS của AS.
2. AS có thể **tự điền mã** hoặc dẫn thẳng tới trang xác minh giao dịch tương ứng.
3. Alice **vẫn cần xem và xác nhận đúng yêu cầu cấp quyền**, không được cấp token chỉ vì URL được mở.

**`verification_uri_complete` là tùy chọn.** Không phải AS nào cũng trả trường này; client cần có phương án **hiển thị verification URI và user code thủ công**.

### 6.1. QR làm giảm thao tác nhập, không thay consent

~~~mermaid
flowchart TD
    A[TV hiển thị mã và QR] --> B[Người dùng quét bằng điện thoại]
    B --> C[Trình duyệt mở verification_uri_complete của AS]
    C --> D{Đúng domain AS tin cậy?}
    D -- Không --> X[Dừng, không cung cấp credential]
    D -- Có --> E[AS xác thực người dùng nếu cần]
    E --> F[Hiển thị client, quyền và mã yêu cầu]
    F --> G{Người dùng đang chủ động liên kết đúng thiết bị?}
    G -- Không --> H[Từ chối hoặc hủy]
    G -- Có --> I[Chấp thuận theo policy]
    I --> J[TV polling nhận token từ AS]
~~~

**Không được auto-approve** chỉ vì mã đã được điền bằng QR. Một link QR có thể đến từ thiết bị của attacker hoặc một tấm ảnh/website giả. Việc mở đúng tên miền AS chưa chứng minh **người yêu cầu là TV của Alice**.

### 6.2. Rủi ro rò mã qua URL đầy đủ

`verification_uri_complete` có thể mang `user_code` trong query string. Khác với OAuth bearer access token, đây là **pairing code ngắn hạn** được thiết kế để con người nhập/truyền, không phải credential trực tiếp gọi API. Nhưng nó vẫn nhạy cảm trong ngữ cảnh ghép nối:

- Browser history, clipboard, bookmark hoặc ảnh chụp màn hình có thể lưu URL.
- Reverse proxy/CDN, web access log, công cụ analytics, APM và crash report có thể ghi query.
- Chia sẻ QR hoặc link cho người khác có thể giúp họ **định vị yêu cầu cấp quyền đang chờ**.
- Hành vi gửi `Referer` phụ thuộc chính sách trình duyệt, origin và điều hướng; không nên giả định mọi request luôn gửi toàn query.

Biện pháp giảm rủi ro tại trang xác minh:

1. Dùng HTTPS và giới hạn script bên thứ ba/tracker trên các trang chứa pairing code.
2. Không log nguyên query chứa `user_code`; nên ghi route template và request ID đã bảo vệ.
3. Áp `Referrer-Policy` thích hợp và quản lý caching; khi xử lý mã trong URL có thể chuyển sang trang sạch sau khi ghi nhận giao dịch bằng session state an toàn.
4. Không tạo open redirect để chuyển tiếp pairing code tới domain khác.
5. Ràng buộc user code với đúng giao dịch, TTL, trạng thái và quy trình consent.

**Không sử dụng `verification_uri_complete` như nơi truyền access token, refresh token, `device_code` hoặc client secret.** Việc RFC cho phép URI chứa user code không hợp thức hóa đưa bearer token vào query.

### 6.3. Người dùng vẫn nên nhìn thấy mã trên cả hai màn hình

Khi trang AS có thể tự điền code từ QR, nó nên hiển thị hoặc cho xác nhận mã/tên thiết bị để Alice **đối chiếu với màn hình TV đang trước mặt**. Nếu hai màn hình khác nhau, phải dừng.

Đối chiếu mã là **một dấu hiệu ngữ cảnh**, không phải bằng chứng mật mã về sở hữu thiết bị: attacker có thể trình cho nạn nhân một mã hoàn toàn nhất quán do chính attacker xin. Vì thế giao diện cũng phải hỏi **Alice có chủ động khởi tạo liên kết thiết bị này không** và ứng dụng đang xin những quyền gì.

## 7. Sinh user code: dễ nhập nhưng không thể đoán tùy tiện

`user_code` thường ngắn hơn nhiều so với `device_code` vì người dùng phải nhập bằng tay. Điều này tạo rủi ro **brute force và collision**: nếu thử được nhiều mã, attacker có thể tìm ra một yêu cầu đang chờ để gây nhầm lẫn hoặc khiến người dùng chấp thuận sai thiết bị.

### 7.1. Entropy và bề mặt thử mã

Giả sử mã gồm `L` ký tự, mỗi ký tự chọn độc lập trong bảng chữ cái có `N` giá trị thì không gian mã lý thuyết là:

\[
|\text{CodeSpace}| = N^L
\]

Tăng độ dài hoặc độ lớn bảng chữ cái làm tăng không gian mã, nhưng có đánh đổi về khả năng đọc/nhập. **Bảo mật thực tế phụ thuộc cả số mã đang hoạt động, TTL và số lần AS cho phép thử**, không chỉ độ dài mã.

Ví dụ, mã dễ đọc chỉ dùng chữ hoa và số đã lọc ký tự nhầm lẫn có thể giúp người dùng nhập chính xác hơn; AS phải kết hợp:

- CSPRNG khi sinh user code, không dùng số tăng dần hoặc timestamp dễ đoán.
- Không tái sử dụng cùng một mã cho hai giao dịch **đang hoạt động** có thể gây nhập nhằng.
- TTL phù hợp với thao tác nhập nhưng không kéo dài không cần thiết.
- Rate limit theo IP, account/session, client hoặc các tín hiệu liên quan; cân nhắc giới hạn toàn hệ thống để ngăn phân tán thử mã.
- Chống enumeration và bảo vệ backend lookup khỏi việc tiết lộ có hay không một mã còn sống.

**Không có một con số độ dài user code duy nhất đúng cho mọi hệ thống.** Phải thiết kế dựa trên entropy, UX, tốc độ thử tối đa và mức độ nhạy cảm của quyền có thể cấp. RFC 8628 đặc biệt lưu ý đến brute-force protection của user code.

### 7.2. Tách không gian user code và device code

| Thuộc tính | User code | Device code |
|---|---|---|
| Người dùng nhập bằng tay? | Có, hoặc QR/link hỗ trợ | Không |
| Yêu cầu dễ đọc? | Cao | Không |
| Độ dài thực tế | Thường ngắn và được phân nhóm | Có thể dài, không cần tối ưu UX |
| Được hiển thị trên màn hình? | Có | **Không** |
| Được gửi tới token endpoint khi polling? | Không | **Có** |
| Kiểm soát bảo mật | Entropy, rate limit, TTL, uniqueness, binding | Entropy cao, TTL, client binding, trạng thái, anti-replay |

Một sai lầm nghiêm trọng là dùng **cùng một chuỗi** cho `user_code` và `device_code`. Khi đó, mã đang hiển thị cho người dùng có thể trở thành credential giúp attacker polling token endpoint. Hai giá trị nên được thiết kế độc lập với mục đích khác nhau.

### 7.3. Lưu trữ và đối chiếu user code

AS có thể lưu dạng đã chuẩn hóa và một **verifier/lookup key** bảo vệ, ví dụ:

~~~text
user_code_lookup      = HMAC(server_secret, normalized_user_code)
device_code_lookup    = HMAC(server_secret, raw_device_code)
transaction_id        = tx-104
client_id             = shop-tv
state                 = PENDING
requested_scopes      = orders:read
expires_at            = ...
failed_attempt_count  = 0
~~~

Đây là schema **minh họa**, không phải thuật toán lưu trữ bắt buộc của RFC. HMAC key phải được bảo vệ riêng. Vì user code có **entropy thấp hơn token ngẫu nhiên dài**, việc dùng hash không khóa tùy ý có thể dễ bị kiểm tra offline nếu DB bị lộ. Thiết kế lưu trữ cần xem xét khả năng đoán mã sau lộ DB và nhu cầu tra cứu.

Nếu AS cần tra cứu theo mã con người nhập, phải chuẩn hóa **trước khi tính lookup** theo cùng quy tắc đã dùng lúc phát hành. Đừng chấp nhận các biến thể Unicode hoặc bỏ ký tự một cách bất nhất để tránh hai mã hợp lệ bị nhập nhằng.

### 7.4. Rate limiting phải chống đoán mã nhưng không tự tạo DoS

Một limiter có thể xét nhiều chiều:

~~~text
verification_attempts:
    source network / IP (có xét NAT)
    browser session / authenticated account
    client registration
    global requests per interval
    mã nhập sai liên tiếp
~~~

Không chỉ khóa theo một IP vì nhiều người dùng thật có thể cùng NAT; không chỉ khóa theo một user account vì attacker có thể dùng nhiều tài khoản hoặc IP. Hệ thống cần kiểm soát tổng thể, khả năng điều tra và độ trễ phản hồi hợp lý.

Nếu attacker cố nhập sai mã của một người dùng để **khóa giao dịch hợp lệ**, AS cần cân nhắc chính sách bảo vệ chống DoS thay vì để một vài lần nhập sai từ bất kỳ nguồn nào làm mất toàn bộ yêu cầu device flow. Mục tiêu là hạn chế brute force mà không khiến mọi user khó đăng nhập.

### 7.5. Mã hết hạn và tái phát hành

Khi mã hết hạn:

1. Trang AS không được tiếp tục chấp thuận giao dịch dựa trên user code cũ.
2. Device polling phải nhận kết quả hết hạn theo giao thức và dừng.
3. Nếu Alice muốn tiếp tục, TV khởi tạo **device authorization request mới** và hiển thị cặp code mới.
4. AS không tái kích hoạt cùng giao dịch cũ chỉ vì người dùng nhấn tải lại trang.

Tái sử dụng user code sau khi các giao dịch cũ đã hết hạn cần chính sách chống nhầm lẫn, retention và bảo đảm mapping chỉ tới **một giao dịch đang hiệu lực**, không tự biến code cũ thành mã mới của một thiết bị khác trong cửa sổ mơ hồ.

## 8. Trang verification URI phải xác thực và yêu cầu phê duyệt

Đây là nơi một user code chuyển từ "mã hiển thị" thành **quyết định ủy quyền có chủ ý**.

### 8.1. Các bước ở Authorization Server

1. Người dùng truy cập **verification URI** hợp lệ của issuer qua HTTPS.
2. AS xác thực người dùng nếu chưa có phiên hoặc cần xác thực lại theo policy.
3. Người dùng nhập user code, hoặc AS xử lý user code đã được điền từ `verification_uri_complete`.
4. AS chuẩn hóa và tra mã, kiểm tra TTL, trạng thái và giới hạn thử.
5. AS lấy **client registration và grant thực tế**, hiển thị ứng dụng nào đang yêu cầu quyền, quyền và tài nguyên liên quan.
6. Người dùng đối chiếu ngữ cảnh với **thiết bị đang chủ động ghép nối**.
7. Người dùng chọn **Chấp thuận** hoặc **Từ chối**.
8. AS lưu quyết định có ràng buộc với user đã xác thực, client, scope/resource và device transaction, có audit phù hợp.

**Không đủ:** "user code khớp thì tự APPROVED". Nếu không xác thực user/consent theo policy, bất kỳ ai đoán mã có thể tạo ra một kết quả cấp quyền trái phép hoặc gây nhầm lẫn.

### 8.2. Nội dung xác nhận nên hiển thị

~~~text
Yêu cầu kết nối thiết bị

Ứng dụng: Shop TV
Mã đang xác minh: T8KQ-M7PL
Tài khoản: alice@example.com
Quyền yêu cầu: Xem danh sách đơn hàng

Bạn có đang thiết lập Shop TV trên thiết bị trước mặt?

[Từ chối]       [Chấp thuận kết nối]
~~~

Ví dụ hiển thị email chỉ để minh họa; ứng dụng thực tế phải tuân thủ chính sách dữ liệu cá nhân và không hiển thị account/email cho người chưa xác thực. AS cần kiểm tra **client name đã được đăng ký và kiểm soát tin cậy**, không lấy tên ứng dụng trực tiếp từ request không xác minh vì attacker có thể giả tên.

Nếu app yêu cầu scope nhạy cảm như thay đổi thanh toán, xóa dữ liệu hoặc đọc dữ liệu doanh nghiệp, AS có thể yêu cầu xác thực bổ sung, user consent cụ thể hoặc **cấm Device Grant** đối với client/scope đó theo policy.

### 8.3. Không cho phép tự phê duyệt qua GET

Mở verification URI hoặc link QR bằng HTTP GET phải **không tự thay đổi trạng thái thành APPROVED**. Một link có thể bị mở bởi browser preview, công cụ quét an toàn hoặc bên thứ ba. Hành động chấp thuận nên là thao tác rõ ràng trong phiên user đã xác thực, có bảo vệ CSRF/session theo kiến trúc.

Sau khi duyệt, AS có thể hiển thị "Bạn có thể quay lại TV". Trang điện thoại **không cần chứa access token của TV** và không nên trả device_code hoặc refresh token cho browser.

### 8.4. Ràng buộc danh tính, scope, audience và tenant

Một yêu cầu đến từ `shop-tv` có thể xin `orders:read`. Khi Alice chấp thuận, AS phải tạo grant giới hạn:

~~~text
subject = alice-123
client = shop-tv
scope = orders:read
audience = https://orders.example.com
device_transaction = tx-104
status = APPROVED
~~~

Không được cấp `orders:delete` hay token dành cho Billing API chỉ vì TV đã được ghép nối. Nếu có tenant, tổ chức hoặc role cụ thể, phải áp policy tương ứng. **User code giúp tìm đúng transaction; nó không mang tự thân quyền admin hoặc audience.**

## 9. Device polling: thiết bị biết người dùng đã xác minh bằng cách nào?

Shop TV không cần giao tiếp trực tiếp với điện thoại Alice. Thay vào đó, TV gửi **`device_code`** đến token endpoint của AS theo khoảng thời gian AS quy định. AS tham chiếu đến cùng một device transaction mà trang verification URI đã cập nhật.

### 9.1. Token request dùng device code grant

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=<OPAQUE_DEVICE_CODE>&client_id=shop-tv
~~~

Grant type chính thức của RFC 8628 là:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

Trong HTTP form body, ký tự `:` phải được mã hóa phù hợp như ví dụ trên. Với confidential client, AS yêu cầu client authentication theo phương thức đã đăng ký; ví dụ public client có `client_id` để AS xác định client liên quan. Không gửi `user_code` làm thay `device_code` trong token request.

### 9.2. Khi Alice chưa chấp thuận

AS trả lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "authorization_pending"
}
~~~

Điều này có nghĩa yêu cầu vẫn còn chờ; **không phải bằng chứng đăng nhập thất bại** và không phải lệnh cấp token. Client tiếp tục polling theo giới hạn.

### 9.3. Khi client polling quá nhanh

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "slow_down"
}
~~~

Theo RFC 8628, khi nhận `slow_down`, client phải **tăng khoảng polling thêm 5 giây** so với khoảng trước đó cho lần gọi này và các lần gọi tiếp theo. Không được phớt lờ `slow_down`, gửi burst request hoặc reset interval về 0 sau khi lỗi.

### 9.4. Khi Alice chấp thuận và AS phát token

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN_FOR_ORDERS_API>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

AS có thể cấp **refresh token** theo grant/client/policy; không được mặc định mọi Device Authorization Grant đều có refresh token. Trong hệ thống có OIDC profile phù hợp, có thể có ID token theo các quy tắc OIDC tương ứng; không tự yêu cầu/nhận ID token chỉ vì user đã vào trang verification URI.

TV dùng **access token đúng audience** gọi Orders API:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

Orders API kiểm tra issuer, audience, thời gian, scope, token type và quyền Alice đối với **đơn hàng cụ thể**. Một access token có `scope=orders:read` chưa tự cấp quyền đọc mọi đơn hàng của mọi user.

### 9.5. Phân loại các lỗi polling quan trọng

| Kết quả từ token endpoint | Thiết bị phải làm gì? |
|---|---|
| `authorization_pending` | Giữ giao dịch và poll tiếp, không vượt interval |
| `slow_down` | **Tăng interval thêm 5 giây**, poll lại chậm hơn |
| `access_denied` | Dừng polling; hiển thị người dùng đã từ chối hoặc yêu cầu không được duyệt |
| `expired_token` | Dừng polling; nếu muốn tiếp tục thì xin **cặp device/user code mới** |
| HTTP 200 có token hợp lệ | Dừng polling, lưu token an toàn; không tiếp tục đổi device code |
| `invalid_client` hoặc lỗi xác thực khác | Dừng/khắc phục cấu hình, không thử client secret tùy tiện |
| Lỗi network/timeout | Giảm tần suất, retry có kiểm soát; không tạo vòng request dồn |

Đối với token endpoint, cả thiết bị lẫn AS phải kiểm tra **code, client binding, grant state và TTL**. Không chỉ đọc một cờ boolean từ cache rồi phát token.

### 9.6. Khoảng polling ban đầu

AS trả `interval` bằng **giây** nếu muốn chỉ định tần suất polling. Khi `interval` **không có**, RFC 8628 quy định client phải dùng mặc định **5 giây**. Thiết bị không được polling nhanh hơn khoảng thời gian áp dụng.

~~~text
Ví dụ:
    interval ban đầu = 5 giây
    POST /token -> authorization_pending
    chờ ít nhất 5 giây
    POST /token -> slow_down
    tăng khoảng chờ lên 10 giây
    chờ ít nhất 10 giây
    POST /token -> authorization_pending
    tiếp tục theo khoảng 10 giây, không trở lại 5 giây
~~~

Khi kết nối timeout, client cũng nên **giảm tần suất polling** để giảm tải cho AS; dùng backoff theo profile, không xoay vòng thật nhanh vì không thấy response.

### 9.7. User code không có mặt trong polling request

Trong quy trình đúng:

- **Trang web của AS:** nhận user code để tìm giao dịch cần người dùng xác minh.
- **Token endpoint của AS:** nhận device code để tìm giao dịch cần trả kết quả polling.

Một API cho phép polling bằng `user_code` là sai hướng thiết kế: mã ngắn hiển thị công khai có thể trở thành credential để truy xuất access token. Không tái sử dụng user code như bearer token hoặc API key.

## 10. State machine và single-use của device transaction

Thiết kế server cần tránh các trạng thái "đã xác minh" chung chung. Có ít nhất ba đường kết thúc khác nhau: **chấp thuận**, **từ chối**, **hết hạn**. Sau khi TV nhận token thành công, transaction cần chuyển sang trạng thái không thể phát tiếp.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Tạo user_code + device_code
    PENDING --> APPROVED: User đã đăng nhập và chấp thuận
    PENDING --> DENIED: User từ chối
    PENDING --> EXPIRED: Hết TTL
    APPROVED --> CONSUMED: Polling hợp lệ, cấp token một lần
    APPROVED --> EXPIRED: Hết TTL trước khi đổi token
    DENIED --> [*]
    EXPIRED --> [*]
    CONSUMED --> [*]
~~~

Đây là **mô hình triển khai minh họa**. Tên trạng thái nội bộ không bắt buộc theo RFC. Điểm bất biến là **không có token trước chấp thuận, không có token sau từ chối/hết hạn, và không phát nhiều bộ token trái phép từ một device transaction**.

### 10.1. Bất biến cần cưỡng chế

1. **Mỗi `user_code` đang hoạt động ánh xạ đúng một transaction.**
2. **Mỗi `device_code` ánh xạ đúng một transaction và client đã khởi tạo.**
3. `PENDING` không thể tự thành `APPROVED` chỉ vì có HTTP GET tới verification URI.
4. Chỉ người dùng đã xác thực, qua trang/điều kiện consent phù hợp, mới có thể đưa yêu cầu sang `APPROVED`.
5. `DENIED` hoặc `EXPIRED` không được chuyển thành `APPROVED` bằng request cũ.
6. Token endpoint chỉ cấp token khi trạng thái và TTL hợp lệ **tại thời điểm xử lý**, không tin bản sao cache cũ.
7. Sau khi phát token thành công, `device_code` phải được tiêu thụ để không cấp lại token ngoài chính sách.
8. Scope, audience, client và subject lấy từ grant/transaction đã được AS xác minh, không từ tham số tự khai khi polling.

### 10.2. Tại sao atomicity quan trọng?

Giả sử AS có hai node và Shop TV gửi hai poll requests cùng lúc:

~~~text
Node A: đọc tx-104 = APPROVED
Node B: đọc tx-104 = APPROVED
Node A: cấp token A1, đánh dấu CONSUMED
Node B: cấp token A2, đánh dấu CONSUMED
=> Hai lần phát token từ cùng device transaction.
~~~

Server nên dùng **transaction, row-level lock, compare-and-swap/version hoặc cơ chế tương đương** để đảm bảo chuyển `APPROVED → CONSUMED` và lưu trạng thái token đúng một lần theo policy. Phải áp nhất quán qua mọi AS nodes/regions.

Một client gửi nhiều poll đồng thời là lỗi vận hành; server vẫn phải **fail closed** khi gặp concurrency. `device_code` đã dùng không được "khôi phục APPROVED" chỉ vì client báo response bị mất.

### 10.3. User code chỉ chọn giao dịch, không cấp grant mới

Sau khi user code được nhập và xác nhận, AS không được sao chép approval sang một transaction khác có cùng client name hoặc cùng thiết bị. Một attacker có thể mở nhiều device requests đồng thời:

~~~text
Transaction A -> user_code A -> device_code A
Transaction B -> user_code B -> device_code B
~~~

Nếu Alice duyệt **A**, chỉ A được chuyển APPROVED. B phải tiếp tục PENDING hoặc hết hạn. Không duyệt theo `client_id` đơn thuần hoặc một flag "Shop TV is approved" chung cho mọi device request.

### 10.4. Người dùng hủy trên TV

Khi TV có nút Hủy, UI phải dừng polling. Nếu AS có API hủy transaction phù hợp, có thể cập nhật trạng thái server; **chỉ dừng UI không nhất thiết làm device code phía AS mất hiệu lực**. Không để một transaction còn APPROVED/PENDING ngoài ý muốn nếu threat model yêu cầu thu hồi ngay.

Khi TV yêu cầu mã mới, cần quy định rõ mã cũ bị hủy/hết hạn hay có thể vẫn sống; tốt nhất tránh hiển thị hai user codes song song làm người dùng nhập nhầm.

## 11. Device-code phishing: domain thật chưa đủ chứng minh thiết bị thật

Một rủi ro đặc trưng của Device Authorization Grant là attacker có thể **khởi tạo yêu cầu device authorization trên thiết bị của attacker**, rồi lừa nạn nhân nhập `user_code` của yêu cầu đó vào **trang AS thật**.

### 11.1. Diễn biến tấn công

~~~mermaid
sequenceDiagram
    participant X as Attacker / device giả
    participant AS as Authorization Server thật
    actor U as Nạn nhân
    participant B as Browser nạn nhân
    X->>AS: POST device_authorization bằng client đăng ký/giả mạo được
    AS-->>X: device_code X + user_code X
    X-->>U: Tin nhắn dụ mở trang AS và nhập user_code X
    U->>B: Mở verification_uri thật
    B->>AS: Nhập user_code X
    AS-->>B: Trang đăng nhập và yêu cầu chấp thuận
    U->>B: Chấp thuận vì hiểu nhầm là xác minh tài khoản
    B->>AS: Phê duyệt transaction X
    X->>AS: Polling bằng device_code X
    AS-->>X: Access token nếu policy cho phép
~~~

Điểm nguy hiểm là **verification URI có thể đúng tên miền chính thức**, nên lời khuyên "chỉ cần kiểm tra URL hợp lệ" **chưa đủ**. Kẻ tấn công không cần giả trang AS nếu có thể dụ nạn nhân duyệt một yêu cầu thiết bị do attacker khởi tạo.

Mã code đúng trên trang AS chỉ chứng minh nó thuộc một yêu cầu đang chờ; nó **không chứng minh nạn nhân thực sự đang cầm thiết bị yêu cầu**.

### 11.2. Dấu hiệu nhận biết

- Một email/chat/cuộc gọi không mong đợi bảo người dùng vào trang kích hoạt thiết bị để "tránh khóa tài khoản" hoặc "xác minh thanh toán".
- Người dùng **không đang mở một TV/CLI/thiết bị cần ghép nối** mà vẫn được yêu cầu nhập mã.
- Trang xác minh hiển thị client, scope hoặc thiết bị không khớp với những gì người dùng đang làm.
- Người gọi gửi QR/link đầy đủ có mã và yêu cầu nhấn **Chấp thuận** gấp.
- Ứng dụng yêu cầu quyền lớn hơn chức năng người dùng dự kiến.

### 11.3. Kiểm soát tại Authorization Server

1. Giao diện xác minh nêu rõ: **"Chỉ chấp thuận nếu bạn vừa chủ động bắt đầu đăng nhập/kết nối trên một thiết bị mà bạn kiểm soát."**
2. Hiển thị client đã đăng ký, publisher/nhà phát triển nếu đáng tin, scope được mô tả dễ hiểu và tài khoản đang xác minh.
3. Đối chiếu user code với màn hình thiết bị; QR tự điền code vẫn nên hiển thị để đối chiếu.
4. Dùng consent rõ ràng, không tự approve khi user mở link hoặc nhập mã.
5. Áp policy chặt với client/public device grant, scope nhạy cảm, yêu cầu xác thực bổ sung hoặc chặn grant theo rủi ro.
6. Giám sát các mẫu bất thường như số transaction khởi tạo cao, mã được nhập từ nhiều bối cảnh, tỷ lệ approval và token issuance.
7. Cho người dùng cách xem và thu hồi các thiết bị/session đã liên kết.

**Không dựa duy nhất vào IP, geolocation hoặc tên thiết bị như bằng chứng sở hữu.** IP có thể đổi do mạng di động/NAT/VPN; tên client có thể gây nhầm nếu không được kiểm soát; user code không phải proof-of-possession của thiết bị.

### 11.4. Kiểm soát ở thiết bị và người dùng

Thiết bị thật:

- Chỉ hiển thị verification URI do **AS tin cậy** trả về sau TLS/issuer validation.
- Hiển thị code/QR và tên ứng dụng rõ ràng; không yêu cầu người dùng cung cấp mật khẩu cho thiết bị.
- Có nút Hủy, xử lý hết hạn và yêu cầu cấp mã mới minh bạch.
- Chỉ lưu token sau khi polling nhận success hợp lệ, không tự chuyển sang trạng thái connected khi mã mới được nhập.

Người dùng:

- Chỉ nhập user code khi **chính mình vừa kích hoạt luồng trên thiết bị đang có mặt**.
- Mở trang AS chính thức thay vì dựa hoàn toàn vào link lạ gửi qua chat/email.
- Kiểm tra ứng dụng/quyền/tài khoản trước khi chấp thuận.
- Từ chối mọi yêu cầu không rõ nguồn hoặc không khớp thiết bị.

**User code là tín hiệu ghép nối, không phải bí mật để gửi cho nhân viên hỗ trợ.** Nhân viên hỗ trợ hợp lệ cũng không nên yêu cầu khách hàng nhập/chấp thuận mã device authorization do bên khác cung cấp để "xác minh danh tính".

## 12. Mẫu thiết kế Java: client hiển thị mã và polling đúng

Các ví dụ Java sau tập trung vào **trách nhiệm của client**. Những type như `DeviceAuthorizationClient`, `DeviceGrantResponse`, `PollResult` và `TokenStore` là **pseudocode của ứng dụng**, không phải API Spring Security có sẵn. Với hệ thống thật, nên dùng OAuth client library hỗ trợ RFC 8628 thay vì tự thực hiện token endpoint và xử lý credential bằng tay.

### 12.1. Dữ liệu cần lưu tạm trong thiết bị

~~~java
// DTO minh họa, không phải class do RFC/Spring cung cấp.
record DeviceGrantResponse(
        String deviceCode,
        String userCode,
        URI verificationUri,
        URI verificationUriComplete,
        long expiresInSeconds,
        Long intervalSeconds) {}
~~~

Sau khi gọi device authorization endpoint, client phải giữ **deviceCode** trong kho tạm an toàn và chỉ hiển thị:

~~~text
Verification URI: https://login.example.com/activate
User code:       T8KQ-M7PL
Expires in:      900 seconds
Optional QR:     verification_uri_complete
~~~

Không in `deviceCode` cùng userCode vào UI; không gửi cả JSON response vào crash report. `verificationUriComplete` có thể là `null`, nên phải luôn có đường thủ công bằng URI + user code.

### 12.2. State machine phía client

~~~java
// Pseudocode: scheduler/HTTP callbacks là các helper ứng dụng.
void activateDevice(DeviceAuthorizationClient client,
                    DeviceUi ui,
                    Clock clock,
                    TokenStore tokenStore) {

    DeviceGrantResponse challenge =
        client.requestDeviceAuthorization("shop-tv", "orders:read");

    ui.showPairingCode(
        challenge.verificationUri(),
        challenge.userCode(),
        challenge.verificationUriComplete());

    Instant deadline = clock.instant()
        .plusSeconds(challenge.expiresInSeconds());

    long interval = challenge.intervalSeconds() != null
        ? challenge.intervalSeconds()
        : 5L; // RFC 8628: 5 giây khi server bỏ interval.

    while (clock.instant().isBefore(deadline) && !ui.isCancelled()) {
        scheduler.waitAtLeastSeconds(interval);

        PollResult result = client.pollTokenEndpoint(
            challenge.deviceCode(), "shop-tv");

        switch (result.kind()) {
            case AUTHORIZATION_PENDING -> {
                ui.showWaiting();
            }
            case SLOW_DOWN -> {
                interval += 5L;
                ui.showWaiting();
            }
            case ACCESS_DENIED -> {
                ui.showDenied();
                return;
            }
            case EXPIRED_TOKEN -> {
                ui.showExpired();
                return;
            }
            case SUCCESS -> {
                tokenStore.saveSecurely(result.credentials());
                ui.showConnected();
                return;
            }
            case FATAL_ERROR -> {
                ui.showError();
                return;
            }
            case NETWORK_TIMEOUT -> {
                interval = retryPolicy.increaseWait(interval);
            }
        }
    }

    ui.showExpiredOrCancelled();
}
~~~

**Không dùng mã này như một client production có thể biên dịch ngay.** `scheduler`, `retryPolicy`, `ui`, `PollResult` đều được giả định. Khi thực thi thật cần xử lý HTTP error JSON, clock, server rate limit, trạng thái cancel, TLS, retry policy, secrets, concurrency và lifecycle bằng thư viện đáng tin.

### 12.3. Vì sao không polling ngay trong vòng lặp không delay?

Sai:

~~~java
// SAI: gửi liên tục có thể tạo quá tải và bị slow_down.
while (!isAuthorized()) {
    pollTokenEndpoint(deviceCode);
}
~~~

Việc lặp nhanh không khiến user chấp thuận sớm hơn. Nó chỉ tăng tải lên AS, dễ bị rate limit và thậm chí chặn nhầm client thật. Áp **interval**, `slow_down`, backoff sau timeout và thời hạn giao dịch; không tự bypass server throttle.

### 12.4. Sau khi nhận token

Client chỉ gửi **access token** cho Orders API:

~~~java
// Pseudocode Spring RestClient; accessToken lấy từ kho bảo vệ.
RestClient ordersClient = RestClient.builder()
    .baseUrl("https://orders.example.com")
    .build();

OrderDto order = ordersClient.get()
    .uri("/api/orders/{id}", orderId)
    .headers(h -> h.setBearerAuth(accessToken))
    .retrieve()
    .body(OrderDto.class);
~~~

Device code, user code và verification URI **không được dùng làm bearer credential cho resource server**. Orders API phải xác minh JWT/opaque access token đúng issuer, audience, thời gian và scope, sau đó áp authorization theo owner/tenant/action cụ thể.

## 13. Mẫu xử lý phía Authorization Server

Phía AS mới là nơi quyết định user code thuộc giao dịch nào, user nào đã chấp thuận và khi nào device code được đổi thành token. Các đoạn sau chỉ là **pseudocode kiến trúc**; production cần OAuth framework, transaction và policy đầy đủ.

### 13.1. Xác minh user code trên trang AS

~~~java
// Pseudocode: user đã đăng nhập theo session/AS policy.
VerificationView openVerificationPage(
        AuthenticatedUser user,
        String enteredUserCode) {

    String normalized = userCodePolicy.normalize(enteredUserCode);
    rateLimiter.checkVerificationAttempt(user, normalized);

    DeviceTransaction tx =
        transactionStore.findPendingByUserCode(normalized);

    if (tx == null || tx.isExpired()) {
        // Không tiết lộ mã thuộc client/user nào.
        return VerificationView.invalidOrExpired();
    }

    RegisteredClient registeredClient =
        clientRegistry.load(tx.clientId());

    return VerificationView.confirmation(
        tx.id(),
        registeredClient.verifiedDisplayName(),
        tx.requestedScopes(),
        tx.allowedResources(),
        user.displayAccountName());
}
~~~

**Chỉ hiển thị confirmation view, chưa APPROVE.** Việc mở trang hay nhập code không phải quyết định cấp quyền. Backend cần session protection, CSRF, giới hạn thử code và dữ liệu hiển thị đã lọc/bảo vệ.

### 13.2. Chấp thuận phải là hành động riêng

~~~java
// Pseudocode: ví dụ có CSRF/session protection và consent rõ.
void approveDevice(
        AuthenticatedUser user,
        VerificationTransactionId id,
        ConsentDecision decision) {

    transaction.run(() -> {
        DeviceTransaction tx =
            transactionStore.lockAndRead(id);

        require(tx.isPendingAndNotExpired());
        grantPolicy.verifyClientScopeAndResources(
            user, tx.clientId(), tx.requestedScopes(),
            tx.allowedResources());
        csrfAndConsent.verifyUserAction(user, decision);

        if (decision.isApproved()) {
            transactionStore.markApproved(
                tx.id(), user.subjectId(),
                grantPolicy.approvedScopes(user, tx));
        } else {
            transactionStore.markDenied(tx.id());
        }
    });
}
~~~

AS phải ghi quyết định **đúng một transaction** đã được tìm bằng user code. Không cho client khai `subject=alice` hoặc `approved=true` trong device authorization request rồi tự cấp token.

### 13.3. Khi thiết bị polling token endpoint

~~~java
// Pseudocode mô tả điều kiện, không phải OAuth endpoint hoàn chỉnh.
PollOutcome pollDeviceCode(
        VerifiedOAuthClient client,
        String rawDeviceCode,
        Instant now) {

    DeviceTransaction tx =
        transactionStore.findBySecureDeviceCode(rawDeviceCode);
    if (tx == null) {
        return PollOutcome.invalidGrant();
    }

    return transaction.run(() -> {
        DeviceTransaction current =
            transactionStore.lockAndRead(tx.id());

        require(current.belongsTo(client));
        if (current.isExpiredAt(now)) {
            return PollOutcome.expiredToken();
        }
        if (current.isDenied()) {
            return PollOutcome.accessDenied();
        }
        if (pollingPolicy.isTooFrequent(current, now)) {
            pollingPolicy.recordSlowDown(current);
            return PollOutcome.slowDown();
        }
        if (current.isPending()) {
            return PollOutcome.authorizationPending();
        }
        if (!current.isApproved()) {
            return PollOutcome.invalidGrant();
        }

        // Chính sách single-use: không thể cấp token hai lần cùng code.
        transactionStore.markConsumedExactlyOnce(current.id());
        return tokenIssuer.issueOnlyApprovedGrant(current);
    });
}
~~~

Đây là sơ đồ chức năng. Một triển khai thực còn phải **ghi token/grant state nhất quán với transaction**, xác định response OAuth chính xác, xử lý rollback/commit, token signing, client authentication, resource indicators, code expiry, rate limiting và multi-node concurrency.

Nếu lỗi phát token dẫn đến rollback trạng thái CONSUMED, AS không được vô tình mở đường cho hai request cùng đổi device code. Nếu AS cần giữ trạng thái revoke/audit khi trả lỗi, cần bảo đảm thay đổi bảo mật **được commit** trước khi exception dẫn đến rollback tự động.

### 13.4. Đừng dùng user code làm khóa duy nhất mãi mãi

Sau khi APPROVED hoặc EXPIRED, cần có chính sách:

- Ngừng chấp nhận lại user code cũ tại verification page.
- Giữ metadata đủ để audit/replay detection theo retention, **không giữ credential thô tùy tiện**.
- Không map user code cũ sang một device code mới đang sống.
- Không cho hai AS nodes cấp cùng user code còn hiệu lực cho hai transactions.
- Không để một transaction bị phê duyệt nhầm do lookup từ replica thiếu nhất quán.

Mã ngắn cho con người là thành phần của **stateful authorization transaction**, không phải một chuỗi dùng lại vô thời hạn.

## 14. Spring Security và Spring Authorization Server trong device flow

Trong hệ sinh thái Java, cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| **Spring Authorization Server** | Có thể cung cấp device authorization/device verification và token endpoint theo phiên bản/cấu hình hỗ trợ |
| **Spring Security OAuth2 Client** | Thực hiện OAuth client flow theo khả năng thư viện; không mặc định SDK nào cũng hỗ trợ device flow đầy đủ |
| **Spring Security OAuth2 Resource Server** | Xác minh JWT/opaque access token khi Orders API được gọi |

### 14.1. Đăng ký client được phép dùng Device Authorization Grant

Định danh grant theo RFC 8628:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

Khi cấu hình một OAuth client như `shop-tv` tại AS, phải xác định **được phép dùng grant nào**, loại client, scopes/resources và client authentication method. Không cho một client bất kỳ tự xin device flow chỉ vì nó gọi được `/device_authorization`.

Ví dụ metadata **minh họa nội bộ**, không phải schema Spring bắt buộc:

~~~yaml
client_id: shop-tv
client_type: public
allowed_grant_types:
  - urn:ietf:params:oauth:grant-type:device_code
allowed_scopes:
  - orders:read
allowed_resources:
  - https://orders.example.com
device_authorization:
  verification_uri: https://login.example.com/activate
  user_code_ttl_seconds: 900
  polling_interval_seconds: 5
  consent_required: true
~~~

Các trường TTL/policy trên chỉ là **lựa chọn thiết kế của AS**. Cấu hình thực tế phải dựa theo phiên bản Spring Authorization Server, metadata/discovery và validators được hỗ trợ, không sao chép YAML này rồi giả định Spring tự hiểu.

### 14.2. Trang xác minh cần là một phần của Authorization Server

Trang `https://login.example.com/activate` phải có:

- Kết nối tới transaction store được AS bảo vệ.
- Xác thực user, xác minh mã và giới hạn thử.
- Màn hình consent hiển thị client đã đăng ký và quyền thực tế.
- Chống CSRF/session fixation theo kiến trúc web.
- Phê duyệt/từ chối chỉ một transaction, ghi audit an toàn.

Không xây một trang frontend độc lập có quyền gửi `approved=true` vào một public endpoint rồi để AS tin cờ này. Approval phải diễn ra qua một **trust boundary được xác thực và bảo vệ**.

### 14.3. Resource server không kiểm tra user code

Khi Shop TV đã có access token, Orders API thường cấu hình JWT validation hoặc opaque introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Đây mới chỉ là cấu hình issuer. Orders API còn phải **kiểm tra expected audience, thời gian, scope, token type và quyền trên từng order**, và có cơ chế trạng thái/thu hồi khi hệ thống cần. Không đưa user code, device code hay ID token OIDC vào Bearer header của Orders API.

### 14.4. Cấu hình framework không thay kiểm thử giao thức

Ngay cả khi AS framework hỗ trợ RFC 8628, cần kiểm tra thực tế:

- Client registration chỉ cho phép đúng Device Grant và scopes.
- User verification URI HTTPS, code mapping, TTL, rate limiting và consent.
- Polling interval, `slow_down`, các OAuth error codes và trạng thái terminal.
- Một `device_code` không phát nhiều bộ token từ nhiều AS nodes.
- Token được cấp đúng issuer, audience, client, subject và scope.
- Logging, QR, browser session và redirect không làm lộ pairing code hoặc token.

**Không bật endpoint rồi coi như đã hoàn tất bảo mật.** UX xác minh người dùng và chống phishing là phần không thể thiếu của Device Authorization Grant.

## 15. Threat model và các sai lầm thường gặp

### 15.1. Ma trận đe dọa theo ranh giới

| Mối đe dọa | Tấn công vào đâu? | Kiểm soát phù hợp |
|---|---|---|
| **Đoán user code** | Trang verification URI | Code CSPRNG, TTL, rate limit, chống enumeration |
| **User code collision** | AS tạo mã cho nhiều thiết bị | Kiểm soát uniqueness khi mã đang active, transaction binding |
| **Device-code phishing** | Nạn nhân bị dụ duyệt mã của attacker | Consent rõ ràng, đối chiếu mã/thiết bị, giới hạn scope/client, cảnh báo |
| **QR phishing** | Link hoặc QR từ nguồn không tin cậy | HTTPS/domain check, xác nhận ngữ cảnh, không autoapprove |
| **Rò verification_uri_complete** | URL history, log, analytics | Redaction, referrer policy, TTL và xác minh user |
| **Device code bị lộ** | Kho tạm, crash log, debug trace của TV | Secret storage, TTL, client binding, single-use |
| **Tự động phê duyệt bằng GET** | Trang AS xử lý verification URI | POST có chủ ý và CSRF/session protection, không approval qua link |
| **Không xác thực user** | Verification UI/backend | Xác thực người dùng và kiểm tra phiên chính xác |
| **Scope escalation** | AS cấp token sau duyệt | Scope/resource/tenant phải theo grant và policy, không tự cấp |
| **Polling quá nhanh** | Token endpoint | `interval`, `slow_down`, rate limit/backoff |
| **Polling race** | Hai AS nodes xử lý cùng device code | Atomic transition và token issuance nhất quán |
| **Dùng mã sau khi hết hạn** | Lookup/approval/token endpoint | TTL, state machine và từ chối terminal state |
| **Client authentication bị bỏ qua** | Confidential client polling | Xác thực client theo registration, binding với device transaction |
| **Sai audience/token type** | Orders API | JWT/opaque validation, issuer, audience, expiry, profile |
| **Refresh replay** | AS/token endpoint sau cấp quyền | Refresh rotation/sender constraint, revocation và TTL |
| **Thông tin nội bộ bị lộ** | Log/response/analytics | Redaction và least-privilege observability |

### 15.2. Phân biệt code phishing với đánh cắp token

**Device-code phishing** có thể xảy ra **trước khi access token tồn tại trên thiết bị của người dùng**: attacker khởi tạo giao dịch của riêng họ, nạn nhân cấp quyền nhầm, AS hợp lệ phát token cho thiết bị attacker. Trong khi đó **token theft** là việc lấy một token đã được phát hành rồi sử dụng lại.

Cả hai dẫn đến quyền truy cập trái phép nhưng cách phòng vệ khác nhau:

- Phishing lúc ghép nối cần **consent có ý thức, kiểm tra thiết bị/ứng dụng, chống dụ nhập mã lạ**.
- Token theft cần **bảo vệ storage, token lifetime, sender constraint, revocation và giám sát reuse**.

Một hệ thống có DPoP/mTLS sau phát hành vẫn phải chống phishing ở bước cấp quyền. Nếu user chấp thuận chính yêu cầu của attacker, việc token ràng buộc với khóa trên thiết bị attacker có thể không tự giải quyết vấn đề.

### 15.3. Khi nào không nên dùng Device Authorization Grant?

Không phải mọi ứng dụng có giao diện nhỏ đều nên dùng device flow:

- Nếu client có thể sử dụng **system browser và redirect URI an toàn**, Authorization Code + PKCE thường là lựa chọn tự nhiên hơn.
- Nếu một thiết bị hoàn toàn không có cách hiển thị URL/mã hoặc truyền ngữ cảnh bảo mật rõ ràng, cần cân nhắc giao thức/kênh enrollment riêng có threat model.
- Với scope/ứng dụng nhạy cảm, AS có thể **không cho Device Grant** hoặc yêu cầu chứng thực/consent tăng cường.
- Với **machine-to-machine không có người dùng**, Client Credentials Grant có mô hình khác; không giả một user code để cấp quyền workload.
- Không dùng Device Grant như lối đi vòng MFA, phê duyệt của tổ chức hoặc ranh giới truy cập được quy định cho login thông thường.

### 15.4. Màn hình "Connected" có thể sai

Ví dụ không an toàn:

~~~text
TV hiển thị user_code.
Người dùng nhập mã trên trang web.
TV lập tức hiện "Kết nối thành công" vì phát hiện mã đã được nhập.
~~~

Sai ở chỗ **code entry chưa phải approval và chưa chắc đã được cấp access token**. TV chỉ nên báo kết nối thành công sau khi polling nhận **token response hợp lệ** từ AS, đã lưu credential an toàn và thực hiện xử lý trạng thái đúng contract.

### 15.5. Bảo vệ log và dữ liệu phân tích

Không ghi raw:

~~~text
device_code = <SECRET>
user_code = T8KQ-M7PL
verification_uri_complete = https://login.example.com/activate?user_code=...
Authorization: Bearer <ACCESS_TOKEN>
refresh_token = <SECRET>
Cookie: session=<SECRET>
~~~

Trong môi trường test, việc log user code mẫu có thể được kiểm soát theo fixture; production nên ưu tiên metadata không thể đổi thành credential.

Có thể ghi có kiểm soát:

~~~text
traceId
clientId
deviceTransactionId (định danh nội bộ không bí mật)
grantType=urn:ietf:params:oauth:grant-type:device_code
verificationOutcome=APPROVED|DENIED|EXPIRED
pollErrorCategory=AUTH_PENDING|SLOW_DOWN|EXPIRED|...
scopeNames / resourceIds nếu chính sách cho phép
createdAt, completedAt, policyVersion
~~~

Ngay cả account ID, device ID, scope hoặc IP có thể là dữ liệu cần bảo vệ. Cần giới hạn quyền truy cập và retention log, tránh lưu mã sau khi dùng.

## 16. Ma trận kiểm thử user code, URI, polling và cấp quyền

### 16.1. Device authorization endpoint

| Kịch bản | Kỳ vọng |
|---|---|
| Client được phép dùng Device Grant, scope hợp lệ | Cấp device_code + user_code + verification_uri + expires_in |
| `client_id` không được đăng ký hoặc không có quyền dùng grant | Từ chối theo chính sách/loại lỗi OAuth |
| Confidential client không xác thực đúng method | Từ chối, không cấp cặp mã |
| Client xin scope ngoài allowed scopes | Từ chối hoặc giới hạn theo policy; không cấp vượt quyền |
| Thiếu `verification_uri` trong response | Test contract thất bại; client không đủ thông tin bắt đầu |
| Không có `verification_uri_complete` | Client vẫn hiển thị URI và user code thủ công |
| User code trùng với mã đang active | AS không tạo giao dịch nhập nhằng |
| Device code ngắn/dễ đoán | Test/security review thất bại |
| Response không có `expires_in` | Test contract thất bại |
| Response không có `interval` | Client dùng mặc định 5 giây |
| Verification URI trỏ đến host không tin cậy/không HTTPS | Client/AS từ chối theo thiết kế bảo mật |

### 16.2. Verification URI và user code

| Kịch bản | Kỳ vọng |
|---|---|
| Alice nhập đúng user code còn hạn | AS hiển thị bước xác thực/consent, **không tự approve** |
| Mã không tồn tại | Thông báo an toàn, không tiết lộ thông tin giao dịch |
| Mã hết hạn | Từ chối; yêu cầu lấy mã mới trên TV |
| Mã đúng nhưng transaction đã DENIED/CONSUMED | Không cho approve lại |
| Mã bị đoán thử hàng loạt | Rate limiting/throttling và giám sát, tránh enumeration |
| Hai giao dịch active nhận cùng user code | Test fail; phải bảo đảm unique mapping |
| Mã nhập có dấu nối/khoảng trắng/viết thường | Chuẩn hóa đúng policy, không tạo collision mơ hồ |
| Người dùng chưa đăng nhập | Yêu cầu xác thực theo chính sách trước khi phê duyệt |
| Người dùng đăng nhập nhầm tài khoản | Hiển thị đúng tài khoản, không cấp quyền ngoài ý muốn |
| User mở verification_uri_complete có code sẵn | Không autoapprove; vẫn cần xác nhận rõ ràng |
| Truy cập verification_uri bằng HTTP GET | Không tự đổi transaction sang APPROVED |
| Client display name không đáng tin | Không cho mạo danh publisher/ứng dụng |
| Người dùng từ chối | Trạng thái DENIED, polling nhận access_denied |
| User cố approve sau khi hết TTL | Từ chối, không cấp token |

### 16.3. Token endpoint polling

| Kịch bản | Kỳ vọng |
|---|---|
| Device code đúng, trạng thái PENDING | `authorization_pending`, không có token |
| Client polling quá nhanh | `slow_down`; client tăng interval thêm 5 giây |
| AS bỏ `interval` | Client dùng khoảng mặc định 5 giây |
| User từ chối | `access_denied`; client dừng polling |
| Device transaction hết hạn | `expired_token`; client dừng và xin mã mới nếu cần |
| User approve đúng client, scope, device_code còn hạn | Có thể cấp access token theo grant |
| Device code của client A được trình từ client B | Từ chối, kiểm tra client binding |
| Device code không tồn tại/sai định dạng | Không cấp token, lỗi OAuth phù hợp |
| Client public chỉ gửi `client_id` | AS không coi client_id là secret; vẫn kiểm tra transaction |
| Confidential client không authenticates đúng | Từ chối token request |
| Device code được gửi lại sau SUCCESS | Không phát token lần hai ngoài policy |
| Hai token requests đồng thời sau approval | Tối đa một lần chuyển APPROVED → CONSUMED |
| Polling bị network timeout | Client backoff, không dồn request |
| Client nhận access token nhưng vẫn tiếp tục polling | Test fail, phải dừng polling |

### 16.4. Access token và resource authorization

| Kịch bản | Kỳ vọng |
|---|---|
| JWT access token đúng issuer, audience, time, scope | Chuyển sang kiểm tra quyền nghiệp vụ |
| JWT access token sai chữ ký hoặc sai issuer | Từ chối |
| JWT đúng chữ ký nhưng sai audience Orders API | Từ chối |
| Access token hết hạn hoặc opaque token inactive | Từ chối |
| ID token gửi vào Bearer header của Orders API | Từ chối sai mục đích |
| `user_code` hoặc `device_code` gửi như Bearer | Từ chối |
| Access token `orders:read` xin đơn hàng của Bob | Từ chối nếu Alice không có quyền cụ thể |
| Token được AS cấp scope rộng hơn grant/consent | Test phát hiện lỗi phát hành |
| Refresh token bị replay | AS xử lý rotation/sender constraint/revocation theo policy |
| Thu hồi device grant nhưng JWT offline còn hạn | Kiểm tra đúng policy revoke/TTL thực tế, không giả định tự vô hiệu ngay |

### 16.5. Kiểm thử người dùng và an toàn QR

- Quét QR xong, trang AS hiển thị mã/tên app/quyền và yêu cầu xác nhận rõ ràng.
- Dùng QR/link của attacker nhưng vào **AS thật** vẫn phải có cảnh báo và bước review quyền thiết bị.
- Nếu QR mở domain giả, trình duyệt/người dùng phải có cơ hội nhận biết khác biệt.
- Xóa mã khỏi URL trang AS sau khi đọc khi kiến trúc hỗ trợ, giảm rò qua log và scripts.
- Trang verification không gọi analytics bên thứ ba chứa user code hoặc dữ liệu tài khoản.
- Trang approval có CSRF/session protection; GET/preview không thay đổi trạng thái.
- Cùng một `verification_uri_complete` không thể được dùng để phê duyệt một giao dịch đã EXPIRED hoặc CONSUMED.
- Người dùng có thể hủy luồng và xác định chính xác thiết bị nào được liên kết sau khi thành công.

**Không dùng credential production thật khi kiểm thử rò rỉ URL hoặc log**. Test phải dùng fixture và dọn sạch state sau khi chạy.

## 17. Ứng cứu khi phát hiện lộ mã hoặc cấp quyền nhầm

Nếu tổ chức phát hiện người dùng đã nhập mã do attacker gửi, không nên chỉ xóa mã khỏi màn hình TV và kết luận an toàn. Cần đánh giá **grant/token đã được cấp**.

1. **Xác định transaction:** client registration, thời điểm tạo, user code identifier đã bảo vệ, account đã chấp thuận, scopes và audience đã cấp.
2. **Ngừng giao dịch còn mở:** hủy/đánh dấu từ chối hoặc hết hạn các device transactions nghi vấn, chặn mã dùng tiếp.
3. **Thu hồi grant/refresh token:** áp OAuth token revocation và session/device management theo khả năng AS.
4. **Đánh giá access token đã phát hành:** JWT offline có thể còn hạn tới `exp` nếu resource server không kiểm tra trạng thái bổ sung; cân nhắc denylist/introspection/session version theo policy.
5. **Xem nhật ký API:** điều tra hành động bất thường trên resource, không chỉ các lần đăng nhập.
6. **Xử lý nguồn phishing:** gỡ chiến dịch giả mạo, kiểm soát client registration/scope, cập nhật consent UI và cảnh báo người dùng.
7. **Rà soát log chứa mã:** request URL, QR, APM, support ticket, crash reports và quyền truy cập vào chúng.
8. **Bổ sung kiểm thử và giám sát:** mã bị đoán thử, approval bất thường, polling sớm, client không được phép, token reuse.

Không khẳng định mọi sự kiện nhập mã lạ chắc chắn dẫn đến chiếm tài khoản: phải xác định **có approval không, token đã được cấp không, phạm vi cấp quyền là gì và API đã bị gọi chưa**.

### 17.1. Khác biệt giữa thu hồi mã và thu hồi token

~~~text
Hủy user_code/device_code đang PENDING:
    -> Ngăn hoàn thành device transaction đó.

Thu hồi refresh token/grant sau khi APPROVED:
    -> Ngăn xin access token mới bằng grant liên quan.

Thu hồi hoặc chặn access token:
    -> Tùy JWT/opaque và chính sách resource server.

Điều tra API actions đã diễn ra:
    -> Không thể "thu hồi" dữ liệu đã bị đọc chỉ bằng vô hiệu hóa token.
~~~

Đó là lý do kiến trúc phải nối được **device transaction → authorization grant → token issuance → resource access** qua metadata/audit **không chứa raw credentials**, để ứng cứu có thể xác định phạm vi tác động.

## 18. Tình huống tự suy luận

### Tình huống A — Alice nhập mã nhưng TV chưa nhận token

Shop TV hiển thị `T8KQ-M7PL`. Alice nhập mã trên điện thoại, nhưng dừng lại ở màn hình "Shop TV muốn đọc đơn hàng" mà không chọn Chấp thuận. TV đang polling token endpoint.

**Câu hỏi:** TV có thể nhận access token chưa?

**Đáp án:** Chưa. Việc nhập mã chỉ xác định transaction. Nếu AS chưa có quyết định APPROVED hợp lệ, polling phải trả `authorization_pending` hoặc trạng thái tương ứng, không cấp token.

### Tình huống B — Link QR tự điền mã

Shop TV hiển thị QR từ `verification_uri_complete`. Alice quét và được đưa thẳng vào trang chi tiết yêu cầu.

**Câu hỏi:** Có thể tự chấp thuận vì QR chứa đúng user code không?

**Đáp án:** Không. Trang AS vẫn phải xác thực Alice theo chính sách và yêu cầu cô xem xét ứng dụng, quyền, thiết bị đang liên kết rồi chủ động chấp thuận. QR chỉ giảm thao tác nhập mã.

### Tình huống C — Người dùng nhận mã qua email lạ

Alice không đăng nhập TV nào, nhưng nhận email "Vào trang xác minh tài khoản chính thức và nhập mã ABCD-1234". URL đúng domain của AS.

**Câu hỏi:** URL chính thức đã đủ an toàn chưa?

**Đáp án:** Chưa. Đây có thể là **device-code phishing**: mã thuộc thiết bị attacker, nạn nhân bị dụ cấp quyền. Nếu Alice không chủ động bắt đầu kết nối trên thiết bị trước mặt, phải từ chối và không nhập/chấp thuận mã.

### Tình huống D — Hai TV dùng trùng user code

Do lỗi sinh mã, hai transaction đang PENDING của TV phòng khách và TV khách sạn cùng hiển thị `T8KQ-M7PL`.

**Câu hỏi:** AS có thể lấy transaction đầu tiên rồi cho tiếp tục không?

**Đáp án:** Không nên. User code phải định vị một yêu cầu đang hoạt động không nhập nhằng. AS cần uniqueness/atomic issuance và từ chối/khắc phục collision, không tùy tiện chọn thiết bị đầu hoặc cuối.

### Tình huống E — Polling mỗi 100 ms

AS trả `interval=5`, nhưng client cứ 100 ms gọi token endpoint vì user đang nóng lòng.

**Câu hỏi:** Kết quả mong đợi?

**Đáp án:** Client đang vi phạm interval. AS có thể trả `slow_down` và áp throttling. Client phải giữ khoảng tối thiểu, tăng thêm 5 giây sau `slow_down`, không spam request.

### Tình huống F — Không có interval

Device authorization response có `expires_in=900` nhưng không có `interval`.

**Câu hỏi:** TV được polling liên tục không?

**Đáp án:** Không. RFC 8628 yêu cầu dùng khoảng **mặc định 5 giây** khi trường `interval` vắng mặt.

### Tình huống G — Token của Orders API dùng ở Billing API

Alice đã chấp thuận scope `orders:read`. Shop TV nhận JWT access token có `aud=https://orders.example.com`, rồi gửi token đó đến Billing API.

**Câu hỏi:** Billing API có chấp nhận vì cùng issuer không?

**Đáp án:** Không. Billing API phải kiểm tra audience đúng chính nó; access token của Orders API không trở thành quyền Billing API chỉ nhờ chữ ký issuer hợp lệ.

### Tình huống H — Device code được dùng lại sau thành công

AS đã trả access token cho Shop TV sau khi phê duyệt. Một request khác dùng lại cùng device code.

**Câu hỏi:** AS nên phát thêm token mới không?

**Đáp án:** Không theo mô hình single-use. Device transaction phải chuyển CONSUMED sau lần đổi thành công. Nếu cần token mới, dùng refresh token được cấp theo chính sách hoặc luồng ủy quyền mới; không tái sử dụng device code.

### Tình huống I — Mã hết hạn nhưng trang vẫn đang mở

Alice mở verification URI trước khi code hết hạn, nhưng chờ quá lâu rồi mới nhấn Chấp thuận.

**Câu hỏi:** Thời điểm mở trang hay thời điểm quyết định quan trọng?

**Đáp án:** AS phải kiểm tra TTL/trạng thái **tại thời điểm quyết định**. Trang đã mở trước đó không được biến mã hết hạn thành hợp lệ. Yêu cầu TV tạo cặp mã mới.

### Tình huống J — Sai loại credential

Lập trình viên gửi `Authorization: Bearer T8KQ-M7PL` đến Orders API vì user code đã được Alice nhập.

**Câu hỏi:** API nên làm gì?

**Đáp án:** Từ chối. `user_code` chỉ để xác định yêu cầu trên trang AS, không phải access token. Chỉ token được AS phát hành sau approval và polling hợp lệ mới được trình đến API đúng audience.

### Tình huống K — Account đang đăng nhập không đúng

Alice mở verification URI nhưng điện thoại đang đăng nhập tài khoản công ty của Bob. Trang AS hiển thị tài khoản Bob, trong khi TV của Alice muốn dùng dữ liệu của Alice.

**Câu hỏi:** AS có nên tự chuyển thành Alice bằng mã TV không?

**Đáp án:** Không. User code không xác định chủ tài khoản. AS phải xác thực user thực tế, hiển thị rõ account đang cấp quyền, cho đổi account khi phù hợp và chỉ cấp grant với subject đã được xác minh.

### Tình huống L — Hai AS instances phát token từ một device code

Giao dịch được chấp thuận, hai poll requests gần như đồng thời tới hai node; mỗi node đọc trạng thái APPROVED từ cache riêng và đều cấp token.

**Câu hỏi:** Cần sửa gì?

**Đáp án:** Dùng transition APPROVED → CONSUMED nguyên tử, lưu trữ có consistency thích hợp, kiểm tra token issuance state trong transaction. Không chỉ thêm client-side delay vì server còn phải đúng khi có concurrency hoặc caller độc hại.

## 19. Checklist vận hành và tóm tắt

Trước khi đưa Device Authorization Grant vào production, kiểm tra:

1. **Grant registration:** client thực sự được phép dùng device grant, scopes/resources được giới hạn, public/confidential phân loại đúng.
2. **Device authorization endpoint:** HTTP POST qua HTTPS, trả đúng các trường RFC 8628 và không cấp access token trước approval.
3. **User code:** mã ngẫu nhiên, đủ entropy theo threat model, dễ nhập, không collision khi active, TTL phù hợp và rate limiting.
4. **Device code:** giá trị khó đoán, không hiển thị, không log, gắn đúng client và transaction, dùng một lần.
5. **Verification URI:** do AS tin cậy cung cấp, HTTPS, dễ gõ, không có open redirect hoặc script/tracker làm rò pairing code.
6. **Verification URI complete:** tùy chọn, dùng để QR/link tự điền code; **không bao giờ tự approve** và vẫn hiển thị đường nhập thủ công.
7. **Consent:** AS xác thực user, hiển thị client/quyền/account, hỏi rõ đây có phải thiết bị đang được user chủ động kết nối không.
8. **Phishing:** kiểm tra kịch bản user nhận mã do attacker gửi và truy cập **trang AS thật**; domain đúng một mình chưa đủ.
9. **State:** PENDING, APPROVED, DENIED, EXPIRED, CONSUMED được kiểm soát, không chuyển trái phép hoặc phát hai lần.
10. **Polling:** đúng grant type `urn:ietf:params:oauth:grant-type:device_code`; interval mặc định 5 giây nếu vắng, `slow_down` tăng thêm 5 giây, dừng khi kết thúc.
11. **Token response:** phát đúng client, subject, scope, audience, TTL; dùng TLS và header chống cache, không ghi token vào log.
12. **Resource server:** kiểm tra JWT/opaque token, issuer, audience, expiry, scope và quyền trên resource/tenant/action.
13. **Refresh/lifecycle:** refresh token nếu được cấp có replay protection phù hợp, TTL và revocation; không dùng user code để refresh.
14. **Observability:** lưu event/transaction ID có kiểm soát, không ghi raw user code, device code, complete URI có mã hoặc access/refresh token.
15. **Incident response:** có thể thu hồi grant/device session, xem xét access token còn hạn và điều tra hành động API bất thường.

### Tóm tắt bằng một sơ đồ ngắn

~~~text
Shop TV xin device authorization
    |
    +--> device_code: giữ ở TV để polling token endpoint
    |
    +--> user_code:   hiển thị cho Alice
    |
    +--> verification_uri: trang AS Alice mở trên điện thoại
                        |
                        v
               Alice xác thực và kiểm tra client/quyền
                        |
                 +------+------+
                 |             |
             Từ chối      Chấp thuận
                 |             |
           access_denied   APPROVED
                               |
                         TV polling
                               |
                         token endpoint
                               |
                    Access token đúng audience
                               |
                           Orders API
                    Kiểm tra token + resource
~~~

**Kết luận:** `user_code` giúp một người dùng nhập hoặc xác minh **đúng yêu cầu ghép nối** từ thiết bị nhập liệu hạn chế; `verification_uri` đưa người dùng tới **Authorization Server đáng tin** để xác thực và xem xét quyền. `verification_uri_complete` có thể giảm thao tác bằng QR nhưng không thay sự chấp thuận có ý thức. `device_code` mới là giá trị thiết bị dùng để polling token endpoint, và access token chỉ được phát khi AS xác minh **client, grant, mã, TTL, trạng thái, quyết định user và policy**. Muốn hệ thống an toàn cần bảo vệ **cả UX chống phishing lẫn backend chống đoán mã, polling sai, replay và cấp quyền vượt phạm vi**.

## Tài liệu tham khảo

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): đặc tả chính cho device authorization endpoint, user code, verification URI, device code, token polling và an toàn giao thức.
- [RFC 8628 §3.2 — Device Authorization Response](https://www.rfc-editor.org/rfc/rfc8628#section-3.2): các trường bắt buộc/tùy chọn `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in` và `interval`.
- [RFC 8628 §3.3 — User Interaction](https://www.rfc-editor.org/rfc/rfc8628#section-3.3): cách hiển thị user code, verification URI, QR và trải nghiệm người dùng.
- [RFC 8628 §3.5 — Token Response](https://www.rfc-editor.org/rfc/rfc8628#section-3.5): polling, `authorization_pending`, `slow_down`, `access_denied` và `expired_token`.
- [RFC 8628 §5 — Security Considerations](https://www.rfc-editor.org/rfc/rfc8628#section-5): brute force user code, phishing, bảo vệ thiết bị và các mối đe dọa của device flow.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth client, grant, scope, token endpoint, access/refresh token và error responses.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): chống token leakage, replay và giới hạn tin cậy OAuth.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata của issuer/endpoint đáng tin khi discovery được hỗ trợ.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sử dụng Authorization Bearer và lỗi resource server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token với issuer, audience và scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token và trạng thái active.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token/grant khi phát hiện lạm dụng.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token khi kiến trúc hỗ trợ.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt ID token với access token trong các profile OIDC.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): triển khai AS, OAuth2 device authorization/verification theo phiên bản hỗ trợ.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác minh JWT/opaque access token tại API.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): thực hành bảo vệ luồng OAuth, client, token và authorization.
