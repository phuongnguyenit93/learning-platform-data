# Signature-based detection trong IDS/IPS: nguyên lý, thiết kế rule và vận hành

## 1. Signature-based detection là gì?

**Signature-based detection (phát hiện dựa trên chữ ký)** là phương pháp đối chiếu dữ liệu quan sát được với các **mẫu hoặc điều kiện đã biết** để tìm dấu hiệu của hành vi, giao thức, nội dung hoặc kỹ thuật cần cảnh báo. Trong **Intrusion Detection System (IDS)** và **Intrusion Prevention System (IPS)**, chữ ký thường được biểu diễn thành **rule** chứa điều kiện áp dụng và hành động khi khớp.

Ví dụ, đội an ninh muốn nhận biết các yêu cầu HTTP trong phòng lab có header **User-Agent: TrainingClient/1.0**. Một rule có thể kiểm tra trường User-Agent đã được giải mã và tạo sự kiện khi thấy giá trị này. Sự kiện **chỉ xác nhận điều kiện quan sát được**, chưa chứng minh máy gửi bị xâm nhập hoặc cuộc tấn công đã thành công.

Trong module **SECURITY_NETWORK_SECURITY**, đây là kiến thức nền để triển khai phòng vệ nhiều lớp: phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và cloud. Một hệ thống phát hiện tốt phải biết **nó nhìn thấy phần nào của lưu lượng**, **chữ ký nào khớp**, **hành động nào được thực thi**, và **cần bằng chứng gì trước khi kết luận sự cố**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cách engine IDS/IPS giải mã gói tin, tái dựng luồng và đối chiếu chữ ký.
2. Phân biệt chữ ký theo payload, trường giao thức, trạng thái luồng và IOC.
3. Đọc một rule mẫu và giải thích từng điều kiện match/action.
4. Đánh giá **true positive, false positive, false negative** và giới hạn của phát hiện chữ ký.
5. Thiết kế quy trình thử nghiệm, cập nhật, hiệu chỉnh, rollback và giám sát rule.
6. Liên hệ phát hiện chữ ký với TLS, NAT, segmentation, VPN, cloud và ứng phó sự cố.

## 2. IDS, IPS và vai trò của chữ ký

| Khái niệm | Vị trí/đặc điểm | Khi chữ ký khớp | Lưu ý |
| --- | --- | --- | --- |
| **Network IDS (NIDS)** | Thường quan sát traffic từ TAP/SPAN hoặc nguồn mạng tương đương | Sinh alert/log hoặc dữ liệu điều tra | Ngoài luồng (*out-of-band*), thường không trực tiếp chặn gói đi qua |
| **Network IPS (NIPS)** | Được đặt trên đường xử lý traffic (*inline*) hoặc tích hợp cơ chế enforcement | Có thể alert, drop, reject hoặc thực hiện hành động được nền tảng hỗ trợ | Tính khả dụng và false positive ảnh hưởng trực tiếp tới dịch vụ |
| **Host IDS/IPS (HIDS/HIPS)** | Thu dữ liệu và/hoặc thực thi chính sách trên endpoint/host | Cảnh báo hoặc chặn ở host theo khả năng | Tập quan sát khác NIDS; có thể thấy sự kiện tiến trình/file |
| **NGFW / firewall tích hợp IPS** | Kết hợp policy kết nối với khả năng phân tích lưu lượng/nội dung | Áp dụng rule firewall và IPS profile theo policy | **ALLOW ở firewall** chưa có nghĩa payload được IPS chấp nhận |
| **WAF có rule signature** | Quan sát HTTP/API ở tầng ứng dụng | Chặn/cảnh báo mẫu web theo khả năng | WAF tập trung ngữ nghĩa HTTP, không thay NIDS cho toàn mạng |

Trong **IDS**, alert thường yêu cầu người vận hành hoặc công cụ tự động xác minh và xử lý tiếp. Trong **IPS**, một rule có thể có hành động chặn, nhưng **không phải rule nào khớp cũng phải chặn**; nhiều tổ chức chạy rule mới ở chế độ phát hiện trước khi cân nhắc enforcement.

**Chữ ký** trong ngữ cảnh này không phải **chữ ký số** dùng khóa riêng/công khai. Nó là **mẫu phát hiện**; không tạo bảo đảm mật mã rằng thông điệp là chính xác hoặc người gửi hợp lệ.

## 3. Pipeline xử lý: từ packet đến alert

~~~mermaid
flowchart LR
    A["Nguồn traffic: TAP, SPAN hoặc inline"] --> B["Capture và decode L2/L3/L4"]
    B --> C["Flow tracking / TCP reassembly"]
    C --> D["Protocol parsing và normalization"]
    D --> E["Signature matching"]
    E --> F{"Điều kiện rule khớp?"}
    F -- "Không" --> G["Tiếp tục xử lý"]
    F -- "Có" --> H["Alert / log / metadata"]
    H --> I{"IPS inline và rule chặn?"}
    I -- "Có" --> J["Drop/reject theo engine"]
    I -- "Không" --> K["Chuyển traffic theo policy khác"]
~~~

Sơ đồ là mô hình khái quát: thứ tự chi tiết, fast-pattern engine, flow classification, app-layer detection, rule grouping và cách gói bị drop phụ thuộc engine/phiên bản. **Không phải mọi chữ ký đều chạy trên cùng một biểu diễn payload**.

### 3.1. Thu thập gói và vị trí cảm biến

Sensor có thể đặt ở:

- **Biên Internet/DMZ:** Quan sát truy cập vào dịch vụ public và traffic egress.
- **Giữa các zone:** Theo dõi lưu lượng east–west, đặc biệt User → Server, App → DB hoặc Dev → Prod.
- **Đường VPN sau giải mã:** Xem traffic đã ra khỏi VPN tunnel tại điểm được phép quan sát; nếu chỉ thấy outer IPsec packets, nội dung ứng dụng vẫn bị che.
- **VPC/VNet/cloud:** Dùng traffic mirroring, service insertion, virtual appliance hoặc sensor trên host theo khả năng nền tảng.

**SPAN không đảm bảo nhận mọi packet** nếu cổng mirror bị quá tải hoặc thiết lập sai. Đặt sensor trên một đường mạng nhưng traffic đi đường khác sẽ tạo **blind spot**. HA/failover có thể làm thay đổi đường đi và khiến sensor mất khả năng quan sát nếu topology không được kiểm tra.

### 3.2. Giải mã giao thức và xây dựng flow

Một yêu cầu HTTP có thể trải qua các lớp:

~~~text
Ethernet frame
  └── IPv4 / IPv6 packet
        └── TCP segment
              └── HTTP request hoặc response
                    ├── Method / URI
                    ├── Headers
                    └── Body
~~~

