# DoH và DoT: mã hóa truy vấn DNS và thiết kế bảo mật phân giải tên

**DNS over HTTPS (DoH)** và **DNS over TLS (DoT)** là hai cơ chế chuyển truy vấn DNS qua một kênh được bảo vệ bằng TLS. Chúng giúp hạn chế người quan sát trên đường truyền giữa **DNS client** và **DNS resolver được chọn** đọc hoặc sửa nội dung truy vấn và phản hồi DNS. Cả hai đều nhằm khắc phục một điểm yếu của DNS truyền thống: nhiều truy vấn DNS trước đây được gửi không mã hóa, dễ bị quan sát hoặc can thiệp tại một số điểm mạng.

Trong chương **DNS security** của học phần **SECURITY_NETWORK_SECURITY**, DoH và DoT cần được hiểu trong bức tranh rộng hơn: phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ Wi-Fi và dịch vụ cloud. **Mã hóa DNS không đồng nghĩa DNS hoàn toàn riêng tư, không chứng minh bản ghi là đúng và không tự bảo vệ endpoint hay mạng trước mọi cuộc tấn công.**

Bài học này giải thích giao thức, mô hình tin cậy, điểm mạnh và giới hạn, cách triển khai resolver cho mạng doanh nghiệp, vấn đề split DNS/VPN, giám sát an toàn, kiểm thử và cách xử lý các tình huống vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả hành trình DNS từ ứng dụng, stub resolver đến recursive resolver và authoritative DNS.
2. Giải thích vì sao DNS plaintext có thể gây lộ thông tin hoặc bị sửa đổi trên đường truyền.
3. So sánh DoT với DoH về lớp giao thức, cổng, định danh resolver, khả năng quan sát và quản trị.
4. Phân biệt **bảo mật kênh DNS bằng TLS** với **xác thực dữ liệu DNS bằng DNSSEC**.
5. Xác định các giới hạn riêng tư: resolver vẫn nhìn thấy truy vấn, metadata mạng vẫn lộ ở mức nhất định.
6. Thiết kế chính sách DNS cho máy trạm, trình duyệt, VPN, mạng khách, cloud và hệ thống nội bộ.
7. Xác minh cấu hình mã hóa DNS bằng bằng chứng từ endpoint, resolver và mạng, không chỉ qua một phép thử cổng.
8. Lập kế hoạch xử lý lỗi, giám sát và ngăn truy vấn DNS đi ra ngoài các resolver được quản lý.

## 2. DNS truyền thống hoạt động như thế nào?

Khi một ứng dụng cần kết nối tới tên miền, nó thường yêu cầu hệ điều hành hoặc bộ thư viện DNS tìm địa chỉ hoặc bản ghi tương ứng. Trong mô hình phổ biến:

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant S as Stub resolver của máy
    participant R as Recursive resolver
    participant Z as Authoritative DNS
    A->>S: Cần địa chỉ của app.example
    S->>R: Truy vấn DNS
    alt Chưa có kết quả trong cache
        R->>Z: Hỏi thông tin cần thiết
        Z-->>R: Bản ghi và dữ liệu liên quan
    end
    R-->>S: Phản hồi DNS
    S-->>A: Kết quả phân giải
~~~

**Stub resolver** là thành phần ở máy khách hoặc ứng dụng tạo yêu cầu. **Recursive resolver** chịu trách nhiệm trả lời bằng cache hoặc tra cứu tiếp các máy chủ DNS khác. **Authoritative DNS** cung cấp dữ liệu có thẩm quyền cho vùng tên miền tương ứng.

Đường phân giải thực có thể phức tạp hơn sơ đồ, bao gồm cache của trình duyệt, hệ điều hành, proxy, recursive forwarder, DNS64 hoặc các cơ chế điều phối nội bộ.

### 2.1. DNS truyền thống và lớp vận chuyển

DNS thường dùng **UDP/53** và cũng dùng **TCP/53**. TCP có thể cần cho những phản hồi hoặc tình huống DNS cụ thể; không nên coi DNS chỉ sử dụng UDP. Các cơ chế DNS qua HTTPS/TLS được thiết kế để sử dụng kênh bảo mật riêng, không đồng nghĩa tắt mọi nhu cầu DNS trên UDP/TCP 53 trong hạ tầng.

Ví dụ khi client ở mạng Wi-Fi công cộng gửi DNS plaintext tới resolver:

~~~text
Client --(DNS UDP/53 không mã hóa)--> Resolver
                ^
                |
       Điểm quan sát trên đường đi
~~~

Người có vị trí quan sát thích hợp có thể thấy những thông tin như **tên miền hỏi, loại bản ghi, địa chỉ resolver, thời điểm** và có thể ảnh hưởng gói nếu họ kiểm soát phần đường truyền. Tuy nhiên không nên tự giả định mọi thiết bị cùng Wi-Fi đều nhìn thấy toàn bộ lưu lượng unicast của nhau; isolation, switching và bảo vệ liên kết quyết định phạm vi thực tế.

### 2.2. DNS không phải nội dung HTTP

Khi người dùng mở một website HTTPS, DNS có thể phân giải tên miền trước khi thiết lập kết nối, nhưng nội dung truy vấn DNS và nội dung HTTP của website là hai luồng khác nhau. **HTTPS bảo vệ HTTP** tại phiên TLS ứng dụng; nó không mặc nhiên mã hóa DNS của hệ điều hành nếu DNS đang đi dưới dạng plaintext.

DoH hoặc DoT bảo vệ **kết nối client → resolver**. Chúng không tự mã hóa HTTP của website, không thay thế TLS cho ứng dụng và không bảo đảm website đích là hợp pháp.

## 3. Động cơ dùng DNS mã hóa

DNS plaintext tạo nhiều vấn đề trong một số mô hình đe dọa:

- **Lộ lịch sử phân giải tên:** điểm quan sát có thể biết một phần tên miền mà client truy vấn.
- **Sửa đổi hoặc giả mạo phản hồi trên đường không được bảo vệ:** người có khả năng tác động tới lưu lượng có thể cố chuyển hướng kết quả.
- **Chèn chính sách không minh bạch hoặc phát hiện sai:** một số mạng trung gian có thể trả kết quả khác so với resolver mong đợi.
- **Khó bảo đảm tính toàn vẹn đường truyền:** client không có bằng chứng mật mã rằng nội dung trả về từ resolver định dùng đã nguyên vẹn.

DoH và DoT giới hạn những năng lực đó **trên chặng TLS được thiết lập và xác thực đúng**. Chúng không bảo vệ nội dung khi chính resolver đã bị chiếm quyền hoặc khi ứng dụng/endpoint bị kiểm soát.

### 3.1. Cụ thể bảo vệ những thuộc tính nào?

| Thuộc tính | DNS plaintext không có bảo vệ kênh | DoH/DoT được cấu hình và xác thực đúng |
|---|---|---|
| Bí mật tên miền trong payload trên chặng client–resolver | Có thể bị đọc tại điểm quan sát phù hợp | Được mã hóa trong phiên TLS |
| Toàn vẹn DNS message trên chặng đó | Có thể bị sửa nếu đối thủ kiểm soát đường đi | TLS bảo vệ tính toàn vẹn phiên |
| Xác thực danh tính resolver | Thường không có xác thực mật mã ở lớp truyền DNS truyền thống | Có thể xác thực resolver theo tên/chứng chỉ và chính sách client |
| Chống chặn hoặc làm mất kết nối | Không | Không; TLS không bảo đảm availability |
| Resolver có thấy truy vấn không? | Có | **Có**: resolver là đầu kết thúc TLS |
| Authoritative DNS có thấy truy vấn từ recursive resolver không? | Tùy quá trình truy vấn | Vẫn có thể thấy một phần tùy cấu hình recursive resolver |
| Dữ liệu DNS có đúng theo DNSSEC không? | Không tự có | Không tự có; cần xác thực DNSSEC riêng nếu muốn |

**Nguyên tắc:** TLS bảo vệ một **kênh tới resolver được xác thực**, còn việc resolver trả câu trả lời nào là vấn đề **tin cậy và xác minh dữ liệu DNS**.

## 4. DoT (DNS over TLS) là gì?

