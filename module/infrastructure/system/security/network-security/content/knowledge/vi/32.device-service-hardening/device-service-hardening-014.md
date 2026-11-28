# Cấu hình fail-safe khi thiết bị gặp lỗi

## 1. Mục tiêu của fail-safe trong hardening thiết bị và dịch vụ mạng

Một thiết bị mạng có thể gặp lỗi phần cứng, mất nguồn, quá tải CPU, treo tiến trình, hết bộ nhớ, mất kết nối tới máy chủ xác thực, lỗi đường truyền hoặc nhận cấu hình sai. Nếu hệ thống chỉ được thiết kế để hoạt động khi mọi thành phần khỏe mạnh, lỗi của một phần tử có thể làm gián đoạn dịch vụ, làm mất kiểm soát bảo mật hoặc vô tình mở đường truy cập trái phép.

**Fail-safe** là nguyên tắc thiết kế để khi một thành phần hỏng hoặc không thể xác định trạng thái, toàn hệ thống chuyển sang **trạng thái đã định nghĩa trước, được đánh giá là an toàn đối với mục tiêu cần bảo vệ**. Trong an ninh mạng, trạng thái an toàn có thể là **từ chối một luồng truy cập**, **duy trì các kiểm soát bảo mật qua thiết bị dự phòng** hoặc **chỉ cung cấp chức năng tối thiểu có kiểm soát**. Không có một chế độ duy nhất phù hợp cho mọi thiết bị.

Đây là một chủ đề trong **Hardening thiết bị và dịch vụ mạng** của module **SECURITY_NETWORK_SECURITY**. Kiến thức về phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, xác thực kết nối, mạng không dây, cloud, giám sát xâm nhập và thiết kế kiến trúc bảo mật đều cần được vận dụng khi chọn trạng thái an toàn lúc xảy ra lỗi.

Ví dụ:

- Firewall biên ngừng hoạt động: nếu **cho phép mọi lưu lượng đi qua**, dịch vụ có thể tiếp tục nhưng ranh giới bảo vệ bị mất.
- Hệ thống NAC không liên lạc được RADIUS: nếu **mọi thiết bị đều được cấp VLAN nội bộ**, một sự cố xác thực biến thành lỗ hổng kiểm soát truy cập.
- Cặp firewall HA có cấu hình và phiên đồng bộ đầy đủ: thiết bị dự phòng có thể tiếp quản đường truyền, **vẫn thực thi chính sách** và giảm thời gian gián đoạn.
- VPN gateway mất IdP: việc chấp nhận mọi đăng nhập để duy trì khả dụng là không an toàn; phương án dự phòng phải giữ được **cơ chế xác thực đáng tin**.
- DNS resolver bị lỗi: có thể chuyển sang resolver thứ hai với cùng chính sách bảo vệ, thay vì tự động gửi truy vấn nhạy cảm đến DNS công cộng không được phê duyệt.

**Mục tiêu học tập:** hiểu các chế độ fail-open/fail-closed/fail-secure, lựa chọn trạng thái lỗi cho từng loại thiết bị, thiết kế HA và đường dự phòng, cấu hình có kiểm soát, kiểm tra chuyển đổi và xây dựng quy trình vận hành/rollback.

## 2. Phân biệt fail-safe, fail-secure, fail-open, fail-closed và failover

Những thuật ngữ này liên quan nhưng không đồng nghĩa.

| Thuật ngữ | Ý nghĩa | Ví dụ | Điểm cần lưu ý |
|---|---|---|---|
| **Fail-safe** | Khi lỗi, hệ thống chuyển về trạng thái an toàn theo mục tiêu rủi ro đã chọn | Khi bộ kiểm soát xác thực lỗi, cổng quản trị không chấp nhận phiên không được xác thực | “An toàn” phải được định nghĩa theo ngữ cảnh |
| **Fail-secure** | Ưu tiên không phá vỡ biên bảo mật, chính sách quyền và tính bí mật/toàn vẹn khi lỗi | Firewall lỗi không tự bật bypass qua phân đoạn nhạy cảm | Có thể giảm tính sẵn sàng |
| **Fail-closed** | Không cấp quyền hoặc không cho luồng đi qua khi không xác minh được điều kiện cần thiết | Không mở phiên VPN mới nếu không thể kiểm tra danh tính | Thường phù hợp với truy cập đặc quyền, dữ liệu nhạy cảm |
| **Fail-open** | Bỏ qua một bước kiểm soát khi chính bước đó lỗi, để duy trì hoạt động | Inline IPS chuyển sang hardware bypass khi mất nguồn | Giữ khả dụng nhưng có thể mất khả năng kiểm tra/chặn |
| **Failover** | Chuyển chức năng sang thành phần hoặc tuyến dự phòng | Active firewall hỏng, standby nhận VIP/route và chính sách | Chỉ bảo toàn an ninh nếu thành phần dự phòng cũng áp dụng kiểm soát |
| **Fail-static / giữ trạng thái cuối** | Giữ cấu hình/trạng thái đã biết khi mất bộ điều khiển | Thiết bị chuyển tiếp giữ policy cuối được lập trình | Có rủi ro policy cũ hoặc hết hiệu lực; phải có giới hạn và cơ chế phục hồi |
| **Degraded mode** | Tiếp tục cung cấp chức năng bị giới hạn để kiểm soát rủi ro | Chỉ cho phép cổng cứu hộ/giám sát; tạm ngừng dịch vụ không thiết yếu | Cần phân quyền, giới hạn thời gian, logging và xác định người quyết định |

**Fail-open không có nghĩa là fail-safe trong mọi tình huống.** Đối với hệ thống an ninh, fail-open có thể chính là trạng thái **không an toàn**. Ngược lại, trong một hệ thống mà mất kết nối gây nguy hiểm đến con người, yêu cầu an toàn vật lý có thể ưu tiên duy trì một luồng liên lạc khẩn cấp. Cách xử lý đúng phải dựa trên đánh giá nguy cơ cụ thể, không áp dụng khẩu hiệu “luôn fail-closed”.

Một hệ thống còn có thể **fail-closed ở luồng quản trị** nhưng **failover giữ thông suốt lưu lượng sản xuất**. Điều đó chỉ có nghĩa là thiết kế có nhiều lớp quyết định riêng, không có mâu thuẫn.

### Ba mặt phẳng cần xét riêng

1. **Data plane:** gói tin có còn được chuyển tiếp, có đi qua kiểm soát an ninh, có bị mất phiên NAT hoặc rơi route?
2. **Control plane:** routing adjacency, HA heartbeat, DNS/AAA signaling, policy controller, chứng chỉ và trạng thái xác thực có còn hoạt động?
3. **Management plane:** người vận hành có còn kênh SSH/HTTPS/console/OOB được bảo vệ để khắc phục lỗi mà không mở rộng quyền truy cập?

