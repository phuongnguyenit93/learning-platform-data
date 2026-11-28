# HTTP và HTTPS: giao tiếp Web và bảo vệ dữ liệu trên mạng

HTTP (Hypertext Transfer Protocol) là giao thức ứng dụng dùng để trao đổi yêu cầu và phản hồi giữa client (trình duyệt, ứng dụng di động, dịch vụ gọi API) với server. HTTPS là HTTP được truyền qua một kết nối có bảo vệ bằng TLS (Transport Layer Security). Hai giao thức xuất hiện trong gần như mọi hoạt động Web, API, đăng nhập và quản trị hệ thống. Đối với **an ninh mạng**, hiểu HTTP/HTTPS giúp phân tích lưu lượng, nhận diện nguy cơ nghe lén hoặc giả mạo máy chủ, thiết kế điểm kết thúc TLS và cấu hình lớp phòng vệ thích hợp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Đặt HTTP, HTTPS, TLS, TCP, UDP, QUIC và IP vào đúng vị trí trong mô hình OSI và ngăn xếp TCP/IP.
2. Đọc một HTTP request/response, giải thích ý nghĩa method, URL, header, body và mã trạng thái.
3. Mô tả các bước kết nối HTTPS, cách chứng chỉ số xác thực máy chủ và phạm vi bảo vệ của TLS.
4. Phân biệt HTTP/1.1, HTTP/2 và HTTP/3, đặc biệt là giao thức vận chuyển bên dưới.
5. Chọn các biện pháp bảo vệ cookie, session, HTTP header, reverse proxy và kiểm tra lưu lượng khi xử lý sự cố.

## 2. HTTP nằm ở đâu trong mô hình OSI?

HTTP là giao thức ở **tầng ứng dụng (Application, tầng 7)** của OSI. Trong ngăn xếp TCP/IP, HTTP thuộc tầng ứng dụng; bên dưới là các thành phần vận chuyển và mạng.

| Thành phần | Vai trò | Liên hệ với HTTP/HTTPS |
| --- | --- | --- |
| Tầng ứng dụng OSI / TCP/IP | Quy tắc trao đổi dữ liệu giữa các chương trình | HTTP quy định request, response, method, header, status và ngữ nghĩa tài nguyên |
| TLS | Mã hóa, bảo đảm toàn vẹn và xác thực đầu cuối kết nối | HTTPS sử dụng TLS để bảo vệ dữ liệu HTTP; TLS không khớp cứng với một tầng OSI duy nhất |
| TCP (tầng vận chuyển) | Truyền byte đáng tin cậy, có thứ tự | HTTP/1.1 và HTTP/2 thông dụng chạy trên TCP |
| QUIC trên UDP (tầng vận chuyển) | Kết nối bảo mật và nhiều luồng truyền độc lập | HTTP/3 dùng QUIC; TLS 1.3 được tích hợp vào quá trình thiết lập QUIC |
| IP (tầng mạng) | Định địa chỉ và định tuyến gói tin | Chuyển gói giữa client, router, firewall và server |
| Ethernet/Wi-Fi (tầng liên kết) | Truyền frame trên liên kết cục bộ | Mang các gói IP qua mạng có dây hoặc không dây |

Minh họa các ngăn xếp thường gặp:

~~~text
HTTP/1.1 và HTTP/2                  HTTP/3
┌─────────────────────┐             ┌─────────────────────┐
│ HTTP                │             │ HTTP                │
├─────────────────────┤             ├─────────────────────┤
│ TLS (khi dùng HTTPS)│             │ QUIC + TLS 1.3      │
├─────────────────────┤             ├─────────────────────┤
│ TCP                 │             │ UDP                 │
├─────────────────────┤             ├─────────────────────┤
│ IP                  │             │ IP                  │
└─────────────────────┘             └─────────────────────┘
~~~

**Phân biệt với DNS:** DNS giúp tìm địa chỉ IP tương ứng với tên miền trước khi kết nối, nhưng DNS là một giao thức khác HTTP. Truy vấn DNS truyền thống có thể lộ tên miền; DNS over HTTPS (DoH) hoặc DNS over TLS (DoT) là các cơ chế bảo vệ riêng.

