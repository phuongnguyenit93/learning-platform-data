# Đào tạo operator về dấu hiệu tấn công

## 1. Vai trò của operator trong vận hành mạng an toàn

Trong chương **Quản trị vận hành mạng an toàn** thuộc module **SECURITY_NETWORK_SECURITY**, người vận hành mạng (network operator, NOC engineer, ca trực hạ tầng) là tuyến quan sát đầu tiên khi trạng thái mạng đổi bất thường. Các hệ thống do operator theo dõi thường bao gồm router/switch, firewall, VPN, IDS/IPS, DNS, load balancer, mạng Wi-Fi, các kết nối cloud và các dịch vụ hỗ trợ như NTP, AAA, syslog, monitoring.

Operator không cần trở thành chuyên gia phân tích mã độc để phát hiện tín hiệu quan trọng. Nhiệm vụ trước mắt là **nhận biết sai lệch, xác minh bằng chứng, đánh giá tác động và chuyển đúng người xử lý**, đồng thời giữ dịch vụ vận hành và không làm mất dấu vết của sự cố. Khi cần xử lý sâu hơn, đội SOC/CSIRT/Incident Response (IR) thực hiện điều tra an ninh và chỉ đạo cô lập, khắc phục theo thẩm quyền.

Bài học gắn kết các lớp phòng vệ: phân đoạn mạng, kiểm soát firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và cloud; qua đó giúp operator phân tích lưu lượng, hình dung đường đi của mối đe dọa, phát hiện xâm nhập sớm và hỗ trợ kiến trúc an toàn.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt **alert, anomaly, indicator, incident và outage**, tránh coi mọi cảnh báo là tấn công.
2. Nêu các dấu hiệu đáng chú ý của scanning, brute force/password spraying, beaconing, DNS tunneling, lưu lượng east–west bất thường, DDoS, lạm dụng quyền quản trị, giả mạo mạng nội bộ, rủi ro Wi-Fi và thay đổi cloud network policy.
3. Chọn đúng nguồn telemetry: firewall traffic/threat log, DNS resolver, VPN/AAA, IDS/IPS/NDR, NetFlow/IPFIX, SNMP/telemetry, Wi-Fi controller, EDR, cloud flow/audit và syslog.
4. Phân biệt **fact – hypothesis – unknown**, nối IP với tài sản đúng thời điểm và giải thích các điểm mù như NAT, proxy, cache, TLS, DoH/DoT hoặc sampling.
5. Thực hiện triage theo thứ tự **an toàn vận hành → xác nhận sự kiện → đánh giá tác động → định tuyến escalation → lưu chứng cứ**.
6. Viết ticket/SITREP rõ thời gian, tài sản, mức tác động, bằng chứng và những việc đã làm; bàn giao đủ dữ liệu cho SOC/IR.
7. Thực hành tabletop trên log giả lập, chấm điểm quyết định và đưa bài học vào runbook ca trực.

### 1.2. Kết quả nào thuộc trách nhiệm operator?

| NOC/operator thường chịu trách nhiệm | SOC/IR hoặc vai trò có thẩm quyền quyết định |
|---|---|
| Theo dõi trạng thái link, route, DNS, VPN, firewall, IDS/IPS và chất lượng log | Kết luận sự cố an ninh, điều tra nguyên nhân tấn công và mức độ xâm nhập |
| Ghi nhận dấu hiệu bất thường và xác minh nguồn sự kiện | Phân tích sâu endpoint/forensics, xác định phạm vi compromise |
| Kiểm tra reachability, route, interface, policy hit, telemetry health | Ra quyết định containment trên diện rộng khi có rủi ro nghiệp vụ |
| Mở ticket, bảo quản log, chuyển escalation đúng SLA | Điều phối CSIRT, pháp chế, truyền thông và chủ dữ liệu khi cần |
| Thực hiện thay đổi đã được phê duyệt, có rollback | Phê duyệt phương án khắc phục và điều kiện kết thúc incident |

Ranh giới vai trò thay đổi theo tổ chức. Một ca trực NOC có thể được ủy quyền chặn một IP rõ ràng theo playbook, nhưng không được tự suy rằng mình có quyền cô lập subnet, xóa log, clear toàn bộ session hay shutdown thiết bị trọng yếu.

## 2. Khung tư duy: sự kiện khác cảnh báo, sự cố và gián đoạn

### 2.1. Định nghĩa vận hành

- **Event:** một thay đổi/trạng thái được ghi nhận, chẳng hạn số lần đăng nhập VPN thất bại tăng.
- **Alert:** hệ thống giám sát so khớp điều kiện và tạo thông báo. Điều kiện có thể sai hoặc thiếu bối cảnh.
- **Anomaly:** giá trị khác baseline đáng kể nhưng chưa rõ nguyên nhân; tăng traffic do triển khai phần mềm cũng là anomaly.
- **Indicator:** dấu hiệu có thể liên quan hoạt động không mong muốn (ví dụ nhiều kết nối tới cổng quản trị, process lạ phát kết nối).
- **Security incident:** sự kiện hoặc chuỗi sự kiện được tổ chức đánh giá là xâm phạm/đe dọa chính sách hoặc bảo mật, theo tiêu chí nội bộ.
- **Outage:** mất dịch vụ hoặc suy giảm chất lượng; nguyên nhân có thể là hỏng phần cứng, cấu hình sai, quá tải hợp lệ hoặc tấn công.

**Không có tương đương một-một** giữa outage và attack. Tấn công DDoS có thể gây outage; sai cấu hình DNS cũng gây outage tương tự. Một hành vi dò quét có thể không làm gián đoạn dịch vụ nhưng vẫn đáng điều tra bảo mật.

### 2.2. Tách điều đã thấy khỏi cách giải thích

| Tình huống | Fact có thể xác minh | Hypothesis cần kiểm chứng |
|---|---|---|
| Tăng nhiều truy vấn DNS NXDOMAIN | Resolver log ghi tăng RCODE=NXDOMAIN từ một số client | DGA, lỗi ứng dụng, deployment mới hoặc DNS misconfiguration |
| SSH login thất bại hàng loạt | AAA log có số lượng thất bại tăng theo thời gian | Password spraying, credential lỗi, job automation lỗi |
| Firewall CPU tăng | Telemetry ghi CPU > baseline, packet drop hoặc session tăng | DoS, log storm, thay đổi rule/IPS, lỗi phần mềm |
| Nhiều thiết bị đột ngột mất Wi-Fi | Controller ghi disassociation hoặc authentication failure | RF interference, AP outage, controller issue, deauthentication attack |
| Workload cloud kết nối đích mới | Flow log có destination mới hoặc egress tăng | Cập nhật hợp lệ, cấu hình sai, C2, dữ liệu rò rỉ |

Khi chưa đủ dữ liệu, ghi **“nghi vấn”** hoặc **“chưa xác định”**, không ghi “đã bị hack” chỉ từ biểu đồ traffic.

## 3. Lớp phòng thủ và điểm quan sát của operator

### 3.1. Bản đồ giám sát mạng

~~~mermaid
flowchart LR
    U["User / Wi-Fi / IoT"] --> A["Access switch / NAC"]
    A --> F["Firewall / IDS-IPS"]
    V["VPN / Partner"] --> F
    F --> D["DNS / Shared services"]
    F --> S["Application / Data"]
    F --> C["Cloud VPC / VNet"]
    A -. "telemetry / syslog" .-> SIEM["NOC dashboards / SIEM"]
    F -. "traffic / threat / session" .-> SIEM
    D -. "resolver logs" .-> SIEM
    V -. "AAA / VPN logs" .-> SIEM
    C -. "flow / audit" .-> SIEM
    S -. "EDR / app logs" .-> SIEM
~~~

Các đường nét đứt thể hiện **đường thu log**, không phải đường lưu lượng người dùng. Dashboard có thể hiện trạng thái tốt trong khi sensor/log pipeline không hoạt động; phải giám sát cả **sức khỏe của việc giám sát**.

### 3.2. Mỗi nguồn nói được điều gì?

