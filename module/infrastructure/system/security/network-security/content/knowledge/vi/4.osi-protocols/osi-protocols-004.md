# Tầng Session và Application trong mô hình OSI

Trong bảo mật mạng, một kết nối có thể được mã hóa an toàn nhưng người dùng vẫn bị chiếm phiên đăng nhập; ngược lại, người dùng có thể đã đăng nhập thành công nhưng một API vẫn phải kiểm tra quyền cho từng yêu cầu. Để hiểu các tình huống đó, cần phân biệt **tầng Session (tầng 5)**, **tầng Application (tầng 7)** và những cơ chế triển khai chúng trong các hệ thống TCP/IP hiện đại.

Bài học thuộc chủ đề **OSI và giao thức**, nằm trong phạm vi **SECURITY_NETWORK_SECURITY**: xây dựng nền tảng để phân tích lưu lượng, xác thực kết nối, nhận diện điểm tấn công và thiết kế phòng vệ nhiều lớp cho các dịch vụ mạng.

## 1. Vị trí của Session và Application

Mô hình OSI mô tả bảy tầng chức năng. Phần gần ứng dụng nhất gồm:

| Tầng OSI | Trách nhiệm khái niệm | Ví dụ trong hệ thống thực tế |
|---|---|---|
| 7 — Application | Cung cấp giao thức và dịch vụ mạng cho tiến trình ứng dụng; xác định cấu trúc, ý nghĩa thông điệp | HTTP, DNS, SMTP, IMAP, SSH |
| 6 — Presentation | Biểu diễn, chuyển đổi dữ liệu; có thể gắn với mã hóa/giải mã theo cách phân tầng khái niệm | JSON, UTF-8, mã hóa TLS khi mô tả theo chức năng; không có ánh xạ OSI duy nhất |
| 5 — Session | Điều phối hội thoại, thiết lập/duy trì/kết thúc phiên; hỗ trợ đồng bộ và tiếp tục trao đổi | Chức năng phiên trong RPC, NetBIOS Session Service, cơ chế quản lý phiên ở tầng ứng dụng |
| 4 — Transport | Vận chuyển dữ liệu giữa các đầu cuối, dùng cổng và cơ chế truyền phù hợp | TCP, UDP; QUIC kết hợp một số chức năng vận chuyển và bảo mật trên UDP |

**Lưu ý về mô hình:** Internet ngày nay thường được mô tả bằng mô hình TCP/IP. Các chức năng OSI tầng 5, 6 và 7 thường được gộp vào **tầng ứng dụng của TCP/IP**, do thư viện hoặc chính giao thức ứng dụng đảm nhiệm. Vì thế, không thể lấy một tên giao thức thực tế rồi luôn gán cứng cho đúng một tầng OSI.

Đặc biệt, **TLS không đồng nghĩa với phiên đăng nhập**. TLS giúp bảo vệ kênh trao đổi; phiên đăng nhập quyết định một yêu cầu có gắn với danh tính đã được xác thực hay không.

## 2. Tầng Session (tầng 5): quản lý hội thoại

### 2.1. Phiên là gì?

Theo mô hình OSI, **session** là quan hệ trao đổi logic giữa hai thực thể ứng dụng trong một khoảng thời gian. Tầng 5 tập trung vào cách hai bên tổ chức hội thoại, thay vì nội dung nghiệp vụ của từng thông điệp.

Những trách nhiệm thường được mô tả cho tầng này gồm:

1. **Thiết lập phiên:** hai bên thống nhất bắt đầu trao đổi, các trạng thái và khả năng cần thiết.
2. **Duy trì phiên:** theo dõi tiến trình hội thoại, điều phối lượt truyền khi giao thức yêu cầu và nhận biết sự gián đoạn.
3. **Đồng bộ:** đánh dấu các mốc xử lý (checkpoint) để phục hồi hoặc tiếp tục công việc khi có cơ chế tương ứng.
4. **Kết thúc phiên:** giải phóng trạng thái và tài nguyên liên quan khi hội thoại hoàn tất hoặc hết hạn.

