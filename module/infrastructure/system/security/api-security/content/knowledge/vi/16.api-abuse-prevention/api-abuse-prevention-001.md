# Credential stuffing, scraping và enumeration

API có thể xác thực đúng nhưng vẫn bị lạm dụng thông qua các request hợp lệ về mặt giao thức. Kẻ tấn công có thể dùng mật khẩu bị rò rỉ từ dịch vụ khác để thử đăng nhập hàng loạt (credential stuffing), tự động thu thập dữ liệu (scraping), hoặc dò xem tài khoản, mã khách hàng, đơn hàng và endpoint nào tồn tại (enumeration). Các hành vi này có thể dẫn đến chiếm tài khoản, rò rỉ dữ liệu, tăng tải hệ thống và tạo cơ sở cho những cuộc tấn công tiếp theo.

Bảo vệ API cần kết hợp kiểm soát xác thực, phân quyền, giới hạn tài nguyên, phát hiện hành vi tự động và thiết kế phản hồi không làm lộ thông tin. Một request có token hợp lệ vẫn phải chịu quota, rate limit và kiểm tra quyền trên từng đối tượng. Ngược lại, không nên coi mọi client tự động là độc hại: ứng dụng di động, đối tác tích hợp, công cụ tìm kiếm và hệ thống đồng bộ có thể tạo lưu lượng tự động hợp lệ. Chính sách cần dựa trên danh tính, quyền, phạm vi, tốc độ và hành vi thay vì chỉ chặn theo User-Agent.

## 1. Phân biệt ba kiểu lạm dụng

| Kiểu | Mục tiêu | Cách hoạt động phổ biến | Hậu quả |
|---|---|---|---|
| Credential stuffing | Chiếm tài khoản | Thử cặp username/email và mật khẩu đã bị lộ từ dịch vụ khác | Account takeover, gian lận, truy cập dữ liệu riêng tư |
| Scraping | Thu thập dữ liệu quy mô lớn | Tự động gọi API, duyệt trang hoặc endpoint tìm kiếm | Rò rỉ dữ liệu, sao chép nội dung, tăng tải và chi phí |
| Enumeration | Xác định tài khoản, object hoặc chức năng tồn tại | Thử email, số điện thoại, ID tuần tự, mã đơn hàng, token hoặc endpoint | Lộ metadata, hỗ trợ phishing, BOLA và credential attacks |

Ba hành vi có thể nối tiếp nhau. Kẻ tấn công có thể enumeration để xác định email có tài khoản, dùng credential stuffing để chiếm một số tài khoản, rồi scraping để thu thập hồ sơ hoặc dữ liệu mà tài khoản đó truy cập được.

### 1.1. Credential stuffing khác brute force

- **Brute force:** thử nhiều mật khẩu khác nhau cho một tài khoản hoặc một tập tài khoản.
- **Credential stuffing:** thử các cặp username/password đã bị lộ từ nơi khác, thường mỗi tài khoản chỉ thử một vài mật khẩu.
- **Password spraying:** thử một hoặc một số ít mật khẩu phổ biến trên nhiều tài khoản.

Rate limit chỉ theo username có thể không phát hiện tốt credential stuffing phân tán; rate limit chỉ theo IP có thể bị né bằng nhiều địa chỉ nguồn. Cần phối hợp tín hiệu theo tài khoản, IP/network, thiết bị, client, tenant và thời gian.

### 1.2. Scraping không đồng nghĩa mọi truy cập tự động đều xấu

Một đối tác có thể đồng bộ danh mục theo lịch; ứng dụng mobile có thể tải nhiều trang; công cụ tìm kiếm có thể truy cập nội dung công khai. Hành vi cần đánh giá theo điều khoản sử dụng, loại dữ liệu, phạm vi được phép, tốc độ, dấu hiệu né giới hạn và tác động lên hệ thống.

Không dựa riêng vào User-Agent, IP hoặc robots.txt để bảo vệ API. Các giá trị này có thể bị giả mạo hoặc không áp dụng cho API riêng tư. Quyền truy cập phải được thực thi ở server.

## 2. Threat model và bề mặt tấn công

Các endpoint thường bị lạm dụng gồm:

- Đăng nhập, refresh token, đăng xuất và xác thực MFA.
- Đăng ký, xác minh email/số điện thoại, quên mật khẩu và khôi phục tài khoản.
- Tra cứu user, customer, invoice, order, ticket hoặc mã tham chiếu.
- Search, autocomplete, filter, export, download và phân trang.
- Endpoint công khai có quota thấp hoặc dữ liệu có giá trị thương mại.
- API dành cho operator, đối tác và ứng dụng mobile.
- GraphQL, batch endpoint, API version cũ và endpoint nội bộ bị lộ ra gateway.

Khi lập threat model, cần xác định:

1. **Tài sản:** tài khoản, thông tin xác minh, dữ liệu cá nhân, dữ liệu kinh doanh, token, quota và tài nguyên hạ tầng.
2. **Tác nhân:** botnet, proxy network, người dùng tự động hóa, đối thủ cạnh tranh, malware trên thiết bị hoặc người đã có tài khoản hợp lệ.
3. **Điểm quan sát:** response code, nội dung lỗi, kích thước response, thời gian phản hồi, pagination, ID trong URL, header và khác biệt giữa các trạng thái tài khoản.
4. **Ranh giới tin cậy:** client/API gateway, gateway/application, application/database, tenant/tenant và hệ thống của đối tác.
5. **Tác động:** chiếm tài khoản, thu thập dữ liệu, suy luận thông tin riêng tư, gian lận, DoS và chi phí tăng.

### Chuỗi tấn công thường gặp

~~~mermaid
flowchart TD
    A[Thu thập email, username hoặc ID] --> B[Enumeration tài khoản và object]
    B --> C[Thử credential bị lộ]
    C --> D{Đăng nhập thành công?}
    D -->|Không| E[Thử nguồn hoặc tài khoản khác]
    D -->|Có| F[Chiếm session hoặc lấy token]
    F --> G[Enumeration endpoint và quyền]
    G --> H[Scraping hoặc thao tác dữ liệu]
    H --> I[Phát hiện, giới hạn và thu hồi]
~~~

Một hệ thống có thể chặn từng request riêng lẻ nhưng vẫn thất bại khi không phát hiện chuỗi hành vi qua nhiều endpoint. Ví dụ, nhiều lần gọi quên mật khẩu, tra cứu trạng thái email và đăng nhập có thể là một chiến dịch enumeration/credential stuffing liên kết.

## 3. Phòng chống credential stuffing

### 3.1. Bảo vệ mật khẩu và quy trình xác thực

- Lưu mật khẩu bằng password hashing chuyên dụng như Argon2id, scrypt hoặc bcrypt với salt riêng và tham số phù hợp.
- Không lưu hoặc ghi log mật khẩu plaintext; không gửi mật khẩu trong URL hay thông báo lỗi.
- Hỗ trợ MFA, ưu tiên phương thức chống phishing cho tài khoản có rủi ro cao.
- Khuyến khích passkey/WebAuthn hoặc cơ chế xác thực chống phishing khi phù hợp.
- Kiểm tra mật khẩu mới với danh sách mật khẩu phổ biến hoặc đã bị lộ; không tự động gửi mật khẩu người dùng tới dịch vụ bên thứ ba nếu chưa có thiết kế riêng tư phù hợp.
- Dùng luồng reset mật khẩu có token ngẫu nhiên, một lần, thời hạn ngắn và thu hồi session/token theo policy.
- Không cho phép endpoint đăng nhập tiết lộ quá nhiều thông tin về trạng thái tài khoản.

MFA làm giảm nguy cơ chiếm tài khoản khi mật khẩu bị lộ, nhưng không loại bỏ mọi rủi ro. Phishing proxy, session theft, MFA fatigue và quy trình khôi phục yếu vẫn có thể bị khai thác. Cần bảo vệ cả session sau khi đăng nhập.

### 3.2. Rate limit đa chiều

Không dùng một khóa rate limit duy nhất. Nên phối hợp các chiều:

| Chiều | Ví dụ giới hạn | Mục đích |
|---|---|---|
| Tài khoản/username chuẩn hóa | Số lần xác thực thất bại trong cửa sổ thời gian | Nhận diện nhắm vào một tài khoản |
| IP hoặc network prefix | Request đăng nhập, reset, OTP trong thời gian ngắn | Giảm tấn công tập trung từ một nguồn |
| Device/session | Tần suất và số tài khoản được thử từ một thiết bị | Nhận diện một client thử nhiều danh tính |
| Client/application | Lưu lượng theo API client hoặc app identity | Bảo vệ tích hợp và client đã đăng ký |
| Tenant | Lưu lượng đăng nhập, reset và API tổng thể | Ngăn một tenant gây ảnh hưởng hệ thống dùng chung |
| Global | Tổng tải toàn hệ thống | Bảo vệ capacity khi tấn công phân tán |

