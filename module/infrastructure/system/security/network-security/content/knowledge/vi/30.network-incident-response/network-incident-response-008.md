# Điều phối giữa network, platform và application team khi ứng phó sự cố mạng

## 1. Vì sao sự cố mạng hiếm khi thuộc riêng một nhóm?

Một khách hàng báo rằng ứng dụng thanh toán chậm, đôi lúc trả **HTTP 502**, trong khi dashboard của load balancer vẫn hiển thị tình trạng healthy. Network team kiểm tra thấy đường TCP đến Kubernetes ingress hoạt động. Platform team thấy Pods đang ở trạng thái Running. Application team lại phát hiện kết nối tới cơ sở dữ liệu bị timeout sau một đợt triển khai. Cả ba nhóm đều có thể báo **“phần của tôi vẫn ổn”**, nhưng người dùng vẫn không thanh toán được.

Sự cố mạng hiện đại thường trải qua nhiều ranh giới:

- **Network:** định tuyến, địa chỉ IP, DNS network path, firewall, NAT, VPN, load balancer, IDS/IPS, WAF và khả năng kết nối giữa các vùng.
- **Platform:** cloud VPC/VNet, Kubernetes, container networking, ingress/service mesh, node health, runtime, secrets/certificates và hệ thống cung cấp tài nguyên cho ứng dụng.
- **Application:** HTTP/API semantics, application authentication/authorization, dependencies, database pools, retries, timeouts, feature flags, business transactions và tính đúng đắn dữ liệu.

Để ứng phó nhanh và an toàn, cần **một quy trình điều phối chung** thay vì ba cuộc điều tra tách biệt. Mỗi nhóm chịu trách nhiệm xác minh những điều mình có thể chứng minh, cung cấp bằng chứng có thời điểm/điểm đo, thực hiện thay đổi trong phạm vi quyền được giao và nhận biết hậu quả của thay đổi đối với các nhóm còn lại.

Bài **Điều phối giữa network, platform và application team** thuộc chương **Ứng phó sự cố mạng** của học phần **SECURITY_NETWORK_SECURITY**. Kiến thức được kết nối với **firewall, VPN, IDS/IPS, phân đoạn, DNS, PKI/mTLS, telemetry, network threat modeling, Kubernetes/cloud network và packet analysis**. Mục tiêu là xây năng lực **cùng phát hiện, cùng khoanh vùng, cùng ra quyết định, phục hồi có kiểm chứng và cải tiến sau sự cố**.

### 1.1. Năng lực đạt được

Sau bài học, bạn có thể:

1. Phân biệt **trách nhiệm kỹ thuật** của network, platform và application team theo từng hop và thành phần.
2. Dựng cấu trúc chỉ huy gồm **Incident Commander (IC), technical leads, communications lead, scribe và security lead** khi cần.
3. Lập **RACI/DRI** cho triage, containment, thay đổi mạng, rollback ứng dụng, thu thập bằng chứng và kết thúc sự cố.
4. Thiết lập **một timeline chung** dùng UTC, correlation IDs, flow/trace IDs, deployment revisions, DNS answers và trạng thái cảnh báo.
5. Thực hiện **triage theo hướng từ client tới ứng dụng** và ngược lại, tránh đổ lỗi qua ranh giới đội.
6. Phân biệt **routing/TCP/TLS/DNS/WAF/ingress/service mesh/application/database** bằng chứng từ từng nhóm.
7. Đánh giá lựa chọn **isolate host, block IP/domain, rate limit, failover, rollback, rotate credential** theo blast radius và tác động nghiệp vụ.
8. Thực hành giao tiếp nội bộ/đối ngoại, tabletop drill, checklist phục hồi, post-incident review và cải tiến có chủ sở hữu.

### 1.2. Một nguyên tắc thống nhất

**Người dùng không quan tâm đường lỗi thuộc đội nào; họ quan tâm dịch vụ có an toàn và hoạt động đúng không.** Vì vậy trong thời gian xử lý sự cố, “owner của một tầng” không đồng nghĩa “chủ sở hữu duy nhất của sự cố”. Các nhóm cần chung **mục tiêu phục hồi, tiêu chí an toàn, bằng chứng, trách nhiệm và cách ra quyết định**.

Không được nhầm **phối hợp khẩn cấp** với cho phép mọi người tự do sửa production. Trong khẩn cấp, thay đổi vẫn cần **người có quyền thực hiện, phê duyệt theo runbook, ghi dấu vết và cách rollback**.

## 2. Bản đồ ranh giới trách nhiệm theo luồng request

### 2.1. Vẽ đường dữ liệu trước khi quy trách nhiệm

~~~mermaid
flowchart LR
    U["User/partner"] --> DNS["DNS / edge resolution"]
    DNS --> EDGE["CDN / WAF / external LB"]
    EDGE --> FW["Network firewall / VPC routing"]
    FW --> ING["Kubernetes ingress / gateway"]
    ING --> SVC["Service / mesh / workload"]
    SVC --> APP["Application API"]
    APP --> DB["Database / queue / external API"]
    NET["Network team"] -. "Routing, transport, edge, policy" .-> FW
    NET -. "DNS/edge coordination" .-> EDGE
    PLAT["Platform team"] -. "Cluster/ingress/runtime" .-> ING
    PLAT -. "Service endpoints/mesh" .-> SVC
    APPTEAM["Application team"] -. "HTTP/business/dependencies" .-> APP
    APPTEAM -. "Data semantics" .-> DB
~~~

Sơ đồ là mô hình **logic**, không áp đặt ranh giới sở hữu cho mọi tổ chức. Ví dụ một doanh nghiệp có thể để platform quản lý cloud load balancer, network quản lý private DNS và application team quản lý database schema. **Ownership thực tế phải được ghi ở service catalog/runbook**, không đoán từ tên sản phẩm.

### 2.2. Các hop và nguồn bằng chứng

| Hop | Câu hỏi xác minh | Nguồn bằng chứng thường cần | Nhóm chủ trì theo mô hình điển hình |
| --- | --- | --- | --- |
| **Client / VPN / ZTNA** | User có đường đi và danh tính được cấp phép? | VPN/ZTNA logs, client path, auth signals | Network + Identity/Security |
| **DNS** | Client nhận bản ghi nào, từ resolver nào, tại thời điểm nào? | Resolver query logs, answer TTL, DNS policy | Network/Platform theo sở hữu |
| **Internet edge / WAF** | Request bị rate-limit, challenge hay deny ở edge? | WAF actions, LB status, edge request ID | Network + Security |
| **Routing / NAT / firewall** | Packet được forward hay drop, route qua đâu? | Flow verdicts, effective routes, NAT state | Network |
| **L4/L7 load balancer** | Target nào được chọn, upstream có healthy? | LB health, target status, 4xx/5xx origin attribution | Network/Platform |
| **Kubernetes ingress** | Route/host/path/cert/endpoint có đúng? | Controller logs, Ingress/Gateway config, endpoints | Platform |
| **CNI / service mesh** | Pod-to-Pod route, mTLS, policy có cho kết nối? | CNI flows, mesh control/data plane logs, cert status | Platform + Network |
| **Application API** | Request được parse, auth, xử lý và trả gì? | Structured app logs, traces, error codes | Application |
| **Data stores / queues** | Latency, quota, pool và transaction state có đúng? | DB/queue metrics, app instrumentation | Application + DBA/Platform |
| **External provider** | Có lỗi từ nhà cung cấp hay egress path? | Provider status, proxy logs, retries, contract | Application + Network |

**HTTP 502 trả về ở edge** không mặc định chứng minh network fault: 502 là response do một gateway/proxy phát hiện vấn đề khi giao tiếp upstream; upstream có thể không ready, timeout, TLS mTLS sai hoặc trả response không hợp lệ. Phải xác định **đúng hop tạo status**.

### 2.3. Control plane khác data plane

Trong sự cố cloud/Kubernetes, cần phân biệt:

- **Control plane:** trạng thái API/config/route/Ingress/NetworkPolicy khai báo, health controller, certificate issuance, deployment revision.
- **Data plane:** gói thực tế tới đâu, bị chặn/chuyển tiếp như thế nào, proxy chọn target nào và ứng dụng có xử lý request không.

Ví dụ một NetworkPolicy tồn tại trong Kubernetes API **không tự chứng minh CNI đã áp policy**. Một ingress object đúng **không tự chứng minh controller đã cập nhật listener**. Một load balancer target healthy **không bảo đảm API nghiệp vụ hợp lệ**. Phải ghép desired state với observed behavior.

### 2.4. Shared responsibility không có nghĩa “không ai chịu trách nhiệm”

Một incident có thể ảnh hưởng nhiều tầng nhưng phải có:

- **Một Incident Commander** chịu trách nhiệm điều phối quyết định và nhịp xử lý.
- **Một DRI (Directly Responsible Individual)** cho mỗi hành động/nhánh điều tra.
- **Một owner kỹ thuật** cho cấu hình được thay.
- **Một người ghi timeline** hoặc công cụ ghi nhận tương đương.
- **Một đầu mối truyền thông**, nhất quán nội dung cho người dùng/stakeholders.

Nếu đội nhỏ, một người có thể kiêm vai, nhưng cần ghi rõ và tách **quyền phê duyệt thay đổi rủi ro cao** khi có thể.

## 3. Cấu trúc điều phối sự cố và vai trò

### 3.1. Incident Commander (IC)

IC tập trung vào **mục tiêu, ưu tiên, thời gian và quyết định**, không nhất thiết là chuyên gia sâu nhất về DNS/TLS/Kubernetes. Nhiệm vụ:

1. Xác nhận có sự cố, mở mã/tên incident và severity ban đầu.
2. Chỉ định người chịu trách nhiệm từng nhánh.
3. Thiết lập **nhịp cập nhật (cadence)** và một kênh tập trung.
4. Yêu cầu các nhóm nêu **facts, hypotheses, confidence, next test**.
5. Kiểm soát **thay đổi đồng thời** dễ làm nhiễu kết quả.
6. Chọn hướng containment/restore theo rủi ro với các owner có quyền.
7. Quyết định điều kiện chuyển sang monitoring/closure theo chính sách.
8. Bảo đảm có post-incident review và action owners.

**IC không nên ép một đội triển khai thay đổi vượt quyền hoặc trái chính sách chỉ để tăng tốc.** Nếu cần quyền bổ sung, gọi đúng change approver/on-call/incident response authority.

### 3.2. Network lead

Chịu trách nhiệm dẫn dắt **path analysis**:

- DNS reachability/resolution khi thuộc phạm vi network.
- IPv4/IPv6 routes, NAT, peering, VPN, zero-trust access.
- Firewall/ACL/SG/NSG, WAF/LB policies, DDoS mitigation.
- Packet capture/NetFlow/flow verdict và network timeouts.
- Tác động của thay route, chặn source/dest, rate limit hoặc isolate segment.

Network lead phải trả lời **“đường kết nối thực từ nguồn nào qua hop nào, rule nào tác động, bằng chứng ở đâu?”**, không chỉ báo “ping OK”.

### 3.3. Platform lead

Phụ trách **runtime/cluster/cloud middleware**:

- Node/Pod readiness, restarts, rollout status, resource pressure.
- Ingress/Gateway API, Service/EndpointSlice, DNS trong cluster.
- CNI policies, overlay, service mesh mTLS và gateway.
- Cloud controllers, certificates/secrets và policy propagation.
- Autoscaling, stateful service placement, capacity/availability.

Platform lead trả lời **“manifest và runtime có khớp không, service có endpoints khỏe không, policy đã chạy vào data plane chưa?”**.

### 3.4. Application lead

Phụ trách **hành vi ứng dụng và giao dịch nghiệp vụ**:

- Error codes, correlation IDs, release/feature flags.
- Authentication/authorization, session và API contracts.
- Dependency timeouts, connection pool, retries/circuit breaker.
- Database/queue failures và nhất quán dữ liệu.
- Business impact, khả năng read-only/degraded mode và rollback ứng dụng.

Application lead trả lời **“request có tới app và xử lý tới bước nào, dữ liệu nào bị ảnh hưởng, người dùng có thể giao dịch an toàn không?”**.

### 3.5. Security/IR lead, scribe và communications lead

Với incident có nghi vấn xâm nhập hoặc thất thoát dữ liệu:

- **Security/IR lead:** đánh giá threat, evidence preservation, containment, phạm vi compromise, credential response, liên hệ pháp lý/đơn vị chịu trách nhiệm thông báo nếu cần.
- **Scribe:** ghi **UTC timeline, evidence links, owner, quyết định, hành động và trạng thái**; tách observation khỏi hypothesis.
- **Communications lead:** phát **internal/external updates** theo mức độ xác minh và quy định; không tiết lộ chi tiết tấn công/bí mật hay khẳng định nguyên nhân chưa được kiểm chứng.

Không phải mọi incident availability đều cần một full security war room. Ngược lại, có dấu hiệu attack thì **đừng chỉ khởi động lại Pods** rồi bỏ qua việc bảo toàn bằng chứng.

### 3.6. Vai trò có thể thay đổi khi biết thêm dữ liệu

Ví dụ ban đầu network lead chủ trì vì nhìn thấy packet loss. Sau khi xác định packet drops là **CNI policy do platform rollout**, platform có thể trở thành technical owner cho fix, trong khi network vẫn giữ vai trò xác minh egress/return path. **IC duy trì đầu mối xuyên suốt**, cập nhật ownership rõ trong timeline; không chuyển sự cố qua nhiều nhóm bằng cách đóng ticket và mở ticket mới không liên kết.

## 4. Phân loại tác động, ưu tiên và khởi động incident

### 4.1. Severity dựa vào hậu quả, không dựa vào đội bị nghi

Một hệ thống có thể dùng **SEV1/SEV2/SEV3** hoặc mức khác theo quy định nội bộ. Tiêu chí có thể gồm:

- Mức độ ảnh hưởng **khách hàng/giao dịch cốt lõi**.
- **Tính khả dụng** trên nhiều region/service.
- **Tính toàn vẹn dữ liệu** hoặc nguy cơ xử lý giao dịch trùng.
- **Tính bí mật** và khả năng lộ credentials/data.
- Blast radius, thời gian tồn tại và tính cấp bách của khôi phục.
- Rủi ro an toàn người dùng, pháp lý hoặc yêu cầu hợp đồng.

Không sử dụng ví dụ dưới đây như policy severity chính thức:

| Mức minh họa | Điều kiện gợi ý | Điều phối tối thiểu |
| --- | --- | --- |
| **SEV1 — rất nghiêm trọng** | Dịch vụ cốt lõi ngừng diện rộng, nghi dữ liệu nhạy cảm bị rò, sự cố đang lan | IC + leads + security/comms thích hợp, cập nhật thường xuyên |
| **SEV2 — nghiêm trọng** | Một chức năng/region quan trọng suy giảm đáng kể hoặc risk tăng | IC/DRI, các team liên quan, ưu tiên phục hồi |
| **SEV3 — hạn chế** | Ảnh hưởng hẹp, workaround an toàn, không nghi breach | Owner trực tiếp, escalation nếu vượt ngưỡng |

**Nhịp cập nhật và thời hạn phản hồi phải theo runbook/SLO đã phê duyệt của tổ chức**, không có một số phút mặc định áp cho mọi mô hình.

### 4.2. Khởi tạo incident record

Ngay khi đủ căn cứ:

~~~text
Incident ID:       INC-LAB-2026-008
Opened at UTC:     2026-11-28T09:00:00Z
Severity:          SEV2 (minh họa, có thể điều chỉnh)
Affected service:  checkout-api (staging lab)
Customer impact:   35% synthetic checkout requests return 502
First detected by: synthetic probe + ingress 5xx
IC:                designated on-call incident coordinator
Network lead:      on-call-network
Platform lead:     on-call-platform
Application lead:  on-call-checkout
Security lead:     invited only if threat hypothesis arises
Single timeline:   incident record / shared channel
Next checkpoint:   agreed by IC, noted in UTC
Current hypothesis: UNCONFIRMED
~~~

Đây là **record minh họa**, không phải sự cố thực. Tỷ lệ lỗi của synthetic probe không đồng nghĩa 35% toàn bộ traffic khách hàng; phải ghi rõ **mẫu số và nguồn đo**.

### 4.3. Điều phối theo hai dòng công việc

Trong incident nghiêm trọng, IC thường tách:

- **Mitigation/restoration stream:** tìm cách giảm impact ngay nhưng an toàn, ví dụ chuyển traffic khỏi backend không khỏe, feature flag hoặc rollback có kiểm soát.
- **Investigation/evidence stream:** xác định nguyên nhân, phạm vi ảnh hưởng và giữ dữ liệu để không lặp lại hoặc bỏ sót dấu hiệu tấn công.

Hai dòng việc phải trao đổi liên tục. **Mitigation làm thay đổi hệ thống**, có thể xóa dấu vết như conntrack, ephemeral Pod logs hoặc nội dung memory. Nếu có nghi xâm nhập, security lead cần tham gia quyết định bảo toàn bằng chứng phù hợp; điều này không có nghĩa trì hoãn mọi biện pháp bảo vệ khách hàng trong tình huống khẩn cấp.

### 4.4. Điều chỉnh severity và scope theo bằng chứng

Không cố giữ mức SEV ban đầu khi impact thay đổi. Khi phát hiện dấu hiệu **data exposure, lateral movement, credential compromise hoặc ảnh hưởng nhiều vùng**, cần đánh giá lại severity/escalation. Khi hoạt động ổn định, severity có thể được giảm theo policy, nhưng **closure cần tiêu chí nghiệm thu riêng**; dashboard xanh vài phút chưa chứng minh mọi transactions và queues đã phục hồi.

## 5. Ma trận trách nhiệm RACI cho ba đội

### 5.1. RACI là gì và khi nào có ích?

RACI phân vai cho **một công việc/quyết định cụ thể**:

- **R — Responsible:** người/nhóm thực hiện hành động.
- **A — Accountable:** người chịu trách nhiệm cuối cho kết quả/quyết định theo quy trình.
- **C — Consulted:** người cần tham vấn hai chiều trước quyết định.
- **I — Informed:** người cần được cập nhật kết quả.

