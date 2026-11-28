# DNS exfiltration: nhận diện và ngăn rò rỉ dữ liệu qua DNS

**DNS exfiltration** là hành vi lợi dụng hệ thống phân giải tên miền (Domain Name System – DNS) để đưa thông tin từ một môi trường ra bên ngoài qua những thông điệp DNS. Trong nhiều tổ chức, DNS được phép hoạt động để máy tính, trình duyệt và ứng dụng tìm được địa chỉ dịch vụ. Chính tính phổ biến này khiến DNS có thể bị lạm dụng làm kênh truyền dữ liệu không mong muốn, ngay cả khi nhiều giao thức kết nối ra ngoài khác đã bị giới hạn.

Vấn đề phòng thủ không đơn giản là “chặn các tên miền dài”. Nhiều truy vấn hợp lệ của CDN, xác thực email, dịch vụ cloud và hệ thống giám sát cũng có tên dài hoặc nhiều chuỗi khó đọc. Đồng thời, không phải mọi hành vi exfiltration đều tạo ra tên miền quá dài hay tỷ lệ lỗi phân giải cao. Muốn phát hiện đáng tin cậy, cần kết hợp **ngữ cảnh tài sản, cấu trúc truy vấn, hành vi theo thời gian, quyền truy cập DNS, log resolver và dữ liệu endpoint**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề này liên kết DNS security với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, mạng không dây, giám sát xâm nhập và kiến trúc cloud. Bài học tập trung vào **phòng ngừa, quan sát, điều tra và ứng cứu**; mọi ví dụ chỉ dùng dữ liệu minh họa, không hướng dẫn chuyển dữ liệu thật ra ngoài.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **DNS exfiltration** khác gì với truy vấn DNS hợp lệ, DNS tunneling và DNS-based command-and-control (C2).
2. Mô tả những thành phần tham gia một truy vấn DNS: **client/stub resolver, recursive resolver, authoritative DNS và hệ thống ghi log**.
3. Nhận biết các dấu hiệu như **nhiều subdomain duy nhất, nhãn bất thường, tần suất cao, biến đổi độ dài và loại bản ghi**.
4. Phân tích các hạn chế của chỉ số **entropy, NXDOMAIN, DNS query length và query volume** để giảm false positive.
5. Hiểu những blind spot do **cache, DNS over HTTPS (DoH), DNS over TLS (DoT), DNS over QUIC (DoQ), VPN và DNS phân tán**.
6. Đề xuất biện pháp phòng thủ gồm **resolver được quản lý, egress policy, endpoint telemetry, RPZ/sinkhole phù hợp và kiểm soát danh tính thiết bị**.
7. Xây dựng **kịch bản điều tra và ma trận kiểm thử có phép**, phân biệt bằng chứng trực tiếp với giả thuyết chưa xác nhận.

## 2. DNS vận hành bình thường ra sao?

Khi ứng dụng cần kết nối tới một dịch vụ theo tên, nó có thể gọi hệ thống phân giải tên. Tùy cấu hình, truy vấn được trả lời từ cache cục bộ, recursive resolver, hoặc cần đi tới các máy chủ DNS authoritative.

~~~text
             [Ứng dụng trên laptop]
                        |
                 Stub resolver / OS
                        |
                DNS resolver được cấp
                        |
              [Recursive resolver]
                 |            |
             Cache hit    Cache miss
                 |            |
             Trả kết quả  [Root / TLD / Authoritative DNS]
                                |
                         Trả thông tin DNS
                                |
                       Recursive resolver
                                |
                             Client
~~~

Các thành phần chính:

| Thành phần | Vai trò | Ý nghĩa đối với điều tra |
|---|---|---|
| **Ứng dụng / stub resolver** | Khởi tạo truy vấn hoặc dùng API phân giải của hệ điều hành | Có thể liên hệ domain với tiến trình, user và hành vi máy |
| **Recursive resolver** | Phân giải hoặc trả dữ liệu từ cache; áp chính sách nếu được quản lý | Cung cấp log truy vấn, quyết định block/allow và telemetry tập trung |
| **Authoritative DNS** | Phục vụ thông tin cho zone mà nó có thẩm quyền | Có thể nhận câu hỏi cho tên dưới zone của mình, tùy cache và đường phân giải |
| **DNS cache** | Giảm số lần cần hỏi phía ngoài | Log authoritative và log endpoint không nhất thiết có cùng số lượng truy vấn |
| **Firewall / IDS / NDR** | Quan sát lưu lượng tại điểm đặt | Có thể thấy địa chỉ, cổng, DNS rõ hoặc chỉ flow mã hóa |

**Không nên mặc định mọi truy vấn client đều tới authoritative server.** Resolver có thể trả lời từ cache, sử dụng forwarder, áp chính sách local hoặc thực hiện các tối ưu khác. Nhiều triển khai cũng có **split-horizon DNS**, phân giải domain khác nhau tùy mạng nội bộ hay bên ngoài.

### Những trường DNS quan trọng

Một câu hỏi DNS có thể chứa:

- **QNAME:** tên cần phân giải, ví dụ app.corp.example.test.
- **QTYPE:** loại bản ghi được hỏi, ví dụ A, AAAA, MX, TXT, CNAME hoặc SRV.
- **QCLASS:** lớp của câu hỏi, thường là IN trong DNS Internet.
- **Response code / RCODE:** kết quả như NOERROR, NXDOMAIN hoặc SERVFAIL.
- **Answer/authority/additional sections:** những dữ liệu trả về, khi có.
- **TTL:** thông tin thời hạn cache đối với các bản ghi thích hợp.

DNS có giới hạn định dạng: một **label tối đa 63 octet**, và tên miền trong biểu diễn DNS on-wire có độ dài tối đa **255 octet**. Tuy vậy, những giới hạn kỹ thuật này **không phải dấu hiệu nhận diện exfiltration**: truy vấn đạt gần giới hạn chưa chắc độc hại, và kênh rò rỉ cũng không nhất thiết dùng tên dài.

## 3. DNS exfiltration hoạt động ở mức khái niệm

Giả sử một máy trong mạng doanh nghiệp có dữ liệu mà kẻ tấn công muốn đưa ra ngoài. Nếu máy đó chỉ được phép hỏi DNS, kẻ tấn công có thể tìm cách đưa những phần thông tin vào **nội dung mà hệ thống DNS chuyển qua ranh giới mạng**, thay vì tạo một kết nối ứng dụng ra ngoài thông thường.

~~~text
                   MẠNG DOANH NGHIỆP

            [Endpoint bị xâm nhập]
                       |
              Truy vấn DNS bất thường
                       |
             [Resolver / DNS policy]
                       |
                 [Network edge]
                       |
                       v
                  INTERNET
                       |
             [Hạ tầng DNS bên ngoài]

 Vùng cần bảo vệ: Dữ liệu và danh tính endpoint
 Điểm quan sát:  EDR + resolver logs + firewall/NDR
