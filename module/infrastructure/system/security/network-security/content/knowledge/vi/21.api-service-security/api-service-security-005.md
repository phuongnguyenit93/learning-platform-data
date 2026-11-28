# Rate limiting theo client và identity: Kiểm soát công bằng, chống lạm dụng API và bảo vệ dịch vụ mạng

## 1. Rate limiting là gì và giải quyết vấn đề nào?

**Rate limiting** là cơ chế giới hạn **tần suất hoặc tổng chi phí yêu cầu** mà một thực thể được phép tạo ra trong một khoảng thời gian. Với API và dịch vụ mạng, thực thể ấy có thể là **địa chỉ IP nguồn**, **client ứng dụng**, **API key**, **tài khoản người dùng đã xác thực**, **service account**, **thiết bị** hoặc **tenant**. Cách chọn đối tượng bị giới hạn quan trọng không kém cách chọn con số.

Một API có thể có nhiều backend, reverse proxy, load balancer và vùng mạng riêng. Nếu không có cơ chế điều tiết, một client lỗi hoặc một nhóm request tự động có thể tiêu thụ quá nhiều tài nguyên, làm tăng độ trễ và gây lỗi cho những người dùng khác. Ngược lại, nếu gom tất cả thiết bị chung một địa chỉ IP NAT vào cùng một hạn mức quá thấp, người dùng hợp lệ có thể bị chặn lẫn nhau.

Trong chương **API và network service security** thuộc học phần **SECURITY_NETWORK_SECURITY**, rate limiting là lớp bảo vệ bổ sung cho **firewall, reverse proxy, WAF, bảo vệ DNS, phân đoạn mạng, IDS/IPS, xác thực kết nối và chống DDoS**. Nó góp phần bảo vệ tính sẵn sàng, hạn chế credential stuffing và lạm dụng API, nhưng **không tự thay thế xác thực, phân quyền, kiểm tra dữ liệu đầu vào hoặc phòng vệ upstream**.

**Ví dụ:** API đăng nhập cho phép mỗi tài khoản có số lần thử hợp lý trong một khoảng thời gian, đồng thời giới hạn request theo IP trước khi biết tài khoản có thật hay không. Nếu chỉ dùng IP, một hệ thống có thể chặn cả văn phòng qua NAT; nếu chỉ dùng tài khoản, kẻ xấu có thể thử hàng nghìn tài khoản khác nhau từ một nguồn. Một chính sách bảo vệ tốt thường cần **nhiều lớp khóa giới hạn**, mỗi lớp phục vụ một mục tiêu.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **rate limit**, **quota**, **burst**, **concurrency limit**, **request size limit** và **throttling**.
2. Chọn khóa giới hạn theo **IP, client, tài khoản đã xác thực, API key, tenant, endpoint** mà không tin nhầm header do client tự gửi.
3. Diễn giải **fixed window, sliding window, token bucket và leaky bucket** cùng những đánh đổi về độ chính xác và tài nguyên.
4. Tổ chức rate limiting nhiều lớp tại **CDN/WAF → API gateway → service**, kể cả trường hợp có nhiều instance hoặc vùng triển khai.
5. Thiết kế HTTP **429 Too Many Requests**, **Retry-After**, backoff và phản ứng của API client.
6. Thực hiện kiểm thử ranh giới, concurrency, IPv4/IPv6, NAT, retry và các tình huống phân tán bằng môi trường được phép.
7. Giám sát tác động lên người dùng hợp lệ, phân tích false positive/false negative và xây runbook khi limit store bị lỗi.

## 2. Những khái niệm dễ nhầm

| Khái niệm | Đơn vị/quy tắc | Mục tiêu | Ví dụ minh họa |
| --- | --- | --- | --- |
| **Rate limit** | Request/s, request/min hoặc đơn vị chi phí/thời gian | Giới hạn tốc độ tiêu thụ | 60 requests/phút/user |
| **Burst allowance** | Số request có thể đến dồn trong thời gian ngắn | Cho phép đỉnh tải hợp lệ | Cho 20 request đến gần như đồng thời |
| **Quota** | Tổng request/bytes/operations trong chu kỳ | Kiểm soát sử dụng theo gói hoặc ngân sách | 10.000 requests/ngày/tenant |
| **Concurrency limit** | Số tác vụ đang hoạt động | Bảo vệ worker, DB pool và queue | 5 exports đồng thời/tenant |
| **Body size limit** | Byte/request | Chặn payload quá lớn | 1 MiB JSON body |
| **Bandwidth limit** | Byte hoặc bit/giây | Bảo vệ đường truyền | 5 Mbit/s/client |
| **Timeout** | Thời gian xử lý/chờ | Tránh giữ tài nguyên quá lâu | 15 giây cho API thông thường |
| **Throttling** | Làm chậm, xếp hàng hoặc từ chối theo chính sách | Điều tiết tải | Trì hoãn request hoặc trả 429 |

Các cơ chế này **không tương đương nhau**. Một người dùng có thể gửi một request xuất báo cáo rất nặng nhưng không vượt giới hạn requests/minute; request ấy vẫn có thể giữ CPU và cơ sở dữ liệu quá lâu. Ngược lại, hàng nghìn request nhỏ có thể làm quá tải xác thực hoặc cache mà không vi phạm giới hạn kích thước body.

### 2.1. Giới hạn theo đơn vị nào?

Một hệ thống cần định nghĩa rõ:

- **Sự kiện tính phí:** trước hay sau xác thực, trước hay sau cache lookup, khi bắt đầu hay hoàn tất request?
- **Khóa:** account ID, API key ID, tenant ID, địa chỉ IP, device ID hoặc tổ hợp.
- **Phạm vi:** một route, nhóm route, toàn API, một region hay toàn tổ chức.
- **Đơn vị:** một request, một operation, số byte hoặc **weighted cost**.
- **Chu kỳ:** mỗi giây/phút hoặc một khoảng quota theo lịch.
- **Hành vi khi vượt:** từ chối, đợi, xếp hàng, giảm chất lượng hoặc chuyển sang chế độ dự phòng.

Ví dụ **60 requests/phút/user** còn mơ hồ nếu không biết một user có nhiều API keys, request tới hai cluster khác nhau có được tính chung hay không, và token bucket có cho phép burst bao nhiêu.

### 2.2. Rate limiting không phải authorization

**Authentication** trả lời ai đang yêu cầu. **Authorization** quyết định người đó có quyền làm gì. **Rate limiting** giới hạn họ có thể yêu cầu nhanh và nhiều tới đâu. Một request dưới hạn mức nhưng **không được phép truy cập** vẫn phải bị từ chối; một tài khoản đã xác thực và có quyền vẫn có thể bị trả 429 nếu tiêu thụ vượt ngân sách.

**Không dùng việc đã có quota để bỏ qua kiểm tra quyền trên từng tài nguyên.** Một API có lỗ hổng BOLA/IDOR có thể bị khai thác ngay với một vài request, dù rate limiting được cấu hình rất chặt.

## 3. “Client” và “identity” có thể là những đối tượng khác nhau

### 3.1. Các khóa rate limit thường gặp

| Khóa giới hạn | Nguồn đáng tin phù hợp | Khi nào hữu ích | Giới hạn/rủi ro |
| --- | --- | --- | --- |
| **Source IP** | Remote peer được gateway nhìn thấy, hoặc nguồn đã xác minh qua proxy tin cậy | Trước xác thực, chặn burst từ một nguồn | CGNAT, shared proxy, IPv6 privacy, thay IP |
| **IPv6 prefix / nhóm địa chỉ** | Địa chỉ nguồn đã xác minh và quy tắc nhóm phù hợp | Khi client thay nhiều IPv6 addresses | Gộp quá rộng có thể ảnh hưởng nhiều người hợp lệ |
| **Account/user ID** | Kết quả xác thực của IdP/auth service | Hạn chế hoạt động trên một tài khoản | Kẻ xấu có thể phân tán qua nhiều accounts |
| **API key ID** | Key đã được gateway xác minh, không dùng raw secret làm metric label | Bảo vệ tích hợp máy-máy | Một app có thể sở hữu nhiều keys |
| **OAuth client ID** | Client đã được xác thực/ràng buộc theo OAuth policy | Hạn chế một ứng dụng tích hợp | Client ID công khai trong một số flow không chứng minh client đã được xác thực |
| **Service identity / workload ID** | mTLS/SPIFFE hoặc identity system đã kiểm tra | Service-to-service APIs | Rotation/redeploy, identity cấp quá rộng |
| **Tenant / organization ID** | Claim đã được xác thực và policy mapping từ hệ thống tin cậy | Công bằng giữa khách hàng doanh nghiệp | Một tenant có thể có nhiều users/keys |
| **Device identity** | MDM, client certificate hoặc cơ chế ràng buộc thiết bị đã xác minh | Hạn chế thiết bị/tài nguyên nhạy cảm | BYOD, đổi thiết bị, spoofing nếu chỉ tin chuỗi tự khai |
| **Session ID** | Session đã được tạo và xác minh bởi server | Chặn burst trong phiên | Có thể tạo phiên mới, hết hạn hoặc đăng nhập lại |
| **Route / operation** | Router/API schema do server xác định | Phân loại chi phí nghiệp vụ | Một endpoint có thể có nhiều kiểu payload khác nhau |

Không có một khóa duy nhất phù hợp cho **mọi API**. Các hệ thống lớn thường kết hợp **giới hạn hạ tầng theo nguồn + giới hạn nghiệp vụ theo danh tính đã xác thực + giới hạn theo tenant + giới hạn tài nguyên đắt tiền**.

### 3.2. Một người dùng, nhiều thiết bị và nhiều API keys

Nếu tài khoản A dùng điện thoại và laptop, **per-user limit** thường được chia sẻ giữa các thiết bị. Nếu muốn có hạn mức riêng theo thiết bị, cần có **device identity đáng tin** và quy tắc tổng hạn mức user/tenant để một người không nhân vô hạn quyền bằng cách tạo thêm thiết bị.

Tương tự, nếu tenant X tạo 100 API keys, **per-key limit** đơn lẻ có thể cho phép tenant X sử dụng gấp 100 lần một tenant chỉ có một key. Cần có **parent budget theo tenant** và **child budget theo key/user** khi mục tiêu là công bằng và kiểm soát ngân sách.

### 3.3. Identity phải được xác minh, không lấy từ input tự khai

Một header như:

~~~http
GET /api/orders HTTP/1.1
Host: api.lab.example
X-User-ID: premium-customer
~~~

**Không chứng minh** người gửi là khách hàng premium. Nếu gateway rate limit theo **X-User-ID** do Internet client tự đặt, người gửi có thể đổi chuỗi để né hạn mức hoặc đẩy request vào bucket của người khác.

Cách thiết kế đúng là dùng danh tính do **auth middleware/IdP/API key verifier** xác nhận. Nếu gateway chuyển danh tính cho upstream bằng header nội bộ, điểm ingress phải **xóa hoặc ghi đè** bản header từ client, bảo vệ kênh gateway–service và bảo đảm backend **không thể được gọi trực tiếp** để giả mạo danh tính.

### 3.4. OAuth và claim không tự đáng tin nếu chưa xác minh

Đối với JWT access token, hệ thống cần kiểm tra **chữ ký, issuer, audience, thời gian hiệu lực và các ràng buộc liên quan** trước khi dùng claim như `sub`, `client_id` hoặc `tenant_id` làm khóa. Chỉ **base64-decode JWT payload** rồi đọc user ID là không đủ.

Lưu ý OAuth **client_id** không nhất thiết là bằng chứng một confidential client đã tự xác thực trong mọi flow. Cần hiểu loại token, cơ chế cấp phát, audience và ứng dụng có quyền làm gì trước khi coi claim đó là định danh đã xác minh.

### 3.5. Khóa phải ổn định nhưng không lộ bí mật

Nên dùng **internal subject ID/tenant ID/key identifier** đã xác minh thay vì:

- Email hoặc tên hiển thị có thể thay đổi.
- API secret, access token, cookie phiên hoặc mật khẩu.
- User-Agent hoặc hostname do client tự khai.
- Chỉ raw public IP làm định danh người dùng lâu dài.

