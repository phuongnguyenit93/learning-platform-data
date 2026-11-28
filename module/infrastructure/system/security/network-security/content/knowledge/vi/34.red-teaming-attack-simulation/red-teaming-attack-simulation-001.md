# Mục tiêu và phạm vi của network red team

## 1. Network red team nhằm kiểm chứng điều gì?

**Network red team** là hoạt động mô phỏng có ủy quyền những hành vi đối kháng liên quan đến hạ tầng mạng nhằm đánh giá khả năng **ngăn ngừa, phát hiện, điều tra, ứng phó và phục hồi** của một tổ chức trước các mục tiêu tấn công thực tế. Red team không chỉ hỏi “có lỗ hổng nào?” mà hỏi “trong điều kiện và phạm vi cho phép, các lớp phòng vệ có ngăn được một kịch bản rủi ro có ý nghĩa đối với hoạt động kinh doanh hay không?”.

Trong chương **Red team và mô phỏng tấn công mạng** thuộc mô-đun **SECURITY_NETWORK_SECURITY**, phạm vi có thể liên quan đến **phân đoạn mạng, firewall/ACL, VPN, IDS/IPS, DNS, Wi-Fi/NAC, load balancer, proxy, mạng cloud, service mesh, IAM và giám sát lưu lượng**. Mục tiêu không phải phá hủy hoặc giành quyền truy cập tối đa bằng mọi cách, mà là thu thập bằng chứng có kiểm soát về khả năng hoạt động của những lớp phòng vệ này.

Ví dụ, một tổ chức yêu cầu xác minh giả thuyết: “Một tài khoản nhà thầu chỉ có quyền VPN vào vùng hỗ trợ không được phép tiếp cận mạng thanh toán”. Một bài red team tốt sẽ định nghĩa trước các tài sản mô phỏng, điểm khởi đầu, đường truy cập được phép thử, tín hiệu phòng vệ kỳ vọng, điều kiện dừng và bằng chứng chấp nhận được. **Chỉ khi bài kiểm thử được chủ sở hữu phê duyệt**, nhóm mới thực hiện các bước đã thống nhất và báo cáo kết quả.

Sau bài học, người học cần:

- Phân biệt network red team với vulnerability assessment, penetration test, purple team và diễn tập ứng phó.
- Chuyển rủi ro nghiệp vụ thành **mục tiêu và giả thuyết kiểm thử có thể đo**.
- Xác định tài sản, vùng tin cậy, con đường giao tiếp, danh tính, dữ liệu và kỹ thuật **trong/ngoài phạm vi**.
- Xây dựng **Rules of Engagement (RoE)** với phê duyệt, giới hạn an toàn, điều kiện dừng và phối hợp các bên.
- Xác định chứng cứ và tiêu chí đánh giá cả ngăn ngừa, phát hiện, phản ứng và phục hồi.
- Đọc kết quả đúng giới hạn, tránh coi một kịch bản thành công hoặc thất bại là kết luận tuyệt đối về toàn bộ mạng.

**Nguyên tắc cốt lõi:** một bài diễn tập chỉ có giá trị khi **mục tiêu rõ ràng, quyền hạn rõ ràng, rủi ro vận hành được kiểm soát và kết luận có bằng chứng**.

## 2. Red team khác những hình thức kiểm thử nào?

| Hoạt động | Câu hỏi trung tâm | Kết quả chính | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **Vulnerability assessment** | Có cấu hình yếu hoặc lỗ hổng đã biết nào? | Danh sách phát hiện, mức độ nghiêm trọng và khuyến nghị | Không mặc định chứng minh đường tấn công khả thi |
| **Penetration testing** | Có thể khai thác hoặc chứng minh một điểm yếu trong phạm vi cụ thể không? | Bằng chứng kỹ thuật và khuyến nghị sửa | Thường chú trọng phát hiện điểm yếu hơn năng lực phòng vệ end-to-end |
| **Network red team** | Phòng vệ có ngăn, phát hiện và xử lý được hành vi đối kháng hướng mục tiêu không? | Kết quả theo mục tiêu, timeline, detection/response gaps | Kết quả tùy kịch bản, thời gian và RoE; không bao phủ mọi đe dọa |
| **Purple teaming** | Red và blue phối hợp cải thiện detection/response như thế nào? | Điều chỉnh detection rule, playbook, telemetry và kiểm thử lại | Tính phối hợp thường cao hơn diễn tập đối kháng kín thông tin |
| **Breach and attack simulation (BAS)** | Những hành vi giả lập cụ thể có kích hoạt control/detection không? | Kiểm tra lặp lại, có thể tự động hóa và đo độ bao phủ | Kịch bản mô phỏng có thể đơn giản hơn hành vi người thật |
| **Tabletop exercise** | Quyết định, phối hợp và quy trình ứng phó có hiệu quả không? | Bài học về quy trình, quyền hạn và truyền thông | Có thể không tạo traffic hoặc bằng chứng kỹ thuật |
| **Configuration/segmentation validation** | Policy được áp dụng có khớp thiết kế không? | Ma trận allow/deny và cấu hình cần sửa | Có thể không đánh giá đầy đủ năng lực SOC |

Các hình thức trên bổ sung nhau. Chẳng hạn, việc thấy TCP/22 có thể truy cập được từ một mạng khách là một **phát hiện về phạm vi kết nối**; chưa đủ chứng minh tài khoản bị xâm nhập. Một bài red team có thể dùng phát hiện này làm điểm khởi đầu cho giả thuyết được phép, nhưng không nhất thiết phải tiếp tục những hành động có nguy cơ cao.

### 2.1. Red team không đồng nghĩa “kiểm thử không giới hạn”

Mô phỏng đối kháng có thể giúp đánh giá năng lực phòng vệ tốt hơn khi có yếu tố bất ngờ, nhưng **không trao quyền tự động** cho đội kiểm thử truy cập mọi host, lấy dữ liệu thật, đánh cắp credential, làm nghẽn hệ thống hoặc bỏ qua các giới hạn đã thống nhất. Mọi hành động vẫn chịu sự điều chỉnh của thẩm quyền, hợp đồng, chính sách tổ chức và RoE.