| Nguồn | Chỉ số hoặc sự kiện quan trọng | Giới hạn cần nhớ |
|---|---|---|
| Interface/optical telemetry | Băng thông, lỗi CRC, drops, utilization, duplex, flaps | Không phân loại được ý định của packet |
| Routing/BGP/OSPF | Adjacency, prefix, next hop, route change, convergence | Route thay đổi có thể do maintenance; có route chưa chứng minh traffic thực đi qua |
| Firewall traffic/session/NAT | IP, port, policy, action, zone, translation, session duration | Log ALLOW không chứng minh ứng dụng hoạt động; NAT có thể ẩn nguồn |
| IDS/IPS/NDR | Signature, hành vi, alert severity, action, flow link | Alert có false positive; IPS drop có thể gây gián đoạn hợp lệ |
| DNS resolver | Client, QNAME, QTYPE, RCODE, answer, timestamp | Cache, forwarding, DoH/DoT khiến thiếu tầm nhìn |
| VPN/AAA/IdP | Login, MFA, user, IP pool, session start/end, lỗi xác thực | IP VPN có thể thay đổi, MFA success không loại trừ lạm dụng tài khoản |
| Proxy/SWG | URL/host quan sát được, user, action, TLS/proxy result | HTTPS passthrough không cho thấy payload |
| NetFlow/IPFIX | Nguồn/đích, bytes, packets, duration và tần suất | Thường chỉ metadata, có sampling/aggregation |
| WLAN controller/NAC | AP, SSID, client, roam, 802.1X, VLAN assignment | RF noise và roaming dễ giống tấn công |
| EDR/host log | Process, user, socket, file event, policy action | Có thể thiếu agent/visibility trên IoT hoặc appliance |
| Cloud audit/flow | Network policy, route, IAM change, VPC/VNet flow | Log có thể trễ/sampling; provider-managed service thiếu PCAP |
| NTP/syslog pipeline | Clock offset, ingest delay, missing device logs | Log đồng hồ lệch có thể đảo thứ tự sự kiện |

**Quy tắc thực hành:** một tín hiệu đủ để mở cuộc kiểm tra, nhưng kết luận nghiêm trọng nên được củng cố bởi **ít nhất hai nguồn độc lập** khi có thể. Số nguồn không thay thế chất lượng chứng cứ.

### 3.3. Năm điểm mù hay gặp

1. **NAT/proxy/resolver:** IP nhìn thấy trên gateway có thể thuộc trung gian, không phải máy bị nghi ngờ.
2. **Mã hóa:** TLS, VPN, DoH/DoT khiến sensor mạng không đọc được nội dung ở một số điểm quan sát.
3. **Vị trí capture:** sensor bên ngoài có thể không thấy lưu lượng east–west trong cùng VLAN/VPC.
4. **Dữ liệu thiếu:** NetFlow sampling, log retention, packet loss, logger quá tải và đồng hồ lệch.
5. **Chính sách khác nhau theo tuyến:** IPv6, route dự phòng, overlay, split tunnel hoặc cloud peering có thể đi ngoài firewall dự kiến.

Operator cần ghi rõ **“không quan sát được”**, khác với **“không xảy ra”**.

## 4. Dấu hiệu tấn công: cách nhìn qua các lớp mạng

### 4.1. Dò quét, khám phá dịch vụ và reconnaissance

**Dấu hiệu quan sát:** một nguồn kết nối ngắn tới nhiều địa chỉ hoặc nhiều cổng; số lượng kết nối thất bại tăng; firewall log có nhiều DENY/TCP SYN; IDS/NDR báo hành vi port scan.

**Giải thích hợp lệ có thể có:** hệ thống vulnerability scanner đã đăng ký, service discovery, kiểm thử được phê duyệt, monitor health check sau thay đổi route.

**Operator nên làm:** kiểm tra asset nguồn, thời gian, danh sách máy quét được phê duyệt, phạm vi đích, rule thực match và chủ hệ thống. Nếu nguồn không có trong inventory scanner và nhắm các cổng quản trị, ưu tiên báo SOC/IR.

**Không làm:** tự quét ngược IP lạ, đăng nhập đích ngoài scope hoặc trả đũa.

### 4.2. Brute force, password spraying và tài khoản bị lạm dụng

**Dấu hiệu:** số lần đăng nhập VPN, SSH, RDP, Wi-Fi 802.1X hoặc IdP thất bại tăng; một nguồn thử nhiều user; một user bị thử từ nhiều nguồn; có phiên thành công bất thường sau chuỗi thất bại; MFA push bất thường.

**Phân biệt:** một người dùng nhập sai mật khẩu liên tục khác với nhiều tài khoản cùng thất bại từ một tập nguồn. Password spraying thường dùng ít thử trên nhiều tài khoản để né khóa tài khoản; không thể kết luận chỉ từ một thống kê aggregated.

**Kiểm tra bổ sung:** username đã được bảo vệ, source IP, VPN pool, device identity, thời điểm, account lockout, danh sách thay đổi password/SSO/AAA và maintenance. Nếu có xác thực thành công từ thiết bị lạ, chuyển ưu tiên cao hơn.

**Lưu ý riêng tư:** không đưa mật khẩu, token hoặc dữ liệu xác thực nhạy cảm vào ticket chung.

### 4.3. Beaconing và liên lạc điều khiển nghi vấn

**Dấu hiệu:** một host gửi nhiều kết nối nhỏ tới đích mới/hiếm theo chu kỳ, có DNS first-seen, user/process không giải thích được; policy egress bất thường.

**Giải thích hợp lệ:** monitoring agent, update service, time sync, API polling, health check và CDN.

**Kiểm tra bổ sung:** DNS/flow/proxy/firewall/EDR, mức hiếm so baseline của cùng loại host, đối chiếu process owner. Một luồng TLS/HTTPS nhỏ lặp lại **không tự chứng minh C2** hoặc nội dung tải về.

### 4.4. DNS tunneling, DGA và DNS abuse

**Dấu hiệu có thể gặp:** nhiều tên DNS dài hoặc có nhãn biến đổi dưới một zone, distinct QNAME ratio tăng, TXT query bất thường, NXDOMAIN tăng, query rate thay đổi và DNS egress đi thẳng resolver ngoài chính sách.

**Khả năng hợp lệ:** CDN, hash/ID ứng dụng, DNSSEC/TXT verification, email DKIM/SPF, lỗi resolver, ứng dụng mới, cache-busting.

**Kiểm tra bổ sung:** phân tích theo client + zone + cửa sổ, QTYPE, RCODE, tên thực, bản ghi trả lời, process và DNS policy. DGA thường có nhiều base domain thay đổi; DNS tunneling thường tập trung nhiều subdomain dưới một số zone; hai hiện tượng có thể kết hợp nhưng không đồng nghĩa.

**Lưu ý:** QNAME có thể chứa định danh nhạy cảm; hạn chế chia sẻ log thô. DoH/DoT làm QNAME không nhìn thấy từ PCAP TLS thông thường.

### 4.5. Lateral movement và traffic east–west trái phép

**Dấu hiệu:** máy user lần đầu mở kết nối SMB, RDP, SSH, WinRM hoặc database tới nhiều server; firewall/NAC thấy USER → MGMT/DATA bị từ chối; authentication server ghi truy cập ngoài lịch; VLAN/VRF có route mới mở reachability.

**Giải thích hợp lệ:** bản vá, phần mềm quản trị được phê duyệt, backup, migration, domain management, triển khai hệ thống.

**Kiểm tra bổ sung:** host/process, security zone, rule ID, change record, endpoint owner, danh sách server quản trị được phép. Cổng 445/3389/22 xuất hiện trong flow **không chứng minh có xâm nhập**; cần xác định nguồn và quyền.

### 4.6. DDoS, flood và resource exhaustion

**Dấu hiệu:** packets per second/connection attempts tăng mạnh, link bị bão hòa, firewall session table/CPU cao, drop/latency tăng, dịch vụ không đáp ứng, nhiều nguồn nhắm một VIP.

**Phân biệt vận hành:** chiến dịch hợp lệ, traffic spike do sự kiện công khai, CDN lỗi, retry storm, routing loop hoặc lỗi network appliance cũng gây tăng tải.

**Operator nên làm:** xác định dịch vụ tác động, chiều lưu lượng, interfaces, packet/syn/session rate và phạm vi khách hàng; đối chiếu upstream, CDN/DDoS protection và NOC network owner. Bật biện pháp chống DDoS theo runbook được phê duyệt; không tự null-route toàn bộ subnet.

### 4.7. Bất thường định tuyến và dấu hiệu chuyển hướng lưu lượng