Ở tầng mạng, engine có thể đọc IP, protocol, port, TCP flags. Để phát hiện chuỗi HTTP, engine cần phân tích đúng **dữ liệu ứng dụng**. TCP có thể chia một chuỗi qua nhiều segment, truyền lại segment hoặc gửi segment đến không theo thứ tự; chỉ tìm một chuỗi trong từng packet thô có thể bỏ sót mẫu.

**Flow tracking** giữ ngữ cảnh kết nối: hướng client/server, established/new, traffic tới server hay tới client. **Stream reassembly** tái dựng luồng TCP theo quy tắc engine; **normalization** xử lý những khác biệt biểu diễn được hỗ trợ để giảm việc một mẫu có nhiều cách mã hóa tương đương.

### 3.3. Bước matching và tạo sự kiện

Engine có thể kết hợp:

1. **Header/rule prefilter:** IP nguồn/đích, port, protocol, chiều, zone/biến địa chỉ.
2. **Flow state:** Established, to-server/to-client hoặc các trạng thái khác engine hiểu.
3. **Protocol buffer:** URI, Host, DNS query, TLS metadata, nội dung HTTP body đã giải mã theo khả năng.
4. **Pattern content/regex/byte test:** Mẫu byte, biểu thức chính quy hoặc điều kiện trường.
5. **Threshold/suppression và action:** Ghi alert, đếm tần suất, điều chỉnh thông báo; IPS xử lý theo cấu hình enforcement.

Hai rule có cùng mẫu content nhưng khác **flow, scope, protocol buffer hoặc action** có thể tạo ra hành vi và tỉ lệ false positive rất khác nhau.

## 4. Những loại chữ ký thường gặp

| Loại | Điều kiện ví dụ | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **Byte/payload pattern** | Chuỗi byte hoặc magic bytes trong dữ liệu quan sát được | Dễ hiểu và so khớp nhanh với mẫu rõ ràng | Dễ bị bỏ sót khi nội dung bị mã hóa, biến đổi hoặc mẫu quá đặc thù |
| **Protocol field** | HTTP method/URI/User-Agent; DNS query type; TLS metadata có thể thấy | Ít nhầm hơn khi match đúng trường | Phụ thuộc protocol parser và phiên bản giao thức |
| **Flow/state signature** | TCP established, chiều đến server, chuỗi sự kiện theo flow | Thêm ngữ cảnh, giảm một phần match sai | Tốn state; không luôn nhận thấy toàn bộ luồng |
| **IOC/reputation** | IP, hostname, URL hoặc hash đã biết liên quan chiến dịch | Bổ sung nhận diện hạ tầng/artefact đã điều tra | IOC có thể thay đổi nhanh, IP dùng chung, thông tin hết hạn |
| **Exploit-behavior pattern** | Một chuỗi trường/giá trị gợi ý hành vi khai thác đã biết | Có thể cảnh báo trước khi exploit thành công | Match có thể là kiểm thử hợp pháp hoặc chỉ là dấu hiệu thăm dò |
| **Policy signature** | Giao thức cấm, User-Agent lab, DNS query ngoài resolver được phép | Có ích cho phát hiện vi phạm quy định nội bộ | Vi phạm policy không tự bằng xâm nhập |

Một **signature** có thể có nhiều điều kiện chứ không chỉ một chuỗi; ví dụ “TCP established, request đến server, URI trong parser HTTP chứa mẫu A và header X có giá trị B”.

**Phân biệt với anomaly-based detection:** Phát hiện bất thường so hành vi với đường cơ sở hoặc mô hình học được, có thể nhận diện hành vi chưa có chữ ký cụ thể nhưng dễ nhạy với sự thay đổi bình thường. Hệ thống thực tế thường kết hợp **signature + anomaly + logs từ endpoint/application + threat intelligence** để giảm lỗ hổng quan sát.

## 5. Đọc một rule mẫu theo cú pháp Suricata

Đoạn dưới đây là **ví dụ minh họa phòng lab** theo phong cách rule Suricata; nó chỉ cảnh báo một header vô hại để học cú pháp. Biến **$HOME_NET** và **$EXTERNAL_NET** phải được đặt phù hợp với mạng giám sát. Không đưa rule vào IPS Production khi chưa chạy kiểm tra cú pháp và thử nghiệm phiên bản engine đang dùng.

~~~suricata
alert http $EXTERNAL_NET any -> $HOME_NET any (msg:"LAB HTTP User-Agent TrainingClient"; flow:established,to_server; http.user_agent; content:"TrainingClient/1.0"; nocase; sid:1000001; rev:1;)
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| **alert** | Hành động sinh alert khi khớp; bản thân nó không phải lệnh chặn |
| **http** | Chỉ áp dụng với dữ liệu được engine nhận dạng và phân tích là HTTP |
| **$EXTERNAL_NET any → $HOME_NET any** | Điều kiện địa chỉ nguồn/đích và cổng; không tự đồng nghĩa Internet thực tế vì phụ thuộc định nghĩa biến |
| **msg** | Thông điệp mô tả alert cho người vận hành |
| **flow:established,to_server** | Giới hạn theo kết nối đã được xác lập và hướng request đến server theo ngữ nghĩa engine |
| **http.user_agent** | *Sticky buffer*: chuyển vùng so khớp sang trường User-Agent do HTTP parser trích xuất |
| **content** | Chuỗi cần đối chiếu trong buffer đang chọn |
| **nocase** | Không phân biệt chữ hoa/chữ thường khi so khớp content tương ứng |
| **sid** | Signature ID, định danh rule trong namespace/phạm vi cấu hình |
| **rev** | Phiên bản sửa đổi của rule, hỗ trợ theo dõi thay đổi |

**Dấu hiệu match của rule:** Một HTTP request mà parser nhìn thấy User-Agent chứa **TrainingClient/1.0**, đi qua vùng địa chỉ và flow phù hợp. Nó không cho biết người gửi là công cụ độc hại; User-Agent là trường do phía client cung cấp và có thể bị giả.

### 5.1. Rule cho truy vấn DNS trong lab

Ví dụ khác nhận diện truy vấn tới tên mô phỏng **ids-lab.example** trên DNS/53:

~~~suricata
alert dns $HOME_NET any -> $EXTERNAL_NET 53 (msg:"LAB DNS query marker"; dns.query; content:"ids-lab.example"; nocase; sid:1000002; rev:1;)
~~~

Nếu DNS resolver **nằm trong HOME_NET** hoặc client dùng **DoH/DoT**, rule theo hướng/port trên có thể không match dù ứng dụng vẫn phân giải tên. **dns.query** là trường do DNS parser cung cấp; đó không phải mọi byte được mã hóa ở các giao thức DNS over HTTPS hoặc DNS over TLS.

Một rule DNS thực tế còn phải đánh giá **name boundary, loại truy vấn, ngữ nghĩa exact vs substring và false positive**. Không dùng một mẫu chuỗi đơn giản làm bằng chứng chắc chắn rằng một domain có hành vi độc hại.

### 5.2. Khác biệt Snort, Suricata và nhà cung cấp