**DNS over TLS** vận chuyển thông điệp DNS qua một kết nối TLS, phổ biến trên **TCP/853**. Giao thức được chuẩn hóa, với nền tảng trong **RFC 7858** và các hồ sơ sử dụng quyền riêng tư trong **RFC 8310**.

~~~text
Ứng dụng
   |
Stub / system DNS resolver
   |
TCP + TLS tới resolver được cấu hình
   |       thường TCP/853
   v
DoT resolver
   |
Recursive cache / DNS infrastructure
~~~

DoT bảo vệ nội dung DNS query/response **trong phiên TLS từ client tới DoT resolver**. Resolver có thể tiếp tục truy vấn authoritative DNS theo các cơ chế khác; không được giả định toàn bộ hành trình tới authoritative DNS đã được mã hóa chỉ vì client dùng DoT.

### 4.1. DoT dùng TLS và kết nối TCP như thế nào?

Ở mức khái niệm:

1. Client biết hoặc khám phá endpoint DoT theo cơ chế được quản trị.
2. Client thiết lập kết nối TCP tới resolver, thường trên port 853.
3. Client và resolver thực hiện TLS handshake.
4. Client kiểm tra danh tính resolver theo chính sách xác thực.
5. Truy vấn và phản hồi DNS được gửi dưới dạng các message DNS bên trong kết nối TLS.

Trong DoT, thông điệp DNS được đóng khung theo cách phù hợp với DNS trên luồng TCP, gồm phần chiều dài thông điệp, thay vì dùng HTTP request/response. Một kết nối TLS có thể được tái sử dụng cho nhiều truy vấn; điều này giúp giảm chi phí handshake khi có nhiều yêu cầu.

### 4.2. Strict Privacy và Opportunistic Privacy

Hai mô hình quan trọng khi dùng DoT:

- **Strict Privacy Profile:** client yêu cầu resolver được xác thực đúng theo cấu hình/tên hoặc cơ chế pinning được chấp nhận và bảo đảm kênh TLS thích hợp. Nếu không đạt yêu cầu, client phải xử lý như lỗi kết nối bảo mật theo chính sách, thay vì âm thầm chuyển sang plaintext.
- **Opportunistic Privacy Profile:** client cố dùng bảo vệ kênh khi khả thi nhưng có thể chấp nhận các điều kiện yếu hơn về xác thực hoặc chuyển về đường không mã hóa theo thiết kế. Vì vậy không nên tuyên bố mức bảo vệ giống strict mode.

Khi quản trị doanh nghiệp, phải quy định rõ **fail closed, fail open hay fallback có điều kiện**. Cho phép chuyển về DNS không mã hóa sau một lỗi TLS có thể tạo cơ hội **downgrade** nếu mạng không tin cậy chủ động ngăn kết nối 853.

### 4.3. Cổng 853 không tự chứng minh đã có DoT an toàn

Quan sát kết nối **TCP/853** chỉ gợi ý khả năng DoT, không chứng minh:

- Client đã kiểm tra đúng chứng chỉ resolver.
- DNS message thật sự được truyền thành công.
- Resolver là thành phần được doanh nghiệp phê duyệt.
- Toàn bộ ứng dụng trên máy đều dùng DoT.
- Không có truy vấn plaintext song song hoặc fallback.

Cần kiểm tra cấu hình resolver, trạng thái TLS, log endpoint và log resolver, không chỉ nhìn firewall allow TCP/853.

## 5. DoH (DNS over HTTPS) là gì?

**DNS over HTTPS** vận chuyển các DNS message thông qua giao thức HTTPS, được chuẩn hóa trong **RFC 8484**. DoH thường đi qua **HTTPS trên TCP/443**, và có thể dùng HTTP/3 qua QUIC trên **UDP/443** nếu cả client và server hỗ trợ.

~~~text
Browser / application / OS DNS client
                  |
                  v
             HTTPS request
       thường /dns-query (tùy endpoint)
                  |
                  v
               DoH server
                  |
             DNS resolver
~~~

Khác với DoT vận chuyển DNS trực tiếp trên TLS, DoH sử dụng **HTTP request/response** làm lớp ứng dụng. Trong RFC 8484, dạng biểu diễn chuẩn thường dùng media type **application/dns-message**, chứa thông điệp DNS ở dạng wire format.

### 5.1. Các phương thức DoH phổ biến

- **HTTP POST:** gửi DNS message nhị phân trong request body, media type application/dns-message.
- **HTTP GET:** mã hóa DNS message vào tham số **dns** dạng base64url không padding trên URI của endpoint.

Cả GET và POST đều được truyền bên trong phiên HTTPS khi sử dụng DoH chuẩn. Không nên kết luận GET luôn làm lộ tên miền cho người quan sát mạng: nội dung URI/path/query được TLS bảo vệ trong phiên HTTPS chuẩn. Tuy nhiên **DoH server, điểm TLS termination và hệ thống ghi access logs của nó** có thể thấy URI hoặc body, nên cần thiết kế quyền riêng tư và caching cẩn thận.

### 5.2. Đường dẫn endpoint không phải lúc nào cũng cố định

Đường dẫn **/dns-query** thường gặp nhưng không phải mọi triển khai đều buộc dùng đúng URI này. Client cần endpoint/URI template được cấu hình hoặc khám phá phù hợp.

Các proxy, CDN hoặc load balancer có thể đứng trước DoH server. Nếu HTTPS kết thúc tại một proxy, **proxy có thể đọc DNS message sau giải mã**. Vì thế phải biết ai là điểm kết thúc TLS thật và bên nào được tin cậy xử lý dữ liệu.

### 5.3. Vì sao DoH khó phân biệt với HTTPS khác?

DoH có thể đi qua cùng port **443** mà nhiều website và API hợp lệ sử dụng. Firewall chỉ match IP/port có thể không phân biệt được một kết nối là truy vấn DoH hay truy cập website thông thường, nhất là khi có TLS, HTTP/2/HTTP/3 hoặc hạ tầng CDN chia sẻ IP.

Đây là lợi ích về khả năng đi qua các mạng cho phép HTTPS, nhưng cũng tạo thách thức quản trị: **chặn port 53 hoặc 853 không đồng nghĩa đã buộc mọi ứng dụng dùng DNS resolver nội bộ**, vì một số ứng dụng có thể dùng DoH trên 443 tới resolver ngoài.

## 6. So sánh DoH, DoT và DNS truyền thống

| Tiêu chí | DNS truyền thống | DoT | DoH |
|---|---|---|---|
| Mô hình lớp vận chuyển | UDP/TCP | DNS trong TLS qua TCP | DNS trong HTTPS |
| Port thường dùng | UDP/53 và TCP/53 | TCP/853 | HTTPS TCP/443, có thể HTTP/3 qua UDP/443 |
| Bảo vệ payload client–resolver | Không có mã hóa kênh mặc định | TLS | TLS qua HTTPS |
| Xác thực resolver bằng TLS | Không | Có khi client kiểm tra theo chính sách | Có khi HTTPS client kiểm tra đúng endpoint |
| Quan sát bằng firewall chỉ dựa trên port | Có thể nhận ra DNS/53 | Thường dễ nhận ra DoT/853 | Khó phân biệt với HTTPS khác/443 |
| Phổ biến ở đâu | Hạ tầng DNS hiện hữu, mạng LAN | OS/router/forwarder/resolver được cấu hình DoT | Browser, OS, app, API client, DoH gateway |
| Cần HTTP stack | Không | Không | Có |
| Có thể tích hợp proxy/CDN HTTP | Không trực tiếp | Không theo lớp ứng dụng HTTP | Có, tùy kiến trúc |
| Bảo vệ trước resolver độc hại | Không tự có | Không tự có | Không tự có |
| DNSSEC có thay thế được không? | Không | Không | Không |

Không có câu trả lời “DoH luôn an toàn hơn DoT” hoặc ngược lại. Với **mật mã TLS được cấu hình đúng**, hai cơ chế có mục tiêu bảo vệ đường truyền tương tự; khác biệt nằm ở lớp ứng dụng, cách triển khai, quản lý policy, đường đi, quyền riêng tư của resolver và hệ sinh thái hỗ trợ.

### 6.1. Khác biệt DoH với DoQ