**Dấu hiệu:** BGP prefix xuất hiện từ peer bất ngờ, route quảng bá sai, next hop thay đổi không có ticket, đột ngột chuyển đường qua vùng không tin cậy, tần suất BGP flap tăng; traffic qua vùng inspection giảm dù tổng băng thông vẫn giữ.

**Nguyên nhân hợp lệ:** bảo trì nhà cung cấp, failover, thay chính sách peering, mạng hội tụ hoặc sai cấu hình.

**Operator nên làm:** chụp RIB/FIB, BGP updates, prefix/AS-path được phép xem, change record và đường về. Việc phát hiện **route anomaly** chưa đủ kết luận “BGP hijack”; cần so đối chiếu nhiều vantage point và thông tin từ carrier/peering team.

### 4.8. Lạm dụng management plane

**Dấu hiệu:** SSH/HTTPS/SNMP/API vào switch, firewall hoặc controller từ user/guest zone; thay đổi policy không có change ID; login admin ngoài giờ; xuất hiện tài khoản quyền cao mới; thay syslog/AAA/NTP hoặc tắt giám sát.

**Nguyên nhân hợp lệ:** automation, bảo trì, đường OOB/VPN đặc biệt, emergency break-glass có phê duyệt.

**Rủi ro:** một lần thay đổi route/ACL trái phép có thể mở đường sang nhiều vùng hoặc vô hiệu hóa telemetry. Ưu tiên bảo toàn log AAA, config audit, event time và xác thực người phê duyệt.

### 4.9. Dấu hiệu tấn công mạng không dây

**Dấu hiệu:** authentication failures tăng ở một AP/SSID, deauthentication/disassociation cao, rogue AP/SSID giống tên doanh nghiệp, thay đổi VLAN assignment, nhiều thiết bị IoT mất kết nối đồng thời.

**Nguyên nhân hợp lệ:** RF interference, AP reboot, controller failover, roaming, thay chứng chỉ RADIUS, mật khẩu/802.1X hết hạn.

**Operator nên làm:** kiểm tra RF/channel, controller AP status, RADIUS/802.1X logs, NAC/VLAN mapping, thời điểm thay đổi chính sách. Không kết luận deauthentication attack chỉ từ số lượng disconnect.

### 4.10. Cloud network và dịch vụ công khai sai phạm vi

**Dấu hiệu:** security group/NSG rule mở cổng quản trị ra Internet, tạo public IP/route mới, NAT egress tăng bất thường, VPC/VNet peering mới, firewall bypass hoặc flow giữa workload chưa có trong ma trận.

**Nguyên nhân hợp lệ:** triển khai hạ tầng, CI/CD, failover, autoscaling, yêu cầu hệ thống mới.

**Operator nên làm:** tra cloud audit trail, identity thực hiện, change pipeline, asset owner, route table trước/sau, policy effective; chuyển nhóm cloud security hoặc SOC khi phát hiện quyền quá rộng không có phê duyệt.

## 5. Xây baseline và ngưỡng cảnh báo có bối cảnh

### 5.1. Baseline phải phù hợp loại tài sản

Không nên so traffic của core router, DNS resolver, proxy doanh nghiệp, máy người dùng và IoT bằng cùng một ngưỡng. Cần nhóm theo:

- Vùng mạng/VLAN/SSID, site, IP pool VPN và loại thiết bị.
- Giờ làm việc/ngày nghỉ, giờ backup, thời gian chạy batch và sự kiện kinh doanh.
- Dịch vụ/port, hướng, source–destination, ứng dụng và nhà cung cấp.
- Lịch triển khai, bản vá, thay đổi định tuyến, thay certificate hoặc cập nhật agent.
- Mức độ đầy đủ của log và phương pháp đo: flow count, HTTP requests, DNS queries hay packets.

Ví dụ ngưỡng **thực hành** do đội vận hành tự điều chỉnh:

| Feature | Ví dụ hành vi cần xem xét | Vì sao không nên dùng làm kết luận ngay |
|---|---|---|
| Số đăng nhập VPN thất bại/5 phút | Cao gấp nhiều lần baseline của cùng VPN pool | SSO outage cũng gây nhiều retry |
| DNS NXDOMAIN ratio | Bất ngờ tăng trên một client hoặc nhóm host | DNS deployment hoặc lỗi app |
| Băng thông vào VIP | Tăng gấp nhiều lần baseline cùng giờ | Sự kiện traffic hợp lệ hoặc CDN |
| DENY tới management subnet | Nhiều host USER/GUEST cùng thử SSH | Có thể do sai health probe hoặc config |
| Route change ngoài lịch | Prefix mới hoặc next hop thay đổi | Có thể do failover đã định trước |
| Egress rare destination | Host gọi đích mới sau giờ làm | Update agent hoặc dịch vụ mới |
| Interface drops | Drops tăng trong khi utilization cao | Congestion, optic fault hoặc flood |

Không có con số x/giây hay y% đúng cho mọi doanh nghiệp. Ưu tiên cảnh báo **nhiều tín hiệu liên quan cùng tài sản và thời điểm** hơn là ngưỡng cứng toàn mạng.

### 5.2. Thống kê căn bản

**Tốc độ sự kiện (rate)** trong cửa sổ T giây:

\[
r=\frac{\text{số sự kiện trong cửa sổ}}{T}.
\]

**Tỷ lệ thất bại xác thực**:

\[
p_{\mathrm{fail}}=\frac{\text{số lần xác thực thất bại}}{\text{tổng số lần xác thực}}.
\]

Hai chỉ số cần mẫu đủ lớn, phân biệt user/host/zone và chất lượng log. Nếu chỉ có một lần xác thực và bị lỗi, tỷ lệ thất bại 100% không tự động là sự cố bảo mật.

**Trung vị và phân vị cao (p95/p99)** thích hợp đánh giá latency và kích thước response khi phân phối lệch; vẫn cần kiểm tra outlier, sampling và cửa sổ thời gian. Khi so trước/sau thay đổi, cố gắng giữ cùng cách đo và điểm sensor.

### 5.3. Tương quan hơn một tín hiệu

Một máy vừa xuất hiện destination DNS mới, đồng thời có nhiều flow nhỏ lặp đều và EDR ghi tiến trình chưa rõ sẽ đáng ưu tiên hơn máy có một DNS query hiếm. Tương tự, nhiều VPN login thất bại kèm một login thành công từ IP lạ và thay đổi firewall rule sau đó có ý nghĩa hơn mỗi alert đơn lẻ.

**Tương quan không tự chứng minh quan hệ nhân quả**: NOC phải nêu độ chắc chắn và điều gì cần xác minh tiếp.

## 6. Quy trình triage chuẩn cho ca trực

~~~mermaid
flowchart TD
    A["Alert / dashboard anomaly"] --> B{"Có ảnh hưởng dịch vụ<br/>hoặc dấu hiệu nguy hiểm khẩn cấp?"}
    B -->|Có| C["Mở incident bridge theo quy trình<br/>báo NOC/SOC/IR phù hợp"]
    B -->|Chưa rõ| D["Kiểm tra sensor health, timestamp,<br/>scope, change calendar"]
    C --> D
    D --> E{"Sự kiện có được<br/>nguồn khác xác nhận?"}
    E -->|Không đủ dữ liệu| F["Ghi INCONCLUSIVE<br/>bổ sung logs/owner"]
    E -->|Có| G["Xác định asset, zone,<br/>đường đi, tác động"]
    F --> G
    G --> H{"Có chỉ báo an ninh<br/>hoặc vi phạm policy?"}
    H -->|Có hoặc nghi vấn cao| I["Escalate SOC/IR<br/>và chuẩn bị evidence"]
    H -->|Chủ yếu lỗi vận hành| J["Escalate NOC/Network owner<br/>theo runbook"]
    I --> K["Chỉ thực hiện containment<br/>khi được phê duyệt"]
    J --> K
    K --> L["Kiểm tra dịch vụ + telemetry<br/>ghi SITREP và bàn giao"]
~~~

Đây là mô hình **quy trình gợi ý**; trong sự cố nghiêm trọng, operator cần thông báo theo quy trình khẩn cấp ngay khi có tín hiệu đủ ưu tiên, không nhất thiết đợi hoàn thành mọi bước thu thập.

### 6.1. Bước 1 — Ghi nhận đúng sự kiện

Ghi:

- Incident/ticket ID, nguồn alert, thời gian **event UTC** và thời gian nhận alert.
- Asset nguồn/đích (nếu biết), zone/VRF/VPN/site, rule ID và severity do hệ thống đề xuất.
- Chỉ số quan sát được, baseline trước đó và tác động nghiệp vụ thực tế.
- Sensor và các log cần bảo toàn trước khi retention ngắn xóa đi.
- Thay đổi/maintenance đang thực hiện có liên quan không.

### 6.2. Bước 2 — Xác minh chất lượng nguồn

- Sensor có online và ingest log bình thường không?
- Có packet drop hoặc log sampling/aggregation không?
- Firewall đang ghi ALLOW/DENY đủ cho policy liên quan hay chỉ có threat log?
- Có sự chênh lệch giờ NTP, timezone hoặc độ trễ SIEM?
- IP nguồn có bị SNAT hoặc thuộc resolver/proxy/NAT gateway?
- Endpoint đang VPN hoặc Wi-Fi roaming dẫn tới thay IP/VLAN trong khoảng đó?

Nếu câu trả lời chưa rõ, ghi **giới hạn quan sát** trong ticket. “Không tìm thấy log” không có nghĩa sự kiện không xảy ra.

### 6.3. Bước 3 — Xác định asset theo thời điểm

Đối chiếu DHCP lease lịch sử, NAC, VPN session, NAT mapping, Wi-Fi controller, cloud instance ID và asset inventory. Không lấy IP hiện tại rồi mặc nhiên gán cho sự kiện ba giờ trước.

Nếu firewall chỉ thấy IP proxy hoặc DNS resolver, truy về client qua log trung gian và session ID. Không cô lập một proxy/resolver chia sẻ cho toàn bộ người dùng chỉ vì thấy traffic khả nghi xuất hiện từ IP của nó.

### 6.4. Bước 4 — Đánh giá ưu tiên

Xem đồng thời:

1. **Impact:** mất dịch vụ, mất định tuyến, gián đoạn VPN/khách hàng.
2. **Exposure:** internet-facing, management plane, dữ liệu nhạy cảm, quyền admin.
3. **Confidence:** số nguồn độc lập, tính đầy đủ của telemetry, tín hiệu từ endpoint/identity.
4. **Scope:** một host, một VLAN, cả site, nhiều tài khoản hay cloud account.
5. **Ongoing activity:** đang tiếp diễn hoặc đã kết thúc; nguy cơ mất chứng cứ.

Một ví dụ phân loại **chỉ để học tập**:

| Độ ưu tiên | Biểu hiện | Hành động mặc định |
|---|---|---|
| Khẩn cấp | Đang mất dịch vụ trọng yếu, traffic flood lớn hoặc thay đổi quyền mạng trái phép làm lộ DATA/MGMT | Gọi bridge và thông báo SOC/IR/NOC ngay theo runbook; bảo toàn dấu vết song song |
| Cao | Nhiều tín hiệu nghi vấn cùng host, quản trị trái phép hoặc tài khoản nhạy cảm đăng nhập bất thường | Mở case ưu tiên cao, chỉ định người điều tra, duy trì cập nhật liên tục |
| Trung bình | Một nguồn phát hiện bất thường có tác động chưa rõ | Xác minh sensor, baseline, asset mapping và báo SOC khi đủ tiêu chí |
| Thấp | Sai lệch nhỏ, có change record rõ và không ảnh hưởng | Ghi ticket, xác nhận owner, xem xét tuning detector |

Mỗi tổ chức có thang **P0/P1/P2/P3** và SLA riêng; không áp bảng ví dụ thành quy định chung.

### 6.5. Bước 5 — Chỉ containment theo thẩm quyền

Biện pháp có thể gồm chặn destination cụ thể, chuyển host sang VLAN cách ly, thu hồi tài khoản, áp rate limit, bật upstream DDoS protection hoặc đổi firewall rule hẹp. Mỗi hành động cần xét:

- Tài sản nào bị ảnh hưởng và dependency nào có thể gián đoạn?
- Biện pháp có được phê duyệt và có thể rollback?
- Có làm mất nguồn log/telemetry hoặc phá điều tra không?
- Kiểm thử nào chứng minh biện pháp có hiệu lực mà ứng dụng hợp lệ vẫn chạy?

Đặc biệt tránh thay đổi routing/firewall trên production từ suy đoán đơn nguồn.

## 7. Bảng runbook dấu hiệu – kiểm tra – escalation

| Dấu hiệu | Kiểm tra đầu tiên của operator | Escalation thường gặp |
|---|---|---|
| Nhiều FW DENY tới SSH/MGMT | Rule ID, src IP/zone, số host, change log | SOC + Network Security |
| VPN thất bại hàng loạt | VPN/AAA/IdP health, IP/username phân bố, MFA | Identity team, SOC nếu pattern đáng ngờ |
| DNS NXDOMAIN/TXT bất thường | Resolver log, client, zone, QTYPE/RCODE, change record | DNS owner + SOC |
| Egress lặp tới đích hiếm | Flow, DNS/proxy, NAT mapping, asset/process | SOC/EDR team |
| Băng thông/pps quá tải | Interface errors/drops, VIP, source distribution, CDN/upstream | NOC lead, DDoS team, SOC |
| Route/prefix thay ngoài lịch | RIB/FIB, BGP peers, change calendar, link state | Network routing lead + SOC khi nghi hijack |
| Nhiều AP disconnect | Controller/RADIUS, RF, firmware, roaming, SSID | Wireless team; SOC nếu nghi rogue/deauth |
| Cloud SG/route mở rộng quyền | Cloud audit actor, ticket, effective policy, exposure | Cloud security/IAM + SOC |
| Syslog hoặc IDS ngừng gửi | Pipeline health, disk, route/NTP, collector status | Observability/NOC + SOC nếu cùng lúc có dấu hiệu lạm dụng |
| SSH từ USER tới DATA server | Identity, process nếu có, firewall rule, access request | SOC + App owner |
| Tài khoản admin thay policy trái lịch | AAA command audit, change ticket, config diff, signer | Incident Commander/SOC ngay theo quy định |

Bảng này là **điểm bắt đầu** cho runbook. Operator phải ưu tiên quy trình sự cố hiện hành của tổ chức khi có tình huống thực.

## 8. Log giả lập: điều tra một tình huống khó

### 8.1. Bối cảnh lab

Hệ thống giả lập có:

| Thành phần | Địa chỉ lab | Mục đích |
|---|---|---|
| Client-A ở USER | 10.44.10.25 | Máy nguồn nghi vấn |
| Recursive DNS | 10.44.0.53 | Resolver được quản lý |
| Firewall-LAB | L3 giữa USER và APP | Log flow và policy |
| App-LAB | 10.44.30.10 | Ứng dụng HTTPS |
| MGMT-LAB | 10.44.90.11 | SSH quản trị chỉ từ bastion |
| Bastion | 10.44.91.10 | Truy cập quản trị hợp lệ |
| SIEM | 10.44.60.10 | Thu log diễn tập |
| FQDN ví dụ | telemetry-lab.example | Chỉ dùng dữ liệu tài liệu |

**Cửa sổ điều tra:** 09:00–09:15 UTC, ngày 15-01-2026. Các bản ghi dưới đây là **dữ liệu tổng hợp**, không phải nhật ký hệ thống thật và không tạo kết nối đến Internet.

### 8.2. Bộ log mẫu

~~~text
2026-01-15T08:55:00Z DHCP lease asset=Client-A ip=10.44.10.25 vlan=USER
2026-01-15T09:00:04Z DNS client=10.44.10.25 qname=telemetry-lab.example qtype=A rcode=NOERROR
2026-01-15T09:00:06Z FW src=10.44.10.25 dst=10.44.30.10 proto=TCP dport=443 action=ALLOW rule=USER-APP
2026-01-15T09:01:02Z FW src=10.44.10.25 dst=10.44.90.11 proto=TCP dport=22 action=DENY rule=USER-NO-MGMT
2026-01-15T09:01:10Z FW src=10.44.10.25 dst=10.44.90.11 proto=TCP dport=22 action=DENY rule=USER-NO-MGMT
2026-01-15T09:02:10Z VPN user=operator-lab auth=FAIL source=198.51.100.44 reason=invalid_credentials
2026-01-15T09:02:14Z VPN user=operator-lab auth=FAIL source=198.51.100.44 reason=invalid_credentials
2026-01-15T09:03:06Z FW src=10.44.10.25 dst=10.44.30.10 proto=TCP dport=443 action=ALLOW rule=USER-APP
2026-01-15T09:04:00Z NDR alert=EX-OPS-012 src=10.44.10.25 reason=mgmt_probe_plus_rare_dns confidence=medium
2026-01-15T09:05:20Z SIEM ingestion_delay_sec=90 source=fw-lab
2026-01-15T09:06:11Z CHANGE ticket=CHG-012 component=Client-A job=monitoring-agent-upgrade approved=TRUE
2026-01-15T09:08:00Z EDR asset=Client-A process=monitor-agent status=review_required owner=platform-team
2026-01-15T09:09:05Z FW src=10.44.10.25 dst=10.44.90.11 proto=TCP dport=22 action=DENY rule=USER-NO-MGMT
2026-01-15T09:10:30Z NOC ticket=EX-OPS-012 status=TRIAGE
~~~

