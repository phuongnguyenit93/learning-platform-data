# Quan sát, vận hành và ứng phó sự cố xuyên nền tảng

## 1. Vì sao vận hành hybrid và multi-cloud khó hơn?

Một hệ thống hybrid có thể chạy ứng dụng trên cloud public, database tại data center, identity tại enterprise IdP và kết nối qua VPN hoặc private link. Một hệ thống multi-cloud có thể phân tán workload qua nhiều provider, mỗi bên dùng control plane, billing, logging, IAM, network và công cụ giám sát riêng. Khi một giao dịch thất bại, dấu hiệu có thể nằm ở nhiều miền: DNS, đường truyền, firewall, cloud load balancer, Kubernetes, database, queue hoặc dịch vụ của đối tác.

Thách thức không chỉ là có nhiều dashboard. Các nền tảng khác nhau có thể sử dụng tên metric, đơn vị, timestamp, resource ID, severity và cách phân loại lỗi khác nhau. Log có thể nằm ở nhiều vùng dữ liệu; trace có thể bị đứt tại ranh giới network hoặc message broker; quyền truy cập vận hành có thể không cho phép một đội xem mọi môi trường. Nếu không chuẩn hóa ngữ nghĩa và quy trình, đội trực phải ghép thông tin thủ công trong lúc sự cố đang diễn ra.

**Cross-platform observability and operations** là cách thiết kế khả năng quan sát, quy trình vận hành và ứng phó sự cố xuyên nhiều cloud, data center và dịch vụ bên ngoài. Mục tiêu là có một bức tranh vận hành đủ thống nhất để điều tra end-to-end, đồng thời tôn trọng ranh giới bảo mật, quyền sở hữu và yêu cầu lưu trữ dữ liệu của từng nền tảng.

Một mô hình tốt kết hợp:

- Telemetry có schema và ngữ nghĩa thống nhất.
- Context chung để liên kết service, workload, environment, tenant và deployment.
- Nguồn dữ liệu gốc vẫn thuộc nền tảng chịu trách nhiệm phát sinh.
- Dashboard và cảnh báo theo service journey/SLO, không chỉ theo provider.
- Quy trình incident command, escalation và handoff rõ ràng.
- Runbook, automation và DR drill đã được kiểm chứng.
- Quyền truy cập, retention, residency và chi phí telemetry được kiểm soát.

Trong module **CLOUD_ARCHITECTURE**, nội dung này nối thiết kế hybrid/multi-cloud với reliability, security, networking, platform engineering và operational excellence. Đa cloud không tự động tăng availability; nếu thiếu quan sát và ownership xuyên nền tảng, nó còn có thể làm tăng thời gian phát hiện và khôi phục sự cố.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Thiết kế mô hình observability hợp nhất cho cloud, on-premises và SaaS.
2. Chuẩn hóa resource identity, labels, timestamps, severity và telemetry schema.
3. Liên kết metrics, logs, traces, events và business signals xuyên ranh giới nền tảng.
4. Thiết lập SLI/SLO, dashboard và alert theo service journey.
5. Xây dựng operational ownership, incident command và escalation matrix.
6. Điều tra sự cố liên quan identity, DNS, network, compute, data và provider.
7. Thiết kế runbook, automation, failover và disaster recovery.
8. Kiểm soát data sovereignty, privacy, access và chi phí telemetry.

## 2. Bản đồ vận hành xuyên nền tảng

Trước khi xây dashboard, cần xác định các miền vận hành và cách chúng kết nối.

| Miền | Ví dụ thành phần | Nguồn tín hiệu |
|---|---|---|
| Enterprise/on-premises | Data center, virtualization, storage, DNS, directory | Infrastructure monitoring, syslog, CMDB |
| Cloud A | VM, managed database, object storage, load balancer | Native cloud monitoring, audit logs |
| Cloud B | Kubernetes, serverless, managed queue, CDN | Provider metrics/events, cluster telemetry |
| Shared platform | Identity federation, CI/CD, service mesh, secrets | IAM audit, platform logs, deployment events |
| Network/interconnect | VPN, private link, WAN, firewall, DNS resolver | Flow logs, network probes, device telemetry |
| SaaS/provider | Payment, email, identity, observability | Provider status/API, synthetic checks |
| Business/data | Booking, payment, pipeline, reporting | Domain events, business metrics, data quality |

### 2.1. Service dependency map

Một request có thể đi qua nhiều môi trường:

~~~mermaid
flowchart LR
    User["Customer"] --> Edge["Cloud edge / CDN"]
    Edge --> API["Cloud API service"]
    API --> Link["Private interconnect"]
    Link --> DC["On-prem database"]
    API --> Queue["Cloud message queue"]
    Queue --> Worker["Worker in another cloud"]
    Worker --> SaaS["External payment / notification"]
    API --> IdP["Enterprise identity"]
    DC --> Data["On-prem data platform"]
    Worker --> DataCloud["Cloud analytics"]
~~~