## 3. HTTP hoạt động như thế nào?

### 3.1. Mô hình request–response

Client tạo một yêu cầu chỉ rõ hành động muốn làm với tài nguyên, chẳng hạn đọc danh sách sản phẩm, tải ảnh hoặc gửi biểu mẫu. Server xử lý và trả một phản hồi kèm mã trạng thái và có thể có nội dung.

Ví dụ dạng văn bản của **HTTP/1.1**:

~~~http
GET /api/products?page=2 HTTP/1.1
Host: shop.example.test
Accept: application/json
User-Agent: LearningClient/1.0

~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: public, max-age=60

{"items":[{"id":101,"name":"Router"}],"page":2}
~~~

Trong ví dụ này:

- **Method GET** yêu cầu lấy biểu diễn của tài nguyên.
- **Path /api/products** xác định tài nguyên trên server; **query page=2** bổ sung tham số.
- **Host** chỉ tên máy chủ đích, quan trọng khi nhiều website dùng chung địa chỉ IP.
- **Accept** cho biết client muốn nhận định dạng nào; **Content-Type** mô tả định dạng của body phản hồi.
- **200 OK** báo yêu cầu thành công; **Cache-Control** hướng dẫn việc lưu cache.
- Dòng trống ngăn cách phần header với body. HTTP có thể truyền văn bản, JSON, ảnh, video và dữ liệu nhị phân; không chỉ truyền HTML.

Các ví dụ ở trên thể hiện cú pháp HTTP/1.1 để dễ đọc. HTTP/2 và HTTP/3 trao đổi thông tin tương đương bằng **frame nhị phân**, không truyền nguyên văn dòng mở đầu như HTTP/1.1.

### 3.2. URL, method và tính chất thao tác

Một URL như **https://shop.example.test:443/api/products?page=2** có scheme (https), hostname, port tùy chọn, path và query. Fragment sau dấu # được xử lý ở client và không được gửi trong HTTP request thông thường. Với HTTPS, path, query, header và body được mã hóa trong quá trình truyền; nhưng hostname có thể vẫn bị suy đoán từ DNS, địa chỉ IP hay thông tin bắt tay TLS.

| Method | Mục đích thông dụng | Safe? | Idempotent? |
| --- | --- | --- | --- |
| GET | Đọc tài nguyên | Có | Có |
| HEAD | Lấy metadata/header như GET nhưng không có body phản hồi | Có | Có |
| OPTIONS | Hỏi khả năng giao tiếp/các tùy chọn | Có | Có |
| POST | Gửi dữ liệu để server xử lý, thường tạo tác vụ hoặc tài nguyên | Không | Không bảo đảm |
| PUT | Tạo/thay thế trạng thái của tài nguyên tại URI xác định | Không | Có |
| PATCH | Chỉnh sửa một phần tài nguyên | Không | Không bảo đảm |
| DELETE | Yêu cầu xóa tài nguyên | Không | Có |

**Safe** nghĩa là ngữ nghĩa method không yêu cầu thay đổi trạng thái ứng dụng; **idempotent** nghĩa là lặp cùng một yêu cầu có cùng *tác động dự định* lên trạng thái server như thực hiện một lần. Idempotent không đồng nghĩa phản hồi lặp luôn có cùng status: DELETE lần đầu có thể trả 204, lần sau trả 404. Triển khai server vẫn phải tuân thủ các ngữ nghĩa này; một API viết sai có thể gây thay đổi dữ liệu qua GET.

### 3.3. Nhóm mã trạng thái HTTP

| Nhóm / mã | Diễn giải | Điều cần chú ý |
| --- | --- | --- |
| 1xx | Thông tin trung gian | Ví dụ 100 Continue |
| 200, 201, 204 | Thành công, tạo mới, thành công nhưng không có nội dung trả về | 204 không có response body |
| 301, 302, 307, 308 | Chuyển hướng | 307/308 giữ nguyên method khi chuyển hướng; 301/302 có thể được client đổi POST thành GET |
| 304 | Nội dung cache còn hợp lệ | Thường dùng với ETag/If-None-Match hoặc Last-Modified/If-Modified-Since |
| 400, 401, 403, 404, 405 | Request sai, cần xác thực, bị cấm, không tìm thấy, method không hỗ trợ | 401 khác 403; không dùng 403 thay cho kiểm tra quyền truy cập |
| 408, 429 | Hết thời gian yêu cầu, quá nhiều yêu cầu | 429 thường đi kèm chính sách giới hạn tốc độ |
| 500, 502, 503, 504 | Lỗi server, upstream không hợp lệ, tạm không phục vụ, gateway hết thời gian | Hữu ích khi điều tra proxy, load balancer và ứng dụng |