Tài liệu OSI cổ điển mô tả các chức năng như *dialog control*, *synchronization* và *session management*. Trong một dịch vụ web hiện đại, những chức năng tương tự có thể do HTTP, framework, ứng dụng hoặc thành phần trung gian thực hiện; không nhất thiết tồn tại một giao thức tầng 5 độc lập.

### 2.2. Ví dụ về duy trì và phục hồi hội thoại

Giả sử một hệ thống đồng bộ tệp cần chuyển 3 GB dữ liệu. Sau khi chuyển được 2 GB, mạng bị ngắt.

- Nếu hai bên không lưu tiến độ, quá trình có thể phải bắt đầu lại.
- Nếu ứng dụng ghi nhận offset, mã định danh tệp và trạng thái đã xác thực, phía nhận có thể yêu cầu gửi tiếp phần còn thiếu.
- Trong HTTP, cơ chế như yêu cầu `Range` có thể hỗ trợ tải tiếp *khi máy chủ hỗ trợ và điều kiện tài nguyên cho phép*. Đây là **chức năng phục hồi phiên ở mức ứng dụng**, không có nghĩa HTTP đã triển khai một tầng 5 OSI riêng.

Điều cần rút ra là **phiên là quan hệ logic có trạng thái**; trạng thái đó có thể tồn tại lâu hơn một kết nối mạng đơn lẻ, tùy thiết kế dịch vụ.

### 2.3. Phân biệt ba loại “phiên” thường gặp

| Khái niệm | Được dùng để làm gì? | Khi kết nối mạng bị ngắt |
|---|---|---|
| **TCP connection** | Truyền luồng byte đáng tin cậy giữa hai socket | Kết nối đã mất thường phải được tạo lại |
| **TLS connection/session** | Xác thực đầu cuối theo cấu hình, mã hóa và bảo vệ tính toàn vẹn kênh truyền; có cơ chế tiếp tục bắt tay TLS | Kênh có thể được tạo lại; việc tiếp tục TLS phụ thuộc phiên bản, chính sách và khả năng của hai đầu |
| **Application/login session** | Gắn các yêu cầu với trạng thái đăng nhập, danh tính hoặc ngữ cảnh công việc | Có thể vẫn hợp lệ sau khi mở kết nối mới, nếu trạng thái phiên chưa hết hạn hoặc bị thu hồi |

Ví dụ: người dùng đăng nhập một website, đóng tab, rồi mở lại trang. Kết nối TCP và TLS mới có thể được tạo ra, nhưng website vẫn nhận ra phiên đăng nhập nếu cookie còn hợp lệ và phía máy chủ chấp nhận phiên.

Ngược lại, kết nối TCP còn mở **không chứng minh** người dùng vẫn có quyền truy cập. Ứng dụng phải đánh giá danh tính và quyền tại điểm thực hiện thao tác quan trọng.

## 3. Tầng Application (tầng 7): giao thức phục vụ ứng dụng

Tầng Application là nơi các tiến trình sử dụng **quy tắc giao tiếp mạng có ý nghĩa nghiệp vụ**: cách đặt câu hỏi DNS, gửi email, yêu cầu trang web, truy cập tệp hoặc gọi API. Tầng này không đồng nghĩa với toàn bộ phần mềm giao diện mà người dùng nhìn thấy.

### 3.1. Những giao thức tiêu biểu

| Giao thức/dịch vụ | Công dụng | Cổng thường gặp | Điểm cần quan sát khi phân tích bảo mật |
|---|---|---|---|
| **HTTP** | Truyền yêu cầu và phản hồi web/API | TCP 80; HTTP/3 chạy trên QUIC, thường UDP 443 khi dùng HTTPS | Method, đường dẫn, header, mã phản hồi, chính sách xác thực |
| **HTTPS** (HTTP qua TLS) | Bảo vệ HTTP bằng TLS | Thường TCP 443; HTTP/3 thường UDP 443 | Chứng chỉ, tên miền, phiên bản TLS, cấu hình máy chủ, quyền ở ứng dụng |
| **DNS** | Phân giải tên miền và truy vấn bản ghi | UDP/TCP 53; DoT thường TCP 853; DoH thường HTTPS 443 | Kết quả phân giải, giả mạo DNS, rò rỉ truy vấn, cấu hình resolver |
| **SMTP** | Chuyển hoặc gửi thư | TCP 25 giữa máy chủ; submission thường TCP 587; implicit TLS thường TCP 465 | Xác thực gửi thư, STARTTLS/TLS, chống giả mạo nguồn gửi |
| **IMAP** | Đồng bộ và đọc hộp thư | TCP 143; IMAP qua TLS thường TCP 993 | Bảo vệ thông tin đăng nhập, phân quyền hộp thư |
| **SSH** | Quản trị từ xa và tạo kênh bảo mật | TCP 22 | Khóa máy chủ, khóa người dùng, giới hạn đăng nhập và lệnh |