Dùng cửa sổ trượt hoặc token bucket/leaky bucket tùy mục đích. Giới hạn cần tính đến NAT, mạng di động và văn phòng dùng chung IP để tránh khóa nhầm nhiều người dùng hợp lệ.

Không khóa tài khoản vĩnh viễn chỉ vì có nhiều lần đăng nhập sai: kẻ tấn công có thể cố tình khóa tài khoản nạn nhân (denial of service). Có thể dùng delay tăng dần, yêu cầu step-up challenge, tạm hạn chế luồng đăng nhập, cảnh báo chủ tài khoản hoặc biện pháp risk-based. Nếu có khóa tạm, thời hạn và cơ chế mở khóa phải được thiết kế rõ ràng.

### 3.3. Phát hiện credential stuffing phân tán

Tín hiệu có thể bao gồm:

- Nhiều tài khoản khác nhau bị thử từ cùng IP, ASN, device fingerprint hoặc dải mạng.
- Một tài khoản nhận request đăng nhập từ nhiều nguồn trong thời gian ngắn.
- Nhiều lần thất bại với mật khẩu phổ biến hoặc mẫu user-agent bất thường.
- Tỷ lệ đăng nhập thất bại tăng đột ngột so với baseline.
- Nhiều tài khoản đăng nhập thành công sau một chuỗi thử thất bại.
- Sau đăng nhập, principal bắt đầu truy cập endpoint hoặc dữ liệu khác với hành vi thường lệ.
- Refresh token/session được sử dụng từ thiết bị hoặc vị trí mạng bất thường.

Không coi một IP lạ hoặc một lần đăng nhập thất bại là bằng chứng đủ để chặn tài khoản. Kết hợp nhiều tín hiệu, mức độ rủi ro và tác động của quyết định. Với sự kiện rủi ro cao, yêu cầu xác thực lại, MFA hoặc xác nhận từ thiết bị đã đăng ký.

### 3.4. Bảo vệ reset password và OTP

Endpoint quên mật khẩu và gửi OTP thường bị lạm dụng để enumeration, spam và tiêu hao chi phí SMS/email.

- Trả thông báo chung, ví dụ “Nếu thông tin phù hợp với tài khoản, hướng dẫn sẽ được gửi”.
- Giữ thời gian phản hồi tương đối nhất quán giữa tài khoản tồn tại và không tồn tại; tránh tạo khác biệt rõ rệt qua status, body hoặc kích thước response.
- Rate limit theo tài khoản chuẩn hóa, địa chỉ nguồn, thiết bị và tổng chi phí gửi.
- Có cooldown/resend window và giới hạn số OTP sai.
- Token/OTP có entropy phù hợp, thời hạn ngắn, dùng một lần và ràng buộc đúng mục đích.
- Không cho phép dùng OTP của một luồng để xác minh luồng khác.
- Không tiết lộ OTP trong log, analytics, ticket hoặc thông báo không an toàn.
- Theo dõi chi phí và số lượng gửi để phát hiện SMS pumping hoặc email bombing.

Không dùng chung một mã lỗi tiết lộ “email không tồn tại” ở reset password trong khi đăng nhập lại trả “sai mật khẩu” theo cách giúp kẻ tấn công xác định tài khoản. Thông báo cho người dùng sau khi họ chứng minh được quyền kiểm soát kênh liên hệ có thể cung cấp thêm thông tin phù hợp.

## 4. Chống enumeration tài khoản và dữ liệu

Enumeration là việc suy luận một đối tượng có tồn tại hay không từ phản hồi API. Đối tượng có thể là email, username, số điện thoại, customer ID, invoice ID, API key, token, tenant hoặc endpoint.

### 4.1. Tránh response tiết lộ sự tồn tại

Ví dụ không an toàn:

~~~http
POST /api/password/forgot
Content-Type: application/json

{"email":"person@example.test"}
~~~

Khi email tồn tại, API trả 200 với body “Đã gửi email”. Khi không tồn tại, API trả 404 với body “Không tìm thấy tài khoản”. Khác biệt này cho phép kẻ tấn công dò danh sách email.

Một phản hồi ít tiết lộ hơn:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "message": "Nếu thông tin phù hợp với tài khoản, hướng dẫn sẽ được gửi."
}
~~~

