# Viết playbook cô lập nguồn tấn công

**Chương:** Dự án thực hành bảo mật mạng  
**Bài thực hành:** Viết playbook cô lập nguồn tấn công  
**Phạm vi:** Phát hiện, xác minh, khoanh vùng và cô lập nguồn gây hại trong mạng doanh nghiệp, kết hợp firewall, phân đoạn mạng, VPN, IDS/IPS, DNS, hệ thống danh tính, EDR và hạ tầng cloud.

## 1. Kết quả cần đạt và sản phẩm bàn giao

Trong vận hành bảo mật mạng, khi IDS/IPS hoặc SIEM báo một nguồn đang quét, khai thác hoặc liên lạc bất thường, đội ứng cứu phải quyết định **cô lập cái gì, tại đâu, trong bao lâu, bằng chứng nào đủ và làm sao khôi phục an toàn**. Nếu phản ứng chỉ bằng cách thêm ngay một rule chặn IP, đội vận hành có thể ngắt nhầm khách hàng, proxy, thiết bị dùng chung hoặc đường quản trị quan trọng mà vẫn để phiên nguy hiểm tiếp tục hoạt động qua đường khác.

Mục tiêu của bài này là viết một **playbook có thể thực hiện, kiểm toán và kiểm thử** cho tình huống cô lập nguồn tấn công. Đây là công việc phòng vệ, chỉ mô phỏng với tài sản lab được cho phép; không yêu cầu khai thác lỗ hổng hoặc tạo lưu lượng tấn công thật.

Hoàn thành bài thực hành, người học cần có:

1. Sơ đồ xác định nguồn, nạn nhân, ranh giới tin cậy và điểm thực thi cô lập.
2. Bộ điều kiện kích hoạt, phân loại mức độ tin cậy và các ngưỡng cần người phê duyệt.
3. Playbook từng bước từ nhận cảnh báo, xác minh, lựa chọn biện pháp, áp dụng, kiểm tra hiệu quả, đến rollback.
4. Một đặc tả rule tạm thời có owner, phạm vi, thời điểm hết hạn, lý do và bằng chứng liên quan.
5. Nhật ký thực hành lab thể hiện trạng thái **trước khi chặn**, **sau khi chặn** và **sau khi khôi phục**.
6. Bộ tiêu chí chấp nhận, các trường hợp lỗi và báo cáo rút kinh nghiệm.

Trong module `SECURITY_NETWORK_SECURITY`, bài tập tích hợp các lớp bảo vệ từ phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối tới DNS, mạng không dây và cloud; đồng thời rèn khả năng phân tích lưu lượng, mô hình hóa mối đe dọa, giám sát xâm nhập và xây kiến trúc phòng vệ có thể vận hành thực tế.

## 2. Hiểu đúng “nguồn tấn công”

Từ “nguồn” có thể chỉ nhiều thực thể, không nhất thiết là một địa chỉ IP:

| Loại nguồn | Ví dụ | Rủi ro khi nhận diện sai |
|---|---|---|
| IP công cộng quan sát trên firewall/WAF | `198.51.100.25` | Có thể là NAT/CGNAT, reverse proxy, CDN hoặc VPN gateway phục vụ nhiều người |
| Thiết bị nội bộ | `WS-07` ở VLAN người dùng | DHCP hoặc NAT khiến IP có thể đổi, chặn cả subnet gây ảnh hưởng rộng |
| Tài khoản/danh tính | `lab.suspect` hoặc service account | Một tài khoản có thể đăng nhập trên nhiều máy; chặn IP không cắt được token |
| Workload/container | Pod, VM, instance hoặc cloud principal | IP/container được tái tạo hoặc dịch chuyển khi autoscaling |
| Tên miền/đích giao tiếp | Domain máy chủ điều khiển, endpoint ngoài | Domain có thể dùng CDN/chia sẻ hạ tầng, thay IP; DNS blocking không ngắt phiên sẵn có |
| Phiên/tunnel | VPN session, SSH tunnel, RDP session | Chặn phiên cụ thể có thể chính xác hơn chặn toàn mạng |

Các địa chỉ thuộc `198.51.100.0/24`, `192.0.2.0/24` và `203.0.113.0/24` trong bài là dải ví dụ dành cho tài liệu; không biểu thị nguồn tấn công có thật.

**Quan trọng:** ở đây “cô lập nguồn tấn công” có hai tình huống khác nhau:

- **Nguồn bên ngoài** đang gửi request hoặc lưu lượng nguy hiểm tới dịch vụ được bảo vệ. Hành động thường là chặn/rate-limit tại WAF, edge firewall, DDoS service hoặc gateway thích hợp, ở phạm vi dịch vụ có liên quan.
- **Nguồn bên trong** là máy, tài khoản hay workload nghi đã bị xâm nhập và đang tạo lưu lượng bất thường. Hành động có thể là EDR host isolation, chuyển sang VLAN/quarantine, cô lập security group, vô hiệu hóa phiên/danh tính hoặc giới hạn egress; phải giữ đường điều tra cần thiết theo chính sách.

Chọn sai tình huống có thể gây mất khả năng giám sát hoặc không xử lý được nguyên nhân. Ví dụ chặn IP NAT công cộng khi máy bên trong đã bị nhiễm mã độc có thể khiến toàn bộ nhóm người dùng mất Internet nhưng máy bị nhiễm vẫn giao tiếp qua proxy khác.

## 3. Phân biệt detection, triage, containment và recovery

| Giai đoạn | Câu hỏi cần trả lời | Đầu ra |
|---|---|---|
| Detection | Điều gì bất thường đã được ghi nhận? | Alert và dữ liệu gốc |
| Triage | Có khả năng gây hại thật không? Nguồn/nạn nhân là ai? | Mức tin cậy, mức độ nghiêm trọng, phạm vi |
| Containment | Cần giới hạn đường tương tác nào để giảm tác động? | Biện pháp cô lập có phạm vi, chủ sở hữu, TTL |
| Investigation | Lỗ hổng, danh tính, tiến trình hay phiên nào liên quan? | Timeline, IOC, phạm vi ảnh hưởng |
| Eradication | Nguyên nhân gốc và quyền/tác nhân độc hại đã được loại bỏ? | Xử lý điểm xâm nhập, thu hồi credential nếu cần |
| Recovery | Có thể mở lại truy cập an toàn chưa? | Kiểm tra sạch, rollback/unblock và theo dõi |
| Lessons learned | Cần cải thiện phát hiện, policy hoặc quy trình gì? | Kết quả diễn tập và nhiệm vụ cải tiến |

**Containment không đồng nghĩa đã xử lý tận gốc.** Rule chặn tạm có thể ngăn đường giao tiếp đang thấy nhưng không khử persistence, sửa lỗ hổng hoặc thu hồi phiên đã bị chiếm.

## 4. Mô hình kiến trúc phòng vệ cho bài lab