**Cổng chỉ là quy ước phổ biến**, không phải bằng chứng chắc chắn về giao thức đang chạy. Một dịch vụ có thể dùng cổng tùy chỉnh; kỹ thuật kiểm tra cần kết hợp cấu hình, bắt tay giao thức và log.

### 3.2. HTTP biểu diễn nghiệp vụ như thế nào?

Ví dụ yêu cầu đọc hồ sơ:

~~~http
GET /api/profile HTTP/1.1
Host: portal.example
Accept: application/json
Cookie: __Host-session=<opaque-session-id>
~~~

Một phản hồi hợp lệ có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"displayName":"Lan","role":"student"}
~~~

Tầng ứng dụng quy định đường dẫn `/api/profile`, method `GET`, header, dạng JSON và ý nghĩa của mã `200`. TCP đảm nhận truyền luồng dữ liệu khi sử dụng HTTP/1.1 hoặc HTTP/2; TLS bảo vệ dữ liệu truyền trong HTTPS. **Máy chủ ứng dụng mới là nơi quyết định** cookie tương ứng với ai và người đó có được xem hồ sơ hay không.

HTTP về nguyên tắc là giao thức **stateless**: từng yêu cầu không tự mang theo toàn bộ lịch sử trước đó. Website tạo trải nghiệm đăng nhập liên tục bằng cookie, session ID, token hoặc các cơ chế trạng thái bổ sung.

## 4. Một lượt truy cập HTTPS có đăng nhập diễn ra ra sao?

Xét người dùng mở `https://portal.example` và đăng nhập:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant D as DNS resolver
    participant G as HTTPS gateway
    participant A as Ứng dụng
    participant S as Kho lưu phiên

    B->>D: Phân giải portal.example
    D-->>B: Địa chỉ IP
    B->>G: Thiết lập TCP + TLS (hoặc QUIC + TLS)
    B->>G: POST /login qua HTTPS
    G->>A: Chuyển yêu cầu đăng nhập
    A->>A: Xác minh thông tin đăng nhập
    A->>S: Tạo và lưu trạng thái phiên
    S-->>A: Đã lưu
    A-->>B: Set-Cookie chứa mã phiên
    B->>G: GET /api/profile + Cookie
    G->>A: Chuyển yêu cầu
    A->>S: Kiểm tra phiên còn hiệu lực
    S-->>A: Danh tính / trạng thái
    A->>A: Kiểm tra quyền xem hồ sơ
    A-->>B: Trả dữ liệu được phép truy cập
~~~

Sơ đồ giả định TLS được kết thúc tại gateway và ứng dụng dùng **session lưu phía máy chủ**. Một hệ thống khác có thể kết thúc TLS ngay tại dịch vụ, không dùng gateway, hoặc xác thực token mà không có kho phiên; các lớp chức năng vẫn có ý nghĩa tương tự.

Diễn giải theo chức năng:

1. **DNS (Application):** xác định địa chỉ cần truy cập. Kết quả DNS phải được xem xét cùng các cơ chế bảo vệ và chính sách tin cậy.
2. **Transport và bảo mật kênh:** TCP/TLS (HTTP/1.1 hoặc HTTP/2) hay QUIC/TLS (HTTP/3) tạo kênh truyền; trình duyệt kiểm tra chứng chỉ và tên miền theo quy tắc xác thực TLS.
3. **Application:** `POST /login` gửi dữ liệu để dịch vụ xác thực tài khoản.
4. **Quản lý phiên:** ứng dụng tạo mã phiên khó đoán, gắn nó với ngữ cảnh tài khoản và thời hạn, rồi yêu cầu trình duyệt lưu cookie.
5. **Application và kiểm soát truy cập:** mỗi yêu cầu nhạy cảm phải xác minh phiên/token và **quyền đối với tài nguyên cụ thể**.

