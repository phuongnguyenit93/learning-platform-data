# DDoS runbook: chuẩn bị, ứng phó, giảm thiểu và khôi phục dịch vụ

## 1. Runbook DDoS là gì và dùng khi nào?

**DDoS runbook** là tài liệu vận hành mô tả **ai làm gì, dựa trên tín hiệu nào, theo trình tự nào và cần kiểm chứng điều gì** khi hệ thống có dấu hiệu bị tấn công **Distributed Denial of Service (DDoS)**. Mục tiêu không chỉ là chặn gói tin bất thường, mà còn **giữ dịch vụ hợp lệ hoạt động**, bảo vệ dữ liệu, giới hạn tác động tới người dùng, tránh gây gián đoạn do chính biện pháp ứng phó và khôi phục có bằng chứng.

DDoS xảy ra khi nhiều nguồn hoặc hạ tầng phát sinh lưu lượng/yêu cầu nhằm làm cạn **băng thông, tài nguyên xử lý trạng thái kết nối, năng lực ứng dụng hoặc một phụ thuộc quan trọng**. Một đợt tăng lưu lượng cao không mặc nhiên là DDoS: chiến dịch marketing, ra mắt sản phẩm, bot tìm kiếm hợp lệ và lỗi retry của chính hệ thống cũng có thể tạo ra triệu chứng tương tự.

Runbook trong bài này là **mẫu học tập trung lập với nhà cung cấp**, dành cho người học module **SECURITY_NETWORK_SECURITY**. Nó gắn kết các lớp phòng vệ **segmentation, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và cloud**, đồng thời thực hành phân tích lưu lượng, threat modeling, monitoring và xây dựng kiến trúc mạng có khả năng chịu sự cố.

**Nguyên tắc an toàn:** Chỉ áp dụng các thao tác ứng phó trên những tài sản, dịch vụ và thiết bị được giao quản lý; các thay đổi có thể làm mất kết nối như blackhole, thay route BGP, chặn diện rộng, vô hiệu hóa endpoint hoặc thay DNS phải qua thẩm quyền, kiểm tra tác động và cơ chế rollback rõ ràng.

### Sau bài học, bạn cần làm được

1. Viết runbook gồm **chuẩn bị → phát hiện → phân loại → kích hoạt → giảm thiểu → kiểm chứng → khôi phục → rút kinh nghiệm**.
2. Phân biệt tấn công bão hòa đường truyền, cạn tài nguyên L3/L4 và cạn tài nguyên L7; biết khi nào nhiều loại xảy ra đồng thời.
3. Chọn chỉ số **SLI/SLO, baseline, triệu chứng và ngưỡng** phù hợp, không nhầm lưu lượng lớn với sự cố an ninh.
4. Phân công **Incident Commander, Network/SRE, Security/SOC, ứng dụng, CDN/ISP và truyền thông** có quyền hạn rõ ràng.
5. Xây dựng bảng quyết định kiểm soát DDoS và xác minh không gây ảnh hưởng quá mức đến người dùng hợp lệ.
6. Lập kế hoạch diễn tập, hậu kiểm và cải tiến hệ thống lâu dài.

## 2. Phân biệt các kiểu DDoS để chọn đúng điểm giảm thiểu

| Kiểu / lớp | Tài nguyên bị tác động | Chỉ dấu thường gặp | Điểm giảm thiểu thích hợp |
| --- | --- | --- | --- |
| **Volumetric (L3/L4)** | Băng thông WAN, uplink, năng lực của nhà mạng | Bps/pps tăng mạnh, link saturation, packet loss trước firewall | ISP, cloud DDoS provider, scrubbing/Anycast, upstream filtering |
| **Protocol/state exhaustion** | Connection table, SYN backlog, session/NAT table, CPU thiết bị | SYN rate, connections, state allocation và timeout bất thường | SYN protection, rate/connection limits có scope, upstream L4 protection, capacity |
| **Application-layer (L7)** | HTTP/API workers, DB pool, CPU ứng dụng, cache, hàng đợi | Rps/rpm tăng hoặc không quá cao nhưng p95 latency/5xx/DB wait tăng | CDN, WAF/bot management, API gateway, per-identity quota, cache, circuit breaker |
| **DNS-targeted** | Authoritative DNS/resolver, băng thông UDP/TCP, backend DNS | DNS qps tăng, timeout, rcode phân bố lạ, cache miss | Anycast authoritative DNS, DNS rate limiting theo thiết kế, upstream protection |
| **Reflection/amplification** | Hạ tầng nạn nhân nhận traffic từ phản xạ | Nhiều UDP packets từ dịch vụ bên thứ ba, kích thước/phân bố bất thường | Anti-spoofing ở mạng nguồn (BCP 38), scrubbing upstream, filtering có điều kiện |
| **Multi-vector** | Nhiều lớp cùng lúc | Bps/pps và tải ứng dụng đều bất thường, mẫu thay đổi theo thời gian | Điều phối ISP/CDN/WAF/on-prem, quan sát nhiều lớp |
| **Resource/cost exhaustion** | Hạn mức tài nguyên cloud, autoscaling, băng thông tính phí | Requests làm tăng autoscaling/billing/egress dù chưa mất kết nối | Budget alerts, quotas, bot/rate policy, origin protection, resource guardrails |

**Lưu ý:** “L3/L4” và “L7” là cách phân loại **điểm tác động**, không có nghĩa chữ ký/mẫu lưu lượng luôn khớp một tầng duy nhất. Một lượng HTTP hợp lệ về cú pháp nhưng không hợp lệ về mục đích có thể làm DB cạn kết nối mà không cần đạt băng thông lớn. Ngược lại, một đường WAN bão hòa có thể khiến cả firewall, IDS và ứng dụng không nhận được lưu lượng để phân tích.

### 2.1. Cách suy luận nhanh từ triệu chứng

- **Ingress WAN 100% capacity + high packet loss:** Ưu tiên phối hợp **nhà mạng/điểm lọc upstream**, vì firewall ở phía sau đường nghẽn không thể mở lại băng thông đã bị bão hòa.
- **WAN chưa đầy nhưng firewall session/NAT table gần cạn:** Kiểm tra khả năng chống state exhaustion, các cấu hình timeout và điều kiện cho phép kết nối ở lớp mạng.
- **WAN bình thường, HTTP 5xx/latency tăng và DB pool cạn:** Xem traffic theo URL, identity, cache hit, request cost; ưu tiên biện pháp **L7** và bảo vệ phụ thuộc phía sau.
- **Chỉ DNS gặp vấn đề:** Xem authoritative DNS khác recursive resolver, qps, timeout và cơ chế cung cấp DNS trước khi thay toàn bộ firewall policy.
- **Cả người dùng thật và hệ thống giám sát đều thất bại:** Chưa thể khẳng định DDoS; kiểm tra triển khai ứng dụng, cert/TLS, DNS, routing, database và outage của nhà cung cấp.

## 3. Các vai trò, quyền quyết định và kênh liên lạc

Một runbook thiếu người chịu trách nhiệm thường thất bại ngay khi cần thay đổi khẩn cấp.

| Vai trò | Trách nhiệm trong sự cố | Quyết định / bằng chứng |
| --- | --- | --- |
| **Incident Commander (IC)** | Tổ chức chỉ huy, xác định mức độ, nhịp cập nhật, ưu tiên và kết thúc sự cố | Ghi timeline, phê duyệt chuyển pha theo chính sách tổ chức |
| **SOC/Security Analyst** | Phân tích dấu hiệu tấn công, threat intel, false positive, đề xuất giảm thiểu | Báo cáo phân loại, IOC có nguồn, mức tin cậy |
| **Network/Firewall Engineer** | Routing, ISP, firewall/ACL, VPN, NAT, traffic path, upstream escalation | Cấu hình trước/sau, route, counters, rollback |
| **SRE/Platform/Cloud** | Hạ tầng, load balancer, CDN/WAF, autoscaling, capacity, monitoring | SLI, error budget, dashboard, health của từng region |
| **Application/DB Owner** | API, cache, DB, queue, tác động nghiệp vụ, fallback | Tỷ lệ request hợp lệ, lỗi, tình trạng dependencies |
| **ISP/CDN/DDoS Provider** | Lọc/scrubbing lưu lượng theo hợp đồng và phạm vi được cấp | Ticket, mức bảo vệ, thời điểm áp dụng, tác động |
| **Communications/Support** | Thông báo đến người dùng, lãnh đạo, đối tác | Nội dung đã kiểm chứng, thời gian cập nhật kế tiếp |
| **Scribe/Incident Recorder** | Ghi mốc sự kiện, quyết định và kết quả phép thử | Nhật ký sự cố phục vụ handoff và postmortem |

Trong đơn vị nhỏ, một người có thể giữ nhiều vai trò, nhưng cần tách rõ **người đề xuất**, **người có quyền thực thi** và **người kiểm chứng** đối với thay đổi có nguy cơ gián đoạn rộng.

### 3.1. Danh bạ ứng phó cần chuẩn bị trước