~~~

Ở mô hình này, truy vấn DNS có thể mang tín hiệu hoặc thông tin do bên gửi đưa vào **QNAME** hay thành phần giao thức khác tùy cách lạm dụng. Nếu truy vấn được chuyển ra hệ thống DNS mà một bên không được phép kiểm soát, dữ liệu trong tên được hỏi có thể ra khỏi ranh giới bảo mật. Chính sách bảo vệ cần giới hạn ai được dùng resolver nào, phát hiện những tên bất thường và bảo đảm lưu lượng đi qua điểm quan sát đã được phê duyệt.

**Không đồng nghĩa chỉ cần thấy DNS query dài là đã xảy ra rò rỉ.** Muốn xác nhận exfiltration, phải có bằng chứng rằng dữ liệu không được phép đã được đưa ra khỏi hệ thống, hoặc có kết luận điều tra đủ tin cậy liên hệ endpoint, nội dung, tên đích và hành vi gửi.

### DNS exfiltration, DNS tunneling và C2 khác nhau thế nào?

| Khái niệm | Mục đích nổi bật | Có phải cùng một hiện tượng? |
|---|---|---|
| **DNS exfiltration** | Chuyển thông tin ra ngoài qua DNS | Là hành vi rò rỉ; có thể chỉ một chiều và không cần phiên tương tác dài |
| **DNS tunneling** | Dùng DNS làm lớp vận chuyển cho dữ liệu của kênh khác | Có thể được dùng để exfiltration, C2 hoặc mục đích đặc biệt; không phải mọi tunneling đều tự chứng minh rò rỉ trái phép |
| **DNS-based C2** | Trao đổi tín hiệu điều khiển với thành phần bị xâm nhập | Có thể tồn tại mà không có exfiltration đã xác nhận; vẫn là rủi ro bảo mật |
| **DNS lookup hợp lệ** | Phân giải tên phục vụ một hoạt động được phép | Có thể có nhiều truy vấn và tên phức tạp mà không phải tấn công |

Việc phân biệt giúp **chọn đúng kịch bản ứng cứu**: nghi ngờ C2 cần kiểm tra tiến trình và hành vi điều khiển; nghi ngờ exfiltration cần tập trung vào phạm vi dữ liệu có thể bị lộ và các kênh thoát ra ngoài.

## 4. Mô hình hóa mối đe dọa

Nên bắt đầu bằng việc xác định **tài sản cần bảo vệ, điểm tin cậy và quyền truy cập DNS**.

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| **Tài sản** | Endpoint nào lưu dữ liệu nhạy cảm, token, khóa API, tài liệu hoặc thông tin khách hàng? |
| **Đối tượng truy cập** | Người dùng, dịch vụ, container và IoT nào được dùng DNS? Có endpoint không quản lý không? |
| **Điểm thoát mạng** | DNS đi qua recursive resolver nội bộ, VPN, cloud resolver hay đường truy vấn trực tiếp? |
| **Tên miền/zone** | Những domain nào phục vụ nghiệp vụ thật; domain nào mới xuất hiện hoặc chưa rõ chủ sở hữu? |
| **Điểm thực thi** | Firewall, DNS firewall, NAC, host policy và cloud security control nào có thể giới hạn egress? |
| **Nguồn dữ liệu** | Resolver logs, EDR, NDR, proxy, flow logs và identity logs nào có thể tương quan? |
| **Tác động** | Dữ liệu nào có thể bị lộ, từ máy nào, trong khung thời gian nào và yêu cầu báo cáo ra sao? |

### Những đường rò rỉ tiềm tàng cần xem xét

1. **Truy vấn trực tiếp từ endpoint** tới DNS resolver bên ngoài khi chính sách egress cho phép.
2. **Truy vấn qua recursive resolver của tổ chức**, trông như hoạt động DNS hợp lệ nhưng có mẫu tên bất thường.
3. **Truy vấn dùng DNS mã hóa** tới resolver không thuộc tổ chức, làm sensor DNS rõ trên đường mạng không đọc được QNAME.
4. **DNS qua VPN hoặc proxy** khiến địa chỉ nguồn quan sát ở một lớp khác địa chỉ endpoint thực.
5. **Workload cloud/container** dùng DNS riêng của nền tảng hoặc resolver được cấu hình ở môi trường triển khai.

**Đường thoát DNS không nhất thiết là UDP/53.** Cần tính tới TCP/53, DNS mã hóa và các cơ chế hệ điều hành/trình duyệt quản lý resolver. Không nên chặn tùy tiện toàn bộ TCP/53 vì DNS hợp lệ có thể dùng TCP, chẳng hạn khi response lớn hoặc theo triển khai giao thức.

## 5. Dấu hiệu trong DNS query và log

Không có một đặc trưng đơn lẻ đủ tin cậy để khẳng định hành vi rò rỉ. Phát hiện tốt thường kết hợp nhiều nhóm tín hiệu.

| Nhóm tín hiệu | Quan sát đáng chú ý | Vì sao cần thận trọng? |
|---|---|---|
| **Tên miền dài** | QNAME có nhãn dài hoặc gần giới hạn thông thường | CDN, mã xác minh, dịch vụ telemetry cũng có tên dài |
| **Nhiều subdomain duy nhất** | Một máy hỏi hàng loạt tên chưa từng thấy dưới cùng parent domain | Hệ thống theo dõi/định danh request hợp lệ cũng có thể tạo tên độc nhất |
| **Độ biến thiên ký tự** | Label có chuỗi ít giống từ tự nhiên, độ đa dạng ký tự cao | Hash, nonce, identifier và nội dung mã hóa hợp lệ gây hiện tượng tương tự |
| **Tần suất và nhịp thời gian** | Nhiều query trong thời gian ngắn, lặp có nhịp hoặc khác baseline | Batch job, agent cập nhật hoặc lỗi DNS retry có thể giống |
| **QTYPE bất thường** | Tỷ lệ loại record thay đổi so với vai trò endpoint | TXT, SRV, CNAME, AAAA đều có ứng dụng hợp lệ |
| **RCODE/NXDOMAIN** | Lượng kết quả không tồn tại tăng, nhiều tên duy nhất | Lỗi cấu hình, typo, search suffix hoặc service discovery tạo NXDOMAIN |
| **Domain mới hoặc ít được biết đến** | Máy liên hệ domain không nằm trong inventory hoặc baseline | Domain mới không tự là độc hại; đối tác có thể thay đổi dịch vụ |
| **Quy mô và hướng lưu lượng** | Tăng bytes câu hỏi DNS outbound, biến động upstream | DNSSEC, EDNS, response lớn, retry và số client dùng chung resolver ảnh hưởng |
| **Nguồn endpoint** | Tiến trình lạ bắt đầu nhiều DNS query hoặc đổi resolver | Cần kiểm tra lịch cập nhật, công việc chính đáng và dấu hiệu xác thực |