Ví dụ firewall còn chuyển tiếp gói nhưng controller chính sách bị mất liên lạc. Nếu thiết bị giữ “last known good policy”, data plane có thể tiếp tục an toàn trong thời hạn nhất định; nhưng cần phát hiện policy drift, hết hạn khóa/chứng chỉ và mất khả năng cập nhật quy tắc mới.

## 3. Chọn trạng thái an toàn theo CIA và mức độ rủi ro

Ba thuộc tính bảo mật thường phải cân đối là **Confidentiality (bí mật)**, **Integrity (toàn vẹn)** và **Availability (sẵn sàng)**.

- Với **biên bảo mật chứa dữ liệu hoặc quyền quan trọng**, việc mở truy cập không xác thực có thể gây thiệt hại lớn hơn gián đoạn ngắn. Ưu tiên fail-closed hoặc failover sang tuyến vẫn áp dụng policy.
- Với **dịch vụ vận hành quan trọng**, gián đoạn có thể gây hậu quả nghiêm trọng. Ưu tiên HA, dự phòng nhiều lớp, chế độ suy giảm tối thiểu và các kênh phục vụ khẩn cấp đã được kiểm soát.
- Với **kiểm soát phát hiện không nằm trên đường truyền**, việc sensor mất kết nối không nhất thiết phải cắt lưu lượng; cần cảnh báo “mất khả năng quan sát” và bù đắp bằng telemetry khác.
- Với **hệ thống an toàn vận hành/OT**, trạng thái khi lỗi phụ thuộc phân tích an toàn theo hệ thống và nhà sản xuất; không tự áp chính sách của mạng văn phòng lên điều khiển công nghiệp.

### Ma trận quyết định minh họa

| Tài sản hoặc chức năng | Rủi ro khi cho qua không kiểm soát | Rủi ro khi ngắt dịch vụ | Hướng mặc định để đánh giá |
|---|---|---|---|
| Firewall phân đoạn DB/sản xuất | Truy cập trái phép tài sản nhạy cảm | Dừng giao dịch/ứng dụng | HA thực thi cùng policy; fail-closed nếu không còn biên bảo vệ |
| Firewall internet cho hệ thống phổ thông | Expose toàn bộ dịch vụ nội bộ | Mất truy cập Internet | HA/đa tuyến; không tự chuyển thành “allow any” |
| Inline IPS trước dịch vụ có yêu cầu sẵn sàng cao | Mất ngăn chặn exploit khi bypass | Ngắt ứng dụng nếu inline box treo | Chọn bypass/closed theo risk acceptance; có kiểm soát bù đắp |
| IDS passive / log collector | Mất telemetry | Thường không gây đứt tuyến data plane | Tiếp tục data plane, cảnh báo và khôi phục giám sát |
| NAC cho thiết bị nội bộ | Thiết bị lạ truy cập VLAN tin cậy | Thiết bị hợp lệ bị ngắt | RADIUS dự phòng; restricted/critical VLAN theo thiết kế; không cấp full access |
| VPN/SSO/IdP | Chấp nhận danh tính giả hoặc phiên mới không đủ kiểm tra | Người dùng không truy cập từ xa | IdP dự phòng, phiên đã xác thực theo policy; fail-closed với login mới chưa xác minh |
| DNS resolver/forwarder | Rò rỉ truy vấn, bypass DNS filtering | Ứng dụng mất phân giải tên | Resolver dự phòng cùng policy; hạn chế fallback không được phê duyệt |
| Hệ thống quản trị mạng | Ai cũng có thể cấu hình thiết bị | Khó khôi phục khi lỗi | OOB, break-glass có bảo vệ, không bỏ xác thực |
| Mạng guest/Wi-Fi khách | Khách đi vào mạng nội bộ | Khách mất Internet | Guest isolation vẫn hiệu lực; từ chối hoặc restricted access |
| Kênh liên lạc an toàn sinh mạng | Có thể truy cập thiếu kiểm soát | Mất liên lạc có thể gây nguy hiểm | Phân tích safety chuyên biệt và phê duyệt chế độ khẩn cấp |

Câu hỏi quyết định không phải chỉ là “thiết bị có tiếp tục chuyển gói không?”, mà là **“chuyển gói nào, theo chính sách nào, vào những vùng nào, trong bao lâu, với bằng chứng gì?”**.

## 4. Phân tích lỗi trước khi cấu hình

Thiết kế fail-safe bắt đầu bằng nhận diện **failure mode** chứ không bằng bật một tùy chọn vendor.

| Kịch bản lỗi | Dấu hiệu | Tác động nếu không thiết kế | Biện pháp cần xem xét |
|---|---|---|---|
| Mất điện toàn thiết bị | Link down, mất heartbeat, mất nguồn telemetry | Mất kết nối, có thể kích hoạt hardware bypass | Nguồn dự phòng/UPS, HA, kiểm soát bypass |
| Treo data plane hoặc quá tải | Interface còn up nhưng không chuyển gói đúng | Blackhole traffic, gián đoạn kéo dài | Health probe xuyên đường truyền, khả năng failover dựa trên datapath |
| Mất control plane/routing | Adjacency down, route rút hoặc route stale | Lưu lượng sai tuyến, blackhole/asymmetric path | Routing redundancy, giới hạn giữ route, policy khi adjacency mất |
| Mất heartbeat HA | Hai node không thấy nhau | Split-brain, tranh chấp IP/MAC hoặc cùng active | Quorum/fencing, nhiều kênh heartbeat độc lập, điều kiện bầu active |
| Mất đồng bộ state | Phiên NAT/VPN/session không được copy | Failover làm rớt phiên đã thiết lập | Stateful HA/HA state sync nếu nền tảng hỗ trợ, bài test phục hồi phiên |
| Hết hạn cert/key hoặc lỗi NTP | TLS/AAA/VPN fail, log thời gian sai | Auth lỗi hoặc cấu hình bất an nếu bỏ xác minh | Đồng bộ thời gian, rotation, giám sát hạn, phương án xác thực dự phòng an toàn |
| Mất DNS/AAA/IdP | Timeout, auth fail, resolution fail | Đứt dịch vụ hoặc bypass quyền | Replica/secondary cùng policy, giới hạn cache, fail-closed khi cần |
| Sai rule do triển khai | Lockout management, deny/allow sai | Mất vận hành hoặc mở biên không chủ ý | Canary, commit-confirmed/auto rollback nếu hỗ trợ, OOB |
| Controller/Cloud API không sẵn sàng | Không phát hành policy mới | Policy drift, instance/workload mới nhận trạng thái mơ hồ | Pre-provisioned policy, last known good có điều kiện, alert và rollback |
| Đứt kết nối giám sát | Log/heartbeat không tới SIEM | Mù phát hiện nhưng dịch vụ vẫn chạy | Cảnh báo độ bao phủ, buffer log, nguồn giám sát độc lập |