Runbook thực tế phải có nơi quản lý cập nhật cho: người trực on-call, số liên hệ khẩn của ISP/CDN, account/ticket ID của nhà cung cấp, domain/IP/prefix được bảo vệ, quyền truy cập quản trị, escalation path, đường truyền dự phòng và kênh trao đổi khi hệ thống chat chính bị ảnh hưởng.

**Không lưu token API, private key, mật khẩu hoặc số điện thoại riêng tư trực tiếp trong tài liệu học/runbook chia sẻ rộng.** Chỉ liên kết tới hệ thống quản lý bí mật và danh bạ được cấp quyền.

## 4. Phân tích rủi ro và bản đồ dịch vụ trước sự cố

Mỗi dịch vụ cần một **service card** để IC không phải khám phá kiến trúc trong lúc đang bị tấn công.

~~~yaml
# Mẫu tài liệu, không phải cấu hình thực thi.
service_id: public-api
environment: production
business_owner: team-api
security_owner: soc
entrypoints:
  - api.example.org
dependencies:
  - authoritative-dns
  - edge-cdn-or-lb
  - api-gateway
  - application
  - database
  - external-authentication
critical_paths:
  - login
  - order-read
  - checkout
network_zones:
  - internet
  - edge
  - app
  - data
upstream_protection:
  - isp
  - ddos-provider
emergency_changes:
  allowed_by: approved-incident-policy
  rollback_owner: network-oncall
  change_record: required
~~~

Tên **example.org** và các trường trên chỉ dùng để minh họa. Trong triển khai thật cần gắn **địa chỉ IP/prefix, lưu lượng theo vùng, lớp ứng dụng, backend origin, chính sách ingress/egress và điểm kết thúc TLS** với hồ sơ có quyền truy cập phù hợp.

### 4.1. Vẽ đường đi traffic và nơi có thể nghẽn

~~~mermaid
flowchart LR
    U["Người dùng / Internet"] --> ISP["ISP / Upstream"]
    ISP --> CDN["CDN / DDoS edge"]
    CDN --> FW["Firewall / Load balancer"]
    FW --> API["API / App"]
    API --> DB[("Database")]
    DNS["Authoritative DNS"] -. "Phân giải hostname" .-> U
    CDN --> M["Edge telemetry"]
    FW --> N["Network telemetry"]
    API --> A["Application telemetry"]
~~~

Sơ đồ khái niệm: các thành phần có thể đặt ở thứ tự khác hoặc một phần do provider managed. Cần biết **chỗ giới hạn băng thông**, **chỗ có quyền lọc trước nghẽn**, **nơi giữ TLS/session state**, **đường bypass CDN đi thẳng tới origin**, và **các phụ thuộc mà người dùng cần để hoàn thành giao dịch**.

### 4.2. Xác định SLI/SLO có ý nghĩa với người dùng

Ví dụ với API:

| SLI | Đơn vị | Vì sao quan trọng? |
| --- | --- | --- |
| Request thành công theo endpoint trọng yếu | % trong cửa sổ xác định | Tách hoạt động tốt thực sự khỏi trạng thái thiết bị “UP” |
| HTTP 5xx / timeout của người dùng hợp lệ | % / số lượng | Thấy tác động dù hệ thống vẫn xử lý phần request khác |
| Latency p95/p99 | ms | Phát hiện nghẽn xử lý trước khi lỗi hoàn toàn |
| TCP/TLS handshake failure | % | Phân biệt sự cố đường truyền và ứng dụng |
| DNS availability + resolution latency | % / ms | Người dùng không truy cập được nếu không phân giải tên |
| Origin error / cache hit | % | Biết CDN có bảo vệ backend hay không |
| Link utilization / bps / pps | % capacity, bps, pps | Phân biệt bão hòa băng thông và state exhaustion |
| Concurrent sessions / SYN backlog / CPU | số lượng / % | Thấy tải firewall/LB khi lưu lượng không quá lớn |
| DB connection pool / queue depth | % / số lượng | Phát hiện dạng DDoS làm cạn phụ thuộc phía sau |

**Baseline** phải chia theo giờ, ngày, khu vực, loại endpoint, chiến dịch kinh doanh và thời điểm phát hành. Chỉ số tổng toàn site có thể che khuất việc một API quan trọng bị quá tải.

## 5. Chuẩn bị trước sự cố (PREPARE)

### 5.1. Danh mục năng lực giảm thiểu

Trước khi xảy ra DDoS cần biết **đúng nền tảng nào có thể làm gì**, ví dụ:

- **ISP / upstream scrubbing:** Tiếp nhận traffic lớn trước khi bão hòa uplink của tổ chức.
- **CDN, Anycast, DDoS provider:** Hấp thụ/phân tán lưu lượng, cache, lọc bot và một phần kiểm tra L7.
- **WAF/API gateway:** Lọc theo route, method, header, session, danh tính và ràng buộc ứng dụng.
- **Firewall/IPS:** Chặn những luồng có điều kiện L3/L4 phù hợp khi link còn tải được; bảo đảm policy an toàn sau failover.
- **Rate limiting theo identity / token:** Bảo vệ backend, phối hợp với quota và chính sách sản phẩm.
- **Application controls:** Cache, circuit breaker, queue, graceful degradation, timeout/retry budget, khả năng ưu tiên request quan trọng.
- **DNS provider:** Authoritative DNS có dự phòng, Anycast và bảo vệ trước lưu lượng DNS lớn.
- **Observability:** Network flow, firewall logs, IDS/IPS, DNS, CDN/WAF, application metrics, synthetic monitoring và cloud audit logs.

Hãy kiểm tra **năng lực theo hợp đồng, quy trình kích hoạt, điều kiện cần chuẩn bị (prefix/RPKI/route/credentials), điểm có thể làm đứt kết nối và chính sách thay đổi**. Không đợi sự cố mới kiểm tra nhà cung cấp có quyền bảo vệ prefix hay không.

### 5.2. Guardrails chống tự gây sự cố

1. Có **người phê duyệt** và giới hạn phạm vi cho từng loại mitigation.
2. Có **thời hạn tự động hết hiệu lực** hoặc lịch rà soát với rule khẩn cấp.
3. Có **allowlist hợp lệ có kiểm soát** cho health check, đối tác, service-to-service khi thực sự cần; không dùng allowlist như cách bỏ qua toàn bộ bảo vệ.
4. Có **canary/synthetic probes** từ các ISP, vùng địa lý và luồng nghiệp vụ khác nhau.
5. Có khả năng **rollback**, lưu cấu hình trước/sau và audit mọi thao tác.
6. Các biện pháp chặn theo **quốc gia, ASN, IP, User-Agent hoặc fingerprint** phải được đánh giá false positive vì chúng có thể ảnh hưởng người dùng hợp lệ.
7. Không vô hiệu hóa TLS, xác thực API, kiểm tra chứng chỉ hoặc phân đoạn Prod để “giảm tải” nếu không có quyết định rủi ro được phê duyệt.

### 5.3. Kế hoạch liên lạc ngoài băng

Khi DNS, SSO, VPN hoặc email doanh nghiệp không hoạt động, đội ứng phó cần **kênh dự phòng** không phụ thuộc toàn bộ vào dịch vụ đang hỏng. Kiểm tra trước quyền truy cập dashboard của provider, cầu hội nghị khẩn, danh sách liên hệ và quy trình công bố status page.

## 6. Phát hiện và xác nhận sự cố (DETECT)

**Một cảnh báo traffic cao chưa đủ kết luận DDoS.** Nên tổng hợp ít nhất **khả dụng của người dùng**, **áp lực hạ tầng** và **sự bất thường của lưu lượng**.

### 6.1. Nhóm tín hiệu

| Nhóm | Chỉ báo | Câu hỏi cần làm rõ |
| --- | --- | --- |
| **Availability** | Health check fail, HTTP 5xx/429, DNS timeout, handshake error | Dịch vụ nào không phục vụ được người dùng thật? |
| **Volume** | Bps, pps, Rps/Qps tăng, upstream drops | Chỗ nào cạn băng thông hoặc xử lý? |
| **Connection** | SYN/ACK ratio thay đổi, half-open, connection table pressure | Có thiếu state trên firewall/LB hay do retry storm? |
| **Application** | Một URL/operation chiếm CPU/DB pool, cache miss tăng | Có request đắt tiền hoặc dependency bị nghẽn? |
| **Distribution** | Nhiều nguồn/ASN/địa lý, đặc điểm request lặp lại | Đây là người dùng thật, crawler hợp lệ hay nguồn bất thường? |
| **Security** | IDS/IPS/WAF events, bot score, challenge pass rate | Rule đang phản ánh kỹ thuật hay chỉ dấu hiệu yếu? |
| **Operations** | Deploy, campaign, DNS change, autoscale failure, provider incident | Có nguyên nhân không phải tấn công không? |

**Lưu ý NAT/CDN:** Nhiều người dùng hợp lệ có thể chung một public IP; nhiều địa chỉ nguồn cũng có thể là proxy hoặc botnet. Không xếp loại chỉ dựa trên số lượng IP.

### 6.2. Kiểm tra đối chứng chống kết luận sai

