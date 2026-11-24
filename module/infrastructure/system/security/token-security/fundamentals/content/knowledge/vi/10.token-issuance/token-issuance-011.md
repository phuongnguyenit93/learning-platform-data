# Giới hạn tốc độ token issuance

Một Authorization Server (AS) có thể kiểm mật khẩu, xác thực client, đối chiếu authorization code và ký JWT đúng chuẩn nhưng vẫn gặp sự cố nếu một client gửi **hàng nghìn yêu cầu cấp token mỗi giây**. Kẻ tấn công có thể tận dụng khả năng phát hành token để làm cạn tài nguyên, thử đoán thông tin xác thực, lợi dụng refresh token bị lộ hoặc khiến các client hợp pháp không thể đăng nhập. **Giới hạn tốc độ token issuance (token issuance rate limiting)** là kiểm soát số lượng và nhịp độ các yêu cầu liên quan đến việc cấp token, áp dụng theo chính sách và nhiều chiều nhận dạng.

Điểm cốt lõi: **rate limiting không thay thế xác thực, phân quyền hay kiểm tra token**. Hạn mức không làm cho một JWT trở nên an toàn nếu thiếu kiểm `iss`, `aud`, `exp` và chữ ký; cũng không ngăn hoàn toàn việc phát lại bearer token đã bị đánh cắp. Nó giảm khả năng lạm dụng **quy trình phát hành token**, bổ sung cho các bảo vệ grant, client, phiên người dùng và vòng đời token.

Trong chương **Token issuance** của module **Security Token Security Fundamentals**, bài này giải thích cách đặt giới hạn tại các điểm cấp token của OAuth 2.0/OIDC, phân biệt JWT/opaque access token với refresh token, thiết kế quota nhiều lớp, xử lý HTTP/OAuth error và vận hành rate limiter trong môi trường nhiều instance.

## 1. Vì sao phải giới hạn tốc độ cấp token?

Giả sử hệ thống có ba client:

- **Web App** dùng Authorization Code + PKCE để đăng nhập người dùng và gọi API.
- **Billing Worker** dùng `client_credentials` để gọi API nội bộ.
- **Mobile App** sử dụng refresh token để duy trì phiên mà không yêu cầu đăng nhập lại ở mỗi lần access token hết hạn.

Trong điều kiện bình thường, tất cả đều cần nhận token. Nhưng khi một script liên tục xin token hoặc một ứng dụng có lỗi retry vô hạn, AS có thể gặp các rủi ro:

| Rủi ro | Ví dụ | Tại sao liên quan đến issuance |
|---|---|---|
| **Cạn tài nguyên** | Client hợp lệ hoặc bot gọi `/token` liên tục | AS phải xác thực, tra grant/session, đọc dữ liệu và đôi khi ký JWT qua HSM/KMS |
| **Đoán thông tin xác thực** | Thử nhiều client secret hoặc lạm dụng luồng đăng nhập | Gây brute force/password spraying ở các điểm liên quan xác thực |
| **Lạm dụng refresh token** | Một token bị đánh cắp bị dùng liên tục để đổi access token | Tăng số lần thử sử dụng bí mật và áp lực lên kho grant/token |
| **Lỗi client tạo bão retry** | Sau lỗi mạng, hàng nghìn pod đồng thời thử lại | Retry storm, thậm chí khi không có kẻ tấn công |
| **Bất công tài nguyên** | Một tenant lớn chiếm toàn bộ năng lực AS | Client/tenant khác bị tăng độ trễ hoặc không được phục vụ |
| **Phát hành vượt chính sách** | Service xin hàng loạt token có scope rộng | Tăng bề mặt bị đánh cắp nếu cấp phát không được giới hạn hợp lý |
| **Làm nhiễu giám sát** | Bot tạo nhiều yêu cầu thất bại | Khó phân biệt sự cố thật với tấn công |

Hai nhóm mục tiêu nên được theo dõi riêng:

1. **Bảo vệ khả năng sẵn sàng (availability):** chặn lưu lượng quá mức trước những bước tốn chi phí, phân chia năng lực công bằng.
2. **Giảm lạm dụng bảo mật:** hạn chế thử sai credential/grant, quan sát mẫu hành vi đáng ngờ và bổ sung chính sách khóa/step-up khi cần.

Một ngưỡng cố định như “100 token/phút cho tất cả” thường **không đủ**. Mỗi grant, loại client, tenant và profile sử dụng có đặc điểm khác nhau. Các giá trị minh họa trong bài **không phải ngưỡng do OAuth quy định**.

## 2. Phải giới hạn ở đâu trong các luồng OAuth 2.0/OIDC?

Không phải mọi yêu cầu trong OAuth đều là yêu cầu **phát hành token**. Phân biệt vị trí kiểm soát giúp tránh giới hạn sai đối tượng.