Sơ đồ này cho thấy một service journey có thể phụ thuộc vào network, identity, data và provider ở nhiều miền. Mỗi edge nên ghi protocol, owner, criticality, timeout, retry policy, data classification và telemetry propagation support.

### 2.2. Phân biệt provider health và service health

Provider status page có thể báo một region đang hoạt động bình thường, nhưng ứng dụng vẫn lỗi do route, quota, IAM policy hoặc cấu hình riêng của tenant. Ngược lại, một dịch vụ managed có thể gặp degraded status nhưng workload vẫn đạt SLO nhờ cache/fallback.

Vì vậy cần tối thiểu ba góc nhìn:

- **Provider/platform health:** hạ tầng hoặc dịch vụ nền tảng có sự cố diện rộng hay không.
- **Workload health:** ứng dụng cụ thể có xử lý đúng request/job hay không.
- **Business outcome:** người dùng có hoàn tất luồng nghiệp vụ theo chất lượng cam kết hay không.

## 3. Chuẩn hóa inventory và service identity

Cross-platform observability bắt đầu từ việc nhận diện nhất quán resource và service. Tên resource do provider cấp thường không giống nhau; một service có thể có nhiều deployment ở nhiều region/account.

### 3.1. Service catalog

Mỗi service nên có metadata tối thiểu:

| Trường | Ví dụ |
|---|---|
| Service ID | booking-api |
| Business capability | Booking |
| Owner team | team-booking |
| Criticality | Tier 1 |
| Environment | production |
| Platform | Cloud A, on-prem, Cloud B |
| Region/site | Region A, DC-East |
| Dependencies | Identity, database, queue, payment |
| SLO | Availability, latency, completion |
| Data classification | Confidential |
| Runbook | Link tới quy trình vận hành |
| Escalation | Primary/secondary on-call |

Service ID nên ổn định khi resource được thay thế hoặc chuyển provider. Resource ID và cloud tags có thể thay đổi theo deployment; chúng cần được map về service catalog.

### 3.2. Resource identity và labels

Một schema thống nhất có thể gồm:

- service.name
- service.namespace hoặc product
- deployment.environment
- cloud.provider
- cloud.account/project/subscription
- cloud.region hoặc datacenter.site
- host/container/cluster identity
- team.owner
- tenant scope nếu được phép
- release.version hoặc deployment.revision

Không áp dụng mọi label cho mọi telemetry. Metric cần cardinality thấp; log/trace có thể mang context chi tiết hơn nếu data policy cho phép. Không đưa email, access token, customer name hoặc secret vào label.

### 3.3. Ownership và inventory reconciliation

Inventory cần được cập nhật từ cloud API, CMDB, Kubernetes metadata, infrastructure-as-code và service catalog. Định kỳ đối chiếu:

1. Resource còn tồn tại nhưng không có service owner.
2. Service catalog khai báo dependency không còn đúng.
3. Resource có tag khác với catalog.
4. Endpoint production không có runbook hoặc on-call.
5. Identity/credential dùng cho monitoring không rõ owner.

Inventory chính xác giúp alert có thể route tới đúng người và incident commander biết phạm vi ảnh hưởng.

## 4. Kiến trúc telemetry hợp nhất

Không nhất thiết gửi tất cả telemetry từ mọi nền tảng vào một backend duy nhất. Có thể dùng mô hình federated: mỗi miền thu thập tại chỗ, chuẩn hóa và chuyển những dữ liệu phù hợp sang lớp điều phối/tổng quan.

### 4.1. Mô hình tham khảo

~~~mermaid
flowchart TD
    subgraph OnPrem["On-premises"]
      OAgent["Collectors / agents"]
      OStore["Local telemetry store"]
      OAgent --> OStore
    end
    subgraph CloudA["Cloud A"]
      AAgent["Cloud exporter / collector"]
      AStore["Native monitoring"]
      AAgent --> AStore
    end
    subgraph CloudB["Cloud B"]
      BAgent["Cluster / service collector"]
      BStore["Native monitoring"]
      BAgent --> BStore
    end
    OStore --> Hub["Federated observability layer"]
    AStore --> Hub
    BStore --> Hub
    Hub --> Dash["Unified service dashboards"]
    Hub --> Alert["Alert routing / incident platform"]
    Hub --> Lake["Long-term analytics / audit archive"]
~~~

Federation layer có thể truy vấn, liên kết metadata, tổng hợp alert hoặc nhận bản sao telemetry đã lọc. Dữ liệu gốc vẫn có thể nằm tại từng provider/region để đáp ứng residency, retention và quyền truy cập.

### 4.2. Centralized và federated

| Mô hình | Ưu điểm | Đánh đổi |
|---|---|---|
| Centralized ingestion | Search/correlation tập trung, một nơi điều tra | Egress cost, data residency, central blast radius, phụ thuộc network |
| Federated query | Dữ liệu ở lại miền sở hữu, giảm copy | Query cross-system phức tạp, latency và schema không đồng nhất |
| Hybrid | Centralize metadata/critical signals, giữ raw data tại chỗ | Cần governance rõ về dữ liệu nào được chuyển |

