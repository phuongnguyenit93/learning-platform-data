# Intrusion Detection System (IDS): phát hiện xâm nhập trong hệ thống mạng

**Intrusion Detection System (IDS)** là hệ thống giám sát những hoạt động trên mạng hoặc trên máy chủ để **phát hiện dấu hiệu tấn công, hành vi trái chính sách hoặc hoạt động bất thường**, sau đó tạo thông báo và bằng chứng cho quá trình điều tra. IDS giúp đội bảo mật nhận biết một số hoạt động mà firewall, VPN hoặc cơ chế xác thực chỉ kiểm soát theo những tiêu chí khác.

Trong chương **IDS và IPS** của học phần **SECURITY_NETWORK_SECURITY**, cần hiểu IDS như một **lớp phát hiện** bổ sung cho phân đoạn, firewall, VPN, kiểm soát truy cập, bảo vệ DNS, Wi-Fi và cloud. Nó không tự làm cho mạng an toàn: giá trị của IDS phụ thuộc vào **điểm quan sát, loại dữ liệu được thu thập, chất lượng detection rule, khả năng phân tích cảnh báo và quy trình ứng phó**.

Bài học giúp người học phân biệt IDS với IPS, NIDS với HIDS, giải thích cách sensor xử lý sự kiện, lập kế hoạch bao phủ mạng, đọc và xác minh cảnh báo, giảm false positive, nhận biết false negative và tích hợp IDS vào kiến trúc phòng vệ nhiều lớp.

## 1. IDS giải quyết bài toán nào?

Giả sử firewall cho phép các máy ứng dụng kết nối API nội bộ qua TCP/443. Chính sách này đúng với nghiệp vụ. Tuy nhiên một máy ứng dụng bị chiếm quyền vẫn có thể gửi những yêu cầu bất thường tới API qua **đường vốn được cho phép**. Firewall L3/L4 thường không biết yêu cầu đó có biểu hiện khai thác lỗ hổng, brute force hay chuyển dữ liệu bất thường hay không.

IDS có thể theo dõi những tín hiệu phù hợp tại điểm có khả năng quan sát, ví dụ:

- Một nguồn mới liên tục thử kết nối tới nhiều cổng hoặc nhiều host trong thời gian ngắn.
- Một luồng mạng có mẫu payload trùng chữ ký tấn công đã biết, nếu sensor nhìn được nội dung phù hợp.
- Một host đột nhiên liên hệ tới máy quản trị không nằm trong dependency thông thường.
- Dịch vụ có chuỗi lỗi xác thực tăng đột biến, nếu IDS tích hợp log liên quan.
- Một workstation gửi truy vấn DNS với tần suất hoặc cấu trúc rất khác baseline.
- Một máy chủ phát sinh kết nối outbound bất thường ngay sau sự kiện host đáng nghi.

**IDS báo tín hiệu cần điều tra, không phải máy xác nhận tấn công tuyệt đối.** Dữ liệu của một sensor có thể thiếu hoặc bị méo bởi mã hóa, NAT, mất gói, cấu hình mirror và vị trí đặt sensor.

### 1.1. Detection khác prevention

| Năng lực | IDS | IPS |
|---|---|---|
| Mục tiêu chính | Phát hiện và cảnh báo hoạt động đáng ngờ | Phát hiện và có thể ngăn hoạt động theo chính sách |
| Vị trí thường gặp | Ngoài luồng truyền, nhận traffic mirror/TAP; hoặc agent trên host | Trong đường truyền (inline) hoặc điểm enforcement |
| Kết quả điển hình | Alert, event, metadata, packet evidence | Alert kèm drop, reject, reset, block hoặc action khác |
| Tác động lên traffic | IDS thụ động thông thường không chặn gói | Quyết định chặn có thể làm thay đổi traffic thực |
| Rủi ro vận hành | Bỏ sót, cảnh báo nhiễu, quá tải sensor | Tất cả rủi ro phát hiện và thêm nguy cơ chặn nhầm dịch vụ hợp lệ |
| Điều kiện hiệu quả | Sensor nhìn thấy đủ dữ liệu, detection và triage tốt | Ngoài detection còn cần inline enforcement, hiệu năng và chính sách chặn phù hợp |

Một công cụ có thể hỗ trợ cả IDS lẫn IPS tùy **chế độ triển khai**. Đừng kết luận sensor đã chặn traffic chỉ vì tên sản phẩm có chữ IPS hoặc rule có mức cảnh báo cao. Cần kiểm tra **action đã thực thi** và vị trí đặt thiết bị.

## 2. Nguyên lý hoạt động của IDS

Một IDS điển hình có bốn khâu: **thu thập → phân tích → tạo sự kiện/cảnh báo → xử lý kết quả**.

~~~mermaid
flowchart LR
    T[Traffic / host events] --> S[Sensor thu thập]
    S --> D[Decode / phân tích luồng]
    D --> E[Detection engine]
    R[Rules / baseline / intelligence] --> E
    E --> L[Event / alert]
    L --> C[Collector / SIEM]
    C --> SOC[Phân tích và phản ứng]
~~~

**Thu thập:** NIDS lấy packet hoặc flow ở một điểm mạng; HIDS lấy event và trạng thái host. **Giải mã/chuẩn hóa:** hệ thống nhận biết protocol, session, IP, port, một số thông tin ứng dụng. **Phát hiện:** so với chữ ký, hành vi kỳ vọng, quy tắc phân tích hoặc dữ liệu threat intelligence. **Ghi nhận:** tạo event có thời gian, nguồn, đích, loại cảnh báo và bằng chứng. **Ứng phó:** người vận hành hoặc hệ thống tự động đánh giá mức độ và quyết định thao tác an toàn.

Một cảnh báo có thể bị thiếu ở bất kỳ khâu nào: sensor không nhận packet, parser không nhận giao thức, payload đã mã hóa, rule chưa phù hợp, event không được gửi tới SIEM hoặc alert bị lọc sai.

### 2.1. IDS không có “khả năng nhìn thấy toàn mạng” theo mặc định

IDS là một **điểm quan sát cụ thể**. Một sensor trên đường Internet có thể thấy kết nối đến website public nhưng không thấy VM A nói chuyện trực tiếp với VM B trên cùng vSwitch; một sensor ở VLAN guest không tự nhận traffic của VLAN quản trị.

Vì vậy thiết kế IDS bắt đầu bằng câu hỏi **“Đối thủ cần bị phát hiện đang đi qua đường nào, và sensor có thật sự thấy đường đó không?”**

## 3. Các loại IDS: NIDS, HIDS và cách kết hợp

### 3.1. Network-based IDS (NIDS)

**NIDS** phân tích lưu lượng từ mạng, thường tại TAP, cổng SPAN/mirror, virtual tap, cloud traffic mirroring hoặc điểm xuất flow phù hợp.

Dữ liệu có thể gồm:

