# Mô phỏng command and control

## 1. Mục tiêu của bài học

Trong chương **Red team và mô phỏng tấn công mạng**, mô phỏng **command and control (C2)** giúp tổ chức kiểm tra khả năng phát hiện và ứng phó khi một thiết bị có dấu hiệu liên lạc tới hạ tầng điều khiển bên ngoài. Đối với module **SECURITY_NETWORK_SECURITY**, bài thực hành liên kết các lớp phòng vệ: phân đoạn mạng, firewall và kiểm soát egress, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây, cloud, phân tích lưu lượng và giám sát xâm nhập.

**C2** là khả năng một tác nhân duy trì kênh liên lạc với hệ thống hoặc tài khoản đã bị kiểm soát để trao đổi tín hiệu, nhận chỉ thị hoặc gửi trạng thái. Trong hoạt động kiểm thử an ninh, mô phỏng C2 nhằm đánh giá xem đội phòng thủ có nhận ra và xử lý đúng các **dấu hiệu giống C2** hay không.

Bài học sử dụng các nguồn sau để thực hành an toàn:

- **Telemetry tổng hợp**: DNS query log, firewall/proxy log, NetFlow, sự kiện endpoint và PCAP được dựng cho lab.
- **Mock collector trong mạng cô lập**: chỉ ghi nhận yêu cầu sức khỏe hoặc mã sự kiện cố định, không truyền lệnh thực thi.
- **Inject do người điều phối phát**: mô phỏng phản hồi “tasking” và những tình huống thay đổi để người chơi ra quyết định.
- **Hệ thống kiểm soát phòng thủ**: policy firewall, DNS, SIEM, NDR/IDS/IPS và EDR trong phạm vi được phép.

Không cần xây dựng mã độc, cơ chế điều khiển máy từ xa, persistence, né phát hiện hoặc kênh gửi dữ liệu thật để kiểm tra các mục tiêu của bài này. Những hành vi có nguy cơ ảnh hưởng hệ thống sẽ được thay bằng bằng chứng mô phỏng và đánh dấu rõ ràng.

### 1.1. Kết quả học tập

Sau khi hoàn thành, người học có thể:

1. Phân biệt **C2**, beacon, tasking, staging, exfiltration và telemetry hợp lệ theo **bằng chứng quan sát được**.
2. Lập kế hoạch diễn tập với scope, rules of engagement (ROE), mục tiêu và quyền phê duyệt rõ ràng.
3. Thiết kế một kịch bản C2 giả lập có cấu trúc, timeline, các tình huống bất ngờ và đáp án đánh giá.
4. Phân tích các tín hiệu DNS, HTTP(S), TLS, flow metadata, firewall, proxy, VPN, NDR/IDS và EDR để nhận ra hành vi liên lạc bất thường.
5. Tính và giải thích các chỉ số như khoảng cách giữa các kết nối, số lần liên hệ, entropy thời gian, byte ra/vào và mức hiếm của đích, tránh các kết luận không có chứng cứ.
6. Xây dựng playbook triage, kiểm chứng, containment và đo độ trễ phát hiện/ứng phó.
7. Viết báo cáo purple-team với evidence ID, phát hiện, khoảng trống quan sát, đề xuất và cách kiểm tra lại.

## 2. Hiểu C2 qua góc nhìn phòng thủ mạng

Một phiên liên lạc đáng nghi có thể gồm nhiều giai đoạn, nhưng **không phải mọi phiên tới Internet đều là C2**.

| Khái niệm | Ý nghĩa | Dữ liệu mà đội phòng thủ có thể thấy |
|---|---|---|
| Initial contact | Thiết bị liên lạc lần đầu tới một đích | DNS first-seen, TCP/UDP session, process network event |
| Beacon/check-in | Thiết bị gửi tín hiệu nhỏ định kỳ hoặc theo sự kiện | Chuỗi thời điểm kết nối, kích thước gói/flow, DNS/HTTP log |
| Tasking | Bên điều khiển trả một chỉ thị hoặc dữ liệu cho thiết bị | Phản hồi proxy/app nếu có quyền quan sát; trong lab dùng inject |
| Status/result | Thiết bị báo trạng thái sau khi nhận chỉ thị | Flow hoặc telemetry sau phản hồi; trong lab chỉ gửi marker vô hại |
| Reconnect/failover | Thiết bị thử liên hệ lại sau lỗi hoặc chuyển đích | Nhiều kết nối mới, DNS resolution, lỗi TLS/timeout |
| Exfiltration | Dữ liệu bị đưa ra ngoài phạm vi được phép | Cần chứng cứ nội dung và nguồn dữ liệu; bytes_out đơn lẻ chưa đủ |

Từ góc độ mạng, đội phòng thủ thường quan sát được **metadata** tốt hơn nội dung. Với HTTPS/DoH/DoT, tên miền, URL, payload hoặc header có thể không nhìn thấy tại sensor tùy vị trí capture và phương án mã hóa. Một kết nối TLS nhỏ lặp lại không tự chứng minh có lệnh điều khiển.

### 2.1. C2 liên quan gì tới những lớp phòng vệ của module?

- **Phân đoạn và NAC:** một thiết bị thuộc USER, IoT hoặc GUEST có quyền đi tới đâu, tài sản đó có đang ở đúng VLAN/SSID không?
- **Firewall egress:** host có được kết nối trực tiếp tới Internet hay bắt buộc qua proxy/resolver được quản lý?
- **DNS:** thiết bị hỏi zone nào, ở resolver nào, có sử dụng DNS trực tiếp ngoài chính sách không?
- **IDS/IPS/NDR:** hệ thống có nhận ra tương quan giữa chuỗi phiên, hành vi tên miền và dấu hiệu endpoint không?
- **VPN:** người hoặc thiết bị đang kết nối từ xa sử dụng pool, route, policy và danh tính nào?
- **Cloud:** workload đi qua NAT gateway, VPC/VNet firewall, security group hoặc private endpoint nào?
- **Endpoint:** tiến trình, người dùng, tác vụ nền và danh sách dịch vụ hợp lệ có giải thích được kết nối không?
- **Identity/AAA:** tài khoản nào có quyền thay đổi policy, tạo ngoại lệ và truy cập nhật ký điều tra?

Kiểm tra C2 có giá trị khi đo được **tác dụng phối hợp của các lớp**, thay vì chỉ bật một signature IDS rồi kết luận “đã phát hiện”.

## 3. Phân biệt các mô hình liên lạc và false positive

### 3.1. Những mẫu hành vi cần hiểu

**Beacon có chu kỳ:** khoảng cách giữa các lần kết nối tương đối đều. Hệ thống cập nhật phần mềm, health check, tác vụ đồng bộ và monitoring cũng có đặc điểm này.

**Beacon theo sự kiện:** máy kết nối khi đăng nhập, thay đổi mạng hoặc xảy ra một sự kiện. Không thể chỉ dùng bộ phát hiện tính chu kỳ để bao phủ tất cả trường hợp.