Chọn theo latency điều tra, yêu cầu residency, data classification, chi phí egress, retention và năng lực vận hành. Không sao chép toàn bộ debug log vào một account trung tâm nếu không có mục đích và quyền phù hợp.

## 5. Chuẩn hóa metrics, logs, traces và events

### 5.1. Metrics

Metrics nên mô tả đơn vị đo và ngữ nghĩa thống nhất. Một hệ thống có thể xuất CPU ở percent, một hệ thống khác ở millicore; database connection có thể là active, idle hoặc total. Không chuẩn hóa đơn vị sẽ tạo biểu đồ so sánh sai.

Metric contract nên có:

- Tên và mô tả.
- Type: counter, gauge, histogram.
- Unit và aggregation semantics.
- Labels hợp lệ và cardinality budget.
- Source/platform và collection interval.
- Owner, retention và mapping tới SLI/SLO.

### 5.2. Logs

Dùng structured logs với timestamp có timezone/UTC, severity, service ID, environment, request/trace ID, event name, error category và deployment version. Chuẩn hóa severity levels như DEBUG, INFO, WARN, ERROR, FATAL; mapping các mức provider-specific vào taxonomy nội bộ.

Không giả định một dòng WARN ở provider A có độ nghiêm trọng giống WARN ở ứng dụng. Cần quy ước mapping và event semantics.

### 5.3. Distributed traces

Trace context có thể đi qua HTTP, gRPC, message headers và service mesh nếu các thành phần hỗ trợ propagation. Khi đi qua hệ thống cũ hoặc partner không hỗ trợ, có thể dùng correlation ID ở boundary và tạo span link hoặc event liên kết.

Không phải mọi provider đều chia sẻ cùng trace backend. Có thể export trace ID, span ID và metadata cần thiết thay vì buộc raw span data đi qua ranh giới không được phép.

### 5.4. Events

Các event quan trọng gồm deployment, scaling, failover, certificate rotation, IAM change, DNS update, backup completion, provider incident và maintenance. Event timeline giúp liên hệ thay đổi với metric spike.

### 5.5. Chuẩn timestamp

Đồng bộ clock bằng NTP hoặc dịch vụ tương đương; ghi UTC và giữ timezone/source nếu cần; theo dõi clock skew; phân biệt event time với ingestion time. Clock skew giữa data center và cloud có thể làm trace sắp xếp sai hoặc incident timeline thiếu chính xác.

## 6. Correlation xuyên ranh giới nền tảng

Khi transaction đi qua nhiều cloud, cần context đủ để nối các thành phần:

- Trace ID/span ID cho distributed request.
- Correlation/operation ID cho luồng nghiệp vụ.
- Service ID và deployment revision.
- Tenant hoặc partition identifier đã được kiểm soát.
- Region/site/provider và network path.
- Change/incident ID.

### 6.1. Ví dụ flow booking hybrid

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Cloud Booking API
    participant N as Network interconnect
    participant DB as On-prem database
    participant Q as Cloud queue
    participant W as Worker in Cloud B
    U->>API: Create booking (trace context)
    API->>N: Private connection
    N->>DB: Check inventory / commit
    DB-->>N: Result
    N-->>API: Database response
    API->>Q: Publish event + correlation ID
    Q->>W: Deliver event
    W->>W: Update downstream workflow
    W-->>Q: Ack / retry / DLQ decision
    API-->>U: Booking response
~~~

API response thành công chưa chắc toàn bộ asynchronous workflow hoàn tất. Dashboard cần tách API acceptance, database commit và downstream completion. Khi trace bị đứt tại queue hoặc legacy system, correlation ID và business event cho phép nối timeline.

### 6.2. Bảo vệ correlation context

Không đưa credential hoặc PII vào trace baggage tùy ý. Trace context từ client bên ngoài cần được xác thực/giới hạn để tránh header spoofing, cardinality abuse hoặc truyền dữ liệu không tin cậy qua hệ thống nội bộ.

## 7. SLI/SLO xuyên service và provider

SLO nên đo trải nghiệm của người dùng hoặc business journey, không chỉ availability của từng component.

### 7.1. SLI theo journey

Ví dụ booking transaction gồm API ở Cloud A, database on-prem và notification worker ở Cloud B. Có thể định nghĩa:

| SLI | Đo ở đâu | Ý nghĩa |
|---|---|---|
| API availability | Public API boundary | Người dùng gửi request và nhận phản hồi hợp lệ |
| Booking commit success | Business transaction/database boundary | Booking được ghi nhận nhất quán |
| Confirmation completion | Async workflow | Booking đạt trạng thái terminal hợp lệ trong deadline |
| End-to-end latency | Từ user request tới confirmation | Thời gian hoàn tất hành trình |
| Data freshness | Data platform/reporting | Báo cáo cập nhật trong SLA |