Trước khi kích hoạt biện pháp diện rộng, kiểm tra:

- Có thay đổi **deploy, routing, firewall, DNS, certificate, backend capacity** ngay trước lúc tăng lỗi không?
- Có **khuyến mãi/sự kiện** dẫn đến traffic thật tăng không?
- Client có đang **retry quá nhanh** vì API chậm hoặc lỗi 429/503 không? Đây có thể là một **retry storm** do hệ thống tự gây ra.
- Provider edge báo nhận lưu lượng tăng hay chỉ **origin** báo tăng? Nếu chỉ origin tăng, kiểm tra đường CDN bypass, cache miss và route mới.
- Từ các nguồn quan sát độc lập, ảnh hưởng có lặp lại không? Một synthetic probe lỗi không chứng minh toàn dịch vụ bị DDoS.

### 6.3. Quy tắc kích hoạt minh họa

Các ngưỡng sau chỉ là **mẫu thảo luận**, không dùng làm cấu hình production:

~~~text
Điều kiện nghi ngờ:
  - Traffic hoặc tài nguyên > baseline tương ứng trong nhiều cửa sổ;
  - Đồng thời availability của ít nhất một luồng nghiệp vụ giảm; HOẶC
  - Provider/IDS/Network xác nhận dấu hiệu tấn công đáng tin cậy.

Điều kiện bắt đầu incident:
  - Có tác động người dùng, nguy cơ cạn tài nguyên rõ ràng
    hoặc threat signal đủ độ tin cậy;
  - On-call đánh giá và IC ghi nhận quyết định.

Không áp dụng quy tắc:
  - Một ngưỡng bps/rps tĩnh cho tất cả endpoint, mùa vụ và địa lý.
~~~

## 7. Xếp mức độ (SEVERITY) và kích hoạt chỉ huy

Tổ chức phải định nghĩa severity dựa trên **tác động nghiệp vụ, độ khẩn, phạm vi và khả năng mất dịch vụ**, không chỉ dựa trên số packets.

| Mức ví dụ | Tiêu chí tác động minh họa | Hành động |
| --- | --- | --- |
| **SEV-3 / Suspected** | Dấu hiệu lưu lượng bất thường, chưa có ảnh hưởng đáng kể tới dịch vụ | Mở sự kiện, thu metric, xác minh nguyên nhân, trực cảnh báo |
| **SEV-2 / Degraded** | Endpoint quan trọng tăng lỗi/độ trễ, đang dùng hết một phần đáng kể năng lực dự phòng | Bổ nhiệm IC, huy động Network/SRE/SOC, thông báo bên liên quan |
| **SEV-1 / Critical** | Giao dịch cốt lõi mất khả dụng trên diện rộng hoặc upstream gần/đã bão hòa, có nguy cơ lan rộng | Kích hoạt cầu ứng phó, cấp quyền escalation theo quy trình, phối hợp provider |

**Ví dụ:** 5 Gbps có thể làm nghẽn kết nối 1 Gbps nhưng vẫn nằm dưới năng lực thiết kế của mạng 100 Gbps. Vì vậy, **không dùng con số tĩnh** để gắn mức độ chung cho mọi hệ thống.

### 7.1. Trình tự khởi động incident

1. **On-call xác minh** alert, tác động và tính mới của sự kiện.
2. **IC nhận quyền điều phối**, mở incident ID/timeline, nêu mục tiêu ưu tiên và phạm vi dịch vụ.
3. **Scribe ghi nhận**: thời điểm đầu tiên, nguồn tín hiệu, những thay đổi gần đây và trạng thái hiện tại.
4. **Network/SRE/SOC** chia việc: đường truyền/upstream; cloud/CDN/WAF; ứng dụng và dữ liệu; đối chứng sự kiện.
5. **Comms** chuẩn bị thông báo nội bộ và status page nếu tác động người dùng đã được xác nhận.
6. **Handoff rõ người trực** khi incident kéo dài; không để một thay đổi quan trọng thiếu owner.

## 8. Runbook 15 phút đầu: phân loại và giữ hiện trạng

Thời gian trong ví dụ là **mốc phối hợp vận hành tham khảo**, không cam kết mọi DDoS được xử lý trong 15 phút.

| Mốc tham khảo | Câu hỏi chính | Việc nên làm | Bằng chứng cần ghi |
| --- | --- | --- | --- |
| **0–5 phút** | Có lỗi với người dùng thật không? | Xác minh synthetic monitor/SLI, tạo incident ID, khoanh dịch vụ | Error/latency, vùng người dùng, timestamp |
| **5–10 phút** | Nghẽn ở link, state hay ứng dụng? | So sánh WAN/CDN/LB/firewall/API/DB, kiểm tra deploy và DNS | Bps/pps/rps, top endpoints, route/provider status |
| **10–15 phút** | Điểm giảm thiểu nào chặn được trước bottleneck? | Chọn biện pháp phạm vi hẹp và nhà cung cấp có quyền xử lý; trình IC phê duyệt theo playbook | Phương án, expected effect, risk, rollback |
| **Xuyên suốt** | Mitigation có làm hại user hợp lệ không? | Duy trì health probes, so sánh allow/deny, ghi từng thay đổi | Synthetic pass rate, error rate, blocking metrics |

**Ưu tiên trong lúc cấp bách:** Không thay đổi đồng thời nhiều lớp nếu có thể thực hiện theo từng bước và đo tác dụng. Nếu bắt buộc nhiều biện pháp, ghi thứ tự, người thực hiện và mốc áp dụng để truy nguyên hiệu ứng.

### 8.1. Checklist thu bằng chứng ban đầu

- Thời gian UTC, incident ID, người chịu trách nhiệm, service/region/endpoint ảnh hưởng.
- **Ingress/egress bps, pps**, upstream drops, sử dụng link so với năng lực thực.
- **HTTP rps, status code, latency p95/p99**, lượng request theo endpoint/method.
- **TCP states / SYN backlog / conntrack / NAT capacity**, CPU firewall/LB.
- **DNS qps, timeout, resolver/authoritative status**, tình trạng TLS handshake.
- Phân bố traffic theo ASN/region/source **khi việc thu thập được phép**, tránh coi IP là danh tính chắc chắn.
- Trạng thái **CDN/WAF/ISP protection**, route và tần suất health-check.
- Các thay đổi triển khai/cấu hình trước thời điểm xảy ra lỗi.
- Chỉ số người dùng thật hoặc giao dịch quan trọng; thông tin này quyết định thành công ứng phó.

## 9. Cây quyết định chọn biện pháp giảm thiểu

~~~mermaid
flowchart TD
    A["Sự cố khả dụng được xác nhận"] --> B{"Link/uplink bão hòa?"}
    B -- "Có" --> C["Liên hệ ISP / scrubbing / provider upstream"]
    B -- "Không" --> D{"Firewall/LB state table bị áp lực?"}
    D -- "Có" --> E["L4 protections và connection controls có scope"]
    D -- "Không" --> F{"App/DB/API cạn tài nguyên?"}
    F -- "Có" --> G["WAF / API quota / CDN cache / app guardrails"]
    F -- "Không" --> H["Kiểm tra DNS, TLS, deploy, routing, dependency"]
    C --> I["Canary + SLI + false-positive validation"]
    E --> I
    G --> I
    H --> I
    I --> J{"Tác động đã giảm, user hợp lệ phục hồi?"}
    J -- "Chưa" --> K["Xét lớp tiếp theo và escalation"]
    J -- "Đạt" --> L["Ổn định, theo dõi, chuẩn bị khôi phục"]
    K --> B
~~~

**Quy tắc cốt lõi:** Biện pháp giảm thiểu phải được thực thi **trước tài nguyên đang nghẽn**, hoặc trực tiếp bảo vệ tài nguyên đó. Nếu đường 1 Gbps đã bị flood 10 Gbps, thêm firewall deny **sau** đường WAN chỉ có thể giảm tải downstream, không giải quyết bão hòa uplink.

## 10. Biện pháp cho volumetric và L3/L4 DDoS

### 10.1. Phối hợp ISP, scrubbing và Anycast

Khi xảy ra bão hòa upstream, đội mạng cần liên hệ **ISP/DDoS provider đã ký hợp đồng** để kích hoạt hoặc xác nhận lớp bảo vệ. Tùy nền tảng, lưu lượng có thể được đưa qua vùng **scrubbing** để lọc trước khi chuyển phần hợp lệ về origin.

**Bằng chứng cần xác minh:**

- Prefix/IP và dịch vụ được bảo vệ **đúng phạm vi**.
- Lớp lọc đã thực sự có hiệu lực ở **trước điểm nghẽn**.
- Đường traffic sạch trở lại có **route đối xứng** phù hợp và không làm mất các kết nối nghiệp vụ.
- Việc chuyển route có tác động đến **IPsec VPN, NAT, BGP policy, MTU, geolocation và firewall policy** không?
- Provider báo lượng traffic bị lọc, lượng traffic chuyển tiếp, false positives và health check thế nào?