Nếu gateway kết thúc TLS, đoạn mạng từ gateway đến ứng dụng cần được bảo vệ phù hợp với mô hình đe dọa (chẳng hạn TLS nội bộ hoặc mTLS). Mã hóa kết nối bên ngoài không tự bảo vệ chặng nội bộ.

## 5. Thiết kế phiên đăng nhập cho ứng dụng web

### 5.1. Phiên lưu trên máy chủ (stateful session)

Một cách phổ biến là tạo mã định danh **ngẫu nhiên, đủ mạnh, không có ý nghĩa nghiệp vụ**, rồi lưu dữ liệu liên quan trong bộ nhớ hoặc kho phiên:

~~~text
Trình duyệt:
  Cookie: __Host-session=<random-opaque-id>

Kho phiên phía máy chủ:
  hash/khóa tra cứu mã phiên -> userId, createdAt, expiresAt, trạng thái, ...

Mỗi yêu cầu:
  nhận mã -> tra cứu -> kiểm tra hết hạn/thu hồi -> kiểm tra quyền
~~~

Không đưa mật khẩu, thông tin bí mật hoặc dữ liệu người dùng nhạy cảm trực tiếp vào giá trị cookie. Trong hệ thống nhiều máy chủ, cần kho phiên dùng chung hoặc chiến lược quản lý trạng thái nhất quán; chỉ dựa vào RAM của một instance có thể làm mất đăng nhập khi chuyển máy hoặc khởi động lại.

Một header cookie có cấu hình bảo vệ cơ bản:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<random-opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

| Thuộc tính | Tác dụng |
|---|---|
| `Secure` | Chỉ gửi cookie qua kết nối bảo mật theo quy tắc của trình duyệt |
| `HttpOnly` | Không cho JavaScript đọc cookie qua `document.cookie`; không ngăn mọi tác động của XSS |
| `SameSite=Lax` hoặc `Strict` | Giảm một số tình huống gửi cookie từ ngữ cảnh cross-site; chọn theo luồng đăng nhập và yêu cầu sản phẩm |
| `Path=/` | Giới hạn phạm vi đường dẫn mà cookie được gửi |
| Tiền tố `__Host-` | Trên trình duyệt hỗ trợ, yêu cầu `Secure`, `Path=/` và **không có** thuộc tính `Domain`, giúp hạn chế phạm vi cookie |

**SameSite không thay thế hoàn toàn biện pháp chống CSRF.** Với các thao tác thay đổi trạng thái, cân nhắc CSRF token, kiểm tra `Origin`/`Referer` theo chính sách, đồng thời thiết kế method và CORS đúng mục đích.

Thời hạn phía trình duyệt và thời hạn phiên phía máy chủ là **hai phép kiểm tra riêng**. Chẳng hạn, chính sách có thể hết hạn sau 15 phút không hoạt động và tối đa 8 giờ kể từ đăng nhập; đây chỉ là ví dụ, cần chọn theo mức độ nhạy cảm và nhu cầu thực tế. Đăng xuất phải **vô hiệu hóa phiên tại phía máy chủ** khi có trạng thái lưu trên máy chủ, đồng thời xóa cookie khỏi trình duyệt.

### 5.2. Token tự chứa (ví dụ JWT)

Một số hệ thống dùng **access token** có chữ ký số thay cho tra cứu phiên truyền thống. Token có thể mang các claim như chủ thể, thời điểm hết hạn, tổ chức phát hành và đối tượng nhận.

Máy chủ nhận token phải kiểm tra **chữ ký và thuật toán được phép**, `iss` (issuer), `aud` (audience), `exp` (expiry), các ràng buộc khác và quyền truy cập tài nguyên. Token được ký **không mặc nhiên được mã hóa**: payload của JWT dạng JWS thông thường có thể đọc được, vì vậy không đặt bí mật vào đó.