Không cộng hoặc nhân đơn giản availability của các provider để suy ra SLO end-to-end nếu dependency có retry, redundancy, fallback hoặc mức sử dụng khác nhau. Đo trực tiếp journey khi có thể.

### 7.2. Dependency budget

Mỗi dependency nên có timeout, retry, circuit breaker/fallback và objective phù hợp. Service owner cần biết ngân sách latency mà dependency được phép tiêu thụ. Ví dụ API có deadline 2 giây thì không thể chờ database 2 giây, payment 2 giây và network retry nhiều lần.

### 7.3. Error budget và ownership

Một service có thể đạt SLO riêng nhưng làm journey fail vì downstream. Cần xác định:

- Journey owner chịu trách nhiệm end-to-end.
- Component owner xử lý nguyên nhân trong miền của họ.
- Platform/network/security owner hỗ trợ dependency dùng chung.
- Provider escalation contact khi lỗi nằm ngoài quyền kiểm soát.

## 8. Dashboard theo service journey

Dashboard tổng quan xuyên nền tảng nên tổ chức quanh service, product và journey; provider dashboard là nơi drill-down vào tài nguyên cụ thể.

### 8.1. Bố cục gợi ý

| Khu vực | Nội dung |
|---|---|
| Business outcome | Booking success, payment completion, user-impact estimate |
| End-to-end SLO | Availability, latency, completion, error budget |
| Service map | Dependency, owner, region, provider và criticality |
| Application | RED, saturation, retries, queue age |
| Infrastructure | CPU, memory, storage, DB, node, network |
| Identity/security | Auth failures, policy changes, certificate status |
| Change timeline | Deploy, config, DNS, failover, maintenance |
| Data quality | Freshness, reconciliation, missing/duplicate events |

### 8.2. Dashboard phải có freshness

Nếu telemetry từ on-prem trễ 5 phút và telemetry cloud gần realtime, một dashboard hợp nhất có thể so sánh hai thời điểm khác nhau. Hiển thị last received timestamp, ingestion lag và data gap; không diễn giải metric thiếu dữ liệu như zero.

### 8.3. Synthetic monitoring

Synthetic check từ nhiều vị trí có thể kiểm tra DNS, TLS, login, API transaction và luồng nghiệp vụ đại diện. Nên chạy từ cả vị trí cloud và mạng doanh nghiệp khi cần xác minh private path. Synthetic test cần tài khoản/test data riêng, idempotency và giới hạn tác động lên production.

## 9. Alert routing và phân loại mức độ

Alert xuyên nền tảng phải route theo service owner và miền xử lý. Không gửi tất cả alert tới một đội cloud trung tâm rồi yêu cầu họ tự tìm owner.

### 9.1. Severity model tham khảo

| Mức | Mô tả | Phản ứng |
|---|---|---|
| SEV-1 | Critical business journey ngừng hoạt động hoặc ảnh hưởng diện rộng | Incident commander, bridge, owner các miền, executive/customer communication theo policy |
| SEV-2 | Suy giảm lớn, có workaround hoặc một phần người dùng bị ảnh hưởng | On-call liên quan, phối hợp cross-team, cập nhật định kỳ |
| SEV-3 | Ảnh hưởng giới hạn, chưa vi phạm SLO đáng kể | Team owner xử lý theo giờ làm việc/priority |
| SEV-4 | Warning, drift hoặc capacity risk chưa ảnh hưởng dịch vụ | Ticket/backlog, theo dõi và khắc phục có kế hoạch |

Severity phải dựa trên user/business impact, scope và urgency, không chỉ theo loại resource hoặc provider status.

### 9.2. Alert payload

Alert nên có:

- Service/journey và environment.
- Start time, duration, data freshness.
- User/business impact hoặc SLI đang vi phạm.
- Provider/region/site và dependency nghi vấn.
- Owner/on-call/escalation.
- Dashboard, trace query và runbook.
- Change/deployment liên quan gần nhất.

Không tạo alert lặp từ cùng một nguyên nhân ở từng tầng nếu có thể group/correlate. Tuy nhiên không gộp nhiều failure độc lập thành một alert duy nhất làm che khuất tác động.

## 10. Incident command xuyên nền tảng

Một sự cố liên quan nhiều provider cần một đầu mối điều phối và phân công rõ. Người điều phối không nhất thiết phải là người trực tiếp sửa mọi thành phần.

### 10.1. Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander (IC) | Xác định ưu tiên, scope, quyết định và điều phối |
| Technical lead | Tổng hợp giả thuyết, giao điều tra kỹ thuật |
| Service owner | Chẩn đoán và phục hồi workload thuộc service |
| Platform/network lead | Điều tra cloud, data center, DNS và interconnect |
| Security lead | Xử lý credential compromise, policy hoặc data exposure |
| Communications lead | Cập nhật stakeholder theo cadence |
| Scribe | Ghi timeline, quyết định, owner và evidence |
| Provider liaison | Mở/escalate support case và truyền thông tin provider |

Trong sự cố nhỏ, một người có thể kiêm nhiều vai trò; với SEV cao nên tách IC khỏi technical lead để giữ khả năng điều phối.