**Anycast** có thể giúp phân tán yêu cầu đến nhiều vị trí edge, nhưng không phải phép bảo đảm mọi tấn công bị hấp thụ. Năng lực, độ phủ vùng, routing và kiểm soát chống abuse vẫn quyết định kết quả.

### 10.2. BGP FlowSpec, filtering và RTBH: phương án rủi ro cao

Một số mạng dùng **BGP Flow Specification (FlowSpec)** để phân phối chính sách lọc/rate-limit ở tầng mạng; **Remotely Triggered Black Hole (RTBH)** cho phép nhà mạng loại bỏ traffic tới/qua phạm vi được chỉ định nhằm bảo vệ phần còn lại của mạng.

**RTBH là biện pháp đánh đổi availability rất mạnh:** Traffic **hợp lệ đến đích bị blackhole cũng có thể bị mất**. Vì thế chỉ cân nhắc khi cần khoanh vùng khẩn cấp, theo chính sách đã được phê duyệt, với prefix/đích rõ ràng, owner, thời hạn và đường khôi phục. Không tự đề xuất blackhole toàn bộ production subnet vì chỉ một API bị tấn công.

FlowSpec cũng phải được quản lý **bên nhận tin cậy, scope prefix, điều kiện lọc, quyền kích hoạt, thời gian hiệu lực, giám sát, và rollback**. Cấu hình sai có thể làm gián đoạn nhiều dịch vụ hoặc lọc nhầm người dùng hợp lệ.

### 10.3. SYN / state exhaustion

Khi bottleneck là connection tracking, SYN backlog hoặc session table, những biện pháp **được nền tảng hỗ trợ và đã thử nghiệm** có thể gồm:

- SYN cookies/SYN proxy hoặc bảo vệ TCP handshake phù hợp.
- Connection limits theo endpoint/zone/nguồn, xét đặc tính CGNAT/proxy dùng chung.
- Timeout/state allocation được điều chỉnh thận trọng, không gây ngắt các phiên hợp lệ dài.
- Lọc gói tin có đặc điểm không hợp lệ theo chuẩn mạng và chính sách đang áp dụng.
- Giảm bề mặt dịch vụ công khai, chỉ mở protocol/port cần thiết.
- Tăng năng lực dự phòng nếu chi phí và thời gian triển khai phù hợp.

**Không dùng một mức giới hạn chung cho mọi IP** khi có nhiều người dùng hợp lệ phía sau NAT/CDN. Đối với ứng dụng cần kết nối dài (WebSocket, streaming, VPN), timeout hoặc connection cap quá thấp có thể gây sự cố rộng.

### 10.4. Reflection/amplification và anti-spoofing

Reflection/amplification phụ thuộc những dịch vụ trả lời traffic lớn tới địa chỉ được giả mạo. Phòng vệ dài hạn gồm:

- **Source address validation** theo BCP 38/BCP 84 (lọc địa chỉ nguồn giả trên mạng phù hợp).
- Không vận hành dịch vụ UDP phản xạ mở ngoài nhu cầu, giới hạn DNS/NTP và các dịch vụ tương ứng.
- DNS authoritative anycast, rate limiting được hiệu chỉnh và chống abuse theo nhà cung cấp.
- Phối hợp **upstream** để lọc traffic phản xạ đến nạn nhân trước khi bão hòa link.

**uRPF** có thể hỗ trợ chống spoofing trong một số thiết kế, nhưng strict uRPF có thể gây false drops khi có **asymmetric routing**; phải kiểm tra routing topology và lựa chọn chế độ đúng.

## 11. Biện pháp cho HTTP/API và các phụ thuộc L7

### 11.1. Xác định đơn vị giới hạn phù hợp

L7 DDoS không chỉ tính **requests/second** mà còn tính **chi phí của request**:

- Endpoint tìm kiếm không có cache có thể tốn nhiều CPU/DB hơn endpoint đọc dữ liệu tĩnh.
- Một người dùng có thể gửi ít request nhưng tạo nhiều truy vấn DB, queue jobs hoặc gọi dịch vụ bên thứ ba.
- Một request hợp lệ về cú pháp vẫn có thể làm cạn tài nguyên nếu thiếu quota, timeout, circuit breaker hoặc xác thực.

Vì thế cần theo dõi **rps theo route/method/identity**, cache hit, backend latency, DB connections, CPU time và error rate; không chỉ nhìn vào tổng request ở CDN.

### 11.2. Thứ tự biện pháp tham khảo

1. **Cache và edge offload:** Cache nội dung tĩnh/đáp ứng được phép cache, giảm request vào origin; kiểm soát cache key và dữ liệu cá nhân.
2. **Rate limit có scope:** Ưu tiên theo **token/user/API key/session + endpoint**, kết hợp IP chỉ khi phù hợp với đặc tính mạng.
3. **WAF/bot mitigation:** Rule theo pattern, hành vi, điểm tín nhiệm và challenge khi loại client hỗ trợ; đánh giá accessibility và tác động tới client API.
4. **Prioritize critical paths:** Ưu tiên login/checkout hoặc endpoint cần thiết theo mục tiêu nghiệp vụ; ngăn endpoint phụ làm cạn pool dùng chung.
5. **Circuit breaker/bulkhead:** Giảm lan truyền lỗi từ DB/queue/external APIs, giới hạn đồng thời và dùng timeout có kiểm soát.
6. **Graceful degradation:** Tạm bỏ tính năng phụ có chi phí lớn theo feature flag được phê duyệt, bảo toàn giao dịch cốt lõi.
7. **Autoscaling có guardrails:** Tăng năng lực khi phù hợp nhưng không coi đây là phòng vệ duy nhất; tránh **cost exhaustion** và giới hạn tài nguyên phụ thuộc.

### 11.3. HTTP 429, Retry-After và retry storm

Khi rate limit, server có thể trả **HTTP 429 Too Many Requests** và hướng dẫn retry phù hợp trong hợp đồng API. Client nên có **exponential backoff với jitter, giới hạn số lần retry và idempotency** cho thao tác ghi để không làm sự cố trầm trọng hơn.

**429 không chứng minh DDoS**: nó cũng có thể phản ánh chính sách quota bình thường. Tỷ lệ 429 tăng phải được đối chiếu với tỷ lệ giao dịch hợp lệ thất bại, backend saturation và dấu hiệu traffic bất thường. Không để một lớp WAF tự động chặn hàng loạt đối tác chỉ vì hệ thống phía sau đã trả 429.

### 11.4. Bảo vệ origin khỏi bypass

Nếu CDN/WAF lọc ở edge mà client vẫn có thể kết nối trực tiếp tới **public origin IP**, một phần lưu lượng có thể bỏ qua biện pháp. Cần xét:

- Origin chỉ nhận traffic qua đường/identity được cho phép từ edge hoặc private connectivity.
- Xác minh **đích thực** của kết nối; không chỉ tin header HTTP do client có thể tự đặt.
- Quản lý DNS, IP lịch sử, chứng chỉ, service discovery, các port phụ và IPv6.
- Đường health check, kênh quản trị và dự phòng vẫn hoạt động khi hạn chế origin ingress.

**Không lấy danh sách IP CDN tĩnh lâu năm để chặn origin mà không có quy trình cập nhật**, vì range/edge của nhà cung cấp có thể thay đổi và làm gián đoạn dịch vụ.

## 12. Runbook theo dịch vụ: DNS, VPN, cloud và thiết bị mạng

### 12.1. Khi authoritative DNS bị tấn công

Nếu tên miền không phân giải được, một ứng dụng đang khỏe vẫn không được người dùng truy cập. Cần phân biệt:

| Thành phần | Triệu chứng | Điểm cần kiểm tra |
| --- | --- | --- |
| **Authoritative DNS** | Resolver bên ngoài không lấy được bản ghi cho domain | Anycast DNS, provider availability, authoritative qps, timeout, DNSSEC và delegation |
| **Recursive resolver** | Chỉ một nhóm client/mạng không phân giải được | Resolver health, cache, upstream, rate limit, DoT/DoH policy |
| **Ứng dụng/LB** | DNS thành công nhưng HTTPS lỗi | TLS, CDN, route, firewall, origin, application |
| **DNS configuration** | Bản ghi sai, TTL không phù hợp, thay đổi NS/DS | Audit thay đổi, zone serial, policy và bản ghi thực tế |

Biện pháp có thể gồm nhà cung cấp DNS Anycast, phân tán authoritative nameservers, cơ chế chống quá tải theo tài liệu provider và bảo vệ resolver. **Không tắt DNSSEC, xóa toàn bộ bản ghi hoặc tự thay đổi delegation trong sự cố** nếu chưa đánh giá ảnh hưởng, thời gian lan truyền và quyền thực thi.

### 12.2. Khi endpoint VPN hoặc truy cập từ xa bị bão hòa

Nếu VPN gateway được đặt sau đường WAN bị flood, ưu tiên bảo vệ **uplink/ISP**; các rule tại VPN concentrator có thể quá muộn. Cần theo dõi **kết nối VPN mới, số phiên đồng thời, quá tải xác thực, IKE/handshake errors, client reconnect, MFA/IdP capacity** và đường dự phòng.