Lab mô phỏng ba vùng: Internet/nguồn ngoài, DMZ chứa dịch vụ và vùng người dùng nội bộ. Firewall ở ranh giới và EDR trên host là hai điểm cưỡng chế riêng.

~~~mermaid
flowchart LR
    EXT["EXT-01<br/>Nguồn bên ngoài giả lập"]
    EDGE["WAF / Edge Firewall<br/>Điểm chặn inbound"]
    WEB["WEB-01<br/>DMZ / HTTPS"]
    USER["WS-01<br/>VLAN người dùng"]
    INT["Internal Firewall<br/>Điểm chặn east-west"]
    APP["APP-01<br/>Vùng ứng dụng"]
    EDR["EDR / Host Isolation"]
    LOG["SIEM + Firewall/Flow logs"]

    EXT -->|"HTTPS lab"| EDGE --> WEB
    USER -->|"HTTPS được duyệt"| INT --> APP
    EDR -.->|"Cô lập WS-01 nếu xác minh bị xâm nhập"| USER
    EDGE -. telemetry .-> LOG
    INT -. telemetry .-> LOG
    EDR -. telemetry .-> LOG
~~~

### Danh mục tài sản minh họa

| Tài sản | Vị trí | Địa chỉ ví dụ trong lab | Vai trò |
|---|---|---|---|
| EXT-01 | Mạng mô phỏng bên ngoài | `10.77.10.11` | Sinh một số request HTTP vô hại phục vụ kiểm thử |
| EDGE-01 | Gateway giữa các vùng | `10.77.20.1` | Firewall/WAF thực thi rule tạm |
| WEB-01 | DMZ | `10.77.20.20` | Dịch vụ HTTP/HTTPS kiểm thử |
| WS-01 | User VLAN | `10.77.30.11` | Thiết bị nội bộ có thể được đưa vào cách ly giả lập |
| APP-01 | Application VLAN | `10.77.40.20` | Dịch vụ nội bộ của lab |
| ADMIN-01 | Management VLAN | `10.77.50.10` | Máy quản trị/giám sát được phê duyệt |
| SOC-01 | Monitoring zone | `10.77.60.10` | Hệ thống nhận log và lưu hồ sơ diễn tập |

Địa chỉ `10.77.0.0/16` ở đây là **ví dụ cho môi trường riêng biệt**, cần đổi theo mạng lab thực tế và bảo đảm không xung đột. Không thực hiện bài diễn tập trên địa chỉ, subnet hoặc thiết bị ngoài phạm vi cho phép.

### Luồng chức năng phải bảo vệ

- Máy kiểm thử được phép gọi `WEB-01` theo giao thức được phê duyệt.
- Người dùng hợp lệ từ vùng liên quan vẫn truy cập được tài nguyên cần thiết sau khi nguồn nghi vấn bị chặn.
- `ADMIN-01` và `SOC-01` vẫn có đường quản trị/telemetry cần thiết.
- Sau rollback, luồng của nguồn lab phải phục hồi theo chính sách gốc.

**Tiêu chí thiết kế:** cô lập đúng mối quan hệ `nguồn → đích → dịch vụ`, thay vì tạo rule chặn rộng khiến cả mạng mất liên lạc.

## 5. Khi nào playbook được kích hoạt?

Nên định nghĩa các tín hiệu đầu vào với độ tin cậy và mức tác động dự kiến.

| Nguồn cảnh báo | Dấu hiệu | Cần xác minh |
|---|---|---|
| IDS/IPS/NDR | Phát hiện mẫu quét/khai thác hoặc lưu lượng bất thường | Signature có false positive? IP sau NAT? Có gói bị chặn sẵn? |
| WAF | Nhiều request vi phạm quy tắc đến một ứng dụng | Có CDN/proxy đứng trước? Đúng client IP từ proxy tin cậy? |
| Firewall/flow logs | Kết nối bất thường từ một host đến nhiều đích/cổng | Có job/backup, monitoring, inventory scan được duyệt? |
| EDR | Tiến trình nguy hiểm, tạo kết nối nghi vấn, phát hiện mã độc | Thiết bị/identity được xác nhận đúng và agent còn kết nối? |
| SIEM correlation | Nhiều hành vi khớp thành chuỗi trong thời gian ngắn | Có trùng sự kiện, lệch thời gian hoặc lỗi mapping nguồn? |
| Identity/VPN logs | Đăng nhập lạ, nhiều phiên hoặc thiết bị không phù hợp | MFA, session ID, loại tài khoản, shared egress IP |
| DNS logs | Truy vấn đích đáng ngờ hoặc giải mã domain bất thường | Resolver có ghi đầy đủ? Domain thuộc dịch vụ hợp lệ? |

Không thiết kế playbook tự động cô lập chỉ dựa vào **một cảnh báo mức thấp** hoặc một IP xuất hiện trong threat feed. Cần thêm bối cảnh về tài sản, khả năng ảnh hưởng và loại nguồn.

### Ma trận quyết định minh họa

| Mức | Bằng chứng | Quyết định mặc định |
|---|---|---|
| `LOW` | Một tín hiệu thiếu ngữ cảnh, chưa xác nhận nguồn | Theo dõi và thu thập thêm |
| `MEDIUM` | Nhiều tín hiệu phù hợp, chưa xác nhận tác động | Triage, đề xuất rule tạm có người duyệt |
| `HIGH` | Có IOC rõ, nhiều nguồn độc lập, tài sản xác thực được | Cô lập theo playbook đã phê duyệt, giới hạn blast radius |
| `CRITICAL` | Đang có ảnh hưởng nghiêm trọng hoặc dấu hiệu lan rộng | Kích hoạt incident commander, containment khẩn cấp theo quyền đã phân công |

Các mức này là **ví dụ chính sách tổ chức**, không phải ngưỡng chuẩn chung. Phản ứng khẩn cấp phải nằm trong quyền hạn đã cấp và có audit; khi thiếu thẩm quyền hoặc có nguy cơ ngắt hệ thống trọng yếu, phải nâng cấp quyết định lên người chịu trách nhiệm.

## 6. Preflight: xác minh nguồn và điều kiện được phép chặn

Trước hành động thay đổi chính sách, người điều phối lập hồ sơ:

| Trường | Yêu cầu |
|---|---|
| Incident ID | Mã vụ việc, nguồn alert, ngày giờ UTC, người phụ trách |
| Source identity | IP, host, workload, user và session ID nếu có |
| Target | Đích, giao thức/cổng, ứng dụng và mức độ quan trọng |
| Evidence | Alert ID, bản ghi gốc, thời điểm, sự kiện từ ít nhất các nguồn phù hợp |
| Network context | NAT, VPN, proxy/CDN, IPv4/IPv6, route, segment và firewall path |
| Confidence | LOW/MEDIUM/HIGH/CRITICAL và lý do |
| Proposed scope | Rule/host/session nào sẽ bị hạn chế; cụ thể từ đâu tới đâu |
| Owner & approval | Người có thẩm quyền, stakeholder bị ảnh hưởng, liên hệ khi dừng |
| Temporary duration | Thời gian hiệu lực, phương pháp theo dõi và thời điểm rà soát |
| Rollback | Cấu hình ban đầu, cách đảo thay đổi, người kiểm chứng |