### 10.2. Incident lifecycle

~~~mermaid
flowchart TD
    Detect["Detect / alert"] --> Triage["Triage and classify impact"]
    Triage --> Declare{"Incident declared?"}
    Declare -->|No| Owner["Route to service owner"]
    Declare -->|Yes| IC["Assign incident commander"]
    IC --> Scope["Establish scope and timeline"]
    Scope --> Mitigate["Mitigate / restore service"]
    Mitigate --> Verify["Verify SLI and business recovery"]
    Verify --> Close["Close incident and preserve evidence"]
    Close --> Review["Post-incident review / corrective actions"]
~~~

### 10.3. Communication cadence

Với incident lớn, thống nhất tần suất cập nhật, ví dụ mỗi 15 hoặc 30 phút tùy mức ảnh hưởng. Mỗi update gồm impact hiện tại, điều đã biết, hành động đang chạy, rủi ro, quyết định cần hỗ trợ và thời điểm update tiếp theo. Không suy đoán nguyên nhân như thể đã xác nhận.

## 11. Quy trình điều tra theo lớp

Khi một journey fail, điều tra theo dependency graph để tránh đổ lỗi cho provider đầu tiên có status cảnh báo.

### 11.1. Trình tự

1. Xác nhận user/business impact, start time và scope theo tenant/region/channel.
2. Kiểm tra synthetic journey và SLI end-to-end.
3. Xác định service map và dependency path trong thời gian sự cố.
4. Kiểm tra deployment/config/IAM/DNS/certificate change gần nhất.
5. Phân tách DNS, routing, TLS, authentication, application, data và provider errors.
6. So sánh telemetry từ cả hai đầu network path.
7. Theo trace/log tới span chậm/lỗi; nếu đứt trace, dùng correlation/business ID.
8. Kiểm tra saturation, quota, connection pool, queue lag và replication lag.
9. Chọn mitigation có blast radius thấp nhất.
10. Xác minh business state, dữ liệu và SLO sau khôi phục.

### 11.2. Các điểm kiểm tra ở hybrid boundary

| Lớp | Câu hỏi |
|---|---|
| DNS | Resolver nào được dùng? Record/TTL/delegation có đúng? |
| Network | Route, VPN/BGP, private link, firewall và MTU có thay đổi? |
| TLS | Certificate chain, SAN, expiry và trust store có đúng? |
| Identity | Federation issuer/audience, clock skew, token và role có hợp lệ? |
| Compute | Node, pod, VM, quota, autoscaling có healthy? |
| Data | DB connection, lock, replication, consistency và schema? |
| Queue | Publish/consume, lag, visibility, retry và DLQ? |
| Provider | Status, quota, rate limit và support case? |

## 12. Runbook và automation

Runbook cần mô tả hành động có thể thực hiện trong sự cố, không chỉ danh sách lệnh.

### 12.1. Cấu trúc runbook

1. Tên alert và điều kiện kích hoạt.
2. Service/journey bị ảnh hưởng và impact dự kiến.
3. Owner, escalation và điều kiện declare incident.
4. Dashboard/query/trace cần mở.
5. Các giả thuyết phổ biến và cách xác minh.
6. Mitigation an toàn, điều kiện dừng và rollback.
7. Kiểm tra data correctness và business recovery.
8. Communication và provider escalation.
9. Evidence cần lưu và bước follow-up.

### 12.2. Automation

Có thể tự động hóa:

- Tạo incident và gắn service/owner từ alert metadata.
- Thu thập snapshot metrics/logs/change events.
- Kiểm tra DNS/TLS endpoint từ nhiều vị trí.
- Đối chiếu deployment revision và config drift.
- Chạy health check hoặc synthetic transaction an toàn.
- Mở provider support case qua quy trình được phê duyệt.
- Chuyển traffic hoặc failover theo playbook có guardrail.

Không tự động thực hiện hành động phá hủy hoặc có blast radius lớn chỉ từ một metric đơn lẻ. Failover, revoke key, thay DNS hoặc xóa resource cần điều kiện, approval và xác minh phù hợp.

### 12.3. Runbook phải được diễn tập

Kiểm thử runbook trong staging hoặc game day; xác minh quyền IAM và network thực sự cho phép hành động; kiểm tra lệnh còn đúng với phiên bản CLI/API; ghi nhận thời gian hoàn tất và bước mơ hồ; cập nhật owner sau khi tổ chức thay đổi.

## 13. Failover và disaster recovery xuyên nền tảng

Multi-cloud hoặc hybrid có thể cung cấp phương án dự phòng, nhưng failover chỉ hữu ích khi ứng dụng, dữ liệu, identity, network, DNS và quy trình vận hành đều sẵn sàng.

### 13.1. DR terms