**DNS over QUIC (DoQ)** là một cơ chế khác, sử dụng QUIC và được tiêu chuẩn hóa riêng. DoQ không đồng nghĩa với **DoH chạy trên HTTP/3** dù cả hai có thể sử dụng QUIC làm lớp vận chuyển bên dưới. Khi phân tích gói mạng, phải xác định đúng giao thức và endpoint, không quy mọi traffic UDP liên quan DNS về DoH.

## 7. TLS bảo vệ gì và còn điều gì phải tin cậy?

DoT và DoH sử dụng TLS để bảo vệ tính bí mật và toàn vẹn các thông điệp trong phiên, đồng thời hỗ trợ xác thực đầu cuối resolver.

### 7.1. Kiểm tra chứng chỉ và danh tính resolver

Một cấu hình bảo mật cần xác định:

- Resolver endpoint được tin cậy là **tên nào hoặc danh tính nào**?
- Client có kiểm tra chứng chỉ TLS, chuỗi tin cậy, tên dịch vụ và thời hạn không?
- Nếu dùng pinning hoặc identity cụ thể, quy trình thay khóa/chứng chỉ có an toàn không?
- Client có cho kết nối khi chứng chỉ sai, hết hạn hoặc tên không khớp không?
- Khi TLS thất bại, ứng dụng có fallback sang plaintext không; fallback đó có được phép không?

**Có biểu tượng ổ khóa hoặc handshake TLS không đủ nếu client bỏ kiểm tra danh tính.** TLS tới một resolver không đúng ý định chỉ bảo vệ kết nối tới **resolver đó**, không bảo đảm client đang dùng đúng nhà cung cấp DNS mong muốn.

### 7.2. Khởi tạo kết nối và bài toán bootstrap

Nếu cấu hình DoH endpoint bằng hostname (ví dụ **resolver.lab.example**), client có thể cần tìm IP của chính endpoint trước khi tạo HTTPS connection. Đây là bài toán **bootstrap DNS**.

Những phương án khác nhau:

1. Hệ điều hành dùng một resolver sẵn có để phân giải tên DoH endpoint rồi nâng cấp sang DoH.
2. Client được cấu hình sẵn địa chỉ IP liên quan, nhưng vẫn phải xác thực **tên TLS đúng**.
3. Môi trường quản trị dùng cơ chế khám phá resolver mã hóa đáng tin cậy hoặc cấu hình tập trung.
4. Một ứng dụng có kết nối resolver từ phiên trước có thể dùng thông tin cache trong điều kiện chính sách phù hợp.

**Bootstrap có thể làm lộ một truy vấn ban đầu** nếu dùng DNS plaintext. Điều đó không đồng nghĩa mọi truy vấn sau khi thiết lập DoH cũng ở dạng plaintext. Tuy nhiên cần xét DNS leakage, cache poisoning và khả năng giả mạo resolver khi bootstrap không được xác thực độc lập.

### 7.3. Downgrade và lỗi kết nối

Giả sử client ưu tiên DoT nhưng cho fallback sang DNS/53 bất cứ khi nào TCP/853 không kết nối được. Trên mạng không tin cậy, một bên có quyền chặn TCP/853 có thể khiến client dùng đường plaintext theo policy fallback.

**Đề xuất thiết kế:** đối với tài nguyên nhạy cảm, quy định rõ **chỉ dùng resolver mã hóa đã phê duyệt** hoặc fallback có điều kiện được đánh giá rủi ro và ghi log. Không tự bật downgrade im lặng rồi quảng bá tính riêng tư “end-to-end”.

## 8. DoH/DoT và DNSSEC là những lớp khác nhau

Đây là một nhầm lẫn bảo mật thường gặp.

**DNSSEC** dùng chữ ký và chuỗi xác thực DNS để giúp một **validating resolver** hoặc thành phần kiểm tra xác định dữ liệu DNS từ những zone được ký có tính xác thực nguồn gốc và toàn vẹn phù hợp. DNSSEC **không mã hóa truy vấn DNS**.

DoH/DoT mã hóa kênh **client → resolver**, nhưng không tự chứng minh rằng câu trả lời DNS của một zone là hợp lệ theo DNSSEC, hoặc resolver đang vận hành trung thực.

| Tình huống | DoH/DoT có xử lý được? | DNSSEC có xử lý được? |
|---|---|---|
| Người nghe lén trên Wi-Fi đọc tên miền từ DNS payload client–resolver | Giảm nguy cơ khi phiên TLS đúng | Không; DNSSEC không mã hóa |
| Kẻ trung gian sửa DNS message trong phiên client–resolver | TLS có thể phát hiện/ngăn sửa đổi hữu hiệu | DNSSEC cũng có thể phát hiện sửa dữ liệu được ký khi có validation |
| Resolver chủ ý trả dữ liệu sai cho zone không được ký | Không bảo đảm phát hiện | Không có chữ ký hợp lệ để kiểm chứng |
| Resolver trả dữ liệu sai cho zone được ký và bên kiểm tra xác thực DNSSEC | Chỉ bảo vệ đường truyền, không đủ một mình | Có thể phát hiện dữ liệu không hợp lệ theo chuỗi xác thực |
| Resolver ghi lại lịch sử tên miền của client | Không ngăn resolver quan sát | Không giải quyết |
| Đứt mạng/DoS làm DNS không khả dụng | Không | Không |

**Một mô hình mạnh** có thể dùng DoH/DoT tới resolver được tin cậy **và** DNSSEC validation ở vị trí phù hợp. Tuy nhiên phải xác định ai đang thực hiện DNSSEC validation và client có bằng chứng gì về hành vi đó. Không được đồng nhất việc nhận một phản hồi qua TLS với việc đã tự kiểm tra chữ ký DNSSEC.

### 8.1. QNAME minimization và các lớp giảm lộ dữ liệu khác

**QNAME minimization** là kỹ thuật tại recursive resolver nhằm hạn chế mức tên miền đầy đủ được đưa đến từng authoritative server trong các giai đoạn phân giải phù hợp. Nó giải quyết phần khác của quyền riêng tư: **resolver ↔ authoritative DNS**, không thay thế DoH/DoT client ↔ resolver.

Ngoài ra một số hệ thống có **padding DNS**, chính sách giảm log, lựa chọn resolver đáng tin cậy hoặc cơ chế như **Oblivious DoH (ODoH)** trong những triển khai được hỗ trợ. ODoH cố tách bên nhìn thấy danh tính nguồn khỏi bên nhìn thấy nội dung truy vấn theo mô hình riêng, nhưng **không phải mặc định của DoH thường** và không bảo đảm ẩn danh tuyệt đối.

## 9. Mô hình tin cậy: thông tin nào vẫn bị lộ?

Mã hóa là một lớp bảo vệ, không xóa mọi dấu vết metadata.

~~~mermaid
flowchart LR
    C[Client] -->|DoH hoặc DoT mã hóa| R[Recursive resolver]
    R -->|Tra cứu tiếp, cache, chính sách| A[Authoritative DNS]
    C -->|Kết nối ứng dụng sau DNS| W[Website / API]
    N[Điểm mạng trung gian] -.Quan sát metadata.-> C
    R -.Có thể ghi lại truy vấn.-> L[(Resolver logs)]
~~~

### 9.1. Người quan sát trên mạng

Điểm quan sát phù hợp vẫn có thể thấy một phần:

- IP client và IP resolver, thời gian và mức lưu lượng.
- Giao thức/cổng hoặc fingerprint đủ để suy đoán đó là DoT/DoH trong một số điều kiện.
- Kích thước, tần suất, hướng truyền và mẫu kết nối.
- Những metadata TLS còn quan sát được tùy phiên bản, chức năng ECH và vị trí.

**Không khẳng định người quan sát không biết website nào được mở.** Khi client kết nối trực tiếp tới website sau phân giải, IP đích và một số metadata có thể giúp suy luận, dù DNS payload đã mã hóa. HTTPS/ECH/VPN thay đổi những gì bị lộ nhưng không mặc nhiên cung cấp ẩn danh.

### 9.2. Recursive resolver vẫn thấy yêu cầu

Resolver là **điểm kết thúc TLS**, nên có thể đọc tên được truy vấn và áp caching, policy, lọc bảo mật hoặc logging. Quyền riêng tư phụ thuộc vào:

- Nhà vận hành resolver, chính sách ghi log và lưu trữ.
- Dữ liệu tài khoản, IP, token, EDNS Client Subnet nếu có và bối cảnh sử dụng.
- Khả năng chia sẻ thông tin với bên thứ ba hoặc hạ tầng khác.
- Quy trình kiểm toán, phân quyền và bảo vệ hệ thống resolver.
- Cấu hình DNSSEC, DNS filtering, QNAME minimization và các tính năng bảo mật được cấp.

**DoH tới một resolver bên ngoài không chắc riêng tư hơn DoT tới resolver nội bộ**, nếu mô hình tin cậy và chính sách dữ liệu khác nhau. Người dùng phải chọn được **đối tượng mình tin**, không chỉ chọn tên giao thức.

### 9.3. Authoritative server và website đích

Authoritative DNS có thể thấy truy vấn từ recursive resolver theo cách recursive resolver thực hiện phân giải; thường không trực tiếp thấy IP client gốc nếu không có thông tin bổ sung được chuyển tiếp. Website đích cũng có log kết nối riêng, có thể nhìn thấy IP client/proxy hoặc danh tính đăng nhập theo thiết kế.

DoH/DoT không che thông tin người dùng tự gửi tới website và không thay thế HTTP/TLS, bảo vệ cookie, quyền ứng dụng hoặc chính sách truy cập.

## 10. Client sử dụng resolver nào? Hệ điều hành, trình duyệt và ứng dụng

Một máy có thể có **nhiều đường phân giải tên**:

- **OS stub resolver** dùng DNS server được cấu hình qua DHCP, VPN, MDM hoặc chính sách hệ thống.
- **Browser secure DNS** có thể dùng DoH riêng, độc lập một phần với OS resolver.
- **Ứng dụng** có thể tích hợp DNS client riêng hoặc dùng thư viện gọi DoH endpoint cụ thể.
- **Container/Kubernetes** có thể dùng cluster DNS như CoreDNS, rồi forwarder mới quyết định đường upstream.
- **Proxy** có thể phân giải tên ở phía proxy thay vì ở client.
- **VPN client** có thể cấp DNS server, suffix và quy tắc split DNS.

Vì vậy, cấu hình DoT ở hệ điều hành **không chứng minh** mọi browser/app đều dùng resolver đó. Ngược lại, bật DoH trong browser **không chứng minh** OS, VPN client hoặc ứng dụng khác đã chuyển sang DoH.

### 10.1. Mô hình quản lý doanh nghiệp

Một tổ chức có thể ưu tiên:

1. DNS client được quản lý gửi qua DoT/DoH tới resolver doanh nghiệp khi được hỗ trợ.
2. Resolver doanh nghiệp thực hiện logging theo chính sách, DNSSEC validation khi áp dụng và security filtering.
3. Firewall hạn chế đường DNS plaintext hoặc DoT trái phép tại các vùng cần kiểm soát.
4. Endpoint/MDM và browser policies ngăn ứng dụng tự chọn resolver ngoài policy khi có khả năng quản trị.
5. Resolver có HA, giám sát availability và quy trình xử lý lỗi an toàn.

Không nhất thiết mọi tổ chức phải chặn DoH public; quyết định phụ thuộc **mức độ tin cậy của mạng, yêu cầu quyền riêng tư, quy định và nhu cầu phát hiện mối đe dọa**. Nếu chặn DoH tùy tiện, ứng dụng hợp lệ có thể bị lỗi hoặc chuyển sang đường không mong muốn.

### 10.2. Chính sách khác nhau cho các nhóm thiết bị

| Nhóm | Yêu cầu thường gặp | Cần làm rõ |
|---|---|---|
| Máy nhân viên quản trị bằng MDM | Resolver doanh nghiệp, split DNS, audit, threat filtering | OS/browser/app có dùng cùng chính sách không? |
| Mạng Guest/BYOD | Quyền riêng tư và internet access, giới hạn vào LAN | Có cần portal, DNS filtering và cách xử lý DNS ngoài? |
| Máy chủ nội bộ | Resolver ổn định, zone private, DNSSEC khi phù hợp | Truy cập DNS qua VLAN/host firewall và HA |
| Container/cloud workload | Cluster/service discovery, DNS upstream được kiểm soát | CoreDNS/kube-dns, policy egress, NAT, resolver identity |
| Thiết bị IoT | Hỗ trợ TLS/DNS có thể hạn chế | Bảo vệ tại gateway, danh sách đích, phân đoạn |
| VPN remote | Phân giải zone công ty và DNS policy | Full/split tunnel, DNS leak, resolver priority |
| Mạng công cộng không tin cậy | Xác thực resolver và tránh downgrade | Captive portal, bootstrap, lỗi TLS |

## 11. Split DNS, private zones và VPN

**Split DNS (split-horizon DNS)** là tình huống cùng một tên hoặc một nhóm tên miền được trả lời khác nhau dựa trên resolver, mạng hoặc bối cảnh của client. Nhiều doanh nghiệp cần DNS nội bộ để phân giải tên của dịch vụ private.

Ví dụ:

~~~text
Client từ Internet hỏi: api.corp.example
  -> Public resolver: không trả IP private nội bộ theo thiết kế

Client VPN được cấp quyền hỏi: api.corp.example
  -> Internal resolver: 10.20.30.15

Browser tự dùng public DoH resolver:
  -> Có thể không nhận được record private phù hợp
~~~

Các tên miền có hậu tố **.example** chỉ dùng minh họa. Trong hệ thống thật, doanh nghiệp cần tổ chức zone/suffix và quyền truy cập DNS phù hợp.

### 11.1. DoH public có thể làm hỏng split DNS

Nếu browser chuyển toàn bộ tên nội bộ sang public DoH resolver, public resolver có thể không biết zone private. Một số kết quả là **NXDOMAIN**, thiếu bản ghi nội bộ, hoặc trả record công khai khác kỳ vọng.

**Giải pháp có thể dùng:** cấu hình browser/OS theo enterprise policy, split resolver theo suffix, DNS proxy được quản lý hoặc DoH/DoT doanh nghiệp hỗ trợ private zones. Cần kiểm tra hành vi cụ thể của client vì các sản phẩm khác nhau có cơ chế bypass/fallback và thứ tự resolver riêng.

### 11.2. VPN không bảo đảm không có DNS leak

Khi máy kết nối VPN, DNS có thể đi:

- Vào tunnel và đến resolver doanh nghiệp.
- Ra Internet qua kết nối mặc định vì client/browser đang dùng resolver khác.
- Qua một split tunnel theo đích và suffix.
- Tới resolver có sẵn trước khi VPN kết nối, do cache/fallback/ưu tiên hệ điều hành.

**DNS leak** ở đây chỉ việc một số truy vấn đi ra ngoài đường resolver/tunnel mà chính sách mong muốn. Không kết luận DNS leak chỉ từ việc máy có một truy vấn HTTPS ra Internet, vì đó có thể là hoạt động ứng dụng bình thường. Cần bằng chứng về resolver endpoint, query source và policy hiệu lực.

### 11.3. Khi đường DNS mã hóa bị lỗi

Nếu client dùng strict DoT/DoH tới resolver doanh nghiệp nhưng tunnel/đường mạng mất, client có thể không phân giải tên, dù địa chỉ IP vẫn reachable. Đây có thể là **fail-closed đúng theo bảo mật**, nhưng ảnh hưởng khả năng sử dụng.

Cần thiết kế resolver dự phòng **được xác thực**, bảo vệ availability/HA và thông báo lỗi rõ; không tự mở DNS plaintext hoặc public resolver ngoài policy chỉ để che lỗi.

## 12. Captive portal, bootstrap và discovery

Mạng khách sạn, sân bay hoặc Wi-Fi công cộng có thể dùng **captive portal**, nơi người dùng phải hoàn tất đăng nhập/chấp nhận điều khoản trước khi có Internet.

Một client ở strict DoH/DoT có thể gặp khó khăn khi DNS endpoint chưa reachable hoặc cần truy cập portal để mở mạng. Một số OS/browser có logic phát hiện captive portal và tạm điều chỉnh hành vi mạng theo chính sách.

**Cần phân biệt hai mục tiêu:**