### 6.1. Quy kết nguồn sau NAT, proxy và CDN

Nguồn mà server nhìn thấy có thể là IP của load balancer, proxy, VPN concentrator hoặc NAT gateway. Header `X-Forwarded-For` có thể bị client tự đặt nếu ứng dụng/proxy không thiết lập chuỗi tin cậy chặt chẽ; **không dùng một giá trị header không đáng tin để chặn toàn IP**. Dùng access log của proxy **được tin cậy**, thông tin phiên, NAT translation và bảng mapping địa chỉ theo **đúng thời điểm** để xác định client gốc.

Nếu hàng nghìn người dùng đi qua cùng một IP CGNAT hoặc CDN, nên ưu tiên WAF rule theo request/signature, account/session hoặc rate limit cho đường dẫn cụ thể. Chặn IP chia sẻ tại edge có nguy cơ ảnh hưởng rất lớn.

### 6.2. Kiểm tra đường ảnh hưởng

Phải xác định nguồn có phải là:

- DNS resolver, NTP server, IdP, KMS, proxy, NAT gateway, SIEM collector hoặc EDR management server?
- Jump host, domain controller, thiết bị VPN, đường DR/backup hay máy quản trị khẩn cấp?
- IP động có thể đã đổi chủ sau khi alert được sinh?
- Đường CDN, load balancer hoặc API đối tác mà nhiều dịch vụ cùng sử dụng?

Nếu có, dừng kế hoạch chặn IP rộng và chọn biện pháp hẹp hơn hoặc chuyển cấp quyết định. Nếu máy bị nghi là hệ thống trọng yếu, lựa chọn containment có thể phải phối hợp với chủ hệ thống và phương án vận hành suy giảm.

## 7. Chọn biện pháp cô lập phù hợp

| Công cụ/lớp | Tác dụng chính | Khi nên chọn | Lưu ý quan trọng |
|---|---|---|---|
| WAF | Chặn/rate-limit request theo nguồn, path, rule hoặc phiên | HTTP(S) vào ứng dụng; cần giữ khách hàng chung NAT | Tin cậy địa chỉ client sau proxy, xử lý false positive |
| Edge firewall/ACL | Chặn luồng theo IP/CIDR, cổng, hướng, zone | Nguồn ngoài đã xác minh, phạm vi mạng rõ | Có thể không chặn phiên đang tồn tại; chú ý IPv6 và NAT |
| Internal firewall/segmentation | Chặn east-west giữa vùng | Host nội bộ đang truy cập trái phép sang vùng khác | Không cắt nhầm luồng quản trị/DR/telemetry |
| EDR host isolation | Hạn chế kết nối của endpoint | Thiết bị bị nghi xâm nhập, cần cách ly tại host | Cơ chế ngoại lệ cho EDR/management tùy vendor |
| NAC/quarantine VLAN | Chuyển thiết bị sang mạng cách ly | Thiết bị LAN/Wi-Fi đã xác thực qua NAC | VLAN mới có thể thay IP; kiểm tra DHCP/DNS/agent |
| VPN/session revocation | Ngắt phiên truy cập từ xa | Tài khoản/phiên VPN đáng ngờ | Có thể cần thu hồi token hoặc xác thực lại |
| IAM/account control | Khóa/giới hạn quyền danh tính hoặc thu hồi phiên | Lộ tài khoản hoặc token, IP không phải ranh giới đúng | Quyết định tác động ở cấp tài khoản, có xác nhận owner |
| DNS filtering | Chặn truy vấn domain có hại qua resolver được quản lý | Kênh liên lạc theo tên miền | Không cắt kết nối IP đã mở hoặc DoH ngoài kiểm soát |
| Cloud SG/NSG/network firewall | Giới hạn luồng ở VPC/VNet/instance | Workload cloud hoặc segment được xác minh | Kiểm tra ENI/NIC, route, tag, shared SG, region |
| Kubernetes policy/egress gateway | Giới hạn lưu lượng pod/workload | Pod đã xác định, CNI có hỗ trợ thực thi | IP pod thay đổi; chọn theo label/namespace và xem policy khác |

Với nhiều lớp bảo vệ, tránh tạo các lệnh chặn chồng chéo không được theo dõi. Có thể tạm áp WAF rule tức thời và dùng firewall/EDR để containment tiếp theo, nhưng hồ sơ phải ghi rõ **mỗi biện pháp** và điều kiện tháo gỡ.

### Đường đi quyết định

~~~mermaid
flowchart TD
    Alert["Alert + log gốc"]
    Valid{"Có đủ bằng chứng?<br/>Đã nhận diện đúng nguồn?"}
    Triage["Bổ sung log, NAT/VPN mapping,<br/>owner và tình huống hợp lệ"]
    Type{"Nguồn nằm ở đâu?"}
    External["Nguồn ngoài:<br/>WAF / Edge firewall / Rate limit"]
    Internal["Nguồn nội bộ:<br/>EDR / NAC / segmentation"]
    Identity["Nguồn là danh tính/phiên:<br/>IAM / VPN revoke"]
    Gate{"Đã kiểm tra tác động,<br/>quyền và rollback?"}
    Hold["Giữ nguyên + chuyển cấp / xử lý rủi ro"]
    Apply["Áp rule tạm, lưu change ID và TTL"]
    Verify["Xác minh nguồn bị hạn chế,<br/>luồng hợp lệ còn hoạt động"]
    Monitor["Giám sát, điều tra, quyết định<br/>gia hạn hay gỡ bỏ"]

    Alert --> Valid
    Valid -- "Chưa" --> Triage --> Valid
    Valid -- "Rồi" --> Type
    Type -- "Ngoài" --> External --> Gate
    Type -- "Nội bộ" --> Internal --> Gate
    Type -- "Phiên/tài khoản" --> Identity --> Gate
    Gate -- "Chưa" --> Hold
    Gate -- "Đã" --> Apply --> Verify --> Monitor
~~~

## 8. Playbook vận hành chuẩn

Playbook nên là một thủ tục rõ **vai trò thực hiện, đầu vào, đầu ra, điều kiện dừng** của từng bước.

### Bước 0 — Khởi tạo vụ việc

**Người chịu trách nhiệm:** SOC analyst/on-call.

**Thực hiện:**

1. Tạo incident ID, ghi UTC hiện tại, liên kết alert gốc.
2. Lưu nguyên bản log/sự kiện kèm thời gian thu nhận; xử lý thông tin nhạy cảm theo quyền truy cập.
3. Kiểm tra đã có vụ việc/rule tương ứng hay chưa để tránh tạo nhiều rule trùng.
4. Phân loại mức ảnh hưởng (dịch vụ người dùng, dữ liệu, quyền quản trị, phạm vi vùng mạng).