**Tín hiệu tương đối ngắn và nhỏ:** thường được quan sát như request/response nhỏ, nhưng các ứng dụng hợp lệ cũng tạo heartbeat; một số phiên C2 có thể mang nhiều byte hơn.

**Thay đổi DNS hoặc đích:** nhiều địa chỉ/IP hoặc hostname trong một khoảng thời gian có thể xuất phát từ CDN, failover, dịch vụ đám mây hoặc kịch bản không được phép.

**Kênh qua proxy và TLS:** nhiều thiết bị đi qua cùng proxy khiến địa chỉ IP nguồn tại firewall chỉ là proxy. Muốn xác định endpoint cần log proxy hoặc metadata nhận dạng bổ sung.

### 3.2. Không đánh đồng beacon với C2

| Hiện tượng | Dấu hiệu giống C2 | Kiểm tra để loại trừ |
|---|---|---|
| Agent EDR/monitoring | Kết nối lặp định kỳ, kích thước nhỏ | Nhà cung cấp, destination allowlist, process signature, policy |
| Đồng bộ thời gian/NTP | Nhịp đều, lưu lượng ít | Protocol UDP/123, máy chủ thời gian được phê duyệt |
| Update agent | Kết nối theo lịch tới cloud | Lịch cập nhật, URL/domain, binary và asset owner |
| API polling | Yêu cầu HTTPS lặp tới một đích | Job scheduler, service account, runbook ứng dụng |
| DNS resolver retry | Cụm kết nối/truy vấn lặp | Resolver health, timeout, RCODE và retry logic |
| Điểm kiểm tra kết nối VPN | Heartbeat và reconnect khi roaming | VPN session, WLAN controller, tunnel event |
| C2 đáng nghi | Có thể dùng chính các mẫu trên | Cần thêm bằng chứng về process, mục đích và dữ liệu/nhật ký thực tế |

Mục đích diễn tập là nâng chất lượng **phân biệt thật–giả**. Không chấm điểm cao một đội chỉ vì chặn mọi phiên định kỳ, nếu điều đó phá vỡ dịch vụ đang vận hành.

## 4. Rules of engagement (ROE) và ranh giới mô phỏng

Một bài red-team/purple-team an toàn cần có hồ sơ phân quyền trước khi chạy.

| Thành phần ROE | Yêu cầu minh họa |
|---|---|
| Mục tiêu | Kiểm chứng khả năng phát hiện tín hiệu giống C2, quy trình phân loại và ngăn chặn |
| Tài sản | Các VM, subnet, DNS zone và collector được chỉ định trong lab |
| Phương pháp | Replay telemetry, log tổng hợp, kết nối smoke test đơn lẻ tới mock collector nội bộ |
| Dữ liệu | Chỉ dùng token cố định, nhãn EXERCISE và dữ liệu giả lập; không sử dụng tài liệu thật |
| Thao tác cấm | Điều khiển máy từ xa, cài persistence, thu thông tin đăng nhập, phát payload độc hại, gửi dữ liệu thật |
| Bên liên quan | Exercise Controller, Red/Purple Lead, SOC, NOC, Endpoint Owner, Service Owner, Evaluator |
| Khung thời gian | Khởi động, từng inject, mốc kết thúc, thời gian debrief |
| Điều kiện dừng | Gây ảnh hưởng ngoài scope, phát hiện sự cố thật, sai tuyến/đích, mất kiểm soát test |
| Hoàn tác | Xóa rule test tạm đúng phạm vi, tắt mock collector, khôi phục snapshot và kiểm thử dịch vụ |

Mọi tài khoản, ticket, log marker và thông báo phải có tiền tố **[EXERCISE]**. Cần một lệnh dừng rõ ràng, ví dụ **EXERCISE STOP**, và kênh xử lý sự cố thật tách biệt với kênh diễn tập.

**Khuyến nghị phạm vi:** trước tiên chạy tabletop hoặc replay log; chỉ tạo traffic lab khi network team xác nhận nguồn, đích, đường đi và khả năng hoàn tác. Không phát tán traffic hoặc dùng đích Internet ngoài scope.

## 5. Lựa chọn cách mô phỏng C2

| Hình thức | Cách diễn tập | Kiểm chứng được | Không kiểm chứng được |
|---|---|---|---|
| Tabletop | Điều phối viên phát thẻ tình huống có log và phản hồi của đội | Vai trò, quyết định, phân loại, giao tiếp, escalation | Đường packet thực tế hoặc sensor detection thật |
| Telemetry replay | Nạp log/PCAP tổng hợp vào lab SIEM/NDR hoặc xử lý offline | Parser, correlation rule, analyst workflow | Tác dụng của firewall trên kết nối live |
| Mock network contact | Client lab thực hiện một kết nối kiểm thử vô hại tới collector nội bộ | Route, NAT, policy, log proxy/firewall và health check | C2 thực, task execution, persistence, exfiltration |
| Purple-team end-to-end | Kết hợp replay, test traffic có scope và inject | Kết nối detection → triage → containment → recovery | Khả năng bao phủ mọi kỹ thuật trong môi trường thật |

Không trộn lẫn nhãn kết quả giữa các hình thức. Ví dụ: khi SIEM nhận log replay và tạo alert, đó là **detector PASS với dữ liệu replay**, không đồng nghĩa firewall production đã ngăn chặn lưu lượng thật.

### 5.1. Mục đích của mock collector

Mock collector là một dịch vụ HTTP(S) nội bộ chỉ phản hồi nội dung tĩnh hoặc ghi log test ID. Nó **không cấp lệnh**, **không nhận nội dung file**, **không thực thi code**, **không quản lý agent**.

Trong mô phỏng tasking, controller có thể phát một inject:

> [EXERCISE] Collector trả về mã TASK-PLACEHOLDER-02; người chơi hãy xác định nguồn liên lạc, mức rủi ro và biện pháp khoanh vùng.

“Task” ở đây là **tình huống dành cho đội ứng phó**, không phải chỉ thị được gửi để máy trạm tự thi hành.

## 6. Kiến trúc lab cô lập

Địa chỉ trong ví dụ là địa chỉ private phục vụ tài liệu. Hostname có đuôi **.example** dành cho ví dụ và chỉ được ánh xạ trong DNS/hosts của lab. Không cần hoặc không được tìm tới một C2 service thật.

| Vùng/tài sản | Giá trị lab | Vai trò |
|---|---|---|
| USER-LAB | 10.77.10.0/24 | Mạng giả lập user |
| Client-LAB-25 | 10.77.10.25 | Thiết bị tạo kết nối lab hoặc nguồn của log replay |
| INTERNAL-DNS | 10.77.0.53 | Resolver của lab |
| MOCK-COLLECTOR | 10.77.50.20:8443 | Endpoint HTTP(S) tĩnh ghi test marker |
| Firewall-LAB | Gateway giữa USER-LAB và COLLECTOR | Egress policy và NAT/session log |
| ANALYTICS | 10.77.60.10 | SIEM/NDR/collector log cô lập |
| EDR-LAB | Agent/trích xuất log được giả lập | Tương quan process và network event |
| Domain lab | c2-exercise.lab.example | Hostname do DNS lab quản lý |