**Không đồng nhất tên miền “trông ngẫu nhiên” với nội dung được mã hóa.** Dữ liệu có entropy cao chỉ là dấu hiệu thống kê. Ngược lại, nếu kênh được phân mảnh thành các tên ngắn hoặc pha trộn với hoạt động bình thường, chỉ nhìn độ dài sẽ không đủ.

### 5.1. Chú ý parent domain và subdomain

Khi nhiều truy vấn có tên không giống nhau nhưng chung một domain gốc hoặc zone do cùng bên kiểm soát, nên tổng hợp hành vi theo **registrable domain/eTLD+1 hoặc zone được xác định chính xác**.

Không nên tự xác định registrable domain chỉ bằng cách lấy **hai label cuối**, vì có nhiều public suffix gồm nhiều cấp, ví dụ domain thuộc các cấu trúc tên phân cấp. Việc phân nhóm phải dựa vào **Public Suffix List phù hợp** hoặc dữ liệu phân cấp zone được xác minh để tránh gộp nhầm những chủ thể không liên quan.

**Bẫy thống kê:** nếu chỉ tổng hợp theo resolver IP, một resolver phục vụ hàng nghìn endpoint có thể sinh hàng triệu truy vấn hợp lệ. Cần bổ sung client identity, network segment và mối liên hệ với app/host nếu có.

### 5.2. Phân biệt query volume và uniqueness

Một máy có thể hỏi **cùng một tên** hàng nghìn lần vì retry hoặc lỗi cache; hành vi ấy khác với hàng nghìn **QNAME duy nhất** dưới một domain. Trong một đợt điều tra, nên đo đồng thời:

- Tổng số query và số **QNAME duy nhất**.
- Tỷ lệ unique QNAME / tổng số query theo từng client–domain trong khung thời gian.
- Độ dài QNAME hoặc label **trung vị, phân vị 95/99**, không chỉ giá trị lớn nhất.
- Phân phối **QTYPE, RCODE, response size** và khoảng cách giữa các query.
- Độ mới của parent domain đối với **chính tài sản**, không chỉ độ mới toàn tổ chức.

Những số liệu này **phụ thuộc điểm thu thập và cơ chế cache**, nên cần ghi rõ log lấy ở stub, recursive resolver hay authoritative layer.

## 6. NXDOMAIN, TXT và những ngộ nhận thường gặp

### NXDOMAIN không phải điều kiện cần

**NXDOMAIN** cho biết tên được hỏi không tồn tại theo phản hồi DNS phù hợp. Một số mẫu truy vấn bất thường có thể tạo nhiều NXDOMAIN, nhưng nhiều ứng dụng hợp lệ cũng vậy. Mặt khác, một hệ thống có thể trả lời NOERROR cho nhiều tên động, nên **không thấy NXDOMAIN không chứng minh an toàn**.

Các nguyên nhân NXDOMAIN hợp lệ:

- Trình duyệt/người dùng gõ sai tên.
- Search domain suffix của hệ điều hành tự thử các tên nội bộ.
- Phát hiện dịch vụ hoặc ứng dụng kiểm tra nhiều tên trong quá trình khởi động.
- Thiết bị di động chuyển mạng hoặc stale configuration tạo retry.

### TXT không phải bản ghi mặc định là độc hại

**TXT records** được dùng hợp pháp cho SPF/DKIM, DMARC, xác minh quyền sở hữu domain, ACME DNS challenge và nhiều cơ chế cấu hình. Do đó, chỉ chặn toàn bộ TXT là một biện pháp dễ gây gián đoạn và chưa chắc ngăn được các kỹ thuật lợi dụng tên truy vấn.

Điều cần kiểm tra là **vai trò của client, owner của domain, cấu trúc truy vấn và thay đổi hành vi**. Các loại record A/AAAA, TXT, CNAME, SRV và những loại khác đều có thể xuất hiện trong hệ thống hợp lệ.

### DNSSEC và rò rỉ dữ liệu

**DNSSEC** giúp xác minh nguồn gốc và tính toàn vẹn của dữ liệu DNS được ký trong chuỗi tin cậy; nó **không mã hóa nội dung truy vấn**, cũng **không ngăn một client được phép gửi truy vấn tới domain do bên ngoài kiểm soát**. Vì thế bật DNSSEC không thay thế giám sát và chính sách egress chống DNS exfiltration.

## 7. Ví dụ telemetry tổng hợp trong điều tra

Dưới đây là **log tổng hợp giả lập**, chỉ gồm metadata, không chứa dữ liệu bí mật hoặc tên dùng cho kênh truyền thực:

~~~text
2026-11-28T09:20:01+07:00
client=10.20.10.25
process=unknown-at-resolver
qname=alpha07.telemetry-lab.example.test
qtype=A
rcode=NOERROR
resolver=corp-dns-01

2026-11-28T09:20:02+07:00
client=10.20.10.25
qname=beta18.telemetry-lab.example.test
qtype=AAAA
rcode=NOERROR
resolver=corp-dns-01

2026-11-28T09:20:03+07:00
client=10.20.10.25
qname=gamma29.telemetry-lab.example.test
qtype=A
rcode=NOERROR
resolver=corp-dns-01
~~~

Những tên trên chỉ là **giá trị lab minh họa**, không chứng minh exfiltration. Ba query ngắn không đủ để phân biệt giữa kiểm thử hợp lệ, hệ thống gắn định danh cho từng truy vấn và hành vi bất thường.

**Cần hỏi thêm:**

1. Máy 10.20.10.25 thuộc nhóm nào? Có chạy agent giám sát hoặc bản cập nhật mới không?
2. Domain có chủ sở hữu và mục đích đã được xác minh không?
3. Số query và tên duy nhất trong **toàn bộ khoảng thời gian** là bao nhiêu, so với baseline cùng vai trò?
4. Ở endpoint, **tiến trình nào** tạo các truy vấn? Là tiến trình được quản lý hay mới xuất hiện?
5. Có tương quan với truy cập tài liệu nhạy cảm, thay đổi tài khoản hoặc phát hiện EDR khác không?
6. Resolver có đi ra ngoài đúng đường được phép hay thiết bị gửi DNS trực tiếp qua đường khác?

Chỉ sau khi kết hợp những bằng chứng này mới có thể ưu tiên hành động phù hợp.

## 8. DNS được mã hóa: DoH, DoT, DoQ và visibility

DNS mã hóa bảo vệ quyền riêng tư và hạn chế quan sát/sửa đổi truy vấn trên đường truyền, nhưng có thể tạo **blind spot** cho NIDS nếu tổ chức chỉ thu thập DNS rõ tại UDP/TCP 53.