**Đầu ra:** vụ việc có owner, danh sách nguồn/đích và bằng chứng cơ bản.

### Bước 1 — Xác minh và phân loại nguồn

**Người chịu trách nhiệm:** SOC phối hợp Network/Endpoint/Identity team.

Xác nhận alert bằng cách:

- Đối chiếu ít nhất các loại log phù hợp: IDS alert + firewall flow, WAF request + app log, hoặc EDR event + host network telemetry.
- Kiểm tra thời gian, đồng bộ đồng hồ, địa chỉ IP trước/sau NAT, proxy chain và phiên.
- Đọc bối cảnh bảo trì, quét lỗ hổng có ủy quyền, công việc giám sát và hoạt động dự phòng.
- Xác định nguồn là **IP công cộng**, **host nội bộ**, **workload** hay **danh tính/phiên**.
- Kiểm tra mức tin cậy và độ nghiêm trọng; khi false positive hoặc không đủ dữ liệu, ghi `INSUFFICIENT_EVIDENCE` và chuyển sang triage.

**Điều kiện dừng:** dữ liệu mâu thuẫn, nguồn thuộc hạ tầng chung quan trọng hoặc không xác định được chính sách đang thực thi.

### Bước 2 — Chọn scope hẹp nhất có tác dụng

**Người chịu trách nhiệm:** Network Security/Incident Commander theo phân quyền.

Đối với nguồn ngoài, ưu tiên chặn đúng **IP/identity/request pattern → ứng dụng/đích/cổng** cần bảo vệ. Nếu hoạt động xấu chỉ xảy ra trên một API, WAF rule theo endpoint/behavior có thể tác động ít hơn chặn toàn địa chỉ IP.

Đối với nguồn nội bộ, cần xác định có thể cô lập endpoint tại EDR, chuyển NAC quarantine hay chặn traffic qua inter-zone firewall. Phải giữ kết nối điều tra/management có ủy quyền nếu giải pháp hỗ trợ. Với tài khoản bị chiếm, thu hồi phiên và credential liên quan có thể quan trọng hơn chặn host.

**Đầu ra:** đề xuất biện pháp có đích, hướng, action, owner, TTL, đường rollback và lưu ý về các kết nối đã thiết lập.

### Bước 3 — Phê duyệt và kiểm tra trước khi thay đổi

**Người chịu trách nhiệm:** người có thẩm quyền theo incident severity, chủ dịch vụ khi cần.

- Rà lại rule và điểm thực thi; đảm bảo không chặn admin, logging, DNS, NTP, authentication, backup và dịch vụ thiết yếu.
- Chụp/export cấu hình đang chạy, ghi policy revision, firewall node/region, ID/UUID của rule.
- Xác nhận người trực theo dõi, kênh trao đổi và điều kiện dừng.
- Kiểm tra phương án rollback có thể thực thi bằng tài khoản/quyền đang có.
- Ghi rõ rule tạm có thời hạn; không thêm ngoại lệ không có chủ sở hữu.

Với cơ chế containment khẩn cấp đã được quy định và ủy quyền, playbook có thể cho phép hành động nhanh hơn, nhưng phải bảo đảm dấu vết audit và đánh giá tác động sau hành động.

### Bước 4 — Áp biện pháp và lưu bằng chứng thay đổi

**Người chịu trách nhiệm:** Network/EDR/IAM operator.

1. Ghi `change_id` và `incident_id` vào ticket/metadata, xác định điểm thực thi.
2. Thêm hoặc kích hoạt biện pháp được duyệt, với scope và TTL đã chốt.
3. Xác minh rule đã được **commit/push/apply** thành công trên đúng thiết bị, context hoặc vùng.
4. Kiểm tra policy order, NAT, hai stack IPv4/IPv6 và các tuyến HA nếu chúng có liên quan.
5. Ghi rule ID/UUID thực tế và thời điểm hiệu lực; không coi “API trả HTTP 200” là bằng chứng gói tin đã bị chặn.
6. Nếu kết nối nguy hiểm đã tồn tại, đánh giá **session table/conntrack** và khả năng cắt session theo quy trình nền tảng; thêm rule mới chưa chắc ảnh hưởng phiên cũ.

### Bước 5 — Xác minh hiệu quả và kiểm tra tác động phụ

**Người chịu trách nhiệm:** SOC, Network và Application owner.

Đánh giá **hai mặt**:

- **Negative test:** nguồn lab được chỉ định không còn thực hiện được hành động cần chặn; có log deny/rate-limit/host isolation tương ứng.
- **Positive test:** máy dùng hợp lệ, đường quản trị, DNS, dịch vụ ứng dụng và monitoring vẫn hoạt động; độ trễ và tỷ lệ lỗi không vượt ngưỡng.

Nếu một kết nối thất bại nhưng thiếu log áp dụng rule, không mặc định nguyên nhân là firewall: có thể DNS sai, backend hỏng hoặc route mất. Đối chiếu đường dữ liệu và nhật ký policy.

### Bước 6 — Giám sát, điều tra và giữ containment

**Người chịu trách nhiệm:** Incident Commander, SOC và chủ dịch vụ.

Theo dõi:

- Nguồn cũ có tiếp tục tạo lưu lượng ở đường khác (IPv6, VPN, egress phụ, region khác) không?
- Có sự gia tăng request từ nguồn mới hoặc tài khoản liên quan không?
- Có dấu hiệu mất dịch vụ, khách hàng hợp lệ bị chặn hoặc agent EDR mất kết nối không?
- Có bằng chứng rằng nguyên nhân gốc đã được xử lý, hay cần giữ containment có kiểm soát?

Nếu cần gia hạn rule, phải có owner, lý do, thời hạn mới và rà soát tác động; tránh để rule khẩn cấp trở thành cấu hình vĩnh viễn không được review.

### Bước 7 — Phục hồi/rollback và đóng vụ việc

Chỉ gỡ containment khi đã có quyết định hợp lệ: nguồn không còn là mối đe dọa hoặc đã được xử lý, hệ thống sạch theo mức xác minh cần thiết, tài khoản/token được thu hồi hoặc thay đổi nếu bị xâm phạm, và có kế hoạch theo dõi sau mở lại.

Gỡ **đúng rule/biện pháp do vụ việc tạo**, dựa trên ID/UUID và policy revision; không xóa một rule đang phục vụ vụ việc khác. Kiểm tra:

1. Chính sách được khôi phục đúng thứ tự/ngữ nghĩa và đã apply hoàn toàn.
2. Luồng hợp lệ trở lại theo kỳ vọng, không mở thêm đường nào ngoài baseline.
3. Log/audit của thao tác rollback tồn tại và được liên kết với incident.
4. Quan sát ổn định qua cửa sổ theo dõi rồi đóng ticket, cập nhật postmortem.

## 9. Đặc tả playbook dưới dạng YAML (mẫu để triển khai)