| Điểm vào hoặc hoạt động | Token được cấp trực tiếp? | Nguy cơ/kiểm soát cần ưu tiên |
|---|---|---|
| **Authorization endpoint** (`/authorize`) | Thường bắt đầu luồng xin authorization code; chưa nhất thiết cấp access token | Tốc độ khởi tạo flow, consent/login spam, kiểm `state`, `redirect_uri`, PKCE, chống CSRF |
| **Trang đăng nhập/MFA/recovery** | Thường không trực tiếp cấp OAuth access token | Giới hạn thử mật khẩu/OTP, chống credential stuffing, bảo vệ người dùng tránh bị khóa hàng loạt |
| **Token endpoint** (`/token`) | Có: đổi code, refresh token, client credential, device code hoặc grant được hỗ trợ | Giới hạn theo client/grant/nguồn, kiểm grant một lần và quyền trước khi cấp |
| **Device authorization endpoint** | Thường cấp `device_code`/`user_code` chứ chưa cấp access token | Giới hạn tạo thiết bị, chống quét mã và lạm dụng QR/user code |
| **Device flow polling tại token endpoint** | Cấp token khi người dùng hoàn thành ủy quyền | Tuân thủ `interval`, `authorization_pending` và `slow_down` |
| **Token exchange endpoint / grant** | Có thể cấp token downstream mới | Giới hạn theo client, subject/actor, resource/audience và delegation |
| **Token refresh** | Thường cấp access token mới, đôi khi refresh token mới | Chống refresh storm, bảo đảm rotation/kiểm reuse an toàn |
| **Introspection endpoint** | Không cấp access token mới | Rate limit **riêng** để bảo vệ tra cứu token; không gộp bừa với quota phát hành |
| **Revocation endpoint** | Không cấp access token mới | Kiểm client/quyền và giới hạn lạm dụng; không cản thu hồi hợp lệ theo cách gây nguy hiểm |
| **JWKS endpoint** | Công bố khóa xác minh, không phát hành token | Cache và rate limit riêng, tránh làm resource server mất khả năng kiểm chữ ký |

Điểm quan trọng với **JWT và opaque token**: cả hai có thể được phát hành bởi token endpoint, nên quota theo yêu cầu/token **không nên phụ thuộc vào việc token có parse được tại client hay không**. Ký JWT có thể tốn CPU/HSM, còn cấp opaque token có thể tốn thao tác ghi vào kho trạng thái. Cần đo chi phí thực của hệ thống.

### Luồng cấp token với hai lớp giới hạn

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant G as Gateway / Edge
    participant AS as Authorization Server
    participant L as Shared Limiter
    participant DB as Grant & Token Store
    C->>G: POST /token (grant hợp lệ hoặc không)
    G->>G: Kiểm kích thước, kết nối, hạn mức thô
    alt Vượt hạn mức edge
        G-->>C: 429 + Retry-After
    else Qua được hạn mức edge
        G->>AS: Chuyển request
        AS->>L: Kiểm/đặt trước quota grant và client
        alt Vượt quota
            L-->>AS: DENY + retryAfter
            AS-->>C: 429 (không cấp token)
        else Trong quota
            L-->>AS: ALLOW / reservation
            AS->>AS: Xác thực client, kiểm grant và chính sách
            AS->>DB: Tiêu thụ grant/rotate refresh atomically nếu hợp lệ
            DB-->>AS: Trạng thái hợp lệ
            AS->>AS: Cấp token đúng aud/scope/thời hạn
            AS-->>C: Token response có no-store
        end
    end
~~~

Sơ đồ chỉ nêu **các ranh giới trách nhiệm**; trong hệ thống thật, bước xác thực client và mức limiter chuyên biệt có thể sắp xếp khác để tránh tin một `client_id` do attacker tự khai. Điều bất biến là **không cấp token nếu chưa đủ điều kiện**, và phải kiểm quota/tiêu thụ grant theo trình tự có thể xử lý đồng thời an toàn.

## 3. Đếm cái gì: request, lần thử xác thực hay token được cấp?

Nếu chỉ giới hạn “số token cấp thành công”, attacker có thể gửi vô hạn request sai mà không chạm quota. Nếu chỉ giới hạn tất cả request như nhau, một client bị lỗi mạng có thể bị khóa lâu dù chưa nhận token nào.

| Chỉ số | Cách đếm | Dùng để bảo vệ |
|---|---|---|
| **Request attempts** | Mọi request đến điểm vào, kể cả bị từ chối sớm | Chống flood, bảo vệ CPU/network |
| **Failed authentication attempts** | Lần xác thực client hoặc người dùng thất bại, theo ngữ cảnh | Chống đoán client secret/mật khẩu/OTP; phát hiện rủi ro |
| **Grant validation failures** | Code sai/đã dùng, refresh token bị từ chối, device code sai | Nhận diện dò grant và lỗi tích hợp |
| **Successful token responses** | Lần cấp token thành công, gồm access token và có thể refresh token | Quản trị năng lực issuer, chi phí ký/ghi trạng thái |
| **Concurrent operations** | Số phép xác thực/ký/ghi token đang thực hiện cùng lúc | Chống cạn connection pool/HSM/KMS/DB |
| **Bytes/compute cost** | Kích thước payload, chi phí introspection/KMS/DB theo flow | Điều tiết đường xử lý đắt tiền |

Một hệ thống thực tế thường dùng **ít nhất hai lớp**:

- Hạn mức **request thô** để từ chối flood trước khi xử lý tốn kém.
- Hạn mức **đã định danh** theo client, subject/tenant và grant nhằm chia sẻ năng lực công bằng.

Có thể bổ sung quota **token cấp thành công** cho client hoặc tenant, nhưng quota thành công **không thay thế** hạn mức lần thử thất bại. Các bộ đếm cần độc lập để hệ thống có thể chẩn đoán “đột biến người dùng thật” khác “brute force”.

## 4. Chọn khóa rate limiting thế nào để vừa công bằng vừa chống lạm dụng?

Rate limit theo **IP duy nhất** thường gây khó khăn: nhiều người dùng sau NAT hoặc proxy cùng địa chỉ IP sẽ bị khóa lẫn nhau; mạng bot có nhiều IP lại né được ngưỡng. Rate limit theo **`client_id` duy nhất** cũng rủi ro: attacker có thể gửi một client ID của nạn nhân để tiêu quota của nạn nhân nếu limiter tin giá trị chưa xác thực.

### Các chiều có thể dùng