Biện pháp như giới hạn yêu cầu khởi tạo/nguồn, VPN gateway nhiều vùng, DDoS protection trước endpoint, điều phối client và quota phải giữ **xác thực mạnh và quyền truy cập tối thiểu**. Không tạm vô hiệu hóa MFA hoặc cấp đường vào subnet quản trị không được bảo vệ chỉ để tăng tỷ lệ kết nối thành công.

### 12.3. Khi tài nguyên cloud bị tăng tải hoặc vượt hạn mức

Cloud autoscaling có thể giữ dịch vụ hoạt động, nhưng cũng có giới hạn **instance quota, LB throughput, request quota, database connections và ngân sách**. Runbook cần theo dõi:

- Limit/quota theo resource và vùng; có thể tăng hay phải liên hệ nhà cung cấp?
- Load balancer/Anycast/CDN/DDoS service đã được bật đúng tài khoản, region, endpoint?
- Firewall/security group/network policy có tạo bottleneck sau khi scale out?
- Chi phí egress, WAF request processing và compute có tăng quá mức dự tính?
- Có **cloud control plane permissions** cho automation và audit mọi route/policy change?

Nếu chuyển traffic sang region khác, cần xác minh **data residency, DNS, certificate, database replication, quyền service, RTO/RPO** và hạn chế cross-region traffic. Chuyển region không phải cách chữa DDoS mặc định nếu nơi dự phòng không có dữ liệu/ứng dụng sẵn sàng.

### 12.4. Khi firewall hoặc IPS trở thành bottleneck

Ở một đợt DDoS, firewall có thể bão hòa CPU, **session table**, log pipeline hoặc inspection engine. Không mặc định tắt IPS sẽ giải quyết nếu **link upstream đã đầy**. Kiểm tra đúng lớp nghẽn, phân tách **data plane** và **control plane**, giám sát rule hits và mất gói.

Chế độ **fail-open/fail-closed** phải tuân theo chính sách rủi ro; không bỏ kiểm soát bảo mật ở đường vào dữ liệu nhạy cảm mà thiếu thẩm quyền. Nếu cụm HA chuyển node, đo cả **route convergence, NAT state, VPN reconnect và tính hiệu lực của DENY rules**.

## 13. Ma trận chọn biện pháp và tác động phụ

| Biện pháp | Khi thường hữu ích | Nguy cơ ảnh hưởng người dùng hợp lệ | Kiểm tra trước/sau |
| --- | --- | --- | --- |
| **Upstream scrubbing** | Bão hòa mạng, flood diện rộng | Route sai, MTU, traffic hợp lệ bị lọc, tăng latency | Bps sạch, route, synthetic probes từ nhiều vùng |
| **Anycast/CDN** | Public website và static content, phân tán edge | Cache sai, origin bypass, edge-specific outage | Cache hit, origin RPS, HTTPS/SSL behavior |
| **WAF rule theo URL/method** | Mẫu request HTTP rõ, có scope ứng dụng | Chặn API/endpoint hợp lệ, false match | Valid requests, WAF decision, HTTP 4xx/5xx |
| **Challenge/bot mitigation** | Truy cập trình duyệt cần phân biệt automation | API client, accessibility, người dùng ở mạng khó khăn | Challenge pass, conversion, error/drop theo cohort |
| **Per-user/API-key quota** | API có identity ổn định và nhu cầu hạn mức | Khách hàng hợp lệ dùng nhiều bị throttled | SLI theo tenant, 429 rate, support reports |
| **IP-based rate limit** | Nguồn hạn chế/đã xác minh có hành vi bất thường | CGNAT, proxy, VPN, CDN share IP | False positive theo nguồn/ASN, scope/TTL |
| **SYN protection/connection limits** | Cạn state L4, có traffic mới bất thường | Ảnh hưởng handshake, kết nối dài, thiết bị NAT | SYN backlog, app success, session failures |
| **DNS protection** | Authoritative/resolver qps bị quá tải | DNS hợp lệ timeout, ảnh hưởng resolver dùng chung | Resolution latency, rcode, availability theo vùng |
| **Caching, bulkhead, circuit breaker** | L7 làm cạn backend/DB | Dữ liệu cũ, tính năng phụ giảm chất lượng | Business SLI, data correctness, backend load |
| **RTBH / blackhole** | Phương án cô lập khẩn cấp để cứu hạ tầng khác | **Từ chối cả traffic hợp lệ tới đích** | Phê duyệt cấp cao, đích, phạm vi, TTL, rollback |
| **Geo/ASN restriction** | Chỉ khi có tín hiệu mạnh và được chấp nhận rủi ro | Chặn user du lịch, CDN/proxy hợp lệ, đối tác | Business geography, allowlist, impact review |

**Mọi biện pháp cần có:** *owner, lý do, phạm vi cụ thể, điều kiện bắt đầu, thời điểm thực thi, mức tác động dự kiến, metric kiểm chứng, thời hạn, phê duyệt và rollback*. Không được coi “mitigation enabled” là dấu hiệu thành công nếu người dùng hợp lệ vẫn không dùng được dịch vụ.

## 14. Theo dõi trong lúc giảm thiểu (MITIGATE & VERIFY)

### 14.1. Hai câu hỏi bắt buộc sau mỗi thay đổi

**Câu 1 – Có giảm ảnh hưởng từ traffic không mong muốn?** Ví dụ, băng thông qua điểm nghẽn giảm, firewall không còn cạn state, origin request load giảm, DB pool phục hồi.

**Câu 2 – Người dùng hợp lệ có hoạt động tốt hơn và có bị chặn sai không?** Kiểm tra synthetic checkout/login, giao dịch từ nhiều nhà mạng/region, error rate, API client và partner integrations. **Tổng lượng traffic giảm không chứng minh mitigation tốt** nếu tất cả request hợp lệ cũng bị chặn.

### 14.2. Decision log theo thay đổi

~~~text
INCIDENT: INC-EXAMPLE-2026
UTC_TIME: 2026-01-10T10:30:00Z
SERVICE: public-api
OWNER: network-oncall / incident-commander
HYPOTHESIS: upstream link saturation is dominant
CHANGE: enable provider mitigation for approved service scope
EXPECTED: reduce WAN loss without denying legitimate checkout flows
RISKS: route changes, false-positive filtering, increased RTT
VALIDATION: edge bps/pps, origin requests, checkout synthetic success
ROLLBACK_TRIGGER: legitimate success rate falls or routing deviates
APPROVAL: recorded in authorized incident channel
EXPIRY_OR_REVIEW: defined by incident lead
RESULT: pending verification
~~~

Đây là **mẫu ghi nhận**, không phải lệnh thao tác. Dấu thời gian và ID minh họa không phản ánh một sự cố có thật.

### 14.3. Kết hợp thời gian và nguồn quan sát

Các log của ISP, CDN, firewall, DNS và ứng dụng có thể có **múi giờ, độ trễ ingest, sampling và định nghĩa request khác nhau**. Khi so sánh, quy đổi UTC, ghi rõ loại timestamp và cửa sổ thời gian. Nếu hệ thống không thể thu toàn bộ log khi quá tải, phải ghi **data gap** thay vì khẳng định không có sự kiện.

Nếu CDN edge báo lượng traffic 100.000 rps nhưng origin chỉ thấy 2.000 rps, điều đó có thể phản ánh cache/filtering; không suy rằng mọi request còn lại đều độc hại. Cần dữ liệu về **cache hits, challenges, edge actions và error distribution**.

## 15. Truyền thông trong incident

Truyền thông tốt làm giảm nhiễu cho đội kỹ thuật và giúp người dùng điều chỉnh hành vi (ví dụ tránh retry liên tục khi giao dịch chưa xác nhận).

### 15.1. Mẫu cập nhật nội bộ

~~~text
INCIDENT ID: <mã>
STATUS: Investigating / Mitigating / Monitoring / Resolved
SEVERITY: <mức được IC xác nhận>
UTC: <thời điểm cập nhật>
IMPACT: <dịch vụ, khu vực, hành trình người dùng bị ảnh hưởng>
EVIDENCE: <SLI, nguồn giám sát; phần nào chưa xác minh>
MITIGATION: <hành động đã được phê duyệt và áp dụng>
CURRENT RESULT: <tác động đã đo; false positives nếu có>
RISKS: <giới hạn còn lại / đường đi phụ thuộc>
NEXT UPDATE: <mốc theo lịch điều phối>
OWNER: <vai trò, kênh liên hệ được phép>
~~~

### 15.2. Mẫu thông báo tới người dùng

> “Chúng tôi đang điều tra tình trạng truy cập chậm hoặc gián đoạn đối với [dịch vụ] tại [phạm vi]. Đội vận hành đang triển khai các biện pháp khôi phục và tiếp tục theo dõi. Chúng tôi sẽ cập nhật khi có thông tin đã xác minh.”

Nếu chưa xác nhận DDoS, **không khẳng định có tấn công**, mất dữ liệu hoặc nguồn tấn công cụ thể. Không công khai IP origin bí mật, cấu hình lọc, danh sách bypass hoặc thông tin có thể làm tăng rủi ro khi sự cố còn diễn ra.