Tệp sau là **đặc tả logic phục vụ thiết kế/đào tạo**, không phải cú pháp mặc định của một sản phẩm SOAR, SIEM, firewall hay EDR. Mọi thao tác thật phải dùng API chính thức, xác thực đúng quyền, có kiểm soát lỗi và phê duyệt như quy trình:

~~~yaml
playbook:
  id: IR-NET-ISOLATE-001
  name: Co lap nguon tan cong da xac minh
  owner: soc-network-security
  version: 1.0
  scope:
    environment: isolated-lab
    allowed_assets: [EXT-01, EDGE-01, WEB-01, WS-01, APP-01]
    excluded_assets: [ADMIN-01, SOC-01]
  triggers:
    - validated_ids_alert
    - verified_waf_abuse
    - confirmed_endpoint_compromise
    - incident_commander_request
  required_evidence:
    - incident_id
    - source_identity_and_attribution_method
    - target_and_service
    - timestamps_utc
    - correlated_log_references
    - asset_owner_and_business_context
  decision_gates:
    source_confidence: high_or_approved_exception
    shared_infrastructure_check: pass
    scope_approval: required
    prechange_backup: required
    rollback_path: verified
    break_glass_authority: documented
  action:
    type: temporary_deny
    source_ip: 10.77.10.11
    destination_ip: 10.77.20.20
    protocol: tcp
    destination_port: 443
    direction: ingress_to_service
    policy_context: edge-lab
    reason: "Lab exercise: approved source isolation"
    incident_id: LAB-IR-012
    rule_owner: network-security-oncall
    expires_after_minutes: 30
    auto_remove: platform_supports_verified_expiry
  validations:
    - blocked_source_cannot_reach_target_service
    - approved_source_still_reaches_target_service
    - deny_audit_event_present
    - admin_and_telemetry_paths_unchanged
  stop_conditions:
    - wrong_asset_or_scope
    - critical_service_impact
    - missing_rollback_access
    - evidence_attribution_conflict
  recovery:
    remove_only_incident_owned_rule: true
    revalidate_service: true
    record_change_and_observations: true
~~~

Các khóa như `scope_approval`, `auto_remove` và `verified_expiry` là yêu cầu thiết kế **cần được hiện thực hóa**. Nếu nền tảng không hỗ trợ TTL tự động, đội on-call cần lịch kiểm tra và nhiệm vụ thu hồi có người chịu trách nhiệm.

### Các bất biến vận hành

- **Idempotency:** cùng một `incident_id` và một nguồn/đích không sinh vô hạn rule trùng; việc chạy lại phải tìm rule hiện hữu và quyết định gia hạn/sửa có ghi nhận.
- **Least privilege:** tài khoản tự động hóa chỉ có quyền thay đổi policy trong scope và truy cập log cần thiết.
- **Concurrency control:** tránh hai quy trình cùng sửa rule/policy khiến nhau ghi đè hoặc làm sai thứ tự.
- **Audit:** mọi quyết định, rule ID, người duyệt, thời điểm apply, kiểm thử và rollback được ghi nhận.
- **Expiry:** quy trình có giới hạn thời gian và cơ chế xem xét khi hết hạn.
- **Fail-safe:** nếu không xác định đúng nguồn hoặc không có đường rollback, dừng tự động hóa và chuyển cấp; không mặc định chặn subnet lớn hơn.

## 10. Sơ đồ trạng thái cho một vụ cô lập

~~~mermaid
stateDiagram-v2
    [*] --> Alerted
    Alerted --> Triaged: Thu log va xac minh
    Triaged --> Rejected: False positive / wrong target
    Triaged --> AwaitApproval: Co bang chung, can phe duyet
    AwaitApproval --> Contained: Ap policy tam
    AwaitApproval --> Triaged: Thieu thong tin
    Contained --> Verified: Negative + positive tests dat
    Contained --> Rollback: Loi pham vi / tac dong phu
    Verified --> Investigating: Theo doi va xu ly nguyen nhan
    Investigating --> Recovered: Du dieu kien go bo
    Investigating --> Verified: Gia han containment co duyet
    Rollback --> Investigating: Khoi phuc va dieu tra tiep
    Recovered --> [*]
    Rejected --> [*]
~~~

Không tự chuyển từ `Contained` sang `Recovered` chỉ vì alert im lặng: sự im lặng có thể do nguồn đổi IP, log bị mất hoặc rule chặn chưa có hiệu lực tại tất cả đường mạng.

## 11. Thực hành lab: nguồn ngoài truy cập WEB-01

### 11.1. Mục tiêu và giả định

**Giả định** EDGE-01 là firewall ở giữa EXT-01 và WEB-01, WEB-01 đang phục vụ HTTPS trong lab. Một nguồn hợp lệ khác, chẳng hạn `10.77.10.12`, cũng cần truy cập WEB-01. Đội lab đã xác nhận quyền thao tác cấu hình trên EDGE-01, có snapshot baseline và đường quản trị dự phòng.

**Kịch bản:** hệ thống sinh một cảnh báo **giả định** từ IDS cho nguồn `10.77.10.11` truy cập WEB-01. Người học phải xác minh log và chặn có thời hạn **chỉ** luồng `10.77.10.11 → 10.77.20.20 TCP/443`, giữ `10.77.10.12` tiếp tục truy cập.

### 11.2. Trình tự thao tác

| Bước | Hành động | Bằng chứng lưu |
|---|---|---|
| 1 | Xác nhận các máy trong scope và đồng bộ giờ | Asset inventory, UTC/NTP check |
| 2 | Gửi một request kiểm thử hợp lệ từ cả hai nguồn tới WEB-01 | Trạng thái HTTP/TLS, thời gian |
| 3 | Xem IDS và firewall flow log giả lập, kiểm tra source NAT | Alert ID, IP mapping, flow 5-tuple |
| 4 | Tạo ticket `LAB-IR-012` và rule đề xuất | Ticket, owner, thời hạn 30 phút |
| 5 | Áp rule tạm tại EDGE-01 theo công cụ lab đã duyệt | Rule UUID, policy revision, commit result |
| 6 | Thử lại hai nguồn, đồng thời xem log deny/allow | Kết quả negative và positive |
| 7 | Kiểm tra không ảnh hưởng ADMIN-01 và SOC-01 | Monitoring status, kiểm tra đường quản trị |
| 8 | Gỡ đúng rule tạm, kiểm tra phục hồi | Rollback log, chính sách sau thay đổi |

### 11.3. Lệnh quan sát không thay đổi cấu hình

Trên Linux lab, có thể dùng lệnh xem route và trạng thái socket:

~~~bash
# Chạy trong máy lab được cấp quyền.
ip route get 10.77.20.20
ss -nt

# Chỉ ghi nhận tối đa 20 packet đúng host/port trong scope.
sudo tcpdump -ni any -c 20 'host 10.77.20.20 and tcp port 443'
~~~

Trên Windows lab:

~~~powershell
# Kết quả chỉ nói về khả năng kết nối TCP, chưa xác nhận policy được áp đúng.
Test-NetConnection -ComputerName 10.77.20.20 -Port 443
Get-Date -Format o
~~~

Các lệnh trên dùng để **quan sát**. Chỉ chạy `tcpdump` trên host/network thuộc scope được phê duyệt và hạn chế capture dữ liệu nhạy cảm. Để chứng minh rule đang chặn, cần kết hợp thêm **log policy tại EDGE-01** và kết quả kiểm thử từ nguồn hợp lệ. Timeout đơn lẻ có thể do dịch vụ không chạy, route hoặc DNS, nên không đủ làm chứng cứ.

### 11.4. Biểu mẫu rule tạm theo ý định

~~~yaml
# Ví dụ policy intent; không phải cấu hình firewall của nhà sản xuất.
rule:
  id: LAB-IR-012-BLOCK-01
  enabled: true
  source: 10.77.10.11/32
  destination: 10.77.20.20/32
  protocol: tcp
  destination_port: 443
  direction: ext_to_dmz
  action: deny
  log: true
  owner: network-security-oncall
  incident: LAB-IR-012
  expires_at_utc: "2026-11-28T08:30:00Z"
  rollback: remove_this_rule_by_exact_id
~~~

Thời điểm trên chỉ minh họa format ISO 8601, không có nghĩa rule cần triển khai ở thời điểm đó. Một số nền tảng không có `expires_at_utc` nguyên thủy; phải vận hành TTL bằng chức năng được hỗ trợ hoặc nhiệm vụ thu hồi có kiểm toán.

### 11.5. Dữ liệu log giả định để phân tích

~~~json
[
  {
    "time_utc": "2026-11-28T08:00:00Z",
    "device": "EDGE-01",
    "source_ip": "10.77.10.11",
    "destination_ip": "10.77.20.20",
    "destination_port": 443,
    "action": "allow",
    "policy": "baseline-allow-https",
    "incident": "LAB-IR-012"
  },
  {
    "time_utc": "2026-11-28T08:05:00Z",
    "device": "EDGE-01",
    "source_ip": "10.77.10.11",
    "destination_ip": "10.77.20.20",
    "destination_port": 443,
    "action": "deny",
    "policy": "LAB-IR-012-BLOCK-01",
    "incident": "LAB-IR-012"
  },
  {
    "time_utc": "2026-11-28T08:05:10Z",
    "device": "EDGE-01",
    "source_ip": "10.77.10.12",
    "destination_ip": "10.77.20.20",
    "destination_port": 443,
    "action": "allow",
    "policy": "baseline-allow-https",
    "incident": "LAB-IR-012"
  }
]
~~~

Đây là **dữ liệu được chuẩn hóa và giả lập**, không phải cấu trúc log gốc của firewall cụ thể. Bộ log này minh họa rằng rule dường như đã hoạt động và nguồn hợp lệ không bị chặn. Muốn xác nhận hoàn toàn phải đối chiếu phiên đang tồn tại, cấu hình đã cài và chức năng dịch vụ.

## 12. Tình huống mở rộng: host nội bộ nghi bị xâm nhập

**Bối cảnh:** EDR phát hiện một tiến trình bất thường trên `WS-01` và NDR ghi nhận host này kết nối tới nhiều dịch vụ quản trị ở vùng ứng dụng. Việc chặn một IP ngoài Internet có thể không ngăn được truy cập east-west nội bộ.

### Playbook điều chỉnh

1. Xác định máy bằng host ID/EDR agent ID và bằng chứng phiên, không chỉ địa chỉ DHCP.
2. Đối chiếu hoạt động quản trị hợp lệ, lịch kiểm thử bảo mật và thay đổi hạ tầng.
3. Xác minh năng lực EDR isolation và đường kết nối quản lý mà EDR cần duy trì.
4. Nếu có quyền và bằng chứng đủ, dùng EDR host isolation hoặc NAC quarantine đã kiểm thử.
5. Ở điểm segmentation, chặn tạm đúng những luồng không được phép đến vùng ứng dụng, đồng thời giữ đường thu thập chứng cứ có phê duyệt.
6. Rà danh tính/phiên liên quan; cân nhắc thu hồi phiên và credential theo chính sách ứng cứu.
7. Sau containment, xác định phạm vi ảnh hưởng và xử lý nguyên nhân trước khi mở lại.

**Ví dụ sai lầm:** khóa toàn bộ subnet `10.77.30.0/24` chỉ vì WS-01 đáng ngờ làm các máy khác mất truy cập, nhưng endpoint bị xâm nhập có thể vẫn đi qua mạng Wi-Fi khác hoặc VPN. Biện pháp theo **host identity + vị trí mạng + quyền danh tính** thường chính xác hơn nếu nền tảng hỗ trợ.

### Bảo đảm đường cứu hộ

Với máy chủ trọng yếu hoặc endpoint từ xa, cần biết rõ thao tác cách ly có cắt luôn đường quản trị hay không. Nếu cách ly làm mất EDR cloud connectivity, phải có quy trình truy cập trực tiếp hoặc đường management/out-of-band phù hợp; nếu không, không thực hiện cách ly mù.

## 13. SOAR: tự động hóa có điều kiện, chống lặp và chống chặn nhầm

Tự động hóa có ích khi phát hiện lặp lại, nhưng càng nhanh càng phải có **guardrail dựa trên chứng cứ và tác động**. Pseudocode sau diễn đạt logic, không chạy trực tiếp:

~~~text
on verified_security_event(event):
    incident = open_or_attach_incident(event)
    source = attribute_source_with_trusted_logs(event)

    if source is UNKNOWN or evidence_is_conflicting(event):
        route_to_analyst("INSUFFICIENT_EVIDENCE")
        return

    if source.is_shared_gateway or source.is_critical_infrastructure:
        require_incident_commander_review()
        return

    proposed = minimal_containment_scope(source, event.target, event.service)
    if not rollback_is_available(proposed):
        require_operator_review("ROLLBACK_UNAVAILABLE")
        return

    if not authorization_is_satisfied(incident, proposed):
        request_scope_approval()
        return

    existing = find_rule_by_incident_and_scope(incident.id, proposed)
    if existing:
        record_idempotent_noop_or_approved_extension(existing)
    else:
        result = apply_temporary_containment(proposed, ttl_minutes=30)
        verify_commit_and_policy_id(result)

    if not negative_test_passes() or not positive_test_passes():
        rollback_exact_incident_rule()
        escalate_to_oncall()
        return

    monitor_effectiveness_and_blast_radius()
    schedule_review_before_expiry()
~~~

### Phân tầng quyền và hành động