Snort và Suricata có cú pháp rule tương đồng ở mức cơ bản nhưng **keyword, sticky buffer, hỗ trợ decoder, app-layer parsing, thứ tự evaluation và tính năng phiên bản có thể khác nhau**. Một rule chạy trên Suricata không mặc nhiên tương thích đầy đủ với Snort hoặc IPS của NGFW khác.

Đối với rule thật, phải kiểm tra:

- Rule syntax và **engine version**.
- Ý nghĩa của **$HOME_NET**, **$EXTERNAL_NET**, address group và local variables.
- HTTP/DNS/TLS buffers được hỗ trợ; có giải mã đúng loại traffic dự kiến hay không.
- **SID uniqueness**, revision, metadata, action và thứ tự/tương tác các policy.
- Ảnh hưởng tới hiệu năng, flowbits/xbits/state tracking và quản lý update.

## 6. Chữ ký đang phát hiện “dấu hiệu” gì?

Không nên đánh đồng ba mức bằng chứng:

| Mức | Ví dụ | Kết luận có thể rút ra |
| --- | --- | --- |
| **Match mẫu** | User-Agent chứa chuỗi lab, URI chứa một token | Có dữ liệu quan sát được khớp rule |
| **Hành vi nghi vấn** | Mẫu trùng với một kỹ thuật đã biết và có ngữ cảnh mạng phù hợp | Đáng điều tra; chưa chắc khai thác thành công |
| **Xâm nhập được xác nhận** | Alert tương quan với log ứng dụng, thay đổi trái phép, endpoint evidence và xác thực của điều tra viên | Có căn cứ xác nhận sự kiện trong phạm vi bằng chứng |

Ví dụ, signature gắn mã CVE có thể báo một request giống payload khai thác. **Alert không tự chứng minh server đang chạy phiên bản dễ bị ảnh hưởng**, đã xử lý payload hoặc bị kiểm soát. Để kết luận cần kết hợp **asset inventory, kết quả quản lý lỗ hổng, phiên bản dịch vụ, application logs và bằng chứng đáp ứng**.

Đối với rule IOC, một IP trùng danh sách đe dọa không tự chứng minh máy chủ nhận là độc hại: có thể là hosting dùng chung, CDN, địa chỉ bị chuyển chủ, thông tin threat intel đã cũ hoặc dữ liệu nhầm.

## 7. Tại sao signature-based detection có false positive và false negative?

### 7.1. Bốn kết quả cơ bản

| Thực tế / quyết định | Rule báo động | Rule không báo động |
| --- | --- | --- |
| **Có sự kiện cần phát hiện** | **True Positive (TP)** | **False Negative (FN)** |
| **Không có sự kiện cần phát hiện** | **False Positive (FP)** | **True Negative (TN)** |

**False positive** có thể do chữ ký quá rộng, nội dung hợp lệ trùng mẫu, rule thiếu flow context, môi trường đang có hoạt động kiểm thử được phép hoặc IOC không còn đúng.

**False negative** có thể do chữ ký chưa có, mẫu thay đổi, traffic mã hóa, parser không nhận diện giao thức, cảm biến không thấy gói, packet loss hoặc mẫu nằm ngoài phạm vi rule.

### 7.2. Chỉ số đo trong một tập mẫu có nhãn

Với dữ liệu kiểm thử đã xác minh kết quả thực tế:

\[
\text{Precision} = \frac{TP}{TP+FP}
\]

\[
\text{Recall} = \frac{TP}{TP+FN}
\]

\[
\text{False Positive Rate} = \frac{FP}{FP+TN}
\]

Ví dụ một tập kiểm thử gồm **100 trường hợp thật sự cần phát hiện** và **1.000 trường hợp bình thường**. Engine có:

~~~text
TP = 80    FN = 20
FP = 20    TN = 980

Precision = 80 / (80 + 20)   = 80%
Recall    = 80 / (80 + 20)   = 80%
FPR       = 20 / (20 + 980)  = 2%
~~~

Một FPR nhỏ vẫn gây nhiều cảnh báo sai khi lưu lượng bình thường có quy mô rất lớn. Do đó cần cân bằng **độ phủ phát hiện, chi phí điều tra, độ trễ, hiệu năng và tác động của hành động chặn**.

**Giới hạn đo lường:** Trong sản xuất, số sự kiện bị bỏ sót (FN) và số trường hợp thực sự bình thường (TN) thường không biết đầy đủ. Không lấy “không có alert” làm bằng chứng TN nếu không có ground truth; hãy đo trên tập mẫu kiểm thử/diễn tập được gán nhãn.

## 8. Giới hạn lớn nhất: traffic mã hóa và vùng mù quan sát

Một NIDS thấy packet của kết nối TLS thường có thể quan sát **địa chỉ IP, port, hướng, kích thước/timing và một số metadata handshake tùy phiên bản/cấu hình**, nhưng không thể tự đọc HTTP URI, header hay body đã được mã hóa đúng cách.

| Vị trí sensor | Thường thấy được | Hạn chế |
| --- | --- | --- |
| Trước điểm kết thúc HTTPS | IP/TCP/UDP, TLS handshake metadata còn hiển thị, flow statistics | Không có HTTP body plaintext; TLS 1.3 và ECH giảm metadata hiển thị trong một số tình huống |
| Sau reverse proxy đã kết thúc TLS | HTTP plaintext trên chặng backend nếu chặng đó dùng HTTP | Nếu proxy tái mã hóa bằng TLS, sensor trên dây vẫn không đọc được payload |
| Tại proxy/WAF có quyền giải mã | Các trường HTTP mà proxy xử lý | Phụ thuộc cấu hình, quyền truy cập log và giới hạn dữ liệu |
| Tại endpoint/ứng dụng | Request metadata, kết quả xác thực, hành vi xử lý | Phải bảo vệ quyền riêng tư, secrets và tính toàn vẹn log |
| Ngoài IPsec VPN tunnel | Outer headers và thông số tunnel | Không đọc được nội dung bên trong tunnel chỉ nhờ capture |
| Sau điểm kết thúc VPN | Luồng IP đã giải mã theo quyền quan sát | Nếu ứng dụng dùng HTTPS, HTTP vẫn mã hóa tiếp |

**TLS 1.3 không có nghĩa mọi handshake metadata đều ẩn**: tùy ECH và cấu hình, một số trường như SNI có thể còn nhìn thấy; cũng không nên giả định chứng chỉ máy chủ luôn xuất hiện dưới dạng plaintext. Chỉ dùng signature trên **metadata thật sự quan sát được**.

### 8.1. Các hướng giải quyết hợp pháp

- **Đưa phát hiện đến đúng điểm quan sát:** WAF/API gateway/application logs sau nơi TLS được kết thúc hợp lệ.
- **NIDS kết hợp endpoint telemetry:** Theo dõi network flow và hành vi host khi payload bị mã hóa.
- **TLS inspection có kiểm soát:** Chỉ áp dụng tại nơi có quyền và chính sách phù hợp; quản lý certificate/private key, loại dữ liệu nhạy cảm và tác động đến bảo mật người dùng.
- **Bổ sung hành vi và metadata:** DNS logs, egress allowlist, kết nối bất thường, tần suất, fingerprint mạng phù hợp theo năng lực sản phẩm; không biến fingerprint đơn lẻ thành bằng chứng xâm nhập.