Không nên coi status 200 là bằng chứng giao dịch an toàn. Một endpoint có thể trả 200 nhưng làm lộ dữ liệu do kiểm tra phân quyền sai.

### 3.4. HTTP có trạng thái hay không?

Về bản chất HTTP là giao thức **stateless**: mỗi request có thể được hiểu độc lập. Ứng dụng vẫn triển khai phiên đăng nhập bằng cookie, session ID, token hoặc kho lưu trạng thái phía server. Sự khác biệt này đặc biệt quan trọng khi thiết kế bảo mật: việc có HTTPS không đồng nghĩa session được quản lý đúng.

## 4. HTTPS bổ sung điều gì?

Với kết nối HTTPS hợp lệ, TLS cung cấp ba tính chất chính:

1. **Bí mật (confidentiality):** người nghe lén trên đường truyền không thể trực tiếp đọc nội dung HTTP.
2. **Toàn vẹn (integrity):** phát hiện việc sửa đổi dữ liệu được bảo vệ trong quá trình truyền.
3. **Xác thực máy chủ (server authentication):** client kiểm tra chứng chỉ để xác nhận đầu kết nối có quyền sử dụng tên miền yêu cầu, theo chuỗi tin cậy của CA (Certificate Authority).

HTTPS thường dùng cổng **443**; HTTP không mã hóa thường dùng cổng **80**. Đây là cổng mặc định, không phải ràng buộc bắt buộc. Chẳng hạn, HTTPS có thể chạy trên cổng 8443.