Status và cấu trúc response nên giống nhau cho cả hai trường hợp. Không thể bảo đảm thời gian thực thi giống hệt tuyệt đối, nhưng cần tránh khác biệt rõ rệt và có thể đoán được.

### 4.2. Chuẩn hóa lỗi và response

Kiểm tra các chiều có thể tạo side channel:

- HTTP status code.
- Error code và message.
- Kích thước body và số lượng field.
- Thời gian phản hồi.
- Header như Location, Retry-After hoặc header tùy chỉnh.
- Số lượng kết quả, pagination metadata và total count.
- Sự khác nhau giữa 404, 403 và 200 với body rỗng.

Không phải mọi endpoint đều phải trả cùng status code cho mọi lỗi. Cần chọn policy phù hợp với mục đích endpoint và tránh để sự khác biệt tiết lộ dữ liệu nhạy cảm. Với object mà principal không có quyền biết sự tồn tại, có thể trả 404 nhất quán thay vì 403, tùy hợp đồng API.

### 4.3. ID tuần tự và mã tham chiếu

ID tuần tự như 10001, 10002, 10003 giúp kẻ tấn công dễ duyệt qua một dải đối tượng. UUID hoặc ID ngẫu nhiên làm khó việc đoán nhưng không thay thế authorization.

Ví dụ endpoint:

~~~http
GET /api/invoices/INV-10001
Authorization: Bearer <access-token>
~~~

Dù ID là UUID khó đoán, server vẫn phải kiểm tra:

1. Principal đã xác thực.
2. Permission chức năng cho phép invoice:read.
3. Invoice thuộc tenant mà principal được phép truy cập.
4. Principal có quyền trên invoice cụ thể theo owner/assignment/ủy quyền.
5. Dữ liệu trả về đã được giới hạn field theo policy.

Không chỉ dựa vào việc ID khó đoán hoặc trả 404 khi không tìm thấy. Mọi endpoint detail, update, delete, export và bulk đều phải áp dụng kiểm tra tương tự.

### 4.4. Enumeration endpoint và API version

Kẻ tấn công có thể dò endpoint qua wordlist, HTTP method, GraphQL introspection hoặc tài liệu cũ. Không dựa vào việc endpoint khó đoán hoặc không xuất hiện trên UI.

- Tắt debug endpoint và API documentation công khai ở production nếu không cần.
- Bảo vệ OpenAPI/Swagger UI và schema nội bộ theo quyền.
- Loại bỏ route cũ hoặc deprecate với thời hạn rõ ràng; route cũ vẫn phải giữ authorization.
- Kiểm tra cả HTTP method và action endpoint.
- Với GraphQL, giới hạn introspection theo môi trường/chính sách, depth, complexity, alias và số lượng resolver; introspection không thay thế authorization ở resolver.
- Không để error message trả stack trace hoặc danh sách route nội bộ.

## 5. Hạn chế scraping và thu thập dữ liệu quy mô lớn

### 5.1. Xác định dữ liệu nào được phép truy cập

Chia dữ liệu theo mức độ nhạy cảm:

- **Public:** có thể truy cập không cần đăng nhập nhưng vẫn có quota và giới hạn tốc độ.
- **Authenticated:** chỉ user đã xác thực mới truy cập được.
- **Tenant-scoped:** chỉ principal có membership và quyền trong tenant mới truy cập được.
- **Sensitive:** cần permission cụ thể, giới hạn field và audit.
- **Bulk/export restricted:** cần quyền riêng, quota, phê duyệt hoặc job có thời hạn.

Không coi việc endpoint trả dữ liệu cho một user là cho phép tải toàn bộ dữ liệu. Quyền đọc một object không tự động bao gồm quyền export hàng triệu object.

### 5.2. Giới hạn pagination, search và export

- Đặt default và maximum page size; giới hạn deep offset.
- Ưu tiên cursor/keyset pagination với thứ tự ổn định khi dữ liệu lớn.
- Giới hạn số filter, độ dài query, sort field và khoảng thời gian tìm kiếm.
- Chỉ cho phép các field được công bố; không trả field nội bộ hoặc dữ liệu nhạy cảm không cần thiết.
- Giới hạn số bản ghi export, dung lượng file, số job đang chạy và thời gian lưu kết quả.
- Yêu cầu permission riêng cho bulk export; audit ai tạo export, phạm vi và số bản ghi.
- Pre-signed URL download cần thời hạn ngắn và giới hạn đúng object; URL là bearer capability nên không đưa vào log hoặc chia sẻ rộng.
- Với API public, cân nhắc quota theo client và chính sách sử dụng dữ liệu.