Nếu phải dùng định danh nhạy cảm trong counter key, có thể **mã hóa biểu diễn khóa (ví dụ HMAC có secret được bảo vệ) hoặc chuẩn hóa định danh nội bộ** phù hợp chính sách. Không đặt raw token vào tên key Redis, log, metric label hoặc response headers.

## 4. Địa chỉ IP qua nhiều proxy: Ranh giới tin cậy

### 4.1. Vì sao địa chỉ IP nhìn thấy ở backend có thể sai với ý định?

Trong kiến trúc:

~~~mermaid
flowchart LR
    C["Client thực"] --> CDN["CDN / Edge"]
    CDN --> LB["Load balancer"]
    LB --> GW["API Gateway / Auth"]
    GW --> APP["Service"]
    GW --> COUNTER["Rate-limit counter"]
~~~

Backend có thể thấy **IP của API gateway** là remote peer. Nếu backend giới hạn theo remote IP này, toàn bộ người dùng sẽ bị dồn vào **một bucket**. Ngược lại, nếu gateway tự tin **X-Forwarded-For** do Internet gửi, client có thể tự đổi IP được dùng làm khóa.

### 4.2. X-Forwarded-For, Forwarded và các header riêng

Một số hệ thống dùng:

- **Forwarded** theo cú pháp HTTP đã chuẩn hóa.
- **X-Forwarded-For (XFF)** như quy ước phổ biến.
- Header vendor như **True-Client-IP** hoặc header edge tương đương.
- **PROXY protocol** khi load balancer và backend thống nhất dùng một cơ chế truyền metadata nguồn ở lớp kết nối.

Các giá trị này **chỉ tin cậy trong một trust boundary đã được bảo vệ**. Nếu backend được truy cập trực tiếp qua Internet, hoặc proxy cuối cùng không xác thực nguồn header, một client có thể gửi header giả rồi làm sai rate limit và audit log.

### 4.3. Quy trình xác định IP nguồn đúng

1. Xác định **trusted ingress**: CDN/LB/proxy nào thực sự nằm trong quyền quản trị và đã được bảo vệ đường vào.
2. Chặn truy cập trực tiếp tới backend/gateway nếu policy yêu cầu mọi traffic qua ingress đã kiểm soát.
3. Tại edge, **xóa/chuẩn hóa các client-IP headers không được tin**, sau đó tạo metadata nguồn đáng tin theo cấu hình của sản phẩm.
4. Ở mỗi hop, chỉ tin remote peer khi nó thuộc **danh sách proxy tin cậy**; không chọn ngẫu nhiên phần tử đầu/cuối của XFF.
5. Kiểm tra trường hợp có nhiều proxy, IPv4/IPv6, địa chỉ private, format không hợp lệ và proxy config thay đổi.
6. Trong log, tách **remote_peer_ip**, **verified_client_ip**, **trusted_proxy_chain** để việc điều tra không bị nhầm.

**Thứ tự xuất hiện trong XFF không tự quyết định độ tin cậy.** Phương pháp xác định client IP phải dựa trên trust policy và cách từng hop thêm/ghi đè giá trị thực tế.

### 4.4. NAT, CGNAT và người dùng bị chặn oan

Một trường học, văn phòng, Wi-Fi khách hoặc nhà mạng di động có thể dùng **NAT/CGNAT** khiến nhiều thiết bị chia sẻ một public IP. Một mức **10 requests/phút/IP** có thể chặn oan cả nhóm dù mỗi người chỉ gửi ít request.

Giải pháp cân bằng:

- Dùng IP limit trước xác thực như một **phòng vệ sơ cấp**, không coi IP là danh tính mạnh.
- Sau xác thực, áp **per-user/per-client/per-tenant limits** có quota riêng.
- Đặt ngân sách IP theo mô hình traffic và khả năng NAT của đối tượng sử dụng.
- Theo dõi false positives theo ASN/điểm ra công cộng, không tự bỏ rate limit cho mọi nguồn NAT.
- Với endpoint login, kết hợp khóa IP/source và khóa tài khoản/nhóm tài khoản để hạn chế lạm dụng phân tán.

### 4.5. IPv6 và rotating addresses

Một thiết bị IPv6 có thể sử dụng **privacy addresses** hoặc nhiều địa chỉ theo thời gian. Nếu rate limit chỉ theo **địa chỉ IPv6 /128**, một client có thể đổi nguồn hợp lệ trong một số kiến trúc và làm bucket phân tán.

Có thể cân nhắc nhóm theo **prefix** (chẳng hạn /64 trong một số thiết kế) với điều kiện:

- Prefix thực sự đại diện đối tượng mạng nào và có khả năng thay đổi không?
- Có NAT, VPN, ISP reassignment hoặc nhiều người dùng chung một prefix không?
- Nguy cơ chặn oan nếu nhóm quá rộng là gì?
- Chính sách IPv4/IPv6 có mức công bằng tương đương không?

**Không mặc định /64 là định danh của đúng một người dùng**; điều đó phụ thuộc cấp phát prefix và topology. Sau đăng nhập, danh tính xác thực thường là khóa nghiệp vụ tốt hơn một địa chỉ IP bất kỳ.

## 5. Rate limiting nhiều lớp theo thời điểm xác thực

Không phải request nào cũng có identity đáng tin trước khi xử lý. Một kiến trúc thực tế phân chia:

~~~mermaid
flowchart TD
    REQ["HTTP request đến API"] --> EDGE["Giới hạn edge theo nguồn đã xác minh<br/>Global / IP / ASN / connection"]
    EDGE --> AUTH{"Xác thực thành công?"}
    AUTH -->|Không| PRE["Giới hạn login/error theo nguồn,<br/>đối tượng tài khoản và chính sách auth"]
    AUTH -->|Có| ID["Lấy verified user/client/tenant ID"]
    ID --> BUDGET{"Đủ budget các lớp?"}
    BUDGET -->|Không| REJECT["HTTP 429 hoặc hành động policy"]
    BUDGET -->|Có| AUTHZ{"Được quyền gọi operation?"}
    AUTHZ -->|Không| DENY["403/404 theo authz policy"]
    AUTHZ -->|Có| SERVICE["Gọi service có timeout,<br/>concurrency và cost limits"]
    PRE --> ERR["Phản hồi lỗi xác thực an toàn"]
~~~

**Sơ đồ đơn giản hóa thứ tự xử lý.** Trong thực tế có thể kiểm tra authorization trước khi trừ quota tính phí, hoặc áp một số counter trước parse/đọc body. Điều quan trọng là các **rate-limit keys phải đáng tin tại thời điểm sử dụng** và không tạo đường bypass.

### 5.1. Edge pre-auth limit

Edge/CDN/WAF có thể dùng một giới hạn khá rộng theo IP/nhóm nguồn để giảm burst và request không cần đến hệ thống xác thực. Đây là **biện pháp giảm tải bước đầu**, không phù hợp làm cách duy nhất kiểm soát quota của tài khoản vì NAT và source IP rotation.

### 5.2. Authentication endpoints

Đăng nhập, khôi phục mật khẩu, gửi OTP, xác minh MFA và API tạo token có đặc trưng riêng: **giới hạn quá chặt gây từ chối dịch vụ cho người hợp lệ**, còn giới hạn quá lỏng tăng rủi ro thử mật khẩu/OTP và chi phí SMS/email.

Có thể dùng những ngân sách riêng:

- Theo **source IP hoặc nguồn đã xác minh** để ngăn burst.
- Theo **định danh tài khoản được yêu cầu** (đã chuẩn hóa theo chính sách auth), nhưng tránh tạo cơ chế lockout dễ bị lạm dụng để DoS người khác.
- Theo **thiết bị/session đã xác minh** nếu hệ thống có cách nhận dạng đáng tin.
- Theo **operation nhạy cảm** như gửi OTP, tạo reset link, yêu cầu gửi email.
- Theo **toàn hệ thống/tenant** để bảo vệ tài nguyên downstream.

Không phản hồi khác biệt tiết lộ rõ tài khoản có tồn tại hay không chỉ vì counter cho một account chưa được tìm thấy. Việc chuẩn hóa account identifier, thông báo lỗi và quản lý lockout phải chống **account enumeration**.

### 5.3. Post-auth limit theo user, client và tenant

Khi IdP/API key verifier đã xác thực, gateway có thể chọn các khóa:

~~~text
global:api-service
tenant:<verified-tenant-id>
client:<verified-client-or-api-key-id>
user:<verified-user-id>
operation:<route-family>
~~~

Đây là **mô hình tên khóa**, không phải code chạy trong Redis. Trong triển khai thực tế cần **namespace theo môi trường/phiên bản policy**, bảo vệ định danh nhạy cảm và tránh raw secret.

Một request có thể phải thỏa **đồng thời** ngân sách toàn service, tenant, user và operation. Ví dụ user còn 10 requests nhưng tenant đã hết quota tổng thì request vẫn có thể bị từ chối theo hợp đồng của tenant.

### 5.4. Tránh lập danh sách “VIP bypass all”

Một exception cho dịch vụ quan trọng không nên có nghĩa là **bỏ tất cả giới hạn**. Có thể nới riêng budget hợp đồng cho service account đã được xác thực, song vẫn cần **global safety guard, concurrency cap, parser/body limit và audit**.

Exception cần có **owner, lý do, phạm vi route, mức tối đa, thời hạn và lịch rà soát**. Một khóa API bị lộ mà nằm trong danh sách bypass vô hạn có thể gây tiêu thụ tài nguyên rất lớn.

## 6. Các thuật toán rate limiting phổ biến

Không có thuật toán nào đồng thời đạt độ chính xác, tính công bằng, chi phí bộ nhớ, tốc độ và khả năng phân tán tối ưu cho mọi trường hợp. Trước khi chọn thuật toán cần xác định **có cho phép burst hay không, giới hạn có chính xác tuyệt đối ở ranh giới thời gian không, có bao nhiêu khóa và hệ thống chạy một hay nhiều instance**.

### 6.1. Fixed window counter

**Fixed window** chia thời gian thành các khoảng cố định (ví dụ từng phút theo đồng hồ) và đếm request trong mỗi khoảng. Nếu đã dùng đủ budget, các request còn lại trong cùng window bị từ chối.

~~~text
Policy: 100 requests / phút / user

12:00:00–12:00:59  nhận tối đa 100 requests
12:01:00–12:01:59  bắt đầu window mới, nhận tiếp tối đa 100
~~~

Ưu điểm: dễ hiểu, ít trạng thái (một counter cho mỗi khóa/window), thuận tiện khi dùng store hỗ trợ tăng counter nguyên tử. Nhược điểm: **hiệu ứng ranh giới cửa sổ** — client có thể gửi 100 request ngay cuối phút rồi 100 request ngay đầu phút tiếp theo, tức gần **200 request trong thời gian rất ngắn** dù policy quảng cáo 100/phút.

Đặc biệt cần xem cách triển khai **TTL, reset và tăng counter nguyên tử**. Đọc giá trị rồi ghi lại theo hai lệnh tách rời dễ dẫn đến race condition ở nhiều worker.

### 6.2. Sliding window log

**Sliding window log** giữ timestamp của những request được tính trong khoảng trượt dài W giây. Khi request mới tới, xóa timestamp quá cũ, đếm các request còn thuộc khoảng, rồi quyết định allow/reject.

~~~text
Policy: tối đa 3 request trong 10 giây

t =  0s: request A -> allow
t =  2s: request B -> allow
t =  4s: request C -> allow
t =  5s: request D -> reject
t = 11s: request E -> allow (A tại 0s đã ra khỏi cửa sổ)
~~~

Độ chính xác theo cửa sổ trượt cao hơn fixed window ở ranh giới, nhưng cần giữ **nhiều timestamp**, dọn dữ liệu cũ, và xử lý concurrency/clock một cách nhất quán. Nếu hệ thống có hàng triệu user và mỗi user rất nhiều request, lưu log từng request có thể tốn bộ nhớ và thao tác store.

### 6.3. Sliding window counter (xấp xỉ)

Một lựa chọn khác lưu counter cho window hiện tại và window trước, rồi tính **phần đóng góp ước lượng** từ window trước dựa trên vị trí thời gian hiện tại. Nó thường rẻ hơn log từng request nhưng không chính xác tuyệt đối khi lượng request phân bố không đều trong window.