**Lỗi một thành phần không được làm mọi biên bảo mật đổ theo.** Cần xác định thiết bị nào *fail-open được phép*, luồng nào *phải fail-closed* và yếu tố nào dùng **dự phòng** để tránh buộc phải chọn giữa bảo mật và tính sẵn sàng.

### FMEA rút gọn

Có thể dùng bảng phân tích chế độ lỗi và hậu quả (*Failure Mode and Effects Analysis*):

| Thành phần | Lỗi | Hậu quả | Tác động | Cách phát hiện | Trạng thái an toàn | Phương án khôi phục |
|---|---|---|---|---|---|---|
| Firewall HA A | Treo packet processing | Mất luồng qua A | Cao | Probe xuyên data plane | B tiếp quản policy | Khôi phục A sau root cause |
| IPS inline | Mất nguồn | Ngắt link hoặc bypass | Theo luồng | Link/health + alert out-of-band | Theo quyết định được phê duyệt | Đưa IPS dự phòng vào tuyến |
| RADIUS 1 | Timeout | 802.1X không cấp quyền mới | Trung bình/cao | AAA health | Thử RADIUS 2, sau đó restricted | Sửa kết nối AAA |
| DNS resolver 1 | Không phản hồi | Client timeout | Trung bình/cao | DNS functional query | Resolver 2 cùng policy | Khôi phục service 1 |
| VPN IdP | API lỗi | Không cấp login mới | Cao | Auth synthetic test | Từ chối login chưa kiểm chứng | IdP dự phòng, break-glass được kiểm soát |

Các ngưỡng “cao/thấp” phải được xác định theo hệ thống thực tế, dữ liệu, chi phí gián đoạn và nghĩa vụ hoạt động.

## 5. Kiến trúc HA giữ nguyên kiểm soát bảo mật

**High Availability (HA)** làm giảm nhu cầu chuyển sang fail-open bằng cách đưa dịch vụ sang node khác **vẫn có chính sách tương đương**. Tuy vậy, HA không tự động bảo đảm fail-safe: hai node có thể cùng lỗi cấu hình, dùng chung nguồn điện, cùng phụ thuộc DNS/AAA hoặc không đồng bộ phiên.

### Kiến trúc minh họa

~~~mermaid
flowchart LR
  C["Client / Internet"] --> R["Router hoặc Load Balancer"]
  R --> F1["Firewall A (Active; policy P)"]
  R -.->|Failover| F2["Firewall B (Standby; policy P)"]
  F1 <-->|Heartbeat + policy/state sync| F2
  F1 --> Z["Ứng dụng trong vùng tin cậy"]
  F2 --> Z
  O["Giám sát độc lập + OOB"] -.-> F1
  O -.-> F2
~~~

Cần kiểm chứng tối thiểu:

1. **Policy parity:** hai node áp cùng luật, đối tượng địa chỉ, NAT, ACL, TLS inspection, chứng chỉ và phiên bản phù hợp. “Standby” thiếu rule không phải đường an toàn.
2. **Đường dữ liệu độc lập:** nguồn điện, uplink, switch, cáp, zone, AZ khi cần; tránh một điểm chung làm hỏng cả hai node.
3. **Heartbeat và tình trạng data plane:** link up chưa chắc forwarding tốt. Health check cần nhìn được dịch vụ thật, không chỉ ping IP của thiết bị.
4. **Tránh split-brain:** dùng cơ chế bầu vai trò, quorum/fencing do sản phẩm hỗ trợ; tránh hai node cùng quảng bá gateway/đường mặc định.
5. **Đồng bộ state:** NAT, session table, IPsec/SSL VPN, connection tracking khi nền tảng hỗ trợ. Nếu không có, phải chấp nhận một số phiên bị reset và test khả năng reconnect.
6. **Routing convergence:** ARP/ND, VRRP/HSRP, BGP/OSPF, load balancer và route propagation theo kiến trúc; chú ý asymmetric routing qua stateful firewall.
7. **Kênh quản trị khẩn cấp:** OOB/console, AAA độc lập có kiểm soát, backup cấu hình và phương án sửa rule nếu đường quản trị bị chặn.

### Phát hiện lỗi và tránh flapping

Một health checker thường dùng nhiều phép thử: **interface**, **route**, **forwarding**, **service request**, **state sync** và **sự hiện diện của node dự phòng**. Chọn ngưỡng và khoảng thời gian phù hợp để không đổi vai trò liên tục khi mạng chập chờn.

Ví dụ logic giả lập (không phải cấu hình sản phẩm):

~~~text
IF data_path_probe_failed_consecutively >= threshold
AND standby_healthy
AND standby_policy_version == approved_policy_version
AND fencing_or_quorum_prevents_dual_active
THEN transition_traffic_to_standby
ELSE maintain_defined_failure_policy_and_alert

AFTER failover:
  verify traffic reaches intended destination
  verify denied paths remain denied
  verify NAT/session behavior
  notify on-call and record incident
~~~

Ngưỡng, số lần probe, hold-down và preemption phải được thử dưới tải và mô hình lỗi thực. **Preemption tự động** có thể làm gián đoạn dịch vụ thêm lần nữa khi node chính hồi phục; nhiều hệ thống chọn phục hồi có kiểm soát.

## 6. Fail-safe cho firewall, router và switch

### 6.1. Firewall và phân đoạn

Ở biên bảo mật, quy tắc cốt lõi là **không bỏ policy chỉ vì engine có lỗi**. Cấu hình mặc định nên là deny những luồng chưa được phê duyệt, logging cho quyết định quan trọng và HA với đường thay thế vẫn thực thi policy. Cần phân biệt:

- **Stateful policy failover:** node dự phòng tiếp quản; tính an toàn phụ thuộc vào tính đồng bộ rule/state.
- **Firewall virtual/cloud:** route table chuyển đến appliance khác, hoặc dùng khả năng HA do cloud cung cấp; bảo đảm route không chuyển trực tiếp qua đường bypass.
- **Lỗi cấu hình rule:** có thể gây mở truy cập vô ý dù thiết bị vẫn “healthy”. Do đó kiểm tra behavior, diff và approval quan trọng như kiểm tra trạng thái phần cứng.
- **Session established:** phiên cũ có thể rớt khi failover; không nên tự mở “allow any” nhằm cứu session.