### 15.3. Ngăn quyết định mâu thuẫn

Mọi thay đổi upstream/CDN/firewall cần một **decision log chung**. Không để hai đội đồng thời thay TTL DNS, route BGP, ruleset WAF và firewall filter mà không có thứ tự, người kiểm chứng và rollback. Nếu có nhiều miền trách nhiệm, IC phải xác nhận **hành động nào đang giữ traffic và action nào có thể gây gián đoạn**.

## 16. Khôi phục có kiểm soát (RECOVER)

Sau khi lưu lượng giảm, việc **tắt ngay mọi mitigation** có thể khiến tấn công hoặc tăng tải quay trở lại. Pha recovery cần mục tiêu và tiêu chí rõ ràng:

1. **Ổn định:** Đảm bảo SLI ở các hành trình trọng yếu hồi phục qua đủ cửa sổ quan sát, không chỉ một lần thành công.
2. **Kiểm tra tồn dư:** Xem DB queue/backlog, connection pools, rate-limit state, cache, retries và job xử lý còn tồn đọng.
3. **Phân loại mitigation:** Biện pháp nào chỉ dùng khẩn cấp, biện pháp nào là cải tiến bảo mật cần giữ lại sau review?
4. **Gỡ dần thay đổi tạm:** Tháo các rule có scope rộng, hạn mức quá chặt hoặc route diversion theo **thứ tự được phê duyệt**, đo SLI sau mỗi bước.
5. **Kiểm tra người dùng hợp lệ:** API partners, login, checkout, vùng địa lý ít traffic, IPv6, DNS và VPN nếu liên quan.
6. **Đóng đường bypass:** Nếu đã mở ngoại lệ tạm cho health check, support hoặc partner, đảm bảo không để lại quyền ngoài chính sách.
7. **Lưu bằng chứng:** Incident timeline, cấu hình trước/sau, tickets provider, metrics và các quyết định/ngoại lệ.
8. **Handoff:** Chuyển từ war room sang monitoring/operations với owner và lịch rà soát.

### 16.1. Tiêu chí đóng incident mẫu

| Tiêu chí | Cách xác minh |
| --- | --- |
| Các luồng nghiệp vụ trọng yếu đạt mức SLO theo cửa sổ được xác định | Synthetic và application telemetry |
| WAN/CDN/firewall/origin không còn cạn năng lực | Network/provider dashboard và capacity metrics |
| DNS/TLS/VPN và endpoint liên quan hoạt động hợp lệ | Probes và logs từ đúng vị trí |
| Chặn sai giảm về mức chấp nhận được | WAF/IPS false-positive review và business indicators |
| Các route/rule khẩn cấp có owner, expiry hoặc đã rollback | IaC diff, change log, provider ticket |
| Log, backup, audit và IAM vẫn đúng chính sách | Kiểm tra kiểm soát sau ứng phó |
| Có theo dõi tái phát và lịch postmortem | Incident handoff, on-call và action items |

**Resolved** không nhất thiết có nghĩa đã tìm ra danh tính tác nhân tấn công. Nó có nghĩa dịch vụ đã hồi phục theo tiêu chí và tổ chức đã xác định các công việc điều tra/cải tiến còn lại.

## 17. Post-incident review và cải tiến kiến trúc

Postmortem nên tập trung vào **sự kiện và hệ thống**, tránh quy trách nhiệm cảm tính khi chưa có bằng chứng.

### 17.1. Những câu hỏi cần trả lời

- Thời điểm đầu tiên hệ thống thấy tín hiệu là khi nào, **tác động người dùng bắt đầu** lúc nào?
- Sự cố nghẽn **uplink, firewall state, DNS, origin, DB hay dependency**? Có bao nhiêu lớp xảy ra cùng lúc?
- **Detection delay, escalation delay, mitigation activation delay và application recovery time** là bao nhiêu?
- Tại sao traffic hợp lệ bị ảnh hưởng? Có tỷ lệ false-positive hoặc challenge failure không?
- Nhà cung cấp upstream/CDN phản ứng như thế nào? Hợp đồng và quyền kích hoạt có phù hợp?
- Có **đường bypass origin**, route không đối xứng, subnet không được bảo vệ, hạn mức cloud hay phụ thuộc đơn lẻ nào?
- Có rule khẩn cấp, quyền IAM hoặc bypass còn sót sau sự cố không?
- Runbook thiếu bước, quyền, công cụ, chủ sở hữu hay dashboard nào?

### 17.2. Theo dõi chỉ tiêu cải tiến

| Chỉ tiêu | Định nghĩa | Mục đích |
| --- | --- | --- |
| **Time to detect** | Từ tác động/tín hiệu được chọn đến khi phát hiện hợp lệ | Giảm độ trễ phát hiện |
| **Time to engage** | Từ phát hiện đến khi IC/provider phù hợp tham gia | Kiểm tra escalation và quyền sẵn có |
| **Time to mitigate** | Từ lúc quyết định đến khi tác động bắt đầu giảm có bằng chứng | Đo hiệu quả hành động kỹ thuật |
| **Time to recover** | Từ sự cố đến khi hành trình người dùng hồi phục ổn định | Đo kết quả cuối cùng |
| **False positive impact** | Người dùng/giao dịch hợp lệ bị chặn nhầm | Ngăn “bảo vệ thành gián đoạn” |
| **Repeat attack resilience** | Kết quả khi traffic tương tự quay lại trong diễn tập | Xem bài học đã chuyển thành năng lực chưa |

Các định nghĩa thời điểm phải được **chốt trước**; nếu mỗi sự cố tính theo điểm bắt đầu khác nhau, không nên so sánh MTTR như một chỉ số duy nhất.

### 17.3. Backlog cải tiến

Một bảng action item tối thiểu:

| Vấn đề | Hành động | Owner | Cách xác minh |
| --- | --- | --- | --- |
| Link ISP bị nghẽn trước firewall | Kích hoạt upstream protection/thiết kế dự phòng có hợp đồng | Network | Diễn tập provider-approved, đo synthetic |
| Origin công khai bypass CDN | Giới hạn ingress origin theo đường/identity được duyệt | Platform | Test không thể truy cập bypass trái quyền |
| API search làm cạn DB pool | Quota theo route/user, cache, bulkhead | Application | Load test hợp lệ trong lab và SLI |
| Không thấy attack do traffic path thay đổi | Bổ sung sensor/flow metrics theo cả nhánh HA | SOC/Network | Kiểm chứng coverage sau failover |
| Rule emergency không có expiry | Policy-as-code, ticket bắt buộc, TTL/review | Security | Audit sau diễn tập và sau incident |
| Không liên hệ được ISP on-call | Kiểm tra hợp đồng và diễn tập escalation | IC/Procurement | Provider acknowledgment trong drill |

## 18. Thực hành offline: phân loại tín hiệu và đánh giá mức nghi ngờ

Đoạn Python sau chỉ dùng **dữ liệu mô phỏng** để minh họa một cách tổng hợp nhiều tín hiệu. Nó **không gửi traffic**, không quét mạng, không thay policy và không kích hoạt mitigation. Quy tắc đưa ra nhãn **“needs_triage”**, không tự khẳng định đã xảy ra tấn công.

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class TrafficWindow:
    name: str
    observed_mbps: float
    baseline_mbps: float
    link_capacity_mbps: float
    error_rate: float
    baseline_error_rate: float
    app_latency_p95_ms: float
    baseline_latency_p95_ms: float
    deploy_in_window: bool


def triage(window: TrafficWindow) -> dict:
    """Phân loại tín hiệu để điều tra, KHÔNG quyết định chặn traffic."""
    if window.baseline_mbps <= 0 or window.link_capacity_mbps <= 0:
        raise ValueError("Baseline and capacity must be positive")
    if not 0 <= window.error_rate <= 1:
        raise ValueError("Error rate must be between 0 and 1")

    traffic_ratio = window.observed_mbps / window.baseline_mbps
    link_utilization = window.observed_mbps / window.link_capacity_mbps
    errors_increased = window.error_rate > max(
        0.05, window.baseline_error_rate + 0.03
    )
    latency_increased = (
        window.app_latency_p95_ms
        > 2 * window.baseline_latency_p95_ms
    )
    infrastructure_pressure = link_utilization >= 0.85
    user_impact = errors_increased or latency_increased

    return {
        "name": window.name,
        "needs_triage": user_impact and (
            traffic_ratio >= 3 or infrastructure_pressure
        ),
        "potential_link_pressure": infrastructure_pressure,
        "user_impact": user_impact,
        "deployment_is_alternative_explanation": window.deploy_in_window,
    }


windows = [
    TrafficWindow("normal", 100, 100, 1000, 0.001, 0.001,
                  80, 80, False),
    TrafficWindow("campaign", 500, 100, 1000, 0.002, 0.001,
                  90, 80, False),
    TrafficWindow("suspected_saturation", 920, 100, 1000,
                  0.15, 0.001, 450, 80, False),
    TrafficWindow("deploy_related", 120, 100, 1000,
                  0.20, 0.001, 400, 80, True),
]