## 3. Từ rủi ro nghiệp vụ đến mục tiêu red team

Một đề bài như “hãy tấn công mạng nội bộ” quá rộng và khó kiểm chứng. Thay vào đó, bắt đầu với **tài sản quan trọng và kết quả kinh doanh cần bảo vệ**, sau đó viết thành mục tiêu có điều kiện.

### 3.1. Mô hình bốn lớp

~~~text
Rủi ro nghiệp vụ
    ↓
Tài sản và năng lực cần bảo vệ
    ↓
Giả thuyết về đường tiếp cận và lớp phòng vệ
    ↓
Tiêu chí kiểm chứng và bằng chứng chấp nhận được
~~~

Ví dụ:

| Cấp | Nội dung minh họa |
| --- | --- |
| Rủi ro nghiệp vụ | Một tài khoản nhà thầu bị lạm dụng có thể tiếp cận dữ liệu thanh toán |
| Tài sản cần bảo vệ | Mạng thanh toán, API xử lý giao dịch, dịch vụ xác thực và audit logs |
| Giả thuyết | VPN/NAC và firewall phân đoạn ngăn kết nối từ vùng CONTRACTOR sang PAYMENT |
| Mục tiêu red team | Xác minh ranh giới truy cập và khả năng SOC phát hiện các attempt bị từ chối |
| Bằng chứng | Flow/firewall deny, VPN identity, kiểm thử kết nối giới hạn, cảnh báo và timeline SOC |
| Tiêu chí thành công phòng vệ | Không truy cập được endpoint đích ngoài quyền; telemetry đầy đủ; phản ứng theo playbook |

**Lưu ý:** mục tiêu của red team và mục tiêu của hệ thống phòng vệ không giống nhau. Nhóm red có thể đặt mục tiêu “thử chứng minh ranh giới bị vượt qua” trong khi đội blue mong muốn “ngăn chặn, ghi nhận và phản ứng”. Cả hai cần dùng cùng tiêu chí đã phê duyệt để đánh giá.

### 3.2. Cấu trúc một mục tiêu tốt

Mục tiêu nên trả lời:

1. **Đối tượng đe dọa giả định:** mức quyền, vị trí truy cập và năng lực được mô phỏng.
2. **Điểm bắt đầu:** subnet, VPN account thử nghiệm, lab host hoặc workload cụ thể.
3. **Tài sản/khả năng bảo vệ:** hệ thống, luồng hoặc dữ liệu có ý nghĩa nghiệp vụ.
4. **Ranh giới cần xác minh:** firewall, identity, DNS, network policy, EDR/NDR, proxy hoặc quy trình SOC.
5. **Bằng chứng đủ:** sự kiện nào chứng minh một control đã chặn, cho phép, phát hiện hoặc phản ứng.
6. **Giới hạn:** hành động bị cấm, điều kiện dừng và biện pháp thay thế an toàn.

Một mục tiêu dạng “đếm được bao nhiêu host” dễ tạo ra danh sách dài nhưng không chứng minh được sự cải thiện rủi ro. Ngược lại, mục tiêu dựa trên một đường ảnh hưởng nghiệp vụ giúp nhóm xác định **đúng phạm vi** và **đúng loại bằng chứng**.

## 4. Xác định phạm vi: không chỉ là dải IP

**Scope** là tập hợp các ranh giới của bài kiểm thử, bao gồm tài sản, danh tính, tuyến truy cập, thời gian, hành vi, dữ liệu và tác động cho phép. Danh sách IP chỉ là một thành phần.

| Chiều phạm vi | Câu hỏi xác định | Ví dụ |
| --- | --- | --- |
| Tài sản | Host, VM, appliance, domain, service nào được phép? | Gateway thử nghiệm, một subnet lab, API canary |
| Môi trường | Production, staging, lab hay tenant cloud nào? | Chỉ tenant security-validation |
| Vị trí nguồn | Team bắt đầu từ đâu? | VPN test user và máy thử nghiệm được quản lý |
| Danh tính | Tài khoản/quyền nào dùng được? | Account giả lập nhà thầu, không dùng tài khoản thật |
| Giao thức | TCP, UDP, DNS, HTTP, VPN hoặc Wi-Fi nào thuộc phạm vi? | TCP/443 với endpoint canary |
| Network path | Những zone, firewall, proxy và gateway nào được xét? | CONTRACTOR → VPN → FW → APP |
| Dữ liệu | Loại dữ liệu kiểm chứng nào được sử dụng? | Test marker không nhạy cảm |
| Kỹ thuật | Những nhóm hành vi mô phỏng nào được phép? | Kiểm tra allow/deny và tạo sự kiện thử nghiệm |
| Thời gian | Khung giờ, thời lượng, mốc dừng? | Cửa sổ thay đổi đã duyệt |
| Tác động | Ngưỡng tải, số request, điều kiện tạm dừng? | Không làm tăng lỗi dịch vụ, dừng theo tín hiệu NOC |
| Bên thứ ba | Có nhà cung cấp hoặc đối tác nào trong đường đi? | CDN và cloud managed LB phải có điều kiện riêng |

### 4.1. Trong phạm vi, ngoài phạm vi và chưa rõ

Không chỉ ghi “in scope”; cần mô tả riêng:

- **IN_SCOPE:** tài sản và hành vi đã được cấp quyền rõ ràng.
- **OUT_OF_SCOPE:** hệ thống quan trọng, thiết bị của bên thứ ba, tài khoản người dùng thực hoặc các hành vi chưa được phê duyệt.
- **CONDITIONAL_SCOPE:** chỉ thực hiện nếu có phê duyệt bổ sung, ví dụ service probing hoặc kiểm thử trong production.
- **UNKNOWN:** ranh giới chưa đủ bằng chứng về ownership hoặc tác động; **không thử trước, xác minh quyền trước**.

Ví dụ một hostname thuộc sở hữu tổ chức nhưng trỏ qua CDN của nhà cung cấp: quyền kiểm thử domain **không mặc nhiên cấp quyền tác động mọi thành phần edge/CDN**. Tương tự, việc tài khoản VPN truy cập được một subnet không có nghĩa toàn bộ thiết bị trong subnet đó đều được đưa vào cuộc diễn tập.