Nguyên tắc thực hành: **mỗi dòng quyết định nên có một A rõ ràng**; có thể có nhiều R nếu cùng thực hiện, nhưng phải chỉ định **DRI riêng cho đầu việc**. Một bảng toàn chữ R/A cho mọi nhóm làm mờ ownership.

### 5.2. RACI tham khảo cho incident mạng có yếu tố ứng dụng

| Hoạt động | IC | Network | Platform | Application | Security/IR |
| --- | :---: | :---: | :---: | :---: | :---: |
| Khai báo incident, severity và nhịp cập nhật | **A/R** | C | C | C | C nếu cần |
| Xác minh routing/ACL/NAT/firewall/LB paths | I | **A/R** | C | I | C nếu nghi tấn công |
| Xác minh Kubernetes ingress/CNI/node/service endpoints | I | C | **A/R** | C | C |
| Xác minh app traces, API errors, DB dependencies | I | I | C | **A/R** | C |
| Đánh giá incident có phải xâm nhập/data exposure | I | C | C | C | **A/R** |
| Phê duyệt thay đổi phục hồi liên đội | **A** | R theo phần sở hữu | R theo phần sở hữu | R theo phần sở hữu | C nếu ảnh hưởng security |
| Thực thi thay rule firewall cụ thể | I | **A/R** | C | C | C |
| Rollback Deployment/Ingress config | I | C | **A/R** | C | C nếu có nguy cơ |
| Rollback logic/feature flag ứng dụng | I | I | C | **A/R** | C |
| Đánh giá giữ bằng chứng khi nghi compromise | I | C | C | C | **A/R** |
| Kiểm thử end-to-end nghiệp vụ sau phục hồi | I | C | C | **A/R** | C |
| Quyết định kết thúc điều phối incident | **A/R** | C | C | C | C nếu security incident |

**Đây là RACI minh họa, không tự ghi đè authority thật.** Một tổ chức có thể yêu cầu change manager, legal/privacy officer, business owner hoặc CISO phê duyệt hành động đặc biệt. IC điều phối không đồng nghĩa có quyền vô hiệu hóa firewall hoặc xóa forensic evidence. Khi thay đổi liên quan bảo mật cao, phải áp **approval path** được quy định.

### 5.3. Cách tránh RACI trở thành bảng treo tường

Trong cuộc gọi incident, không cần đọc lại toàn bảng. IC nói rõ:

> Network DRI xác minh flow drop tại edge, Platform DRI xác minh ingress endpoints và Application DRI xác minh lỗi DB pool. Mỗi người gửi bằng chứng, time range và next step trước checkpoint tiếp theo; **chưa ai thay đổi production ngoài hành động đã được duyệt**.

Sau mỗi kết luận, chỉ định **action owner + deadline/checkpoint + verification owner + rollback condition**. Nếu một việc không có người thực hiện, RACI trên wiki không giải quyết được gì.

### 5.4. Ownership theo tài sản thay vì công nghệ

Cùng một công nghệ có thể được quản trị ở nhiều nơi:

- Cloud security group do platform IaC kiểm soát, network phải tham vấn.
- Private DNS zones do application service owner đề xuất nhưng network/DNS team triển khai.
- Service mesh mTLS CA do platform quản lý, còn workload certificate identity do security policy quy định.
- Edge CDN/WAF rules do security team sở hữu, network vận hành route.
- Database cluster do DBA sở hữu, application team chịu trách nhiệm query behavior.

Cần ghi **thực thể và owner cụ thể**, ví dụ **edge-lb-prod-eu**, **cluster-a/namespace-payment** và **checkout-api**, không chỉ viết “K8s = platform”, “TCP = network”.

## 6. Chu trình ứng phó liên đội: Từ detect tới post-incident review

### 6.1. Các pha cần kết nối

~~~mermaid
flowchart TD
    DET["Detect: Alert / user report"] --> TRI["Triage: Impact + evidence + incident severity"]
    TRI --> COM["Command: IC, leads, owners, communication"]
    COM --> CON{"Có nguy cơ an ninh ngay?"}
    CON -->|Có| SEC["Security-led containment + evidence protection"]
    CON -->|Chưa rõ / Không| REST["Mitigation + safe rollback/failover"]
    SEC --> REST
    REST --> VER["Verify: technical + business + security"]
    VER --> STABLE{"Ổn định trong observation window?"}
    STABLE -->|Không| TRI
    STABLE -->|Có| CLOSE["Closure + stakeholder update"]
    CLOSE --> PIR["Post-incident review + prevention actions"]
~~~

Đây là luồng tổng quát. **Containment và restoration có thể diễn ra song song**, không nhất thiết hoàn toàn tuần tự. Khi có nguy cơ data loss đang tiếp diễn, containment thường cần quyết định khẩn cấp; khi chỉ có availability fault, rollback có thể là lựa chọn ưu tiên. Các bước nên phù hợp với quy trình IR của tổ chức và không được phép xóa evidence không cần thiết.

### 6.2. Pha Detect: Tạo tín hiệu đáng tin

Nguồn kích hoạt:

- Synthetic monitoring hoặc external user report.
- SLO burn-rate alerts, p95/p99 latency, error-budget exhaustion.
- WAF/IDS/IPS/NDR alerts về traffic bất thường.
- Cloud firewall denies, route changes, VPC flow anomalies.
- Kubernetes readiness/error budget và crash loops.
- Application 4xx/5xx, DB pool saturation, queue backlog.
- DNS errors hoặc TLS certificate verification failures.
- Thông báo từ đối tác/provider về outage, maintenance hoặc threat.

**Một alert không tự là nguyên nhân gốc.** Các nguồn cần được đưa vào cùng timeline và có phân biệt **observed symptom** với **possible cause**.

### 6.3. Pha Triage: Đo đúng ảnh hưởng

Ghi:

1. Dịch vụ/chức năng nào bị ảnh hưởng, **đối tượng nào**, trong thời gian nào?
2. Ảnh hưởng ở vùng, tenant, user role hay network path nào?
3. Mẫu số đo là **tổng request, synthetic probe hay users thực**?
4. Có chứng cứ **data integrity, confidentiality hoặc safety** bị ảnh hưởng?
5. Khi nào bắt đầu so với recent deployments, firewall/WAF policy, certificate, DNS hoặc cloud changes?
6. Có workaround hợp lệ mà không làm tăng quyền truy cập?
7. Có **traffic hay logs mất** gây sai lệch tỷ lệ lỗi?

Nếu một proxy trả 502, cần xác nhận **502 ở edge, ingress hay app**. Nếu một client báo timeout, cần phân biệt **DNS failure, TCP connect timeout, TLS handshake timeout và application response timeout**.

### 6.4. Pha Contain/Mitigate: Một thay đổi có kiểm soát tại một thời điểm

Các nhóm nên thống nhất **thứ tự thay đổi** để dễ xác minh hiệu quả:

~~~text
Change proposal:
  incident_id:
  owner + authority:
  suspected failure:
  exact resources/scope:
  proposed action:
  expected positive effect:
  security / business side effects:
  how to verify:
  rollback:
  start/end UTC:
~~~

Ví dụ nếu nghi WAF rule chặn nhầm callback thanh toán, thay đổi an toàn hơn có thể là **narrow exception theo route/signed identity/method** so với vô hiệu hóa toàn bộ WAF. Nếu database cluster bị lỗi, rollback ứng dụng có thể không giúp; cần xác minh đúng điểm nghẽn.

### 6.5. Pha Restore: Khôi phục chức năng, không chỉ đèn xanh

Phục hồi phải kiểm tra:

- Network reachability đúng nguồn/đích/port.
- DNS/TLS/mTLS/identity policy vẫn đúng.
- Ingress routes, healthy endpoints và connection drains.
- Application error rate, latency, queue length, DB health.
- **Business transactions** có được xử lý đúng, không lặp/thiếu?
- Người dùng ở các vùng/tenant bị ảnh hưởng có truy cập lại được?
- Đường mạng không cần thiết vẫn bị chặn; không có bypass vừa mở để chữa lỗi.

**Một Pod Running/Ready không chứng minh checkout hoàn thành hoặc dữ liệu đã nhất quán.** Application team phải cung cấp business-level checks.

### 6.6. Pha Observe và Close

IC chỉ đề xuất kết thúc khi:

1. Điều kiện phục hồi được các owner xác nhận bằng **metrics và synthetic/business tests**.
2. Những counter/hệ thống có thể bị trễ đã hồi phục trong **observation window** phù hợp.
3. Các biện pháp tạm thời có **owner, expiry hoặc change ticket**.
4. Không còn nghi vấn threat chưa được giao IR xử lý.
5. Có stakeholder update cuối và action items đã được ghi.

**Closure điều phối** không đồng nghĩa mọi phân tích nguyên nhân gốc đã xong. Một investigation theo sau có thể tiếp tục nhưng phải có owner, thời hạn và bằng chứng bảo tồn.

## 7. Một nguồn thông tin chung: Incident room, timeline và evidence board

### 7.1. Tránh “ba dashboard, ba sự thật”

Network dashboard có thể thấy **packet forwarded**, platform dashboard thấy **Pod Running**, còn application dashboard ghi **HTTP 503**. Những observations không mâu thuẫn: packet có thể tới Pod nhưng app không đáp ứng contract, hoặc metric của platform thiếu health check nghiệp vụ.

Thiết lập **single source of truth** dưới dạng incident record/kênh điều phối có:

- Impact summary và severity hiện tại.
- IC, leads, on-call schedule, escalation contact.
- UTC timeline of observations and actions.
- Hypotheses với evidence và confidence.
- Các thay đổi đang diễn ra và owner.
- Những câu hỏi mở/nhánh điều tra.
- Next checkpoint và external communication status.

Đây là **nguồn phối hợp**, không thay các log stores có phân quyền và dữ liệu nhạy cảm.

### 7.2. Phân loại Fact / Hypothesis / Action / Decision

| Loại ghi chú | Ví dụ đúng | Cách viết không nên |
| --- | --- | --- |
| **FACT** | “09:02 UTC, ingress log báo 502 ở request ID r-1042, upstream timeout 30 s.” | “Network đang lỗi.” |
| **HYPOTHESIS** | “Nghi kết nối từ ingress→backend bị CNI deny sau policy rollout.” | “Platform chắc chắn gây lỗi.” |
| **ACTION** | “Platform DRI kiểm tra CNI flow verdict cho Pod UID P tại 09:02.” | “Kiểm tra lại hệ thống.” |
| **DECISION** | “IC phê duyệt rollback policy revision 8 sang revision 7 trong namespace X, rollback nếu baseline vẫn lỗi.” | “Đã quyết định rollback tất cả.” |
| **UNKNOWN** | “Không có capture upstream ở AZ-B; chưa xác minh tuyến này.” | “Các AZ khác chắc giống nhau.” |

Mỗi note nên có **author, event time/ingest time nếu có, evidence link và confidence**; đặc biệt khi chuyển ca.

### 7.3. Timeline chuẩn hóa UTC

~~~text
09:00:04Z  FACT      Synthetic checkout p95 vượt SLO
09:00:31Z  FACT      Edge 502 count tăng tại region east
09:01:12Z  FACT      Ingress rollout revision 42 hoàn tất (Kubernetes API)
09:02:07Z  HYPOTHESIS  CNI policy propagation ảnh hưởng backend
09:02:30Z  ACTION    Network DRI kiểm tra flow verdict; Platform DRI kiểm tra Pod UIDs
09:03:18Z  FACT      CNI log: ingress Pod -> backend Pod TCP/8443 DROPPED
09:04:00Z  DECISION  Rollback narrow NetworkPolicy theo authorized runbook
09:05:20Z  FACT      Egress path test PASS; synthetic checkout 200 OK
09:06:00Z  UNKNOWN   User transactions vừa timeout có bị retry trùng không?
09:06:30Z  ACTION    Application DRI kiểm tra idempotency key và queue state
~~~

Tất cả thông tin **giả lập**. Lưu cả **thời điểm sự kiện** lẫn **thời điểm được biết** khi có độ trễ logs; đừng ngầm sắp xếp sự kiện dựa hoàn toàn vào timestamp của một thiết bị chưa đồng bộ đồng hồ.

### 7.4. Evidence board và tính chất nguồn

| Evidence | Hỗ trợ kết luận gì? | Không chứng minh |
| --- | --- | --- |
| **Flow verdict DROPPED** | Packet/flow bị chặn tại enforcement point | Mọi đường khác đều bị chặn |
| **TCP handshake complete** | Kết nối TCP thiết lập ở nơi đo | TLS/app authorization thành công |
| **TLS ServerHello** | Server đáp lại/đề xuất lựa chọn TLS | Certificate được client tin hoặc HTTP thành công |
| **HTTP 502 tại ingress** | Ingress có upstream problem theo logs | Root cause là network |
| **Pod Ready** | Readiness probe đạt theo thiết kế | Mọi business operation khỏe |
| **App trace 5xx** | Request qua một số spans trả lỗi | Traffic chưa được instrument không có lỗi |
| **DNS NOERROR** | Resolver trả response phù hợp tên/QTYPE theo context | Client đã dùng answer đó |
| **DB pool exhausted** | Ứng dụng không lấy được connection từ pool | Database server chắc chắn down |
| **WAF challenge/deny event** | Edge đã xử lý policy với request đó | Client khác/region khác bị cùng rule |
| **Cloud audit change** | Ai sửa một cấu hình và khi nào | Data plane áp change ngay lập tức |

**Bằng chứng cần có sensor/hop và phạm vi quan sát**, nhất là khi nhiều proxy/NAT/caches làm một request đi qua nhiều lớp.

### 7.5. Correlation IDs và dữ liệu không nên đưa vào war room

Các hệ thống nên chuyển tiếp **trace ID, request ID, connection ID, policy ID và workload identity** theo cách đáng tin, với retention phù hợp. Không dùng **session token, password, API secret, private key hoặc raw personal data** làm correlation ID.

Với các proxy:

- **Client-generated request ID** có thể bị spoof hoặc lặp; gateway cần validate/generate trusted identifier khi dùng làm audit key.
- **Traceparent** của distributed tracing hữu ích, nhưng không tự bảo đảm identity.
- **NAT source IP** không luôn là user/workload gốc.
- **TLS session** có thể phục vụ nhiều HTTP/2 requests.
- **Kubernetes Pod IP** có thể tái sử dụng; dùng Pod UID và timestamp.

Những điểm không chắc phải ghi rõ trước khi đưa ra quyết định containment.

## 8. Protocol chung để triage theo tầng

### 8.1. Bắt đầu từ triệu chứng người dùng

Một cách đi từ ngoài vào trong:

~~~mermaid
flowchart TD
    A["Khách hàng báo lỗi API/network"] --> B{"DNS resolution đúng?"}
    B -->|Không| C["DNS resolver, split horizon, cache, zone policy"]
    B -->|Có| D{"TCP/QUIC/transport tới đúng điểm?"}
    D -->|Không| E["Routes, firewall, NAT, VPN, LB listener, packet loss"]
    D -->|Có| F{"TLS/mTLS handshake thành công?"}
    F -->|Không| G["Cert trust, SNI, ALPN, client cert, mesh/ingress"]
    F -->|Có| H{"HTTP request tới đúng route/upstream?"}
    H -->|Không| I["WAF, ingress, URL/Host, Service endpoints"]
    H -->|Có| J{"Ứng dụng xử lý request?"}
    J -->|Không| K["App errors, dependency timeouts, DB/queue"]
    J -->|Có| L{"Giao dịch nghiệp vụ đúng?"}
    L -->|Không| M["Data integrity, authz, idempotency, business logic"]
    L -->|Có| N["Ghi nhận recovered path + coverage"]
    C --> O["Tổng hợp evidence + owners + next test"]
    E --> O
    G --> O
    I --> O
    K --> O
    M --> O
    N --> O
~~~

Không có bước nào cho phép kết luận chỉ từ **một ping**. IC cần định hướng từng nhóm đưa **quan sát, giả thuyết, phép kiểm chứng và kết quả** vào một timeline.

### 8.2. Phân biệt các lỗi thường trông giống nhau

| Quan sát | Hướng điều tra đầu tiên | Không vội kết luận |
| --- | --- | --- |
| **NXDOMAIN** | DNS zone/hostname, search suffix, split DNS | Firewall chặn TCP |
| **SERVFAIL** | Recursive resolver, upstream/DNSSEC, policy | Domain chắc chắn không tồn tại |
| **TCP SYN timeout** | Route/ACL/SG/VPN/LB listener | TLS certificate hết hạn |
| **TCP RST** | Host/app close, firewall/proxy reset, state | Ai đã reset nếu chỉ có một capture |
| **TLS unknown_ca** | Client truststore, chain, đúng TLS hop | Máy chủ bị xâm nhập |
| **TLS handshake_failure** | Versions/ciphers/groups, client cert, policies | Một nguyên nhân duy nhất |
| **HTTP 401** | Authentication/token/identity | Đường mạng down |
| **HTTP 403** | Application/WAF/authorization policy | User chỉ cần thêm VPN route |
| **HTTP 429** | Quota/rate limit ở app/gateway/WAF | Chắc là DDoS |
| **HTTP 502** | Proxy/ingress upstream connection/protocol | Tất cả Pods chết |
| **HTTP 503** | Unavailable origin/target/capacity | Chắc do DNS |
| **HTTP 504** | Proxy upstream timeout hoặc xử lý chậm | Chắc do firewall |
| **Pod CrashLoopBackOff** | Process/image/config/dependency | Chắc do network |
| **Readiness PASS + synthetic fail** | Business route not covered by probe | Ứng dụng khỏe |

### 8.3. Hai phép kiểm chứng độc lập tốt hơn một giả định

Nếu nghi firewall drop giữa ingress và backend:

1. **Platform:** xác định ingress Pod UID, backend endpoint IP/port, Service/EndpointSlice và CNI policy revision đúng thời điểm.
2. **Network:** kiểm tra flow verdict và tuyến/SG/NSG tại source/dest; ghi observation point.
3. **Application:** xác minh backend có nhận request ID không; nếu không nhận, tập trung mạng/proxy; nếu có nhận và trả lỗi, điều tra app/dependencies.