~~~text
Ước lượng điển hình:
  weighted_count =
      current_window_count
    + previous_window_count * remaining_fraction_of_previous_window

Ví dụ:
  previous = 80 requests
  current  = 10 requests
  đã đi qua 25% cửa sổ hiện tại
  weighted_count = 10 + 80 * 0,75 = 70 requests
~~~

Đây là công thức **xấp xỉ**, giả định kiểu phân bổ của sự kiện trong window trước khi tính tỷ trọng; không được coi nó giống sliding log chính xác. Khi cần bảo vệ ngân sách đắt đỏ hoặc quy định cứng, phải đánh giá tác động của sai số.

### 6.4. Token bucket

**Token bucket** lưu một lượng token tối đa là **capacity C**. Token được thêm theo tốc độ **r token/giây**, tối đa bằng C. Mỗi request tiêu thụ **cost** token; request được cho qua nếu có đủ token và bị từ chối hoặc chờ nếu không đủ.

Mô hình cập nhật:

~~~text
tokens_before = min(
    capacity,
    previous_tokens + refill_rate * elapsed_seconds
)

if tokens_before >= request_cost:
    tokens_after = tokens_before - request_cost
    ALLOW
else:
    tokens_after = tokens_before
    REJECT hoặc DELAY theo policy
~~~

**Ví dụ:** capacity = **20 token**, refill = **5 token/giây**, cost = **1 token/request**. Bucket đầy ở thời điểm bắt đầu:

| Thời điểm | Hành vi | Số token |
| --- | --- | --- |
| 0 giây | Bắt đầu ở capacity | 20 |
| 0 giây | 18 request đến gần như cùng lúc, đều được cho phép | 2 còn lại |
| 3 giây | Sau 3 giây không có request, refill 15 token | 17 |
| 3 giây | 19 request mới đến gần như cùng lúc | **17 allow, 2 reject** |
| 4 giây | Nếu không có request khác, refill 5 token | 5 |

**Ý nghĩa:** client có thể gửi burst tối đa theo lượng token đã tích lũy; về lâu dài tốc độ trung bình bị điều tiết về khoảng refill rate. **Capacity 20 không đồng nghĩa 20 requests/giây**, và **refill 5/s không đồng nghĩa luôn cho phép đúng 5 request trong từng giây đồng hồ**.

Với request có **cost khác nhau**, token bucket có thể kiểm soát công bằng theo tài nguyên thay vì đếm mọi operation bằng một đơn vị.

### 6.5. Leaky bucket và hàng đợi

Mô hình **leaky bucket** thường được dùng để làm phẳng dòng request ra với một tốc độ xử lý ổn định; dữ liệu mới đến có thể vào một **hàng đợi hữu hạn** và bị từ chối khi quá dung lượng. Một số tài liệu hoặc sản phẩm dùng tên leaky bucket cho biến thể cơ chế đo tải, vì vậy luôn kiểm tra semantics thật của nền tảng.

~~~text
Input:  10 requests đến cùng lúc
Output target: 2 requests/giây
Queue capacity: 8 requests (minh họa)

Request được nhận có thể phải chờ.
Request mới khi hàng đợi đầy bị reject theo policy.
~~~

**Rủi ro:** không có hàng đợi miễn phí. Đợi quá lâu làm tăng latency, tốn RAM/connection và có thể vượt deadline ở client. Nếu mục tiêu là phản hồi nhanh cho API tương tác, **trả 429 có Retry-After phù hợp** đôi khi tốt hơn kéo dài hàng đợi không có kiểm soát.

### 6.6. GCRA và các biến thể

Một số hệ thống dùng **Generic Cell Rate Algorithm (GCRA)** hoặc cơ chế tương đương để theo dõi thời điểm request tiếp theo được phép theo **virtual scheduling time**. Có thể biểu diễn hạn mức mà không lưu log của từng request. Việc hỗ trợ burst và phép tính có thể tương đương một số chính sách token bucket khi tham số được chọn đúng, nhưng triển khai khác nhau.

**Không cần tự viết GCRA từ đầu** nếu gateway/store đã cung cấp thuật toán được kiểm thử. Điều quan trọng đối với kiến trúc là biết **burst semantics, atomicity, thời gian, bộ nhớ và hành vi khi store lỗi**.

### 6.7. So sánh và lựa chọn

| Thuật toán | Có burst? | Trạng thái lưu | Điểm mạnh | Điểm yếu |
| --- | --- | --- | --- | --- |
| **Fixed window** | Có thể burst ở ranh giới | Counter/window | Đơn giản, dễ phân tán | Độ dồn tại boundary |
| **Sliding log** | Theo giới hạn window | Timestamp từng event | Chính xác theo cửa sổ trượt | Tốn bộ nhớ và thao tác |
| **Sliding counter** | Điều tiết xấp xỉ | Hai hoặc vài counters | Giảm tài nguyên so sliding log | Có sai số |
| **Token bucket** | Có, theo capacity | Tokens + last update | Linh hoạt burst và weighted cost | Cần đồng bộ state/clock |
| **Leaky bucket / queue** | Đầu ra thường được làm phẳng | Queue hoặc virtual state | Chống tăng tốc đột ngột vào backend | Dễ tăng latency/queue nếu cấu hình sai |
| **GCRA** | Theo tolerance | Virtual time/state | Nhẹ trạng thái, phù hợp một số quota | Tham số ít trực quan với người vận hành |

**Không tự đồng nhất hai cấu hình có cùng “100/min”**: fixed window, sliding window và token bucket có thể tạo trải nghiệm và số request được phép khác nhau khi client gửi burst.

## 7. Hierarchical rate limiting và công bằng theo ngân sách

### 7.1. Kết hợp các tầng giới hạn

Một API đa tenant có thể yêu cầu request đi qua các ngân sách:

~~~mermaid
flowchart LR
    REQ["Request đã xác thực"] --> G{"Global service budget"}
    G -->|Đủ| T{"Tenant budget"}
    G -->|Hết| X["Reject / shed load"]
    T -->|Đủ| U{"User hoặc API-key budget"}
    T -->|Hết| X
    U -->|Đủ| O{"Operation cost / concurrency"}
    U -->|Hết| X
    O -->|Đủ| A["Backend thực thi"]
    O -->|Hết| X
~~~

Ví dụ **không phải ngưỡng production**:

| Budget | Giới hạn minh họa | Mục tiêu |
| --- | --- | --- |
| Toàn dịch vụ | 20.000 đơn vị cost/giây | Tránh vượt năng lực hạ tầng |
| Tenant A | 1.000 đơn vị cost/phút | Cân bằng giữa tenant |
| User trong tenant A | 120 request/phút | Ngăn một user chiếm quota tenant |
| API key cụ thể | 60 request/phút | Chặn app lỗi hoặc token bị lộ |
| /reports/export | 2 tác vụ đồng thời/user | Giữ worker/DB ổn định |

Một request chỉ được phép nếu **tất cả budget bắt buộc** còn khả dụng và được trừ theo chính sách. Những hạn mức có đơn vị khác nhau phải được đánh giá riêng; không lấy **request/minute** cộng trực tiếp với **cost/second**.

### 7.2. Atomicity khi trừ nhiều ngân sách

Giả sử request còn 1 token ở budget user nhưng tenant đã hết. Nếu hệ thống **trừ token user trước** rồi phát hiện tenant hết và trả 429, client có thể mất quota user mà request chưa thực thi. Tùy chính sách, điều này có thể bị xem là không công bằng.

Các hướng thiết kế:

1. Kiểm tra và trừ **nguyên tử trong một operation** nếu cùng store/phạm vi hỗ trợ.
2. Dùng **reserve/commit/cancel** với timeout/rollback có kiểm soát nếu chi phí thực tế chỉ biết sau xử lý.
3. Chấp nhận tính phí cho **attempt** theo hợp đồng rõ ràng với các endpoint bảo vệ chống lạm dụng.
4. Nếu kiểm tra nhiều vùng/cluster, xác định mức **xấp xỉ có chủ ý** và trần an toàn thay vì tuyên bố tuyệt đối.

Không giải quyết bằng thao tác **GET rồi SET** trên shared counter khi nhiều instance cùng ghi; có thể xảy ra race condition, vượt quota hoặc trừ nhiều lần.

### 7.3. Charge on attempt hay charge on success?

| Chiến lược | Lợi ích | Vấn đề cần giải quyết |
| --- | --- | --- |
| **Tính phí ngay lúc nhận request** | Bảo vệ trước khi backend tốn tài nguyên | Request bị 401/403/5xx có thể vẫn tiêu quota |
| **Tính phí sau xác thực** | Phân phối theo verified identity | Chi phí xử lý auth trước limit có thể cao |
| **Tính phí sau khi xử lý thành công** | Gần quota tiêu thụ nghiệp vụ | Request thất bại vẫn có thể tiêu tốn CPU/DB |
| **Reserve cost trước, settle sau** | Hỗ trợ operation cost khác nhau | Cần reconciliation, idempotency và timeout |

Trong thực tế có thể dùng **hai budget**: guard theo số attempts ở edge/auth và quota nghiệp vụ cho operations đã được xác thực. Cần công bố quy tắc tính phí cho khách hàng khi quota là thành phần hợp đồng.

## 8. Weighted-cost limiting: Một request không phải lúc nào cũng bằng một request

Một API trả danh sách 10 phần tử có chi phí khác API xuất 100.000 dòng dữ liệu. GraphQL cũng có thể có query ngắn về số byte nhưng yêu cầu thực hiện nhiều nested operations. Đếm mọi request bằng **1** có thể không phản ánh chi phí.

### 8.1. Ví dụ weight theo operation

| Operation | Cost minh họa | Điều kiện bổ sung |
| --- | --- | --- |
| GET /health | 1 | Monitor được phép, health checks không phụ thuộc auth phức tạp |
| GET /items?pageSize=20 | 1 | Giới hạn pageSize tối đa |
| GET /items?pageSize=200 | 5 | Hạn chế số trang và DB scan |
| POST /search/complex | 10 | Complexity budget, timeout |
| POST /reports/export | 25 | Queue/concurrency và quota export |
| POST /upload | Tùy MiB hoặc object size | Per-file, total body và storage quota |

Các weight này chỉ để **luyện tư duy thiết kế**, không phải công thức chuẩn. Chi phí thực tế có thể dựa trên query plan, độ sâu GraphQL, số dòng trả về, CPU time, external API calls hoặc giới hạn hợp đồng.

### 8.2. Ví dụ tính ngân sách

Tenant có **100 cost units/phút**, user A thực hiện:

~~~text
20 lần GET /items?pageSize=20  ×  1 =  20 units
 5 lần GET /items?pageSize=200 ×  5 =  25 units
 3 lần POST /search/complex  × 10 =  30 units
                                   ---------
Tổng đã dùng =                         75 units
Ngân sách còn =                        25 units
~~~

Nếu một yêu cầu export tốn 25 units đến tiếp thì có thể được chấp nhận theo policy; một export thứ hai ngay sau đó sẽ vượt quota nếu không có refill/reconciliation. **Số requests đã gửi là 28**, nhưng chi phí được tính là **75 units**.

### 8.3. Complexity cap khác weighted budget

Ngay cả khi tenant còn nhiều quota, một GraphQL query hoặc SQL filter có độ phức tạp cực lớn vẫn cần **per-request maximum cost/depth/rows/time** để bảo vệ backend. Token bucket theo average cost không thay thế **hard per-operation limit**.

### 8.4. Pagination, batch và streaming

- **Pagination:** giới hạn pageSize, tránh client dùng một request lấy khối dữ liệu vô hạn.
- **Batch API:** đếm cost theo số phần tử hoặc tác vụ, không để batch 1.000 items tính như một request đơn giản.
- **Long-running export:** dùng queue/concurrency và quota theo job; một HTTP request trả 202 không có nghĩa chi phí backend đã kết thúc.
- **gRPC streaming/WebSocket:** giới hạn messages/bytes/operations trên luồng, số connections và thời gian; mỗi connection có thể chở rất nhiều tác vụ.
- **Retries:** quyết định request retry có tính thêm quota hay được miễn theo idempotency/contract, tránh vừa bị 429 vừa tạo retry storm.