| Độ tin cậy / tác động | Hành động tự động phù hợp | Quyền kiểm soát |
|---|---|---|
| Thấp | Làm giàu IOC, chuẩn hóa log, gán ticket | Read-only |
| Trung bình | Đề xuất rule hẹp và dự báo tác động | Người duyệt áp dụng |
| Cao, nguồn lab/scope nhỏ | Áp containment có thời hạn nếu đã ủy quyền | Audit, expiry, kiểm thử, tự rollback khi sai |
| Cao nhưng nguồn dùng chung/hạ tầng trọng yếu | Không tự chặn rộng | Incident Commander phê duyệt và kế hoạch dự phòng |

Hệ thống SOAR phải phân biệt **lỗi API**, **thay đổi policy đang chờ commit** và **thay đổi đã có hiệu lực**. Khi thao tác thất bại, không chạy vòng lặp cấp quyền ngày càng rộng hoặc tự chặn cả subnet như phương án dự phòng.

## 14. Kiểm chứng với nhiều lớp dữ liệu

| Lớp quan sát | Câu hỏi | Bằng chứng cần thu |
|---|---|---|
| Edge firewall | Rule đang hoạt động đúng hướng, source/destination và protocol? | Policy ID/UUID, commit log, deny counter |
| WAF | Request thực sự bị block/rate-limit ở ứng dụng? | WAF action, request ID, route/path, trusted client IP |
| Internal segmentation | Nguồn nội bộ còn kết nối tới đích bị bảo vệ không? | Inter-zone flow, ACL, NAT/route |
| EDR/NAC | Endpoint đã vào trạng thái isolation/quarantine đúng chưa? | Agent/device ID, trạng thái theo thời gian |
| VPN/Identity | Phiên đáng ngờ đã bị revoke theo scope chưa? | Session/revocation events, sign-in logs |
| DNS | Truy vấn đích bị chặn trên resolver phù hợp không? | DNS response/action, resolver và client |
| Application | Người dùng hợp lệ vẫn thực hiện được giao dịch chứ? | SLI, synthetic probe, access log |
| SIEM | Có thể tái dựng mốc thời gian và quyết định containment không? | Timeline, log references, analyst comments |

### Đặc biệt chú ý các phiên đang hoạt động

Nhiều firewall stateful cho phép **established connections** tiếp tục đi qua nhờ session table. Thêm rule deny chỉ ảnh hưởng phiên mới ở một số sản phẩm/cấu hình; cần kiểm tra behavior của nền tảng. Nếu phải cắt session hiện hữu, thực hiện đúng phương pháp có kiểm soát và xác nhận phạm vi session bị tác động. Không xóa toàn bộ state table khi mục tiêu chỉ là một phiên.

### Đặc biệt chú ý failover và multi-region

Khi firewall chạy active/standby hoặc active/active, rule có thể cần được triển khai lên nhiều node; ở cloud, cùng workload có thể có NIC, subnet hoặc region dự phòng. Kiểm tra chính sách và logging sau HA failover, route bất đối xứng và IPv6. Nếu rule chỉ hoạt động trên đường chính, nguồn có thể tiếp tục qua đường phụ.

## 15. Điều kiện rollback và cách tránh tạo sự cố mới

Rollback phải được thiết kế **trước khi áp rule**:

| Tình huống cần dừng/gỡ | Tác động | Phản ứng đúng |
|---|---|---|
| Phát hiện nguồn là proxy/NAT dùng chung | Chặn nhầm nhiều người | Gỡ rule rộng, chuyển sang chặn theo dịch vụ/session/behavior |
| Mất kết nối quản trị hoặc EDR telemetry | Không thể kiểm soát/điều tra tiếp | Dùng đường quản trị dự phòng được duyệt, khôi phục chính sách |
| Dịch vụ hợp lệ thất bại sau thay đổi | Mất availability | Rollback đúng ID, kiểm tra lưu lượng và ứng dụng |
| Rule áp sai thứ tự/zone/region | Chặn sai hoặc không có hiệu lực | Khôi phục policy revision, rà path và deploy lại có duyệt |
| IP nguồn bị tái cấp phát hoặc thay đổi | Rule chặn nhầm tài sản mới | Đối chiếu lại host/identity mapping, sửa scope/thu hồi rule |
| Điều tra cho thấy false positive | Duy trì chặn không cần thiết | Gỡ rule, phân tích detector và cập nhật điều kiện triage |
| Sự cố đã xử lý và owner duyệt mở lại | Cần phục hồi truy cập hợp lệ | Gỡ đúng biện pháp của incident, kiểm tra sau mở lại |

**Rollback chính xác** yêu cầu biết rule ID/UUID, policy revision, thứ tự, context, owner và vị trí trong hệ thống quản lý. Không chỉ xóa một rule có tên gần giống, không xóa danh sách chặn của nhiều vụ việc.

## 16. Mẫu báo cáo sự cố và bằng chứng

~~~text
Incident ID: LAB-IR-012
Playbook version: IR-NET-ISOLATE-001 v1.0
Environment: isolated lab
Window (UTC): [start] - [end]
Incident Commander / SOC / Network owner: [assigned]

Alert:
  Source: [trusted log ID and time]
  Observed behavior: [description]
  Confidence: [LOW / MEDIUM / HIGH / CRITICAL]
  Source attribution: [IP/host/identity + NAT or proxy context]
  Target/service: [destination, protocol, port]
  Scope impact: [affected asset/service]

Containment decision:
  Enforcement point: [edge/WAF/EDR/NAC/IAM/...]
  Rule/operation: [exact approved action]
  Incident and change IDs: [ids]
  Approval: [person, time, authorization]
  Expiry: [UTC]
  Baseline backup/policy revision: [reference]

Validation:
  Source denied/isolated: [PASS/FAIL/NOT_TESTED + evidence]
  Approved clients unaffected: [PASS/FAIL/NOT_TESTED + evidence]
  Existing sessions evaluated: [result]
  Management/logging intact: [result]
  HA/IPv6/alternate route evaluated: [result]

Monitoring and outcome:
  Residual traffic observed: [yes/no/unknown + scope]
  False positives / business impact: [details]
  Root cause handled: [yes/no/in progress]
  Rollback/unblock: [time, exact rule, operator, verification]
  Follow-up owner/date: [person and deadline]
~~~

Đính kèm **tham chiếu** tới log gốc, phiên bản policy, kết quả kiểm thử và timeline. Không sao chép thông tin xác thực, token hoặc dữ liệu riêng tư không cần thiết vào báo cáo.

## 17. KPI và tiêu chí nghiệm thu bài lab

### 17.1. Các số đo hữu ích