Dải **198.51.100.0/24** dành cho tài liệu; không đại diện IP tấn công thật. Hai lần VPN auth failure **chưa chứng minh password spraying**; chúng liên quan user operator-lab, nhưng chưa xác minh liên hệ với Client-A hoặc chính sách mạng.

### 8.3. Những nhận định phải tách bạch

| Ghi nhận | Loại | Giải thích |
|---|---|---|
| Client-A có ít nhất ba lần bị chặn SSH tới MGMT-LAB | Fact | Rule DENY xuất hiện với source và dest khớp |
| Có DNS query mới từ Client-A | Fact | Resolver ghi telemetry-lab.example tại 09:00 |
| NDR nghi chuỗi hành vi liên quan nhau | Hypothesis của detector | Alert confidence medium không chứng minh liên hệ nhân quả |
| Client-A đã bị điều khiển từ xa | Unknown | Chưa có chứng cứ về process/action hoặc endpoint compromise |
| Monitoring-agent upgrade có thể giải thích traffic HTTPS | Hypothesis | Cần đối chiếu process và đích thật |
| Hai lần VPN failure là password spraying | Chưa đủ cơ sở | Thiếu số lượng tài khoản, nguồn và baseline |
| Log firewall bị trễ nhận 90 giây | Fact | Cần phân biệt event/ingest time để dựng timeline |

### 8.4. Quy trình xử lý khuyến nghị

1. Mở ticket **EX-OPS-012**, ghi rõ đây là dữ liệu lab/diễn tập.
2. Xác nhận mapping 10.44.10.25 → Client-A theo lease tại 09:00, tránh dùng trạng thái hiện tại.
3. Kiểm tra lịch sử firewall DENY tới management và xác nhận không có phiên ALLOW liên quan ở các đường khác trong phạm vi quan sát.
4. Đối chiếu thay đổi monitoring-agent, DNS query, flow HTTPS và process lineage của Client-A.
5. Kiểm tra VPN failure như một nhánh độc lập cho đến khi có chứng cứ liên hệ.
6. Thông báo SOC khi có nhiều dấu hiệu phối hợp; không tuyên bố đã có C2 hay brute force khi chưa đủ dữ liệu.
7. Không chặn Client-A hoặc toàn VLAN nếu chưa có thẩm quyền/đánh giá tác động.
8. Lưu log/capture cần thiết, ghi kết quả và bàn giao owner kiểm chứng.

## 9. Cách đọc thời gian, nguồn, NAT và độ tin cậy

### 9.1. Event time, ingest time và analyst time

Giả sử firewall ghi sự kiện lúc 09:00:06 UTC nhưng SIEM chỉ nhận lúc 09:01:36 UTC; người vận hành mở ticket lúc 09:03:00 UTC. Đây là ba mốc khác nhau:

- **Event time:** 09:00:06 UTC.
- **Ingest time:** 09:01:36 UTC.
- **Operator observation time:** 09:03:00 UTC.

Khi so log giữa DNS, firewall và EDR, ghép theo event time, bù clock skew đã đo. Không tự sửa timestamp trong chứng cứ gốc. Khi tính time-to-detect, phải ghi rõ lấy điểm bắt đầu/kết thúc nào.

### 9.2. Tại sao NAT/VRF/VPN làm nhầm nguồn?

Nhiều client có thể qua một source NAT; firewall Internet chỉ thấy gateway, còn proxy thấy user identity. Trên VPN, IP pool dùng lại; tại Wi-Fi, roaming và dynamic VLAN thay đổi mapping. Trong cloud, workload có instance ID nhưng flow log qua NAT gateway có thể mất IP ban đầu ở một điểm quan sát.

**Luôn ghi vị trí sensor và loại tuple:** pre-NAT, post-NAT, interface ingress/egress, security zone và session ID nếu có. Một subnet có route vào management không chứng minh packet đã vào được; cần kiểm tra rule và đường đi thực tế.

### 9.3. Đánh giá độ tin cậy theo chất lượng chứng cứ

Có thể mô tả:

- **Cao:** nhiều nguồn độc lập xác nhận sự kiện, asset mapping và thời gian chính xác; có log cả hai phía đường truyền.
- **Trung bình:** một số nguồn khớp nhưng thiếu endpoint/response hoặc log sampling.
- **Thấp:** chỉ một alert không rõ rule match, IP nguồn chung hoặc dữ liệu bị trễ/thiếu.

Đây là mô tả định tính phục vụ học tập, không thay thế thang confidence chính thức của SOC.

## 10. Lệnh đọc tình trạng và chứng cứ an toàn

Các ví dụ dưới đây dành cho **máy lab hoặc hệ thống do operator được phép quản trị**. Chỉ thu thông tin thụ động hoặc phân tích file log/PCAP có sẵn; không tạo traffic dò quét hay truy cập đích ngoài scope.

### 10.1. Kiểm tra kết nối và tuyến trên Linux

~~~bash
ip -br address
ip route
ip route get 10.44.30.10
ip -s link show
ss -tuan
~~~

Ý nghĩa:

- **ip -br address:** xem địa chỉ và trạng thái interface.
- **ip route/ip route get:** kiểm tra tuyến cục bộ đến địa chỉ lab.
- **ip -s link show:** xem thống kê link; giá trị drops/errors cần đặt trong bối cảnh thời gian và tốc độ.
- **ss -tuan:** xem socket/transport trên chính host; không phải bằng chứng firewall đã cho phép toàn bộ luồng.

Đối với thiết bị hãng khác, dùng lệnh **show/display** chỉ đọc phù hợp; không sao chép lệnh cấu hình giữa các vendor.

### 10.2. Trên Windows PowerShell

~~~powershell
Get-NetIPAddress
Get-NetRoute -AddressFamily IPv4
Get-NetAdapterStatistics
Get-NetTCPConnection
~~~

Dữ liệu ở endpoint chỉ phản ánh trạng thái của máy đó tại thời điểm chạy; muốn ghép với sự kiện trong quá khứ cần log lưu trữ.

### 10.3. Đọc PCAP đã được cấp quyền

~~~bash
sha256sum /path/to/ops-012.pcapng
capinfos /path/to/ops-012.pcapng
tshark -r /path/to/ops-012.pcapng -q -z conv,tcp
~~~

Lọc gói DNS không mã hóa (nếu PCAP có và được phép phân tích):

~~~bash
tshark -r /path/to/ops-012.pcapng \
  -Y 'dns.flags.response == 0' \
  -T fields -E header=y \
  -e frame.time_epoch -e ip.src -e ip.dst \
  -e dns.qry.name -e dns.qry.type
~~~

Lọc các kết nối TCP liên quan một host lab:

~~~bash
tshark -r /path/to/ops-012.pcapng \
  -Y 'ip.addr == 10.44.10.25 && tcp' \
  -T fields -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.flags.syn -e tcp.flags.reset
~~~

PCAP chỉ phản ánh **những gói được capture tại điểm thu**. Không thấy DNS query có thể do caching, DNS mã hóa hoặc vị trí capture; không thấy response có thể do packet loss hoặc đường về khác. Hash SHA-256 giúp đối chiếu tính toàn vẹn của file kể từ lúc tính, không chứng minh file đã ghi đủ lưu lượng.

### 10.4. Truy vấn log theo schema giả định

Ví dụ SQL bên dưới giả định bảng **firewall_events** với các field được chuẩn hóa. Đó là **pseudodataset**; khi dùng SIEM thực phải đối chiếu field, kiểu thời gian, NAT và tên rule.