| Chiều khóa | Ví dụ | Điểm mạnh | Hạn chế |
|---|---|---|---|
| **Nguồn kết nối đáng tin** | IP mà edge nhìn thấy, mạng/ASN theo chính sách | Chặn traffic thô ngay ở edge | NAT, botnet, sai nguồn nếu tin `X-Forwarded-For` không an toàn |
| **Client đã xác thực** | `client_id` được AS xác minh | Công bằng giữa client hợp lệ, đặc biệt `client_credentials` | Chỉ dùng khi đã xác thực hoặc có lớp chống spoofing |
| **Người dùng đã xác thực** | `issuer + subject`/session nội bộ | Giới hạn lạm dụng per-user | Không có ở các request chưa đăng nhập |
| **Tenant hoặc tổ chức** | `tenant-A` từ nguồn quyền tin cậy | Giới hạn noisy tenant, đảm bảo công bằng | Một tenant lớn có lưu lượng hợp pháp cao |
| **Grant type** | `authorization_code`, `refresh_token`, `client_credentials` | Chia quota theo rủi ro và tần suất hợp pháp | Grant type do request khai báo, phải validate shape |
| **Resource/audience được phép** | `invoice-api`, `payments-api` theo AS | Điều tiết tài nguyên đích và loại token đắt tiền | Không tin `aud` do client tự khai ngoài chính sách |
| **Điểm rủi ro/thiết bị** | Session, thiết bị có bằng chứng đáng tin | Điều chỉnh khi có hành vi bất thường | Fingerprint thiết bị có thể thiếu ổn định và ảnh hưởng quyền riêng tư |

**Phương pháp ghép tầng:**

~~~text
1. Edge:        limit by trusted network source + endpoint
2. AS, trước auth: limit malformed/unauthenticated attempts by source
3. AS, sau auth:  limit by verified client_id + grant_type
4. AS, theo flow: limit by verified user/session/tenant/resource
5. Hệ thống:    global quota + concurrency guard cho DB/HSM/KMS
~~~

Các bước này cần chịu được **key cardinality attack**: attacker tạo vô hạn client ID ngẫu nhiên khiến bộ nhớ Redis/memory đầy vì mỗi ID sinh một bucket. Đặt giới hạn số lượng key, TTL, kiểm dạng request sớm và chỉ cấp bucket định danh đắt tiền cho identity đã xác minh.

### Khóa kiểm trước và sau xác thực là hai tập khác nhau

Trước xác thực client, `client_id` hoặc email trong request **chưa đáng tin**. Có thể dùng chúng làm *tín hiệu phòng thủ* kết hợp IP, nhưng **không** được coi là danh tính đã xác minh; cần tránh “một attacker gọi tên client của người khác để khóa client thật”. Sau khi AS xác thực, có thể dùng khóa ổn định như `verified_client_id + grant_type` để quản lý quota riêng.

Nếu cần giới hạn theo tài khoản trong bước đăng nhập, tránh thiết kế chỉ khóa tài khoản sau N lần sai vì attacker có thể tạo **denial-of-service theo tài khoản**. Thường kết hợp giảm nhịp theo nguồn, kiểm tín hiệu rủi ro, cảnh báo, xác thực tăng cường hoặc bảo vệ ngoài băng khi cần.

## 5. Chọn thuật toán hạn mức: cố định, trượt, token bucket và concurrency

Thuật toán không quyết định chính sách kinh doanh, nhưng ảnh hưởng mạnh đến việc client có bị chặn nhầm và limiter có chống được burst hay không.

| Thuật toán | Nguyên lý | Ưu điểm | Cần lưu ý |
|---|---|---|---|
| **Fixed window** | Đếm request trong mỗi khoảng thời gian cố định | Dễ triển khai | Có thể có burst gấp đôi quanh ranh giới cửa sổ |
| **Sliding window** | Đếm trong cửa sổ di động hoặc xấp xỉ | Giảm burst mép cửa sổ | Tốn bộ nhớ/compute hơn tùy cách hiện thực |
| **Token bucket** | Bucket có `capacity`, bổ sung token theo `refill rate`; mỗi request tiêu đơn vị | Cho phép burst ngắn có kiểm soát và tốc độ trung bình | Cần thao tác cập nhật nguyên tử giữa nhiều instance |
| **Leaky bucket / GCRA** | Điều tiết nhịp yêu cầu theo thời gian | Làm mượt lưu lượng và kiểm nhịp | Khả năng cho burst phụ thuộc tham số |
| **Concurrency limiter** | Giới hạn số xử lý đang hoạt động | Bảo vệ connection pool, KMS, DB khi độ trễ tăng | Không tự giới hạn tổng request trong một khoảng dài |

### Ví dụ token bucket cho một client

Giả định **chỉ để minh họa**: một client đã xác thực có bucket sức chứa **12** và được thêm **0,2 token/giây** (trung bình 12 request/phút). Mỗi request có chi phí 1 token:

~~~text
capacity = 12
refillRate = 0.2 token / second

onRequest(now):
    elapsed = max(0, now - bucket.lastUpdated)
    bucket.tokens = min(12, bucket.tokens + elapsed * 0.2)
    bucket.lastUpdated = now

    if bucket.tokens < 1:
        return DENY(retryAfter = ceil((1 - bucket.tokens) / 0.2))

    bucket.tokens -= 1
    return ALLOW
~~~

Ở thời điểm bucket đầy, tối đa 12 request có thể đi qua ngay; sau đó nhịp bổ sung quyết định khi nào được nhận yêu cầu tiếp. **Không chọn con số này làm mặc định sản xuất**: một web client phục vụ nhiều người dùng hoặc máy chủ M2M có thể cần khả năng cấp phát cao hơn nhiều.

Đo lường `granted`/`denied` và p95/p99 latency theo **loại grant**; đặt capacity/burst/rate theo SLO, năng lực hệ thống và lưu lượng thực, thay vì chỉ nhìn tổng request.