~~~mermaid
flowchart LR
    C["Client-LAB-25<br/>10.77.10.25"] --> SW["USER-LAB / switch"]
    SW --> FW["Firewall-LAB<br/>rule + session logs"]
    SW --> DNS["DNS lab<br/>10.77.0.53"]
    FW --> COL["Mock collector<br/>10.77.50.20:8443"]
    DNS -. "query log" .-> SOC["SOC / SIEM<br/>10.77.60.10"]
    FW -. "flow + policy log" .-> SOC
    C -. "endpoint log" .-> SOC
    COL -. "application test log" .-> SOC
~~~

Đây là lab có **đường kết nối cố định**; không có tuyến từ collector sang production hoặc mạng Internet thật. Firewall phải cho phép đúng luồng test (hoặc chặn có chủ đích theo inject), đồng thời chặn mọi đích ngoài scope.

### 6.1. Các luồng được kiểm tra

| Nguồn | Đích | Dịch vụ | Kỳ vọng |
|---|---|---|---|
| Client-LAB-25 | INTERNAL-DNS | UDP/TCP 53 | ALLOW |
| Client-LAB-25 | MOCK-COLLECTOR | TCP 8443 | ALLOW ở pha quan sát; DENY ở pha containment |
| Client-LAB-25 | Internet bất kỳ | TCP/UDP bất kỳ | DENY mặc định |
| Client-LAB-25 | MANAGEMENT/SIEM | SSH, HTTPS quản trị | DENY nếu không có ngoại lệ |
| Firewall/collector | ANALYTICS | Log/telemetry theo thiết kế | ALLOW đúng đích |
| Người điều phối | Collector admin | Interface quản trị lab | Chỉ theo đường admin được phê duyệt |

**Không tạo route mặc định ra Internet** chỉ để mô phỏng beacon. Nếu muốn kiểm thử egress qua proxy, dựng proxy trong lab và bổ sung vào sơ đồ/ma trận, không dùng proxy production.

## 7. Bài toán và chuỗi tình huống C2 giả lập

### 7.1. Bối cảnh

Từ 09:00 đến 09:15 UTC ngày **15-01-2026**, SOC nhận log cho thấy Client-LAB-25 liên hệ nhiều lần với c2-exercise.lab.example thông qua Firewall-LAB. Các phiên có kích thước nhỏ và có khoảng thời gian gần nhau. Một host khác trong lab vẫn hoạt động bình thường để làm nhóm đối chứng.

Mục tiêu không phải chứng minh máy có mã độc. Đội điều tra phải xác định:

- Địa chỉ và tài sản nào thực sự tạo kết nối?
- Các kết nối có phải tới mock collector đã cho phép hay xuất phát từ nguồn không được kiểm soát?
- Có dấu hiệu thời gian lặp, tên miền mới, TLS/proxy hoặc process bất thường nào?
- Hành động containment tối thiểu là gì? Nó có ảnh hưởng tới dịch vụ hợp lệ không?
- Giám sát có phát hiện và xác minh đúng trước và sau thay đổi policy không?

### 7.2. Dữ liệu tổng hợp cho người chơi

Mỗi bản ghi sau được **dựng cho bài tập**, có thể khác cấu trúc log của nhà cung cấp. Không phải log ghi nhận một phiên tấn công thật.

~~~text
2026-01-15T08:57:12Z DHCP client=10.77.10.25 asset=Client-LAB-25 vlan=USER-LAB
2026-01-15T09:00:02Z DNS client=10.77.10.25 resolver=10.77.0.53 query=c2-exercise.lab.example type=A answer=10.77.50.20
2026-01-15T09:00:04Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9001
2026-01-15T09:00:05Z PROXY client=10.77.10.25 host=c2-exercise.lab.example method=GET path=/health code=200 marker=EX-C2-006
2026-01-15T09:02:05Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9002
2026-01-15T09:02:06Z COLLECTOR client=10.77.10.25 marker=EX-C2-006 response=NOOP-LAB
2026-01-15T09:04:07Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9003
2026-01-15T09:06:04Z EDR asset=Client-LAB-25 process=lab-health-client binary_status=unreviewed correlation=review_required
2026-01-15T09:06:10Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9004
2026-01-15T09:08:12Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9005
2026-01-15T09:08:20Z NDR alert=EX-C2-006 src=10.77.10.25 reason=rare_dest_repeated_small_flows confidence=medium
2026-01-15T09:10:15Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=ALLOW rule=LAB-COLLECTOR session=9006
2026-01-15T09:12:17Z FW src=10.77.10.25 dst=10.77.50.20 dport=8443 proto=TCP action=DENY rule=LAB-C2-CONTAIN
2026-01-15T09:12:18Z COLLECTOR marker=EX-C2-006 new_request=NONE_AFTER_TEST_BLOCK
~~~

Các dòng ở thời điểm 09:12 chỉ minh họa hiệu lực chặn trong **pha containment giả lập**; không được tự tạo “bằng chứng firewall” nếu chưa thực hiện thử nghiệm tương ứng trong lab. Nếu là tabletop/replay, ghi nguồn là **controller inject**.

### 7.3. Timeline và giới hạn kết luận

| Mốc | Quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|---|
| 09:00 | DNS và phiên TCP 8443 tới collector | Client kết nối đích lab | Đây là C2 thực |
| 09:02–09:10 | Nhiều phiên nhỏ có khoảng cách gần hai phút | Có dạng liên lạc lặp lại đáng phân tích | Payload chứa lệnh hay exfiltration |
| 09:06 | Endpoint ghi process chưa được review | Cần xác minh owner và process lineage | Process độc hại |
| 09:08 | NDR tạo alert confidence medium | Detector đã bắt đầu cảnh báo | Kịch bản đã được điều tra đầy đủ |
| 09:12 | Firewall ghi DENY sau khi đổi rule | Một test flow đã bị deny | Mọi đường thay thế đều đã chặn |

Các thời điểm nhằm huấn luyện phân tích. Khoảng thời gian giữa các phiên nhỏ **không đồng nghĩa chính xác chu kỳ hai phút**; cần tính trên toàn bộ dữ liệu, xem sai lệch, session reuse và cách hệ thống tạo flow.

## 8. Chuẩn bị telemetry và khả năng quan sát

Trước buổi diễn tập, controller và evaluator cần xác nhận công cụ thật sự thu đủ trường.