- Địa chỉ IP, TCP/UDP port, protocol và hướng kết nối.
- TCP flags, session metadata, kích thước và thời gian.
- DNS, HTTP không mã hóa hoặc protocol khác khi payload có thể quan sát.
- Một số metadata TLS và thông tin chứng chỉ/handshake trong điều kiện phù hợp.
- Chỉ báo payload hoặc mẫu giao thức đáng ngờ nếu parser và rule hỗ trợ.

**Ưu điểm:** quan sát một tập lưu lượng lớn mà không cần cài agent trên từng máy; thuận lợi tại ranh giới giữa các vùng. **Giới hạn:** khó quan sát traffic không đi qua điểm mirror, payload mã hóa, host activity không tạo gói hoặc luồng bị mất packet trước sensor.

### 3.2. Host-based IDS (HIDS)

**HIDS** chạy trên máy hoặc thu nhận nhật ký của host để phát hiện các thay đổi đáng ngờ:

- Thay đổi file cấu hình, binary, service hoặc registry.
- Sự kiện đăng nhập thất bại, quyền quản trị, chạy tiến trình mới.
- Biến động quyền file, tài khoản hoặc tác vụ theo lịch.
- Hoạt động truy cập tài nguyên mà host ghi nhận và chính sách đánh giá.
- Log hệ điều hành, application và security agent.

**Ưu điểm:** có thể thấy hành vi trên endpoint và dữ liệu sau khi ứng dụng đã giải mã; gắn sự kiện với process, user hoặc file khi nguồn cung cấp. **Giới hạn:** phụ thuộc quyền agent, độ tin cậy máy bị theo dõi, tính đầy đủ của log và overhead cục bộ.

### 3.3. Network detection and response (NDR), EDR, SIEM

| Khái niệm | Trọng tâm | Quan hệ với IDS |
|---|---|---|
| **NIDS** | Phân tích lưu lượng mạng để phát hiện | Một loại IDS |
| **HIDS** | Quan sát hành vi/sự kiện trên host | Một loại IDS |
| **IPS** | Phát hiện và chặn tại điểm thực thi | Thường chia sẻ engine detection với IDS |
| **NDR** | Phân tích telemetry mạng và có thể hỗ trợ điều tra/response | Có thể bao gồm chức năng NIDS, tương quan và phân tích hành vi |
| **EDR** | Phát hiện/điều tra/response trên endpoint | Bổ sung thông tin tiến trình, file, user cho NIDS |
| **SIEM** | Tập hợp, tìm kiếm, tương quan nhiều nguồn event | Tiếp nhận và kết hợp alert IDS với firewall/VPN/DNS/IAM |
| **SOAR** | Điều phối quy trình xử lý và tự động hóa phản ứng | Có thể dùng alert IDS làm đầu vào, phải kiểm soát quyền/action |

**Không đồng nhất IDS với SIEM:** một hệ thống SIEM có thể phát hiện dựa trên log; nhưng NIDS thường làm phân tích protocol/packet trước khi gửi alert. Trong thực tế có thể kết hợp để thu được nhiều lớp bằng chứng.

## 4. Phương pháp phát hiện xâm nhập

Một IDS hiện đại có thể kết hợp nhiều phương pháp. Mỗi cách có điểm mạnh và hạn chế.

| Phương pháp | Nguyên lý | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Signature-based** | Match mẫu đã biết, rule protocol, chuỗi byte hoặc hành vi xác định | Có thể giải thích tín hiệu cụ thể, hiệu quả với mẫu đã biết | Dễ bỏ sót biến thể mới; cần cập nhật, có thể false positive |
| **Anomaly-based** | So sánh hoạt động với baseline hoặc phân phối kỳ vọng | Có thể chỉ ra biến động chưa từng có | Baseline sai, thay đổi hợp lệ, thiếu dữ liệu gây nhiễu |
| **Stateful protocol analysis** | Theo dõi trạng thái và kiểm tra hành vi giao thức | Phát hiện vi phạm trình tự hoặc format bất thường | Cần parser chính xác; giao thức mới/mã hóa làm giảm quan sát |
| **Behavioral correlation** | Ghép nhiều event theo host, thời gian hoặc đường tấn công | Thấy chuỗi hoạt động thay vì một gói đơn lẻ | Phụ thuộc enrichment, đồng hồ và chất lượng dữ liệu |
| **Threat intelligence matching** | So khớp địa chỉ, domain, hash hoặc indicator | Hữu ích khi indicator còn giá trị | IP/domain thay đổi, shared infrastructure, trùng hợp hợp lệ |

### 4.1. Signature-based detection

Giả sử rule được thiết kế để cảnh báo khi thấy một **mẫu request HTTP đã biết** trong môi trường lab. Rule engine cần có khả năng giải mã HTTP và nhận đúng lưu lượng ở vị trí sensor. Nếu payload nằm bên trong TLS mà sensor không giải mã, chữ ký dựa trên nội dung HTTP không thể match chỉ từ ciphertext.

Đặc điểm của rule cần ghi: **giao thức, hướng, trường kiểm tra, điều kiện, mức nghiêm trọng, lý do tạo alert, phạm vi áp dụng và dữ liệu cần quan sát**. Một chữ ký tốt nên có bối cảnh để tránh cảnh báo trên payload hợp lệ trông giống mẫu nguy hiểm.

### 4.2. Anomaly detection

Ví dụ một workstation bình thường chỉ truy cập DNS resolver và vài API công ty. Một ngày máy này liên tục kết nối nhiều host nội bộ chưa từng có tương tác. Hệ thống anomaly có thể đánh dấu hành vi, dù không có chữ ký exploit cụ thể.

Tuy nhiên **bất thường không đồng nghĩa độc hại**: có thể là công cụ kiểm kê mới, triển khai agent, backup, thay đổi lịch làm việc hoặc cập nhật phần mềm. Cần kiểm tra asset owner, change window và baseline trước khi nâng mức cảnh báo.

### 4.3. Stateful protocol analysis

Khi IDS tái dựng phiên TCP, HTTP, DNS hoặc giao thức khác, engine có thể hiểu một số đặc điểm vượt khỏi từng packet riêng lẻ. Ví dụ IDS có thể báo trường giao thức bị định dạng sai, request không nhất quán hoặc chuỗi kết nối lạ.

Việc **reassembly**, xử lý fragment, retransmission, out-of-order packet và phân biệt client/server ảnh hưởng mạnh tới detection. Mất packet ở SPAN/TAP hoặc bất đối xứng định tuyến có thể khiến parser không tạo được bối cảnh đúng.

## 5. NIDS khác firewall ở đâu?

Một firewall **stateful L3/L4** quyết định traffic có được đi qua điểm policy theo 5-tuple, zone, trạng thái và rule; một **NIDS** tìm bằng chứng hành vi bất thường trong các luồng được quan sát.