| Chỉ số | Định nghĩa | Giới hạn |
|---|---|---|
| Time to validate | Từ alert tới khi nguồn được xác minh đủ | Cần timestamp đồng bộ, không tính theo thời gian ticket bị tạo muộn |
| Time to contain | Từ khi sự cố được xác nhận tới khi biện pháp thực sự có hiệu lực | Không lấy mốc “gửi lệnh” làm hoàn tất |
| Containment effectiveness | Các luồng đã xác định cần chặn thực sự bị hạn chế | Cần kiểm tra nguồn/đích/dịch vụ và đường dự phòng |
| Collateral impact | Số dịch vụ/nguồn hợp lệ bị ảnh hưởng và độ dài gián đoạn | Không dùng số false positive bằng 0 nếu không có đo lường |
| Rollback time | Từ quyết định gỡ đến khi policy và dịch vụ phục hồi | Có thể bị ảnh hưởng bởi policy push hoặc failover |
| Evidence completeness | Tỷ lệ trường bắt buộc có bằng chứng đáng tin | Phân biệt UNKNOWN với không có sự kiện |
| Rule hygiene | Rule tạm đã hết hạn được gỡ/đánh giá đúng lịch | Theo dõi cả rule trùng và rule không có owner |

### 17.2. Bảng chấm kết quả

| Tiêu chí | Kỳ vọng đạt |
|---|---|
| Định danh | Không nhầm IP NAT/CDN/proxy với host hoặc người dùng gốc |
| Quyết định | Có confidence, tác động dự kiến, quyền thực hiện và lý do |
| Scope | Rule hẹp theo nguồn/đích/dịch vụ; không làm thay đổi subnet ngoài scope |
| Kiểm soát | Xác nhận apply/commit và đánh giá established sessions |
| Negative test | Nguồn lab bị cô lập khỏi dịch vụ đã chọn |
| Positive test | Nguồn hợp lệ vẫn truy cập và telemetry còn hoạt động |
| Rollback | Gỡ đúng rule tạm, phục hồi hành vi baseline |
| Báo cáo | Có UTC timeline, evidence references, owner, TTL, kết luận và follow-up |

**Không đạt** nếu chỉ có ảnh chụp dòng lệnh “block IP” nhưng không có bằng chứng hiệu lực, tác động phụ và kết quả gỡ bỏ.

## 18. Câu hỏi phân tích và bài tập mở rộng

1. WAF báo nhiều request nguy hiểm từ IP của một CDN. Vì sao không nên chặn ngay IP này tại edge firewall? Cần kiểm tra chuỗi proxy tin cậy và lựa chọn biện pháp nào?
2. Máy trạm WS-01 đổi IP sau DHCP lease renewal. Playbook dùng IP cũ có còn cô lập đúng thiết bị không? Nguồn định danh nào bền hơn?
3. Firewall xác nhận rule deny đã commit nhưng IDS vẫn thấy cùng flow. Bạn cần kiểm tra session table, tuyến, NAT, HA và vị trí sensor ra sao?
4. Vì sao một rule chỉ có trên IPv4 hoặc region chính có thể để nguồn tiếp tục truy cập qua đường khác?
5. Nếu EDR host isolation khiến máy mất kết nối với SOC và chủ hệ thống không có đường quản trị dự phòng, quyết định nào giảm rủi ro hơn?
6. Khi nào có thể tự động hóa chặn, khi nào phải có phê duyệt của Incident Commander?
7. Nếu rule tạm hết hạn trước khi điều tra xong, playbook nên xử lý gia hạn như thế nào để tránh cô lập vô thời hạn?
8. Trong tình huống nguồn bị chiếm quyền là tài khoản dịch vụ, vì sao thao tác chặn IP riêng lẻ có thể không đủ?

**Gợi ý trả lời:** (1) CDN là hạ tầng chia sẻ; xác minh IP thực từ proxy đáng tin và dùng WAF rule theo endpoint/behavior. (2) Địa chỉ động có thể được cấp lại; dùng asset/agent ID, NAC identity hoặc mapping DHCP tại thời điểm sự kiện. (3) Rule mới không chắc cắt phiên cũ, sensor có thể ở ngoài điểm chặn hoặc đường phụ. (4) IPv6/multi-region/HA có điểm thực thi riêng. (5) Chuyển cấp để chọn containment có đường quản trị/forensics phù hợp. (6) Theo mức tin cậy, phạm vi, quyền đã cấp và blast radius. (7) Có quyết định gia hạn theo owner, TTL và audit. (8) Token hoặc tài khoản có thể tiếp tục dùng từ host khác, cần phối hợp IAM và xử lý nguyên nhân.

### Bài tập mở rộng: nguồn dùng chung

Giả sử alert từ địa chỉ công cộng `203.0.113.22` thuộc một VPN gateway phục vụ hàng trăm nhân viên. Chỉ một phiên từ tài khoản `lab.suspect` gọi API nội bộ trái quy định. Hãy sửa playbook để:

- Xác định đúng user/session thông qua VPN và IdP logs.
- Ưu tiên chấm dứt **phiên cụ thể** hoặc thu hồi token/đặt lại quyền theo quy trình.
- Giữ quyền truy cập hợp lệ của người dùng khác qua gateway.
- Thu thập audit về người thực hiện, session bị revoke và kiểm tra sau thao tác.

Đây là một ví dụ về **containment dựa trên danh tính**, giúp giảm tác động phụ so với chặn một IP chia sẻ.

## 19. Checklist cuối bài

- [ ] Đã ghi rõ phạm vi và xác nhận thẩm quyền đối với thiết bị/nguồn trong lab.
- [ ] Có alert gốc, timeline UTC, bằng chứng liên quan từ log phù hợp.
- [ ] Đã phân biệt IP công cộng, host nội bộ, NAT/proxy/VPN, danh tính và phiên.
- [ ] Đã phân biệt nguồn tấn công bên ngoài với endpoint bị nghi xâm nhập bên trong.
- [ ] Có ma trận chọn WAF/firewall/EDR/NAC/IAM/DNS theo loại nguồn.
- [ ] Có rule hẹp, owner, incident ID, hạn dùng và cơ chế ngăn tạo rule trùng.
- [ ] Có backup policy, rollback, quyền phê duyệt và liên hệ khi dừng.
- [ ] Đã kiểm tra routing, NAT, IPv4/IPv6, HA, đường phụ và phiên đang hoạt động.
- [ ] Đã làm negative test và positive test, lưu log hiệu lực và tác động phụ.
- [ ] Đã gỡ biện pháp tạm đúng phạm vi và xác minh dịch vụ phục hồi.
- [ ] Có báo cáo, KPI, những khoảng trống quan sát và hành động cải tiến.

## 20. Ghi nhớ

Một playbook cô lập nguồn tấn công hiệu quả không dừng ở lệnh “deny IP”. Nó phải trả lời **nguồn thực sự là ai, đường nào đang gây hại, điểm kiểm soát nào đúng, phạm vi nhỏ nhất là gì, ai phê duyệt, bằng chứng nào chứng minh đã chặn, và khi nào có thể gỡ**. Phối hợp IDS/IPS, WAF, firewall, VPN, phân đoạn, EDR, IAM, DNS và giám sát giúp giảm tác động của sự cố mà vẫn giữ đường quản trị và dịch vụ hợp lệ. Kết quả phải được kiểm chứng qua cả **khả năng hạn chế hành vi nguy hiểm** lẫn **khả năng phục hồi an toàn**.