| Nguồn | Trường hữu ích | Điểm mù |
|---|---|---|
| DNS resolver | Client, QNAME, QTYPE, RCODE, answer, timestamp | Nếu client tự dùng resolver ngoài hoặc DoH |
| Firewall policy | Ingress/egress zone, 5-tuple, rule ID, action, NAT, session | Có thể thiếu user/process và HTTP path |
| NetFlow/IPFIX | Duration, packets, bytes, directions, destination | Không nói lên nội dung mã hóa |
| Proxy/SWG | User/device, hostname, method, URL path nếu quan sát được, TLS policy | HTTPS passthrough có thể chỉ thấy hostname/metadata |
| IDS/IPS/NDR | Alert type, rule, confidence, matched flow | Một alert không chứng minh xâm nhập |
| EDR/host | Process, parent process, command line, hash, user, socket | Agent mất kết nối hoặc bị giới hạn telemetry |
| DHCP/NAC/VPN | Lease lịch sử, MAC, IP pool, identity, VLAN/SSID | IP ở thời điểm hiện tại có thể khác tại sự kiện |
| Cloud flow/DNS | VPC/VNet, workload identity, security policy, NAT | Provider-managed service có thể không cho PCAP |
| Mock collector | Request timestamp, test marker, response tĩnh | Không chứng minh hoạt động task execution hoặc dữ liệu thật |

**Vantage point** là điểm capture. Nếu capture ở firewall phía Internet sau NAT, có thể chỉ thấy địa chỉ NAT/proxy; nếu DNS resolver cache trả lời, sensor trên đường ra ngoài có thể không thấy truy vấn tương ứng. Ghi rõ vị trí, điều kiện lọc và giới hạn trước khi đánh giá sensor có “bỏ sót” hay không.

### 8.1. Kiểm tra chất lượng thời gian

- Tất cả log nên lưu UTC hoặc ghi rõ offset/múi giờ.
- Phân biệt **event time**, **ingestion time** và **analyst observation time**.
- Kiểm tra NTP, clock skew, độ trễ log và sampling.
- Ghi cửa sổ lấy mẫu cố định khi tính khoảng thời gian beacon.
- Không ghép hai sự kiện chỉ vì có cùng IP nếu DHCP/NAT mapping thay đổi.

## 9. Phân tích beacon: số liệu và giới hạn

### 9.1. Các chỉ số nên kết hợp

| Feature | Cách đọc | Những nguyên nhân hợp lệ có thể gây nhiễu |
|---|---|---|
| Số phiên tới cùng đích | Session count theo source, destination, port, thời gian | Polling và monitoring |
| Inter-arrival time | Khoảng thời gian giữa hai lần liên hệ liên tiếp | Scheduler định kỳ |
| Độ biến thiên khoảng thời gian | Phân phối/phương sai của inter-arrival | Network jitter, retry, cache, clock skew |
| Bytes/packets theo chiều | Mẫu gói nhỏ hai chiều hoặc bất thường so baseline | Heartbeat, TLS handshake, telemetry |
| Đích hiếm/first-seen | Domain/IP mới với asset hoặc toàn tổ chức | Dịch vụ mới hoặc CDN |
| DNS pattern | Tên miền, tỷ lệ NXDOMAIN, số QNAME riêng biệt | Resolver retry, app ID, CDN |
| Process lineage | Chương trình nào mở socket, ai khởi chạy | Agent hợp lệ nhưng chưa trong inventory |
| Rule/policy path | Proxy, direct egress, chặn/cho phép, NAT | Thay đổi mạng có phê duyệt |

Không có một ngưỡng như “cứ hai phút là C2” phù hợp mọi tổ chức. Muốn lập detector, hãy lấy baseline theo nhóm thiết bị và ứng dụng, xác định false-positive rate, kiểm tra lịch thay đổi và kết hợp nhiều nguồn.

### 9.2. Cách đọc inter-arrival time

Giả sử các phiên mới được tạo ở giây 00, 121, 243, 366 kể từ đầu bài, khoảng cách là:

- 121 − 0 = 121 giây
- 243 − 121 = 122 giây
- 366 − 243 = 123 giây

Ba khoảng này gợi ý **hoạt động gần định kỳ**. Nhưng cần biết đó là **kết nối mới** hay dữ liệu được gửi trong một kết nối keep-alive có sẵn; NetFlow timeout và aggregation có thể tạo biểu diễn khác với số request HTTP thật.

Để tránh kết luận sai:

1. Dùng cùng loại timestamp và so với thời gian ingest.
2. Tách mỗi source–destination–transport và các kết nối sau NAT.
3. Xử lý retransmission và flow expiration để không đếm giả nhiều phiên.
4. Kiểm tra tồn tại baseline/ứng dụng hoặc công việc theo lịch tương ứng.
5. Dùng một cửa sổ quan sát đủ dài, đánh dấu chất lượng dữ liệu và khoảng trống.

### 9.3. Tương quan nhiều tín hiệu

Một trường hợp đáng ưu tiên điều tra có thể gồm **đích mới + nhiều phiên nhỏ lặp lại + process chưa có trong inventory + kết nối egress ngoài policy**. Khi mỗi nguồn bổ sung thông tin độc lập, độ tin cậy tăng. Nếu EDR xác minh đúng agent cập nhật hợp lệ, DNS thuộc nhà cung cấp và service owner xác nhận lịch polling, giả thuyết C2 phải được hạ mức hoặc bác bỏ.

Trong báo cáo luôn phân biệt:

- **Fact:** đã thấy trên log/capture nào, lúc nào.
- **Hypothesis:** điều nào có thể giải thích các fact.
- **Unknown:** dữ liệu chưa có hoặc sensor không đọc được.
- **Decision:** hành động nào đã được phê duyệt.
- **Next check:** nguồn độc lập nào sẽ củng cố hoặc bác bỏ.

## 10. Phân tích PCAP và log trong môi trường phòng thủ

Ví dụ sau chỉ đọc tệp PCAP mẫu đã được chuẩn bị trong lab; không tạo phần mềm C2.

### 10.1. Kiểm tra file và xác nhận điểm thu

~~~bash
sha256sum /path/to/ex-c2-006.pcapng
capinfos /path/to/ex-c2-006.pcapng
~~~

Ghi **source, collector, UTC window, capture interface, filter, owner** và hash trong evidence manifest. Hash chỉ cho phép kiểm chứng file giữ nguyên từ khi tính, không tự chứng minh mọi packet trong mạng đã được ghi.

### 10.2. Lọc các kết nối TCP theo địa chỉ lab

~~~bash
tshark -r /path/to/ex-c2-006.pcapng \
  -Y 'ip.addr == 10.77.10.25 && ip.addr == 10.77.50.20 && tcp.port == 8443' \
  -T fields -E header=y \
  -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.flags.syn \
  -e tcp.flags.reset -e frame.len
~~~

Với IPv6, cần lọc bằng địa chỉ IPv6 và các field tương ứng. Với TLS, lưu lượng ứng dụng bị mã hóa; có thể xem metadata phiên, thông tin TLS hợp lệ quan sát được tại vị trí capture và log ứng dụng từ collector nếu có quyền.