Ví dụ traffic từ App tới DB TCP/5432 được firewall cho phép vì nghiệp vụ cần. Nếu App bị chiếm quyền, NIDS có thể phát hiện các kiểu kết nối lạ hoặc thay đổi mức lưu lượng khi có khả năng quan sát đủ. Tuy nhiên quyền truy cập dữ liệu trong DB vẫn do **DB authentication/authorization** quyết định. IDS không thể thay thế DB audit, least privilege hoặc TLS.

### 5.1. Một yêu cầu, nhiều lớp quyết định

~~~mermaid
flowchart LR
    C[Client] --> FW[Firewall: Allow TCP/443?]
    FW --> APP[Service: TLS + Auth + Authorization]
    FW -.Traffic copy.-> IDS[NIDS: Phân tích / Alert]
    IDS --> SIEM[SIEM / SOC]
    APP --> LOG[Application logs]
    LOG --> SIEM
~~~

Khi firewall chặn nguồn ngay tại biên, sensor **đặt sau firewall** có thể không thấy những attempt bị chặn đó; phải lấy firewall deny log hoặc đặt sensor ở vị trí thích hợp. Khi firewall cho phép nhưng ứng dụng từ chối login, cần kết hợp log ứng dụng với alert mạng để tránh suy diễn.

## 6. Sensor NIDS được đặt ở đâu?

**Placement (vị trí đặt sensor)** quyết định phạm vi quan sát. Những điểm thường gặp gồm:

| Điểm đặt | Thấy được | Có thể bỏ sót |
|---|---|---|
| Trước firewall Internet | Một phần traffic đến/đi Internet, kể cả nhiều attempt bị chặn | Luồng nội bộ không đi qua biên, danh tính sau VPN |
| Sau firewall Internet | Lưu lượng lọt qua firewall tại điểm quan sát | Traffic bị chặn trước đó, một số traffic sau NAT/proxy |
| Giữa App và Data | East-west traffic qua ranh giới này | Host ↔ host cùng VLAN không đi qua gateway |
| Sau VPN gateway | Lưu lượng sau giải mã tunnel nếu sensor đúng vị trí | Traffic trước VPN hoặc VPN khác |
| Vùng DNS/Resolver | Truy vấn/response mà sensor quan sát được | DNS cache, DoH/DoT ngoài phạm vi, resolver khác |
| Cloud traffic mirroring | Traffic tại NIC/điểm hỗ trợ mirror | Những nguồn không hỗ trợ mirror, traffic chưa được mirror, giới hạn cloud |
| Host agent / endpoint | Process, local connection, log trên host | Traffic ở host khác nếu không có telemetry |
| Kubernetes CNI/eBPF telemetry | Flow pod/workload theo datapath hỗ trợ | Traffic bypass datapath, hostNetwork hoặc phạm vi không thu thập |

### 6.1. SPAN/mirror, TAP và inline

- **SPAN / port mirroring:** switch hoặc virtual switch gửi bản sao traffic từ port/VLAN nguồn tới cổng monitor. Thuận tiện nhưng có thể **drop traffic mirror khi quá tải** hoặc không giữ được đầy đủ một số thông tin frame.
- **Network TAP:** thiết bị chuyên dụng sao chép luồng truyền để quan sát; khả năng, hướng và yêu cầu băng thông phụ thuộc phần cứng.
- **Inline IPS:** thiết bị nằm trên đường truyền và có quyền drop/reset theo policy; không phải cách triển khai thụ động thông thường của IDS.

**Không xem số gói IDS nhận được là số gói thật của đường truyền** nếu chưa kiểm tra packet loss, công suất mirror, offloading, MTU, encapsulation và thời gian. Cổng mirror 1 Gb/s không thể mặc định chứa trọn bản sao của nhiều luồng cộng lại vượt khả năng nhận.

### 6.2. East-west và cùng VLAN

Giả sử hai máy VM trong cùng subnet nói chuyện trực tiếp qua vSwitch. Firewall đặt giữa subnet và Internet không nhìn thấy luồng này; một NIDS ở firewall biên cũng không. Muốn có coverage, cân nhắc distributed sensor, host telemetry, CNI/eBPF flow logging hoặc mirroring đúng điểm.

Việc bổ sung NIDS **không tự tạo phân đoạn**. Firewall/ACL/microsegmentation phải chặn đường không cần thiết; IDS hỗ trợ phát hiện những hành vi bất thường còn lại.

### 6.3. Cloud và môi trường container

Trong cloud, log mạng có thể được lấy từ firewall managed, VPC/VNet flow logs, mirror traffic hoặc workload agent. Flow log thường thiên về metadata và không tự có payload cho signature matching. Trong Kubernetes, NetworkPolicy được thực thi bởi CNI hỗ trợ, còn việc tạo alert và flow visibility tùy các sensor/datapath được triển khai.

Cần biết cloud/account/region, VPC/VNet, cluster, interface và danh sách endpoint đã được cấp quyền thu thập. **Một cảm biến duy nhất trong cloud không bảo đảm nhìn thấy toàn bộ traffic giữa các workload.**

## 7. Ảnh hưởng của mã hóa đối với IDS

Lưu lượng ngày nay thường dùng **TLS, mTLS, VPN IPsec, WireGuard hoặc MACsec**. Điều này bảo vệ dữ liệu trên đường truyền nhưng cũng giới hạn những gì NIDS ở điểm không giải mã có thể kiểm tra.

| Tình huống | Sensor mạng có thể thấy | Có thể không thấy |
|---|---|---|
| HTTP không mã hóa | HTTP request/response và nội dung trong phạm vi capture | Request ở những đường không qua sensor |
| HTTPS không giải mã | IP/port, thời gian, kích thước, hướng, một phần handshake metadata tùy phiên bản | URL/path/body và nội dung HTTP đã mã hóa |
| IPsec/WireGuard tunnel | Metadata lớp ngoài của tunnel | IP/port bên trong và payload nếu sensor nằm trước giải mã |
| Sau TLS termination | Traffic backend theo thiết kế kết nối phía sau | Nội dung nếu backend tiếp tục dùng TLS hoặc sensor không nằm đúng đường |
| HIDS/EDR trên endpoint | Một số sự kiện sau giải mã, process và file theo khả năng agent | Toàn bộ packet ở các máy khác |

**TLS không làm IDS vô dụng**, vì nhiều tín hiệu hữu ích vẫn là flow metadata, hướng truyền, tần suất, DNS, kết nối mới và hành vi endpoint. Tuy nhiên các rule cần **payload cụ thể** có thể không hoạt động với dữ liệu chỉ là ciphertext. Những tuyên bố như “NIDS đọc được mọi HTTPS” là sai khi không có điều kiện giải mã phù hợp.

### 7.1. IDS tại điểm TLS termination