| Cơ chế | Vận chuyển thường gặp | Sensor ngoài phiên nhìn thấy gì? | Nguồn telemetry thích hợp |
|---|---|---|---|
| **DNS truyền thống** | UDP/TCP 53 | Có thể đọc QNAME/QTYPE/RCODE nếu sensor thấy gói và chúng không được bảo vệ bởi tunnel khác | Resolver logs, DNS sensor, endpoint logs |
| **DNS over TLS (DoT)** | TCP 853 thường gặp | Flow/TLS metadata, không tự đọc DNS question | Resolver được quản lý, endpoint/OS policy |
| **DNS over HTTPS (DoH)** | HTTPS, thường TCP/443 hoặc HTTP/3 tùy triển khai | Có thể giống HTTPS thông thường, không tự đọc QNAME | Resolver logs nếu do tổ chức kiểm soát, browser/EDR, proxy telemetry |
| **DNS over QUIC (DoQ)** | QUIC, thường dùng UDP/853 theo cấu hình tiêu chuẩn | Metadata transport/QUIC phù hợp, không tự đọc DNS message | Resolver và endpoint telemetry |
| **DNS qua VPN/IPsec** | Bọc trong tunnel | Sensor ngoài tunnel có thể chỉ thấy outer IP/UDP/ESP | Sensor sau VPN termination, resolver nội bộ |

**Không thể khẳng định mọi HTTPS tới TCP/443 là DoH** hoặc mọi UDP/853 chắc chắn là DoQ. Cổng và IP chỉ là tín hiệu; CDN/shared infrastructure có thể phục vụ nhiều ứng dụng. Một số client có thể dùng resolver tùy chọn hoặc đổi giao thức khi mạng thay đổi.

### Cách giảm blind spot mà không phá quyền riêng tư

- Sử dụng **resolver do tổ chức quản lý** và bật logging phù hợp với mục đích an ninh.
- Cấu hình chính sách hệ điều hành, trình duyệt và ứng dụng quản lý để dùng resolver được phê duyệt.
- Giới hạn **DNS egress** tới resolver cho phép bằng firewall/NAC/cloud policy, xét cả IPv4 và IPv6.
- Theo dõi endpoint/EDR để biết **tiến trình nào** tạo DNS hoặc kết nối tới resolver ngoài danh mục.
- Đối chiếu firewall flow, TLS/QUIC metadata và danh tính thiết bị, không giả định giải mã mọi kết nối.
- Xây dựng ngoại lệ có owner cho VPN, endpoint lưu động và dịch vụ cần resolver đặc thù.

**Chặn DoH bằng cách chặn toàn bộ HTTPS/443 là không phù hợp** với hầu hết mạng nghiệp vụ và có thể gây ảnh hưởng nghiêm trọng. Kiểm soát DoH nên dựa trên client được quản lý, policy resolver, danh mục dịch vụ có căn cứ và giám sát các đường ngoài dự kiến.

## 9. Kiến trúc phòng vệ DNS theo nhiều lớp

Một phương án tham chiếu:

~~~text
                 [Managed endpoints]
                   |           |
                   |           +-- [EDR / process telemetry]
                   |
          [NAC / endpoint policy]
                   |
             [Internal DNS]
             recursive resolver
                   |       |
              DNS policy   Resolver query logs
              / filtering         |
                   |              v
                   |          [SIEM / NDR]
                   |
           [Firewall / Egress]
                   |
                 Internet
                   |
             Authoritative DNS

  Nhánh ngoài dự kiến:
  Endpoint -> external resolver / DoH service
           -> cần chính sách và telemetry bổ sung
~~~

### Những biện pháp chính

| Lớp | Biện pháp | Điều cần xác minh |
|---|---|---|
| **Endpoint/NAC** | Thiết bị quản lý được cấp chính sách DNS, danh tính và role | Không có endpoint phụ gửi DNS ra ngoài qua đường không kiểm soát |
| **Recursive resolver** | Ghi log truy vấn, quản lý upstream, phân loại domain và policy | Bật đúng phạm vi log, có đồng bộ thời gian, không lưu dữ liệu quá mức |
| **Firewall/egress** | Chỉ cho các nguồn phù hợp đi đến resolver được duyệt; xét TCP/UDP và dual-stack | Rule không chặn DNS phục vụ nghiệp vụ, VPN hoặc khôi phục sự cố |
| **DNS firewall/RPZ** | Chặn hoặc thay đổi câu trả lời cho domain được đánh giá rủi ro theo chính sách | Danh sách có chất lượng, xử lý false positive, kiểm soát thay đổi |
| **IDS/NDR** | Phân tích tần suất, độ dài, uniqueness, domain novelty và flow | Sensor thấy đúng đường, không chỉ nhìn traffic Internet edge |
| **EDR** | Liên kết query với process, tài khoản và hành vi file | Quyền agent/OS cho phép; không tự có coverage 100% |
| **Cloud/Kubernetes** | Resolver, egress policy, CNI/host telemetry, service account | Workload không bị bỏ qua vì đường DNS của node/sidecar |
| **SIEM/correlation** | Kết hợp resolver, firewall, EDR, inventory và identity logs | Cùng múi giờ, có mapping địa chỉ động và NAT đúng |

**DNS sinkhole/RPZ** là công cụ có thể được dùng để ngăn hoặc chuyển hướng tên theo chính sách, nhưng không nên tự động đưa mọi domain lạ vào sinkhole. Nếu một domain phục vụ dịch vụ hợp lệ, chặn nhầm sẽ ảnh hưởng availability; cần quy trình ngoại lệ và bằng chứng.

## 10. Bảo vệ ranh giới egress và giảm khả năng bypass

Để một chính sách DNS có hiệu quả, cần biết **DNS thật sự đi qua đâu**:

1. Máy nhân viên có bắt buộc dùng recursive resolver nội bộ không?
2. VPN client dùng DNS nội bộ hay DNS của mạng ngoài khi split tunnel?
3. Thiết bị có IPv6 resolver khác với IPv4 resolver không?
4. Browser có bật chế độ tự chọn DoH resolver không?
5. Container hoặc cloud workload có resolver riêng hay đi qua node?
6. Firewall có rule cho phép đi thẳng tới TCP/UDP 53 ngoài danh mục không?
7. Proxy/ngõ ra HTTPS nào cho phép lưu lượng mã hóa không có telemetry?

**Lưu ý:** Ngăn đường DNS trực tiếp không đồng nghĩa ngăn mọi rò rỉ dữ liệu. HTTPS, cloud storage, email, kênh API và những dịch vụ khác vẫn có thể bị lợi dụng. Chính sách egress là thành phần của chiến lược **data loss prevention (DLP)** và **least privilege**, không chỉ là bộ lọc một giao thức.

### Split tunneling và thiết bị lưu động