~~~sql
SELECT
  src_ip,
  dst_ip,
  dst_port,
  action,
  COUNT(*) AS event_count,
  MIN(event_time_utc) AS first_seen,
  MAX(event_time_utc) AS last_seen
FROM firewall_events
WHERE event_time_utc >= TIMESTAMPTZ '2026-01-15 09:00:00+00'
  AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:15:00+00'
  AND src_ip = '10.44.10.25'
GROUP BY src_ip, dst_ip, dst_port, action
ORDER BY event_count DESC;
~~~

Một truy vấn thống kê khác, vẫn là schema giả định, để tìm lỗi VPN nhiều tài khoản:

~~~sql
SELECT
  source_ip,
  COUNT(*) AS failed_logins,
  COUNT(DISTINCT username) AS distinct_usernames,
  MIN(event_time_utc) AS first_seen,
  MAX(event_time_utc) AS last_seen
FROM vpn_auth_events
WHERE event_time_utc >= TIMESTAMPTZ '2026-01-15 09:00:00+00'
  AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:15:00+00'
  AND result = 'FAIL'
GROUP BY source_ip
ORDER BY failed_logins DESC;
~~~

Kết quả đếm không đủ để chứng minh mục đích tấn công. IP nguồn có thể thuộc NAT, và field username là dữ liệu nhạy cảm cần masking khi chia sẻ.

## 11. Bảo toàn chứng cứ, nhật ký và chuỗi bàn giao

### 11.1. Evidence manifest cơ bản

| Thuộc tính | Ví dụ diễn tập |
|---|---|
| Case ID | EX-OPS-012 |
| Evidence ID | EX-OPS-012-FW-01 |
| Hệ thống nguồn | Firewall-LAB |
| Kiểu dữ liệu | Traffic log export |
| Event window | 2026-01-15 09:00–09:15 UTC |
| Thời gian thu | UTC của lần export |
| Operator | Người thu theo phân quyền |
| Query/filter | src=10.44.10.25, window 15 phút |
| Định dạng và kích thước | JSON/CSV/PCAP; kích thước thực |
| SHA-256 | Giá trị tính từ file thu, không dùng hash minh họa |
| Nơi lưu và truy cập | Kho chứng cứ có audit, retention |
| Chain of custody | Người bàn giao/tiếp nhận, mục đích, thời điểm |

Không chỉnh sửa raw logs để chúng “phù hợp giả thuyết”. Khi cần lọc hoặc ẩn dữ liệu cá nhân, giữ bản gốc phân quyền chặt và ghi cách tạo bản dẫn xuất. Không copy credential, token, QNAME chứa định danh hoặc tài liệu nhạy cảm vào kênh chat không được phép.

### 11.2. Bằng chứng nào cần có trước khi yêu cầu chặn?

Thông thường nên cung cấp:

- Asset/identity và IP theo đúng sự kiện.
- Destination, protocol/port, security zone, route hoặc NAT mapping.
- Thời điểm bắt đầu/diễn tiến, số lượng/tần suất, policy action đã ghi.
- Những nguồn khác xác nhận hoặc bác bỏ.
- Đánh giá ảnh hưởng nghiệp vụ nếu block; chủ ứng dụng và owner mạng.
- Phạm vi chặn tối thiểu, change/incident approval và rollback.
- Test chứng minh chặn thành công mà các ứng dụng hợp lệ vẫn hoạt động.

Trong sự cố khẩn cấp, quy trình có thể cho phép hành động sớm hơn với mức bằng chứng tối thiểu. Operator cần tuân thủ đúng quyền được giao và ghi lại quyết định.

## 12. Giao tiếp khi chuyển ca và escalations

### 12.1. Mẫu ticket ngắn

~~~text
[EXERCISE] CASE: EX-OPS-012
Time window: 2026-01-15 09:00-09:15 UTC
Priority: Đang phân loại theo runbook
Source: Firewall + DNS + NDR + DHCP
Asset: Client-A / 10.44.10.25 tại thời điểm sự kiện

FACTS:
- Firewall ghi ba lượt DENY TCP/22 từ USER tới MGMT.
- DNS ghi một truy vấn telemetry-lab.example từ Client-A.
- NDR phát cảnh báo confidence=medium; SIEM ingest trễ 90 giây.

HYPOTHESES:
- Có thể là cấu hình/agent kiểm tra sai đích quản trị.
- Cũng có thể là hoạt động trái phép, cần đối chiếu endpoint.

UNKNOWN:
- Process nào tạo kết nối TCP/22, chủ ứng dụng có phê duyệt không?
- Các đường IPv6/VPN/proxy khác có cùng hành vi không?

IMPACT:
- Chưa xác nhận mất dịch vụ hoặc đăng nhập quản trị thành công.

ACTIONS:
- Thu firewall/DNS/EDR logs và hỏi platform owner về CHG-012.
- Escalate SOC để phân loại nếu dấu hiệu tiếp tục hoặc có bằng chứng mới.

OWNER / NEXT UPDATE:
- NOC on-call + SOC triage owner / 09:30 UTC
~~~

Mẫu không yêu cầu ghi toàn bộ raw log trong ticket; sử dụng evidence ID và link nội bộ có quyền hạn phù hợp.

### 12.2. Mẫu SITREP cho người điều phối

Một SITREP tốt trả lời trong vài câu: **Sự kiện gì? Ảnh hưởng đến ai? Điều gì đã được xác nhận? Những gì còn chưa rõ? Đang làm gì và cập nhật tiếp khi nào?**

Ví dụ:

> [EXERCISE] 09:20 UTC: Firewall đã chặn ba lượt kết nối SSH từ một máy USER tới mạng quản trị; chưa thấy bằng chứng đăng nhập thành công. NDR có cảnh báo bổ sung nhưng chưa đủ chứng cứ xác định nguyên nhân. NOC đang đối chiếu change record và endpoint log, SOC hỗ trợ phân loại; không có thay đổi firewall ngoài quy trình. Cập nhật tiếp lúc 09:30 UTC.

### 12.3. Bàn giao ca

Checklist bàn giao gồm:

- Ticket còn mở, độ ưu tiên, owner và quyết định đã phê duyệt.
- Time window và thời điểm cuối cùng nhận dữ liệu.
- Log/capture đã thu, nơi lưu, hạn retention và những nguồn đang thiếu.
- Tình trạng dịch vụ, workaround/containment đang hoạt động.
- Kết quả thử xác nhận và các điều kiện có thể kích hoạt rollback.
- Mốc cập nhật tiếp theo, kênh liên hệ SOC/IR/network/app owner.
- Các giả thuyết đã bị bác bỏ, tránh ca sau điều tra lại từ đầu.

## 13. Đào tạo theo năng lực, không chỉ ghi nhớ IOC

### 13.1. Ba mức thành thạo

| Mức | Năng lực | Bài đánh giá |
|---|---|---|
| **Cơ bản (L1)** | Đọc dashboard, nhận diện alert, xác định thời gian và asset, tra runbook | Triage một alert đơn giản và mở ticket đủ dữ liệu |
| **Vận hành (L2)** | Ghép firewall/DNS/VPN/route logs, phân biệt false positive, biết khi nào escalate | Phân tích một tình huống đa nguồn với ít nhất một điểm mù |
| **Nâng cao (L3)** | Điều phối sự cố liên vùng, đánh giá containment/HA/rollback và cải tiến detection | Tabletop có cloud/VPN/IPv6 và một thay đổi policy được kiểm chứng |

Không khuyến khích đào tạo operator bằng cách bắt học thuộc một danh sách “IP xấu” cố định. IP/domain thay đổi và bị tái sử dụng; năng lực cốt lõi là biết **quan sát, xác minh, phản biện giả thuyết và giao tiếp**.

### 13.2. Phương pháp dạy hiệu quả

1. **Giải thích (15 phút):** đọc một bộ log và nhận diện fact/hypothesis/unknown.
2. **Thị phạm (15 phút):** người hướng dẫn cùng nhóm tra firewall rule, DHCP mapping và log pipeline.
3. **Thực hành (25 phút):** operator tự xử lý 2–3 ca với dữ liệu giả lập.
4. **Inject bất ngờ (15 phút):** thêm một change record hoặc sensor delay để kiểm tra khả năng đổi giả thuyết.
5. **Bàn giao (10 phút):** viết ticket/SITREP, nêu escalation và việc không được tự thực hiện.
6. **Debrief (10 phút):** giải thích tại sao một case bị kết luận sai, cập nhật runbook.