Một kiến trúc có reverse proxy có thể đặt cơ chế detection sau khi proxy kết thúc TLS, nếu quy trình và công nghệ cho phép quan sát HTTP request đã được giải mã. Cần xác định đường proxy → backend có mã hóa lại không, quyền truy cập nội dung và ảnh hưởng tới bảo vệ dữ liệu.

Không nên bật giải mã hàng loạt chỉ để tăng coverage mà không xem xét yêu cầu bảo mật, riêng tư, hiệu năng và luồng vận hành. Trong nhiều trường hợp, **application logs, WAF và EDR** là nguồn phù hợp hơn để bổ sung thiếu hụt của NIDS.

## 8. Những công cụ và kiểu triển khai thường gặp

Có nhiều thành phần phục vụ giám sát xâm nhập:

- **Suricata:** engine nhận diện lưu lượng, hỗ trợ rule và tạo các sự kiện protocol/alert theo cấu hình. Có thể được triển khai ở chế độ IDS hoặc ở một số chế độ IPS.
- **Snort:** engine phát hiện theo rule đối với lưu lượng mạng; hành vi thực tế phụ thuộc phiên bản và chế độ triển khai.
- **Zeek:** nền tảng phân tích mạng và sinh log giàu ngữ cảnh theo giao thức/kết nối; thường được dùng làm **network security monitoring**, không nên đồng nhất mọi log Zeek với alert signature IDS.
- **OSSEC/Wazuh và các agent host:** phục vụ một số bài toán phân tích log, file integrity và sự kiện hệ thống theo khả năng triển khai.
- **IDS/NDR managed hoặc cloud-native:** có thể dùng flow telemetry, log dịch vụ, metadata hoặc những nguồn riêng của nền tảng để phát hiện bất thường.

Tên công cụ không tự chứng minh khả năng thực tế: cần kiểm tra **sensor input, phiên bản, ruleset, scope, loại log, quyền, trạng thái decoder, tỷ lệ drop và đường truyền từ sensor đến SIEM**.

### 8.1. IDS engine và dữ liệu đầu ra

Một NIDS dựa trên packet có thể sinh:

- **Alert:** trùng rule hoặc logic phát hiện.
- **Flow/session:** thông tin 5-tuple, packets, bytes, duration, state.
- **Protocol logs:** DNS query, HTTP host/URI khi nhìn được, TLS metadata, SSH handshake và các trường hỗ trợ.
- **Stats/health:** uptime, capture loss, memory, decoder errors.
- **File metadata:** thông tin file truyền qua giao thức nếu engine quan sát được, tùy cấu hình.

Đối với triage, **health/stats** quan trọng không kém alert: khi sensor mất 60% lưu lượng do quá tải, số alert giảm không chứng minh mạng an toàn hơn.

## 9. Đọc một IDS alert

Một alert có ích cần gắn **thời điểm, nguồn cảm biến, hành vi, đối tượng mạng, loại tín hiệu và bằng chứng hỗ trợ**.

Ví dụ một bản ghi JSON **minh họa**, không phải dữ liệu thật và không phải schema bắt buộc của công cụ cụ thể:

~~~json
{
  "timestamp": "2026-11-28T05:00:00Z",
  "sensor_id": "nids-app-data-01",
  "event_type": "alert",
  "src_ip": "10.20.20.15",
  "src_port": 52340,
  "dest_ip": "10.20.30.25",
  "dest_port": 5432,
  "proto": "TCP",
  "flow_id": "flow-9382",
  "alert": {
    "signature_id": "LAB-1001",
    "signature": "Kết nối DB từ nguồn chưa nằm trong dependency map",
    "category": "Policy anomaly",
    "severity": 2,
    "action": "alert"
  },
  "evidence": {
    "source": "flow-metadata",
    "encrypted_payload": false
  }
}
~~~

Cần đọc các trường theo đúng định nghĩa của công cụ. **Severity 2** trong ví dụ chỉ là số nội bộ, không mặc định có cùng thang đo giữa các vendor. **Action alert** chỉ cho biết cảnh báo được tạo, không chứng minh traffic đã bị chặn.

### 9.1. Những câu hỏi khi nhận alert

1. **Sensor nào** phát hiện? Nó đứng trước/sau NAT, VPN, firewall, TLS termination nào?
2. **Luồng gì**? 5-tuple, hướng kết nối, timestamp, session/flow ID, rule ID.
3. **Detection dựa vào gì**? Payload, metadata, anomaly baseline hay threat intelligence?
4. **Rule có thấy đủ dữ liệu không**? Có packet loss, parser error, traffic mã hóa hay bất đối xứng không?
5. **Nguồn là ai**? Gắn IP với asset/user/workload từ DHCP, VPN, NAC, EDR hoặc cloud inventory đúng thời điểm.
6. **Đích là gì**? Độ nhạy tài sản, vai trò máy chủ, service port thực tế.
7. **Có dấu hiệu bổ sung không**? Firewall allow/deny, endpoint process, application log, DB auth, DNS, thay đổi cloud IAM.
8. **Đã xảy ra tác động chưa**? Chỉ có attempt, kết nối thành công, đăng nhập thành công hay thao tác trên dữ liệu?

### 9.2. Quy tắc diễn giải thận trọng

Một alert về **“suspicious database connection”** không chứng minh database đã bị truy cập trái phép. Nó có thể là một luồng được cho phép và chính đáng nhưng chưa cập nhật dependency map; cũng có thể là một host đã bị chiếm. Phải kiểm tra rule, owner, lịch triển khai, endpoint và kết quả DB.

## 10. False positive, false negative và chất lượng phát hiện

IDS không thể nhận diện chính xác 100% mọi hoạt động. Hai nhóm lỗi cần hiểu:

- **False positive (FP):** báo nghi vấn dù sự kiện thực tế hợp lệ hoặc không đáp ứng định nghĩa tấn công đang xét.
- **False negative (FN):** bỏ sót sự kiện thực sự cần phát hiện.

Bảng confusion matrix:

| Thực tế / IDS | IDS báo alert | IDS không báo |
|---|---|---|
| Có hoạt động cần phát hiện | **True positive (TP)** | **False negative (FN)** |
| Không có hoạt động cần phát hiện | **False positive (FP)** | **True negative (TN)** |

Các chỉ số thường dùng:

\[
\text{Precision} = \frac{TP}{TP+FP}
\]

\[
\text{Recall (Detection Rate)} = \frac{TP}{TP+FN}
\]

\[
\text{False Positive Rate} = \frac{FP}{FP+TN}
\]

**Precision** phản ánh trong số alert đã tạo, tỷ lệ thật sự phù hợp với điều cần phát hiện. **Recall** thể hiện tỷ lệ sự kiện thật sự được phát hiện. Các chỉ số chỉ có nghĩa nếu có **bộ mẫu được gán nhãn đáng tin** và hiểu rõ định nghĩa “positive”.

### 10.1. Ví dụ tính precision

Giả sử đội SOC review 100 alert trong một đợt diễn tập có kết quả xác minh: **25 true positive và 75 false positive**. Khi đó:

\[
\text{Precision} = \frac{25}{25+75} = 25\%
\]

Điều này không có nghĩa 75% lưu lượng mạng là vô hại, hay IDS bỏ sót bao nhiêu cuộc tấn công. Không có số **FN** từ một bộ dữ liệu được kiểm chứng thì chưa tính được recall.

### 10.2. Cảnh báo nhiều không đồng nghĩa phát hiện tốt

Một rule quá rộng có thể cảnh báo mọi kết nối DNS hoặc mọi failed login, làm analyst ngập cảnh báo. Rule quá hẹp có thể giảm false positive nhưng bỏ qua các biến thể mới. Cần đo bằng dữ liệu thật và kịch bản kiểm tra hợp lệ, chú ý:

- **Detection coverage:** có phát hiện được các hành vi quan trọng trong threat model không?
- **Actionability:** alert có đủ IP/identity/context để ra quyết định không?
- **Latency:** từ event đến triage mất bao lâu?
- **Noise:** các alert lặp và false positive có làm người vận hành bỏ qua tín hiệu quan trọng không?
- **Sensor health:** có mất packet, log ingest lỗi hoặc thay đổi cấu hình không?

Không được tính một rule “đã triển khai” là coverage đạt yêu cầu khi sensor chưa được kiểm chứng nhận đúng luồng và parser phù hợp.

## 11. Thiết kế một use case phát hiện

Một **detection use case** tốt mô tả giả thuyết rõ ràng, nguồn dữ liệu, logic, ngoại lệ hợp lệ và cách xác minh.

Ví dụ: **phát hiện một máy trong Staff VLAN cố truy cập nhiều máy quản trị không thuộc quyền của nó**.

| Trường | Mô tả use case |
|---|---|
| Mục tiêu | Phát hiện hành vi có thể liên quan lateral movement hoặc reconnaissance |
| Tài sản bảo vệ | Máy chủ quản trị, jump host, controller |
| Vị trí adversary | Workstation trong Staff VLAN hoặc host bị chiếm |
| Telemetry | NIDS/flow + firewall deny + NAC/EDR inventory |
| Logic | Một nguồn liên hệ nhiều đích quản trị bất thường trong thời gian xác định |
| Điều kiện lọc | Loại trừ công cụ inventory được cấp phép trong đúng scope và lịch |
| Cảnh báo | Source/asset owner, đích, ports, tần suất, rule và evidence |
| Phản ứng | Xác minh change ticket, EDR, auth log; cô lập host nếu có đủ căn cứ và thẩm quyền |
| Kiểm chứng | Tạo dữ liệu mô phỏng/lab được phép, xác định alert có phát và có đầy đủ trường |

Điều kiện **“nhiều”**, **“bất thường”** cần baseline và yêu cầu nghiệp vụ. Không gán một ngưỡng universal cho mọi VLAN và tổ chức.

### 11.1. Detection rule ở mức khái niệm

~~~text
INPUT: flow events từ Staff tới Management trong 5 phút

GROUP BY: verified_source_asset
MEASURE: số destination IP và destination port riêng biệt
FILTER: bỏ những job kiểm kê đã phê duyệt đúng thời gian/scope

IF:
  số đích/cổng vượt baseline của vai trò máy
  AND có một hoặc nhiều luồng vi phạm access policy
THEN:
  tạo alert chứa flow IDs, thời gian và tài sản liên quan
~~~

Đây là **pseudocode**, không phải rule có thể dán trực tiếp vào Suricata, Snort hay SIEM bất kỳ. Engine và schema quyết định cú pháp thực tế. Hãy giữ **logic và nguồn bằng chứng** tách khỏi ngôn ngữ cấu hình của sản phẩm.

### 11.2. Những kịch bản nên bao phủ theo threat model

| Kịch bản | Tín hiệu mạng có thể dùng | Dữ liệu bổ sung |
|---|---|---|
| Port scanning nội bộ | Nhiều SYN/connection attempt tới port/host khác nhau | Firewall deny, asset scanner allowlist |
| Thử xác thực liên tục | Nhiều session/failed auth nếu nguồn ghi nhận | SSH/IdP/VPN/app auth logs |
| Truy cập DB bất thường | Workload lạ tới DB port hoặc thay đổi flow baseline | DB authentication/audit, deployment ticket |
| DNS bất thường | Tần suất, kích thước, cấu trúc tên hoặc resolver không chuẩn | Resolver logs, endpoint process, change baseline |
| DDoS/traffic spike | Tăng flow/bytes/pps và tỷ lệ lỗi | Firewall counters, upstream, application latency |
| Đường đi dữ liệu lạ | Egress lớn tới đích mới | Cloud logs, app/backup schedules, DLP nếu có |
| Thay đổi chính sách bảo mật | Luồng mới sau chỉnh firewall/SG | Config audit, IAM, ticket |
| Hành vi host bất thường | Kết nối mới liên quan tiến trình không quen thuộc | EDR/HIDS, process tree, file events |

Nếu chỉ có metadata, detection phải được diễn đạt là **nghi vấn từ metadata**. Ví dụ DNS có tên dài bất thường không tự chứng minh data exfiltration; có nhiều giao thức và ứng dụng hợp lệ sinh chuỗi dài.

## 12. IDS và phòng vệ nhiều lớp

NIDS phát hiện traffic bất thường có ý nghĩa nhất khi kết hợp với các lớp làm giảm attack surface.

| Lớp phòng vệ | Chức năng | IDS bổ sung gì? |
|---|---|---|
| Phân đoạn VLAN/subnet, microsegmentation | Giới hạn đường giao tiếp east-west | Cảnh báo luồng bất thường trong vùng hoặc thử vượt ranh giới được quan sát |
| Firewall/ACL | Cho/chặn theo policy | Phát hiện hành vi nghi vấn trên luồng vẫn được phép |
| VPN/ZTNA | Xác thực, mã hóa và cấp đường kết nối từ xa | Phát hiện kết nối khác baseline sau tunnel, khi sensor thấy được |
| 802.1X/NAC | Kiểm soát thiết bị được tham gia mạng | Bổ sung nhận biết activity của endpoint đã được cho tham gia |
| TLS/mTLS | Bảo vệ dữ liệu và xác thực kết nối/dịch vụ | Phân tích metadata và hành vi; cần HIDS/app log khi payload đã mã hóa |
| DNS protection | Giới hạn resolver và tăng tin cậy phân giải | Theo dõi pattern DNS nếu log/capture phù hợp |
| Cloud security group/NetworkPolicy | Giới hạn đường tới workload | Phát hiện luồng mới hoặc bất thường tại vùng cloud được thu thập |
| EDR/HIDS | Quan sát tiến trình, file và hành vi host | Liên hệ network alert với thực thể/process tại endpoint |
| SIEM/SOAR | Tương quan, điều tra, điều phối xử lý | Biến cảnh báo IDS thành tín hiệu có ngữ cảnh và quy trình |