Không hạ bảo mật TLS của ứng dụng chỉ để sensor dễ đọc payload. Cần cân nhắc **mục tiêu phát hiện, bảo vệ dữ liệu và vị trí thực thi**.

## 9. Vị trí NIDS/IPS, phân đoạn mạng và thay đổi đường đi

~~~mermaid
flowchart TB
    I["Internet"] --> F["Firewall / IPS inline"]
    F --> W["DMZ / Web API"]
    W --> A["App zone"]
    A --> D[("DB zone")]
    F -. "Mirror/TAP nếu hỗ trợ" .-> N["NIDS sensor"]
    A -. "East-west visibility" .-> E["Sensor nội bộ"]
    N --> S["SIEM / điều tra"]
    E --> S
~~~

**North–south monitoring** có thể phát hiện traffic từ Internet hoặc đi ra Internet. **East–west monitoring** quan trọng khi tài khoản/workload trong một zone bị xâm nhập và cố truy cập zone khác. Đặt sensor phải căn cứ **data flow và threat model**, không chỉ chỗ dễ lắp đặt.

### 9.1. Tác động của NAT và routing

- Nếu sensor đặt **trước NAT**, IP mà nó thấy có thể khác IP được ứng dụng thấy.
- Nếu sensor đặt **sau NAT**, nhiều client có thể xuất hiện dưới cùng một địa chỉ dịch.
- Route bất đối xứng hoặc load balancing khiến sensor chỉ thấy một chiều, làm sai flow state hoặc thiếu gói.
- Các nhánh HA firewall thay đổi sau failover; phải xác minh sensor còn nhận traffic ở cả hai đường.
- VLAN/trunk, overlay VXLAN, tunneling và cloud virtual networking cần khả năng giải mã phù hợp để tránh phân tích nhầm header.

### 9.2. Chữ ký không thay thế chính sách truy cập

Một rule phát hiện cổng quản trị bị truy cập không thay cho **firewall DENY** hoặc **xác thực quản trị**. Thiết kế phòng vệ nên: hạn chế kết nối bằng phân đoạn và ACL; xác thực bằng IAM/mTLS/VPN/NAC phù hợp; dùng IDS/IPS để phát hiện/chặn những mẫu hành vi đáng ngờ mà các lớp trước không xử lý đủ.

## 10. IDS cảnh báo, IPS chặn và chính sách fail-open/fail-closed

Quyết định đưa signature vào **IPS block mode** cần thận trọng hơn alert-only. Một false positive trên rule áp vào DNS, payment hoặc authentication có thể gây gián đoạn lớn.

| Chế độ/hành động | Hành vi | Khi cân nhắc |
| --- | --- | --- |
| **Alert** | Ghi sự kiện, traffic tiếp tục theo các policy khác | Rule mới, rule có độ tin cậy trung bình hoặc cần thêm dữ liệu hiệu chỉnh |
| **Drop / block** | Ngăn gói/luồng thuộc điều kiện match theo nền tảng | Rule đã thử nghiệm tốt, phạm vi rõ ràng, tác động được chấp nhận |
| **Reject** | Có thể gửi phản hồi từ chối/reset theo engine/protocol | Khi hành vi phản hồi là mục tiêu đã duyệt, chú ý tương tác với ứng dụng |
| **Threshold / suppression** | Điều chỉnh thông báo theo tần suất/nguồn | Giảm noise nhưng không tự thay đổi tất cả hành vi enforcement |
| **Disabled** | Không đánh giá rule đó trong tập policy | Rule không phù hợp môi trường, lỗi thời hoặc có vấn đề cần rollback |

**Fail-open:** Khi bộ phận IPS inline không thể kiểm tra, một số triển khai có khả năng tiếp tục cho traffic đi qua. **Fail-closed:** Có thể ngắt traffic khi không thể thực thi chính sách. Hai lựa chọn đều có rủi ro; phải gắn với **loại dịch vụ, độ nhạy dữ liệu và yêu cầu sẵn sàng**.

Không mặc định mọi sensor/IPS có hardware bypass, fail-open hoặc cơ chế hành động giống nhau. Khi cấu hình HA, phải kiểm tra cả tình huống sensor/engine chết nhưng interface vẫn hoạt động.

## 11. Vòng đời của một signature từ phát hiện đến vận hành

Một rule tốt cần có **nguồn gốc, ý nghĩa, bằng chứng thử nghiệm, chủ sở hữu và đường rollback**.

~~~mermaid
flowchart LR
    A["Yêu cầu phát hiện / threat intelligence"] --> B["Viết hoặc chọn rule"]
    B --> C["Xác định scope và dữ liệu kiểm thử"]
    C --> D["Validate cú pháp & replay offline"]
    D --> E["Triển khai alert-only / canary"]
    E --> F["Đo FP, TP, performance"]
    F --> G{"Đủ tin cậy?"}
    G -- "Chưa" --> B
    G -- "Đạt" --> H["Phê duyệt action, rollout"]
    H --> I["Theo dõi, review, expire/rollback"]
    I --> A
~~~

### Bước 1. Nêu giả thuyết và hành vi cần phát hiện

Thay vì mô tả “cần chặn hacker”, hãy viết:

> “Cần phát hiện request HTTP plaintext đến nhóm ứng dụng lab có User-Agent mang marker TrainingClient/1.0, nhằm kiểm tra pipeline rule và logging.”

Với rule production, nêu **tài sản, kỹ thuật, điều kiện trước, độ tin cậy, nguồn quan sát, action mong muốn và giới hạn**.

### Bước 2. Xác định phạm vi bằng tài sản và data flow

Chọn cụ thể **HOME_NET**, source/destination zone, hướng traffic, port, giao thức, ứng dụng, các network exception và thông tin NAT. Đừng chạy một rule giả định áp dụng cho “mọi IP/port/protocol” khi mục tiêu chỉ liên quan một endpoint cụ thể.

### Bước 3. Chuẩn bị dữ liệu có nhãn

Tập kiểm thử cần gồm:

- **Positive samples:** Mẫu lab hợp lệ để chứng minh chữ ký khớp khi điều kiện đúng.
- **Negative samples:** Traffic bình thường gần giống mẫu, các protocol/port khác và tình huống không nên match.
- **Biến thể phân đoạn/stream:** Request bị chia qua nhiều TCP segment, kết nối hai chiều, retransmission, trường hợp parser có thể bỏ sót.
- **Mẫu môi trường thực tế được phép dùng:** Được xử lý để bảo vệ dữ liệu nhạy cảm, đáp ứng quy định lưu trữ.