### 4.2. Tài sản “đi qua” và tài sản “được kiểm thử”

Một request có thể đi qua ISP, CDN, firewall, load balancer và cloud networking. Những thành phần trung gian **có thể bị ảnh hưởng** nhưng không nhất thiết thuộc quyền điều khiển của tổ chức. Nêu rõ **điểm chèn hành vi mô phỏng**, **điểm quan sát** và **điểm kết thúc**; tránh biến thiết bị trung gian của bên thứ ba thành mục tiêu chỉ vì nó nằm trong đường đi.

## 5. Lập bản đồ trust boundary và giả thuyết đường đi

Red team mạng nên bắt đầu bằng một **sơ đồ logical** thể hiện các vùng tin cậy và controls bảo vệ, thay vì mặc định địa chỉ IP là bản đồ đầy đủ.

~~~mermaid
flowchart LR
    C[Máy thử nghiệm nhà thầu] --> V[VPN / Identity]
    V --> F[Firewall phân đoạn]
    F --> A[Application zone]
    A --> G[API Gateway]
    G --> P[Payment service canary]
    D[DNS / Service discovery] -. Phân giải .-> A
    N[IDS / NDR / SOC] -. Giám sát .-> V
    N -. Giám sát .-> F
    N -. Giám sát .-> G
    Q[White cell] -. Quyền hạn và điều kiện dừng .-> C
~~~

Sơ đồ là ví dụ. Nó chưa chứng minh route thực tế, NAT hoặc nơi TLS được kết thúc. Phải đối chiếu:

- Vùng mạng, VLAN/VRF, VPC/VNet, subnet và route table.
- Firewall/ACL, cloud security group, NACL và Kubernetes NetworkPolicy.
- VPN remote access/site-to-site, chính sách danh tính và quyền nhà thầu.
- DNS/DoH/DoT, split-horizon, proxy và load balancer.
- IDS/IPS, NDR, SIEM, endpoint telemetry và phạm vi coverage.
- Kênh kiểm thử chiều đi **và chiều về**, bao gồm NAT/session state.

**Cùng một IP đích có thể có kết quả khác nhau từ hai zone**, và một VIP có thể do proxy trả lời mà không truyền request tới backend. Khi xây mục tiêu, phải quy định rõ **vị trí nguồn** và **điểm bằng chứng**, không suy “cả mạng đều an toàn” từ một phép thử thành công.

## 6. Chọn đối tượng đe dọa giả định và năng lực mô phỏng

Một kịch bản red team có ý nghĩa khi năng lực của đối tượng đe dọa giả định **phù hợp rủi ro thực tế** nhưng không vượt giới hạn an toàn.

| Hồ sơ giả định | Điểm bắt đầu có thể mô phỏng | Điều cần kiểm chứng |
| --- | --- | --- |
| Người dùng không tin cậy | Mạng GUEST hoặc Wi-Fi khách | Client isolation, firewall, NAC, portal access |
| Tài khoản nhà thầu đã được cấp | VPN test identity với quyền hạn cố định | Least privilege, zone segmentation, giám sát |
| Workload bị cấu hình sai | Pod/VM test trong vùng APP | Egress policy, microsegmentation và log |
| Sai sót quản trị nội bộ | Thay đổi cấu hình đã diễn tập trong lab | Change control, cảnh báo drift và khả năng rollback |
| Nguồn bên ngoài | Điểm quan sát Internet do tổ chức kiểm soát | Phơi lộ dịch vụ theo chủ trương, WAF/CDN protection |
| Bên trong một site bị sự cố | Tài khoản hoặc host giả định trong zone có giới hạn | Trust boundary và khả năng cô lập |

Không nên chọn giả định “có toàn quyền domain admin và có thể đọc mọi dữ liệu” nếu đó không phải điểm bắt đầu được thỏa thuận. Ngược lại, giả định quá yếu cũng khiến bài kiểm thử không kiểm chứng được rủi ro quan trọng.

### 6.1. Threat-informed nhưng không đồng nhất threat intelligence với sự thật

Có thể dựa trên **MITRE ATT&CK** để mô tả các nhóm hành vi dự kiến ở mức chiến thuật như Initial Access, Discovery, Lateral Movement, Command and Control hoặc Exfiltration, nhưng mỗi kỹ thuật phải được xét lại theo rủi ro, quyền và môi trường. ATT&CK là khung phân loại hành vi, **không phải giấy phép thực hiện kỹ thuật** hoặc danh sách hành động bắt buộc.

Kịch bản nên mô phỏng **tín hiệu kiểm thử an toàn** cho detection khi có thể. Ví dụ, để thử xem một luồng truy cập trái policy có được ghi log, chỉ cần sử dụng endpoint canary và danh tính test; không cần truy cập dữ liệu khách hàng hay thử lấy quyền quản trị thật.

## 7. Rules of Engagement: giới hạn quyền và trách nhiệm

**Rules of Engagement (RoE)** là tài liệu phê duyệt quy định **ai làm gì, từ đâu, trên hệ thống nào, lúc nào, bằng phương pháp nào, tới giới hạn nào và liên lạc với ai khi có sự cố**. Không có RoE hợp lệ thì không chạy mô phỏng trên hệ thống thật.

### 7.1. Nội dung RoE tối thiểu

1. **Ủy quyền:** chủ sở hữu hệ thống, sponsor, đơn vị được ủy quyền, phạm vi pháp lý/hợp đồng.
2. **Mục tiêu nghiệp vụ và giả thuyết:** những gì cần kiểm chứng, mức độ rủi ro ưu tiên.
3. **In-scope và exclusions:** IP, FQDN, cloud account, subnet, tenant, zone, tài khoản, dữ liệu và nhà cung cấp.
4. **Kỹ thuật và tương tác cho phép:** công cụ/loại probe, telemetry generation, tài khoản test, test marker.
5. **Hoạt động bị cấm:** gây gián đoạn, phá dữ liệu, thu thông tin thật, nhắm người không đồng ý, thay cấu hình production nếu không có quyền riêng.
6. **Giới hạn tải:** số host, request rate, concurrency, duration, dung lượng dữ liệu.
7. **Khung thời gian:** start/end UTC, maintenance window, lịch freeze hoặc change blackout.
8. **Thông báo và deconfliction:** đầu mối white cell, SOC/NOC, trực vận hành, kênh liên lạc khẩn cấp.
9. **Quy tắc dừng (kill switch):** ai có quyền dừng và trigger nào bắt buộc dừng.
10. **Bằng chứng và bảo mật dữ liệu:** log/PCAP, test marker, retention, mã hóa, quyền đọc, chain of custody.
11. **Phục hồi và đóng thử nghiệm:** reset test accounts, cleanup, kiểm chứng không còn tác động.
12. **Thay đổi phạm vi:** không mở rộng mục tiêu hoặc kỹ thuật chỉ bằng thỏa thuận miệng không được ghi nhận.