- **RTO:** thời gian mục tiêu để khôi phục dịch vụ.
- **RPO:** mức mất dữ liệu tối đa có thể chấp nhận, biểu diễn bằng thời gian/điểm dữ liệu.
- **Failover:** chuyển workload hoặc traffic sang môi trường dự phòng.
- **Failback:** quay lại môi trường chính sau khi ổn định.
- **Active-active:** nhiều site/region cùng phục vụ.
- **Active-passive:** site chính phục vụ, site dự phòng chờ hoặc chạy một phần.

### 13.2. Những phụ thuộc thường bị bỏ quên

- Identity federation và emergency admin path.
- DNS registrar, authoritative DNS và DNSSEC.
- KMS/key access, certificate và secrets.
- Network route, firewall rule, VPN/private circuit.
- Image/artifact registry và package repository.
- Database replication, write authority và consistency.
- Queue, event replay, idempotency và deduplication.
- License, quota và capacity ở site đích.
- Telemetry/alert routing khi site chính unavailable.

### 13.3. Quy trình failover

1. Xác nhận incident và điều kiện kích hoạt DR.
2. Kiểm tra site đích có capacity, identity, network và key access.
3. Xác định trạng thái dữ liệu, replication lag và write authority.
4. Fence hoặc ngăn writer cũ để tránh split-brain.
5. Promote database/queue theo thứ tự đã thiết kế.
6. Khởi động workload và xác minh dependency.
7. Chuyển traffic qua DNS/load balancer/global routing theo plan.
8. Chạy synthetic và business transaction.
9. Theo dõi SLO, data correctness và duplicate/loss.
10. Công bố trạng thái và ghi timeline.

Không thực hiện failover database chỉ vì health probe của một node thất bại. Cần xác định quorum, replication state và quyền ghi để tránh split-brain.

### 13.4. Failback

Failback thường phức tạp hơn failover vì phải đồng bộ dữ liệu đã phát sinh trong site dự phòng, xác minh consistency, chuyển write authority, cập nhật routing và bảo đảm không có hai hệ thống cùng nhận ghi. Nên có kế hoạch riêng, không coi failback là thao tác đảo ngược tức thì.

## 14. Security operations và quyền truy cập xuyên nền tảng

Một observability hub tập trung có thể nhìn thấy dữ liệu nhạy cảm từ nhiều miền. Cần thiết kế quyền và trust boundary:

- Federation identity riêng cho operator và automation.
- RBAC theo service/environment/platform; JIT cho quyền production đặc quyền.
- Data access policy theo classification, tenant và region.
- Mask/redact PII, token, secret và payload nhạy cảm.
- Audit mọi truy vấn/export và hành động remediation.
- Credential ngắn hạn, rotation và emergency revocation.
- Segmentation giữa telemetry read access và control-plane write access.
- Không dùng tài khoản admin chung cho mọi provider.

Người điều tra incident cần đủ dữ liệu để xử lý nhưng không nhất thiết phải đọc payload cá nhân hoặc secret. Có thể cung cấp metadata, trace attributes đã lọc và quy trình nâng quyền có audit khi cần.

## 15. Data sovereignty, residency và retention

Log/trace có thể chứa IP, tenant ID, user context, request payload hoặc thông tin vận hành nhạy cảm. Khi thu thập xuyên quốc gia/provider, cần xác định dữ liệu nào được phép rời vùng.

### Thiết kế kiểm soát

- Phân loại telemetry trước khi export.
- Giữ raw logs/traces trong region/site phù hợp khi có yêu cầu.
- Chuyển metadata hoặc aggregate đã giảm nhạy cảm sang global view.
- Thiết lập retention riêng cho operational telemetry và audit evidence.
- Mã hóa in transit/at rest và quản lý key theo boundary.
- Hạn chế query/export cross-region theo role và purpose.
- Kiểm tra provider subprocessors và nơi lưu trữ telemetry.
- Xóa dữ liệu theo policy nhưng giữ evidence cần thiết theo nghĩa vụ pháp lý/kiểm toán.

Không giả định log đã được mask tại agent nếu pipeline còn một đường ingest khác. Cần kiểm tra redaction end-to-end.

## 16. Cost và performance của telemetry xuyên nền tảng

Export toàn bộ logs/traces từ nhiều provider có thể tạo egress, ingest, storage và query cost lớn. Central hub cũng có thể thành bottleneck khi incident xảy ra.

Thực hành:

- Giữ raw telemetry tại nguồn khi có thể; export critical signal hoặc sampled data.
- Dùng regional collectors và buffer khi network gián đoạn.
- Ưu tiên error/slow trace theo sampling policy.
- Giảm metric cardinality và duplicate collection.
- Thiết lập quota/rate limit cho telemetry ingestion.
- Theo dõi pipeline lag, dropped data và collector health.
- Có local dashboard/runbook khi central observability không khả dụng.
- Ước tính chi phí egress giữa provider và storage retention.

Telemetry pipeline phải chịu được chính sự cố mà nó được dùng để quan sát. Nếu mất kết nối WAN làm collector không gửi được dữ liệu, cần buffer có giới hạn, retry có backoff và chỉ báo rõ khoảng trống telemetry.

