# HSTS và chống hạ cấp kết nối

> **Chương:** TLS và bảo mật kênh truyền  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi:** Bảo vệ kênh HTTP/HTTPS và phiên TLS trong kiến trúc phòng vệ mạng nhiều lớp: DNS, firewall, WAF/CDN, reverse proxy, VPN, hệ thống nhận dạng, giám sát xâm nhập và dịch vụ cloud.

## 1. HSTS và chống hạ cấp kết nối giải quyết điều gì?

**HTTPS** bảo vệ tính bí mật và toàn vẹn của nội dung HTTP trên đường truyền bằng **TLS**, đồng thời giúp client xác thực tên máy chủ qua chứng chỉ khi được cấu hình và kiểm tra đúng. Tuy nhiên, một dịch vụ có HTTPS **chưa chắc mọi lần truy cập đều bắt đầu và duy trì trên kết nối an toàn**.

Một người dùng có thể gõ **http://portal.example.com** hoặc theo liên kết HTTP cũ. Server dự định trả **301/308 redirect sang HTTPS**. Nếu request ban đầu đi qua HTTP thuần, một đối tượng có khả năng can thiệp trên đường mạng có thể ngăn hoặc sửa redirect trước khi trình duyệt thiết lập TLS. Kiểu làm yếu đường đi từ HTTPS về HTTP thường được gọi là **HTTPS stripping / SSL stripping**.

**HTTP Strict Transport Security (HSTS)** là cơ chế để website thông báo cho **user agent có hỗ trợ**: trong một khoảng thời gian, hãy chỉ truy cập hostname này bằng HTTPS và không cho phép bỏ qua các lỗi TLS/certificate thuộc phạm vi HSTS. Khi đã có chính sách HSTS hợp lệ, trình duyệt chuyển những lần truy cập HTTP tương ứng sang HTTPS **trước khi gửi request không mã hóa**.

**Chống hạ cấp kết nối** còn rộng hơn HSTS. Một đường truyền có thể gặp vấn đề ở nhiều mức:

- **HTTP → HTTPS:** request bắt đầu qua HTTP hoặc bị giữ ở HTTP; HSTS giảm rủi ro này đối với user agent hỗ trợ.
- **TLS phiên bản mạnh → phiên bản yếu:** phía client/server bị buộc dùng phiên bản TLS cũ hoặc cấu hình fallback thiếu an toàn; cần kiểm soát phiên bản giao thức, bắt tay TLS và cơ chế chống downgrade.
- **Cipher/đặc tính bảo mật không phù hợp:** server/client bật bộ mật mã lỗi thời hoặc thuật toán không được chính sách cho phép; cần TLS configuration và validation.
- **TLS tại edge nhưng plaintext tới origin:** trình duyệt có HTTPS, song đoạn CDN/WAF → ứng dụng có thể không được bảo vệ; HSTS không mã hóa đoạn đó.
- **Nội dung hỗn hợp hoặc liên kết ra site khác:** trang HTTPS gọi tài nguyên HTTP/endpoint không có chính sách tương đương; HSTS của trang chính không bảo vệ mọi hostname bên ngoài.

**Điểm cốt lõi:** HSTS giải quyết **chính sách sử dụng HTTPS tại client cho một hostname**, không tự thay thế TLS hiện đại, chứng chỉ hợp lệ, DNS security, phân đoạn, firewall hay xác thực ứng dụng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích cơ chế HSTS, cú pháp header và trạng thái HSTS trên trình duyệt.
2. Phân biệt **HTTP redirect, HSTS đã ghi nhớ, HSTS preload** và giới hạn "first visit".
3. Đánh giá các tùy chọn **max-age, includeSubDomains, preload**, giai đoạn rollout và rollback.
4. Phân biệt **HTTP downgrade** với **TLS protocol downgrade**, hiểu vai trò của TLS 1.2/1.3 và các cơ chế phát hiện fallback.
5. Thiết kế HSTS đúng tại **CDN/WAF, load balancer, reverse proxy, origin**, với DNS, TLS certificate và cookie an toàn.
6. Dùng công cụ đọc trạng thái HTTP/TLS để kiểm tra có phép, cùng ma trận test browser/hostname/IPv4/IPv6.
7. Xử lý lỗi chứng chỉ, subdomain cũ, HSTS preload, CDN cache, reverse proxy và chính sách thay đổi không đồng nhất.

## 2. Phân biệt HTTP, HTTPS, TLS và trạng thái HSTS

| Thành phần | Chức năng | Giới hạn |
|---|---|---|
| **HTTP** | Giao thức ứng dụng trao đổi request/response | HTTP thuần không mặc định mã hóa hoặc xác thực máy chủ |
| **HTTPS** | HTTP sử dụng kênh được bảo vệ bằng TLS | Phụ thuộc TLS/certificate validation và toàn bộ đường đi |
| **TLS** | Giao thức bảo mật kênh, hỗ trợ xác thực endpoint và mã hóa | Không tự quyết định user có được phép xem dữ liệu nghiệp vụ |
| **Chứng chỉ máy chủ** | Liên kết public key với danh tính tên miền theo trust model | Chỉ có chứng chỉ không bảo đảm ứng dụng không có lỗ hổng |
| **Redirect 301/308** | Thông báo client chuyển URL sang vị trí HTTPS | Redirect phát trên HTTP có thể bị can thiệp trước TLS |
| **HSTS** | Chính sách phía client ghi nhớ chỉ sử dụng HTTPS cho hostname | User agent không hỗ trợ/không biết HSTS vẫn có thể thử HTTP |
| **HSTS preload** | Một số trình duyệt có sẵn danh sách hostname cần HTTPS | Phụ thuộc chương trình preload, bản cập nhật client và quy trình gỡ |
| **Firewall/WAF** | Kiểm soát luồng mạng hoặc request theo policy | Không thay chính sách TLS/certificate validation ở client |
| **DNS/DNSSEC** | Phân giải tên và có thể xác thực dữ liệu DNS được ký | DNSSEC không tự ép HTTP thành HTTPS |

### 2.1. HSTS không phải redirect ở server

Với **HTTP redirect** thông thường, client thường phải gửi một request HTTP đến server để nhận chỉ dẫn chuyển sang HTTPS. Với **HSTS còn hiệu lực**, user agent biết chính sách sẽ **chuyển URL sang HTTPS trước khi thực hiện network request** tương ứng.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Trình duyệt chưa biết HSTS
    participant N as Mạng HTTP
    participant S as Website
    U->>N: GET http://portal.example.com
    N->>S: Request HTTP đầu tiên
    S-->>U: 301/308 Location: https://portal.example.com
    U->>S: TLS + GET https://portal.example.com
    S-->>U: HTTPS response + Strict-Transport-Security
    Note over U: Ghi nhớ HSTS nếu policy hợp lệ
    Note over U,S: Lần sau HTTP URL được nâng lên HTTPS trước network
~~~

Sơ đồ là tình huống **redirect hợp lệ**. Nếu attacker can thiệp HTTP ở lần đầu, client có thể **không tới được response HTTPS mang HSTS**. Đây chính là lý do cần hiểu **first-visit problem**.

## 3. SSL stripping, HTTP downgrade và giới hạn của redirect

Giả sử trang đăng nhập **portal.example.com** cung cấp HTTPS, nhưng một liên kết cũ bắt đầu bằng HTTP. Một kẻ can thiệp **on-path** có thể cố thay đổi hoặc chặn phản hồi redirect ở chặng HTTP chưa được bảo vệ. Người dùng có thể thấy một trang HTTP và nhầm rằng phiên làm việc vẫn an toàn nếu không kiểm tra URL và cảnh báo.

**Điều kiện rủi ro:** người dùng truy cập HTTP trước khi trình duyệt có HSTS cho hostname đó, hoặc user agent không hỗ trợ/không tuân thủ HSTS. Không cần giả định nội dung đã bị đánh cắp; phải có bằng chứng data path và truy cập thực tế để xác định tác động sự cố.

### 3.1. Vì sao "luôn redirect sang HTTPS" vẫn chưa đủ?

1. Request HTTP đầu tiên vẫn đi trên đường truyền không có TLS.
2. Redirect từ HTTP có thể bị can thiệp trước khi client nhận.
3. Cookie hoặc URL nhạy cảm có thể bị lộ nếu ứng dụng cho phép tạo request HTTP không an toàn.
4. Một số client không tuân theo redirect hoặc có logic fallback riêng.

**Biện pháp kết hợp:** HTTPS làm mặc định, HTTP chỉ phục vụ chuyển hướng tối thiểu khi cần, HSTS trên response HTTPS hợp lệ, cookie **Secure**, kiểm tra chứng chỉ và xóa URL HTTP trong ứng dụng/tài liệu.

### 3.2. HSTS chỉ bảo vệ hostname thuộc phạm vi

HSTS của **portal.example.com** không mặc định bảo vệ **login.other-example.net** hoặc **api.example.org**. Nếu ứng dụng redirect sang domain khác hoặc tải tài nguyên từ hostname khác, mỗi hostname cần đánh giá chính sách HTTPS/TLS riêng.

## 4. Cú pháp Strict-Transport-Security

Website thông báo HSTS qua **HTTP response header** trên **kết nối HTTPS đã được xác thực hợp lệ**:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Trong ví dụ:

- **Strict-Transport-Security** là tên header.
- **max-age=31536000** chỉ số giây user agent ghi nhớ chính sách từ lần nhận header hợp lệ; đây là khoảng **một năm 365 ngày**.
- **includeSubDomains** mở rộng phạm vi chính sách xuống các subdomain của hostname phát header.

Tham số **preload** có thể được thêm như một **tín hiệu tham gia chương trình preload của trình duyệt**, không phải chỉ thị HSTS cốt lõi khiến trình duyệt tự động được preload ngay:

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

**Giá trị max-age không phải thời gian tồn tại của chứng chỉ TLS, DNS TTL hay cache HTML.** Đây là thời gian trạng thái HSTS tồn tại tại user agent và có thể được gia hạn khi nhận response HTTPS mới có header hợp lệ.

### 4.1. Các directive

| Directive | Tác dụng | Rủi ro vận hành |
|---|---|---|
| **max-age=N** | Bật chính sách trong N giây kể từ lần nhận hợp lệ | N quá lớn khiến cấu hình HTTPS sai khó khắc phục từ phía website |
| **includeSubDomains** | Áp chính sách cho các tên nằm dưới hostname đã khai báo | Có thể làm hỏng legacy/dev/partner subdomain còn HTTP |
| **preload** | Tín hiệu hỗ trợ quy trình đăng ký preload ở những trình duyệt/danh sách có áp dụng | Không tự có hiệu lực nếu chưa được chấp nhận/phân phối; gỡ rất chậm |
| **max-age=0** | Yêu cầu xóa trạng thái HSTS động của hostname gửi header | Không gỡ được chính sách HSTS kế thừa từ cha và không gỡ ngay preload tích hợp |