### 7.2. Mẫu RoE minh họa

~~~yaml
exercise_id: RT-NET-EXAMPLE-001
title: "Xác minh phân đoạn VPN nhà thầu"
environment: "staging"
sponsor: "Owner dịch vụ thanh toán (mô phỏng)"
white_cell_contact: "incident-coordinator@example.test"
time_window_utc:
  start: "2026-11-28T02:00:00Z"
  end: "2026-11-28T03:00:00Z"
source:
  asset: "rt-test-client-01"
  zone: "CONTRACTOR"
  identity: "vpn-contractor-test"
targets:
  - asset: "payment-canary-01"
    address: "192.0.2.20"
    approved_ports: [443]
allowed_actions:
  - "Kiểm thử kết nối an toàn, giới hạn tốc độ"
  - "Gửi request tới endpoint canary với test marker"
  - "Đối chiếu firewall, VPN, NDR và SOC logs"
prohibited_actions:
  - "Truy cập dữ liệu khách hàng"
  - "Thay đổi production firewall"
  - "Brute force, persistence và phá hủy dữ liệu"
stop_conditions:
  - "Error rate của dịch vụ tăng bất thường"
  - "On-call hoặc white cell yêu cầu dừng"
  - "Lưu lượng rời khỏi phạm vi phê duyệt"
deliverables:
  - "Timeline red/blue với UTC timestamp"
  - "Báo cáo gaps, bằng chứng và kế hoạch kiểm thử lại"
~~~

Các tên và địa chỉ trong mẫu chỉ để minh họa. **192.0.2.0/24 là dải tài liệu**, không phải mục tiêu quét hoặc mô phỏng thật. Một RoE vận hành phải có owner/approval thực, tài sản thuộc quyền kiểm soát và giới hạn cụ thể trước khi thực hiện.

## 8. Vai trò tổ chức: red, blue, white và purple

| Vai trò | Trách nhiệm | Không nên nhầm với |
| --- | --- | --- |
| **Executive sponsor / business owner** | Chấp thuận mục tiêu, mức chấp nhận rủi ro, thời gian và nguồn lực | Người trực tiếp chỉ đạo chi tiết kỹ thuật hàng phút |
| **Red team** | Thiết kế và thực hiện kịch bản trong RoE, lưu bằng chứng, báo cáo | Có toàn quyền hành động ngoài phạm vi |
| **Blue team / SOC** | Giám sát, phát hiện, điều tra, quyết định theo playbook | Bắt buộc biết trước toàn bộ chi tiết chiến thuật |
| **White cell / control team** | Nắm kế hoạch, phối hợp an toàn, phê duyệt tạm dừng/khôi phục, deconfliction | Đơn thuần là nhóm quan sát thụ động |
| **NOC / SRE / service owner** | Theo dõi sức khỏe, chịu trách nhiệm dịch vụ và xác nhận điều kiện dừng | Chỉ được liên hệ sau khi sự cố xảy ra |
| **Legal / privacy / compliance** | Xác nhận phạm vi pháp lý, quy định dữ liệu, bên thứ ba khi cần | Thay thế owner kỹ thuật |
| **Purple-team facilitator** | Kết nối phát hiện với kế hoạch cải tiến và retest | Bắt buộc mọi bài red team phải công khai từ đầu |

### 8.1. Mô hình thông tin có kiểm soát

- **Covert theo RoE:** blue team không biết thời điểm/chi tiết hành vi mô phỏng, nhưng white cell và đầu mối an toàn biết để tránh hiểu nhầm với sự cố thật.
- **Assumed breach:** diễn tập bắt đầu từ một danh tính hoặc workload test đã được chuẩn bị, không phải chứng minh cách xâm nhập ban đầu.
- **Collaborative/purple:** red và blue cùng quan sát để xây detection và phản ứng hiệu quả.

Mức độ bí mật là một biến của thiết kế bài tập, không phải lý do để bỏ qua phê duyệt hoặc giấu hoạt động gây nguy cơ cho production. White cell phải có quyền **dừng ngay** khi điều kiện an toàn xuất hiện.

## 9. Xác định mục tiêu kiểm thử theo các lớp phòng vệ mạng

| Lớp phòng vệ | Mục tiêu kiểm thử có ý nghĩa | Bằng chứng kỳ vọng |
| --- | --- | --- |
| **Segmentation/VLAN/VRF** | Zone ít tin cậy không đi tới đích nhạy cảm ngoài quyền | Matrix allow/deny, route và firewall logs |
| **Firewall/ACL/NAT** | Policy không bị bypass bởi đường được phép mô phỏng | Session decision, NAT mapping, config audit |
| **VPN và Zero Trust access** | Chỉ danh tính/thiết bị đủ điều kiện mới vào đúng tài nguyên | Auth logs, posture result, route và session |
| **IDS/IPS/NDR** | Những mẫu test đã định nghĩa có được phát hiện và chuyển xử lý | Alert ID, coverage, thời gian phát hiện |
| **DNS security** | Resolver, logging và policy có xử lý truy vấn mẫu đúng thiết kế | Resolver log, response, deny/allow |
| **Proxy/WAF/API gateway** | Request thử nghiệm đến đúng route, control ghi nhận và áp policy | Access log, rule/action, request ID |
| **Wi-Fi/NAC/802.1X** | Mạng khách bị giới hạn, thiết bị test đúng VLAN/identity | RADIUS/controller logs và segmentation result |
| **Cloud security** | Security group/NSG/NACL, egress và workload identity đúng cấu hình | Cloud audit, flow logs, policy snapshot |
| **Kubernetes/service mesh** | NetworkPolicy và mTLS/service auth phân tách workload | CNI/mesh logs, pod/service IDs và test results |
| **Monitoring/SIEM/SOC** | Alert đi đúng pipeline, phân loại/điều tra đúng playbook | Timeline, case ID, analyst notes, escalations |