## 6. Chính sách riêng cho các grant và luồng đặc thù

### Authorization Code + PKCE

Trong Authorization Code Flow, mã `code` thường **ngắn hạn và chỉ dùng một lần**. Rate limiter tại `/token` giảm brute force và flood, nhưng không được thay thế:

- Liên kết authorization code với client, redirect URI và điều kiện PKCE theo giao thức.
- Kiểm code chưa hết hạn và chưa được dùng; **tiêu thụ atomically**.
- Không tái cấp token bằng cách chấp nhận lại code đã dùng chỉ vì client gặp lỗi mạng.

Nếu request bị từ chối do throttle **trước khi** code được xác nhận/tiêu thụ, client có thể đợi rồi thử lại **khi code còn hiệu lực**. Nếu AS đã cấp token và tiêu thụ code nhưng response bị mất, việc retry bằng cùng code phải tuân thủ nguyên tắc **code một lần**; ứng dụng có thể cần khởi tạo authorization flow mới. **Không dùng retry “bất chấp” làm cơ chế khôi phục.**

### Refresh token grant và rotation

Refresh token thường tồn tại lâu hơn access token và có khả năng được dùng để xin token mới theo grant hiện hành. Những điểm cần kiểm:

1. Xác thực client và ràng buộc refresh token với client/grant theo hợp đồng.
2. Kiểm hiệu lực, thu hồi, expiry, device/session nếu có.
3. Không tự tăng scope/audience vượt grant đã cho phép.
4. Nếu dùng **refresh token rotation**, đánh dấu token cũ đã dùng và phát hành token kế tiếp bằng thao tác nhất quán, chống phát lại.
5. Kiểm các request đồng thời hoặc retry chậm, tránh nhận nhầm tình huống race hợp lệ thành hành vi đánh cắp; nhưng không được bỏ cơ chế phát hiện reuse.

**Ví dụ:** Hai tab cùng dùng refresh token R1. Tab A đổi R1 thành R2; tab B gần như đồng thời gửi R1. Nếu AS không xử lý atomically, có thể tạo hai nhánh refresh token hợp lệ, làm yếu rotation. Nếu AS phát hiện R1 được dùng lại, cần chính sách phản ứng phù hợp như điều tra/thu hồi token family; cũng nên có thiết kế client **single-flight refresh** để tránh tự gây race.

Rate limiting giảm tần suất refresh storm, **không** thay thế rotation, binding, expiry hoặc replay detection.

### Client Credentials

Client dùng `client_credentials` thường xin token đại diện cho **service**, không nhất thiết có người dùng cuối. Quota cần tính đến:

- Mỗi client đã xác thực và ứng dụng workload; tách quyền/ưu tiên giữa công việc batch và online.
- Caching access token ở client tới khi gần hết hạn, **không xin token mới cho mỗi API call**.
- Giới hạn ký JWT hoặc ghi opaque token, đặt concurrency guard khi AS/HSM bị quá tải.
- Không coi `client_id` tự khai là đã xác thực; client authentication phải đúng phương thức đã đăng ký.

### Device Authorization Grant (RFC 8628)

Device Flow cần **polling token endpoint** trong lúc người dùng xác nhận trên thiết bị khác. Đây là loại request lặp **được giao thức dự kiến**, không nên xử lý y hệt flood chung:

- Client tuân thủ tham số `interval` được trả về; nếu không có, RFC 8628 quy định giá trị mặc định.
- Khi chưa được chấp thuận, AS trả OAuth error **`authorization_pending`**; client tiếp tục sau khoảng chờ.
- Khi AS trả **`slow_down`**, client phải tăng khoảng chờ theo quy tắc RFC 8628 (tăng 5 giây cho yêu cầu hiện tại và các yêu cầu tiếp theo của phiên polling).
- Khi hết hạn `device_code` hoặc người dùng từ chối, client phải dừng theo thông tin lỗi tương ứng.

**Đừng thay thế máy móc `authorization_pending` hoặc `slow_down` bằng mọi trường hợp `429`** mà làm client Device Flow không hiểu trạng thái; có thể bổ sung bảo vệ hạ tầng nếu quá tải, nhưng phải tôn trọng đặc tả của grant.

### Token Exchange và đổi audience

Với OAuth 2.0 Token Exchange (RFC 8693), một service có thể xin token dành cho resource server khác. Ngoài quota chung, cần xét:

- Identity của client/actor đã xác minh.
- Subject token và actor token nếu có; tính hợp lệ và quyền delegation.
- Số request theo resource/audience được phép, tránh một client đánh vào mọi API.
- **Downscoping**: không tự tăng scope hoặc audience ngoài chính sách của AS.

Đối với access token mới — JWT hay opaque — resource server đích vẫn phải kiểm `aud` và scope/quyền đối tượng; quota token exchange không chứng minh quyền của token sau đó.

## 7. Thực thi limiter an toàn trong kiến trúc phân tán

Nếu AS có 20 instance mà mỗi instance giữ bộ đếm riêng “12 request/phút/client”, một client có thể thực tế dùng tới khoảng 240 request/phút khi load balancer phân đều. Muốn một quota **toàn cụm**, cần lưu/đồng bộ trạng thái phù hợp.

~~~mermaid
flowchart LR
    C["Clients"] --> G["Gateway / WAF"]
    G --> A1["AS instance 1"]
    G --> A2["AS instance 2"]
    G --> A3["AS instance 3"]
    A1 --> L[("Distributed limiter")]
    A2 --> L
    A3 --> L
    A1 --> D[("Grants / tokens DB")]
    A2 --> D
    A3 --> D
~~~

### Một lần kiểm và cập nhật quota phải nguyên tử