Một phép **synthetic request nhỏ được phê duyệt** có thể giúp tạo correlation ID; không flood hệ thống đang quá tải. Khi nghi breach, hành động probing cần phối hợp IR để không phá bằng chứng.

### 8.4. Mỗi bên ghi phạm vi lời khẳng định

Thay vì:

> “Network OK, không liên quan chúng tôi.”

Hãy ghi:

> “Tại 10:15 UTC, 20/20 TCP connection attempts từ subnet client-test tới edge-LB TCP/443 hoàn tất trong 80 ms; **chưa xác minh edge→backend hoặc HTTP business flow**.”

Đây là cách nói **có bằng chứng, có mẫu số và có giới hạn**. Một bộ 20 synthetic tests chỉ minh họa kỹ thuật, không tự đại diện cho mọi users/regions và không nên chạy khi gây tăng tải không phù hợp.

## 9. Network team: Thu thập bằng chứng kết nối và chính sách

### 9.1. Bộ câu hỏi network phải trả lời

1. **Source identity:** client subnet, VPN address, Pod/node/egress gateway hay NAT IP nào là nguồn thực?
2. **Destination:** IP/port nào được truy cập ở thời điểm incident? DNS có trỏ đúng region/LB không?
3. **Route:** lưu lượng đi qua default gateway, transit, peering, tunnel hay firewall nào?
4. **Enforcement:** SG/NSG/ACL/firewall/WAF/IDS/IPS rule nào permit/deny?
5. **State:** TCP handshake hoàn tất? Có RST, retransmission, zero window, timeout hoặc packet loss?
6. **Return path:** route hai chiều có đối xứng, stateful firewall/conntrack xử lý đúng?
7. **Scope:** lỗi theo một site/region/subnet/IPv4/IPv6 hay một phần workload?
8. **Recent changes:** ACL, route, NAT, VPN, certificate ở edge, WAF rules hoặc load balancer targets?

**Network lead không chỉ thông báo “cổng 443 mở”.** Cần chứng minh **đúng nguồn→đúng đích→đúng hop→đúng thời điểm** và chỉ ra những đoạn chưa đo.

### 9.2. Evidence matrix tại network

| Nguồn | Dữ kiện hữu ích | Điểm mù |
| --- | --- | --- |
| **Firewall flow verdict** | ACL/policy ID, src/dst, allow/drop, timestamp | Một hop cho phép chưa chứng minh các hop khác |
| **Effective routes** | Next hop, subnet route, peering/VPN | Control plane có thể khác thực thi nhất thời |
| **NAT state/translation** | Original→translated tuple, egress gateway | NAT IP dùng chung che source gốc |
| **VPC/VNet flow logs** | Tuples, bytes, time window | Có thể sampling/aggregate, không có L7 request |
| **LB/WAF edge logs** | Rule action, target, status origin, rate limiting | Không phản ánh đầy đủ backend business errors |
| **Packet capture** | SYN/ACK, TLS ClientHello, fragmentation, loss | Capture có thể thiếu một chiều hoặc chứa PII |
| **DNS resolver** | QNAME/QTYPE/response/TTL/source | Client cache, DoH ngoài sensor, direct IP |
| **VPN/ZTNA logs** | Session/identity, tunnel routes, posture policy | Tunnel active chưa chắc app reachable |

### 9.3. Các lệnh chỉ đọc trên Linux lab

Trong **VM/máy lab có quyền**, những lệnh sau giúp kiểm tra trạng thái mạng mà không sửa cấu hình:

~~~bash
# Địa chỉ và interfaces.
ip -br address

# Bảng route IPv4/IPv6.
ip -4 route show
ip -6 route show

# Trạng thái socket TCP.
ss -tn

# Ví dụ một đường tới IP tài liệu; đổi thành IP lab thật khi kiểm chứng.
ip route get 192.0.2.20
~~~

**ip route get** chỉ trả quyết định định tuyến hiện tại theo context tham số; nó **không gửi packet** và không chứng minh firewall cho traffic qua. Linux namespaces, policy routing, VPN và container network có thể làm route trong host khác route trong Pod.

Không chạy các lệnh thay firewall/routing như **iptables -F**, **nft flush ruleset** hoặc xóa default route trong incident khi chưa có phê duyệt: chúng có thể mở quyền mạng hoặc cắt dịch vụ ngoài phạm vi.

### 9.4. Packet capture phải có phạm vi

Khi cần PCAP, ưu tiên:

- Chỉ capture **source/destination/port** được ủy quyền trong khoảng thời gian ngắn.
- Giới hạn bytes/packet count theo nhu cầu.
- Đánh dấu **capture point** và clock status.
- Không thu session secrets hoặc decrypted content nếu không thật cần thiết.
- Khi so sánh client/server, cân nhắc NAT/proxy làm đổi 5-tuple và TLS termination.

**Một PCAP không có response** chưa chứng minh server không trả lời: có thể một chiều bị chặn, sensor bỏ gói hoặc capture sai interface.

### 9.5. DDoS và volumetric pressure

Khi nghi DDoS, network lead cần:

1. Xác định **PPS/BPS/connections/rate** tại edge và capacity, không chỉ 5xx.
2. Phân biệt spike lưu lượng hợp lệ (campaign/batch) với patterns đáng ngờ.
3. Cùng security đánh giá rate limiting/WAF/upstream scrubbing.
4. Cùng platform xem LB/ingress/node CPU/memory/queue.
5. Cùng app xem endpoint cost, expensive queries, retry storms và business traffic.
6. Chọn mitigation **ít ảnh hưởng traffic hợp lệ nhất**; ghi chính xác rule scope/expiry.

Không block toàn bộ ASN/country/IP range chỉ vì một dashboard chỉ ra lưu lượng cao nếu không có bằng chứng và đánh giá tác động. CDN/shared NAT có thể khiến rất nhiều user hợp lệ dùng chung source IP.

### 9.6. Trách nhiệm bàn giao network → platform/application

Một handoff tốt:

~~~text
Network finding:
  Time: 2026-11-28T09:03:18Z (lab)
  Flow: ingress Pod 10.40.2.18:53012 -> backend 10.40.4.25:8443
  Observation: CNI egress verdict DROPPED at named hook
  Policy: netpol-backend-restrict revision 8
  Scope: affected namespace, observed 4 flow attempts
  Attribution: Pod UIDs confirmed using event-time mapping
  Unknown: behavior on secondary interface / other AZs
  Requested next check:
    Platform confirm policy selection and desired revision.
    Application confirm backend request ID absent for these tests.
~~~

Địa chỉ và dữ liệu trong ví dụ **giả lập**. CNI verdict ở một hook không chứng minh mọi đường egress của Pod đều bị chặn; cần gắn observation point rõ ràng.

## 10. Platform team: Kiểm tra runtime, controllers và đường kết nối nội bộ

### 10.1. Tách “desired state” khỏi “actual runtime”

Platform cần xác minh:

- Kubernetes objects được khai báo đúng (Deployment, Service, Ingress/Gateway, NetworkPolicy, Secret, ConfigMap).
- Controller đã reconcile và data plane nhận cấu hình mới.
- Pod/Node có healthy, endpoint readiness và tài nguyên đủ?
- Service/EndpointSlice có trỏ **đúng Pods, đúng port, đúng region/zone**?
- CNI/firewall/mesh sidecar/enforcement agent có áp policy mới?
- Certificates/identity của workloads có hợp lệ, expiry, trust chain đúng?
- Recent rollout/rollback, autoscaling, node replacement có tương quan thời điểm lỗi?

**Một Deployment Ready không chứng minh Service route đúng**; readiness probe có thể chỉ kiểm tra health endpoint đơn giản.

### 10.2. Lệnh Kubernetes chỉ đọc dùng trong cluster lab được cấp RBAC

~~~bash
# Chỉ với namespace và workload mà bạn được phép xem.
kubectl get deployments -n incident-lab
kubectl get pods -n incident-lab -o wide
kubectl get services -n incident-lab
kubectl get endpointslices -n incident-lab
kubectl get ingress -n incident-lab
kubectl get networkpolicies -n incident-lab

# Thay các placeholder bằng tên object đã được owner cấp.
kubectl describe deployment checkout-api -n incident-lab
kubectl describe service checkout-api -n incident-lab
kubectl describe pod checkout-pod-lab -n incident-lab
~~~

Các lệnh này xem **trạng thái API/resources**, chưa chứng minh packet/HTTP chạy qua data plane thành công. Trong cluster thật, quyền **list/watch** có thể bị giới hạn; một kết quả **Forbidden** là RBAC, không chứng minh object không tồn tại. Đừng tự dùng kubeconfig của người khác để vượt quyền.

### 10.3. Kubernetes NetworkPolicy và hiệu lực thực

Một NetworkPolicy chuẩn khi chọn Pods và quy định ingress/egress sẽ phụ thuộc **CNI hỗ trợ thực thi**. Khi điều tra:

1. Xác định namespace, **label selectors và Pod UIDs tại event time**.
2. Xem Pod đang bị ingress/egress isolation từ những policies nào.
3. Xem **source/destination, ports, namespaceSelectors, podSelectors**.
4. Đối chiếu CNI flow verdicts với **policy revision** đã apply.
5. Xác định có hostNetwork, NodeLocal DNSCache, secondary interface, SR-IOV hoặc service mesh khác đường hay không.
6. Phân biệt Kubernetes API object với **cloud security groups** có thể cùng chặn.

Một **NetworkPolicy allow mới** không mặc nhiên ghi đè một **cloud firewall deny** ở lớp khác. Tùy CNI, product-specific policies cũng có precedence riêng; không suy từ ngữ nghĩa API chuẩn sang mọi extension.

### 10.4. Service mesh và mTLS

Nếu ingress gọi backend qua service mesh:

- Network có thể thấy **TCP connectivity** thành công.
- Platform mesh control plane có thể báo **certificate trust, workload identity hoặc authorization policy** thất bại.
- Application có thể **không nhận request** nếu sidecar/gateway từ chối trước khi tới process.
- Một proxy có thể terminate/re-originate TLS, tạo nhiều TLS hops và logs khác nhau.

Phân biệt **mTLS handshake error** với HTTP **RBAC deny** ở mesh và **app-level 403**. Chỉ có TCP connect success không đủ nói traffic được mesh cho phép.

### 10.5. Rollout và lỗi cấu hình lan theo thời gian

Trong incident sau deploy, platform lead cần biết:

| Thuộc tính | Vì sao quan trọng |
| --- | --- |
| **Deployment revision/image digest** | Xác định code/runtime version thật |
| **ReplicaSet/Pod UID history** | Không gán log cũ cho Pod mới trùng IP |
| **Ingress/Gateway revision** | Route/host/path/certificate đã đổi? |
| **NetworkPolicy/CNI version** | Policy intent và enforcement đã thay? |
| **Secret/CA rotation** | mTLS trust và expired cert có thể khác giữa pods |
| **HPA/node scaling** | New pods/nodes có khác network policy hoặc endpoints |
| **DNS/CoreDNS updates** | Search suffix, resolver timeout, NXDOMAIN changes |
| **Cloud LB target health** | L4/L7 health check có khớp business service không |

Nếu chỉ lỗi một AZ/node, có thể có **stale CNI state, node-local DNS/conntrack, certificate secret hoặc route drift**; không mở toàn bộ network rules trước khi xác định phạm vi.

### 10.6. Handoff platform → application/network

~~~text
Platform finding (lab):
  Resource: cluster-a / namespace checkout / ingress-checkout
  Revision: checkout rollout 42; ingress policy 8
  Observed: 6/6 backend Pods Ready; Service endpoints include all 6
  CNI: new policy selects ingress Pods, egress to backend/8443 denied
  Control plane: policy object present
  Data plane: drop logs corroborate revision 8
  Unknown: some long-lived TCP sessions may remain established
  Request:
    Network validate route and firewall at next hop.
    Application validate synthetic transaction after narrow fix.
~~~

Thông tin **Ready** ở đây không thay business readiness; Application DRI phải thực hiện end-to-end verification.

## 11. Application team: Chứng minh tác động nghiệp vụ và lỗi dependency

### 11.1. Không chỉ nhìn status code

Application cần cung cấp:

- **Affected operations:** login, checkout, upload, webhook, payment capture, order confirmation?
- **Request correlation:** trace ID/request ID, tenant/service identity có quyền.
- **Error class:** timeout, 5xx, authn/authz, database deadlock, rate limiting, business validation.
- **Dependency graph:** DB, queue, cache, third-party API, token issuer, feature flag provider.
- **Retries/idempotency:** hành vi retry có gây xử lý trùng, dead-letter queue hoặc backlog?
- **Data integrity:** giao dịch đang pending, committed, rolled back hay cần đối soát?
- **Release/change:** code revision, config/feature flag, library/SDK changes.

**Một API trả HTTP 200 không chứng minh giao dịch đúng** nếu kết quả nghiệp vụ sai hoặc side effects chưa hoàn tất. Với thanh toán, cần kiểm tra **transaction state và duplicate prevention**, không phát lại request bằng tay khi chưa hiểu idempotency.

### 11.2. Từ dấu hiệu tới giả thuyết

| Quan sát ứng dụng | Giả thuyết | Dữ liệu đối chiếu |
| --- | --- | --- |
| **Request không có trong app logs** | Bị chặn trước process hoặc logging gap | Ingress/WAF/CNI, trace coverage |
| **Request nhận nhưng DB connect timeout** | Route/SG, pool exhaustion, DB overload | Platform/network flows + DB metrics |
| **Một API route trả 403** | App authz hoặc gateway policy | Auth decision logs, WAF/mesh policy |
| **Callbacks không về sau DNS change** | Wrong public DNS/region/partner allowlist | Resolver, edge/LB logs, partner status |
| **Client timeout sau release** | App processing slow, retry storm hoặc infra bottleneck | Traces, heap/CPU, dependencies |
| **502 chỉ với upload lớn** | Proxy request-body limit/timeout hoặc app streaming | Edge/ingress config, app body handling |
| **Giao dịch bị nhân đôi sau failover** | Retry/idempotency bug, queue re-delivery | Business transaction log, outbox/queue state |
| **Tất cả application logs bỗng ngừng** | Logging pipeline outage hoặc app process down | Collector health, node logs, synthetic checks |

### 11.3. Tracing giúp xác định hop cuối có xử lý

Trong distributed tracing có thể có các spans:

~~~text
edge.request (traceID=T1)
  -> ingress.forward
    -> checkout-api.handler
       -> pricing-service.call
       -> database.query
       -> payment-provider.request
~~~

Nếu trace dừng ở **ingress.forward**, đó là một tín hiệu cần xem ingress→app nhưng **không tuyệt đối chứng minh app không nhận**: instrumentation, sampling, header propagation hoặc exporter có thể lỗi. Application team cần đối chiếu **app logs và independent metrics**.

**Không đưa user passwords, bearer tokens hoặc thẻ thanh toán vào trace attributes** chỉ để gắn correlation. Nếu cần nhận diện tenant, dùng identifier/role phù hợp chính sách và quyền xem log.

### 11.4. Timeout budget và retry amplification

Một request có thể qua:

~~~text
Browser timeout:          30s (ví dụ)
Edge proxy timeout:       25s
Ingress upstream timeout: 20s
App DB request timeout:   15s
Payment SDK retry policy:  3 attempts
~~~

Các số chỉ là **ví dụ**, không phải giá trị khuyên dùng. Các timers lệch có thể khiến edge trả **504** trong khi backend vẫn xử lý, dẫn đến **retry trùng**. Khi một dependency chậm, retries không có jitter/backoff có thể tạo **thundering herd**, làm mạng, CPU, connection pools và provider tệ hơn.

Application team cần:

- Biết **end-to-end deadline** và timeouts từng hop.
- Xác định retry có an toàn/idempotent không.
- Giảm fanout/concurrency khi phục hồi nếu cần.
- Dùng circuit breaker/degraded mode theo thiết kế.
- Không tăng timeout vô hạn khi backend đang quá tải.

### 11.5. Application authorization khác network reachability

Một HTTP 403 có thể phát từ WAF, gateway, service mesh hoặc backend application. Nếu backend nhận request và từ chối **tenant/resource ownership**, mở firewall **không sửa được** và có thể làm tăng bề mặt tấn công.

Ngược lại, một gateway chặn policy khiến app không có request log; app team cần cung cấp **expected route/identity/operation** để network/platform xác minh grant hẹp đúng mục tiêu.

### 11.6. Application handoff với kết luận có giới hạn

~~~text
Application finding (lab):
  Request: trace T1, checkout POST /orders
  Time: 09:02:07Z
  Route: ingress -> checkout API
  Handler reached: NO, verified in application access logs for request ID T1
  Overall request result: 502 at ingress
  Available evidence: ingress forward attempt, app log search, synthetic request
  Logging health: NORMAL for peer requests in same window
  Suspected layer: ingress->backend path or mesh interception
  Needed: Platform CNI/mesh verdict, Network route/firewall logs
  Business risk: retries may create duplicate orders; hold uncontrolled replay
~~~

**Không chỉ dùng việc không tìm thấy trace** như bằng chứng duy nhất handler không chạy. Kết luận mạnh hơn khi **logging pipeline có heartbeat, ingress có request ID và các peer requests vẫn được ghi**.

## 12. Quyết định containment, mitigation và rollback không được tách khỏi nhau

### 12.1. Phân biệt ba loại hành động

| Loại | Mục tiêu | Ví dụ | Rủi ro nếu làm sai |
| --- | --- | --- | --- |
| **Containment** | Giảm khả năng gây hại/lan rộng của threat đang hoạt động | Cô lập một compromised workload, thu hồi token, chặn egress đích cụ thể | Mất bằng chứng hoặc cắt luồng business hợp lệ |
| **Mitigation** | Giảm hậu quả trước khi tìm root cause | Rate limiting một route, giảm rollout traffic, tạm chuyển vùng | Che dấu root cause hoặc gây bottleneck mới |
| **Rollback/recovery** | Khôi phục trạng thái được biết là hoạt động | Revert Ingress/CNI/WAF policy revision, rollback app release | Quay lại phiên bản có lỗ hổng hoặc dữ liệu schema không tương thích |