Ví dụ ý định policy:

~~~yaml
# PSEUDOCONFIG - mô tả chính sách, không phải cấu hình áp dụng trực tiếp.
security_boundary: app_to_database
default_action: deny
allowed_flows:
  - source_zone: application
    destination_zone: database
    protocol: tcp
    destination_port: 5432
    principals: approved_application_workloads
failure_policy:
  if_primary_unavailable: use_healthy_standby_with_same_policy
  if_no_valid_policy_enforcer: deny_unapproved_flows
  alert: immediate
~~~

Đây là yêu cầu logic. Cách diễn đạt tương ứng bằng ACL, security group, policy API hay cấu hình HA khác nhau theo hãng; không sao chép YAML này vào thiết bị.

### 6.2. Router, dynamic routing và đường dự phòng

Đường dự phòng phải được thiết kế để **không tự vượt qua firewall/IPS bắt buộc**. Khi một router lỗi, routing có thể hội tụ sang tuyến thứ hai. Đánh giá:

- BGP/OSPF adjacency, policy import/export, next-hop reachability, route filtering và trạng thái thực của data plane.
- BFD hoặc các cơ chế phát hiện lỗi nhanh nếu phù hợp và được sản phẩm hỗ trợ; cấu hình quá nhạy có thể gây flapping.
- Thời gian hold route/route convergence: giữ route không còn sử dụng được quá lâu gây blackhole.
- Các cơ chế graceful restart và stale route cần được đánh giá theo kiến trúc; không mặc định luôn giữ sẵn sàng.
- Chính sách chống route leak, phân đoạn VRF và kiểm soát hướng lưu lượng phải còn hiệu lực sau chuyển tuyến.

Một đường thứ hai vẫn giữ policy và đi qua firewall dự phòng là **failover tốt**. Một đường thứ hai đi thẳng từ Internet vào subnet nội bộ có thể tăng availability nhưng phá biên bảo mật.

### 6.3. Switch và lớp truy cập

Trong mạng LAN, lỗi uplink, nguồn, STP loop, EtherChannel/LACP, chassis stack hoặc control plane đều có thể cắt đường truyền. Hardening fail-safe gồm:

- Thiết kế uplink dự phòng, loop prevention, phát hiện lỗi và kiểm soát broadcast storm.
- Giới hạn trunk/VLAN cho phép; khi failover không tự gộp guest VLAN vào production VLAN.
- Bảo toàn cấu hình 802.1X, DHCP snooping, DAI, port security, ACL và management VLAN ở đường còn hoạt động.
- Phát hiện khi switch mất kết nối controller: policy đã cài đặt được giữ ra sao, có thời hạn không, có thể cấp quyền mới không?
- Quản trị qua OOB hoặc console; lưu cấu hình và quy trình rollback.

Một số platform có khả năng giữ cấu hình chuyển tiếp cuối (*last-known-good forwarding*) khi controller không tới được. Hãy xác định rõ policy nào còn hoạt động và ảnh hưởng của việc thiết bị/identity mới kết nối trong thời gian cô lập.

## 7. Fail-safe cho IDS/IPS, WAF và các thiết bị inline

### 7.1. IDS thụ động khác IPS inline

**IDS passive** quan sát lưu lượng qua TAP/SPAN và gửi cảnh báo; khi sensor lỗi, phần lớn thiết kế không làm đứt data path nhưng gây **mất khả năng phát hiện**. Điều kiện fail-safe lúc này là phát cảnh báo sensor offline, kiểm tra telemetry coverage, buffer log nếu có và khôi phục nhanh.

**IPS inline** có thể thực sự đứng trên đường truyền. Khi quá tải, treo process hoặc mất nguồn, tùy thiết bị có thể:

- **Fail-closed:** ngắt đường khi không kiểm tra được. Hữu ích khi không được phép truyền lưu lượng chưa kiểm soát nhưng gây downtime.
- **Fail-open/bypass:** gói tin tiếp tục đi qua đường bypass. Giữ kết nối, song có thể không còn kiểm tra/chặn xâm nhập.
- **Failover sang IPS khác:** đường dự phòng tiếp tục áp dụng kiểm tra phù hợp; đây thường là lựa chọn an toàn hơn nếu thiết kế/kiểm thử đúng.
- **Degraded inspection:** chỉ áp dụng một tập quy tắc tối thiểu hoặc tạm bỏ chức năng tốn tài nguyên; phải được đánh giá, phê duyệt và giám sát.

**Hardware bypass** có thể hoạt động khi thiết bị mất điện, nhưng khả năng thực tế phụ thuộc NIC, chế độ lắp đặt, cấu hình, topology và nhà sản xuất. Không suy ra “fail-open” đồng nghĩa mọi luồng đều được phép: các firewall và ACL khác có thể vẫn chặn.

### 7.2. Rủi ro nếu bỏ qua inspection

Giả sử inline IPS bảo vệ một ứng dụng từ Internet. Nếu IPS vào bypass, firewall phía trước vẫn phải chặn các dịch vụ không được công bố và WAF/reverse proxy vẫn áp dụng xác thực, rate limiting. Nếu chính IPS là lớp ngăn chặn duy nhất cho một lớp tấn công nguy hiểm, fail-open làm tăng rủi ro đáng kể.

Cần xác định trước:

- Luồng nào được phép bypass, luồng nào buộc fail-closed?
- Sau bypass còn những kiểm soát độc lập nào?
- Cảnh báo bypass có gửi tới SOC/NOC bằng kênh không phụ thuộc sensor không?
- Trong bao lâu được chạy ở chế độ suy giảm, ai có quyền chấp thuận gia hạn?
- Khi thiết bị phục hồi, quá trình quay lại inspection có làm rớt phiên không?

WAF dạng reverse proxy cũng cần policy khi engine kiểm tra lỗi hoặc cập nhật rule thất bại. Tránh chuyển toàn bộ request sang trạng thái bypass vô thời hạn mà không có kiểm soát dự phòng.

## 8. Fail-safe cho VPN, xác thực mạng và NAC/802.1X

### 8.1. VPN và hệ thống danh tính

Một VPN có thể còn data path nhưng mất khả năng kiểm tra phiên đăng nhập mới vì IdP, RADIUS, LDAP hoặc MFA provider lỗi. Phải tách:

- **Đăng nhập mới:** không cấp quyền truy cập trái tiêu chuẩn khi không xác minh được danh tính/MFA; sử dụng nguồn xác thực dự phòng được kiểm duyệt hoặc từ chối đăng nhập.
- **Phiên đã xác thực trước đó:** chính sách có thể cho phép duy trì tới thời hạn phiên và yêu cầu re-auth phù hợp; đánh giá khả năng thu hồi, token expiry và rủi ro khi backend identity không phản hồi.
- **Truy cập cứu hộ:** tài khoản break-glass, xác thực và ghi log qua đường độc lập có kiểm soát; không dùng tài khoản chung không audit hoặc vô hiệu MFA đại trà.
- **Đường VPN dự phòng:** thiết bị và đường mạng thứ hai phải giữ tunnel encryption, route policy, split-tunnel restrictions và phân đoạn mạng tương đương.

Một cấu hình fail-safe không được rơi vào trạng thái “MFA lỗi → cho phép tất cả người dùng”.

### 8.2. NAC và 802.1X

Khi switch/AP không thể liên lạc RADIUS:

| Tùy chọn | Tác dụng | Điều kiện xem xét |
|---|---|---|
| RADIUS/AAA dự phòng | Tiếp tục xác thực hợp lệ | Nên là phương án chính; kiểm tra timeout và thứ tự server |
| **Fail-closed / unauthorized** | Thiết bị chưa xác thực không vào mạng | Phù hợp cho tài sản/zone nhạy cảm |
| **Restricted/critical VLAN** | Thiết bị được truy cập rất giới hạn (ví dụ DHCP/DNS và cổng khắc phục) | Chỉ dùng khi thiết kế rõ ACL, nội dung VLAN và kiểm soát đầu ra |
| MAC Authentication Bypass (MAB) | Dùng định danh MAC cho nhóm thiết bị không hỗ trợ 802.1X | MAC dễ giả mạo; chỉ như cơ chế có giới hạn, không tương đương 802.1X |
| Cấp full corporate VLAN khi AAA lỗi | Duy trì truy cập rộng | Thường không chấp nhận ở môi trường bảo mật; cần phê duyệt rủi ro đặc biệt |

**Khác biệt quan trọng:** “critical VLAN” không phải tự động là vùng an toàn. Nếu VLAN này truy cập được máy chủ quan trọng, cấu hình fallback có thể khiến mọi thiết bị chưa xác minh tiếp cận mạng nhạy cảm.

### 8.3. Wi-Fi và mạng khách

Với AP/controller hoặc captive portal mất liên lạc, chính sách có thể giữ SSID ở chế độ hoạt động bị giới hạn hoặc tạm dừng xác thực mới. Điều bắt buộc là:

- Guest/client isolation và VLAN tách biệt vẫn được thực thi.
- Không tự chuyển guest sang internal SSID/VLAN.
- WPA2/WPA3-Enterprise, 802.1X và kiểm soát chứng chỉ không bị bỏ qua.
- Nếu dùng chế độ offline forwarding, xác định thời hạn, danh sách policy giữ lại và khả năng cấp phiên mới.

## 9. Fail-safe cho DNS, NTP, dịch vụ cloud và bảo vệ dữ liệu

### DNS

Khi resolver không trả lời, hệ thống có thể sử dụng resolver thứ hai trong cùng miền quản trị và chính sách. Lưu ý:

- Secondary resolver phải đáp ứng yêu cầu phân giải nội bộ, logging, DNS security filtering và DNSSEC validation nếu chính sách yêu cầu.
- **Không tự động fallback đến resolver công cộng** khi điều đó làm lộ truy vấn nội bộ, phá DNS filtering hoặc đưa kết quả không nhất quán.
- Cache/stale answer có thể cải thiện availability trong một số triển khai, nhưng cần TTL và chính sách phục vụ dữ liệu cũ rõ ràng; dữ liệu DNS lỗi thời có thể gây rủi ro và dẫn sai đích.
- Nếu thiết bị sử dụng tên miền để kiểm tra quyền hoặc kết nối controller, phải xét tình trạng DNS lỗi ảnh hưởng tới việc xác thực policy.

### NTP và chứng chỉ

Mất nguồn thời gian chuẩn có thể gây sai lệch timestamp, làm hỏng Kerberos/TLS/VPN, khiến điều tra và kiểm chứng thứ tự sự kiện khó hơn. Nên có nhiều nguồn thời gian tin cậy, giám sát độ lệch và không bỏ xác minh chứng chỉ để “chữa” lỗi đồng hồ.

### Cloud và microsegmentation

Ở cloud, lỗi có thể thuộc VM, route table, NAT gateway, load balancer, security group, CNI/network policy controller hoặc Identity Provider. Thiết kế fail-safe:

- Đưa traffic sang instance/appliance healthy có policy cùng phiên bản; tránh route trực tiếp vượt qua biên bắt buộc.
- Giữ “default deny” ở security group hoặc network policy nơi thích hợp; đừng tạo rule mở rộng chỉ để xử lý lỗi API.
- Với Kubernetes NetworkPolicy, tính thực thi phụ thuộc CNI; controller mất liên lạc có thể ảnh hưởng tới việc tạo pod và chính sách được áp dụng. Phải test behavior thực tế.
- Tách quyền của control plane và data plane; giám sát policy propagation và phát hiện workload mới không nhận được policy.
- Xác định giới hạn của “last known good”: policy cũ vẫn có thể không phù hợp sau khi quyền/nguy cơ thay đổi.

## 10. Chu trình thiết kế và triển khai fail-safe

~~~mermaid
flowchart TD
  A["Lập danh mục tài sản, luồng dữ liệu và phụ thuộc"] --> B["Xác định failure mode và mục tiêu an ninh/sẵn sàng"]
  B --> C{"Có đường dự phòng cùng policy?"}
  C -->|"Có"| D["Thiết kế HA/failover + state sync + fencing"]
  C -->|"Không"| E["Chọn fail-closed hoặc degraded/bypass đã chấp thuận"]
  D --> F["Xác định health checks, điều kiện chuyển trạng thái"]
  E --> F
  F --> G["Thiết lập logging, OOB, cảnh báo, rollback"]
  G --> H["Thử lỗi có kiểm soát và so sánh actual với expected"]
  H --> I{"Giữ được ranh giới bảo mật và SLO?"}
  I -->|"Không"| J["Rollback, sửa policy hoặc kiến trúc"]
  J --> B
  I -->|"Có"| K["Triển khai từng phần, giám sát, diễn tập định kỳ"]
~~~

Quy trình thực hiện:

1. **Định nghĩa tài sản bảo vệ:** dịch vụ nào phải liên tục, dữ liệu nào nhạy cảm, vùng nào không được kết nối, bên nào có quyền quản trị.
2. **Ghi yêu cầu khả dụng và bảo mật:** RTO (thời gian khôi phục mục tiêu), RPO nếu có dữ liệu trạng thái cần phục hồi, SLA/SLO, độ trễ, mức chấp nhận gián đoạn/ mất phiên và rủi ro khi bypass.
3. **Lập danh sách lỗi:** mất điện, treo process, interface lỗi một chiều, đường truyền chập chờn, HA peer không phản hồi, mất state sync, lỗi IAM/DNS, sai policy, cạn tài nguyên.
4. **Đưa ra quyết định cụ thể cho từng lỗi:** failover, fail-closed, restricted mode hoặc fail-open có điều kiện và kiểm soát bù đắp; ghi lý do và chủ sở hữu rủi ro.
5. **Thiết kế điều kiện phát hiện:** health check từ bên ngoài, kiểm tra chính sách và data plane, xác minh standby có đủ điều kiện nhận tải.
6. **Chuẩn bị thực thi và khôi phục:** lưu cấu hình, sơ đồ luồng, tài khoản/kênh OOB, thời điểm change, failback plan và bằng chứng đo trước/sau.
7. **Thử nghiệm từng kịch bản:** diễn tập trên lab/staging hoặc canary; production test theo quy trình và khung bảo trì được phê duyệt.
8. **Quan sát và cập nhật:** thời gian phát hiện/đổi trạng thái, phiên bị rớt, lưu lượng không được phép, độ đầy log, health metrics, khả năng cảnh báo và ảnh hưởng kinh doanh.

### Mẫu quyết định failure policy

~~~yaml
# Ví dụ tài liệu thiết kế, KHÔNG phải config chạy trực tiếp.
asset: "firewall-ha-prod"
owner: "network-security-team"
protected_zones:
  - "internet_to_app"
  - "app_to_database"
requirements:
  rto_seconds: 60           # ví dụ nội bộ, không phải cam kết thiết bị
  policy_on_unknown_traffic: "deny"
failure_modes:
  - trigger: "active_dataplane_unhealthy"
    preferred_action: "failover_to_policy_equivalent_standby"
    fallback_if_no_standby: "block_unapproved_flows"
    alert_severity: "critical"
  - trigger: "policy_sync_failed"
    preferred_action: "prevent_unsafe_takeover_and_alert"
    recovery: "restore_policy_parity_then_retest"
safety_invariants:
  - "user_vlan_cannot_reach_database_admin"
  - "guest_network_cannot_reach_internal_management"
  - "remote_access_requires_approved_authentication"
approval:
  business_owner: "defined_in_change_record"
  security_owner: "defined_in_change_record"
~~~

Giá trị `rto_seconds` chỉ là mục tiêu giả định để minh họa cách đặc tả yêu cầu. Trong thực tế phải đo và xác nhận bằng diễn tập, đồng thời tính cả thời gian phát hiện, chuyển tuyến, hội tụ routing và ứng dụng kết nối lại.

## 11. Kiểm thử fail-safe: xác minh tính an toàn và tính khả dụng

Một bài test tốt không chỉ hỏi “dịch vụ có lên lại không?” mà còn hỏi **“trong và sau khi lỗi, các luồng bị cấm có vẫn bị cấm không?”**.

### Danh mục kiểm thử

| Test | Thao tác mô phỏng có kiểm soát | Kỳ vọng về an ninh | Kỳ vọng vận hành |
|---|---|---|---|
| Mất nguồn node active | Mô phỏng tắt node trên lab/canary theo quy trình | Dự phòng giữ policy, không mở ranh giới bị cấm | Đo downtime, session loss và failover |
| Treo forwarding nhưng link vẫn up | Dùng điều kiện lỗi giả lập hoặc kiểm thử sức khỏe data plane | Không giữ route blackhole hoặc bypass tùy tiện | Detector phát hiện và xử lý trong thời gian mục tiêu |
| Mất heartbeat HA | Mất kênh heartbeat có kiểm soát | Không hai active cùng lúc; fencing/quorum đúng | Không flapping liên tục |
| Mất state sync | Ngắt đồng bộ trong lab | Không tạo rule rộng để giữ session | Ghi rõ khả năng mất/reconnect phiên |
| Mất RADIUS/IdP | Tạm không truy cập authentication backend trong test | Client chưa xác thực không nhận quyền vượt policy | Dự phòng hoặc restricted VLAN hoạt động như thiết kế |
| Mất DNS resolver | Dừng resolver chính ở lab | Không tự truy vấn resolver không được phê duyệt | Secondary trả đúng bản ghi/policy |
| IPS chuyển bypass | Simulate bypass có hỗ trợ trong lab | Firewall khác vẫn chặn luồng bị cấm; cảnh báo bypass | Dịch vụ theo mục tiêu được duy trì |
| Mất cloud policy controller | Giả lập gián đoạn control plane | Workload mới không được cấp quyền không kiểm soát | Workload cũ theo hành vi đã định nghĩa |
| Cấu hình quản trị sai | Áp cấu hình test có commit-confirmed/rollback | Không phải tắt xác thực hoặc mở management port | OOB/console còn khôi phục được |
| Phục hồi và failback | Đưa node/service trở lại healthy | Chính sách không đổi và audit đầy đủ | Không tạo vòng chuyển đổi liên tục |

**Không gây lỗi thật ngoài hệ thống kiểm thử nếu chưa có phê duyệt và kế hoạch rollback.** Những thao tác như ngắt điện, phá heartbeat, xóa route hay làm mất AAA có thể ảnh hưởng nhiều hệ thống và người dùng.

### Chỉ số quan sát

- **Detection time:** từ khi lỗi bắt đầu đến khi hệ thống nhận diện.
- **Failover time:** từ lúc nhận diện đến khi chuyển tiếp ở đường mới theo thiết kế.
- **End-to-end recovery time:** đến khi người dùng/ứng dụng có thể hoạt động lại; thời gian này có thể dài hơn chuyển tuyến vì phải kết nối lại.
- **Session loss:** số phiên bị rớt, lỗi auth, timeout, lỗi transaction.
- **Security regression:** số luồng bị cấm chuyển thành cho phép; phải là **0** với những bất biến bảo mật đã định nghĩa.
- **Visibility gap:** thời gian không có log/telemetry và khả năng truy vết quyết định.
- **Failback stability:** có flapping, asymmetric routing hoặc chuyển tuyến lại ngoài kế hoạch không.

### Bất biến bảo mật (security invariants)

Trước buổi thử nghiệm, ghi các điều kiện **luôn phải đúng**, kể cả trong thời gian chuyển trạng thái:

~~~text
Invariant 1: Guest VLAN không truy cập management VLAN.
Invariant 2: User VLAN không truy cập trực tiếp database admin port.
Invariant 3: Không cấp VPN session mới nếu chưa xác minh đủ policy xác thực.
Invariant 4: Mọi luồng qua tuyến dự phòng vẫn phải đi qua policy firewall bắt buộc.
Invariant 5: Nếu IPS bypass được chấp thuận, cảnh báo được gửi qua giám sát độc lập.
Invariant 6: OOB/break-glass còn dùng được và có audit.
~~~

Các bất biến này nên được kiểm chứng cả **trước, trong, sau** failover. Một hệ thống có thể đạt RTO nhưng vẫn thất bại về an ninh nếu policy bị bypass trong 20 giây.

## 12. Tình huống thực tế và cách xử lý

### Tình huống A — Firewall HA có node dự phòng thiếu policy

**Bối cảnh:** firewall A active, B standby. Hai thiết bị cùng thấy heartbeat khỏe nhưng rule cập nhật gần nhất chỉ nằm trên A. Khi A lỗi, B tiếp quản nhưng cho phép traffic từ VLAN người dùng vào vùng quản trị.

**Vấn đề:** HA có availability nhưng không bảo đảm policy parity.

**Biện pháp:**

1. Kiểm tra trạng thái sync và phiên bản chính sách trước khi cho standby có quyền nhận vai trò.
2. Có cơ chế cảnh báo và chặn takeover không an toàn theo khả năng thiết bị; nếu không đủ, chọn trạng thái lỗi đã được phê duyệt.
3. Dùng test luồng bị cấm như một phần tiêu chí failover.
4. Khắc phục nguồn gây drift và thử lại.

### Tình huống B — Inline IPS hỏng, kích hoạt hardware bypass

**Bối cảnh:** một IPS inline trên đường public web có chức năng fail-open. Khi mất nguồn, cổng bypass nối qua để giữ traffic. Monitoring chỉ theo dõi link nên không báo IPS đã mất inspection.

**Vấn đề:** dịch vụ không ngắt nhưng ngăn chặn tấn công đã suy yếu.

**Biện pháp:** giám sát nguồn/health của IPS độc lập, gửi cảnh báo bypass tới SOC, giữ WAF/firewall/rate limit ở tầng khác, giới hạn thời gian vận hành ở degraded mode, cân nhắc IPS dự phòng hoặc fail-closed cho luồng nhạy cảm.

### Tình huống C — RADIUS mất kết nối, switch đẩy thiết bị vào VLAN mặc định

**Bối cảnh:** RADIUS chính lỗi, switch không có AAA dự phòng và cho mọi endpoint chưa xác thực vào VLAN sản xuất để “không gián đoạn”.

**Vấn đề:** lỗi xác thực trở thành truy cập mạng trái phép.

**Biện pháp:** dùng RADIUS dự phòng, thử logic timeout, fail-closed ở port nhạy cảm, restricted VLAN có ACL chỉ cho DHCP/DNS/khắc phục nếu được phê duyệt; xác nhận máy lạ không đến được server nhạy cảm.

### Tình huống D — DNS fallback sang resolver ngoài

**Bối cảnh:** máy khách không truy cập được DNS nội bộ và tự dùng public DNS. Các truy vấn tên dịch vụ nội bộ bị gửi ra Internet; quy tắc lọc DNS của doanh nghiệp không còn.

**Vấn đề:** cải thiện một phần availability nhưng làm lộ metadata và phá cơ chế bảo vệ.

**Biện pháp:** resolver phụ cùng chính sách, cấu hình client/egress DNS có kiểm soát, giữ bản ghi nội bộ và xác thực DNS theo kiến trúc; kiểm tra rằng khi primary mất, truy vấn không đi tới đích ngoài phê duyệt.

### Tình huống E — Mất heartbeat gây split-brain

**Bối cảnh:** firewall cluster hai node vẫn có data plane hoạt động, nhưng mất kênh heartbeat; cả hai tự nhận active và quảng bá địa chỉ gateway.

**Vấn đề:** ARP/ND và route dao động, session bị rớt, có thể có bất nhất policy/state.

**Biện pháp:** cơ chế quorum/fencing, heartbeat qua nhiều đường độc lập, xác định node nào được quyền active khi không có quorum, tránh tự động preempt nếu chưa ổn định, ghi lại sự kiện chuyển vai trò.

### Tình huống F — Cloud route failover đi vòng appliance bảo mật

**Bối cảnh:** một network virtual appliance lỗi. Automation thay route đích thành Internet gateway trực tiếp thay vì appliance dự phòng cùng policy.

**Vấn đề:** đường mạng “phục hồi” nhưng bỏ qua lớp kiểm soát bắt buộc.

**Biện pháp:** automation chỉ chọn healthy appliance có policy tương đương; guardrail kiểm tra route table, network policy, security groups và luồng bị cấm trước khi xác nhận thành công; monitor mọi thay đổi route.

## 13. Tổ chức vận hành, logging và khôi phục

### Phân quyền quyết định

- **Network/SRE:** thiết kế HA, routing, trạng thái interface, health probe, cảnh báo và đo RTO.
- **Security/SOC:** phê duyệt ranh giới tin cậy, điều kiện fail-closed/fail-open, compensating controls và các bất biến cần kiểm thử.
- **Chủ hệ thống/kinh doanh:** xác định hậu quả downtime, dịch vụ tối thiểu chấp nhận được và rủi ro còn lại.
- **Incident commander hoặc người trực được ủy quyền:** điều phối khi failure thật xảy ra, quyết định thay đổi khẩn cấp, ghi lý do và thời điểm khôi phục policy.

Cần lưu phiên bản cấu hình, owner, sơ đồ luồng, trạng thái trước thay đổi, đầu ra test, hành động của automation và kết quả failback. Một bản ghi sự kiện nên có ít nhất:

~~~yaml
event_id: "FS-EXAMPLE-014"
observed_at: "2026-11-28T14:20:00+07:00"
asset: "fw-cluster-example"
failure_mode: "primary_dataplane_unhealthy"
previous_state: "node_A_active"
new_state: "node_B_active"
decision_reason: "Standby healthy, policy parity verified, fencing in effect"
security_policy_version: "approved-policy-rev-42"
observed_effects:
  - "Approved application traffic recovered"
  - "User-to-management forbidden path remained denied"
session_disruption: "Some sessions reconnected"
evidence_refs:
  - "ha-event-log-ref"
  - "flow-test-ref"
owner: "oncall-network-security"
next_review: "after incident stabilization"
~~~

Tên trường và giá trị trong mẫu chỉ là minh họa. Log thực tế cần bảo vệ khỏi chỉnh sửa trái phép, lưu đúng múi giờ, đồng bộ NTP và tránh ghi token/bí mật trong ticket.

### Runbook khi chuyển sang trạng thái lỗi

