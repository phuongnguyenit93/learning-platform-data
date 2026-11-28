# Phân tích DNS tunneling

## 1. Mục tiêu và phạm vi điều tra

**DNS tunneling** là kỹ thuật đưa dữ liệu hoặc thông điệp điều khiển vào các trường của giao thức DNS để truyền qua hạ tầng phân giải tên miền. Trong một số trường hợp, kỹ thuật này được dùng cho kết nối hợp lệ hoặc kiểm thử được cấp phép; trong sự cố an ninh, nó có thể bị lạm dụng làm kênh **command-and-control (C2)**, nhận lệnh, chuyển dữ liệu ra ngoài hoặc vượt qua chính sách truy cập mạng. Dấu hiệu DNS tunneling vì vậy cần được điều tra trong ngữ cảnh, không được kết luận chỉ từ một tên miền dài hay một cảnh báo IDS/IPS.

Trong chương **Điều tra số trên mạng** của module **SECURITY_NETWORK_SECURITY**, việc phân tích DNS tunneling kết hợp kiến thức về DNS, luồng mạng, firewall, phân đoạn VLAN, VPN, IDS/IPS, xác thực kết nối, hệ thống không dây và mạng đám mây. Trọng tâm của bài là **thu thập và đối chiếu chứng cứ mạng**, kiểm tra các giả thuyết, truy nguyên tài sản liên quan, đánh giá nguy cơ và đưa ra hành động ứng phó có kiểm chứng.

Sau khi học xong, người học có thể:

1. Mô tả luồng phân giải DNS bình thường và vị trí dữ liệu bất thường có thể xuất hiện trong truy vấn/phản hồi.
2. Phân biệt dấu hiệu của DNS tunneling với DNS hợp lệ có tên miền ngẫu nhiên, DGA, cập nhật phần mềm, dịch vụ CDN và lỗi cấu hình.
3. Trích xuất, phân tích và tương quan **PCAP**, DNS resolver log, firewall/flow log, DHCP/IPAM, IDS/NDR, EDR và thông tin danh tính.
4. Tính các chỉ số hữu ích: số truy vấn theo thời gian, độ dài QNAME, tỷ lệ tên miền duy nhất, entropy nhãn, loại bản ghi, RCODE, tỷ lệ byte và nhịp truy vấn.
5. Thiết kế quy trình điều tra từ cảnh báo đến xác minh, khoanh vùng, bảo toàn chứng cứ và báo cáo với mức độ tin cậy phù hợp.
6. Đề xuất phòng thủ như kiểm soát DNS egress, giám sát resolver, phân đoạn mạng, phát hiện bất thường và xử lý qua hệ thống quản lý sự cố.

**Nguyên tắc cốt lõi:** dữ liệu “có hình dạng bất thường” là tín hiệu để đặt câu hỏi. Chỉ khi nhiều nguồn độc lập củng cố lẫn nhau mới nên nâng mức kết luận từ **nghi vấn** thành **sự kiện đã xác minh**.

## 2. Luồng DNS bình thường và vị trí có thể bị lạm dụng

### 2.1. Vai trò của các thành phần DNS

Khi một máy trạm muốn truy cập một dịch vụ bằng tên miền, nó thường gửi truy vấn từ **stub resolver** của hệ điều hành đến **recursive resolver** được cấu hình qua DHCP, VPN hoặc chính sách thiết bị. Recursive resolver kiểm tra cache, hỏi hệ thống DNS có thẩm quyền khi cần, rồi trả kết quả cho client.

~~~mermaid
flowchart LR
    C["Thiết bị đầu cuối<br/>stub resolver"] -->|DNS query| R["Recursive resolver<br/>nội bộ"]
    R -->|Cache miss| A["Hệ thống DNS<br/>authoritative"]
    A -->|DNS response| R
    R -->|DNS response| C
    R -.-> L["DNS query logs<br/>security analytics"]
    C -.-> E["EDR / process log"]
    R -.-> F["Firewall / NetFlow<br/>giám sát egress"]
~~~