Với Redis hoặc kho đồng bộ tương đương, phép “đọc số token → tính refill → trừ → lưu lại” cần được thực hiện **atomically** (ví dụ script Lua/transaction thích hợp). Nếu hai instance cùng đọc bucket còn 1 token rồi cả hai cho phép, quota đã bị vượt.

Một giao diện phía AS có thể là:

~~~text
interface IssuanceLimiter:
    reserve(
        key = trustedClientOrSourceKey,
        grant = normalizedGrantType,
        cost = requestCost,
        timestamp = trustedServerClock
    ) -> ALLOW(reservationId) | DENY(retryAfterSeconds)
~~~

Đây là **mã giả về contract**, không phải thư viện có sẵn. Nếu hệ thống dùng nhiều data center/region, cần quyết định quota có **toàn cầu chính xác** hay chấp nhận **giới hạn xấp xỉ theo region**. Phân tán nhiều vùng có thể chọn quota cục bộ cộng quota hệ thống để giảm latency, nhưng phải hiểu mức vượt có thể có trong khoảng đồng bộ.

### Limiter hỏng thì fail-open hay fail-closed?

Không có một đáp án cho mọi đường vào:

| Tình huống | Phương án cân nhắc | Rủi ro cần hiểu |
|---|---|---|
| Lưu lượng internet không xác thực tăng đột biến | Ưu tiên chặn/phòng vệ ở edge, quota dự phòng | Fail-open vô điều kiện dễ làm sập AS |
| Service nội bộ thiết yếu bị mất kết nối limiter | Có thể dùng quota dự phòng cục bộ rất hạn chế và cảnh báo | Fail-closed toàn bộ có thể làm gián đoạn nghiệp vụ quan trọng |
| Yêu cầu grant/refresh token có dấu hiệu tấn công | Từ chối hoặc yêu cầu bước bảo vệ mạnh hơn theo policy | Không bỏ kiểm grant/token chỉ vì limiter lỗi |
| Limiter mất trạng thái phân tán | Hạn mức cục bộ tạm thời, circuit breaker, giảm tải có kiểm soát | Dữ liệu quota có thể không chính xác |

**Dù lựa chọn fallback nào, không được fail-open đối với xác thực client, xác minh grant, PKCE, rotation hay phân quyền.** Fail-open ở đây chỉ nói về **quota phụ trợ**, không phải bỏ điều kiện bảo mật cốt lõi.

### Đếm quota và tiêu thụ grant: tránh lỗi thứ tự

Một thiết kế an toàn cần xác định:

1. Trước bước kiểm tra nặng, áp dụng **cheap admission control**.
2. Sau khi xác thực đủ ngữ cảnh, xét **quota client/tenant/grant chính xác hơn**.
3. Trước phát hành, kiểm và **tiêu thụ grant/rotate refresh token atomically**; chống hai request đổi cùng một grant.
4. Tạo response token một lần theo kết quả giao dịch và không cấp token nếu grant đã dùng hoặc bị thu hồi.
5. Ghi metric/phí quota theo semantics đã thiết kế, có logic xử lý reservation thất bại mà **không biến code/refresh token thành dùng nhiều lần**.

Không nên **tiêu thụ authorization code rồi mới quyết định chặn do quota**: client có thể bị mất code mà chưa bao giờ nhận token. Ngược lại, cũng không nên **ký token rồi chờ quota và sau đó rollback theo cách không thu hồi được token đã phát hành**. Thiết kế reservation, grant transaction và response phải nhất quán, đặc biệt khi DB, limiter và AS ở nhiều hệ thống khác nhau.

## 8. Minh họa Java: PEP hạn mức trước logic phát hành

Ví dụ sau biểu diễn một **use case Java 17/Spring** với interface chính sách nội bộ. Nó không phải ứng dụng chạy độc lập và không thay thế token endpoint được cung cấp bởi Authorization Server framework; mục tiêu là làm rõ vị trí kiểm tra.

~~~java
public interface IssuanceRateLimiter {
    LimitDecision check(String trustedKey, String grantType);
}

public record LimitDecision(
    boolean allowed,
    long retryAfterSeconds
) {}

public final class TokenRequestHandler {
    private final IssuanceRateLimiter limiter;
    private final ClientAuthenticator authenticator;
    private final GrantValidator grantValidator;
    private final TokenIssuer issuer;

    public TokenResponse handle(TokenRequest request, TrustedNetworkSource source) {
        // Lớp admission chống flood thô trước các phép kiểm tốn kém.
        LimitDecision preAuth = limiter.check(
            "edge:" + source.stableKey(), request.normalizedGrantType());
        if (!preAuth.allowed()) {
            throw new TooManyRequestsException(preAuth.retryAfterSeconds());
        }

        VerifiedClient client = authenticator.authenticate(request);

        // Không lấy client_id thô từ request làm identity tin cậy.
        LimitDecision clientQuota = limiter.check(
            "client:" + client.id(), request.normalizedGrantType());
        if (!clientQuota.allowed()) {
            throw new TooManyRequestsException(clientQuota.retryAfterSeconds());
        }

        // Gồm kiểm PKCE/code một lần, refresh rotation, audience,
        // scope/grant và chính sách của từng loại grant.
        VerifiedGrant grant = grantValidator.validateAndConsumeAtomically(
            client, request);

        return issuer.issueWithinVerifiedGrant(client, grant);
    }
}
~~~

Các kiểu `TrustedNetworkSource`, `VerifiedClient`, `VerifiedGrant`, `TokenIssuer` và exception ở đây là **tên minh họa do ứng dụng thiết kế**. Ở production, cần chiến lược phân tán **atomic limiter**, kiểm grant cùng transaction, thời gian chờ, chống trùng, thứ tự quota và code HTTP phù hợp. Đặc biệt, bước `validateAndConsumeAtomically` và `issueWithinVerifiedGrant` phải phối hợp được khi ký token hoặc ghi kho lưu trạng thái bị lỗi; chỉ mô tả trong hai lệnh không bảo đảm giao dịch phân tán thực sự nguyên tử.