### 10.3. Xem danh sách conversation và thời lượng

~~~bash
tshark -r /path/to/ex-c2-006.pcapng -q -z conv,tcp
~~~

Một lần kết nối TCP có thể chứa nhiều HTTP request qua keep-alive hoặc HTTP/2; ngược lại một đợt thử kết nối có thể sinh nhiều SYN. Đừng coi mỗi dòng TCP flow là một “lệnh C2”.

### 10.4. Truy vấn log tổng hợp

Ví dụ SQL sau dùng bảng giả định **network_flows** đã chuẩn hóa. Điều chỉnh syntax/schema theo nền tảng SIEM.

~~~sql
SELECT
  src_asset,
  dst_ip,
  dst_port,
  COUNT(*) AS flow_count,
  MIN(event_time_utc) AS first_seen_utc,
  MAX(event_time_utc) AS last_seen_utc,
  SUM(bytes_out) AS total_bytes_out,
  SUM(bytes_in) AS total_bytes_in
FROM network_flows
WHERE event_time_utc >= TIMESTAMPTZ '2026-01-15 08:55:00+00'
  AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:20:00+00'
  AND src_ip = '10.77.10.25'
GROUP BY src_asset, dst_ip, dst_port
ORDER BY flow_count DESC;
~~~

Các kết quả tính theo **flow record**, không phải số HTTP request, và phụ thuộc timeout/logging. Nếu muốn tính inter-arrival, cần dùng event timestamp cho các **sự kiện khởi tạo được định nghĩa rõ**. Với các sensor khác nhau, định nghĩa ấy có thể không giống nhau.

Ví dụ truy vấn chỉ đọc để xem khoảng cách thời gian giữa các **connection-start event**:

~~~sql
WITH starts AS (
  SELECT
    src_ip,
    dst_ip,
    dst_port,
    event_time_utc,
    LAG(event_time_utc) OVER (
      PARTITION BY src_ip, dst_ip, dst_port
      ORDER BY event_time_utc
    ) AS previous_start
  FROM network_flows
  WHERE event_kind = 'connection_start'
    AND event_time_utc >= TIMESTAMPTZ '2026-01-15 08:55:00+00'
    AND event_time_utc <  TIMESTAMPTZ '2026-01-15 09:20:00+00'
)
SELECT
  src_ip, dst_ip, dst_port, event_time_utc,
  EXTRACT(EPOCH FROM event_time_utc - previous_start) AS gap_seconds
FROM starts
WHERE previous_start IS NOT NULL
ORDER BY src_ip, dst_ip, dst_port, event_time_utc;
~~~

**Lưu ý:** nhiều hệ thống chỉ xuất flow end record. Nếu không có trường event_kind hoặc connection_start, phải xác định thời gian bắt đầu từ các trường hợp lệ và kiểm tra với PCAP. Không bịa trường hoặc diễn giải flow end time thành beacon timestamp.

## 11. Kiểm tra smoke test cho mock collector

Chỉ thực hiện khi **đã có sẵn mock HTTPS collector trong lab**, hostname và chứng chỉ được quản lý. Đây là **một kết nối kiểm tra duy nhất** tới dịch vụ sức khỏe tĩnh, không tải về hoặc thực thi chỉ thị.

Ví dụ từ Client-LAB-25:

~~~bash
curl --connect-timeout 3 --max-time 10 \
  --cacert /path/to/lab-ca.pem \
  --resolve c2-exercise.lab.example:8443:10.77.50.20 \
  https://c2-exercise.lab.example:8443/health
~~~

Các tùy chọn:

- **--resolve** ánh xạ hostname tới IP lab trong kết nối này để vẫn dùng Host/SNI tương ứng.
- **--cacert** xác thực chứng chỉ của CA lab; không tắt xác minh TLS.
- **--connect-timeout** và **--max-time** giới hạn thời gian.
- Chỉ endpoint **/health** được dùng; không có request chứa file, credential hoặc dữ liệu thật.
- Không cho chạy command này qua cron/daemon hoặc vòng lặp tự động để tránh chuyển thành công cụ beacon.

Kiểm tra thành công phải đối chiếu ít nhất: client response, firewall/proxy ALLOW trên đúng rule, collector access log với test marker và DNS/route theo design. Khi chuyển sang inject containment, có thể thay hành động thực tế bằng log replay **DENY**; nếu thực hiện đổi rule trong lab, phải có rollback và xác minh luồng hợp lệ không bị ảnh hưởng.

## 12. Kịch bản inject cho buổi purple team 90 phút

| Thời điểm | Inject cho người chơi | Hành động được mong đợi | Tiêu chí chấm |
|---|---|---|---|
| T+00 | [EXERCISE] Briefing: lab, phạm vi, nguồn log, liên hệ | Nhận vai trò, kiểm tra dashboard, sẵn sàng | Người trực và escalation rõ ràng |
| T+10 | NDR phát EX-C2-006: rare destination và small repeated flows | Mở case, xác minh alert, ưu tiên | Không kết luận C2 chỉ từ một alert |
| T+20 | DNS log liên kết query với Client-LAB-25 | Tra DHCP, chủ tài sản, đường egress | Asset mapping đúng timestamp |
| T+30 | Proxy log chỉ cho thấy HTTPS /health, EDR ghi process unreviewed | Kiểm tra process lineage và mục đích ứng dụng | Tách fact, hypothesis, unknown |
| T+40 | Controller báo một thiết bị hợp lệ cũng polling định kỳ | Loại trừ false positive, so baseline | Phân biệt polling hợp lệ với kịch bản nghi vấn |
| T+50 | Firewall log cho thấy luồng test còn ALLOW; quản lý yêu cầu phương án | Lập containment hẹp, đánh giá tác động và rollback | Có IC/phê duyệt và ảnh hưởng rõ |
| T+60 | Inject giả lập rule DENY được áp, collector hết request mới | Xác minh nhiều nguồn và kiểm tra health | Không coi “hết alert” là bằng chứng duy nhất |
| T+70 | Log SIEM nhận trễ 5 phút; event time và ingest time khác | Điều chỉnh timeline, đánh giá độ tin cậy | Không kết luận sai do log delay |
| T+80 | Quản lý yêu cầu SITREP trong 2 phút | Trình bày đã biết, chưa biết, next action | Ngắn, chính xác, không khẳng định exfiltration |
| T+90 | Kết thúc exercise, thu chứng cứ và debrief | AAR, action tracker, chủ sở hữu cải tiến | Có kế hoạch retest |

Controller có thể thêm nhánh nếu đội xử lý sớm hoặc chậm. Cần ghi mọi inject đã phát và tình huống thay đổi, tránh chấm điểm đội theo những dữ liệu họ chưa được nhận.

### 12.1. Nhánh A — False positive của monitoring

