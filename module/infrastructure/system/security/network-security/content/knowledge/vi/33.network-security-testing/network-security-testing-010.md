# Kiểm thử failover và khả năng phục hồi

## 1. Kiểm thử failover nhằm chứng minh điều gì?

Trong một hệ thống mạng, **failover** là quá trình chuyển hoạt động từ một thành phần hoặc đường đi bị lỗi sang thành phần hoặc đường dự phòng. **Khả năng phục hồi (resilience)** là khả năng duy trì chức năng ở mức chấp nhận được, giới hạn ảnh hưởng, khôi phục dịch vụ sau lỗi và tránh tái diễn lỗi dây chuyền.

Kiểm thử failover không chỉ xác nhận “đường mạng hoạt động trở lại”. Với hệ thống bảo mật mạng, một phép thử chỉ đạt yêu cầu khi:

- Lưu lượng **được phép** vẫn đáp ứng mức dịch vụ sau chuyển tuyến, trong giới hạn gián đoạn đã thống nhất.
- Lưu lượng **bị cấm** tiếp tục bị chặn trong toàn bộ thời gian xảy ra lỗi, chuyển tuyến và khôi phục.
- Các cơ chế xác thực, phân đoạn, mã hóa, ghi log và kiểm soát quản trị vẫn đáp ứng chính sách.
- Trạng thái kết nối, phiên VPN/NAT/TLS, route, DNS, session và cấu hình được phục hồi đúng phạm vi dự kiến.
- Hệ thống phát hiện lỗi, phát cảnh báo, tự chuyển đổi hoặc hỗ trợ người vận hành can thiệp theo quy trình.
- Khi lỗi kết thúc, hệ thống không rơi vào **flapping**, **split-brain**, bất đối xứng đường đi hoặc trạng thái suy giảm không được phát hiện.

Chủ đề thuộc chương **Kiểm thử và xác minh bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Bài học kết nối kiến thức về phân đoạn, firewall, VPN, IDS/IPS, bảo vệ DNS, kiểm soát mạng không dây và hạ tầng đám mây với phương pháp kiểm thử lưu lượng, mô hình hóa mối đe dọa, giám sát và thiết kế kiến trúc mạng an toàn.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt failover, failback, redundancy, recovery, RTO, RPO và các chỉ số đo chất lượng chuyển đổi.
2. Viết kế hoạch kiểm thử có phạm vi, giả thuyết, điều kiện thành công, bất biến bảo mật và rollback.
3. Chọn kịch bản lỗi cho firewall HA, router, switch, VPN, DNS, AAA/NAC, IPS, Wi-Fi, load balancer, cloud/VPC và các đường giám sát.
4. Đo gián đoạn bằng probe và bằng chứng đa nguồn thay vì chỉ nhìn trạng thái “healthy” trên dashboard.
5. Phân tích lỗi có điều kiện như mất đồng bộ policy, lỗi kết nối một chiều, mất quorum hoặc chuyển đường dự phòng sai.
6. Lập báo cáo kết quả tái lập được, chỉ rõ điều kiện chưa kiểm chứng và cải tiến cần thiết.

## 2. Thuật ngữ và giới hạn của tính sẵn sàng

| Khái niệm | Ý nghĩa thực hành | Điểm dễ nhầm |
|---|---|---|
| **Redundancy** | Có thành phần/đường dự phòng như node thứ hai, ISP thứ hai, DNS resolver thứ hai | Có dự phòng chưa chắc cơ chế chuyển đổi hoạt động |
| **Failover** | Chuyển traffic hoặc quyền cung cấp dịch vụ sang thành phần còn hoạt động | Link chuyển xong chưa chắc ứng dụng phục hồi |
| **Failback** | Chuyển từ thành phần dự phòng về trạng thái hoạt động ưu tiên hoặc cân bằng ban đầu | Tự động quay về quá sớm có thể gây thêm downtime |
| **High Availability (HA)** | Kiến trúc giảm gián đoạn nhờ dự phòng, kiểm tra sức khỏe và chuyển đổi | HA không bảo vệ khỏi lỗi cấu hình chung hoặc mất cả failure domain |
| **Disaster Recovery (DR)** | Khôi phục sau thảm họa diện rộng, đôi khi ở site/region khác | DR có thể yêu cầu khôi phục dữ liệu và quy trình thủ công hơn HA |
| **RTO** | Mục tiêu thời gian tối đa chấp nhận để phục hồi hoạt động sau gián đoạn | RTO là **mục tiêu**; cần đo thời gian phục hồi thực tế |
| **RPO** | Mức mất dữ liệu hoặc trạng thái có thể chấp nhận, diễn đạt theo thời gian tại điểm khôi phục | RPO chủ yếu áp dụng khi có dữ liệu/state cần khôi phục; không tự đồng nghĩa packet loss |
| **MTTD** | Thời gian trung bình phát hiện lỗi qua nhiều lần thử/sự cố | MTTD khác thời gian failover và thời gian khôi phục ứng dụng |
| **Convergence** | Quá trình giao thức và các node thống nhất đường đi/trạng thái sau thay đổi | Routing hội tụ chưa chắc ứng dụng có thể giao dịch |
| **Fail-open / fail-closed** | Khi kiểm soát lỗi, cho lưu lượng qua hoặc không cho qua theo thiết kế | Cả hai phải được đánh giá theo bối cảnh bảo mật và an toàn vận hành |

### Các mốc thời gian phải tách riêng

Giả sử một bài thử được gắn mốc thời gian:

- \`t0\`: lỗi thực tế bắt đầu tại phần tử được thử.
- \`td\`: hệ thống phát hiện lỗi.
- \`ts\`: standby bắt đầu nhận trách nhiệm chuyển tiếp hoặc cung cấp dịch vụ.
- \`tr\`: ứng dụng được giám sát trở lại mức đáp ứng ổn định.
- \`tf\`: hoàn tất failback (nếu có).

Khi đó:

~~~text
Detection delay       = td - t0
Failover control time = ts - td
End-to-end recovery   = tr - t0
Failback duration     = tf - thời điểm bắt đầu failback
~~~

**Không đồng nhất** thời điểm chuyển vai trò (\`ts\`) với thời điểm phục hồi cuối cùng (\`tr\`): client có thể phải reconnect, đợi DNS cache hết hạn, thiết lập lại TLS/VPN, ARP/ND hoặc chờ database leader sẵn sàng.

Một ví dụ **giả lập**:

| Mốc | Thời điểm | Ý nghĩa |
|---|---|---|
| \`t0\` | 10:00:00 | Đường active được mô phỏng lỗi |
| \`td\` | 10:00:07 | Health checker xác nhận lỗi |
| \`ts\` | 10:00:11 | Standby nhận route/traffic |
| \`tr\` | 10:00:16 | Probe giao dịch ứng dụng ổn định trở lại |

Kết quả giả lập: phát hiện 7 giây, chuyển vai trò sau phát hiện 4 giây, phục hồi từ lúc bắt đầu lỗi 16 giây. Đây **không phải số đo thực tế** hay cam kết của một nhà cung cấp.

Nếu probe chạy mỗi 5 giây, chỉ số phục hồi ghi được có sai số do chu kỳ lấy mẫu và điều kiện xác định “ổn định”. Muốn báo cáo đáng tin, phải ghi **tần suất probe, mốc thời gian gốc và độ lệch đồng hồ**, không trình bày các số đo như chính xác tuyệt đối.

## 3. Kiểm thử khả dụng đồng thời với bảo mật

### 3.1. Hai nhóm phép thử bắt buộc

**Positive test** xác minh các luồng hợp lệ vẫn hoạt động:

- Người dùng truy cập ứng dụng qua HTTPS theo đường được phê duyệt.
- Application tier truy cập đúng database/API nội bộ.
- Nhân viên được cấp quyền thiết lập VPN và truy cập đúng subnet.
- DNS phân giải được tên public/internal tương ứng và tuân thủ chính sách.
- Đội vận hành truy cập thiết bị qua bastion hoặc mạng quản trị.

**Negative test** xác minh các ranh giới an ninh vẫn đúng:

- Guest VLAN không truy cập management VLAN.
- User VLAN không kết nối trực tiếp cổng quản trị database.
- Internet không truy cập được dịch vụ quản trị VPN/firewall.
- Thiết bị chưa xác thực 802.1X không vào được corporate VLAN tin cậy.
- DNS client không tự vượt qua DNS filtering qua resolver không được phê duyệt nếu chính sách chặn việc đó.
- Khi IPS chuyển chế độ, các lớp kiểm soát bắt buộc còn lại vẫn áp dụng.

**Một phép thử failover chỉ kiểm tra ping hoặc HTTP 200 là chưa đủ.** Ping có thể thành công trong khi API lỗi, và HTTP 200 có thể đến từ cache hoặc trang dự phòng sai. Negative test phải có đường kiểm chứng riêng (log firewall, flow telemetry, kết quả request và nguồn/đích thực).

### 3.2. Security invariants — điều kiện không được phá vỡ

**Bất biến bảo mật** là yêu cầu phải giữ đúng trước, trong và sau khi failover, bất kể tuyến active thay đổi.

Ví dụ:

~~~text
INV-01: Guest -> Management (TCP/22, TCP/443): DENY
INV-02: User VLAN -> Database (TCP/5432): DENY
INV-03: Application tier -> Database (TCP/5432): ALLOW, đúng identity/nguồn
INV-04: Internet -> Router/Switch management: DENY
INV-05: VPN login mới chưa xác thực đầy đủ: DENY
INV-06: App request từ nguồn đã xác thực: phục vụ qua HTTPS đúng cert
INV-07: Đường dự phòng vẫn đi qua bộ kiểm soát phân đoạn bắt buộc
INV-08: Trạng thái IPS bypass (nếu được chấp thuận) phát cảnh báo độc lập
~~~

Với phép thử bảo mật, “không ghi nhận luồng cấm thành công” chỉ có ý nghĩa trong **phạm vi và độ bao phủ** telemetry đã xác định. Kết luận cần dựa trên một request có chủ đích, quan sát ở điểm vào và quy tắc enforcement; thiếu log không tự chứng minh đã bị chặn.

### 3.3. Ma trận luồng kiểm tra mẫu

| ID | Nguồn | Đích | Dịch vụ | Kỳ vọng khi bình thường | Kỳ vọng khi failover |
|---|---|---|---|---|---|
| P1 | Internet test client | Public web VIP | HTTPS/443 | Thành công | Thành công sau gián đoạn trong ngưỡng |
| P2 | Application subnet | DB private IP | TCP/5432 | Thành công khi đúng principal | Tiếp tục được phép qua tuyến bảo vệ |
| P3 | Admin jump host | Firewall management | SSH/HTTPS | Thành công có xác thực | Đường OOB/standby quản trị được theo policy |
| N1 | Guest VLAN | Management subnet | SSH/22 | Bị chặn | Vẫn bị chặn |
| N2 | User subnet | Database subnet | TCP/5432 | Bị chặn | Vẫn bị chặn |
| N3 | Internet test client | Firewall management IP | HTTPS/443 | Bị chặn | Vẫn bị chặn |
| N4 | Tài khoản chưa hoàn tất MFA | VPN | Phiên mới | Không được cấp quyền | Không được cấp quyền |

Ma trận phải phản ánh **đúng chính sách của hệ thống được thử**. Tên vùng, cổng và vai trò chỉ là ví dụ.

## 4. Chuẩn bị trước buổi thử nghiệm

### 4.1. Xác định phạm vi và người chịu trách nhiệm

Bản kế hoạch cần ghi:

- **Hệ thống:** môi trường lab/staging/production, site, VPC/VNet, zone, thiết bị, node active/standby, phiên bản firmware/policy.
- **Phạm vi ảnh hưởng:** subnet, người dùng, ứng dụng, các tác vụ sao lưu, DNS/VPN/AAA và phụ thuộc ngoài phạm vi.
- **Phê duyệt:** chủ hệ thống, NOC/SRE, đội an ninh, người trực, khung thay đổi và thời điểm bắt đầu/kết thúc.
- **RTO/RPO/SLO:** mục tiêu cụ thể cho từng chức năng và phép thử; tiêu chí mất phiên, mất gói, độ trễ, lỗi ứng dụng.
- **Bất biến bảo mật:** tập positive/negative tests đã thống nhất.
- **Cách chèn lỗi:** tác động lên thành phần nào, khả năng khôi phục, rủi ro lan truyền và điều kiện dừng.
- **Quản lý rollback:** cấu hình trước thay đổi, backup, console/OOB, người có quyền khôi phục, sự kiện phải dừng thử.
- **Bằng chứng:** thời gian đồng bộ, nơi lưu log, sơ đồ topology, nguồn sensor, bản ghi trước/trong/sau.

Với production, chỉ thực hiện mô phỏng lỗi theo quy trình thay đổi và thẩm quyền đã được phê duyệt. Một số phương pháp như tắt nguồn, ngắt tuyến, can thiệp routing hoặc cắt AAA có thể tác động nhiều hệ thống; nên kiểm thử trên lab hoặc canary trước.

### 4.2. Chốt baseline và failure domain

Trước thử nghiệm, xác nhận:

- Active/standby đang đúng vai trò; đồng bộ policy, state/session, object, certificate và route đã hoàn tất.
- Phần tử dự phòng có capacity đủ chịu tải; không dùng chung một điểm lỗi nguồn điện, uplink, rack, switch, DNS, IdP hoặc region ngoài ý muốn.
- Mạng dự phòng **không đi vòng** firewall/segmentation/inspection được yêu cầu.
- Có kênh quản trị ngoài băng (*out-of-band*, OOB) độc lập, thông tin liên lạc đội trực và bản sao cấu hình có thể khôi phục.
- Health check đang đo được datapath và dịch vụ thật, tránh “link up nhưng ứng dụng chết”.
- Monitoring, SIEM, flow collector, NTP và đồng hồ máy client hoạt động; biết điểm mù thu thập log.
- Có phương án kiểm soát tự động **failback/preemption** nếu thử nghiệm yêu cầu giữ node standby ổn định để đo.

**Failure domain** là tập thành phần có thể hỏng vì cùng một nguyên nhân. Hai firewall ở hai node nhưng cùng nguồn điện hoặc cùng switch uplink không phải thiết kế loại bỏ được sự cố thuộc miền lỗi đó.

### 4.3. Mẫu biên bản test case

~~~yaml
test_id: "FO-010-FW-01"
system: "firewall-ha-staging"
scope: "internet-to-app"
owner: "network-security-oncall"
preconditions:
  - "Policy parity verified"
  - "Standby healthy; OOB reachable"
  - "Baseline P1, N1, N2 captured"
failure_injection: "Controlled active-node failover in staging"
expected:
  rto_seconds_max: 30     # ví dụ minh họa
  allowed_traffic: "P1 stable after recovery"
  denied_traffic: "N1 and N2 always denied"
  security_policy: "unchanged"
  alarm: "HA transition event recorded"
stop_conditions:
  - "Unexpected permit on a prohibited path"
  - "Standby becomes unhealthy"
  - "Service impact exceeds approved safety threshold"
rollback: "Return to previously verified HA state per runbook"
evidence:
  - "Health probe timeline"
  - "Firewall HA and policy logs"
  - "Client traces and application results"
~~~

Các giá trị ngưỡng trong ví dụ là **giả định để minh họa cấu trúc**, không phải chuẩn mặc định của nhà sản xuất.

## 5. Thiết kế kịch bản lỗi: từ đơn giản đến phức tạp

Không nên chỉ thử “rút cáp uplink” rồi kết luận toàn hệ thống có HA. Các failure mode khác nhau có thể kích hoạt cơ chế khác nhau.

| Lỗi cần mô phỏng | Vấn đề muốn kiểm chứng | Dấu hiệu cần thu |
|---|---|---|
| Mất một đường uplink vật lý | Link failover và routing có hoạt động? | Link state, route, LACP, traffic loss |
| Thiết bị active dừng hoạt động | Standby có tiếp quản, policy còn nguyên? | HA role, ARP/ND, VIP, app probe |
| Forwarding lỗi nhưng interface còn up | Probe có nhận ra “blackhole” data plane? | End-to-end probe, BFD/health, route |
| Mất heartbeat HA | Có split-brain hoặc cả hai active không? | Quorum/fencing, ownership IP/MAC |
| Mất state sync nhưng heartbeat còn | Phiên/NAT/VPN bị rớt ra sao? | Session continuity, reconnect, log state |
| Chính sách giữa hai node lệch | Standby có mở luồng bị cấm khi tiếp quản? | Policy hash/version, negative tests |
| Lỗi route/next hop | Chuyển đường có gây asymmetric routing? | FIB/RIB, path trace, stateful drops |
| Mất DNS chính | Resolver dự phòng có giữ đáp án và policy? | Query timeline, response, resolver IP |
| Mất RADIUS/IdP | Cấp phiên mới có tuân thủ xác thực? | Auth accept/reject, VLAN, VPN logs |
| Mất một VPN gateway | Client có tự kết nối lại và bị giới hạn đúng mạng? | Session reauth, MFA, split tunnel |
| IPS inline chuyển bypass | Inspection mất nhưng các lớp kiểm soát còn lại thế nào? | Bypass event, policy, alerting |
| Mất AZ/node cloud | Route/ingress/workload có chuyển trong cùng policy? | VPC flow, LB targets, security group |
| Giám sát/SIEM không nhận log | Mất detection có được báo? | Heartbeat telemetry, delivery lag |
| Failback trở lại node chính | Có flapping, lỗi policy hoặc reset phiên? | Role transitions, session errors |

**Bắt đầu bằng lỗi một thành phần** có khả năng rollback nhanh; sau khi hệ thống ổn định mới đánh giá lỗi kết hợp, lỗi chung failure domain hoặc diễn tập vùng/site rộng theo phê duyệt.

## 6. Quy trình kiểm thử chuẩn

~~~mermaid
flowchart TD
    A["Chốt test plan, owner, mục tiêu và điểm dừng"] --> B["Kiểm tra active/standby và policy parity"]
    B --> C["Thu baseline positive + negative + logs"]
    C --> D["Gắn mốc thời gian t0 và chèn lỗi có kiểm soát"]
    D --> E["Quan sát detector, route, role, session, ứng dụng"]
    E --> F{"Bất biến bảo mật còn đúng?"}
    F -->|Không| G["Dừng thử, cô lập rủi ro, rollback theo runbook"]
    F -->|Có| H{"Khả dụng phục hồi trong ngưỡng?"}
    H -->|Không| G
    H -->|Có| I["Kiểm tra ổn định, khả năng quan sát và failback"]
    I --> J{"Failback và chính sách ổn định?"}
    J -->|Không| G
    J -->|Có| K["Lưu bằng chứng, chấm kết quả, mở issue cải tiến"]
~~~

### Bước 1 — Đo trạng thái ổn định

Thu các chỉ số baseline trong một khoảng đủ đại diện:

- \`P1\`: HTTP(S) response code và thời gian phản hồi, giao dịch đọc/ghi thử nghiệm không phá dữ liệu.
- \`P2\`: kết nối ứng dụng–database và kết quả truy vấn test, không chỉ TCP handshake.
- \`N1/N2\`: lưu lượng không được phép bị chặn, có log/điểm quan sát xác nhận.
- HA state, active route, BGP/OSPF neighbor, route priority, NAT/session count, throughput, CPU/memory.
- VPN login mới, phiên hiện hữu, DNS lookup, 802.1X authentication, IPS/WAF policy.
- Time sync, sampling interval, phiên bản cấu hình và tác nhân đo.

### Bước 2 — Kích hoạt lỗi theo kịch bản

Ghi lại **đúng phương pháp** đã dùng: mô phỏng node không healthy trong lab, vô hiệu hóa một đường thử, đặt health state không đạt bằng chức năng vendor hỗ trợ hoặc chuyển vai trò active theo runbook. Không giả định các cách này tương đương với mất nguồn hoặc treo phần cứng thật.

Thời điểm \`t0\` nên có bằng chứng từ thiết bị hoặc công cụ chèn lỗi. Không dùng thời gian dashboard hiển thị alert làm mốc lỗi bắt đầu nếu cảnh báo đến trễ.

### Bước 3 — Quan sát liên tục

Theo dõi cả ba tầng:

1. **Network:** link, route, ARP/ND, BFD, traffic counters, firewall/IPS decision, path.
2. **Control/identity:** HA role, quorum, policy sync, BGP/OSPF, RADIUS/IdP, certificate, DNS.
3. **Ứng dụng/người dùng:** giao dịch end-to-end, TLS handshake, DNS, TCP reconnect, lỗi thời gian thực.

Không chỉ nhìn **trạng thái cuối**: một luồng cấm có thể được phép trong vài giây chuyển tuyến rồi bị chặn trở lại. Cần probe đủ thường xuyên, log enforcement và kiểm tra timestamp để phát hiện khoảng trống này.

### Bước 4 — Đạt trạng thái phục hồi rồi thử failback

Chỉ xem phục hồi khi các điều kiện **ổn định trong một khoảng đã định**, ví dụ các probe liên tiếp thành công cùng với kiểm tra lỗi ứng dụng. Không đánh đồng lần ping thành công đầu tiên với khôi phục hoàn chỉnh.

Khi failback, kiểm tra đồng bộ policy, route, cert, state, health của node chính; tắt/hoãn preemption nếu được thiết kế như vậy. Failback cũng có thể làm gián đoạn dịch vụ và phải được đo riêng.

### Bước 5 — Rollback hoặc kết thúc

Dừng thử và rollback khi vượt ngưỡng ảnh hưởng, mất quản trị, thấy một luồng cấm được phép, mất khả năng giám sát quan trọng hoặc standby không ổn định. Sau khi rollback, xác nhận lại **positive và negative tests**, log, rule và trạng thái đồng bộ.

## 7. Đo thời gian phục hồi và chất lượng dịch vụ

### 7.1. Đo bằng probe đa tầng

Nên có ít nhất:

| Lớp | Probe mẫu | Câu hỏi trả lời |
|---|---|---|
| L2/L3 | Ping hoặc ARP/ND theo thiết kế, path tracing | Có đường kết nối mạng cơ bản không? |
| L4 | Kết nối TCP đến cổng được phép | TCP handshake có hoạt động không? |
| L5/L6 | TLS handshake với tên miền/chứng chỉ đúng | Phiên an toàn được thiết lập không? |
| L7 | HTTP GET/health hoặc giao dịch ứng dụng thực | Chức năng ứng dụng đã phục hồi chưa? |
| Identity | VPN/802.1X/AAA login test có kiểm soát | Người hợp lệ được cấp đúng quyền, người không hợp lệ bị từ chối? |
| Enforcement | Kết nối bị cấm kèm firewall/NAC/flow log | Boundary còn chặn đúng ngay trong chuyển trạng thái? |
| Monitoring | Syslog/SIEM/metrics/alert probe | Có thể thấy và điều tra sự cố không? |

Một lệnh \`ping\` có thể thất bại vì ICMP bị chặn trong khi ứng dụng vẫn tốt; ngược lại ping thành công không chứng minh dịch vụ HTTPS hoạt động. Luôn đặt điều kiện thành công theo mục tiêu lớp ứng dụng.

### 7.2. Công cụ quan sát trên lab hoặc hệ thống được cấp phép

~~~bash
# Ghi nhận response code và thời gian phục vụ qua HTTPS.
curl --silent --show-error --output /dev/null \
  --write-out 'code=%{http_code} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  https://app.example.com/health

# Kiểm tra kết quả DNS và resolver đang được hỏi.
dig @192.0.2.53 app.example.com A +time=2 +tries=1

# Kiểm tra đường đi và số hop (tùy quyền và hệ điều hành).
traceroute app.example.com

# Khảo sát kết nối đang lắng nghe hoặc đã thiết lập trên Linux.
ss -tan
~~~

Dùng \`example.com\` và dải địa chỉ dành cho tài liệu để minh họa; trong lab thay bằng tài sản đã được phê duyệt. Các lệnh trên chỉ thu trạng thái, **không tự tạo phép đo RTO chính xác** nếu không có bộ lập lịch probe và đồng hồ thu thập thống nhất.

Các phép thử âm tính có thể dùng công cụ kiểm tra kết nối từ đúng VLAN nguồn trong lab. Khi kết luận “DENY”, cần kết hợp kết quả client với log ở điểm chính sách; timeout có thể vì đích tắt, routing lỗi hoặc ACL, không đủ để xác định đúng lớp enforcement.

### 7.3. Phân biệt packet loss, lỗi ứng dụng và mất phiên

- **Packet loss:** phần trăm gói không được trả lời trong phép đo. ICMP có thể bị rate-limit; không dùng riêng để suy diễn loss của ứng dụng.
- **Request failure rate:** tỷ lệ giao dịch thất bại; phân biệt timeout, lỗi DNS, TLS, HTTP 5xx và lỗi database.
- **Session survival:** phiên TCP/NAT/VPN đã thiết lập có còn hoạt động hay phải kết nối lại; HA state sync có thể bảo toàn một số loại session nhưng không phải mọi giao thức.
- **Recovery stability:** có bao nhiêu lần success liên tiếp, lỗi mới có tái diễn, latency và throughput có trở về phạm vi chấp nhận.
- **Security regression:** số trường hợp kết nối trái phép thực sự vượt qua điểm chặn; mục tiêu với invariant bắt buộc là **0 sự kiện xác nhận**.

Ví dụ số đo giả lập một lượt thử:

| Chỉ số | Quan sát minh họa | Đánh giá theo tiêu chí giả định |
|---|---:|---|
| Mục tiêu end-to-end RTO | ≤ 30 giây | Yêu cầu đặt trước |
| Thời gian phát hiện | 7 giây | Số đo mô phỏng |
| Thời gian ứng dụng phục hồi | 16 giây | Đạt RTO giả định |
| Lỗi giao dịch trong cửa sổ thử | 8/100 requests | Cần so với SLO đã duyệt |
| VPN session phải reconnect | 2/10 session thử | Phân tích state sync và client behavior |
| Luồng cấm được cho phép | 0 trên tập probe đã định | Không có regression trong phạm vi thử |
| Log HA gửi tới SIEM | Có, chậm 4 giây | So với mục tiêu độ trễ phát hiện |

Không dùng tỷ lệ mẫu nhỏ này để suy ra SLA dài hạn; chỉ là cách trình bày một lượt thử. Cần chạy lại dưới tải và điều kiện đại diện, báo cáo phân phối kết quả thay vì chỉ giá trị đẹp nhất.

## 8. Kiểm thử firewall HA và phân đoạn

### 8.1. Mục tiêu

Đối với cặp firewall active–standby hoặc active–active, xác minh:

- Standby nhận traffic sau mất node active hoặc datapath không healthy.
- Bảng route, policy/ACL, NAT, VIP, certificate, user identity và object bảo mật tương đương.
- Các vùng nội bộ vẫn giữ phân đoạn, đặc biệt guest, user, management, app, database.
- Không có split-brain, duplicate gateway hoặc đường nối tắt bypass chính sách.
- Khi failback, kết nối không dao động liên tục và log sự kiện vẫn đầy đủ.

### 8.2. Kịch bản thực hành mẫu

**Tiền điều kiện:** hai node đồng bộ policy, có OOB, đã chọn một nguồn client hợp lệ và hai nguồn client thử luồng cấm. Thử trong lab hoặc cửa sổ được phê duyệt.

1. Ghi trạng thái A active, B standby, hash/version policy, trạng thái state sync và routing.
2. Chạy P1/P2 và N1/N2 liên tục; thu firewall traffic logs và client transaction log.
3. Dùng chức năng thử HA của sản phẩm để mô phỏng A không thể đảm nhiệm vai trò active.
4. Đánh dấu \`t0\`, quan sát B nhận vai trò, route/VIP/NAT và thời gian giao dịch trở lại ổn định.
5. Tiếp tục N1/N2 trong và ngay sau chuyển đổi; kiểm tra không có rule cho phép ngoài dự kiến.
6. Kiểm tra liệu các phiên TCP/VPN đang mở còn hoạt động và có phải re-auth không.
7. Đưa A trở lại điều kiện healthy, đồng bộ chính sách và failback theo kế hoạch.
8. Xác nhận active/standby ổn định, không lỗi session, log vẫn gửi, mọi bất biến được giữ.

### 8.3. Kiểm thử những lỗi mà health check đơn giản bỏ sót

- **Link up nhưng forwarding chết:** probe trực tiếp vào IP quản trị firewall có thể vẫn thành công. Phải có giao dịch xuyên firewall.
- **Standby thiếu rule:** failover có thể duy trì ứng dụng nhưng mở cổng quản trị; negative test phát hiện điều này.
- **Asymmetric routing:** packet đi qua node A và return đi qua node B; stateful firewall có thể drop dù mạng nhìn chung có đường đi.
- **Split-brain:** mất heartbeat khiến hai node cùng active; cần kiểm tra quorum/fencing, ownership gateway, ARP/ND, VIP và route.
- **Capacity thấp:** standby đủ tải trong giờ thấp điểm nhưng nghẽn ở peak; cần phép thử tải đại diện và cảnh báo saturation.

## 9. Kiểm thử routing, switch và đường WAN dự phòng

### 9.1. Routing và convergence

Trong hạ tầng có BGP, OSPF, IS-IS, static route tracking, BFD hoặc dynamic cloud routing, kiểm thử phải phân biệt:

- **Thời gian phát hiện neighbor/path chết:** physical link có thể báo nhanh, lỗi blackhole một chiều khó nhận hơn.
- **Rút/chọn route:** RIB và FIB có cập nhật đúng, có route stale, route leak hay default route ngoài dự kiến không.
- **Convergence end-to-end:** khi route đã hiện đúng, traffic ứng dụng có thực sự theo tuyến thay thế không.
- **Security path parity:** tuyến dự phòng có đi qua firewall/IPS/segmentation bắt buộc hoặc cơ chế kiểm soát tương đương không.
- **Tác động của BFD/hello/hold-down:** chỉnh timer quá nhạy có thể tăng flapping và bão cập nhật; thử trong điều kiện loss/jitter thực tế.

Không tự mặc định bật hoặc chỉnh BFD/OSPF/BGP timer trên production chỉ vì một lần failover chậm. Các tham số phải tuân theo tương thích thiết bị và ảnh hưởng control plane.

### 9.2. Switch/access và Wi-Fi

Thử các tình huống:

- Mất một uplink trong cặp LACP/MLAG/stack; đảm bảo VLAN allowlist và port ACL không thay đổi.
- Hỏng một switch trong hệ thống dự phòng; gateway/ARP/ND, STP/loop protection và DHCP còn ổn định.
- Switch/AP mất kết nối bộ điều khiển; guest isolation và management VLAN vẫn đúng.
- RADIUS không trả lời: 802.1X có chuyển sang fallback được phê duyệt hoặc từ chối thiết bị chưa xác thực không?
- Wi-Fi controller failover: SSID, VLAN mapping, WPA-Enterprise, session roaming và logging có còn đúng?

**Negative test quan trọng:** máy chưa xác thực không được vào corporate VLAN; guest SSID không được truy cập mạng quản trị dù controller hoặc AAA bị lỗi.

### 9.3. WAN hai nhà mạng

Với dual ISP, ghi nhận public IP thay đổi, NAT, inbound DNS/routing, đường về, latency và chính sách egress. Một tuyến dự phòng có thể làm HTTPS outbound hoạt động nhưng làm đứt VPN site-to-site, allowlist IP ở đối tác hoặc webhook inbound. Phải kiểm thử **từng chức năng phụ thuộc vào IP/định tuyến** thay vì chỉ kiểm tra browsing.

## 10. Kiểm thử VPN, AAA và DNS khi lỗi dịch vụ hỗ trợ

### 10.1. VPN gateway hoặc IdP lỗi

Chia bài thử thành các nhóm độc lập:

| Nhóm | Phép thử | Kỳ vọng bảo mật |
|---|---|---|
| Phiên VPN đã tồn tại | Duy trì kết nối hoặc reconnect khi gateway chuyển | Không mở rộng subnet được phép, giữ encryption/cipher policy |
| VPN login mới hợp lệ | Đăng nhập qua gateway/IdP dự phòng | Xác thực và MFA đúng yêu cầu |
| Login chưa đủ MFA | Thử tình huống IdP/MFA timeout | Không có phiên được cấp mà bỏ qua yếu tố bắt buộc |
| Thu hồi phiên hoặc tài khoản | Kiểm tra khả năng revoke theo chính sách | Trạng thái dự phòng không giữ quyền quá mức |
| Route/split tunnel | So sánh allowed networks trước và sau failover | Không mở default route hoặc route nội bộ trái phép |

Nếu giải pháp cho phép phiên đã xác thực hoạt động trong thời hạn cụ thể khi IdP lỗi, chính sách đó cần được phê duyệt và ghi rõ **giới hạn phiên**, điều kiện re-auth, cách thu hồi và log. Không coi duy trì phiên cũ là chấp nhận mọi đăng nhập mới.

### 10.2. AAA/NAC/802.1X

Khi RADIUS chính không phản hồi, test lần lượt **RADIUS phụ**, timeout, trạng thái cổng đã xác thực, cổng mới và phương án restricted VLAN nếu có.

Bộ ca thử phải gồm: endpoint hợp lệ, endpoint không hợp lệ, thiết bị không hỗ trợ 802.1X cần cơ chế thay thế theo policy, và guest device. Nếu fallback gán VLAN nhưng không có ACL hạn chế, đó có thể là **lỗi bảo mật** dù thiết bị vẫn lên mạng.

### 10.3. DNS resolver và DNS filtering

Chỉ kiểm tra \`dig\` trả lời không đủ. Cần xác minh:

- Internal split-horizon domain vẫn trả đúng record/vùng;
- Client thực sự hỏi resolver phụ đã được phê duyệt, không gửi truy vấn nội bộ ra public DNS;
- DNSSEC validation và chính sách DNS filtering còn nguyên (nếu áp dụng);
- Negative cache, TTL, stale answer hoặc DNS load balancing có thể ảnh hưởng thời gian phục hồi;
- Ứng dụng vốn dùng persistent connections có thể không tra DNS lại ngay;
- Cả UDP/TCP 53 và đường encrypted DNS do tổ chức quản lý (nếu có) đều được xét đúng thiết kế.

## 11. Kiểm thử IPS/IDS, WAF, load balancer và cloud

### 11.1. IPS inline hoặc WAF

Với IPS inline, xác nhận trạng thái khi sensor/inspection engine không healthy: **fail-closed, hardware bypass, phần tử dự phòng hoặc degraded inspection**. Nếu bypass được thiết kế, phải kiểm tra cảnh báo bypass độc lập và các chính sách firewall khác vẫn từ chối đường cấm.

Với WAF/reverse proxy, yêu cầu không chỉ là HTTP còn trả kết quả, mà còn là route, TLS certificate, authentication/session, rate limit và tập rule chính sách có còn áp dụng. Một proxy failover sang backend sai tenant hoặc bỏ xác thực là lỗi bảo mật nghiêm trọng.

Với **IDS passive**, sensor lỗi thường không làm gián đoạn data plane, nhưng phải phát hiện rõ mất khả năng quan sát và đánh giá khoảng trống telemetry trước khi kết luận hệ thống vẫn được giám sát.

### 11.2. Load balancer và hệ thống ứng dụng

Các phép thử phổ biến:

- Một backend app bị unhealthy, load balancer rút khỏi pool và đưa traffic sang backend còn healthy.
- Một instance mới được đưa vào pool chỉ sau khi health check ứng dụng đạt; tránh kiểm tra chỉ “port TCP open”.
- Session affinity/sticky session có được xử lý đúng với ứng dụng stateful không.
- Backend mới vẫn có quyền mạng tối thiểu, TLS, secrets, logging và role giống backend cũ.
- Cache và retry không che khuất lỗi transaction, không tạo giao dịch ghi trùng nếu client retry.

### 11.3. Cloud/VPC, Kubernetes và đa vùng

Trong môi trường cloud, kiểm thử có thể liên quan:

- Instance/availability zone lỗi: auto-healing và load balancer thay node; capacity, policy và secrets đúng ở node mới.
- Route table hoặc network virtual appliance failover: lưu lượng vẫn qua enforcement point bắt buộc.
- VPN/Direct Connect/ExpressRoute hoặc peering phụ: kiểm tra BGP/route advertisement, NAT và bảo vệ egress.
- Kubernetes node mất: pod được reschedule, Service/Ingress định tuyến đúng, NetworkPolicy tiếp tục được CNI thực thi.
- Identity/control-plane outage: workload cũ và workload mới có policy an toàn đã xác định; không tự mở quyền khi controller unreachable.
- Cross-region DR: kiểm tra identity, dữ liệu, encryption key, certificate, DNS/traffic manager và yêu cầu RPO nếu dữ liệu có bản sao.

**Kubernetes NetworkPolicy không tự hoạt động trên mọi CNI.** Việc kiểm thử phải xác minh hành vi enforcement trong môi trường thực, kể cả pod mới được tạo sau lỗi.

## 12. Thu thập bằng chứng và phân tích timeline

### 12.1. Các nguồn dữ liệu cần liên kết

| Nguồn | Bằng chứng | Giới hạn |
|---|---|---|
| HA manager / firewall | Thời điểm đổi role, policy sync, session table, rule decision | Role đã đổi không bảo đảm ứng dụng hoạt động |
| Router/switch/BGP | Neighbor event, route withdraw/install, interface counters | RIB/FIB đúng không khẳng định giao dịch end-to-end |
| Flow/PCAP | Gói mất/retransmission, hướng kết nối, trạng thái phiên | Không luôn thấy nội dung TLS/SSH hoặc quyết định xác thực |
| Client synthetic monitor | Success/failure, latency, DNS/TLS/HTTP details | Kết quả phụ thuộc vantage point, tần suất probe |
| DNS/IdP/VPN/NAC | Resolver, auth decision, session reconnect, VLAN mapping | Không có log có thể do chính backend gặp lỗi |
| Cloud audit/IaC | Route, SG, policy, node/pod, LB target changes | Có thể đến chậm, phải đối chiếu event time và collection time |
| SIEM/metrics | Alert phát ra, thời gian nhận, gap dữ liệu | Thời gian nhận không phải thời gian lỗi bắt đầu |
| Ứng dụng/database | Giao dịch thành công, lỗi, trạng thái dữ liệu/session | Cần đối chiếu network events để xác định nguyên nhân |

**Bảo toàn dữ liệu gốc** theo quy trình: timestamp và timezone, phiên bản cấu hình, hash hoặc storage reference nếu có, agent/sensor name, định danh request, người thao tác, mốc \`t0\`, clock offset và điều kiện mô phỏng lỗi.

### 12.2. Timeline mẫu

~~~text
09:59:55.000  BASELINE  P1 OK; N1 DENY; N2 DENY; FW-A active
10:00:00.000  TEST      Inject failure of FW-A in approved staging
10:00:07.000  DETECT    Health checker marks FW-A unhealthy
10:00:11.000  ROLE      FW-B active; policy version verified
10:00:16.000  RECOVER   Application probes meet stability condition
10:00:19.000  VERIFY    N1/N2 still DENY; no unexpected bypass observed
10:01:00.000  RESTORE   FW-A healthy, policy sync reestablished
10:02:00.000  FAILBACK  Controlled return per runbook
10:02:20.000  VERIFY    P1 OK; N1/N2 DENY; monitoring/HA stable
~~~

Đây là ví dụ minh họa. Đặc biệt, một kiểm tra N1/N2 sau khi hồi phục **không chứng minh** luồng bị cấm chưa từng mở trong 16 giây trước đó; phải probe/ghi log xuyên suốt khoảng chuyển đổi.

### 12.3. Chấm kết quả đúng phạm vi

- **PASS:** tiêu chí khả dụng, security invariants, rollback/failback và bằng chứng đạt theo phạm vi được định nghĩa.
- **FAIL:** bất kỳ invariant bắt buộc nào bị phá vỡ, hoặc chỉ số phục hồi vượt ngưỡng thống nhất.
- **INCONCLUSIVE:** thiếu dữ liệu để xác minh, công cụ đo lỗi, chưa mô phỏng được failure mode hoặc bài thử không thực hiện đúng tiền điều kiện.
- **BLOCKED / NOT RUN:** chưa đủ quyền thay đổi, standby không khỏe, thiếu OOB hoặc chưa có xác nhận cửa sổ kiểm thử.

Không tự đánh **PASS** chỉ vì không thấy lỗi trong log. Nếu log rơi mất đúng lúc failover, kết quả bảo mật có thể phải là *INCONCLUSIVE*, ngay cả khi ứng dụng phục hồi nhanh.

## 13. Ví dụ bài kiểm thử hoàn chỉnh: firewall HA bảo vệ web và database

### Bối cảnh

Doanh nghiệp có:

- **Internet → Web:** HTTPS/443 cho người dùng.
- **Web → Application:** backend HTTPS/8443.
- **Application → Database:** PostgreSQL TCP/5432 chỉ từ application tier.
- **User VLAN và Guest VLAN:** không được truy cập cổng quản trị hoặc database.
- **Firewall A/B:** HA có state/policy sync, management qua bastion/OOB.

Mục tiêu thử ở staging: chuyển từ A sang B, giữ ma trận P1/P2/N1/N2 và quan sát health checker, route, logging. Chẳng hạn mục tiêu **RTO giả định ≤ 30 giây**, không có luồng cấm thành công, và mọi thay đổi phải phục hồi được.

### Các bước thực hiện

**Chuẩn bị:** xác nhận B healthy, chính sách đồng bộ, đủ công suất, OOB sẵn sàng. Bật probe HTTPS có xác minh chứng chỉ và kết quả ứng dụng; từ application tier chạy giao dịch DB test không làm thay đổi dữ liệu quan trọng. Từ user/guest source, chạy phép thử kết nối bị cấm có kiểm soát và lưu firewall logs.

**Thử lỗi:** dùng cơ chế sản phẩm cho phép kích hoạt failover có kiểm soát ở staging, ghi \`t0\`. Theo dõi HA role, policy version, ARP/ND/route và từng kết quả probe.

**Đo:** thời điểm nhận lỗi, B nhận vai trò, số request thất bại, thời gian ứng dụng ổn định, session survival và thời gian log đến SIEM. Đối chiếu kết quả N1/N2 trong toàn cửa sổ.

**Phục hồi:** trả A về healthy, xác minh policy sync, failback có kiểm soát, lặp P1/P2/N1/N2 và xác nhận không flapping.

### Báo cáo giả lập

| Tiêu chí | Kết quả minh họa | Nhận xét |
|---|---|---|
| RTO ≤ 30s | 16s | PASS về thời gian |
| Positive P1/P2 | Phục hồi đúng sau 16s | PASS trong phạm vi |
| Negative N1/N2 xuyên failover | Bị chặn và có log enforcement | PASS trong phạm vi |
| HA policy parity | Cùng phiên bản trước và sau | PASS |
| Session continuity | 2/10 phiên cần reconnect | Theo tiêu chí session đã phê duyệt |
| Cảnh báo failover | SIEM nhận sau 4s | PASS nếu trong SLO cảnh báo |
| Failback | Ổn định, không flapping | PASS |

Nếu ứng dụng đạt 16 giây nhưng N1 được phép một lần trong giai đoạn chuyển tuyến, **bài test thất bại về bảo mật**. Khắc phục policy/route trước khi coi tính sẵn sàng cao là đạt yêu cầu.

## 14. Các sai lầm làm sai lệch kết quả kiểm thử

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ bấm nút “switchover” | Chưa thử mất nguồn, blackhole, split-brain hoặc link lỗi một chiều | Phân loại failure mode và thử theo từng điều kiện |
| Chỉ kiểm tra ping/VIP | Không biết ứng dụng, TLS, DNS, VPN, DB có thực sự khôi phục | Giao dịch end-to-end và session test |
| Chỉ thử traffic được phép | Không thấy route dự phòng bypass firewall hoặc NAC | Negative test xuyên suốt trước/trong/sau lỗi |
| Standby chưa đồng bộ policy | Trên standby có thể mở rule cấm | Kiểm tra parity và chặn takeover không an toàn theo thiết kế |
| Đồng hồ không đồng bộ | Timeline và RTO sai | Dùng cùng thời gian tham chiếu, ghi clock offset |
| Probe quá thưa | Bỏ qua mất kết nối ngắn hoặc bypass trong vài giây | Chọn chu kỳ theo RTO, bổ sung log thiết bị độ phân giải cao |
| Chỉ kiểm tra lúc ít tải | Bỏ sót standby thiếu capacity khi peak | Thử tải đại diện và giám sát saturation |
| Giả lập lỗi không tương đương lỗi thật | Kết luận vượt phạm vi đã thử | Ghi chính xác phương pháp injection và giới hạn |
| Không thử failback | Bỏ sót lỗi preemption, route dao động, session reset | Thử hướng trở lại và thời gian ổn định |
| Coi thiếu alert là không có sự cố | Mất telemetry trong khi failover | Kiểm thử độc lập kênh monitoring |
| Chỉ kiểm thử IPv4 | Bỏ sót đường IPv6 hoặc ACL không tương xứng | Kiểm tra hai họ địa chỉ theo phạm vi |
| Chạy cả hai đường dự phòng nhưng chung điểm lỗi | Cả hệ thống chết vì một phụ thuộc chung | Phân tích failure domain: nguồn, switch, DNS, IdP, region |
| Không giữ kết quả trước thay đổi | Không đối chiếu được baseline và nguyên nhân | Lưu cấu hình, probes, logs, test case version |
| Không định nghĩa điều kiện dừng | Sự cố thử nghiệm gây ảnh hưởng lan rộng | Gắn owner, thẩm quyền và rollback trước khi injection |

## 15. Checklist kiểm thử có thể sử dụng tại hiện trường

### Trước khi thử

- [ ] Có phạm vi, owner, cửa sổ bảo trì, sự chấp thuận và người phối hợp giữa Network/SRE/SOC.
- [ ] Có topology và các failure domain, đã xác nhận standby có đủ capacity.
- [ ] Có RTO/RPO/SLO, định nghĩa phục hồi ổn định và tiêu chí PASS/FAIL.
- [ ] Có ma trận luồng hợp lệ/bị cấm, bao gồm đường quản trị, VPN, DNS, AAA và IPv6 nếu sử dụng.
- [ ] Đã xác minh HA policy parity, state sync, NTP và kênh console/OOB.
- [ ] Có rollback, stop conditions, baseline và nơi lưu log/PCAP/metrics.

### Trong khi thử

- [ ] Ghi mốc injection \`t0\` và điều kiện lỗi thực sự.
- [ ] Chạy positive/negative tests xuyên suốt cửa sổ chuyển trạng thái.
- [ ] Quan sát detection, HA role, route, session, DNS, auth và ứng dụng.
- [ ] Kiểm tra split-brain, asymmetric routing, capacity và policy drift.
- [ ] Dừng test/rollback ngay nếu xuất hiện điều kiện dừng.

### Sau khi thử

- [ ] Đã kiểm tra phục hồi dịch vụ và thời gian ổn định thực tế.
- [ ] Đã xác minh quyền truy cập, segmentation, encryption, IPS/WAF và logging đúng chính sách.
- [ ] Đã kiểm thử failback và không có flapping hoặc mất cấu hình.
- [ ] Có báo cáo kết quả, độ tin cậy phép đo, điểm mù và vấn đề phải khắc phục.
- [ ] Có kế hoạch chạy lại sau khi sửa hoặc sau thay đổi kiến trúc quan trọng.

## 16. Câu hỏi tự kiểm tra và bài tập thực hành

1. Vì sao một cặp firewall HA có thể đạt thời gian failover rất ngắn nhưng vẫn thất bại về an ninh? Hãy nêu hai cách phát hiện.
2. Phân biệt thời gian phát hiện lỗi, chuyển vai trò và phục hồi ứng dụng. Nếu mỗi probe chạy cách nhau 10 giây, việc công bố RTO chính xác đến 1 giây có hợp lý không?
3. Nêu ba failure mode không được kiểm chứng chỉ bằng thao tác switchover chủ động.
4. Với VPN có MFA, bạn sẽ thử riêng phiên hiện hữu và đăng nhập mới như thế nào khi IdP mất kết nối?
5. Một switch 802.1X chuyển thiết bị chưa xác thực vào restricted VLAN khi RADIUS lỗi. Cần kiểm thử những luồng nào để chứng minh đó thực sự là VLAN hạn chế?
6. Khi route từ ISP A chuyển sang ISP B, những hệ thống dùng IP allowlist của đối tác hoặc VPN site-to-site có thể gặp vấn đề gì?
7. Nếu hệ thống không ghi được firewall logs trong 15 giây failover, có thể đánh PASS cho bất biến “guest không vào management” hay không? Cần thu thêm bằng chứng gì?
8. Dựng một test plan cho DNS primary/secondary có split-horizon và DNS filtering. Ghi expected result của cả truy vấn hợp lệ và truy vấn phải bị chặn.
9. Hãy liệt kê dữ liệu tối thiểu để tái lập một bài thử thất bại: điều kiện ban đầu, cấu hình, mốc lỗi, phương pháp injection, telemetry và rollback.
10. Thiết kế bộ kiểm thử gồm một lỗi active node, một lỗi blackhole data path, một lỗi AAA và một lần failback. Với mỗi case, ghi **positive check, negative check, thời gian mục tiêu, điểm dừng và chứng cứ cần lưu**.

**Điểm cần nhớ:** kiểm thử failover và khả năng phục hồi phải chứng minh đồng thời **dịch vụ trở lại trong giới hạn chấp nhận được** và **các ranh giới bảo mật không bị phá vỡ trong lúc hệ thống lỗi**. Kết quả đáng tin cậy phải có failure mode rõ ràng, phép đo từ nhiều lớp, bằng chứng xuyên suốt khoảng chuyển trạng thái, thử lại hướng failback và điều kiện rollback được xác định trước.