for item in windows:
    result = triage(item)
    print(
        result["name"],
        "needs_triage=", result["needs_triage"],
        "user_impact=", result["user_impact"],
        "link_pressure=", result["potential_link_pressure"],
    )
~~~

Kết quả dự kiến:

~~~text
normal needs_triage= False user_impact= False link_pressure= False
campaign needs_triage= False user_impact= False link_pressure= False
suspected_saturation needs_triage= True user_impact= True link_pressure= True
deploy_related needs_triage= False user_impact= True link_pressure= False
~~~

**Cách đọc:** “campaign” tăng traffic 5 lần nhưng chưa tác động người dùng; chưa đủ để khẳng định sự cố. “suspected_saturation” cần điều tra do liên quan tải đường truyền và lỗi. “deploy_related” có tác động người dùng nhưng không đủ tín hiệu về tăng tải đường truyền; đây là trường hợp cần **kiểm tra deploy, ứng dụng và dependency** thay vì tự bật DDoS filter.

**Giới hạn nghiêm ngặt:** Các ngưỡng **3 lần baseline, 85% link, 5% error, 2 lần latency** được chọn **chỉ để dạy cách kết hợp tín hiệu**, không phải khuyến nghị vận hành. DDoS L7 lưu lượng thấp có thể bị ví dụ này bỏ sót; cũng có thể có volumetric DDoS chưa gây impact nhờ upstream protection. Mẫu không có ground truth, không thể dùng tính chính xác/recall của detector production.

### Bài tập mở rộng

1. Thêm **API request rate, DB pool usage, CDN blocked/request ratio** để mô tả DDoS L7 trong khi Mbps không tăng.
2. Thêm một cửa sổ có **upstream mitigation đã bật**, traffic tại origin thấp nhưng provider thấy lưu lượng rất cao; giải thích vì sao detector chỉ nhìn origin có thể bỏ sót.
3. Đổi baseline theo ngày/giờ và thêm trường **region**; phân tích rủi ro của một ngưỡng toàn cầu.
4. Viết hàm chỉ tạo **triage ticket** với các metric và lý do, tuyệt đối không tự gọi API chặn.
5. Định nghĩa các ca **false positive / false negative** sau khi có dữ liệu kiểm thử đã gán nhãn.

## 19. Diễn tập tabletop và kiểm thử không gây hại

DDoS drill **không cần phát sinh lưu lượng tấn công thật**. Có thể kiểm chứng phần lớn quy trình thông qua **tabletop exercise**, log mô phỏng, phân tích cấu hình, synthetic probe được phê duyệt và kiểm thử tải **hợp pháp, có giới hạn** trong môi trường phù hợp.

### 19.1. Kịch bản tabletop A – Web/API bị nghẽn

**Bối cảnh:** Monitoring báo p95 tăng, HTTP 5xx tăng; CDN thấy Rps tăng, origin DB pool đã đầy nhưng WAN còn dư.

**Câu hỏi cho đội ứng phó:**

1. Ai xác nhận tác động, bổ nhiệm IC và liên hệ application owner?
2. Dữ liệu nào cho thấy đây là L7 overload chứ không phải volumetric?
3. Giảm tải qua cache, API quota, bulkhead và circuit breaker theo thứ tự nào?
4. Kiểm chứng false positives với người dùng thật và đối tác ra sao?
5. Điều kiện để rollback WAF rule nếu tỷ lệ giao dịch hợp lệ giảm?

### 19.2. Kịch bản tabletop B – WAN bão hòa

**Bối cảnh:** ISP báo lượng bps lớn vượt uplink, firewall/IPS phía sau chỉ thấy traffic thấp vì đã có packet drops ở upstream.

**Câu hỏi:** Ai có quyền gọi provider scrubbing? Prefix nào được phép bảo vệ? Cần đo route/MTU/VPN và health như thế nào? Khi nào tuyệt đối không nên áp dụng RTBH vì nó sẽ làm mất toàn bộ truy cập vào dịch vụ cần bảo vệ?

### 19.3. Kịch bản tabletop C – False positive của biện pháp khẩn cấp

**Bối cảnh:** Rate limit theo IP làm các đối tác đi qua cùng một NAT bị 429 hàng loạt.

**Câu hỏi:** Có thể phân biệt theo tenant/API key, route hoặc session không? Hạn mức đã dùng có phù hợp không? Làm sao rollback **đúng rule**, giữ được bảo vệ khác và giải thích tác động trong thông báo sự cố?

### 19.4. Ma trận validation tổng hợp

| Test ID | Kịch bản an toàn | Kết quả mong đợi |
| --- | --- | --- |
| DD-01 | Alert traffic tăng nhưng health vẫn tốt trong log giả lập | Chưa tự kết luận DDoS; mở triage theo bằng chứng |
| DD-02 | User error tăng sau deploy, WAN bình thường | Điều tra nguyên nhân release/app trước khi lọc diện rộng |
| DD-03 | Upstream saturation được báo bởi ISP | Escalate đúng provider và thu được thông tin scope/ticket |
| DD-04 | CDN lọc lượng lớn requests, origin SLI tốt | Đo cả legitimate success, không lấy số bị chặn làm tiêu chí duy nhất |
| DD-05 | WAF alert-only rule mới trên dữ liệu test | Không làm ngắt giao dịch hợp lệ |
| DD-06 | API partner dùng chung IP qua NAT | Chính sách quota không chặn diện rộng chỉ theo source IP |
| DD-07 | Origin bypass được kiểm tra từ phạm vi kiểm thử có phép | Đường trực tiếp không vượt kiểm soát CDN/origin access |
| DD-08 | DNS provider đang chậm | Có thông tin phân biệt authoritative, resolver và app |
| DD-09 | VPN gateway quá tải nhưng MFA khỏe | Chọn biện pháp upstream/capacity, không vô hiệu hóa MFA |
| DD-10 | Cụm firewall failover trong lab | Network telemetry và chính sách DENY vẫn đúng |
| DD-11 | Provider activation thay route trong lab/staging | Return path, NAT, MTU, health của traffic hợp lệ được kiểm tra |
| DD-12 | Quy tắc lọc mới gây false positive | Rollback có thẩm quyền, log và kiểm chứng dịch vụ phục hồi |
| DD-13 | Tấn công giảm trong bản ghi mô phỏng | Gỡ mitigation có thứ tự sau khi theo dõi đủ cửa sổ |
| DD-14 | Kênh SSO/email nội bộ mất trong tabletop | Đội có đường liên lạc và truy cập provider dự phòng |
| DD-15 | Truy vấn cloud costs/quota tăng | Có guardrail và người phụ trách chi phí khi autoscaling |
| DD-16 | Kết thúc diễn tập | Có timeline, action owners, SLI, tài liệu cải tiến và ngày kiểm tra lại |

Mọi phép thử ảnh hưởng hệ thống thật cần **phạm vi, authorization, giới hạn tải và người giám sát**. Không thực hiện flood thử nghiệm vào Internet hay dịch vụ bên ngoài không thuộc quyền quản lý.

## 20. Case study: giảm lưu lượng nhưng khách hàng vẫn không mua được hàng

**Tình huống giả định:** Trang thương mại điện tử dùng CDN/WAF trước origin. Khi traffic tăng đột ngột, đội vận hành đặt giới hạn **100 requests/phút trên mỗi IP** cho toàn bộ website. Dashboard WAF cho thấy số request đến origin giảm mạnh, nhưng tỷ lệ hoàn tất thanh toán của khách hàng cũng giảm.

### 20.1. Phân tích nguyên nhân

| Quan sát | Điều có thể suy ra | Điều cần xác minh |
| --- | --- | --- |
| Origin RPS giảm 70% | Có giảm tải tới origin | Bao nhiêu request hợp lệ bị block hoặc 429? |
| Checkout conversion giảm | Trải nghiệm người dùng bị ảnh hưởng | Tỷ lệ lỗi theo API, tenant/region, NAT networks |
| Một số IP phát sinh nhiều request | Có lưu lượng tập trung ở IP | IP là CGNAT, ISP proxy, đối tác hay nguồn tự động bất thường? |
| WAF block rate tăng | Rule đang thực thi | Rule match đúng hành vi không mong muốn hay quá rộng? |
| DB load giảm nhưng 5xx vẫn cao | Nghẽn có thể còn ở lớp khác | Retry storm, cache, dependency, app health |

### 20.2. Hướng khắc phục theo runbook

1. IC xác nhận **kết quả kinh doanh bị ảnh hưởng**, không tuyên bố thành công chỉ dựa vào RPS.
2. SOC/SRE kiểm tra **từng endpoint**, loại request, token/tenant, challenge và tỷ lệ thành công.
3. Thay giới hạn IP toàn site quá rộng bằng **quota theo identity và endpoint** hoặc biện pháp phù hợp được phê duyệt; giữ quan sát L7.
4. Xem xét **caching** cho nội dung ít thay đổi, giảm áp lực tới DB nhưng không cache sai dữ liệu nhạy cảm.
5. Test nhiều nhóm người dùng hợp lệ, trong đó có đối tác đi qua NAT, người dùng mobile và luồng thanh toán.
6. Theo dõi rollback/canary, cập nhật quyết định và thời hạn của biện pháp tạm.