### 4.2. Điều kiện user agent chấp nhận HSTS

Theo mô hình chuẩn, user agent chỉ ghi nhận/cập nhật HSTS khi:

- Header đến từ **kết nối HTTPS an toàn với danh tính máy chủ được xác minh**.
- Cú pháp header và tham số quan trọng hợp lệ.
- Hostname phù hợp với phạm vi xử lý HSTS (thông thường là **DNS hostname**, không phải IP literal).

**Header HSTS gửi qua HTTP thuần bị bỏ qua.** Nếu server trả:

~~~http
HTTP/1.1 301 Moved Permanently
Location: https://portal.example.com/
Strict-Transport-Security: max-age=31536000
~~~

trên **kết nối HTTP không mã hóa**, trình duyệt tuân thủ chuẩn **không lấy chính header đó làm bằng chứng HSTS đáng tin**. HSTS cần xuất hiện trên **response HTTPS hợp lệ**.

### 4.3. Gửi HSTS trên những response nào?

Nên phát HSTS nhất quán trên **HTTPS response thích hợp**, không chỉ trang chủ 200. Một người dùng có thể lần đầu tới API 401, trang 404, redirect HTTPS hoặc trang lỗi do proxy tạo. Khi những response HTTPS đó **không mang header**, cơ hội để client học hoặc gia hạn HSTS có thể bị bỏ lỡ.

Lưu ý cần cấu hình tại **đúng TLS endpoint** và tránh header trùng lặp/khác nhau giữa CDN, WAF, reverse proxy và ứng dụng.

## 5. Phạm vi HSTS theo hostname và subdomain

Giả sử:

- **example.com**: website chính.
- **www.example.com**: frontend.
- **api.example.com**: API.
- **admin.example.com**: portal quản trị.
- **legacy.example.com**: ứng dụng cũ chưa dùng HTTPS.

### 5.1. Chỉ khai báo trên một subdomain

Nếu **www.example.com** gửi:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

thì policy được ghi nhận cho **www.example.com**. Nó **không tự động áp lên example.com hoặc api.example.com**.

### 5.2. Khai báo tại domain cha với includeSubDomains

Nếu **example.com** gửi:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

thì trình duyệt đã biết HSTS của **example.com** sẽ yêu cầu HTTPS cho **example.com và các subdomain**, kể cả các subdomain có nhiều cấp. Vì vậy **legacy.example.com** có thể không còn truy cập được qua HTTP từ những trình duyệt này nếu nó chưa sẵn sàng HTTPS.

~~~mermaid
flowchart TD
    P[example.com - HSTS + includeSubDomains] --> W[www.example.com]
    P --> A[api.example.com]
    P --> M[admin.example.com]
    P --> L[legacy.example.com]
    L --> X{Legacy có HTTPS + cert hợp lệ?}
    X -- Không --> F[Client HSTS không cho dùng HTTP fallback]
    X -- Có --> OK[Truy cập HTTPS phù hợp]
~~~

**HSTS của cha vẫn có hiệu lực ở con dù con không tự phát HSTS.** Một subdomain gửi **max-age=0** có thể xóa chính sách động cho chính nó nếu có, nhưng **không thể ghi đè quy tắc includeSubDomains còn hiệu lực từ domain cha**.

### 5.3. Domain được chuyển giao/ủy quyền

Nếu tổ chức dùng subdomain cho **đối tác, hệ thống dev, mail web interface hoặc ứng dụng nội bộ qua VPN**, việc bật includeSubDomains ở apex có thể ảnh hưởng những dịch vụ này. Cả các tên được quản trị bởi một nhà cung cấp khác nhưng nằm dưới namespace cũng phải được đưa vào **inventory** và kế hoạch kiểm thử.

### 5.4. HSTS với địa chỉ IP và port

Không nên dựa vào HSTS cho URL sử dụng **IP literal** như https://192.0.2.10; chính sách HSTS theo chuẩn/trình duyệt chủ yếu áp dụng DNS hostname. HSTS cũng **không phải firewall theo cổng**: khi chuyển URL HTTP, cổng 80 thường được đổi thành 443; nếu URL chỉ định một **cổng khác 80**, chính sách có những quy tắc giữ cổng tương ứng và client vẫn phải dùng HTTPS. Dịch vụ HTTPS ở cổng không chuẩn cần kiểm thử theo user agent và kiến trúc thực tế.

## 6. HSTS dynamic và bài toán first visit

**Dynamic HSTS** là chính sách được trình duyệt học từ header HTTPS trong một phiên truy cập hợp lệ. Nó có ích từ **lần sau**, nhưng trước lần đầu tiên nhận được policy, client có thể vẫn truy cập HTTP.

| Trạng thái trình duyệt | Người dùng nhập http://example.com | Rủi ro chính |
|---|---|---|
| **Chưa biết HSTS** | Có thể gửi HTTP trước khi nhận redirect | First-visit attack surface |
| **Đã ghi nhớ HSTS còn hạn** | Chuyển sang HTTPS trước network request | Phụ thuộc TLS/certificate và user agent tuân thủ |
| **HSTS hết hạn** | Có thể quay về xử lý URL HTTP thông thường | Cần server tiếp tục phục vụ HTTPS/HSTS |
| **Có trong preload list của browser** | Chuyển sang HTTPS từ lần đầu cho tên trong phạm vi preload | Phụ thuộc trình duyệt/danh sách được cài và cập nhật |
| **Client không hỗ trợ HSTS** | Theo hành vi HTTP/redirect riêng | HSTS không thể cưỡng chế ở client này |

### 6.1. First visit không thể sửa hoàn toàn chỉ bằng header

Server không thể bảo vệ một **HTTP response chưa được xác thực** bằng cách chỉ gửi thêm HSTS trên chính HTTP response đó. Phải có **kênh HTTPS được xác thực** hoặc cơ chế browser đã biết trước (ví dụ preload, HTTPS-First/HTTPS-Only mode tùy trình duyệt) để tránh tiếp xúc HTTP ban đầu.

Vì thế khi xây dựng website mới, hãy **xuất bản URL HTTPS** trong email, tài liệu, QR code, API docs, OAuth redirect URI và hệ thống nội bộ; tránh tạo điểm vào HTTP không cần thiết.

### 6.2. Khi HSTS hết hạn hoặc trình duyệt xóa dữ liệu

Người dùng có thể xóa browser state, đổi thiết bị, dùng trình duyệt mới hoặc kết nối qua client không có hỗ trợ HSTS. HSTS dynamic **không phải bảo đảm vĩnh viễn**; cần duy trì redirect an toàn và HTTPS hoạt động ổn định, còn preload nếu phù hợp có thể giảm first-visit risk cho các browser hỗ trợ.

## 7. HSTS preload: lợi ích, điều kiện và trách nhiệm vận hành

**HSTS preload** là cơ chế một số browser phân phối trước danh sách hostname bắt buộc HTTPS. Với tên đã nằm trong danh sách preload của một trình duyệt, client **không cần đợi một lần truy cập HTTPS trước đó** để áp HSTS.

### 7.1. Cần làm gì trước khi cân nhắc preload?

1. Kiểm kê **toàn bộ subdomain**, gồm dịch vụ phụ, dev/staging công khai, endpoint người dùng cũ và hostname do đối tác vận hành.
2. Bảo đảm **HTTPS hợp lệ trên apex và mọi subdomain nằm trong phạm vi**, kể cả trang lỗi và luồng chuyển hướng.
3. Duy trì DNS, chứng chỉ, TLS và hệ thống gia hạn chứng chỉ ổn định; chuẩn bị cho giai đoạn cert rotation và sự cố CA.
4. Cấu hình redirect HTTP → HTTPS và header HSTS thích hợp.
5. Kiểm tra **điều kiện nộp** trong hệ thống preload mà bạn định tham gia (chẳng hạn chương trình được các browser dựa trên Chromium sử dụng).
6. Hiểu **thời gian đưa vào danh sách và gỡ khỏi danh sách** phụ thuộc quy trình review/bản phát hành trình duyệt; không có bảo đảm thay đổi lập tức.

Một số chương trình preload thường yêu cầu **max-age dài (ví dụ ít nhất một năm), includeSubDomains và directive preload**, cùng các điều kiện HTTPS/redirect khác. **Đây là tiêu chí chương trình, không phải quy tắc bắt buộc của RFC 6797**, và có thể thay đổi; phải xác minh điều kiện hiện hành trên trang chương trình trước khi nộp.

### 7.2. Header preload không đồng nghĩa đã được preload

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

Header này có thể là một phần của việc đăng ký, nhưng **trình duyệt không tự thêm tên miền vào preload list chỉ vì thấy chữ preload**. Cần trạng thái được chương trình chấp nhận và phân phối thực tế. Đồng thời **directive preload không phải yêu cầu bắt buộc để dynamic HSTS hoạt động**.

### 7.3. Rủi ro vận hành nghiêm trọng

Một tổ chức dùng **printer.example.com** trên mạng nội bộ với HTTP thuần hoặc một ứng dụng legacy ở **legacy.example.com** có thể thấy truy cập từ các browser hỗ trợ bị lỗi khi domain cha đã preload với includeSubDomains. **Không thể sửa ngay bằng cách bỏ header tại apex**: browser vẫn giữ trạng thái preload tích hợp cho đến khi được cập nhật theo quy trình.

### 7.4. Không nộp preload như một bài kiểm thử nhanh

Chỉ preload khi domain owner kiểm soát vòng đời DNS, TLS, subdomain và có năng lực duy trì HTTPS **lâu dài**. Thử nghiệm trước với **dynamic HSTS ngắn** trên hostname phạm vi hẹp, đánh giá dần; đừng đưa domain sản xuất vào preload để xem "có làm được không".

## 8. Lộ trình triển khai HSTS an toàn

### Giai đoạn 0 — Kiểm kê và chuẩn hóa HTTPS

Thu thập:

- Domain, subdomain, owner, DNS view và tình trạng HTTPS của từng dịch vụ.
- URL HTTP còn xuất hiện trong email, trang web, API clients, mobile apps và tài liệu.
- Chứng chỉ TLS, SAN/hostname, CA, auto-renewal, alert hết hạn và key management.
- TLS termination tại CDN/WAF, load balancer, reverse proxy và origin.
- Các hostname chỉ dùng trong VPN, private DNS, staging hoặc hệ thống OT/IoT.
- Những client không phải browser có thể **không hỗ trợ HSTS**, ví dụ thư viện HTTP cũ.