- **Khả năng vào mạng:** portal và DNS bootstrap phải hoạt động trong điều kiện giới hạn.
- **Bảo mật sau khi vào mạng:** DNS mã hóa phải được thiết lập tới resolver xác thực đúng, không âm thầm duy trì chế độ plaintext khi policy yêu cầu strict.

### 12.1. Khám phá resolver mã hóa

Ngoài cấu hình tĩnh, một số nền tảng hỗ trợ **khám phá hoặc chỉ định resolver mã hóa** qua chính sách hệ điều hành, cấu hình mạng hoặc các cơ chế tiêu chuẩn liên quan như **Discovery of Designated Resolvers (DDR)** và **Discovery of Network-designated Resolvers (DNR)** khi được hỗ trợ.

Các cơ chế này khác nhau về cách lấy thông tin và điều kiện xác thực. **Một quảng cáo resolver chưa được xác thực không đủ để tin endpoint**, nhất là trên Wi-Fi công cộng: cần đánh giá cơ chế chứng minh resolver mã hóa có liên hệ với resolver/mạng được kỳ vọng, và hành vi chống downgrade.

Trong môi trường doanh nghiệp, cấu hình được quản trị bằng MDM, OS policy hoặc profile VPN thường giúp xác định rõ resolver và logging hơn là phụ thuộc vào discovery ngoài ý muốn.

## 13. Kiến trúc triển khai DoH/DoT cho doanh nghiệp

Một phương án minh họa là dùng resolver tập trung được quản lý, có upstream policy và cơ chế giám sát:

~~~mermaid
flowchart TD
    STAFF[Máy nhân viên / OS DNS] -->|DoT 853 hoặc DoH HTTPS| R[Enterprise DNS resolver]
    BROWSER[Browser có chính sách quản trị] -->|DoH được phê duyệt| R
    VPN[Thiết bị VPN từ xa] -->|DNS theo VPN/split policy| R
    APP[App / K8s workload] --> D[DNS proxy / CoreDNS]
    D -->|Đường DNS đã được cấu hình| R
    R --> CACHE[(Cache / private zones)]
    R --> UP[Authoritative / upstream DNS]
    R -.DNS telemetry.-> SIEM[SIEM / SOC]
    FW[Firewall / egress policy] -.Kiểm soát đường DNS.-> R
~~~

Sơ đồ là **thiết kế logic**, không phải một kết nối vật lý hay khẳng định mọi thiết bị trên mạng đều hỗ trợ đồng thời cả DoT và DoH. Máy chủ DNS có thể triển khai nhiều instance để bảo đảm HA; CoreDNS có thể forward theo giao thức và plugin cấu hình thực tế.

### 13.1. Những quyết định kiến trúc cần ghi rõ

| Quyết định | Lựa chọn cần thống nhất |
|---|---|
| Resolver sở hữu bởi ai? | On-prem, cloud managed, đối tác hoặc public provider được cấp phép |
| Client nào dùng DoH/DoT? | OS, browser, app, VPN client, IoT, workload |
| Định danh endpoint | Hostname DoT, URI DoH, chứng chỉ TLS, policy xác thực |
| DNS nội bộ | Private zones, search suffix, split DNS, resolver routing |
| DNSSEC validation | Kiểm tra ở đâu, trả lỗi ra sao, xử lý zone chưa ký |
| Availability | HA, health check, lưu cache, dự phòng resolver đã phê duyệt |
| Egress | Cho phép DNS/53, TCP/853 và DoH/443 tới đâu, kiểm soát app bypass thế nào |
| Logging | Query logs, allow/deny, TLS errors, audit thay đổi và retention |
| Privacy | Ai xem log, thời hạn giữ, tối thiểu hóa dữ liệu và quyền của resolver |
| Ứng phó | Khi resolver lỗi, chứng chỉ hết hạn, policy sai hoặc bị nghi chiếm quyền thì xử lý ra sao |

### 13.2. Phân đoạn mạng và chính sách DNS

Một policy khái niệm:

~~~text
STAFF_MANAGED -> ENTERPRISE_RESOLVER   TCP/853    ALLOW nếu dùng DoT
BROWSER_MANAGED -> ENTERPRISE_DOH      HTTPS/443  ALLOW nếu dùng DoH
APP_WORKLOAD  -> CLUSTER_DNS          UDP/TCP 53  ALLOW theo thiết kế
CLUSTER_DNS   -> ENTERPRISE_RESOLVER  Kênh được duyệt ALLOW
GUEST         -> INTERNAL_DNS_PRIVATE Theo policy DENY nếu không thuộc quyền
UNKNOWN       -> EXTERNAL_DNS_53      UDP/TCP 53  DENY ở mạng managed, khi có yêu cầu
~~~

Đây là pseudo-rule, không phải cú pháp dùng trực tiếp cho firewall. Cần xác định IP/service identity thực tế, NAT, IPv4/IPv6, stateful/stateless, port phía server và đường dự phòng.

**Quan trọng:** nếu client/app gửi DoH đến resolver ngoài qua TCP/443 hoặc HTTP/3/UDP/443, rule chỉ chặn DNS/53 **không đủ** kiểm soát đường này. Việc nhận diện DoH ngoài policy có thể đòi hỏi endpoint/browser management, DNS egress governance và các biện pháp khác, không nên mặc định có thể chặn tùy ý toàn bộ HTTPS.

## 14. Tác động tới firewall, IDS/IPS, DNS filtering và giám sát

Mã hóa DNS khiến IDS/NDR đứng trên đường mạng **không còn đọc tên truy vấn từ payload DNS** nếu không ở điểm giải mã.

### 14.1. Những nơi còn nhìn thấy DNS

- **Resolver logs:** điểm tin cậy có thể ghi QNAME, loại bản ghi, response code, client identity theo chính sách.
- **OS/browser endpoint telemetry:** có thể cho biết ứng dụng nào yêu cầu phân giải, nếu sản phẩm hỗ trợ.
- **DNS proxy/forwarder logs:** giúp xác định workload/namespace gắn với truy vấn.
- **Firewall/flow logs:** thấy kết nối tới DoH/DoT endpoint, metadata và quyết định rule.
- **SIEM/NDR:** tương quan metadata, domain classification từ nguồn hợp lệ và endpoint events.
- **Cloud audit:** thay đổi DNS resolver config, policy, security group và IAM.

### 14.2. Một cảm biến chỉ nhìn ciphertext không thể phân tích QNAME

NIDS đứng giữa client và DoH resolver nhìn thấy HTTPS đã mã hóa có thể suy luận traffic tới IP/port resolver, nhưng không đọc được tên miền hỏi từ payload trong phiên TLS. Một rule IDS dựa trên QNAME chỉ hoạt động khi có **DNS data đã giải mã** từ resolver, endpoint hoặc nguồn logging phù hợp.

Nếu doanh nghiệp cần **malware domain detection**, cách hợp lý thường là giám sát tại resolver được quản lý hoặc tích hợp endpoint telemetry, chứ không tắt TLS cho toàn mạng mà không xem xét tác động riêng tư.

### 14.3. DoH và việc thực thi DNS policy

Một số tổ chức dùng DNS filtering để chặn domain đã biết có rủi ro. Nếu client tự chọn resolver bên ngoài, chính sách đó có thể không còn tác dụng tại resolver doanh nghiệp. Giải pháp cần kết hợp:

1. Công bố resolver bắt buộc/được phép theo nhóm thiết bị.
2. Cấu hình browser/OS/application đúng quyền quản trị.
3. Hạn chế những đường DNS ngoài danh sách theo cách tương thích ứng dụng.
4. Thu DNS logs ở resolver và giám sát những kết nối DoH/DoT khác lạ.
5. Định kỳ kiểm chứng với cả client thuộc mạng nội bộ, VPN và guest.

Không mặc định **mọi DoH public là độc hại**. Người dùng có thể sử dụng để bảo vệ riêng tư; quyết định hạn chế phải dựa trên mô hình đe dọa, chính sách thông báo và yêu cầu của tổ chức.

## 15. Hiệu năng, cache và độ tin cậy

DoH/DoT thêm TLS handshake và một số lớp giao thức, nhưng **không nhất thiết chậm hơn DNS plaintext trong mọi tình huống**. Kết quả phụ thuộc khoảng cách tới resolver, cache, tái sử dụng kết nối, HTTP version, cấu hình server và độ ổn định của mạng.