### 20.3. Kết quả mong muốn

**Thành công** phải được đo bằng việc **checkout thành công trở lại**, backend không cạn tài nguyên và traffic không mong muốn được giới hạn trong phạm vi phù hợp; không đơn thuần là “chặn được nhiều IP”.

## 21. Những nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Lưu lượng tăng bất thường chắc chắn là DDoS.” | Có thể là chiến dịch, crawler hợp lệ, release hoặc retry storm; cần nhiều nguồn bằng chứng. |
| “Cứ thêm firewall deny là giảm được mọi flood.” | Nếu uplink nghẽn trước firewall, phải giảm tải ở upstream. |
| “DDoS chỉ có băng thông rất lớn.” | L7 có thể làm cạn DB/CPU với rps vừa phải. |
| “Có CDN thì origin hoàn toàn an toàn.” | Origin có thể bị truy cập trực tiếp hoặc backend cạn tài nguyên do request hợp lệ về cú pháp. |
| “Autoscale luôn là giải pháp tốt nhất.” | Có quota, chi phí, hiệu ứng với DB và nguy cơ cost exhaustion. |
| “Càng nhiều traffic bị chặn thì mitigation càng tốt.” | Phải đo ảnh hưởng lên **người dùng hợp lệ và giao dịch cốt lõi**. |
| “Chặn một IP chỉ ảnh hưởng một người dùng.” | CGNAT, proxy và CDN có thể chia sẻ IP cho nhiều người dùng. |
| “Chặn theo địa lý không gây ảnh hưởng nghiệp vụ.” | Người dùng/đối tác hợp lệ có thể ở nhiều region hoặc dùng VPN/proxy. |
| “RTBH giúp dịch vụ bị tấn công tiếp tục hoạt động bình thường.” | Blackhole thường làm mất cả traffic hợp lệ tới đích được chỉ định. |
| “Một IP/ASN xuất hiện nhiều là nguồn tấn công được xác nhận.” | Cần xem spoofing, NAT, bot traffic hợp lệ và dữ liệu provider; IP không chứng minh danh tính. |
| “Đã giảm bps thì incident kết thúc.” | Phải phục hồi SLI, DNS/TLS/API, giảm false positives và dọn rule khẩn. |
| “DDoS runbook chỉ cần lệnh CLI của firewall.” | Cần phối hợp ISP, app, cloud, security, truyền thông, quyết định và rollback. |
| “Fail-open IPS luôn là giải pháp bảo đảm uptime.” | Có thể gây bypass kiểm tra an ninh, phải đánh giá theo vùng và rủi ro. |
| “DDoS protection có thể thay xác thực API và phân đoạn mạng.” | DDoS protection xử lý tính sẵn sàng; auth, authorization và segmentation bảo vệ những thuộc tính khác. |

## 22. Mẫu runbook một trang để sử dụng khi diễn tập

~~~text
TÊN SỰ CỐ: DDoS / Availability Degradation
INCIDENT ID: ___________________________
UTC START: _____________________________
IC / SCRIBE: ___________________________
ON-CALL: Network ____ SOC ____ SRE ____ App ____
PROVIDER CONTACT/TICKET: _______________

SERVICE/REGION/CRITICAL USER JOURNEY:
  ______________________________________

1. VERIFY
  [ ] Impact verified from independent user/application signals
  [ ] DNS/TLS/deploy/routing/maintenance checked as alternatives
  [ ] Business SLI and baseline recorded

2. CLASSIFY
  [ ] Upstream bandwidth / pps
  [ ] Firewall/LB connection or state exhaustion
  [ ] HTTP/API/DB resource pressure
  [ ] DNS/VPN/cloud quota or other dependency
  [ ] Severity and confidence recorded

3. MITIGATE
  [ ] Approved owner and change/rollback record
  [ ] Control placed before the actual bottleneck
  [ ] Scope constrained; no unnecessary production bypass
  [ ] ISP/CDN/WAF/Firewall/App owner informed

4. VERIFY
  [ ] Legitimate user transactions restored
  [ ] False positive/blocked customers measured
  [ ] Network/edge/origin/DB resource pressure reduced
  [ ] Deny/authentication/security controls remain effective

5. RECOVER
  [ ] SLI stable for required observation window
  [ ] Temporary rules/routes reviewed or rolled back
  [ ] Monitoring owner assigned
  [ ] Incident timeline and provider tickets archived
  [ ] Postmortem and improvement tasks scheduled

NEXT UPDATE UTC: ________   OWNER: ________
~~~

**Lưu ý:** Đây là **checklist thao tác tư duy**, không thay thế quy trình ứng phó sự cố đã được phê duyệt tại tổ chức. Khi phát sinh xung đột, phải theo **ủy quyền, chính sách và hướng dẫn kỹ thuật của nhà cung cấp đang vận hành**.

## 23. Câu hỏi tự kiểm tra

1. **Vì sao một firewall đặt sau uplink bão hòa không thể giải quyết toàn bộ volumetric DDoS?** Vì gói tin đã làm đầy đường truyền trước khi đến firewall; cần upstream mitigation.
2. **L7 DDoS khác flood băng thông như thế nào?** Nó có thể tiêu hao tài nguyên ứng dụng hoặc DB mà không cần bps/pps lớn.
3. **Một đợt tăng RPS gấp năm lần nhưng latency và lỗi không đổi có đủ kết luận DDoS?** Không. Cần đối chiếu bối cảnh, threat signals và tác động thực.
4. **IC chịu trách nhiệm gì?** Điều phối mức độ, nhân sự, quyết định theo thẩm quyền, nhịp thông báo và tiêu chí đóng incident.
5. **Tại sao không chặn mọi request từ một IP sau NAT?** Một IP có thể đại diện nhiều người dùng hoặc đối tác hợp lệ.
6. **RTBH cần thận trọng điều gì?** Có thể làm mất toàn bộ lưu lượng hợp lệ tới đích; yêu cầu phê duyệt, phạm vi, thời hạn và rollback.
7. **Vì sao mitigation ở CDN không luôn bảo vệ origin?** Origin có thể bị bypass hoặc bị quá tải bởi traffic hợp lệ về mặt giao thức nhưng tốn tài nguyên.
8. **Làm sao phân biệt DNS outage với API outage?** Kiểm tra authoritative/recursive resolution từ nhiều nguồn, sau đó kiểm tra TLS/API/backend.
9. **Chỉ số nào xác nhận hiệu quả cuối cùng?** Tỷ lệ giao dịch hợp lệ thành công, latency, lỗi và false-positive impact, cộng sức khỏe hạ tầng.
10. **Tại sao không tắt ngay biện pháp khi traffic giảm?** Traffic có thể tăng trở lại; cần theo dõi ổn định và tháo rule có kiểm soát.
11. **DDoS runbook phải cập nhật sau thay đổi nào?** Kiến trúc WAN/CDN/ISP, service/dependency, route, IP, cloud account, TLS termination, quy trình cấp quyền hoặc kết quả postmortem.
12. **Vai trò của segmentation, IDS/IPS, firewall và VPN trong runbook?** Chúng giới hạn đường truy cập, cung cấp tín hiệu hoặc giảm thiểu theo phạm vi; không một lớp nào thay thế hoàn toàn khả năng hấp thụ DDoS upstream và phục hồi ứng dụng.

### Bài tập cuối chương

Một tổ chức có API Production, website qua CDN, IPsec VPN cho nhân viên và DNS authoritative do bên thứ ba quản lý. Trong cùng thời điểm, p95 API tăng, firewall session table gần đầy, DNS qps tăng và người dùng mobile phản ánh HTTP 429. Một chiến dịch quảng bá cũng đang chạy.

Hãy lập:

1. **Incident brief** gồm các giả thuyết cạnh tranh với DDoS, mức tin cậy và dữ liệu còn thiếu.
2. **Sơ đồ data flow** qua ISP/CDN/firewall/API/DB/DNS/VPN, đánh dấu từng bottleneck và failure domain.
3. **Bảng hành động** phân biệt upstream L3/L4, firewall state, L7 quota và DNS protection; nêu owner, risk, rollback.
4. **Ít nhất tám ca kiểm chứng** gồm người dùng hợp lệ qua mobile/NAT, partner API, DNS resolution, VPN authentication và giao dịch thanh toán.
5. **Kế hoạch truyền thông và recovery**, gồm điều kiện khi nào được tháo rate limit tạm, và bằng chứng để tuyên bố resolved.

**Kết luận:** Một DDoS runbook tốt kết nối **threat model, năng lực mạng, chỉ số ứng dụng, quyền quyết định, biện pháp upstream/L3/L4/L7, truyền thông và kiểm chứng** thành một quy trình có thể diễn tập. Mục tiêu cuối cùng không phải làm số gói tin giảm bằng mọi giá, mà là **duy trì/khôi phục giao dịch hợp lệ với ranh giới an ninh vẫn được bảo toàn**, đồng thời cải thiện hệ thống sau mỗi sự cố.