### Giai đoạn 1 — HTTPS và redirect trước, HSTS ngắn

Khi HTTPS đã được xác minh, triển khai HSTS với max-age ngắn và **chưa includeSubDomains** ở hostname cụ thể:

~~~http
Strict-Transport-Security: max-age=300
~~~

Đây là giá trị minh họa **5 phút** để giảm hậu quả khi cần sửa. Cần nhớ: trong 5 phút, một số browser vẫn áp HSTS ngay cả sau khi website xóa header; thao tác rollback không có tác dụng tức thời trên client đã ghi nhớ.

### Giai đoạn 2 — Tăng thời hạn theo kiểm thử

Khi đã xác nhận HTTPS, certificate renewal, API, caching và user agents ổn định, có thể tăng có kiểm soát:

~~~http
Strict-Transport-Security: max-age=86400
~~~

Sau đó tiến đến thời hạn dài hơn theo yêu cầu và rủi ro chấp nhận, ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Không có lịch "5 phút → 1 ngày → 1 năm" bắt buộc. **Thời điểm tăng** phải dựa trên coverage, lỗi TLS thực tế, ứng dụng phụ thuộc và kế hoạch rollback.

### Giai đoạn 3 — includeSubDomains khi toàn namespace đã sẵn sàng

Chỉ khi **mọi subdomain** trong phạm vi có thể dùng HTTPS hợp lệ và được owner xác nhận, cân nhắc:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

### Giai đoạn 4 — Cân nhắc preload

Khi có nhu cầu giảm first-visit risk và năng lực quản trị lâu dài, kiểm tra yêu cầu chương trình preload và tác động tới toàn bộ DNS namespace rồi mới đăng ký.

~~~mermaid
flowchart TD
    A[Inventory hostname + cert + TLS termination] --> B[HTTPS hoạt động và redirect được kiểm thử]
    B --> C[HSTS max-age ngắn trên hostname mục tiêu]
    C --> D{Browser/API/cert rotation và các lỗi đã ổn?}
    D -- Không --> E[Chỉnh TLS/HTTPS, giữ thời hạn thấp]
    E --> C
    D -- Có --> F[Tăng max-age theo policy]
    F --> G{Mọi subdomain và delegated hostname đều HTTPS-ready?}
    G -- Không --> H[Chưa bật includeSubDomains]
    G -- Có --> I[Cân nhắc includeSubDomains]
    I --> J{Cần preload và có khả năng vận hành lâu dài?}
    J -- Không --> K[Duy trì dynamic HSTS + monitoring]
    J -- Có --> L[Đánh giá/nộp theo chương trình preload]
~~~

## 9. Rollback HSTS và những điều không thể đảo ngược ngay

### 9.1. max-age=0 hoạt động ra sao?

Nếu website gửi từ **kết nối HTTPS hợp lệ**:

~~~http
Strict-Transport-Security: max-age=0
~~~

user agent tuân thủ có thể xóa **trạng thái HSTS động** của hostname đó. Tuy nhiên:

- Client cần **thực sự nhận được response HTTPS hợp lệ chứa header**.
- Nếu HTTPS đang lỗi chứng chỉ, nhiều browser HSTS **không cho bỏ qua lỗi** để nhận header xóa.
- Nếu domain cha vẫn có **includeSubDomains**, host con vẫn chịu chính sách của cha.
- Nếu domain đang nằm trong **preload list tích hợp**, max-age=0 **không làm tên biến mất ngay** khỏi danh sách của browser.
- Người dùng offline hoặc không truy cập lại sẽ không nhận lệnh xóa.

### 9.2. Vì sao rollback phải được lên kế hoạch trước?

Nếu HSTS với max-age dài được phát nhầm cho **legacy hostname không có HTTPS**, nhóm vận hành có thể không dễ quay về "dùng lại HTTP" vì browser đã ghi nhớ chính sách. Đường phục hồi đáng tin hơn thường là **sửa HTTPS/certificate/TLS trước**, thay vì dựa vào việc người dùng xóa browser state hoặc tắt kiểm tra bảo mật.

### 9.3. Nguyên tắc xử lý sự cố

**Không hướng dẫn người dùng bỏ qua cảnh báo chứng chỉ, cài CA không tin cậy hoặc tắt HSTS để tiếp tục đăng nhập.** Cần khôi phục hostname/certificate hợp lệ, rollback cấu hình proxy sai và xác minh mọi endpoint nằm trong phạm vi.

## 10. HSTS và kiểm tra chứng chỉ TLS

HSTS chỉ có ý nghĩa khi **HTTPS được xác thực đúng**. Trình duyệt kiểm tra chứng chỉ máy chủ theo trust model, bao gồm chain tới trust anchor phù hợp, thời hạn, hostname, mục đích sử dụng và các chính sách liên quan.

### 10.1. Những lỗi điển hình

| Lỗi | Tác động khi HSTS đang hiệu lực | Cách khắc phục đúng |
|---|---|---|
| **Chứng chỉ hết hạn** | Browser từ chối HTTPS và không cho fallback HTTP | Gia hạn/triển khai chứng chỉ hợp lệ |
| **Sai hostname / SAN** | Browser không xác thực được đích | Cấp cert cho hostname đang dùng |
| **Thiếu intermediate chain** | Một số client không xây dựng được chuỗi tin cậy | Cấu hình full chain đúng |
| **CA không được tin cậy** | TLS validation thất bại | Dùng CA hợp lệ; private PKI cần quản trị trust đúng |
| **TLS version/cipher không tương thích** | Kết nối thất bại trước khi nhận HSTS mới | Sửa negotiation và policy phiên bản được hỗ trợ |
| **SNI/virtual host sai** | Server có thể trả cert của host khác | Kiểm tra SNI, listener, edge routing |
| **Đồng hồ client sai** | Đánh giá thời hạn chứng chỉ không chính xác | Sửa clock/time sync, không tắt validation |

### 10.2. Vì sao HSTS ngăn click-through với lỗi TLS?

Đối với hostname đang chịu chính sách HSTS, user agent tuân thủ không được coi **người dùng chọn bỏ qua chứng chỉ lỗi** là một đường hoạt động bình thường. Tính chất này ngăn kẻ on-path lợi dụng thao tác "tiếp tục dù không an toàn" để làm suy yếu kết nối.

**Lưu ý:** cách hiển thị lỗi khác nhau theo trình duyệt, nhưng chính sách đúng không nên dựa vào việc cho user bỏ qua certificate error. Với domain nội bộ nằm dưới cha có HSTS includeSubDomains, phải quản lý **private PKI và trust store** trên client đúng chuẩn.

### 10.3. HSTS không thay certificate lifecycle

Vẫn phải có certificate issuance, automated renewal, rotation, key protection, alert, xác minh SAN, TLS tests và kế hoạch sự cố CA. HSTS làm việc vận hành HTTPS **quan trọng hơn**, không giúp chữa một chứng chỉ sai.

## 11. TLS protocol downgrade khác HTTP downgrade thế nào?

**HTTP downgrade** là thay đổi cách client sử dụng URL/protocol HTTP và HTTPS. **TLS protocol downgrade** là tình huống client/server sử dụng phiên bản TLS yếu hơn mức lẽ ra có thể và nên thỏa thuận, đôi khi do tương tác fallback thiếu an toàn hoặc can thiệp trong quá trình bắt tay.

### 11.1. Ví dụ logic

Một client và server đều hỗ trợ TLS 1.3. Kết nối bình thường nên thương lượng TLS 1.3 (trừ các điều kiện cấu hình/triển khai khác). Nếu một thiết kế có **fallback thiếu kiểm soát sang phiên bản cũ** khi bắt tay lỗi, attacker có thể cố tận dụng hành vi fallback để giảm mức bảo mật.

Ngược lại, nếu một server hợp lệ chỉ hỗ trợ TLS 1.2 còn client hỗ trợ 1.2/1.3, việc hai bên thương lượng TLS 1.2 **không tự là một cuộc tấn công downgrade**. Cần đánh giá **khả năng thực, chính sách tối thiểu và bằng chứng can thiệp**.

### 11.2. Ba nhóm phòng vệ

1. **Không hỗ trợ phiên bản yếu**: trên web hiện đại nên ưu tiên TLS 1.3 và hỗ trợ TLS 1.2 khi cần tương thích; vô hiệu hóa TLS 1.0/1.1 và SSL cũ theo chuẩn/đánh giá rủi ro.
2. **Triển khai negotiation đúng chuẩn**: không viết fallback tùy tiện và dùng các cơ chế phát hiện downgrade được hỗ trợ bởi phiên bản giao thức.
3. **Giám sát handshake failures và phiên bản thực**: quan sát phân bố TLS version/cipher, client legacy, thay đổi sau deploy và mạng middlebox.

**HSTS không chọn phiên bản TLS**, không ép client dùng TLS 1.3 và không thay TLS configuration của server.

## 12. TLS 1.2, TLS 1.3 và chống fallback

### 12.1. Chọn minimum TLS version

Trong đa số dịch vụ HTTPS mới, nên áp chính sách tối thiểu **TLS 1.2** và ưu tiên **TLS 1.3**, đồng thời xem yêu cầu tương thích của client và chuẩn tổ chức. RFC 8996 đã đánh dấu TLS 1.0 và TLS 1.1 là các phiên bản bị loại bỏ khỏi sử dụng hiện đại. Không dựa vào "browser đã có HSTS" để tiếp tục giữ TLS 1.0/1.1 ở server.

### 12.2. TLS_FALLBACK_SCSV

**TLS_FALLBACK_SCSV** theo RFC 7507 hỗ trợ server nhận biết một client đang thực hiện **fallback có chủ đích xuống phiên bản thấp hơn mức server hỗ trợ**, nhằm ngăn một số trường hợp hạ cấp không phù hợp trong hệ sinh thái TLS trước đây. Nó **không thay minimum TLS version** và không thay HSTS.

### 12.3. Cơ chế downgrade protection của TLS 1.3

RFC 8446 định nghĩa cách biểu diễn phiên bản và một số **dấu hiệu downgrade** trong trường server random khi server có hỗ trợ TLS 1.3 nhưng thương lượng phiên bản cũ hơn trong hoàn cảnh quy định. Cơ chế này giúp client phát hiện một số hành vi downgrade trong quá trình bắt tay.

**Giới hạn:** cần implement đúng ở cả hai phía; không có một flag đơn lẻ thay thế xác thực handshake, danh sách phiên bản được phép và kiểm soát fallback. **Không nên cố sửa thủ công dữ liệu handshake** như một phương pháp kiểm thử thông thường.

### 12.4. TLS 1.3 0-RTT không phải downgrade