Khi laptop vừa kết nối VPN doanh nghiệp vừa dùng mạng Internet cục bộ, lưu lượng DNS có thể đi tới **resolver nội bộ, resolver tại nhà hoặc dịch vụ mã hóa** tùy OS/policy. Chỉ kiểm tra DNS ở data center không chứng minh toàn bộ yêu cầu của endpoint đã được quan sát. Cần xác định chính sách client, tunnel routes, DNS search suffix và behavior khi VPN mất kết nối.

### Rủi ro availability khi cưỡng chế DNS

Nếu chỉ có một resolver nội bộ mà không có phương án dự phòng, việc chặn các resolver khác có thể làm **mọi ứng dụng mất khả năng phân giải khi resolver chính lỗi**. Thiết kế phải có recursive resolver HA, kiểm tra health, giám sát thời gian phản hồi và kế hoạch khi DNS provider/network segment bị gián đoạn.

## 11. Xây dựng detection theo hướng nhiều tín hiệu

Một detection dùng một ngưỡng cố định như “QNAME dài hơn N ký tự thì block” dễ gây chặn nhầm. Có thể thay bằng một **quy trình đánh giá theo tầng**:

~~~text
DNS event(s)
      |
      v
Kiểm tra nguồn, loại thiết bị, resolver và baseline
      |
      v
Tổng hợp query theo client + domain + time window
      |
      v
Tín hiệu kết hợp:
  - số subdomain mới
  - độ dài label và biến thiên ký tự
  - query volume / QTYPE / RCODE
  - domain novelty và business ownership
      |
      v
Đối chiếu EDR, inventory, identity và egress logs
      |
      v
Ưu tiên điều tra, rồi mới quyết định chặn hoặc cô lập
~~~

### Pseudocode cho triage, không phải detector tự động

~~~text
FOR each client + parent-domain in a reviewed time window:
    Gather query counts, distinct names, type distribution, rcode
    Compare with the baseline of the same asset role
    Check domain ownership and known business dependencies
    Correlate with endpoint process and firewall egress events

    IF multiple unusual signals appear:
        Open investigation with supporting evidence
    ELSE:
        Retain telemetry within the approved policy

Do not automatically label a host compromised from entropy alone.
~~~

**Không có ngưỡng duy nhất đúng cho mọi môi trường.** Laptop văn phòng, DNS resolver tập trung, máy chủ email, Kubernetes node và ứng dụng telemetry có baseline khác nhau. Chỉ số entropy, đặc điểm label và query rate cần được hiệu chỉnh theo **loại tài sản, lịch làm việc, phần mềm chạy và lượng traffic thực tế**.

### Entropy và tính ngẫu nhiên

Entropy hoặc độ đa dạng ký tự có thể giúp đưa các label có dạng không giống ngôn ngữ tự nhiên vào nhóm cần điều tra. Nhưng:

- Hash, nonce, identifier và cơ chế chứng thực hợp lệ cũng có entropy cao.
- Tên được tạo có quy luật vẫn có thể chứa dữ liệu, nên entropy thấp không bảo đảm an toàn.
- Kết quả bị ảnh hưởng bởi độ dài chuỗi và cách tiền xử lý ký tự.
- Không nên lưu hoặc xuất những phần QNAME nghi chứa dữ liệu bí mật khi chỉ cần thống kê.

Một **model/anomaly score** chỉ phù hợp khi có phép đo false positive và quy trình reviewer xác minh sự kiện; score không phải kết luận đã có exfiltration.

## 12. Phân biệt sự kiện thật và false positive

Những tình huống hợp lệ thường gây nhiễu:

| Hành vi hợp lệ | Vì sao giống exfiltration? | Cách kiểm chứng |
|---|---|---|
| **ACME DNS-01 challenge** | Tên TXT có giá trị xác minh khó đọc | Chủ domain, quy trình cấp chứng chỉ, thời điểm triển khai |
| **DKIM/SPF/DMARC** | DNS TXT và label dài, chứa khóa/cấu hình | DNS email policy và chủ dịch vụ |
| **CDN/service discovery** | Nhiều hostname động và CNAME | Danh mục nhà cung cấp, app và traffic thực tế |
| **Ứng dụng telemetry** | Query chứa định danh phiên/thiết bị | Hợp đồng sản phẩm, process, chính sách dữ liệu |
| **Agent update/monitoring** | Lặp truy vấn theo lịch hoặc nhiều đích | Log triển khai, EDR process, lịch cập nhật |
| **Kubernetes/service mesh** | SRV/A/AAAA và truy vấn nội bộ đa dạng | Cluster DNS, namespaces, workload owner |
| **Sai search suffix** | Nhiều NXDOMAIN theo pattern | Cấu hình resolver/OS và tên được tìm |
| **DNS cache lỗi/retry storm** | Tăng query đột biến | Resolver health, TTL, timeout và network path |

Phân tích phải gồm **đối chứng với baseline hợp lệ**. Nếu một quy tắc chỉ dựa vào độ dài mà chặn dịch vụ cấp chứng chỉ hoặc DKIM, hệ thống có thể bị ảnh hưởng nghiệp vụ trong khi không có bằng chứng tấn công.

### Phân biệt false alert và false block

- **False alert:** detector gắn nhãn đáng ngờ cho truy vấn hợp lệ nhưng chỉ ghi cảnh báo.
- **False block:** policy thực sự từ chối DNS hợp lệ, khiến ứng dụng không phân giải hoặc không kết nối được.
- **False negative:** hành vi exfiltration không bị phát hiện; có thể vẫn bị chặn bởi lớp khác.

Đo chất lượng kiểm soát phải báo cáo **cả độ chính xác phát hiện và tác động availability**.

## 13. Quyền riêng tư và bảo quản DNS telemetry

DNS log có thể tiết lộ thói quen truy cập, dịch vụ y tế/tài chính hoặc những chuỗi dữ liệu được đưa vào tên miền. Với nghi ngờ exfiltration, **QNAME tự nó có thể chứa thông tin nhạy cảm**. Đội phòng thủ cần:

1. Thu thập **mức dữ liệu tối thiểu** phục vụ detection và điều tra.
2. Kiểm soát quyền xem full QNAME và nội dung có nguy cơ chứa dữ liệu bí mật.
3. Áp retention theo nhu cầu, nghĩa vụ và chính sách tổ chức; tránh lưu mọi truy vấn vô thời hạn.
4. Che hoặc hạn chế xuất những đoạn tên bị nghi chứa thông tin nhạy cảm trong ticket, email và dashboard.
5. Đồng bộ thời gian, sử dụng timezone rõ ràng và ghi lại thay đổi cấu hình logging.
6. Duy trì audit trail cho thao tác truy vấn log và xử lý bằng chứng khi có sự cố.
7. Chỉ chuyển dữ liệu đến hệ thống bên ngoài/nhà cung cấp khi được phép và đã đánh giá yêu cầu bảo vệ dữ liệu.