Một hành động có thể thuộc nhiều nhóm, nhưng **mục đích và tiêu chí thành công** phải rõ. Ví dụ rollback một NetworkPolicy sai phục hồi availability, nhưng có thể mở lại quyền egress trái chính sách nếu revision cũ không còn an toàn.

### 12.2. Thẩm quyền thay đổi không đồng nhất thẩm quyền điều tra

IC quyết định ưu tiên và điều phối; owner của thành phần phải thực hiện theo **runbook, IAM/RBAC và quy trình phê duyệt**. Đối với thay đổi lớn:

1. Ghi **current state, policy revision, owner**.
2. Nêu **những người cần tham vấn**, nhất là security khi ảnh hưởng network trust boundaries.
3. Xác định **blast radius**, cả tenant/region/cluster/port/protocol.
4. Đề xuất **thay đổi nhỏ nhất có thể đảo ngược**.
5. Ghi **positive và negative verification tests**.
6. Gắn **rollback trigger** dựa trên metric và thời gian.
7. Chỉ thực thi khi có **authority và người canh**.
8. Cập nhật timeline ngay sau thay đổi, ghi revision actually deployed.

**Không tự ý tắt WAF, mở 0.0.0.0/0, dỡ mTLS hay disable toàn bộ NetworkPolicy** chỉ để xem lỗi có biến mất. Nếu phải dùng ngoại lệ khẩn cấp, phạm vi, thời hạn và audit phải được xác lập.

### 12.3. Change window khẩn cấp phải có tính đồng bộ

Trong một incident, **hai thay đổi cùng lúc** có thể khiến kết quả không thể quy nguyên nhân. Ví dụ network nới ACL, platform restart Pods và application rollback code trong cùng phút: khi ứng dụng hồi phục, không thể biết thay đổi nào có tác dụng hay đã mở rủi ro mới.

Thực hành:

~~~text
Decision ID: DEC-07
Approved by: Authorized incident/change role
Technical owner: Platform DRI
Current revision: CNI policy 8
Proposed revision: CNI policy 7 (scoped ingress->backend only)
Start UTC: documented
Expected improvement: TCP/8443 flow no longer DROPPED
Security invariant: All non-approved egress remains denied
Positive test: synthetic order read or safe validation
Negative test: unrelated management endpoint still denied
Abort/rollback trigger: new errors or security invariant fails
Verification owner: Network + Application DRI
~~~

Đây là template; không phải lệnh áp policy. Với **controlling incident** nghi breach, có thể cần hành động đồng thời để hạn chế nguy cơ ngay lập tức, nhưng IC phải ghi sự phụ thuộc và mốc của từng thay đổi.

### 12.4. Containment có thể làm mất chứng cứ

Những hành động như **reboot host, delete Pod, flush conntrack, rotate secret, isolate subnet, scale-to-zero** có thể thay đổi hoặc xóa volatile state. Khi có nghi xâm nhập:

- Security/IR lead xác định **điểm nào cần giữ log/memory/flow/cloud audit**.
- Platform/Network xác định **điểm có thể cô lập** mà giảm hại và giữ được evidence theo khả năng.
- Application team bảo vệ **transaction logs, data access audit, message queues và consistency state**.
- Quyết định cân bằng **bảo vệ dịch vụ/người dùng** với forensic needs.

**Không trì hoãn containment nguy hiểm chỉ vì muốn bảo toàn mọi byte log**; phải dùng risk-based incident policy, ghi rõ điều có thể mất và điều đã thu.

### 12.5. Phục hồi nhưng không mở lối tấn công cũ

Một số workaround dễ tạo rủi ro:

| Workaround hấp dẫn | Nguy cơ | Thay thế nên ưu tiên |
| --- | --- | --- |
| Allow all outbound từ app server | Bỏ egress/DLP control | Narrow allow theo workload/destination/protocol |
| Disable WAF toàn domain | Mất protection nhiều routes | Exception ngắn hạn theo route/rule/identity |
| Turn off mTLS giữa services | Mất peer authentication | Sửa cert/trust/identity đúng hop, HA cert rotation |
| Bật public origin trực tiếp | Bỏ qua edge policy/logging | Restore proxy/LB hoặc failover sanctioned route |
| Rollback toàn cluster | Blast radius rất lớn | Rollback revision/object/namespace bị ảnh hưởng |
| Bỏ kiểm tra TLS certificate | Chấp nhận MITM/sai đích | Sửa SAN, CA, truststore và routing |
| Xóa queue để giảm backlog | Mất giao dịch/dữ liệu | Drain/replay có kiểm soát, idempotency |
| Tăng retries vô hạn | Khuếch đại overload | Bounded retries, backoff, circuit breaker |

### 12.6. Ai kiểm tra sau thay đổi?

Không nên để chỉ người triển khai tự tuyên bố PASS. Một cơ chế **cross-team verification**:

- **Network** xác minh đường đi được cho đúng nguồn, **unauthorized paths vẫn bị chặn**.
- **Platform** xác minh data plane/controllers/runtime áp revision và health.
- **Application** xác minh business action và data integrity, không chỉ HTTP status.
- **Security** xác minh containment/identity policies còn hiệu lực nếu có threat.
- **IC** tổng hợp pass/fail và quyết định tiếp tục hoặc rollback.

## 13. Khi sự cố là an ninh mạng: Phối hợp IR, quyền và bằng chứng

### 13.1. Phân biệt incident availability với security incident

Các sự kiện có thể bắt đầu giống nhau:

- DNS anomalies do resolver outage **hoặc** cấu hình bị sửa trái phép.
- WAF/IDS alerts do traffic marketing campaign **hoặc** exploit/abuse.
- CNI egress deny bursts do app config lỗi **hoặc** compromised workload.
- VPN login failures do MFA provider outage **hoặc** credential stuffing.
- TLS errors do certificate rotation lỗi **hoặc** một proxy/certificate không được phê duyệt.

Phân loại phải dựa vào **các sự kiện cụ thể và ranh giới tin cậy**, không dùng một chỉ số đơn lẻ để kết luận tấn công.

### 13.2. Dựng threat hypothesis cùng nhau

Ví dụ security lead đưa giả thuyết: **một workload có thể đã bị chiếm và cố gửi dữ liệu tới đích ngoài allowlist**.

| Nhóm | Bằng chứng hỗ trợ | Điều cần bảo vệ |
| --- | --- | --- |
| **Network** | Egress flows, DNS/Proxy logs, IDS/IPS hits, firewall verdicts | Route/ACL state, NAT mappings, packet evidence |
| **Platform** | Pod UID, image digest, runtime events, service account, Node/CNI logs | Ephemeral runtime/container state và audit |
| **Application** | Data read/export audit, request IDs, service identity scopes | Transaction/data integrity và app logs |
| **Security/IR** | Timeline, indicators, identity compromise evidence, containment priority | Evidence custody, incident classification và coordination |

Một **large outbound byte count** không tự chứng minh có exfiltration; nó có thể là backup hoặc batch export. Ngược lại, **đích nằm trong allowlist** không tự chứng minh dữ liệu được phép chia sẻ: application authorization và DLP còn quyết định mục đích/nội dung.

### 13.3. Không đánh mất định danh nguồn do NAT hoặc Pod IP reuse

Ở Kubernetes/cloud, public NAT IP hoặc source Pod IP **không phải danh tính bền vững**. Để quy luồng:

~~~text
Flow event time (UTC)
Original source IP:port / translated tuple
Cluster + Node + Namespace
Pod UID + workload owner + image digest
ServiceAccount/workload identity
Destination IP:port / domain context
Sensor + observation point + verdict
Associated app access/export event
Confidence and gaps
~~~

Không dùng một **Pod hiện tại có IP giống log cũ** để quy một hành vi mạng xảy ra trước khi Pod đó được tạo. Network và Platform phải trao đổi **historical assignment mappings**; Application/Security kiểm chứng tác động dữ liệu.

### 13.4. Hướng containment có khả năng đảo ngược

Một số lựa chọn theo mức rủi ro:

- Giới hạn egress của **một workload/Pod group** tới đích không được phê duyệt.
- Thu hồi/rotate **workload token, service account permissions hoặc credential** theo kế hoạch đã được duyệt.
- Chặn **một destination/domain** có xác minh, tránh làm hỏng CDN/shared services.
- Cô lập endpoint/host ở network zone đã chuẩn bị sẵn.
- Tạm hạn chế **sensitive API export functionality** nếu nghi data loss.
- Đưa workload về **known-good immutable image** sau khi có evidence và owner approval.

**Không dùng một IP/hostname trên public Internet làm target để thử nghiệm tấn công.** Mọi kiểm thử containment trong bài nên dùng test endpoints do tổ chức kiểm soát.

### 13.5. Evidence preservation và chain of custody

Một record evidence:

~~~text
Evidence ID: E-INC-LAB-008-04
Source: egress gateway flow log (lab)
Event window: 2026-11-28T09:00:00Z..09:05:00Z
Collector ID and format:
Hash / integrity digest:
Storage location with RBAC:
Collected by authorized analyst:
Related Pod UID / asset ID:
Original event preserved? yes/no
Normalized transformation:
Retention/handling classification:
Known gaps / sensor loss:
~~~

Khi chuyển hồ sơ giữa các đội, chỉ chia sẻ **tham chiếu tới kho bằng chứng có phân quyền**, tránh gửi raw PCAP chứa credentials hoặc PII lên kênh trò chuyện chung.

### 13.6. Không để containment chặn khả năng xử lý sự cố

Chặn toàn bộ network của một cluster/region có thể cắt:

- Log shipping/telemetry.
- Identity/PKI/certificate refresh.
- Control-plane access phục vụ khôi phục.
- Health checking và disaster recovery.
- Các giao dịch đang cần hoàn tất để giữ tính toàn vẹn dữ liệu.

Network/Platform phải cùng security xác định **management plane và forensic visibility** có còn hoạt động hay không sau containment. Nếu không, cần kế hoạch độc lập được phê duyệt, **không tự mở lại untrusted egress** chỉ vì chưa truy cập được log.

### 13.7. Lưu ý truyền thông về dữ liệu và pháp lý

Nếu có khả năng data breach, **Security/Privacy/Legal** cần đánh giá nghĩa vụ thông báo theo phạm vi pháp luật/hợp đồng áp dụng. Đội kỹ thuật không nên tự khẳng định “không có dữ liệu bị lộ” chỉ vì chưa tìm thấy anomaly trong logs có điểm mù. Đồng thời, không được công bố “đã bị đánh cắp” khi mới có flow indicators.

Mẫu định tính đúng:

> “Chúng tôi xác nhận có kết nối bất thường từ workload X tới đích Y. Hiện chưa đủ bằng chứng để kết luận dữ liệu nào, nếu có, đã rời hệ thống; việc đối chiếu application data-access logs đang diễn ra.”

## 14. Giao tiếp trong incident: Nhịp, thuật ngữ và bàn giao

### 14.1. Mỗi cuộc cập nhật trả lời năm câu

Một cập nhật nhanh cần:

1. **Impact:** ai/chức năng nào bị ảnh hưởng, mức độ và phạm vi?
2. **Observed facts:** bằng chứng nào đã xác minh, nguồn nào?
3. **Current hypothesis:** chúng ta nghi gì, độ tin cậy bao nhiêu?
4. **Actions:** ai đang làm gì, có thay đổi production nào?
5. **Next checkpoint:** khi nào có cập nhật tiếp và điều kiện thay đổi ưu tiên?

**Không biến update thành cuộc tranh luận xem lỗi thuộc nhóm nào**. Những giả thuyết chưa chứng minh có thể tồn tại song song, nhưng mỗi nhánh phải có owner và phép kiểm tra.

### 14.2. Mẫu cập nhật nội bộ ngắn

~~~text
[INC-LAB-008] Update at 09:15 UTC
Impact: Checkout 502 elevated in region east; 2/3 synthetic routes affected.
Confirmed: TCP to edge healthy; ingress->backend/8443 drops observed
           on named CNI enforcement point after revision 8.
Unknown: Total real-user error rate; app transaction retry consistency.
Actions: Platform preparing scoped rollback (approved by change owner).
         Network verifying rule before/after.
         Application checking idempotency and business endpoints.
Risk: Broad policy rollback could reopen egress; negative tests required.
Next checkpoint: agreed UTC time in incident channel.
~~~

Các tỷ lệ là **minh họa**, không dùng thay số thật trong báo cáo. Nếu nguồn là synthetic probes, phải ghi rõ như ví dụ.

### 14.3. Mẫu truyền thông khách hàng

Truyền thông bên ngoài nên tập trung vào **triệu chứng xác minh, phạm vi, cách ứng phó và kênh cập nhật**, không nêu nguyên nhân/tấn công khi chưa có bằng chứng:

~~~text
Chúng tôi đang xử lý sự cố làm một số yêu cầu thanh toán chậm
hoặc thất bại tại một khu vực dịch vụ. Nhóm vận hành đang giảm
ảnh hưởng và kiểm tra tính toàn vẹn giao dịch. Chúng tôi sẽ cập nhật
trên kênh trạng thái chính thức khi có thông tin đã xác minh.
Người dùng không nên gửi lại giao dịch nhiều lần nếu hệ thống
đang thông báo kết quả chưa xác định; hãy kiểm tra trạng thái đơn hàng.
~~~

Đây là **mẫu giao tiếp minh họa**, phải được điều chỉnh theo dịch vụ, chính sách truyền thông và tình trạng giao dịch thực. Không hứa thời điểm phục hồi nếu chưa có dự báo đáng tin.

### 14.4. Nghiêm cấm đưa giả thuyết thành phát ngôn chắc chắn

| Câu dễ gây hiểu nhầm | Cách viết có trách nhiệm |
| --- | --- |
| “Network đã sạch.” | “Không thấy flow deny tại hai hooks đã kiểm tra; chưa bao phủ AZ-C.” |
| “Kubernetes OK.” | “6/6 Pods Ready, nhưng synthetic checkout vẫn lỗi.” |
| “Không bị rò dữ liệu.” | “Chưa có bằng chứng xác nhận data loss; còn gaps X/Y cần kiểm tra.” |
| “DDoS từ quốc gia Z.” | “Edge ghi lưu lượng tăng từ một số nguồn, chưa xác minh tính chất và quy mô.” |
| “Lỗi do deploy.” | “Thời điểm bắt đầu tương quan với deploy revision 42; đang xác minh causal link.” |
| “Đã xử lý xong.” | “Mitigation áp dụng, business tests PASS trong observation window, đang theo dõi.” |

### 14.5. Handoff giữa các ca trực

Khi thay ca, cần tóm tắt:

~~~text
Incident ID and current SEV:
IC and outgoing/incoming leads:
Current impact and business risk:
Confirmed facts with evidence links:
Live hypotheses + confidence:
Changes already deployed + exact revisions:
Pending tests and owners:
Rollback/containment conditions:
Known telemetry gaps and incomplete analysis:
Next checkpoint and external communication owner:
Temporary exception expiry / follow-up ticket:
~~~

Handoff không hoàn tất chỉ bằng nhắn “đã bàn giao”. Người nhận nên xác nhận **đã hiểu active mitigations, credentials/permissions cần dùng, các lệnh bị cấm và hành động sắp tới**. Nếu còn tình huống nguy hiểm, IC giữ command cho tới khi transfer rõ.

### 14.6. Ghi quyết định khi có bất đồng

Network có thể muốn rollback firewall, Security phản đối vì rule cũ từng chặn đường rò dữ liệu. Không nên tự tranh luận bằng cảm tính; IC cần:

1. Ghi **hai mục tiêu đang xung đột**: availability và exposure.
2. Yêu cầu **evidence/impact/scope** từ mỗi nhóm.
3. Liệt kê phương án hẹp hơn và tác dụng phụ.
4. Gọi đúng **risk/authority owner** nếu vượt quyền IC.
5. Ghi **quyết định, lý do, owner, expiry và verification**.

**Cộng tác tốt không có nghĩa mọi người phải đồng ý ngay; nghĩa là bất đồng được giải quyết bằng bằng chứng và thẩm quyền rõ ràng.**

## 15. Case study A — HTTP 502 sau rollout NetworkPolicy

### 15.1. Bối cảnh

Ứng dụng **checkout-api** chạy trong Kubernetes sau một CDN/WAF, load balancer và ingress controller. Hệ thống vừa cập nhật **NetworkPolicy** để hạn chế kết nối ingress→backend. Khách hàng thấy checkout trả HTTP 502 tại edge; dashboard application lại thiếu request traces.

Đây là **kịch bản giả lập**. Tên namespace, IP và số liệu chỉ nhằm minh họa cách phối hợp, không đề cập sự cố công ty cụ thể.

### 15.2. Topology và dấu hiệu ban đầu

~~~mermaid
flowchart LR
    U["Synthetic checkout client"] --> E["WAF/LB"]
    E --> I["Ingress controller"]
    I -. "TCP/8443 dropped" .-> CNI["CNI policy hook"]
    CNI --> S["checkout-api Service/Pods"]
    S --> DB["Orders database"]
    N["Network"] -. "Flow verdict" .-> CNI
    P["Platform"] -. "Policy revision/endpoints" .-> I
    A["Application"] -. "Trace/transaction state" .-> S
~~~

### 15.3. Timeline quan sát

| UTC giả lập | Observation/action | Đội xác minh |
| --- | --- | --- |
| **08:55** | Change record đã phê duyệt áp NetworkPolicy revision 8 | Platform |
| **08:57** | Error rate synthetic checkout tăng | Application/SRE |
| **08:58** | Edge nhận request, trả 502 vì upstream fail | Network/Edge owner |
| **08:59** | Ingress controller có route hợp lệ; backend EndpointSlices có Pods | Platform |
| **09:00** | CNI ghi DENY ingress Pod→backend/8443 tại policy hook | Network/Platform |
| **09:01** | Application không nhận request ID đã thử, các log pipelines vẫn hoạt động | Application |
| **09:02** | IC duyệt rollback hẹp cho rule sai với verification plan | IC/Change owner |
| **09:04** | Policy revision 7 được reconcile theo platform | Platform |
| **09:05** | Test kết nối ingress→backend PASS, ngoài quyền vẫn DENY | Network |
| **09:07** | Checkout synthetic PASS và business state đúng | Application |
| **09:10** | Chuyển sang observation window và kiểm tra các AZ khác | IC |