TLS 1.3 có thể hỗ trợ **early data (0-RTT)** ở một số triển khai. Đây là một vấn đề **replay risk** đối với thao tác không idempotent nếu ứng dụng xử lý không đúng, **không phải cùng một cơ chế với HTTP stripping hoặc TLS version downgrade**. Khi bật 0-RTT phải đánh giá ứng dụng và anti-replay theo kiến trúc.

## 13. Cipher suites, SNI, ALPN và xác thực kênh

| Khái niệm | Chức năng | Vì sao không được nhầm với HSTS |
|---|---|---|
| **TLS cipher suite** | Lựa chọn thuật toán bảo vệ phiên theo phiên bản TLS | HSTS không quyết định thuật toán |
| **SNI** | Client thông báo tên máy chủ ở giai đoạn TLS thích hợp để chọn virtual host/cert | Sai SNI có thể trả nhầm cert, HSTS không sửa được |
| **ALPN** | Thỏa thuận giao thức ứng dụng như HTTP/1.1, HTTP/2 | ALPN không đồng nghĩa bị hạ cấp TLS |
| **TLS certificate validation** | Xác thực endpoint theo hostname và trust chain | Phải hoạt động đúng để HSTS đáng tin |
| **mTLS** | Hai phía xác thực bằng certificate theo chính sách | HSTS không thay việc xác thực client |
| **HTTP/3/QUIC** | Vận chuyển HTTP qua QUIC với cơ chế TLS 1.3 tương ứng | Vẫn cần HTTPS/origin policy và kiểm thử đường edge |

**Không kết luận HTTP/2 → HTTP/1.1 là TLS downgrade**. Hai giao thức ứng dụng có đặc điểm và cơ chế negotiation riêng; cần xem TLS phiên bản, nguyên nhân chuyển protocol và chính sách hỗ trợ ở client/server.

### 13.1. Chặn phiên bản TLS yếu mà không phá dịch vụ

Trước khi thay minimum version:

1. Đo **phân bố phiên bản TLS thực tế** tại edge/load balancer.
2. Xác định client legacy có owner và mức độ quan trọng.
3. Kiểm tra API/mobile app, thiết bị IoT, VPN client và ứng dụng nội bộ đặc thù.
4. Thử nghiệm thay đổi trên staging/canary với certificate chain và SNI đúng.
5. Quy định ngoại lệ nếu thực sự cần, **cô lập trên hostname/endpoint riêng, có thời hạn và biện pháp bù**, thay vì làm yếu toàn website.

### 13.2. Phân biệt connection failure và tấn công

Không phải mọi handshake failure hoặc TLS 1.2 connection đều là dấu hiệu bị can thiệp. Chứng chỉ lỗi, thiếu cipher chung, proxy TLS inspection, firewall sai, middlebox không tương thích và client cũ có thể tạo triệu chứng tương tự. Cần log, baseline, network path và dữ liệu từ cả client/server.

## 14. HSTS tại CDN, WAF và reverse proxy

Trong kiến trúc thực, TLS có thể kết thúc tại nhiều nơi:

~~~mermaid
flowchart LR
    B[Browser] -->|HTTPS + valid cert| E[CDN / Edge WAF]
    E -->|HTTPS được xác thực riêng| L[Load Balancer / Reverse proxy]
    L -->|TLS/mTLS theo policy| A[Origin / Application]
    E -. HSTS response header tới browser .-> B
    E -. WAF/TLS logs .-> S[SOC / SIEM]
    L -. Backend TLS logs .-> S
~~~

**Browser chỉ thấy chứng chỉ và HTTP headers của endpoint nó kết nối**, thường là CDN/WAF hoặc load balancer công khai. HSTS phát ở origin có thể bị proxy loại bỏ, sửa hoặc thay bằng response lỗi tại edge. Hãy kiểm tra **response thực tế từ Internet**, không chỉ cấu hình application server.

### 14.1. Trách nhiệm từng lớp

| Thành phần | Cần làm gì | Rủi ro |
|---|---|---|
| **DNS** | Trỏ hostname tới edge/điểm phục vụ đúng | Trỏ sai origin, bypass WAF hoặc cert mismatch |
| **CDN/WAF** | HTTPS/TLS policy, HSTS header ở response, redirect, certificate | HTTP mode ở edge, response thiếu header, policy lệch giữa region |
| **Load balancer** | Đúng listener/TLS/certificate và X-Forwarded-* trust boundary | Redirect loop hoặc sai scheme detection |
| **Reverse proxy** | HTTPS to origin khi yêu cầu, header policy, redirect đúng | Chấp nhận header client giả khiến app nghĩ request là HTTPS |
| **Origin** | Xác thực TLS ở upstream và ứng dụng, chống direct-origin access | Plaintext trên đoạn internal/cloud không được kiểm soát |
| **Firewall/segmentation** | Chỉ edge được kết nối origin; quản trị riêng | Public origin bypass bảo vệ WAF/CDN |
| **SOC/SRE** | Thu event TLS/HSTS, cert expiry, routing và availability | Thiếu độ phủ logging hoặc thiếu kiểm thử từ ngoài |

### 14.2. Cẩn trọng với TLS ở từng hop

Nếu Browser → CDN dùng HTTPS, nhưng CDN → Origin dùng HTTP qua một mạng không được tin cậy, browser **không thể biết chỉ từ HSTS** rằng chặng sau an toàn. Nên yêu cầu **HTTPS/mTLS và xác thực certificate trên chặng edge–origin** theo threat model; không chỉ bật HTTPS rồi tắt xác thực chứng chỉ ở reverse proxy.

### 14.3. Header từ nhiều nơi

Nếu CDN, WAF và app cùng thêm **Strict-Transport-Security** với max-age khác nhau, response cuối có thể chứa nhiều giá trị hoặc bị override. Hành vi parse header không đồng nhất có thể tạo chính sách thực tế khó đoán. Nên **chỉ định owner duy nhất của HSTS policy tại TLS entrypoint**, hoặc có quy trình hợp nhất rõ ràng và kiểm thử header sau mọi proxy.

## 15. Ví dụ cấu hình HSTS theo intent, không ràng buộc hãng

### 15.1. Chính sách mong muốn

~~~yaml
# PSEUDOCODE: cấu hình ý định, không phải cú pháp cho CDN/Nginx/Apache.
https_transport_policy:
  hostname: "portal.example.com"
  owner: "Web Platform"
  tls:
    minimum_version: "TLS 1.2"
    prefer_tls_1_3: true
    validate_certificate_and_hostname: true
    origin_transport: "HTTPS validated where required"
  http:
    redirect_to_https: true
    never_accept_credentials_over_plain_http: true
  hsts:
    enabled: true
    max_age_seconds: 300
    include_subdomains: false
    preload: false
    emit_only_on_valid_https: true
    emit_on_https_error_responses: true
  cookies:
    secure_for_sensitive_sessions: true
    httponly_where_appropriate: true
    samesite_per_application_risk: true
  monitoring:
    check_external_edge_response: true
    detect_tls_version_regression: true
    alert_certificate_expiration: true
    audit_policy_changes: true
  rollout:
    canary: true
    rollback_plan: required
    include_subdomains_requires_owner_approval: true
~~~

### 15.2. Header trên reverse proxy Nginx (đoạn cấu hình minh họa)

~~~nginx
# Đặt trong HTTPS server block đã cấu hình listener, cert và key hợp lệ.
# KHÔNG coi đây là cấu hình production đầy đủ.
add_header Strict-Transport-Security "max-age=300" always;
~~~

**Ý nghĩa của always:** trên Nginx hỗ trợ directive này, header được thêm cả với nhiều response status mà cách thêm header thông thường có thể bỏ sót. Cần kiểm tra **định nghĩa thừa kế của add_header, location block, error handler và phiên bản Nginx**, vì cấu hình ở location khác có thể khiến kết quả không như dự kiến.

Không copy dòng này vào **HTTP server block** rồi cho rằng browser sẽ ghi nhớ HSTS. HSTS phải đến từ **response HTTPS hợp lệ**. Và nếu CDN ở trước Nginx, phải kiểm tra response mà browser thật nhận.

### 15.3. Không nâng max-age trước khi test

Đoạn Nginx trên dùng thời hạn ngắn có chủ đích. Sau khi QA, mới cân nhắc tăng theo lộ trình ở mục 8. **Không paste "max-age=63072000; includeSubDomains; preload" vào domain sản xuất** khi subdomain inventory chưa đầy đủ.

## 16. Redirect HTTP → HTTPS và vòng lặp qua reverse proxy

### 16.1. Redirect đúng

Client truy cập **http://portal.example.com/path** phải được điều hướng sang HTTPS tại hostname/URL thích hợp mà không mất thông tin không cần thiết. Các status như **301/308** có thể phù hợp tùy endpoint và yêu cầu phương thức HTTP; **308** giữ nguyên phương thức/body theo semantics, trong khi client có thể xử lý 301 khác nhau với các phương thức lịch sử.

**Không nên gửi thông tin nhạy cảm qua HTTP chỉ để đợi redirect.** API/mobile app nên gọi HTTPS ngay từ đầu; không phụ thuộc việc HTTP POST mang password rồi được redirect.

### 16.2. Vì sao xuất hiện redirect loop?

Ví dụ CDN kết thúc TLS, sau đó proxy tới backend bằng HTTP. Backend chỉ thấy HTTP và tự redirect về HTTPS; CDN tiếp tục gọi backend HTTP, tạo chuỗi redirect lặp.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant E as CDN TLS endpoint
    participant O as Origin app
    U->>E: HTTPS GET /dashboard
    E->>O: HTTP request qua backend (theo cấu hình)
    O-->>E: 301 Location: https://portal.example.com/dashboard
    E-->>U: 301
    U->>E: HTTPS GET /dashboard lại
    Note over E,O: Nếu backend vẫn hiểu sai scheme thì có thể lặp
~~~

**Cách khắc phục:** chuẩn hóa **trusted proxy headers**, scheme detection và kiến trúc TLS hop. Không tin giá trị **X-Forwarded-Proto** do client ngoài Internet tự gửi. Edge/proxy được tin cậy phải tạo hoặc ghi đè header theo kết nối đã xác minh.

### 16.3. Khi 301/308 bị cache

Redirect vĩnh viễn có thể được client hoặc các lớp cache ghi nhớ theo chính sách. Nếu hostname hoặc đường đích sai, rollback có thể có tác động kéo dài độc lập với HSTS. Do đó cần **kiểm thử location, HTTP methods, query parameters, canonical hostname và cache behavior** trước khi thay redirect đại trà.

## 17. HSTS, cookie Secure và mixed content

### 17.1. Cookie session

HSTS giảm nguy cơ browser gửi request HTTP cho hostname đã biết; tuy nhiên cookie session vẫn phải được cấu hình đúng:

~~~http
Set-Cookie: session_id=opaque-value; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Ví dụ chỉ mang tính minh họa, không phải cách tạo session token.

- **Secure:** cookie chỉ được gửi qua kết nối an toàn theo semantics của trình duyệt.
- **HttpOnly:** hạn chế JavaScript truy cập cookie (không tự ngăn mọi XSS/CSRF).
- **SameSite:** hỗ trợ chính sách gửi cookie trong ngữ cảnh cross-site, cần chọn theo luồng nghiệp vụ.

**HSTS không thay Secure, HttpOnly, SameSite, chống CSRF hoặc session management.**

### 17.2. Mixed content

Một trang HTTPS có thể cố tải hình ảnh, script, stylesheet hoặc kết nối qua HTTP. Browser hiện đại có cơ chế chặn hoặc nâng cấp một số loại mixed content, nhưng mức xử lý khác nhau theo loại tài nguyên và browser. Cần sửa **tất cả URL nội bộ/đối tác sang HTTPS** và thiết kế Content Security Policy (CSP) thích hợp.

Ví dụ một policy **được cân nhắc theo ứng dụng**, không dùng nguyên văn khi chưa test:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Directive này có thể khiến user agent nâng các yêu cầu tải tài nguyên không an toàn theo policy CSP, nhưng **không tương đương HSTS** và không bảo vệ mọi client/context. Trước khi áp dụng, cần kiểm tra tài nguyên HTTP không có HTTPS hoặc các luồng ngoại lệ.

### 17.3. WebSocket và API

Trang HTTPS nên sử dụng **wss://** cho kết nối WebSocket được bảo vệ; HTTP API cần gọi bằng **https://**. Không dựa vào HSTS để làm cho mọi SDK, native app hoặc non-browser client tự chuyển giao thức. Các hệ thống tự triển khai HTTP client cần **chính sách HTTPS/TLS/certificate riêng**.

## 18. DNS, DNSSEC, captive portal và điều hướng sai

HSTS hoạt động theo **hostname**, trong khi DNS quyết định IP nào được truy cập. Nếu resolver trả IP không mong đợi do cache poisoning hoặc hijacking, trình duyệt có HSTS vẫn yêu cầu HTTPS và **kiểm tra chứng chỉ cho hostname**. Một máy sai đích thiếu chứng chỉ phù hợp thường gây lỗi TLS thay vì được mặc nhiên tin cậy.

**Giới hạn:** DNSSEC giúp xác thực dữ liệu DNS được ký khi client dùng validator đúng, nhưng không thay HSTS và TLS. Ngược lại HSTS không đảm bảo địa chỉ DNS là đúng và không ngăn mọi lạm dụng khi kẻ tấn công có khả năng kiểm soát hệ thống phát certificate hoặc thiết bị tin cậy.

### 18.1. Wi-Fi công cộng và captive portal

Captive portal có thể dựa vào việc thiết bị phát hiện mạng cần đăng nhập bằng các URL thử nghiệm. Nếu người dùng truy cập một hostname HSTS trong lúc bị captive portal chặn hoặc redirect, trình duyệt có thể không cho hiện trang giả ở HTTPS. Đây là **hành vi bảo vệ mong muốn**, nhưng người dùng có thể báo "website không mở".

**Vận hành đúng:** dùng cơ chế captive portal được hệ điều hành hỗ trợ; không yêu cầu người dùng bỏ qua chứng chỉ của hostname HSTS để đăng nhập Wi-Fi.

### 18.2. Private DNS và VPN

Subdomain như **admin.example.com** có thể chỉ phân giải được bên trong VPN nhưng vẫn thuộc **includeSubDomains** của example.com trên browser. Nếu backend dùng HTTP hoặc chứng chỉ private PKI chưa được cấp trust, kết nối có thể lỗi dù DNS/VPN hoạt động. Cần **kiểm thử từ client qua VPN** và đảm bảo TLS private hostname hợp lệ.

## 19. HSTS khác WAF, IDS/IPS và các lớp phòng vệ mạng

| Lớp | Hỗ trợ chống hạ cấp/giảm rủi ro ra sao | Không thay thế |
|---|---|---|
| **HSTS ở browser** | Ngăn HTTP navigation cho host đã biết HSTS, buộc lỗi TLS rõ ràng | Không mã hóa edge → origin hay kiểm tra business authorization |
| **TLS 1.2/1.3 + certificate validation** | Bảo vệ kênh, chống một số kiểu downgrade TLS | Không tự ngăn request tới endpoint trái quyền |
| **WAF/CDN** | Redirect HTTPS, phát HSTS, phân loại request ở edge | Không sửa first-visit ở browser chưa biết HSTS nếu thiếu preload |
| **Network firewall** | Giới hạn inbound/outbound, chặn direct-to-origin | Không bảo đảm browser từ chối certificate sai |
| **VPN/mTLS** | Bảo vệ kết nối từ xa và một số hop nội bộ | Không thay HTTPS cho public web hoặc client authz |
| **DNSSEC/secure resolver** | Bảo vệ độ tin cậy DNS data theo cơ chế phù hợp | Không quyết định giao thức ứng dụng phải dùng HTTPS |
| **IDS/IPS/NDR** | Phát hiện bất thường trên đường có quan sát, một số lỗi policy | Không thấy plaintext khi traffic TLS và không có khả năng giải mã hợp pháp |
| **Segmentation/Zero Trust** | Hạn chế đường đi và quyền tới origin, backend, management | Không thay HSTS cho browser |
| **Certificate/key management** | Duy trì danh tính TLS đáng tin và giảm rủi ro khóa lộ | Không thay kiểm soát nội dung hoặc phản hồi HTTP |

### 19.1. Vùng không được quan sát

Khi traffic sử dụng TLS, cảm biến mạng thông thường có thể thấy **IP/port, TLS handshake metadata trong giới hạn**, nhưng không mặc nhiên thấy HTTP headers, cookie hoặc body. HSTS được phát trong response HTTPS và thường được **mã hóa trên đường truyền**; muốn kiểm tra header, dùng điểm termination đáng tin, log ứng dụng/proxy hoặc công cụ client có quyền.

Không coi "IDS không có alert" là bằng chứng server đang dùng TLS đúng phiên bản hoặc đã phát HSTS.

## 20. Kiểm tra HSTS bằng curl một cách an toàn

Các lệnh sau dùng để **đọc phản hồi HTTP**, chỉ thực hiện với hostname của tổ chức hoặc hệ thống có phép kiểm thử. Thay **portal.example.com** bằng tên được sở hữu khi vận hành.

~~~bash
# Kiểm tra header do HTTPS endpoint thực sự trả về
curl --head --silent --show-error https://portal.example.com/

# Kiểm tra phản hồi HTTPS tại một endpoint khác (ví dụ API hoặc trang lỗi)
curl --head --silent --show-error https://portal.example.com/health

# Kiểm tra HTTP redirect, CHỈ trên hostname được phép và không gửi credential
curl --head --silent --show-error http://portal.example.com/

# Theo dõi redirect với giới hạn số bước, không đưa token/cookie vào lệnh
curl --head --location --max-redirs 5 --silent --show-error \
  http://portal.example.com/
~~~

**Chú ý hai giới hạn quan trọng:**

1. **curl không đồng nghĩa browser**. Chỉ đọc được header không chứng minh mọi user agent đã ghi nhớ HSTS, có trong preload hay không. Hỗ trợ cache HSTS của curl phụ thuộc tính năng/phiên bản và cấu hình, không phải mặc định của mọi invocation.
2. HTTP request đầu tiên trong bài test vẫn là **HTTP thuần**; không gửi password, cookie, access token hoặc dữ liệu nhạy cảm trong phép thử redirect.

### 20.1. Những gì cần đối chiếu trong output

- Response HTTPS có **một policy HSTS hợp lệ** hay có nhiều header mâu thuẫn?
- **max-age** có phù hợp giai đoạn rollout?
- **includeSubDomains/preload** đã được owner phê duyệt chưa?
- Header có xuất hiện từ **CDN/WAF ở edge** và các status HTTPS không chỉ 200 không?
- HTTP response có chuyển tới **HTTPS đúng hostname/path**, không loop?
- Certificate/TLS có hợp lệ ở hostname đích thực mà client nhìn thấy không?

## 21. Kiểm tra phiên TLS và chứng chỉ bằng OpenSSL

Các ví dụ dùng **openssl s_client** để quan sát handshake trên endpoint đã được cho phép:

~~~bash
# Thực hiện handshake có SNI và yêu cầu kiểm tra hostname/chứng chỉ
openssl s_client -connect portal.example.com:443 \
  -servername portal.example.com \
  -verify_hostname portal.example.com \
  -verify_return_error </dev/null

# Kiểm tra TLS 1.2 có được hỗ trợ theo chính sách (nếu client OpenSSL hỗ trợ)
openssl s_client -connect portal.example.com:443 \
  -servername portal.example.com -tls1_2 \
  -verify_hostname portal.example.com \
  -verify_return_error </dev/null

# Kiểm tra TLS 1.3 có được hỗ trợ theo chính sách (nếu OpenSSL hỗ trợ)
openssl s_client -connect portal.example.com:443 \
  -servername portal.example.com -tls1_3 \
  -verify_hostname portal.example.com \
  -verify_return_error </dev/null
~~~

**Lưu ý vận hành:**

- Phiên bản OpenSSL và trust store tại client ảnh hưởng kết quả. Thiếu CA trong local trust store có thể gây lỗi **không phải do server**.
- **SNI và hostname verification** cần được chỉ định phù hợp để không thử nhầm virtual host.
- s_client là công cụ TLS, **không phải browser HSTS test**; thành công TLS không chứng minh HSTS đang được browser lưu.
- Thử TLS 1.0/1.1 khi có quyền và mục tiêu audit có thể thất bại **ngay tại client OpenSSL** do cấu hình local, nên một lần thất bại không đủ kết luận server đã chặn phiên bản đó.
- Nếu site có nhiều CDN edge/region, chỉ một điểm test không chứng minh cấu hình trên mọi edge là giống nhau.

### 21.1. Khi test server chỉ hỗ trợ TLS 1.2

Một TLS 1.3 handshake thất bại nhưng TLS 1.2 thành công **chưa đủ chứng minh attacker downgrade**: có thể listener chỉ hỗ trợ 1.2. Việc chấp nhận phiên bản nào là quyết định **security policy và yêu cầu tương thích**, cần kiểm tra log/định tuyến/cấu hình trên cả hai phía.

## 22. Kiểm tra HSTS từ trình duyệt và hệ điều hành

### 22.1. Browser đã biết HSTS hay chưa?