**Quan sát tốt không nhất thiết đồng nghĩa lưu toàn bộ payload.** Trong giai đoạn phát hiện ban đầu, số tên duy nhất, độ dài, phân phối loại bản ghi và endpoint identity có thể đủ để ưu tiên kiểm tra; việc xem QNAME cụ thể nên thực hiện theo quyền và nhu cầu điều tra.

## 14. Quy trình ứng cứu nghi ngờ DNS exfiltration

### Bước 1. Xác minh sự kiện và phạm vi

- Ghi thời gian, client IP, hostname/asset identity, resolver, domain, query count, QTYPE/RCODE và alert source.
- Kiểm tra asset inventory: máy văn phòng, server, IoT, container hay VPN client?
- Xác định dữ liệu này đến từ **stub, recursive resolver, network sensor hay EDR**, vì mỗi nguồn thấy khác nhau.
- Phân biệt **một hoạt động mới của ứng dụng hợp lệ** với nhiều tín hiệu bất thường.

### Bước 2. Tương quan đa nguồn

- **EDR/host telemetry:** tiến trình nguồn, parent process, executable, user, lịch công việc, thay đổi file.
- **Resolver logs:** QNAME/QTYPE, domain, tốc độ, unique labels, RCODE và upstream decision.
- **Firewall/NDR:** đường egress, NAT, lưu lượng DNS rõ hay DoH/DoT, endpoint tương ứng.
- **Identity/access logs:** tài khoản đang sử dụng, truy cập dữ liệu nhạy cảm, đăng nhập bất thường.
- **Ứng dụng và change management:** triển khai agent, certificate automation, batch workload, cấu hình DNS mới.

Không nên khẳng định tài khoản hoặc thiết bị bị xâm nhập chỉ từ một điểm dữ liệu. Nếu log resolver chỉ ghi địa chỉ NAT của cả mạng, cần mapping chính xác tới endpoint.

### Bước 3. Phân loại và bảo toàn bằng chứng

Tách các khả năng:

1. **BENIGN:** có bằng chứng khớp chức năng đã phê duyệt.
2. **SUSPICIOUS:** nhiều tín hiệu bất thường, chưa chứng minh rò rỉ.
3. **CONFIRMED SECURITY INCIDENT:** có bằng chứng đủ mạnh theo quy trình ứng cứu cho thấy hành vi không được phép.
4. **INCONCLUSIVE:** thiếu telemetry hoặc sai lệch dữ liệu, chưa thể kết luận.

Ghi phạm vi thời gian, mức độ tin cậy, người xác nhận và nguồn bằng chứng. Chỉ giữ log/artefact cần thiết theo chính sách pháp lý và quyền riêng tư.

### Bước 4. Kiềm chế và khắc phục

Tùy mức độ và quyền vận hành:

- Hạn chế egress của **đúng endpoint hoặc workload** khi có đủ căn cứ, tránh chặn toàn bộ DNS doanh nghiệp.
- Chặn/sinkhole domain theo phê duyệt, đánh giá rủi ro domain dùng chung và false positive.
- Cô lập máy bị nghi xâm nhập bằng EDR/NAC nếu chính sách và mức độ sự cố yêu cầu.
- Kiểm tra tài khoản, token, khóa hoặc dữ liệu có thể bị ảnh hưởng và phối hợp owner.
- Khôi phục chính sách resolver, loại bỏ cấu hình bypass, kiểm tra trình duyệt/VPN/cloud DNS.
- Xác minh chức năng hợp lệ vẫn hoạt động và mở rollback nếu mitigation gây lỗi nghiêm trọng.

### Bước 5. Đánh giá tác động và phục hồi

Không tự suy khối lượng dữ liệu rò rỉ chỉ từ số query nhân độ dài QNAME. Tên miền chứa **metadata, header/overhead, ký tự không phải dữ liệu người dùng hoặc dữ liệu đã được lặp**; ngoài ra log có thể không đầy đủ vì cache, mất gói hoặc resolver khác. Đánh giá tác động cần kết hợp bằng chứng endpoint và những hệ thống lưu dữ liệu liên quan.

Sau xử lý, cập nhật detector và inventory, sửa rule quá rộng, dọn ngoại lệ tạm và rà soát đường egress. Ghi kết quả điều tra và việc cần cải thiện mà không công bố dữ liệu nhạy cảm.

## 15. Case study: máy ứng dụng tạo nhiều subdomain lạ

**Bối cảnh giả định:** Một máy chủ ứng dụng thuộc zone có dữ liệu khách hàng được phép hỏi recursive DNS nội bộ. SOC thấy số QNAME duy nhất dưới một domain chưa nằm trong inventory tăng bất thường trong 15 phút. Một số nhãn dài, có độ đa dạng ký tự cao; resolver vẫn trả phản hồi DNS theo cơ chế bình thường.

### Dữ liệu ban đầu

~~~text
Asset:             app-server-07
Client IP:         10.30.20.17
Resolver:          corp-dns-02
Time window:       2026-11-28 10:00-10:15 +07:00
Observation:       unique subdomains tăng so với baseline
Domain:            unknown-zone.example.test (giả định)
QTYPE:             A / AAAA
RCODE:             phần lớn NOERROR
EDR process:       chưa được đối chiếu
Security verdict:  SUSPICIOUS, chưa xác nhận exfiltration
~~~

**Điều có thể kết luận ngay:** có hoạt động phân giải **bất thường theo baseline** của máy. **Điều chưa thể kết luận:** có dữ liệu bí mật đi ra, domain do kẻ tấn công kiểm soát hoặc máy đã bị xâm nhập.

### Các giả thuyết cạnh tranh

- **Bản cập nhật hợp lệ:** ứng dụng mới có tính năng telemetry/service discovery với tên động.
- **Lỗi phần mềm:** retry và cache miss tạo nhiều query trùng chức năng nhưng khác identifier.
- **Điều kiện sai về owner domain:** domain thuộc đối tác đã được phê duyệt nhưng inventory chưa cập nhật.
- **Tiến trình không được phép:** phần mềm lạ tạo hoạt động DNS bất thường.
- **Rò rỉ dữ liệu:** có bằng chứng bổ sung liên kết dữ liệu/tiến trình và tên được gửi tới DNS bên ngoài.

### Quy trình xử lý

1. Xác minh thiết bị, role, chủ ứng dụng, lịch triển khai, sự kiện thay đổi cấu hình.
2. So sánh số QNAME duy nhất, độ dài và QTYPE/RCODE với **baseline của chính nhóm server tương ứng**, không so bừa với laptop.
3. Xác minh ownership domain và đường authoritative resolution, chú ý resolver cache và forwarder.
4. Tìm tiến trình tạo query qua host/EDR telemetry; kiểm tra hoạt động truy cập dữ liệu nhạy cảm.
5. Đối chiếu flow ở egress, DNS được mã hóa, IPv6 và những đường không qua resolver quản lý.
6. Nếu đủ căn cứ sự cố, thực hiện cách ly có kiểm soát và phối hợp incident response; nếu là telemetry hợp lệ, cập nhật inventory và hiệu chỉnh detector.
7. Sau thay đổi, kiểm thử cả **DNS hợp lệ** và **detection** để tránh chặn nhầm dịch vụ ứng dụng.