Ví dụ sau khi một account VPN bị chiếm, IDS ở **sau VPN gateway** có thể nhận biết nguồn đó thử hàng loạt cổng nội bộ mà user thông thường không sử dụng. Nhưng kết luận “account bị chiếm” cần kết hợp IdP, MFA, VPN login, device posture và các log endpoint liên quan.

## 13. Triển khai IDS trong mạng doanh nghiệp

Một kiến trúc giả định:

~~~mermaid
flowchart TD
    INTERNET[Internet] --> EDGE[Firewall biên]
    EDGE --> WEB[Public Web]
    EDGE --> VPN[VPN Gateway]
    VPN --> STAFF[Staff subnet]
    STAFF --> IFW[Firewall nội bộ]
    WEB --> IFW
    IFW --> APP[App subnet]
    IFW --> DB[Data subnet]
    EDGE -.Mirror.-> IDS1[NIDS biên]
    IFW -.Mirror.-> IDS2[NIDS east-west]
    APP --> HIDS[Host/EDR telemetry]
    IDS1 --> COL[Collector]
    IDS2 --> COL
    HIDS --> COL
    COL --> SIEM[SIEM / SOC]
~~~

**Giải thích:** sensor biên giúp phát hiện hoạt động từ mạng ngoài theo coverage, sensor east-west thấy những luồng giữa các zone đi qua firewall nội bộ, HIDS/EDR bổ sung hành vi endpoint. Firewall tự tạo deny/allow logs. SIEM liên kết sự kiện theo thời gian, source/destination, asset và danh tính.

### 13.1. Các quyết định thiết kế cần ghi

1. **Tài sản trọng yếu:** DNS, VPN, ứng dụng, DB, management, cloud control plane, backup.
2. **Threat model:** adversary ở Internet, Staff, Guest, VPN, App workload bị chiếm có những đường nào?
3. **Điểm đặt:** sensor trước/sau firewall, sau VPN termination, tại East-West và cloud workload.
4. **Phương pháp capture:** TAP, SPAN, port mirror, cloud mirror, endpoint agent hoặc flow logs.
5. **Mức quan sát:** packet/payload, flow metadata, protocol event hay HIDS log.
6. **Khả năng xử lý:** peak Mbps/Gbps, packets per second, buffer, CPU, disk, thời gian lưu.
7. **Rule và update:** ai phê duyệt rule, giám sát thay đổi chữ ký, rollback khi false positive.
8. **Dữ liệu:** sự kiện nào lưu, bảo vệ thông tin nhạy cảm và thời hạn giữ.
9. **Đáp ứng:** alert nào vào SOC, mức ưu tiên, playbook, người xử lý.
10. **Kiểm chứng:** bài test nào chứng minh sensor thấy đường mạng và phát đúng alert?

### 13.2. Thất thoát packet và tải sensor

Sensor có thể mất gói khi tốc độ mirror lớn hơn cổng nhận, CPU decode quá tải, hệ điều hành không cấp buffer đủ, dung lượng lưu trữ bị đầy hoặc driver bị drop. Do đó cần theo dõi:

- **Packets captured / dropped** ở giao diện và engine.
- Throughput/pps thực tế, nhất là giờ cao điểm.
- Decoder/parser errors, reassembly failures.
- Alerts/flows per second, queue và độ trễ xử lý.
- Sự cố mất nguồn log hoặc collector ingest trễ.
- Thời điểm deploy rule, thay đổi SPAN/TAP hoặc mirror filter.

**Ít cảnh báo hơn sau một thay đổi không chứng minh hệ thống an toàn hơn** nếu sensor mới chỉ nhìn thấy một phần traffic.

## 14. Cách triage một cảnh báo IDS

Triage là phân loại và xác minh nhanh để quyết định có cần điều tra sâu hay ứng phó.

### Bước 1 — Xác định độ tin cậy nguồn

Kiểm tra sensor ID, thời gian, trạng thái thiết bị, rule version, packet loss, health và kết nối log collector. Nếu sensor mất nhiều traffic, phải ghi rõ giới hạn của phân tích.

### Bước 2 — Hiểu điều kiện tạo alert

Đọc rule/signature, protocol, field được kiểm tra, mức nghiêm trọng và action. Phân biệt **phát hiện chữ ký nội dung** với **bất thường từ flow** hoặc **IOC match**. Xem rule có ngoại lệ nào không.

### Bước 3 — Xác định tài sản và đường đi

Đối chiếu 5-tuple, NAT, VLAN, VPN, cloud workload identity, DNS và asset inventory theo thời điểm. Xác định firewall/ACL nào kiểm soát đường này.

### Bước 4 — Tìm bằng chứng độc lập

Ghép EDR/host logs, firewall logs, SSH/VPN/application/DB logs, DNS telemetry và cloud audit. Xem có kết nối thành công, quá trình xác thực hay hành động nghiệp vụ thực tế.

### Bước 5 — Đánh giá tác động và ưu tiên

Một alert mức trung bình tới máy chủ giữ secrets có thể cần ưu tiên cao hơn alert cùng chữ ký tới host lab, tùy ngữ cảnh. Xem exposure, khả năng xâm nhập thực tế, asset criticality, tín hiệu lặp và số nguồn độc lập.

### Bước 6 — Hành động đúng thẩm quyền

Các hành động có thể gồm tăng thu thập log, giám sát host, cô lập endpoint, điều chỉnh ACL, vô hiệu token hoặc khôi phục workload; phải chọn theo mức bằng chứng và quy trình phản ứng. **IDS thụ động không tự chặn traffic chỉ vì phát alert.** Nếu kết nối SOAR/EDR/firewall để phản ứng tự động, cần guardrails tránh false positive gây gián đoạn.

### Bước 7 — Đóng vòng phản hồi

Gắn nhãn sự kiện (true positive/false positive/needs more evidence), cập nhật rule, ngoại lệ giới hạn, inventory, playbook và kịch bản kiểm chứng. Tránh chỉ đóng alert mà không cập nhật chất lượng detection.

## 15. Quy trình tạo và tuning detection rule

Một rule hữu dụng cần đảm bảo **đúng mục tiêu, có khả năng quan sát, có thể kiểm chứng và có người chịu trách nhiệm**.

### 15.1. Quy trình từ ý tưởng đến production