Không viết một interceptor “rate-limit theo client_id trong JSON” rồi coi đó là bảo mật vì attacker có thể chọn tên client bất kỳ. Trong Spring, nếu chèn filter vào chain, cần bảo đảm nó **không bỏ lọt token endpoint** thực tế do Authorization Server framework quản lý.

## 9. Khi vượt hạn mức: HTTP 429, OAuth errors và retry

### HTTP 429 Too Many Requests

Đối với throttling HTTP thông thường, có thể trả **429 Too Many Requests** kèm **`Retry-After`** để hướng dẫn client khi nào có thể thử lại:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Cache-Control: no-store
Content-Type: application/json

{"error":"rate_limited"}
~~~

`Retry-After: 5` ở đây là **5 giây minh họa**, không phải giá trị mặc định chuẩn. Client có thể sử dụng exponential backoff, jitter và giới hạn số lần thử; phải tôn trọng `Retry-After` nếu server cung cấp và không flood lại ngay lập tức.

Với token endpoint OAuth, **đừng trộn** throttling với lỗi grant:

| Điều kiện | Phản hồi thường gặp | Ý nghĩa |
|---|---|---|
| **Chạm hạn mức phát hành HTTP** | `429` và có thể `Retry-After` | Thử lại theo chính sách; chưa kết luận grant sai |
| **Authorization code/refresh token sai, đã hết hạn hoặc không hợp lệ** | OAuth `invalid_grant`, thường HTTP `400` | Grant bị từ chối; không được lặp vô hạn |
| **Client authentication sai** | `invalid_client`; trong ngữ cảnh thích hợp có thể HTTP `401` | Client không được xác thực; throttling không thay validation |
| **Client không được dùng grant** | `unauthorized_client` (theo OAuth error semantics) | Chính sách grant/đăng ký client |
| **Device Flow chưa được người dùng duyệt** | `authorization_pending` | Tiếp tục polling theo interval |
| **Device Flow poll quá nhanh** | `slow_down` | Tăng interval đúng RFC 8628 |
| **Hạ tầng quá tải không chỉ do một client** | `503 Service Unavailable` và backoff phù hợp trong một số thiết kế | Vấn đề khả dụng chung; không nhất thiết là quota cá nhân |

Với OAuth, thông điệp lỗi phải được xây dựng theo **endpoint, grant và profile tương ứng**; không nhất thiết mọi AS đều trả JSON `{"error":"rate_limited"}` theo cùng một extension. Nếu dùng RFC 6749 token error response, cần không tạo ra một error code tùy biến rồi giả vờ đó là error code chuẩn của OAuth.

**Đừng cung cấp chi tiết có thể hỗ trợ dò tài khoản/client**, ví dụ tiết lộ chính xác tài khoản nào tồn tại, còn bao nhiêu lần đoán mật khẩu hoặc client nào đang hoạt động. Có thể công bố quota cho client hợp pháp qua kênh quản trị riêng và thống nhất behavior lỗi ở API công khai.

### Client retry mà không tạo bão request

- **429 hoặc 503:** tôn trọng `Retry-After` khi có, dùng backoff tăng dần và jitter; giới hạn retry budget, chống nhiều instance đồng loạt thử lại.
- **`invalid_grant`:** không đổi code/refresh token cũ vô hạn; điều tra tình huống hết hạn, reuse, rotation hoặc bắt đầu lại flow khi phù hợp.
- **`invalid_client`:** không brute force credential; sửa cấu hình client/secret một cách an toàn.
- **Authorization Code Flow:** nếu code đã được tiêu thụ thì retry cùng code không tạo quyền dùng lần hai.
- **Refresh token rotation:** client nên phối hợp **một yêu cầu refresh tại một thời điểm** cho một token family/session và cập nhật token mới an toàn; timeout không chứng minh yêu cầu đầu chắc chắn thất bại.
- **Device Flow:** tuân thủ `interval`, `authorization_pending`, `slow_down` thay vì retry bằng thuật toán của API nghiệp vụ.

## 10. Hạn mức và bảo mật token: điều gì được và không được giải quyết?

| Vấn đề | Rate limiting hỗ trợ gì? | Điều kiện bảo vệ vẫn phải có |
|---|---|---|
| **Bearer access token bị lộ** | Có thể giảm nhịp yêu cầu cấp token mới của attacker | TLS, bảo vệ lưu trữ, audience/scope hẹp, thời hạn, thu hồi, sender-constraining khi phù hợp |
| **Refresh token bị đánh cắp** | Giới hạn số lần gọi `/token` và phát hiện đột biến | Rotation/reuse detection, binding client, session/grant revocation |
| **Client secret bị đoán** | Giới hạn thử sai, phát hiện brute force | Client authentication đúng, secret mạnh/mTLS/private_key_jwt tùy thiết kế |
| **Authorization code bị phát lại** | Giảm tốc độ thử code | Code ngắn hạn, single-use atomic, PKCE, client/redirect binding |
| **JWT giả mạo** | Không trực tiếp khắc phục | Kiểm chữ ký, thuật toán/khóa tin cậy, `iss`, `aud`, `exp`, type/profile |
| **Lạm dụng scope** | Có thể giới hạn tần suất xin scope nhạy cảm | Kiểm grant và quyền được cấp; không tự mở rộng scope |
| **Vượt quyền tài nguyên** | Không tự giải quyết | Resource Server kiểm scope, tenant, owner, role, dữ liệu thực và business policy |
| **Token exchange sai delegation** | Có thể giới hạn số lần xin đổi token | AS xác minh subject/actor và quyền xuống resource server đích |