## 9. HTTP 429 Too Many Requests và hành vi client

### 9.1. Khi nào dùng 429?

**HTTP 429 Too Many Requests** chỉ ra client đang gửi quá nhiều requests trong khoảng thời gian hoặc theo chính sách áp dụng. Đây là mã HTTP quen thuộc cho việc một request bị rate limiting từ chối. Các trường hợp **không xác thực** hoặc **không đủ quyền** vẫn cần xử lý bằng **401/403** theo semantics riêng, dù hệ thống có thể áp rate limit để giảm chi phí.

Một response minh họa:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 10
Cache-Control: no-store

{"error":"rate_limit_exceeded","retry_after_seconds":10}
~~~

Ở đây **Retry-After: 10** là số **giây** được gợi ý để client đợi trước khi thử lại, không phải thông báo chắc chắn lần thử kế tiếp sẽ được cấp quyền. Retry-After cũng có dạng **HTTP-date** theo semantics HTTP. Với các ngân sách chia sẻ, cửa sổ động và cạnh tranh giữa request, kết quả tại thời điểm thử lại vẫn có thể là 429.

### 9.2. RateLimit fields và hợp đồng API

Một số sản phẩm hỗ trợ các trường **RateLimit** để truyền thông tin policy/budget, nhưng tên trường và cách diễn giải cần theo chuẩn/profile **được nền tảng thực tế hỗ trợ**; không trộn các biến thể header cũ và mới rồi giả định client hiểu đúng.

Hợp đồng API nên làm rõ:

- Đơn vị giới hạn (requests hoặc cost units).
- Scope của quota (user, key, tenant, route), ở mức đủ để client sử dụng đúng mà không lộ thông tin nội bộ.
- Cách tính reset hoặc refill, và thời điểm nên thử lại.
- Các trường hợp ưu tiên dùng Retry-After và xử lý 429.
- Các giới hạn không được công khai vì lý do chống lạm dụng, nếu có.

**Đừng công bố raw API key, tenant secret, ID nhạy cảm hoặc thông tin chi tiết về rule phòng vệ** trong response. Không tự khẳng định một trường Remaining bằng 0 luôn đồng nghĩa tất cả request của client bị chặn vì có thể tồn tại nhiều bucket/operation với cost khác nhau.

### 9.3. Phân biệt 429, 503 và các lỗi khác

| Mã hoặc trạng thái | Ngữ nghĩa thường gặp | Hướng xử lý client |
| --- | --- | --- |
| **429 Too Many Requests** | Quá hạn mức theo rate/quota policy | Tuân Retry-After/backoff; giảm tốc độ |
| **503 Service Unavailable** | Server tạm không sẵn sàng/quá tải | Backoff và kiểm tra khả năng retry an toàn |
| **401 Unauthorized** | Thiếu/không hợp lệ thông tin xác thực theo HTTP semantics | Sửa/quay lại flow xác thực, tránh retry vô hạn |
| **403 Forbidden** | Không được phép thực hiện | Không đổi tốc độ để vượt authorization |
| **413 Content Too Large** | Body request vượt giới hạn | Giảm payload hoặc dùng upload flow hợp lệ |
| **408 / timeout** | Không hoàn thành request kịp | Xem retry policy, idempotency, mạng và server |
| **gRPC RESOURCE_EXHAUSTED** | Hết quota/tài nguyên theo gRPC status semantics | Dùng backoff/trailer metadata đúng client library |

Không dùng 429 làm cách che mọi lỗi backend: nếu store quota bị lỗi, hành vi **fail-open, fail-closed hoặc local fallback** phải được thiết kế và ghi nhận cụ thể; trả một status nào còn phụ thuộc loại lỗi và hợp đồng dịch vụ.

### 9.4. Backoff với jitter

Khi nhiều client cùng bị rate limit, chúng có thể đồng loạt retry sau đúng một khoảng và tạo **thundering herd**. Client cần cân nhắc:

1. Tuân **Retry-After** nếu được cung cấp và phù hợp deadline.
2. Dùng **exponential backoff có jitter** khi không có hướng dẫn cụ thể.
3. Đặt **số lần thử tối đa**, tổng timeout/deadline và cơ chế hủy.
4. Với thao tác gây tác dụng phụ, dùng **idempotency key** hoặc cơ chế tránh chạy trùng được server hỗ trợ.
5. Không retry vô hạn với 401/403 hay một request payload chắc chắn không hợp lệ.

~~~text
Ví dụ backoff cơ bản (minh họa):
  base = 1 giây, cap = 30 giây
  delay_cap_n = min(30, 2^n)
  actual_delay = random(0, delay_cap_n)  # full jitter

Client vẫn phải tuân Retry-After và deadline riêng.
~~~

Phép tính minh họa không phải code thư viện production. Không giảm độ trễ bằng cách **tạo nhiều client identities/API keys** để bỏ qua quota theo hợp đồng.

### 9.5. Khi nào chờ, khi nào từ chối ngay?

Một gateway có thể **xếp hàng ngắn** các request có độ ưu tiên phù hợp, nhưng phải giới hạn hàng đợi và **tránh giữ kết nối lâu**. Với API tương tác, từ chối nhanh bằng 429 thường dễ kiểm soát hơn khi backend gần quá tải. Với batch jobs, một queue có quota và theo dõi trạng thái có thể hợp lý hơn.

**Từ chối nhanh không thay thế chống DDoS:** một cuộc tấn công chiếm băng thông upstream vẫn có thể làm nghẽn đường truyền trước khi HTTP gateway trả 429.

## 10. Local và distributed rate limiting

### 10.1. Khi API có nhiều instance

Giả sử API gateway có **4 instance**, mỗi instance độc lập cho tối đa **100 requests/phút/user**. Nếu client phân phối đều request tới cả bốn instance và mỗi instance chỉ giữ counter cục bộ, tổng số request có thể được cho phép xấp xỉ **400 requests/phút**, chứ không phải 100/phút cho toàn dịch vụ.

~~~mermaid
flowchart TD
    C["Client / verified identity"] --> LB["Load balancer"]
    LB --> G1["Gateway A / local counter"]
    LB --> G2["Gateway B / local counter"]
    LB --> G3["Gateway C / local counter"]
    LB --> G4["Gateway D / local counter"]
    G1 -. "Không tự chia sẻ state" .- G2
    G2 -. "Không tự chia sẻ state" .- G3
    G3 -. "Không tự chia sẻ state" .- G4
~~~

**Local rate limiter** hữu ích để bảo vệ gần nguồn, xử lý tốc độ cao hoặc làm lớp safety khi store chung bị lỗi. Tuy nhiên, nếu hợp đồng là **100 requests cho một user trên toàn cluster**, cần **shared state, consistent sharding hoặc cơ chế cấp phát budget toàn cục**.

### 10.2. Shared counter store

Một cách triển khai phổ biến là gateway dùng **shared store** hoặc **global rate-limit service**. State logic của một token bucket có thể gồm:

~~~text
Key:
  env=prod, service=orders,
  policy=v3, tenant=tenant-42,
  scope=GET:/api/orders

State:
  tokens=23.5
  last_refill_time=...
  capacity=100
  refill_rate=2/s
  ttl=...
~~~

Đây là ví dụ dữ liệu, không phải schema chuẩn Redis. **Version/namespace** giúp hạn chế nhầm counter khi đổi policy, nhưng cần quản lý TTL, migration và memory growth.

### 10.3. Atomicity và race condition

Hai gateway có thể xử lý cùng user **đồng thời**. Nếu đều đọc thấy một token cuối cùng rồi ghi lại, cả hai request có thể được allow và làm vượt hạn mức.

Một triển khai đúng cần operation cập nhật state **nguyên tử** theo khóa hoặc tập khóa liên quan, chẳng hạn atomic script/transaction được datastore hỗ trợ.

**Pseudocode token bucket trong một atomic operation:**

~~~text
function check_and_consume(key, now, cost, capacity, refill_rate):
    state = atomic_store.read(key)
    if state does not exist:
        tokens = capacity
        last_time = now
    else:
        elapsed = max(0, now - state.last_time)
        tokens = min(capacity, state.tokens + elapsed * refill_rate)
        last_time = now

    if cost > capacity:
        atomic_store.set(key, tokens, last_time, ttl)
        return REJECT_HARD_COST_LIMIT

    if tokens < cost:
        # refill_rate phải > 0 hoặc có xử lý riêng.
        wait_seconds = (cost - tokens) / refill_rate
        atomic_store.set(key, tokens, last_time, ttl)
        return REJECT(wait_seconds)

    tokens = tokens - cost
    atomic_store.set(key, tokens, last_time, ttl)
    return ALLOW
~~~

Đây là **giả mã**, chưa phải chương trình production. Một bản thực tế phải xử lý **refill_rate=0, timestamps lỗi, overflow, TTL, policy version, atomicity của nhiều keys và lỗi kết nối**. Thời gian cần lấy từ nguồn nhất quán với state update; không tin timestamp do client tự gửi.

### 10.4. Redis và TTL

Nếu dùng Redis hoặc một shared key/value store:

- Dùng thao tác **nguyên tử** cho kiểm tra và cập nhật budget.
- Áp **TTL hợp lý** để thu hồi buckets không hoạt động.
- Theo dõi **hot keys** (global/tenant), latency, memory, eviction và command errors.
- Với sharding/cluster, kiểm tra giới hạn của **atomic multi-key operations**; các khóa ở những shard khác nhau không tự tạo transaction chung.
- Không dùng raw API tokens/email nhạy cảm làm tên key hoặc metric label.
- Có kế hoạch failover và xác minh hành vi khi store unavailable.

**Một Redis instance trung tâm không tự bảo đảm high availability.** Nếu store được gọi cho mọi request, sự cố tại đây có thể trở thành sự cố của toàn API.

### 10.5. Quota theo nhiều region

Hệ thống multi-region có thể chọn:

1. **Regional budgets:** mỗi region cấp một phần quota; ít phụ thuộc cross-region latency nhưng có thể từ chối ở region này khi region khác còn quota.
2. **Global shared budget:** nhiều region phối hợp để tính chung; gần strict global contract hơn nhưng tăng độ trễ và phụ thuộc hạ tầng liên vùng.
3. **Budget leasing:** cấp trước một số tokens/quota cho từng region rồi cân đối; tăng khả năng sẵn sàng nhưng có thể có overshoot/underutilization tạm thời.

Ví dụ quota toàn cầu **1.000 units/phút** được phân **600 cho Region A, 400 cho Region B**. Nếu A đã dùng 600 còn B dùng 50, A có thể reject mặc dù toàn dịch vụ mới tiêu thụ 650. Muốn dùng phần quota còn lại cần cơ chế điều chuyển đủ an toàn.

### 10.6. Fail-open, fail-closed và local fallback

Khi shared limiter không sẵn sàng:

| Phương án | Hành vi | Đánh đổi |
| --- | --- | --- |
| **Fail-open** | Tạm cho qua dù chưa kiểm tra quota | Bảo vệ availability, tăng rủi ro lạm dụng và chi phí |
| **Fail-closed** | Tạm từ chối vì không xác minh được ngân sách | Bảo vệ operation nhạy cảm, nguy cơ outage |
| **Local fallback** | Áp hạn mức riêng tại gateway | Giữ một lớp phòng vệ nhưng có thể vượt strict global quota |
| **Degraded mode** | Chỉ cho thao tác ưu tiên, giảm quota hoặc tạm hoãn job | Cân bằng availability/tài nguyên, đòi hỏi policy rõ |

Không áp một fail policy cho mọi route: **GET công khai**, **gửi OTP trả phí**, **thanh toán** và **thao tác quản trị** có rủi ro khác nhau. Nếu store lỗi, một request được từ chối **không nhất thiết là vì client đã vượt quota**; phải thể hiện đúng nguyên nhân trong telemetry và xử lý theo hợp đồng API.

### 10.7. Clock skew và counter consistency

Các limiter có thể tính sai khi:

- Đồng hồ gateway/region lệch nhau hoặc client tự gửi timestamp.
- Counter replication trễ, race condition hoặc store failover làm mất state.
- Cache eviction khiến bucket được tạo lại ở trạng thái đầy.
- Chính sách capacity/refill thay đổi trong khi bucket cũ chưa hết TTL.
- Một request bị retry sau timeout nhưng lần đầu đã trừ quota.

Cần chọn nguồn thời gian được kiểm soát, giới hạn drift, có chính sách đổi version và theo dõi các sự kiện **counter reset, partial reservation, duplicate charge** để vận hành minh bạch.

## 11. Ví dụ Nginx: IP-based rate limit tại reverse proxy

Nginx HTTP module có **limit_req_zone** để khai báo shared memory zone, khóa và rate, cùng **limit_req** để áp chính sách tại ngữ cảnh được hỗ trợ. Ví dụ dưới minh họa **giới hạn theo IP tại một Nginx deployment**, chưa phải per-user/tenant limit dựa trên danh tính đã xác minh.

### 11.1. Cấu hình lab

~~~nginx
# Ví dụ dùng trong nginx.conf có context http.
# Backend lab chạy loopback 127.0.0.1:8080.
http {
    upstream lab_api {
        server 127.0.0.1:8080;
    }

    # Một bucket cho mỗi địa chỉ nguồn mà Nginx xác định.
    limit_req_zone $binary_remote_addr zone=api_per_ip:10m rate=10r/s;

    server {
        listen 127.0.0.1:8088;
        server_name api.lab.example;

        # Mặc định limit_req dùng 503; minh họa đổi thành 429.
        limit_req_status 429;

        location /api/ {
            limit_req zone=api_per_ip burst=20 nodelay;
            proxy_pass http://lab_api;
        }
    }
}
~~~

**Diễn giải:**

- **$binary_remote_addr** là địa chỉ peer theo semantics Nginx. Nếu Nginx ở sau CDN/LB, đây có thể là IP của proxy trước, không phải client cuối.
- **zone=api_per_ip:10m** là tên/dung lượng shared memory state, **không phải giới hạn 10 MiB request body**.
- **rate=10r/s** là tốc độ xử lý/ghi nhận theo thuật toán leaky bucket của module; không phải fixed window “10 request ở đầu mỗi giây”.
- **burst=20 nodelay** cho phép burst vượt tốc độ nền được xử lý không trì hoãn trong giới hạn được cấu hình; vượt nữa có thể bị reject.
- **limit_req_status 429** đổi HTTP status từ chối của module theo ngữ cảnh đang áp dụng.

Không coi đây là cấu hình production. Nó chưa có **TLS, verified identity, bảo vệ endpoint login, quan sát phân tán, authz, WAF, header handling và high availability**.

### 11.2. Nginx ở sau CDN và rủi ro XFF

Nếu CDN chuyển mọi traffic qua một vài IP edge, limiter theo remote_addr có thể khiến khách dùng chung bucket. Có thể cấu hình **real IP module** để lấy IP client từ metadata đã được ingress tin cậy, nhưng chỉ khi:

1. Có danh sách **trusted proxy addresses/networks** chính xác.
2. Edge xóa/ghi đè header nguồn từ client và quản trị chain đúng cách.
3. Backend không thể bị gọi trực tiếp bằng đường đi bỏ qua CDN.
4. Mọi proxy hop xử lý IPv4/IPv6 nhất quán.

**Ví dụ không an toàn — không triển khai:**

~~~nginx
# X-Forwarded-For có thể do client tự chọn nếu không được chuẩn hóa.
# Không dùng raw header như security identity.
limit_req_zone $http_x_forwarded_for zone=unsafe:10m rate=10r/s;
~~~

Nếu client thay header trên mỗi request, hệ thống có thể tạo hàng nghìn buckets hoặc tránh giới hạn theo nguồn. Vấn đề không phải bản thân header XFF xấu mà là **tin dữ liệu từ bên ngoài ranh giới bảo vệ**.

### 11.3. Nginx local khác global limit

Shared memory zone thường chia sẻ giữa các **worker trên cùng một Nginx instance**, không tự đồng bộ giữa nhiều gateway hosts. Nếu có ba ingress replicas, một rule giống nhau trên ba máy **không đồng nghĩa** strict global quota.

Để giới hạn theo **user/client/tenant đã xác thực** và shared state, cần cơ chế ở **API gateway/auth middleware/global limiter** phù hợp. Không lấy một user ID thô do Internet client tự gửi rồi đặt làm key trong limit_req_zone.

### 11.4. Validation khi triển khai

Trong lab có Nginx và quyền đọc cấu hình:

~~~bash
# Chỉ kiểm tra cú pháp và tham chiếu cấu hình.
nginx -t
~~~

**nginx -t thành công chưa chứng minh rate limit hoạt động đúng.** Cần gửi các request thử nghiệm có kiểm soát, xem status/log, kiểm tra location match, tải cục bộ, đường proxy thật, trạng thái reload và hành vi trên các replicas.

## 12. Policy mẫu cho API nhiều tenant

Bảng dưới là **con số luyện tập**, không phải khuyến nghị cố định cho production.

| Route / nghiệp vụ | Khóa primary | Budget minh họa | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| **GET /public/catalog** | Verified client IP trước auth | 120 requests/phút/IP | Edge global, cache, response-size limit |
| **POST /auth/login** | IP/source + account được yêu cầu | 10 attempts/phút/source cùng ngưỡng bảo vệ account | Chống enumeration, MFA, theo dõi spraying |
| **POST /auth/send-otp** | Account/session theo policy | 3 sends/10 phút/account | Chi phí SMS, anti-abuse, khôi phục hợp lệ |
| **GET /api/products** | Verified user + tenant | 100 requests/phút/user | Tenant aggregate và pagination |
| **POST /api/orders** | User + tenant + operation | 30 operations/phút/user | Authz, idempotency, giao dịch |
| **POST /api/search** | Tenant + weighted cost | 500 units/phút/tenant | Query depth/rows/timeout |
| **POST /api/reports/export** | Tenant + user | 2 jobs đồng thời/user | Queue, job timeout, quota |
| **Service-to-service inventory API** | Verified workload identity | Theo hợp đồng của service | mTLS, retry budget, safety cap |

### 12.1. Login và rủi ro khóa tài khoản hộ người khác

Nếu policy **hard-lock account sau 5 lần sai** mà bất cứ người nào cũng có thể gửi username, một tác nhân xấu có thể cố ý khiến người dùng hợp lệ bị khóa. Rate limiting bảo vệ auth nhưng cũng có thể tạo **denial of service theo tài khoản** nếu thiết kế thô.

Cần cân nhắc:

1. Giới hạn theo nguồn và phát hiện pattern password spraying **trên nhiều accounts**.
2. Chậm dần hoặc **risk-based challenges** theo IdP, thay vì khóa cứng vô điều kiện.
3. Hạn chế tiết lộ account existence từ mã lỗi/thời gian phản hồi.
4. Xác minh trạng thái MFA, client/device và login context.
5. Cơ chế khôi phục tài khoản hợp lệ khi người dùng bị chặn oan.

Giới hạn theo account chưa được xác thực phải xử lý **input chuẩn hóa và case folding theo chính sách nhận dạng**, tránh tạo nhiều buckets cho cùng tài khoản hoặc để client chọn khóa tùy ý.

### 12.2. Rotation API key không được nhân quota

Khi một client thay API key, bucket per-key có thể khởi tạo mới. Nếu muốn kiểm soát tổng ngân sách của tích hợp, **client/tenant budget** phải bao phủ cả key cũ và mới trong giai đoạn rotation. Key rotation là thực hành tốt, không phải cách nhận thêm quota ngoài hợp đồng.

### 12.3. Route canonicalization

Một API có thể xuất hiện dưới những đường dẫn:

~~~text
/api/v1/orders
/api/v2/orders
/API/v1/orders
/api/v1/orders/
/api/v1/orders?limit=1000
~~~

Đừng tự coi các URL này chắc chắn trùng hoặc khác route. Proxy, framework và backend có thể xử lý **chữ hoa/thường, slash, percent-encoding, query string và rewrite** khác nhau. Nên áp key theo **route ID / operation ID được server xác định sau canonicalization đáng tin**, thay vì dùng nguyên URL do client cung cấp khiến số bucket tăng vô hạn hoặc tạo đường bypass.

### 12.4. Global safety guard và gói dịch vụ cao cấp

Tenant doanh nghiệp có thể có rate/quota cao hơn, nhưng vẫn cần **global safety guard, concurrency cap, request cost cap và backend overload protection**. Việc trả phí không nên làm một token bị lộ có thể tiêu thụ vô hạn CPU/DB hoặc làm gián đoạn các tenant khác.

## 13. Threat modeling: Lạm dụng API và né rate limit

### 13.1. Những tình huống cần bảo vệ

| Tình huống | Vì sao limiter đơn giản có thể thiếu? | Kiểm soát bổ sung |
| --- | --- | --- |
| **Brute force** trên một account | Attacker đổi source IP | Counter/risk policy theo account cùng source |
| **Password spraying** trên nhiều accounts | Per-account threshold ít bị chạm | Phân tích nguồn, mẫu thời gian, nhiều account, global auth budget |
| **Credential stuffing phân tán** | Nhiều IP/ASN/thiết bị tham gia | Bot/risk signals, MFA, identity-aware detection và upstream protection |
| **Token/API key rotation để né cap** | Mỗi key mới có bucket mới | Verified client/tenant parent budget |
| **XFF spoofing** | Header nguồn do client tự đặt | Trusted proxy chain và normalization tại ingress |
| **IPv6 source rotation** | Mỗi /128 một bucket | Phân nhóm theo kiến trúc prefix khi phù hợp và identity budget |
| **Path encoding/case bypass** | Raw URL khác nhưng backend cùng operation | Canonical route ID và policy ở mọi biến thể route |
| **Bypass CDN qua origin IP** | Limiter chỉ có ở edge | Origin ACL/private link, gateway enforcement, IPv6 |
| **API batch amplification** | Một request thực hiện hàng trăm hành động | Weighted operation cost, batch/field count cap |
| **GraphQL deep query** | Body nhỏ nhưng tốn CPU/DB | Complexity/depth/timeout cap |
| **Retry storm** | Clients cùng retry khi lỗi 429/503 | Retry-After, jitter, retry budget, circuit breaker |
| **Shared NAT gây false positive** | Nhiều users dùng một IP | Post-auth identity limits, ngân sách edge hợp lý |
| **WebSocket/gRPC streaming abuse** | Một kết nối chở nhiều messages | Per-message/cost limits, concurrent streams và duration |
| **High-cardinality bucket exhaustion** | Client gửi vô số giá trị key tự khai | Verified/normalized keys, key TTL, cap số buckets và memory |

**Không có “một thuật toán chống mọi bot”.** Token bucket, rate limit theo nguồn và WAF có thể giảm một số kiểu abuse nhưng một tác nhân phân tán vẫn có thể dùng nhiều identity hợp lệ hoặc hoạt động dưới ngưỡng của từng bucket. Cần kết hợp **phân tích hành vi, danh tính, authorization, upstream mitigation và observability**.

### 13.2. Bypass bằng API key/identity giả

Một API nhận khóa trong header có thể phân biệt:

- **Raw API key:** bí mật dùng để chứng minh quyền, tuyệt đối không dùng làm metric label hoặc error response.
- **API key ID:** định danh được tìm từ bản ghi key sau xác minh; có thể dùng làm limiter key.
- **Client application ID:** định danh ứng dụng được ánh xạ từ key/token và auth policy.
- **Tenant ID:** định danh tổ chức chủ quản key đã được hệ thống tin cậy xác nhận.

Nếu frontend tự gửi tenant ID mà gateway chưa kiểm tra nó có thuộc về principal đã xác thực không, attacker có thể **dịch chuyển request sang bucket của tenant khác** hoặc tạo bucket vô hạn. **Đối tượng của limiter phải đi từ kết quả authorization/identity mapping**, không phải tham số tùy ý.

### 13.3. Denial of wallet và quota có thể trở thành vũ khí

Một API được tính tiền theo request hoặc operation có thể bị lạm dụng để tăng chi phí (ví dụ gửi OTP/SMS, truy vấn dữ liệu có phí, gọi AI model, tạo report). Rate limiting và quota cần tính đúng **cost thực tế**, phân biệt attempts với billable operations và có budget bất biến ở mức account/tenant.