| Tiêu chí | Session ID + trạng thái phía máy chủ | Access token tự chứa |
|---|---|---|
| Xác minh | Tra cứu hoặc kiểm tra trạng thái phiên ở phía máy chủ | Kiểm tra chữ ký, claim và chính sách |
| Thu hồi ngay lập tức | Thường thuận tiện khi xóa/vô hiệu hóa bản ghi phiên | Cần thời hạn ngắn, danh sách thu hồi hoặc cơ chế quản lý bổ sung nếu muốn thu hồi sớm |
| Mở rộng nhiều instance | Cần chia sẻ trạng thái hoặc một cơ chế nhất quán | Có thể xác minh tại nhiều instance bằng khóa và chính sách chung |
| Rủi ro chính | Lộ session ID, lỗi kho phiên, hết hạn không đúng | Lộ token, xác minh claim sai, quản lý khóa hoặc thu hồi không phù hợp |

Cả hai cơ chế đều có thể bị lạm dụng nếu kẻ tấn công lấy được thông tin xác thực dạng bearer. Nơi lưu token, cách vận chuyển và thời hạn sống phải được thiết kế theo kiểu ứng dụng; không có một cách lưu token phía trình duyệt phù hợp cho mọi hệ thống.

### 5.3. Xác thực khác với phân quyền

- **Authentication (xác thực):** xác định chủ thể là ai, ví dụ hoàn thành đăng nhập hoặc xác minh token.
- **Authorization (phân quyền):** quyết định chủ thể được thao tác gì trên tài nguyên nào, ví dụ chỉ đọc hồ sơ của chính mình.
- **Session management (quản lý phiên):** duy trì, đổi mới, hết hạn và thu hồi ngữ cảnh dùng giữa các yêu cầu.

Một `GET /api/users/42` có session hợp lệ vẫn phải bị từ chối nếu người dùng không có quyền xem tài khoản 42. Đây là lỗi **kiểm soát truy cập đối tượng** khi bị bỏ qua, dù HTTPS và cơ chế đăng nhập hoạt động tốt.

## 6. Đe dọa thường gặp ở phần phiên và ứng dụng

| Nguy cơ | Biểu hiện | Biện pháp phòng vệ chủ đạo |
|---|---|---|
| **Session hijacking** | Kẻ khác dùng session ID hoặc token đã bị lộ | TLS toàn tuyến phù hợp, `Secure`/`HttpOnly`, tránh ghi token vào log, thời hạn hợp lý, thu hồi phiên và phát hiện bất thường |
| **Session fixation** | Nạn nhân đăng nhập bằng session ID do kẻ khác định trước | Tạo hoặc xoay session ID sau khi xác thực và khi thay đổi đặc quyền; từ chối ID phiên không hợp lệ |
| **CSRF** | Trình duyệt đã đăng nhập bị dụ gửi yêu cầu đổi trạng thái | CSRF token khi phù hợp, `SameSite`, xác minh nguồn yêu cầu, bảo vệ endpoint nhạy cảm |
| **XSS** | Mã độc chạy trong ngữ cảnh trang, có thể thao tác thay người dùng | Escape/encode theo ngữ cảnh, hạn chế HTML không tin cậy, CSP phù hợp, kiểm soát nguồn script |
| **Replay** | Một thông điệp hoặc token hợp lệ bị phát lại trái mục đích | Nonce/idempotency key khi cần, giới hạn thời gian, kiểm soát phát lại ở tác vụ quan trọng; thận trọng với TLS 1.3 0-RTT |
| **Lạm dụng đăng nhập/API** | Thử nhiều mật khẩu hoặc gọi API vượt ngưỡng | Giới hạn tốc độ theo ngữ cảnh, MFA cho tài khoản phù hợp, giám sát sự kiện, kiểm tra quyền tại endpoint |
| **Giả mạo/chuyển hướng DNS** | Người dùng bị đưa tới đích ngoài mong muốn | Resolver tin cậy, DNSSEC khi áp dụng, xác minh chứng chỉ/tên máy chủ TLS, giám sát cấu hình DNS |