### 5.3. Phát hiện hành vi scraping

Một số tín hiệu:

- Client duyệt tuần tự ID hoặc cursor với tốc độ cao.
- Request lặp lại trên nhiều trang, filter hoặc category với pattern đều đặn.
- Một principal đọc số lượng object lớn nhưng không có hành động nghiệp vụ tương ứng.
- Tỷ lệ tải dữ liệu cao, nhiều endpoint search/export được gọi liên tục.
- Nhiều tài khoản dùng chung fingerprint hoặc cùng một pattern truy cập.
- Client thay đổi IP/User-Agent liên tục nhưng giữ cùng pattern truy vấn.
- Số lượng response bytes hoặc số bản ghi trả về tăng đột biến.

Dùng nhiều tín hiệu để phân loại rủi ro. Một đối tác đồng bộ hợp lệ có thể có lưu lượng đều và cao; hãy cấp client identity riêng, scope rõ, quota đã thỏa thuận và audit. Đừng chặn toàn bộ một dải IP chỉ vì một client trong đó có hành vi bất thường.

### 5.4. Giảm dữ liệu trả về

- Dùng response DTO theo mục đích thay vì serialize entity nội bộ.
- Chỉ trả field client cần; hỗ trợ field selection theo allowlist nếu có nhu cầu.
- Mask hoặc bỏ thông tin cá nhân, email, số điện thoại, địa chỉ và metadata nhạy cảm.
- Tránh trả tổng số chính xác nếu nó tiết lộ quy mô dữ liệu không được phép biết.
- Không trả quan hệ nội bộ, ID liên kết hoặc thông tin debug không cần thiết.
- Dùng phân trang và giới hạn export; không có endpoint “dump all” chỉ dựa vào token thông thường.

## 6. Rate limit và bot mitigation nhiều lớp

Rate limit là một lớp kiểm soát, không phải giải pháp duy nhất. Nên phối hợp:

| Lớp | Ví dụ kiểm soát |
|---|---|
| Edge/API gateway | Request rate, connection, header/body size, IP reputation, bot signal |
| Authentication | Thử đăng nhập, OTP, reset, refresh token theo account/device/network |
| Application | Rate limit theo principal, permission, endpoint và tenant |
| Business | Hạn mức giao dịch, số lần export, số object được đọc hoặc tạo |
| Data layer | Query timeout, row limit, concurrency và connection pool |
| Detection | Baseline, anomaly detection, cảnh báo và correlation nhiều endpoint |

### 6.1. Token bucket và cửa sổ trượt

Token bucket cho phép một lượng burst nhỏ nhưng giới hạn tốc độ trung bình. Cửa sổ trượt đếm request trong khoảng thời gian gần nhất. Chọn thuật toán theo hành vi cần kiểm soát; cần xử lý đồng thời và lưu trạng thái phân tán nếu API chạy nhiều instance.

Ví dụ policy minh họa:

| Endpoint | Giới hạn ví dụ | Ghi chú |
|---|---:|---|
| Đăng nhập | 5 lần thất bại/10 phút/account, cộng giới hạn theo IP/device | Không khóa vĩnh viễn tài khoản |
| Gửi OTP | 3 lần/15 phút/destination, cộng quota nguồn | Có cooldown và cost alert |
| Search public | 60 request/phút/client | Kèm page size tối đa |
| Đọc dữ liệu tenant | 300 request/phút/principal và quota tenant | Quyền object vẫn bắt buộc |
| Bulk export | 2 job đồng thời/tenant | Có permission và audit |

Các con số chỉ để minh họa; cần đo traffic hợp lệ, capacity và yêu cầu nghiệp vụ trước khi áp dụng. Nếu giới hạn quá thấp, người dùng thật và tích hợp hợp lệ sẽ bị ảnh hưởng.

### 6.2. Rate limit theo danh tính đã xác minh

Không dùng tenant ID do client tự gửi làm key quota. Với request đã xác thực, dùng principal/client/tenant context đã được server xác minh. Với request chưa xác thực, có thể kết hợp IP/network, device signal và các khóa tạm thời đã chuẩn hóa.