Một bài red team không bắt buộc thử tất cả lớp. Nên chọn **các ranh giới trực tiếp liên quan mục tiêu nghiệp vụ** và ghi rõ những lớp chưa nằm trong bài, tránh gây ấn tượng rằng mọi lớp đều đã được chứng minh.

## 10. Thiết kế kịch bản có bằng chứng và điều kiện thắng

Mỗi kịch bản nên có:

- **Mã kịch bản và phiên bản:** để trace được lần chạy và thay đổi thiết kế.
- **Mục tiêu nghiệp vụ:** ví dụ bảo vệ dữ liệu thanh toán khỏi zone nhà thầu.
- **Preconditions:** tài khoản test, route, policy version, host, test marker và dữ liệu nền.
- **Điểm bắt đầu:** mô phỏng quyền hạn nào, ở zone nào.
- **Danh sách hành vi cho phép:** có giới hạn, tác động được dự đoán và kiểm soát.
- **Controls kiểm chứng:** firewall deny, NDR alert, SOC response, IAM policy.
- **Success/failure criteria:** định nghĩa trước thay vì chọn sau khi nhìn kết quả.
- **Evidence plan:** loại log và thời gian từ red/blue/white; vị trí capture, retention.
- **Safety gates:** điều kiện dừng, rollback và quyền ra quyết định.
- **Cleanup:** thu hồi test identity, xóa tài nguyên giả, xác nhận cấu hình không đổi ngoài ý định.

### 10.1. Điều kiện thành công phải phân biệt theo phía

| Khía cạnh | Bằng chứng về kiểm soát hiệu quả | Bằng chứng về khoảng trống |
| --- | --- | --- |
| Prevention | Policy từ chối attempt không được phép | Attempt chạm được canary trái kỳ vọng |
| Detection | Alert có mốc thời gian, context và ưu tiên phù hợp | Không có tín hiệu dù telemetry được cấu hình để thu |
| Triage | Analyst liên hệ đúng asset, nguồn và đích | Nhận sai tài sản hoặc bỏ qua alert |
| Response | Escalation và xử lý đúng playbook trong mục tiêu thời gian | Không phân loại/escalate hoặc xử lý gây gián đoạn ngoài ý định |
| Recovery | Có thể kết thúc test, đóng tài khoản, trả hệ thống về baseline | Còn test account, rule hoặc tài nguyên chưa dọn |

**Không thấy alert không tự chứng minh IDS/NDR “vô dụng”**. Cần kiểm tra cảm biến có nhìn thấy flow, rule có được bật, log pipeline có mất sự kiện, thời gian ingest và kịch bản có nằm trong mục tiêu detection đã thống nhất hay không.

### 10.2. Dừng tại bằng chứng đủ thay vì đẩy tới rủi ro cao

Nếu mục tiêu là xác minh một đường truy cập trái policy, có thể dùng **endpoint canary, test identity và test marker** để chứng minh ranh giới có hay không được áp dụng. Không cần đọc dữ liệu khách hàng hoặc tạo persistence để hoàn thành mục tiêu. Khi đã có bằng chứng đủ, dừng hành động và chuyển sang phân tích cùng blue team.

## 11. Bằng chứng phải có: network telemetry và timeline

Trước khi chạy, xác định nguồn dữ liệu và trách nhiệm lưu:

| Nguồn | Điều có thể xác nhận | Giới hạn |
| --- | --- | --- |
| Firewall/NAT/session logs | Allow/deny, zone, policy, original/translated tuple | Chỉ tại thiết bị có log |
| VPN/identity logs | Test user, device identity, tunnel, auth/policy outcome | Không tự chứng minh quyền ứng dụng |
| DNS/resolver logs | Query, answer, RCODE, TTL và resolver | Query không chứng minh connection |
| PCAP ở hai phía ranh giới | Có packet tại ingress/egress và mốc TCP/UDP | TLS mã hóa, sai interface hoặc capture drop |
| Proxy/WAF/API logs | Request, route, status, upstream, request ID | Chỉ khi đã nhận request; proxy có thể tạo kết nối mới |
| IDS/NDR/SIEM | Alert/correlation và timestamp | Có thể trễ, sampling hoặc rule chưa bật |
| Endpoint/EDR | Test process/asset, socket, identity | Nguồn tại host có thể thiếu event |
| Cloud/CNI/mesh logs | Policy decision, workload và route liên quan | Tài sản động, flow log aggregation |
| SOC case/playbook logs | Triage, escalation, containment decision | Quy trình có thể chưa được kích hoạt nếu alert không đủ điều kiện |

### 11.1. Timeline nên chuẩn hóa UTC

~~~text
02:00:00 UTC  WHITE  Bắt đầu bài test đã được duyệt, xác nhận healthy baseline
02:02:10 UTC  RED    Gửi request thử nghiệm tới canary từ VPN test identity
02:02:10 UTC  VPN    Ghi nhận session và identity nguồn
02:02:11 UTC  FW     Ghi nhận quyết định deny theo policy đã thiết kế
02:02:12 UTC  NDR    Event chuyển đến collector
02:02:17 UTC  SIEM   Alert được tạo và có asset context
02:05:00 UTC  BLUE   Analyst triage và phân loại test artifact
02:12:00 UTC  WHITE  Xác nhận hoàn tất kịch bản, yêu cầu cleanup
~~~

Đây chỉ là timeline minh họa. Cần ghi **thời gian sự kiện và thời gian ingest**, sự sai lệch đồng hồ, người thu log, raw event/case ID và những khoảng không quan sát được. Một firewall deny không chứng minh ở mọi đường khác đều không có route; một alert được tạo không đồng nghĩa analyst đã nhìn thấy hoặc xử lý kịp.