1. **Định nghĩa đối thủ và hành vi:** ví dụ một thiết bị Guest cố tiếp cận nhiều máy Management.
2. **Xác định nguồn dữ liệu:** NIDS ở ranh giới Guest/Management, firewall deny log, NAC inventory.
3. **Mô tả logic:** tập IP/zone, khoảng thời gian, số đích/cổng, điều kiện bổ sung.
4. **Thiết lập baseline:** phân biệt công việc quản trị/scanner được phép và traffic nhân viên.
5. **Kiểm thử bằng dữ liệu lab hoặc bản ghi đã được phê duyệt:** xác nhận alert có phát và không phát khi điều kiện không thỏa.
6. **Triển khai ở chế độ theo dõi/tuning:** đánh giá tỉ lệ false positive, CPU và khối lượng alert.
7. **Bật rule chính thức:** có owner, version, tài liệu điều kiện và runbook.
8. **Theo dõi sau thay đổi:** đánh giá drift, packet loss, app deploy và hành vi mới.
9. **Rà soát định kỳ:** loại bỏ rule không còn liên quan, điều chỉnh nguồn/dải theo policy.

### 15.2. Tuning không nên che lấp một vùng nguy hiểm

Nếu scanner hợp lệ thường chạy mỗi tối, có thể tạo ngoại lệ **chỉ cho scanner đã xác thực, đúng phạm vi đích và thời gian**. Không nên loại trừ toàn bộ Staff VLAN hoặc bỏ mọi alert liên quan SSH chỉ để giảm noise.

Tương tự, rule phát hiện TLS metadata không nên được coi đã kiểm tra **payload đã mã hóa**. Trong hồ sơ rule hãy ghi rõ giới hạn và vị trí sensor.

## 16. Thực hành an toàn: quan sát và tạo luồng mẫu trên localhost

Mục tiêu thực hành là hiểu luồng dữ liệu đầu vào của IDS trong **môi trường người học tự quản lý**, không tiến hành scan hoặc thử khai thác hệ thống ngoài phạm vi cho phép.

Giả sử máy Linux hoặc máy ảo lab có Python 3, curl và tcpdump. Những công cụ này có thể chưa được cài; câu lệnh dưới đây chỉ là ví dụ để tự thực hành, **không phải đã chạy trong quá trình viết bài**.

### 16.1. Tạo dịch vụ thử nghiệm

Mở terminal thứ nhất trong thư mục thử nghiệm **không chứa dữ liệu bí mật**:

~~~bash
python3 -m http.server 8080 --bind 127.0.0.1
~~~

Server HTTP đơn giản này lắng nghe **127.0.0.1:8080**, tức IPv4 loopback. Nó phục vụ file trong thư mục hiện hành, vì vậy không nên khởi chạy trong thư mục có dữ liệu riêng tư. Dừng server bằng **Ctrl+C** khi xong.

### 16.2. Tạo một request hợp lệ

Trên terminal thứ hai:

~~~bash
curl -v http://127.0.0.1:8080/
~~~

Quan sát server log và các thông tin request/response. Đây là request HTTP hợp lệ, **không phải hành vi tấn công**. Nếu IDS có rule hoặc parser nhận dạng HTTP, nó có thể sinh protocol event; không mặc nhiên tạo intrusion alert.

### 16.3. Đối chiếu với packet capture

Trên Linux, nếu có quyền và tên loopback interface là **lo**:

~~~bash
sudo tcpdump -i lo -nn -c 20 'tcp port 8080'
~~~

Một số hệ điều hành/driver dùng interface khác cho loopback hoặc không hỗ trợ capture như ví dụ. NIDS muốn thấy luồng này phải **capture đúng giao diện loopback**, có rule/phân tích phù hợp và không bị lọc bỏ. Việc chỉ chạy một sensor trên Ethernet interface khác sẽ không nhất thiết thấy HTTP localhost.

**Quan sát quan trọng:**

- TCP có SYN, SYN-ACK và các packet truyền dữ liệu.
- Request tới 127.0.0.1 không tự đi qua firewall biên hoặc switch trong LAN.
- Một protocol parser có thể ghi HTTP metadata mà không có alert đe dọa.
- Nếu chạy HTTPS thay vì HTTP, NIDS ở ngoài điểm giải mã thường không thấy nội dung request.

### 16.4. Bài học về coverage

Thử nghiệm trên localhost giúp hiểu packet và request; để kiểm chứng NIDS giám sát một vùng mạng thật, cần một lab nhiều VM/vSwitch hoặc bản capture đã được phê duyệt, xác định rõ đường truyền, sensor input, rule, logging và kết quả mong đợi.

Không nên tự chạy quét cổng lớn hay tạo traffic gây tải cao để “thử IDS” trên mạng sản xuất khi chưa có kế hoạch và quyền kiểm tra. Có thể đánh giá detection bằng **PCAP mẫu được phép, replay trong lab cách ly hoặc sự kiện mô phỏng có kiểm soát**, đồng thời xem ảnh hưởng tới hệ thống vận hành.

## 17. Kịch bản và bài tập phân tích

### Tình huống A — IDS báo port scan từ máy quản trị

NIDS báo một nguồn thử nhiều port tới các server. Firewall deny logs cũng tăng. Inventory cho biết nguồn là máy asset scanner chạy định kỳ đã được phê duyệt.

**Câu hỏi:** có phải intrusion đã được xác nhận? Cần điều chỉnh điều gì?

**Gợi ý:** chưa. Phải kiểm tra scanner identity, lịch chạy, danh sách đích, owner và thay đổi scope. Nếu khớp công việc hợp lệ, phân loại false positive hoặc benign activity theo định nghĩa use case; tạo ngoại lệ **giới hạn theo điều kiện**. Nếu scanner thử tài sản ngoài phạm vi, cần điều tra tiếp.

### Tình huống B — Firewall allow nhưng NIDS alert

Máy App kết nối DB TCP/5432 được phép theo firewall. NIDS lại báo nguồn lạ sử dụng cổng DB, nhưng nguồn thực tế là một instance mới vừa được triển khai.

**Câu hỏi:** nên chặn ngay không?

**Gợi ý:** trước tiên xác minh deployment ticket, workload identity, đường App → DB, policy và DB auth. Nếu instance hợp lệ nhưng inventory chưa cập nhật thì cần sửa dependency map/detection. Nếu không hợp lệ, đánh giá ưu tiên và cô lập theo quy trình. NIDS alert tự nó không phải bằng chứng đã khai thác DB.

### Tình huống C — IDS không thấy payload HTTPS

Ứng dụng public dùng HTTPS; sensor NIDS ngoài reverse proxy chỉ nhận flow và TLS metadata, không phát alert cho rule tìm mẫu HTTP body.

**Câu hỏi:** vì sao rule không hoạt động?

**Gợi ý:** nội dung HTTP được TLS mã hóa trước khi tới điểm quan sát, rule dựa trên plaintext không có dữ liệu để so khớp. Cân nhắc WAF, reverse proxy access logs, application security monitoring hoặc điểm hợp pháp sau TLS termination. Không suy luận “không có alert nghĩa không có tấn công”.

### Tình huống D — IDS mất gói trong giờ cao điểm

Sau khi mở thêm mirroring của hai VLAN lên một cổng monitor, số alert giảm mạnh nhưng thống kê sensor cho thấy drop rate tăng.