Thời lượng chỉ là gợi ý cho **buổi đào tạo 90 phút**, không phải tiêu chuẩn bắt buộc.

## 14. Diễn tập tabletop 90 phút cho NOC/SOC

### 14.1. Điều kiện trước khi diễn tập

- Có người điều phối, evaluator, NOC lead, SOC triage, network owner và một người đóng vai application owner.
- Dữ liệu được dán nhãn **[EXERCISE]**, không trộn vào trang sự cố production mà không phân biệt.
- Chỉ dùng log giả lập/replay hoặc sensor lab được phép; không cần gây tấn công thật.
- Có stop condition, contact path xử lý sự cố thật và bộ đáp án riêng của controller.
- Chọn các tình huống có **ít nhất một lời giải thích hợp lệ** để kiểm tra khả năng tránh false positive.

### 14.2. Timeline inject

| Mốc | Inject | Kỹ năng cần thể hiện |
|---|---|---|
| T+00 | Briefing môi trường, ROE và dashboard | Nhận vai trò, kiểm tra nguồn quan sát |
| T+10 | Firewall DENY SSH từ USER tới MGMT | Xác nhận rule/asset, mở ticket |
| T+20 | DNS query đến zone mới và NDR alert medium | Tương quan nhưng không khẳng định C2 |
| T+30 | Hai VPN failure xuất hiện từ IP tài liệu | Giữ nhánh identity độc lập khi chưa có mối liên hệ |
| T+40 | Controller đưa change record nâng cấp agent hợp lệ | Cập nhật giả thuyết, hỏi owner |
| T+50 | SIEM ingest trễ 90 giây | Tách event/ingest time, giữ timeline chuẩn |
| T+60 | Có người đề nghị chặn toàn USER VLAN | Đánh giá tác động, quyền phê duyệt và lựa chọn hẹp |
| T+70 | SOC yêu cầu SITREP và evidence manifest | Viết rõ fact, unknown, next action |
| T+80 | Controller thông báo EDR xác nhận agent hợp lệ nhưng SSH là task sai cấu hình | Điều chỉnh kết luận, chọn owner vận hành |
| T+90 | Kết thúc, AAR và chấm điểm | Nêu cải tiến cụ thể và cách kiểm tra lại |

Tình huống kết thúc **có thể là lỗi cấu hình chứ không phải tấn công**. Đây là kết quả hợp lệ của một cuộc điều tra nếu được chứng minh bằng dữ liệu.

### 14.3. Nhánh mở rộng

**Nhánh A — DDoS thật sự ảnh hưởng dịch vụ:** cùng lúc có pps tăng, drops, lỗi HTTP và upstream alert. Đội cần ưu tiên an toàn dịch vụ và gọi escalation DDoS thay vì chờ điều tra nguồn DNS.

**Nhánh B — Proxy che nguồn:** log chỉ thấy proxy IP ở firewall, còn proxy log có user/device. Đội không được gán proxy là host compromise.

**Nhánh C — IPv6 bypass:** IPv4 USER → MGMT bị DENY, IPv6 có connection thành công. Đội báo nguy cơ policy không đồng nhất, chuẩn bị negative test và chuyển network security để xử lý.

**Nhánh D — Cloud rule change:** security group mở SSH rộng ngoài change window, nhưng flow log chưa thấy kết nối. Đội vẫn cần đánh giá **exposure** dù chưa có bằng chứng khai thác.

## 15. Rubric chấm kỹ năng operator

| Tiêu chí | Điểm tối đa | Bằng chứng đạt |
|---|---:|---|
| Nhận diện và mô tả tín hiệu | 15 | Nêu alert source, tài sản, thời gian, đặc tính traffic |
| Chất lượng triage và log | 20 | Sensor health, baseline, NAT/DHCP, event vs ingest time |
| Phân biệt fact/hypothesis/false positive | 20 | Có lập luận, không khẳng định quá mức |
| Mức ưu tiên và escalation | 15 | Chọn đúng owner, kịp thời, không vượt thẩm quyền |
| Ứng phó an toàn | 10 | Cân nhắc impact, phê duyệt, rollback và kiểm thử |
| Evidence/ticket/SITREP | 10 | Lưu đủ provenance và ghi rõ unknown |
| Bàn giao và AAR | 10 | Owner, next update, action tracker, retest |
| **Tổng** | **100** | Đánh giá qua bằng chứng và quyết định, không chỉ số cảnh báo đã thấy |

Đối với bài kiểm tra đầu vào L1, có thể đặt mức đạt theo tiêu chí của tổ chức. Một operator **không** nên được đánh giá đạt chỉ vì tổng điểm cao khi đã thực hiện một hành động nguy hiểm ngoài ROE hoặc bỏ qua escalation khẩn cấp.

## 16. Các bài tập phân tích nhanh

### Bài tập 1 — Nhiều login VPN thất bại

NOC thấy 100 lần VPN auth FAIL trong 5 phút. SOC muốn biết đây là password spraying hay lỗi xác thực tập trung. Operator nên thu những trường nào?

**Gợi ý:** source IP, username duy nhất, kết quả MFA, event time, IdP health, lỗi AAA/certificate, VPN pool và change record. Đếm 100 lượt thất bại **không đủ** để phân loại.

### Bài tập 2 — Kết nối định kỳ

Một máy người dùng gọi HTTPS tới domain mới mỗi hai phút. DNS log và flow log khớp; chưa có EDR telemetry. Có thể tuyên bố đã phát hiện C2 không?

**Gợi ý:** chưa. Đây là tín hiệu ưu tiên điều tra. Cần process/owner, baseline, lịch update, payload/log ứng dụng có quyền và đường qua proxy. Nếu thiếu EDR, ghi rõ điểm mù.

### Bài tập 3 — Firewall không có log

IDS/NDR thấy kết nối USER → DATA, nhưng firewall segmentation không có log. Những cách giải thích hợp lý nào cần kiểm tra?

**Gợi ý:** route bypass, nằm cùng subnet, log policy tắt, sensor gián đoạn, lọc sai timestamp, NAT/proxy hoặc khác điểm capture. Không tự kết luận firewall hỏng.

### Bài tập 4 — DDoS hay flash crowd?

Link Internet nhận traffic gấp năm lần baseline; web server HTTP 200 vẫn ổn, số lỗi thấp và có lịch phát livestream. Đội nên thông báo thế nào?

**Gợi ý:** báo spike và nguy cơ capacity, đối chiếu campaign, CDN, pps, drops và latency; chưa đủ chứng cứ để gọi là DDoS. Tăng cảnh giác và chuẩn bị capacity playbook.

### Bài tập 5 — Cloud SSH mở ngoài dự kiến

Một IaC change mở TCP/22 từ Internet vào VM quản trị; hiện chưa thấy accepted flow. Đội có nên bỏ qua không?

**Gợi ý:** không. Exposure có thể quan trọng ngay cả khi chưa có flow; cần xác minh effective policy, owner, change approval, asset criticality và đề xuất thu hẹp theo quy trình.

### Bài tập 6 — Sai lệch do đồng hồ

Firewall ghi 09:00:03 UTC, SIEM hiển thị 09:02:10 UTC, NDR ghi 09:00:08 UTC. Làm sao dựng timeline?

**Gợi ý:** tách event/ingest time, kiểm tra NTP/clock offset, ghi độ tin cậy và dữ liệu cần xác minh; không sắp thứ tự chỉ theo thời điểm SIEM nhận.

### Bài tập 7 — Nhận diện nhầm đích

Một thiết bị Wi-Fi guest có nhiều DNS NXDOMAIN và mất kết nối liên tục. Đây có chắc là DNS tunneling không?

**Gợi ý:** chưa. Cần phân biệt lỗi captive portal, roaming, RADIUS, DNS cấu hình, app retry và dữ liệu DNS query thực. Kiểm tra controller, DHCP/NAC, resolver, client và thay đổi gần đây.

## 17. Kỹ năng ghi nhận và phối hợp sự cố

### 17.1. Quy tắc phát ngôn an toàn