Điều phối cung cấp change record chứng minh Client-LAB-25 mới cài agent monitoring hợp lệ trước mốc 09:00. Người chơi phải đối chiếu binary, owner, URL và lịch polling, rồi điều chỉnh mức tin cậy. Nếu kết luận benign, đó có thể là kết quả đúng; vẫn nên đề xuất tuning detector để giảm nhiễu.

### 12.2. Nhánh B — Sai lệch do proxy/NAT

Firewall chỉ nhìn thấy IP proxy 10.77.40.10, còn proxy log có client identity và destination. Đội phải nối proxy session/NAT mapping với host thật; không tự động cô lập proxy của toàn tổ chức.

### 12.3. Nhánh C — Cloud workload và DNS mã hóa

Một workload cloud liên hệ endpoint qua đường NAT gateway; sensor không đọc được nội dung TLS/DoH. Đội phải kiểm tra cloud flow log, DNS logs hợp lệ, workload identity, security group/route và EDR. Không suy ra payload từ byte count.

### 12.4. Nhánh D — Control bị lỗi nhưng SIEM im lặng

Rule thử nghiệm đang DENY, nhưng collector vẫn nhận một request từ đường đi khác. Đội cần kiểm tra policy coverage, NAT/VRF/IPv6, route bypass và dữ liệu quan sát. Đây là bài kiểm thử kiến trúc mạng, không phải cơ hội để tạo đường C2 thực.

## 13. Playbook điều tra khi có tín hiệu giống C2

### Bước 1 — Triage alert

Ghi incident ID, alert type, nguồn sensor, event/ingest time, asset, IP, destination, confidence, phạm vi giả định và người xử lý. Xác định alert thuộc exercise hay sự cố thật. Nếu phát hiện sự cố thật trong khi diễn tập, dừng inject liên quan và chuyển đúng quy trình production.

### Bước 2 — Xác minh asset theo thời điểm

Đối chiếu DHCP lease, MAC, NAC/VLAN, VPN pool, NAT, Wi-Fi controller, cloud instance ID và inventory. Tại firewall sau proxy/NAT, một IP có thể đại diện nhiều máy; cần dữ liệu tương quan đúng thời điểm.

### Bước 3 — Phân tích chuỗi kết nối

Tạo timeline từ firewall/proxy/flow/DNS. Xác định số phiên, khoảng giữa phiên, first/last seen, đích hiếm, tần suất thất bại, bytes theo chiều và thay đổi quanh mốc giờ xảy ra sự kiện. Kiểm tra baseline ứng dụng và thiết bị cùng nhóm.

### Bước 4 — Tìm lời giải thích từ endpoint

Tra EDR/OS log, process lineage, binary signature, chủ dịch vụ, change record, scheduled task hợp lệ và cấu hình proxy/DNS. Không tự gán nhãn độc hại cho process chỉ vì tên chưa biết.

### Bước 5 — Phân loại và mở rộng phạm vi

Nếu có căn cứ tăng mức nghi vấn, xem liệu host khác có liên hệ cùng đích, dùng cùng process hoặc nhóm DNS bất thường không. Phân biệt phân vùng user, VPN, Wi-Fi/IoT và cloud; xác nhận hệ thống nào cần được cách ly. Cần cân nhắc ảnh hưởng nghiệp vụ trước khi thay đổi firewall.

### Bước 6 — Containment hẹp và có rollback

Trong lab, IC có thể duyệt chặn **Client-LAB-25 → MOCK-COLLECTOR:8443** thay vì chặn toàn VLAN. Ghi rule ID, người phê duyệt, thời điểm, cấu hình trước/sau và cách hoàn tác. Sau khi áp rule, dùng log DENY và kết quả collector để xác minh, đồng thời thử dịch vụ hợp lệ để phát hiện tác động phụ.

Trong sự cố thực, lựa chọn có thể là cô lập host bằng EDR/NAC, chặn destination đã xác minh, hạn chế egress hoặc thu hồi tài khoản/khóa liên quan. Quyết định phụ thuộc mức tin cậy và mức độ ảnh hưởng; không suy diễn từ dữ liệu lab sang production.

### Bước 7 — Phục hồi và cải tiến

Xác minh xử lý nguyên nhân hoặc ghi rõ rủi ro còn lại được chấp thuận. Thử lại DNS, ứng dụng, VPN và đường quản trị hợp lệ; kiểm tra sensor vẫn nhận log. Chỉ đóng case khi điều kiện đã được phê duyệt, sau đó đưa phát hiện vào AAR và kế hoạch cải tiến.

## 14. Detection engineering và yêu cầu kiểm chứng

### 14.1. Mô hình detector nhiều tín hiệu

Một detector có thể ưu tiên case nếu đồng thời có:

- Source là endpoint hoặc workload có định danh rõ.
- Destination hiếm, mới xuất hiện hoặc nằm ngoài danh sách dịch vụ được phê duyệt.
- Nhiều connection-start event tới cùng đích trong cửa sổ có tần suất bất thường so baseline.
- Kích thước các flow tương đối nhỏ và cùng loại trong nhiều lần.
- Process chưa có trong inventory, hoặc hành vi xuất hiện không giải thích được bằng change record.
- Đường egress vi phạm policy (ví dụ trực tiếp thay vì qua proxy/DNS được quản lý).

**Pseudo detection logic** (không phải rule cài được ngay):

~~~text
INPUT: normalized DNS + flow + proxy + EDR events

GROUP BY src_asset, destination, time_window
FEATURES:
  new_destination
  repeated_connection_starts
  gap_distribution
  flow_byte_distribution
  process_known_or_unknown
  destination_policy_exception
  correlated_dns_query
  telemetry_quality

IF multiple_independent_signals AND not approved_business_pattern:
    CREATE investigation_case
    INCLUDE facts, raw_event_ids, sources, missing_evidence
ELSE:
    retain_for_baseline_or_tuning
~~~

Không hard-code một ngưỡng duy nhất dùng cho mọi VLAN. Detector phải có tài liệu giải thích logic, các nguồn phụ thuộc, danh sách ngoại lệ có owner và kế hoạch thử hồi quy.

### 14.2. Những tiêu chí detector cần đo

| Chỉ số | Giải thích | Cách lấy bằng chứng |
|---|---|---|
| True positive trên kịch bản lab | Alert được tạo đúng trường hợp giả lập trong phạm vi | Test run ID và sự kiện SIEM |
| False positive trên nhóm đối chứng | Agent hợp lệ có bị báo sai không? | Baseline và change record |
| Time to alert | Event time đến alert creation time | Log nguồn và SIEM |
| Time to acknowledge | Alert đến analyst nhận case | Ticket timestamp |
| Time to triage | Nhận case đến kết luận phân loại có lý do | Decision log |
| Time to containment | Quyết định đến thời điểm rule có hiệu lực | Rule log, traffic test |
| Detection coverage | Bao nhiêu kịch bản/nguồn dữ liệu thuộc scope tạo ra tín hiệu | Ma trận kịch bản và log |
| Telemetry completeness | Bao nhiêu nguồn/field kỳ vọng sẵn có | Sensor health và schema check |