- **QNAME (Query Name):** tên được hỏi, ví dụ \`www.lab.example.\`.
- **QTYPE:** loại bản ghi được yêu cầu, như \`A\`, \`AAAA\`, \`CNAME\`, \`TXT\`, \`MX\`; mỗi loại có mục đích hợp lệ.
- **RCODE:** trạng thái trả lời như \`NOERROR\`, \`NXDOMAIN\`, \`SERVFAIL\`; \`NOERROR\` vẫn có thể không chứa bản ghi trả lời cho loại được hỏi.
- **TTL:** thời gian cache được chỉ định cho bản ghi; caching và negative caching ảnh hưởng số lần truy vấn quan sát được ở mỗi cảm biến.
- **Truyền tải:** DNS cổ điển thường dùng UDP/53, có thể dùng TCP/53; DNS mã hóa dùng các cơ chế như **DoT** (thường TCP/853) và **DoH** (qua HTTPS, có thể dùng HTTP/2 hoặc HTTP/3). Cổng hay giao thức truyền tải không đủ để kết luận nội dung.

Một nhãn DNS (phần giữa hai dấu chấm) dài tối đa **63 octet ở dạng wire**; tên DNS đầy đủ dài tối đa **255 octet khi mã hóa trên wire**, tính cả dấu độ dài nhãn và nhãn gốc. Độ dài hiển thị phụ thuộc cách biểu diễn, ví dụ tên Unicode cần chuẩn hóa IDNA trước khi so sánh theo byte.

### 2.2. Hai hướng truyền dữ liệu có thể xuất hiện

Trong kịch bản lạm dụng DNS, dữ liệu có thể nằm ở các vị trí:

| Hướng | Vị trí quan sát | Dấu hiệu khả nghi có thể gặp | Giới hạn suy luận |
|---|---|---|---|
| Client → hạ tầng DNS | Các nhãn bên trái của QNAME | Nhãn dài, ký tự có phân bố gần ngẫu nhiên, nhiều QNAME khác nhau dưới một zone | CDN, mã nhận dạng ứng dụng và hệ thống đo lường cũng có thể sinh tên tương tự |
| DNS → client | Trường trả lời, ví dụ TXT hoặc dữ liệu DNS hợp lệ khác | Phản hồi dài hoặc lặp lại nhiều lần theo một host/zone | TXT được dùng hợp lệ cho xác minh domain, SPF/DKIM và nhiều dịch vụ |
| Trao đổi hai chiều | Chuỗi truy vấn/phản hồi liên tiếp | Nhịp trao đổi đều, nhiều QNAME không lặp, dữ liệu trả lời thay đổi | Cần tương quan với tiến trình và mục đích ứng dụng để xác định bản chất |

Với DNS recursion thông thường, client không nhất thiết kết nối trực tiếp đến authoritative nameserver của zone đáng ngờ. **Resolver nội bộ có thể là trung gian**: log trên endpoint hoặc tại resolver cho biết host nào hỏi, còn log từ cổng Internet có thể chỉ thấy địa chỉ của resolver khi nó hỏi ra ngoài. Không gán IP resolver thành “máy bị xâm nhập”.

### 2.3. Tín hiệu tunneling khác gì một tên miền lạ?

Một số chiến dịch sử dụng tên miền ngẫu nhiên theo thuật toán (**DGA**) để tìm điểm điều khiển: thường thấy nhiều domain khác nhau, nhiều truy vấn thất bại. DNS tunneling lại thường tạo **nhiều subdomain thay đổi dưới một hoặc một nhóm domain/zone** để vận chuyển các phần thông điệp. Hai hiện tượng có thể cùng xuất hiện nhưng không đồng nghĩa.

Ví dụ chỉ để quan sát cấu trúc (tên miền \`.example\` dành cho tài liệu):

~~~text
portal.lab.example.                                  # Truy vấn ứng dụng thông thường
status.corp.lab.example.                             # Truy vấn nội bộ thường gặp
m7r2k9q4c6t8v3p5n2w7d9f4h6s1x8a3.case-lab.example. # Nhãn có cấu trúc khó diễn giải
p8f5k2r9v4m7h6s3c1w9q2n8t5d4a6b7.case-lab.example. # Thay đổi giữa các lần hỏi
~~~

Hai dòng cuối chưa chứng minh được có dữ liệu được mã hóa, có phản hồi điều khiển hay có hành vi đánh cắp dữ liệu. Tác vụ kiểm thử, bộ định danh phiên, telemetry hợp lệ hoặc cơ chế bảo mật riêng cũng có thể tạo chuỗi khó đọc.

## 3. Mô hình đe dọa và câu hỏi điều tra

Trước khi tìm chỉ báo, đặt câu hỏi về **tài sản**, **đường truyền**, **dữ liệu**, **đối tượng điều khiển** và **khả năng quan sát**.

~~~mermaid
flowchart TD
    A["DNS anomaly alert"] --> B{"Xác định được<br/>nguồn phát?"}
    B -->|Chưa| C["Kiểm tra điểm capture,<br/>NAT, DHCP, resolver"]
    B -->|Rồi| D["Phân tích đặc điểm DNS<br/>theo client + zone + thời gian"]
    C --> D
    D --> E{"Có giải thích<br/>nghiệp vụ hợp lý?"}
    E -->|Có| F["Đối chiếu app/EDR/<br/>thay đổi cấu hình"]
    E -->|Chưa| G["Tìm tín hiệu khác:<br/>EDR, egress, lịch sử, IOC"]
    F --> H{"Bằng chứng<br/>nhất quán?"}
    G --> H
    H -->|Chưa rõ| I["Ghi khoảng trống,<br/>thu thêm chứng cứ"]
    H -->|Nguy cơ rõ| J["Leo thang, khoanh vùng,<br/>bảo toàn và ứng phó"]
    I --> D
~~~

Các câu hỏi chính:

- **Ai tạo truy vấn?** IP nguồn ở thời điểm đó có ánh xạ đến một thiết bị cụ thể qua DHCP lease, NAC, VPN hoặc cloud asset inventory không?
- **Truy vấn đi đâu?** Qua resolver được phê duyệt hay truy cập DNS ngoài trực tiếp? Có proxy/NAT/VPN làm đổi IP quan sát?
- **Chuyện gì bất thường?** Tần suất, độ dài tên, tính duy nhất, đặc trưng ký tự, loại query, RCODE, phản hồi, khung giờ và khác biệt baseline.
- **Có dữ liệu từ host không?** EDR ghi nhận tiến trình nào phát sinh truy vấn, có hoạt động file/network bất thường đi kèm hay không?
- **Có mục đích nghiệp vụ không?** Zone thuộc dịch vụ nào, chủ dịch vụ xác nhận gì, có thay đổi phiên bản hoặc cấu hình đúng thời điểm không?
- **Mức ảnh hưởng là gì?** Host, subnet/VLAN, tài khoản, dữ liệu quan trọng và các tài sản khác có cùng hành vi.
- **Độ chắc chắn tới đâu?** Mỗi kết luận dựa trên bản ghi cụ thể nào, dữ liệu còn thiếu gì, sự kiện nào có thể bác bỏ giả thuyết?

Một nhóm điều tra nên duy trì bảng gồm **Fact / Hypothesis / Unknown / Next action**. Điều này giảm nguy cơ nhầm “nhãn ngẫu nhiên” thành “đã có exfiltration”.

## 4. Dữ liệu cần thu thập và những gì mỗi nguồn chứng minh được

| Nguồn | Có thể biết | Điều không thể kết luận chỉ từ nguồn đó |
|---|---|---|
| DNS resolver query log | Client hỏi QNAME nào, QTYPE, timestamp, RCODE, resolver xử lý | Tiến trình trên client hoặc dữ liệu gốc trước khi đưa vào QNAME |
| Passive DNS / authoritative log | Zone nào nhận nhiều truy vấn, QNAME và response tương ứng | Host cuối trong mạng nếu log chỉ thấy resolver trung gian |
| PCAP tại client/sensor | Gói DNS quan sát được, thời gian, transaction ID, QNAME, phản hồi nếu không mã hóa | Không thấy gói không có nghĩa lưu lượng không tồn tại; có thể thiếu do vị trí capture |
| Firewall / proxy / NetFlow / IPFIX | Kết nối, cổng, lưu lượng, quyết định ALLOW/DENY, NAT và xu hướng | Payload trong DoH/TLS hoặc nội dung exfiltration |
| IDS/IPS / NDR | Quy tắc hoặc hành vi gây cảnh báo, mức độ nghi ngờ, metadata | Một signature không tự chứng minh xâm nhập thành công |
| DHCP / IPAM / NAC / 802.1X | Lịch sử IP–MAC–switch port–user hoặc nhận diện thiết bị mạng | Danh tính người dùng tuyệt đối khi thiết bị/tài khoản dùng chung |
| EDR / endpoint logs | Tiến trình, đường dẫn, user context, thao tác file và kết nối trên máy | Không phải máy nào cũng có agent, logs có thể thiếu hoặc bị trì hoãn |
| VPN / identity / cloud audit | Phiên kết nối, tài khoản, VPC/VNet workload, thay đổi cấu hình | Không xác định chính xác hành vi ứng dụng nếu thiếu log host |
| DNS policy/config logs | Ai đổi resolver, chính sách egress, DNS forwarding, conditional forwarding | Không chứng minh một truy vấn dài là ác ý |

**Chọn điểm quan sát phù hợp:**

- **Trước recursive resolver:** tốt để gắn truy vấn với địa chỉ client, nhưng có thể bỏ lỡ hoạt động đi thẳng ra resolver ngoài.
- **Sau recursive resolver:** tốt để quan sát câu hỏi mà resolver phải hỏi ra Internet, nhưng dễ mất định danh client và chịu ảnh hưởng cache.
- **Tại endpoint:** cung cấp tiến trình gốc nhưng đòi quyền và log agent.
- **Tại cloud/VPN/NAT:** phải đọc kèm mapping phiên, flow và route. Trong mạng không dây, đối chiếu Wi-Fi controller/NAC với DHCP vì roaming làm thay đổi điểm truy cập.

**DNS mã hóa:** nếu client dùng DoH/DoT, sensor mạng thông thường không đọc được QNAME chỉ bằng việc nhìn luồng TLS. Không tự diễn giải lưu lượng HTTPS đến resolver là DNS tunneling. Cần sử dụng DNS log ở resolver được quản lý, nhật ký endpoint hoặc các nguồn có quyền truy cập hợp pháp; mọi giải mã/kiểm tra sâu phải tuân thủ chính sách tổ chức.

## 5. Các chỉ báo phân tích (features)

Các chỉ số nên được tính trong **cửa sổ thời gian** rõ ràng, nhóm theo **client + zone/domain + điểm quan sát**, so sánh với baseline cùng loại thiết bị và giai đoạn hoạt động.

### 5.1. Các chỉ số cơ bản

| Chỉ số | Cách tính / diễn giải | Cảnh báo diễn giải sai |
|---|---|---|
| Query rate | Số truy vấn trong mỗi 1/5/15 phút theo client, zone và QTYPE | Một resolver xử lý hàng nghìn máy không so được với một endpoint |
| Distinct QNAME ratio | \`COUNT(DISTINCT qname) / COUNT(*)\` trong cửa sổ | Có thể cao với cache-busting, dịch vụ quảng cáo hoặc CDN |
| QNAME length | Phân vị p50/p90/p99 của độ dài QNAME; đồng thời đo nhãn dài nhất | Tên dài thường gặp ở DKIM, TXT verification, CDN hoặc IDN |
| Character entropy | Shannon entropy theo nhãn/suffix, đơn vị bit/ký tự | Tên ngẫu nhiên hợp lệ cũng entropy cao; mẫu ngắn gây nhiễu |
| NXDOMAIN ratio | \`count(RCODE=3) / count(responses)\` | Tunnel thành công có thể trả NOERROR; NXDOMAIN không phải dấu hiệu bắt buộc |
| Query-type mix | Phần trăm A/AAAA/TXT/CNAME và chuyển đổi theo thời gian | TXT hay A không tự động đáng ngờ |
| Response-size trend | Phân phối kích thước DNS response so với request, số answer và RCODE | EDNS(0), DNSSEC, truncation và retry làm thay đổi kích thước |
| Burst / periodicity | Các cụm truy vấn liên tục hoặc nhịp đều theo thiết bị | Monitoring, heartbeat, cập nhật phần mềm có thể có nhịp định kỳ |
| Rare destination / zone | Mức phổ biến của zone trong tổ chức; first-seen timestamp | Domain mới được phép triển khai có thể rất hiếm |
| Policy deviation | Client dùng DNS ngoài quy định, đường egress mới, rule mới | Có thể là DNS failover hoặc thay đổi cấu hình có phê duyệt |

Chỉ số \`distinct ratio\` phải chỉ rõ **chuẩn hóa tên miền**: DNS không phân biệt chữ hoa/chữ thường; loại bỏ dấu chấm kết thúc khi cần; chuyển IDNA nhất quán; phân biệt trùng lặp câu hỏi do retransmission và các truy vấn thật sự mới.

### 5.2. Shannon entropy dùng đúng cách

Với chuỗi ký tự \`s\`, tần suất tương đối của mỗi ký tự \`p(c)\`, entropy là:

\[
H(s)=-\sum_{c \in s} p(c)\log_2 p(c).
\]

Đơn vị là **bit trên mỗi ký tự** cho phân bố ký tự trong chuỗi. Các nhãn dài có ký tự phân bố gần đều thường có entropy cao hơn tên đọc được bằng ngôn ngữ tự nhiên; tuy nhiên, entropy **không phát hiện được mọi kiểu mã hóa** và không xác định được mục đích của dữ liệu.

Những trường hợp dễ gây false positive:

- Chuỗi hash/version, ID phiên, content-addressed storage và một số hostname CDN.
- Tên miền do dịch vụ bảo mật sinh ngẫu nhiên để đo lường hoặc chống tracking.
- Tên miền quốc tế được biểu diễn dưới dạng Punycode (\`xn--...\`).
- Các nhãn rất ngắn làm phép đo entropy mất ổn định.
- Các tên chứa ký tự giống mã hóa nhưng thực chất là mã định danh nghiệp vụ.

Nên so **entropy trên nhãn biến đổi** (nhãn bên trái zone đang xét), sau khi chuẩn hóa, thay vì entropy toàn tên gồm zone cố định. Có thể dùng baseline theo ứng dụng và đo cả tỷ lệ nhãn dài để tránh chấm điểm quá nặng một tên miền đơn lẻ.

### 5.3. Tương quan nhiều tín hiệu

Một giả thuyết cần ưu tiên điều tra hơn khi **đồng thời** thấy các tín hiệu như:

1. Host vốn chỉ dùng resolver nội bộ bỗng gửi nhiều truy vấn tới zone lạ.
2. Nhiều QNAME có nhãn dài và thay đổi liên tục, distinct ratio vượt baseline.
3. Truy vấn duy trì theo chu kỳ bất thường, tập trung dưới cùng zone.
4. Firewall/flow và PCAP xác nhận lưu lượng đã đi qua, không phải chỉ có alert thử nghiệm.
5. EDR ghi nhận tiến trình chưa được công nhận hoặc tác vụ lạ phát sinh truy vấn.
6. Chủ ứng dụng không xác nhận domain hoặc không có thay đổi hệ thống giải thích hành vi.

Không có ngưỡng “entropy > X” hoặc “hơn Y truy vấn/phút” phù hợp cho mọi mạng. Với tổ chức lớn, dùng rule có bước **lọc dịch vụ hợp lệ** và quy tắc nâng cấp cảnh báo khi nhiều nguồn cùng phát hiện.

## 6. Quy trình network forensics theo từng bước

### Bước 1 — Tiếp nhận cảnh báo và giữ ngữ cảnh

Ghi **incident ID**, nguồn cảnh báo, độ ưu tiên, người phụ trách, thời điểm sự kiện và thời điểm nhận cảnh báo (đều ở UTC hoặc có múi giờ rõ ràng). Lưu truy vấn SIEM, phạm vi thời gian, filter được sử dụng và thông tin nơi lưu bản gốc.

Cần xác nhận:

- Cảnh báo áp dụng cho host nào, hay là DNS resolver tập trung?
- Log đến từ sensor nào, có lọc TCP/UDP 53, có hỗ trợ DoH/DoT hay không?
- Dữ liệu có độ trễ ingest, sampling, retention hoặc sai lệch đồng hồ không?
- Có phải alert hợp lệ từ một detector, hay dòng test / dữ liệu diễn tập?

Nếu nghi có sự cố đang tiếp diễn, phối hợp đội phản ứng để đánh giá ngăn chặn sớm mà vẫn bảo toàn được chứng cứ phù hợp.

### Bước 2 — Truy ngược IP đến tài sản theo đúng thời điểm

Đối chiếu log DNS với **DHCP lease lịch sử**, NAT mapping, VPN session, 802.1X/NAC, inventory, IAM và thời điểm host được quan sát. Không dùng thông tin “IP đang cấp cho ai lúc này” để gán trực tiếp cho sự kiện quá khứ.

Ví dụ: nếu PCAP tại gateway chỉ thấy \`10.30.0.53\`, đó có thể là resolver, trong khi query log nội bộ cho biết client là \`10.30.14.25\`. Khi thiết bị dùng DNS forwarding cục bộ, cần theo thêm các hop tương ứng.

### Bước 3 — Tạo timeline bằng nhiều nguồn

Trong timeline phải tách:

- **Event time:** thời điểm gói, truy vấn hoặc thay đổi cấu hình thực sự xảy ra theo nguồn.
- **Observed/ingest time:** thời điểm sensor hoặc SIEM nhận log.
- **Analyst time:** thời điểm người điều tra xem và ghi nhận kết luận.

Ghép các nguồn theo cửa sổ thời gian đủ rộng để bù clock skew, nhưng không tự sửa timestamp trong bản chứng cứ gốc. Timeline tốt sẽ trả lời: **bắt đầu từ khi nào**, **thay đổi hành vi ở đâu**, **đến tài sản nào**, **đã có biện pháp nào** và **biện pháp đó có hiệu lực không**.

### Bước 4 — Phân tích theo client, zone và cửa sổ thời gian

Xây một bảng quan sát: client, resolver, zone, số query, số QNAME riêng biệt, QTYPE, median/max length, entropy, response RCODE, số byte, địa chỉ đích, thời điểm xuất hiện lần đầu/lần cuối.

Lưu ý cách gộp theo zone: hậu tố đăng ký (\`eTLD+1\`) cần **Public Suffix List** để xử lý miền như \`co.uk\`; nhiều tổ chức sở hữu zone nội bộ sâu hơn nên có thể cần cấu hình riêng. Không cắt tên miền bằng cách lấy hai nhãn cuối một cách máy móc.

### Bước 5 — Kiểm chứng qua endpoint và chủ dịch vụ

Đối chiếu tiến trình tạo truy vấn, DNS client configuration, thay đổi gần đây, task/scheduled service, kết nối socket, phần mềm cập nhật và xác nhận của chủ ứng dụng.

Tự hỏi điều gì có thể **bác bỏ giả thuyết DNS tunneling**:

- Hành vi chỉ xuất hiện sau một đợt cập nhật dịch vụ được phê duyệt?
- Mẫu query có tài liệu của nhà cung cấp giải thích, và gói phản hồi đúng kỳ vọng?
- Mọi endpoint cùng bản ứng dụng đều sinh lưu lượng tương tự?
- Phân tích process lineage cho thấy chương trình hợp lệ với chữ ký và bản phát hành xác minh được?

Nếu có bằng chứng phù hợp, ghi “hoạt động hợp lệ/false positive” kèm nguyên nhân, không xóa chứng cứ hay bỏ qua cải tiến detector.

### Bước 6 — Đánh giá ảnh hưởng và quyết định ngăn chặn

Nhóm ứng phó xem xét mức tin cậy, số tài sản liên quan, độ nhạy dữ liệu, khả năng tiếp diễn và ảnh hưởng nghiệp vụ. Biện pháp có thể gồm chính sách **DNS chỉ qua resolver được phê duyệt**, điều tra tiến trình endpoint, cô lập host hoặc chặn domain/đích đã kiểm chứng theo change control. Phương án phải ghi rõ phạm vi, người phê duyệt, rollback và cách kiểm thử dịch vụ sau thay đổi.

**Không kết luận “đã rò rỉ dữ liệu” chỉ dựa vào số byte hoặc entropy.** Để kết luận về dữ liệu, phải có cơ sở bổ sung như nội dung được khôi phục hợp pháp từ chứng cứ, log ứng dụng/file, hoạt động tiến trình và mối liên hệ thời gian; nếu không, ghi mức nghi ngờ và khoảng trống điều tra.

### Bước 7 — Bảo toàn, phục hồi và báo cáo

Lưu bản gốc PCAP/log, kiểm tra hash, metadata thu thập, người thu, nguồn, khoảng thời gian, bộ lọc và lịch sử bàn giao. Sau xử lý, xác minh resolver chính sách còn hoạt động, ứng dụng thiết yếu không bị gián đoạn, telemetry được ghi nhận và hành vi nghi ngờ không tái diễn trong cửa sổ quan sát được xác định trước.

## 7. Kịch bản mẫu: một máy trạm truy vấn zone không quen thuộc

Toàn bộ tên miền và địa chỉ trong ví dụ sau là **dữ liệu lab tổng hợp**. Dải 198.51.100.0/24 và \`.example\` được dùng cho tài liệu; không có kết nối thật đến máy chủ điều khiển. Mục tiêu là minh họa phương pháp phân tích, không thực hiện kênh truyền dữ liệu.

**Môi trường giả lập:**

- Máy trạm \`Client-25\`: \`10.30.14.25\`, thuộc \`VLAN 14\`.
- DNS resolver được quản lý: \`10.30.0.53\`.
- Một resolver ngoài được đưa vào bài lab: \`198.51.100.53\`.
- Zone cần điều tra: \`case-lab.example\`.
- Nguồn chứng cứ: DNS resolver log, firewall flow, DHCP lease, EDR và PCAP trên đường client → resolver.
- Cửa sổ nghi ngờ: **09:00–09:05 UTC ngày 15-01-2026**.

### 7.1. Dữ liệu quan sát giả lập

~~~text
2026-01-15T08:57:04Z DHCP    asset=Client-25 ip=10.30.14.25 vlan=14 lease=ACTIVE
2026-01-15T09:00:02Z DNS     client=10.30.14.25 resolver=10.30.0.53 qtype=A
                            qname=m7r2k9q4c6t8v3p5n2w7d9f4h6s1x8a3.case-lab.example. rcode=NOERROR
2026-01-15T09:00:03Z DNS     client=10.30.14.25 resolver=10.30.0.53 qtype=TXT
                            qname=p8f5k2r9v4m7h6s3c1w9q2n8t5d4a6b7.case-lab.example. rcode=NOERROR
2026-01-15T09:00:04Z FLOW    src=10.30.14.25 dst=10.30.0.53 proto=UDP dport=53 action=ALLOW
2026-01-15T09:01:06Z DNS     client=10.30.14.25 resolver=10.30.0.53 qtype=A
                            qname=f2c8r4v7n1p9k5d6s3m8w2t7q4h6a5b9.case-lab.example. rcode=NXDOMAIN
2026-01-15T09:04:31Z SIEM    alert=EX-DNS-006 indicator=rare_zone_high_unique_qname
2026-01-15T09:05:12Z EDR     asset=Client-25 status=process_review_required confidence=medium
~~~

Đây là dữ liệu **để đặt giả thuyết**, không có sẵn nội dung payload hay kết luận an ninh. Một log quy chuẩn có thể được trình bày khác; timestamp và field trong ví dụ cần được điều chỉnh khi làm việc với hệ thống thật.

Trong cùng cửa sổ 5 phút, bảng tính năng tổng hợp giả lập:

| Chỉ số | Client-25, zone \`case-lab.example\` | Mức tham chiếu lịch sử của cùng client |
|---|---:|---:|
| Tổng query / 5 phút | 310 | 45 |
| Số QNAME duy nhất | 288 | 18 |
| Distinct QNAME ratio | 92,9% | 40,0% |
| Response NXDOMAIN | 32/310 = 10,3% | 2/45 = 4,4% |
| Query loại TXT | 120 | 0 |
| QNAME length median (ký tự) | 76 | 27 |
| Zone xuất hiện lần đầu | Trong cửa sổ điều tra | Không thấy ở baseline |

Các số này được **tạo để luyện tập**; không phải ngưỡng quy định và không phải số liệu từ file PCAP thực. Chú ý rằng baseline trong bảng là toàn bộ truy vấn thông thường của Client-25, còn cột nghi ngờ chỉ giới hạn một zone: sự khác nhau về phạm vi nhóm làm so sánh **chỉ mang tính gợi ý**. Khi triển khai phát hiện, nên xây cả baseline tổng thể và baseline cho từng lớp ứng dụng/zone.

### 7.2. Câu hỏi phải trả lời trước khi kết luận

1. Vì sao Client-25 đột nhiên hỏi zone mới? Có thay đổi cấu hình hoặc phiên bản ứng dụng đúng 09:00 không?
2. Các QNAME có thực sự dài và biến đổi ở **nhãn trái** hay chỉ phần đuôi chứa ID hợp lệ?
3. Query/response có được ghi đúng vị trí capture? Các bản ghi TXT có nội dung hoặc độ dài bất thường không?
4. Truy vấn đi qua resolver được duyệt hay còn luồng đến DNS ngoài; flow ALLOW có nghĩa gói thành công hay chỉ rule cho phép?
5. DNS log có bỏ sót response do mất gói, cache hoặc retry không?
6. EDR đã xác định được **tiến trình nào**, chữ ký, parent process và người dùng chưa?
7. Có host khác trong cùng subnet, VLAN, VPN hoặc cloud workload cùng hỏi zone không?
8. Có bằng chứng truy cập dữ liệu hoặc truyền nội dung nhạy cảm không? Nếu chưa, phải ghi rõ **chưa xác minh**.

### 7.3. Ví dụ ghi nhận phát hiện theo mức chứng cứ

| Ghi nhận | Phân loại | Lý do |
|---|---|---|
| 310 query từ Client-25 trong 5 phút | **Fact** | Đếm từ DNS resolver log, phạm vi nêu rõ |
| 288 QNAME khác nhau dưới một zone | **Fact** | Sau chuẩn hóa case/trailing dot |
| Client-25 có dấu hiệu DNS tunneling | **Hypothesis** | Các feature gợi ý nhưng chưa chứng minh mục đích |
| Đã rò rỉ dữ liệu | **Unknown** | Chưa có chứng cứ nội dung, process/file hoặc luồng dữ liệu xác minh |
| Tiến trình nào tạo query | **Unknown** | EDR mới có nhãn “process_review_required” |
| Thu process telemetry và hỏi chủ ứng dụng | **Next action** | Nhằm bác bỏ/củng cố giả thuyết |

## 8. Đọc PCAP và truy xuất log an toàn

Các lệnh dưới đây chỉ dùng cho **PCAP/log được phép phân tích trong lab hoặc hệ thống được cấp quyền**. Không thực hiện truy vấn ra tên miền bên ngoài, không tạo tunnel và không giải mã lưu lượng ngoài phạm vi.

### 8.1. Kiểm tra file trước khi phân tích

Nếu được giao một PCAP, lưu thông tin nguồn, thời gian, điểm capture, filter và hash trước khi chuyển sang bản sao để phân tích.

~~~bash
sha256sum /path/to/case-006.pcapng
capinfos /path/to/case-006.pcapng
~~~

\`capinfos\` cung cấp thông tin file (định dạng, số packet, thời gian bắt gói tùy phiên bản), **không** tự đánh giá chất lượng chứng cứ. Hash chỉ xác minh tính nguyên vẹn của file tại thời điểm tính và so sánh; không bảo đảm file đã ghi lại đủ mọi gói trên mạng.

### 8.2. Xác định DNS có trong PCAP

~~~bash
tshark -r /path/to/case-006.pcapng \
  -Y 'dns' \
  -T fields -E header=y -E separator=, -E quote=d \
  -e frame.time_epoch -e ip.src -e ip.dst \
  -e dns.id -e dns.flags.response -e dns.qry.name \
  -e dns.qry.type -e dns.flags.rcode
~~~

Các trường DNS trong Wireshark/TShark có thể khác nhau giữa các phiên bản hoặc yêu cầu tính năng giải mã đúng giao thức. Lọc thêm \`dns.flags.response == 0\` để xem **query**, và \`dns.flags.response == 1\` để xem **response**. Nếu tệp gồm IPv6, thêm \`ipv6.src\` và \`ipv6.dst\`; cột \`ip.src\` không bao trùm IPv6. Lưu ý nhiều cột có thể trống đối với các gói không phải query/response tương ứng.

Để chỉ xem query của máy trạm giả lập:

~~~bash
tshark -r /path/to/case-006.pcapng \
  -Y 'dns.flags.response == 0 && ip.src == 10.30.14.25' \
  -T fields -e frame.time_epoch -e ip.src \
  -e dns.qry.name -e dns.qry.type
~~~

Muốn phân tích câu trả lời cho những tên đã hỏi, lọc \`dns.flags.response == 1\`, xem \`dns.flags.rcode\`, trường answer và kích thước frame. Transaction ID **không đủ để nối duy nhất** truy vấn/phản hồi; cần thêm IP, cổng, giao thức, chiều và thời điểm, đặc biệt khi có ID được tái sử dụng.

### 8.3. Lọc trong Wireshark

Một số display filter hữu ích:

~~~text
dns
dns.flags.response == 0
dns.flags.rcode == 3
dns.qry.type == 16
ip.addr == 10.30.14.25 && dns
dns.qry.name contains "case-lab.example"
~~~

Trong DNS, QTYPE số **16** là TXT. Lọc \`contains\` là **tìm chuỗi con**, có thể khớp tên tương tự ngoài zone mong muốn; khi xuất dữ liệu để phân tích, hãy chuẩn hóa và dùng đối sánh hậu tố **ranh giới nhãn** (ví dụ tên đúng bằng \`case-lab.example\` hoặc kết thúc bằng \`.case-lab.example\`).

Khi phân tích thống kê, dùng \`Statistics → Conversations\`, \`Statistics → I/O Graphs\` hoặc chức năng tương đương của phiên bản Wireshark; biểu đồ từ PCAP là lưu lượng được capture tại **sensor đó**, không phải luôn là tổng mọi hoạt động của client.

### 8.4. Truy vấn SIEM với schema giả định

Ví dụ SQL dưới đây giả định bảng \`dns_events\` chứa các cột \`event_time_utc\`, \`client_ip\`, \`qname\`, \`qtype\` và \`rcode\`. Đây là mẫu tương tự PostgreSQL; phải điều chỉnh cú pháp, kiểu dữ liệu và mapping theo log thực tế.

~~~sql
SELECT
    date_trunc('minute', event_time_utc) AS minute_utc,
    client_ip,
    COUNT(*) AS query_count,
    COUNT(DISTINCT LOWER(TRIM(TRAILING '.' FROM qname))) AS distinct_qname,
    SUM(CASE WHEN rcode = 'NXDOMAIN' THEN 1 ELSE 0 END) AS nxdomain_count,
    SUM(CASE WHEN qtype = 'TXT' THEN 1 ELSE 0 END) AS txt_count,
    MAX(LENGTH(qname)) AS max_qname_length
FROM dns_events
WHERE event_time_utc >= TIMESTAMPTZ '2026-01-15 09:00:00+00'
  AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:05:00+00'
  AND client_ip = '10.30.14.25'
GROUP BY minute_utc, client_ip
ORDER BY minute_utc;
~~~

Đây mới là bước **tổng hợp chỉ số**, chưa đo entropy hay chứng minh đó là tunneling. Trong dữ liệu thực tế, nhiều hệ thống tách **query events** và **response events**; cần lọc đúng loại sự kiện để không đếm trùng hoặc chia NXDOMAIN cho số lượng query sai. \`LENGTH(qname)\` đo số ký tự của cách trình bày hiện tại, không đồng nhất với số octet DNS trên wire.

Một truy vấn riêng để lấy mẫu tên cần kiểm tra:

~~~sql
SELECT event_time_utc, client_ip, qname, qtype, rcode
FROM dns_events
WHERE event_time_utc >= TIMESTAMPTZ '2026-01-15 09:00:00+00'
  AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:05:00+00'
  AND client_ip = '10.30.14.25'
  AND (
       LOWER(TRIM(TRAILING '.' FROM qname)) = 'case-lab.example'
       OR LOWER(TRIM(TRAILING '.' FROM qname)) LIKE '%.case-lab.example'
  )
ORDER BY event_time_utc;
~~~

Không đưa toàn bộ dữ liệu QNAME vào bên thứ ba để “thử giải mã” khi chưa phân loại độ nhạy. QNAME có thể chứa ID phiên, email được mã hóa hoặc dữ liệu khác cần bảo vệ.

### 8.5. Tập hợp chứng cứ khi có DoH hoặc DoT

Khi sensor chỉ thấy TLS đến resolver, các câu hỏi cần trả lời bằng cách đối chiếu metadata và nguồn hợp lệ:

- Endpoint đang cấu hình resolver nào; policy MDM/GPO/VPN có bật DoH/DoT không?
- Có tiến trình và phiên kết nối nào trùng thời điểm bất thường?
- Có resolver log từ phía dịch vụ doanh nghiệp hoặc log ở endpoint thể hiện QNAME không?
- Có log thay đổi policy hoặc trạng thái proxy ảnh hưởng tuyến DNS không?
- Khả năng quan sát thiếu ở đâu, và kết luận nào vì vậy phải để ở mức “chưa biết”?

**Không khẳng định đã đọc được QNAME qua một phiên TLS chỉ từ PCAP không có khóa giải mã.**

## 9. Phân biệt DNS tunneling với các hiện tượng gần giống

| Hiện tượng | Điểm giống | Tín hiệu phân biệt cần thu |
|---|---|---|
| DNS tunneling nghi vấn | Nhiều query dưới một zone, nhãn biến thiên, phản hồi đặc biệt | Process gốc, mục đích domain, chiều truyền, lịch sử thay đổi và sự nhất quán nhiều nguồn |
| Domain Generation Algorithm (DGA) | Tên khó đọc và nhiều NXDOMAIN | Nhiều base domain/zone thay đổi thay vì chỉ nhiều subdomain của cùng zone |
| CDN và hostname sinh ID | Subdomain ngẫu nhiên, distinct ratio cao | Domain thuộc nhà cung cấp được phê duyệt, nhiều client hợp lệ có cùng pattern |
| DKIM/SPF/domain verification | TXT dài hoặc nhiều TXT records | QNAME/QTYPE thuộc quy trình email xác minh, xuất hiện ở ngữ cảnh phù hợp |
| DNSSEC/EDNS(0) | Kích thước response tăng, phát sinh retry/TCP | DNSSEC records, extension options, cờ truncated và thay đổi resolver |
| Lỗi ứng dụng hoặc resolver | Tăng NXDOMAIN/SERVFAIL, query lặp | Log cấu hình, lỗi ứng dụng, xử lý retry, trạng thái upstream |
| Phần mềm giám sát và heartbeat | Nhịp đều, truy vấn liên tục | Chủ dịch vụ xác nhận, binary/process hợp lệ, traffic baseline nhất quán |
| DNS cache-busting hợp lệ | Nhiều tên duy nhất dưới một zone | Documentation, version ứng dụng, mục đích cache control |
| Lạm dụng DNS thực sự | Lưu lượng DNS và dấu hiệu bất thường có thể trùng các trường hợp trên | Cần chuỗi bằng chứng kỹ thuật cho thấy cơ chế và hành vi không được phép |

**Một quy trình loại trừ tốt:** bắt đầu từ bằng chứng có thể kiểm tra, tìm lời giải thích hợp lệ, hỏi chủ ứng dụng, đối chiếu process và telemetry độc lập; chỉ sau đó mới tăng độ tin cậy về kịch bản lạm dụng.

## 10. Phòng vệ và ứng phó sau phát hiện

### 10.1. Kiểm soát mạng theo nhiều lớp

| Lớp | Biện pháp | Cách xác minh |
|---|---|---|
| Thiết bị đầu cuối | Quản lý DNS policy, giám sát tiến trình và resolver configuration, EDR | Query từ app hợp lệ có process lineage; drift cấu hình được cảnh báo |
| Phân đoạn / firewall | Chỉ cho phép DNS tới resolver được quản lý theo yêu cầu nghiệp vụ; kiểm soát DNS egress | Test client lab truy vấn DNS qua đường được duyệt, kết nối ngoài quy định bị chặn |
| Resolver | Bật query log theo chính sách, RPZ hoặc domain filtering được phê duyệt, cảnh báo rare zone | Log có client identity, QTYPE, RCODE, timestamp; policy được thử |
| IDS/IPS / NDR | Tương quan distinct QNAME, label length, periodicity, TXT ratio và dấu hiệu process | Replay dữ liệu lab: phát hiện đúng và báo cáo false positive |
| VPN / Wi-Fi / NAC | Giữ mapping thiết bị, user và mạng tại thời điểm sự kiện | Truy ngược thiết bị dù roaming hoặc đổi VPN IP |
| Hạ tầng cloud | Theo dõi VPC/VNet flow, DNS query log và policy DNS của workload | Gắn hostname/instance/service identity với query và thời gian |
| SIEM / SOAR | Gắn cảnh báo với asset, NAT/DHCP, nhóm dịch vụ, rule và workflow điều tra | Case được tự động làm giàu, vẫn có người xác thực trước biện pháp lớn |

Có thể bắt đầu bằng **monitor-only**, sau đó triển khai chặn hẹp hoặc chặn theo chính sách khi đã kiểm tra phụ thuộc. Một số ứng dụng dùng resolver riêng vì yêu cầu kỹ thuật, vì vậy thay đổi DNS policy cần có khảo sát và lộ trình phù hợp.

DNS mã hóa yêu cầu cách quản lý khác nhau tùy môi trường: policy endpoint, khả năng logging của resolver được quản lý và kiểm soát truy cập tới dịch vụ DoH/DoT trong phạm vi được phép. Chặn mỗi UDP/53 **không bảo đảm** đã kiểm soát toàn bộ con đường DNS.

### 10.2. Triage → containment → eradication → recovery

1. **Triage:** tiếp nhận cảnh báo, xác định asset và mức ưu tiên bằng chứng.
2. **Containment:** nếu nguy cơ đủ cao, cô lập host hoặc áp chính sách DNS egress hẹp, được phê duyệt và có rollback.
3. **Eradication:** xử lý nguyên nhân đã xác minh, ví dụ tiến trình không được phép, cấu hình sai, tài khoản bị lộ hoặc lỗ hổng quản lý DNS policy.
4. **Recovery:** kiểm thử DNS hợp lệ, ứng dụng, VPN, kết nối giữa VLAN và phụ thuộc cloud; theo dõi tín hiệu tái diễn.
5. **Lessons learned:** bổ sung detection, asset mapping, quy trình điều tra và chuẩn hóa phản ứng.

Trong mọi bước, ghi **tác động nghiệp vụ**: chặn resolver hoặc zone có thể ảnh hưởng DNS nội bộ, dịch vụ xác thực, mail hoặc cloud workloads. Các thay đổi cần được đo ở cả phía “đã giảm lưu lượng khả nghi” lẫn “dịch vụ bình thường vẫn hoạt động”.

### 10.3. Tiêu chí xác minh biện pháp

- Lưu lượng nghi vấn bị hạn chế theo mục tiêu mà IC phê duyệt.
- Truy vấn DNS hợp lệ vẫn phân giải và ứng dụng quan trọng qua health check.
- Sensor vẫn ghi nhận dữ liệu, không phải “hết alert” vì pipeline ngừng.
- Có đối chiếu rule counter, resolver log, flow và endpoint ở cùng giai đoạn.
- Nguồn gốc hành vi đã được xử lý hoặc phần rủi ro còn lại có owner và được chấp thuận.
- Rule mới, ngoại lệ, rollback và quyết định đóng case được ghi lại.

## 11. Bảo quản chứng cứ và báo cáo network forensics

### 11.1. Evidence manifest

Mỗi bản chứng cứ nên có một dòng manifest, ví dụ:

| Trường | Ví dụ minh họa |
|---|---|
| Case ID | NF-DNS-006 |
| Evidence ID | NF-DNS-006-E04 |
| Loại | DNS query log export hoặc \`case-006.pcapng\` |
| Nguồn | Resolver \`10.30.0.53\`, điểm capture \`VLAN 14\` |
| Thời gian sự kiện | 2026-01-15 09:00–09:05 UTC |
| Thời gian thu | 2026-01-15 09:20 UTC |
| Người thu | Analyst được chỉ định |
| Kỹ thuật / filter | DNS log export theo client+thời gian, hoặc capture filter được lưu |
| SHA-256 | Giá trị thực từ file khi thu thập (không tự điền hash giả) |
| Nơi lưu | Kho chứng cứ phân quyền, có retention và audit log |
| Bàn giao | Người giao, người nhận, thời điểm, mục đích |

Cần quản lý dữ liệu cá nhân và thông tin có thể nằm trong QNAME, như token hoặc định danh người dùng. Ẩn dữ liệu khi chia sẻ báo cáo rộng, nhưng giữ bản gốc trong kho chứng cứ và ghi nhận mọi phép biến đổi dữ liệu.

### 11.2. Mẫu tóm tắt điều tra

~~~text
CASE: NF-DNS-006
Mức ưu tiên: Đang đánh giá (ví dụ P2 theo quy trình nội bộ)
Khoảng thời gian: 2026-01-15 09:00–09:05 UTC
Nguồn quan sát: DNS resolver, firewall flow, DHCP, EDR
Tài sản nghi vấn: Client-25 / 10.30.14.25 ở thời điểm sự kiện

FACTS:
- 310 DNS query trong 5 phút, 288 QNAME duy nhất theo mẫu thống kê.
- Có TXT queries và nhiều tên dưới case-lab.example.
- DHCP log liên kết địa chỉ nguồn với Client-25 trong khoảng thời gian đó.

HYPOTHESIS:
- Hành vi có đặc điểm phù hợp với DNS tunneling, cần kiểm chứng.

UNKNOWN:
- Tiến trình phát query; dịch vụ hợp lệ tương ứng; có dữ liệu
  thực tế được truyền ra ngoài hay không.

ACTIONS:
- Kiểm tra process lineage, owner ứng dụng, response, NAT và DNS policy.
- Bảo toàn log/PCAP, xác thực độ đầy đủ của telemetry.
- Thống nhất ngưỡng leo thang và phương án containment có rollback.

KẾT LUẬN TẠM THỜI:
- DNS tunneling là giả thuyết ưu tiên điều tra; chưa đủ bằng chứng
  kết luận đã có C2 hoặc exfiltration.
~~~

Báo cáo cuối cùng cần nêu nguồn và độ tin cậy của từng kết luận, phạm vi ảnh hưởng, quyết định đã phê duyệt, hiệu quả kiểm soát, khoảng trống chứng cứ, việc còn tồn và người chịu trách nhiệm.

## 12. Sai lầm thường gặp khi phân tích DNS tunneling

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Chỉ dùng entropy để phán đoán | Gây false positive với CDN, ID và phần mềm hợp lệ | Kết hợp tần suất, zone, process, owner và baseline |
| Coi mọi TXT là đáng ngờ | Báo sai cho SPF/DKIM/verification | Kiểm tra ngữ cảnh QTYPE và chức năng domain |
| Coi nhiều NXDOMAIN là exfiltration | Nhầm DGA hoặc lỗi resolver với tunneling | Phân biệt pattern thay đổi subdomain và domain gốc |
| Gán resolver IP thành host phát sinh | Điều tra sai endpoint, cô lập sai tài sản | Dùng query log phía client, DHCP/NAT/VPN mapping |
| Dùng hai nhãn cuối làm domain chính | Gộp sai các miền công cộng như \`co.uk\` | Public Suffix List và cấu hình zone nội bộ |
| Không loại query/response trùng | Phóng đại query count và tỷ lệ lỗi | Chỉ rõ loại event, direction, retransmission |
| Bỏ qua cache và điểm capture | Tưởng rằng không có lưu lượng hoặc số liệu lệch | Ghi vantage, cache, sampling và packet loss |
| Kết luận nội dung từ flow metadata | “Chứng minh” exfiltration khi chỉ thấy bytes | Báo cáo dữ liệu thực thấy, yêu cầu chứng cứ bổ sung |
| Không tính tới DoH/DoT | Bỏ sót hoạt động hoặc đọc sai PCAP TLS | Đối chiếu endpoint và resolver được quản lý |
| Chặn toàn DNS không kiểm thử | Mất phân giải tên cho nhiều dịch vụ | Chặn hẹp, xác minh ứng dụng, rollback rõ |
| Không ghi điều kiện đóng case | Không biết sự cố đã được xử lý hay chỉ tạm im lặng | Tiêu chí phục hồi và thời gian giám sát được phê duyệt |
| Chia sẻ QNAME không phân loại dữ liệu | Rò rỉ token/định danh trong chứng cứ | Hạn chế truy cập, masking báo cáo và lưu bản gốc bảo vệ |

## 13. Bài tập thực hành và câu hỏi kiểm tra

### Bài tập 1 — Nhận diện dấu hiệu và giới hạn

Một client phát 800 DNS query/10 phút dưới cùng zone với 95% QNAME duy nhất, nhãn trái dài 40 ký tự và entropy cao. Nêu **ít nhất bốn cách giải thích**, gồm cả hợp lệ và bất thường; sau đó chọn **ba nguồn bằng chứng** giúp bác bỏ hoặc củng cố từng giả thuyết.

**Gợi ý:** kênh DNS lạm dụng, CDN/cache-busting, phần mềm monitoring, lỗi cấu hình, ứng dụng mới triển khai. Dùng resolver log, process/EDR, DHCP/NAT, firewall và xác nhận chủ dịch vụ. Chỉ số cao **chưa đủ** để kết luận đã rò rỉ dữ liệu.

### Bài tập 2 — Đọc log từ nhiều điểm

Firewall Internet chỉ thấy \`10.30.0.53\` truy vấn zone lạ, còn DNS resolver log cho thấy \`10.30.14.25\` là client. Hãy giải thích:

1. Vì sao hai địa chỉ nguồn khác nhau?
2. Bước cần thiết để gắn \`10.30.14.25\` với asset chính xác?
3. Tại sao không được cô lập máy \`10.30.0.53\` chỉ dựa vào flow Internet?

**Đáp án hướng dẫn:** recursive resolver hỏi authoritative thay cho client; cần đối chiếu lease/time và inventory/NAC/VPN; cô lập resolver có thể làm hỏng DNS của cả hệ thống và không xác định nguyên nhân ở endpoint.

### Bài tập 3 — Thiết kế truy vấn SIEM

Từ các trường \`event_time_utc\`, \`client_ip\`, \`qname\`, \`qtype\`, \`rcode\`, hãy đề xuất một bảng nhóm theo mỗi 5 phút và mỗi zone: total, unique QNAME, tỷ lệ NXDOMAIN, tỷ lệ TXT, p95 QNAME length và first/last seen.

**Tiêu chí đạt:** lọc đúng query/response, chuẩn hóa QNAME, ghi rõ cách xác định zone, không dùng ngưỡng cố định cho mọi client, biết rằng percentile có thể khác cú pháp giữa các hệ SIEM.

### Bài tập 4 — Khoảng trống DoH

Sensor chỉ thấy HTTPS đến một resolver ngoài, không thấy nội dung QNAME. Những kết luận nào được phép rút ra? Những nguồn nào có thể dùng để điều tra tiếp?

**Gợi ý:** có thể xác nhận metadata kết nối theo telemetry; không khẳng định tên đã hỏi, kiểu bản ghi hoặc tunneling chỉ từ TLS flow. Tra endpoint policy, resolver log có quyền, EDR, proxy và cloud log liên quan.

### Bài tập 5 — Ra quyết định khi dịch vụ quan trọng

Một endpoint liên quan máy chủ xác thực có tín hiệu DNS bất thường; nếu chặn cả subnet, nhiều ứng dụng sẽ ngừng hoạt động. Viết decision log gồm: mức ưu tiên, cơ sở, thay đổi hẹp nhất, bên phê duyệt, kiểm tra tác động, rollback và tiêu chí xác nhận ngăn chặn.

**Tiêu chí đạt:** giải pháp cân bằng bằng chứng, rủi ro và tính liên tục dịch vụ; không đưa ra thao tác phá vỡ hoạt động khi chưa kiểm chứng.

### Bài tập 6 — Viết kết luận forensics

Dựa vào số liệu của Client-25, viết đoạn 5–7 câu để gửi Incident Commander, trong đó phải có: **hai fact**, **một hypothesis**, **hai unknown** và **hai next actions**.

**Ví dụ đạt:** “Trong 5 phút, log của resolver ghi 310 truy vấn từ Client-25; 288 QNAME là duy nhất. Hành vi tập trung dưới zone hiếm và có nhiều bản ghi TXT, phù hợp với giả thuyết DNS tunneling. Chưa xác định được tiến trình sinh truy vấn và chưa có bằng chứng xác minh dữ liệu rò rỉ. Nhóm đang thu process telemetry và kiểm tra change log của chủ dịch vụ; đồng thời chuẩn bị phương án DNS egress hẹp có rollback theo đánh giá tác động.”

## 14. Checklist tự kiểm tra trước khi hoàn tất điều tra

- [ ] Xác định điểm quan sát và những loại DNS mà công cụ có thể/không thể thấy.
- [ ] Gắn IP với tài sản bằng mapping **đúng thời điểm**, kể cả DHCP, NAT và VPN khi liên quan.
- [ ] Có timeline tách event time, ingest time và thời gian analyst xử lý.
- [ ] Phân tích QNAME theo client + zone + cửa sổ; chuẩn hóa case, trailing dot và IDNA.
- [ ] Kiểm tra query type, RCODE, độ dài nhãn, distinct ratio, entropy và nhịp truy vấn.
- [ ] So sánh với baseline phù hợp, chú ý ảnh hưởng cache, retransmission và sampling.
- [ ] Đối chiếu endpoint process, chủ ứng dụng, firewall/flow và DNS resolver logs.
- [ ] Phân biệt chứng cứ thực tế, giả thuyết, điều chưa biết và phương án kiểm chứng.
- [ ] Đánh giá khả năng DoH/DoT hoặc tuyến DNS ngoài khiến mất vùng nhìn thấy.
- [ ] Có evidence manifest, nguồn và khoảng thời gian, hash bản gốc, nơi lưu và chuỗi bàn giao.
- [ ] Biện pháp ứng phó có phạm vi rõ, phê duyệt, rollback và kiểm thử phụ thuộc nghiệp vụ.
- [ ] Báo cáo cuối có mức tin cậy, tác động, rủi ro còn lại và hành động cải tiến có owner.

Phân tích DNS tunneling hiệu quả dựa vào việc **đọc DNS trong ngữ cảnh của mạng và tài sản**, không phải tìm một dấu hiệu đơn lẻ. Kết quả forensics có thể là xác minh hành vi không được phép, xác nhận hoạt động hợp lệ, hoặc kết luận chưa đủ dữ liệu; cả ba đều có giá trị khi được chứng minh minh bạch và dẫn tới quyết định bảo vệ mạng phù hợp.