### Câu hỏi tình huống

1. Vì sao **NOERROR** không loại trừ nguy cơ DNS exfiltration?
2. Vì sao nhiều subdomain duy nhất đáng chú ý hơn chỉ số query volume trong một số trường hợp?
3. Khi resolver chỉ thấy IP NAT, phải bổ sung những nguồn log nào để xác định endpoint?
4. Nếu domain là dịch vụ telemetry hợp lệ, nên cập nhật detector ra sao mà không cho phép mọi domain tương tự?
5. Trường hợp nào cần cô lập endpoint ngay, và trường hợp nào nên tiếp tục thu thập dữ liệu trước?

## 16. Bài thực hành phân tích an toàn trong lab

Mục tiêu bài thực hành là **đọc log DNS giả lập** để phân loại hành vi, không tạo kênh vận chuyển dữ liệu hoặc gửi nội dung thật ra hệ thống ngoài.

### Chuẩn bị

Sử dụng bộ log tổng hợp trong bài hoặc log được tổ chức cấp quyền đọc. Không cần truy vấn DNS hàng loạt, không cần cài phần mềm tunneling và không sử dụng tài liệu có dữ liệu thật. Nếu dùng log có nguồn gốc production, áp dụng quy định ẩn danh, phân quyền và retention.

### Mẫu dữ liệu quan sát

| Client | Parent domain | Số query (giả định) | QNAME duy nhất | Độ dài thường gặp | Diễn giải ban đầu |
|---|---|---:|---:|---|---|
| Laptop nhân viên A | mail-service.example.test | 120 | 6 | Ngắn | Có thể là dịch vụ mail hợp lệ |
| Server B | telemetry-lab.example.test | 140 | 132 | Trung bình đến dài | Cần kiểm tra phần mềm telemetry và owner |
| Endpoint C | update-service.example.test | 75 | 8 | Ngắn đến trung bình | Có thể do vòng kiểm tra cập nhật |
| Server D | unknown-zone.example.test | 260 | 247 | Nhiều nhãn dài | Ưu tiên đối chiếu tiến trình và egress |
| DNS resolver trung tâm | Nhiều domain | 100.000 | 42.000 | Hỗn hợp | Không so trực tiếp với một endpoint |

**Tất cả số liệu đều giả định.** Bảng chỉ giúp luyện tập đánh giá theo baseline và vai trò tài sản.

### Nhiệm vụ phân tích

1. Tính tỷ lệ **QNAME duy nhất / tổng query** cho từng hàng; so sánh với loại tài sản.
2. Chọn hai trường hợp cần điều tra trước, giải thích bằng **nhiều tín hiệu** chứ không chỉ dựa vào tỷ lệ.
3. Liệt kê bằng chứng cần thu từ **EDR, resolver, firewall, inventory và app owner**.
4. Giải thích vì sao không thể tự chặn tất cả tên dài hoặc domain mới xuất hiện.
5. Viết ba tiêu chí giúp xác nhận **một sự kiện benign** và ba tiêu chí cho biết cần chuyển xử lý sự cố.
6. Đề xuất cách ghi log phù hợp mà không công bố QNAME nghi chứa dữ liệu bí mật.

### Biên bản kiểm tra

~~~text
Investigation ID:   DNS-EXFIL-LAB-01
Asset / owner:      [loại host, chủ hệ thống]
Time range:         [timestamp + timezone]
Resolver/source:    [nguồn log]
Parent domain:      [giá trị đã kiểm tra, che nếu nhạy cảm]
Query count:        [số liệu]
Unique QNAMEs:      [số liệu]
QTYPE / RCODE:      [phân phối]
Baseline context:   [nhóm tài sản, lịch hoạt động]
Endpoint evidence:  [tiến trình, user, change]
Egress evidence:    [route, policy, NAT nếu có]
Assessment:         [BENIGN / SUSPICIOUS / CONFIRMED / INCONCLUSIVE]
Next action:        [điều tra, tăng giám sát, containment có phép]
Reviewer:           [người xác nhận]
~~~

**INCONCLUSIVE** là lựa chọn đúng khi không có đủ log để liên kết QNAME với tiến trình hoặc không xác minh được domain ownership. Không nên báo CONFIRMED chỉ vì domain chưa có trong danh sách nội bộ.

## 17. Đánh giá chất lượng detection và mức bao phủ

| Chỉ số | Ý nghĩa | Hạn chế |
|---|---|---|
| **Resolver visibility coverage** | Tỷ lệ endpoint/workload dùng resolver có log đúng chính sách | Có thể bỏ qua truy vấn qua DoH, VPN hoặc resolver khác |
| **Client attribution rate** | Tỷ lệ sự kiện gắn được với endpoint/owner thay vì IP NAT chung | DHCP, IPv6, cloud scaling, CGNAT có thể làm sai mapping |
| **Alert precision** | TP / (TP + FP) trên tập đã có nhãn | Nhãn của rule tự động không phải ground truth |
| **False Positive Rate** | FP / (FP + TN) trên các trường hợp hợp lệ được đánh giá | Production khó có đủ TN chắc chắn |
| **Detection latency** | Thời gian từ hoạt động bất thường tới alert | Log ingest có thể chậm; phát hiện quá muộn làm giảm giá trị |
| **Mean time to triage** | Thời gian có được kết luận điều tra ban đầu | Phụ thuộc ứng dụng/endpoint owner và nguồn log |
| **False block / DNS availability** | Tỷ lệ truy vấn hợp lệ bị policy chặn, lỗi phân giải, timeout | Chính sách quá rộng có thể ngắt ứng dụng quan trọng |
| **Policy bypass observations** | Những kết nối DNS ngoài resolver được quản lý bị phát hiện | Không phải mọi HTTPS có thể được phân loại là DoH |

Nên đặt mục tiêu trước tiên cho **tài sản quan trọng, dữ liệu nhạy cảm, mạng quản trị và workload có quyền truy cập rộng**, sau đó mở rộng coverage theo rủi ro. Không lấy con số “100% DNS visible” từ một điểm giám sát duy nhất khi hạ tầng có VPN, cloud và DNS mã hóa.

### Kiểm thử hồi quy cho chính sách DNS