Nếu chỉ rate limit theo IP, proxy hoặc NAT có thể làm nhiều người dùng chung một bucket. Nếu chỉ theo account, botnet có thể phân tán trên nhiều account. Nếu chỉ theo API key, một key bị lộ có thể tạo tải lớn trong phạm vi quota. Kết hợp các chiều giúp giảm khả năng né giới hạn.

### 6.3. CAPTCHA và challenge theo rủi ro

CAPTCHA hoặc challenge có thể tăng chi phí tự động hóa ở các luồng nhạy cảm như đăng nhập, đăng ký hoặc reset password. Nên áp dụng theo risk signal thay vì bắt mọi request đều giải CAPTCHA.

CAPTCHA không phải xác thực danh tính và không bảo vệ API nếu endpoint có thể gọi trực tiếp mà không qua luồng challenge. Server phải xác minh challenge token, hostname/action/expiry theo nhà cung cấp và ràng buộc kết quả với request/session phù hợp. Không tin một cờ captchaSolved=true do client gửi.

### 6.4. Client identity và API key

Với đối tác tích hợp, cấp client identity riêng và credential có vòng đời, scope, quota, owner và khả năng thu hồi. Không nhúng secret dùng chung vào frontend hoặc mobile binary. API key chỉ nhận diện client; quyền trên dữ liệu vẫn cần access token, workload identity hoặc policy phù hợp. Một key hợp lệ không cho phép scraping mọi dữ liệu.

## 7. Ví dụ kiểm soát trong Spring

### 7.1. Không tiết lộ tài khoản trong password reset

Ví dụ controller luôn trả cùng response sau khi nhận request hợp lệ:

~~~java
@PostMapping("/api/password/forgot")
ResponseEntity<GenericMessage> forgotPassword(
        @Valid @RequestBody ForgotPasswordRequest request) {

    passwordResetService.requestIfAccountExists(request.email());

    return ResponseEntity.accepted()
            .body(new GenericMessage(
                    "Nếu thông tin phù hợp với tài khoản, hướng dẫn sẽ được gửi."));
}
~~~

Service chỉ phát hành token khi account tồn tại và đáp ứng policy. Việc gửi email nên chạy qua cơ chế có quota/cooldown. Không để controller trả khác biệt theo kết quả tìm thấy account. Cần cân nhắc timing và side effect để tránh khác biệt có thể đo được.

### 7.2. Kiểm tra object trước khi trả dữ liệu

~~~java
public CustomerSummary getCustomer(
        AuthenticatedPrincipal principal,
        UUID customerId) {

    Customer customer = customerRepository
            .findByIdAndTenantId(customerId, principal.tenantId())
            .orElseThrow(NotFoundException::new);

    authorizationService.requirePermission(
            principal, "customer:read", customer);

    return CustomerSummary.from(customer);
}
~~~

Ví dụ này minh họa kiểm tra tenant và quyền object. principal.tenantId() phải đến từ token/context đã xác minh, không phải query hoặc body. Response DTO chỉ chứa field được phép. Nếu user chỉ được xem khách hàng được phân công, policy cần kiểm tra assignment cụ thể.

### 7.3. Rate limit không thay thế authorization

Rate limiter có thể chạy ở gateway hoặc application và từ chối request vượt ngưỡng bằng 429 Too Many Requests. Dù request nằm dưới ngưỡng, application vẫn phải xác thực principal, kiểm tra permission, tenant và object. Không cấp quyền chỉ vì client có quota còn lại.

Trong hệ thống nhiều instance, rate limit theo account/client/tenant cần dùng state chia sẻ hoặc gateway có khả năng phân tán. Nếu mỗi instance đếm riêng, client có thể tăng tổng tốc độ bằng cách phân phối request qua nhiều instance.

## 8. Phản hồi HTTP và tránh side channel

| Status | Sử dụng phù hợp | Lưu ý bảo mật |
|---|---|---|
| 200 OK / 202 Accepted | Request hợp lệ hoặc tác vụ được tiếp nhận | Với reset/lookup nhạy cảm, body nên trung tính và không tiết lộ tồn tại |
| 400 Bad Request | Request sai cú pháp hoặc tham số | Không phản chiếu dữ liệu nhạy cảm trong lỗi |
| 401 Unauthorized | Thiếu hoặc credential không hợp lệ | Thông báo không nên phân biệt username tồn tại và mật khẩu sai |
| 403 Forbidden | Principal không có quyền | Cân nhắc 404 nếu cần che giấu object |
| 404 Not Found | Object không tồn tại hoặc được che theo policy | Duy trì hành vi nhất quán với object ngoài phạm vi |
| 409 Conflict | Xung đột trạng thái nghiệp vụ | Không tiết lộ trạng thái nhạy cảm không cần thiết |
| 429 Too Many Requests | Vượt rate limit/quota | Có thể trả Retry-After; không lộ bucket của user khác |
| 503 Service Unavailable | Hệ thống tạm thời quá tải | Có thể trả Retry-After, không lộ hạ tầng nội bộ |