**Không dùng payload khai thác thật lên hệ thống không được phép để “thử IPS”.** Có thể kiểm thử bằng marker vô hại, trace/pcap được cấp quyền và kịch bản kiểm chứng trong lab.

### Bước 4. Kiểm tra cú pháp và replay

Với engine như Suricata, quy trình thường có **rule validation** và chạy trên **pcap offline** trong môi trường thử nghiệm. Ví dụ ý tưởng (tên file và option phụ thuộc phiên bản/cấu hình):

~~~text
rule file lab.rules -> syntax validation -> offline sample.pcap
                                       -> alert logs -> compare expected
~~~

Đảm bảo kiểm thử **cùng engine version, parser settings, HOME_NET và relevant features** với hệ thống đích; thành công trên dữ liệu mô phỏng không chứng minh production traffic sẽ được thấy.

### Bước 5. Đưa vào chế độ quan sát

Triển khai với action alert ở nhóm nhỏ hoặc chế độ monitor nếu nền tảng cho phép. Thu alert metadata, tỉ lệ alert trên tổng request/flow phù hợp, false positives được xác nhận, CPU/memory, packet drops và độ trễ.

### Bước 6. Tuning theo đúng nguyên nhân

Có thể hiệu chỉnh **source/destination**, zone, flow direction, app-layer buffer, điều kiện content bổ sung, exception có scope nhỏ, threshold và action. Mỗi lần tuning cần kiểm tra lại **positive lẫn negative**: giảm alert bằng cách tắt rule hoặc loại cả vùng mạng quá rộng có thể che giấu detection gap.

### Bước 7. Rollout và rollback có kiểm soát

Rule có tác động block phải được review, có owner và lịch rollback. Đối với traffic trọng yếu, theo dõi **HTTP error, DNS failure, latency, session reset, chính sách DENY/ALLOW** trước và sau rollout.

### Bước 8. Cập nhật và nghỉ hưu rule

Signature có thể lỗi thời khi ứng dụng được vá, protocol thay đổi hoặc IOC hết giá trị. Cần quản lý **signature set version, SID/rev, changelog, thời điểm phát hành, nguồn threat intel, mức độ tin cậy, ngày rà soát và các ngoại lệ**. Bản cập nhật tự động cũng có thể gây lỗi; nên kiểm thử và triển khai theo đợt.

## 12. Thiết kế rule để giảm false positive

| Thiết kế yếu | Thiết kế chính xác hơn | Lý do |
| --- | --- | --- |
| Match chuỗi trên raw payload bất kỳ | Chọn đúng app-layer buffer như URI, HTTP header hoặc DNS query | Tránh match vào dữ liệu không liên quan |
| Match mọi source/destination | Giới hạn zone, dịch vụ, hướng và asset liên quan | Tăng ngữ cảnh và giảm phạm vi |
| Dùng IP IOC cũ để block toàn doanh nghiệp | Kiểm tra freshness, ownership, CDN/shared hosting, ngữ cảnh | Giảm rủi ro chặn dịch vụ hợp lệ |
| Match chuỗi ngắn dễ trùng | Kết hợp nhiều điều kiện đặc trưng, nếu phù hợp với detector | Giảm số match tình cờ |
| Không xét TCP reassembly | Dùng parser/flow awareness và test phân mảnh | Giảm bỏ sót do chuỗi bị chia đoạn |
| Coi signature match là “compromised” | Mức cảnh báo phản ánh đúng điều kiện đã quan sát và bằng chứng | Tránh khẳng định quá mức khi điều tra |
| Bật drop ngay sau khi viết | Validate, alert-only, đo FP/FN rồi mới cân nhắc block | Tránh làm hỏng dịch vụ vì rule chưa thử nghiệm |

**Tuning không chỉ tối ưu độ chính xác.** Rule rất phức tạp, regex chi phí cao hoặc tạo quá nhiều state có thể tăng CPU và memory, dẫn đến **packet drop** và **giảm độ phủ quan sát**. Cần cân bằng độ phức tạp với năng lực sensor ở tải thực.

### 12.1. Fast pattern, rule ordering và performance

Nhiều engine dùng **prefilter/fast pattern matching** để giảm số rule phải xử lý đầy đủ. Một số rule có keyword tối ưu như **fast_pattern** theo cú pháp hỗ trợ. Nhưng chọn một chuỗi phổ biến, quá ngắn hoặc match trên buffer sai có thể khiến performance kém.

Không mặc định **“rule ở trên sẽ được thực thi trước rồi dừng ở rule đầu tiên”** như firewall ACL first-match. IDS/IPS có thể đánh giá nhiều signatures trên cùng traffic, có **action precedence**, rule groups và điều kiện threshold riêng. Điều đó quyết định **số alert**, khả năng **drop** và hành vi của các rule tương tác.

## 13. Thực hành offline: mô phỏng signature matching trên sự kiện log

Bài lab sau chỉ xử lý **dữ liệu HTTP đã mô phỏng**; không kết nối mạng, không quét dịch vụ, không gửi request và không thực thi rule IPS thật.

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class HttpEvent:
    id: str
    direction: str
    protocol: str
    established: bool
    user_agent: str
    should_alert: bool  # Nhãn ground truth của dữ liệu lab


events = [
    HttpEvent("e1", "to_server", "http", True,
              "TrainingClient/1.0", True),
    HttpEvent("e2", "to_server", "http", True,
              "Mozilla/5.0", False),
    HttpEvent("e3", "to_client", "http", True,
              "TrainingClient/1.0", False),
    HttpEvent("e4", "to_server", "dns", True,
              "TrainingClient/1.0", False),
    HttpEvent("e5", "to_server", "http", True,
              "lab-trainingclient/1.0 variant", True),
    HttpEvent("e6", "to_server", "http", False,
              "TrainingClient/1.0", False),
]


def signature_match(event: HttpEvent) -> bool:
    """Mô phỏng điều kiện http + established/to_server + content/nocase."""
    return (
        event.protocol == "http"
        and event.established
        and event.direction == "to_server"
        and "trainingclient/1.0" in event.user_agent.lower()
    )


tp = fp = tn = fn = 0
for event in events:
    hit = signature_match(event)
    print(event.id, "ALERT" if hit else "NO_ALERT")
    if hit and event.should_alert:
        tp += 1
    elif hit and not event.should_alert:
        fp += 1
    elif not hit and event.should_alert:
        fn += 1
    else:
        tn += 1

print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
precision = tp / (tp + fp) if tp + fp else 0
recall = tp / (tp + fn) if tp + fn else 0
print(f"Precision={precision:.0%}; Recall={recall:.0%}")
~~~

Kết quả dự kiến:

~~~text
e1 ALERT
e2 NO_ALERT
e3 NO_ALERT
e4 NO_ALERT
e5 ALERT
e6 NO_ALERT
TP=2 FP=0 FN=0 TN=4
Precision=100%; Recall=100%
~~~