## 17. Case study: vận hành nền tảng đặt phòng hybrid multi-cloud

**Bối cảnh:** nền tảng đặt phòng phục vụ khách hàng qua API trên Cloud A. Inventory database vẫn nằm tại data center vì yêu cầu tích hợp hệ thống cũ. Notification worker và analytics chạy trên Cloud B. Enterprise identity cung cấp SSO; payment provider là SaaS. Các team hiện dùng ba dashboard riêng và thường mất nhiều thời gian xác định sự cố nằm ở network hay database.

### 17.1. Kiến trúc vận hành

~~~mermaid
flowchart TD
    subgraph DC["Data center"]
      Legacy["Inventory DB / legacy service"]
      LocalObs["Local collectors and store"]
      Legacy --> LocalObs
    end
    subgraph A["Cloud A"]
      API["Booking API / edge"]
      AObs["Cloud A telemetry"]
      API --> AObs
    end
    subgraph B["Cloud B"]
      Worker["Notification / analytics workers"]
      BObs["Cloud B telemetry"]
      Worker --> BObs
    end
    API <--> Legacy
    API --> Worker
    LocalObs --> Fed["Federated observability"]
    AObs --> Fed
    BObs --> Fed
    Fed --> Dash["Journey dashboard"]
    Fed --> Inc["Incident platform"]
    IdP["Enterprise IdP"] --> API
    Pay["Payment SaaS"] --> API
~~~

### 17.2. Chuẩn hóa vận hành

1. Catalog gán service ID, owner, criticality, dependencies và runbook cho API, database, worker, identity và payment integration.
2. Mỗi miền giữ raw telemetry tại chỗ; export metrics và metadata cần thiết sang federated layer.
3. Trace context đi qua API và message queue; legacy database boundary dùng operation/correlation ID.
4. Dashboard tổng hợp booking success, API latency, database wait, interconnect health và worker queue age.
5. Alert gắn với journey owner; network/database/platform owner được route theo dependency.
6. Incident SEV cao chỉ định IC, technical lead, provider liaison và scribe.
7. DR plan xác định database write authority, worker replay, identity/key và DNS prerequisites.

### 17.3. Ví dụ điều tra sự cố

Booking confirmation giảm trong 10 phút, trong khi provider status pages đều xanh:

1. Journey SLI phát alert và chỉ ra channel/API bị ảnh hưởng.
2. Trace cho thấy span gọi inventory database tăng latency.
3. Metrics ở Cloud A cho thấy connection pool wait tăng.
4. Metrics ở data center cho thấy DB query latency bình thường nhưng packet retransmit trên interconnect tăng.
5. Network owner xác minh route/firewall/WAN telemetry và phát hiện một đường kết nối dự phòng đang flap.
6. IC yêu cầu chuyển sang route ổn định theo runbook; team database kiểm tra connection recovery.
7. Synthetic transaction và business SLI xác nhận booking confirmation phục hồi.
8. Post-incident review ghi nhận thiếu alert cho interconnect packet loss và cập nhật capacity/failover test.

Tình huống là ví dụ minh họa; nguyên nhân thực tế phải được xác minh từ telemetry hai đầu và network devices.

### 17.4. Tiêu chí nghiệm thu

- Một dashboard hiển thị journey SLI và dependency map xuyên Cloud A, data center và Cloud B.
- Mỗi service có owner, runbook, criticality và on-call.
- Trace/correlation ID nối được synchronous và asynchronous workflow.
- Collector mất kết nối có buffer, retry và cảnh báo data gap.
- Raw telemetry được giữ theo residency/classification policy.
- Alert route đúng team và incident command có role/cadence rõ.
- DR drill xác minh identity, network, data, DNS, key và observability ở site dự phòng.
- Dashboard hiển thị data freshness để không nhầm missing telemetry với zero.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng một dashboard cho mọi provider nhưng không chuẩn hóa semantics | So sánh metric sai đơn vị/ngữ nghĩa | Metric contract và normalization layer |
| Chỉ xem provider status page | Bỏ lỡ lỗi account, route, quota hoặc config riêng | SLI/workload health và synthetic transaction |
| Đẩy toàn bộ raw telemetry về một region | Egress cost, residency và blast radius | Federated/hybrid data architecture |
| Không có service catalog/owner | Alert không tới đúng người | Owner metadata và inventory reconciliation |
| Trace bị đứt tại hybrid boundary | Không xác định được dependency chậm | Propagation và correlation ID ở boundary |
| Clock skew giữa on-prem và cloud | Timeline/trace sai thứ tự | Clock sync, UTC và skew monitoring |
| Mỗi team có severity riêng | Incident triage và escalation không thống nhất | Shared severity/impact taxonomy |
| Tập trung mọi incident vào một đội platform | Bottleneck và ownership mơ hồ | Journey owner, component owner và IC |
| Failover chỉ kiểm tra compute | Site dự phòng thiếu key, DNS, quota hoặc data | DR dependency checklist và game day |
| Tự động failover khi một probe fail | Split-brain hoặc chuyển traffic sai | Multi-signal gate, fencing và approval |
| Không buffer telemetry khi WAN mất | Mất bằng chứng đúng lúc cần điều tra | Local store, bounded buffer và data-gap alert |
| Bỏ qua privacy/residency | Rò dữ liệu hoặc vi phạm policy | Classification, redaction, regional retention |
| Incident đóng khi pod xanh | Business journey/data vẫn chưa phục hồi | Verify SLI, correctness và async completion |