### 15.1. Connection reuse và caching

- **DoT:** có thể giữ kết nối TLS/TCP để gửi nhiều DNS query thay vì handshake cho từng query.
- **DoH:** có thể dùng connection reuse và multiplexing của HTTP/2 hoặc HTTP/3, tùy hỗ trợ.
- **Client/OS/browser cache:** giảm số query phải gửi tới resolver.
- **Recursive cache:** giảm số lần resolver phải tra cứu authoritative DNS.
- **TTL:** quyết định thời gian cache bản ghi theo chính sách; ghi log có thể không thấy mỗi lần ứng dụng dùng một tên đã cache.

DoH dùng HTTP cache còn phải tuân thủ ngữ nghĩa DNS, TTL và chính sách không làm sai dữ liệu; không được tự coi mọi response DNS đều có thể cache công khai như static HTML. Request/response chứa thông tin nhạy cảm cần kiểm soát log/cache tại server.

### 15.2. Đo độ trễ theo thành phần

Các chỉ số thực tế:

| Chỉ số | Giải thích |
|---|---|
| DNS resolution latency p50/p95/p99 | Trải nghiệm phân giải tên ở client |
| TLS handshake failures | Resolver name/certificate/protocol/network có vấn đề |
| DoH HTTP status/error rate | Lỗi HTTP endpoint và lỗi bên trong DNS payload cần phân biệt |
| DNS RCODE distribution | NOERROR, NXDOMAIN, SERVFAIL... theo nguồn dữ liệu |
| Cache hit/miss ratio | Resolver có tận dụng cache không |
| Connection reuse | Số phiên/kết nối được tái sử dụng |
| Fallback to plaintext | Có vi phạm chính sách mã hóa hay không |
| Resolver availability | Tỷ lệ client kết nối và nhận câu trả lời |
| Query volume by identity/zone | Phát hiện hành vi bất thường và nhu cầu capacity |
| Ingest/telemetry quality | Log có bị mất hoặc trễ không |

**DoH HTTP 200 không tự chứng minh DNS query trả về bản ghi hợp lệ**: phải giải mã message DNS và xem RCODE/answer. Tương tự, TLS handshake thành công không đảm bảo resolver đã phân giải được tên.

### 15.3. Capacity và nguy cơ DoS tới resolver

Resolver tập trung có thể trở thành tài sản quan trọng; sự cố hoặc quá tải ảnh hưởng nhiều ứng dụng. Cần:

- Nhiều instance hoặc vùng sẵn sàng tùy SLO.
- Cache và giới hạn tài nguyên theo client/tenant khi phù hợp.
- Giám sát request/connection, CPU, memory, query rate và upstream latency.
- Phòng vệ DDoS mạng và application-layer nếu resolver public.
- Quy trình thay chứng chỉ/khóa không gián đoạn.
- Thử failover và kiểm chứng các resolver dự phòng đều **được xác thực**.

## 16. Thực hành quan sát và kiểm tra an toàn

Các ví dụ dưới đây chỉ dùng cho **resolver, client và môi trường lab do người học quản trị hoặc được phép kiểm thử**. Không yêu cầu quét, phát tải hoặc truy cập DNS của bên thứ ba. Những domain có hậu tố **.example** là placeholder tài liệu, không phải endpoint hoạt động.

### 16.1. Xem cấu hình DNS hệ điều hành

Trên Linux có systemd-resolved:

~~~bash
# Đọc DNS server và domain routing của hệ thống
resolvectl status

# Đọc các DNS record theo resolver của hệ thống; không khẳng định kênh DoH/DoT
resolvectl query app.example
~~~

Tùy distro, hệ thống có thể dùng NetworkManager, dnsmasq, unbound hoặc resolver khác. Nếu không có resolvectl, hãy xem công cụ quản trị DNS phù hợp. Nội dung file resolv.conf đơn lẻ có thể chỉ trỏ tới local stub nên **không đủ để xác định upstream có dùng TLS hay không**.

Trên Windows PowerShell:

~~~powershell
# Xem những DNS server mà hệ điều hành gán cho interface
Get-DnsClientServerAddress

# Xem thông tin cấu hình DNS client theo interface
Get-DnsClient | Select-Object InterfaceAlias, ConnectionSpecificSuffix
~~~

Danh sách DNS server IP **chưa chứng minh** các truy vấn đã mã hóa. Hỗ trợ cấu hình DoH/DoT ở hệ điều hành phụ thuộc phiên bản và chính sách; phải xem công cụ setting tương ứng trên phiên bản đang dùng.

### 16.2. Kiểm tra điểm cuối DoT trong lab

Nếu trong lab có endpoint DoT thật ở tên **resolver.lab.example**, có thể kiểm tra TLS handshake bằng OpenSSL:

~~~bash
# Thay tên bằng endpoint DoT do bạn quản trị và có DNS/IP phù hợp
openssl s_client -connect resolver.lab.example:853 \
  -servername resolver.lab.example -brief
~~~

Lệnh trên tạo kết nối TLS để xem thông tin handshake/chứng chỉ; **nó không gửi DNS query hợp lệ** và không chứng minh toàn bộ policy DNS client. Việc OpenSSL in một số thông tin chứng chỉ cũng không có nghĩa tự động đã xác minh tên resolver theo policy của ứng dụng; cần kiểm tra chain/name và yêu cầu xác thực thực tế.

Nếu muốn thử DNS qua DoT, dùng công cụ DNS client **có hỗ trợ DoT theo phiên bản cụ thể** và chỉ hướng tới resolver lab đã cấu hình. Không nên đoán một tùy chọn của mọi phiên bản dig/unbound/kdig là giống nhau.

### 16.3. Kiểm tra DoH trong lab

Một số bản build **curl có hỗ trợ DoH** thông qua tùy chọn **--doh-url**. Ví dụ khái niệm:

~~~bash
# Chỉ chạy khi endpoint lab có thực và bản curl hỗ trợ DoH
curl --doh-url https://resolver.lab.example/dns-query \
  https://app.lab.example/
~~~

Tùy chọn này yêu cầu curl sử dụng DoH để phân giải tên của **đích truy cập HTTP**, chứ không phải xuất bản toàn bộ raw DNS message ra màn hình. Nếu resolver.lab.example cần phân giải trước để khởi tạo kết nối, phải xem cách curl/bootstrap hoạt động và không được bỏ qua xác thực TLS. HTTP response của app cũng không tự chứng minh mọi truy vấn OS/browser khác dùng DoH.

Nếu có DoH endpoint riêng do mình quản trị, một bài kiểm tra giao thức đầy đủ có thể gửi DNS wireformat theo RFC 8484 bằng client phù hợp và giải mã RCODE/answer; tránh gửi trực tiếp message ngẫu nhiên tới production vì có thể gây log/error noise.

### 16.4. Quan sát luồng mạng có kiểm soát

Ví dụ trên Linux khi có quyền capture trên interface lab:

~~~bash
# Chỉ ghi metadata/packet của phiên bạn được phép quan sát
sudo tcpdump -i eth0 -nn \
  'tcp port 53 or udp port 53 or tcp port 853 or tcp port 443 or udp port 443'
~~~

Lệnh này không chứng minh gói **443** nào là DoH vì nhiều ứng dụng khác cũng dùng HTTPS/QUIC. Packet capture có thể chứa dữ liệu nhạy cảm, phải giới hạn giao diện và thời gian/đích theo quyền được cấp; ví dụ trên là biểu thức bộ lọc minh họa cần thu hẹp khi dùng thực tế.

**Không nhìn thấy UDP/53 không đồng nghĩa chắc chắn không có DNS leak:** query có thể ở port/endpoint khác, được cache, đi qua giao diện khác hoặc do ứng dụng tự gửi.

### 16.5. Đối chiếu ba nguồn bằng chứng

Một phép xác minh đáng tin nên có:

1. **Cấu hình client:** DoH/DoT endpoint, strict policy, browser/app settings.
2. **Kết nối thực tế:** client thiết lập TLS tới đúng resolver và không fallback trái policy.
3. **Resolver logs:** thấy query hợp lệ từ client/identity theo thời điểm, đúng zone và trả kết quả kỳ vọng.