Đo thời gian theo định nghĩa nhất quán; chỉ gọi các phép đo trung bình là **MTTD/MTTR** nếu có nhiều lượt và định nghĩa mốc đầu/cuối phù hợp. Một case lab không đại diện cho toàn bộ hiệu quả production.

### 14.3. Kiểm tra cả độ nhạy và độ đặc hiệu

Một detector tăng sensitivity bằng cách cảnh báo mọi kết nối định kỳ có thể khiến SOC quá tải. Cần nhóm đối chứng như monitoring, software update, NTP và API polling. Chấm chất lượng khi detector **phát hiện ca cần điều tra** đồng thời giữ mức false positive có thể vận hành được.

## 15. Đo kết quả một lượt diễn tập

Giả định timeline mẫu độc lập với các inject:

| Sự kiện | UTC |
|---|---|
| Kết nối lab đầu tiên | 09:00:04 |
| NDR alert | 09:08:20 |
| SOC nhận trách nhiệm | 09:11:00 |
| SOC phân loại nghi vấn, báo IC | 09:18:00 |
| IC phê duyệt containment | 09:22:00 |
| Firewall ghi DENY cho test mới | 09:25:00 |
| Dịch vụ hợp lệ vượt health check | 09:29:00 |
| Đóng phiên diễn tập | 09:45:00 |

| Chỉ số | Công thức | Kết quả |
|---|---|---:|
| Phát hiện tín hiệu | 09:08:20 − 09:00:04 | 8 phút 16 giây |
| Tiếp nhận alert | 09:11:00 − 09:08:20 | 2 phút 40 giây |
| Phân loại sau tiếp nhận | 09:18:00 − 09:11:00 | 7 phút |
| Ngăn chặn sau phê duyệt | 09:25:00 − 09:22:00 | 3 phút |
| Xác minh dịch vụ sau containment | 09:29:00 − 09:25:00 | 4 phút |

Số liệu chỉ là minh họa, không phải SLO chung cho mọi SOC. Khi SIEM log trễ, không được tự động dùng ingest time thay event time mà không ghi khác biệt. Các bước điều tra có thể chồng lấp; timeline cho phép thấy rõ lý do quyết định.

### 15.1. Rubric 100 điểm

| Năng lực | Điểm tối đa | Bằng chứng |
|---|---:|---|
| Chuẩn bị và tuân thủ ROE | 10 | Scope, quyền, stop condition, marker |
| Detection và triage | 20 | Alert/ticket đúng kịch bản, analyst xác nhận |
| Điều tra và phân biệt false positive | 20 | Đối chiếu DNS/flow/EDR, baseline, giả thuyết |
| Asset mapping và scope | 10 | DHCP/NAT/VPN/cloud correlation đúng timestamp |
| Containment và rollback | 15 | Phê duyệt, rule hẹp, verify DENY, health check |
| Chứng cứ và timeline | 10 | Event IDs, UTC, PCAP/log, manifest |
| Phối hợp và SITREP | 10 | Thông tin đúng, rõ fact và unknown |
| AAR và cải tiến | 5 | Owner, deadline, retest |
| **Tổng** | **100** | Chấm theo bằng chứng, không dựa trên tuyên bố của controller |

## 16. Nhật ký điều phối và mẫu báo cáo

### 16.1. Evidence manifest

| Trường | Giá trị minh họa |
|---|---|
| Exercise/Case ID | EX-C2-006 |
| Evidence ID | EX-C2-006-E04 |
| Nguồn | Firewall-LAB hoặc DNS01 |
| Loại | Log export/PCAP trong lab |
| Event time (UTC) | 2026-01-15 09:00–09:15 |
| Thời gian thu | Khi analyst xuất file và ghi timestamp |
| Người thu | Analyst được chỉ định |
| Phạm vi/filter | 10.77.10.25 ↔ 10.77.50.20:8443 |
| Hash | SHA-256 thực của tệp đã lưu |
| Vị trí lưu | Kho lab có quyền truy cập và retention rõ |
| Chain of custody | Người giao, nhận, thời điểm và mục đích |

Không tự đặt hash giả trong hồ sơ chứng cứ. Khi chuyển log cho đội đánh giá, loại thông tin không cần thiết, hạn chế quyền và giữ bản gốc trong kho an toàn.

### 16.2. Mẫu SITREP

~~~text
[EXERCISE] SITREP 01
Case: EX-C2-006
Time: 2026-01-15 09:20 UTC
Status: UNDER INVESTIGATION

FACTS:
- Client-LAB-25 phát sinh các phiên TCP/8443 lặp lại
  tới địa chỉ collector trong lab.
- DNS và firewall logs xác nhận hostname/đường đi
  trong cửa sổ sự kiện.
- NDR tạo alert EX-C2-006 lúc 09:08:20 UTC.

HYPOTHESIS:
- Hành vi giống beacon C2; chưa chứng minh có
  task execution hoặc exfiltration.

UNKNOWN:
- Process có phải phần mềm được phê duyệt?
- Có đường kết nối khác ngoài collector test không?

ACTIONS:
- Endpoint owner kiểm tra process lineage và change record.
- NOC chuẩn bị containment hẹp với rollback.
- SOC so nhóm đối chứng và rà soát cloud/VPN scope.

NEXT UPDATE: 09:35 UTC
~~~

Khi diễn tập không có dữ liệu về payload, báo cáo cần ghi rõ **không có chứng cứ cho tasking thật hoặc exfiltration**. Không được viết “đã điều khiển từ xa” chỉ vì thấy packet nhỏ lặp lại.

### 16.3. After Action Review (AAR)

Sau buổi diễn tập, thu nhận các thông tin:

1. **Objective:** mục tiêu nào được kiểm tra, dữ liệu và công cụ nào được dùng?
2. **Observation:** alert đúng thời điểm hay chậm, analyst lấy nguồn dữ liệu đúng không?
3. **Impact:** thiếu log/DHCP/NAT/EDR có làm chậm xác định host hoặc thay đổi policy không?
4. **Root cause:** do detector, quyền truy cập, schema, quy trình hoặc hạ tầng?
5. **Improvement:** action cụ thể, người phụ trách, deadline và cách test lại.

Ví dụ: “Proxy chỉ giữ NAT IP → SOC mất 12 phút truy đúng máy → bổ sung trường authenticated_device_id và lưu NAT mapping vào SIEM → SOC platform owner → dùng lại EX-C2-006 với IP client đổi để xác minh”.