### 15.4. Phân tích vì sao các dashboard không mâu thuẫn

- **Edge healthy**: người dùng vẫn tới được listener; upstream đã lỗi.
- **Ingress route tồn tại**: control plane có cấu hình, nhưng data plane ở CNI chặn kết nối.
- **Pod Ready**: readiness có thể kiểm tra tại node/Pod nhưng không chứng minh ingress có quyền vào Pod.
- **Application không có trace**: request bị chặn trước process (theo correlated evidence), không phải app code nhất thiết gây ra 502.
- **CNI DENY**: là bằng chứng tại enforcement point đó, cần network/platform xác nhận rule owner và mọi hop khác.

### 15.5. Quyết định sửa đổi có giới hạn

Thay vì cho **allow all egress** từ ingress namespace, Platform DRI đề xuất phục hồi rule **chỉ ingress source identities→backend selected Pods:8443** đã được duyệt trước đó, trong khi policy giới hạn traffic sang admin/database zones vẫn giữ nguyên.

Trước khi áp:

1. Network đối chiếu route/firewall ngoài CNI.
2. Platform xác nhận revision 7 không có các lỗ hổng đã bị loại ở revision 8.
3. Application xác định nghiệp vụ cần test.
4. IC phê duyệt theo change authority.
5. Ghi rollback/monitoring criteria.

Sau khi áp, network negative test cần chứng minh **management TCP/22 hoặc DB destinations ngoài quyền vẫn bị từ chối**; application kiểm tra **checkout thực sự xử lý đúng và không tạo order trùng do retry**.

### 15.6. Kết luận và hành động sau sự cố

Root cause trong kịch bản: policy selector/egress rule không bao phủ đúng backend target/port sau một thay đổi kiến trúc. Nhưng postmortem cần ghi rõ **tại sao review/test không bắt được**:

- Không có **end-to-end negative/positive canary** khi deploy NetworkPolicy.
- Người áp policy chỉ xem object đã apply, không xem CNI verdict.
- Probe readiness không đi qua ingress path.
- Không có tiêu chí abort rõ cho network policy deployment.

Action items có thể: thêm **policy integration test**, canary rollout theo namespace, owner mapping ingress/backend, request ID tracing, và diễn tập rollback hẹp.

## 16. Case study B — DNS và mTLS sau khi rotate certificate

### 16.1. Bối cảnh

Một cluster có **service mesh mTLS** và dùng private DNS để tìm service. Sau khi rotate certificate/trust bundle, một số yêu cầu **billing-api → ledger-service** thất bại. Người dùng chỉ thấy 503; network team nói TCP/8443 tới một số backend vẫn thành công.

Mục tiêu là **phân biệt lỗi DNS, kết nối TCP, handshake mTLS và application authorization**.

### 16.2. Bốn lớp có thể thất bại

~~~text
billing-api
  1. DNS service name lookup
  2. Route to ledger-service endpoint
  3. TCP connect to sidecar/gateway
  4. mTLS peer authentication / trust bundle
  5. HTTP/gRPC authorization and ledger business logic
~~~

Những tầng này có thể cho kết quả khác nhau theo Pod/node/zone. Chẳng hạn DNS trả **NOERROR** không có nghĩa TLS chain đúng; TCP established không có nghĩa peer certificate được tin; một **gRPC status PERMISSION_DENIED** không mặc định do firewall.

### 16.3. Phân phối nhiệm vụ

| Đội | Câu hỏi | Dữ kiện cần gửi |
| --- | --- | --- |
| **Network** | Có packet drop hoặc reset ở TCP/8443 giữa source/dest? | CNI/cloud flow verdict, route, NAT/MTU theo Pod UID |
| **Platform** | Secret/trust bundle CA có đồng bộ trên mọi sidecars? | Mesh policy, cert expiry, serial/issuer, SDS/control plane status |
| **Application** | Request nào tới được ledger handler, operation nào lỗi? | Trace IDs, gRPC/HTTP status, business impact |
| **Security/PKI** | CA rotation có hợp lệ, có credential compromise hoặc policy regression? | PKI change record và validation policy |
| **IC** | Có rollback an toàn hay cần certificate repair? | Impact, blast radius, risk decision |

### 16.4. Timeline gợi ý

~~~text
10:00Z  Trust bundle revision 12 deployed to half of sidecars.
10:02Z  billing-api p95 and failed request ratio rise.
10:03Z  TCP established on many affected flows (network evidence).
10:04Z  Mesh log shows peer certificate validation failure for subset.
10:05Z  Application traces show ledger handler missing for those requests.
10:06Z  Platform identifies inconsistent trust revision among sidecars.
10:08Z  Authorized repair/rollback of trust distribution starts.
10:11Z  Mesh handshake success and business ledger checks pass.
~~~

**Dữ liệu hoàn toàn giả lập.** Không nên dùng **khôi phục CA cũ** nếu CA đã bị compromise chỉ để giảm downtime. Security/PKI cần xác định phương án tin cậy an toàn, có thể là phân phối đúng bundle mới, rotate certificates theo thứ tự và verify mTLS giữa các phiên bản.

### 16.5. Điều làm case này khác lỗi network

Nếu packet path cho kết nối TCP thành công nhưng **mTLS peer validation** thất bại, mở firewall rộng hơn thường không sửa được. Có thể cần:

- Correct CA chain/trust bundle.
- Synchronize sidecar/gateway config distribution.
- Check SAN/service identity và certificate lifetime.
- Verify clock/PKI issuance.
- Separate client↔edge TLS khỏi mesh service↔service TLS.

Không tắt **mTLS STRICT** hoặc chọn trust-all trên production để “thử nhanh”. Kiểm tra trong lab/staging và dùng phương án rollback được duyệt.

### 16.6. Kiểm chứng phục hồi

Platform xác minh **toàn bộ affected sidecars** có trust revision đúng, không chỉ control-plane object. Network xác minh **kết nối ở cả các AZ/vùng bị ảnh hưởng**. Application kiểm thử **ledger operations đúng và không có double write**, đánh giá backlog/retries. Security xác nhận **mTLS peer verification vẫn được bật**, không phát sinh bypass.

## 17. Case study C — Lưu lượng tăng mạnh: DDoS hay retry storm?

### 17.1. Triệu chứng

Tại edge, traffic tới **POST /checkout** tăng nhanh, HTTP 503/504 tăng và CPU tại ingress cũng tăng. Một số nguồn IP public gửi nhiều requests. IC mở incident, có thể cân nhắc DDoS nhưng chưa xác nhận.

**Lưu lượng tăng không mặc định là attack.** Một chiến dịch bán hàng, client bug, retry storm hoặc một dependency timeout cũng có thể khuếch đại số request.

### 17.2. Cách network và application nhìn cùng hiện tượng

~~~mermaid
flowchart LR
    USERS["Legitimate users and retrying clients"] --> EDGE["CDN/WAF rate controls"]
    EDGE --> LB["LB/Ingress"]
    LB --> APP["Checkout"]
    APP --> DB["Payment/DB dependency"]
    DB -. "Slow responses" .-> APP
    APP -. "Timeouts trigger retries at clients" .-> USERS
    NET["Network"] -. "PPS/BPS, sources, edge actions" .-> EDGE
    PLAT["Platform"] -. "Queue/concurrency/CPU" .-> LB
    ATEAM["Application"] -. "Retry behavior, DB cost" .-> APP
~~~

### 17.3. Cần chứng minh trước khi block

| Câu hỏi | Bằng chứng |
| --- | --- |
| Tăng **requests/s, new TCP connections hay bytes/s**? | Edge LB/flow metrics có cùng interval |
| Traffic có phù hợp business campaign? | Release/marketing calendar, sales metric |
| Tỷ lệ request có session/user hợp lệ? | App auth logs/edge bot signals có độ tin cậy |
| Source IP có phải shared CDN/proxy/NAT? | Trusted proxy chain và request attribution |
| Có retry loop từ app/mobile SDK? | Request IDs/idempotency keys, client version |
| Dependency nào bão hòa đầu tiên? | App traces, DB pool, queue, upstream latency |
| WAF/rate limits có đang chặn user thật? | 429/challenge success, business error rate |
| ISP/upstream capacity có bị saturated? | Network interface/PPS/BPS, provider observations |

### 17.4. Phân tách mitigation stream

- **Network/Security:** giữ edge capacity, chọn rate limit/challenge/scrubbing theo evidence và policy; không block quá rộng.
- **Platform:** theo dõi ingress queue, HPA, pod/node capacity, load shedding và autoscaling headroom.
- **Application:** sửa retry budget/idempotency, giảm expensive operations, cache khi đúng semantics hoặc bật degraded mode phù hợp.
- **IC:** điều phối changes để biết **rate-limit hay app retry fix** gây tác động nào; giao tiếp ảnh hưởng tới users.

Không thay đổi mọi thứ cùng lúc. Ví dụ một **global 429 rule** có thể làm client retry mạnh hơn nếu SDK không tôn trọng Retry-After/backoff; Application lead phải xác minh hành vi đó.

### 17.5. Tiêu chí phục hồi

Chỉ số nên gồm:

- Edge traffic/mitigation effectiveness, tỷ lệ người dùng hợp lệ bị challenge nhầm.
- Ingress/backend queue, p95/p99 latency, error rates theo route.
- DB pool/saturation và rollback của retry amplification.
- Checkout business success và **không có duplicate charges**.
- Temporary WAF/limit exceptions có owner và expiry.

**Giảm traffic 70% không tự là thành công** nếu phần bị giảm chủ yếu là người dùng hợp lệ hoặc tấn công đã chuyển sang một route khác.

## 18. Case study D — Nghi có outbound data exfiltration từ workload

### 18.1. Triệu chứng và giả thuyết

Security alert báo một workload **reports-api** bắt đầu có kết nối outbound tới địa chỉ công cộng mới, data out tăng và DNS query pattern khác baseline. Đây có thể là **legitimate report export**, library update, lỗi cấu hình hoặc compromise. Chưa có căn cứ kết luận dữ liệu nào đã bị lộ.

### 18.2. Yêu cầu điều phối đặc biệt

**Security/IR lead** chỉ đạo đánh giá rủi ro và evidence preservation, trong khi:

- Network giữ **egress firewall/proxy/DNS/flow logs**, xác định đường kết nối thực và policy.
- Platform giữ **Pod UID/image digest/service account, process/runtime events, node audit**, tránh xóa Pod trước khi đánh giá volatile evidence.
- Application giữ **data export/audit, API caller, business job schedule, object access logs**, xác minh data classification và quyền xuất.
- IC phối hợp containment kịp thời để giảm rủi ro tiếp diễn.

### 18.3. Một bảng bằng chứng có giới hạn

| Quan sát | Điều được chứng minh | Điều chưa được chứng minh |
| --- | --- | --- |
| Egress flow 600 MB tới public IP trong một giờ | Có network bytes theo sensor/aggregation | Nội dung là dữ liệu nhạy cảm |
| DNS QNAME dài, entropy cao | Có tên khác baseline tại điểm đo | DNS tunneling hoặc data theft |
| App audit có export job được phê duyệt | Có business purpose tương ứng | Mọi bytes đều thuộc job đó |
| Pod vừa restart với image digest mới | Runtime thay đổi | Image bị cài mã độc |
| Service account có quyền storage quá rộng | Có exposure về quyền | Quyền đó đã bị lạm dụng |
| Egress firewall allow rule mới | Policy thay đổi | Thay đổi trái phép nếu chưa xem approval |

### 18.4. Bước an toàn đầu tiên

IC/Security cân nhắc **chặn đúng destination/workload** hoặc giới hạn export operation theo quyền và runbook, đồng thời bảo toàn các logs/metadata cần thiết. Tránh quyết định:

- **Scale toàn namespace về 0** khi có một Pod đang nghi vấn, nếu không cần thiết.
- **Xóa ngay Pod nghi vấn** khi chưa xem evidence preservation.
- **Chặn toàn bộ storage/proxy** khiến backup/identity/telemetry ngừng.
- **Xem toàn bộ traffic data là bị lấy cắp** khi còn thiếu application audit.

Đôi khi containment phải ưu tiên lập tức để ngăn hại; điều quan trọng là **có người chịu trách nhiệm, giới hạn phạm vi và ghi ảnh hưởng/evidence lost**.

### 18.5. Phối hợp điều tra nguồn và nội dung

~~~text
Flow timestamp and original/transformed NAT tuple
  → Pod UID and workload identity at event time
  → Process/runtime/cloud credentials context
  → DNS/proxy destination records
  → Application data read/export events
  → Object/cloud resource audit and destination permissions
  → Evidence-supported data exposure conclusion or unknown
~~~

**Không đồng nhất một public NAT IP với một ứng dụng duy nhất**. Nhiều Pods có thể dùng chung egress IP. Khi flow/source identity không đủ, ghi **attribution confidence** và các điều chưa thể xác minh.

### 18.6. Hồi phục sau containment

Trước khi phục hồi workload:

1. Xác định **known-good image/config**.
2. Revoke/rotate credentials liên quan theo đánh giá IR.
3. Áp network egress least privilege và resource IAM đúng scope.
4. Bảo đảm logging/EDR/flow telemetry hoạt động.
5. Kiểm tra dependencies và data integrity.
6. Đặt thời gian quan sát, kiểm tra repeat suspicious flows.
7. Ghi các giả thuyết chưa giải quyết và trách nhiệm tiếp tục điều tra.

**Đưa workload lên lại không có nghĩa case an ninh đã khép lại**, nhất là khi rủi ro dữ liệu, credential reuse và lateral access còn phải phân tích.

## 19. Case study E — Failover đa vùng nhưng ứng dụng chưa phục hồi

### 19.1. Kịch bản

Một ứng dụng quan trọng chạy ở **region A (primary)** và **region B (standby)**. Sự cố mất kết nối tại A khiến IC quyết định chuyển traffic qua B. Network báo DNS/LB failover thành công; platform báo các Pods ở B đã Ready; application lại phát hiện **đơn hàng vừa được tạo ở A chưa xuất hiện ở B**.

Đây là ví dụ cho thấy **network routing recovery khác data/application recovery**.

### 19.2. Những câu hỏi bắt buộc trước failover

| Nhóm | Câu hỏi chính |
| --- | --- |
| **Network** | Global LB/DNS traffic steering sang B có hiệu lực? TTL/caches/IPv6/VPN/peering thế nào? |
| **Platform** | B có ingress/CNI/mesh/certs/secrets/capacity đủ? Health checks đúng service? |
| **Application** | Database replication lag? Jobs/queues, sessions, idempotency, dependencies có sẵn ở B? |
| **Security/Identity** | B có cùng least-privilege access, mTLS, WAF, audit, DLP? |
| **IC/Business owner** | RTO/RPO, khả năng mất dữ liệu, ưu tiên read-only hay failover đầy đủ? |

**RTO (Recovery Time Objective)** và **RPO (Recovery Point Objective)** là mục tiêu được tổ chức đặt ra, không phải bảo đảm của công nghệ. Nếu replication không đồng bộ, route sang B có thể làm **người dùng nhìn thấy dữ liệu thiếu hoặc tạo giao dịch trùng**; phải cân nhắc chế độ read-only, reconcile hoặc giữ write traffic có kiểm soát.

### 19.3. Failover không chỉ là đổi DNS

~~~mermaid
flowchart TD
    USERS["Clients / DNS caches"] --> G["Global DNS / LB"]
    G --> RA["Region A: impaired"]
    G --> RB["Region B: standby"]
    RB --> API["Application replicas"]
    API --> DATA["Region B data / queues"]
    RA -. "Replication state and lag" .-> DATA
    NET["Network DRI"] -. "Traffic steering / route" .-> G
    PLAT["Platform DRI"] -. "Gateway, pods, mTLS, capacity" .-> RB
    APP["Application DRI"] -. "RPO, transaction semantics" .-> DATA
~~~

Network cần đo **traffic thực sự vào B**, không chỉ console báo failover. Platform cần xác nhận **listener, certificates, regions, ingress endpoints, CNI/mesh policies** đã sẵn sàng. Application phải kiểm tra **business operations, state consistency, pending transactions**.

### 19.4. Readiness và quyết định mở traffic

Một rollout/failover có thể theo các bước:

1. **B đã ready ở tầng mạng, runtime và dữ liệu?**
2. IC xác minh risk tradeoff và business approval.
3. Đưa một tỷ lệ traffic thử **synthetic hoặc tenant canary** với khả năng rollback.
4. Theo dõi 4xx/5xx, p95/p99, data read/write consistency.
5. Tăng dần traffic theo chính sách đã định, không vượt capacity.
6. Ngăn **split-brain writes** nếu hệ thống không hỗ trợ active-active.
7. Đánh giá pending jobs, duplicate callbacks và database consistency.
8. Duy trì logs/trace correlation theo region.

**Không phải mọi hệ thống có thể an toàn khi chạy active-active**, và failback về A cần quy trình riêng. Chuyển route ngay lập tức khi data replication chưa sẵn sàng có thể làm availability có vẻ tốt hơn trong khi data correctness xấu đi.

### 19.5. Kết thúc và failback

Sau khi B phục vụ ổn định:

- Đối chiếu **RPO thực tế với mục tiêu**, ghi giao dịch có khả năng thiếu.
- Đảm bảo không còn **client traffic trực tiếp vào A** ngoài luồng được duyệt.
- Khôi phục replication theo architecture, không tự đồng bộ dữ liệu theo hướng có thể overwrite.
- Xác nhận các network security controls ở B không kém A.
- Lập **separate failback change** khi A khỏe, test rõ và có phê duyệt.

## 20. Khi phụ thuộc bên ngoài: CDN, cloud provider, ISP và nhà cung cấp SaaS

### 20.1. Một sự cố không nhất thiết do đội nội bộ tạo ra