| Tiêu chí | HTTP truyền trực tiếp (thường là http://) | HTTPS (https://) |
| --- | --- | --- |
| Nội dung truyền trên mạng | Có thể bị đọc hoặc sửa bởi bên trung gian | Được TLS mã hóa và kiểm tra toàn vẹn |
| Xác thực danh tính server bằng chứng chỉ | Không có trong HTTP truyền trực tiếp | Có, nếu client xác minh chứng chỉ hợp lệ |
| Nguy cơ nghe lén mật khẩu/cookie | Cao khi truyền thông tin nhạy cảm | Giảm đáng kể trên đường truyền |
| Chống XSS, SQL injection, CSRF, lỗi phân quyền | Không | Cũng không; cần cơ chế bảo vệ tầng ứng dụng riêng |
| Cổng mặc định | 80 | 443 |

**Giới hạn của HTTPS:** TLS bảo vệ kết nối giữa các điểm kết thúc TLS. Nó không bảo đảm website là đáng tin về nội dung, không che hoàn toàn danh tính đích đến (địa chỉ IP, đôi khi DNS/SNI), không chống phần mềm độc hại trên thiết bị đầu cuối và không tự ngăn được dữ liệu bị lộ từ ứng dụng sau khi giải mã.

### 4.1. Trình tự truy cập một website HTTPS

Ví dụ client truy cập https://portal.example.test:

~~~mermaid
sequenceDiagram
    participant C as Trình duyệt
    participant D as DNS
    participant S as Máy chủ / Reverse proxy
    C->>D: Tra cứu portal.example.test
    D-->>C: Trả địa chỉ IP
    Note over C,S: HTTP/1.1 hoặc 2: kết nối TCP
    Note over C,S: HTTP/3: QUIC trên UDP
    C->>S: Khởi tạo TLS và đề xuất giao thức
    S-->>C: Chứng chỉ, tham số bảo mật
    Note over C: Kiểm tra hostname, CA, hiệu lực chứng chỉ
    C->>S: HTTP request trong kênh đã bảo vệ
    S-->>C: HTTP response trong kênh đã bảo vệ
~~~

Các bước quan trọng:

1. Client xác định tên miền và địa chỉ đích (có thể sử dụng cache DNS).
2. Client thiết lập kết nối vận chuyển. Với HTTP/1.1 hoặc HTTP/2 thông dụng, đó là TCP; với HTTP/3, đó là QUIC qua UDP.
3. TLS thương lượng thuật toán và khóa phiên, đồng thời cung cấp chứng chỉ máy chủ. Client kiểm tra chuỗi CA tin cậy, thời hạn, tên miền trong trường **Subject Alternative Name (SAN)** và các điều kiện xác minh liên quan.
4. Client chỉ nên gửi thông tin nhạy cảm khi việc xác minh thành công. Với HTTP/2 qua TLS, giao thức thường được thương lượng bằng **ALPN** (ví dụ h2); HTTP/3 sử dụng QUIC với ALPN h3.
5. Các bản tin HTTP đi trong kênh đã bảo vệ. Trong TLS 1.3, khóa phiên được sinh từ quá trình thỏa thuận khóa; chứng chỉ giúp xác thực, chứ không phải được dùng để mã hóa mọi byte HTTP bằng khóa công khai.

Nếu chứng chỉ hết hạn, sai hostname hoặc không thuộc chuỗi tin cậy, trình duyệt có thể cảnh báo hoặc chặn truy cập. Việc bỏ qua cảnh báo chứng chỉ trên hệ thống thật làm mất một phần quan trọng của cơ chế chống giả mạo.

### 4.2. TLS 1.2, TLS 1.3 và chứng chỉ

- **TLS 1.3** là lựa chọn ưu tiên cho kết nối hiện đại; TLS 1.2 vẫn có thể cần cho tính tương thích nếu được cấu hình an toàn.
- Không nên cho phép SSL cũ, TLS 1.0 hoặc TLS 1.1 trên dịch vụ công khai hiện đại.
- Chứng chỉ cần có hostname đúng, thời hạn hợp lệ, khóa riêng được bảo vệ, chuỗi CA được cấu hình đầy đủ và cơ chế gia hạn/giám sát trước khi hết hạn.
- Có thể sử dụng **mTLS (mutual TLS)** khi *cả client và server* đều xác thực chứng chỉ; đây là lựa chọn cho một số kết nối nội bộ hoặc API đối tác, không phải yêu cầu mặc định của HTTPS công cộng.
- Sau khi reverse proxy hoặc load balancer kết thúc TLS, kết nối từ proxy đến backend là **một chặng riêng**: cần đánh giá và bảo vệ chặng đó, nhất là khi vượt mạng hoặc vùng tin cậy.

## 5. HTTP/1.1, HTTP/2 và HTTP/3 khác nhau ra sao?

| Phiên bản | Giao thức vận chuyển thông dụng | Đặc điểm chính | Lưu ý an ninh / vận hành |
| --- | --- | --- | --- |
| HTTP/1.1 | TCP; thêm TLS nếu dùng HTTPS | Bản tin dạng văn bản, kết nối duy trì, mỗi kết nối xử lý yêu cầu theo thứ tự; có thể mở nhiều kết nối | Dễ phân tích request dạng văn bản khi không mã hóa |
| HTTP/2 | TCP + TLS trên trình duyệt thông dụng | Frame nhị phân; nhiều stream cùng kết nối; nén header HPACK | Nhiều stream vẫn chia sẻ một TCP, nên mất gói ở TCP có thể cản các stream |
| HTTP/3 | QUIC qua UDP, tích hợp TLS 1.3 | Nhiều stream độc lập ở lớp QUIC; giảm ảnh hưởng mất gói giữa các stream | Cần chính sách firewall/giám sát cho UDP; thiết bị chỉ nhìn TCP/443 có thể bỏ sót lưu lượng |

Chú ý:

- HTTP/2 có chế độ **h2c** không dùng TLS trong một số môi trường, nhưng trình duyệt thông thường dùng HTTP/2 qua HTTPS.
- HTTP/3 dựa trên QUIC và bắt buộc có bảo vệ mật mã tương ứng; không phải HTTP/2 đơn giản chuyển sang UDP.
- HTTP/3 có thể được quảng bá qua **Alt-Svc** hoặc cơ chế khám phá phù hợp; client có thể dùng HTTP/2 hoặc HTTP/1.1 nếu không dùng được HTTP/3.
- Phiên bản HTTP không quyết định quyền truy cập hay độ an toàn của logic ứng dụng; các kiểm soát phân quyền, logging, giới hạn tốc độ vẫn phải thực hiện.

## 6. Các header và cơ chế bảo mật thường gặp

### 6.1. Cookie và phiên đăng nhập

Một server có thể trả header:

~~~http
Set-Cookie: session_id=<opaque_value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| Secure | Trình duyệt chỉ gửi cookie qua kết nối bảo mật (với một số ngoại lệ môi trường cục bộ) | Không mã hóa cookie ở nơi lưu trữ hoặc tại server |
| HttpOnly | JavaScript trên trang không trực tiếp đọc được cookie | XSS vẫn có thể kích hoạt request thay mặt người dùng |
| SameSite=Lax/Strict | Hạn chế một số tình huống gửi cookie xuyên site | Không thay thế toàn bộ biện pháp chống CSRF |
| Path và Domain | Xác định phạm vi cookie được gửi | Phải giới hạn chặt để giảm chia sẻ phiên không cần thiết |
| Max-Age / Expires | Xác định thời hạn cookie | Session phía server vẫn cần hạn dùng và cơ chế thu hồi |

Không truyền session ID, access token hoặc mật khẩu trong URL query vì URL có thể xuất hiện trong lịch sử trình duyệt, log proxy, công cụ giám sát hoặc liên kết được chia sẻ. Nên dùng thời hạn token phù hợp, xoay/thu hồi khi cần và kiểm soát phân quyền **trên từng request**.

### 6.2. HSTS và chuyển hướng HTTP sang HTTPS

Một cấu hình web thường chuyển từ http:// sang https://. Tuy nhiên, request HTTP đầu tiên vẫn có thể bị bên trung gian tác động. **HTTP Strict Transport Security (HSTS)** hướng dẫn trình duyệt ưu tiên HTTPS trong các lần truy cập tiếp theo sau khi đã nhận chính sách hợp lệ qua HTTPS.

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Ví dụ này yêu cầu áp dụng chính sách trong một năm cho cả các subdomain. Chỉ bật **includeSubDomains** sau khi kiểm tra mọi subdomain liên quan đều hỗ trợ HTTPS; cân nhắc kỹ trước khi tham gia danh sách **HSTS preload**. Header HSTS gửi qua HTTP không thiết lập được chính sách HSTS đáng tin cậy; preload có thể bảo vệ ngay lần truy cập đầu ở trình duyệt hỗ trợ.

### 6.3. Một số header khác

| Header | Công dụng | Điều cần tránh hiểu nhầm |
| --- | --- | --- |
| Content-Security-Policy | Giới hạn nguồn script, style và tài nguyên được tải; hỗ trợ giảm tác động của XSS | Không thay thế kiểm tra dữ liệu và mã hóa đầu ra |
| X-Content-Type-Options: nosniff | Giảm hành vi suy đoán MIME type ở trình duyệt | Không phải hệ thống quét mã độc |
| Cache-Control: no-store | Yêu cầu cache không lưu phản hồi, hữu ích với nội dung nhạy cảm | Không xóa bản sao đã nằm trong log hoặc ứng dụng |
| Referrer-Policy | Điều chỉnh mức thông tin Referer truyền sang nơi khác | Không thay thế bảo vệ dữ liệu trong URL |
| Access-Control-Allow-Origin | Khai báo origin được phép đọc phản hồi theo cơ chế CORS của trình duyệt | **CORS không phải** cơ chế xác thực hoặc phân quyền API |

Ví dụ về phản hồi mang dữ liệu cá nhân:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
X-Content-Type-Options: nosniff

{"userId":42,"displayName":"Example User"}
~~~

Đối với API được gọi từ trình duyệt, cần kết hợp CORS theo danh sách origin được phép, kiểm soát CSRF khi dùng xác thực dựa trên cookie và xác thực/phân quyền độc lập ở backend.

## 7. Phân tích đe dọa: HTTPS giải quyết được gì?

| Tình huống | Rủi ro | Biện pháp và phạm vi |
| --- | --- | --- |
| Người lạ bắt gói trên Wi-Fi | Đọc mật khẩu, session hoặc nội dung nếu dùng HTTP thuần | HTTPS/TLS hợp lệ che nội dung và phát hiện sửa đổi trên đường truyền |
| Kẻ tấn công giả mạo server hoặc chèn phản hồi | Đánh cắp thông tin, thay nội dung trang | Kiểm tra chứng chỉ, hostname và HSTS; không bỏ qua cảnh báo TLS |
| Hạ cấp kết nối về HTTP | Lộ request trước khi được chuyển sang HTTPS | HSTS, preload khi phù hợp, luôn dùng URL HTTPS cho đường dẫn nhạy cảm |
| Cookie phiên bị lạm dụng | Chiếm phiên khi cookie lộ hoặc bị đánh cắp | Secure, HttpOnly, SameSite, thời hạn, chống CSRF và thu hồi session |
| XSS, SQL injection, truy cập sai quyền | Mất dữ liệu ngay trên ứng dụng dù TLS đúng | Mã hóa đầu ra, truy vấn có tham số, kiểm tra quyền phía server, CSP |
| TLS kết thúc ở load balancer, backend truyền HTTP qua mạng khác | Dữ liệu lộ trên chặng proxy–backend | Bảo vệ mạng nội bộ, phân đoạn, kiểm soát proxy và dùng TLS/mTLS giữa các chặng khi cần |
| Firewall chỉ kiểm tra TCP/443 | Không nhìn thấy HTTP/3 qua UDP/443 | Chính sách và giám sát bổ sung cho QUIC/UDP; kiểm soát theo mục tiêu bảo mật |
| Log chứa URL, cookie, Authorization | Rò rỉ bí mật từ hệ thống giám sát | Ẩn/redact dữ liệu nhạy cảm; giới hạn truy cập và thời gian giữ log |

Một điểm dễ nhầm: HTTPS mã hóa **nội dung** trao đổi, nhưng không bảo đảm ẩn mọi metadata lưu lượng. Địa chỉ IP, kích thước gói, thời gian kết nối và đôi khi tên miền qua DNS/SNI vẫn có thể bị quan sát. Các cơ chế như DoH/DoT hoặc Encrypted ClientHello (ECH) có thể giảm một phần thông tin lộ ra trong điều kiện triển khai hỗ trợ, nhưng không tạo ra tính ẩn danh hoàn toàn.

## 8. Vai trò của HTTP/HTTPS trong kiến trúc phòng vệ mạng

Một hệ thống thực tế có thể gồm người dùng, firewall, WAF, reverse proxy và nhiều backend:

~~~mermaid
flowchart LR
    C[Trình duyệt hoặc ứng dụng] -->|HTTPS| F[Firewall / WAF]
    F -->|HTTPS| P[Reverse proxy / Load balancer]
    P -->|HTTP hoặc HTTPS nội bộ| A[Application API]
    A --> D[(Cơ sở dữ liệu)]
~~~

Ở sơ đồ này, firewall tầng mạng có thể lọc theo địa chỉ IP/cổng mà không cần giải mã HTTP. WAF chỉ có thể phân tích nội dung HTTP khi được đặt tại điểm kết thúc TLS hoặc có khả năng giải mã hợp lệ. Nếu WAF kết thúc TLS rồi mã hóa lại tới reverse proxy, kết nối WAF–proxy là một chặng TLS riêng cần được cấu hình và kiểm tra.

Ở kiến trúc này, cần trả lời rõ:

1. **TLS kết thúc ở đâu?** Nếu tại reverse proxy, đoạn sau proxy phải có chính sách bảo vệ tương xứng với phân đoạn mạng và độ nhạy dữ liệu.
2. **Ai xác thực và phân quyền?** Firewall/WAF giúp lọc lưu lượng, nhưng ứng dụng vẫn chịu trách nhiệm quyết định từng người dùng được truy cập tài nguyên nào.
3. **Header nào đáng tin?** Các header chuyển tiếp như X-Forwarded-For và X-Forwarded-Proto chỉ được tin khi do proxy đáng tin kiểm soát; không tin giá trị do client tự gửi trực tiếp.
4. **Giám sát ở đâu?** Khi mã hóa đầu cuối, thiết bị mạng trung gian thường chỉ thấy metadata. Muốn đọc log HTTP phải dựa vào điểm kết thúc TLS hoặc telemetry của ứng dụng đã được cho phép.
5. **Ranh giới tin cậy nằm ở đâu?** Nên phân đoạn hệ thống công khai, API nội bộ, quản trị và dữ liệu; áp dụng nguyên tắc ít quyền, rate limiting và cơ chế phát hiện truy cập bất thường.

HTTPS là lớp bảo vệ truyền thông rất quan trọng, nhưng phải phối hợp với firewall, IDS/IPS, WAF, quản lý danh tính, bảo vệ DNS và thiết kế mạng an toàn để hình thành phòng vệ nhiều lớp.

## 9. Thực hành đọc và kiểm tra kết nối

Các lệnh sau dùng website công khai **example.org** để minh họa. Kết quả phụ thuộc server, môi trường mạng và phiên bản công cụ; không cần đoán trước chính xác status hay phiên bản được thương lượng.

### Bài thực hành A: Quan sát header và chuyển hướng

~~~bash
curl -I http://example.org
curl -I https://example.org
curl -IL http://example.org
~~~

Quan sát:

- Dòng trạng thái phản hồi thuộc nhóm 2xx, 3xx hay 4xx?
- Nếu có chuyển hướng, header **Location** trỏ tới URL dùng scheme nào?
- Có xuất hiện **Strict-Transport-Security**, **Cache-Control** hoặc các header an ninh khác không?
- **-I** gửi yêu cầu HEAD; **-L** theo các bước chuyển hướng. Không phải máy chủ nào cũng cấu hình chuyển hướng hoặc HSTS giống nhau.

### Bài thực hành B: Kiểm tra TLS và phiên bản HTTP

~~~bash
curl -vI https://example.org
curl --http1.1 -I https://example.org
curl --http2 -I https://example.org
~~~

Đọc output verbose để xác định việc xác minh chứng chỉ, phiên bản TLS và giao thức HTTP được dùng nếu công cụ có hiển thị. Tùy bản build, curl có thể không hỗ trợ HTTP/2 hoặc HTTP/3; lỗi thiếu hỗ trợ giao thức ở client không chứng minh server gặp lỗi. Tránh chia sẻ log verbose có chứa cookie, token hay thông tin nội bộ.

### Bài thực hành C: Đọc lưu lượng trong Wireshark

Với lưu lượng do chính bạn tạo ra hoặc được phép phân tích, thử các display filter:

~~~text
http
tls
tcp.port == 443
udp.port == 443
quic
~~~

So sánh ba trường hợp:

1. HTTP/1.1 không mã hóa: có thể thấy request line và nhiều header khi lưu lượng không được bảo vệ ở tầng khác.
2. HTTPS qua TCP: thấy kết nối TCP và một số thông tin bắt tay TLS, nhưng không đọc trực tiếp URL path, cookie và body bên trong TLS.
3. HTTP/3: thấy UDP/QUIC; chỉ lọc TCP/443 sẽ bỏ qua một phần lưu lượng HTTPS hiện đại.

Trong Developer Tools của trình duyệt, người dùng tại đầu cuối vẫn xem được method, status, header và nội dung response đã giải mã do chính trình duyệt nhận. Điều này không mâu thuẫn với việc người nghe lén trung gian không đọc được dữ liệu TLS.

## 10. Một số tình huống xử lý sự cố

**Tình huống 1 — Trình duyệt báo chứng chỉ không khớp tên miền.** Kiểm tra hostname người dùng truy cập với SAN trên chứng chỉ, cấu hình virtual host và reverse proxy. Không hướng dẫn người dùng bấm bỏ qua cảnh báo để tiếp tục đăng nhập.

**Tình huống 2 — Trang HTTPS tải không đầy đủ.** Kiểm tra lỗi *mixed content*: trang dùng HTTPS nhưng tải script, ảnh hoặc tài nguyên qua HTTP. Nâng đường dẫn tài nguyên sang HTTPS và kiểm tra CSP; trình duyệt có thể chặn một số dạng nội dung trộn.

**Tình huống 3 — Lỗi 502 hoặc 504 sau reverse proxy.** Xác minh upstream, DNS nội bộ, cổng, thời gian phản hồi, firewall và TLS giữa các chặng. Đây thường là lỗi giao tiếp với backend, không đủ chứng cứ để kết luận chứng chỉ phía client sai.

**Tình huống 4 — HTTP/2 hoạt động nhưng HTTP/3 không dùng được.** Kiểm tra hỗ trợ QUIC của client và server, chính sách UDP/443, firewall và thông tin quảng bá giao thức. Client có thể tự chuyển về HTTP/2/HTTP/1.1.

**Tình huống 5 — API dùng HTTPS nhưng người dùng xem được dữ liệu của người khác.** Kiểm tra authorization ở mọi API và đối tượng dữ liệu. Đây là lỗi phân quyền tầng ứng dụng; TLS chỉ bảo vệ đường truyền đến API.

## 11. Kiểm tra kiến thức và vận dụng

**Câu hỏi 1.** HTTPS có nghĩa mọi dữ liệu giữa trình duyệt và cơ sở dữ liệu đều được mã hóa không?

*Gợi ý:* Không nhất thiết. HTTPS bảo vệ các chặng có TLS. Phải xem nơi kết thúc TLS và cách ứng dụng kết nối tới backend/database.

**Câu hỏi 2.** Vì sao GET thường được coi là idempotent, nhưng POST không được bảo đảm idempotent?

*Gợi ý:* Đọc cùng tài nguyên lặp lại không tạo thêm tác động dự định; POST có thể tạo thêm đơn hàng hoặc giao dịch mỗi lần gửi. Một API có thể bổ sung idempotency key cho POST, nhưng đó là cơ chế của ứng dụng.

**Câu hỏi 3.** Khi bắt được gói UDP/443, có thể kết luận đó là HTTP/3 không?

*Gợi ý:* Không. Cổng chỉ là dấu hiệu; cần nhận diện giao thức QUIC và, nếu có thông tin thích hợp, ngữ cảnh thương lượng ứng dụng.

**Câu hỏi 4.** Vì sao bật Secure và HttpOnly cho cookie vẫn chưa đủ chống chiếm quyền phiên?

*Gợi ý:* Còn rủi ro CSRF, XSS thực thi thao tác thay người dùng, session bị lộ từ server, token không hết hạn hoặc lỗi phân quyền; cần các biện pháp phối hợp.

**Bài tập thiết kế.** Một doanh nghiệp có website công khai, API xử lý đơn hàng và dịch vụ dữ liệu nội bộ. Hãy vẽ các chặng từ trình duyệt qua reverse proxy đến API; đánh dấu nơi TLS kết thúc, nơi áp dụng xác thực/phân quyền, vị trí firewall/WAF và nơi thu thập log. Đề xuất cách phát hiện lỗi chứng chỉ, chuyển hướng sai, truy cập bất thường và API phản hồi 5xx, đồng thời bảo vệ bí mật không lọt vào log.

## 12. Những điểm cần ghi nhớ

- **HTTP** xác định ngữ nghĩa request–response ở tầng ứng dụng; **HTTPS** sử dụng TLS để bảo vệ các bản tin HTTP khi truyền.
- **HTTP/1.1 và HTTP/2** thường dựa trên TCP; **HTTP/3** chạy trên QUIC qua UDP và sử dụng TLS 1.3.
- HTTPS bảo vệ tính bí mật, toàn vẹn và xác thực máy chủ khi chứng chỉ được kiểm tra đúng; nó không thay thế phân quyền, chống XSS/CSRF, quản lý session hoặc bảo vệ backend.
- HSTS, cookie Secure/HttpOnly/SameSite, CSP và cấu hình TLS an toàn là các lớp phòng vệ bổ trợ, mỗi lớp giải quyết một nhóm rủi ro riêng.
- Khi điều tra lưu lượng, hãy xác định **phiên bản HTTP, chặng kết thúc TLS, cổng/giao thức vận chuyển, ranh giới tin cậy và log ứng dụng** trước khi kết luận nguyên nhân sự cố.