**Diễn giải:** Tập dữ liệu này quá nhỏ và được thiết kế để khớp đúng nên Precision/Recall đạt 100% **không thể dùng làm cam kết vận hành**. Hàm Python chỉ kiểm tra trường đã được giải mã sẵn; nó không phân tích pcap, không tái dựng TCP, không xác minh HTTP và không thể thay rule engine thực tế.

### Bài tập mở rộng

1. Thêm sự kiện User-Agent chứa marker nhưng được gửi bởi **hoạt động kiểm thử hợp lệ**; thay nhãn **should_alert** theo mục tiêu điều tra và phân tích FP.
2. Thêm sự kiện HTTP hợp lệ cần cảnh báo nhưng viết User-Agent khác mẫu; minh họa **FN** và thảo luận giới hạn coverage của signature.
3. Thêm trường **zone** và chỉ cho phép rule áp dụng với source thuộc vùng ngoài và destination thuộc vùng lab; so sánh số alert.
4. Thêm đánh dấu **transport_is_encrypted**: giải thích vì sao NIDS không được cấp plaintext không thể chạy hàm này trên HTTP header đang ở trong TLS.

## 14. Từ alert tới điều tra: những trường dữ liệu cần có

Một sự kiện signature-based IDS/IPS nên cung cấp đủ **bối cảnh tái hiện quyết định**, nhưng tránh đưa secrets và dữ liệu nhạy cảm vào log.

| Trường | Công dụng |
| --- | --- |
| Timestamp với múi giờ chuẩn | Tương quan sự kiện giữa sensor, firewall, DNS, server và endpoint |
| Sensor ID, interface/zone, vị trí capture | Biết traffic được nhìn thấy ở đâu và có bị NAT/định tuyến thay đổi không |
| Source/destination IP, port, protocol | Xác định flow và bên liên quan, sau khi kiểm tra NAT |
| Direction/flow ID, session metadata | Tương quan nhiều packet/alert cùng một kết nối |
| SID, revision, signature message | Biết **đúng rule** và phiên bản nào đã match |
| Signature source, category, severity, confidence | Đánh giá chất lượng rule; không tự đồng nghĩa mức độ nghiêm trọng thực tế |
| Action: alert/drop/reject | Phân biệt quan sát và enforcement |
| App protocol, fields đã dùng match | Hiểu vì sao điều kiện signature khớp |
| Hostname/SNI/DNS query khi nhìn thấy hợp lệ | Hỗ trợ định danh dịch vụ; cần đánh giá spoofing và encrypted metadata |
| Asset owner, environment và business context | Phân biệt production/staging, tài sản nhạy cảm, traffic kiểm thử |
| Log reference/packet reference được phép lưu | Truy xuất bằng chứng mà không sao chép plaintext nhạy cảm bừa bãi |

### 14.1. Cách xử lý một cảnh báo

1. **Xác nhận nguồn:** Sensor khỏe không? Alert có timestamp, SID/rev, event type và packet/flow context hợp lệ không?
2. **Hiểu rule:** Chính xác trường nào khớp? Match theo content, flow, DNS name, IOC hay decoded protocol?
3. **Bổ sung tài sản:** IP đó thuộc máy/service nào ở thời điểm alert? Có NAT, load balancer, VPN, proxy hoặc cloud NAT không?
4. **Tương quan nguồn khác:** Firewall action, WAF, DNS, application logs, EDR, vulnerability inventory hoặc thay đổi triển khai.
5. **Phân loại:** False positive, hoạt động hợp lệ nhưng vi phạm policy, nghi ngờ cần điều tra hoặc xâm nhập được xác nhận.
6. **Ứng phó có phạm vi:** Khi đủ bằng chứng, áp dụng kiểm soát như giới hạn kết nối, cập nhật rule, điều chỉnh truy cập, cô lập host hay sửa ứng dụng theo playbook.
7. **Phản hồi về rule:** Ghi bằng chứng cho việc nâng mức action, tuning, giảm severity hoặc hết hiệu lực signature.

### 14.2. Ví dụ sự kiện JSON minh họa

Đây là **schema tự mô tả cho bài học**, không tuyên bố trùng với mọi bản ghi EVE JSON của Suricata:

~~~json
{
  "timestamp": "2026-01-10T10:15:00Z",
  "sensor": "nids-dmz-lab",
  "event_type": "alert",
  "source_ip": "198.51.100.10",
  "destination_ip": "192.0.2.10",
  "destination_port": 80,
  "protocol": "TCP",
  "application_protocol": "http",
  "signature_id": 1000001,
  "signature_revision": 1,
  "signature_name": "LAB HTTP User-Agent TrainingClient",
  "action": "alert",
  "observed_field": "http.user_agent",
  "observed_value": "TrainingClient/1.0",
  "assessment": "untriaged"
}
~~~

Các địa chỉ **192.0.2.0/24** và **198.51.100.0/24** là dải tài liệu TEST-NET. Trường **observed_value** chỉ minh họa trong lab; production cần chính sách **data minimization**, masking, retention và quyền truy cập log phù hợp.

## 15. Case study: chữ ký DNS làm gián đoạn truy vấn hợp lệ

**Bối cảnh giả định:** Doanh nghiệp bật một IPS tại đường ra DNS từ mạng nhân viên. Một chữ ký dựa trên tên miền trong danh sách IOC được cấu hình **drop** ngay khi cập nhật. Vài phút sau, một bộ phận không truy cập được ứng dụng đối tác.

### 15.1. Điều tra theo thứ tự

| Bước | Câu hỏi | Bằng chứng nên xem |
| --- | --- | --- |
| Xác nhận tác động | Truy vấn DNS thất bại là do IPS hay resolver/ISP? | DNS client logs, resolver logs, service health |
| Xác định rule | SID/rev nào bắt đầu có hit tăng và action drop? | IPS alert logs, deployment history |
| Kiểm tra nội dung khớp | Exact domain, suffix, substring, DNS type hay metadata nào khớp? | Rule definition, parsed DNS fields |
| Đánh giá nguồn IOC | Chỉ báo còn mới? Domain/IP có thể dùng chung hoặc được chuyển chủ? | Threat intel metadata và nguồn được phép |
| Kiểm tra phạm vi | Rule áp dụng toàn doanh nghiệp hay chỉ một nhóm? | Zone, source/destination, policy bindings |
| Quyết định điều chỉnh | Có thể thu hẹp, dùng alert-only hoặc rollback rule mới không? | Approval, impact và phương án kiểm thử |
| Xác nhận phục hồi | Domain hợp lệ hoạt động lại, rule cần thiết còn tác dụng? | DNS query test, allow/deny matrix, business telemetry |

**Nguyên nhân gốc giả định:** IOC đã hết giá trị hoặc rule so khớp chuỗi con khiến tên miền hợp lệ bị match. **Lưu ý:** Đây là tình huống minh họa, không chứng minh mọi trường hợp gián đoạn DNS đều do chữ ký.

### 15.2. Biện pháp khắc phục