## 17. Các lỗi thường gặp khi tổ chức mô phỏng C2

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Đưa traffic tới endpoint Internet thật | Vượt scope và khó kiểm soát | Chỉ dùng collector lab, log replay hoặc đích đã phê duyệt |
| Cho phép mock collector thực thi lệnh | Thay đổi rủi ro và mục đích diễn tập | Chỉ phản hồi marker tĩnh, không có thực thi |
| Kết luận beacon chỉ từ periodicity | False positive với monitoring | Baseline, process, owner và nguồn độc lập |
| Kết luận exfil từ bytes_out | Không có chứng cứ về nội dung dữ liệu | Phân biệt metadata với payload có thể xác minh |
| Không gắn nguồn với host thật | Nhầm NAT/proxy/resolver thành endpoint | DHCP/VPN/NAC/proxy correlation theo thời điểm |
| Không xem DoH/DoT và TLS | Đánh giá sai coverage của sensor | Ghi điểm mù, xem endpoint/resolver log có quyền |
| Coi “không có alert” là đã ngăn chặn | Có thể sensor/log bị lỗi | Test rule DENY, collector log và health telemetry |
| Containment cả VLAN | Gián đoạn dịch vụ nghiệp vụ | Chặn hẹp, phê duyệt, rollback, kiểm thử |
| Đặt ngưỡng giống nhau cho mọi asset | Sinh nhiều alert không hữu ích | Tuning theo nhóm dịch vụ và baseline |
| Không phân biệt replay với test live | Báo sai kết quả của firewall production | Ghi rõ loại exercise cho từng kết quả |
| Không ghi time sync và data gaps | Timeline sai, quyết định thiếu căn cứ | Event/ingest time, NTP, sensor health |
| Không có nhóm đối chứng | Không đo được false positive | Bổ sung health check/update agent hợp lệ |
| Không có owner cho cải tiến | Kết quả không dẫn tới thay đổi | AAR với deadline và retest |

## 18. Bài tập tự thực hành

### Bài tập 1 — Phân biệt beacon giả với monitoring

Hai host có kết nối HTTPS tới một đích mỗi hai phút. Host A thuộc nhóm monitoring đã đăng ký; host B có process chưa rõ. Hãy lập danh sách **bốn nguồn chứng cứ** và đưa ra hai giả thuyết cho mỗi host.

**Gợi ý:** process lineage, change record, proxy/DNS logs, service owner, firewall egress và baseline. Không kết luận Host B bị chiếm quyền chỉ vì process chưa được inventory.

### Bài tập 2 — Đọc dữ liệu flow

Cho kết nối từ 10.77.10.25 tới 10.77.50.20:8443 ở 09:00:04, 09:02:05, 09:04:07 và 09:06:10. Hãy tính inter-arrival và giải thích liệu đủ bằng chứng để kết luận có C2 hay chưa.

**Gợi ý:** khoảng cách lần lượt 121, 122 và 123 giây; đây là tín hiệu gần định kỳ. Chưa đủ để chứng minh task execution, mục đích ác ý hoặc dữ liệu đã thoát ra ngoài.

### Bài tập 3 — Nhận ra điểm mù

Firewall thấy một IP proxy truy cập collector, nhưng không thấy IP máy trạm. Hãy nêu cách gắn kết nối với asset thật, và lý do không nên cô lập proxy ngay.

**Gợi ý:** proxy user/device log, NAT mapping, session ID, identity, DHCP và timestamp. Proxy có thể phục vụ nhiều máy.

### Bài tập 4 — Đánh giá containment

Sau khi controller phát inject DENY, NDR không còn alert mới nhưng client vẫn truy cập ứng dụng nội bộ. Có đủ cơ sở để kết luận containment PASS không?

**Gợi ý:** chưa đủ. Cần firewall rule hit/action, collector không nhận request mới theo cửa sổ đã định, kiểm tra đường thay thế và xác nhận sensor vẫn hoạt động; sau đó xác minh ứng dụng hợp lệ vẫn bình thường.

### Bài tập 5 — Viết phát hiện ở mức tin cậy đúng

Một analyst báo “đã phát hiện C2 chắc chắn, có exfiltration” dựa vào six small flows và DNS query mới. Hãy viết lại phát hiện theo dạng **facts → hypotheses → unknowns → next checks**.

**Gợi ý:** facts là kết nối lặp lại và domain mới; C2 là giả thuyết; dữ liệu/tiến trình/chủ đích còn chưa xác minh; cần endpoint và service owner cùng telemetry độc lập.

### Bài tập 6 — Thiết kế detector

Hãy thiết kế pseudo-rule cảnh báo khi một host liên hệ tới destination hiếm, có nhiều phiên gần định kỳ và process lạ. Nêu ít nhất **ba false positives**, hai nguồn telemetry bổ sung và cách đo precision theo dữ liệu test được gán nhãn.

**Tiêu chí đạt:** không đặt ngưỡng chung cho mọi môi trường, có nguồn chứng cứ và quy trình tuning; ghi rõ chưa kiểm chứng trên production.

## 19. Checklist trước khi công bố hoàn thành diễn tập

- [ ] Có ROE, phạm vi mạng, người phê duyệt, thời gian, điều kiện dừng và rollback.
- [ ] Dùng dữ liệu lab tổng hợp, endpoint collector nội bộ và marker EXERCISE; không có task execution thực.
- [ ] Đã xác minh nguồn, đích, route, firewall policy và điểm quan sát trước bài test.
- [ ] DNS/flow/proxy/firewall/EDR có event time UTC, asset mapping và tình trạng sensor rõ.
- [ ] Đã tách metadata của TLS/DNS khỏi nội dung không thể quan sát.
- [ ] Detector phát alert trên kịch bản cần phát hiện và có nhóm đối chứng cho false positive.
- [ ] Analyst lập timeline, kiểm tra periodicity, đích hiếm, process và ngữ cảnh nghiệp vụ.
- [ ] Báo cáo phân biệt fact, hypothesis, unknown, decision và next action.
- [ ] Containment có phê duyệt, phạm vi hẹp, rollback và xác minh hiệu lực trên nhiều nguồn.
- [ ] Kiểm tra ứng dụng và dịch vụ hợp lệ sau containment.
- [ ] Bằng chứng được lưu có ID, timestamp, điểm thu, hash (nếu file), quyền truy cập và chain of custody.
- [ ] Có SITREP, kết quả theo rubric, AAR và cải tiến cụ thể có người phụ trách.
- [ ] Kết quả ghi rõ là tabletop, replay hay traffic test; không suy rộng sang môi trường khác chưa kiểm thử.

Một bài **mô phỏng command and control** đạt yêu cầu khi đội phòng thủ có thể nhận diện đúng tín hiệu cần điều tra, giải thích mức độ tin cậy của kết luận, kiểm tra ranh giới mạng và thực hiện ứng phó có kiểm chứng. Phương pháp này phát triển năng lực red team/purple team trong phạm vi an toàn, đồng thời cải thiện firewall egress, DNS, IDS/IPS, giám sát endpoint, cloud và quy trình phản ứng sự cố mạng.