Ngược lại, kẻ xấu có thể **cố ý làm hết quota của người khác** nếu hệ thống trừ token của tenant chỉ dựa trên tenant ID tự khai trước khi xác thực. Hãy kiểm tra identity binding và bảo đảm những failure không được phép bị tính vào quota của nạn nhân.

### 13.4. Hạn mức an ninh và chống DDoS là các phạm vi khác nhau

- **Volumetric DDoS:** có thể bão hòa đường truyền tới origin trước khi proxy trả 429; cần upstream/CDN/ISP.
- **L7 high-rate abuse:** có thể được kiểm soát bằng edge/WAF/API rate limits và auth.
- **Low-and-slow:** không nhất thiết vượt RPS; cần timeout, connection/stream caps và resource monitoring.
- **Expensive requests:** request rate thấp nhưng cost cao; cần backend cost/concurrency budgets.

Một chiến lược tốt phối hợp **network protection và application-aware limits**, đồng thời phân biệt tác động tới client hợp lệ.

## 14. Observability: Biết limiter đang bảo vệ hay đang chặn nhầm

### 14.1. Các trường log nên có

Một sự kiện rate limit được chuẩn hóa có thể chứa:

| Trường | Mục đích | Bảo mật |
| --- | --- | --- |
| event_time_utc, service, environment, region | Xác định thời điểm và scope | Đồng bộ clock |
| request_id / trace_id | Đối chiếu proxy, gateway, backend | Không dùng request ID như bằng chứng danh tính |
| route_id / operation_id | Biết nhóm chức năng bị hạn chế | Tránh ghi raw path có PII không cần thiết |
| authenticated_principal_type | user, service, API key, tenant | Không lộ raw tokens |
| limiter_key_type | IP / user / client / tenant / operation | Có thể hash/pseudonymize key value |
| policy_id, policy_version | Xác định ngưỡng đang có hiệu lực | Cần bảo vệ quyền sửa policy |
| algorithm, cost, capacity, available_budget | Giải thích quyết định | Không công khai hết nội bộ cho client |
| decision, reject_reason, status | ALLOW/REJECT/DELAY/fallback | Phân biệt lỗi store với thực sự quá hạn |
| upstream_request_status | Có chuyển request đến backend không | Tránh nhầm nguồn HTTP 429 |
| verified_client_ip / proxy context | Tìm lỗi source IP trust | IP có thể là dữ liệu cá nhân |
| store_latency / fallback_mode | Chẩn đoán outage limiter | Giám sát hot key và region |

**Không ghi Authorization header, cookie, raw API key, OTP, mật khẩu hoặc toàn bộ request body** vào log rate limiting. Các trường IP, session và user có thể liên quan tới cá nhân; cần retention, audit và quyền truy cập theo chính sách.

### 14.2. Ví dụ log minh họa

~~~json
{
  "event_time_utc": "2026-11-28T10:00:00Z",
  "service": "orders-api-lab",
  "region": "lab-a",
  "request_id": "req-lab-0042",
  "route_id": "POST:orders",
  "limiter_key_type": "verified_user",
  "subject_ref": "anon-user-07",
  "policy_id": "order-write-v3",
  "algorithm": "token_bucket",
  "request_cost": 1,
  "decision": "REJECT",
  "reject_reason": "budget_exhausted",
  "http_status": 429,
  "retry_after_seconds": 4,
  "limiter_store": "shared",
  "upstream_forwarded": false
}
~~~

Đây là **log giả lập**, không phải schema thực tế của nhà cung cấp. Định danh user đã được ẩn danh, không có API secret hoặc token.

### 14.3. Metric nên theo dõi

| Chỉ số | Mục đích | Điều cần tránh |
| --- | --- | --- |
| **Allow/deny counts theo policy/route** | Theo dõi tác động của giới hạn | Không coi mọi deny là tấn công |
| **429 rate và top affected routes** | Phát hiện sai policy hoặc client abuse | Phân biệt tầng nào tạo 429 |
| **Budget utilization / reject reason** | Xác định bucket nào hết | Không trộn budget theo các đơn vị khác nhau |
| **p50/p95/p99 limiter lookup latency** | Giám sát chi phí middleware | Limiter chậm làm toàn API chậm |
| **Limiter store errors/fallbacks** | Phát hiện fail-open/closed | Không đánh đồng lỗi store với quota exhausted |
| **Counter keys và memory usage** | Phát hiện high-cardinality/eviction | Không để vô số metric labels theo user ID |
| **Retry traffic/attempt amplification** | Đo retry storm | Phân biệt retries với operations mới |
| **Authenticated active identities / NAT context** | Phân tích công bằng | IP không bằng user |
| **Backend saturation: CPU/DB pool/queue/5xx** | Kiểm tra limiter thực sự giảm tải | 429 giảm không đồng nghĩa backend khỏe |
| **Appeals/tickets/FP vs verified abuse** | Đánh giá chất lượng policy | Cần ground truth, không kết luận từ dashboard |

**High-cardinality metrics:** không thêm một metric label riêng cho **mỗi user/IP/token** trên toàn bộ thời gian dài. Điều đó có thể làm bùng nổ chi phí và tài nguyên của hệ thống metrics; dùng thống kê tổng hợp, log tìm kiếm có kiểm soát hoặc sampling khi cần.

### 14.4. False positive và false negative

**False positive (FP) vận hành** trong ngữ cảnh này có thể hiểu là request bị giới hạn nhưng hành vi được xác minh là hợp lệ và nằm trong nhu cầu/policy mong muốn. **False negative (FN)** là hành vi cần ngăn theo threat model vẫn qua được vì route/key/counter/coverage sai.

| Tình huống | Loại lỗi | Hướng khắc phục |
| --- | --- | --- |
| 50 nhân viên chung NAT bị chặn khi mỗi người dùng ít | FP | Post-auth user limits và edge NAT-aware budget |
| Mỗi API key được quota mới, client tạo nhiều keys | FN | Parent budget theo verified client/tenant |
| IPv6 /128 thay đổi liên tục bỏ qua source cap | FN | IPv6 policy và identity controls phù hợp |
| Auth service lỗi khiến login thất bại hàng loạt | FP nếu cảnh báo nhầm bot | Tương quan IdP outage/reason codes |
| Route /api/v2 mới quên gắn limiter | FN | Policy-as-code và route coverage tests |
| Client gửi batch lớn nhưng chỉ tốn một token | FN | Weighted cost và batch constraints |
| Người dùng upload lớn hợp lệ nhưng body cap quá thấp | Không phải rate limit FP trực tiếp | Chỉnh size limit theo hợp đồng khác |

**Một kết quả 429 không tự là false positive** nếu hợp đồng đã công bố giới hạn và client thực sự vượt ngưỡng, kể cả người dùng không thích bị chặn. Khi đánh giá FP phải có **tiêu chuẩn và ground truth được định nghĩa**.

## 15. Triển khai theo giai đoạn và quản trị thay đổi

### Bước 1 — Chọn tài nguyên và use case

Xác định API công khai, login/MFA, endpoint đắt tiền, internal services, service accounts và tenant có cam kết riêng. Cần có owner của mỗi route/operation, công suất backend và giả định về client behavior.

### Bước 2 — Xác lập danh tính đáng tin

Kiểm tra điểm kết thúc TLS, chuỗi trusted proxies, cơ chế xác thực JWT/API key/mTLS, tenant mapping và quyền truy cập. Đừng tạo counter dựa trên header hoặc account string chưa xác minh.

### Bước 3 — Chọn key, phạm vi và thuật toán

Định nghĩa **key hierarchy**, algorithm, refill/window, burst, cost, concurrency, scope region/global và hành vi với unauthenticated/unknown identities.

### Bước 4 — Xác định quota/budget dựa trên dữ liệu

Đo tải hợp lệ, traffic pattern, cao điểm, phân bố NAT và những operation hiếm nhưng cần thiết. Đối chiếu backend concurrency, DB pool, downstream rate limits và yêu cầu hợp đồng. Không chọn một con số tùy tiện chỉ vì cấu hình ví dụ dùng con số ấy.

### Bước 5 — Chạy quan sát

Nếu nền tảng cho phép **shadow mode / log-only**, ghi nhận các request **sẽ bị giới hạn** nhưng chưa từ chối, để phân tích false positives. Phải hạn chế chi phí ghi log và bảo đảm quan sát không làm tăng thời gian đáp ứng quá mức.

### Bước 6 — Kiểm thử và rollout

Thực hiện thử ranh giới theo thuật toán, login/tenant/API key, NAT/IPv6, concurrency, global store outage, nhiều gateway và route bypass. Bật enforcement theo canary hoặc traffic slice có kế hoạch, giám sát **429, 5xx, latency, retry storms và ticket hỗ trợ**.

### Bước 7 — Rollback có điều kiện

Có version policy cũ, ngưỡng được phê duyệt, cách tắt riêng một rule mà vẫn giữ **global safety guard**, và cảnh báo khi store lỗi. **Không vô hiệu hóa tất cả limiter** chỉ để khôi phục một route, nếu có thể giảm phạm vi và duy trì phòng vệ cơ bản.

### Bước 8 — Rà soát định kỳ

Khi thêm route, đổi tier, tăng số replica, thay CDN hoặc chuyển IPv6/region, cần chạy lại route coverage tests. Xóa exception hết hạn, theo dõi identity spoofing và sửa client retry behavior khi cần.

## 16. Bài thực hành lab: Kiểm tra limit theo IP và identity

**Phạm vi:** chỉ dùng một API gateway/service ở máy lab hoặc môi trường đã được cấp quyền. Không gửi burst lớn, không thử password guessing vào tài khoản thật và không kiểm tra giới hạn của dịch vụ công cộng mà bạn không được phép đánh giá.

### 16.1. Bài A — Mô phỏng token bucket trên giấy

Giả định một bucket có:

~~~text
Capacity:          5 tokens
Refill rate:       1 token / giây
Request cost:      1 token
Initial tokens:    5
Time origin:       t = 0 giây
~~~

| Thời điểm | Yêu cầu | Token trước xử lý | Kết quả | Token sau |
| --- | --- | --- | --- | --- |
| t = 0 | 3 requests gần như cùng lúc | 5 | 3 allow | 2 |
| t = 0 | 3 requests nữa | 2 | 2 allow, 1 reject | 0 |
| t = 2 | 1 request | 2 (refill 2) | 1 allow | 1 |
| t = 2 | 2 requests nữa | 1 | 1 allow, 1 reject | 0 |
| t = 6 | 5 requests gần như cùng lúc | 4 (refill 4) | 4 allow, 1 reject | 0 |

**Giải thích:** tại t=6, nếu không có traffic từ t=2, bucket nhận thêm 4 token; vì capacity=5 và trạng thái trước đó bằng 0, lượng còn lúc đó là 4. Không có “reset mọi giây”. Nếu request cost lớn hơn 1, các kết quả cần tính lại theo số token tương ứng.

### 16.2. Bài B — Fixed window và burst boundary

Giới hạn **5 requests/10 giây** theo fixed windows [0,10), [10,20):

~~~text
t = 9.90 giây: 5 requests -> allow (đủ 5 trong window đầu)
t = 10.01 giây: 5 requests -> allow (window mới)

Tổng 10 requests trong khoảng thời gian ~0,11 giây,
dù bảng cấu hình ghi 5 requests mỗi 10 giây.
~~~

**Bài học:** nếu endpoint quá nhạy cảm với burst ngắn, fixed window đơn thuần có thể không đáp ứng mục tiêu. Có thể dùng token bucket, sliding window hoặc lớp concurrency/in-flight guard.

### 16.3. Bài C — Mô hình giới hạn theo danh tính

Giả sử hai user **A** và **B** cùng đi qua một public IP của văn phòng:

~~~text
Shared IP: 198.51.100.50 (địa chỉ ví dụ)
Per-IP edge budget:      50 requests/phút
Per-user budget A:       20 requests/phút
Per-user budget B:       20 requests/phút
Tenant shared budget:   100 requests/phút
~~~