Một số nguyên tắc vận hành cần giữ:

1. **Bảo vệ bí mật phiên:** session ID, access token, refresh token và thông tin xác thực không xuất hiện trong URL, log, số liệu theo dõi hoặc thông báo lỗi.
2. **Xoay phiên khi tăng đặc quyền:** sau đăng nhập, đổi mật khẩu hoặc nâng quyền, không tiếp tục tin một session ID do người dùng chưa xác thực cung cấp.
3. **Kiểm tra tại mỗi thao tác:** xác minh quyền với tài nguyên thực tế, không chỉ ẩn nút thao tác ở giao diện.
4. **Quản lý vòng đời:** đặt thời hạn không hoạt động và thời hạn tối đa, thu hồi khi đăng xuất hoặc có tín hiệu rủi ro, đồng bộ cơ chế thu hồi giữa các instance.
5. **Phòng vệ mạng và ứng dụng cùng lúc:** firewall/WAF, TLS, phân đoạn mạng, IDS/IPS và giám sát lưu lượng hỗ trợ giảm bề mặt tấn công; chúng không thay thế logic xác thực và phân quyền trong ứng dụng.

## 7. Quan sát và xử lý sự cố

### 7.1. Thực hành kiểm tra an toàn

Trên máy có công cụ tương ứng, có thể quan sát kết quả phân giải tên miền và header HTTP bằng các lệnh chỉ đọc:

~~~powershell
nslookup example.com
curl.exe -I https://example.com/
curl.exe -v -I https://example.com/
~~~

- `nslookup` cho biết phản hồi DNS theo resolver mà máy đang dùng. Kết quả không tự chứng minh đích cuối cùng là đáng tin.
- `curl.exe -I` yêu cầu chỉ lấy response header; kết quả có thể gồm mã HTTP, `Content-Type`, `Cache-Control` hoặc chính sách cookie nếu dịch vụ thiết lập.
- `curl.exe -v` hỗ trợ quan sát quá trình kết nối/TLS và header phục vụ gỡ lỗi. Chỉ dùng với dịch vụ được phép kiểm tra; không chia sẻ bản ghi verbose nếu chứa cookie, token hay header xác thực.

Các ví dụ dùng miền `example.com` cho mục đích minh họa. Header thực tế phụ thuộc dịch vụ và không nhất thiết có `Set-Cookie`.

### 7.2. Phân biệt lỗi theo lớp