- Chuyển rule gây tác động sang **alert-only** hoặc rollback theo quy trình nếu chưa đủ bằng chứng để block; không tắt toàn bộ IPS khi chỉ một rule có vấn đề.
- Bổ sung kiểm tra chính xác domain boundary, nguồn IOC, khoảng thời gian tin cậy và phạm vi đối tượng; kiểm thử lại DNS/HTTPS hợp lệ.
- Tách **rule thử nghiệm** và **rule đã xác minh đủ điều kiện block**.
- Đặt canary/monitor cho truy vấn DNS, API trọng yếu, độ trễ và drop rate trước mỗi đợt cập nhật.
- Giữ rule ID, revision, thời điểm thay đổi, owner, kết quả kiểm thử và phương án rollback trong hồ sơ.

**Bài học:** Tác dụng của IPS chỉ có giá trị khi **độ chính xác, phạm vi và tính sẵn sàng** được quản lý. Một signature khớp kỹ thuật có thể vẫn gây hại nếu action và scope sai.

## 16. Ma trận kiểm thử trước khi đưa signature vào production

| Test ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| SIG-01 | HTTP plaintext trong lab có User-Agent marker và đúng flow | Có alert theo SID/rev kỳ vọng |
| SIG-02 | HTTP bình thường không có marker | Không có alert của rule lab |
| SIG-03 | Chuỗi marker xuất hiện ở buffer không liên quan | Không match nếu rule chỉ xét User-Agent |
| SIG-04 | Lưu lượng DNS thay vì HTTP | Không match rule HTTP |
| SIG-05 | HTTP trong TLS không giải mã tại sensor | Không có khẳng định match payload HTTP từ traffic mã hóa |
| SIG-06 | Traffic từ source/zone ngoài scope rule | Không match rule giới hạn phạm vi |
| SIG-07 | Marker chia qua nhiều TCP segment trong lab | Phát hiện theo khả năng reassembly/parser đã kiểm chứng |
| SIG-08 | Rule mới ở alert-only | Không drop traffic chỉ bởi action alert |
| SIG-09 | IPS block được phê duyệt trong lab | Chặn đúng mẫu positive, không làm hỏng negative samples |
| SIG-10 | Packet loss/sensor overload mô phỏng trong môi trường được phép | Có metric/cảnh báo về mất khả năng quan sát |
| SIG-11 | Firewall HA chuyển đường qua node khác | Sensor tiếp tục nhìn thấy đúng flow hoặc báo blind spot |
| SIG-12 | Update rule set gây lỗi/FP | Có rollback rule/version và xác nhận dịch vụ hồi phục |
| SIG-13 | NAT/proxy thay đổi IP thấy tại sensor | Asset correlation vẫn xác định được nguồn đúng |
| SIG-14 | DNS qua resolver nội bộ hoặc DoH/DoT | Không suy rằng rule DNS/53 phải nhìn thấy mọi truy vấn |
| SIG-15 | Tăng tải ứng dụng bình thường | CPU/memory/latency/drop rate nằm trong mức đã được duyệt |

Mỗi ca nên ghi **engine version, config version, sensor placement, source/destination, giao thức, nhãn ground truth, SID/rev, action, kết quả thực và bằng chứng log/pcap được phép**. Kiểm tra ở chế độ **passive trước**, sau đó mới cân nhắc thay đổi enforcement nếu đã phê duyệt.

## 17. Giám sát chất lượng phát hiện và độ tin cậy cảm biến

Giám sát IDS/IPS cần bao gồm cả **sức khỏe thiết bị** và **chất lượng chữ ký**:

| Nhóm | Chỉ số/tín hiệu | Hành động khi bất thường |
| --- | --- | --- |
| Capture | Packet drops, missed flows, interface errors, SPAN congestion | Kiểm tra topology, băng thông, capture mode, sensor sizing |
| Engine | CPU, memory, flow table, reassembly/decoder errors | Tối ưu rule set, cấu hình parser hoặc tăng năng lực |
| Detection | Alert volume/SID, phân bố theo zone, false positive được xác minh | Điều chỉnh scope, ngưỡng, mức độ và nội dung rule |
| Coverage | Những luồng/protocol bị mã hóa hoặc không được sensor nhìn thấy | Điều chỉnh placement, tích hợp endpoint/WAF/logs |
| Update | Signature age, feed freshness, revision drift giữa node | Rà soát nguồn, lịch update và config synchronization |
| IPS impact | Drop/reject theo SID, HTTP errors, DNS failures, latency | Kiểm tra tương quan với rollout, tuning hoặc rollback |
| Response | Thời gian phân loại alert, tỷ lệ được triage, alert trùng | Tối ưu phân nhóm/correlation, runbook, phân công owner |
| Governance | Rule không có owner, rule hết hạn, exception không được review | Audit và thu hồi rule/exception đúng quy trình |

**Không coi “số alert cao” là bằng chứng hệ thống phát hiện tốt.** Nó có thể phản ánh lưu lượng hợp lệ, rule quá rộng hoặc tấn công thực. **Không coi “số alert thấp” là an toàn**, vì sensor có thể mù, thiếu chữ ký hoặc không thấy TLS payload.

### 17.1. Chất lượng rule giữa các environment

Một rule phù hợp với **Production Web API** chưa chắc phù hợp **Dev/QA**, nơi có công cụ kiểm thử và traffic bất thường được phê duyệt. Do vậy, có thể dùng **policy/rule profile theo environment**, nhưng phải tránh cho Dev/QA trở thành đường vòng sang Prod chỉ vì cho phép traffic thử nghiệm.

Một ví dụ quản trị:

~~~text
Signature:       LAB_HTTP_UA_001
Owner:           SOC / Detection Engineering
Scope:           Lab HTTP service only
Environment:     Staging training
Default action:  Alert
Expected FP:     Kết nối test hợp lệ nếu dùng cùng marker
Validation:      Positive/negative fixture
Review date:     Theo lịch vận hành
Rollback:        Disable chỉ rule này qua quy trình cấu hình
~~~

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “Signature-based IDS phát hiện được mọi tấn công.” | Chỉ phát hiện những hành vi/mẫu phù hợp rule và được sensor nhìn thấy; chưa biết hoặc biến thể có thể bị bỏ sót. |
| “Signature match nghĩa là đã khai thác thành công.” | Match chỉ xác nhận điều kiện của rule; cần điều tra với asset và application evidence. |
| “IDS và IPS giống nhau vì cùng dùng chữ ký.” | IDS thường cảnh báo ngoài luồng; IPS có thể chặn khi nằm trên đường xử lý traffic. |
| “Bật drop cho mọi chữ ký sẽ an toàn hơn.” | FP có thể làm ngừng dịch vụ; action cần dựa trên thử nghiệm và rủi ro. |
| “Chữ ký là chữ ký số.” | Signature ở đây là mẫu điều kiện, không phải chứng thực mật mã. |
| “NIDS luôn đọc được nội dung HTTPS.” | TLS mã hóa payload; cần điểm quan sát được quyền giải mã hoặc telemetry ở endpoint. |
| “Một regex trong raw packet đủ để thấy mọi HTTP request.” | TCP segmentation, retransmission và protocol normalization có thể khiến cách quét thô bỏ sót hoặc match sai. |
| “Không có alert nghĩa là không bị tấn công.” | Có thể sensor không thấy traffic, packet loss, thiếu rule hoặc mẫu bị mã hóa. |
| “Một IP IOC trùng là bằng chứng endpoint độc hại.” | IP có thể dùng chung hoặc IOC cũ; phải xác minh ngữ cảnh và nguồn. |
| “Rule đầu tiên khớp luôn quyết định giống firewall ACL.” | Engine IDS/IPS có thể đánh giá nhiều signature, action precedence và policy groups khác first-match. |
| “Có IDS/IPS thì không cần firewall, phân đoạn và xác thực.” | Mỗi lớp xử lý một rủi ro khác nhau; IDS/IPS bổ sung vào phòng vệ nhiều lớp. |
| “Rule hợp lệ về cú pháp chắc chắn có hiệu quả.” | Còn cần đúng buffer, flow, HOME_NET, vị trí capture, performance và test ngữ nghĩa. |
| “Khi firewall failover, sensor luôn thấy đầy đủ traffic.” | Đường đi có thể thay đổi và tạo vùng mù nếu chưa thiết kế mirror/sensor cho cả hai nhánh. |

## 19. Câu hỏi tự kiểm tra

1. **Signature-based detection quan sát và đối chiếu những gì?** Các trường/gói/luồng đã thu thập với mẫu và điều kiện được định nghĩa trong rule.
2. **Vì sao một dấu hiệu cùng chuỗi nhưng khác buffer có thể cho kết quả khác?** HTTP User-Agent, URI và body có ý nghĩa khác nhau; sticky buffer và parser giới hạn vùng match.
3. **IDS alert có đồng nghĩa traffic bị chặn không?** Không. Chặn chỉ có thể xảy ra nếu cơ chế IPS/enforcement và hành động phù hợp thực sự được áp dụng.
4. **Vì sao cần stream reassembly?** Vì cùng một chuỗi ứng dụng có thể trải trên nhiều TCP segment hoặc đến không theo thứ tự.
5. **Một alert trùng signature CVE có chứng minh server bị khai thác thành công không?** Không; cần xác minh phiên bản dễ bị ảnh hưởng, khả năng xử lý request, trạng thái hệ thống và bằng chứng khác.
6. **True Positive khác False Positive như thế nào?** TP là cảnh báo trùng sự kiện thật sự cần phát hiện; FP là cảnh báo khi sự kiện đó không xảy ra.
7. **Khi nào rule có nguy cơ false negative cao?** Khi chưa có mẫu, mẫu thay đổi, nội dung bị TLS mã hóa, parser thiếu hỗ trợ hoặc sensor mất gói/không đúng vị trí.
8. **Vì sao HOME_NET phải khai báo chính xác?** Vì scope ảnh hưởng điều kiện match, nên có thể tạo vùng mù hoặc alert sai.
9. **Khi nào nên cân nhắc đưa một rule từ alert-only sang drop?** Sau khi đã xác minh mục tiêu, phạm vi, hiệu năng, FP/FN, tác động nghiệp vụ và có phê duyệt/rollback.
10. **Làm sao phân biệt “không có tấn công” với “sensor không thấy traffic”?** Kiểm tra health/capture metrics, topology, packet drops, nguồn log bổ sung và bài test positive có kiểm soát.

### Bài tập tình huống

Hệ thống có public Web API dùng HTTPS, một NIDS đặt trước reverse proxy và một IPS đặt ở đường kết nối HTTP nội bộ từ proxy đến backend. Đội SOC muốn tạo chữ ký dựa trên URI và User-Agent của HTTP request:

1. Vẽ các vị trí sensor và cho biết **thiết bị nào có thể quan sát những trường nào**, khi proxy kết thúc TLS rồi gửi HTTP tới backend.
2. Viết **giả thuyết phát hiện** chỉ dùng marker vô hại và một rule minh họa có source/destination, flow, buffer và action **alert**.
3. Định nghĩa ít nhất ba **positive samples** và năm **negative samples**, gồm request có cùng chuỗi ở trường khác.
4. Nêu lý do vì sao rule HTTP plaintext ở NIDS ngoài TLS **không tự phát hiện** URI/User-Agent của HTTPS.
5. Lập kế hoạch chuyển sang IPS block mode nếu có kết quả kiểm thử tốt, với owner, phê duyệt, canary và rollback.
6. Xác định những metric giúp phát hiện mất khả năng quan sát khi firewall chuyển HA.

## 20. Checklist vận hành chữ ký IDS/IPS

- [ ] Đã xác định tài sản, threat scenario, luồng dữ liệu và vị trí sensor?
- [ ] Đã biết rule đang phân tích raw packet, stream hay app-layer field?
- [ ] HOME_NET, EXTERNAL_NET, zone, source/destination, protocol và port đã khớp môi trường?
- [ ] Đã xác minh khả năng quan sát HTTP, DNS, TLS, VPN và traffic mã hóa?
- [ ] Engine/version, keyword, SID/rev và rule set được quản lý có phiên bản?
- [ ] Rule đã có positive và negative samples được gắn nhãn?
- [ ] Đã kiểm tra parser/reassembly và các nhánh traffic qua NAT, proxy, HA hoặc cloud?
- [ ] Đã đo false positives, misses, throughput, packet drops và độ trễ?
- [ ] Action alert/drop/reject và fail-open/fail-closed phù hợp chính sách?
- [ ] Đã thử trên lab/canary/monitor mode trước khi thay đổi enforcement?
- [ ] Có owner, lịch rà soát IOC/signature và chính sách cập nhật/rollback?
- [ ] Alert có đủ metadata để điều tra mà không lộ secrets/PII?
- [ ] Có tương quan giữa signature, firewall, DNS, WAF, endpoint và application logs?
- [ ] Có kiểm thử cả traffic cần **ALLOW** và trường hợp cần **DENY/BLOCK**?
- [ ] Có kế hoạch kiểm tra coverage sau thay đổi routing, TLS termination và failover?

**Kết luận:** Signature-based detection giúp IDS/IPS phát hiện nhanh **những mẫu đã được định nghĩa**, nhưng giá trị an ninh chỉ xuất hiện khi **mẫu đúng, luồng được quan sát đầy đủ, rule được kiểm thử và alert được diễn giải theo bằng chứng**. Để xây dựng mạng an toàn, hãy kết hợp chữ ký với **segmentation, firewall, xác thực, TLS, giám sát endpoint và quy trình phản ứng**, đồng thời đánh giá cả hiệu quả phát hiện lẫn rủi ro gián đoạn khi bật IPS chặn.