Thử cả **positive case** (resolver hoạt động, truy vấn phân giải đúng) và **negative case** (chứng chỉ không hợp lệ hoặc endpoint không reachable) trong lab để biết client có âm thầm chuyển sang DNS plaintext hay không.

## 17. Ma trận kiểm thử triển khai DoH/DoT

| Test | Điểm xuất phát | Điều kiện | Kỳ vọng |
|---|---|---|---|
| T1 | Máy managed nội bộ | DoT resolver hợp lệ, chứng chỉ đúng | Phân giải được, kênh TLS được xác thực |
| T2 | Máy managed nội bộ | Chứng chỉ resolver sai/hết hạn | Không chấp nhận như resolver đã xác thực; xử lý theo strict policy |
| T3 | Máy managed nội bộ | Chặn tạm TCP/853 trong lab | Quan sát rõ fail/fallback theo chính sách; không downgrade lén |
| T4 | Browser managed | DoH endpoint doanh nghiệp hợp lệ | Browser dùng resolver đã phê duyệt |
| T5 | Browser dùng split DNS | Truy vấn tên nội bộ thuộc private zone | Đi đúng resolver nội bộ và nhận record đúng |
| T6 | VPN remote | Kết nối VPN với DNS policy | Query của zone công ty đi đúng resolver/tunnel |
| T7 | Workload Kubernetes | Pod truy vấn cluster service | CoreDNS và đường upstream đúng, không bị egress policy chặn |
| T8 | Client không được phép | Cố truy vấn resolver ngoài policy | Bị quản lý/chặn theo policy thực thi được, không làm hỏng HTTPS hợp lệ |
| T9 | Resolver HA | Một instance dừng trong lab | Client chuyển sang resolver dự phòng được xác thực; SLO phù hợp |
| T10 | Sensor mạng | Quan sát traffic DoH/DoT mã hóa | Thấy metadata phù hợp, không tuyên bố đọc QNAME từ ciphertext |
| T11 | DNSSEC validation | Tên có dữ liệu DNSSEC không hợp lệ trong lab | Resolver validating xử lý đúng chính sách |
| T12 | Mạng dual-stack | IPv4 và IPv6 tới DNS endpoint | Cùng yêu cầu xác thực và ranh giới egress phù hợp |

Test cần có **owner, phạm vi, cấu hình thiết bị, thời gian và kết quả thực tế**. Không ghi “PASS” chỉ vì ping một IP thành công; cần bằng chứng DNS query và chính sách TLS đã có hiệu lực.

## 18. Chẩn đoán lỗi thường gặp

### 18.1. DoT timeout nhưng DNS plaintext chạy được

**Triệu chứng:** client tới được resolver UDP/53 nhưng không mở được TLS TCP/853.

**Kiểm tra:** route, firewall egress, listener DoT, NAT, proxy, MTU, TLS handshake và chính sách nhà mạng. Nếu kết nối 853 bị chặn bởi Wi-Fi/ISP, strict mode có thể từ chối phân giải.

**Không nên sửa bằng cách bật fallback plaintext mặc định** nếu chính sách yêu cầu mã hóa; ưu tiên resolver DoH được phê duyệt hoặc đường mạng đúng.

### 18.2. DoH báo lỗi HTTP nhưng TCP/443 vẫn open

**Triệu chứng:** kết nối HTTPS thiết lập được nhưng DoH client không phân giải tên.

**Kiểm tra:** URI endpoint đúng chưa, HTTP status, Content-Type, DNS message format, RCODE, chứng chỉ, phương thức GET/POST được hỗ trợ, proxy authorization và rate limiting. TCP/443 open chỉ chứng minh khả năng thiết lập kết nối mạng, không đảm bảo DoH endpoint hoạt động.

### 18.3. Browser vào Internet được nhưng app nội bộ không hoạt động

**Nguyên nhân có thể:** browser dùng DoH công cộng không có private zone, trong khi OS/VPN dùng resolver doanh nghiệp.

**Kiểm tra:** DNS policy của browser và OS, split DNS, VPN suffix/routing, cache và tên resolver được dùng thật. Không vội kết luận firewall API chặn khi ứng dụng còn chưa phân giải được hostname.

### 18.4. Hệ thống báo DNS leak sau khi kết nối VPN

**Kiểm tra:** query thực sự tới resolver nào, qua interface nào, trong thời điểm nào; DNS cache và browser DoH settings; split tunnel và ưu tiên DNS của OS; IPv6/IPv4. Lưu lượng HTTPS tới một IP có thể là ứng dụng khác, không đủ xác định là DoH.

### 18.5. DNSSEC validation trả SERVFAIL

**Nguyên nhân có thể:** dữ liệu chữ ký/chuỗi xác thực DNSSEC không hợp lệ, lỗi kết nối/upstream hoặc sự cố resolver khác. Không tự kết luận DoH/DoT đã hỏng chỉ vì DNS trả SERVFAIL.

**Kiểm tra:** logs DNSSEC validation và authoritative data, trạng thái resolver, clock, upstream connectivity. TLS xác thực resolver và DNSSEC validation là hai kiểm tra khác nhau.

### 18.6. IDS không còn hiển thị QNAME

**Giải thích:** khi DNS được mã hóa và sensor không nằm ở điểm giải mã, payload DNS không còn quan sát được.

**Giải pháp:** thu logging ở resolver hoặc endpoint được quản lý, dùng DNS security telemetry phù hợp và bảo vệ log theo quyền; không cố gắng giải mã tùy tiện traffic của người dùng.

### 18.7. DoH/DoT chậm hơn kỳ vọng

**Kiểm tra:** kết nối TLS có được tái sử dụng, resolver có quá xa, cache hit rate, HTTP/2/3 support, DNS retries, DNSSEC validation latency, proxy/CDN, IPv6 path, packet loss, CPU và quá tải resolver. Không quy mọi chậm trễ cho bản thân mã hóa.

## 19. Tình huống thực hành và đáp án gợi ý

### Tình huống A — Nhân viên trên Wi-Fi công cộng

Một máy quản trị dùng DoT strict tới resolver doanh nghiệp và chứng chỉ được xác thực đúng. Người cùng mạng Wi-Fi hỏi liệu họ có thể xem nội dung DNS query qua traffic capture không.

**Gợi ý:** nếu không kiểm soát endpoint hoặc điểm giải mã, họ không thể đọc DNS payload trong phiên TLS chỉ từ packet capture. Họ vẫn có thể thấy một số metadata nếu ở vị trí quan sát phù hợp, và có thể gây mất kết nối; DoT không bảo đảm ẩn danh hay availability.

### Tình huống B — Chặn port 53 để ép mã hóa DNS

Firewall chặn DNS UDP/TCP 53 ra Internet, nhưng browser vẫn dùng một DoH resolver ngoài trên HTTPS.

**Gợi ý:** đó không phải bằng chứng firewall lỗi. DoH có thể đi trên 443 và trông giống HTTPS khác; quản trị cần kết hợp policy trình duyệt/OS, danh sách resolver được phê duyệt, kiểm soát egress có điều kiện và telemetry endpoint.

### Tình huống C — Tên miền nội bộ không phân giải được

Sau khi bật browser secure DNS dùng một resolver public, nhân viên mất khả năng truy cập **api.corp.example** dù VPN vẫn hoạt động.

**Gợi ý:** kiểm tra split-horizon DNS, browser resolver override, suffix và OS/VPN DNS. Chọn resolver doanh nghiệp hoặc policy phân giải nội bộ phù hợp; không mở quyền truy cập trực tiếp tới DB hay ứng dụng chỉ vì lỗi DNS.

### Tình huống D — Resolver bị lỗi chứng chỉ

DoT client trước đây hoạt động, nhưng sau thay chứng chỉ DNS server bắt đầu từ chối kết nối.

**Gợi ý:** strict client có thể đang bảo vệ đúng bằng cách từ chối chứng chỉ không hợp lệ. Kiểm tra SNI, SAN, certificate chain, thời hạn, tên resolver và trust store; sửa endpoint/certificate theo quy trình thay vì tắt verification.

### Tình huống E — Resolver công cộng ghi lại truy vấn

Người dùng chuyển từ DNS plaintext của mạng nội bộ sang DoH public và cho rằng “không ai có thể biết tôi đã truy cập tên nào”.