| Triệu chứng | Nên kiểm tra đầu tiên | Không nên kết luận vội |
|---|---|---|
| Không phân giải được tên miền | DNS resolver, bản ghi, đường đi tới DNS, chính sách chặn | Ứng dụng đăng nhập bị lỗi |
| Lỗi chứng chỉ hoặc bắt tay TLS | Tên miền, chuỗi chứng chỉ, thời gian hệ thống, cấu hình TLS | Cookie phiên đã hết hạn |
| Truy cập được trang nhưng liên tục phải đăng nhập lại | Cookie/thuộc tính cookie, hết hạn, chia sẻ kho phiên, vòng đời token, đồng hồ giữa các hệ thống | Chắc chắn do TCP mất kết nối |
| API trả `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực, phiên/token hết hạn | Người dùng không có quyền với tài nguyên cụ thể |
| API trả `403 Forbidden` | Chính sách quyền và trạng thái chủ thể; cũng có thể do cơ chế bảo vệ khác từ chối | TLS hoặc DNS đang hỏng |
| Chỉ lỗi sau khi chuyển sang máy chủ khác | Kho phiên dùng chung, khóa xác minh token, cấu hình cân bằng tải | Cần mở thêm cổng firewall bên ngoài |

Mã `401` và `403` có ý nghĩa HTTP theo ngữ cảnh xác thực/phân quyền; cách dịch vụ triển khai cụ thể có thể khác. Hãy kết hợp **log ứng dụng, log gateway, DNS và quan sát kết nối**, gắn chúng bằng request ID hoặc correlation ID, đồng thời che thông tin nhạy cảm.

### 7.3. Trường hợp thực tế: dịch vụ chạy trên nhiều instance

Giả sử ứng dụng có hai instance A và B sau load balancer:

1. Người dùng đăng nhập qua A; A tạo session ID nhưng chỉ lưu trạng thái vào RAM của A.
2. Yêu cầu kế tiếp được chuyển tới B; B không biết session ID và trả yêu cầu đăng nhập lại.
3. Hệ thống khắc phục bằng kho phiên chia sẻ được bảo vệ phù hợp, hoặc thiết kế token và xác minh nhất quán giữa các instance.

Sticky session ở load balancer có thể giảm triệu chứng nhưng không tự giải quyết việc mất trạng thái khi A ngừng hoạt động. Dù chọn cách nào, vẫn phải bảo vệ session ID/token, đặt thời hạn và thực thi phân quyền ở ứng dụng.

## 8. Những nhầm lẫn cần tránh

- **“Tầng Session của OSI chính là TCP.”** Sai: TCP vận chuyển byte và quản lý trạng thái kết nối ở tầng transport; OSI Session nói về việc điều phối hội thoại logic.
- **“Mọi phiên web đều dùng giao thức tầng 5 riêng.”** Sai: session web thường do ứng dụng và framework quản lý trên nền HTTP.
- **“HTTPS đồng nghĩa đã đăng nhập và có quyền.”** Sai: HTTPS bảo vệ kênh truyền, còn xác thực và phân quyền phải do hệ thống nghiệp vụ thực hiện.
- **“Cookie chứa tài khoản đã được mã hóa nên an toàn.”** Không được mặc định như vậy: cookie có thể chỉ là mã tham chiếu hoặc chứa token; thiết kế và cách bảo vệ giá trị của nó mới quyết định rủi ro.
- **“JWT có chữ ký thì nội dung được giữ bí mật.”** Sai: chữ ký chống sửa đổi không đồng nghĩa mã hóa payload.
- **“Đã có WAF/IDS/IPS thì không cần kiểm tra quyền API.”** Sai: các lớp phòng vệ hạ tầng hỗ trợ phát hiện/ngăn chặn lưu lượng đáng ngờ, nhưng không hiểu đầy đủ quyền trên từng bản ghi nghiệp vụ.

## 9. Vận dụng vào thiết kế kiến trúc bảo mật mạng

Khi thiết kế hoặc đánh giá một dịch vụ mới, hãy lần lượt truy theo chuỗi:

**Tên miền → kết nối → bảo vệ kênh → giao thức ứng dụng → xác thực → phiên → phân quyền → ghi log và thu hồi.**

Ví dụ đối với cổng quản trị nội bộ:

- Kiểm soát DNS, giới hạn nguồn truy cập bằng phân đoạn mạng và firewall.
- Dùng HTTPS/TLS phù hợp, xác minh chứng chỉ đúng tên miền; cân nhắc mTLS giữa gateway và backend nếu mô hình đe dọa yêu cầu.
- Bảo vệ đăng nhập bằng cơ chế xác thực mạnh phù hợp, hạn chế thử mật khẩu, xoay định danh phiên sau xác thực.
- Cấu hình cookie an toàn hoặc triển khai kiểm tra token nhất quán; xử lý hết hạn, đăng xuất và thu hồi.
- Kiểm tra phân quyền trên từng API và đối tượng được thao tác; ghi sự kiện an ninh không kèm bí mật.
- Theo dõi dấu hiệu bất thường trong cả lưu lượng mạng lẫn log ứng dụng để điều tra sự cố theo ngữ cảnh.

**Điểm cốt lõi:** tầng 5 giúp hình dung *vòng đời và trạng thái hội thoại*; tầng 7 giúp hiểu *ngữ nghĩa giao thức và hành động ứng dụng*. Trong hệ thống hiện đại, hai nhóm chức năng này có thể được hiện thực cùng một nơi. Thiết kế bảo mật tốt phải nhận diện đúng trạng thái nào cần bảo vệ, ai có quyền sử dụng trạng thái đó và các lớp mạng hỗ trợ kiểm soát ra sao.