Trong cùng một phút, A gửi **18 requests** và B gửi **17 requests**: tổng **35** nên chưa chạm ngưỡng per-IP=50 hay các user budgets. Nếu A gửi thêm **5 requests**, giới hạn user A có thể từ chối **3 requests** dù edge IP còn room. Nếu một nhóm 100 người cùng dùng IP ấy, **per-IP budget 50** có thể chặn người dùng hợp lệ ngay cả khi budget từng user chưa hết. Điều này cho thấy **các hạn mức độc lập có tác động kết hợp**.

Địa chỉ **198.51.100.50** chỉ dành cho tài liệu (RFC 5737), không phải IP truy cập tới một hệ thống ngoài thực tế.

### 16.4. Bài D — Thử Nginx trên loopback

Trong một Nginx lab đã cấu hình **đúng route**, bạn có thể dùng mức rất thấp để thử:

~~~nginx
# Chỉ là biến thể test ngưỡng thấp của ví dụ ở mục 11.
# Đặt trong http, không tự đưa vào production.
limit_req_zone $binary_remote_addr zone=lab_very_small:1m rate=1r/s;

# Đặt trong server/location được phép.
limit_req_status 429;
limit_req zone=lab_very_small burst=1 nodelay;
~~~

Sau khi **người vận hành lab** đã cấu hình và áp dụng thay đổi đúng quy trình, một script thử nhỏ trên loopback:

~~~bash
# Tối đa 5 request tuần tự trong lab; không dùng cho Internet.
for i in 1 2 3 4 5; do
  curl --silent --output /dev/null \
       --write-out "request=$i http=%{http_code}\n" \
       --max-time 3 \
       http://127.0.0.1:8088/api/ping
done
~~~

Kết quả status phụ thuộc thời gian thực giữa các lệnh, upstream route và các policy khác; **không hứa một dãy cố định 200/429**. Cần đối chiếu access/error log và tránh gán 404/401 của backend thành lỗi limiter. Lệnh này chỉ gửi **5 request** tới loopback, phù hợp kiểm tra sơ bộ; không phải stress test hay phép đo thông lượng.

### 16.5. Ma trận test quan trọng hơn một script

| Test case | Cách mô phỏng trong lab | Kỳ vọng |
| --- | --- | --- |
| Dưới limit | Các request hợp lệ không quá ngân sách | Không bị limiter từ chối |
| Đúng ngưỡng | Sử dụng hết budget mà không vượt | Quyết định đúng thuật toán đã chọn |
| Vượt ngưỡng | Thêm 1 request có cost hợp lệ | 429/reject theo policy |
| Refill/window reset | Chờ đúng khoảng rồi thử lại | Budget được phục hồi như thiết kế |
| Hai user sau NAT | A và B có user identities khác nhau, cùng outer IP | Per-user budgets riêng; edge budget vẫn chung |
| Một user nhiều API keys | Hai keys cùng client/tenant | Parent budget không bị bỏ qua |
| Header IP/User giả | Gửi metadata không đáng tin qua lab ingress | Không thay đổi verified limiter key |
| IPv6 addresses thay đổi | Hai IPv6 nguồn được phép trong lab | Áp chính sách nhóm/identity đúng |
| Hai gateway replicas | Cùng user gửi request qua cả hai | Global limit chính xác theo mode đã công bố |
| IdP hoặc limiter store lỗi | Mô phỏng dependency failure trong lab | Fail policy/fallback và telemetry đúng |
| Route mới hoặc rewrite | Cùng operation qua đường dẫn khác | Không bypass theo URL biến thể |
| GraphQL/batch | Một request có nhiều operations | Cost tính theo nội dung/operation |
| Concurrent jobs | Nhiều export jobs nhỏ có quyền | Giới hạn số job đang chạy |
| Retry sau 429 | Client tôn trọng Retry-After, jitter | Không tạo storm hoặc retry vô hạn |
| gRPC/WebSocket | Các messages trên một connection lab | Rate/cost theo message hoặc operation phù hợp |

### 16.6. Test khác biệt giữa IP và identity

Kiểm thử đơn giản theo tình huống giả định:

1. Hai phiên đã xác thực khác user ID, dùng cùng địa chỉ NAT. Xác nhận limiter biết phân biệt **user identity** nhưng vẫn tính chung nếu edge IP budget bị chạm.
2. Một user sử dụng hai API keys nhưng cùng **verified tenant**. Xác minh tenant budget chung.
3. Một request chưa xác thực gắn **X-User-ID: admin**. Xác minh request **không được hưởng quota của admin** và không chặn quota người đó.
4. Thay source IP tại network simulator hoặc hai client lab hợp lệ. Xác minh identity limit không reset nếu user vẫn là một.
5. Thử token bị vô hiệu hóa: gateway phải **không dùng claim từ token không hợp lệ** làm identity đã xác minh.

Không cần thử tấn công trên Internet hay gửi rất nhiều request để kiểm chứng logic khóa. Một bộ **identity fixtures và logs** có thể chứng minh sai lệch chính sách mà không gây ảnh hưởng người dùng thật.

## 17. Xử lý sự cố rate limiting

~~~mermaid
flowchart TD
    A["Client báo lỗi 429 hoặc API chậm"] --> B{"Xác định tầng trả status"}
    B --> C["CDN/WAF, proxy, gateway hay backend?"]
    C --> D{"Policy/bucket nào quyết định?"}
    D --> E["Kiểm tra verified key: IP, user, client, tenant"]
    E --> F{"Client thật sự vượt budget?"}
    F -->|Có| G["Xem traffic/retry/burst, quota hợp đồng"]
    F -->|Không hoặc không chắc| H["Kiểm tra NAT, headers, route, store, reset, replica"]
    G --> I["Điều chỉnh client behavior hoặc policy theo owner"]
    H --> I
    I --> J["Retest allow/deny + latency + backend health"]
~~~

### 17.1. Một IP bị 429 dù mỗi người dùng ít

**Khả năng:** nhiều người dùng chung NAT hoặc API gateway đang dùng IP của CDN làm key. Kiểm tra **remote peer, verified client IP, trusted proxies**, số users cùng nguồn và route. Giải pháp không phải bỏ hết rate limiting mà là **đặt budget edge hợp lý và dùng verified identity sau auth**.

### 17.2. Một user vượt quota khi gửi qua nhiều node

**Khả năng:** counter local, không shared state, sticky session khiến kết quả khác nhau, hoặc quota bị trừ hai lần khi retry. Kiểm tra **gateway instance, request IDs, store key, policy version và điều kiện atomicity**.

### 17.3. Tài khoản bị 429 dù không gửi nhiều request

**Khả năng:** API key/tenant dùng chung, một ứng dụng nền đang retry, user bị chia sẻ session, quota tính theo **weighted cost** chứ không phải request count, hoặc một kẻ xấu có token hợp lệ.

**Kiểm tra:** cost breakdown, source/device, các keys liên quan, log ứng dụng, quyền hoạt động và thời gian. Không kết luận kẻ xấu chỉ dựa trên counter tăng.

### 17.4. Client tiếp tục nhận 429 dù đã chờ

**Khả năng:** có nhiều buckets (IP, user, tenant, global) và chỉ một bucket được client nhìn thấy; Retry-After không phản ánh tất cả; client khác đang tiêu budget chung; thời gian/refill không được cập nhật do store lỗi.

**Kiểm tra:** policy ID, all applicable budgets, retry-after calculation, remaining/reset semantics, clock drift và request cost. **Retry-After là hướng dẫn thời gian**, không phải giấy đảm bảo request được phép khi đúng giây đó.

### 17.5. Tăng replicas lại làm vượt quota

**Khả năng:** limiter chỉ theo từng instance. Việc scale từ 2 lên 5 gateway làm tổng allowance tăng nếu client cân bằng tải qua nhiều nodes. Cần quyết định **strict global vs local safety** và cấu hình shared-state/allocated budgets phù hợp.

### 17.6. 429 tăng ngay sau một lần deploy

**Khả năng:** policy mới áp ngưỡng thấp hơn, route mapping thay đổi, store key namespace đổi làm reset state, batch cost được tính lại, một node dùng cấu hình sai hoặc client mới tạo retry loop.

**Hướng xử lý:** đối chiếu **policy version, deploy timestamp, per-route metrics và backend health**. Cân nhắc rollback rule ảnh hưởng riêng thay vì tắt toàn bộ bảo vệ.

### 17.7. Backend vẫn quá tải dù limiter báo allow hợp lệ

**Khả năng:** requests rất đắt về CPU/DB, connection concurrency cao, queue dài, cache miss, downstream quota, payload lớn hoặc DDoS không đi qua limiter.

**Hướng xử lý:** xem **per-operation cost cap, concurrency, body size, timeouts, cache, WAF/edge và khả năng backend**. Một RPS cap không thể thay thế capacity planning.

### 17.8. Không còn 429 sau khi store bị lỗi

**Khả năng:** limiter đang fail-open. Đây có thể là hành vi được thiết kế cho availability, nhưng phải có **fallback, metric và cảnh báo**. Không kết luận traffic đã “trở lại bình thường” khi counter store đang unavailable.

### 17.9. API trả 503 khi bị giới hạn bởi Nginx

**Khả năng:** Nginx limit_req module sử dụng **status mặc định 503** nếu không thay đổi policy trả status. Khi API cần 429, có thể cấu hình **limit_req_status 429** theo ngữ cảnh được hỗ trợ và kiểm tra lại.

**Không mặc định mọi 503 là rate limiting:** 503 còn có thể do upstream outage, maintenance hoặc backend overload.

## 18. Tình huống tổng hợp: API đa tenant và một sự cố chặn oan

**Bối cảnh:** doanh nghiệp phục vụ ba nhóm:

- **Khách chưa đăng nhập** gọi catalog công khai.
- **Nhân viên đã đăng nhập** dùng trang quản lý đơn hàng.
- **Ứng dụng đối tác** gọi API bằng API keys đã được xác minh, thuộc các tenant.

Hạ tầng: **CDN/WAF → Nginx reverse proxy → API gateway/IdP → hai backend instances → Redis/DB**.

Policy ban đầu:

~~~text
CDN:
  50 requests/minute per observed IP

Nginx:
  100 requests/minute per remote_addr

API gateway:
  60 requests/minute per API key

No tenant-level aggregate budget
No explicit concurrency cap for report exports
~~~

### 18.1. Sự kiện quan sát

1. Một văn phòng đối tác có **80 người dùng chung public IP** bắt đầu bị trả 429 mặc dù mỗi người chỉ truy vấn vài lần.
2. Một hệ thống tích hợp thay API key liên tục nên có vẻ không chạm hạn mức per-key.
3. Endpoint **/reports/export** chỉ có 20 requests/phút nhưng backend liên tục quá tải do nhiều job đắt tiền đồng thời.
4. Sau khi scale Nginx từ 2 lên 4 nodes, số requests được chấp nhận tăng bất thường.
5. Một số requests trực tiếp tới hostname origin không qua CDN vẫn được backend xử lý.

### 18.2. Phân tích nguyên nhân

| Quan sát | Phân tích | Hướng giải quyết |
| --- | --- | --- |
| Nhiều user chung IP bị chặn | Per-IP cap ở edge quá thấp cho NAT | Tinh chỉnh guard theo nguồn; thêm verified identity budget |
| API key rotation giúp tăng allowance | Chỉ có per-key, thiếu parent tenant/client | Thêm tenant aggregate và verified app identity |
| Report export làm quá tải | RPS không đo chi phí jobs đang chạy | Concurrency, queue, cost/job quota |
| Scale nodes làm allowance tăng | Local counters độc lập | Shared/global limiter hoặc phân bổ budget nhất quán |
| Origin bypass CDN | Chỉ edge enforcement không phủ mọi đường | Origin ACL/private connectivity và gateway enforcement |

### 18.3. Policy cải tiến ở mức kiến trúc

1. **CDN/WAF** áp coarse burst protection theo source và các tín hiệu hạ tầng có độ tin cậy; không dùng IP làm identity nghiệp vụ duy nhất.
2. **Nginx** có local safety guard nhưng sử dụng source IP được xác định đúng chuỗi proxy.
3. **Gateway** xác minh token/key, lấy user/client/tenant ID đáng tin và dùng shared counter.
4. **Service** giới hạn cost, đồng thời số export jobs, batch size, DB query complexity.
5. **Redis/store** có atomic operations, HA/fallback rõ, tránh raw secrets và unbounded key growth.
6. **Observability** gắn request ID, policy ID, reject reason, tầng tạo 429 và tác động tới khách.
7. **Network firewall** hạn chế direct access tới origin, bảo vệ IPv4/IPv6 và các đường route phụ.