Một DNS provider outage, CDN edge regression, ISP route leak, cloud control plane problem hoặc SaaS dependency chậm có thể ảnh hưởng ứng dụng dù không có deployment mới. Nhưng “provider đang lỗi” cũng không nên được dùng làm kết luận nếu chưa có bằng chứng.

Cần:

1. Xem provider status/advisory nếu có, **ghi thời điểm công bố và vùng dịch vụ liên quan**.
2. So sánh **các paths/regions/providers** với synthetic tests có giới hạn.
3. Kiểm tra **own application resilience**: retries, timeouts, circuit breakers, graceful degradation.
4. Gửi ticket provider với **flow examples, timestamps UTC, request IDs, region, trace IDs và impact**, tránh gửi secrets.
5. Tiếp tục bảo vệ user trong khi chờ provider: failover được phê duyệt hoặc tạm giảm chức năng.

### 20.2. Mẫu yêu cầu hỗ trợ nhà cung cấp

~~~text
Subject: Elevated upstream connection failures — incident INC-LAB-008

Service/region: provider-api in region-B
Observed window (UTC): 2026-11-28T10:00Z..10:15Z
Symptoms: 504 at our proxy, connection timeout toward provider endpoint
Observed sources: our approved egress gateways (references available securely)
Destination: service hostname and port, verified by resolver logs
Selected examples: sanitized request IDs and timestamps
Our findings: DNS and TCP path evidence, origin status if known
Impact: specific business operations affected
Questions: provider-side errors/maintenance? target/route changes?
Contact: on-call incident technical owner
Sensitive artifacts: shared only via approved secure channel
~~~

**Không gửi raw token, personal customer payload, TLS key logs hoặc PCAP chứa bí mật** vào ticket nhà cung cấp chỉ vì họ yêu cầu log. Có thể cung cấp mẫu đã làm sạch, trường network cần thiết và tham chiếu phân quyền.

### 20.3. Ownership khi provider chưa phản hồi

- **Network** tiếp tục so sánh routes/latency/packet loss từ các egress points.
- **Platform** giữ proxy/NAT, pod/node resource và controller health.
- **Application** đánh giá fallback behavior và user-facing impact.
- **IC/comms** không hứa SLA khôi phục nếu không có căn cứ từ provider.
- **Security** theo dõi các thay đổi bất thường của DNS/TLS identity/peering trong lúc xử lý.

Một provider update có thể là **thông tin bổ sung**, không tự thay kết quả đo tại môi trường của bạn. Nếu provider nói “đã resolved” nhưng synthetic app transactions vẫn lỗi, incident chưa nên đóng.

### 20.4. Phân biệt network route và provider application error

| Hiện tượng | Cần kiểm chứng |
| --- | --- |
| DNS resolver trả NXDOMAIN cho provider hostname | Domain/zone và provider DNS configuration, không chỉ route |
| TCP connect timeout tới IP được cung cấp | Firewall/ISP/transit/provider listener và alternate region |
| TLS hostname mismatch sau đổi endpoint | SAN/hostname, DNS/edge redirects, approved certificate chain |
| HTTP 429 do provider | Quota/rate budget, retry policy, contract |
| HTTP 503 do provider | Provider availability, fallback/read-only mode |
| HTTP 200 nhưng API schema thay | Application contract compatibility |

**Có kết nối TCP thành công chưa chứng minh một SaaS API khỏe**. Ngược lại, một HTTP 429 hợp lệ có thể phản ánh quota business, không phải sự cố network.

## 21. Một giao thức làm việc chung cho ba nhóm trong 15 phút đầu

### 21.1. Mục tiêu là đồng bộ bằng chứng sớm, không ép kết luận

Phần này là **khung tabletop minh họa**, không áp thời gian cố định cho tổ chức. Nhịp thời gian thực phải theo SEV/runbook. Trong một incident được ghi nhận:

| Pha ngắn | IC | Network | Platform | Application |
| --- | --- | --- | --- | --- |
| **Khởi tạo** | Mở incident, severity, kênh, owner | Xác minh edge/path chính | Xác minh cluster/proxy/runtime | Xác minh chức năng/mức lỗi nghiệp vụ |
| **Xác minh sơ bộ** | Chọn hypotheses ưu tiên | DNS/TCP/TLS/flow verdict | Ingress/Service endpoints/CNI | Traces, error classification, dependencies |
| **Phân nhánh** | Chốt phép kiểm tra và checkpoint | Cung cấp evidence source/hop | Cung cấp revision/runtime owner | Cung cấp business impact/synthetic request |
| **Mitigation decision** | Phê duyệt theo quyền, ghi risk | Đề xuất narrow route/rule fix | Đề xuất rollback/scale/failover | Đề xuất feature flag/retry guard |
| **Sau thay đổi** | Tổng hợp PASS/FAIL | Verify path + deny invariants | Verify deployed state | Verify end-to-end transaction |

Không phải mọi sự cố đều cần cả ba đội ngay từ đầu. Tuy nhiên với **network symptom ảnh hưởng ứng dụng phân tán**, gọi đúng owners sớm thường tốt hơn chuyển ticket qua từng hàng đợi mà không có chung timeline.

### 21.2. Mẫu yêu cầu từ một đội sang đội khác

~~~text
Requesting team:
Incident ID and severity:
What is confirmed (timestamp UTC, source):
What is only suspected:
Exact source identity and destination:
Protocol, port, region, namespace, request ID:
Requested check:
Why this team is the owner:
Expected evidence/result:
Impact if check fails:
Next checkpoint / owner:
Permission and safety constraints:
~~~

Nếu chỉ gửi **“Network check giúp”**, người nhận có thể mất thời gian tìm môi trường, đích, route, tenant hoặc time range. Một yêu cầu chính xác giảm latency điều tra và hạn chế đụng phạm vi không được cấp quyền.

### 21.3. Cách điều phối những nhánh song song

Sơ đồ:

~~~mermaid
flowchart TB
    IC["Incident Commander / shared timeline"]
    IC --> N["Network: DNS/TCP/firewall evidence"]
    IC --> P["Platform: ingress/CNI/runtime evidence"]
    IC --> A["Application: traces/business impact"]
    N --> MERGE["Evidence checkpoint"]
    P --> MERGE
    A --> MERGE
    MERGE --> DEC{"Một hypothesis có đủ evidence?"}
    DEC -->|Có| CHANGE["Owner-approved scoped mitigation"]
    DEC -->|Chưa| NEXT["Define next discriminating test"]
    NEXT --> IC
    CHANGE --> VALID["Cross-team verification and observe"]
~~~

Điểm quan trọng là **mỗi nhánh tạo bằng chứng độc lập trước checkpoint**, không lặp ba lần cùng một phép ping. IC phải hỏi **“kết quả nào có thể bác bỏ giả thuyết hiện tại?”**, không chỉ “đã kiểm tra xong chưa?”.

### 21.4. Một test phân biệt có giá trị

Nếu nghi lỗi ở network vs app:

- Một client gửi **một safe synthetic request** với unique request ID đến endpoint lab được cấp quyền.
- Network xác minh TCP/TLS/flow path tại ingress/edge.
- Platform xem ingress proxy request/forward, CNI/mesh verdict đến Pod UID.
- Application tìm request ID và xem business handler/external dependency.

Nếu client tới edge nhưng không có ingress event, có thể tập trung **edge→ingress route/logging**. Nếu ingress có forward attempt nhưng CNI DROP, tập trung policy/data plane. Nếu app nhận request và DB query timeout, tập trung **app/data dependency**. Mỗi kết quả vẫn phải xét **log health/sampling**.

### 21.5. Khi nào chuyển từ triage sang mitigation?

Một mitigation không nhất thiết cần root cause 100%, nhưng nên có:

1. **Impact đang diễn ra** và hướng tác động rõ.
2. Phương án có **expected benefit** dựa trên evidence.
3. Blast radius có thể kiểm soát.
4. Security/business invariants được xác định.
5. Owner/approval/rollback/verification sẵn sàng.

Nếu chưa có phương án an toàn, có thể tiếp tục điều tra ở một checkpoint ngắn hơn; tránh **thử hàng loạt changes không đo trước/sau**.

## 22. Tabletop exercise: Diễn tập điều phối sự cố nhiều tầng

### 22.1. Mục tiêu bài diễn tập

Diễn tập không yêu cầu tạo sự cố thật. Người học nhận **một bộ sự kiện giả lập**, chia vai network/platform/application/IC và đưa ra **quyết định có bằng chứng**. Không chạy traffic lớn, scan mạng, disable firewall hoặc thay đổi cluster production.

Kết quả mong đợi:

- Một **incident record** với impact, severity và owner.
- Một **timeline UTC** và bảng fact/hypothesis/unknown.
- Một ma trận **câu hỏi cho từng nhóm** để phân biệt lớp lỗi.
- Một **mitigation proposal** có scope, approval, verification và rollback.
- Một **khung thông báo** nhất quán.
- Một **post-incident action list** có DRI và test nghiệm thu.

### 22.2. Kịch bản nền

Hệ thống thử có:

~~~text
External users
  -> demo DNS resolver and edge
  -> WAF / HTTPS load balancer
  -> Kubernetes ingress
  -> checkout-api service
  -> orders-db (private)
  -> payment-provider API (egress proxy)

Owners:
  Network: edge, WAF, firewall, routes, DNS as scoped
  Platform: cluster, CNI, ingress, gateway, node, mesh
  Application: checkout handler, DB/queue, payment logic
  Security: IR, WAF policy risk, evidence and identity
  IC: severity, coordination, updates, decision log
~~~

Các dịch vụ/nhãn chỉ là **đối tượng mô phỏng**, không cần host hoặc API thật.

### 22.3. Bộ injects mô phỏng

Giảng viên gửi cho các đội từng phần, không công bố hết ngay:

| Inject | Sự kiện | Điều người học cần làm |
| --- | --- | --- |
| **A** | 10:00 UTC: synthetic checkout 502 tăng | Tuyên bố impact có mẫu số và mở incident |
| **B** | 10:02 UTC: edge listener healthy, WAF không có deny tương ứng | Không kết luận network hoàn toàn OK |
| **C** | 10:04 UTC: 6/6 checkout Pods Ready | Không coi Ready = business healthy |
| **D** | 10:05 UTC: deployment của ingress CNI policy mới | Đưa vào timeline, chưa kết luận root cause |
| **E** | 10:06 UTC: CNI flow verdict DROPPED ingress→checkout TCP/8443 | Phối hợp owner policy/route, đề xuất discriminating test |
| **F** | 10:07 UTC: app logs không thấy request ID R1, log pipeline có heartbeat | Nâng confidence lỗi xảy ra trước app handler |
| **G** | 10:08 UTC: Security nhắc rule cũ từng bảo vệ admin port | Không rollback toàn policy nếu mở admin surface |
| **H** | 10:09 UTC: change owner đồng ý narrow allow cho TCP/8443 | Ghi quyết định, owner, rollback và negative test |
| **I** | 10:12 UTC: synthetic checkout PASS nhưng payment callback queue tăng | Không đóng incident; kiểm tra data/queue consistency |
| **J** | 10:15 UTC: dữ liệu cho thấy idempotency keys xử lý an toàn | Bắt đầu observation window và cập nhật stakeholders |

Đây là **sự kiện hư cấu**, không đại diện cho metrics thật và không định nghĩa response time SLO chính thức.

### 22.4. Luật diễn tập

1. **Chỉ IC** thay đổi severity, mở/đóng incident record theo phương pháp đã thống nhất.
2. Mỗi đội có tối thiểu một **evidence owner**.
3. Mỗi quyết định thay đổi phải có **scope/approval/negative test/rollback**.
4. Không dùng các khẳng định vượt bằng chứng: **“network OK”**, **“K8s OK”**, **“chắc bị tấn công”**.
5. Mỗi người phân biệt **observed fact vs hypothesis vs next test**.
6. Communications lead cập nhật bằng những thông tin đã được xác minh.
7. Nhóm khác có quyền nêu rủi ro rollback, nhưng phải chỉ ra **invariant bị phá và phương án hẹp hơn**.

### 22.5. Mẫu bảng chấm theo tiêu chí

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| **Impact clarity** | Có đường lỗi, người dùng/chức năng và mẫu số |
| **Role clarity** | Mỗi nhánh có DRI và owner cho cấu hình |
| **Evidence quality** | Events có timestamp UTC, sensor/hop, policy revision |
| **Cross-layer reasoning** | Phân biệt TCP/TLS, ingress/CNI, app/business |
| **Risk management** | Không mở egress/admin port ngoài mục tiêu |
| **Change discipline** | Có duyệt, scope, rollback và một thay đổi kiểm chứng được |
| **Business verification** | Không đóng chỉ dựa Pod Ready/HTTP 200; có data checks |
| **Communication** | Thông điệp chính xác, không khẳng định nguyên nhân khi chưa biết |
| **Closure quality** | Observation window, exceptions/owners và follow-up |

Đánh giá nên dựa trên **chất lượng lập luận và khả năng kiểm chứng**, không chỉ đội nào tìm root cause trước.

### 22.6. Mẫu kết quả diễn tập tốt

~~~text
STATUS: Mitigated, monitoring
Observed root cause (lab): NetworkPolicy revision 8 dropped
  ingress Pod to checkout backend/8443.
Evidence:
  CNI flow verdict + Platform policy revision + app request absence
Mitigation:
  Scoped allow restored for ingress->checkout/8443 under approval
Negative checks:
  Unauthorized admin/DB reachability remains denied
Positive checks:
  Synthetic checkout and payment flow pass
Residual risk:
  Existing retries and queue backlog under observation
Action items:
  Add canary policy test; improve service owner mapping;
  include business transaction verification in network changes.
Unknown:
  Whether all impacted tenants recovered within the initial window.
~~~

**Một báo cáo đầy đủ phải giữ cả unknowns**, tránh ép kết luận “mọi user đã phục hồi” nếu chỉ kiểm tra một synthetic route.

## 23. Chuẩn bị trước sự cố: Làm sao để phối hợp không bị nghẽn?

### 23.1. Service catalog và dependency ownership

Trước incident, một catalog tối thiểu nên có:

| Thuộc tính | Mục tiêu |
| --- | --- |
| **Service ID / business capability** | Biết ứng dụng phục vụ nghiệp vụ gì |
| **Service owner / on-call group** | Gọi đúng người ngay |
| **Regions/tenants/sensitivity** | Ước lượng blast radius |
| **Ingress FQDN/listener/protocol** | Xác định các cửa vào |
| **Internal service dependencies** | Hiểu API/DB/queue/identity path |
| **Egress approved destinations** | Tránh mở Internet khi dependency lỗi |
| **Network zones / VPC / cluster / namespace** | Tìm đúng policy/routing context |
| **PKI/truststores/secret owners** | Xử lý TLS/mTLS/cert rotation |
| **Observability sources** | Xem logs, metrics, traces, flow verdicts |
| **SLO and business probes** | Biết thế nào là recovered |
| **DR/failover mode** | Có RTO/RPO, cách tránh split-brain |
| **Security/data classification** | Biết containment/investigation cần tham vấn ai |

**Không cần một sơ đồ vĩ đại luôn chính xác tuyệt đối**, nhưng phải có các thông tin giúp IC gọi đúng owner và đặt phép kiểm tra trong vài phút đầu. Catalog cần được cập nhật theo CI/CD/IaC/change process.

### 23.2. Runbook chuẩn bị theo “đường đi”

Các runbook hữu ích thường bắt đầu từ câu hỏi:

- Client không giải được DNS → **resolver/Split DNS runbook**.
- SYN timeout/packet loss → **routing/firewall/LB/VPN runbook**.
- TLS/mTLS failed → **certificate/truststore/mesh runbook**.
- HTTP 502/504 từ ingress → **upstream/EndpointSlice/CNI runbook**.
- Request đến app nhưng DB pool exhausted → **application/data dependency runbook**.
- Traffic burst/IDS alert → **DDoS/abuse incident runbook**.
- Suspicious outbound → **egress/data exposure IR runbook**.
- Regional failure → **RTO/RPO/failover runbook**.

Mỗi runbook nên có **checklist evidence, access prerequisites, safe commands, owner, approve path, possible negative impact, rollback, validation**. Một runbook chỉ có “restart Pod” thường không đủ.

### 23.3. Quyền truy cập trong khẩn cấp

Không nên đợi đến khi có incident rồi mới phát hiện Network không xem được flow logs, Platform không có quyền xem controller status, Application không truy cập được traces hoặc Security không thể lưu forensic snapshots.

Cần:

- **Read-only dashboards/log access** theo least privilege.
- Break-glass accounts có MFA, audit, owner và expiry.
- Cách lấy approved change authority khi đường SSO chính gặp outage.
- Quy trình hợp pháp cho cross-team evidence exchange.
- Test định kỳ quyền truy cập và recovery workflows.

**Break-glass không phải super-admin vĩnh viễn bỏ mọi kiểm soát.** Nếu sử dụng, log phải ghi mục đích, người thực hiện, thời điểm và kết thúc quyền.

### 23.4. Thiết kế observability để nối các nhóm

Trong trạng thái bình thường, nên instrument:

~~~text
External edge:
  request_id, hostname/path category, status, WAF action, target, latency
Network:
  source/destination tuple, NAT mapping, policy verdict, sensor ID
Platform:
  cluster/namespace/Pod UID, ingress/mesh revision, controller errors
Application:
  trace ID, operation, result, dependency spans, business event ID
Identity/Security:
  auth decision, policy version, service/user identity, risk events
SRE:
  synthetic probes, SLO measurements, collector health
~~~

Giữ **identity/correlation consistency** theo time window, không đưa passwords/tokens/PII quá mức vào telemetry. Với HTTP/2, **một TCP connection có nhiều requests**; NAT có thể che source; Kubernetes Pod IP được tái sử dụng. Không xây correlation chỉ từ source IP và port.

### 23.5. Synthetic checks không được làm hại nghiệp vụ

Một health check **GET /healthz** có thể chỉ chứng minh process responsive. Nếu muốn đo business transaction, dùng **synthetic tenant/test objects**, operations có thể rollback, idempotency keys và guardrails; không gửi giao dịch tài chính thật hoặc dữ liệu người dùng.