Ví dụ: Một attacker có bearer access token hợp lệ `aud=payments-api` và `scope=payment:write`. Họ có thể **gọi Payments API bằng chính token đó**, không cần xin token mới. Giới hạn phát hành ở AS **không chặn được** các request sử dụng access token đã có. Payments API cần **rate limiting cho tài nguyên/giao dịch**, object-level authorization, anti-replay/transaction confirmation và cơ chế phát hiện gian lận riêng.

## 11. Giám sát, cảnh báo và điều chỉnh chính sách

Rate limiting chỉ hữu ích khi có số liệu. Những tín hiệu nên đo:

| Tín hiệu | Phân đoạn nên theo dõi | Dùng để làm gì? |
|---|---|---|
| **RPS tại `/token`** | Grant type, client class, edge zone | Phát hiện burst và định cỡ hệ thống |
| **Tỷ lệ từ chối 429 / slow_down** | Grant/client đã xác thực (ẩn danh hóa khi cần) | Phát hiện hạn mức quá thấp hoặc lạm dụng |
| **Tỷ lệ `invalid_client` / `invalid_grant`** | Nguồn/nhóm client, không lộ bí mật | Phát hiện sai cấu hình, brute force và replay |
| **Token phát hành thành công/phút** | Access/refresh, JWT/opaque, tenant, audience | Dự báo chi phí AS/DB/HSM |
| **p50/p95/p99 latency của token issuance** | Grant type và tầng hạ tầng | Cảnh báo suy giảm SLO |
| **Concurrent issuance/signing operations** | HSM/KMS/DB pool/AS instance | Ngăn quá tải hệ thống |
| **Refresh reuse/race events** | Phiên/token family đã băm ID | Phát hiện mất token hoặc lỗi đồng thời |
| **Limiter backend errors** | Region, instance, datastore | Đánh giá phương án fallback |

Đừng đưa access token, refresh token, authorization code, client secret hay OTP vào log/metrics labels. `client_id` và subject ID có thể là định danh nhạy cảm; dùng nhãn phân nhóm, hashing có quản lý hoặc cardinality thấp cho metrics, và lưu audit chi tiết trong hệ thống kiểm soát truy cập khi cần.

### Quy trình chọn ngưỡng

1. **Đo baseline** theo từng grant, client class, tenant và resource trong lúc chưa siết ngưỡng.
2. **Ước lượng khả năng chịu tải** của AS, DB, signing/KMS và downstream, bao gồm traffic tăng đột biến hợp pháp.
3. **Chọn chính sách nhiều lớp** (edge request, verified client, tenant, grant và concurrency) với burst phù hợp.
4. **Bật chế độ chỉ quan sát/shadow** nếu hạ tầng hỗ trợ để ước lượng false positive.
5. **Canary và điều chỉnh** từ metric 429, cấp token thất bại, latency, tỷ lệ hoàn tất login và lỗi refresh.
6. **Xem lại theo sự kiện**: release client mới, thay TTL access token, chuyển từ JWT sang opaque hoặc thêm token exchange có thể thay đổi RPS.

Thay đổi **TTL của access token** có tác động đến tần suất refresh: TTL ngắn hơn có thể tăng lưu lượng `/token` dù cải thiện giới hạn thời gian hiệu lực của bearer token. Phải cân bằng bảo mật và năng lực AS, không chỉ giảm TTL mà quên đo quota.

## 12. Ma trận kiểm thử: bảo mật và độ sẵn sàng

| Trường hợp | Đầu vào | Kết quả kỳ vọng |
|---|---|---|
| **Client hợp lệ trong quota** | `client_credentials` đúng, tần suất bình thường | Cấp token đúng audience/scope/thời hạn |
| **Burst vượt token bucket** | Nhiều request từ cùng client hợp lệ | Từ chối request vượt quota; không ký hoặc ghi token ngoài chính sách |
| **Attacker giả client ID** | Nhiều request không xác thực khai `client_id` của client thật | Không dễ khóa quota đã xác thực của nạn nhân bằng dữ liệu tự khai |
| **Nhiều người dùng sau NAT** | Request hợp pháp cùng public IP | Không vô tình chặn hàng loạt chỉ vì dùng IP quota duy nhất |
| **Botnet đổi IP** | Nhiều IP cùng tấn công một loại grant | Có giới hạn nguồn/tài nguyên và tín hiệu rủi ro bổ sung |
| **Nhiều AS instance** | Request đồng thời qua nhiều replica | Quota toàn cụm/region theo thiết kế; không double-spend bucket ngoài sai số đã công bố |
| **Authorization code dùng lại** | Hai request đổi cùng code | Tối đa một lần tiêu thụ code hợp lệ; request còn lại bị từ chối |
| **Refresh rotation race** | Hai tab gửi cùng R1 gần đồng thời | Không phát hai nhánh token trái quy tắc; xử lý reuse/race theo policy |
| **429 và retry** | Client bị throttle rồi thử lại sau `Retry-After` | Không retry storm; grant không bị tiêu thụ chỉ vì quota reject |
| **Device Flow poll quá nhanh** | Poll trước interval | Có phản hồi `slow_down`/chính sách grant phù hợp; client tăng interval |
| **JWT signing quá tải** | KMS tăng latency | Concurrency limiter/backpressure; không làm cạn pool vô hạn |
| **Limiter datastore bị lỗi** | Redis/shared limiter mất kết nối | Fallback theo chính sách, cảnh báo; không bỏ xác thực/grant validation |
| **Client bị thu hồi quyền** | Vẫn xin scope cao sau role change | AS không tự cấp scope ngoài quyền hiện hành |
| **Token exchange sai audience** | Client xin token cho API không được phép | AS từ chối hoặc chỉ cấp phạm vi/resource được phép |
| **Opaque token bị thu hồi** | Dùng opaque token đã inactive tại resource API | RS từ chối theo introspection; quota issuance không thay thế bước này |
| **Bearer token cũ gọi API** | Không xin token mới, gọi liên tục tới resource | Rate limit tại AS không có tác dụng trực tiếp; RS phải có hạn mức riêng |