## 19. Checklist review vận hành xuyên nền tảng

### Observability và inventory

- [ ] Có service catalog với stable service ID, owner, criticality và dependency.
- [ ] Resource từ cloud/on-prem/SaaS được map về service identity.
- [ ] Metric có unit/semantics; log có severity/timestamp; trace có correlation.
- [ ] Clock sync và ingestion freshness được theo dõi.
- [ ] Có federated/hybrid design phù hợp residency và egress cost.
- [ ] Local observability vẫn dùng được khi central hub hoặc WAN mất.

### SLO, dashboard và alert

- [ ] SLI đo business/service journey end-to-end.
- [ ] Dashboard tách provider health, workload health và business outcome.
- [ ] Có RED/USE/dependency signals và change timeline.
- [ ] Alert có impact, service owner, severity, runbook và escalation.
- [ ] Missing telemetry được phân biệt với metric bằng zero.
- [ ] Synthetic monitoring bao gồm các boundary quan trọng.

### Incident và recovery

- [ ] Incident command, technical lead, scribe và communication role được định nghĩa.
- [ ] Có escalation/contact cho từng provider và network/data center owner.
- [ ] Runbook có điều kiện, bước xác minh, rollback và evidence.
- [ ] Automation có guardrail, approval và audit.
- [ ] DR có RTO/RPO, write authority, fencing và failback plan.
- [ ] Game day kiểm tra identity, DNS, key, network, data và observability.

### Security, governance và cost

- [ ] Operator access dùng federation/JIT và least privilege.
- [ ] Telemetry được phân loại, redact, encrypt và audit.
- [ ] Data residency/retention được định nghĩa theo miền.
- [ ] Không ghi secret/PII không cần thiết vào log/trace/metric.
- [ ] Theo dõi telemetry egress, ingestion, retention, cardinality và dropped data.
- [ ] Có owner cho schema, collector, pipeline và service catalog.

## 20. Bài tập thực hành

**Bối cảnh:** nền tảng đặt phòng chạy Booking API trên Cloud A, inventory database on-premises, notification worker trên Cloud B và payment SaaS. Khi traffic tăng, booking confirmation thỉnh thoảng chậm; provider dashboard đều báo healthy. Trace hiện chỉ tồn tại trong Booking API, logs mỗi miền dùng timezone/severity khác nhau, không có một incident commander xuyên team.

Hãy thiết kế mô hình vận hành:

1. Vẽ service dependency map và xác định owner/criticality từng node/edge.
2. Xây schema service catalog và resource labels xuyên provider.
3. Chọn centralized, federated hay hybrid telemetry; giải thích residency, egress và failure mode.
4. Định nghĩa metric/log/trace/event contract, timestamp và correlation strategy.
5. Chọn SLI/SLO cho API acceptance, booking commit và async confirmation.
6. Thiết kế dashboard và alert để phân biệt provider health, workload health và business impact.
7. Viết severity model, incident command role và communication cadence.
8. Tạo runbook điều tra DNS, TLS, identity, interconnect, database và queue.
9. Thiết kế failover/DR bao gồm identity, key, DNS, data write authority và worker replay.
10. Lập game day cho WAN outage, database failover, trace pipeline loss và payment provider degradation.

**Gợi ý tự kiểm tra:** Một provider có status xanh không chứng minh service journey đạt SLO. Raw telemetry không nhất thiết phải rời region; metadata/aggregate có thể đủ cho global view. Failover cần bảo đảm dữ liệu và write authority, không chỉ chuyển traffic. Incident chỉ đóng khi business operation, data correctness và telemetry xác nhận đã phục hồi.

## 21. Ghi nhớ

Vận hành hybrid và multi-cloud cần một mô hình chung về service identity, dependency, telemetry, SLO, ownership và incident response. Có thể dùng central, federated hoặc hybrid observability; lựa chọn phải cân bằng khả năng correlation với data sovereignty, quyền truy cập, egress cost và resilience của chính telemetry pipeline.

Thiết kế tốt tổ chức dashboard quanh service journey, phân biệt provider/platform health với workload và business health, chuẩn hóa timestamp/labels/severity, liên kết trace qua boundary và gắn alert với owner/runbook. Incident xuyên nền tảng cần incident commander, technical lead, communication và provider liaison; DR phải kiểm chứng identity, network, key, DNS, data và failback. Quan trọng nhất, chỉ xác nhận phục hồi sau khi business SLI và tính đúng đắn dữ liệu trở lại bình thường, không chỉ vì từng resource báo healthy.