## 12. Tiêu chí đo lường hiệu quả

Để đánh giá khả năng phòng vệ, chọn các chỉ số phù hợp **với kịch bản**, không chỉ đếm số lỗ hổng tìm được.

| Chỉ số | Định nghĩa thực hành | Lưu ý |
| --- | --- | --- |
| Objective completion | Mục tiêu red hoặc mục tiêu blue đạt theo tiêu chí nào | Ghi cả các phần không thử vì RoE |
| Prevention coverage | Những đường kiểm thử đã được kiểm soát đúng policy | Chỉ là mẫu được thử, không phải toàn bộ đường mạng |
| Detection coverage | Sự kiện thử có tín hiệu ở đúng sensor/SIEM không | Cần xác minh điểm nhìn và log ingest |
| Time to detect | Thời gian từ **event được định nghĩa** đến alert có thể sử dụng | Quy định mốc bắt đầu và kết thúc rõ |
| Time to triage | Từ alert đến analyst đánh giá có căn cứ | Không đồng nhất với time to respond |
| Time to respond | Từ sự kiện/quyết định tới hành động ứng phó xác minh được | Các tình huống cần phê duyệt có thời gian riêng |
| Time to recover | Từ khi ảnh hưởng bắt đầu đến dịch vụ đạt tiêu chí phục hồi | Có thể không áp dụng bài không gây gián đoạn |
| Telemetry completeness | Những trường/log cần thiết có được thu không | Tránh đếm số log mà quên tính đúng |
| False positive / false negative | Sự kiện nào bị báo sai hoặc bỏ sót theo ground truth | Cần tập dữ liệu và định nghĩa nhãn rõ |
| Repeatability | Kịch bản có thể được tái chạy với điều kiện tương đương không | Hạ tầng cloud/policy có thể thay đổi |

**Một kịch bản bị chặn không chứng minh hệ thống an toàn tuyệt đối**; một kịch bản không bị phát hiện chưa chứng minh mọi quy trình ứng phó thất bại. Giới hạn thời gian, số mẫu, visibility và kỹ thuật cho phép phải xuất hiện trong báo cáo.

### 12.1. Đo đúng thời gian phát hiện

Nếu hành động test diễn ra 02:02:10, event được sensor ghi lúc 02:02:12, SIEM tạo alert lúc 02:02:17, thì cần phân biệt **sensor detection latency**, **pipeline ingestion/alert latency** và **analyst triage latency**. Không trộn các mốc khác nhau thành một con số MTTD không có định nghĩa.

## 13. Quy trình thực hiện có các cổng kiểm soát

~~~mermaid
flowchart TD
    A[Rủi ro và mục tiêu nghiệp vụ] --> B[Threat model và giả thuyết kiểm thử]
    B --> C[Xác định tài sản, dữ liệu, zone và kỹ thuật]
    C --> D{RoE / owner / white cell phê duyệt?}
    D -->|Không| X[Không thực hiện: cập nhật kế hoạch]
    D -->|Có| E[Baseline, health, logging và test accounts]
    E --> F[Thực hiện từng hành động giới hạn]
    F --> G{Vượt phạm vi hoặc có tác động?}
    G -->|Có| H[Dừng, thông báo và bảo toàn bằng chứng]
    G -->|Không| I[Thu log, xác minh mục tiêu và điều kiện thắng]
    I --> J[Cleanup và xác nhận trạng thái]
    J --> K[Red/blue debrief và remediation]
    K --> L[Retest theo phạm vi được duyệt]
~~~

### 13.1. Trước khi chạy

1. Có sponsor, hệ thống owner và RoE **đã được phê duyệt**.
2. Hoàn tất inventory và xác định tài sản/các bên thứ ba.
3. Kiểm tra backup/configuration baseline và cơ chế rollback trong trường hợp tác động ngoài ý định.
4. Xác định test identities, test canary, log sources, time sync và kênh điều phối.
5. NOC/SRE/white cell chốt ngưỡng dừng và tình trạng khỏe ban đầu của dịch vụ.
6. Tài liệu hóa phạm vi tiết lộ thông tin cho blue team.

### 13.2. Khi chạy

Chỉ triển khai hành vi thuộc danh sách đã duyệt; thực hiện từng bước có kiểm tra tác động; không mở rộng nguồn, đích hoặc kỹ thuật dựa trên phát hiện tình cờ. Nếu có bất thường về CPU, latency, packet loss, auth lockout hoặc cảnh báo sản xuất, dừng theo RoE và báo white cell. Quy tắc dừng có **ưu tiên cao hơn mục tiêu hoàn thành diễn tập**.

### 13.3. Sau khi chạy

Xác minh cleanup: test accounts, access grants, temporary policies, test markers, VMs/pods, DNS entries và telemetry routing đều trở lại trạng thái dự kiến. Ghi nhận nếu có một điều kiện dừng khiến kịch bản không hoàn tất; đây là kết quả hợp lệ cần báo cáo, không phải lý do bỏ qua quy trình.

## 14. Tình huống minh họa: xác minh ranh giới nhà thầu và mạng thanh toán

### 14.1. Bối cảnh

Một doanh nghiệp có hai vùng mạng:

- **CONTRACTOR:** mạng dành cho đối tác truy cập qua VPN, chỉ được đi tới dịch vụ hỗ trợ được chỉ định.
- **PAYMENT:** vùng xử lý giao dịch được bảo vệ bởi firewall, API gateway và chính sách identity.

Giả thuyết kiểm thử: nếu một tài khoản test mang profile nhà thầu cố truy cập **endpoint canary** trong PAYMENT qua đúng luồng được phê duyệt, firewall và policy sẽ từ chối; NDR/SIEM ghi nhận và SOC có khả năng phân loại.

~~~text
Test client (CONTRACTOR)
     |
     v
VPN test identity
     |
     v
Firewall CONTRACTOR -> PAYMENT
     |     (kỳ vọng: deny và audit)
     v
Payment canary: 192.0.2.20:443

Nguồn chứng cứ:
  VPN auth/session + firewall rule + flow log + NDR/SIEM + SOC case
~~~