Khi hệ thống đang suy giảm, synthetic traffic phải có **rate nhỏ và giới hạn** để không thành một nguồn overload. Nếu workload xử lý side effects, chỉ thực hiện khi có test plan được owner xác nhận.

### 23.6. Game day và cross-team readiness

Định kỳ thực hành các trường hợp:

1. DNS resolver failover và cache behavior.
2. Certificate/mTLS rotation giữa ingress và backend.
3. CNI/NetworkPolicy rollout với canary, negative tests.
4. Firewall rule thay đổi làm mất route/egress.
5. DDoS/traffic spike và response phối hợp.
6. Kubernetes node/AZ loss, route failover.
7. Backup/restore và data consistency sau service downtime.
8. Log pipeline mất source trong khi traffic vẫn có.

Không cần phá production để tập: **tabletop, staging, fault injection có kiểm soát hoặc read-only replay** có thể xác minh nhiều quy trình với rủi ro thấp hơn.

### 23.7. SLO và error budget làm nền quyết định

Nếu SLO availability là một tiêu chí quan trọng, IC cần biết **error budget burn**, nhưng metric đó chỉ phản ánh **mẫu số/định nghĩa SLI**. Ví dụ:

- Synthetic probe lỗi không tự đại diện cho mọi người dùng.
- Edge 2xx có thể che business transaction sai.
- Backend 5xx không đo client timeouts không tới app.
- Một service có nhiều tenants/regions cần phân đoạn SLI.

**Ưu tiên business impact và security risk** bên cạnh SLO để không vô tình “sửa dashboard” thay vì sửa dịch vụ.

## 24. Post-incident review không đổ lỗi và theo dõi cải tiến

### 24.1. Phân biệt trigger, contributing factors và root cause

Sau khi dịch vụ ổn định, cần hiểu **vì sao incident xảy ra và vì sao hệ thống không ngăn được impact**, thay vì chỉ tìm cá nhân áp config cuối cùng.

Ví dụ:

- **Trigger:** NetworkPolicy revision 8 được deploy.
- **Immediate technical cause:** rule thiếu đường ingress→backend TCP/8443.
- **Contributing factor:** policy review không có service dependency graph.
- **Detection gap:** synthetic probe không dùng đúng path người dùng; controller status được coi là đủ.
- **Containment gap:** rollback thiếu negative test, có nguy cơ mở thêm quyền.
- **Organizational gap:** network/platform/application không có owner chung cho change end-to-end.

Không coi “người triển khai nhầm” là kết luận cuối nếu quy trình cho phép một thay đổi rủi ro đi qua mà **không có tests/ownership/verification**.

### 24.2. Mẫu cấu trúc postmortem

~~~text
Incident summary:
  Impact, severity, time range, affected users/transactions

Timeline (UTC):
  First symptom, detection, escalation, key decisions,
  mitigation, validation, closure

Technical explanation:
  Data path, control plane vs data plane,
  initiating change, failure mechanism

Business impact:
  Failed operations, retries, data integrity and recovery

Security analysis:
  Whether any policy was weakened / data exposure evidence

What went well:
  Fast detection, clear owner, useful evidence and safe rollback

What made response harder:
  Missing telemetry, unclear owner, undocumented dependency

Contributing conditions:
  Review/test gaps, rollout strategy, alert design

Counterfactual:
  What earlier detection/control could have reduced impact?

Follow-up items:
  DRI, priority, verification test, due date/review, status

Uncertainties:
  Gaps where data or timestamps could not prove a claim
~~~

**Không tô hồng timeline** bằng cách chỉ giữ sự kiện chứng minh giả thuyết cuối. Những quyết định hợp lý dựa trên thông tin lúc đó có thể dẫn tới kết quả không tốt; phân tích cần phản ánh **bối cảnh thực tế**, không chỉ kết quả khi đã biết root cause.

### 24.3. Action items phải đo được

| Action item kém | Action item có thể nghiệm thu |
| --- | --- |
| “Cải thiện monitoring.” | “Thêm SLO alert cho end-to-end checkout theo region/tenant, có owner và test bằng synthetic case.” |
| “Review firewall kỹ hơn.” | “Yêu cầu positive/negative connectivity tests cho mọi egress NetworkPolicy PR trước merge.” |
| “Đồng bộ các đội.” | “Cập nhật service catalog với network/path owners, triển khai incident channel template và quarterly tabletop.” |
| “Sửa TLS.” | “Thêm mTLS trust-bundle rollout canary và test handshake giữa old/new revisions.” |
| “Tránh outage tương lai.” | “Đặt rollback trigger/owner cho LB/WAF policy changes và đo success/failure trong game day.” |
| “Lưu logs tốt hơn.” | “Đo collector event-loss/ingest lag và phát alert khi mất một nguồn critical.” |

Mỗi action item nên có **một DRI, độ ưu tiên, tiêu chí PASS, dependency và kỳ review**. Không mặc định đóng action chỉ vì có ticket hoặc PR merge; cần **verify behavior**.

### 24.4. Hậu kiểm phát hiện lỗ hổng kiểm soát

Một sự cố availability có thể khiến đội nới egress, WAF hoặc network firewall. Sau khi ổn định, Security/Network phải đối chiếu:

- Còn **temporary allow rules** nào không có expiry?
- Có **new ingress paths** cho public origin/backend không?
- mTLS/TLS verification có bị tắt ở bất kỳ hop nào?
- Có **service account/credential** dùng tạm mà chưa thu hồi?
- Logs/IDS/IPS/WAF đã hoạt động trở lại?
- Có policy drift giữa IaC và actual cloud/cluster state?
- Có region/node nào chưa nhận lại baseline?

**Phục hồi business service không được đổi bằng việc để lại bypass bảo mật lâu dài**.

### 24.5. Theo dõi hiệu quả của postmortem

Đánh giá hành động phòng ngừa qua:

- Lần rollout mới có chạy **canary+negative tests** không?
- Các incidents tương tự có được phát hiện **trước khi gây impact diện rộng**?
- Handoff có giảm thời gian xác minh owner/destination không?
- Có bớt **phép test trùng lặp** và **changes cùng lúc** không?
- Đã khắc phục telemetry gaps không?
- Có giảm rủi ro data integrity/retries sau failover không?

**Không ép một postmortem phải chứng minh mọi sự cố trong tương lai đã bị loại bỏ**. Mục tiêu là giảm xác suất, blast radius, thời gian phát hiện/phục hồi và làm rõ rủi ro còn tồn tại.

## 25. Chỉ số đo chất lượng phối hợp

### 25.1. Không chỉ dùng MTTR

**MTTR** có thể được hiểu khác nhau: mean time to repair/recover/resolve tùy tổ chức. Nếu không định nghĩa rõ **điểm bắt đầu/kết thúc** và loại incident, so sánh rất dễ sai.

Nên có các chỉ số:

| Metric | Đo điều gì | Giới hạn cần ghi |
| --- | --- | --- |
| **Time to detect/acknowledge** | Từ symptom/alert đến nhận trách nhiệm | Detection source khác nhau |
| **Time to correct owner** | Khi nào đúng kỹ thuật lead được nhận diện | Không tính blame transfer thành tối ưu hóa |
| **Time to first discriminating evidence** | Khi có bằng chứng loại trừ một hypothesis | Phụ thuộc telemetry coverage |
| **Time to mitigate** | Khi impact được giảm đến mức đã định | Khác full recovery |
| **Time to recover service** | Khi end-to-end business SLI đạt tiêu chí | Cần observation window |
| **Time to establish business consistency** | Khi data/queues/transactions được đối soát | Có thể dài hơn network recovery |
| **Unauthorized policy exceptions** | Còn rule tạm/quyền rộng nào sau incident | Cần audit toàn môi trường |
| **Concurrent change count** | Bao nhiêu thay đổi chồng lên nhau khi điều tra | Không quy kết lỗi tự động |
| **Evidence completeness** | Tỷ lệ cases có UTC/owner/hop/IDs | Không có log có thể do sensor gap |
| **Handoff quality** | Người nhận có đủ impact, unknowns, next actions | Cần đánh giá định tính |
| **Alert precision/coverage** | Dữ liệu có giúp đúng đội phản ứng? | Unknown cases và false negatives |
| **Action item closure verified** | Các biện pháp phòng ngừa đã được kiểm thử? | Merge PR chưa đủ |

### 25.2. Phân biệt thời gian kỹ thuật và thời gian giao tiếp

Ví dụ:

~~~text
10:00  User impact begins
10:02  Alert fired
10:03  Incident acknowledged
10:05  IC starts cross-team coordination
10:08  Correct data-plane deny evidence found
10:12  Narrow mitigation applied
10:15  Synthetic checkout recovered
10:27  Transaction backlog reconciled
10:40  Observation criteria satisfied
~~~

Đây là timeline giả lập. Nếu chỉ tính **10:12→10:15** là MTTR, báo cáo sẽ bỏ qua thời gian phát hiện và vấn đề dữ liệu tới 10:27. Nên trình bày **mốc riêng**: impact start, detect, mitigate, business recovery, verified closure.

### 25.3. Tỷ lệ error và kiểm chứng vùng ảnh hưởng

Một phép tính đơn giản:

\[
\text{error rate} =
\frac{\text{requests được xác minh lỗi trong cửa sổ}}
{\text{requests trong cùng cửa sổ, cùng nguồn đo}}
\]

Điều kiện: nguồn đo phải rõ và **mẫu số cùng phạm vi**; không lấy **5xx từ ingress A** chia cho **total requests từ CDN ở cả ba regions**. Sự khác nhau về **sampling, retries, cache hits và synthetic/user traffic** cần được ghi rõ.

Với sự cố bảo mật, **việc không thấy data exfil logs** không tự tính được “0% breach probability”: nếu coverage thiếu hoặc data encrypted ngoài sensor, đó là **unknown**, không là negative evidence chắc chắn.

### 25.4. KPI không nên biến thành công cụ phạt nhóm

Nếu nhóm bị đánh giá chỉ bằng **time-to-close ticket**, họ có động cơ đóng sớm, đẩy ticket sang người khác hoặc xóa unknowns. Chỉ số tốt cần khuyến khích:

- Gọi đúng owner sớm.
- Ghi chứng cứ có ranh giới.
- Mitigation nhanh nhưng không nới security quá mức.
- Business recovery đúng, kể cả data consistency.
- Postmortem thẳng thắn về gaps.

**Đo để cải thiện hệ thống và quy trình, không tìm người chịu lỗi bằng một con số.**

## 26. Checklist điều phối: Trước, trong và sau sự cố

### 26.1. Trước incident: Sẵn sàng

| Kiểm tra | Câu hỏi | Bằng chứng mong đợi |
| --- | --- | --- |
| **Service ownership** | Có business owner, on-call, network/platform/app owners? | Service catalog và escalation list |
| **Dependency map** | Có FQDN, route, ingress, internal APIs, DB/queue/egress? | Architecture và change history |
| **Trust boundaries** | TLS/mTLS/WAF/VPN/ZTNA/PKI ở hop nào? | Data path và cert/identity inventory |
| **Control plane** | Ai sở hữu route, firewall, Kubernetes NetworkPolicy, Ingress? | IaC repo owners/change records |
| **Runbooks** | Có DNS, TCP, TLS, 502, DDoS, egress, failover procedures? | Runbook links có reviewer |
| **Observability** | Có log/flow/trace/request IDs và UTC time? | Synthetic tests và collector health |
| **Permissions** | On-call có read-only evidence access? | RBAC/test run logs |
| **Emergency changes** | Có approval/break-glass/rollback policy? | Change authority và drill |
| **Data integrity** | Có business-level checks/idempotency/reconciliation? | Test tenant, synthetic transaction |
| **Recovery objectives** | Có RTO/RPO và plan theo service/region? | DR plan được duyệt |
| **Privacy/evidence** | PCAP, logs, tokens được phân quyền/retention? | Handling rules |
| **Tabletop** | Đã tập giao tiếp liên đội và chuyển ca? | Exercise review/action items |

### 26.2. Trong incident: Điều phối và chứng minh

| Hạng mục | Điều kiện PASS |
| --- | --- |
| **Incident declared** | Có ID, severity theo impact và IC |
| **Named technical leads** | Network/Platform/Application có DRI khi liên quan |
| **Scope** | Dịch vụ, users/regions/tenants, time window, SLI source rõ |
| **Shared timeline** | Fact/hypothesis/action/decision có timestamps và evidence |
| **Correct hop** | Có sơ đồ/request path và không trộn các TLS/ingress legs |
| **Source attribution** | NAT/Pod UID/VPN/identity theo đúng thời điểm |
| **Network evidence** | DNS/flow/route/TCP/TLS/WAF theo tầng |
| **Platform evidence** | Resource/controller/runtime/CNI/mesh effective state |
| **Application evidence** | Request/trace/dependency/business transaction state |
| **Security assessment** | Nghi threat thì gọi IR và bảo toàn evidence đúng mức |
| **Change control** | Mọi thay đổi có scope, approver, owner, verification, rollback |
| **Narrow mitigation** | Không nới allow all, không bỏ TLS auth hoặc xóa data tùy tiện |
| **Cross-team verification** | Positive test nghiệp vụ và negative security tests khi phù hợp |
| **Communication** | Update đúng fact/unknown, có người chịu trách nhiệm |
| **Telemetry gaps** | Mất logs/sampling/clock skew được ghi rõ |

### 26.3. Sau mitigation: Chưa đóng vội

| Hạng mục | Điều kiện nghiệm thu |
| --- | --- |
| **Technical recovery** | Network route/TLS/ingress/Pod health được xác minh |
| **Business recovery** | Real/synthetic workflow và data integrity đạt yêu cầu |
| **Security invariants** | WAF/firewall/mTLS/egress/private origin vẫn theo policy |
| **Regional coverage** | Những zones/regions/tenants bị ảnh hưởng đã được đo |
| **Queue/retry reconciliation** | Pending jobs/duplicate operations được xử lý an toàn |
| **Observation window** | SLO và errors ổn định theo điều kiện IC/business owner |
| **Exception lifecycle** | Temporary rules/tokens có expiry và owner |
| **Stakeholder update** | Không còn thông tin trái nhau hoặc hứa hẹn không có bằng chứng |
| **Evidence retention** | Logs/PCAP/case artifacts bảo vệ theo chính sách |
| **Postmortem** | Có timeline, nguyên nhân/contributing factors/unknowns |
| **Action plan** | DRI + priority + verification test cho follow-up |

### 26.4. Mẫu biên bản bàn giao cuối ca

~~~text
INCIDENT:
  id:
  severity and current state:
  start UTC / current checkpoint:
  affected service/business impact:

OWNERS:
  IC:
  network DRI:
  platform DRI:
  application DRI:
  security/IR DRI (if applicable):

FACTS:
  evidence item, source, time, observation point, result

HYPOTHESES:
  ranked, confidence, next falsifying test

CHANGES:
  revision, owner, approval, impact, rollback trigger

RECOVERY:
  end-to-end tests, data consistency, security negative checks

UNKNOWN / GAPS:
  sampling, lost logs, unobserved region, unidentified NAT clients

NEXT:
  task owner, checkpoint UTC, communication owner, pending approval
~~~

Không điền **token, customer secrets hay private key** vào biên bản. Nếu evidence cần quyền cao, để **link/ref tới kho đã phân quyền**.

### 26.5. Những câu hỏi IC nên hỏi ở mỗi checkpoint

1. **Điều gì đã thay đổi trong impact so với checkpoint trước?**
2. **Thông tin nào là fact, hypothesis, unknown?**
3. **Bằng chứng nào giúp loại trừ hoặc xác nhận hypothesis ưu tiên?**
4. **Có thao tác nào đang làm khác với change plan không?**
5. **Thay đổi nào vừa được triển khai, và ai đã kiểm chứng nó ở data plane?**
6. **Có rủi ro bảo mật hoặc dữ liệu nào mới xuất hiện?**
7. **Có cần mời owner mới hoặc escalation sang provider/IR không?**
8. **Next action/owner/checkpoint là gì?**

Nếu không có bằng chứng mới, **đừng lặp vô hạn “mọi người đang kiểm tra”**. IC cần chuyển sang một test phân biệt tốt hơn, bổ sung sensor/owner hoặc đánh giá mitigation được kiểm soát.

## 27. Câu hỏi tự kiểm tra và đáp án

**1. Vì sao sự cố HTTP 502 không thể tự gán cho Network team?**

502 có thể do gateway không kết nối/nhận được response hợp lệ từ upstream vì **CNI policy, backend unavailable, TLS upstream sai, timeout hoặc app behavior**. Cần xác định hop phát status, flow và app logs.

**2. Incident Commander có cần là người hiểu TCP/TLS sâu nhất không?**

Không nhất thiết. IC chịu trách nhiệm **mục tiêu, owner, quyết định, nhịp cập nhật và phối hợp**, huy động technical leads cho phân tích chuyên sâu.

**3. Network lead nên cung cấp gì ngoài “ping thành công”?**

Source/destination, routes, ports, firewall/NAT verdicts, TCP/TLS observations, time window, sensor point và phạm vi chưa đo.

**4. Pod Ready có chứng minh ứng dụng nhận được request từ ingress không?**

Không. Readiness có thể PASS ngay cả khi NetworkPolicy/Service endpoints/mesh chặn đường từ ingress tới Pod.

**5. Application team cần xác minh gì sau khi network route được khôi phục?**

Business transaction success, idempotency, queue backlog, data integrity, application authorization và tenant/region coverage.

**6. RACI có nghĩa A và R phải luôn là cùng người?**

Không. A chịu trách nhiệm cuối; R thực hiện. Trong bảng minh họa có thể cùng một nhóm A/R, nhưng mỗi quyết định nên có **một A rõ**.

**7. DRI dùng để làm gì?**

Chỉ rõ một người chịu trách nhiệm **đầu việc cụ thể** và báo kết quả, tránh công việc treo giữa các nhóm.

**8. Fact khác hypothesis như thế nào?**

Fact là observation có nguồn và thời gian; hypothesis là giải thích chưa xác minh. Ví dụ CNI **DROPPED** là fact tại hook; “do revision mới gây ra” cần tương quan thêm.