Hai trình duyệt, hoặc một trình duyệt thường và một profile mới, có thể hành xử khác nhau vì **HSTS cache, preload list, HTTPS-First mode, extension hoặc enterprise policy** khác nhau. Hãy phân biệt:

- **Response header có được phát đúng không?**
- **Browser có đang áp HSTS cho hostname đó không?**
- **Hostname có trong preload list của browser/version đang kiểm tra không?**
- **Client có dùng proxy/VPN/SSL inspection và trust store khác không?**

Không dùng chế độ tắt kiểm tra certificate để "kiểm thử HSTS". Nếu cần xác định browser gửi request HTTP hay tự upgrade, có thể xem **Network/DevTools** và log test với quyền phù hợp, nhưng UI/thuật ngữ có thể thay đổi theo phiên bản.

### 22.2. Windows PowerShell

~~~powershell
# Chỉ đọc header từ HTTPS endpoint nếu PowerShell/.NET hỗ trợ
$response = Invoke-WebRequest -Uri "https://portal.example.com/" -Method Head
$response.Headers["Strict-Transport-Security"]

# Kiểm tra hostname DNS đang được client phân giải
Resolve-DnsName portal.example.com
~~~

Một số server không chấp nhận **HEAD** hoặc trả policy khác trên HEAD so với GET. Khi đó dùng GET được phép, nhưng tránh in/log body có dữ liệu nhạy cảm. **PowerShell không đại diện cho chính sách HSTS của trình duyệt**, vì HTTP client library có hành vi riêng.

### 22.3. DNS, IPv4/IPv6 và SNI

Nếu hostname phân giải tới nhiều địa chỉ IPv4/IPv6, một số CDN edge hoặc listener có thể trả TLS/certificate/HSTS khác nhau. Đừng kết luận toàn hệ thống đạt yêu cầu chỉ từ một IP. Cần test qua **hostname thực có SNI**, từ nhiều region/network và theo các endpoint quan trọng.

## 23. Ma trận kiểm thử chống hạ cấp kết nối

Các phép thử nên áp dụng trên **môi trường sở hữu hoặc được cấp phép**, dùng URL không nhạy cảm và máy test. Phân biệt các test **thuộc website** với những thứ phụ thuộc state browser.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| **T-01** | HTTPS trang chính | Cert/hostname hợp lệ, HSTS header đúng policy |
| **T-02** | HTTP tới hostname chưa có HSTS trong browser test | Redirect đúng HTTPS, không truyền credential |
| **T-03** | Browser đã ghi nhớ HSTS truy cập HTTP URL | Nâng HTTPS trước network HTTP request tương ứng |
| **T-04** | HTTPS trả 301/302/308 hợp lệ | Header được phát nếu policy yêu cầu, không loop |
| **T-05** | HTTPS trả 401/404/5xx từ edge/origin | HSTS không biến mất ngoài dự kiến |
| **T-06** | Client mới chưa có dynamic HSTS | Biết giới hạn first-visit; kiểm tra preload nếu áp dụng |
| **T-07** | www, api, admin và hostname phụ | Mỗi hostname có TLS/cert và chính sách đúng scope |
| **T-08** | Parent domain includeSubDomains | Các subdomain và delegated host đều HTTPS-ready |
| **T-09** | Subdomain gửi max-age=0 khi parent includeSubDomains | Không nhầm rằng subdomain có thể vô hiệu hóa policy của cha |
| **T-10** | Chính sách max-age dài hoặc preload được cân nhắc | Có owner, inventory, rollback và chấp thuận rõ |
| **T-11** | HTTPS trên IPv4 và IPv6 | TLS/cert/headers đồng nhất ở các listener |
| **T-12** | CDN/WAF nhiều POP/region | Edge response đúng, không thiếu HSTS ở một vùng |
| **T-13** | Redirect đi qua proxy nhiều lớp | Không có loop, không tin X-Forwarded-Proto giả |
| **T-14** | Edge HTTPS → origin | Xác minh TLS và hostname giữa các hop theo policy |
| **T-15** | Direct-to-origin access | Firewall/identity chặn đường bypass được quy định |
| **T-16** | TLS 1.3 endpoint | Thương lượng đúng trên client/server hỗ trợ |
| **T-17** | TLS 1.2 endpoint | Chỉ hoạt động nếu policy cho phép; cipher an toàn |
| **T-18** | TLS 1.0/1.1 hoặc SSL cũ | Không được phục vụ theo policy hiện đại, có bằng chứng từ phía server/audit |
| **T-19** | Chứng chỉ sai/hết hạn trên lab hợp lệ | Browser HSTS từ chối, không cho fallback HTTP |
| **T-20** | Page HTTPS tải subresource HTTP | Được sửa/chặn/nâng cấp theo chính sách, không còn mixed content không an toàn |
| **T-21** | Cookie session | Secure, HttpOnly, SameSite theo app risk; không gửi qua HTTP thuần |
| **T-22** | API/SDK không phải browser | HTTPS/TLS enforced riêng, không giả định đọc HSTS |
| **T-23** | Wi-Fi captive portal và VPN private subdomain | Không phá TLS trust, trang vào mạng vận hành đúng |
| **T-24** | Cert renewal và rotation | Không mất khả dụng khi HSTS đang có hiệu lực |
| **T-25** | HSTS max-age=0 trong lab | Hiểu phạm vi dynamic removal; không nhầm với preload/parent |
| **T-26** | Quy tắc firewall/WAF/IDS sau thay đổi TLS | Dịch vụ hợp lệ còn hoạt động, log/visibility đúng mong đợi |
| **T-27** | HTTP/2, HTTP/3, WebSocket nếu sử dụng | Đường vận chuyển và HTTPS/WSS an toàn theo khả năng nền tảng |
| **T-28** | Rollback proxy/cert policy | Có bằng chứng recovery, không yêu cầu user bypass cert error |

### 23.1. Test deny và test allow

Chỉ nhìn thấy browser tự nâng lên HTTPS chưa đủ: cần chứng minh **HTTP không mang dữ liệu nhạy cảm, TLS version/cipher đáp ứng policy, chứng chỉ hợp lệ và service SLI còn tốt**. Ngược lại, một phép thử "HTTP không mở được" không tự chứng minh HSTS hoạt động: có thể do server đóng port 80, host offline hoặc route lỗi.

### 23.2. Giới hạn test với người dùng thật

Không sửa HSTS cache/profile thật của người dùng và không chủ động tạo certificate error trên production. Tạo **test hostname độc lập** và dùng thiết bị/profile thử nghiệm khi cần xác minh hành vi browser có HSTS/không có HSTS.

## 24. Giám sát, log và dấu hiệu bất thường

### 24.1. Nguồn telemetry

| Nguồn | Trường hữu ích | Dùng để trả lời |
|---|---|---|
| **CDN/WAF access logs** | hostname, TLS version, edge status, redirect, policy version | Edge có áp HTTPS/redirect/HSTS policy đúng không? |
| **Reverse proxy/load balancer** | listener, certificate, SNI, negotiated TLS, upstream | Có TLS mismatch/redirect loop tại một hop không? |
| **Origin server** | upstream connections, TLS validation failures, app status | Chặng proxy–origin có an toàn và khả dụng không? |
| **Certificate manager** | SAN, expiry, issuer, rotation, key ID | Có rủi ro cert hết hạn/không đúng host không? |
| **Browser/synthetic checks** | redirect, HSTS header, cert validity, handshake, SLI | Client nhìn thấy gì từ nhiều vị trí? |
| **DNS monitoring** | A/AAAA, CNAME, route tới edge, thay đổi record | Có hostname vô tình đi trực tiếp origin hoặc khác region? |
| **Firewall/VPN/IDS** | flow metadata, deny event, private endpoint reachability | Có đường bypass/đoạn mạng ngoài kiến trúc không? |
| **Change management** | HSTS max-age, policy diff, cert deploy, WAF version | Sự cố có trùng thời điểm deploy không? |

**HSTS header có thể không xuất hiện trong network-layer logs** do response đã được mã hóa. Hãy dùng **synthetic HTTPS fetch tại client hoặc log ngay điểm TLS termination** để đo header thực.

### 24.2. Các cảnh báo có ý nghĩa

- Một hostname public trả **HTTPS không có HSTS** dù policy yêu cầu.
- Một edge/region gửi **max-age=0**, mất **includeSubDomains** hoặc thêm preload trái change control.
- Tăng **certificate errors**, SAN mismatches, cert expiry gần, handshake failures.
- Tăng **redirect loop, 3xx chain**, HTTP endpoint nhận credential hoặc nhiều URL HTTP còn tồn tại.
- Phát hiện **TLS 1.0/1.1** hoặc cipher ngoài danh mục tại endpoint production.
- Chênh lệch TLS policy giữa **IPv4/IPv6, edge/origin, primary/backup listener**.
- Một backend chuyển sang HTTP thuần hoặc bỏ xác thực upstream certificate.
- Subdomain thuộc domain cha HSTS bị lỗi HTTPS sau khi thêm DNS record hoặc chuyển nhà cung cấp.

### 24.3. Chỉ số vận hành

- % hostname được bao phủ bởi HTTPS với cert hợp lệ.
- % hostname nhận HSTS header đúng max-age/scope theo policy.
- % subdomain đã được owner xác nhận HTTPS-ready trước includeSubDomains.
- Tỷ lệ TLS 1.3/TLS 1.2 và phiên bản ngoài policy theo điểm quan sát.
- Rate handshake/certificate errors; số ticket ảnh hưởng browser HSTS.
- Tỷ lệ HTTP → HTTPS redirect đúng và không có loop.
- Tình trạng giám sát expiry/renewal, latency, 5xx và DNS/edge health.

**Không dùng số HSTS headers trong log để kết luận browser nào đã ghi nhớ chính sách**. Browser state không có một nguồn telemetry tập trung đáng tin chỉ từ server.

## 25. Runbook triển khai HSTS và TLS hardening

### Bước 1 — Xác minh tài sản và owner

Liệt kê domain, subdomain, certificate, DNS, endpoint, CDN/WAF/NGINX, API clients, VPN private zones và application owners. Xác định **hostname nào có thể áp includeSubDomains** và hostname nào cần giữ chính sách riêng.

### Bước 2 — Cập nhật minimum TLS và certificate

Chuẩn hóa TLS 1.2/1.3 theo policy, loại phiên bản/cipher cũ, cấu hình SNI/certificate chain và tự động gia hạn. Nếu tổ chức dùng mTLS/private PKI cho origin, kiểm tra trust store và hostname verification từng hop.

### Bước 3 — Sửa toàn bộ URL HTTP nội bộ