| Test ID | Kịch bản được phép | Kỳ vọng |
|---|---|---|
| DNS-01 | Laptop sử dụng resolver nội bộ và truy cập dịch vụ nghiệp vụ | Phân giải thành công; có log cần thiết |
| DNS-02 | Máy thuộc mạng Guest thử dùng DNS theo chính sách đã phê duyệt | Không được truy cập resolver nhạy cảm ngoài quyền |
| DNS-03 | Client được quản lý cố sử dụng resolver ngoài danh mục trong bài kiểm thử policy | Chính sách egress áp dụng đúng; log ghi nhận |
| DNS-04 | Truy vấn DNS hợp lệ với TXT/SRV hoặc tên dài | Không bị block chỉ vì hình dạng dữ liệu |
| DNS-05 | Thiết bị IPv6 hoặc kết nối VPN | Cùng nguyên tắc chính sách và khả năng attribution |
| DNS-06 | Mất một resolver trong bài diễn tập HA | Chức năng phân giải vẫn khả dụng theo thiết kế |
| DNS-07 | Sự kiện log tổng hợp có nhiều QNAME duy nhất | Detector tạo cảnh báo đúng rule; chưa tự kết luận exfiltration |
| DNS-08 | Domain được phê duyệt bị false positive | Có quy trình ngoại lệ, xác minh và rollback |

Chỉ kiểm thử trong môi trường **được cấp quyền**, ưu tiên cấu hình lab và dữ liệu tổng hợp. Không tạo traffic có dữ liệu nhạy cảm, không thử vượt các kiểm soát trên hệ thống không thuộc phạm vi quản trị.

## 18. Những hiểu nhầm phổ biến

| Nhận định sai | Vì sao không đúng? | Cách tiếp cận |
|---|---|---|
| “Mọi QNAME dài là dữ liệu bị rò rỉ” | Nhiều dịch vụ hợp lệ dùng tên dài hoặc identifier | Kết hợp domain owner, process và baseline |
| “NXDOMAIN cao chứng minh DNS exfil” | DNS lỗi cấu hình/retry tạo nhiều NXDOMAIN | Phân tích thêm uniqueness, endpoint và ngữ cảnh |
| “NXDOMAIN thấp thì không thể có exfil” | Phản hồi NOERROR vẫn có thể đi cùng hành vi bất thường | Không dùng RCODE làm tiêu chí duy nhất |
| “TXT là loại record nguy hiểm cần chặn hết” | SPF/DKIM/DMARC/ACME dùng TXT hợp lệ | Policy theo ứng dụng và nhu cầu |
| “Bật DNSSEC là chặn được rò rỉ dữ liệu” | DNSSEC xác thực dữ liệu DNS được ký, không ngăn gửi QNAME | Thêm egress control và behavior detection |
| “Chặn UDP/53 là đủ” | Có TCP/53, DNS mã hóa và VPN/cloud paths | Kiểm kê mọi đường resolver hợp lệ |
| “Chặn mọi HTTPS giải quyết DoH” | HTTPS là giao thức nghiệp vụ cốt lõi | Quản lý resolver/client và telemetry theo quyền |
| “Không có DNS log nghĩa không có truy vấn” | Cache, DoH, sensor placement và log gaps tồn tại | Phối hợp EDR, flow, resolver và app |
| “Entropy cao luôn là mã độc” | Hash, nonce và ACME verification hợp lệ có entropy cao | Dùng đa tín hiệu và kiểm chứng chủ dịch vụ |
| “Có DNS exfil thì chắc chắn đo được số byte bí mật” | Log có overhead, cache, packet gaps và retry | Kết hợp bằng chứng về dữ liệu ở endpoint |
| “Chặn domain nghi ngờ là không ảnh hưởng nghiệp vụ” | Domain dùng chung có thể phục vụ chức năng hợp lệ | Đánh giá owner, scope, SLO và rollback |
| “Một sensor ngoài Internet edge nhìn thấy toàn bộ DNS” | East–west, VPN, cloud hoặc encrypted DNS có thể không đi qua | Xác minh route và visibility coverage |

## 19. Câu hỏi tự kiểm tra

1. DNS exfiltration khác DNS tunneling và DNS-based C2 ở mục tiêu chính như thế nào?
2. Vì sao một recursive resolver có thể không chuyển mọi truy vấn của client tới authoritative DNS?
3. Những trường nào của câu hỏi DNS hữu ích cho phân tích và vì sao QNAME một mình không đủ kết luận?
4. Hai lý do hợp lệ khiến một hệ thống tạo nhiều QNAME duy nhất dưới một domain là gì?
5. Vì sao NXDOMAIN cao không chứng minh exfiltration, còn NXDOMAIN thấp không loại trừ nó?
6. DNSSEC bảo vệ điều gì và vì sao không thay thế chính sách egress?
7. DoH/DoT/DoQ làm thay đổi nguồn telemetry của NIDS như thế nào?
8. Khi máy gửi DNS qua VPN split tunnel, cần kiểm tra những điểm nào để tìm đúng resolver?
9. Vì sao tính entropy theo label không nên dùng làm tín hiệu cô lập endpoint tự động?
10. Những nguồn log nào giúp gắn một query với **tiến trình** thay vì chỉ IP NAT?
11. Một đợt chặn domain nghi ngờ gây mất phân giải DNS cho ứng dụng hợp lệ. Cần xử lý false block và rollback ra sao?
12. Trong case study app-server-07, những bằng chứng nào cần có trước khi gọi là sự cố exfiltration đã xác nhận?
13. Vì sao không thể tính chính xác lượng dữ liệu lộ chỉ bằng số lượng query nhân độ dài QNAME?
14. Hãy đề xuất một ma trận kiểm thử cho DNS resolver policy bao gồm IPv6, VPN, TXT hợp lệ, DNS mã hóa và HA.

## 20. Ghi nhớ trọng tâm

**DNS exfiltration** là việc lợi dụng cơ chế DNS để đưa thông tin qua ranh giới mạng trái với chính sách. Việc DNS được phép trong nhiều môi trường, cộng với cache, nhiều tầng resolver và các đường DNS mã hóa, khiến rủi ro khó phát hiện chỉ bằng một thiết bị trên đường truyền. **QNAME dài, entropy cao, nhiều subdomain duy nhất, query rate lớn hoặc NXDOMAIN tăng** đều là những tín hiệu hữu ích, nhưng **không phải bằng chứng độc lập** cho thấy dữ liệu đã bị rò rỉ.

Phòng thủ hiệu quả đòi hỏi **resolver được quản lý, kiểm soát DNS egress theo quyền tối thiểu, phân đoạn mạng, EDR/NAC, firewall/NDR, log DNS và SIEM correlation**. Đối với DoH/DoT/DoQ, cần nhận thức rõ blind spot và ưu tiên telemetry từ điểm kiểm soát hợp pháp, không chặn toàn bộ HTTPS hoặc phá mã hóa. Khi điều tra, hãy giữ riêng **sự kiện quan sát được, giả thuyết và kết luận có bằng chứng**, đồng thời bảo vệ QNAME có thể chứa dữ liệu nhạy cảm, giảm false positive và xác minh tính sẵn sàng của các dịch vụ DNS hợp lệ.