### 18.4. Kết quả nghiệm thu mong đợi

- Hai user cùng NAT được **hưởng per-user budget độc lập** sau auth, trong khi edge guard vẫn giới hạn tổng tải hợp lý.
- Nhiều API keys cùng tenant **không làm tăng tenant aggregate budget**.
- Thêm replicas **không tự tăng strict global quota**.
- Một report job tốn tài nguyên bị hạn chế bởi **concurrency/cost**, dù RPS thấp.
- Client xử lý 429 bằng **Retry-After/backoff**, không tạo retry storm.
- Khi store lỗi, hành vi fallback phù hợp và có telemetry rõ.
- Tất cả ingress paths được kiểm tra, không có đường bypass chính sách.

## 19. Câu hỏi tự kiểm tra và gợi ý giải

**1. Vì sao một API không nên chỉ giới hạn theo source IP nếu đã có xác thực người dùng?**

Vì một IP có thể đại diện cho nhiều người qua NAT/CGNAT, còn một người có thể thay IP. IP phù hợp làm tín hiệu coarse pre-auth, nhưng **verified user/client/tenant** thường công bằng hơn cho quota nghiệp vụ.

**2. Có thể dùng X-User-ID do client gửi làm limiter key không?**

Không, nếu header chưa được xác minh và ràng buộc với danh tính đã xác thực. Client có thể tự thay giá trị để tạo buckets mới hoặc làm người khác hết quota.

**3. Một OAuth client_id luôn chứng minh ứng dụng đã được xác thực?**

Không. Điều này tùy flow và cơ chế xác thực client. Phải dùng identity **được authorization server/gateway xác nhận theo profile phù hợp**, không tin chuỗi client_id tự khai.

**4. Cùng một user dùng hai API keys, tại sao cần thêm parent tenant budget?**

Để đổi/thêm key không làm nhân tổng quyền sử dụng; per-key limit giải quyết app/token cụ thể, còn **tenant limit** giải quyết tổng ngân sách.

**5. Fixed window 100 requests/phút có thể cho 200 requests trong một thời gian rất ngắn không?**

Có. Nếu request được dồn sát hai phía của ranh giới cửa sổ, hai windows độc lập có thể cho phép tổng gần 200 trong thời gian ngắn.

**6. Token bucket capacity=20, refill=5/s có nghĩa mỗi giây cho phép tối đa đúng 5 requests không?**

Không. Client có thể burst tối đa theo tokens đã tích lũy; về lâu dài refill rate mới là thước đo tốc độ duy trì.

**7. Vì sao đếm quota bằng GET rồi SET ở Redis có thể sai khi nhiều gateway cùng gửi request?**

Vì race condition: nhiều worker đọc cùng một giá trị rồi ghi đè. Cần thao tác **atomic** theo thuật toán đã chọn.

**8. Tại sao tăng số API gateway replicas có thể làm tăng allowance bất ngờ?**

Mỗi replica có **local counter độc lập**, khiến hạn mức toàn cluster trở thành tổng các hạn mức riêng nếu client có thể đi qua nhiều nodes.

**9. Một gói GraphQL query nhỏ về byte có thể gây quá tải dù dưới requests/minute không?**

Có. Query có thể có **depth/complexity** lớn hoặc tạo nhiều database calls. Cần complexity và per-operation cost caps.

**10. Vì sao không nên trả 403 cho mọi request vượt rate limit?**

403 biểu thị vấn đề về quyền truy cập; **429** phù hợp hơn khi nguyên nhân là quá nhiều requests theo policy. Phân biệt giúp client biết cần backoff chứ không phải tìm cách đổi quyền.

**11. Retry-After: 5 có đảm bảo client thử lại sau 5 giây sẽ được allow không?**

Không. Đây là hướng dẫn chờ; bucket có thể vẫn bị tiêu bởi những request khác hoặc giới hạn khác đang áp dụng.

**12. Tại sao API key rotation nên giữ nguyên tenant quota?**

Vì rotation là việc thay secret để cải thiện an toàn, không phải lý do tự có một tổng ngân sách mới.

**13. Rate limiting chống được volumetric DDoS làm bão hòa ISP link không?**

Không đủ. Khi traffic đã làm nghẽn uplink trước khi đến API gateway, cần phòng vệ **upstream/CDN/ISP**.

**14. Khi Redis limiter bị lỗi, phải luôn fail-open?**

Không. Chính sách phụ thuộc mức nhạy cảm của route, khả năng backend, business impact và fallback. Cần kiểm thử **fail-open/fail-closed/local fallback** và báo log chính xác.

**15. Vì sao 429 của CDN không xuất hiện trong log backend?**

Vì request có thể đã bị chặn ở edge và chưa từng tới backend. Phải quan sát logs theo **từng hop** và correlation ID.

**16. Một request export gây 30 giây CPU nhưng chỉ tính một token có đủ bảo vệ backend không?**

Không. Nên có **weighted cost**, concurrency/queue limit, timeout và resource budget.

**17. IPv6 /128 có phải là một user ổn định?**

Không. Privacy addressing và thay đổi prefix có thể làm nhiều địa chỉ gắn với một thiết bị/user; ngược lại một prefix có thể chứa nhiều người dùng. Cần quy tắc nhóm phù hợp và verified identity.

**18. Nếu người dùng hợp lệ bị 429 theo đúng quota công bố, có luôn là false positive không?**

Không. Cần định nghĩa tiêu chí FP theo hợp đồng và mong đợi nghiệp vụ. Vượt quota thực sự vẫn có thể là một kết quả enforcement đúng; yêu cầu thay quota là câu chuyện capacity/product policy.

## 20. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Rate limit và bandwidth limit là một.” | Một bên đếm request/cost theo thời gian, bên kia kiểm soát lưu lượng dữ liệu. |
| “Limit theo IP chính là limit theo user.” | NAT/CGNAT, proxy và IP rotation làm hai đại lượng khác nhau. |
| “X-Forwarded-For luôn là IP thật.” | Chỉ tin metadata nguồn qua chuỗi proxy được cấu hình và bảo vệ. |
| “User ID trong header là verified identity.” | Phải có xác thực và binding ở gateway/auth service. |
| “JWT decode được sub là đủ.” | Phải xác minh signature, issuer, audience, thời hạn và policy. |
| “OAuth client_id luôn là một secret.” | Một số OAuth flows có client ID công khai, không đủ làm bằng chứng tự xác thực. |
| “Mỗi API key một quota là đủ công bằng cho tenant.” | Nhiều keys có thể nhân tổng allowance nếu thiếu parent budget. |
| “Fixed window 100/phút đảm bảo mọi 60 giây trượt đều không quá 100.” | Burst qua ranh giới window có thể gần 200 trong khoảng rất ngắn. |
| “Token bucket capacity=20 nghĩa là 20 requests mỗi giây.” | Capacity là lượng burst tích lũy tối đa; refill quyết định tốc độ bền vững. |
| “Nginx limit_req_zone tự đồng bộ giữa các máy.” | Shared memory zone thông thường không chia state qua các instances. |
| “Redis GET rồi SET là đủ cho limiter.” | Race condition có thể cho phép vượt quota; cần atomic update. |
| “Gắn thêm replicas luôn giữ nguyên quota toàn dịch vụ.” | Local limit có thể nhân lên khi scale. |
| “HTTP 429 luôn là tấn công.” | Có thể là app lỗi, retry storm hoặc người dùng hợp lệ vượt hạn mức. |
| “HTTP 429 và 403 có cùng ngữ nghĩa.” | 429 là giới hạn số request; 403 là vấn đề quyền truy cập. |
| “Retry-After bảo đảm phép thử kế tiếp thành công.” | Các buckets khác hoặc người dùng khác vẫn có thể tiêu budget. |
| “Limit 100 RPS giúp ngăn mọi DoS.” | Không chống hết payload nặng, slow upload, concurrency và volumetric DDoS. |
| “Một GraphQL request luôn bằng một request đơn giản.” | Chi phí có thể phụ thuộc depth và số operations. |
| “Fail-open nghĩa là limiter khỏe.” | Store có thể lỗi và traffic không được kiểm tra; cần telemetry và fallback. |
| “Mỗi log request có user ID thật là cần thiết.” | Ưu tiên định danh được ẩn/giảm thiểu PII và không log tokens. |
| “Chặn ở CDN thì không cần bảo vệ origin.” | Direct origin, IPv6 hoặc ingress phụ có thể bypass nếu không kiểm soát. |
| “Không thấy 429 nghĩa là API đang được bảo vệ tốt.” | Có thể rule không gắn route, store lỗi fail-open, hoặc requests quá đắt nhưng RPS thấp. |

## 21. Tổng kết

**Rate limiting theo client và identity** không chỉ là một công thức **N requests/phút**. Nó bắt đầu từ việc xác định **đối tượng được giới hạn** và **nguồn danh tính nào có thể tin** tại từng điểm trên đường đi request. Trước xác thực, IP/nguồn mạng có ích cho bảo vệ sơ cấp nhưng có giới hạn do NAT, proxy, IPv6 và nguồn phân tán. Sau xác thực, **user, API client, workload và tenant identities đã được xác minh** cho phép áp ngân sách công bằng và chính xác hơn.

Đối với thuật toán, **fixed window** đơn giản nhưng có burst boundary; **sliding windows** hạn chế dồn tại ranh giới; **token bucket** cân bằng tốc độ bền vững với burst; **leaky bucket/queue** làm phẳng đầu ra nhưng cần giới hạn thời gian chờ. Trong hệ thống nhiều instance, **atomic shared state, clock consistency, quota scope và fail policy** quyết định limiter có thực sự giữ được cam kết toàn cluster hay không.

Trong học phần **SECURITY_NETWORK_SECURITY**, rate limiting là một lớp bảo vệ phục vụ **API gateway, WAF, proxy/load balancer L7, hệ thống xác thực, dịch vụ mạng và backend**. Để hiệu quả, hãy kết hợp **identity-aware budgets, per-operation cost, concurrency, size/time limits, network segmentation, upstream DDoS protection và giám sát**. Thành công phải được kiểm chứng bằng **hành vi allow/deny ở ranh giới, độ công bằng cho người dùng hợp lệ, khả năng chịu lỗi và tác động thật tới tài nguyên backend**.

### Tài liệu tham khảo và hướng đọc thêm

- **RFC 6585 — Additional HTTP Status Codes:** định nghĩa HTTP **429 Too Many Requests**.
- **RFC 9110 — HTTP Semantics:** ngữ nghĩa status, Retry-After và cơ chế xử lý HTTP.
- **RFC 7239 — Forwarded HTTP Extension:** thông tin proxy và các trường Forwarded; phải dùng trong trust boundary phù hợp.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc token và các claim như subject/audience/issuer.
- **RFC 8725 — JSON Web Token Best Current Practices:** yêu cầu an toàn khi xác minh và sử dụng JWT.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** các vai trò client, authorization và access token.
- **NGINX Documentation — ngx_http_limit_req_module:** limit_req_zone, limit_req, burst, nodelay và limit_req_status.
- **NGINX Documentation — ngx_http_realip_module:** định nghĩa nguồn IP tin cậy qua chuỗi reverse proxy.
- **OWASP API Security Top 10 (2023), API4: Unrestricted Resource Consumption:** rủi ro tiêu thụ tài nguyên qua API.
- **OWASP Authentication Cheat Sheet:** hướng dẫn bảo vệ xác thực, lỗi đăng nhập và các biện pháp chống tự động hóa.
- **OWASP Denial of Service Cheat Sheet:** kiểm soát tài nguyên, concurrency và phòng vệ nhiều lớp.
- **Tài liệu chính thức của API gateway, CDN/WAF và shared counter store đang vận hành:** thuật toán cụ thể, hạn mức, hành vi fallback và khả năng phân tán theo phiên bản sản phẩm.