Đổi internal links, API URLs, redirect endpoints, WebSocket URL, image/script CSS, OAuth callback và tài liệu thành HTTPS/WSS phù hợp. Thiết lập redirect từ HTTP cho đường legacy cần giữ nhưng không truyền secret qua HTTP.

### Bước 4 — Thử HSTS thời hạn ngắn

Phát HSTS trên HTTPS ở entrypoint, **max-age ngắn không includeSubDomains**. Kiểm tra browser và curl/openssl, cả response lỗi, proxy, IPv4/IPv6, CDN edge và client API.

### Bước 5 — Giám sát và tăng dần

Quan sát certificate failures, availability, redirect loops, mDNS/DNS không liên quan nếu có nhầm định tuyến, các báo cáo user với private subdomains hoặc captive portals. Tăng max-age theo change approval sau khi chứng minh ổn định.

### Bước 6 — includeSubDomains/preload nếu phù hợp

Chỉ tiến hành sau **inventory toàn namespace, xác nhận tất cả delegated/legacy hostname và cam kết HTTPS lâu dài**. Nếu preload, áp quy trình đăng ký và hiểu thời gian gỡ phụ thuộc browser updates.

### Bước 7 — Regression và bảo trì

Sau thay đổi **certificate, CDN/WAF, reverse proxy, DNS, TLS minimum version, cloud load balancer, VPN/private DNS hoặc server migration**, chạy lại ma trận kiểm thử. Không coi HSTS là dự án cấu hình một lần.

~~~mermaid
flowchart TD
    A[Inventory DNS/TLS/hostname] --> B[HTTPS + cert + modern TLS]
    B --> C[Fix HTTP URLs + redirects]
    C --> D[HSTS max-age ngắn]
    D --> E[Browser + edge + origin + IPv6 tests]
    E --> F{Cert và dịch vụ ổn định?}
    F -- Không --> G[Fix TLS/header/route; rollback có kế hoạch]
    G --> D
    F -- Có --> H[Tăng max-age theo change control]
    H --> I{Subdomains đạt yêu cầu?}
    I -- Không --> J[Giữ policy ở hostname phù hợp]
    I -- Có --> K[Cân nhắc includeSubDomains/preload]
    K --> L[Giám sát và regression dài hạn]
    J --> L
~~~

## 26. Runbook sự cố khi HSTS làm ứng dụng không truy cập được

### Tình huống khởi đầu

Người dùng báo **admin.example.com** đột ngột không truy cập được, browser hiển thị lỗi chứng chỉ và không cho tiếp tục. Gần thời điểm đó, nhóm web đã bật **includeSubDomains** trên **example.com**.

### Giai đoạn 1 — Khoanh vùng và xác nhận

1. Ghi hostname, browser/version, DNS view (public/private/VPN), thời điểm và thông báo TLS.
2. Xác minh **domain cha có HSTS includeSubDomains/preload** hay không.
3. Kiểm tra endpoint đó có **HTTPS, certificate đúng SAN, chain/trust store và TLS version** hợp lệ không.
4. So response từ **CDN và private VPN path**, IPv4/IPv6, đường redirect và SNI.
5. Kiểm tra những subdomain khác dùng cùng parent policy có bị ảnh hưởng không.

### Giai đoạn 2 — Giữ bằng chứng

Lưu **policy version, change ticket, chứng chỉ, listener/proxy configuration, HTTP/TLS headers đã được phép**, các lỗi handshake và trạng thái DNS. Không yêu cầu người dùng gửi cookie, password hoặc private key.

### Giai đoạn 3 — Khôi phục an toàn

- **Ưu tiên sửa HTTPS/certificate tại subdomain** để browser HSTS truy cập được.
- Nếu header của cha mới được phát nhầm và **chưa preload**, cần đánh giá thay đổi parent policy theo kế hoạch; nhưng **xóa header không làm browser đã lưu state ngừng áp ngay**.
- Nếu domain đã preload, phối hợp với owner và chương trình preload để xin gỡ khi cần; **không hứa có hiệu lực ngay**.
- Nếu ảnh hưởng một ứng dụng nội bộ, đảm bảo private PKI/trust store được quản lý đúng trên thiết bị công ty; không bảo người dùng bỏ qua lỗi chứng chỉ.
- Kiểm tra CDN/edge và proxy không đang trả certificate khác theo SNI hoặc location.

### Giai đoạn 4 — Xác minh và hậu kiểm

Thử trên **browser profile mới và profile đã từng biết HSTS**, qua VPN và Internet, cả IPv4/IPv6. Kiểm tra user-facing SLI, certificate renewal, login/API và các lỗi 3xx/4xx/5xx. Bổ sung bước review **subdomain owners và trạng thái TLS** trước lần bật includeSubDomains tiếp theo.

## 27. Các tình huống phân tích chuyên sâu

### Tình huống A — Web có HTTPS và 301 nhưng vẫn có first-visit risk

**Dữ kiện:** người dùng gõ http://portal.example.com từ browser chưa biết HSTS. Server redirect tới HTTPS và phát HSTS trên response HTTPS.

**Phân tích:** sau HTTPS response hợp lệ, browser đã được bảo vệ tốt hơn ở những lần sau. Tuy nhiên request HTTP đầu tiên chưa được bảo vệ bằng TLS. **Preload hoặc chính sách HTTPS-first của user agent** có thể giảm rủi ro lần đầu khi được áp dụng; không gọi một cấu hình "HSTS header trên HTTP" là giải pháp.

### Tình huống B — HSTS có nhưng trình duyệt vẫn báo mất an toàn

**Dữ kiện:** header HSTS có ở website HTTPS, nhưng browser hiển thị certificate mismatch.

**Phân tích:** HSTS không làm chứng chỉ sai trở thành đúng. Ngược lại, browser HSTS cần từ chối và không cho fallback HTTP. Sửa **SNI, SAN, chain, DNS hoặc certificate deployment**, không tắt HSTS/TLS validation để che nguyên nhân.

### Tình huống C — CDN có HTTPS nhưng origin không được mã hóa

**Dữ kiện:** browser thấy HTTPS và HSTS đúng; CDN proxy tới origin bằng HTTP qua mạng mà đội bảo mật không chấp nhận plaintext.

**Phân tích:** bảo vệ Browser → CDN không đồng nghĩa bảo vệ CDN → Origin. Cần **TLS cho origin hop, certificate validation, giới hạn direct-origin access**, rồi kiểm tra log và SLI sau khi bật.

### Tình huống D — Một host phát HSTS, host khác không

**Dữ kiện:** www.example.com có HSTS nhưng api.example.com không có; apex chưa bật includeSubDomains.

**Phân tích:** browser đã học HSTS của www **không mặc nhiên áp** lên api. Cần audit từng hostname hoặc triển khai parent policy sau khi namespace đã sẵn sàng; với API SDK không hỗ trợ HSTS, cần enforcement HTTPS độc lập.

### Tình huống E — "preload" xuất hiện trong header nhưng browser mới vẫn gửi HTTP

**Dữ kiện:** server gửi max-age dài; includeSubDomains; preload, nhưng trình duyệt mới ở phiên bản nhất định vẫn chưa có trạng thái HSTS cho tên đó.

**Phân tích:** header không đồng nghĩa đã được **đưa vào và phân phối** trong preload list. Kiểm tra trạng thái tại chương trình và browser/version; không dựa vào header để khẳng định đã bảo vệ first visit.

### Tình huống F — Bật includeSubDomains làm hỏng hệ thống nội bộ qua VPN

**Dữ kiện:** thiết bị quản trị chỉ hỗ trợ http://router.mgmt.example.com, trong khi example.com bật HSTS includeSubDomains.

**Phân tích:** browser biết parent HSTS sẽ nâng URL lên HTTPS. Khắc phục cần **triển khai HTTPS với certificate/trust hợp lệ hoặc đổi kiến trúc hostname** theo owner, không nên yêu cầu user tắt browser security.

### Tình huống G — TLS 1.3 test lỗi, TLS 1.2 test thành công

**Dữ kiện:** OpenSSL client TLS 1.3 không kết nối, TLS 1.2 kết nối.

**Phân tích:** có thể do listener chỉ hỗ trợ 1.2 hoặc TLS 1.3 bị middlebox/proxy xử lý khác; không tự kết luận có protocol downgrade attack. Xem server config, handshake logs, client version, SNI và route để phân loại.

### Tình huống H — HTTPS đã bật nhưng một script vẫn tải HTTP

**Dữ kiện:** website HTTPS bị browser chặn một script HTTP từ third-party host.

**Phân tích:** HSTS của trang chính không bảo vệ mọi third-party hostname. Sửa dependency sang HTTPS, đánh giá CSP, SRI hoặc loại script không tin cậy; không chuyển cả trang về HTTP để chạy script.

### Tình huống I — Reverse proxy tạo redirect loop sau khi bật HTTPS-only

**Dữ kiện:** CDN chuyển HTTPS tới proxy bằng HTTP, app nhìn scheme là HTTP rồi redirect mãi.

**Phân tích:** lỗi **scheme detection/trusted headers/hop TLS**, không phải lỗi max-age. Sửa proxy configuration và kiểm chứng từ browser thực; đừng tạm cho phép credential qua HTTP để tránh loop.

### Tình huống J — Cert gia hạn ở một edge nhưng edge khác vẫn dùng cert cũ

**Dữ kiện:** người dùng một region truy cập được, region khác nhận lỗi cert trên domain HSTS.

**Phân tích:** certificate deployment không đồng nhất giữa POP/region hoặc IPv4/IPv6 listener. Cần audit từng endpoint và quy trình rollout certificate, không kết luận từ một lệnh curl tại văn phòng.