Không phải mọi endpoint đều cần giấu mọi khác biệt. Ví dụ, một API tra cứu danh mục công khai có thể trả 404 khi object không tồn tại. Nhưng endpoint đăng nhập, reset password, xác minh email hoặc tra cứu thông tin cá nhân cần đánh giá xem response có cho phép suy ra danh tính hay không.

## 9. Giám sát, tương quan và ứng phó

### 9.1. Metric và sự kiện cần theo dõi

- Tỷ lệ đăng nhập thất bại/thành công theo account, IP/network, device và client.
- Số account khác nhau được thử từ một nguồn trong khoảng thời gian ngắn.
- Số nguồn khác nhau nhắm vào cùng account.
- Tần suất reset password, gửi OTP, resend và xác minh OTP thất bại.
- Số object được đọc, số trang, bytes trả về và tốc độ duyệt ID/cursor.
- Tỷ lệ 401, 403, 404, 429 và các thay đổi bất thường về response time.
- Số export/job, dung lượng file và số bản ghi được tải.
- Đăng nhập mới sau chuỗi thất bại, đổi mật khẩu, đổi MFA hoặc thay đổi thông tin liên hệ.
- Token/session refresh từ nguồn bất thường và các thao tác nhạy cảm sau đăng nhập.

Không log mật khẩu, OTP, raw access token, refresh token, cookie hoặc API key. Dùng request ID, principal/client ID đã kiểm soát, key ID, kết quả, endpoint, timestamp và metadata mạng phù hợp để điều tra.

### 9.2. Correlation giữa nhiều endpoint

Một chiến dịch có thể phân tán qua login, forgot password, OTP, profile lookup và data export. Cần tương quan sự kiện theo account, device, client, tenant, IP/network và khoảng thời gian. Không chỉ đặt alert độc lập cho mỗi endpoint.

### 9.3. Quy trình ứng phó

1. **Xác nhận phạm vi:** endpoint, loại dữ liệu, số principal/object bị ảnh hưởng, nguồn và khoảng thời gian.
2. **Giảm tốc độ tấn công:** điều chỉnh rate limit/challenge theo risk signal, chặn nguồn rõ ràng độc hại và bảo vệ capacity.
3. **Bảo vệ tài khoản:** yêu cầu step-up, thu hồi session/token đáng ngờ, reset credential khi có bằng chứng xâm phạm và thông báo qua kênh tin cậy.
4. **Ngăn rò rỉ tiếp diễn:** giảm scope/field, tạm dừng export hoặc endpoint bị lạm dụng khi cần, kiểm tra object authorization.
5. **Điều tra:** xác định dữ liệu đã được trả, session nào bị chiếm, request nào thành công và downstream nào bị ảnh hưởng.
6. **Khôi phục:** mở lại luồng hợp lệ, theo dõi false positive, khôi phục quota và kiểm tra trải nghiệm người dùng.
7. **Khắc phục nguyên nhân:** cập nhật policy, kiểm thử, cải thiện detection và rà soát các endpoint tương tự.

Nếu phát hiện credential stuffing thành công, không chỉ khóa IP nguồn. Cần đánh giá account takeover, thu hồi token/session, kiểm tra thay đổi email/MFA/thông tin thanh toán và rà soát hành vi sau đăng nhập.

## 10. Kiểm thử bảo mật

Kiểm thử nên mô phỏng hành vi phân tán, tốc độ khác nhau và nhiều danh tính. Dùng tài khoản/dữ liệu thử nghiệm; không thử credential thật của người khác.