**Gợi ý:** người quan sát trên đường đi khó đọc DNS payload, nhưng DoH resolver vẫn nhận được query. Website đích, DNS authoritative và metadata mạng cũng có các mức quan sát riêng. Quyền riêng tư phải đánh giá nhà vận hành resolver, lưu log, endpoint và chính sách dữ liệu.

### Tình huống F — DNSSEC không hợp lệ dù DoH kết nối tốt

DoH TLS handshake thành công, HTTP request trả lời, nhưng resolver validating báo kết quả DNSSEC không hợp lệ cho một tên đã ký.

**Gợi ý:** đó là hai lớp độc lập. TLS chứng minh giao tiếp với endpoint được xác thực, không chứng minh DNS record đã đạt kiểm tra DNSSEC. Cần xem DNSSEC logs, authoritative chain, chữ ký và nguyên nhân lỗi; không tự bỏ validation để che lỗi.

### Tình huống G — Mạng Guest có captive portal

Thiết bị mới kết nối Wi-Fi guest nhưng strict DoH không tới được endpoint trước khi mở portal; trình duyệt báo DNS lỗi.

**Gợi ý:** kiểm tra yêu cầu portal và mạng bootstrap; dùng cơ chế captive-portal detection phù hợp của OS theo chính sách. Sau khi hoàn tất portal, xác minh lại DoH endpoint và tránh fallback plaintext ngoài ý muốn.

### Tình huống H — SOC không còn thấy truy vấn DNS ở NIDS

Sau khi chuyển tất cả máy managed sang DoT, dashboard NIDS dựa trên UDP/53 giảm mạnh.

**Gợi ý:** giảm log DNS plaintext tại sensor có thể là kết quả mong muốn, không chứng minh lưu lượng DNS đã biến mất. Cần chuyển nguồn quan sát sang resolver query logs, endpoint telemetry, giám sát TLS/DoT và quản lý privacy/retention hợp lý.

## 20. Sai lầm thường gặp

1. **DoH hoặc DoT là DNSSEC.** Mã hóa kênh khác xác thực dữ liệu DNS.
2. **DoH an toàn tuyệt đối vì chạy trên 443.** HTTPS bảo vệ kênh đúng endpoint, không tự chứng minh resolver trung thực.
3. **DoT 853 chắc chắn được xác thực.** Có kết nối không có nghĩa strict certificate validation đã diễn ra.
4. **Mã hóa DNS là ẩn danh.** Resolver và một số điểm khác vẫn thấy truy vấn/metadata.
5. **Bật browser DoH đồng nghĩa toàn máy dùng DoH.** OS, VPN, app và container có thể có resolver riêng.
6. **Chặn port 53 là đã chặn mọi DNS ngoài.** DoH thường đi qua HTTPS/443; còn các cơ chế khác.
7. **Vào VPN thì mọi DNS tự đi qua tunnel.** Split tunnel, browser override và IP version có thể làm lệch đường.
8. **DNS plaintext và encrypted DNS cùng mức bảo mật khi fallback.** Downgrade có thể làm mất thuộc tính mật mã mong muốn.
9. **Firewall TCP/853 allow chứng minh DNS đã mã hóa toàn hệ thống.** Phải xác minh truy vấn thực tế, TLS identity và client policy.
10. **DoH GET làm lộ URI cho mọi người quan sát mạng.** HTTPS bảo vệ URI trong phiên; điểm TLS termination vẫn có thể thấy/log.
11. **DoH luôn nhanh hơn hoặc chậm hơn DoT.** Hiệu năng phụ thuộc cache, route, TLS reuse, phiên bản HTTP và resolver.
12. **Không cần DNSSEC nếu đã dùng DoH.** Khi cần kiểm tra tính xác thực dữ liệu vùng được ký, DNSSEC vẫn hữu ích.
13. **Một resolver public tốt cho mọi private zone.** Split DNS và chính sách doanh nghiệp cần resolver phù hợp.
14. **Không có UDP/53 nghĩa không có DNS leak.** Query có thể qua DoH/DoT, IPv6, interface khác hoặc cache.
15. **IDS phải giải mã được QNAME từ DoH/DoT.** Không ở điểm TLS termination thì chỉ có metadata phù hợp.
16. **Chỉ dùng một DoH endpoint là đủ availability.** Cần HA, quy trình thay chứng chỉ, dự phòng và kiểm soát DDoS.
17. **Bỏ qua IPv6.** Một máy có thể dùng DNS resolver/đường IPv6 ngoài chính sách IPv4.
18. **Thu toàn bộ DNS logs vô thời hạn.** Truy vấn DNS có thể nhạy cảm; cần retention và phân quyền.
19. **Coi mọi encrypted DNS ngoài doanh nghiệp là ác ý.** Chính sách phải dựa trên mô hình tin cậy và mục tiêu bảo vệ.
20. **Tin một phép test duy nhất.** Cần kiểm tra cả DNS answer, TLS identity, path, fallback và tính nhất quán OS/browser/app.

## 21. Checklist triển khai DoH và DoT

- [ ] Xác định tài sản, threat model và yêu cầu riêng tư của các nhóm client.
- [ ] Chọn resolver được tin cậy và ghi rõ owner, nhà vận hành, logging policy.
- [ ] Cấu hình DoT hostname hoặc DoH URI cùng xác thực chứng chỉ/TLS.
- [ ] Quy định strict privacy, fallback và hành vi khi resolver bị lỗi.
- [ ] Xác định cách bootstrap endpoint và cơ chế khám phá nếu sử dụng.
- [ ] Đảm bảo split DNS/private zones hoạt động cho LAN và VPN.
- [ ] Xem policy khác nhau giữa OS, browser, ứng dụng, container và proxy.
- [ ] Kiểm tra cả IPv4 và IPv6, những đường ngoài VPN và đường egress khác.
- [ ] Không đồng nhất DoH/DoT với DNSSEC; xác định DNSSEC validation nếu cần.
- [ ] Bảo vệ quyền sửa resolver, certificate, browser policy, VPN DNS và firewall rules.
- [ ] Thiết kế HA/resolver dự phòng được xác thực, health checks và kế hoạch thay chứng chỉ.
- [ ] Thu telemetry ở resolver/endpoint; xác định điểm mù của NIDS trên traffic mã hóa.
- [ ] Theo dõi latency, cache hit, TLS errors, DNS RCODE, fallback và resolver availability.
- [ ] Bảo vệ DNS query logs bằng phân quyền, mã hóa, retention và audit.
- [ ] Kiểm thử tên public và private, trường hợp allow/deny và lỗi chứng chỉ trong lab.
- [ ] Xác minh sự kiện DoH HTTP được phân tích cùng DNS answer/RCODE, không chỉ mã HTTP.
- [ ] Kiểm tra tương tác với captive portal, proxy, CDN, firewall, WAF và DoS protection.
- [ ] Có quy trình xử lý sai cấu hình, downgrade, DNS leak và mất availability.
- [ ] Review cấu hình khi có thay đổi mạng, VPN, browser, cloud, DNS provider hoặc policy.
- [ ] Ghi lại bằng chứng end-to-end về **client → TLS endpoint → resolver → DNS answer**.

## 22. Kết luận

**DoT** và **DoH** đều dùng TLS để bảo vệ nội dung DNS trên chặng từ client tới resolver đã được xác thực. DoT thường sử dụng **TCP/853**, còn DoH vận chuyển DNS qua **HTTPS**, thường trên **443**. Khác biệt lớn nhất là cách đóng gói, khả năng tích hợp ứng dụng, quản trị và quan sát, chứ không phải DoH mặc nhiên “mạnh” hơn DoT hoặc ngược lại.

Để triển khai đúng trong **SECURITY_NETWORK_SECURITY**, cần kết hợp **chọn resolver tin cậy, kiểm tra chứng chỉ, chống downgrade, DNSSEC validation khi phù hợp, split DNS/VPN, firewall/egress policy, logging tại resolver, giám sát IDS/IPS và khả năng sẵn sàng của hạ tầng**. Thiết kế thành công phải chứng minh vừa bảo vệ được truy vấn trên đường truyền, vừa phân giải đúng dịch vụ của người dùng và vẫn đáp ứng các yêu cầu bảo mật, riêng tư và vận hành của tổ chức.