## 28. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| **"Có HTTPS là hết SSL stripping."** | Người dùng có thể bắt đầu ở HTTP; cần HSTS/HTTPS-first/preload phù hợp. |
| **"301 redirect an toàn như HSTS."** | HTTP redirect đầu tiên có thể bị can thiệp; HSTS được browser ghi nhớ từ HTTPS. |
| **"HSTS trên HTTP response vẫn được nhận."** | User agent tuân thủ không nhận HSTS từ HTTP không an toàn. |
| **"HSTS bảo vệ ngay lần đầu ở mọi browser."** | Dynamic HSTS có first-visit gap; preload phụ thuộc browser/program. |
| **"Có chữ preload là đã được preload."** | Cần chương trình chấp nhận và phân phối đến browser. |
| **"includeSubDomains chỉ áp cho www."** | Áp cho mọi cấp subdomain trong phạm vi parent, kể cả delegated/legacy names. |
| **"Subdomain max-age=0 có thể tắt HSTS của parent."** | Không thể vô hiệu hóa chính sách includeSubDomains còn hiệu lực từ cha. |
| **"Bỏ header HSTS là mọi browser quên ngay."** | Browser giữ state tới expiry hoặc nhận xóa hợp lệ; preload còn riêng. |
| **"HSTS giúp bypass lỗi certificate để website chạy."** | HSTS khiến user agent nghiêm ngặt hơn với certificate errors. |
| **"HSTS bắt buộc TLS 1.3."** | HSTS chỉ ép dùng HTTPS; TLS version do negotiation/config quyết định. |
| **"TLS 1.2 luôn là dấu hiệu downgrade attack."** | Có thể là phiên bản mạnh nhất hai bên cùng hỗ trợ theo policy. |
| **"TLS_FALLBACK_SCSV thay việc tắt TLS cũ."** | Nó hỗ trợ phát hiện fallback không phù hợp, không thay min version. |
| **"CDN có HTTPS tức origin cũng mã hóa."** | TLS có thể chỉ đến edge; phải kiểm tra edge–origin. |
| **"WAF/IDS nhìn thấy header HSTS trong mọi flow."** | TLS che HTTP header trên đường không giải mã; cần kiểm tra tại termination/client. |
| **"HSTS thay DNSSEC hoặc TLS certificate validation."** | Các cơ chế xử lý những ranh giới tin cậy khác nhau. |
| **"Cookie Secure/HttpOnly/SameSite không còn cần."** | HSTS không thay an ninh cookie/session. |
| **"Một IP/curl result chứng minh mọi CDN region chuẩn."** | Cần nhiều endpoint, IPv4/IPv6, browser và policy version. |
| **"Chỉ kiểm tra response 200 là đủ."** | Redirect, 401/404/5xx có thể khác header tại edge/proxy. |
| **"Vẫn dùng HTTP cho private host dưới parent preload được."** | Browser HSTS của parent có thể buộc HTTPS cho cả host nội bộ. |

## 29. Checklist HSTS và chống hạ cấp kết nối

- [ ] Có inventory hostname public/private, subdomain, delegated zone, owner và data path.
- [ ] Mọi ứng dụng quan trọng có **HTTPS/TLS certificate hợp lệ** đúng SAN/hostname và chain.
- [ ] TLS minimum version/cipher phù hợp policy hiện đại; không để SSL/TLS cũ hoạt động ngoài ngoại lệ được phê duyệt.
- [ ] HTTP endpoint chỉ phục vụ redirect tối thiểu khi cần; không nhận credential/session qua HTTP.
- [ ] HSTS được phát **trên HTTPS hợp lệ**, không dựa vào header ở HTTP.
- [ ] Header max-age đúng giai đoạn rollout, chỉ có một policy cuối nhất quán.
- [ ] Phát HSTS trên các response HTTPS quan trọng gồm trang lỗi/redirect theo policy.
- [ ] Đã test hostname riêng trước khi bật **includeSubDomains** ở parent.
- [ ] Mọi subdomain, hostname delegated, legacy và private VPN đã có HTTPS được quản trị.
- [ ] Cân nhắc preload theo điều kiện chương trình và năng lực vận hành **lâu dài**, không thử tùy tiện.
- [ ] Hiểu max-age=0 không xóa HSTS của parent và preload không gỡ tức thì.
- [ ] Có certificate renewal, expiry alert, key protection và kế hoạch CA incident.
- [ ] Đã kiểm tra SSL/TLS đúng ở CDN/WAF, load balancer, reverse proxy và origin.
- [ ] Edge → origin dùng bảo vệ TLS/identity phù hợp threat model, không để direct-origin bypass.
- [ ] Scheme detection/trusted headers chính xác, không loop vì X-Forwarded-Proto giả hoặc sai.
- [ ] Cookies nhạy cảm có Secure/HttpOnly/SameSite theo application risk.
- [ ] HTML/API/WebSocket/subresource URL dùng HTTPS/WSS; mixed content/CSP được kiểm thử.
- [ ] Có bài test TLS 1.2/1.3, SNI, ALPN và version/cipher không được phép theo quy trình.
- [ ] Có kiểm thử cả IPv4 và IPv6, CDN POP/region, primary/backup listener.
- [ ] Kiểm tra browser đã/ chưa biết HSTS và client không phải browser; không suy từ curl rằng browser đã ghi nhớ.
- [ ] DNS, split DNS, captive portal và private PKI/VPN không bị phá khi bật HSTS.
- [ ] Có ma trận test cho HTTPS 200, redirect, 401/404/5xx, certificate errors và cert rotation.
- [ ] SOC/SRE có telemetry cho TLS version, cert mismatch, redirect loop và policy drift.
- [ ] HSTS/certificate/configuration changes có owner, approval, canary, rollback và hậu kiểm.
- [ ] Không hướng dẫn người dùng bỏ qua certificate errors hoặc tắt HSTS như cách sửa sự cố.

## 30. Câu hỏi tự kiểm tra

**1. HSTS khác HTTP redirect ở đâu?**  
Redirect do server trả sau khi client gửi request; nếu request đầu là HTTP thì có khoảng không được bảo vệ. HSTS đã được browser ghi nhớ sẽ nâng URL HTTP lên HTTPS trước khi gửi network request.

**2. Vì sao chỉ bật HSTS sau response HTTPS không giải quyết hoàn toàn first visit?**  
Trình duyệt chưa có state HSTS có thể gửi HTTP trước khi tới trang HTTPS mang header. Preload hoặc cơ chế HTTPS-first phía browser có thể giảm khoảng trống này khi được hỗ trợ.

**3. max-age=31536000 có ý nghĩa gì?**  
Thời gian ghi nhớ HSTS khoảng một năm kể từ lần nhận header HTTPS hợp lệ, không phải DNS TTL hay certificate validity.

**4. includeSubDomains có thể làm hỏng ứng dụng nào?**  
Mọi subdomain thuộc parent, đặc biệt hệ thống legacy/private VPN chưa hỗ trợ HTTPS/chứng chỉ hợp lệ hoặc được vận hành bởi bên khác.

**5. Chỉ thêm chữ preload vào header có đủ để browser mới biết trước domain không?**  
Không. Phải được chương trình preload chấp nhận và phân phối vào browser tương ứng.

**6. Subdomain gửi max-age=0 có thể vô hiệu hóa HSTS từ parent includeSubDomains không?**  
Không. Nó không thể ghi đè chính sách cha còn hiệu lực; cũng không lập tức loại bỏ hostname khỏi preload tích hợp.

**7. HSTS có ngăn mọi kiểu downgrade TLS không?**  
Không. HSTS ngăn HTTP downgrade cho host trong phạm vi; TLS version downgrade được xử lý bằng negotiation, minimum versions và cơ chế protocol như TLS_FALLBACK_SCSV/TLS 1.3.

**8. TLS 1.2 được thương lượng có nhất thiết là đang bị tấn công?**  
Không. Nếu server chỉ hỗ trợ TLS 1.2, đó có thể là kết quả hợp lệ theo cấu hình. Cần xét policy, khả năng hai phía và bằng chứng can thiệp.

**9. Browser có HSTS nhưng chứng chỉ hết hạn sẽ làm gì?**  
Từ chối kết nối không an toàn, không fallback về HTTP hoặc cho phép bỏ qua tùy ý theo cách làm yếu chính sách HSTS.

**10. Vì sao HSTS tại CDN không chứng minh origin hop an toàn?**  
Browser kết nối TLS tới CDN, còn CDN tới origin có thể là một kết nối khác. Phải xác thực/mã hóa từng hop theo trust boundary.

**11. Vì sao curl -I https://host không chứng minh browser đã nhớ HSTS?**  
curl chỉ thấy response header của request đó; browser cache/preload state và hành vi của curl là hai vấn đề khác.

**12. Nếu trang HTTPS gọi script HTTP từ domain khác, HSTS của trang chính có sửa được không?**  
Không tự động. Cần thay URL script bằng HTTPS và áp CSP/mixed-content policy phù hợp cho hostname đó.

**13. Có nên dùng HTTP 301 redirect cho API gửi password trong body không?**  
Không nên để credential được gửi qua HTTP rồi đợi redirect. Client phải gọi HTTPS ngay từ đầu; redirect không che dữ liệu đã gửi ở request HTTP đầu.

**14. Khi bật HSTS có lỗi redirect loop, nên kiểm tra lớp nào?**  
Kiểm tra TLS termination, trusted proxy headers, scheme detection, redirect logic ở CDN/load balancer/origin và path qua từng hop, không chỉ thay max-age.

**15. Vì sao không nên bật includeSubDomains và preload cho toàn domain ngay ngày đầu?**  
Vì mọi subdomain và delegated hostname phải sẵn sàng HTTPS, các lỗi chứng chỉ có thể gây outage diện rộng; preload còn khó gỡ tức thì.

## 31. Tài liệu tham khảo

- [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797): định nghĩa chính sách HSTS, max-age, includeSubDomains và hành vi user agent.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3, negotiation và cơ chế chống downgrade.
- [RFC 7507 — TLS Fallback Signaling Cipher Suite Value (SCSV)](https://www.rfc-editor.org/rfc/rfc7507): hỗ trợ nhận biết fallback xuống phiên bản TLS thấp hơn không phù hợp.
- [RFC 8996 — Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996): trạng thái các phiên bản TLS cũ.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics HTTP, redirect và các mã trạng thái.
- [RFC 6066 — Transport Layer Security (TLS) Extensions](https://www.rfc-editor.org/rfc/rfc6066): SNI và các TLS extensions liên quan.
- [RFC 7301 — TLS Application-Layer Protocol Negotiation Extension](https://www.rfc-editor.org/rfc/rfc7301): ALPN.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookie và thuộc tính Secure/HttpOnly theo nền tảng HTTP state.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security): giải thích header và cân nhắc triển khai HSTS trong browser.
- [HSTS Preload List Submission](https://hstspreload.org/): thông tin/điều kiện chương trình preload, cần kiểm tra yêu cầu hiện hành.
- [NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of TLS Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final): lựa chọn phiên bản và cấu hình TLS an toàn.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): thực hành TLS, HTTPS và lựa chọn bảo vệ kênh truyền.

**Ghi nhớ:** HSTS giúp **user agent đã biết chính sách** không hạ truy cập từ HTTPS xuống HTTP, đồng thời bắt buộc nghiêm túc với lỗi chứng chỉ của hostname thuộc phạm vi. Để bảo vệ thật sự cần kết hợp **HTTPS-first, HSTS động/preload được triển khai có kiểm soát, TLS 1.2/1.3 với certificate validation, cấu hình đúng ở CDN/WAF/reverse proxy/origin, quản trị subdomain và giám sát**. Đừng nhầm **redirect với HSTS**, **HSTS với TLS protocol downgrade protection**, hay **HTTPS tại edge với mã hóa toàn bộ đường truyền**.