Canary là endpoint thử nghiệm, không phải cơ sở dữ liệu thanh toán thật. Địa chỉ 192.0.2.20 là IP tài liệu; khi áp dụng trong lab phải thay bằng tài sản thuộc phạm vi được duyệt.

### 14.2. Mục tiêu và ràng buộc

| Mục | Thiết kế bài tập |
| --- | --- |
| Mục tiêu | Xác nhận không vượt ranh giới CONTRACTOR → PAYMENT |
| Mô phỏng | Một tài khoản VPN nhà thầu test với quyền hạn hạn chế |
| Tài sản đích | Payment canary chỉ chứa test marker |
| Kỹ thuật | Kiểm tra kết nối đơn giản, số lần thử giới hạn |
| Bị cấm | Xác thực brute-force, truy cập data thật, privilege escalation, persistence |
| Thành công phòng vệ | Deny đúng policy; log và triage có đủ context |
| Điểm quan sát | VPN session, firewall logs, NDR, SIEM, canary access log |
| Dừng | Tải tăng, lỗi production, white cell yêu cầu, phạm vi bị vượt |

### 14.3. Kết quả giả định và cách đọc

| Quan sát | Nguồn | Diễn giải |
| --- | --- | --- |
| VPN chấp nhận test identity trong zone CONTRACTOR | VPN log | Có phiên test đúng giả định |
| Firewall ghi deny đối với 192.0.2.20:443 | Firewall policy/session log | Ranh giới được áp dụng tại điểm đó |
| Canary không ghi nhận request phù hợp | Canary log | Phù hợp với deny, nhưng cần kiểm tra log coverage |
| NDR ghi nhận attempt, SIEM tạo alert | NDR/SIEM | Pipeline có tín hiệu cho mẫu kiểm thử |
| SOC không triage trong ngưỡng mục tiêu | SOC case/timeline | Khoảng trống quy trình hoặc ưu tiên cần xem |

**Kết luận phù hợp:** “Trong cửa sổ và luồng kiểm thử được phê duyệt, firewall ngăn được kết nối từ CONTRACTOR tới canary, NDR/SIEM phát tín hiệu, nhưng quy trình triage chưa đạt mục tiêu thời gian.” Điều này **không** có nghĩa mọi đường từ CONTRACTOR tới PAYMENT đều đã được kiểm chứng hoặc đe dọa thực bị chặn trong mọi tình huống.

### 14.4. Hành động cải tiến

- Kiểm tra độ đầy đủ của audit log, zone/identity context và việc gán case.
- Điều chỉnh rule correlation, ưu tiên cảnh báo hoặc playbook nếu có bằng chứng khoảng trống.
- Rà soát các ranh giới tương tự theo risk-based backlog, không tự động mở rộng scan.
- Dùng cùng kịch bản và điều kiện tương đương để retest sau thay đổi.
- Ghi version policy trước/sau và kết quả cả **positive** lẫn **negative** test nếu được phép.

## 15. Đảm bảo an toàn và bảo vệ dữ liệu trong diễn tập

### 15.1. Dữ liệu và chứng cứ

Ưu tiên tài khoản test, tài nguyên canary và test marker không nhạy cảm. Khi mô phỏng sự kiện liên quan dữ liệu, dùng **dữ liệu tổng hợp** và bằng chứng từ logs thay vì tải dữ liệu cá nhân, credential thực hoặc tài liệu nội bộ. PCAP có thể chứa cookie, token, IP nội bộ và payload; phải giới hạn phạm vi, mã hóa, phân quyền và retention.

Ghi raw event ID, time UTC, sensor, phương thức thu, filter, clock skew và các điều chưa được quan sát. Nếu có yêu cầu pháp chứng, bảo quản bản gốc và hash, phân tích trên bản sao, ghi lịch sử chuyển giao theo quy trình tổ chức.

### 15.2. Ngăn tác động dây chuyền

Phải xem xét các phụ thuộc cùng hạ tầng: một bài test nhỏ có thể kích hoạt IDS/IPS block, account lockout, WAF rate limiting, autoscaling hoặc cảnh báo đến nhà cung cấp bên thứ ba. Cần giới hạn concurrency/request rate, có kênh báo SOC/NOC và xác định trước ngưỡng stop. Không cố tiếp tục hoặc né kiểm soát khi bị chặn ngoài dự kiến.

### 15.3. Xử lý khi phát hiện vấn đề thật

Nếu gặp dấu hiệu xâm nhập thật hoặc hệ thống ngoài phạm vi:

1. Dừng phần hoạt động có thể tác động hoặc vượt quyền.
2. Bảo toàn sự kiện và bằng chứng đã thu được theo RoE.
3. Báo white cell/incident commander hoặc owner qua kênh đã chỉ định.
4. Không tự ý mở rộng điều tra hoặc khai thác thêm bằng quyền của bài diễn tập.
5. Phân biệt rõ **incident thật** với **test traffic** trong báo cáo và log coordination.

## 16. Báo cáo kết quả và truyền đạt cho các bên

Một báo cáo tốt không chỉ liệt kê hành động đã thử, mà thể hiện mối liên hệ giữa **rủi ro – mục tiêu – bằng chứng – kết luận – kế hoạch cải tiến**.

### 16.1. Các phần cần có

| Phần | Nội dung tối thiểu |
| --- | --- |
| Executive summary | Mục tiêu, kết quả chính, ảnh hưởng nghiệp vụ và ưu tiên cải tiến |
| Scope và RoE | Phạm vi, exclusions, phiên bản approval, thời gian, phương pháp |
| Threat model | Điểm bắt đầu, giả định về quyền và ranh giới được thử |
| Scenario timeline | Mốc UTC, red actions, sensor alerts, blue response, white decisions |
| Evidence | Raw IDs, policy snapshots, request markers, log/PCAP references |
| Findings | Kiểm soát hiệu quả, khoảng trống, tác động có căn cứ, độ tin cậy |
| Limitations | Không đủ coverage, stop condition, không thử kỹ thuật ngoài phạm vi |
| Remediation | Owner, priority, thay đổi dự kiến, test chấp nhận |
| Retest | Bài kiểm thử lặp lại, điều kiện so sánh, kết quả trước/sau |
| Cleanup/closure | Test account/marker được thu hồi, trạng thái hệ thống an toàn |