**Câu hỏi:** có thể đánh giá mạng an toàn hơn không?

**Gợi ý:** không. Việc mất packet có thể làm parser không tái dựng được session và bỏ lỡ chữ ký. Cần đánh giá throughput/pps, tốc độ cổng monitor, filter phù hợp, buffer, CPU, engine stats và khả năng chia sensor trước khi diễn giải thay đổi alert.

### Tình huống E — Lateral movement trong cùng subnet

Một host bị chiếm liên lạc với server quản trị nằm trong **cùng subnet**. Firewall liên VLAN không ghi traffic, NIDS ở gateway cũng không có alert.

**Câu hỏi:** hệ thống thiếu những điểm quan sát nào?

**Gợi ý:** traffic có thể đi trực tiếp qua vSwitch/switch. Cần host firewall logs, EDR, distributed sensor, CNI flow telemetry hoặc mirroring phù hợp. Kết hợp phân đoạn ở mức workload vì IDS không tự chặn lưu lượng.

### Tình huống F — NIDS tạo alert “DNS bất thường”

Một workstation gửi nhiều truy vấn DNS với subdomain dài. Đây cũng có thể là hành vi của phần mềm cập nhật, kiểm thử hoặc hệ thống CDN.

**Câu hỏi:** cần bằng chứng gì?

**Gợi ý:** xem resolver logs, domain ownership, tần suất so baseline, tiến trình trên host, traffic outbound tiếp theo, identity và lịch cập nhật. DNS query bất thường là tín hiệu cần điều tra, chưa chứng minh có kênh rò rỉ dữ liệu.

### Tình huống G — Một tài khoản VPN có hành vi mới

Sau khi đăng nhập VPN thành công, nguồn VPN truy cập hàng loạt cổng quản trị mà user đó thường không dùng. IDS sau VPN tunnel phát alert.

**Câu hỏi:** cần kết hợp những log nào?

**Gợi ý:** VPN session/assigned IP, IdP/MFA, NAC/device posture, firewall allow/deny, EDR của máy client, log SSH/RDP của đích và thay đổi quyền. Đăng nhập VPN thành công không mặc định trao quyền quản trị.

## 18. Lỗi triển khai IDS thường gặp

1. **Chỉ đặt sensor ở Internet gateway:** bỏ lỡ east-west traffic giữa workload nội bộ.
2. **Không tính mã hóa:** rule payload-based không thể đọc HTTP body bên trong TLS nếu sensor không được giải mã.
3. **Mất packet nhưng không giám sát:** ít alert là hậu quả thiếu dữ liệu.
4. **Chỉ đếm alert:** không đánh giá TP/FP/FN, coverage, chất lượng rule và công sức SOC.
5. **Coi alert là tấn công thành công:** một dấu hiệu chỉ là một giả thuyết, cần kiểm chứng.
6. **Lẫn lộn IDS và IPS:** IDS passive thông thường không chặn traffic.
7. **Tuning quá rộng:** loại trừ cả VLAN hoặc cổng nhạy cảm chỉ để giảm noise.
8. **Không ghép NAT/VPN/DHCP:** gán nhầm IP cho người dùng hoặc workload.
9. **Không kiểm soát timezone:** timeline giữa IDS, firewall, VPN và EDR sai thứ tự.
10. **Thiếu asset inventory:** không biết đích là lab hay database quan trọng.
11. **Không version ruleset:** không xác định được logic nào tạo alert tại thời điểm sự kiện.
12. **Không quan sát chính sensor:** capture pipeline có thể lỗi mà SOC không nhận biết.
13. **Lưu bản ghi không an toàn:** telemetry chứa IP nội bộ, tên miền, identity và có thể metadata nhạy cảm.
14. **Không kiểm chứng với traffic hợp lệ:** ruleset gây quá nhiều false positive hoặc bỏ sót behavior thực tế.
15. **Bỏ qua cloud control plane:** thay đổi firewall/NetworkPolicy/IAM có thể tạo đường mới ngoài phạm vi cảm biến cũ.

## 19. Checklist trước khi vận hành IDS

- [ ] Xác định tài sản cần bảo vệ, adversary, vị trí tấn công và hành vi cần phát hiện.
- [ ] Ghi rõ IDS theo mạng hay host và khả năng thực tế của mỗi sensor.
- [ ] Xác định sensor thấy những đường north-south/east-west nào; có đường bypass không.
- [ ] Đã kiểm chứng TAP/SPAN/cloud mirror/CNI capture và thống kê packet loss.
- [ ] Đã hiểu phạm vi payload, metadata, mã hóa TLS/VPN và điểm termination.
- [ ] Có logic detection cho các kịch bản quan trọng, có owner và bản version.
- [ ] Phân biệt cảnh báo IDS với action thực thi của IPS/firewall.
- [ ] Có baseline, điều kiện loại trừ hợp lệ và đánh giá false positive/false negative.
- [ ] Có timestamp UTC/offset và đồng bộ thời gian, lưu event time và ingest time.
- [ ] Có 5-tuple/flow ID/sensor ID/rule ID và đủ ngữ cảnh cho triage.
- [ ] Kết hợp được firewall, VPN/NAC, DNS, EDR/HIDS, cloud IAM và ứng dụng khi cần.
- [ ] SIEM/collector ingest đầy đủ, theo dõi log pipeline, parse errors và alert latency.
- [ ] Có quyền truy cập, mã hóa, retention, audit và bảo vệ dữ liệu log.
- [ ] Có runbook phân loại, điều tra, phản ứng và phục hồi phù hợp.
- [ ] Đã test rule bằng dữ liệu/lab được phê duyệt, bao gồm test positive và negative.
- [ ] Có lịch kiểm tra sau thay đổi mạng, ứng dụng, CNI, firewall và ruleset.

## 20. Tổng kết

**Intrusion Detection System** là một lớp **phát hiện có điều kiện**, cung cấp cảnh báo khi cảm biến nhìn thấy những hoạt động phù hợp với quy tắc, hành vi bất thường hoặc thông tin đe dọa. Hiệu quả IDS không chỉ phụ thuộc chữ ký mà còn vào **sensor placement, độ đầy đủ telemetry, khả năng xử lý packet/flow, mã hóa, chất lượng rule và năng lực triage của con người**.

Trong kiến trúc mạng an toàn, **firewall và phân đoạn** giới hạn đường truy cập, **VPN/NAC và xác thực** kiểm soát danh tính/kết nối, **TLS/mTLS** bảo vệ dữ liệu, còn **IDS cùng SIEM/EDR/DNS/cloud audit** phát hiện và giải thích các tín hiệu đáng ngờ. Khi triển khai đúng điểm, kiểm chứng thường xuyên và phản ứng dựa trên bằng chứng, IDS giúp giảm thời gian phát hiện, hỗ trợ điều tra và cải thiện phòng vệ mạng qua mỗi thay đổi.
