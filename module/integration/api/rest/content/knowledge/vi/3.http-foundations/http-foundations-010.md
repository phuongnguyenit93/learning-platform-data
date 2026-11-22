# Phân biệt lỗi DNS, TLS, kết nối và phản hồi lỗi HTTP

“Gọi API thất bại” chưa phải mô tả đủ để sửa lỗi. Không phân giải được hostname, không mở được kết nối, không xác minh được chứng thư và nhận được `403 Forbidden` là những tình huống khác nhau. Chúng cần bằng chứng, cách xử lý và chính sách retry khác nhau.

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này xây dựng cách phân loại lỗi theo giai đoạn và theo chặng giao tiếp. Bạn sẽ liên hệ các lỗi với hợp đồng REST, gateway, xác thực, idempotency, kiểm thử và cách bắt lỗi trong Java/Spring hoặc công nghệ tương đương.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt lỗi DNS, lỗi thiết lập hoặc duy trì kết nối, lỗi TLS và response HTTP báo lỗi.
- Giải thích vì sao timeout phía client không tự trở thành HTTP `504`.
- Nhận biết sự khác nhau giữa điều client quan sát và nguyên nhân ở phía gateway/upstream.
- Đọc exception, exit code và mã trạng thái mà không trộn chúng thành một loại.
- Chọn bước chẩn đoán, thông tin log và cách retry phù hợp với khả năng request đã được thực hiện.

## 2. Một lần gọi HTTPS diễn ra qua những giai đoạn nào?

### 2.1. Mô hình đơn giản cho kết nối mới dùng TCP

Với HTTPS qua HTTP/1.1 hoặc HTTP/2 trên một kết nối TCP mới, có thể hình dung:

~~~mermaid
flowchart LR
    A[Đọc URI và cấu hình] --> B[Phân giải hostname]
    B --> C[Thiết lập TCP]
    C --> D[Thương lượng TLS]
    D --> E[Gửi HTTP request]
    E --> F[Nhận response header]
    F --> G[Đọc content]
    G --> H[Giải mã và xử lý dữ liệu]
~~~

Ví dụ URI:

~~~text
https://api.example.test:443/orders/ord-1042
        └─ hostname ──┘       └─ đường dẫn ─┘
~~~

Hostname, cổng, giao thức và đường dẫn đóng vai trò khác nhau. DNS không tìm đơn hàng theo đường dẫn; TLS không quyết định người dùng có quyền hủy đơn; HTTP `404` không đồng nghĩa DNS không tìm thấy hostname.

Mô hình trên phục vụ định vị lỗi, không phải mọi request đều thực hiện lại toàn bộ các bước:

- DNS có thể dùng cache hoặc cơ chế phân giải khác.
- Client có thể tái sử dụng kết nối đã mở.
- Proxy có thể thay đổi nơi thực hiện DNS hoặc tạo thêm bước thiết lập tunnel.
- HTTP/3 dùng QUIC; không áp nguyên chuỗi “TCP rồi TLS” cho mọi phiên bản HTTP.
- Chuyển hướng có thể dẫn tới hostname khác và một chuỗi trao đổi mới.

### 2.2. Bằng chứng ở giai đoạn sau không chứng minh toàn bộ hệ thống hoạt động

Đọc được response HTTP thực từ một peer HTTPS cho thấy chặng với peer đó đã hoạt động đủ để trao đổi HTTP. Điều đó không chứng minh dịch vụ nghiệp vụ phía sau gateway khỏe mạnh, cũng không chứng minh request vừa thực hiện một truy vấn DNS mới.

Ngược lại, không nhận được response hoàn chỉnh không đủ để kết luận request chưa tới server. Lỗi có thể xảy ra sau khi server đã xử lý nhưng trước khi client đọc được kết quả.

## 3. Lỗi DNS: chưa tìm được địa chỉ cần dùng

### 3.1. DNS trả lời câu hỏi nào?

DNS tham gia chuyển tên như `api.example.test` thành thông tin địa chỉ cần cho việc kết nối. Trong một môi trường thực tế, quá trình phân giải còn chịu ảnh hưởng của resolver, cache, cấu hình mạng, VPN, file hosts và service discovery.

Những tình huống cần phân biệt:

| Hiện tượng | Ý nghĩa định hướng | Chưa thể kết luận |
|---|---|---|
| Tên không tồn tại theo kết quả phân giải | Có thể sai hostname hoặc thiếu bản ghi trong vùng đang hỏi | Toàn bộ dịch vụ đã bị xóa |
| Resolver trả lỗi xử lý | Hệ thống phân giải gặp vấn đề hoặc không hoàn tất được truy vấn | API đang trả HTTP 500 |
| Không nhận trả lời trước timeout | Có thể lỗi đường tới resolver, resolver chậm hoặc cấu hình sai | Hostname chắc chắn không tồn tại |
| Trả địa chỉ không mong đợi | Có thể cache cũ, split DNS, cấu hình hoặc đích đã đổi | Lỗi luôn xuất hiện dưới dạng DNS exception |

Một bản ghi DNS sai nhưng vẫn trả được địa chỉ có thể dẫn tới lỗi kết nối, chứng thư không khớp hoặc HTTP `404` ở một dịch vụ khác. Vì vậy, chỉ nhìn tên exception không đủ để xác nhận cấu hình DNS đúng.

### 3.2. Biểu hiện ở client

Ví dụ thông báo có thể gặp:

~~~text
Could not resolve host
UnknownHostException
UnresolvedAddressException trong chuỗi nguyên nhân
~~~

Tên exception và cách bọc nguyên nhân phụ thuộc thư viện, JDK và đường gọi. Một exception ngoài cùng mang tên kết nối vẫn có thể chứa nguyên nhân địa chỉ chưa phân giải ở bên trong.

Nếu chính client không phân giải được đích cần kết nối và chưa có trao đổi HTTP tương ứng, nó không nhận được một HTTP status do đích đó trả. Không tự ghi “DNS trả 404”; lỗi tên miền và response `404 Not Found` thuộc hai lớp khác nhau.

### 3.3. Chẩn đoán đúng môi trường

Hãy so sánh:

- Hostname thực trong URI sau khi áp cấu hình.
- Kết quả phân giải từ chính máy, container hoặc pod đang lỗi.
- Resolver đang dùng, VPN và mạng mà tiến trình truy cập.
- Tập địa chỉ IPv4/IPv6 và địa chỉ client đã thử.
- Cache của hệ điều hành, runtime và thành phần discovery nếu có.

Kết quả phân giải thành công trên laptop chưa chứng minh một container hoặc gateway có cùng kết quả. Không sửa URL thành một IP tùy ý rồi kết luận DNS đã được xử lý, vì việc đó còn có thể thay đổi TLS và định tuyến.

## 4. Lỗi kết nối: không thiết lập được hoặc không giữ được đường trao đổi

### 4.1. Connection refused và connect timeout

**Connection refused** thường cho thấy một thành phần trên đường kết nối chủ động từ chối. Ví dụ, không có tiến trình lắng nghe tại cổng được gọi hoặc chính sách mạng trả từ chối.

**Connect timeout** cho thấy việc thiết lập kết nối không hoàn tất trong ngân sách thời gian của client. Có thể liên quan firewall bỏ gói, định tuyến, địa chỉ không tới được, tải hệ thống hoặc vấn đề mạng khác.

Hai thông báo này không chỉ ra duy nhất một nguyên nhân. “Timeout chắc chắn do server xử lý chậm” là kết luận vượt quá bằng chứng nếu TCP còn chưa được thiết lập.

### 4.2. Reset, EOF và mất kết nối giữa chừng

Kết nối có thể bị ngắt sau khi đã thiết lập:

~~~text
Connection reset
Unexpected EOF
Connection closed before response completed
~~~

Cần hỏi lỗi xuất hiện:

1. Trước khi gửi request?
2. Trong lúc gửi header/body?
3. Sau khi gửi xong nhưng chưa nhận response header?
4. Sau khi nhận status nhưng đang đọc content?

Một reset sau khi gửi request có thể để lại **kết quả nghiệp vụ chưa biết**. Server có thể chưa thực hiện, đang thực hiện hoặc đã hoàn tất. Exception kết nối không tự mang câu trả lời về giao dịch.

### 4.3. Không phải mọi thời gian chờ đều là connect timeout

Client có thể chờ lấy connection từ pool, chờ phản hồi, chờ byte tiếp theo hoặc chờ hoàn tất một deadline ứng dụng. Những timeout này có ý nghĩa khác nhau.

Nếu pool đã cạn nhưng mạng bình thường, tăng connect timeout không giải quyết nguyên nhân. Nếu response body bị ngắt, đổi DNS cũng chưa có cơ sở. Đặt tên metric và log theo giai đoạn thực sự quan sát được.

## 5. Lỗi TLS: không thiết lập hoặc duy trì được kênh bảo mật phù hợp

### 5.1. Những nguyên nhân thường gặp