| Nhóm | Tình huống kiểm thử | Kết quả mong đợi |
|---|---|---|
| Credential stuffing | Nhiều account bị thử từ một nguồn | Rate limit/detection kích hoạt theo policy |
| Distributed attempts | Một account bị thử từ nhiều nguồn | Risk signal tương quan được phát hiện |
| Password spraying | Một mật khẩu thử trên nhiều account | Phát hiện theo account set và nguồn |
| Account lockout abuse | Kẻ tấn công cố tình gây thất bại cho account nạn nhân | Không khóa vĩnh viễn dễ bị DoS; có delay/challenge phù hợp |
| MFA | Mật khẩu đúng nhưng thiếu yếu tố thứ hai | Không cấp session đầy đủ |
| Password reset | Email tồn tại và không tồn tại | Response không tiết lộ sự tồn tại qua status/body rõ ràng |
| OTP abuse | Gửi resend liên tục hoặc thử OTP sai | Cooldown, quota và giới hạn thử hoạt động |
| User enumeration | Thử username/email/phone khác nhau | Response và timing không tạo oracle rõ rệt |
| Object enumeration | Dò ID tuần tự hoặc UUID của tenant khác | Authorization chặn; không lộ object ngoài phạm vi |
| Scraping | Duyệt nhiều trang và ID theo pattern | Quota/detection kích hoạt theo policy |
| Bulk export | Tạo nhiều export hoặc tải quá nhiều bản ghi | Permission, quota và audit được thực thi |
| API key abuse | Dùng key của client khác hoặc key bị thu hồi | Bị từ chối; key không cấp quyền dữ liệu vượt scope |
| Header/metadata | Thử User-Agent, IP hoặc header giả để né giới hạn | Không dựa riêng vào một tín hiệu dễ giả mạo |
| Response side channel | So sánh status, body size và latency cho account tồn tại/không tồn tại | Không có khác biệt rõ rệt tiết lộ thông tin |
| Multi-instance rate limit | Phân phối request qua nhiều instance | Tổng giới hạn vẫn được thực thi đúng |
| False positive | Người dùng hợp lệ dùng NAT, đổi mạng hoặc đăng nhập khi đi du lịch | Cơ chế challenge/khôi phục không gây khóa nhầm diện rộng |

Kiểm thử load và abuse phải theo phạm vi được ủy quyền, dùng dữ liệu giả và giới hạn tải để không ảnh hưởng môi trường thật. Đánh giá cả khả năng phát hiện lẫn khả năng khôi phục sau khi giới hạn được kích hoạt.

## 11. Checklist thiết kế trước khi phát hành

- [ ] Đã phân loại endpoint và dữ liệu public, authenticated, tenant-scoped, sensitive và bulk/export.
- [ ] Đăng nhập có rate limit đa chiều và phát hiện credential stuffing/password spraying.
- [ ] Có MFA hoặc step-up cho hành động/tài khoản có rủi ro cao.
- [ ] Không khóa tài khoản vĩnh viễn chỉ dựa trên số lần đăng nhập sai.
- [ ] Reset password, OTP và xác minh email không làm lộ tài khoản tồn tại.
- [ ] Token reset/OTP có thời hạn ngắn, dùng một lần và ràng buộc đúng mục đích.
- [ ] Mọi endpoint detail/search/export đều kiểm tra function, object và tenant authorization.
- [ ] Pagination, filter, cursor, response fields và export có giới hạn.
- [ ] Rate limit/quota áp dụng theo principal, client, tenant và global capacity.
- [ ] CAPTCHA/challenge được xác minh ở server và chỉ dùng như tín hiệu bổ sung.
- [ ] API key/client identity có scope, owner, quota, rotation và revoke.
- [ ] Có detection/correlation giữa login, reset, OTP, lookup và export.
- [ ] Log không chứa password, OTP, token, cookie hoặc raw API key.
- [ ] Có test cho distributed attempts, enumeration, scraping, side channel và false positive.
- [ ] Có quy trình ứng phó account takeover và data scraping.

Credential stuffing tận dụng mật khẩu đã bị lộ; scraping khai thác khả năng truy cập dữ liệu ở quy mô lớn; enumeration tận dụng khác biệt phản hồi để suy ra tài khoản hoặc object tồn tại. Phòng thủ hiệu quả cần kết hợp xác thực mạnh, authorization theo endpoint/object/tenant, response nhất quán, giới hạn đa chiều, giảm dữ liệu trả về và giám sát hành vi xuyên nhiều API. Khi các lớp này phối hợp, việc một request riêng lẻ trông hợp lệ sẽ không đủ để kẻ tấn công tự do thử tài khoản, dò dữ liệu hoặc thu thập toàn bộ hệ thống.