1. **Nhận biết:** cảnh báo thiết bị, data plane, xác thực và tình trạng chính sách.
2. **Kiểm tra mức độ ảnh hưởng:** lưu lượng nào ngừng, truy cập nào bất ngờ được phép, khách hàng/đối tượng nào bị tác động.
3. **Xác minh trạng thái an toàn:** đường dự phòng có policy đúng, ranh giới mạng còn nguyên, không có split-brain hoặc bypass không được kiểm soát.
4. **Giảm thiểu rủi ro theo thẩm quyền:** chuyển tuyến, giới hạn phạm vi, bật control bù đắp, cô lập vùng nhạy cảm nếu cần.
5. **Khôi phục chính:** sửa lỗi, đồng bộ policy/state, kiểm tra sức khỏe và xác định thời điểm failback an toàn.
6. **Xác minh sau sự cố:** chạy lại phép thử các luồng cho phép/cấm, đo RTO, audit thay đổi và bổ sung bài học vào FMEA.

## 14. Sai lầm phổ biến khi cấu hình fail-safe

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đồng nhất fail-safe với fail-open | Mất lớp kiểm soát lúc sự cố | Xác định trạng thái an toàn theo từng luồng/tài sản |
| Luôn fail-closed mà không xét tác động | Dịch vụ quan trọng bị gián đoạn không cần thiết | Thiết kế dự phòng có cùng policy, degraded mode được phê duyệt |
| HA nhưng policy không đồng bộ | Node dự phòng làm lộ tài sản hoặc chặn sai | So sánh policy/state/version và kiểm thử bảo mật khi failover |
| Chỉ giám sát link hoặc ping | Thiết bị treo forwarding vẫn “up” | Dùng health probe dịch vụ/data path có ngưỡng hợp lý |
| Không có quorum/fencing | Split-brain, route/IP dao động | Kiểm soát active ownership và thử lỗi heartbeat |
| RADIUS lỗi → cấp full VLAN | Thiết bị chưa xác minh vào mạng tin cậy | AAA dự phòng hoặc restricted VLAN thật sự hạn chế |
| IPS bypass mà không cảnh báo | Mất khả năng ngăn chặn dài ngày | Giám sát độc lập, bù đắp và giới hạn degraded period |
| Chọn tuyến thứ hai đi vòng firewall | Traffic tiếp tục nhưng mất segmentation | Guardrail route và kiểm tra invariant trên đường dự phòng |
| Quên phiên NAT/VPN/state | Sau chuyển tuyến nhiều phiên rớt ngoài dự kiến | Stateful sync hoặc kế hoạch reconnect, đo recovery thực tế |
| Thử failover chỉ đo uptime | Không thấy khoảng thời gian các luồng cấm được mở | Chạy bộ test cho cả allow và deny trước/trong/sau lỗi |
| Không có OOB/rollback | Không thể sửa cấu hình khi management plane bị cắt | Kênh console/OOB, backup và rollback có kiểm soát |
| Bật preemption quá nhạy | Failover/failback liên tục | Hysteresis, hold-down, quy trình phục hồi ổn định |

## 15. Checklist đánh giá thiết kế fail-safe

- [ ] Đã xác định dịch vụ và vùng mạng quan trọng, dữ liệu nhạy cảm và owner chưa?
- [ ] Đã mô tả các failure mode: mất nguồn, hỏng link, treo data plane, mất AAA/DNS/IdP, lỗi policy và split-brain chưa?
- [ ] Đã phân biệt yêu cầu an ninh và availability, có RTO/RPO/SLO phù hợp chưa?
- [ ] Với mỗi lỗi, chế độ failover/fail-closed/restricted/fail-open có được quyết định và phê duyệt không?
- [ ] Mọi đường dự phòng có policy, segmentation, NAT và quyền quản trị tương đương không?
- [ ] Có health check cho data plane và điều kiện tránh flapping/split-brain không?
- [ ] Nếu IPS/WAF bypass, có cảnh báo và lớp bảo vệ bù đắp không?
- [ ] Nếu RADIUS/DNS/VPN/IdP lỗi, có phương án dự phòng **giữ chính sách bảo mật** không?
- [ ] Có logging, giám sát độc lập, OOB và cách rollback để khôi phục quyền quản trị không?
- [ ] Đã thử các luồng **được phép** và **bị cấm** trong cả thời gian chuyển trạng thái chưa?
- [ ] Có xác minh ứng dụng phục hồi, phiên cần reconnect và tỷ lệ lỗi thực tế không?
- [ ] Đã có lịch diễn tập và quy trình xem xét lại khi cấu hình/threat model thay đổi chưa?

## 16. Câu hỏi tự kiểm tra và bài tập

1. Phân biệt fail-safe, fail-open và failover qua ví dụ một firewall HA bảo vệ vùng database.
2. Vì sao một IPS inline có hardware bypass vẫn có thể khiến hệ thống **không** đạt yêu cầu an ninh khi mất điện?
3. Khi NAC mất RADIUS, lựa chọn nào phù hợp hơn giữa fail-closed, restricted VLAN và full-access VLAN? Những yếu tố nào làm thay đổi quyết định?
4. Một firewall standby có policy lỗi thời nhưng heartbeat và link khỏe. Có nên cho thiết bị nhận vai trò active tự động không? Vì sao?
5. Vì sao health check chỉ dựa vào ICMP ping có thể bỏ sót trường hợp data plane không chuyển gói?
6. Giải thích split-brain trong cặp thiết bị HA và vai trò của quorum/fencing khi mất heartbeat.
7. Một DNS resolver nội bộ lỗi khiến máy trạm chuyển sang public DNS. Vấn đề an ninh có thể xảy ra và phương án failover phù hợp là gì?
8. Vì sao giữ RTO dưới 60 giây chưa chứng minh fail-safe đạt yêu cầu? Hãy nêu ba bất biến bảo mật cần thử.
9. Dựng một sơ đồ failover cho firewall, VPN và DNS của công ty; mô tả hậu quả khi từng thành phần lỗi và cách tránh shared failure domain.
10. Viết bảng FMEA cho một switch access sử dụng 802.1X: mất điện, mất uplink, mất AAA và lỗi controller. Ghi expected fallback, kiểm thử và rollback cho mỗi chế độ.

**Điểm cần nhớ:** Cấu hình fail-safe phải được đánh giá theo **trạng thái sau lỗi**, không chỉ theo khả năng thiết bị tự khởi động lại. Một kiến trúc tốt luôn xác định rõ luồng nào được duy trì, quyền nào phải bị từ chối, đường dự phòng có bảo vệ tương đương không và cách chứng minh điều đó bằng kiểm thử có kiểm soát.