Ưu tiên câu: **“Firewall ghi nhận ba kết nối TCP/22 bị chặn từ một địa chỉ trong USER VLAN tới MGMT subnet trong 9 phút; chưa xác định được tiến trình sinh traffic.”**

Tránh câu: **“Máy này đã bị hacker điều khiển và đang tấn công mạng quản trị”** khi chưa có endpoint evidence.

Thông báo tốt có: sự kiện, thời gian, nguồn, tác động, độ tin cậy, thiếu sót và bước tiếp theo. Không sử dụng ngôn từ khẳng định thái quá hoặc ám chỉ một cá nhân cụ thể khi chỉ có địa chỉ IP dùng chung.

### 17.2. Khi có bằng chứng rò rỉ hoặc lạm dụng thực sự

Nếu có dữ liệu từ endpoint, audit, proxy hoặc ứng dụng chỉ ra khả năng truy cập trái phép dữ liệu nhạy cảm, operator nên:

- Tăng mức ưu tiên theo tiêu chí của tổ chức, bảo toàn bằng chứng.
- Báo SOC/IR và chủ dữ liệu, giữ kín thông tin theo phân loại dữ liệu.
- Tránh mở file nhạy cảm hoặc gửi bản sao qua kênh không có quyền.
- Chỉ thực hiện containment theo playbook được phê duyệt.
- Ghi ai, khi nào, điều gì đã xác nhận và những vùng chưa biết.

Operator không tự quyết định nghĩa vụ thông báo pháp lý hoặc truyền thông; việc đó thuộc trách nhiệm có thẩm quyền.

## 18. Chỉ số đo chất lượng đào tạo và vận hành

### 18.1. KPI hỗ trợ phát triển

| KPI | Định nghĩa gợi ý | Điều cần tránh |
|---|---|---|
| Tỷ lệ triage đúng | Số tình huống được phân loại đúng / tổng tình huống gán nhãn | Chấm theo đáp án thiếu bối cảnh |
| Thời gian nhận alert | Alert created → operator acknowledged | Đổ lỗi operator vì SIEM ingest trễ |
| Thời gian escalation | Từ mốc đủ tiêu chí đến lúc chuyển đúng team | Chỉ tối ưu thời gian mà bỏ chất lượng |
| Tỷ lệ ticket đủ dữ liệu | Ticket có asset, time, fact, unknown, evidence | Điền trường cho có nhưng không xác thực |
| False-positive handling | Tỷ lệ giải thích hợp lệ có bằng chứng | Ép operator đóng mọi alert thành benign |
| Coverage diễn tập | Các loại DNS/VPN/firewall/Wi-Fi/cloud/route được thực hành | Chỉ lặp một tình huống giống nhau |
| Tuân thủ ROE | Thực hiện đúng quyền và điều kiện dừng | Chấm cao cho thao tác nguy hiểm ngoài phạm vi |
| Hành động cải tiến đã retest | Action tracker được xác minh đã khắc phục | Đóng task khi chưa có bằng chứng |

Mỗi chỉ số phải có định nghĩa timestamp và nguồn dữ liệu. **MTTD/MTTR** ở cấp tổ chức là kết quả của nhiều quy trình/hệ thống, không nên quy hết trách nhiệm cho một người trực.

### 18.2. Lộ trình đào tạo liên tục

- **Hằng tuần:** 15–20 phút review một case từ log đã ẩn danh, cập nhật false positives.
- **Hằng tháng:** tabletop đa nguồn; luân phiên DNS, firewall/VPN, Wi-Fi, cloud và routing.
- **Sau thay đổi lớn:** test lại giám sát và đường escalation tương ứng với kiến trúc mới.
- **Sau sự cố thực:** cập nhật runbook, parser, ma trận quyền, mô hình severity và thực hành lại trên dữ liệu đã được phép dùng.
- **Định kỳ theo nội quy:** kiểm tra kỹ năng L1/L2/L3, chú trọng thực hành và an toàn hơn ghi nhớ IOC.

Các chu kỳ này chỉ mang tính gợi ý; nội dung và thời gian cụ thể theo khả năng vận hành và mức độ rủi ro của hệ thống.

## 19. Sai lầm thường gặp trong ca trực

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Coi mọi alert IDS là xâm nhập | Tăng false positive và phản ứng quá mức | Xem signature, flow, nguồn độc lập, baseline |
| Chỉ nhìn đường biểu diễn băng thông | Nhầm DDoS, spike hợp lệ và lỗi interface | Đọc pps, drops, latency, app status, upstream |
| Dùng IP hiện tại để gán sự kiện cũ | Điều tra sai asset | DHCP/NAT/VPN/NAC mapping theo thời điểm |
| Không phân biệt event và ingest time | Ghép sai diễn biến sự cố | NTP/UTC và log pipeline health |
| Không xem route, VRF, IPv6, proxy | Kết luận sai ranh giới firewall | Kiểm tra packet path thực, mọi đường phụ |
| Thấy HTTPS định kỳ và kết luận C2 | Báo sai agent hợp lệ | Process/owner, DNS/flow, change record |
| Thấy DNS dài và kết luận exfil | Không có chứng cứ payload | Kiểm tra zone, QTYPE, baseline, endpoint |
| Chặn cả subnet vì một host | Mất ứng dụng nghiệp vụ | Containment hẹp, phê duyệt, rollback |
| Clear log/counter để “xem cho sạch” | Mất chứng cứ điều tra | Lưu nguyên trạng, dùng cửa sổ lọc |
| Tắt IDS/IPS khi alert nhiều | Mất kiểm soát bảo mật | Tuning có change control, kiểm thử rule |
| Không kiểm tra sensor đang hoạt động | “Không alert” dù không thu log | Health telemetry, ingest lag, log volume |
| Không ghi những điều chưa biết | SOC không biết giới hạn chứng cứ | Fact/hypothesis/unknown/next checks |
| Không bàn giao ca có owner | Sự cố bị bỏ quên | Ticket, deadline, contact và next update |
| Dùng dữ liệu thật trong bài diễn tập | Lộ thông tin nhạy cảm | Log giả lập hoặc dữ liệu đã được phê duyệt/ẩn danh |

## 20. Checklist operator khi nhận dấu hiệu tấn công

- [ ] Xác minh đây là alert/sự kiện thật hay test/maintenance đã phê duyệt.
- [ ] Ghi ticket ID, event time UTC, ingest time, tên sensor và phạm vi.
- [ ] Xác định dấu hiệu ở lớp nào: DNS, VPN, IDS/IPS, firewall, route, Wi-Fi, cloud hoặc endpoint.
- [ ] Kiểm tra sensor/log pipeline có đang hoạt động đầy đủ và đồng bộ giờ.
- [ ] Xác định nguồn/đích, zone/VRF, VLAN/SSID, port và protocol.
- [ ] Đối chiếu DHCP/NAT/VPN/NAC/cloud identity theo đúng thời điểm.
- [ ] Tìm baseline, change record, service owner và lời giải thích hợp lệ.
- [ ] Tách fact, hypothesis, unknown và hành động cần xác minh.
- [ ] Kiểm tra mức độ ảnh hưởng đến dịch vụ và rủi ro DATA/MGMT.
- [ ] Escalate SOC/IR/NOC theo thẩm quyền và tiêu chí ưu tiên đã công bố.
- [ ] Chỉ thay đổi firewall/routing/NAC/EDR khi được phép và có rollback.
- [ ] Thu evidence ID, filter, timestamp, hash file và nơi lưu có kiểm soát.
- [ ] Ghi SITREP, owner, thời gian cập nhật tiếp theo và công việc chưa hoàn thành.
- [ ] Bàn giao ca rõ tình trạng service, các quyết định và những điểm mù.
- [ ] Sau diễn tập/sự cố, cập nhật runbook và kiểm thử lại cải tiến.

**Tổng kết:** đào tạo operator về dấu hiệu tấn công không nhằm biến mọi bất thường thành cảnh báo nguy cấp. Giá trị của đội vận hành nằm ở việc **nhìn thấy đúng tín hiệu, kiểm tra nguồn và bối cảnh, bảo vệ chứng cứ, giao tiếp chính xác và phối hợp phản ứng an toàn**. Khi có năng lực đó, các lớp phòng vệ từ phân đoạn, firewall, VPN, DNS, Wi-Fi đến cloud mới được vận hành như một hệ thống phòng thủ có thể quan sát, xác minh và cải thiện liên tục.