### 16.2. Ví dụ mẫu phát hiện

~~~text
Finding ID: RT-NET-001
Mục tiêu: Xác minh phân đoạn CONTRACTOR -> PAYMENT
Mức độ ảnh hưởng nghiệp vụ: Cao nếu kiểm soát thất bại

Đã kiểm chứng:
  - VPN xác thực test account vào zone CONTRACTOR
  - Firewall ghi deny đối với endpoint canary được chọn
  - NDR và SIEM ghi nhận sự kiện kiểm thử tương ứng
  - Triage của SOC chưa đạt thời gian mục tiêu đã thống nhất

Chưa kiểm chứng:
  - Các đường giao tiếp khác tới PAYMENT
  - Các dạng giao thức chưa nằm trong phạm vi
  - Khả năng xử lý một đe dọa thật ngoài kịch bản giả định

Kết luận:
  - Prevention đạt cho luồng đã thử
  - Detection có hoạt động
  - Cần cải tiến triage theo playbook

Kiến nghị:
  - Rà soát rule ưu tiên và context mapping
  - Phân công SOC owner kiểm chứng
  - Retest cùng trường hợp sau thay đổi
~~~

Mức độ nghiêm trọng của phát hiện phải phản ánh tác động nghiệp vụ và bằng chứng; không nên coi mọi thiếu sót về timestamp/log là mức nghiêm trọng cao, cũng không nên hạ thấp một đường truy cập trái phép chỉ vì chưa khai thác thêm.

## 17. Những sai lầm thường gặp khi định nghĩa mục tiêu và phạm vi

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Đề bài chỉ là “hack nội bộ” | Không có mục tiêu đo được, dễ vượt phạm vi | Bắt đầu từ rủi ro nghiệp vụ và giả thuyết |
| Scope chỉ ghi một dải IP | Bỏ qua identity, zone, dữ liệu, kỹ thuật, thời gian | Ma trận scope nhiều chiều |
| Chủ sở hữu domain được hiểu là sở hữu mọi IP CDN | Tác động bên thứ ba hoặc vượt quyền | Xác minh ownership và điều kiện nhà cung cấp |
| Không có white cell/đầu mối dừng | Khó phân biệt sự cố thật với test, phản ứng chậm | Có control team và kênh khẩn cấp |
| Đặt mục tiêu “chiếm quyền tối đa” | Dẫn tới hành vi nguy cơ cao không cần thiết | Dùng canary, test marker và điểm dừng theo bằng chứng đủ |
| Không xét hạ tầng cloud/kubernetes động | IP/workload thay đổi, log ghép nhầm | Dùng instance ID, pod UID, policy snapshot |
| Tắt IDS/IPS để dễ mô phỏng | Không còn đánh giá thực tế lớp phòng vệ | Giữ controls hoạt động và điều chỉnh theo RoE nếu thật sự cần |
| Chỉ tính “red thành công” | Bỏ sót khả năng phát hiện, triage, response | Đo prevention/detection/response riêng |
| Không xác nhận sensor coverage | Hiểu nhầm “không alert” là không có phòng vệ | Kiểm tra log pipeline, interface và sampling |
| Ghi kết luận bao trùm từ một luồng thử | Khẳng định quá mức về toàn mạng | Ghi giới hạn theo source, time và protocol |
| Không có cleanup | Tồn tại account, marker, cấu hình test ngoài ý muốn | Bắt buộc checklist closure |
| Không retest sau cải tiến | Không biết thay đổi có hiệu quả | Lặp kịch bản trong điều kiện tương đương |

## 18. Checklist thiết kế một bài network red team

- [ ] Có business sponsor và hệ thống owner phê duyệt mục tiêu dựa trên rủi ro.
- [ ] Phân biệt rõ red team với pentest, vulnerability scan, BAS và tabletop.
- [ ] Có giả thuyết, điều kiện thắng và bằng chứng chấp nhận được cho mỗi mục tiêu.
- [ ] Xác định điểm bắt đầu, danh tính thử nghiệm, vùng mạng, tuyến truy cập và tài sản đích.
- [ ] Scope ghi đủ IP/FQDN, cloud tenant, protocol, port, tài khoản, dữ liệu, thời gian và kỹ thuật.
- [ ] Có danh sách OUT_OF_SCOPE, CONDITIONAL_SCOPE và bên thứ ba cần cho phép riêng.
- [ ] Đã vẽ trust boundaries và kiểm tra NAT, VPN, firewall, proxy, DNS, Wi-Fi và cloud path liên quan.
- [ ] RoE xác định giới hạn tải, hành vi cấm, điều kiện dừng và người có quyền yêu cầu dừng.
- [ ] Có white cell, NOC/SRE, SOC/blue và kênh phối hợp khẩn cấp.
- [ ] Dùng canary, test marker, synthetic data và ít thao tác nhất đủ để tạo bằng chứng.
- [ ] Có baseline dịch vụ, monitoring health và khả năng rollback/cleanup.
- [ ] Evidence plan định nghĩa raw logs, PCAP/flow, VPN/identity, NDR/SIEM và UTC timestamps.
- [ ] Kết quả đo riêng prevention, detection, triage/response và recovery khi áp dụng.
- [ ] Báo cáo nêu rõ tài sản đã thử, tài sản chưa thử, bằng chứng, giả thuyết và độ tin cậy.
- [ ] Có action owner, remediation, retest và xác nhận xóa test accounts/resources sau diễn tập.

**Điểm cốt lõi:** một bài **network red team** được thiết kế tốt không bắt đầu từ câu hỏi “dùng kỹ thuật tấn công nào?” mà từ **rủi ro nào cần được kiểm chứng, ranh giới nào có thể thử an toàn, những bằng chứng nào xác nhận khả năng phòng vệ và ai chịu trách nhiệm khi điều kiện thay đổi**. Mục tiêu và phạm vi được định nghĩa chặt chẽ giúp diễn tập phản ánh năng lực bảo vệ mạng, phát hiện và ứng phó mà không tạo thêm rủi ro không cần thiết cho hệ thống đang vận hành.