| Nhóm vấn đề | Ví dụ |
|---|---|
| Tin cậy chứng thư | Client không xây dựng được chuỗi tới CA mà truststore tin cậy |
| Thời hạn | Chứng thư hết hạn hoặc chưa có hiệu lực theo thời gian kiểm tra |
| Danh tính đích | Hostname trong URI không khớp danh tính được chứng thư xác nhận |
| Thương lượng | Các bên không tìm được cấu hình TLS/giao thức ứng dụng phù hợp |
| Xác thực hai chiều | Server yêu cầu chứng thư client nhưng client thiếu hoặc không đáp ứng chính sách |
| Thiết bị trung gian | Proxy hoặc thiết bị kiểm tra TLS đưa vào một chuỗi chứng thư khác |

Biểu hiện có thể là `SSLHandshakeException`, thông báo kiểm tra đường dẫn chứng thư, hostname mismatch hoặc TLS alert. TLS có hệ thống alert riêng; các giá trị như `handshake_failure`, `certificate_expired`, `unknown_ca` không phải HTTP status. [RFC 8446 về TLS alert](https://www.rfc-editor.org/rfc/rfc8446.html#section-6).

### 5.2. Kết nối TCP thành công chưa chứng minh TLS thành công

Một cổng 443 có thể chấp nhận TCP nhưng gửi chứng thư sai, yêu cầu mTLS chưa được cấu hình hoặc thậm chí không phục vụ TLS như client mong đợi.

Tương tự, bắt tay TLS thành công chỉ xác nhận các điều kiện TLS tương ứng. Nó không cấp quyền đọc mọi tài nguyên. Một request sau đó vẫn có thể nhận `401` hoặc `403` ở tầng HTTP.

### 5.3. Sửa theo danh tính và nguồn tin cậy

Các điểm kiểm tra gồm hostname, SNI theo cách client gửi, chuỗi chứng thư server cung cấp, truststore thực được tiến trình dùng, thời gian hệ thống và cấu hình mTLS.

Giữ cơ chế xác minh chứng thư trong luồng tích hợp. Tắt kiểm tra xác minh làm mất một phần bảo đảm danh tính và có thể che khuất nguyên nhân cấu hình. Đổi URI từ hostname sang IP cũng có thể tạo lỗi hostname mới, ngay cả khi IP đúng.

Nếu bắt tay TLS của chính chặng đó thất bại trước khi trao đổi HTTP, không có response JSON chuẩn nào từ ứng dụng ở phía bên kia chặng đó để client đọc. Một gateway đã hoàn tất TLS với client vẫn có thể tạo response HTTP riêng cho lỗi TLS ở chặng upstream; đây là trường hợp khác.

## 6. Phản hồi lỗi HTTP: đã có thông điệp HTTP để diễn giải

### 6.1. Một response 503 là thông tin khác với exception timeout

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 30

{
  "code": "SERVICE_TEMPORARILY_UNAVAILABLE",
  "message": "Dịch vụ tạm thời chưa xử lý được yêu cầu.",
  "requestId": "rq-29"
}
~~~

Ở đây có status `503`, header và body theo hợp đồng JSON minh họa. Client cần xử lý response thay vì báo chung “không kết nối được”.

`Retry-After: 30` gợi ý khoảng chờ tính bằng giây trong ví dụ. Việc retry còn phụ thuộc thao tác, khả năng chống lặp và deadline của bên gọi; không tự động gửi lại mọi request chỉ vì có header này.

### 6.2. Một số mã cần phân biệt

| Status | Ý nghĩa cần nhận diện | Hướng xử lý ban đầu |
|---|---|---|
| `400` | Request có vấn đề theo ngữ nghĩa kiểm tra của server | Kiểm tra cấu trúc và hợp đồng |
| `401` | Cần thông tin xác thực hợp lệ cho tài nguyên | Kiểm tra cơ chế xác thực và challenge |
| `403` | Server từ chối thực hiện | Kiểm tra quyền và chính sách |
| `404` | Không tìm thấy hoặc không công bố tài nguyên theo ngữ nghĩa response | Kiểm tra URI, định tuyến và quyền liên quan |
| `409` | Xung đột với trạng thái hiện tại | Đọc dữ liệu lỗi và trạng thái mới |
| `500` | Điều kiện không mong đợi ngăn server hoàn tất request | Đối chiếu log và mã liên kết |
| `502` | Gateway/proxy gặp phản hồi upstream không hợp lệ | Kiểm tra chặng gateway–upstream |
| `503` | Server tạm chưa phục vụ được, chẳng hạn quá tải hoặc bảo trì | Xem chính sách phục hồi và retry |
| `504` | Gateway/proxy không nhận phản hồi upstream kịp thời | Kiểm tra thời gian chờ và xử lý upstream |

Các mã 5xx có ngữ nghĩa cụ thể; đặc biệt, `504` là response do thành phần đóng vai gateway/proxy tạo khi chờ upstream, không phải tên chung cho mọi timeout. [RFC 9110, mục 15.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6).

### 6.3. Exception của framework vẫn có thể chứa response HTTP

Một số thư viện Java/Spring biểu diễn response 4xx/5xx bằng exception. Nếu exception giữ status, header và body thì vẫn có phản hồi HTTP, dù API lập trình sử dụng nhánh `catch`.

Ngược lại, exception I/O có thể không có status nào. Không lấy sự tồn tại của exception làm tiêu chí duy nhất để phân biệt HTTP error và lỗi truyền thông.

Body lỗi cũng không chắc là JSON. Gateway có thể trả HTML hoặc text. Kiểm tra `Content-Type`, giới hạn dữ liệu đọc và hợp đồng trước khi đưa body vào JSON parser.

### 6.4. Có status chưa chắc đã đọc xong response

Có thể nhận `200 OK` rồi kết nối bị ngắt giữa body, hoặc đã nhận `503` nhưng không đọc được hết nội dung lỗi. Ghi lại riêng:

- Có nhận được status không?
- Body đã hoàn tất chưa?
- Dữ liệu đã giải mã và kiểm tra hợp đồng chưa?

Một trường `success=true` chỉ dựa vào việc thấy 200 có thể che mất response bị cắt.

## 7. Nhìn theo từng chặng: client thấy HTTP, upstream lại lỗi mạng

### 7.1. Hai cuộc trao đổi khác nhau

~~~mermaid
flowchart LR
    C[Client] -->|HTTPS thành công| G[Gateway]
    G -->|DNS, kết nối hoặc TLS gặp lỗi| U[Dịch vụ upstream]
    G -->|Response HTTP do gateway tạo| C
~~~

Client có thể nhận `502` hoặc một response khác theo chính sách gateway, trong khi gateway ghi nhận không phân giải được tên upstream.

Cần phân biệt:

| Góc nhìn | Điều được quan sát |
|---|---|
| Client | Đã nhận HTTP response từ gateway |
| Gateway khi gọi upstream | Có thể gặp lỗi DNS/TLS/kết nối và chưa nhận response từ upstream |
| Dịch vụ nghiệp vụ | Có thể chưa nhận request, hoặc nhận ở một lần thử khác |

Không có quy tắc phổ quát “mọi lỗi DNS upstream luôn phải ánh xạ thành 502”. Cách ánh xạ phụ thuộc vai trò, sản phẩm gateway và hợp đồng vận hành. Giữ nguyên nhân chi tiết trong telemetry nội bộ và đọc status theo chặng mà nó được trả.

### 7.2. Header Server không đủ xác định nguồn

Header hoặc trang lỗi có thể gợi ý response được tạo bởi proxy, WAF hoặc ứng dụng, nhưng không phải bằng chứng tuyệt đối. Cần kết hợp access log, trace và mã request tại các điểm quan sát.

Nếu gateway trả lỗi trước khi gọi ứng dụng, việc không thấy log controller là có thể hiểu được. Nếu logging lấy mẫu hoặc lỗi ghi log, thiếu log cũng chưa chứng minh request chưa tới. Kết luận cần dựa trên nhiều dấu hiệu phù hợp.

### 7.3. Không làm mất phân loại khi trả lỗi ra ngoài

Một backend gọi hệ thống khác có thể chọn trả response HTTP cho client của nó. Nó nên giữ riêng trong log:

~~~text
outbound_failure_category=TLS
outbound_http_status=null
inbound_http_status=502
response_source=this_service
~~~

Ví dụ này mô tả chính sách của một dịch vụ, không khẳng định mọi dịch vụ phải dùng 502 cho tình huống đó. `outbound_http_status=null` ngăn hiểu lầm rằng upstream đã trả một status mà nó chưa từng gửi.

## 8. Timeout không phải một nguyên nhân duy nhất

### 8.1. Đọc tên timer trước khi xử lý

| Timer | Điều có thể đang chờ |
|---|---|
| DNS timeout | Kết quả phân giải |
| Pool acquisition timeout | Quyền sử dụng một connection hoặc tài nguyên client |
| Connect timeout | Thiết lập kết nối theo định nghĩa của thư viện |
| TLS handshake timeout | Hoàn tất thương lượng bảo mật nếu stack có timer riêng |
| Response/read timeout | Header, byte hoặc hoạt động đọc theo định nghĩa client |
| Deadline của nghiệp vụ | Toàn bộ thời gian được phép cho thao tác ở một ranh giới |

Tên và phạm vi timer không đồng nhất giữa các thư viện. Một số thành phần gộp nhiều giai đoạn vào cùng ngân sách. Không suy ra phạm vi chỉ từ một tên cấu hình gần giống.

### 8.2. Cùng một hệ thống có thể tạo hai quan sát khác nhau

Giả sử gateway chờ upstream tối đa 5 giây:

- Nếu client chờ đủ lâu, nó có thể nhận response `504` do gateway tạo.
- Nếu client hết deadline sau 2 giây, nó có thể nhận exception timeout của chính client trước khi gateway trả response.

Trường hợp thứ hai không được ghi thành “đã nhận HTTP 504” nếu client chưa đọc status đó. Có thể gateway tạo 504 sau khi client đã bỏ cuộc, nhưng đó là quan sát ở gateway.

### 8.3. Timeout sau khi gửi có thể để lại kết quả chưa biết

Với `POST /orders`, tình huống có thể là:

~~~text
Client gửi request
Server tạo đơn và commit dữ liệu
Đường trả response gặp lỗi hoặc client hết thời gian chờ
Client không biết mã đơn vừa tạo
~~~

Tự động gửi lại POST có thể tạo hai đơn. API cần hợp đồng idempotency, mã thao tác để truy vấn kết quả hoặc quy trình đối soát phù hợp. Timeout không hoàn tác giao dịch đã commit.

Đừng dùng câu “client không nhận response” để chứng minh “server chưa thực hiện”. Phân loại giai đoạn lỗi giúp quyết định, nhưng không thay thế bảo đảm nghiệp vụ đầu cuối.

## 9. Bộ công cụ chẩn đoán theo lớp

Các lệnh dưới đây là ví dụ học tập trên Windows. `api.example.test` là hostname minh họa; khi áp dụng, thay bằng đích và môi trường đã được phép kiểm tra.

### 9.1. Kiểm tra phân giải

~~~powershell
Resolve-DnsName -Name api.example.test
~~~

Lệnh giúp kiểm tra kết quả phân giải tại môi trường chạy nó. Nó không kiểm tra endpoint, chứng thư hoặc quyền HTTP. [Tài liệu Resolve-DnsName của Microsoft](https://learn.microsoft.com/en-us/powershell/module/dnsclient/resolve-dnsname).

Nếu ứng dụng dùng proxy hoặc resolver riêng, kết quả của công cụ hệ điều hành có thể chưa phản ánh đầy đủ đường ứng dụng đi.

### 9.2. Kiểm tra khả năng thiết lập TCP

~~~powershell
Test-NetConnection -ComputerName api.example.test -Port 443
~~~

Kết quả TCP thành công chỉ có giá trị với phép kiểm tra TCP đó. Nó không xác nhận TLS, HTTP, mTLS hay luồng QUIC của HTTP/3. Nếu có nhiều địa chỉ, xem địa chỉ thực được kiểm tra.

### 9.3. Quan sát curl và các mốc thời gian

~~~powershell
$curlArgs = @(
    '--verbose',
    '--connect-timeout', '3',
    '--max-time', '8',
    '--output', 'NUL',
    '--write-out',
    'http=%{http_code} remote=%{remote_ip} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} first=%{time_starttransfer} total=%{time_total}\n',
    'https://api.example.test/health'
)
& curl.exe @curlArgs
$curlExitCode = $LASTEXITCODE
"curl_exit=$curlExitCode"
~~~

Dùng `curl.exe` để gọi chương trình curl trên Windows. Ví dụ bỏ body vào thiết bị NUL và không đính kèm thông tin xác thực. Khi dùng verbose với request thật, kiểm soát việc lưu và chia sẻ credential/header nhạy cảm.

Các mốc timing là thời gian tích lũy từ đầu phép chuyển giao tới mốc tương ứng, không phải những khoảng độc lập để cộng lại. Reuse kết nối, proxy hoặc chuyển hướng có thể làm cách diễn giải phức tạp hơn. `time_starttransfer` không chỉ là thời gian xử lý nghiệp vụ của server. [curl manual về write-out và timing](https://curl.se/docs/manpage.html#-w).

### 9.4. Phân biệt exit code và HTTP status

| Kết quả curl | Định hướng |
|---|---|
| Exit code `6` | Không phân giải được host |
| Exit code `7` | Không kết nối được tới đích cần gọi |
| Exit code `28` | Đạt điều kiện timeout của phép chuyển giao |
| Exit code `35` | Có vấn đề trong TLS handshake |
| Exit code `60` | Xác minh chứng thư peer thất bại |
| HTTP `503` | Một response HTTP đã được quan sát; xem thêm tình trạng hoàn tất chuyển giao |

Đây là mã công cụ, không phải mã trạng thái HTTP. Đặc biệt, exit code 28 không tự xác định timeout thuộc DNS, kết nối hay chờ response. [Danh mục lỗi chính thức của libcurl](https://curl.se/libcurl/c/libcurl-errors.html).

`http_code=000` không phải status hợp lệ do server gửi; đó là giá trị hiển thị khi công cụ không có response code tương ứng để báo. Nó không chỉ ra riêng một loại lỗi.

Mặc định, curl có thể kết thúc thành công về chuyển giao dù nhận HTTP 4xx/5xx. Tùy chọn như `--fail` thay đổi cách trả exit code; vì vậy phải xem cả tùy chọn, exit code và HTTP status. [curl manual về --fail](https://curl.se/docs/manpage.html#-f).

### 9.5. Thử một địa chỉ đã biết mà giữ hostname TLS

Trong phép kiểm tra có kiểm soát, có thể dùng:

~~~powershell
curl.exe --verbose --connect-timeout 3 --max-time 8 --resolve api.example.test:443:203.0.113.10 https://api.example.test/health
~~~

Địa chỉ trên chỉ để minh họa. `--resolve` cung cấp địa chỉ cho cặp host/cổng, trong khi hostname của URL vẫn được dùng cho các xử lý tương ứng như danh tính đích. Cách này giúp tách một giả thuyết phân giải khỏi các lớp tiếp theo; nó không sửa DNS của ứng dụng. Nếu có proxy, phải kiểm tra bên nào thực hiện phân giải đích. [curl manual về --resolve](https://curl.se/docs/manpage.html#--resolve).

Không chỉ đổi URL thành IP rồi xem việc chứng thư không khớp là bằng chứng API hỏng.

## 10. Phân biệt trong Java với JDK HttpClient

### 10.1. Response lỗi vẫn là HttpResponse

JDK `HttpClient` trả status qua `HttpResponse`; response 4xx/5xx không tự trở thành exception I/O chỉ vì mã trạng thái. Lỗi gửi/nhận và việc body được xử lý ra sao còn phụ thuộc lời gọi cùng `BodyHandler`. [Tài liệu JDK HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html).

Ví dụ Java sau chỉ minh họa nhánh quan sát. Nó bỏ body để tập trung vào status và exception, không phải một client nghiệp vụ hoàn chỉnh:

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.channels.UnresolvedAddressException;
import java.time.Duration;
import javax.net.ssl.SSLException;

public class HttpFailureDemo {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.example.test/health"))
            .timeout(Duration.ofSeconds(8))
            .GET()
            .build();

        try {
            HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding()
            );
            System.out.printf(
                "outcome=HTTP_RESPONSE http_status=%d%n",
                response.statusCode()
            );
        } catch (HttpConnectTimeoutException e) {
            report("CONNECT_TIMEOUT", e);
        } catch (HttpTimeoutException e) {
            report("REQUEST_TIMEOUT", e);
        } catch (IOException e) {
            report(classify(e), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("outcome=INTERRUPTED");
        }
    }

    private static String classify(Throwable error) {
        if (hasCause(error, UnknownHostException.class)
                || hasCause(error, UnresolvedAddressException.class)) {
            return "DNS_OR_ADDRESS";
        }
        if (hasCause(error, SSLException.class)) {
            return "TLS_IO";
        }
        if (hasCause(error, ConnectException.class)) {
            return "CONNECTION";
        }
        return "IO_UNCLASSIFIED";
    }

    private static boolean hasCause(
            Throwable error, Class<? extends Throwable> type) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }

    private static void report(String category, Throwable error) {
        System.out.printf(
            "outcome=CLIENT_FAILURE category=%s exception=%s%n",
            category, error.getClass().getSimpleName()
        );
    }
}
~~~

`HttpConnectTimeoutException` được bắt trước `HttpTimeoutException` vì nó là kiểu chuyên biệt. Hàm `classify` dùng dấu hiệu trong chuỗi nguyên nhân, không tuyên bố đã tìm ra nguyên nhân vận hành cuối cùng.

Ví dụ dùng hostname giả và không chạy như một phép kiểm tra dịch vụ thực. Khi áp dụng vào ứng dụng, nên tái sử dụng client phù hợp vòng đời ứng dụng và xây dựng telemetry, giới hạn thời gian cùng xử lý body theo yêu cầu thực tế.

### 10.2. Hai timeout có phạm vi khác nhau

Connect timeout của JDK áp dụng khi cần tạo kết nối mới; nếu tái sử dụng kết nối thì cấu hình này không có tác dụng cho lần đó. [JDK HttpClient.Builder.connectTimeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration)).

Timeout ở `HttpRequest` là cấu hình chờ response của request theo hành vi JDK. Không suy nó là read timeout giống hệt mọi thư viện khác, hoặc tự coi nó là deadline cho mọi công việc ứng dụng sau khi nhận response. [JDK HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)).

Khi dùng body dạng streaming, cần kiểm tra riêng thời hạn và cách hủy việc đọc body. Một timeout cấu hình ở builder không thay thế thiết kế ngân sách thời gian của toàn bộ luồng nghiệp vụ.

### 10.3. Với Spring hoặc client khác

Bắt đầu từ hai câu hỏi:

1. Exception có chứa response HTTP thực với status/header không?
2. Nếu không, exception và chuỗi nguyên nhân cho biết giai đoạn nào?

Adapter nên giữ hai nhóm thông tin riêng: lỗi truyền thông của lần gọi outbound và response được dịch vụ hiện tại tạo ra cho client của nó. Không biến mọi exception thành một nhãn “upstream trả 500” nếu upstream chưa trả status nào.

## 11. Retry theo ngữ nghĩa và bằng chứng

| Tình huống | Cân nhắc xử lý |
|---|---|
| Hostname cấu hình sai | Sửa cấu hình; lặp nhanh không làm tên đúng |
| Chứng thư không hợp lệ | Sửa danh tính/chuỗi tin cậy/thời gian/cấu hình liên quan |
| Kết nối lỗi tạm thời khi đọc GET | Có thể retry có giới hạn nếu hợp đồng và tải cho phép |
| Nhận 401/403 | Xử lý xác thực/quyền; không gửi lặp nguyên request vô hạn |
| Nhận 503/504 | Đánh giá khả năng phục hồi, Retry-After nếu có, deadline và tác dụng phụ |
| POST timeout sau khi gửi | Xác định kết quả bằng cơ chế idempotency hoặc đối soát trước khi gây lặp |
| Body nhận thiếu | Không dùng như response đầy đủ; xem hợp đồng khôi phục của thao tác |

Retry nên có số lần giới hạn, khoảng chờ tăng phù hợp, phân tán thời điểm thử lại và tổng ngân sách. Nhiều tầng cùng retry có thể nhân tải: client thử ba lần, gateway thử ba lần và backend thử ba lần không chỉ tạo ba lần gọi cuối.

Không đặt chính sách chỉ từ con số 5xx hoặc tên exception. Một response lỗi có thể xảy ra sau một phần tác dụng nghiệp vụ; bảo đảm an toàn cần gắn với thao tác cụ thể.

## 12. Ghi log và metric để không mất bằng chứng

Một log lỗi truyền thông có thể có:

~~~text
operation=createOrder
outcome=CLIENT_FAILURE
stage=TLS
http_status=null
exception=SSLHandshakeException
attempt=1
elapsed_ms=183
request_id=client-rq-57
~~~

Một log response HTTP có thể là:

~~~text
operation=getOrder
outcome=HTTP_RESPONSE
http_status=503
body_complete=true
attempt=1
elapsed_ms=842
request_id=rq-29
~~~

Tên field là quy ước minh họa. Điểm chính là không điền status giả để che chỗ chưa có status, và không dùng nhãn “body hoàn tất” nếu tầng quan sát chưa biết.

Nên lưu các thông tin cần thiết như môi trường, đích logic, chặng gọi, loại lỗi, thời gian, số lần thử, phiên bản cấu hình liên quan và mã liên kết. Một request ID do client tự tạo giúp đối chiếu, nhưng không chứng minh server đã nhận.

Metric nên phân nhóm lỗi với số lượng nhãn kiểm soát được. Không dùng từng request ID, full URL có định danh hay toàn bộ exception message làm nhãn metric. Khi cần tương quan thời gian, lưu mốc chuẩn để đối chiếu và dùng đồng hồ đo khoảng thời gian phù hợp trong tiến trình.

Thông tin xác thực, khóa, cookie và body nhạy cảm không cần xuất hiện chỉ để phân loại DNS/TLS/kết nối. Chia sẻ bằng chứng đã chọn lọc theo vấn đề đang điều tra.

## 13. Những tình huống giống lỗi mạng nhưng cần tách riêng

### 13.1. Trình duyệt chặn do CORS

JavaScript có thể không đọc được response do chính sách CORS dù một trao đổi mạng đã diễn ra. Một lỗi hiển thị trong ứng dụng web không tự chứng minh DNS hoặc TLS thất bại.

Cần xem thông báo trình duyệt, preflight và request thực. Đặc biệt, việc JavaScript không đọc được kết quả không bảo đảm thao tác có tác dụng phụ chưa xảy ra.

### 13.2. HTTP thành công nhưng dữ liệu sai hợp đồng

Response `200` có thể chứa HTML của trang đăng nhập, JSON sai schema hoặc dữ liệu nghiệp vụ ngoài mong đợi. Đây là vấn đề xác thực/định tuyến/hợp đồng tùy bằng chứng, không tự là DNS error.

Tách các trạng thái “nhận HTTP”, “đọc đủ body”, “parse được” và “nghiệp vụ đạt yêu cầu” giúp kiểm thử chính xác hơn.

### 13.3. Lỗi cấu hình trước khi gọi mạng

URI sai cú pháp, thiếu cấu hình hoặc yêu cầu bị circuit breaker từ chối ngay tại client có thể xảy ra trước khi có DNS hay kết nối. Đừng gán chúng thành lỗi server chỉ vì người dùng bấm nút gọi API.

## 14. Bài tập phân loại

Với mỗi tình huống, hãy nêu lớp lỗi quan sát được, điều chưa biết và bước kiểm tra tiếp theo.

### A. Client báo UnknownHostException

Không có status HTTP. Đây là dấu hiệu phân giải/địa chỉ ở client. Kiểm tra hostname, resolver và môi trường thực của tiến trình. Chưa kết luận dịch vụ nghiệp vụ bị sập.

### B. TCP 443 thành công nhưng chứng thư không khớp hostname

Đường TCP kiểm tra được, nhưng xác minh danh tính TLS thất bại. Kiểm tra URI, chứng thư, SNI và điểm TLS termination; thành công của TCP không bác bỏ lỗi TLS.

### C. Client nhận HTTP 502, gateway ghi DNS upstream lỗi

Client quan sát response HTTP từ gateway. Gateway quan sát lỗi phân giải ở chặng khác. Giữ hai thông tin cùng lúc thay vì chọn một nhãn và bỏ thông tin còn lại.

### D. Client timeout sau 2 giây, gateway trả 504 ở giây thứ 5

Client không được báo đã nhận 504 nếu không đọc status đó. Đối chiếu log theo chặng và thời gian; điều chỉnh ngân sách cần tính cả thời gian phản hồi và mục tiêu nghiệp vụ.

### E. POST tạo đơn bị reset trước khi client nhận mã đơn

Kết quả nghiệp vụ chưa biết. Dùng cơ chế idempotency hoặc truy vấn/đối soát kết quả; không tạo request mới một cách mù quáng.

### F. curl nhận 404 nhưng exit code bằng 0

Có thể là hành vi mặc định của công cụ nếu chuyển giao hoàn tất. Đọc HTTP status và tùy chọn curl; exit code 0 không chứng minh nghiệp vụ thành công.

### G. Java nhận 200 rồi đọc body bị lỗi

Đã có bằng chứng về response header, nhưng chưa có response content hoàn chỉnh. Ghi cả status đã thấy và lỗi đọc; không dùng body thiếu như dữ liệu hợp lệ.

## 15. Checklist trước khi kết luận

- [ ] Đã phân biệt URI/cấu hình sai với lỗi trong quá trình truyền thông.
- [ ] Đã biết có response HTTP thực hay chỉ có exception ở client.
- [ ] Đã xác định chặng đang nói tới: client–gateway hay gateway–upstream.
- [ ] Đã xem exception gốc, status và mức hoàn tất body.
- [ ] Đã kiểm tra từ đúng môi trường mạng của tiến trình lỗi.
- [ ] Đã đọc đúng phạm vi timeout thay vì gọi mọi timeout là 504.
- [ ] Đã tách lỗi TLS khỏi xác thực/phân quyền HTTP.
- [ ] Đã đánh giá khả năng request có tác dụng phụ trước khi retry.
- [ ] Đã giữ riêng mã lỗi công cụ, nhãn nội bộ và HTTP status.
- [ ] Đã ghi đủ bằng chứng để đối chiếu mà không lộ dữ liệu nhạy cảm.

Câu hỏi hữu ích khi gặp sự cố là: tiến trình nào quan sát lỗi, trên chặng nào, đã đi tới giai đoạn nào và bằng chứng nào cho biết điều đó? Trả lời được các câu hỏi này giúp chọn đúng nơi sửa, giữ đúng hợp đồng lỗi và bảo vệ nghiệp vụ khi kết quả của một lần gọi chưa rõ.