**9. Tại sao không nên thay firewall, restart Pods và rollback app cùng một phút nếu không bắt buộc?**

Các thay đổi đồng thời làm khó xác định tác dụng, có thể phá evidence và tăng blast radius. Cần kế hoạch, owner, verification và ghi chronology.

**10. Security lead cần tham gia khi nào?**

Khi có nghi **compromise, data exposure, identity misuse, policy bypass hoặc containment** ảnh hưởng bảo mật; security cũng có thể tham vấn về các thay đổi rủi ro cao.

**11. NetworkPolicy object có tự chứng minh traffic bị chặn không?**

Không. CNI phải thực thi ở data plane; cần flow verdict và negative/positive test đúng source/dest.

**12. Vì sao cần Pod UID thay vì chỉ IP?**

Pod IP có thể được tái sử dụng; phải gắn identity theo event time và owner/revision.

**13. Vì sao không lấy một public NAT IP làm bằng chứng một user cụ thể?**

Nhiều workloads/endpoints có thể chia sẻ địa chỉ qua NAT; cần original tuple, mapping và identity tương ứng thời điểm.

**14. SNI và TCP handshake thành công có chứng minh HTTP request đến app không?**

Không. TLS có thể chưa hoàn tất, proxy/mesh có thể chặn, và SNI chỉ là hostname đề xuất.

**15. HTTP 403 sau TLS handshake có nhất thiết là firewall deny không?**

Không. Nó có thể do WAF, gateway, mesh hoặc application authorization; phải xác định nơi phát ra.

**16. Sự khác nhau giữa mitigation và recovery?**

Mitigation giảm hậu quả, có thể chưa xử lý hết nguyên nhân/data backlog; recovery xác minh dịch vụ và giao dịch trở lại mức chấp nhận theo tiêu chí.

**17. Vì sao rollback NetworkPolicy cần negative test?**

Để chắc không mở lại admin/egress path trái chính sách trong khi khôi phục kết nối hợp lệ.

**18. Có nên disable toàn bộ mTLS để chữa certificate lỗi trong production không?**

Không. Cần xác minh CA/cert/trust/identity đúng hop và dùng repair hoặc rollback được phê duyệt, giữ peer authentication.

**19. Vì sao một certificate error cần phân biệt client→ingress và ingress→backend?**

Đó là các TLS sessions khác nhau với certificates/truststores/owners khác nhau. Sửa sai hop không khắc phục sự cố.

**20. Một flow DROPPED có chứng minh mọi đường ra của workload đều bị chặn không?**

Không. Nó chỉ là verdict tại observation point; còn IPv6, alternate NIC, NAT/peering và routes khác.

**21. DDoS và retry storm có thể tạo dashboard giống nhau thế nào?**

Cùng tăng request rate, latency, errors và pressure. Cần xem user/session context, client retries, backend dependency, edge mitigation và business traffic.

**22. Khi suspect exfiltration, outbound bytes lớn có phải bằng chứng dữ liệu nhạy cảm bị lấy không?**

Không. Có thể là backup/job hợp lệ; cần app data-access logs, DLP, destination resource audit, source attribution và evidence preservation.

**23. Vì sao IC cần phân biệt hành động containment với restoration?**

Containment giảm khả năng gây hại, restoration phục hồi dịch vụ; một số cách phục hồi có thể mở lại đường tấn công, còn containment có thể giảm availability.

**24. Khi provider báo sự cố đã kết thúc, có nên đóng incident ngay?**

Không. Cần đo **synthetic/business tests, error rates và data queues** tại môi trường của mình, không chỉ dựa provider status.

**25. Failover sang region B có được coi thành công chỉ vì DNS trỏ sang B?**

Không. Phải xác minh traffic đến B, platform capacity, cert/identity, dữ liệu replication state, RTO/RPO và business operations.

**26. Vì sao RPO quan trọng trong network failover?**

Vì đường mạng đã phục hồi ở B có thể vẫn không có dữ liệu mới nhất, dẫn đến mất hoặc lệch trạng thái giao dịch; cần chiến lược consistency.

**27. Khi traces không có request ID, có kết luận request không tới application không?**

Chưa chắc. Instrumentation/log pipeline có thể mất/sampling; cần xác minh logging health và bằng chứng ở các hop khác.

**28. Vì sao một incident cần timeline UTC?**

Để tương quan logs giữa edge, Kubernetes, endpoints và app. Còn phải kiểm tra clock sync/ingest lag, không chỉ đổi timezone nhãn.

**29. Tại sao không dùng client request ID tùy ý làm identity tin cậy?**

Client có thể gửi ID giả hoặc trùng; gateway/telemetry phải xác minh hoặc tạo trusted correlation identifier nếu dùng cho audit.

**30. Security invariant là gì trong rollout khẩn cấp?**

Là điều kiện bảo mật không được đánh đổi, ví dụ chỉ cho ingress→backend/8443 nhưng admin zone vẫn denied và origin không public.

**31. Khi nào có thể kết thúc incident nếu root cause chưa được tìm đầy đủ?**

Khi service ổn định theo tiêu chí, data/security risk được kiểm soát, còn investigation/follow-up có owner rõ; closure phối hợp khác kết thúc mọi nghiên cứu.

**32. Postmortem nên tránh điều gì?**

Tránh quy trách nhiệm con người dựa trên hậu nghiệm, bỏ qua evidence trái chiều, hoặc đóng action items chỉ vì đã có PR; cần nhìn system/process gaps.

**33. Vì sao đo MTTR không đủ đánh giá phối hợp?**

Vì MTTR có nhiều định nghĩa và có thể bỏ qua detection, business consistency, security exceptions và chất lượng handoff.

**34. Bằng chứng nào chứng minh phục hồi end-to-end tốt hơn một lệnh ping?**

Network/TLS verification, ingress/backend request correlation, application business synthetic transaction, data integrity check và observation window.

**35. Tại sao cùng một sự cố có thể cần Security, DBA, PKI hoặc provider ngoài ba đội?**

Vì ranh giới sở hữu có thể ở **identity, dữ liệu, certificate trust, external service**; IC cần gọi owner thực thay vì ép ba đội xử lý mọi thứ.

**36. Cần gửi gì khi handoff ca trực?**

Incident ID/severity, current impact, facts/hypotheses, changes and revisions, owners, pending tests, known gaps, rollback triggers và next checkpoint.

**37. Vì sao không nên coi “log không có sự kiện” là bằng chứng không có tấn công?**

Sensor có thể không phủ, logs có thể bị sampling/mất, routing có thể bypass; phải ghi coverage và confidence.

**38. Mỗi change trong incident nên có những thành phần nào?**

Owner, approval, exact scope, expected benefit, security/business risks, rollback condition, positive/negative tests và applied revision.

**39. Một service hoàn toàn hết 5xx có chắc không còn hậu quả?**

Không. Queue backlog, retries, pending payments, data loss hoặc security bypass tạm thời có thể tồn tại.

**40. Thế nào là điều phối liên đội tốt?**

Có **một IC, owners rõ, dữ kiện có điểm đo và thời gian, phép thử phân biệt, thay đổi hẹp có kiểm chứng, phục hồi nghiệp vụ và postmortem có trách nhiệm**; không phải số cuộc gọi hay số ticket được chuyển.

## 28. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Có HTTP 502 nghĩa Network team phải sửa.” | 502 có thể phát từ proxy khi upstream lỗi vì route, mTLS, CNI, backend hoặc app. |
| “Network ping OK là network không có vấn đề.” | ICMP reachability không xác minh TCP port/TLS/HTTP/identity. |
| “Application logs không có request nên chắc không liên quan app.” | Có thể do proxy/CNI chặn hoặc logging thiếu; cần correlation và business dependency. |
| “Pod Running/Ready là business healthy.” | Readiness chỉ theo probe, không bảo đảm end-to-end transaction. |
| “Có NetworkPolicy object là packet bị chặn.” | CNI/host/network datapath phải thực thi, cần flow verdict và tests. |
| “Control plane báo healthy nghĩa data plane healthy.” | Config/API status có thể khác packet forwarding thực. |
| “IP source trong cloud log luôn là user/workload gốc.” | NAT, forwarder, proxy và Pod IP reuse có thể che identity. |
| “Một TCP connection = một HTTP request.” | HTTP/2 multiplexing và keep-alive có thể dùng chung connection. |
| “TLS ServerHello nghĩa client đã tin certificate.” | Certificate verification xảy ra theo client profile và các bước sau. |
| “HTTP 403 chắc do firewall.” | Có thể do WAF, gateway, mesh hoặc app authorization. |
| “Một nhóm phải tìm root cause trước khi gọi nhóm khác.” | Gọi đúng owner sớm giúp tạo evidence song song và giảm blind spots. |
| “IC phải tự chạy mọi lệnh.” | IC điều phối, owners thực thi trong phạm vi quyền. |
| “IC có quyền xóa mọi firewall rule khi khẩn cấp.” | Authorization/change controls vẫn áp dụng; cần thẩm quyền phù hợp. |
| “Ai khai báo incident thì phải sửa tận gốc.” | Reporter khác technical owner; IC và DRIs phân vai theo evidence. |
| “Có RACI rồi không cần trao đổi.” | RACI phải được dùng thành action owner/checkpoint/verification thật. |
| “Càng nhiều người cùng sửa càng nhanh.” | Concurrent uncontrolled changes tăng blast radius và mất causal evidence. |
| “Rollback policy cũ luôn an toàn.” | Revision cũ có thể mở lại quyền không cần thiết hoặc lỗi bảo mật. |
| “Tắt WAF/mTLS là cách debug hợp lý nhất.” | Làm giảm security; ưu tiên sửa route/cert/policy hẹp, có lab/approval. |
| “Nới 0.0.0.0/0 cho xong incident, sau sửa.” | Một bypass rộng có thể tồn tại lâu; cần least privilege, expiry và audit. |
| “Containment và recovery luôn cùng mục tiêu.” | Containment giảm threat, recovery tăng availability; phải cân bằng risk. |
| “Restart Pods không ảnh hưởng forensic evidence.” | Có thể xóa ephemeral state, logs hoặc active connections. |
| “Giữ evidence nghĩa không được khôi phục dịch vụ.” | Cần cân bằng bảo vệ khách hàng và bảo toàn bằng chứng theo incident authority. |
| “Một flow DROPPED chứng minh mọi luồng đều bị deny.” | Chỉ chứng minh verdict tại một observation point. |
| “Bytes out tăng nghĩa đã có exfiltration.” | Cần data audit, process/identity, destination và content evidence. |
| “Provider status xanh là ứng dụng mình đã recovered.” | Phải xác minh route, API business tests và queue/data state nội bộ. |
| “Đổi DNS sang region B nghĩa đã hoàn tất failover.” | Cần kiểm chứng traffic steering, cert, workload capacity và RPO/RTO. |
| “HTTP 200 nghĩa giao dịch thanh toán hoàn tất đúng.” | Business integrity, queue events, idempotency và đối soát có thể vẫn lỗi. |
| “Mọi retry sẽ giúp hệ thống hồi phục.” | Retry storms có thể tăng overload và gây xử lý trùng. |
| “Giảm DDoS traffic 70% tức mitigation thành công.” | Cần kiểm tra legitimate-user errors và business availability. |
| “Không thấy log chứng tỏ không có request/attack.” | Log pipeline/sampling/coverage gaps có thể che events. |
| “Sửa tất cả faults cùng lúc giúp nhanh hơn.” | Khó phân biệt tác dụng, làm khó rollback và điều tra root cause. |
| “Một thông báo incident phải đoán đúng nguyên nhân.” | Chỉ thông báo facts, scope, unknowns và actions được xác minh. |
| “Chuyển ticket là đã handoff.” | Người nhận cần đủ owner, impact, timeline, changes, unknowns và checkpoint. |
| “Đóng incident nghĩa không còn investigation.” | Follow-up có owner vẫn có thể tiếp tục sau business recovery. |
| “Postmortem là tìm ai cấu hình sai.” | Phân tích cần tìm cả guardrail, detection, review và process gaps. |
| “Merge PR là action item đã được kiểm chứng.” | Cần validate behavior ở môi trường đúng. |
| “MTTR thấp luôn chứng minh IR tốt.” | Có thể bỏ qua data consistency, security bypass và false closure. |
| “Một chuẩn runbook áp được mọi tổ chức.” | Roles, assets, SLO, legal/privacy và change authority phải theo tổ chức. |

## 29. Tổng kết

**Điều phối giữa network, platform và application team** là năng lực xử lý **một incident xuyên nhiều tầng** mà không làm mất dấu bằng chứng hoặc mở thêm rủi ro bảo mật trong khi phục hồi. Mục tiêu của ba nhóm không phải chứng minh tầng của mình “không lỗi”, mà là cùng trả lời:

> **Dịch vụ bị ảnh hưởng thế nào, packet/request dừng ở đâu, chính sách hay dependency nào tác động, thay đổi nào an toàn nhất và bằng chứng nào xác nhận người dùng cùng dữ liệu đã phục hồi?**

Các nguyên tắc cốt lõi:

1. **Một đầu mối điều phối:** IC quản lý severity, ưu tiên, owners, timeline và quyết định; technical leads chịu trách nhiệm chuyên môn theo phạm vi.
2. **RACI và DRI rõ ràng:** mỗi thay đổi/hypothesis có người chịu trách nhiệm, quyền thao tác, checkpoint và bằng chứng cần gửi.
3. **Bản đồ luồng end-to-end:** DNS, VPN/ZTNA, firewall/NAT, WAF/LB, Kubernetes ingress/CNI, mesh mTLS, API và database là các hop khác nhau.
4. **Không kết luận vượt dữ liệu:** TCP ACK không chứng minh TLS, Pod Ready không chứng minh business khỏe, HTTP 502 không mặc định do network.
5. **Một timeline và nguồn phối hợp chung:** sự kiện UTC, source/hop, policy/deployment revision, fact/hypothesis/unknown, evidence refs và correlation IDs.
6. **Phép thử phân biệt thay vì đổ lỗi:** network tìm flow/path, platform tìm runtime/enforcement, application tìm request/transaction và cùng xác minh.
7. **Containment/rollback có giới hạn:** mỗi production change cần thẩm quyền, scope, security invariants, positive/negative tests và rollback condition.
8. **Bảo vệ bằng chứng và dữ liệu:** khi nghi xâm nhập, phối hợp IR/PKI/Identity/Legal thích hợp; không coi log gap hoặc traffic bytes là kết luận data breach.
9. **Phục hồi thật:** kiểm tra ứng dụng end-to-end, quyền truy cập, tính toàn vẹn giao dịch, queues, replication, không chỉ trạng thái network hay Pod.
10. **Cải tiến dựa trên bằng chứng:** postmortem không đổ lỗi, action items có DRI và test, tabletop và service catalog được duy trì.

Trong học phần **SECURITY_NETWORK_SECURITY**, kỹ năng này kết nối **network segmentation, firewall, VPN, IDS/IPS, DNS, TLS/PKI, packet capture, cloud/Kubernetes networking, telemetry và network incident response** thành một quy trình vận hành thống nhất. Một đội vận hành trưởng thành không đo thành công bằng số người có mặt trong war room, mà bằng **mức độ rõ ràng của trách nhiệm, thời gian tìm đúng bằng chứng, khả năng giảm thiểu an toàn, phục hồi đúng nghiệp vụ và việc loại bỏ các điều kiện khiến sự cố lặp lại**.

### Tài liệu tham khảo và hướng đọc thêm

- **NIST SP 800-61 — Computer Security Incident Handling / Incident Response Recommendations:** mô hình chuẩn bị, phân tích, phản ứng, khôi phục và cải tiến sau sự cố; khi triển khai đối chiếu ấn bản hiện hành.
- **NIST Cybersecurity Framework (CSF) 2.0:** các chức năng Govern, Identify, Protect, Detect, Respond và Recover; dùng để kết nối trách nhiệm kinh doanh/bảo mật/vận hành.
- **NIST SP 800-207 — Zero Trust Architecture:** phân biệt policy decision/enforcement và ứng dụng các nguyên tắc zero trust trong điều tra/quyền truy cập.
- **NIST SP 800-53 — Security and Privacy Controls:** logging/audit, incident response, access control và configuration management theo policy tổ chức.
- **NIST SP 800-41 — Guidelines on Firewalls and Firewall Policy:** quản lý quy tắc firewall và ranh giới kiểm soát mạng.
- **Google SRE Book / SRE Workbook — Managing Incidents, Monitoring Distributed Systems, Postmortem Culture:** tổ chức incident command, observability và hậu kiểm không đổ lỗi.
- **ITIL / ISO/IEC 20000 Service Management:** vai trò quản lý incident, escalation và sự phối hợp với change management.
- **RFC 9110 — HTTP Semantics:** ý nghĩa HTTP status code và hành vi gateway/proxy.
- **RFC 8446 — TLS 1.3:** handshake, alerts, xác thực peer và giới hạn quan sát trên packet capture.
- **RFC 1034/RFC 1035 — DNS:** nguyên tắc phân giải tên và những điểm có thể lỗi khi truy cập dịch vụ.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** dải IP dùng trong ví dụ không đại diện máy chủ thật.
- **Kubernetes Documentation — Deployments, Services, EndpointSlices, Ingress/Gateway API, NetworkPolicy:** desired state, runtime endpoints, routing và data-plane isolation.
- **Cloud networking documentation của nhà cung cấp đang dùng (AWS, Azure, Google Cloud hoặc khác):** effective routes, flow logs, security groups/NSGs, NAT/LB, DNS, private endpoints và audit semantics.
- **OpenTelemetry Specification/Documentation:** trace context, logs/metrics/trace correlation và resource attributes.
- **OWASP Incident Response và Logging/Monitoring hướng dẫn liên quan:** tránh ghi secrets, bảo vệ logs và gắn evidence với application-layer risks.
- **Tài liệu nội bộ được phê duyệt về severity, escalation, authorization, privacy, legal notification, retention và disaster recovery:** đây mới là nguồn quy định ai có quyền thay gì, khi nào gửi thông báo và điều kiện nào cho phép đóng incident thực tế.