### Bài tập tình huống

Ứng dụng **Shop Mobile** có access token thời hạn 10 phút và refresh token được rotation. Đội phát triển vừa giảm access-token TTL từ 30 phút xuống 10 phút, nhưng vẫn đặt quota `5 request/phút trên mỗi IP` tại token endpoint. Mỗi giờ cao điểm, hàng nghìn người dùng trong mạng công ty/NAT cùng nhận IP public; nhiều request refresh đồng thời bị 429. Client thấy 429 liền retry 10 lần/giây, trong khi hai tab của cùng một người dùng vẫn cùng refresh bằng token R1.

**Câu hỏi 1: Vì sao limiter hiện tại gây lỗi dù không có tấn công?**

Quota duy nhất theo IP gom nhiều người dùng hợp pháp vào cùng bucket. TTL ngắn hơn làm refresh thường xuyên hơn; chính sách cũ chưa được tính lại. Retry không backoff làm phát sinh bão request mới.

**Câu hỏi 2: Cần thay đổi những gì?**

Dùng quota nhiều lớp: network-source admission rộng ở edge, quota theo client đã xác thực, theo phiên/user đã xác thực và grant, cùng giới hạn concurrency hệ thống. Định cỡ theo baseline mới, hỗ trợ `Retry-After`/backoff+jitter, và cân nhắc quota riêng cho refresh so với login hoặc M2M.

**Câu hỏi 3: Nếu hai tab cùng đổi R1, chỉ tăng quota đã đủ chưa?**

Chưa. Client nên dùng **single-flight refresh** và cập nhật refresh token mới an toàn. AS phải bảo đảm rotation **nguyên tử**, kiểm reuse và có chính sách phản ứng với race; rate limiting không thay thế an toàn của refresh token.

**Câu hỏi 4: Nếu Shop Mobile đã có access token dùng gọi Payment API 1.000 lần/phút thì quota tại `/token` có chặn không?**

Không. Đây là lưu lượng **sử dụng access token tại Resource Server**, không phải phát hành token. Payment API cần kiểm audience/scope/object permission, rate limit nghiệp vụ và kiểm soát anti-abuse riêng.

## 13. Checklist triển khai token issuance rate limiting

1. **Nhận diện mọi điểm vào:** `/authorize`, login/MFA, `/token`, device flow, token exchange, introspection và revocation có chính sách tương ứng, không dùng một quota cho tất cả?
2. **Phân loại grant:** authorization code, refresh token, client credentials, device polling và exchange được định cỡ theo hành vi thực tế?
3. **Giới hạn nhiều chiều:** edge/source, client **đã xác thực**, tenant/user/session có bằng chứng và quota toàn hệ thống?
4. **Chống spoofing & DoS:** Không dùng mỗi IP hoặc `client_id` tự khai làm khóa cho mọi quyết định; chống high-cardinality bucket?
5. **Chọn thuật toán rõ ràng:** Burst, refill/window, concurrency limit và ngữ nghĩa đếm được tài liệu hóa?
6. **Đồng bộ đa instance:** Cập nhật quota atomic, có chiến lược cross-region/fallback và quan sát các tình huống race?
7. **Không làm yếu grant:** PKCE, authorization code một lần, refresh token rotation và token exchange delegation vẫn được xác minh đầy đủ?
8. **Phát hành tối thiểu:** Chỉ cấp token với `aud`, `scope` và thời hạn được AS cho phép, dù request đang trong quota?
9. **Phản hồi đúng giao thức:** Phân biệt 429/`Retry-After` với `invalid_grant`, `invalid_client`, và `slow_down` của device flow?
10. **Client retry an toàn:** Backoff, jitter, retry budget, refresh single-flight và không dùng lại code/token theo cách phá rotation?
11. **Quan sát và cảnh báo:** Đo attempt/failure/success, latency, issuer capacity, token reuse và lỗi limiter; tuyệt đối không log secret/token?
12. **Kiểm thử hồi quy:** Dùng nhiều instance, shared NAT, botnet, Redis outage, token giả, quyền thay đổi, overload và bypass edge để xác minh các lớp phòng vệ?

**Ghi nhớ:** Giới hạn tốc độ phát hành token là **một chính sách availability và anti-abuse đặt quanh Authorization Server**. Làm đúng đòi hỏi **đếm cả request sai lẫn token được cấp**, phân biệt từng grant, dùng khóa định danh đáng tin, limiter phân tán nguyên tử, và phản hồi để client có thể retry đúng cách. Quota chỉ kiểm **bao nhiêu lần được thử/cấp**, còn quyền cấp token và quyền dùng token vẫn phải dựa vào **grant hợp lệ, issuer, audience, scope, hiệu lực, bảo vệ refresh token và chính sách của resource server**.

### Chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, grant types, `scope` và token error response.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách sử dụng bearer token tại resource server, khác bước issuance.
- **RFC 8628 — OAuth 2.0 Device Authorization Grant:** polling, `interval`, `authorization_pending` và `slow_down`.
- **RFC 8693 — OAuth 2.0 Token Exchange:** grant đổi token và kiểm delegation cho token downstream.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** chỉ định resource đích khi xin token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims và profile của JWT access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra hiệu lực của opaque/reference token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token, hoạt động khác với issuance.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `exp`, `jti` và các quy tắc JWT.
